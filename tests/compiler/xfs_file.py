#!/usr/bin/env python3
"""Bounded written-file sectors from exact historical XFS bytes, with a bigint model."""

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import tempfile

import xfs_geometry as geometry
import xfs_root as root_model
from unsigned_oracle import Case, NativeRunner, Rejection, require


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures/xfs-file"
IMPORTS = (
    "std.binary",
    "std.binary_buffer",
    "storage.sector",
    "storage.block_io",
    "storage.sector_window",
    "fs.xfs_file",
)
FACTS = ("inode_number", "inode_lba", "size_bytes", "first_data_lba", "extent_blocks")
COORDINATES = ("source_lba", "valid_bytes")
RESERVED = (1 << 52) - (1 << 17)
CAPACITY = 655360
HASHES = {
    "superblock.hex": "b3ce9d495c5f91596385c4481322b09a684437560897967416ecb5069e29f237",
    "root.hex": "4d1bb74d3d1d1c4fb95f4720dd841a94a1f81d19c02d3f7700df172efb9cdcad",
    "written-inode.hex": "39858ab68e2df643a9d7133895df019cc56efc2a0cea7ab57166571620be9029",
    "written-extent-0.hex": "a85a602f970ca9c8e1874782e76d83ae0d884f6e62367e6d21daf9bbf3dd4031",
    "written.txt": "1e245b1841f9c93c29c90b553e41e65671773b921d12ca65345f6b3fd6fca5ea",
}


def fixture(name):
    transport = (FIXTURES / name).read_bytes()
    if name.endswith(".hex"):
        require(transport.endswith(b"\n") and transport.count(b"\n") == 1, "one-line canonical fixture")
        require(all(c in b"0123456789abcdef" for c in transport[:-1]), "lowercase canonical fixture")
        data = bytes.fromhex(transport.decode())
    else:
        data = transport
    require(hashlib.sha256(data).hexdigest() == HASHES[name], "fixture identity: " + name)
    return data


def be(data, offset, count):
    return int.from_bytes(data[offset : offset + count], "big")


def set_inode(data, *fields, repair=True):
    result = bytearray(data)
    for offset, count, value in fields:
        result[offset : offset + count] = value.to_bytes(count, "big")
    return root_model.fix(result) if repair else bytes(result)


def extent(data, start=24, count=5, offset=0, unwritten=False, block_bytes=4096, size=None):
    record = (int(unwritten) << 127) | (offset << 73) | (start << 21) | count
    return set_inode(data, (176, 16, record), (64, 8, count), (56, 8, count * block_bytes if size is None else size))


def address(sb, encoded, count):
    """Bigint half-open intervals, not the implementation's guarded arithmetic."""
    block_bytes, ag_blocks, ag_count, blocks = (be(sb, p, n) for p, n in ((4, 4), (84, 4), (88, 4), (8, 8)))
    stride = 2 ** sb[124]
    ag, local = divmod(encoded, stride)
    actual = min(ag_blocks, blocks - ag * ag_blocks)
    if not (0 < count and 0 <= encoded < encoded + count <= RESERVED):
        return 0
    if not (0 <= ag < ag_count and local * block_bytes >= 2048 and local + count <= actual):
        return 0
    start = (ag * ag_blocks + local) * block_bytes
    end = start + count * block_bytes
    log_ag, log_local = divmod(be(sb, 48, 8), stride)
    log_start = (log_ag * ag_blocks + log_local) * block_bytes
    log_end = log_start + be(sb, 96, 4) * block_bytes
    if max(start, log_start) < min(end, log_end):
        return 0
    require(0 <= start < end <= blocks * block_bytes <= (1 << 64) - 1, "model address bound")
    return start


@dataclass(frozen=True)
class Expected:
    status: str
    issue: str = "none"
    facts: tuple = (0,) * 5
    sector: tuple = (0, 0)


