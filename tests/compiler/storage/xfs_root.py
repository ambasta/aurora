#!/usr/bin/env python3
"""fs.xfs_root lookup, indexed entries and copied reports over preserved root slices.

The four canonical 512-byte slices are recovered mkfs output (fixtures/xfs-root);
all mutations are synthetic, CRC-repaired inputs. Expected results are golden.
"""

from __future__ import annotations

import random

import harness
from xfs_inputs import change, fix_inode, root_fixture, set_fields, shortform

LOOKUP, ENTRY, FABRICATED_LOOKUP, FABRICATED_ENTRY = range(4)
LOOKUP_STATUSES = ("found", "not_found", "geometry_rejected", "unsupported_profile", "invalid_query")
LOOKUP_STATUSES += ("invalid_inode", "invalid_directory")
ENTRY_STATUSES = ("found", "end", "invalid_index", "geometry_rejected", "unsupported_profile", "invalid_inode")
ENTRY_STATUSES += ("invalid_directory",)


def lookup_corpus():
    """(label, superblock, inode, query): real lookups plus every validation branch."""
    sb, ino = root_fixture("named-superblock.hex"), root_fixture("named-root.hex")
    empty_sb, empty = root_fixture("empty-superblock.hex"), root_fixture("empty-root.hex")
    out = []

    def add(label, b=ino, s=sb, q=b"alpha"):
        out.append((label, s, b, q))

    def setv(data, p, n, v, crc=100):
        return set_fields(data, (p, n, v), crc=crc)

    add("real alpha")
    add("real docs", q=b"docs")
    add("real absent", q=b"none")
    add("real case sensitive", q=b"Alpha")
    add("real empty", empty, empty_sb)
    for n in [1, 511, 513]:
        add(f"inode length{n}", (ino + b"X")[:n])
    for n in [1, 511, 513]:
        add(f"sb length{n}", s=(sb + b"X")[:n])
    for q in [b".", b"..", b"a/b", b"\0", b"X" * 256]:
        add("bad query" + q[:8].hex(), q=q)
    for p in [0, 5, 100, 103, 104, 175, 176, 511]:
        x = bytearray(ino)
        x[p] ^= 1
        add(f"unrepaired byte{p}", bytes(x))
    for p, n, vals in [
        (0, 2, [0, 0x494F]),
        (4, 1, [0, 2, 4]),
        (152, 8, [0, 129, 2**63]),
        (160, 1, [255]),
        (120, 8, [0, 8, 16, 1, 2, 4, 32, 2**63]),
        (2, 2, [0, 0x81ED, 0x4FFF]),
        (5, 1, [0, 2, 3]),
        (6, 2, [1]),
        (16, 4, [0, 1, 0x7FFFFFFF, 0x80000000]),
        (24, 8, [1]),
        (64, 8, [1]),
        (72, 4, [1]),
        (76, 4, [1]),
        (80, 2, [1]),
        (82, 1, [1]),
        (83, 1, [0, 1]),
        (84, 4, [1]),
        (88, 2, [1]),
        (90, 2, [1]),
        (96, 4, [0]),
        (128, 4, [1]),
        (132, 1, [1]),
        (143, 1, [1]),
        (56, 8, [0, 5, 6, 30, 32, 336, 337, 2**63]),
        (177, 1, [1, 255]),
        (176, 1, [0, 1, 3, 16, 17, 255]),
        (178, 4, [0, 129]),
        (182, 1, [0, 1, 255]),
        (183, 2, [0, 95, 97, 104, 120, 65528]),
        (190, 1, [0, 8, 9, 255]),
        (191, 4, [0, 1, 128, 131, 0xFFFFFFFF]),
        (195, 1, [0, 255]),
    ]:
        for v in vals:
            add(f"field {p}:{n}={v}", setv(ino, p, n, v))
    for q in [b"\xff", b"\xc0\x80", b"a" * 255]:
        add("raw name " + q[:5].hex(), shortform(ino, [(q, 131, 1, 96)]), q=q)
    for q in [b".", b"..", b"/", b"\0"]:
        add("invalid entry " + q.hex(), shortform(ino, [(q, 131, 1, 96)]))
    for ft in range(9):
        add(f"raw type{ft}", shortform(ino, [(b"alpha", 131, ft, 96)]))
    add("permitted first gap", shortform(ino, [(b"alpha", 131, 1, 104), (b"docs", 132, 2, 144)]))
    add("overlap later", shortform(ino, [(b"alpha", 131, 1, 96), (b"docs", 132, 2, 112)]))
    add("duplicate", shortform(ino, [(b"alpha", 131, 1, 96), (b"alpha", 132, 2, 120)]))
    add("later bad name rejects early match", shortform(ino, [(b"alpha", 131, 1, 96), (b"a/b", 132, 2, 120)]))
    add("last footprint exact", shortform(ino, [(b"alpha", 131, 1, 4040)]))
    add("last footprint exceeds", shortform(ino, [(b"alpha", 131, 1, 4048)]))
    entries = [(bytes([65 + i]), 131 + i, 1, 96 + i * 16) for i in range(16)]
    add("sixteen entries", shortform(ino, entries), q=b"P")
    for flags in [0, 8, 16, 24]:
        for features in [3, 11, 35, 43]:
            add(f"flags{flags}/features{features}", setv(ino, 120, 8, flags), setv(sb, 216, 4, features, 224))
    add("single-dirblock profile", s=setv(sb, 192, 1, 1, 224))
    large = change(sb, inodesize=1024, inodelog=10, inopblock=4, inopblog=2, inoalignmt=16)
    add("1024 inode profile", s=large)
    for root in [0, 1, 7, 8, 127, 128, 129, (1 << 18) + 128, (4 << 18), 0xFFFFFFFF, 1 << 32, 2**64 - 1]:
        s = setv(sb, 56, 8, root, 224)
        b = setv(ino, 152, 8, root)
        if root <= 0xFFFFFFFF:
            b = setv(b, 178, 4, root)
        add(f"root address{root}", b, s)
    s = change(sb, agblocks=32767, agblklog=15, dblocks=4 * 32767, logstart=65543)
    for root in [(2 << 18) + 128, (2 << 18) + (32767 << 3), (3 << 18) + 128]:
        b = setv(setv(ino, 152, 8, root), 178, 4, root)
        add(f"nonpower AG root{root}", b, setv(s, 56, 8, root, 224))
    s = change(sb, dblocks=3 * 32768 + 64, logstart=65543)
    for root in [(3 << 18) + (63 << 3) + 7, (3 << 18) + (64 << 3)]:
        b = setv(setv(ino, 152, 8, root), 178, 4, root)
        add(f"partial final AG root{root}", b, setv(s, 56, 8, root, 224))
    rng = random.Random(23004)
    for i in range(40):
        b = bytearray(ino)
        p = rng.randrange(512)
        b[p] = rng.randrange(256)
        add(f"seed23004 mutation{i}@{p}", fix_inode(b))
    harness.require(len(out) == 203, "complete root lookup corpus")
    return out


