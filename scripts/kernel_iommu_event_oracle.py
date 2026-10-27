#!/usr/bin/env python3
"""Pure byte oracle for four bounded, current-image Event emulator fixtures.

The caller reproduces image admission and supplies its current payload_layout.
No guest launch, production decoder, historical pin or review decision lives here.
Register captures are source-copied MMIO observations, not independent MMIO reads.
"""

import json
import math
import re
import struct
from kernel_layout import LAYOUT  # noqa: E402

MODES = ("iommu-event-denial", "iommu-event-success", "iommu-event-overflow", "iommu-event-command-error")
# transfers, completion, polls, acknowledgements, entered, output bytes, tail, status
CASES = (
    (5, 0, 3, 2, 1, 192, 32, 10),
    (2, 0, 1, 0, 1, 0, 0, 8),
    (257, 2, 0, 0, 0, 0, 4080, 11),
    (0, 4, 1, 0, 1, 57, 16, 10),
)
CAPTURES = (
    ("terminal.bin", "terminal", 672, 8),
    ("before-ring.bin", "before_ring", 4096, 4096),
    ("after-ring.bin", "after_ring", 4096, 4096),
    ("live-ring.bin", "ring", 4096, 4096),
    ("backing.bin", "backing", 32768, 4096),
)
ADMISSION = "AURORA_EVENT_ADMISSION_OK: default-ivrs=1 handoff-complete=1"
SERIAL_LIMIT, QMP_LIMIT = 1024 * 1024, 65536


def need(value, reason):
    if not value:
        raise ValueError(reason)


def json_object(raw):
    """Strict shared manifest/QMP parser, independent of behavior expectations."""

    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def finite(value):
        number = float(value)
        need(math.isfinite(number), "nonfinite JSON")
        return number

    result = json.loads(
        raw, object_pairs_hook=unique, parse_float=finite, parse_constant=lambda _: need(False, "nonfinite JSON")
    )
    need(type(result) is dict, "JSON object required")
    return result


def ownership(serial):
    """Extract exactly one complete ownership record, including live streams."""
    need(type(serial) is bytes and len(serial) <= SERIAL_LIMIT, "serial extent/type")
    rows = re.findall(rb"(?:^|\r\n)(AURORA_UEFI_OWNERSHIP_OK:[^\r\n]*)\r\n", serial)
    need(len(rows) == 1 and serial.count(b"AURORA_UEFI_OWNERSHIP_OK") == 1, "unique ownership record")
    match = re.fullmatch(
        rf"AURORA_UEFI_OWNERSHIP_OK: arena=([1-9][0-9]*) bytes={LAYOUT.arena_bytes} descriptors=([1-9][0-9]*)".encode(),
        rows[0],
    )
    need(match is not None, "ownership syntax")
    arena, descriptors = map(int, match.groups())
    need(
        arena % 4096 == 0
        and 0x100000 <= arena
        and arena + LAYOUT.arena_bytes <= 128 * 1024**2
        and 1 <= descriptors <= 512,
        "ownership bounds",
    )
    return arena, descriptors


def capture_layout(receipt):
    """Return exact capture order, derived only from reproduced image admission."""
    backing = receipt["image"]["backing"]
    objects = backing["objects"]
    need(set(objects) == {role for _, role, _, _ in CAPTURES}, "retained object inventory")
    begin, end = backing["payload_rw_begin"], backing["payload_memory_end"]
    need(
        type(begin) is int
        and type(end) is int
        and 0 < begin < end <= LAYOUT.kernel_payload_limit
        and begin % 4096 == end % 4096 == 0,
        "retained payload bounds",
    )
    result = [("handoff.bin", 0, 128)]
    for name, role, size, alignment in CAPTURES:
        row = objects[role]
        offset = row["offset"]
        need(
            type(offset) is int
            and row["bytes"] == size
            and row["alignment"] == alignment
            and offset % alignment == 0
            and begin <= offset
            and offset + size <= end
            and row["arena_offset"] == LAYOUT.kernel_payload_offset + offset,
            "retained allocation: " + role,
        )
        start = row["arena_offset"]
        need(all(start + size <= old or old + length <= start for _, old, length in result), "overlapping captures")
        result.append((name, start, size))
    return result


