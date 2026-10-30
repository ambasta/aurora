#!/usr/bin/env python3
"""Pure CORE conversion against preserved Linux recovery output; no write authority."""

import json

import harness
from xfs_inputs import hex_fixture, set_fields


def describe(compiler, directory):
    hashes = json.loads((harness.ROOT / "fixtures/xfs-core-redo/hashes.json").read_text())

    def fixture(name):
        return hex_fixture("xfs-core-redo", name + ".hex", hashes[name + ".hex"])

    sb = fixture("superblock")
    rows = []

    def case(label, home, core, inode=99, lsn=(1 << 32) | 5, expected=None, **fields):
        values = dict(
            sb=sb,
            home=home,
            core=core,
            sb_length=512,
            home_length=512,
            core_length=len(core),
            inode=inode,
            lsn=lsn,
            capacity=1048576,
        )
        values.update(fields)
        rows.append((label, values, expected))

    for inode, record in ((99, 5), (100, 2)):
        home = fixture(f"inode-{inode}-before")
        core = fixture(f"log-record-{record}-inode-{inode}-core")
        after = fixture(f"inode-{inode}-after")
        lsn = (1 << 32) | record
        case(f"Linux inode {inode} committed CORE", home, core, inode, lsn, after)
        case(f"Linux inode {inode} equal LSN reapplies", after, core, inode, lsn, after)
        stale_equal = set_fields(home, (112, 8, lsn), crc=100)
        case(f"inode {inode} equal LSN stale timestamps reapplied", stale_equal, core, inode, lsn, after)
        newer = set_fields(after, (112, 8, lsn + 1), crc=100)
        case(f"inode {inode} newer intact home", newer, core, inode, lsn, bytes(512))
    home = fixture("inode-99-before")
    core = fixture("log-record-5-inode-99-core")
    after = fixture("inode-99-after")
    ignored = bytearray(core)
    ignored[112:120] = bytes([255]) * 8
    case("logged LSN ignored", home, bytes(ignored), expected=after)
    for name, field, value in (
        ("short superblock", "sb_length", 511),
        ("short home", "home_length", 511),
        ("short CORE", "core_length", 175),
        ("oversized CORE", "core_length", 177),
        ("zero transaction LSN", "lsn", 0),
        ("out-of-log LSN", "lsn", (1 << 32) | 131072),
        ("wrong inode", "inode", 100),
        ("short volume", "capacity", 1),
    ):
        case(name, home, core, expected=bytes(512), **{field: value})
    for offset in (0, 32, 100, 176, 511):
        bad = bytearray(home)
        bad[offset] ^= 1
        case(f"torn home byte {offset}", bytes(bad), core, expected=bytes(512))
    for offset in (2, 8, 16, 64, 76, 152, 160):
        bad = bytearray(core)
        bad[offset] ^= 1
        case(f"immutable CORE byte {offset}", home, bytes(bad), expected=bytes(512))
    for offset in (36, 44, 52, 148):
        bad = bytearray(core)
        bad[offset : offset + 4] = (1000000000).to_bytes(4, "little")
        case(f"invalid timestamp nanoseconds {offset}", home, bytes(bad), expected=bytes(512))
    bad_newer = bytearray(core)
    bad_newer[64] ^= 1
    case(
        "newer home cannot hide unsupported CORE",
        set_fields(after, (112, 8, (1 << 32) | 6), crc=100),
        bytes(bad_newer),
        expected=bytes(512),
    )
    for offset in (24, 120):
        bad = bytearray(core)
        bad[offset] = 1
        case(f"unsupported CORE field {offset}", home, bytes(bad), expected=bytes(512))
    # Genuine Linux same-block growth, independently recovered before these tests.
    staged_hashes = json.loads((harness.ROOT / "fixtures/xfs-staged-replace/hashes.json").read_text())

    def staged(name):
        return hex_fixture("xfs-staged-replace", name + ".hex", staged_hashes[name + ".hex"])

    staged_sb = staged("superblock")
    staged_home, staged_core, staged_after = staged("inode-before"), staged("stage-core"), staged("inode-after")
    stage_lsn = (1 << 32) | 22
    case("Linux one-block growth64 to777", staged_home, staged_core, 100, stage_lsn, staged_after, sb=staged_sb)
    case("grown inode equal LSN reapplies", staged_after, staged_core, 100, stage_lsn, staged_after, sb=staged_sb)
    for size in (1, 64, 4096):
        changed = bytearray(staged_core)
        changed[56:64] = size.to_bytes(8, "little")
        expected = set_fields(staged_after, (56, 8, size), crc=100)
        case(f"synthetic one-block size {size}", staged_home, bytes(changed), 100, stage_lsn, expected, sb=staged_sb)
    for size in (0, 4097, (1 << 63), (1 << 64) - 1):
        changed = bytearray(staged_core)
        changed[56:64] = size.to_bytes(8, "little")
        case(f"rejected one-block size {size}", staged_home, bytes(changed), 100, stage_lsn, bytes(512), sb=staged_sb)
    # A valid newer home cannot suppress malformed size admission.
    changed = bytearray(staged_core)
    changed[56:64] = (4097).to_bytes(8, "little")
    case(
        "newer home cannot hide cross-block size",
        set_fields(staged_after, (112, 8, stage_lsn + 1), crc=100),
        bytes(changed),
        100,
        stage_lsn,
        bytes(512),
        sb=staged_sb,
    )
    for name, source_home, source_core in (
        ("Linux inode99", fixture("inode-99-after"), fixture("log-record-5-inode-99-core")),
        ("Linux inode100", fixture("inode-100-after"), fixture("log-record-2-inode-100-core")),
        ("Linux grown inode100", staged_after, staged_core),
    ):
        encoded = bytearray(source_core)
        # Linux ignores/normalizes these native log fields; canonical encoding
        # leaves them zero rather than duplicating the byte-layout converter.
        for begin, end in ((6, 8), (24, 32), (96, 104), (112, 120), (132, 144)):
            encoded[begin:end] = bytes(end - begin)
        case("encode " + name, source_home, source_core, expected=bytes(encoded) + bytes(336), encode=1)
    case("encode short home", staged_home, staged_core, expected=bytes(512), encode=1, home_length=511)
    driver = harness.Driver(compiler, directory, harness.HERE / "xfs_core_redo.au", "CoreInput")
    results = driver.run([(values, 65) for _, values, _ in rows])
    for (label, values, expected), result in zip(rows, results):
        sector = b"".join(word.to_bytes(8, "little") for word in result[1:])
        harness.require(sector == expected, f"{label}: sector differs from Linux golden or required zero")
        if values.get("encode"):
            yield label, "encoded " + ("Linux payload" if any(sector) else "zero")
        else:
            yield label, driver.name("XfsCoreRedoStatus", result[0]) + " " + ("Linux sector" if any(sector) else "zero")


if __name__ == "__main__":
    harness.main("xfs_core_redo", describe)
