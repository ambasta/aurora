#!/usr/bin/env python3
"""Single declaration table for the private compiler host bridge.

Rows specify source signatures/calls and existing transport policy. Physical
layouts and target symbols remain compiler-fact authorities.
"""

from pathlib import Path
import re
import sys

# Source signature, forwarding expression (direct/copy/move), argument record
# (name:fields[:scalar lanes]), and host policy (noexcept/discard/consume[:alias]).
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
        "formatter_run(compiler_formatter::Workspace& workspace, const compiler_parser::AstArena& arena, "
        "bool format) -> i64",
        "direct compiler_formatter::run(workspace, arena, format)",
        "",
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
        "emitter_create(builtin::ByteRegion region) -> compiler_x86::EmitWorkspace",
        "move compiler_x86::create(region)",
        "EmitterCreate:region",
        "noexcept",
    ),
    (
        "emitter_release(builtin::ByteRegion region, compiler_x86::EmitWorkspace workspace) -> i64",
        "direct compiler_x86::release(region, move(workspace))",
        "EmitterRelease:region,workspace",
        "noexcept,discard",
    ),
    (
        "emitter_status(const compiler_x86::EmitWorkspace& workspace) -> compiler_x86::EmitStatus",
        "direct workspace.status()",
        "",
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
        "emitter_object_status(const compiler_x86::ObjectWorkspace& workspace) -> compiler_x86::EmitStatus",
        "direct workspace.status()",
        "",
        "noexcept",
    ),
    (
        "emitter_enable_object(compiler_x86::ObjectWorkspace& workspace) -> bool",
        "direct workspace.enable_object()",
        "",
        "noexcept",
    ),
    (
        "emitter_add_retained(compiler_x86::EmitWorkspace& workspace, i64 callable) -> bool",
        "direct workspace.add_retained(callable)",
        "",
        "noexcept",
    ),
    (
        "emitter_prepare_facts(compiler_x86::EmitWorkspace& workspace, compiler_x86::Artifact artifact) -> bool",
        "direct workspace.prepare_facts(artifact)",
        "",
        "noexcept",
    ),
    (
        "emitter_append_name(compiler_x86::EmitWorkspace& workspace, builtin::span<const u8> name) -> i64",
        "direct workspace.append_name(name)",
        "EmitterNameInput:name",
        "noexcept",
    ),
    (
        "emitter_add_abi_name(compiler_x86::EmitWorkspace& workspace, compiler_x86::AbiNameRow name) -> bool",
        "direct workspace.add_abi_name(name)",
        "EmitterAbiNameInput:name",
        "noexcept",
    ),
    (
        "emitter_run(compiler_x86::EmitWorkspace& workspace, compiler_x86::ObjectWorkspace& object, "
        "const compiler_ir_metadata::MetadataStore& "
        "metadata, const compiler_ir_instructions::InstructionStore& instructions, i64 binding, i64 "
        "reflection) -> compiler_x86::EmitStatus",
        "direct compiler_x86::run(workspace, object, metadata, instructions, binding, reflection)",
        "",
        "noexcept",
    ),
    (
        "emitter_facts(compiler_x86::EmitWorkspace& workspace, const compiler_ir_metadata::MetadataStore& "
        "metadata, compiler_x86::Artifact artifact) -> compiler_x86::EmitStatus",
        "direct compiler_x86::emitter_facts(workspace, metadata, artifact)",
        "",
        "noexcept",
    ),
    (
        "emitter_size(const compiler_x86::EmitWorkspace& workspace, compiler_x86::Artifact artifact) -> i64",
        "direct workspace.artifact_size(artifact)",
        "",
        "noexcept",
    ),
    (
        "emitter_chunk(const compiler_x86::EmitWorkspace& workspace, compiler_x86::Artifact artifact, i64 "
        "offset) -> compiler_x86::EmitChunk",
        "copy workspace.chunk(artifact, offset)",
        "",
        "noexcept",
    ),
    (
        "lexer_next(builtin::span<const u8> source, compiler_lexer::Cursor cursor) -> compiler_lexer::Lexeme",
        "copy compiler_lexer::next_lexeme(source, cursor)",
        "LexerInput:source,cursor",
        ":lexer_invoke",
    ),
    (
        "parser_create(builtin::ByteRegion region, i64 capacity) -> compiler_parser::AstArena",
        "move compiler_parser::create(region, capacity)",
        "ParserCreate:region,capacity",
        "",
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
        "parser_release(builtin::ByteRegion region, compiler_parser::AstArena arena) -> i64",
        "direct compiler_parser::release(region, move(arena))",
        "ParserRelease:region,arena",
        "discard",
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
        "resolver_create(builtin::ByteRegion region) -> compiler_resolver::Session",
        "move compiler_resolver::create(region)",
        "ResolverCreate:region",
        "",
    ),
    (
        "resolver_ingest(builtin::ByteRegion region, compiler_resolver::Session session, "
        "compiler_parser::AstArena parsed, i64 module_id, i64 root) -> compiler_resolver::Session",
        "move compiler_resolver::ingest(region, move(session), move(parsed), module_id, root)",
        "ResolverIngest:region,session,parsed,module,root",
        "consume",
    ),
    (
        "resolver_release(builtin::ByteRegion region, compiler_resolver::Session session) -> i64",
        "direct compiler_resolver::release(region, move(session))",
        "ResolverRelease:region,session",
        "discard",
    ),
    (
        "resolver_release_pair(builtin::ByteRegion region, compiler_resolver::Session session, "
        "compiler_parser::AstArena parsed) -> i64",
        "direct compiler_resolver::release_pair(region, move(session), move(parsed))",
        "ResolverReleasePair:region,session,parsed",
        "discard",
    ),
    (
        "resolver_append_source(compiler_resolver::Session& session, builtin::span<const u8> source) -> i64",
        "direct compiler_resolver::append_source(session, source)",
        "ResolverSourceInput:source",
        "",
    ),
    (
        "resolver_append_text(compiler_resolver::Session& session, builtin::span<const u8> source) -> i64",
        "direct compiler_resolver::append_text(session, source)",
        "ResolverTextInput:text",
        "",
    ),
    (
        "resolver_order_module(compiler_resolver::Session& session, i64 module_id, i64 order, i64 scope, bool "
        "root) -> bool",
        "direct compiler_resolver::order_module(session, module_id, order, scope, root)",
        "ResolverOrderInput:module,order,scope,root:0,1,2,3",
        "",
    ),
    (
        "resolver_bind_import(compiler_resolver::Session& session, i64 module_id, i64 node, i64 target) -> bool",
        "direct compiler_resolver::bind_import(session, module_id, node, target)",
        "ResolverImportInput:module,node,target:0,1,2",
        "",
    ),
    (
        "resolver_graph_step(compiler_resolver::Session& session, i64 root) -> compiler_resolver::WorkRow",
        "copy compiler_resolver::graph_step(session, root)",
        "",
        "",
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
        "resolver_seed_builtin(compiler_resolver::Session& session, compiler_resolver::MetaRow definition) -> i64",
        "direct compiler_resolver::seed_builtin(session, definition)",
        "ResolverSeedBuiltinInput:definition",
        "",
    ),
    (
        "resolver_seed_member(compiler_resolver::Session& session, compiler_resolver::MetaRow definition) -> i64",
        "direct compiler_resolver::seed_member(session, definition)",
        "ResolverSeedMemberInput:member",
        "",
    ),
    ("resolver_run(compiler_resolver::Session& session) -> i64", "direct compiler_resolver::run(session)", "", ""),
    (
        "resolver_read_syntax(const compiler_resolver::Session& session, i64 index) -> compiler_resolver::SyntaxRow",
        "copy compiler_resolver::read_syntax(session, index)",
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
        "resolver_read_resolved(const compiler_resolver::Session& session, i64 index) -> "
        "compiler_resolver::ResolvedRow",
        "copy compiler_resolver::read_resolved(session, index)",
        "",
        "",
    ),
    (
        "lowering_begin(compiler_resolver::Session& session, compiler_lowering::LoweringConfig configuration) -> i64",
        "direct compiler_lowering::begin_lowering(session, configuration)",
        "LoweringBeginInput:configuration",
        "noexcept",
    ),
    (
        "lowering_seed_scalar(compiler_resolver::Session& session, compiler_lowering::ScalarSeed seed) -> i64",
        "direct compiler_lowering::seed_scalar(session, seed)",
        "LoweringScalarInput:seed",
        "noexcept",
    ),
    (
        "lowering_seed_service(compiler_resolver::Session& session, compiler_lowering::ServiceSeed seed) -> i64",
        "direct compiler_lowering::seed_service(session, seed)",
        "LoweringServiceInput:seed",
        "noexcept",
    ),
    (
        "lowering_seed_layout_symbol(compiler_resolver::Session& session, i64 symbol) -> i64",
        "direct compiler_lowering::seed_layout_symbol(session, symbol)",
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
        "graph_create_input(builtin::ByteRegion region, i64 functions, i64 edges) -> compiler_ir_graph::Input",
        "move compiler_ir_graph::create_input(region, functions, edges)",
        "GraphCreateInput:region,functions,edges",
        "noexcept",
    ),
    (
        "graph_create_workspace(builtin::ByteRegion region, i64 functions, i64 edges) -> compiler_ir_graph::Workspace",
        "move compiler_ir_graph::create_workspace(region, functions, edges)",
        "GraphCreateWorkspace:region,functions,edges",
        "noexcept",
    ),
    (
        "graph_release_input(builtin::ByteRegion region, compiler_ir_graph::Input input) -> i64",
        "direct compiler_ir_graph::release_input(region, move(input))",
        "GraphReleaseInput:region,input",
        "noexcept,discard",
    ),
    (
        "graph_release_workspace(builtin::ByteRegion region, compiler_ir_graph::Workspace workspace) -> i64",
        "direct compiler_ir_graph::release_workspace(region, move(workspace))",
        "GraphReleaseWorkspace:region,workspace",
        "noexcept,discard",
    ),
    (
        "graph_set_function(compiler_ir_graph::Input& input, i64 index, compiler_ir_graph::FunctionRow "
        "function) -> bool",
        "direct compiler_ir_graph::set_function(input, index, function)",
        "GraphFunctionInput:index,function:0",
        "noexcept",
    ),
    (
        "graph_set_edge(compiler_ir_graph::Input& input, i64 index, i64 target) -> bool",
        "direct compiler_ir_graph::set_edge(input, index, target)",
        "GraphEdgeInput:index,target:0,1",
        "noexcept",
    ),
    (
        "graph_run(compiler_ir_graph::Workspace& workspace, const compiler_ir_graph::Input& input) -> "
        "compiler_ir_graph::GraphStatus",
        "direct compiler_ir_graph::run(workspace, input)",
        "",
        "noexcept",
    ),
    (
        "graph_retained(const compiler_ir_graph::Workspace& workspace, i64 index) -> bool",
        "direct compiler_ir_graph::retained(workspace, index)",
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
        "metadata_object_leaf_root(const compiler_ir_metadata::MetadataStore& store, i64 callable, i64 offset) -> i64",
        "direct compiler_ir_metadata::object_leaf_root(store, callable, offset)",
        "",
        "noexcept",
    ),
    (
        "metadata_byte_array_element_root(const compiler_ir_metadata::MetadataStore& store, i64 callable, i64 "
        "offset) -> i64",
        "direct compiler_ir_metadata::byte_array_element_root(store, callable, offset)",
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
        "verification_create(builtin::ByteRegion region) -> compiler_ir_verification::VerificationWorkspace",
        "move compiler_ir_verification::create(region)",
        "VerificationCreate:region",
        "noexcept",
    ),
    (
        "verification_run(compiler_ir_verification::VerificationWorkspace& workspace, const "
        "compiler_ir_metadata::MetadataStore& metadata, const "
        "compiler_ir_instructions::InstructionStore& instructions, i64 callable) -> "
        "compiler_ir_verification::VerificationStatus",
        "direct compiler_ir_verification::run(workspace, metadata, instructions, callable)",
        "",
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


def declarations():
    entries = []
    for signature, forward, transport, policy in ROWS:
        match = re.fullmatch(r"(\w+)\((.*)\) -> ([\w:]+)", signature)
        if match is None:
            raise ValueError("invalid private bridge signature")
        name, arguments, result = match.groups()
        mode, expression = forward.split(" ", 1)
        flags, _, host = policy.partition(":")
        flags = set(flags.split(",")) - {""}
        if flags - {"noexcept", "discard", "consume"}:
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
        if "consume" in flags and (record is None or "discard" in flags):
            raise ValueError("invalid private consuming record policy")
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
                "consume" in flags,
            )
        )
    if len({entry[6] for entry in entries}) != len(entries):
        raise ValueError("duplicate private host alias")
    return tuple(entries)


ENTRIES = declarations()


def signatures():
    """Read the deliberately closed source signature spelling in the table."""
    entries = {}
    for name, arguments, result, expression, mode, record, host, noexcept, discard, loads, consume in ENTRIES:
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
        if name in entries or len(roots) > 4 or (consume and roots):
            raise ValueError("duplicate bridge or unsupported root count")
        entries[name] = (tuple(roots), tuple(parameters), result, record, discard)
    return entries


def render(source):
    """Expand only the explicit scaffold marker; existing source/probes stay exact."""
    marker = "// @generated-forwarders"
    if marker not in source:
        return source
    lines = ["export namespace compiler_frontend {"]
    for name, arguments, result, expression, mode, *_ in ENTRIES:
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