def boot_prefix(lines, arena, descriptors):
    start = [i for i, line in enumerate(lines) if line == "AURORA_UEFI_ENTRY"]
    need(len(start) == 1 and all("AURORA_" not in line for line in lines[: start[0]]), "unique boot prefix")
    rows = lines[start[0] :]
    patterns = [
        r"AURORA_UEFI_ENTRY",
        r"AURORA_BAR_DESCRIPTOR: kind=bar bytes=48 data=[0-9a-f]{96}",
        r"AURORA_BAR_DESCRIPTOR: kind=root bytes=140 data=[0-9a-f]{280}",
        r"AURORA_UEFI_EXIT_OK: attempts=1",
        r"AURORA_UEFI_PAYLOAD_ENTRY",
        f"AURORA_UEFI_OWNERSHIP_OK: arena={arena} bytes={LAYOUT.arena_bytes} descriptors={descriptors}",
        rf"AURORA_UEFI_PROTECTION_OK: root={arena + 0x11000} stack=([0-9]+)",
        r"AURORA_UEFI_LANGUAGE_OK: value=42",
        r"AURORA_ACPI_CPU: id=0 uid=0 enabled=1 capable=0 x2=0",
        r"AURORA_ACPI_TOPOLOGY: records=1 enabled=1 capable=0 lapic=4276092928",
        r"AURORA_IVRS_RAW: bytes=176 data=[0-9a-f]{352}",
        r"AURORA_IVRS_TABLE: units=1 records=2 requesters=6 base=4275568640 bytes=16384",
        r"AURORA_ACPI_WINDOW_CLOSED: copies=15",
        r"AURORA_PCI_APERTURE: base=3758096384 bytes=268435456 segment=0 first=0 last=255",
    ]
    for device, function, vendor, product, cls, sub, interface in (
        (0, 0, 32902, 10688, 6, 0, 0),
        (1, 0, 4130, 5145, 8, 6, 0),
        (4, 0, 4660, 4584, 0, 255, 0),
        (31, 0, 32902, 10520, 6, 1, 0),
        (31, 2, 32902, 10530, 1, 6, 1),
        (31, 3, 32902, 10544, 12, 5, 0),
    ):
        patterns.append(
            f"AURORA_PCI_FUNCTION: segment=0 bus=0 device={device} function={function} vendor={vendor} "
            f"product={product} class={cls} subclass={sub} interface={interface} "
            "header=0 command=7 secondary=0 subordinate=0"
        )
    patterns += [r"AURORA_PCI_INVENTORY: functions=6 buses=1", r"AURORA_PCI_WINDOW_CLOSED: reads=39"]
    need(len(rows) == len(patterns), "boot prefix inventory/order")
    for row, pattern in zip(rows, patterns):
        need(re.fullmatch(pattern, row) is not None, "boot prefix record: " + row[:90])
    stack = int(re.fullmatch(patterns[6], rows[6])[1])
    need(
        stack % 8 == 0 and arena + LAYOUT.kernel_stack_bottom <= stack < arena + LAYOUT.kernel_stack_top,
        "boot protected stack",
    )


def validate_handoff(header, receipt, arena, descriptors):
    u = lambda at, width=8: int.from_bytes(header[at : at + width], "little")
    need(
        u(0) == 0x41524F5255454649
        and u(8, 4) == 4
        and u(12, 4) == 128
        and u(16) == LAYOUT.arena_bytes
        and u(24) == arena,
        "handoff identity",
    )
    need(
        40 <= u(40) <= 256
        and u(40) % 8 == 0
        and 0 < u(32) == descriptors * u(40) <= 65536
        and u(48, 4) == 1
        and u(52, 4) == 1,
        "handoff map shape/boot attempts",
    )
    layout = receipt["image"]["payload_layout"]
    keys = ("payload_size", "payload_text_end", "payload_read_end", "payload_memory_end")
    need(set(layout) == set(keys) and all(type(layout[k]) is int for k in keys), "current payload layout")
    size, text, read, memory = (layout[k] for k in keys)
    backing = receipt["image"]["backing"]
    need(
        0 < text <= read <= memory <= LAYOUT.kernel_payload_limit
        and text <= size <= read
        and text % 4096 == read % 4096 == memory % 4096 == 0
        and read == backing["payload_rw_begin"]
        and memory == backing["payload_memory_end"],
        "current payload bounds",
    )
    need(tuple(u(at) for at in (56, 64, 72, 80)) == (size, text, read, memory), "handoff current image layout")
    need(
        u(88) == arena + 0x11000
        and 0 < u(96) <= 16
        and u(104) == arena + LAYOUT.kernel_payload_offset
        and 0 < u(112) < 128 * 1024**2
        and u(120) == arena + 0x81000,
        "handoff table/payload/firmware binding",
    )


