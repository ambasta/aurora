#!/usr/bin/env python3
"""Run hosted HostFiles programs over their golden cases.

    host_files.py GOLDEN [--update] -- NAME=EXECUTABLE...

Each `case<TAB>result` line of GOLDEN names a program and its arguments. The
program runs in a fresh fixture directory holding `tree/` (regular files, a
subdirectory, a symlink, a directory symlink and a FIFO); the result is the
exit status, stdout and stderr as in golden.py, then the sorted entries of
`tree/` afterwards, so committed and discarded outputs and leftover
temporaries are visible. Cases run concurrently.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from golden import compare, flat  # noqa: E402


def fixture(root):
    tree = root / "tree"
    (tree / "sub").mkdir(parents=True)
    (tree / "a.txt").write_bytes(b"alpha\n")
    (tree / "sub" / "b.txt").write_bytes(b"beta beta\n")
    (tree / "big.txt").write_bytes(bytes(48 + i % 75 for i in range(1500)))
    (tree / "empty.txt").write_bytes(b"")
    (tree / "link").symlink_to("a.txt")
    (tree / "dirlink").symlink_to("sub", target_is_directory=True)
    os.mkfifo(tree / "fifo")


def run(programs, case, timeout):
    words = shlex.split(case)
    with tempfile.TemporaryDirectory(prefix="aurora-host-files-") as directory:
        root = Path(directory)
        fixture(root)
        try:
            result = subprocess.run(
                [programs[words[0]], *words[1:]], cwd=root, capture_output=True, timeout=timeout, check=False
            )
        except subprocess.TimeoutExpired:
            return f"timeout after {timeout}s"
        status = f"signal {-result.returncode}" if result.returncode < 0 else f"exit {result.returncode}"
        text = [status]
        if result.stdout:
            text.append("stdout: " + flat(result.stdout))
        if result.stderr:
            text.append("stderr: " + flat(result.stderr))
        text.append("tree: " + " ".join(sorted(path.name for path in (root / "tree").iterdir())))
        return " | ".join(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("golden", type=Path)
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("programs", nargs="+")
    args = parser.parse_args()
    programs = dict(item.split("=", 1) for item in args.programs)
    cases = [line.split("\t", 1)[0] for line in args.golden.read_text().splitlines()]
    with ThreadPoolExecutor(min(16, len(os.sched_getaffinity(0)) * 2)) as pool:
        results = list(pool.map(lambda case: run(programs, case, args.timeout), cases))
    compare(args.golden, [f"{case}\t{result}" for case, result in zip(cases, results)], args.update)


if __name__ == "__main__":
    main()
