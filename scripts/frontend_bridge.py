#!/usr/bin/env python3
"""Single declaration table for the private compiler host bridge.

Rows specify source signatures/calls and existing transport policy. Physical
layouts and target symbols remain compiler-fact authorities.
"""

from pathlib import Path
import re
import sys

# Source signature, forwarding expression (direct/copy/move), argument record
# (name:fields[:scalar lanes]), and host policy (noexcept/discard[:alias]).
ROWS = (
    (
        "private_object_create(builtin::ByteRegion region) -> compiler_private_object::Workspace",
        "move compiler_private_object::create(region)",
        "PrivateObjectCreate:region",
        "noexcept",
    ),
    (
        "private_object_release(builtin::ByteRegion region, compiler_private_object::Workspace workspace) -> i64",
        "direct compiler_private_object::release(region, move(workspace))",
        "PrivateObjectRelease:region,workspace",
        "noexcept,discard",
    ),
    (
        "private_object_run(compiler_private_object::Workspace& workspace, builtin::span<const u8> source, "
        "builtin::span<const u8> wrapper, builtin::span<const u8> selected) -> compiler_x86::EmitStatus",
        "direct compiler_private_object::run(workspace, source, wrapper, selected)",
        "PrivateObjectRun:source,wrapper,selected",
        "noexcept",
    ),
    (
        "private_object_size(const compiler_private_object::Workspace& workspace) -> i64",
        "direct workspace.size()",
        "",
        "noexcept",
    ),
    (
        "private_object_chunk(const compiler_private_object::Workspace& workspace, i64 offset) -> "
        "compiler_x86::EmitChunk",
        "copy workspace.chunk(offset)",
        "",
        "noexcept",
    ),
    (
        "formatter_create(builtin::ByteRegion region) -> compiler_formatter::Workspace",
        "move compiler_formatter::create(region)",
        "FormatterCreate:region",
        "noexcept",
    ),
    (
        "formatter_release(builtin::ByteRegion region, compiler_formatter::Workspace workspace) -> i64",
        "direct compiler_formatter::release(region, move(workspace))",
        "FormatterRelease:region,workspace",
        "noexcept,discard",
    ),
    (
        "formatter_prepare(compiler_formatter::Workspace& workspace, builtin::span<const u8> source) -> bool",
        "direct workspace.begin(source)",
        "FormatterInput:source",
        "noexcept",
    ),
    (
        "formatter_run(builtin::ByteRegion region, compiler_formatter::Workspace workspace, bool layout) -> "
        "compiler_formatter::Workspace",
        "move compiler_formatter::run(region, move(workspace), layout)",
        "FormatterRun:region,workspace,layout",
        "noexcept",
    ),
    (
        "formatter_chunk(const compiler_formatter::Workspace& workspace, i64 offset) -> compiler_x86::EmitChunk",
        "copy workspace.chunk(offset)",
        "",
        "noexcept",
    ),
    (
        "formatter_finding(const compiler_formatter::Workspace& workspace, i64 index) -> compiler_formatter::Row",
        "copy workspace.read_finding(index)",
        "",
        "noexcept",
    ),
    (
        "formatter_diagnostic(const compiler_formatter::Workspace& workspace, i64 index, i64 offset) -> "
        "compiler_resolver::Report",
        "copy compiler_formatter::diagnostic(workspace, index, offset)",
        "",
        "noexcept",
    ),
    (
        "object_report(compiler_x86::EmitStatus status, bool wrapper, i64 offset) -> compiler_resolver::Report",
        "copy compiler_resolver::object_report(status, wrapper, offset)",
        "ObjectReport:status,wrapper,offset",
        "noexcept",
    ),
    (
        "emitter_object_create(builtin::ByteRegion region) -> compiler_x86::ObjectWorkspace",
        "move compiler_x86::object_create(region)",
        "EmitterObjectCreate:region",
        "noexcept",
    ),
    (
        "emitter_object_release(builtin::ByteRegion region, compiler_x86::ObjectWorkspace workspace) -> i64",
        "direct compiler_x86::object_release(region, move(workspace))",
        "EmitterObjectRelease:region,workspace",
        "noexcept,discard",
    ),
    (
        "emitter_wrapper_run(compiler_x86::ObjectWorkspace& workspace, builtin::span<const u8> recipe) -> "
        "compiler_x86::EmitStatus",
        "direct compiler_frontend_wrapper::run(workspace, recipe)",
        "EmitterWrapperInput:recipe",
        "noexcept",
    ),
    (
        "emitter_object_size(const compiler_x86::ObjectWorkspace& workspace) -> i64",
        "direct workspace.size()",
        "",
        "noexcept",
    ),
    (
        "emitter_object_chunk(const compiler_x86::ObjectWorkspace& workspace, i64 offset) -> compiler_x86::EmitChunk",
        "copy workspace.chunk(offset)",
        "",
        "noexcept",
    ),
    (
        "parser_create(builtin::ByteRegion region, i64 capacity) -> compiler_parser::AstArena",
        "move compiler_parser::create(region, capacity)",
        "ParserCreate:region,capacity",
        "",
    ),
    (
        "parser_source(compiler_parser::AstArena& arena, builtin::span<const u8> source) -> "
        "compiler_resolver::SourceResult",
        "copy compiler_resolver::parse_source(arena, source)",
        "ParserSourceInput:source",
        "",
    ),
    (
        "parser_release(builtin::ByteRegion region, compiler_parser::AstArena arena) -> i64",
        "direct compiler_parser::release(region, move(arena))",
        "ParserRelease:region,arena",
        "discard",
    ),
    (
        "resolver_create(builtin::ByteRegion region) -> compiler_resolver::Session",
        "move compiler_resolver::create(region)",
        "ResolverCreate:region",
        "",
    ),
    (
        "resolver_release(builtin::ByteRegion region, compiler_resolver::Session session) -> i64",
        "direct compiler_resolver::release(region, move(session))",
        "ResolverRelease:region,session",
        "discard",
    ),
    (
        "resolver_append_source(compiler_resolver::Session& session, builtin::span<const u8> source, "
        "compiler_resolver::SourceResult result) -> i64",
        "direct compiler_resolver::load_source(session, source, result)",
        "ResolverSourceInput:source,result",
        "",
    ),
    (
        "resolver_ingest(compiler_resolver::Session& session, const compiler_parser::AstArena& parsed) -> i64",
        "direct compiler_resolver::ingest_source(session, parsed)",
        "",
        "",
    ),
    (
        "resolver_name_chunk(builtin::span<const u8> source, i64 begin, i64 end, i64 offset, bool path) -> "
        "compiler_resolver::LinkageChunk",
        "copy compiler_resolver::name_chunk(source, begin, end, offset, path)",
        "ResolverNameInput:source,begin,end,offset,path",
        "",
    ),
    (
        "resolver_order_module(compiler_resolver::Session& session, i64 module_id, i64 order, i64 scope, bool "
        "root) -> bool",
        "direct compiler_resolver::order_named_module(session, module_id, order, scope, root)",
        "ResolverOrderInput:module,order,scope,root:0,1,2,3",
        "",
    ),
    (
        "resolver_graph_step(compiler_resolver::Session& session, i64 root, i64 roots) -> compiler_resolver::WorkRow",
        "copy compiler_resolver::load_step(session, root, roots)",
        "",
        "",
    ),
    ("resolver_run(compiler_resolver::Session& session) -> i64", "direct compiler_resolver::run(session)", "", ""),
    (
        "resolver_report(const compiler_resolver::Session& session, i64 offset) -> compiler_resolver::Report",
        "copy compiler_resolver::report(session, offset)",
        "",
        "",
    ),
    (
        "resolver_source_report(builtin::span<const u8> source, compiler_resolver::SourceResult result, "
        "compiler_parser::Stop stop, i64 offset) -> compiler_resolver::Report",
        "copy compiler_resolver::source_report(source, result, stop, offset)",
        "ResolverSourceReport:source,result,stop,offset",
        "",
    ),
    (
        "lowering_begin(compiler_resolver::Session& session, i64 mode) -> i64",
        "direct compiler_lowering::begin_lowering(session, mode)",
        "",
        "noexcept",
    ),
    (
        "lowering_run(compiler_resolver::Session& session) -> compiler_lowering::LoweringResult",
        "copy compiler_lowering::run_lowering(session)",
        "",
        "noexcept",
    ),
    (
        "pipeline_run(builtin::ByteRegion region, compiler_resolver::Session session, i64 root, i64 diagnostic, "
        "u64 options) -> compiler_pipeline::Result",
        "move compiler_pipeline::run(region, move(session), root, diagnostic, options)",
        "PipelineRun:region,session,root,diagnostic,options",
        "noexcept",
    ),
    (
        "pipeline_release(builtin::ByteRegion region, compiler_pipeline::Result result) -> i64",
        "direct compiler_pipeline::release(region, move(result))",
        "PipelineRelease:region,result",
        "noexcept,discard",
    ),
    (
        "pipeline_report(const compiler_pipeline::Result& result) -> compiler_pipeline::Report",
        "copy result.report()",
        "",
        "noexcept",
    ),
    (
        "pipeline_diagnostic(const compiler_pipeline::Result& result, i64 index, i64 offset) -> "
        "compiler_resolver::Report",
        "copy compiler_pipeline::diagnostic(result, index, offset)",
        "",
        "noexcept",
    ),
    (
        "pipeline_chunk(const compiler_pipeline::Result& result, compiler_x86::Artifact artifact, i64 offset) -> "
        "compiler_x86::EmitChunk",
        "copy result.chunk(artifact, offset)",
        "",
        "noexcept",
    ),
)

