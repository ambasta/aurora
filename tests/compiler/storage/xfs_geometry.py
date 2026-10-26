#!/usr/bin/env python3
"""fs.xfs_probe, fs.xfs_geometry and fs.xfs_sector over the preserved real superblock.

Only fixtures/xfs-offline/superblock-v5-512.hex is mkfs output. Every variant is
a synthetic header, CRC-repaired unless named unrepaired, and establishes nothing
about unseen disks. Expected results are golden.
"""

from __future__ import annotations

import random

import harness
from harness import U64, require
from xfs_inputs import SCHEMA, SUPERBLOCK_CRC, change, offline_superblock, repair

U32 = (1 << 32) - 1
SEED = 19019
MASKS = ("compat", "ro_compat", "incompat", "log_incompat")
INSPECT, FABRICATED, LAYOUT, DETACHED, PROBE, SECTOR, FABRICATED_SECTOR = range(7)
GEOMETRY_STATUSES = ("probe_rejected", "unsupported_feature_profile", "unsupported_layout", "offline_state_indicated")
GEOMETRY_STATUSES += ("inconsistent_header", "size_unrepresentable", "header_geometry_consistent")
SECTOR_STATUSES = ("read_failed", "geometry_rejected", "source_too_small", "header_fits_source")
IO_STATUSES = ("success", "out_of_range", "read_only", "invalid_source")
LAYOUT_TYPES = ("XfsBlockFacts", "XfsInodeFacts", "XfsDataFacts", "XfsAgFacts", "XfsLogFacts", "XfsGeometryFacts")
LAYOUT_TYPES += ("XfsHeaderObservations", "XfsFeatureMasks", "XfsFeatureDiagnostics", "XfsGeometryReport")


