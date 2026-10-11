#!/usr/bin/env python3
"""Bounded graphical Console image, stack and capture-structure admission.

The native build graph supplies the measured artifacts and their dependencies.
These checks do not prove arbitrary machine safety or capture behavior; hosted
and guest behavior gates and independent review remain separate requirements.
"""

from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/uefi"
RECEIPT = BUILD / "graphical-console-admission.json"
MODES = ("graphical-console", "graphical-console-capture")
ENTRY = "__au_v_m1_24kernel_graphical_console_n0__d17graphical_console"
CPP_ENTRY = "_ZN6aurora4uefi21run_graphical_consoleEmRKNS0_5BytesE"
BRIDGE = "__au_runtime_graphical_entry"
VALUE_BRIDGE = "__au_runtime_graphical_value"
VALUE_ENTRY = "aurora_kernel_value"
HOST_IMPORTS = frozenset(("__au_runtime_console_next", "__au_runtime_console_put", "__au_runtime_display_pixel"))
COMMON_CPP_OBJECTS = ("payload", "acpi", "pci", "runtime")
CPP_OBJECTS = COMMON_CPP_OBJECTS + ("graphical-console",)
COMMON_ASSEMBLY_OBJECTS = ("payload-entry", "language", "memory")
ASSEMBLY_OBJECTS = ("payload-entry", "console-entry", "language", "memory")


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


def configure_paths(build_dir, source_root=None):
    global ROOT, BUILD, RECEIPT
    common.configure_paths(build_dir, source_root or ROOT)
    ROOT, BUILD = common.ROOT, common.BUILD
    RECEIPT = BUILD / "graphical-console-admission.json"
    console.configure_paths(BUILD, ROOT)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


read_json = common.read_json

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
    reflection = common.stack_facts.reflection_inventory(language_names)
    need(
        {name for name in linked_names if name.startswith(("aurora_reflect_", "__au_reflect_"))} == reflection
        and not reflection.intersection(set(frames) | set(memory_names)),
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


LANGUAGE_ROOTS = frozenset(
    (
        ENTRY,
        BRIDGE,
        VALUE_BRIDGE,
        VALUE_ENTRY,
        "__au_f_m2_8graphics7font5x7_n1_8graphics_d10glyph_bits",
        "graphical_glyph_bits",
    )
)


def verify_language_object(language):
    imports = {row.name for row in language.symbols if row.name and row.section == 0}
    need(
        imports == {"__au_runtime_console_next", "__au_runtime_display_pixel"},
        "Unexpected generated language import inventory",
    )
    need(
        LANGUAGE_ROOTS <= set(language.functions),
        "Missing generated language entry/bridge inventory",
    )
    reflection = common.stack_facts.reflection_inventory(language.functions)
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
                if name in reflection
                else ("LOCAL", "DEFAULT")
            ),
            "Generated function escaped private ELF binding: " + name,
        )
    return sorted(imports)


