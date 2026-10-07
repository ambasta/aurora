#!/usr/bin/env python3
"""Focused proof of an owned byte block and copied status-plus-block result."""
from pathlib import Path
import argparse
import hashlib
import tempfile

from unsigned_oracle import Case, NativeRunner, Rejection, require


IMPORTS = ("storage.block",)
CODEC_IMPORTS = ("storage.block", "storage.block_codec", "std.binary_writer")


def initialized_block():
    return """
        storage::Block64 block = storage::Block64();
        i64 initialize = 0;
        while (initialize < 64) {
            if (block.write_byte(initialize, u8(initialize + 128)) != storage::BlockStatus::success) {
                return 0u64;
            }
            initialize = initialize + 1;
        }
    """


def check_bytes(values, name="block"):
    elements = ", ".join(f"{byte}u8" for byte in values)
    return f"""
        const builtin::array<u8, 64> expected = {{{elements}}};
        i64 offset = 0;
        while (offset < 64) {{
            const storage::BlockByteResult byte = {name}.read_byte(offset);
            if (byte.status() != storage::BlockStatus::success) {{
                return 0u64;
            }}
            if (byte.value_or(0u8) != expected[offset]) {{
                return 0u64;
            }}
            offset = offset + 1;
        }}
        return 42u64;
    """


def cases():
    for index in range(64):
        for value in (0, 1, 128, 255):
            expected = bytearray(range(128, 192))
            expected[index] = value
            body = initialized_block() + f"""
                if (block.write_byte({index}, {value}u8) != storage::BlockStatus::success) {{
                    return 0u64;
                }}
            """ + check_bytes(expected)
            yield Case(f"independent byte {index} value {value}", body, 42, imports=IMPORTS)
    for index in (-(1 << 63), -1, 64, (1 << 63) - 1):
        body = initialized_block() + f"""
            if (block.write_byte({index}, 255u8) != storage::BlockStatus::out_of_range) {{
                return 0u64;
            }}
            const storage::BlockByteResult byte = block.read_byte({index});
            if (byte.status() != storage::BlockStatus::out_of_range) {{
                return 0u64;
            }}
            if (byte.value_or(42u8) != 42u8) {{
                return 0u64;
            }}
        """ + check_bytes(range(128, 192))
        yield Case(f"signed boundary {index} preserves all bytes", body, 42, imports=IMPORTS)
    yield Case("zero initialization and physical value sizes", """
        const storage::Block64 block = storage::Block64();
        if (block.size() != 64) {
            return 0u64;
        }
        if (size_of(storage::Block64) != 64) {
            return 0u64;
        }
        if (size_of(storage::BlockReadResult) != 72) {
            return 0u64;
        }
    """ + check_bytes(bytes(64)), 42, imports=IMPORTS)
    yield Case("failed public reports mask nonzero payloads", initialized_block() + """
        const storage::BlockReadResult report = storage::BlockReadResult(storage::BlockStatus::out_of_range, block);
        const storage::Block64 masked = report.block_or_zero();
        const storage::BlockByteResult byte = storage::BlockByteResult(storage::BlockStatus::out_of_range, 255u8);
        if (byte.value_or(42u8) != 42u8) {
            return 0u64;
        }
    """ + check_bytes(bytes(64), "masked"), 42, imports=IMPORTS)
    yield Case("copied result and function boundaries", initialized_block() + """
        const storage::BlockReadResult report = storage::BlockReadResult(storage::BlockStatus::success, block);
        const storage::BlockReadResult copy = identity(report);
        if (copy.status() != storage::BlockStatus::success) {
            return 0u64;
        }
        const storage::Block64 copied = copy.block_or_zero();
    """ + "{" + check_bytes(range(128, 192), "copied").replace("return 42u64;", "") + "}" + """
        block.write_byte(0, 0u8);
        storage::Block64 changed = copy.block_or_zero();
        changed.write_byte(63, 0u8);
        const storage::Block64 saved = report.block_or_zero();
    """ + check_bytes(range(128, 192), "saved"), 42, imports=IMPORTS, prelude="""
        auto identity(storage::BlockReadResult report) -> storage::BlockReadResult {
            return report;
        }
    """)
    expected = bytearray(64)
    expected[0:2] = (4660).to_bytes(2, "big")
    expected[56:64] = ((1 << 63) + 42).to_bytes(8, "little")
    yield Case("writer conversions preserve independent wire bytes", """
        std::BinaryWriter64 writer = std::BinaryWriter64();
        writer.write_be16(0, 4660u64);
        writer.write_le64(56, 9223372036854775850u64);
        storage::Block64 block = storage::block_from_writer(writer);
        writer.write_u8(0, 0u8);
        std::BinaryWriter64 returned = storage::writer_from_block(block);
        if (returned.at(0) != 18u8) {
            return 0u64;
        }
        if (returned.at(1) != 52u8) {
            return 0u64;
        }
        if (returned.at(56) != 42u8) {
            return 0u64;
        }
        if (returned.at(63) != 128u8) {
            return 0u64;
        }
        i64 copy_offset = 2;
        while (copy_offset < 63) {
            if (copy_offset != 56) {
                if (returned.at(copy_offset) != 0u8) {
                    return 0u64;
                }
            }
            copy_offset = copy_offset + 1;
        }
        returned.write_u8(63, 0u8);
    """ + check_bytes(expected), 42, imports=CODEC_IMPORTS)


def rejections():
    prefix = "module test; import storage.block; auto test() -> u64 {"
    prefix += "storage::Block64 block = storage::Block64();"
    bodies = (
        "return block.words[0];",
        "block.write_byte(0, 255u64); return 0u64;",
        "block.read_byte(0u64); return 0u64;",
        "const storage::Block64 frozen = block; frozen.write_byte(0, 1u8); return 0u64;",
    )
    for index, body in enumerate(bodies):
        yield Rejection(f"block privacy/type rejection {index}", prefix + body + "}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("compiler", type=Path)
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    require(compiler.is_file(), "compiler must exist")
    print(f"compiler_sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()}", flush=True)
    corpus = list(cases())
    rejected = list(rejections())
    with tempfile.TemporaryDirectory(prefix="aurora-block-value-") as temporary:
        runner = NativeRunner(Path(temporary), compiler, 10)
        batch = []
        for case in corpus:
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
        for case in rejected:
            runner.rejection(case)
    print(f"PASS owned block value proof: {len(corpus)} native cases, {len(rejected)} rejections", flush=True)


if __name__ == "__main__":
    main()
