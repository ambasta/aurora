#!/usr/bin/env python3
"""Require current compiler frontend convergence and exact source diagnostics."""

from pathlib import Path
from copy import deepcopy
import hashlib
import json
import os
import subprocess
import sys
import tempfile


def stage_modules(root, destination):
    # Import the actual build staging helper: both paths copy exported modules
    # exactly, without rewriting their namespaces or interface declarations.
    sys.path.insert(0, str(root / "scripts"))
    from bootstrap_frontend import stage_modules as stage

    stage(destination, [root / "compiler" / name for name in COMPILER_MODULES])


# Every .au file in compiler/ is a frontend module.
COMPILER_MODULES = tuple(sorted(path.name for path in (Path(__file__).resolve().parents[2] / "compiler").glob("*.au")))


INITIALIZATION_OPERATIONS = (
    "create", "release", "allocated", "status", "initialize", "slot_count", "word_count",
    "retained_count", "current_count", "retained_count_at", "load", "retain", "join",
    "scalar_state", "write_scalar", "object_initialized", "object_pristine", "mark_object", "clear_object",
    "array_first_missing", "clear_array",
)


def require(value, message):
    if not value:
        raise AssertionError(message)


def sources(root):
    # Only checked-in source roots, never generated build or retained evidence.
    return sorted(
        path for name in ("compiler", "examples", "kernel", "library", "tests") for path in (root / name).rglob("*.au")
    )


def run(command):
    return subprocess.run(command, capture_output=True, timeout=30, check=True).stdout


def frontend_arguments(compiler, root, output):
    return [
        str(compiler),
        "--output",
        str(output),
        *(str(root / "compiler" / name) for name in COMPILER_MODULES),
        str(root / "compiler/hosted_lexer.S"),
        str(root / "compiler/hosted_parser.S"),
        str(root / "compiler/hosted_resolver.S"),
        str(root / "compiler/hosted_graph.S"),
        str(root / "compiler/hosted_ir_metadata.S"),
        str(root / "compiler/hosted_ir_instructions.S"),
        str(root / "compiler/hosted_ir_initialization.S"),
    ]


def symbols(path, globals_only=False):
    command = ["nm", "--defined-only", "--format=posix", "--print-size"]
    if globals_only:
        command.append("--extern-only")
    return {row.split()[0]: row.split()[1:] for row in run([*command, str(path)]).decode().splitlines()}


