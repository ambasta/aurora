#!/usr/bin/env python3
"""Fail-closed serial receipts for the pinned q35 namespace-free BAR fixture.

The synthetic PCI success suffix is only an input to an earlier-phase validator;
it is never emitted or represented as evidence that the guest continued.
"""

from pathlib import Path
import importlib.util
import json
import re
import sys

spec = importlib.util.spec_from_file_location("pci_smoke", Path(__file__).with_name("kernel-pci-smoke.py"))
pci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pci)
need = pci.need
MODES = (
    "bar-state",
    "bar-capture",
    "bar-inherited",
    "bar-read",
    "bar-prepare",
    "bar-write",
    "bar-revoked",
    "bar-alias",
)
CLEAN = ("bar-read", "bar-prepare", "bar-write", "bar-revoked", "bar-alias")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from kernel_layout import LAYOUT  # noqa: E402
import kernel_profiles  # noqa: E402

# Cases that boot bar-fixture and read its selector; state/capture/prepare do not.
FIXTURE_MODES = tuple(mode for mode, (image, _) in kernel_profiles.FIXTURE_MODES.items() if image == "bar-fixture")
READS = ((0, 8), (8, 4), (0x14, 4), (0x1C, 4), (0x24, 4), (0x28, 8), (0x30, 8))
WINDOW = 0xFFFF800000001000
CAP = 18023332293183487
VERSION = 0x10400
FAIL = "AURORA_UEFI_PAYLOAD_FAIL: ACPI discovery"
SUFFIX = ["AURORA_UEFI_LANGUAGE_OK: value=42", "AURORA_UEFI_OK"]
DEC = r"(0|[1-9][0-9]*)"


def protocol_lines(text):
    """Ignore firmware preamble only; never silently discard an Aurora record."""
    need(isinstance(text, str) and text.endswith("\n"), "Truncated serial log")
    lines = text.replace("\r\n", "\n").split("\n")[:-1]
    positions = [i for i, line in enumerate(lines) if line == "AURORA_UEFI_ENTRY"]
    need(len(positions) == 1, "Missing/duplicate exact UEFI entry")
    at = positions[0]
    need(not any("AURORA_" in line for line in lines[:at]), "Unexpected pre-entry Aurora record")
    need(all(line.startswith("AURORA_") and "\r" not in line for line in lines[at:]), "Unknown/truncated serial tail")
    return lines[at:]


def resource_bytes(line, kind):
    match = re.fullmatch(r"AURORA_BAR_DESCRIPTOR: kind=" + kind + r" bytes=" + DEC + r" data=([0-9a-f]+)", line)
    need(match is not None, "Malformed raw resource descriptor")
    size, raw = int(match[1]), match[2]
    need(48 <= size <= 738 and (size - 2) % 46 == 0 and len(raw) == size * 2, "Invalid descriptor bound/length")
    data = bytes.fromhex(raw)
    need(data[-2:] == b"\x79\x00", "Invalid EndTag/checksum")
    return data


def resources(data, kind):
    """Independent interpretation of the explicitly selected EDK2 producer."""
    need(kind in ("bar", "root") and (kind != "bar" or len(data) == 48), "Invalid descriptor source")
    result = []
    for at in range(0, len(data) - 2, 46):
        raw = data[at : at + 46]
        get = lambda offset: int.from_bytes(raw[offset : offset + 8], "little")
        typ, flags, specific = raw[3:6]
        granularity, base, maximum, translation, length = (get(i) for i in (6, 14, 22, 30, 38))
        need(
            raw[:3] == b"\x8a\x2b\x00" and typ <= 2 and flags == 0 and translation == 0 and length > 0,
            "Unsupported resource header/translation",
        )
        end = base + length
        if kind == "bar":
            need(
                typ == 0
                and specific == 0
                and granularity == 64
                and 4096 <= length <= 0x100000
                and length & (length - 1) == 0
                and maximum == length - 1
                and base > 0
                and base % length == 0,
                "Invalid named EDK2 BAR profile",
            )
        else:
            need(base <= maximum < (1 << 64) - 1 and maximum - base + 1 == length, "Invalid root inclusive range")
        if typ == 0:
            need(
                specific in (0, 6)
                and granularity in (32, 64)
                and end <= 1 << 40
                and (granularity != 32 or end <= 1 << 32),
                "Resource exceeds physical width/profile",
            )
        elif typ == 1:
            need(specific == 0 and granularity == 0 and end <= 65536, "Invalid EDK2 I/O reservation")
        else:
            need(specific == 0 and granularity == 0 and end <= 256, "Invalid bus reservation")
        need(not any(t == typ and lo < end and base < hi for t, lo, hi, _ in result), "Overlapping root resources")
        result.append((typ, base, end, specific))
    return result


