#!/usr/bin/env python3
"""fs.xfs_file sector planning and reads over historical and synthetic inline inodes.

fixtures/xfs-file holds mkfs-produced superblock, root, inode and extent slices
with their file payloads. Every mutated inode is a synthetic, CRC-repaired input.
Expected results are golden; historical sparse reads are also checked directly
against the preserved sparse.txt payload.
"""

from __future__ import annotations

import hashlib

import harness
from harness import require
from xfs_inputs import be, change, hex_fixture, set_fields

RESERVED = (1 << 52) - (1 << 17)
CAPACITY = 655360
PLAN, READ, FABRICATED_REPORT, FABRICATED_COORDINATE, INDEXED = range(5)
STATUSES = ("ready", "end", "invalid_index", "geometry_rejected", "source_too_small", "unsupported_profile")
STATUSES += ("invalid_inode", "invalid_extent")
HASHES = {
    "superblock.hex": "b3ce9d495c5f91596385c4481322b09a684437560897967416ecb5069e29f237",
    "root.hex": "4d1bb74d3d1d1c4fb95f4720dd841a94a1f81d19c02d3f7700df172efb9cdcad",
    "written-inode.hex": "39858ab68e2df643a9d7133895df019cc56efc2a0cea7ab57166571620be9029",
    "written-extent-0.hex": "a85a602f970ca9c8e1874782e76d83ae0d884f6e62367e6d21daf9bbf3dd4031",
    "written.txt": "1e245b1841f9c93c29c90b553e41e65671773b921d12ca65345f6b3fd6fca5ea",
    "empty-inode.hex": "550564d66df85ad33f66233ca7de896107d67cd7ffb533cf59e8fdfe6cbd5730",
    "reserve-inode.hex": "bb008f52eb956e5bb673fef166d65eb32e9c8d1f7668f7eab11d7a24631877b2",
    "sparse-inode.hex": "7c0d06f21fce090fdb1e3f8d831bde1edb6a4717aeadb354c7f5bfc761061bd8",
    "sparse-extent-0.hex": "e89a3442796c7d6c6e06cb864c88bcdc15211bdf94ce92b0da0fe8632be1217e",
    "sparse-extent-1.hex": "de8e46fa8d1af912fc165c6b741076fbf44b7e8a9f2b7f2c65b88b883cae64ae",
    "sparse-extent-2.hex": "01bb7d9e1469459d109dd542b3bb8b57be1e8d6a1e5a35906337f231e10314df",
    "sparse.txt": "0b3fbe758f5cb8d857ebd00e0cd368f2d31634cfa79d709900fc971ceef1fbb9",
}


def fixture(name):
    if name.endswith(".hex"):
        return hex_fixture("xfs-file", name, HASHES[name])
    data = (harness.ROOT / "fixtures/xfs-file" / name).read_bytes()
    require(hashlib.sha256(data).hexdigest() == HASHES[name], "fixture identity: " + name)
    return data


def set_inode(data, *fields, repair=True):
    return set_fields(data, *fields, crc=100 if repair else None)


def extent(data, start=24, count=5, offset=0, unwritten=False, block_bytes=4096, size=None):
    record = (int(unwritten) << 127) | (offset << 73) | (start << 21) | count
    return set_inode(data, (176, 16, record), (64, 8, count), (56, 8, count * block_bytes if size is None else size))


def real_lba(physical, sb):
    """First LBA of encoded filesystem block `physical` under superblock `sb` (input construction)."""
    ag, local = divmod(physical, 1 << sb[124])
    return (ag * be(sb, 84, 4) + local) * be(sb, 4, 4) // 512


def plan_case(label, sb, inode, number=131, index=0, capacity=CAPACITY):
    values = dict(operation=PLAN, number=number, index=index, capacity=capacity)
    return label, {**values, **files(sb, inode)}, 11


def read_case(label, sb, inode, window, index, base, number=131, capacity=CAPACITY, empty=False, payload=None):
    values = dict(operation=READ, number=number, index=index, capacity=capacity, base=base)
    values.update(window_offset=len(window) if empty else 0, window_length=0 if empty else len(window))
    values.update(harness.spread("window", window, 8))
    return label, {**values, **files(sb, inode), "payload": payload, "window": window}, 66


