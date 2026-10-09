#!/usr/bin/env python3
"""Give an existing artifact-managed runner a fresh build-local output directory."""

from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    if len(sys.argv) < 2 or '@ARTIFACTS@' not in sys.argv[1:]:
        raise SystemExit('expected a command with an @ARTIFACTS@ output argument')
    parent = Path(tempfile.mkdtemp(prefix='aurora-meson-'))
    command = [str(parent / 'output') if value == '@ARTIFACTS@' else value for value in sys.argv[1:]]
    print('Retained artifacts: ' + str(parent), flush=True)
    raise SystemExit(subprocess.call(command))


if __name__ == '__main__':
    main()