def abi_generation(facts):
    from bootstrap_frontend import abi_declaration, frontend_abi_header

    # An additional copied record and a renamed field need no renderer schema.
    changed = deepcopy(facts)
    symbol, node = abi_declaration(changed, "records", "compiler_parser::AstNode")
    extra = deepcopy(node)
    extra["source_name"] = "fixture::AdditionalRecord"
    extra["fields"][1]["name"] = "_replacement_index"
    changed["records"][symbol + "_fixture"] = extra
    generated = frontend_abi_header(changed)
    require("namespace aurora::hosted_abi::fixture {" in generated, "new record namespace was omitted")
    require("struct alignas(8) AdditionalRecord {" in generated, "new copied record was omitted")
    require("std::int64_t _replacement_index{};" in generated, "Aurora field spelling was not preserved")
    require("i64_type = 1," in generated, "Aurora enum case spelling was not preserved")
    _, nested = abi_declaration(facts, "records", "compiler_parser::TypeResult")
    require(
        "aurora::hosted_abi::compiler_parser::ParseToken next_token{};" in generated
        and nested["fields"][-1]["kind"] == "class",
        "nested copied record was flattened or omitted",
    )
    require(
        "struct alignas(8) AdmissionInput {" in generated
        and "aurora::hosted_abi::compiler_parser::AdmissionConfig configuration{};" in generated
        and "aurora::hosted_abi::compiler_parser::AdmissionStatus result{};" in generated,
        "declaration admission input/configuration/result was flattened or omitted",
    )
    require(
        all(
            f"struct alignas(8) {name} {{" in generated
            for name in (
                "ResolverCreate",
                "ResolverIngest",
                "ResolverRelease",
                "ResolverReleasePair",
                "ResolverSourceInput",
                "ResolverTextInput",
                "ResolverOrderInput",
                "ResolverImportInput",
                "ResolverSeedBuiltinInput",
                "ResolverSeedMemberInput",
            )
        )
        and "aurora::hosted_abi::compiler_resolver::Session session{};" in generated
        and "aurora::hosted_abi::compiler_parser::AstArena parsed{};" in generated
        and "static_assert(sizeof(ResolverReleasePair) == offsetof(ResolverIngest, module));" in generated,
        "resolution argument records or checked consuming-owner prefixes were omitted",
    )
    require(
        all(
            f"struct alignas(8) {name} {{" in generated
            for name in (
                "LoweringBeginInput",
                "LoweringScalarInput",
                "LoweringServiceInput",
            )
        )
        and "aurora::hosted_abi::compiler_lowering::LoweringConfig configuration{};" in generated
        and "aurora::hosted_abi::compiler_lowering::ScalarSeed seed{};" in generated
        and "aurora::hosted_abi::compiler_lowering::ServiceSeed seed{};" in generated
        and "aurora::hosted_abi::compiler_lowering::ServiceParameters parameterTypes{};" in generated,
        "lowering input/configuration/catalog records were flattened or omitted",
    )
    # Candidate source expectations; this check must compare fresh compiler facts
    # before these sizes are qualification evidence.
    for source, extent in (
        ("compiler_resolver::Session", 520),
        ("compiler_lowering::OutputRow", 64),
        ("compiler_lowering::OperandRow", 40),
        ("compiler_lowering::LoweringResult", 32),
        ("compiler_lowering::LocalRow", 160),
        ("compiler_lowering::SnapshotRow", 48),
        ("compiler_lowering::ContinuationRow", 496),
        ("compiler_ir_metadata::ReceiverShape", 24),
        ("compiler_ir_metadata::CallableOptions", 56),
        ("compiler_ir_metadata::CallableRow", 120),
        ("compiler_ir_metadata::SlotRow", 40),
        ("compiler_ir_metadata::InputCounts", 80),
        ("compiler_ir_metadata::MetadataStore", 512),
        ("compiler_ir_instructions::RawInstructionRow", 64),
        ("compiler_ir_instructions::RawOperandRow", 40),
        ("compiler_ir_instructions::CodeRow", 32),
        ("compiler_ir_instructions::BodyRow", 24),
        ("compiler_ir_instructions::InstructionCounts", 32),
        ("compiler_ir_instructions::InstructionStore", 176),
    ):
        _, entry = abi_declaration(facts, "records", source)
        require(entry["reserved"] == extent and entry["alignment"] == 8, f"frontend layout changed: {source}")
    require(
        "struct alignas(8) MetadataCreate {" in generated
        and "struct alignas(8) MetadataRelease {" in generated
        and "aurora::hosted_abi::compiler_ir_metadata::InputCounts counts{};" in generated
        and "std::int64_t callableCount{};" in generated
        and "std::int64_t slotCount{};" in generated
        and "std::int64_t instructionBegin{};" in generated
        and "metadataStore_typesBytes = 32;" in generated
        and "metadataStore_callablesBytes = 32;" in generated
        and "metadataStore_slotsBytes = 32;" in generated
        and "metadataCallableRowPhysicalBytes = 120;" in generated
        and "metadataRawTypeRowPhysicalBytes = 64;" in generated
        and "metadataSlotRowPhysicalBytes = 40;" in generated,
        "metadata arguments or closed owner/row physical bindings were omitted",
    )
    require(
        all(f"struct alignas(8) {name} {{" in generated for name in (
            "InstructionsCreate", "InstructionsRelease"
        ))
        and all(f"instructionStore_{pool}Bytes = 32;" in generated for pool in (
            "instructions", "operands", "literals", "codeOrder", "bodies"
        ))
        and all(f"instruction{row}PhysicalBytes = {width};" in generated for row, width in (
            ("RawInstructionRow", 64), ("RawOperandRow", 40), ("CodeRow", 32), ("BodyRow", 24)
        )),
        "instruction arguments or closed owner/row physical bindings were omitted",
    )
    _, code_row = abi_declaration(facts, "records", "compiler_ir_instructions::CodeRow")
    require(
        [(field["name"], field["kind"], field["offset"], field["bytes"]) for field in code_row["fields"]]
        == [("instructionId", "i64", 0, 8), ("targetPosition", "i64", 8, 8),
            ("flowFlags", "u64", 16, 8), ("scratchValue", "i64", 24, 8)],
        "instruction identity, structural facts or scratch layout changed",
    )
    # Exact root signatures are the only native entry authority. An imported
    # implementation must not become a fallback when its forwarding root is lost.
    for operation in (
        "begin",
        "seed_scalar",
        "seed_service",
        "seed_layout_symbol",
        "run",
        "count",
        "read_output",
        "read_operand",
    ):
        for mutation in ("receiver", "result", "parameters", "root"):
            changed = deepcopy(facts)
            source = "compiler_frontend::lowering_" + operation
            _, entry = abi_declaration(changed, "functions", source)
            if mutation == "receiver":
                entry["borrowed_roots"] = []
            elif mutation == "result":
                entry["result"]["bytes"] += 8
            elif mutation == "parameters":
                if entry["parameters"]:
                    entry["parameters"][0]["type_name"] = "wrong-lowering-parameter"
                else:
                    entry["parameter_bytes"] += 8
            else:
                entry["source_name"] = "fixture::removed_lowering_" + operation
            try:
                frontend_abi_header(changed)
            except ValueError:
                continue
            raise AssertionError(f"unsafe lowering bridge accepted: {operation}/{mutation}")
    graph_input, _ = abi_declaration(facts, "records", "compiler_ir_graph::Input")
    graph_workspace, _ = abi_declaration(facts, "records", "compiler_ir_graph::Workspace")
    for field, value in (
        ("receiver", graph_input),
        ("receiver_mutable", False),
        ("borrowed_parameter", False),
        ("second_receiver", None),
        ("second_receiver", {"type_name": graph_workspace, "mutable": False}),
        ("second_receiver", {"type_name": graph_input, "mutable": True}),
        ("root_count", 1),
        ("root_order", ["second_receiver", "receiver"]),
        ("root_tuple_bytes", 8),
        ("parameters", [{"kind": "i64", "bytes": 8, "offset": 0}]),
        ("parameter_bytes", 8),
        ("result", {"kind": "i64", "bytes": 8}),
    ):
        changed = deepcopy(facts)
        _, entry = abi_declaration(changed, "functions", "compiler_frontend::graph_run")
        entry[field] = value
        try:
            frontend_abi_header(changed)
        except ValueError:
            continue
        raise AssertionError(f"unsafe graph paired bridge accepted: {field}={value}")
    metadata_store, _ = abi_declaration(facts, "records", "compiler_ir_metadata::MetadataStore")
    instruction_store, _ = abi_declaration(facts, "records", "compiler_ir_instructions::InstructionStore")
    initialization, _ = abi_declaration(facts, "records", "compiler_ir_initialization::InitializationWorkspace")
    require(
        all(f"struct alignas(8) {name} {{" in generated for name in ("InitializationCreate", "InitializationRelease"))
        and all(f"initializationWorkspace_{pool}Bytes = 32;" in generated for pool in
                ("currentWords", "retainedWords", "retainedCounts"))
        and "initializationWordPairPhysicalBytes = 16;" in generated
        and "initializationCountPairPhysicalBytes = 16;" in generated,
        "initialization owner transfer or physical pool facts were omitted",
    )
    for operation in INITIALIZATION_OPERATIONS:
        for mutation in ("receiver", "result", "parameters", "root"):
            changed = deepcopy(facts)
            _, entry = abi_declaration(changed, "functions", "compiler_frontend::initialization_" + operation)
            if mutation == "receiver":
                entry["receiver"] = initialization if entry["receiver"] is None else None
            elif mutation == "result":
                entry["result"]["bytes"] += 8
            elif mutation == "parameters":
                if entry["parameters"]:
                    entry["parameters"][0]["bytes"] += 8
                else:
                    entry["parameter_bytes"] += 8
            else:
                entry["source_name"] = "fixture::removed_initialization_" + operation
            try:
                frontend_abi_header(changed)
            except ValueError:
                continue
            raise AssertionError(f"unsafe initialization bridge accepted: {operation}/{mutation}")
    for operation in ("initialize", "scalar_state", "write_scalar", "object_initialized", "object_pristine",
                      "mark_object", "clear_object", "array_first_missing", "clear_array"):
        for field, value in (
            ("receiver_mutable", False),
            ("borrowed_parameter", False),
            ("second_receiver", None),
            ("second_receiver", {"type_name": initialization, "mutable": False}),
            ("second_receiver", {"type_name": metadata_store, "mutable": True}),
            ("root_count", 1),
            ("root_order", ["second_receiver", "receiver"]),
            ("root_tuple_bytes", 8),
            ("result", {"kind": "class", "type_name": initialization, "bytes": 8}),
        ):
            changed = deepcopy(facts)
            _, entry = abi_declaration(changed, "functions", "compiler_frontend::initialization_" + operation)
            entry[field] = value
            try:
                frontend_abi_header(changed)
            except ValueError:
                continue
            raise AssertionError(f"unsafe initialization paired bridge accepted: {operation}/{field}={value}")
    for source, field in (
        ("InitializationWorkspace", "currentWords"), ("InitializationWorkspace", "retainedWords"),
        ("InitializationWorkspace", "retainedCounts"), ("InitializationWorkspace", "retainedCount"),
        ("WordPair", "mustBits"), ("CountPair", "mayCount"),
    ):
        changed = deepcopy(facts)
        _, entry = abi_declaration(changed, "records", "compiler_ir_initialization::" + source)
        next(member for member in entry["fields"] if member["name"] == field)["bytes"] += 8
        try:
            frontend_abi_header(changed)
        except ValueError:
            continue
        raise AssertionError(f"unsafe initialization owner/row binding accepted: {source}/{field}")
    for operation in ("create", "release", "allocated", "admit", "structure", "publish", "error"):
        for mutation in ("receiver", "result", "parameters", "root"):
            changed = deepcopy(facts)
            _, entry = abi_declaration(changed, "functions", "compiler_frontend::instructions_" + operation)
            if mutation == "receiver":
                entry["receiver"] = instruction_store if entry["receiver"] is None else None
            elif mutation == "result":
                entry["result"]["bytes"] += 8
            elif mutation == "parameters":
                if entry["parameters"]:
                    entry["parameters"][0]["bytes"] += 8
                else:
                    entry["parameter_bytes"] += 8
            else:
                entry["source_name"] = "fixture::removed_instructions_" + operation
            try:
                frontend_abi_header(changed)
            except ValueError:
                continue
            raise AssertionError(f"unsafe instruction bridge accepted: {operation}/{mutation}")
    # Both admission phases borrow the same ordered pair: mutable instructions,
    # immutable declarations. Neither may gain a second mutable root or silently
    # degrade to the former single-root normalization entrypoint.
    for operation in ("admit", "structure"):
        for field, value in (
            ("receiver", metadata_store),
            ("receiver_mutable", False),
            ("borrowed_parameter", False),
            ("second_receiver", None),
            ("second_receiver", {"type_name": instruction_store, "mutable": False}),
            ("second_receiver", {"type_name": metadata_store, "mutable": True}),
            ("root_count", 1),
            ("root_count", 3),
            ("root_order", ["second_receiver", "receiver"]),
            ("root_order", ["receiver", "receiver"]),
            ("root_tuple_bytes", 8),
            ("root_tuple_bytes", 24),
            ("parameters", [{"kind": "i64", "bytes": 8, "offset": 0}]),
            ("parameter_bytes", 8),
        ):
            changed = deepcopy(facts)
            _, entry = abi_declaration(changed, "functions", "compiler_frontend::instructions_" + operation)
            entry[field] = value
            try:
                frontend_abi_header(changed)
            except ValueError:
                continue
            raise AssertionError(f"unsafe instruction paired bridge accepted: {operation}/{field}={value}")
    for pool, row in (("instructions", "RawInstructionRow"), ("operands", "RawOperandRow"),
                      ("literals", None), ("codeOrder", "CodeRow"), ("bodies", "BodyRow")):
        for mutation in ("owner", "stride", "leaf") if row else ("owner",):
            changed = deepcopy(facts)
            if mutation == "owner":
                _, entry = abi_declaration(changed, "records", "compiler_ir_instructions::InstructionStore")
                next(field for field in entry["fields"] if field["name"] == pool)["bytes"] += 8
            else:
                _, entry = abi_declaration(changed, "records", "compiler_ir_instructions::" + row)
                if mutation == "stride":
                    entry["size"] -= 1
                else:
                    entry["fields"][0]["kind"] = "bool"
            try:
                frontend_abi_header(changed)
            except ValueError:
                continue
            raise AssertionError(f"unsafe instruction pool binding accepted: {pool}/{mutation}")
    for operation, parameter, name in (
        ("create", 2, "callable-count"), ("create", 3, "slot-count"), ("create", 4, "instruction-begin"),
        ("object_leaf_root", 0, "callable"), ("object_leaf_root", 1, "offset"),
        ("byte_array_element_root", 0, "callable"), ("byte_array_element_root", 1, "offset"),
    ):
        for mutation in ("missing", "type", "offset"):
            changed = deepcopy(facts)
            _, entry = abi_declaration(changed, "functions", "compiler_frontend::metadata_" + operation)
            if mutation == "missing":
                entry["parameters"].pop(parameter)
            elif mutation == "type":
                entry["parameters"][parameter]["kind"] = "u64"
            else:
                entry["parameters"][parameter]["offset"] += 8
            try:
                frontend_abi_header(changed)
            except ValueError:
                continue
            raise AssertionError(f"unsafe metadata {operation}/{name} argument accepted: {mutation}")
    for operation in ("create", "release", "allocated", "run", "error", "object_leaf_root", "byte_array_element_root"):
        for mutation in ("receiver", "result", "parameters", "root"):
            changed = deepcopy(facts)
            _, entry = abi_declaration(changed, "functions", "compiler_frontend::metadata_" + operation)
            if mutation == "receiver":
                entry["receiver"] = metadata_store if entry["receiver"] is None else None
            elif mutation == "result":
                entry["result"]["bytes"] += 8
            elif mutation == "parameters":
                if entry["parameters"]:
                    entry["parameters"][0]["bytes"] += 8
                else:
                    entry["parameter_bytes"] += 8
            else:
                entry["source_name"] = "fixture::removed_metadata_" + operation
            try:
                frontend_abi_header(changed)
            except ValueError:
                continue
            raise AssertionError(f"unsafe metadata bridge accepted: {operation}/{mutation}")
    for operation in ("allocated", "run", "error", "object_leaf_root", "byte_array_element_root"):
        changed = deepcopy(facts)
        _, entry = abi_declaration(changed, "functions", "compiler_frontend::metadata_" + operation)
        entry["borrowed_roots"][0]["mutable"] = operation != "run"
        try:
            frontend_abi_header(changed)
        except ValueError:
            continue
        raise AssertionError(f"unsafe metadata owner authority accepted: {operation}")
    for kind in (
        "metadata_second_root",
        "metadata_owner_extent",
        "metadata_row_stride",
        "metadata_narrow_leaf",
        "metadata_slot_owner_extent",
        "metadata_slot_stride",
        "metadata_slot_narrow_leaf",
        "unexpected_second_root",
        "unexpected_root_count",
        "unexpected_root_tuple",
        "result_extent",
        "field_extent",
        "unsupported_array",
        "admission_receiver",
        "admission_result_extent",
        "admission_configuration_extent",
        "admission_parameter_offset",
        "resolver_receiver",
        "resolver_ingest_result",
        "resolver_ingest_session",
        "resolver_ingest_parsed",
        "resolver_release_prefix",
        "resolver_release_pair_prefix",
        "resolver_source_shape",
        "resolver_order_shape",
        "resolver_seed_shape",
    ):
        changed = deepcopy(facts)
        if kind == "metadata_second_root":
            _, entry = abi_declaration(changed, "functions", "compiler_frontend::metadata_run")
            entry["second_receiver"] = {"type_name": metadata_store, "mutable": False}
        elif kind in ("metadata_owner_extent", "metadata_slot_owner_extent"):
            _, entry = abi_declaration(changed, "records", "compiler_ir_metadata::MetadataStore")
            pool = "slots" if kind == "metadata_slot_owner_extent" else "types"
            next(field for field in entry["fields"] if field["name"] == pool)["bytes"] += 8
        elif kind in (
            "metadata_row_stride", "metadata_narrow_leaf", "metadata_slot_stride", "metadata_slot_narrow_leaf"
        ):
            row = "SlotRow" if kind.startswith("metadata_slot_") else "IndexRow"
            _, entry = abi_declaration(changed, "records", "compiler_ir_metadata::" + row)
            if kind in ("metadata_row_stride", "metadata_slot_stride"):
                entry["size"] -= 1
            else:
                entry["fields"][0]["kind"] = "bool"
        elif kind.startswith("unexpected_"):
            _, entry = abi_declaration(changed, "functions", "compiler_frontend::parser_read_node")
            if kind == "unexpected_second_root":
                entry["second_receiver"] = {"type_name": entry["receiver"], "mutable": False}
            elif kind == "unexpected_root_count":
                entry["root_count"] = 2
            else:
                entry["root_tuple_bytes"] = 16
        elif kind == "result_extent":
            _, entry = abi_declaration(changed, "functions", "compiler_frontend::parser_read_node")
            entry["result"]["bytes"] += 8
        elif kind.startswith("resolver_"):
            source = {
                "resolver_receiver": "compiler_frontend::resolver_append_source",
                "resolver_ingest_result": "compiler_frontend::resolver_ingest",
                "resolver_ingest_session": "compiler_frontend::resolver_ingest",
                "resolver_ingest_parsed": "compiler_frontend::resolver_ingest",
                "resolver_release_prefix": "compiler_frontend::resolver_release",
                "resolver_release_pair_prefix": "compiler_frontend::resolver_release_pair",
                "resolver_source_shape": "compiler_frontend::resolver_append_source",
                "resolver_order_shape": "compiler_frontend::resolver_order_module",
                "resolver_seed_shape": "compiler_frontend::resolver_seed_member",
            }[kind]
            _, entry = abi_declaration(changed, "functions", source)
            if kind == "resolver_receiver":
                entry["borrowed_roots"] = []
            elif kind == "resolver_ingest_result":
                entry["result"]["bytes"] += 8
            elif kind in ("resolver_ingest_session", "resolver_ingest_parsed"):
                entry["parameters"][1 if kind == "resolver_ingest_session" else 2]["type_name"] = "wrong-owner"
            elif kind.endswith("prefix"):
                entry["parameters"][-1]["offset"] += 8
            else:
                entry["parameters"][-1]["bytes"] += 8
        elif kind.startswith("admission_"):
            _, entry = abi_declaration(changed, "functions", "compiler_frontend::parser_admit")
            if kind == "admission_receiver":
                entry["borrowed_roots"] = []
            elif kind == "admission_result_extent":
                entry["result"]["bytes"] += 8
            elif kind == "admission_configuration_extent":
                entry["parameters"][-1]["bytes"] += 8
            else:
                entry["parameters"][-1]["offset"] += 8
        else:
            _, entry = abi_declaration(changed, "records", "compiler_parser::AstNode")
            entry["fields"][1]["bytes" if kind == "field_extent" else "array_length"] += 1
        try:
            frontend_abi_header(changed)
        except ValueError:
            continue
        raise AssertionError(f"unsupported or unsafe ABI facts accepted: {kind}")
    print("PASS generic source-spelled ABI records/enums, nested layout and exact lowering/metadata/instruction bridge rejection")


