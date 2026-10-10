#!/usr/bin/env python3
"""Focused method readonly-span ABI, lifetime and bulk append hosted tests."""

from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
import random
from pathlib import Path
import tempfile

from byte_buffer import BufferSuite, CREATE, check_state, program
from owned_bytes import command
from unsigned_oracle import require

SPAN = "builtin::span<const u8>"
ARRAY = "const builtin::array<u8, 3> data = {7u8, 128u8, 255u8};"
VIEW = f"const {SPAN} input = borrow_bytes(data);"


def append_cases(suite):
    literal_body = (
        CREATE
        + r"""
        if (!buffer.try_append_bytes("") || !buffer.try_append_bytes("\0\xffZ")) { return 0; }
        if (!std::equal(buffer.bytes(), "\0\xffZ") || !std::starts_with(buffer.bytes(), "\0")) { return 0; }
        if (!buffer.try_truncate(0)) { return 0; }
        return 42;
    """
    )
    exe = suite.compile("immutable-literal-with-runtime-owner", program(literal_body, "import std.bytes;"))
    suite.run(exe, 3, 3, 0, 42, 1, 1)

    body = CREATE + ARRAY + VIEW
    body += "if (!buffer.try_append_bytes(input)) { return 0; }"
    body += "if (buffer.size() != 3 || buffer.capacity() != flag) { return 0; }"
    body += check_state([7, 128, 255], "flag")
    body += "if (!buffer.try_append_bytes(input.subspan(1, 0))) { return 0; }"
    body += check_state([7, 128, 255], "flag") + "return 42;"
    exe = suite.compile("array-growth-and-empty", program(body))
    for initial, capacity, allocations in ((0, 3, 2), (1, 3, 2), (2, 4, 2), (3, 3, 1), (9, 9, 1)):
        suite.run(exe, capacity, initial, capacity, 42, allocations, 1)
    suite.run(exe, 9, 9, 9, 42, 1, 1, fail_after=1)

    exe = suite.compile(
        "empty-valid-invalid",
        program(
            CREATE
            + ARRAY
            + VIEW
            + """
        const bool result = buffer.try_append_bytes(input.subspan(0, 0));
        if (result != buffer.ok() || buffer.size() != 0 || buffer.capacity() != flag) { return 0; }
        return 42;
    """
        ),
    )
    suite.run(exe, 0, 0, 0, 42, 1, 1, fail_after=1)
    suite.run(exe, 8, 8, 8, 42, 1, 1, fail_after=1)
    suite.run(exe, 0, 1, 0, 42, 0, 0)
    suite.run(exe, 8, 0, 0, 42, 0, 0, fail_after=0)

    body = CREATE + ARRAY + VIEW + "if (!buffer.try_append(11u8) || !buffer.try_append(22u8)) { return 0; }"
    body += "if (buffer.try_append_bytes(input)) { return 0; }" + check_state([11, 22], 2)
    body += "if (!buffer.try_append_bytes(input.subspan(0, 0))) { return 0; }"
    body += "if (!buffer.try_truncate(1) || !buffer.try_append_bytes(input.subspan(2, 1))) { return 0; }"
    body += check_state([11, 255], 2) + "return 42;"
    exe = suite.compile("failure-atomic-complete-prefix", program(body))
    suite.run(exe, 4, 2, 0, 42, 1, 1)
    suite.run(exe, 99, 2, 0, 42, 1, 1, fail_after=1)

    body = CREATE + ARRAY + VIEW + "if (!buffer.try_append_bytes(input.subspan(0, 2))) { return 0; }"
    body += "if (buffer.try_append_bytes(input.subspan(2, 1))) { return 0; }" + check_state([7, 128], 2)
    body += "if (!buffer.try_reserve(3) || !buffer.try_append_bytes(input.subspan(2, 1))) { return 0; }"
    body += check_state([7, 128, 255], 3) + "return 42;"
    exe = suite.compile("no-exact-growth-fallback", program(body))
    suite.run(exe, 3, 2, 0, 42, 2, 1, release_order=[1, 2])

    exe = suite.compile(
        "runtime-owner-over-4096",
        program("""
        builtin::OwnedBytes source = region.try_allocate(n);
        i64 index = 0;
        while (index < n) { source.set(index, u8(index % 256)); index = index + 1; }
        builtin::OwnedBytes allocation = region.try_allocate(0);
        std::ByteBuffer buffer = std::ByteBuffer(region, move(allocation));
        if (!buffer.try_append_bytes(borrow_bytes(source))) { return 0; }
        if (buffer.size() != n || buffer.capacity() != n) { return 0; }
        index = 0;
        while (index < n) {
            const std::ByteReadResult byte = buffer.read_u8(index);
            if (byte.value_or(256u64) != u64(index % 256) || source.at(index) != u8(index % 256)) { return 0; }
            index = index + 1;
        }
        source.set(0, 99u8);
        return 42;
    """),
    )
    for count in (1, 4097, 8193):
        suite.run(exe, count * 2, count, 0, 42, 3, 2, release_order=[2, 3, 1])

    body = CREATE + ARRAY + VIEW + "if (!buffer.try_append_bytes(input)) { return 0; }"
    body += """
        builtin::OwnedBytes other_allocation = region.try_allocate(0);
        std::ByteBuffer other = std::ByteBuffer(region, move(other_allocation));
        if (!other.try_append_bytes(buffer.bytes().subspan(1, 2))) { return 0; }
        if (!other.try_append_bytes(buffer.bytes())) { return 0; }
        if (!buffer.clear()) { return 0; }
        std::ByteBuffer moved = move(other);
    """
    body += check_state([128, 255, 7, 128, 255], 5, "moved") + "return 42;"
    exe = suite.compile("other-buffer-temporary-views-move", program(body))
    suite.run(exe, 8, 3, 0, 42, 4, 2, release_order=[2, 3, 4, 1])


