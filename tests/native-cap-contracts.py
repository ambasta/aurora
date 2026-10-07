#!/usr/bin/env python3
"""Check resource configuration through the real entrypoints, without native work."""
from pathlib import Path
import argparse
from collections import Counter
import os
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import time
import tempfile
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
CONSUMERS = (
    ('tests/compiler/package_identity.py', 128, False),
    ('tests/compiler/package_manifest.py', 256, False),
    ('tests/compiler/package_graph.py', 256, False),
    ('tests/kernel-budget-native.py', 128, True),
    ('tests/kernel-round-robin-native.py', 128, True),
    ('tests/kernel-ipc-transition-native.py', 128, True),
)


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def rejected(call, reason):
    try:
        call()
    except (AssertionError, RuntimeError) as error:
        require(reason in str(error), 'wrong rejection: ' + str(error))
        return
    raise RuntimeError('configuration boundary was accepted')


def artifact_root(value):
    raw = Path(value).absolute()
    require('..' not in raw.parts, 'artifact path traversal denied')
    require(not any(p.is_symlink() for p in (raw, *raw.parents)), 'artifact symlink denied')
    result = raw.resolve(strict=False)
    require(result.is_relative_to(ROOT), 'artifacts must remain in the candidate')
    return result


def accounting(module, native):
    cap, reserve, floor = 1024 << 20, 65536, 1 << 30
    output = ROOT / 'build' / 'uncreated-accounting-control'
    if native:
        with mock.patch.object(module, 'allocated', return_value=cap - 1), \
             mock.patch.object(module, 'free_bytes', return_value=floor):
            module.guard(output, 1024)
        with mock.patch.object(module, 'allocated', return_value=cap), \
             mock.patch.object(module, 'free_bytes', return_value=floor):
            rejected(lambda: module.guard(output, 1024), 'allocation cap')
        with mock.patch.object(module, 'allocated', return_value=0), \
             mock.patch.object(module, 'free_bytes', return_value=floor - 1):
            rejected(lambda: module.guard(output, 1024), 'free-space floor')
        with mock.patch.object(module, 'allocated', return_value=cap - reserve), \
             mock.patch.object(module, 'free_bytes', return_value=floor + reserve):
            rejected(lambda: module.guard(output, 1024, reserve), 'allocation cap')
        return
    runner = object.__new__(module.Runner)
    runner.cap, runner.peak, runner.artifacts = cap, 0, output
    # Manifest/Graph inherit their accounting implementation from the shared runner.
    implementation = sys.modules[module.Runner.budget.__module__]
    with mock.patch.object(implementation, 'allocated_bytes', return_value=cap - reserve), \
         mock.patch.object(implementation, 'free_bytes', return_value=floor + reserve):
        runner.budget(reserve)
        rejected(lambda: runner.budget(reserve + 1), 'owned-output')
    with mock.patch.object(implementation, 'allocated_bytes', return_value=cap - reserve), \
         mock.patch.object(implementation, 'free_bytes', return_value=floor + reserve - 1):
        rejected(lambda: runner.budget(reserve), 'free floor')


