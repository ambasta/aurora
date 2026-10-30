#!/usr/bin/env python3
"""Exact named kernel profiles shared by Meson and thin command selectors.

This is build data, not guest authorization. Event execution retains its
separate reviewed model, firmware, admission and supervised-plan requirements.
"""

import argparse
import os
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kernel_layout import IMAGE_POLICIES, LAYOUT, metadata as layout_metadata, read_table

FIXTURES = read_table(Path(__file__).resolve().parents[1] / "kernel/uefi/runtime-fixtures.inc")


def check_fixture_families(rows):
    """Keep every fixture image within its explicitly admitted selector interval(s)."""
    values = [value for _, _, value in rows.values()]
    if len(set(values)) != len(values) or not all(0 < value < 256 for value in values):
        raise ValueError("Fixture selectors must be distinct bytes")
    for image in {image for _, image, _ in rows.values()}:
        family = sorted(value for _, owner, value in rows.values() if owner == image)
        if image in ("program-fixture", "storage-fixture", "snapshot-call-fixture"):
            # These loaders/selectors admit only their explicit closed intervals;
            # moving a row family does not renumber existing selectors.
            intervals = {
                "program-fixture": (
                    ("program_append_construct_fault", "program_append_service_backing"),
                    ("program_request_fault", "program_append_site"),
                ),
                "storage-fixture": (("ram_baseline", "scratchpad_fixture"), ("namespace_console", "namespace_fixture")),
                "snapshot-call-fixture": (("call_baseline", "snapshot_reply_reserved"),),
            }[image]
            expected = [value for first, last in intervals for value in range(rows[first][2], rows[last][2] + 1)]
        else:
            expected = list(range(family[0], family[0] + len(family)))
        if family != expected:
            raise ValueError("Fixture family differs from its admitted selector intervals: " + image)


check_fixture_families(FIXTURES)
FIXTURE_MODES = {
    mode: (image, value) for name, (mode, image, value) in FIXTURES.items() if not name.startswith("bios_")
}
# Process-image rows that run a run list: the valid volume's selector plus a
# case word (fw_cfg opt/aurora/case) naming runs/<case> in that volume (the
# compiler volume for COMPILER_CASES, the self-host volume for
# SELF_HOST_CASES). Each run is (watchdog ticks, flags, memory quota in frames
# or 0 for all, volume path, arguments as shell words); flag 1 faults the
# kernel during the run's first kernel call, flag 2 checks that the load walk
# rejects edited tables, flag 4 walks the whole space after every memory call,
# commit and kernel access and flag 8 makes each tick 128 times longer
# (kernel/uefi/process.md#run-lists).
ROOT = Path(__file__).resolve().parents[1]
# One process per hosted memory-runtime case (tests/host-files/memory.golden),
# each walked after every memory call unless it churns, then the compiler with
# no arguments, and the failure path under small quotas: a probe whose first
# owner does not fit and the compiler, whose memory runtime cannot start.
MEMORY_GOLDEN = ROOT / "tests/host-files/memory.golden"
MEMORY_RUNS = tuple(
    (128, 4 if index in (0, 1, 3) else 0, 0, "bin/memory", key)
    for index, key in enumerate(line.split("\t", 1)[0] for line in MEMORY_GOLDEN.read_text().splitlines())
)
# One process per HostFiles case (tests/host-files/cases.golden, then the
# 64 MiB output of limits.golden) of the cat, probe and sort programs, over
# the volume's copy of the cases' tree, except the cases that need what the
# volume lacks by design: symlinks (link, dirlink), a FIFO, /dev and a closed
# standard stream.
FILES_GOLDEN = [ROOT / "tests/host-files" / name for name in ("cases.golden", "limits.golden")]
FILES_PROGRAMS = {"cat": "bin/cat", "probe": "bin/probe", "sort": "bin/sort"}
FILES_ABSENT = {"link", "dirlink", "fifo", "!closed"}


def files_case(key):
    words = shlex.split(key)
    return (
        words[0] in FILES_PROGRAMS
        and not FILES_ABSENT & {part for word in words for part in word.split("/")}
        and not any(word.startswith("/dev") for word in words)
    )


