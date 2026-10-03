#!/usr/bin/env python3
"""Run native descriptor-race checks only within an owned disposable fixture tree."""
from pathlib import Path
import subprocess
import sys
import tempfile
with tempfile.TemporaryDirectory(prefix="aurora-source-capability-") as directory:
    subprocess.run([str(Path(sys.argv[1]).resolve()), directory], check=True, timeout=15)
