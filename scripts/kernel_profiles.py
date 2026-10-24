#!/usr/bin/env python3
"""Exact named kernel profiles shared by Meson and thin command selectors.

This is build data, not guest authorization. Event execution retains its
separate reviewed model, firmware, admission and supervised-plan requirements.
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kernel_layout import IMAGE_POLICIES, LAYOUT, metadata as layout_metadata, read_table

FIXTURES = read_table(Path(__file__).resolve().parents[1] / "kernel/uefi/runtime-fixtures.inc")
FIXTURE_MODES = {
    mode: (image, value) for name, (mode, image, value) in FIXTURES.items() if not name.startswith("bios_")
}
BIOS_FIXTURE_MODES = {
    mode: (image, value) for name, (mode, image, value) in FIXTURES.items() if name.startswith("bios_")
}

# Base flags plus bounded variants mirror the existing admitted profiles.
UEFI_FAMILIES = [
    (
        [
            "-DAURORA_UEFI_ACPI",
            "-DAURORA_UEFI_PCI",
            "-DAURORA_UEFI_RUNTIME",
            "-DAURORA_UEFI_IPC",
            "-DAURORA_UEFI_SERVICE_BUDGET",
            "-DAURORA_UEFI_USER_BUDGET",
            "-DAURORA_RAM_FILE",
        ],
        {
            "ram-scratchpad-console": ["-DAURORA_RAM_SCRATCHPAD_CONSOLE"],
            "ram-scratchpad-console-fixture": ["-DAURORA_RAM_SCRATCHPAD_CONSOLE", "-DAURORA_SCRATCHPAD_FIXTURE"],
            "user-ram-file": [],
            "user-ram-file-fixture": ["-DAURORA_RUNTIME_FIXTURE"],
        },
    ),
    (
        [
            "-DAURORA_UEFI_ACPI",
            "-DAURORA_UEFI_PCI",
            "-DAURORA_UEFI_RUNTIME",
            "-DAURORA_UEFI_IPC",
            "-DAURORA_UEFI_SERVICE_BUDGET",
            "-DAURORA_UEFI_USER_BUDGET",
            "-DAURORA_BLOCKING_CALL",
        ],
        {
            "user-call": [],
            "user-call-fixture": ["-DAURORA_RUNTIME_FIXTURE"],
        },
    ),
    ([], {"normal": []}),
    (
        ["-maccumulate-outgoing-args", "-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_PCI", "-DAURORA_UEFI_IOMMU_EVENT"],
        {
            "iommu-event-denial": ["-DAURORA_IOMMU_EVENT_CASE=0"],
            "iommu-event-success": ["-DAURORA_IOMMU_EVENT_CASE=1"],
            "iommu-event-overflow": ["-DAURORA_IOMMU_EVENT_CASE=2"],
            "iommu-event-command-error": ["-DAURORA_IOMMU_EVENT_CASE=3"],
            "iommu-event-observe": ["-DAURORA_IOMMU_EVENT_CASE=4"],
        },
    ),
    (
        ["-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_GRAPHICAL_CONSOLE", "-DAURORA_UEFI_GRAPHICAL_FIXTURE"],
        {"graphical-console": [], "graphical-console-capture": ["-DAURORA_UEFI_GRAPHICAL_CAPTURE"]},
    ),
    (
        ["-DAURORA_UEFI_FRAMEBUFFER", "-DAURORA_UEFI_FRAMEBUFFER_FIXTURE", "-DAURORA_UEFI_FRAMEBUFFER_CAPTURE"],
        {
            "framebuffer": [],
        },
    ),
    (["-DAURORA_UEFI_FRAMEBUFFER", "-DAURORA_UEFI_FRAMEBUFFER_PROBE"], {"framebuffer-probe": []}),
    (["-DAURORA_UEFI_OWNED_BYTES"], {"owned-bytes": []}),
    (
        [
            "-DAURORA_UEFI_ACPI",
            "-DAURORA_UEFI_PCI",
            "-DAURORA_UEFI_RUNTIME",
            "-DAURORA_UEFI_SERVICE_BUDGET",
            "-DAURORA_OWNED_TEXT",
        ],
        {
            "runtime-owned-text": [],
            "runtime-console-region": ["-DAURORA_CONSOLE_REGION"],
            "runtime-console-region-fixture": ["-DAURORA_CONSOLE_REGION", "-DAURORA_RUNTIME_FIXTURE"],
            "runtime-owned-text-fixture": ["-DAURORA_RUNTIME_FIXTURE"],
        },
    ),
    (
        [
            "-DAURORA_UEFI_SNAPSHOT",
            "-DAURORA_UEFI_ACPI",
            "-DAURORA_UEFI_PCI",
            "-DAURORA_UEFI_RUNTIME",
            "-DAURORA_UEFI_IPC",
        ],
        {
            "snapshot": [],
            "snapshot-fixture": ["-DAURORA_RUNTIME_FIXTURE", "-DAURORA_SNAPSHOT_FIXTURE"],
        },
    ),
    (
        ["-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_CONSOLE"],
        {
            "console": [],
            "console-fixture": ["-DAURORA_CONSOLE_SERVICE_FIXTURE"],
        },
    ),
    (
        [
            "-DAURORA_UEFI_ACPI",
            "-DAURORA_UEFI_PCI",
            "-DAURORA_UEFI_RUNTIME",
            "-DAURORA_UEFI_IPC",
            "-DAURORA_UEFI_SERVICE_BUDGET",
            "-DAURORA_UEFI_USER_BUDGET",
            "-DAURORA_UEFI_PROGRAM_CONSOLE",
        ],
        {
            "program-console": [],
            "program-fixture": ["-DAURORA_RUNTIME_FIXTURE", "-DAURORA_PROGRAM_FIXTURE"],
            "program-file-call": ["-DAURORA_BLOCKING_CALL", "-DAURORA_FILE_CALL"],
            "program-file-call-fixture": ["-DAURORA_BLOCKING_CALL", "-DAURORA_FILE_CALL", "-DAURORA_RUNTIME_FIXTURE"],
        },
    ),
    (
        [
            "-DAURORA_UEFI_ACPI",
            "-DAURORA_UEFI_PCI",
            "-DAURORA_UEFI_BAR_CAPTURE",
            "-DAURORA_UEFI_BAR_EDK2",
            "-DAURORA_UEFI_IVRS",
        ],
        {
            "ivrs-fixture": ["-DAURORA_IVRS_FIXTURE"],
        },
    ),
    (
        [
            "-DAURORA_UEFI_ACPI",
            "-DAURORA_UEFI_PCI",
            "-DAURORA_UEFI_BAR_CAPTURE",
            "-DAURORA_UEFI_BAR_EDK2",
            "-DAURORA_UEFI_NVME_PREPARE",
        ],
        {"bar-prepare": []},
    ),
    (
        ["-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_PCI", "-DAURORA_UEFI_BAR_CAPTURE", "-DAURORA_UEFI_BAR_EDK2"],
        {
            "bar-fixture": ["-DAURORA_BAR_FIXTURE"],
        },
    ),
    (
        ["-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_PCI", "-DAURORA_UEFI_BAR_ADMISSION", "-DAURORA_UEFI_BAR_CAPTURE"],
        {"bar-capture": []},
    ),
    (["-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_PCI", "-DAURORA_UEFI_BAR_ADMISSION"], {"bar-state": []}),
    (
        [
            "-DAURORA_UEFI_ACPI",
            "-DAURORA_UEFI_PCI",
            "-DAURORA_UEFI_RUNTIME",
            "-DAURORA_UEFI_IPC",
            "-DAURORA_UEFI_SERVICE_BUDGET",
            "-DAURORA_UEFI_DISPATCH",
            "-DAURORA_UEFI_USER_BUDGET",
        ],
        {
            "user-resume": ["-DAURORA_USER_RESUME"],
            "user-fixture": ["-DAURORA_RUNTIME_FIXTURE", "-DAURORA_USER_FIXTURE"],
            "user-phases": ["-DAURORA_USER_PHASES"],
        },
    ),
    (
        [
            "-DAURORA_UEFI_ACPI",
            "-DAURORA_UEFI_PCI",
            "-DAURORA_UEFI_RUNTIME",
            "-DAURORA_UEFI_IPC",
            "-DAURORA_UEFI_SERVICE_BUDGET",
            "-DAURORA_UEFI_DISPATCH",
        ],
        {
            "dispatch": [],
            "dispatch-fixture": ["-DAURORA_RUNTIME_FIXTURE", "-DAURORA_DISPATCH_FIXTURE"],
        },
    ),
    (
        [
            "-DAURORA_UEFI_ACPI",
            "-DAURORA_UEFI_PCI",
            "-DAURORA_UEFI_RUNTIME",
            "-DAURORA_UEFI_IPC",
            "-DAURORA_UEFI_SERVICE_BUDGET",
        ],
        {
            "budget": [],
            "budget-fixture": ["-DAURORA_RUNTIME_FIXTURE", "-DAURORA_BUDGET_FIXTURE"],
        },
    ),
    (
        ["-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_PCI", "-DAURORA_UEFI_RUNTIME", "-DAURORA_UEFI_IPC"],
        {
            "ipc": [],
            "ipc-fixture": ["-DAURORA_RUNTIME_FIXTURE", "-DAURORA_IPC_FIXTURE"],
        },
    ),
    (
        [
            "-DAURORA_UEFI_ACPI",
            "-DAURORA_UEFI_PCI",
            "-DAURORA_UEFI_RUNTIME",
            "-DAURORA_UEFI_PINS",
            "-DAURORA_UEFI_TABLES",
            "-DAURORA_DORMANT_TABLE_TESTING=1",
        ],
        {
            "runtime-table-fixture": ["-DAURORA_RUNTIME_FIXTURE", "-DAURORA_TABLE_FIXTURE"],
        },
    ),
    (
        ["-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_PCI", "-DAURORA_UEFI_RUNTIME", "-DAURORA_UEFI_PINS"],
        {
            "runtime-pin-fixture": [
                "-DAURORA_RUNTIME_FIXTURE",
                "-DAURORA_PIN_FIXTURE",
                "-DAURORA_PIN_LEDGER_TESTING=1",
            ],
        },
    ),
    (
        ["-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_PCI", "-DAURORA_UEFI_RUNTIME"],
        {
            "runtime": [],
            "runtime-span": [],
            "runtime-multipage": ["-DAURORA_RUNTIME_MULTIPAGE"],
            "runtime-fixture": ["-DAURORA_RUNTIME_FIXTURE", "-DAURORA_RUNTIME_CONTROL_FIXTURE"],
        },
    ),
    (["-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_PCI"], {"pci": [], "pci-devices": [], "pci-bridge": []}),
    (
        ["-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_PCI"],
        {
            "pci-fixture": ["-DAURORA_PCI_FIXTURE"],
        },
    ),
    (["-DAURORA_UEFI_ACPI"], {"acpi": [], "acpi-two": []}),
    (
        ["-DAURORA_UEFI_ACPI"],
        {
            "acpi-fixture": ["-DAURORA_ACPI_FIXTURE"],
            "acpi-duplicate-root": ["-DAURORA_ACPI_DUPLICATE_ROOT"],
        },
    ),
    (["-DAURORA_UEFI_EXHAUSTED"], {"stale-exhausted": []}),
    (["-DAURORA_UEFI_STALE"], {"stale": []}),
    (["-DAURORA_UEFI_BAD_HANDOFF"], {"bad-handoff": []}),
    (["-DAURORA_UEFI_BAD_TABLE"], {"bad-table": []}),
    (["-DAURORA_UEFI_BAD_MAP"], {"bad-map": []}),
    (["-DAURORA_UEFI_WP"], {"wp": []}),
    (["-DAURORA_UEFI_NX"], {"nx": []}),
]

BIOS_CONTROLS = {
    "bios-fixture": {"KERNEL_TEST_BIOS_FIXTURE": "1"},
    "bios-schedule-fixture": {"KERNEL_TEST_BIOS_FIXTURE": "1", "KERNEL_TEST_SCHEDULE": "1"},
    "normal": {},
    "division-zero": {"KERNEL_TEST_DIVISION": "zero"},
    "division-remainder-zero": {"KERNEL_TEST_DIVISION": "remainder-zero"},
    "division-overflow": {"KERNEL_TEST_DIVISION": "overflow"},
    "division-remainder-min": {"KERNEL_TEST_DIVISION": "remainder-min"},
    "division-kernel-trap": {"KERNEL_TEST_DIVISION": "kernel-trap"},
    "unsigned-valid": {"KERNEL_TEST_UNSIGNED": "valid"},
    "unsigned-shift-count": {"KERNEL_TEST_UNSIGNED": "shift-count"},
    "unsigned-conversion-overflow": {"KERNEL_TEST_UNSIGNED": "conversion-overflow"},
    "unsigned-kernel-trap": {"KERNEL_TEST_UNSIGNED": "kernel-trap"},
    "schedule": {"KERNEL_TEST_SCHEDULE": "1"},
    "schedule-smp": {"KERNEL_TEST_SCHEDULE": "1"},
    "schedule-mmio": {"KERNEL_TEST_SCHEDULE": "1", "KERNEL_TEST_PROGRAM_APIC_READ": "1"},
    "schedule-no-apic": {"KERNEL_TEST_SCHEDULE": "1"},
    "schedule-forged": {"KERNEL_TEST_SCHEDULE": "1", "KERNEL_TEST_SCHEDULE_FORGED": "1"},
    "schedule-context": {"KERNEL_TEST_SCHEDULE": "1", "KERNEL_TEST_SCHEDULE_CONTEXT": "1"},
    "schedule-root": {"KERNEL_TEST_SCHEDULE": "1", "KERNEL_TEST_SCHEDULE_ROOT": "1"},
    "schedule-softint": {"KERNEL_TEST_SCHEDULE": "1", "KERNEL_TEST_PROGRAM_SOFTINT": "1"},
    "schedule-fpu": {"KERNEL_TEST_SCHEDULE": "1", "KERNEL_TEST_PROGRAM_FPU": "1"},
    "fault": {"KERNEL_TEST_DIVIDE_ERROR": "1"},
    "page-fault": {"KERNEL_TEST_PAGE_FAULT": "1"},
    "wp": {"KERNEL_TEST_WP": "1"},
    "nx": {"KERNEL_TEST_NX": "1"},
    "stack": {"KERNEL_TEST_STACK": "1"},
    "user-read": {"KERNEL_USER_PROBE_MODE": "1"},
    "user-write": {"KERNEL_USER_PROBE_MODE": "2"},
    "user-cli": {"KERNEL_USER_PROBE_MODE": "3"},
    "user-code-write": {"KERNEL_USER_PROBE_MODE": "4"},
    "user-nx": {"KERNEL_USER_PROBE_MODE": "5"},
    "user-io": {"KERNEL_USER_PROBE_MODE": "6"},
    "program-terminal-input": {"KERNEL_TEST_TERMINAL_EVENT_INPUT": "1"},
    "program-terminal-output": {"KERNEL_TEST_TERMINAL_EVENT_OUTPUT": "1"},
    "program-bad-return": {"KERNEL_TEST_PROGRAM_BAD_RETURN": "1"},
    "program-unknown-trap": {"KERNEL_TEST_PROGRAM_UNKNOWN_TRAP": "1"},
    "program-kernel-trap": {"KERNEL_TEST_PROGRAM_KERNEL_TRAP": "1"},
    "domain-code": {"KERNEL_TEST_PROGRAM_FOREIGN_CODE": "1"},
    "domain-stack": {"KERNEL_TEST_PROGRAM_FOREIGN_STACK": "1"},
    "domain-root-mismatch": {"KERNEL_TEST_DOMAIN_ROOT_MISMATCH": "1"},
    "no-nx": {},
    "console": {"KERNEL_CONSOLE": "1"},
}


def user_images(
    kind,
    mode,
    *,
    budget=False,
    dispatcher=False,
    user_budget=False,
    program=False,
    snapshot=False,
    blocking_call=False,
    file_call=False,
    ram_file=False,
    scratchpad=False,
):
    """Exact source/adapter composition; Meson owns every compile/link edge."""
    result = {}
    names = ("clean", "bounds", "peer") if dispatcher else ("clean", "bounds")
    for index, name in enumerate(names):
        if kind == "runtime":
            source = (
                "multipage" if mode == "multipage" else "span-clean" if name == "clean" and mode == "span" else name
            )
            entry = "kernel/uefi/user-image-entry.S"
            defines = []
            if mode == "multipage" and index == 1:
                defines.append("UEFI_USER_MULTIPAGE_FAULT=1")
            if mode == "fixture" and index == 0:
                defines.append("UEFI_USER_PROBES=1")
        else:
            source = "budget-service" if budget and index == 1 else "ipc-client" if index == 0 else "ipc-service"
            if program:
                source = "program-upper-client" if index == 0 else "program-stream-service"
            if dispatcher:
                source = (
                    "dispatch-service" if index == 1 else "dispatch-client-a" if index == 0 else "dispatch-client-b"
                )
            if user_budget and not program and index != 1:
                source = "user-budget-client-a" if index == 0 else "user-budget-client-b"
            if user_budget and mode == "resume" and index != 1:
                source = "user-checksum-client"
            if snapshot:
                source = "snapshot-client" if index == 0 else "snapshot-service"
            if blocking_call:
                client = "call-client-fixture" if mode == "user-call-fixture" else "call-snapshot-client"
                source = client if index == 0 else "call-snapshot-service"
            if file_call:
                source = "call-client" if index == 0 else "file-call-service"
            if ram_file:
                source = "ram-file-client" if index == 0 else "ram-file-service"
            entry = (
                "kernel/uefi/ram-scratchpad-client-entry.S"
                if scratchpad and index == 0
                else "kernel/uefi/ipc-user-entry.S"
            )
            # Fixture kernels select hostile probes in the one domain whose former
            # image carried them: the user client, the dispatcher's peer, or the
            # budget service.
            probe_index = 0 if user_budget else 2 if dispatcher else 1
            defines = ["IPC_PROBES=1"] if mode == "probes" and index == probe_index else []
            if (blocking_call or ram_file) and not scratchpad and index == 0:
                defines.append("CALL_CLIENT=1")
            if ram_file and index == 1:
                defines.append("SERVE_SERVICE=1")
            if (snapshot or program or blocking_call) and index == 1:
                defines.append(
                    "SNAPSHOT_SERVICE=1" if snapshot or (blocking_call and not file_call) else "PROGRAM_NOTE_SERVICE=1"
                )
        result[name] = dict(
            source=(
                "examples/kernel-ram-scratchpad-client.au"
                if scratchpad and index == 0
                else "tests/kernel-programs/" + source + ".au"
            ),
            roots=["library"] + (["kernel/policies"] if snapshot or program or blocking_call else []),
            base=LAYOUT.user_code + index * LAYOUT.code_stride,
            entry=entry,
            entry_flags=[value for define in defines for value in ("--defsym", define)],
            combined=ram_file
            or ((snapshot or program or blocking_call) and index == 1)
            or (blocking_call and index == 0),
        )
    return result


def bios_profile(mode, controls):
    division = controls.get("KERNEL_TEST_DIVISION", "none")
    unsigned = controls.get("KERNEL_TEST_UNSIGNED", "none")
    schedule = controls.get("KERNEL_TEST_SCHEDULE") == "1"
    console = controls.get("KERNEL_CONSOLE") == "1"
    flags = ["-DAURORA_INTERACTIVE_CONSOLE"] if console else []
    fixture = controls.get("KERNEL_TEST_BIOS_FIXTURE") == "1"
    if fixture and controls != BIOS_CONTROLS["bios-schedule-fixture" if schedule else "bios-fixture"]:
        raise ValueError("BIOS fixture rejects incompatible payload or entry controls")
    if fixture:
        flags += ["-DAURORA_BIOS_FIXTURE", "-DAURORA_BIOS_" + ("SCHEDULE" if schedule else "FAULT") + "_FIXTURE"]
    if division != "none":
        flags.append('-DAURORA_DIVISION_FIXTURE="' + division + '"')
    if division in ("zero", "remainder-zero"):
        flags.append("-DAURORA_TEST_DIVISION_ZERO")
    elif division == "kernel-trap":
        flags.append("-DAURORA_TEST_DIVISION_KERNEL_TRAP")
    if unsigned != "none":
        flags.append('-DAURORA_UNSIGNED_FIXTURE="' + unsigned + '"')
    if unsigned == "shift-count":
        flags.append("-DAURORA_TEST_UNSIGNED_SHIFT_COUNT")
    elif unsigned == "kernel-trap":
        flags.append("-DAURORA_TEST_UNSIGNED_KERNEL_TRAP")
    for name in (
        "DIVIDE_ERROR",
        "PAGE_FAULT",
        "WP",
        "NX",
        "STACK",
        "PROGRAM_KERNEL_TRAP",
        "DOMAIN_ROOT_MISMATCH",
        "SCHEDULE",
        "SCHEDULE_FORGED",
        "SCHEDULE_CONTEXT",
        "SCHEDULE_ROOT",
    ):
        if controls.get("KERNEL_TEST_" + name) == "1":
            flags.append("-DAURORA_TEST_" + name)
    flags.append("-DAURORA_USER_PROBE_MODE=" + controls.get("KERNEL_USER_PROBE_MODE", "0"))
    for name in ("INPUT", "OUTPUT"):
        if controls.get("KERNEL_TEST_TERMINAL_EVENT_" + name) == "1":
            flags.append("-DAURORA_TERMINAL_EVENT_" + name)
    defines = [
        "AURORA_PROGRAM_" + name + "=1"
        for name in ("BAD_RETURN", "UNKNOWN_TRAP", "FOREIGN_CODE", "FOREIGN_STACK", "SOFTINT", "FPU", "APIC_READ")
        if controls.get("KERNEL_TEST_PROGRAM_" + name) == "1"
    ]
    users = {}
    for index, name in enumerate(("clean", "bounds", "overflow")):
        source = name
        source = {
            ("zero", "bounds"): "division-zero",
            ("remainder-zero", "bounds"): "division-remainder-zero",
            ("overflow", "overflow"): "division-overflow",
            ("remainder-min", "clean"): "division-remainder-min",
        }.get((division, name), source)
        if unsigned != "none" and name == "clean":
            source = "unsigned-valid"
        if unsigned == "shift-count" and name == "bounds":
            source = "unsigned-shift-count"
        if unsigned == "conversion-overflow" and name == "overflow":
            source = "unsigned-conversion-overflow"
        if schedule:
            source = {"clean": "scheduled-clean", "bounds": "scheduled-spin", "overflow": "bounds"}[name]
        entry_defines = defines + (["AURORA_PROGRAM_CONTEXT_PROBE=1"] if schedule and name == "clean" else [])
        users[name] = dict(
            source="tests/kernel-programs/" + source + ".au",
            roots=["library"],
            base=0x1B0000 + index * 4096,
            entry="kernel/program-entry.S",
            entry_flags=[value for define in entry_defines for value in ("--defsym", define)],
            combined=False,
        )
    cpp = {
        "kernel-" + name: "kernel/" + name + ".cpp"
        for name in ("main", "interrupts", "protection", "user-program", "address-spaces", "apic", "scheduler")
    }
    assembly = {
        name: dict(source=source, flags=flags)
        for name, source, flags in (
            ("boot", "kernel/boot.S", ["--32"]),
            ("start", "kernel/start.S", ["--64"]),
            ("kernel-memory", "kernel/uefi/memory.S", ["--64"]),
            ("exceptions", "kernel/exceptions.S", ["--64"]),
            ("user", "kernel/user.S", ["--64"]),
        )
    }
    if console:
        assembly["serial-input"] = dict(source="kernel/serial-input.S", flags=["--64"])
        cpp["kernel-interactive-console"] = "kernel/interactive-console.cpp"
    return dict(
        platform="bios",
        mode=mode,
        flags=flags,
        language="examples/kernel-console.au" if console else "examples/kernel-bios.au",
        roots=["kernel/policies"] + (["library"] if console else []),
        bridge="kernel/console-service-entry.S" if console else "",
        cpp=cpp,
        assembly=assembly,
        users=users,
        user_kind="bios",
        user_mode="",
        user_options=[],
        user_metadata_options=["--division-fixture", division, "--unsigned-fixture", unsigned]
        + (["--bios-fixture-family", "schedule" if schedule else "ordinary"] if fixture else []),
        link=[
            "kernel-apic",
            "kernel-scheduler",
            "kernel-memory",
            "start",
            "exceptions",
            "user",
            "kernel-user-program",
            "kernel-address-spaces",
            "kernel-user-images",
            "kernel-protection",
            "kernel-interrupts",
            "kernel-main",
            "kernel-language",
        ]
        + (["serial-input", "kernel-interactive-console", "kernel-uart"] if console else []),
        closed=False,
    )


def uefi_profile(mode, flags):
    scratchpad = mode in ("ram-scratchpad-console", "ram-scratchpad-console-fixture")
    scratchpad_fixture = mode == "ram-scratchpad-console-fixture"
    runtime = scratchpad or mode.startswith(("runtime", "ipc", "budget", "dispatch", "user-", "program-", "snapshot"))
    ipc = scratchpad or mode.startswith(("ipc", "budget", "dispatch", "user-", "program-", "snapshot"))
    console_region = mode.startswith("runtime-console-region")
    owned_text = mode.startswith("runtime-owned-text") or console_region
    budget = scratchpad or mode.startswith(("budget", "dispatch", "user-", "program-")) or owned_text
    file_call = mode.startswith("program-file-call")
    blocking_call = mode.startswith("user-call") or file_call
    ram_file = scratchpad or mode in ("user-ram-file", "user-ram-file-fixture")
    dispatcher = mode.startswith(("dispatch", "user-")) and not (blocking_call or ram_file)
    user_budget = scratchpad or mode.startswith(("user-", "program-"))
    program = mode.startswith("program-")
    snapshot = mode.startswith("snapshot")
    console = mode in ("console", "console-fixture")
    graphical = mode in ("graphical-console", "graphical-console-capture")
    framebuffer = mode == "framebuffer"
    event = mode.startswith("iommu-event-")
    user_mode = "normal"
    if mode.startswith("runtime-") and mode[8:] in ("span", "multipage", "owned-text", "fixture"):
        user_mode = mode[8:]
    if owned_text:
        user_mode = (
            "console-region-fixture"
            if mode == "runtime-console-region-fixture"
            else "console-region"
            if console_region
            else "owned-text"
        )
    if mode == "user-resume":
        user_mode = "resume"
    if mode in ("budget-fixture", "dispatch-fixture", "user-fixture"):
        user_mode = "probes"
    user_options = [
        option
        for enabled, option in (
            (budget and not owned_text, "--service-budget"),
            (dispatcher, "--dispatcher"),
            (user_budget, "--user-budget"),
            (program, "--program-console"),
            (snapshot, "--snapshot"),
            (blocking_call, "--blocking-call"),
            (file_call, "--file-call"),
            (ram_file, "--ram-file"),
            (scratchpad, "--ram-scratchpad-console"),
            (scratchpad_fixture, "--ram-scratchpad-fixture"),
        )
        if enabled
    ]
    users = (
        user_images(
            "ipc" if ipc else "runtime",
            user_mode,
            budget=budget,
            dispatcher=dispatcher,
            user_budget=user_budget,
            program=program,
            snapshot=snapshot,
            blocking_call=blocking_call,
            file_call=file_call,
            ram_file=ram_file,
            scratchpad=scratchpad,
        )
        if runtime
        else {}
    )
    if mode == "program-file-call-fixture":
        users["clean"]["source"] = "tests/kernel-programs/call-client-fixture.au"
    if mode == "user-ram-file-fixture":
        users["bounds"]["source"] = "tests/kernel-programs/ram-file-service-fixture.au"
    if scratchpad_fixture:
        users["bounds"]["source"] = "tests/kernel-programs/scratchpad-service-fixture.au"
    if owned_text:
        users["clean"].update(
            source=(
                "tests/kernel-programs/console-region-fixture.au"
                if mode == "runtime-console-region-fixture"
                else "tests/kernel-programs/console-region.au"
            )
            if console_region
            else "tests/kernel-programs/owned-text.au",
            entry="kernel/uefi/console-region-entry.S" if console_region else "kernel/uefi/owned-text-entry.S",
            combined=True,
        )
    if mode == "runtime-console-region-fixture":
        users["clean"]["entry_flags"] += ["--defsym", "AURORA_CONSOLE_FIXTURE=1"]
    image_policy = (
        "multipage"
        if "-DAURORA_RUNTIME_MULTIPAGE" in flags
        else "call"
        if blocking_call or ram_file
        else "owned_text"
        if owned_text
        else "one_page"
    )
    flags = [*flags, "-DAURORA_RUNTIME_IMAGE_POLICY=" + image_policy]
    for index, image in enumerate(users.values()):
        image["max_pages"] = IMAGE_POLICIES[image_policy][index]
    cpp = {name: "kernel/uefi/" + name + ".cpp" for name in ("payload", "acpi", "pci", "runtime")}
    assembly = {
        name: dict(source="kernel/uefi/" + name + ".S", flags=["--64"])
        for name in ("payload-entry", "memory", "transition")
    }
    runtime_objects = []
    if runtime:
        runtime_flags = (["--defsym", "AURORA_IPC=1"] if ipc else []) + (
            ["--defsym", "AURORA_SERVICE_BUDGET=1"] if budget else []
        )
        if owned_text:
            runtime_flags += ["--defsym", "AURORA_OWNED_TEXT=1"]
        if mode == "user-resume" or blocking_call or ram_file or console_region:
            runtime_flags += ["--defsym", "AURORA_USER_RESUME=1"]
        if blocking_call or ram_file:
            runtime_flags += ["--defsym", "AURORA_BLOCKING_CALL=1"]
        if mode == "runtime-fixture":
            runtime_flags += ["--defsym", "AURORA_RUNTIME_PROBES=1"]
        if mode in ("budget-fixture", "dispatch-fixture", "user-fixture"):
            runtime_flags += ["--defsym", "AURORA_IPC_PROBES=1"]
        assembly["runtime-entry"] = dict(source="kernel/uefi/runtime-entry.S", flags=["--64"] + runtime_flags)
        assembly["runtime-exceptions"] = dict(
            source="kernel/exceptions.S",
            flags=["--64", "--defsym", "AURORA_RELATIVE_ONLY=1"]
            + (["--defsym", "AURORA_BLOCKING_CALL=1"] if blocking_call or ram_file else [])
            + (["--defsym", "AURORA_OWNED_TEXT=1"] if owned_text else []),
        )
        runtime_objects = ["runtime-entry", "runtime-exceptions"]
    console_objects = []
    if console or graphical:
        assembly["console-entry"] = dict(source="kernel/uefi/console-entry.S", flags=["--64"])
        name = "graphical-console" if graphical else "console"
        cpp[name] = "kernel/uefi/" + name + ".cpp"
        console_objects = ["console-entry", name]
    owned_objects = []
    if mode == "owned-bytes" or snapshot or (blocking_call and not file_call):
        cpp["owned-bytes-runtime"] = "kernel/owned-bytes.cpp"
        name = "snapshot" if snapshot or blocking_call else "owned-bytes-profile"
        cpp[name] = "kernel/uefi/" + ("snapshot" if snapshot or blocking_call else "owned-bytes") + ".cpp"
        owned_objects = ["owned-bytes-runtime", name]
    if owned_text:
        cpp["owned-bytes-runtime"] = "kernel/owned-bytes.cpp"
        owned_objects = ["owned-bytes-runtime"]
    if framebuffer:
        cpp["framebuffer"] = "kernel/uefi/framebuffer.cpp"
    if event and mode != "iommu-event-observe":
        cpp["event-intake"] = "kernel/uefi/event-intake.cpp"
    entry, bridge = "examples/kernel.au", ""
    for enabled, source, adapter in (
        (event and mode != "iommu-event-observe", "iommu-event-service", "event-service"),
        (framebuffer, "display-service", "display-service"),
        (program, "program-console", "program-note"),
        (file_call, "program-file-call", "program-file-call"),
        (scratchpad, "ram-scratchpad-console", "ram-scratchpad-console"),
        (mode == "owned-bytes", "owned-bytes", "owned-bytes"),
        (snapshot or (blocking_call and not file_call), "snapshot", "snapshot"),
        (console, "console-service", "console-service"),
        (graphical, "graphical-console", "graphical-console"),
    ):
        if enabled:
            entry, bridge = "examples/kernel-" + source + ".au", "kernel/uefi/" + adapter + "-entry.S"
    return dict(
        platform="uefi",
        mode=mode,
        flags=flags,
        language=entry,
        roots=["kernel/policies", "library"],
        bridge=bridge,
        cpp=cpp,
        assembly=assembly,
        users=users,
        user_kind="ipc" if ipc else "runtime",
        user_mode=user_mode,
        user_options=user_options,
        user_metadata_options=[],
        link=["payload-entry", "memory", "payload", "acpi", "pci", "runtime"]
        + runtime_objects
        + console_objects
        + ["language"]
        + owned_objects
        + (["framebuffer"] if framebuffer else [])
        + (["event-intake"] if event and mode != "iommu-event-observe" else []),
        closed=program,
    )


# UEFI guest families booted by scripts/kernel-uefi-smoke.sh; Meson registers each
# mode as a test in the suites guest and guest-<family>.
GUEST_FAMILIES = {
    "uefi": "normal stale stale-exhausted bad-handoff bad-map bad-table wp nx",
    "acpi": "acpi acpi-two acpi-disabled acpi-checksum acpi-bad-source acpi-duplicate-root acpi-write acpi-revoked",
    "pci": "pci pci-devices pci-bridge pci-checksum pci-cycle pci-write pci-revoked",
    "runtime": "runtime runtime-multipage runtime-terminal-input runtime-terminal-output runtime-code runtime-stack "
    "runtime-kernel runtime-window runtime-root runtime-kernel-trap runtime-entry-stack runtime-write runtime-nx "
    "runtime-return runtime-unknown runtime-syscall runtime-sysenter runtime-span",
    "ipc": "ipc ipc-fault ipc-cancel ipc-owner ipc-stale ipc-version ipc-phase ipc-transaction ipc-site ipc-unknown "
    "ipc-root ipc-kernel-trap ipc-duplicate ipc-late ipc-exhausted",
    "budget": "budget budget-fault budget-context budget-pending budget-noapic budget-smp budget-discovery "
    "budget-cache budget-alias budget-forged budget-root budget-mmio budget-softint budget-fpu budget-epoch",
    "dispatch": "dispatch dispatch-budget dispatch-fault dispatch-mixed dispatch-pending dispatch-cross-reply "
    "dispatch-client-owner dispatch-stale dispatch-duplicate dispatch-full dispatch-root dispatch-peer-code",
    "user-phases": "user-phases user-context user-retire-pending user-request-budget user-completion-budget "
    "user-request-bounds user-completion-bounds user-request-overflow user-completion-overflow user-pending "
    "user-role user-phase user-transaction user-epoch user-root user-unknown user-stale-grant user-ram-file "
    "user-ram-file-service-fault user-ram-file-grant user-ram-file-site user-ram-file-settlement "
    "user-ram-file-commit-fault user-ram-file-caller-budget user-ram-file-service-budget user-ram-file-abort-budget "
    "user-ram-file-epochs user-ram-file-pending user-ram-file-frame user-ram-file-root",
    "tables": "runtime-table-readback runtime-table-reject runtime-table-exhaust runtime-table-quarantine",
    "pins": "runtime-pin-cancel runtime-pin-fault runtime-pin-stale runtime-pin-exhaust",
}


UEFI_ALIASES = {
    "budget-smp": "budget",
    # Rejected in ACPI discovery, before the fixture selector is read.
    "ivrs-missing": "ivrs-fixture",
    "pci-devices": "pci",
    "pci-bridge": "pci",
    "acpi-two": "acpi",
}
UEFI_ALIASES.update({mode: image for mode, (image, _) in FIXTURE_MODES.items()})
BIOS_ALIASES = {"schedule-smp": "schedule", "schedule-no-apic": "schedule", "no-nx": "normal"}
BIOS_ALIASES.update({mode: image for mode, (image, _) in BIOS_FIXTURE_MODES.items()})


def canonical_profile(platform, mode):
    aliases = BIOS_ALIASES if platform == "bios" else UEFI_ALIASES
    return aliases.get(mode, mode)


def select(platform, environment, requested=None):
    """Choose one bounded profile; never silently combine inherited fixtures."""
    if platform not in ("bios", "uefi"):
        raise ValueError("Unknown kernel platform: " + platform)
    controls = {}
    known = {name for values in BIOS_CONTROLS.values() for name in values}
    for name, value in environment.items():
        if not (name.startswith("KERNEL_TEST_") or name in ("KERNEL_CONSOLE", "KERNEL_USER_PROBE_MODE")):
            continue
        if not value:
            continue
        if name not in known:
            raise ValueError("Unknown kernel profile control: " + name)
        inactive = "none" if name in ("KERNEL_TEST_DIVISION", "KERNEL_TEST_UNSIGNED") else "0"
        if value != inactive:
            controls[name] = value
    if platform == "uefi":
        if controls:
            raise ValueError("UEFI profiles reject inherited BIOS controls: " + ", ".join(sorted(controls)))
        inherited = environment.get("UEFI_MODE")
        mode = requested or inherited or "normal"
        if inherited and requested and inherited != requested:
            raise ValueError("UEFI_MODE conflicts with requested profile")
        if mode not in {mode for _, variants in UEFI_FAMILIES for mode in variants} | UEFI_ALIASES.keys():
            raise ValueError("Unknown UEFI profile: " + mode)
        return mode
    if environment.get("UEFI_MODE"):
        raise ValueError("BIOS profiles reject inherited UEFI_MODE")
    if requested is not None:
        if requested not in BIOS_CONTROLS:
            raise ValueError("Unknown BIOS profile: " + requested)
        if controls and controls != BIOS_CONTROLS[requested]:
            raise ValueError("Inherited BIOS controls conflict with requested profile")
        return requested
    matches = [mode for mode, values in BIOS_CONTROLS.items() if values == controls]
    if not matches:
        raise ValueError("Unsupported or conflicting BIOS profile controls: " + repr(controls))
    return matches[0]


def profiles():
    result = {
        "bios/" + mode: bios_profile(mode, controls)
        for mode, controls in BIOS_CONTROLS.items()
        if mode not in BIOS_ALIASES
    }
    for common, variants in UEFI_FAMILIES:
        for mode, extra in variants.items():
            if mode in UEFI_ALIASES:
                continue
            key = "uefi/" + mode
            if key in result:
                raise ValueError("Duplicate kernel profile: " + key)
            result[key] = uefi_profile(mode, common + extra)
    return result


def keyval_rows(prefix, value):
    """Emit Meson's existing keyval syntax, preserving complete argument values."""
    if isinstance(value, dict):
        yield prefix + "=" + "|".join(value)
        for key, item in value.items():
            yield from keyval_rows(prefix + "." + key, item)
    else:
        values = value if isinstance(value, list) else [int(value) if isinstance(value, bool) else value]
        words = [str(item) for item in values]
        if any(any(character in word for character in "|\n\r#") for word in words):
            raise ValueError("Unsupported profile data delimiter")
        yield prefix + "=" + "|".join(words)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--meson-output", type=Path)
    action.add_argument("--select", choices=("bios", "uefi"))
    action.add_argument("--fixture-byte")
    action.add_argument("--bios-fixture-byte")
    args = parser.parse_args()
    if args.bios_fixture_byte:
        print(BIOS_FIXTURE_MODES.get(args.bios_fixture_byte, ("", ""))[1])
    elif args.fixture_byte:
        print(FIXTURE_MODES.get(args.fixture_byte, ("", ""))[1])
    elif args.select:
        try:
            print(select(args.select, os.environ))
        except ValueError as error:
            parser.error(str(error))
    else:
        rows = list(keyval_rows("profiles", profiles()))
        rows += keyval_rows("layout", layout_metadata())
        rows += keyval_rows("guests", {name: modes.split() for name, modes in GUEST_FAMILIES.items()})
        rows += keyval_rows("image_policies", {name: list(values) for name, values in IMAGE_POLICIES.items()})
        rows += keyval_rows(
            "aliases",
            {"bios/" + key: "bios/" + value for key, value in BIOS_ALIASES.items()}
            | {"uefi/" + key: "uefi/" + value for key, value in UEFI_ALIASES.items()},
        )
        args.meson_output.write_text("\n".join(rows) + "\n")
