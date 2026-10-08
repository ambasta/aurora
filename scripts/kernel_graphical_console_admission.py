#!/usr/bin/env python3
"""Exact combined graphical Console admission; no inherited image qualification.

Source-only until an allocated build supplies actual linked forms. Unknown forms
fail closed. A successful emit is evidence for independent review, never review.
"""

from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/uefi"
RECEIPT = BUILD / "graphical-console-admission.json"
MODES = ("graphical-console", "graphical-console-capture")
ENTRY = "__au_v_m1_24kernel_graphical_console_n0__d17graphical_console"
REFLECTION_HELPERS = frozenset(("aurora_reflect_size", "aurora_reflect_field_count"))
BRIDGE = "__au_runtime_graphical_entry"
VALUE_BRIDGE = "__au_runtime_graphical_value"
VALUE_ENTRY = "aurora_kernel_value"
TOOLS = ("as", "ld", "objcopy", "objdump", "nm", "readelf", "c++filt", "python3")
HOST_IMPORTS = frozenset(("__au_runtime_console_next", "__au_runtime_console_put", "__au_runtime_display_pixel"))
CPP_OBJECTS = ("payload", "acpi", "pci", "runtime", "graphical-console")
ASSEMBLY_OBJECTS = ("payload-entry", "console-entry", "language", "memory")
BASE_FLAGS = tuple(
    (
        "-std=c++23 -O2 -fstack-usage -Wall -Wextra -Werror -ffreestanding "
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


def normalize_instruction(decoder, row, payload):
    if row.op in ("sti", "mfence", "pause", "wrmsr"):
        need(not row.args, "Unexpected privileged/fence operands")
    if row.op == "push" and row.args.startswith("$"):
        expected = {"$0x0": b"\x6a\x00", "$0x28": b"\x6a\x28"}.get(row.args)
        raw = payload[row.address : row.address + row.size]
        need(
            expected is not None and row.size == 2 and raw == expected,
            "Unreviewed immediate push width, bytes or value",
        )
        return decoder.Instruction(row.address, row.size, "push", "%rax"), dict(
            address=row.address,
            original=row.args,
            bytes=raw.hex(),
            equivalent="validated imm8 sign-extended qword push, +8 stack bytes",
        )
    # No memory-push, signed-wide stack immediate, or mnemonic normalization.
    return row, None


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
        and {name for name in linked_names if name.startswith("aurora_reflect_")} == REFLECTION_HELPERS
        and not REFLECTION_HELPERS.intersection(set(frames) | set(memory_names)),
        "Reflection helpers must belong only to generated language",
    )
    runtime = {name for name in linked_names if name.startswith("__au_runtime_")}
    need(runtime == HOST_IMPORTS | {BRIDGE, VALUE_BRIDGE}, "Unexpected combined runtime authority/import inventory")
    need(
        not any(name.startswith(("uefi_runtime_", "aurora_user_", "aurora_kernel_budget_")) for name in linked_names),
        "Unexpected protected runtime or budget fixture",
    )


def paired_recursion_proofs(decoder, functions, symbols, code, starts, paired_walk):
    legacy = decoder.WALK
    need(
        paired_walk != legacy and {legacy, paired_walk} <= set(functions), "Two separate concrete page walkers required"
    )
    result = {}
    try:
        for label, name in (("legacy_empty_tree", legacy), ("paired_mapping", paired_walk)):
            decoder.WALK = name
            levels, roots = decoder.recursion_proof(functions, symbols, code, starts)
            result[label] = dict(symbol=name, levels=levels, roots=roots, maximum_live_frames=4)
    finally:
        decoder.WALK = legacy
    return result


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
    def mangle(kind, scope, name):
        namespace = "0_" if not scope else "1_" + str(len(scope)) + scope
        return "__au_" + kind + "_m1_24kernel_graphical_console_n" + namespace + "_d" + str(len(name)) + name

    names = {
        BRIDGE,
        VALUE_BRIDGE,
        "aurora_kernel_value",
        "glyph_bits",
        "graphical_glyph_bits",
        "text_scale",
    } | REFLECTION_HELPERS
    names.update(mangle("v", "", name) for name in ("graphical_console", "draw_glyph", "draw_cell"))
    methods = {
        "Line64": ("finish", "reject", "consume"),
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
            "show_exit",
            "show_empty",
            "show_bounded",
        ),
    }
    for scope, items in methods.items():
        names.add(mangle("k", scope, scope))
        names.update(mangle("m", scope, name) for name in items)
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


