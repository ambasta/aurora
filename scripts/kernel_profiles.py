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


def check_fixture_families(rows):
    """read_fixture admits one value interval per image, so each image's rows are consecutive values."""
    values = [value for _, _, value in rows.values()]
    if len(set(values)) != len(values) or not all(0 < value < 256 for value in values):
        raise ValueError("Fixture selectors must be distinct bytes")
    for image in {image for _, image, _ in rows.values()}:
        family = sorted(value for _, owner, value in rows.values() if owner == image)
        if family != list(range(family[0], family[0] + len(family))):
            raise ValueError("Fixture family is not one selector interval: " + image)


check_fixture_families(FIXTURES)
FIXTURE_MODES = {
    mode: (image, value) for name, (mode, image, value) in FIXTURES.items() if not name.startswith("bios_")
}
# These images read their selector from a QEMU fw_cfg file instead of a serial
# byte: early-fixture injects before ExitBootServices, while firmware owns the
# UART, and the Event harness writes serial output to a file.
FW_CFG_IMAGES = frozenset(("early-fixture", "iommu-event"))
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
            "user-call-fixture": ["-DAURORA_RUNTIME_FIXTURE"],
        },
    ),
    ([], {"normal": []}),
    (
        ["-maccumulate-outgoing-args", "-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_PCI", "-DAURORA_UEFI_IOMMU_EVENT"],
        {"iommu-event": []},
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
            # The one production UEFI image: this full protected stack with the
            # program console rendered by the graphical terminal, and no fixture
            # selector, test hook or capture handshake.
            "production": ["-DAURORA_PRODUCTION", "-DAURORA_UEFI_GRAPHICAL_TERMINAL"],
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
            "budget-fixture": ["-DAURORA_RUNTIME_FIXTURE", "-DAURORA_BUDGET_FIXTURE"],
        },
    ),
    (
        ["-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_PCI", "-DAURORA_UEFI_RUNTIME", "-DAURORA_UEFI_IPC"],
        {
            "ipc-fixture": ["-DAURORA_RUNTIME_FIXTURE", "-DAURORA_IPC_FIXTURE"],
        },
    ),
    # The plain runtime, span and multipage baselines and the pin and dormant-table
    # supervisors, each selected at boot; its user images are RUNTIME_BANK.
    (
        ["-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_PCI", "-DAURORA_UEFI_RUNTIME"],
        {
            "runtime-fixture": [
                "-DAURORA_RUNTIME_FIXTURE",
                "-DAURORA_RUNTIME_CONTROL_FIXTURE",
                "-DAURORA_RUNTIME_MULTIPAGE",
                "-DAURORA_UEFI_PINS",
                "-DAURORA_PIN_FIXTURE",
                "-DAURORA_PIN_LEDGER_TESTING=1",
                "-DAURORA_UEFI_TABLES",
                "-DAURORA_DORMANT_TABLE_TESTING=1",
                "-DAURORA_TABLE_FIXTURE",
            ],
        },
    ),
    (
        ["-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_PCI"],
        {
            "pci-fixture": ["-DAURORA_PCI_FIXTURE"],
        },
    ),
    (
        ["-DAURORA_UEFI_ACPI"],
        {
            "acpi-fixture": ["-DAURORA_ACPI_FIXTURE"],
        },
    ),
    # Loader and payload handoff faults, selected by a fw_cfg file read at loader entry.
    (["-DAURORA_UEFI_ACPI", "-DAURORA_EARLY_FIXTURE"], {"early-fixture": []}),
]

