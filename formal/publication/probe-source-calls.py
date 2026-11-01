#!/usr/bin/env python3
"""Native actual-source/full-publication call controls; not a proof oracle.
Usage: probe-source-calls.py IR ROOT MODULE CLASS SOURCE...
"""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

artifact = Path(sys.argv[1]).read_bytes()
root, module, cls, *sources = sys.argv[2:]
base = Path(__file__).resolve().parent
probe = base / ".lake/build/bin/source-binding-probe"
structural = base / ".lake/build/bin/publication-probe"
lines = artifact.splitlines(keepends=True)
pool = bytes.fromhex(next(x.split()[1].decode() for x in lines if x.startswith(b"ir-name-bytes ")))
D1 = "uncaught exception: artifact structure rejected"
D2 = "uncaught exception: selected closure rejected"
CALL = "uncaught exception: source/publication call semantics rejected"


def prefix(parts):
    return str(len(parts)) + "_" + "".join(str(len(p.encode())) + p for p in parts)


def symbol(member):
    return "__au_m_m" + prefix(module.split(".")) + "_n" + prefix(cls.split("::")) + "_d" + str(len(member)) + member


def codes(member):
    ids = [
        w[1]
        for line in lines
        if (w := line.split())[0] == b"ir-callable"
        and pool[int(w[2]) : int(w[2]) + int(w[3])] == symbol(member).encode()
    ]
    assert len(ids) == 1
    return [x.split() for x in lines if x.startswith(b"ir-code " + ids[0] + b" ")]


def tag(code):
    return b"ir-code " + code[1] + b" " + code[2] + b" "


def operand(code, index=0):
    return f"ir-operand {int(code[12]) + index} ".encode()


def row(key):
    return next(x.split() for x in lines if x.startswith(key))


def mutate(edits):
    changed = list(lines)
    for key, index, value in edits:
        positions = [i for i, x in enumerate(changed) if x.startswith(key)]
        assert len(positions) == 1
        i = positions[0]
        words = changed[i].split()
        words[index] = value
        changed[i] = b" ".join(words) + b"\n"
    result = b"".join(changed)
    assert result != artifact
    return result


def invoke(command, error=None):
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if result.returncode != (0 if error is None else 1) or (error and result.stderr.strip() != error):
        raise SystemExit(f"unexpected result {result.returncode}: {command}\n{result.stdout}{result.stderr}")


