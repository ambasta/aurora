#!/usr/bin/env python3
"""Four-record RAM store checked against complete independent Python byte models."""
from pathlib import Path
import argparse
import hashlib
import random
import tempfile

from unsigned_oracle import Case, NativeRunner, Rejection, command, require, validate_values


ROOT = Path(__file__).resolve().parents[2]
IMPORTS = ("storage.block", "storage.ram_blocks")


def initialized_store():
    return """
        storage::RamBlockStore store = storage::RamBlockStore();
        i64 initialize_block = 0;
        while (initialize_block < 4) {
            storage::Block64 initial = storage::Block64();
            i64 initialize_byte = 0;
            while (initialize_byte < 64) {
                initial.write_byte(initialize_byte, u8(initialize_block * 64 + initialize_byte));
                initialize_byte = initialize_byte + 1;
            }
            if (store.write_block(initialize_block, initial) != storage::BlockStatus::success) {
                return 0u64;
            }
            initialize_block = initialize_block + 1;
        }
    """


def make_block(name, values):
    elements = ", ".join(f"{byte}u8" for byte in values)
    return f"""
        const builtin::array<u8, 64> {name}_bytes = {{{elements}}};
        storage::Block64 {name} = storage::Block64();
        i64 {name}_index = 0;
        while ({name}_index < 64) {{
            {name}.write_byte({name}_index, {name}_bytes[{name}_index]);
            {name}_index = {name}_index + 1;
        }}
    """


def check_store(expected, name="store"):
    elements = ", ".join(f"{byte}u8" for block in expected for byte in block)
    return f"""
        const builtin::array<u8, 256> expected = {{{elements}}};
        i64 block_index = 0;
        while (block_index < 4) {{
            const storage::BlockReadResult report = {name}.read_block(block_index);
            if (report.status() != storage::BlockStatus::success) {{
                return 0u64;
            }}
            const storage::Block64 block = report.block_or_zero();
            i64 byte_index = 0;
            while (byte_index < 64) {{
                const storage::BlockByteResult byte = block.read_byte(byte_index);
                if (byte.status() != storage::BlockStatus::success) {{
                    return 0u64;
                }}
                if (byte.value_or(0u8) != expected[block_index * 64 + byte_index]) {{
                    return 0u64;
                }}
                byte_index = byte_index + 1;
            }}
            block_index = block_index + 1;
        }}
        return 42u64;
    """


def continue_check(expected, name="store"):
    return "{" + check_store(expected, name).replace("return 42u64;", "") + "}"


def initial_model():
    return [bytes(range(index * 64, index * 64 + 64)) for index in range(4)]


