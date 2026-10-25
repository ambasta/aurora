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
# byte. The loader fixture images read it at loader entry, echo it and hand it
# over in one handoff word: platform-fixture's loader cases inject before
# ExitBootServices, while firmware owns the UART, and the display, device,
# storage and text images co-host subsystems that each need their row from the
# first phase, including interactive console sessions no harness can send a
# byte to. The Event harness writes serial output to a file.
LOADER_FIXTURE_IMAGES = frozenset(
    ("platform-fixture", "display-fixture", "device-fixture", "storage-fixture", "text-fixture")
)
FW_CFG_IMAGES = LOADER_FIXTURE_IMAGES | {"iommu-event"}
BIOS_FIXTURE_MODES = {
    mode: (image, value) for name, (mode, image, value) in FIXTURES.items() if name.startswith("bios_")
}

# Base flags plus bounded variants mirror the existing admitted profiles.
UEFI_FAMILIES = [
    ([], {"normal": []}),
    (
        ["-maccumulate-outgoing-args", "-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_PCI", "-DAURORA_UEFI_IOMMU_EVENT"],
        {"iommu-event": []},
    ),
    # The framebuffer cases and the standalone graphical console (plain and
    # capture), selected by a fw_cfg row read at loader entry.
    (
        [
            "-DAURORA_UEFI_ACPI",
            "-DAURORA_UEFI_GRAPHICAL_CONSOLE",
            "-DAURORA_UEFI_GRAPHICAL_FIXTURE",
            "-DAURORA_UEFI_GRAPHICAL_CAPTURE",
            "-DAURORA_UEFI_FRAMEBUFFER",
            "-DAURORA_UEFI_FRAMEBUFFER_FIXTURE",
            "-DAURORA_UEFI_FRAMEBUFFER_CAPTURE",
        ],
        {"display-fixture": ["-DAURORA_DISPLAY_FIXTURE"]},
    ),
    # The UEFI console, its service faults and owned bytes, selected likewise.
    (
        [
            "-DAURORA_UEFI_ACPI",
            "-DAURORA_UEFI_CONSOLE",
            "-DAURORA_CONSOLE_SERVICE_FIXTURE",
            "-DAURORA_UEFI_OWNED_BYTES",
        ],
        {"device-fixture": ["-DAURORA_DEVICE_FIXTURE"]},
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
        },
    ),
    # The protected file-call console and the owned-text and console-region
    # applications, selected by a fw_cfg row read at loader entry; each row runs
    # its former image's user images (TEXT_ROWS) from one packed bank.
    (
        [
            "-DAURORA_UEFI_ACPI",
            "-DAURORA_UEFI_PCI",
            "-DAURORA_UEFI_RUNTIME",
            "-DAURORA_UEFI_IPC",
            "-DAURORA_UEFI_SERVICE_BUDGET",
            "-DAURORA_UEFI_USER_BUDGET",
            "-DAURORA_UEFI_PROGRAM_CONSOLE",
            "-DAURORA_BLOCKING_CALL",
            "-DAURORA_FILE_CALL",
            "-DAURORA_OWNED_TEXT",
            "-DAURORA_CONSOLE_REGION",
        ],
        {"text-fixture": ["-DAURORA_RUNTIME_FIXTURE", "-DAURORA_TEXT_FIXTURE"]},
    ),
    # The RAM file service, the RAM scratchpad console, the blocking snapshot
    # call and the snapshot producer, selected likewise (STORAGE_ROWS).
    (
        [
            "-DAURORA_UEFI_ACPI",
            "-DAURORA_UEFI_PCI",
            "-DAURORA_UEFI_RUNTIME",
            "-DAURORA_UEFI_IPC",
            "-DAURORA_UEFI_SERVICE_BUDGET",
            "-DAURORA_UEFI_USER_BUDGET",
            "-DAURORA_RAM_FILE",
            "-DAURORA_RAM_SCRATCHPAD_CONSOLE",
            "-DAURORA_BLOCKING_CALL",
            "-DAURORA_UEFI_SNAPSHOT",
        ],
        {
            "storage-fixture": [
                "-DAURORA_RUNTIME_FIXTURE",
                "-DAURORA_SCRATCHPAD_FIXTURE",
                "-DAURORA_SNAPSHOT_FIXTURE",
                "-DAURORA_STORAGE_FIXTURE",
            ]
        },
    ),
    # The IPC, service-budget, dispatcher, user-run and resume compositions, each
    # selected at boot; its user images are SERVICE_BANK.
    (
        [
            "-DAURORA_UEFI_ACPI",
            "-DAURORA_UEFI_PCI",
            "-DAURORA_UEFI_RUNTIME",
            "-DAURORA_UEFI_IPC",
            "-DAURORA_UEFI_SERVICE_BUDGET",
            "-DAURORA_UEFI_DISPATCH",
            "-DAURORA_UEFI_USER_BUDGET",
            "-DAURORA_USER_RESUME",
        ],
        {
            "service-fixture": [
                "-DAURORA_RUNTIME_FIXTURE",
                "-DAURORA_SERVICE_FIXTURE",
                "-DAURORA_IPC_FIXTURE",
                "-DAURORA_BUDGET_FIXTURE",
                "-DAURORA_DISPATCH_FIXTURE",
                "-DAURORA_USER_FIXTURE",
            ],
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
    # Loader handoff, ACPI, PCI, BAR, NVMe-preparation and IVRS cases, selected by
    # a fw_cfg file read at loader entry.
    (
        [
            "-DAURORA_UEFI_ACPI",
            "-DAURORA_UEFI_PCI",
            "-DAURORA_UEFI_BAR_CAPTURE",
            "-DAURORA_UEFI_NVME_PREPARE",
            "-DAURORA_UEFI_IVRS",
        ],
        {"platform-fixture": ["-DAURORA_PLATFORM_FIXTURE"]},
    ),
]

_RAM = [
    "-DAURORA_UEFI_ACPI",
    "-DAURORA_UEFI_PCI",
    "-DAURORA_UEFI_RUNTIME",
    "-DAURORA_UEFI_IPC",
    "-DAURORA_UEFI_SERVICE_BUDGET",
    "-DAURORA_UEFI_USER_BUDGET",
    "-DAURORA_RAM_FILE",
]
_CALL = _RAM[:-1] + ["-DAURORA_BLOCKING_CALL"]
_TEXT = ["-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_PCI", "-DAURORA_UEFI_RUNTIME", "-DAURORA_UEFI_SERVICE_BUDGET"]
_FILE = _RAM[:-1] + ["-DAURORA_UEFI_PROGRAM_CONSOLE", "-DAURORA_BLOCKING_CALL", "-DAURORA_FILE_CALL"]
# The separate images the packed test images replaced, as build data only: each
# one's user image recipes, metadata and page policy are what its rows still run.
FORMER_IMAGES = {
    "user-ram-file": _RAM,
    "user-ram-file-fixture": _RAM + ["-DAURORA_RUNTIME_FIXTURE"],
    "ram-scratchpad-console": _RAM + ["-DAURORA_RAM_SCRATCHPAD_CONSOLE"],
    "ram-scratchpad-console-fixture": _RAM + ["-DAURORA_RAM_SCRATCHPAD_CONSOLE", "-DAURORA_SCRATCHPAD_FIXTURE"],
    "user-call-fixture": _CALL + ["-DAURORA_RUNTIME_FIXTURE"],
    "snapshot-fixture": [
        "-DAURORA_UEFI_SNAPSHOT",
        "-DAURORA_UEFI_ACPI",
        "-DAURORA_UEFI_PCI",
        "-DAURORA_UEFI_RUNTIME",
        "-DAURORA_UEFI_IPC",
        "-DAURORA_RUNTIME_FIXTURE",
        "-DAURORA_SNAPSHOT_FIXTURE",
    ],
    "runtime-owned-text-fixture": _TEXT + ["-DAURORA_OWNED_TEXT", "-DAURORA_RUNTIME_FIXTURE"],
    "runtime-console-region-fixture": _TEXT
    + ["-DAURORA_OWNED_TEXT", "-DAURORA_CONSOLE_REGION", "-DAURORA_RUNTIME_FIXTURE"],
    "program-file-call": _FILE,
    "program-file-call-fixture": _FILE + ["-DAURORA_RUNTIME_FIXTURE"],
}
# Packed test image -> row name (exact, or a prefix ending in "_") -> former image.
PACKED_ROWS = {
    "storage-fixture": {
        "ram_baseline": "user-ram-file",
        "ram_": "user-ram-file-fixture",
        "scratchpad_baseline": "ram-scratchpad-console",
        "scratchpad_fixture": "ram-scratchpad-console-fixture",
        "call_": "user-call-fixture",
        "snapshot_": "snapshot-fixture",
    },
    "text-fixture": {
        "text_": "runtime-owned-text-fixture",
        "console_": "runtime-console-region-fixture",
        "file_baseline": "program-file-call",
        "file_": "program-file-call-fixture",
    },
}


def former_image(image, row):
    """The former image whose users and page policy one packed row runs."""
    rows = PACKED_ROWS[image]
    if row in rows:
        return rows[row]
    return next(former for prefix, former in rows.items() if prefix.endswith("_") and row.startswith(prefix))


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
# service-fixture's user image bank: (name, source, domain image it is linked
# for, entry defines, whether its metadata carries the service-timer compiled
# and context ranges). Each one-page image keeps the source and probe wrapper
# its former image had; budget-client is ipc-client with the budget metadata.
SERVICE_BANK = (
    ("ipc-client", "ipc-client", 0, (), False),
    ("ipc-service", "ipc-service", 1, (), False),
    ("budget-client", "ipc-client", 0, (), True),
    ("budget-service", "budget-service", 1, ("IPC_PROBES",), True),
    ("dispatch-client-a", "dispatch-client-a", 0, (), True),
    ("dispatch-service", "dispatch-service", 1, (), True),
    ("dispatch-client-b", "dispatch-client-b", 2, ("IPC_PROBES",), True),
    ("user-client-a", "user-budget-client-a", 0, ("IPC_PROBES",), True),
    ("user-client-b", "user-budget-client-b", 2, (), True),
    ("checksum-client-a", "user-checksum-client", 0, (), True),
    ("checksum-client-b", "user-checksum-client", 2, (), True),
)
# Row family (row-name prefix) -> the bank images acting as images 0, 1 (and 2).
SERVICE_SETS = {
    "ipc_": ("ipc-client", "ipc-service"),
    "budget_": ("budget-client", "budget-service"),
    "dispatch_": ("dispatch-client-a", "dispatch-service", "dispatch-client-b"),
    "user_": ("user-client-a", "dispatch-service", "user-client-b"),
    "resume_": ("checksum-client-a", "dispatch-service", "checksum-client-b"),
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
    if kind == "ipc" and mode == "service":
        for name, source, role, defines, _ in SERVICE_BANK:
            result[name] = dict(
                source="tests/kernel-programs/" + source + ".au",
                roots=["library"],
                base=LAYOUT.user_code + role * LAYOUT.code_stride,
                entry="kernel/uefi/ipc-user-entry.S",
                entry_flags=[value for define in defines for value in ("--defsym", define + "=1")],
                combined=False,
                max_pages=1,
            )
        return result
    for index, name in enumerate(("clean", "bounds")):
        if kind == "runtime":
            source = name
            entry = "kernel/uefi/user-image-entry.S"
            defines = []
        else:
            source = "ipc-client" if index == 0 else "ipc-service"
            if program:
                source = "program-upper-client" if index == 0 else "program-stream-service"
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
            defines = []
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
            reflection_only=False,
            local_symbols=False,
            abi=False,
            byte_stubs=False,
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
        sealed=False,
        optimization="2",
        languages={},
    )


OWNED_USER_MODES = ("owned-text", "console-region", "console-region-fixture")


def packed_users(image, formers):
    """One packed bank of every former image's user images, deduplicated by recipe."""
    users, sets = {}, []
    for row, (mode, owner, value) in FIXTURES.items():
        if owner != image:
            continue
        chosen = []
        for name, user in formers[former_image(image, row)]["users"].items():
            slot = Path(user["source"]).stem
            if users.setdefault(slot, user) != user:
                raise ValueError(f"{image}: two {slot} user images with different recipes")
            chosen.append(slot)
        sets.append((mode, value, chosen))
    return users, sets


def packed_profile(image, flags):
    """A test image co-hosting former images' compositions, each run by its rows."""
    formers = {name: uefi_profile(name, FORMER_IMAGES[name]) for name in dict.fromkeys(PACKED_ROWS[image].values())}
    users, sets = packed_users(image, formers)
    # The kernel admits, per row, its former image's page policy; the widest
    # bounds the layout and each slot keeps its image's own link-time cap.
    policies = {
        next(flag.split("=", 1)[1] for flag in profile["flags"] if flag.startswith("-DAURORA_RUNTIME_IMAGE_POLICY="))
        for profile in formers.values()
    }
    widest = min(
        (
            name
            for name, pages in IMAGE_POLICIES.items()
            if all(all(a >= b for a, b in zip(pages, IMAGE_POLICIES[other])) for other in policies)
        ),
        key=lambda name: sum(IMAGE_POLICIES[name]),
    )
    flags = [
        *flags,
        "-DAURORA_RUNTIME_IMAGE_POLICY=" + widest,
        "-DAURORA_RUNTIME_ROW_POLICY",
        f"-DAURORA_RUNTIME_IMAGE_BANK={len(users)}",
        f"-DAURORA_RUNTIME_BANK_PAGES={sum(user['max_pages'] for user in users.values())}",
    ]
    user_options = ["--service-budget"]
    for name, user in users.items():
        role = (user["base"] - LAYOUT.user_code) // LAYOUT.code_stride
        extra = [key for key in ("budget", "owned", "console") if user[key]]
        user_options += ["--image", ":".join([name, str(role), *extra, f"pages={user['max_pages']}"])]
    for mode, value, chosen in sets:
        user_options += ["--set", f"{mode}:{value}:{','.join(chosen)}"]
    union = lambda key: {name: item for profile in formers.values() for name, item in profile[key].items()}
    assembly = union("assembly")
    for name in ("runtime-entry", "runtime-exceptions"):
        words = [profile["assembly"][name]["flags"] for profile in formers.values()]
        defines = dict.fromkeys(w[i + 1] for w in words for i in range(len(w)) if w[i] == "--defsym")
        assembly[name] = dict(
            assembly[name], flags=["--64"] + [word for define in defines for word in ("--defsym", define)]
        )
    primary = formers["ram-scratchpad-console" if image == "storage-fixture" else "program-file-call"]
    languages = {}
    if image == "storage-fixture":
        # The snapshot producer is a second closed Aurora object with its own
        # bridge, local symbols and import policy; the scratchpad object exports
        # the kernel policies every row calls.
        languages["producer"] = dict(
            source="examples/kernel-snapshot.au",
            bridge="kernel/uefi/snapshot-producer-entry.S",
            roots=["kernel/policies", "library"],
        )
    owned_objects = list(dict.fromkeys(name for profile in formers.values() for name in profile["owned_objects"]))
    link = ["payload-entry", "memory", "payload", "acpi", "pci", "runtime", "runtime-entry", "runtime-exceptions"]
    return dict(
        platform="uefi",
        mode=image,
        flags=flags,
        language=primary["language"],
        roots=["kernel/policies", "library"],
        bridge=primary["bridge"],
        cpp=union("cpp"),
        assembly=assembly,
        users=users,
        user_kind="ipc",
        user_mode="bank",
        user_options=user_options,
        user_metadata_options=[],
        link=link + ["language"] + list(languages) + owned_objects,
        closed=primary["closed"],
        sealed=True,
        optimization="s",
        languages=languages,
        owned_objects=owned_objects,
    )


def uefi_profile(profile_mode, flags):
    if profile_mode in PACKED_ROWS:
        return packed_profile(profile_mode, flags)
    # The production image composes exactly the protected program console and,
    # as a second closed Aurora object, the graphical terminal that renders it.
    mode = "program-console" if profile_mode == "production" else profile_mode
    terminal = "-DAURORA_UEFI_GRAPHICAL_TERMINAL" in flags
    scratchpad = mode in ("ram-scratchpad-console", "ram-scratchpad-console-fixture")
    scratchpad_fixture = mode == "ram-scratchpad-console-fixture"
    service = mode == "service-fixture"
    runtime = scratchpad or service or mode.startswith(("runtime", "user-", "program-", "snapshot"))
    ipc = scratchpad or service or mode.startswith(("user-", "program-", "snapshot"))
    console_region = mode.startswith("runtime-console-region")
    owned_text = mode.startswith("runtime-owned-text") or console_region
    budget = scratchpad or service or mode.startswith(("user-", "program-")) or owned_text
    file_call = mode.startswith("program-file-call")
    blocking_call = mode.startswith("user-call") or file_call
    ram_file = scratchpad or mode in ("user-ram-file", "user-ram-file-fixture")
    user_budget = scratchpad or service or mode.startswith(("user-", "program-"))
    program = mode.startswith("program-")
    snapshot = mode.startswith("snapshot")
    console = owned_bytes = mode == "device-fixture"
    graphical = framebuffer = mode == "display-fixture"
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
    if service:
        user_mode = "service"
    user_options = [
        option
        for enabled, option in (
            (budget and not owned_text, "--service-budget"),
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
    owned_users = user_mode in OWNED_USER_MODES
    for index, (name, image) in enumerate(users.items()):
        if "max_pages" not in image:
            image["max_pages"] = IMAGE_POLICIES[image_policy][index]
        # Per-image compiler options: closed callers, owned text and RAM file
        # images have independently checked linked graphs (ABI facts).
        owned = owned_users and name == "clean"
        call_client = image["combined"] and blocking_call
        image.update(
            reflection_only=(call_client and name == "clean") or owned or ram_file,
            local_symbols=owned,
            abi=program or call_client or owned or ram_file,
            byte_stubs=owned,
            # Kernel-read metadata: service-timer ranges, owned-byte and Console sites.
            budget=budget and not owned_text,
            owned=owned,
            console=owned and user_mode.startswith("console-region"),
        )
    if user_mode == "fixture":
        # The kernel admits multipage's three pages for image 0 and 1 of every
        # row; each bank image keeps its own build-time page cap.
        flags.append(f"-DAURORA_RUNTIME_IMAGE_BANK={len(RUNTIME_BANK)}")
        for name, _, role, _, _ in RUNTIME_BANK:
            user_options += ["--image", f"{name}:{role}"]
        for mode_name, chosen in RUNTIME_SETS.items():
            user_options += ["--set", f"{mode_name}:{FIXTURE_MODES[mode_name][1]}:{','.join(chosen)}"]
    if service:
        # Every row names its images; only budget-bearing images carry timer ranges.
        flags.append(f"-DAURORA_RUNTIME_IMAGE_BANK={len(SERVICE_BANK)}")
        for name, _, role, _, timed in SERVICE_BANK:
            user_options += ["--image", f"{name}:{role}" + (":budget" if timed else "")]
        for row, (mode_name, image, value) in FIXTURES.items():
            if image == "service-fixture":
                chosen = next(names for family, names in SERVICE_SETS.items() if row.startswith(family))
                user_options += ["--set", f"{mode_name}:{value}:{','.join(chosen)}"]
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
        if service or blocking_call or ram_file or console_region:
            runtime_flags += ["--defsym", "AURORA_USER_RESUME=1"]
        if blocking_call or ram_file:
            runtime_flags += ["--defsym", "AURORA_BLOCKING_CALL=1"]
        if mode == "runtime-fixture":
            runtime_flags += ["--defsym", "AURORA_RUNTIME_PROBES=1"]
        if service:
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
    if owned_bytes or snapshot or (blocking_call and not file_call):
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
        (program, "program-console", "program-note"),
        (file_call, "program-file-call", "program-file-call"),
        (scratchpad, "ram-scratchpad-console", "ram-scratchpad-console"),
        (snapshot or (blocking_call and not file_call), "snapshot", "snapshot"),
        (console, "console-service", "console-service"),
        (graphical, "graphical-console", "graphical-console"),
    ):
        if enabled:
            entry, bridge = "examples/kernel-" + source + ".au", "kernel/uefi/" + adapter + "-entry.S"
    # Further closed Aurora objects, each with its own private bridge, local
    # symbols and import policy (imports:STEM): the production terminal painter,
    # and the services co-hosted by the display and device fixture images.
    languages = {}
    for enabled, stem, source, adapter, roots in (
        (terminal, "terminal", "graphical-terminal", "graphical-terminal", ["library"]),
        (framebuffer, "display", "display-service", "display-service", ["kernel/policies", "library"]),
        (owned_bytes, "owned-bytes", "owned-bytes", "owned-bytes", ["kernel/policies", "library"]),
    ):
        if enabled:
            languages[stem] = dict(
                source="examples/kernel-" + source + ".au", bridge="kernel/uefi/" + adapter + "-entry.S", roots=roots
            )
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
        + list(languages)
        + owned_objects
        + (["framebuffer"] if framebuffer else [])
        + (["event-intake"] if event else []),
        closed=program,
        # Closed objects keep local symbols and referenced reflection only.
        sealed=program or scratchpad,
        # The closed supervisor and the scratchpad keep the protected Console size recipe.
        optimization="s" if program or scratchpad else "2",
        languages=languages,
        owned_objects=owned_objects,
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
    # The protected program console is the production image's console.
    "program-console": "production",
}
UEFI_ALIASES.update({mode: image for mode, (image, _) in FIXTURE_MODES.items()})
UEFI_ALIASES.update({variant: UEFI_ALIASES.get(base, base) for variant, base in UEFI_VARIANTS.items()})
# Baseline rows select a fixture image's normal flow; the image has no separate ordinary build.
BASELINE_MODES = frozenset(mode for name, (mode, _, _) in FIXTURES.items() if name.endswith("_baseline"))


def family_modes(image, family=""):
    """Modes of one fixture image whose row names start with `family` (all rows by default)."""
    return tuple(
        mode
        for name, (mode, owner, _) in FIXTURES.items()
        if owner == image and name.startswith(family) and not name.startswith("bios_")
    )


def fixture_cases(image, family=""):
    """Fault modes of one fixture image (or one row family of it), excluding its baseline selector."""
    return tuple(mode for mode in family_modes(image, family) if mode not in BASELINE_MODES)


# The scheduler baseline's machine variants boot bios-fixture with the baseline selector.
BIOS_VARIANTS = {"schedule-smp": "schedule", "schedule-no-apic": "schedule"}
BIOS_ALIASES = {"no-nx": "normal"}
BIOS_ALIASES.update({mode: image for mode, (image, _) in BIOS_FIXTURE_MODES.items()})
BIOS_ALIASES.update({variant: BIOS_ALIASES.get(base, base) for variant, base in BIOS_VARIANTS.items()})


def selected_modes(image, family=""):
    """Every mode booting one fixture image (or row family) with a selector: cases, baseline, machine variants."""
    modes = family_modes(image, family)
    return modes + tuple(variant for variant, base in UEFI_VARIANTS.items() if base in modes)


def serial_fixture_byte(mode):
    image, value = FIXTURE_MODES.get(UEFI_VARIANTS.get(mode, mode), ("", ""))
    return "" if image in FW_CFG_IMAGES else value


def fw_cfg_fixture(mode):
    """QEMU arguments carrying a fw_cfg selector; empty for serial-selector and ordinary modes."""
    image, value = FIXTURE_MODES.get(UEFI_VARIANTS.get(mode, mode), ("", 0))
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
