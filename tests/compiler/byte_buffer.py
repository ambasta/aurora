#!/usr/bin/env python3
"""Hosted ByteBuffer checks using the existing owner bridge and allocation oracle.

Complete byte models cover repeated operations and recoverable failures. Compile
admission can run without linking or executing generated programs. This focused
library gate does not qualify a compiler, kernel or full native aggregate.
"""

from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
from pathlib import Path
import random
import tempfile

from owned_bytes import ROOT, Suite, command
from unsigned_oracle import require

MAX_I64 = (1 << 63) - 1
MIN_I64 = -(1 << 63)
IMPORTS = "import std.binary;\nimport std.byte_buffer;\n"
CREATE = """
    builtin::OwnedBytes allocation = region.try_allocate(n);
    std::ByteBuffer buffer = std::ByteBuffer(region, move(allocation));
"""


def program(body, helpers=""):
    return (
        "module byte_buffer_test;\n"
        + IMPORTS
        + helpers
        + "auto entry(builtin::ByteRegion region, i64 n, i64 flag) -> i64 {\n"
        + body
        + "\n}\n"
    )


class BufferSuite(Suite):
    def __init__(self, compiler, directory, compile_only):
        super().__init__(compiler, directory, ROOT / "library", entry_name="entry")
        self.compile_only = compile_only
        self.skipped_native = 0

    def compile(self, name, source, entry_name=None):
        if not self.compile_only:
            return super().compile(name, source, entry_name)
        folder = self.directory / name
        folder.mkdir()
        input_path = folder / "input.au"
        assembly = folder / "output.s"
        input_path.write_text(source)
        result = command([self.compiler, *self.module_args, input_path, "-o", assembly])
        require(result.returncode == 0, f"{name}: compile failed: {result.stderr.decode()}")
        require(assembly.is_file() and assembly.stat().st_size > 0, f"{name}: missing assembly")
        self.programs += 1
        return folder / "native-not-built"

    def run(self, *args, **kwargs):
        if self.compile_only:
            self.skipped_native += 1
        else:
            super().run(*args, **kwargs)


def check_state(values, capacity, variable="buffer"):
    elements = ", ".join(f"{value}u8" for value in values) if values else "0u8"
    return f"""
    {{
        if (!{variable}.ok() || {variable}.size() != {len(values)} || {variable}.capacity() != {capacity}) {{
            return 0;
        }}
        const builtin::array<u8, {max(1, len(values))}> expected = {{{elements}}};
        i64 index = 0;
        while (index < {len(values)}) {{
            const std::ByteReadResult byte = {variable}.read_u8(index);
            if (byte.status() != std::ByteReadStatus::success || byte.value_or(256u64) != u64(expected[index])) {{
                return 0;
            }}
            index = index + 1;
        }}
        const std::ByteReadResult past = {variable}.read_u8({len(values)});
        if (past.status() != std::ByteReadStatus::out_of_range || past.value_or(256u64) != 256u64) {{
            return 0;
        }}
    }}
    """


