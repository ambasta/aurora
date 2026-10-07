#!/usr/bin/env python3
"""Bounded ordinary native tests for fs.xfs_geometry, with a bigint schema oracle.

Only the canonical preserved 512-byte header is a real mkfs fixture. All repaired
variants are synthetic headers and establish nothing about unseen disk contents.
No devices, mounts, kernel changes, mutable views, or compiler changes are used.
Every scalar leaf is returned as a complete native u64 (closed enums are explicit
predicates), including all zero facts on failure. Signals, timeouts, diagnostics,
and compiler/tool failures fail the gate and retain unique source/command receipts.
The instrumented compiler does not make generated Aurora code ASan-instrumented.

Run: python3 tests/compiler/xfs_geometry.py /path/to/aurorac --compiler-sha256 EXPECTED_SHA256
Controls: python3 -O tests/compiler/xfs_geometry.py --self-test-only
"""
from __future__ import annotations

import re
import argparse
from collections import Counter
from dataclasses import asdict, dataclass, replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import shutil
import signal
import sys
import tempfile
import time

sys.dont_write_bytecode = True

from storage_binary import crc32c_reference, VECTORS
from unsigned_oracle import Case, Observation, require, validate_values
from utf8 import Suite as BoundedSuite

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from compiler_contract import add_identity_arguments, resolve_identity, validate_identity_selection
U64 = (1 << 64) - 1
U32 = (1 << 32) - 1
MAX_SOURCE = 65536
MAX_BATCH = 4
SEED = 19019
PROPOSAL_SHA = "40021cf66fba001094c9f0762475075967b64bd4f55b8be845490ddf37fc5b86"
SPAN = "builtin::span<const u8>"
PREFIX = "module xfs_geometry_test;import fs.xfs_geometry;import fs.xfs_probe;import std.binary;\n"

# This schema is authored from disk offsets, not compiler layout or the module.
SCHEMA = {
    "magic": (0, 4), "blocksize": (4, 4), "dblocks": (8, 8),
    "rblocks": (16, 8), "rextents": (24, 8), "logstart": (48, 8),
    "rbmino": (64, 8), "rsumino": (72, 8), "rextsize": (80, 4),
    "agblocks": (84, 4), "agcount": (88, 4), "rbmblocks": (92, 4),
    "logblocks": (96, 4), "versionnum": (100, 2), "sectsize": (102, 2),
    "inodesize": (104, 2), "inopblock": (106, 2), "blocklog": (120, 1),
    "sectlog": (121, 1), "inodelog": (122, 1), "inopblog": (123, 1),
    "agblklog": (124, 1), "rextslog": (125, 1), "inprogress": (126, 1),
    "imax_pct": (127, 1), "frextents": (152, 8), "qflags": (176, 2),
    "flags": (178, 1), "shared_vn": (179, 1), "inoalignmt": (180, 4),
    "unit": (184, 4), "width": (188, 4), "dirblklog": (192, 1),
    "logsectlog": (193, 1), "logsectsize": (194, 2), "logsunit": (196, 4),
    "features2": (200, 4), "bad_features2": (204, 4), "compat": (208, 4),
    "ro_compat": (212, 4), "incompat": (216, 4), "log_incompat": (220, 4),
    "spino_align": (228, 4),
}
MASKS = ("compat", "ro_compat", "incompat", "log_incompat")
KNOWN = (0, 15, 0x7ff, 1)
ALLOWED = (0, 15, 0x2b, 0)
GROUPS = {
    "blocks": ("XfsBlockFacts", ("block_bytes", "sector_bytes", "block_log", "sector_log",
                                "directory_block_bytes", "effective_log_sector_bytes")),
    "inodes": ("XfsInodeFacts", ("inode_bytes", "inodes_per_block", "inode_log", "inodes_per_block_log")),
    "data": ("XfsDataFacts", ("data_blocks", "claimed_data_bytes", "claimed_data_sectors")),
    "ags": ("XfsAgFacts", ("ag_block_log", "ag_blocks", "ag_count", "ag_bytes", "last_ag_blocks", "last_ag_start_bytes")),
    "log": ("XfsLogFacts", ("log_start_encoded", "log_ag", "log_ag_block", "log_start_bytes", "log_bytes")),
}
FACTS = tuple(name for _, fields in GROUPS.values() for name in fields)
LEAVES = ("status_predicate", "issue_predicate", "probe_status_predicate",
          *["probe_" + name for name in MASKS], "versionnum", "features2", "bad_features2",
          *["unsupported_" + name for name in MASKS], *["unknown_" + name for name in MASKS], *FACTS)
require(len(LEAVES) == 42 and len(FACTS) == 24, "schema leaf count")


@dataclass(frozen=True)
class Expected:
    status: str
    issue: str
    probe_status: str
    probe_masks: tuple[int, ...]
    raw: tuple[int, ...] = (0, 0, 0)
    unsupported: tuple[int, ...] = (0, 0, 0, 0)
    unknown: tuple[int, ...] = (0, 0, 0, 0)
    facts: tuple[int, ...] = (0,) * 24

    def scalars(self):
        return (1, 1, 1, *self.probe_masks, *self.raw, *self.unsupported, *self.unknown, *self.facts)


