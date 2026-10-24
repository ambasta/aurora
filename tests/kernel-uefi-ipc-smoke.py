#!/usr/bin/env python3
"""Strict ordered evidence for the fixed staged IPC fixture, not a general log parser."""

from pathlib import Path
import importlib.util, json, re, sys

spec = importlib.util.spec_from_file_location("pci", Path(__file__).with_name("kernel-pci-smoke.py"))
pci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pci)
need = pci.need
BASE = 0x10000000000
# Historical synthetic scenarios include copied-policy failures now covered hosted.
# Current boot modes are admitted separately by kernel_profiles and emulator_clock.
MODES = (
    "ipc",
    "ipc-fault",
    "ipc-cancel",
    "ipc-owner",
    "ipc-stale",
    "ipc-version",
    "ipc-phase",
    "ipc-transaction",
    "ipc-site",
    "ipc-unknown",
    "ipc-root",
    "ipc-kernel-trap",
    "ipc-duplicate",
    "ipc-late",
    "ipc-exhausted",
    "ipc-policy-request-input",
    "ipc-policy-request-output",
    "ipc-policy-cancel-input",
    "ipc-policy-cancel-output",
)
SUCCESS = ("ipc", "ipc-fault", "ipc-cancel")
REQUEST_POLICY_MODES = ("ipc-policy-request-input", "ipc-policy-request-output")
CANCEL_POLICY_MODES = ("ipc-policy-cancel-input", "ipc-policy-cancel-output")
SUFFIX = "AURORA_UEFI_LANGUAGE_OK: value=42\nAURORA_UEFI_OK\n"


def metadata_valid(metadata, mode):
    keys = {
        "entry",
        "size",
        "return_pc",
        "bounds_pc",
        "overflow_pc",
        "division_zero_pc",
        "shift_count_pc",
        "probe_offset",
        "probe_pc",
    }
    need(type(metadata) is dict and set(metadata) == {"clean", "bounds"}, "Malformed IPC image set")
    for index, name in enumerate(("clean", "bounds")):
        image = metadata[name]
        base = BASE + index * 16384
        need(
            type(image) is dict
            and set(image) == keys
            and all(type(v) is int and 0 <= v < 1 << 64 for v in image.values()),
            "Malformed IPC metadata values",
        )
        size = image["size"]
        call_client = index == 0 and mode in ("user-call", "user-call-pending", "user-call-owner", "user-call-site")
        need(image["entry"] == base and 4 <= size <= (8192 if call_client else 4096), "IPC image layout widened")
        sites = [image[k] for k in ("return_pc", "bounds_pc", "overflow_pc", "division_zero_pc", "shift_count_pc")]
        present = [pc for pc in sites if pc]
        need(all(sites[:3]) and len(set(present)) == len(present), "IPC sites missing/aliased")
        need(
            all(base <= pc <= base + size - 2 for pc in present) and image["return_pc"] >= base + 2,
            "IPC site outside image",
        )
        # Hostile exits are now injected by the fixture kernel, so no IPC image
        # carries a probe address of its own.
        probe = image["probe_pc"]
        need(image["probe_offset"] == 0 and not probe, "Unexpected IPC probe authority")
        need(not probe or base <= probe <= base + size - 2 and probe not in present, "IPC probe out of range/aliased")


