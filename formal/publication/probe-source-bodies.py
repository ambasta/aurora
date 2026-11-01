#!/usr/bin/env python3
"""Native complete-input body mutation receipts, not a validator or proof oracle.
Usage: probe-source-bodies.py IR ROOT_MODULE MODULE CLASS SOURCE...
The workload-specific selectors below never enter Lean checker/proof logic.
"""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

artifact = Path(sys.argv[1]).read_bytes()
root, module, cls, *sources = sys.argv[2:]
base = Path(__file__).resolve().parent
probe = base / ".lake/build/bin/source-binding-probe"
structural = base / ".lake/build/bin/publication-probe"
lines = artifact.splitlines(keepends=True)
pool = bytes.fromhex(next(line.split()[1].decode() for line in lines if line.startswith(b"ir-name-bytes ")))
callables = [line.split() for line in lines if line.startswith(b"ir-callable ")]
D1_ERROR = "uncaught exception: artifact structure rejected"
D2_ERROR = "uncaught exception: selected closure rejected"
BODY_ERROR = "uncaught exception: source/publication body semantics rejected"


def prefix(parts):
    return str(len(parts)) + "_" + "".join(str(len(p.encode())) + p for p in parts)


def row(tag):
    return next(line.split() for line in lines if line.startswith(tag))


def code_tag(code):
    return b"ir-code " + code[1] + b" " + code[2] + b" "


def operand_tag(code, index=0):
    return f"ir-operand {int(code[12]) + index} ".encode()


def mutate(edits):
    changed = list(lines)
    for tag, index, value in edits:
        matches = [i for i, line in enumerate(changed) if line.startswith(tag)]
        assert len(matches) == 1
        position = matches[0]
        words = changed[position].split()
        words[index] = value
        changed[position] = b" ".join(words) + b"\n"
    result = b"".join(changed)
    assert result != artifact
    return result


def invoke(command, error=None):
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    expected_exit = 0 if error is None else 1
    if result.returncode != expected_exit or (error is not None and result.stderr.strip() != error):
        raise SystemExit(f"unexpected process result {result.returncode}: {command}\n{result.stdout}{result.stderr}")
    return result


