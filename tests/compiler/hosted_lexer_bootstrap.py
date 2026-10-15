#!/usr/bin/env python3
"""Require current compiler frontend convergence and exact source diagnostics."""

from pathlib import Path
from copy import deepcopy
import hashlib
import io
import json
import os
import signal
import subprocess
import sys
import tempfile


def stage_modules(root, destination):
    # Import the actual build staging helper: both paths copy exported modules
    # exactly, without rewriting their namespaces or interface declarations.
    sys.path.insert(0, str(root / "scripts"))
    from bootstrap_frontend import stage_modules as stage

    stage(destination, frontend_modules(root))


# Every .au file in compiler/ is a frontend module.
COMPILER_MODULES = tuple(sorted(path.name for path in (Path(__file__).resolve().parents[2] / "compiler").glob("*.au")))
FRONTEND_LIBRARY_MODULES = ("std/decimal_digits.au",)


def frontend_modules(root):
    return [root / "compiler" / name for name in COMPILER_MODULES] + [
        root / "library" / name for name in FRONTEND_LIBRARY_MODULES
    ]


EMITTER_OPERATIONS = (
    "create",
    "release",
    "status",
    "add_retained",
    "prepare_facts",
    "append_name",
    "add_abi_name",
    "run",
    "facts",
    "size",
    "chunk",
)


INITIALIZATION_SERVICE_OPERATIONS = (
    "payload_bytes",
    "acquire_service_loan",
    "release_service_loan",
    "service_unsuspended",
    "validate_service_call",
    "complete_service_call",
    "service_loans_closed",
    "same_service_loans",
)