def basic_cases(suite):
    failed = suite.compile(
        "failed-owner",
        program(
            CREATE
            + f"""
        if (buffer.ok() || buffer.size() != 0 || buffer.capacity() != 0) {{ return 0; }}
        if (buffer.try_reserve(0) || buffer.try_reserve(1) || buffer.try_append(1u8) ||
            buffer.try_truncate(0) || buffer.clear() || buffer.try_write_u8(0, 1u8)) {{ return 0; }}
        const std::ByteReadResult first = buffer.read_u8(0);
        const std::ByteReadResult negative = buffer.read_u8({MIN_I64});
        if (first.status() != std::ByteReadStatus::out_of_range || first.value_or(99u64) != 99u64 ||
            negative.status() != std::ByteReadStatus::out_of_range) {{ return 0; }}
        return 42;
    """
        ),
    )
    for quota, count, fail_after in ((0, 1, None), (8, -1, None), (8, 0, 0), (8, 8, 0), (8, MAX_I64, None)):
        suite.run(failed, quota, count, 0, 42, 0, 0, fail_after)

    moved_failure = suite.compile(
        "failed-owner-moves",
        program(
            CREATE
            + """
        std::ByteBuffer returned = bounce(region, move(buffer));
        std::ByteBuffer moved = move(returned);
        if (moved.ok() || moved.size() != 0 || moved.capacity() != 0 || moved.try_append(1u8) ||
            moved.try_reserve(0) || moved.try_truncate(0) || moved.clear() || moved.try_write_u8(0, 1u8)) {
            return 0;
        }
        const std::ByteReadResult byte = moved.read_u8(0);
        if (byte.status() != std::ByteReadStatus::out_of_range || byte.value_or(99u64) != 99u64) { return 0; }
        return 42;
        """,
            "auto bounce(builtin::ByteRegion region, std::ByteBuffer input) -> std::ByteBuffer { return move(input); }",
        ),
    )
    suite.run(moved_failure, 0, 1, 0, 42, 0, 0)
    suite.run(moved_failure, 8, 0, 0, 42, 0, 0, fail_after=0)

    empty = suite.compile(
        "valid-empty",
        program(
            CREATE
            + """
        if (!buffer.ok() || buffer.size() != 0 || buffer.capacity() != 0) { return 0; }
        if (!buffer.try_reserve(0) || !buffer.try_truncate(0) || !buffer.clear()) { return 0; }
        if (buffer.try_append(1u8) || buffer.try_write_u8(0, 1u8)) { return 0; }
        const std::ByteReadResult byte = buffer.read_u8(0);
        if (byte.status() != std::ByteReadStatus::out_of_range || byte.value_or(99u64) != 99u64) { return 0; }
        return 42;
    """
        ),
    )
    suite.run(empty, 0, 0, 0, 42, 1, 1)
    suite.run(empty, 8, 0, 0, 42, 1, 1, fail_after=1)

    lifecycle = """
        builtin::OwnedBytes allocation = region.try_allocate(n);
        i64 fill = 0;
        while (fill < n) {
            allocation.set(fill, 231u8);
            fill = fill + 1;
        }
        std::ByteBuffer buffer = std::ByteBuffer(region, move(allocation));
    """
    lifecycle += check_state([], 4)
    lifecycle += """
        if (!buffer.try_reserve(0) || !buffer.try_reserve(4) || !buffer.try_truncate(0) || !buffer.clear()) {
            return 0;
        }
        if (buffer.try_reserve(-1) || buffer.try_write_u8(0, 9u8) || buffer.try_truncate(1)) { return 0; }
        if (!buffer.try_append(1u8) || !buffer.try_append(128u8) || !buffer.try_append(255u8)) { return 0; }
        const std::ByteReadResult saved = buffer.read_u8(0);
        if (!buffer.try_write_u8(0, 42u8) || saved.value_or(256u64) != 1u64) { return 0; }
    """
    lifecycle += check_state([42, 128, 255], 4)
    for offset in (MIN_I64, -1, 3, 4, MAX_I64):
        lifecycle += f"""
        {{
            const std::ByteReadResult byte = buffer.read_u8({offset});
            if (byte.status() != std::ByteReadStatus::out_of_range || byte.value_or(256u64) != 256u64 ||
                buffer.try_write_u8({offset}, 99u8)) {{ return 0; }}
        }}
        """
    for length in (MIN_I64, -1, 4, MAX_I64):
        lifecycle += f"if (buffer.try_truncate({length})) {{ return 0; }}\n"
    lifecycle += check_state([42, 128, 255], 4)
    lifecycle += "if (!buffer.try_truncate(1)) { return 0; }\n"
    lifecycle += check_state([42], 4)
    lifecycle += "if (buffer.try_truncate(3) || !buffer.try_append(7u8)) { return 0; }\n"
    lifecycle += check_state([42, 7], 4)
    lifecycle += "if (!buffer.clear() || !buffer.clear()) { return 0; }\n"
    lifecycle += check_state([], 4)
    lifecycle += "if (!buffer.try_append(9u8)) { return 0; }\n"
    lifecycle += check_state([9], 4) + "return 42;"
    executable = suite.compile("hidden-bytes-and-retained-capacity", program(lifecycle))
    suite.run(executable, 4, 4, 0, 42, 1, 1, fail_after=1)


