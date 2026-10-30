#!/usr/bin/env python3
"""Bounded synchronous owning-object borrow source and real hosted-runtime gate.

The library helper uses the existing JSON scalar codec and one bulk append. This
suite checks complete bytes, returned copied observations, allocation identities,
normal cleanup and clean output-preserving rejection. It is not a general borrow
checker, fail-stop unwinder, kernel gate or proof of memory safety. All assertions
use require(), including under Python -O. Failed artifacts are always retained.

The default full profile runs every fixture. --smoke selects two real native
programs and seven named safety rejections for developer feedback. All selected
programs share one packed native binary (owned_bytes.Suite, deferred).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

from byte_buffer import BufferSuite, CREATE, check_state, program
from native_runner import require
import owned_bytes

SPAN = "builtin::span<const u8>"
PRESERVED = b"previous verified assembly\x00\xff\n"
SMOKE_PROGRAMS = (
    "forwarding-and-independent-result",
    "json-forwarded-borrow-copied-result",
)
SMOKE_REJECTIONS = (
    "mutable-later-mutation",
    "named-empty-self-span",
    "shared-later-mutation",
    "const-owner-escalation",
    "formal-move-to-local",
    "borrowed-span-result",
    "json-writer-later-read-of-output",
)
HELPERS = f"""
class Count {{
    i64 value;
public:
    Count(i64 input) : value(input) {{}}
    auto get() const -> i64 {{ return value; }}
}};
auto inspect(const std::ByteBuffer& input) -> i64 {{ return input.size(); }}
auto forward_read(const std::ByteBuffer& input) -> i64 {{ return inspect(input); }}
auto measure_view(const std::ByteBuffer& input) -> i64 {{
    const {SPAN} view = input.bytes();
    return view.size();
}}
auto append_one(std::ByteBuffer& output, u8 value) -> bool {{ return output.try_append(value); }}
auto forward_write(std::ByteBuffer& output, u8 value) -> bool {{
    const i64 before = inspect(output);
    if (!append_one(output, value)) {{ return false; }}
    return forward_read(output) == before + 1;
}}
auto snapshot(const std::ByteBuffer& input, i64 offset) -> std::ByteReadResult {{
    const std::ByteReadResult result = input.read_u8(offset);
    return result;
}}
auto append_window(std::ByteBuffer& output, i64 before, {SPAN} input, Count copied, i64 after) -> Count {{
    if (!output.try_append_bytes(input)) {{
        const Count failed = Count(-1);
        return failed;
    }}
    const Count result = Count(before + copied.get() + after + output.size());
    return result;
}}
auto shared_window(const std::ByteBuffer& input, {SPAN} view, i64 extra) -> Count {{
    const Count result = Count(input.size() + view.size() + extra);
    return result;
}}
auto shared_argument(const std::ByteBuffer& input, i64 extra) -> i64 {{
    return input.size() + extra;
}}
auto shared_after(const std::ByteBuffer& input, bool changed) -> i64 {{
    if (!changed) {{ return -1; }}
    return input.size();
}}
auto append_after(std::ByteBuffer& output, bool changed) -> bool {{
    if (!changed) {{ return false; }}
    return output.try_append(65u8);
}}
auto consume(builtin::ByteRegion region, std::ByteBuffer input) -> i64 {{ return input.size(); }}
"""


class BorrowCases(BufferSuite):
    """The --smoke profile keeps only the named programs and rejections."""

    def __init__(self, compiler, directory, smoke=False):
        super().__init__(compiler, directory, deferred=True)
        self.smoke = smoke

    def select_program(self, name):
        return not self.smoke or name in SMOKE_PROGRAMS

    def compile(self, name, source, entry_name=None, **options):
        return super().compile(name, source, entry_name, **options) if self.select_program(name) else None

    def run(self, executable, *arguments, **options):
        if executable is not None:
            super().run(executable, *arguments, **options)

    def reject(self, name, source, diagnostic=None):
        if not self.smoke or name in SMOKE_REJECTIONS:
            super().reject(name, source, diagnostic or True)


def plain_borrowing_cases(suite):
    helpers = (
        HELPERS
        + """
class PlainCounter {
    i64 value;
public:
    PlainCounter(i64 initial) : value(initial) {}
    auto get() const -> i64 { return value; }
    auto add(i64 amount) -> bool { value = value + amount; return true; }
    auto snapshot() const -> Count { const Count result = Count(value); return result; }
};
auto plain_read(const PlainCounter& value) -> i64 { return value.get(); }
auto plain_add(PlainCounter& value, i64 amount) -> bool { return value.add(amount); }
auto plain_forward(PlainCounter& value, i64 amount) -> i64 {
    const i64 before = plain_read(value);
    if (!plain_add(value, amount)) { return -1; }
    return plain_read(value) - before;
}
auto plain_snapshot(const PlainCounter& value) -> Count {
    const Count result = value.snapshot(); return result;
}
auto plain_tail(PlainCounter& value, i64 amount) -> i64 { value.add(amount); return value.get(); }
auto plain_shared(const PlainCounter& value, i64 other) -> i64 { return value.get() + other; }
auto plain_copy_value(PlainCounter value) -> i64 { return value.get(); }
auto count_reference(const Count& value) -> i64 { return value.get(); }
class PlainNested {
public:
    Count inner;
    PlainNested(Count value) : inner(value) {}
    auto get() const -> i64 { return inner.get(); }
};
auto nested_read(const PlainNested& value) -> i64 { return value.get(); }
"""
    )
    body = """
