#!/usr/bin/env python3
"""Execute the pinned Aurora probe against one preserved mkfs.xfs superblock.

This verifier never creates, opens, mounts or modifies a filesystem image.
It decodes only the bounded canonical hex transport of the preserved512-byte
fixture. Native build outputs use tempfile and honor the caller's TMPDIR.
"""
from __future__ import annotations

import hashlib
import argparse
import importlib.util
import json
import re
from pathlib import Path
import shutil
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COMPILER = Path('/tmp/aurora-m014-compiler-corrected')
COMPILER_SHA256 = '2d86780c0082d861e7031955737eef81bb36936c7971d5032b6a1abbb4a24bf8'
FIXTURE_SHA256 = '55ad821909c312048d9936a74c8904cd25f97aa190b48ae0004b03eaffdc6586'
HEX_SHA256 = 'd1d3fbc3f8b693d1c0ddf395e92b136a81b2a5d30b9e3cdec36addd580d42986'
HEX_SIZE = 1728
MASK32 = (1 << 32) - 1


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def decode_fixture_hex(payload):
    """Decode only the canonical 32-row ASCII transport of the pinned raw bytes."""
    require(len(payload) == HEX_SIZE, 'hex transport must be exactly 1728 bytes')
    rows = payload.splitlines(keepends=True)
    require(len(rows) == 32, 'hex transport must have exactly 32 rows')
    decoded = bytearray()
    for index, row in enumerate(rows):
        require(re.fullmatch(rb'[0-9a-f]{4}  (?:[0-9a-f]{2} ){15}[0-9a-f]{2}\n', row)
                is not None, 'invalid canonical row or two-digit byte width')
        require(int(row[:4], 16) == index * 16, 'hex row offset is missing, duplicate or unordered')
        decoded.extend(int(byte, 16) for byte in row[6:-1].split(b' '))
    require(len(decoded) == 512, 'decoded fixture must contain exactly 512 bytes')
    require(hashlib.sha256(decoded).hexdigest() == FIXTURE_SHA256, 'decoded raw fixture SHA256 mismatch')
    require(hashlib.sha256(payload).hexdigest() == HEX_SHA256, 'hex transport SHA256 mismatch')
    return bytes(decoded)


def read_fixture_hex(path):
    # Read at most the exact transport size plus one overflow byte.
    with path.open('rb') as stream:
        payload = stream.read(HEX_SIZE + 1)
    return decode_fixture_hex(payload)


def native_workspace():
    # Do not force /tmp: bounded callers provide their own measured TMPDIR.
    return tempfile.TemporaryDirectory(prefix='aurora-xfs-native-')


def transport_self_tests(payload):
    rows = payload.splitlines(keepends=True)
    controls = {
        'missing row': b''.join(rows[:-1]),
        'extra row': payload + rows[-1],
        'duplicate offset': rows[0] + rows[0] + b''.join(rows[2:]),
        'out-of-order rows': rows[1] + rows[0] + b''.join(rows[2:]),
        'wrong offset': b'0001' + payload[4:],
        'malformed offset': b'zzzz' + payload[4:],
        'one-digit byte': payload[:6] + b'5' + payload[8:],
        'three-digit byte': payload[:6] + b'058' + payload[8:],
        'wrong byte widths at fixed size': payload[:6] + b'5 046' + payload[11:],
        'invalid hex byte': payload[:6] + b'gg' + payload[8:],
        'changed raw byte': payload[:6] + b'59' + payload[8:],
        'missing final newline': payload[:-1],
        'noncanonical separator': payload[:4] + b'\t ' + payload[6:],
        'non-ASCII input': bytes([255]) + payload[1:],
        'oversized input': payload + b'x' * HEX_SIZE,
    }
    for name, malformed in controls.items():
        try:
            decode_fixture_hex(malformed)
        except RuntimeError:
            continue
        raise RuntimeError('transport control unexpectedly accepted: ' + name)
    with tempfile.TemporaryDirectory(prefix='aurora-xfs-transport-') as directory:
        missing = Path(directory) / 'missing.hex'
        try:
            read_fixture_hex(missing)
        except FileNotFoundError:
            pass
        else:
            raise RuntimeError('missing transport unexpectedly accepted')
        oversized = Path(directory) / 'oversized.hex'
        oversized.write_bytes(payload + b'x' * HEX_SIZE)
        try:
            read_fixture_hex(oversized)
        except RuntimeError:
            pass
        else:
            raise RuntimeError('bounded reader accepted oversized transport')
    # Exercise the same factory used by the native probe under a distinct
    # caller-selected tempfile root. Restore Python's cached choice afterward.
    with tempfile.TemporaryDirectory(prefix='aurora-xfs-temp-policy-') as parent:
        saved = tempfile.tempdir
        try:
            tempfile.tempdir = parent
            with native_workspace() as native:
                require(Path(native).parent == Path(parent), 'native workspace ignores caller temp root')
        finally:
            tempfile.tempdir = saved
    print('PASS 17 hex transport rejection controls and exact raw/transport hashes')
    print('PASS native workspace honors caller-selected tempfile root')


