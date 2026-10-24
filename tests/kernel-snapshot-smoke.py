#!/usr/bin/env python3
"""Exact ordered evidence for the finite copied-snapshot fixture, not a general parser."""

from pathlib import Path
import importlib.util
import json
import re
import sys

spec = importlib.util.spec_from_file_location("ipc_smoke", Path(__file__).with_name("kernel-uefi-ipc-smoke.py"))
ipc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ipc)
need = ipc.need
PRODUCER_FAILURES = ("snapshot-producer-selector", "snapshot-producer-quota", "snapshot-producer-pages")
SUCCESS = ("snapshot", "snapshot-fault", "snapshot-cancel") + PRODUCER_FAILURES
MODES = SUCCESS + (
    "snapshot-owner",
    "snapshot-stale",
    "snapshot-revoked",
    "snapshot-reply-reserved",
    "snapshot-reply-byte",
)
# Modes that boot the shared snapshot-fixture image, from the one fixture table.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import kernel_profiles  # noqa: E402

FIXTURE_MODES = tuple(mode for mode, (image, _) in kernel_profiles.FIXTURE_MODES.items() if image == "snapshot-fixture")
DONE = (1 << 64) - 1
STACK = r"(\d+)"
SUFFIX = ipc.SUFFIX


def expected(mode, metadata, arena):
    # Test oracle only: the live kernel obtains bytes and continuations from
    # compiled producer/service/client code, never from these native expectations.
    rows = []
    kernel = arena + 0x11000
    grant, transaction = 1, 2

    def record(operation, first, second=0):
        rows.append(f"AURORA_UEFI_IPC_{operation}: transaction={transaction} first={first} second={second}")

    def enter(slot, phase, value, offset=0, *, fault=False, failure=None):
        root = arena + 0x90000 + slot * 0x10000
        image = metadata["bounds" if slot else "clean"]
        ticket = 0 if phase in (0, 6) else transaction
        rows.append(f"AURORA_UEFI_IPC_ENTER: slot={slot} phase={phase} root={root} grant={grant} transaction={ticket}")
        vector, pc = (6, image["bounds_pc"]) if fault else (129, image["return_pc"])
        rows.append(
            f"AURORA_UEFI_DOMAIN_EVENT: vector={vector} error=0 pc={pc} cpl=3 "
            f"root={root} frame={arena + 0x88000 - 176} cr2=0"
        )
        if not fault:
            claim_slot = 1 if failure == "snapshot-owner" else slot
            rows.append(
                f"AURORA_UEFI_IPC_ENVELOPE: phase={phase} version=1 slot={claim_slot} generation={grant} "
                f"transaction={ticket} first={value} second={offset}"
            )
            if failure:
                reason = (
                    "snapshot reply encoding/binding"
                    if failure == "snapshot-reply-reserved"
                    else "IPC request capability/state"
                )
                rows.append("AURORA_UEFI_RUNTIME_FAIL: " + reason)
                return
            operation = "SUBMIT" if phase in (0, 6) else "REPLY" if phase == 1 else "COMPLETE"
            record(operation, value, offset if operation == "SUBMIT" else 0)
        event = "bounds" if fault else "returned"
        rows.append(f"AURORA_UEFI_IPC_RESTORE: slot={slot} root={kernel} stack={STACK} event={event} value={value}")

    if mode in PRODUCER_FAILURES:
        return ["AURORA_UEFI_SNAPSHOT_UNAVAILABLE: unpublished=1 used=0", *SUFFIX.splitlines()]
    if mode in ("snapshot-owner", "snapshot-stale", "snapshot-revoked"):
        # Stale/revoked requests launch with the captured old generation, not
        # the fresh grant (stale) or absent grant (revoked).
        enter(0, 0, 1, failure=mode)
        return rows
    if mode in ("snapshot-fault", "snapshot-cancel"):
        enter(0, 0, 1)
        if mode == "snapshot-fault":
            record("DELIVER", 1)
            enter(1, 4, 0, fault=True)
        record("CONSUME", 0, 1)
        enter(0, 3, DONE - 1)
        rows.append("AURORA_UEFI_SNAPSHOT_RESTART: fresh=1 scrubbed=1")
        grant, transaction = 3, 4
    for offset, unknown in [(value, False) for value in range(66)] + [(DONE, False), (0, True)]:
        operation = 99 if unknown else 1
        reply = 3 if unknown else 2 if offset == 64 else 4 if offset > 64 else 1 | (((offset * 53 + 7) % 256) << 8)
        enter(0, 6 if unknown else 0, operation, offset)
        record("DELIVER", operation, offset)
        if mode == "snapshot-reply-reserved":
            enter(1, 1, reply | (1 << 63), offset, failure=mode)
            return rows
        if mode == "snapshot-reply-byte":
            reply ^= 0x100
        enter(1, 1, reply, offset)
        record("CONSUME", reply)
        continuation = DONE - 2 if mode == "snapshot-reply-byte" else DONE if unknown or offset >= 64 else offset + 1
        enter(0, 7 if unknown else 2, continuation, offset)
        if mode == "snapshot-reply-byte":
            rows.append("AURORA_UEFI_RUNTIME_FAIL: snapshot compiled client continuation")
            return rows
        transaction += 1
    rows.append("AURORA_UEFI_SNAPSHOT_OK: bytes=64 eof=1 range=2 operation=1 used=0 records=0")
    rows.extend(SUFFIX.splitlines())
    return rows


