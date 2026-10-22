#!/usr/bin/env python3
"""Strict evidence checks for bounded read-only q35 PCI inventory."""

from pathlib import Path
import importlib.util
import re
import sys

spec = importlib.util.spec_from_file_location("acpi_smoke", Path(__file__).with_name("kernel-acpi-smoke.py"))
acpi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acpi)
need = acpi.need
WINDOW = acpi.WINDOW
SUCCESS = ("pci", "pci-devices", "pci-bridge")
MODES = SUCCESS + ("pci-checksum", "pci-cycle", "pci-write", "pci-revoked")
SUFFIX = "AURORA_UEFI_LANGUAGE_OK: value=42\nAURORA_UEFI_OK\n"


def validate(status, text, mode):
    need(mode in MODES, "Unknown PCI mode")
    marker = "AURORA_FIXTURE_READY\n"
    fixture = mode not in SUCCESS
    need(text.count(marker) == (1 if fixture else 0), "Exact PCI fixture selector readiness")
    if fixture:
        need(
            text.index("AURORA_ACPI_WINDOW_CLOSED:") < text.index(marker) < text.index("AURORA_UEFI_PAYLOAD_FAIL:"),
            "Selector admission phase",
        )
        if "AURORA_PCI_APERTURE:" in text:
            need(text.index(marker) < text.index("AURORA_PCI_APERTURE:"), "PCI mapping preceded selector")
        text = text.replace(marker, "", 1)

    if mode in SUCCESS:
        acpi.validate(status, text, "acpi")
    else:
        need(status == 35 and text.count("AURORA_UEFI_PAYLOAD_FAIL:") == 1, "Missing unique PCI rejection")
        need(
            "AURORA_UEFI_LANGUAGE_OK" not in text and "AURORA_UEFI_OK" not in text,
            "Rejected inventory executed language",
        )
        need(
            "AURORA_PCI_FUNCTION:" not in text
            and "AURORA_PCI_INVENTORY:" not in text
            and "AURORA_PCI_WINDOW_CLOSED:" not in text,
            "Rejected inventory published",
        )
        before = text[: text.index("AURORA_UEFI_PAYLOAD_FAIL:")]
        before = re.sub(r"AURORA_UEFI_EXCEPTION:[^\r\n]*[\r\n]*", "", before)
        acpi.validate(33, before + SUFFIX, "acpi")
    closed = "AURORA_ACPI_WINDOW_CLOSED:"
    aperture = re.findall(r"AURORA_PCI_APERTURE: base=(\d+) bytes=(\d+) segment=(\d+) first=(\d+) last=(\d+)", text)
    early = mode == "pci-checksum"
    need(
        len(aperture) == (0 if early else 1) and text.count("AURORA_PCI_APERTURE:") == len(aperture),
        "Missing/duplicate/unexpected aperture",
    )
    if not early:
        need(tuple(map(int, aperture[0])) == (0xE0000000, 0x10000000, 0, 0, 255), "Foreign aperture authority")
        need(text.index(closed) < text.index("AURORA_PCI_APERTURE:"), "Firmware window still active")
    if mode not in SUCCESS:
        need(text.index(closed) < text.index("AURORA_UEFI_PAYLOAD_FAIL:"), "Failure phase order")
        if mode in ("pci-write", "pci-revoked"):
            marker = "AURORA_PCI_WRITE_PROBE" if mode == "pci-write" else "AURORA_PCI_REVOKED_PROBE"
            need(text.count(marker) == 1, "Missing unique config probe")
            fault = re.findall(r"AURORA_UEFI_EXCEPTION: vector=(\d+) error=(\d+) rip=(\d+) cr2=(\d+)", text)
            need(len(fault) == 1, "Missing unique config fault")
            vector, error, rip, cr2 = map(int, fault[0])
            arena = int(re.search(r"OWNERSHIP_OK: arena=(\d+)", text)[1])
            need((vector, error, cr2) == (14, 3 if mode == "pci-write" else 0, WINDOW), "Wrong config protection fault")
            need(arena + 0x22000 <= rip < arena + 0x42000, "Config fault outside payload")
            need(
                text.index("AURORA_PCI_APERTURE:")
                < text.index(marker)
                < text.index("AURORA_UEFI_EXCEPTION:")
                < text.index("AURORA_UEFI_PAYLOAD_FAIL:"),
                "Config probe order",
            )
            need("AURORA_UEFI_PAYLOAD_FAIL: exception" in text, "Wrong hardware failure")
        else:
            need(
                "AURORA_UEFI_EXCEPTION:" not in text and "AURORA_UEFI_PAYLOAD_FAIL: ACPI discovery" in text,
                "Wrong policy failure",
            )
        return
    need("AURORA_PCI_WRITE_PROBE" not in text and "AURORA_PCI_REVOKED_PROBE" not in text, "Unexpected probe")
    rows = re.findall(
        (
            "AURORA_PCI_FUNCTION: segment=(\\d+) bus=(\\d+) device=(\\d+) function=(\\d+) vendor=(\\d+) product"
            "=(\\d+) class=(\\d+) subclass=(\\d+) interface=(\\d+) header=(\\d+) command=(\\d+) secondary=(\\d+"
            ") subordinate=(\\d+)"
        ),
        text,
    )
    need(1 <= len(rows) <= 256 and text.count("AURORA_PCI_FUNCTION:") == len(rows), "Malformed function inventory")
    identities = set()
    classes = set()
    buses = set()
    bridge = False
    host = False
    for row in rows:
        (
            segment,
            bus,
            device,
            function,
            vendor,
            product,
            klass,
            subclass,
            interface,
            header,
            command,
            secondary,
            subordinate,
        ) = map(int, row)
        ident = (segment, bus, device, function)
        need(
            segment == 0 and 0 <= bus <= 255 and device < 32 and function < 8 and ident not in identities,
            "Invalid or repeated BDF",
        )
        need(
            0 < vendor < 65535
            and product <= 65535
            and max(klass, subclass, interface, secondary, subordinate) <= 255
            and header in (0, 1, 128, 129)
            and command <= 65535,
            "Invalid header",
        )
        identities.add(ident)
        buses.add(bus)
        classes.add((klass, subclass, interface))
        if (header & 127) == 1:
            need(
                (klass, subclass) == (6, 4)
                and ((secondary == 0 and subordinate == 0) or bus < secondary <= subordinate),
                "Invalid bridge tuple",
            )
            bridge |= secondary > 0
        else:
            need(secondary == subordinate == 0, "Endpoint granted bridge route")
        host |= ident == (0, 0, 0, 0) and (vendor, product, klass, subclass) == (0x8086, 0x29C0, 6, 0)
    need(host, "Missing q35 host identity")
    summary = re.findall(r"AURORA_PCI_INVENTORY: functions=(\d+) buses=(\d+)", text)
    need(
        len(summary) == 1
        and text.count("AURORA_PCI_INVENTORY:") == 1
        and tuple(map(int, summary[0])) == (len(rows), len(buses))
        and len(buses) <= 64,
        "Inventory summary mismatch",
    )
    reads = re.findall(r"AURORA_PCI_WINDOW_CLOSED: reads=(\d+)", text)
    need(
        len(reads) == 1 and text.count("AURORA_PCI_WINDOW_CLOSED:") == 1 and len(rows) <= int(reads[0]) <= 64 * 256,
        "Config window not revoked",
    )
    need(
        text.index("AURORA_PCI_APERTURE:")
        < text.index("AURORA_PCI_FUNCTION:")
        < text.index("AURORA_PCI_INVENTORY:")
        < text.index("AURORA_PCI_WINDOW_CLOSED:")
        < text.index("AURORA_UEFI_LANGUAGE_OK:"),
        "Inventory phase order",
    )
    need(
        all(
            text.index("AURORA_PCI_APERTURE:") < match.start() < text.index("AURORA_PCI_INVENTORY:")
            for match in re.finditer("AURORA_PCI_FUNCTION:", text)
        ),
        "Inventory row outside collection phase",
    )
    if mode == "pci-devices":
        need({(1, 8, 2), (12, 3, 48), (2, 0, 0)} <= classes, "Missing controlled NVMe/xHCI/network functions")
    if mode == "pci-bridge":
        need(bridge and len(buses) >= 2 and (1, 8, 2) in classes, "Missing configured downstream NVMe")


