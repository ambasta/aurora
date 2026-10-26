#!/usr/bin/env python3
"""Emit one Aurora code artifact and its conservative module dependencies."""

import argparse
import json
import re
import sys
from pathlib import Path
import subprocess
import tempfile


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


def validate_terminal_paint_abi(facts):
    """The paint bridge's six-qword record must be exactly the compiled entry."""
    from bootstrap_frontend import abi_declaration, normalize_function_abi

    _, raw = abi_declaration(facts, "functions", "paint_terminal_cell")
    expected = {
        "source_name": "paint_terminal_cell",
        "receiver": None,
        "receiver_mutable": None,
        "borrowed_root_count": 0,
        "borrowed_roots": [],
        "borrowed_root_abi": {
            "kind": "none",
            "register": None,
            "tuple_payload_bytes": 0,
            "tuple_reserved_bytes": 0,
            "saved_root_reserved_bytes": 0,
        },
        "parameter_bytes": 48,
        "parameters": [{"offset": 0, "bytes": 16, "kind": "service"}]
        + [{"offset": offset, "bytes": 8, "kind": "u64"} for offset in (16, 24, 32, 40)],
        "result": {"bytes": 8, "kind": "bool"},
    }
    if normalize_function_abi(facts, raw) != expected:
        raise ValueError("Terminal paint entry shape does not match compiler facts")


def validate_program_session_abi(facts):
    """The session state is opaque; native code reads only the returned facts."""
    from bootstrap_frontend import abi_declaration, normalize_function_abi

    state_symbol, state = abi_declaration(facts, "records", "console::ProgramSession")
    effect_symbol, effect = abi_declaration(facts, "enums", "console::ProgramEffect")
    result_symbol, result = abi_declaration(facts, "records", "console::ProgramSessionUpdate")
    effects = (
        "invalid ready file_ready input note files upper read_note upper_note file peek wc crc unknown "
        "note_saved file_reply abort_file exited failed"
    ).split()
    if effect["cases"] != dict(zip(effects, range(len(effects)))):
        raise ValueError("Program session effect encoding does not match its native executor")
    if (state["size"], state["alignment"], state["reserved"]) != (32, 8, 32) or len(state["fields"]) != 4:
        raise ValueError("Program session state must occupy four copied scalar words")
    for index, field in enumerate(state["fields"]):
        if {key: value for key, value in field.items() if key != "name"} != {
            "offset": index * 8,
            "bytes": 8,
            "array_length": 0,
            "kind": "u64",
        }:
            raise ValueError("Program session initial representation must contain only scalar words")
    fields = [
        dict(name="session", offset=0, bytes=32, array_length=0, kind="class", type_name=state_symbol),
        dict(name="effect", offset=32, bytes=8, array_length=0, kind="enum", type_name=effect_symbol),
        dict(name="after_cr", offset=40, bytes=8, array_length=0, kind="u64"),
        dict(name="outcome", offset=48, bytes=8, array_length=0, kind="u64"),
    ]
    if result != dict(source_name="console::ProgramSessionUpdate", size=56, alignment=8, reserved=56, fields=fields):
        raise ValueError("Program session result layout does not match its native executor")
    _, function = abi_declaration(facts, "functions", "update_program_session")
    expected = {
        "source_name": "update_program_session",
        "receiver": None,
        "receiver_mutable": None,
        "borrowed_root_count": 0,
        "borrowed_roots": [],
        "borrowed_root_abi": {
            "kind": "none",
            "register": None,
            "tuple_payload_bytes": 0,
            "tuple_reserved_bytes": 0,
            "saved_root_reserved_bytes": 0,
        },
        "parameter_bytes": 56,
        "parameters": [dict(offset=0, bytes=32, kind="class", type_name=state_symbol)]
        + [dict(offset=offset, bytes=8, kind="u64") for offset in (32, 40, 48)],
        "result": dict(bytes=56, kind="class", type_name=result_symbol),
    }
    if normalize_function_abi(facts, function) != expected:
        raise ValueError("Program session entry shape does not match its native executor")


