#!/usr/bin/env python3
from pathlib import Path
import importlib.util
import re
import sys

spec = importlib.util.spec_from_file_location("uefi_smoke", Path(__file__).with_name("kernel-uefi-smoke.py"))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
need = base.need
WINDOW = 0xFFFF800000000000


def validate(status, text, mode):
    if mode == "acpi-duplicate-root":
        need(
            status == 35
            and text.count("AURORA_UEFI_ENTRY") == 1
            and text.count("AURORA_UEFI_FAIL: duplicate or invalid ACPI roots") == 1,
            "Duplicate root accepted",
        )
        need(
            all(
                marker not in text
                for marker in (
                    "AURORA_UEFI_EXIT_",
                    "AURORA_UEFI_PAYLOAD_",
                    "AURORA_UEFI_OWNERSHIP_OK",
                    "AURORA_UEFI_PROTECTION_OK",
                    "AURORA_ACPI_CPU:",
                    "AURORA_ACPI_TOPOLOGY:",
                    "AURORA_ACPI_WINDOW_CLOSED:",
                    "AURORA_UEFI_LANGUAGE_OK",
                    "AURORA_UEFI_OK",
                )
            ),
            "Ambiguous root reached payload",
        )
        need(text.index("AURORA_UEFI_ENTRY") < text.index("AURORA_UEFI_FAIL:"), "Root-failure phase order")
        return
    success = mode in ("acpi", "acpi-two", "acpi-disabled")
    if success:
        base.validate(status, text, "normal")
        rows = re.findall(r"AURORA_ACPI_CPU: id=(\d+) uid=(\d+) enabled=(\d+) capable=(\d+) x2=(\d+)", text)
        expected = 2 if mode == "acpi-two" else 1
        need(len(rows) == expected, "Wrong processor count")
        ids = set()
        uids = set()
        enabled = 0
        capable = 0
        for raw in rows:
            ident, uid, on, available, x2 = map(int, raw)
            need(
                ident not in ids and uid not in uids and on in (0, 1) and available in (0, 1) and x2 in (0, 1),
                "Ambiguous CPU record",
            )
            ids.add(ident)
            uids.add(uid)
            enabled += on
            capable += available
        need(
            ids == set(range(expected))
            and uids == set(range(expected))
            and enabled == (0 if mode == "acpi-disabled" else expected),
            "Disabled or foreign CPU misclassified",
        )
        topology = re.findall(r"AURORA_ACPI_TOPOLOGY: records=(\d+) enabled=(\d+) capable=(\d+) lapic=(\d+)", text)
        need(
            len(topology) == 1 and tuple(map(int, topology[0])) == (expected, enabled, capable, 0xFEE00000),
            "Wrong discovered QEMU topology",
        )
        closed = re.findall(r"AURORA_ACPI_WINDOW_CLOSED: copies=(\d+)", text)
        need(len(closed) == 1 and int(closed[0]) >= 5, "Window was not revoked")
        need(
            text.index("AURORA_UEFI_PROTECTION_OK:")
            < text.index("AURORA_ACPI_CPU:")
            < text.index("AURORA_ACPI_TOPOLOGY:")
            < text.index("AURORA_ACPI_WINDOW_CLOSED:")
            < text.index("AURORA_UEFI_LANGUAGE_OK:"),
            "Discovery order",
        )
        return
    need(
        status == 35
        and text.count("AURORA_UEFI_PAYLOAD_FAIL:") == 1
        and "AURORA_UEFI_OK" not in text
        and "AURORA_UEFI_LANGUAGE_OK" not in text,
        "Rejected discovery continued",
    )
    for marker in (
        "AURORA_UEFI_ENTRY",
        "AURORA_UEFI_EXIT_OK: attempts=1",
        "AURORA_UEFI_PAYLOAD_ENTRY",
        "AURORA_UEFI_PROTECTION_OK:",
    ):
        need(text.count(marker) == 1, f"Missing prior handoff {marker}")
    need(
        text.count("AURORA_UEFI_OWNERSHIP_OK:") == 1
        and text.index("AURORA_UEFI_EXIT_OK:")
        < text.index("AURORA_UEFI_PAYLOAD_ENTRY")
        < text.index("AURORA_UEFI_PROTECTION_OK:")
        < text.index("AURORA_UEFI_PAYLOAD_FAIL:"),
        "Rejected-discovery phase order",
    )
    owned = re.search(r"AURORA_UEFI_OWNERSHIP_OK: arena=(\d+) bytes=(\d+) descriptors=(\d+)", text)
    protected = re.search(r"AURORA_UEFI_PROTECTION_OK: root=(\d+) stack=(\d+)", text)
    need(owned and protected, "Missing failure machine context")
    arena, size, count = map(int, owned.groups())
    root, stack = map(int, protected.groups())
    need(
        arena >= 0x100000
        and arena % 4096 == 0
        and size == 0x100000
        and arena + size <= 0x100000000
        and 1 <= count <= 512,
        "Invalid failure arena",
    )
    need(root == arena + 0x11000 and arena + 0x44000 <= stack < arena + 0x48000, "Inherited failure root/stack")
    need(
        "AURORA_ACPI_CPU:" not in text
        and "AURORA_ACPI_TOPOLOGY:" not in text
        and "AURORA_ACPI_WINDOW_CLOSED:" not in text,
        "Invalid topology issued authority",
    )
    if mode in ("acpi-write", "acpi-revoked"):
        marker = "AURORA_ACPI_WRITE_PROBE" if mode == "acpi-write" else "AURORA_ACPI_REVOKED_PROBE"
        need(
            text.count(marker) == 1 and "AURORA_UEFI_PAYLOAD_FAIL: exception" in text, "Missing controlled window probe"
        )
        fault = re.findall(r"AURORA_UEFI_EXCEPTION: vector=(\d+) error=(\d+) rip=(\d+) cr2=(\d+)", text)
        need(len(fault) == 1, "Missing unique window fault")
        vector, error, rip, address = map(int, fault[0])
        need(
            (vector, error, address) == (14, 3 if mode == "acpi-write" else 0, WINDOW), "Wrong window protection fault"
        )
        need(arena + 0x22000 <= rip < arena + 0x42000, "Window fault outside owned payload")
        need(
            text.index("AURORA_UEFI_PROTECTION_OK:")
            < text.index(marker)
            < text.index("AURORA_UEFI_EXCEPTION:")
            < text.index("AURORA_UEFI_PAYLOAD_FAIL:"),
            "Window fault phase order",
        )
    else:
        need(
            "AURORA_UEFI_PAYLOAD_FAIL: ACPI discovery" in text and "AURORA_UEFI_EXCEPTION:" not in text,
            "Wrong parser rejection",
        )