def verify_reflection_body(decoder, symbol, rows, payload):
    """Closed constant lookup: exact bytes, complete coverage, no authority/memory."""
    need(
        symbol.name in REFLECTION_HELPERS and rows and symbol.address >= 0 and symbol.size > 0,
        "Unknown or empty reflection helper",
    )
    cursor = symbol.address
    for row in rows:
        need(row.address == cursor and row.size > 0, "Reflection instruction coverage gap/overlap")
        cursor += row.size
    need(cursor == symbol.address + symbol.size <= len(payload), "Reflection extent/coverage mismatch")

    def raw(row):
        return payload[row.address : row.address + row.size]

    def immediate(row, op, register):
        match = re.fullmatch(r"\$(0x[0-9a-f]+|[0-9]+),%" + register, row.args)
        need(row.op == op and match, "Reflection operand is not an immediate scalar")
        value = int(match[1], 0)
        need(0 <= value <= 0x7FFFFFFF, "Reflection scalar exceeds closed imm32 range")
        if op == "cmp":
            expected = [bytes.fromhex("4883ff") + bytes([value])] if value <= 127 else []
            expected += [bytes.fromhex("4881ff") + value.to_bytes(4, "little")]
        else:
            expected = [bytes.fromhex("48c7c0") + value.to_bytes(4, "little")]
        need(raw(row) in expected, "Reflection immediate opcode/bytes mismatch")
        return value

    index, keys, targets = 0, [], []
    while index < len(rows) and rows[index].op == "cmp":
        value = immediate(rows[index], "cmp", "rdi")
        need(value not in keys and index + 1 < len(rows), "Duplicate/truncated reflection comparison")
        branch = rows[index + 1]
        need(branch.op == "je", "Reflection comparison must have an equality branch")
        target = decoder.target_of(branch)
        branch_bytes = raw(branch)
        if branch.size == 6 and branch_bytes[:2] == bytes.fromhex("0f84"):
            displacement = int.from_bytes(branch_bytes[2:], "little", signed=True)
        elif branch.size == 2 and branch_bytes[:1] == b"\x74":
            displacement = int.from_bytes(branch_bytes[1:], "little", signed=True)
        else:
            raise ValueError("Reflection equality-branch opcode/bytes mismatch")
        need(
            type(target) is int
            and target == branch.address + branch.size + displacement
            and target > branch.address
            and target not in targets,
            "Reflection external/backward/duplicate or misdecoded branch",
        )
        keys.append(value)
        targets.append(target)
        index += 2
    need(keys, "Reflection helper lacks a closed lookup ladder")
    arms = []
    while index < len(rows):
        row = rows[index]
        arms.append(row.address)
        if row.op == "ud2":
            need(not row.args and raw(row) == bytes.fromhex("0f0b"), "Reflection trap bytes/operands mismatch")
            index += 1
            continue
        if row.op == "xor":
            need(
                row.args == "%rax,%rax" and raw(row) == bytes.fromhex("4831c0"),
                "Reflection zero return must be exact register self-zeroing",
            )
        else:
            immediate(row, "mov", "rax")
        need(
            index + 1 < len(rows)
            and rows[index + 1].op == "ret"
            and not rows[index + 1].args
            and raw(rows[index + 1]) == b"\xc3",
            "Reflection return arm must terminate exactly",
        )
        index += 2
    need(
        len(arms) == len(targets) + 1 and targets == arms[1:],
        "Reflection branches must cover only complete internal return arms",
    )
    return dict(
        symbol=symbol.name,
        address=symbol.address,
        bytes=symbol.size,
        cases=len(keys),
        arms=len(arms),
        calls=0,
        data_accesses=0,
    )


