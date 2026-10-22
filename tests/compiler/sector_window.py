#!/usr/bin/env python3
"""Copied sectors from call-scoped readonly windows against complete byte models."""

import argparse
import hashlib
import json
import os
import shlex
import struct
from pathlib import Path
import tempfile

from block_io import check_sector
from unsigned_oracle import Case, NativeRunner, Rejection, ROOT, command, require, validate_values, Observation


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
    source = pattern(owner_length)
    status, expected = oracle(source[offset : offset + length], base, requested)
    scalars = struct.pack(
        "<qqqqqQq",
        owner_length,
        length,
        offset,
        int(const),
        ("success", "invalid_source", "out_of_range").index(status),
        base,
        requested,
    )
    label = f"length={length}, base={base}, request={requested}, offset={offset}, const={const}"
    return label, source.ljust(4096, b"\0") + expected + scalars


WINDOW_DRIVER = """
module sector_window_driver;
import std.binary;
import std.binary_buffer;
import storage.sector;
import storage.block_io;
import storage.sector_window;

class WindowInput {
    builtin::array<u8, 512> bytes0;
    builtin::array<u8, 512> bytes1;
    builtin::array<u8, 512> bytes2;
    builtin::array<u8, 512> bytes3;
    builtin::array<u8, 512> bytes4;
    builtin::array<u8, 512> bytes5;
    builtin::array<u8, 512> bytes6;
    builtin::array<u8, 512> bytes7;
    builtin::array<u8, 512> expected;
    i64 owner_length;
    i64 length;
    i64 offset;
    i64 constant;
    i64 status;
    u64 base;
    i64 requested;
public:
    WindowInput() : bytes0{}, bytes1{}, bytes2{}, bytes3{}, bytes4{}, bytes5{},
                    bytes6{}, bytes7{}, expected{}, owner_length(0), length(0),
                    offset(0), constant(0), status(0), base(0u64), requested(0) {}

    auto is_constant() const -> bool { return constant == 1; }
    auto source_at(i64 index) const -> u8 {
        if (index < 512) { return bytes0[index - 0]; }
        if (index < 1024) { return bytes1[index - 512]; }
        if (index < 1536) { return bytes2[index - 1024]; }
        if (index < 2048) { return bytes3[index - 1536]; }
        if (index < 2560) { return bytes4[index - 2048]; }
        if (index < 3072) { return bytes5[index - 2560]; }
        if (index < 3584) { return bytes6[index - 3072]; }
        return bytes7[index - 3584];
    }
    auto check_window(builtin::span<const u8> source) const -> u64 {
        const builtin::span<const u8> owner = source.subspan(0, owner_length);
        const builtin::span<const u8> view = owner.subspan(offset, length);
        const storage::SectorReadResult report = storage::read_sector_window(view, base, requested);
        if ((status == 0 && report.status() != storage::SectorIoStatus::success)
            || (status == 1 && report.status() != storage::SectorIoStatus::invalid_source)
            || (status == 2 && report.status() != storage::SectorIoStatus::out_of_range)) {
            return 0u64;
        }
        const storage::Sector512 sector = report.sector_or_zero();
        i64 index = 0;
        while (index < 512) {
            const std::ByteReadResult byte = sector.read_byte(index);
            if (byte.status() != std::ByteReadStatus::success
                || u8(byte.value_or(0u64)) != expected[index]) {
                return 0u64;
            }
            index = index + 1;
        }
        index = 0;
        while (index < owner_length) {
            if (source.at(index) != source_at(index)) { return 0u64; }
            index = index + 1;
        }
        return 42u64;
    }

    auto window_entry() const -> u64 {
        SOURCE_ARRAY
        i64 index = 0;
        while (index < 4096) {
            bytes[index] = source_at(index);
            index = index + 1;
        }
        if (is_constant()) {
            const builtin::array<u8, 4096> frozen = bytes;
            return check_window(borrow_bytes(frozen));
        }
        return check_window(borrow_bytes(bytes));
    }
};

"""

