#!/usr/bin/env python3
"""Run hosted HostFiles programs over their golden cases.

    host_files.py GOLDEN [--update] -- NAME=EXECUTABLE...

Each `case<TAB>result` line of GOLDEN names a program and its arguments. The
program runs in a fresh fixture directory holding `tree/` (regular files, a
subdirectory, a symlink, a directory symlink and a FIFO); the result is the
exit status, stdout and stderr as in golden.py, then the sorted entries of
`tree/` afterwards with the size of each regular file, so committed and
discarded outputs and leftover temporaries are visible. A case starting with
`!closed` runs with stdout closed. Cases run concurrently.
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


# The fixture's regular files, which the Aurora kernel's boot volume also
# carries under tree/ (scripts/kernel_volume.py --host-files-tree).
TREE = {
    "a.txt": b"alpha\n",
    "sub/b.txt": b"beta beta\n",
    "big.txt": bytes(48 + i % 75 for i in range(1500)),
    "empty.txt": b"",
}


def fixture(root):
    tree = root / "tree"
    (tree / "sub").mkdir(parents=True)
    for path, content in TREE.items():
        (tree / path).write_bytes(content)
    (tree / "link").symlink_to("a.txt")
    (tree / "dirlink").symlink_to("sub", target_is_directory=True)
    os.mkfifo(tree / "fifo")


def enumeration_fixture(root):
    """Real Linux directory records, isolated from the ordinary golden tree."""
    directory = root / "enumeration"
    for name in ("many", "hidden", "private", "raw", "long", "empty"):
        (directory / name).mkdir(parents=True)
    for index in range(20):
        (directory / "many" / f"r{index:02}").write_bytes(b"")
    for index in range(130):
        (directory / "hidden" / f".aurora-output-{index:03}").write_bytes(b"")
    for name in (".aurora-stage", ".aurora-output-secret", ".visible", ".aurora-stagex"):
        (directory / "private" / name).write_bytes(b"")
    (directory / "long" / ("n" * 255)).write_bytes(b"")
    descriptor = os.open(os.fsencode(directory / "raw") + b"/\xffraw", os.O_CREAT | os.O_WRONLY, 0o600)
    os.close(descriptor)


def entry(path):
    if path.is_symlink() or not path.is_file():
        return path.name
    return f"{path.name}:{path.stat().st_size}"


def run(programs, case, timeout):
    words = shlex.split(case)
    enumeration = words[0] == "!enumeration"
    if enumeration:
        words = words[1:]
    closed = words[0] == "!closed"
    if closed:
        words = words[1:]
    with tempfile.TemporaryDirectory(prefix="aurora-host-files-") as directory:
        root = Path(directory)
        fixture(root)
        if enumeration:
            enumeration_fixture(root)
        try:
            argv = [programs[words[0]], *words[1:]]
            if closed:
                argv = ["/bin/sh", "-c", 'exec "$0" "$@" >&-', *argv]
            result = subprocess.run(argv, cwd=root, capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            return f"timeout after {timeout}s"
        status = f"signal {-result.returncode}" if result.returncode < 0 else f"exit {result.returncode}"
        text = [status]
        if result.stdout:
            text.append("stdout: " + flat(result.stdout))
        if result.stderr:
            text.append("stderr: " + flat(result.stderr))
        entries = sorted((root / "tree").iterdir())
        text.append("tree: " + " ".join(entry(path) for path in entries))
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
