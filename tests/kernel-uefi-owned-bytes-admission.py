#!/usr/bin/env python3
"""Closed object-import boundary for the dedicated kernel owned-byte profile."""

from pathlib import Path
import subprocess
import sys

RUNTIME = frozenset("__au_runtime_bytes_" + name for name in ("allocate", "at", "set", "drop", "borrow_length"))
ENTRY = "__au_v_m1_18kernel_owned_bytes_n0__d24kernel_owned_bytes_entry"
CONSUMER = "__au_v_m1_18kernel_owned_bytes_n0__d13consume_bytes"
TRANSFER = "__au_v_m1_18kernel_owned_bytes_n0__d10pass_bytes"
DEFINITIONS = {
    ENTRY: "t",
    TRANSFER: "t",
    CONSUMER: "t",
    "__au_runtime_bytes_kernel_entry": "T",
    "aurora_reflect_size": "T",
    "aurora_reflect_field_count": "T",
}


def validate_symbols(text):
    imports = set()
    definitions = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[0] == "U":
            if fields[1] in imports:
                raise ValueError("Duplicate undefined symbol")
            imports.add(fields[1])
        elif len(fields) == 3 and len(fields[1]) == 1:
            int(fields[0], 16)
            if fields[2] in definitions:
                raise ValueError("Duplicate defined symbol")
            definitions[fields[2]] = fields[1]
        else:
            raise ValueError("Unrecognized object symbol row")
    unsupported = imports - RUNTIME
    if unsupported:
        raise ValueError("Unsupported kernel owned-byte runtime import: " + ", ".join(sorted(unsupported)))
    if imports != RUNTIME:
        raise ValueError("Dedicated owned-byte profile must exercise all five admitted runtime operations")
    if definitions != DEFINITIONS:
        raise ValueError("Unexpected dedicated owned-byte graph definitions or visibility")
    return dict(imports=sorted(imports), definitions=definitions)


def self_test():
    rows = ["U " + name for name in sorted(RUNTIME)]
    rows += ["0 " + kind + " " + name for name, kind in DEFINITIONS.items()]
    text = "\n".join(rows)
    validate_symbols(text)
    rejected = 0
    mutants = ["\n".join(rows[:i] + rows[i + 1 :]) for i in range(len(rows))]
    mutants += [text + "\nU " + name for name in ("__au_runtime_bytes_resize", "malloc", "unknown_helper")]
    mutants += [
        text + "\n0 T " + name
        for name in (*sorted(RUNTIME), "__au_runtime_bytes_resize", "aurora_kernel_value", "malloc")
    ]
    mutants += [text.replace("0 t " + name, "0 T " + name) for name in (ENTRY, TRANSFER, CONSUMER)]
    mutants += [text + "\n" + rows[0], text + "\n" + rows[-1], text + "\nmalformed"]
    for candidate in mutants:
        try:
            validate_symbols(candidate)
        except ValueError:
            rejected += 1
        else:
            raise RuntimeError("Unsupported graph/import mutation accepted")
    print(f"PASS: owned-byte object admission, 1 positive and {rejected} negative controls")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    elif len(sys.argv) == 2:
        symbols = subprocess.check_output(["nm", "-a", str(Path(sys.argv[1]))], text=True)
        validate_symbols(symbols)
        print("PASS: dedicated owned-byte object has only five admitted runtime imports")
    else:
        raise SystemExit("Expected language.o or --self-test")
