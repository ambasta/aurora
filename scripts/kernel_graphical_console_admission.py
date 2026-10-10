#!/usr/bin/env python3
"""Bounded graphical Console image, stack and capture-structure admission.

Current build provenance binds measured artifacts, not a historical host binary.
These checks do not prove arbitrary machine safety or capture behavior; hosted
and guest behavior gates and independent review remain separate requirements.
"""

from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/uefi"
RECEIPT = BUILD / "graphical-console-admission.json"
MODES = ("graphical-console", "graphical-console-capture")
ENTRY = "__au_v_m1_24kernel_graphical_console_n0__d17graphical_console"
REFLECTION_HELPERS = frozenset(
    ("aurora_reflect_size", "aurora_reflect_field_count")
    + tuple(f"__au_reflect_s{module}_{field}" for module in range(1, 7) for field in ("size", "field_count"))
)
CPP_ENTRY = "_ZN6aurora4uefi21run_graphical_consoleEmRKNS0_5BytesE"
BRIDGE = "__au_runtime_graphical_entry"
VALUE_BRIDGE = "__au_runtime_graphical_value"
VALUE_ENTRY = "aurora_kernel_value"
TOOLS = ("as", "ld", "objcopy", "objdump", "nm", "readelf", "c++filt", "python3")
HOST_IMPORTS = frozenset(("__au_runtime_console_next", "__au_runtime_console_put", "__au_runtime_display_pixel"))
COMMON_CPP_OBJECTS = ("payload", "acpi", "pci", "runtime")
CPP_OBJECTS = COMMON_CPP_OBJECTS + ("graphical-console",)
COMMON_ASSEMBLY_OBJECTS = ("payload-entry", "language", "memory")
ASSEMBLY_OBJECTS = ("payload-entry", "console-entry", "language", "memory")
BASE_FLAGS = tuple(
    (
        "-std=c++23 -O2 -fstack-usage -fcallgraph-info=su -Wall -Wextra -Werror -ffreestanding "
        "-fcf-protection=none -mstringop-strategy=libcall "
        "-fno-exceptions -fno-rtti -fno-stack-protector -fno-asynchronous-unwind-tables "
        "-fno-unwind-tables -mno-red-zone -mgeneral-regs-only -fno-tree-loop-distribute-patterns"
    ).split()
)
PROFILE_FLAGS = ("-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_GRAPHICAL_CONSOLE", "-DAURORA_UEFI_GRAPHICAL_FIXTURE")
TU_FLAGS = {
    "payload/acpi/pci/graphical-console": ["-fpie", "-fvisibility=hidden"],
    "runtime": ["-fpie", "-fvisibility=hidden", "-Ibuild/uefi"],
    "loader": ["-fpie", "-maccumulate-outgoing-args", "-Ibuild/uefi"],
}


def need(value, reason):
    if not value:
        raise ValueError(reason)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


common = load("graphical_common", ROOT / "scripts/kernel_program_console_admission.py")
console = load("graphical_console_controls", ROOT / "scripts/kernel_console_service_admission.py")
digest = common.digest
verify_irq_body = console.verify_irq_body
verify_irq_reachability = console.verify_irq_reachability
verify_stack_budgets = console.verify_stack_budgets
verify_reflection_body = common.verify_reflection_body


BUILD_KEYS = {
    "schema",
    "mode",
    "flags",
    "source_sha256",
    "compiler",
    "cxx",
    "tools",
    "pe_linker",
    "translation_unit_flags",
    "objects",
}


def configure_paths(build_dir, source_root=None):
    global ROOT, BUILD, RECEIPT
    common.configure_paths(build_dir, source_root or ROOT)
    ROOT, BUILD = common.ROOT, common.BUILD
    RECEIPT = BUILD / "graphical-console-admission.json"
    console.configure_paths(BUILD, ROOT)
    for flags in TU_FLAGS.values():
        flags[:] = [common.include_directory() if flag.startswith("-I") else flag for flag in flags]


def source_files():
    return sorted(
        set(common.source_files())
        | {
            ROOT / "compiler/Makefile",
            ROOT / "meson.build",
            ROOT / "tests/meson.build",
            ROOT / "tests/compiler-test-inventory.json",
        }
    )


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result

    return json.loads(
        path.read_text(),
        object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Non-finite JSON: " + value)),
    )


CAPTURE_ONLY_TOKENS = tuple(
    text.encode()
    for text in (
        "graphical_capture",
        "capture_scenario",
        "capture_gate",
        "pixel_attempts",
        "AURORA_GRAPHICAL_CAPTURE_GATE:",
        "AURORA_GRAPHICAL_CAPTURE_RELEASED",
        "AURORA_GRAPHICAL_PRE_SAMPLE:",
        "capture initial state",
        "capture UART status",
        "capture selector",
        "capture release deadline",
        "pixel attempt counter overflow",
        "cross-console",
        "cross-display",
        "stale-console",
        "stale-display",
        "first-pixel-error",
        "interior-pixel-error",
    )
)
CAPTURE_ARTIFACTS = ("payload.elf", "payload.bin", "esp/EFI/BOOT/BOOTX64.EFI") + tuple(
    name + ".o"
    for name in CPP_OBJECTS
    + ASSEMBLY_OBJECTS
    + ("loader", "embed", "transition", "loader-pe", "embed-pe", "transition-pe", "memory-pe")
)


