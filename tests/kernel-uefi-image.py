#!/usr/bin/env python3
"""PE32+ relocation/permission and independently linked PIC payload verifier."""

from pathlib import Path
import hashlib
import importlib.util
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/uefi"

spec = importlib.util.spec_from_file_location(
    "image_admission_common", ROOT / "scripts/kernel_program_console_admission.py"
)
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)


def need(value, reason):
    if not value:
        raise ValueError(reason)


def u(data, offset, size):
    need(0 <= offset <= len(data) and 0 < size <= len(data) - offset, "Truncated integer")
    return int.from_bytes(data[offset : offset + size], "little")


def pe_validate(data, payload):
    need(data[:2] == b"MZ", "DOS signature")
    nt = u(data, 60, 4)
    need(data[nt : nt + 4] == b"PE\0\0", "PE signature")
    need(u(data, nt + 4, 2) == 0x8664, "Wrong PE architecture")
    count = u(data, nt + 6, 2)
    optional = u(data, nt + 20, 2)
    opt = nt + 24
    need(1 <= count <= 32 and optional >= 240 and opt + optional + count * 40 <= len(data), "PE headers")
    need(u(data, opt, 2) == 0x20B and u(data, opt + 68, 2) == 10, "Not PE32+ EFI application")
    need(u(data, opt + 32, 4) == 4096 and u(data, opt + 36, 4) == 512, "PE alignment")
    size = u(data, opt + 56, 4)
    base = u(data, opt + 24, 8)
    entry = u(data, opt + 16, 4)
    need(0 < size <= 1048576 and size % 4096 == 0 and base == 0x100000, "PE image bound")
    need(u(data, opt + 108, 4) == 16 and u(data, opt + 70, 2) & 0x140 == 0x140, "PE relocation/NX flags")
    sections = []
    for i in range(count):
        at = opt + optional + i * 40
        virtual = u(data, at + 8, 4)
        rva = u(data, at + 12, 4)
        raw = u(data, at + 16, 4)
        offset = u(data, at + 20, 4)
        flags = u(data, at + 36, 4)
        need(virtual > 0 and rva >= 4096 and rva % 4096 == 0 and rva + max(raw, virtual) <= size, "PE section range")
        need(raw % 512 == 0 and offset % 512 == 0 and offset + raw <= len(data), "PE section bytes")
        need(not (flags & 0x20000000 and flags & 0x80000000), "PE writable executable section")
        for old in sections:
            need(rva >= old[0] + max(old[1], old[2]) or old[0] >= rva + max(raw, virtual), "Overlapping sections")
        sections.append((rva, virtual, raw, offset, flags))

    def locate(rva, n):
        for start, virtual, raw, offset, flags in sections:
            if start <= rva and rva + n <= start + min(virtual, raw):
                return offset + rva - start, flags
        raise ValueError("RVA not file-backed")

    _, flags = locate(entry, 1)
    need(flags & 0x20000000 and not flags & 0x80000000, "Entry permission")
    import_rva, import_size = u(data, opt + 120, 4), u(data, opt + 124, 4)
    if import_size:
        at, _ = locate(import_rva, import_size)
        need(not any(data[at : at + import_size]), "External imports")
    reloc_rva, reloc_size = u(data, opt + 152, 4), u(data, opt + 156, 4)
    need(reloc_size >= 12, "Missing base relocation")
    cursor, _ = locate(reloc_rva, reloc_size)
    end = cursor + reloc_size
    targets = []
    while cursor < end:
        page, block = u(data, cursor, 4), u(data, cursor + 4, 4)
        need(page % 4096 == 0 and block >= 8 and block % 4 == 0 and cursor + block <= end, "Relocation block")
        for at in range(cursor + 8, cursor + block, 2):
            item = u(data, at, 2)
            kind = item >> 12
            if kind == 0:
                continue
            need(kind == 10, "Only DIR64 base relocations allowed")
            target = page + (item & 4095)
            file_at, _ = locate(target, 8)
            need(target not in targets, "Duplicate relocation")
            value = u(data, file_at, 8)
            need(base <= value < base + size, "Relocation target outside image")
            targets.append(target)
        cursor += block
    need(targets, "No actual address relocation")
    need(data.count(payload) == 1, "Embedded payload identity/uniqueness")
    # Independent relocation arithmetic check at a second load base.
    relocated = bytearray(data)
    delta = 0x2500000
    for target in targets:
        at, _ = locate(target, 8)
        value = u(data, at, 8)
        relocated[at : at + 8] = (value + delta).to_bytes(8, "little")
        need(u(relocated, at, 8) - (base + delta) == value - base, "Relocation arithmetic")
    return nt, opt, sections


