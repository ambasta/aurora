#!/usr/bin/env python3
"""Run every .air case file below the given directories (and any given generated
.air files) with aurora-ir-check.

Files are split across a process pool; each worker runs one driver process
over a batch of files. Any failing case fails the test.
"""

import argparse
import concurrent.futures
import os
from pathlib import Path
import subprocess
import sys


def run(driver, batch):
    result = subprocess.run([driver, *map(str, batch)], capture_output=True, text=True, timeout=300, check=False)
    return result.returncode, result.stdout + result.stderr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("driver")
    parser.add_argument("paths", nargs="+", type=Path, help="directories to search or .air files")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    args = parser.parse_args()
    files = sorted(file for path in args.paths for file in (path.rglob("*.air") if path.is_dir() else [path]))
    if not files:
        print("no .air files found", file=sys.stderr)
        return 1
    jobs = max(1, min(args.jobs, len(files)))
    batches = [files[index::jobs] for index in range(jobs)]
    failed = False
    cases = 0
    with concurrent.futures.ThreadPoolExecutor(jobs) as pool:
        for code, output in pool.map(lambda batch: run(args.driver, batch), batches):
            for line in output.splitlines():
                if line.startswith("PASS "):
                    cases += int(line.rsplit(": ", 1)[1].split()[0])
                else:
                    print(line)
            failed |= code != 0
    print(f"{'FAIL' if failed else 'PASS'}: {cases} cases in {len(files)} files")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
