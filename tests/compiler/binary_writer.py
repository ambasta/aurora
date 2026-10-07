#!/usr/bin/env python3
"""Owned writer native checks against independent complete Python byte vectors.

Every recoverable error checks all 64 preexisting bytes. Bounds traps, compile
rejections, copied values and reader interoperation use the existing native oracle.
This is focused library evidence, not a compiler or root aggregate qualification.
"""
from pathlib import Path
import argparse
import hashlib
import random
import tempfile

from packed_values import Trap
from unsigned_oracle import Case, NativeRunner, Rejection, command, require, validate_trap, validate_values


ROOT = Path(__file__).resolve().parents[2]
CAPACITY = 64
MAX_U64 = (1 << 64) - 1
IMPORTS = ("std.binary_writer",)


def initialized_writer():
    return """
        std::BinaryWriter64 writer = std::BinaryWriter64();
        i64 initialize = 0;
        while (initialize < 64) {
            if (writer.write_u8(initialize, u8(initialize + 128)) != std::ByteWriteStatus::success) {
                return 0u64;
            }
            initialize = initialize + 1;
        }
    """


def byte_checks(expected, variable="writer"):
    elements = ", ".join(f"{value}u8" for value in expected)
    return f"""
        const builtin::array<u8, 64> expected = {{{elements}}};
        i64 check = 0;
        while (check < 64) {{
            if ({variable}.at(check) != expected[check]) {{
                return 0u64;
            }}
            check = check + 1;
        }}
        return 42u64;
    """


def modeled_write(model, width, endian, offset, value):
    size = width // 8
    # Offset errors take precedence, including simultaneous input-width errors.
    if offset < 0 or offset > CAPACITY - size:
        return "out_of_range"
    if value >= 1 << width:
        return "value_out_of_range"
    model[offset:offset + size] = value.to_bytes(size, "little" if endian == "le" else "big")
    return "success"


def scalar_cases(seed, count):
    rng = random.Random(seed)
    for width in (16, 32, 64):
        maximum = (1 << width) - 1
        size = width // 8
        values = [0, 1, 1 << (width - 1), maximum, 0x0123456789ABCDEF & maximum]
        values += [rng.randrange(1 << width) for _ in range(count)]
        offsets = (0, 1, 7, CAPACITY - size)
        for endian in ("le", "be"):
            for value in values:
                for offset in offsets:
                    model = bytearray(range(128, 192))
                    status = modeled_write(model, width, endian, offset, value)
                    body = initialized_writer()
                    body += f"""
                        if (writer.write_{endian}{width}({offset}, {value}u64) !=
                            std::ByteWriteStatus::{status}) {{
                            return 0u64;
                        }}
                    """
                    body += byte_checks(model)
                    yield Case(f"{endian}{width} value {value} offset {offset}", body, 42, imports=IMPORTS)
            failures = [(offset, maximum) for offset in (
                -(1 << 63), -1, CAPACITY - size + 1, 63, 64, (1 << 63) - 1)]
            if width < 64:
                failures += [(offset, value) for offset in (-1, 0, CAPACITY - size, CAPACITY, (1 << 63) - 1)
                             for value in (maximum + 1, MAX_U64)]
            for offset, value in failures:
                model = bytearray(range(128, 192))
                status = modeled_write(model, width, endian, offset, value)
                body = initialized_writer()
                body += f"""
                    if (writer.write_{endian}{width}({offset}, {value}u64) != std::ByteWriteStatus::{status}) {{
                        return 0u64;
                    }}
                """
                body += byte_checks(model)
                yield Case(f"unchanged {endian}{width} offset {offset} value {value}", body, 42, imports=IMPORTS)


def sequence_cases(seed):
    rng = random.Random(seed)
    for sequence in range(8):
        model = bytearray(range(128, 192))
        body = initialized_writer()
        for operation in range(20):
            width = rng.choice((16, 32, 64))
            endian = rng.choice(("le", "be"))
            offset = rng.choice((-1, 0, 1, 5, 7, 8, 31, 56, 60, 62, 63, 64))
            value = rng.choice((0, 42, (1 << width) - 1, MAX_U64))
            status = modeled_write(model, width, endian, offset, value)
            body += f"""
                if (writer.write_{endian}{width}({offset}, {value}u64) != std::ByteWriteStatus::{status}) {{
                    return 0u64;
                }}
            """
            if status != "success":
                body += "{" + byte_checks(model).replace("return 42u64;", "") + "}"
        body += byte_checks(model)
        yield Case(f"overlapping sequence {sequence}", body, 42, imports=IMPORTS)


