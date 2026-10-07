#!/usr/bin/env python3
"""Check resource configuration through the real entrypoints, without native work."""
from pathlib import Path
import argparse
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
    with mock.patch.object(module, 'ROOT', fake_root), \
         mock.patch.object(module.shutil, 'disk_usage', return_value=SimpleNamespace(free=floor + reserve)):
        runner.budget(reserve)
        rejected(lambda: runner.budget(reserve + 1), 'whole-candidate')
    with mock.patch.object(module, 'ROOT', fake_root), \
         mock.patch.object(module.shutil, 'disk_usage', return_value=SimpleNamespace(free=floor + reserve - 1)):
        rejected(lambda: runner.budget(reserve), 'free floor')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path)
    args = parser.parse_args()
    out = artifact_root(args.artifacts or ROOT / 'build' / ('native-cap-contracts-' + str(time.time_ns())))
    require(not out.exists(), 'fresh evidence directory required')
    require(shutil.disk_usage(ROOT).free >= 1 << 30, 'one GiB free floor before outputs')
    sources = [ROOT / name for name, _, _ in CONSUMERS] + [Path(__file__).resolve()]
    pins = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    out.mkdir(parents=True)
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
                  cli_cases=len(rows), consumers=len(CONSUMERS), optimization_modes=[0, 1],
                  accounting='mocked cap/reserve/free-floor boundaries; no large allocation',
                  configuration_source_pins=pins, cases=rows)
    (out / 'configuration-results.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'CONFIGURATION CONTRACTS VERIFIED: {len(rows)} real entrypoint cases; no native acceptance claimed')


if __name__ == '__main__':
    main()
