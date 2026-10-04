#!/usr/bin/env python3
"""M022 exact-source replay of the existing 166 emulator modes.

No project implementation or historical receipt is edited. Shell xtrace is added
only to capture real QEMU exit codes/arguments; original validators are unchanged.
The preflight command is read-only with respect to project images. The run command
requires an explicit parent image-ownership release acknowledgement.
"""
from pathlib import Path
import argparse
import collections
import datetime
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import traceback

BASE = Path('/workspace/scratch/48c5de6446f8')
ROOT = BASE / 'aurora'
OUT = BASE / 'aurora-m022-kernel-receipts'
PIN = BASE / 'aurora-m022-kernel-compiler-frozen'
COMPILER_SHA = 'e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e'
OLD = BASE / 'aurora-m019-kernel-receipts'
OLD_COMPILER = '/tmp/aurora-resource-main-compiler-frozen'
HISTORICAL_PINS = {
    BASE / 'aurora-m019-final-gates.py': '890aef654d8f4af2fd47bf0bb8898b64390723d9e1bd5aa38c6fc9567c7b342b',
    OLD / 'results.json': 'cc459c9bc6c9e3aa04627d0c9eb3484f602a732c903998e097d12361b20c06ca',
    OLD / 'external-inputs.json': 'ef6336767f277b6cbf36af3eed36986300b9cf6a8eedd684a771bf40c662d651',
}
SETTINGS = dict(
    AURORAC=str(PIN),
    QEMU='/tmp/aurora-qemu/root/usr/bin/qemu-system-x86_64',
    QEMU_DATA='/tmp/aurora-qemu/firmware',
    LD_LIBRARY_PATH='/tmp/aurora-qemu/root/usr/lib/x86_64-linux-gnu',
    OVMF='/tmp/aurora-ovmf/root/usr/share/ovmf/OVMF.fd',
    AURORA_BAR_FIRMWARE='/tmp/aurora-clean-ovmf',
    AURORA_BAR_COVERAGE='/tmp/aurora-m014-bar-coverage.json',
    AURORA_IVRS_FIRMWARE='/tmp/aurora-clean-ovmf',
    AURORA_IVRS_COVERAGE='/tmp/aurora-m015-coverage.json',
    PYTHONDONTWRITEBYTECODE='1',
)
ENV = dict(os.environ, **SETTINGS)
FLOOR = 1024 ** 3
RUN_RESERVE = 512 * 1024 ** 2
GATE_RESERVE = 128 * 1024 ** 2
DIRECTORIES = (
    '/tmp/aurora-qemu/firmware',
    '/tmp/aurora-qemu/root/usr/lib/x86_64-linux-gnu',
    '/tmp/aurora-clean-ovmf/output',
    '/tmp/aurora-clean-ovmf/provenance',
    '/tmp/aurora-m015-amdvi-control',
    '/tmp/aurora-msix-trace-control/attempt3',
)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def record(path):
    path = Path(path)
    info = path.lstat()
    result = dict(sha256=sha(path), size=path.stat().st_size,
                  mode=oct(stat.S_IMODE(info.st_mode)),
                  kind='symlink' if path.is_symlink() else 'file')
    if path.is_symlink():
        result.update(target=os.readlink(path), resolved=str(path.resolve()),
                      resolved_mode=oct(stat.S_IMODE(path.stat().st_mode)))
    return result


def project_inputs():
    # Broaden M019's build/test scope to the parent's complete source/document
    # inventory. Historical evidence and generated/cache products stay excluded.
    files = [ROOT / p for p in ('Makefile', 'README.md', 'AGENTS.md', '.gitignore')]
    for directory in ('compiler', 'library', 'examples', 'kernel', 'scripts',
                      'tests', 'storage', 'fixtures', 'tools', 'docs', 'diagnostics'):
        files += [p for p in (ROOT / directory).rglob('*') if p.is_file()
                  and p.suffix != '.pyc'
                  and '__pycache__' not in p.parts and 'build' not in p.parts
                  and 'evidence' not in p.relative_to(ROOT).parts]
    return {str(p.relative_to(ROOT)): record(p) for p in sorted(set(files))}


