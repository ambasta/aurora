#!/usr/bin/env python3
"""Bounded independent disposal-policy, decoder and real-dispatcher gates.

The literal expected relation is not derived from the production implementation.
A selected compiler identity is mandatory; this focused run is not full native or
kernel qualification. Hosted sanitizers do not instrument generated Aurora code.
"""

from pathlib import Path
import argparse
import hashlib
import itertools
import json
import os
import random
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "scripts"))
from compiler_contract import add_identity_arguments, resolve_identity, validate_identity_selection
from owned_outputs import allocated_bytes, free_bytes, temporary_environment, write_checked_receipt

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


def candidate_cap(mib):
    need(type(mib) is int and 128 <= mib <= 1024, "Candidate output cap must be an integer from 128 through 1024 MiB")
    return mib << 20


def cap_self_test():
    for value in (128, 512, 1024):
        need(candidate_cap(value) == value << 20, "Candidate cap boundary conversion")
    for value in (-1, 0, 127, 1025, True, 128.0, "128", None):
        try:
            candidate_cap(value)
        except RuntimeError:
            continue
        raise RuntimeError("Invalid candidate cap accepted")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def guard(out, cap, reserve=0):
    need(allocated_bytes(out) + reserve < candidate_cap(cap), "Owned-output cap reached, including reserve")
    need(free_bytes(out) - reserve >= 1024**3, "One GiB free-space floor reached, including reserve")


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
    return temporary_environment(
        out,
        ASAN_OPTIONS="detect_leaks=0:halt_on_error=1:abort_on_error=1",
        UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1",
    )


def run(command, out, label, cap, timeout=120, expect=0):
    guard(out, cap, 24 << 20)
    started = time.time()
    try:
        result = subprocess.run(command, cwd=ROOT, timeout=timeout, capture_output=True, env=environment(out))
    except subprocess.TimeoutExpired as error:
        (out / (label + ".stdout")).write_bytes(error.stdout or b"")
        (out / (label + ".stderr")).write_bytes(error.stderr or b"")
        (out / (label + ".json")).write_text(
            json.dumps(dict(command=command, timeout=True, elapsed_seconds=time.time() - started), indent=2) + "\n"
        )
        raise
    (out / (label + ".stdout")).write_bytes(result.stdout)
    (out / (label + ".stderr")).write_bytes(result.stderr)
    (out / (label + ".json")).write_text(
        json.dumps(dict(command=command, returncode=result.returncode, elapsed_seconds=time.time() - started), indent=2)
        + "\n"
    )
    need(result.returncode == expect, label + " failed; original evidence retained")
    guard(out, cap)
    return result


def vector_gate(binary, out, label, vectors, model, cap, decode=False):
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
            if count % 16384 == 0:
                guard(out, cap)
    command = [str(binary)] + (["decode"] if decode else [])
    started = time.time()
    with inputs.open("rb") as source, observed.open("wb") as actual, (out / (label + ".stderr")).open("wb") as errors:
        try:
            result = subprocess.run(
                command, stdin=source, stdout=actual, stderr=errors, cwd=ROOT, timeout=120, env=environment(out)
            )
        except subprocess.TimeoutExpired:
            (out / (label + ".json")).write_text(
                json.dumps(
                    dict(command=command, cases=count, timeout=True, elapsed_seconds=time.time() - started), indent=2
                )
                + "\n"
            )
            raise
    receipt = dict(
        command=command,
        cases=count,
        returncode=result.returncode,
        elapsed_seconds=time.time() - started,
        files={path.name: dict(bytes=path.stat().st_size, sha256=sha(path)) for path in (inputs, expected, observed)},
    )
    (out / (label + ".json")).write_text(json.dumps(receipt, indent=2) + "\n")
    need(result.returncode == 0, label + " execution failed")
    need(observed.read_bytes() == expected.read_bytes(), label + " differs from independent literal oracle")
    guard(out, cap)
    return count


def rejection_gate(compiler, out, cap):
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
    receipts = []
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
            result = run(command, out, label, cap, timeout=30, expect=1)
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
            need(diagnostic.encode() in result.stderr, label + " wrong rejection")
            need(output.read_bytes() == sentinel if existing else not output.exists(), label + " changed prior output")
    return len(receipts)