def files(sb, inode):
    values = dict(sb_length=len(sb), inode_length=len(inode))
    return {**values, **harness.spread("sb", sb, 2), **harness.spread("inode", inode, 2)}


def plan_cases(sb, inode):
    yield plan_case("actual written PREALLOC NREXT64 inode", sb, inode)
    for index in (-9223372036854775808, -1, 0, 1, 32, 33, 34, 35, 9223372036854775807):
        yield plan_case(f"index {index}", sb, inode, index=index)
    for capacity in (0, 1, CAPACITY - 1, CAPACITY, CAPACITY + 1, (1 << 63), (1 << 64) - 1):
        yield plan_case(f"capacity {capacity}", sb, inode, capacity=capacity)
    for number in (0, 1, 7, 8, 128, 131, 262144, 0xFFFFFFFF, 1 << 32, (1 << 64) - 1):
        yield plan_case(f"inode number {number}", sb, inode, number=number)
    for length in (1, 511, 513):
        yield plan_case(f"superblock length {length}", (sb * 2)[:length], inode)
        yield plan_case(f"inode length {length}", sb, (inode * 2)[:length])
    for offset in (0, 24, 100, 103, 175, 176, 191, 511):
        bad = bytearray(inode)
        bad[offset] ^= 1
        yield plan_case(f"unrepaired inode byte {offset}", sb, bytes(bad))
    for offset, length, value in (
        (0, 2, 0),
        (4, 1, 2),
        (152, 8, 132),
        (160, 1, 0),
        (120, 8, 1),
        (120, 8, 1 << 63),
        (90, 2, 1),
        (90, 2, 0x8000),
        (2, 2, 0x41ED),
        (5, 1, 1),
        (5, 1, 3),
        (82, 1, 1),
        (83, 1, 1),
        (6, 2, 1),
        (16, 4, 0),
        (16, 4, 0x80000000),
        (16, 4, 0xFFFFFFFF),
        (72, 4, 1),
        (76, 4, 1),
        (80, 2, 1),
        (84, 4, 1),
        (88, 2, 1),
        (96, 4, 0),
        (128, 4, 1),
        (132, 1, 1),
        (143, 1, 1),
        (24, 8, 0),
        (24, 8, 2),
        (24, 8, 21),
        (24, 8, 22),
        (24, 8, (1 << 64) - 1),
        (56, 8, 0),
        (56, 8, (1 << 63) - 1),
        (56, 8, 1 << 63),
        (56, 8, (1 << 64) - 1),
        (64, 8, 4),
        (64, 8, (1 << 64) - 1),
    ):
        yield plan_case(f"field {offset}:{length}={value}", sb, set_inode(inode, (offset, length, value)))
    for flags in (0, 8, 16, 24):
        changed = set_inode(inode, (120, 8, flags), (24, 8, 1 if flags & 16 else 0), (76, 4, 0 if flags & 16 else 1))
        yield plan_case(f"extent count layout flags2={flags}", sb, changed)
        yield plan_case(f"legacy PREALLOC optional flags2={flags}", sb, set_inode(changed, (90, 2, 0)))
        for count in (0, 2, 21, 22, 0xFFFFFFFF):
            yield plan_case(
                f"count layout flags2={flags}, count={count}",
                sb,
                set_inode(changed, (24, 8, count) if flags & 16 else (76, 4, count)),
            )
    for feature in (8, 32):
        yield plan_case(
            f"missing flag feature {feature}",
            change(sb, incompat=be(sb, 216, 4) & ~feature),
            inode,
        )
    for offset in (8, 20, 32, 92, 104, 112, 144, 192, 511):
        yield plan_case(
            f"CRC-covered opaque byte {offset}",
            sb,
            set_inode(inode, (offset, 1, inode[offset] ^ 0x55)),
        )
    for size in (1, 511, 512, 513, 4095, 4096, 4097, 17003, 20479, 20480):
        count = (size + 4095) // 4096
        changed = extent(inode, count=count, size=size)
        yield plan_case(f"file size {size}", sb, changed, index=(size - 1) // 512)
    for label, changed in (
        ("unwritten", extent(inode, unwritten=True)),
        ("hole at file start", extent(inode, offset=1)),
        ("maximum logical offset", extent(inode, offset=(1 << 54) - 1)),
        ("zero extent", extent(inode, count=0, size=1)),
        ("trailing allocation", extent(inode, count=6, size=17003)),
        ("missing allocation", extent(inode, count=4, size=17003)),
        ("second declared extent", set_inode(inode, (24, 8, 2), (192, 16, (29 << 21) | 1))),
    ):
        for index in (0, 34, -1):
            yield plan_case(f"{label}, request {index}", sb, changed, index=index)
    log = be(sb, 48, 8)
    log_count = be(sb, 96, 4)
    for start in (
        0,
        1,
        24,
        20475,
        20476,
        20480,
        32767,
        32768,
        32769,
        32792,
        log - 5,
        log - 4,
        log - 1,
        log,
        log + log_count - 1,
        log + log_count,
        (4 << sb[124]),
        RESERVED - 1,
        RESERVED,
        (1 << 52) - 1,
    ):
        yield plan_case(f"physical interval {start}+5", sb, extent(inode, start=start))
    middle_log_sb = change(sb, logstart=(2 << 15) + 100, logblocks=100)
    for start, count, accepted in (
        (95, 5, True),
        (96, 5, False),
        (100, 1, False),
        (199, 1, False),
        (199, 2, False),
        (200, 1, True),
    ):
        yield plan_case(
            f"exact internal-log interval {start}+{count}",
            middle_log_sb,
            extent(inode, start=(2 << 15) + start, count=count),
        )
    tail_sb = change(sb, dblocks=3 * 20480 + 64)
    for start in (59, 60, 63, 64, 20479):
        yield plan_case(f"last AG tail {start}+5", tail_sb, extent(inode, start=(3 << 15) + start), capacity=CAPACITY)
    large_sb = change(
        sb,
        blocksize=1024,
        blocklog=10,
        inopblock=2,
        inopblog=1,
        agblocks=1 << 30,
        agblklog=30,
        agcount=(1 << 22) + 1,
        dblocks=((1 << 22) + 1) * (1 << 30),
        rextsize=4,
        inoalignmt=32,
        logstart=1024,
        logblocks=64,
    )
    for start, count, accepted in (
        (RESERVED - 1, 1, True),
        (RESERVED - 5, 5, True),
        (RESERVED - 1, 2, False),
        (RESERVED - 5, 6, False),
        (RESERVED, 1, False),
        (RESERVED + 1, 1, False),
        ((1 << 52) - 1, 1, False),
    ):
        yield plan_case(
            f"reserved exact boundary {start}+{count}",
            large_sb,
            extent(inode, start=start, count=count, block_bytes=1024),
            capacity=(1 << 64) - 1,
        )
    maximum_sb = change(
        sb,
        blocksize=65536,
        blocklog=16,
        inopblock=128,
        inopblog=7,
        agblocks=1 << 24,
        agblklog=24,
        dblocks=4 << 24,
        rextsize=1,
        inoalignmt=0,
        spino_align=0,
        logstart=(2 << 24) + 100,
        logblocks=64,
    )
    maximum_count = (1 << 21) - 1
    maximum_inode = extent(inode, count=maximum_count, block_bytes=65536)
    maximum_index = maximum_count * 128 - 1
    yield plan_case(
        "maximum block count and 64KiB block size",
        maximum_sb,
        maximum_inode,
        index=maximum_index,
        capacity=(1 << 64) - 1,
    )
    yield plan_case(
        "maximum supported file end",
        maximum_sb,
        maximum_inode,
        index=maximum_index + 1,
        capacity=(1 << 64) - 1,
    )
    ag_inode = (1 << 18) + 131
    yield plan_case("nonzero AG inode address", sb, set_inode(inode, (152, 8, ag_inode)), number=ag_inode)
    inode1024 = change(sb, inodesize=1024, inodelog=10, inopblock=4, inopblog=2, inoalignmt=16)
    yield plan_case("valid excluded inode size", inode1024, inode)
    bad_inode = set_inode(inode, (100, 4, 0), repair=False)
    for index in (-1, 34, 9223372036854775807):
        yield plan_case("checksum before index", sb, bad_inode, index=index)
    yield plan_case(
        "geometry before capacity",
        change(sb, blocksize=3),
        inode,
        capacity=0,
    )
    yield plan_case("capacity before inode", sb, bad_inode, capacity=0)


def read_cases(sb, inode, data):
    for index in range(34):
        start = index // 8 * 4096
        yield read_case(f"actual file sector {index}", sb, inode, data[start : start + 4096], index, 192 + start // 512)
    for index in (0, 7, 8, 33):
        yield read_case(
            f"exact one-sector window {index}", sb, inode, data[index * 512 : (index + 1) * 512], index, 192 + index
        )
    nonzero_tail = data[16384 : 16896 + 107] + bytes([0xA5]) * (4096 - 512 - 107)
    yield read_case("synthetic nonzero final allocation tail is zeroed", sb, inode, nonzero_tail, 33, 224)
    for size in (1, 511, 512, 513, 4096):
        yield read_case(f"input window size {size}", sb, inode, data[:size], 0, 192)
    yield read_case("empty public subspan window", sb, inode, data[:512], 0, 192, empty=True)
    for base in (0, 191, 193, (1 << 63) - 1, 1 << 63, (1 << 64) - 1):
        yield read_case(f"window base {base}", sb, inode, data[:512], 0, base)
    for index in (-9223372036854775808, -1, 34, 35, 9223372036854775807):
        yield read_case(f"read invalid/end index {index}", sb, inode, data[:512], index, 192)
    large_sb = change(
        sb,
        blocksize=1024,
        blocklog=10,
        inopblock=2,
        inopblog=1,
        agblocks=1 << 30,
        agblklog=30,
        agcount=(1 << 22) + 1,
        dblocks=((1 << 22) + 1) * (1 << 30),
        rextsize=4,
        inoalignmt=32,
        logstart=1024,
        logblocks=64,
    )
    high_inode = extent(inode, start=RESERVED - 1, count=1, block_bytes=1024)
    yield read_case(
        "synthetic high-LBA actual window read",
        large_sb,
        high_inode,
        data[:512],
        1,
        (RESERVED - 1) * 2 + 1,
        capacity=(1 << 64) - 1,
    )
    near_u64_sb = change(
        sb,
        agblocks=1 << 28,
        agblklog=28,
        agcount=1 << 24,
        dblocks=(1 << 52) - 1,
        logstart=1024,
        logblocks=64,
    )
    near_u64_inode = extent(inode, start=RESERVED - 1, count=1)
    yield read_case(
        "synthetic near-u64 data-byte bound read",
        near_u64_sb,
        near_u64_inode,
        data[:512],
        7,
        RESERVED * 8 - 1,
        capacity=(1 << 64) - 1,
    )
    maximum_sb = change(
        sb,
        blocksize=65536,
        blocklog=16,
        inopblock=128,
        inopblog=7,
        agblocks=1 << 24,
        agblklog=24,
        dblocks=4 << 24,
        rextsize=1,
        inoalignmt=0,
        spino_align=0,
        logstart=(2 << 24) + 100,
        logblocks=64,
    )
    maximum_count = (1 << 21) - 1
    maximum_inode = extent(inode, count=maximum_count, block_bytes=65536)
    maximum_index = maximum_count * 128 - 1
    yield read_case(
        "synthetic maximum-size final sector read",
        maximum_sb,
        maximum_inode,
        data[:512],
        maximum_index,
        24 * 128 + maximum_index,
        capacity=(1 << 64) - 1,
    )
    yield read_case("end before invalid window", sb, inode, data[:1], 34, 192)
    yield read_case("invalid inode read is masked", sb, set_inode(inode, (152, 8, 132)), data[:512], 0, 192)
    yield read_case("capacity read is masked", sb, inode, data[:512], 0, 192, capacity=1)
    yield read_case("unwritten read is not data", sb, extent(inode, unwritten=True), data[:512], 0, 192)


def inline_inode(inode, records, size, large_count=True):
    """Synthetic CRC-correct fork, never described as producer output."""
    require(len(records) <= 21, "synthetic records fit the fork")
    fork = bytearray(336)
    allocated = 0
    for index, (logical, physical, length, unwritten) in enumerate(records):
        require(0 <= logical < 1 << 54 and 0 <= physical < 1 << 52, "synthetic field widths")
        require(0 <= length < 1 << 21, "synthetic length width")
        record = (int(unwritten) << 127) | (logical << 73) | (physical << 21) | length
        fork[index * 16 : index * 16 + 16] = record.to_bytes(16, "big")
        allocated += length
    flags = be(inode, 120, 8) | 16 if large_count else be(inode, 120, 8) & ~16
    return set_inode(
        inode,
        (176, 336, int.from_bytes(fork, "big")),
        (24, 8, len(records) if large_count else 0),
        (76, 4, 0 if large_count else len(records)),
        (120, 8, flags),
        (56, 8, size),
        (64, 8, allocated),
    )


def historical_sparse_cases(sb):
    inode = fixture("sparse-inode.hex")
    payload = fixture("sparse.txt")
    samples = [fixture(f"sparse-extent-{index}.hex") for index in range(3)]
    rebuilt = bytearray(9 * 4096)
    for logical, sample in zip((1, 6, 8), samples):
        rebuilt[logical * 4096 : (logical + 1) * 4096] = sample
    require(len(payload) == 32769 and rebuilt[:32769] == payload, "complete historical sparse payload")
    for index in range(65):
        window, base = bytes([0xD9]), (1 << 64) - 1
        if index // 8 in (1, 6, 8):
            record = (1, 6, 8).index(index // 8)
            window, base = samples[record], (15, 29, 31)[record] * 8
        yield read_case(
            f"historical sparse full-payload sector {index}",
            sb,
            inode,
            window,
            index,
            base,
            number=134,
            payload=payload[index * 512 : (index + 1) * 512].ljust(512, b"\0"),
        )
    for index in (-1, 0, 7, 8, 15, 16, 47, 48, 55, 56, 63, 64, 65, 66):
        yield plan_case(f"historical sparse coordinate {index}", sb, inode, number=134, index=index)
    for name, number in (("empty", 132), ("reserve", 133)):
        for index in (-1, 0, 1):
            yield plan_case(
                f"historical {name} empty EOF remains unsupported {index}",
                sb,
                fixture(name + "-inode.hex"),
                number=number,
                index=index,
            )


def inline_cases(sb, inode):
    poison = bytes((index * 19 + 7) % 256 for index in range(4096))
    # This independent descriptor enumeration fixes the expected mapping before
    # the packed inode is passed through the separate bigint decoding model.
    profiles = (
        ("adjacent fragmented", [(0, 24, 1, False), (1, 40, 2, False), (3, 32790, 1, False)], 4 * 4096 - 17),
        ("mixed sparse", [(1, 24, 2, False), (4, 40, 1, True), (6, 32790, 2, False), (9, 60, 1, True)], 40960 - 73),
        ("trailing hole", [(0, 24, 1, False), (4, 40, 1, True)], 12 * 4096 - 13),
        ("all unwritten", [(0, 24, 2, True)], 8191),
        ("all holes", [], 4097),
    )
    for title, records, size in profiles:
        for large_count in (False, True):
            changed = inline_inode(inode, records, size, large_count)
            indices = sorted(
                {
                    0,
                    (size - 1) // 512,
                    *(point for record in records for point in (record[0] * 8, (record[0] + record[2]) * 8 - 1)),
                }
            )
            indices += [index for index in range((size + 511) // 512) if index % 8 in (0, 7)]
            for index in sorted(set(indices)):
                logical, intra = divmod(index, 8)
                selected = [record for record in records if logical in range(record[0], record[0] + record[2])]
                kind, lba = "hole", 0
                if selected:
                    offset, physical, _, unwritten = selected[0]
                    kind = "unwritten" if unwritten else "written"
                    if not unwritten:
                        lba = real_lba(physical, sb) + (logical - offset) * 8 + intra
                label = f"synthetic {title}, large_count={large_count}, sector {index}"
                yield plan_case(label, sb, changed, index=index)
                yield read_case(label, sb, changed, poison[:512], index, lba)
            end = (size + 511) // 512
            for index in (-1, end, end + 1):
                yield plan_case(f"synthetic {title} index endpoint {index}, {large_count}", sb, changed, index=index)
    for count in (0, 1, 2, 21):
        records = [(index * 2, 24 + index, 1, bool(index % 2)) for index in range(count)]
        for large_count in (False, True):
            changed = inline_inode(inode, records, max(1, count * 8192 - 1), large_count)
            for index in (0, max(0, count * 16 - 2), max(0, count * 16 - 1)):
                yield plan_case(f"synthetic count capacity {count}/{large_count}/{index}", sb, changed, index=index)
            if count:
                yield plan_case(
                    f"synthetic declared-last record {count}/{large_count}", sb, changed, index=(count - 1) * 16
                )
            excessive = set_inode(changed, (24, 8, 22) if large_count else (76, 4, 22))
            yield plan_case("synthetic overfull fork", sb, excessive)
    for title, records, issue in (
        ("overlap", [(0, 24, 2, False), (1, 40, 1, False)], "file_offset"),
        ("reverse", [(2, 24, 1, False), (0, 40, 1, False)], "file_offset"),
        ("duplicate", [(0, 24, 1, False), (0, 40, 1, True)], "file_offset"),
        ("zero later length", [(0, 24, 1, False), (2, 40, 0, True)], "block_count"),
        ("last reserved", [(0, 24, 1, False), (2, RESERVED, 1, True)], "extent_address"),
        ("last encoded gap", [(0, 24, 1, False), (2, 20480, 1, False)], "extent_address"),
        ("last AG header", [(0, 24, 1, False), (2, 32768, 1, True)], "extent_address"),
    ):
        changed = inline_inode(inode, records, 4 * 4096)
        for index in (0, 8, 16, 31, 32, -1):
            yield plan_case(
                f"synthetic all-record validation {title}, index {index}",
                sb,
                changed,
                index=index,
            )
        yield read_case(f"synthetic bad later metadata masks zero target: {title}", sb, changed, poison[:1], 8, 0)
    for unwritten in (False, True):
        # Physical range checks must still run on a later unwritten record even
        # while requesting valid written, hole, unwritten, end or invalid indices.
        for physical, count in ((0, 1), (32768, 1), (20479, 2), (20480, 1), (RESERVED - 1, 2), (RESERVED, 1)):
            records = [(0, 24, 1, False), (2, 40, 1, True), (4, physical, count, unwritten)]
            changed = inline_inode(inode, records, 7 * 4096)
            for index in (0, 8, 16, 56, -1):
                yield plan_case(
                    f"synthetic later physical range {physical}+{count}, unwritten={unwritten}, request={index}",
                    sb,
                    changed,
                    index=index,
                )
        changed = inline_inode(inode, [(0, 24, 1, False), (1, 40, 1, unwritten)], 4096)
        for index in (0, 8, -1):
            yield plan_case(
                f"synthetic trailing allocation {unwritten}/{index}",
                sb,
                changed,
                index=index,
            )
        short_tail = inline_inode(inode, [(0, 24, 1, unwritten)], 4097)
        yield read_case("synthetic last short hole", sb, short_tail, poison[:1], 8, 0)
    for allocated in (0, 1, 3, (1 << 64) - 1):
        changed = inline_inode(inode, [(0, 24, 1, False), (2, 40, 1, True)], 4 * 4096)
        changed = set_inode(changed, (64, 8, allocated))
        yield plan_case("synthetic allocation sum mismatch", sb, changed)
    records21 = [(index, 24 + index, 1, False) for index in range(21)]
    changed21 = inline_inode(inode, records21, 21 * 4096)
    for physical in (0, RESERVED):
        record = (20 << 73) | (physical << 21) | 1
        corrupt21 = set_inode(changed21, (496, 16, record))
        yield plan_case(
            "synthetic last possible record rejected before first read",
            sb,
            corrupt21,
        )
    for kind, records in (("hole", []), ("unwritten", [(0, 24, 1, True)])):
        zero_inode = inline_inode(inode, records, 513)
        for length in (1, 511, 512, 513, 4096):
            for index in (0, 1):
                yield read_case(
                    f"synthetic {kind} ignores poisoned window {length}/{index}",
                    sb,
                    zero_inode,
                    poison[:length],
                    index,
                    (1 << 64) - 1,
                )
        yield read_case(f"synthetic {kind} ignores empty window", sb, zero_inode, poison[:1], 0, 0, empty=True)
        for index in (2, 3, -1):
            yield read_case(f"synthetic {kind} never extends EOF {index}", sb, zero_inode, poison[:1], index, 0)
    maximum_size = (1 << 63) - 1
    all_holes = inline_inode(inode, [], maximum_size)
    for index in (0, (maximum_size - 1) // 512, (maximum_size + 511) // 512, (1 << 63) - 1):
        yield plan_case("synthetic i64 maximum sparse file", sb, all_holes, index=index)
    yield read_case(
        "synthetic i64 maximum sparse final sector",
        sb,
        all_holes,
        poison[:1],
        (maximum_size - 1) // 512,
        0,
    )
    far = (maximum_size - 1) // 4096
    for unwritten in (False, True):
        far_inode = inline_inode(inode, [(far, 24, 1, unwritten)], maximum_size)
        yield plan_case("synthetic far sparse extent near signed EOF", sb, far_inode, index=(maximum_size - 1) // 512)
        yield read_case(
            "synthetic far sparse final mapped sector",
            sb,
            far_inode,
            poison[:512],
            (maximum_size - 1) // 512,
            199,
        )
        maximum_offset = inline_inode(inode, [((1 << 54) - 1, 24, 1, unwritten)], maximum_size)
        yield plan_case(
            "synthetic maximum encoded logical offset never scaled",
            sb,
            maximum_offset,
        )
    log_sb = change(sb, logstart=(2 << 15) + 100, logblocks=100)
    tail_sb = change(sb, dblocks=3 * 20480 + 64)
    for changed_sb, title, intervals in (
        (log_sb, "log", [(95, 5, True), (96, 5, False), (199, 1, False), (200, 1, True)]),
        (tail_sb, "last AG", [(59, 5, True), (60, 5, False), (63, 1, True), (64, 1, False)]),
    ):
        ag = 2 if title == "log" else 3
        for start, length, accepted in intervals:
            changed = inline_inode(inode, [(0, 24, 1, False), (2, (ag << 15) + start, length, True)], 8 * 4096)
            for index in (0, 16):
                yield plan_case(
                    f"synthetic later unwritten {title} {start}+{length}/{index}",
                    changed_sb,
                    changed,
                    index=index,
                )
    maximal_sb = change(
        sb,
        blocksize=65536,
        blocklog=16,
        inopblock=128,
        inopblog=7,
        agblocks=1 << 24,
        agblklog=24,
        dblocks=4 << 24,
        rextsize=1,
        inoalignmt=0,
        spino_align=0,
        logstart=(2 << 24) + 100,
        logblocks=64,
    )
    longest = (1 << 21) - 1
    full_records = [
        (index * longest, ((0, 1, 3)[index // 7] << 24) + 24 + index % 7 * longest, longest, bool(index % 2))
        for index in range(21)
    ]
    full_size = 21 * longest * 65536
    full_inode = inline_inode(inode, full_records, full_size)
    yield plan_case(
        "synthetic maximum count in all21 records",
        maximal_sb,
        full_inode,
        index=full_size // 512 - 1,
        capacity=(1 << 64) - 1,
    )
    yield read_case(
        "synthetic all21 maximum records final read",
        maximal_sb,
        full_inode,
        poison[:512],
        full_size // 512 - 1,
        ((3 << 24) + 24 + 7 * longest) * 128 - 1,
        capacity=(1 << 64) - 1,
    )
    later_bad = inline_inode(inode, [(4, 24, 1, True), (6, RESERVED, 1, True)], 4096)
    yield plan_case(
        "synthetic malformed later record outranks earlier trailing allocation",
        sb,
        later_bad,
    )


def report_cases():
    for code, status in enumerate(STATUSES):
        yield f"fabricated masking {status}", dict(operation=FABRICATED_REPORT, selector=code), 15
    for code, kind in enumerate(("none", "written", "hole", "unwritten")):
        yield f"fabricated coordinate kind masking {kind}", dict(operation=FABRICATED_COORDINATE, selector=code), 3


def indexed_root_case(sb, root, inode, data):
    values = dict(operation=INDEXED, capacity=655360, base=192, window_length=512)
    values.update(sb_length=len(sb), inode_length=len(inode))
    values.update(sb0=sb, root0=root, **harness.spread("inode", inode, 2), **harness.spread("window", data[:512], 8))
    return "real indexed-root entry to actual first file sector", {**values, "window": data[:512]}, 68


def cases():
    sb, inode, root = (fixture(name) for name in ("superblock.hex", "written-inode.hex", "root.hex"))
    data = fixture("written-extent-0.hex")
    payload = fixture("written.txt")
    require(len(payload) == 17003 and len(data) == 20480 and data[:17003] == payload, "complete actual payload")
    return [
        *plan_cases(sb, inode),
        *read_cases(sb, inode, data),
        *report_cases(),
        *historical_sparse_cases(sb),
        *inline_cases(sb, inode),
        indexed_root_case(sb, root, inode, data),
    ]


def format_result(driver, values, observed):
    operation = values["operation"]
    status = lambda code: driver.name("XfsFileStatus", code)  # noqa: E731
    kind = lambda code: driver.name("XfsFileSectorKind", code)  # noqa: E731
    check = lambda code: "ok" if code == 1 else f"check-failed-{code}"  # noqa: E731
    if operation == FABRICATED_COORDINATE:
        return " ".join([kind(observed[0]), *map(str, observed[1:])])
    if operation in (PLAN, FABRICATED_REPORT):
        words = [status(observed[0]), driver.name("XfsFileIssue", observed[1]), *map(str, observed[2:7])]
        words += [kind(observed[7]), str(observed[8]), str(observed[9])]
        tail = [check(observed[10])] if operation == PLAN else list(map(str, observed[10:]))
        return " ".join(words + tail)
    if operation == INDEXED:
        head, observed = observed[:3], observed[3:]
    sector = b"".join(word.to_bytes(8, "little") for word in observed[1:65])
    if values.get("payload") is not None:
        require(sector == values["payload"], "historical sparse sector differs from the preserved payload")
    words = [driver.name("SectorIoStatus", observed[0]), harness.describe_sector(values["window"], sector)]
    if operation == INDEXED:
        return " ".join(["found" if head[0] == 1 else "missing", str(head[1]), str(head[2]), *words])
    return " ".join(words + [check(observed[65])])


PREFIX = "module test; import std.binary; import std.binary_buffer; import storage.sector; import storage.block_io;"
PREFIX += " import storage.sector_window; import fs.xfs_file; auto test() -> u64 {"
PREFIX += "const builtin::array<u8, 1> data = {0u8};"
PREFIX += "const storage::SectorGeometry source = storage::SectorGeometry(1u64, false);"
PREFIX += "const fs::XfsFileRequest request = fs::XfsFileRequest(131u64, 0);"
REJECTIONS = (
    ("private request field", "return request._inode;"),
    ("closed kind argument", "const fs::XfsFileSector wrong = fs::XfsFileSector(0u64, 1u64, 512u64); return 0u64;"),
    (
        "exact u64 coordinate",
        "const fs::XfsFileSector wrong = fs::XfsFileSector(fs::XfsFileSectorKind::written, 1, 512u64); return 0u64;",
    ),
    ("closed status enum", "return u64(fs::XfsFileStatus::ready);"),
    (
        "private failure helper",
        "const fs::XfsFileReport result = fs::xf_failure(fs::XfsFileStatus::ready, fs::XfsFileIssue::none);"
        " return 0u64;",
    ),
)


def describe(compiler, directory):
    driver = harness.Driver(compiler, directory, harness.HERE / "xfs_file.au", "FileInput")
    corpus = cases()
    record = lambda values: {k: v for k, v in values.items() if k not in ("payload", "window")}  # noqa: E731
    observed = driver.run([(record(values), slots) for _, values, slots in corpus])
    for (label, values, _), result in zip(corpus, observed):
        yield label, format_result(driver, values, result)
    sources = [(label, PREFIX + body + "}") for label, body in REJECTIONS]
    yield from harness.rejections(compiler, directory, sources)


if __name__ == "__main__":
    harness.main("xfs_file", describe)
