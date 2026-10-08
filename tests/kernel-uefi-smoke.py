#!/usr/bin/env python3
from pathlib import Path
import re
import sys


def need(value, reason):
    if not value:
        raise ValueError(reason)


def validate(status, text, mode):
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
    need(root == arena + 0x11000 and arena + 0x44000 <= stack < arena + 0x48000, "Inherited root/stack")
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
            need(arena + 0x22000 <= rip < arena + 0x42000, "WP origin outside payload")
        need("AURORA_UEFI_LANGUAGE_OK:" not in text, "Fault continued")


def self_test():
    prefix = "AURORA_UEFI_ENTRY\nAURORA_UEFI_EXIT_OK: attempts=1\nAURORA_UEFI_PAYLOAD_ENTRY\n"
    protected = (
        "AURORA_UEFI_OWNERSHIP_OK: arena=16777216 bytes=1048576 descriptors=111\n"
        "AURORA_UEFI_PROTECTION_OK: root=16846848 stack=17068032\n"
    )
    success = prefix + protected + "AURORA_UEFI_LANGUAGE_OK: value=42\nAURORA_UEFI_OK\n"
    cases = {
        "normal": (33, success),
        "stale": (
            33,
            success.replace(
                "AURORA_UEFI_EXIT_OK: attempts=1",
                "AURORA_UEFI_EXIT_REJECTED: attempt=1\nAURORA_UEFI_EXIT_OK: attempts=2",
            ),
        ),
        "bad-handoff": (35, prefix + "AURORA_UEFI_PAYLOAD_FAIL: handoff validation\n"),
        "bad-map": (35, prefix + "AURORA_UEFI_PAYLOAD_FAIL: map ownership\n"),
        "bad-table": (35, prefix + "AURORA_UEFI_PAYLOAD_FAIL: complete mapping tree\n"),
        "wp": (
            35,
            prefix + protected + "AURORA_UEFI_EXCEPTION: vector=14 error=3 rip=16916480 cr2=16916480\n"
            "AURORA_UEFI_PAYLOAD_FAIL: exception\n",
        ),
        "nx": (
            35,
            prefix + protected + "AURORA_UEFI_EXCEPTION: vector=14 error=17 rip=17104896 cr2=17104896\n"
            "AURORA_UEFI_PAYLOAD_FAIL: exception\n",
        ),
    }
    records = (
        "AURORA_UEFI_OWNED_BYTES: length=65 owners=2 pages=2 releases=2 used=0\n"
        "AURORA_UEFI_OWNED_BYTES: length=513 owners=2 pages=2 releases=4 used=0\n"
        "AURORA_UEFI_OWNED_BYTES: length=4097 owners=2 pages=4 releases=6 used=0\n"
        "AURORA_UEFI_OWNED_BYTES_FRAGMENTED: length=4097 owners=2 pages=1,3,5,7 "
        "holders=8 preserved=1 releases=8 used=0\n"
        "AURORA_UEFI_OWNED_BYTES_VIEWS: crossing=4095,4096 empty=1 allocations=9 releases=9 used=0\n"
        "AURORA_UEFI_OWNED_BYTES_RESIZE: case=0 prefix=1 zero=1 preserved=1 allocations=15 releases=15 used=0\n"
        "AURORA_UEFI_OWNED_BYTES_RESIZE: case=1 prefix=1 zero=1 preserved=1 allocations=21 releases=21 used=0\n"
        "AURORA_UEFI_OWNED_BYTES_RESIZE: case=2 prefix=1 zero=1 preserved=1 allocations=22 releases=22 used=0\n"
        "AURORA_UEFI_OWNED_BYTES_RESIZE: case=3 prefix=1 zero=1 preserved=1 allocations=23 releases=23 used=0\n"
        "AURORA_UEFI_OWNED_BYTES_CLOSED: quota=8194 used=0 allocations=23 releases=23\n"
    )
    cases["owned-bytes"] = (33, success.replace("AURORA_UEFI_LANGUAGE_OK:", records + "AURORA_UEFI_LANGUAGE_OK:"))
    cases["stale-exhausted"] = (
        35,
        "AURORA_UEFI_ENTRY\nAURORA_UEFI_EXIT_REJECTED: attempt=1\n"
        "AURORA_UEFI_EXIT_REJECTED: attempt=2\nAURORA_UEFI_EXIT_REJECTED: attempt=3\n"
        "AURORA_UEFI_FAIL: ExitBootServices retry exhausted\n",
    )
    negatives = 0
    for mode, (status, text) in cases.items():
        validate(status, text, mode)
        broken = [
            (0, text),
            (status, text.replace("AURORA_UEFI_EXIT_OK:", "missing")),
            (status, text.replace("AURORA_UEFI_PAYLOAD_ENTRY", "missing")),
            (status, text.replace("attempts=1", "attempts=0").replace("attempts=2", "attempts=0")),
        ]
        for line in text.splitlines():
            broken.append((status, text.replace(line + "\n", (line + "\n") * 2, 1)))
            broken.append((status, text.replace(line + "\n", "", 1)))
        if mode in ("normal", "stale", "owned-bytes"):
            broken.extend(
                [
                    (status, text + "AURORA_UEFI_PAYLOAD_FAIL: unexpected\n"),
                    (status, text.replace("root=16846848", "root=4096")),
                    (status, text.replace("value=42", "value=41")),
                    (
                        status,
                        text.replace("AURORA_UEFI_LANGUAGE_OK: value=42\n", "").replace(
                            "AURORA_UEFI_OWNERSHIP_OK:", "AURORA_UEFI_LANGUAGE_OK: value=42\nAURORA_UEFI_OWNERSHIP_OK:"
                        ),
                    ),
                ]
            )
        else:
            broken.append((status, text + "AURORA_UEFI_OK\n"))
            broken.append(
                (
                    status,
                    text.replace(
                        "AURORA_UEFI_PAYLOAD_FAIL:", "AURORA_UEFI_LANGUAGE_OK: value=42\nAURORA_UEFI_PAYLOAD_FAIL:"
                    )
                    if "AURORA_UEFI_PAYLOAD_FAIL:" in text
                    else text + "AURORA_UEFI_LANGUAGE_OK: value=42\n",
                )
            )
            if mode in ("bad-handoff", "bad-map", "bad-table"):
                broken.append((status, text + "AURORA_UEFI_OWNERSHIP_OK: arena=16777216\n"))
        if mode == "owned-bytes":
            for old, new in [
                ("length=4097", "length=4096"),
                ("owners=2", "owners=1"),
                ("pages=4", "pages=2"),
                ("releases=6", "releases=5"),
                ("used=0", "used=1"),
                ("quota=8194", "quota=8193"),
                ("pages=1,3,5,7", "pages=1,2,3,4"),
                ("holders=8", "holders=7"),
                ("preserved=1", "preserved=0"),
                ("crossing=4095,4096", "crossing=4094,4095"),
                ("empty=1", "empty=0"),
                ("allocations=9", "allocations=10"),
                ("releases=9", "releases=8"),
            ]:
                broken.append((status, text.replace(old, new)))
        if mode in ("wp", "nx"):
            broken.extend(
                [
                    (status, text.replace("vector=14", "vector=13")),
                    (status, text.replace("cr2=16916480", "cr2=1").replace("cr2=17104896", "cr2=1")),
                ]
            )
        for code, bad in broken:
            if bad == text and code == status:
                continue
            try:
                validate(code, bad, mode)
            except ValueError:
                negatives += 1
            else:
                raise RuntimeError(f"Invalid UEFI transcript accepted: {mode}")
    print(f"PASS: UEFI transcripts {len(cases)} positive and {negatives} negative cases")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
        sys.exit(0)
    try:
        validate(int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3])
    except ValueError as error:
        sys.exit(f"FAIL: {error}")