def elf_validate(data, binary):
    need(data[:6] == b"\x7fELF\x02\x01" and u(data, 18, 2) == 62, "Payload ELF architecture")
    need(u(data, 24, 8) == 0 and u(data, 56, 2) == 3 and u(data, 54, 2) == 56, "Payload entry/headers")
    start = u(data, 32, 8)
    previous_end = 0
    for i, flags in enumerate((5, 4, 6)):
        at = start + i * 56
        kind, actual = u(data, at, 4), u(data, at + 4, 4)
        offset, virtual, size, memory, alignment = (u(data, at + x, 8) for x in (8, 16, 32, 40, 48))
        need(kind == 1 and actual == flags and alignment == 4096, "Payload section policy")
        need(
            virtual % 4096 == 0 and virtual >= previous_end and memory >= size and virtual + memory <= 0x20000,
            "Payload section bound",
        )
        need(offset + size <= len(data) and virtual + size <= len(binary) if size else True, "Payload truncation")
        if size:
            need(data[offset : offset + size] == binary[virtual : virtual + size], "Payload extraction mismatch")
        previous_end = virtual + memory
    need(0 < len(binary) <= 0x20000, "Payload bound")


def policy_call_present(disassembly, symbol):
    # GNU objdump -drwC on an unlinked x86-64 object: a direct E8 call with
    # zero displacement, an exact target/addend, and relocation at its imm32.
    pattern = (
        r"\s*([0-9a-f]+):\s+e8 00 00 00 00\s+callq?\s+"
        r"([0-9a-f]+) <[^>]+>\s+([0-9a-f]+): R_X86_64_PLT32\s+" + re.escape(symbol) + r"-0x4\s*"
    )
    for line in disassembly.splitlines():
        match = re.fullmatch(pattern, line)
        if match:
            call, target, relocation = (int(value, 16) for value in match.groups())
            if target == call + 5 and relocation == call + 1:
                return True
    return False


def budget_call_present(disassembly):
    return policy_call_present(disassembly, "aurora_kernel_budget_tick")


def ipc_call_present(disassembly):
    return policy_call_present(disassembly, "aurora_kernel_ipc_transition")


def owned_bytes_symbols(symbols):
    rows = {words[2]: words[1] for line in symbols.splitlines() if len(words := line.split()) == 3}
    required = (
        "__au_runtime_bytes_kernel_entry",
        "__au_runtime_bytes_allocate",
        "__au_runtime_bytes_at",
        "__au_runtime_bytes_set",
        "__au_runtime_bytes_drop",
        "__au_runtime_bytes_borrow_length",
        "__au_runtime_bytes_resize",
        "__au_runtime_bytes_kernel_fault",
    )
    for name in required:
        need(rows.get(name) in ("t", "T"), "Missing kernel owned-byte implementation: " + name)
    for name in (
        "__au_v_m1_18kernel_owned_bytes_n0__d24kernel_owned_bytes_entry",
        "__au_v_m1_18kernel_owned_bytes_n0__d10pass_bytes",
        "__au_v_m1_18kernel_owned_bytes_n0__d13consume_bytes",
    ):
        need(rows.get(name) == "t", "Owned-byte Aurora entry must remain local: " + name)
    forbidden = (
        "aurora_kernel_value",
        "aurora_kernel_budget_tick",
        "aurora_kernel_round_robin_next",
        "aurora_kernel_ipc_transition",
        "aurora_kernel_client_disposal",
        "aurora_kernel_terminal_event",
        "uefi_runtime_enter",
        "uefi_console_interrupt",
        "__au_runtime_bytes_test_entry",
        "malloc",
        "free",
        "calloc",
        "realloc",
        "abort",
        "fputs",
        "fflush",
    )
    need(not any(name in rows for name in forbidden), "Owned-byte profile linked another runtime/host seam")
    need(
        not any(name.startswith(("__cxa_", "_GLOBAL__sub_I", "_Zn", "_Zd")) for name in rows),
        "Owned-byte profile acquired global-constructor/heap machinery",
    )


# The IRQ is shared with the serial Console profile; it is not a profile selector.
GRAPHICAL_OBJECTS = frozenset(
    (
        "payload",
        "payload-entry",
        "language",
        "acpi",
        "pci",
        "runtime",
        "memory",
        "graphical-console",
        "console-entry",
        "loader",
        "embed",
        "transition",
        "loader-pe",
        "embed-pe",
        "transition-pe",
        "memory-pe",
    )
)
REFLECTION_HELPERS = frozenset(
    ("aurora_reflect_size", "aurora_reflect_field_count")
    + tuple(f"__au_reflect_s{module}_{field}" for module in range(1, 6) for field in ("size", "field_count"))
)
GRAPHICAL_BRIDGES = frozenset(("__au_runtime_graphical_entry", "__au_runtime_graphical_value"))
GRAPHICAL_IMPORTS = frozenset(("__au_runtime_console_next", "__au_runtime_display_pixel"))
GRAPHICAL_HOST = GRAPHICAL_IMPORTS | {"__au_runtime_console_put"}
GRAPHICAL_ENTRY = "__au_v_m1_24kernel_graphical_console_n0__d17graphical_console"
EVENT_OBJECTS = (GRAPHICAL_OBJECTS - {"graphical-console", "console-entry"}) | {"event-intake"}
# Event has no imported module scope; graphical also reflects its font module.
EVENT_REFLECTION_HELPERS = frozenset(("aurora_reflect_size", "aurora_reflect_field_count"))
EVENT_BRIDGES = frozenset(("__au_runtime_iommu_event_entry", "__au_runtime_iommu_event_value"))
EVENT_IMPORTS = frozenset(
    ("__au_runtime_iommu_event_poll", "__au_runtime_iommu_event_acknowledge", "__au_runtime_console_put")
)
EVENT_ENTRY = "__au_v_m1_26kernel_iommu_event_service_n0__d18iommu_event_intake"
EVENT_MODES = (
    "iommu-event-denial",
    "iommu-event-success",
    "iommu-event-overflow",
    "iommu-event-command-error",
    "iommu-event-observe",
)