def header_cases(real, seed, random_count):
    result = []

    def add(name, data):
        result.append((name, bytes(data)))

    def mutate(name, base=real, **changes):
        add(name, change(base, **changes))

    add("preserved real header", real)
    for length in (1, 4, 511, 513, 1024):
        add(f"probe length {length}", (real * 2)[:length])
    for name, changes in (
        ("endian magic", {"magic": 0x42534658}),
        ("zero magic", {"magic": 0}),
        ("v4", {"versionnum": 0xB4A4}),
        ("sector4096", {"sectsize": 4096}),
        ("sectorlog12", {"sectlog": 12}),
    ):
        mutate(name, **changes)
    for offset in (4, 224, 227, 511):
        data = bytearray(real)
        data[offset] ^= 1
        add(f"unrepaired byte {offset}", data)
    for offset in (32, 64, 72, 232, 511):
        data = bytearray(real)
        data[offset] ^= 0x80
        add(f"repaired uninterpreted byte {offset}", repair(data, SUPERBLOCK_CRC))

    for bit in range(16):
        if 0xB4A0 & (1 << bit):
            mutate(f"required version bit {bit}", versionnum=0xB4A5 ^ (1 << bit))
        if not 0xBCA5 & (1 << bit):
            mutate(f"extra version bit {bit}", versionnum=0xB4A5 | (1 << bit))
    for bit in range(32):
        value = 0x18A ^ (1 << bit) if 0x18A & (1 << bit) else 0x18A | (1 << bit)
        mutate(f"features2 bit {bit}", features2=value, bad_features2=value)
    for field in MASKS:
        for bit in range(32):
            value = 1 << bit
            mutate(f"{field} single bit {bit}", **{field: value})
    mutate("missing FTYPE", incompat=0x2A)
    mutate("mirror mismatch", bad_features2=0x38A)
    for bl in range(10, 17):
        for il in range(9, min(bl, 11) + 1):
            B, I = 2**bl, 2**il
            A = max(32768, (2**24) // B)
            align = 64 * I // B
            data = change(
                real,
                blocksize=B,
                blocklog=bl,
                inodesize=I,
                inodelog=il,
                inopblock=B // I,
                inopblog=bl - il,
                agblocks=A,
                agcount=4,
                dblocks=A * 4,
                agblklog=(A - 1).bit_length(),
                inoalignmt=align,
                spino_align=align,
                rextsize=max(1, 4096 // B),
                logblocks=64,
                logstart=2 * (2 ** (A - 1).bit_length()) + 7,
            )
            add(f"valid block/inode logs {bl}/{il}", data)
            mutate(f"directory max blocklog {bl} inode {il}", base=data, dirblklog=16 - bl)
    nonpower = change(real, agblocks=30000, dblocks=120000)
    add("non-power-of-two AG encoded AG2 block7", nonpower)
    for tail in (1, 63, 64, 32767, 32768):
        mutate(f"last AG blocks {tail}", dblocks=3 * 32768 + tail)
    for delta in (-1, 0, 1):
        for boundary in (32768, 3 * 32768, 4 * 32768):
            mutate(f"count boundary {boundary} delta {delta}", dblocks=boundary + delta)
    for values in (
        {"versionnum": 0xBCA5, "logsectsize": 512, "logsectlog": 9},
        {"logsunit": 0},
        {"imax_pct": 0},
        {"imax_pct": 100},
        {"spino_align": 0},
        {"spino_align": 1},
        {"spino_align": 8},
        {"incompat": 0x29, "spino_align": 0},
    ):
        mutate("positive " + str(values), **values)
    for size, logarithm in ((0, 0), (512, 0), (0, 9), (4096, 12), (65535, 255), (512, 255)):
        mutate(
            f"declared log sector {size}/{logarithm}",
            versionnum=0xBCA5,
            logsectsize=size,
            logsectlog=logarithm,
        )
    # Scalar extrema and shift/divisor attacks are individually repaired so CRC
    # does not hide the intended validation branch.
    for field, values in {
        "blocksize": (0, 1, 512, 4095, U32),
        "blocklog": (0, 9, 17, 63, 64, 255),
        "inodesize": (0, 1, 256, 511, 2049, 65535),
        "inodelog": (0, 8, 12, 63, 64, 255),
        "inopblock": (0, 1, 7, 9, 65535),
        "inopblog": (0, 2, 4, 63, 64, 255),
        "dirblklog": (5, 63, 64, 255),
        "agblocks": (0, 1, 4095, 4096, 268435456, 268435457, U32),
        "agcount": (0, 1, U32),
        "dblocks": (0, 1, 63, 64, U32, U64),
        "agblklog": (0, 14, 16, 31, 32, 63, 64, 255),
        "rblocks": (1, U64),
        "rextents": (1, U64),
        "rbmblocks": (1, U32),
        "rextslog": (1, 255),
        "frextents": (1, U64),
        "rextsize": (0, 262144, 262145, U32),
        "inoalignmt": (0, 1, 7, 9, U32),
        "spino_align": (3, 9, U32),
        "logstart": (0, 1, 131072, U64),
        "logblocks": (0, 1, 32761, 32762, 1048576, 1048577, U32),
        "logsectsize": (1, 512, 4096, 65535),
        "logsectlog": (1, 9, 12, 63, 64, 255),
        "logsunit": (2, U32),
        "unit": (1, U32),
        "width": (1, U32),
        "qflags": (1, 65535),
        "flags": (1, 255),
        "inprogress": (1, 255),
        "shared_vn": (1, 255),
        "imax_pct": (101, 255),
    }.items():
        for value in values:
            mutate(f"{field}={value}", **{field: value})
    for field, (_, width) in SCHEMA.items():
        for value in (0, (1 << (width * 8)) - 1):
            mutate(f"schema field endpoint {field}={value}", **{field: value})
    mutate("coherent256inode", inodesize=256, inodelog=8, inopblock=16, inopblog=4)
    mutate("inode larger than block", blocksize=1024, blocklog=10, inodesize=2048, inodelog=11)
    mutate("q exceeds u32", agblocks=4096, agblklog=12, dblocks=(U32 + 1) * 4096, agcount=U32)
    mutate("q u32 with remainder", agblocks=4096, agblklog=12, dblocks=U32 * 4096 + 1, agcount=U32)
    mutate("q truncation", agblocks=4096, agblklog=12, dblocks=(U32 + 2) * 4096, agcount=1)
    huge = change(real, agblocks=268435456, agblklog=28, agcount=U32, dblocks=1152921504338411520)
    add("consistent data byte overflow", huge)
    mutate("data overflow outranks misc", base=huge, imax_pct=255)
    for D in (U64 // 4096, U64 // 4096 + 1):
        A = 268435456
        mutate(
            f"data representability edge {D}",
            agblocks=A,
            agblklog=28,
            dblocks=D,
            agcount=(D + A - 1) // A,
        )
    for A in (4096, 268435456):
        mutate(
            f"nominal AG bound {A}",
            agblocks=A,
            agblklog=(A - 1).bit_length(),
            dblocks=A * 4,
            logstart=2 * 2 ** (A - 1).bit_length() + 7,
            logblocks=64,
        )
    mutate(
        "maximum admitted AG exponent30",
        blocksize=1024,
        blocklog=10,
        inopblock=2,
        inopblog=1,
        rextsize=4,
        inoalignmt=32,
        spino_align=4,
        agblocks=1 << 30,
        agblklog=30,
        dblocks=1 << 32,
        logstart=(1 << 31) + 7,
        logblocks=64,
    )
    for g, a, length in ((4, 7, 1), (0, 0, 1), (0, 1, 1), (3, 32767, 1), (3, 32767, 2), (3, 32768, 1), (2, 7, 32762)):
        mutate(f"log range g{g} a{a} len{length}", logstart=g * 32768 + a, logblocks=length)
    for a in (29999, 30000, 32767):
        mutate(f"nonpower encoded gap {a}", base=nonpower, logstart=32768 + a, logblocks=1)
    for a, length in ((63, 1), (63, 2), (64, 1), (1, 63), (1, 64)):
        mutate(f"short tail log {a}+{length}", dblocks=98368, logstart=3 * 32768 + a, logblocks=length)
    for bl in (10, 12, 16):
        B = 2**bl
        base = change(
            real,
            blocksize=B,
            blocklog=bl,
            inopblock=B // 512,
            inopblog=bl - 9,
            inoalignmt=32768 // B,
            spino_align=0,
            rextsize=max(1, 4096 // B),
            agblocks=2**24,
            agblklog=24,
            dblocks=2**26,
            logstart=2**25 + 7,
        )
        for L in (min(1048576, 2136997888 // B), min(1048576, 2136997888 // B) + 1):
            mutate(f"log byte/count edge B{B} L{L}", base=base, logblocks=L)
    for changes in (
        {"versionnum": 0xB4A5 ^ 0x20, "features2": 0, "incompat": U32},
        {"versionnum": 0xB4A5 | 0x100, "features2": 0},
        {"versionnum": 0xB4A5 | 0x100, "features2": 0x38A},
        {"features2": 0x38A, "incompat": 0x10},
        {"incompat": 0x80000010, "bad_features2": 0},
        {"incompat": 0x80000001, "inprogress": 1},
        {"bad_features2": 0, "inprogress": 1},
        {"inprogress": 1, "rblocks": 1},
        {"rblocks": 1, "logstart": 0},
        {"logstart": 0, "unit": 1},
        {"logsunit": 2, "qflags": 1},
        {"qflags": 1, "blocklog": 255},
        {"blocklog": 255, "inodelog": 255},
        {"inodelog": 255, "dirblklog": 255},
        {"dirblklog": 255, "agblocks": 0},
        {"agblocks": 0, "rextents": 1},
        {"rextents": 1, "inoalignmt": 0},
        {"inoalignmt": 0, "logblocks": 0},
        {"logblocks": 0, "imax_pct": 255},
        {"shared_vn": 1, "logsectlog": 255},
    ):
        mutate("precedence " + str(changes), **changes)
    rng = random.Random(seed)
    for index in range(random_count):
        if index % 3 == 0:
            data = bytearray(real)
            for _ in range(1 + index % 5):
                data[rng.randrange(512)] = rng.randrange(256)
            add(f"seed {seed} random repaired bytes {index}", repair(data, SUPERBLOCK_CRC))
        elif index % 3 == 1:
            key = rng.choice(tuple(SCHEMA))
            value = rng.randrange(1 << (8 * SCHEMA[key][1]))
            mutate(f"seed {seed} field {index} {key}", **{key: value})
        else:
            A = rng.randrange(4096, 70000)
            N = rng.randrange(1, 20)
            tail = rng.randrange(64, A + 1)
            g = rng.randrange(N)
            extent = tail if g == N - 1 else A
            a = rng.randrange(1, extent)
            mutate(
                f"seed {seed} valid geometry {index}",
                agblocks=A,
                agcount=N,
                agblklog=(A - 1).bit_length(),
                dblocks=(N - 1) * A + tail,
                logstart=g * 2 ** (A - 1).bit_length() + a,
                logblocks=rng.randrange(1, extent - a + 1),
            )
    # Paired unrepaired cases make the old probe's precedence observable for each
    # new checking family without doubling every source fixture.
    for key, value in (
        ("blocklog", 255),
        ("inodelog", 255),
        ("agblocks", 0),
        ("agblklog", 255),
        ("dblocks", U64),
        ("logstart", U64),
        ("logblocks", 0),
        ("incompat", U32),
        ("features2", 0),
        ("versionnum", 0xB4A5 ^ 0x20),
        ("rextsize", 0),
        ("spino_align", 3),
        ("inprogress", 1),
        ("shared_vn", 1),
    ):
        add(f"paired unrepaired {key}", change(real, repair_crc=False, **{key: value}))
    require(len(result) <= 768, "bounded header corpus")
    return result


# Headers that each reach one validation guard the main corpus leaves implicit.
WITNESSES = (
    (
        "coherent512block",
        dict(
            blocksize=512, blocklog=9, inopblock=1, inopblog=0, rextsize=8, inoalignmt=64, spino_align=4, logblocks=64
        ),
    ),
    ("coherent1byteinode", dict(inodesize=1, inodelog=0, inopblock=4096, inopblog=12, inoalignmt=0, spino_align=0)),
    ("coherent256inodealigned", dict(inodesize=256, inodelog=8, inopblock=16, inopblog=4, inoalignmt=4, spino_align=4)),
    ("coherent8MiB AG", dict(agblocks=2048, agblklog=11, dblocks=8192, logstart=4103, logblocks=64)),
    (
        "coherent over1TiB AG",
        dict(agblocks=268435457, agblklog=29, dblocks=1073741828, logstart=1073741831, logblocks=64),
    ),
    ("internal log at AG2 header block", dict(logstart=65536, logblocks=1)),
    (
        "nonzero sparse with zero chunk",
        dict(blocksize=65536, blocklog=16, inopblock=128, inopblog=7, inoalignmt=0, spino_align=1, logblocks=64),
    ),
    ("wrong chunk without secondary divisor fault", dict(inoalignmt=7, spino_align=0)),
    ("zero sparse divisor", dict(spino_align=0)),
)


def witness_headers(real):
    return [(f"guard witness {name}", change(real, **changes)) for name, changes in WITNESSES]


def probe_fixture(seed):
    """A nonzero synthetic probe sector: every byte past the fixed header is random."""
    rng = random.Random(seed ^ 0x584653)
    values = bytearray(rng.randrange(256) for _ in range(512))
    values[0:4] = b"XFSB"
    values[100:102] = (5).to_bytes(2, "big")
    values[102:104] = (512).to_bytes(2, "big")
    values[121] = 9
    values[511] = 167
    for offset, value in zip((208, 212, 216, 220), (0x80000001, 0xFEDCBA98, 0x01020304, 0xFFFFFFFF)):
        values[offset : offset + 4] = value.to_bytes(4, "big")
    return repair(values, SUPERBLOCK_CRC)


def probe_cases(seed=15015):
    valid = probe_fixture(seed)
    omitted = valid[:224] + valid[228:]

    def rechecksum(values):
        return repair(values, SUPERBLOCK_CRC)

    def with_bytes(offset, data, base=valid):
        values = bytearray(base)
        values[offset : offset + len(data)] = data
        return bytes(values)

    yield "complete nonzero 512-byte sector", valid
    for offset in (208, 212, 216, 220):
        changed = with_bytes(offset, (0xDEADBEEF).to_bytes(4, "big"))
        yield f"changed raw mask at {offset} without new checksum", changed
        yield f"changed raw mask at {offset} with valid checksum is only header integrity", rechecksum(changed)
    for size in (1, 224, 264, 511, 513, 4096):
        yield f"wrong length {size}", (valid * ((size + 511) // 512))[:size]
    for offset in (0, 1, 2, 3):
        yield f"magic mismatch byte {offset} precedes checksum", with_bytes(offset, bytes([valid[offset] ^ 1]))
    for version in (0, 4, 6, 15, 0xFFF4):
        yield f"unsupported version {version:#x} precedes checksum", with_bytes(100, version.to_bytes(2, "big"))
    for version in (0x0015, 0xA005, 0xFFF5):
        yield f"version low-nibble mask {version:#x}", rechecksum(with_bytes(100, version.to_bytes(2, "big")))
    for size in (0, 256, 1024, 4096):
        yield f"unsupported declared sector size {size}", with_bytes(102, size.to_bytes(2, "big"))
    for sector_log in (0, 8, 10, 255):
        yield f"unsupported sector log {sector_log}", with_bytes(121, bytes([sector_log]))
        yield (
            f"unsupported sector log {sector_log} despite valid checksum",
            rechecksum(with_bytes(121, bytes([sector_log]))),
        )
    for offset in (128, 223, 224, 225, 226, 227, 228, 300, 511):
        yield f"corruption at sector byte {offset}", with_bytes(offset, bytes([valid[offset] ^ 1]))
    yield "wrong stored CRC endianness", with_bytes(224, valid[224:228][::-1])
    omitted_crc = harness.crc32c(omitted).to_bytes(4, "little")
    yield "omitted CRC bytes differ from zero substitution", with_bytes(224, omitted_crc)
    yield "zero stored CRC is still checked", with_bytes(224, bytes(4))
    yield "changed final byte with recalculated CRC", rechecksum(with_bytes(511, bytes([valid[511] ^ 1])))


def header(operation, data, **values):
    return {"operation": operation, "length": len(data), **harness.spread("header", data, 8), **values}


def sector_case(label, data, count, io="success", writable=False):
    values = dict(count=count, io=IO_STATUSES.index(io), writable=int(writable))
    return label, header(SECTOR, data, **values), 68


def sector_cases(real, headers, outcomes):
    """Copied first-sector reads; `outcomes` maps header names to observed (status, issue, probe status)."""
    required = int.from_bytes(real[8:16], "big") * int.from_bytes(real[4:8], "big") // 512
    require(required == 1048576, "preserved image capacity")
    for writable in (False, True):
        yield sector_case(f"actual one-sector backend, writable={writable}", real, 1, writable=writable)
        for count in (0, 1, required - 1, required, required + 1, 1 << 63, U64):
            yield sector_case(
                f"constructed source capacity {count}, writable={writable}", real, count, writable=writable
            )
    for io in ("out_of_range", "read_only", "invalid_source"):
        for count in (0, required, U64):
            yield sector_case(f"read failure before parsing/capacity {io}/{count}", real, count, io)
    # One 512-byte header per observed validator outcome crosses the copied-sector boundary.
    selected = {}
    for name, data in headers:
        if len(data) == 512:
            selected.setdefault(outcomes[name], (name, data))
    for (status, _, _), (name, data) in selected.items():
        yield sector_case("metadata gate: " + name, data, 0)
        if status != "header_geometry_consistent":
            yield sector_case("metadata before large capacity: " + name, data, U64)
    large = dict(headers)["data representability edge 4503599627370495"]
    for count in (36028797018963960 - 1, 36028797018963960, 36028797018963960 + 1):
        yield sector_case(f"large synthetic header capacity {count}", large, count)
    for offset in (0, 224, 227, 511):
        changed = bytearray(real)
        changed[offset] ^= 1
        yield sector_case(f"unrepaired full-sector byte {offset}", bytes(changed), required)
    for index in (-(1 << 63), -1, 1, (1 << 63) - 1):
        # A one-sector device's out-of-range read: a failed, zero-payload result.
        yield sector_case(f"actual backend read error {index}", bytes(512), 1, "out_of_range", writable=True)
    for label, data in (("valid header", real), ("nonzero diagnostic masks", change(real, compat=1))):
        for status in SECTOR_STATUSES:
            for io in IO_STATUSES:
                values = dict(selector=SECTOR_STATUSES.index(status), io=IO_STATUSES.index(io))
                yield (
                    f"public report masking/layout {label}/{status}/{io}",
                    header(FABRICATED_SECTOR, data, **values),
                    71,
                )


def other_cases(real):
    for code, status in enumerate(GEOMETRY_STATUSES):
        yield f"fabricated {status} copied and masked all24 facts", dict(operation=FABRICATED, selector=code), 42
    yield "layout and runtime metadata of every report type", dict(operation=LAYOUT), 40
    different = change(real, agblocks=30000, dblocks=120000)
    yield "copied report outlives owner mutation and function return", header(DETACHED, real + different), 44
    for label, data in probe_cases():
        yield "probe " + label, header(PROBE, data), 5


def geometry_words(driver, words):
    names = [driver.name(enum, code) for enum, code in zip(GEOMETRY_ENUMS, words[:3])]
    names += [f"masks={group(words[3:7])}", f"raw={group(words[7:10])}", f"unsupported={group(words[10:14])}"]
    names += [f"unknown={group(words[14:18])}", f"facts={group(words[18:42])}"]
    return " ".join(names)


def group(values):
    """Comma-separated values, or 0 when every value is zero."""
    return ",".join(map(str, values)) if any(values) else "0"


GEOMETRY_ENUMS = ("XfsGeometryStatus", "XfsGeometryIssue", "XfsProbeStatus")


def format_result(driver, values, words):
    operation = values["operation"]
    if operation == INSPECT:
        return geometry_words(driver, words) + (" ok" if words[42] == 1 else f" check-failed-{words[42]}")
    if operation == FABRICATED:
        return geometry_words(driver, words)
    if operation == LAYOUT:
        return " ".join(f"{name}={','.join(map(str, words[4 * i : 4 * i + 4]))}" for i, name in enumerate(LAYOUT_TYPES))
    if operation == DETACHED:
        return geometry_words(driver, words) + f" other_ag_blocks={words[42]} retained_ag_blocks={words[43]}"
    if operation == PROBE:
        return f"{driver.name('XfsProbeStatus', words[0])} masks={group(words[1:5])}"
    facts = words[44:68]
    text = f"{driver.name('XfsSectorHeaderStatus', words[0])} {driver.name('SectorIoStatus', words[1])} "
    text += geometry_words(driver, words[2:44]) + " admitted=" + group(facts)
    if operation == FABRICATED_SECTOR:
        text += " layout=" + ",".join(map(str, words[68:71]))
    return text


PREFIX = "module xfs_geometry_test;import fs.xfs_geometry;import fs.xfs_probe;import std.binary;\n"
SPAN = "builtin::span<const u8>"
SECTOR_PREFIX = "module test; import std.binary; import std.binary_buffer; import storage.sector;"
SECTOR_PREFIX += " import storage.block_io; import storage.ram_sector; import fs.xfs_probe; import fs.xfs_geometry;"
SECTOR_PREFIX += " import fs.xfs_sector; auto test() -> u64 {"
SECTOR_PREFIX += " const storage::SectorGeometry source = storage::SectorGeometry(1u64, false);"
SECTOR_PREFIX += "const storage::Sector512 sector = storage::Sector512();"
SECTOR_PREFIX += "const storage::SectorReadResult read = storage::SectorReadResult("
SECTOR_PREFIX += "storage::SectorIoStatus::success, sector);"


def rejections(real):
    bytes_array = "array<u8,512> bytes={" + ",".join(f"{value}u8" for value in real) + "};"
    report = PREFIX + "auto test()->u64{const " + bytes_array
    report += "const fs::XfsGeometryReport r=fs::inspect_xfs_v5_512_geometry(borrow_bytes(bytes));"
    for label, tail in (
        ("report private status", "return r._status;}"),
        ("status has no numeric conversion", "return u64(r.status());}"),
        ("copied facts not a span", f"const {SPAN} view=r.facts();return 1u64;}}"),
        ("private helper inaccessible", "return fs::xfs_geometry_read32(borrow_bytes(bytes),4);}"),
    ):
        yield label, report + tail
    yield (
        "span return excluded by callable type surface",
        PREFIX + f"auto escape()->{SPAN}{{const {bytes_array}return borrow_bytes(bytes);}}",
    )
    yield (
        "XFS sector class argument",
        SECTOR_PREFIX
        + "const fs::XfsSectorHeaderReport report = fs::inspect_xfs_v5_512_sector(1u64, read);"
        + " return 0u64;}",
    )


def header_rows(real):
    return header_cases(real, SEED, 48) + witness_headers(real)


def describe(compiler, directory):
    real = offline_superblock()
    driver = harness.Driver(compiler, directory, harness.HERE / "xfs_geometry.au", "HeaderInput")
    headers = header_rows(real)
    observed = driver.run([(header(INSPECT, data), 43) for _, data in headers])
    outcomes = {}
    for (name, data), words in zip(headers, observed):
        outcomes.setdefault(name, tuple(driver.name(enum, code) for enum, code in zip(GEOMETRY_ENUMS, words[:3])))
        yield name, format_result(driver, {"operation": INSPECT}, words)
    rest = list(other_cases(real)) + list(sector_cases(real, headers, outcomes))
    for (label, values, _), words in zip(rest, driver.run([(values, slots) for _, values, slots in rest])):
        yield label, format_result(driver, values, words)
    yield from harness.rejections(compiler, directory, list(rejections(real)))


if __name__ == "__main__":
    harness.main("xfs_geometry", describe)
