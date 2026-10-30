#!/usr/bin/env python3
"""One compiled mounted-reader program over sparse synthetic input images.

Preserved sectors are xfsprogs and pinned Linux output; reconstructed sparse
images deliberately omit unrelated AG metadata and are NOT whole filesystems or
interoperability evidence. Independent whole-image runs are in docs/xfs.md.
"""

import hashlib
import json

import harness
from xfs_inputs import change, hex_fixture, set_fields, shortform


def fixture(name, prefix="fresh-"):
    rows = json.loads((harness.ROOT / "fixtures/xfs-file/hashes.json").read_text())
    filename = prefix + name + ".hex"
    digest = next(row["decoded_sha256"] for row in rows if row["name"] == filename)
    return hex_fixture("xfs-file", filename, digest)


def used_cases(log_lba):
    """Synthetic shortened/cycle-mutated inputs from an observed Linux clean log."""
    saved = {
        name: fixture(name, "linux-6.12-used-")
        for name in ("superblock", "root", "inode", "pattern-inode", "data", "log-prefix", "stale-header")
    }
    base = {
        0: change(saved["superblock"], logblocks=8),
        96: saved["root"],
        99: saved["inode"],
        100: saved["pattern-inode"],
        72: saved["data"],
        log_lba + 13: saved["stale-header"],
    }
    for sector in range(13):
        base[log_lba + sector] = saved["log-prefix"][sector * 512 : (sector + 1) * 512]
    yield "Linux used input refused by default fresh profile", base, "hello", 1048576
    header, body = base[log_lba + 11], base[log_lba + 12]
    rows = [("synthetic Linux shortened clean log", {})]

    def crc_record(head, payload, header_size=328):
        # Construction only, not the acceptance oracle: same existing CRC input helper.
        head = bytearray(head)
        head[32:36] = bytes(4)
        head[32:36] = harness.crc32c(head[:header_size] + payload).to_bytes(4, "little")
        return bytes(head)

    for offset in (4, 8, 12, 16, 24, 32, 36, 40, 44, 48, 300, 304, 320, 324, 511):
        bad = bytearray(header)
        bad[offset] ^= 1
        rows.append((f"Linux header corruption byte{offset}", {log_lba + 11: bytes(bad)}))
    for offset in (0, 4, 8, 9, 10, 12, 14, 19, 20, 511):
        bad = bytearray(body)
        bad[offset] ^= 1
        rows.append((f"Linux body corruption byte{offset}", {log_lba + 12: bytes(bad)}))
    for size in (324, 512):
        rows.append((f"Linux wrong CRC header coverage {size}", {log_lba + 11: crc_record(header, body, size)}))
    padding = set_fields(body, (511, 1, body[511] ^ 1), crc=None)
    rows.append(
        (
            "synthetic Linux CRC-covered opaque padding",
            {log_lba + 11: crc_record(header, padding), log_lba + 12: padding},
        )
    )
    rows.append(
        (
            "Linux malformed stale-clear header",
            {log_lba + 13: set_fields(saved["stale-header"], (320, 4, 32768), crc=None)},
        )
    )
    rows.append(("Linux zero hole before newest record", {log_lba + 6: bytes(512)}))
    rows.append(("Linux future cycle hole", {log_lba + 6: set_fields(base[log_lba + 6], (0, 4, 2), crc=None)}))
    rows.append(("Linux extra cycle transition", {log_lba + 40: set_fields(bytes(512), (0, 4, 1), crc=None)}))
    rows.append(
        ("Linux newer stamped data after clean marker", {log_lba + 13: set_fields(bytes(512), (0, 4, 1), crc=None)})
    )
    dirty_body = set_fields(body, (9, 1, 0), crc=None)
    newer = set_fields(header, (16, 8, (1 << 32) | 14), (36, 4, 11), crc=None)
    newer = crc_record(newer, dirty_body)
    rows.append(
        (
            "Linux newer CRC-valid non-UNMOUNT defeats old marker",
            {log_lba + 13: set_fields(bytes(512), (0, 4, 1), crc=None), log_lba + 14: newer, log_lba + 15: dirty_body},
        )
    )
    rows.append(
        (
            "Linux torn newer record defeats old UNMOUNT",
            {log_lba + 13: set_fields(bytes(512), (0, 4, 1), crc=None), log_lba + 14: newer},
        )
    )
    for label, sector, offset in (("superblock", 0, 240), ("inode", 99, 112)):
        for lsn in ((1 << 32) | 14, (2 << 32), (1 << 64) - 1):
            rows.append(
                (
                    f"Linux future or invalid {label} LSN {lsn}",
                    {sector: set_fields(base[sector], (offset, 8, lsn), crc=224 if sector == 0 else 100)},
                )
            )
    for wrap in (False, True):
        changed = {log_lba + sector: set_fields(bytes(512), (0, 4, 2), crc=None) for sector in range(64)}
        start = 63 if wrap else 62
        moved_body = set_fields(body, (0, 4, 3 if wrap else 2), crc=None)
        moved_header = set_fields(header, (4, 4, 2), (16, 8, (2 << 32) | start), crc=None)
        changed[log_lba + start] = crc_record(moved_header, moved_body)
        changed[log_lba + (start + 1) % 64] = moved_body
        rows.append(("synthetic Linux " + ("UNMOUNT wraps header63 body0" if wrap else "whole-cycle head0"), changed))
        bad_cycle = dict(changed)
        bad_cycle[log_lba + (start + 1) % 64] = set_fields(moved_body, (0, 4, 1), crc=None)
        rows.append(("Linux wrong wrapped cycle" if wrap else "Linux torn end-cycle body", bad_cycle))
    for label, changed in rows:
        yield label, {**base, **changed}, "hello", 1048576, "--linux-6.12-x86_64-clean"
    # Genuine unclean-poweroff log sectors, but still a synthetic shortened image.
    dirty = {**base, 0: change(fixture("superblock", "linux-6.12-dirty-"), logblocks=8)}
    prefix = fixture("log-prefix", "linux-6.12-dirty-")
    for sector in range(14):
        dirty[log_lba + sector] = prefix[sector * 512 : (sector + 1) * 512] if sector < 8 else bytes(512)
    yield "synthetic shortened genuine dirty-log input", dirty, "hello", 1048576, "--linux-6.12-x86_64-clean"


