#!/usr/bin/env python3
"""Bind IVRS receipts to exact launched artifacts and linked fault instructions.

The QEMU exception is a compile-selected diagnostic profile, not architectural
MMIO enablement or DMA isolation. Hash receipts establish artifact identity;
they do not establish a reproducible source manifest or signed execution log.
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


prior = module('ivrs_bar_provenance', 'kernel-uefi-bar-provenance.py')
ivrs = module('ivrs_smoke_provenance', 'kernel-uefi-ivrs-smoke.py')
need = ivrs.need
PINS = dict(prior.PINS)
REVISION = prior.REVISION
QEMU_SOURCE = '98f88efe8f07067667b8d9b1a5ce9551d34036c1'
IOMMU = 'amd-iommu,pt=off,intremap=off,device-iotlb=off,xtsup=off'
FILES = prior.FILES | prior.CLEAN_FILES
sha256 = prior.sha256
absolute = prior.absolute


def validate_arguments(receipt, paths):
    argv = receipt.get('argv')
    need(isinstance(argv, list) and all(isinstance(value, str) for value in argv), 'Missing IVRS invocation argv')
    candidate = dict(receipt); reduced = []; count = 0; at = 0
    while at < len(argv):
        if argv[at] == '-device' and at+1 < len(argv) and argv[at+1].split(',')[0] == 'amd-iommu':
            need(argv[at+1] == IOMMU, 'Unreviewed AMD-Vi options')
            count += 1; at += 2
        else:
            reduced.append(argv[at]); at += 1
    need(count == (0 if receipt.get('mode') == 'ivrs-missing' else 1), 'Missing/duplicate/unexpected IOMMU device')
    need(receipt.get('firmware_profile') == 'clean', 'IVRS profile requires clean pinned firmware')
    candidate['argv'] = reduced
    # The removed device is fully validated above. Every remaining argument is
    # checked by the unchanged M014 namespace-free, cold, single-CPU contract.
    return prior.validate_arguments(candidate, paths)


def elf_symbols(data):
    u = lambda at, width: prior.image.u(data, at, width)
    need(data[:6] == b'\x7fELF\x02\x01' and u(18, 2) == 62, 'Wrong IVRS payload architecture')
    shoff, entsize, count = u(40, 8), u(58, 2), u(60, 2)
    need(entsize == 64 and 0 < count < 256 and shoff+count*64 <= len(data), 'Malformed linked section table')
    names_wanted = {'__payload_text_end', 'uefi_ivrs_write_probe', 'uefi_ivrs_revoked_probe',
                    'uefi_bar_write_probe', 'uefi_bar_revoked_probe'}
    result = {}
    for index in range(count):
        at = shoff+index*64
        if u(at+4, 4) != 2: continue
        offset, size, link, stride = u(at+24, 8), u(at+32, 8), u(at+40, 4), u(at+56, 8)
        need(stride == 24 and size % stride == 0 and offset+size <= len(data) and link < count, 'Malformed symbol table')
        strings = shoff+link*64
        need(u(strings+4, 4) == 3, 'Symbol names lack string table')
        start, length = u(strings+24, 8), u(strings+32, 8)
        need(start+length <= len(data), 'Truncated symbol strings')
        names = data[start:start+length]
        for symbol in range(offset, offset+size, 24):
            name_offset = u(symbol, 4)
            need(name_offset < len(names), 'Invalid symbol name offset')
            end = names.find(b'\0', name_offset)
            need(end >= 0, 'Unterminated symbol name')
            name = names[name_offset:end].decode('ascii')
            if name in names_wanted:
                need(name not in result and u(symbol+6, 2) != 0, 'Duplicate/undefined probe symbol')
                result[name] = u(symbol+8, 8)
    return result


def validate_payload(loader, binary, elf, metadata, mode):
    prior.image.pe_validate(loader, binary); prior.image.elf_validate(elf, binary)
    symbols = elf_symbols(elf)
    need(isinstance(metadata, dict) and set(metadata) == {'offset', 'bytes', 'fault_offsets'}
         and metadata['offset'] == 0x22000 and metadata['bytes'] == symbols.get('__payload_text_end')
         and type(metadata['bytes']) is int and 0 < metadata['bytes'] <= len(binary), 'Payload extent differs from linked ELF')
    need(not any(name.startswith('uefi_bar_') for name in symbols), 'Foreign BAR probe linked into IVRS build')
    sites = {'ivrs-write': ('uefi_ivrs_write_probe', bytes.fromhex('48c70000000000')),
             'ivrs-revoked': ('uefi_ivrs_revoked_probe', bytes.fromhex('488b00'))}
    expected = {}
    for candidate, (name, opcode) in sites.items():
        if candidate == mode:
            at = symbols.get(name)
            need(type(at) is int and 0 < at and at+len(opcode) <= metadata['bytes']
                 and binary[at:at+len(opcode)] == opcode, 'Fault site is not exact linked IOMMU probe instruction')
            expected[candidate] = at
        else: need(name not in symbols, 'Foreign IVRS fault probe present')
    need(metadata['fault_offsets'] == expected, 'Fault metadata does not match linked symbols')
    return metadata


def validate_receipt(receipt, contents):
    trace = module('ivrs_trace_receipt', 'kernel-uefi-ivrs-trace.py')
    need(isinstance(receipt, dict) and receipt.get('schema') == 'aurora-ivrs-run-v1'
         and receipt.get('mode') in ivrs.MODES, 'Wrong IVRS receipt schema/mode')
    mode = receipt['mode']
    need(receipt.get('status') == (33 if mode == 'ivrs-read' else 35), 'Process status disagrees with mode')
    need(receipt.get('iommu_profile') == ('architectural' if mode == 'ivrs-default' else ivrs.PROFILE),
         'Implicit/unreviewed IOMMU profile selection')
    need(receipt.get('firmware_profile') == 'clean' and receipt.get('firmware_source_revision') == REVISION,
         'Unreviewed clean firmware profile/source')
    files = receipt.get('files')
    need(isinstance(files, dict) and set(files) == FILES and set(contents) == FILES, 'Missing/extra IVRS run artifacts')
    paths = {}
    for role in FILES:
        record = files[role]
        need(isinstance(record, dict) and set(record) == {'path', 'sha256'}
             and isinstance(record['sha256'], str) and re.fullmatch('[0-9a-f]{64}', record['sha256']), 'Malformed artifact digest')
        need(isinstance(record['path'], str) and Path(record['path']).is_absolute(), 'Artifact path is not absolute')
        paths[role] = absolute(record['path'], receipt['cwd'])
        need(isinstance(contents[role], bytes) and sha256(contents[role]) == record['sha256'], 'Artifact hash mismatch: '+role)
        need(contents[role] or role == 'firmware_log', 'Empty run artifact: '+role)
    need(len(set(paths.values())) == len(paths), 'Artifact roles share a path')
    need(files['qemu']['sha256'] == PINS['qemu'], 'Unreviewed QEMU binary')
    need(contents['events'] == trace.EVENT_TEXT.encode(), 'Unreviewed IVRS trace event inventory')
    need(files['firmware_code']['sha256'] == PINS['clean_code'] and files['firmware_patch']['sha256'] == PINS['clean_patch'],
         'Unreviewed clean firmware CODE/patch')
    need(files['vars_template']['sha256'] == files['vars_initial']['sha256'] == PINS['clean_vars'], 'Non-pristine initial VARS')
    return paths, validate_arguments(receipt, paths)


def validate(path):
    path = Path(path); receipt = json.loads(path.read_text())
    need(isinstance(receipt, dict) and isinstance(receipt.get('files'), dict), 'Malformed IVRS receipt JSON')
    contents = {role: Path(record['path']).read_bytes() for role, record in receipt['files'].items()}
    paths, boot_root = validate_receipt(receipt, contents)
    metadata = json.loads(contents['payload_metadata'])
    validate_payload(contents['loader'], contents['payload'], contents['payload_elf'], metadata, receipt['mode'])
    boot_files = {str(p.resolve()) for p in Path(boot_root).rglob('*') if p.is_file()}
    need(boot_files == {paths['loader']}, 'Unrecorded files in launched FAT tree')
    trace = module('ivrs_trace_validate', 'kernel-uefi-ivrs-trace.py')
    coverage = trace.load_coverage(paths['coverage'])
    need(coverage['events'].encode() == contents['events'], 'Coverage/launch event inventory differs')
    # Provenance validation also checks both actual streams and all controls;
    # merely matching a process-status field cannot validate a receipt.
    result = trace.validate_trace(contents['trace'].decode(), contents['firmware_log'].decode(), contents['serial'].decode(),
                                  receipt['mode'], coverage, metadata)
    return dict(mode=receipt['mode'], qemu_sha256=PINS['qemu'], qemu_source_review=QEMU_SOURCE,
                compiler_sha256=receipt['files']['compiler']['sha256'], payload_sha256=receipt['files']['payload']['sha256'],
                iommu_profile=receipt['iommu_profile'], iommu_reads=result['iommu_reads'],
                source_manifest='not established by this receipt', dma_isolation='not established')


def self_test():
    failures = 0
    paths = {name: '/tmp/synthetic-ivrs/'+name for name in FILES}
    paths['loader'] = '/tmp/synthetic-ivrs/esp/EFI/BOOT/BOOTX64.EFI'
    common = [paths['qemu'], '-L', '/tmp/firmware', '-machine', 'q35', '-accel', 'tcg', '-cpu', 'qemu64', '-smp', '1', '-m', '128M',
              '-nic', 'none', '-display', 'none', '-monitor', 'none', '-no-reboot',
              '-device', 'nvme,serial=SYNTHETIC,bus=pcie.0,addr=02.0', '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04',
              '-serial', 'file:'+paths['serial'], '-debugcon', 'file:'+paths['firmware_log'], '-global', 'isa-debugcon.iobase=0x402',
              '-trace', 'events='+paths['events']+',file='+paths['trace'],
              '-drive', 'format=raw,file=fat:ro:/tmp/synthetic-ivrs/esp,snapshot=on',
              '-drive', 'if=pflash,format=raw,readonly=on,file='+paths['firmware_code'],
              '-drive', 'if=pflash,format=raw,file='+paths['vars_after']]
    for mode in ivrs.MODES:
        argv = common + ([] if mode == 'ivrs-missing' else ['-device', IOMMU])
        receipt = dict(cwd='/tmp/synthetic-ivrs', boot_root='/tmp/synthetic-ivrs/esp',
                       environment={'LD_LIBRARY_PATH': '/tmp/synthetic-libraries'}, firmware_profile='clean', mode=mode, argv=argv)
        validate_arguments(receipt, paths)
        cases = [dict(receipt, argv=argv+['-device', IOMMU]), dict(receipt, firmware_profile='stock'),
                 dict(receipt, argv=argv+['-device', 'nvme-ns,drive=unsafe']),
                 dict(receipt, environment={'LD_LIBRARY_PATH': '/lib', 'LD_PRELOAD': 'unsafe'})]
        for index in range(len(argv)): cases.append(dict(receipt, argv=argv[:index]+argv[index+1:]))
        if mode != 'ivrs-missing':
            for option in ('pt', 'intremap', 'device-iotlb', 'xtsup'):
                cases.append(dict(receipt, argv=[v.replace(option+'=off', option+'=on') for v in argv]))
            cases.append(dict(receipt, argv=argv[:-2]))
        for candidate in cases:
            try: validate_arguments(candidate, paths)
            except (ValueError, KeyError): failures += 1
            else: raise RuntimeError('Invalid IVRS invocation accepted: '+mode)
    print(f'PASS: IVRS provenance {len(ivrs.MODES)} synthetic launch profiles and {failures} adversarial cases; real artifacts required separately')


if __name__ == '__main__':
    if sys.argv[1:] == ['--self-test']: self_test()
    else:
        try: result = validate(sys.argv[1])
        except (ValueError, IndexError, KeyError, OSError) as error: sys.exit('FAIL: '+str(error))
        print('PASS: strict IVRS provenance '+json.dumps(result, sort_keys=True))