def verify_generated_divisions(functions, code, payload):
    """Exactly two register-only signed division pairs in draw_cell's arithmetic.

    CQTO writes RDX from RAX's sign and preserves flags. IDIV R11 writes only
    RAX/RDX and leaves flags undefined. Neither modifies stack, RCX or R14, so
    the existing conservative scalar/flag analysis is sufficient after this
    complete byte, operand, ownership and adjacency check. Synchronous faults
    retain the ordinary fault-path budget.
    """
    owner = "__au_v_m1_24kernel_graphical_console_n0__d9draw_cell"
    need(owner in functions, "Missing generated division owner")
    symbol = functions[owner]
    forms = [row for _, row in sorted(code.items()) if row.op in ("cqto", "idiv")]
    need(len(forms) == 4, "Unexpected generated division instruction inventory")
    evidence = []
    for index in (0, 2):
        sign, divide = forms[index : index + 2]
        need(
            symbol.address <= sign.address < divide.address < divide.next <= symbol.address + symbol.size
            and sign.op == "cqto"
            and not sign.args
            and sign.size == 2
            and payload[sign.address : sign.next] == bytes.fromhex("4899")
            and divide.address == sign.next
            and divide.op == "idiv"
            and divide.args == "%r11"
            and divide.size == 3
            and payload[divide.address : divide.next] == bytes.fromhex("49f7fb"),
            "Unknown generated signed-division bytes/operands/owner/pair",
        )
        evidence.append(
            dict(
                owner=owner,
                sign_address=sign.address,
                divide_address=divide.address,
                bytes="489949f7fb",
                stack_effect=0,
                clobbers=["rax", "rdx"],
            )
        )
    return evidence


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


def verify_retained_wait_paths(functions, owner, recursive):
    required = (BRIDGE, ENTRY, "__au_runtime_console_next")
    paths = []

    def visit(name, path, counts):
        if name in recursive:
            if counts.get(name, 0) == 4:
                return
            counts = dict(counts, **{name: counts.get(name, 0) + 1})
        else:
            need(name not in path, "Unknown wait graph cycle")
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
                visit(call["target"], path, counts)

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
    visit("uefi_payload_entry", [], {})
    need(paths, "No retained wait path")
    return paths


# GCC's retained source-specific lambda ABI compatibility alias. These exact
# names are evidence identities, not an authorization for general ELF aliases.
PAIRED_WALK = (
    "_ZZNK6aurora4uefi10PageTables16verify_graphicalEmRKNS0_5BytesEPKNS0_18LocalApicAdmissionEPKNS0_"
    "20FramebufferAdmissionEENKUlOT_mjmE1_clIRKSD_EEbSC_mjm"
)
PAIRED_ALIAS = (
    "_ZZNK6aurora4uefi10PageTables16verify_graphicalEmRKNS0_5BytesEPKNS0_18LocalApicAdmissionEPKNS0_"
    "20FramebufferAdmissionEENKUlOT_mjmE_clIRKSD_EEbSC_mjm"
)
PAIRED_SU_PARENT = (
    "aurora::uefi::PageTables::verify_graphical(uint64_t, const aurora::uefi::Bytes&, const aurora::"
    "uefi::LocalApicAdmission*, const aurora::uefi::FramebufferAdmission*) const"
)
PAIRED_SU_LAMBDA = "::<lambda(auto:2&&, uint64_t, unsigned int, uint64_t)>"
PAIRED_SU = PAIRED_SU_PARENT + PAIRED_SU_LAMBDA + " [with auto:2 = const " + PAIRED_SU_PARENT + PAIRED_SU_LAMBDA + "&]"
PAIRED_DEMANGLED_PARENT = (
    "bool aurora::uefi::PageTables::verify_graphical(unsigned long, aurora::uefi::Bytes const&, auro"
    "ra::uefi::LocalApicAdmission const*, aurora::uefi::FramebufferAdmission const*) const::"
)
PAIRED_DEMANGLED_LAMBDA = "{lambda(auto:1&&, unsigned long, unsigned int, unsigned long)#3}"
PAIRED_DEMANGLED = (
    PAIRED_DEMANGLED_PARENT
    + PAIRED_DEMANGLED_LAMBDA
    + "::operator()<"
    + PAIRED_DEMANGLED_LAMBDA
    + " const&>("
    + PAIRED_DEMANGLED_LAMBDA
    + " const&, unsigned long, unsigned int, unsigned long) const"
)


def paired_frame_identity(signature):
    # No general typedef substitution or substring-selected lambda identity.
    # The normalized spelling is accepted only for this entire exact signature.
    if signature in (PAIRED_SU, PAIRED_SU.replace("uint64_t", "unsigned long"), PAIRED_DEMANGLED):
        return PAIRED_WALK
    need(
        not ("PageTables::verify_graphical(" in signature and ("<lambda(" in signature or "{lambda(" in signature)),
        "Unknown exact paired walker frame signature",
    )
    return None