def expected(mode, metadata, arena):
    rows = []
    kernel = arena + 0x11000
    grant = 1
    tx = 2

    def row(text):
        rows.append(text)

    def record(name, first, second):
        row(f"AURORA_UEFI_IPC_{name}: transaction={tx} first={first} second={second}")

    def enter(slot, phase, value, second=0, kind="returned", failure=None):
        image = metadata["bounds" if slot else "clean"]
        root = arena + 0x90000 + slot * 0x10000
        ticket = 0 if phase == 0 else tx
        row(f"AURORA_UEFI_IPC_ENTER: slot={slot} phase={phase} root={root} grant={grant} transaction={ticket}")
        vector = 6 if kind == "bounds" or failure in ("ipc-unknown", "ipc-kernel-trap") else 129
        # ipc-site: the fixture moves the trapped exit off the registered return
        # site. ipc-unknown: the client resumes at the wrapper's bad_entry ud2,
        # just after the return site, and raises #UD from an unregistered address.
        pc = (
            image["bounds_pc"]
            if kind == "bounds" or failure == "ipc-kernel-trap"
            else image["return_pc"] + 1
            if failure == "ipc-site"
            else image["return_pc"] + 2
            if failure == "ipc-unknown"
            else image["return_pc"]
        )
        if failure == "ipc-unknown":
            sites = ("return_pc", "bounds_pc", "overflow_pc", "division_zero_pc", "shift_count_pc")
            need(pc not in [image[k] for k in sites], "Unknown UD2 aliases a registered site")
        cpl = 0 if failure == "ipc-kernel-trap" else 3
        frame = r"(\d+)" if cpl == 0 else str(arena + 0x88000 - 176)
        row(f"AURORA_UEFI_DOMAIN_EVENT: vector={vector} error=0 pc={pc} cpl={cpl} root={root} frame={frame} cr2=0")
        if failure == "ipc-root":
            row(f"AURORA_UEFI_RUNTIME_ROOT_PROBE: root={kernel}")
            row("AURORA_UEFI_RUNTIME_FAIL: exception root authority")
            return
        if failure in ("ipc-site", "ipc-unknown", "ipc-kernel-trap"):
            row("AURORA_UEFI_RUNTIME_FAIL: " + ("exception origin/stack" if cpl == 0 else "exception site authority"))
            return
        if kind == "returned":
            claim_phase = 1 if failure == "ipc-phase" else phase
            version = 2 if failure == "ipc-version" else 1
            capslot = 1 - slot if failure == "ipc-owner" else slot
            claimtx = ticket + 1 if failure == "ipc-transaction" else ticket
            row(
                f"AURORA_UEFI_IPC_ENVELOPE: phase={claim_phase} version={version}"
                f" slot={capslot} generation={grant} transaction={claimtx} first"
                f"={value} second={second}"
            )
            if failure:
                reason = (
                    "IPC phase/version authority"
                    if failure in ("ipc-phase", "ipc-version")
                    else "IPC request capability/state"
                    if phase == 0
                    else "IPC reply capability/transaction/state"
                )
                row("AURORA_UEFI_RUNTIME_FAIL: " + reason)
                return
            record(
                "SUBMIT" if phase == 0 else "REPLY" if phase == 1 else "COMPLETE", value, second if phase == 0 else 0
            )
        row(f"AURORA_UEFI_IPC_RESTORE: slot={slot} root={kernel} stack=(\\d+) event={kind} value={value}")

    first_failure = (
        mode
        if mode
        in (
            "ipc-owner",
            "ipc-stale",
            "ipc-version",
            "ipc-phase",
            "ipc-site",
            "ipc-unknown",
            "ipc-root",
            "ipc-kernel-trap",
            "ipc-exhausted",
        )
        + REQUEST_POLICY_MODES
        else None
    )
    enter(0, 0, 40, 2, failure=first_failure)
    if first_failure:
        return rows
    if mode == "ipc-fault" or mode in CANCEL_POLICY_MODES:
        record("DELIVER", 40, 2)
        enter(1, 4, 0, 2, kind="bounds")
    if mode in CANCEL_POLICY_MODES:
        row("AURORA_UEFI_RUNTIME_FAIL: IPC cancel boundary")
        return rows
    if mode in ("ipc-fault", "ipc-cancel", "ipc-late"):
        record("CANCEL", 0, 0)
        record("CONSUME", 0, 1)
        enter(0, 3, 7)
        if mode == "ipc-late":
            enter(1, 1, 42, 2, failure=mode)
            return rows
        if mode == "ipc-fault":
            row(f"AURORA_UEFI_IPC_RESTART: frame={arena + 0xC4000}")
            grant = 3
            tx = 4
        else:
            tx = 3
        enter(0, 0, 40, 2)
    record("DELIVER", 40, 2)
    enter(1, 1, 42, 2, failure=mode if mode == "ipc-transaction" else None)
    if mode == "ipc-transaction":
        return rows
    if mode == "ipc-duplicate":
        enter(1, 1, 42, 2, failure=mode)
        return rows
    record("CONSUME", 42, 0)
    enter(0, 2, 42)
    record("RECYCLE", 0, 0)
    rows.extend(
        (
            "AURORA_UEFI_IPC_CLEANUP_OK: used=0 records=0",
            "AURORA_UEFI_IPC_OK",
            "AURORA_UEFI_LANGUAGE_OK: value=42",
            "AURORA_UEFI_OK",
        )
    )
    return rows


