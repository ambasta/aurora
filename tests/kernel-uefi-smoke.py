#!/usr/bin/env python3
from pathlib import Path
import re
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from kernel_uefi_oracle import need, validate


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
        "AURORA_UEFI_OWNED_BYTES_RECORD: sectors=16 pages=1,3 holders=8 snapshot=1 scrubbed=1 "
        "allocations=1 releases=1 used=0\n"
        "AURORA_UEFI_OWNED_BYTES_STORAGE: case=0 sectors=16 written=0,7,8,15 boundary=4095,4096 pages=0,1 "
        "holders=0 snapshot=1 bounds=1 readonly=1 visibility=1 durable=0 failure=quota preserved=1 "
        "scrubbed=1 allocations=1 releases=1 used=0\n"
        "AURORA_UEFI_OWNED_BYTES_STORAGE: case=1 sectors=16 written=0,7,8,15 boundary=4095,4096 pages=1,3 "
        "holders=8 snapshot=1 bounds=1 readonly=1 visibility=1 durable=0 failure=quota preserved=1 "
        "scrubbed=1 allocations=1 releases=1 used=0\n"
        "AURORA_UEFI_OWNED_BYTES_STORAGE: case=2 sectors=16 written=0,7,8,15 boundary=4095,4096 pages=1,3 "
        "holders=14 snapshot=1 bounds=1 readonly=1 visibility=1 durable=0 failure=pages preserved=1 "
        "scrubbed=1 allocations=1 releases=1 used=0\n"
    )
    for case, status, allocations in ((0, 0, 1), (1, 1, 1), (2, 3, 0), (3, 3, 0)):
        records += (
            f"AURORA_UEFI_OWNED_BYTES_COPY: case={case} status={status} bytes=64 closed=1 reused=1 "
            f"canaries=1 allocations={allocations} releases={allocations} used=0\n"
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
                ("sectors=16", "sectors=8"),
                ("written=0,7,8,15", "written=0,1,2,3"),
                ("boundary=4095,4096", "boundary=4094,4095"),
                ("snapshot=1", "snapshot=0"),
                ("bytes=64", "bytes=63"),
                ("closed=1", "closed=0"),
                ("reused=1", "reused=0"),
                ("canaries=1", "canaries=0"),
                ("case=0 status=0", "case=0 status=3"),
                ("case=1 status=1", "case=1 status=0"),
                ("case=2 status=3", "case=2 status=0"),
                ("case=3 status=3", "case=3 status=0"),
                ("bounds=1", "bounds=0"),
                ("readonly=1", "readonly=0"),
                ("visibility=1", "visibility=0"),
                ("durable=0", "durable=1"),
                ("failure=pages", "failure=quota"),
                ("holders=14", "holders=13"),
                ("scrubbed=1", "scrubbed=0"),
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
