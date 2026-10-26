#!/usr/bin/env python3
"""Focused source/native ownership tests, using the real hosted bootstrap adapter.

No alternate interpreter or fixed buffer models allocation. A trusted scalar-return
bridge grants one region for each invocation. The driver checks that its grant can
close, reports real allocation counters, and verifies bounds traps at the exact
emitted UD2. Generated Aurora assembly is not sanitizer-instrumented.

All programs of a run are packed into one compiled and linked binary
(native_runner.py); AURORA_CASE selects the program an invocation runs.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import threading

import native_runner
from native_runner import require

ROOT = Path(__file__).resolve().parents[2]
REGION = "builtin::ByteRegion"
OWNER = "builtin::OwnedBytes"
MASK = (1 << 64) - 1

DRIVER = r"""
#include "runtime/hosted_bytes.hpp"
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <ucontext.h>
#include <unistd.h>
extern "C" std::uint64_t __au_runtime_bytes_test_entry(std::uint64_t, std::int64_t, std::int64_t);
extern "C" const unsigned char __au_runtime_bytes_test_bounds[];
extern "C" std::uint64_t __au_runtime_bytes_test_case;
extern "C" const std::uint64_t __au_runtime_bytes_test_count;
static void trapped(int signal, siginfo_t *info, void *context) {
    const auto *frame = static_cast<const ucontext_t *>(context);
    const auto pc = static_cast<std::uintptr_t>(frame->uc_mcontext.gregs[REG_RIP]);
    const auto expected = reinterpret_cast<std::uintptr_t>(__au_runtime_bytes_test_bounds);
    if (signal == SIGILL && info->si_code > 0 && pc == expected &&
        __au_runtime_bytes_test_bounds[0] == 0x0f && __au_runtime_bytes_test_bounds[1] == 0x0b) {
        constexpr char message[] = "exact-bounds-trap\n";
        (void)!write(STDOUT_FILENO, message, sizeof(message) - 1);
        _exit(77);
    }
    _exit(78);
}
// Bounded observation storage belongs to this test host, not the allocation API.
struct Trace {
    std::int64_t remaining = -1;
    bool observe_attempts = false;
    std::size_t attempted_sizes[128] {};
    std::size_t attempted_count = 0;
    void *allocations[128] {};
    bool live[128] {};
    std::size_t released[128] {};
    std::size_t allocated_count = 0;
    std::size_t released_count = 0;
};
static void *allocate(void *context, std::size_t size) noexcept {
    auto &trace = *static_cast<Trace *>(context);
    if (trace.observe_attempts) {
        if (trace.attempted_count == 128)
            std::abort();
        trace.attempted_sizes[trace.attempted_count++] = size;
    }
    if (trace.remaining == 0)
        return nullptr;
    if (trace.remaining > 0)
        --trace.remaining;
    if (trace.allocated_count == 128)
        std::abort();
    void *memory = std::malloc(size);
    if (memory != nullptr) {
        trace.allocations[trace.allocated_count] = memory;
        trace.live[trace.allocated_count++] = true;
    }
    return memory;
}
static void deallocate(void *context, void *address) noexcept {
    auto &trace = *static_cast<Trace *>(context);
    for (std::size_t index = 0; index < trace.allocated_count; ++index) {
        if (trace.live[index] && trace.allocations[index] == address) {
            trace.live[index] = false;
            trace.released[trace.released_count++] = index + 1;
            std::free(address);
            return;
        }
    }
    std::abort();
}
int main(int argc, char **argv) {
    if (argc != 4 && argc != 5 && argc != 6)
        return 80;
    // One linked binary holds every program of a run; AURORA_CASE selects one.
    const char *selected = std::getenv("AURORA_CASE");
    __au_runtime_bytes_test_case = selected == nullptr ? 0 : std::strtoull(selected, nullptr, 10);
    if (__au_runtime_bytes_test_case >= __au_runtime_bytes_test_count)
        return 79;
    struct sigaction action {};
    action.sa_sigaction = trapped;
    action.sa_flags = SA_SIGINFO;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGILL, &action, nullptr) != 0)
        return 81;
    Trace trace;
    trace.remaining = argc >= 5 ? std::strtoll(argv[4], nullptr, 10) : -1;
    trace.observe_attempts = argc == 6;
    aurora::hosted::bytes::Allocator allocator {&trace, allocate, deallocate};
    aurora::hosted::bytes::Region region(std::strtoull(argv[1], nullptr, 10), allocator);
    const auto result = __au_runtime_bytes_test_entry(region.id(), std::strtoll(argv[2], nullptr, 10),
                                 std::strtoll(argv[3], nullptr, 10));
    const auto state = region.metrics();
    if (state.used != 0 || state.live_allocations != 0 || !region.close())
        return 82;
    if (trace.allocated_count != state.successful_allocations || trace.released_count != state.releases)
        return 83;
    std::printf("%llu %llu %llu %llu", static_cast<unsigned long long>(result),
                static_cast<unsigned long long>(state.successful_allocations),
                static_cast<unsigned long long>(state.releases),
                static_cast<unsigned long long>(state.peak_live_allocations));
    for (std::size_t index = 0; index < trace.released_count; ++index)
        std::printf(" %zu", trace.released[index]);
    std::puts("");
    if (trace.observe_attempts) {
        for (std::size_t index = 0; index < trace.attempted_count; ++index)
            std::printf("%zu ", trace.attempted_sizes[index]);
        std::puts("");
    }
}
"""


def bridge(entries):
    """Region/n/flag bridge to the selected resource entry, following the compiler's caller convention."""
    lines = [
        ".text",
        ".globl __au_runtime_bytes_test_entry",
        ".type __au_runtime_bytes_test_entry, @function",
        "__au_runtime_bytes_test_entry:",
        "    pushq %rbp",
        "    movq %rsp, %rbp",
        "    subq $32, %rsp",
        "    movq %rdi, (%rsp)",
        "    movq %rsi, 8(%rsp)",
        "    movq %rdx, 16(%rsp)",
        "    movq $0, 24(%rsp)",
        "    movq __au_runtime_bytes_test_case(%rip), %rax",
        "    leaq .Lbytes_test_table(%rip), %rcx",
        "    movq (%rcx,%rax,8), %rax",
        "    movq %rsp, %r11",
        "    call *%rax",
        "    leave",
        "    ret",
        ".size __au_runtime_bytes_test_entry, .-__au_runtime_bytes_test_entry",
        ".globl __au_runtime_bytes_test_bounds",
        ".set __au_runtime_bytes_test_bounds, .Laurora_bounds_trap",
        ".data",
        ".balign 8",
        ".globl __au_runtime_bytes_test_case",
        "__au_runtime_bytes_test_case:",
        "    .quad 0",
        '.section .data.rel.ro,"aw"',
        ".balign 8",
        ".globl __au_runtime_bytes_test_count",
        "__au_runtime_bytes_test_count:",
        f"    .quad {len(entries)}",
        ".Lbytes_test_table:",
        *(f"    .quad {entry}" for entry in entries),
        ".text",
        "",
    ]
    return "\n".join(lines)


def bridged_assembly(text, entry):
    """Compiler output, which owns the one non-executable-stack note, plus the bridge for one entry."""
    notes = [line.strip() for line in text.splitlines() if ".note.GNU-stack" in line]
    require(notes == ['.section .note.GNU-stack,"",@progbits'], "bridge requires one non-executable-stack note")
    return text + "\n" + bridge([entry])


def program(body, helpers=""):
    return f"module owned_bytes;{helpers}auto entry({REGION} region,i64 n,i64 flag)->i64{{{body}}}"


HOST_FLAGS = ("-std=c++23", "-O2", "-Wall", "-Wextra", "-Wpedantic", "-Werror")


def command(args, timeout=30):
    return subprocess.run([str(arg) for arg in args], capture_output=True, timeout=timeout, check=False)


def last_function(text):
    """Old default entry: the last non-reflection native function of the program."""
    symbols = re.findall(r"^\.type ([A-Za-z_][A-Za-z_0-9]*), @function$", text, re.M)
    entries = [symbol for symbol in symbols if not symbol.startswith(("aurora_reflect_", "__au_reflect_"))]
    require(entries, "no native function")
    return entries[-1]


def named_function(name):
    def select(text):
        symbols = re.findall(r"^\.type ([A-Za-z_][A-Za-z_0-9]*), @function$", text, re.M)
        selected = [symbol for symbol in symbols if symbol == name or symbol.endswith(f"__d{len(name)}{name}")]
        require(len(selected) == 1, f"expected one entry named {name}, found {selected}")
        return selected[0]

    return select


class HostedBytes:
    """native_runner harness: the C++ allocation driver and hosted byte runtime."""

    def __init__(self, suite):
        self.suite = suite

    def prepare(self, directory):
        # Compile the driver and runtime adapter once per run.
        self.objects = []
        for source in (self.suite.driver, ROOT / "runtime/hosted_bytes.cpp"):
            output = Path(directory) / (source.stem + ".o")
            result = command([*self.suite.cxx, *HOST_FLAGS, "-I", ROOT, "-c", source, "-o", output], timeout=120)
            require(result.returncode == 0, f"host object {source.name} failed: {result.stderr.decode()}")
            self.objects.append(output)

    def glue(self, entries, values, text):
        for entry in entries:
            require(f".local {entry}\n" in text, f"resource entry {entry} must stay private")
        return bridge(entries)

    def link(self, objects, binary):
        result = command([*self.suite.cxx, *HOST_FLAGS, *self.objects, *objects, "-o", binary], timeout=120)
        require(result.returncode == 0, f"host link failed: {result.stderr.decode()}")

    def invoke(self, binary, index, arguments, timeout):
        return native_runner.run([binary, *arguments], timeout, env={**os.environ, "AURORA_CASE": str(index)})


class Suite:
    """Hosted programs: `compile` then `run`/`trap` invocations, then `finish`.

    With deferred=True every program is packed into one binary built by
    `finish()`. Without it (the interface other tests still use) each
    `compile` links its own program now and `run` executes immediately.
    """

    def __init__(self, compiler, directory, module_root=None, entry_name=None, *, deferred=False, label="owned bytes"):
        self.compiler = compiler
        self.module_args = [] if module_root is None else ["--module-root", module_root]
        self.entry_name = entry_name
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.deferred = deferred
        self.native = self.rejections = self.programs = self.traps = 0
        self.cxx = shlex.split(os.environ.get("CXX", "g++"))
        self.driver = self.directory / "driver.cpp"
        self.driver.write_text(DRIVER)
        self.lock = threading.Lock()
        self.runner = native_runner.Suite(
            compiler, label, module_roots=self.roots(), harness=HostedBytes(self), directory=self.directory
        )

    def roots(self):
        arguments = [str(argument) for argument in self.module_args]
        return [Path(arguments[i + 1]) for i in range(0, len(arguments), 2) if arguments[i] == "--module-root"]

    def compile(self, name, source, entry_name=None, *, modules=None, inspect=None, standalone=False):
        entry = entry_name or self.entry_name
        if self.deferred:
            return self.runner.program(
                name, source, entry=entry or "entry", modules=modules, inspect=inspect, standalone=standalone
            )
        self.runner.module_roots = self.roots()
        self.runner.start(self.directory)
        # The program's folder keeps its name: callers key observations by executable.parent.name.
        binary, text = self.runner.build(
            name,
            source,
            named_function(entry) if entry else last_function,
            modules=modules,
            folder=self.directory / name,
        )
        if inspect is not None:
            inspect(text)
        self.programs += 1
        return binary

    def _invoke(self, executable, arguments, check):
        if self.deferred:
            executable.invoke(arguments, check)
            return
        result = command([executable, *arguments])
        self.last_observation = result
        check(result)

    def run(
        self,
        executable,
        quota,
        length,
        flag,
        expected,
        allocations,
        peak,
        fail_after=None,
        release_order=None,
        attempted_sizes=None,
    ):
        arguments = [quota, length, flag]
        if fail_after is not None or attempted_sizes is not None:
            arguments.append(-1 if fail_after is None else fail_after)
        if attempted_sizes is not None:
            arguments.append("trace-attempts")
        label = f"{getattr(executable, 'name', executable)} {arguments}"

        def check(result):
            require(result.returncode == 0, f"{label}: execution failed {result.returncode}: {result.stderr!r}")
            lines = result.stdout.splitlines()
            require(len(lines) == (1 if attempted_sizes is None else 2), f"{label}: unexpected allocator trace")
            observed = [int(part) for part in lines[0].split()]
            if attempted_sizes is not None:
                attempts = [int(part) for part in lines[1].split()]
                require(attempts == attempted_sizes, f"{label}: wrong allocation attempts {attempts}")
            require(
                observed[:4] == [expected & MASK, allocations, allocations, peak],
                f"{label}: observed {observed}, expected {expected, allocations, peak}",
            )
            require(sorted(observed[4:]) == list(range(1, allocations + 1)), f"{label}: allocation/free mismatch")
            if release_order is not None:
                require(observed[4:] == release_order, f"{label}: wrong cleanup order {observed[4:]}")
            with self.lock:
                self.native += 1

        self._invoke(executable, arguments, check)

    def trap(self, executable, quota, length, flag=0):
        label = f"{getattr(executable, 'name', executable)} trap {[quota, length, flag]}"

        def check(result):
            require(
                result.returncode == 77 and result.stdout == b"exact-bounds-trap\n",
                f"{label}: wrong fault {result.returncode}: {result.stdout!r}",
            )
            with self.lock:
                self.traps += 1

        self._invoke(executable, [quota, length, flag], check)

    def reject(self, name, source, diagnostic=True, *, modules=None):
        if self.deferred:
            self.runner.reject(name, source, diagnostic, modules=modules)
            return
        # Immediate mode keeps the interface its remaining users record: an absent
        # and then an existing output, each compiled through `command`.
        folder = self.directory / ("reject-" + name)
        folder.mkdir()
        input_path = folder / "input.au"
        output = folder / "output.s"
        input_path.write_text(source)
        for prior in (None, b"preserve existing output\n"):
            if prior is not None:
                output.write_bytes(prior)
            result = command([self.compiler, *self.module_args, input_path, "-o", output])
            require(result.returncode == 1 and result.stderr, f"{name}: expected clean rejection, got {result}")
            if diagnostic is not True:
                require(diagnostic in result.stderr.decode(), f"{name}: wrong diagnostic {result.stderr!r}")
            require(
                (not output.exists()) if prior is None else output.read_bytes() == prior,
                f"{name}: rejection modified output",
            )
        require(input_path.read_text() == source, f"{name}: rejection modified its input")
        self.rejections += 1

    def finish(self):
        counts = self.runner.finish()
        self.programs, self.rejections = counts["programs"], counts["rejections"]
        return counts