def growth_cases(suite):
    executable = suite.compile(
        "geometric-growth",
        program("""
        builtin::OwnedBytes allocation = region.try_allocate(0);
        std::ByteBuffer buffer = std::ByteBuffer(region, move(allocation));
        i64 index = 0;
        while (index < n) {
            if (!buffer.try_append(u8(index % 256))) { return 0; }
            index = index + 1;
        }
        if (buffer.size() != n || buffer.capacity() != flag) { return 0; }
        index = 0;
        while (index < n) {
            const std::ByteReadResult byte = buffer.read_u8(index);
            if (byte.status() != std::ByteReadStatus::success || byte.value_or(256u64) != u64(index % 256)) {
                return 0;
            }
            index = index + 1;
        }
        return 42;
    """),
    )
    for count in (0, 1, 2, 3, 8, 9, 65, 513, 4097):
        capacity = 0 if count == 0 else 1 << (count - 1).bit_length()
        allocations = 1 if count == 0 else capacity.bit_length() + 1
        suite.run(executable, capacity, count, capacity, 42, allocations, 1)

    boundary = (
        CREATE
        + """
        if (!buffer.try_append(17u8) || !buffer.try_append(23u8) || buffer.try_append(99u8)) { return 0; }
    """
    )
    boundary += check_state([17, 23], 2)
    boundary += "if (!buffer.try_reserve(3)) { return 0; }\n" + check_state([17, 23], 3)
    boundary += "if (!buffer.try_append(99u8) || buffer.try_append(88u8)) { return 0; }\n"
    boundary += check_state([17, 23, 99], 3) + "return 42;"
    executable = suite.compile("quota-exact-reserve-recovery", program(boundary))
    suite.run(executable, 3, 2, 0, 42, 2, 1, release_order=[1, 2])

    failed = CREATE + "if (!buffer.try_append(17u8) || !buffer.try_append(23u8)) { return 0; }\n"
    failed += f"""
        if (buffer.try_append(99u8) || buffer.try_reserve(3) || buffer.try_reserve({MAX_I64}) ||
            buffer.try_reserve({MIN_I64})) {{ return 0; }}
    """
    failed += check_state([17, 23], 2)
    failed += """
        if (!buffer.try_reserve(2) || !buffer.try_truncate(2) || !buffer.try_truncate(1) ||
            !buffer.try_append(7u8)) { return 0; }
    """
    failed += check_state([17, 7], 2)
    failed += "if (!buffer.clear() || !buffer.try_append(8u8)) { return 0; }\n"
    failed += check_state([8], 2) + "return 42;"
    executable = suite.compile("failure-atomicity-and-allocation-free-reuse", program(failed))
    suite.run(executable, 64, 2, 0, 42, 1, 1, fail_after=1)
    suite.run(executable, 2, 2, 0, 42, 1, 1)

    competition = CREATE + "if (!buffer.try_append(1u8) || !buffer.try_append(2u8)) { return 0; }\n"
    competition += """
        {
            builtin::OwnedBytes blocker = region.try_allocate(2);
            if (!blocker.ok() || buffer.try_append(3u8)) { return 0; }
    """
    competition += check_state([1, 2], 2) + "}\n"
    competition += "if (!buffer.try_append(3u8)) { return 0; }\n"
    competition += check_state([1, 2, 3], 4) + "return 42;"
    executable = suite.compile("shared-quota-recovery", program(competition))
    suite.run(executable, 5, 2, 0, 42, 3, 2, release_order=[2, 1, 3])


def ownership_cases(suite):
    helpers = """
    auto bounce(builtin::ByteRegion region, std::ByteBuffer input) -> std::ByteBuffer {
        if (input.try_append(3u8)) { return move(input); }
        return move(input);
    }
    """
    body = (
        CREATE
        + """
        if (!buffer.try_append(1u8) || !buffer.try_append(2u8)) { return 0; }
        std::ByteBuffer result = bounce(region, move(buffer));
        std::ByteBuffer moved = move(result);
        builtin::OwnedBytes other_allocation = region.try_allocate(1);
        std::ByteBuffer other = std::ByteBuffer(region, move(other_allocation));
        if (!other.try_append(99u8) || !moved.try_write_u8(0, 7u8)) { return 0; }
        const std::ByteBuffer frozen = move(moved);
    """
    )
    body += check_state([7, 2, 3], 4, "frozen") + check_state([99], 1, "other") + "return 42;"
    executable = suite.compile("function-local-const-moves-and-cleanup", program(body, helpers))
    suite.run(executable, 5, 2, 0, 42, 3, 2, release_order=[1, 2, 3])

    loops = """
        i64 iteration = 0;
        while (iteration < n) {
            builtin::OwnedBytes allocation = region.try_allocate(0);
            std::ByteBuffer buffer = std::ByteBuffer(region, move(allocation));
            if (!buffer.try_append(1u8) || !buffer.try_append(2u8) || !buffer.try_append(3u8)) { return 0; }
            if (flag == 1) { return 42; }
            iteration = iteration + 1;
        }
        return 42;
    """
    executable = suite.compile("loop-and-early-return-cleanup", program(loops))
    suite.run(executable, 4, 5, 0, 42, 20, 1)
    suite.run(executable, 4, 5, 1, 42, 4, 1)