# These two distinct authority validators collide under the legacy decoder's
# template-erasing name extraction. Associate only the complete observed GCC
# signature and demangler spelling, retaining the exact separate ELF identities.
SESSION_VALIDATORS = {}
for _space, _transport in (("console", "ServiceTransport"), ("display", "DisplayTransport")):
    _symbol = (
        "_ZN6aurora7"
        + _space
        + "7SessionINS_4uefi12_GLOBAL__N_116"
        + _transport
        + "ENS3_15ServicePlatformEE8validateEPKvmb"
    )
    _stack = (
        "static void aurora::"
        + _space
        + "::Session<Transport, Platform>::validate(const void*, uint64_t, bool) "
        + "[with Transport = aurora::uefi::{anonymous}::"
        + _transport
        + "; Platform = aurora::uefi::{anonymous}::ServicePlatform]"
    )
    _demangled = (
        "aurora::"
        + _space
        + "::Session<aurora::uefi::(anonymous namespace)::"
        + _transport
        + ", aurora::uefi::(anonymous namespace)::ServicePlatform>::validate(void const*, unsigned long, bool)"
    )
    SESSION_VALIDATORS[_symbol] = (_stack, _demangled)


def session_frame_identity(signature):
    for symbol, spellings in SESSION_VALIDATORS.items():
        if signature in spellings:
            return symbol
    need("::validate(" not in signature, "Unknown exact Session validator frame signature")
    return None


def verify_session_frames(frames, associations):
    for symbol in SESSION_VALIDATORS:
        need(symbol in frames and symbol in associations, "Missing distinct Session validator frame")
        need(
            len(associations[symbol]) == 1
            and associations[symbol][0]["object"] == "graphical-console.o"
            and associations[symbol][0]["record"] == SESSION_VALIDATORS[symbol][0],
            "Session validator frame has foreign or duplicated ownership/signature",
        )


def paired_alias_evidence(obj):
    """Read both raw ELF entries before collapsing one proven code body."""
    pair = {PAIRED_WALK, PAIRED_ALIAS}
    need(pair <= set(obj.functions), "Missing exact paired walker alias pair")
    symbols = [obj.functions[name] for name in (PAIRED_WALK, PAIRED_ALIAS)]
    first = symbols[0]
    need(
        first.size == 866
        and first.kind == 2
        and first.section > 0
        and all(
            (row.address, row.size, row.section, row.kind) == (first.address, first.size, first.section, first.kind)
            for row in symbols
        ),
        "Diverged paired walker alias address/section/size/type",
    )
    need(
        {
            row.name
            for row in obj.symbols
            if row.section == first.section and row.address == first.address and row.kind == 2
        }
        == pair,
        "Unexpected paired walker alias inventory",
    )
    entries = []
    for section in obj.sections:
        if section[1] != 2:
            continue
        need(section[9] == 24, "Unsupported paired symbol table")
        strings = obj.section_data(section[6])
        for position in range(section[4], section[4] + section[5], 24):
            offset, info, other, index, address, size = struct.unpack_from("<IBBHQQ", obj.data, position)
            end = strings.find(b"\0", offset)
            need(end >= offset, "Invalid paired symbol string")
            name = strings[offset:end].decode()
            if name not in pair:
                continue
            need(
                info == 0x22 and other == 2 and (index, address, size) == (first.section, first.address, first.size),
                "Changed paired walker WEAK/HIDDEN FUNC binding or raw identity",
            )
            entries.append(
                dict(
                    name=name,
                    address=address,
                    size=size,
                    section=index,
                    binding="WEAK",
                    visibility="HIDDEN",
                    type="FUNC",
                )
            )
    need(len(entries) == 2 and {row["name"] for row in entries} == pair, "Duplicate or missing raw paired alias entry")
    return dict(
        canonical=PAIRED_WALK,
        aliases=sorted(entries, key=lambda row: row["name"]),
        body_sha256=hashlib.sha256(obj.function_bytes(first)).hexdigest(),
    )