INITIALIZATION_OPERATIONS = (
    "create",
    "release",
    "allocated",
    "status",
    "initialize",
    "slot_count",
    "word_count",
    "retained_count",
    "current_count",
    "retained_count_at",
    "load",
    "retain",
    "join",
    "scalar_state",
    "write_scalar",
    "object_initialized",
    "object_pristine",
    "object_was_constructed",
    "object_completion",
    "receiver_field_state",
    "write_receiver_field",
    "receiver_completion",
    "mark_object",
    "clear_object",
    "array_first_missing",
    "clear_array",
) + INITIALIZATION_SERVICE_OPERATIONS


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
        *(str(source) for source in frontend_modules(root)),
        str(root / "compiler/hosted_lexer.S"),
        str(root / "compiler/hosted_parser.S"),
        str(root / "compiler/hosted_resolver.S"),
        str(root / "compiler/hosted_graph.S"),
        str(root / "compiler/hosted_ir_metadata.S"),
        str(root / "compiler/hosted_ir_instructions.S"),
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
        ("compiler_ir_metadata::FlagMasks", 120),
        ("compiler_ir_metadata::ReceiverShape", 24),
        ("compiler_ir_metadata::CallableOptions", 40),
        ("compiler_ir_metadata::CallableRow", 120),
        ("compiler_ir_metadata::SlotRow", 40),
        ("compiler_ir_metadata::InputCounts", 80),
        ("compiler_ir_metadata::MetadataStore", 512),
        ("compiler_ir_instructions::RawInstructionRow", 64),
        ("compiler_ir_instructions::RawOperandRow", 40),
        ("compiler_ir_instructions::CodeRow", 32),
        ("compiler_ir_instructions::BodyRow", 32),
        ("compiler_ir_instructions::InstructionCounts", 32),
        ("compiler_ir_instructions::InstructionStore", 176),
        ("compiler_ir_initialization::InitializationWorkspace", 248),
        ("compiler_ir_initialization::ServiceLoan", 32),
    ):
        _, entry = abi_declaration(facts, "records", source)
        require(entry["reserved"] == extent and entry["alignment"] == 8, f"frontend layout changed: {source}")
    require(
        "struct alignas(8) MetadataCreate {" in generated
        and "struct alignas(8) MetadataInitialize {" in generated
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
        all(f"struct alignas(8) {name} {{" in generated for name in ("InstructionsCreate", "InstructionsRelease"))
        and all(
            f"instructionStore_{pool}Bytes = 32;" in generated
            for pool in ("instructions", "operands", "literals", "codeOrder", "bodies")
        )
        and all(
            f"instruction{row}PhysicalBytes = {width};" in generated
            for row, width in (("RawInstructionRow", 64), ("RawOperandRow", 40), ("CodeRow", 32), ("BodyRow", 32))
        ),
        "instruction arguments or closed owner/row physical bindings were omitted",
    )
    _, flag_masks = abi_declaration(facts, "records", "compiler_ir_metadata::FlagMasks")
    require(
        [(field["name"], field["kind"], field["bytes"]) for field in flag_masks["fields"]]
        == [
            (name, "u64", 8)
            for name in (
                "classLayout",
                "classFields",
                "classStorage",
                "classArrayCarrier",
                "callableReceiver",
                "callableSpanSummary",
                "receiverMutable",
                "receiverConstructor",
                "receiverPublic",
                "serviceConsole",
                "serviceDisplay",
                "serviceIommu",
                "flowLeader",
                "flowFallthrough",
                "flowReached",
            )
        ],
        "metadata flag table is not the named full-width source record",
    )
    for source, member in (
        ("ClassRow", "membershipBits"),
        ("CallableRow", "flags"),
        ("CallableOptions", "flags"),
        ("ReceiverShape", "flags"),
    ):
        _, row = abi_declaration(facts, "records", "compiler_ir_metadata::" + source)
        field = next(field for field in row["fields"] if field["name"] == member)
        require(field["kind"] == "u64" and field["bytes"] == 8, "metadata flags were narrowed or signed")
    _, code_row = abi_declaration(facts, "records", "compiler_ir_instructions::CodeRow")
    require(
        [(field["name"], field["kind"], field["offset"], field["bytes"]) for field in code_row["fields"]]
        == [
            ("instructionId", "i64", 0, 8),
            ("targetPosition", "i64", 8, 8),
            ("flowFlags", "u64", 16, 8),
            ("scratchValue", "i64", 24, 8),
        ],
        "instruction identity, structural facts or scratch layout changed",
    )
    _, body_row = abi_declaration(facts, "records", "compiler_ir_instructions::BodyRow")
    require(
        [(field["name"], field["kind"], field["offset"], field["bytes"]) for field in body_row["fields"]]
        == [
            ("codeBegin", "i64", 0, 8),
            ("codeCapacity", "i64", 8, 8),
            ("retainedCount", "i64", 16, 8),
            ("unreachableAfter", "i64", 24, 8),
        ],
        "instruction body ranges or source-derived unreachable boundary layout changed",
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
        and all(
            f"initializationWorkspace_{pool}Bytes = 32;" in generated
            for pool in ("currentWords", "retainedWords", "retainedCounts", "serviceLoans")
        )
        and "initializationWordPairPhysicalBytes = 16;" in generated
        and "initializationCountPairPhysicalBytes = 16;" in generated
        and "initializationServiceLoanPhysicalBytes = 32;" in generated,
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
    # All entries use the same production root validator. Sample both authority
    # directions here; the complete signature and export checks still cover all.
    for operation in ("acquire_service_loan", "validate_service_call"):
        for mutation in ("authority", "pair"):
            changed = deepcopy(facts)
            _, entry = abi_declaration(changed, "functions", "compiler_frontend::initialization_" + operation)
            if mutation == "authority":
                entry["borrowed_roots"][0]["mutable"] = not entry["borrowed_roots"][0]["mutable"]
            else:
                _, pair = abi_declaration(facts, "functions", "compiler_frontend::initialization_initialize")
                for field in ("borrowed_roots", "borrowed_root_count", "borrowed_root_abi"):
                    entry[field] = deepcopy(pair[field])
            try:
                frontend_abi_header(changed)
            except ValueError:
                continue
            raise AssertionError(f"unsafe initialization service root accepted: {operation}/{mutation}")
    for operation in (
        "initialize",
        "scalar_state",
        "write_scalar",
        "object_initialized",
        "object_pristine",
        "object_was_constructed",
        "object_completion",
        "receiver_field_state",
        "write_receiver_field",
        "receiver_completion",
        "mark_object",
        "clear_object",
        "array_first_missing",
        "clear_array",
    ):
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
        ("InitializationWorkspace", "currentWords"),
        ("InitializationWorkspace", "retainedWords"),
        ("InitializationWorkspace", "retainedCounts"),
        ("InitializationWorkspace", "serviceLoans"),
        ("InitializationWorkspace", "retainedCount"),
        ("InitializationWorkspace", "objectBegin"),
        ("InitializationWorkspace", "objectCount"),
        ("InitializationWorkspace", "receiverBegin"),
        ("InitializationWorkspace", "receiverCount"),
        ("InitializationWorkspace", "serviceCapacity"),
        ("InitializationWorkspace", "factCount"),
        ("WordPair", "mustBits"),
        ("CountPair", "mayCount"),
        ("ServiceLoan", "loanId"),
        ("ServiceLoan", "rootOffset"),
        ("ServiceLoan", "serviceKind"),
        ("ServiceLoan", "calledValue"),
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
    for pool, row in (
        ("instructions", "RawInstructionRow"),
        ("operands", "RawOperandRow"),
        ("literals", None),
        ("codeOrder", "CodeRow"),
        ("bodies", "BodyRow"),
    ):
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
        ("initialize", 1, "callable-count"),
        ("initialize", 2, "slot-count"),
        ("initialize", 3, "instruction-begin"),
        ("object_leaf_root", 0, "callable"),
        ("object_leaf_root", 1, "offset"),
        ("byte_array_element_root", 0, "callable"),
        ("byte_array_element_root", 1, "offset"),
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
    for operation in (
        "flag_masks",
        "create",
        "initialize",
        "release",
        "allocated",
        "run",
        "error",
        "object_leaf_root",
        "byte_array_element_root",
    ):
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
    for operation in ("initialize", "allocated", "run", "error", "object_leaf_root", "byte_array_element_root"):
        changed = deepcopy(facts)
        _, entry = abi_declaration(changed, "functions", "compiler_frontend::metadata_" + operation)
        entry["borrowed_roots"][0]["mutable"] = operation not in ("initialize", "run")
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
            "metadata_row_stride",
            "metadata_narrow_leaf",
            "metadata_slot_stride",
            "metadata_slot_narrow_leaf",
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
    print(
        "PASS generic source-spelled ABI records/enums, nested layout and exact "
        "lowering/metadata/instruction/initialization bridge rejection"
    )


def emitter_generation(facts):
    from bootstrap_frontend import abi_declaration, frontend_abi_header, frontend_bridge, normalize_function_abi

    generated = frontend_abi_header(facts)
    workspace, _ = abi_declaration(facts, "records", "compiler_x86::EmitWorkspace")
    metadata, _ = abi_declaration(facts, "records", "compiler_ir_metadata::MetadataStore")
    instructions, _ = abi_declaration(facts, "records", "compiler_ir_instructions::InstructionStore")
    status, _ = abi_declaration(facts, "enums", "compiler_x86::EmitStatus")
    require(
        all(
            f"struct alignas(8) {name} {{" in generated
            for name in ("EmitterCreate", "EmitterRelease", "EmitterNameInput", "EmitterAbiNameInput")
        )
        and "aurora::hosted_abi::compiler_x86::EmitWorkspace workspace{};" in generated
        and "BuiltinSpan name{};" in generated
        and "aurora::hosted_abi::compiler_x86::AbiNameRow name{};" in generated,
        "emitter consuming-owner or copied name argument records were omitted",
    )
    chunk_symbol, chunk = abi_declaration(facts, "records", "compiler_x86::EmitChunk")
    require(
        (chunk["size"], chunk["reserved"], chunk["alignment"]) == (520, 520, 8)
        and [
            (field["name"], field["kind"], field["offset"], field["bytes"], field.get("array_length", 0))
            for field in chunk["fields"]
        ]
        == [("payload", "u8", 0, 512, 512), ("byteCount", "i64", 512, 8, 0)]
        and "std::array<std::uint8_t, 512> payload{};" in generated
        and "static_assert(sizeof(EmitChunk) == 520 && alignof(EmitChunk) == 8);" in generated,
        "emitter chunk lost its bounded byte payload or physical count field",
    )
    _, read_chunk = abi_declaration(facts, "functions", "compiler_frontend::emitter_chunk")
    require(
        read_chunk["result"] == dict(kind="class", type_name=chunk_symbol, bytes=520),
        "emitter chunk result is not the exact copied bounded record",
    )
    _, name_row = abi_declaration(facts, "records", "compiler_x86::AbiNameRow")
    require(
        (name_row["size"], name_row["reserved"], name_row["alignment"]) == (40, 40, 8)
        and [(field["name"], field["kind"], field["offset"], field["bytes"]) for field in name_row["fields"]]
        == [
            (name, "i64", index * 8, 8)
            for index, name in enumerate(("categoryValue", "identityValue", "memberValue", "beginValue", "countValue"))
        ],
        "emitter ABI name input lost its exact source-owned scalar selectors",
    )
    source = "compiler_frontend::emitter_run"
    run_symbol, run = abi_declaration(facts, "functions", source)
    require(
        run["receiver"] is None
        and run["receiver_mutable"] is None
        and run["borrowed_root_count"] == 3
        and run["borrowed_roots"]
        == [
            dict(ordinal=0, selector=0, type_name=workspace, mutable=True),
            dict(ordinal=1, selector=-1, type_name=metadata, mutable=False),
            dict(ordinal=2, selector=-2, type_name=instructions, mutable=False),
        ]
        and run["borrowed_root_abi"]
        == dict(
            kind="tuple",
            register="r10",
            tuple_payload_bytes=24,
            tuple_reserved_bytes=32,
            saved_root_reserved_bytes=32,
        )
        and run["parameters"] == [dict(offset=0, bytes=8, kind="i64"), dict(offset=8, bytes=8, kind="i64")]
        and run["parameter_bytes"] == 16
        and run["result"] == dict(kind="enum", type_name=status, bytes=8)
        and normalize_function_abi(facts, run) == run,
        "actual emitter run did not retain its ordered three-root scalar-tail ABI",
    )
    require(
        frontend_bridge("call __aurora_frontend_emitter_run\n", facts) == "call " + run_symbol + "\n",
        "actual three-root emitter bridge resolved a different entry",
    )

    def changed_entry(group, source_name):
        symbol, original = abi_declaration(facts, group, source_name)
        entry = deepcopy(original)
        changed = dict(facts)
        changed[group] = dict(facts[group])
        changed[group][symbol] = entry
        return changed, entry

    # Sample the distinct entry shapes. The positive whole-frontend inventory
    # above validates every entry; avoid copying/regenerating all facts once per
    # operation merely to exercise the same closed signature checks repeatedly.
    for operation, mutation in (("create", "result"), ("append_name", "parameters"), ("facts", "root")):
        changed, entry = changed_entry("functions", "compiler_frontend::emitter_" + operation)
        if mutation == "result":
            entry["result"]["bytes"] += 8
        elif mutation == "parameters":
            entry["parameters"][0]["bytes"] += 8
        else:
            entry["source_name"] = "fixture::removed_emitter_" + operation
        try:
            frontend_abi_header(changed)
        except ValueError:
            continue
        raise AssertionError(f"unsafe emitter bridge accepted: {operation}/{mutation}")
    for operation in ("status", "run"):
        changed, entry = changed_entry("functions", "compiler_frontend::emitter_" + operation)
        entry["borrowed_roots"][0]["mutable"] = not entry["borrowed_roots"][0]["mutable"]
        try:
            frontend_abi_header(changed)
        except ValueError:
            continue
        raise AssertionError("unsafe emitter owner authority accepted: " + operation)
    mutations = (
        ("root order", lambda f: f["borrowed_roots"].reverse()),
        ("missing root", lambda f: f["borrowed_roots"].pop()),
        ("duplicate root type", lambda f: f["borrowed_roots"][2].__setitem__("type_name", metadata)),
        ("boolean count", lambda f: f.__setitem__("borrowed_root_count", True)),
        ("missing scalar tail", lambda f: f["parameters"].pop()),
        ("copied tail", lambda f: f["parameters"][0].update(kind="class", type_name=chunk_symbol, bytes=520)),
        ("copied result", lambda f: f["result"].update(kind="class", type_name=chunk_symbol, bytes=520)),
        ("tuple padding", lambda f: f["borrowed_root_abi"].__setitem__("tuple_reserved_bytes", 24)),
    )
    for description, mutation in mutations:
        changed, entry = changed_entry("functions", source)
        mutation(entry)
        try:
            frontend_abi_header(changed)
        except ValueError:
            continue
        raise AssertionError("unsafe three-root emitter ABI accepted: " + description)
    for field, value in (("array_length", 0), ("array_length", 513), ("bytes", 511), ("kind", "i64")):
        changed, entry = changed_entry("records", "compiler_x86::EmitChunk")
        entry["fields"][0][field] = value
        try:
            frontend_abi_header(changed)
        except ValueError:
            continue
        raise AssertionError(f"unsafe bounded emitter chunk accepted: {field}={value}")
    print("PASS exact emitter bridges, actual three-root transport and bounded copied byte chunk")


def pass_bridge_generation(facts):
    from bootstrap_frontend import abi_function_symbol, frontend_abi_header, frontend_bridge

    assembly, header = frontend_bridge(None, facts), frontend_abi_header(facts)
    operations = ["emitter_" + name for name in EMITTER_OPERATIONS]
    operations += ["initialization_" + name for name in INITIALIZATION_OPERATIONS]
    require(assembly.count(".globl ") == len(operations), "private bridge inventory drift")
    for alias in operations:
        require(f".globl aurora_hosted_{alias}\n" in assembly, "missing private host entry: " + alias)
        require(f" aurora_hosted_{alias}(" in header, "missing private host declaration: " + alias)
    # Independent examples of all five transports, including the longest tail.
    for alias, moves, signature in (
        ("emitter_create", [("rdi", "r11"), ("rsi", "r10")], "void *(const void *, void *)"),
        ("initialization_release", [("rdi", "r11")], "void *(void *)"),
        (
            "emitter_run",
            [("rdi", "r10"), ("rsi", "rdi"), ("rdx", "rsi")],
            "std::int64_t *(const void *, std::int64_t, std::int64_t)",
        ),
        ("emitter_append_name", [("rdi", "r10"), ("rsi", "r11")], "std::int64_t *(void *, const void *)"),
        (
            "emitter_chunk",
            [("rdi", "r10"), ("rsi", "rdi"), ("rdx", "rsi"), ("rcx", "r11")],
            "void *(const void *, std::int64_t, std::int64_t, void *)",
        ),
        (
            "initialization_validate_service_call",
            [("rdi", "r10"), ("rsi", "rdi"), ("rdx", "rsi"), ("rcx", "rdx"), ("r8", "rcx")],
            "std::int64_t *(const void *, std::int64_t, std::int64_t, std::int64_t, std::int64_t)",
        ),
    ):
        host = "aurora_hosted_" + alias
        body = f"{host}:\n" + "".join(f"    movq %{source}, %{target}\n" for source, target in moves)
        body += "    jmp " + abi_function_symbol(facts, "compiler_frontend::" + alias) + "\n"
        require(body in assembly, "private register transport drift: " + alias)
        require(signature.replace("*(", host + "(") + " noexcept;" in header, "private host signature drift: " + alias)
    print("PASS closed host inventory and all five generated pass transports")


def borrowed_root_generation(facts):
    from bootstrap_frontend import abi_declaration, frontend_abi_header, frontend_bridge, normalize_function_abi

    require(type(facts["version"]) is int and facts["version"] == 2, "candidate must emit ABI facts v2")
    header = frontend_abi_header(facts)

    def legacy_function(function):
        function = deepcopy(function)
        roots = function.pop("borrowed_roots")
        count = function.pop("borrowed_root_count")
        function.pop("borrowed_root_abi")
        if count > 2 or (count == 2 and not roots[0]["mutable"]):
            raise ValueError("function cannot be represented by the paired source predecessor")
        if roots:
            require(function["receiver"] is None, "borrowed roots duplicated in genuine receiver")
            function["receiver"], function["receiver_mutable"] = roots[0]["type_name"], roots[0]["mutable"]
        function["borrowed_parameter"] = bool(count)
        function["second_receiver"] = dict(type_name=roots[1]["type_name"], mutable=False) if count == 2 else None
        function["root_count"] = count if count else int(function["receiver"] is not None)
        function["root_tuple_bytes"] = 16 if count == 2 else 0
        function["root_order"] = (
            ["receiver", "second_receiver"] if count == 2 else ["receiver"] if function["receiver"] is not None else []
        )
        return function

    # Preserve every predecessor-representable function, including the original
    # one/two-root bridges. New three-root and readonly-pair implementations have
    # no legacy encoding; keep their current facts while round-tripping only the
    # compatible projection. Normalization and exact bridge checks both run, so
    # an absent new bridge cannot make the legacy rejection cases pass vacuously.
    predecessor = deepcopy(facts)
    predecessor["version"] = 1
    predecessor["functions"] = {}
    incompatible = set()
    for symbol, function in facts["functions"].items():
        try:
            predecessor["functions"][symbol] = legacy_function(function)
        except ValueError:
            incompatible.add(symbol)

    def current_projection(document):
        restored = deepcopy(facts)
        for symbol, function in document["functions"].items():
            restored["functions"][symbol] = normalize_function_abi(document, function)
        return restored

    restored = current_projection(predecessor)
    for symbol, function in facts["functions"].items():
        if symbol not in incompatible:
            require(restored["functions"][symbol] == function, "paired predecessor normalization changed a function")
    run_symbol, run = abi_declaration(facts, "functions", "compiler_frontend::emitter_run")
    require(run_symbol in incompatible, "actual three-root emitter entered the paired legacy projection")
    try:
        legacy_function(run)
    except ValueError:
        pass
    else:
        raise AssertionError("three-root emitter silently lost a root in legacy conversion")
    require(frontend_abi_header(restored) == header, "paired predecessor/current normalization changed headers")
    bridge = "call __aurora_frontend_graph_run\ncall __aurora_frontend_lexer_next\n"
    require(frontend_bridge(bridge, restored) == frontend_bridge(bridge, facts), "predecessor/current bridge drift")

    def reject(document, source, mutation):
        changed = deepcopy(document)
        _, function = abi_declaration(changed, "functions", source)
        mutation(function)
        try:
            frontend_abi_header(current_projection(changed) if changed["version"] == 1 else changed)
        except ValueError:
            return
        raise AssertionError("unsafe borrowed-root facts accepted: " + source)

    pair_sources = (
        "graph_run",
        "instructions_admit",
        "instructions_structure",
        "initialization_initialize",
        "emitter_facts",
    )
    for alias in pair_sources:
        source = "compiler_frontend::" + alias
        for lane in (0, 1):
            for field, value in (
                ("ordinal", 1 - lane),
                ("ordinal", False),
                ("selector", -6),
                ("selector", -9223372036854775808),
                ("selector", False),
                ("type_name", "missing-root"),
                ("mutable", lane == 1),
                ("mutable", 1),
            ):
                reject(
                    facts,
                    source,
                    lambda f, lane=lane, field=field, value=value: f["borrowed_roots"][lane].__setitem__(field, value),
                )
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

    # Exercise every supported root-count/authority/scalar-tail combination in
    # addition to the actual three-root emitter checked above.
    _, pair = abi_declaration(facts, "functions", "compiler_frontend::graph_run")
    for count in range(1, 7):
        for mutable in (False, True):
            for tail in range(7 - count):
                function = deepcopy(pair)
                function["borrowed_root_count"] = count
                function["borrowed_roots"] = [
                    dict(
                        ordinal=i,
                        selector=-i,
                        type_name=pair["borrowed_roots"][i % 2]["type_name"],
                        mutable=mutable and i == 0,
                    )
                    for i in range(count)
                ]
                function["borrowed_root_abi"] = dict(
                    kind="direct" if count == 1 else "tuple",
                    register="r10",
                    tuple_payload_bytes=8 * count if count > 1 else 0,
                    tuple_reserved_bytes=16 * ((count + 1) // 2) if count > 1 else 0,
                    saved_root_reserved_bytes=16 * ((count + 1) // 2),
                )
                function["parameters"] = [dict(offset=8 * i, bytes=8, kind="i64") for i in range(tail)]
                function["parameter_bytes"] = 8 * tail
                require(normalize_function_abi(facts, function) == function, "bounded root normalization drift")
    print("PASS bounded borrowed-root facts and exact compatible paired-predecessor header normalization")


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
        and all(
            f'return "invalid typed IR: {message}";' in table
            for message in (
                "empty function body",
                "duplicate or invalid label",
                "unknown jump target",
                "unknown branch target",
                "reachable fallthrough without return",
                "unreachable semantic instruction",
            )
        ),
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
    from bootstrap_frontend import write_frontend_header
    from qemu_transport import run_logged

    def regenerate(compiler, output):
        stdout, stderr = io.BytesIO(), io.BytesIO()
        # This whole-frontend emission takes 25-30 seconds even on an idle host.
        # Reuse owned-process cleanup for the wrapper and its compiler child.
        status = run_logged(
            [
                sys.executable,
                "-B",
                str(root / "scripts/bootstrap_frontend.py"),
                *frontend_arguments(compiler, root, output),
            ],
            stdout,
            stderr=stderr,
            timeout=90,
            timeout_status=False,
        )
        diagnostic = stderr.getvalue()
        require(
            status == 0,
            f"whole frontend self-rebuild failed: {compiler}: {status}: {diagnostic.decode(errors='replace')}",
        )
        require(b"AU9001" not in diagnostic, f"internal compiler failure: {root / 'compiler/frontend.au'}")
        return stdout.getvalue(), diagnostic

    abi_generation(json.loads(built_b.with_suffix(".abi.json").read_text()))
    emitter_generation(json.loads(built_b.with_suffix(".abi.json").read_text()))
    pass_bridge_generation(json.loads(built_b.with_suffix(".abi.json").read_text()))
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
            "create_input",
            "create_workspace",
            "release_input",
            "release_workspace",
            "set_function",
            "set_edge",
            "run",
            "retained",
        )
    )
    entries.update(
        "aurora_hosted_metadata_" + operation
        for operation in (
            "flag_masks",
            "create",
            "initialize",
            "release",
            "allocated",
            "run",
            "error",
            "object_leaf_root",
            "byte_array_element_root",
        )
    )
    entries.update(
        "aurora_hosted_instructions_" + operation
        for operation in ("create", "release", "allocated", "admit", "structure", "publish", "error")
    )
    entries.update("aurora_hosted_initialization_" + operation for operation in INITIALIZATION_OPERATIONS)
    entries.update("aurora_hosted_emitter_" + operation for operation in EMITTER_OPERATIONS)
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
    units, diagnostics = [], []
    for number, compiler in enumerate((current1, current2), start=1):
        output = work / f"frontend-c{number}.s"
        diagnostics.append(regenerate(compiler, output))
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
        for name in FRONTEND_LIBRARY_MODULES:
            require(
                (work / "compiler-modules" / name).read_bytes() == (root / "library" / name).read_bytes(),
                f"staged frontend library module changed exported source: {name}",
            )
    require(diagnostics[0] == diagnostics[1], "whole frontend compiler diagnostics differ")
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
    # Both real stage compilations and all convergence comparisons above remain
    # mandatory. Header idempotence needs only the writer and those emitted facts,
    # not a third complete compilation of the same frontend.
    emitted_facts = json.loads(units[0].with_suffix(".abi.json").read_text())
    message_sources = (
        root / "compiler/lowering_errors.au",
        root / "compiler/ir_metadata_storage.au",
        root / "compiler/ir_instruction_storage.au",
    )
    write_frontend_header(emitted_facts, generated_header, *message_sources, header(built_b))
    require(
        generated_header.read_bytes() == expected and generated_header.stat().st_mtime_ns == old_mtime,
        "unchanged compiler ABI header was rewritten",
    )
    incompatible = work / "incompatible-shared.hpp"
    incompatible.write_bytes(b"incompatible shared host ABI\n")
    rejected_header = work / "rejected-output.hpp"
    sentinel = b"preserve prior header on incompatible ABI\n"
    rejected_header.write_bytes(sentinel)
    os.utime(rejected_header, ns=(old_mtime, old_mtime))
    try:
        write_frontend_header(emitted_facts, rejected_header, *message_sources, incompatible)
    except ValueError as error:
        require("stage2 ABI header differs" in str(error), "wrong shared-header compatibility rejection")
    else:
        raise AssertionError("incompatible shared-host ABI header was accepted")
    require(
        rejected_header.read_bytes() == sentinel and rejected_header.stat().st_mtime_ns == old_mtime,
        "incompatible shared-host ABI changed an existing header before rejection",
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
        frontend_library_sources = {root / "library" / name for name in FRONTEND_LIBRARY_MODULES}
        require(
            frontend_library_sources.issubset(corpus), "a frontend library module is missing from self-rebuild coverage"
        )
        convergence = {root / "compiler/lexer.au", root / "compiler/frontend.au"}
        corpus = [source for source in corpus if (source in convergence) != whole_corpus]
        for source in corpus:
            if source == root / "compiler/frontend.au":
                # The dedicated path compiles this graph with local bindings and
                # ABI facts. Lexer and corpus checks retain ordinary emission.
                frontend_bootstrap(current1, current2, root, work, built_a, built_b)
                records.append({"source": str(source.relative_to(root)), "status": 0})
                continue
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
            if source in frontend_library_sources:
                require(runs[0].returncode == 0, f"frontend library module self-rebuild failed: {source.name}")
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

    def terminate(signum, frame):
        # Let owned-process cleanup finish when Meson's outer deadline expires.
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminate)
    main()