def owned_output_checks(out):
    """Real filesystem scope controls, using small caps rather than large allocation."""
    sys.path.insert(0, str(ROOT / 'scripts'))
    import owned_outputs
    import package_native_runner as transport

    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, ROOT / path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    with tempfile.TemporaryDirectory(prefix='owned-controls-', dir=out) as temporary:
        checkout = Path(temporary)
        unrelated = checkout / 'unrelated-prior-artifact'
        unrelated.write_bytes(b'history\n' * (256 << 10))
        before = hashlib.sha256(unrelated.read_bytes()).hexdigest()
        with (checkout / 'old-sparse-image').open('wb') as stream:
            stream.truncate(700 << 20)
        first, second = checkout / 'run-one', checkout / 'run-two'
        cap = 256 << 10
        for directory in (first, second):
            directory.mkdir()
            (directory / 'output').write_bytes(bytes(160 << 10))
        require(owned_outputs.allocated_bytes(checkout) > cap, 'control checkout must exceed own-output cap')
        require(owned_outputs.allocated_bytes(first, second) > cap, 'independent roots must exceed combined cap')
        for index, (name, _, native) in enumerate(CONSUMERS):
            module = load('scope_subject_' + str(index), name)
            for directory in (first, second):
                with mock.patch.object(module, 'ROOT', checkout):
                    if native:
                        with mock.patch.object(module, 'candidate_cap', return_value=cap):
                            module.guard(directory, 128)
                            rejected(lambda: module.guard(directory, 128, cap), 'allocation cap')
                    else:
                        runner = object.__new__(module.Runner)
                        runner.root, runner.artifacts, runner.cap, runner.peak = checkout, directory, cap, 0
                        require(runner.budget() == owned_outputs.allocated_bytes(directory), 'wrong owned root')
                        rejected(lambda: runner.budget(cap), 'owned-output')
            overflow = second / 'overflow'
            overflow.write_bytes(bytes(cap))
            if native:
                with mock.patch.object(module, 'candidate_cap', return_value=cap):
                    rejected(lambda: module.guard(second, 128), 'allocation cap')
            else:
                rejected(runner.budget, 'owned-output')
            overflow.unlink()
        xfs = load('owned_xfs_control', 'tests/compiler/xfs_root.py')
        with mock.patch.object(xfs, 'ARTIFACTS', first), mock.patch.object(xfs, 'ROOT', checkout), \
             mock.patch.object(xfs, 'CAP', cap):
            xfs.budget()
            rejected(lambda: xfs.budget(cap), 'owned output budget')

        # Sparse files charge physical blocks, hardlinks charge their inode once,
        # and links to files/directories outside owned roots never charge targets.
        links = checkout / 'link-controls'
        links.mkdir()
        sparse = links / 'sparse'
        with sparse.open('wb') as stream:
            stream.truncate(700 << 20)
        require(sparse.stat().st_size == 700 << 20, 'sparse fixture logical size')
        require(owned_outputs.allocated_bytes(links) < cap, 'sparse logical bytes incorrectly charged')
        payload = links / 'payload'
        payload.write_bytes(bytes(65536))
        os.link(payload, links / 'same-inode')
        (links / 'outside-file').symlink_to(unrelated)
        (links / 'outside-directory').symlink_to(first, target_is_directory=True)
        (links / 'dangling').symlink_to(checkout / 'absent')
        expected = sum(path.lstat().st_blocks * 512 for path in (links, sparse, payload,
                       links / 'outside-file', links / 'outside-directory', links / 'dangling'))
        require(owned_outputs.allocated_bytes(links) == expected, 'link scope or inode accounting changed')
        os.link(payload, second / 'shared-inode')
        require(owned_outputs.allocated_bytes(links, second) == expected +
                owned_outputs.allocated_bytes(second) - payload.lstat().st_blocks * 512,
                'hardlink across explicit roots double charged')
        environment_before = dict(os.environ)
        environment = owned_outputs.temporary_environment(first)
        require(dict(os.environ) == environment_before, 'child temporary environment changed parent')
        require(all(environment[name] == str(first / 'tmp') for name in ('TMPDIR', 'TMP', 'TEMP')),
                'temporary files not routed into owned root')
        (first / 'tmp' / 'retained-temp').write_bytes(bytes(cap))
        require(owned_outputs.allocated_bytes(first) > cap, 'owned temporary growth escaped accounting')
        (second / 'tmp').symlink_to(first / 'tmp', target_is_directory=True)
        rejected(lambda: owned_outputs.temporary_environment(second), 'must not be a symlink')

        # Archive bytes and originals coexist in the same budget. Stop before
        # cleanup on overflow; cleanup failure retains the verified archive.
        def compact_fixture(label):
            artifacts = checkout / label
            directory = artifacts / 'batch-000'
            directory.mkdir(parents=True)
            (directory / 'original').write_bytes(b'original bytes\n' * 128)
            runner = object.__new__(transport.PackageRunner)
            runner.artifacts, runner.cap, runner.peak = artifacts, 64 << 20, 0
            return runner, directory

        runner, directory = compact_fixture('archive-overflow')
        archive = directory.with_suffix('.tar.xz')
        real_budget = runner.budget
        def reject_archive(reserve=0):
            if archive.exists():
                runner.cap = owned_outputs.allocated_bytes(runner.artifacts) - 1
            return real_budget(reserve)
        runner.budget = reject_archive
        rejected(lambda: runner.compact(directory), 'owned-output')
        require((directory / 'original').is_file() and archive.is_file(), 'overflow discarded original or archive')
        runner, directory = compact_fixture('cleanup-failure')
        archive = directory.with_suffix('.tar.xz')
        with mock.patch.object(Path, 'unlink', side_effect=RuntimeError('injected cleanup failure')):
            rejected(lambda: runner.compact(directory), 'injected cleanup failure')
        require((directory / 'original').is_file() and archive.is_file(), 'cleanup failure lost retained bytes')
        require(archive.with_suffix('.verified.json').is_file(), 'cleanup started without verified archive')
        require(owned_outputs.allocated_bytes(runner.artifacts) > owned_outputs.allocated_bytes(directory),
                'archive/receipt not charged with originals')
        terminal = checkout / 'terminal-receipt'
        terminal.mkdir()
        receipt = terminal / 'manifest.json'
        terminal_cap = owned_outputs.allocated_bytes(terminal) + 4096
        def terminal_guard():
            require(owned_outputs.allocated_bytes(terminal) <= terminal_cap, 'terminal owned-output overflow')
        report = dict(status='passed', detail='receipt growth' * 4096)
        terminal_guard()
        rejected(lambda: owned_outputs.write_checked_receipt(receipt, report, terminal_guard),
                 'terminal owned-output overflow')
        require(json.loads(receipt.read_text())['status'] == 'failed', 'terminal overflow left passed receipt')
        try:
            try:
                raise RuntimeError('original primary failure')
            finally:
                owned_outputs.write_checked_receipt(receipt, dict(status='failed', detail='x' * 65536),
                                                   terminal_guard)
        except RuntimeError as error:
            require(str(error) == 'original primary failure', 'receipt budget masked primary failure')
        else:
            raise RuntimeError('primary failure suppressed')
        require(hashlib.sha256(unrelated.read_bytes()).hexdigest() == before, 'unrelated history changed')
    return len(CONSUMERS) + 1



