#!/usr/bin/env python3
"""Native execution of private projection lifecycle and allocation controls."""

import argparse
from pathlib import Path

from owned_bytes import Suite, command
from unsigned_oracle import require


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("compiler", type=Path)
    parser.add_argument("module_root", type=Path)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    args.artifacts.mkdir(parents=True, exist_ok=True)
    suite = Suite(args.compiler, args.artifacts, args.module_root, entry_name="entry")
    executable = suite.compile("projection-lifecycle", Path(__file__).with_suffix(".au").read_text())
    checks = 0
    for mode in range(47):
        result = command([executable, 1 << 24, mode, 0])
        require(result.returncode == 0, f"mode {mode}: {result.stderr!r}")
        values = [int(word) for word in result.stdout.split()]
        require(values and values[0] == 0, f"mode {mode}: {values}")
        allocations = values[1]
        checks += 1
        for remaining in range(allocations):
            failed = command([executable, 1 << 24, mode, 0, remaining])
            require(failed.returncode == 0, f"failure {mode}/{remaining}: {failed.stderr!r}")
            observed = [int(word) for word in failed.stdout.split()]
            require(
                observed and (observed[0] == 100 or (mode >= 9 and observed[0] == 0)),
                f"failure {mode}/{remaining}: {observed}",
            )
            checks += 1
        exhausted = command([executable, 0, mode, 0])
        require(
            exhausted.returncode == 0 and exhausted.stdout.split()[0] == b"100",
            f"quota {mode}: {exhausted.stdout!r} {exhausted.stderr!r}",
        )
        checks += 1
    print(
        f"PASS {checks} projection lifecycle, sibling-allocation failure and quota controls; "
        "runtime checks complete cleanup"
    )


if __name__ == "__main__":
    main()