FILES_RUNS = tuple(
    (128, 0, 0, FILES_PROGRAMS[key.split()[0]], key)
    for key in (line.split("\t", 1)[0] for golden in FILES_GOLDEN for line in golden.read_text().splitlines())
    if files_case(key)
)
# The --target aurora compiler compiling for Linux in the guest: host-sort to
# an object in the working directory (the volume root; HostFiles creates no
# directories, on Linux either), which must equal the hosted build's
# host-sort.o, then each rejected source of COMPILE_GOLDEN (the volume's
# rejections/case-NNNN.au), whose diagnostics and exit status must be the
# hosted compiler's. A second successful run compiles and statically links
# the same source for Aurora, without any host binary tool.
COMPILE_GOLDEN = "tests/kernel-process/compile.golden"
COMPILE_FLAGS = "aurorac --emit-object --target linux --runtime-root /runtime/linux"
COMPILE_RUNS = (
    (128, 0, 0, "bin/aurorac", COMPILE_FLAGS + " examples/host-sort.au -o host-sort.o"),
    (
        128,
        0,
        0,
        "bin/aurorac",
        "aurorac --emit-executable --target aurora --runtime-root /runtime/aurora "
        "examples/host-sort.au -o host-sort-aurora-native",
    ),
) + tuple(
    (32, 0, 0, "bin/aurorac", f"{COMPILE_FLAGS} rejections/case-{index:04d}.au -o case-{index:04d}.o")
    for index, _ in enumerate((ROOT / COMPILE_GOLDEN).read_text().splitlines())
)
# The compiler compiling itself in the guest (release suite): the --target
# aurora compiler, given the configured driver and the module tree its own
# build stages, emits the object C1 emits of the compiler (aurorac-stage2.o,
# the hosted build's stage-2 object) with C1's flags. Flag 8: ticks of 2^31
# counts (about 34 s under QEMU), so the budget is about 9 minutes.
SELF_HOST_RUNS = (
    (
        16,
        8,
        0,
        "bin/aurorac",
        "aurorac --emit-object --local-symbols --referenced-reflection-only --target linux "
        "--runtime-root /runtime/linux --module-root /modules aurorac.au -o aurorac-stage2.o",
    ),
)
PROCESS_CASES = {
    "process-run": (
        1,
        (
            (32, 2, 0, "bin/probe", "probe print hello eprint oops exit failure"),
            (32, 0, 0, "bin/probe-linux", "probe print hello"),
            (32, 0, 0, "bin/recurse", "recurse"),
            (4, 0, 0, "bin/hostile", "hostile spin"),
            (8, 0, 0, "bin/isolation-1", "write-code"),
            (8, 0, 0, "bin/isolation-2", "run-stack"),
            (8, 0, 0, "bin/isolation-3", "cli"),
            (8, 0, 0, "bin/isolation-4", "port-in"),
            (8, 0, 0, "bin/isolation-5", "kernel-read"),
            (8, 0, 0, "bin/isolation-6", "bad-call"),
            (8, 0, 0, "bin/isolation-7", "kernel-print"),
            (8, 0, 0, "bin/isolation-8", "raise-vector"),
            (8, 4, 0, "bin/isolation-9", "past-mapping"),
            (8, 4, 0, "bin/isolation-10", "bad-unmap"),
            (8, 4, 0, "bin/isolation-11", "moved-away"),
            (8, 4, 0, "bin/isolation-12", "heap-read"),
            (8, 0, 0, "bin/isolation-13", "read-unmapped"),
            (8, 0, 0, "bin/isolation-14", "read-code"),
            (8, 0, 0, "bin/isolation-15", "path-kernel"),
            (8, 0, 0, "bin/isolation-16", "write-gap"),
            (8, 0, 0, "bin/isolation-17", "forged-ids"),
            (32, 0, 0, "bin/probe", "probe print 'two words' exit success"),
            # A long-tick run (flag 8) ends within its first tick.
            (1, 8, 0, "bin/probe", "probe print 'two words' exit success"),
        ),
    ),
    "process-hostile": (
        2,
        (
            (8, 0, 0, "bin/elf-wx", "elf"),
            (8, 0, 0, "bin/elf-interp", "elf"),
            (8, 0, 0, "bin/elf-entry", "elf"),
            (8, 0, 0, "bin/elf-overlap", "elf"),
            (8, 0, 0, "bin/missing", "elf"),
            (8, 0, 0, "bin/hostile", "hostile"),
            (8, 1, 0, "bin/probe", "probe print hello"),
        ),
    ),
    "process-memory": (
        3,
        MEMORY_RUNS
        + (
            (128, 0, 0, "bin/aurorac", "aurorac"),
            (32, 4, 140, "bin/memory", "memory 100000 10 0 ok A ok B"),
            (32, 0, 1, "bin/aurorac", "aurorac"),
        ),
    ),
    "process-files": (4, FILES_RUNS),
    "process-compile": (5, COMPILE_RUNS),
    "process-self-host": (6, SELF_HOST_RUNS),
    # Exactly two resident processes at a time. The first three pairs keep
    # disjoint quotas; the final pair proves an all-free reservation blocks a
    # second load even though its frames have not been physically allocated.
    "process-lifecycle": (
        7,
        (
            (64, 0, 4096, "bin/lifecycle", "lifecycle A"),
            (64, 0, 4096, "bin/lifecycle", "lifecycle B"),
            (64, 0, 4096, "bin/lifecycle", "lifecycle A"),
            (64, 0, 4096, "bin/lifecycle", "lifecycle fault"),
            (64, 0, 4096, "bin/lifecycle", "lifecycle A"),
            (1, 0, 4096, "bin/lifecycle", "lifecycle spin"),
            (64, 0, 0, "bin/lifecycle", "lifecycle A"),
            (64, 0, 4096, "bin/lifecycle", "lifecycle B"),
        ),
    ),
    "process-service": (
        8,
        (
            (64, 0, 16384, "bin/file-service", "file-service"),
            (
                128,
                0,
                8192,
                "bin/probe",
                "probe create tree/shared write @1 v1 commit @1 file tree/shared "
                "create tree/shared write @5 v2 commit @5 read @4 0 file tree/shared read @9 0 "
                "create tree/pending fill @11 5",
            ),
            (
                128,
                0,
                8192,
                "bin/probe",
                "probe file tree/shared read @1 0 read 65 0 file tree/pending "
                "create tree/reused write @5 z commit @5 file tree/reused read @8 0",
            ),
            (1, 0, 8192, "bin/hostile", "hostile spin"),
            (128, 0, 8192, "bin/probe", "probe file tree/shared read @1 0"),
            (128, 0, 8192, "bin/lifecycle", "lifecycle bulk"),
            (128, 0, 8192, "bin/isolation-6", "raw-write"),
            (128, 0, 8192, "bin/isolation-6", "raw-quota"),
            (128, 0, 8192, "bin/isolation-6", "raw-quota-small"),
            (128, 0, 8192, "bin/probe", "probe file tree/quota-reused read @1 0 file tree/shared read @3 0"),
            (1, 0, 8192, "bin/lifecycle", "lifecycle rpc"),
            (128, 0, 8192, "bin/probe", "probe file tree/rpc-pending file tree/shared read @2 0"),
            (8, 0, 8192, "bin/isolation-6", "forge-service"),
            (8, 0, 8192, "bin/file-service", "file-service unauthorized"),
            (128, 0, 8192, "bin/probe", "probe file tree/shared read @1 0"),
        ),
    ),
    "process-service-hostile": (
        9,
        tuple(
            row
            for mode in ("zero", "stale", "window", "tx", "count", "reply", "reserved", "die", "spin", "duplicate")
            for row in (
                (8, 0, 8192, "bin/isolation-6", "svc-" + mode),
                (128, 0, 8192, "bin/probe", "probe file tree/no-such-file"),
            )
        )
        + (
            (64, 0, 16384, "bin/file-service", "file-service"),
            (128, 0, 8192, "bin/probe", "probe create tree/restart write @1 fresh commit @1"),
            (128, 0, 8192, "bin/probe", "probe file tree/restart read @1 0"),
            (8, 0, 8192, "bin/isolation-6", "block-zero"),
            (8, 0, 8192, "bin/isolation-6", "block-forge"),
            (8, 0, 8192, "bin/isolation-6", "block-reserved"),
            (128, 0, 8192, "bin/probe", "probe file tree/restart read @1 0"),
        ),
    ),
    "process-xfs": (
        10,
        (
            (8, 0, 8192, "bin/isolation-6", "svc-block-forge"),
            (128, 0, 8192, "bin/probe", "probe file tree/no-such-file"),
            (16, 8, 16384, "bin/file-service", "file-service"),
            (16, 8, 8192, "bin/lifecycle", "lifecycle disk"),
            (8, 0, 8192, "bin/isolation-6", "block-forge"),
            (128, 0, 8192, "bin/lifecycle", "lifecycle disk"),
        ),
    ),
    "process-xfs-clean": (
        11,
        (
            (16, 8, 16384, "bin/file-service", "file-service"),
            (
                16,
                8,
                8192,
                "bin/probe",
                "probe file /disk/hello read @1 64 close @1 file /disk/pattern read @4 9001 close @4 "
                "create tree/clean-check write @7 retained commit @7 file tree/clean-check read @10 0",
            ),
            (128, 0, 8192, "bin/lifecycle", "lifecycle disk-clean"),
            (128, 0, 8192, "bin/lifecycle", "lifecycle disk-clean"),
            (
                128,
                0,
                8192,
                "bin/probe",
                "probe file /disk/hello read @1 64 close @1 file tree/clean-check read @4 0 create /disk/pattern",
            ),
        ),
    ),
}
# Recovery remains a private, explicit history-image fixture. Its first boot
# role is writable; all subsequent clients receive only ordinary file authority.
PROCESS_CASES["process-xfs-recover"] = (
    12,
    (
        (16, 8, 16384, "bin/xfs-recover", "xfs-recover"),
        PROCESS_CASES["process-xfs-clean"][1][0],
        (8, 0, 8192, "bin/isolation-6", "writer-stale-write"),
        (8, 0, 8192, "bin/isolation-6", "writer-stale-flush"),
        *PROCESS_CASES["process-xfs-clean"][1][1:],
    ),
)
PROCESS_CASES["process-xfs-recover-pair"] = (
    41,
    (
        *PROCESS_CASES["process-xfs-recover"][1][:4],
        (16, 8, 8192, "bin/lifecycle", "lifecycle recovered-pair"),
    ),
)
# Both mounted rows use production startup and ordinary HostFiles clients.
for mode, case, argument in (
    ("process-xfs-mounted", 17, "mounted"),
    ("process-xfs-mounted-small", 39, "mounted-small"),
):
    PROCESS_CASES[mode] = (
        case,
        (
            (64, 0, 32768, "bin/file-service-mounted", "file-service"),
            (16, 8, 8192, "bin/lifecycle", "lifecycle " + argument),
        ),
    )