def descriptor_pair(lines):
    bar = resources(resource_bytes(lines[0], "bar"), "bar")[0]
    root = resources(resource_bytes(lines[1], "root"), "root")
    _, base, end, _ = bar
    need(
        sum(t == 0 and lo <= base and end <= hi and s == 0 for t, lo, hi, s in root) == 1,
        "BAR lacks exactly one unambiguous root memory range",
    )
    need(sum(t == 2 and lo == 0 and hi > 0 for t, lo, hi, _ in root) == 1, "Missing target bus coverage")
    need(
        not any(
            base < other + size and other < end
            for other, size in ((0xE0000000, 0x10000000), (0xFEE00000, 4096), (0xFEC00000, 4096))
        ),
        "BAR overlaps protected device range",
    )
    return base, end - base


def fixture_rows(command):
    devices = (
        (0, 0, 32902, 10688, 6, 0, 0),
        (1, 0, 4660, 4369, 3, 0, 0),
        (2, 0, 6966, 16, 1, 8, 2),
        (31, 0, 32902, 10520, 6, 1, 0),
        (31, 2, 32902, 10530, 1, 6, 1),
        (31, 3, 32902, 10544, 12, 5, 0),
    )
    return [
        f"AURORA_PCI_FUNCTION: segment=0 bus=0 device={d} function={f} v"
        f"endor={v} product={p} class={c} subclass={s} interface={i} hea"
        f"der=0 command={command if d == 2 else 7} secondary=0 subordina"
        f"te=0"
        for d, f, v, p, c, s, i in devices
    ]


