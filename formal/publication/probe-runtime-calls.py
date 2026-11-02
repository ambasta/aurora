#!/usr/bin/env python3
"""Complete-input contextual nested-call interval controls. Usage: IR ROOT SOURCE...
Selectors are workload fixtures, never checker logic. No lifecycle policy claim.
"""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

artifact = Path(sys.argv[1]).read_bytes()
root, *sources = sys.argv[2:]
base = Path(__file__).resolve().parent
probe = base / ".lake/build/bin/source-binding-probe"
structural = base / ".lake/build/bin/publication-probe"
lines = artifact.splitlines(keepends=True)
pool = bytes.fromhex(next(line.split()[1].decode() for line in lines if line.startswith(b"ir-name-bytes ")))
error = "uncaught exception: source/runtime call interval rejected"


def named(suffix):
    matches = [
        w
        for line in lines
        if (w := line.split())[0] == b"ir-callable"
        and pool[int(w[2]) : int(w[2]) + int(w[3])].endswith(suffix.encode())
    ]
    assert len(matches) == 1
    return matches[0]


def codes(callable):
    return [line.split() for line in lines if line.startswith(b"ir-code " + callable[1] + b" ")]


def operand(code, index=0):
    return f"ir-operand {int(code[12]) + index} ".encode()


def mutate(edits):
    changed = list(lines)
    for key, index, value in edits:
        positions = [i for i, line in enumerate(changed) if line.startswith(key)]
        assert len(positions) == 1
        words = changed[positions[0]].split()
        words[index] = value
        changed[positions[0]] = b" ".join(words) + b"\n"
    return b"".join(changed)


record = named("_d12frame_record")
caller = named("_d16frame_transition")
kernel = named("_d12frame_kernel")
free = named("_d10frame_free")
rc = codes(record)
cc = codes(caller)


def row(key):
    matches = [line.split() for line in lines if line.startswith(key)]
    assert len(matches) == 1
    return matches[0]


def call_name(code):
    op = row(operand(code))
    return pool[int(op[5]) : int(op[5]) + int(op[6])]


def symbol(callable):
    return pool[int(callable[2]) : int(callable[2]) + int(callable[3])]


def codekey(code):
    return b"ir-code " + code[1] + b" " + code[2] + b" "


outer = next(c for c in cc if c[7] == b"19" and call_name(c) == symbol(record))
start_pc = int(outer[2]) - 6
inner, zero, owner = cc[start_pc], cc[start_pc + 2], cc[start_pc + 4]
assert inner[7] == b"19" and call_name(inner) == symbol(kernel)
assert zero[7] == b"5" and owner[7] == b"7"
counts = [c for c in rc if c[7] == b"5"]
source_paths = [Path(p) for p in sources]
source_bytes = [p.read_bytes() for p in source_paths]
expression = b"frame_record(frame_kernel(), 0u64, owner)"
indices = [i for i, data in enumerate(source_bytes) if b"export module kernel.frames;" in data and expression in data]
assert len(indices) == 1
index = indices[0]
call_edit = [(operand(inner), 5, free[2]), (operand(inner), 6, free[3])]
argument_swap = [(codekey(zero), j, owner[j]) for j in (7, 12, 13)] + [
    (codekey(owner), j, zero[j]) for j in (7, 12, 13)
]
leaf_statement = b"return state | (generation << 4) | (word << 32);"
count_edit = [(operand(counts[0]), 3, b"12")]
cases = [
    ("original-nested", artifact, None, True, "0,1,1", start_pc),
    ("ir-callee", mutate(call_edit), None, False, "0,1,1", start_pc),
    (
        "source-callee",
        artifact,
        (expression, expression.replace(b"frame_kernel", b"frame_free")),
        False,
        "0,1,1",
        start_pc,
    ),
    (
        "coherent-other-callee",
        mutate(call_edit),
        (expression, expression.replace(b"frame_kernel", b"frame_free")),
        True,
        "0,1,1",
        start_pc,
    ),
    ("ir-argument-order", mutate(argument_swap), None, False, "0,1,1", start_pc),
    (
        "source-argument-order",
        artifact,
        (expression, b"frame_record(frame_kernel(), owner, 0u64)"),
        False,
        "0,1,1",
        start_pc,
    ),
    (
        "coherent-other-arguments",
        mutate(argument_swap),
        (expression, b"frame_record(frame_kernel(), owner, 0u64)"),
        True,
        "0,1,1",
        start_pc,
    ),
    ("callee-ir-count", mutate(count_edit), None, False, "0,1,1", start_pc),
    (
        "callee-source-count",
        artifact,
        (leaf_statement, leaf_statement.replace(b"<< 4", b"<< 12")),
        False,
        "0,1,1",
        start_pc,
    ),
    (
        "coherent-other-leaf",
        mutate(count_edit),
        (leaf_statement, leaf_statement.replace(b"<< 4", b"<< 12")),
        True,
        "0,1,1",
        start_pc,
    ),
    ("same-typed-formal-slot", mutate([(operand(owner), 3, b"40")]), None, False, "0,1,1", start_pc),
    ("root-prefix-formal-index", mutate([(operand(cc[2]), 3, b"1")]), None, False, "0,1,1", start_pc),
    ("wrong-candidate-pc", artifact, None, False, "0,1,1", start_pc + 1),
    ("different-source-occurrence", artifact, None, False, "0,3", start_pc),
    ("unsupported-nonsingle-return-callee", artifact, None, False, "0,0,0", 23),
]


def invoke(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"abnormal exit {result.returncode}: {result.stderr}")
    return result


results = []
with tempfile.TemporaryDirectory(prefix="aurora-runtime-calls-") as directory:
    directory = Path(directory)
    for name, contents, edit, accept, source_path, candidate in cases:
        ir = directory / (name + ".ir")
        ir.write_bytes(contents)
        actual_sources = list(sources)
        actual_bytes = list(source_bytes)
        if edit:
            before, after = edit
            assert actual_bytes[index].count(before) == 1
            actual_bytes[index] = actual_bytes[index].replace(before, after)
            source = directory / (name + ".au")
            source.write_bytes(actual_bytes[index])
            actual_sources[index] = str(source)
        d1 = invoke([str(structural), str(ir)])
        if d1.returncode != 0:
            raise RuntimeError(f"{name}: unexpected D1 refusal: {d1.stderr}")
        result = invoke(
            [
                str(probe),
                "--runtime-call-expression",
                source_path,
                str(candidate),
                "--ir",
                str(ir),
                root,
                "kernel.frames",
                "kernel",
                "frame_transition",
                *actual_sources,
            ]
        )
        assert result.returncode == (0 if accept else 1), (name, result.stdout, result.stderr)
        if not accept:
            assert result.stderr.strip() == error, (name, result.stderr)
        results.append(
            {
                "case": name,
                "d1_accepts": True,
                "interval_accepts": accept,
                "source_path": source_path,
                "candidate_pc": candidate,
                "ir_bytes": len(contents),
                "ir_sha256": hashlib.sha256(contents).hexdigest(),
                "sources": [
                    {"original_path": str(p), "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
                    for p, b in zip(source_paths, actual_bytes)
                ],
            }
        )
print(
    json.dumps(
        {
            "scope": (
                "native full-input controls; copied capture, not concrete kernel certification or lifecycle ResultSpec"
            ),
            "cases": results,
        },
        indent=2,
    )
)
