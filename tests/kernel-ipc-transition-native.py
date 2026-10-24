#!/usr/bin/env python3
"""Bounded genuine IPC producer, classified decoder, copy and hostile adapter gates.

Fatal ASan/UBSan disables LeakSanitizer for the verified executor ptrace restriction.
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
# Independent literal relation: operation -> phase -> state*2+scrubbed.
# No production branch, enum, invariant table or decoder is used as an oracle.
TABLE = (
    (
        (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
        (0x010102, 0x010102, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
        (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
        (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
    ),
    (
        (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
        (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
        (1, 1, 0x020202, 0x020202, 1, 1, 1, 1, 1, 1, 1, 1),
        (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
    ),
    (
        (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
        (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
        (1, 1, 1, 1, 0x030302, 0x030302, 1, 1, 1, 1, 1, 1),
        (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
    ),
    (
        (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
        (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
        (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
        (1, 1, 1, 1, 1, 1, 0x040502, 0x040502, 0x050502, 0x050502, 1, 1),
    ),
    (
        (1, 1, 0x060402, 0x060402, 0x060402, 0x060402, 1, 1, 1, 1, 1, 1),
        (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
        (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
        (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
    ),
    (
        (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0x070002),
        (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
        (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
        (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
    ),
)
VALID_WORDS = (1, 0x010102, 0x020202, 0x030302, 0x040502, 0x050502, 0x060402, 0x070002)
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


def scratch_env(output):
    """Keep child-process temporary files inside the output directory; fatal sanitizers."""
    temporary = output / "tmp"
    temporary.mkdir(exist_ok=True)
    return dict(
        os.environ,
        ASAN_OPTIONS="detect_leaks=0:halt_on_error=1:abort_on_error=1",
        UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1",
        TMPDIR=str(temporary),
        TMP=str(temporary),
        TEMP=str(temporary),
    )


def contexts():
    return itertools.product(range(6), range(4), range(6), range(2))


def oracle(operation, phase, state, scrubbed):
    if operation > 5 or phase > 3 or state > 5 or scrubbed > 1:
        return 0
    return TABLE[operation][phase][state * 2 + scrubbed]


def decoder_oracle(word, operation, phase, state, scrubbed):
    genuine = oracle(operation, phase, state, scrubbed)
    if genuine == 0:
        return (0, 0, 0)
    if word == 1:
        return (1, 0, 0)
    if genuine != 1 and word == genuine:
        return (2, (genuine >> 8) & 255, (genuine >> 16) & 255)
    return (0, 0, 0)


def policy_vectors():
    yield from contexts()
    # Every raw field independently, then simultaneous invalid fields.
    for values in contexts():
        for field in range(4):
            for value in EDGES:
                changed = list(values)
                changed[field] = value
                yield tuple(changed)
            for bit in range(64):
                changed = list(values)
                changed[field] ^= 1 << bit
                yield tuple(changed)
    for value in EDGES:
        yield (value,) * 4
    rng = random.Random(202610051)
    for _ in range(16384):
        yield tuple(rng.getrandbits(64) for _ in range(4))


def decoder_vectors():
    # Exactly 288 * 4 * 8 * 8 = 73,728 compact classified observations.
    for values in contexts():
        for action, state, effect in itertools.product(range(4), range(8), range(8)):
            yield (action | (state << 8) | (effect << 16), *values)
    for values in contexts():
        for word in VALID_WORDS:
            for bit in range(64):
                yield (word ^ (1 << bit), *values)
            # Full byte boundaries, field overflow and upper reserved bits.
            for shift in (0, 8, 16, 24, 32, 56):
                for edge in (0, 1, 2, 3, 7, 8, 127, 128, 254, 255, 256):
                    yield ((word | (edge << shift)) & MAX, *values)
        for word in EDGES:
            yield (word, *values)
    # Invalid ORIGINAL contexts must reject even refusal/plausible success.
    for field, limit in enumerate((5, 3, 5, 1)):
        for value in EDGES:
            if value <= limit:
                continue
            for base in (
                (0, 1, 0, 1),
                (1, 2, 1, 0),
                (2, 2, 2, 1),
                (3, 3, 3, 0),
                (3, 3, 4, 1),
                (4, 0, 1, 0),
                (4, 0, 2, 1),
                (5, 0, 5, 1),
            ):
                changed = list(base)
                changed[field] = value
                for word in (0, *VALID_WORDS, 1 << 63, MAX):
                    yield (word, *changed)
    rng = random.Random(202610052)
    valid = tuple(contexts())
    for iteration in range(16384):
        values = valid[iteration % len(valid)] if iteration % 2 else tuple(rng.getrandbits(64) for _ in range(4))
        yield (rng.getrandbits(64), *values)


def run(command, folder, name, timeout=120, expect=0):
    try:
        result = subprocess.run(command, cwd=ROOT, timeout=timeout, capture_output=True, env=scratch_env(folder))
    except subprocess.TimeoutExpired as error:
        (folder / (name + ".stdout")).write_bytes(error.stdout or b"")
        (folder / (name + ".stderr")).write_bytes(error.stderr or b"")
        raise
    (folder / (name + ".stdout")).write_bytes(result.stdout)
    (folder / (name + ".stderr")).write_bytes(result.stderr)
    need(result.returncode == expect, name + " failed; original outputs retained")
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
            want.write(struct.pack("<QQQ", *result) if decode else struct.pack("<Q", result))
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
    prefix = "const kernel::TransactionSnapshot s = kernel::TransactionSnapshot(1u64, 0u64, 1u64); "
    decision = prefix + "const kernel::TransactionDecision d = kernel::transaction_transition(0u64, s); "
    bodies = {
        "snapshot_private": ("auto answer() -> u64 { " + prefix + "return s.phase_value; }", "private class field"),
        "decision_private": (
            "auto answer() -> u64 { " + decision + "return d.following_state; }",
            "private class field",
        ),
        "signed_operation": (
            "auto answer() -> u64 { "
            + prefix
            + "const kernel::TransactionDecision d = kernel::transaction_transition(0, s); return d.next(); }",
            "expected u64, got i64",
        ),
        "signed_phase": (
            "auto answer() -> u64 { const kernel::TransactionSnapshot s = "
            "kernel::TransactionSnapshot(1, 0u64, 1u64); return s.phase(); }",
            "expected u64, got i64",
        ),
        "signed_state": (
            "auto answer() -> u64 { const kernel::TransactionSnapshot s = "
            "kernel::TransactionSnapshot(1u64, 0, 1u64); return s.state(); }",
            "expected u64, got i64",
        ),
        "bool_scrubbed": (
            "auto answer() -> u64 { const kernel::TransactionSnapshot s = "
            "kernel::TransactionSnapshot(1u64, 0u64, true); return s.scrubbed(); }",
            "expected u64, got bool",
        ),
        "numeric_action": (
            "auto answer() -> bool { " + decision + "return d.action() == 2u64; }",
            "expected kernel::TransactionAction, got u64",
        ),
        "numeric_effect": (
            "auto answer() -> bool { " + decision + "return d.effect() == 1u64; }",
            "expected kernel::TransactionEffect, got u64",
        ),
        "mixed_enums": (
            "auto answer() -> bool { " + decision + "return d.action() == d.effect(); }",
            "expected kernel::TransactionAction, got kernel::TransactionEffect",
        ),
        "snapshot_parameter_field": (
            "auto change(kernel::TransactionSnapshot s) -> u64 { s.phase_value = 0u64; return s.phase(); }",
            "field assignment requires a mutable class local",
        ),
        "decision_parameter_field": (
            "auto change(kernel::TransactionDecision d) -> u64 { d.following_state = 0u64; return d.next(); }",
            "field assignment requires a mutable class local",
        ),
        "snapshot_const_field": (
            "auto answer() -> u64 { " + prefix + "s.phase_value = 0u64; return s.phase(); }",
            "field assignment requires a mutable class local",
        ),
        "decision_const_field": (
            "auto answer() -> u64 { " + decision + "d.following_state = 0u64; return d.next(); }",
            "field assignment requires a mutable class local",
        ),
        "readonly_snapshot": (
            "auto change(kernel::TransactionSnapshot s) -> u64 { const kernel::TransactionSnapshot other = "
            "kernel::TransactionSnapshot(0u64, 0u64, 0u64); s = other; return s.phase(); }",
            "assignment requires a mutable scalar local",
        ),
        "readonly_decision": (
            "auto change(kernel::TransactionDecision d) -> u64 { const kernel::TransactionDecision other = "
            "kernel::TransactionDecision(kernel::TransactionAction::refused, 0u64, kernel::TransactionEffect::none); "
            "d = other; return d.next(); }",
            "assignment requires a mutable scalar local",
        ),
        "nominal_snapshot": (
            "auto answer() -> u64 { "
            + decision
            + "const kernel::TransactionDecision other = kernel::transaction_transition(0u64, d); "
            "return other.next(); }",
            "expected kernel::TransactionSnapshot",
        ),
    }
    count = 0
    for name, (body, diagnostic) in bodies.items():
        source = out / (name + ".au")
        source.write_text("module probe;\nimport kernel.ipc_transition;\n" + body + "\n")
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
            need(output.read_bytes() == sentinel if existing else not output.exists(), label + " output changed")
    return count


def symbol_map(data):
    return {fields[0]: tuple(fields[1:]) for line in data.decode().splitlines() if (fields := line.split())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", default=str(ROOT / "build/aurorac"))
    parser.add_argument("--output")
    parser.add_argument(
        "--sanitize",
        action="store_true",
        default=os.environ.get("SANITIZE") == "1",
        help="fatal hosted ASan/UBSan; generated Aurora assembly remains uninstrumented",
    )
    args = parser.parse_args()
    compiler = Path(args.compiler).resolve(strict=True)
    out = (
        Path(args.output).absolute()
        if args.output
        else ROOT / "build/kernel-ipc-transition-native" / str(time.time_ns())
    )
    need(not any(path.is_symlink() for path in (out, *out.parents)), "Output symlink denied")
    need(".." not in out.parts, "Output path traversal denied")
    need(not out.exists(), "Use a fresh output directory; never overwrite failed evidence")
    out.mkdir(parents=True)
    finite = [oracle(*values) for values in contexts()]
    need(
        len(finite) == 288 and finite.count(1) == 273 and sum(word > 1 for word in finite) == 15,
        "Literal relation cardinality changed",
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
    run(flags + ["tests/kernel-ipc-transition-native.cpp", str(obj), "-o", str(binary)], out, "link")
    counts = dict(
        finite_contexts=288,
        finite_accepted=15,
        finite_refused=273,
        decoder_compact=73728,
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
            "tests/kernel-programs/ipc-transition-copy.au",
            "-o",
            str(copy_assembly),
        ],
        out,
        "copy-compile",
    )
    run(
        flags + ["tests/kernel-ipc-transition-copy.cpp", str(copy_assembly), "-o", str(copy_binary)],
        out,
        "copy-link",
    )
    run([str(copy_binary)], out, "copy-observe")
    counts["copy_repetitions"] = 4096
    substituted, adapter = out / "adapter-language.o", out / "adapter"
    old, new = "aurora_kernel_ipc_transition", "aurora_kernel_ipc_transition_real"
    before = symbol_map(run(["nm", "--defined-only", "--format=posix", str(obj)], out, "root-symbols").stdout)
    need(
        old in before and new not in before and "aurora_kernel_round_robin_next" in before,
        "Expected genuine producer symbols missing",
    )
    run(["objcopy", "--redefine-sym", old + "=" + new, str(obj), str(substituted)], out, "rename-only-ipc")
    after = symbol_map(
        run(["nm", "--defined-only", "--format=posix", str(substituted)], out, "adapter-root-symbols").stdout
    )
    renamed = dict(before)
    renamed[new] = renamed.pop(old)
    need(after == renamed, "Only IPC producer may be renamed; round-robin and all other symbols must remain genuine")
    run(
        flags + ["tests/kernel-ipc-transition-adapter.cpp", str(substituted), "-o", str(adapter)],
        out,
        "adapter-link",
    )
    run([str(adapter)], out, "adapter-observe")
    for name, artifact in (("native", binary), ("adapter", adapter), ("copy", copy_binary)):
        run(["objdump", "-drwC", str(artifact)], out, name + "-disassembly")
        run(["readelf", "-sW", str(artifact)], out, name + "-symbols")
    print(
        "kernel IPC transition native: passed "
        + ", ".join(f"{k}={v}" for k, v in counts.items())
        + f" sanitize={args.sanitize} (output {out})"
    )


if __name__ == "__main__":
    main()
