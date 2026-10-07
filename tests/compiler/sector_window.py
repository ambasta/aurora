#!/usr/bin/env python3
"""Copied sectors from call-scoped readonly windows against complete byte models."""

import argparse
import hashlib
from pathlib import Path
import tempfile

from block_io import check_sector
from unsigned_oracle import Case, NativeRunner, Rejection, require


IMPORTS = ("std.binary", "std.binary_buffer", "storage.sector", "storage.block_io", "storage.sector_window")
SPAN = "builtin::span<const u8>"
MIN_I64 = -(1 << 63)
MAX_I64 = (1 << 63) - 1
MAX_U64 = (1 << 64) - 1
ZERO = bytes(512)


def pattern(length):
    return bytes((index * 53 + index // 256 * 31 + 7) % 256 for index in range(length))


def source_array(length, const=False):
    # One array only: 4096 source elements already reserve 32768 frame bytes.
    data = pattern(max(1, length))
    elements = ", ".join(f"{value}u8" for value in data)
    return f"{'const ' if const else ''}builtin::array<u8, {len(data)}> bytes = {{{elements}}};\n"


def unchanged_source(length):
    return f"""
        i64 source_index = 0;
        while (source_index < {max(1, length)}) {{
            if (bytes[source_index] != u8((source_index * 53 + source_index / 256 * 31 + 7) % 256)) {{
                return 0u64;
            }}
            source_index = source_index + 1;
        }}
    """


def oracle(data, base, requested):
    if not data or len(data) > 4096 or len(data) % 512:
        return "invalid_source", ZERO
    # Search the mathematical absolute addresses instead of reproducing the
    # implementation's subtraction/multiplication preflight.
    for index, start in enumerate(range(0, len(data), 512)):
        if requested >= 0 and requested == base + index:
            return "success", data[start : start + 512]
    return "out_of_range", ZERO


def read_case(length, base, requested, *, offset=0, owner_length=None, const=False):
    owner_length = max(1, length) if owner_length is None else owner_length
    data = pattern(owner_length)[offset : offset + length]
    status, expected = oracle(data, base, requested)
    body = source_array(owner_length, const)
    body += f"const {SPAN} owner_view = borrow_bytes(bytes);\n"
    body += f"const {SPAN} view = owner_view.subspan({offset}, {length});\n"
    body += f"""
        const storage::SectorReadResult report = storage::read_sector_window(view, {base}u64, {requested});
        if (report.status() != storage::SectorIoStatus::{status}) {{
            return 0u64;
        }}
        const storage::Sector512 sector = report.sector_or_zero();
    """
    body += check_sector("sector", expected) + unchanged_source(owner_length) + "return 42u64;"
    return Case(
        f"length={length}, base={base}, request={requested}, offset={offset}, const={const}", body, 42, imports=IMPORTS
    )


def window_cases():
    for count in range(1, 9):
        for index in range(count):
            yield read_case(count * 512, 19, 19 + index, const=count % 2 == 0)
    for length in (0, 1, 511, 513, 1023, 1025, 4095):
        for base, requested in ((0, 0), (MAX_U64, MIN_I64), (MAX_U64, MAX_I64)):
            yield read_case(length, base, requested)
    # A supported endpoint-empty view reaches the length guard at runtime.
    yield read_case(0, MAX_U64, MIN_I64, offset=4096, owner_length=4096)
    # Sector alignment is relative to the window, never its owner's address.
    for offset, length, requested in ((1, 512, 7), (17, 1024, 8), (511, 512, 7), (1, 3584, 13)):
        yield read_case(length, 7, requested, offset=offset, owner_length=4096)
    for base in (0, 1, 1 << 32, MAX_I64 - 7, MAX_I64, 1 << 63, MAX_U64 - 7, MAX_U64):
        requests = {MIN_I64, -1, 0, MAX_I64}
        requests.update(value for value in (base - 1, base, base + 7, base + 8) if 0 <= value <= MAX_I64)
        for requested in sorted(requests):
            yield read_case(4096, base, requested)
    yield read_case(512, 0, 1)
    yield read_case(512, MAX_I64, MAX_I64)


def copy_cases():
    body = source_array(4096)
    body += """
        const storage::SectorReadResult saved = storage::read_sector_window(borrow_bytes(bytes), 73u64, 80);
        const storage::SectorReadResult copied = copy_read(saved);
        if (saved.status() != storage::SectorIoStatus::success || copied.status() != saved.status()) {
            return 0u64;
        }
        i64 index = 0;
        while (index < 4096) {
            bytes[index] = 0u8;
            index = index + 1;
        }
        storage::Sector512 extracted = saved.sector_or_zero();
        extracted.write_byte(0, 0u8);
        extracted.write_byte(511, 0u8);
        const storage::Sector512 retained = copied.sector_or_zero();
        const storage::SectorReadResult reread = storage::read_sector_window(borrow_bytes(bytes), 73u64, 80);
        const storage::Sector512 current = reread.sector_or_zero();
        if (reread.status() != storage::SectorIoStatus::success ||
            size_of(storage::SectorReadResult) != 520 || size_of(storage::Sector512) != 512) {
            return 0u64;
        }
    """
    body += check_sector("retained", pattern(4096)[3584:]) + check_sector("current", ZERO) + "return 42u64;"
    yield Case(
        "retained report and argument/return copies survive complete owner replacement",
        body,
        42,
        imports=IMPORTS,
        prelude="""
        auto copy_read(storage::SectorReadResult value) -> storage::SectorReadResult {
            return value;
        }
    """,
    )
    prelude = "auto local_read() -> storage::SectorReadResult {" + source_array(1024)
    prelude += """
        const storage::SectorReadResult result = storage::read_sector_window(borrow_bytes(bytes), 37u64, 38);
        return result;
    }
    """
    body = """
        const storage::SectorReadResult saved = local_read();
        if (saved.status() != storage::SectorIoStatus::success) { return 0u64; }
        const storage::Sector512 sector = saved.sector_or_zero();
    """
    body += check_sector("sector", pattern(1024)[512:]) + "return 42u64;"
    yield Case("owned report outlives local source array", body, 42, imports=IMPORTS, prelude=prelude)


def rejections():
    prefix = "module test; " + " ".join(f"import {module};" for module in IMPORTS)
    prefix += " auto test() -> u64 { " + source_array(512)
    calls = (
        ("array needs an explicit borrow", "bytes, 0u64, 0"),
        ("base must be u64", "borrow_bytes(bytes), 0, 0"),
        ("request must be i64", "borrow_bytes(bytes), 0u64, 0u64"),
        ("bool is not a base", "borrow_bytes(bytes), false, 0"),
        ("bool is not a request", "borrow_bytes(bytes), 0u64, false"),
    )
    for label, arguments in calls:
        yield Rejection(
            label,
            prefix
            + "const storage::SectorReadResult report = "
            + f"storage::read_sector_window({arguments}); return 0u64; }}",
        )
    yield Rejection(
        "owned sector does not expose a borrowed array",
        prefix
        + "const storage::Sector512 sector = storage::Sector512();"
        + "const builtin::span<const u8> view = borrow_bytes(sector); return 0u64; }",
    )
    yield Rejection(
        "report payload stays private",
        prefix
        + "const storage::SectorReadResult report = storage::read_sector_window("
        + "borrow_bytes(bytes), 0u64, 0);"
        + "const storage::Sector512 leaked = report.payload; return 0u64; }",
    )
    yield Rejection(
        "source array cannot exceed 4096", "module test; auto test() -> u64 {" + source_array(4097) + "return 0u64; }"
    )
    yield Rejection(
        "result is an owned report, not a span",
        prefix
        + "const builtin::span<const u8> leaked = storage::read_sector_window("
        + "borrow_bytes(bytes), 0u64, 0); return 0u64; }",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("compiler", type=Path)
    args = parser.parse_args()
    compiler = args.compiler.resolve(strict=True)
    print(f"compiler_sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()}", flush=True)
    require(oracle(b"", MAX_U64, MIN_I64) == ("invalid_source", ZERO), "empty-source precedence anchor")
    require(oracle(bytes(8192), 0, 0) == ("invalid_source", ZERO), "model oversized-source anchor")
    require(oracle(pattern(512), MAX_I64, MAX_I64) == ("success", pattern(512)), "signed endpoint anchor")
    require(oracle(pattern(4096), MAX_U64, -1) == ("out_of_range", ZERO), "no signed wrapping anchor")
    corpus = list(window_cases()) + list(copy_cases())
    rejected = list(rejections())
    with tempfile.TemporaryDirectory(prefix="aurora-sector-window-") as temporary:
        runner = NativeRunner(Path(temporary), compiler, 20)
        for case in corpus:
            runner.cases([case])
        for case in rejected:
            runner.rejection(case)
    print(f"PASS sector window: {len(corpus)} native cases, {len(rejected)} rejections", flush=True)


if __name__ == "__main__":
    main()