def validate_qmp(raw, layout, arena):
    need(type(raw) is bytes and 0 < len(raw) <= QMP_LIMIT and raw.endswith(b"\n"), "QMP transcript extent/framing")
    commands = [
        {"execute": "qmp_capabilities", "id": 1},
        {"execute": "stop", "id": 2},
        {"execute": "query-status", "id": 3},
    ]
    commands += [
        {
            "execute": "human-monitor-command",
            "id": i,
            "arguments": {"command-line": f'pmemsave {arena + offset} {size} "{name}"'},
        }
        for i, (name, offset, size) in enumerate(layout, 4)
    ]
    commands.append({"execute": "quit", "id": 10})
    returns = [{}, {}, {"status": "paused", "running": False}] + [""] * 6 + [{}]
    sent, answered, pending, greeted, paused, events = 0, 0, None, False, False, []

    for line in raw.decode("ascii").splitlines():
        send = line.startswith("SEND ")
        row = json_object(line[5:] if send else line)
        need(type(row) is dict and "error" not in row, "invalid/error QMP message")
        if send:
            need(
                greeted
                and pending is None
                and sent < len(commands)
                and row == commands[sent]
                and type(row.get("id")) is int,
                "QMP exact sequential command order",
            )
            need(row["execute"] != "human-monitor-command" or paused, "capture before paused proof")
            pending = row["id"]
            sent += 1
        elif "QMP" in row:
            need(not greeted and sent == 0 and set(row) == {"QMP"} and type(row["QMP"]) is dict, "QMP greeting order")
            greeted = True
        elif "event" in row:
            event = row["event"]
            need(
                (event == "STOP" and sent == 2 and not events)
                or (event == "SHUTDOWN" and sent == 10 and events == ["STOP"]),
                "QMP event order",
            )
            need(set(row) <= {"event", "timestamp", "data"}, "unexpected QMP event fields")
            events.append(event)
        else:
            need(
                pending is not None
                and set(row) == {"id", "return"}
                and type(row["id"]) is int
                and row["id"] == pending == answered + 1
                and row["return"] == returns[answered],
                "QMP response/order",
            )
            if pending == 3:
                need(events == ["STOP"] and row["return"]["running"] is False, "QMP paused proof")
                paused = True
            answered += 1
            pending = None
    need(sent == answered == 10 and events == ["STOP", "SHUTDOWN"] and paused, "incomplete QMP capture/quit")