def validate_program_copied_abi(facts, service=False, replacement=False):
    """Admit the fixed private file/append records before an adapter can copy them."""
    from bootstrap_frontend import abi_declaration, normalize_function_abi

    def shape(source):
        if source in ("i64", "u64", "u8"):
            return dict(bytes=8, kind=source)
        group = "enums" if source == "console::FileEvent" else "records"
        symbol, value = abi_declaration(facts, group, source)
        return dict(
            bytes=8 if group == "enums" else value["reserved"],
            kind="enum" if group == "enums" else "class",
            type_name=symbol,
        )

    def record(source, size, fields, alignment=8):
        _, value = abi_declaration(facts, "records", source)
        expected, offset = [], 0
        for name, kind, count in fields:
            field = shape(kind)
            # Native bytes are dense byte arrays, not scalar ABI qwords.
            width = count if kind == "u8" and count else field["bytes"] * max(1, count)
            expected.append(dict(name=name, offset=offset, array_length=count, **{**field, "bytes": width}))
            offset += width
        if offset != size or value != dict(
            source_name=source, size=size, alignment=alignment, reserved=size, fields=expected
        ):
            raise ValueError("Protected copied record differs from its native boundary: " + source)

    def entry(source, parameters, result):
        _, raw = abi_declaration(facts, "functions", source)
        expected, offset = [], 0
        for kind in parameters:
            field = shape(kind)
            expected.append(dict(offset=offset, **field))
            offset += field["bytes"]
        value = normalize_function_abi(facts, raw)
        if value != dict(
            source_name=source,
            receiver=None,
            receiver_mutable=None,
            borrowed_root_count=0,
            borrowed_roots=[],
            borrowed_root_abi=dict(
                kind="none", register=None, tuple_payload_bytes=0, tuple_reserved_bytes=0, saved_root_reserved_bytes=0
            ),
            parameter_bytes=offset,
            parameters=expected,
            result=shape(result),
        ):
            raise ValueError("Protected copied entry differs from its native boundary: " + source)

    if service:
        record("kernel::NoteRead64", 72, [("bytes", "u8", 64), ("length", "i64", 0)])
        entry("aurora_user_main", ["i64", "i64", "i64", "kernel::NoteRead64", "kernel::NoteRead64"], "i64")
        return
    record("std::BinaryBuffer64", 64, [("elements", "u8", 64)], alignment=1)
    for source in ("console::FileName", "console::FileValue"):
        record(source, 72, [("bytes", "std::BinaryBuffer64", 0), ("length", "i64", 0)])
    record("console::SessionFiles", 264, [("records", "std::BinaryBuffer64", 4), ("occupied", "u64", 0)])
    record("console::ProtectedFiles", 272, [("files", "console::SessionFiles", 0), ("revision", "u64", 0)])
    record(
        "console::FileSelection",
        160,
        [
            ("name", "console::FileName", 0),
            ("revision", "u64", 0),
            ("replacement", "u64", 0),
            ("suffix", "console::FileValue", 0),
        ],
    )
    record("console::FileReply", 80, [("bytes", "u8", 64), ("length", "i64", 0), ("event", "console::FileEvent", 0)])
    _, event = abi_declaration(facts, "enums", "console::FileEvent")
    names = "unknown written read removed listed missing invalid full reserved".split()
    if event["cases"] != dict(zip(names, range(len(names)))):
        raise ValueError("File reply event encoding differs from its native boundary")
    record(
        "FileUpdate",
        520,
        [
            ("files", "console::ProtectedFiles", 0),
            ("reply", "console::FileReply", 0),
            ("action", "u64", 0),
            ("selection", "console::FileSelection", 0),
        ],
    )
    entry("update_files", ["console::ProtectedFiles", "std::BinaryBuffer64", "i64", "u64"], "FileUpdate")
    if replacement:
        record("FileMutation", 352, [("files", "console::ProtectedFiles", 0), ("reply", "console::FileReply", 0)])
        entry(
            "replace_files",
            ["console::ProtectedFiles", "console::FileSelection", "std::BinaryBuffer64", "i64"],
            "FileMutation",
        )


def validate_selected_source_abi(source, facts):
    # This existing compiled image has one exact private launch record. Other
    # uses of ipc-user-entry.S (snapshot, file-call, Call/Serve) retain theirs.
    if Path(source).name == "program-stream-service.au":
        validate_program_copied_abi(facts, service=True)


def render_bridge(source, facts):
    if "# PROGRAM_FILES_ABI:" in source:
        validate_program_copied_abi(facts, replacement="@replace_files@" in source)
    if "# PROGRAM_SESSION_ABI:" in source:
        validate_program_session_abi(facts)
    if "# UART_POLICY_ABI:" in source:
        validate_uart_policy_abi(facts)
    if "# TERMINAL_PAINT_ABI:" in source:
        validate_terminal_paint_abi(facts)
    # Source spellings select compiler facts, never a second mangling recipe.
    from bootstrap_frontend import abi_function_symbol

    def symbol(match):
        value = abi_function_symbol(facts, match[1])
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", value):
            raise ValueError("Unsupported compiler symbol in private bridge")
        return value

    return re.sub(r"@([A-Za-z_][A-Za-z_0-9:]*)@", symbol, source)


