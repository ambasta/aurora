#!/usr/bin/env python3
"""CPU-owned byte construction receipts; never evidence of device DMA behavior."""

from pathlib import Path
import importlib.util, json, re, sys

spec = importlib.util.spec_from_file_location("runtime", Path(__file__).with_name("kernel-uefi-runtime-smoke.py"))
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
need = runtime.need
MODES = tuple("runtime-table-" + v for v in ("readback", "reject", "exhaust", "quarantine"))


def records(mode, arena, old=2, current=4):
    rows = []

    def state(phase, name, pool, pinned=0, quarantine=0, entries=0):
        rows.append(
            (
                phase,
                f"AURORA_TABLE_STATE: event={name} pool={pool} pinned={pinned} q"
                f"uarantine={quarantine} entries={entries} root={arena + 0x11000}"
                f" publication=never",
            )
        )

    state(0, "begin", 8)
    if mode.endswith("quarantine"):
        rows.append((0, f"AURORA_TABLE_OWNER: slot=1 incarnation={old}"))
    if mode.endswith("exhaust"):
        state(0, "fragmented", 9)
        state(0, "pool-full", 12)
        state(0, "entries-full", 10, 2, 0, 2)
    state(0, "sealed", 13, 5, 0, 3)
    rows.append((0, "AURORA_TABLE_CPU_BYTES: dtes=256 leaves=512 pages=5 domain=1 valid=1"))
    rows.append((0, "AURORA_TABLE_SOFTWARE_MODEL: requester_denied=65535 high_iova_denied=1 read=1 write_denied=1"))
    if mode.endswith("reject"):
        for case in range(6):
            rows.append((0, f"AURORA_TABLE_CASE: index={case} state=rejected constructor=0 decoder=0"))
            rows.append((0, f"AURORA_TABLE_CASE: index={case} state=restored constructor=1 decoder=1"))
        rows.append((0, "AURORA_TABLE_CORRUPTION: rejected=6 requests=5 restored=1"))
        state(0, "rejected", 13, 5, 0, 3)
    quarantine = mode.endswith("quarantine")
    if not quarantine:
        state(0, "cancelled", 8)
    state(
        1,
        "fault-restored",
        10 if quarantine else 8,
        2 if quarantine else 0,
        2 if quarantine else 0,
        1 if quarantine else 0,
    )
    if quarantine:
        rows.append(
            (3, f"AURORA_TABLE_RESTART: slot=1 old={old} current={current} stale_owner=1 fresh_cancel=1 retained=2")
        )
        state(3, "service-reborn", 10, 2, 2, 1)
        state(3, "final", 2, 2, 2, 1)
    else:
        state(3, "reborn", 4)
        state(3, "final", 0)
    rows.append((3, "AURORA_TABLE_OK: scope=cpu-only"))
    return rows


def validate(status, text, mode, metadata):
    need(mode in MODES, "Unknown dormant mode")
    text = text.replace("\r", "")
    quarantine = mode.endswith("quarantine")
    runtime.validate(
        status,
        runtime.checked_fixture_projection(text),
        "runtime",
        metadata,
        retained=2 if quarantine else 0,
        final_slot=1 if quarantine else 0,
    )
    need(
        not any(prefix in text for prefix in ("AURORA_PIN", "AURORA_DMA", "AURORA_IOMMU")),
        "Unrelated authority receipt",
    )
    arena = int(re.search(r"AURORA_UEFI_OWNERSHIP_OK: arena=(\d+)", text)[1])
    old = current = 0
    if quarantine:
        owners = list(re.finditer(r"^AURORA_TABLE_OWNER: slot=1 incarnation=(\d+)$", text, re.M))
        restarts = list(
            re.finditer(
                r"^AURORA_TABLE_RESTART: slot=1 old=(\d+) current=(\d+) stale_owner=1 fresh_cancel=1 retained=2$",
                text,
                re.M,
            )
        )
        need(len(owners) == len(restarts) == 1, "Missing/duplicate incarnation authority")
        old = int(owners[0][1])
        current = int(restarts[0][2])
        need(
            old == 2 and current == 4 and int(restarts[0][1]) == old,
            "Incarnation disagrees with four kernel-selected creations",
        )
    expected = records(mode, arena, old, current)
    actual = list(re.finditer(r"^.*AURORA_TABLE[^\n]*$", text, re.M))
    need([m[0] for m in actual] == [line for _, line in expected], "Malformed/missing/reordered table receipt")
    need(text.count("AURORA_TABLE") == len(actual), "Embedded/duplicate table receipt")
    restores = list(re.finditer(r"^AURORA_UEFI_DOMAIN_RESTORE:[^\n]*$", text, re.M))
    enters = list(re.finditer(r"^AURORA_UEFI_DOMAIN_ENTER:[^\n]*$", text, re.M))
    cleanup = text.index("AURORA_UEFI_DOMAIN_CLEANUP_OK:")
    for match, (phase, _) in zip(actual, expected):
        end = enters[phase + 1].start() if phase < 3 else cleanup
        need(restores[phase].end() < match.start() < end, "Operation outside authorized kernel continuation")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit("status log mode metadata required")
    validate(int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3], json.loads(Path(sys.argv[4]).read_text()))
    print("PASS CPU_BYTES/SOFTWARE_MODEL receipt; no DMA result")
