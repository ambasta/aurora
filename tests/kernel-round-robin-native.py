#!/usr/bin/env python3
"""Full-width native selection oracle, real decoder and copy/rejection gates."""

from pathlib import Path
import argparse
import hashlib
import itertools
import json
import random
import shutil
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "scripts"))
from owned_outputs import allocated_bytes, free_bytes, temporary_environment, write_checked_receipt
from compiler_contract import add_identity_arguments, resolve_identity, validate_identity_selection

MAX = (1 << 64) - 1
# Literal truth table, not a translation of the source decision algorithm.
TABLE = ((0x1, 0x10002, 0x102, 0x10002), (0x10001, 0x10002, 0x102, 0x102))


def need(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def candidate_cap(mib):
    need(
        type(mib) is int and 128 <= mib <= 1024,
        "candidate cap must be an integer between 128 and 1024 MiB; increases require explicit aggregate admission",
    )
    return mib << 20


def cap_self_test():
    for mib in (128, 512, 513, 1023, 1024):
        need(candidate_cap(mib) == mib << 20, "candidate cap boundary conversion")
    for mib in (-1, 0, 127, 1025, 1 << 30, True, 512.0, "1024", None):
        try:
            candidate_cap(mib)
        except RuntimeError:
            continue
        raise RuntimeError("invalid candidate cap accepted")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def allocated(output):
    return allocated_bytes(output)


def guard(output, cap, reserve=0):
    cap_bytes = candidate_cap(cap)
    need(allocated(output) + reserve < cap_bytes, "Owned-output allocation cap reached, including reserve")
    need(free_bytes(output) - reserve >= 1024**3, "One GiB free-space floor reached, including reserve")


def oracle(cursor, mask):
    return TABLE[cursor][mask] if cursor < 2 and mask < 4 else 0


def decoder_oracle(word, cursor, mask):
    if cursor >= 2 or mask >= 4:
        return 0
    allowed = (({0x1}, {0x10002}, {0x102}, {0x10002, 0x102}), ({0x10001}, {0x10002}, {0x102}, {0x10002, 0x102}))
    return word if word in allowed[cursor][mask] else 0


def run(command, folder, name, cap):
    guard(folder, cap, 24 << 20)
    started = time.time()
    result = subprocess.run(command, cwd=ROOT, timeout=120, capture_output=True, env=temporary_environment(folder))
    (folder / (name + ".stdout")).write_bytes(result.stdout)
    (folder / (name + ".stderr")).write_bytes(result.stderr)
    (folder / (name + ".json")).write_text(
        json.dumps(
            dict(command=list(map(str, command)), returncode=result.returncode, elapsed_seconds=time.time() - started),
            indent=2,
        )
        + "\n"
    )
    need(result.returncode == 0, name + " failed; original outputs retained")
    guard(folder, cap)
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


def vector_gate(binary, out, label, vectors, model, cap, decode=False):
    inputs, expected, observed = (
        out / (label + suffix) for suffix in (".inputs.bin", ".expected.bin", ".observed.bin")
    )
    count = 0
    with inputs.open("wb") as source, expected.open("wb") as want:
        for values in vectors:
            source.write(struct.pack("<" + "Q" * len(values), *values))
            want.write(struct.pack("<Q", model(*values)))
            count += 1
            if count % 32768 == 0:
                guard(out, cap)
    command = [str(binary)] + (["decode"] if decode else [])
    started = time.time()
    with inputs.open("rb") as source, observed.open("wb") as actual, (out / (label + ".stderr")).open("wb") as errors:
        result = subprocess.run(
            command, stdin=source, stdout=actual, stderr=errors, timeout=120, cwd=ROOT, env=temporary_environment(out)
        )
    receipt = dict(
        command=command,
        returncode=result.returncode,
        cases=count,
        elapsed_seconds=time.time() - started,
        files={p.name: dict(bytes=p.stat().st_size, sha256=sha(p)) for p in (inputs, expected, observed)},
    )
    (out / (label + ".json")).write_text(json.dumps(receipt, indent=2) + "\n")
    need(result.returncode == 0, label + " failed")
    need(observed.read_bytes() == expected.read_bytes(), label + " native observations differ")
    guard(out, cap)
    return count


def rejection_gate(compiler, out, cap):
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
    receipts = []
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
            guard(out, cap, 24 << 20)
            result = subprocess.run(command, cwd=ROOT, timeout=30, capture_output=True, env=temporary_environment(out))
            (out / (label + ".stdout")).write_bytes(result.stdout)
            (out / (label + ".stderr")).write_bytes(result.stderr)
            receipts.append(
                dict(
                    command=command,
                    returncode=result.returncode,
                    expected_diagnostic=diagnostic,
                    source_sha256=sha(source),
                    output_exists=output.exists(),
                )
            )
            (out / "rejections.json").write_text(json.dumps(receipts, indent=2) + "\n")
            guard(out, cap)
            need(result.returncode == 1 and diagnostic.encode() in result.stderr, label + " wrong rejection")
            need(output.read_bytes() == sentinel if existing else not output.exists(), label + " output changed")
    return len(receipts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", default=str(ROOT / "build/aurorac"))
    add_identity_arguments(parser)
    parser.add_argument("--output")
    parser.add_argument(
        "--candidate-cap-mib",
        type=int,
        default=128,
        help="per-invocation owned-output cap 128..1024 MiB; increases require explicit aggregate admission",
    )
    parser.add_argument(
        "--check-cap-only",
        action="store_true",
        help="configuration-only cap checks; no compiler, native test or acceptance receipt",
    )
    args = parser.parse_args()
    validate_identity_selection(args, preflight=args.check_cap_only)
    cap_bytes = candidate_cap(args.candidate_cap_mib)
    if args.check_cap_only:
        cap_self_test()
        print(
            json.dumps(
                dict(
                    status="configuration-only",
                    native_executed=False,
                    candidate_cap_mib=args.candidate_cap_mib,
                    cap_bytes=cap_bytes,
                    focused_default_mib=128,
                    maximum_cap_mib=1024,
                ),
                sort_keys=True,
            )
        )
        return
    cap_self_test()
    compiler = Path(args.compiler).resolve(strict=True)
    identity = resolve_identity(args, compiler, ROOT)
    out = (
        Path(args.output).absolute() if args.output else ROOT / "build/kernel-round-robin-native" / str(time.time_ns())
    )
    need(not any(path.is_symlink() for path in (out, *out.parents)), "Output symlink denied")
    need(".." not in out.parts, "Output path traversal denied")
    need(not out.exists(), "Use a fresh output directory; never overwrite failed evidence")
    guard(out, args.candidate_cap_mib, 65536)
    out.mkdir(parents=True)
    members = (
        "scripts/owned_outputs.py",
        "kernel/policies/kernel/round_robin.au",
        "examples/kernel.au",
        "kernel/round-robin-transport.hpp",
        "kernel/dispatch-policy.hpp",
        "tests/kernel-round-robin-native.cpp",
        "tests/kernel-round-robin-native.py",
        "tests/kernel-programs/round-robin-copy.au",
        "tests/kernel-round-robin-copy.cpp",
    )
    pins = {name: sha(ROOT / name) for name in members}
    assembly, binary = out / "language.s", out / "observe"
    run(
        [str(compiler), "--module-root", "kernel/policies", "examples/kernel.au", "-o", str(assembly)],
        out,
        "compile",
        args.candidate_cap_mib,
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
        args.candidate_cap_mib,
    )
    counts = dict(
        policy=vector_gate(binary, out, "policy", policy_vectors(), oracle, args.candidate_cap_mib),
        decoder=vector_gate(binary, out, "decoder", decoder_vectors(), decoder_oracle, args.candidate_cap_mib, True),
    )
    counts["rejections"] = rejection_gate(compiler, out, args.candidate_cap_mib)
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
        args.candidate_cap_mib,
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
        args.candidate_cap_mib,
    )
    run([str(copy_binary)], out, "copy-observe", args.candidate_cap_mib)
    counts["copy_repetitions"] = 4096
    run(["objdump", "-drwC", str(binary)], out, "disassembly", args.candidate_cap_mib)
    run(["readelf", "-sW", str(binary)], out, "symbols", args.candidate_cap_mib)
    need(sha(compiler) == identity.sha256, "Compiler changed during test")
    need(pins == {name: sha(ROOT / name) for name in pins}, "Source changed during test")
    guard(out, args.candidate_cap_mib)
    identity.verify()
    summary = dict(
        status="passed",
        compiler_identity=identity.record(),
        compiler_sha256=sha(compiler),
        source_pins=pins,
        cases=counts,
        candidate_cap_mib=args.candidate_cap_mib,
        cap_bytes=cap_bytes,
        owned_output_allocated_bytes=allocated(out),
        free_bytes=free_bytes(out),
        output_root=str(out),
        accounting_scope="invocation outputs including tmp",
        limits="Hosted observations only; no QEMU, source-safety proof, whole-kernel stack or acceptance claim.",
    )
    write_checked_receipt(out / "summary.json", summary, lambda: guard(out, args.candidate_cap_mib))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