# Rows over internal stores that only the IR, lexer, parser and lowering test
# drivers call.
ROWS += (
    (
        "lexer_next(builtin::span<const u8> source, compiler_lexer::Cursor cursor) -> compiler_lexer::Lexeme",
        "copy compiler_lexer::next_lexeme(source, cursor)",
        "LexerInput:source,cursor",
        ":lexer_invoke",
    ),
    (
        "parser_parse(compiler_parser::AstArena& arena, builtin::span<const u8> source, "
        "compiler_lexer::Cursor cursor, compiler_parser::Stop stop, compiler_parser::TypeContext context, i64 "
        "enum_count) -> compiler_parser::ParseResult",
        "copy compiler_parser::parse(arena, source, cursor, stop, context, enum_count)",
        "ParserInput:source,cursor,stop,context,enum_count",
        "",
    ),
    (
        "parser_admit(compiler_parser::AstArena& arena, builtin::span<const u8> source, i64 root, "
        "compiler_parser::AdmissionConfig configuration) -> compiler_parser::AdmissionResult",
        "copy compiler_parser::admit(arena, source, root, configuration)",
        "AdmissionInput:source,root,configuration",
        "",
    ),
    (
        "parser_node_count(const compiler_parser::AstArena& arena) -> i64",
        "direct compiler_parser::node_count(arena)",
        "",
        ":parser_count",
    ),
    (
        "parser_edge_count(const compiler_parser::AstArena& arena) -> i64",
        "direct compiler_parser::edge_count(arena)",
        "",
        ":parser_edges",
    ),
    (
        "parser_type_count(const compiler_parser::AstArena& arena) -> i64",
        "direct compiler_parser::type_count(arena)",
        "",
        ":parser_types",
    ),
    (
        "parser_syntax_count(const compiler_parser::AstArena& arena) -> i64",
        "direct compiler_parser::syntax_count(arena)",
        "",
        "",
    ),
    (
        "parser_read_node(const compiler_parser::AstArena& arena, i64 index) -> compiler_parser::AstNode",
        "copy compiler_parser::read_node(arena, index)",
        "",
        ":parser_read",
    ),
    (
        "parser_read_edge(const compiler_parser::AstArena& arena, i64 index) -> compiler_parser::ChildEdge",
        "copy compiler_parser::read_edge(arena, index)",
        "",
        ":parser_edge",
    ),
    (
        "parser_read_type(const compiler_parser::AstArena& arena, i64 index) -> compiler_parser::TypeSyntax",
        "copy compiler_parser::read_type(arena, index)",
        "",
        ":parser_type",
    ),
    (
        "parser_read_syntax(const compiler_parser::AstArena& arena, i64 index) -> compiler_parser::SyntaxNode",
        "copy compiler_parser::read_syntax(arena, index)",
        "",
        ":parser_syntax",
    ),
    (
        "resolver_count(const compiler_resolver::Session& session, i64 pool) -> i64",
        "direct compiler_resolver::count(session, pool)",
        "",
        "",
    ),
    (
        "resolver_read_source(const compiler_resolver::Session& session, i64 index) -> i64",
        "direct compiler_resolver::read_source(session, index)",
        "",
        "",
    ),
    (
        "resolver_linkage_chunk(const compiler_resolver::Session& session, i64 symbol, i64 offset) -> "
        "compiler_resolver::LinkageChunk",
        "copy session.linkage_chunk(symbol, offset)",
        "",
        "",
    ),
    (
        "resolver_status(const compiler_resolver::Session& session) -> compiler_resolver::SessionStatus",
        "copy compiler_resolver::status(session)",
        "",
        "",
    ),
    (
        "resolver_read_meta(const compiler_resolver::Session& session, i64 index) -> compiler_resolver::MetaRow",
        "copy compiler_resolver::read_meta(session, index)",
        "",
        "",
    ),
    (
        "lowering_count(const compiler_resolver::Session& session, i64 pool) -> i64",
        "direct compiler_lowering::lowering_count(session, pool)",
        "",
        "noexcept",
    ),
    (
        "lowering_read_output(const compiler_resolver::Session& session, i64 index) -> compiler_lowering::OutputRow",
        "copy session.view_output(index)",
        "",
        "noexcept",
    ),
    (
        "lowering_read_operand(const compiler_resolver::Session& session, i64 index) -> compiler_lowering::OperandRow",
        "copy session.view_operand(index)",
        "",
        "noexcept",
    ),
    (
        "projection_name_capacity(const compiler_resolver::Session& session) -> i64",
        "direct compiler_lowering_projection::name_capacity(session)",
        "",
        "noexcept",
    ),
    (
        "projection_create(builtin::ByteRegion region, i64 outputs, i64 operands, i64 metadata, i64 nameCapacity) -> "
        "compiler_lowering_projection::ProjectionWorkspace",
        "move compiler_lowering_projection::create(region, outputs, operands, metadata, nameCapacity)",
        "ProjectionCreate:region,outputs,operands,metadata,nameCapacity",
        "noexcept",
    ),
    (
        "projection_release(builtin::ByteRegion region, compiler_lowering_projection::ProjectionWorkspace workspace) "
        "-> i64",
        "direct compiler_lowering_projection::release(region, move(workspace))",
        "ProjectionRelease:region,workspace",
        "noexcept,discard",
    ),
    (
        "projection_measure(const compiler_resolver::Session& session, "
        "compiler_lowering_projection::ProjectionWorkspace& workspace, "
        "compiler_ir_metadata::MetadataStore& metadata, compiler_ir_instructions::InstructionStore& instructions, "
        "i64 root, i64 diagnostic) -> i64",
        "direct compiler_lowering_projection::measure(session, workspace, metadata, instructions, root, diagnostic)",
        "",
        "noexcept",
    ),
    (
        "projection_fill(const compiler_resolver::Session& session, "
        "compiler_lowering_projection::ProjectionWorkspace& workspace, "
        "compiler_ir_metadata::MetadataStore& metadata, "
        "compiler_ir_instructions::InstructionStore& instructions) -> i64",
        "direct compiler_lowering_projection::fill(session, workspace, metadata, instructions)",
        "",
        "noexcept",
    ),
    (
        "projection_count(const compiler_lowering_projection::ProjectionWorkspace& workspace, i64 pool) -> i64",
        "direct workspace.count(pool)",
        "",
        "noexcept",
    ),
    (
        "metadata_flag_masks() -> compiler_ir_metadata::FlagMasks",
        "copy compiler_ir_metadata::flag_masks()",
        "",
        "noexcept",
    ),
    (
        "metadata_create(builtin::ByteRegion region) -> compiler_ir_metadata::MetadataStore",
        "move compiler_ir_metadata::create(region)",
        "MetadataCreate:region",
        "noexcept",
    ),
    (
        "metadata_initialize(compiler_ir_metadata::MetadataStore& store, compiler_ir_metadata::InputCounts "
        "counts, i64 callableCount, i64 slotCount, i64 instructionBegin) -> bool",
        "direct store.initialize(counts, callableCount, slotCount, instructionBegin)",
        "MetadataInitialize:counts,callableCount,slotCount,instructionBegin",
        "noexcept",
    ),
    (
        "metadata_release(builtin::ByteRegion region, compiler_ir_metadata::MetadataStore store) -> i64",
        "direct compiler_ir_metadata::release(region, move(store))",
        "MetadataRelease:region,store",
        "noexcept,discard",
    ),
    (
        "metadata_allocated(const compiler_ir_metadata::MetadataStore& store) -> bool",
        "direct store.allocated()",
        "",
        "noexcept",
    ),
    (
        "metadata_run(compiler_ir_metadata::MetadataStore& store) -> compiler_ir_metadata::MetadataStatus",
        "direct compiler_ir_metadata::run(store)",
        "",
        "noexcept",
    ),
    (
        "metadata_error(const compiler_ir_metadata::MetadataStore& store) -> compiler_ir_metadata::MetadataError",
        "direct store.error()",
        "",
        "noexcept",
    ),
    (
        "instructions_create(builtin::ByteRegion region, i64 instructionCount, i64 operandCount, i64 "
        "literalCount, i64 bodyCount) -> compiler_ir_instructions::InstructionStore",
        "move compiler_ir_instructions::create(region, instructionCount, operandCount, literalCount, bodyCount)",
        "InstructionsCreate:region,instructionCount,operandCount,literalCount,bodyCount",
        "noexcept",
    ),
    (
        "instructions_release(builtin::ByteRegion region, compiler_ir_instructions::InstructionStore store) -> i64",
        "direct compiler_ir_instructions::release(region, move(store))",
        "InstructionsRelease:region,store",
        "noexcept,discard",
    ),
    (
        "instructions_allocated(const compiler_ir_instructions::InstructionStore& store) -> bool",
        "direct store.allocated()",
        "",
        "noexcept",
    ),
    (
        "instructions_admit(compiler_ir_instructions::InstructionStore& store, const "
        "compiler_ir_metadata::MetadataStore& metadata) -> compiler_ir_instructions::InstructionStatus",
        "direct compiler_ir_instructions::admit_instruction_storage(store, metadata)",
        "",
        "noexcept",
    ),
    (
        "instructions_structure(compiler_ir_instructions::InstructionStore& store, const "
        "compiler_ir_metadata::MetadataStore& metadata) -> compiler_ir_instructions::InstructionStatus",
        "direct compiler_ir_instructions::admit_instruction_bodies(store, metadata)",
        "",
        "noexcept",
    ),
    (
        "instructions_publish(compiler_ir_instructions::InstructionStore& store) -> bool",
        "direct store.publish()",
        "",
        "noexcept",
    ),
    (
        "instructions_error(const compiler_ir_instructions::InstructionStore& store) -> "
        "compiler_ir_instructions::InstructionError",
        "direct store.error()",
        "",
        "noexcept",
    ),
    (
        "air_start(builtin::ByteRegion region) -> compiler_air::Reader",
        "move compiler_air::start(region)",
        "AirStart:region",
        "noexcept",
    ),
    (
        "air_release(builtin::ByteRegion region, compiler_air::Reader reader) -> i64",
        "direct compiler_air::release(region, move(reader))",
        "AirRelease:region,reader",
        "noexcept,discard",
    ),
    (
        "air_read(compiler_air::Reader& reader, builtin::span<const u8> source, builtin::span<const u8> abi) -> bool",
        "direct compiler_air::read_module(reader, source, abi)",
        "AirRead:source,abi",
        "noexcept",
    ),
    (
        "air_check(builtin::ByteRegion region, compiler_air::Reader reader) -> compiler_ir_metadata::IndexRow",
        "copy compiler_air::check(region, move(reader))",
        "AirCheck:region,reader",
        "noexcept",
    ),
    (
        "air_run(builtin::ByteRegion region, compiler_air::Reader reader, u64 options) -> compiler_pipeline::Result",
        "move compiler_air::run(region, move(reader), options)",
        "AirRun:region,reader,options",
        "noexcept",
    ),
    (
        "air_metadata(builtin::ByteRegion region, compiler_air::Reader reader) -> compiler_ir_metadata::MetadataStore",
        "move compiler_air::metadata(region, move(reader))",
        "AirMetadata:region,reader",
        "noexcept",
    ),
    (
        "verification_create(builtin::ByteRegion region) -> compiler_ir_verification::VerificationWorkspace",
        "move compiler_ir_verification::create(region)",
        "VerificationCreate:region",
        "noexcept",
    ),
    (
        "verification_report(const compiler_ir_verification::VerificationWorkspace& workspace) -> "
        "compiler_ir_verification::VerificationReport",
        "copy workspace.report()",
        "",
        "noexcept",
    ),
    (
        "verification_release(builtin::ByteRegion region, "
        "compiler_ir_verification::VerificationWorkspace workspace) -> i64",
        "direct compiler_ir_verification::release(region, move(workspace))",
        "VerificationRelease:region,workspace",
        "noexcept,discard",
    ),
)