PROCESS_CASES["process-xfs-mounted-loss"] = (
    40,
    (
        *PROCESS_CASES["process-xfs-mounted"][1],
        (64, 0, 32768, "bin/file-service", "file-service"),
        (16, 8, 8192, "bin/lifecycle", "lifecycle mounted-absent"),
    ),
)
# The run lists of the compiler volume (\\aurora\\compiler, kernel/uefi/loader-fixture.hpp)
# and of the self-host volume (\\aurora\\selfhost).
COMPILER_CASES = frozenset({3, 5})
SELF_HOST_CASES = frozenset({6})
# Guest memory of the rows that need more than the UEFI default: one memory
# case keeps 4 GiB mapped (committed on first touch, but charged in full).
# The fresh source file service owns its copied volume, index and up to a
# 64 MiB output independently of the client. Keep that full capacity; even
# the basic and compile rows now need room for both resident processes.
# The self-host row's compiler charges about 600 MiB at its peak.
PROCESS_MEMORY = {
    "process-run": "256M",
    "process-hostile": "256M",
    "process-compile": "256M",
    "process-memory": "5G",
    "process-files": "256M",
    "process-self-host": "1G",
    "process-service": "256M",
    "process-xfs": "256M",
    "process-xfs-clean": "256M",
    "process-xfs-recover": "256M",
    "process-xfs-recover-pair": "256M",
    "process-xfs-mounted": "256M",
    "process-xfs-mounted-small": "256M",
    "process-xfs-mounted-loss": "256M",
    "process-service-hostile": "256M",
    "production": "256M",
    "program-console": "256M",
}
FIXTURE_MODES.update({mode: FIXTURE_MODES["process-volume"] for mode in PROCESS_CASES})
# These images read their selector from a QEMU fw_cfg file instead of a serial
# byte. The loader fixture images read it at loader entry, echo it and hand it
# over in one handoff word: platform-fixture's loader cases inject before
# ExitBootServices, while firmware owns the UART, and the display, device,
# storage, snapshot-call and text images co-host subsystems that each need their row from the
# first phase, including interactive console sessions no harness can send a
# byte to. The Event harness writes serial output to a file.
LOADER_FIXTURE_IMAGES = frozenset(
    (
        "platform-fixture",
        "display-fixture",
        "device-fixture",
        "storage-fixture",
        "snapshot-call-fixture",
        "text-fixture",
        "process-fixture",
    )
)
FW_CFG_IMAGES = LOADER_FIXTURE_IMAGES | {"iommu-event"}
BIOS_FIXTURE_MODES = {
    mode: (image, value) for name, (mode, image, value) in FIXTURES.items() if name.startswith("bios_")
}

