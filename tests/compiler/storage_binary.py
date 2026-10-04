#!/usr/bin/env python3
"""Independent native functional acceptance for storage byte readers and CRC32C.

Expected endian values come from Python's byte decoder. CRC32C uses whole-message
GF(2) polynomial division with the normal Castagnoli polynomial and reversed input
octets, not the implementation's reflected per-bit recurrence. Published vectors
anchor the model. Every observation is an assembled native function's complete
64-bit result, and every API call must return normally. All checks use require,
including under python -O. This is functional evidence for readonly parsing and
header integrity, not a filesystem mount, compatibility, or security claim.

Run: python3 tests/compiler/storage_binary.py /path/to/aurorac
Harness: python3 -O tests/compiler/storage_binary.py --self-test-only
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
import hashlib
from pathlib import Path
import random
import signal
import tempfile
import time

from readonly_spans import array, view
from unsigned_oracle import (Case, NativeRunner, Observation, command, rejected,
                             require, validate_values)


ROOT = Path(__file__).resolve().parents[2]
MAX_U64 = (1 << 64) - 1
MAX_U32 = (1 << 32) - 1
MIN_I64 = -(1 << 63)
MAX_I64 = (1 << 63) - 1
NORMAL_POLYNOMIAL = (1 << 32) | 0x1EDC6F41
VECTORS = (
    ("empty", b"", 0x00000000),
    ("123456789", b"123456789", 0xE3069283),
    ("32 zero bytes", bytes(32), 0x8A9136AA),
    ("32 ff bytes", bytes([255]) * 32, 0x62A8AB43),
    ("ascending 0..31", bytes(range(32)), 0x46DD794E),
    ("descending 31..0", bytes(reversed(range(32))), 0x113FDB5C),
)


def reverse_bits(value, width):
    require(0 <= value < (1 << width), "invalid reflection operand")
    return int(f"{value:0{width}b}"[::-1], 2)


def polynomial_remainder(dividend):
    """Divide a complete polynomial over GF(2), canceling its highest term."""
    require(dividend >= 0, "negative polynomial")
    while dividend.bit_length() > 32:
        dividend ^= NORMAL_POLYNOMIAL << (dividend.bit_length() - 33)
    return dividend


def crc32c_reference(values, previous=0):
    require(0 <= previous <= MAX_U32, "invalid previous finalized CRC")
    message = bytes(reverse_bits(value, 8) for value in values)
    initial = reverse_bits(previous ^ MAX_U32, 32)
    dividend = ((initial << (len(message) * 8))
                ^ (int.from_bytes(message, "big") << 32))
    return reverse_bits(polynomial_remainder(dividend), 32) ^ MAX_U32


def read_reference(values, offset, width, endian):
    if offset < 0 or len(values) < width or offset > len(values) - width:
        return None
    return int.from_bytes(bytes(values[offset:offset + width]), endian)


def range_valid(size, offset, count):
    return offset >= 0 and count >= 0 and offset <= size and count <= size - offset


def owned_bytes(values):
    """Keep an independent original array for exact byte-for-byte comparison."""
    return (array("bytes", values)
            + f"const array<u8,{len(values)}> original=bytes;" + view())


def unchanged():
    return ("i64 compare_index=0;while(compare_index<view.size()){"
            "if(bytes[compare_index]!=original[compare_index]){return 17u64;}"
            "compare_index=compare_index+1;}")


class Suite:
    """The readonly_spans.Suite pattern, with per-family counts and receipts."""
    def __init__(self, directory, compiler, timeout, keep_going):
        self.runner = NativeRunner(directory, compiler, timeout)
        self.keep_going = keep_going
        self.counts = Counter()
        self.failures = []
        self.api_calls = Counter()

    def check(self, family, name, body, expected=MAX_U64, imports=(), calls=1):
        program = ("module storage_binary;"
                   + "".join(f"import {module};" for module in imports)
                   + f"auto test()->u64{{{body}}}")
        path = self.runner.directory / "input.au"
        output = self.runner.directory / "compiled.s"
        path.write_text(program)
        output.unlink(missing_ok=True)
        try:
            command([self.runner.compiler, "--module-root", ROOT / "library", path,
                     "-o", output], timeout=self.runner.timeout)
            require(path.read_text() == program, name + ": compiler changed source")
            observed, _ = self.runner.assemble(output.read_text(), ["test"])
            validate_values(observed, [Case(name, body, expected)])
            self.counts[family] += 1
            self.api_calls[family] += calls
            print(f"PASS storage {family}: {name}", flush=True)
        except AssertionError as failure:
            details = f"{family}: {name}: {failure}\nReproduction source:\n{program}"
            if not self.keep_going:
                raise AssertionError(details) from failure
            self.failures.append(details)
            print("FAIL storage " + details, flush=True)


def self_tests(suite):
    for name, values, expected in VECTORS:
        require(crc32c_reference(values) == expected, "bad CRC reference: " + name)
        for split in range(len(values) + 1):
            previous = crc32c_reference(values[:split])
            require(crc32c_reference(values[split:], previous) == expected,
                    "bad continuation reference: " + name)
    require(crc32c_reference([], MAX_U32) == MAX_U32,
            "empty continuation did not retain previous CRC")
    for previous in (-1, 1 << 32, MAX_U64):
        rejected(lambda previous=previous: crc32c_reference([], previous),
                 "invalid finalized CRC")
    for width in (2, 4, 8):
        for endian in ("little", "big"):
            require(read_reference([255] * width, 0, width, endian)
                    == (1 << (width * 8)) - 1, "truncated endian reference")
            for offset in (MIN_I64, -1, 1, MAX_I64):
                require(read_reference([255] * width, offset, width, endian) is None,
                        "bad endian offset model")
    require(range_valid(1, 1, 0) and range_valid(0, 0, 0), "bad empty range model")
    for offset, count in ((MIN_I64, 0), (-1, 0), (0, MIN_I64), (0, -1),
                          (MAX_I64, 0), (0, MAX_I64), (1, 1)):
        require(not range_valid(1, offset, count), "bad signed range model")
    full = Observation(MAX_U64.to_bytes(8, "little"), exit_code=0)
    validate_values(full, [Case("complete u64 observation", "", MAX_U64)])
    rejected(lambda: validate_values(full, [Case("low-byte truncation", "", 255)]),
             "truncated u64 expectation")
    for bad in (replace(full, output=full.output[:-1]),
                replace(full, output=full.output + b"x"), replace(full, exit_code=1),
                replace(full, terminal_signal=signal.SIGILL)):
        rejected(lambda bad=bad: validate_values(bad, [Case("bad observation", "", MAX_U64)]),
                 "malformed native result")
    observed, _ = suite.runner.assemble(
        f'.text\n.globl test\ntest:\nmovabsq ${MAX_U64}, %rax\nret\n'
        '.section .note.GNU-stack,"",@progbits\n', ["test"])
    validate_values(observed, [Case("native full-width control", "", MAX_U64)])
    print("PASS storage harness: six CRC vectors, every vector split, "
          "independent endian/range models, full native u64 and malformed-result rejection",
          flush=True)


def binary_cases(suite, seed, random_count):
    rng = random.Random(seed)
    for size in (1, 2, 3, 4, 7, 8, 9, 16, 31, 64, 4096):
        values = [rng.randrange(256) for _ in range(size)]
        values[0], values[-1] = 255, 128
        for width in (2, 4, 8):
            offsets = sorted({MIN_I64, -1, 0, 1, size - width, size - width + 1,
                              size - 1, size, size + 1, MAX_I64}
                             | {rng.randrange(size + 1) for _ in range(random_count)})
            for native, endian in (("le", "little"), ("be", "big")):
                body = owned_bytes(values)
                for index, offset in enumerate(offsets):
                    expected = read_reference(values, offset, width, endian)
                    status = "out_of_range" if expected is None else "success"
                    body += (f"const std::ByteReadResult r{index}=std::read_{native}{width * 8}(view,{offset});"
                             f"if(r{index}.status()!=std::ByteReadStatus::{status}){{return 1u64;}}"
                             f"if(r{index}.value_or(0u64)!={0 if expected is None else expected}u64){{return 2u64;}}"
                             f"if(r{index}.value_or({MAX_U64}u64)!={MAX_U64 if expected is None else expected}u64)"
                             "{return 3u64;}")
                suite.check("binary", f"{native}{width * 8} size {size}: {len(offsets)} offsets",
                            body + unchanged() + f"return {MAX_U64}u64;",
                            imports=("std.binary",), calls=len(offsets))
    for width in (2, 4, 8):
        for native, endian in (("le", "little"), ("be", "big")):
            for values in ([0] * width, [255] * width,
                           [128, 255, 1, 2, 3, 4, 5, 129][:width]):
                expected = read_reference(values, 0, width, endian)
                body = (owned_bytes(values)
                        + f"const std::ByteReadResult report=std::read_{native}{width * 8}(view,0);"
                        "if(report.status()!=std::ByteReadStatus::success){return 17u64;}"
                        + unchanged() + "return report.value_or(42u64);")
                suite.check("binary", f"{native}{width * 8} direct full-width {values}",
                            body, expected, imports=("std.binary",))
            values = [255] * width
            body = (array("bytes", values)
                    + f"const std::ByteReadResult result=std::read_{native}{width * 8}(borrow_bytes(bytes),0);"
                    "bytes[0]=0u8;const std::ByteReadResult copy=result;"
                    "return copy.value_or(0u64);")
            suite.check("binary", f"{native}{width * 8} scalar result survives owner write",
                        body, (1 << (width * 8)) - 1, imports=("std.binary",))
    body = (f"const std::ByteReadResult report=std::ByteReadResult(std::ByteReadStatus::out_of_range,{MAX_U64}u64);"
            "if(report.value_or(0u64)!=0u64){return 17u64;}"
            f"return report.value_or({MAX_U64}u64);")
    suite.check("binary", "failed result masks nonzero payload", body,
                imports=("std.binary",), calls=0)


def crc_call(suite, name, values, offset, count, previous=None):
    stored = list(values) if values else [171]
    invalid_previous = previous is not None and previous > MAX_U32
    valid = range_valid(len(stored), offset, count)
    if invalid_previous:
        status, expected = "invalid_previous", None
    elif not valid:
        status, expected = "out_of_range", None
    else:
        status = "success"
        expected = crc32c_reference(stored[offset:offset + count], previous or 0)
    call = (f"std::crc32c(view,{offset},{count})" if previous is None
            else f"std::crc32c_extend({previous}u64,view,{offset},{count})")
    body = (owned_bytes(stored) + f"const std::ChecksumResult report={call};"
            f"if(report.status()!=std::ChecksumStatus::{status}){{return 17u64;}}"
            f"if(report.value_or(0u64)!={expected if expected is not None else 0}u64){{return 18u64;}}"
            + unchanged() + f"return report.value_or({MAX_U64}u64);")
    suite.check("crc32c", name, body, expected if expected is not None else MAX_U64,
                imports=("std.checksum",))


def crc_cases(suite, seed, random_count):
    for name, values, expected in VECTORS:
        crc_call(suite, "published " + name, values, 0, len(values))
        require(crc32c_reference(values) == expected, "published vector changed")
    rng = random.Random(seed ^ 0xC32C)
    for size in (1, 2, 3, 7, 8, 31, 32, 255, 256, 511, 512, 1024, 4096):
        values = [rng.randrange(256) for _ in range(size)]
        crc_call(suite, f"seed {seed}: full size {size}", values, 0, size)
        offset = rng.randrange(size + 1)
        count = rng.randrange(size - offset + 1)
        crc_call(suite, f"seed {seed}: subrange {offset}+{count} size {size}",
                 values, offset, count)
        # Empty prefix/suffix, midpoint, and seeded splits all use native first
        # results as native continuation inputs; no Python result is substituted.
        splits = sorted({0, 1, size // 2, size - 1, size}
                        | {rng.randrange(size + 1) for _ in range(random_count)})
        body = owned_bytes(values)
        expected = crc32c_reference(values)
        for index, split in enumerate(splits):
            body += (f"const std::ChecksumResult first{index}=std::crc32c(view,0,{split});"
                     f"if(first{index}.status()!=std::ChecksumStatus::success){{return 1u64;}}"
                     f"if(first{index}.value_or({MAX_U64}u64)!={crc32c_reference(values[:split])}u64){{return 2u64;}}"
                     f"const std::ChecksumResult next{index}=std::crc32c_extend(first{index}.value_or({MAX_U64}u64),view,{split},{size - split});"
                     f"if(next{index}.status()!=std::ChecksumStatus::success){{return 3u64;}}"
                     f"if(next{index}.value_or({MAX_U64}u64)!={expected}u64){{return 4u64;}}")
        suite.check("crc32c", f"seed {seed}: size {size}, {len(splits)} continuation splits",
                    body + unchanged() + f"return {MAX_U64}u64;",
                    imports=("std.checksum",), calls=len(splits) * 2)
    values = [0, 128, 255, 17, 90, 221, 3, 42]
    for offset, count in ((MIN_I64, 0), (-1, 0), (MAX_I64, 0),
                          (0, MIN_I64), (0, -1), (0, MAX_I64),
                          (MAX_I64, MAX_I64), (1, MAX_I64), (8, 1), (9, 0),
                          (7, 2), (0, 9), (8, 0), (0, 0), (7, 1)):
        crc_call(suite, f"signed range {offset}+{count}", values, offset, count)
        crc_call(suite, f"continuation signed range {offset}+{count}",
                 values, offset, count, 0x89ABCDEF)
    for previous in (0, 1, 0x80000000, 0xE3069283, MAX_U32):
        for offset, count in ((0, 0), (8, 0), (0, 8), (3, 2)):
            crc_call(suite, f"finalized prior {previous:#x}, {offset}+{count}",
                     values, offset, count, previous)
    for previous in (1 << 32, 1 << 63, MAX_U64):
        for offset, count in ((0, 8), (0, 0), (MIN_I64, MAX_I64)):
            crc_call(suite, f"invalid prior {previous:#x}, precedence {offset}+{count}",
                     values, offset, count, previous)
    for status in ("out_of_range", "invalid_previous"):
        body = (f"const std::ChecksumResult report=std::ChecksumResult(std::ChecksumStatus::{status},{MAX_U64}u64);"
                "if(report.value_or(0u64)!=0u64){return 17u64;}"
                f"return report.value_or({MAX_U64}u64);")
        suite.check("crc32c", f"{status} masks nonzero payload", body,
                    imports=("std.checksum",), calls=0)
    expected = crc32c_reference(values)
    body = (array("bytes", values)
            + "const std::ChecksumResult report=std::crc32c(borrow_bytes(bytes),0,8);"
            "bytes[0]=99u8;const std::ChecksumResult copy=report;"
            f"return copy.value_or({MAX_U64}u64);")
    suite.check("crc32c", "copied result survives owner write", body, expected,
                imports=("std.checksum",))


def xfs_fixture(seed):
    rng = random.Random(seed ^ 0x584653)
    values = bytearray(rng.randrange(256) for _ in range(512))
    values[0:4] = b"XFSB"
    values[100:102] = (5).to_bytes(2, "big")
    values[102:104] = (512).to_bytes(2, "big")
    values[121] = 9
    values[511] = 167
    for offset, value in zip((208, 212, 216, 220),
                             (0x80000001, 0xFEDCBA98, 0x01020304, 0xFFFFFFFF)):
        values[offset:offset + 4] = value.to_bytes(4, "big")
    return xfs_rechecksum(values)


def xfs_rechecksum(values):
    values = bytearray(values)
    require(len(values) == 512, "fixture must have one exact sector")
    values[224:228] = bytes(4)
    values[224:228] = crc32c_reference(values).to_bytes(4, "little")
    return values


def xfs_check(suite, name, values, status, returned_field=None):
    masks = [int.from_bytes(values[offset:offset + 4], "big")
             for offset in (208, 212, 216, 220)]
    if status in ("wrong_length", "unrecognized"):
        masks = [0, 0, 0, 0]
    fields = ("features_compat", "features_ro_compat", "features_incompat",
              "features_log_incompat")
    body = (owned_bytes(values)
            + "const fs::XfsProbeResult report=fs::probe_xfs_v5_512(view);"
            f"if(report.status()!=fs::XfsProbeStatus::{status}){{return 17u64;}}")
    for field, value in zip(fields, masks):
        body += f"if(report.{field}()!={value}u64){{return 18u64;}}"
    body += unchanged()
    expected = MAX_U64
    if returned_field is not None:
        body += f"return report.{fields[returned_field]}();"
        expected = masks[returned_field]
    else:
        body += f"return {MAX_U64}u64;"
    suite.check("xfs", name, body, expected, imports=("fs.xfs_probe",))


def xfs_cases(suite, seed):
    valid = xfs_fixture(seed)
    require(any(valid[264:]), "fixture needs nonzero bytes beyond fixed header")
    require(valid[511] != 0, "fixture needs a nonzero final sector byte")
    zeroed = valid[:224] + bytes(4) + valid[228:]
    omitted = valid[:224] + valid[228:]
    stored = int.from_bytes(valid[224:228], "little")
    require(crc32c_reference(zeroed) == stored, "fixture CRC mismatch")
    require(crc32c_reference(omitted) != stored, "fixture does not distinguish omitted bytes")
    require(valid[224:228] != valid[224:228][::-1], "fixture does not distinguish CRC endianness")
    xfs_check(suite, "complete nonzero 512-byte sector", valid, "header_integrity_valid")
    for field in range(4):
        xfs_check(suite, f"raw BE feature mask {field}, all bits observable", valid,
                  "header_integrity_valid", returned_field=field)
    for offset in (208, 212, 216, 220):
        values = bytearray(valid)
        values[offset:offset + 4] = (0xDEADBEEF).to_bytes(4, "big")
        xfs_check(suite, f"changed raw mask at {offset} without new checksum", values,
                  "checksum_mismatch")
        xfs_check(suite, f"changed raw mask at {offset} with valid checksum is only header integrity",
                  xfs_rechecksum(values), "header_integrity_valid")
    for size in (1, 224, 264, 511, 513, 4096):
        values = (valid * ((size + 511) // 512))[:size]
        xfs_check(suite, f"wrong length {size}", values, "wrong_length")
    for offset in (0, 1, 2, 3):
        values = bytearray(valid)
        values[offset] ^= 1
        xfs_check(suite, f"magic mismatch byte {offset} precedes checksum", values,
                  "unrecognized")
    for version in (0, 4, 6, 15, 0xFFF4):
        values = bytearray(valid)
        values[100:102] = version.to_bytes(2, "big")
        xfs_check(suite, f"unsupported version {version:#x} precedes checksum", values,
                  "unsupported_profile")
    for version in (0x0015, 0xA005, 0xFFF5):
        values = bytearray(valid)
        values[100:102] = version.to_bytes(2, "big")
        xfs_check(suite, f"version low-nibble mask {version:#x}", xfs_rechecksum(values),
                  "header_integrity_valid")
    for size in (0, 256, 1024, 4096):
        values = bytearray(valid)
        values[102:104] = size.to_bytes(2, "big")
        xfs_check(suite, f"unsupported declared sector size {size}", values,
                  "unsupported_profile")
    for sector_log in (0, 8, 10, 255):
        values = bytearray(valid)
        values[121] = sector_log
        xfs_check(suite, f"unsupported sector log {sector_log}", values,
                  "unsupported_profile")
        xfs_check(suite, f"unsupported sector log {sector_log} despite valid checksum",
                  xfs_rechecksum(values), "unsupported_profile")
    for offset in (128, 223, 224, 225, 226, 227, 228, 300, 511):
        values = bytearray(valid)
        values[offset] ^= 1
        xfs_check(suite, f"corruption at sector byte {offset}", values,
                  "checksum_mismatch")
    values = bytearray(valid)
    values[224:228] = values[224:228][::-1]
    xfs_check(suite, "wrong stored CRC endianness", values, "checksum_mismatch")
    values = bytearray(valid)
    values[224:228] = crc32c_reference(omitted).to_bytes(4, "little")
    xfs_check(suite, "omitted CRC bytes differ from zero substitution", values,
              "checksum_mismatch")
    values = bytearray(valid)
    values[224:228] = bytes(4)
    xfs_check(suite, "zero stored CRC is still checked", values, "checksum_mismatch")
    values = bytearray(valid)
    values[511] ^= 1
    xfs_check(suite, "changed final byte with recalculated CRC", xfs_rechecksum(values),
              "header_integrity_valid")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", nargs="?", type=Path, default=ROOT / "build/aurorac")
    parser.add_argument("--seed", type=int, default=15015)
    parser.add_argument("--random-count", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument("--self-test-only", action="store_true")
    parser.add_argument("--only", choices=("binary", "crc32c", "xfs"))
    args = parser.parse_args()
    require(0 <= args.random_count <= 64, "random-count must be between 0 and 64")
    require(args.timeout > 0, "timeout must be positive")
    compiler = args.compiler.resolve()
    started = time.monotonic()
    if not args.self_test_only:
        print(f"INFO storage compiler={compiler} sha256="
              f"{hashlib.sha256(compiler.read_bytes()).hexdigest()} seed={args.seed} "
              f"random-count={args.random_count}", flush=True)
        modules = {"binary": "std/binary.au", "crc32c": "std/checksum.au",
                   "xfs": "fs/xfs_probe.au"}
        for family, module in modules.items():
            if args.only is None or args.only == family:
                path = ROOT / "library" / module
                print(f"INFO storage {module} sha256="
                      f"{hashlib.sha256(path.read_bytes()).hexdigest()}", flush=True)
    with tempfile.TemporaryDirectory(prefix="aurora-storage-binary-") as temporary:
        suite = Suite(Path(temporary), compiler, args.timeout, args.keep_going)
        self_tests(suite)
        if args.self_test_only:
            return
        if args.only in (None, "binary"):
            binary_cases(suite, args.seed, args.random_count)
        if args.only in (None, "crc32c"):
            crc_cases(suite, args.seed, args.random_count)
        if args.only in (None, "xfs"):
            xfs_cases(suite, args.seed)
        print(f"INFO storage counts: native={dict(suite.counts)} "
              f"API calls={dict(suite.api_calls)} failures={len(suite.failures)}", flush=True)
        require(not suite.failures, f"{len(suite.failures)} storage cases failed; receipts above")
        print(f"PASS storage: {sum(suite.counts.values())} native functional cases, "
              f"{sum(suite.api_calls.values())} API calls, complete u64 observations; "
              f"seed={args.seed} random-count={args.random_count}; "
              f"elapsed={time.monotonic() - started:.2f}s", flush=True)


if __name__ == "__main__":
    main()
