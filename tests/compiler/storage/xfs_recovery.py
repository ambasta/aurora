#!/usr/bin/env python3
"""Full-ring historical witness plus synthetic short-ring owning-preflight cases."""

import hashlib
import json
import lzma
import struct

import harness
from xfs_inputs import change, hex_fixture, set_fields, shortform

STATUSES = (
    "superblock topology completion_header completion_body root home agf agi inobt "
    "record_header record_body ready invalid_request protocol_error io_error unsupported "
    "invalid_metadata invalid_log clean_marker already_clean"
).split()
LOG = 524328


def exchange_cases(program, mount, directory):
    """A genuine Linux root transaction and focused, explicitly synthetic variants."""
    fixture_dir = harness.ROOT / "fixtures/xfs-root-exchange"
    hashes = json.loads((fixture_dir / "hashes.json").read_text())
    archive = fixture_dir / "dirty.img.xz"
    harness.require(hashlib.sha256(archive.read_bytes()).hexdigest() == hashes[archive.name], "exchange archive hash")
    image = directory / "exchange.img"
    with lzma.open(archive, "rb") as source, image.open("xb") as output:
        digest, length = hashlib.sha256(), 0
        while chunk := source.read(65536):
            digest.update(chunk)
            length += len(chunk)
            if any(chunk):
                output.write(chunk)
            else:
                output.seek(len(chunk), 1)
        output.truncate(length)
    harness.require(length == 536870912 and digest.hexdigest() == hashes["dirty.img"], "exchange image hash")
    old_root = hex_fixture("xfs-root-exchange", "root-before.hex", hashes["root-before.hex"])
    new_root = hex_fixture("xfs-root-exchange", "root-after.hex", hashes["root-after.hex"])

    def read(lba):
        with image.open("rb") as stream:
            stream.seek(lba * 512)
            return stream.read(512)

    def write(changes):
        with image.open("r+b") as stream:
            for lba, sector in changes.items():
                stream.seek(lba * 512)
                stream.write(sector)

    def run(label, expected=None, clean=False):
        result = harness.command([program, image, "0"], timeout=30)
        harness.require(result.returncode == 0 and not result.stderr, label + ": driver failed")
        state, count, reads, reserve = struct.unpack("<4Q", result.stdout[:32])
        harness.require(len(result.stdout) == 32 + 520 * (count + 2) and reads <= 134000, label + ": output bounds")
        if expected is None:
            harness.require(
                state not in (11, 19) and count == reserve == 0 and result.stdout[32:] == bytes(1040),
                label + ": refusal exposes output",
            )
            return "refused with zero output", []
        if clean:
            harness.require(
                state == 19 and count == 0 and reserve == 32769 and result.stdout[32:] == bytes(1040),
                label + ": clean reentry exposes output",
            )
            return "already_clean writes=0 reserve=32769", []
        harness.require(state == 11 and count == 1 and reserve == 32789, label + ": expected one root home")
        outputs = []
        for index in range(3):
            at = 32 + index * 520
            outputs.append((struct.unpack("<Q", result.stdout[at : at + 8])[0], result.stdout[at + 8 : at + 520]))
        harness.require(outputs[0] == (96, expected), label + ": root differs from reference bytes")
        harness.require([lba for lba, _ in outputs[1:]] == [LOG + 16, LOG + 15], label + ": completion order")
        return "ready writes=1 reserve=32789; exact expected root", outputs

    harness.require(read(96) == old_root, "exchange original root")
    # Full-geometry root replay is qualified by the actual forward/reverse
    # device guests. Keep the original CORE full-ring witness in this component,
    # and use the explicitly synthetic ring for focused root admission cases.
    write({0: change(read(0), logblocks=8)})
    with image.open("rb") as stream:
        before = hashlib.file_digest(stream, "sha256").hexdigest()
    label = "exchange synthetic short ring"
    outcome, outputs = run(label, new_root)
    with image.open("rb") as stream:
        harness.require(hashlib.file_digest(stream, "sha256").hexdigest() == before, "exchange preflight wrote")
    yield label, outcome
    original_header, original_body = read(LOG + 13), read(LOG + 14)

    def record(changes=(), header_changes=()):
        header, body = bytearray(original_header), bytearray(original_body)
        for at, value in changes:
            body[at : at + len(value)] = value
        for at, value in header_changes:
            header[at : at + len(value)] = value
        header[32:36] = bytes(4)
        header[32:36] = harness.crc32c(header[:328] + body).to_bytes(4, "little")
        return {LOG + 13: bytes(header), LOG + 14: bytes(body)}

    # This synthetic no-op keeps the logged core from Linux, restores the two
    # original inode numbers and recomputes only the standard inode checksum.
    # No replay/core conversion is reimplemented as a Python oracle.
    unchanged_mapping = set_fields(new_root, (191, 4, 99), (206, 4, 100), crc=100)
    rows = [
        ("exchange no-op name permutation", record(((308, old_root[176:212]),)), unchanged_mapping),
        ("exchange already applied root", {96: new_root}, new_root),
        ("exchange torn root", {96: set_fields(old_root, (100, 1, old_root[100] ^ 1), crc=None)}, None),
        ("exchange future root LSN", {96: set_fields(old_root, (112, 8, (1 << 32) | 14), crc=100)}, None),
        ("exchange torn referenced inode", {99: set_fields(read(99), (100, 1, read(99)[100] ^ 1), crc=None)}, None),
    ]
    for label, at, value in (
        ("unknown item flags", 56, (7).to_bytes(4, "little")),
        ("wrong transaction region count", 36, (2).to_bytes(4, "little")),
        ("wrong inode region count", 54, (2).to_bytes(2, "little")),
        ("wrong local size", 62, (35).to_bytes(2, "little")),
        ("wrong local region length", 300, (35).to_bytes(4, "big")),
        ("foreign logged inode", 68, (99).to_bytes(8, "little")),
        ("wrong target sector", 92, (97).to_bytes(8, "little")),
        ("changed inode size", 176, (35).to_bytes(8, "little")),
        ("changed inode UID", 128, (1).to_bytes(4, "little")),
        ("changed inode mode", 122, (0x81ED).to_bytes(2, "little")),
        ("changed inode link count", 136, (3).to_bytes(4, "little")),
        ("changed directory parent", 310, (97).to_bytes(4, "big")),
        ("changed entry count", 308, b"\x03"),
        ("changed inode width", 309, b"\x01"),
        ("changed name", 317, b"j"),
        ("changed saved offset", 315, (104).to_bytes(2, "big")),
        ("changed entry type", 322, b"\x02"),
        ("duplicate inode", 323, (99).to_bytes(4, "big")),
        ("foreign inode", 323, (101).to_bytes(4, "big")),
        ("root self reference", 323, (96).to_bytes(4, "big")),
        ("nonzero local padding", 342, b"\x01"),
        ("continued commit", 353, b"\x04"),
    ):
        rows.append(("exchange " + label, record(((at, value),)), None))
    rows.append(("exchange wrong operation count", record(header_changes=((40, (5).to_bytes(4, "big")),)), None))
    torn_body = bytearray(original_body)
    torn_body[317] ^= 1
    rows.append(("exchange record CRC failure", {LOG + 14: bytes(torn_body)}, None))
    # A second genuine CORE-shaped record is not part of the admitted root-only
    # transaction. Rebase its header; the old root transaction itself is intact.
    core_hashes = json.loads((harness.ROOT / "fixtures/xfs-core-redo/hashes.json").read_text())
    core_header = bytearray(
        hex_fixture("xfs-core-redo", "log-record-5-header.hex", core_hashes["log-record-5-header.hex"])
    )
    core_body = hex_fixture("xfs-core-redo", "log-record-5-stamped.hex", core_hashes["log-record-5-stamped.hex"])
    core_header[16:24] = ((1 << 32) | 15).to_bytes(8, "big")
    core_header[24:32] = ((1 << 32) | 13).to_bytes(8, "big")
    core_header[36:40] = (13).to_bytes(4, "big")
    core_header[32:36] = bytes(4)
    core_header[32:36] = harness.crc32c(core_header[:328] + core_body).to_bytes(4, "little")
    rows.append(("exchange mixed later CORE transaction", {LOG + 15: bytes(core_header), LOG + 16: core_body}, None))
    for label, changed, expected in rows:
        previous = {lba: read(lba) for lba in changed}
        write(changed)
        try:
            outcome, _ = run(label, expected)
            yield label, outcome
        finally:
            write(previous)

    # Use only the outputs already compared with the independent Linux home
    # golden; completion bytes are validated by the separate readonly consumer.
    write(dict(outputs[:1]))
    label = "exchange root-write interruption reentry"
    outcome, resumed = run(label, new_root)
    harness.require(resumed == outputs, "exchange home reentry changed plan")
    yield label, outcome
    write(dict(outputs[1:2]))
    refused = harness.command([mount, image, "hello", "--linux-6.12-x86_64-clean"], timeout=30)
    harness.require(refused.returncode != 0 and not refused.stdout, "exchange orphan admitted readonly")
    yield "exchange orphan readonly refusal", "refused without file bytes"
    label = "exchange orphan-body reentry"
    outcome, resumed = run(label, new_root)
    harness.require(resumed == outputs, "exchange orphan reentry changed plan")
    yield label, outcome
    write(dict(outputs[2:]))
    for name, source_name in (("hello", "pattern"), ("pattern", "hello")):
        mounted = harness.command([mount, image, name, "--linux-6.12-x86_64-clean"], timeout=30)
        filename = source_name + "-data.hex"
        expected = hex_fixture("xfs-core-redo", filename, core_hashes[filename])
        harness.require(
            mounted.returncode == 0 and not mounted.stderr and mounted.stdout == expected, "exchange mounted bytes"
        )
        yield "exchange completed readonly " + name, f"exact {len(expected)} bytes"
    label = "exchange completed-marker reentry"
    outcome, _ = run(label, b"", clean=True)
    yield label, outcome