def symbol_map(data):
    return {fields[0]: tuple(fields[1:]) for line in data.decode().splitlines() if (fields := line.split())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", default=str(ROOT / "build/aurorac"))
    add_identity_arguments(parser)
    parser.add_argument("--output")
    parser.add_argument("--candidate-cap-mib", type=int, default=128)
    parser.add_argument(
        "--check-cap-only", action="store_true", help="Compiler-free configuration test, not acceptance"
    )
    parser.add_argument("--sanitize", action="store_true", default=os.environ.get("SANITIZE") == "1")
    args = parser.parse_args()
    validate_identity_selection(args, preflight=args.check_cap_only)
    cap_bytes = candidate_cap(args.candidate_cap_mib)
    cap_self_test()
    if args.check_cap_only:
        print(json.dumps(dict(status="configuration-only", native_executed=False, cap_bytes=cap_bytes), sort_keys=True))
        return
    compiler = Path(args.compiler).resolve(strict=True)
    identity = resolve_identity(args, compiler, ROOT)
    out = (
        Path(args.output).absolute()
        if args.output
        else ROOT / "build/kernel-client-disposal-native" / str(time.time_ns())
    )
    need(out.is_relative_to(ROOT), "Output must remain inside the bounded candidate")
    need(not any(path.is_symlink() for path in (out, *out.parents)), "Output symlink denied")
    need(".." not in out.parts, "Output path traversal denied")
    need(not out.exists(), "Use a fresh output directory; never overwrite failed evidence")
    cap = args.candidate_cap_mib
    guard(out, cap, 65536)
    out.mkdir(parents=True)
    members = (
        "scripts/compiler_contract.py",
        "scripts/owned_outputs.py",
        "examples/kernel.au",
        "kernel/client-disposal-transport.hpp",
        "kernel/ipc-transition-transport.hpp",
        "kernel/round-robin-transport.hpp",
        "kernel/ipc-policy.hpp",
        "kernel/dispatch-policy.hpp",
        "kernel/domain-policy.hpp",
        "tests/kernel-client-disposal-native.cpp",
        "tests/kernel-client-disposal-native.py",
        "tests/kernel-client-disposal-adapter.cpp",
        "tests/kernel-client-disposal.cpp",
        "tests/kernel-client-disposal-copy.cpp",
        "tests/kernel-programs/client-disposal-copy.au",
    )
    members = sorted(set(members) | {str(path.relative_to(ROOT)) for path in (ROOT / "kernel/policies").rglob("*.au")})
    pins = {name: sha(ROOT / name) for name in members}
    finite = [oracle(*values) for values in contexts()]
    need(
        len(finite) == 24 and finite.count(1) == 18 and sum(word > 1 for word in finite) == 6,
        "Literal table cardinality",
    )
    (out / "inputs.json").write_text(
        json.dumps(
            dict(compiler_identity=identity.record(), source_pins=pins, sanitize=args.sanitize, candidate_cap_mib=cap),
            indent=2,
        )
        + "\n"
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
        cap,
    )
    run(["g++", "-c", str(assembly), "-o", str(obj)], out, "assemble", cap)
    run(flags + ["tests/kernel-client-disposal-native.cpp", str(obj), "-o", str(binary)], out, "observer-link", cap)
    counts = dict(
        finite_contexts=24,
        finite_accepted=6,
        finite_refused=18,
        decoder_compact=768,
        policy=vector_gate(binary, out, "policy", policy_vectors(), oracle, cap),
        decoder=vector_gate(binary, out, "decoder", decoder_vectors(), decoder_oracle, cap, True),
    )
    counts["rejections"] = rejection_gate(compiler, out, cap)
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
        cap,
    )
    run(
        flags + ["tests/kernel-client-disposal-copy.cpp", str(copy_assembly), "-o", str(copy_binary)],
        out,
        "copy-link",
        cap,
    )
    run([str(copy_binary)], out, "copy-observe", cap)
    counts["copy_repetitions"] = 4096
    # Rename exactly one producer, preserving real IPC and round-robin behavior.
    substituted, adapter = out / "adapter-language.o", out / "adapter"
    old, new = "aurora_kernel_client_disposal", "aurora_kernel_client_disposal_real"
    before = symbol_map(run(["nm", "--defined-only", "--format=posix", str(obj)], out, "root-symbols", cap).stdout)
    need(
        old in before
        and new not in before
        and "aurora_kernel_ipc_transition" in before
        and "aurora_kernel_round_robin_next" in before,
        "Expected genuine policy producers missing",
    )
    run(["objcopy", "--redefine-sym", old + "=" + new, str(obj), str(substituted)], out, "rename-only-disposal", cap)
    after = symbol_map(
        run(["nm", "--defined-only", "--format=posix", str(substituted)], out, "adapter-symbols", cap).stdout
    )
    renamed = dict(before)
    renamed[new] = renamed.pop(old)
    need(after == renamed, "Only disposal symbol may be renamed")
    run(
        flags + ["tests/kernel-client-disposal-adapter.cpp", str(substituted), "-o", str(adapter)],
        out,
        "adapter-link",
        cap,
    )
    run([str(adapter)], out, "adapter-observe", cap)
    regression = out / "original-regression"
    # Preserve this regression's historical kernel-uefi-user-phases-tests.sh -O1 recipe.
    # The first focused attempt used -O2 and failed GCC 14 -Werror=array-bounds
    # in unchanged Fixture::refresh; retain build/disposal-native-001 and the
    # parent evidence/disposal-native-001 records. New tests retain their normal
    # -O2 (or sanitizer -O1), and no warning or original assertion is weakened.
    regression_flags = ["-O1" if flag == "-O2" else flag for flag in flags]
    run(
        regression_flags + ["tests/kernel-client-disposal.cpp", str(obj), "-o", str(regression)],
        out,
        "regression-link",
        cap,
    )
    run([str(regression)], out, "original-regression", cap)
    for label, executable in (("observer", binary), ("adapter", adapter), ("copy", copy_binary)):
        run(["objdump", "-drwC", str(executable)], out, label + "-disassembly", cap)
        run(["readelf", "-sW", str(executable)], out, label + "-elf-symbols", cap)
    need(pins == {name: sha(ROOT / name) for name in pins}, "Tested source changed during run")
    identity.verify()
    guard(out, cap)
    summary = dict(
        status="passed",
        compiler_identity=identity.record(),
        compiler_sha256=sha(compiler),
        source_pins=pins,
        cases=counts,
        sanitize=args.sanitize,
        candidate_cap_mib=cap,
        cap_bytes=cap_bytes,
        owned_output_allocated_bytes=allocated_bytes(out),
        free_bytes=free_bytes(out),
        output_root=str(out),
        accounting_scope="invocation outputs including tmp",
        limits=(
            "Hosted focused observations only; no QEMU, full-native acceptance or whole-kernel claim. "
            "Generated Aurora assembly is uninstrumented. Fatal hosted ASan/UBSan disables LeakSanitizer; "
            "no leak-clean claim. Unselected delivered state is unreachable through public Dispatcher APIs."
        ),
    )
    write_checked_receipt(out / "summary.json", summary, lambda: guard(out, cap))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