def graphical_cpp_frames(decoder, directory, linked):
    # Keep the shared decoder untouched. Both alias names cross its exact
    # object/link byte-and-relocation association before one frame is counted.
    associated, receipts, alias_objects = {}, {}, []
    for name in CPP_OBJECTS:
        obj = decoder.Elf(directory / (name + ".o"))
        need(obj.type == 1, "Expected relocatable C++ object")
        if name == "graphical-console":
            evidence = paired_alias_evidence(obj)
            for symbol in (PAIRED_WALK, PAIRED_ALIAS):
                decoder.associate_object(linked, obj, obj.functions[symbol])
            alias_objects.append(
                dict(object=name + ".o", **evidence, associated_linked_symbols=[PAIRED_WALK, PAIRED_ALIAS])
            )
        else:
            need(not {PAIRED_WALK, PAIRED_ALIAS} & set(obj.functions), "Paired walker outside exact graphical object")
        rows = decoder.stack_rows((directory / (name + ".su")).read_text())
        names = [symbol for symbol in obj.functions if symbol != PAIRED_ALIAS]
        spellings = decoder.command("c++filt", *names).splitlines() if names else []
        need(len(names) == len(spellings), "Demangler record mismatch")
        used = set()
        for symbol, spelling in zip(names, spellings):
            identity = decoder.frame_identity(spelling) if symbol.startswith("_Z") else symbol
            if identity in SESSION_VALIDATORS:
                need(symbol == identity and name == "graphical-console", "Crossed Session validator ELF identity")
            need(identity in rows, "Missing exact compiler frame: " + symbol)
            need(identity not in used, "Ambiguous object/frame association: " + identity)
            used.add(identity)
            size, signature = rows[identity]
            need(8 <= size <= decoder.STACK_CAP, "Invalid compiler frame bound")
            need(symbol in linked.functions, "Object function omitted from linked profile")
            decoder.associate_object(linked, obj, obj.functions[symbol])
            if symbol in associated:
                need(associated[symbol] == size, "Conflicting COMDAT compiler frames")
            associated[symbol] = size
            receipts.setdefault(symbol, []).append(dict(object=name + ".o", record=signature, bytes=size))
        need(used == set(rows), "Stack records lack exact object definitions: " + name)
    need(len(alias_objects) == 1, "Missing exact graphical alias association")
    return associated, receipts, alias_objects


