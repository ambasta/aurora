#!/usr/bin/env python3
"""Owned-byte object boundary controls and CLI; production helper is in scripts."""

from pathlib import Path
import importlib.util
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("owned_admission", ROOT / "scripts/kernel_owned_bytes_admission.py")
admission = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = admission
spec.loader.exec_module(admission)
RUNTIME = admission.RUNTIME
GENERATED = admission.GENERATED
DEFINITIONS = admission.DEFINITIONS
mangle = admission.mangle
validate_symbols = admission.validate_symbols


def self_test():
    rows = ["U " + name for name in sorted(RUNTIME)]
    rows += ["0 " + kind + " " + name for name, kind in DEFINITIONS.items()]
    text = "\n".join(rows)
    validate_symbols(text)
    rejected = 0
    mutants = ["\n".join(rows[:i] + rows[i + 1 :]) for i in range(len(rows))]
    mutants += [text + "\nU " + name for name in ("__au_runtime_bytes_unknown", "malloc", "unknown_helper")]
    mutants += [
        text + "\n0 T " + name
        for name in (*sorted(RUNTIME), "__au_runtime_bytes_resize", "aurora_kernel_value", "malloc")
    ]
    mutants += [text.replace("0 t " + name, "0 T " + name) for name in GENERATED.values()]
    mutants += [text + "\n0 t " + mangle("m", "storage.unauthorized", "storage::RamSectorDevice", "unknown")]
    mutants += [text + "\n0 T __au_reflect_s8_size"]
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
        print("PASS: dedicated owned-byte object has only six admitted runtime imports")
    else:
        raise SystemExit("Expected language.o or --self-test")
