#!/usr/bin/env python3
"""Bounded synchronous owning-object borrow source and real hosted-runtime gate.

The library helper uses the existing JSON scalar codec and one bulk append. This
suite checks complete bytes, returned copied observations, allocation identities,
normal cleanup and clean output-preserving rejection. It is not a general borrow
checker, fail-stop unwinder, kernel gate or proof of memory safety. All assertions
use require(), including under Python -O. Failed artifacts are always retained.

The default full profile runs every fixture. --smoke selects two real native
programs and seven named safety rejections for developer feedback; its receipts
explicitly mark partial coverage, and it cannot establish the full suite gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import byte_buffer
from byte_buffer import BufferSuite, CREATE, ROOT, check_state, program
import owned_bytes
from unsigned_oracle import require

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


class BorrowSuite(BufferSuite):
    def __init__(self, compiler, directory, compile_only, smoke=False):
        super().__init__(compiler, directory, compile_only)
        self.profile = "smoke" if smoke else "full"
        self.cases = []
        self.selected_programs = []
        self.selected_rejections = []
        self.omitted_programs = []
        self.omitted_rejections = []
        self.save_selection()

    def select_program(self, name):
        selected = self.profile == "full" or name in SMOKE_PROGRAMS
        names = self.selected_programs if selected else self.omitted_programs
        require(name not in names, f"duplicate program fixture: {name}")
        names.append(name)
        self.save_selection()
        return selected

    def compile(self, name, source, entry_name=None):
        if not self.select_program(name):
            return None
        return super().compile(name, source, entry_name)

    def save_selection(self):
        (self.directory / "selection.json").write_text(
            json.dumps(
                {
                    "profile": self.profile,
                    "partial_coverage": self.profile == "smoke",
                    "selected_programs": self.selected_programs,
                    "selected_rejections": self.selected_rejections,
                    "omitted_programs": self.omitted_programs,
                    "omitted_rejections": self.omitted_rejections,
                },
                indent=2,
            )
            + "\n"
        )

    def check_selection(self):
        require(self.programs == len(self.selected_programs), "selected program did not compile")
        require(self.rejections == len(self.selected_rejections), "selected rejection did not complete")
        require(len(self.cases) == self.native + self.skipped_native, "selected runtime accounting mismatch")
        native_programs = set(self.selected_programs) - {"json-import-remains-allocation-free"}
        require({case["program"] for case in self.cases} == native_programs, "selected program has no runtime case")
        if self.profile == "smoke":
            require(set(self.selected_programs) == set(SMOKE_PROGRAMS), "smoke program selection changed")
            require(set(self.selected_rejections) == set(SMOKE_REJECTIONS), "smoke rejection selection changed")
        else:
            require(not self.omitted_programs and not self.omitted_rejections, "full profile omitted fixtures")

    def run(self, executable, quota, length, flag, expected, allocations, peak, fail_after=None, release_order=None):
        if executable is None:
            require(self.profile == "smoke", "full profile cannot omit a runtime case")
            return
        case = {
            "profile": self.profile,
            "program": executable.parent.name,
            "executable": str(executable),
            "quota": quota,
            "length": length,
            "flag": flag,
            "expected": expected,
            "allocations": allocations,
            "peak": peak,
            "fail_after": fail_after,
            "release_order": release_order,
            "skipped": self.compile_only,
        }
        self.cases.append(case)
        self.save_cases()
        super().run(executable, quota, length, flag, expected, allocations, peak, fail_after, release_order)
        if not self.compile_only:
            case["observed"] = [int(part) for part in self.last_observation.stdout.split()]
            case["passed"] = True
        self.save_cases()

    def save_cases(self):
        (self.directory / "cases.json").write_text(json.dumps(self.cases, indent=2) + "\n")

    def reject(self, name, source, diagnostic=None):
        if self.profile == "smoke" and name not in SMOKE_REJECTIONS:
            require(name not in self.omitted_rejections, f"duplicate rejection fixture: {name}")
            self.omitted_rejections.append(name)
            self.save_selection()
            return
        require(name not in self.selected_rejections, f"duplicate rejection fixture: {name}")
        self.selected_rejections.append(name)
        self.save_selection()
        folder = self.directory / ("reject-" + name)
        folder.mkdir()
        path, output = folder / "input.au", folder / "output.s"
        path.write_text(source)
        for attempt, prior in enumerate((None, PRESERVED)):
            if prior is not None:
                output.write_bytes(prior)
            result = owned_bytes.command([self.compiler, *self.module_args, path, "-o", output])
            (folder / f"stderr-{attempt}.txt").write_bytes(result.stderr)
            (folder / f"stdout-{attempt}.bin").write_bytes(result.stdout)
            require(result.returncode == 1, f"{name}: expected clean exit 1: {result.stderr!r}")
            require(bool(result.stderr), f"{name}: missing diagnostic")
            if diagnostic is not None:
                require(diagnostic in result.stderr.decode(), f"{name}: wrong diagnostic: {result.stderr!r}")
            require(not output.exists() if prior is None else output.read_bytes() == prior, f"{name}: changed output")
            require(path.read_text() == source, f"{name}: modified source")
        self.rejections += 1


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
        "const-then-mutable": "auto bad(const std::ByteBuffer& a, std::ByteBuffer& b) -> i64 { return 0; }",
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


def dual_mutable_borrowing_cases(suite):
    """Two independent complete owners grant two lexical mutable capabilities."""
    helpers = (
        HELPERS
        + """
    enum class DualStatus { first_failed, second_failed, complete };
    auto dual_write(std::ByteBuffer& a, std::ByteBuffer& b,
                    i64 offset, u64 expected, u8 value, bool enabled) -> bool {
        if (!enabled || offset != 0 || expected != 17u64) { return false; }
        if (!a.try_write_u8(offset, value)) { return false; }
        // Method and nested borrowed calls may clobber all argument registers.
        if (inspect(a) != 1 || !append_one(b, u8(expected))) { return false; }
        const std::ByteReadResult observed = a.read_u8(offset);
        return observed.value_or(256u64) == u64(value);
    }
    auto dual_forward(std::ByteBuffer& a, std::ByteBuffer& b,
                      i64 offset, u64 expected, u8 value, bool enabled) -> bool {
        return dual_write(a, b, offset, expected, value, enabled);
    }
    auto dual_zero(std::ByteBuffer& a, std::ByteBuffer& b) -> bool {
        return a.try_write_u8(0, 31u8) && b.try_write_u8(0, 37u8);
    }
    auto dual_three(std::ByteBuffer& a, std::ByteBuffer& b, const std::ByteBuffer& c,
                    DualStatus status, u8 value, i64 expected) -> DualStatus {
        if (status != DualStatus::complete || c.size() != expected) { return DualStatus::first_failed; }
        if (!a.try_write_u8(0, value) || !b.try_write_u8(0, 43u8)) { return DualStatus::second_failed; }
        return DualStatus::complete;
    }
    auto dual_three_forward(std::ByteBuffer& a, std::ByteBuffer& b, const std::ByteBuffer& c,
                            DualStatus status, u8 value, i64 expected) -> DualStatus {
        return dual_three(b, a, c, status, value, expected);
    }
    auto dual_after(std::ByteBuffer& a, std::ByteBuffer& b, i64 value, bool enabled) -> bool {
        return enabled && value == 0 && dual_zero(a, b);
    }
    auto dual_growth(std::ByteBuffer& a, std::ByteBuffer& b) -> DualStatus {
        if (!a.try_reserve(2)) { return DualStatus::first_failed; }
        if (!b.try_reserve(2)) { return DualStatus::second_failed; }
        if (!a.try_reserve(4) || !b.try_reserve(4)) { return DualStatus::first_failed; }
        return DualStatus::complete;
    }
    """
    )
    create = (
        CREATE
        + """
        builtin::OwnedBytes backing = region.try_allocate(1);
        std::ByteBuffer other = std::ByteBuffer(region, move(backing));
        if (!buffer.try_append(11u8)) { return 0; }
    """
    )
    body = (
        create
        + """
        if (!dual_forward(buffer, other, 0, 17u64, 23u8, true)) { return 0; }
        if (!dual_zero(other, buffer)) { return 0; }
    """
    )
    body += check_state([37], 1) + check_state([31], 1, "other")
    body += """
        builtin::OwnedBytes third_backing = region.try_allocate(1);
        std::ByteBuffer third = std::ByteBuffer(region, move(third_backing));
        if (!third.try_append(59u8)) { return 0; }
        const std::ByteBuffer frozen = move(third);
        if (dual_three_forward(buffer, other, frozen, DualStatus::complete, 41u8, 1) != DualStatus::complete) {
            return 0;
        }
    """
    body += check_state([43], 1) + check_state([41], 1, "other") + check_state([59], 1, "frozen")
    body += "if (!buffer.clear() || !other.clear()) { return 0; } return 42;"
    exe = suite.compile("dual-mutable-writes-forward-swapped-and-const-third", program(body, helpers))
    suite.run(exe, 3, 1, 0, 42, 3, 3, release_order=[3, 2, 1])

    mixed = """
    auto dual_twin(std::ByteBuffer& a, Twin& b) -> bool {
        return a.try_append(17u8) && b.write_first(23u8) && b.write_second(29u8);
    }
    auto dual_twin_forward(std::ByteBuffer& a, Twin& b) -> bool { return dual_twin(a, b); }
    """
    body = CREATE + TWIN_CREATE + "if (!dual_twin_forward(buffer, twin) || twin_sum(twin) != 52) { return 0; }"
    body += check_state([17], 1) + "return 42;"
    exe = suite.compile("dual-mutable-distinct-concrete-classes", program(body, TWIN + mixed))
    suite.run(exe, 3, 1, 0, 42, 3, 3, release_order=[3, 2, 1])

    body = (
        create
        + """
        if (!other.try_append(19u8)) { return 0; }
        const DualStatus status = dual_growth(buffer, other);
        if ((flag == 0 && status != DualStatus::first_failed) ||
            (flag == 1 && status != DualStatus::second_failed) ||
            (flag == 2 && status != DualStatus::complete)) { return 0; }
    """
    )
    for flag, left, right in ((0, 1, 1), (1, 2, 1), (2, 4, 4)):
        body += f"if (flag == {flag}) {{" + check_state([11], left) + check_state([19], right, "other") + "}"
    body += "if (!dual_zero(buffer, other)) { return 0; } return 42;"
    exe = suite.compile("dual-mutable-alternating-resize-preserves-sibling-and-failure", program(body, helpers))
    suite.run(exe, 8, 1, 2, 42, 6, 2, release_order=[1, 2, 3, 4, 6, 5])
    suite.run(exe, 2, 1, 0, 42, 2, 2, release_order=[2, 1])
    suite.run(exe, 3, 1, 1, 42, 3, 2, release_order=[1, 2, 3])
    suite.run(exe, 99, 1, 0, 42, 2, 2, fail_after=2, release_order=[2, 1])
    suite.run(exe, 99, 1, 1, 42, 3, 2, fail_after=3, release_order=[1, 2, 3])

    conflicts = {
        "same-root": "dual_zero(buffer, buffer);",
        "later-first-read": "dual_after(buffer, other, buffer.size(), true);",
        "later-second-read": "dual_after(buffer, other, other.size(), true);",
        "later-first-write": "dual_after(buffer, other, 0, buffer.clear());",
        "later-second-write": "dual_after(buffer, other, 0, other.clear());",
        "later-first-move": "dual_after(buffer, other, consume(region, move(buffer)), true);",
        "later-second-move": "dual_after(buffer, other, consume(region, move(other)), true);",
        "nested-first-conflict": "dual_after(buffer, other, 0, append_one(buffer, 1u8));",
        "nested-second-conflict": "dual_after(buffer, other, 0, append_one(other, 1u8));",
    }
    for index, root in enumerate(("buffer", "other")):
        conflicts[f"live-span-{index}"] = f"const {SPAN} view = {root}.bytes(); dual_zero(buffer, other);"
        conflicts[f"moved-{index}"] = f"std::ByteBuffer moved = move({root}); dual_zero(buffer, other);"
        arguments = "frozen, other" if index == 0 else "buffer, frozen"
        conflicts[f"const-{index}"] = f"const std::ByteBuffer frozen = move({root}); dual_zero({arguments});"
        conflicts[f"join-moved-{index}"] = (
            f"if (flag == 1) {{ std::ByteBuffer moved = move({root}); }} dual_zero(buffer, other);"
        )
        conflicts[f"backedge-moved-{index}"] = (
            f"while (flag == 1) {{ dual_zero(buffer, other); std::ByteBuffer moved = move({root}); }}"
        )
    for name, statement in conflicts.items():
        suite.reject("dual-" + name, program(create + statement + "return 0;", helpers))

    triple_create = (
        create
        + """
        builtin::OwnedBytes third_backing = region.try_allocate(1);
        std::ByteBuffer third = std::ByteBuffer(region, move(third_backing));
    """
    )
    for first, second in ((0, 1), (0, 2), (1, 2)):
        actuals = ["buffer", "other", "third"]
        actuals[second] = actuals[first]
        call = f"dual_three({', '.join(actuals)}, DualStatus::complete, 1u8, 0);"
        suite.reject(f"dual-three-alias-{first}-{second}", program(triple_create + call + "return 0;", helpers))
    for name, body in {
        "same-formal": "return dual_zero(a, a);",
        "same-second-formal": "return dual_zero(b, b);",
        "nested-active-first": "return dual_after(a, b, 0, append_one(a, 1u8));",
        "nested-active-second": "return dual_after(a, b, 0, append_one(b, 1u8));",
        "first-span": f"const {SPAN} view = a.bytes(); return view.size() == 0;",
        "second-span": f"const {SPAN} view = b.bytes(); return view.size() == 0;",
    }.items():
        declaration = f"auto bad(std::ByteBuffer& a, std::ByteBuffer& b) -> bool {{ {body} }}"
        suite.reject("dual-" + name, program("return 0;", helpers + declaration))
    for index in range(2):
        first = "const " if index == 0 else ""
        second = "const "
        declaration = (
            f"auto bad({first}std::ByteBuffer& a, {second}std::ByteBuffer& b) -> bool {{ return dual_zero(a, b); }}"
        )
        suite.reject(f"dual-formal-const-escalation-{index}", program("return 0;", helpers + declaration))
    leading = "std::ByteBuffer& a, std::ByteBuffer& b"
    signatures = {
        "three-mutable": f"auto bad({leading}, std::ByteBuffer& c) -> i64 {{ return 0; }}",
        "mutable-const-mutable": (
            "auto bad(std::ByteBuffer& a, const std::ByteBuffer& b, std::ByteBuffer& c) -> i64 { return 0; }"
        ),
        "four-roots": f"auto bad({leading}, const std::ByteBuffer& c, const Twin& d) -> i64 {{ return 0; }}",
        "seventh-parameter": f"auto bad({leading}, i64 c, i64 d, i64 e, i64 f, i64 g) -> i64 {{ return 0; }}",
        "copied-tail": f"auto bad({leading}, Count copied) -> i64 {{ return 0; }}",
        "span-tail": f"auto bad({leading}, {SPAN} view) -> i64 {{ return 0; }}",
        "owning-tail": f"auto bad({leading}, std::ByteBuffer taken) -> i64 {{ return 0; }}",
        "builtin-root": "auto bad(std::ByteBuffer& a, builtin::OwnedBytes& b) -> i64 { return 0; }",
        "method-parameters": (f"class Bad {{ public: Bad() {{}} auto bad({leading}) -> i64 {{ return 0; }} }};"),
        "nested-owner": (
            "class Nested { std::ByteBuffer child; public: "
            "Nested(builtin::ByteRegion region, std::ByteBuffer initial) : child(move(initial)) {} };"
            "auto bad(std::ByteBuffer& a, Nested& b) -> i64 { return 0; }"
        ),
        "copied-result": f"auto bad({leading}) -> Count {{ return Count(0); }}",
        "owning-result": f"auto bad({leading}) -> std::ByteBuffer {{ return move(a); }}",
        "span-result": f"auto bad({leading}) -> {SPAN} {{ return a.bytes(); }}",
        "const-third-write": f"auto bad({leading}, const std::ByteBuffer& c) -> bool {{ return c.clear(); }}",
    }
    for name, declaration in signatures.items():
        suite.reject("dual-signature-" + name, program("return 0;", helpers + TWIN + declaration))


def dual_region_borrowing_case(suite):
    """Closed test-only ingress constructs two genuine owners in distinct regions.

    No arbitrary host descriptor or pointer-inequality proof is accepted. The
    existing test allocator creates each payload; RAII drops both exact owners.
    Independent ABI facts bind the sole owner field to the handwritten layout.
    """
    source = """
    module dual_region_test;
    class RegionCell {
        builtin::OwnedBytes payload;
    public:
        RegionCell(builtin::ByteRegion region, builtin::OwnedBytes initial) : payload(move(initial)) {}
        auto read_value() const -> u8 { return payload.at(0); }
        auto write_value(u8 value) -> bool { return payload.set(0, value); }
        auto resize(i64 size) -> bool { return payload.try_resize(size); }
        auto size() const -> i64 { return payload.size(); }
    };
    auto grow(RegionCell& a, RegionCell& b) -> i64 {
        if (!a.resize(2)) { return 0; }
        if (!b.resize(2)) { return 1; }
        if (!a.resize(4) || !b.resize(4)) { return -1; }
        return 2;
    }
    auto entry(RegionCell& a, RegionCell& b, i64 flag) -> i64 {
        if (a.read_value() != 11u8 || b.read_value() != 19u8 || grow(a, b) != flag) { return 0; }
        if (a.read_value() != 11u8 || b.read_value() != 19u8) { return 0; }
        if ((flag == 0 && (a.size() != 1 || b.size() != 1)) ||
            (flag == 1 && (a.size() != 2 || b.size() != 1)) ||
            (flag == 2 && (a.size() != 4 || b.size() != 4))) { return 0; }
        if (!a.write_value(31u8) || !b.write_value(37u8) || a.read_value() != 31u8 || b.read_value() != 37u8) {
            return 0;
        }
        return 42;
    }
    """
    # Retain the established allocator, exact trap observer and trace protocol.
    driver = owned_bytes.DRIVER.split("int main(int argc, char **argv) {")[0]
    driver = driver.replace(
        "__au_runtime_bytes_test_entry(std::uint64_t, std::int64_t, std::int64_t)",
        "__au_runtime_bytes_test_entry(void *const *, std::int64_t)",
    )
    driver += r"""
