#!/usr/bin/env python3
"""Reject Python assert statements, so each harness behaves the same under -O.

Runners execute once, with or without -O; an assert would silently vanish in
optimized runs. Use an explicit check that raises instead.
"""

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
# Byte-pinned historical evidence; its recorded digests must not change.
FROZEN = ROOT / "tests/iommu/fixtures"
SKIPPED = {"build", ".git", "__pycache__"}


def sources(root):
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        if SKIPPED.intersection(relative.parts) or path.is_relative_to(FROZEN):
            continue
        yield path


def assertions(path):
    tree = ast.parse(path.read_text(), str(path))
    return [node.lineno for node in ast.walk(tree) if isinstance(node, ast.Assert)]


def main():
    found = [(path, line) for path in sources(ROOT) for line in assertions(path)]
    for path, line in found:
        print(f"{path.relative_to(ROOT)}:{line}: assert is removed by python -O; raise explicitly", file=sys.stderr)
    if found:
        return 1
    print("PASS: no Python assert statements outside frozen fixtures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
