#!/usr/bin/env python3
"""Bounded independent disposal-policy, decoder and real-dispatcher gates.

The literal expected relation is not derived from the production implementation.
This focused run is not full native or kernel qualification. Hosted sanitizers do
not instrument generated Aurora code.
"""

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
# Independent literal phase -> mailbox-state relation, with no production enum,
# decoder, branch, invariant table or predicted native result in the oracle.
TABLE = (
    (0x0102, 0x0302, 0x0302, 0x0402, 0x0402, 0x0202),
    (1, 1, 1, 1, 1, 1),
    (1, 1, 1, 1, 1, 1),
    (1, 1, 1, 1, 1, 1),
)
WORDS = (1, 0x0102, 0x0202, 0x0302, 0x0402)
EDGES = (
    0,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    15,
    127,
    128,
    255,
    256,
    65535,
    65536,
    (1 << 32) - 1,
    1 << 32,
    (1 << 63) - 1,
    1 << 63,
    MAX,
)


def need(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def contexts():
    return itertools.product(range(4), range(6))


def oracle(phase, state):
    return TABLE[phase][state] if phase < 4 and state < 6 else 0


def decoder_oracle(word, phase, state):
    expected = oracle(phase, state)
    if expected == 0:
        return (0, 0)
    if word == 1:
        return (1, 0)
    if expected != 1 and word == expected:
        return (2, expected >> 8)
    return (0, 0)


def policy_vectors():
    yield from contexts()
    for values in contexts():
        for field in range(2):
            for value in EDGES:
                changed = list(values)
                changed[field] = value
                yield tuple(changed)
            for bit in range(64):
                changed = list(values)
                changed[field] ^= 1 << bit
                yield tuple(changed)
    yield from itertools.product(EDGES, repeat=2)
    rng = random.Random(202610081)
    for _ in range(8192):
        yield (rng.getrandbits(64), rng.getrandbits(64))


def decoder_vectors():
    # All compact action/effect combinations in every finite input context.
    for values in contexts():
        for action, effect in itertools.product(range(4), range(8)):
            yield (action | (effect << 8), *values)
        for word in WORDS:
            for bit in range(64):
                yield (word ^ (1 << bit), *values)
            # Every possible byte in each returned field, preserving its peer.
            for byte in range(256):
                yield ((word & ~255) | byte, *values)
                yield ((word & 255) | (byte << 8), *values)
            # Nonzero unused upper fields can never be silently truncated.
            for shift in (16, 24, 32, 48, 56):
                for byte in (1, 127, 128, 255):
                    yield (word | (byte << shift), *values)
        for word in EDGES:
            yield (word, *values)
    # Original full-width context must be valid even for an ordinary refusal or
    # otherwise plausible accepted effect. High bits are never an enum cast.
    for values in contexts():
        for field, limit in enumerate((3, 5)):
            for value in EDGES:
                if value <= limit:
                    continue
                changed = list(values)
                changed[field] = value
                for word in (0, *WORDS, 1 << 63, MAX):
                    yield (word, *changed)
    rng = random.Random(202610082)
    valid = tuple(contexts())
    for iteration in range(8192):
        values = valid[iteration % len(valid)] if iteration % 2 else (rng.getrandbits(64), rng.getrandbits(64))
        yield (rng.getrandbits(64), *values)


def environment(out):
    """Keep child-process temporary files inside the output directory; fatal sanitizers."""
    temporary = out / "tmp"
    temporary.mkdir(exist_ok=True)
    return dict(
        os.environ,
        ASAN_OPTIONS="detect_leaks=0:halt_on_error=1:abort_on_error=1",
        UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1",
        TMPDIR=str(temporary),
        TMP=str(temporary),
        TEMP=str(temporary),
    )


def run(command, out, label, timeout=120, expect=0):
    try:
        result = subprocess.run(command, cwd=ROOT, timeout=timeout, capture_output=True, env=environment(out))
    except subprocess.TimeoutExpired as error:
        (out / (label + ".stdout")).write_bytes(error.stdout or b"")
        (out / (label + ".stderr")).write_bytes(error.stderr or b"")
        raise
    (out / (label + ".stdout")).write_bytes(result.stdout)
    (out / (label + ".stderr")).write_bytes(result.stderr)
    need(result.returncode == expect, label + " failed; original evidence retained")
    return result


def vector_gate(binary, out, label, vectors, model, decode=False):
    inputs, expected, observed = (
        out / (label + suffix) for suffix in (".inputs.bin", ".expected.bin", ".observed.bin")
    )
    count = 0
    with inputs.open("wb") as source, expected.open("wb") as want:
        for values in vectors:
            source.write(struct.pack("<" + "Q" * len(values), *values))
            result = model(*values)
            want.write(struct.pack("<QQ", *result) if decode else struct.pack("<Q", result))
            count += 1
    command = [str(binary)] + (["decode"] if decode else [])
    with inputs.open("rb") as source, observed.open("wb") as actual, (out / (label + ".stderr")).open("wb") as errors:
        result = subprocess.run(
            command, stdin=source, stdout=actual, stderr=errors, cwd=ROOT, timeout=120, env=environment(out)
        )
    need(result.returncode == 0, label + " execution failed")
    need(observed.read_bytes() == expected.read_bytes(), label + " differs from independent literal oracle")
    return count


def rejection_gate(compiler, out):
    decision = "const kernel::DisposalDecision d = kernel::client_disposal(0u64, 1u64); "
    bodies = {
        "private_action": (
            "auto answer() -> kernel::DisposalAction { " + decision + "return d.outcome; }",
            "private class field",
        ),
        "private_effect": (
            "auto answer() -> kernel::DisposalEffect { " + decision + "return d.treatment; }",
            "private class field",
        ),
        "signed_phase": (
            "auto answer() -> kernel::DisposalAction { const kernel::DisposalDecision d = "
            "kernel::client_disposal(0, 1u64); return d.action(); }",
            "expected u64, got i64",
        ),
        "signed_state": (
            "auto answer() -> kernel::DisposalAction { const kernel::DisposalDecision d = "
            "kernel::client_disposal(0u64, 1); return d.action(); }",
            "expected u64, got i64",
        ),
        "boolean_phase": (
            "auto answer() -> kernel::DisposalAction { const kernel::DisposalDecision d = "
            "kernel::client_disposal(false, 1u64); return d.action(); }",
            "expected u64, got bool",
        ),
        "boolean_state": (
            "auto answer() -> kernel::DisposalAction { const kernel::DisposalDecision d = "
            "kernel::client_disposal(0u64, true); return d.action(); }",
            "expected u64, got bool",
        ),
        "numeric_action": (
            "auto answer() -> bool { " + decision + "return d.action() == 2u64; }",
            "expected kernel::DisposalAction, got u64",
        ),
        "numeric_effect": (
            "auto answer() -> bool { " + decision + "return d.effect() == 3u64; }",
            "expected kernel::DisposalEffect, got u64",
        ),
        "mixed_enums": (
            "auto answer() -> bool { " + decision + "return d.action() == d.effect(); }",
            "expected kernel::DisposalAction, got kernel::DisposalEffect",
        ),
        "constructor_numeric_action": (
            "auto answer() -> kernel::DisposalAction { const kernel::DisposalDecision d = "
            "kernel::DisposalDecision(2u64, kernel::DisposalEffect::empty); return d.action(); }",
            "expected kernel::DisposalAction, got u64",
        ),
        "constructor_numeric_effect": (
            "auto answer() -> kernel::DisposalAction { const kernel::DisposalDecision d = "
            "kernel::DisposalDecision(kernel::DisposalAction::accepted, 1u64); return d.action(); }",
            "expected kernel::DisposalEffect, got u64",
        ),
        "constructor_swapped_enums": (
            "auto answer() -> kernel::DisposalAction { const kernel::DisposalDecision d = "
            "kernel::DisposalDecision(kernel::DisposalEffect::empty, kernel::DisposalAction::accepted); "
            "return d.action(); }",
            "expected kernel::DisposalAction, got kernel::DisposalEffect",
        ),
        "parameter_private_action": (
            "auto change(kernel::DisposalDecision d) -> kernel::DisposalAction { "
            "d.outcome = kernel::DisposalAction::refused; return d.action(); }",
            "field assignment requires a mutable class local",
        ),
        "parameter_private_effect": (
            "auto change(kernel::DisposalDecision d) -> kernel::DisposalEffect { "
            "d.treatment = kernel::DisposalEffect::none; return d.effect(); }",
            "field assignment requires a mutable class local",
        ),
        "const_private_action": (
            "auto answer() -> kernel::DisposalAction { "
            + decision
            + "d.outcome = kernel::DisposalAction::refused; return d.action(); }",
            "field assignment requires a mutable class local",
        ),
        "const_private_effect": (
            "auto answer() -> kernel::DisposalEffect { "
            + decision
            + "d.treatment = kernel::DisposalEffect::none; return d.effect(); }",
            "field assignment requires a mutable class local",
        ),
        "readonly_decision": (
            "auto change(kernel::DisposalDecision d) -> kernel::DisposalEffect { "
            "const kernel::DisposalDecision other = kernel::client_disposal(0u64, 5u64); "
            "d = other; return d.effect(); }",
            "assignment requires a mutable scalar local",
        ),
        "nominal_decision": (
            "class OtherDecision { u64 value; public: OtherDecision(u64 v) : value(v) {} }; "
            "auto inspect(kernel::DisposalDecision d) -> kernel::DisposalEffect { return d.effect(); } "
            "auto answer() -> kernel::DisposalEffect { const OtherDecision other = OtherDecision(0u64); "
            "return inspect(other); }",
            "expected kernel::DisposalDecision",
        ),
    }
    count = 0
    for name, (body, diagnostic) in bodies.items():
        source = out / (name + ".au")
        source.write_text("module probe;\nimport kernel.client_disposal;\n" + body + "\n")
        for existing in (False, True):
            label = name + ("-existing" if existing else "-absent")
            output = out / (label + ".s")
            sentinel = b"prior complete artifact\n"
            if existing:
                output.write_bytes(sentinel)
            command = [str(compiler), "--module-root", str(ROOT / "kernel/policies"), str(source), "-o", str(output)]
            result = run(command, out, label, timeout=30, expect=1)
            count += 1
            need(diagnostic.encode() in result.stderr, label + " wrong rejection")
            need(output.read_bytes() == sentinel if existing else not output.exists(), label + " changed prior output")
    return count


def symbol_map(data):
    return {fields[0]: tuple(fields[1:]) for line in data.decode().splitlines() if (fields := line.split())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", default=str(ROOT / "build/aurorac"))
    parser.add_argument("--output")
    parser.add_argument("--sanitize", action="store_true", default=os.environ.get("SANITIZE") == "1")
    args = parser.parse_args()
    compiler = Path(args.compiler).resolve(strict=True)
    out = (
        Path(args.output).absolute()
        if args.output
        else ROOT / "build/kernel-client-disposal-native" / str(time.time_ns())
    )
    need(not any(path.is_symlink() for path in (out, *out.parents)), "Output symlink denied")
    need(".." not in out.parts, "Output path traversal denied")
    need(not out.exists(), "Use a fresh output directory; never overwrite failed evidence")
    out.mkdir(parents=True)
    finite = [oracle(*values) for values in contexts()]
    need(
        len(finite) == 24 and finite.count(1) == 18 and sum(word > 1 for word in finite) == 6,
        "Literal table cardinality",
    )
    assembly, obj, binary = out / "language.s", out / "language.o", out / "observe"
    flags = [
        "g++",
        "-std=c++23",
        "-O1" if args.sanitize else "-O2",
        "-Wall",
        "-Wextra",
        "-Wpedantic",
        "-Werror",
        "-no-pie",
    ]
    if args.sanitize:
        flags += ["-g", "-fno-omit-frame-pointer", "-fsanitize=address,undefined", "-fno-sanitize-recover=all"]
    run(
        [str(compiler), "--module-root", "kernel/policies", "examples/kernel.au", "-o", str(assembly)],
        out,
        "compile",
    )
    run(["g++", "-c", str(assembly), "-o", str(obj)], out, "assemble")
    run(flags + ["tests/kernel-client-disposal-native.cpp", str(obj), "-o", str(binary)], out, "observer-link")
    counts = dict(
        finite_contexts=24,
        finite_accepted=6,
        finite_refused=18,
        decoder_compact=768,
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
            "tests/kernel-programs/client-disposal-copy.au",
            "-o",
            str(copy_assembly),
        ],
        out,
        "copy-compile",
    )
    run(
        flags + ["tests/kernel-client-disposal-copy.cpp", str(copy_assembly), "-o", str(copy_binary)],
        out,
        "copy-link",
    )
    run([str(copy_binary)], out, "copy-observe")
    counts["copy_repetitions"] = 4096
    # Rename exactly one producer, preserving real IPC and round-robin behavior.
    substituted, adapter = out / "adapter-language.o", out / "adapter"
    old, new = "aurora_kernel_client_disposal", "aurora_kernel_client_disposal_real"
    before = symbol_map(run(["nm", "--defined-only", "--format=posix", str(obj)], out, "root-symbols").stdout)
    need(
        old in before
        and new not in before
        and "aurora_kernel_ipc_transition" in before
        and "aurora_kernel_round_robin_next" in before,
        "Expected genuine policy producers missing",
    )
    run(["objcopy", "--redefine-sym", old + "=" + new, str(obj), str(substituted)], out, "rename-only-disposal")
    after = symbol_map(run(["nm", "--defined-only", "--format=posix", str(substituted)], out, "adapter-symbols").stdout)
    renamed = dict(before)
    renamed[new] = renamed.pop(old)
    need(after == renamed, "Only disposal symbol may be renamed")
    run(
        flags + ["tests/kernel-client-disposal-adapter.cpp", str(substituted), "-o", str(adapter)],
        out,
        "adapter-link",
    )
    run([str(adapter)], out, "adapter-observe")
    regression = out / "original-regression"
    # Hosted -O1 recipe for this regression.
    # The first focused attempt used -O2 and failed GCC 14 -Werror=array-bounds
    # in unchanged Fixture::refresh; retain build/disposal-native-001 and the
    # parent evidence/disposal-native-001 records. New tests retain their normal
    # -O2 (or sanitizer -O1), and no warning or original assertion is weakened.
    regression_flags = ["-O1" if flag == "-O2" else flag for flag in flags]
    run(
        regression_flags + ["tests/kernel-client-disposal.cpp", str(obj), "-o", str(regression)],
        out,
        "regression-link",
    )
    run([str(regression)], out, "original-regression")
    for label, executable in (("observer", binary), ("adapter", adapter), ("copy", copy_binary)):
        run(["objdump", "-drwC", str(executable)], out, label + "-disassembly")
        run(["readelf", "-sW", str(executable)], out, label + "-elf-symbols")
    print(
        "kernel client disposal native: passed "
        + ", ".join(f"{k}={v}" for k, v in counts.items())
        + f" sanitize={args.sanitize} (output {out})"
    )


if __name__ == "__main__":
    main()