def staged_cases(program, mount, directory):
    """Linux size-only/mixed records, with focused synthetic short geometry."""
    fixture_dir = harness.ROOT / "fixtures/xfs-staged-replace"
    hashes = json.loads((fixture_dir / "hashes.json").read_text())

    def fixture(name):
        return hex_fixture("xfs-staged-replace", name + ".hex", hashes[name + ".hex"])

    def expand(name):
        archive = fixture_dir / (name + ".xz")
        harness.require(hashlib.sha256(archive.read_bytes()).hexdigest() == hashes[name + ".xz"], "stage archive hash")
        image = directory / ("stage-" + name)
        with lzma.open(archive, "rb") as source, image.open("xb") as output:
            digest, length = hashlib.sha256(), 0
            while chunk := source.read(65536):
                digest.update(chunk)
                length += len(chunk)
                if any(chunk):
                    output.write(chunk)
                else:
                    output.seek(len(chunk), 1)
            output.truncate(length)
        harness.require(length == 536870912 and digest.hexdigest() == hashes[name], "stage image hash")
        return image

    image = expand("dirty.img")

    def read(lba):
        with image.open("rb") as stream:
            stream.seek(lba * 512)
            return stream.read(512)

    def write(changes):
        with image.open("r+b") as stream:
            for lba, sector in changes.items():
                stream.seek(lba * 512)
                stream.write(sector)

    def run(label, expected=None, head=26, clean=False):
        result = harness.command([program, image, "0"], timeout=30)
        harness.require(result.returncode == 0 and not result.stderr, label + ": driver failure")
        state, count, reads, reserve = struct.unpack("<4Q", result.stdout[:32])
        harness.require(len(result.stdout) == 32 + 520 * (count + 2) and reads <= 134000, label + ": output bound")
        if expected is None:
            harness.require(
                state not in (11, 19) and count == reserve == 0 and result.stdout[32:] == bytes(1040),
                label + ": refusal exposes output",
            )
            return "refused with zero output", []
        if clean:
            harness.require(
                state == 19 and count == 0 and reserve == 32769 and result.stdout[32:] == bytes(1040),
                label + ": clean output",
            )
            return "already_clean writes=0 reserve=32769", []
        harness.require(state == 11 and count == len(expected) and reserve == 32789, label + ": planned homes")
        outputs = []
        for index in range(count + 2):
            at = 32 + 520 * index
            outputs.append((struct.unpack("<Q", result.stdout[at : at + 8])[0], result.stdout[at + 8 : at + 520]))
        harness.require(outputs[:count] == expected, label + ": Linux home golden or home order")
        harness.require(
            [lba for lba, _ in outputs[count:]] == [LOG + head + 1, LOG + head], label + ": completion order"
        )
        return f"ready writes={count}; exact Linux homes", outputs

    # Archive authenticity is checked above; full geometry is exercised by the
    # real copied-image device gate, not repeated for each mutation here.
    write({0: change(read(0), logblocks=8)})
    with image.open("rb") as stream:
        before = hashlib.file_digest(stream, "sha256").digest()
    inode, root = fixture("inode-after"), fixture("root-after")
    expected = [(100, inode), (96, root)]
    outcome, outputs = run("staged CORE then root permutation", expected)
    with image.open("rb") as stream:
        harness.require(hashlib.file_digest(stream, "sha256").digest() == before, "staged preflight mutated input")
    yield "staged CORE then root permutation", outcome
    headers = {at: read(LOG + at) for at in (22, 24)}
    bodies = {at: read(LOG + at + 1) for at in (22, 24)}

    def record(at, changes):
        header, body = bytearray(headers[at]), bytearray(bodies[at])
        for position, value in changes:
            body[position : position + len(value)] = value
        header[32:36] = bytes(4)
        header[32:36] = harness.crc32c(header[:328] + body).to_bytes(4, "little")
        return {LOG + at: bytes(header), LOG + at + 1: bytes(body)}

    rows = [
        ("staged equal home reapplies", {100: inode}, expected, 26),
        ("staged equal root reapplies", {96: root}, expected, 26),
        ("staged both homes reapplied", {100: inode, 96: root}, expected, 26),
        (
            "staged newer intact home skipped",
            {100: set_fields(inode, (112, 8, (1 << 32) | 23), crc=100)},
            [(96, root)],
            26,
        ),
        (
            "staged synthetic prefix without root",
            {LOG + 24: fixture("stale-24"), LOG + 25: fixture("stale-25")},
            [(100, inode)],
            24,
        ),
        ("staged torn target home", {100: set_fields(read(100), (100, 1, read(100)[100] ^ 1), crc=None)}, None, 26),
        ("staged root changes UID", record(24, ((128, (1).to_bytes(4, "little")),)), None, 26),
        ("staged root duplicates inode", record(24, ((338, (100).to_bytes(4, "big")),)), None, 26),
        ("staged first item foreign inode", record(22, ((68, (101).to_bytes(8, "little")),)), None, 26),
        ("staged first item allocation change", record(22, ((184, (2).to_bytes(8, "little")),)), None, 26),
    ]
    for size in (0, 4097, (1 << 63), (1 << 64) - 1):
        rows.append((f"staged rejects size {size}", record(22, ((176, size.to_bytes(8, "little")),)), None, 26))
    for label, changed, wanted, head in rows:
        previous = {lba: read(lba) for lba in changed}
        write(changed)
        try:
            outcome, _ = run(label, wanted, head)
            yield label, outcome
        finally:
            write(previous)
    # Partial publication cannot discard either staged or root replay.
    write(dict(outputs[:1]))
    outcome, resumed = run("staged first-home interruption", expected)
    harness.require(resumed == outputs, "staged first-home reentry changed plan")
    yield "staged first-home interruption", outcome
    write(dict(outputs[1:3]))
    outcome, resumed = run("staged orphan completion reentry", expected)
    harness.require(resumed == outputs, "staged orphan reentry changed plan")
    yield "staged orphan completion reentry", outcome
    write(dict(outputs[3:]))
    old_hashes = json.loads((harness.ROOT / "fixtures/xfs-core-redo/hashes.json").read_text())
    original = hex_fixture("xfs-core-redo", "hello-data.hex", old_hashes["hello-data.hex"])
    for name, data in (("hello", bytes((i * 37 + 91) % 251 for i in range(777))), ("pattern", original)):
        result = harness.command([mount, image, name, "--linux-6.12-x86_64-clean"], timeout=30)
        harness.require(result.returncode == 0 and not result.stderr and result.stdout == data, "staged mounted bytes")
        yield "staged completed readonly " + name, f"exact {len(data)} bytes"
    outcome, _ = run("staged completed-marker reentry", [], clean=True)
    yield "staged completed-marker reentry", outcome

    # A separately captured genuine Linux stage-only crash is not inferred from
    # the combined transaction. It has inode99 CORE only at LSN(1,19).
    image = expand("stage-only.img")
    write({0: change(read(0), logblocks=8)})
    outcome, _ = run("genuine stage-only CORE size change", [(99, fixture("stage-only-inode-after"))], 21)
    yield "genuine stage-only CORE size change", outcome

    result = harness.command([program, image, "A"], timeout=30)
    harness.require(result.returncode == 0 and not result.stderr, "dirty clean-snapshot driver")
    count = struct.unpack("<Q", result.stdout[8:16])[0]
    snapshots = result.stdout[32 + (count + 2) * 520 :]
    harness.require(snapshots == bytes(24 + 5 * 512), "dirty preflight exposes clean snapshot")
    yield "dirty plan clean-snapshot denial", "zero metadata and sectors"
    image = expand("clean.img")
    write({0: change(read(0), logblocks=8)})
    result = harness.command([program, image, "A"], timeout=30)
    harness.require(result.returncode == 0 and not result.stderr, "clean snapshot driver")
    harness.require(struct.unpack("<Q", result.stdout[:8])[0] == 19, "clean snapshot state")
    snapshots = result.stdout[1072:]
    expected_snapshot = struct.pack("<3Q", (1 << 32) | 22, (1 << 32) | 20, 1048576)
    expected_snapshot += b"".join(read(lba) for lba in (0, 96, 99, 100)) + bytes(512)
    harness.require(snapshots == expected_snapshot, "clean snapshot copies or membership")
    yield "clean plan copied snapshot", "exact metadata and admitted sectors; foreign inode zero"


