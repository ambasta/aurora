#!/usr/bin/env python3
"""Fresh generated owner-span consumers against the real fragmented kernel adapter.

This is a host integration, not a guest or a substitute for guest admission.
Fatal sanitizers instrument host C++ only; generated Aurora stays unsanitized.
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

ROOT = Path(__file__).resolve().parents[2]
SOURCE = """module owned_spans_kernel;
import std.binary;
import std.utf8;

auto consume(builtin::span<const u8> bytes) -> i64 {
    const builtin::span<const u8> copy = bytes;
    if (copy.size() != 8193) { return -9; }
    const builtin::span<const u8> emoji = copy.subspan(4095, 4);
    const std::Utf8DecodeResult decoded = std::decode_utf8(emoji, 0, emoji.size(), true);
    const std::Utf8ValidationResult valid = std::validate_utf8(emoji, 0, emoji.size(), true);
    if (decoded.status() != std::Utf8Status::success || decoded.scalar_or(0u64) != 128512u64 ||
        decoded.width() != 4 || valid.status() != std::Utf8Status::success ||
        valid.prefix_bytes() != 4 || valid.scalar_count() != 1) { return -10; }
    const builtin::span<const u8> crossing = copy.subspan(8189, 4);
    const std::ByteReadResult little = std::read_le32(crossing, 0);
    const std::ByteReadResult big = std::read_be32(crossing, 0);
    if (little.status() != std::ByteReadStatus::success || little.value_or(0u64) != 2018915346u64 ||
        big.status() != std::ByteReadStatus::success || big.value_or(0u64) != 305419896u64) { return -11; }
    const builtin::span<const u8> endpoint = copy.subspan(copy.size(), 0);
    if (endpoint.size() != 0 || copy.at(0) != 101u8 || copy.at(4095) != 240u8 ||
        copy.at(4096) != 159u8 || copy.at(8191) != 86u8 || copy.at(8192) != 120u8) { return -12; }
    return 42;
}

auto forward(builtin::span<const u8> bytes) -> i64 {
    const builtin::span<const u8> copy = bytes;
    const builtin::span<const u8> nested = copy.subspan(0, copy.size());
    return consume(nested.subspan(0, nested.size()));
}

auto entry(builtin::ByteRegion region, i64 length, i64 mode) -> i64 {
    builtin::OwnedBytes owner = region.try_allocate(length);
    if (mode == 2) {
        const builtin::span<const u8> failed = borrow_bytes(owner);
        return failed.size();
    }
    if (!owner.ok() || owner.size() != length) { return -1; }
    if (mode == 1) {
        const builtin::span<const u8> empty = borrow_bytes(owner);
        const builtin::span<const u8> copy = empty;
        const builtin::span<const u8> endpoint = copy.subspan(0, 0);
        const std::Utf8DecodeResult decoded = std::decode_utf8(endpoint, 0, 0, true);
        const std::ByteReadResult word = std::read_le32(endpoint, 0);
        if (copy.size() != 0 || endpoint.size() != 0 || decoded.status() != std::Utf8Status::end_of_input ||
            word.status() != std::ByteReadStatus::out_of_range) { return -2; }
        return 42;
    }
    if (mode != 0 || length != 8193) { return -3; }
    if (!owner.set(0, 101u8) || !owner.set(4095, 240u8) || !owner.set(4096, 159u8) ||
        !owner.set(4097, 152u8) || !owner.set(4098, 128u8) || !owner.set(8189, 18u8) ||
        !owner.set(8190, 52u8) || !owner.set(8191, 86u8) || !owner.set(8192, 120u8)) { return -4; }
    {
        const builtin::span<const u8> view = borrow_bytes(owner);
        const builtin::span<const u8> sibling = borrow_bytes(owner);
        const builtin::span<const u8> copy = view;
        if (forward(copy) != 42 || consume(sibling) != 42) { return -5; }
    }
    if (!owner.set(1, 77u8)) { return -6; }
    {
        const builtin::span<const u8> again = borrow_bytes(owner);
        if (again.at(1) != 77u8 || forward(again) != 42) { return -7; }
    }
    return 42;
}
"""
RECEIVER_CLASS = """
class ReceiverBytes {
    u8 prefix;
    builtin::OwnedBytes payload;
    u64 suffix;
public:
    ReceiverBytes(builtin::ByteRegion region, builtin::OwnedBytes initial)
        : prefix(91u8), payload(move(initial)), suffix(123456789u64) {}
    auto ok() const -> bool { return payload.ok(); }
    auto size() const -> i64 { return payload.size(); }
    auto set(i64 index, u8 value) -> bool { return payload.set(index, value); }
    auto check() const -> bool { return prefix == 91u8 && suffix == 123456789u64; }
    auto bytes() const -> builtin::span<const u8> {
        const builtin::span<const u8> whole = borrow_bytes(payload);
        const builtin::span<const u8> copy = whole;
        return copy.subspan(0, copy.size());
    }
};
"""
BRIDGE = """
.text
.globl __au_runtime_owned_spans_kernel_entry
.type __au_runtime_owned_spans_kernel_entry, @function
__au_runtime_owned_spans_kernel_entry:
    pushq %rbp
    movq %rsp, %rbp
    subq $32, %rsp
    movq %rdi, (%rsp)
    movq %rsi, 8(%rsp)
    movq %rdx, 16(%rsp)
    movq $0, 24(%rsp)
    movq %rsp, %r11
    call @ENTRY@
    leave
    ret
