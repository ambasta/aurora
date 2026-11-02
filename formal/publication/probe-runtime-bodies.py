#!/usr/bin/env python3
"""Complete-input whole-body source/code correspondence controls. Usage: IR ROOT SOURCE...
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
error = "uncaught exception: source/runtime body correspondence rejected"


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


valid = named("_d12record_valid")
reject = named("_d12frame_reject")
vc, rc = codes(valid), codes(reject)
source_paths = [Path(p) for p in sources]
source_bytes = [p.read_bytes() for p in source_paths]
indices = [i for i, data in enumerate(source_bytes) if b"export module kernel.frames;" in data]
assert len(indices) == 1
index = indices[0]
mask_source = b"const u64 state = record & 15u64;"
# The same local declaration also occurs in frame_transition; replace both
# coherently in source. Only record_valid is selected in these controls.
mask_edit = [(operand(vc[3]), 4, b"7")]
code_edit = [(operand(rc[8]), 4, b"11")]
cases = [
    ("original-record-valid", artifact, None, True, "record_valid"),
    ("original-frame-reject", artifact, None, True, "frame_reject"),
    ("ir-initializer-mask", mutate(mask_edit), None, False, "record_valid"),
    ("source-initializer-mask", artifact, (mask_source, mask_source.replace(b"15u64", b"7u64")), False, "record_valid"),
    (
        "coherent-other-mask",
        mutate(mask_edit),
        (mask_source, mask_source.replace(b"15u64", b"7u64")),
        True,
        "record_valid",
    ),
    ("same-typed-local-store", mutate([(operand(vc[5]), 3, b"24")]), None, False, "record_valid"),
    ("same-typed-local-load", mutate([(operand(vc[25]), 3, b"16")]), None, False, "record_valid"),
    ("wrong-branch-target", mutate([(operand(vc[15]), 3, b"20")]), None, False, "record_valid"),
    ("wrong-formal-index", mutate([(operand(vc[0]), 3, b"1")]), None, False, "record_valid"),
    ("wrong-enum-case", mutate([(operand(rc[5], 1), 3, b"3")]), None, False, "frame_reject"),
    ("ir-assignment-value", mutate(code_edit), None, False, "frame_reject"),
    ("coherent-other-assignment", mutate(code_edit), (b"code = 2u64;", b"code = 11u64;"), True, "frame_reject"),
    ("const-assignment", artifact, (b"u64 code = 1u64;", b"const u64 code = 1u64;"), False, "frame_reject"),
    ("self-initializer", artifact, (b"u64 code = 1u64;", b"u64 code = code;"), False, "frame_reject"),
    (
        "unchecked-return-suffix",
        artifact,
        (b"return code << 4;", b"return code << 4; return 0u64;"),
        False,
        "frame_reject",
    ),
    (
        "missing-source-branch",
        artifact,
        (b"if (reason == FrameRejection::record) {\n            code = 2u64;\n        }", b""),
        False,
        "frame_reject",
    ),
    (
        "wrong-return-kind",
        artifact,
        (b"auto record_valid(u64 record) -> bool", b"auto record_valid(u64 record) -> u64"),
        False,
        "record_valid",
    ),
]


def invoke(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"abnormal exit {result.returncode}: {result.stderr}")
    return result


results = []
with tempfile.TemporaryDirectory(prefix="aurora-runtime-bodies-") as directory:
    directory = Path(directory)
    for name, contents, edit, accept, member in cases:
        ir = directory / (name + ".ir")
        ir.write_bytes(contents)
        actual_sources = list(sources)
        actual_bytes = list(source_bytes)
        if edit:
            before, after = edit
            assert actual_bytes[index].count(before) >= 1
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
                "--runtime-body",
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
                "body_accepts": accept,
                "member": member,
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