def oracle(sb, inode, number=131, index=0, capacity=CAPACITY):
    def failed(status, issue):
        return Expected(status, issue)

    if geometry.oracle(sb).status != "header_geometry_consistent":
        return failed("geometry_rejected", "geometry")
    if be(sb, 8, 8) * be(sb, 4, 4) > capacity * 512:
        return failed("source_too_small", "capacity")
    if be(sb, 104, 2) != 512:
        return failed("unsupported_profile", "inode_size")
    if number > 0xFFFFFFFF:
        return failed("unsupported_profile", "inode_address")
    slots = be(sb, 106, 2)
    inode_address = address(sb, number // slots, 1) if 1 <= number <= 0xFFFFFFFF else 0
    if not inode_address:
        return failed("invalid_inode", "inode_address")
    if len(inode) != 512:
        return failed("invalid_inode", "inode_length")
    if be(inode, 0, 2) != 0x494E:
        return failed("invalid_inode", "magic")
    if inode[4] != 3:
        return failed("unsupported_profile", "version")
    if root_model.fix(inode) != inode:
        return failed("invalid_inode", "checksum")
    if be(inode, 152, 8) != number or inode[160:176] != sb[32:48]:
        return failed("invalid_inode", "identity")
    flags, features = be(inode, 120, 8), be(sb, 216, 4)
    if flags & ~24 or flags & 8 and not features & 8 or flags & 16 and not features & 32:
        return failed("unsupported_profile", "flags")
    if be(inode, 90, 2) & ~2:
        return failed("unsupported_profile", "flags")
    if be(inode, 2, 2) & 0xF000 != 0x8000:
        return failed("unsupported_profile", "file_type")
    if inode[5] != 2:
        return failed("unsupported_profile", "file_format")
    if inode[82] or inode[83] != 2:
        return failed("unsupported_profile", "attribute_fork")
    if be(inode, 72, 4) or be(inode, 128, 4):
        return failed("unsupported_profile", "extent_hints")
    zero_fields = ((6, 2), (80, 2), (84, 6), (132, 12), (76, 4) if flags & 16 else (24, 8))
    if not 1 <= be(inode, 16, 4) <= 0x7FFFFFFF or be(inode, 96, 4) != 0xFFFFFFFF:
        return failed("invalid_inode", "core")
    if any(be(inode, p, n) for p, n in zero_fields):
        return failed("invalid_inode", "core")
    count = be(inode, 24, 8) if flags & 16 else be(inode, 76, 4)
    if count > 21:
        return failed("invalid_inode", "extent_count")
    if count != 1:
        return failed("unsupported_profile", "extent_count")
    size = be(inode, 56, 8)
    if size > (1 << 63) - 1:
        return failed("invalid_inode", "file_size")
    if size == 0:
        return failed("unsupported_profile", "file_size")
    record = be(inode, 176, 16)
    state, offset = record >> 127, (record >> 73) & ((1 << 54) - 1)
    encoded, length = (record >> 21) & ((1 << 52) - 1), record & ((1 << 21) - 1)
    if state:
        return failed("unsupported_profile", "unwritten")
    if offset:
        return failed("unsupported_profile", "file_offset")
    if not length or be(inode, 64, 8) != length:
        return failed("invalid_extent", "block_count")
    needed = (size + be(sb, 4, 4) - 1) // be(sb, 4, 4)
    if length < needed:
        return failed("invalid_extent", "block_count")
    if length > needed:
        return failed("unsupported_profile", "trailing_allocation")
    start = address(sb, encoded, length)
    if not start:
        return failed("invalid_extent", "extent_address")
    sectors = (size + 511) // 512
    if not 0 <= index <= sectors:
        return failed("invalid_index", "sector_index")
    facts = (number, inode_address // 512 + number % slots, size, start // 512, length)
    if index == sectors:
        return Expected("end", facts=facts)
    return Expected("ready", facts=facts, sector=(start // 512 + index, min(512, size - index * 512)))


def array(name, data):
    return f"builtin::array<u8, {len(data)}> {name} = {{" + ", ".join(f"{b}u8" for b in data) + "};\n"


def getters(variable, names, values):
    return "".join(f"if ({variable}.{name}() != {value}u64) {{ return 0u64; }}\n" for name, value in zip(names, values))


def check_plan(expected):
    body = f"""
        if (report.status() != fs::XfsFileStatus::{expected.status} ||
            report.issue() != fs::XfsFileIssue::{expected.issue}) {{ return 0u64; }}
        const fs::XfsFileFacts facts = report.facts();
        const fs::XfsFileSector coordinate = report.sector();
    """
    return body + getters("facts", FACTS, expected.facts) + getters("coordinate", COORDINATES, expected.sector)


def plan_case(label, sb, inode, number=131, index=0, capacity=CAPACITY, anchor=None):
    expected = oracle(sb, inode, number, index, capacity)
    if anchor:
        require((expected.status, expected.issue) == anchor, label + ": model anchor")
    body = array("sb", sb) + array("inode", inode)
    body += f"""
        const storage::SectorGeometry source = storage::SectorGeometry({capacity}u64, false);
        const fs::XfsFileRequest request = fs::XfsFileRequest({number}u64, {index});
        const fs::XfsFileReport original = fs::plan_xfs_v5_512_file_sector(
            source, borrow_bytes(sb), borrow_bytes(inode), request);
        const fs::XfsFileReport report = original;
        sb[0] = 0u8;
        inode[0] = 0u8;
    """
    return Case(label, body + check_plan(expected) + "return 42u64;", 42, imports=IMPORTS)


def plan_cases(sb, inode):
    yield plan_case("actual written PREALLOC NREXT64 inode", sb, inode, anchor=("ready", "none"))
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
        yield plan_case(f"extent count layout flags2={flags}", sb, changed, anchor=("ready", "none"))
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
            geometry.change(sb, incompat=be(sb, 216, 4) & ~feature),
            inode,
            anchor=("unsupported_profile", "flags"),
        )
    for offset in (8, 20, 32, 92, 104, 112, 144, 192, 511):
        yield plan_case(
            f"CRC-covered opaque byte {offset}",
            sb,
            set_inode(inode, (offset, 1, inode[offset] ^ 0x55)),
            anchor=("ready", "none"),
        )
    for size in (1, 511, 512, 513, 4095, 4096, 4097, 17003, 20479, 20480):
        count = (size + 4095) // 4096
        changed = extent(inode, count=count, size=size)
        yield plan_case(f"file size {size}", sb, changed, index=(size - 1) // 512, anchor=("ready", "none"))
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
    middle_log_sb = geometry.change(sb, logstart=(2 << 15) + 100, logblocks=100)
    for start, count, accepted in (
        (95, 5, True),
        (96, 5, False),
        (100, 1, False),
        (199, 1, False),
        (199, 2, False),
        (200, 1, True),
    ):
        expected = ("ready", "none") if accepted else ("invalid_extent", "extent_address")
        yield plan_case(
            f"exact internal-log interval {start}+{count}",
            middle_log_sb,
            extent(inode, start=(2 << 15) + start, count=count),
            anchor=expected,
        )
    tail_sb = geometry.change(sb, dblocks=3 * 20480 + 64)
    for start in (59, 60, 63, 64, 20479):
        yield plan_case(f"last AG tail {start}+5", tail_sb, extent(inode, start=(3 << 15) + start), capacity=CAPACITY)
    large_sb = geometry.change(
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
    require(geometry.oracle(large_sb).status == "header_geometry_consistent", "large reserved-band fixture")
    for start, count, accepted in (
        (RESERVED - 1, 1, True),
        (RESERVED - 5, 5, True),
        (RESERVED - 1, 2, False),
        (RESERVED - 5, 6, False),
        (RESERVED, 1, False),
        (RESERVED + 1, 1, False),
        ((1 << 52) - 1, 1, False),
    ):
        expected = ("ready", "none") if accepted else ("invalid_extent", "extent_address")
        yield plan_case(
            f"reserved exact boundary {start}+{count}",
            large_sb,
            extent(inode, start=start, count=count, block_bytes=1024),
            capacity=(1 << 64) - 1,
            anchor=expected,
        )
    maximum_sb = geometry.change(
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
        anchor=("ready", "none"),
    )
    yield plan_case(
        "maximum supported file end",
        maximum_sb,
        maximum_inode,
        index=maximum_index + 1,
        capacity=(1 << 64) - 1,
        anchor=("end", "none"),
    )
    ag_inode = (1 << 18) + 131
    yield plan_case(
        "nonzero AG inode address", sb, set_inode(inode, (152, 8, ag_inode)), number=ag_inode, anchor=("ready", "none")
    )
    inode1024 = geometry.change(sb, inodesize=1024, inodelog=10, inopblock=4, inopblog=2, inoalignmt=16)
    yield plan_case("valid excluded inode size", inode1024, inode, anchor=("unsupported_profile", "inode_size"))
    bad_inode = set_inode(inode, (100, 4, 0), repair=False)
    for index in (-1, 34, 9223372036854775807):
        yield plan_case("checksum before index", sb, bad_inode, index=index, anchor=("invalid_inode", "checksum"))
    yield plan_case(
        "geometry before capacity",
        geometry.change(sb, blocksize=3),
        inode,
        capacity=0,
        anchor=("geometry_rejected", "geometry"),
    )
    yield plan_case("capacity before inode", sb, bad_inode, capacity=0, anchor=("source_too_small", "capacity"))


def read_case(label, sb, inode, window, index, base, number=131, capacity=CAPACITY, empty=False):
    planned = oracle(sb, inode, number, index, capacity)
    status = "invalid_source"
    expected = bytes(512)
    if planned.status in ("end", "invalid_index"):
        status = "out_of_range"
    elif planned.status == "ready":
        if empty or not 0 < len(window) <= 4096 or len(window) % 512:
            status = "invalid_source"
        elif not base <= planned.sector[0] < base + len(window) // 512:
            status = "out_of_range"
        else:
            status = "success"
            offset = (planned.sector[0] - base) * 512
            expected = window[offset : offset + planned.sector[1]].ljust(512, b"\0")
    body = array("sb", sb) + array("inode", inode) + array("window", window) + array("expected", expected)
    body += f"""
        const builtin::array<u8, {len(window)}> saved = window;
        const storage::SectorGeometry source = storage::SectorGeometry({capacity}u64, false);
        const fs::XfsFileRequest request = fs::XfsFileRequest({number}u64, {index});
    """
    span = "borrow_bytes(window)"
    if empty:
        body += "const builtin::span<const u8> all = borrow_bytes(window);"
        body += f"const builtin::span<const u8> empty = all.subspan({len(window)}, 0);"
        span = "empty"
    body += f"""
        const storage::SectorReadResult original = fs::read_xfs_v5_512_file_sector(
            source, borrow_bytes(sb), borrow_bytes(inode), request, {span}, {base}u64);
        const storage::SectorReadResult copy = original;
        i64 check = 0;
        while (check < {len(window)}) {{
            if (window[check] != saved[check]) {{ return 0u64; }}
            check = check + 1;
        }}
    """
    if not empty:
        body += f"window[0] = 255u8; window[{len(window) - 1}] = 255u8;\n"
    body += f"""
        sb[0] = 0u8;
        inode[0] = 0u8;
        if (copy.status() != storage::SectorIoStatus::{status}) {{ return 0u64; }}
        const storage::Sector512 sector = copy.sector_or_zero();
        i64 offset = 0;
        while (offset < 512) {{
            const std::ByteReadResult byte = sector.read_byte(offset);
            if (byte.status() != std::ByteReadStatus::success || byte.value_or(999u64) != u64(expected[offset])) {{
                return 0u64;
            }}
            offset = offset + 1;
        }}
        return 42u64;
    """
    return Case(label, body, 42, imports=IMPORTS)


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
    large_sb = geometry.change(
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
    require(
        oracle(large_sb, high_inode, index=1, capacity=(1 << 64) - 1).sector == ((RESERVED - 1) * 2 + 1, 512),
        "high-LBA read anchor",
    )
    yield read_case(
        "synthetic high-LBA actual window read",
        large_sb,
        high_inode,
        data[:512],
        1,
        (RESERVED - 1) * 2 + 1,
        capacity=(1 << 64) - 1,
    )
    near_u64_sb = geometry.change(
        sb,
        agblocks=1 << 28,
        agblklog=28,
        agcount=1 << 24,
        dblocks=(1 << 52) - 1,
        logstart=1024,
        logblocks=64,
    )
    near_u64_inode = extent(inode, start=RESERVED - 1, count=1)
    near_u64_plan = oracle(near_u64_sb, near_u64_inode, index=7, capacity=(1 << 64) - 1)
    require(
        near_u64_plan.status == "ready" and near_u64_plan.sector == (RESERVED * 8 - 1, 512),
        "near-u64 data-byte / high-LBA read anchor",
    )
    yield read_case(
        "synthetic near-u64 data-byte bound read",
        near_u64_sb,
        near_u64_inode,
        data[:512],
        7,
        RESERVED * 8 - 1,
        capacity=(1 << 64) - 1,
    )
    maximum_sb = geometry.change(
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
    require(
        oracle(maximum_sb, maximum_inode, index=maximum_index, capacity=(1 << 64) - 1).sector
        == (24 * 128 + maximum_index, 512),
        "maximum-size final-sector read anchor",
    )
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


def report_cases():
    for status in (
        "ready",
        "end",
        "invalid_index",
        "geometry_rejected",
        "source_too_small",
        "unsupported_profile",
        "invalid_inode",
        "invalid_extent",
    ):
        facts = (1, 2, 3, 4, 5) if status in ("ready", "end") else (0,) * 5
        sector = (6, 7) if status == "ready" else (0, 0)
        body = f"""
            const fs::XfsFileFacts supplied = fs::XfsFileFacts(1u64, 2u64, 3u64, 4u64, 5u64);
            const fs::XfsFileSector coordinate_input = fs::XfsFileSector(6u64, 7u64);
            const fs::XfsFileReport report = fs::XfsFileReport(
                fs::XfsFileStatus::{status}, fs::XfsFileIssue::none, supplied, coordinate_input);
            if (size_of(fs::XfsFileReport) != 72 || size_of(fs::XfsFileRequest) != 16 ||
                size_of(fs::XfsFileFacts) != 40 || size_of(fs::XfsFileSector) != 16 ||
                field_count(fs::XfsFileReport) != 0) {{ return 0u64; }}
        """
        yield Case(
            f"fabricated masking {status}",
            body + check_plan(Expected(status, facts=facts, sector=sector)) + "return 42u64;",
            42,
            imports=IMPORTS,
        )


def indexed_root_case(sb, root, inode, data):
    body = array("sb", sb) + array("root", root) + array("inode", inode) + array("window", data[:512])
    body += """
        const fs::XfsRootEntryReport entry_report = fs::entry_at_xfs_v5_512_root(
            borrow_bytes(sb), borrow_bytes(root), 0);
        if (entry_report.status() != fs::XfsRootEntryStatus::found) { return 0u64; }
        const fs::XfsRootEntry entry = entry_report.entry();
        if (entry.inode_number() != 131u64 || entry.file_type() != 1u64) { return 0u64; }
        const storage::SectorGeometry source = storage::SectorGeometry(655360u64, false);
        const fs::XfsFileRequest request = fs::XfsFileRequest(entry.inode_number(), 0);
        const storage::SectorReadResult read = fs::read_xfs_v5_512_file_sector(
            source, borrow_bytes(sb), borrow_bytes(inode), request, borrow_bytes(window), 192u64);
        if (read.status() != storage::SectorIoStatus::success) { return 0u64; }
        const storage::Sector512 sector = read.sector_or_zero();
        i64 index = 0;
        while (index < 512) {
            const std::ByteReadResult byte = sector.read_byte(index);
            if (byte.value_or(999u64) != u64(window[index])) { return 0u64; }
            index = index + 1;
        }
        return 42u64;
    """
    return Case("real indexed-root entry to actual first file sector", body, 42, imports=IMPORTS + ("fs.xfs_root",))


def rejections():
    prefix = "module test; " + " ".join("import " + m + ";" for m in IMPORTS) + " auto test() -> u64 {"
    prefix += "const builtin::array<u8, 1> data = {0u8};"
    prefix += "const storage::SectorGeometry source = storage::SectorGeometry(1u64, false);"
    prefix += "const fs::XfsFileRequest request = fs::XfsFileRequest(131u64, 0);"
    for body in (
        "return request._inode;",
        "const fs::XfsFileRequest wrong = fs::XfsFileRequest(131u64, 0u64); return 0u64;",
        "const fs::XfsFileRequest wrong = fs::XfsFileRequest(131, 0); return 0u64;",
        "return u64(fs::XfsFileStatus::ready);",
        "const fs::XfsFileReport result = fs::xf_failure("
        "fs::XfsFileStatus::ready, fs::XfsFileIssue::none); return 0u64;",
        "const fs::XfsFileReport result = fs::plan_xfs_v5_512_file_sector("
        "source, borrow_bytes(data), borrow_bytes(data), request); return result._facts;",
        "const fs::XfsFileSector plan = fs::XfsFileSector(192u64, 512u64);"
        "const storage::SectorReadResult result = fs::read_xfs_v5_512_file_sector("
        "source, borrow_bytes(data), borrow_bytes(data), plan, borrow_bytes(data), 192u64); return 0u64;",
        "const storage::SectorReadResult result = fs::read_xfs_v5_512_file_sector("
        "source, borrow_bytes(data), borrow_bytes(data), request, borrow_bytes(data), 192); return 0u64;",
    ):
        yield Rejection("XFS file privacy/exact-type rejection", prefix + body + "}")


def corpus():
    sb, inode, root = (fixture(name) for name in ("superblock.hex", "written-inode.hex", "root.hex"))
    data = fixture("written-extent-0.hex")
    payload = fixture("written.txt")
    require(len(payload) == 17003 and len(data) == 20480 and data[:17003] == payload, "complete actual payload")
    require(oracle(sb, inode).facts == (131, 131, 17003, 192, 5), "actual inode and first-data anchors")
    require(oracle(sb, inode, index=33).sector == (225, 107), "actual final partial sector")
    root_model.geometry = geometry
    root_expected = root_model.oracle(sb, root, b"written")
    require(root_expected.status == "found" and root_expected.values[5:] == (131, 1), "actual root entry anchor")
    return [
        *plan_cases(sb, inode),
        *read_cases(sb, inode, data),
        *report_cases(),
        indexed_root_case(sb, root, inode, data),
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("compiler", type=Path, nargs="?")
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    cases = corpus()
    rejected = list(rejections())
    if args.source_only:
        print(json.dumps({"status": "source-model-only", "cases": len(cases), "rejections": len(rejected)}))
        return
    require(args.compiler is not None, "compiler required for native execution")
    compiler = args.compiler.resolve(strict=True)
    print(f"compiler_sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()}", flush=True)
    with tempfile.TemporaryDirectory(prefix="aurora-xfs-file-") as temporary:
        runner = NativeRunner(Path(temporary), compiler, 15)
        for start in range(0, len(cases), 2):
            runner.cases(cases[start : start + 2])
        for case in rejected:
            runner.rejection(case)
    print(f"PASS XFS file: {len(cases)} native cases, {len(rejected)} rejections", flush=True)


if __name__ == "__main__":
    main()
