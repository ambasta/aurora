#!/usr/bin/env python3
"""Build dependency-tracked test fixtures; never build a bootstrap compiler."""

import argparse
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
    parser.add_argument("--module-root", action="append", default=[], type=Path)
    parser.add_argument("--bridge", action="append", default=[], type=Path)
    parser.add_argument("--assemble-with", action="append", default=[], type=Path, help="extra assembly input")
    parser.add_argument("--defsym", action="append", default=[], help="assembler NAME=VALUE")
    parser.add_argument("--keep-local-labels", action="store_true", help="assemble with -L")
    parser.add_argument(
        "--localize-reflection",
        action="store_true",
        help="make reflection exports local, so separately compiled roots can share one hosted test link",
    )
    parser.add_argument("--local-symbols", action="store_true")
    parser.add_argument("--referenced-reflection-only", action="store_true")
    parser.add_argument("--object", required=True, type=Path)
    parser.add_argument("--depfile", required=True, type=Path)
    args = parser.parse_args()
    compiler = args.compiler.resolve(strict=True)
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
    extra = [str(path) for path in args.assemble_with]
    listing = ["-L"] if args.bridge or args.keep_local_labels else []
    defsyms = [part for definition in args.defsym for part in ("--defsym", definition)]
    subprocess.run(["as", "--64", *listing, *defsyms, str(assembly), *extra, "-o", str(args.object)], check=True)
    if args.localize_reflection:
        symbols = subprocess.run(
            ["nm", "-g", "--defined-only", str(args.object)], check=True, capture_output=True, text=True
        ).stdout
        names = [fields[2] for fields in map(str.split, symbols.splitlines()) if len(fields) == 3]
        names = [name for name in names if name.startswith(("aurora_reflect_", "__au_reflect_"))]
        if names:
            localized = args.object.with_suffix(".reflection")
            localized.write_text("".join(name + "\n" for name in names))
            subprocess.run(["objcopy", f"--localize-symbols={localized}", str(args.object)], check=True)
    # Reuse image dependency discovery, which includes meson_aurora_assembly.py
    # itself and directories, so helper changes, added/removed imports and both
    # production bridge templates invalidate the fixture.
    inputs = sorted(
        {
            *dependencies(args.source, args.module_root),
            Path(__file__).resolve(),
            Path(__file__).with_name("bootstrap_frontend.py").resolve(),
            Path(__file__).with_name("frontend_bridge.py").resolve(),
            *(bridge.resolve() for bridge in args.bridge + args.assemble_with),
        }
    )
    args.depfile.write_text(escaped(args.object) + ": " + " ".join(map(escaped, inputs)) + "\n")


if __name__ == "__main__":
    main()
