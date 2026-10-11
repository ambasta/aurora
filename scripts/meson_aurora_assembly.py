#!/usr/bin/env python3
"""Emit one Aurora assembly input and its conservative module dependencies."""

import argparse
import json
import re
import sys
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


def render_bridge(source, facts):
    # Source spellings select compiler facts, never a second mangling recipe.
    from bootstrap_frontend import abi_function_symbol

    def symbol(match):
        value = abi_function_symbol(facts, match[1])
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", value):
            raise ValueError("Unsupported compiler symbol in private bridge")
        return value

    return re.sub(r"@([A-Za-z_][A-Za-z_0-9:]*)@", symbol, source)


def main():
    if sys.argv[1:2] == ["--render-bridge"]:
        facts, source, output = map(Path, sys.argv[2:])
        output.write_text(render_bridge(source.read_text(), json.loads(facts.read_text())))
        return

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--module-root", action="append", default=[], type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--depfile", required=True, type=Path)
    parser.add_argument("--stack-facts", type=Path)
    parser.add_argument("--abi-facts", type=Path)
    parser.add_argument("--bridge", type=Path, action="append", default=[])
    parser.add_argument("--referenced-reflection-only", action="store_true")
    parser.add_argument("--local-symbols", action="store_true")
    args = parser.parse_args()
    if args.bridge and not args.abi_facts:
        parser.error("--bridge requires --abi-facts")
    inputs = dependencies(args.source, args.module_root)
    inputs += [bridge.absolute() for bridge in args.bridge]
    inputs += [Path(__file__).with_name("bootstrap_frontend.py")]
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
    pending_abi = args.abi_facts.with_suffix(".pending.json") if args.abi_facts else None
    if pending_abi:
        command += ["--abi-facts", str(pending_abi)]
    subprocess.run(command, check=True)
    if pending_abi:
        facts = json.loads(pending_abi.read_text())
        with temporary.open("a") as output:
            for bridge in args.bridge:
                output.write("\n" + render_bridge(bridge.read_text(), facts))
    # A successful command must produce the complete declared pair before any
    # previously admitted assembly/facts/dependencies are replaced.
    temporary.stat()
    if pending_facts:
        pending_facts.stat()
        pending_facts.replace(args.stack_facts)
    if pending_abi:
        pending_abi.replace(args.abi_facts)
    args.depfile.write_text(escaped(args.output) + ": " + " ".join(map(escaped, inputs)) + "\n")
    temporary.replace(args.output)


if __name__ == "__main__":
    main()
