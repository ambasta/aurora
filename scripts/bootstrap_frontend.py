#!/usr/bin/env python3
"""Emit the private hosted frontend and its compiler-described ABI.

The compiler-module root contains exact exported source copies. Generated Aurora
bindings remain local; only trusted register bridges expose host entries.
"""

from pathlib import Path
import re
import json
import shutil
import subprocess
import sys


# Names only: every physical field extent and offset comes from emitted facts.
ARGUMENT_RECORDS = (
    ("LexerInput", "compiler_frontend::lexer_next", ("source", "cursor")),
    ("ParserInput", "compiler_frontend::parser_parse", ("source", "cursor", "stop", "context", "enum_count")),
    ("AdmissionInput", "compiler_frontend::parser_admit", ("source", "root", "configuration")),
    ("ParserCreate", "compiler_frontend::parser_create", ("region", "capacity")),
    ("ParserRelease", "compiler_frontend::parser_release", ("region", "arena")),
    ("ResolverCreate", "compiler_frontend::resolver_create", ("region",)),
    ("ResolverIngest", "compiler_frontend::resolver_ingest", ("region", "session", "parsed", "module", "root")),
    ("ResolverRelease", "compiler_frontend::resolver_release", ("region", "session")),
    ("ResolverReleasePair", "compiler_frontend::resolver_release_pair", ("region", "session", "parsed")),
    ("ResolverSourceInput", "compiler_frontend::resolver_append_source", ("source",)),
    ("ResolverTextInput", "compiler_frontend::resolver_append_text", ("text",)),
    ("ResolverOrderInput", "compiler_frontend::resolver_order_module", ("module", "order", "scope", "root")),
    ("ResolverImportInput", "compiler_frontend::resolver_bind_import", ("module", "node", "target")),
    ("ResolverSeedBuiltinInput", "compiler_frontend::resolver_seed_builtin", ("definition",)),
    ("ResolverSeedMemberInput", "compiler_frontend::resolver_seed_member", ("member",)),
    ("LoweringBeginInput", "compiler_frontend::lowering_begin", ("configuration",)),
    ("LoweringScalarInput", "compiler_frontend::lowering_seed_scalar", ("seed",)),
    ("LoweringServiceInput", "compiler_frontend::lowering_seed_service", ("seed",)),
    ("GraphCreateInput", "compiler_frontend::graph_create_input", ("region", "functions", "edges")),
    ("GraphCreateWorkspace", "compiler_frontend::graph_create_workspace", ("region", "functions", "edges")),
    ("GraphReleaseInput", "compiler_frontend::graph_release_input", ("region", "input")),
    ("GraphReleaseWorkspace", "compiler_frontend::graph_release_workspace", ("region", "workspace")),
    ("GraphFunctionInput", "compiler_frontend::graph_set_function", ("index", "function")),
    ("GraphEdgeInput", "compiler_frontend::graph_set_edge", ("index", "target")),
    ("MetadataCreate", "compiler_frontend::metadata_create", ("region",)),
    (
        "MetadataInitialize",
        "compiler_frontend::metadata_initialize",
        ("counts", "callableCount", "slotCount", "instructionBegin"),
    ),
    ("MetadataRelease", "compiler_frontend::metadata_release", ("region", "store")),
    (
        "InstructionsCreate",
        "compiler_frontend::instructions_create",
        ("region", "instructionCount", "operandCount", "literalCount", "bodyCount"),
    ),
    ("InstructionsRelease", "compiler_frontend::instructions_release", ("region", "store")),
    ("InitializationCreate", "compiler_frontend::initialization_create", ("region",)),
    ("InitializationRelease", "compiler_frontend::initialization_release", ("region", "workspace")),
)


def abi_declaration(facts, group, source_name):
    """Find a resolved declaration; source spelling is never a mangling recipe."""
    if (
        type(facts.get("version")) is not int
        or facts["version"] not in (1, 2)
        or not isinstance(facts.get(group), dict)
    ):
        raise ValueError("unsupported compiler ABI facts")
    found = [(symbol, entry) for symbol, entry in facts[group].items() if entry["source_name"] == source_name]
    if len(found) != 1:
        raise ValueError(f"expected one ABI declaration: {source_name}")
    return found[0]


def abi_function_symbol(facts, source_name):
    return abi_declaration(facts, "functions", source_name)[0]