using aurora::hosted::bytes::NativeOwner;
struct Cell {
    NativeOwner payload{};
    Cell(std::uint64_t region, std::uint64_t value) {
        aurora::hosted::bytes::__au_runtime_bytes_allocate(region, 1, &payload);
        if (!payload.success || !aurora::hosted::bytes::__au_runtime_bytes_set(&payload, 0, value))
            std::abort();
    }
    ~Cell() { aurora::hosted::bytes::__au_runtime_bytes_drop(&payload); }
    Cell(const Cell &) = delete;
    Cell &operator=(const Cell &) = delete;
};
static_assert(sizeof(Cell) == 32 && alignof(Cell) == 8 && offsetof(Cell, payload) == 0);
int main(int argc, char **argv) {
    if (argc != 4 && argc != 5)
        return 80;
    struct sigaction action {};
    action.sa_sigaction = trapped;
    action.sa_flags = SA_SIGINFO;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGILL, &action, nullptr) != 0)
        return 81;
    Trace trace;
    trace.remaining = argc == 5 ? std::strtoll(argv[4], nullptr, 10) : -1;
    aurora::hosted::bytes::Allocator allocator {&trace, allocate, deallocate};
    aurora::hosted::bytes::Region left(std::strtoull(argv[1], nullptr, 10), allocator);
    aurora::hosted::bytes::Region right(std::strtoull(argv[2], nullptr, 10), allocator);
    std::uint64_t result = 0;
    {
        Cell a(left.id(), 11), b(right.id(), 19);
        // These are independently allocated live complete owners, not externally
        // supplied descriptors. The array is the existing private two-root ABI.
        alignas(16) void *roots[2] = {&a, &b};
        result = __au_runtime_bytes_test_entry(roots, std::strtoll(argv[3], nullptr, 10));
    }
    const auto a = left.metrics(), b = right.metrics();
    if (a.used != 0 || b.used != 0 || a.live_allocations != 0 || b.live_allocations != 0 ||
        !left.close() || !right.close())
        return 82;
    if (trace.allocated_count != a.successful_allocations + b.successful_allocations ||
        trace.released_count != a.releases + b.releases)
        return 83;
    std::printf("%llu %llu %llu %llu", static_cast<unsigned long long>(result),
                static_cast<unsigned long long>(a.successful_allocations + b.successful_allocations),
                static_cast<unsigned long long>(a.releases + b.releases),
                static_cast<unsigned long long>(a.peak_live_allocations + b.peak_live_allocations));
    for (std::size_t index = 0; index < trace.released_count; ++index)
        std::printf(" %zu", trace.released[index]);
    std::puts("");
}
"""
    bridge = r"""