def entry_indices(inode):
    """Every index from -1 through one past the declared entry count (at least two)."""
    declared = inode[176] if len(inode) == 512 and inode[176] <= 16 else 2
    return range(-1, max(2, declared) + 2)


def cases():
    """(label, record values, slot count) for every native case."""
    corpus = lookup_corpus()
    for label, sb, inode, query in corpus:
        yield label, inputs(LOOKUP, sb, inode, query=query), 11
    for label, sb, inode, _ in corpus:
        for index in entry_indices(inode):
            yield f"{label} index {index}", inputs(ENTRY, sb, inode, index=index), 12
    sb, inode = root_fixture("named-superblock.hex"), root_fixture("named-root.hex")
    for index in (-(1 << 63), (1 << 63) - 1):
        yield f"signed endpoint index {index}", inputs(ENTRY, sb, inode, index=index), 12
    # A late malformed record or trailing data rejects even an early entry, the
    # end marker or a too-large index: none can bypass complete validation.
    for label, damaged in (
        ("late malformed entry", shortform(inode, [(b"alpha", 131, 1, 96), (b"a/b", 132, 2, 120)])),
        ("trailing payload", set_fields(inode, (56, 8, 32))),
        ("duplicate second name", shortform(inode, [(b"alpha", 131, 1, 96), (b"alpha", 132, 2, 120)])),
    ):
        for index in (0, 2, 3, (1 << 63) - 1):
            yield f"{label} index {index}", inputs(ENTRY, sb, damaged, index=index), 12
    for code, status in enumerate(LOOKUP_STATUSES):
        yield f"fabricated lookup report {status}", {"operation": FABRICATED_LOOKUP, "status": code}, 14
    for code, status in enumerate(ENTRY_STATUSES):
        yield f"fabricated entry report {status}", {"operation": FABRICATED_ENTRY, "status": code}, 14