# BIOS profiles: the smoke image, the interactive console and one test image whose
# fault, program-set and scheduler cases are selected at boot (runtime-fixtures.inc).
BIOS_PROFILES = ("normal", "console", "bios-fixture")
# The test image's program bank, one page each: (name, source, entry defines). The
# entry-probe variants only need the probe in image 0's entry stub, which faults
# before any program code runs, so they are built on the small bounds program.
BIOS_PROGRAMS = (
    ("clean", "clean", ()),
    ("bounds", "bounds", ()),
    ("overflow", "overflow", ()),
    ("division-zero", "division-zero", ()),
    ("division-remainder-zero", "division-remainder-zero", ()),
    ("division-overflow", "division-overflow", ()),
    ("division-remainder-min", "division-remainder-min", ()),
    ("unsigned-valid", "unsigned-valid", ()),
    ("unsigned-shift-count", "unsigned-shift-count", ()),
    ("unsigned-conversion-overflow", "unsigned-conversion-overflow", ()),
    ("bad-return", "bounds", ("AURORA_PROGRAM_BAD_RETURN",)),
    ("unknown-trap", "bounds", ("AURORA_PROGRAM_UNKNOWN_TRAP",)),
    ("foreign-code", "bounds", ("AURORA_PROGRAM_FOREIGN_CODE",)),
    ("foreign-stack", "bounds", ("AURORA_PROGRAM_FOREIGN_STACK",)),
    ("scheduled-clean", "scheduled-clean", ("AURORA_PROGRAM_CONTEXT_PROBE",)),
    ("scheduled-spin", "scheduled-spin", ()),
    ("apic-read", "bounds", ("AURORA_PROGRAM_APIC_READ",)),
    ("softint", "bounds", ("AURORA_PROGRAM_SOFTINT",)),
    ("fpu", "bounds", ("AURORA_PROGRAM_FPU",)),
)
ORDINARY_SET = ("clean", "bounds", "overflow")
# runtime-fixture's user image bank: (name, source, domain image it is linked
# for, admitted pages, entry defines). Every image-0 entry carries the probe
# dispatch, which a zero launch word skips. RUNTIME_SETS names the bank images
# acting as images 0 and 1 for a mode; every other mode runs clean and bounds.
RUNTIME_BANK = (
    ("clean", "clean", 0, 1, ("UEFI_USER_PROBES",)),
    ("bounds", "bounds", 1, 1, ()),
    ("span-clean", "span-clean", 0, 1, ("UEFI_USER_PROBES",)),
    ("multipage-clean", "multipage", 0, 3, ("UEFI_USER_PROBES",)),
    ("multipage-bounds", "multipage", 1, 3, ("UEFI_USER_MULTIPAGE_FAULT",)),
)
RUNTIME_SETS = {
    "runtime-span": ("span-clean", "bounds"),
    "runtime-multipage": ("multipage-clean", "multipage-bounds"),
}
SCHEDULE_SET = ("scheduled-clean", "scheduled-spin", "bounds")
# Fixture mode -> (images 0, 1, 2, division label, unsigned label, family). Other
# bios-fixture modes run the ordinary set.
BIOS_SETS = {
    "division-zero": (("clean", "division-zero", "overflow"), "zero", "none", "ordinary"),
    "division-remainder-zero": (("clean", "division-remainder-zero", "overflow"), "remainder-zero", "none", "ordinary"),
    "division-overflow": (("clean", "bounds", "division-overflow"), "overflow", "none", "ordinary"),
    "division-remainder-min": (("division-remainder-min", "bounds", "overflow"), "remainder-min", "none", "ordinary"),
    "unsigned-valid": (("unsigned-valid", "bounds", "overflow"), "none", "valid", "ordinary"),
    "unsigned-shift-count": (("unsigned-valid", "unsigned-shift-count", "overflow"), "none", "shift-count", "ordinary"),
    "unsigned-conversion-overflow": (
        ("unsigned-valid", "bounds", "unsigned-conversion-overflow"),
        "none",
        "conversion-overflow",
        "ordinary",
    ),
    "unsigned-kernel-trap": (("unsigned-valid", "bounds", "overflow"), "none", "kernel-trap", "ordinary"),
    "program-bad-return": (("bad-return", "bounds", "overflow"), "none", "none", "ordinary"),
    "program-unknown-trap": (("unknown-trap", "bounds", "overflow"), "none", "none", "ordinary"),
    "domain-code": (("foreign-code", "bounds", "overflow"), "none", "none", "ordinary"),
    "domain-stack": (("foreign-stack", "bounds", "overflow"), "none", "none", "ordinary"),
    "schedule": (SCHEDULE_SET, "none", "none", "schedule"),
    "schedule-forged": (SCHEDULE_SET, "none", "none", "schedule"),
    "schedule-context": (SCHEDULE_SET, "none", "none", "schedule"),
    "schedule-root": (SCHEDULE_SET, "none", "none", "schedule"),
    "schedule-mmio": (("apic-read", "scheduled-spin", "bounds"), "none", "none", "schedule"),
    "schedule-softint": (("softint", "scheduled-spin", "bounds"), "none", "none", "schedule"),
    "schedule-fpu": (("fpu", "scheduled-spin", "bounds"), "none", "none", "schedule"),
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
    if kind == "runtime" and mode == "fixture":
        for name, source, role, pages, defines in RUNTIME_BANK:
            result[name] = dict(
                source="tests/kernel-programs/" + source + ".au",
                roots=["library"],
                base=LAYOUT.user_code + role * LAYOUT.code_stride,
                entry="kernel/uefi/user-image-entry.S",
                entry_flags=[value for define in defines for value in ("--defsym", define + "=1")],
                combined=False,
                max_pages=pages,
            )
        return result
    names = ("clean", "bounds", "peer") if dispatcher else ("clean", "bounds")
    for index, name in enumerate(names):
        if kind == "runtime":
            source = name
            entry = "kernel/uefi/user-image-entry.S"
            defines = []
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


def bios_profile(mode):
    console = mode == "console"
    fixture = mode == "bios-fixture"
    flags = ["-DAURORA_INTERACTIVE_CONSOLE"] if console else []
    if fixture:
        flags.append("-DAURORA_BIOS_FIXTURE")
    flags.append("-DAURORA_USER_PROBE_MODE=0")
    programs = BIOS_PROGRAMS if fixture else tuple(row for row in BIOS_PROGRAMS if row[0] in ORDINARY_SET)
    users = {
        name: dict(
            source="tests/kernel-programs/" + source + ".au",
            roots=["library"],
            base=0x1B0000 + index * 4096,
            entry="kernel/program-entry.S",
            entry_flags=[value for define in defines for value in ("--defsym", define + "=1")],
            combined=False,
        )
        for index, (name, source, defines) in enumerate(programs)
    }
    sets = [("default", 0, ORDINARY_SET, "none", "none", "ordinary" if fixture else "")]
    if fixture:
        sets += [
            (case, value, *BIOS_SETS[case]) for case, (_, value) in BIOS_FIXTURE_MODES.items() if case in BIOS_SETS
        ]
    metadata_options = [option for name in users for option in ("--program", name)]
    for name, value, images, division, unsigned, family in sets:
        metadata_options += ["--set", ":".join((name, str(value), division, unsigned, family, ",".join(images)))]
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
        user_metadata_options=metadata_options,
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
        terminal_language="",
        terminal_bridge="",
    )


