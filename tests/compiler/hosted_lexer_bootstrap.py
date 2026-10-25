#!/usr/bin/env python3
"""Stage compare: the frontend C1 emitted (B) and the one C2 emitted (C) are identical.

Like GCC's compare-stage, both outputs are build products; this only compares
them. The host C++ objects are compiled once against header A and reused by
C2, so the generated headers of A, B and C must also agree.
"""

from pathlib import Path
import subprocess
import sys

SUFFIXES = (".o", ".generated.o", ".abi.json", ".stack.json")


def header(unit):
    return unit.parent / (unit.stem.replace("-", "_") + "_abi.hpp")


def exported(obj):
    rows = subprocess.run(
        ["nm", "--defined-only", "--extern-only", "--format=posix", str(obj)], capture_output=True, check=True
    ).stdout.decode()
    return [row.split()[0] for row in rows.splitlines()]


def main():
    built_a, built_b, built_c = (Path(value).resolve() for value in sys.argv[1:])
    failures = [
        f"{built_b.name} and {built_c.name} differ in {suffix}"
        for suffix in SUFFIXES
        if built_b.with_suffix(suffix).read_bytes() != built_c.with_suffix(suffix).read_bytes()
    ]
    if not header(built_a).read_bytes() == header(built_b).read_bytes() == header(built_c).read_bytes():
        failures.append("generated ABI headers of A, B and C differ")
    leaked = [name for name in exported(built_b) if not name.startswith("aurora_hosted_")]
    if leaked:
        failures.append(f"frontend exports generated symbols: {leaked[:5]}")
    if failures:
        sys.exit("FAIL " + "; ".join(failures))
    print("PASS frontend B/C stage compare")


if __name__ == "__main__":
    main()
