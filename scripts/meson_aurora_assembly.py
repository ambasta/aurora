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


def validate_uart_policy_abi(facts):
    """Check every byte of the fixed native UART record against compiler facts."""
    from bootstrap_frontend import abi_declaration, normalize_function_abi

    record_symbol, record = abi_declaration(facts, "records", "kernel::UartTransfer")
    fields = [
        ("receive_error", "bool"),
        ("trigger", "u64"),
        ("value", "u64"),
        ("present", "bool"),
        ("damaged", "bool"),
        ("success", "bool"),
    ]
    expected_record = {
        "source_name": "kernel::UartTransfer",
        "size": 48,
        "alignment": 8,
        "reserved": 48,
        "fields": [
            {"name": name, "offset": 8 * index, "bytes": 8, "array_length": 0, "kind": kind}
            for index, (name, kind) in enumerate(fields)
        ],
    }
    if record != expected_record:
        raise ValueError("UART copied transfer layout does not match compiler facts")
    roots = {
        "kind": "none",
        "register": None,
        "tuple_payload_bytes": 0,
        "tuple_reserved_bytes": 0,
        "saved_root_reserved_bytes": 0,
    }
    for name in ("uart_initialize", "uart_next", "uart_put"):
        _, raw = abi_declaration(facts, "functions", name)
        function = normalize_function_abi(facts, raw)
        parameters = [
            {"offset": 0, "bytes": 16, "kind": "service", "type_name": "builtin::Com1UartGrant"},
            {"offset": 16, "bytes": 48, "kind": "class", "type_name": record_symbol},
        ]
        if name == "uart_put":
            parameters.append({"offset": 64, "bytes": 8, "kind": "u8"})
        expected = {
            "source_name": name,
            "receiver": None,
            "receiver_mutable": None,
            "borrowed_root_count": 0,
            "borrowed_roots": [],
            "borrowed_root_abi": roots,
            "parameter_bytes": 72 if name == "uart_put" else 64,
            "parameters": parameters,
            "result": {"bytes": 48, "kind": "class", "type_name": record_symbol},
        }
        if function != expected:
            raise ValueError("UART private entry shape does not match compiler facts: " + name)


def render_bridge(source, facts):
    if "# UART_POLICY_ABI:" in source:
        validate_uart_policy_abi(facts)
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
    inputs += [Path(__file__).with_name("bootstrap_frontend.py"), Path(__file__).with_name("frontend_bridge.py")]
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