def event_objects(mode):
    return EVENT_OBJECTS - {"event-intake"} if mode == "iommu-event-observe" else EVENT_OBJECTS


def observation_object_policy(symbols, object_symbols):
    need(set(object_symbols) == event_objects("iommu-event-observe"), "Exact observation object inventory required")
    names = nm_entries(symbols)
    need(names.get("uefi_event_observation") in ("t", "T"), "Missing readonly observation entry")
    for owner, text in {"linked": symbols, **object_symbols}.items():
        entries = nm_entries(text)
        need(
            not any(
                name.startswith(("__au_runtime_", "uefi_event_backing", "uefi_event_terminal"))
                or "run_event_intake" in name
                or "BootLifetimeRing" in name
                or "EventAdmission" in name
                for name in entries
            ),
            "Observation linked producer/session authority: " + owner,
        )
    need(
        nm_entries(object_symbols["language"]).get("aurora_kernel_value") == "T",
        "Observation requires ordinary scalar language fixture",
    )


def image_options(arguments):
    allowed = (
        [],
        ["--ipc-policy"],
        ["--owned-bytes"],
        ["--ipc-policy", "--disposal-policy"],
        ["--graphical-console"],
        ["--iommu-event"],
        ["--iommu-event-observe"],
    )
    need(arguments in allowed, "Expected one exact supported image-policy flag combination")
    return dict(
        require_ipc="--ipc-policy" in arguments,
        require_owned_bytes="--owned-bytes" in arguments,
        require_disposal="--disposal-policy" in arguments,
        require_graphical_console="--graphical-console" in arguments,
        require_iommu_event="--iommu-event" in arguments or "--iommu-event-observe" in arguments,
        require_iommu_observe="--iommu-event-observe" in arguments,
    )


def nm_entries(text):
    result = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) == 3:
            _, kind, name = fields
        elif len(fields) == 2 and fields[0] in ("U", "w", "v"):
            kind, name = fields
        else:
            continue
        # File/section metadata can repeat; retain data and weak symbols so
        # neither can masquerade as (or add) a runtime authority.
        if kind in ("a", "N", "n") or name.startswith("."):
            continue
        need(name not in result, "Duplicate code/import symbol: " + name)
        result[name] = kind
    return result


