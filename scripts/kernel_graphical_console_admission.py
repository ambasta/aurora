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


# These are SOURCE contracts, never synthetic replacements for emitted code.
# The native overlay implements the independently reviewed closed fixture plan.
# Freeze complete token streams, plus each conditional region and its insertion
# point, so a matching fragment cannot hide a second writer or bypassing path.
# Whitespace/comments are irrelevant; strings, operators and all other tokens
# remain exact. All three Session headers are unchanged reviewed dependencies.
CAPTURE_NATIVE = "kernel/uefi/graphical-console.cpp"
CAPTURE_POLICY = "kernel/uefi/graphical-capture-policy.hpp"
CAPTURE_SOURCE_PINS = {
    CAPTURE_POLICY: "d243cfdd14409fdbbe6803662378c12e9ff17f72734c4702e9f24b158cd53611",
    "kernel/graphical-session.hpp": "27ef0622f075054ab3062148e332b66d68d3e37dc4801e3ff0b7be279b61d79f",
    "kernel/console-session.hpp": "8dcf227c5283735ffa02bc41f40509f907a980f56877189cb04d345b082af21f",
    "kernel/display-session.hpp": "a087a8e34438ff75c373b7015133db274c18ddd8f5a8c92b750f20893bd9117d",
}
CAPTURE_REGIONS = (
    ("policy include", "ifdef", 3, "864f5fcd25a82700a95438723b30f9e7e3302661c8f1b58e32503c18adb94f01"),
    ("private state", "ifdef", 143, "594d1f1292f5a429620ca1e3eb9a6da93deb0634a375da90b5277660d1c1aea7"),
    ("failure diagnostics", "ifdef", 456, "acc794c0ac7709b2ad4c2a39aa63952b39596e619723bcdc680c3b069706da44"),
    ("production fail exit", "ifndef", 463, "77105a271a56baed767bd387c269f99d8f181029b6950b226932a84ac3be933a"),
    ("selector gate and sole writer", "ifdef", 907, "49b4dc9144b81945ce82034234a68e8bf37b2e5aefcb7ca8a9ce22ed26d6199c"),
    ("admitted pixel failure", "ifdef", 1246, "7be663f9d39f01990c9850ffcfb75374736911348fb84bc9cd94329852f0eb78"),
    ("pre-sample diagnostics", "ifdef", 1847, "ddf0a795439653c175b4e86475c001392cec7056510d2ff1a1019be3064878c8"),
    ("pre-grant gate call", "ifdef", 2930, "f8ad783a0ef5ac8964306cfa7eb8b44fe293e471a247cf6049fb7a463714477c"),
    ("local record and real reopen", "ifdef", 3047, "f2f7d5c3a0806f8b88198e1b99d88942984c81ff1b1b037859ba98f7ca1dab42"),
    ("completion diagnostics", "ifdef", 3273, "b7be54c1a7e28646f80d7ffa8ff17fbc102407f256413d1956572d5da7b8da72"),
    ("production completion exit", "ifndef", 3280, "5b0af10a4420bb529ad54f0ea52302a493b18c1b59b2666d3ca098fb1e3b9d22"),
)
CAPTURE_SELECTORS = {
    "G": "normal",
    "C": "cross-console",
    "D": "cross-display",
    "c": "stale-console",
    "d": "stale-display",
    "F": "first-pixel-error",
    "I": "interior-pixel-error",
}
CAPTURE_LINKED_REQUIREMENTS = (
    "closed selector decode, sole scenario writer and release ordering",
    "local six-word record mutations and genuine Session close/reopen generations",
    "trusted-record identity and both preflights dominate the sole compiled entry",
    "pixel admission dominates one checked attempt increment and fixed 0/55 failure before store",
    "exact failure/completion diagnostics and successful-store accounting",
    "actual object/link bytes, relocations, frames and unchanged generated language/bridge bytes",
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
CPP_SOURCE_TOKEN = re.compile(
    r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|'
    r"[A-Za-z_]\w*|0[xX][0-9A-Fa-f]+[uUlL]*|[0-9]+[uUlL]*|"
    r"::|->|\+\+|--|==|!=|<=|>=|&&|\|\||<<|>>|\+=|-=|\*=|/=|%=|&=|\|=|\^=|[^\s]"
)


def capture_source_tokens(text):
    need(not re.search(r"\\\r?\n|\?\?/", text), "Unreviewed capture source line splicing")
    return [row.group() for row in CPP_SOURCE_TOKEN.finditer(text) if not row.group().startswith(("//", "/*"))]


def capture_source_digest(text):
    return hashlib.sha256(canonical(capture_source_tokens(text)).encode()).hexdigest()


def capture_source_projection(text):
    """Only the actual closed profile directives, not a general preprocessor."""
    production, capture, regions, region = "", "", [], None
    for line in text.splitlines(keepends=True):
        directive = line.strip()
        if directive in ("#ifdef AURORA_UEFI_GRAPHICAL_CAPTURE", "#ifndef AURORA_UEFI_GRAPHICAL_CAPTURE"):
            need(region is None, "Nested capture source condition")
            region = [directive.split()[0][1:], "", len(capture_source_tokens(production))]
        elif directive == "#endif":
            need(region is not None, "Unmatched capture source condition")
            kind, body, position = region
            regions.append((kind, position, capture_source_digest(body)))
            if kind == "ifndef":
                production += body
            else:
                capture += body
            region = None
        else:
            need(not directive.startswith("#") or directive.startswith("#include "), "Unreviewed source directive")
            if region is not None:
                region[1] += line
            else:
                production += line
                capture += line
    need(region is None, "Unclosed capture source condition")
    return production, capture, regions


def capture_source_evidence(mode, sources=None):
    need(mode in MODES, "Unknown graphical profile")
    paths = {CAPTURE_NATIVE, *CAPTURE_SOURCE_PINS}
    if sources is None:
        sources = {name: (ROOT / name).read_text() for name in paths}
    need(set(sources) == paths, "Changed capture source dependency inventory")
    for name, expected in CAPTURE_SOURCE_PINS.items():
        need(capture_source_digest(sources[name]) == expected, "Unreviewed capture source dependency: " + name)
    production, capture, regions = capture_source_projection(sources[CAPTURE_NATIVE])
    need(len(regions) == len(CAPTURE_REGIONS), "Changed capture conditional region inventory")
    for actual, (name, kind, position, expected) in zip(regions, CAPTURE_REGIONS):
        need(actual == (kind, position, expected), "Changed capture source region/position: " + name)
    need(
        capture_source_digest(production) == "1e85afab1304e327bbf9dbce2677e1665ee7059ebdafffaef8a9fa15f3472066",
        "Changed ordinary graphical source projection",
    )
    need(
        capture_source_digest(capture) == "6116de63e74e431c0df88a36366efbd704d0b682bd976b0ff7e43ed23bc0a7a0",
        "Changed complete capture graphical source projection",
    )
    return dict(
        schema="aurora-graphical-capture-source-v1",
        mode=mode,
        status="source-contract-only",
        source_sha256={name: hashlib.sha256(sources[name].encode()).hexdigest() for name in sorted(sources)},
        selectors=dict(CAPTURE_SELECTORS) if mode == MODES[1] else {},
        invalid_selectors=249 if mode == MODES[1] else 0,
        failure_successful_store_ordinals=[0, 55] if mode == MODES[1] else [],
        regions=[name for name, *_ in CAPTURE_REGIONS],
        remaining_linked_proofs=list(CAPTURE_LINKED_REQUIREMENTS)
        if mode == MODES[1]
        else ["production fixture absence"],
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
            and b"AURORA_GRAPHICAL_CAPTURE_RELEASED: scenario=" in owner["contents"],
            "Missing capture fixture state or exact release diagnostic",
        )
    return dict(
        mode=mode,
        status="requires-actual-linked-fixture-proof" if mode == MODES[1] else "fixture-absent",
        fixture_tokens=found,
        artifact_sha256=hashes,
    )


def require_capture_linked_proof(mode):
    need(mode in MODES, "Unknown graphical profile")
    # Intentionally no override, receipt pin or source predicate can clear this.
    # Replace only after actual compiler output and independent linked review;
    # retain all original instruction/stack/import/IRQ/paging guards meanwhile.
    need(
        mode != MODES[1],
        "Capture fixture linked proof pending: construct the exact capture objects/ELF, retain original "
        "instruction bytes/operands, relocations and .su frames, then independently review: "
        + "; ".join(CAPTURE_LINKED_REQUIREMENTS),
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


PAIRED_WALK = (
    "_ZZNK6aurora4uefi10PageTables16verify_graphicalEmRKNS0_5BytesEPKNS0_18LocalApicAdmissionEPKNS0_"
    "20FramebufferAdmissionEENKUlOT_mjmE1_clIRKSD_EEbSC_mjm"
)
PAIRED_ALIAS = (
    "_ZZNK6aurora4uefi10PageTables16verify_graphicalEmRKNS0_5BytesEPKNS0_18LocalApicAdmissionEPKNS0_"
    "20FramebufferAdmissionEENKUlOT_mjmE_clIRKSD_EEbSC_mjm"
)

# This pure induction engine is not an admission substitute. The caller must
# first establishes the closed linked root snapshot/guard and visited-store
# contract below before applying this engine to the original instructions.
PAIRED_LEVEL_HELPER = "_ZN6aurora4uefi14expected_flagsEmRKNS0_5BytesE"
PAIRED_LEVEL_SPILLS = frozenset((0x18, 0x20, 0x3C))
PAIRED_LEVEL_OPS = frozenset(
    (
        "push pop mov movabs movb movl movq movw movzbl sub add cmp cmpb test lea xor "
        "shl shr and or call ret nop nopl nopw cs data16"
    ).split()
)


def paired_frame_envelope(decoder, symbol, code):
    rows = [row for address, row in sorted(code.items()) if symbol.address <= address < symbol.address + symbol.size]
    saves = ("%r15", "%r14", "%r13", "%r12", "%rbp", "%rbx")
    prologue = [("push", saves[0]), ("mov", "%rdx,%r11")]
    prologue += [("push", register) for register in saves[1:]] + [("sub", "$0x48,%rsp")]
    need([(row.op, row.args) for row in rows[:8]] == prologue, "Changed paired fixed-frame prologue")
    restores = [("add", "$0x48,%rsp")] + [("pop", register) for register in reversed(saves)] + [("ret", "")]
    exits = []
    allowed_stack_changes = {row.address for row in rows[:8] if row.op in ("push", "sub")}
    for index, row in enumerate(rows):
        if row.op == "ret":
            need(
                index >= 7 and [(item.op, item.args) for item in rows[index - 7 : index + 1]] == restores,
                "Changed paired fixed-frame restoration",
            )
            exits.append(row.address)
            allowed_stack_changes.update(item.address for item in rows[index - 7 : index + 1])
    need(exits, "Paired walker has no balanced return")
    for row in rows:
        args = decoder.arguments(row.args)
        need(not (row.op == "lea" and "%rsp" in row.args), "Paired private frame address escapes via LEA")
        if row.op in ("push", "pop", "leave", "pushf") or (args and args[-1] in ("%rsp", "%esp", "%sp", "%spl")):
            need(row.address in allowed_stack_changes, "Paired spill frame base changes inside body")
        for operand in args:
            if "sp" in operand and "%" in operand:
                need(
                    operand == "%rsp"
                    and row.address in allowed_stack_changes
                    or re.fullmatch(r"(?:0x[0-9a-f]+)?\(%rsp\)", operand),
                    "Paired private frame address escapes or has indexed/unknown form",
                )
    return rows


def paired_readonly_leaf(decoder, name, symbols, code, functions):
    need(
        name == PAIRED_LEVEL_HELPER and name in symbols and not functions[name]["calls"],
        "Paired level helper is not the exact closed leaf",
    )
    symbol = symbols[name]
    readonly = {"cmp", "cmpb", "cmpl", "cmpq", "cmpw", "test", "bt", "nop", "nopl", "nopw", "cs", "data16"}
    for address, row in code.items():
        if not symbol.address <= address < symbol.address + symbol.size:
            continue
        args = decoder.arguments(row.args)
        need(
            row.op not in ("call", "push", "pop", "leave", "pushf", "rep", "xchg", "syscall", "out", "in")
            and not any("%rsp" in operand or "%rbp" in operand for operand in args),
            "Paired helper has calls, side effects or private-frame access",
        )
        if row.op in decoder.BRANCHES:
            need(
                symbol.address <= decoder.target_of(row) < symbol.address + symbol.size,
                "Paired helper branches outside its read-only body",
            )
        elif row.op not in readonly and row.op != "ret":
            need(
                row.op in {"mov", "movabs", "movzbl", "lea", "xor", "or", "sub", "add", "shl", "cmovae"}
                and paired_register(args[-1]) not in PAIRED_SAVES,
                "Paired helper has unknown effects or clobbers a callee-saved register",
            )
            need(
                args
                and re.fullmatch(
                    r"%(?:r(?:ax|bx|cx|dx|si|di|[89]|1[0-5])|e(?:ax|bx|cx|dx|si|di)|[abcd][lh]|r(?:[89]|1[0-5])[dwb])",
                    args[-1],
                ),
                "Paired helper writes memory or a non-scalar register",
            )
    return dict(symbol=name, calls=0, memory_writes=0)


def paired_level_induction(decoder, symbol, code, starts, generic, bitmap_stores=(), storage=None):
    """Original-instruction ECX/R9D and byte-spill fixed points for seeds 0..3.

    bitmap_stores must be the exact addresses whose bounded, root-owned target
    was proved by the linked root and local walker contract. With storage set,
    each seed also establishes caller-memory preservation and closure forwarding;
    a child may preserve spills only after its smaller seed was established.
    Without storage this is solely a pure level constituent, never admission.
    """
    rows = paired_frame_envelope(decoder, symbol, code)
    begin, end = symbol.address, symbol.address + symbol.size
    body = {row.address: row for row in rows}
    bitmap_stores = frozenset(bitmap_stores)
    need(bitmap_stores <= set(body), "Bitmap write summary references another function")
    call_rows = [row for row in rows if row.op == "call"]
    targets = [starts.get(decoder.target_of(row)) for row in call_rows]
    need(
        targets.count(symbol.name) == 1 and targets.count(PAIRED_LEVEL_HELPER) == 2 and len(targets) == 3,
        "Unexpected paired helper/self-call inventory",
    )
    generic_calls = {row["address"]: row for row in generic["calls"]}
    need(set(generic_calls) == {row.address for row in call_rows}, "Paired generic call inventory mismatch")

    def register(operand):
        if operand in ("%rcx", "%ecx", "%cx", "%cl", "%ch"):
            return 0
        if operand in ("%r9", "%r9d", "%r9w", "%r9b"):
            return 1
        return None

    def width(operand):
        if re.fullmatch(r"%r(?:ax|bx|cx|dx|si|di|bp|[89]|1[0-5])", operand):
            return 8
        if re.fullmatch(r"%(?:e(?:ax|bx|cx|dx|si|di|bp)|r(?:[89]|1[0-5])d)", operand):
            return 4
        if re.fullmatch(r"%(?:ax|bx|cx|dx|si|di|bp|r(?:[89]|1[0-5])w)", operand):
            return 2
        if re.fullmatch(r"%(?:al|ah|bl|bh|cl|ch|dl|dh|sil|dil|bpl|r(?:[89]|1[0-5])b)", operand):
            return 1
        return None

    def stack_slot(operand):
        match = re.fullmatch(r"(0x[0-9a-f]+)?\(%rsp\)", operand)
        return int(match[1] or "0", 16) if match else None

    if storage is not None:
        need(
            storage["walker"]["conditional_on_smaller_seed"] is True
            and bitmap_stores == {storage["walker"]["bitmap_store"]}
            and set(storage["helpers"]) == set(PAIRED_HELPERS)
            and all(effect["caller_memory_writes"] == 0 for effect in storage["helpers"].values()),
            "Missing paired local storage/helper premise",
        )
    levels = {}
    readonly = {"cmp", "cmpb", "test", "nop", "nopl", "nopw", "cs", "data16"}
    preserve_flags = {
        "mov",
        "movabs",
        "movb",
        "movl",
        "movq",
        "movw",
        "movzbl",
        "lea",
        "push",
        "pop",
        "nop",
        "nopl",
        "nopw",
        "cs",
        "data16",
    }
    for seed in range(4):
        # Byte precision prevents adjacent qword data spills from being treated
        # as preserving overlapping dword level facts. No address-only memo.
        closure_seed = ("closure", "closure") if storage is not None else (None, None)
        states = {begin: (seed, None, None, (None,) * 0x48, closure_seed)}
        pending, visited, calls, returns = [begin], set(), {}, set()

        def schedule(address, state):
            need(begin <= address < end and address in body, "Paired CFG leaves body or enters an instruction interior")
            prior = states.get(address)
            if prior is not None:
                state = tuple(a if a == b else None for a, b in zip(prior[:3], state[:3])) + (
                    tuple(a if a == b else None for a, b in zip(prior[3], state[3])),
                    tuple(a if a == b else None for a, b in zip(prior[4], state[4])),
                )
                if state == prior:
                    return
            states[address] = state
            pending.append(address)

        while pending:
            address = pending.pop()
            row = body[address]
            need(
                row.next <= end and row.op in PAIRED_LEVEL_OPS | decoder.BRANCHES,
                "Unreviewed paired level instruction or extent",
            )
            visited.add(address)
            cx, r9, zf, memory, closure = states[address]
            values, memory, next_closure = [cx, r9], list(memory), list(closure)
            args = decoder.arguments(row.args)
            next_zf = zf if row.op in preserve_flags | decoder.BRANCHES else None
            if row.op == "ret":
                returns.add(address)
                continue
            if row.op == "call":
                target = starts.get(decoder.target_of(row))
                call = dict(generic_calls[address])
                if target == symbol.name:
                    need(
                        seed > 0 and seed - 1 in levels and cx == seed - 1,
                        "Paired child lacks previously proved decreasing level",
                    )
                    if storage is not None:
                        need(
                            levels[cx].get("caller_memory_contract") is True and closure == ("closure", "closure"),
                            "Paired child lacks established memory contract or identical closure",
                        )
                    call["level"] = cx
                else:
                    need(target == PAIRED_LEVEL_HELPER, "Unexpected paired level callee")
                    if storage is not None:
                        need("closure" not in closure, "Paired closure escapes to scalar helper")
                    call["level"] = None
                previous = calls.get(address)
                need(previous is None or previous == call, "Paired call level facts disagree at a join")
                calls[address] = call
                # No caller-saved level/flag survives even a read-only helper.
                schedule(row.next, (None, None, None, tuple(memory), (None, None)))
                continue
            if row.op in decoder.BRANCHES:
                target = decoder.target_of(row)
                taken = (
                    zf if row.op in ("je", "jz") else (not zf if zf is not None and row.op in ("jne", "jnz") else None)
                )
                if row.op == "jmp" or taken is not False:
                    schedule(target, (cx, r9, zf, tuple(memory), closure))
                if row.op != "jmp" and taken is not True:
                    schedule(row.next, (cx, r9, zf, tuple(memory), closure))
                continue
            if args and row.op not in readonly:
                closure_register = paired_register(args[-1])
                if closure_register in ("rdi", "rsi"):
                    destination = ("rdi", "rsi").index(closure_register)
                    next_closure[destination] = None
                    if row.op == "mov" and args[-1] == "%" + closure_register:
                        source = paired_register(args[0])
                        if source in ("rdi", "rsi") and args[0] == "%" + source:
                            next_closure[destination] = closure[("rdi", "rsi").index(source)]
                        else:
                            offset = stack_slot(args[0])
                            if offset is not None and memory[offset : offset + 8] == [("closure", i) for i in range(8)]:
                                next_closure[destination] = "closure"
                destination = register(args[-1])
                if destination is not None:
                    values[destination] = None
                    if row.op == "mov" and len(args) == 2 and args[-1] in ("%ecx", "%r9d"):
                        source = register(args[0])
                        if source is not None and args[0] in ("%ecx", "%r9d"):
                            values[destination] = (cx, r9)[source]
                        else:
                            offset = stack_slot(args[0])
                            if offset in PAIRED_LEVEL_SPILLS and offset + 4 <= 0x48:
                                content = memory[offset : offset + 4]
                                if len(content) == 4 and all(type(value) is int for value in content):
                                    value = int.from_bytes(bytes(content), "little")
                                    values[destination] = value if value <= 3 else None
                    elif row.op == "lea" and row.args == "-0x1(%r9),%ecx" and r9 is not None:
                        values[0] = (r9 - 1) & 0xFFFFFFFF
                if "(" in args[-1]:
                    offset = stack_slot(args[-1])
                    if offset is None:
                        need(
                            address in bitmap_stores and row.op == "movb" and row.args == "$0x1,(%rdx,%rax,1)",
                            "Unproved paired external/aliased write",
                        )
                    else:
                        size = {"movb": 1, "movw": 2, "movl": 4, "movq": 8}.get(row.op)
                        if row.op == "mov" and len(args) == 2:
                            size = width(args[0])
                        need(
                            size is not None and 0 <= offset and offset + size <= 0x48,
                            "Unbounded or unknown paired spill write width/range",
                        )
                        memory[offset : offset + size] = [None] * size
                        if row.op == "mov" and args[0] in ("%ecx", "%r9d") and offset in PAIRED_LEVEL_SPILLS:
                            value = (cx, r9)[register(args[0])]
                            if value is not None:
                                memory[offset : offset + 4] = value.to_bytes(4, "little")
                        if row.op == "mov" and size == 8 and args[0] in ("%rdi", "%rsi"):
                            value = closure[("%rdi", "%rsi").index(args[0])]
                            if value == "closure":
                                memory[offset : offset + 8] = [("closure", i) for i in range(8)]
            if row.op == "test" and row.args == "%r9d,%r9d" and r9 is not None:
                next_zf = r9 == 0
            schedule(row.next, (values[0], values[1], next_zf, tuple(memory), tuple(next_closure)))
        recursive = [row for row in calls.values() if row["target"] == symbol.name]
        need(
            not recursive if seed == 0 else len(recursive) == 1 and recursive[0]["level"] == seed - 1,
            "Paired recursion is not bounded for every seed",
        )
        need(returns, "Paired seed has no returning path")
        levels[seed] = dict(
            generic,
            calls=sorted(calls.values(), key=lambda row: row["address"]),
            instructions=len(visited),
            returns=len(returns),
            seed=seed,
            private_spill_bytes=0x48,
            caller_saved_killed=True,
            caller_memory_contract=storage is not None,
            established_child_seed=None if seed == 0 else seed - 1,
            identical_closure_forwarding=storage is not None,
        )
    return levels


# Closed image006 instruction contracts. These hashes cover the complete original
# instruction inventories, including unreachable padding. Only independently
# resolved direct-call and RIP-table relocations are normalized. They freeze the
# audited semantics below; neither a matching hash alone nor a selected slice is
# a storage/recursion proof. A new emitted shape requires a new independent audit.
PAIRED_ROOT = (
    "_ZNK6aurora4uefi10PageTables16verify_graphicalEmRKNS0_5BytesEPKNS0_18LocalApicAdmissionEPKNS0_"
    "20FramebufferAdmissionE"
)
PAIRED_GUARD = "_ZN6aurora4uefi10PageTables33paired_graphical_storage_disjointEmmmm"
PAIRED_LAYOUT = "_ZN6aurora4uefi20RuntimeLayoutProfileILm2EE5validEm"
PAIRED_BYTES = "_ZNK6aurora4uefi5Bytes3getEmj"
PAIRED_ENTRY = "_ZNK6aurora4uefi10PageTables5entryEm"
PAIRED_WINDOW = "_ZNK6aurora4uefi10PageTables11window_slotEv.isra.0"
PAIRED_HELPERS = (PAIRED_LAYOUT, PAIRED_BYTES, PAIRED_LEVEL_HELPER, PAIRED_GUARD, PAIRED_ENTRY, PAIRED_WINDOW)
PAIRED_MACHINE_CONTRACTS = {
    PAIRED_ROOT: (2084, 483, "248f70669f871707a268211f3454fd9365a402b01009fbf44f5910d235ad24cf"),
    PAIRED_WALK: (866, 194, "d8867daaaceefeb5d64ef4dcd7c18b14dfe4207f96a24c1c4ac78b12d2bf6458"),
    PAIRED_LAYOUT: (826, 174, "a405c4b6a848938ff414204e852558572acf8627fa0578414e16161a42299d1e"),
    PAIRED_BYTES: (88, 27, "63e95aa6c16e985070d60d833a3973841213d5425306a8449926b75d128bd276"),
    PAIRED_LEVEL_HELPER: (813, 153, "c66fbbbc719273cdaf98d1639ecf89dfa11fb829766cb8bd2c96e10d16a301ba"),
    PAIRED_GUARD: (34, 14, "94a3650c743e0a6f5676c288ae3ad4e987dcc456b22da68e288242a740abf0e2"),
    PAIRED_ENTRY: (132, 37, "80aec290b73bb625358142cbf89e138facfc2ca601e760243e0af2312d444af1"),
    PAIRED_WINDOW: (115, 29, "36367b56b5d8d3a1e36126e10a90fc51eb7a72958fe453ed720786c494cbeb43"),
}
PAIRED_SAVES = ("r15", "r14", "r13", "r12", "rbp", "rbx")
PAIRED_CALLER_SAVED = ("rax", "rcx", "rdx", "rsi", "rdi", "r8", "r9", "r10", "r11")
PAIRED_NO_WRITE = frozenset("cmp cmpb cmpl cmpq cmpw test bt nop nopl nopw cs data16".split())


def paired_rows(symbol, code):
    rows = [row for address, row in sorted(code.items()) if symbol.address <= address < symbol.address + symbol.size]
    cursor = symbol.address
    for row in rows:
        need(row.address == cursor and row.size > 0, "Paired instruction overlap, gap or wrong address")
        cursor = row.next
    need(cursor == symbol.address + symbol.size, "Incomplete paired function instruction extent")
    return rows


def paired_register(operand):
    for root in ("rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rbp", "rsp"):
        stem = root[1:]
        aliases = (
            (root, "e" + stem, stem, stem[0] + "l", stem[0] + "h")
            if root in ("rax", "rbx", "rcx", "rdx")
            else (root, "e" + stem, stem, stem + "l")
        )
        if operand.removeprefix("%") in aliases and operand.startswith("%"):
            return root
    match = re.fullmatch(r"%(r(?:[89]|1[0-5]))[dwb]?", operand)
    return match[1] if match else None


def paired_width(row, args):
    if row.op in ("movb", "movw", "movl", "movq"):
        return {"movb": 1, "movw": 2, "movl": 4, "movq": 8}[row.op]
    need(row.op == "mov" and len(args) == 2, "Unknown paired memory-write semantics")
    source = args[0]
    root = paired_register(source)
    need(root is not None, "Unknown paired store width")
    if source == "%" + root:
        return 8
    if source.startswith("%e") or re.fullmatch(r"%r\d+d", source):
        return 4
    if source in ("%al", "%ah", "%bl", "%bh", "%cl", "%ch", "%dl", "%dh", "%sil", "%dil", "%bpl", "%spl"):
        return 1
    return 1 if source.endswith("b") else 2


def paired_slot(operand):
    match = re.fullmatch(r"(0x[0-9a-f]+)?\(%rsp\)", operand)
    return int(match[1] or "0", 16) if match else None


def paired_machine_inventory(decoder, symbol, code, starts, payload):
    rows = paired_rows(symbol, code)
    inventory = []
    for row in rows:
        raw = payload[row.address : row.next]
        need(len(raw) == row.size, "Truncated paired machine bytes")
        args = row.args
        if row.op == "call":
            target = decoder.target_of(row)
            need(
                row.size == 5
                and raw[:1] == b"\xe8"
                and row.next + int.from_bytes(raw[1:], "little", signed=True) == target
                and target in starts,
                "Paired direct call bytes/target disagree",
            )
            args, raw = starts[target], raw[:1] + b"\0" * 4
        elif row.op in decoder.BRANCHES:
            target = decoder.target_of(row)
            need(
                symbol.address <= target < symbol.address + symbol.size and target in code,
                "Paired branch leaves body or enters instruction interior",
            )
            condition = dict(
                jo=0,
                jno=1,
                jb=2,
                jae=3,
                je=4,
                jne=5,
                jbe=6,
                ja=7,
                js=8,
                jns=9,
                jp=10,
                jnp=11,
                jl=12,
                jge=13,
                jle=14,
                jg=15,
            )
            need(row.op == "jmp" or row.op in condition, "Unreviewed paired branch condition")
            prefixes = (
                (b"\xeb", b"\xe9")
                if row.op == "jmp"
                else (bytes((0x70 + condition[row.op],)), bytes((0x0F, 0x80 + condition[row.op])))
            )
            size = 1 if raw.startswith(prefixes[0]) else 4
            prefix = prefixes[0] if size == 1 else prefixes[1]
            need(
                raw.startswith(prefix)
                and len(raw) == len(prefix) + size
                and row.next + int.from_bytes(raw[-size:], "little", signed=True) == target,
                "Paired branch bytes/condition/target disagree",
            )
            args = hex(target - symbol.address)
        elif "%rip" in row.args:
            match = re.fullmatch(r"(-?0x[0-9a-f]+)\(%rip\),%(rdi|rdx)", row.args)
            need(
                match and row.op == "lea" and row.size == 7 and raw[:3] in (b"\x48\x8d\x3d", b"\x48\x8d\x15"),
                "Unreviewed paired RIP access",
            )
            displacement = int.from_bytes(raw[3:], "little", signed=True)
            need(displacement == int(match[1], 16), "Paired RIP bytes/address disagree")
            target = row.next + displacement
            need(
                0 <= target <= len(payload) - 12 and payload[target : target + 12] == struct.pack("<III", 39, 30, 21),
                "Changed paired read-only page-level table",
            )
            args, raw = "levels[39,30,21],%" + match[2], raw[:3] + b"\0" * 4
        inventory.append([row.address - symbol.address, row.size, row.op, args, raw.hex()])
    return inventory


def paired_exact_machine(decoder, symbols, code, starts, payload):
    need(payload is not None, "Paired snapshot/guard linked storage proof requires exact machine bytes")
    receipts = {}
    for name, (size, count, expected) in PAIRED_MACHINE_CONTRACTS.items():
        need(name in symbols and symbols[name].size == size, "Changed paired audited function size: " + name)
        inventory = paired_machine_inventory(decoder, symbols[name], code, starts, payload)
        actual = hashlib.sha256(canonical(inventory).encode()).hexdigest()
        need(
            len(inventory) == count and actual == expected, "Changed paired audited instruction/byte inventory: " + name
        )
        receipts[name] = dict(bytes=size, instructions=count, normalized_sha256=actual)
    need(len(receipts) == 8, "Incomplete paired audited machine inventory")
    return receipts


def paired_cfg(decoder, symbol, code):
    rows = paired_rows(symbol, code)
    addresses = {row.address for row in rows}
    successors, predecessors = {}, {address: set() for address in addresses}
    for row in rows:
        following = set()
        if row.op in decoder.BRANCHES:
            following.add(decoder.target_of(row))
        if row.op not in ("ret", "jmp"):
            following.add(row.next)
        need(following <= addresses, "Paired CFG leaves its exact body")
        successors[row.address] = following
        for target in following:
            predecessors[target].add(row.address)
    reachable, pending = set(), [symbol.address]
    while pending:
        address = pending.pop()
        if address not in reachable:
            reachable.add(address)
            pending.extend(successors[address])
    dominators = {address: ({address} if address == symbol.address else set(reachable)) for address in reachable}
    changed = True
    while changed:
        changed = False
        for address in sorted(reachable - {symbol.address}):
            incoming = predecessors[address] & reachable
            value = {address} | set.intersection(*(dominators[parent] for parent in incoming))
            if value != dominators[address]:
                dominators[address], changed = value, True
    return successors, predecessors, dominators


def paired_helper_effects(decoder, symbols, code, functions):
    effects = {}
    for name in PAIRED_HELPERS:
        symbol = symbols[name]
        rows = paired_rows(symbol, code)
        need(not functions[name]["calls"] and all(row.op != "call" for row in rows), "Paired helper acquired a call")
        saved = PAIRED_SAVES if name == PAIRED_LAYOUT else (("rbx",) if name == PAIRED_ENTRY else ())
        prologue = [row for row in rows if row.op == "push"]
        need([row.args for row in prologue] == ["%" + value for value in saved], "Changed helper register saves")
        # A per-path save/restore automaton proves preservation, including early
        # layout rejection returns before its conditional prologue.
        successors, _, _ = paired_cfg(decoder, symbol, code)
        states, pending = {symbol.address: ((), 0)}, [symbol.address]
        stores = []
        while pending:
            address = pending.pop()
            row = code[address]
            stack, allocation = states[address]
            args = decoder.arguments(row.args)
            if row.op == "push":
                need(args == ["%" + saved[len(stack)]] and not allocation, "Unbalanced paired helper save")
                stack += (args[0],)
            elif row.op == "pop":
                need(stack and args == [stack[-1]] and not allocation, "Unbalanced paired helper restore")
                stack = stack[:-1]
            elif args[-1:] == ["%rsp"] and row.op in ("sub", "add"):
                need(
                    name == PAIRED_LAYOUT and row.args == "$0xb8,%rsp" and len(stack) == 6,
                    "Unknown helper stack allocation",
                )
                need(allocation == (0 if row.op == "sub" else 0xB8), "Changed helper private-frame lifetime")
                allocation = 0xB8 if row.op == "sub" else 0
            elif row.op == "ret":
                need(not stack and not allocation, "Helper returns without restoring its caller")
            elif row.op not in PAIRED_NO_WRITE | decoder.BRANCHES:
                need(
                    row.op
                    in {
                        "mov",
                        "movabs",
                        "movq",
                        "movzbl",
                        "lea",
                        "xor",
                        "and",
                        "or",
                        "sub",
                        "add",
                        "shl",
                        "shr",
                        "setae",
                        "cmovae",
                    },
                    "Unknown paired helper effect",
                )
                destination = paired_register(args[-1])
                need(destination != "rsp", "Unknown helper stack write")
                if destination in PAIRED_SAVES:
                    need("%" + destination in stack, "Paired helper clobbers an unsaved callee register")
                if "(" in args[-1]:
                    slot = paired_slot(args[-1])
                    width = paired_width(row, args)
                    need(
                        name == PAIRED_LAYOUT
                        and allocation == 0xB8
                        and slot is not None
                        and 0 <= slot
                        and slot + width <= allocation,
                        "Paired helper writes caller/unknown memory",
                    )
                    stores.append((address, slot, width))
            state = stack, allocation
            for target in successors[address]:
                if target in states:
                    need(states[target] == state, "Helper stack preservation disagrees at CFG join")
                else:
                    states[target] = state
                    pending.append(target)
        # Classify even unreachable instructions; exact machine coverage prevents
        # hidden stores in ignored padding and the reachable pass checks lifetime.
        all_stores = [
            row.address
            for row in rows
            if decoder.arguments(row.args)[-1:]
            and "(" in decoder.arguments(row.args)[-1]
            and row.op not in PAIRED_NO_WRITE | decoder.BRANCHES
        ]
        need(set(all_stores) == {address for address, _, _ in stores}, "Unclassified paired helper memory write")
        effects[name] = dict(
            caller_memory_writes=0,
            private_stores=sorted(set(stores)),
            callee_saved_preserved=list(PAIRED_SAVES),
            calls=0,
        )
    return effects


def paired_require_slice(symbol, code, offset, operations):
    address = symbol.address + offset
    for operation in operations:
        row = code.get(address)
        need(row is not None and (row.op, row.args) == operation, "Changed paired protected instruction slice")
        address = row.next
    return address


def paired_root_storage(decoder, symbols, code, starts, functions):
    symbol = symbols[PAIRED_ROOT]
    rows = paired_rows(symbol, code)
    begin = symbol.address
    saves = [("push", "%" + register) for register in PAIRED_SAVES]
    paired_require_slice(symbol, code, 0, saves + [("sub", "$0xb8,%rsp")])
    paired_require_slice(
        symbol,
        code,
        0x11,
        [
            ("mov", "(%rdi),%r13"),
            ("mov", "0x8(%rdi),%r12"),
            ("mov", "0x10(%rdi),%rax"),
            ("mov", "%rsi,0x28(%rsp)"),
            ("mov", "%rcx,0x20(%rsp)"),
            ("mov", "%r8,0x18(%rsp)"),
            ("mov", "%r13,0x48(%rsp)"),
            ("mov", "%r12,0x50(%rsp)"),
            ("mov", "%rax,0x58(%rsp)"),
        ],
    )
    paired_require_slice(
        symbol,
        code,
        0x6A2,
        [("add", "$0xb8,%rsp")] + [("pop", "%" + r) for r in reversed(PAIRED_SAVES)] + [("ret", "")],
    )
    # The three observed qwords are captured before ANY store after the prologue.
    # Initial callee saves precede the observation interval and are not reused as
    # descriptor-field values. Field validation is pinned and dominates walking.
    successors, predecessors, dominators = paired_cfg(decoder, symbol, code)
    rootcall, bitmap_store = begin + 0x646, begin + 0x624
    captures = {begin + offset for offset in (0x11, 0x14, 0x18, 0x2B, 0x30, 0x35)}
    need(captures <= dominators[rootcall], "Partial or bypassed paired snapshot capture")
    required = {begin + offset for offset in (0x74, 0x79, 0x7D, 0x83, 0x85, 0x8B, 0x8F, 0x95, 0x98)}
    need(required <= dominators[rootcall], "Paired used/base/arena validation does not dominate root call")
    paired_require_slice(symbol, code, 0x74, [("lea", "-0x1(%r12),%rdx"), ("cmp", "$0xf,%rdx")])
    need(
        code[begin + 0x7D].op == "ja" and decoder.target_of(code[begin + 0x7D]) == begin + 0x6A0,
        "Paired snapshot used count lacks unsigned 1..16 rejection",
    )
    paired_require_slice(symbol, code, 0x8B, [("mov", "(%rsp),%rax"), ("add", "$0x11000,%rax"), ("cmp", "%rax,%r13")])
    need(
        code[begin + 0x98].op == "jne" and decoder.target_of(code[begin + 0x98]) == begin + 0x6A0,
        "Paired snapshot base is not the admitted arena table base",
    )
    objects = dict(bitmap=(0x38, 16), snapshot=(0x48, 24), helper_closure=(0x60, 24), closure=(0x78, 56))
    intervals = sorted((start, start + size) for start, size in objects.values())
    need(
        all(0 <= start < end <= 0xB8 for start, end in intervals)
        and all(left[1] <= right[0] for left, right in zip(intervals, intervals[1:])),
        "Paired protected root objects overlap or escape the real frame",
    )
    construction = {
        0x2B: (0x48, "captured_base"),
        0x30: (0x50, "captured_used"),
        0x35: (0x58, "captured_framebuffer"),
        0x51B: (0x88, ("frame", 0x60)),
        0x530: (0x60, ("frame", 0x30)),
        0x53F: (0x90, ("frame", 0x20)),
        0x551: (0x98, ("frame", 0x18)),
        0x55C: (0x68, "bytes"),
        0x561: (0x70, ("frame", 0x28)),
        0x566: (0x78, ("frame", 0x48)),
        0x56B: (0x80, ("frame", 0x38)),
        0x573: (0xA0, ("frame", 0x28)),
        0x57B: (0xA8, "bytes"),
    }
    guard_calls = (0x583, 0x5A0, 0x5BD, 0x5DA, 0x5F7, 0x614)
    guard_args = (
        ("original", 24, ("frame", 0x38), 16),
        ("original", 24, ("frame", 0x48), 24),
        ("original", 24, ("frame", 0x78), 56),
        (("frame", 0x48), 24, ("frame", 0x38), 16),
        (("frame", 0x48), 24, ("frame", 0x78), 56),
        (("frame", 0x38), 16, ("frame", 0x78), 56),
    )
    guard_states = dict(zip(guard_calls, guard_args))
    for offset in guard_calls:
        row = code[begin + offset]
        test = code[row.next]
        branch = code[test.next]
        need(
            row.op == "call"
            and starts.get(decoder.target_of(row)) == PAIRED_GUARD
            and (test.op, test.args) == ("test", "%al,%al")
            and branch.op == "je"
            and decoder.target_of(branch) == begin + 0x6A0,
            "Paired guard does not reject its false result",
        )
        need(
            {row.address, test.address, branch.address, branch.next} <= dominators[bitmap_store]
            and branch.next in dominators[rootcall],
            "Paired bitmap write/walk bypasses a successful storage guard",
        )
    paired_require_slice(
        symbol,
        code,
        0x621,
        [
            ("mov", "%r13,%rax"),
            ("movb", "$0x0,(%rax)"),
            ("add", "$0x1,%rax"),
            ("cmp", "%r12,%rax"),
        ],
    )
    loop = code[begin + 0x62E]
    need(
        loop.op == "jne"
        and decoder.target_of(loop) == bitmap_store
        and predecessors[bitmap_store] == {begin + 0x621, loop.address},
        "Paired bitmap initialization has an unbounded/bypassing loop",
    )
    paired_require_slice(
        symbol,
        code,
        0x630,
        [
            ("mov", "0x48(%rsp),%rbx"),
            ("xor", "%r8d,%r8d"),
            ("mov", "$0x3,%ecx"),
            ("mov", "%r15,%rsi"),
            ("mov", "%r15,%rdi"),
            ("mov", "%rbx,%rdx"),
        ],
    )
    # Symbolic pointer/capture lineage with byte-granular local slots. Facts meet
    # conservatively at every CFG join. Arithmetic invalidates origins; exact
    # loop contracts below summarize only the two bounded bitmap loops.
    initial = {name: None for name in (*PAIRED_CALLER_SAVED, *PAIRED_SAVES)}
    initial.update(rdi="original", rdx="bytes", rsi="arena", rcx="lapic", r8="framebuffer")
    registers = tuple(initial)
    initial = tuple(initial[name] for name in registers)
    states, pending = {begin: (initial, (None,) * 0xB8)}, [begin]
    observed_stores, observed_calls, constructed = {}, {}, set()

    def schedule(address, regs, memory):
        state = tuple(regs[name] for name in registers), tuple(memory)
        prior = states.get(address)
        if prior is not None:
            state = (
                tuple(a if a == b else None for a, b in zip(prior[0], state[0])),
                tuple(a if a == b else None for a, b in zip(prior[1], state[1])),
            )
            if state == prior:
                return
        states[address] = state
        pending.append(address)

    def remembered(memory, slot, size=8):
        parts = memory[slot : slot + size]
        if len(parts) == size and all(
            part is not None and part == (parts[0][0], index) for index, part in enumerate(parts)
        ):
            return parts[0][0]
        return None

    while pending:
        address = pending.pop()
        row, offset = code[address], address - begin
        regs, memory = states[address]
        regs, memory = dict(zip(registers, regs)), list(memory)
        args = decoder.arguments(row.args)
        if row.op == "ret":
            continue
        # Every field load from original-this belongs to the single observation
        # interval. No helper may subsequently receive it except as guard integer.
        for operand in args:
            for used in re.findall(r"%[a-z0-9]+", operand):
                if "(" in operand and regs.get(paired_register(used)) == "original":
                    need(
                        offset in (0x11, 0x14, 0x18) and used == "%rdi" and operand == args[0],
                        "Late original descriptor read or aliased original receiver",
                    )
        if row.op == "call":
            target = starts.get(decoder.target_of(row))
            need(target in (*PAIRED_HELPERS, PAIRED_WALK), "Unknown root helper effect")
            if target == PAIRED_GUARD:
                values = tuple(regs[name] for name in ("rdi", "rsi", "rdx", "rcx"))
                need(
                    offset in guard_states and values == guard_states[offset],
                    "Wrong storage guard object/extent/lineage",
                )
            elif target == PAIRED_WALK:
                need(
                    offset == 0x646
                    and (regs["rdi"], regs["rsi"], regs["rdx"], regs["rcx"], regs["r8"])
                    == (("frame", 0x78), ("frame", 0x78), "captured_base", 3, 0),
                    "Paired external root lacks snapshot/closure/level-three provenance",
                )
                for slot, value in ((0x78, ("frame", 0x48)), (0x80, ("frame", 0x38)), (0x88, ("frame", 0x60))):
                    need(remembered(memory, slot) == value, "Wrong paired immutable closure field")
            elif target == PAIRED_ENTRY:
                need(regs["rdi"] == ("frame", 0x48), "Paired member receiver is not the immutable snapshot")
            elif target == PAIRED_WINDOW:
                need(
                    (regs["rdi"], regs["rsi"]) == ("captured_base", "captured_used"),
                    "Paired scalarized window receiver lacks snapshot provenance",
                )
            else:
                need(
                    not any(
                        regs[name] == "original" or isinstance(regs[name], tuple)
                        for name in ("rdi", "rsi", "rdx", "rcx", "r8", "r9")
                    ),
                    "Paired private/original address escapes to an unrelated helper",
                )
            observed_calls[address] = target
            for name in PAIRED_CALLER_SAVED:
                regs[name] = None
        elif row.op in ("push", "pop"):
            need(offset < 0xA or 0x6A9 <= offset <= 0x6B1, "Unexpected root save/restore inside lifetime")
            if row.op == "pop":
                regs[paired_register(args[0])] = None
        elif args[-1:] == ["%rsp"]:
            need(
                offset in (0xA, 0x6A2) and row.op in ("sub", "add"), "Paired root frame moves during protected lifetime"
            )
        elif row.op not in PAIRED_NO_WRITE | decoder.BRANCHES and not (row.op == "xchg" and row.args == "%ax,%ax"):
            value, destination = None, paired_register(args[-1])
            if row.op in ("mov", "movabs") and len(args) == 2:
                source = paired_register(args[0])
                if args[0].startswith("$"):
                    value = int(args[0][1:], 16)
                elif source and args[0] == "%" + source:
                    value = regs[source]
                elif offset in (0x11, 0x14, 0x18):
                    value = {0x11: "captured_base", 0x14: "captured_used", 0x18: "captured_framebuffer"}[offset]
                elif paired_slot(args[0]) is not None:
                    value = remembered(memory, paired_slot(args[0]))
            elif row.op == "lea" and paired_slot(args[0]) is not None:
                value = ("frame", paired_slot(args[0]))
            elif row.op == "xor" and len(args) == 2 and args[0] == args[1]:
                value = 0
            if "(" in args[-1]:
                slot, width = paired_slot(args[-1]), paired_width(row, args)
                if slot is None:
                    need(
                        address == bitmap_store and (row.op, row.args) == ("movb", "$0x0,(%rax)"),
                        "Unclassified root external/aliased write",
                    )
                    need(
                        regs["r13"] == ("frame", 0x38) and regs["r12"] == ("frame", 0x48),
                        "Bitmap loop loses its exact [0,16) bounds",
                    )
                    observed_stores[address] = dict(object="bitmap", offset=0x38, bytes=16)
                else:
                    need(0 <= slot and slot + width <= 0xB8, "Root write escapes allocated frame")
                    overlap = [
                        name for name, (first, size) in objects.items() if slot < first + size and first < slot + width
                    ]
                    if overlap:
                        need(
                            offset in construction and width == 8 and construction[offset] == (slot, value),
                            "Root spill overlaps or changes immutable snapshot/closure",
                        )
                        constructed.add(offset)
                    memory[slot : slot + width] = [
                        (value, index) if value is not None else None for index in range(width)
                    ]
                    observed_stores[address] = dict(
                        object=overlap[0] if overlap else "private_scalar", offset=slot, bytes=width
                    )
            elif destination:
                # Partial writes destroy pointer provenance. Zero-extending
                # immediates/zero are scalar constants, never preserved pointers.
                regs[destination] = value if args[-1] == "%" + destination or isinstance(value, int) else None
            else:
                need(False, "Unknown paired root destination/effect")
        if offset == 0x659:
            # The inventory exit is taken only when its integer counter equals
            # the captured used count. This fact is used as window_slot's second
            # scalarized receiver; it is not assumed to survive any call.
            need(
                row.op == "je"
                and decoder.target_of(row) == begin + 0x6B4
                and code[begin + 0x64F].args == "0x50(%rsp),%rax"
                and code[begin + 0x656].args == "%rdx,%rax",
                "Changed postwalk used-count equality",
            )
            branch_regs = dict(regs, rdx="captured_used")
            schedule(begin + 0x6B4, branch_regs, memory)
            schedule(row.next, regs, memory)
        else:
            for target in successors[address]:
                schedule(target, regs, memory)
    need(
        constructed == set(construction) and {begin + offset for offset in construction} <= dominators[rootcall],
        "Missing or bypassed immutable paired object initialization",
    )
    all_stores = {
        row.address
        for row in rows
        if "(" in decoder.arguments(row.args)[-1] and row.op not in PAIRED_NO_WRITE | decoder.BRANCHES
    }
    need(all_stores == set(observed_stores), "Root contains an unclassified/unreachable memory write")
    need(
        set(observed_calls) == {call["address"] for call in functions[PAIRED_ROOT]["calls"]},
        "Root call inventories disagree",
    )
    external = [
        (name, call)
        for name, function in functions.items()
        for call in function["calls"]
        if call["target"] == PAIRED_WALK and name != PAIRED_WALK
    ]
    need(
        len(external) == 1
        and external[0][0] == PAIRED_ROOT
        and external[0][1]["address"] == rootcall
        and external[0][1]["kind"] == "call"
        and external[0][1]["level"] == 3,
        "Unexpected paired walker external caller or entry level",
    )
    return dict(
        symbol=PAIRED_ROOT,
        frame_bytes=0xB8,
        objects=objects,
        coherent_capture_qwords=3,
        postwalk_conditional_on_bounded_walker=True,
        guards=[begin + offset for offset in guard_calls],
        bitmap_initialization=bitmap_store,
        rootcall=rootcall,
        stores=observed_stores,
        snapshot_member_receivers=6,
        original_descriptor_integer_only=True,
    )


def paired_walker_storage(decoder, symbol, code, starts):
    rows = paired_frame_envelope(decoder, symbol, code)
    begin = symbol.address
    successors, predecessors, dominators = paired_cfg(decoder, symbol, code)
    # Original machine sequence: the descriptor comes only from closure[0], and
    # closure[8] is the root bitmap. Root validation gave 1 <= used <= 16 and a
    # page-aligned arena+0x11000 base below 2**32; hence end cannot overflow and
    # (table-base)>>12 is in [0,15]. All rejection edges go to the false return.
    prefix = [
        ("mov", "(%rdi),%rax"),
        ("mov", "%rdi,0x8(%rsp)"),
        ("mov", "(%rax),%rdx"),
        ("cmp", "%rdx,%r11"),
        ("jb", 0x200),
        ("mov", "0x8(%rax),%rax"),
        ("shl", "$0xc,%rax"),
        ("add", "%rdx,%rax"),
        ("cmp", "%rax,%r11"),
        ("jae", 0x200),
        ("test", "$0xfff,%r11d"),
        ("jne", 0x200),
        ("mov", "%r11,%rax"),
        ("sub", "%rdx,%rax"),
        ("mov", "0x8(%rsp),%rdx"),
        ("shr", "$0xc,%rax"),
        ("mov", "0x8(%rdx),%rdx"),
        ("cmpb", "$0x0,(%rdx,%rax,1)"),
        ("jne", 0x200),
        ("movb", "$0x1,(%rdx,%rax,1)"),
    ]
    address, protected = begin + 0x11, []
    for op, args in prefix:
        row = code[address]
        need(
            row.op == op and (decoder.target_of(row) == begin + args if isinstance(args, int) else row.args == args),
            "Changed bounded visited-index/snapshot instruction",
        )
        protected.append(address)
        address = row.next
    bitmap_store = protected[-1]
    need(
        bitmap_store == begin + 0x63 and set(protected[:-1]) <= dominators[bitmap_store],
        "Paired visited write bypasses a bounds/alignment check",
    )
    for previous, address in zip(protected, protected[1:]):
        need(predecessors[address] == {previous}, "Entry into middle of paired visited bounds proof")
    child = begin + 0x320
    need(bitmap_store in dominators[child], "Paired child bypasses visited storage proof")
    # Conditional local transformer, not a child memory proof: assuming smaller
    # descendants preserve caller memory, the known root closure reaches both
    # self arguments. The ascending engine below discharges that assumption at
    # each actual seed and rechecks pointer forwarding. Full-width spills retain
    # byte tags; every overlapping partial/wide write destroys those tags.
    initial = {name: None for name in (*PAIRED_CALLER_SAVED, *PAIRED_SAVES)}
    initial.update(rdi="closure", rsi="closure")
    registers = tuple(initial)
    states = {begin: (tuple(initial[name] for name in registers), (None,) * 0x48)}
    pending, calls, stores = [begin], set(), set()

    def schedule(address, regs, memory):
        state = tuple(regs[name] for name in registers), tuple(memory)
        prior = states.get(address)
        if prior is not None:
            state = (
                tuple(a if a == b else None for a, b in zip(prior[0], state[0])),
                tuple(a if a == b else None for a, b in zip(prior[1], state[1])),
            )
            if state == prior:
                return
        states[address] = state
        pending.append(address)

    while pending:
        address = pending.pop()
        row = code[address]
        regs, memory = states[address]
        regs, memory = dict(zip(registers, regs)), list(memory)
        args = decoder.arguments(row.args)
        if row.op == "ret":
            continue
        if row.op == "call":
            target = starts.get(decoder.target_of(row))
            if target == symbol.name:
                need(
                    address == child and regs["rdi"] == regs["rsi"] == "closure",
                    "Paired child closure is unknown, clobbered or not forwarded identically",
                )
            else:
                need(target == PAIRED_LEVEL_HELPER, "Unproved paired helper write contract")
                need(regs["rdi"] != "closure" and regs["rsi"] != "closure", "Paired closure escapes to scalar helper")
            calls.add(address)
            for name in PAIRED_CALLER_SAVED:
                regs[name] = None
        elif row.op not in PAIRED_NO_WRITE | decoder.BRANCHES:
            destination, value = paired_register(args[-1]), None
            if row.op == "mov" and len(args) == 2:
                source = paired_register(args[0])
                if source is not None and args[0] == "%" + source:
                    value = regs[source]
                slot = paired_slot(args[0])
                if slot is not None:
                    parts = memory[slot : slot + 8]
                    if parts == [("closure", index) for index in range(8)]:
                        value = "closure"
            if "(" in args[-1]:
                slot = paired_slot(args[-1])
                if slot is None:
                    need(address == bitmap_store, "Unclassified paired walker external/aliased write")
                else:
                    width = paired_width(row, args)
                    need(0 <= slot and slot + width <= 0x48, "Paired private spill escapes allocation")
                    memory[slot : slot + width] = [(value, index) if value else None for index in range(width)]
                stores.add(address)
            elif destination and destination != "rsp":
                regs[destination] = value if args[-1] == "%" + destination else None
        for target in successors[address]:
            schedule(target, regs, memory)
    need(calls == {row.address for row in rows if row.op == "call"}, "Incomplete paired walker call effect proof")
    need(
        stores
        == {
            row.address
            for row in rows
            if "(" in decoder.arguments(row.args)[-1] and row.op not in PAIRED_NO_WRITE | decoder.BRANCHES
        },
        "Unclassified paired walker write",
    )
    return dict(
        bitmap_store=bitmap_store,
        bitmap_index=[0, 15],
        private_spill_bytes=0x48,
        conditional_on_smaller_seed=True,
        stores=sorted(stores),
        calls=sorted(calls),
    )


def paired_linked_storage(decoder, functions, symbols, code, starts, payload):
    inventory = paired_exact_machine(decoder, symbols, code, starts, payload)
    helpers = paired_helper_effects(decoder, symbols, code, functions)
    root = paired_root_storage(decoder, symbols, code, starts, functions)
    walker = paired_walker_storage(decoder, symbols[PAIRED_WALK], code, starts)
    # Each descendant saves six qwords and allocates 72 bytes below its incoming
    # return address. Its only caller-memory write is within the root bitmap.
    # Read-only helpers and bounded private helper frames cannot reach caller
    # objects, even if input reads alias caller frames. No frame-address escape
    # is admitted by paired_frame_envelope. Ascending induction can now preserve
    # spill facts, snapshot, closure and the bitmap base across a proven child.
    return dict(machine=inventory, helpers=helpers, root=root, walker=walker)


def paired_recursion_proofs(decoder, functions, symbols, code, starts, paired_walk, payload=None):
    legacy = decoder.WALK
    need(
        paired_walk != legacy and {legacy, paired_walk} <= set(functions), "Two separate concrete page walkers required"
    )
    # The original legacy contract remains authoritative and unchanged.
    legacy_levels, legacy_roots = decoder.recursion_proof(functions, symbols, code, starts)
    need(paired_walk == PAIRED_WALK, "Unknown concrete paired walker identity")
    storage = paired_linked_storage(decoder, functions, symbols, code, starts, payload)
    paired_readonly_leaf(decoder, PAIRED_LEVEL_HELPER, symbols, code, functions)
    levels = paired_level_induction(
        decoder,
        symbols[paired_walk],
        code,
        starts,
        functions[paired_walk],
        (storage["walker"]["bitmap_store"],),
        storage=storage,
    )
    return dict(
        legacy=dict(symbol=legacy, levels=legacy_levels, roots=legacy_roots),
        paired=dict(
            symbol=paired_walk,
            levels=levels,
            storage=storage,
            roots=[dict(caller=PAIRED_ROOT, address=storage["root"]["rootcall"], initial_level=3)],
        ),
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


# GCC's source-specific lambda signatures accompany the two exact linkage
# names above; no general ELF alias or signature normalization is admitted.
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
    original_code = dict(code)
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
            raise ValueError(unreviewed_linked_function(symbol, original_code, payload, error)) from error
    console.verify_noreturn(functions, decoder.NORETURN)
    verify_bridge_body(decoder, body(linked.functions[BRIDGE]), starts)
    private_abi = verify_private_abi(decoder, linked, code, starts, language.functions, functions)
    proofs = paired_recursion_proofs(decoder, functions, linked.functions, code, starts, paired_walk, payload)
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


def image_evidence(directory, mode):
    fixture_source = capture_source_evidence(mode)
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
    fixture_artifacts = {}
    for name in CAPTURE_ARTIFACTS:
        path = directory / name
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
        capture_fixture=dict(source=fixture_source, artifacts=capture_artifact_evidence(mode, fixture_artifacts)),
    )


def emit(mode):
    RECEIPT.unlink(missing_ok=True)
    record = provenance(mode)
    result = dict(
        schema="aurora-graphical-console-admission-v2",
        status="requires-independent-review",
        mode=mode,
        clock="tcg-original-clock",
        build=record,
        image=image_evidence(BUILD, mode),
        stack=stack_evidence(BUILD),
    )
    require_capture_linked_proof(mode)
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
        receipt["schema"] == "aurora-graphical-console-admission-v2"
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
        canonical(receipt["image"]) == canonical(image_evidence(BUILD, mode))
        and canonical(receipt["stack"]) == canonical(stack_evidence(BUILD)),
        "Receipt image/stack evidence differs from fresh combined proof",
    )
    require_capture_linked_proof(mode)
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
            "source",
        ),
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
    elif args.action == "source":
        print(json.dumps(capture_source_evidence(args.mode), indent=2, sort_keys=True))
    else:
        checked(args.mode)
        print("Verified current combined receipt identity; independent qualification not claimed.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        raise SystemExit("FAIL: graphical Console admission: " + str(error)) from error