@dataclass(frozen=True)
class Header:
    name: str
    data: bytes
    expected: Expected
    family: str


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def transport_module():
    spec = importlib.util.spec_from_file_location("xfs_canonical_transport", ROOT / "fixtures/xfs-offline/verify_native.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def real_fixture(controls=True):
    transport = transport_module()
    path = ROOT / "fixtures/xfs-offline/superblock-v5-512.hex"
    data = transport.read_fixture_hex(path)
    if controls:
        with path.open("rb") as stream:
            transport.transport_self_tests(stream.read(1729))
    return data


def fields(data):
    require(len(data) == 512, "schema decoding needs exact input")
    return {name: int.from_bytes(data[offset:offset + width], "big")
            for name, (offset, width) in SCHEMA.items()}


def repair(data):
    result = bytearray(data)
    require(len(result) == 512, "CRC repair needs exact input")
    result[224:228] = bytes(4)
    result[224:228] = crc32c_reference(result).to_bytes(4, "little")
    return bytes(result)


def change(data, repair_crc=True, **changes):
    result = bytearray(data)
    for name, value in changes.items():
        offset, width = SCHEMA[name]
        require(0 <= value < (1 << (width * 8)), "field mutation width " + name)
        result[offset:offset + width] = value.to_bytes(width, "big")
    return repair(result) if repair_crc else bytes(result)


def oracle(data):
    """Direct bigint relations; no machine truncation or checked arithmetic model.

    Interval equations and ceil division operate on unbounded Python integers.
    This deliberately does not replicate the module's guard-by-guard arithmetic.
    """
    zero_masks = (0,) * 4
    if len(data) != 512:
        return Expected("probe_rejected", "none", "wrong_length", zero_masks)
    d = fields(data)
    if d["magic"] != 0x58465342:
        return Expected("probe_rejected", "none", "unrecognized", zero_masks)
    masks = tuple(d[name] for name in MASKS)
    if d["versionnum"] % 16 != 5 or (d["sectsize"], d["sectlog"]) != (512, 9):
        return Expected("probe_rejected", "none", "unsupported_profile", masks)
    if repair(data) != data:
        return Expected("probe_rejected", "none", "checksum_mismatch", masks)
    result = Expected("header_geometry_consistent", "none", "header_integrity_valid", masks,
                      tuple(d[name] for name in ("versionnum", "features2", "bad_features2")),
                      tuple(word & (U32 ^ admitted) for word, admitted in zip(masks, ALLOWED)),
                      tuple(word & (U32 ^ known) for word, known in zip(masks, KNOWN)))

    def failure(status, issue):
        return replace(result, status=status, issue=issue)

    def bad(issue):
        return failure("inconsistent_header", issue)

    def unsupported(issue):
        return failure("unsupported_layout", issue)

    if d["versionnum"] & 0xb4a0 != 0xb4a0:
        return bad("legacy_required_bits")
    if d["features2"] & 0x18a != 0x18a:
        return bad("features2_required_bits")
    if d["versionnum"] & (0xffff ^ 0xbca5):
        return failure("unsupported_feature_profile", "legacy_excluded_bits")
    if d["features2"] & (U32 ^ 0x18a):
        return failure("unsupported_feature_profile", "features2_excluded_bits")
    if d["incompat"] & 0x10:
        return failure("offline_state_indicated", "needs_repair")
    if any(result.unsupported) or d["incompat"] & 1 == 0:
        return failure("unsupported_feature_profile", "extended_feature_masks")
    if d["features2"] != d["bad_features2"]:
        return unsupported("features2_mirror")
    if d["inprogress"]:
        return failure("offline_state_indicated", "offline_operation")
    if d["rblocks"]:
        return unsupported("realtime")
    if d["logstart"] == 0:
        return unsupported("external_log")
    if d["unit"] or d["width"] or d["logsunit"] > 1:
        return unsupported("striping")
    if d["qflags"] or d["flags"]:
        return unsupported("quota_or_misc_flags")
    B, A, N, D = (d[name] for name in ("blocksize", "agblocks", "agcount", "dblocks"))
    bl, il, I = d["blocklog"], d["inodelog"], d["inodesize"]
    if not 10 <= bl <= 16 or B != 2 ** bl or B < 512:
        return bad("block_geometry")
    if not 8 <= il <= 11 or I != 2 ** il:
        return bad("inode_geometry")
    if il == 8:
        return unsupported("inode_geometry")
    if I > B or d["inopblock"] * I != B or d["inopblog"] + il != bl:
        return bad("inode_geometry")
    if bl + d["dirblklog"] > 16:
        return bad("directory_geometry")
    if min(A, N, D) == 0 or not 2 ** 24 <= A * B <= 2 ** 40:
        return bad("ag_geometry")
    if d["agblklog"] != (A - 1).bit_length() or N != (D + A - 1) // A:
        return bad("ag_geometry")
    tail_base, tail = (N - 1) * A, D - (N - 1) * A
    if not 64 <= tail <= A:
        return bad("ag_geometry")
    if D * B > U64:
        return failure("size_unrepresentable", "data_byte_size")
    if any(d[name] for name in ("rextents", "rbmblocks", "rextslog", "frextents")):
        return bad("realtime_zero_geometry")
    if not 4096 <= d["rextsize"] * B <= 1073741824:
        return bad("realtime_zero_geometry")
    alignment, sparse = d["inoalignmt"], d["spino_align"]
    if d["incompat"] & 2:
        if alignment != (64 * I) // B:
            return bad("inode_alignment")
        if sparse and (sparse > alignment or alignment % sparse):
            return bad("inode_alignment")
    elif sparse:
        return bad("inode_alignment")
    log_sector = (512, 9) if d["versionnum"] & 0x800 else (0, 0)
    if (d["logsectsize"], d["logsectlog"]) != log_sector:
        return unsupported("log_geometry") if d["versionnum"] & 0x800 else bad("log_geometry")
    L, F = d["logblocks"], d["logstart"]
    if not 1 <= L <= 1048576 or L * B > 2136997888:
        return bad("log_geometry")
    g, a = divmod(F, 2 ** d["agblklog"])
    actual = tail if g == N - 1 else A
    raw_start = g * A + a
    if not 0 <= g < N or not 3 * 512 // B < a < actual or a + L > actual:
        return bad("log_geometry")
    if not 0 <= raw_start <= raw_start + L <= D:
        return bad("log_geometry")
    if d["shared_vn"] != 0 or d["imax_pct"] > 100:
        return bad("misc_geometry")
    facts = {
        "block_bytes": B, "sector_bytes": 512, "block_log": bl, "sector_log": 9,
        "directory_block_bytes": B * 2 ** d["dirblklog"], "effective_log_sector_bytes": 512,
        "inode_bytes": I, "inodes_per_block": B // I, "inode_log": il,
        "inodes_per_block_log": bl - il, "data_blocks": D, "claimed_data_bytes": D * B,
        "claimed_data_sectors": D * B // 512, "ag_block_log": d["agblklog"],
        "ag_blocks": A, "ag_count": N, "ag_bytes": A * B, "last_ag_blocks": tail,
        "last_ag_start_bytes": tail_base * B, "log_start_encoded": F, "log_ag": g,
        "log_ag_block": a, "log_start_bytes": raw_start * B, "log_bytes": L * B,
    }
    require(set(facts) == set(FACTS), "complete fact schema")
    return replace(result, facts=tuple(facts[name] for name in FACTS))


def header_cases(real, seed, random_count):
    result = []

    def add(name, data, family="targeted", expected=None):
        observed = oracle(data)
        if expected is not None:
            require((observed.status, observed.issue) == expected, "case anchor " + name)
        result.append(Header(name, bytes(data), observed, family))

    def mutate(name, base=real, family="targeted", **changes):
        add(name, change(base, **changes), family)

    add("preserved real header", real, "real", ("header_geometry_consistent", "none"))
    for length in (1, 4, 511, 513, 1024):
        add(f"probe length {length}", (real * 2)[:length], "probe")
    for name, changes in (("endian magic", {"magic": 0x42534658}), ("zero magic", {"magic": 0}),
                          ("v4", {"versionnum": 0xb4a4}), ("sector4096", {"sectsize": 4096}),
                          ("sectorlog12", {"sectlog": 12})):
        mutate(name, family="probe", **changes)
    for offset in (4, 224, 227, 511):
        data = bytearray(real)
        data[offset] ^= 1
        add(f"unrepaired byte {offset}", data, "probe")
    for offset in (32, 64, 72, 232, 511):
        data = bytearray(real)
        data[offset] ^= 0x80
        add(f"repaired uninterpreted byte {offset}", repair(data), "opaque")

    for bit in range(16):
        if 0xb4a0 & (1 << bit):
            mutate(f"required version bit {bit}", versionnum=0xb4a5 ^ (1 << bit), family="legacy")
        if not 0xbca5 & (1 << bit):
            mutate(f"extra version bit {bit}", versionnum=0xb4a5 | (1 << bit), family="legacy")
    for bit in range(32):
        value = 0x18a ^ (1 << bit) if 0x18a & (1 << bit) else 0x18a | (1 << bit)
        mutate(f"features2 bit {bit}", features2=value, bad_features2=value, family="legacy")
    for field in MASKS:
        for bit in range(32):
            value = 1 << bit
            mutate(f"{field} single bit {bit}", family="extended", **{field: value})
    mutate("missing FTYPE", incompat=0x2a, family="extended")
    mutate("mirror mismatch", bad_features2=0x38a, family="legacy")
    for bl in range(10, 17):
        for il in range(9, min(bl, 11) + 1):
            B, I = 2 ** bl, 2 ** il
            A = max(32768, (2 ** 24) // B)
            align = 64 * I // B
            data = change(real, blocksize=B, blocklog=bl, inodesize=I, inodelog=il,
                          inopblock=B // I, inopblog=bl - il, agblocks=A, agcount=4,
                          dblocks=A * 4, agblklog=(A - 1).bit_length(), inoalignmt=align,
                          spino_align=align, rextsize=max(1, 4096 // B), logblocks=64,
                          logstart=2 * (2 ** (A - 1).bit_length()) + 7)
            add(f"valid block/inode logs {bl}/{il}", data, "positive", ("header_geometry_consistent", "none"))
            mutate(f"directory max blocklog {bl} inode {il}", base=data, dirblklog=16 - bl, family="positive")
    nonpower = change(real, agblocks=30000, dblocks=120000)
    add("non-power-of-two AG encoded AG2 block7", nonpower, "positive")
    require(oracle(nonpower).facts[FACTS.index("log_start_bytes")] == 245788672, "nonpower address anchor")
    for tail in (1, 63, 64, 32767, 32768):
        mutate(f"last AG blocks {tail}", dblocks=3 * 32768 + tail, family="ag")
    for delta in (-1, 0, 1):
        for boundary in (32768, 3 * 32768, 4 * 32768):
            mutate(f"count boundary {boundary} delta {delta}", dblocks=boundary + delta, family="ag")
    for values in ({"versionnum": 0xbca5, "logsectsize": 512, "logsectlog": 9},
                   {"logsunit": 0}, {"imax_pct": 0}, {"imax_pct": 100}, {"spino_align": 0},
                   {"spino_align": 1}, {"spino_align": 8}, {"incompat": 0x29, "spino_align": 0}):
        mutate("positive " + str(values), family="positive", **values)
    for size, logarithm in ((0, 0), (512, 0), (0, 9), (4096, 12), (65535, 255), (512, 255)):
        mutate(f"declared log sector {size}/{logarithm}", versionnum=0xbca5,
               logsectsize=size, logsectlog=logarithm, family="log")
    # Scalar extrema and shift/divisor attacks are individually repaired so CRC
    # does not hide the intended validation branch.
    for field, values in {
        "blocksize": (0, 1, 512, 4095, U32), "blocklog": (0, 9, 17, 63, 64, 255),
        "inodesize": (0, 1, 256, 511, 2049, 65535), "inodelog": (0, 8, 12, 63, 64, 255),
        "inopblock": (0, 1, 7, 9, 65535), "inopblog": (0, 2, 4, 63, 64, 255),
        "dirblklog": (5, 63, 64, 255), "agblocks": (0, 1, 4095, 4096, 268435456, 268435457, U32),
        "agcount": (0, 1, U32), "dblocks": (0, 1, 63, 64, U32, U64),
        "agblklog": (0, 14, 16, 31, 32, 63, 64, 255), "rblocks": (1, U64),
        "rextents": (1, U64), "rbmblocks": (1, U32), "rextslog": (1, 255), "frextents": (1, U64),
        "rextsize": (0, 262144, 262145, U32), "inoalignmt": (0, 1, 7, 9, U32),
        "spino_align": (3, 9, U32), "logstart": (0, 1, 131072, U64),
        "logblocks": (0, 1, 32761, 32762, 1048576, 1048577, U32),
        "logsectsize": (1, 512, 4096, 65535), "logsectlog": (1, 9, 12, 63, 64, 255),
        "logsunit": (2, U32), "unit": (1, U32), "width": (1, U32),
        "qflags": (1, 65535), "flags": (1, 255), "inprogress": (1, 255),
        "shared_vn": (1, 255), "imax_pct": (101, 255),
    }.items():
        for value in values:
            mutate(f"{field}={value}", family="extrema", **{field: value})
    for field, (_, width) in SCHEMA.items():
        for value in (0, (1 << (width * 8)) - 1):
            mutate(f"schema field endpoint {field}={value}", family="schema_extrema", **{field: value})
    mutate("coherent256inode", inodesize=256, inodelog=8, inopblock=16, inopblog=4)
    mutate("inode larger than block", blocksize=1024, blocklog=10, inodesize=2048, inodelog=11)
    mutate("q exceeds u32", agblocks=4096, agblklog=12, dblocks=(U32 + 1) * 4096, agcount=U32)
    mutate("q u32 with remainder", agblocks=4096, agblklog=12, dblocks=U32 * 4096 + 1, agcount=U32)
    mutate("q truncation", agblocks=4096, agblklog=12, dblocks=(U32 + 2) * 4096, agcount=1)
    huge = change(real, agblocks=268435456, agblklog=28, agcount=U32, dblocks=1152921504338411520)
    add("consistent data byte overflow", huge, "overflow", ("size_unrepresentable", "data_byte_size"))
    mutate("data overflow outranks misc", base=huge, imax_pct=255, family="precedence")
    for D in (U64 // 4096, U64 // 4096 + 1):
        A = 268435456
        mutate(f"data representability edge {D}", agblocks=A, agblklog=28, dblocks=D,
               agcount=(D + A - 1) // A, family="overflow")
    for A in (4096, 268435456):
        mutate(f"nominal AG bound {A}", agblocks=A, agblklog=(A - 1).bit_length(),
               dblocks=A * 4, logstart=2 * 2 ** (A - 1).bit_length() + 7, logblocks=64, family="positive")
    mutate("maximum admitted AG exponent30", blocksize=1024, blocklog=10, inopblock=2, inopblog=1,
           rextsize=4, inoalignmt=32, spino_align=4, agblocks=1 << 30, agblklog=30,
           dblocks=1 << 32, logstart=(1 << 31) + 7, logblocks=64, family="positive")
    for g, a, length in ((4, 7, 1), (0, 0, 1), (0, 1, 1), (3, 32767, 1),
                         (3, 32767, 2), (3, 32768, 1), (2, 7, 32762)):
        mutate(f"log range g{g} a{a} len{length}", logstart=g * 32768 + a, logblocks=length, family="log")
    for a in (29999, 30000, 32767):
        mutate(f"nonpower encoded gap {a}", base=nonpower, logstart=32768 + a, logblocks=1, family="log")
    for a, length in ((63, 1), (63, 2), (64, 1), (1, 63), (1, 64)):
        mutate(f"short tail log {a}+{length}", dblocks=98368, logstart=3 * 32768 + a, logblocks=length, family="log")
    for bl in (10, 12, 16):
        B = 2 ** bl
        base = change(real, blocksize=B, blocklog=bl, inopblock=B // 512, inopblog=bl - 9,
                      inoalignmt=32768 // B, spino_align=0, rextsize=max(1, 4096 // B),
                      agblocks=2 ** 24, agblklog=24, dblocks=2 ** 26, logstart=2 ** 25 + 7)
        for L in (min(1048576, 2136997888 // B), min(1048576, 2136997888 // B) + 1):
            mutate(f"log byte/count edge B{B} L{L}", base=base, logblocks=L, family="log")
    for changes in (
        {"versionnum": 0xb4a5 ^ 0x20, "features2": 0, "incompat": U32},
        {"versionnum": 0xb4a5 | 0x100, "features2": 0},
        {"versionnum": 0xb4a5 | 0x100, "features2": 0x38a},
        {"features2": 0x38a, "incompat": 0x10},
        {"incompat": 0x80000010, "bad_features2": 0},
        {"incompat": 0x80000001, "inprogress": 1},
        {"bad_features2": 0, "inprogress": 1},
        {"inprogress": 1, "rblocks": 1}, {"rblocks": 1, "logstart": 0},
        {"logstart": 0, "unit": 1}, {"logsunit": 2, "qflags": 1},
        {"qflags": 1, "blocklog": 255}, {"blocklog": 255, "inodelog": 255},
        {"inodelog": 255, "dirblklog": 255}, {"dirblklog": 255, "agblocks": 0},
        {"agblocks": 0, "rextents": 1}, {"rextents": 1, "inoalignmt": 0},
        {"inoalignmt": 0, "logblocks": 0}, {"logblocks": 0, "imax_pct": 255},
        {"shared_vn": 1, "logsectlog": 255},
    ):
        mutate("precedence " + str(changes), family="precedence", **changes)
    rng = random.Random(seed)
    for index in range(random_count):
        if index % 3 == 0:
            data = bytearray(real)
            for _ in range(1 + index % 5):
                data[rng.randrange(512)] = rng.randrange(256)
            add(f"seed {seed} random repaired bytes {index}", repair(data), "seeded")
        elif index % 3 == 1:
            key = rng.choice(tuple(SCHEMA))
            value = rng.randrange(1 << (8 * SCHEMA[key][1]))
            mutate(f"seed {seed} field {index} {key}", family="seeded", **{key: value})
        else:
            A = rng.randrange(4096, 70000)
            N = rng.randrange(1, 20)
            tail = rng.randrange(64, A + 1)
            g = rng.randrange(N)
            extent = tail if g == N - 1 else A
            a = rng.randrange(1, extent)
            mutate(f"seed {seed} valid geometry {index}", family="seeded", agblocks=A, agcount=N,
                   agblklog=(A - 1).bit_length(), dblocks=(N - 1) * A + tail,
                   logstart=g * 2 ** (A - 1).bit_length() + a, logblocks=rng.randrange(1, extent - a + 1))
    # Paired unrepaired cases make the old probe's precedence observable for each
    # new checking family without doubling every source fixture.
    for key, value in (("blocklog", 255), ("inodelog", 255), ("agblocks", 0), ("agblklog", 255),
                       ("dblocks", U64), ("logstart", U64), ("logblocks", 0), ("incompat", U32),
                       ("features2", 0), ("versionnum", 0xb4a5 ^ 0x20), ("rextsize", 0),
                       ("spino_align", 3), ("inprogress", 1), ("shared_vn", 1)):
        add(f"paired unrepaired {key}", change(real, repair_crc=False, **{key: value}), "unrepaired")
    require(len(result) <= 768, "bounded header corpus")
    return result


def array(name, data, const=True):
    return f"{'const ' if const else ''}array<u8,{len(data)}> {name}={{" + ",".join(f"{value}u8" for value in data) + "};"


def projections(report="r"):
    code = f"const fs::XfsProbeResult p={report}.probe();const fs::XfsHeaderObservations raw={report}.raw();"
    code += f"const fs::XfsFeatureDiagnostics masks={report}.masks();"
    code += "const fs::XfsFeatureMasks unsupported=masks.unsupported();const fs::XfsFeatureMasks unknown=masks.unknown();"
    code += f"const fs::XfsGeometryFacts facts={report}.facts();"
    for group, (typename, _) in GROUPS.items():
        code += f"const fs::{typename} {group}=facts.{group}();"
    return code


def scalar_expressions():
    return ([f"p.features_{name}()" for name in MASKS]
            + [f"raw.{name}()" for name in ("versionnum", "features2", "bad_features2")]
            + [f"{kind}.{name}()" for kind in ("unsupported", "unknown") for name in MASKS]
            + [f"{group}.{name}()" for group, (_, names) in GROUPS.items() for name in names])


def shared_renderer():
    code = "auto geometry_scalar(fs::XfsGeometryReport r,i64 slot)->u64{" + projections()
    for slot, expression in enumerate(scalar_expressions(), 3):
        code += f"if(slot=={slot}){{return {expression};}}"
    code += f"return {U64}u64;}}\n"
    return code


def render_case(case, function):
    expected = case.expected
    code = f"auto {function}(i64 slot)->u64{{" + array("bytes", case.data)
    code += f"const array<u8,{len(case.data)}> original=bytes;const {SPAN} view=borrow_bytes(bytes);"
    code += "const fs::XfsGeometryReport r=fs::inspect_xfs_v5_512_geometry(view);"
    code += "i64 i=0;while(i<view.size()){if(bytes[i]!=original[i]){return 170u64;}i=i+1;}"
    code += f"if(slot==0){{if(r.status()==fs::XfsGeometryStatus::{expected.status}){{return 1u64;}}return 0u64;}}"
    code += f"if(slot==1){{if(r.issue()==fs::XfsGeometryIssue::{expected.issue}){{return 1u64;}}return 0u64;}}"
    code += "const fs::XfsProbeResult p=r.probe();"
    code += f"if(slot==2){{if(p.status()==fs::XfsProbeStatus::{expected.probe_status}){{return 1u64;}}return 0u64;}}"
    code += "if(slot==42){const fs::XfsGeometryReport repeated=fs::inspect_xfs_v5_512_geometry(view);"
    code += "if(r.status()!=repeated.status()){return 171u64;}if(r.issue()!=repeated.issue()){return 172u64;}"
    code += "const fs::XfsProbeResult direct=fs::probe_xfs_v5_512(view);const fs::XfsProbeResult other=repeated.probe();"
    code += "if(p.status()!=direct.status()){return 173u64;}if(p.status()!=other.status()){return 174u64;}"
    for name in MASKS:
        code += f"if(p.features_{name}()!=direct.features_{name}()){{return 175u64;}}"
    code += "i64 s=3;while(s<42){if(geometry_scalar(r,s)!=geometry_scalar(repeated,s)){return 176u64;}s=s+1;}"
    code += "i64 j=0;while(j<view.size()){if(bytes[j]!=original[j]){return 177u64;}j=j+1;}return 1u64;}"
    code += "return geometry_scalar(r,slot);}\n"
    return code


class Suite(BoundedSuite):
    def __init__(self, compiler, directory, timeout, sanitized, module_root=None):
        super().__init__(compiler, directory, timeout, sanitized)
        self.module_root = module_root or ROOT / "library"
        self.families = Counter()
        self.scalar_count = 0

    def execute_slots(self, directory, functions, slots=43):
        assembly = [".text", ".globl _start", "_start:"]
        for function in functions:
            for slot in range(slots):
                assembly += [f"movq ${slot},%rdi", f"call {function}", "pushq %rax", "movq $1,%rax",
                             "movq $1,%rdi", "movq %rsp,%rsi", "movq $8,%rdx", "syscall", "addq $8,%rsp"]
        assembly += ["movq $60,%rax", "xorq %rdi,%rdi", "syscall", '.section .note.GNU-stack,"",@progbits']
        (directory / "entry.s").write_text("\n".join(assembly) + "\n")
        self.command(["as", "--64", directory / "compiled.s", "-o", directory / "program.o"], directory, "assemble")
        self.command(["as", "--64", directory / "entry.s", "-o", directory / "entry.o"], directory, "entry")
        self.command(["ld", "-o", directory / "program", directory / "entry.o", directory / "program.o"], directory, "link")
        return Observation(self.command([directory / "program"], directory, "native", native=True), exit_code=0)

    def check_headers(self, cases):
        require(1 <= len(cases) <= MAX_BATCH, "case batch bound")
        functions = [f"geometry_case_{i}" for i in range(len(cases))]
        source = PREFIX + shared_renderer() + "".join(render_case(case, function) for case, function in zip(cases, functions))
        expected = [Case(case.name + " / " + leaf, "", value)
                    for case in cases for leaf, value in zip((*LEAVES, "repeat_direct_probe_unchanged"), (*case.expected.scalars(), 1))]
        directory = self.directory / f"batch-{self.batches:04d}"
        self.batches += 1
        self.run_source(directory, source, expected, functions, slots=True,
                        details={"headers": [{"name": case.name, "family": case.family,
                                              "input_sha256": hashlib.sha256(case.data).hexdigest(),
                                              "expected": asdict(case.expected)} for case in cases]})
        self.count += len(cases)
        self.scalar_count += len(expected)
        self.families.update(case.family for case in cases)
        print(f"PASS XFS geometry batch {self.batches}: {len(cases)} headers, {len(expected)} raw observations", flush=True)

    def run_source(self, directory, source, expected, functions, slots=False, details=None):
        directory.mkdir(parents=True, exist_ok=False)
        path = directory / "input.au"
        path.write_text(source)
        receipt = {"status": "running", "source_sha256": sha(path), "source_bytes": len(source.encode()),
                   "compiler_sha256": sha(self.compiler), **(details or {})}
        started = time.monotonic()
        try:
            require(len(source.encode()) <= MAX_SOURCE, "source byte budget")
            self.command([self.compiler, "--module-root", self.module_root, path, "-o", directory / "compiled.s"], directory, "compiler", compiler=True)
            require(path.read_text() == source, "compiler changed fixture")
            observed = self.execute_slots(directory, functions) if slots else self.execute(directory, functions)
            validate_values(observed, expected)
            receipt["observations"] = [{"name": case.name, "expected": case.expected,
                                        "observed": int.from_bytes(observed.output[i * 8:i * 8 + 8], "little")}
                                       for i, case in enumerate(expected)]
            receipt["status"] = "passed"
        except Exception as error:
            receipt.update(status="failed", error=str(error))
            raise AssertionError(f"geometry failure; retained at {directory}: {error}") from error
        finally:
            receipt["seconds"] = round(time.monotonic() - started, 6)
            (directory / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
            self.receipts.append(receipt)

    def reject(self, label, source, index, expected_text):
        directory = self.directory / f"reject-{index:03d}"
        directory.mkdir()
        path, output = directory / "input.au", directory / "compiled.s"
        path.write_text(source)
        sentinel = b"prior artifact must survive semantic rejection\n"
        output.write_bytes(sentinel)
        receipt = {"label": label, "source_sha256": sha(path), "compiler_sha256": sha(self.compiler),
                   "status": "running"}
        try:
            require(len(source.encode()) <= MAX_SOURCE, "rejection source bound")
            try:
                self.command([self.compiler, "--module-root", self.module_root, path, "-o", output],
                             directory, "compiler", compiler=True)
            except AssertionError:
                command = json.loads((directory / "compiler.command.json").read_text())
                diagnostic = (directory / "compiler.stderr").read_text()
                require(command.get("returncode") == 1, "rejection must be normal exit1, not crash/timeout")
                require(
                    re.fullmatch(
                        rf"(?:{re.escape(str(path))}:[1-9][0-9]*:[1-9][0-9]*|aurorac): error "
                        r"AU(?:1001|200[12]|3001|4001): [^\n]+\n",
                        diagnostic,
                    ) is not None,
                    "rejection must be compiler diagnostic",
                )
                require(any(word in diagnostic.lower() for word in expected_text), "unexpected rejection diagnostic")
                require("sanitizer" not in diagnostic.lower(), "sanitizer failure is not rejection")
            else:
                raise AssertionError("invalid API use compiled: " + label)
            require(output.read_bytes() == sentinel, "semantic rejection replaced existing artifact")
            require(path.read_text() == source, "semantic rejection modified source")
            receipt["status"] = "passed"
        except Exception as error:
            receipt.update(status="failed", error=str(error))
            raise
        finally:
            (directory / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


def fabricated_constructor():
    source, values = "", {}
    count = 0
    for group, (typename, names) in GROUPS.items():
        arguments = []
        for name in names:
            values[name] = (1 << 63) + count * 65537 + 17
            arguments.append(str(values[name]) + "u64")
            count += 1
        source += f"const fs::{typename} {group}=fs::{typename}(" + ",".join(arguments) + ");"
    source += "const fs::XfsGeometryFacts facts=fs::XfsGeometryFacts(blocks,inodes,data,ags,log);"
    source += "const fs::XfsProbeResult probe=fs::XfsProbeResult(fs::XfsProbeStatus::checksum_mismatch,1u64,2u64,3u64,4u64);"
    source += "const fs::XfsHeaderObservations raw=fs::XfsHeaderObservations(5u64,6u64,7u64);"
    source += "const fs::XfsFeatureMasks unsupported=fs::XfsFeatureMasks(8u64,9u64,10u64,11u64);"
    source += "const fs::XfsFeatureMasks unknown=fs::XfsFeatureMasks(12u64,13u64,14u64,15u64);"
    source += "const fs::XfsFeatureDiagnostics masks=fs::XfsFeatureDiagnostics(unsupported,unknown);"
    return source, values


def semantic_cases(suite, real):
    sizes = {**{typename: len(names) * 8 for typename, names in GROUPS.values()},
             "XfsGeometryFacts": 192, "XfsHeaderObservations": 24, "XfsFeatureMasks": 32,
             "XfsFeatureDiagnostics": 64, "XfsGeometryReport": 336}
    source, functions, expected = PREFIX, [], []
    for typename, size in sizes.items():
        for expression, label, value in ((f"size_of(fs::{typename})", "size", size),
                                          (f"reflect_size(type_id(fs::{typename}))", "metadata size", size),
                                          (f"field_count(fs::{typename})", "visible fields", 0),
                                          (f"reflect_field_count(type_id(fs::{typename}))", "metadata visible fields", 0)):
            function = f"layout_{len(functions)}"
            functions.append(function)
            source += f"auto {function}()->u64{{return u64({expression});}}\n"
            expected.append(Case(typename + " " + label, "", value))
    suite.run_source(suite.directory / "layout", source, expected, functions,
                     details={"layout_scope": "native size and runtime metadata; every private scalar consumed separately in functional fixtures"})

    prelude, fabricated = fabricated_constructor()
    source = PREFIX + shared_renderer()
    functions, expected = [], []
    for status in ("probe_rejected", "unsupported_feature_profile", "unsupported_layout", "offline_state_indicated",
                   "inconsistent_header", "size_unrepresentable", "header_geometry_consistent"):
        function = "fabricated_" + status
        functions.append(function)
        source += f"auto {function}()->u64{{" + prelude
        source += f"const fs::XfsGeometryReport supplied=fs::XfsGeometryReport(fs::XfsGeometryStatus::{status},fs::XfsGeometryIssue::none,probe,raw,masks,facts);"
        source += "const fs::XfsGeometryReport copied=supplied;"
        values = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
                  *[fabricated[name] if status == "header_geometry_consistent" else 0 for name in FACTS])
        for slot, value in enumerate(values, 3):
            source += f"if(geometry_scalar(copied,{slot})!={value}u64){{return {slot}u64;}}"
        source += f"return {U64}u64;}}\n"
        expected.append(Case("fabricated " + status + " copied and masked all24 facts", "", U64))
    source += "auto detached()->fs::XfsGeometryReport{" + array("owner", real, const=False)
    source += "const fs::XfsGeometryReport r=fs::inspect_xfs_v5_512_geometry(borrow_bytes(owner));owner[0]=0u8;return r;}\n"
    source += "auto detached_copy()->u64{const fs::XfsGeometryReport r=detached();const fs::XfsGeometryReport copy=r;"
    source += "const fs::XfsGeometryFacts retained=r.facts();const fs::XfsAgFacts retained_ags=retained.ags();"
    source += array("different", change(real, agblocks=30000, dblocks=120000))
    source += "const fs::XfsGeometryReport other=fs::inspect_xfs_v5_512_geometry(borrow_bytes(different));"
    source += "const fs::XfsGeometryFacts other_facts=other.facts();const fs::XfsAgFacts other_ags=other_facts.ags();"
    source += "if(other_ags.ag_blocks()!=30000u64){return 101u64;}if(retained_ags.ag_blocks()!=32768u64){return 102u64;}"
    for slot, value in enumerate(oracle(real).scalars()[3:], 3):
        source += f"if(geometry_scalar(copy,{slot})!={value}u64){{return {slot}u64;}}"
    source += f"return {U64}u64;}}\n"
    functions.append("detached_copy")
    expected.append(Case("copied report outlives owner mutation and function return", "", U64))
    suite.run_source(suite.directory / "fabricated-and-copied", source, expected, functions)

    rejects = []
    constructors = {typename: "0u64," * (len(names) - 1) + "0u64" for typename, names in GROUPS.values()}
    for group, (typename, names) in GROUPS.items():
        rejects.append((typename + " privacy", PREFIX + f"auto test()->u64{{const fs::{typename} r=fs::{typename}({constructors[typename]});return r._{names[0]};}}", ("private", "access")))
    for label, tail in (
        ("facts group privacy", "const fs::XfsBlockFacts hidden=facts._blocks;return 1u64;}"),
        ("raw observation privacy", "return raw._versionnum;}"),
        ("feature mask privacy", "return unsupported._compat;}"),
        ("diagnostic group privacy", "const fs::XfsFeatureMasks hidden=masks._unknown;return 1u64;}"),
    ):
        rejects.append((label, PREFIX + "auto test()->u64{" + prelude + tail, ("private", "access")))
    report_prefix = PREFIX + "auto test()->u64{" + array("bytes", real)
    report_prefix += "const fs::XfsGeometryReport r=fs::inspect_xfs_v5_512_geometry(borrow_bytes(bytes));"
    for label, tail, words in (
        ("report private status", "return r._status;}", ("private", "access")),
        ("report private facts", "const fs::XfsGeometryFacts f=r._facts;return 1u64;}", ("private", "access")),
        ("status has no numeric conversion", "return u64(r.status());}", ("conversion", "convert", "u64", "enum")),
        ("issue has no numeric conversion", "return u64(r.issue());}", ("conversion", "convert", "u64", "enum")),
        ("copied facts not a span", f"const {SPAN} view=r.facts();return 1u64;}}", ("type", "span", "expected")),
        ("nominal group types", "const fs::XfsBlockFacts b=r.raw();return 1u64;}", ("type", "expected")),
        ("private helper inaccessible", "return fs::xfs_geometry_read32(borrow_bytes(bytes),4);}", ("private", "visible", "unknown")),
    ):
        rejects.append((label, report_prefix + tail, words))
    rejects.append(("span return excluded by callable type surface", PREFIX + f"auto escape()->{SPAN}{{" + array("bytes", real) + "return borrow_bytes(bytes);}", ("only scalar function results or scalar-field class values are supported",)))
    for index, (label, program, words) in enumerate(rejects):
        suite.reject(label, program, index, words)
    print(f"PASS XFS semantic controls: {len(sizes) * 4} layout observations, {len(functions)} copied/fabricated cases, {len(rejects)} rejections", flush=True)
    return {"layout_observations": len(sizes) * 4, "copy_fabricated_cases": len(functions), "semantic_rejections": len(rejects)}


def mutation_controls(suite, real):
    """Mutated library copies must fail ordinary native tests, never pass as input errors.

    A compiler/tool crash or timeout is a failed control, not a mutation kill.
    A native signal remains a failed native invocation and is explicitly recorded
    as the guard regression this negative control was designed to expose.
    Redundant guards are source-audited below, not misreported as killed mutations.
    """
    original = (ROOT / "library/fs/xfs_geometry.au").read_text()
    original_sha = hashlib.sha256(original.encode()).hexdigest()
    mutations = []
    corpus = {case.name: case for case in header_cases(real, SEED, 0)}

    def sample(label, **changes):
        data = change(real, **changes)
        return Header(label, data, oracle(data), "mutation_witness")

    def control(label, replacements, case):
        candidate = original
        for before, after in replacements:
            require(candidate.count(before) == 1, "mutation anchor must occur once: " + label + " / " + before)
            candidate = candidate.replace(before, after, 1)
        mutations.append((label, candidate, case, replacements))

    def disable(label, condition, case):
        control(label, [("if (" + condition + ") {", "if (false) {")], case)

    for label, condition, name in (
        ("required version", "(raw.versionnum() & 46240u64) != 46240u64", "required version bit 5"),
        ("required features2", "(raw.features2() & 394u64) != 394u64", "features2 bit 1"),
        ("excluded version", "(raw.versionnum() & (65535u64 ^ 48293u64)) != 0u64", "extra version bit 8"),
        ("excluded features2", "(raw.features2() & (4294967295u64 ^ 394u64)) != 0u64", "features2 bit 9"),
        ("NEEDSREPAIR is offline", "(probe.features_incompat() & 16u64) != 0u64", "incompat single bit 4"),
        ("unknown bit admission", "(unsupported.compat() | unsupported.ro_compat() | unsupported.incompat() | unsupported.log_incompat()) != 0u64", "compat single bit 31"),
        ("FTYPE required", "(probe.features_incompat() & 1u64) == 0u64", "missing FTYPE"),
        ("features2 mirror", "raw.features2() != raw.bad_features2()", "mirror mismatch"),
        ("offline operation", "bytes.at(126) != 0u8", "inprogress=1"),
        ("realtime excluded", "xfs_geometry_read64(bytes, 16) != 0u64", "rblocks=1"),
        ("external log excluded", "xfs_geometry_read64(bytes, 48) == 0u64", "logstart=0"),
        ("stripes excluded", "(xfs_geometry_read32(bytes, 184) | xfs_geometry_read32(bytes, 188)) != 0u64", "unit=1"),
        ("logsunit limit", "xfs_geometry_read32(bytes, 196) > 1u64", "logsunit=2"),
        ("quota excluded", "(xfs_geometry_read16(bytes, 176) | u64(bytes.at(178))) != 0u64", "qflags=1"),
        ("block shift upper guard", "block_log > 16u64", "blocklog=64"),
        ("block power relation", "block_bytes != (1u64 << i64(block_log))", "blocksize=4095"),
        ("inode shift upper guard", "inode_log > 11u64", "inodelog=64"),
        ("inode zero divisor relation", "inode_bytes != (1u64 << i64(inode_log))", "inodesize=0"),
        ("inodes per block relation", "xfs_geometry_read16(bytes, 106) != block_bytes / inode_bytes", "inopblock=0"),
        ("inode logarithm difference", "u64(bytes.at(123)) != block_log - inode_log", "inopblog=255"),
        ("directory shift range", "directory_log > 16u64 - block_log", "dirblklog=255"),
        ("AG logarithm ceil relation", "ag_log != u64(std::bit_width(ag_blocks - 1u64)))", "agblklog=14"),
        ("short last AG minimum", "last_ag_blocks < 64u64", "last AG blocks 63"),
        ("realtime zero relations", "(xfs_geometry_read64(bytes, 24) | xfs_geometry_read32(bytes, 92) | u64(bytes.at(125)) | xfs_geometry_read64(bytes, 152)) != 0u64", "rextents=1"),
        ("realtime extent minimum", "realtime_extent_bytes < 4096u64", "rextsize=0"),
        ("realtime extent maximum", "realtime_extent_bytes > 1073741824u64", "rextsize=262145"),
        ("sparse divisor relation", "inode_alignment % sparse_alignment != 0u64", "spino_align=3"),
        ("absent log sector declarations", "(log_sector_bytes | log_sector_log) != 0u64", "logsectsize=512"),
        ("present log sector size", "log_sector_bytes != 512u64", "declared log sector 0/9"),
        ("present log sector log", "log_sector_log != 9u64", "declared log sector 512/255"),
        ("log zero count", "log_blocks == 0u64", "logblocks=0"),
        ("log count maximum", "log_blocks > 1048576u64", "log byte/count edge B1024 L1048577"),
        ("log byte maximum", "log_blocks * block_bytes > 2136997888u64", "log byte/count edge B4096 L521729"),
        ("encoded gap subtraction guard", "log_ag_block >= actual_ag_blocks", "nonpower encoded gap 32767"),
        ("log must stay inside one AG", "log_blocks > actual_ag_blocks - log_ag_block", "log range g2 a7 len32762"),
        ("imax limit", "bytes.at(127) > 100u8", "imax_pct=101"),
        ("shared version limit", "bytes.at(179) != 0u8", "shared_vn=1"),
    ):
        # The condition string includes every closing delimiter of the expression.
        if label == "AG logarithm ceil relation":
            condition = "ag_log != u64(std::bit_width(ag_blocks - 1u64))"
        disable(label, condition, corpus[name])
    disable("data byte overflow", "data_blocks > maximum / block_bytes", corpus[f"data representability edge {U64 // 4096 + 1}"])
    disable("block lower bound", "block_log < 10u64", sample("coherent512block", blocksize=512, blocklog=9,
            inopblock=1, inopblog=0, rextsize=8, inoalignmt=64, spino_align=4, logblocks=64))
    disable("inode lower bound", "inode_log < 8u64", sample("coherent1byteinode", inodesize=1, inodelog=0,
            inopblock=4096, inopblog=12, inoalignmt=0, spino_align=0))
    disable("inode256 local exclusion", "inode_log == 8u64", sample("coherent256inodealigned", inodesize=256,
            inodelog=8, inopblock=16, inopblog=4, inoalignmt=4, spino_align=4))
    disable("AG byte lower bound", "ag_bytes < 16777216u64", sample("coherent8MiB AG", agblocks=2048,
            agblklog=11, dblocks=8192, logstart=4103, logblocks=64))
    disable("AG byte upper bound", "ag_bytes > 1099511627776u64", sample("coherent over1TiB AG", agblocks=268435457,
            agblklog=29, dblocks=1073741828, logstart=1073741831, logblocks=64))
    disable("AG header sector exclusion", "log_ag_block <= 1536u64 / block_bytes",
            sample("internal log at AG2 header block", logstart=65536, logblocks=1))
    disable("sparse zero chunk range", "sparse_alignment > inode_alignment", sample("nonzero sparse with zero chunk",
            blocksize=65536, blocklog=16, inopblock=128, inopblog=7, inoalignmt=0, spino_align=1, logblocks=64))
    disable("sparse chunk relation", "inode_alignment != (64u64 * inode_bytes) / block_bytes",
            sample("wrong chunk without secondary divisor fault", inoalignmt=7, spino_align=0))
    control("ceil replaced by floor", [("expected_count = expected_count + 1u64;", "expected_count = expected_count + 0u64;")], corpus["last AG blocks 64"])
    control("encoded log address treated as linear", [("const u64 linear_start = log_ag * ag_blocks + log_ag_block;",
            "const u64 linear_start = encoded_start;")], corpus["non-power-of-two AG encoded AG2 block7"])
    control("last AG fact loses shortening", [("ag_blocks * block_bytes, data_blocks - tail_base, tail_base * block_bytes);",
            "ag_blocks * block_bytes, ag_blocks, tail_base * block_bytes);")], corpus["last AG blocks 64"])
    control("sparse zero divisor protection", [("if (sparse_alignment != 0u64) {\n                if (sparse_alignment > inode_alignment)",
            "if (true) {\n                if (sparse_alignment > inode_alignment)")], sample("zero sparse divisor", spino_align=0))
    control("combined last AG range guards", [
        ("if (log_ag == ag_count - 1u64) { actual_ag_blocks = last_ag_blocks; }", "if (false) { actual_ag_blocks = last_ag_blocks; }"),
        ("if (linear_start > data_blocks) {", "if (false) {"),
        ("if (log_blocks > data_blocks - linear_start) {", "if (false) {")], corpus["short tail log 64+1"])
    require(len(mutations) <= 64, "mutation count budget")

    # These guards remain required source obligations. Their individual deletion
    # is mathematically hidden by another checked relation on every disk input;
    # no executable test can honestly claim to distinguish equivalent behavior.
    redundant = {
        "block_bytes < 512u64": "B=2^block_log and block_log>=10 already prove B>=1024.",
        "inode_bytes > block_bytes": "The later inode_log>block_log guard and established powers reject the same cases.",
        "inode_log > block_log": "The prior inode_bytes>block_bytes guard and established powers imply this guard.",
        "ag_blocks == 0u64": "Minimum nominal AG bytes rejects A=0 before subtraction/division.",
        "ag_count == 0u64": "D>0 and expected_count equality reject N=0 before N-1.",
        "data_blocks == 0u64": "N>0 and expected_count equality reject D=0.",
        "ag_blocks > maximum / block_bytes": "u32 A times B<=2^16 fits u64.",
        "ag_log > 30u64": "A*B<=2^40 and B>=2^10 prove A<=2^30; bit_width equality already checked.",
        "quotient > 4294967295u64": "Untruncated u64 expected_count cannot equal decoded u32 N; A>=256 also bounds q+1.",
        "quotient == 4294967295u64": "With remainder, untruncated expected_count exceeds any disk N.",
        "ag_count != expected_count": "Tail64..A and tail=(D-(N-1)*A) independently force ceil(D/A)=N.",
        "ag_count - 1u64 > maximum / ag_blocks": "Two u32 values have product below2^64.",
        "tail_base > data_blocks": "N=ceil(D/A) with A,D>0 establishes tail_base<D.",
        "last_ag_blocks > ag_blocks": "The established exact ceil count proves tail<=A.",
        "tail_base > maximum / block_bytes": "tail_base<D and successful D*B representability imply this product fits.",
        "realtime_extent_blocks > maximum / block_bytes": "u32 extent blocks times B<=2^16 fits u64.",
        "inode_bytes > maximum / 64u64": "Admitted inode_bytes<=2048.",
        "log_blocks > maximum / block_bytes": "u32 log blocks times B<=2^16 fits u64.",
        "log_ag >= ag_count": "Later global linear range rejects g>=N for A>0; earlier guard prevents unnecessary arithmetic.",
        "log_ag > maximum / ag_blocks": "g<N<=u32 and A<=u32.",
        "log_base > maximum - log_ag_block": "g<N plus a<actual_AG gives rawStart<D<=u64.",
        "linear_start > data_blocks": "g<N plus a<actual_AG independently bounds linear_start<D.",
        "log_blocks > data_blocks - linear_start": "Same-actual-AG extent range independently proves global range.",
        "linear_start > maximum / block_bytes": "linear_start<D and D*B fits u64.",
    }
    for condition in redundant:
        require("if (" + condition + ") {" in original, "audited source guard missing: " + condition)
    audits = {"source_sha256": original_sha, "individual_guard_deletion_not_observable": redundant,
              "count_truncation_note": "Truncating expected_count alone is hidden by quotient checks and independently correct last-AG bounds. No false mutation kill is claimed.",
              "tail_note": "Removing only actual-tail selection is hidden by the independent global extent bound; combined range weakening is exercised separately."}
    controls = []
    for index, (label, candidate, case, replacements) in enumerate(mutations):
        directory = suite.directory / f"mutation-{index:03d}"
        library = directory / "library"
        for path in ("std/binary.au", "std/checksum.au", "std/bit.au", "fs/xfs_probe.au"):
            destination = library / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / "library" / path, destination)
        (library / "fs/xfs_geometry.au").write_text(candidate)
        mutated_suite = Suite(suite.compiler, directory, suite.timeout, suite.sanitized_compiler, library)
        receipt = {"label": label, "source_sha256": hashlib.sha256(candidate.encode()).hexdigest(),
                   "baseline_sha256": original_sha, "replacements": replacements, "witness": case.name,
                   "status": "running"}
        try:
            try:
                mutated_suite.check_headers([case])
            except AssertionError as error:
                run = directory / "batch-0000"
                require(json.loads((run / "compiler.command.json").read_text()).get("returncode") == 0,
                        "mutation control compiler failed; not a detected library regression")
                native = json.loads((run / "native.command.json").read_text())
                require(not native.get("timeout"), "mutation timeout fails the control")
                code = native.get("returncode")
                require(code in (0, -signal.SIGILL), "unrelated native signal or nonzero exit fails the control")
                receipt.update(status="detected", native_returncode=code,
                               detection="full-output mismatch" if code == 0 else "native signal is failed library execution",
                               error=str(error))
            else:
                raise AssertionError("mutation escaped its selected witness: " + label)
        finally:
            (directory / "mutation.json").write_text(json.dumps(receipt, indent=2) + "\n")
            controls.append(receipt)
    require(sha(ROOT / "library/fs/xfs_geometry.au") == original_sha, "mutation controls changed baseline source")
    (suite.directory / "mutation-audit.json").write_text(json.dumps({**audits, "controls": controls}, indent=2) + "\n")
    print(f"PASS XFS mutation controls: {len(controls)} detected regressions; {len(redundant)} source-audited redundant guards", flush=True)
    return {"detected": len(controls), "source_audited_guards": len(redundant)}


def self_tests(real):
    for name, data, expected in VECTORS:
        require(crc32c_reference(data) == expected, "GF(2) CRC anchor " + name)
    require(repair(real) == real, "exact fixture GF(2) CRC")
    observed = oracle(real)
    require(observed.status == "header_geometry_consistent", "real schema acceptance")
    anchors = {"block_bytes": 4096, "sector_bytes": 512, "inode_bytes": 512, "inodes_per_block": 8,
               "data_blocks": 131072, "claimed_data_bytes": 536870912, "claimed_data_sectors": 1048576,
               "ag_blocks": 32768, "ag_count": 4, "ag_bytes": 134217728, "last_ag_blocks": 32768,
               "last_ag_start_bytes": 402653184, "log_start_encoded": 65543, "log_ag": 2,
               "log_ag_block": 7, "log_start_bytes": 268464128, "log_bytes": 67108864,
               "effective_log_sector_bytes": 512, "directory_block_bytes": 4096,
               "block_log": 12, "sector_log": 9, "inode_log": 9, "inodes_per_block_log": 3, "ag_block_log": 15}
    require(tuple(anchors[name] for name in FACTS) == observed.facts, "all24 real fact anchors")
    require(observed.probe_masks == (0, 15, 43, 0) and observed.raw == (0xb4a5, 0x18a, 0x18a), "real masks/raw")
    require(fields(real)["rbmino"] == 129 and fields(real)["rsumino"] == 130, "real nonzero realtime inode numbers")
    good = Observation(U64.to_bytes(8, "little"), exit_code=0)
    expected = [Case("complete width", "", U64)]
    validate_values(good, expected)
    for bad in (replace(good, output=good.output[:1]), replace(good, output=good.output + b"x"),
                replace(good, exit_code=1), replace(good, terminal_signal=signal.SIGILL),
                replace(good, terminal_signal=signal.SIGSEGV), replace(good, terminal_signal=signal.SIGFPE),
                replace(good, output=(U64 ^ (1 << 63)).to_bytes(8, "little"))):
        try:
            validate_values(bad, expected)
        except AssertionError:
            continue
        raise AssertionError("malformed native observation accepted")
    for case in header_cases(real, SEED, 12):
        require(len(case.expected.scalars()) == 42, "all42 outputs")
        require(all(0 <= value <= U64 for value in case.expected.scalars()), "oracle representability")
        if case.expected.status != "header_geometry_consistent":
            require(case.expected.facts == (0,) * 24, "complete zero failure facts")
        if case.expected.status == "header_geometry_consistent":
            require(case.expected.facts[FACTS.index("ag_block_log")] <= 30, "admitted AG shift bound")
    print("PASS XFS schema/CRC/transport/full-width harness controls (active under Python -O)", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", nargs="?", type=Path)
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--sanitized-compiler", action="store_true")
    add_identity_arguments(parser)
    parser.add_argument("--self-test-only", action="store_true")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--random-count", type=int, default=48)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--case-filter", help="substring selection for diagnosis; not the complete acceptance gate")
    parser.add_argument("--mutation-controls", action="store_true", help="also test bounded mutated copies of the module")
    parser.add_argument("--mutations-only", action="store_true", help="diagnostic mutation run; omits the complete acceptance gate")
    args = parser.parse_args()
    validate_identity_selection(args, preflight=args.self_test_only)
    if not args.self_test_only:
        require(args.compiler is not None, "compiler required")
        compiler = args.compiler.resolve(strict=True)
        identity = resolve_identity(args, compiler, ROOT)
        expected_pin = identity.sha256
    require(0 <= args.random_count <= 128, "seeded case budget")
    require(5 <= args.timeout <= 90, "native timeout bound")
    require(sha(ROOT / "docs/xfs-geometry-proposal.md") == PROPOSAL_SHA, "approved proposal identity")
    real = real_fixture()
    self_tests(real)
    if args.self_test_only:
        return
    if args.sanitized_compiler:
        require(os.environ.get("ASAN_OPTIONS") in (
            "detect_leaks=0:halt_on_error=1",
            "detect_leaks=0:halt_on_error=1:abort_on_error=1"),
            "explicit retained fatal ASan options required")
    (ROOT / "build").mkdir(exist_ok=True)
    directory = args.artifacts.resolve() if args.artifacts else Path(tempfile.mkdtemp(prefix="xfs-geometry-", dir=ROOT / "build"))
    if args.artifacts:
        directory.mkdir(parents=True, exist_ok=False)
    relevant_inputs = ("tests/compiler/xfs_geometry.py", "tests/compiler/utf8.py", "tests/compiler/storage_binary.py",
                       "tests/compiler/readonly_spans.py", "tests/compiler/unsigned_oracle.py",
                       "fixtures/xfs-offline/verify_native.py", "fixtures/xfs-offline/superblock-v5-512.hex",
                       "docs/xfs-geometry-proposal.md", "library/fs/xfs_geometry.au", "library/fs/xfs_probe.au",
                       "library/std/binary.au", "library/std/checksum.au", "library/std/bit.au")
    input_hashes = {path: sha(ROOT / path) for path in relevant_inputs}
    manifest = {"compiler": str(compiler), "compiler_sha256": sha(compiler), "compiler_identity": identity.record(),
                "explicit_compiler_pin": args.compiler_sha256, "input_sha256": input_hashes,
                "test_sha256": sha(Path(__file__)), "module_sha256": sha(ROOT / "library/fs/xfs_geometry.au"),
                "probe_sha256": sha(ROOT / "library/fs/xfs_probe.au"), "proposal_sha256": PROPOSAL_SHA,
                "seed": args.seed, "seeded_count": args.random_count, "case_filter": args.case_filter,
                "mutations_only": args.mutations_only,
                "python": sys.version, "optimized_python": not __debug__, "asan_options": os.environ.get("ASAN_OPTIONS"),
                "limits": {"cpu_soft_hard_seconds": [10, 11], "tool_wall_seconds": 30,
                           "native_wall_seconds": args.timeout, "regular_file_bytes": 8 << 20,
                           "compiler_address_space_bytes": None if args.sanitized_compiler else 512 << 20,
                           "other_address_space_bytes": 128 << 20, "source_bytes": MAX_SOURCE,
                           "headers_per_batch": MAX_BATCH, "maximum_headers": 768},
                "scope": "finite ordinary native functional evidence; no generated-code sanitizer, filesystem, safety or performance claim",
                "status": "running"}
    suite = Suite(compiler, directory, args.timeout, args.sanitized_compiler)
    try:
        manifest["tools"] = {tool: suite.command([tool, "--version"], directory, tool + "-version").decode()
                             for tool in ("as", "ld")}
        cases = header_cases(real, args.seed, args.random_count)
        if args.case_filter:
            cases = [case for case in cases if args.case_filter in case.name]
        require(cases, "empty selected corpus")
        if not args.mutations_only:
            for start in range(0, len(cases), MAX_BATCH):
                suite.check_headers(cases[start:start + MAX_BATCH])
        semantics = semantic_cases(suite, real) if not args.case_filter and not args.mutations_only else {"omitted": "diagnostic selection"}
        mutations = mutation_controls(suite, real) if args.mutation_controls or args.mutations_only else {"not_run": True}
        identity.verify()
        manifest.update(status="passed", headers=suite.count, raw_observations=suite.scalar_count,
                        families=dict(suite.families), batches=suite.batches, semantic_controls=semantics, mutation_controls=mutations)
    except Exception as error:
        manifest.update(status="failed", error=str(error), headers=suite.count)
        raise
    finally:
        changed = [path for path, checksum in input_hashes.items() if sha(ROOT / path) != checksum]
        if sha(compiler) != expected_pin:
            changed.append(str(compiler))
        if changed:
            manifest.update(status="failed", changed_inputs=changed)
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        require(not changed, "inputs changed during gate: " + str(changed))
    print("PASS XFS geometry: " + json.dumps({"headers": suite.count, "raw_observations": suite.scalar_count,
                                             "artifacts": str(directory)}), flush=True)


if __name__ == "__main__":
    main()
