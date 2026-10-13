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
        ("compiler_ir_metadata::CallableOptions", 40),
        ("compiler_ir_metadata::CallableRow", 128),
        ("compiler_ir_metadata::SlotRow", 40),
        ("compiler_ir_metadata::InputCounts", 80),
        ("compiler_ir_metadata::MetadataStore", 504),
    ):
        _, entry = abi_declaration(facts, "records", source)
        require(entry["reserved"] == extent and entry["alignment"] == 8, f"frontend layout changed: {source}")
    require(
        "struct alignas(8) MetadataCreate {" in generated
        and "struct alignas(8) MetadataRelease {" in generated
        and "aurora::hosted_abi::compiler_ir_metadata::InputCounts counts{};" in generated
        and "std::int64_t callableCount{};" in generated
        and "std::int64_t slotCount{};" in generated
        and "metadataStore_typesBytes = 32;" in generated
        and "metadataStore_callablesBytes = 32;" in generated
        and "metadataStore_slotsBytes = 32;" in generated
        and "metadataCallableRowPhysicalBytes = 128;" in generated
        and "metadataRawTypeRowPhysicalBytes = 64;" in generated
        and "metadataSlotRowPhysicalBytes = 40;" in generated,
        "metadata arguments or closed owner/row physical bindings were omitted",
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
                entry["receiver"] = None
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
    for parameter, name in ((2, "callable-count"), (3, "slot-count")):
        for mutation in ("missing", "type", "offset"):
            changed = deepcopy(facts)
            _, entry = abi_declaration(changed, "functions", "compiler_frontend::metadata_create")
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
            raise AssertionError(f"unsafe metadata {name} argument accepted: {mutation}")
    for operation in ("create", "release", "allocated", "run", "error"):
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
    for operation in ("allocated", "run", "error"):
        changed = deepcopy(facts)
        _, entry = abi_declaration(changed, "functions", "compiler_frontend::metadata_" + operation)
        entry["receiver_mutable"] = operation != "run"
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
                entry["receiver"] = None
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
                entry["receiver"] = None
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
    print("PASS generic source-spelled ABI records/enums, nested layout and exact lowering/metadata bridge rejection")


def message_generation(facts, root):
    from bootstrap_frontend import lowering_messages, metadata_messages

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
            "        paired_borrowed_span_production\n",
            "        paired_borrowed_span_production\n        //: dangling\n",
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


def frontend_bootstrap(current1, current2, root, work, built_a, built_b):
    abi_generation(json.loads(built_b.with_suffix(".abi.json").read_text()))
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
        for operation in ("create", "release", "allocated", "run", "error")
    )
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