HELPERS = f"""
class Value {{
    i64 number;
public:
    Value(i64 input) : number(input) {{}}
    auto get() const -> i64 {{ return number; }}
}};
class Reader {{
    builtin::OwnedBytes payload;
public:
    Reader(builtin::ByteRegion region, builtin::OwnedBytes input) : payload(move(input)) {{}}
    auto bytes() const -> {SPAN} {{ return borrow_bytes(payload); }}
    auto measure(i64 before, {SPAN} first, Value copied, {SPAN} second, i64 after) const -> Value {{
        const Value result = Value(before + first.size() + copied.get() + second.size() + after +
                                   i64(first.at(0)) + i64(second.at(0)));
        return result;
    }}
    auto forward({SPAN} input) const -> Value {{
        const Value amount = Value(3);
        const Value result = measure(1, input, amount, input, 2);
        return result;
    }}
    auto window({SPAN} input, Value offset, i64 count) const -> {SPAN} {{
        input.size();
        return borrow_bytes(payload).subspan(offset.get(), count);
    }}
    auto order(bool changed, {SPAN} input) const -> i64 {{
        if (!changed) {{ return -1; }}
        return i64(input.at(0));
    }}
    auto later({SPAN} input, bool changed) const -> i64 {{ return input.size(); }}
}};
"""
READER = (
    "builtin::OwnedBytes backing = region.try_allocate(3); backing.set(0, 10u8); backing.set(1, 20u8); "
    "Reader reader = Reader(region, move(backing));"
)


def method_cases(suite):
    exe = suite.compile(
        "mixed-method-records-and-self-aliases",
        program(
            READER
            + f"""
        const {SPAN} first = reader.bytes();
        const {SPAN} second = first;
        const Value amount = Value(3);
        const Value result = reader.measure(1, first, amount, second, 2);
        const Value forwarded = reader.forward(reader.bytes());
        if (result.get() != 32 || forwarded.get() != 32) {{ return 0; }}
        const Value offset = Value(1);
        const {SPAN} window = reader.window(reader.bytes(), offset, 1);
        if (window.size() != 1 || window.at(0) != 20u8) {{ return 0; }}
        return 42;
    """,
            HELPERS,
        ),
    )
    suite.run(exe, 3, 0, 0, 42, 1, 1)
    exe = suite.compile(
        "method-argument-order-and-release",
        program(
            READER
            + """
        builtin::OwnedBytes source = region.try_allocate(1);
        if (reader.order(source.set(0, 42u8), borrow_bytes(source)) != 42) { return 0; }
        source.set(0, 17u8);
        builtin::OwnedBytes moved = move(source);
        if (moved.at(0) != 17u8) { return 0; }
        return 42;
    """,
            HELPERS,
        ),
    )
    suite.run(exe, 4, 0, 0, 42, 2, 2, release_order=[2, 1])

    exe = suite.compile(
        "result-retains-only-receiver",
        program(
            READER
            + f"""
        builtin::OwnedBytes source = region.try_allocate(1);
        source.set(0, 99u8);
        const Value offset = Value(1);
        const {SPAN} result = reader.window(borrow_bytes(source), offset, 1);
        if (!source.try_resize(2) || !source.set(0, 7u8)) {{ return 0; }}
        builtin::OwnedBytes moved = move(source);
        if (result.size() != 1 || result.at(0) != 20u8 || moved.at(0) != 7u8) {{ return 0; }}
        return 42;
    """,
            HELPERS,
        ),
    )
    suite.run(exe, 5, 0, 0, 42, 3, 2, release_order=[2, 3, 1])


def modeled_cases(suite):
    for seed, initial, quota, fail_after in ((3, 0, 31, None), (19, 2, 17, None), (71, 3, 41, 3)):
        rng = random.Random(seed)
        values = []
        capacity = initial
        allocations = 1
        body = CREATE + ARRAY + VIEW
        for _ in range(48):
            if rng.randrange(5) == 0:
                length = rng.randrange(len(values) + 1)
                body += f"if (!buffer.try_truncate({length})) {{ return 0; }}"
                values = values[:length]
            else:
                count = rng.randrange(4)
                required = len(values) + count
                target = capacity if required <= capacity else max(required, max(1, capacity * 2))
                success = target == capacity or (target <= quota and (fail_after is None or allocations < fail_after))
                body += (
                    f"if ({'!' if success else ''}buffer.try_append_bytes(input.subspan(0, {count}))) {{ return 0; }}"
                )
                if success:
                    values += [7, 128, 255][:count]
                    if target != capacity:
                        allocations += 1
                        capacity = target
            body += check_state(values, capacity)
        exe = suite.compile(f"bulk-model-{seed}", program(body + "return 42;"))
        suite.run(exe, quota, initial, 0, 42, allocations, 1, fail_after=fail_after)