def value_cases():
    yield Case("size, exact representation and zero initialization", """
        const std::BinaryWriter64 writer = std::BinaryWriter64();
        if (writer.size() != 64) {
            return 0u64;
        }
        if (size_of(std::BinaryWriter64) != 64) {
            return 0u64;
        }
    """ + byte_checks(bytes(CAPACITY)), 42, imports=IMPORTS)
    for offset in (-(1 << 63), -1, 0, 63, 64, (1 << 63) - 1):
        for value in (0, 42, 255):
            model = bytearray(range(128, 192))
            status = "success" if 0 <= offset < CAPACITY else "out_of_range"
            if status == "success":
                model[offset] = value
            body = initialized_writer() + f"""
                if (writer.write_u8({offset}, {value}u8) != std::ByteWriteStatus::{status}) {{
                    return 0u64;
                }}
            """ + byte_checks(model)
            yield Case(f"u8 offset {offset} value {value}", body, 42, imports=IMPORTS)
    yield Case("ordinary copied argument and return remain independent", """
        std::BinaryWriter64 original = std::BinaryWriter64();
        original.write_be16(62, 4660u64);
        std::BinaryWriter64 copy = identity(original);
        original.write_u8(62, 255u8);
        copy.write_u8(63, 0u8);
        if (original.at(63) != 52u8) {
            return 0u64;
        }
        if (copy.at(62) != 18u8) {
            return 0u64;
        }
        return 42u64;
    """, 42, imports=IMPORTS, prelude="""
        auto identity(std::BinaryWriter64 writer) -> std::BinaryWriter64 {
            return writer;
        }
    """)
    for width in (16, 32, 64):
        for endian in ("le", "be"):
            value = 0x0123456789ABCDEF & ((1 << width) - 1)
            size = width // 8
            wire = ", ".join(f"writer.at({index + 3})" for index in range(size))
            yield Case(f"readonly reader interoperation {endian}{width}", f"""
                std::BinaryWriter64 writer = std::BinaryWriter64();
                if (writer.write_{endian}{width}(3, {value}u64) != std::ByteWriteStatus::success) {{
                    return 0u64;
                }}
                const builtin::array<u8, {size}> wire = {{{wire}}};
                const std::ByteReadResult report = std::read_{endian}{width}(borrow_bytes(wire), 0);
                if (report.status() != std::ByteReadStatus::success) {{
                    return 0u64;
                }}
                return report.value_or(0u64);
            """, value, imports=IMPORTS + ("std.binary",))


def rejection_cases():
    bodies = [
        "return u64(writer.elements[0]);",
        "writer.elements[0] = 1u8; return 0u64;",
        "const std::BinaryWriter64 frozen = writer; frozen.write_u8(0, 1u8); return 0u64;",
        "const std::BinaryWriter64 frozen = writer; frozen.write_le64(0, 1u64); return 0u64;",
        "writer.write_u8(0, 1u64); return 0u64;",
        "writer.write_le16(0, 1); return 0u64;",
        "writer.write_be32(0u64, 1u64); return 0u64;",
        "return consume(borrow_bytes(writer));",
    ]
    for index, body in enumerate(bodies):
        yield Rejection(f"writer visibility/type rejection {index}",
                        "module test; import std.binary_writer;"
                        "auto consume(builtin::span<const u8> input) -> u64 { return u64(input.size()); }"
                        "auto test() -> u64 {"
                        "std::BinaryWriter64 writer = std::BinaryWriter64();" + body + "}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("compiler", type=Path)
    parser.add_argument("--seed", type=int, default=24024)
    parser.add_argument("--random-count", type=int, default=2)
    args = parser.parse_args()
    require(0 <= args.random_count <= 16, "random-count must be 0..16")
    compiler = args.compiler.resolve()
    print(f"compiler_sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()} seed={args.seed}", flush=True)
    cases = list(value_cases()) + list(scalar_cases(args.seed, args.random_count)) + list(sequence_cases(args.seed))
    rejections = list(rejection_cases())
    with tempfile.TemporaryDirectory(prefix="aurora-binary-writer-") as temporary:
        runner = NativeRunner(Path(temporary), compiler, 10)
        batch = []
        for case in cases:
            if case.prelude:
                if batch:
                    runner.cases(batch)
                    batch = []
                runner.cases([case])
            else:
                batch.append(case)
                if len(batch) == 8:
                    runner.cases(batch)
                    batch = []
        if batch:
            runner.cases(batch)
        for case in rejections:
            runner.rejection(case)
        for offset in (-1, 64, (1 << 63) - 1):
            path = Path(temporary) / "bounds.au"
            output = Path(temporary) / "bounds.s"
            path.write_text("module bounds; import std.binary_writer; auto test() -> u64 {"
                            "const std::BinaryWriter64 writer = std::BinaryWriter64();"
                            f"return u64(writer.at({offset}));" + "}")
            command([compiler, "--module-root", ROOT / "library", path, "-o", output])
            observed, symbols = runner.assemble(output.read_text(), ["test"])
            validate_trap(observed, Trap.BOUNDS, symbols, f"writer read bounds {offset}")
        example = ROOT / "library/examples/binary_writer.au"
        assembly = Path(temporary) / "binary-writer-example.s"
        command([compiler, "--module-root", ROOT / "library", example, "-o", assembly])
        observed, _ = runner.assemble(assembly.read_text(), ["main"])
        validate_values(observed, [Case("binary writer example", "", 42, result_type="i64")])
    print(f"PASS binary writer: {len(cases)} native cases, {len(rejections)} rejections, "
          "3 exact bounds traps; example=passed", flush=True)


if __name__ == "__main__":
    main()