# The initialization workspace probes (tests/compiler/initialization_probe.au)
# for initialization-facts: name, workspace and paired metadata roots, scalar
# parameters, result.
_WORKSPACE = "compiler_ir_verification::VerificationWorkspace& workspace"
_PAIR = _WORKSPACE + ", const compiler_ir_metadata::MetadataStore& metadata"
INITIALIZATION_PROBES = (
    ("compare_metadata_bytes", "const " + _PAIR, "i64 left, i64 right, i64 count", "i64"),
    ("allocated", "const " + _WORKSPACE, "", "bool"),
    ("status", "const " + _WORKSPACE, "", "compiler_ir_verification::InitializationStatus"),
    ("slot_count", "const " + _WORKSPACE, "", "i64"),
    ("word_count", "const " + _WORKSPACE, "", "i64"),
    ("payload_bytes", "const " + _WORKSPACE, "", "i64"),
    ("acquire_service_loan", _WORKSPACE, "i64 id, i64 root, i64 kind", "i64"),
    ("release_service_loan", _WORKSPACE, "i64 id, i64 kind", "i64"),
    ("service_unsuspended", "const " + _WORKSPACE, "i64 root", "i64"),
    (
        "validate_service_call",
        "const " + _WORKSPACE,
        "i64 first, i64 first_kind, i64 second, i64 second_kind",
        "compiler_ir_verification::ServiceCallState",
    ),
    ("complete_service_call", _WORKSPACE, "i64 first, i64 second", "bool"),
    ("service_loans_closed", "const " + _WORKSPACE, "", "i64"),
    ("same_service_loans", "const " + _WORKSPACE, "i64 id", "i64"),
    ("retained_count", "const " + _WORKSPACE, "", "i64"),
    ("current_count", "const " + _WORKSPACE, "", "i64"),
    ("retained_count_at", "const " + _WORKSPACE, "i64 id", "i64"),
    ("load", _WORKSPACE, "i64 id", "bool"),
    ("retain", _WORKSPACE, "", "i64"),
    ("join", _WORKSPACE, "i64 id", "compiler_ir_verification::InitializationJoin"),
    ("restore_facts", _WORKSPACE, "i64 count", "bool"),
    ("initialize", _PAIR, "i64 callable", "compiler_ir_verification::InitializationStatus"),
    ("scalar_state", _PAIR, "i64 offset", "i64"),
    ("write_scalar", _PAIR, "i64 offset", "i64"),
    ("object_initialized", _PAIR, "i64 base", "i64"),
    ("object_pristine", _PAIR, "i64 base", "i64"),
    ("object_was_constructed", _PAIR, "i64 base", "i64"),
    ("object_completion", _PAIR, "i64 base", "compiler_ir_verification::ObjectCompletion"),
    ("mark_object", _PAIR, "i64 base", "bool"),
    ("clear_object", _PAIR, "i64 base", "bool"),
    ("receiver_field_state", _PAIR, "i64 field", "i64"),
    ("write_receiver_field", _PAIR, "i64 field", "i64"),
    ("receiver_completion", _PAIR, "", "compiler_ir_verification::ReceiverCompletion"),
    ("array_first_missing", _PAIR, "i64 offset, i64 length, i64 width", "i64"),
    ("clear_array", _PAIR, "i64 offset, i64 length, i64 width", "bool"),
)
ROWS += tuple(
    (
        f"initialization_{name}({roots}{', ' + tail if tail else ''}) -> {result}",
        "direct compiler_initialization_probe::"
        + name
        + "("
        + ", ".join(
            ["workspace"]
            + (["metadata"] if "metadata" in roots else [])
            + [part.split()[1] for part in tail.split(", ") if part]
        )
        + ")",
        "",
        "noexcept",
    )
    for name, roots, tail, result in INITIALIZATION_PROBES
)


