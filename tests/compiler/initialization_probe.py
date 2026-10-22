#!/usr/bin/env python3
"""Build only the initialization regression probe and fact-check its host seam.

The selected compiler emits current source modules with local symbols. This is a
native test dependency, never a production frontend input or historical oracle.
The frontend's generated ABI facts establish layout compatibility; the standalone
test bridges construct the real owners. Neither symbol mangling nor layouts are
inferred from source spelling.
"""

import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("_initialization_frontend_abi", ROOT / "scripts/bootstrap_frontend.py")
ABI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ABI)

WORKSPACE = "compiler_ir_verification::VerificationWorkspace"
METADATA = "compiler_ir_metadata::MetadataStore"
NAMESPACE = "compiler_initialization_probe::"
# name, mutable workspace, paired metadata root, scalar tail count, return type.
# This closes the test transport rather than generating arbitrary callable access.
PROBES = (
    ("allocated", False, False, 0, "bool"),
    ("status", False, False, 0, "InitializationStatus"),
    ("slot_count", False, False, 0, "i64"),
    ("word_count", False, False, 0, "i64"),
    ("payload_bytes", False, False, 0, "i64"),
    ("acquire_service_loan", True, False, 3, "i64"),
    ("release_service_loan", True, False, 2, "i64"),
    ("service_unsuspended", False, False, 1, "i64"),
    ("validate_service_call", False, False, 4, "ServiceCallState"),
    ("complete_service_call", True, False, 2, "bool"),
    ("service_loans_closed", False, False, 0, "i64"),
    ("same_service_loans", False, False, 1, "i64"),
    ("retained_count", False, False, 0, "i64"),
    ("current_count", False, False, 0, "i64"),
    ("retained_count_at", False, False, 1, "i64"),
    ("load", True, False, 1, "bool"),
    ("retain", True, False, 0, "i64"),
    ("join", True, False, 1, "InitializationJoin"),
    ("restore_facts", True, False, 1, "bool"),
    ("initialize", True, True, 1, "InitializationStatus"),
    ("scalar_state", True, True, 1, "i64"),
    ("write_scalar", True, True, 1, "i64"),
    ("object_initialized", True, True, 1, "i64"),
    ("object_pristine", True, True, 1, "i64"),
    ("object_was_constructed", True, True, 1, "i64"),
    ("object_completion", True, True, 1, "ObjectCompletion"),
    ("mark_object", True, True, 1, "bool"),
    ("clear_object", True, True, 1, "bool"),
    ("receiver_field_state", True, True, 1, "i64"),
    ("write_receiver_field", True, True, 1, "i64"),
    ("receiver_completion", True, True, 0, "ReceiverCompletion"),
    ("array_first_missing", True, True, 3, "i64"),
    ("clear_array", True, True, 3, "bool"),
)