results = []
with tempfile.TemporaryDirectory(prefix="aurora-source-bodies-") as directory:
    directory = Path(directory)
    for member in ["enter", "leave"]:
        symbol = "__au_m_m" + prefix(module.split(".")) + "_n" + prefix(cls.split("::"))
        symbol += "_d" + str(len(member.encode())) + member
        ids = [int(w[1]) for w in callables if pool[int(w[2]) : int(w[2]) + int(w[3])] == symbol.encode()]
        assert len(ids) == 1
        codes = [line.split() for line in lines if line.startswith(f"ir-code {ids[0]} ".encode())]
        by_pc = {int(w[2]): w for w in codes}
        stores = [w for w in codes if w[7] == b"33"]
        requires = [w for w in codes if w[7] == b"91"]
        assert len(stores) >= 2 and len(requires) == 1
        requirement = requires[0]
        first, second = stores[:2]
        rhs = by_pc[int(second[2]) - 1] if member == "enter" else by_pc[int(first[2]) - 1]
        assert rhs[7] == b"5" and row(operand_tag(rhs))[2] == b"11"
        final_const = next(w for w in reversed(codes) if w[7] == b"5")
        assert row(operand_tag(final_const))[2] == b"10"
        replace_require = [
            (code_tag(requirement), 7, b"5"),
            (code_tag(requirement), 12, final_const[12]),
            (code_tag(requirement), 13, final_const[13]),
        ]
        pair_a = [by_pc[int(first[2]) - 1], first]
        pair_b = [by_pc[int(second[2]) - 1], second]
        reordered = [
            (code_tag(dst), index, src[index])
            for dst, src in zip(pair_a + pair_b, pair_b + pair_a, strict=True)
            for index in range(7, 14)
        ]
        terminal = codes[-1]
        assert terminal[7] == b"43"
        extra_store = [
            (code_tag(terminal), 7, b"33"),
            (code_tag(terminal), 5, b"6"),
            (code_tag(terminal), 12, first[12]),
            (code_tag(terminal), 13, first[13]),
        ]
        cases = [
            ("original", artifact, None),
            ("same-kind-store-target", mutate([(operand_tag(first), 3, row(operand_tag(second))[3])]), None),
            ("store-RHS-literal", mutate([(operand_tag(rhs), 4, b"9")]), None),
            ("require-replaced-by-bool-constant", mutate(replace_require), None),
            ("reordered-complete-writes", mutate(reordered), None),
            ("return-literal", mutate([(operand_tag(final_const), 3, b"0")]), None),
            (
                "missing-require-row",
                b"".join(line for line in lines if not line.startswith(code_tag(requirement))),
                D1_ERROR,
            ),
            ("terminal-replaced-by-extra-store", mutate(extra_store), D2_ERROR),
        ]
        if member == "enter":
            rhs_load = by_pc[int(first[2]) - 1]
            binds = [w for w in codes if w[7] == b"45"]
            assert rhs_load[7] == b"7" and len(binds) == 2
            # The other slot is bool, so this deliberately fails D2, not just D3.
            wrong_slot = row(operand_tag(binds[1], 1))[3]
            cases.append(("parameter-slot-type-mismatch", mutate([(operand_tag(rhs_load), 3, wrong_slot)]), D2_ERROR))
        for label, content, structural_error in cases:
            path = directory / f"{member}-{label}.ir"
            path.write_bytes(content)
            start = time.monotonic()
            invoke([str(structural), str(path), symbol], structural_error)
            invoke(
                [str(probe), "--body", "--ir", str(path), root, module, cls, member, *sources],
                None if label == "original" else BODY_ERROR,
            )
            results.append(
                {
                    "member": member,
                    "case": label,
                    "d2_accepts": structural_error is None,
                    "structural_refusal": structural_error,
                    "body_accepts": label == "original",
                    "bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "seconds": round(time.monotonic() - start, 3),
                }
            )
        source_matches = [
            (i, Path(p).read_bytes())
            for i, p in enumerate(sources)
            if ("auto " + member + "(").encode() in Path(p).read_bytes()
        ]
        assert len(source_matches) == 1
        index, source = source_matches[0]
        begin = source.index(("auto " + member + "(").encode())
        assertion = source.index(b"builtin::require(", begin)
        assertion_end = source.index(b");", assertion) + 2
        assignment = b"active_slot = slot;" if member == "enter" else b"operation = 0u64;"
        replacement = b"operation = slot;" if member == "enter" else b"active_slot = 0u64;"
        at = source.index(assignment, assertion_end)
        returning = source.index(b"return true;", assertion_end)
        source_cases = [
            ("source-assignment-target", source[:at] + source[at:].replace(assignment, replacement, 1)),
            ("source-missing-require", source[:assertion] + source[assertion_end:]),
            ("source-extra-effect", source[:returning] + b"operation = 0u64; " + source[returning:]),
        ]
        for label, content in source_cases:
            path = directory / f"{member}-{label}.au"
            path.write_bytes(content)
            changed_sources = list(sources)
            changed_sources[index] = str(path)
            # Identical original IR already passed D2 above; only source bytes change.
            invoke(
                [
                    str(probe),
                    "--body",
                    "--ir",
                    str(directory / f"{member}-original.ir"),
                    root,
                    module,
                    cls,
                    member,
                    *changed_sources,
                ],
                BODY_ERROR,
            )
            results.append(
                {
                    "member": member,
                    "case": label,
                    "d2_accepts": True,
                    "d2_reused_identical_original": True,
                    "body_accepts": False,
                    "source_bytes": len(content),
                    "source_sha256": hashlib.sha256(content).hexdigest(),
                }
            )
print(
    json.dumps(
        {
            "scope": "native receipts only; NOT concrete kernel acceptance or external/native effects proof",
            "sources": [
                {
                    "path": p,
                    "bytes": len(Path(p).read_bytes()),
                    "sha256": hashlib.sha256(Path(p).read_bytes()).hexdigest(),
                }
                for p in sources
            ],
            "cases": results,
        },
        indent=2,
    )
)
