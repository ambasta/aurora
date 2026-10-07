#!/usr/bin/env python3
"""Owned sectors and copied record windows against independent complete byte models."""

import argparse
import hashlib
from pathlib import Path
import random
import tempfile

from unsigned_oracle import Case, NativeRunner, Rejection, require


ROOT = Path(__file__).resolve().parents[2]
IMPORTS = ("std.binary", "std.binary_buffer", "storage.sector")
CODECS = IMPORTS
CAPACITY = 512
WINDOW = 64
INITIAL = bytes((index * 37 + index // 256 * 19 + 11) % 256 for index in range(CAPACITY))
INVALID_BYTES = (-(1 << 63), -1, 512, (1 << 63) - 1)
INVALID_WINDOWS = (-(1 << 63), -1, 449, 511, 512, (1 << 63) - 1)


def array(name, values):
    elements = ", ".join(f"{value}u8" for value in values)
    return f"const builtin::array<u8, {len(values)}> {name} = {{{elements}}};"


def initialized_sector():
    return """
        storage::Sector512 sector = storage::Sector512();
        i64 initialize = 0;
        while (initialize < 512) {
            if (sector.write_byte(initialize, u8((initialize * 37 + initialize / 256 * 19 + 11) % 256)) !=
                std::ByteWriteStatus::success) {
                return 0u64;
            }
            initialize = initialize + 1;
        }
    """


def make_record(name, values):
    return (
        array(f"{name}_bytes", values)
        + f"""
        std::BinaryBuffer64 {name} = std::BinaryBuffer64();
        i64 {name}_index = 0;
        while ({name}_index < 64) {{
            if ({name}.write_u8({name}_index, {name}_bytes[{name}_index]) != std::ByteWriteStatus::success) {{
                return 0u64;
            }}
            {name}_index = {name}_index + 1;
        }}
    """
    )


def check_bytes(expected, name="sector"):
    read_method = "read_u8" if len(expected) == WINDOW else "read_byte"
    return (
        array("expected", expected)
        + f"""
        i64 check = 0;
        while (check < {len(expected)}) {{
            const std::ByteReadResult byte = {name}.{read_method}(check);
            if (byte.status() != std::ByteReadStatus::success || u8(byte.value_or(0u64)) != expected[check]) {{
                return 0u64;
            }}
            check = check + 1;
        }}
        return 42u64;
    """
    )


def continue_check(expected, name="sector"):
    return "{" + check_bytes(expected, name).replace("return 42u64;", "") + "}"


def value_cases():
    yield Case(
        "zero initialization and exact sector layout",
        """
        const storage::Sector512 sector = storage::Sector512();
        if (sector.size() != 512 || size_of(storage::Sector512) != 512) {
            return 0u64;
        }
    """
        + check_bytes(bytes(CAPACITY)),
        42,
        imports=IMPORTS,
    )
    yield Case(
        "every byte is independently writable",
        array("original", INITIAL)
        + array("replacement", bytes(255 - value for value in INITIAL))
        + """
        i64 offset = 0;
        while (offset < 512) {
    """
        + initialized_sector()
        + """
            if (sector.write_byte(offset, replacement[offset]) != std::ByteWriteStatus::success) {
                return 0u64;
            }
            i64 index = 0;
            while (index < 512) {
                u8 expected = original[index];
                if (index == offset) {
                    expected = replacement[offset];
                }
                const std::ByteReadResult byte = sector.read_byte(index);
                if (byte.status() != std::ByteReadStatus::success || u8(byte.value_or(0u64)) != expected) {
                    return 0u64;
                }
                index = index + 1;
            }
            offset = offset + 1;
        }
        return 42u64;
    """,
        42,
        imports=IMPORTS,
    )
    for offset in INVALID_BYTES:
        yield Case(
            f"invalid byte {offset} is recoverable and unchanged",
            initialized_sector()
            + f"""
            if (sector.write_byte({offset}, 255u8) != std::ByteWriteStatus::out_of_range) {{
                return 0u64;
            }}
            const std::ByteReadResult failed = sector.read_byte({offset});
            if (failed.status() != std::ByteReadStatus::out_of_range || u8(failed.value_or(42u64)) != 42u8) {{
                return 0u64;
            }}
        """
            + check_bytes(INITIAL),
            42,
            imports=IMPORTS,
        )
    changed = bytearray(INITIAL)
    changed[511] = 255
    original = bytearray(INITIAL)
    original[0] = 0
    yield Case(
        "whole-sector argument and return copies",
        initialized_sector()
        + """
        storage::Sector512 copy = changed_copy(sector);
    """
        + continue_check(INITIAL)
        + continue_check(changed, "copy")
        + """
        sector.write_byte(0, 0u8);
        const storage::Sector512 snapshot = copy;
        copy.write_byte(256, 0u8);
    """
        + continue_check(changed, "snapshot")
        + check_bytes(original),
        42,
        imports=IMPORTS,
        prelude="""
        auto changed_copy(storage::Sector512 input) -> storage::Sector512 {
            storage::Sector512 result = input;
            result.write_byte(511, 255u8);
            return result;
        }
    """,
    )
    yield Case(
        "retained byte result survives overwrite",
        initialized_sector()
        + f"""
        const std::ByteReadResult saved = sector.read_byte(511);
        sector.write_byte(511, 0u8);
        if (saved.status() != std::ByteReadStatus::success) {{
            return 0u64;
        }}
        return saved.value_or(0u64);
    """,
        INITIAL[511],
        imports=IMPORTS,
    )


def window_cases():
    yield Case(
        "every valid window reads all 64 independent bytes",
        initialized_sector()
        + array("original", INITIAL)
        + """
        i64 offset = 0;
        while (offset <= 448) {
            const storage::RecordReadResult report = sector.read_record(offset);
            if (report.status() != std::ByteReadStatus::success) {
                return 0u64;
            }
            const std::BinaryBuffer64 block = report.record_or_zero();
            i64 index = 0;
            while (index < 64) {
                const std::ByteReadResult byte = block.read_u8(index);
                if (byte.status() != std::ByteReadStatus::success ||
                    u8(byte.value_or(0u64)) != original[offset + index]) {
                    return 0u64;
                }
                index = index + 1;
            }
            offset = offset + 1;
        }
        return 42u64;
    """,
        42,
        imports=IMPORTS,
    )
    pattern = bytes((index * 17 + 203) % 256 for index in range(WINDOW))
    yield Case(
        "every valid window write preserves all neighboring bytes",
        array("original", INITIAL)
        + make_record("input", pattern)
        + """
        i64 offset = 0;
        while (offset <= 448) {
    """
        + initialized_sector()
        + """
            if (sector.write_record(offset, input) != std::ByteWriteStatus::success) {
                return 0u64;
            }
            i64 index = 0;
            while (index < 512) {
                u8 expected = original[index];
                if (index >= offset && index < offset + 64) {
                    expected = input_bytes[index - offset];
                }
                const std::ByteReadResult byte = sector.read_byte(index);
                if (byte.status() != std::ByteReadStatus::success || u8(byte.value_or(0u64)) != expected) {
                    return 0u64;
                }
                index = index + 1;
            }
            offset = offset + 1;
        }
        return 42u64;
    """,
        42,
        imports=IMPORTS,
    )
    for offset in INVALID_WINDOWS:
        yield Case(
            f"invalid window {offset} masks the read and preserves all sector bytes",
            initialized_sector()
            + make_record("input", bytes([255]) * WINDOW)
            + f"""
            if (sector.write_record({offset}, input) != std::ByteWriteStatus::out_of_range) {{
                return 0u64;
            }}
            const storage::RecordReadResult failed = sector.read_record({offset});
            if (failed.status() != std::ByteReadStatus::out_of_range) {{
                return 0u64;
            }}
            const std::BinaryBuffer64 masked = failed.record_or_zero();
        """
            + continue_check(bytes(WINDOW), "masked")
            + check_bytes(INITIAL),
            42,
            imports=IMPORTS,
        )
    for offset in (0, 1, 255, 448):
        changed = bytearray(INITIAL)
        changed[offset : offset + WINDOW] = bytes(WINDOW)
        yield Case(
            f"window {offset} report and extracted copies survive sector mutation",
            initialized_sector()
            + f"""
            const storage::RecordReadResult report = sector.read_record({offset});
            const storage::RecordReadResult saved = copy_report(report);
            if (saved.status() != std::ByteReadStatus::success) {{
                return 0u64;
            }}
            const std::BinaryBuffer64 zero = std::BinaryBuffer64();
            sector.write_record({offset}, zero);
            std::BinaryBuffer64 changed = saved.record_or_zero();
            changed.write_u8(0, 0u8);
            changed.write_u8(63, 0u8);
            const std::BinaryBuffer64 snapshot = saved.record_or_zero();
        """
            + continue_check(INITIAL[offset : offset + WINDOW], "snapshot")
            + check_bytes(changed),
            42,
            imports=IMPORTS,
            prelude="""
            auto copy_report(storage::RecordReadResult report) -> storage::RecordReadResult {
                return report;
            }
        """,
        )
    changed = bytearray(INITIAL)
    changed[448:512] = pattern
    yield Case(
        "write takes a complete copied block",
        initialized_sector()
        + make_record("input", pattern)
        + """
        if (sector.write_record(448, input) != std::ByteWriteStatus::success) {
            return 0u64;
        }
        input.write_u8(0, 0u8);
        input.write_u8(63, 0u8);
    """
        + check_bytes(changed),
        42,
        imports=IMPORTS,
    )


def codec_cases():
    for width in (16, 32, 64):
        size = width // 8
        for endian in ("le", "be"):
            for offset in (0, 1, 448):
                value = 0x89ABCDEF01234567 & ((1 << width) - 1)
                encoded = value.to_bytes(size, "little" if endian == "le" else "big")
                model = bytearray(INITIAL)
                model[offset : offset + WINDOW] = bytes(WINDOW)
                model[offset + WINDOW - size : offset + WINDOW] = encoded
                body = (
                    initialized_sector()
                    + f"""
                    std::BinaryBuffer64 writer = std::BinaryBuffer64();
                    if (writer.write_{endian}{width}({WINDOW - size}, {value}u64) !=
                        std::ByteWriteStatus::success) {{
                        return 0u64;
                    }}
                    const std::BinaryBuffer64 block = writer;
                    if (sector.write_record({offset}, block) != std::ByteWriteStatus::success) {{
                        return 0u64;
                    }}
                    writer.write_u8(63, 0u8);
                """
                    + continue_check(model)
                    + f"""
                    const storage::RecordReadResult report = sector.read_record({offset});
                    if (report.status() != std::ByteReadStatus::success) {{
                        return 0u64;
                    }}
                    const std::BinaryBuffer64 snapshot = report.record_or_zero();
                    const std::BinaryBuffer64 returned = snapshot;
                """
                )
                values = ", ".join(f"returned.at({WINDOW - size + index})" for index in range(size))
                body += f"""
                    const builtin::array<u8, {size}> wire = {{{values}}};
                    const std::ByteReadResult decoded = std::read_{endian}{width}(borrow_bytes(wire), 0);
                    if (decoded.status() != std::ByteReadStatus::success) {{
                        return 0u64;
                    }}
                    return decoded.value_or(0u64);
                """
                yield Case(
                    f"{endian}{width} codec at window {offset} with independent wire bytes", body, value, imports=CODECS
                )


def sequence_cases():
    rng = random.Random(51264)
    for sequence in range(4):
        model = bytearray(INITIAL)
        body = initialized_sector()
        for operation in range(12):
            offset = rng.choice((-1, 0, 1, 63, 64, 255, 256, 447, 448, 449, 511, (1 << 63) - 1))
            if operation % 3 == 0:
                value = rng.randrange(256)
                status = "success" if 0 <= offset < CAPACITY else "out_of_range"
                body += f"""
                    if (sector.write_byte({offset}, {value}u8) != std::ByteWriteStatus::{status}) {{
                        return 0u64;
                    }}
                """
                if status == "success":
                    model[offset] = value
            else:
                pattern = bytes(rng.randrange(256) for _ in range(WINDOW))
                status = "success" if 0 <= offset <= CAPACITY - WINDOW else "out_of_range"
                body += (
                    "{"
                    + make_record("input", pattern)
                    + f"""
                    if (sector.write_record({offset}, input) != std::ByteWriteStatus::{status}) {{
                        return 0u64;
                    }}
                """
                    + "}"
                )
                if status == "success":
                    model[offset : offset + WINDOW] = pattern
            # Verify all 512 bytes after each operation, including every failure.
            body += continue_check(model)
        body += "return 42u64;"
        yield Case(f"mixed overlapping writes sequence {sequence}", body, 42, imports=IMPORTS, prelude="\n")



def record_report_cases():
    pattern = bytes((index * 29 + 7) % 256 for index in range(WINDOW))
    for status in ("success", "out_of_range"):
        body = make_record("payload", pattern)
        body += f"""
            const storage::RecordReadResult original = storage::RecordReadResult(
                std::ByteReadStatus::{status}, payload);
            const storage::RecordReadResult report = copy_record_report(original);
            if (size_of(storage::RecordReadResult) != 72 || report.status() != std::ByteReadStatus::{status}) {{
                return 0u64;
            }}
            payload.write_u8(0, 0u8);
            const std::BinaryBuffer64 saved = report.record_or_zero();
        """
        body += check_bytes(pattern if status == "success" else bytes(WINDOW), "saved")
        yield Case(f"record report layout, copying and masking {status}", body, 42, imports=IMPORTS, prelude="""
            auto copy_record_report(storage::RecordReadResult input) -> storage::RecordReadResult {
                return input;
            }
        """)
    body = "storage::Sector512 sector = storage::Sector512();"
    model = bytearray(CAPACITY)
    for position in (0, 64, 128, 192, 64, 0):
        record = bytes((position + index * 11 + 3) % 256 for index in range(WINDOW))
        body += "{" + make_record("record", record) + f"""
            if (sector.write_record({position}, record) != std::ByteWriteStatus::success) {{ return 0u64; }}
        """ + "}"
        model[position:position + WINDOW] = record
        body += continue_check(model)
    body += "return 42u64;"
    yield Case("four records share one sector without changing other records or unused bytes",
               body, 42, imports=IMPORTS)

def rejections():
    prefix = "module test; import std.binary; import std.binary_buffer; import storage.sector; auto test() -> u64 {"
    prefix += "storage::Sector512 sector = storage::Sector512();"
    bodies = (
        "return u64(sector.elements[0]);",
        "sector.elements[511] = 255u8; return 0u64;",
        "const std::ByteReadResult result = sector.read_byte(0u64); return 0u64;",
        "sector.write_byte(0, 255u64); return 0u64;",
        "const storage::RecordReadResult result = sector.read_record(0u64); return 0u64;",
        "sector.write_record(0, sector); return 0u64;",
        "const storage::Sector512 frozen = sector; frozen.write_byte(0, 1u8); return 0u64;",
        "const storage::Sector512 frozen = sector; const std::BinaryBuffer64 block = std::BinaryBuffer64();"
        "frozen.write_record(0, block); return 0u64;",
        "const builtin::span<const u8> leaked = borrow_bytes(sector); return 0u64;",
    )
    for index, body in enumerate(bodies):
        yield Rejection(f"sector privacy/readonly/type rejection {index}", prefix + body + "}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("compiler", type=Path)
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    require(compiler.is_file(), "compiler must exist")
    print(f"compiler_sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()}", flush=True)
    corpus = list(value_cases()) + list(window_cases()) + list(codec_cases())
    corpus += list(sequence_cases()) + list(record_report_cases())
    rejected = list(rejections())
    with tempfile.TemporaryDirectory(prefix="aurora-sector-") as temporary:
        runner = NativeRunner(Path(temporary), compiler, 15)
        batch = []
        for case in corpus:
            if case.prelude:
                if batch:
                    runner.cases(batch)
                    batch = []
                runner.cases([case])
            else:
                batch.append(case)
                if len(batch) == 4:
                    runner.cases(batch)
                    batch = []
        if batch:
            runner.cases(batch)
        for case in rejected:
            runner.rejection(case)
    print(f"PASS owned sector: {len(corpus)} native cases, {len(rejected)} rejections", flush=True)


if __name__ == "__main__":
    main()
