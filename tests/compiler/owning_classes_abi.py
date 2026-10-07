#!/usr/bin/env python3
"""Literal-layout handwritten owning-class boundaries with the real hosted adapter.

The direct-IR fixture is compiled separately. This runner checks handwritten
entry records, transferred descriptor clearing, padding/canaries, callee-saved
registers, runtime-helper alignment, mixed positions and exact release order.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

from unsigned_oracle import require

ROOT = Path(__file__).resolve().parents[2]

DRIVER = r"""
#include "runtime/hosted_bytes.hpp"
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
using namespace aurora::hosted::bytes;
extern "C" std::uint64_t __au_runtime_bytes_test_entry(void *, void *);
struct Trace {
    std::vector<void *> allocations;
    std::vector<bool> live;
    std::vector<std::size_t> released;
    static void *allocate(void *context, std::size_t size) noexcept {
        auto &self = *static_cast<Trace *>(context);
        void *p = std::malloc(size);
        if (p) { self.allocations.push_back(p); self.live.push_back(true); }
        return p;
    }
    static void release(void *context, void *p) noexcept {
        auto &self = *static_cast<Trace *>(context);
        for (std::size_t i = 0; i < self.allocations.size(); ++i)
            if (self.live[i] && self.allocations[i] == p) {
                self.live[i] = false; self.released.push_back(i + 1); std::free(p); return;
            }
        std::abort();
    }
};
static void check(bool value, const char *message) {
    if (!value) { std::fprintf(stderr, "ABI failure: %s\n", message); std::exit(90); }
}
static void put(void *p, std::uint64_t value) { std::memcpy(p, &value, 8); }
static std::uint64_t get(const void *p) { std::uint64_t value; std::memcpy(&value,p,8); return value; }
static void allocate_field(unsigned char *p, Region &region, std::int64_t length) {
    NativeOwner owner{}; __au_runtime_bytes_allocate(region.id(), length, &owner);
    check(owner.success == 1, "host fixture allocation succeeded"); std::memcpy(p,&owner,32);
}
static void init_parcel(unsigned char *p, Region &region, int n) {
    p[0] = 197 + n; put(p + 40, 123456789 + n); p[80] = 223 + n;
    allocate_field(p + 8,region,3 + n); allocate_field(p + 48,region,5 + n);
}
static void padding(const unsigned char *p, unsigned char poison) {
    for (int i = 1; i < 8; ++i) check(p[i] == poison, "leading representation padding preserved");
    for (int i = 81; i < 88; ++i) check(p[i] == poison, "trailing representation padding preserved");
}
static void consumed(const unsigned char *p, int n) {
    check(p[0] == 197 + n && get(p+40) == static_cast<unsigned>(123456789+n) && p[80] == 223+n,
          "move preserves source scalar bytes");
    for (int base : {8,48}) for (int i = 0; i < 32; ++i) check(p[base+i] == 0, "source descriptor cleared");
    padding(p,0xab);
}
static void valid_result(const unsigned char *p, Region &region) {
    check(p[0] == 197 && get(p+40) == 123456789 && p[80] == 223, "result scalar layout");
    for (int base : {8,48}) {
        check(get(p+base) == region.id() && get(p+base+8) != 0 && get(p+base+24) == 1,
              "result descriptor words survive padding cleanup");
        check(get(p+base+16) == static_cast<unsigned>(base == 8 ? 3 : 5), "result descriptor length");
    }
    padding(p,0xcd);
}
static void drop(unsigned char *p) {
    NativeOwner owner{}; std::memcpy(&owner,p,32); std::memset(p,0,32); __au_runtime_bytes_drop(&owner);
}
int main(int argc, char **argv) {
    check(argc == 2,"one fixture mode"); const std::string mode = argv[1];
    Trace trace; Region region(1024, Allocator{&trace, Trace::allocate, Trace::release});
    alignas(16) std::array<unsigned char, 208> input;
    alignas(16) std::array<unsigned char, 112> output;
    input.fill(0xab); output.fill(0xcd);
    unsigned char *record = input.data()+8, *result = output.data()+8;
    put(record,region.id());
    if (mode == "move" || mode == "six") init_parcel(record+8,region,0);
    if (mode == "six") init_parcel(record+96,region,1);
    if (mode == "method") init_parcel(record,region,0);
    const auto input_before = input;
    const auto answer = __au_runtime_bytes_test_entry(record,result);
    if (mode.starts_with("construct"))
        check(answer == (mode == "construct" ? 8 : 42),"constructor lengths and cleanup preserve result");
    else if (mode == "copied") check(answer == 42,"owning receiver with copied args and result");
    else if (mode == "method") {
        check(answer == 1,"borrowed payload write result");
        check(input == input_before,"borrowed method does not alter descriptor/scalar/padding bytes");
        NativeOwner owner{}; std::memcpy(&owner,record+8,32);
        check(__au_runtime_bytes_at(&owner,0) == 42,"borrowed write reaches actual payload");
        drop(record+48); drop(record+8);
    } else {
        consumed(record+8,0); if (mode == "six") consumed(record+96,1);
        valid_result(result,region);
        NativeOwner owner{}; std::memcpy(&owner,result+8,32);
        check(__au_runtime_bytes_at(&owner,0) == 0,
              "real zeroed allocated payload survived transfer");
        drop(result+48); drop(result+8);
    }
    for (int i = 0; i < 8; ++i) check(input[i] == 0xab && output[i] == 0xcd,"left canary");
    const int input_extent = mode == "six" ? 184 : mode == "move" ? 96 : mode == "method" ? 88 : 8;
    for (std::size_t i = 8 + input_extent; i < input.size(); ++i) check(input[i] == 0xab,"right input canary");
    for (std::size_t i = 96; i < output.size(); ++i) check(output[i] == 0xcd,"right result canary");
    if (mode.starts_with("construct") || mode == "method" || mode == "copied")
        for (auto byte : output) check(byte == 0xcd,"scalar result does not write hidden destination");
    std::vector<std::size_t> expected = mode == "copied" ? std::vector<std::size_t>{1}
                                     : mode == "six" ? std::vector<std::size_t>{5,4,3,2,1}
                                                       : std::vector<std::size_t>{2,1};
    check(trace.released == expected,"exact reverse release order, no duplicate release");
    const auto metrics = region.metrics();
    check(metrics.used == 0 && metrics.live_allocations == 0 && metrics.releases == expected.size(),
          "all transferred resources released exactly once");
    check(region.close(),"region closes without leaked owners");
    std::printf("PASS hosted owning ABI %s", mode.c_str());
    for (auto id : trace.released) std::printf(" %zu",id);
    std::puts("");
}
"""

ALIGN = "movq %rsp,%r9\nandq $15,%r9\ncmpq $8,%r9\njne .Lowning_abi_fail\n"


def bridge(mode):
    target = "owning_method" if mode == "method" else "owning_entry"
    text = "\n.text\n.globl __au_runtime_bytes_test_entry\n__au_runtime_bytes_test_entry:\n"
    text += "pushq %rbp\npushq %rbx\npushq %r12\npushq %r13\npushq %r14\npushq %r15\nsubq $8,%rsp\n"
    text += "movq $111,%rbp\nmovq $222,%rbx\nmovq $333,%r12\nmovq $444,%r13\nmovq $555,%r14\nmovq $666,%r15\n"
    text += "movq %rdi,%r10\n" if mode == "method" else "movq %rdi,%r11\nmovq %rsi,%r10\n"
    text += f"call {target}\n"
    for register, value in [("rbp", 111), ("rbx", 222), ("r12", 333), ("r13", 444), ("r14", 555), ("r15", 666)]:
        text += f"cmpq ${value},%{register}\njne .Lowning_abi_fail\n"
    text += "addq $8,%rsp\npopq %r15\npopq %r14\npopq %r13\npopq %r12\npopq %rbx\npopq %rbp\nret\n"
    for name in ("allocate", "drop", "at", "set"):
        text += f"owning_abi_{name}:\n{ALIGN}jmp __au_runtime_bytes_{name}\n"
    return text + '.Lowning_abi_fail:\nud2\n.section .note.GNU-stack,"",@progbits\n'


def move_descriptor(source, destination, source_base=0, destination_base=0):
    code = ""
    for byte in range(0, 32, 8):
        code += f"movq {source_base + byte}({source}),%rcx\nmovq %rcx,{destination_base + byte}({destination})\n"
        code += f"movq $0,{source_base + byte}({source})\n"
    return code


def compare_byte(base, offset, value):
    return f"cmpb ${value},{offset}({base})\njne .Lowning_abi_fail\n"


def handwritten_constructor():
    code = ALIGN
    code += "cmpq %r10,%r11\nje .Lowning_abi_fail\n"
    code += compare_byte("%r11", 40, 197) + compare_byte("%r11", 88, 223)
    code += "cmpq $123456789,80(%r11)\njne .Lowning_abi_fail\n"
    for offset, size in [(8, 3), (48, 5)]:
        code += f"movq (%r11),%rcx\ncmpq %rcx,{offset}(%r11)\njne .Lowning_abi_fail\n"
        code += f"cmpq ${size},{offset + 16}(%r11)\njne .Lowning_abi_fail\n"
        code += f"cmpq $1,{offset + 24}(%r11)\njne .Lowning_abi_fail\n"
        for word in range(0, 32, 8):
            code += f"cmpq $0,{offset + word}(%r10)\njne .Lowning_abi_fail\n"
        code += move_descriptor("%r11", "%r10", offset, offset)
    code += "movb $197,(%r10)\nmovq $123456789,40(%r10)\nmovb $223,80(%r10)\nxorq %rax,%rax\nret\n"
    return code


def handwritten_six():
    code = ALIGN + "cmpq %r10,%r11\nje .Lowning_abi_fail\n"
    code += compare_byte("%r11", 96, 201)
    code += "movabsq $0x123456789,%rcx\ncmpq %rcx,136(%r11)\njne .Lowning_abi_fail\n"
    code += "cmpq $7,120(%r11)\njne .Lowning_abi_fail\n"
    for parcel_base, n in [(8, 0), (144, 1)]:
        code += compare_byte("%r11", parcel_base, 197 + n)
        code += compare_byte("%r11", parcel_base + 80, 223 + n)
        code += f"cmpq ${123456789 + n},{parcel_base + 40}(%r11)\njne .Lowning_abi_fail\n"
        for i in list(range(1, 8)) + list(range(81, 88)):
            code += compare_byte("%r11", parcel_base + i, 0)
        for offset, size in [(8, 3 + n), (48, 5 + n)]:
            code += f"movq (%r11),%rcx\ncmpq %rcx,{parcel_base + offset}(%r11)\njne .Lowning_abi_fail\n"
            code += f"cmpq ${size},{parcel_base + offset + 16}(%r11)\njne .Lowning_abi_fail\n"
            code += f"cmpq $1,{parcel_base + offset + 24}(%r11)\njne .Lowning_abi_fail\n"
    for i in range(97, 104):
        code += compare_byte("%r11", i, 0)
    for i in range(232, 240):
        code += compare_byte("%r11", i, 0)
    # Save private input/result pointers across real runtime drops.
    code += "pushq %rbp\npushq %r12\npushq %r13\nmovq %r11,%r12\nmovq %r10,%r13\n"
    code += "movb 8(%r12),%cl\nmovb %cl,(%r13)\nmovq 48(%r12),%rcx\nmovq %rcx,40(%r13)\n"
    code += "movb 88(%r12),%cl\nmovb %cl,80(%r13)\n"
    code += move_descriptor("%r12", "%r13", 16, 8) + move_descriptor("%r12", "%r13", 56, 48)
    for offset in (104, 192, 152):
        code += f"leaq {offset}(%r12),%rdi\ncall owning_abi_drop\n"
    code += "popq %r13\npopq %r12\npopq %rbp\nxorq %rax,%rax\nret\n"
    return code


def handwritten_copied():
    code = ALIGN
    for left, right in [("%r10", "%r11"), ("%r10", "%rax"), ("%r11", "%rax")]:
        code += f"cmpq {left},{right}\nje .Lowning_abi_fail\n"
    for offset, value in [(16, 3), (24, 1), (40, 99)]:
        code += f"cmpq ${value},{offset}(%r10)\njne .Lowning_abi_fail\n"
    code += compare_byte("%r10", 32, 17) + compare_byte("%r10", 48, 77)
    code += compare_byte("%r11", 0, 17)
    code += "cmpq $99,8(%r11)\njne .Lowning_abi_fail\ncmpq $42,16(%r11)\njne .Lowning_abi_fail\n"
    for i in list(range(1, 8)) + list(range(24, 32)):
        code += compare_byte("%r11", i, 0)
    code += "movb $17,(%rax)\nmovq $42,8(%rax)\nxorq %rax,%rax\nret\n"
    return code


def command(args, timeout=60):
    result = subprocess.run([str(arg) for arg in args], capture_output=True, timeout=timeout, check=False)
    require(
        result.returncode == 0,
        f"command failed ({result.returncode}): {' '.join(str(arg) for arg in args)}\n"
        + result.stdout.decode(errors="replace")
        + result.stderr.decode(errors="replace"),
    )
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    cxx = shlex.split(os.environ.get("CXX", "g++"))
    count = 0
    with tempfile.TemporaryDirectory(prefix="aurora-owning-abi-") as temporary:
        directory = args.work_dir or Path(temporary)
        directory.mkdir(parents=True, exist_ok=True)
        driver = directory / "driver.cpp"
        driver.write_text(DRIVER)
        command(
            [
                *cxx,
                "-std=c++23",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                ROOT,
                "-c",
                driver,
                "-o",
                directory / "driver.o",
            ]
        )
        command(
            [
                *cxx,
                "-std=c++23",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                ROOT,
                "-c",
                ROOT / "runtime/hosted_bytes.cpp",
                "-o",
                directory / "runtime.o",
            ]
        )
        for mode in ("move", "construct", "construct-odd", "construct-even", "six", "method", "copied"):
            assembly = command([args.fixture.resolve(), "--emit-abi", mode]).decode()
            for handwritten in (False, True) if mode in ("construct", "six", "copied") else (False,):
                candidate = assembly
                if handwritten:
                    symbol = (
                        "owning_constructor"
                        if mode == "construct"
                        else "copy_method"
                        if mode == "copied"
                        else "owning_six"
                    )
                    body = (
                        handwritten_constructor()
                        if mode == "construct"
                        else handwritten_copied()
                        if mode == "copied"
                        else handwritten_six()
                    )
                    pattern = rf"(?m)^{symbol}:\n[\s\S]*?^\.size {symbol},[^\n]*\n"
                    candidate, replaced = re.subn(
                        pattern, lambda _: f"{symbol}:\n{body}.size {symbol},.-{symbol}\n", candidate
                    )
                    require(replaced == 1, "exactly one private emitted target replaced")
                candidate = re.sub(
                    r"call __au_runtime_bytes_(allocate|drop|at|set)\b", r"call owning_abi_\1", candidate
                )
                stem = f"{mode}-{int(handwritten)}"
                source = directory / (stem + ".s")
                source.write_text(candidate + bridge(mode))
                executable = directory / (stem + ".elf")
                command([*cxx, "-no-pie", directory / "driver.o", directory / "runtime.o", source, "-o", executable])
                symbols = command(["nm", executable]).decode()
                for symbol in ["owning_method"] if mode == "method" else ["owning_entry"]:
                    require(re.search(rf"\bt {symbol}$", symbols, re.M), "resource entry retains private binding")
                output = command([executable, mode]).decode()
                (directory / (stem + ".observation")).write_text(output)
                require(output.startswith("PASS hosted owning ABI"), "hosted adapter observation recorded")
                print(f"PASS owning class ABI {mode} handwritten-target={handwritten}: {output.strip()}", flush=True)
                count += 1
        # Deliberate backend-text mutants establish that the literal host oracle
        # detects descriptor clearing, representation padding, and drop ordering.
        mutants = []
        move = (directory / "move-0.s").read_text()
        original = "    movq $0, 16(%r11)"
        require(move.count(original) == 1, "one descriptor source-clear mutant site")
        mutants.append(("source-clear", "move", move.replace(original, "    nop"), "source descriptor cleared"))
        original = "    movq -432(%rbp), %r10"
        require(move.count(original) == 1, "one owning return result-pointer site")
        mutants.append(
            (
                "result-padding",
                "move",
                move.replace(original, original + "\n    movb $0, 1(%r10)"),
                "leading representation padding preserved",
            )
        )
        construct = (directory / "construct-0.s").read_text()
        left, right = "    leaq -48(%rbp), %rdi", "    leaq -88(%rbp), %rdi"
        require(construct.count(left) == 1 and construct.count(right) == 1, "one class reverse-drop pair")
        reversed_drops = construct.replace(left, "REVERSE_DROP_SENTINEL").replace(right, left)
        reversed_drops = reversed_drops.replace("REVERSE_DROP_SENTINEL", right)
        mutants.append(("drop-order", "construct", reversed_drops, "exact reverse release order"))
        for name, mode, candidate, diagnostic in mutants:
            source = directory / ("mutant-" + name + ".s")
            executable = directory / ("mutant-" + name + ".elf")
            source.write_text(candidate)
            command([*cxx, "-no-pie", directory / "driver.o", directory / "runtime.o", source, "-o", executable])
            result = subprocess.run([str(executable), mode], capture_output=True, timeout=30, check=False)
            observed = result.stdout.decode(errors="replace") + result.stderr.decode(errors="replace")
            (directory / ("mutant-" + name + ".observation")).write_text(observed)
            require(result.returncode == 90 and diagnostic in observed, f"{name}: exact host oracle rejects mutant")
            print(f"PASS owning class ABI rejected mutant {name}", flush=True)
    print(f"PASS owning class ABI: {count} literal-layout hosted boundary cases and 3 rejected mutants")


if __name__ == "__main__":
    main()
