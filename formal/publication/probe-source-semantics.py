#!/usr/bin/env python3
"""Native production mutation receipts, not a parser, proof checker, or hash proof.
Usage: probe-source-semantics.py IR ROOT_MODULE MODULE CLASS MEMBER SOURCE...
Requires the complete captured source graph and current full IR publication.
"""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

artifact = Path(sys.argv[1]).read_bytes()
root_module, module, cls, member, *source_paths = sys.argv[2:]
selection = [root_module, module, cls, member]
base = Path(__file__).resolve().parent
exe = base / ".lake/build/bin/source-binding-probe"
structural = base / ".lake/build/bin/publication-probe"


def prefix(parts):
    return str(len(parts)) + "_" + "".join(str(len(p.encode())) + p for p in parts)


symbol = (
    "__au_m_m" + prefix(module.split(".")) + "_n" + prefix(cls.split("::")) + "_d" + str(len(member.encode())) + member
)
lines = artifact.splitlines(keepends=True)
pool = bytes.fromhex(next(line.split()[1].decode() for line in lines if line.startswith(b"ir-name-bytes ")))
callables = [line.split() for line in lines if line.startswith(b"ir-callable ")]
ids = [int(w[1]) for w in callables if pool[int(w[2]) : int(w[2]) + int(w[3])] == symbol.encode()]
assert len(ids) == 1
codes = [line.split() for line in lines if line.startswith(f"ir-code {ids[0]} ".encode())]


def change(tag, index, value):
    changed = list(lines)
    positions = [i for i, line in enumerate(lines) if line.startswith(tag)]
    assert len(positions) == 1
    pos = positions[0]
    words = changed[pos].split()
    assert words[index] != value
    words[index] = value
    changed[pos] = b" ".join(words) + b"\n"
    return b"".join(changed)


def operand(row, index=0):
    return f"ir-operand {int(row[12]) + index} ".encode()


def code(row):
    return b"ir-code " + row[1] + b" " + row[2] + b" "


def words(tag):
    return next(line.split() for line in lines if line.startswith(tag))


loads = [w for w in codes if w[7] == b"32"]
locals_ = [w for w in codes if w[7] == b"7"]
constants = [w for w in codes if w[7] == b"5"]
comparison = next(w for w in codes if w[7] == b"14")
subtraction = next(w for w in codes if w[7] == b"12")
# These fixture choices describe this production workload; proof/checker logic
# contains no callable IDs, field ordinals, golden hashes, or expected answers.
cases = [
    ("original", artifact, True),
    ("same-typed-field-use", change(operand(loads[0]), 3, words(operand(loads[1]))[3]), False),
    ("bytes-read-as-epoch", change(operand(loads[2]), 3, words(operand(loads[1]))[3]), False),
    ("same-typed-formal-use", change(operand(locals_[0]), 3, words(operand(locals_[1]))[3]), False),
    ("guard-word-literal", change(operand(constants[0]), 4, b"2"), False),
    ("guard-comparison", change(code(comparison), 10, b"0"), False),
    ("subtraction-to-addition", change(code(subtraction), 9, b"0"), False),
]
results = []
with tempfile.TemporaryDirectory(prefix="aurora-source-semantics-") as directory:
    for label, content, expected in cases:
        path = Path(directory) / (label + ".ir")
        path.write_bytes(content)
        start = time.monotonic()
        d2 = subprocess.run([str(structural), str(path), symbol], capture_output=True, text=True, timeout=60)
        checked = subprocess.run(
            [str(exe), "--ir", str(path), *selection, *source_paths], capture_output=True, text=True, timeout=60
        )
        accepted = checked.returncode == 0
        # Abnormal terminations are never successful negative tests.
        d2_expected = label != "subtraction-to-addition"
        if (
            (d2.returncode == 0) != d2_expected
            or d2.returncode not in (0, 1)
            or accepted != expected
            or checked.returncode not in (0, 1)
        ):
            raise SystemExit(
                f"{label}: unexpected D2={d2.returncode} semantic={checked.returncode}\n{d2.stderr}{checked.stderr}"
            )
        if not d2_expected and d2.stderr.strip() != "uncaught exception: selected closure rejected":
            raise SystemExit(f"{label}: unexpected structural refusal {d2.stderr!r}")
        if not expected and checked.stderr.strip() != "uncaught exception: source/publication guard semantics rejected":
            raise SystemExit(f"{label}: unexpected refusal {checked.stderr!r}")
        results.append(
            {
                "case": label,
                "d2_accepts": d2.returncode == 0,
                "semantic_accepts": accepted,
                "exit": checked.returncode,
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "elapsed_seconds": round(time.monotonic() - start, 3),
            }
        )
    # Independently mutate a real selected source use, retaining all graph files.
    found = [
        (i, Path(p).read_bytes())
        for i, p in enumerate(source_paths)
        if ("auto " + member + "(").encode() in Path(p).read_bytes()
    ]
    assert len(found) == 1
    index, source = found[0]
    begin = source.index(("auto " + member + "(").encode())
    target = source.index(b"snapshot_phase != 1u64", begin)
    altered = source[:target] + source[target:].replace(b"snapshot_phase != 1u64", b"snapshot_epoch != 1u64", 1)
    changed_path = Path(directory) / "changed-source.au"
    changed_path.write_bytes(altered)
    changed_sources = list(source_paths)
    changed_sources[index] = str(changed_path)
    original_path = Path(directory) / "original.ir"
    checked = subprocess.run(
        [str(exe), "--ir", str(original_path), *selection, *changed_sources], capture_output=True, text=True, timeout=60
    )
    if (
        checked.returncode != 1
        or checked.stderr.strip() != "uncaught exception: source/publication guard semantics rejected"
    ):
        raise SystemExit(f"source-use mutation unexpected exit {checked.returncode}: {checked.stderr}")
    results.append(
        {
            "case": "actual-source-same-typed-name-use",
            "d2_accepts": True,
            "semantic_accepts": False,
            "exit": checked.returncode,
            "source_bytes": len(altered),
            "sha256": hashlib.sha256(altered).hexdigest(),
        }
    )
print(
    json.dumps(
        {
            "scope": "native receipts, NOT concrete kernel acceptance; tail/backend/capture unproved",
            "sources": [
                {
                    "path": p,
                    "bytes": len(Path(p).read_bytes()),
                    "sha256": hashlib.sha256(Path(p).read_bytes()).hexdigest(),
                }
                for p in source_paths
            ],
            "cases": results,
        },
        indent=2,
    )
)