.size __au_runtime_owned_spans_kernel_entry, .-__au_runtime_owned_spans_kernel_entry
.section .note.GNU-stack,"",@progbits
"""


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def receiver_source():
    source = SOURCE.replace("module owned_spans_kernel;", "module owned_spans_kernel_receiver;")
    source = source.replace("auto entry(", RECEIVER_CLASS + "\nauto entry(")
    source = source.replace(
        "    builtin::OwnedBytes owner = region.try_allocate(length);",
        "    builtin::OwnedBytes allocation = region.try_allocate(length);\n"
        "    ReceiverBytes owner = ReceiverBytes(region, move(allocation));",
    ).replace("borrow_bytes(owner)", "owner.bytes()")
    source = source.replace(
        "if (!owner.ok() || owner.size() != length)", "if (!owner.check() || !owner.ok() || owner.size() != length)"
    )
    source = source.replace("if (!owner.set(1, 77u8))", "if (!owner.check() || !owner.set(1, 77u8))")
    prefix, separator, suffix = source.rpartition("    return 42;\n}")
    require(bool(separator), "receiver final success anchor changed")
    return prefix + "    if (!owner.check()) { return -8; }\n" + separator + suffix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--sanitize", action="store_true")
    parser.add_argument("--compile-only", action="store_true")
    parser.add_argument("--receiver-bound", action="store_true")
    args = parser.parse_args()
    compiler = args.compiler.resolve(strict=True)
    directory = (
        args.artifacts.resolve() if args.artifacts else Path(tempfile.mkdtemp(prefix="aurora-owner-span-kernel-"))
    )
    if args.artifacts:
        directory.mkdir(parents=True, exist_ok=False)
    sources = [
        compiler,
        Path(__file__).resolve(),
        ROOT / "tests/compiler/owned_spans_kernel_host.cpp",
        ROOT / "kernel/owned-bytes.cpp",
        ROOT / "kernel/owned-bytes.hpp",
        ROOT / "kernel/pages.hpp",
        ROOT / "runtime/bytes_abi.hpp",
        *sorted((ROOT / "library").rglob("*.au")),
    ]
    inputs = {str(path): digest(path) for path in sources}
    receipt = dict(
        status="running",
        inputs=inputs,
        sanitize=args.sanitize,
        compile_only=args.compile_only,
        receiver_bound=args.receiver_bound,
        guest_executed=False,
        commands=[],
    )

    def save():
        (directory / "run.json").write_text(json.dumps(receipt, indent=2) + "\n")

    def run(label, argv, expected=0, env=None):
        argv = list(map(str, argv))
        result = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, timeout=120)
        (directory / (label + ".stdout")).write_bytes(result.stdout)
        (directory / (label + ".stderr")).write_bytes(result.stderr)
        receipt["commands"].append(dict(label=label, argv=argv, returncode=result.returncode, expected=expected))
        save()
        require(result.returncode == expected, f"{label}: expected {expected}, got {result.returncode}")
        return result

    print(f"artifacts={directory}", flush=True)
    save()
    try:
        source = directory / "input.au"
        source.write_text(receiver_source() if args.receiver_bound else SOURCE)
        assembly = directory / "output.s"
        run("compile", [compiler, "--module-root", ROOT / "library", source, "-o", assembly])
        text = assembly.read_text()
        entries = re.findall(r"^\.type (\w+__d5entry), @function$", text, re.M)
        require(len(entries) == 1 and f".local {entries[0]}\n" in text, "one local resource entry required")
        require(
            "__au_runtime_bytes_borrow_span" in text and "__au_runtime_bytes_at" in text,
            "real validation and backend-neutral copied read imports required",
        )
        linked = directory / "linked.s"
        linked.write_text(text + BRIDGE.replace("@ENTRY@", entries[0]))
        receipt["generated_sha256"] = digest(assembly)
        if not args.compile_only:
            flags = [
                "-std=c++23",
                "-O1",
                "-g",
                "-Wall",
                "-Wextra",
                "-Wpedantic",
                "-Werror",
                "-DNDEBUG",
                "-fno-exceptions",
                "-fno-rtti",
                "-no-pie",
            ]
            if args.sanitize:
                flags += ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"]
            executable = directory / "native"
            run(
                "link",
                [
                    *shlex.split(os.environ.get("CXX", "g++")),
                    *flags,
                    ROOT / "tests/compiler/owned_spans_kernel_host.cpp",
                    ROOT / "kernel/owned-bytes.cpp",
                    linked,
                    "-o",
                    executable,
                ],
            )
            receipt["native_sha256"] = digest(executable)
            env = os.environ.copy()
            env.update(
                ASAN_OPTIONS="detect_leaks=0:halt_on_error=1:abort_on_error=1",
                UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1",
            )
            for mode in range(3):
                result = run(f"mode-{mode}", [executable, mode], 82 if mode == 2 else 0, env)
                require(not result.stderr, f"mode {mode}: unexpected stderr")
                if mode == 2:
                    require(
                        result.stdout
                        == (
                            b"PASS generated kernel owned spans: failed borrow, exact fault 2, "
                            b"unchanged metrics/pages/leases\n"
                        ),
                        "failed borrow did not reach exact read-only fault endpoint",
                    )
                else:
                    require(
                        re.fullmatch(
                            (
                                rf"PASS generated kernel owned spans: mode={mode} checks=[1-9][0-9]* "
                                r"exact metrics/pages/leases\n"
                            ),
                            result.stdout.decode(),
                        )
                        is not None,
                        "wrong native success observation",
                    )
                print(result.stdout.decode(), end="", flush=True)
        require(all(digest(Path(path)) == expected for path, expected in inputs.items()), "source/compiler changed")
        receipt.update(status="passed", inputs_stable=True, native_cases=0 if args.compile_only else 3)
    except BaseException as error:
        receipt.update(status="failed", error=str(error))
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
