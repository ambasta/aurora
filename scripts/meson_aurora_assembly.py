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


def validate_native_abi(facts, source):
    """Admit every marked native contract once for the complete bridge artifact."""
    from bootstrap_frontend import abi_declaration, normalize_function_abi

    def shape(source):
        if source in ("i64", "u64", "u8", "bool"):
            return dict(bytes=8, kind=source)
        if source == "span":
            return dict(bytes=56, kind="span")
        if source in ("builtin::CallSession", "builtin::ConsoleSession"):
            return dict(bytes=16, kind="service")
        if source == "builtin::ServeSession":
            return dict(bytes=16, kind="service", type_name=source)
        group = (
            "enums"
            if source
            in (
                "console::FileEvent",
                "console::ProgramEffect",
                "console::NamespaceOperation",
                "console::NamespaceInputAction",
                "console::NamespaceResponseKind",
                "kernel::MapVerdict",
                "kernel::GrantVerdict",
                "kernel::VolumeVerdict",
                "kernel::ElfVerdict",
                "kernel::LayoutVerdict",
                "kernel::TrapClass",
                "kernel::CallAction",
                "kernel::RunsVerdict",
            )
            else "records"
        )
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

    def enum(source, names):
        _, value = abi_declaration(facts, "enums", source)
        names = names.split()
        if value["cases"] != dict(zip(names, range(len(names)))):
            raise ValueError("Native enum encoding differs from compiler facts: " + source)

    if "# UART_POLICY_ABI:" in source:
        validate_uart_policy_abi(facts)
    if "# TERMINAL_PAINT_ABI:" in source:
        validate_terminal_paint_abi(facts)
    if "# PROGRAM_SESSION_ABI:" in source:
        _, state = abi_declaration(facts, "records", "console::ProgramSession")
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
        enum(
            "console::ProgramEffect",
            "invalid ready file_ready input note files upper read_note upper_note file peek wc crc unknown "
            "note_saved file_reply abort_file exited failed",
        )
        record(
            "console::ProgramSessionUpdate",
            56,
            [
                ("session", "console::ProgramSession", 0),
                ("effect", "console::ProgramEffect", 0),
                ("after_cr", "u64", 0),
                ("outcome", "u64", 0),
            ],
        )
        entry(
            "update_program_session", ["console::ProgramSession", "u64", "u64", "u64"], "console::ProgramSessionUpdate"
        )

    if "# NAMESPACE_OWNER_ABI:" in source:
        entry("aurora_user_main", ["builtin::ServeSession", "u64"], "u64")
    if "# NAMESPACE_CLIENT_ABI:" in source or "# NAMESPACE_CONSOLE_ABI:" in source:
        record("std::BinaryBuffer64", 64, [("elements", "u8", 64)], alignment=1)
        for name in ("console::FileName", "console::FileValue"):
            record(name, 72, [("bytes", "std::BinaryBuffer64", 0), ("length", "i64", 0)])
        record(
            "console::NamespaceCommand",
            152,
            [
                ("name", "console::FileName", 0),
                ("value", "console::FileValue", 0),
                ("operation", "console::NamespaceOperation", 0),
            ],
        )
        record(
            "console::NamespaceResult",
            88,
            [
                ("bytes", "u8", 64),
                ("count", "u64", 0),
                ("event", "console::FileEvent", 0),
                ("generation", "u64", 0),
            ],
        )
        for name, names in (
            ("console::NamespaceOperation", "read write"),
            ("console::FileEvent", "unknown written read removed listed missing invalid full reserved"),
        ):
            enum(name, names)
        if "# NAMESPACE_CLIENT_ABI:" in source:
            entry(
                "aurora_user_main",
                ["builtin::CallSession", "console::NamespaceCommand", "u64"],
                "console::NamespaceResult",
            )
        if "# NAMESPACE_CONSOLE_ABI:" in source:
            record(
                "console::NamespaceSubmission",
                168,
                [
                    ("command", "console::NamespaceCommand", 0),
                    ("action", "console::NamespaceInputAction", 0),
                    ("after_cr", "u64", 0),
                ],
            )
            record(
                "console::NamespaceResponse",
                176,
                [
                    ("name", "console::FileName", 0),
                    ("submitted_size", "u64", 0),
                    ("result", "console::NamespaceResult", 0),
                    ("kind", "console::NamespaceResponseKind", 0),
                ],
            )
            for name, names in (
                ("console::NamespaceInputAction", "command requested_exit output_failure"),
                (
                    "console::NamespaceResponseKind",
                    "ready completed aborted read_failed committed_caller_failed "
                    "indeterminate_reset reset unavailable limit",
                ),
            ):
                enum(name, names)
            entry("read_namespace_input", ["builtin::ConsoleSession", "bool"], "console::NamespaceSubmission")
            entry("present_namespace_response", ["builtin::ConsoleSession", "console::NamespaceResponse"], "bool")

    if "# PROGRAM_APPEND_CLIENT_ABI:" in source or "# PROGRAM_APPEND_SERVICE_ABI:" in source:
        record("kernel::NoteRead64", 72, [("bytes", "u8", 64), ("length", "i64", 0)])
    if "# PROGRAM_APPEND_CLIENT_ABI:" in source:
        entry("aurora_user_main", ["i64", "i64", "i64"], "i64")
        entry("append_candidate", ["builtin::CallSession", "i64"], "kernel::NoteRead64")
    if "# PROGRAM_APPEND_SERVICE_ABI:" in source:
        entry("aurora_user_main", ["i64", "i64", "i64", "kernel::NoteRead64", "kernel::NoteRead64"], "i64")
        entry(
            "append_producer",
            ["builtin::ServeSession", "i64", "i64", "i64", "kernel::NoteRead64", "kernel::NoteRead64"],
            "i64",
        )
    if "# PROGRAM_FILES_ABI:" in source:
        record("std::BinaryBuffer64", 64, [("elements", "u8", 64)], alignment=1)
        for name in ("console::FileName", "console::FileValue"):
            record(name, 72, [("bytes", "std::BinaryBuffer64", 0), ("length", "i64", 0)])
        record("console::FileNamespace", 264, [("records", "std::BinaryBuffer64", 4), ("occupied", "u64", 0)])
        record("console::SessionFiles", 264, [("namespace_files", "console::FileNamespace", 0)])
        record("console::ProtectedFiles", 272, [("files", "console::FileNamespace", 0), ("revision", "u64", 0)])
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
        record(
            "console::FileReply", 80, [("bytes", "u8", 64), ("length", "i64", 0), ("event", "console::FileEvent", 0)]
        )
        enum("console::FileEvent", "unknown written read removed listed missing invalid full reserved")
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
        if "@replace_files@" in source:
            record("FileMutation", 352, [("files", "console::ProtectedFiles", 0), ("reply", "console::FileReply", 0)])
            entry(
                "replace_files",
                ["console::ProtectedFiles", "console::FileSelection", "std::BinaryBuffer64", "i64"],
                "FileMutation",
            )

    if "# PROCESS_POLICY_ABI:" in source:
        for name, names in (
            ("kernel::MapVerdict", "valid version stride length alignment range overlap"),
            ("kernel::GrantVerdict", "granted map bounds arena uncovered"),
            (
                "kernel::VolumeVerdict",
                "valid truncated limit magic version header count layout reserved checksum padding flags name path "
                "order data nesting",
            ),
        ):
            enum(name, names)
        record("kernel::FrameRange", 24, [("_status", "u64", 0), ("_first", "u64", 0), ("_pages", "u64", 0)])
        record("kernel::VolumeEntry", 24, [("_found", "u64", 0), ("_offset", "u64", 0), ("_size", "u64", 0)])
        entry("process_map_admit", ["span", "u64", "u64"], "kernel::MapVerdict")
        entry("process_volume_grant", ["span", "u64", "u64", "u64", "u64"], "kernel::GrantVerdict")
        entry("process_frame_range", ["span", "u64", "u64", "u64", "u64", "u64"], "kernel::FrameRange")
        entry("process_volume_admit", ["span"], "kernel::VolumeVerdict")
        entry("process_volume_find", ["span", "span"], "u64")
        entry("process_volume_entry", ["span", "u64"], "kernel::VolumeEntry")
        entry("process_base64_group", ["span", "u64"], "u64")
        entry("aurora_kernel_frame_transition", ["u64", "u64", "u64", "u64", "u64"], "u64")
        for name, names in (
            (
                "kernel::ElfVerdict",
                "valid truncated magic format type machine header segment interpreter dynamic tls stack permissions "
                "writable_executable alignment file memory address overlap entry empty",
            ),
            ("kernel::LayoutVerdict", "valid image kernel arguments"),
            (
                "kernel::TrapClass",
                "kernel timer call system_call invalid_opcode stack_guard page_fault protection divide debug "
                "breakpoint overflow bound fpu alignment simd",
            ),
            ("kernel::CallAction", "invalid exit print read"),
            (
                "kernel::RunsVerdict",
                "valid truncated magic version count ticks path arguments flags padding trailing",
            ),
        ):
            enum(name, names)
        region = ("kind", "first", "pages", "flags", "vaddr", "offset", "bytes")
        record("kernel::ProcessRegion", 56, [(name, "u64", 0) for name in region])
        trap = ("vector", "error", "rip", "cs", "flags", "rsp", "ss", "cr2", "opcode")
        record("kernel::ProcessTrap", 72, [(name, "u64", 0) for name in trap])
        record(
            "kernel::KernelCall",
            24,
            [("_action", "kernel::CallAction", 0), ("_value", "u64", 0), ("_length", "u64", 0)],
        )
        run = ("found", "ticks", "flags", "path", "path_bytes", "arguments", "argument_bytes")
        record("kernel::RunEntry", 56, [(name, "u64", 0) for name in run])
        entry("process_elf_admit", ["span"], "kernel::ElfVerdict")
        entry("process_layout", ["span", "u64", "u64", "u64"], "kernel::LayoutVerdict")
        entry("process_region", ["span", "u64", "u64"], "kernel::ProcessRegion")
        entry("process_elf_entry", ["span"], "u64")
        entry("process_trap", ["kernel::ProcessTrap"], "kernel::TrapClass")
        entry("process_call", ["u64", "u64", "u64", "u64"], "kernel::KernelCall")
        entry("process_runs_admit", ["span"], "kernel::RunsVerdict")
        entry("process_run", ["span", "u64"], "kernel::RunEntry")


