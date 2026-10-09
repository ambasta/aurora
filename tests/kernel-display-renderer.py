#!/usr/bin/env python3
"""Compile the actual Aurora page; compare independent pixels and untouched padding."""

from pathlib import Path
import os
import shlex
import subprocess
import sys
import tempfile
from kernel_display_oracle import reference

ROOT = Path(__file__).resolve().parents[1]


def main():
    compiler = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="aurora-display-renderer-") as temporary:
        work = Path(temporary)
        assembly, obj, binary = work / "page.s", work / "page.o", work / "page"
        subprocess.run(
            [
                str(compiler),
                "--module-root",
                str(ROOT / "library"),
                str(ROOT / "examples/kernel-display-service.au"),
                "-o",
                str(assembly),
            ],
            check=True,
        )
        subprocess.run(
            ["as", "--64", str(assembly), str(ROOT / "kernel/uefi/display-service-entry.S"), "-o", str(obj)], check=True
        )
        command = shlex.split(os.environ.get("CXX", "g++")) + [
            "-std=c++23",
            "-O1",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-no-pie",
            str(ROOT / "tests/kernel-display-renderer.cpp"),
            str(obj),
            "-o",
            str(binary),
        ]
        subprocess.run(command, check=True)
        cases = [(800, 600, 800, 1), (800, 600, 803, 0), (43, 40, 47, 1), (53, 199, 61, 0), (1024, 768, 1024, 0)]
        for width, height, pitch, fmt in cases:
            output = work / "pixels.bin"
            result = subprocess.run(
                [str(binary), str(width), str(height), str(pitch), str(fmt), str(output)],
                check=True,
                text=True,
                capture_output=True,
            )
            expected, stores = reference(width, height, pitch, fmt)
            actual = output.read_bytes()
            if actual != expected:
                mismatch = next(
                    (i for i, (a, b) in enumerate(zip(actual, expected)) if a != b), min(len(actual), len(expected))
                )
                raise AssertionError(f"Independent pixel mismatch for {width}x{height}/{pitch}/{fmt} at {mismatch}")
            if f"stores={stores} " not in result.stdout:
                raise AssertionError("Source store-count mismatch")
            print(result.stdout.strip(), f"geometry={width}x{height}/{pitch}/{fmt}")
        foreign = subprocess.run(
            [str(binary), "800", "600", "800", "1", str(work / "forbidden.bin"), "foreign-console"], check=False
        )
        if foreign.returncode != 77 or (work / "forbidden.bin").exists():
            raise AssertionError("Actual generated entry did not reject foreign Console grant before stores")
    print("PASS: actual Aurora renderer, five independent RGB/BGR/clip/padding oracles and foreign-grant rejection")


if __name__ == "__main__":
    main()