def reject(suite, name, source, diagnostic):
    folder = suite.directory / ("reject-" + name)
    folder.mkdir()
    path = folder / "input.au"
    path.write_text(source)
    output = folder / "output.s"
    for prior in (None, b"preserve prior assembly\n"):
        if prior is not None:
            output.write_bytes(prior)
        result = command([suite.compiler, *suite.module_args, path, "-o", output])
        (folder / "stderr.txt").write_bytes(result.stderr)
        require(result.returncode == 1, f"{name}: expected exit 1: {result.stderr!r}")
        require(diagnostic in result.stderr.decode(), f"{name}: expected {diagnostic!r}: {result.stderr.decode()}")
        require(not output.exists() if prior is None else output.read_bytes() == prior, f"{name}: modified output")
    suite.rejections += 1


def rejection_cases(suite):
    frozen = "cannot mutate or move an owner while a readonly span is live"
    for name, body in {
        "self-append": "buffer.try_append_bytes(buffer.bytes());",
        "empty-self-append": "buffer.try_append_bytes(buffer.bytes().subspan(0, 0));",
        "named-self-append": f"const {SPAN} input = buffer.bytes(); buffer.try_append_bytes(input);",
        "descendant-freezes-root": (
            f"const {SPAN} input = buffer.bytes(); const {SPAN} child = input.subspan(0, 0); buffer.clear();"
        ),
        "borrowed-root-move": f"const {SPAN} input = buffer.bytes(); std::ByteBuffer moved = move(buffer);",
    }.items():
        reject(suite, name, program(CREATE + body + "return 0;"), frozen)
    reject(
        suite,
        "later-owner-mutation",
        program(
            READER + "builtin::OwnedBytes source = region.try_allocate(1); "
            "return reader.later(borrow_bytes(source), source.set(0, 1u8));",
            HELPERS,
        ),
        frozen,
    )
    reject(
        suite,
        "const-destination",
        program(
            CREATE
            + ARRAY
            + VIEW
            + "const std::ByteBuffer frozen = move(buffer); frozen.try_append_bytes(input); return 0;"
        ),
        "mutable method requires a mutable receiver",
    )
    reject(
        suite,
        "wrong-argument",
        program(CREATE + "buffer.try_append_bytes(1); return 0;"),
        "span initializer requires borrow_bytes, a live span or its subspan",
    )
    reject(
        suite,
        "constructor-span",
        program("return 0;", f"class Bad {{ public: Bad({SPAN} input) {{}} }};"),
        "only scalar, enum or class constructor parameters are supported",
    )
    consume = "auto consume(builtin::ByteRegion region, builtin::OwnedBytes input) -> bool { return input.ok(); }"
    reject(
        suite,
        "later-owner-move",
        program(
            READER + "builtin::OwnedBytes source = region.try_allocate(1); "
            "return reader.later(borrow_bytes(source), consume(region, move(source)));",
            HELPERS + consume,
        ),
        frozen,
    )
    reject(
        suite,
        "later-receiver-move",
        program(
            READER + "return reader.later(reader.bytes(), consume_reader(region, move(reader)));",
            HELPERS + "auto consume_reader(builtin::ByteRegion region, Reader input) -> bool { return true; }",
        ),
        frozen,
    )
    reject(
        suite,
        "return-parameter",
        program(
            "return 0;", HELPERS.replace("return borrow_bytes(payload).subspan(offset.get(), count);", "return input;")
        ),
        "returned span must derive directly",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    parser.add_argument("--compile-only", action="store_true")
    parser.add_argument("--artifacts", type=Path)
    args = parser.parse_args()
    compiler = args.compiler.resolve(strict=True)
    before = hashlib.sha256(compiler.read_bytes()).hexdigest()
    if args.artifacts is not None:
        args.artifacts.mkdir(parents=True, exist_ok=False)
    context = (
        tempfile.TemporaryDirectory(prefix="aurora-method-spans-")
        if args.artifacts is None
        else nullcontext(args.artifacts)
    )
    with context as temporary:
        suite = BufferSuite(compiler, Path(temporary), args.compile_only)
        append_cases(suite)
        method_cases(suite)
        modeled_cases(suite)
        rejection_cases(suite)
        require(hashlib.sha256(compiler.read_bytes()).hexdigest() == before, "compiler changed during gate")
        print(
            f"PASS method spans: {suite.programs} programs, {suite.native} native cases, "
            f"{suite.rejections} rejections, {suite.skipped_native} native cases skipped"
        )
        print(f"compiler_sha256={before}")


if __name__ == "__main__":
    main()