# Base flags plus bounded variants mirror the existing admitted profiles.
UEFI_FAMILIES = [
    ([], {"normal": []}),
    # The boot volume, frame allocator, export and processes (kernel/uefi/process.md),
    # selected by a fw_cfg row and case word read at loader entry.
    (
        [],
        {
            "process-fixture": [
                "-DAURORA_UEFI_ACPI",
                "-DAURORA_UEFI_PCI",
                "-DAURORA_UEFI_NVME",
                "-DAURORA_PROCESS_FIXTURE",
                "-maccumulate-outgoing-args",
            ]
        },
    ),
    (
        ["-maccumulate-outgoing-args", "-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_PCI", "-DAURORA_UEFI_IOMMU_EVENT"],
        {"iommu-event": []},
    ),
    (
        ["-maccumulate-outgoing-args", "-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_PCI", "-DAURORA_UEFI_NVME"],
        {"nvme": []},
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
            "production": [
                "-DAURORA_PRODUCTION",
                "-DAURORA_UEFI_GRAPHICAL_TERMINAL",
                "-DAURORA_UEFI_NVME",
                "-DAURORA_PROGRAM_APPEND_CALL",
                "-DAURORA_BLOCKING_CALL",
            ],
            "program-fixture": [
                "-DAURORA_RUNTIME_FIXTURE",
                "-DAURORA_PROGRAM_FIXTURE",
                "-DAURORA_PROGRAM_APPEND_CALL",
                "-DAURORA_BLOCKING_CALL",
            ],
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
    # The RAM file service, scratchpad and protected namespace, selected likewise.
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
            "-DAURORA_NAMESPACE_CONSOLE",
            "-DAURORA_NAMESPACE_FIXTURE",
        ],
        {
            "storage-fixture": [
                "-DAURORA_RUNTIME_FIXTURE",
                "-DAURORA_SCRATCHPAD_FIXTURE",
                "-DAURORA_STORAGE_FIXTURE",
            ]
        },
    ),
    # The ordinary blocking Call and snapshot producer, without the RAM console.
    (
        [
            "-DAURORA_UEFI_ACPI",
            "-DAURORA_UEFI_PCI",
            "-DAURORA_UEFI_RUNTIME",
            "-DAURORA_UEFI_IPC",
            "-DAURORA_UEFI_SERVICE_BUDGET",
            "-DAURORA_UEFI_USER_BUDGET",
            "-DAURORA_BLOCKING_CALL",
            "-DAURORA_UEFI_SNAPSHOT",
        ],
        {"snapshot-call-fixture": ["-DAURORA_RUNTIME_FIXTURE", "-DAURORA_SNAPSHOT_FIXTURE"]},
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
    "namespace-console": _RAM + ["-DAURORA_NAMESPACE_CONSOLE"],
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
        "namespace_": "namespace-console",
    },
    "snapshot-call-fixture": {
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
    namespace=False,
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
            if namespace:
                source = "namespace-client" if index == 0 else "namespace-service"
            entry = (
                "kernel/uefi/namespace-client-entry.S"
                if namespace and index == 0
                else "kernel/uefi/namespace-service-entry.S"
                if namespace and index == 1
                else "kernel/uefi/ram-scratchpad-client-entry.S"
                if scratchpad and index == 0
                else "kernel/uefi/program-client-entry.S"
                if program and not file_call and index == 0
                else "kernel/uefi/program-service-entry.S"
                if program and not file_call and index == 1
                else "kernel/uefi/ipc-user-entry.S"
            )
            defines = []
            if (blocking_call or ram_file) and not (scratchpad or namespace) and index == 0:
                defines.append("CALL_CLIENT=1")
            if ram_file and not namespace and index == 1:
                defines.append("SERVE_SERVICE=1")
            if (snapshot or program or blocking_call) and index == 1 and not (program and not file_call):
                defines.append(
                    "SNAPSHOT_SERVICE=1" if snapshot or (blocking_call and not file_call) else "PROGRAM_NOTE_SERVICE=1"
                )
        result[name] = dict(
            source=(
                "examples/kernel-namespace-client.au"
                if namespace and index == 0
                else "examples/kernel-ram-scratchpad-client.au"
                if scratchpad and index == 0
                else "tests/kernel-programs/" + source + ".au"
            ),
            roots=["library"] + (["kernel/policies"] if snapshot or program or blocking_call else []),
            base=LAYOUT.user_code + index * LAYOUT.code_stride,
            entry=entry,
            entry_flags=[value for define in defines for value in ("--defsym", define)],
            combined=ram_file
            or (program and not file_call and index == 0)
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
    if image == "snapshot-call-fixture":
        # This small ordinary caller has a one-page link/packing cap. The row's
        # Call admission stays unchanged; a larger fixture must fail the link.
        users["call-snapshot-client"] = dict(users["call-snapshot-client"], max_pages=1)
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
    primary = formers[
        {
            "storage-fixture": "ram-scratchpad-console",
            "snapshot-call-fixture": "snapshot-fixture",
            "text-fixture": "program-file-call",
        }[image]
    ]
    languages = {}
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
        sealed=primary["sealed"],
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
    namespace = mode == "namespace-console"
    scratchpad = mode in ("ram-scratchpad-console", "ram-scratchpad-console-fixture")
    scratchpad_fixture = mode == "ram-scratchpad-console-fixture"
    service = mode == "service-fixture"
    runtime = namespace or scratchpad or service or mode.startswith(("runtime", "user-", "program-", "snapshot"))
    ipc = namespace or scratchpad or service or mode.startswith(("user-", "program-", "snapshot"))
    console_region = mode.startswith("runtime-console-region")
    owned_text = mode.startswith("runtime-owned-text") or console_region
    budget = namespace or scratchpad or service or mode.startswith(("user-", "program-")) or owned_text
    file_call = mode.startswith("program-file-call")
    blocking_call = mode.startswith("user-call") or file_call
    append_call = "-DAURORA_PROGRAM_APPEND_CALL" in flags
    ram_file = namespace or scratchpad or mode in ("user-ram-file", "user-ram-file-fixture")
    user_budget = namespace or scratchpad or service or mode.startswith(("user-", "program-"))
    program = mode.startswith("program-")
    snapshot = mode.startswith("snapshot")
    console = owned_bytes = mode == "device-fixture"
    graphical = framebuffer = mode == "display-fixture"
    event = mode == "iommu-event"
    nvme = mode in ("nvme", "process-fixture") or profile_mode == "production"
    process = mode == "process-fixture" or profile_mode == "production"
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
            namespace=namespace,
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
        "named_namespace"
        if namespace
        else "multipage"
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
            reflection_only=append_call or (call_client and name == "clean") or owned or ram_file,
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
        if service or blocking_call or append_call or ram_file or console_region:
            runtime_flags += ["--defsym", "AURORA_USER_RESUME=1"]
        if blocking_call or append_call or ram_file:
            runtime_flags += ["--defsym", "AURORA_BLOCKING_CALL=1"]
        if mode == "runtime-fixture":
            runtime_flags += ["--defsym", "AURORA_RUNTIME_PROBES=1"]
        if service:
            runtime_flags += ["--defsym", "AURORA_IPC_PROBES=1"]
        assembly["runtime-entry"] = dict(source="kernel/uefi/runtime-entry.S", flags=["--64"] + runtime_flags)
        assembly["runtime-exceptions"] = dict(
            source="kernel/exceptions.S",
            flags=["--64", "--defsym", "AURORA_RELATIVE_ONLY=1"]
            + (["--defsym", "AURORA_BLOCKING_CALL=1"] if blocking_call or append_call or ram_file else [])
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
    if nvme:
        cpp["nvme"] = "kernel/uefi/nvme.cpp"
    if event:
        cpp["event-intake"] = "kernel/uefi/event-intake.cpp"
    if process:
        cpp["process"] = "kernel/uefi/process.cpp"
        assembly["process-user"] = dict(source="kernel/uefi/process-user.S", flags=["--64"])
        assembly["process-exceptions"] = dict(
            source="kernel/exceptions.S",
            flags=[
                "--64",
                "--defsym",
                "AURORA_RELATIVE_ONLY=1",
                "--defsym",
                "AURORA_PROCESS_CALL=1",
                "--defsym",
                "AURORA_PROCESS_TRAPS=1",
            ],
        )
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
    if profile_mode == "production":
        bridge = "kernel/uefi/production-program-entry.S"
    # Further closed Aurora objects, each with its own private bridge, local
    # symbols and import policy (imports:STEM): the production terminal painter,
    # and the services co-hosted by the display and device fixture images.
    languages = {}
    for enabled, stem, source, adapter, roots in (
        (terminal, "terminal", "graphical-terminal", "graphical-terminal", ["library"]),
        (framebuffer, "display", "display-service", "display-service", ["kernel/policies", "library"]),
        (owned_bytes, "owned-bytes", "owned-bytes", "owned-bytes", ["kernel/policies", "library"]),
        (process, "process-policy", "process", "process", ["kernel/policies", "library"]),
        (process, "budget-root", "budget-root", "budget-root", ["kernel/policies"]),
        (profile_mode == "production", "execution", "execution", "execution", ["kernel/policies"]),
    ):
        if enabled:
            languages[stem] = dict(
                source="examples/kernel-" + source + ".au", bridge="kernel/uefi/" + adapter + "-entry.S", roots=roots
            )
            if stem == "process-policy" and profile_mode == "production":
                languages[stem]["bridge"] = "kernel/uefi/production-process-entry.S"
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
        + (["event-intake"] if event else [])
        + (["nvme"] if nvme else [])
        + (["process", "process-user", "process-exceptions"] if process else []),
        closed=program,
        # Closed objects keep local symbols and referenced reflection only.
        sealed=program or scratchpad,
        # The closed supervisor and the scratchpad keep the protected Console size recipe.
        optimization="s" if program or scratchpad else "2",
        languages=languages,
        owned_objects=owned_objects,
        esp=PRODUCTION_ESP if profile_mode == "production" else PROCESS_ESP if process else {},
    )


# The process image's ESP volumes (scripts/kernel_volume.py arguments over
# repository files): the valid volume, an unsorted index with a valid checksum
# and an empty file. Every listed repository file is a build input.
PROCESS_VOLUME_FILES = ("examples/core_math.au", "examples/host-sort.au")
# Programs (--program PATH=KIND:NAME, a build product: aurora for --target
# aurora, linux for the hosted Linux build, assembly for GNU as) and header-only ELF files (--elf
# PATH=EDITS over the writer's admission image) the run lists name. The
# compiler volume carries the compiler and the memory probe for cases 3 and 5.
PROCESS_COMPILER_PROGRAMS = {
    "bin/aurorac": "aurora:aurorac",
    "bin/memory": "aurora:host-memory-probe",
    "bin/file-service": "aurora:file-service",
}
# It also holds what the compile row reads: both runtime roots and the program.
PROCESS_RUNTIME_FILES = ("runtime/linux/aurora/host.au", "runtime/linux/aurora/memory.au")
PROCESS_COMPILER_FILES = ("examples/host-sort.au", "runtime/aurora/aurora/host.au", *PROCESS_RUNTIME_FILES)
PROCESS_PROGRAMS = {
    "bin/probe": "aurora:host-files-probe",
    "bin/xfs-recover": "aurora:xfs-recover",
    "bin/hostile": "aurora:process-hostile",
    "bin/lifecycle": "aurora:process-lifecycle",
    "bin/file-service": "aurora:file-service",
    "bin/file-service-mounted": "aurora:file-service-mounted",
    "bin/recurse": "assembly:process-recurse",
    "bin/isolation-1": "assembly:process-isolation-1",
    "bin/isolation-2": "assembly:process-isolation-2",
    "bin/isolation-3": "assembly:process-isolation-3",
    "bin/isolation-4": "assembly:process-isolation-4",
    "bin/isolation-5": "assembly:process-isolation-5",
    "bin/isolation-6": "assembly:process-isolation-6",
    "bin/isolation-7": "assembly:process-isolation-7",
    "bin/isolation-8": "assembly:process-isolation-8",
    "bin/isolation-9": "assembly:process-isolation-9",
    "bin/isolation-10": "assembly:process-isolation-10",
    "bin/isolation-11": "assembly:process-isolation-11",
    "bin/isolation-12": "assembly:process-isolation-12",
    "bin/isolation-13": "assembly:process-isolation-13",
    "bin/isolation-14": "assembly:process-isolation-14",
    "bin/isolation-15": "assembly:process-isolation-15",
    "bin/isolation-16": "assembly:process-isolation-16",
    "bin/isolation-17": "assembly:process-isolation-17",
    "bin/cat": "aurora:host-files-cat",
    "bin/sort": "aurora:host-sort",
    "bin/probe-linux": "linux:host-files-probe",
}
PROCESS_ELVES = {
    "bin/elf-wx": "p1.flags=7",
    "bin/elf-interp": "p3.type=3",
    "bin/elf-entry": "entry=0x400000",
    "bin/elf-overlap": "p2.vaddr=0x401000",
}
PROCESS_ESP = {
    "volume": [word for path in PROCESS_VOLUME_FILES for word in ("--file", path)]
    + ["--text", "aurora/empty=", "--host-files-tree"]
    + [word for path, program in PROCESS_PROGRAMS.items() for word in ("--program", path + "=" + program)]
    + [word for path, edits in PROCESS_ELVES.items() for word in ("--elf", path + "=" + edits)]
    + [
        word
        for case, runs in PROCESS_CASES.values()
        if case not in COMPILER_CASES | SELF_HOST_CASES
        for ticks, flags, quota, path, arguments in runs
        for word in ("--run", f"{case}:{ticks}:{flags}:{quota}:{path}:{arguments}")
    ],
    "compiler": [
        word for path, program in PROCESS_COMPILER_PROGRAMS.items() for word in ("--program", path + "=" + program)
    ]
    + [word for path in PROCESS_COMPILER_FILES for word in ("--file", path)]
    + ["--program", "runtime/aurora/aurora/memory.au=source:aurora-memory"]
    + ["--rejections", "rejections=" + COMPILE_GOLDEN]
    + [
        word
        for case, runs in PROCESS_CASES.values()
        if case in COMPILER_CASES
        for ticks, flags, quota, path, arguments in runs
        for word in ("--run", f"{case}:{ticks}:{flags}:{quota}:{path}:{arguments}")
    ],
    # The configured compiler driver (source:aurorac) and the compiler modules
    # (--compiler-modules, kernel-images/meson.build) as the build stages them.
    "selfhost": [
        "--program",
        "bin/aurorac=aurora:aurorac",
        "--program",
        "bin/file-service=aurora:file-service",
        "--program",
        "bin/file-service-mounted=aurora:file-service-mounted",
        "--program",
        "aurorac.au=source:aurorac",
    ]
    + [word for path in PROCESS_RUNTIME_FILES for word in ("--file", path)]
    + ["--compiler-modules", "modules"]
    + [
        word
        for case, runs in PROCESS_CASES.values()
        if case in SELF_HOST_CASES
        for ticks, flags, quota, path, arguments in runs
        for word in ("--run", f"{case}:{ticks}:{flags}:{quota}:{path}:{arguments}")
    ],
    "corrupt": ["--raw-order"] + [word for path in reversed(PROCESS_VOLUME_FILES) for word in ("--file", path)],
    "empty": ["--empty"],
}


# The shipped production volume contains programs and source, never run lists or
# hostile kernel fixtures. Every command resolves through the same retained file
# service; the short source alias fits the console's established 64-byte line.
PRODUCTION_ESP = {
    "system": [
        "--program",
        "bin/aurorac=aurora:aurorac",
        "--program",
        "bin/file-service=aurora:file-service",
        "--program",
        "bin/file-service-mounted=aurora:file-service-mounted",
        "--program",
        "bin/xfs-recover=aurora:xfs-recover",
        "--program",
        "bin/cat=aurora:host-files-cat",
        "--program",
        "bin/sort=aurora:host-sort",
        "--program",
        "sort.au=source:host-sort",
        "--program",
        "runtime/aurora/aurora/memory.au=source:aurora-memory",
        "--program",
        "input.txt=source:host-sort-input",
    ]
    + [word for path in ("runtime/aurora/aurora/host.au", *PROCESS_RUNTIME_FILES) for word in ("--file", path)]
}


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
    "process": "process-volume process-volume-corrupt process-volume-empty process-volume-map process-run "
    "process-hostile process-memory process-files process-compile process-lifecycle process-service "
    "process-service-hostile process-xfs",
    # The release suite's row (tests/native/meson.build), minutes under TCG.
    "self-host": "process-self-host",
}
# The QEMU limit of a guest row in seconds (scripts/kernel-uefi-smoke.sh), 60 unless listed.
# The independent memory/files goldens boot a fresh source-service companion
# per case (28/35 executions of one compiled ELF). Their original 60s outer
# bound expired during healthy progress; process watchdog budgets are unchanged.
GUEST_TIMEOUTS = {
    "process-self-host": 900,
    "process-xfs": 900,
    "process-xfs-clean": 900,
    "process-xfs-recover": 900,
    "process-xfs-recover-pair": 900,
    "process-xfs-mounted": 900,
    "process-xfs-mounted-small": 900,
    "process-xfs-mounted-loss": 900,
    "process-memory": 180,
    "process-files": 180,
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


def mounted_recovery_outcome(prefix):
    """Closed completed-command prefixes of the reviewed 777-byte mounted plan.

    Equal-LSN homes are replayed idempotently, even when their bytes are already
    on disk. The returned changed sectors exclude those already durable bytes.
    """
    if not 0 <= prefix <= 16:
        raise ValueError("Mounted recovery prefix outside 0..16")
    target = 64 if prefix <= 11 else 777
    if prefix <= 8 or prefix == 16:
        return 0, 1, target, set()
    if prefix == 9:
        return 2, 3, target, {524361, 524362}
    if prefix <= 11:
        return 3, 3, target, {100, 524363, 524364}
    changed = {524365}
    if prefix < 15:
        changed.add(524366)
    if prefix < 14:
        changed.add(96)
    if prefix < 13:
        changed.add(100)
    return 4, 3, target, changed


RECOVERY_CUT_CASES = {"flush-1": 13, "flush-2": 14, "flush-3": 15, "write-1": 16}
MOUNTED_CUT_CASES = {
    **{f"write-{ordinal}": 17 + ordinal for ordinal in range(1, 17)},
    **{f"flush-{ordinal}": 33 + ordinal for ordinal in range(1, 6)},
}


def fw_cfg_fixture(mode, *, recovery_cut=None, mounted_cut=None):
    """QEMU arguments carrying a fw_cfg selector; empty for serial-selector and ordinary modes."""
    if recovery_cut is not None and (mode != "process-xfs-recover" or recovery_cut not in RECOVERY_CUT_CASES):
        raise ValueError("Recovery cut requires the closed private recovery fixture")
    if mounted_cut is not None and (mode != "process-xfs-mounted" or mounted_cut not in MOUNTED_CUT_CASES):
        raise ValueError("Mounted cut requires the closed private mounted fixture")
    image, value = FIXTURE_MODES.get(UEFI_VARIANTS.get(mode, mode), ("", 0))
    if image not in FW_CFG_IMAGES:
        return []
    number = RECOVERY_CUT_CASES[recovery_cut] if recovery_cut else PROCESS_CASES.get(mode, (0,))[0]
    if mounted_cut:
        number = MOUNTED_CUT_CASES[mounted_cut]
    case = ["-fw_cfg", f"name=opt/aurora/case,string={number}"] if mode in PROCESS_CASES else []
    return ["-fw_cfg", f"name=opt/aurora/fixture,string={value}", *case]


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
    action.add_argument("--guest-timeout")
    args = parser.parse_args()
    if args.guest_timeout:
        print(GUEST_TIMEOUTS.get(args.guest_timeout, 60))
    elif args.bios_fixture_byte:
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
        rows += keyval_rows("guest_timeouts", GUEST_TIMEOUTS)
        rows += keyval_rows("image_policies", {name: list(values) for name, values in IMAGE_POLICIES.items()})
        rows += keyval_rows(
            "aliases",
            {"bios/" + key: "bios/" + value for key, value in BIOS_ALIASES.items()}
            | {"uefi/" + key: "uefi/" + value for key, value in UEFI_ALIASES.items()},
        )
        args.meson_output.write_text("\n".join(rows) + "\n")
