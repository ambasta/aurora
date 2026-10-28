#!/usr/bin/env python3
"""Compare two aurorac builds on a fixed set of inputs.

Usage: scripts/compiler-speed.py BEFORE AFTER [--repeat N] [--referenced-reflection-only]

Reports the best wall time and child CPU time of N runs per input and compiler,
their ratios and maximum observed child peak RSS, and fails if the two compilers
produce different output. RSS uses wait4's platform units (KiB on Linux, bytes on
macOS); it is not necessarily the sample with the best wall/CPU time. Run it
before and after a compiler change and record the result with the change; the
host load matters, so compare builds on the same machine at the same time.
The optional referenced-reflection mode applies the same existing compiler flag
to both builds; exact output equality remains mandatory. It permits comparisons
across builtin catalogue additions without benchmarking unused reflection tables.
"""

import argparse
import math
import os
from pathlib import Path
import sys
import tempfile
import time

from bootstrap_frontend import stage_modules

ROOT = Path(__file__).resolve().parents[1]
INPUTS = (
    ("library/std/json.au", ("library",)),
    ("library/fs/xfs_sector.au", ("library",)),
    ("library/console/session_files.au", ("library",)),
    ("library/package/graph.au", ("library",)),
    ("examples/kernel-graphical-console.au", ("library", "kernel/policies")),
    ("compiler/aurorac.au", None),
)


def measure(compiler, source, roots, output, repeat, compiler_flags=()):
    # The compiler itself: its modules, staged, and this tree's runtime root.
    if roots and roots[0].name == "modules":
        compiler_flags = [*compiler_flags, "--runtime-root", str(ROOT / "runtime/linux")]
    best_wall = best_cpu = math.inf
    peak_rss = 0
    for _ in range(repeat):
        start = time.perf_counter()
        pid = os.fork()
        if pid == 0:
            arguments = [arg for root in roots for arg in ("--module-root", str(root))]
            os.execv(compiler, [compiler, *compiler_flags, *arguments, str(source), "-o", str(output)])
        _, status, usage = os.wait4(pid, 0)
        if os.waitstatus_to_exitcode(status) != 0:
            sys.exit(f"{compiler} failed on {source}")
        best_wall = min(best_wall, time.perf_counter() - start)
        best_cpu = min(best_cpu, usage.ru_utime + usage.ru_stime)
        peak_rss = max(peak_rss, usage.ru_maxrss)
    return best_wall, best_cpu, peak_rss


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--referenced-reflection-only", action="store_true")
    args = parser.parse_args()
    compiler_flags = ["--referenced-reflection-only"] if args.referenced_reflection_only else []
    print("Compiler flags:", " ".join(compiler_flags) or "(default)")
    with tempfile.TemporaryDirectory(prefix="aurora-compiler-speed-") as temporary:
        work = Path(temporary)
        stage_modules(
            work / "modules",
            [
                *(path for path in (ROOT / "compiler").glob("*.au") if path.name != "aurorac.au"),
                ROOT / "library/std/decimal_digits.au",
                ROOT / "library/std/binary.au",
            ],
        )
        ratios = []
        rss_unit = {"linux": "KiB", "darwin": "bytes"}.get(sys.platform, "platform units")
        print(f"Peak RSS: maximum per-child wait4 ru_maxrss in {rss_unit} on {sys.platform}")
        print(
            f"{'input':42} {'before ms':>10} {'after ms':>10} {'wall':>6} {'cpu':>6} "
            f"{'before RSS':>12} {'after RSS':>12}"
        )
        for name, roots in INPUTS:
            roots = [work / "modules"] if roots is None else [ROOT / root for root in roots]
            results = []
            for label, compiler in (("before", args.before), ("after", args.after)):
                output = work / f"{label}.s"
                results.append(
                    (
                        measure(
                            str(compiler.resolve()),
                            ROOT / name,
                            roots,
                            output,
                            args.repeat,
                            compiler_flags,
                        ),
                        output,
                    )
                )
            (before, before_output), (after, after_output) = results
            if before_output.read_bytes() != after_output.read_bytes():
                sys.exit(f"FAIL: {name} compiles differently")
            ratios.append(after[1] / before[1])
            print(
                f"{name:42} {before[0] * 1000:10.0f} {after[0] * 1000:10.0f} "
                f"{after[0] / before[0]:5.2f}x {after[1] / before[1]:5.2f}x {before[2]:12} {after[2]:12}"
            )
        mean = math.exp(sum(math.log(ratio) for ratio in ratios) / len(ratios))
        print(f"geometric mean CPU ratio: {mean:.2f}x; outputs identical")


if __name__ == "__main__":
    main()
