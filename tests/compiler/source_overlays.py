#!/usr/bin/env python3
"""Run the existing-file snapshot overlay gate inside a fresh fixture directory."""

from pathlib import Path
import subprocess
import sys
import tempfile

with tempfile.TemporaryDirectory(prefix="aurora-source-overlays-") as directory:
    result = subprocess.run([str(Path(sys.argv[1]).resolve()), directory], timeout=30)
    raise SystemExit(result.returncode)