def host_tool_checks(out):
    # All subprocess calls below are mocked. These controls never execute tools.
    sys.path.insert(0, str(ROOT / 'scripts'))
    import package_native_runner as transport
    serial = 0
    def fixture():
        nonlocal serial
        directory = out / ('host-scope-' + str(serial)); serial += 1
        directory.mkdir()
        compiler, library, oracle, native = (directory / name for name in ('compiler', 'library', 'oracle', 'native'))
        hosts = {name:directory/name for name in ('as', 'ld', 'nm', 'readelf', 'python')}
        for path in (compiler, library, oracle, native, *hosts.values()): path.write_bytes(b'original bytes\n')
        with mock.patch.object(transport.shutil, 'which', side_effect=lambda name:str(hosts[name])), \
             mock.patch.object(transport.sys, 'executable', str(hosts['python'])):
            runner = transport.PackageRunner(compiler, directory, 256 << 20, root=out,
                prefix='', shared=lambda:'', validate=lambda *args:(), function_prefix='unused', sentinel=b'keep')
        runner.budget = mock.Mock(return_value=0)
        runner.measure = mock.Mock(return_value=(0, 1 << 30))
        runner.pins = {p:transport.sha(p) for p in (compiler, library, oracle, *hosts.values())}
        return runner, hosts, library, oracle, native
    def mutate(path):
        stat = path.stat(); path.write_bytes(b'changed! bytes\n')
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    def run(*args, **kwargs): return SimpleNamespace(returncode=0)
    def finish(runner, report=None):
        report = {'status':'passed'} if report is None else report
        errors = transport.finalize_report(runner, report, runner.compiler, runner.artifacts)
        return errors, report

    real_sha, calls = transport.sha, Counter()
    def counted(path):
        calls[Path(path)] += 1
        return real_sha(path)
    with mock.patch.object(transport, 'sha', side_effect=counted), mock.patch.object(transport.subprocess, 'run', side_effect=run):
        runner, hosts, library, oracle, native = fixture()
        for number, executable in enumerate((hosts['as'], hosts['python'], runner.compiler, native)):
            runner.command([executable], runner.artifacts, str(number))
            receipt = json.loads((runner.artifacts / (str(number)+'.command.json')).read_text())
            require(receipt['executable_hash_scope'] == ('suite-boundary' if executable in hosts.values() else 'command'), 'wrong executable hash scope')
        errors, report = finish(runner)
        require(not errors and report['status']=='passed', 'stable host suite rejected')
        require(all(calls[p]==2 for p in hosts.values()), 'host binaries rehashed between suite boundaries')
        require(calls[library]==10 and calls[oracle]==10 and calls[runner.compiler]>=10,
                'compiler/library/oracle command checks weakened')
        require(calls[native]==1, 'generated executable hash not command-scoped')

    for field in ('compiler', 'library', 'oracle'):
        for during in (False, True):
            runner, hosts, library, oracle, _ = fixture()
            path = {'compiler':runner.compiler, 'library':library, 'oracle':oracle}[field]
            def drift(*args, **kwargs): mutate(path); return run(*args, **kwargs)
            if not during: mutate(path)
            with mock.patch.object(transport.subprocess, 'run', side_effect=drift if during else run) as execute:
                rejected(lambda:runner.command([hosts['as']], runner.artifacts, 'source-drift'), 'input/tool changed')
                require(execute.call_count==int(during), 'source drift checked at wrong boundary')

    for name in ('as', 'ld', 'nm', 'readelf', 'python'):
        runner, hosts, _, _, _ = fixture(); mutate(hosts[name])
        with mock.patch.object(transport.subprocess, 'run', side_effect=run):
            runner.command([hosts['as']], runner.artifacts, 'host-drift')
        errors, report = finish(runner)
        require(report['status']=='failed' and any(str(hosts[name]) in error for error in errors), 'persistent host drift escaped finalization')

    for primary in (subprocess.TimeoutExpired(['mock'], 30), AssertionError('primary'), SystemExit(7), KeyboardInterrupt()):
        runner, hosts, _, _, _ = fixture(); caught = None
        def fail(*args, **kwargs):
            mutate(hosts['python']); raise primary
        try:
            try:
                with mock.patch.object(transport.subprocess, 'run', side_effect=fail):
                    runner.command([hosts['as']], runner.artifacts, 'failed-command')
            except BaseException as error:
                caught = error; raise
            finally:
                errors, report = finish(runner, {'status':'failed', 'error':'primary'})
                require(errors and report['error']=='primary', 'final drift masked primary failure')
        except BaseException as error:
            require(error is caught, 'primary exception replaced during finalization')
        require(caught is not None, 'injected failure passed')

    for deleted in (False, True):
        runner, hosts, _, _, _ = fixture()
        if deleted: hosts['python'].unlink()
        def denied(path):
            if Path(path)==hosts['python'] and not deleted: raise PermissionError('host hash denied')
            return real_sha(path)
        with mock.patch.object(transport, 'sha', side_effect=denied): errors, report = finish(runner)
        require(errors and report['status']=='failed', 'final host read failure passed')

    runner, hosts, _, _, _ = fixture(); runner.compiler = hosts['as']; mutate(hosts['as'])
    with mock.patch.object(transport.subprocess, 'run', side_effect=run) as execute:
        rejected(lambda:runner.command([hosts['as']], runner.artifacts, 'compiler-alias'), 'input/tool changed')
        require(not execute.called, 'host classification weakened compiler identity')
    runner, hosts, _, _, _ = fixture(); original = hosts['as'].read_bytes(); mutate(hosts['as'])
    with mock.patch.object(transport.subprocess, 'run', side_effect=run): runner.command([hosts['as']], runner.artifacts, 'transient')
    hosts['as'].write_bytes(original)
    require(not finish(runner)[0], 'suite-boundary policy unexpectedly detects restored transient host drift')
    return serial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    args = parser.parse_args()
    out = artifact_root(args.artifacts or ROOT / 'build' / ('native-cap-contracts-' + str(time.time_ns())))
    require(not out.exists(), 'fresh evidence directory required')
    require(shutil.disk_usage(ROOT).free >= 1 << 30, 'one GiB free floor before outputs')
    sources = [ROOT / name for name, _, _ in CONSUMERS] + [
        Path(__file__).resolve(), ROOT / 'scripts/package_native_runner.py', ROOT / 'scripts/owned_outputs.py']
    pins = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    out.mkdir(parents=True)
    owned_scope_consumers = owned_output_checks(out)
    host_scope_controls = host_tool_checks(out)
    rows = []
    for index, (name, minimum, native) in enumerate(CONSUMERS):
        spec = importlib.util.spec_from_file_location('cap_subject_' + str(index), ROOT / name)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        module.cap_self_test()
        accounting(module, native)
        for optimized in (False, True):
            # Invalid caps are tested both through configuration-only mode and
            # normal startup. Neither may touch outputs or read/run a compiler.
            cases = [(value, True, True) for value in (None, minimum, 512, 513, 1023, 1024)]
            cases += [(value, only, False) for value in (-1, 0, minimum - 1, 1025, 1 << 30)
                      for only in (False, True)]
            for value, only, valid in cases:
                folder = out / str(len(rows))
                folder.mkdir()
                requested = folder / 'requested'
                requested.mkdir()
                sentinel = requested / 'sentinel'
                sentinel.write_bytes(b'preserve configuration-only evidence\n')
                compiler = folder / 'not-a-compiler'
                compiler.write_bytes(b'never execute this input\n')
                command = [sys.executable, '-B'] + (['-O'] if optimized else []) + [str(ROOT / name)]
                command += ['--compiler', str(compiler)] if native else [str(compiler)]
                command += ['--compiler-sha256', '0' * 64]
                command += ['--output' if native else '--artifact-root', str(requested)]
                if value is not None:
                    command += ['--candidate-cap-mib', str(value)]
                if only:
                    command += ['--check-cap-only']
                result = subprocess.run(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                        capture_output=True, timeout=20)
                (folder / 'stdout').write_bytes(result.stdout)
                (folder / 'stderr').write_bytes(result.stderr)
                row = dict(consumer=name, optimized=optimized, cap_mib=value,
                           configuration_only=only, expected_valid=valid,
                           command=command, returncode=result.returncode)
                (folder / 'receipt.json').write_text(json.dumps(row, indent=2) + '\n')
                require(list(requested.iterdir()) == [sentinel]
                        and sentinel.read_bytes() == b'preserve configuration-only evidence\n',
                        'resource configuration changed requested output')
                if valid:
                    require(result.returncode == 0, 'valid cap rejected: ' + result.stderr.decode())
                    selected = minimum if value is None else value
                    observed = json.loads(result.stdout)
                    expected = dict(status='configuration-only', native_executed=False,
                                    candidate_cap_mib=selected, cap_bytes=selected << 20,
                                    focused_default_mib=minimum, maximum_cap_mib=1024)
                    require(observed == expected, 'configuration result changed')
                    require(observed['native_executed'] is False
                            and observed['status'] != 'passed'
                            and not set(observed) & {'cases', 'compiler_sha256', 'source_pins'},
                            'configuration-only result resembles native acceptance')
                else:
                    require(result.returncode != 0 and b'candidate cap' in result.stderr,
                            'invalid cap was not rejected before compiler/output processing')
                rows.append(row)
                require(sum(p.stat().st_blocks * 512 for p in out.rglob('*') if p.is_file()) < 4 << 20,
                        'configuration evidence exceeds four MiB')
                require(shutil.disk_usage(out).free >= 1 << 30, 'one GiB free floor')
    require(pins == {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
            'configuration sources changed during checks')
    report = dict(status='configuration-contracts-verified', native_executed=False,
                  cli_cases=len(rows), host_scope_controls=host_scope_controls, consumers=len(CONSUMERS), optimization_modes=[0, 1],
                  owned_scope_consumers=owned_scope_consumers,
                  accounting='mocked boundaries and real owned-root/link/sparse/overflow/archive/cleanup controls',
                  configuration_source_pins=pins, cases=rows)
    (out / 'configuration-results.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'CONFIGURATION CONTRACTS VERIFIED: {len(rows)} real entrypoint cases; no native acceptance claimed')


if __name__ == '__main__':
    main()
