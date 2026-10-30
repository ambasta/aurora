#!/usr/bin/env python3
"""One source service driver over synthetic cases and a genuine mounted witness."""

import harness
import sys
import struct
import hashlib
import json
import lzma
from xfs_inputs import change, set_fields, shortform
from xfs_mount import fixture

sys.path.insert(0, str(harness.ROOT / "scripts"))
from kernel_volume import volume

ZERO_CHUNK = bytes(65536)


def mounted_cases(program, directory):
    """Production formatter against the Linux-accepted command witness.

    One genuine full-ring proof serves payload and append-response cases.
    A synthetic reversed-name image receives its own complete clean preflight.
    Response faults and reversed names are not additional Linux witnesses.
    """
    fixture_dir = harness.ROOT / "fixtures/xfs-staged-replace"
    hashes = json.loads((fixture_dir / "append-hashes.json").read_text())
    archive = fixture_dir / "append-clean.img.xz"
    harness.require(hashlib.sha256(archive.read_bytes()).hexdigest() == hashes[archive.name], "commit archive hash")
    image = directory / "mounted.img"
    digest, length = hashlib.sha256(), 0
    with lzma.open(archive, "rb") as source, image.open("xb") as output:
        while chunk := source.read(65536):
            digest.update(chunk)
            length += len(chunk)
            if chunk != ZERO_CHUNK[: len(chunk)]:
                output.write(chunk)
            else:
                output.seek(len(chunk), 1)
        output.truncate(length)
    harness.require(length == 536870912 and digest.hexdigest() == hashes["append-clean.img"], "commit image hash")
    witness = bytes.fromhex((fixture_dir / "append-writes.hex").read_text())
    harness.require(hashlib.sha256(witness).hexdigest() == hashes["append-writes.hex"], "commit witness hash")
    payload = directory / "mounted.payload"
    data = bytes((at * 37 + 91) % 251 for at in range(4097))
    payload.write_bytes(data)
    case_file = directory / "mounted.cases"

    def run(rows):
        case_file.write_bytes(b"".join(struct.pack("<QQ", size, bad_append) for size, bad_append, _ in rows))
        result = harness.command([program, image, "mounted", payload, case_file], timeout=30)
        harness.require(result.returncode == 0 and not result.stderr, "mounted batch: " + result.stderr.decode())
        expected_length = sum((8448 if outcome == 0 else 0) + 8 for _, _, outcome in rows)
        harness.require(len(result.stdout) == expected_length, "complete mounted batch; no trailing plan bytes")
        cursor = 0
        for size, _, expected in rows:
            length = 8448 if expected == 0 else 0
            plan = result.stdout[cursor : cursor + length]
            observed = struct.unpack_from("<Q", result.stdout, cursor + length)[0]
            harness.require(observed == expected, "mounted acceptance or refusal phase")
            cursor += length + 8
            yield size, plan

    def describe_plan(size, plan, first_lba=160):
        if not plan:
            return "refused; no writes"
        harness.require(len(plan) == 8448, "bounded write plan")
        records = [plan[at : at + 528] for at in range(0, 8448, 528)]
        harness.require(
            b"".join(row[16:] for row in records[:8]) == data[:size] + bytes(4096 - size), "payload and zero tail"
        )
        harness.require(
            [struct.unpack("<Q", row[8:16])[0] for row in records]
            == [int(at in (9, 11, 13, 14, 15)) for at in range(16)],
            "five flush boundaries",
        )
        harness.require(
            [struct.unpack("<Q", row[:8])[0] for row in records[:8]] == list(range(first_lba, first_lba + 8)),
            "staging data blocks",
        )
        stage_inode = 100 if first_lba == 160 else 99
        harness.require(struct.unpack("<Q", records[12][:8])[0] == stage_inode, "staging inode home")
        harness.require(int.from_bytes(records[12][72:80], "big") == size, "staging inode size")
        harness.require(struct.unpack("<Q", records[13][:8])[0] == 96, "root inode home")
        if size == 777 and first_lba == 160:
            harness.require(plan == witness, "Linux-accepted exact command witness")
        return "16 writes; 5 flushes; exact payload and zero tail"

    sizes = [0, 1, 777, 4096, 4097]
    rows = [(size, 0, 0 if 1 <= size <= 4096 else 1) for size in sizes]
    # These zero-sector responses reach the real append consumer only after
    # the unchanged full image has passed clean recovery. Every LBA must fail
    # specifically at accept_append, without exposing a write plan.
    rows += [(1, 524328 + sector, 2) for sector in range(33, 40)]
    observed = list(run(rows))
    # Preserve the cold-preflight distinction at the first stale boundary:
    # zero old-cycle data is still clean, but cannot arm the mounted writer.
    # This synthetic disk receives its own full proof, not the original's.
    with image.open("r+b") as stream:
        stream.seek(524361 * 512)
        stale = stream.read(512)
        stream.seek(524361 * 512)
        stream.write(bytes(512))
    try:
        harness.require(list(run([(1, 524361, 2)])) == [(1, b"")], "cold noncanonical boundary refuses append")
    finally:
        with image.open("r+b") as stream:
            stream.seek(524361 * 512)
            stream.write(stale)
    for index, (size, plan) in enumerate(observed):
        label = (
            f"mounted replacement size {size}"
            if index < len(sizes)
            else f"mounted noncanonical append sector {33 + index - len(sizes)}"
        )
        yield label, describe_plan(size, plan)

    with image.open("r+b") as stream:
        stream.seek(96 * 512)
        root = stream.read(512)
        swapped = shortform(root, [(b"hello", 100, 1, 96), (b".aurora-stage", 99, 1, 120)], parent=96)
        stream.seek(96 * 512)
        stream.write(swapped)
    # The root changed: do not reuse the original root's authenticated proof.
    for size, plan in run([(1, 0, 0)]):
        yield "mounted synthetic reversed inode roles", describe_plan(size, plan, 72)


