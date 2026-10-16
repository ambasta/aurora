#!/usr/bin/env python3
"""Build dependency-tracked test fixtures; never build a bootstrap compiler."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from meson_aurora_assembly import dependencies, render_bridge


def escaped(path):
    return str(path).replace("\\", "\\\\").replace(" ", "\\ ").replace("#", "\\#").replace("$", "$$")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--module-root", required=True, action="append", type=Path)
    parser.add_argument("--bridge", action="append", default=[], type=Path)
    parser.add_argument("--local-symbols", action="store_true")
    parser.add_argument("--referenced-reflection-only", action="store_true")
    parser.add_argument("--object", required=True, type=Path)
    parser.add_argument("--depfile", required=True, type=Path)
    args = parser.parse_args()
    compiler = args.compiler.resolve(strict=True)
    before = hashlib.sha256(compiler.read_bytes()).hexdigest()
    assembly = args.object.with_suffix(".s")
    command = [str(compiler)]
    for root in args.module_root:
        command += ["--module-root", str(root)]
    if args.local_symbols:
        command.append("--local-symbols")
    if args.referenced_reflection_only:
        command.append("--referenced-reflection-only")
    abi = args.object.with_suffix(".abi.json")
    if args.bridge:
        command += ["--abi-facts", str(abi)]
    subprocess.run(command + [str(args.source), "-o", str(assembly)], check=True)
    if args.bridge:
        facts = json.loads(abi.read_text())
        with assembly.open("a") as output:
            for bridge in args.bridge:
                output.write("\n" + render_bridge(bridge.read_text(), facts))
    subprocess.run(["as", "--64", *(["-L"] if args.bridge else []), str(assembly), "-o", str(args.object)], check=True)
    if hashlib.sha256(compiler.read_bytes()).hexdigest() != before:
        raise RuntimeError("Meson-selected compiler changed during fixture generation")
    # Reuse image dependency discovery, which includes meson_aurora_assembly.py
    # itself and directories, so helper changes, added/removed imports and both
    # production bridge templates invalidate the fixture.
    inputs = sorted(
        {
            *dependencies(args.source, args.module_root),
            Path(__file__).resolve(),
            Path(__file__).with_name("bootstrap_frontend.py").resolve(),
            Path(__file__).with_name("frontend_bridge.py").resolve(),
            *(bridge.resolve() for bridge in args.bridge),
        }
    )
    args.depfile.write_text(escaped(args.object) + ": " + " ".join(map(escaped, inputs)) + "\n")
    print("Meson fixture used observed compiler SHA256 " + before + "; no fresh-build or acceptance claim")


if __name__ == "__main__":
    main()