def reverse_bits(value, width):
    return int(f'{value:0{width}b}'[::-1], 2)


def crc32c_gf2(data):
    """Whole-message polynomial division, rather than Aurora's byte recurrence."""
    message = bytes(reverse_bits(value, 8) for value in data)
    polynomial = (MASK32 << (8 * len(message))) ^ (int.from_bytes(message, 'big') << 32)
    while polynomial.bit_length() > 32:
        polynomial ^= 0x11EDC6F41 << (polynomial.bit_length() - 33)
    return reverse_bits(polynomial, 32) ^ MASK32


def declaration(data):
    return ('const array<u8,512> bytes={' + ','.join(f'{x}u8' for x in data)
            + '};const builtin::span<const u8> view=borrow_bytes(bytes);')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transport-self-test-only', action='store_true')
    parser.add_argument('--receipt', type=Path, help='explicit JSON output path; no receipt is written by default')
    parser.add_argument('--compiler', type=Path, default=COMPILER)
    parser.add_argument('--compiler-sha256', default=COMPILER_SHA256,
                        help='expected SHA256, required to match the selected compiler bytes')
    args = parser.parse_args()
    fixture = HERE / 'superblock-v5-512.hex'
    data = read_fixture_hex(fixture)
    with fixture.open('rb') as stream:
        transport_self_tests(stream.read(HEX_SIZE + 1))
    if args.transport_self_test_only:
        return
    compiler = args.compiler.resolve()
    compiler_sha256 = args.compiler_sha256
    require(len(compiler_sha256) == 64 and all(c in '0123456789abcdef' for c in compiler_sha256),
            'expected compiler SHA256 must be 64 lowercase hexadecimal characters')
    require(sha256(compiler) == compiler_sha256, 'compiler identity changed')
    require(len(data) == 512, 'fixture must have exactly 512 bytes')
    zeroed = bytearray(data)
    zeroed[224:228] = bytes(4)
    stored = int.from_bytes(data[224:228], 'little')
    computed = crc32c_gf2(zeroed)
    require(crc32c_gf2(b'123456789') == 0xE3069283, 'GF(2) known vector mismatch')
    require(computed == stored == 0xB67113C7, 'GF(2) fixture CRC mismatch')
    fields = {name: int.from_bytes(data[offset:offset + 4], 'big') for name, offset in (
        ('features_compat', 208), ('features_ro_compat', 212),
        ('features_incompat', 216), ('features_log_incompat', 220))}
    raw = {
        'magic_be32': int.from_bytes(data[:4], 'big'),
        'version_be16': int.from_bytes(data[100:102], 'big'),
        'version_low4': int.from_bytes(data[100:102], 'big') & 15,
        'sectsize_be16': int.from_bytes(data[102:104], 'big'),
        'sectlog_u8': data[121],
        **fields,
        'crc_bytes_hex': data[224:228].hex(),
        'crc_le32': stored,
        'crc_gf2': computed,
        'xfs_db_crc_display': '0xc71371b6 (correct)',
    }
    with native_workspace() as temporary:
        work = Path(temporary)
        copied_runner = work / 'unsigned_oracle.py'
        shutil.copyfile(ROOT / 'tests/compiler/unsigned_oracle.py', copied_runner)
        spec = importlib.util.spec_from_file_location('xfs_fixture_runner', copied_runner)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        module.ROOT = ROOT
        cases = []

        def add(name, tail, expected, result_type='u64', values=data):
            cases.append(module.Case(name, declaration(values) + tail, expected,
                                     result_type=result_type,
                                     imports=('fs.xfs_probe', 'std.binary', 'std.checksum')))

        probe = 'const fs::XfsProbeResult result=fs::probe_xfs_v5_512(view);'
        add('real_header_integrity_valid', probe +
            'return result.status()==fs::XfsProbeStatus::header_integrity_valid;', 1, 'bool')
        for name, expected in fields.items():
            add(name, probe + f'return result.{name}();', expected)
        for name, expression, expected in (
            ('magic_be32', 'std::read_be32(view,0)', raw['magic_be32']),
            ('version_be16', 'std::read_be16(view,100)', raw['version_be16']),
            ('version_low4', 'std::read_be16(view,100)', 5),
            ('sectsize_be16', 'std::read_be16(view,102)', 512),
            ('crc_le32', 'std::read_le32(view,224)', stored),
        ):
            mask = '&15u64' if name == 'version_low4' else ''
            add(name, f'const std::ByteReadResult read={expression};'
                f'return read.value_or(0u64){mask};', expected)
        add('sectlog_u8', 'return view.at(121)==9u8;', 1, 'bool')
        add('crc_zeroed_whole_sector',
            'const array<u8,4> zeros={0u8,0u8,0u8,0u8};'
            'const std::ChecksumResult prefix=std::crc32c(view,0,224);'
            'const std::ChecksumResult middle=std::crc32c_extend('
            'prefix.value_or(0u64),borrow_bytes(zeros),0,4);'
            'const std::ChecksumResult complete=std::crc32c_extend('
            'middle.value_or(0u64),view,228,284);return complete.value_or(0u64);',
            computed)
        add('probe_preserves_all_512_bytes',
            'const array<u8,512> original=bytes;' + probe +
            'i64 index=0;while(index<512){if(bytes[index]!=original[index])'
            '{return false;}index=index+1;}return true;', 1, 'bool')
        for name, offset in (('changed_padding_rejected', 511), ('changed_crc_rejected', 224)):
            damaged = bytearray(data)
            damaged[offset] ^= 1
            add(name, probe + 'return result.status()==fs::XfsProbeStatus::checksum_mismatch;',
                1, 'bool', damaged)
        runner = module.NativeRunner(work, compiler, 60)
        runner.cases(cases)
        # Capture the full scalar values from another run of the same native binary.
        observation, _ = runner.assemble((work / 'compiled.s').read_text(),
                                         [f'oracle_{n}' for n in range(len(cases))])
        module.validate_values(observation, cases)
        results = []
        for index, case in enumerate(cases):
            actual = int.from_bytes(observation.output[index * 8:(index + 1) * 8], 'little')
            results.append({'name': case.name, 'expected': case.expected,
                            'observed': actual, 'result_type': case.result_type, 'passed': True})
        report = {
            'fixture_sha256': FIXTURE_SHA256,
            'fixture_transport_sha256': HEX_SHA256,
            'fixture_transport': 'canonical 32-row ASCII hex; decoded raw512 SHA independently checked',
            'compiler_path': str(compiler), 'compiler_sha256': compiler_sha256,
            'oracle': 'Python unbounded-integer GF(2) division, normal polynomial 0x11edc6f41',
            'source_sha256': {str(path.relative_to(ROOT)): sha256(path) for path in (
                ROOT / 'library/fs/xfs_probe.au', ROOT / 'library/std/checksum.au',
                ROOT / 'library/std/binary.au', ROOT / 'tests/compiler/unsigned_oracle.py',
                ROOT / 'tests/compiler/integer_signal.cpp', Path(__file__).resolve())},
            'raw_fields': raw, 'native_exit_code': observation.exit_code,
            'native_terminal_signal': observation.terminal_signal,
            'native_output_hex': observation.output.hex(),
            'native_cases_passed': len(cases), 'native_cases': results,
            'generated_source_sha256': sha256(work / 'input.au'),
            'generated_assembly_sha256': sha256(work / 'compiled.s'),
        }
        if args.receipt is not None:
            args.receipt.write_text(json.dumps(report, indent=2) + '\n')
        print(f'PASS {len(cases)} native observations against real mkfs.xfs fixture')
        print(f'CRC bytes={data[224:228].hex(" ")} LE/GF(2)/native=0x{stored:08x}')
        print('Raw feature masks:', ', '.join(f'{name}=0x{value:x}' for name, value in fields.items()))


if __name__ == '__main__':
    main()
