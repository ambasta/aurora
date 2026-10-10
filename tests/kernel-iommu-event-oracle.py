#!/usr/bin/env python3
"""Compiler-free synthetic controls for complete Event serial/RAM/QMP evidence."""

import copy
import json
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import kernel_iommu_event_oracle as oracle


def fixture(selector=0, sink=b"\x01\x02\x03\x04"):
    """Construct independent fixture bytes, without calling oracle expectations."""
    mode = ("iommu-event-denial", "iommu-event-success", "iommu-event-overflow", "iommu-event-command-error")[selector]
    arena, descriptors = 0x5000000, 100
    rows = [
        ("handoff.bin", None, 0, 128, 8),
        ("terminal.bin", "terminal", 0x35000, 672, 8),
        ("before-ring.bin", "before_ring", 0x37000, 4096, 4096),
        ("after-ring.bin", "after_ring", 0x36000, 4096, 4096),
        ("live-ring.bin", "ring", 0x40000, 4096, 4096),
        ("backing.bin", "backing", 0x38000, 32768, 4096),
    ]
    receipt = {
        "mode": mode,
        "image": {
            "mode": mode,
            "backing": {
                "payload_rw_begin": 0x13000,
                "payload_memory_end": 0x20000,
                "objects": {
                    role: dict(offset=offset - 0x22000, arena_offset=offset, bytes=size, alignment=align)
                    for name, role, offset, size, align in rows
                    if role
                },
            },
            "payload_layout": dict(
                payload_size=75888, payload_text_end=0x12000, payload_read_end=0x13000, payload_memory_end=0x20000
            ),
        },
    }
    p = {name: arena + offset for name, _, offset, _, _ in rows}
    b, ring = p["backing.bin"], p["live-ring.bin"]
    transfers, completion, polls, ack, entered, output, tail, status = (
        (5, 0, 3, 2, 1, 192, 32, 10),
        (2, 0, 1, 0, 1, 0, 0, 8),
        (257, 2, 0, 0, 0, 0, 4080, 11),
        (0, 4, 1, 0, 1, 57, 16, 10),
    )[selector]
    memory = bytearray()
    for slot in range(256):
        a, v = 0xF5A55A5ADEAD0000 + slot, 0xBAD0000000000000 + 16 * slot
        if selector == 0 and slot in (0, 1):
            a, v = (0x2050123400000020, 0x3100) if slot == 0 else (0x2070123400000020, 0x4100)
        if selector == 2 and slot < 255:
            a, v = 0x2070123400000020, 0x4100
        if selector == 3 and slot == 0:
            a, v = 0x5000000000000000, b + 12288
        memory += struct.pack("<QQ", a, v)
    if selector:
        sink = bytes.fromhex("6f4d2b19" if selector == 1 else "d2b49678")
    data = b"".join(
        bytes(range(160, 176)) + value + bytes(range(80, 96))
        for value in [bytes.fromhex(x) for x in ("82a4c6e8", "416385a7", "6f4d2b19")] + [sink]
    )
    regs = [
        b + 1,
        ((b + 12288) | (8 << 56)) if selector == 3 else 0,
        ring | (8 << 56),
        0x1005 if selector == 3 else 5,
        0x29D3,
        0,
        16 if selector == 3 else 0,
        0,
        tail,
        status,
        0 if selector == 3 else 2,
        0 if selector == 3 else 4,
    ]
    post = list(regs)
    post[7] = 32 if selector == 0 else 0
    terminal = struct.pack(
        "<24Q",
        0x41554556494E5431,
        1,
        selector,
        5,
        0,
        completion,
        b,
        ring,
        p["before-ring.bin"],
        p["after-ring.bin"],
        4096,
        transfers,
        transfers,
        257,
        polls,
        ack,
        output,
        1,
        1,
        entered,
        0,
        1,
        1,
        3,
    )
    terminal += struct.pack("<12Q", *regs) + struct.pack("<12Q", *post) + data + data
    backing = bytearray(32768)
    struct.pack_into("<QQ", backing, 1024, (b + 8192) | 0x6000000000000203, 0x1234)
    for index, offset, permission in ((3, 16384, 2), (4, 20480, 1), (5, 24576, 3), (6, 28672, 3)):
        struct.pack_into("<Q", backing, 8192 + index * 8, (b + offset) | 1 | (permission << 61))
    for i, offset in enumerate((16384, 20480, 24576, 28672)):
        backing[offset + 240 : offset + 276] = data[36 * i : 36 * (i + 1)]
    handoff = struct.pack(
        "<QIIQQQQII9Q",
        0x41524F5255454649,
        4,
        128,
        1048576,
        arena,
        descriptors * 48,
        48,
        1,
        1,
        75888,
        73728,
        77824,
        131072,
        arena + 0x11000,
        8,
        arena + 0x22000,
        0x7000000,
        arena + 0x81000,
    )
    captures = {
        "handoff.bin": handoff,
        "terminal.bin": terminal,
        "backing.bin": bytes(backing),
        **{name: bytes(memory) for name in ("before-ring.bin", "after-ring.bin", "live-ring.bin")},
    }
    lines = [
        "Firmware banner",
        "AURORA_UEFI_ENTRY",
        "AURORA_BAR_DESCRIPTOR: kind=bar bytes=48 data=" + "00" * 48,
        "AURORA_BAR_DESCRIPTOR: kind=root bytes=140 data=" + "00" * 140,
        "AURORA_UEFI_EXIT_OK: attempts=1",
        "AURORA_UEFI_PAYLOAD_ENTRY",
        f"AURORA_UEFI_OWNERSHIP_OK: arena={arena} bytes=1048576 descriptors={descriptors}",
        f"AURORA_UEFI_PROTECTION_OK: root={arena + 0x11000} stack={arena + 0x47FF0}",
        "AURORA_UEFI_LANGUAGE_OK: value=42",
        "AURORA_ACPI_CPU: id=0 uid=0 enabled=1 capable=0 x2=0",
        "AURORA_ACPI_TOPOLOGY: records=1 enabled=1 capable=0 lapic=4276092928",
        "AURORA_IVRS_RAW: bytes=176 data=" + "00" * 176,
        "AURORA_IVRS_TABLE: units=1 records=2 requesters=6 base=4275568640 bytes=16384",
        "AURORA_ACPI_WINDOW_CLOSED: copies=15",
        "AURORA_PCI_APERTURE: base=3758096384 bytes=268435456 segment=0 first=0 last=255",
    ]
    for dev, fun, ven, prod, cls, sub, interface in (
        (0, 0, 32902, 10688, 6, 0, 0),
        (1, 0, 4130, 5145, 8, 6, 0),
        (4, 0, 4660, 4584, 0, 255, 0),
        (31, 0, 32902, 10520, 6, 1, 0),
        (31, 2, 32902, 10530, 1, 6, 1),
        (31, 3, 32902, 10544, 12, 5, 0),
    ):
        lines.append(
            f"AURORA_PCI_FUNCTION: segment=0 bus=0 device={dev} function={fun} vendor={ven} "
            f"product={prod} class={cls} subclass={sub} interface={interface} "
            "header=0 command=7 secondary=0 subordinate=0"
        )
    lines += [
        "AURORA_PCI_INVENTORY: functions=6 buses=1",
        "AURORA_PCI_WINDOW_CLOSED: reads=39",
        "AURORA_EVENT_ADMISSION_OK: default-ivrs=1 handoff-complete=1",
        "AURORA_IOMMU_EVENT_BACKING: terminal=%016x data=%016x ring=%016x pre=%016x post=%016x"
        % (p["terminal.bin"], b, ring, p["before-ring.bin"], p["after-ring.bin"]),
    ]
    for phase, registers in (("pre", regs), ("post", post)):
        if phase == "post" and selector == 0:
            lines += [
                "IOMMU F raw=2050123400000020/0000000000003100 rid=0020 dom=1234 dva=0000000000003100 status=0a",
                "IOMMU F raw=2070123400000020/0000000000004100 rid=0020 dom=1234 dva=0000000000004100 status=0a",
            ]
        if phase == "post" and selector == 3:
            lines += ["IOMMU C raw=5000000000000000/%016x status=0a" % (b + 12288)]
        lines += [
            f"AURORA_IOMMU_EVENT_REGISTERS: phase={phase} producer_quiet=0000000000000001 words="
            + "".join(f"{v:016x}/" for v in registers),
            f"AURORA_IOMMU_EVENT_DATA: phase={phase} guarded=" + data.hex(),
        ]
        lines += [
            f"AURORA_IOMMU_EVENT_RAW: phase={phase} offset={at:016x} bytes=" + memory[at : at + 16].hex()
            for at in range(0, 4096, 16)
        ]
    lines += [
        f"AURORA_IOMMU_EVENT_TERMINAL: case={selector:016x} completion={completion:016x} "
        f"checks=0000000000000003 submitted={transfers:016x} completed={transfers:016x} "
        f"polls={polls:016x} acknowledged={ack:016x} readiness=0000000000000101 entered={entered:016x}"
    ]
    qmp = [json.dumps({"QMP": {"version": {}, "capabilities": []}})]
    commands = [
        ("qmp_capabilities", {}, {}),
        ("stop", {}, {}),
        ("query-status", {}, {"status": "paused", "running": False}),
    ]
    commands += [
        ("human-monitor-command", {"arguments": {"command-line": f'pmemsave {p[name]} {size} "{name}"'}}, "")
        for name, _, _, size, _ in rows
    ]
    commands += [("quit", {}, {})]
    for i, (command, arguments, result) in enumerate(commands, 1):
        qmp.append("SEND " + json.dumps(dict(execute=command, id=i, **arguments)))
        if i in (2, 10):
            qmp.append(json.dumps({"event": "STOP" if i == 2 else "SHUTDOWN"}))
        qmp.append(json.dumps({"return": result, "id": i}))
    return [mode, receipt, ("\r\n".join(lines) + "\r\n").encode(), captures, ("\n".join(qmp) + "\n").encode()]