# A test-local borrowed receiver bridge. The source constructs every span itself;
# the host supplies only plain byte arrays and scalars checked against ABI facts.
WINDOW_HOST = r"""
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <fstream>
struct Input {
    std::array<std::uint8_t, 4096> bytes;
    std::array<std::uint8_t, 512> expected;
    std::int64_t owner_length, length, offset, constant, status;
    std::uint64_t base;
    std::int64_t requested;
};
static_assert(sizeof(Input) == 4664 && offsetof(Input, owner_length) == 4608);
extern "C" std::uint64_t sector_invoke(const Input *);
int main(int argc, char **argv) {
    if (argc != 2) return 1;
    std::ifstream stream(argv[1], std::ios::binary);
    if (!stream) return 2;
    while (stream.peek() != std::char_traits<char>::eof()) {
        Input input{};
        if (!stream.read(reinterpret_cast<char *>(&input), sizeof(input))) return 3;
        const auto result = sector_invoke(&input);
        if (std::fwrite(&result, sizeof(result), 1, stdout) != 1) return 4;
    }
    return stream.bad() ? 5 : 0;
}
"""


def run_windows(runner, cases):
    directory = runner.directory / "windows"
    directory.mkdir()
    source, assembly, facts = (directory / name for name in ("input.au", "compiled.s", "abi.json"))
    source.write_text(WINDOW_DRIVER.replace("SOURCE_ARRAY", source_array(4096)))
    command(
        [runner.compiler, "--module-root", ROOT / "library", source, "-o", assembly, "--abi-facts", facts],
        timeout=runner.timeout,
    )
    abi = json.loads(facts.read_text())
    entries = [(name, row) for name, row in abi["functions"].items() if row["source_name"] == "window_entry"]
    require(len(entries) == 1, "sector driver entry ABI")
    symbol, row = entries[0]
    records = [(name, value) for name, value in abi["records"].items() if value["source_name"] == "WindowInput"]
    require(len(records) == 1, "sector driver input ABI")
    record_symbol, record = records[0]
    expected_fields = [(f"bytes{index}", index * 512, 512, "u8", 512) for index in range(8)]
    expected_fields += [("expected", 4096, 512, "u8", 512)]
    expected_fields += [
        (name, 4608 + index * 8, 8, kind, 0)
        for index, (name, kind) in enumerate(
            (
                ("owner_length", "i64"),
                ("length", "i64"),
                ("offset", "i64"),
                ("constant", "i64"),
                ("status", "i64"),
                ("base", "u64"),
                ("requested", "i64"),
            )
        )
    ]
    require(
        record["size"] == record["reserved"] == 4664
        and record["alignment"] == 8
        and [
            (field["name"], field["offset"], field["bytes"], field["kind"], field.get("array_length", 0))
            for field in record["fields"]
        ]
        == expected_fields,
        "sector driver borrowed input layout",
    )
    require(
        row["receiver"] == record_symbol
        and not row["receiver_mutable"]
        and row["borrowed_root_count"] == 0
        and row["parameter_bytes"] == 0
        and row["result"] == {"bytes": 8, "kind": "u64"}
        and row["parameters"] == [],
        "sector driver call ABI",
    )
    with assembly.open("a") as stream:
        stream.write(f"\n.text\n.globl sector_invoke\nsector_invoke:\nmovq %rdi, %r10\njmp {symbol}\n")
    host, executable, data = (directory / name for name in ("driver.cpp", "program", "cases.bin"))
    host.write_text(WINDOW_HOST)
    command(
        [
            *shlex.split(os.environ.get("CXX", "g++")),
            "-std=c++23",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            host,
            assembly,
            "-o",
            executable,
        ],
        timeout=30,
    )
    data.write_bytes(b"".join(packet for _, packet in cases))
    result = command([executable, data], timeout=runner.timeout)
    require(not result.stderr, "sector driver produced stderr")
    validate_values(Observation(result.stdout, exit_code=0), [Case(label, "", 42) for label, _ in cases])


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
    windows = list(window_cases())
    copies = list(copy_cases())
    corpus = copies
    rejected = list(rejections())
    with tempfile.TemporaryDirectory(prefix="aurora-sector-window-") as temporary:
        runner = NativeRunner(Path(temporary), compiler, 20)
        run_windows(runner, windows)
        for case in corpus:
            runner.cases([case])
        for case in rejected:
            runner.rejection(case)
    print(
        f"PASS sector window: {len(windows) + len(copies)} native cases in {1 + len(corpus)} programs, "
        f"{len(rejected)} rejections",
        flush=True,
    )


if __name__ == "__main__":
    main()
