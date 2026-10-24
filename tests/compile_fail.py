#!/usr/bin/env python3
"""Every line of CASES is one C++ translation unit that must not compile.

    compile_fail.py CASES ROOT -- CXX...

A case line is `expected diagnostic<TAB>compiler arguments<TAB>code`, `\\n` separating lines.
The code is compiled from stdin with `CXX -std=c++23 -fsyntax-only -Wfatal-errors
-I ROOT`; it must fail and print the expected diagnostic. Cases run concurrently.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shlex
import subprocess
import sys

ENVIRONMENT = dict(os.environ, LC_ALL="C")  # ASCII quotes in diagnostics


def check(compiler, root, line):
    message, arguments, code = line.split("\t")
    code = code.replace("\\n", "\n")
    argv = [*compiler, "-std=c++23", "-fsyntax-only", "-Wfatal-errors", "-I", root, *shlex.split(arguments)]
    result = subprocess.run(
        [*argv, "-x", "c++", "-"], input=code + "\n", capture_output=True, text=True, timeout=120, env=ENVIRONMENT
    )
    if result.returncode != 0 and message in result.stderr:
        return None
    return f"{arguments} {code!r}: exit {result.returncode}, expected {message!r}\n{result.stderr[-2000:]}"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cases", type=Path)
    parser.add_argument("root")
    parser.add_argument("compiler", nargs="+")
    args = parser.parse_args()
    lines = [line for line in args.cases.read_text().splitlines() if line and not line.startswith("#")]
    with ThreadPoolExecutor(len(os.sched_getaffinity(0))) as pool:
        failures = [
            failure for failure in pool.map(lambda line: check(args.compiler, args.root, line), lines) if failure
        ]
    for failure in failures:
        print("FAIL", failure)
    if failures:
        sys.exit(1)
    print(f"PASS {args.cases.name}: {len(lines)} rejected configurations")


if __name__ == "__main__":
    main()
