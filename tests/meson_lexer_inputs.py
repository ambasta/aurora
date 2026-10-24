#!/usr/bin/env python3
"""Run a source fixture on its legacy roots or all checked-in Aurora source roots."""

from pathlib import Path
import subprocess
import sys

fixture, root = sys.argv[1], Path(sys.argv[2])
# Digest-pinned byte copies of earlier compiler sources, kept only as emitter
# differential inputs (tests/compiler/emitter_differential.py); lexed as originals.
FROZEN = root / "tests/fixtures/emitter-history/compiler-d4cbabb"
if len(sys.argv) == 5 and sys.argv[3] == "--all":
    inputs = sorted(
        str(path)
        for name in ("compiler", "examples", "kernel", "library", "tests")
        for path in (root / name).rglob("*.au")
        if FROZEN not in path.parents
    )
    generated = Path(sys.argv[4])
    if not generated.is_file():
        raise SystemExit("generated frontend is missing")
    inputs.append(str(generated))
elif len(sys.argv) == 3:
    inputs = sorted(
        str(path) for name in ("examples", "library/examples", "library/std") for path in (root / name).glob("*.au")
    )
else:
    raise SystemExit("expected fixture, root, and optional --all GENERATED_FRONTEND")
if not inputs:
    raise SystemExit("lexer source inventory is empty")
raise SystemExit(subprocess.call([fixture, *inputs]))
