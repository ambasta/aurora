#!/usr/bin/env python3
"""Fail-closed receipts for the explicitly selected QEMU 10.0.13 IVRS fixture.

This is discovery evidence, never DMA isolation. Synthetic suffixes below only
exercise an earlier-phase validator; they do not claim that the guest continued.
The historical BAR/PCI validators and their default profiles remain unchanged.
"""

from pathlib import Path
import importlib.util
import json
import re
import sys


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


bar = module("ivrs_bar", "kernel-uefi-bar-smoke.py")
need = bar.need
DEC = bar.DEC
# Historical scenario/synthetic oracle coverage, not the current launch catalog.
# Shared write/revoked artifacts still require current selectors and both fault sites.
HISTORICAL_MODES = (
    "ivrs-default",
    "ivrs-read",
    "ivrs-write",
    "ivrs-revoked",
    "ivrs-pair",
    "ivrs-alias",
    "ivrs-reserved",
    "ivrs-scope",
    "ivrs-capability",
    "ivrs-range",
    "ivrs-missing",
)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from kernel_layout import LAYOUT  # noqa: E402
import kernel_profiles  # noqa: E402

EARLY = ("ivrs-pair", "ivrs-alias", "ivrs-reserved", "ivrs-missing")
READ_MODES = ("ivrs-read", "ivrs-write", "ivrs-revoked")
BASE, LENGTH, WINDOW = 0xFED80000, 0x4000, 0xFFFF800000002000
READS = ((0x18, 8), (0x30, 8), (0x2020, 8))
PROFILE = "qemu-10.0.13-cold"
TABLE = bytes.fromhex(
    "49565253a80000000112424f43485320425850432020202001000000425850430100000001280000000000000000000010d13400180040000000d8fe0000000000000000440000000200000002080000021000000218000002f8000002fa000002fb000011114400180040000000d8fe000000000000000000000000d32900000000000000000000000000000200000002080000021000000218000002f8000002fa000002fb0000"
)
HEADER = bytes.fromhex(
    "2210191407001000000006080000000000000000000000000000000000000000000000000000000000000000f41a0011000000006000000000000000ff000000"
)
CAPABILITY = bytes.fromhex(
    "0f00031f0000d8fe00000000000000ff40281800000000000540000008580000055c8000000000000000000000000000"
)
REQUESTERS = (0, 8, 16, 24, 248, 250, 251)
SUMMARY = f"AURORA_IVRS_TABLE: units=1 records=2 requesters=7 base={BASE} bytes={LENGTH}"
POLICY = f"AURORA_IVRS_READ_POLICY: profile={PROFILE} base={BASE} bytes={LENGTH}"
REGISTERS = "AURORA_IVRS_REGISTERS: control=0 efr=10707 status=0"
CLOSED = "AURORA_IVRS_WINDOW_CLOSED: reads=3 pages=2 revoked=1"