def external_inputs():
    historical = json.loads((OLD / 'external-inputs.json').read_text())
    files = {Path(p) for p in historical if p != OLD_COMPILER}
    files.update(HISTORICAL_PINS)
    files.update((PIN, Path(__file__).resolve(), BASE / 'aurora-m022-parent/adoption.json',
                  BASE / 'aurora-m022-parent/source-before.json',
                  BASE / 'aurora-m022-parent/after-aggregate.json'))
    for directory in DIRECTORIES:
        files.update(p for p in Path(directory).rglob('*') if p.is_file())
    # Pin the actual host compiler implementation as well as the g++ driver.
    for name in ('cc1plus', 'collect2'):
        files.add(Path(subprocess.check_output(['g++', '-print-prog-name=' + name], text=True).strip()).resolve())
    for name in ('g++', 'as', 'ld', 'objcopy', 'objdump', 'nm', 'readelf', 'python3', 'bash', 'make', 'timeout'):
        files.add(Path(shutil.which(name)))
        files.add(Path(shutil.which(name)).resolve())
    return {str(p): record(p) for p in sorted(files)}


def inventory():
    historical = json.loads((OLD / 'results.json').read_text())
    modes = [(x['family'], x['mode']) for x in historical['modes']]
    if len(modes) != 166 or len(set(modes)) != 166:
        raise RuntimeError('Historical inventory is not 166 unique modes')
    if collections.Counter(f for f, _ in modes) != dict(bios=37, uefi=111, bar=7, ivrs=11):
        raise RuntimeError('Historical mode family counts changed')
    if any(x['exit_code'] != 0 for x in historical['modes']):
        raise RuntimeError('Historical mode inventory includes failed records')
    m016 = json.loads((BASE / 'aurora-m016-kernel-receipts/results.json').read_text())
    expected = [(x['family'], x['mode']) for x in m016['modes']] + [
        ('uefi', 'runtime-table-' + m) for m in ('readback', 'reject', 'exhaust', 'quarantine')]
    if modes != expected:
        raise RuntimeError('Inventory differs from original M019 runner composition')
    return modes


def disk_check(reserve):
    free = shutil.disk_usage(BASE).free
    if free < FLOOR + reserve:
        raise RuntimeError(f'Disk floor protection: {free} bytes free; need {FLOOR + reserve}')
    return dict(free_bytes=free, floor_bytes=FLOOR, reserved_growth_bytes=reserve)