def validate(status, text, mode, metadata):
    need(mode in MODES, "Unknown snapshot mode")
    selected = mode in FIXTURE_MODES
    need(
        text.count("AURORA_FIXTURE_READY") == int(selected)
        and text.splitlines().count("AURORA_FIXTURE_READY") == int(selected),
        "Snapshot fixture selector readiness",
    )
    if selected:
        need(
            "AURORA_PCI_WINDOW_CLOSED:" in text
            and text.index("AURORA_PCI_WINDOW_CLOSED:") < text.index("AURORA_FIXTURE_READY"),
            "Snapshot selector precedes hardware closure",
        )
        first = min(
            (text.find(marker) for marker in ("AURORA_UEFI_SNAPSHOT_", "AURORA_UEFI_IPC_") if text.find(marker) >= 0),
            default=-1,
        )
        need(first > text.index("AURORA_FIXTURE_READY"), "Snapshot selector follows publication")
        text = text.replace("AURORA_FIXTURE_READY\r\n", "").replace("AURORA_FIXTURE_READY\n", "")
    ipc.metadata_valid(metadata, "ipc")
    need(status == (33 if mode in SUCCESS else 35), "Wrong snapshot exit status")
    lines = text.splitlines()
    markers = ("AURORA_UEFI_SNAPSHOT_", "AURORA_UEFI_IPC_", "AURORA_UEFI_DOMAIN_", "AURORA_UEFI_RUNTIME_")
    start = next((index for index, line in enumerate(lines) if any(marker in line for marker in markers)), None)
    need(start is not None, "Missing snapshot execution/publication outcome")
    prefix = "\n".join(lines[:start]) + "\n"
    ipc.pci.validate(33, prefix + SUFFIX, "pci")
    arena = int(re.search(r"AURORA_UEFI_OWNERSHIP_OK: arena=(\d+)", prefix)[1])
    actual = [line for line in lines[start:] if "AURORA_" in line]
    wanted = expected(mode, metadata, arena)
    need(len(actual) == len(wanted), "Snapshot phase/record count")
    for line, pattern in zip(actual, wanted):
        match = re.fullmatch(pattern, line)
        need(match is not None, "Wrong snapshot phase/order/authority: " + line)
        if STACK in pattern:
            address = int(match[1])
            need(arena + 0x44000 <= address < arena + 0x48000 and address % 8 == 0, "Wrong snapshot kernel stack")
    need(
        "AURORA_UEFI_PAYLOAD_FAIL:" not in text and "AURORA_UEFI_FAIL:" not in text, "Unexpected snapshot boot failure"
    )
    if mode in SUCCESS:
        ipc.pci.validate(status, text, "pci")


if __name__ == "__main__":
    try:
        need(len(sys.argv) == 5, "Usage: kernel-snapshot-smoke.py STATUS LOG MODE METADATA")
        validate(
            int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3], json.loads(Path(sys.argv[4]).read_text())
        )
    except (ValueError, OSError) as error:
        raise SystemExit(f"FAIL: {error}")
    print("PASS: copied snapshot exact transcript")
