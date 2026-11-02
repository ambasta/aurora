#!/usr/bin/env python3
"""Complete-input closed-DAG source/code correspondence controls. Usage: IR ROOT SOURCE...
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
error = "uncaught exception: source/runtime DAG correspondence rejected"


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


root_call = named("_d16frame_transition")
free = named("_d10frame_free")
kernel = named("_d12frame_kernel")
valid = named("_d12record_valid")
reject = named("_d12frame_reject")
fc, kc, vc, rc, root_code = codes(free), codes(kernel), codes(valid), codes(reject), codes(root_call)
source_paths = [Path(p) for p in sources]
source_bytes = [p.read_bytes() for p in source_paths]
indices = [i for i, data in enumerate(source_bytes) if b"export module kernel.frames;" in data]
assert len(indices) == 1
index = indices[0]
free_text = b"auto frame_free() -> u64 {\n        return 1u64;\n    }"
kernel_text = b"auto frame_kernel() -> u64 {\n        return 3u64;\n    }"
last_return = b"return frame_record(frame_free(), current + 1u64, link);"


def codekey(code):
    return b"ir-code " + code[1] + b" " + code[2] + b" "


def call_edits(code, target):
    return [
        (codekey(code), 7, b"19"),
        (codekey(code), 13, b"1"),
        (operand(code), 2, b"100"),
        (operand(code), 3, b"0"),
        (operand(code), 4, b"0"),
        (operand(code), 5, target[2]),
        (operand(code), 6, target[3]),
    ]


root_const = next(
    c
    for c in root_code
    if c[7] == b"5" and next(line.split() for line in lines if line.startswith(operand(c)))[4] == b"15"
)
root_state = b"const u64 state = record & 15u64;\n        const u64 current"
self_cycle = [(free_text, free_text.replace(b"return 1u64;", b"return frame_free();"))]
mutual_cycle = [
    (free_text, free_text.replace(b"return 1u64;", b"return frame_kernel();")),
    (kernel_text, kernel_text.replace(b"return 3u64;", b"return frame_free();")),
]
cases = [
    ("original-closed-root", artifact, [], True),
    ("source-self-cycle", artifact, self_cycle, False),
    ("coherent-self-cycle", mutate(call_edits(fc[0], free)), self_cycle, False),
    ("coherent-mutual-cycle", mutate(call_edits(fc[0], kernel) + call_edits(kc[0], free)), mutual_cycle, False),
    (
        "dead-root-recursion",
        artifact,
        [(last_return, last_return + b" return frame_transition(operation, record, owner, generation, link);")],
        False,
    ),
    ("dead-missing-callee", artifact, [(last_return, last_return + b" return missing();")], False),
    ("source-leaf-literal", artifact, [(free_text, free_text.replace(b"1u64", b"5u64"))], False),
    ("ir-leaf-literal", mutate([(operand(fc[0]), 4, b"5")]), [], False),
    (
        "coherent-alternative-leaf",
        mutate([(operand(fc[0]), 4, b"5")]),
        [(free_text, free_text.replace(b"1u64", b"5u64"))],
        True,
    ),
    ("nonroot-missing-return", mutate([(codekey(fc[1]), j, fc[0][j]) for j in (7, 12, 13)]), [], False),
    ("nonroot-local-store-alias", mutate([(operand(vc[5]), 3, b"24")]), [], False),
    ("nominal-case-mismatch", mutate([(operand(rc[5], 1), 3, b"3")]), [], False),
    ("root-mask-mismatch", mutate([(operand(root_const), 4, b"7")]), [], False),
    (
        "coherent-alternative-root",
        mutate([(operand(root_const), 4, b"7")]),
        [(root_state, root_state.replace(b"15u64", b"7u64"))],
        True,
    ),
    ("wrong-root-formal-order", mutate([(operand(root_code[2]), 3, b"1")]), [], False),
]


def invoke(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"abnormal exit {result.returncode}: {result.stderr}")
    return result


results = []
with tempfile.TemporaryDirectory(prefix="aurora-runtime-dag-") as directory:
    directory = Path(directory)
    for name, contents, edits, accept in cases:
        ir = directory / (name + ".ir")
        ir.write_bytes(contents)
        actual_sources = list(sources)
        actual_bytes = list(source_bytes)
        if edits:
            for before, after in edits:
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
                "--runtime-dag",
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
                "dag_accepts": accept,
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