PlainCounter first = PlainCounter(10);
PlainCounter second = PlainCounter(20);
i64 at = 0;
while (at < 3) {
    if (plain_forward(first, 1) != 1) { return 0; }
    at = at + 1;
}
if (flag == 0) { plain_add(second, 9); } else { plain_forward(second, 9); }
const PlainCounter copied = first;
const Count snapshot = plain_snapshot(first);
if (plain_shared(first, plain_read(first)) != 26 || count_reference(snapshot) != 13) { return 0; }
if (plain_copy_value(copied) != 13) { return 0; }
const PlainNested nested = PlainNested(snapshot);
if (nested_read(nested) != 13) { return 0; }
return plain_read(first) + plain_read(second);
"""
    exe = suite.compile("plain-complete-roots-and-forwarding", program(body, helpers))
    suite.run(exe, 0, 0, 0, 42, 0, 0)
    suite.run(exe, 0, 1, 0, 42, 0, 0)
    declarations = {
        "plain-multiple-roots": "auto bad(PlainCounter& first,const PlainCounter& second)->i64{return 0;}",
        "plain-mixed-owning-roots": "auto bad(std::ByteBuffer& first,PlainCounter& second)->i64{return 0;}",
        "plain-mixed-service": "auto bad(PlainCounter& first,builtin::ConsoleSession& second)->i64{return 0;}",
        "plain-region-tail": "auto bad(PlainCounter& first,builtin::ByteRegion region)->i64{return 0;}",
        "plain-formal-copy": (
            "auto bad(const PlainCounter& value)->i64{const PlainCounter copy=value;return copy.get();}"
        ),
        "plain-formal-value-argument": "auto bad(const PlainCounter& value)->i64{return plain_copy_value(value);}",
        "plain-formal-return": "auto bad(const PlainCounter& value)->PlainCounter{return value;}",
        "plain-formal-rebind": "auto bad(PlainCounter& value)->i64{value=PlainCounter(1);return 0;}",
        "plain-formal-move": "auto bad(PlainCounter& value)->PlainCounter{return move(value);}",
        "plain-formal-private-read": "auto bad(const PlainCounter& value)->i64{return value.value;}",
        "plain-formal-const-escalation": "auto bad(const PlainCounter& value)->bool{return plain_add(value,1);}",
    }
    for name, declaration in declarations.items():
        suite.reject(name, program("return 0;", helpers + declaration))
    bodies = {
        "plain-frozen-later-read": "plain_tail(value, value.get());",
        "plain-frozen-later-copy": "plain_tail(value, plain_copy_value(value));",
        "plain-shared-later-mutation": "plain_shared(value, plain_forward(value,1));",
        "plain-temporary-root": "plain_read(PlainCounter(1));",
        "plain-projected-root": (
            "const Count count=Count(1);PlainNested nested=PlainNested(count);count_reference(nested.inner);"
        ),
        "plain-wrong-nominal": "const Count other=Count(1);plain_read(other);",
        "plain-incomplete-root": "PlainCounter missing;plain_read(missing);",
        "plain-const-local-mutation": "const PlainCounter frozen=PlainCounter(1);plain_add(frozen,1);",
    }
    for name, rejected in bodies.items():
        suite.reject(name, program("PlainCounter value=PlainCounter(1);" + rejected + "return 0;", helpers))


def borrowing_cases(suite):
    body = (
        CREATE
        + """
        if (!forward_write(buffer, 17u8) || !append_one(buffer, 29u8)) { return 0; }
        if (forward_read(buffer) != 2 || inspect(buffer) != 2) { return 0; }
        const std::ByteReadResult saved = snapshot(buffer, 0);
        if (!buffer.try_write_u8(0, 91u8) || !buffer.clear()) { return 0; }
        std::ByteBuffer moved = move(buffer);
        if (!append_one(moved, 7u8)) { return 0; }
        const std::ByteBuffer frozen = move(moved);
        if (forward_read(frozen) != 1 || saved.value_or(256u64) != 17u64) { return 0; }
    """
    )
    body += check_state([7], 4, "frozen") + "return 42;"
    exe = suite.compile("forwarding-and-independent-result", program(body, HELPERS))
    suite.run(exe, 4, 4, 0, 42, 1, 1, release_order=[1])

    shadow_helpers = """
    auto copied_shadow(std::ByteBuffer& input) -> u64 {
        const std::ByteReadResult input = snapshot(input, 0);
        return input.value_or(256u64);
    }
    auto scalar_shadow(std::ByteBuffer& input) -> i64 {
        const i64 input = inspect(input);
        return input;
    }
    auto method_shadow(std::ByteBuffer& input) -> i64 {
        const i64 input = input.size();
        return input;
    }
    auto forward_self_view(std::ByteBuffer& input) -> i64 {
        const Count result = shared_window(input, input.bytes(), inspect(input));
        if (!input.try_write_u8(0, 21u8)) { return -1; }
        return result.get();
    }
    """
    body = (
        CREATE
        + f"""
        if (!append_one(buffer, 7u8) || !append_one(buffer, 8u8)) {{ return 0; }}
        {{
            const {SPAN} view = buffer.bytes();
            const Count result = shared_window(buffer, view, inspect(buffer));
            const Count temporary = shared_window(buffer, buffer.bytes().subspan(1, 1), forward_read(buffer));
            if (result.get() != 6 || temporary.get() != 5 || shared_argument(buffer, inspect(buffer)) != 4) {{
                return 0;
            }}
        }}
        if (copied_shadow(buffer) != 7u64 || scalar_shadow(buffer) != 2 || method_shadow(buffer) != 2 ||
            forward_self_view(buffer) != 6) {{ return 0; }}
    """
    )
    body += check_state([21, 8], 2) + "return 42;"
    exe = suite.compile("shared-root-allows-readonly-aliases", program(body, HELPERS + shadow_helpers))
    suite.run(exe, 2, 2, 0, 42, 1, 1)

    body = (
        CREATE
        + """
        const builtin::array<u8, 3> bytes = {7u8, 128u8, 255u8};
        const builtin::span<const u8> view = borrow_bytes(bytes);
        const Count amount = Count(11);
        const Count result = append_window(buffer, 2, view, amount, 5);
        if (result.get() != 21 || !buffer.clear()) { return 0; }
        if (result.get() != 21 || !append_one(buffer, 99u8)) { return 0; }
    """
    )
    body += check_state([99], 3) + "return 42;"
    exe = suite.compile("mixed-span-copied-scalar-record", program(body, HELPERS))
    suite.run(exe, 3, 0, 0, 42, 2, 1, release_order=[1, 2])

    body = (
        CREATE
        + """
        if (!append_one(buffer, 7u8) || !append_one(buffer, 8u8)) { return 0; }
        builtin::OwnedBytes backing = region.try_allocate(0);
        std::ByteBuffer other = std::ByteBuffer(region, move(backing));
        const Count amount = Count(0);
        const Count result = append_window(other, 0, buffer.bytes().subspan(1, 1), amount, 0);
        if (result.get() != 1 || !append_one(buffer, 9u8)) { return 0; }
    """
    )
    body += check_state([7, 8, 9], 4) + check_state([8], 1, "other") + "return 42;"
    exe = suite.compile("distinct-buffers-share-region", program(body, HELPERS))
    suite.run(exe, 5, 2, 0, 42, 4, 2, release_order=[2, 1, 3, 4])

    body = (
        CREATE
        + """
        if (!append_one(buffer, 42u8)) { return 0; }
        builtin::OwnedBytes backing = region.try_allocate(1);
        std::ByteBuffer other = std::ByteBuffer(region, move(backing));
        if (append_after(buffer, other.try_append(9u8))) { return 0; }
    """
    )
    body += check_state([42], 1) + check_state([9], 1, "other") + "return 42;"
    exe = suite.compile("completed-later-argument-is-not-rolled-back", program(body, HELPERS))
    suite.run(exe, 2, 1, 0, 42, 2, 2, release_order=[2, 1])
    suite.run(exe, 99, 1, 0, 42, 2, 2, fail_after=2, release_order=[2, 1])

    helper = """
    auto early(std::ByteBuffer& output, i64 count) -> i64 {
        if (count == 0) { return output.size(); }
        i64 index = 0;
        while (index < count) {
            if (!forward_write(output, u8(index))) { return -1; }
            index = index + 1;
        }
        return inspect(output);
    }
    """
    body = (
        CREATE
        + """
        if (early(buffer, 0) != 0 || early(buffer, 3) != 3) { return 0; }
        if (!buffer.clear() || early(buffer, 1) != 1) { return 0; }
    """
    )
    body += check_state([0], 4) + "return 42;"
    exe = suite.compile("borrow-call-cleanup-loop-and-early-return", program(body, HELPERS + helper))
    suite.run(exe, 4, 4, 0, 42, 1, 1)

    helper = f"""
    auto read_scope_then_write(std::ByteBuffer& output) -> bool {{
        {{
            const {SPAN} bytes = output.bytes();
            if (bytes.size() != 1 || bytes.at(0) != 19u8 || measure_view(output) != 1) {{ return false; }}
        }}
        return append_one(output, 23u8);
    }}
    """
    body = (
        CREATE
        + """
        if (!append_one(buffer, 19u8) || !read_scope_then_write(buffer) || measure_view(buffer) != 2) { return 0; }
    """
    )
    body += check_state([19, 23], 2) + "return 42;"
    exe = suite.compile("borrowed-formal-scoped-view-release", program(body, HELPERS + helper))
    suite.run(exe, 2, 2, 0, 42, 1, 1)

    # Whole-class local reassignment is unsupported. Replace a direct copied field
    # from a named snapshot to preserve it past the owner's lexical scope instead.
    holder = """
    class SnapshotHolder {
    public:
        std::ByteReadResult value;
        SnapshotHolder(std::ByteReadResult initial) : value(initial) {}
        auto get() const -> u64 { return value.value_or(256u64); }
    };
    """
    body = """
        const std::ByteReadResult empty = std::ByteReadResult(std::ByteReadStatus::out_of_range, 0u64);
        SnapshotHolder saved = SnapshotHolder(empty);
        {
            builtin::OwnedBytes allocation = region.try_allocate(1);
            std::ByteBuffer local = std::ByteBuffer(region, move(allocation));
            if (!append_one(local, 61u8)) { return 0; }
            const std::ByteReadResult observed = snapshot(local, 0);
            saved.value = observed;
        }
        builtin::OwnedBytes replacement = region.try_allocate(1);
        if (!replacement.ok() || !replacement.set(0, 99u8) || saved.get() != 61u64) { return 0; }
        return 42;
    """
    exe = suite.compile("copied-result-outlives-borrowed-owner", program(body, HELPERS + holder))
    suite.run(exe, 1, 0, 0, 42, 2, 1, release_order=[1, 2])


TWIN = f"""
class Twin {{
    builtin::OwnedBytes first;
    builtin::OwnedBytes second;
public:
    Twin(builtin::ByteRegion region, builtin::OwnedBytes a, builtin::OwnedBytes b) :
        first(move(a)), second(move(b)) {{}}
    auto write_first(u8 value) -> bool {{ return first.set(0, value); }}
    auto write_second(u8 value) -> bool {{ return second.set(0, value); }}
    auto read_first() const -> u8 {{ return first.at(0); }}
    auto read_second() const -> u8 {{ return second.at(0); }}
    auto first_bytes() const -> {SPAN} {{ return borrow_bytes(first); }}
}};
auto twin_write(Twin& input, u8 a, u8 b) -> bool {{
    return input.write_first(a) && input.write_second(b);
}}
auto twin_sum(const Twin& input) -> i64 {{ return i64(input.read_first()) + i64(input.read_second()); }}
"""
TWIN_CREATE = """
    builtin::OwnedBytes a = region.try_allocate(1);
    builtin::OwnedBytes b = region.try_allocate(1);
    Twin twin = Twin(region, move(a), move(b));
