#!/usr/bin/env python3
"""Bounded inline XFS file sectors: historical/synthetic fixtures and a bigint model."""

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
FACTS = ("inode_number", "inode_lba", "size_bytes", "extent_count", "allocated_blocks")
COORDINATES = ("source_lba", "valid_bytes")
RESERVED = (1 << 52) - (1 << 17)
CAPACITY = 655360
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
    kind: str = "none"


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
    size = be(inode, 56, 8)
    if size > (1 << 63) - 1:
        return failed("invalid_inode", "file_size")
    if size == 0:
        return failed("unsupported_profile", "file_size")
    records = []
    for record_index in range(count):
        record = be(inode, 176 + 16 * record_index, 16)
        state, offset = record >> 127, (record >> 73) & ((1 << 54) - 1)
        encoded, length = (record >> 21) & ((1 << 52) - 1), record & ((1 << 21) - 1)
        if not length:
            return failed("invalid_extent", "block_count")
        if records and offset < records[-1][1]:
            return failed("invalid_extent", "file_offset")
        start = address(sb, encoded, length)
        if not start:
            return failed("invalid_extent", "extent_address")
        records.append((offset, offset + length, state, start, length))
    allocated = sum(record[4] for record in records)
    if allocated != be(inode, 64, 8):
        return failed("invalid_extent", "block_count")
    needed = (size + be(sb, 4, 4) - 1) // be(sb, 4, 4)
    if any(record[1] > needed for record in records):
        return failed("unsupported_profile", "trailing_allocation")
    sectors = (size + 511) // 512
    if not 0 <= index <= sectors:
        return failed("invalid_index", "sector_index")
    facts = (number, inode_address // 512 + number % slots, size, count, allocated)
    if index == sectors:
        return Expected("end", facts=facts)
    logical, intra = divmod(index * 512, be(sb, 4, 4))
    matching = [record for record in records if record[0] <= logical < record[1]]
    require(len(matching) <= 1, "model logical mapping uniqueness")
    kind, source_lba = "hole", 0
    if matching:
        first, _, state, start, _ = matching[0]
        kind = "unwritten" if state else "written"
        if not state:
            source_lba = (start + (logical - first) * be(sb, 4, 4) + intra) // 512
    return Expected("ready", facts=facts, sector=(source_lba, min(512, size - index * 512)), kind=kind)


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
    body += f"if (coordinate.kind() != fs::XfsFileSectorKind::{expected.kind}) {{ return 0u64; }}\n"
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


def read_case(label, sb, inode, window, index, base, number=131, capacity=CAPACITY, empty=False, payload=None):
    planned = oracle(sb, inode, number, index, capacity)
    status = "invalid_source"
    expected = bytes(512)
    if planned.status in ("end", "invalid_index"):
        status = "out_of_range"
    elif planned.status == "ready":
        if planned.kind in ("hole", "unwritten"):
            status = "success"
        elif empty or not 0 < len(window) <= 4096 or len(window) % 512:
            status = "invalid_source"
        elif not base <= planned.sector[0] < base + len(window) // 512:
            status = "out_of_range"
        else:
            status = "success"
            offset = (planned.sector[0] - base) * 512
            expected = window[offset : offset + planned.sector[1]].ljust(512, b"\0")
    if payload is not None:
        require(status == "success" and expected == payload, label + ": independent payload anchor")
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
            const fs::XfsFileSector coordinate_input = fs::XfsFileSector(fs::XfsFileSectorKind::written, 6u64, 7u64);
            const fs::XfsFileReport report = fs::XfsFileReport(
                fs::XfsFileStatus::{status}, fs::XfsFileIssue::none, supplied, coordinate_input);
            if (size_of(fs::XfsFileReport) != 80 || size_of(fs::XfsFileRequest) != 16 ||
                size_of(fs::XfsFileFacts) != 40 || size_of(fs::XfsFileSector) != 24 ||
                field_count(fs::XfsFileReport) != 0) {{ return 0u64; }}
        """
        yield Case(
            f"fabricated masking {status}",
            body
            + check_plan(Expected(status, facts=facts, sector=sector, kind="written" if status == "ready" else "none"))
            + "return 42u64;",
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
        "const fs::XfsFileSector wrong = fs::XfsFileSector(0u64, 1u64, 512u64); return 0u64;",
        "const fs::XfsFileSector wrong = fs::XfsFileSector(fs::XfsFileSectorKind::written, 1, 512u64); return 0u64;",
        "const fs::XfsFileSector private_value = fs::XfsFileSector(fs::XfsFileSectorKind::hole, 0u64, 512u64);"
        "return private_value._lba;",
        "const fs::XfsFileRequest wrong = fs::XfsFileRequest(131u64, 0u64); return 0u64;",
        "const fs::XfsFileRequest wrong = fs::XfsFileRequest(131, 0); return 0u64;",
        "return u64(fs::XfsFileStatus::ready);",
        "const fs::XfsFileReport result = fs::xf_failure("
        "fs::XfsFileStatus::ready, fs::XfsFileIssue::none); return 0u64;",
        "const fs::XfsFileReport result = fs::plan_xfs_v5_512_file_sector("
        "source, borrow_bytes(data), borrow_bytes(data), request); return result._facts;",
        "const fs::XfsFileSector plan = fs::XfsFileSector(fs::XfsFileSectorKind::written, 192u64, 512u64);"
        "const storage::SectorReadResult result = fs::read_xfs_v5_512_file_sector("
        "source, borrow_bytes(data), borrow_bytes(data), plan, borrow_bytes(data), 192u64); return 0u64;",
        "const storage::SectorReadResult result = fs::read_xfs_v5_512_file_sector("
        "source, borrow_bytes(data), borrow_bytes(data), request, borrow_bytes(data), 192); return 0u64;",
    ):
        yield Rejection("XFS file privacy/exact-type rejection", prefix + body + "}")


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
    require(oracle(sb, inode, number=134).facts == (134, 134, 32769, 3, 3), "historical sparse facts")
    for index in range(65):
        logical, intra = divmod(index, 8)
        kind, lba, window, base = "hole", 0, bytes([0xD9]), (1 << 64) - 1
        if logical in (1, 6, 8):
            record = (1, 6, 8).index(logical)
            lba = (15, 29, 31)[record] * 8 + intra
            kind, window, base = "written", samples[record], (15, 29, 31)[record] * 8
        planned = oracle(sb, inode, number=134, index=index)
        require(planned.kind == kind and planned.sector == (lba, 1 if index == 64 else 512), "sparse sector map")
        expected = payload[index * 512 : (index + 1) * 512].ljust(512, b"\0")
        yield read_case(
            f"historical sparse full-payload sector {index}",
            sb,
            inode,
            window,
            index,
            base,
            number=134,
            payload=expected,
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
                anchor=("unsupported_profile", "file_size"),
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
                        lba = address(sb, physical, 1) // 512 + (logical - offset) * 8 + intra
                planned = oracle(sb, changed, index=index)
                valid = min(512, size - index * 512)
                require(planned.kind == kind and planned.sector == (lba, valid), title + ": descriptor anchor")
                label = f"synthetic {title}, large_count={large_count}, sector {index}"
                yield plan_case(label, sb, changed, index=index, anchor=("ready", "none"))
                expected = poison[:valid].ljust(512, b"\0") if kind == "written" else bytes(512)
                yield read_case(label, sb, changed, poison[:512], index, lba, payload=expected)
            end = (size + 511) // 512
            for index in (-1, end, end + 1):
                yield plan_case(f"synthetic {title} index endpoint {index}, {large_count}", sb, changed, index=index)
    for count in (0, 1, 2, 21):
        records = [(index * 2, 24 + index, 1, bool(index % 2)) for index in range(count)]
        for large_count in (False, True):
            changed = inline_inode(inode, records, max(1, count * 8192 - 1), large_count)
            require(oracle(sb, changed).facts[-2:] == (count, count), "inline record count facts")
            for index in (0, max(0, count * 16 - 2), max(0, count * 16 - 1)):
                yield plan_case(f"synthetic count capacity {count}/{large_count}/{index}", sb, changed, index=index)
            if count:
                yield plan_case(
                    f"synthetic declared-last record {count}/{large_count}", sb, changed, index=(count - 1) * 16
                )
            excessive = set_inode(changed, (24, 8, 22) if large_count else (76, 4, 22))
            yield plan_case("synthetic overfull fork", sb, excessive, anchor=("invalid_inode", "extent_count"))
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
                anchor=("invalid_extent", issue),
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
                    anchor=("invalid_extent", "extent_address"),
                )
        changed = inline_inode(inode, [(0, 24, 1, False), (1, 40, 1, unwritten)], 4096)
        for index in (0, 8, -1):
            yield plan_case(
                f"synthetic trailing allocation {unwritten}/{index}",
                sb,
                changed,
                index=index,
                anchor=("unsupported_profile", "trailing_allocation"),
            )
        short_tail = inline_inode(inode, [(0, 24, 1, unwritten)], 4097)
        require(oracle(sb, short_tail, index=8).kind == "hole", "trailing hole differs from trailing allocation")
        yield read_case("synthetic last short hole", sb, short_tail, poison[:1], 8, 0, payload=bytes(512))
    for allocated in (0, 1, 3, (1 << 64) - 1):
        changed = inline_inode(inode, [(0, 24, 1, False), (2, 40, 1, True)], 4 * 4096)
        changed = set_inode(changed, (64, 8, allocated))
        yield plan_case("synthetic allocation sum mismatch", sb, changed, anchor=("invalid_extent", "block_count"))
    records21 = [(index, 24 + index, 1, False) for index in range(21)]
    changed21 = inline_inode(inode, records21, 21 * 4096)
    for physical in (0, RESERVED):
        record = (20 << 73) | (physical << 21) | 1
        corrupt21 = set_inode(changed21, (496, 16, record))
        yield plan_case(
            "synthetic last possible record rejected before first read",
            sb,
            corrupt21,
            anchor=("invalid_extent", "extent_address"),
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
                    payload=bytes(512),
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
        payload=bytes(512),
    )
    far = (maximum_size - 1) // 4096
    for unwritten in (False, True):
        far_inode = inline_inode(inode, [(far, 24, 1, unwritten)], maximum_size)
        yield plan_case("synthetic far sparse extent near signed EOF", sb, far_inode, index=(maximum_size - 1) // 512)
        expected = bytes(512) if unwritten else poison[:511] + b"\0"
        yield read_case(
            "synthetic far sparse final mapped sector",
            sb,
            far_inode,
            poison[:512],
            (maximum_size - 1) // 512,
            199,
            payload=expected,
        )
        maximum_offset = inline_inode(inode, [((1 << 54) - 1, 24, 1, unwritten)], maximum_size)
        yield plan_case(
            "synthetic maximum encoded logical offset never scaled",
            sb,
            maximum_offset,
            anchor=("unsupported_profile", "trailing_allocation"),
        )
    log_sb = geometry.change(sb, logstart=(2 << 15) + 100, logblocks=100)
    tail_sb = geometry.change(sb, dblocks=3 * 20480 + 64)
    for changed_sb, title, intervals in (
        (log_sb, "log", [(95, 5, True), (96, 5, False), (199, 1, False), (200, 1, True)]),
        (tail_sb, "last AG", [(59, 5, True), (60, 5, False), (63, 1, True), (64, 1, False)]),
    ):
        ag = 2 if title == "log" else 3
        for start, length, accepted in intervals:
            changed = inline_inode(inode, [(0, 24, 1, False), (2, (ag << 15) + start, length, True)], 8 * 4096)
            for index in (0, 16):
                anchor = ("ready", "none") if accepted else ("invalid_extent", "extent_address")
                yield plan_case(
                    f"synthetic later unwritten {title} {start}+{length}/{index}",
                    changed_sb,
                    changed,
                    index=index,
                    anchor=anchor,
                )
    maximal_sb = geometry.change(
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
    expected = oracle(maximal_sb, full_inode, index=full_size // 512 - 1, capacity=(1 << 64) - 1)
    require(expected.facts[-2:] == (21, 21 * longest), "all21 maximum block counts")
    require(expected.sector == (((3 << 24) + 24 + 7 * longest) * 128 - 1, 512), "all21 maximum last LBA")
    yield plan_case(
        "synthetic maximum count in all21 records",
        maximal_sb,
        full_inode,
        index=full_size // 512 - 1,
        capacity=(1 << 64) - 1,
        anchor=("ready", "none"),
    )
    yield read_case(
        "synthetic all21 maximum records final read",
        maximal_sb,
        full_inode,
        poison[:512],
        full_size // 512 - 1,
        expected.sector[0],
        capacity=(1 << 64) - 1,
        payload=poison[:512],
    )
    later_bad = inline_inode(inode, [(4, 24, 1, True), (6, RESERVED, 1, True)], 4096)
    yield plan_case(
        "synthetic malformed later record outranks earlier trailing allocation",
        sb,
        later_bad,
        anchor=("invalid_extent", "extent_address"),
    )
    for kind in ("none", "written", "hole", "unwritten"):
        expected_lba = 999 if kind == "written" else 0
        expected_valid = 0 if kind == "none" else 333
        yield Case(
            "fabricated coordinate kind masking " + kind,
            f"""
                const fs::XfsFileSector coordinate = fs::XfsFileSector(fs::XfsFileSectorKind::{kind}, 999u64, 333u64);
                const fs::XfsFileSector copy = coordinate;
                if (copy.kind() != fs::XfsFileSectorKind::{kind} || copy.source_lba() != {expected_lba}u64 ||
                    copy.valid_bytes() != {expected_valid}u64) {{ return 0u64; }}
                return 42u64;
            """,
            42,
            imports=IMPORTS,
        )


def corpus():
    sb, inode, root = (fixture(name) for name in ("superblock.hex", "written-inode.hex", "root.hex"))
    data = fixture("written-extent-0.hex")
    payload = fixture("written.txt")
    require(len(payload) == 17003 and len(data) == 20480 and data[:17003] == payload, "complete actual payload")
    require(oracle(sb, inode).facts == (131, 131, 17003, 1, 5), "actual inode and allocation anchors")
    require(oracle(sb, inode, index=33).sector == (225, 107), "actual final partial sector")
    root_model.geometry = geometry
    root_expected = root_model.oracle(sb, root, b"written")
    require(root_expected.status == "found" and root_expected.values[5:] == (131, 1), "actual root entry anchor")
    return [
        *plan_cases(sb, inode),
        *read_cases(sb, inode, data),
        *report_cases(),
        *historical_sparse_cases(sb),
        *inline_cases(sb, inode),
        indexed_root_case(sb, root, inode, data),
    ]


def batches(cases, count=16, source_bytes=1 << 17):
    # Each compile pays for the whole XFS import graph, so batch independent
    # cases. Compile time grows faster than linearly with module size (a 512 KiB
    # batch takes about 25 s), so keep each batch near one second.
    group, size = [], 0
    for case in cases:
        cost = len(case.body) + 64
        require(cost <= source_bytes, f"{case.name}: generated case exceeds the batch source budget")
        if group and (len(group) == count or size + cost > source_bytes):
            yield group
            group, size = [], 0
        group.append(case)
        size += cost
    if group:
        yield group


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
        for group in batches(cases, count=32):
            # Compiler-only runaway watchdog; Meson bounds the complete correctness fixture to 600 seconds.
            runner.cases(group)
        for case in rejected:
            runner.rejection(case)
    print(f"PASS XFS file: {len(cases)} native cases, {len(rejected)} rejections", flush=True)


if __name__ == "__main__":
    main()
