#!/usr/bin/env python3
"""Native complete-input free/forward controls; no concrete kernel certificate.
Usage: probe-source-leaf.py IR ROOT_MODULE SOURCE...
The selectors are workload fixture data, never proof/checker logic.
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
FORWARD = "uncaught exception: source/publication forward semantics rejected"
POLICY = "uncaught exception: exact leaf policy rejected"
wrapper_name = "process_snapshot_writable_leaf"
leaf_name = "__au_f_m2_6kernel16snapshot_mapping_n1_6kernel_d22snapshot_writable_leaf"


def named(name):
    matches = [
        words
        for line in lines
        if (words := line.split())[0] == b"ir-callable"
        and pool[int(words[2]) : int(words[2]) + int(words[3])] == name.encode()
    ]
    assert len(matches) == 1
    return matches[0]


def codes(callable):
    return [line.split() for line in lines if line.startswith(b"ir-code " + callable[1] + b" ")]


def operand(code, index=0):
    return f"ir-operand {int(code[12]) + index} ".encode()


def row(key):
    matches = [line.split() for line in lines if line.startswith(key)]
    assert len(matches) == 1
    return matches[0]


def mutate(edits):
    changed = list(lines)
    for key, index, value in edits:
        positions = [i for i, line in enumerate(changed) if line.startswith(key)]
        assert len(positions) == 1
        words = changed[positions[0]].split()
        words[index] = value
        changed[positions[0]] = b" ".join(words) + b"\n"
    result = b"".join(changed)
    assert result != artifact
    return result


def invoke(command, error=None):
    result = subprocess.run(command, capture_output=True, text=True, timeout=90)
    if result.returncode != (0 if error is None else 1) or (error and result.stderr.strip() != error):
        raise SystemExit(f"unexpected result {result.returncode}: {command}\n{result.stdout}{result.stderr}")
    return result


wrapper = named(wrapper_name)
leaf = named(leaf_name)
wrapper_codes = codes(wrapper)
leaf_codes = codes(leaf)
call = next(code for code in wrapper_codes if code[7] == b"19")
loads = [code for code in wrapper_codes if code[7] == b"7"]
assert len(loads) == 6
mask = next(code for code in leaf_codes if code[7] == b"5" and row(operand(code))[4] == b"18442240474082185119")
shift = next(code for code in leaf_codes if code[7] == b"5" and row(operand(code))[2:4] == [b"10", b"12"])
word_type = row(operand(mask, 1))[3]
original_mask = b"18442240474082185119u64"
weaker_mask = b"18442240474082185115u64"
source_paths = [Path(path) for path in sources]
source_bytes = [path.read_bytes() for path in source_paths]
policy_indices = [i for i, data in enumerate(source_bytes) if original_mask in data]
wrapper_indices = [i for i, data in enumerate(source_bytes) if b"return kernel::snapshot_writable_leaf(" in data]
assert len(policy_indices) == len(wrapper_indices) == 1
policy_index, wrapper_index = policy_indices[0], wrapper_indices[0]
mask_edit = [(operand(mask), 4, b"18442240474082185115")]
swap = [
    (operand(loads[0]), 3, row(operand(loads[1]))[3]),
    (operand(loads[1]), 3, row(operand(loads[0]))[3]),
]
forward_text = b"kernel::snapshot_writable_leaf(leaf, physical,"
forward_swap = b"kernel::snapshot_writable_leaf(physical, leaf,"
assert forward_text in source_bytes[wrapper_index]
cases = [
    ("original", artifact, None, None, root, wrapper_name),
    ("source-only-mask", artifact, (policy_index, original_mask, weaker_mask), FORWARD, root, wrapper_name),
    ("ir-only-mask", mutate(mask_edit), None, FORWARD, root, wrapper_name),
    ("signed-count-eleven", mutate([(operand(shift), 3, b"11")]), None, FORWARD, root, wrapper_name),
    ("signed-count-word-type", mutate([(operand(shift, 1), 3, word_type)]), None, FORWARD, root, wrapper_name),
    (
        "signed-count-unsigned-role",
        mutate([(operand(shift), 2, b"11"), (operand(shift), 3, b"0"), (operand(shift), 4, b"12")]),
        None,
        FORWARD,
        root,
        wrapper_name,
    ),
    (
        "coherent-weaker-policy",
        mutate(mask_edit),
        (policy_index, original_mask, weaker_mask),
        POLICY,
        root,
        wrapper_name,
    ),
    ("coherent-forward-order", mutate(swap), (wrapper_index, forward_text, forward_swap), FORWARD, root, wrapper_name),
    (
        "wrong-callee",
        mutate([(operand(call), 5, wrapper[2]), (operand(call), 6, wrapper[3])]),
        None,
        FORWARD,
        root,
        wrapper_name,
    ),
    ("wrong-root", artifact, None, FORWARD, "fixture_wrong_root", wrapper_name),
    ("wrong-wrapper", artifact, None, FORWARD, root, "fixture_wrong_wrapper"),
    ("wrong-root-module", mutate([(b"ir-callable " + wrapper[1] + b" ", 4, b"1")]), None, FORWARD, root, wrapper_name),
    ("wrong-leaf-signature", mutate([(b"ir-callable " + leaf[1] + b" ", 5, b"0")]), None, FORWARD, root, wrapper_name),
]
results = []
with tempfile.TemporaryDirectory(prefix="aurora-source-leaf-") as directory:
    directory = Path(directory)
    for name, contents, edit, error, selected_root, selected_wrapper in cases:
        path = directory / f"{name}.ir"
        path.write_bytes(contents)
        actual_sources = list(sources)
        actual_bytes = list(source_bytes)
        if edit:
            index, before, after = edit
            assert actual_bytes[index].count(before) == 1
            actual_bytes[index] = actual_bytes[index].replace(before, after)
            changed_source = directory / f"{name}.au"
            changed_source.write_bytes(actual_bytes[index])
            actual_sources[index] = str(changed_source)
        invoke([str(structural), str(path)])
        result = invoke(
            [
                str(probe),
                "--forward-leaf",
                selected_wrapper,
                "--ir",
                str(path),
                selected_root,
                "kernel.snapshot_mapping",
                "kernel",
                "snapshot_writable_leaf",
                *actual_sources,
            ],
            error,
        )
        generic = "SOURCE-IR-FORWARD " in result.stdout
        assert generic == (error != FORWARD)
        results.append(
            {
                "case": name,
                "d1_accepts": True,
                "generic_forward_accepts": generic,
                "exact_policy_accepts": error is None,
                "bytes": len(contents),
                "sha256": hashlib.sha256(contents).hexdigest(),
                "sources": [
                    {"original_path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                    for path, data in zip(source_paths, actual_bytes)
                ],
                "changed_source_index": edit[0] if edit else None,
            }
        )
print(
    json.dumps(
        {
            "scope": "native whole-input controls; D1 baseline, not class-only D2 or concrete kernel certification",
            "cases": results,
        },
        indent=2,
    )
)