def profile_selection(symbols, object_names, graphical, event=False, observe=False):
    # Do not impose the paired duplicate-symbol policy on historical profiles.
    names = (
        nm_entries(symbols)
        if graphical or event
        else {fields[-1]: fields[-2] for line in symbols.splitlines() if len(fields := line.split()) in (2, 3)}
    )
    paired = (
        any(name.startswith("__au_runtime_graphical_") or "kernel_graphical_console" in name for name in names)
        or "graphical-console" in object_names
    )
    need(graphical or not paired, "Paired image requires explicit --graphical-console")
    event_present = (
        any(name.startswith("__au_runtime_iommu_event_") or "kernel_iommu_event_service" in name for name in names)
        or "event-intake" in object_names
    )
    need(event or not event_present, "Event image requires explicit --iommu-event")
    need(not (event and graphical), "Event and graphical image policies cannot combine")
    need(observe or "uefi_event_observation" not in names, "Observation requires explicit --iommu-event-observe")
    if observe:
        need(event and not graphical and not event_present, "Observation cannot acquire production Event authority")
        need(set(object_names) == event_objects("iommu-event-observe"), "Exact observation objects required")
    if event and not observe:
        need(set(object_names) == EVENT_OBJECTS, "Exact Event object inventory required")
        need(
            {name for name in names if name.startswith("__au_runtime_")} == EVENT_BRIDGES | EVENT_IMPORTS,
            "Crossed or incomplete Event authority inventory",
        )
        need(
            all(names.get(name) in ("t", "T") for name in EVENT_BRIDGES | EVENT_IMPORTS),
            "Event authorities must be linked code",
        )
        need(
            names.get(EVENT_ENTRY) == "t" and names.get("aurora_kernel_value") == "t",
            "Event source/value entries must stay local",
        )
        need(
            {name for name in names if name.startswith(("aurora_reflect_", "__au_reflect_"))}
            == EVENT_REFLECTION_HELPERS
            and all(names.get(name) == "T" for name in EVENT_REFLECTION_HELPERS),
            "Event reflection helper inventory/type mismatch",
        )
        need(
            not any(
                name.startswith(
                    (
                        "uefi_runtime_",
                        "aurora_user_",
                        "aurora_kernel_budget_",
                        "uefi_console_",
                        "uefi_service_",
                        "uefi_program_",
                        "aurora_exception_",
                    )
                )
                or name
                in (
                    "aurora_kernel_ipc_transition",
                    "aurora_kernel_terminal_event",
                    "aurora_kernel_client_disposal",
                    "malloc",
                    "calloc",
                    "realloc",
                    "free",
                    "abort",
                )
                or name.startswith(("__cxa_", "_GLOBAL__sub_I", "_Zn", "_Zd"))
                for name in names
            ),
            "Event image acquired an IRQ, timer, user runtime, heap or host authority",
        )
    if graphical:
        need(set(object_names) == GRAPHICAL_OBJECTS, "Exact graphical object inventory required")
        need("uefi_console_interrupt" in names, "Graphical profile requires its console IRQ")
        need(
            {name for name in names if name.startswith("__au_runtime_")} == GRAPHICAL_BRIDGES | GRAPHICAL_HOST,
            "Crossed or incomplete graphical runtime authority inventory",
        )
        need(
            all(names.get(name) in ("t", "T") for name in GRAPHICAL_BRIDGES | GRAPHICAL_HOST),
            "Graphical runtime authority must be linked code",
        )
        need(
            {name for name in names if name.startswith(("aurora_reflect_", "__au_reflect_"))} == REFLECTION_HELPERS
            and all(names[name] == "T" for name in REFLECTION_HELPERS),
            "Graphical reflection helper inventory/type mismatch",
        )
        need(
            names.get(GRAPHICAL_ENTRY) == "t" and names.get("aurora_kernel_value") == "t",
            "Paired source/value entries must stay local",
        )
        need(
            not any(name.startswith(("uefi_runtime_", "aurora_user_", "aurora_kernel_budget_")) for name in names),
            "Graphical profile linked a protected runtime or budget fixture",
        )
    return (
        "event"
        if event
        else "graphical"
        if graphical
        else ("console" if "uefi_console_interrupt" in names else "ordinary")
    )


def event_object_policy(symbols, object_symbols, calls, language_bindings, mode):
    """Exact finite Event authority ownership; machine CFG admission is separate."""
    need(mode in EVENT_MODES, "Unknown Event image mode")
    profile_selection(symbols, object_symbols, False, True, mode == "iommu-event-observe")
    if mode == "iommu-event-observe":
        observation_object_policy(symbols, object_symbols)
        return
    parsed = {name: nm_entries(value) for name, value in object_symbols.items()}
    language = parsed["language"]
    need(
        {name for name, kind in language.items() if kind in ("U", "w", "v")} == EVENT_IMPORTS,
        "Generated Event imports must be exactly poll, acknowledge and console output",
    )
    need(
        {name for name, kind in language.items() if kind.isupper() and kind != "U"}
        == EVENT_BRIDGES | EVENT_REFLECTION_HELPERS
        and all(language.get(name) == "T" for name in EVENT_BRIDGES | EVENT_REFLECTION_HELPERS),
        "Event globals must be exactly private bridges and reflection helpers",
    )
    need(
        language.get(EVENT_ENTRY) == "t" and language.get("aurora_kernel_value") == "t",
        "Event source/value entries escaped private object binding",
    )
    need(
        set(language_bindings) == {name for name, kind in language.items() if kind in ("t", "T")},
        "Event ELF function/binding inventory mismatch",
    )
    for name, binding in language_bindings.items():
        expected = (
            ("GLOBAL", "HIDDEN")
            if name in EVENT_BRIDGES
            else ("GLOBAL", "DEFAULT")
            if name in EVENT_REFLECTION_HELPERS
            else ("LOCAL", "DEFAULT")
        )
        need(binding == expected, "Event function escaped private ELF binding: " + name)
    expected = {
        "language": (EVENT_BRIDGES, EVENT_IMPORTS),
        "event-intake": (
            EVENT_IMPORTS,
            set() if mode == "iommu-event-overflow" else {"__au_runtime_iommu_event_entry"},
        ),
        "payload": (set(), {"__au_runtime_iommu_event_value"}),
    }
    for owner, entries in parsed.items():
        defined, imported = expected.get(owner, (set(), set()))
        authority = {name: kind for name, kind in entries.items() if name.startswith("__au_runtime_")}
        need(
            all(kind in ("T", "U") for kind in authority.values())
            and {name for name, kind in authority.items() if kind != "U"} == defined
            and {name for name, kind in authority.items() if kind == "U"} == imported,
            "Wrong Event authority owner/importer: " + owner,
        )
        reflection = {name for name in entries if name.startswith(("aurora_reflect_", "__au_reflect_"))}
        need(
            reflection == (EVENT_REFLECTION_HELPERS if owner == "language" else set())
            and all(entries[name] == "T" for name in reflection),
            "Wrong Event reflection owner: " + owner,
        )
        if owner != "language":
            need(
                not any(name.startswith("__au_v_") or name == "aurora_kernel_value" for name in entries),
                "Event source entry escaped language object: " + owner,
            )
    for owner, targets in (
        ("event-intake", () if mode == "iommu-event-overflow" else ("__au_runtime_iommu_event_entry",)),
        ("payload", ("__au_runtime_iommu_event_value",)),
        ("language", tuple(sorted(EVENT_IMPORTS))),
    ):
        for target in targets:
            need(
                policy_call_present(calls[owner], target),
                "Missing direct Event authority call: " + owner + ": " + target,
            )


