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


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from kernel_layout import LAYOUT  # noqa: E402
import kernel_profiles  # noqa: E402
from kernel_uefi_oracle import loader_selection  # noqa: E402

FIXTURE_MODES = kernel_profiles.fixture_cases("platform-fixture", "acpi_")
# Guest runs of the baseline and its two-CPU variant also boot platform-fixture with its row.
SELECTED = ("acpi-duplicate-root", *kernel_profiles.selected_modes("platform-fixture", "acpi_"))
MODES = SELECTED


def validate(status, text, mode, selected=None):
    """`selected` marks a guest run's own loader selector; reused transcript prefixes carry none."""
    need(mode in MODES, "Unknown ACPI mode")
    selected = mode in FIXTURE_MODES if selected is None else selected
    text = loader_selection(text, mode, selected)
    need("AURORA_FIXTURE_READY" not in text, "Unexpected serial fixture selector")
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
        and size == LAYOUT.arena_bytes
        and arena + size <= 0x100000000
        and 1 <= count <= 512,
        "Invalid failure arena",
    )
    need(
        root == arena + 0x11000 and arena + LAYOUT.kernel_stack_bottom <= stack < arena + LAYOUT.kernel_stack_top,
        "Inherited failure root/stack",
    )
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
        need(
            arena + LAYOUT.kernel_payload_offset
            <= rip
            < arena + LAYOUT.kernel_payload_offset + LAYOUT.kernel_payload_limit,
            "Window fault outside owned payload",
        )
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


if __name__ == "__main__":
    try:
        validate(int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3], sys.argv[3] in SELECTED)
    except ValueError as error:
        sys.exit(f"FAIL: {error}")
