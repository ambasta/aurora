#!/usr/bin/env python3
"""Run a source fixture on its legacy roots or all checked-in Aurora source roots."""

from pathlib import Path
import subprocess
import sys

fixture, root = sys.argv[1], Path(sys.argv[2])
if sys.argv[3:] == ["--all"]:
    inputs = sorted(
        str(path)
        for name in ("compiler", "examples", "kernel", "library", "tests")
        for path in (root / name).rglob("*.au")
    )
elif len(sys.argv) == 3:
    inputs = sorted(
        str(path) for name in ("examples", "library/examples", "library/std") for path in (root / name).glob("*.au")
    )
else:
    raise SystemExit("expected fixture, root, and optional --all")
if not inputs:
    raise SystemExit("lexer source inventory is empty")
raise SystemExit(subprocess.call([fixture, *inputs]))