def declarations(rows=ROWS):
    entries = []
    for signature, forward, transport, policy in rows:
        match = re.fullmatch(r"(\w+)\((.*)\) -> ([\w:]+)", signature)
        if match is None:
            raise ValueError("invalid private bridge signature")
        name, arguments, result = match.groups()
        mode, expression = forward.split(" ", 1)
        flags, _, host = policy.partition(":")
        flags = set(flags.split(",")) - {""}
        if flags - {"noexcept", "discard"}:
            raise ValueError("unknown private bridge policy")
        record, loads = None, ()
        if transport:
            fields = transport.split(":")
            if len(fields) not in (2, 3):
                raise ValueError("invalid private argument record policy")
            record = (fields[0], tuple(fields[1].split(",")))
            loads = tuple(map(int, fields[2].split(","))) if len(fields) == 3 else ()
        if any(index < 0 or index > 5 for index in loads) or len(set(loads)) != len(loads):
            raise ValueError("invalid private scalar lanes")
        if host and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", host):
            raise ValueError("invalid private host alias")
        entries.append(
            (
                name,
                arguments,
                result,
                expression,
                mode,
                record,
                host or name,
                "noexcept" in flags,
                "discard" in flags,
                loads,
            )
        )
    if len({entry[6] for entry in entries}) != len(entries):
        raise ValueError("duplicate private host alias")
    return tuple(entries)