def borrowed_root_generation(facts):
    from bootstrap_frontend import abi_declaration, frontend_abi_header, frontend_bridge, normalize_function_abi

    require(type(facts["version"]) is int and facts["version"] == 2, "candidate must emit ABI facts v2")
    header = frontend_abi_header(facts)
    predecessor = deepcopy(facts)
    predecessor["version"] = 1
    for function in predecessor["functions"].values():
        roots = function.pop("borrowed_roots")
        count = function.pop("borrowed_root_count")
        function.pop("borrowed_root_abi")
        require(count <= 2 and (count != 2 or roots[0]["mutable"]), "frontend exceeded paired source predecessor")
        if roots:
            require(function["receiver"] is None, "borrowed roots duplicated in genuine receiver")
            function["receiver"], function["receiver_mutable"] = roots[0]["type_name"], roots[0]["mutable"]
        function["borrowed_parameter"] = bool(count)
        function["second_receiver"] = (
            dict(type_name=roots[1]["type_name"], mutable=False) if count == 2 else None
        )
        function["root_count"] = count if count else int(function["receiver"] is not None)
        function["root_tuple_bytes"] = 16 if count == 2 else 0
        function["root_order"] = (["receiver", "second_receiver"] if count == 2 else
                                  ["receiver"] if function["receiver"] is not None else [])
    require(frontend_abi_header(predecessor) == header, "paired predecessor/current normalization changed headers")
    bridge = "call __aurora_frontend_graph_run\ncall __aurora_frontend_lexer_next\n"
    require(frontend_bridge(bridge, predecessor) == frontend_bridge(bridge, facts), "predecessor/current bridge drift")

    def reject(document, source, mutation):
        changed = deepcopy(document)
        _, function = abi_declaration(changed, "functions", source)
        mutation(function)
        try:
            frontend_abi_header(changed)
        except ValueError:
            return
        raise AssertionError("unsafe borrowed-root facts accepted: " + source)

    pair_sources = ("graph_run", "instructions_admit", "instructions_structure", "initialization_initialize")
    for alias in pair_sources:
        source = "compiler_frontend::" + alias
        for lane in (0, 1):
            for field, value in (("ordinal", 1 - lane), ("ordinal", False), ("selector", -6),
                                 ("selector", -9223372036854775808), ("selector", False),
                                 ("type_name", "missing-root"), ("mutable", lane == 1), ("mutable", 1)):
                reject(facts, source, lambda f, lane=lane, field=field, value=value:
                       f["borrowed_roots"][lane].__setitem__(field, value))
        for mutation in (
            lambda f: f["borrowed_roots"].reverse(),
            lambda f: f["borrowed_roots"].pop(),
            lambda f: f["borrowed_roots"].append(dict(f["borrowed_roots"][1])),
            lambda f: f["borrowed_roots"][1].__setitem__("type_name", f["borrowed_roots"][0]["type_name"]),
            lambda f: f.__setitem__("borrowed_root_count", True),
            lambda f: f.__setitem__("borrowed_root_count", 3),
            lambda f: f["borrowed_root_abi"].__setitem__("tuple_payload_bytes", 24),
            lambda f: f["borrowed_root_abi"].__setitem__("tuple_reserved_bytes", 8),
            lambda f: f["borrowed_root_abi"].__setitem__("saved_root_reserved_bytes", 0),
            lambda f: f.__setitem__("third_receiver", None),
        ):
            reject(facts, source, mutation)
        for mutation in (
            lambda f: f.__setitem__("root_count", 3),
            lambda f: f.__setitem__("root_count", True),
            lambda f: f.__setitem__("root_order", ["receiver", "second_receiver", "third_receiver"]),
            lambda f: f.__setitem__("receiver_mutable", False),
            lambda f: f["second_receiver"].__setitem__("mutable", True),
            lambda f: f.__setitem__("borrowed_roots", []),
            lambda f: f.__setitem__("third_receiver", None),
            lambda f: f.pop("root_tuple_bytes"),
        ):
            reject(predecessor, source, mutation)

    # The normalizer understands the bounded capability even though this
    # unchanged frontend deliberately uses only predecessor-compatible helpers.
    _, pair = abi_declaration(facts, "functions", "compiler_frontend::graph_run")
    for count in range(1, 7):
        for mutable in (False, True):
            for tail in range(7 - count):
                function = deepcopy(pair)
                function["borrowed_root_count"] = count
                function["borrowed_roots"] = [
                    dict(ordinal=i, selector=-i, type_name=pair["borrowed_roots"][i % 2]["type_name"],
                         mutable=mutable and i == 0) for i in range(count)
                ]
                function["borrowed_root_abi"] = dict(
                    kind="direct" if count == 1 else "tuple", register="r10",
                    tuple_payload_bytes=8 * count if count > 1 else 0,
                    tuple_reserved_bytes=16 * ((count + 1) // 2) if count > 1 else 0,
                    saved_root_reserved_bytes=16 * ((count + 1) // 2),
                )
                function["parameters"] = [dict(offset=8 * i, bytes=8, kind="i64") for i in range(tail)]
                function["parameter_bytes"] = 8 * tail
                require(normalize_function_abi(facts, function) == function, "bounded root normalization drift")
    print("PASS bounded borrowed-root facts and exact paired-predecessor/current header normalization")


def message_generation(facts, root):
    from bootstrap_frontend import instruction_messages, lowering_messages, metadata_messages

    source = (root / "compiler/lowering_errors.au").read_text()
    table = "\n".join(lowering_messages(source, facts))
    require(
        "{\"unknown class type '{type}'\", MessageOrigin::source_or_synthetic, false, "
        "{OperandRole::DiagnosticTypeId, OperandRole::NoDiagnosticValue}},"
        in table
        and '{"IR: storage extent exceeds 65536 bytes", MessageOrigin::unlocated, true,' in table,
        "lowering message table lost a placeholder role or integrity flag",
    )
    first = "        unknown_class_type,"
    for changed in (
        source.replace("        //: unknown class type '{type}'\n", "", 1),
        source.replace("unknown class type '{type}'", "unknown class type '{kind}'", 1),
        source.replace("unknown class type '{type}'", "unknown class type '{type", 1),
        source.replace("unknown class type '{type}'", "unknown class type '{type}' {", 1),
        source.replace("unknown class type '{type}'", "unknown class type '{type}' }", 1),
        source.replace("unknown class type '{type}'", "unknown class type '{{type}'", 1),
        source.replace("unknown class type '{type}'", "[integrity] unknown class type '{type}'", 1),
        source.replace(
            "        borrowed_arguments_require_distinct_roots\n",
            "        borrowed_arguments_require_distinct_roots\n        //: dangling\n",
            1,
        ),
        source.replace(first, first + "\n        //: extra reason\n        unlisted_reason,", 1),
    ):
        try:
            lowering_messages(changed, facts)
        except ValueError:
            continue
        raise AssertionError("lowering message generation accepted a missing, extra or malformed message")

    source = (root / "compiler/ir_metadata_storage.au").read_text()
    table = "\n".join(metadata_messages(source, facts))
    require(
        "case MetadataError::none: return nullptr;" in table
        and 'case MetadataError::class_leaf: return "invalid typed IR: non-scalar class layout field";' in table,
        "metadata message table lost its constant diagnostic binding",
    )
    for changed in (
        source.replace("        //: invalid hosted IR metadata transport\n", "", 1),
        source.replace("        integrity,", "        unknown_reason,", 1),
    ):
        try:
            metadata_messages(changed, facts)
        except ValueError:
            continue
        raise AssertionError("metadata message generation accepted a missing message or mismatched reason")
    source = (root / "compiler/ir_instruction_storage.au").read_text()
    table = "\n".join(instruction_messages(source, facts))
    require(
        "case InstructionError::none: return nullptr;" in table
        and 'return "invalid typed IR: noncanonical instruction type payload";' in table
        and all(f'return "invalid typed IR: {message}";' in table for message in (
            "empty function body", "duplicate or invalid label", "unknown jump target",
            "unknown branch target", "reachable fallthrough without return", "unreachable semantic instruction",
        )),
        "instruction message table lost its constant diagnostic binding",
    )
    for changed in (
        source.replace("        //: invalid hosted IR instruction transport\n", "", 1),
        source.replace("        //: invalid typed IR: unreachable semantic instruction\n", "", 1),
        source.replace("        integrity,", "        unknown_reason,", 1),
    ):
        try:
            instruction_messages(changed, facts)
        except ValueError:
            continue
        raise AssertionError("instruction message generation accepted a missing message or mismatched reason")


def frontend_bootstrap(current1, current2, root, work, built_a, built_b):
    abi_generation(json.loads(built_b.with_suffix(".abi.json").read_text()))
    borrowed_root_generation(json.loads(built_b.with_suffix(".abi.json").read_text()))
    message_generation(json.loads(built_b.with_suffix(".abi.json").read_text()), root)
    entries = {
        "aurora_hosted_lexer_invoke",
        "aurora_hosted_parser_create",
        "aurora_hosted_parser_parse",
        "aurora_hosted_parser_admit",
        "aurora_hosted_parser_count",
        "aurora_hosted_parser_read",
        "aurora_hosted_parser_edges",
        "aurora_hosted_parser_edge",
        "aurora_hosted_parser_types",
        "aurora_hosted_parser_type",
        "aurora_hosted_parser_syntax_count",
        "aurora_hosted_parser_syntax",
        "aurora_hosted_parser_release",
    }
    entries.update(
        "aurora_hosted_resolver_" + operation
        for operation in (
            "create",
            "ingest",
            "release",
            "release_pair",
            "append_source",
            "append_text",
            "order_module",
            "bind_import",
            "count",
            "read_source",
            "read_syntax",
            "read_meta",
            "read_resolved",
            "status",
            "seed_builtin",
            "seed_member",
            "run",
        )
    )
    entries.update(
        "aurora_hosted_lowering_" + operation
        for operation in (
            "begin",
            "seed_scalar",
            "seed_service",
            "seed_layout_symbol",
            "run",
            "count",
            "read_output",
            "read_operand",
        )
    )
    entries.update(
        "aurora_hosted_graph_" + operation
        for operation in (
            "create_input", "create_workspace", "release_input", "release_workspace",
            "set_function", "set_edge", "run", "retained",
        )
    )
    entries.update(
        "aurora_hosted_metadata_" + operation
        for operation in ("create", "release", "allocated", "run", "error", "object_leaf_root", "byte_array_element_root")
    )
    entries.update(
        "aurora_hosted_instructions_" + operation
        for operation in ("create", "release", "allocated", "admit", "structure", "publish", "error")
    )
    entries.update("aurora_hosted_initialization_" + operation for operation in INITIALIZATION_OPERATIONS)
    # A is predecessor-generated and need not equal B. Both actual build
    # objects must expose exactly the private host shim contract.
    for unit in (built_a, built_b):
        require(
            set(symbols(unit.with_suffix(".o"), globals_only=True)) == entries,
            f"built frontend leaked a generated symbol or lost a shim: {unit}",
        )

    def header(unit):
        return unit.parent / (unit.stem.replace("-", "_") + "_abi.hpp")

    require(
        header(built_a).read_bytes() == header(built_b).read_bytes(),
        "A/B generated layout differs for reused host objects",
    )
    units = []
    for number, compiler in enumerate((current1, current2), start=1):
        output = work / f"frontend-c{number}.s"
        run(
            [
                sys.executable,
                "-B",
                str(root / "scripts/bootstrap_frontend.py"),
                *frontend_arguments(compiler, root, output),
            ]
        )
        units.append(output)
        obj = output.with_suffix(".o")
        run(["as", "--64", str(output), "-o", str(obj)])
        require(set(symbols(obj, globals_only=True)) == entries, "frontend leaked a generated symbol or lost a shim")
        for name in COMPILER_MODULES:
            require(
                (work / "compiler-modules/aurora/compiler" / name).read_bytes()
                == (root / "compiler" / name).read_bytes(),
                f"staged compiler module changed exported source: {name}",
            )
    for suffix, description in (
        (".s", "assembly"),
        (".generated.s", "generated graph"),
        (".o", "object bytes"),
        (".abi.json", "ABI facts"),
    ):
        regenerated_b = units[0].with_suffix(suffix).read_bytes()
        require(
            regenerated_b == built_b.with_suffix(suffix).read_bytes(),
            f"regenerated frontend B differs from the actual B consumed by current C2: {description}",
        )
        require(
            regenerated_b == units[1].with_suffix(suffix).read_bytes(),
            f"current compiler frontend B/C convergence differs: {description}",
        )
    require(
        header(units[0]).read_bytes() == header(built_b).read_bytes() == header(units[1]).read_bytes(),
        "generated ABI header convergence differs",
    )
    generated_header = header(units[0])
    expected = generated_header.read_bytes()
    old_mtime = 1_000_000_000_000_000_000
    os.utime(generated_header, ns=(old_mtime, old_mtime))
    run(
        [
            sys.executable,
            "-B",
            str(root / "scripts/bootstrap_frontend.py"),
            *frontend_arguments(current1, root, units[0]),
        ]
    )
    require(
        generated_header.read_bytes() == expected and generated_header.stat().st_mtime_ns == old_mtime,
        "unchanged compiler ABI header was rewritten",
    )
    print(
        "PASS generated ABI facts/header and frontend B/C convergence, built-B identity, "
        "exact exported module staging and private shim-only exports"
    )


def main():
    # The default selection checks stage convergence through the lexer and the
    # whole frontend, which imports every compiler module. --corpus compares
    # every other checked-in source across the two stages; slow suites run it.
    arguments = sys.argv[1:]
    whole_corpus = arguments[-1:] == ["--corpus"]
    if whole_corpus:
        arguments = arguments[:-1]
    current1, current2, root, built_a, built_b = (Path(value).resolve() for value in arguments)
    with tempfile.TemporaryDirectory(prefix="hosted-lexer-bootstrap-") as temporary:
        work = Path(temporary)
        outputs = [work / "current-c1.s", work / "current-c2.s"]
        module_root = work / "compiler-modules"
        stage_modules(root, module_root)
        records = []
        corpus = sources(root)
        require(root / "compiler/lexer.au" in corpus, "lexer self-rebuild input is missing")
        require(root / "compiler/frontend.au" in corpus, "whole frontend self-rebuild input is missing")
        compiler_sources = {root / "compiler" / name for name in COMPILER_MODULES}
        require(compiler_sources.issubset(corpus), "a real compiler module is missing from self-rebuild coverage")
        convergence = {root / "compiler/lexer.au", root / "compiler/frontend.au"}
        corpus = [source for source in corpus if (source in convergence) != whole_corpus]
        for source in corpus:
            runs = []
            for compiler, output in zip((current1, current2), outputs, strict=True):
                output.write_bytes(b"preserve on rejection\n")
                runs.append(
                    subprocess.run(
                        [
                            str(compiler),
                            "--module-root",
                            str(module_root if source in compiler_sources else root / "library"),
                            str(source),
                            "-o",
                            str(output),
                        ],
                        capture_output=True,
                        timeout=30,
                        check=False,
                    )
                )
            for run, output in zip(runs, outputs, strict=True):
                require(
                    run.returncode in (0, 1),
                    f"compiler crash or invocation failure: {source}: {run.returncode}",
                )
                require(b"AU9001" not in run.stderr, f"internal compiler failure: {source}")
                if run.returncode == 1:
                    require(
                        output.read_bytes() == b"preserve on rejection\n",
                        f"rejected output changed: {source}",
                    )
            require(
                (runs[0].returncode, runs[0].stdout, runs[0].stderr)
                == (runs[1].returncode, runs[1].stdout, runs[1].stderr),
                f"compiler diagnostics differ: {source}",
            )
            require(
                outputs[0].read_bytes() == outputs[1].read_bytes(),
                f"assembly/output preservation differs: {source}",
            )
            if source == root / "compiler/lexer.au":
                require(runs[0].returncode == 0, "lexer self-rebuild failed")
                print("PASS current C2 lexer rebuild SHA256 " + hashlib.sha256(outputs[1].read_bytes()).hexdigest())
            # Vocabulary/result-only modules have no concrete free function;
            # the complete frontend graph compiles and covers their declarations.
            vocabulary_modules = {"resolution_kinds.au", "lowering_kinds.au", "lowering_errors.au"}
            if source in compiler_sources and source.name not in vocabulary_modules:
                require(runs[0].returncode == 0, f"compiler module self-rebuild failed: {source.name}")
            if source == root / "compiler/frontend.au":
                require(runs[0].returncode == 0, "whole frontend self-rebuild failed")
                frontend_bootstrap(current1, current2, root, work, built_a, built_b)
            records.append({"source": str(source.relative_to(root)), "status": runs[0].returncode})
        require(len(records) > 1, "source corpus is empty")
        print(
            ("PASS current C1/C2 corpus" if whole_corpus else "PASS current C1/C2 lexer and frontend")
            + " diagnostics, assembly and output preservation: "
            + json.dumps(
                {
                    "sources": len(records),
                    "accepted": sum(row["status"] == 0 for row in records),
                }
            )
        )


if __name__ == "__main__":
    main()