def capture_artifact_evidence(mode, artifacts):
    """Presence/ownership is necessary; it cannot establish capture semantics."""
    need(mode in MODES, "Unknown graphical profile")
    need(set(artifacts) == set(CAPTURE_ARTIFACTS), "Changed fixture artifact inventory")
    embedded = {"payload.elf", "payload.bin", "esp/EFI/BOOT/BOOTX64.EFI", "embed.o", "embed-pe.o"}
    found, hashes = {}, {}
    for name, fields in artifacts.items():
        need(set(fields) == {"contents", "symbols", "relocations"}, "Changed fixture artifact evidence fields")
        hashes[name] = {}
        for field, value in fields.items():
            need(type(value) is bytes, "Fixture artifact evidence must retain original bytes")
            hashes[name][field] = hashlib.sha256(value).hexdigest()
            tokens = [token.decode() for token in CAPTURE_ONLY_TOKENS if token in value]
            if tokens:
                need(
                    mode == MODES[1], "Capture fixture leaked into production: " + name + ":" + field + ": " + tokens[0]
                )
                need(
                    name == "graphical-console.o" or name in embedded,
                    "Capture fixture has foreign ownership: " + name + ":" + field,
                )
                found[name + ":" + field] = tokens
    if mode == MODES[1]:
        owner = artifacts["graphical-console.o"]
        need(
            all(token in owner["symbols"] for token in (b"capture_scenario", b"pixel_attempts"))
            and b"AURORA_GRAPHICAL_CAPTURE_RELEASED: selector=" in owner["contents"],
            "Missing capture fixture state or exact release diagnostic",
        )
    return dict(
        mode=mode,
        status="structure-only-behavior-qualification-pending" if mode == MODES[1] else "fixture-absent",
        fixture_tokens=found,
        artifact_sha256=hashes,
    )


CAPTURE_STATE_FIELDS = {
    "capture_scenario": 1,
    "pixel_attempts": 8,
    "consumer_entries": 8,
    "sample_calls": 8,
    "output_attempts": 8,
    "completed_samples": 8,
    "stores": 8,
    "wakes": 8,
    "active_operation": 4,
    "console_grant": 24,
    "console_generation": 8,
    "display_grant": 48,
    "display_generation": 8,
    "entry_active": 1,
}
CAPTURE_AUTHORITY_SYMBOLS = {
    "console_grant": (
        "_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE6grant_E"
    ),
    "console_generation": (
        "_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE11generation_E"
    ),
    "display_grant": (
        "_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE6grant_E"
    ),
    "display_generation": (
        "_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE11generation_E"
    ),
    "entry_active": (
        "_ZN6aurora9graphical5EntryINS_7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportE"
        "NS5_15ServicePlatformEEENS_7display7SessionINS5_16DisplayTransportES7_EES7_E7active_E"
    ),
}
CAPTURE_STRUCTURE_SCHEMA = "aurora-graphical-capture-structure-v1"


def capture_structure_evidence(linked):
    """Check fixture storage only; no selector/authority/pixel behavior proof.

    Object binding, .su/.ci frames, linked control flow, private ABI and stack
    budgets are checked by the surrounding admission. Capture behavior belongs
    to the hosted policy/session tests and actual guest capture/failure gates.
    """

    def matches(field):
        # GCC14/16 differ only in the local-linkage spelling here. Addresses and
        # section indexes are measured, never tied to one compiler build.
        if field in CAPTURE_AUTHORITY_SYMBOLS:
            return [row for row in linked.symbols if row.name == CAPTURE_AUTHORITY_SYMBOLS[field]]
        pattern = rf"_ZN6aurora4uefi12_GLOBAL__N_1L?{len(field)}{field}E"
        return [row for row in linked.symbols if re.fullmatch(pattern, row.name)]

    markers = matches("capture_scenario")
    if not markers:
        need(not matches("pixel_attempts"), "Capture counter without scenario owner")
        return None
    states = {}
    for field, size in CAPTURE_STATE_FIELDS.items():
        rows = matches(field)
        need(len(rows) == 1, "Missing or ambiguous capture state: " + field)
        row = rows[0]
        need(
            row.kind == 1 and row.size == size and 0 < row.section < len(linked.sections),
            "Invalid capture state shape: " + field,
        )
        section = linked.sections[row.section]
        need(
            section[1] == 8 and section[2] & 7 == 3,
            "Capture state must be writable, allocated, non-executable BSS: " + field,
        )
        need(
            section[3] <= row.address and row.address + size <= section[3] + section[5],
            "Capture state outside its BSS section: " + field,
        )
        need(row.address % min(size, 8) == 0, "Misaligned capture state: " + field)
        for other in states.values():
            need(
                row.address + size <= other["address"] or other["address"] + other["bytes"] <= row.address,
                "Overlapping capture state: " + field,
            )
        states[field] = dict(symbol=row.name, address=row.address, bytes=size, section=row.section)
    need(HOST_IMPORTS | {CPP_ENTRY} <= set(linked.functions), "Missing capture session/import owner")
    return dict(
        schema=CAPTURE_STRUCTURE_SCHEMA,
        status="structure-only",
        states=states,
        behavior_qualification="pending-hosted-and-guest-gates",
    )


def require_capture_structure(mode, evidence=None):
    need(mode in MODES, "Unknown graphical profile")
    if mode == MODES[0]:
        need(evidence is None, "Production cannot carry capture state")
        return
    need(
        type(evidence) is dict
        and set(evidence) == {"schema", "status", "states", "behavior_qualification"}
        and evidence["schema"] == CAPTURE_STRUCTURE_SCHEMA
        and evidence["status"] == "structure-only"
        and evidence["behavior_qualification"] == "pending-hosted-and-guest-gates"
        and type(evidence["states"]) is dict
        and set(evidence["states"]) == set(CAPTURE_STATE_FIELDS),
        "Missing current capture structure evidence; behavior qualification remains separate",
    )


def unreviewed_linked_function(symbol, original_code, payload, error):
    """Retain unknown emission as a precise blocker, never a neutral opcode."""
    reason = str(error)
    rows = [
        row
        for address, row in sorted(original_code.items())
        if symbol.address <= address < symbol.address + symbol.size
    ]
    if reason.startswith("Unknown instruction semantics: "):
        rows = [row for row in rows if row.op == reason.removeprefix("Unknown instruction semantics: ")]
    elif reason.startswith("Unbounded or unknown stack adjustment: "):
        rows = [row for row in rows if row.args == reason.removeprefix("Unbounded or unknown stack adjustment: ")]
    evidence = [
        dict(
            address=row.address,
            bytes=payload[row.address : row.address + row.size].hex(),
            operation=row.op,
            operands=row.args,
        )
        for row in rows
    ]
    return (
        symbol.name
        + ": "
        + reason
        + "; call/stack effect remains unproved; original linked instructions="
        + canonical(evidence)
    )