root_codes = codes("fill_snapshot")
external = next(w for w in root_codes if w[7] == b"89")
external_pc = int(external[2])
by_pc = {int(w[2]): w for w in root_codes}
loads = [by_pc[external_pc - n] for n in [8, 6, 2]]
zero = by_pc[external_pc - 4]
assert all(w[7] == b"7" for w in loads) and zero[7] == b"5"
require = by_pc[external_pc + 1]
assert require[7] == b"91"
ordinary = [w for w in root_codes if w[7] == b"38"]
assert len(ordinary) == 2
last_const = root_codes[-2]
assert last_const[7] == b"5"
enter_codes = codes("enter")
stores = [w for w in enter_codes if w[7] == b"33"]
method_id = row(operand(external, 2))[3]
resource_id = row(operand(external, 4))[3]
method_key = b"ir-resource-method " + resource_id + b" " + method_id + b" "
method = row(method_key)
new_native = b"fixture_alternate_runtime_binding".hex().encode()
cases = [
    ("original", artifact, None, True),
    (
        "argument-order",
        mutate([(operand(loads[0]), 3, row(operand(loads[1]))[3]), (operand(loads[1]), 3, row(operand(loads[0]))[3])]),
        None,
        False,
    ),
    ("zero-literal", mutate([(operand(zero), 4, b"1")]), None, False),
    (
        "callee-target",
        mutate(
            [
                (operand(ordinary[0]), 5, row(operand(ordinary[1]))[5]),
                (operand(ordinary[0]), 6, row(operand(ordinary[1]))[6]),
            ]
        ),
        D2,
        False,
    ),
    ("resource-field", mutate([(operand(external, 1), 3, b"0")]), D2, False),
    ("resource-method", mutate([(operand(external, 2), 3, b"0")]), D2, False),
    (
        "require-replaced",
        mutate([(tag(require), 7, b"5"), (tag(require), 12, last_const[12]), (tag(require), 13, last_const[13])]),
        None,
        False,
    ),
    ("callee-store-target", mutate([(operand(stores[0]), 3, row(operand(stores[1]))[3])]), None, False),
    ("return-literal", mutate([(operand(last_const), 3, b"0")]), None, False),
    ("missing-trailing-return", b"".join(x for x in lines if not x.startswith(tag(root_codes[-1]))), D1, False),
    ("coherent-different-native-interface", mutate([(method_key, 9, new_native)]), None, True),
    ("changed-source-method-spelling", mutate([(method_key, 10, b"other_source_method".hex().encode())]), None, False),
]
# Swap complete invocation payloads: D2 accepts their structure; source-use correspondence rejects.
cases.append(
    (
        "reordered-calls",
        mutate(
            [(tag(dst), i, src[i]) for dst, src in zip(ordinary, reversed(ordinary), strict=True) for i in range(7, 14)]
        ),
        None,
        False,
    )
)
# A former administrative label cannot hide a real extra effect.
label = by_pc[int(ordinary[0][2]) - 5]
assert label[7] == b"40"
cases.append(
    (
        "extra-nonlabel",
        mutate([(tag(label), 7, b"5"), (tag(label), 12, last_const[12]), (tag(label), 13, last_const[13])]),
        D2,
        False,
    )
)
results = []
with tempfile.TemporaryDirectory(prefix="aurora-call-controls-") as temp:
    temp = Path(temp)
    for name, content, structural_error, accepts in cases:
        path = temp / (name + ".ir")
        path.write_bytes(content)
        invoke([str(structural), str(path), symbol("fill_snapshot")], structural_error)
        invoke(
            [str(probe), "--calls", "--ir", str(path), root, module, cls, "fill_snapshot", *sources],
            None if accepts else CALL,
        )
        print(f"PASS {name}", file=sys.stderr, flush=True)
        results.append(
            {
                "case": name,
                "d2_accepts": structural_error is None,
                "earlier_refusal": structural_error,
                "calls_accepts": accepts,
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    matches = [
        (i, Path(p).read_bytes()) for i, p in enumerate(sources) if b"auto fill_snapshot(" in Path(p).read_bytes()
    ]
    assert len(matches) == 1
    index, source = matches[0]
    begin = source.index(b"auto fill_snapshot(")
    tail = source[begin:]
    edits = [
        (
            "source-argument-order",
            b"fill_snapshot_chunk(epoch, offset, 0u64, count)",
            b"fill_snapshot_chunk(offset, epoch, 0u64, count)",
        ),
        (
            "source-zero",
            b"fill_snapshot_chunk(epoch, offset, 0u64, count)",
            b"fill_snapshot_chunk(epoch, offset, 1u64, count)",
        ),
        ("source-extra-call", b"leave();", b"leave(); leave();"),
        (
            "source-missing-require",
            b"builtin::require(authority.fill_snapshot_chunk(epoch, offset, 0u64, count));",
            b"authority.fill_snapshot_chunk(epoch, offset, 0u64, count);",
        ),
        ("source-extra-effect", b"return true;", b"operation = 0u64; return true;"),
    ]
    for name, old, new in edits:
        assert old in tail
        content = source[:begin] + tail.replace(old, new, 1)
        path = temp / (name + ".au")
        path.write_bytes(content)
        changed = list(sources)
        changed[index] = str(path)
        invoke(
            [str(probe), "--calls", "--ir", str(temp / "original.ir"), root, module, cls, "fill_snapshot", *changed],
            CALL,
        )
        print(f"PASS {name}", file=sys.stderr, flush=True)
        results.append(
            {
                "case": name,
                "d2_accepts": True,
                "identical_original_ir": True,
                "calls_accepts": False,
                "source_bytes": len(content),
                "source_sha256": hashlib.sha256(content).hexdigest(),
            }
        )
print(
    json.dumps(
        {
            "scope": "native only; changed coherent linkage is a different supplied interface, not fidelity proof",
            "publication_sha256": hashlib.sha256(artifact).hexdigest(),
            "sources": [
                {"path": p, "bytes": Path(p).stat().st_size, "sha256": hashlib.sha256(Path(p).read_bytes()).hexdigest()}
                for p in sources
            ],
            "cases": results,
        },
        indent=2,
    )
)