def self_test():
    prefix = (
        "AURORA_UEFI_ENTRY\nAURORA_UEFI_EXIT_OK: attempts=1\nAURORA_UEFI_PAYLOAD_ENTRY\nAURORA_UEFI_OWNERSHIP_O"
        "K: arena=16777216 bytes=1048576 descriptors=111\nAURORA_UEFI_PROTECTION_OK: root=16846848 stack=170680"
        "32\n"
    )
    cases = {}
    for mode, count, enabled in [("acpi", 1, 1), ("acpi-two", 2, 2), ("acpi-disabled", 1, 0)]:
        text = prefix + "".join(
            f"AURORA_ACPI_CPU: id={i} uid={i} enabled={1 if enabled else 0} capable=0 x2=0\n" for i in range(count)
        )
        text += (
            f"AURORA_ACPI_TOPOLOGY: records={count} enabled={enabled} capabl"
            f"e=0 lapic=4276092928\nAURORA_ACPI_WINDOW_CLOSED: copies=12\nAU"
            f"RORA_UEFI_LANGUAGE_OK: value=42\nAURORA_UEFI_OK\n"
        )
        cases[mode] = (33, text)
    for mode in ("acpi-checksum", "acpi-bad-entry", "acpi-duplicate", "acpi-bad-source", "acpi-changed-header"):
        cases[mode] = (35, prefix + "AURORA_UEFI_PAYLOAD_FAIL: ACPI discovery\n")
    cases["acpi-duplicate-root"] = (35, "AURORA_UEFI_ENTRY\nAURORA_UEFI_FAIL: duplicate or invalid ACPI roots\n")
    for mode, error, marker in [("acpi-write", 3, "WRITE"), ("acpi-revoked", 0, "REVOKED")]:
        cases[mode] = (
            35,
            prefix + f"AURORA_ACPI_{marker}_PROBE\nAURORA_UEFI_EXCEPTION: vector=14 e"
            f"rror={error} rip=16916480 cr2={WINDOW}\nAURORA_UEFI_PAYLOAD_FA"
            f"IL: exception\n",
        )
    failures = 0
    for mode, (status, text) in cases.items():
        validate(status, text, mode)
        negatives = [(0, text)]
        for line in text.splitlines():
            negatives.append((status, text.replace(line + "\n", "", 1)))
            negatives.append((status, text.replace(line + "\n", (line + "\n") * 2, 1)))
        if status == 33:
            negatives.extend(
                [
                    (status, text + "AURORA_UEFI_PAYLOAD_FAIL: unexpected\n"),
                    (status, text.replace("id=0", "id=9")),
                    (
                        status,
                        text.replace("enabled=0", "enabled=1")
                        if mode == "acpi-disabled"
                        else text.replace("enabled=1", "enabled=0"),
                    ),
                    (status, text.replace("copies=12", "copies=0")),
                    (status, text.replace("lapic=4276092928", "lapic=4276092929")),
                ]
            )
        else:
            negatives.extend(
                [
                    (status, text + "AURORA_UEFI_OK\n"),
                    (status, text + "AURORA_ACPI_CPU: id=0 uid=0 enabled=1 capable=0 x2=0\n"),
                ]
            )
        if mode == "acpi-duplicate-root":
            for extra in (
                "AURORA_UEFI_LANGUAGE_OK: value=42",
                "AURORA_UEFI_OWNERSHIP_OK: arena=16777216",
                "AURORA_UEFI_PROTECTION_OK: root=1",
                "AURORA_ACPI_TOPOLOGY: records=1",
                "AURORA_ACPI_WINDOW_CLOSED: copies=12",
            ):
                negatives.append((status, text + extra + "\n"))
        if mode in ("acpi-write", "acpi-revoked"):
            marker = "AURORA_ACPI_WRITE_PROBE" if mode == "acpi-write" else "AURORA_ACPI_REVOKED_PROBE"
            negatives.extend(
                [
                    (status, text.replace("rip=16916480", "rip=0")),
                    (status, text.replace("root=16846848", "root=4096")),
                    (status, text.replace("stack=17068032", "stack=0")),
                    (
                        status,
                        text.replace(marker + "\n", "").replace(
                            "AURORA_UEFI_PAYLOAD_FAIL:", marker + "\nAURORA_UEFI_PAYLOAD_FAIL:"
                        ),
                    ),
                ]
            )
            negatives.extend(
                [(status, text.replace("vector=14", "vector=13")), (status, text.replace(f"cr2={WINDOW}", "cr2=0"))]
            )
        for code, bad in negatives:
            try:
                validate(code, bad, mode)
            except ValueError:
                failures += 1
            else:
                raise RuntimeError(f"Invalid ACPI transcript accepted: {mode}")
    print(f"PASS: ACPI transcripts {len(cases)} positive and {failures} negative cases")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
        sys.exit(0)
    try:
        validate(int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3])
    except ValueError as error:
        sys.exit(f"FAIL: {error}")
