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
            ["span", "compiler_lexer::Cursor", "compiler_parser::Stop", "compiler_parser::TypeContext", "i64"],
            "compiler_parser::ParseResult",
        ),
        (
            "parser_admit",
            "compiler_parser::admit",
            arena,
            ["span", "i64", "compiler_parser::AdmissionConfig"],
            "compiler_parser::AdmissionResult",
        ),
        ("parser_release", "compiler_parser::release", None, ["region", "compiler_parser::AstArena"], "i64"),
    ]
    checks += [
        ("parser_" + name, "compiler_parser::" + name, arena, [], "i64")
        for name in ("node_count", "edge_count", "type_count", "syntax_count")
    ]
    checks += [
        ("parser_" + name, "compiler_parser::" + name, arena, ["i64"], "compiler_parser::" + result)
        for name, result in (
            ("read_node", "AstNode"),
            ("read_edge", "ChildEdge"),
            ("read_type", "TypeSyntax"),
            ("read_syntax", "SyntaxNode"),
        )
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
    for name, source, fields in (
        ("LexerInput", "compiler_lexer::next_lexeme", ("source", "cursor")),
        ("ParserInput", "compiler_parser::parse", ("source", "cursor", "stop", "context", "enum_count")),
        ("AdmissionInput", "compiler_parser::admit", ("source", "root", "configuration")),
        ("ParserCreate", "compiler_parser::create", ("region", "capacity")),
        ("ParserRelease", "compiler_parser::release", ("region", "arena")),
    ):
        _, function = abi_declaration(facts, "functions", source)
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
        "static_assert(sizeof(void *) == 8);",
        "}",
    ]
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
    for source, name in ((lexer, "lexer.au"), (arena, "syntax_arena.au")):
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