def cases():
    yield Case("geometry, zero initialization and fixed layout", """
        const storage::RamBlockStore store = storage::RamBlockStore();
        const storage::BlockGeometry geometry = store.geometry();
        if (geometry.block_size_bytes() != 64u64) {
            return 0u64;
        }
        if (geometry.block_count() != 4u64) {
            return 0u64;
        }
        if (size_of(storage::RamBlockStore) != 256) {
            return 0u64;
        }
        if (size_of(storage::BlockGeometry) != 16) {
            return 0u64;
        }
        if (store.flush() != storage::BlockFlushStatus::volatile_complete) {
            return 0u64;
        }
    """ + check_store([bytes(64)] * 4), 42, imports=IMPORTS)
    rng = random.Random(26007)
    patterns = [bytes(64), bytes([255]) * 64, bytes(range(64)), bytes(range(128, 192)),
                bytes([128, 0, 255, 1]) * 16, bytes(rng.randrange(256) for _ in range(64))]
    for index in range(4):
        for pattern_index, pattern in enumerate(patterns):
            model = initial_model()
            model[index] = pattern
            body = initialized_store() + make_block("input", pattern) + f"""
                if (store.write_block({index}, input) != storage::BlockStatus::success) {{
                    return 0u64;
                }}
                input.write_byte(0, 42u8);
            """ + check_store(model)
            yield Case(f"block {index} independent pattern {pattern_index} preserves neighbors",
                       body, 42, imports=IMPORTS)
    for index in (-(1 << 63), -1, 4, (1 << 63) - 1):
        body = initialized_store() + make_block("input", bytes([255]) * 64) + f"""
            if (store.write_block({index}, input) != storage::BlockStatus::out_of_range) {{
                return 0u64;
            }}
            const storage::BlockReadResult failed = store.read_block({index});
            if (failed.status() != storage::BlockStatus::out_of_range) {{
                return 0u64;
            }}
            const storage::Block64 masked = failed.block_or_zero();
            i64 mask_index = 0;
            while (mask_index < 64) {{
                const storage::BlockByteResult byte = masked.read_byte(mask_index);
                if (byte.status() != storage::BlockStatus::success) {{
                    return 0u64;
                }}
                if (byte.value_or(255u8) != 0u8) {{
                    return 0u64;
                }}
                mask_index = mask_index + 1;
            }}
        """ + check_store(initial_model())
        yield Case(f"invalid block {index} masks reads and preserves every record", body, 42, imports=IMPORTS)
    original = initial_model()
    original[1] = bytes(64)
    copied = initial_model()
    copied[2] = bytes([255]) * 64
    body = initialized_store() + """
        storage::RamBlockStore copy = identity(store);
        const storage::Block64 zero = storage::Block64();
        store.write_block(1, zero);
    """ + continue_check(initial_model(), "copy") + make_block("replacement", bytes([255]) * 64) + """
        copy.write_block(2, replacement);
    """ + continue_check(copied, "copy") + check_store(original)
    yield Case("copied store and function result are independent", body, 42, imports=IMPORTS, prelude="""
        auto identity(storage::RamBlockStore store) -> storage::RamBlockStore {
            return store;
        }
    """)
    yield Case("copied read survives overwrite and extracted-copy mutation", initialized_store() + """
        const storage::BlockReadResult saved = store.read_block(2);
        const storage::Block64 zero = storage::Block64();
        store.write_block(2, zero);
        storage::Block64 changed = saved.block_or_zero();
        changed.write_byte(0, 0u8);
        const storage::Block64 original = saved.block_or_zero();
        i64 index = 0;
        while (index < 64) {
            const storage::BlockByteResult byte = original.read_byte(index);
            if (byte.status() != storage::BlockStatus::success) {
                return 0u64;
            }
            if (byte.value_or(0u8) != u8(index + 128)) {
                return 0u64;
            }
            index = index + 1;
        }
        return 42u64;
    """, 42, imports=IMPORTS)
    for sequence in range(8):
        model = initial_model()
        body = initialized_store()
        for operation in range(12):
            if operation % 3 == 2:
                body += """
                    if (store.flush() != storage::BlockFlushStatus::volatile_complete) {
                        return 0u64;
                    }
                """
            else:
                index = rng.choice((-1, 0, 1, 2, 3, 4, (1 << 63) - 1))
                pattern = bytes(rng.randrange(256) for _ in range(64))
                status = "success" if 0 <= index < 4 else "out_of_range"
                body += make_block(f"input_{operation}", pattern)
                body += f"""
                    if (store.write_block({index}, input_{operation}) != storage::BlockStatus::{status}) {{
                        return 0u64;
                    }}
                """
                if status == "success":
                    model[index] = pattern
            # Check the complete independent model immediately after every write
            # or flush, so a later overwrite cannot conceal an earlier defect.
            body += continue_check(model)
        body += "return 42u64;"
        yield Case(f"write/read/volatile-flush sequence {sequence}", body, 42, imports=IMPORTS, prelude="\n")


def rejections():
    prefix = "module test; import storage.block; import storage.ram_blocks; auto test() -> u64 {"
    prefix += "storage::RamBlockStore store = storage::RamBlockStore();"
    bodies = (
        "return store.words[0];",
        "store.read_block(0u64); return 0u64;",
        "store.write_block(0, 1u64); return 0u64;",
        "const storage::RamBlockStore frozen = store; const storage::Block64 block = storage::Block64();"
        "frozen.write_block(0, block); return 0u64;",
        "return u64(storage::BlockFlushStatus::volatile_complete);",
    )
    for index, body in enumerate(bodies):
        yield Rejection(f"RAM API privacy/type rejection {index}", prefix + body + "}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("compiler", type=Path)
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    require(compiler.is_file(), "compiler must exist")
    print(f"compiler_sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()}", flush=True)
    corpus = list(cases())
    rejected = list(rejections())
    with tempfile.TemporaryDirectory(prefix="aurora-ram-blocks-") as temporary:
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
        example = ROOT / "library/examples/ram_record.au"
        assembly = Path(temporary) / "ram-record.s"
        command([compiler, "--module-root", ROOT / "library", example, "-o", assembly])
        observed, _ = runner.assemble(assembly.read_text(), ["main"])
        validate_values(observed, [Case("RAM record example", "", 42, result_type="i64")])
    print(f"PASS RAM block store: {len(corpus)} native cases, {len(rejected)} rejections; example=passed", flush=True)


if __name__ == "__main__":
    main()