def event_image_policy(directory, symbols=None, mode=None):
    directory = Path(directory)
    if mode is None:
        manifest = json.loads((directory / "iommu-event-build-start.json").read_text())
        mode = manifest["mode"]
        need(
            mode in EVENT_MODES
            and manifest["schema"] == "aurora-iommu-event-build-v1"
            and {flag for flag in manifest["flags"] if flag.startswith("-DAURORA_IOMMU_EVENT_CASE")}
            == {"-DAURORA_IOMMU_EVENT_CASE=" + str(EVENT_MODES.index(mode))},
            "Event image lacks exact build selector",
        )
    if symbols is None:
        symbols = subprocess.check_output(["nm", "-a", str(directory / "payload.elf")], text=True)
    profile_selection(
        symbols, {path.stem for path in directory.glob("*.o")}, False, True, mode == "iommu-event-observe"
    )
    objects = {
        name: subprocess.check_output(["nm", "-a", str(directory / (name + ".o"))], text=True)
        for name in sorted(event_objects(mode))
    }
    calls = {
        name: subprocess.check_output(["objdump", "-drwC", str(directory / (name + ".o"))], text=True)
        for name in (
            ("payload", "language") if mode == "iommu-event-observe" else ("payload", "event-intake", "language")
        )
    }
    bindings = subprocess.check_output(["readelf", "-sW", str(directory / "language.o")], text=True)
    event_object_policy(symbols, objects, calls, elf_function_bindings(bindings), mode)
    sections = subprocess.check_output(["readelf", "-SW", str(directory / "payload.elf")], text=True)
    need(
        not any(name in sections for name in (".init_array", ".fini_array", ".ctors", ".dtors")),
        "Event image must not register constructors/destructors",
    )
    return dict(
        mode=mode,
        objects=sorted(event_objects(mode)),
        language_imports=[] if mode == "iommu-event-observe" else sorted(EVENT_IMPORTS),
        language_bridges=[] if mode == "iommu-event-observe" else sorted(EVENT_BRIDGES),
        reflection_helpers=sorted(
            name for name in nm_entries(objects["language"]) if name.startswith(("aurora_reflect_", "__au_reflect_"))
        ),
    )