def append_cases(program, mount, directory):
    """Actual Aurora completed-command cuts; Linux independently supplies homes.

    Only the ring geometry below is synthetic. The pending body has no committed
    header and must never be replayed, even though its canonical bytes are checked.
    """
    fixture_dir = harness.ROOT / "fixtures/xfs-staged-replace"
    hashes = json.loads((fixture_dir / "append-hashes.json").read_text())
    archive = fixture_dir / "append-clean.img.xz"
    harness.require(hashlib.sha256(archive.read_bytes()).hexdigest() == hashes[archive.name], "append archive hash")
    image = directory / "append.img"
    digest, length = hashlib.sha256(), 0
    with lzma.open(archive, "rb") as source, image.open("xb") as output:
        while chunk := source.read(65536):
            digest.update(chunk)
            length += len(chunk)
            if any(chunk):
                output.write(chunk)
            else:
                output.seek(len(chunk), 1)
        output.truncate(length)
    harness.require(length == 536870912 and digest.hexdigest() == hashes["append-clean.img"], "append image hash")

    def fixture(name):
        return hex_fixture("xfs-staged-replace", name, hashes[name])

    authored = fixture("append-writes.hex")
    harness.require(len(authored) == 16 * 528, "append command stream")
    commands = []
    for at in range(0, len(authored), 528):
        lba, flush = struct.unpack("<QQ", authored[at : at + 16])
        commands.append((lba, authored[at + 16 : at + 528]))
        harness.require(flush == int(at // 528 + 1 in (10, 12, 14, 15, 16)), "append flush boundary")
    stage_home = fixture("append-stage-linux.hex")

    def read(lba):
        with image.open("rb") as stream:
            stream.seek(lba * 512)
            return stream.read(512)

    def write(changes):
        with image.open("r+b") as stream:
            for lba, sector in changes.items():
                harness.require(len(sector) == 512, "append sector size")
                stream.seek(lba * 512)
                stream.write(sector)

    original = {
        lba: read(lba) for lba in {0, 1, 72, 96, 99, 100, *range(LOG + 30, LOG + 42), *(x[0] for x in commands)}
    }

    def run(label, expected=None, head=33, clean=False):
        result = harness.command([program, image, "0"], timeout=30)
        harness.require(result.returncode == 0 and not result.stderr, label + ": driver failure")
        state, count, reads, reserve = struct.unpack("<4Q", result.stdout[:32])
        harness.require(len(result.stdout) == 32 + 520 * (count + 2) and reads <= 134000, label + ": output bounds")
        if expected is None:
            harness.require(
                state not in (11, 19) and count == reserve == 0 and result.stdout[32:] == bytes(1040),
                label + ": refusal exposes output",
            )
            return "refused with zero output", []
        if clean:
            harness.require(
                state == 19 and count == 0 and reserve == 32769 and result.stdout[32:] == bytes(1040),
                label + ": clean reentry",
            )
            return "already_clean writes=0 reserve=32769", []
        harness.require(
            state == 11 and count == len(expected) and reserve == 32789,
            label + f": planned homes (state={state}, count={count})",
        )
        outputs = []
        for index in range(count + 2):
            at = 32 + 520 * index
            outputs.append((struct.unpack("<Q", result.stdout[at : at + 8])[0], result.stdout[at + 8 : at + 520]))
        harness.require(outputs[:count] == expected, label + ": Linux homes")
        harness.require(
            [lba for lba, _ in outputs[count:]] == [LOG + head + 1, LOG + head], label + ": completion order"
        )
        return f"ready writes={count}; pending body not replayed", outputs

    def altered(sector, at, value):
        result = bytearray(sector)
        result[at : at + len(value)] = value
        return bytes(result)

    def inode_crc(sector):
        result = bytearray(sector)
        result[100:104] = bytes(4)
        result[100:104] = harness.crc32c(result).to_bytes(4, "little")
        return bytes(result)

    for kind, prefix, head, expected in (("stage", 9, 33, []), ("root", 11, 35, [(100, stage_home)])):
        write(original)
        write(dict(commands[:prefix]))
        # The complete prefix must match the independently mounted raw image.
        cut_hash = {
            "stage": "88ea52aaf29ecf5be853ed3d831d9ef47652433d87ea83ee4a70d53e5df0d322",
            "root": "14cc9b9a6ec34cb233de11bc9bf536c27a025621cc3b7742605564176824fdbf",
        }[kind]
        with image.open("rb") as stream:
            harness.require(
                hashlib.file_digest(stream, "sha256").hexdigest() == cut_hash, "authored " + kind + " cut hash"
            )
        write({0: change(original[0], logblocks=8)})
        baseline = {lba: read(lba) for lba in original}
        label = "authored " + kind + " body-only short ring"
        outcome, outputs = run(label, expected, head)
        yield label, outcome
        harness.require(all(read(lba) == value for lba, value in baseline.items()), "append preflight wrote")
        result = harness.command([mount, image, "hello", "--linux-6.12-x86_64-clean"], timeout=30)
        harness.require(result.returncode != 0, "readonly scanner admitted incomplete body")
        yield "readonly rejects " + kind + " body-only", "refused without recovery overlay"
        completion_lba, completion_body = outputs[-2]
        write({completion_lba: altered(completion_body, 511, b"\x01")})
        outcome, _ = run(kind + " append malformed completion body")
        yield kind + " append malformed completion body", outcome
        write(dict(outputs[-2:-1]))
        outcome, resumed = run(kind + " append completion-body interruption", expected, head)
        harness.require(resumed == outputs, "completion-body restart changed plan")
        yield kind + " append completion-body interruption", outcome
        write(baseline)
        if kind == "root":
            write({100: stage_home})
            # Equal LSN is deliberately replayed: another checkpoint may share
            # that transaction. The exact same plan must remain idempotent.
            outcome, resumed = run("root append already-replayed stage", expected, head)
            harness.require(resumed == outputs, "already-replayed stage changed plan")
            yield "root append already-replayed stage", outcome
            write(baseline)
        body = baseline[LOG + head + 1]
        cases = [
            ("nonzero padding", {LOG + head + 1: altered(body, 511, b"\x01")}),
            ("wrong ticket", {LOG + head + 1: altered(body, 12, b"\x00\x00\x00\x01")}),
            ("wrong body cycle", {LOG + head + 1: altered(body, 0, b"\x00\x00\x00\x09")}),
            ("bad frontier header", {LOG + head: altered(baseline[LOG + head], 16, b"\xff")}),
            ("bad successor", {LOG + head + 2: bytes(512)}),
            ("second current body", {LOG + head + 3: body}),
            ("corrupt root home", {96: altered(baseline[96], 511, b"\x01")}),
            ("foreign stage name", {96: inode_crc(baseline[96].replace(b".aurora-stage", b".aurora-other"))}),
            ("corrupt allocation metadata", {1: altered(baseline[1], 511, b"\x01")}),
            ("multiply linked stage", {100: inode_crc(altered(baseline[100], 16, (2).to_bytes(4, "big")))}),
            (
                "wrong logged inode",
                {LOG + head + 1: altered(body, 68, (99 if kind == "stage" else 100).to_bytes(8, "little"))},
            ),
        ]
        if kind == "stage":
            for size in (0, 4097):
                cases.append((f"pending size {size}", {LOG + head + 1: altered(body, 176, size.to_bytes(8, "little"))}))
        else:
            cases.append(("pending root no exchange", {LOG + head + 1: altered(body, 308, baseline[96][176:216])}))
            cases.append(("missing committed stage header", {LOG + 33: original[LOG + 33]}))
        for name, changes in cases:
            write(baseline)
            write(changes)
            label = kind + " append " + name
            outcome, _ = run(label)
            yield label, outcome
        write(baseline)
        write(dict(outputs))
        outcome, _ = run(kind + " append completed reentry", [], head, clean=True)
        yield kind + " append completed reentry", outcome
        result = harness.command([mount, image, "hello", "--linux-6.12-x86_64-clean"], timeout=30)
        harness.require(result.returncode == 0 and len(result.stdout) == 64, "append target no longer old")
        harness.require(result.stdout == original[72][:64], "append target changed")
        yield kind + " append retains old target", "exact old 64 bytes"
        result = harness.command([mount, image, ".aurora-stage", "--linux-6.12-x86_64-clean"], timeout=30)
        # This diagnostic owns the raw image and can already read its sectors.
        # Public HostFiles privacy is enforced/tested at the shared service boundary.
        private = fixture("append-" + kind + "-linux-data.hex")[: 64 if kind == "stage" else 777]
        harness.require(result.returncode == 0 and result.stdout == private, "raw stage differs from Linux")
        yield kind + " append raw stage matches Linux", f"exact {len(private)} bytes"


def describe(compiler, directory):
    hashes = json.loads((harness.ROOT / "fixtures/xfs-core-redo/hashes.json").read_text())

    def fixture(name):
        return hex_fixture("xfs-core-redo", name + ".hex", hashes[name + ".hex"])

    ag_hashes = json.loads((harness.ROOT / "fixtures/xfs-recovery-ag/hashes.json").read_text())

    def ag_fixture(name):
        return hex_fixture("xfs-recovery-ag", name + ".hex", ag_hashes[name + ".hex"])

    source = harness.HERE / "xfs_recovery.au"
    assembly, obj, program = (directory / name for name in ("recovery.s", "recovery.o", "recovery"))
    for command in (
        [
            compiler,
            "--module-root",
            harness.ROOT / "library",
            "--runtime-root",
            harness.ROOT / "runtime/linux",
            source,
            "-o",
            assembly,
        ],
        ["as", "-o", obj, assembly],
        ["ld", "-o", program, obj],
    ):
        result = harness.command(command, timeout=120)
        harness.require(result.returncode == 0, result.stderr.decode())
    mount_assembly, mount_obj, mount = (directory / name for name in ("mount.s", "mount.o", "mount"))
    for command in (
        [
            compiler,
            "--module-root",
            harness.ROOT / "library",
            "--runtime-root",
            harness.ROOT / "runtime/linux",
            harness.ROOT / "examples/xfs-fresh-cat.au",
            "-o",
            mount_assembly,
        ],
        ["as", "-o", mount_obj, mount_assembly],
        ["ld", "-o", mount, mount_obj],
    ):
        result = harness.command(command, timeout=120)
        harness.require(result.returncode == 0, result.stderr.decode())
    base = {
        0: fixture("superblock"),
        96: fixture("root-before"),
        99: fixture("inode-99-before"),
        100: fixture("inode-100-before"),
        LOG: fixture("dirty-log-prefix"),
    }
    base[72] = fixture("hello-data")
    base[160] = fixture("pattern-data")
    stale = fixture("dirty-stale-header")
    headers = bytearray()
    for block in range(7, 4098):
        header = bytearray(stale)
        header[16:24] = block.to_bytes(8, "big")
        headers.extend(header)
    base[LOG + 7] = bytes(headers)
    for ag in range(4):
        for name, offset in (("agf", 1), ("agi", 2), ("inobt", 24)):
            base[ag * 262144 + offset] = ag_fixture(f"{name}-{ag}")
    # Keep the historical ring once. Focused cases use synthetic geometry, not
    # a complete Linux-valid filesystem: scan all 64 declared sectors, with the
    # same active records, stale boundary and zero tail. No product scan bypass.
    full_ring = {0: base[0], LOG + 7: base[LOG + 7]}
    base[0] = change(base[0], logblocks=8)
    base[LOG + 7] = bytes(headers[: 9 * 512])  # stale sectors 7..15; 16..63 are zero
    success_labels = (
        "full dirty log plans Linux inode sectors",
        "synthetic short-ring dirty log plans Linux inode sectors",
        "synthetic short-ring dirty log with already recovered homes",
    )
    rows = [(success_labels[0], full_ring, "0"), (success_labels[1], {}, "0")]
    rows.extend(
        (label, {}, str(mode))
        for mode, label in enumerate(("short cache", "reused topology", "failed IO", "wrong LBA", "short response"), 1)
    )
    rows.append(("late failed IO discards prior converted homes", {}, "6"))
    rows.extend(
        (f"torn home {inode}", {inode: set_fields(base[inode], (100, 1, 0), crc=None)}, "0") for inode in (99, 100)
    )
    rows.append(
        (
            "duplicate root target",
            {96: shortform(base[96], [(b"hello", 99, 1, 96), (b"pattern", 99, 1, 120)], parent=96)},
            "0",
        )
    )
    rows.append(("mismatched summary", {0: set_fields(base[0], (144, 8, 58), crc=224)}, "0"))
    rows.append(("bad final AG CRC", {3 * 262144 + 2: set_fields(base[3 * 262144 + 2], (312, 1, 0), crc=None)}, "0"))
    rows.append(
        ("bad final INOBT CRC", {3 * 262144 + 24: set_fields(base[3 * 262144 + 24], (52, 1, 0), crc=None)}, "0")
    )
    last_tree = bytearray(base[3 * 262144 + 24])
    last_tree[4095] ^= 1
    rows.append(("bad final INOBT last byte", {3 * 262144 + 24: bytes(last_tree)}, "0"))
    prefix = base[LOG]
    second_header, second_body = bytearray(prefix[5 * 512 : 6 * 512]), bytearray(prefix[6 * 512 : 7 * 512])
    second_body[56] = 3  # Unsupported ilf_fields after the first transaction converted both targets.
    second_header[32:36] = bytes(4)
    second_header[32:36] = harness.crc32c(second_header[:328] + second_body).to_bytes(4, "little")
    rows.append(
        (
            "unsupported later transaction discards earlier plan",
            {LOG + 5: bytes(second_header), LOG + 6: bytes(second_body)},
            "0",
        )
    )
    rows.append(("late truncated live record CRC", {LOG + 6: b"\x00\x00\x00\x01" + bytes(508)}, "0"))
    rows.append(
        (
            success_labels[2],
            {99: fixture("inode-99-after"), 100: fixture("inode-100-after")},
            "0",
        )
    )
    expected = {inode: fixture(f"inode-{inode}-after") for inode in (99, 100)}
    for label, changed, mode in rows:
        image = directory / "input.img"
        with image.open("wb") as stream:
            stream.truncate(1048576 * 512)
            for lba, data in base.items():
                stream.seek(lba * 512)
                stream.write(data)
            for lba, data in changed.items():
                stream.seek(lba * 512)
                stream.write(data)
        before = None
        if label in success_labels:
            with image.open("rb") as stream:
                before = hashlib.file_digest(stream, "sha256").digest()
        result = harness.command([program, image, mode], timeout=30)
        harness.require(
            result.returncode == 0 and not result.stderr, f"{label}: {result.returncode}: {result.stderr!r}"
        )
        status, count, reads, reserve = struct.unpack("<4Q", result.stdout[:32])
        harness.require(len(result.stdout) == 32 + 520 * (count + 2), label + ": malformed output")
        harness.require(reads <= 134000, label + ": read bound")
        if label in success_labels:
            harness.require(status == 11 and count == 2, label + ": failed planning")
            planned = {}
            for index in range(count):
                at = 32 + index * 520
                lba = struct.unpack("<Q", result.stdout[at : at + 8])[0]
                planned[lba] = result.stdout[at + 8 : at + 520]
            harness.require(planned == expected, "planned sectors differ from Linux recovery")
            completions = []
            for index in range(2):
                at = 32 + (count + index) * 520
                completions.append(
                    (struct.unpack("<Q", result.stdout[at : at + 8])[0], result.stdout[at + 8 : at + 520])
                )
            harness.require([lba for lba, _ in completions] == [LOG + 8, LOG + 7], "completion order")
            if label == success_labels[1]:
                model = directory / "model.img"
                # Keep the generated sparse fixture sparse; its holes are
                # logically zero and need not consume a full 512 MiB per run.
                with image.open("rb") as source, model.open("xb") as output:
                    length = 0
                    while chunk := source.read(65536):
                        length += len(chunk)
                        if any(chunk):
                            output.write(chunk)
                        else:
                            output.seek(len(chunk), 1)
                    output.truncate(length)
                with model.open("r+b") as stream:
                    for lba, sector in planned.items():
                        stream.seek(lba * 512)
                        stream.write(sector)
                    stream.seek(completions[0][0] * 512)
                    stream.write(completions[0][1])
                partial = harness.command([mount, model, "hello", "--linux-6.12-x86_64-clean"], timeout=30)
                harness.require(partial.returncode != 0 and not partial.stdout, "body-only model admitted")
                yield "modeled body-only interruption", "readonly refused without file bytes"
                resumed_body = harness.command([program, model, "0"], timeout=30)
                harness.require(
                    resumed_body.returncode == 0 and not resumed_body.stderr, "orphan-body reentry driver failure"
                )
                body_state, body_count, body_reads, body_reserve = struct.unpack("<4Q", resumed_body.stdout[:32])
                harness.require(
                    body_state == 11
                    and body_count == 2
                    and body_reserve == reserve
                    and resumed_body.stdout[32:] == result.stdout[32:],
                    "orphan-body plan changed",
                )
                yield (
                    "exact orphan body resumes full preflight",
                    f"ready writes=2 reads={body_reads} reserve={body_reserve}",
                )
                for mode, name in (
                    ("7", "changed completion header on reread"),
                    ("8", "changed completion body on reread"),
                ):
                    rejected = harness.command([program, model, mode], timeout=30)
                    harness.require(
                        rejected.returncode == 0 and not rejected.stderr and len(rejected.stdout) == 1072,
                        name + ": driver failure",
                    )
                    state, writes, consumed, remaining = struct.unpack("<4Q", rejected.stdout[:32])
                    harness.require(
                        state not in (11, 19)
                        and writes == 0
                        and remaining == 0
                        and consumed > 64
                        and rejected.stdout[32:] == bytes(1040),
                        name + ": not rejected after full scan",
                    )
                    yield name, f"{STATUSES[state]} writes=0 reads={consumed} reserve=0"
                original_body = completions[0][1]
                old8 = bytes(headers[512:1024])
                old9 = bytes(headers[1024:1536])
                old10 = bytes(headers[1536:2048])
                padded = bytearray(original_body)
                padded[511] = 1
                bad_header = bytearray(stale)
                bad_header[304] ^= 1
                orphan_cases = (
                    ("non-stale old boundary cannot arm orphan", {LOG + 7: bytes(512)}, {LOG + 7: stale}),
                    ("altered orphan padding", {LOG + 8: bytes(padded)}, {LOG + 8: original_body}),
                    (
                        "wrong orphan cycle",
                        {LOG + 8: b"\x00\x00\x00\x02" + original_body[4:]},
                        {LOG + 8: original_body},
                    ),
                    (
                        "wrong orphan location",
                        {LOG + 8: old8, LOG + 9: original_body},
                        {LOG + 8: original_body, LOG + 9: old9},
                    ),
                    ("double orphan body", {LOG + 10: original_body}, {LOG + 10: old10}),
                    ("invalid old header before orphan", {LOG + 7: bytes(bad_header)}, {LOG + 7: stale}),
                    (
                        "orphan cannot hide torn home",
                        {99: set_fields(planned[99], (100, 1, 0), crc=None)},
                        {99: planned[99]},
                    ),
                )
                for name, mutation, restore in orphan_cases:
                    with model.open("r+b") as stream:
                        for lba, sector in mutation.items():
                            stream.seek(lba * 512)
                            stream.write(sector)
                    rejected = harness.command([program, model, "0"], timeout=30)
                    harness.require(
                        rejected.returncode == 0 and not rejected.stderr and len(rejected.stdout) == 1072,
                        name + ": driver failure",
                    )
                    state, writes, consumed, remaining = struct.unpack("<4Q", rejected.stdout[:32])
                    harness.require(
                        state not in (11, 19)
                        and writes == 0
                        and remaining == 0
                        and rejected.stdout[32:] == bytes(1040),
                        name + ": exposes output",
                    )
                    yield name, f"{STATUSES[state]} writes=0 reads={consumed} reserve=0"
                    with model.open("r+b") as stream:
                        for lba, sector in restore.items():
                            stream.seek(lba * 512)
                            stream.write(sector)

                with model.open("r+b") as stream:
                    stream.seek(completions[1][0] * 512)
                    stream.write(completions[1][1])
                for name in ("hello", "pattern"):
                    mounted = harness.command([mount, model, name, "--linux-6.12-x86_64-clean"], timeout=30)
                    harness.require(
                        mounted.returncode == 0 and not mounted.stderr and mounted.stdout == fixture(name + "-data"),
                        "completed model read mismatch",
                    )
                    yield "modeled completion readonly " + name, f"exact {len(mounted.stdout)} bytes"
                with model.open("rb") as stream:
                    clean_before = hashlib.file_digest(stream, "sha256").digest()
                resumed = harness.command([program, model, "0"], timeout=30)
                harness.require(
                    resumed.returncode == 0 and not resumed.stderr and len(resumed.stdout) == 1072,
                    "clean reentry driver failure",
                )
                state, writes, consumed, remaining = struct.unpack("<4Q", resumed.stdout[:32])
                harness.require(
                    state == 19 and writes == 0 and remaining == 32769 and resumed.stdout[32:] == bytes(1040),
                    "clean reentry exposes writes",
                )
                with model.open("rb") as stream:
                    harness.require(
                        hashlib.file_digest(stream, "sha256").digest() == clean_before, "clean reentry changed image"
                    )
                yield "modeled completed-marker reentry", f"already_clean writes=0 reads={consumed} reserve={remaining}"
                denied_clean = harness.command([program, model, "9"], timeout=30)
                harness.require(
                    denied_clean.returncode == 0 and not denied_clean.stderr and len(denied_clean.stdout) == 1072,
                    "clean-marker IO failure driver error",
                )
                state, writes, consumed, remaining = struct.unpack("<4Q", denied_clean.stdout[:32])
                harness.require(
                    state == 14 and writes == 0 and remaining == 0 and denied_clean.stdout[32:] == bytes(1040),
                    "clean-marker IO failure exposes output",
                )
                yield "clean marker IO failure", f"io_error writes=0 reads={consumed} reserve=0"
                for name, lba, changed_bytes, original in (
                    ("torn home", 99, set_fields(planned[99], (100, 1, 0), crc=None), planned[99]),
                    ("mismatched summary", 0, set_fields(base[0], (144, 8, 58), crc=224), base[0]),
                ):
                    with model.open("r+b") as stream:
                        stream.seek(lba * 512)
                        stream.write(changed_bytes)
                    rejected = harness.command([program, model, "0"], timeout=30)
                    harness.require(
                        rejected.returncode == 0 and not rejected.stderr and len(rejected.stdout) == 1072,
                        "invalid clean reentry driver failure",
                    )
                    state, writes, consumed, remaining = struct.unpack("<4Q", rejected.stdout[:32])
                    harness.require(
                        state not in (11, 19)
                        and writes == 0
                        and remaining == 0
                        and rejected.stdout[32:] == bytes(1040),
                        "invalid clean reentry exposes output",
                    )
                    yield "clean marker cannot hide " + name, f"{STATUSES[state]} writes=0 reads={consumed} reserve=0"
                    with model.open("r+b") as stream:
                        stream.seek(lba * 512)
                        stream.write(original)

            with image.open("rb") as stream:
                harness.require(hashlib.file_digest(stream, "sha256").digest() == before, "preflight wrote image")
        else:
            harness.require(
                status != 11 and count == 0 and reserve == 0 and result.stdout[32:] == bytes(1040),
                label + ": refusal exposes output",
            )
        yield label, f"{STATUSES[status]} writes={count} reads={reads} reserve={reserve}"

    yield from exchange_cases(program, mount, directory)
    yield from staged_cases(program, mount, directory)
    yield from append_cases(program, mount, directory)


if __name__ == "__main__":
    harness.main("xfs_recovery", describe)