def verify_private_abi(decoder, linked, code, starts, language_names, functions):
    def body(name):
        symbol = linked.functions[name]
        return [
            row for address, row in sorted(code.items()) if symbol.address <= address < symbol.address + symbol.size
        ]

    value_body = body(VALUE_BRIDGE)
    verify_value_bridge_body(decoder, value_body, starts)
    # Generated entry copies and scalar completion checks belong to trusted
    # compiler lowering. The native record and host contract remain independent.
    expected_record = dict(
        parameters=[["builtin::ConsoleSession", 16], ["builtin::DisplaySession", 16], ["scalar", 8], ["scalar", 8]],
        result_bytes=8,
    )
    need(
        (functions[ENTRY].get("service_abi") or {}).get("record") == expected_record,
        "Changed native paired service record",
    )
    pixel_sites = []
    for name in language_names:
        sites = [row for row in functions[name]["calls"] if row["target"] == "__au_runtime_display_pixel"]
        if not sites:
            continue
        fact = (functions[name].get("service_abi") or {}).get("calls", {}).get("__au_runtime_display_pixel")
        need(fact == dict(sysv_arguments=7, result_max=1), "Changed native pixel service ABI")
        for site in sites:
            need(site["live_bytes"] % 16 == 0, "Misaligned pixel SysV host call")
            pixel_sites.append(dict(function=name, address=site["address"], live_bytes=site["live_bytes"]))
    need(pixel_sites, "No concrete Display pixel host call")
    return dict(
        entry_record=expected_record,
        pixel_sites=pixel_sites,
        value_bridge=dict(symbol=VALUE_BRIDGE, entry=VALUE_ENTRY),
        generated_abi_basis="compiler service facts bound to object bytes and linked call edges",
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
    decoder = load("graphical_stack_decoder", ROOT / "scripts/kernel_stack.py")
    decoder.CPP_OBJECTS = CPP_OBJECTS
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
    payload = (directory / "payload.bin").read_bytes()
    body = lambda symbol: [r for a, r in sorted(code.items()) if symbol.address <= a < symbol.address + symbol.size]
    verify_irq_body(decoder, body(linked.functions[irq.name]), starts)
    language, memory = (decoder.Elf(directory / "objects" / (name + ".o")) for name in ("language", "memory"))
    for obj in (language, memory):
        for symbol in obj.functions.values():
            decoder.associate_object(linked, obj, symbol)
    assembly = [item for name in ASSEMBLY_OBJECTS for item in decoder.linked_assembly(linked, directory, name)]
    verify_inventory(linked.functions, frames, language.functions, memory.functions)
    language_imports = verify_language_object(language)
    reflection = common.verify_reflection_image(directory)
    decoder.NORETURN = frozenset(
        name
        for name in linked.functions
        if name == "uefi_payload_fail"
        or "4failE" in name
        or "21run_graphical_consoleE" in name
        or "23graphical_console_faultE" in name
    )
    functions = decoder.compiled_stack_functions(
        directory, linked, language, code, starts, frames, compiler_edges, (BRIDGE, VALUE_BRIDGE)
    )
    functions.update(
        decoder.assembly_stack_functions(
            linked.functions,
            code,
            starts,
            set(memory.functions)
            | {
                BRIDGE,
                VALUE_BRIDGE,
                "uefi_payload_entry",
                "uefi_payload_fault",
                "uefi_payload_page_fault",
                "fault_common",
            },
        )
    )
    console.verify_noreturn(functions, decoder.NORETURN)
    verify_bridge_body(decoder, body(linked.functions[BRIDGE]), starts)
    private_abi = verify_private_abi(decoder, linked, code, starts, language.functions, functions)
    # Four local traversal slots replace the former recursive source contract.
    # Metadata-based C++ bounds admit no call cycles.
    for name in functions:
        common.graph_peak(functions, name)
    normal = common.graph_peak(functions, "uefi_payload_entry")
    session = common.graph_peak(functions, ENTRY)
    fault = 48 + max(
        common.graph_peak(functions, name)["peak"] for name in ("uefi_payload_fault", "uefi_payload_page_fault")
    )
    dispatch = common.graph_peak(functions, "uefi_console_interrupt_dispatch")
    irq_peak = 176 + 15 + dispatch["peak"]
    owner, irq_reachable = verify_wait_closure(code, named, functions, language.functions, payload, linked.functions)
    need(owner not in irq_reachable, "IRQ reaches interruptible wait")
    retained_paths = verify_retained_wait_paths(functions, owner)
    waiting = common.graph_peak(functions, "uefi_payload_entry", target=owner)
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
        "language.stack.json",
        "embed.S",
        "image-metadata.json",
    ]
    if mode != "normal":
        names += ["console-poll-metadata.json"]
    names += [name + ".o" for name in cpp + assembly + ("loader", "embed", "transition")]
    names += [name + suffix for name in cpp + ("loader",) for suffix in (".su", ".ci")]
    names += [name + "-pe.o" for name in ("loader", "memory", "embed", "transition")]
    return common.build_artifacts(names)


def image_evidence(directory, mode):
    need(mode in MODES, "Unknown graphical profile")
    image = load("graphical_image_decoder", ROOT / "scripts/kernel_uefi_image.py")
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
    need(mode in MODES, "Unsupported graphical console profile")
    before = common.hashes(build_files())
    result = dict(
        schema="aurora-graphical-console-admission-v6",
        status="requires-independent-review",
        mode=mode,
        clock="tcg-original-clock",
        image=image_evidence(BUILD, mode),
        stack=stack_evidence(BUILD),
    )
    require_capture_structure(mode, result["stack"].get("capture_fixture"))
    common.write_admission(RECEIPT, result, build_files(), before)
    print("PASS: bounded image/stack/structure checks; independent review and hosted/guest behavior gates required")
    return result


def checked(mode):
    need(mode in MODES, "Unsupported graphical console profile")
    receipt = common.check_admission(RECEIPT, "aurora-graphical-console-admission-v6", mode, build_files())
    current_image, current_stack = image_evidence(BUILD, mode), stack_evidence(BUILD)
    need(
        canonical(receipt["image"]) == canonical(current_image)
        and canonical(receipt["stack"]) == canonical(current_stack),
        "Receipt image/stack evidence differs from fresh combined proof",
    )
    require_capture_structure(mode, current_stack.get("capture_fixture"))
    return receipt


def main():
    parser = argparse.ArgumentParser()
    common.path_arguments(parser)
    parser.add_argument("action", choices=("emit", "checked", "diagnose"))
    parser.add_argument("--mode", required=True, choices=MODES)
    args = parser.parse_args()
    configure_paths(args.build_dir or args.source_root / "build/uefi", args.source_root)
    if args.action == "emit":
        emit(args.mode)
    elif args.action == "diagnose":
        print(json.dumps(stack_evidence(BUILD), indent=2, sort_keys=True))
    else:
        checked(args.mode)
        print("PASS: current image admission; independent qualification not claimed.")


if __name__ == "__main__":
    try:
        main()
    except common.Blocked as error:
        print("BLOCKED: " + str(error), file=sys.stderr)
        raise SystemExit(2) from error
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        raise SystemExit("FAIL: graphical Console admission: " + str(error)) from error
