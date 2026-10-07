#!/usr/bin/env python3
"""Focused source/native ownership tests, using the real hosted bootstrap adapter.

No alternate interpreter or fixed buffer models allocation. A trusted scalar-return
bridge grants one region for each invocation. The driver checks that its grant can
close, reports real allocation counters, and verifies bounds traps at the exact
emitted UD2. Generated Aurora assembly is not sanitizer-instrumented.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

from unsigned_oracle import require

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
    void *allocations[128] {};
    bool live[128] {};
    std::size_t released[128] {};
    std::size_t allocated_count = 0;
    std::size_t released_count = 0;
};
static void *allocate(void *context, std::size_t size) noexcept {
    auto &trace = *static_cast<Trace *>(context);
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
}
"""

BRIDGE = r"""
.text
.globl __au_runtime_bytes_test_entry
.type __au_runtime_bytes_test_entry, @function
__au_runtime_bytes_test_entry:
    pushq %rbp
    movq %rsp, %rbp
    subq $32, %rsp
    movq %rdi, (%rsp)
    movq %rsi, 8(%rsp)
    movq %rdx, 16(%rsp)
    movq $0, 24(%rsp)
    movq %rsp, %r11
    call ENTRY
    leave
    ret
.size __au_runtime_bytes_test_entry, .-__au_runtime_bytes_test_entry
.globl __au_runtime_bytes_test_bounds
.set __au_runtime_bytes_test_bounds, .Laurora_bounds_trap
.section .note.GNU-stack,"",@progbits
"""


def program(body, helpers=""):
    return f"module owned_bytes;{helpers}auto entry({REGION} region,i64 n,i64 flag)->i64{{{body}}}"


def command(args, timeout=30):
    result = subprocess.run([str(arg) for arg in args], capture_output=True, timeout=timeout, check=False)
    return result


class Suite:
    def __init__(self, compiler, directory):
        self.compiler = compiler
        self.directory = directory
        self.native = self.rejections = self.programs = self.traps = 0
        self.cxx = shlex.split(os.environ.get("CXX", "g++"))
        self.driver = directory / "driver.cpp"
        self.driver.write_text(DRIVER)

    def compile(self, name, source):
        folder = self.directory / name
        folder.mkdir()
        source_path = folder / "input.au"
        source_path.write_text(source)
        assembly = folder / "output.s"
        result = command([self.compiler, source_path, "-o", assembly])
        require(result.returncode == 0, f"{name}: compile failed: {result.stderr.decode()}")
        text = assembly.read_text()
        symbols = re.findall(r"^\.type ([A-Za-z_][A-Za-z_0-9]*), @function$", text, re.M)
        entries = [
            symbol
            for symbol in symbols
            if not symbol.startswith("aurora_reflect_") and not symbol.startswith("__au_reflect_")
        ]
        require(entries, f"{name}: no native function")
        entry = entries[-1]
        require(f".local {entry}\n" in text, f"{name}: resource entry must stay private")
        assembly.write_text(text + BRIDGE.replace("ENTRY", entry))
        executable = folder / "native"
        result = command(
            [
                *self.cxx,
                "-std=c++23",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Wpedantic",
                "-Werror",
                "-I",
                ROOT,
                self.driver,
                ROOT / "runtime/hosted_bytes.cpp",
                assembly,
                "-o",
                executable,
            ],
            timeout=60,
        )
        require(result.returncode == 0, f"{name}: host link failed: {result.stderr.decode()}")
        self.programs += 1
        return executable

    def run(self, executable, quota, length, flag, expected, allocations, peak, fail_after=None, release_order=None):
        arguments = [executable, quota, length, flag]
        if fail_after is not None:
            arguments.append(fail_after)
        result = command(arguments)
        require(result.returncode == 0, f"{executable.name}: execution failed {result.returncode}: {result.stderr!r}")
        observed = [int(part) for part in result.stdout.split()]
        require(
            observed[:4] == [expected & MASK, allocations, allocations, peak],
            f"{executable.parent.name}: observed {observed}, expected {expected, allocations, peak}",
        )
        require(sorted(observed[4:]) == list(range(1, allocations + 1)), "actual allocation/free identity mismatch")
        if release_order is not None:
            require(observed[4:] == release_order, f"wrong cleanup order: {observed[4:]} != {release_order}")
        self.native += 1

    def trap(self, executable, quota, length, flag=0):
        result = command([executable, quota, length, flag])
        require(
            result.returncode == 77 and result.stdout == b"exact-bounds-trap\n",
            f"{executable.parent.name}: wrong fault {result.returncode}: {result.stdout!r}",
        )
        self.traps += 1

    def reject(self, name, source):
        folder = self.directory / ("reject-" + name)
        folder.mkdir()
        input_path = folder / "input.au"
        output = folder / "output.s"
        input_path.write_text(source)
        for prior in (None, b"preserve existing output\n"):
            if prior is not None:
                output.write_bytes(prior)
            result = command([self.compiler, input_path, "-o", output])
            require(result.returncode == 1 and result.stderr, f"{name}: expected clean rejection, got {result}")
            require(
                (not output.exists()) if prior is None else output.read_bytes() == prior,
                f"{name}: rejection modified output",
            )
        self.rejections += 1

    def cases(self):
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
        collisions = ["malloc", "free", "memset", "abort", "fputs", "fflush", "printf"]
        definitions = "".join(
            f"auto {name}(i64 x)->i64{{return x+{index};}}" for index, name in enumerate(collisions, 1)
        )
        collision = self.compile(
            "local-libc-collisions",
            program(
                f"""
            {OWNER} a = region.try_allocate(65);
            if (!a.ok() || !a.set(0,42u8)) {{ return -1; }}
            return i64(a.at(0)) + malloc(1) + free(1) + memset(1) + abort(1)
                   + fputs(1) + fflush(1) + printf(1);
        """,
                definitions,
            ),
        )
        emitted = (collision.parent / "output.s").read_text()
        for name in collisions:
            require(
                f".local {name}\n" in emitted and f".globl {name}\n" not in emitted,
                f"host dependency can be interposed by source helper {name}",
            )
        self.run(collision, 65, 0, 0, 77, 1, 1, release_order=[1])
        readonly = self.compile(
            "const-owner",
            program(f"""
            const {OWNER} a = region.try_allocate(1);
            if (!a.ok()) {{ return -1; }}
            return i64(a.at(0)) + a.size();
        """),
        )
        self.run(readonly, 1, 0, 0, 1, 1, 1)

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
            "scalar-conversion": "return i64(a);",
            "borrow-view": "const builtin::span<const u8> s=borrow_bytes(a); return 0;",
            "reflect-owner": f"return size_of({OWNER});",
            "forge-region": f"{REGION} r=1; return 0;",
            "rebind-owner": "a=move(a); return 0;",
            "discard-allocation": "region.try_allocate(1); return 0;",
        }
        for name, body in bad.items():
            self.reject(name, program(declarations + body, consume))
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
        return {
            "programs": self.programs,
            "native_cases": self.native,
            "exact_bounds_traps": self.traps,
            "source_rejections": self.rejections,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    parser.add_argument("--artifact-dir", type=Path)
    args = parser.parse_args()
    compiler = args.compiler.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="aurora-owned-bytes-") as temporary:
        directory = args.artifact_dir.resolve() if args.artifact_dir else Path(temporary)
        directory.mkdir(parents=True, exist_ok=True)
        summary = Suite(compiler, directory).cases()
        summary["compiler_sha256"] = hashlib.sha256(compiler.read_bytes()).hexdigest()
        (directory / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