def table_facts(raw, match_inventory=True):
    """Independent bounded interpretation, including paired scope equality."""
    need(isinstance(raw, bytes) and 120 <= len(raw) <= 2160, "Invalid IVRS extent")
    u = lambda at, size: int.from_bytes(raw[at : at + size], "little")
    need(
        raw[:4] == b"IVRS" and u(4, 4) == len(raw) and raw[8] == 1 and sum(raw) % 256 == 0,
        "Invalid IVRS signature, length, revision or checksum",
    )
    need(u(36, 4) == 0x2801 and u(40, 8) == 0, "Unsupported IVRS header features")
    blocks = {}
    at = 48
    while at < len(raw):
        need(len(raw) - at >= 4, "Truncated IVHD header")
        kind, length = raw[at], u(at + 2, 2)
        need(kind in (0x10, 0x11) and kind not in blocks, "Unknown/duplicate IVHD or IVMD")
        header = 24 if kind == 0x10 else 40
        need(header + 4 <= length <= len(raw) - at and (length - header) % 4 == 0, "Malformed IVHD extent")
        need(
            raw[at + 1] == (0xD1 if kind == 0x10 else 0x11)
            and u(at + 6, 2) == 0x40
            and u(at + 18, 2) == 0
            and u(at + 20, 4) == (0x44 if kind == 0x10 else 0),
            "Unsupported IVHD flags/features",
        )
        if kind == 0x11:
            need(u(at + 24, 8) == 0x29D3 and u(at + 32, 8) == 0, "Unsupported IVHD extended features")
        base = u(at + 8, 8)
        need(base and base % 0x4000 == 0 and base + 0x4000 <= 1 << 40, "Invalid IVHD aperture")
        scopes = []
        for offset in range(at + header, at + length, 4):
            need(raw[offset] == 2 and raw[offset + 3] == 0, "Unsupported IVHD scope semantics")
            requester = u(offset + 1, 2)
            need(requester not in scopes, "Duplicate IVHD requester")
            scopes.append(requester)
        blocks[kind] = ((u(at + 16, 2), u(at + 4, 2), u(at + 6, 2), base), set(scopes))
        at += length
    need(set(blocks) == {0x10, 0x11} and blocks[0x10] == blocks[0x11], "Missing/conflicting paired IVHD")
    identity, scopes = blocks[0x10]
    need(identity == (0, 24, 0x40, BASE), "IVRS identity mismatch")
    if match_inventory:
        need(scopes == set(REQUESTERS), "IVRS inventory mismatch")
    return {"base": BASE, "length": LENGTH, "requesters": tuple(sorted(scopes))}


def capability_facts(header, capability):
    need(len(header) == 64 and len(capability) == 48, "Truncated PCI capability snapshot")
    h = lambda at, width: int.from_bytes(header[at : at + width], "little")
    c = lambda at, width: int.from_bytes(capability[at : at + width], "little")
    need(
        h(0, 4) == 0x14191022
        and h(4, 2) == 7
        and h(6, 2) == 0x10
        and h(8, 4) == 0x08060000
        and h(14, 1) == 0
        and h(0x34, 1) == 0x60,
        "Wrong IOMMU PCI identity/state",
    )
    need(
        tuple(c(at, 4) for at in range(0, 24, 4)) == (0x1F03000F, BASE, 0, 0xFF000000, 0x182840, 0),
        "Foreign IOMMU capability/base/enable state",
    )
    pointer = h(0x34, 1)
    for expected, kind, following in ((0x60, 5, 0x5C), (0x5C, 8, 0x58), (0x58, 5, 0x40), (0x40, 15, 0)):
        need(
            pointer == expected and c(pointer - 0x40, 1) == kind and c(pointer - 0x40 + 1, 1) == following,
            "Unreachable/cyclic/malformed IOMMU capability chain",
        )
        pointer = following
    need(header == HEADER and capability == CAPABILITY, "Snapshot differs from pinned cold fixture")
    return {"mmio_enable": 0, "base": BASE}


def fixture_rows():
    rows = bar.fixture_rows(2)
    rows.insert(
        3,
        (
            "AURORA_PCI_FUNCTION: segment=0 bus=0 device=3 function=0 vendor=4130 product=5145 class=8 subclass"
            "=6 interface=0 header=0 command=7 secondary=0 subordinate=0"
        ),
    )
    return rows


def raw_record(line):
    match = re.fullmatch(r"AURORA_IVRS_RAW: bytes=" + DEC + r" data=([0-9a-f]+)", line)
    need(
        match is not None and int(match[1]) * 2 == len(match[2]) and int(match[1]) <= 2160, "Malformed IVRS raw receipt"
    )
    return bytes.fromhex(match[2])


