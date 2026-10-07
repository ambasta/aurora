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
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
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
    if native:
        with mock.patch.object(module, 'allocated', return_value=cap - 1), \
             mock.patch.object(module.shutil, 'disk_usage', return_value=SimpleNamespace(free=floor)):
            module.guard(1024)
        with mock.patch.object(module, 'allocated', return_value=cap), \
             mock.patch.object(module.shutil, 'disk_usage', return_value=SimpleNamespace(free=floor)):
            rejected(lambda: module.guard(1024), 'allocation cap')
        with mock.patch.object(module, 'allocated', return_value=0), \
             mock.patch.object(module.shutil, 'disk_usage', return_value=SimpleNamespace(free=floor - 1)):
            rejected(lambda: module.guard(1024), 'free-space floor')
        return
    fake_root = SimpleNamespace(lstat=lambda: SimpleNamespace(st_blocks=(cap - reserve) // 512),
                                rglob=lambda _pattern: [])
    runner = object.__new__(module.Runner)
    runner.cap, runner.peak = cap, 0
    runner.root = fake_root
    with mock.patch.object(module, 'ROOT', fake_root), \
         mock.patch.object(module.shutil, 'disk_usage', return_value=SimpleNamespace(free=floor + reserve)):
        runner.budget(reserve)
        rejected(lambda: runner.budget(reserve + 1), 'whole-candidate')
    with mock.patch.object(module, 'ROOT', fake_root), \
         mock.patch.object(module.shutil, 'disk_usage', return_value=SimpleNamespace(free=floor + reserve - 1)):
        rejected(lambda: runner.budget(reserve), 'free floor')



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
        Path(__file__).resolve(), ROOT / 'scripts/package_native_runner.py']
    pins = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    out.mkdir(parents=True)
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
                  accounting='mocked cap/reserve/free-floor boundaries; no large allocation',
                  configuration_source_pins=pins, cases=rows)
    (out / 'configuration-results.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'CONFIGURATION CONTRACTS VERIFIED: {len(rows)} real entrypoint cases; no native acceptance claimed')


if __name__ == '__main__':
    main()