def verify_bridge_body(decoder, body, starts):
    need(
        len(body) == 6
        and [(r.op, r.args) for r in body[:3]] == [("push", "%rbp"), ("mov", "%rsp,%rbp"), ("mov", "%rdi,%r11")]
        and body[3].op == "call"
        and starts.get(decoder.target_of(body[3])) == ENTRY
        and [(r.op, r.args) for r in body[4:]] == [("leave", ""), ("ret", "")],
        "Changed private dual-grant bridge or graphical entry",
    )


def verify_value_bridge_body(decoder, body, starts):
    need(
        len(body) == 1 and body[0].op == "jmp" and starts.get(decoder.target_of(body[0])) == VALUE_ENTRY,
        "Changed value-only private bridge",
    )


def cpp_stack_functions(decoder, symbols, code, starts, payload, frames, edges):
    """Trust GCC frame/call facts; cross-check direct transfers, not C++ semantics.

    Retain the full frame at every call AND tail call. GCC does not account for
    the reviewed inline PUSHFQ/POP pair, so add eight bytes to its owner's bound.
    Compiler-generated stack adjustments, register choices and local CFG are
    trusted. Reviewed C++ inline assembly must remain stack-neutral except for
    these adjacent flag-save pairs: GCC metadata does not bound arbitrary asm.
    Generated Aurora and standalone assembly remain decoded.
    """
    need(all(a in frames and b in symbols for a, b in edges), "Unknown compiler caller or callee")
    pop_bytes = {
        "%" + name: bytes(([0x41] if index >= 8 else []) + [0x58 + index % 8])
        for index, name in enumerate("rax rcx rdx rbx rsp rbp rsi rdi r8 r9 r10 r11 r12 r13 r14 r15".split())
        if name != "rsp"
    }
    functions, direct = {}, set()
    for name, frame in frames.items():
        symbol = symbols[name]
        rows = [
            row for address, row in sorted(code.items()) if symbol.address <= address < symbol.address + symbol.size
        ]
        need(rows and rows[0].address == symbol.address, "Missing C++ function instructions")
        pairs, calls = [], []
        for row in rows:
            need(row.next <= symbol.address + symbol.size, "C++ instruction exceeds function")
            if row.op.startswith(("pushf", "popf")):
                pop = code.get(row.next)
                need(
                    row.op == "pushf"
                    and not row.args
                    and payload[row.address : row.next] == b"\x9c"
                    and pop is not None
                    and pop.op == "pop"
                    and pop.args in pop_bytes
                    and pop.next <= symbol.address + symbol.size
                    and payload[pop.address : pop.next] == pop_bytes[pop.args],
                    "Unsupported inline PUSHFQ/POP stack contract",
                )
                pairs.append(row.address)
            transfers = [
                token
                for token in (row.op + " " + row.args.split("<", 1)[0]).split()
                if re.fullmatch(r"(?:[bl]?call\w*|[bl]?jmp\w*|j\w+|loop\w*|l?ret\w*|iret\w*)", token)
            ]
            need(
                not transfers or (transfers == [row.op] and row.op in decoder.BRANCHES | {"call", "ret"}),
                "Unsupported C++ control-transfer spelling",
            )
            if row.op != "call" and row.op not in decoder.BRANCHES:
                continue
            target = decoder.target_of(row)  # Supported call/jump targets must resolve directly.
            need(target in code, "C++ transfer to non-instruction")
            if row.op != "call" and symbol.address <= target < symbol.address + symbol.size:
                continue
            need(target in starts, "C++ transfer lacks exact function entry")
            direct.add((name, starts[target]))
            calls.append(dict(address=row.address, target=starts[target], kind="call" if row.op == "call" else "tail"))
        bound = frame + (8 if pairs else 0)
        for call in calls:
            call["live_bytes"] = bound
        functions[name] = dict(
            local_peak=bound,
            calls=calls,
            returns=sum(row.op == "ret" for row in rows),
            compiler_frame_bytes=frame,
            inline_stack_bytes=bound - frame,
            inline_pushfq_sites=pairs,
            basis="GCC .su/.ci; full frame retained at calls and tails; direct-transfer cross-check",
        )
    need(direct == edges, "Compiler/linked C++ call edges disagree")
    return functions


def verify_inventory(linked_names, frames, language_names, memory_names):
    fixed = {
        "uefi_payload_entry",
        "uefi_payload_fault",
        "uefi_payload_page_fault",
        "fault_common",
        "uefi_console_interrupt",
    }
    need(
        set(linked_names) == set(frames) | set(language_names) | set(memory_names) | fixed,
        "Unaccounted combined linked function/frame inventory",
    )
    need({ENTRY, BRIDGE} <= set(language_names), "Missing exact paired language entry/bridge")
    need(
        REFLECTION_HELPERS <= set(language_names)
        and {name for name in linked_names if name.startswith(("aurora_reflect_", "__au_reflect_"))}
        == REFLECTION_HELPERS
        and not REFLECTION_HELPERS.intersection(set(frames) | set(memory_names)),
        "Reflection helpers must belong only to generated language",
    )
    runtime = {name for name in linked_names if name.startswith("__au_runtime_")}
    need(runtime == HOST_IMPORTS | {BRIDGE, VALUE_BRIDGE}, "Unexpected combined runtime authority/import inventory")
    need(
        not any(name.startswith(("uefi_runtime_", "aurora_user_", "aurora_kernel_budget_")) for name in linked_names),
        "Unexpected protected runtime or budget fixture",
    )


def verify_wait_closure(code, named, functions, language_functions, payload, linked_functions):
    begin, end = (named[key].address for key in ("uefi_console_poll_begin", "uefi_console_poll_end"))
    need(
        0 < begin < end <= len(payload) and payload[begin:end] == bytes.fromhex("fbf4fa"),
        "Changed exact timer wait interval",
    )
    need(
        [row.address for row in code.values() if row.op == "sti"] == [begin],
        "Interrupt enable outside the sole admitted wait",
    )
    need(
        all(address in code for address in (begin, begin + 1, begin + 2))
        and [(code[address].op, code[address].args, code[address].size) for address in (begin, begin + 1, begin + 2)]
        == [("sti", "", 1), ("hlt", "", 1), ("cli", "", 1)],
        "Wait decode/bytes mismatch",
    )
    owners = [
        name
        for name, symbol in linked_functions.items()
        if symbol.address <= begin < end <= symbol.address + symbol.size
    ]
    need(len(owners) == 1 and "wait_for_sample" in owners[0], "Ambiguous or replaced wait owner")
    reachable = verify_irq_reachability(functions, language_functions)
    return owners[0], reachable


