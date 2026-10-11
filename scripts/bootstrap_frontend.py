#!/usr/bin/env python3
"""Emit the private hosted frontend and its compiler-described ABI.

The compiler-module root contains exact exported source copies. Generated Aurora
bindings remain local; only the two trusted assembly bridges expose host entries.
"""

from pathlib import Path
import re
import json
import shutil
import subprocess
import sys


def abi_declaration(facts, group, source_name):
    """Find a resolved declaration; source spelling is never a mangling recipe."""
    if facts.get("version") != 1 or not isinstance(facts.get(group), dict):
        raise ValueError("unsupported compiler ABI facts")
    found = [(symbol, entry) for symbol, entry in facts[group].items() if entry["source_name"] == source_name]
    if len(found) != 1:
        raise ValueError(f"expected one ABI declaration: {source_name}")
    return found[0]


def abi_function_symbol(facts, source_name):
    return abi_declaration(facts, "functions", source_name)[0]


def frontend_abi_entries(facts):
    """Check the fixed register bridges before allowing generated record writes."""

    def shape(source):
        if source in ("i64", "region", "span"):
            return source, None, facts["span_bytes"] if source == "span" else 8
        group = "enums" if source == "compiler_parser::Stop" else "records"
        symbol, record = abi_declaration(facts, group, source)
        return "enum" if group == "enums" else "class", symbol, 8 if group == "enums" else record["reserved"]

    def matches(actual, expected):
        kind, symbol, width = shape(expected)
        return actual["kind"] == kind and actual.get("type_name") == symbol and actual["bytes"] == width

    arena, _ = abi_declaration(facts, "records", "compiler_parser::AstArena")
    checks = [
        (
            "lexer_next",
            "compiler_lexer::next_lexeme",
            None,
            ["span", "compiler_lexer::Cursor"],
            "compiler_lexer::Lexeme",
        ),
        ("parser_create", "compiler_parser::create", None, ["region", "i64"], "compiler_parser::AstArena"),
        (
            "parser_parse",
            "compiler_parser::parse",
            arena,
            ["span", "compiler_lexer::Cursor", "compiler_parser::Stop", "compiler_parser::TypeContext"],
            "compiler_parser::ParseResult",
        ),
        ("parser_release", "compiler_parser::release", None, ["region", "compiler_parser::AstArena"], "i64"),
    ]
    checks += [
        ("parser_" + name, "compiler_parser::" + name, arena, [], "i64")
        for name in ("node_count", "edge_count", "type_count")
    ]
    checks += [
        ("parser_" + name, "compiler_parser::" + name, arena, ["i64"], "compiler_parser::" + result)
        for name, result in (("read_node", "AstNode"), ("read_edge", "ChildEdge"), ("read_type", "TypeSyntax"))
    ]
    entries = {}
    for alias, source, receiver, parameters, result in checks:
        symbol, function = abi_declaration(facts, "functions", source)
        if (
            function["receiver"] != receiver
            or len(function["parameters"]) != len(parameters)
            or not matches(function["result"], result)
        ):
            raise ValueError(f"private bridge signature changed: {source}")
        offset = 0
        for actual, expected in zip(function["parameters"], parameters):
            if not matches(actual, expected) or actual["offset"] != offset:
                raise ValueError(f"private bridge parameter changed: {source}")
            offset += actual["bytes"]
        if function["parameter_bytes"] != offset:
            raise ValueError(f"private bridge record changed: {source}")
        entries[alias] = symbol
    return entries