"""


def paired_borrowing_cases(suite):
    helpers = (
        HELPERS
        + """
    enum class PairStatus { unchanged, written, failed };
    auto paired_write(std::ByteBuffer& output, const std::ByteBuffer& input,
                      i64 offset, u64 expected, u8 byte, bool enabled) -> bool {
        if (!enabled) { return false; }
        const std::ByteReadResult saved = input.read_u8(offset);
        const builtin::array<u8, 1> local = {7u8};
        const builtin::span<const u8> view = borrow_bytes(local);
        if (saved.value_or(256u64) != expected || view.at(0) != 7u8) { return false; }
        return output.try_append(byte);
    }
    auto paired_forward(std::ByteBuffer& output, const std::ByteBuffer& input,
                        i64 offset, u64 expected, u8 byte, bool enabled) -> bool {
        const i64 before = output.size();
        const bool changed = paired_write(output, input, offset, expected, byte, enabled);
        return changed && output.size() == before + 1 && inspect(input) == 1;
    }
    auto paired_status(std::ByteBuffer& output, const std::ByteBuffer& input, PairStatus action) -> PairStatus {
        if (action == PairStatus::unchanged) { return PairStatus::unchanged; }
        if (!output.try_append(29u8) || inspect(input) != 1) { return PairStatus::failed; }
        return PairStatus::written;
    }
    auto paired_after(std::ByteBuffer& output, const std::ByteBuffer& input, i64 value, bool changed) -> i64 {
        if (!changed) { return -1; }
        return value + input.size();
    }
    """
    )
    create = (
        CREATE
        + """
        builtin::OwnedBytes backing = region.try_allocate(1);
        std::ByteBuffer input = std::ByteBuffer(region, move(backing));
        if (!input.try_append(17u8)) { return 0; }
    """
    )
    body = (
        create
        + """
        if (!paired_forward(buffer, input, 0, 17u64, 23u8, inspect(input) == 1)) { return 0; }
        if (paired_status(buffer, input, PairStatus::unchanged) != PairStatus::unchanged) { return 0; }
        if (paired_status(buffer, input, PairStatus::written) != PairStatus::written) { return 0; }
        if (!input.try_write_u8(0, 31u8)) { return 0; }
        const std::ByteBuffer frozen = move(input);
    """
    )
    body += check_state([23, 29], 2) + check_state([31], 1, "frozen")
    body += "if (!buffer.clear() || paired_after(buffer, frozen, inspect(frozen), true) != 2) { return 0; } return 42;"
    exe = suite.compile("paired-distinct-same-class-nested-forwarding", program(body, helpers))
    suite.run(exe, 3, 2, 0, 42, 2, 2, release_order=[2, 1])

    mixed = """
    auto paired_twin(std::ByteBuffer& output, const Twin& input) -> bool {
        return output.try_append(input.read_first());
    }
    """
    body = (
        CREATE
        + TWIN_CREATE
        + """
        if (!twin_write(twin, 17u8, 25u8) || !paired_twin(buffer, twin) || twin_sum(twin) != 42) { return 0; }
    """
    )
    body += check_state([17], 1) + "return 42;"
    exe = suite.compile("paired-distinct-concrete-classes", program(body, TWIN + mixed))
    suite.run(exe, 3, 1, 0, 42, 3, 3, release_order=[3, 2, 1])

    conflicts = {
        "same-root-alias": "paired_after(buffer, buffer, 0, true);",
        "later-first-root-read": "paired_after(buffer, input, buffer.size(), true);",
        "later-first-root-write": "paired_after(buffer, input, 0, buffer.clear());",
        "later-second-root-write": "paired_after(buffer, input, 0, input.clear());",
        "later-second-root-move": "paired_after(buffer, input, consume(region, move(input)), true);",
        "later-first-root-move": "paired_after(buffer, input, consume(region, move(buffer)), true);",
    }
    for name, body in conflicts.items():
        suite.reject("paired-" + name, program(create + body + "return 0;", helpers))

    bodies = {
        "const-write": "return input.clear();",
        "const-mutable-forward": "return append_one(input, 1u8);",
        "first-formal-move": "std::ByteBuffer taken = move(output); return true;",
        "second-formal-move": "std::ByteBuffer taken = move(input); return true;",
        "first-formal-span": f"const {SPAN} view = output.bytes(); return view.size() == 0;",
        "second-formal-span": f"const {SPAN} view = input.bytes(); return view.size() == 0;",
        "forward-alias": "return paired_write(output, output, 0, 17u64, 1u8, true);",
    }
    for name, body in bodies.items():
        signature = "auto bad(std::ByteBuffer& output, const std::ByteBuffer& input) -> bool { " + body + " }"
        diagnostic = "multiple borrowed roots cannot produce spans" if name.endswith("-span") else None
        suite.reject("paired-" + name, program("return 0;", helpers + signature), diagnostic)

    leading = "std::ByteBuffer& a, const std::ByteBuffer& b"
    signatures = {
        "copied-second-root": "auto bad(std::ByteBuffer& a, const Count& b) -> i64 { return 0; }",
        "copied-argument": f"auto bad({leading}, Count value) -> i64 {{ return 0; }}",
        "span-argument": f"auto bad({leading}, {SPAN} view) -> i64 {{ return 0; }}",
        "region-argument": f"auto bad({leading}, builtin::ByteRegion region) -> i64 {{ return 0; }}",
        "owner-argument": f"auto bad({leading}, builtin::OwnedBytes taken) -> i64 {{ return 0; }}",
        "service-argument": f"auto bad({leading}, builtin::ConsoleSession& service) -> i64 {{ return 0; }}",
        "copied-result": f"auto bad({leading}) -> Count {{ const Count result = Count(0); return result; }}",
        "span-result": f"auto bad({leading}) -> {SPAN} {{ return b.bytes(); }}",
        "owning-result": f"auto bad({leading}) -> std::ByteBuffer {{ return move(a); }}",
        "overload": (
            f"auto bad({leading}, i64 n) -> i64 {{ return n; }}auto bad({leading}, u64 n) -> u64 {{ return n; }}"
        ),
        "parameter-cap": f"auto bad({leading}, i64 c, i64 d, i64 e, i64 f, i64 g) -> i64 {{ return 0; }}",
    }
    for name, signature in signatures.items():
        suite.reject("paired-" + name, program("return 0;", helpers + signature))


def bounded_borrowing_cases(suite):
    """One compact real program crosses every prefix/tail boundary and forwards it."""
    definitions = [HELPERS, "enum class RootMode { zero, one };"]
    checks = []
    for roots in range(1, 5):
        for mutable in sorted({0, 1, 1 << (roots - 1), (1 << roots) - 1} | ({3, 10} if roots == 4 else set())):
            for tail in range(7 - roots):
                name = f"roots_{roots}_{int(mutable)}_{tail}"
                formals = [
                    f"{'' if mutable & (1 << index) else 'const '}std::ByteBuffer& r{index}" for index in range(roots)
                ]
                formals += [f"{'RootMode' if index % 2 else 'i64'} a{index}" for index in range(tail)]
                body = "".join(
                    f"if (!r{index}.clear()) {{ return -1; }}" for index in range(roots) if mutable & (1 << index)
                )
                body += "".join(
                    f"if (a{index} != RootMode::one) {{ return -1; }}" for index in range(tail) if index % 2
                )
                terms = [f"r{index}.capacity()" for index in range(roots)]
                terms += ["1" if index % 2 else f"a{index}" for index in range(tail)]
                body += "return " + " + ".join(terms) + ";"
                parameters = ", ".join(formals)
                definitions.append(f"auto {name}({parameters}) -> i64 {{ {body} }}")
                forwarded = ", ".join([f"r{index}" for index in range(roots)] + [f"a{index}" for index in range(tail)])
                definitions.append(f"auto forward_{name}({parameters}) -> i64 {{ return {name}({forwarded}); }}")
                actual = [f"v{index}" for index in range(roots)]
                actual += ["RootMode::one" if index % 2 else str(101 + index) for index in range(tail)]
                expected = sum(1 if index % 2 else 101 + index for index in range(tail))
                checks.append(f"if (forward_{name}({', '.join(actual)}) != {roots} * n + {expected}) {{ return 0; }}")
    formals = ", ".join(f"const std::ByteBuffer& r{index}" for index in range(3))
    definitions.append(f"auto roots_enum({formals}) -> RootMode {{ return RootMode::one; }}")
    definitions.append(
        "auto roots_growth(std::ByteBuffer& r0, const std::ByteBuffer& r1, "
        "const std::ByteBuffer& r2) -> bool { return r0.try_reserve(r1.capacity() + 1); }"
    )
    create = "".join(
        f"builtin::OwnedBytes allocation{index} = region.try_allocate(n);"
        f"std::ByteBuffer v{index} = std::ByteBuffer(region, move(allocation{index}));"
        f"if (!v{index}.ok()) {{ return -7; }}"
        for index in range(4)
    )
    actuals = ", ".join(f"v{index}" for index in range(3))
    body = create + "".join(checks)
    body += f"if (roots_enum({actuals}) != RootMode::one) {{ return 0; }}"
    body += f"if (flag == 1 && roots_growth({actuals})) {{ return 0; }}"
    body += "".join(f"if (v{index}.capacity() != n || v{index}.size() != 0) {{ return 0; }}" for index in range(4))
    definitions.append(
        "auto write_later(const std::ByteBuffer& r0, std::ByteBuffer& r1, "
        "const std::ByteBuffer& r2, std::ByteBuffer& r3) -> bool { "
        "return r1.try_append(17u8) && r3.try_append(25u8); }"
    )
    body += "if (n > 0) { if (!write_later(v0, v1, v2, v3)) { return 0; } "
    body += "if (v0.size() != 0 || v2.size() != 0 || v1.size() != 1 || v3.size() != 1) { return 0; } "
    body += "const std::ByteReadResult a = v1.read_u8(0); const std::ByteReadResult b = v3.read_u8(0); "
    body += "if (a.value_or(0u64) != 17u64 || b.value_or(0u64) != 25u64) { return 0; } }"
    executable = suite.compile("bounded-roots-one-through-four", program(body + "return 42;", "".join(definitions)))
    for length in (0, 2):
        suite.run(executable, 4 * length, length, 0, 42, 4, 4)
        suite.run(executable, 4 * length, length, 1, 42, 4, 4, fail_after=4)
    suite.run(executable, 100, 2, 1, 42, 4, 4, fail_after=4)
    suite.run(executable, 12, 2, 0, -7, 2, 2, fail_after=2)
    suite.run(executable, 5, 2, 0, -7, 2, 2)

    # All-readonly duplicate roots must reject too, even when every successful
    # allocation is empty and every nominal class is the same.
    for roots in range(2, 5):
        for first in range(roots):
            for second in range(first + 1, roots):
                arguments = [f"v{index}" for index in range(roots)]
                arguments[second] = arguments[first]
                call = f"roots_{roots}_0_0({', '.join(arguments)});"
                suite.reject(
                    f"bounded-readonly-alias-{roots}-{first}-{second}",
                    program(
                        create + call + "return 0;",
                        f"auto roots_{roots}_0_0("
                        + ", ".join(f"const std::ByteBuffer& r{i}" for i in range(roots))
                        + ") -> i64 { return 0; }",
                    ),
                    "borrowed arguments require distinct owning roots",
                )
    readonly = ", ".join(f"const std::ByteBuffer& r{index}" for index in range(4))
    for ordinal in range(4):
        for name, statement, diagnostic in (
            (
                "span",
                f"const {SPAN} view = r{ordinal}.bytes(); return view.size();",
                "multiple borrowed roots cannot produce spans",
            ),
            (
                "const-escalation",
                f"append_one(r{ordinal}, 1u8); return 0;",
                "mutable borrowed parameter requires a mutable owning object",
            ),
            (
                "move-formal",
                f"std::ByteBuffer taken = move(r{ordinal}); return 0;",
                "borrowed object parameters cannot be copied or transferred by value",
            ),
            (
                "private-field",
                f"return r{ordinal}.payload.size();",
                "borrowed object parameters support public methods, not field projections",
            ),
        ):
            suite.reject(
                f"bounded-{name}-{ordinal}",
                program("return 0;", HELPERS + f"auto bad({readonly}) -> i64 {{ {statement} }}"),
                diagnostic,
            )
    five = ", ".join(f"const std::ByteBuffer& r{index}" for index in range(5))
    suite.reject(
        "bounded-five-roots",
        program("return 0;", HELPERS + f"auto bad({five}) -> i64 {{ return 0; }}"),
        "borrowed functions require one plain concrete class reference, one to four owning-class references",
    )
    seven = ", ".join(f"const std::ByteBuffer& r{index}" for index in range(7))
    suite.reject(
        "bounded-seven-roots",
        program("return 0;", f"auto bad({seven}) -> i64 {{ return 0; }}"),
        "at most six parameters supported",
    )
    suite.reject(
        "bounded-nonleading-root",
        program(
            "return 0;",
            HELPERS
            + "auto bad(const std::ByteBuffer& r0, i64 value, const std::ByteBuffer& r1) -> i64 { return value; }",
        ),
        "borrowed parameters require a supported leading ownership reference signature",
    )
    mutable = ", ".join(f"std::ByteBuffer& r{index}" for index in range(4))
    exclusive = f"auto exclusive({mutable}, i64 value) -> i64 {{ return value; }}"
    for ordinal in range(4):
        for name, operation in (
            ("read", f"v{ordinal}.size()"),
            ("write", f"i64(v{ordinal}.clear())"),
            ("move", f"consume(region, move(v{ordinal}))"),
        ):
            suite.reject(
                f"bounded-exclusive-later-{name}-{ordinal}",
                program(create + f"exclusive(v0, v1, v2, v3, {operation}); return 0;", HELPERS + exclusive),
            )


def direct_method_return_case(suite):
    helpers = (
        HELPERS
        + """
    class Reader {
        builtin::OwnedBytes payload;
    public:
        Reader(builtin::ByteRegion region, builtin::OwnedBytes initial) : payload(move(initial)) {}
        auto capture(builtin::span<const u8> bytes) -> Count {
            payload.set(0, bytes.at(0));
            return Count(i64(payload.at(0)) + payload.size());
        }
        auto forward(builtin::span<const u8> bytes) -> Count { return capture(bytes); }
        auto clear() -> bool { return payload.set(0, 0u8); }
    };
    auto copy_report(Reader& receiver, builtin::span<const u8> bytes) -> Count {
        const builtin::span<const u8> view = bytes.subspan(0, 1);
        return receiver.forward(view);
    }
    """
    )
    body = """
        builtin::OwnedBytes allocation = region.try_allocate(2);
        Reader receiver = Reader(region, move(allocation));
        builtin::array<u8, 1> bytes = {40u8};
        i64 total = 0;
        i64 index = 0;
        while (index < 2) {
            const Count result = copy_report(receiver, borrow_bytes(bytes));
            if (!receiver.clear()) { return 0; }
            bytes[0] = bytes[0] + 1u8;
            total = total + result.get();
            index = index + 1;
        }
        if (total != 85) { return 0; }
        return 42;
    """
    exe = suite.compile("direct-method-result-closes-span-and-owner-loans", program(body, helpers))
    suite.run(exe, 2, 2, 0, 42, 1, 1, release_order=[1])


def multiple_field_cases(suite):
    body = (
        TWIN_CREATE
        + """
        if (!twin_write(twin, 17u8, 25u8) || twin_sum(twin) != 42) { return 0; }
        Twin moved = move(twin);
        if (twin_sum(moved) != 42 || !twin_write(moved, 99u8, 1u8) || twin_sum(moved) != 100) { return 0; }
        return 42;
    """
    )
    exe = suite.compile("concrete-owner-with-two-resource-fields", program(body, TWIN))
    suite.run(exe, 2, 0, 0, 42, 2, 2, release_order=[2, 1])
    for name, body in {
        "other-field-live-view": (f"const {SPAN} first = twin.first_bytes(); twin_write(twin, 1u8, 2u8);"),
        "other-field-empty-view": (
            f"const {SPAN} first = twin.first_bytes().subspan(0, 0); twin_write(twin, 1u8, 2u8);"
        ),
        "later-other-field-read": "twin_write(twin, 1u8, twin.read_second());",
        "later-other-field-write": "twin_after(twin, twin.write_second(2u8));",
    }.items():
        helper = "auto twin_after(Twin& input, bool value) -> bool { return value; }"
        diagnostic = (
            "cannot mutate or move an owner while a readonly span is live"
            if name.startswith("other-field-")
            else "owning object is exclusively borrowed for a call"
        )
        suite.reject(name, program(TWIN_CREATE + body + "return 0;", TWIN + helper), diagnostic)


def json_program(body, helpers=""):
    return program(body, helpers).replace("import std.binary;", "import std.json_write;\nimport std.binary;")


def escaped_bytes(scalar):
    # Python's independent JSON encoder agrees on canonical short/control escapes;
    # ensure_ascii=False preserves valid non-ASCII scalars as shortest UTF-8.
    return list(json.dumps(chr(scalar), ensure_ascii=False)[1:-1].encode("utf-8"))


def json_cases(suite):
    body = """
        const std::JsonAppendResult success = std::JsonAppendResult(std::JsonAppendStatus::success, n);
        const std::JsonAppendResult invalid = std::JsonAppendResult(std::JsonAppendStatus::invalid_scalar, n);
        const std::JsonAppendResult failed = std::JsonAppendResult(std::JsonAppendStatus::append_failed, n);
        if (n >= 1 && n <= 6) {
            if (success.status() != std::JsonAppendStatus::success || success.appended_bytes() != n) { return 0; }
        } else {
            if (success.status() != std::JsonAppendStatus::append_failed || success.appended_bytes() != 0) { return 0; }
        }
        if (invalid.status() != std::JsonAppendStatus::invalid_scalar || invalid.appended_bytes() != 0 ||
            failed.status() != std::JsonAppendStatus::append_failed || failed.appended_bytes() != 0) { return 0; }
        return 42;
    """
    exe = suite.compile("json-copied-report-constructor-bounds", json_program(body))
    for count in (-(1 << 63), -1, 0, 1, 6, 7, (1 << 63) - 1):
        suite.run(exe, 0, count, 0, 42, 0, 0)

    scalars = list(range(32)) + [
        34,
        47,
        65,
        92,
        0x7F,
        0x80,
        0x7FF,
        0x800,
        0xD7FF,
        0xE000,
        0xFFFF,
        0x10000,
        0x1F600,
        0x10FFFF,
    ]
    body = """
        builtin::OwnedBytes allocation = region.try_allocate(flag);
        std::ByteBuffer buffer = std::ByteBuffer(region, move(allocation));
        if (!buffer.try_append(33u8)) { return 0; }
        const std::JsonAppendResult result = std::append_json_scalar(buffer, u64(n));
        if (result.status() != std::JsonAppendStatus::success) { return 0; }
    """
    for scalar in scalars:
        values = escaped_bytes(scalar)
        body += f"if (n == {scalar}) {{"
        body += f"if (result.appended_bytes() != {len(values)}) {{ return 0; }}"
        body += check_state([33, *values], "flag")
        body += "if (!buffer.clear() || result.appended_bytes() == 0) { return 0; } return 42; }"
    body += "return 0;"
    exe = suite.compile("json-canonical-scalar-bytes", json_program(body))
    for scalar in scalars:
        suite.run(exe, 7, scalar, 7, 42, 1, 1, fail_after=1)

    body = (
        CREATE
        + """
        if (!buffer.try_append(33u8)) { return 0; }
        const std::JsonAppendResult result = std::append_json_scalar(buffer, 0u64);
        if (result.status() != std::JsonAppendStatus::success || result.appended_bytes() != 6) { return 0; }
    """
    )
    body += check_state([33, 92, 117, 48, 48, 48, 48], "flag") + "return 42;"
    exe = suite.compile("json-single-geometric-growth", json_program(body))
    for initial, target in ((1, 7), (2, 7), (4, 8), (7, 7)):
        allocations = 1 if initial == target else 2
        suite.run(exe, target, initial, target, 42, allocations, 1)

    body = CREATE + "if (!buffer.try_append(17u8) || !buffer.try_append(23u8)) { return 0; }"
    for scalar in (0xD800, 0xDFFF, 0x110000, (1 << 64) - 1):
        body += f"""
        {{
            const std::JsonAppendResult result = std::append_json_scalar(buffer, {scalar}u64);
            if (result.status() != std::JsonAppendStatus::invalid_scalar || result.appended_bytes() != 0) {{
                return 0;
            }}
        }}
        """
        body += check_state([17, 23], 2)
    body += "return 42;"
    exe = suite.compile("json-invalid-scalar-no-mutation", json_program(body))
    suite.run(exe, 2, 2, 0, 42, 1, 1, fail_after=1)

    body = (
        CREATE
        + """
        if (!buffer.try_append(17u8) || !buffer.try_append(23u8)) { return 0; }
        const std::JsonAppendResult result = std::append_json_scalar(buffer, 0u64);
        if (result.status() != std::JsonAppendStatus::append_failed || result.appended_bytes() != 0) { return 0; }
    """
    )
    body += check_state([17, 23], 2)
    body += """
        if (!buffer.try_truncate(1)) { return 0; }
        const std::JsonAppendResult retry = std::append_json_scalar(buffer, 65u64);
        if (retry.status() != std::JsonAppendStatus::success || retry.appended_bytes() != 1 ||
            result.status() != std::JsonAppendStatus::append_failed) { return 0; }
    """
    body += check_state([17, 65], 2) + "return 42;"
    exe = suite.compile("json-recoverable-failure-preserves-state", json_program(body))
    suite.run(exe, 2, 2, 0, 42, 1, 1)
    suite.run(exe, 99, 2, 0, 42, 1, 1, fail_after=1)

    body = (
        CREATE
        + """
        if (!buffer.try_append(17u8) || !buffer.try_append(23u8)) { return 0; }
        const std::JsonAppendResult failed = std::append_json_scalar(buffer, 0u64);
        if (failed.status() != std::JsonAppendStatus::append_failed) { return 0; }
        builtin::OwnedBytes remaining = region.try_allocate(3);
        if (!remaining.ok() || remaining.size() != 3) { return 0; }
    """
    )
    body += check_state([17, 23], 2) + "return 42;"
    exe = suite.compile("json-failed-growth-preserves-committed-quota", json_program(body))
    suite.run(exe, 5, 2, 0, 42, 2, 2, release_order=[2, 1])

    body = (
        CREATE
        + """
        const std::JsonAppendResult invalid = std::append_json_scalar(buffer, 55296u64);
        const std::JsonAppendResult failed = std::append_json_scalar(buffer, 65u64);
        if (buffer.ok() || buffer.size() != 0 || buffer.capacity() != 0 ||
            invalid.status() != std::JsonAppendStatus::invalid_scalar || invalid.appended_bytes() != 0 ||
            failed.status() != std::JsonAppendStatus::append_failed || failed.appended_bytes() != 0) { return 0; }
        return 42;
    """
    )
    exe = suite.compile("json-invalid-destination", json_program(body))
    suite.run(exe, 0, 1, 0, 42, 0, 0)
    suite.run(exe, 8, 0, 0, 42, 0, 0, fail_after=0)

    helper = """
    auto write_forward(std::ByteBuffer& output, u64 scalar) -> std::JsonAppendResult {
        const std::JsonAppendResult result = std::append_json_scalar(output, scalar);
        return result;
    }
    """
    body = (
        CREATE
        + """
        const std::JsonAppendResult result = write_forward(buffer, 128512u64);
        if (result.status() != std::JsonAppendStatus::success || result.appended_bytes() != 4) { return 0; }
    """
    )
    body += check_state([240, 159, 152, 128], 4)
    body += "std::ByteBuffer moved = move(buffer); if (!moved.clear() || result.appended_bytes() != 4) { return 0; }"
    body += "return 42;"
    exe = suite.compile("json-forwarded-borrow-copied-result", json_program(body, helper))
    suite.run(exe, 4, 0, 0, 42, 2, 1)


def rejection_cases(suite):
    amount = "const Count amount = Count(0);"
    calls = {
        "mutable-later-size": "append_window(buffer, buffer.size(), borrow_bytes(bytes), amount, 0);",
        "mutable-later-read": "append_window(buffer, inspect(buffer), borrow_bytes(bytes), amount, 0);",
        "mutable-later-mutation": "append_after(buffer, buffer.clear());",
        "mutable-later-consumption": "append_window(buffer, consume(region, move(buffer)), view, amount, 0);",
        "self-span": "append_window(buffer, 0, buffer.bytes(), amount, 0);",
        "self-empty-span": "append_window(buffer, 0, buffer.bytes().subspan(0, 0), amount, 0);",
        "named-self-span": f"const {SPAN} self = buffer.bytes(); append_window(buffer, 0, self, amount, 0);",
        "named-empty-self-span": (
            f"const {SPAN} self = buffer.bytes().subspan(0, 0); append_window(buffer, 0, self, amount, 0);"
        ),
        "disjoint-self-spans": (
            f"const {SPAN} left = buffer.bytes().subspan(0, 1); "
            "append_window(buffer, 0, buffer.bytes().subspan(1, 1), amount, 0);"
        ),
        "shared-later-mutation": "shared_after(buffer, buffer.clear());",
        "shared-later-consumption": "shared_argument(buffer, consume(region, move(buffer)));",
        "shared-later-mutable-borrow": "shared_after(buffer, append_one(buffer, 1u8));",
        "const-owner-escalation": "const std::ByteBuffer fixed = move(buffer); append_one(fixed, 1u8);",
        "move-argument-is-not-borrow": "inspect(move(buffer));",
        "consumed-owner-borrow": "std::ByteBuffer moved = move(buffer); inspect(buffer);",
        "wrong-concrete-class": "Count wrong = Count(1); inspect(wrong);",
        "scalar-is-not-object": "inspect(1);",
        "temporary-constructor": (
            "builtin::OwnedBytes extra = region.try_allocate(0); inspect(std::ByteBuffer(region, move(extra)));"
        ),
        "temporary-owning-call": "inspect(bounce(region, move(buffer)));",
        "reference-local": "std::ByteBuffer& alias = buffer;",
        "reference-local-const": "const std::ByteBuffer& alias = buffer;",
        "address-of": "inspect(&buffer);",
        "pointer-local": "std::ByteBuffer* pointer = &buffer;",
        "rvalue-reference": "std::ByteBuffer&& alias = move(buffer);",
    }
    setup = (
        CREATE
        + amount
        + "const builtin::array<u8, 1> bytes = {7u8};"
        + f"const {SPAN} view = borrow_bytes(bytes);"
        + "buffer.try_append(1u8); buffer.try_append(2u8);"
    )
    bounce = "auto bounce(builtin::ByteRegion region, std::ByteBuffer input) -> std::ByteBuffer { return move(input); }"
    diagnostics = {
        "mutable-later-size": "owning object is exclusively borrowed for a call",
        "mutable-later-read": "owning object is exclusively borrowed for a call",
        "mutable-later-mutation": "owning object is exclusively borrowed for a call",
        "mutable-later-consumption": "owning object is exclusively borrowed for a call",
        "self-span": "owning object is exclusively borrowed for a call",
        "self-empty-span": "owning object is exclusively borrowed for a call",
        "named-self-span": "cannot mutate or move an owner while a readonly span is live",
        "named-empty-self-span": "cannot mutate or move an owner while a readonly span is live",
        "disjoint-self-spans": "cannot mutate or move an owner while a readonly span is live",
        "shared-later-mutation": "cannot mutate or move an owning object while borrowed",
        "shared-later-consumption": "cannot mutate or move an owning object while borrowed",
        "shared-later-mutable-borrow": "cannot mutate or move an owning object while borrowed",
        "const-owner-escalation": "mutable borrowed parameter requires a mutable owning object",
        "move-argument-is-not-borrow": "borrowed object argument requires a complete named owning object",
        "consumed-owner-borrow": "use after move of 'buffer'",
        "wrong-concrete-class": "expected std::ByteBuffer, got Count",
        "scalar-is-not-object": "borrowed object argument requires a complete named owning object",
        "temporary-constructor": "borrowed object argument requires a complete named owning object",
        "temporary-owning-call": "borrowed object argument requires a complete named owning object",
        "reference-local": "assignment requires a local or local field",
        "reference-local-const": "expected identifier",
        "address-of": "expected expression",
        "pointer-local": "assignment requires a local or local field",
        "rvalue-reference": "assignment requires a local or local field",
    }
    for name, call in calls.items():
        # Copied-result functions require a typed initializer even on a path that
        # must reject for an argument loan. Reach that intended semantic check.
        call = call.replace("append_window(", "const Count result = append_window(")
        suite.reject(name, program(setup + call + "return 0;", HELPERS + bounce), diagnostics[name])

    borrowed_bodies = {
        "formal-const-escalation": ("const ", "return append_one(input, 1u8);"),
        "formal-const-method-mutation": ("const ", "return input.clear();"),
        "formal-move-to-local": ("", "std::ByteBuffer taken = move(input); return true;"),
        "formal-implicit-copy": ("", "std::ByteBuffer copied = input; return true;"),
        "formal-whole-assignment": ("", "input = input; return true;"),
        "formal-drop": ("", "drop(input); return true;"),
        "formal-private-field": ("", "input.length = 7; return true;"),
        "formal-private-owner-extraction": ("", "builtin::OwnedBytes taken = move(input.payload); return true;"),
        "formal-private-owner-read": ("const ", "return input.payload.ok();"),
        "formal-later-self-access": ("", "return append_after(input, input.ok());"),
        "formal-later-self-span": (
            "",
            "const Count amount = Count(0); append_window(input, 0, input.bytes(), amount, 0); return true;",
        ),
        "formal-view-then-mutable-forward": ("", f"const {SPAN} view = input.bytes(); return append_one(input, 1u8);"),
    }
    body_diagnostics = {
        "formal-const-escalation": "mutable borrowed parameter requires a mutable owning object",
        "formal-const-method-mutation": "mutable method requires a mutable receiver",
        "formal-move-to-local": "borrowed object parameters cannot be copied or transferred by value",
        "formal-implicit-copy": "owning class cannot be copied; use move(named_local)",
        "formal-whole-assignment": "assignment requires a mutable scalar local",
        "formal-drop": "unknown function 'drop'",
        "formal-private-field": "borrowed object parameters support public methods, not field assignment",
        "formal-private-owner-extraction": "ownership operation requires a local name",
        "formal-private-owner-read": "borrowed object parameters support public methods, not field projections",
        "formal-later-self-access": "owning object is exclusively borrowed for a call",
        "formal-later-self-span": "owning object is exclusively borrowed for a call",
        "formal-view-then-mutable-forward": "cannot mutate or move an owner while a readonly span is live",
    }
    for name, (const, body) in borrowed_bodies.items():
        body = body.replace("append_window(", "const Count result = append_window(")
        helper = f"auto bad({const}std::ByteBuffer& input) -> bool {{ {body} }}"
        suite.reject(name, program("return 0;", HELPERS + helper), body_diagnostics[name])

    signatures = {
        "nonleading-borrow": "auto bad(i64 first, std::ByteBuffer& input) -> i64 { return first; }",
        "borrow-after-region": ("auto bad(builtin::ByteRegion region, std::ByteBuffer& input) -> i64 { return 0; }"),
        "borrow-and-owning-parameter": (
            "auto bad(std::ByteBuffer& input, std::ByteBuffer taken) -> i64 { return input.size(); }"
        ),
        "borrow-and-owned-bytes-parameter": (
            "auto bad(std::ByteBuffer& input, builtin::OwnedBytes taken) -> i64 { return input.size(); }"
        ),
        "borrow-and-region-parameter": (
            "auto bad(std::ByteBuffer& input, builtin::ByteRegion region) -> i64 { return input.size(); }"
        ),
        "borrowed-owning-result": "auto bad(std::ByteBuffer& input) -> std::ByteBuffer { return move(input); }",
        "borrowed-reference-result": "auto bad(std::ByteBuffer& input) -> std::ByteBuffer& { return input; }",
        "borrowed-span-result": f"auto bad(const std::ByteBuffer& input) -> {SPAN} {{ return input.bytes(); }}",
        "multiple-plain-class-references": "auto bad(Count& first, Count& second) -> i64 { return first.get(); }",
        "scalar-reference": "auto bad(i64& input) -> i64 { return input; }",
        "builtin-owner-reference": "auto bad(builtin::OwnedBytes& input) -> i64 { return input.size(); }",
        "const-builtin-owner-reference": "auto bad(const builtin::OwnedBytes& input) -> i64 { return input.size(); }",
        "rvalue-reference-parameter": "auto bad(std::ByteBuffer&& input) -> i64 { return input.size(); }",
        "reference-field": "class Bad { std::ByteBuffer& input; public: Bad() {} };",
        "const-reference-field": "class Bad { const std::ByteBuffer& input; public: Bad() {} };",
        "constructor-reference": "class Bad { public: Bad(std::ByteBuffer& input) {} };",
        "method-reference": "class Bad { public: Bad() {} auto bad(std::ByteBuffer& input) -> i64 { return 0; } };",
        "function-template-reference": (
            "template<Value T> auto bad(std::ByteBuffer& input, T value) -> T { return value; }"
        ),
        "generic-reference": "template<Value T> auto bad(T& input) -> i64 { return 0; }",
        "borrow-overload": (
            "auto bad(std::ByteBuffer& input, i64 value) -> i64 { return value; }"
            "auto bad(std::ByteBuffer& input, u64 value) -> u64 { return value; }"
        ),
        "const-borrow-overload": (
            "auto bad(std::ByteBuffer& input) -> i64 { return 0; }"
            "auto bad(const std::ByteBuffer& input) -> i64 { return 0; }"
        ),
        "pointer-parameter": "auto bad(std::ByteBuffer* input) -> i64 { return 0; }",
    }
    declaration_diagnostic = (
        "borrowed parameters require a supported leading ownership reference signature on an ordinary function"
    )
    result_diagnostic = (
        "borrowed functions require one plain concrete class reference, one to four owning-class references"
    )
    later_diagnostic = "borrowed-function tails require scalar or enum values"
    signature_diagnostics = {
        "nonleading-borrow": declaration_diagnostic,
        "borrow-after-region": declaration_diagnostic,
        "borrow-and-owning-parameter": later_diagnostic,
        "borrow-and-owned-bytes-parameter": later_diagnostic,
        "borrow-and-region-parameter": later_diagnostic,
        "borrowed-owning-result": result_diagnostic,
        "borrowed-reference-result": "expected '{'",
        "borrowed-span-result": "only scalar function results or scalar-field class values are supported",
        "multiple-plain-class-references": result_diagnostic,
        "scalar-reference": declaration_diagnostic,
        "builtin-owner-reference": declaration_diagnostic,
        "const-builtin-owner-reference": declaration_diagnostic,
        "rvalue-reference-parameter": "expected identifier",
        "reference-field": "expected identifier",
        "const-reference-field": "unsupported or reserved type spelling",
        "constructor-reference": declaration_diagnostic,
        "method-reference": declaration_diagnostic,
        "function-template-reference": declaration_diagnostic,
        "generic-reference": declaration_diagnostic,
        "borrow-overload": "borrowed-object functions cannot be overloaded",
        "const-borrow-overload": "borrowed-object functions cannot be overloaded",
        "pointer-parameter": "expected identifier",
    }
    for name, signature in signatures.items():
        suite.reject(name, program("return 0;", HELPERS + signature), signature_diagnostics[name])

    private_class = """
    class Vault {
        builtin::OwnedBytes payload;
        auto hidden() const -> i64 { return payload.size(); }
    public:
        Vault(builtin::ByteRegion region, builtin::OwnedBytes input) : payload(move(input)) {}
        auto size() const -> i64 { return hidden(); }
    };
    """
    suite.reject(
        "borrowed-private-method",
        program("return 0;", private_class + "auto bad(const Vault& input) -> i64 { return input.hidden(); }"),
        "private method is inaccessible",
    )
    suite.reject(
        "borrowed-private-field-view",
        program(
            "return 0;",
            private_class + f"auto bad(const Vault& input) -> i64 {{ const {SPAN} view = borrow_bytes(input.payload); "
            "return view.size(); }",
        ),
        "borrowed object parameters support public methods, not field access",
    )
    suite.reject(
        "projection-cannot-be-borrow-actual",
        program(CREATE + "inspect(buffer.payload); return 0;", HELPERS),
        "borrowed object argument requires a complete named owning object",
    )
    suite.reject(
        "json-writer-const-output",
        json_program(
            CREATE + "const std::ByteBuffer frozen = move(buffer); "
            "const std::JsonAppendResult result = std::append_json_scalar(frozen, 65u64); return 0;"
        ),
        "mutable borrowed parameter requires a mutable owning object",
    )
    suite.reject(
        "json-writer-later-read-of-output",
        json_program(
            CREATE + "const std::JsonAppendResult result = "
            "std::append_json_scalar(buffer, u64(buffer.size())); return 0;"
        ),
        "owning object is exclusively borrowed for a call",
    )


def independent_json_import(suite):
    name = "json-import-remains-allocation-free"
    if not suite.select_program(name):
        return
    folder = suite.directory / name
    folder.mkdir()
    path, output = folder / "input.au", folder / "output.s"
    path.write_text("""module pure_json_import;