def expected_language_functions():
    # Exact current source declarations, using compiler/modules.hpp's reviewed
    # private naming. Root scalar helpers retain leaf names in the sealed graph.
    def mangle(kind, scope, name, module="kernel_graphical_console"):
        def components(parts):
            return str(len(parts)) + "_" + "".join(str(len(part)) + part for part in parts)

        return (
            "__au_"
            + kind
            + "_m"
            + components(module.split("."))
            + "_n"
            + components(scope.split("::") if scope else [])
            + "_d"
            + str(len(name))
            + name
        )

    names = {
        BRIDGE,
        VALUE_BRIDGE,
        "aurora_kernel_value",
        "__au_f_m2_8graphics7font5x7_n1_8graphics_d10glyph_bits",
        "graphical_glyph_bits",
    } | REFLECTION_HELPERS
    names.update(mangle("v", "", name) for name in ("graphical_console", "draw_glyph", "draw_cell"))
    methods = {
        "Line64": ("finish", "clear_submission", "submission_size", "submission_byte", "reject", "consume"),
        "TextCells": (
            "initialize",
            "append",
            "erase",
            "response",
            "hide_cursor",
            "at",
            "cursor_at",
            "dirty",
            "commit",
            "finish_paint",
            "show_ready",
            "show_help",
            "show_status",
            "show_unknown",
            "show_rejected",
            "show_note",
            "show_files",
            "show_exit",
            "show_empty",
            "show_bounded",
        ),
    }
    for scope, items in methods.items():
        names.add(mangle("k", scope, scope))
        names.update(mangle("m", scope, name) for name in items)
    # Complete declaration closure of the shared note and its fixed byte storage.
    # This admits no additional runtime service, allocator or device authority.
    classes = {
        ("console.session_note", "console", "SessionNote"): ("size", "at", "submit"),
        ("console.session_files", "console", "FileReply"): ("status", "size", "at", "append", "text", "select"),
        ("console.session_files", "console", "SessionFiles"): ("commit", "submit"),
        ("std.binary", "std", "ByteReadResult"): ("status", "value_or"),
        ("std.binary_buffer", "std", "BinaryBuffer64"): (
            "size",
            "at",
            "starts_with",
            "read_u8",
            "write_u8",
            "write_le16",
            "write_be16",
            "write_le32",
            "write_be32",
            "write_le64",
            "write_be64",
        ),
    }
    classes.update({("std.bytes", "std", "Bytes" + str(n)): ("at", "set") for n in (2, 4, 8)})
    classes.update({("std.bytes", "std", "Encode" + str(n) + "Result"): ("status", "bytes_or_zero") for n in (16, 32)})
    for (module, namespace, name), items in classes.items():
        scope = namespace + "::" + name
        names.add(mangle("k", scope, name, module))
        names.update(mangle("m", scope, item, module) for item in items)
    names.update(mangle("v", "std", name, "std.bytes") for name in ("starts_with", "equal"))
    for bits in (16, 32, 64):
        for order in ("le", "be"):
            names.add(mangle("v", "std", "read_" + order + str(bits), "std.binary"))
            names.add(mangle("v", "std", "encode_" + order + str(bits), "std.bytes"))
            names.add(mangle("v", "std", "decode_" + order + str(bits), "std.bytes"))
    return names


def verify_language_object(language):
    imports = {row.name for row in language.symbols if row.name and row.section == 0}
    need(
        imports == {"__au_runtime_console_next", "__au_runtime_display_pixel"},
        "Unexpected generated language import inventory",
    )
    need(
        set(language.functions) == expected_language_functions(),
        "Unexpected generated language module/function inventory",
    )
    rows = subprocess.check_output(["readelf", "-sW", language.path], text=True).splitlines()
    bindings = {}
    for line in rows:
        fields = line.split()
        if len(fields) == 8 and fields[3] == "FUNC" and fields[6] != "UND":
            need(fields[7] not in bindings, "Duplicate generated ELF function")
            bindings[fields[7]] = (fields[4], fields[5])
    need(set(bindings) == set(language.functions), "Generated ELF binding inventory mismatch")
    for name, binding in bindings.items():
        need(
            binding
            == (
                ("GLOBAL", "HIDDEN")
                if name in (BRIDGE, VALUE_BRIDGE)
                else ("GLOBAL", "DEFAULT")
                if name in REFLECTION_HELPERS
                else ("LOCAL", "DEFAULT")
            ),
            "Generated function escaped private ELF binding: " + name,
        )
    return sorted(imports)


def verify_generated_divisions(decoder, functions, code, payload):
    owners = console.SESSION_FILE_DIVISIONS | {
        "__au_v_m1_24kernel_graphical_console_n0__d9draw_cell": 2,
    }
    return console.verify_generated_divisions(decoder, functions, code, payload, owners)


