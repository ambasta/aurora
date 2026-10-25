#!/usr/bin/env python3
"""Strict CPU-only pin-ledger receipts, layered on exact ring-3 runtime checks."""

from pathlib import Path
import importlib.util, json, re, sys

spec = importlib.util.spec_from_file_location("runtime", Path(__file__).with_name("kernel-uefi-runtime-smoke.py"))
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
need = runtime.need
MODES = ("runtime-pin-cancel", "runtime-pin-fault", "runtime-pin-stale", "runtime-pin-exhaust")
# event, pool allocations, retained pin pages, quarantined pages, occupied entries
EXPECTED = {
    "runtime-pin-cancel": [
        ("begin", 8, 0, 0, 0),
        ("loan", 10, 2, 0, 1),
        ("cancelled", 8, 0, 0, 0),
        ("fault-restored", 8, 0, 0, 0),
        ("reborn", 4, 0, 0, 0),
        ("final", 0, 0, 0, 0),
    ],
    "runtime-pin-fault": [
        ("begin", 8, 0, 0, 0),
        ("uncertainty", 10, 2, 2, 1),
        ("fault-restored", 10, 2, 2, 1),
        ("service-reborn", 10, 2, 2, 1),
        ("final", 2, 2, 2, 1),
    ],
    "runtime-pin-stale": [
        ("begin", 8, 0, 0, 0),
        ("stale-rejected", 8, 0, 0, 0),
        ("fault-restored", 8, 0, 0, 0),
        ("reborn", 4, 0, 0, 0),
        ("final", 0, 0, 0, 0),
    ],
    "runtime-pin-exhaust": [
        ("begin", 8, 0, 0, 0),
        ("entries-full", 12, 4, 0, 4),
        ("pool-full", 15, 0, 0, 0),
        ("borrower-loan", 10, 2, 0, 1),
        ("fault-restored", 8, 0, 0, 0),
        ("reborn", 4, 0, 0, 0),
        ("final", 0, 0, 0, 0),
    ],
}
PATTERN = r"AURORA_PIN_STATE: event=([a-z-]+) pool=(\d+) pinned=(\d+) quarantine=(\d+) entries=(\d+) root=(\d+)"


def validate(status, text, mode, metadata):
    need(mode in MODES, "Unknown pin mode")
    runtime.validate(
        status,
        text,
        "runtime",
        metadata,
        retained=2 if mode == "runtime-pin-fault" else 0,
        final_slot=1 if mode == "runtime-pin-fault" else 0,
        selected=mode,
    )
    rows = list(re.finditer(PATTERN, text))
    seen = [(m[1], *(int(m[i]) for i in range(2, 6))) for m in rows]
    need(seen == EXPECTED[mode], "Pin sequence/count mismatch")
    for line in text.splitlines():
        if "AURORA_PIN" in line:
            need(
                re.fullmatch(PATTERN, line) is not None
                or line == "AURORA_PIN_OK"
                or re.fullmatch(r"AURORA_PIN_OWNER: slot=1 incarnation=\d+", line)
                or re.fullmatch(
                    r"AURORA_PIN_RESTART: slot=1 old=\d+ current=\d+ stale_owner=1 stale_token=1 retained=2", line
                ),
                "Malformed pin record",
            )
    need(text.count("AURORA_PIN_STATE:") == len(rows) and text.count("AURORA_PIN_OK") == 1, "Duplicate pin record")
    arena = int(re.search(r"AURORA_UEFI_OWNERSHIP_OK: arena=(\d+)", text)[1])
    need(all(int(m[6]) == arena + 0x11000 for m in rows), "Pin operation under wrong root")
    enters = list(re.finditer("AURORA_UEFI_DOMAIN_ENTER:", text))
    restores = list(re.finditer(r"AURORA_UEFI_DOMAIN_RESTORE:[^\n]*", text))
    for row in rows:
        event = row[1]
        if event == "fault-restored":
            need(restores[1].end() < row.start() < enters[2].start(), "Fault before trusted restoration")
        elif event in ("reborn", "service-reborn", "final"):
            need(restores[3].end() < row.start() < text.index("AURORA_UEFI_DOMAIN_CLEANUP_OK:"), "Late pin ordering")
        else:
            need(restores[0].end() < row.start() < enters[1].start(), "Loan without valid request return")
    owners = list(re.finditer(r"AURORA_PIN_OWNER: slot=1 incarnation=(\d+)", text))
    need(len(owners) == (1 if mode == "runtime-pin-fault" else 0), "Unexpected pin owner receipt")
    restarts = list(
        re.finditer(r"AURORA_PIN_RESTART: slot=1 old=(\d+) current=(\d+) stale_owner=1 stale_token=1 retained=2", text)
    )
    need(len(restarts) == (1 if mode == "runtime-pin-fault" else 0), "Unexpected restart receipt")
    if restarts:
        restart = restarts[0]
        old, current = map(int, restart.groups())
        need(0 < old < current <= 2**64 - 1 and old == int(owners[0][1]), "Replayed service incarnation")
        uncertainty = next(row for row in rows if row[1] == "uncertainty")
        need(rows[0].end() < owners[0].start() < uncertainty.start(), "Owner loan ordering")
        service = next(row for row in rows if row[1] == "service-reborn")
        need(restores[3].end() < restart.start() < service.start(), "Restart authority ordering")
    need(
        rows[-1].end() < text.index("AURORA_PIN_OK") < text.index("AURORA_UEFI_DOMAIN_CLEANUP_OK:"),
        "Pin completion order",
    )


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit("status log mode metadata required")
    validate(int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3], json.loads(Path(sys.argv[4]).read_text()))
    print("PASS: exact CPU-only pin-ledger receipt")