def graphical_object_policy(symbols, object_symbols, calls, language_bindings):
    """Pure ownership/call policy; linked opcode/stack admission remains mandatory."""
    profile_selection(symbols, object_symbols, True)
    parsed = {name: nm_entries(value) for name, value in object_symbols.items()}
    language = parsed["language"]
    need(
        {name for name, kind in language.items() if kind in ("U", "w", "v")} == GRAPHICAL_IMPORTS,
        "Graphical generated imports must be exactly Console.next and Display.pixel",
    )
    need(
        {name for name, kind in language.items() if kind.isupper() and kind != "U"}
        == GRAPHICAL_BRIDGES | REFLECTION_HELPERS
        and all(language.get(name) == "T" for name in GRAPHICAL_BRIDGES | REFLECTION_HELPERS),
        "Graphical globals must be exactly paired bridges and closed reflection helpers",
    )
    need(
        language.get(GRAPHICAL_ENTRY) == "t" and language.get("aurora_kernel_value") == "t",
        "Graphical source/value entries must remain local",
    )
    need(
        set(language_bindings) == {name for name, kind in language.items() if kind in ("t", "T")},
        "Graphical ELF function/binding inventory mismatch",
    )
    for name, binding in language_bindings.items():
        need(
            binding
            == (
                ("GLOBAL", "HIDDEN")
                if name in GRAPHICAL_BRIDGES
                else ("GLOBAL", "DEFAULT")
                if name in REFLECTION_HELPERS
                else ("LOCAL", "DEFAULT")
            ),
            "Graphical function escaped private ELF binding: " + name,
        )
    expected = {
        "language": (GRAPHICAL_BRIDGES, GRAPHICAL_IMPORTS),
        "graphical-console": (GRAPHICAL_HOST, {"__au_runtime_graphical_entry"}),
        "payload": (set(), {"__au_runtime_graphical_value"}),
    }
    for object_name, entries in parsed.items():
        reflection = {name for name in entries if name.startswith(("aurora_reflect_", "__au_reflect_"))}
        need(
            reflection == (REFLECTION_HELPERS if object_name == "language" else set())
            and all(entries[name] == "T" for name in reflection),
            "Wrong reflection helper owner/importer: " + object_name,
        )
        defined, imported = expected.get(object_name, (set(), set()))
        authorities = {name: kind for name, kind in entries.items() if name.startswith("__au_runtime_")}
        need(
            all(kind in ("T", "U") for kind in authorities.values())
            and {name for name, kind in authorities.items() if kind != "U"} == defined
            and {name for name, kind in authorities.items() if kind == "U"} == imported,
            "Wrong graphical authority owner/importer: " + object_name,
        )
        if object_name != "language":
            need(
                GRAPHICAL_ENTRY not in entries and "aurora_kernel_value" not in entries,
                "Graphical source/value entry escaped language object: " + object_name,
            )
    need(
        parsed["console-entry"].get("uefi_console_interrupt") == "T"
        and parsed["console-entry"].get("uefi_console_interrupt_dispatch") == "U"
        and parsed["graphical-console"].get("uefi_console_interrupt_dispatch") == "T"
        and parsed["graphical-console"].get("uefi_console_interrupt") == "U",
        "Graphical engine/IRQ ownership mismatch",
    )
    for name, owner, importer in (
        ("uefi_console_interrupt", "console-entry", "graphical-console"),
        ("uefi_console_interrupt_dispatch", "graphical-console", "console-entry"),
    ):
        need(
            [obj for obj, entries in parsed.items() if name in entries and entries[name] != "U"] == [owner],
            "Crossed graphical engine/IRQ definition: " + name,
        )
        need(
            [obj for obj, entries in parsed.items() if entries.get(name) == "U"] == [importer],
            "Crossed graphical engine/IRQ importer: " + name,
        )
    for object_name, targets in (
        ("graphical-console", ("__au_runtime_graphical_entry",)),
        ("payload", ("__au_runtime_graphical_value",)),
        ("language", tuple(sorted(GRAPHICAL_IMPORTS))),
    ):
        for target in targets:
            need(
                policy_call_present(calls[object_name], target),
                "Missing exact graphical direct call in " + object_name + ": " + target,
            )


def elf_function_bindings(text):
    result = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) == 8 and fields[3] == "FUNC" and fields[6] != "UND":
            need(fields[7] not in result, "Duplicate generated ELF function")
            result[fields[7]] = (fields[4], fields[5])
    return result


def console_service_policy(symbols, language_symbols, calls, contents, graphical=False):
    """Retain the serial Console checks for both engines, with explicit bridges."""
    engine = "graphical-console" if graphical else "console"
    bridge = "__au_runtime_graphical_entry" if graphical else "__au_runtime_console_entry"
    operations = GRAPHICAL_IMPORTS if graphical else ("__au_runtime_console_next", "__au_runtime_console_put")
    need("uefi_runtime_enter" not in symbols, "Console linked a user runtime")
    need(policy_call_present(calls[engine], bridge), "Console host must call the actual sealed service bridge")
    for entry in operations:
        need(policy_call_present(calls["language"], entry), "Aurora service must use the closed operation: " + entry)
    for legacy in ("aurora_console_byte", "aurora_console_command"):
        need(legacy not in symbols, "Native console retained legacy policy wrapper: " + legacy)
    for object_name in ("payload", "acpi", "pci", "runtime", engine, "loader"):
        for legacy in (
            "aurora::console::Line::",
            "aurora::console::Presentation<",
            "aurora_console_byte",
            "aurora_console_command",
            "__au_runtime_bytes_",
        ):
            need(legacy not in calls[object_name], "Native console retained a legacy/owner reference in " + object_name)
        for response in (b"Unknown command.", b"Line rejected:", b"Show commands", b"line capacity=64", b"aurora> "):
            need(response not in contents[object_name], "Human command presentation remains in C++ " + object_name)
    allowed_globals = (
        GRAPHICAL_BRIDGES | REFLECTION_HELPERS
        if graphical
        else {
            "__au_runtime_console_entry",
            "__au_runtime_console_value",
            "aurora_reflect_size",
            "aurora_reflect_field_count",
        }
    )
    for row in language_symbols.splitlines():
        fields = row.split()
        if len(fields) == 3 and fields[1] == "T":
            need(
                fields[2] in allowed_globals or (not graphical and common.is_reflection_helper(fields[2])),
                "Native service exposed a source entry: " + fields[2],
            )