def self_test():
    prefix = (
        "AURORA_UEFI_ENTRY\nAURORA_UEFI_EXIT_OK: attempts=1\nAURORA_UEFI_PAYLOAD_ENTRY\nAURORA_UEFI_OWNERSHIP_O"
        "K: arena=16777216 bytes=1048576 descriptors=111\nAURORA_UEFI_PROTECTION_OK: root=16846848 stack=170680"
        "32\nAURORA_ACPI_CPU: id=0 uid=0 enabled=1 capable=0 x2=0\nAURORA_ACPI_TOPOLOGY: records=1 enabled=1 ca"
        "pable=0 lapic=4276092928\nAURORA_ACPI_WINDOW_CLOSED: copies=14\n"
    )
    aperture = "AURORA_PCI_APERTURE: base=3758096384 bytes=268435456 segment=0 first=0 last=255\n"

    def row(bus, device, vendor, product, klass, subclass, interface, header=0, secondary=0):
        return (
            f"AURORA_PCI_FUNCTION: segment=0 bus={bus} device={device} funct"
            f"ion=0 vendor={vendor} product={product} class={klass} subclass"
            f"={subclass} interface={interface} header={header} command=6 se"
            f"condary={secondary} subordinate={secondary}\n"
        )

    host = row(0, 0, 0x8086, 0x29C0, 6, 0, 0)
    cases = {}
    for mode in MODES:
        if mode in SUCCESS:
            rows = host
            buses = 1
            count = 1
            if mode == "pci-devices":
                rows += (
                    row(0, 2, 0x1B36, 0x10, 1, 8, 2)
                    + row(0, 3, 0x1B36, 0xD, 12, 3, 48)
                    + row(0, 4, 0x8086, 0x10D3, 2, 0, 0)
                )
                count = 4
            if mode == "pci-bridge":
                rows += row(0, 2, 0x1B36, 0xC, 6, 4, 0, 1, 1) + row(1, 0, 0x1B36, 0x10, 1, 8, 2)
                count = 3
                buses = 2
            text = (
                prefix
                + aperture
                + rows
                + f"AURORA_PCI_INVENTORY: functions={count} buses={buses}\nAURORA_PCI_WINDOW_CLOSED: reads=64\n"
                + SUFFIX
            )
            cases[mode] = (33, text)
        elif mode in ("pci-write", "pci-revoked"):
            marker = "WRITE" if mode == "pci-write" else "REVOKED"
            error = 3 if mode == "pci-write" else 0
            cases[mode] = (
                35,
                prefix + aperture + f"AURORA_PCI_{marker}_PROBE\nAURORA_UEFI_EXCEPTION: vector=14 er"
                f"ror={error} rip=16916480 cr2={WINDOW}\nAURORA_UEFI_PAYLOAD_FAI"
                f"L: exception\n",
            )
        else:
            cases[mode] = (
                35,
                prefix + (aperture if mode == "pci-cycle" else "") + "AURORA_UEFI_PAYLOAD_FAIL: ACPI discovery\n",
            )
    for mode in cases:
        if mode not in SUCCESS:
            status, text = cases[mode]
            cases[mode] = (status, text.replace(prefix, prefix + "AURORA_FIXTURE_READY\n", 1))
    failed = 0
    for mode, (status, text) in cases.items():
        validate(status, text, mode)
        invalid = [(0, text)]
        for line in text.splitlines():
            invalid.extend(
                [(status, text.replace(line + "\n", "", 1)), (status, text.replace(line + "\n", (line + "\n") * 2, 1))]
            )
        if status == 33:
            final_row = [line for line in text.splitlines() if line.startswith("AURORA_PCI_FUNCTION:")][-1] + "\n"
            invalid.append((status, text.replace(final_row, "") + final_row))
            invalid.append((status, final_row + text.replace(final_row, "")))
            invalid.extend(
                [
                    (status, text + "AURORA_UEFI_PAYLOAD_FAIL: unexpected\n"),
                    (status, text.replace("base=3758096384", "base=0")),
                    (status, text.replace("reads=64", "reads=0")),
                    (status, text.replace("vendor=32902", "vendor=65535")),
                ]
            )
        else:
            invalid.extend(
                [
                    (status, text + SUFFIX),
                    (status, text + host),
                    (status, text + "AURORA_PCI_INVENTORY: functions=1 buses=1\n"),
                ]
            )
        if mode in ("pci-write", "pci-revoked"):
            invalid.extend(
                [
                    (status, text.replace("rip=16916480", "rip=0")),
                    (status, text.replace("vector=14", "vector=13")),
                    (status, text.replace(f"cr2={WINDOW}", "cr2=0")),
                ]
            )
        for code, bad in invalid:
            try:
                validate(code, bad, mode)
            except ValueError:
                failed += 1
            else:
                raise RuntimeError(f"Invalid PCI transcript accepted: {mode}")
    print(f"PASS: PCI transcripts {len(cases)} positive and {failed} negative cases")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
        sys.exit(0)
    try:
        validate(int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3])
    except ValueError as error:
        sys.exit(f"FAIL: {error}")
