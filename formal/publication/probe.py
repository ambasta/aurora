#!/usr/bin/env python3
"""Mutation runner for the SAME Lean executable; not a parser/semantic validator.
Requires a separately captured full production artifact, not a host-pruned AST.
"""

import json
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time

source = Path(sys.argv[1]).read_bytes()
roots = sys.argv[2:]
exe = Path(__file__).parent / ".lake/build/bin/publication-probe"
lines = source.splitlines(keepends=True)


def change_line(tag, change):
    changed = list(lines)
    index = next(i for i, line in enumerate(changed) if line.startswith(tag))
    changed[index] = change(changed[index])
    return b"".join(changed)


def field(line, index, value):
    words = line.rstrip(b"\n").split(b" ")
    words[index] = value
    return b" ".join(words) + b"\n"


cases = [
    ("original", source, True),
    ("unknown-tag", b"unknown\n" + source, False),
    ("missing-final-LF", source[:-1], False),
    ("trailing-display", source + b"origin harmless\n", False),
    ("duplicate-type", change_line(b"ir-type 0 ", lambda x: x + x), False),
    ("missing-type", change_line(b"ir-type 0 ", lambda _: b""), False),
    ("bad-type-id", change_line(b"ir-type 0 ", lambda x: field(x, 1, b"-1")), False),
    ("bad-type-range", change_line(b"ir-type 0 ", lambda x: field(x, 3, b"9223372036854775807")), False),
    ("overflow", change_line(b"ir-counts ", lambda x: field(x, 1, b"9223372036854775808")), False),
    ("bad-body-position", change_line(b"ir-code ", lambda x: field(x, 2, b"1")), False),
    ("missing-body-end", change_line(b"ir-end-body ", lambda _: b""), False),
    ("wrong-body-count", change_line(b"ir-end-body ", lambda x: field(x, 2, b"0")), False),
    ("wrong-trailer", change_line(b"ir-end ", lambda x: field(x, 1, b"0")), False),
    ("control-byte", change_line(b"origin ", lambda x: x[:-1] + b"\x00\n"), False),
    # D1 does not validate operation semantics/CFG outside a selected closure.
    ("opaque-unselected-form", change_line(b"ir-code ", lambda x: field(x, 7, b"999")), True),
    ("opaque-unselected-target", change_line(b"ir-code ", lambda x: field(x, 4, b"999")), True),
]
if roots:
    # Untrusted mutation addressing for this production workload only. These
    # helpers do not admit an AST or issue a certificate; Lean consumes every
    # resulting complete raw file independently.
    pool = bytes.fromhex(
        next(line.split(b" ", 1)[1].decode().strip() for line in lines if line.startswith(b"ir-name-bytes "))
    )
    callable_rows = [line.split() for line in lines if line.startswith(b"ir-callable ")]

    def callable_id(name):
        matches = [int(w[1]) for w in callable_rows if pool[int(w[2]) : int(w[2]) + int(w[3])] == name]
        if len(matches) != 1:
            raise SystemExit("mutation fixture callable identity unavailable")
        return matches[0]

    root = callable_id(roots[0].encode())
    enter_name = roots[0].rsplit("d13fill_snapshot", 1)[0] + "d5enter"
    enter = callable_id(enter_name.encode())
    root_codes = [line.split() for line in lines if line.startswith(f"ir-code {root} ".encode())]
    enter_codes = [line.split() for line in lines if line.startswith(f"ir-code {enter} ".encode())]

    def code_tag(w):
        return b"ir-code " + w[1] + b" " + w[2] + b" "

    def operand_tag(w, ordinal=0):
        return f"ir-operand {int(w[12]) + ordinal} ".encode()

    receiver_loads = [w for w in root_codes if w[7] == b"32"]
    branch = next(w for w in root_codes if w[7] == b"42")
    bind = next(w for w in root_codes if w[7] == b"45")
    final_const = next(w for w in reversed(root_codes) if w[7] == b"5")
    enter_final_const = next(w for w in reversed(enter_codes) if w[7] == b"5")
    # This workload has same-typed snapshot phase/epoch fields43/42.
    first_field = next(line.split()[3] for line in lines if line.startswith(operand_tag(receiver_loads[0])))
    second_field = next(line.split()[3] for line in lines if line.startswith(operand_tag(receiver_loads[1])))
    removed_enter = [
        line
        for line in lines
        if not any(line.startswith(f"{tag} {enter} ".encode()) for tag in ("ir-body", "ir-code", "ir-end-body"))
    ]
    removed_enter = [
        field(line, 1, str(int(line.split()[1]) - 1).encode()) if line.startswith(b"ir-end ") else line
        for line in removed_enter
    ]
    root_signature = next(w for w in callable_rows if int(w[1]) == root)
    receiver_name = pool[int(root_signature[7]) : int(root_signature[7]) + int(root_signature[8])]
    cls = next(
        line.split()
        for line in lines
        if line.startswith(b"ir-class ")
        and pool[int(line.split()[2]) : int(line.split()[2]) + int(line.split()[3])] == receiver_name
    )
    leaf_tag = f"ir-type {int(cls[5])} ".encode()
    enter_branch = next(w for w in reversed(enter_codes) if w[7] == b"42")
    cases += [
        ("selected-leaf-tail", change_line(leaf_tag, lambda x: field(x, 7, b"1")), False),
        ("selected-leaf-name", change_line(leaf_tag, lambda x: field(field(x, 3, b"0"), 4, b"1")), False),
        (
            "false-reached-block",
            change_line(code_tag(enter_branch), lambda x: field(field(x, 7, b"41"), 5, b"4")),
            False,
        ),
        ("selected-unknown-form", change_line(code_tag(root_codes[0]), lambda x: field(x, 7, b"999")), False),
        ("selected-unknown-flags", change_line(code_tag(root_codes[0]), lambda x: field(x, 5, b"15")), False),
        (
            "selected-wrong-target",
            change_line(code_tag(branch), lambda x: field(x, 4, str(int(branch[4]) + 1).encode())),
            False,
        ),
        ("selected-backedge", change_line(code_tag(branch), lambda x: field(x, 4, b"0")), False),
        ("selected-missing-code", change_line(code_tag(root_codes[3]), lambda _: b""), False),
        ("missing-ordinary-callee-body", b"".join(removed_enter), False),
        ("wrong-formal-binding", change_line(operand_tag(bind), lambda x: field(x, 3, b"1")), False),
        ("boolean-two", change_line(operand_tag(final_const), lambda x: field(x, 3, b"2")), False),
        ("catalogue-arity", change_line(b"ir-resource-method 4 19 ", lambda x: field(x, 5, b"5")), False),
        ("catalogue-unknown-effect", change_line(b"ir-resource-method 4 19 ", lambda x: field(x, 8, b"3")), False),
        (
            "consume-unknown-join",
            change_line(code_tag(enter_final_const), lambda x: field(field(x, 7, b"91"), 13, b"0")),
            False,
        ),
        # EXPECTED ACCEPTANCE: typing does not establish source field-use identity.
        (
            "same-typed-field-swap",
            change_line(operand_tag(receiver_loads[0]), lambda x: field(x, 3, second_field)),
            True,
        ),
    ]
    if first_field == second_field:
        raise SystemExit("field-swap mutation would be a no-op")

results = []
with tempfile.TemporaryDirectory() as temporary:
    for name, content, expected in cases:
        path = Path(temporary) / (name + ".ir")
        path.write_bytes(content)
        start = time.monotonic()
        run = subprocess.run([str(exe), str(path), *roots], capture_output=True, text=True, timeout=30)
        if run.returncode not in (0, 1):
            raise SystemExit(f"{name}: abnormal termination {run.returncode}: {run.stderr}")
        if run.returncode == 1 and run.stderr.strip() not in (
            "uncaught exception: artifact structure rejected",
            "uncaught exception: selected closure rejected",
        ):
            raise SystemExit(f"{name}: unexpected failure: {run.stderr}")
        passed = run.returncode == 0
        result = dict(
            case=name,
            expected=expected,
            accepted=passed,
            wall_seconds=time.monotonic() - start,
            stdout=run.stdout.strip(),
            stderr=run.stderr.strip(),
        )
        results.append(result)
        if passed != expected:
            print(json.dumps(results, indent=2))
            raise SystemExit("mutation outcome mismatch")
print(
    json.dumps(
        dict(
            scope="native execution checks, not concrete kernel proofs",
            cases=results,
            max_child_rss_KiB=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        ),
        indent=2,
    )
)