def model_cases(suite):
    # Each operation is checked against a complete independent Python byte vector.
    # Keep the model below the existing fixed-array fixture bound, not the API bound.
    for seed, initial, quota, failure_limit in ((7, 0, 31, None), (23, 3, 19, None), (91, 2, 31, 3)):
        rng = random.Random(seed)
        values = bytearray()
        capacity = initial
        allocations = 1
        body = CREATE + check_state(values, capacity)
        operations = ["append"] * 10 + [
            rng.choice(("append", "write", "reserve", "truncate", "clear")) for _ in range(50)
        ]
        for operation in operations:
            if operation == "append":
                value = rng.randrange(256)
                wanted = capacity if len(values) < capacity else max(1, capacity * 2)
                allowed = wanted == capacity or (
                    wanted <= quota and (failure_limit is None or allocations < failure_limit)
                )
                expression = f"buffer.try_append({value}u8)"
                if allowed:
                    if wanted != capacity:
                        allocations += 1
                        capacity = wanted
                    values.append(value)
            elif operation == "write":
                offset = rng.choice((-1, 0, len(values) - 1, len(values), MAX_I64))
                value = rng.randrange(256)
                expression = f"buffer.try_write_u8({offset}, {value}u8)"
                allowed = 0 <= offset < len(values)
                if allowed:
                    values[offset] = value
            elif operation == "reserve":
                wanted = rng.choice((-1, 0, capacity, capacity + 1, 17, 31, MAX_I64))
                expression = f"buffer.try_reserve({wanted})"
                allowed = wanted >= 0 and (
                    wanted <= capacity or (wanted <= quota and (failure_limit is None or allocations < failure_limit))
                )
                if allowed and wanted > capacity:
                    allocations += 1
                    capacity = wanted
            elif operation == "truncate":
                wanted = rng.choice((-1, 0, len(values) // 2, len(values), len(values) + 1, MAX_I64))
                expression = f"buffer.try_truncate({wanted})"
                allowed = 0 <= wanted <= len(values)
                if allowed:
                    del values[wanted:]
            else:
                expression = "buffer.clear()"
                allowed = True
                values.clear()
            body += f"if ({'!' if allowed else ''}{expression}) {{ return 0; }}\n"
            body += check_state(values, capacity)
        executable = suite.compile(f"modeled-sequence-{seed}", program(body + "return 42;"))
        suite.run(executable, quota, initial, 0, 42, allocations, 1, fail_after=failure_limit)


def rejection_cases(suite):
    bodies = {
        "implicit-copy": "std::ByteBuffer copied = buffer;",
        "after-move": "std::ByteBuffer moved = move(buffer); buffer.size();",
        "double-move": "std::ByteBuffer moved = move(buffer); std::ByteBuffer twice = move(buffer);",
        "private-payload": "buffer.payload.try_resize(4);",
        "private-length": "buffer.length = 4;",
        "owner-extraction": "builtin::OwnedBytes escaped = move(buffer.payload);",
        "payload-view": "const builtin::span<const u8> view = borrow_bytes(buffer);",
        "wrong-byte-type": "buffer.try_append(1);",
        "wrong-offset-type": "buffer.read_u8(0u64);",
        "wrong-reserve-type": "buffer.try_reserve(4u64);",
        "wrong-truncate-type": "buffer.try_truncate(0u64);",
        "receiver-consumed-in-argument": "buffer.try_reserve(consume(region, move(buffer)));",
    }
    for operation in ("try_append(1u8)", "try_write_u8(0, 1u8)", "try_reserve(4)", "try_truncate(0)", "clear()"):
        bodies[f"const-{operation.split('(')[0]}"] = f"const std::ByteBuffer frozen = move(buffer); frozen.{operation};"
    helper = "auto consume(builtin::ByteRegion region, std::ByteBuffer input) -> i64 { return input.size(); }\n"
    for name, body in bodies.items():
        suite.reject(name, program(CREATE + body + "return 0;", helper))


def example_cases(suite):
    executable = suite.compile(
        "example", (ROOT / "library/examples/byte_buffer.au").read_text(), entry_name="byte_buffer_example"
    )
    for initial, count in ((0, 0), (0, 65), (3, 3), (8, 3), (2, 513)):
        allocations = 1 + int(count > initial)
        suite.run(
            executable,
            max(initial, count),
            initial,
            count,
            sum(index % 256 for index in range(count)) % 65536,
            allocations,
            1,
        )
    suite.run(executable, 2, 2, 3, -2, 1, 1)
    suite.run(executable, 0, 1, 1, -1, 0, 0)
    suite.run(executable, 0, 0, -1, -1, 1, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    parser.add_argument("--compile-only", action="store_true")
    parser.add_argument("--artifacts", type=Path, help="retain this run in a new directory")
    args = parser.parse_args()
    compiler = args.compiler.resolve(strict=True)
    if args.artifacts is not None:
        args.artifacts.mkdir(parents=True, exist_ok=False)
    context = (
        tempfile.TemporaryDirectory(prefix="aurora-byte-buffer-")
        if args.artifacts is None
        else nullcontext(args.artifacts)
    )
    with context as temporary:
        suite = BufferSuite(compiler, Path(temporary), args.compile_only)
        basic_cases(suite)
        growth_cases(suite)
        ownership_cases(suite)
        model_cases(suite)
        rejection_cases(suite)
        example_cases(suite)
        print(
            f"PASS byte buffer: {suite.programs} programs, {suite.native} native cases, "
            f"{suite.rejections} rejections, {suite.skipped_native} native cases skipped"
        )
        print(f"compiler_sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