def graphical_image_policy(directory, symbols=None):
    """Read-only explicit paired policy, shared by image build and receipt replay.

    This does not emit metadata or replace PE/ELF/PIC/combined stack admission.
    Extra stale profile objects fail closed; never delete evidence to pass it.
    """
    directory = Path(directory)
    if symbols is None:
        symbols = subprocess.check_output(["nm", "-a", str(directory / "payload.elf")], text=True)
    profile_selection(symbols, {path.stem for path in directory.glob("*.o")}, True)
    object_symbols = {
        name: subprocess.check_output(["nm", "-a", str(directory / (name + ".o"))], text=True)
        for name in sorted(GRAPHICAL_OBJECTS)
    }
    host_names = ("payload", "acpi", "pci", "runtime", "graphical-console", "loader")
    calls = {
        name: subprocess.check_output(["objdump", "-drwC", str(directory / (name + ".o"))], text=True)
        for name in (*host_names, "language")
    }
    bindings = subprocess.check_output(["readelf", "-sW", str(directory / "language.o")], text=True)
    graphical_object_policy(symbols, object_symbols, calls, elf_function_bindings(bindings))
    contents = {name: (directory / (name + ".o")).read_bytes() for name in host_names}
    console_service_policy(symbols, object_symbols["language"], calls, contents, graphical=True)
    return dict(
        objects=sorted(GRAPHICAL_OBJECTS),
        language_imports=sorted(GRAPHICAL_IMPORTS),
        language_bridges=sorted(GRAPHICAL_BRIDGES),
        host_authorities=sorted(GRAPHICAL_HOST),
        reflection_helpers=sorted(REFLECTION_HELPERS),
    )


