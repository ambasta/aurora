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
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from kernel_layout import LAYOUT  # noqa: E402
import kernel_profiles  # noqa: E402

SUCCESS = ("pci", "pci-devices", "pci-bridge")
# Guest runs of every PCI mode, the successful baseline and its variants included, boot pci-fixture.
SELECTED = kernel_profiles.selected_modes("pci-fixture")
MODES = SUCCESS + kernel_profiles.fixture_cases("pci-fixture")
SUFFIX = "AURORA_UEFI_LANGUAGE_OK: value=42\nAURORA_UEFI_OK\n"


def validate(status, text, mode, selected=None):
    """`selected` marks a guest run's own PCI selector; reused transcript prefixes carry none."""
    need(mode in MODES, "Unknown PCI mode")
    marker = "AURORA_FIXTURE_READY\n"
    selected = mode not in SUCCESS if selected is None else selected
    need(text.count(marker) == int(selected), "Exact PCI fixture selector readiness")
    if selected:
        need(text.index("AURORA_ACPI_WINDOW_CLOSED:") < text.index(marker), "Selector admission phase")
        if "AURORA_UEFI_PAYLOAD_FAIL:" in text:
            need(text.index(marker) < text.index("AURORA_UEFI_PAYLOAD_FAIL:"), "Selector admission phase")
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
            need(
                arena + LAYOUT.kernel_payload_offset
                <= rip
                < arena + LAYOUT.kernel_payload_offset + LAYOUT.kernel_payload_limit,
                "Config fault outside payload",
            )
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


if __name__ == "__main__":
    try:
        validate(int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3], sys.argv[3] in SELECTED)
    except ValueError as error:
        sys.exit(f"FAIL: {error}")
