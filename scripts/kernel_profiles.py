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
FIXTURE_MODES = {mode: (image, value) for mode, image, value in FIXTURES.values()}

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
            "framebuffer-record": ["-DAURORA_FRAMEBUFFER_RECORD"],
            "framebuffer-permissions": ["-DAURORA_FRAMEBUFFER_PERMISSIONS"],
            "framebuffer-stale": ["-DAURORA_FRAMEBUFFER_STALE"],
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
            "snapshot-fault": ["-DAURORA_SNAPSHOT_FAULT"],
            "snapshot-cancel": ["-DAURORA_SNAPSHOT_CANCEL"],
            "snapshot-owner": ["-DAURORA_SNAPSHOT_OWNER"],
            "snapshot-stale": ["-DAURORA_SNAPSHOT_STALE"],
            "snapshot-revoked": ["-DAURORA_SNAPSHOT_REVOKED"],
            "snapshot-producer-selector": ["-DAURORA_SNAPSHOT_PRODUCER_SELECTOR"],
            "snapshot-producer-quota": ["-DAURORA_SNAPSHOT_PRODUCER_QUOTA"],
            "snapshot-producer-pages": ["-DAURORA_SNAPSHOT_PRODUCER_PAGES"],
            "snapshot-reply-reserved": ["-DAURORA_SNAPSHOT_REPLY_RESERVED"],
            "snapshot-reply-byte": ["-DAURORA_SNAPSHOT_REPLY_BYTE"],
        },
    ),
    (
        ["-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_CONSOLE"],
        {
            "console": [],
            "console-service-stale": ["-DAURORA_CONSOLE_SERVICE_STALE"],
            "console-service-reentry": ["-DAURORA_CONSOLE_SERVICE_REENTRY"],
            "console-service-timeout": ["-DAURORA_CONSOLE_SERVICE_TIMEOUT"],
            "console-service-report": ["-DAURORA_CONSOLE_SERVICE_REPORT"],
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
            "program-file-call": ["-DAURORA_BLOCKING_CALL", "-DAURORA_FILE_CALL"],
            "program-file-call-fault": ["-DAURORA_BLOCKING_CALL", "-DAURORA_FILE_CALL", "-DAURORA_FILE_CALL_FAULT"],
            "program-file-call-budget": ["-DAURORA_BLOCKING_CALL", "-DAURORA_FILE_CALL", "-DAURORA_FILE_CALL_BUDGET"],
            "program-request-fault": ["-DAURORA_PROGRAM_REQUEST_FAULT"],
            "program-service-fault": ["-DAURORA_PROGRAM_SERVICE_FAULT"],
            "program-completion-fault": ["-DAURORA_PROGRAM_COMPLETION_FAULT"],
            "program-request-budget": ["-DAURORA_PROGRAM_REQUEST_BUDGET"],
            "program-service-budget": ["-DAURORA_PROGRAM_SERVICE_BUDGET"],
            "program-completion-budget": ["-DAURORA_PROGRAM_COMPLETION_BUDGET"],
            "program-pending": ["-DAURORA_PROGRAM_PENDING"],
            "program-owner": ["-DAURORA_PROGRAM_OWNER"],
            "program-ordinal": ["-DAURORA_PROGRAM_ORDINAL"],
            "program-unknown": ["-DAURORA_PROGRAM_UNKNOWN"],
            "program-transaction": ["-DAURORA_PROGRAM_TRANSACTION"],
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
            "ivrs-default": ["-DAURORA_IVRS_DEFAULT"],
            "ivrs-read": ["-DAURORA_IVRS_READ"],
            "ivrs-write": ["-DAURORA_IVRS_WRITE"],
            "ivrs-revoked": ["-DAURORA_IVRS_REVOKED"],
            "ivrs-pair": ["-DAURORA_IVRS_PAIR"],
            "ivrs-alias": ["-DAURORA_IVRS_ALIAS"],
            "ivrs-reserved": ["-DAURORA_IVRS_RESERVED"],
            "ivrs-scope": ["-DAURORA_IVRS_SCOPE"],
            "ivrs-capability": ["-DAURORA_IVRS_CAPABILITY"],
            "ivrs-range": ["-DAURORA_IVRS_RANGE"],
            "ivrs-missing": ["-DAURORA_IVRS_MISSING"],
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
            "bar-read": [],
            "bar-inherited": [],
            "bar-write": ["-DAURORA_BAR_WRITE"],
            "bar-revoked": ["-DAURORA_BAR_REVOKED"],
            "bar-alias": ["-DAURORA_BAR_ALIAS"],
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
            "user-disposal-input": ["-DAURORA_USER_REQUEST_BOUNDS", "-DAURORA_USER_DISPOSAL_INPUT"],
            "user-disposal-output": ["-DAURORA_USER_REQUEST_BOUNDS", "-DAURORA_USER_DISPOSAL_OUTPUT"],
            "user-resume": ["-DAURORA_USER_RESUME"],
            "user-phases": ["-DAURORA_USER_PHASES"],
            "user-context": ["-DAURORA_USER_CONTEXT"],
            "user-retire-pending": ["-DAURORA_USER_RETIRE_PENDING"],
            "user-request-budget": ["-DAURORA_USER_REQUEST_BUDGET"],
            "user-completion-budget": ["-DAURORA_USER_COMPLETION_BUDGET"],
            "user-request-bounds": ["-DAURORA_USER_REQUEST_BOUNDS"],
            "user-completion-bounds": ["-DAURORA_USER_COMPLETION_BOUNDS"],
            "user-request-overflow": ["-DAURORA_USER_REQUEST_OVERFLOW"],
            "user-completion-overflow": ["-DAURORA_USER_COMPLETION_OVERFLOW"],
            "user-pending": ["-DAURORA_USER_PENDING"],
            "user-role": ["-DAURORA_USER_ROLE"],
            "user-phase": ["-DAURORA_USER_PHASE"],
            "user-transaction": ["-DAURORA_USER_TRANSACTION"],
            "user-epoch": ["-DAURORA_USER_EPOCH"],
            "user-root": ["-DAURORA_USER_ROOT"],
            "user-unknown": ["-DAURORA_USER_UNKNOWN"],
            "user-stale-grant": ["-DAURORA_USER_STALE_GRANT"],
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
            "dispatch-budget": ["-DAURORA_DISPATCH_BUDGET"],
            "dispatch-fault": ["-DAURORA_DISPATCH_FAULT"],
            "dispatch-mixed": ["-DAURORA_DISPATCH_MIXED"],
            "dispatch-pending": ["-DAURORA_DISPATCH_PENDING"],
            "dispatch-cross-reply": ["-DAURORA_DISPATCH_CROSS_REPLY"],
            "dispatch-client-owner": ["-DAURORA_DISPATCH_CLIENT_OWNER"],
            "dispatch-stale": ["-DAURORA_DISPATCH_STALE"],
            "dispatch-duplicate": ["-DAURORA_DISPATCH_DUPLICATE"],
            "dispatch-full": ["-DAURORA_DISPATCH_FULL"],
            "dispatch-root": ["-DAURORA_DISPATCH_ROOT"],
            "dispatch-peer-code": ["-DAURORA_DISPATCH_PEER_CODE"],
            "dispatch-policy-cursor": ["-DAURORA_DISPATCH_POLICY_CURSOR"],
            "dispatch-policy-mask": ["-DAURORA_DISPATCH_POLICY_MASK"],
            "dispatch-policy-output": ["-DAURORA_DISPATCH_POLICY_OUTPUT"],
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
            "budget-fault": ["-DAURORA_BUDGET_FAULT"],
            "budget-noapic": ["-DAURORA_BUDGET_NOAPIC"],
            "budget-smp": ["-DAURORA_BUDGET_SMP"],
            "budget-discovery": ["-DAURORA_BUDGET_DISCOVERY"],
            "budget-cache": ["-DAURORA_BUDGET_CACHE"],
            "budget-alias": ["-DAURORA_BUDGET_ALIAS"],
            "budget-pending": ["-DAURORA_BUDGET_PENDING"],
            "budget-forged": ["-DAURORA_BUDGET_FORGED"],
            "budget-root": ["-DAURORA_BUDGET_ROOT"],
            "budget-mmio": ["-DAURORA_BUDGET_MMIO"],
            "budget-softint": ["-DAURORA_BUDGET_SOFTINT"],
            "budget-fpu": ["-DAURORA_BUDGET_FPU"],
            "budget-context": ["-DAURORA_BUDGET_CONTEXT"],
            "budget-epoch": ["-DAURORA_BUDGET_EPOCH"],
            "budget-policy-zero": ["-DAURORA_BUDGET_POLICY_ZERO"],
            "budget-policy-counts": ["-DAURORA_BUDGET_POLICY_COUNTS"],
            "budget-policy-wide": ["-DAURORA_BUDGET_POLICY_WIDE"],
            "budget-policy-output": ["-DAURORA_BUDGET_POLICY_OUTPUT"],
        },
    ),
    (
        ["-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_PCI", "-DAURORA_UEFI_RUNTIME", "-DAURORA_UEFI_IPC"],
        {
            "ipc": [],
            "ipc-fault": ["-DAURORA_IPC_FAULT"],
            "ipc-cancel": ["-DAURORA_IPC_CANCEL"],
            "ipc-owner": ["-DAURORA_IPC_OWNER"],
            "ipc-stale": ["-DAURORA_IPC_STALE"],
            "ipc-version": ["-DAURORA_IPC_VERSION"],
            "ipc-phase": ["-DAURORA_IPC_PHASE"],
            "ipc-transaction": ["-DAURORA_IPC_TRANSACTION"],
            "ipc-site": ["-DAURORA_IPC_SITE"],
            "ipc-unknown": ["-DAURORA_IPC_UNKNOWN"],
            "ipc-root": ["-DAURORA_IPC_ROOT"],
            "ipc-kernel-trap": ["-DAURORA_IPC_KERNEL_TRAP"],
            "ipc-duplicate": ["-DAURORA_IPC_DUPLICATE"],
            "ipc-late": ["-DAURORA_IPC_LATE"],
            "ipc-exhausted": ["-DAURORA_IPC_EXHAUSTED"],
            "ipc-policy-request-input": ["-DAURORA_IPC_POLICY_REQUEST_INPUT"],
            "ipc-policy-request-output": ["-DAURORA_IPC_POLICY_REQUEST_OUTPUT"],
            "ipc-policy-cancel-input": ["-DAURORA_IPC_POLICY_CANCEL_INPUT"],
            "ipc-policy-cancel-output": ["-DAURORA_IPC_POLICY_CANCEL_OUTPUT"],
        },
    ),
    (
        ["-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_PCI", "-DAURORA_UEFI_RUNTIME"],
        {
            "runtime-terminal-input": ["-DAURORA_TERMINAL_EVENT_INPUT"],
            "runtime-terminal-output": ["-DAURORA_TERMINAL_EVENT_OUTPUT"],
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
            "runtime-table-readback": ["-DAURORA_TABLE_READBACK"],
            "runtime-table-reject": ["-DAURORA_TABLE_REJECT"],
            "runtime-table-exhaust": ["-DAURORA_TABLE_EXHAUST"],
            "runtime-table-quarantine": ["-DAURORA_TABLE_QUARANTINE", "-DAURORA_PIN_FAULT"],
        },
    ),
    (
        ["-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_PCI", "-DAURORA_UEFI_RUNTIME", "-DAURORA_UEFI_PINS"],
        {
            "runtime-pin-cancel": ["-DAURORA_PIN_CANCEL"],
            "runtime-pin-fault": ["-DAURORA_PIN_FAULT", "-DAURORA_PIN_LEDGER_TESTING=1"],
            "runtime-pin-stale": ["-DAURORA_PIN_STALE"],
            "runtime-pin-exhaust": ["-DAURORA_PIN_EXHAUST"],
        },
    ),
    (
        ["-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_PCI", "-DAURORA_UEFI_RUNTIME"],
        {
            "runtime": [],
            "runtime-span": [],
            "runtime-multipage": ["-DAURORA_RUNTIME_MULTIPAGE"],
            "runtime-code": ["-DAURORA_RUNTIME_CODE"],
            "runtime-stack": ["-DAURORA_RUNTIME_STACK"],
            "runtime-kernel": ["-DAURORA_RUNTIME_KERNEL"],
            "runtime-window": ["-DAURORA_RUNTIME_WINDOW"],
            "runtime-root": ["-DAURORA_RUNTIME_ROOT"],
            "runtime-kernel-trap": ["-DAURORA_RUNTIME_KERNEL_TRAP"],
            "runtime-entry-stack": ["-DAURORA_RUNTIME_ENTRY_STACK"],
            "runtime-write": ["-DAURORA_RUNTIME_WRITE"],
            "runtime-nx": ["-DAURORA_RUNTIME_NX"],
            "runtime-return": ["-DAURORA_RUNTIME_RETURN"],
            "runtime-unknown": ["-DAURORA_RUNTIME_UNKNOWN"],
            "runtime-syscall": ["-DAURORA_RUNTIME_SYSCALL"],
            "runtime-sysenter": ["-DAURORA_RUNTIME_SYSENTER"],
        },
    ),
    (["-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_PCI"], {"pci": [], "pci-devices": [], "pci-bridge": []}),
    (
        ["-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_PCI"],
        {
            "pci-checksum": ["-DAURORA_PCI_CHECKSUM"],
            "pci-reserved": ["-DAURORA_PCI_RESERVED"],
            "pci-overlap": ["-DAURORA_PCI_OVERLAP"],
            "pci-range": ["-DAURORA_PCI_RANGE"],
            "pci-write": ["-DAURORA_PCI_WRITE"],
            "pci-revoked": ["-DAURORA_PCI_REVOKED"],
            "pci-cycle": ["-DAURORA_PCI_CYCLE"],
        },
    ),
    (["-DAURORA_UEFI_ACPI"], {"acpi": [], "acpi-two": []}),
    (
        ["-DAURORA_UEFI_ACPI"],
        {
            "acpi-duplicate-root": ["-DAURORA_ACPI_DUPLICATE_ROOT"],
            "acpi-changed-header": ["-DAURORA_ACPI_CHANGED_HEADER"],
            "acpi-checksum": ["-DAURORA_ACPI_CHECKSUM"],
            "acpi-bad-entry": ["-DAURORA_ACPI_BAD_ENTRY"],
            "acpi-duplicate": ["-DAURORA_ACPI_DUPLICATE"],
            "acpi-disabled": ["-DAURORA_ACPI_DISABLED"],
            "acpi-bad-source": ["-DAURORA_ACPI_BAD_SOURCE"],
            "acpi-write": ["-DAURORA_ACPI_WRITE"],
            "acpi-revoked": ["-DAURORA_ACPI_REVOKED"],
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
            defines = (
                ["UEFI_USER_" + mode.upper() + "=1"]
                if index == 0
                and mode
                in ("code", "stack", "window", "kernel", "write", "nx", "return", "unknown", "syscall", "sysenter")
                else []
            )
            if mode == "multipage" and index == 1:
                defines.append("UEFI_USER_MULTIPAGE_FAULT=1")
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
                source = "call-client" if index == 0 else "call-snapshot-service"
            if file_call:
                source = "call-client" if index == 0 else "file-call-service"
            entry = "kernel/uefi/ipc-user-entry.S"
            hostile = (index == 0 and mode in ("owner", "stale", "version", "phase", "site", "unknown", "ordinal")) or (
                index == 1 and mode in ("transaction", "mmio", "softint", "fpu", "context")
            )
            if dispatcher and index == 2 and mode == "peer-code":
                hostile = True
            if user_budget and mode == "context":
                hostile = index == 0
            defines = ["IPC_" + mode.upper().replace("-", "_") + "=1"] if hostile else []
            if user_budget and mode == "context" and index == 0:
                defines.append("IPC_CLIENT_CONTEXT=1")
            if blocking_call and index == 0:
                defines.append("CALL_CLIENT=1")
            if (snapshot or program or blocking_call) and index == 1:
                defines.append(
                    "SNAPSHOT_SERVICE=1" if snapshot or (blocking_call and not file_call) else "PROGRAM_NOTE_SERVICE=1"
                )
                if mode in ("reply-reserved", "reply-byte"):
                    defines.append("SNAPSHOT_" + mode.upper().replace("-", "_") + "=1")
        result[name] = dict(
            source="tests/kernel-programs/" + source + ".au",
            roots=["library"] + (["kernel/policies"] if snapshot or program or blocking_call else []),
            base=LAYOUT.user_code + index * LAYOUT.code_stride,
            entry=entry,
            entry_flags=[value for define in defines for value in ("--defsym", define)],
            combined=((snapshot or program or blocking_call) and index == 1) or (blocking_call and index == 0),
        )
    return result


def bios_profile(mode, controls):
    division = controls.get("KERNEL_TEST_DIVISION", "none")
    unsigned = controls.get("KERNEL_TEST_UNSIGNED", "none")
    schedule = controls.get("KERNEL_TEST_SCHEDULE") == "1"
    console = controls.get("KERNEL_CONSOLE") == "1"
    flags = ["-DAURORA_INTERACTIVE_CONSOLE"] if console else []
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
        user_metadata_options=["--division-fixture", division, "--unsigned-fixture", unsigned],
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
        + (["serial-input", "kernel-interactive-console"] if console else []),
        image_options=["--console"] if console else [],
        admission="",
        checks=[],
    )


def uefi_profile(mode, flags):
    runtime = mode.startswith(("runtime", "ipc", "budget", "dispatch", "user-", "program-", "snapshot"))
    ipc = mode.startswith(("ipc", "budget", "dispatch", "user-", "program-", "snapshot"))
    console_region = mode.startswith("runtime-console-region")
    owned_text = mode.startswith("runtime-owned-text") or console_region
    budget = mode.startswith(("budget", "dispatch", "user-", "program-")) or owned_text
    file_call = mode.startswith("program-file-call")
    blocking_call = mode.startswith("user-call") or file_call
    dispatcher = mode.startswith(("dispatch", "user-")) and not blocking_call
    user_budget = mode.startswith(("user-", "program-"))
    program = mode.startswith("program-")
    snapshot = mode.startswith("snapshot")
    console = mode == "console" or mode.startswith("console-service-")
    graphical = mode in ("graphical-console", "graphical-console-capture")
    framebuffer = mode in ("framebuffer", "framebuffer-record", "framebuffer-permissions", "framebuffer-stale")
    event = mode.startswith("iommu-event-")
    user_mode = "normal"
    if mode.startswith("runtime-") and mode[8:] in (
        "span",
        "multipage",
        "owned-text",
        "code",
        "stack",
        "kernel",
        "window",
        "write",
        "nx",
        "return",
        "unknown",
        "syscall",
        "sysenter",
    ):
        user_mode = mode[8:]
    if owned_text:
        user_mode = (
            "console-region-fixture"
            if mode == "runtime-console-region-fixture"
            else "console-region"
            if console_region
            else "owned-text"
        )
    if snapshot and mode in ("snapshot-owner", "snapshot-reply-reserved", "snapshot-reply-byte"):
        user_mode = mode[9:]
    if program and mode in ("program-owner", "program-ordinal", "program-unknown", "program-transaction"):
        user_mode = mode[8:]
    if mode in ("user-unknown", "user-context", "user-resume"):
        user_mode = mode[5:]
    if mode == "dispatch-peer-code":
        user_mode = "peer-code"
    if mode.startswith("budget-") and mode[7:] in ("mmio", "softint", "fpu", "context"):
        user_mode = mode[7:]
    if mode.startswith("ipc-") and mode[4:] in ("owner", "version", "phase", "transaction", "site", "unknown"):
        user_mode = mode[4:]
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
        )
        if runtime
        else {}
    )
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
        if blocking_call
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
        if mode == "user-resume" or blocking_call or console_region:
            runtime_flags += ["--defsym", "AURORA_USER_RESUME=1"]
        if blocking_call:
            runtime_flags += ["--defsym", "AURORA_BLOCKING_CALL=1"]
        assembly["runtime-entry"] = dict(source="kernel/uefi/runtime-entry.S", flags=["--64"] + runtime_flags)
        assembly["runtime-exceptions"] = dict(
            source="kernel/exceptions.S",
            flags=["--64", "--defsym", "AURORA_RELATIVE_ONLY=1"]
            + (["--defsym", "AURORA_BLOCKING_CALL=1"] if blocking_call else [])
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
        (mode == "owned-bytes", "owned-bytes", "owned-bytes"),
        (snapshot or (blocking_call and not file_call), "snapshot", "snapshot"),
        (console, "console-service", "console-service"),
        (graphical, "graphical-console", "graphical-console"),
    ):
        if enabled:
            entry, bridge = "examples/kernel-" + source + ".au", "kernel/uefi/" + adapter + "-entry.S"
    image_options = ["--ipc-policy"] if ipc else []
    if mode == "runtime-multipage":
        image_options += ["--multipage"]
    if owned_text:
        image_options += ["--owned-text"]
    if console_region:
        image_options += ["--console-region"]
    if mode == "budget-noapic":
        image_options += ["--budget-noapic"]
    if snapshot or (blocking_call and not file_call):
        image_options += ["--snapshot"] + (["--call-snapshot"] if blocking_call else [])
    if mode == "owned-bytes":
        image_options += ["--owned-bytes"]
    if graphical:
        image_options += ["--graphical-console"]
    if event:
        image_options += ["--iommu-event-observe" if mode == "iommu-event-observe" else "--iommu-event"]
    if mode.startswith(("user-request-", "user-completion-", "user-disposal-")) or mode in (
        "user-retire-pending",
        "user-resume",
        "user-stale-grant",
    ):
        image_options += ["--disposal-policy"]
    admission = (
        "program"
        if program
        else "console"
        if console
        else "graphical"
        if graphical
        else "framebuffer"
        if framebuffer
        else "event"
        if event
        else ""
    )
    checks = (
        (["owned-bytes"] if mode == "owned-bytes" else [])
        + (["snapshot"] if snapshot else [])
        + (["note"] if program else [])
        + (["call"] if blocking_call and not file_call else [])
        + (["tables"] if mode.startswith("runtime-table-") else [])
        + (["ivrs"] if mode.startswith("ivrs-") else [])
        + (["nvme"] if mode == "bar-prepare" else [])
    )
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
        image_options=image_options,
        admission=admission,
        checks=checks,
    )


UEFI_ALIASES = {"bar-inherited": "bar-read", "pci-devices": "pci", "pci-bridge": "pci", "acpi-two": "acpi"}
UEFI_ALIASES.update({mode: image for mode, (image, _) in FIXTURE_MODES.items()})
BIOS_ALIASES = {"schedule-smp": "schedule", "schedule-no-apic": "schedule", "no-nx": "normal"}


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
    args = parser.parse_args()
    if args.fixture_byte:
        print(FIXTURE_MODES.get(args.fixture_byte, ("", ""))[1])
    elif args.select:
        try:
            print(select(args.select, os.environ))
        except ValueError as error:
            parser.error(str(error))
    else:
        rows = list(keyval_rows("profiles", profiles()))
        rows += keyval_rows("layout", layout_metadata())
        rows += keyval_rows("image_policies", {name: list(values) for name, values in IMAGE_POLICIES.items()})
        rows += keyval_rows(
            "aliases",
            {"bios/" + key: "bios/" + value for key, value in BIOS_ALIASES.items()}
            | {"uefi/" + key: "uefi/" + value for key, value in UEFI_ALIASES.items()},
        )
        args.meson_output.write_text("\n".join(rows) + "\n")