def stack_evidence(directory):
    decoder = load("graphical_stack_decoder", ROOT / "tests/kernel-uefi-owned-bytes-stack.py")
    decoder.CPP_OBJECTS = CPP_OBJECTS
    # Scalar additions are the reviewed operand-decoded console forms, not
    # arbitrary opcode rewriting: RSP/RBP writes still cross the core stack
    # checks first; unknown writes kill ECX/R14 level facts. test widths are
    # read-only. MFENCE/PAUSE/STI/WRMSR require no operands below; STI is further
    # restricted to the exact wait. SIDT is an explicit memory write, never an
    # implicit stack adjustment. No form here authorizes indirect control flow.
    decoder.NEUTRAL |= frozenset(
        (
            "sti wrmsr sar movswl movzwl movw sal sidt setg setge cmovb cmovg cmovge "
            "testb testl testw cmovs bswap mfence pause"
        ).split()
    )
    decoder.READ_ONLY |= frozenset(("testb", "testl", "testw"))
    decoder.PRESERVE_FLAGS |= frozenset(("sti", "wrmsr", "mfence", "pause", "cqto"))
    decoder.NEUTRAL |= frozenset(("cqto", "idiv"))
    linked = decoder.Elf(directory / "payload.elf")
    need(linked.type == 2, "Expected linked executable payload")
    need(not subprocess.check_output(["nm", "-u", directory / "payload.elf"], text=True).strip(), "Unresolved payload")
    paired_linked = paired_alias_evidence(linked)
    paired_walk = PAIRED_WALK
    old_identity = decoder.frame_identity
    aliases = {
        "aurora::uefi::service_next": "__au_runtime_console_next",
        "aurora::uefi::service_put": "__au_runtime_console_put",
        "aurora::uefi::display_pixel": "__au_runtime_display_pixel",
        "aurora::uefi::interrupt_dispatch": "uefi_console_interrupt_dispatch",
    }

    def identity(signature):
        session = session_frame_identity(signature)
        if session is not None:
            return session
        paired = paired_frame_identity(signature)
        if paired is not None:
            return paired
        value = old_identity(signature)
        return aliases.get(value, value)

    decoder.frame_identity = identity
    old_rows = decoder.stack_rows
    bounded = []

    def stack_rows(text):
        lines = []
        for line in text.splitlines():
            if line.endswith("\tdynamic,bounded"):
                need(
                    any(
                        name in line
                        for name in (
                            "aurora::uefi::run_graphical_console(",
                            "FramebufferPayload::restore_graphical_fixture(",
                        )
                    ),
                    "Unreviewed dynamically bounded C++ frame",
                )
                bounded.append(line)
                line = line.removesuffix("\tdynamic,bounded") + "\tstatic"
            lines.append(line)
        return old_rows("\n".join(lines))

    decoder.stack_rows = stack_rows
    frames, associations, alias_objects = graphical_cpp_frames(decoder, directory, linked)
    verify_session_frames(frames, associations)
    # Raw symbols and evidence remain intact; only the analyzed function graph
    # loses the compatibility spelling after both associations have succeeded.
    del linked.functions[PAIRED_ALIAS]
    named = {row.name: row for row in linked.symbols if row.section}
    irq = named["uefi_console_interrupt"]
    irq_object = decoder.Elf(directory / "console-entry.o")
    irq_symbols = [row for row in irq_object.symbols if row.name == irq.name]
    need(len(irq_symbols) == 1, "Ambiguous IRQ object symbol")
    original = irq_symbols[0]
    extent = irq_object.sections[original.section][5] - original.address
    linked.functions[irq.name] = decoder.Symbol(irq.name, irq.address, extent, irq.section, 2)
    starts = {symbol.address: name for name, symbol in linked.functions.items()}
    need(len(starts) == len(linked.functions), "Ambiguous linked function starts")
    code, disassembly = decoder.disassemble(directory / "payload.elf")
    payload = (directory / "payload.bin").read_bytes()
    divisions = verify_generated_divisions(linked.functions, code, payload)
    body = lambda symbol: [r for a, r in sorted(code.items()) if symbol.address <= a < symbol.address + symbol.size]
    verify_irq_body(decoder, body(linked.functions[irq.name]), starts)
    normalized = []
    for address, row in list(code.items()):
        if irq.address <= address < irq.address + extent:
            continue  # Entire exact IRQ has its separate save/restore proof above.
        code[address], receipt = normalize_instruction(decoder, row, payload)
        if receipt:
            normalized.append(receipt)
    language, memory = (decoder.Elf(directory / (name + ".o")) for name in ("language", "memory"))
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
    functions = {}
    for name, symbol in linked.functions.items():
        if name == irq.name:
            continue
        try:
            functions[name] = decoder.analyze_function(symbol, code, starts, fault=name == "fault_common")
        except ValueError as error:
            raise ValueError(name + ": " + str(error)) from error
    console.verify_noreturn(functions, decoder.NORETURN)
    verify_bridge_body(decoder, body(linked.functions[BRIDGE]), starts)
    private_abi = verify_private_abi(decoder, linked, code, starts, language.functions, functions)
    proofs = paired_recursion_proofs(decoder, functions, linked.functions, code, starts, paired_walk)
    recursive = {proof["symbol"] for proof in proofs.values()}
    for name in functions:
        common.graph_peak(functions, frames, name, recursive)
    normal = common.graph_peak(functions, frames, "uefi_payload_entry", recursive)
    session = common.graph_peak(functions, frames, ENTRY, recursive)
    fault = 48 + max(
        common.graph_peak(functions, frames, name, recursive)["peak"]
        for name in ("uefi_payload_fault", "uefi_payload_page_fault")
    )
    dispatch = common.graph_peak(functions, frames, "uefi_console_interrupt_dispatch", recursive)
    irq_peak = 176 + 15 + dispatch["peak"]
    owner, irq_reachable = verify_wait_closure(code, named, functions, language.functions, payload, linked.functions)
    need(owner not in irq_reachable, "IRQ reaches interruptible wait")
    retained_paths = verify_retained_wait_paths(functions, owner, recursive)
    waiting = common.graph_peak(functions, frames, "uefi_payload_entry", recursive, target=owner)
    need(
        {ENTRY, BRIDGE, "__au_runtime_console_next"} <= set(waiting["path"]),
        "Wait does not retain paired Aurora service and Console host call",
    )
    verify_stack_budgets(normal["peak"], waiting["peak"], irq_peak, fault)
    waiting["peak_with_interrupt"] = waiting["peak"] + irq_peak
    waiting["peak_with_interrupt_and_fault"] = waiting["peak"] + irq_peak + fault
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
        normalized_stack_immediates=normalized,
        paired_walker_identity=dict(linked=paired_linked, objects=alias_objects),
        page_verifiers=proofs,
        disassembly_sha256=hashlib.sha256(disassembly.encode()).hexdigest(),
    )


