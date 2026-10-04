#!/usr/bin/env python3
"""Bind a BAR run receipt to exact files, launch arguments and linked fault sites.

Receipts establish artifact identity, not source reproducibility. A compiler hash
alone is not a source manifest, and recorded argv is not a signed execution log.
The serial and hardware trace validators remain separately mandatory.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import re
import sys


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


image = module('bar_image', 'kernel-uefi-image.py')
trace = module('bar_trace', 'kernel-uefi-bar-trace.py')
bar = trace.bar
need = bar.need
PINS = {
    'qemu': 'd3c1a558ad220e77a4412048c8d96b44f8c2b41c7ad2a4ecfe522a4b122fe067',
    'events': '9f115add677f04405f67f3570311e07b0f3d49b7533ab15ee87ec7ff37696a41',
    'clean_code': '24b30416142749dd60ac241fe755df6232fc5b10663a8b799501659b796d0268',
    'clean_vars': '5d2ac383371b408398accee7ec27c8c09ea5b74a0de0ceea6513388b15be5d1e',
    'clean_patch': '2a6e8f018d16fc1b4c0304bf7d1f3b56ca4962ca8ec204a19ff94b0e4790ad1f',
    'stock_code': '14954040cc754ade0c625ac3470ea46d4c14318b5b1396de4ef77090203d76db',
}
REVISION = 'fbe0805b2091393406952e84724188f8c1941837'
FILES = {'qemu', 'events', 'compiler', 'loader', 'payload', 'payload_elf', 'payload_metadata',
         'serial', 'trace', 'firmware_log', 'firmware_code', 'coverage'}
CLEAN_FILES = {'vars_initial', 'vars_after', 'vars_template', 'firmware_patch'}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def fields(value, empty=()):
    parts = value.split(',')
    result = {}
    for part in parts:
        need('=' in part, 'Unsupported comma option')
        key, item = part.split('=', 1)
        need(key and (item or key in empty) and key not in result, 'Empty/duplicate comma option')
        result[key] = item
    return result


def absolute(path, cwd):
    need(isinstance(path, str) and path and '\x00' not in path and ',' not in path, 'Invalid artifact path')
    value = Path(path)
    return str((value if value.is_absolute() else Path(cwd)/value).resolve())


def validate_arguments(receipt, paths):
    argv = receipt.get('argv')
    cwd = receipt.get('cwd')
    need(isinstance(cwd, str) and Path(cwd).is_absolute(), 'Missing absolute invocation cwd')
    need(isinstance(argv, list) and argv and all(isinstance(v, str) and v and '\x00' not in v for v in argv), 'Malformed invocation argv')
    need(absolute(argv[0], cwd) == paths['qemu'], 'Invoked QEMU differs from hashed binary')
    environment = receipt.get('environment')
    need(isinstance(environment, dict) and set(environment) <= {'LD_LIBRARY_PATH', 'LC_ALL', 'TZ'}
         and isinstance(environment.get('LD_LIBRARY_PATH'), str) and environment['LD_LIBRARY_PATH'], 'Missing/unsafe environment overrides')
    values, flags = {}, []
    pairs = {'-L', '-machine', '-accel', '-cpu', '-smp', '-m', '-bios', '-drive', '-nic', '-display', '-serial',
             '-monitor', '-device', '-debugcon', '-global', '-trace', '-chardev'}
    i = 1
    while i < len(argv):
        option = argv[i]
        if option in ('-no-reboot', '-no-shutdown'):
            need(option not in flags, 'Repeated invocation flag'); flags.append(option); i += 1
        else:
            need(option in pairs and i+1 < len(argv), 'Unreviewed/incomplete QEMU option: ' + option)
            values.setdefault(option, []).append(argv[i+1]); i += 2
    for option in pairs - {'-drive', '-device'}:
        need(len(values.get(option, [])) <= 1, 'Repeated singleton QEMU option')
    required = {'-machine': 'q35', '-accel': 'tcg', '-cpu': 'qemu64', '-smp': '1', '-m': '128M',
                '-nic': 'none', '-display': 'none', '-monitor': 'none'}
    need(all(values.get(k) == [v] for k, v in required.items()) and '-no-reboot' in flags, 'Wrong pinned q35 CPU/memory/runtime profile')
    need(values.get('-L') and Path(absolute(values['-L'][0], cwd)).is_absolute(), 'Missing firmware search directory')
    need(values.get('-serial'), 'Missing serial destination')
    if values['-serial'] == ['stdio']:
        stdio = receipt.get('stdio')
        need(isinstance(stdio, dict) and set(stdio) == {'stdout', 'stderr'} and stdio['stderr'] == 'stdout'
             and absolute(stdio['stdout'], cwd) == paths['serial'], 'Unbound serial stdout/stderr redirection')
    else:
        need(values['-serial'][0].startswith('file:') and absolute(values['-serial'][0][5:], cwd) == paths['serial'],
             'Unbound serial output destination')
    separate_debug = '-chardev' in values
    if separate_debug:
        need('-debugcon' not in values and '-global' not in values and values['-chardev'][0].startswith('file,'),
             'Ambiguous firmware debug transport')
        chardev = fields(values['-chardev'][0].split(',', 1)[1])
        need(set(chardev) == {'id', 'path'} and chardev['id'] == 'firmware'
             and absolute(chardev['path'], cwd) == paths['firmware_log'], 'Unbound firmware chardev')
    else:
        need(values.get('-global') == ['isa-debugcon.iobase=0x402'] and values.get('-debugcon')
             and values['-debugcon'][0].startswith('file:') and absolute(values['-debugcon'][0][5:], cwd) == paths['firmware_log'],
             'Unbound firmware debug output')
    need(values.get('-trace'), 'Tracing was not enabled at process startup')
    traced = fields(values['-trace'][0])
    need(set(traced) == {'events', 'file'} and absolute(traced['events'], cwd) == paths['events']
         and absolute(traced['file'], cwd) == paths['trace'], 'Unbound trace destination/event inventory')
    devices = values.get('-device', [])
    need(len(devices) == (3 if separate_debug else 2), 'Additional/missing devices in namespace-free fixture')
    debug_devices = [v for v in devices if v.startswith('isa-debugcon,')]
    need(debug_devices == (['isa-debugcon,iobase=0x402,chardev=firmware'] if separate_debug else []), 'Wrong debugcon port/device')
    nvme = [v for v in devices if v.startswith('nvme,')]
    debug_exit = [v for v in devices if v.startswith('isa-debug-exit,')]
    need(len(nvme) == len(debug_exit) == 1, 'Wrong device models')
    nvme = fields(nvme[0].split(',', 1)[1], empty=('romfile',))
    need(set(nvme) <= {'id', 'serial', 'bus', 'addr', 'romfile'} and nvme.get('serial') and nvme.get('bus') == 'pcie.0'
         and nvme.get('addr') in ('02.0', '2.0') and nvme.get('romfile', '') == '', 'Unpinned NVMe location/options or namespace backend')
    exit_fields = fields(debug_exit[0].split(',', 1)[1])
    need(exit_fields == {'iobase': '0xf4', 'iosize': '0x04'} or exit_fields == {'iobase': '0xf4', 'iosize': '4'}, 'Unbound debug-exit port')
    boot_root = absolute(receipt.get('boot_root'), cwd)
    need(paths['loader'] == str(Path(boot_root)/'EFI/BOOT/BOOTX64.EFI'), 'Loader is not the launched FAT boot file')
    drives = [fields(value) for value in values.get('-drive', [])]
    fat = [d for d in drives if d.get('file', '').startswith('fat:')]
    need(len(fat) == 1 and set(fat[0]) == {'format', 'file', 'snapshot'} and fat[0]['format'] == 'raw'
         and fat[0]['snapshot'] == 'on' and fat[0]['file'].startswith('fat:ro:')
         and absolute(fat[0]['file'][7:], cwd) == boot_root, 'Guest boot FAT is unbound/writable')
    clean = receipt['firmware_profile'] == 'clean'
    if clean:
        need('-bios' not in values and len(drives) == 3, 'Clean firmware must use explicit CODE and VARS pflash')
        pflash = [d for d in drives if d.get('if') == 'pflash']
        need(len(pflash) == 2, 'Missing/extra pflash drives')
        if any('unit' in device for device in pflash):
            need(pflash[0].pop('unit', None) == '0' and pflash[1].pop('unit', None) == '1', 'Wrong pflash CODE/VARS units')
        need(set(pflash[0]) == {'if', 'format', 'readonly', 'file'}
             and pflash[0]['format'] == 'raw' and pflash[0]['readonly'] == 'on'
             and absolute(pflash[0]['file'], cwd) == paths['firmware_code'], 'Unbound/writable clean firmware CODE')
        need(set(pflash[1]) in ({'if', 'format', 'file'}, {'if', 'format', 'readonly', 'file'})
             and pflash[1]['format'] == 'raw' and pflash[1].get('readonly', 'off') == 'off'
             and absolute(pflash[1]['file'], cwd) == paths['vars_after'], 'Unbound clean runtime VARS file')
        need(len({paths[name] for name in ('vars_initial', 'vars_after', 'vars_template')}) == 3, 'Pristine/template/runtime VARS identities overlap')
    else:
        need(len(drives) == 1 and values.get('-bios') and absolute(values['-bios'][0], cwd) == paths['firmware_code'], 'Unbound stock firmware')
    return boot_root


def elf_symbols(data):
    u = lambda at, width: image.u(data, at, width)
    need(data[:6] == b'\x7fELF\x02\x01' and u(18, 2) == 62, 'Wrong linked payload architecture')
    shoff, entsize, count = u(40, 8), u(58, 2), u(60, 2)
    need(entsize == 64 and 0 < count < 256 and shoff+count*64 <= len(data), 'Malformed linked section table')
    result = {}
    for index in range(count):
        at = shoff+index*64
        if u(at+4, 4) != 2: continue
        offset, size, link, stride = u(at+24, 8), u(at+32, 8), u(at+40, 4), u(at+56, 8)
        need(stride == 24 and size % stride == 0 and offset+size <= len(data) and link < count, 'Malformed symbol table')
        strings = shoff+link*64
        need(u(strings+4, 4) == 3, 'Symbol names do not reference a string table')
        start, length = u(strings+24, 8), u(strings+32, 8)
        need(start+length <= len(data), 'Truncated symbol strings')
        names = data[start:start+length]
        for symbol in range(offset, offset+size, 24):
            name_offset = u(symbol, 4)
            need(name_offset < len(names), 'Invalid symbol name offset')
            end = names.find(b'\0', name_offset)
            need(end >= 0, 'Unterminated symbol name')
            name = names[name_offset:end].decode('ascii')
            if name in ('__payload_text_end', 'uefi_bar_write_probe', 'uefi_bar_revoked_probe'):
                need(name not in result and u(symbol+6, 2) != 0, 'Duplicate/undefined probe symbol')
                result[name] = u(symbol+8, 8)
    return result


def validate_payload(loader, binary, elf, metadata, mode):
    image.pe_validate(loader, binary)
    image.elf_validate(elf, binary)
    symbols = elf_symbols(elf)
    need(isinstance(metadata, dict) and set(metadata) == {'offset', 'bytes', 'fault_offsets'}
         and metadata['offset'] == 0x22000 and metadata['bytes'] == symbols.get('__payload_text_end')
         and type(metadata['bytes']) is int and 0 < metadata['bytes'] <= len(binary), 'Payload metadata differs from linked code extent')
    expected = {}
    sites = {'bar-write': ('uefi_bar_write_probe', bytes.fromhex('c70000000000')),
             'bar-revoked': ('uefi_bar_revoked_probe', bytes.fromhex('8b00'))}
    for candidate, (name, opcode) in sites.items():
        if candidate == mode:
            at = symbols.get(name)
            need(type(at) is int and 0 < at and at+len(opcode) <= metadata['bytes']
                 and binary[at:at+len(opcode)] == opcode, 'Fault site is not exact linked MMIO probe instruction')
            expected[candidate] = at
        else:
            need(name not in symbols, 'Foreign fault probe present in this build')
    need(metadata['fault_offsets'] == expected, 'Fault metadata does not match linked symbol')
    return metadata


def validate_receipt(receipt, contents):
    """Pure receipt/hash checks; contents maps named roles to exact file bytes."""
    need(receipt.get('schema') == 'aurora-bar-run-v1' and receipt.get('mode') in bar.MODES, 'Wrong run receipt schema/mode')
    mode = receipt['mode']; clean = mode in bar.CLEAN
    need(receipt.get('status') == (33 if mode == 'bar-read' else 35), 'Recorded process status disagrees with mode')
    need(receipt.get('firmware_profile') == ('clean' if clean else 'stock'), 'Wrong firmware profile for mode')
    required = FILES | (CLEAN_FILES if clean else set())
    files = receipt.get('files')
    need(isinstance(files, dict) and set(files) == required and set(contents) == required, 'Missing/extra run artifacts')
    paths = {}
    for role in required:
        record = files[role]
        need(isinstance(record, dict) and set(record) == {'path', 'sha256'} and re.fullmatch('[0-9a-f]{64}', record['sha256']), 'Malformed artifact record')
        need(isinstance(record['path'], str) and Path(record['path']).is_absolute(), 'Artifact paths must be absolute')
        paths[role] = absolute(record['path'], receipt['cwd'])
        need(isinstance(contents[role], bytes) and sha256(contents[role]) == record['sha256'], 'Artifact hash mismatch: ' + role)
        need(contents[role] or role == 'firmware_log', 'Empty artifact: ' + role)
    need(len(set(paths.values())) == len(paths), 'Artifact roles share a path')
    need(files['qemu']['sha256'] == PINS['qemu'] and files['events']['sha256'] == PINS['events'], 'Unreviewed QEMU binary/events')
    need(files['firmware_code']['sha256'] == PINS['clean_code' if clean else 'stock_code'], 'Unreviewed firmware CODE')
    if clean:
        need(receipt.get('firmware_source_revision') == REVISION and files['firmware_patch']['sha256'] == PINS['clean_patch'], 'Unreviewed clean firmware source/patch')
        need(files['vars_template']['sha256'] == files['vars_initial']['sha256'] == PINS['clean_vars'], 'Reused/non-pristine initial VARS')
    else:
        need('firmware_source_revision' not in receipt, 'Stock firmware mislabeled with clean source identity')
    boot_root = validate_arguments(receipt, paths)
    return paths, boot_root


def validate(path):
    path = Path(path)
    receipt = json.loads(path.read_text())
    need(isinstance(receipt, dict) and isinstance(receipt.get('files'), dict), 'Malformed run JSON')
    contents = {role: Path(record['path']).read_bytes() for role, record in receipt['files'].items()}
    paths, boot_root = validate_receipt(receipt, contents)
    metadata = json.loads(contents['payload_metadata'])
    validate_payload(contents['loader'], contents['payload'], contents['payload_elf'], metadata, receipt['mode'])
    # Check the only bootable file and reject unexpected writable guest content.
    boot_files = {str(p.resolve()) for p in Path(boot_root).rglob('*') if p.is_file()}
    need(boot_files == {paths['loader']}, 'Unrecorded files in launched FAT tree')
    coverage = trace.load_coverage(paths['coverage'])
    need(coverage['events'].encode() == contents['events'], 'Coverage/launch event inventory differs')
    trace.validate_coverage(coverage)
    bar.validate(receipt['status'], contents['serial'].decode(), receipt['mode'], metadata)
    return {'mode': receipt['mode'], 'qemu_sha256': PINS['qemu'], 'compiler_sha256': receipt['files']['compiler']['sha256'],
            'firmware_profile': receipt['firmware_profile'], 'payload_sha256': receipt['files']['payload']['sha256'],
            'source_manifest': 'not established by this receipt'}


def self_test():
    failures = 0
    for clean, stdio in ((False, False), (True, False), (False, True), (True, True)):
        roles = FILES | (CLEAN_FILES if clean else set())
        paths = {name: '/tmp/synthetic-bar/'+name for name in roles}
        paths['loader'] = '/tmp/synthetic-bar/esp/EFI/BOOT/BOOTX64.EFI'
        receipt = {'cwd': '/tmp/synthetic-bar', 'boot_root': '/tmp/synthetic-bar/esp',
                   'environment': {'LD_LIBRARY_PATH': '/tmp/synthetic-libraries'}, 'firmware_profile': 'clean' if clean else 'stock'}
        argv = [paths['qemu'], '-L', '/tmp/firmware', '-machine', 'q35', '-accel', 'tcg', '-cpu', 'qemu64', '-smp', '1', '-m', '128M',
                '-nic', 'none', '-display', 'none', '-monitor', 'none', '-no-reboot',
                '-device', 'nvme,serial=SYNTHETIC,bus=pcie.0,addr=02.0', '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04',
                '-serial', 'file:'+paths['serial'], '-debugcon', 'file:'+paths['firmware_log'], '-global', 'isa-debugcon.iobase=0x402',
                '-trace', 'events='+paths['events']+',file='+paths['trace'], '-drive', 'format=raw,file=fat:ro:/tmp/synthetic-bar/esp,snapshot=on']
        if clean:
            argv += ['-drive', 'if=pflash,format=raw,readonly=on,file='+paths['firmware_code'], '-drive', 'if=pflash,format=raw,file='+paths['vars_after']]
        else:
            argv += ['-bios', paths['firmware_code']]
        if stdio:
            debug_at = argv.index('-debugcon'); del argv[debug_at:debug_at+2]
            global_at = argv.index('-global'); del argv[global_at:global_at+2]
            argv[argv.index('-serial')+1] = 'stdio'
            argv += ['-chardev', 'file,id=firmware,path='+paths['firmware_log'], '-device', 'isa-debugcon,iobase=0x402,chardev=firmware']
            receipt['stdio'] = {'stdout': paths['serial'], 'stderr': 'stdout'}
            if clean:
                argv = [v.replace('if=pflash,format=raw,readonly=on,', 'if=pflash,format=raw,unit=0,readonly=on,')
                        .replace('if=pflash,format=raw,file=', 'if=pflash,format=raw,unit=1,file=') for v in argv]
        receipt['argv'] = argv
        validate_arguments(receipt, paths)
        cases = [dict(receipt, argv=argv+['-device', 'nvme-ns,drive=unsafe']),
                 dict(receipt, environment={'LD_LIBRARY_PATH': '/lib', 'LD_PRELOAD': 'unsafe'}),
                 dict(receipt, boot_root='/tmp/foreign')]
        if stdio:
            cases += [dict(receipt, stdio={'stdout': '/tmp/other', 'stderr': 'stdout'}),
                      dict(receipt, stdio={'stdout': paths['serial'], 'stderr': 'ignore'}), dict(receipt, stdio=None)]
        for index in range(len(argv)):
            cases.append(dict(receipt, argv=argv[:index]+argv[index+1:]))
        for old, new in (('q35', 'pc'), ('qemu64', 'host'), ('128M', '256M'), ('-no-reboot', '-daemonize'),
                         ('nvme,serial=SYNTHETIC,bus=pcie.0,addr=02.0', 'nvme,serial=SYNTHETIC,bus=pcie.0,addr=02.0,drive=unsafe')):
            cases.append(dict(receipt, argv=[new if item == old else item for item in argv]))
        for index, value in enumerate(argv):
            if 'fat:ro:' in value:
                mutated = argv[:]; mutated[index] = value.replace('fat:ro:', 'fat:rw:'); cases.append(dict(receipt, argv=mutated))
            if value.startswith('events='):
                mutated = argv[:]; mutated[index] = value+',enable=pci_nvme_mmio_read'; cases.append(dict(receipt, argv=mutated))
        for candidate in cases:
            try: validate_arguments(candidate, paths)
            except (ValueError, KeyError): failures += 1
            else: raise RuntimeError('Invalid launch provenance accepted')
    print(f'PASS: BAR provenance 4 synthetic launch profiles and {failures} adversarial cases; real artifact checks required separately')


if __name__ == '__main__':
    if sys.argv[1:] == ['--self-test']:
        self_test()
    else:
        try:
            result = validate(sys.argv[1])
        except (ValueError, KeyError, IndexError, TypeError, OSError) as error:
            sys.exit('FAIL: ' + str(error))
        print('PASS: strict BAR run provenance ' + json.dumps(result, sort_keys=True))