def frontend_abi_header(facts):
    """Generate only this private frontend's supported record shapes."""
    frontend_abi_entries(facts)
    lines = [
        "// Generated from compiler ABI facts; do not edit.",
        "#pragma once",
        "#include <array>",
        "#include <cstddef>",
        "#include <cstdint>",
    ]
    enums = {}
    enum_specs = [
        ("compiler_lexer::Event", "hosted_lexer", "Event"),
        ("compiler_parser::NodeKind", "hosted_parser", "NodeKind"),
        ("compiler_parser::TypeKind", "hosted_parser", "TypeKind"),
        ("compiler_parser::ParseStatus", "hosted_parser", "Status"),
        ("compiler_parser::Stop", "hosted_parser", "Stop"),
    ]
    type_aliases = {
        "i64_type": "I64",
        "u64_type": "U64",
        "u8_type": "U8",
        "bool_type": "Bool",
        "array_type": "Array",
        "own_type": "Own",
        "ref_type": "Ref",
        "mutref_type": "MutRef",
        "builtin_type": "Builtin",
    }
    for source, namespace, name in enum_specs:
        symbol, record = abi_declaration(facts, "enums", source)
        cpp = f"aurora::{namespace}::{name}"
        enums[symbol] = cpp
        lines += [f"namespace aurora::{namespace} {{", f"enum class {name} : std::int64_t {{"]
        for case, value in record["cases"].items():
            if not re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*", case) or type(value) is not int:
                raise ValueError("unsupported private ABI enum case")
            alias = type_aliases.get(case) if name == "TypeKind" else None
            alias = alias or "".join(part.capitalize() for part in case.split("_"))
            lines.append(f"    {alias} = {value},")
        lines += ["};", "}"]
    lines.append("namespace aurora::hosted_abi {")

    def declaration(source):
        return abi_declaration(facts, "records", source)

    def number(value):
        if type(value) is not int or not 0 <= value <= 65536:
            raise ValueError("invalid private ABI extent")
        return value

    def field_type(field):
        if field["array_length"] != 0:
            raise ValueError("array field is outside the private copied ABI")
        kind = field["kind"]
        if kind == "enum":
            cpp = enums.get(field["type_name"])
            if cpp is None or field["bytes"] != 8:
                raise ValueError("unknown private ABI enum field")
            return cpp
        if kind not in ("i64", "u64", "u8", "bool") or field["bytes"] != (1 if kind == "u8" else 8):
            raise ValueError("unsupported private copied field")
        return "std::uint8_t" if kind == "u8" else "std::uint64_t" if kind == "u64" else "std::int64_t"

    def fields(source, aliases, defaults=None):
        _, record = declaration(source)
        defaults = defaults or {}
        if set(aliases) != {field["name"] for field in record["fields"]}:
            raise ValueError(f"private ABI fields changed: {source}")
        result = []
        for field in record["fields"]:
            name = aliases[field["name"]]
            cpp = field_type(field)
            default = defaults.get(name, f"static_cast<{cpp}>(-1)")
            result.append((field["offset"], field["bytes"], cpp, name, default))
        return record, result

    def record(name, size, alignment, members):
        nonlocal lines
        size, alignment = number(size), number(alignment)
        if alignment not in (1, 8) or not size:
            raise ValueError("unsupported private ABI alignment/size")
        lines.append(f"struct alignas({alignment}) {name} {{")
        cursor = 0
        for index, (offset, width, cpp, field, default) in enumerate(members):
            offset, width = number(offset), number(width)
            if offset < cursor or width <= 0 or offset + width > size:
                raise ValueError("overlapping private ABI fields")
            if offset > cursor:
                lines.append(f"    std::array<std::byte, {offset - cursor}> padding{index}{{}};")
            lines.append(f"    {cpp} {field} = {default};")
            cursor = offset + width
        if cursor < size:
            lines.append(f"    std::array<std::byte, {size - cursor}> tailPadding{{}};")
        lines += ["};", f"static_assert(sizeof({name}) == {size} && alignof({name}) == {alignment});"]
        for offset, _, _, field, _ in members:
            lines.append(f"static_assert(offsetof({name}, {field}) == {offset});")

    copied = [
        (
            "Lexeme",
            "compiler_lexer::Lexeme",
            {"event": "event", "offset": "offset", "line": "line", "line_start": "lineStart"},
            {},
        ),
        (
            "ParseResult",
            "compiler_parser::ParseResult",
            {
                "result": "status",
                "root_node": "root",
                "node_count": "count",
                "token_count": "tokens",
                "source_offset": "offset",
            },
            {"status": "aurora::hosted_parser::Status::Invalid"},
        ),
        (
            "Node",
            "compiler_parser::AstNode",
            {
                "tag": "kind",
                "token_index": "token",
                "first_child": "first",
                "second_child": "second",
                "tree_depth": "depth",
                "name_end": "nameEnd",
                "closing_token": "close",
            },
            {"kind": "aurora::hosted_parser::NodeKind::Invalid"},
        ),
        (
            "Edge",
            "compiler_parser::ChildEdge",
            {
                "child_node": "child",
                "previous_edge": "previous",
                "argument_count": "count",
                "tree_depth": "depth",
                "field_token": "field",
            },
            {},
        ),
        (
            "TypeSyntax",
            "compiler_parser::TypeSyntax",
            {
                "tag": "kind",
                "token_index": "token",
                "name_end": "nameEnd",
                "closing_token": "close",
                "first_child": "first",
                "second_child": "second",
                "owner_token": "owner",
                "owner_role": "role",
            },
            {"kind": "aurora::hosted_parser::TypeKind::Invalid", "role": "0"},
        ),
    ]
    for name, source, aliases, defaults in copied:
        layout, members = fields(source, aliases, defaults)
        record(name, layout["reserved"], layout["alignment"], members)

    cursor_symbol, cursor = declaration("compiler_lexer::Cursor")
    context_symbol, context = declaration("compiler_parser::TypeContext")
    cursor_aliases = {"offset": "offset", "line": "line", "line_start": "lineStart"}
    context_aliases = {
        "first_begin": "type1Begin",
        "first_end": "type1End",
        "second_begin": "type2Begin",
        "second_end": "type2End",
        "capacity_begin": "capacityBegin",
        "capacity_end": "capacityEnd",
        "template_mode": "mode",
    }
    _, cursor_fields = fields("compiler_lexer::Cursor", cursor_aliases, {"offset": "0", "line": "1", "lineStart": "0"})
    _, context_fields = fields(
        "compiler_parser::TypeContext", context_aliases, {name: "0" for name in context_aliases.values()}
    )
    # One intentionally trusted builtin encoding: a contiguous readonly span.
    # Aurora source classes, enums and composite argument extents are generated.
    if facts["span_bytes"] != 56:
        raise ValueError("unsupported builtin span ABI")
    span = [
        (0, 8, "std::uint64_t", "kind", "0"),
        (8, 8, "const char *", "backing", "nullptr"),
        (16, 24, "std::array<std::uint64_t, 3>", "reserved", "{}"),
        (40, 8, "std::int64_t", "start", "0"),
        (48, 8, "std::int64_t", "length", "0"),
    ]
    for name, source, parser in (
        ("LexerInput", "compiler_lexer::next_lexeme", False),
        ("ParserInput", "compiler_parser::parse", True),
    ):
        _, function = abi_declaration(facts, "functions", source)
        params = function["parameters"]
        if (
            len(params) != (4 if parser else 2)
            or params[0]["kind"] != "span"
            or params[0]["bytes"] != 56
            or params[0]["offset"] != 0
        ):
            raise ValueError("unsupported private parser/lexer input")
        if params[1].get("type_name") != cursor_symbol or params[1]["bytes"] != cursor["reserved"]:
            raise ValueError("private cursor parameter mismatch")
        members = list(span) + [
            (params[1]["offset"] + off, width, cpp, field, default) for off, width, cpp, field, default in cursor_fields
        ]
        if parser:
            stop_symbol, _ = abi_declaration(facts, "enums", "compiler_parser::Stop")
            if (
                params[2].get("type_name") != stop_symbol
                or params[2]["bytes"] != 8
                or params[3].get("type_name") != context_symbol
                or params[3]["bytes"] != context["reserved"]
            ):
                raise ValueError("private parser context mismatch")
            members.append(
                (params[2]["offset"], 8, enums[stop_symbol], "stop", "aurora::hosted_parser::Stop::Semicolon")
            )
            members += [
                (params[3]["offset"] + off, width, cpp, field, default)
                for off, width, cpp, field, default in context_fields
            ]
        record(name, function["parameter_bytes"], 8, members)

    arena_symbol, arena = declaration("compiler_parser::AstArena")
    lines += [
        f"inline constexpr std::size_t arenaBytes = {number(arena['reserved'])};",
        f"inline constexpr std::size_t arenaAlignment = {number(arena['alignment'])};",
    ]
    for name, source, owning in (
        ("ParserCreate", "compiler_parser::create", False),
        ("ParserRelease", "compiler_parser::release", True),
    ):
        _, function = abi_declaration(facts, "functions", source)
        params = function["parameters"]
        if len(params) != 2 or params[0]["kind"] != "region" or params[0]["bytes"] != 8:
            raise ValueError("unsupported private arena authority record")
        members = [(params[0]["offset"], 8, "std::uint64_t", "region", "0")]
        if owning:
            if params[1].get("type_name") != arena_symbol or params[1]["bytes"] != arena["reserved"]:
                raise ValueError("private arena release extent mismatch")
            members.append((params[1]["offset"], arena["reserved"], "std::array<std::byte, arenaBytes>", "arena", "{}"))
        else:
            if (
                params[1]["kind"] != "i64"
                or params[1]["bytes"] != 8
                or function["result"].get("type_name") != arena_symbol
                or function["result"]["bytes"] != arena["reserved"]
            ):
                raise ValueError("private arena create extent mismatch")
            members.append((params[1]["offset"], 8, "std::int64_t", "capacity", "0"))
        record(name, function["parameter_bytes"], 8, members)
    lines += ["static_assert(sizeof(void *) == 8);", "}"]
    return "\n".join(lines) + "\n"


