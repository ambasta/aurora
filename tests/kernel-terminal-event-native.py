#!/usr/bin/env python3
"""Independent literal terminal-event relation and actual adapter refusal controls."""

from pathlib import Path
import argparse
import hashlib
import itertools
import json
import os
import random
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "scripts"))
from compiler_contract import add_identity_arguments, resolve_identity, validate_identity_selection

# All accepted tuples, explicit and independent of production branches/ordinals.
ACCEPTED = {
    (129, 1, 1): 1,
    (6, 2, 0): 2,
    (6, 2, 1): 2,
    (6, 4, 0): 3,
    (6, 4, 1): 3,
    (6, 8, 0): 4,
    (6, 8, 1): 4,
    (6, 16, 0): 5,
    (6, 16, 1): 5,
}
MAX = (1 << 64) - 1


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", default="build/aurorac")
    add_identity_arguments(parser)
    parser.add_argument("--output")
    parser.add_argument("--sanitize", action="store_true", default=os.environ.get("SANITIZE") == "1")
    args = parser.parse_args()
    validate_identity_selection(args)
    compiler = Path(args.compiler).resolve(strict=True)
    identity = resolve_identity(args, compiler, ROOT)
    out = Path(args.output).absolute() if args.output else ROOT / "build/terminal-event-native" / str(time.time_ns())
    need(not out.exists(), "Output must be fresh")
    need(not any(p.is_symlink() for p in (out, *out.parents)), "Output symlink denied")
    out.mkdir(parents=True)
    env = dict(
        os.environ, ASAN_OPTIONS="detect_leaks=0:halt_on_error=1", UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1"
    )
    commands = []

    def run(argv, name, data=None):
        result = subprocess.run(
            [str(x) for x in argv],
            cwd=ROOT,
            env=env,
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
        )
        (out / (name + ".stdout")).write_bytes(result.stdout)
        (out / (name + ".stderr")).write_bytes(result.stderr)
        commands.append(dict(argv=[str(x) for x in argv], status=result.returncode, name=name))
        (out / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        need(result.returncode == 0, name + " failed; see retained stderr")
        return result.stdout

    asm, obj = out / "language.s", out / "language.o"
    run([compiler, "--module-root", "kernel/policies", "examples/kernel.au", "-o", asm], "compile")
    run(["as", "--64", asm, "-o", obj], "assemble")
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
        flags += ["-g", "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"]
    binary = out / "observer"
    run(flags + ["tests/kernel-terminal-event-native.cpp", obj, "-o", binary], "link")
    edges = list(range(34)) + [
        127,
        128,
        129,
        130,
        254,
        255,
        256,
        257,
        65535,
        65536,
        (1 << 32) - 1,
        1 << 32,
        (1 << 63) - 1,
        1 << 63,
        MAX,
    ]
    finite = list(itertools.product(range(256), range(32), range(2)))
    hostile = list(itertools.product(edges, edges, [0, 1, 2, 255, 256, 1 << 32, 1 << 63, MAX]))
    rng = random.Random(0x7465726D)
    hostile += [tuple(rng.getrandbits(64) for _ in range(3)) for _ in range(4096)]
    vectors = finite + hostile
    data = "".join(f"{v} {m} {t} 0\n" for v, m, t in vectors).encode()
    observed = [int(x) for x in run([binary, "policy"], "policy", data).splitlines()]
    need(observed == [ACCEPTED.get(row, 0) for row in vectors], "Producer differs from independent literal relation")
    # Every compact result and high-bit mutation of every positive result.
    words = sorted(set(range(9)) | {MAX} | {e | (1 << bit) for e in range(6) for bit in range(3, 64)})
    decoder_vectors = [(v, m, t, e) for v, m, t in finite for e in range(8)]
    decoder_vectors += [
        (v, m, t, e) for v, m, t in list(ACCEPTED) + [(256, 1, 1), (129, 33, 1), (129, 1, 2), (6, 3, 1)] for e in words
    ]
    decoder_vectors += [(*row, words[i % len(words)]) for i, row in enumerate(hostile)]
    data = "".join(" ".join(map(str, row)) + "\n" for row in decoder_vectors).encode()
    observed = [int(x) for x in run([binary, "decoder"], "decoder", data).splitlines()]
    expected = [e if e != 0 and ACCEPTED.get((v, m, t), 0) == e else 0 for v, m, t, e in decoder_vectors]
    need(observed == expected, "Decoder accepts an unrelated or malformed proposal")
    sub = out / "substituted.o"
    before = run(["nm", "--defined-only", "--format=posix", obj], "symbols-before")
    need(
        b"aurora_kernel_terminal_event " in before and b"aurora_kernel_terminal_event_real " not in before,
        "Missing unique genuine terminal producer",
    )
    run(
        ["objcopy", "--redefine-sym", "aurora_kernel_terminal_event=aurora_kernel_terminal_event_real", obj, sub],
        "rename",
    )
    after = run(["nm", "--defined-only", "--format=posix", sub], "symbols-after")
    normalize = lambda data: sorted(data.decode().splitlines())
    need(
        normalize(before.replace(b"aurora_kernel_terminal_event ", b"aurora_kernel_terminal_event_real "))
        == normalize(after),
        "Substitution changed another producer",
    )
    adapter = out / "adapter"
    run(flags + ["-DTERMINAL_SUBSTITUTE", "tests/kernel-terminal-event-native.cpp", sub, "-o", adapter], "adapter-link")
    count = int(run([adapter, "adapter"], "adapter", "".join(str(e) + "\n" for e in words).encode()))
    need(count == len(words) * 10, "Incomplete adapter controls")
    for fixture in ["kernel-program", "kernel-program-layout", "kernel-schedule"]:
        exe = out / fixture
        run(flags + [f"tests/{fixture}.cpp", obj, "-o", exe], fixture + "-link")
        run([exe], fixture)
    receipt = dict(
        status="passed",
        scope="focused-terminal-event",
        compiler_identity=identity.record(),
        compiler_sha256=sha(compiler),
        sanitize=args.sanitize,
        generated_assembly_sanitized=False,
        finite=len(finite),
        producer=len(vectors),
        decoder=len(decoder_vectors),
        adapter=count,
        accepted_literal=[[*row, e] for row, e in ACCEPTED.items()],
        source_sha256={
            str(p.relative_to(ROOT)): sha(p)
            for p in [
                ROOT / "kernel/user-program.hpp",
                ROOT / "kernel/terminal-event-transport.hpp",
                ROOT / "kernel/policies/kernel/terminal_event.au",
                ROOT / "examples/kernel.au",
                Path(__file__),
                ROOT / "tests/kernel-terminal-event-native.cpp",
            ]
        },
    )
    (out / "run.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