def validate(status, serial, mode, payload=None):
    need(mode in HISTORICAL_MODES and status == (33 if mode == "ivrs-read" else 35), "Wrong IVRS mode/process status")
    # Parse raw UART framing once, including CRLF from provenance artifact replay.
    # Every live IVRS mode is a platform-fixture row, echoed right after loader entry.
    lines = bar.protocol_lines(serial, mode if mode in kernel_profiles.FIXTURE_MODES else None)
    need("AURORA_FIXTURE_READY" not in lines, "Unexpected serial fixture selector")
    need(len(lines) >= 11, "Truncated IVRS receipt")
    base, length = bar.descriptor_pair(lines[1:3])
    expected = [
        r"AURORA_UEFI_ENTRY",
        r"AURORA_UEFI_EXIT_OK: attempts=1",
        r"AURORA_UEFI_PAYLOAD_ENTRY",
        r"AURORA_UEFI_OWNERSHIP_OK: arena=" + DEC + rf" bytes={LAYOUT.arena_bytes} descriptors=" + DEC,
        r"AURORA_UEFI_PROTECTION_OK: root=" + DEC + r" stack=" + DEC,
        r"AURORA_ACPI_CPU: id=0 uid=0 enabled=1 capable=0 x2=0",
        r"AURORA_ACPI_TOPOLOGY: records=1 enabled=1 capable=0 lapic=4276092928",
    ]
    # Entry + two descriptors + seven handoff/topology records.
    prefix = lines[:1] + lines[3:9]
    need(
        len(prefix) == len(expected) and all(re.fullmatch(pattern, line) for pattern, line in zip(expected, prefix)),
        "Malformed/reordered IVRS handoff prefix",
    )
    bar.pci.acpi.base.validate(33, "\n".join(prefix + bar.SUFFIX) + "\n", "normal")
    arena = int(re.search(r"arena=([0-9]+)", prefix[3])[1])
    need(not (base < arena + LAYOUT.arena_bytes and arena < base + length), "NVMe BAR overlaps owned arena")
    need(not (base < BASE + LENGTH and BASE < base + length), "NVMe BAR aliases IOMMU aperture")
    need(not (BASE < arena + LAYOUT.arena_bytes and arena < BASE + LENGTH), "IOMMU aperture overlaps owned arena")
    tail = lines[9:]
    result = dict(command=2, base=base, length=length, reads=0, iommu_reads=0, early=mode in EARLY)
    if mode == "ivrs-missing":
        need(tail == ["AURORA_IVRS_REJECTED: reason=missing-table", bar.FAIL], "Missing-table failure continued")
        return result
    raw = raw_record(tail[0])
    tail = tail[1:]
    if mode in EARLY:
        need(raw == changed_table(mode), "Table differs from exact mode injection")
        try:
            table_facts(raw)
        except ValueError:
            pass
        else:
            raise ValueError("Rejected table independently validates")
        need(
            tail == ["AURORA_IVRS_REJECTED: reason=table-profile", bar.FAIL],
            "Parser rejection continued or read registers",
        )
        return result
    need(
        raw == (changed_table(mode) if mode == "ivrs-scope" else TABLE),
        "IVRS bytes differ from pinned producer/injection",
    )
    table_facts(raw, match_inventory=mode != "ivrs-scope")
    wanted = [
        SUMMARY,
        "AURORA_ACPI_WINDOW_CLOSED: copies=17",
        "AURORA_PCI_APERTURE: base=3758096384 bytes=268435456 segment=0 first=0 last=255",
    ]
    wanted += fixture_rows() + ["AURORA_PCI_INVENTORY: functions=7 buses=1", "AURORA_PCI_WINDOW_CLOSED: reads=39"]
    if mode == "ivrs-scope":
        need(
            tail == wanted + ["AURORA_IVRS_REJECTED: reason=requester-coverage", bar.FAIL],
            "Requester mismatch did not stop before BAR reads",
        )
        return result
    wanted += [
        "AURORA_BAR_RESERVATIONS: count=3 matched=1",
        f"AURORA_BAR_STATE: segment=0 bus=0 device=2 function=0 command="
        f"2 base={base} length={length} cap={bar.CAP} version={bar.VERSION}"
        f" cc=0 csts=0 aqa=0 asq=0 acq=0",
        "AURORA_BAR_WINDOW_CLOSED: reads=7 config=9 revoked=1",
        "AURORA_BAR_READ_ONLY_OK",
    ]
    need(tail[: len(wanted)] == wanted, "Incomplete/reordered PCI/NVMe reconciliation")
    result["reads"] = 7
    tail = tail[len(wanted) :]
    match = re.fullmatch(r"AURORA_IVRS_PCI_RAW: header=([0-9a-f]{128}) cap=([0-9a-f]{96})", tail[0] if tail else "")
    need(match is not None, "Missing complete IOMMU PCI snapshot")
    header, capability = map(bytes.fromhex, match.groups())
    tail = tail[1:]
    if mode == "ivrs-capability":
        changed = bytearray(CAPABILITY)
        changed[4] ^= 2
        need(header == HEADER and capability == bytes(changed), "Capability differs from exact snapshot injection")
        try:
            capability_facts(header, capability)
        except ValueError:
            pass
        else:
            raise ValueError("Rejected PCI snapshot independently validates")
        need(tail == ["AURORA_IVRS_REJECTED: reason=capability", bar.FAIL], "Capability failure continued")
        return result
    capability_facts(header, capability)
    if mode in ("ivrs-default", "ivrs-range"):
        reason = "mmio-disabled" if mode == "ivrs-default" else "resource-admission"
        wanted = (
            ["AURORA_IVRS_RANGE_PROBE: type=7 base=4275568640 pages=4 attributes=8"] if mode == "ivrs-range" else []
        )
        need(
            tail == wanted + ["AURORA_IVRS_REJECTED: reason=" + reason, bar.FAIL],
            "Admission failure acquired MMIO authority",
        )
        return result
    need(tail[:2] == [POLICY, REGISTERS], "Wrong explicit read profile/register values")
    result["iommu_reads"] = 3
    tail = tail[2:]
    if mode == "ivrs-read":
        need(
            tail == [CLOSED, "AURORA_IVRS_READ_ONLY_OK"] + bar.SUFFIX,
            "Read lease not closed before successful continuation",
        )
    else:
        need(
            isinstance(payload, dict) and set(payload) == {"offset", "bytes", "fault_offsets"},
            "Missing exact payload metadata",
        )
        offset, extent = payload.get("offset"), payload.get("bytes")
        faults = payload.get("fault_offsets")
        probe = faults.get(mode) if isinstance(faults, dict) else None
        need(
            type(offset) is int
            and offset == LAYOUT.kernel_payload_offset
            and type(extent) is int
            and 0 < extent <= LAYOUT.kernel_payload_limit
            and type(probe) is int
            and 0 < probe < extent
            and set(faults) == {"ivrs-write", "ivrs-revoked"}
            and all(type(value) is int and 0 < value < extent for value in faults.values())
            and len(set(faults.values())) == 2,
            "Invalid linked IVRS probe metadata",
        )
        write = mode == "ivrs-write"
        expected = ([] if write else [CLOSED]) + [
            "AURORA_IVRS_" + ("WRITE" if write else "REVOKED") + "_PROBE",
            f"AURORA_UEFI_EXCEPTION: vector=14 error={3 if write else 0} rip"
            f"={arena + offset + probe} cr2={WINDOW + 0x18}",
            "AURORA_UEFI_PAYLOAD_FAIL: exception",
        ]
        need(tail == expected, "Wrong IOMMU fault address/site/phase or fail-stop tail")
    return result


def changed_table(mode):
    raw = bytearray(TABLE)
    if mode == "ivrs-pair":
        raw[108:116] = (BASE + 4096).to_bytes(8, "little")
    elif mode == "ivrs-alias":
        raw[72] = 0x42
    elif mode == "ivrs-reserved":
        raw.extend(bytes(32))
        raw[168] = 0x20
        raw[170:172] = (32).to_bytes(2, "little")
        raw[184:192] = (0x100000).to_bytes(8, "little")
        raw[192:200] = (4096).to_bytes(8, "little")
        raw[4:8] = len(raw).to_bytes(4, "little")
    elif mode == "ivrs-scope":
        raw[81] = raw[149] = 17
    raw[9] = 0
    raw[9] = -sum(raw) & 255
    return bytes(raw)


if __name__ == "__main__":
    try:
        result = validate(
            int(sys.argv[1]),
            Path(sys.argv[2]).read_text(),
            sys.argv[3],
            json.loads(Path(sys.argv[4]).read_text()) if len(sys.argv) > 4 else None,
        )
    except (ValueError, IndexError, KeyError, OSError) as error:
        sys.exit("FAIL: " + str(error))
    print("PASS: strict IVRS serial " + json.dumps(result, sort_keys=True))
