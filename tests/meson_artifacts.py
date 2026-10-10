#!/usr/bin/env python3
"""Give a runner fresh build-local scratch, retaining unsuccessful runs or explicit keeps."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    if len(sys.argv) < 2 or "@ARTIFACTS@" not in sys.argv[1:]:
        raise SystemExit("expected a command with an @ARTIFACTS@ output argument")
    parent = Path(tempfile.mkdtemp(prefix="aurora-meson-"))
    command = [str(parent / "output") if value == "@ARTIFACTS@" else value for value in sys.argv[1:]]
    print("Artifacts: " + str(parent), flush=True)
    result = None
    try:
        result = subprocess.call(command)
    finally:
        if result == 0 and os.environ.get("AURORA_MESON_KEEP_ARTIFACTS") != "1":
            try:
                shutil.rmtree(parent)
            except OSError as error:
                print("Artifact cleanup incomplete: " + str(parent) + ": " + str(error), file=sys.stderr, flush=True)
            else:
                print("Removed artifacts: " + str(parent), flush=True)
        else:
            print("Retained artifacts: " + str(parent), flush=True)
    raise SystemExit(result)


if __name__ == "__main__":
    main()