def main(
    require_ipc=False,
    require_owned_bytes=False,
    require_disposal=False,
    require_graphical_console=False,
    require_iommu_event=False,
    require_iommu_observe=False,
):
    need(
        not require_graphical_console or not (require_ipc or require_owned_bytes or require_disposal),
        "Graphical profile cannot combine with another image-policy flag",
    )
    need(
        not require_iommu_event
        or not (require_ipc or require_owned_bytes or require_disposal or require_graphical_console),
        "Event profile cannot combine with another image-policy flag",
    )
    pe_path = BUILD / "esp/EFI/BOOT/BOOTX64.EFI"
    data = pe_path.read_bytes()
    binary = (BUILD / "payload.bin").read_bytes()
    elf = (BUILD / "payload.elf").read_bytes()
    nt, opt, sections = pe_validate(data, binary)
    elf_validate(elf, binary)
    names = ["payload", "payload-entry", "language", "acpi", "pci", "runtime", "memory"]
    symbols = subprocess.check_output(["nm", "-a", str(BUILD / "payload.elf")], text=True)
    profile = profile_selection(
        symbols,
        {path.stem for path in BUILD.glob("*.o")},
        require_graphical_console,
        require_iommu_event,
        require_iommu_observe,
    )
    if require_iommu_event:
        event_image_policy(BUILD, symbols)
        if not require_iommu_observe:
            names += ["event-intake"]
    if require_graphical_console:
        graphical_image_policy(BUILD, symbols)
    if require_owned_bytes:
        need(not require_ipc, "Owned-byte and IPC profiles cannot combine")
        owned_bytes_symbols(symbols)
        names += ["owned-bytes-runtime", "owned-bytes-profile"]
        sections_text = subprocess.check_output(["readelf", "-SW", str(BUILD / "payload.elf")], text=True)
        need(
            not any(name in sections_text for name in (".init_array", ".fini_array", ".ctors", ".dtors")),
            "Owned-byte profile must not register constructors/destructors",
        )
        language_symbols = subprocess.check_output(["nm", "-a", str(BUILD / "language.o")], text=True)
        need("aurora_kernel_value" not in language_symbols, "Owned-byte profile included ordinary scalar graph")
        profile_calls = subprocess.check_output(["objdump", "-drwC", str(BUILD / "owned-bytes-profile.o")], text=True)
        need(
            policy_call_present(profile_calls, "__au_runtime_bytes_kernel_entry"),
            "Kernel grant does not call the actual private bridge",
        )
    else:
        need("__au_runtime_bytes_" not in symbols, "Ordinary profile acquired an owned-byte runtime dependency")

    if "uefi_runtime_enter" in symbols:
        names += ["runtime-entry", "runtime-exceptions"]
        terminal_calls = subprocess.check_output(["objdump", "-drwC", str(BUILD / "runtime.o")], text=True)
        need(
            policy_call_present(terminal_calls, "aurora_kernel_terminal_event"),
            "Runtime must call the actual Aurora terminal-event producer",
        )
        terminal_symbols = {
            row.split()[2]: int(row.split()[0], 16) for row in symbols.splitlines() if len(row.split()) == 3
        }
        need(
            0 < terminal_symbols.get("aurora_kernel_terminal_event", 0) < terminal_symbols["__payload_text_end"],
            "Terminal-event entry outside owned payload RX",
        )
    if profile in ("console", "graphical"):
        engine = "graphical-console" if require_graphical_console else "console"
        names += [engine, "console-entry"]
        if not require_graphical_console:
            host_names = ("payload", "acpi", "pci", "runtime", engine, "loader")
            calls = {
                name: subprocess.check_output(["objdump", "-drwC", str(BUILD / (name + ".o"))], text=True)
                for name in (*host_names, "language")
            }
            contents = {name: (BUILD / (name + ".o")).read_bytes() for name in host_names}
            language_symbols = subprocess.check_output(["nm", "-a", str(BUILD / "language.o")], text=True)
            common.verify_reflection_image(BUILD)
            console_service_policy(symbols, language_symbols, calls, contents, require_graphical_console)
    if "uefi_service_drain_begin" in symbols:
        policy_relocations = subprocess.check_output(["objdump", "-drwC", str(BUILD / "runtime.o")], text=True)
        need(budget_call_present(policy_relocations), "Service timer does not call the actual Aurora budget entry")
        policy_symbols = {
            row.split()[2]: int(row.split()[0], 16) for row in symbols.splitlines() if len(row.split()) == 3
        }
        need(
            0 < policy_symbols.get("aurora_kernel_budget_tick", 0) < policy_symbols["__payload_text_end"],
            "Aurora budget entry outside owned payload RX",
        )
    if require_ipc:
        policy_relocations = subprocess.check_output(["objdump", "-drwC", str(BUILD / "runtime.o")], text=True)
        need(ipc_call_present(policy_relocations), "Mailbox runtime does not call the actual Aurora transaction entry")
        policy_symbols = {
            row.split()[2]: int(row.split()[0], 16) for row in symbols.splitlines() if len(row.split()) == 3
        }
        need(
            0 < policy_symbols.get("aurora_kernel_ipc_transition", 0) < policy_symbols["__payload_text_end"],
            "Aurora transaction entry outside owned payload RX",
        )
    if require_disposal:
        need(require_ipc, "Disposal profile requires the IPC authority graph")
        # User-run recovery must contain a genuine copied-plan call. Other
        # dispatcher profiles do not necessarily instantiate dispose_client.
        policy_relocations = subprocess.check_output(["objdump", "-drwC", str(BUILD / "runtime.o")], text=True)
        need(
            policy_call_present(policy_relocations, "aurora_kernel_client_disposal"),
            "User recovery does not call the actual Aurora disposal entry",
        )
        policy_symbols = {
            row.split()[2]: int(row.split()[0], 16) for row in symbols.splitlines() if len(row.split()) == 3
        }
        need(
            0 < policy_symbols.get("aurora_kernel_client_disposal", 0) < policy_symbols["__payload_text_end"],
            "Aurora disposal entry outside owned payload RX",
        )
    for name in names:
        relocations = subprocess.check_output(["readelf", "-rW", str(BUILD / f"{name}.o")], text=True)
        types = set(re.findall(r"R_X86_64_\w+", relocations))
        need(types <= {"R_X86_64_PC32", "R_X86_64_PLT32"}, f"Non-PIC object relocation in {name}: {types}")
        if name == "memory":
            need(not types, "Freestanding memory primitives must not call or relocate helpers")
    need(
        not subprocess.check_output(["nm", "-u", str(BUILD / "payload.elf")], text=True).strip(),
        "Unresolved payload symbol",
    )
    negatives = []

    def mutate(at, value, width):
        broken = bytearray(data)
        broken[at : at + width] = value.to_bytes(width, "little")
        negatives.append(bytes(broken))

    for at, value, width in (
        (0, 0, 2),
        (nt, 0, 4),
        (nt + 4, 0x14C, 2),
        (opt, 0x10B, 2),
        (opt + 68, 3, 2),
        (opt + 70, u(data, opt + 70, 2) & ~0x40, 2),
        (opt + 70, u(data, opt + 70, 2) & ~0x100, 2),
        (opt + 32, 512, 4),
        (opt + 56, 0xFFFFFFFF, 4),
        (opt + 16, 0, 4),
        (opt + 156, 0, 4),
    ):
        mutate(at, value, width)
    section_table = opt + u(data, nt + 20, 2)
    mutate(section_table + 36, 0xE0000020, 4)
    mutate(section_table + 12, 0, 4)
    negatives.extend((data[:128], data.replace(binary, b"\0" * len(binary), 1)))
    for broken in negatives:
        try:
            pe_validate(broken, binary)
        except ValueError:
            pass
        else:
            raise RuntimeError("Invalid UEFI PE image accepted")
    bad_elf = bytearray(elf)
    bad_elf[u(elf, 32, 8) + 4 : u(elf, 32, 8) + 8] = (7).to_bytes(4, "little")
    try:
        elf_validate(bad_elf, binary)
    except ValueError:
        pass
    else:
        raise RuntimeError("RWX payload accepted")
    (BUILD / "image-metadata.json").write_text(
        json.dumps(
            {
                "pe_sha256": hashlib.sha256(data).hexdigest(),
                "payload_sha256": hashlib.sha256(binary).hexdigest(),
                "payload_bytes": len(binary),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"PASS: PE32+ EFI relocation/RX policy, exact PIC payload; {len(negatives) + 1} negative images")


if __name__ == "__main__":
    import sys

    try:
        options = image_options(sys.argv[1:])
    except ValueError as error:
        raise SystemExit(str(error)) from error
    main(**options)
