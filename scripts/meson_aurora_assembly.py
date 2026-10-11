#!/usr/bin/env python3
"""Emit one Aurora assembly input and its conservative module dependencies."""

import argparse
from pathlib import Path
import subprocess


def escaped(path):
    value = str(path)
    if "\n" in value or "\r" in value:
        raise ValueError("Dependency paths cannot contain line breaks")
    return value.replace("\\", "\\\\").replace(" ", "\\ ").replace("#", "\\#").replace("$", "$$").replace(":", "\\:")


def dependencies(source, roots):
    # Directory mtimes discover added/removed modules, including a new ambiguous
    # candidate. Existing modules and directories retain their full identities.
    paths = {source.absolute(), Path(__file__).resolve()}
    for root in roots:
        root = root.absolute()
        paths.add(root)
        for path in root.rglob("*"):
            if path.is_dir() or path.suffix == ".au":
                paths.add(path)
    return sorted(paths)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--module-root", action="append", default=[], type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--depfile", required=True, type=Path)
    parser.add_argument("--stack-facts", type=Path)
    parser.add_argument("--referenced-reflection-only", action="store_true")
    parser.add_argument("--local-symbols", action="store_true")
    args = parser.parse_args()
    inputs = dependencies(args.source, args.module_root)
    temporary = args.output.with_suffix(".pending.s")
    command = [str(args.compiler.resolve(strict=True))]
    if args.referenced_reflection_only:
        command.append("--referenced-reflection-only")
    if args.local_symbols:
        command.append("--local-symbols")
    for root in args.module_root:
        command += ["--module-root", str(root.absolute())]
    command += [str(args.source.absolute()), "-o", str(temporary)]
    pending_facts = args.stack_facts.with_suffix(".pending.json") if args.stack_facts else None
    if pending_facts:
        command += ["--stack-facts", str(pending_facts)]
    subprocess.run(command, check=True)
    # A successful command must produce the complete declared pair before any
    # previously admitted assembly/facts/dependencies are replaced.
    temporary.stat()
    if pending_facts:
        pending_facts.stat()
        pending_facts.replace(args.stack_facts)
    args.depfile.write_text(escaped(args.output) + ": " + " ".join(map(escaped, inputs)) + "\n")
    temporary.replace(args.output)


if __name__ == "__main__":
    main()
