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

# Appended to compiler output, which already owns the non-executable-stack note.
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
"""


def bridged_assembly(text, entry):
    assembly = text + BRIDGE.replace("ENTRY", entry)
    notes = [line.strip() for line in assembly.splitlines() if ".note.GNU-stack" in line]
    require(notes == ['.section .note.GNU-stack,"",@progbits'], "bridge requires one non-executable-stack note")
    return assembly


def bridge_self_test():
    note = '.section .note.GNU-stack,"",@progbits\n'
    bridged_assembly(".text\n" + note, "entry")
    for text in (
        ".text\n",
        note + note,
        note.replace('"",', '"x",'),
        note + '.section .note.GNU-stack,"x",@progbits\n',
    ):
        try:
            bridged_assembly(text, "entry")
        except AssertionError:
            pass
        else:
            raise AssertionError("bridge accepted a missing, duplicate or executable stack note")


def program(body, helpers=""):
    return f"module owned_bytes;{helpers}auto entry({REGION} region,i64 n,i64 flag)->i64{{{body}}}"


def command(args, timeout=30):
    result = subprocess.run([str(arg) for arg in args], capture_output=True, timeout=timeout, check=False)
    return result


class Suite:
    def __init__(self, compiler, directory, module_root=None, entry_name=None):
        self.compiler = compiler
        self.module_args = [] if module_root is None else ["--module-root", module_root]
        self.entry_name = entry_name
        self.directory = directory
        self.native = self.rejections = self.programs = self.traps = 0
        self.cxx = shlex.split(os.environ.get("CXX", "g++"))
        self.driver = directory / "driver.cpp"
        self.driver.write_text(DRIVER)

    def compile(self, name, source, entry_name=None):
        folder = self.directory / name
        folder.mkdir()
        source_path = folder / "input.au"
        source_path.write_text(source)
        assembly = folder / "output.s"
        result = command([self.compiler, *self.module_args, source_path, "-o", assembly])
        require(result.returncode == 0, f"{name}: compile failed: {result.stderr.decode()}")
        text = assembly.read_text()
        symbols = re.findall(r"^\.type ([A-Za-z_][A-Za-z_0-9]*), @function$", text, re.M)
        entries = [
            symbol
            for symbol in symbols
            if not symbol.startswith("aurora_reflect_") and not symbol.startswith("__au_reflect_")
        ]
        require(entries, f"{name}: no native function")
        selected_name = entry_name or self.entry_name
        if selected_name is None:
            entry = entries[-1]
        else:
            selected = [
                symbol
                for symbol in entries
                if symbol == selected_name or symbol.endswith(f"__d{len(selected_name)}{selected_name}")
            ]
            require(len(selected) == 1, f"{name}: expected one entry named {selected_name}, found {selected}")
            entry = selected[0]
        require(f".local {entry}\n" in text, f"{name}: resource entry must stay private")
        assembly.write_text(bridged_assembly(text, entry))
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
        self.last_observation = result
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
            result = command([self.compiler, *self.module_args, input_path, "-o", output])
            require(result.returncode == 1 and result.stderr, f"{name}: expected clean rejection, got {result}")
            require(
                (not output.exists()) if prior is None else output.read_bytes() == prior,
                f"{name}: rejection modified output",
            )
        self.rejections += 1

    def typed_cases(self):
        previous_entry = self.entry_name
        self.entry_name = "entry"
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
                "typed-invalid-element-" + str(self.rejections),
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
        compact = self.compile(
            "typed-compact-copied-return",
            program("Wide copied=snapshot(region,n,flag);return score(17,copied,29)-46;", wide_helpers),
        )
        compact_text = (compact.parent / "output.s").read_text()
        require("rep movsb" in compact_text, "typed wide copied value did not exercise compact copies")
        require(
            "leaq 8(%rsp), %rax\n    pushq %rsi\n    pushq %rdi\n    pushq %rcx" in compact_text,
            "typed wide copied argument did not exercise captured RSP packing",
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
            self.reject("typed-consumed-receiver-" + str(self.rejections), program(body, consuming))

        module_root = self.directory / "typed-module-inputs"
        module_root.mkdir()
        (module_root / "left.au").write_text(
            "export module left;export namespace left {class Node{public:i64 value;};auto marker()->i64{return 0;}}"
        )
        (module_root / "right.au").write_text(
            "export module right;export namespace right {class Node{public:i64 value;};auto marker()->i64{return 0;}}"
        )
        previous_modules = self.module_args
        self.module_args = [*previous_modules, "--module-root", module_root]
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
        imported_owner = self.compile("typed-imported-identity", imported)
        self.run(imported_owner, 800, 0, 0, 42, 1, 1)
        self.reject("typed-imported-wrong-fill", imported.replace("(100,left)", "(100,right)"))
        self.reject("typed-imported-wrong-result", imported.replace("left::Node copied", "right::Node copied"))
        self.module_args = previous_modules

        self.entry_name = previous_entry

    def cases(self):
        self.typed_cases()
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
        )
        emitted = (collision.parent / "output.s").read_text()
        for name in collisions:
            require(
                f".local {name}\n" in emitted and f".globl {name}\n" not in emitted,
                f"host dependency can be interposed by source helper {name}",
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
        return {
            "programs": self.programs,
            "native_cases": self.native,
            "exact_bounds_traps": self.traps,
            "source_rejections": self.rejections,
        }


def main():
    bridge_self_test()
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