def build_files():
    names = [
        "payload.elf",
        "payload.bin",
        "esp/EFI/BOOT/BOOTX64.EFI",
        "uefi-payload.hpp",
        "language.s",
        "embed.S",
        "console-poll-metadata.json",
        "image-metadata.json",
    ]
    names += [name + ".o" for name in CPP_OBJECTS + ASSEMBLY_OBJECTS + ("loader", "embed", "transition")]
    names += [name + ".su" for name in CPP_OBJECTS + ("loader",)]
    names += [name + "-pe.o" for name in ("loader", "memory", "embed", "transition")]
    return [BUILD / name for name in names]


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
    record["output_sha256"] = common.hashes(build_files())
    (BUILD / "graphical-console-build.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")


def provenance(mode):
    record = read_json(BUILD / "graphical-console-build.json")
    verify_inputs(record, mode)
    need(set(record) == BUILD_KEYS | {"output_sha256"}, "Incomplete build manifest")
    need(record["output_sha256"] == common.hashes(build_files()), "Combined build output changed")
    return record


def image_evidence(directory):
    image = load("graphical_image_decoder", ROOT / "tests/kernel-uefi-image.py")
    binary = (directory / "payload.bin").read_bytes()
    elf = (directory / "payload.elf").read_bytes()
    pe = (directory / "esp/EFI/BOOT/BOOTX64.EFI").read_bytes()
    image.elf_validate(elf, binary)
    image.pe_validate(pe, binary)
    graphical_policy = image.graphical_image_policy(directory)
    objects = {}
    for name in CPP_OBJECTS + ASSEMBLY_OBJECTS:
        relocations = subprocess.check_output(["readelf", "-rW", directory / (name + ".o")], text=True)
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
    return dict(
        **metadata,
        elf_sha256=hashlib.sha256(elf).hexdigest(),
        object_relocations=objects,
        poll=poll,
        graphical_policy=graphical_policy,
    )


def emit(mode):
    RECEIPT.unlink(missing_ok=True)
    record = provenance(mode)
    result = dict(
        schema="aurora-graphical-console-admission-v1",
        status="requires-independent-review",
        mode=mode,
        clock="tcg-original-clock",
        build=record,
        image=image_evidence(BUILD),
        stack=stack_evidence(BUILD),
    )
    need(record == provenance(mode), "Build changed during admission")
    result["sha256"] = common.hashes(source_files() + build_files() + [BUILD / "graphical-console-build.json"])
    RECEIPT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("PASS: automatic combined image/stack evidence; independent first-image acceptance still required")
    return result


def checked(mode):
    receipt = read_json(RECEIPT)
    need(type(receipt) is dict, "Receipt must be an object")
    need(
        set(receipt) == {"schema", "status", "mode", "clock", "build", "image", "stack", "sha256"},
        "Unexpected receipt keys",
    )
    need(
        receipt["schema"] == "aurora-graphical-console-admission-v1"
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
    need(
        canonical(receipt["image"]) == canonical(image_evidence(BUILD))
        and canonical(receipt["stack"]) == canonical(stack_evidence(BUILD)),
        "Receipt image/stack evidence differs from fresh combined proof",
    )
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
    parser.add_argument(
        "action",
        choices=("begin", "end", "begin-build", "end-build", "emit", "verify", "checked", "reviewed", "diagnose"),
    )
    parser.add_argument("--mode", required=True, choices=MODES)
    parser.add_argument("--compiler")
    parser.add_argument("--cxx")
    parser.add_argument("--linker")
    parser.add_argument("--flag", action="append", default=[])
    args = parser.parse_args()
    if args.action in ("begin", "begin-build"):
        begin(args.mode, args.compiler, args.cxx, args.flag, args.linker)
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