import std.json;
auto plain_json() -> i64 {
    const builtin::array<u8, 4> bytes = {110u8, 117u8, 108u8, 108u8};
    const std::JsonResult result = std::validate_json(borrow_bytes(bytes), 0, 4);
    if (result.status() != std::JsonStatus::success || result.max_depth() != 0) { return 0; }
    return result.token_count();
}
""")
    result = owned_bytes.command([suite.compiler, *suite.module_args, path, "-o", output])
    require(result.returncode == 0, f"standalone std.json import failed: {result.stderr!r}")
    require("__au_runtime_bytes_" not in output.read_text(), "std.json gained an owner runtime dependency")
    suite.programs += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    parser.add_argument(
        "--smoke", action="store_true", help="partial developer profile: two native programs and seven rejections"
    )
    parser.add_argument("--artifacts", type=Path, help="retain this run in a new directory")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="aurora-borrowed-objects-") as temporary:
        suite = BorrowCases(args.compiler.resolve(strict=True), args.artifacts or Path(temporary), args.smoke)
        plain_borrowing_cases(suite)
        borrowing_cases(suite)
        paired_borrowing_cases(suite)
        bounded_borrowing_cases(suite)
        direct_method_return_case(suite)
        multiple_field_cases(suite)
        json_cases(suite)
        rejection_cases(suite)
        independent_json_import(suite)
        suite.finish()
        profile = "smoke" if args.smoke else "full"
        print(f"PASS borrowed objects [profile={profile}]: {suite.native} native runs")


if __name__ == "__main__":
    main()