def uefi_profile(profile_mode, flags):
    # The production image composes exactly the protected program console and,
    # as a second closed Aurora object, the graphical terminal that renders it.
    mode = "program-console" if profile_mode == "production" else profile_mode
    terminal = "-DAURORA_UEFI_GRAPHICAL_TERMINAL" in flags
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
    event = mode == "iommu-event"
    user_mode = "normal"
    if mode.startswith("runtime-") and mode[8:] in ("owned-text", "fixture"):
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
        if "max_pages" not in image:
            image["max_pages"] = IMAGE_POLICIES[image_policy][index]
    if user_mode == "fixture":
        # The kernel admits multipage's three pages for image 0 and 1 of every
        # row; each bank image keeps its own build-time page cap.
        flags.append(f"-DAURORA_RUNTIME_IMAGE_BANK={len(RUNTIME_BANK)}")
        for name, _, role, _, _ in RUNTIME_BANK:
            user_options += ["--image", f"{name}:{role}"]
        for mode_name, chosen in RUNTIME_SETS.items():
            user_options += ["--set", f"{mode_name}:{FIXTURE_MODES[mode_name][1]}:{','.join(chosen)}"]
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
    if event:
        cpp["event-intake"] = "kernel/uefi/event-intake.cpp"
    entry, bridge = "examples/kernel.au", ""
    for enabled, source, adapter in (
        (event, "iommu-event-service", "event-service"),
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
        mode=profile_mode,
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
        + (["kernel-uart"] if console else [])
        + ["language"]
        + (["terminal"] if terminal else [])
        + owned_objects
        + (["framebuffer"] if framebuffer else [])
        + (["event-intake"] if event else []),
        closed=program,
        terminal_language="examples/kernel-graphical-terminal.au" if terminal else "",
        terminal_bridge="kernel/uefi/graphical-terminal-entry.S" if terminal else "",
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


# Machine variants boot their baseline mode's image and selector on other QEMU hardware.
UEFI_VARIANTS = {
    "budget-smp": "budget",
    "pci-devices": "pci",
    "pci-bridge": "pci",
    "acpi-two": "acpi",
}
UEFI_ALIASES = {
    # Rejected in ACPI discovery, before the fixture selector is read.
    "ivrs-missing": "ivrs-fixture",
    # The protected program console is the production image's console.
    "program-console": "production",
}
UEFI_ALIASES.update({mode: image for mode, (image, _) in FIXTURE_MODES.items()})
UEFI_ALIASES.update({variant: UEFI_ALIASES.get(base, base) for variant, base in UEFI_VARIANTS.items()})
# Baseline rows select a fixture image's normal flow; the image has no separate ordinary build.
BASELINE_MODES = frozenset(mode for name, (mode, _, _) in FIXTURES.items() if name.endswith("_baseline"))


def fixture_cases(image):
    """Fault modes of one fixture image, excluding its baseline selector."""
    return tuple(mode for mode, (owner, _) in FIXTURE_MODES.items() if owner == image and mode not in BASELINE_MODES)


# The scheduler baseline's machine variants boot bios-fixture with the baseline selector.
BIOS_VARIANTS = {"schedule-smp": "schedule", "schedule-no-apic": "schedule"}
BIOS_ALIASES = {"no-nx": "normal"}
BIOS_ALIASES.update({mode: image for mode, (image, _) in BIOS_FIXTURE_MODES.items()})
BIOS_ALIASES.update({variant: BIOS_ALIASES.get(base, base) for variant, base in BIOS_VARIANTS.items()})


def selected_modes(image):
    """Every mode that boots one fixture image with a selector: cases, baseline and its machine variants."""
    modes = tuple(mode for mode, (owner, _) in FIXTURE_MODES.items() if owner == image)
    return modes + tuple(variant for variant, base in UEFI_VARIANTS.items() if base in modes)


def serial_fixture_byte(mode):
    image, value = FIXTURE_MODES.get(UEFI_VARIANTS.get(mode, mode), ("", ""))
    return "" if image in FW_CFG_IMAGES else value


def fw_cfg_fixture(mode):
    """QEMU arguments carrying a fw_cfg selector; empty for serial-selector and ordinary modes."""
    image, value = FIXTURE_MODES.get(mode, ("", 0))
    return ["-fw_cfg", f"name=opt/aurora/fixture,string={value}"] if image in FW_CFG_IMAGES else []


def canonical_profile(platform, mode):
    aliases = BIOS_ALIASES if platform == "bios" else UEFI_ALIASES
    return aliases.get(mode, mode)


def select(platform, environment, requested=None):
    """One named profile or fixture mode; UEFI_MODE still names a UEFI profile."""
    if platform == "uefi":
        inherited = environment.get("UEFI_MODE")
        mode = requested or inherited or "normal"
        if inherited and requested and inherited != requested:
            raise ValueError("UEFI_MODE conflicts with requested profile")
        if mode not in {mode for _, variants in UEFI_FAMILIES for mode in variants} | UEFI_ALIASES.keys():
            raise ValueError("Unknown UEFI profile: " + mode)
        return mode
    if platform != "bios":
        raise ValueError("Unknown kernel platform: " + platform)
    if environment.get("UEFI_MODE"):
        raise ValueError("BIOS profiles reject inherited UEFI_MODE")
    mode = requested or "normal"
    if mode not in BIOS_PROFILES and mode not in BIOS_ALIASES:
        raise ValueError("Unknown BIOS profile: " + mode)
    return mode


def profiles():
    result = {"bios/" + mode: bios_profile(mode) for mode in BIOS_PROFILES}
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
    action.add_argument("--canonical", nargs=2, metavar=("PLATFORM", "PROFILE"))
    action.add_argument("--fixture-byte")
    action.add_argument("--bios-fixture-byte")
    args = parser.parse_args()
    if args.bios_fixture_byte:
        print(BIOS_FIXTURE_MODES.get(BIOS_VARIANTS.get(args.bios_fixture_byte, args.bios_fixture_byte), ("", ""))[1])
    elif args.fixture_byte:
        print(serial_fixture_byte(args.fixture_byte))
    elif args.canonical:
        platform, profile = args.canonical
        try:
            print(canonical_profile(platform, select(platform, {}, profile)))
        except ValueError as error:
            parser.error(str(error))
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
