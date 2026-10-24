#!/usr/bin/env python3
"""Full-width native selection oracle, real decoder and copy/rejection gates."""

from pathlib import Path
import argparse
import itertools
import os
import random
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True

MAX = (1 << 64) - 1
# Literal truth table, not a translation of the source decision algorithm.
TABLE = ((0x1, 0x10002, 0x102, 0x10002), (0x10001, 0x10002, 0x102, 0x102))


def need(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def scratch_env(output):
    """Keep child-process temporary files inside the output directory."""
    temporary = output / "tmp"
    temporary.mkdir(exist_ok=True)
    return dict(os.environ, TMPDIR=str(temporary), TMP=str(temporary), TEMP=str(temporary))


def oracle(cursor, mask):
    return TABLE[cursor][mask] if cursor < 2 and mask < 4 else 0


def decoder_oracle(word, cursor, mask):
    if cursor >= 2 or mask >= 4:
        return 0
    allowed = (({0x1}, {0x10002}, {0x102}, {0x10002, 0x102}), ({0x10001}, {0x10002}, {0x102}, {0x10002, 0x102}))
    return word if word in allowed[cursor][mask] else 0


def run(command, folder, name):
    result = subprocess.run(command, cwd=ROOT, timeout=120, capture_output=True, env=scratch_env(folder))
    (folder / (name + ".stdout")).write_bytes(result.stdout)
    (folder / (name + ".stderr")).write_bytes(result.stderr)
    need(result.returncode == 0, name + " failed; original outputs retained")
    return result


def policy_vectors():
    yield from itertools.product(range(2), range(4))
    values = (0, 1, 2, 3, 4, 7, 15, 127, 128, 255, 256, (1 << 32) - 1, 1 << 32, (1 << 63) - 1, 1 << 63, MAX)
    yield from itertools.product(values, repeat=2)
    for bit in range(64):
        for cursor, mask in itertools.product(range(2), range(4)):
            yield cursor ^ (1 << bit), mask
            yield cursor, mask ^ (1 << bit)
    randomizer = random.Random(20261005)
    for _ in range(16384):
        yield randomizer.getrandbits(64), randomizer.getrandbits(64)


def decoder_vectors():
    # Exhaust every word below the highest allocated transport bit for all
    # contexts, then mutate every bit of all distinct valid outputs.
    for cursor, mask in itertools.product(range(2), range(4)):
        for word in range(1 << 17):
            yield word, cursor, mask
        for word in (1, 0x10001, 0x10002, 0x102):
            for bit in range(64):
                yield word ^ (1 << bit), cursor, mask
    for cursor, mask in itertools.product((0, 1, 2, 3, 4, 1 << 63, MAX), repeat=2):
        for word in (0, 1, 2, 0x10001, 0x10002, 0x102, 1 << 63, MAX):
            yield word, cursor, mask


def vector_gate(binary, out, label, vectors, model, decode=False):
    inputs, expected, observed = (
        out / (label + suffix) for suffix in (".inputs.bin", ".expected.bin", ".observed.bin")
    )
    count = 0
    with inputs.open("wb") as source, expected.open("wb") as want:
        for values in vectors:
            source.write(struct.pack("<" + "Q" * len(values), *values))
            want.write(struct.pack("<Q", model(*values)))
            count += 1
    command = [str(binary)] + (["decode"] if decode else [])
    with inputs.open("rb") as source, observed.open("wb") as actual, (out / (label + ".stderr")).open("wb") as errors:
        result = subprocess.run(
            command, stdin=source, stdout=actual, stderr=errors, timeout=120, cwd=ROOT, env=scratch_env(out)
        )
    need(result.returncode == 0, label + " failed")
    need(observed.read_bytes() == expected.read_bytes(), label + " native observations differ")
    return count


def rejection_gate(compiler, out):
    bodies = {
        "private_field": (
            "auto answer() -> u64 { const kernel::SelectionDecision d = "
            "kernel::round_robin_next(0u64, 3u64); return d.selected_slot; }",
            "private class field is inaccessible",
        ),
        "signed_cursor": (
            "auto answer() -> u64 { const kernel::SelectionDecision d = "
            "kernel::round_robin_next(0, 3u64); return d.next(); }",
            "expected u64, got i64",
        ),
        "signed_mask": (
            "auto answer() -> u64 { const kernel::SelectionDecision d = "
            "kernel::round_robin_next(0u64, 3); return d.next(); }",
            "expected u64, got i64",
        ),
        "numeric_action": (
            "auto answer() -> bool { const kernel::SelectionDecision d = "
            "kernel::round_robin_next(0u64, 3u64); return d.action() == 2u64; }",
            "expected kernel::SelectionAction, got u64",
        ),
        "copied_parameter": (
            "auto change(kernel::SelectionDecision d) -> u64 { "
            "d = kernel::SelectionDecision(kernel::SelectionAction::idle, 0u64, 0u64); return d.next(); }",
            "assignment requires a mutable scalar local",
        ),
    }
    count = 0
    for name, (body, diagnostic) in bodies.items():
        source = out / (name + ".au")
        source.write_text("module probe;\nimport kernel.round_robin;\n" + body + "\n")
        for existing in (False, True):
            label = name + ("-existing" if existing else "-absent")
            output = out / (label + ".s")
            sentinel = b"prior complete artifact\n"
            if existing:
                output.write_bytes(sentinel)
            command = [str(compiler), "--module-root", str(ROOT / "kernel/policies"), str(source), "-o", str(output)]
            result = subprocess.run(command, cwd=ROOT, timeout=30, capture_output=True, env=scratch_env(out))
            (out / (label + ".stdout")).write_bytes(result.stdout)
            (out / (label + ".stderr")).write_bytes(result.stderr)
            count += 1
            need(result.returncode == 1 and diagnostic.encode() in result.stderr, label + " wrong rejection")
            need(output.read_bytes() == sentinel if existing else not output.exists(), label + " output changed")
    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", default=str(ROOT / "build/aurorac"))
    parser.add_argument("--output")
    args = parser.parse_args()
    compiler = Path(args.compiler).resolve(strict=True)
    out = (
        Path(args.output).absolute() if args.output else ROOT / "build/kernel-round-robin-native" / str(time.time_ns())
    )
    need(not any(path.is_symlink() for path in (out, *out.parents)), "Output symlink denied")
    need(".." not in out.parts, "Output path traversal denied")
    need(not out.exists(), "Use a fresh output directory; never overwrite failed evidence")
    out.mkdir(parents=True)
    assembly, binary = out / "language.s", out / "observe"
    run(
        [str(compiler), "--module-root", "kernel/policies", "examples/kernel.au", "-o", str(assembly)],
        out,
        "compile",
    )
    run(
        [
            "g++",
            "-std=c++23",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Wpedantic",
            "-Werror",
            "-no-pie",
            "tests/kernel-round-robin-native.cpp",
            str(assembly),
            "-o",
            str(binary),
        ],
        out,
        "link",
    )
    counts = dict(
        policy=vector_gate(binary, out, "policy", policy_vectors(), oracle),
        decoder=vector_gate(binary, out, "decoder", decoder_vectors(), decoder_oracle, True),
    )
    counts["rejections"] = rejection_gate(compiler, out)
    copy_assembly, copy_binary = out / "copy.s", out / "copy"
    run(
        [
            str(compiler),
            "--module-root",
            "kernel/policies",
            "tests/kernel-programs/round-robin-copy.au",
            "-o",
            str(copy_assembly),
        ],
        out,
        "copy-compile",
    )
    run(
        [
            "g++",
            "-std=c++23",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Wpedantic",
            "-Werror",
            "-no-pie",
            "tests/kernel-round-robin-copy.cpp",
            str(copy_assembly),
            "-o",
            str(copy_binary),
        ],
        out,
        "copy-link",
    )
    run([str(copy_binary)], out, "copy-observe")
    counts["copy_repetitions"] = 4096
    run(["objdump", "-drwC", str(binary)], out, "disassembly")
    run(["readelf", "-sW", str(binary)], out, "symbols")
    print("kernel round-robin native: passed " + ", ".join(f"{k}={v}" for k, v in counts.items()) + f" (output {out})")


if __name__ == "__main__":
    main()