class Controls(unittest.TestCase):
    def reject(self, evidence):
        with self.assertRaises(ValueError):
            oracle.validate(*evidence)

    def test_four_complete_profiles_and_nonzero_denial_sink(self):
        for selector in range(4):
            self.assertEqual(oracle.validate(*fixture(selector))["selector"], selector)
        oracle.validate(*fixture(0, b"\x00" * 4))
        for bad in (bytes.fromhex("82a4c6e8"), bytes.fromhex("d2b49678"), b"\x82\x02\x03\x04"):
            self.reject(fixture(0, bad))

    def test_terminal_fields_guards_and_ring_boundaries(self):
        original = fixture()
        for name, offsets in [
            ("terminal.bin", list(range(0, 192, 8)) + [192, 248, 288, 344, 384, 400, 508, 527, 528, 671])
        ] + [(name, [0, 16, 32, 4064, 4080]) for name in ("before-ring.bin", "after-ring.bin", "live-ring.bin")]:
            for offset in offsets:
                evidence = copy.deepcopy(original)
                raw = bytearray(evidence[3][name])
                raw[offset] ^= 128
                evidence[3][name] = bytes(raw)
                self.reject(evidence)

    def test_backing_handoff_extent_layout_and_mode(self):
        original = fixture()
        for name, offsets in (
            ("backing.bin", [0, 1024, 1032, 8216, 8240, 12288, 16624, 28947, 32767]),
            ("handoff.bin", [0, 8, 24, 32, 48, 52, 56, 72, 88, 120]),
        ):
            for offset in offsets:
                evidence = copy.deepcopy(original)
                raw = bytearray(evidence[3][name])
                raw[offset] ^= 128
                evidence[3][name] = bytes(raw)
                self.reject(evidence)
        evidence = copy.deepcopy(original)
        raw = bytearray(evidence[3]["handoff.bin"])
        struct.pack_into("<Q", raw, 112, 0)
        evidence[3]["handoff.bin"] = bytes(raw)
        self.reject(evidence)
        for name in original[3]:
            evidence = copy.deepcopy(original)
            evidence[3][name] = evidence[3][name][:-1]
            self.reject(evidence)
        evidence = copy.deepcopy(original)
        evidence[0] = "iommu-event-observe"
        self.reject(evidence)
        evidence = copy.deepcopy(original)
        evidence[1]["image"]["backing"]["objects"]["ring"]["arena_offset"] += 4096
        self.reject(evidence)
        evidence = copy.deepcopy(original)
        evidence[1]["image"]["payload_layout"]["payload_size"] += 1
        self.reject(evidence)

    def test_serial_order_duplicates_unknown_and_framing(self):
        original = fixture()
        for old, new in (
            (b"\r\n", b"\n"),
            (b"Firmware banner", b"AURORA_UNKNOWN"),
            (b"AURORA_UEFI_ENTRY\r\n", b"AURORA_UEFI_ENTRY\r\n" * 2),
            (b"handoff-complete=1", b"handoff-complete=0"),
            (b"value=42", b"value=41"),
            (b"producer_quiet=0000000000000001", b"producer_quiet=0000000000000000"),
        ):
            evidence = copy.deepcopy(original)
            evidence[2] = evidence[2].replace(old, new, 1)
            self.reject(evidence)
        for suffix in (b"extra\r\n", b"AURORA_EVENT_ADMISSION_OK: default-ivrs=1 handoff-complete=1\r\n"):
            evidence = copy.deepcopy(original)
            evidence[2] += suffix
            self.reject(evidence)
        evidence = copy.deepcopy(original)
        rows = evidence[2].split(b"\r\n")
        rows[35], rows[36] = rows[36], rows[35]
        evidence[2] = b"\r\n".join(rows)
        self.reject(evidence)

    def test_qmp_sequential_pause_capture_and_json(self):
        original = fixture()
        for old, new in (
            (b'"paused"', b'"running"'),
            (b'"running": false', b'"running": 0'),
            (b'"event": "STOP"', b'"event": "RESUME"'),
            (b'"id": 4', b'"id": 5'),
            (b'"id": 4', b'"id": 4, "id": 4'),
            (b'128 \\"handoff.bin', b'129 \\"handoff.bin'),
        ):
            evidence = copy.deepcopy(original)
            evidence[4] = evidence[4].replace(old, new, 1)
            self.assertNotEqual(evidence[4], original[4])
            self.reject(evidence)
        evidence = copy.deepcopy(original)
        rows = evidence[4].splitlines()
        rows[7], rows[8] = rows[8], rows[7]
        evidence[4] = b"\n".join(rows) + b"\n"
        self.reject(evidence)
        evidence = copy.deepcopy(original)
        evidence[4] = evidence[4].rsplit(b"\n", 2)[0] + b"\n"
        self.reject(evidence)


if __name__ == "__main__":
    unittest.main()