def verify_private_abi(decoder, linked, code, starts, language_names, functions):
    def body(name):
        symbol = linked.functions[name]
        return [
            row for address, row in sorted(code.items()) if symbol.address <= address < symbol.address + symbol.size
        ]

    value_body = body(VALUE_BRIDGE)
    verify_value_bridge_body(decoder, value_body, starts)
    entry = body(ENTRY)
    need(
        [(row.op, row.args) for row in entry[:2]] == [("push", "%rbp"), ("mov", "%rsp,%rbp")],
        "Changed paired entry frame",
    )
    need(
        len(entry) > 5 and entry[2].op == "sub" and re.fullmatch(r"\$(?:0x[0-9a-f]+|[0-9]+),%rsp", entry[2].args),
        "Missing paired entry allocation",
    )
    allocated = int(entry[2].args.split(",")[0][1:], 0)
    need(allocated > 0 and allocated % 16 == 0, "Unaligned paired frame allocation")
    # The retained compiler output touches the allocated stack before saving
    # R11. Require its exact qword, zero-immediate, top-of-frame form; do not
    # skip arbitrary instructions or make the touch optional.
    need((entry[3].op, entry[3].args) == ("orq", "$0x0,(%rsp)"), "Missing or changed paired entry stack touch")
    saved = re.fullmatch(r"%r11,(-0x[0-9a-f]+\(%rbp\))", entry[4].args)
    need(entry[4].op == "mov" and saved, "Missing private record save")
    # BindServiceParameter emits one reload then two qword copy pairs. The
    # trailing width/height scalars each reload the same private record.
    cursor, slots, copies = 5, [], []
    for group in ((0, 8), (16, 24), (32,), (40,)):
        row = entry[cursor]
        need((row.op, row.args) == ("mov", saved[1] + ",%r11"), "Changed record reload")
        cursor += 1
        for offset in group:
            read, write = entry[cursor : cursor + 2]
            address = ("" if offset == 0 else hex(offset)) + "(%r11),%rax"
            need((read.op, read.args) == ("mov", address), "Wrong paired record qword/width/order")
            slot = re.fullmatch(r"%rax,(-0x[0-9a-f]+\(%rbp\))", write.args)
            need(
                write.op == "mov" and slot and slot[1] != saved[1] and slot[1] not in slots,
                "Aliased or missing paired parameter slot",
            )
            slots.append(slot[1])
            copies.append(dict(offset=offset, destination=slot[1], address=read.address))
            cursor += 2
    offsets = [int(slot.split("(")[0], 16) for slot in [saved[1]] + slots]
    need(
        all(-allocated <= offset <= -8 and offset % 8 == 0 for offset in offsets) and len(set(offsets)) == 7,
        "Overlapping, unaligned or unallocated paired record slots",
    )
    need(
        offsets[2] == offsets[1] + 8 and offsets[4] == offsets[3] + 8,
        "Service grant/generation field adjacency changed",
    )
    pixel_sites = []
    for name in language_names:
        rows = body(name)
        for index, call in enumerate(rows):
            if call.op != "call" or starts.get(decoder.target_of(call)) != "__au_runtime_display_pixel":
                continue
            need(index >= 9 and index + 1 < len(rows), "Truncated pixel host ABI")
            before = rows[index - 9 : index]
            grant = re.fullmatch(r"(-0x[0-9a-f]+)\(%rbp\),%rdi", before[0].args)
            generation = re.fullmatch(r"(-0x[0-9a-f]+)\(%rbp\),%rsi", before[1].args)
            need(
                before[0].op == before[1].op == "mov"
                and grant
                and generation
                and int(generation[1], 16) == int(grant[1], 16) + 8,
                "Pixel grant/generation not distinct adjacent qwords",
            )
            need(
                len(rows) >= 3
                and [(r.op, r.args) for r in rows[:2]] == [("push", "%rbp"), ("mov", "%rsp,%rbp")]
                and rows[2].op == "sub"
                and re.fullmatch(r"\$(?:0x[0-9a-f]+|[0-9]+),%rsp", rows[2].args),
                "Pixel helper frame has unknown allocation",
            )
            pixel_frame = int(rows[2].args.split(",")[0][1:], 0)
            pixel_offsets = [int(grant[1], 16), int(generation[1], 16)]
            need(
                pixel_frame > 0
                and pixel_frame % 16 == 0
                and all(-pixel_frame <= offset <= -8 and offset % 8 == 0 for offset in pixel_offsets),
                "Pixel grant/generation slots are unaligned or outside helper frame",
            )
            need(
                [(r.op, r.args) for r in before[2:7]] == [("pop", r) for r in ("%r10", "%r9", "%r8", "%rcx", "%rdx")],
                "Pixel scalar ABI changed",
            )
            need(
                before[7].op == "sub"
                and before[7].args in ("$0x8,%rsp", "$0x10,%rsp")
                and (before[8].op, before[8].args) == ("mov", "%r10,(%rsp)")
                and (rows[index + 1].op, rows[index + 1].args) == ("add", before[7].args),
                "Pixel seventh argument or balanced outgoing stack changed",
            )
            sites = [row for row in functions[name]["calls"] if row["address"] == call.address]
            need(len(sites) == 1 and sites[0]["live_bytes"] % 16 == 0, "Misaligned pixel SysV host call")
            need(
                index + 3 < len(rows)
                and (rows[index + 2].op, rows[index + 2].args) == ("cmp", "$0x1,%rax")
                and rows[index + 3].op == "ja"
                and code[decoder.target_of(rows[index + 3])].op == "ud2",
                "Pixel completion validation changed",
            )
            pixel_sites.append(dict(function=name, address=call.address, outgoing=before[7].args))
    need(pixel_sites, "No concrete Display pixel host call")
    return dict(
        entry_qword_copies=copies, pixel_sites=pixel_sites, value_bridge=dict(symbol=VALUE_BRIDGE, entry=VALUE_ENTRY)
    )


def verify_retained_wait_paths(functions, owner):
    required = (BRIDGE, ENTRY, "__au_runtime_console_next")
    paths = []

    def visit(name, path):
        need(name not in path, "Unexpected wait-path call cycle")
        path = path + [name]
        if name == owner:
            need(
                all(item in path for item in required)
                and [path.index(item) for item in required] == sorted(path.index(item) for item in required),
                "Wait bypasses retained paired service or Console host call",
            )
            paths.append(path)
            return
        for call in functions[name]["calls"]:
            if call["target"] is not None:
                visit(call["target"], path)

    # Only traverse nodes that can reach the wait, avoiding unrelated scalar
    # call-chain multiplicity; every retained path remains covered.
    reaches = {owner}
    while True:
        larger = reaches | {
            name for name, body in functions.items() if any(row["target"] in reaches for row in body["calls"])
        }
        if larger == reaches:
            break
        reaches = larger
    narrowed = {
        name: dict(body, calls=[row for row in body["calls"] if row["target"] in reaches])
        for name, body in functions.items()
    }
    functions = narrowed
    visit("uefi_payload_entry", [])
    need(paths, "No retained wait path")
    return paths


