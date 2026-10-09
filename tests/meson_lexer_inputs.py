#!/usr/bin/env python3
"""Run the lexer fixture against every source in the original Make glob roots."""
from pathlib import Path
import subprocess
import sys

fixture, root = sys.argv[1], Path(sys.argv[2])
inputs = sorted(str(path) for name in ('examples', 'library/examples', 'library/std')
                for path in (root / name).glob('*.au'))
if not inputs:
    raise SystemExit('lexer source inventory is empty')
raise SystemExit(subprocess.call([fixture, *inputs]))
