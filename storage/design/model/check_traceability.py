#!/usr/bin/env python3
"""Checks package structure/provenance, not the semantic truth of requirements."""

from hashlib import sha256
from pathlib import Path
import argparse
import re
import sys


class ValidationError(Exception):
    pass


def check(condition, message):
    # Deliberately not assert: validation must remain active under python -O.
    if not condition:
        raise ValidationError(message)


def validate(root):
    original = (root / "original-requirements.md").read_bytes()
    check(len(original) == 26360, "input byte length changed")
    check(
        sha256(original).hexdigest() == "72ff3628f4d8043560c5a2055b507e4881178b29fc95a9212f6955804aa64bf6",
        "input hash changed",
    )
    titles = re.findall(r"^# (\d+)\. (.+)$", original.decode(), re.M)
    check([int(n) for n, _ in titles] == list(range(1, 57)), "source numbering")
    adapted = (root / "requirements.md").read_text()
    adapted_titles = re.findall(r"^## (\d+)\. (.+)$", adapted, re.M)
    check([int(n) for n, _ in adapted_titles] == list(range(1, 58)), "adapted numbering")
    check(adapted_titles[:56] == titles, "source section title correspondence")
    trace = (root / "traceability.md").read_text()
    rows = re.findall(r"^\| R(\d+) \| (\d+)\. (.*?) \| (.*?) \| (.*?) \|$", trace, re.M)
    check([int(n) for n, *_ in rows] == list(range(1, 57)), "trace numbering")
    roadmap = (root / "roadmap.md").read_text()
    stage_names = re.findall(r"^## ([SX]\d+)\.", roadmap, re.M)
    gates = set(stage_names)
    check(len(stage_names) == len(gates), "duplicated stage")
    check(gates == {f"S{i}" for i in range(12)} | {f"X{i}" for i in range(4)}, "stage inventory")
    for ident, number, title, detail, refs in rows:
        check(int(ident) == int(number), f"source identifier in R{ident}")
        check(title == dict(titles).get(number), f"source title in R{ident}")
        check(detail.startswith("§" + number + ". "), f"target section in R{ident}")
        check(set(refs.split(",")) <= gates, f"unknown gates in R{ident}")
    check(len(re.findall(r"^\| USER-XFS \|", trace, re.M)) == 1, "new XFS requirement")
    check(re.findall(r"^## (A\d+)\.", adapted, re.M) == [f"A{i}" for i in range(1, 9)], "Aurora contract numbering")
    check(
        "read-write" in adapted and "not a working filesystem" in (root / "README.md").read_text(),
        "implementation limitation missing",
    )
    for name in ("README.md", "requirements.md", "traceability.md", "roadmap.md", "sources.md"):
        text = (root / name).read_text()
        check("\ufffd" not in text, f"replacement character in {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="package root; tests pass disposable copies",
    )
    args = parser.parse_args()
    try:
        validate(args.root)
    except (ValidationError, OSError, UnicodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        (
            "PASS: original 26,360 bytes/hash; source sections 1..56; adapted 1..57; 56 trace rows + XFS; A1..A"
            "8; S0..S11 and X0..X3 references"
        )
    )
    print("This is structural/provenance validation, not semantic review or target filesystem evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
