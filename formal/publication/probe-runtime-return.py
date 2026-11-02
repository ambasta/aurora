#!/usr/bin/env python3
"""Complete-input single-return controls. Usage: IR ROOT SOURCE...
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
error = "uncaught exception: source/runtime return correspondence rejected"


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
rc = codes(record)
loads = [c for c in rc if c[7] == b"7"]
counts = [c for c in rc if c[7] == b"5"]
operators = [c for c in rc if c[7] == b"12"]


def codekey(code):
    return b"ir-code " + code[1] + b" " + code[2] + b" "


source_paths = [Path(p) for p in sources]
source_bytes = [p.read_bytes() for p in source_paths]
statement = b"return state | (generation << 4) | (word << 32);"
indices = [i for i, data in enumerate(source_bytes) if statement in data]
assert len(indices) == 1
index = indices[0]
count_edit = [(operand(counts[0]), 3, b"12")]
cases = [
    ("kernel-owner", artifact, None, "kernel_owner", True),
    ("frame-record", artifact, None, "frame_record", True),
    ("ir-count", mutate(count_edit), None, "frame_record", False),
    ("source-count", artifact, (statement, statement.replace(b"<< 4", b"<< 12")), "frame_record", False),
    (
        "coherent-other-expression",
        mutate(count_edit),
        (statement, statement.replace(b"<< 4", b"<< 12")),
        "frame_record",
        True,
    ),
    ("same-typed-formal-load", mutate([(operand(loads[0]), 3, b"16")]), None, "frame_record", False),
    (
        "ordered-formal-swap",
        mutate([(operand(loads[0]), 3, b"16"), (operand(loads[1]), 3, b"8")]),
        None,
        "frame_record",
        False,
    ),
    ("entry-index", mutate([(operand(rc[0]), 3, b"1")]), None, "frame_record", False),
    ("ir-operator", mutate([(codekey(operators[1]), 9, b"5")]), None, "frame_record", False),
    ("source-operator", artifact, (statement, statement.replace(b"state |", b"state &")), "frame_record", False),
    (
        "source-result-type",
        artifact,
        (
            b"auto frame_record(u64 state, u64 generation, u64 word) -> u64",
            b"auto frame_record(u64 state, u64 generation, u64 word) -> bool",
        ),
        "frame_record",
        False,
    ),
    ("source-extra-return", artifact, (statement, statement + b" return state;"), "frame_record", False),
    ("return-replaced", mutate([(codekey(rc[-1]), 7, b"9")]), None, "frame_record", False),
]


def invoke(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"abnormal exit {result.returncode}: {result.stderr}")
    return result


results = []
with tempfile.TemporaryDirectory(prefix="aurora-runtime-return-") as directory:
    directory = Path(directory)
    for name, contents, edit, member, accept in cases:
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
                "--runtime-expression",
                "--ir",
                str(ir),
                root,
                "kernel.frames",
                "kernel",
                member,
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
                "correspondence_accepts": accept,
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
