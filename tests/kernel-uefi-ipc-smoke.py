#!/usr/bin/env python3
"""Strict ordered evidence for the fixed staged IPC fixture, not a general log parser."""

from pathlib import Path
import copy, importlib.util, json, re, sys

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
        probe = image["probe_pc"]
        wanted = index == 0 and mode in ("ipc-site", "ipc-unknown")
        need(image["probe_offset"] == 0 and bool(probe) == wanted, "Unexpected IPC probe authority")
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
        pc = (
            image["bounds_pc"]
            if kind == "bounds" or failure == "ipc-kernel-trap"
            else image["probe_pc"]
            if failure in ("ipc-site", "ipc-unknown")
            else image["return_pc"]
        )
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


FIXTURE_MODES = (
    "ipc-fault",
    "ipc-cancel",
    "ipc-stale",
    "ipc-root",
    "ipc-kernel-trap",
    "ipc-duplicate",
    "ipc-late",
    "ipc-exhausted",
)


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


def self_test():
    arena = 0x1000000
    kernel = arena + 0x11000
    prefix = (
        f"AURORA_UEFI_ENTRY\nAURORA_UEFI_EXIT_OK: attempts=1\nAURORA_UEF"
        f"I_PAYLOAD_ENTRY\nAURORA_UEFI_OWNERSHIP_OK: arena={arena} bytes"
        f"=1048576 descriptors=111\nAURORA_UEFI_PROTECTION_OK: root="
        f"{kernel} stack={arena + 0x47E00}\nAURORA_ACPI_CPU: id=0 uid=0 "
        f"enabled=1 capable=0 x2=0\nAURORA_ACPI_TOPOLOGY: records=1 enab"
        f"led=1 capable=0 lapic=4276092928\nAURORA_ACPI_WINDOW_CLOSED: c"
        f"opies=14\nAURORA_PCI_APERTURE: base=3758096384 bytes=268435456"
        f" segment=0 first=0 last=255\nAURORA_PCI_FUNCTION: segment=0 bu"
        f"s=0 device=0 function=0 vendor=32902 product=10688 class=6 sub"
        f"class=0 interface=0 header=0 command=7 secondary=0 subordinate"
        f"=0\nAURORA_PCI_INVENTORY: functions=1 buses=1\nAURORA_PCI_WIND"
        f"OW_CLOSED: reads=39\n"
    )
    rejected = 0
    for mode in MODES:
        metadata = {}
        for index, name in enumerate(("clean", "bounds")):
            base = BASE + index * 16384
            metadata[name] = dict(
                entry=base,
                size=128,
                return_pc=base + 60,
                bounds_pc=base + 64,
                overflow_pc=base + 68,
                division_zero_pc=base + 72,
                shift_count_pc=base + 76,
                probe_pc=base + 52 if index == 0 and mode in ("ipc-site", "ipc-unknown") else 0,
                probe_offset=0,
            )
        rows = [row.replace(r"(\d+)", str(arena + 0x47C00)) for row in expected(mode, metadata, arena)]
        case_prefix = prefix + ("AURORA_FIXTURE_READY\n" if mode in FIXTURE_MODES else "")
        text = case_prefix + "\n".join(rows) + "\n"
        status = 33 if mode in SUCCESS else 35
        validate(status, text, mode, metadata)
        failures = [
            (0, text),
            (status, text + "AURORA_UEFI_IPC_OK\n"),
            (status, text + "AURORA_UEFI_RUNTIME_FAIL: unexpected\n"),
        ]
        for i, line in enumerate(text.splitlines()):
            failures.extend(
                ((status, text.replace(line + "\n", "", 1)), (status, text.replace(line + "\n", (line + "\n") * 2, 1)))
            )
        for i, line in enumerate(rows):
            for field in re.findall(r"([a-z]+)=\d+", line):
                changed = re.sub(rf"{field}=\d+", f"{field}=9999999999999999999", line)
                failures.append((status, text.replace(line, changed, 1)))
            if i + 1 < len(rows):
                swapped = rows.copy()
                swapped[i], swapped[i + 1] = swapped[i + 1], swapped[i]
                failures.append((status, case_prefix + "\n".join(swapped) + "\n"))
        if mode not in SUCCESS:
            failures.append((status, text + SUFFIX))
        for field, value in [
            ("return_pc", 0),
            ("bounds_pc", BASE - 2),
            ("overflow_pc", BASE + 16384),
            ("size", 8192),
            ("entry", 0),
            ("return_pc", True),
            ("probe_offset", 8),
        ]:
            altered = copy.deepcopy(metadata)
            old = altered["clean"][field]
            altered["clean"][field] = value
            bad = text.replace(f"pc={old} ", f"pc={int(value)} ") if field == "return_pc" else text
            try:
                validate(status, bad, mode, altered)
            except ValueError:
                rejected += 1
            else:
                raise RuntimeError(f"Bad IPC metadata accepted: {mode} {field}")
        for code, bad in failures:
            try:
                validate(code, bad, mode, metadata)
            except ValueError:
                rejected += 1
            else:
                raise RuntimeError(f"Bad IPC transcript accepted: {mode}")
    # Only the four closed Call modes widen the caller; service and IPC stay one page.
    for call_mode in ("user-call", "user-call-pending", "user-call-owner", "user-call-site"):
        boundary = copy.deepcopy(metadata)
        boundary["clean"]["size"] = 8192
        metadata_valid(boundary, call_mode)
        for name, size, selected in (
            ("clean", 8193, call_mode),
            ("bounds", 4097, call_mode),
            ("clean", 4097, "ipc-fault"),
        ):
            changed = copy.deepcopy(boundary)
            changed["clean"]["size"] = 128
            changed[name]["size"] = size
            try:
                metadata_valid(changed, selected)
            except ValueError:
                rejected += 1
            else:
                raise RuntimeError("Call-specific image boundary widened")
    print(f"PASS: IPC transcripts {len(MODES)} positive and {rejected} negative cases")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    else:
        try:
            validate(
                int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3], json.loads(Path(sys.argv[4]).read_text())
            )
        except (ValueError, IndexError, KeyError) as error:
            raise SystemExit(f"FAIL: {error}")
        print("PASS: staged IPC exact transcript")
