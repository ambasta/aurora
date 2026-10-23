#!/usr/bin/env python3
"""Exact ordered evidence for the finite copied-snapshot fixture, not a general parser."""

from pathlib import Path
import copy
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


def self_test():
    arena = 0x1000000
    metadata = {
        name: dict(
            entry=base,
            size=128,
            return_pc=base + 60,
            bounds_pc=base + 64,
            overflow_pc=base + 68,
            division_zero_pc=base + 72,
            shift_count_pc=base + 76,
            probe_offset=0,
            probe_pc=0,
        )
        for name, base in (("clean", ipc.BASE), ("bounds", ipc.BASE + 16384))
    }
    prefix = (
        "AURORA_UEFI_ENTRY\nAURORA_UEFI_EXIT_OK: attempts=1\nAURORA_UEFI_PAYLOAD_ENTRY\n"
        f"AURORA_UEFI_OWNERSHIP_OK: arena={arena} bytes=1048576 descriptors=111\n"
        f"AURORA_UEFI_PROTECTION_OK: root={arena + 0x11000} stack={arena + 0x47E00}\n"
        "AURORA_ACPI_CPU: id=0 uid=0 enabled=1 capable=0 x2=0\n"
        "AURORA_ACPI_TOPOLOGY: records=1 enabled=1 capable=0 lapic=4276092928\n"
        "AURORA_ACPI_WINDOW_CLOSED: copies=14\n"
        "AURORA_PCI_APERTURE: base=3758096384 bytes=268435456 segment=0 first=0 last=255\n"
        "AURORA_PCI_FUNCTION: segment=0 bus=0 device=0 function=0 vendor=32902 product=10688 "
        "class=6 subclass=0 interface=0 header=0 command=7 secondary=0 subordinate=0\n"
        "AURORA_PCI_INVENTORY: functions=1 buses=1\nAURORA_PCI_WINDOW_CLOSED: reads=39\n"
    )
    rejected = 0

    def reject(code, text, mode, meta=metadata):
        nonlocal rejected
        try:
            validate(code, text, mode, meta)
        except ValueError:
            rejected += 1
        else:
            raise RuntimeError(f"Invalid snapshot transcript/metadata accepted: {mode}")

    fixtures = {}
    for mode in MODES:
        rows = [row.replace(STACK, str(arena + 0x47C00)) for row in expected(mode, metadata, arena)]
        case_prefix = prefix + ("AURORA_FIXTURE_READY\n" if mode in FIXTURE_MODES else "")
        text = case_prefix + "\n".join(rows) + "\n"
        status = 33 if mode in SUCCESS else 35
        validate(status, text, mode, metadata)
        counts = {
            "snapshot": 1159,
            "snapshot-fault": 1175,
            "snapshot-cancel": 1171,
            "snapshot-reply-reserved": 10,
            "snapshot-reply-byte": 18,
        }
        need(len(rows) == counts.get(mode, 3 if mode in PRODUCER_FAILURES else 4), "Self-test boundary length")
        fixtures[mode] = (status, text)
        if mode in FIXTURE_MODES:
            reject(status, text.replace("AURORA_FIXTURE_READY\n", ""), mode)
            reject(status, text.replace("AURORA_FIXTURE_READY", "AURORA_FIXTURE_READY\nAURORA_FIXTURE_READY"), mode)
            reject(status, "AURORA_FIXTURE_READY\n" + text.replace("AURORA_FIXTURE_READY\n", ""), mode)
            reject(status, text.replace("AURORA_FIXTURE_READY\n", "") + "AURORA_FIXTURE_READY\n", mode)
            reject(status, text.replace("AURORA_FIXTURE_READY", "AURORA_FIXTURE_READY extra"), mode)
        # A bounded set of controls for every mode, rather than multiplying
        # thousands of identical per-byte field mutations over the long traces.
        reject(35 if status == 33 else 33, text, mode)
        reject(status, text + SUFFIX, mode)
        reject(status, text + "AURORA_UEFI_IPC_COMPLETE: transaction=2 first=1 second=0\n", mode)
        reject(status, text + "AURORA_UEFI_RUNTIME_FAIL: forged\n", mode)
        reject(status, text.replace("AURORA_PCI_WINDOW_CLOSED: reads=39\n", ""), mode)
        reject(status, rows[0] + "\n" + text, mode)
        reject(status, "noise " + rows[0] + "\n" + text, mode)
        reject(status, case_prefix + "\n".join(rows[1:]) + "\n", mode)
        reject(status, text + rows[-1] + "\n", mode)
        reordered = rows.copy()
        reordered[-1], reordered[-2] = reordered[-2], reordered[-1]
        reject(status, case_prefix + "\n".join(reordered) + "\n", mode)
        if mode not in SUCCESS:
            reject(33, text.rsplit("AURORA_UEFI_RUNTIME_FAIL:", 1)[0] + SUFFIX, mode)
        if mode in PRODUCER_FAILURES:
            reject(status, text.replace("unpublished=1", "unpublished=0"), mode)
            reject(status, text.replace("used=0", "used=1"), mode)
            continue
        # Root/frame, envelope authority, actual reply, continuation and offset
        # corruptions target distinct observations, including legal but wrong values.
        for old, new in (
            (f"root={arena + 0x90000}", f"root={arena + 0xA0000}"),
            (f"frame={arena + 0x88000 - 176}", f"frame={arena + 0x88000 - 168}"),
            ("vector=129", "vector=6"),
            (f"pc={metadata['clean']['return_pc']}", f"pc={metadata['clean']['bounds_pc']}"),
            ("cpl=3", "cpl=0"),
            ("version=1", "version=2"),
            ("generation=1", "generation=3"),
            ("transaction=0", "transaction=2"),
            (f"stack={arena + 0x47C00}", f"stack={arena + 0x48000}"),
            (f"stack={arena + 0x47C00}", f"stack={arena + 0x47C01}"),
        ):
            if old in text:
                reject(status, text.replace(old, new, 1), mode)
        if mode == "snapshot-reply-reserved":
            reject(status, text.replace(f"first={1793 | (1 << 63)}", "first=1793", 1), mode)
        if mode == "snapshot-reply-byte":
            reject(status, text.replace("first=1537", "first=1793", 1), mode)
            reject(status, text.replace(f"first={DONE - 2}", "first=1", 1), mode)
        if mode in ("snapshot", "snapshot-fault", "snapshot-cancel"):
            normal_start = 2 if mode == "snapshot" else 4
            # Independent anchors: 64 byte replies + EOF + two ranges + unknown;
            # only the recovery modes have one extra cancelled request.
            requests = [line for line in rows if line.startswith("AURORA_UEFI_IPC_SUBMIT:")]
            need(len(requests) == (68 if mode == "snapshot" else 69), "Self-test request coverage")
            need(
                requests[-1] == f"AURORA_UEFI_IPC_SUBMIT: transaction={normal_start + 67} first=99 second=0",
                "Self-test terminal transaction/operation",
            )
            for offset, reply in ((0, 1793), (1, 15361), (31, 29185), (63, 4609), (64, 2), (65, 4), (DONE, 4)):
                transaction = normal_start + (66 if offset == DONE else offset)
                line = f"AURORA_UEFI_IPC_REPLY: transaction={transaction} first={reply} second=0"
                need(line in rows, "Self-test byte/EOF/range oracle")
                reject(status, text.replace(line + "\n", "", 1), mode)
                reject(status, text.replace(line, line.replace(f"first={reply}", f"first={reply ^ 256}"), 1), mode)
            reject(status, case_prefix + rows[-3] + "\n" + SUFFIX, mode)
            completion = f"AURORA_UEFI_IPC_COMPLETE: transaction={normal_start} first=1 second=0"
            reject(status, text.replace(completion, completion.replace("first=1", "first=2"), 1), mode)
            # Remove and reorder complete middle transactions while preserving
            # a convincing EOF, final unknown-operation probe and success suffix.
            middle = (
                next(
                    index
                    for index, row in enumerate(rows)
                    if row == f"AURORA_UEFI_IPC_SUBMIT: transaction={normal_start + 31} first=1 second=31"
                )
                - 3
            )
            missing = rows[:middle] + rows[middle + 17 :]
            swapped = rows[:middle] + rows[middle + 17 : middle + 34] + rows[middle : middle + 17] + rows[middle + 34 :]
            reject(status, case_prefix + "\n".join(missing) + "\n", mode)
            reject(status, case_prefix + "\n".join(swapped) + "\n", mode)
            for old, new in (("second=64", "second=65"), ("phase=6", "phase=0"), ("phase=7", "phase=2")):
                reject(status, text.replace(old, new, 1), mode)
            if mode != "snapshot":
                reject(status, text.replace("fresh=1 scrubbed=1", "fresh=1 scrubbed=0"), mode)
                reject(status, text.replace("grant=3", "grant=1", 1), mode)
                reject(status, text.replace(f"first={DONE - 1}", f"first={DONE}", 1), mode)
            if mode == "snapshot-fault":
                reject(status, text.replace("phase=4", "phase=1", 1), mode)
                reject(status, text.replace("event=bounds value=0", "event=returned value=0", 1), mode)

    status, text = fixtures["snapshot"]
    reject(status, text, "snapshot-unknown")
    for name, field, value in (
        ("clean", "entry", 0),
        ("bounds", "entry", ipc.BASE),
        ("clean", "size", 4097),
        ("clean", "size", True),
        ("clean", "return_pc", 0),
        ("clean", "return_pc", ipc.BASE + 127),
        ("clean", "bounds_pc", ipc.BASE + 60),
        ("clean", "overflow_pc", ipc.BASE - 2),
        ("bounds", "division_zero_pc", "0"),
        ("bounds", "shift_count_pc", -1),
        ("clean", "probe_pc", ipc.BASE + 52),
        ("bounds", "probe_offset", 8),
    ):
        altered = copy.deepcopy(metadata)
        old = altered[name][field]
        altered[name][field] = value
        # Even a transcript changed to match malformed metadata must fail.
        bad = text.replace(f"pc={old} ", f"pc={value} ") if field.endswith("_pc") else text
        reject(status, bad, "snapshot", altered)
    for altered in (None, {}, {"clean": metadata["clean"]}, dict(metadata, peer=metadata["clean"])):
        reject(status, text, "snapshot", altered)
    print(f"PASS: snapshot transcripts {len(MODES)} positive and {rejected} negative cases")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    else:
        try:
            need(len(sys.argv) == 5, "Usage: kernel-snapshot-smoke.py STATUS LOG MODE METADATA")
            validate(
                int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3], json.loads(Path(sys.argv[4]).read_text())
            )
        except (ValueError, OSError) as error:
            raise SystemExit(f"FAIL: {error}")
        print("PASS: copied snapshot exact transcript")