def zero_references(rows):
    """One GNU reference object: snippets plus native register/byte observations."""
    snippets, wrappers, data, entries = [], [], [], []
    registers = (
        "rax",
        "rbx",
        "rcx",
        "rdx",
        "rsi",
        "rdi",
        "r8",
        "r9",
        "r10",
        "r11",
        "r12",
        "r13",
        "r14",
        "r15",
        "rbp",
        "rsp",
    )
    seeds = {name: 0x1234567800000100 + index for index, name in enumerate(registers)}
    for index, (count, offset) in enumerate(rows):
        instructions = ""
        if count:
            instructions = (
                "    pushq %rax\n    pushq %rdi\n    pushq %rcx\n"
                f"    leaq {offset}(%r10), %rdi\n    movl $0, %eax\n"
                f"    movl ${count}, %ecx\n    cld\n    rep stosb\n"
                "    popq %rcx\n    popq %rdi\n    popq %rax\n"
            )
        snippets.append(instructions)
        # Reviewed flag patterns exercise both clear/set arithmetic bits with DF
        # set on entry. The helper must establish forward traversal, not assume it.
        for flags in (0x402, 0xCD7):
            name = f"zero_native_{index}_{flags}"
            entries.append(name)
            out = [f"{name}:", "movq %rsp, zero_saved_rsp(%rip)"]
            if count:
                out += [
                    f"leaq zero_buffer_{index}(%rip), %rdi",
                    f"movq ${offset + count + 32}, %rcx",
                    "movq $165, %rax",
                    "cld",
                    "rep stosb",
                ]
            out += [f"movabsq ${value}, %{reg}" for reg, value in seeds.items() if reg not in ("r10", "rsp")]
            out += [f"leaq zero_buffer_{index}+16(%rip), %r10" if count else "movq $0, %r10"]
            out += [f"pushq ${flags}", "popfq", f"call reference_zero_{index}"]
            out += [f"movq %{reg}, zero_observed+{at * 8}(%rip)" for at, reg in enumerate(registers)]
            out += [
                "pushfq",
                "popq zero_flags(%rip)",
                "cld",
                "movq zero_flags(%rip), %rax",
                "andq $3285, %rax",
                f"cmpq ${flags & (0x8D5 if count else 0xCD5)}, %rax",
                "jne .Lzero_fail",
            ]
            for at, reg in enumerate(registers):
                if reg == "rsp":
                    out += ["movq zero_saved_rsp(%rip), %rax"]
                elif reg == "r10":
                    out += [f"leaq zero_buffer_{index}+16(%rip), %rax" if count else "movq $0, %rax"]
                else:
                    out += [f"movabsq ${seeds[reg]}, %rax"]
                out += [f"cmpq %rax, zero_observed+{at * 8}(%rip)", "jne .Lzero_fail"]
            if count or offset < 4096:
                out += [
                    f"leaq zero_buffer_{index}(%rip), %rdi",
                    f"leaq zero_expected_{index}(%rip), %rsi",
                    f"movq ${offset + count + 32}, %rcx",
                    "repe cmpsb",
                    "jne .Lzero_fail",
                ]
            out += ["movq $42, %rax", "ret"]
            wrappers.append("\n".join(out))
        if count or offset < 4096:
            data += [
                f"zero_buffer_{index}: .fill {offset + count + 32},1,165",
                f"zero_expected_{index}: .fill {offset + 16},1,165",
                f".fill {count},1,0",
                ".fill 16,1,165",
            ]
    start = [".globl _start", "_start:"]
    for name in entries:
        start += [f"call {name}", "cmpq $42, %rax", "jne .Lzero_exit_fail"]
    start += [
        "movq $60, %rax",
        "movq $0, %rdi",
        "syscall",
        ".Lzero_exit_fail:",
        "movq $60, %rax",
        "movq $1, %rdi",
        "syscall",
        ".Lzero_fail:",
        "cld",
        "movq $-1, %rax",
        "ret",
    ]
    native = "\n".join(
        wrappers
        + start
        + [".data"]
        + data
        + [
            ".bss",
            ".balign 8",
            "zero_saved_rsp: .zero 8",
            "zero_flags: .zero 8",
            "zero_observed: .zero 128",
            ".text",
            "",
        ]
    )
    return snippets, native


