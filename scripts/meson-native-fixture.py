#!/usr/bin/env python3
"""Build dependency-tracked test fixtures; never build a bootstrap compiler."""

import argparse
import hashlib
from pathlib import Path
import subprocess


def escaped(path):
    return str(path).replace("\\", "\\\\").replace(" ", "\\ ").replace("#", "\\#").replace("$", "$$")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--module-root", required=True, type=Path)
    parser.add_argument("--object", required=True, type=Path)
    parser.add_argument("--depfile", required=True, type=Path)
    args = parser.parse_args()
    compiler = args.compiler.resolve(strict=True)
    before = hashlib.sha256(compiler.read_bytes()).hexdigest()
    assembly = args.object.with_suffix(".s")
    subprocess.run(
        [str(compiler), "--module-root", str(args.module_root), str(args.source), "-o", str(assembly)], check=True
    )
    subprocess.run(["as", "--64", str(assembly), "-o", str(args.object)], check=True)
    if hashlib.sha256(compiler.read_bytes()).hexdigest() != before:
        raise RuntimeError("Meson-selected compiler changed during fixture generation")
    # Conservative module-root dependencies include all current policy modules.
    # Editing an existing import first reruns this target and discovers new files.
    inputs = sorted({args.source.resolve(), Path(__file__).resolve(), *args.module_root.resolve().rglob("*.au")})
    args.depfile.write_text(escaped(args.object) + ": " + " ".join(map(escaped, inputs)) + "\n")
    print("Meson fixture used observed compiler SHA256 " + before + "; no fresh-build or acceptance claim")


if __name__ == "__main__":
    main()
