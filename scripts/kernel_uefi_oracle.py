"""Shared ordinary UEFI serial oracle; no process or image access."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kernel_layout import LAYOUT  # noqa: E402
from kernel_profiles import FIXTURE_MODES, UEFI_VARIANTS  # noqa: E402


def need(value, reason):
    if not value:
        raise ValueError(reason)


ENTRY_ECHO = re.compile(r"AURORA_UEFI_ENTRY\r?\n(AURORA_FIXTURE_SELECTED: value=(\d+)\r?\n)")


def loader_selection(text, mode, selected=True):
    """platform-fixture's loader echoes its fw_cfg row on the line after loader entry.

    The echo precedes every other record, so no case can inject before its own
    phase, and must be the mode's row. Returns the transcript without the echo.
    Other images, and prefixes another oracle reuses (`selected` false), carry none.
    """
    image, value = FIXTURE_MODES.get(UEFI_VARIANTS.get(mode, mode), ("", 0))
    echoes = list(ENTRY_ECHO.finditer(text))
    if not selected or image != "platform-fixture":
        need(not echoes, "Unexpected loader fixture selector")
        return text
    need(
        len(echoes) == 1
        and echoes[0][2] == str(value)
        and text.count("AURORA_FIXTURE_SELECTED:") == 1
        and text.count("AURORA_UEFI_ENTRY") == 1
        and "AURORA_FIXTURE_READY" not in text,
        "Wrong loader fixture selector",
    )
    return text[: echoes[0].start(1)] + text[echoes[0].end(1) :]


def validate(status, text, mode):
    loader_selection(text, mode)
    rejected = re.findall(r"AURORA_UEFI_EXIT_REJECTED: attempt=(\d+)", text)
    need(
        rejected == (["1", "2", "3"] if mode == "stale-exhausted" else ["1"] if mode == "stale" else []),
        "Wrong rejected-key sequence",
    )
    if mode == "stale-exhausted":
        need(
            status == 35
            and text.count("AURORA_UEFI_ENTRY") == 1
            and text.count("AURORA_UEFI_FAIL: ExitBootServices retry exhausted") == 1,
            "Wrong retry exhaustion",
        )
        need(
            all(
                marker not in text
                for marker in (
                    "AURORA_UEFI_EXIT_OK",
                    "AURORA_UEFI_PAYLOAD_ENTRY",
                    "AURORA_UEFI_OK",
                    "AURORA_UEFI_LANGUAGE_OK",
                    "AURORA_UEFI_OWNERSHIP_OK",
                    "AURORA_UEFI_PROTECTION_OK",
                )
            ),
            "Exhausted exit continued",
        )
        return
    need("AURORA_UEFI_FAIL:" not in text, "Loader failure continued")
    for marker in ("AURORA_UEFI_ENTRY", "AURORA_UEFI_EXIT_OK:", "AURORA_UEFI_PAYLOAD_ENTRY"):
        need(text.count(marker) == 1, f"Missing/duplicate {marker}")
    need(
        text.index("AURORA_UEFI_ENTRY") < text.index("AURORA_UEFI_EXIT_OK:") < text.index("AURORA_UEFI_PAYLOAD_ENTRY"),
        "Handoff order",
    )
    attempts = re.search(r"AURORA_UEFI_EXIT_OK: attempts=(\d+)", text)
    need(attempts and int(attempts[1]) == (2 if mode == "stale" else 1), "Wrong exit/retry evidence")
    if mode in ("normal", "stale", "owned-bytes"):
        need(status == 33 and text.count("AURORA_UEFI_OK") == 1 and "_FAIL:" not in text, "UEFI failed")
        need(text.count("AURORA_UEFI_LANGUAGE_OK: value=42") == 1, "Missing compiled result")
    else:
        need(
            status == 35
            and text.count("AURORA_UEFI_PAYLOAD_FAIL:") == 1
            and "AURORA_UEFI_OK" not in text
            and "AURORA_UEFI_LANGUAGE_OK" not in text,
            "Fault not rejected",
        )
        expected = {
            "bad-handoff": "handoff validation",
            "bad-map": "map ownership",
            "bad-table": "complete mapping tree",
            "wp": "exception",
            "nx": "exception",
        }[mode]
        need(f"AURORA_UEFI_PAYLOAD_FAIL: {expected}" in text, "Wrong rejection")
        if mode in ("bad-handoff", "bad-map", "bad-table"):
            need(
                "AURORA_UEFI_PROTECTION_OK:" not in text and "AURORA_UEFI_OWNERSHIP_OK:" not in text,
                "Unvalidated handoff accepted",
            )
            return
    owned = re.search(r"AURORA_UEFI_OWNERSHIP_OK: arena=(\d+) bytes=(\d+) descriptors=(\d+)", text)
    protected = re.search(r"AURORA_UEFI_PROTECTION_OK: root=(\d+) stack=(\d+)", text)
    need(owned and protected, "Missing independent ownership/protection evidence")
    need(
        text.count("AURORA_UEFI_OWNERSHIP_OK:") == 1 and text.count("AURORA_UEFI_PROTECTION_OK:") == 1,
        "Duplicate ownership/protection evidence",
    )
    need(
        text.index("AURORA_UEFI_PAYLOAD_ENTRY")
        < text.index("AURORA_UEFI_OWNERSHIP_OK:")
        < text.index("AURORA_UEFI_PROTECTION_OK:"),
        "Protection order",
    )
    if mode in ("normal", "stale", "owned-bytes"):
        need(
            text.index("AURORA_UEFI_PROTECTION_OK:")
            < text.index("AURORA_UEFI_LANGUAGE_OK:")
            < text.index("AURORA_UEFI_OK"),
            "Payload completion order",
        )
    arena, size, count = map(int, owned.groups())
    root, stack = map(int, protected.groups())
    need(
        arena >= 0x100000
        and arena % 4096 == 0
        and size == 0x100000
        and arena + size <= 0x100000000
        and 1 <= count <= 512,
        "Invalid arena/map",
    )
    need(
        root == arena + 0x11000 and arena + LAYOUT.kernel_stack_bottom <= stack < arena + LAYOUT.kernel_stack_top,
        "Inherited root/stack",
    )
    owned_lines = [
        "AURORA_UEFI_OWNED_BYTES: length=65 owners=2 pages=2 releases=2 used=0",
        "AURORA_UEFI_OWNED_BYTES: length=513 owners=2 pages=2 releases=4 used=0",
        "AURORA_UEFI_OWNED_BYTES: length=4097 owners=2 pages=4 releases=6 used=0",
        (
            "AURORA_UEFI_OWNED_BYTES_FRAGMENTED: length=4097 owners=2 pages=1,3,5,7 "
            "holders=8 preserved=1 releases=8 used=0"
        ),
        "AURORA_UEFI_OWNED_BYTES_VIEWS: crossing=4095,4096 empty=1 allocations=9 releases=9 used=0",
        "AURORA_UEFI_OWNED_BYTES_RESIZE: case=0 prefix=1 zero=1 preserved=1 allocations=15 releases=15 used=0",
        "AURORA_UEFI_OWNED_BYTES_RESIZE: case=1 prefix=1 zero=1 preserved=1 allocations=21 releases=21 used=0",
        "AURORA_UEFI_OWNED_BYTES_RESIZE: case=2 prefix=1 zero=1 preserved=1 allocations=22 releases=22 used=0",
        "AURORA_UEFI_OWNED_BYTES_RESIZE: case=3 prefix=1 zero=1 preserved=1 allocations=23 releases=23 used=0",
        "AURORA_UEFI_OWNED_BYTES_CLOSED: quota=8194 used=0 allocations=23 releases=23",
        (
            "AURORA_UEFI_OWNED_BYTES_RECORD: sectors=16 pages=1,3 holders=8 snapshot=1 scrubbed=1 "
            "allocations=1 releases=1 used=0"
        ),
        (
            "AURORA_UEFI_OWNED_BYTES_STORAGE: case=0 sectors=16 written=0,7,8,15 boundary=4095,4096 pages=0,1 "
            "holders=0 snapshot=1 bounds=1 readonly=1 visibility=1 durable=0 failure=quota preserved=1 "
            "scrubbed=1 allocations=1 releases=1 used=0"
        ),
        (
            "AURORA_UEFI_OWNED_BYTES_STORAGE: case=1 sectors=16 written=0,7,8,15 boundary=4095,4096 pages=1,3 "
            "holders=8 snapshot=1 bounds=1 readonly=1 visibility=1 durable=0 failure=quota preserved=1 "
            "scrubbed=1 allocations=1 releases=1 used=0"
        ),
        (
            "AURORA_UEFI_OWNED_BYTES_STORAGE: case=2 sectors=16 written=0,7,8,15 boundary=4095,4096 pages=1,3 "
            "holders=14 snapshot=1 bounds=1 readonly=1 visibility=1 durable=0 failure=pages preserved=1 "
            "scrubbed=1 allocations=1 releases=1 used=0"
        ),
        *[
            f"AURORA_UEFI_OWNED_BYTES_COPY: case={case} status={status} bytes=64 closed=1 reused=1 "
            f"canaries=1 allocations={allocations} releases={allocations} used=0"
            for case, status, allocations in ((0, 0, 1), (1, 1, 1), (2, 3, 0), (3, 3, 0))
        ],
    ]
    actual_owned = [line.strip() for line in text.splitlines() if "AURORA_UEFI_OWNED_BYTES" in line]
    need(actual_owned == (owned_lines if mode == "owned-bytes" else []), "Wrong owned-byte lifecycle evidence")
    if mode == "owned-bytes":
        ordered = ["AURORA_UEFI_PROTECTION_OK:", *owned_lines, "AURORA_UEFI_LANGUAGE_OK:", "AURORA_UEFI_OK"]
        need(
            all(text.index(first) < text.index(second) for first, second in zip(ordered, ordered[1:])),
            "Wrong owned-byte grant/cleanup order",
        )
    if mode in ("wp", "nx"):
        fault = re.search(r"AURORA_UEFI_EXCEPTION: vector=(\d+) error=(\d+) rip=(\d+) cr2=(\d+)", text)
        need(fault and text.count("AURORA_UEFI_EXCEPTION:") == 1, "Missing/duplicate hardware fault")
        vector, error, rip, cr2 = map(int, fault.groups())
        need(vector == 14 and error == (3 if mode == "wp" else 17), "Wrong protection error")
        need(cr2 == arena + (0x22000 if mode == "wp" else 0x50000), "Wrong fault target")
        if mode == "nx":
            need(rip == cr2, "NX RIP mismatch")
        else:
            need(
                arena + LAYOUT.kernel_payload_offset
                <= rip
                < arena + LAYOUT.kernel_payload_offset + LAYOUT.kernel_payload_limit,
                "WP origin outside payload",
            )
        need("AURORA_UEFI_LANGUAGE_OK:" not in text, "Fault continued")