# The compiler's .ci assembler symbol joins its complete .su source record.
# These exact authority symbols are inventory requirements, never name guesses.
SESSION_VALIDATORS = {
    "_ZN6aurora7"
    + space
    + "7SessionINS_4uefi12_GLOBAL__N_116"
    + transport
    + "ENS3_15ServicePlatformEE8validateEPKvmb": "kernel/" + space + "-session.hpp"
    for space, transport in (("console", "ServiceTransport"), ("display", "DisplayTransport"))
}


def verify_session_frames(frames, associations):
    for symbol, source in SESSION_VALIDATORS.items():
        need(symbol in frames and symbol in associations, "Missing distinct Session validator frame")
        need(
            len(associations[symbol]) == 1
            and type(frames[symbol]) is int
            and frames[symbol] > 0
            and associations[symbol][0].get("compiler_symbol") == symbol
            and associations[symbol][0].get("bytes") == frames[symbol]
            and associations[symbol][0]["object"] == "graphical-console.o"
            and (ROOT / associations[symbol][0]["source"]).resolve() == (ROOT / source).resolve(),
            "Session validator frame has foreign or duplicated ownership/source",
        )


def stack_evidence(directory):
    decoder = load("graphical_stack_decoder", ROOT / "tests/kernel-uefi-owned-bytes-stack.py")
    decoder.CPP_OBJECTS = CPP_OBJECTS
    decoder.configure_console("graphical")
    linked = decoder.Elf(directory / "payload.elf")
    need(linked.type == 2, "Expected linked executable payload")
    need(not subprocess.check_output(["nm", "-u", directory / "payload.elf"], text=True).strip(), "Unresolved payload")
    old_rows = decoder.stack_rows
    bounded = []

    def stack_rows(text):
        bounded.extend(line for line in text.splitlines() if line.endswith("\tdynamic,bounded"))
        return old_rows(
            text,
            allow_bounded=lambda signature: any(
                name in signature
                for name in (
                    "aurora::uefi::run_graphical_console(",
                    "FramebufferPayload::restore_graphical_fixture(",
                )
            ),
        )

    decoder.stack_rows = stack_rows
    compiler_edges = set()
    frames, associations = decoder.cpp_frames(directory, linked, edges=compiler_edges, source_root=ROOT)
    verify_session_frames(frames, associations)
    named = {row.name: row for row in linked.symbols if row.section}
    irq = named["uefi_console_interrupt"]
    irq_object = decoder.Elf(directory / "objects" / "console-entry.o")
    irq_symbols = [row for row in irq_object.symbols if row.name == irq.name]
    need(len(irq_symbols) == 1, "Ambiguous IRQ object symbol")
    original = irq_symbols[0]
    extent = irq_object.sections[original.section][5] - original.address
    linked.functions[irq.name] = decoder.Symbol(irq.name, irq.address, extent, irq.section, 2)
    starts = {symbol.address: name for name, symbol in linked.functions.items()}
    need(len(starts) == len(linked.functions), "Ambiguous linked function starts")
    code, disassembly = decoder.disassemble(directory / "payload.elf")
    original_code = dict(code)
    payload = (directory / "payload.bin").read_bytes()
    divisions = verify_generated_divisions(decoder, linked.functions, code, payload)
    body = lambda symbol: [r for a, r in sorted(code.items()) if symbol.address <= a < symbol.address + symbol.size]
    verify_irq_body(decoder, body(linked.functions[irq.name]), starts)
    language, memory = (decoder.Elf(directory / "objects" / (name + ".o")) for name in ("language", "memory"))
    for obj in (language, memory):
        for symbol in obj.functions.values():
            decoder.associate_object(linked, obj, symbol)
    assembly = [item for name in ASSEMBLY_OBJECTS for item in common.linked_assembly(decoder, linked, directory, name)]
    verify_inventory(linked.functions, frames, language.functions, memory.functions)
    language_imports = verify_language_object(language)
    reflection = []
    for name in sorted(REFLECTION_HELPERS):
        original = language.functions[name]
        need(
            not any(
                section == original.section
                and address < original.address + original.size
                and address + 4 > original.address
                for section, address, *_ in language.relocations
            ),
            "Reflection helper acquired a relocation",
        )
        reflection.append(
            verify_reflection_body(decoder, linked.functions[name], body(linked.functions[name]), payload)
        )
    decoder.NORETURN = frozenset(
        name
        for name in linked.functions
        if name == "uefi_payload_fail"
        or "4failE" in name
        or "21run_graphical_consoleE" in name
        or "23graphical_console_faultE" in name
    )
    functions = cpp_stack_functions(decoder, linked.functions, code, starts, payload, frames, compiler_edges)
    for name, symbol in linked.functions.items():
        if name == irq.name or name in frames:
            continue
        try:
            functions[name] = decoder.analyze_function(symbol, code, starts, fault=name == "fault_common")
        except ValueError as error:
            raise ValueError(unreviewed_linked_function(symbol, original_code, payload, error)) from error
    console.verify_noreturn(functions, decoder.NORETURN)
    verify_bridge_body(decoder, body(linked.functions[BRIDGE]), starts)
    private_abi = verify_private_abi(decoder, linked, code, starts, language.functions, functions)
    # Four local traversal slots replace the former recursive source contract.
    # Metadata-based C++ bounds admit no call cycles.
    for name in functions:
        common.graph_peak(functions, frames, name)
    normal = common.graph_peak(functions, frames, "uefi_payload_entry")
    session = common.graph_peak(functions, frames, ENTRY)
    fault = 48 + max(
        common.graph_peak(functions, frames, name)["peak"] for name in ("uefi_payload_fault", "uefi_payload_page_fault")
    )
    dispatch = common.graph_peak(functions, frames, "uefi_console_interrupt_dispatch")
    irq_peak = 176 + 15 + dispatch["peak"]
    owner, irq_reachable = verify_wait_closure(code, named, functions, language.functions, payload, linked.functions)
    need(owner not in irq_reachable, "IRQ reaches interruptible wait")
    retained_paths = verify_retained_wait_paths(functions, owner)
    waiting = common.graph_peak(functions, frames, "uefi_payload_entry", target=owner)
    need(
        {ENTRY, BRIDGE, "__au_runtime_console_next"} <= set(waiting["path"]),
        "Wait does not retain paired Aurora service and Console host call",
    )
    verify_stack_budgets(normal["peak"], waiting["peak"], irq_peak, fault)
    waiting["peak_with_interrupt"] = waiting["peak"] + irq_peak
    waiting["peak_with_interrupt_and_fault"] = waiting["peak"] + irq_peak + fault
    capture_fixture = capture_structure_evidence(linked)
    return dict(
        stack_bytes=16384,
        cap_bytes=15360,
        normal=normal,
        session=session,
        boot_fault=fault,
        irq_frame_bytes=176,
        irq_alignment_bytes=15,
        irq_fault_reserve_bytes=4096,
        irq_dispatch=dispatch,
        irq_peak=irq_peak,
        irq_reachable=irq_reachable,
        wait=waiting,
        bridge=dict(symbol=BRIDGE, entry=ENTRY, record_qwords=6),
        host_imports=sorted(HOST_IMPORTS),
        language_imports=language_imports,
        private_abi=private_abi,
        retained_wait_paths=retained_paths,
        reflection_helpers=reflection,
        generated_divisions=divisions,
        compiler_frames=associations,
        linked_functions=functions,
        assembly_objects=assembly,
        original_dynamic_bounded_rows=bounded,
        page_verifiers=dict(traversal_slots=4, recursion="rejected"),
        graphical_traversal=dict(
            stack="compiler-metadata-acyclic-call-graph",
            semantics="reviewed-C++-source-and-trusted-compilation; hosted-and-guest-gates-required",
        ),
        disassembly_sha256=hashlib.sha256(disassembly.encode()).hexdigest(),
        capture_fixture=capture_fixture,
    )