def frontend_bridge(bridge, facts):
    for alias, symbol in frontend_abi_entries(facts).items():
        bridge = bridge.replace("__aurora_frontend_" + alias, symbol)
    if "__aurora_frontend_" in bridge:
        raise ValueError("unknown private frontend bridge entry")
    return bridge


def stage_modules(module_root, lexer, arena):
    destination = module_root / "aurora" / "compiler"
    destination.mkdir(parents=True, exist_ok=True)
    for source, name in ((lexer, "lexer.au"), (arena, "expression_arena.au")):
        shutil.copyfile(source, destination / name)


def emit(compiler, source, bridges, output, module_root, compatible_header=None):
    raw = output.with_suffix(".generated.s")
    facts_output = output.with_suffix(".abi.json")
    command = ["--local-symbols", "--abi-facts", str(facts_output.resolve())]
    command += ["--module-root", str(module_root.resolve())]
    command += [str(source.resolve()), "-o", str(raw.resolve())]
    subprocess.run([str(compiler.resolve()), *command], check=True)
    facts = json.loads(facts_output.read_text())
    header = output.parent / (output.stem.replace("-", "_") + "_abi.hpp")
    content = frontend_abi_header(facts).encode()
    if compatible_header is not None and compatible_header.read_bytes() != content:
        raise ValueError("stage2 ABI header differs from the header used by shared host objects")
    if not header.exists() or header.read_bytes() != content:
        header.write_bytes(content)
    # Symbol spellings come from this emitted module; only register moves are trusted.
    output.write_bytes(
        b"\n".join([raw.read_bytes(), *(frontend_bridge(bridge.read_text(), facts).encode() for bridge in bridges)])
    )


def main():
    compiler, lexer, arena, parser, lexer_bridge, parser_bridge, output, *headers = map(Path, sys.argv[1:])
    if len(headers) > 1:
        raise ValueError("expected at most one shared-host ABI header")
    module_root = output.parent / "compiler-modules"
    stage_modules(module_root, lexer, arena)
    emit(compiler, parser, [lexer_bridge, parser_bridge], output, module_root, headers[0] if headers else None)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        sys.exit(f"bootstrap frontend: {error}")