def preflight():
    for path, expected in HISTORICAL_PINS.items():
        if sha(path) != expected:
            raise RuntimeError(f'Historical runner/receipt changed: {path}')
    historical = json.loads((OLD / 'external-inputs.json').read_text())
    for path, expected in historical.items():
        if path != OLD_COMPILER and sha(path) != expected:
            raise RuntimeError(f'Historical external pin changed: {path}')
    if sha(ROOT / 'build/aurorac') != COMPILER_SHA:
        raise RuntimeError('Adopted project compiler does not match M022 release pin')
    parent_inputs = json.loads((BASE / 'aurora-m022-parent/source-before.json').read_text())
    current_inputs = {name: item['sha256'] for name, item in project_inputs().items()}
    if parent_inputs != current_inputs:
        raise RuntimeError('Project source inventory differs from parent aggregate manifest')
    if PIN.exists() and (sha(PIN) != COMPILER_SHA or stat.S_IMODE(PIN.stat().st_mode) != 0o555):
        raise RuntimeError('Existing frozen M022 compiler differs or is writable')
    # These validators only load existing historical coverage; no control rerun.
    coverage_results = {}
    for family in ('bar', 'ivrs'):
        spec = importlib.util.spec_from_file_location(f'm022_{family}_trace', ROOT / f'tests/kernel-uefi-{family}-trace.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        coverage = module.load_coverage(SETTINGS[f'AURORA_{family.upper()}_COVERAGE'])
        module.validate_coverage(coverage)
        coverage_results[family] = 'Original coverage validators passed on existing controls'
    historical_bytes = sum(p.stat().st_size for p in OLD.rglob('*') if p.is_file())
    return dict(time_utc=now(), disk=disk_check(RUN_RESERVE), historical_receipt_bytes=historical_bytes,
                mode_count=len(inventory()), project_input_count=len(current_inputs),
                historical_external_pins_matched=len(historical)-1,
                coverage=coverage_results, compiler_sha256=COMPILER_SHA,
                original_compiler_binding_replaced=OLD_COMPILER,
                binding_note='Only the new runner selects the M022 compiler. No fixture pin or validator changed.',
                expected_runtime_note='M019 observed approximately 18 minutes; current runtime may differ.')


def command_for(family, mode, out):
    if family in ('bar', 'ivrs'):
        return ['python3', f'scripts/kernel-uefi-{family}-run.py', mode, '--output', str(out / family / mode)]
    script = './scripts/kernel-smoke.sh' if family == 'bios' else './scripts/kernel-uefi-smoke.sh'
    return ['bash', '-x', script, mode]


def run_gate(family, mode, destination):
    disk = disk_check(GATE_RESERVE)
    if sha(PIN) != COMPILER_SHA or stat.S_IMODE(PIN.stat().st_mode) != 0o555:
        raise RuntimeError('Frozen compiler changed before gate')
    command = command_for(family, mode, destination)
    dest = destination / family
    dest.mkdir(parents=True, exist_ok=True)
    label = mode.lstrip('-')
    log = dest / (label + '.command.log')
    started = now()
    with log.open('w') as stream:
        result = subprocess.run(command, cwd=ROOT, env=ENV, stdout=stream, stderr=subprocess.STDOUT)
    (dest / (label + '.command.status')).write_text(str(result.returncode) + '\n')
    text = log.read_text()
    if family in ('bar', 'ivrs'):
        status_path = dest / mode / 'status'
        qemu_status = int(status_path.read_text()) if status_path.exists() else None
    else:
        statuses = re.findall(r'^\+ status=(-?\d+)$', text, flags=re.MULTILINE)
        qemu_status = int(statuses[0]) if len(statuses) == 1 else None
        base = (ROOT / 'build' / ('kernel-serial' if mode == 'normal' else 'kernel-' + label)) if family == 'bios' else ROOT / 'build/uefi' / mode
        for suffix in ('.log', '.metadata.json'):
            source = base.with_name(base.name + suffix)
            if source.exists():
                shutil.copy2(source, dest / (label + suffix))
    if mode.startswith('runtime-table-'):
        stack_source = ROOT / 'build/uefi/table-stack' / mode
        if stack_source.is_dir():
            shutil.copytree(stack_source, dest / (mode + '-stack'))
        elif result.returncode == 0:
            raise RuntimeError('Successful table gate omitted actual stack receipts')
    files = {str(p.relative_to(destination)): record(p) for p in sorted(dest.rglob('*'))
             if p.is_file() and (p.name.startswith(label + '.') or mode in p.parts or mode + '-stack' in p.parts)}
    return dict(family=family, mode=mode, started_utc=started, completed_utc=now(),
                command=command, exit_code=result.returncode, qemu_exit_code=qemu_status,
                result='PASS' if result.returncode == 0 else 'FAIL', files=files, disk=disk)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--parent-released-images', action='store_true')
    args = parser.parse_args()
    os.chdir(ROOT)
    sys.dont_write_bytecode = True
    check = preflight()
    if args.preflight:
        print(json.dumps(check, indent=2))
        return 0
    if not args.parent_released_images:
        parser.error('Run only after parent explicitly releases shared images')
    OUT.mkdir(exist_ok=False)
    write(OUT / 'preflight.json', check)
    if not PIN.exists():
        shutil.copyfile(ROOT / 'build/aurorac', PIN)
        PIN.chmod(0o555)
    if sha(PIN) != COMPILER_SHA:
        raise RuntimeError('Frozen compiler copy identity mismatch')
    shutil.copy2(__file__, OUT / 'run-gates.py')
    write(OUT / 'compiler-copy.json', dict(source=str(ROOT / 'build/aurorac'), copy=str(PIN), record=record(PIN)))
    modes = inventory()
    commands = [command_for(family, mode, OUT) for family, mode in modes]
    started = now()
    before = project_inputs()
    external_before = external_inputs()
    write(OUT / 'source-inputs.json', before)
    write(OUT / 'external-inputs.json', external_before)
    write(OUT / 'commands.json', dict(cwd=str(ROOT), started_utc=started,
          source_manifest_timing='Captured before first build/gate; content, file modes and path sets rechecked at completion.',
          capture_note='bash -x adds command/exit tracing only. Original shell/Python assertions remain unchanged.', commands=commands))
    versions = {name: subprocess.check_output([exe, '--version'], env=ENV, text=True).splitlines()[0]
                for name, exe in [('g++', 'g++'), ('as', 'as'), ('ld', 'ld'), ('python', 'python3'), ('qemu', SETTINGS['QEMU'])]}
    write(OUT / 'tools.json', dict(versions=versions, environment=SETTINGS,
          inherited_environment_note='No inherited AURORA, UEFI, KERNEL, CXX, CC, SANITIZE, QEMU, OVMF or LD override was present during preparation.'))
    results = []
    errors = []
    restoration = []
    write(OUT / 'results.json', dict(started_utc=started, state='RUNNING', distinct_modes=0, modes=[]))
    try:
        for family, mode in modes:
            result = run_gate(family, mode, OUT)
            results.append(result)
            write(OUT / 'results.json', dict(started_utc=started, updated_utc=now(), state='RUNNING',
                  distinct_modes=len(results), compiler_sha256=COMPILER_SHA, modes=results))
            print(f'{len(results)}/166 {family} {mode}: {result["exit_code"]} (QEMU {result["qemu_exit_code"]})', flush=True)
            if result['exit_code'] != 0 or result['qemu_exit_code'] is None:
                raise RuntimeError(f'Gate failed or lacked raw QEMU status: {family} {mode}; exit={result["exit_code"]}')
        normal_payload = ROOT / 'build/uefi/payload.bin'
        if b'AURORA_TABLE' in normal_payload.read_bytes():
            raise RuntimeError('Normal payload retained table test markers')
        symbols = subprocess.check_output(['nm', '-C', str(ROOT / 'build/uefi/payload.elf')], text=True)
        if any(name in symbols for name in ('DormantTables', 'DormantTableTestAccess', 'table_readback')):
            raise RuntimeError('Normal image retained inspector/table implementation')
    except BaseException as error:
        errors.append(dict(error=str(error), traceback=traceback.format_exc(), time_utc=now()))
        print('FAIL: ' + str(error), flush=True)
    finally:
        # Explicit successful normal boots establish restoration even after failure.
        for family in ('bios', 'uefi'):
            try:
                result = run_gate(family, 'normal', OUT / 'restoration')
                restoration.append(result)
                if result['exit_code'] != 0 or result['qemu_exit_code'] is None:
                    raise RuntimeError(f'Normal {family} restoration failed')
            except BaseException as error:
                errors.append(dict(error=str(error), traceback=traceback.format_exc(), time_utc=now()))
        after = project_inputs()
        external_after = external_inputs()
        write(OUT / 'source-inputs-after.json', after)
        write(OUT / 'external-inputs-after.json', external_after)
        if before != after:
            errors.append(dict(error='Project input bytes, modes or inventory changed during gates'))
        if external_before != external_after:
            errors.append(dict(error='External input bytes, modes or inventory changed during gates'))
        payload = ROOT / 'build/uefi/payload.bin'
        symbols = subprocess.check_output(['nm', '-C', str(ROOT / 'build/uefi/payload.elf')], text=True)
        absent = b'AURORA_TABLE' not in payload.read_bytes() and not any(
            name in symbols for name in ('DormantTables', 'DormantTableTestAccess', 'table_readback'))
        if not absent:
            errors.append(dict(error='Final normal payload retains table test markers or inspector symbols'))
        restored = len(restoration) == 2 and all(r['exit_code'] == 0 and r['qemu_exit_code'] is not None for r in restoration) and absent
        normal_files = [ROOT / p for p in ('build/aurora.img', 'build/kernel.elf', 'build/kernel.bin',
                        'build/uefi/payload.bin', 'build/uefi/payload.elf', 'build/uefi/esp/EFI/BOOT/BOOTX64.EFI')]
        write(OUT / 'normal-restoration.json', dict(normal_images_restored=restored,
              table_test_symbols_absent=absent, table_markers_absent=absent,
              executions=restoration, files={str(p): record(p) for p in normal_files}))
        passed = len(results) == 166 and not errors and restored and all(r['exit_code'] == 0 for r in results)
        write(OUT / 'results.json', dict(started_utc=started, completed_utc=now(),
              state='PASS' if passed else 'FAIL', distinct_modes=len(results), expected_distinct_modes=166,
              bios_distinct=sum(r['family'] == 'bios' for r in results),
              uefi_distinct=sum(r['family'] != 'bios' for r in results), compiler_sha256=COMPILER_SHA,
              source_inputs_unchanged_at_completion=before == after, source_input_count=len(before),
              source_input_manifest_sha256=sha(OUT / 'source-inputs.json'),
              external_inputs_unchanged_at_completion=external_before == external_after,
              external_input_count=len(external_before), normal_images_restored=restored,
              normal_restoration_extra_executions=len(restoration), errors=errors, modes=results))
        write(OUT / 'errors.json', errors)
        write(OUT / 'disk-final.json', dict(free_bytes=shutil.disk_usage(BASE).free, floor_bytes=FLOOR))
        (OUT / 'README.txt').write_text(
            'M022 exact-source replay of the existing 166-mode inventory: 37 BIOS and 129 UEFI-family modes. '
            'Original mode semantics/assertions, packaged QEMU/OVMF and clean firmware, real historical trace controls are retained. '
            'Compiler binding alone selects the new copied read-only M022 compiler. No project validator was changed. '
            'Two additional normal boots are restoration checks, not new distinct modes. '
            'Source/test/build inputs and external tools/firmware/control bytes, file modes and inventories are captured before and after. '
            'The complete parent source/document inventory is included; historical evidence and generated products are excluded. '
            'SHA256.json and artifact-modes.json seal receipt contents and permissions. '
            'The AMD control preserves its failed broader whole-run criterion; only the reviewed bounded CTRL producer witness supplies coverage. '
            'No active DMA, new QEMU setup, installation, hardware or remote publication occurred. '
            'Parent aggregate and independent review remain separate acceptance stages.\n')
        write(OUT / 'artifact-modes.json', {str(p.relative_to(OUT)): oct(stat.S_IMODE(p.lstat().st_mode))
              for p in sorted(OUT.rglob('*')) if p.is_file() and p.name not in ('artifact-modes.json', 'SHA256.json')})
        write(OUT / 'SHA256.json', {str(p.relative_to(OUT)): sha(p) for p in sorted(OUT.rglob('*'))
              if p.is_file() and p.name != 'SHA256.json'})
        print(('PASS full166' if passed else 'FAIL incomplete/full166') + '; receipts ' + str(OUT), flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