def build_files(mode="graphical-console"):
    need(mode in ("normal", *MODES), "Unknown staged profile")
    cpp = COMMON_CPP_OBJECTS if mode == "normal" else CPP_OBJECTS
    assembly = COMMON_ASSEMBLY_OBJECTS if mode == "normal" else ASSEMBLY_OBJECTS
    names = [
        "payload.ld",
        "payload.elf",
        "payload.bin",
        "esp/EFI/BOOT/BOOTX64.EFI",
        "uefi-payload.hpp",
        "language.s",
        "embed.S",
        "image-metadata.json",
    ]
    if mode != "normal":
        names += ["console-poll-metadata.json"]
    names += [name + ".o" for name in cpp + assembly + ("loader", "embed", "transition")]
    names += [name + suffix for name in cpp + ("loader",) for suffix in (".su", ".ci")]
    names += [name + "-pe.o" for name in ("loader", "memory", "embed", "transition")]
    return common.build_artifacts(names)


def expected_flags(mode):
    need(mode in MODES, "Unknown graphical profile")
    return list(BASE_FLAGS + PROFILE_FLAGS + (("-DAURORA_UEFI_GRAPHICAL_CAPTURE",) if mode == MODES[1] else ()))


def verify_inputs(record, mode):
    need(type(record) is dict, "Build record must be an object")
    need(set(record) in (BUILD_KEYS, BUILD_KEYS | {"output_sha256"}), "Unexpected build manifest keys")
    need(
        record["schema"] == "aurora-graphical-console-build-v1" and record["mode"] == mode,
        "Graphical build profile mismatch",
    )
    need(record["flags"] == expected_flags(mode), "Exact graphical compiler flags/order mismatch")
    need(
        record["translation_unit_flags"] == TU_FLAGS
        and record["objects"] == [str(path.relative_to(BUILD)) for path in build_files()],
        "Changed graphical translation/object inventory",
    )
    need(record["source_sha256"] == common.hashes(source_files()), "Graphical source changed since begin")
    need(type(record["tools"]) is dict and set(record["tools"]) == set(TOOLS), "Build tool inventory mismatch")
    for name, item in list(record["tools"].items()) + [
        (name, record[name]) for name in ("compiler", "cxx", "pe_linker")
    ]:
        need(
            type(item) is dict
            and set(item) == {"path", "sha256"}
            and type(item["path"]) is str
            and Path(item["path"]).is_absolute()
            and re.fullmatch(r"[0-9a-f]{64}", item["sha256"]),
            "Malformed executable identity",
        )
        need(digest(Path(item["path"])) == item["sha256"], "Build executable changed: " + name)
        if name in TOOLS:
            need(item == common.executable(name), "Tool resolution changed: " + name)


def begin(mode, compiler, cxx, flags, linker=None):
    # Invalidate before any fallible argument, source or executable validation.
    RECEIPT.unlink(missing_ok=True)
    (BUILD / "graphical-console-build.json").unlink(missing_ok=True)
    (BUILD / "graphical-console-build-start.json").unlink(missing_ok=True)
    need(compiler and cxx and flags == expected_flags(mode), "Missing exact graphical build controls")
    record = dict(
        schema="aurora-graphical-console-build-v1",
        mode=mode,
        flags=flags,
        source_sha256=common.hashes(source_files()),
        compiler=common.executable(compiler),
        cxx=common.executable(cxx),
        tools={name: common.executable(name) for name in TOOLS},
        pe_linker=common.executable(linker or "ld"),
        translation_unit_flags=TU_FLAGS,
        objects=[str(path.relative_to(BUILD)) for path in build_files()],
    )
    verify_inputs(record, mode)
    (BUILD / "graphical-console-build-start.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")


def end(mode):
    record = read_json(BUILD / "graphical-console-build-start.json")
    verify_inputs(record, mode)
    common.verify_object_exports(build_files())
    record["output_sha256"] = common.hashes(build_files())
    (BUILD / "graphical-console-build.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")


def provenance(mode):
    record = read_json(BUILD / "graphical-console-build.json")
    verify_inputs(record, mode)
    need(set(record) == BUILD_KEYS | {"output_sha256"}, "Incomplete build manifest")
    common.verify_object_exports(build_files())
    need(record["output_sha256"] == common.hashes(build_files()), "Combined build output changed")
    return record