def normalize_function_abi(facts, function):
    """Normalize exactly the selected paired predecessor and current root facts.

    This version-1 branch belongs only to the immutable paired-root source
    predecessor. Remove it when that predecessor no longer builds this frontend;
    missing lanes never imply additional roots or a later compatibility version.
    """
    version = facts.get("version")
    if type(version) is not int or version not in (1, 2) or type(function) is not dict:
        raise ValueError("unsupported compiler ABI root facts")
    old_fields = {"borrowed_parameter", "second_receiver", "root_count", "root_tuple_bytes", "root_order"}
    new_fields = {"borrowed_roots", "borrowed_root_count", "borrowed_root_abi"}
    common_fields = {"source_name", "receiver", "receiver_mutable", "parameter_bytes", "parameters", "result"}
    if (new_fields if version == 1 else old_fields) & function.keys():
        raise ValueError("conflicting compiler ABI root representations")
    if not (old_fields if version == 1 else new_fields) <= function.keys():
        raise ValueError("incomplete compiler ABI root facts")
    if function.keys() != common_fields | (old_fields if version == 1 else new_fields):
        raise ValueError("unknown compiler ABI function facts")
    receiver, mutable = function.get("receiver"), function.get("receiver_mutable")
    records = facts.get("records", {})
    if (
        "receiver" not in function
        or "receiver_mutable" not in function
        or (receiver is None and mutable is not None)
        or (
            receiver is not None and (type(receiver) is not str or receiver not in records or type(mutable) is not bool)
        )
    ):
        raise ValueError("invalid compiler ABI receiver facts")

    if version == 1:
        borrowed, second = function["borrowed_parameter"], function["second_receiver"]
        if type(borrowed) is not bool or (borrowed and receiver is None):
            raise ValueError("invalid predecessor borrowed root")
        if second is not None and (
            not borrowed
            or mutable is not True
            or type(second) is not dict
            or set(second) != {"type_name", "mutable"}
            or second["mutable"] is not False
            or type(second["type_name"]) is not str
            or second["type_name"] not in records
        ):
            raise ValueError("invalid predecessor second borrowed root")
        count = 2 if second is not None else int(receiver is not None)
        if (
            type(function["root_count"]) is not int
            or function["root_count"] != count
            or type(function["root_tuple_bytes"]) is not int
            or function["root_tuple_bytes"] != (16 if count == 2 else 0)
            or function["root_order"]
            != (["receiver", "second_receiver"] if count == 2 else ["receiver"] if count else [])
        ):
            raise ValueError("invalid predecessor root count, order or tuple")
        roots = []
        if borrowed:
            roots.append(dict(ordinal=0, selector=0, type_name=receiver, mutable=mutable))
            if second is not None:
                roots.append(dict(ordinal=1, selector=-1, type_name=second["type_name"], mutable=False))
            receiver, mutable = None, None
    else:
        roots = function["borrowed_roots"]
        count = function["borrowed_root_count"]
        if type(count) is not int or not 0 <= count <= 6 or type(roots) is not list or len(roots) != count:
            raise ValueError("invalid compiler ABI borrowed root count")
        if count and receiver is not None:
            raise ValueError("borrowed roots cannot also grant a method receiver")

    for ordinal, root in enumerate(roots):
        if (
            type(root) is not dict
            or set(root) != {"ordinal", "selector", "type_name", "mutable"}
            or type(root["ordinal"]) is not int
            or root["ordinal"] != ordinal
            or type(root["selector"]) is not int
            or root["selector"] != -ordinal
            or type(root["mutable"]) is not bool
            or (ordinal > 0 and root["mutable"])
            or type(root["type_name"]) is not str
            or root["type_name"] not in records
            or not any(field.get("kind") == "owner" for field in records[root["type_name"]]["fields"])
        ):
            raise ValueError("invalid compiler ABI borrowed root lane")
    count = len(roots)
    if count + len(function["parameters"]) > 6 or (
        count >= 2
        and (
            any(parameter["kind"] not in ("i64", "u64", "u8", "bool", "enum") for parameter in function["parameters"])
            or function["result"]["kind"] not in ("i64", "u64", "u8", "bool", "enum")
        )
    ):
        raise ValueError("invalid compiler ABI borrowed root tail")
    root_abi = dict(
        kind="tuple" if count >= 2 else "direct" if count else "none",
        register="r10" if count else None,
        tuple_payload_bytes=8 * count if count >= 2 else 0,
        tuple_reserved_bytes=((8 * count + 15) // 16) * 16 if count >= 2 else 0,
        saved_root_reserved_bytes=((8 * count + 15) // 16) * 16 if count else 0,
    )
    if version == 2 and json.dumps(function["borrowed_root_abi"], sort_keys=True) != json.dumps(
        root_abi, sort_keys=True
    ):
        raise ValueError("invalid compiler ABI borrowed root transport")
    return {
        **{key: value for key, value in function.items() if key not in old_fields},
        "receiver": receiver,
        "receiver_mutable": mutable,
        "borrowed_roots": roots,
        "borrowed_root_count": count,
        "borrowed_root_abi": root_abi,
    }


def frontend_abi_entries(facts):
    """Check the fixed register bridges before allowing generated record writes."""

    def shape(source):
        if source in ("i64", "u64", "u8", "bool", "region", "span"):
            return source, None, facts["span_bytes"] if source == "span" else 8
        group = "enums" if any(value["source_name"] == source for value in facts["enums"].values()) else "records"
        symbol, record = abi_declaration(facts, group, source)
        return "enum" if group == "enums" else "class", symbol, 8 if group == "enums" else record["reserved"]

    def matches(actual, expected):
        kind, symbol, width = shape(expected)
        return actual["kind"] == kind and actual.get("type_name") == symbol and actual["bytes"] == width

    arena, _ = abi_declaration(facts, "records", "compiler_parser::AstArena")
    session, _ = abi_declaration(facts, "records", "compiler_resolver::Session")
    graph_input, _ = abi_declaration(facts, "records", "compiler_ir_graph::Input")
    graph_workspace, _ = abi_declaration(facts, "records", "compiler_ir_graph::Workspace")
    metadata, _ = abi_declaration(facts, "records", "compiler_ir_metadata::MetadataStore")
    instructions, _ = abi_declaration(facts, "records", "compiler_ir_instructions::InstructionStore")
    initialization, _ = abi_declaration(facts, "records", "compiler_ir_initialization::InitializationWorkspace")
    checks = [
        (
            "lexer_next",
            "compiler_frontend::lexer_next",
            None,
            ["span", "compiler_lexer::Cursor"],
            "compiler_lexer::Lexeme",
        ),
        ("parser_create", "compiler_frontend::parser_create", None, ["region", "i64"], "compiler_parser::AstArena"),
        (
            "parser_parse",
            "compiler_frontend::parser_parse",
            arena,
            ["span", "compiler_lexer::Cursor", "compiler_parser::Stop", "compiler_parser::TypeContext", "i64"],
            "compiler_parser::ParseResult",
        ),
        (
            "parser_admit",
            "compiler_frontend::parser_admit",
            arena,
            ["span", "i64", "compiler_parser::AdmissionConfig"],
            "compiler_parser::AdmissionResult",
        ),
        ("parser_release", "compiler_frontend::parser_release", None, ["region", "compiler_parser::AstArena"], "i64"),
        ("resolver_create", "compiler_frontend::resolver_create", None, ["region"], "compiler_resolver::Session"),
        (
            "resolver_ingest",
            "compiler_frontend::resolver_ingest",
            None,
            ["region", "compiler_resolver::Session", "compiler_parser::AstArena", "i64", "i64"],
            "compiler_resolver::Session",
        ),
        (
            "resolver_release",
            "compiler_frontend::resolver_release",
            None,
            ["region", "compiler_resolver::Session"],
            "i64",
        ),
        (
            "resolver_release_pair",
            "compiler_frontend::resolver_release_pair",
            None,
            ["region", "compiler_resolver::Session", "compiler_parser::AstArena"],
            "i64",
        ),
        ("resolver_append_source", "compiler_frontend::resolver_append_source", session, ["span"], "i64"),
        ("resolver_append_text", "compiler_frontend::resolver_append_text", session, ["span"], "i64"),
        (
            "resolver_order_module",
            "compiler_frontend::resolver_order_module",
            session,
            ["i64", "i64", "i64", "bool"],
            "bool",
        ),
        ("resolver_bind_import", "compiler_frontend::resolver_bind_import", session, ["i64", "i64", "i64"], "bool"),
        ("resolver_count", "compiler_frontend::resolver_count", session, ["i64"], "i64"),
        ("resolver_read_source", "compiler_frontend::resolver_read_source", session, ["i64"], "i64"),
        ("resolver_status", "compiler_frontend::resolver_status", session, [], "compiler_resolver::SessionStatus"),
        (
            "resolver_seed_builtin",
            "compiler_frontend::resolver_seed_builtin",
            session,
            ["compiler_resolver::MetaRow"],
            "i64",
        ),
        (
            "resolver_seed_member",
            "compiler_frontend::resolver_seed_member",
            session,
            ["compiler_resolver::MetaRow"],
            "i64",
        ),
        ("resolver_run", "compiler_frontend::resolver_run", session, [], "i64"),
        (
            "lowering_begin",
            "compiler_frontend::lowering_begin",
            session,
            ["compiler_lowering::LoweringConfig"],
            "i64",
        ),
        (
            "lowering_seed_scalar",
            "compiler_frontend::lowering_seed_scalar",
            session,
            ["compiler_lowering::ScalarSeed"],
            "i64",
        ),
        (
            "lowering_seed_service",
            "compiler_frontend::lowering_seed_service",
            session,
            ["compiler_lowering::ServiceSeed"],
            "i64",
        ),
        ("lowering_seed_layout_symbol", "compiler_frontend::lowering_seed_layout_symbol", session, ["i64"], "i64"),
        ("lowering_run", "compiler_frontend::lowering_run", session, [], "compiler_lowering::LoweringResult"),
        ("lowering_count", "compiler_frontend::lowering_count", session, ["i64"], "i64"),
        (
            "lowering_read_output",
            "compiler_frontend::lowering_read_output",
            session,
            ["i64"],
            "compiler_lowering::OutputRow",
        ),
        (
            "lowering_read_operand",
            "compiler_frontend::lowering_read_operand",
            session,
            ["i64"],
            "compiler_lowering::OperandRow",
        ),
    ]
    checks += [
        ("graph_" + name, "compiler_frontend::graph_" + name, receiver, parameters, result)
        for name, receiver, parameters, result in (
            ("create_input", None, ["region", "i64", "i64"], "compiler_ir_graph::Input"),
            ("create_workspace", None, ["region", "i64", "i64"], "compiler_ir_graph::Workspace"),
            ("release_input", None, ["region", "compiler_ir_graph::Input"], "i64"),
            ("release_workspace", None, ["region", "compiler_ir_graph::Workspace"], "i64"),
            ("set_function", graph_input, ["i64", "compiler_ir_graph::FunctionRow"], "bool"),
            ("set_edge", graph_input, ["i64", "i64"], "bool"),
            ("run", graph_workspace, [], "compiler_ir_graph::GraphStatus"),
            ("retained", graph_workspace, ["i64"], "bool"),
        )
    ]
    checks += [
        ("metadata_" + name, "compiler_frontend::metadata_" + name, receiver, parameters, result)
        for name, receiver, parameters, result in (
            ("flag_masks", None, [], "compiler_ir_metadata::FlagMasks"),
            (
                "create",
                None,
                ["region"],
                "compiler_ir_metadata::MetadataStore",
            ),
            ("initialize", metadata, ["compiler_ir_metadata::InputCounts", "i64", "i64", "i64"], "bool"),
            ("release", None, ["region", "compiler_ir_metadata::MetadataStore"], "i64"),
            ("allocated", metadata, [], "bool"),
            ("run", metadata, [], "compiler_ir_metadata::MetadataStatus"),
            ("error", metadata, [], "compiler_ir_metadata::MetadataError"),
            ("object_leaf_root", metadata, ["i64", "i64"], "i64"),
            ("byte_array_element_root", metadata, ["i64", "i64"], "i64"),
        )
    ]
    checks += [
        ("instructions_" + name, "compiler_frontend::instructions_" + name, receiver, parameters, result)
        for name, receiver, parameters, result in (
            ("create", None, ["region", "i64", "i64", "i64", "i64"], "compiler_ir_instructions::InstructionStore"),
            ("release", None, ["region", "compiler_ir_instructions::InstructionStore"], "i64"),
            ("allocated", instructions, [], "bool"),
            ("admit", instructions, [], "compiler_ir_instructions::InstructionStatus"),
            ("structure", instructions, [], "compiler_ir_instructions::InstructionStatus"),
            ("publish", instructions, [], "bool"),
            ("error", instructions, [], "compiler_ir_instructions::InstructionError"),
        )
    ]
    initialization_pairs = {
        "initialization_" + name
        for name in (
            "initialize",
            "scalar_state",
            "write_scalar",
            "object_initialized",
            "object_pristine",
            "object_was_constructed",
            "object_completion",
            "mark_object",
            "clear_object",
            "array_first_missing",
            "clear_array",
        )
    }
    initialization_readonly = {
        "initialization_" + name
        for name in (
            "allocated",
            "status",
            "slot_count",
            "word_count",
            "retained_count",
            "current_count",
            "retained_count_at",
        )
    }
    checks += [
        ("initialization_" + name, "compiler_frontend::initialization_" + name, receiver, parameters, result)
        for name, receiver, parameters, result in (
            ("create", None, ["region"], "compiler_ir_initialization::InitializationWorkspace"),
            ("release", None, ["region", "compiler_ir_initialization::InitializationWorkspace"], "i64"),
            ("allocated", initialization, [], "bool"),
            ("status", initialization, [], "compiler_ir_initialization::InitializationStatus"),
            ("initialize", initialization, ["i64"], "compiler_ir_initialization::InitializationStatus"),
            ("slot_count", initialization, [], "i64"),
            ("word_count", initialization, [], "i64"),
            ("retained_count", initialization, [], "i64"),
            ("current_count", initialization, [], "i64"),
            ("retained_count_at", initialization, ["i64"], "i64"),
            ("load", initialization, ["i64"], "bool"),
            ("retain", initialization, [], "i64"),
            ("join", initialization, ["i64"], "compiler_ir_initialization::InitializationJoin"),
            ("scalar_state", initialization, ["i64"], "i64"),
            ("write_scalar", initialization, ["i64"], "i64"),
            ("object_initialized", initialization, ["i64"], "i64"),
            ("object_pristine", initialization, ["i64"], "i64"),
            ("object_was_constructed", initialization, ["i64"], "i64"),
            ("object_completion", initialization, ["i64"], "compiler_ir_initialization::ObjectCompletion"),
            ("mark_object", initialization, ["i64"], "bool"),
            ("clear_object", initialization, ["i64"], "bool"),
            ("array_first_missing", initialization, ["i64", "i64", "i64"], "i64"),
            ("clear_array", initialization, ["i64", "i64", "i64"], "bool"),
        )
    ]
    checks += [
        ("parser_" + name, "compiler_frontend::parser_" + name, arena, [], "i64")
        for name in ("node_count", "edge_count", "type_count", "syntax_count")
    ]
    checks += [
        ("resolver_" + name, "compiler_frontend::resolver_" + name, session, ["i64"], "compiler_resolver::" + result)
        for name, result in (("read_syntax", "SyntaxRow"), ("read_meta", "MetaRow"), ("read_resolved", "ResolvedRow"))
    ]
    checks += [
        ("parser_" + name, "compiler_frontend::parser_" + name, arena, ["i64"], "compiler_parser::" + result)
        for name, result in (
            ("read_node", "AstNode"),
            ("read_edge", "ChildEdge"),
            ("read_type", "TypeSyntax"),
            ("read_syntax", "SyntaxNode"),
        )
    ]
    entries = {}
    for alias, source, receiver, parameters, result in checks:
        symbol, raw_function = abi_declaration(facts, "functions", source)
        function = normalize_function_abi(facts, raw_function)
        roots = function["borrowed_roots"]
        expected_roots = [receiver] if receiver is not None else []
        if alias in ("graph_run", "instructions_admit", "instructions_structure") or alias in initialization_pairs:
            expected_roots.append(graph_input if alias == "graph_run" else metadata)
        if (
            function["receiver"] is not None
            or [root["type_name"] for root in roots] != expected_roots
            or len(function["parameters"]) != len(parameters)
            or not matches(function["result"], result)
        ):
            raise ValueError(f"private bridge signature changed: {source}")
        if roots:
            readonly = (
                (alias.startswith("parser_") and alias not in ("parser_parse", "parser_admit"))
                or (
                    alias.startswith("resolver_")
                    and alias
                    in (
                        "resolver_count",
                        "resolver_read_source",
                        "resolver_status",
                        "resolver_read_syntax",
                        "resolver_read_meta",
                        "resolver_read_resolved",
                    )
                )
                or (
                    alias.startswith("lowering_")
                    and alias
                    in (
                        "lowering_count",
                        "lowering_read_output",
                        "lowering_read_operand",
                    )
                )
                or alias == "graph_retained"
                or (alias.startswith("metadata_") and alias not in ("metadata_initialize", "metadata_run"))
                or alias in ("instructions_allocated", "instructions_error")
                or alias in initialization_readonly
            )
            if roots[0]["mutable"] is not (not readonly):
                raise ValueError(f"private bridge root authority changed: {source}")
        if alias.startswith("initialization_") and receiver is not None:
            if (
                len(parameters) > 4
                or any(shape(parameter)[0] not in ("i64", "u64", "u8", "bool", "enum") for parameter in parameters)
                or shape(result)[0] not in ("i64", "u64", "u8", "bool", "enum")
            ):
                raise ValueError(f"private initialization register signature changed: {source}")
        offset = 0
        for actual, expected in zip(function["parameters"], parameters):
            if not matches(actual, expected) or actual["offset"] != offset:
                raise ValueError(f"private bridge parameter changed: {source}")
            offset += actual["bytes"]
        if function["parameter_bytes"] != offset:
            raise ValueError(f"private bridge record changed: {source}")
        entries[alias] = symbol
    # Cleanup receives a generated prefix of the live transfer record. Refuse
    # layout drift before any host code can reinterpret that enclosing prefix.
    _, ingest = abi_declaration(facts, "functions", "compiler_frontend::resolver_ingest")
    for source, count in (("compiler_frontend::resolver_release", 2), ("compiler_frontend::resolver_release_pair", 3)):
        _, release = abi_declaration(facts, "functions", source)
        if (
            release["parameters"] != ingest["parameters"][:count]
            or release["parameter_bytes"] != ingest["parameters"][count]["offset"]
        ):
            raise ValueError(f"private resolver owner prefix changed: {source}")
    return entries


MESSAGE_ROLES = {"name": "DiagnosticNameId", "type": "DiagnosticTypeId", "integer": "DiagnosticInteger"}
MESSAGE_ORIGINS = {
    "": "source_or_synthetic",
    "unlocated": "unlocated",
    "synthetic": "synthetic",
    "integrity": "unlocated",
}


def lowering_messages(source, facts):
    """Host message table from the `//:` lines above each LoweringError case."""
    start = source.index("enum class LoweringError {")
    block = source[start : source.index("};", start)].splitlines()[1:]
    messages, pending = {}, []
    for line in (raw.strip() for raw in block):
        if line.startswith("//:"):
            pending.append(line[3:].strip())
        elif not line or line.startswith("//"):
            if pending:
                raise ValueError("lowering message text must directly precede its reason")
        else:
            name = line.removesuffix(",")
            if not re.fullmatch(r"[a-z][a-z0-9_]*", name) or name in messages:
                raise ValueError("unsupported or repeated lowering reason: " + line)
            messages[name] = " ".join(pending)
            pending = []
    if pending:
        raise ValueError("lowering message text must directly precede its reason")
    _, reasons = abi_declaration(facts, "enums", "compiler_lowering::LoweringError")
    if list(messages) != list(reasons["cases"]) or list(reasons["cases"].values()) != list(range(len(messages))):
        raise ValueError("lowering messages differ from the compiled LoweringError reasons")
    rows = []
    for name, text in messages.items():
        if name == "none":
            if text:
                raise ValueError("the none reason has no message")
            rows.append(
                "    {nullptr, MessageOrigin::unlocated, false, "
                "{OperandRole::NoDiagnosticValue, OperandRole::NoDiagnosticValue}},"
            )
            continue
        flag, _, body = text.partition("] ") if text.startswith("[") else ("", "", text)
        flag = flag.removeprefix("[")
        holes = re.findall(r"\{([^}]*)\}", body)
        if (
            not body
            or flag not in MESSAGE_ORIGINS
            or len(holes) > 2
            or any(h not in MESSAGE_ROLES for h in holes)
            or body.count("{") != len(holes)
            or body.count("}") != len(holes)
        ):
            raise ValueError("unsupported lowering message for " + name)
        if flag == "integrity" and holes:
            raise ValueError("integrity messages carry no payload values: " + name)
        roles = [MESSAGE_ROLES[h] for h in holes] + ["NoDiagnosticValue"] * (2 - len(holes))
        literal = '"' + body.replace("\\", "\\\\").replace('"', '\\"') + '"'
        rows.append(
            f"    {{{literal}, MessageOrigin::{MESSAGE_ORIGINS[flag]}, {'true' if flag == 'integrity' else 'false'}, "
            f"{{OperandRole::{roles[0]}, OperandRole::{roles[1]}}}}},"
        )
    return [
        "namespace aurora::hosted_abi::compiler_lowering {",
        "enum class MessageOrigin : std::uint8_t { source_or_synthetic, synthetic, unlocated };",
        "struct LoweringMessage {",
        "    const char *text;",
        "    MessageOrigin origin;",
        "    bool integrity;",
        "    std::array<OperandRole, 2> values;",
        "};",
        f"inline constexpr std::array<LoweringMessage, {len(rows)}> loweringMessages{{{{",
        *rows,
        "}};",
        "}",
    ]


def owner_messages(source, facts, namespace, enumeration, function):
    """Render constant owner diagnostics from their source-owned reasons."""
    start = source.index("enum class " + enumeration + " {")
    block = source[start : source.index("};", start)].splitlines()[1:]
    messages, pending = {}, []
    for line in (raw.strip() for raw in block):
        if line.startswith("//:"):
            pending.append(line[3:].strip())
        elif not line or line.startswith("//"):
            if pending:
                raise ValueError("owner message must directly precede its reason")
        else:
            name = line.removesuffix(",")
            if not re.fullmatch(r"[a-z][a-z0-9_]*", name) or name in messages:
                raise ValueError("unsupported or repeated owner reason: " + line)
            text = " ".join(pending)
            if (name == "none") != (not text):
                raise ValueError("owner reason requires exactly one constant message: " + name)
            messages[name] = text
            pending = []
    _, reasons = abi_declaration(facts, "enums", namespace + "::" + enumeration)
    if pending or list(messages) != list(reasons["cases"]):
        raise ValueError("owner messages differ from the compiled reasons")
    return [
        "namespace aurora::hosted_abi::" + namespace + " {",
        "inline constexpr const char *" + function + "(" + enumeration + " reason) {",
        "    switch (reason) {",
        *[
            f"    case {enumeration}::{name}: return {json.dumps(text, ensure_ascii=True) if text else 'nullptr'};"
            for name, text in messages.items()
        ],
        "    }",
        "    return nullptr;",
        "}",
        "}",
    ]


def metadata_messages(source, facts):
    return owner_messages(source, facts, "compiler_ir_metadata", "MetadataError", "metadataErrorMessage")


def instruction_messages(source, facts):
    return owner_messages(source, facts, "compiler_ir_instructions", "InstructionError", "instructionErrorMessage")


def frontend_abi_header(facts, messages=None, metadata_source=None, instruction_source=None):
    """Render compiler-described classes and enums without a second field schema."""
    frontend_abi_entries(facts)
    lines = [
        "// Generated from compiler ABI facts; do not edit.",
        "#pragma once",
        "#include <array>",
        "#include <cstddef>",
        "#include <cstdint>",
    ]

    def number(value):
        if type(value) is not int or not 0 <= value <= 65536:
            raise ValueError("invalid private ABI extent")
        return value

    def identifier(name):
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError("unsupported private ABI identifier")
        return name

    names = {}
    for group in ("enums", "records"):
        for symbol, declaration in facts[group].items():
            name = "::".join(identifier(part) for part in declaration["source_name"].split("::"))
            if name in names.values():
                raise ValueError("ambiguous private ABI source name")
            names[symbol] = name

    def cpp_name(symbol):
        if symbol not in names:
            raise ValueError("unknown private ABI type")
        return "aurora::hosted_abi::" + names[symbol]

    for symbol, declaration in sorted(facts["enums"].items(), key=lambda item: names[item[0]]):
        namespace, _, name = names[symbol].rpartition("::")
        lines += [
            "namespace aurora::hosted_abi" + ("::" + namespace if namespace else "") + " {",
            f"enum class {name} : std::int64_t {{",
        ]
        for case, value in declaration["cases"].items():
            identifier(case)
            if type(value) is not int or not -(2**63) <= value < 2**63:
                raise ValueError("unsupported private ABI enum value")
            lines.append(f"    {case} = {value},")
        lines += ["};", "}"]

    def record(name, size, alignment, members):
        nonlocal lines
        size, alignment = number(size), number(alignment)
        if alignment not in (1, 8) or not size:
            raise ValueError("unsupported private ABI alignment/size")
        lines.append(f"struct alignas({alignment}) {name} {{")
        field_names = {field for _, _, _, field in members}

        def padding_name(candidate):
            while candidate in field_names:
                candidate += "_"
            return candidate

        cursor = 0
        for index, (offset, width, cpp, field) in enumerate(members):
            offset, width = number(offset), number(width)
            if offset < cursor or width <= 0 or offset + width > size:
                raise ValueError("overlapping private ABI fields")
            if offset > cursor:
                lines.append(
                    f"    std::array<std::byte, {offset - cursor}> {padding_name(f'abi_padding_{index}')}{{}};"
                )
            lines.append(f"    {cpp} {field}{{}};")
            cursor = offset + width
        if cursor < size:
            lines.append(f"    std::array<std::byte, {size - cursor}> {padding_name('abi_tail_padding')}{{}};")
        lines += ["};", f"static_assert(sizeof({name}) == {size} && alignof({name}) == {alignment});"]
        for offset, width, _, field in members:
            lines.append(f"static_assert(offsetof({name}, {field}) == {offset});")
            lines.append(f"static_assert(sizeof({name}::{field}) == {width});")

    emitted, active = set(), set()

    def owning(symbol, ancestors=()):
        if symbol in ancestors or symbol not in facts["records"]:
            raise ValueError("invalid private ABI record dependency")
        return any(
            field["kind"] == "owner" or (field["kind"] == "class" and owning(field["type_name"], (*ancestors, symbol)))
            for field in facts["records"][symbol]["fields"]
        )

    def copied_type(field):
        kind, width = field["kind"], field["bytes"]
        if field.get("array_length", 0):
            raise ValueError("array field is outside the private copied ABI")
        if kind in ("enum", "class"):
            symbol = field["type_name"]
            if kind == "class":
                emit_record(symbol)
            expected = 8 if kind == "enum" else facts["records"][symbol]["reserved"]
            if width != expected:
                raise ValueError("private nested ABI extent mismatch")
            return cpp_name(symbol)
        if kind not in ("i64", "u64", "u8", "bool") or width != (1 if kind == "u8" else 8):
            raise ValueError("unsupported private copied field")
        return "std::uint8_t" if kind == "u8" else "std::uint64_t" if kind == "u64" else "std::int64_t"

    def emit_record(symbol):
        if symbol in emitted:
            return
        if symbol in active or symbol not in facts["records"]:
            raise ValueError("invalid private ABI record dependency")
        active.add(symbol)
        declaration = facts["records"][symbol]
        # Owning descriptors never become host-inspectable fields. The host only
        # supplies storage which Aurora constructs and consumes through bridges.
        opaque = owning(symbol)
        members = []
        for field in declaration["fields"] if not opaque else []:
            name = identifier(field["name"])
            members.append((field["offset"], field["bytes"], copied_type(field), name))
        namespace, _, name = names[symbol].rpartition("::")
        lines.append("namespace aurora::hosted_abi" + ("::" + namespace if namespace else "") + " {")
        if opaque:
            size = number(declaration["reserved"])
            members = [(0, size, f"std::array<std::byte, {size}>", "storage")]
        record(name, declaration["reserved"], declaration["alignment"], members)
        lines.append("}")
        active.remove(symbol)
        emitted.add(symbol)

    for symbol in sorted(facts["records"], key=lambda symbol: names[symbol]):
        emit_record(symbol)

    lines.append("namespace aurora::hosted_abi {")
    # A closed host binding, not general access to owning objects. Source review
    # binds each pool name to its row type; predecessor facts provide the physical
    # offsets and copied row shape, but do not claim to encode owner element identity.
    _, metadata_store = abi_declaration(facts, "records", "compiler_ir_metadata::MetadataStore")
    metadata_pools = {
        "bytes": None,
        "types": "RawTypeRow",
        "classes": "ClassRow",
        "fields": "FieldRow",
        "storage": "StorageRow",
        "indices": "IndexRow",
        "descriptors": "DescriptorRow",
        "views": "ViewRow",
        "enums": "EnumRow",
        "callables": "CallableRow",
        "slots": "SlotRow",
        "results": "ClassResultRow",
        "frames": "FrameRow",
    }
    owners = {field["name"]: field for field in metadata_store["fields"] if field["kind"] == "owner"}
    if owners.keys() != metadata_pools.keys():
        raise ValueError("private metadata owner pools changed")

    def qword_row(symbol, ancestors=()):
        if symbol in ancestors:
            raise ValueError("cyclic private metadata row")
        for field in facts["records"][symbol]["fields"]:
            if field.get("array_length", 0):
                raise ValueError("array in private metadata row")
            if field["kind"] == "class":
                qword_row(field["type_name"], (*ancestors, symbol))
            elif field["kind"] not in ("i64", "u64") or field["bytes"] != 8:
                raise ValueError("private metadata row requires integer words")

    for field_name, row_name in metadata_pools.items():
        field = owners[field_name]
        offset, width = number(field["offset"]), number(field["bytes"])
        if width != 32 or field.get("array_length", 0) or offset + width > metadata_store["size"]:
            raise ValueError("private metadata owner descriptor changed: " + field_name)
        lines += [
            f"inline constexpr std::size_t metadataStore_{field_name}Offset = {offset};",
            f"inline constexpr std::size_t metadataStore_{field_name}Bytes = {width};",
        ]
        if row_name is not None:
            symbol, row = abi_declaration(facts, "records", "compiler_ir_metadata::" + row_name)
            qword_row(symbol)
            stride = number(row["size"])
            if stride == 0 or stride > 520 or stride != row["reserved"] or row["alignment"] != 8:
                raise ValueError("private metadata row stride changed: " + row_name)
            lines += [
                f"inline constexpr std::size_t metadata{row_name}PhysicalBytes = {stride};",
                f"static_assert(sizeof({cpp_name(symbol)}) == metadata{row_name}PhysicalBytes);",
            ]
    _, instruction_store = abi_declaration(facts, "records", "compiler_ir_instructions::InstructionStore")
    instruction_pools = {
        "instructions": "RawInstructionRow",
        "operands": "RawOperandRow",
        "literals": None,
        "codeOrder": "CodeRow",
        "bodies": "BodyRow",
    }
    owners = {field["name"]: field for field in instruction_store["fields"] if field["kind"] == "owner"}
    if owners.keys() != instruction_pools.keys():
        raise ValueError("private instruction owner pools changed")
    for field_name, row_name in instruction_pools.items():
        field = owners[field_name]
        offset, width = number(field["offset"]), number(field["bytes"])
        if width != 32 or field.get("array_length", 0) or offset + width > instruction_store["size"]:
            raise ValueError("private instruction owner descriptor changed: " + field_name)
        lines += [
            f"inline constexpr std::size_t instructionStore_{field_name}Offset = {offset};",
            f"inline constexpr std::size_t instructionStore_{field_name}Bytes = {width};",
        ]
        if row_name is not None:
            symbol, row = abi_declaration(facts, "records", "compiler_ir_instructions::" + row_name)
            qword_row(symbol)
            stride = number(row["size"])
            if stride == 0 or stride > 520 or stride != row["reserved"] or row["alignment"] != 8:
                raise ValueError("private instruction row stride changed: " + row_name)
            lines += [
                f"inline constexpr std::size_t instruction{row_name}PhysicalBytes = {stride};",
                f"static_assert(sizeof({cpp_name(symbol)}) == instruction{row_name}PhysicalBytes);",
            ]
    # Mutable initialization pools never expose native payload observations.
    # Still validate their complete actual owner/control layout against emitted
    # facts before producing the opaque enclosing create/release record.
    _, initialization_workspace = abi_declaration(
        facts, "records", "compiler_ir_initialization::InitializationWorkspace"
    )
    initialization_fields = (
        ("currentWords", "owner"),
        ("retainedWords", "owner"),
        ("retainedCounts", "owner"),
        ("callableId", "i64"),
        ("scalarBegin", "i64"),
        ("scalarCount", "i64"),
        ("objectBegin", "i64"),
        ("objectCount", "i64"),
        ("wordCount", "i64"),
        ("retainedCount", "i64"),
        ("retainedCapacity", "i64"),
        ("currentMust", "i64"),
        ("currentMay", "i64"),
        ("statusValue", "enum"),
    )
    fields = initialization_workspace["fields"]
    if (
        len(fields) != len(initialization_fields)
        or initialization_workspace["alignment"] != 8
        or initialization_workspace["reserved"] != initialization_workspace["size"]
    ):
        raise ValueError("private initialization owner layout changed")
    status, _ = abi_declaration(facts, "enums", "compiler_ir_initialization::InitializationStatus")
    end = 0
    for field, (name, kind) in zip(fields, initialization_fields):
        offset, width = number(field["offset"]), number(field["bytes"])
        if (
            field["name"] != name
            or field["kind"] != kind
            or field.get("array_length", 0)
            or offset < end
            or offset % 8 != 0
            or width != (32 if kind == "owner" else 8)
            or offset + width > initialization_workspace["size"]
            or (kind == "enum" and field.get("type_name") != status)
        ):
            raise ValueError("private initialization field changed: " + name)
        end = offset + width
        lines += [
            f"inline constexpr std::size_t initializationWorkspace_{name}Offset = {offset};",
            f"inline constexpr std::size_t initializationWorkspace_{name}Bytes = {width};",
        ]
    if end != initialization_workspace["size"]:
        raise ValueError("private initialization owner extent changed")
    for row_name, kind, field_names in (
        ("WordPair", "u64", ("mustBits", "mayBits")),
        ("CountPair", "i64", ("mustCount", "mayCount")),
    ):
        symbol, row = abi_declaration(facts, "records", "compiler_ir_initialization::" + row_name)
        qword_row(symbol)
        stride = number(row["size"])
        if (
            row["alignment"] != 8
            or stride != row["reserved"]
            or stride != 16
            or len(row["fields"]) != len(field_names)
            or any(
                field["name"] != name or field["kind"] != kind or field["offset"] != index * 8
                for index, (field, name) in enumerate(zip(row["fields"], field_names))
            )
        ):
            raise ValueError("private initialization row changed: " + row_name)
        lines += [
            f"inline constexpr std::size_t initialization{row_name}PhysicalBytes = {stride};",
            f"static_assert(sizeof({cpp_name(symbol)}) == initialization{row_name}PhysicalBytes);",
        ]
    # The only manual physical shape is the trusted contiguous readonly span.
    # Source records and their nesting use the compiler's names and field facts.
    if facts["span_bytes"] != 56:
        raise ValueError("unsupported builtin span ABI")
    record(
        "BuiltinSpan",
        56,
        8,
        [
            (0, 8, "std::uint64_t", "kind"),
            (8, 8, "const char *", "backing"),
            (16, 24, "std::array<std::uint64_t, 3>", "reserved"),
            (40, 8, "std::int64_t", "start"),
            (48, 8, "std::int64_t", "length"),
        ],
    )
    for name, source, fields in ARGUMENT_RECORDS:
        _, function = abi_declaration(facts, "functions", source)
        if len(fields) != len(function["parameters"]):
            raise ValueError(f"private ABI argument names changed: {source}")
        members = []
        for field, parameter in zip(fields, function["parameters"]):
            kind = parameter["kind"]
            cpp = "BuiltinSpan" if kind == "span" else "std::uint64_t" if kind == "region" else copied_type(parameter)
            members.append((parameter["offset"], parameter["bytes"], cpp, field))
        record(name, function["parameter_bytes"], 8, members)
    lines += [
        "inline constexpr std::size_t frameBytes = sizeof(compiler_parser::ParseFrame);",
        "inline constexpr std::size_t arenaBytes = sizeof(compiler_parser::AstArena);",
        "inline constexpr std::size_t arenaAlignment = alignof(compiler_parser::AstArena);",
        "inline constexpr std::size_t sessionBytes = sizeof(compiler_resolver::Session);",
        "inline constexpr std::size_t sessionAlignment = alignof(compiler_resolver::Session);",
        "static_assert(offsetof(ResolverRelease, session) == offsetof(ResolverIngest, session));",
        "static_assert(sizeof(ResolverRelease) == offsetof(ResolverIngest, parsed));",
        "static_assert(offsetof(ResolverReleasePair, session) == offsetof(ResolverIngest, session));",
        "static_assert(offsetof(ResolverReleasePair, parsed) == offsetof(ResolverIngest, parsed));",
        "static_assert(sizeof(ResolverReleasePair) == offsetof(ResolverIngest, module));",
        "static_assert(sizeof(void *) == 8);",
        "}",
    ]
    if messages is not None:
        lines += lowering_messages(messages, facts)
    if metadata_source is not None:
        lines += metadata_messages(metadata_source, facts)
    if instruction_source is not None:
        lines += instruction_messages(instruction_source, facts)
    return "\n".join(lines) + "\n"


def frontend_bridge(bridge, facts):
    for alias, symbol in sorted(frontend_abi_entries(facts).items(), key=lambda item: len(item[0]), reverse=True):
        function = facts["functions"][symbol]
        for index, parameter in enumerate(function["parameters"]):
            bridge = bridge.replace(f"__aurora_parameter_{alias}_{index}", str(parameter["offset"]))
        bridge = bridge.replace("__aurora_frontend_" + alias, symbol)
    if "__aurora_frontend_" in bridge or "__aurora_parameter_" in bridge:
        raise ValueError("unknown private frontend bridge entry")
    return bridge


def stage_modules(module_root, modules):
    """Copy each compiler module unchanged under its own name in the module root."""
    destination = module_root / "aurora" / "compiler"
    destination.mkdir(parents=True, exist_ok=True)
    for source in modules:
        shutil.copyfile(source, destination / source.name)


def emit(
    compiler,
    source,
    bridges,
    output,
    module_root,
    messages,
    metadata_source,
    instruction_source,
    compatible_header=None,
):
    raw = output.with_suffix(".generated.s")
    facts_output = output.with_suffix(".abi.json")
    command = ["--local-symbols", "--abi-facts", str(facts_output.resolve())]
    command += ["--module-root", str(module_root.resolve())]
    command += [str(source.resolve()), "-o", str(raw.resolve())]
    subprocess.run([str(compiler.resolve()), *command], check=True)
    facts = json.loads(facts_output.read_text())
    header = output.parent / (output.stem.replace("-", "_") + "_abi.hpp")
    content = frontend_abi_header(
        facts, messages.read_text(), metadata_source.read_text(), instruction_source.read_text()
    ).encode()
    if compatible_header is not None and compatible_header.read_bytes() != content:
        raise ValueError("stage2 ABI header differs from the header used by shared host objects")
    if not header.exists() or header.read_bytes() != content:
        header.write_bytes(content)
    # Symbol spellings come from this emitted module; only register moves are trusted.
    output.write_bytes(
        b"\n".join([raw.read_bytes(), *(frontend_bridge(bridge.read_text(), facts).encode() for bridge in bridges)])
    )


def main():
    # COMPILER --output OUTPUT INPUT...: .au inputs are the compiler modules,
    # .S inputs are the bridges in order, and an optional .hpp is the header
    # that stage-2 output must reproduce.
    arguments = sys.argv[1:]
    if len(arguments) < 4 or arguments[1] != "--output":
        raise ValueError("expected COMPILER --output OUTPUT INPUT...")
    compiler, output = Path(arguments[0]), Path(arguments[2])
    inputs = [Path(argument) for argument in arguments[3:]]
    modules = [path for path in inputs if path.suffix == ".au"]
    bridges = [path for path in inputs if path.suffix == ".S"]
    headers = [path for path in inputs if path.suffix == ".hpp"]
    names = [path.name for path in modules]
    if (
        len(modules) + len(bridges) + len(headers) != len(inputs)
        or len(headers) > 1
        or len(set(names)) != len(names)
        or not {
            "frontend.au",
            "lowering_errors.au",
            "ir_metadata_storage.au",
            "ir_instruction_storage.au",
            "ir_initialization.au",
        }
        <= set(names)
    ):
        raise ValueError("expected unique .au modules including frontend.au, .S bridges and at most one .hpp header")
    module_root = output.parent / "compiler-modules"
    stage_modules(module_root, modules)
    emit(
        compiler,
        modules[names.index("frontend.au")],
        bridges,
        output,
        module_root,
        modules[names.index("lowering_errors.au")],
        modules[names.index("ir_metadata_storage.au")],
        modules[names.index("ir_instruction_storage.au")],
        headers[0] if headers else None,
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        sys.exit(f"bootstrap frontend: {error}")