def describe(compiler, directory):
    source = harness.ROOT / "examples/xfs-fresh-cat.au"
    assembly, obj, program = (directory / n for n in ("mount.s", "mount.o", "mount"))
    command = [
        compiler,
        "--module-root",
        harness.ROOT / "library",
        "--runtime-root",
        harness.ROOT / "runtime/linux",
        source,
        "-o",
        assembly,
    ]
    result = harness.command(command, timeout=120)
    harness.require(result.returncode == 0, result.stderr.decode())
    for command in (["as", "-o", obj, assembly], ["ld", "-o", program, obj]):
        result = harness.command(command)
        harness.require(result.returncode == 0, result.stderr.decode())
    sb, root, inode = [fixture(n) for n in ("superblock", "root", "inode")]
    header, unmount, data = [fixture(n) for n in ("log-header", "log-unmount", "data")]
    # The golden payload comes from the mkfs prototype input, not the parser.
    payload = b"Aurora reads a real XFS file through its checked block backend.\n"
    log_lba = 65541 * 8
    base = {0: change(sb, logblocks=1), 96: root, 99: inode, 72: data, log_lba: header, log_lba + 1: unmount}
    cases = [
        ("synthetic shortened-log mounted file", {}, "hello", 1048576),
        ("full64MiB zero-log scan", {0: sb}, "hello", 1048576),
        ("absent name", {}, "absent", 1048576),
        ("invalid path", {}, "../hello", 1048576),
        ("short volume", {}, "hello", 1048575),
    ]
    for field, value in [("incompat", 3), ("ro_compat", 15), ("compat", 1), ("log_incompat", 1), ("dirblklog", 1)]:
        cases.append(("excluded " + field, {0: change(base[0], **{field: value})}, "hello", 1048576))
    for lba, offsets in [
        (log_lba, [0, 4, 8, 12, 16, 24, 32, 36, 40, 44, 300, 304, 320, 511]),
        (log_lba + 1, [0, 4, 8, 9, 10, 12, 20, 511]),
        (log_lba + 7, [0, 511]),
        (96, [100]),
        (99, [100]),
    ]:
        for offset in offsets:
            bad = bytearray(base.get(lba, bytes(512)))
            bad[offset] ^= 1
            cases.append((f"corrupt sector{lba} byte{offset}", {lba: bytes(bad)}, "hello", 1048576))
    cases.append(("nonzero superblock LSN", {0: set_fields(base[0], (240, 8, 1), crc=224)}, "hello", 1048576))
    cases.append(("nonzero inode LSN", {99: set_fields(inode, (112, 8, 1), crc=100)}, "hello", 1048576))
    cases.append(("null UUID", {0: set_fields(base[0], (32, 16, 0), crc=224)}, "hello", 1048576))
    cases.append(("all-zero log rejected", {log_lba: bytes(512), log_lba + 1: bytes(512)}, "hello", 1048576))
    cases.append(("unsupported nested directory", {96: set_fields(root, (190, 1, 2), crc=100)}, "hello", 1048576))
    cases.append(("unsupported empty regular file", {99: set_fields(inode, (56, 8, 0), crc=100)}, "hello", 1048576))
    hole = set_fields(inode, (64, 8, 0), (76, 4, 0), crc=100)
    unwritten = set_fields(inode, (176, 1, inode[176] | 128), crc=100)
    cases.append(("mounted sparse hole masks poison data", {99: hole, 72: b"X" * 512}, "hello", 1048576))
    cases.append(("mounted unwritten extent masks poison data", {99: unwritten, 72: b"X" * 512}, "hello", 1048576))
    later = shortform(root, [(b"hello", 99, 1, 96), (b"later", 100, 2, 120)], parent=96)
    cases.append(("unsupported later entry prevents earlier file publication", {96: later}, "hello", 1048576))
    cases.append(("late full-log stale record", {0: sb, log_lba + 131071: header}, "hello", 1048576))
    cases.append(
        (
            "fresh record is not a Linux clean record",
            {0: change(sb, logblocks=8)},
            "hello",
            1048576,
            "--linux-6.12-x86_64-clean",
        )
    )
    cases.append(("unknown explicit profile argument", {}, "hello", 1048576, "--unknown"))
    cases.extend(used_cases(log_lba))
    for row in cases:
        label, changed, name, sectors = row[:4]
        options = row[4:]
        image = directory / "input.img"
        with image.open("wb") as stream:
            stream.truncate(sectors * 512)
            for lba, contents in {**base, **changed}.items():
                stream.seek(lba * 512)
                stream.write(contents)
        # Hash the complete positive image once, including unallocated holes.
        before = None
        if label == "full64MiB zero-log scan":
            with image.open("rb") as stream:
                before = hashlib.file_digest(stream, "sha256").digest()
        result = harness.command([program, image, name, *options], timeout=10)
        if before is not None:
            with image.open("rb") as stream:
                after = hashlib.file_digest(stream, "sha256").digest()
            harness.require(before == after, "reader modified image")
        out = result.stdout.decode("ascii", errors="backslashreplace").replace("\n", "\\n")
        err = result.stderr.decode("ascii", errors="backslashreplace").replace("\n", "\\n")
        if label in ("synthetic shortened-log mounted file", "full64MiB zero-log scan"):
            harness.require(result.stdout == payload, "mounted bytes differ from prototype input")
        if label.startswith("synthetic Linux "):
            expected = bytes((index * 37 + 11) % 256 for index in range(64))
            harness.require(
                result.returncode == 0 and result.stdout == expected,
                "mounted used bytes differ from reference writer input",
            )
        yield (
            label,
            f"exit={result.returncode} stdout={out!r} stderr={err!r}" + (" unchanged" if before is not None else ""),
        )
    # Source-level private state and linear ownership cannot be used to fabricate ready.
    prefix = "module test; import std.binary; import std.binary_buffer; import storage.sector;"
    prefix += " import storage.block_io; import fs.xfs_mount; import fs.xfs_log;"
    prefix += " auto test(builtin::ByteRegion region, i64 n, i64 flag) -> u64 {"
    prefix += "builtin::OwnedBytes cache=region.try_allocate(1536);"
    prefix += " const fs::XfsLogTopology topology=fs::XfsLogTopology();"
    prefix += " fs::XfsReadonlyMount mount=fs::XfsReadonlyMount(region,move(cache),1048576u64,"
    prefix += "fs::XfsReadonlyProfile::fresh_format,topology);"
    yield from harness.rejections(
        compiler,
        directory,
        [
            ("private state", prefix + "mount._status=fs::XfsMountStatus::ready; return 0u64;}"),
            ("mount cannot copy", prefix + "fs::XfsReadonlyMount copy=mount; return 0u64;}"),
        ],
    )


if __name__ == "__main__":
    harness.main("xfs_mount", describe)