def image_evidence(directory, mode):
    need(mode in MODES, "Unknown graphical profile")
    image = load("graphical_image_decoder", ROOT / "tests/kernel-uefi-image.py")
    binary = (directory / "payload.bin").read_bytes()
    elf = (directory / "payload.elf").read_bytes()
    pe = (directory / "esp/EFI/BOOT/BOOTX64.EFI").read_bytes()
    image.elf_validate(elf, binary)
    image.pe_validate(pe, binary)
    graphical_policy = image.graphical_image_policy(directory)
    objects = {}
    for name in CPP_OBJECTS + ASSEMBLY_OBJECTS:
        relocations = subprocess.check_output(["readelf", "-rW", directory / "objects" / (name + ".o")], text=True)
        kinds = set(re.findall(r"R_X86_64_\w+", relocations))
        need(kinds <= {"R_X86_64_PC32", "R_X86_64_PLT32"}, "Non-PIC combined object: " + name)
        need(name != "memory" or not kinds, "Memory primitive has helpers")
        objects[name] = sorted(kinds)
    names = common.symbols(directory / "payload.elf")
    poll = dict(
        wait_begin=names["uefi_console_poll_begin"],
        wait_end=names["uefi_console_poll_end"],
        text_end=names["__payload_text_end"],
        frame_bytes=176,
        interrupt=names["uefi_console_interrupt"],
        dispatch=names["uefi_console_interrupt_dispatch"],
        polling_count=1250000,
        uart_irq=0,
    )
    need(canonical(read_json(directory / "console-poll-metadata.json")) == canonical(poll), "Poll metadata drift")
    metadata = dict(
        pe_sha256=hashlib.sha256(pe).hexdigest(),
        payload_sha256=hashlib.sha256(binary).hexdigest(),
        payload_bytes=len(binary),
    )
    need(canonical(read_json(directory / "image-metadata.json")) == canonical(metadata), "Image metadata drift")
    fixture_artifacts = {}
    for name in CAPTURE_ARTIFACTS:
        path = directory / ("objects/" + name if name.endswith(".o") else name)
        symbolic = name.endswith((".o", ".elf"))
        fixture_artifacts[name] = dict(
            contents=path.read_bytes(),
            symbols=subprocess.check_output(["nm", "-a", path]) if symbolic else b"",
            relocations=subprocess.check_output(["objdump", "-r", path]) if symbolic else b"",
        )
    return dict(
        **metadata,
        elf_sha256=hashlib.sha256(elf).hexdigest(),
        object_relocations=objects,
        poll=poll,
        graphical_policy=graphical_policy,
        capture_fixture=capture_artifact_evidence(mode, fixture_artifacts),
    )


def emit(mode):
    RECEIPT.unlink(missing_ok=True)
    record = provenance(mode)
    result = dict(
        schema="aurora-graphical-console-admission-v6",
        status="requires-independent-review",
        mode=mode,
        clock="tcg-original-clock",
        build=record,
        image=image_evidence(BUILD, mode),
        stack=stack_evidence(BUILD),
    )
    require_capture_structure(mode, result["stack"].get("capture_fixture"))
    need(record == provenance(mode), "Build changed during admission")
    result["sha256"] = common.hashes(source_files() + build_files() + [BUILD / "graphical-console-build.json"])
    RECEIPT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("PASS: bounded image/stack/structure checks; independent review and hosted/guest behavior gates required")
    return result


def checked(mode):
    receipt = read_json(RECEIPT)
    need(type(receipt) is dict, "Receipt must be an object")
    need(
        set(receipt) == {"schema", "status", "mode", "clock", "build", "image", "stack", "sha256"},
        "Unexpected receipt keys",
    )
    need(
        receipt["schema"] == "aurora-graphical-console-admission-v6"
        and receipt["mode"] == mode
        and receipt["status"] == "requires-independent-review"
        and receipt["clock"] == "tcg-original-clock",
        "Unexpected graphical receipt/profile/status",
    )
    need(receipt["build"] == provenance(mode), "Admitted graphical build changed")
    need(
        receipt["sha256"] == common.hashes(source_files() + build_files() + [BUILD / "graphical-console-build.json"]),
        "Admission source/output inventory or bytes changed",
    )
    current_image, current_stack = image_evidence(BUILD, mode), stack_evidence(BUILD)
    need(
        canonical(receipt["image"]) == canonical(current_image)
        and canonical(receipt["stack"]) == canonical(current_stack),
        "Receipt image/stack evidence differs from fresh combined proof",
    )
    require_capture_structure(mode, current_stack.get("capture_fixture"))
    return receipt


def reviewed(mode):
    pin = os.environ.get("GRAPHICAL_CONSOLE_REVIEW_SHA256", "")
    need(
        re.fullmatch(r"[0-9a-f]{64}", pin) and RECEIPT.is_file() and digest(RECEIPT) == pin,
        "Independent GRAPHICAL_CONSOLE_REVIEW_SHA256 receipt pin required",
    )
    return checked(mode)


begin_build, end_build, verify = begin, end, checked


def main():
    parser = argparse.ArgumentParser()
    common.path_arguments(parser)
    parser.add_argument(
        "action",
        choices=(
            "begin",
            "end",
            "begin-build",
            "end-build",
            "emit",
            "verify",
            "checked",
            "reviewed",
            "diagnose",
        ),
    )
    parser.add_argument("--mode", required=True, choices=MODES)
    parser.add_argument("--compiler")
    parser.add_argument("--cxx")
    parser.add_argument("--linker")
    parser.add_argument("--flag", action="append", default=[])
    args = parser.parse_args()
    common.check_depfile_options(args)
    configure_paths(args.build_dir or args.source_root / "build/uefi", args.source_root)
    if args.action in ("begin", "begin-build"):
        begin(args.mode, args.compiler, args.cxx, args.flag, args.linker)
        common.write_build_depfile(args, "graphical-console-build-start.json")
    elif args.action in ("end", "end-build"):
        end(args.mode)
    elif args.action == "emit":
        emit(args.mode)
    elif args.action == "reviewed":
        reviewed(args.mode)
        print("Verified externally pinned exact combined evidence.")
    elif args.action == "diagnose":
        print(json.dumps(stack_evidence(BUILD), indent=2, sort_keys=True))
    else:
        checked(args.mode)
        print("Verified current combined receipt identity; independent qualification not claimed.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        raise SystemExit("FAIL: graphical Console admission: " + str(error)) from error