def compose_object_bridge(path, bridges, facts, assembler="as", linker="ld", objcopy="objcopy", *, compiler=None):
    """Keep native adapters separate and preserve private source bindings."""
    from bootstrap_frontend import abi_function_symbol

    sources = [bridge.read_text() for bridge in bridges]
    # Rendering validates the copied layouts before any symbol is exposed.
    assembly = "\n".join(render_bridge(source, facts) for source in sources)
    # Text bridges share the source emitter's note. A standalone wrapper object
    # needs its own non-executable PROGBITS note without changing that text route.
    assembly += '\n.section .note.GNU-stack,"",@progbits\n'
    selected = sorted(
        {
            abi_function_symbol(facts, name)
            for source in sources
            for name in re.findall(r"@([A-Za-z_][A-Za-z_0-9:]*)@", source)
        }
    )
    compose_private_object(path, assembly, selected, assembler, linker, objcopy, compiler=compiler)


def compose_private_object(path, assembly, selected, assembler="as", linker="ld", objcopy="objcopy", *, compiler=None):
    """Compose rendered native wrappers with their fact-selected LOCAL targets."""
    if not selected or len(set(selected)) != len(selected):
        raise ValueError("Object bridge requires unique fact-selected private entries")
    if any(not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name) for name in selected):
        raise ValueError("Unsupported compiler symbol in private bridge")

    def symbol_types(object_path):
        result = subprocess.run(
            ["nm", "-P", "--defined-only", str(object_path)], check=True, capture_output=True, text=True
        )
        return {fields[0]: fields[1] for fields in map(str.split, result.stdout.splitlines()) if len(fields) >= 2}

    with tempfile.TemporaryDirectory(prefix=".aurora-bridge-", dir=path.parent) as directory:
        work = Path(directory)
        source_object = work / "source.o"
        bridge_source = work / "bridge.s"
        bridge_object = work / "bridge.o"
        combined = work / "combined.o"
        bridge_source.write_text(assembly)
        subprocess.run([assembler, "--64", str(bridge_source), "-o", str(bridge_object)], check=True)
        if compiler is not None:
            names = work / "selected"
            names.write_text("".join(name + "\n" for name in selected))
            # The compiler admits LOCAL targets and writes a distinct artifact;
            # its CLI rejects all input aliases, including the pending source.
            subprocess.run(
                [
                    str(compiler),
                    "--compose-private-object",
                    str(path),
                    str(bridge_object),
                    str(names),
                    "-o",
                    str(combined),
                ],
                check=True,
            )
            combined.replace(path)
            return
        before = symbol_types(path)
        if any(before.get(name) != "t" for name in selected):
            raise ValueError("Object bridge targets must be defined LOCAL text symbols")
        subprocess.run(
            [objcopy, *["--globalize-symbol=" + name for name in selected], str(path), str(source_object)], check=True
        )
        subprocess.run(
            [
                linker,
                "-m",
                "elf_x86_64",
                "-r",
                "--build-id=none",
                str(source_object),
                str(bridge_object),
                "-o",
                str(combined),
            ],
            check=True,
        )
        subprocess.run([objcopy, *["--localize-symbol=" + name for name in selected], str(combined)], check=True)
        after = symbol_types(combined)
        if any(after.get(name) != "t" for name in selected):
            raise ValueError("Object bridge did not restore private source bindings")
        combined.replace(path)


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
    parser.add_argument("--emit-object", action="store_true")
    parser.add_argument("--compose-private-object", action="store_true")
    parser.add_argument("--assembler", default="as")
    parser.add_argument("--linker", default="ld")
    parser.add_argument("--objcopy", default="objcopy")
    args = parser.parse_args()
    if args.bridge and not args.abi_facts:
        parser.error("--bridge requires --abi-facts")
    if args.compose_private_object and not (args.emit_object and args.bridge):
        parser.error("--compose-private-object requires --emit-object and --bridge")
    inputs = dependencies(args.source, args.module_root)
    inputs += [bridge.absolute() for bridge in args.bridge]
    inputs += [Path(__file__).with_name("bootstrap_frontend.py"), Path(__file__).with_name("frontend_bridge.py")]
    temporary = args.output.with_suffix(".pending.o" if args.emit_object else ".pending.s")
    command = [str(args.compiler.resolve(strict=True))]
    if args.emit_object:
        command.append("--emit-object")
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
        validate_selected_source_abi(args.source, facts)
        if args.emit_object and args.bridge:
            compose_object_bridge(
                temporary,
                args.bridge,
                facts,
                args.assembler,
                args.linker,
                args.objcopy,
                compiler=args.compiler.resolve(strict=True) if args.compose_private_object else None,
            )
        elif not args.emit_object:
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