.text
.globl __au_runtime_bytes_test_entry
.type __au_runtime_bytes_test_entry, @function
__au_runtime_bytes_test_entry:
    pushq %rbp
    movq %rsp, %rbp
    movq %rdi, %r10
    movq %rsi, %rdi
    call ENTRY
    leave
    ret
.size __au_runtime_bytes_test_entry, .-__au_runtime_bytes_test_entry
.globl __au_runtime_bytes_test_bounds
.set __au_runtime_bytes_test_bounds, .Laurora_bounds_trap
"""
    original_driver, original_objects, original_bridge = suite.driver, suite.host_objects, owned_bytes.BRIDGE
    try:
        suite.driver = suite.directory / "dual-region-driver.cpp"
        suite.driver.write_text(driver)
        suite.host_objects = None
        owned_bytes.BRIDGE = bridge
        exe = suite.compile("dual-mutable-different-region-resize-and-failure", source)
    finally:
        suite.driver, suite.host_objects, owned_bytes.BRIDGE = original_driver, original_objects, original_bridge
    if exe is not None:
        facts = exe.parent / "layout.abi.json"
        result = owned_bytes.command(
            [suite.compiler, exe.parent / "input.au", "--abi-facts", facts, "-o", exe.parent / "layout.s"]
        )
        require(result.returncode == 0, f"dual-region layout facts failed: {result.stderr.decode()}")
        records = json.loads(facts.read_text())["records"]
        rows = [row for row in records.values() if row["source_name"] == "RegionCell"]
        require(len(rows) == 1, "expected one concrete RegionCell layout")
        row = rows[0]
        require(row["size"] == 32 and row["alignment"] == 8, "RegionCell layout differs from trusted host")
        require(len(row["fields"]) == 1, "RegionCell must contain exactly one owner")
        field = row["fields"][0]
        require(
            field["name"] == "payload" and field["kind"] == "owner" and field["offset"] == 0 and field["bytes"] == 32,
            "RegionCell owner field layout mismatch",
        )
    suite.run(exe, 4, 4, 2, 42, 6, 2, release_order=[1, 2, 3, 4, 6, 5])
    suite.run(exe, 1, 4, 0, 42, 2, 2, release_order=[2, 1])
    suite.run(exe, 4, 1, 1, 42, 3, 2, release_order=[1, 2, 3])
    suite.run(exe, 4, 4, 0, 42, 2, 2, fail_after=2, release_order=[2, 1])
    suite.run(exe, 4, 4, 1, 42, 3, 2, fail_after=3, release_order=[1, 2, 3])


def bounded_root_facts(suite, executable):
    """Bind the adapter to real emitted roots, independently of fixed host entries."""
    if executable is None:
        return  # The explicitly partial smoke profile omits this program.
    import sys
    from copy import deepcopy

    sys.path.insert(0, str(ROOT / "scripts"))
    from bootstrap_frontend import abi_declaration, normalize_function_abi

    output = executable.parent / "roots.abi.json"
    result = owned_bytes.command(
        [
            suite.compiler,
            *suite.module_args,
            executable.parent / "input.au",
            "--abi-facts",
            output,
            "-o",
            executable.parent / "roots.s",
        ]
    )
    require(result.returncode == 0, f"bounded root facts emission failed: {result.stderr.decode()}")
    facts = json.loads(output.read_text())
    pristine = deepcopy(facts)
    accepted, rejected = [], []
    owner, _ = abi_declaration(facts, "records", "std::ByteBuffer")
    copied, _ = abi_declaration(facts, "records", "Count")
    for count in range(1, 4):
        for mutable in range(min(count, 2) + 1):
            for tail in range(7 - count):
                for prefix in ("", "forward_"):
                    source = f"{prefix}roots_{count}_{mutable}_{tail}"
                    _, function = abi_declaration(facts, "functions", source)
                    require(
                        function["borrowed_roots"]
                        == [dict(ordinal=i, selector=-i, type_name=owner, mutable=i < mutable) for i in range(count)],
                        f"emitted root authority/order differs: {source}",
                    )
                    require(function["borrowed_root_count"] == count, f"emitted root count differs: {source}")
                    require(
                        function["borrowed_root_abi"]
                        == dict(
                            kind="direct" if count == 1 else "tuple",
                            register="r10",
                            tuple_payload_bytes=8 * count if count > 1 else 0,
                            tuple_reserved_bytes=16 * ((count + 1) // 2) if count > 1 else 0,
                            saved_root_reserved_bytes=16 * ((count + 1) // 2),
                        ),
                        f"emitted root transport differs: {source}",
                    )
                    require(
                        normalize_function_abi(facts, function) == function, f"root normalization differs: {source}"
                    )
                    accepted.append(source)
    # Also preserve real zero-root functions, methods and single-root copied tails.
    for function in facts["functions"].values():
        require(normalize_function_abi(facts, function) == function, "existing emitted ABI normalization differs")

    _, triple = abi_declaration(facts, "functions", "roots_3_2_1")

    def reject(label, mutation, expected):
        function = deepcopy(triple)
        mutation(function)
        try:
            normalize_function_abi(facts, function)
        except ValueError as error:
            require(str(error) == expected, f"{label} failed the wrong guard: {error}")
            rejected.append(dict(case=label, guard=expected))
            return
        raise AssertionError("unsafe bounded root facts accepted: " + label)

    lane_error = "invalid compiler ABI borrowed root lane"
    for lane in range(3):
        for key, value in (
            ("ordinal", 4),
            ("ordinal", False),
            ("selector", -6),
            ("selector", False),
            ("type_name", 1),
            ("type_name", "missing-root"),
            ("type_name", copied),
            ("mutable", 1),
            ("extra", 0),
        ):
            reject(
                f"lane {lane} {key}={value!r}",
                lambda f, lane=lane, key=key, value=value: f["borrowed_roots"][lane].__setitem__(key, value),
                lane_error,
            )
        reject(
            f"lane {lane} missing selector", lambda f, lane=lane: f["borrowed_roots"][lane].pop("selector"), lane_error
        )
        reject(
            f"lane {lane} not a record", lambda f, lane=lane: f["borrowed_roots"].__setitem__(lane, None), lane_error
        )
    for label, mutate in (
        ("const then mutable", lambda f: f["borrowed_roots"][0].__setitem__("mutable", False)),
        ("third mutable", lambda f: f["borrowed_roots"][2].__setitem__("mutable", True)),
        (
            "nonleading mutable",
            lambda f: (
                f["borrowed_roots"][1].__setitem__("mutable", False),
                f["borrowed_roots"][2].__setitem__("mutable", True),
            ),
        ),
        ("reversed lanes", lambda f: f["borrowed_roots"].reverse()),
    ):
        reject(label, mutate, lane_error)
    # All builtin lane metadata is otherwise valid: reject the mixture itself,
    # not an unknown key, missing descriptor, bad element or unknown record.
    reject(
        "builtin mixed with concrete owners",
        lambda f: f["borrowed_roots"].__setitem__(
            1,
            dict(
                ordinal=1,
                selector=-1,
                mutable=True,
                type_name="builtin::OwnedValues",
                kind="owned_values",
                element_type_name=copied,
                descriptor_bytes=32,
            ),
        ),
        "invalid compiler ABI borrowed typed buffer",
    )
    for label, mutate in (
        ("boolean count", lambda f: f.__setitem__("borrowed_root_count", True)),
        ("missing lane", lambda f: f["borrowed_roots"].pop()),
        (
            "four complete lanes",
            lambda f: (
                f["borrowed_roots"].append(dict(ordinal=3, selector=-3, type_name=owner, mutable=False)),
                f.__setitem__("borrowed_root_count", 4),
                f["borrowed_root_abi"].update(tuple_payload_bytes=32),
            ),
        ),
    ):
        reject(label, mutate, "invalid compiler ABI borrowed root count")
    reject(
        "method receiver collision",
        lambda f: f.update(receiver=owner, receiver_mutable=True),
        "borrowed roots cannot also grant a method receiver",
    )
    reject(
        "receiver flag without receiver",
        lambda f: f.update(receiver_mutable=True),
        "invalid compiler ABI receiver facts",
    )
    for key, value in (
        ("kind", "direct"),
        ("register", "r11"),
        ("tuple_payload_bytes", 16),
        ("tuple_reserved_bytes", 16),
        ("saved_root_reserved_bytes", 16),
        ("extra", 0),
    ):
        reject(
            f"transport {key}",
            lambda f, key=key, value=value: f["borrowed_root_abi"].__setitem__(key, value),
            "invalid compiler ABI borrowed root transport",
        )
    for shape in (
        dict(kind="class", type_name=copied, bytes=facts["records"][copied]["reserved"]),
        dict(kind="span", bytes=facts["span_bytes"]),
        dict(kind="region", bytes=8),
        dict(kind="owner", bytes=32),
    ):
        reject(
            f"non-scalar tail {shape['kind']}",
            lambda f, shape=shape: f.update(parameters=[dict(offset=0, **shape)], parameter_bytes=shape["bytes"]),
            "invalid compiler ABI borrowed root tail",
        )
        reject(
            f"non-scalar result {shape['kind']}",
            lambda f, shape=shape: f.update(result=shape),
            "invalid compiler ABI borrowed root tail",
        )
    reject(
        "seventh parameter",
        lambda f: f.update(parameters=[dict(offset=8 * i, bytes=8, kind="i64") for i in range(4)], parameter_bytes=32),
        "invalid compiler ABI borrowed root tail",
    )
    require(facts == pristine, "bounded root mutations changed emitted facts")
    require(len(accepted) == 78 and len(rejected) == 58, "bounded root ABI case inventory changed")
    (executable.parent / "roots-validation.json").write_text(
        json.dumps(dict(accepted=accepted, rejected=rejected), indent=2) + "\n"
    )
    print("PASS 78 emitted root/forward/tail shapes and 58 isolated malformed root guards")


def bounded_borrowing_cases(suite):
    """One compact real program crosses every prefix/tail boundary and forwards it."""
    definitions = [HELPERS, "enum class RootMode { zero, one };"]
    checks = []
    for roots in range(1, 4):
        for mutable in range(min(roots, 2) + 1):
            for tail in range(7 - roots):
                name = f"roots_{roots}_{int(mutable)}_{tail}"
                formals = [f"{'' if index < mutable else 'const '}std::ByteBuffer& r{index}" for index in range(roots)]
                formals += [f"{'RootMode' if index % 2 else 'i64'} a{index}" for index in range(tail)]
                body = "".join(f"if (!r{index}.clear()) {{ return -1; }}" for index in range(mutable))
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
        f"{'' if index < 2 else 'const '}std::ByteBuffer v{index} = std::ByteBuffer(region, move(allocation{index}));"
        f"if (!v{index}.ok()) {{ return -7; }}"
        for index in range(3)
    )
    actuals = ", ".join(f"v{index}" for index in range(3))
    body = create + "".join(checks)
    body += f"if (roots_enum({actuals}) != RootMode::one) {{ return 0; }}"
    body += f"if (flag == 1 && roots_growth({actuals})) {{ return 0; }}"
    body += "".join(f"if (v{index}.capacity() != n || v{index}.size() != 0) {{ return 0; }}" for index in range(3))
    executable = suite.compile("bounded-roots-one-through-three", program(body + "return 42;", "".join(definitions)))
    bounded_root_facts(suite, executable)
    for length in (0, 2):
        suite.run(executable, 3 * length, length, 0, 42, 3, 3)
        suite.run(executable, 3 * length, length, 1, 42, 3, 3, fail_after=3)
    suite.run(executable, 100, 2, 1, 42, 3, 3, fail_after=3)
    suite.run(executable, 12, 2, 0, -7, 2, 2, fail_after=2)
    suite.run(executable, 5, 2, 0, -7, 2, 2)

    # All-readonly duplicate roots must reject too, even when every successful
    # allocation is empty and every nominal class is the same.
    for roots in range(2, 4):
        for first in range(roots):
            for second in range(first + 1, roots):
                arguments = [f"v{index}" for index in range(roots)]
                arguments[second] = arguments[first]
                call = f"roots_{roots}_0_0({', '.join(arguments)});"
                suite.reject(
                    f"bounded-readonly-alias-{roots}-{first}-{second}",
                    program(create + call + "return 0;", "".join(definitions)),
                    "borrowed arguments require distinct owning roots",
                )
    readonly = ", ".join(f"const std::ByteBuffer& r{index}" for index in range(3))
    for ordinal in range(3):
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
    four = ", ".join(f"const std::ByteBuffer& r{index}" for index in range(4))
    suite.reject(
        "bounded-four-roots",
        program("return 0;", HELPERS + f"auto bad({four}) -> i64 {{ return 0; }}"),
        "borrowed functions require one to three leading concrete owning-class references",
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
    for ordinal in range(1, 3):
        formals = ", ".join(f"{'' if index == ordinal else 'const '}std::ByteBuffer& r{index}" for index in range(3))
        suite.reject(
            f"bounded-later-mutable-root-{ordinal}",
            program("return 0;", f"auto bad({formals}) -> i64 {{ return 0; }}"),
            "borrowed parameters require a supported leading ownership reference signature",
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
        "formal-move-to-local": "borrowed object parameters cannot transfer ownership",
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
        "three-mutable-borrows": (
            "auto bad(std::ByteBuffer& a, std::ByteBuffer& b, std::ByteBuffer& c) -> i64 { return 0; }"
        ),
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
        "nonowning-class-reference": "auto bad(Count& input) -> i64 { return input.get(); }",
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
    result_diagnostic = "borrowed functions require one to three leading concrete owning-class references"
    later_diagnostic = "borrowed-function tails require scalar or enum values"
    signature_diagnostics = {
        "nonleading-borrow": declaration_diagnostic,
        "three-mutable-borrows": declaration_diagnostic,
        "borrow-after-region": declaration_diagnostic,
        "borrow-and-owning-parameter": later_diagnostic,
        "borrow-and-owned-bytes-parameter": later_diagnostic,
        "borrow-and-region-parameter": later_diagnostic,
        "borrowed-owning-result": result_diagnostic,
        "borrowed-reference-result": "expected '{'",
        "borrowed-span-result": "only scalar function results or scalar-field class values are supported",
        "nonowning-class-reference": result_diagnostic,
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
    parser.add_argument("--compile-only", action="store_true")
    parser.add_argument(
        "--smoke", action="store_true", help="partial developer profile: two native programs and seven rejections"
    )
    parser.add_argument("--artifacts", type=Path, help="retain this run in a new directory")
    args = parser.parse_args()
    compiler = args.compiler.resolve(strict=True)
    before = hashlib.sha256(compiler.read_bytes()).hexdigest()
    directory = args.artifacts
    if directory is None:
        directory = Path(tempfile.mkdtemp(prefix="aurora-borrowed-objects-"))
    else:
        directory.mkdir(parents=True, exist_ok=False)
    inputs = {path: path.read_bytes() for path in (ROOT / "library").rglob("*.au")}
    for path in (
        Path(__file__).resolve(),
        ROOT / "scripts/bootstrap_frontend.py",
        ROOT / "scripts/frontend_bridge.py",
        ROOT / "tests/compiler/byte_buffer.py",
        ROOT / "tests/compiler/owned_bytes.py",
        ROOT / "tests/compiler/unsigned_oracle.py",
        ROOT / "runtime/hosted_bytes.cpp",
        ROOT / "runtime/hosted_bytes.hpp",
    ):
        inputs[path] = path.read_bytes()
    commands = []
    original_command = owned_bytes.command

    def recorded_command(argv, **kwargs):
        record = {"argv": [str(part) for part in argv], "kwargs": kwargs}
        commands.append(record)
        (directory / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        result = original_command(argv, **kwargs)
        record.update(returncode=result.returncode, stdout_hex=result.stdout.hex(), stderr_hex=result.stderr.hex())
        (directory / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        return result

    owned_bytes.command = recorded_command
    byte_buffer.command = recorded_command
    passed = False
    try:
        suite = BorrowSuite(compiler, directory, args.compile_only, args.smoke)
        (directory / "inputs.json").write_text(
            json.dumps(
                {
                    "compiler_sha256": before,
                    "profile": suite.profile,
                    "partial_coverage": args.smoke,
                    "compile_only": args.compile_only,
                    "requested_programs": list(SMOKE_PROGRAMS) if args.smoke else "all",
                    "requested_rejections": list(SMOKE_REJECTIONS) if args.smoke else "all",
                    "inputs": {str(path): hashlib.sha256(content).hexdigest() for path, content in inputs.items()},
                },
                indent=2,
            )
            + "\n"
        )
        borrowing_cases(suite)
        paired_borrowing_cases(suite)
        dual_mutable_borrowing_cases(suite)
        dual_region_borrowing_case(suite)
        bounded_borrowing_cases(suite)
        direct_method_return_case(suite)
        multiple_field_cases(suite)
        json_cases(suite)
        rejection_cases(suite)
        independent_json_import(suite)
        suite.check_selection()
        require(hashlib.sha256(compiler.read_bytes()).hexdigest() == before, "compiler changed during gate")
        for path, content in inputs.items():
            require(path.read_bytes() == content, f"bound input changed: {path}")
        (directory / "summary.json").write_text(
            json.dumps(
                {
                    "compiler_sha256": before,
                    "profile": suite.profile,
                    "partial_coverage": args.smoke,
                    "full_borrowed_objects_gate": not args.smoke and not args.compile_only,
                    "selected_programs": suite.selected_programs,
                    "selected_rejections": suite.selected_rejections,
                    "omitted_programs": suite.omitted_programs,
                    "omitted_rejections": suite.omitted_rejections,
                    "programs": suite.programs,
                    "native_cases": suite.native,
                    "rejection_fixtures": suite.rejections,
                    "rejection_executions": 2 * suite.rejections,
                    "skipped_native_cases": suite.skipped_native,
                    "compile_only": args.compile_only,
                    "passed": True,
                },
                indent=2,
            )
            + "\n"
        )
        print(
            f"PASS borrowed objects [profile={suite.profile}, compile_only={args.compile_only}]: "
            f"{suite.programs} programs, {suite.native} native cases, "
            f"{suite.rejections} rejections, {suite.skipped_native} native cases skipped"
        )
        print(f"compiler_sha256={before}")
        passed = True
    finally:
        owned_bytes.command = original_command
        byte_buffer.command = original_command
        if passed and args.artifacts is None:
            shutil.rmtree(directory)
        else:
            print(f"artifacts={directory}")


if __name__ == "__main__":
    main()