def describe(compiler, directory):
    assembly, obj, program = (directory / name for name in ("service.s", "service.o", "service"))
    result = harness.command(
        [
            compiler,
            "--module-root",
            harness.ROOT / "library",
            "--module-root",
            harness.ROOT / "services",
            "--module-root",
            harness.ROOT / "kernel/policies",
            "--runtime-root",
            harness.ROOT / "runtime/linux",
            harness.ROOT / "tests/services/xfs.au",
            "-o",
            assembly,
        ],
        timeout=120,
    )
    harness.require(result.returncode == 0, result.stderr.decode())
    for command in (["as", "-o", obj, assembly], ["ld", "-o", program, obj]):
        result = harness.command(command)
        harness.require(result.returncode == 0, result.stderr.decode())

    def bootstrap(operation=1, volume=0, profile=0, count=0, last=0):
        return struct.pack("<8Q", operation, volume, profile, count, 0, 0, 0, last)

    for label, data in [
        ("fresh bootstrap", bootstrap()),
        ("Linux bootstrap at maximum volume", bootstrap(volume=268435456, profile=1)),
        ("oversized bootstrap volume", bootstrap(volume=268435457)),
        ("unknown bootstrap profile", bootstrap(profile=2)),
        ("overflow bootstrap profile", bootstrap(profile=(1 << 64) - 1)),
        ("wrong bootstrap operation", bootstrap(operation=2)),
        ("nonzero bootstrap count byte24", bootstrap(count=1)),
        ("nonzero bootstrap reserved byte63", bootstrap(last=1 << 56)),
        ("empty bootstrap", b""),
        ("short bootstrap", bootstrap()[:-1]),
        ("long bootstrap", bootstrap() + b"\0"),
    ]:
        record = directory / "bootstrap.bin"
        record.write_bytes(data)
        result = harness.command([program, record, "header"], timeout=10)
        yield label, "exit={} stdout={!r} stderr={!r}".format(result.returncode, result.stdout, result.stderr)

    sb, root, inode = [fixture(name) for name in ("superblock", "root", "inode")]
    # Synthetic second file and shortened log. This is not a formatted filesystem.
    sb = change(sb, logblocks=1)
    root = shortform(root, [(b"hello", 99, 1, 96), (b"pattern", 100, 1, 120)], parent=96)
    pattern_inode = set_fields(inode, (152, 8, 100), (56, 8, 9001), (64, 8, 3), (176, 16, (16 << 21) | 3), crc=100)
    pattern = bytes((index * 37 + 11) % 256 for index in range(9001))
    sectors = {
        0: sb,
        96: root,
        99: inode,
        100: pattern_inode,
        72: fixture("data"),
        128: pattern,
        524328: fixture("log-header"),
        524329: fixture("log-unmount"),
    }
    rows = [
        ("owned mount handles, reads, close, confinement and quarantine", {}, 1048576, []),
        ("partial read I/O failure publishes no bytes", {}, 1048576, ["io"]),
        ("partial read generation change publishes no bytes", {}, 1048576, ["generation"]),
        ("dirty mounted backend unavailable", {524335: bytes([1]) + bytes(511)}, 1048576, []),
        ("unsupported mounted backend unavailable", {0: change(sb, ro_compat=15)}, 1048576, []),
        ("short mounted backend unavailable", {}, 1048575, []),
    ]
    for label, changes, length, arguments in rows:
        image = directory / "input.img"
        with image.open("wb") as stream:
            stream.truncate(length * 512)
            for lba, data in {**sectors, **changes}.items():
                stream.seek(lba * 512)
                stream.write(data)
        result = harness.command([program, image, *arguments], timeout=10)
        yield label, "exit={} stdout={!r} stderr={!r}".format(result.returncode, result.stdout, result.stderr)
    for label, entries, mode in [
        ("boot root routing, confinement and absent disk preserve Store", [], "boot"),
        ("source export snapshot, replacement, empty files and cancelled outputs", [], "export"),
        ("boot file collision reserves unavailable disk namespace", [(b"disk", b"C")], "collision"),
        ("boot directory collision reserves unavailable disk namespace", [(b"disk/hidden", b"C")], "collision"),
    ]:
        image = directory / "boot.volume"
        image.write_bytes(volume([(b"tree/a", b"A"), (b"tree/disk/hello", b"B"), *entries]))
        result = harness.command([program, image, mode], timeout=10)
        yield label, "exit={} stdout={!r} stderr={!r}".format(result.returncode, result.stdout, result.stderr)

    def command(text, profile=None):
        return (
            text.ljust(64, b"\0")
            + struct.pack("<Q", len(text))
            + (b"" if profile is None else struct.pack("<Q", profile))
        )

    def selection(name, revision, writable, suffix=b""):
        return (
            name.ljust(64, b"\0")
            + struct.pack("<QQQ", len(name), revision, writable)
            + suffix.ljust(64, b"\0")
            + struct.pack("<Q", len(suffix))
        )

    note = b"a" * 53
    scripts = [
        (
            "console note53, replacement revision, clear and stale rejection",
            [
                (10, 0, command(b"cat note")),
                (10, 0, command(b"write note " + note)),
                (10, 0, command(b"upper note")),
                (12, 2, command(note.upper())),
                (12, 2, command(b"stale")),
                (12, 3, command(b"a" * 54)),
                (14, 0, b""),
                (10, 0, command(b"cat note")),
                (12, 3, command(b"stale")),
            ],
        ),
        (
            "console files append proof, conflict, clear and monotonic selection",
            [
                (11, 0, command(b"write a hello", 0)),
                (11, 0, command(b"append a !", 0)),
                (13, 0, selection(b"a", 2, 2, b"!") + command(b"hellX!")),
                (13, 0, selection(b"a", 2, 2, b"!") + command(b"hello!")),
                (13, 0, selection(b"a", 2, 2, b"!") + command(b"hello!")),
                (11, 0, command(b"cat a", 0)),
                (14, 0, b""),
                (11, 0, command(b"write a again", 0)),
                (13, 0, selection(b"a", 3, 1) + command(b"stale")),
                (11, 0, command(b"upper a", 0)),
            ],
        ),
        (
            "console file49 boundary and canonical malformed wire",
            [
                (11, 0, command(b"write b " + b"x" * 49, 0)),
                (11, 0, command(b"cat b", 0)),
                (11, 0, command(b"write b " + b"x" * 50, 0)),
                (11, 0, command(b"cat b", 0)),
                (11, 0, command(b"write c blocked", 1)),
                (10, 1, command(b"cat note")),
                (10, 0, b""),
                (10, 0, b"cat note" + b"x" + bytes(55) + struct.pack("<Q", 8)),
                (14, 1, b""),
                (15, 0, b""),
            ],
        ),
    ]
    for label, commands in scripts:
        image = directory / "console.commands"
        image.write_bytes(
            b"".join(
                struct.pack("<QQQ", operation, expected, len(payload)) + payload
                for operation, expected, payload in commands
            )
        )
        result = harness.command([program, image, "notes"], timeout=10)
        yield label, "exit={} stdout={!r} stderr={!r}".format(result.returncode, result.stdout, result.stderr)

    yield from mounted_cases(program, directory)


if __name__ == "__main__":
    harness.main("xfs_service", describe)
