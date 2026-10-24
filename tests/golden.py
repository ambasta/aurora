#!/usr/bin/env python3
"""Compare a prebuilt test driver's observations with the reviewed golden file beside it.

    golden.py GOLDEN -- COMMAND...           stdout of COMMAND is GOLDEN, byte for byte
    golden.py GOLDEN --modes -- COMMAND...   each `mode<TAB>result` line runs `COMMAND mode`
                                             (the mode split into arguments)
    golden.py GOLDEN --reject -- AURORAC...  each `"source"<TAB>diagnostic` line is one
                                             rejected Aurora source (a JSON string)

A mode result is the exit status or terminating signal, then stdout and stderr
(one line each, newlines shown as ` / `). A rejection compiles the source alone
with `AURORAC... case.au -o case.s` (or without `-o` under --check) and must
exit 1 with diagnostics, creating no output and leaving an existing one
unchanged; the result is the diagnostic text with the scratch path removed.
Lines run concurrently. `--update` rewrites the result column (or the whole
file) for an intended, reviewed change.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile


def flat(data):
    return data.decode(errors="replace").strip().replace("\n", " / ")


def observe(argv, timeout):
    try:
        result = subprocess.run(argv, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return f"timeout after {timeout}s"
    status = (
        f"signal {signal.Signals(-result.returncode).name}" if result.returncode < 0 else f"exit {result.returncode}"
    )
    text = [status]
    if result.stdout:
        text.append("stdout: " + flat(result.stdout))
    if result.stderr:
        text.append("stderr: " + flat(result.stderr))
    return " | ".join(text)


def reject(compiler, directory, index, source, timeout):
    path = Path(directory) / f"case-{index:04d}.au"
    path.write_text(source)
    output = path.with_suffix(".s")
    # Alternate absent and existing outputs: a rejection neither publishes nor changes one.
    existing = b"existing output must survive a rejection\n" if index % 2 and "--check" not in compiler else None
    if existing:
        output.write_bytes(existing)
    argv = [*compiler, str(path)] + ([] if "--check" in compiler else ["-o", str(output)])
    try:
        result = subprocess.run(argv, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return f"timeout after {timeout}s"
    diagnostic = flat(result.stderr).replace(f"{path}:", "")
    published = output.read_bytes() != existing if existing else output.exists()
    if result.returncode != 1 or published or result.stdout or not diagnostic:
        return f"exit {result.returncode} output-changed={published} stdout={result.stdout!r} {diagnostic}"
    return diagnostic


def compare(golden, observed, update=False):
    """Fail with the first differing lines unless `observed` equals the golden file's lines."""
    if update:
        golden.write_text("".join(line + "\n" for line in observed))
        print(f"UPDATED {golden}: {len(observed)} lines")
        return
    expected = golden.read_text().splitlines() if golden.exists() else []
    differences = [(index, want, got) for index, (want, got) in enumerate(zip(expected, observed)) if want != got]
    if differences or len(expected) != len(observed):
        print(
            f"FAIL {golden.name}: {len(differences)} differing lines,"
            f" {len(observed)} observed vs {len(expected)} golden"
        )
        for index, want, got in differences[:30]:
            print(f"  line {index + 1}:\n    expected {want}\n    observed {got}")
        sys.exit(1)
    print(f"PASS {golden.name}: {len(observed)} lines")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("golden", type=Path)
    kind = parser.add_mutually_exclusive_group()
    kind.add_argument("--modes", action="store_true")
    kind.add_argument("--reject", action="store_true")
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--update", action="store_true")
    parser.add_argument("command", nargs="+")
    args = parser.parse_args()
    if args.modes or args.reject:
        keys = [line.split("\t", 1)[0] for line in args.golden.read_text().splitlines()]
        workers = min(32, len(os.sched_getaffinity(0)) * 2)
        with tempfile.TemporaryDirectory(prefix="aurora-golden-") as directory, ThreadPoolExecutor(workers) as pool:
            if args.modes:
                jobs = [pool.submit(observe, [*args.command, *shlex.split(key)], args.timeout) for key in keys]
            else:
                jobs = [
                    pool.submit(reject, args.command, directory, index, json.loads(key), args.timeout)
                    for index, key in enumerate(keys)
                ]
            observed = [f"{key}\t{job.result()}" for key, job in zip(keys, jobs)]
    else:
        result = subprocess.run(args.command, capture_output=True, timeout=args.timeout, check=False)
        if result.returncode != 0 or result.stderr:
            sys.exit(f"FAIL {args.golden.name}: {observe(args.command, args.timeout)}")
        observed = result.stdout.decode().splitlines()
    compare(args.golden, observed, args.update)


if __name__ == "__main__":
    main()