def render_bridge(source, facts):
    validate_native_abi(facts, source)
    # Source spellings select compiler facts, never a second mangling recipe.
    from bootstrap_frontend import abi_function_symbol

    def symbol(match):
        value = abi_function_symbol(facts, match[1])
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", value):
            raise ValueError("Unsupported compiler symbol in private bridge")
        return value

    return re.sub(r"@([A-Za-z_][A-Za-z_0-9:]*)@", symbol, source)


def compose_object_bridge(path, bridges, facts, assembler="as", *, compiler):
    """Keep native adapters separate and preserve private source bindings."""
    from bootstrap_frontend import abi_function_symbol

    sources = [bridge.read_text() for bridge in bridges]
    # Rendering validates the copied layouts before any symbol is exposed.
    assembly = render_bridge("\n".join(sources), facts)
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
    compose_private_object(path, assembly, selected, assembler, compiler=compiler)


def compose_private_object(path, assembly, selected, assembler="as", *, compiler):
    """Compose rendered native wrappers with their fact-selected LOCAL targets."""
    if not selected or len(set(selected)) != len(selected):
        raise ValueError("Object bridge requires unique fact-selected private entries")
    if any(not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name) for name in selected):
        raise ValueError("Unsupported compiler symbol in private bridge")

    with tempfile.TemporaryDirectory(prefix=".aurora-bridge-", dir=path.parent) as directory:
        work = Path(directory)
        bridge_source = work / "bridge.s"
        bridge_object = work / "bridge.o"
        combined = work / "combined.o"
        names = work / "selected"
        bridge_source.write_text(assembly)
        names.write_text("".join(name + "\n" for name in selected))
        # The composer admits only the plain .text/.data/.bss/.note.GNU-stack layout;
        # some distributions' as adds .note.gnu.property by default.
        subprocess.run(
            [assembler, "--64", "-mx86-used-note=no", str(bridge_source), "-o", str(bridge_object)], check=True
        )
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
    parser.add_argument("--assembler", default="as")
    args = parser.parse_args()
    if args.bridge and not args.abi_facts:
        parser.error("--bridge requires --abi-facts")
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
        if args.emit_object and args.bridge:
            compose_object_bridge(
                temporary,
                args.bridge,
                facts,
                args.assembler,
                compiler=args.compiler.resolve(strict=True),
            )
        elif args.bridge and not args.emit_object:
            with temporary.open("a") as output:
                output.write("\n" + render_bridge("\n".join(bridge.read_text() for bridge in args.bridge), facts))
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