# Modes that boot the shared ipc-fixture image, from the one fixture table.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import kernel_profiles  # noqa: E402

FIXTURE_MODES = tuple(mode for mode, (image, _) in kernel_profiles.FIXTURE_MODES.items() if image == "ipc-fixture")


def validate(status, text, mode, metadata):
    marker = "AURORA_FIXTURE_READY\n"
    need(text.count(marker) == (1 if mode in FIXTURE_MODES else 0), "Exact IPC fixture readiness")
    if mode in FIXTURE_MODES:
        need(
            text.index("AURORA_PCI_WINDOW_CLOSED:") < text.index(marker) < text.index("AURORA_UEFI_IPC_ENTER:"),
            "IPC selector admission phase",
        )
        text = text.replace(marker, "", 1)
    return validate_protocol_projection(status, text, mode, metadata)


def validate_protocol_projection(status, text, mode, metadata):
    """Ordered IPC protocol only; not proof of this family's selector admission.

    The budget oracle projects its independently admitted timer run here.
    Real IPC receipts always enter through validate() above.
    """
    need(mode in MODES, "Unknown IPC mode")
    metadata_valid(metadata, mode)
    need(status == (33 if mode in SUCCESS else 35), "Wrong IPC exit status")
    lines = text.splitlines()
    start = next(
        (
            i
            for i, line in enumerate(lines)
            if line.startswith(("AURORA_UEFI_IPC_", "AURORA_UEFI_DOMAIN_", "AURORA_UEFI_RUNTIME_"))
        ),
        None,
    )
    need(
        start is not None and lines[start].startswith("AURORA_UEFI_IPC_ENTER:"),
        "IPC never entered/early injected record",
    )
    prefix = "\n".join(lines[:start]) + "\n"
    pci.validate(33, prefix + SUFFIX, "pci")
    arena = int(re.search(r"AURORA_UEFI_OWNERSHIP_OK: arena=(\d+)", prefix)[1])
    expected_rows = expected(mode, metadata, arena)
    actual = [line for line in lines[start:] if line.startswith("AURORA_")]
    need(len(actual) == len(expected_rows), "IPC phase/record count")
    for line, pattern in zip(actual, expected_rows):
        need(re.fullmatch(pattern, line) is not None, "Wrong IPC phase/order/authority: " + line)
        if " stack=" in line or mode == "ipc-kernel-trap" and line.startswith("AURORA_UEFI_DOMAIN_EVENT:"):
            field = "stack" if " stack=" in line else "frame"
            address = int(re.search(rf"{field}=(\d+)", line)[1])
            need(arena + 0x44000 <= address < arena + 0x48000 and address % 8 == 0, "Wrong IPC kernel stack")
    need("AURORA_UEFI_PAYLOAD_FAIL:" not in text and "AURORA_UEFI_FAIL:" not in text, "Unexpected boot failure")
    if mode in SUCCESS:
        pci.validate(status, text, "pci")


if __name__ == "__main__":
    try:
        validate(
            int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3], json.loads(Path(sys.argv[4]).read_text())
        )
    except (ValueError, IndexError, KeyError) as error:
        raise SystemExit(f"FAIL: {error}")
    print("PASS: staged IPC exact transcript")