def validate(mode, checked_receipt, serial, captures, qmp_log):
    """Validate full ordered serial, six complete RAM captures and paused QMP."""
    need(mode in MODES and checked_receipt["mode"] == mode and checked_receipt["image"]["mode"] == mode, "Event mode")
    arena, descriptors = ownership(serial)
    need(
        serial.endswith(b"\r\n")
        and b"\r" not in serial.replace(b"\r\n", b"")
        and b"\n" not in serial.replace(b"\r\n", b""),
        "strict serial CRLF framing",
    )
    need(not any(token in serial for token in (b"FAIL", b"EXCEPTION", b"REJECTED")), "guest failure marker")
    lines = serial.decode("ascii").split("\r\n")
    need(lines.count(ADMISSION) == 1 and serial.count(b"AURORA_EVENT_ADMISSION") == 1, "unique Event admission")
    start = lines.index(ADMISSION)
    boot_prefix(lines[:start], arena, descriptors)
    layout = capture_layout(checked_receipt)
    need(set(captures) == {name for name, _, _ in layout}, "capture inventory")
    for name, _, size in layout:
        need(type(captures[name]) is bytes and len(captures[name]) == size, "capture extent: " + name)
    physical = {name: arena + offset for name, offset, _ in layout}
    backing, ring = physical["backing.bin"], physical["live-ring.bin"]
    command = backing + 12288
    selector = MODES.index(mode)
    transfers, completion, polls, acknowledgements, entered, output_bytes, tail, status = CASES[selector]
    slots = []
    for i in range(256):
        if selector == 0 and i < 2:
            words = ((0x2050123400000020, 0x3100), (0x2070123400000020, 0x4100))[i]
        elif selector == 2 and i < 255:
            words = (0x2070123400000020, 0x4100)
        elif selector == 3 and i == 0:
            words = (0x5000000000000000, command)
        else:
            words = (0xF5A55A5ADEAD0000 | i, 0xBAD0000000000000 | i * 16)
        slots.append(struct.pack("<QQ", *words))
    expected_ring = b"".join(slots)
    for name in ("before-ring.bin", "after-ring.bin", "live-ring.bin"):
        need(captures[name] == expected_ring, "all 256 ring slots: " + name)
    terminal = captures["terminal.bin"]
    header = list(struct.unpack("<24Q", terminal[:192]))
    readiness = header[13]
    need(max(1, transfers) <= readiness <= max(1, transfers) * (1 << 24), "readiness bound")
    need(
        header
        == [
            0x41554556494E5431,
            1,
            selector,
            5,
            0,
            completion,
            backing,
            ring,
            physical["before-ring.bin"],
            physical["after-ring.bin"],
            4096,
            transfers,
            transfers,
            readiness,
            polls,
            acknowledgements,
            output_bytes,
            1,
            1,
            entered,
            0,
            1,
            1,
            3,
        ],
        "terminal scalar fields",
    )
    before = [
        backing | 1,
        command | (8 << 56) if selector == 3 else 0,
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
    after = before.copy()
    if selector == 0:
        after[7] = 32
    need(
        terminal[192:288] == struct.pack("<12Q", *before) and terminal[288:384] == struct.pack("<12Q", *after),
        "source-copied register arrays",
    )
    sink = terminal[508:512] if selector == 0 else bytes.fromhex("6f4d2b19" if selector == 1 else "d2b49678")
    values = [bytes.fromhex(x) for x in ("82a4c6e8", "416385a7", "6f4d2b19")]
    if selector == 0:
        need(
            all(x != y and x != z for x, y, z in zip(sink, values[0], bytes.fromhex("d2b49678"))),
            "denial sink discrimination",
        )
    data = b"".join(bytes(range(0xA0, 0xB0)) + v + bytes(range(0x50, 0x60)) for v in values + [sink])
    need(terminal[384:528] == data == terminal[528:672], "all 144 guarded data bytes")
    full = bytearray(32768)
    struct.pack_into("<QQ", full, 0x20 * 32, (backing + 8192) | 3 | (1 << 9) | (3 << 61), 0x1234)
    for index, offset, perm in ((3, 16384, 2), (4, 20480, 1), (5, 24576, 3), (6, 28672, 3)):
        struct.pack_into("<Q", full, 8192 + index * 8, (backing + offset) | 1 | (perm << 61))
    for i, offset in enumerate((16384, 20480, 24576, 28672)):
        full[offset + 0xF0 : offset + 0x114] = data[i * 36 : (i + 1) * 36]
    need(captures["backing.bin"] == full, "all 32768 backing bytes")
    expected = [
        ADMISSION,
        "AURORA_IOMMU_EVENT_BACKING: terminal=%016x data=%016x ring=%016x pre=%016x post=%016x"
        % (physical["terminal.bin"], backing, ring, physical["before-ring.bin"], physical["after-ring.bin"]),
    ]
    aurora = (
        [
            "IOMMU F raw=2050123400000020/0000000000003100 rid=0020 dom=1234 dva=0000000000003100 status=0a",
            "IOMMU F raw=2070123400000020/0000000000004100 rid=0020 dom=1234 dva=0000000000004100 status=0a",
        ]
        if selector == 0
        else ["IOMMU C raw=5000000000000000/%016x status=0a" % command]
        if selector == 3
        else []
    )
    need(sum(len(x) + 2 for x in aurora) == output_bytes, "Aurora output extent")
    for phase, regs in (("pre", before), ("post", after)):
        if phase == "post":
            expected += aurora
        expected += [
            "AURORA_IOMMU_EVENT_REGISTERS: phase=%s producer_quiet=0000000000000001 words=%s"
            % (phase, "".join("%016x/" % v for v in regs)),
            "AURORA_IOMMU_EVENT_DATA: phase=%s guarded=%s" % (phase, data.hex()),
        ]
        expected += [
            "AURORA_IOMMU_EVENT_RAW: phase=%s offset=%016x bytes=%s" % (phase, i, expected_ring[i : i + 16].hex())
            for i in range(0, 4096, 16)
        ]
    expected += [
        "AURORA_IOMMU_EVENT_TERMINAL: case=%016x completion=%016x checks=0000000000000003 submitted=%016x "
        "completed=%016x polls=%016x acknowledged=%016x readiness=%016x entered=%016x"
        % (selector, completion, transfers, transfers, polls, acknowledgements, readiness, entered),
        "",
    ]
    need(lines[start:] == expected, "complete ordered Event serial protocol")
    validate_handoff(captures["handoff.bin"], checked_receipt, arena, descriptors)
    validate_qmp(qmp_log, layout, arena)
    return dict(
        mode=mode,
        selector=selector,
        completion=completion,
        dma_completed=transfers,
        readiness_reads=readiness,
        polls=polls,
        acknowledgements=acknowledgements,
        event_protocol_lines=len(expected) - 1,
        terminal_bytes=672,
        guarded_data_bytes=144,
        ring_slots_per_capture=256,
        ring_captures=3,
        backing_bytes=32768,
        handoff_bytes=128,
        paused_before_captures=True,
    )