def canonical_shape(facts, value):
    if isinstance(value, list):
        return [canonical_shape(facts, child) for child in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, child in value.items():
        if key == "type_name":
            matches = [facts[group][child]["source_name"] for group in ("records", "enums") if child in facts[group]]
            if len(matches) != 1:
                raise ValueError("unresolved test ABI type")
            result[key] = matches[0]
        else:
            result[key] = canonical_shape(facts, child)
    return result


def compatible_owners(facts, frontend):
    # Each imported shared declaration must match the production frontend ABI.
    # Test bridges construct owners; compare names, not per-translation symbols.
    for group in ("records", "enums"):
        for declaration in facts[group].values():
            name = declaration["source_name"]
            if not name.startswith(("compiler_ir_verification::", "compiler_ir_metadata::")):
                raise ValueError("unexpected declaration in initialization probe: " + name)
            _, other = ABI.abi_declaration(frontend, group, name)
            if canonical_shape(facts, declaration) != canonical_shape(frontend, other):
                raise ValueError("probe/frontend owner ABI mismatch: " + name)
    _, workspace = ABI.abi_declaration(facts, "records", WORKSPACE)
    if workspace["size"] != 496 or workspace["reserved"] != 496 or workspace["alignment"] != 8:
        raise ValueError("current verifier workspace is not the reviewed 496-byte owner")
    if sum(field["kind"] == "owner" for field in workspace["fields"]) != 11:
        raise ValueError("current verifier workspace must contain eleven real owners")


def bridges(facts):
    declared = {
        entry["source_name"].removeprefix(NAMESPACE)
        for entry in facts["functions"].values()
        if entry["source_name"].startswith(NAMESPACE)
    }
    if declared != {row[0] for row in PROBES}:
        raise ValueError("initialization test operation inventory changed")
    workspace_symbol, _ = ABI.abi_declaration(facts, "records", WORKSPACE)
    metadata_symbol, _ = ABI.abi_declaration(facts, "records", METADATA)
    header = [
        "// Generated from initialization test probe ABI facts; do not edit.",
        "#pragma once",
        '#include "hosted_frontend_abi.hpp"',
        "static_assert(aurora::hosted_abi::verificationWorkspaceBytes == 496);",
        'extern "C" {',
    ]
    assembly = [".text"]
    registers = ("%rdi", "%rsi", "%rdx", "%rcx", "%r8", "%r9")
    for name, mutable, paired, parameter_count, result in PROBES:
        symbol, raw = ABI.abi_declaration(facts, "functions", NAMESPACE + name)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", symbol):
            raise ValueError("unsafe generated test symbol")
        function = ABI.normalize_function_abi(facts, raw)
        roots = [(workspace_symbol, mutable)] + ([(metadata_symbol, False)] if paired else [])
        actual_roots = [(root["type_name"], root["mutable"]) for root in function["borrowed_roots"]]
        if function["receiver"] is not None or actual_roots != roots:
            raise ValueError("initialization probe root authority changed: " + name)
        expected_abi = function["borrowed_root_abi"]
        if expected_abi["kind"] != ("tuple" if paired else "direct") or expected_abi["tuple_reserved_bytes"] != (
            16 if paired else 0
        ):
            raise ValueError("initialization probe root transport changed: " + name)
        parameters = function["parameters"]
        if len(parameters) != parameter_count or function["parameter_bytes"] != parameter_count * 8:
            raise ValueError("initialization probe parameter count changed: " + name)
        for at, parameter in enumerate(parameters):
            if (
                parameter["kind"] != "i64"
                or parameter.get("type_name") is not None
                or parameter["bytes"] != 8
                or parameter["offset"] != at * 8
            ):
                raise ValueError("initialization probe parameter shape changed: " + name)
        returned = function["result"]
        enum_symbol = (
            None
            if result in ("i64", "bool")
            else ABI.abi_declaration(facts, "enums", "compiler_ir_verification::" + result)[0]
        )
        if (
            returned["kind"] != (result if enum_symbol is None else "enum")
            or returned.get("type_name") != enum_symbol
            or returned["bytes"] != 8
        ):
            raise ValueError("initialization probe result changed: " + name)
        host = "aurora_test_initialization_" + name
        arguments = ["const void *" if paired or not mutable else "void *"] + ["std::int64_t"] * parameter_count
        header.append(f"std::int64_t {host}({', '.join(arguments)}) noexcept;")
        assembly += [f".globl {host}", f".hidden {host}", f".type {host}, @function", host + ":", "    movq %rdi, %r10"]
        assembly += [f"    movq {registers[at + 1]}, {registers[at]}" for at in range(parameter_count)]
        assembly += [f"    jmp {symbol}", f".size {host}, .-{host}"]
    return "\n".join(header + ["}"]) + "\n", "\n".join(assembly) + "\n"


FIXTURES = (
    "verification_create",
    "verification_release",
    "verification_report",
    "metadata_flag_masks",
    "metadata_create",
    "metadata_initialize",
    "metadata_release",
    "metadata_allocated",
    "metadata_run",
    "metadata_error",
)


def fixture_bridges(facts, frontend):
    """Same five supported private transports, in this single test graph only."""
    namespace = "compiler_initialization_fixture::"
    declared = {
        row["source_name"].removeprefix(namespace)
        for row in facts["functions"].values()
        if row["source_name"].startswith(namespace)
    }
    if declared != set(FIXTURES):
        raise ValueError("initialization fixture operation inventory changed")
    declarations, assembly = ['extern "C" {'], [".text"]
    for name in FIXTURES:
        symbol, raw = ABI.abi_declaration(facts, "functions", namespace + name)
        _, production_raw = ABI.abi_declaration(frontend, "functions", "compiler_frontend::" + name)
        function = ABI.normalize_function_abi(facts, raw)
        production = ABI.normalize_function_abi(frontend, production_raw)
        actual = canonical_shape(facts, {key: value for key, value in function.items() if key != "source_name"})
        expected = canonical_shape(frontend, {key: value for key, value in production.items() if key != "source_name"})
        if actual != expected or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", symbol):
            raise ValueError("test lifecycle/admission ABI differs from production: " + name)
        host = "aurora_test_" + name
        returned = "void"
        if name.endswith("_create"):
            arguments, moves = ["const void *", "void *"], [("%rdi", "%r11"), ("%rsi", "%r10")]
        elif name.endswith("_release"):
            arguments, moves = ["void *"], [("%rdi", "%r11")]
        elif name == "metadata_flag_masks":
            arguments, moves = ["void *"], [("%rdi", "%r10")]
        elif name == "metadata_initialize":
            arguments, moves = ["void *", "const void *"], [("%rdi", "%r10"), ("%rsi", "%r11")]
            returned = "std::int64_t"
        elif name == "verification_report":
            arguments, moves = ["const void *", "void *"], [("%rdi", "%r10"), ("%rsi", "%r11")]
        else:
            arguments, moves = ["void *" if name == "metadata_run" else "const void *"], [("%rdi", "%r10")]
            returned = "std::int64_t"
        declarations.append(f"{returned} {host}({', '.join(arguments)}) noexcept;")
        assembly += [f".globl {host}", f".hidden {host}", f".type {host}, @function", host + ":"]
        assembly += [f"    movq {source}, {destination}" for source, destination in moves]
        assembly += [f"    jmp {symbol}", f".size {host}, .-{host}"]
    return "\n".join(declarations + ["}"]) + "\n", "\n".join(assembly) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--frontend-facts", required=True, type=Path)
    parser.add_argument("inputs", nargs="+", type=Path)
    args = parser.parse_args()
    expected = {
        "initialization_probe.au",
        "ir_verification_errors.au",
        "ir_verification_storage.au",
        "ir_verification_initialization.au",
        "ir_metadata_storage.au",
        "ir_metadata.au",
    }
    if len(args.inputs) != len(expected) or {path.name for path in args.inputs} != expected:
        raise ValueError("initialization probe requires exactly its current source dependency closure")
    output = args.output.resolve()
    modules = output.with_suffix(".modules")
    ABI.stage_modules(modules, args.inputs)
    source = modules / "aurora/tests/initialization_probe.au"
    raw = output.with_suffix(".generated.s")
    facts_path = output.with_suffix(".abi.json")
    command = [str(args.compiler.resolve()), "--local-symbols", "--abi-facts", str(facts_path)]
    command += ["--module-root", str(modules), str(source), "-o", str(raw)]
    subprocess.run(command, check=True)
    facts = json.loads(facts_path.read_text())
    frontend = json.loads(args.frontend_facts.read_text())
    compatible_owners(facts, frontend)
    header, assembly = bridges(facts)
    fixture_header, fixture_assembly = fixture_bridges(facts, frontend)
    header += fixture_header
    assembly += fixture_assembly
    output.with_name("initialization_probe_abi.hpp").write_text(header)
    output.write_bytes(raw.read_bytes() + b"\n" + assembly.encode())


if __name__ == "__main__":
    main()