class OwnedBytesCases(Suite):
    """The owned-bytes and typed-owner program families."""

    def typed_borrow_cases(self, node, owner):
        helpers = (
            node
            + f"""
            auto append_row({owner}& rows, i64 count, Node row) -> bool {{
                if (count == rows.size()) {{
                    if (!rows.try_resize(count + 1, row)) {{ return false; }}
                }}
                return rows.set(count, row);
            }}
            auto forward_row({owner}& rows, i64 count, Node row) -> bool {{
                return append_row(rows, count, row);
            }}
        """
        )
        local_body = f"""
            const Node fill = Node(Kind::literal, 2u8, 40);
            const Node next = Node(Kind::literal, 3u8, 60);
            {owner} rows = region.try_allocate(2, fill);
            if (!rows.ok()) {{ return -1; }}
            const Node snapshot = rows.at(0);
            if (!forward_row(rows, 2, next)) {{
                const Node retained = rows.at(0);
                if (rows.size() != 2 || retained.score() != 42) {{ return -2; }}
                return 43;
            }}
            if (!append_row(rows, 0, next)) {{ return -3; }}
            {owner} moved = move(rows);
            const Node first = moved.at(0);
            const Node last = moved.at(2);
            if (moved.size() != 3 || first.score() != 63 || last.score() != 63) {{ return -4; }}
            return snapshot.score();
        """
        local = self.compile("typed-borrow-local", program(local_body, helpers))
        facts_input = self.directory / "typed-borrow-local.au"
        facts_input.write_text(program(local_body, helpers))
        facts_path = self.directory / "typed-borrow-local.abi.json"
        emitted = command([self.compiler, facts_input, "-o", facts_path.with_suffix(".s"), "--abi-facts", facts_path])
        require(emitted.returncode == 0, "typed borrowed ABI facts did not emit")
        facts = json.loads(facts_path.read_text())
        require(facts["version"] == 3, "typed borrowed ABI facts require version 3")
        sys.path.insert(0, str(ROOT / "scripts"))
        from bootstrap_frontend import normalize_function_abi

        for function in facts["functions"].values():
            if not function["borrowed_root_count"]:
                continue
            require(normalize_function_abi(facts, function) == function, "typed borrowed ABI normalization changed")
            root = function["borrowed_roots"][0]
            require(
                root["kind"] == "owned_values" and root["descriptor_bytes"] == 32,
                "typed borrowed ABI lost descriptor identity",
            )
            for key, value in (("mutable", False), ("descriptor_bytes", 24), ("element_type_name", "missing")):
                broken = {**function, "borrowed_roots": [{**root, key: value}]}
                try:
                    normalize_function_abi(facts, broken)
                except ValueError:
                    continue
                raise AssertionError(f"typed borrowed ABI accepted invalid {key}")
        self.run(local, 72, 0, 0, 42, 2, 1, release_order=[1, 2])
        self.run(local, 48, 0, 0, 43, 1, 1)
        self.run(local, 72, 0, 0, 43, 1, 1, fail_after=1)
        box = f"""
            class Pair {{
                {owner} first;
                i64 sentinel;
                {owner} second;
                i64 count;
            public:
                Pair({REGION} region, Node fill)
                    : first(region.try_allocate(1, fill)), sentinel(73),
                      second(region.try_allocate(1, fill)), count(1) {{}}
                auto append(Node row) -> bool {{
                    const i64 used = count;
                    if (!append_row(second, used, row)) {{ return false; }}
                    count = count + 1;
                    return true;
                }}
                auto inspect() const -> i64 {{
                    const Node a = first.at(0);
                    const Node b = second.at(count - 1);
                    if (sentinel != 73 || first.size() != 1 || a.score() != 42
                        || second.size() != count) {{ return -1; }}
                    return b.score();
                }}
            }};
        """
        field_body = """
            const Node fill = Node(Kind::literal, 2u8, 40);
            const Node next = Node(Kind::literal, 3u8, 60);
            Pair pair = Pair(region, fill);
            if (!pair.append(next)) { return pair.inspect(); }
            Pair moved = move(pair);
            return moved.inspect();
        """
        field = self.compile("typed-borrow-field", program(field_body, helpers + box))
        self.run(field, 72, 0, 0, 63, 3, 2, release_order=[2, 3, 1])
        self.run(field, 48, 0, 0, 42, 2, 2)
        self.run(field, 72, 0, 0, 42, 2, 2, fail_after=2)
        # Each negative isolates the loan violation: no later move from a const
        # owner or assignment in a const method may mask a wrongly admitted loan.
        simple_call = f"""
            const Node fill = Node(Kind::literal, 2u8, 40);
            {owner} rows = region.try_allocate(2, fill);
            if (forward_row(rows, 2, fill)) {{ return 42; }}
            return 43;
        """
        const_box = box.replace("auto append(Node row) ->", "auto append(Node row) const ->").replace(
            "if (!append_row(second, used, row)) { return false; }\n"
            "                    count = count + 1;\n                    return true;",
            "return append_row(second, used, row);",
        )
        require("count = count + 1" not in const_box, "const-field negative retains unrelated assignment")
        for name, source in (
            ("const-local", program(simple_call.replace(f"{owner} rows =", f"const {owner} rows ="), helpers)),
            (
                "later-owner-read",
                program(
                    local_body.replace("forward_row(rows, 2, next)", "forward_row(rows, rows.size(), next)"), helpers
                ),
            ),
            (
                "moved-argument",
                program(simple_call.replace("forward_row(rows, 2, fill)", "forward_row(move(rows), 2, fill)"), helpers),
            ),
            (
                "formal-move",
                program(
                    local_body,
                    helpers.replace(
                        "return append_row(rows, count, row);", f"{owner} stolen = move(rows); return true;"
                    ),
                ),
            ),
            (
                "const-field",
                program(field_body, helpers + const_box),
            ),
            (
                "later-receiver-read",
                program(
                    field_body, helpers + box.replace("append_row(second, used, row)", "append_row(second, count, row)")
                ),
            ),
            (
                "later-receiver-call",
                program(
                    field_body,
                    helpers + box.replace("append_row(second, used, row)", "append_row(second, inspect(), row)"),
                ),
            ),
            (
                "readonly-signature",
                program(
                    f"const Node fill = Node(Kind::literal, 2u8, 40); {owner} rows = region.try_allocate(1, fill);"
                    "return observe(rows);",
                    node + f"auto observe(const {owner}& rows) -> i64 {{ return rows.size(); }}",
                ),
            ),
        ):
            self.reject("typed-borrow-" + name, source)

    def typed_span_cases(self, node, owner):
        """Readonly typed views: borrow_values, size/at/subspan, parameters and receiver results."""
        span = "builtin::span<const Node>"
        helpers = (
            node
            + f"""
            auto total({span} rows) -> i64 {{
                i64 sum = 0;
                i64 i = 0;
                while (i < rows.size()) {{
                    const Node row = rows.at(i);
                    sum = sum + row.score();
                    i = i + 1;
                }}
                return sum;
            }}
            class Pool {{
                {owner} rows;
            public:
                Pool(builtin::ByteRegion region, {owner} owned) : rows(move(owned)) {{}}
                auto put(i64 index, Node row) -> bool {{ return rows.set(index, row); }}
                auto view() const -> {span} {{
                    const {span} all = borrow_values(rows);
                    return all;
                }}
                auto window(i64 offset) const -> {span} {{
                    const {span} all = borrow_values(rows);
                    const {span} part = all.subspan(offset, all.size() - offset);
                    return part;
                }}
                auto score(i64 index) const -> i64 {{
                    const {span} all = borrow_values(rows);
                    const Node row = all.at(index);
                    return row.score();
                }}
            }};
        """
        )
        # Element k scores k + 2, so a wrong element, owner, start or stride shows.
        fill_body = f"""
            const Node fill = Node(Kind::literal, 2u8, -1);
            {owner} values = region.try_allocate(n, fill);
            if (!values.ok()) {{ return 43; }}
            i64 k = 0;
            while (k < n) {{
                const Node row = Node(Kind::literal, 2u8, k);
                if (!values.set(k, row)) {{ return -1; }}
                k = k + 1;
            }}
        """
        local = self.compile(
            "typed-span-local",
            program(
                fill_body
                + f"""
            {{
                const {span} all = borrow_values(values);
                if (all.size() != n) {{ return -2; }}
                if (n > 1) {{
                    const {span} tail = all.subspan(1, n - 1);
                    const {span} again = tail;
                    const Node first = again.at(0);
                    if (tail.size() != n - 1 || first.score() != 3 || total(tail) != total(all) - 2) {{ return -3; }}
                }}
                if (total(all) != n * (n - 1) / 2 + 2 * n) {{ return -4; }}
                const Node chosen = all.at(flag);
                if (chosen.score() != flag + 2) {{ return -5; }}
            }}
            // The view has ended, so the owner may be written and moved again.
            if (!values.set(0, fill)) {{ return -6; }}
            {owner} moved = move(values);
            return 42;
        """,
                helpers,
            ),
        )
        for count, flag in ((1, 0), (4, 3), (200, 117)):
            self.run(local, count * 24, count, flag, 42, 1, 1)
        for count, flag in ((4, -1), (4, 4), (0, 0)):
            self.trap(local, count * 24, count, flag)
        receiver = self.compile(
            "typed-span-receiver",
            program(
                fill_body
                + f"""
            Pool pool = Pool(region, move(values));
            const Node replaced = Node(Kind::literal, 2u8, 1000);
            if (!pool.put(n - 1, replaced)) {{ return -2; }}
            {{
                const {span} rows = pool.view();
                const {span} part = pool.window(flag);
                const Node last = rows.at(n - 1);
                const Node first = part.at(0);
                if (rows.size() != n || part.size() != n - flag || last.score() != 1002 || first.score() != flag + 2
                    || pool.score(flag) != flag + 2) {{
                    return -3;
                }}
            }}
            if (!pool.put(0, replaced)) {{ return -4; }}
            return 42;
        """,
                helpers,
            ),
        )
        # The last element is replaced; flag selects an earlier window start.
        for count, flag in ((2, 0), (5, 2), (64, 62)):
            self.run(receiver, count * 24, count, flag, 42, 1, 1)
        self.trap(receiver, 96, 4, 5)

        def reject(name, body, extra, diagnostic):
            self.reject("typed-span-" + name, program(fill_body + body, helpers + extra), diagnostic)

        other = "class Other { i64 value; public: Other(i64 v) : value(v) {} };"
        view = f"const {span} all = borrow_values(values);"
        live = "cannot mutate or move an owner while a readonly span is live"
        for name, body, extra, diagnostic in (
            ("set-while-live", f"{view} values.set(0, fill); return 0;", "", live),
            ("resize-while-live", f"{view} values.try_resize(1, fill); return 0;", "", live),
            ("move-while-live", f"{view} {owner} m = move(values); return 0;", "", live),
            ("mutable-binding", f"{span} all = borrow_values(values); return 0;", "", "span bindings must be const"),
            (
                "element-mismatch",
                "const builtin::span<const Other> all = borrow_values(values); return 0;",
                other,
                "expected Other, got Node",
            ),
            ("at-type-mismatch", f"{view} const Other o = all.at(0); return 0;", other, "expected Node, got Other"),
            (
                "at-argument",
                f"{view} return consume(all.at(0));",
                "auto consume(Node row) -> i64 { return row.score(); }",
                "typed span access requires a typed copied local",
            ),
            (
                "scalar-borrow",
                "const i64 size = borrow_values(values); return size;",
                "",
                "borrow_values requires a span binding or span argument",
            ),
            (
                "byte-owner",
                f"{OWNER} bytes = region.try_allocate(4); const {span} b = borrow_values(bytes); return 0;",
                "",
                "borrow_values requires a named owned-values local",
            ),
            (
                "byte-initializer",
                f"{OWNER} bytes = region.try_allocate(4); const {span} b = borrow_bytes(bytes); return 0;",
                "",
                "span initializer requires borrow_bytes",
            ),
            (
                "byte-parameter",
                f"{view} return bytes(all);",
                "auto bytes(builtin::span<const u8> view) -> i64 { return view.size(); }",
                "expected builtin::span<const u8>, got builtin::span<const Node>",
            ),
            (
                "typed-to-byte-reborrow",
                f"{view} const builtin::span<const u8> b = all; return 0;",
                "",
                "expected builtin::span<const u8>, got builtin::span<const Node>",
            ),
            (
                "free-function-result",
                "return 0;",
                f"auto leak({span} rows) -> {span} {{ return rows; }}",
                "only scalar function results",
            ),
            (
                "field",
                "return 0;",
                f"class Holder {{ {span} rows; public: Holder() {{}} }};",
                "unsupported class field type 'builtin::span<const Node>'",
            ),
            (
                "scalar-element",
                "const builtin::span<const i64> all = borrow_values(values); return 0;",
                "",
                "expected 'u8' (found 'i64')",
            ),
            (
                "template-element",
                "return 0;",
                "template<Scalar T> class Wrap { T value; public: Wrap(T v) : value(v) {} };"
                "auto f(builtin::span<const Wrap<i64>> rows) -> i64 { return rows.size(); }",
                "typed spans require a named concrete copied class",
            ),
            (
                "mutable-call-while-receiver-view",
                f"Pool pool = Pool(region, move(values)); const {span} rows = pool.view();"
                " pool.put(0, fill); return 0;",
                "",
                "cannot mutate or move an owner while a readonly span is live",
            ),
            (
                "mutable-method-result",
                "return 0;",
                f"class Bad {{ {owner} rows; public:"
                f" Bad(builtin::ByteRegion region, {owner} owned) : rows(move(owned)) {{}}"
                f" auto view() -> {span} {{ const {span} all = borrow_values(rows); return all; }} }};",
                "span results require a const non-template class method",
            ),
            (
                "borrowed-object-field",
                "return 0;",
                f"auto peek(const Pool& pool) -> i64 {{ const {span} rows = borrow_values(pool.rows);"
                " return rows.size(); }",
                "borrowed object parameters support public methods, not field access",
            ),
            (
                "mutable-loan-while-live",
                f"{view} grow(values, fill); return 0;",
                f"auto grow({owner}& rows, Node fill) -> bool {{ return rows.try_resize(rows.size() + 1, fill); }}",
                "cannot mutate or move an owner while a readonly span is live",
            ),
            ("reflect", f"{view} return i64(size_of({span}));", "", "span capabilities are unavailable to reflection"),
        ):
            reject(name, body, extra, diagnostic)
        self.reject(
            "typed-span-owning-element",
            f"module bad; class Res {{ {OWNER} b; public: Res(builtin::ByteRegion r) : b(r.try_allocate(1)) {{}} }};"
            "auto f(builtin::span<const Res> rows) -> i64 { return rows.size(); }",
            "typed spans require a bounded pointer-free copied class element",
        )

    def typed_cases(self):
        node = """
            enum class Kind { unused, literal, binary };
            class Node {
                Kind kind;
                u8 tag;
                i64 payload;
            public:
                Node(Kind k,u8 t,i64 p):kind(k),tag(t),payload(p){}
                auto score() const -> i64 {
                    if (kind == Kind::literal) { return payload + i64(tag); }
                    return -1;
                }
            };
        """
        owner = "builtin::OwnedValues<Node>"
        self.typed_borrow_cases(node, owner)
        self.typed_span_cases(node, owner)
        dynamic = self.compile(
            "typed-runtime-capacity",
            program(
                f"""
            Node fill = Node(Kind::literal,2u8,40);
            {owner} values = region.try_allocate(n,fill);
            if (!values.ok()) {{ return 43; }}
            if (values.size()!=n) {{ return -1; }}
            i64 i=0;
            while(i<n) {{
                Node copied=values.at(i);
                if(copied.score()!=42) {{return -2;}}
                i=i+1;
            }}
            if(values.set(-1,fill)||values.set(n,fill)) {{return -3;}}
            return 42;
        """,
                node,
            ),
        )
        for count in (0, 1, 65, 171, 513):
            self.run(dynamic, count * 24, count, 0, 42, 1, 1)
        for count in (-1, (1 << 63) - 1):
            self.run(dynamic, 24000, count, 0, 43, 0, 0)
        self.run(dynamic, 23, 1, 0, 43, 0, 0)

        resize = self.compile(
            "typed-replacement",
            program(
                f"""
            Node fill=Node(Kind::literal,2u8,40);
            Node next=Node(Kind::literal,3u8,60);
            {owner} values=region.try_allocate(200,fill);
            if(!values.ok()) {{return -1;}}
            Node independent=values.at(170);
            if(!values.set(170,next)) {{return -2;}}
            if(!values.try_resize(n,fill)) {{
                Node retained=values.at(170);
                if(values.size()!=200||retained.score()!=63||independent.score()!=42) {{return -3;}}
                return 43;
            }}
            if(values.size()!=n) {{return -4;}}
            if(n>200) {{Node grown=values.at(n-1);if(grown.score()!=42){{return -5;}}}}
            {owner} moved=move(values);
            return independent.score();
        """,
                node,
            ),
        )
        self.run(resize, 7200, 300, 0, 42, 2, 1)
        self.run(resize, 4800, 201, 0, 43, 1, 1)
        self.run(resize, 7200, 300, 0, 43, 1, 1, fail_after=1)
        self.run(resize, 4800, -1, 0, 43, 1, 1)
        self.run(resize, 4800, 200, 0, 42, 1, 1)
        self.run(resize, 4800, 0, 0, 42, 2, 1)

        empty = self.compile(
            "typed-empty-elements",
            program(
                """
            Empty fill=Empty();
            builtin::OwnedValues<Empty> values=region.try_allocate(n,fill);
            if(!values.ok()||values.size()!=n){return -1;}
            Empty copied=values.at(n-1);
            if(!values.set(n-1,copied)){return -2;}
            return 42;
        """,
                "class Empty {public:Empty(){} };",
            ),
        )
        self.run(empty, 800, 100, 0, 42, 1, 1)

        # An element read returned at once is copied straight into the caller's
        # result; one with any code between keeps its local copy. Both must agree.
        pool = """
            class Pool {
                builtin::OwnedValues<Node> rows;
            public:
                Pool(builtin::ByteRegion region, i64 count, Node fill) : rows(region.try_allocate(count, fill)) {}
                auto put(i64 index, Node row) -> bool { return rows.set(index, row); }
                auto direct(i64 index) const -> Node { return rows.at(index); }
                auto held(i64 index) const -> Node {
                    const Node row = rows.at(index);
                    if (index < 0) { return row; }
                    return row;
                }
            };
        """

        def returned_shape(text):

            def body(method):
                start = re.search(r"^__au_m_\w+_d%d%s:$" % (len(method), method), text, re.M)
                require(start, f"missing {method}")
                return text[start.end() : text.index("\n.size ", start.end())].split("\n")

            direct, held, score = body("direct"), body("held"), body("score")
            call = direct.index("    call __au_runtime_values_at")
            require(
                direct[call - 1].startswith("    movq -")
                and direct[call - 1].endswith("(%rbp), %rcx")
                and direct[call + 1] == "    xorq %rax, %rax"
                and direct[call + 2].startswith("    jmp .Lreturn"),
                "direct element return still copies through a local",
            )
            call = held.index("    call __au_runtime_values_at")
            require(held[call - 1].startswith("    leaq -"), "held element return lost its local copy")
            # The receiver's kind is compared with the enum case without a stack round trip.
            compare = next(index for index, line in enumerate(score) if line.startswith("    cmpq "))
            require("    pushq %rax" not in score[:compare], "constant comparison still spills its left operand")

        returned = self.compile(
            "typed-returned-element",
            program(
                """
            Node fill=Node(Kind::literal,2u8,-1);
            Pool pool=Pool(region,n,fill);
            i64 i=0;
            while(i<n) {
                Node row=Node(Kind::literal,2u8,i);
                if(!pool.put(i,row)) {return -1;}
                i=i+1;
            }
            // Each element scores its index + 2, so a wrong element, owner or stride shows.
            Node last=pool.direct(n-1);
            Node kept=pool.held(n-1);
            Node first=pool.direct(0);
            Node chosen=pool.direct(flag);
            if(last.score()!=n+1||kept.score()!=n+1||first.score()!=2||chosen.score()!=flag+2) {return -2;}
            return 42;
        """,
                node + pool,
            ),
            inspect=returned_shape,
        )
        for count, flag in ((1, 0), (4, 2), (200, 199)):
            self.run(returned, count * 24, count, flag, 42, 1, 1)
        for flag in (-1, 4):
            self.trap(returned, 96, 4, flag)
        self.trap(empty, 0, 0)

        blank = self.compile(
            "typed-zero-field-braces",
            program(
                """
            Blank fill=Blank{};
            Blank independent=fill;
            builtin::OwnedValues<Blank> values=region.try_allocate(100,independent);
            Blank copied=values.at(99);
            if(!values.set(0,copied)){return -1;}
            return values.size();
        """,
                "class Blank {};",
            ),
        )
        self.run(blank, 800, 0, 0, 100, 1, 1)

        moved_helpers = (
            node
            + f"""
            auto pass(builtin::ByteRegion region,{owner} input)->{owner} {{return move(input);}}
            class Arena {{
                {owner} nodes;
            public:
                Arena(builtin::ByteRegion region,{owner} initial):nodes(move(initial)){{}}
                auto size() const -> i64 {{return nodes.size();}}
                auto get(i64 i) const -> Node {{return nodes.at(i);}}
                auto put(i64 i,Node value)->bool {{return nodes.set(i,value);}}
                auto grow(i64 n,Node fill)->bool {{return nodes.try_resize(n,fill);}}
            }};
        """
        )
        moved = self.compile(
            "typed-owning-class",
            program(
                f"""
            Node fill=Node(Kind::literal,2u8,40);
            {owner} initial=region.try_allocate(100,fill);
            {owner} transferred=pass(region,move(initial));
            Arena arena=Arena(region,move(transferred));
            Node next=Node(Kind::literal,3u8,60);
            if(!arena.put(99,next)||!arena.grow(200,fill)){{return -1;}}
            Node copied=arena.get(99);
            if(arena.size()!=200||copied.score()!=63){{return -2;}}
            return 42;
        """,
                moved_helpers,
            ),
        )
        self.run(moved, 4800, 0, 0, 42, 2, 1)

        produced_node = node.replace(
            "auto score()", "auto change(i64 value) -> i64 { payload = value; return 2; } auto score()"
        )
        produced_helpers = (
            produced_node
            + f"""
            auto make_nodes({REGION} region) -> {owner} {{
                const Node fill = Node(Kind::literal, 2u8, 7);
                {owner} result = region.try_allocate(1, fill); return move(result);
            }}
            class Produced {{
                {owner} direct; {owner} returned;
            public:
                Produced({REGION} region, Node fill, i64 count)
                    : returned(make_nodes(region)), direct(region.try_allocate(count, fill)) {{}}
                auto check(i64 count) const -> i64 {{
                    if (!returned.ok() || returned.size() != 1) {{ return -1; }}
                    Node saved = returned.at(0);
                    if (saved.score() != 9) {{ return -2; }}
                    if (!direct.ok()) {{ return 43; }}
                    if (direct.size() != count) {{ return -3; }}
                    if (count > 0) {{
                        Node copied = direct.at(count - 1); copied.change(99);
                        Node retained = direct.at(count - 1);
                        if (copied.score() != 101 || retained.score() != 42) {{ return -3; }}
                    }}
                    return 42;
                }}
            }};
            auto pass_produced({REGION} region, Produced input) -> Produced {{ return move(input); }}
        """
        )
        produced = self.compile(
            "typed-produced-fields-named-fill-and-return",
            program(
                "Node fill = Node(Kind::literal, 2u8, 40); Produced initial = Produced(region, fill, n); "
                "fill.change(99); const Produced result = pass_produced(region, move(initial)); "
                "if (fill.score() != 101) { return -4; } return result.check(n);",
                produced_helpers,
            ),
        )
        for count in (0, 2):
            self.run(produced, 72, count, 0, 42, 2, 2, release_order=[2, 1], attempted_sizes=[32 + 24 * count, 56])
        for count in (-1, (1 << 63) - 1, 4):
            self.run(produced, 72, count, 0, 43, 1, 1, release_order=[1], attempted_sizes=[56])
        for name, initializer in {
            "temporary-fill": "region.try_allocate(1, Node(Kind::literal, 2u8, 40))",
            "scalar-fill": "region.try_allocate(1, 42)",
            "wrong-fill": "region.try_allocate(1, other)",
            "missing-fill": "region.try_allocate(1)",
            "byte-result": "make_bytes(region)",
            "wrong-nominal-result": "make_other(region)",
        }.items():
            self.reject(
                "typed-produced-field-" + name,
                program(
                    "return 0;",
                    produced_node
                    + f"""
                class Other {{ public: i64 first; i64 second; i64 third; }};
                auto make_bytes({REGION} region) -> {OWNER} {{
                    {OWNER} result = region.try_allocate(1); return move(result);
                }}
                auto make_other({REGION} region) -> builtin::OwnedValues<Other> {{
                    Other fill = Other{{.first = 1, .second = 2, .third = 3}};
                    builtin::OwnedValues<Other> result = region.try_allocate(1, fill); return move(result);
                }}
                class Bad {{ {owner} nodes; public:
                    Bad({REGION} region, Node fill, Other other) : nodes({initializer}) {{}} }};
            """,
                ),
            )

        arena_source = (ROOT / "compiler/syntax_arena.au").read_text()
        arena = self.compile(
            "compiler-typed-ast-arena",
            arena_source
            + """
            auto arena_entry(builtin::ByteRegion region,i64 n,i64 flag)->i64 {
                compiler_parser::AstArena arena=compiler_parser::make_arena(region,n);
                if(!arena.ok()){return -1;}
                if(flag==1){
                    const i64 first=arena.append(compiler_parser::NodeKind::literal,0,-1,-1);
                    if(first!=0||arena.append(compiler_parser::NodeKind::unary,1,1,-1)!=-1||arena.size()!=1){return -6;}
                    const i64 second=arena.append(compiler_parser::NodeKind::literal,1,-1,-1);
                    if(second!=1||arena.append(compiler_parser::NodeKind::unary,2,0,-1)!=-1||arena.size()!=2){
                        return -7;
                    }
                    compiler_parser::AstNode kept=arena.at(0);
                    if(kept.token()!=0||kept.depth()!=1){return -8;}
                    return 42;
                }
                if(flag==2){
                    i64 parent=arena.append(compiler_parser::NodeKind::literal,0,-1,-1);
                    i64 depth=1;
                    while(depth<128){parent=arena.append(compiler_parser::NodeKind::unary,depth,parent,-1);depth=depth+1;}
                    if(parent!=127||arena.append(compiler_parser::NodeKind::unary,128,parent,-1)!=-1||arena.size()!=128){
                        return -9;
                    }
                    return 42;
                }
                if(flag==3){compiler_parser::AstNode invalid=arena.at(0);return invalid.token();}
                i64 token=0;
                i64 root=-1;
                while(token<100){
                    const i64 leaf=arena.append(compiler_parser::NodeKind::literal,token,-1,-1);
                    if(leaf<0){return -2;}
                    if(root<0){root=leaf;}
                    else{root=arena.append(compiler_parser::NodeKind::binary,token,root,leaf);}
                    if(root<0){return -3;}
                    token=token+1;
                }
                if(arena.size()!=199||arena.append(compiler_parser::NodeKind::unary,0,199,-1)!=-1){return -4;}
                compiler_parser::AstNode node=arena.at(root);
                if(node.kind()!=compiler_parser::NodeKind::binary||node.first()>=root||node.second()>=root){return -5;}
                return 42;
            }
        """,
            entry_name="arena_entry",
        )
        # Empty frame, argument, type and syntax stores each retain real owner metadata.
        # Class cleanup reverses field order; node growth first retires its old block.
        self.run(arena, 16384, 200, 0, 42, 5, 5, release_order=[5, 4, 3, 2, 1])
        self.run(arena, 16384, 100, 0, 42, 6, 5, release_order=[1, 5, 4, 3, 2, 6])
        self.run(arena, 112, 2, 1, 42, 5, 5, release_order=[5, 4, 3, 2, 1])
        self.run(arena, 16384, 200, 2, 42, 5, 5, release_order=[5, 4, 3, 2, 1])
        self.run(arena, 16384, -1, 0, -1, 4, 4, release_order=[4, 3, 2, 1])
        # Zero-length syntax storage is a real fifth owner. Refuse every
        # initial allocation and the node-growth replacement; each successfully
        # allocated prefix must unwind once in exact reverse field order.
        for allowed in range(5):
            self.run(
                arena,
                16384,
                200,
                0,
                -1,
                allowed,
                allowed,
                fail_after=allowed,
                release_order=list(range(allowed, 0, -1)),
            )
        self.run(arena, 16384, 100, 0, -3, 5, 5, fail_after=5, release_order=[5, 4, 3, 2, 1])
        self.trap(arena, 16384, 200, 3)

        statement_arena = self.compile(
            "compiler-statement-arena",
            arena_source
            + """
            auto statement_arena_entry(builtin::ByteRegion region,i64 n,i64 flag)->i64 {
                compiler_parser::AstArena arena=compiler_parser::make_arena(region,0);
                if(!arena.ok()){return -1;}
                i64 count=0;
                bool failed=false;
                while(count<n&&!failed){
                    compiler_parser::SyntaxNode value=compiler_parser::SyntaxNode(
                        compiler_parser::SyntaxKind::block,2*count,2*count+2,count-1);
                    const i64 appended=arena.append_syntax(value);
                    if(appended<0){failed=true;}
                    else{
                        if(appended!=count){return -3;}
                        count=count+1;
                    }
                }
                if(arena.syntax_size()!=count||arena.size()!=0||arena.types()!=0||arena.arguments()!=0){return -4;}
                if(failed&&arena.failure()!=compiler_parser::ArenaFailure::allocation){return -5;}
                i64 index=0;
                while(index<count){
                    compiler_parser::SyntaxNode kept=arena.syntax_at(index);
                    if(kept.kind()!=compiler_parser::SyntaxKind::block||kept.token()!=2*index
                        ||kept.end()!=2*index+2||kept.previous()!=index-1||kept.expression()!=-1
                        ||kept.target()!=-1||kept.type()!=-1||kept.binding()!=-1||kept.body()!=-1
                        ||kept.other()!=-1||kept.mutable_binding()!=0||kept.borrow_site()!=-1){return -6;}
                    index=index+1;
                }
                if(failed){return -2;}
                return 42;
            }
        """,
            entry_name="statement_arena_entry",
        )
        # make_arena owns nodes, frames, edges, types and syntax in that
        # order. Each syntax resize retires its prior block (starting at 5);
        # class cleanup drops the replacement before the four unchanged owners.
        self.run(statement_arena, 1048576, 0, 0, 42, 5, 5, release_order=[5, 4, 3, 2, 1])
        self.run(statement_arena, 1048576, 1, 0, 42, 6, 5, release_order=[5, 6, 4, 3, 2, 1])
        # The first growth holds eight 96-byte SyntaxNode values, including
        # borrow_site; the fifth owner remains the same syntax allocation.
        self.run(statement_arena, 8 * 96 - 1, 1, 0, -2, 5, 5, release_order=[5, 4, 3, 2, 1])
        self.run(statement_arena, 8 * 96, 1, 0, 42, 6, 5, release_order=[5, 6, 4, 3, 2, 1])
        self.run(statement_arena, 1048576, 9, 0, 42, 7, 5, release_order=[5, 6, 7, 4, 3, 2, 1])
        self.run(
            statement_arena,
            1048576,
            513,
            0,
            42,
            13,
            5,
            release_order=[*range(5, 14), 4, 3, 2, 1],
        )
        for allowed in range(5, 13):
            self.run(
                statement_arena,
                1048576,
                513,
                0,
                -2,
                allowed,
                5,
                fail_after=allowed,
                release_order=[*range(5, allowed + 1), 4, 3, 2, 1],
            )

        same_layout = "class Other {public:i64 a;i64 b;i64 c;};"
        for name, body in {
            "wrong-fill": f"Other fill=Other{{.a=1,.b=2,.c=3}};{owner} values=region.try_allocate(1,fill);return 0;",
            "wrong-copy": f"""
                Node fill=Node(Kind::literal,2u8,40);
                {owner} values=region.try_allocate(1,fill);
                Other out=values.at(0);
                return 0;
            """,
            "byte-borrow": f"""
                Node fill=Node(Kind::literal,2u8,40);
                {owner} values=region.try_allocate(1,fill);
                const builtin::span<const u8> bytes=borrow_bytes(values);
                return bytes.size();
            """,
            "byte-set": f"""
                Node fill=Node(Kind::literal,2u8,40);
                {owner} values=region.try_allocate(1,fill);
                return i64(values.set(0,42u8));
            """,
            "missing-fill": f"{owner} values=region.try_allocate(1);return 0;",
            "resize-missing-fill": f"""
                Node fill=Node(Kind::literal,2u8,40);
                {owner} values=region.try_allocate(1,fill);
                return i64(values.try_resize(2));
            """,
            "const-set": f"""
                Node fill=Node(Kind::literal,2u8,40);
                const {owner} values=region.try_allocate(1,fill);
                return i64(values.set(0,fill));
            """,
            "owner-assignment": f"""
                Node fill=Node(Kind::literal,2u8,40);
                {owner} values=region.try_allocate(1,fill);
                {owner} copy=values;
                return 0;
            """,
            "nominal-move": f"""
                Node fill=Node(Kind::literal,2u8,40);
                {owner} values=region.try_allocate(1,fill);
                builtin::OwnedValues<Other> wrong=move(values);
                return 0;
            """,
            "use-after-move": f"""
                Node fill=Node(Kind::literal,2u8,40);
                {owner} values=region.try_allocate(1,fill);
                {owner} moved=move(values);
                Node out=values.at(0);
                return out.score();
            """,
        }.items():
            self.reject("typed-" + name, program(body, node + same_layout))
        for element in ("i64", "builtin::OwnedBytes", "builtin::ByteRegion", "builtin::span<const u8>"):
            self.reject(
                "typed-invalid-element-" + element,
                program(f"builtin::OwnedValues<{element}> values=region.try_allocate(1);return 0;"),
            )

        direct_return = (
            node
            + f"""
            auto get(builtin::ByteRegion region)->Node{{
                Node fill=Node(Kind::literal,2u8,40);
                {owner} values=region.try_allocate(1,fill);
                return values.at(0);
            }}
        """
        )
        direct = self.compile(
            "typed-direct-return", program("Node copied=get(region);return copied.score();", direct_return)
        )
        self.run(direct, 24, 0, 0, 42, 1, 1)

        # A full 64-byte copied element crosses the compact REP threshold. This
        # exercises typed snapshot staging, RSP argument packing with live scalar
        # arguments, resize, and copied return before the owner is dropped.
        wide_helpers = """
            class Wide {public:i64 a;i64 b;i64 c;i64 d;i64 e;i64 f;i64 g;i64 h;};
            auto score(i64 head,Wide value,i64 tail)->i64{
                return head+value.a+value.b+value.c+value.d+value.e+value.f+value.g+value.h+tail;
            }
            auto snapshot(builtin::ByteRegion region,i64 count,i64 flag)->Wide{
                Wide fill=Wide{.a=1,.b=2,.c=3,.d=4,.e=5,.f=6,.g=7,.h=8};
                Wide next=Wide{.a=11,.b=12,.c=13,.d=14,.e=15,.f=16,.g=17,.h=18};
                builtin::OwnedValues<Wide> values=region.try_allocate(2,fill);
                Wide saved=values.at(1);
                bool replaced=values.set(0,next);
                bool resized=values.try_resize(count,next);
                if(!replaced||!resized){return fill;}
                if(flag==0){return saved;}
                return values.at(count-1);
            }
        """

        def compact_copies(text):
            require("rep movsb" in text, "typed wide copied value did not exercise compact copies")
            require(
                "leaq 8(%rsp), %rax\n    pushq %rsi\n    pushq %rdi\n    pushq %rcx" in text,
                "typed wide copied argument did not exercise captured RSP packing",
            )

        compact = self.compile(
            "typed-compact-copied-return",
            program("Wide copied=snapshot(region,n,flag);return score(17,copied,29)-46;", wide_helpers),
            inspect=compact_copies,
        )
        for count in (1, 3):
            for flag, expected in ((0, 36), (1, 116)):
                self.run(compact, 192, count, flag, expected, 2, 1)

        consuming = (
            node
            + f"""
            auto consume(builtin::ByteRegion region,{owner} value)->i64{{return 0;}}
        """
        )
        for operation in ("at(consume(region,move(values)))", "try_resize(consume(region,move(values)),fill)"):
            body = f"Node fill=Node(Kind::literal,2u8,40);{owner} values=region.try_allocate(1,fill);"
            body += (
                ("Node out=values." if operation.startswith("at") else "bool out=values.") + operation + ";return 0;"
            )
            self.reject("typed-consumed-receiver-" + operation.split("(")[0], program(body, consuming))

        modules = {
            "left": "export module left;export namespace left {class Node{public:i64 value;};"
            "auto marker()->i64{return 0;}}",
            "right": "export module right;export namespace right {class Node{public:i64 value;};"
            "auto marker()->i64{return 0;}}",
        }
        imported = """
            module typed_imports;import left;import right;
            auto entry(builtin::ByteRegion region,i64 n,i64 flag)->i64{
                left::Node left=left::Node{.value=42};
                right::Node right=right::Node{.value=7};
                builtin::OwnedValues<left::Node> values=region.try_allocate(100,left);
                left::Node copied=values.at(99);
                return copied.value;
            }
        """
        imported_owner = self.compile("typed-imported-identity", imported, modules=modules)
        self.run(imported_owner, 800, 0, 0, 42, 1, 1)
        self.reject("typed-imported-wrong-fill", imported.replace("(100,left)", "(100,right)"), modules=modules)
        self.reject(
            "typed-imported-wrong-result", imported.replace("left::Node copied", "right::Node copied"), modules=modules
        )

    def emitter_mov_cases(self):
        # All helpers and closed register aliases run in this existing packed
        # driver. GNU as assembles the reviewed data once, never one program per
        # value. Equality with MOV-only reference bytes also checks that zero
        # loads preserve flags instead of becoming a flags-changing idiom.
        registers = (
            ("rax", "eax"),
            ("rbx", "ebx"),
            ("rcx", "ecx"),
            ("rdx", "edx"),
            ("rsi", "esi"),
            ("rdi", "edi"),
            ("r8", "r8d"),
            ("r9", "r9d"),
            ("r10", "r10d"),
            ("r11", "r11d"),
            ("rbp", "ebp"),
            ("rsp", "esp"),
        )
        rows = [
            line.split()
            for line in (ROOT / "tests/compiler/emitter_mov.cases").read_text().splitlines()
            if line and not line.startswith("#")
        ]
        signed = [value for kind, value, _, _ in rows if kind == "i64"]
        unsigned = [value + "u64" for kind, value, _, _ in rows if kind == "u64"]
        references = []
        for wide, narrow in registers:
            instructions = []
            for kind, _, mnemonic, immediate in rows:
                instruction = f"    {mnemonic} ${immediate}, %{narrow if mnemonic == 'movl' else wide}\n"
                instructions.extend([instruction] * (2 if kind == "i64" else 1))
            references.append("".join(instructions))
        zero_rows = [
            tuple(map(int, line.split()))
            for line in (ROOT / "tests/compiler/emitter_zero.cases").read_text().splitlines()
            if line and not line.startswith("#") and not line.endswith(" reject")
        ]
        invalid_zero_rows = [
            tuple(map(int, line.split()[:2]))
            for line in (ROOT / "tests/compiler/emitter_zero.cases").read_text().splitlines()
            if line.endswith(" reject")
        ]
        zero_snippets, zero_native = zero_references(zero_rows)
        reference = self.directory / "emitter-mov-reference.s"
        reference.write_text(
            ".text\n"
            + "".join(
                f".globl reference_{wide}\n.type reference_{wide},@function\nreference_{wide}:\n"
                + text
                + f".size reference_{wide},.-reference_{wide}\n"
                for (wide, _), text in zip(registers, references)
            )
            + "".join(
                f".globl reference_zero_{index}\n.type reference_zero_{index},@function\nreference_zero_{index}:\n"
                + text
                + f".size reference_zero_{index},.-reference_zero_{index}\n    ret\n"
                for index, text in enumerate(zero_snippets)
            )
            + zero_native
            + '.section .note.GNU-stack,"",@progbits\n'
        )
        reference_object, reference_binary = reference.with_suffix(".o"), reference.with_suffix(".bin")
        native_runner.command(["as", "--64", reference, "-o", reference_object])
        native_runner.command(["objcopy", "-O", "binary", "--only-section=.text", reference_object, reference_binary])
        symbols = {}
        for line in (
            native_runner.command(["nm", "-S", "--defined-only", reference_object]).stdout.decode().splitlines()
        ):
            parts = line.split()
            offset, size, _, name = parts if len(parts) == 4 else [parts[0], "0", parts[1], parts[2]]
            symbols[name] = (int(offset, 16), int(size, 16))
        native_reference = reference.with_suffix(".native")
        native_runner.command(["ld", "-o", native_reference, reference_object])
        native_runner.command([native_reference])
        encoded = reference_binary.read_bytes()
        selections, comparisons = [], []
        for index, ((wide, _), text) in enumerate(zip(registers, references)):
            selections.append(f"if(n=={index}){{target=compiler_x86::Register::{wide};}}")
            offset, size = symbols["reference_" + wide]
            literal = '"' + "".join(f"\\x{byte:02x}" for byte in encoded[offset : offset + size]) + '"'
            comparisons.append(
                f"if(n=={index}){{if(!same_text(w,{json.dumps(text)})||!same_object(o,{literal})){{return -4;}}}}"
            )
        zero_comparisons = []
        for index, text in enumerate(zero_snippets):
            offset, size = symbols[f"reference_zero_{index}"]
            literal = '"' + "".join(f"\\x{byte:02x}" for byte in encoded[offset : offset + size]) + '"'
            zero_comparisons.append(
                f"if(n=={index}){{if(!same_text(w,{json.dumps(text)})||!same_object(o,{literal})){{return -14;}}}}"
            )
        source = r"""
            module emitter_mov_test;
            import aurora.compiler.x86_storage;
            import aurora.compiler.x86_object_storage;
            auto same_text(const compiler_x86::EmitWorkspace& w,builtin::span<const u8> expected)->bool {
                if(w.artifact_size(compiler_x86::Artifact::assembly)!=expected.size()){return false;}
                i64 offset=0;
                while(offset<expected.size()) {
                    const compiler_x86::EmitChunk chunk=w.chunk(compiler_x86::Artifact::assembly,offset);
                    if(chunk.size()<=0){return false;}
                    i64 at=0;
                    while(at<chunk.size()) {
                        if(chunk.at(at)!=expected.at(offset+at)){return false;}
                        at=at+1;
                    }
                    offset=offset+chunk.size();
                }
                return true;
            }
            auto object_word(const compiler_x86::ObjectWorkspace& o,i64 offset)->i64 {
                const compiler_x86::EmitChunk chunk=o.chunk(offset);
                u64 value=0u64;
                i64 at=0;
                while(at<8){value=value|(u64(chunk.at(at))<<(at*8));at=at+1;}
                return i64(value);
            }
            auto same_object(const compiler_x86::ObjectWorkspace& o,builtin::span<const u8> expected)->bool {
                // Read the ELF64 section-table address and .text section fields,
                // rather than pinning any generated code or file offsets.
                const i64 section=object_word(o,40)+64;
                const i64 start=object_word(o,section+24);
                if(object_word(o,section+32)!=expected.size()){return false;}
                i64 offset=0;
                while(offset<expected.size()) {
                    const compiler_x86::EmitChunk chunk=o.chunk(start+offset);
                    i64 at=0;
                    while(at<chunk.size()&&offset+at<expected.size()) {
                        if(chunk.at(at)!=expected.at(offset+at)){return false;}
                        at=at+1;
                    }
                    if(at==0){return false;}
                    offset=offset+at;
                }
                return true;
            }
            auto zero_case(builtin::ByteRegion region,i64 n)->i64 {
                compiler_x86::EmitWorkspace w=compiler_x86::create(region);
                compiler_x86::EmitWorkspace v=compiler_x86::create(region);
                compiler_x86::ObjectWorkspace t=compiler_x86::object_create(region);
                compiler_x86::ObjectWorkspace o=compiler_x86::object_create(region);
                if(!w.begin()||!v.begin()||!o.enable_object()
                    ||!w.begin_function(0,0,0)||!v.begin_function(0,0,0)){return -11;}
                const array<i64,ZERO_COUNT> counts={ZERO_COUNTS};
                const array<i64,ZERO_COUNT> offsets={ZERO_OFFSETS};
                if(!compiler_x86::zero_receiver_bytes(w,t,offsets[n],counts[n])
                    ||!compiler_x86::zero_receiver_bytes(v,o,offsets[n],counts[n])){return -12;}
                const compiler_x86::FunctionFact text_fact=w.function_at(0);
                const compiler_x86::FunctionFact object_fact=v.function_at(0);
                i64 local=8;
                if(counts[n]>0){local=32;}
                if(w.live_stack()!=8||v.live_stack()!=8||w.stack_depth()!=0||v.stack_depth()!=0
                    ||text_fact.local()!=local||object_fact.local()!=local){return -13;}
                if(!w.finish_assembly()||!o.seal()){return -15;}
                ZERO_COMPARISONS
                return 42;
            }
            auto invalid_zero_case(builtin::ByteRegion region,i64 n)->i64 {
                compiler_x86::EmitWorkspace w=compiler_x86::create(region);
                compiler_x86::ObjectWorkspace o=compiler_x86::object_create(region);
                if(!w.begin()||!w.begin_function(0,0,0)){return -21;}
                const bool object=n>=INVALID_COUNT;
                if(object&&!o.enable_object()){return -22;}
                const i64 at=n%INVALID_COUNT;
                const array<i64,INVALID_COUNT> counts={INVALID_COUNTS};
                const array<i64,INVALID_COUNT> offsets={INVALID_OFFSETS};
                if(compiler_x86::zero_receiver_bytes(w,o,offsets[at],counts[at])){return -23;}
                const compiler_x86::FunctionFact fact=w.function_at(0);
                if(w.status()!=compiler_x86::EmitStatus::invalid||w.live_stack()!=8||fact.local()!=8){return -24;}
                if(object){if(!o.seal()||!same_object(o,"")){return -25;}}
                return 42;
            }
            auto entry(builtin::ByteRegion region,i64 n,i64 flag)->i64 {
                if(flag==1){return zero_case(region,n);}
                if(flag==2){return invalid_zero_case(region,n);}
                compiler_x86::EmitWorkspace w=compiler_x86::create(region);
                compiler_x86::ObjectWorkspace o=compiler_x86::object_create(region);
                if(!w.begin()||!o.enable_object()){return -1;}
                compiler_x86::Register target=compiler_x86::Register::rax;
                SELECTIONS
                const array<i64,SIGNED_COUNT> signed_values={SIGNED_VALUES};
                const array<u64,UNSIGNED_COUNT> unsigned_values={UNSIGNED_VALUES};
                i64 at=0;
                while(at<SIGNED_COUNT) {
                    if(!w.mov_imm(signed_values[at],target)||!o.mov_imm(signed_values[at],target)
                        ||!w.mov_abs(signed_values[at],target)||!o.mov_abs(signed_values[at],target)){return -2;}
                    at=at+1;
                }
                at=0;
                while(at<UNSIGNED_COUNT) {
                    if(!w.mov_uimm(unsigned_values[at],target)||!o.mov_uimm(unsigned_values[at],target)){return -2;}
                    at=at+1;
                }
                if(!w.finish_assembly()||!o.seal()){return -3;}
                COMPARISONS
                return 42;
            }
        """
        for name, value in (
            ("INVALID_COUNTS", ",".join(str(count) for count, _ in invalid_zero_rows)),
            ("INVALID_OFFSETS", ",".join(str(offset) for _, offset in invalid_zero_rows)),
            ("INVALID_COUNT", str(len(invalid_zero_rows))),
            ("ZERO_COMPARISONS", "".join(zero_comparisons)),
            ("ZERO_COUNTS", ",".join(str(count) for count, _ in zero_rows)),
            ("ZERO_OFFSETS", ",".join(str(offset) for _, offset in zero_rows)),
            ("ZERO_COUNT", str(len(zero_rows))),
            ("SELECTIONS", "".join(selections)),
            ("COMPARISONS", "".join(comparisons)),
            ("UNSIGNED_COUNT", str(len(unsigned))),
            ("SIGNED_COUNT", str(len(signed))),
            ("UNSIGNED_VALUES", ",".join(unsigned)),
            ("SIGNED_VALUES", ",".join(signed)),
        ):
            source = source.replace(name, value)
        executable = self.compile(
            "emitter-numeric-mov",
            source,
            modules={
                "aurora.compiler.x86_storage": (ROOT / "compiler/x86_storage.au").read_text(),
                "aurora.compiler.x86_object_storage": (ROOT / "compiler/x86_object_storage.au").read_text(),
            },
        )
        for index, (wide, _) in enumerate(registers):

            def check(result, wide=wide):
                require(result.returncode == 0, f"numeric MOV {wide}: execution failed {result.stderr!r}")
                observed = [int(part) for part in result.stdout.split()]
                require(observed[0] == 42, f"numeric MOV {wide}: text or GNU object bytes differ: {observed}")
                # The common host verifies zero live allocations and every free.
                with self.lock:
                    self.native += 1

            self._invoke(executable, [65536, index, 0], check)
        for index, (count, offset) in enumerate(zero_rows):

            def check(result, count=count, offset=offset):
                require(result.returncode == 0, f"zero bytes {count}/{offset}: execution failed {result.stderr!r}")
                observed = [int(part) for part in result.stdout.split()]
                require(observed[0] == 42, f"zero bytes {count}/{offset}: text/object/facts differ: {observed}")
                with self.lock:
                    self.native += 1

            self._invoke(executable, [65536, index, 1], check)
        for index in range(2 * len(invalid_zero_rows)):

            def check(result, index=index):
                require(result.returncode == 0, f"invalid zero {index}: execution failed {result.stderr!r}")
                observed = [int(part) for part in result.stdout.split()]
                require(
                    observed[0] == 42, f"invalid zero {index}: bounds or pre-emission rejection differs: {observed}"
                )
                with self.lock:
                    self.native += 1

            self._invoke(executable, [65536, index, 2], check)

    def emitter_storage_cases(self):
        # Exercise the real source workspace in the existing region/owner driver.
        # Large logical bounds need no million-row allocation or IR fixture.
        executable = self.compile(
            "emitter-checked-storage",
            """
            module emitter_storage_test;
            import aurora.compiler.x86_storage;
            import aurora.compiler.x86_object_storage;
            auto entry(builtin::ByteRegion region, i64 n, i64 flag)->i64 {
                compiler_x86::EmitWorkspace w=compiler_x86::create(region);
                if(flag==0) {
                    if(compiler_x86::grow_capacity(1048576,1048577,9223372036854775807/48,16)!=2097152) {return -1;}
                    if(compiler_x86::grow_capacity(0,9223372036854775807,9223372036854775807/48,16)!=-1) {return -2;}
                    if(compiler_x86::grow_capacity(8,9,9,16)!=9) {return -3;}
                    if(compiler_x86::grow_capacity(-1,0,9,16)!=-1) {return -4;}
                    if(compiler_x86::stack_byte_bound(67108864,256,1048832)<=67108864) {return -5;}
                    if(compiler_x86::stack_byte_bound(0,0,0)!=1024) {return -6;}
                    if(compiler_x86::stack_byte_bound(9223372036854775807,0,0)!=-1) {return -7;}
                    if(compiler_x86::stack_byte_bound(0,9223372036854775807,0)!=-1) {return -8;}
                    if(compiler_x86::stack_byte_bound(0,0,9223372036854775807)!=-1) {return -9;}
                    return 42;
                }
                if(flag==1) {
                    if(!w.add_retained(2147483647)||!w.add_retained(0)||!w.add_retained(n)) {return -10;}
                    const bool valid=w.retained_valid(2147483648);
                    if(n==0) {
                        if(valid||w.status()!=compiler_x86::EmitStatus::invalid) {return -11;}
                    } else {
                        if(!valid||w.retained_at(0)!=2147483647||w.retained_at(1)!=0||w.retained_at(2)!=n) {return -12;}
                    }
                    return 42;
                }
                if(flag==2) {
                    if(w.add_retained(n)) {return -13;}
                    if(n<0) {
                        if(w.status()!=compiler_x86::EmitStatus::invalid) {return -14;}
                    } else {
                        if(w.status()!=compiler_x86::EmitStatus::allocation) {return -15;}
                    }
                    if(w.artifact_size(compiler_x86::Artifact::assembly)!=-1) {return -16;}
                    return 42;
                }
                if(flag==6) {
                    if(n==0) {
                        const i64 frame=w.pack_address(0,8);
                        if(w.advance_address(frame,8)!=0) {return -24;}
                        const i64 relative=w.pack_address(4,999999998);
                        if(w.advance_address(relative,1)!=4999999999) {return -25;}
                        if(w.advance_address(relative,2)!=-1) {return -26;}
                    }
                    if(n==1) {if(w.pack_address(0,1000000000)!=-1) {return -27;}}
                    if(n==2) {if(w.pack_address(2,-1)!=-1) {return -28;}}
                    if(n==3) {if(w.advance_address(8,9)!=-1) {return -29;}}
                    if(n==4) {if(w.pack_address(5,0)!=-1) {return -30;}}
                    if(n==5) {if(w.memory(-1)) {return -31;}}
                    if(n==6) {if(w.memory(5000000000)) {return -32;}}
                    if(n==7) {if(w.advance_address(1000000000,9223372036854775807)!=-1) {return -33;}}
                    if(n==8) {if(w.advance_address(-1,1)!=-1) {return -34;}}
                    if(w.status()!=compiler_x86::EmitStatus::invalid||w.advance_address(-1,1)!=-1) {return -35;}
                    return 42;
                }
                if(flag==5) {
                    if(w.begin()||w.status()!=compiler_x86::EmitStatus::allocation) {return -23;}
                    return 42;
                }
                if(!w.begin()) {return -17;}
                if(flag==3) {
                    const compiler_x86::EmitChunk incomplete=w.chunk(compiler_x86::Artifact::assembly,0);
                    if(incomplete.size()!=-1) {return -18;}
                    i64 at=0;
                    while(at<n) {if(!w.byte('x')) {return -19;} at=at+1;}
                    if(!w.finish_assembly()||!w.prepare_facts(compiler_x86::Artifact::stack)||!w.begin_stack()) {
                        return -20;
                    }
                    if(!w.text("{}")||!w.finish_stack()) {return -20;}
                    const compiler_x86::EmitChunk first=w.chunk(compiler_x86::Artifact::assembly,0);
                    const compiler_x86::EmitChunk last=w.chunk(compiler_x86::Artifact::assembly,n-1);
                    const compiler_x86::EmitChunk end=w.chunk(compiler_x86::Artifact::assembly,n);
                    const compiler_x86::EmitChunk outside=w.chunk(compiler_x86::Artifact::assembly,n+1);
                    i64 expected=n;
                    if(expected>512) {expected=512;}
                    if(first.size()!=expected||last.size()!=1||last.at(0)!='x'||end.size()!=0||outside.size()!=-1) {
                        return -21;
                    }
                    return 42;
                }
                if(w.reserve_output(67108865)||w.status()!=compiler_x86::EmitStatus::limit
                    ||w.artifact_size(compiler_x86::Artifact::assembly)!=-1) {
                    return -22;
                }
                return 42;
            }
            """,
            modules={
                "aurora.compiler.x86_storage": (ROOT / "compiler/x86_storage.au").read_text(),
                "aurora.compiler.x86_object_storage": (ROOT / "compiler/x86_object_storage.au").read_text(),
            },
        )
        self.run(executable, 0, 0, 0, 42, 8, 8)
        for last_id in (0, 7):
            self.run(executable, 128, last_id, 1, 42, 10, 8)
        for invalid_id in (-1, 0):
            self.run(executable, 0, invalid_id, 2, 42, 8, 8)
        for size in (511, 512, 513):
            self.run(executable, 4096, size, 3, 42, 9, 8)
        self.run(executable, 0, 0, 4, 42, 8, 8)
        for malformed_address in range(9):
            self.run(executable, 0, malformed_address, 6, 42, 8, 8)
        for completed in (0, 4):
            self.run(executable, 0, 0, 5, 42, completed, completed, fail_after=completed)

    def cases(self):
        self.typed_cases()
        self.emitter_storage_cases()
        self.emitter_mov_cases()
        dynamic = self.compile(
            "dynamic-two-owners",
            program(f"""
            {OWNER} a = region.try_allocate(n);
            {OWNER} b = region.try_allocate(n + 1);
            if (!a.ok() || !b.ok() || a.size() != n || b.size() != n + 1) {{ return -1; }}
            i64 i = 0;
            while (i < n) {{
                if (a.at(i) != 0u8 || b.at(i) != 0u8) {{ return -2; }}
                if (!a.set(i, u8((i * 17 + 3) % 256)) || !b.set(i, 9u8)) {{ return -3; }}
                i = i + 1;
            }}
            if (a.set(-1, 33u8) || a.set(n, 33u8) || b.at(n) != 0u8) {{ return -4; }}
            i = 0;
            i64 sum = 0;
            while (i < n) {{ sum = sum + i64(a.at(i)) + i64(b.at(i)); i = i + 1; }}
            return sum;
        """),
        )
        for length in (0, 1, 65, 513, 4097):
            self.run(
                dynamic,
                2 * length + 1,
                length,
                0,
                sum((i * 17 + 3) % 256 + 9 for i in range(length)),
                2,
                2,
                release_order=[2, 1],
            )

        helpers = f"""
            auto bounce({REGION} region, {OWNER} value, i64 flag)->{OWNER} {{
                {OWNER} sibling = region.try_allocate(3);
                if (!sibling.ok()) {{ return move(value); }}
                sibling.set(0, 91u8);
                if (flag == 0) {{ return move(value); }}
                {OWNER} moved = move(value);
                moved.set(0, 71u8);
                return move(moved);
            }}
        """
        transfer = self.compile(
            "function-transfer",
            program(
                f"""
            {OWNER} first = region.try_allocate(n);
            if (!first.ok()) {{ return -1; }}
            first.set(0, 42u8);
            {OWNER} second = move(first);
            {OWNER} returned = bounce(region, move(second), flag);
            return i64(returned.at(0));
        """,
                helpers,
            ),
        )
        for flag in (0, 1):
            self.run(transfer, 516, 513, flag, 42 if flag == 0 else 71, 2, 2, release_order=[2, 1])

        factory = self.compile(
            "owned-result-factory",
            program(
                f"""
            {OWNER} a = create(region, n);
            if (!a.ok()) {{ return 7; }}
            return a.size();
        """,
                f"""
            auto create({REGION} r,i64 count)->{OWNER}{{
                {OWNER} result = r.try_allocate(count);
                return move(result);
            }}
        """,
            ),
        )
        self.run(factory, 0, 0, 0, 0, 1, 1)
        self.run(factory, 513, 513, 0, 513, 1, 1)
        self.run(factory, 0, 65, 0, 7, 0, 0)
        choose = self.compile(
            "choose-owner-parameter",
            program(
                f"""
            {OWNER} a = region.try_allocate(1);
            {OWNER} b = region.try_allocate(1);
            a.set(0,17u8); b.set(0,29u8);
            {OWNER} selected = choose(region, move(a), move(b), flag);
            return i64(selected.at(0));
        """,
                f"""
            auto choose({REGION} r,{OWNER} a,{OWNER} b,i64 choice)->{OWNER}{{
                if (choice == 0) {{ return move(a); }}
                return move(b);
            }}
        """,
            ),
        )
        self.run(choose, 2, 0, 0, 17, 2, 2, release_order=[2, 1])
        self.run(choose, 2, 0, 1, 29, 2, 2, release_order=[1, 2])

        quota = self.compile(
            "quota-and-failure",
            program(f"""
            {OWNER} a = region.try_allocate(n);
            if (!a.ok() || !a.set(0, 17u8)) {{ return -1; }}
            {{
                {OWNER} failed = region.try_allocate(1);
                if (failed.ok() || failed.size() != 0 || failed.set(0, 2u8)) {{ return -2; }}
                {OWNER} moved = move(failed);
                if (moved.ok() || a.at(0) != 17u8) {{ return -3; }}
            }}
            return i64(a.at(0));
        """),
        )
        self.run(quota, 65, 65, 0, 17, 1, 1)
        self.run(quota, 66, 65, 0, 17, 1, 1, fail_after=1)
        loop = self.compile(
            "loop-scope-reuse",
            program(f"""
            i64 i = 0;
            while (i < n) {{
                {OWNER} a = region.try_allocate(65);
                if (!a.ok()) {{ return -1; }}
                {{ {OWNER} b = region.try_allocate(3); if (!b.ok()) {{ return -2; }} }}
                i = i + 1;
            }}
            return i;
        """),
        )
        for length in (0, 1, 31):
            self.run(
                loop,
                68,
                length,
                0,
                length,
                length * 2,
                2 if length else 0,
                release_order=[value for index in range(length) for value in (2 * index + 2, 2 * index + 1)],
            )
        failure = self.compile(
            "allocation-failure",
            program(f"""
            {OWNER} a = region.try_allocate(n);
            if (a.ok() || a.size() != 0 || a.set(-1, 4u8) || a.set(0, 4u8)) {{ return -1; }}
            return 42;
        """),
        )
        for quota_value, length in ((0, 1), (8, -1), (8, (1 << 63) - 1)):
            self.run(failure, quota_value, length, 0, 42, 0, 0)
        self.run(failure, 0, 0, 0, 42, 0, 0, fail_after=0)
        empty = self.compile(
            "empty-and-failed",
            program(f"""
            {OWNER} a = region.try_allocate(0);
            {OWNER} b = region.try_allocate(1);
            if (!a.ok() || b.ok() || a.size() != 0 || b.size() != 0) {{ return -1; }}
            {OWNER} moved = move(a);
            if (!moved.ok() || moved.set(0, 3u8)) {{ return -2; }}
            return 42;
        """),
        )
        self.run(empty, 0, 0, 0, 42, 1, 1)
        early = self.compile(
            "early-branch-cleanup",
            program(f"""
            {OWNER} a = region.try_allocate(1);
            if (flag == 0) {{ {OWNER} b = region.try_allocate(1); return 41; }}
            {{ {OWNER} b = region.try_allocate(1); }}
            return 42;
        """),
        )
        self.run(early, 2, 0, 0, 41, 2, 2, release_order=[2, 1])
        self.run(early, 2, 0, 1, 42, 2, 2, release_order=[2, 1])
        access = self.compile(
            "bounds-at",
            program(f"""
            {OWNER} a = region.try_allocate(n);
            return i64(a.at(flag));
        """),
        )
        for quota_value, length, index in ((2, 2, -1), (2, 2, 2), (0, 0, 0), (0, 1, 0)):
            self.trap(access, quota_value, length, index)

        packed = self.compile(
            "packed-resource-arguments",
            program(
                f"""
            {OWNER} a = region.try_allocate(1);
            return check(region, 231u8, true, move(a), 123u64, -7);
        """,
                f"""
            auto check({REGION} r,u8 byte,bool enabled,{OWNER} a,u64 word,i64 number)->i64{{
                if (!enabled || word != 123u64 || number != -7 || !a.set(0,byte)) {{ return -1; }}
                return i64(a.at(0));
            }}
        """,
            ),
        )
        self.run(packed, 1, 0, 0, 231, 1, 1)
        expression_drop = self.compile(
            "expression-stack-drop",
            program(
                f"""
            {OWNER} a = region.try_allocate(1);
            {OWNER} b = region.try_allocate(1);
            return 7 + consume(region, move(a)) + (9 + consume(region, move(b)));
        """,
                f"auto consume({REGION} r,{OWNER} a)->i64{{return 123;}}",
            ),
        )
        self.run(expression_drop, 2, 0, 0, 262, 2, 2)
        snapshot = self.compile(
            "left-to-right-snapshot",
            program(
                f"""
            {OWNER} a = region.try_allocate(1);
            a.set(0,42u8);
            return observe(region,a.at(0),a.set(0,99u8),move(a));
        """,
                f"""
            auto observe({REGION} r,u8 before,bool written,{OWNER} value)->i64{{
                if (before == 42u8 && written && value.at(0) == 99u8) {{ return 42; }}
                return -1;
            }}
        """,
            ),
        )
        self.run(snapshot, 1, 0, 0, 42, 1, 1, release_order=[1])
        collisions = ["malloc", "free", "memset", "abort", "fputs", "fflush", "printf", "memcpy"]
        definitions = "".join(
            f"auto {name}(i64 x)->i64{{return x+{index};}}" for index, name in enumerate(collisions, 1)
        )

        def private_helpers(text):
            for name in collisions:
                require(
                    f".local {name}\n" in text and f".globl {name}\n" not in text,
                    f"host dependency can be interposed by source helper {name}",
                )

        # Root-level helper names must stay private symbols, so this program is not packed.
        collision = self.compile(
            "local-libc-collisions",
            program(
                f"""
            {OWNER} a = region.try_allocate(65);
            if (!a.ok() || !a.set(0,42u8) || !a.try_resize(66)) {{ return -1; }}
            return i64(a.at(0)) + malloc(1) + free(1) + memset(1) + abort(1)
                   + fputs(1) + fflush(1) + printf(1) + memcpy(1);
        """,
                definitions,
            ),
            inspect=private_helpers,
        )
        self.run(collision, 66, 0, 0, 86, 2, 1, release_order=[1, 2])
        readonly = self.compile(
            "const-owner",
            program(f"""
            const {OWNER} a = region.try_allocate(1);
            if (!a.ok()) {{ return -1; }}
            return i64(a.at(0)) + a.size();
        """),
        )
        self.run(readonly, 1, 0, 0, 1, 1, 1)

        resize = self.compile(
            "resize-cycle-two-owners",
            program(f"""
            {OWNER} a = region.try_allocate(n);
            {OWNER} b = region.try_allocate(2);
            if (!a.ok() || !b.ok() || !b.set(0, 213u8)) {{ return -1; }}
            i64 i = 0;
            while (i < n) {{ a.set(i, u8((i * 17 + 3) % 256)); i = i + 1; }}
            if (!a.try_resize(n + 3) || a.size() != n + 3 || !a.ok()) {{ return -2; }}
            i = 0;
            while (i < n) {{
                if (a.at(i) != u8((i * 17 + 3) % 256)) {{ return -3; }}
                i = i + 1;
            }}
            while (i < n + 3) {{ if (a.at(i) != 0u8) {{ return -4; }} i = i + 1; }}
            if (!a.try_resize(n / 2) || a.size() != n / 2) {{ return -5; }}
            i = 0;
            while (i < n / 2) {{
                if (a.at(i) != u8((i * 17 + 3) % 256)) {{ return -6; }}
                i = i + 1;
            }}
            if (!a.try_resize(0) || !a.ok() || a.size() != 0 || a.set(0, 1u8)) {{ return -7; }}
            if (!a.try_resize(n) || a.size() != n || !a.ok()) {{ return -8; }}
            i = 0;
            while (i < n) {{ if (a.at(i) != 0u8) {{ return -9; }} i = i + 1; }}
            if (b.at(0) != 213u8 || b.at(1) != 0u8 || b.size() != 2) {{ return -10; }}
            return 42;
        """),
        )
        for length in (0, 1, 65, 513, 4097):
            order = [1, 3, 2, 4] if length == 0 else [1, 3, 4, 2, 5] if length == 1 else [1, 3, 4, 5, 2, 6]
            self.run(resize, length + 5, length, 0, 42, len(order), 2, release_order=order)

        preserved = self.compile(
            "resize-failure-preservation",
            program(f"""
            {OWNER} a = region.try_allocate(3);
            {OWNER} b = region.try_allocate(2);
            a.set(0, 17u8); a.set(1, 33u8); a.set(2, 99u8); b.set(0, 91u8);
            bool changed = a.try_resize(n);
            if (changed != (n == 3)) {{ return -1; }}
            if (!a.ok() || a.size() != 3 || a.at(0) != 17u8 || a.at(1) != 33u8 || a.at(2) != 99u8) {{ return -2; }}
            if (!b.ok() || b.size() != 2 || b.at(0) != 91u8 || b.at(1) != 0u8) {{ return -3; }}
            return 42;
        """),
        )
        for length in (-1, -(1 << 63), 4, (1 << 63) - 1):
            self.run(preserved, 5, length, 0, 42, 2, 2, release_order=[2, 1])
        for length in (0, 1, 3, 4):
            self.run(preserved, 6, length, 0, 42, 2, 2, fail_after=2, release_order=[2, 1])

        failed_resize = self.compile(
            "resize-failed-owner",
            program(f"""
            {OWNER} a = region.try_allocate(-1);
            if (a.try_resize(n) || a.ok() || a.size() != 0) {{ return -1; }}
            {OWNER} b = move(a);
            if (b.try_resize(0) || b.ok()) {{ return -2; }}
            return 42;
        """),
        )
        for length in (-1, 0, 65):
            self.run(failed_resize, 128, length, 0, 42, 0, 0)

        resized_transfer = self.compile(
            "resize-local-function-transfer",
            program(
                f"""
            {OWNER} original = region.try_allocate(2);
            original.set(0, 41u8); original.set(1, 77u8);
            {OWNER} local = move(original);
            {OWNER} result = grow(region, move(local), n);
            if (!result.ok() || result.size() != n || result.at(0) != 41u8) {{ return -1; }}
            if (n > 1 && result.at(1) != 77u8) {{ return -2; }}
            if (n > 2 && result.at(n - 1) != 0u8) {{ return -3; }}
            return 42;
        """,
                f"""
            auto grow({REGION} r, {OWNER} input, i64 count)->{OWNER}{{
                input.try_resize(count);
                return move(input);
            }}
        """,
            ),
        )
        for length in (1, 2, 65, 513):
            count = 1 if length == 2 else 2
            self.run(resized_transfer, max(2, length), length, 0, 42, count, 1, release_order=list(range(1, count + 1)))

        stack = self.compile(
            "resize-expression-stack",
            program(
                f"""
            {OWNER} a = region.try_allocate(1);
            return 7 + score(a.size(), a.try_resize(n), a.size()) +
                   (9 + score(a.size(), a.try_resize(n + 1), a.size()));
        """,
                "auto score(i64 before, bool success, i64 after)->i64 {"
                "if (!success) {return -1000;} return before * 100 + after;}",
            ),
        )
        self.run(stack, 4, 3, 0, 423, 3, 1, release_order=[1, 2, 3])

        sibling_argument = self.compile(
            "resize-argument-consumes-sibling",
            program(
                f"""
            {OWNER} a = region.try_allocate(1);
            {OWNER} b = region.try_allocate(n);
            a.set(0, 199u8);
            if (!a.try_resize(consume(region, move(b)))) {{ return -1; }}
            if (a.size() != n || a.at(0) != 199u8 || a.at(n - 1) != 0u8) {{ return -2; }}
            return 42;
        """,
                f"auto consume({REGION} r,{OWNER} b)->i64{{return b.size();}}",
            ),
        )
        self.run(sibling_argument, 66, 65, 0, 42, 3, 2, release_order=[2, 1, 3])

        loop_resize = self.compile(
            "resize-loop-and-short-circuit",
            program(f"""
            {OWNER} a = region.try_allocate(1);
            i64 i = 0;
            while (i < n && a.try_resize(i + 2)) {{ i = i + 1; }}
            if (flag == 0 && a.try_resize(-1)) {{ return -1; }}
            if (flag != 0 || a.try_resize(a.size())) {{ return i * 100 + a.size(); }}
            return -2;
        """),
        )
        self.run(loop_resize, 5, 4, 0, 405, 5, 1, release_order=[1, 2, 3, 4, 5])
        self.run(loop_resize, 5, 4, 1, 203, 3, 1, fail_after=3, release_order=[1, 2, 3])
        self.run(loop_resize, 1, 0, 0, 1, 1, 1, release_order=[1])
        branch_resize = self.compile(
            "resize-branch-keeps-authority",
            program(f"""
            {OWNER} a = region.try_allocate(1);
            if (flag == 0) {{ a.try_resize(2); }} else {{ a.try_resize(3); }}
            a.set(0, 42u8);
            return i64(a.at(0)) + a.size();
        """),
        )
        self.run(branch_resize, 3, 0, 0, 44, 2, 1, release_order=[1, 2])
        self.run(branch_resize, 3, 0, 1, 45, 2, 1, release_order=[1, 2])
        resized_bounds = self.compile(
            "resize-shrunk-bounds",
            program(f"""
            {OWNER} a = region.try_allocate(4);
            if (!a.try_resize(n)) {{ return -1; }}
            return i64(a.at(flag));
        """),
        )
        for length, index in ((0, 0), (1, 1), (2, -1)):
            self.trap(resized_bounds, 4, length, index)

        borrowed = self.compile(
            "borrow-view",
            program(f"""
            {OWNER} a = region.try_allocate(1);
            a.set(0, 42u8);
            const builtin::span<const u8> s = borrow_bytes(a);
            return i64(s.at(0));
        """),
        )
        self.run(borrowed, 1, 0, 0, 42, 1, 1, release_order=[1])

        consume = f"auto consume({REGION} r,{OWNER} b)->i64{{return 0;}}"
        declarations = f"{OWNER} a = region.try_allocate(1);"
        bad = {
            "implicit-copy": f"{OWNER} b = a; return 0;",
            "repeated-move": f"{OWNER} b=move(a); {OWNER} c=move(a); return 0;",
            "read-after-move": f"{OWNER} b=move(a); return a.size();",
            "implicit-argument": "return consume(region,a);",
            "conditional-consume": "if(flag==0){consume(region,move(a));} return 0;",
            "short-and-consume": "bool b=flag==0 && consume(region,move(a))==0; return 0;",
            "short-or-consume": "bool b=flag==0 || consume(region,move(a))==0; return 0;",
            "loop-condition-consume": "while(consume(region,move(a))==0){return 1;} return 0;",
            "loop-backedge-consume": "while(flag==0){consume(region,move(a));} return 0;",
            "at-consuming-index": "return i64(a.at(consume(region,move(a))));",
            "set-consuming-index": "a.set(consume(region,move(a)),1u8); return 0;",
            "set-consuming-value": "a.set(0,u8(consume(region,move(a)))); return 0;",
            "resize-consuming-length": "a.try_resize(consume(region,move(a))); return 0;",
            "resize-after-move": f"{OWNER} b=move(a); a.try_resize(2); return 0;",
            "resize-u64-length": "a.try_resize(2u64); return 0;",
            "resize-u8-length": "a.try_resize(2u8); return 0;",
            "resize-bool-length": "a.try_resize(true); return 0;",
            "resize-missing-length": "a.try_resize(); return 0;",
            "resize-extra-length": "a.try_resize(1,2); return 0;",
            "resize-bool-result": "i64 bad_size=a.try_resize(2); return bad_size;",
            "scalar-conversion": "return i64(a);",
            "write-borrowed-owner": "const builtin::span<const u8> s=borrow_bytes(a); a.set(0, 1u8); return 0;",
            "reflect-owner": f"return size_of({OWNER});",
            "forge-region": f"{REGION} r=1; return 0;",
            "rebind-owner": "a=move(a); return 0;",
            "discard-allocation": "region.try_allocate(1); return 0;",
        }
        for name, body in bad.items():
            self.reject(name, program(declarations + body, consume))
        self.reject("const-resize", program(f"const {OWNER} a=region.try_allocate(1);a.try_resize(2);return 0;"))
        self.reject("const-write", program(f"const {OWNER} a=region.try_allocate(1);a.set(0,1u8);return 0;"))
        self.reject("const-move", program(f"const {OWNER} a=region.try_allocate(1);{OWNER} b=move(a);return 0;"))
        self.reject("owner-field", f"module bad;class C{{private:{OWNER} b;}};auto f()->i64{{return 0;}}")
        self.reject("missing-region", f"module bad;auto f({OWNER} a)->i64{{return 0;}}")
        self.reject("two-regions", f"module bad;auto f({REGION} a,{REGION} b)->i64{{return 0;}}")
        self.reject("region-result", f"module bad;auto f({REGION} a)->{REGION}{{return a;}}")
        self.reject("implicit-return", f"module bad;auto f({REGION} r,{OWNER} a)->{OWNER}{{return a;}}")
        self.reject(
            "duplicate-argument",
            program(
                declarations + "return both(region,move(a),move(a));",
                f"auto both({REGION} r,{OWNER} a,{OWNER} b)->i64{{return 0;}}",
            ),
        )
        self.reject(
            "nested-repeated-move",
            program(
                declarations + "return take(region,move(a),consume(region,move(a)));",
                consume + f"auto take({REGION} r,{OWNER} a,i64 n)->i64{{return n;}}",
            ),
        )
        self.reject(
            "nested-first-consumption",
            program(
                declarations + "return take(region,consume(region,move(a)),move(a));",
                consume + f"auto take({REGION} r,i64 n,{OWNER} a)->i64{{return n;}}",
            ),
        )
        self.reject("reserved-helper", "module bad;auto __au_runtime_bytes_drop()->i64{return 0;}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    parser.add_argument("--artifact-dir", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="aurora-owned-bytes-") as temporary:
        directory = args.artifact_dir.resolve() if args.artifact_dir else Path(temporary)
        directory.mkdir(parents=True, exist_ok=True)
        suite = OwnedBytesCases(args.compiler.resolve(strict=True), directory, ROOT / "library", deferred=True)
        suite.cases()
        suite.finish()
        print(f"PASS owned bytes: {suite.native} native runs, {suite.traps} exact bounds traps")


if __name__ == "__main__":
    main()
