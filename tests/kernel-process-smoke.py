#!/usr/bin/env python3
"""Serial oracle for the process-fixture rows (kernel/uefi/process.md#guest-rows).

    kernel-process-smoke.py STATUS LOG MODE IMAGE_DIR

The baseline exports one boot-volume entry, which must equal the repository
file of the same path; the volume size is the image's own ESP volume.
"""

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from kernel_uefi_oracle import exports, loader_selection, need  # noqa: E402

BASE = (
    "AURORA_UEFI_ENTRY",
    "AURORA_UEFI_EXIT_OK: attempts=1",
    "AURORA_UEFI_PAYLOAD_ENTRY",
    "AURORA_UEFI_OWNERSHIP_OK:",
    "AURORA_UEFI_PROTECTION_OK:",
    "AURORA_UEFI_LANGUAGE_OK: value=42",
    "AURORA_UEFI_OK",
)
FRAMES = re.compile(
    r"AURORA_PROCESS_FRAMES: frames=(\d+) ranges=(\d+) tables=(\d+) metadata=(\d+) free=(\d+)\r?$", re.M
)
EXPORTED = "examples/host-sort.au"


def ordered(text, markers):
    positions = []
    for marker in markers:
        need(text.count(marker) == 1, f"Missing/duplicate {marker}")
        positions.append(text.index(marker))
    need(positions == sorted(positions), "Record order")


def frames(text):
    """The inventory's own consistency; the kernel's walk and the hosted cases check the plan."""
    match = FRAMES.search(text)
    need(match and text.count("AURORA_PROCESS_FRAMES:") == 1, "Missing frame inventory")
    count, ranges, tables, metadata, free = map(int, match.groups())
    need(1 <= ranges <= 512 and tables and metadata and free > 0 and count == tables + metadata + free, "Inventory")
    return free


def validate(status, text, mode, image):
    text = loader_selection(text, mode)
    need("AURORA_UEFI_PAYLOAD_FAIL" not in text and "AURORA_UEFI_EXCEPTION" not in text, "Payload failure")
    if mode == "process-volume-empty":
        need(status == 35 and text.count("AURORA_UEFI_FAIL: boot volume bounds") == 1, "Empty volume accepted")
        need("AURORA_UEFI_EXIT_OK" not in text and "AURORA_PROCESS" not in text, "Empty volume continued")
        return
    need("AURORA_UEFI_FAIL:" not in text, "Loader failure")
    ordered(text, BASE)
    volume = (image / "esp/aurora/volume").read_bytes()
    if mode == "process-volume-map":
        need(
            status == 35
            and text.count("AURORA_PROCESS_GRANT_REJECTED: reason=arena") == 1
            and text.count("AURORA_PROCESS_FAIL: boot volume map ownership") == 1,
            "Unconfirmed volume accepted",
        )
        need("AURORA_PROCESS_FRAMES" not in text and "AURORA_EXPORT" not in text, "Unconfirmed volume continued")
        return
    if mode == "process-volume-corrupt":
        frames(text)
        need(
            status == 35
            and text.count("AURORA_PROCESS_VOLUME_REJECTED: reason=order") == 1
            and text.count("AURORA_PROCESS_FAIL: boot volume admission") == 1,
            "Unsorted volume accepted",
        )
        need("AURORA_PROCESS_VOLUME_OK" not in text and "AURORA_EXPORT" not in text, "Unsorted volume continued")
        return
    need(mode == "process-volume", "Unknown process mode")
    need(status == 33 and "AURORA_PROCESS_FAIL" not in text, "Process row failed")
    free = frames(text)
    ordered(
        text,
        (
            "AURORA_UEFI_OK",
            "AURORA_PROCESS_FRAMES:",
            f"AURORA_PROCESS_VOLUME_OK: bytes={len(volume)} pages={(len(volume) + 4095) // 4096}",
            f"AURORA_PROCESS_FRAMES_OK: allocated={free} scrubbed={free} released={free} rejected=6 leaks=0",
            "AURORA_PROCESS_SPACE_OK: rejected=4",
            f"AURORA_EXPORT_BEGIN: path={EXPORTED} bytes=",
            "AURORA_PROCESS_OK",
        ),
    )
    need(exports(text) == {EXPORTED: (ROOT / EXPORTED).read_bytes()}, "Exported bytes differ from the source")


if __name__ == "__main__":
    try:
        validate(int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3], Path(sys.argv[4]))
    except (ValueError, OSError) as error:
        sys.exit(f"FAIL: {error}")