ENTRIES = declarations()


def signatures(table=ENTRIES):
    """Read the deliberately closed source signature spelling in the table."""
    entries = {}
    for name, arguments, result, expression, mode, record, host, noexcept, discard, loads in table:
        roots, parameters = [], []
        for argument in arguments.split(", ") if arguments else ():
            spelling, parameter = argument.rsplit(" ", 1)
            if spelling.endswith("&"):
                if parameters:
                    raise ValueError("bridge roots must precede copied parameters")
                roots.append((spelling.removeprefix("const ").removesuffix("&"), not spelling.startswith("const ")))
            else:
                parameters.append(
                    {"builtin::ByteRegion": "region", "builtin::span<const u8>": "span"}.get(spelling, spelling)
                )
        if name in entries or len(roots) > 4:
            raise ValueError("duplicate bridge or unsupported root count")
        entries[name] = (tuple(roots), tuple(parameters), result, record, discard)
    return entries


def render(source):
    """Expand only the explicit scaffold marker; existing source/probes stay exact."""
    table, marker = ENTRIES, "// @generated-forwarders"
    if marker not in source:
        return source
    lines = ["export namespace compiler_frontend {"]
    for name, arguments, result, expression, mode, *_ in table:
        lines.append(f"    auto {name}({arguments}) -> {result} {{")
        if mode == "direct":
            lines.append(f"        return {expression};")
        elif mode in ("copy", "move"):
            lines.append(f"        {'const ' if mode == 'copy' else ''}{result} result = {expression};")
            lines.append("        return " + ("move(result)" if mode == "move" else "result") + ";")
        else:
            raise ValueError("unsupported bridge return mode")
        lines.append("    }")
    lines.append("}")
    return source.replace(marker, "\n".join(lines))


if __name__ == "__main__":
    source, output = map(Path, sys.argv[1:])
    output.write_text(render(source.read_text()))