def validate(status, serial, mode, payload=None):
    need(mode in MODES, "Unknown BAR mode")
    need(status == (33 if mode in ("bar-read", "bar-prepare") else 35), "Wrong emulator exit status")
    lines = protocol_lines(serial)
    # bar-fixture cases read their selector after ACPI closure, before PCI.
    marker = "AURORA_FIXTURE_READY"
    need(lines.count(marker) == (1 if mode in FIXTURE_MODES else 0), "Exact BAR fixture readiness")
    if mode in FIXTURE_MODES:
        at = lines.index(marker)
        need(
            at > 0
            and lines[at - 1].startswith("AURORA_ACPI_WINDOW_CLOSED:")
            and at + 1 < len(lines)
            and lines[at + 1].startswith("AURORA_PCI_APERTURE:"),
            "BAR fixture admission phase",
        )
        lines.remove(marker)
    command = 2 if mode in CLEAN else 7
    descriptor_count = 0 if mode == "bar-state" else 2
    need(
        sum("AURORA_BAR_DESCRIPTOR" in line for line in lines) == descriptor_count,
        "Missing/duplicate/malformed descriptor",
    )
    if descriptor_count:
        base, length = descriptor_pair(lines[1:3])
        prefix = lines[:1] + lines[3:]
    else:
        base = length = None
        prefix = lines[:]
    closed = "AURORA_PCI_WINDOW_CLOSED: reads=39"
    need(prefix.count(closed) == 1, "Missing exact PCI closure")
    split = prefix.index(closed) + 1
    before, tail = prefix[:split], prefix[split:]
    # Require complete anchored lines before handing off to the PCI validator.
    expected = [
        r"AURORA_UEFI_ENTRY",
        r"AURORA_UEFI_EXIT_OK: attempts=1",
        r"AURORA_UEFI_PAYLOAD_ENTRY",
        r"AURORA_UEFI_OWNERSHIP_OK: arena=" + DEC + r" bytes=1048576 descriptors=" + DEC,
        r"AURORA_UEFI_PROTECTION_OK: root=" + DEC + r" stack=" + DEC,
        r"AURORA_ACPI_CPU: id=0 uid=0 enabled=1 capable=0 x2=0",
        r"AURORA_ACPI_TOPOLOGY: records=1 enabled=1 capable=0 lapic=4276092928",
        r"AURORA_ACPI_WINDOW_CLOSED: copies=14",
        r"AURORA_PCI_APERTURE: base=3758096384 bytes=268435456 segment=0 first=0 last=255",
    ]
    expected += list(map(re.escape, fixture_rows(command)))
    expected += [r"AURORA_PCI_INVENTORY: functions=6 buses=1", re.escape(closed)]
    need(
        len(before) == len(expected) and all(re.fullmatch(pattern, line) for pattern, line in zip(expected, before)),
        "Malformed/reordered/incomplete pinned PCI prefix",
    )
    pci.validate(33, "\n".join(before + SUFFIX) + "\n", "pci")
    arena = int(re.search(r"arena=([0-9]+)", before[3])[1])
    if base is not None:
        need(not (base < arena + 0x100000 and arena < base + length), "BAR overlaps owned arena")
    if mode == "bar-state":
        need(
            tail
            == [
                "AURORA_BAR_ADMISSION: segment=0 bus=0 device=2 function=0 command=7 grant=0 reason=bus-master-enabled",
                FAIL,
            ],
            "Missing exact measured BME refusal/fail-stop tail",
        )
        return {"command": command, "reads": 0}
    if mode == "bar-capture":
        need(
            tail == ["AURORA_BAR_REJECTED: reason=resource-profile", FAIL],
            "Strict parser did not refuse named producer/fail stop",
        )
        return {"command": command, "base": base, "length": length, "reads": 0}
    need(tail and tail[0] == "AURORA_BAR_RESERVATIONS: count=3 matched=1", "Incomplete non-target BAR reconciliation")
    if mode == "bar-alias":
        need(
            tail == [tail[0], "AURORA_BAR_REJECTED: reason=mapping-alias", FAIL],
            "Alias rejection issued read authority/continued",
        )
        return {"command": command, "base": base, "length": length, "reads": 0}
    fields = (
        "segment",
        "bus",
        "device",
        "function",
        "command",
        "base",
        "length",
        "cap",
        "version",
        "cc",
        "csts",
        "aqa",
        "asq",
        "acq",
    )
    match = re.fullmatch(
        "AURORA_BAR_STATE: " + " ".join(name + "=" + DEC for name in fields), tail[1] if len(tail) > 1 else ""
    )
    need(match is not None, "Missing/malformed measured BAR state")
    state = dict(zip(fields, map(int, match.groups())))
    need(
        tuple(state[k] for k in fields[:9]) == (0, 0, 2, 0, command, base, length, CAP, VERSION),
        "Foreign BAR identity/resource/CAP/VS",
    )
    values = tuple(state[k] for k in fields[9:])
    if mode == "bar-inherited":
        cc, csts, aqa, asq, acq = values
        need(
            (cc, csts, aqa) == (0x460001, 1, 0x10001)
            and asq > 0
            and acq > 0
            and asq != acq
            and asq % 4096 == acq % 4096 == 0
            and asq < 1 << 40
            and acq < 1 << 40,
            "Inherited active queues not measured",
        )
    else:
        need(values == (0, 0, 0, 0, 0), "Clean receipt contains active/retained controller state")
    close = "AURORA_BAR_WINDOW_CLOSED: reads=7 config=8 revoked=1"
    if mode in ("bar-read", "bar-prepare"):
        preparation = (
            [
                "AURORA_NVME_PREPARED: pages=5 bytes=20480 generation=1 unpublished=1",
                "AURORA_NVME_CANCELLED: pages=0 pool=0 scrubbed=20480",
            ]
            if mode == "bar-prepare"
            else []
        )
        wanted = preparation + [close, "AURORA_BAR_READ_ONLY_OK"] + SUFFIX
    elif mode == "bar-inherited":
        wanted = [close, "AURORA_BAR_REJECTED: reason=inactive-controller-required", FAIL]
    else:
        need(isinstance(payload, dict), "Fault requires linked payload metadata")
        offset, extent = payload.get("offset"), payload.get("bytes")
        faults = payload.get("fault_offsets", {})
        probe = faults.get(mode)
        need(
            type(offset) is int
            and offset == 0x22000
            and type(extent) is int
            and 0 < extent <= LAYOUT.kernel_payload_limit
            and type(probe) is int
            and 0 <= probe < extent
            # The shared bar-fixture image links both fault sites, distinctly.
            and set(faults) == {"bar-write", "bar-revoked"}
            and len(set(faults.values())) == 2,
            "Missing/invalid exact linked probe metadata",
        )
        marker = "AURORA_BAR_WRITE_PROBE" if mode == "bar-write" else "AURORA_BAR_REVOKED_PROBE"
        wanted = ([] if mode == "bar-write" else [close]) + [
            marker,
            f"AURORA_UEFI_EXCEPTION: vector=14 error={3 if mode == 'bar-write' else 0}"
            f" rip={arena + offset + probe} cr2={WINDOW + 8}",
            "AURORA_UEFI_PAYLOAD_FAIL: exception",
        ]
    need(tail[2:] == wanted, "Wrong BAR phase order, fault site, or fail-stop tail")
    return dict(state, reads=7)


if __name__ == "__main__":
    try:
        validate(
            int(sys.argv[1]),
            Path(sys.argv[2]).read_text(),
            sys.argv[3],
            json.loads(Path(sys.argv[4]).read_text()) if len(sys.argv) > 4 else None,
        )
    except (ValueError, IndexError, OSError) as error:
        sys.exit("FAIL: " + str(error))
    print("PASS: strict BAR serial receipt (" + sys.argv[3] + ")")