def inputs(operation, sb, inode, query=b"", index=0):
    values = {"operation": operation, "index": index, "query0": query}
    values.update(sb_length=len(sb), inode_length=len(inode), query_length=len(query))
    return {**values, **harness.spread("sb", sb, 2), **harness.spread("inode", inode, 2)}


def format_result(driver, operation, observed):
    """status issue, then every scalar leaf; the final slot must report a passed self-check."""
    check = {LOOKUP: 10, ENTRY: 11}.get(operation)
    words = [str(value) for value in observed]
    if operation in (LOOKUP, FABRICATED_LOOKUP):
        words[0] = driver.name("XfsRootStatus", observed[0])
    else:
        words[0] = driver.name("XfsRootEntryStatus", observed[0])
    words[1] = driver.name("XfsRootIssue", observed[1])
    if check is not None:
        words[check] = "ok" if observed[check] == 1 else f"check-failed-{observed[check]}"
    return " ".join(words)


ENTRY_PREFIX = "module test; import fs.xfs_root; auto test() -> u64 {"
ENTRY_PREFIX += "const fs::XfsRootEntry entry = fs::XfsRootEntry(1u64, 2u64, 3u64, 4u64);"
LOOKUP_PREFIX = "module root_lookup_test;import fs.xfs_root;\nauto answer()->u64{const array<u8,1> bytes={0u8};"
FACTS = "const fs::XfsRootFacts f=fs::XfsRootFacts(1u64,2u64,3u64,4u64,5u64);"
REJECTIONS = (
    ("private name coordinates", ENTRY_PREFIX + "return entry._name_offset;}"),
    ("private result field mutation", ENTRY_PREFIX + "entry._name_length = 0u64; return 0u64;}"),
    ("closed entry enum", ENTRY_PREFIX + "return u64(fs::XfsRootEntryStatus::found);}"),
    (
        "index exact signed type",
        ENTRY_PREFIX + "const array<u8, 1> data = {0u8};"
        "const fs::XfsRootEntryReport result = fs::entry_at_xfs_v5_512_root("
        "borrow_bytes(data), borrow_bytes(data), 0u64); return 0u64;}",
    ),
    ("private helper", LOOKUP_PREFIX + "return fs::xr_address(borrow_bytes(bytes),128u64);}"),
    (
        "wrong query type",
        LOOKUP_PREFIX + "const fs::XfsRootReport r="
        "fs::lookup_xfs_v5_512_root(borrow_bytes(bytes),borrow_bytes(bytes),1u64);return 0u64;}",
    ),
    ("closed enum conversion", LOOKUP_PREFIX + "return u64(fs::XfsRootStatus::found);}"),
    (
        "span result excluded by callable type surface",
        "module root_lookup_test;import fs.xfs_root;\n"
        "auto leak()->builtin::span<const u8>{const array<u8,1> bytes={0u8};return borrow_bytes(bytes);}",
    ),
)


def describe(compiler, directory):
    driver = harness.Driver(compiler, directory, harness.HERE / "xfs_root.au", "RootInput")
    corpus = list(cases())
    observed = driver.run([(values, slots) for _, values, slots in corpus])
    for (label, values, _), result in zip(corpus, observed):
        yield label, format_result(driver, values["operation"], result)
    yield from harness.rejections(compiler, directory, REJECTIONS)


if __name__ == "__main__":
    harness.main("xfs_root", describe)
