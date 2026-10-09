#!/usr/bin/env python3
"""Independent full-width native package.graph differential oracle.

The reference was frozen before graph.au inspection. Every result is observed
as exact u64 words; host assembly is a bootstrap transport, never a source API.
"""

from __future__ import annotations
import argparse, gzip, hashlib, itertools, json, os, random, re
import shutil, sys, tempfile, time
from pathlib import Path
from dataclasses import dataclass

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from package_profiles import (
    add_identity_arguments,
    developer_artifacts,
    finalize_selected_identity,
    profile_record,
    resolve_identity,
    select_cases,
    validate_identity_selection,
)
from package_native_runner import PackageRunner, finalize_report, safe_receipt

CONTRACT_SHA256 = "2272fba3b7163550f5dabef95c5b54c0d1039063b84545ef0c0b20f93928e01c"
REFERENCE_SHA256 = "6a54b890a7b33abd378c9ca7a0de05c179cb4448c2fc2daaf5a33c677aeafa42"
CAP, FLOOR, RESERVE = 256 << 20, 1 << 30, 24 << 20
SOURCE_CAP, BATCH = 64 << 10, 96
U64 = (1 << 64) - 1
IMIN, IMAX = -(1 << 63), (1 << 63) - 1
COUNT_FALLBACK = IMIN + 123456789
INDEX_FALLBACK = -81985529216486896
RANK_FALLBACK = IMIN + 918273645
VERSION_FALLBACKS = (U64, 1 << 63, 0xFEDCBA9876543210)
PREFIX = "module graph_oracle;import package.graph;import package.manifest;import package.identity;import std.array;\n"
ORDER_RANKS = tuple(range(8)) + (-1, 8, IMIN, IMAX)
ORDER_WIDTH = 2 + len(ORDER_RANKS)
ENTRY_WIDTH = 33


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def candidate_cap(mib):
    require(
        type(mib) is int and 256 <= mib <= 1024,
        "candidate cap must be an integer between 256 and 1024 MiB; increases require explicit aggregate admission",
    )
    return mib << 20


def cap_self_test():
    for mib in (256, 512, 513, 1023, 1024):
        require(candidate_cap(mib) == mib << 20, "candidate cap boundary conversion")
    for mib in (-1, 0, 255, 1025, 1 << 30, True, 512.0, "1024", None):
        try:
            candidate_cap(mib)
        except AssertionError:
            continue
        raise AssertionError("invalid candidate cap accepted")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def signed(x):
    return "(-9223372036854775807-1)" if x == IMIN else str(x)


def artifact_path(value):
    raw = Path(value).absolute()
    require(".." not in raw.parts, "artifact path traversal denied")
    require(not any(p.is_symlink() for p in [raw, *raw.parents]), "symlink output root denied")
    path = raw.resolve(strict=False)
    require(path.is_relative_to(ROOT), "artifacts must remain inside candidate")
    return path


"""Independent graph specification; frozen before graph.au has been read.

Reference choices: byte-line splitting, decimal canonicalization by roundtrip,
and searching all vertex permutations in lexical order. No production scanners
or graph algorithm are imported. Python unbounded integers define range checks.
"""
from dataclasses import dataclass
from itertools import permutations

U32 = (1 << 32) - 1
STATUSES = (
    "success",
    "invalid_count",
    "out_of_range",
    "malformed",
    "duplicate_package",
    "missing_package",
    "version_mismatch",
    "cycle",
    "index_out_of_range",
)


@dataclass(frozen=True)
class Identity:
    name: bytes
    version: tuple


def identity(token):
    chunks = token.split(b"@")
    if len(chunks) != 2:
        return None
    name, numbers = chunks
    if not 1 <= len(name) <= 24 or not 97 <= name[0] <= 122:
        return None
    if name.endswith(b"-") or b"--" in name:
        return None
    if any(not (97 <= c <= 122 or 48 <= c <= 57 or c == 45) for c in name):
        return None
    parts = numbers.split(b".")
    if len(parts) != 3:
        return None
    values = []
    for text in parts:
        if not text or any(not 48 <= c <= 57 for c in text):
            return None
        number = int(text)
        if number > U32 or str(number).encode() != text:
            return None
        values.append(number)
    return Identity(name, tuple(values))


def manifest(data):
    if not 37 <= len(data) <= 615:
        return None
    lines = data.split(b"\n")
    if len(lines) < 4 or lines[:1] != [b"aurora-package 1"] or lines[-2:] != [b"end", b""]:
        return None
    if not lines[1].startswith(b"package "):
        return None
    root = identity(lines[1][8:])
    if root is None:
        return None
    dep_lines = lines[2:-2]
    if len(dep_lines) > 8:
        return None
    deps = []
    for line in dep_lines:
        if not line.startswith(b"depends "):
            return None
        parsed = identity(line[8:])
        if parsed is None:
            return None
        deps.append(parsed)
    if len({x.name for x in (root, *deps)}) != len(deps) + 1:
        return None
    return root, tuple(deps)


def graph(data, offsets, lengths, count):
    if not 0 <= count <= 8:
        return "invalid_count", (), ()
    windows = list(zip(offsets[:count], lengths[:count]))
    if any(o < 0 or n < 0 or o + n > len(data) for o, n in windows):
        return "out_of_range", (), ()
    parsed = tuple(manifest(data[o : o + n]) for o, n in windows)
    if None in parsed:
        return "malformed", (), ()
    roots = tuple(x[0] for x in parsed)
    by_name = {x.name: i for i, x in enumerate(roots)}
    if len(by_name) != count:
        return "duplicate_package", (), ()
    pins = tuple((i, d) for i, (_, deps) in enumerate(parsed) for d in deps)
    if any(d.name not in by_name for _, d in pins):
        return "missing_package", (), ()
    if any(d.version != roots[by_name[d.name]].version for _, d in pins):
        return "version_mismatch", (), ()
    edges = tuple((i, by_name[d.name]) for i, d in pins)
    # Exhaustive mathematical reference: the first valid full permutation in
    # canonical-name lexical order is the uniquely specified output sequence.
    for order in permutations(sorted(range(count), key=lambda i: roots[i].name)):
        ranks = {vertex: rank for rank, vertex in enumerate(order)}
        if all(ranks[d] < ranks[i] for i, d in edges):
            return "success", order, roots
    return "cycle", (), ()


def order_constructor(status, order, count):
    if status == "success" and not (
        0 <= count <= 8 and sorted(order[:count]) == list(range(count)) and all(x == 0 for x in order[count:])
    ):
        return "malformed"
    return status


def entry_constructor(status, ident, count, rank, index):
    if status == "success" and not (ident is not None and 1 <= count <= 8 and 0 <= rank < count and 0 <= index < count):
        return "malformed"
    return status


def make_manifest(name=b"a", version=(0, 0, 0), deps=()):
    def token(n, v):
        return n + b"@" + b".".join(str(x).encode() for x in v)

    return (
        b"aurora-package 1\npackage "
        + token(name, version)
        + b"\n"
        + b"".join(b"depends " + token(n, v) + b"\n" for n, v in deps)
        + b"end\n"
    )


def pack(manifests):
    offsets = []
    lengths = []
    data = b""
    for value in manifests:
        offsets.append(len(data))
        lengths.append(len(value))
        data += value
    return data or b"\0", offsets + [0] * (8 - len(offsets)), lengths + [0] * (8 - len(lengths))


def identity_values(ident):
    return (
        (1, len(ident.name), *ident.version, *ident.name.ljust(24, b"\0"))
        if ident
        else (2, 0, *VERSION_FALLBACKS, *bytes(24))
    )


def order_values(status, order, count):
    good = status == "success"
    return (
        STATUSES.index(status) + 1,
        count if good else COUNT_FALLBACK & U64,
        *(order[r] if good and 0 <= r < count else INDEX_FALLBACK & U64 for r in ORDER_RANKS),
    )


def entry_values(status, ident, count, rank, index):
    good = status == "success"
    return (
        STATUSES.index(status) + 1,
        count if good else COUNT_FALLBACK & U64,
        rank if good else RANK_FALLBACK & U64,
        index if good else INDEX_FALLBACK & U64,
        *identity_values(ident if good else None),
    )


def expected_graph(data, offsets, lengths, count, ranks):
    status, order, roots = graph(data, offsets, lengths, count)
    result = order_values(status, order, count)
    for rank in ranks:
        selected = status if status != "success" or 0 <= rank < count else "index_out_of_range"
        index = order[rank] if selected == "success" else 0
        result += entry_values(selected, roots[index] if selected == "success" else None, count, rank, index)
    return result


@dataclass(frozen=True)
class Case:
    label: str
    body: str
    expected: tuple
    helpers: str = ""
    arguments: tuple = (0, 0)
    block_result: bool = False


def array(name, data):
    require(1 <= len(data) <= 4096, "byte owner must be representable")
    return f"array<u8,{len(data)}> {name}={{" + ",".join(f"{b}u8" for b in data) + "};"


def index_arrays(offsets, lengths):
    return (
        "std::array<i64,8> offsets=std::array<i64,8>();std::array<i64,8> lengths=std::array<i64,8>();"
        + "".join(f"offsets.set({i},{signed(x)});" for i, x in enumerate(offsets) if x)
        + "".join(f"lengths.set({i},{signed(x)});" for i, x in enumerate(lengths) if x)
    )


def finish_body(count, ranks=None):
    # For each complete report the result is copied, and both
    # original owner bytes and caller-owned selection arrays are then poisoned.
    mutate = (
        "i64 p=0;while(p<len(owner)){owner[p]=255u8;p=p+1;}"
        "offsets.set(0,(-9223372036854775807-1));lengths.set(0,9223372036854775807);"
    )
    src = (
        f"if(slot<{ORDER_WIDTH}){{const package::GraphOrderResult original="
        f"package::order_manifests(borrow_bytes(owner),offsets,lengths,{signed(count)});"
        f"const package::GraphOrderResult r=original;"
        + mutate
        + f"const std::array<u64,{ENTRY_WIDTH}> words=observe_order_block(r);return words;}}"
    )
    if ranks is None:
        src += f"const i64 rank=(slot-{ORDER_WIDTH})/{ENTRY_WIDTH};"
    else:
        src += (
            f"const array<i64,{len(ranks)}> ranks={{"
            + ",".join(signed(r) for r in ranks)
            + "};"
            + f"const i64 rank=ranks[(slot-{ORDER_WIDTH})/{ENTRY_WIDTH}];"
        )
    return (
        src + f"const package::GraphEntryResult original="
        f"package::ordered_manifest(borrow_bytes(owner),offsets,lengths,{signed(count)},rank);"
        f"const package::GraphEntryResult r=original;"
        + mutate
        + f"const std::array<u64,{ENTRY_WIDTH}> words=observe_entry_block(r);return words;"
    )


def catalog_case(label, manifests=None, *, data=None, offsets=None, lengths=None, count=None, ranks=None):
    if data is None:
        data, offsets, lengths = pack(manifests)
    count = len(manifests) if count is None else count
    if ranks is None:
        ranks = tuple(range(count)) if 0 < count <= 8 else (0,)
    body = array("owner", data) + index_arrays(offsets, lengths) + finish_body(count, ranks)
    return Case(label, body, expected_graph(data, offsets, lengths, count, ranks), block_result=True)


def shared():
    s = "auto bits(i64 x)->u64{if(x<0){return 9223372036854775808u64+u64(x-(-9223372036854775807-1));}return u64(x);}"
    s += "auto observe_status(package::GraphStatus s)->u64{"
    for n, status in enumerate(STATUSES):
        s += f"if(s==package::GraphStatus::{status}){{return {n + 1}u64;}}"
    s += (
        "return 0u64;}auto observe_identity(package::IdentityResult r,i64 slot)->u64{"
        "if(slot==0){if(r.status()==package::IdentityStatus::success){return 1u64;}"
        "if(r.status()==package::IdentityStatus::malformed){return 2u64;}return 3u64;}"
        "if(slot==1){return u64(r.name_size());}"
    )
    for n, (method, fallback) in enumerate(zip(("major_or", "minor_or", "patch_or"), VERSION_FALLBACKS), 2):
        s += f"if(slot=={n}){{return r.{method}({fallback}u64);}}"
    s += "const std::array<u8,24> name=r.name_bytes_or_zero();return u64(name.at(slot-5));}"
    s += (
        "auto observe_order(package::GraphOrderResult r,i64 slot)->u64{if(slot==0){return observe_status(r.status());}"
        + f"if(slot==1){{return bits(r.package_count_or({signed(COUNT_FALLBACK)}));}}"
    )
    s += (
        f"const array<i64,{len(ORDER_RANKS)}> ranks={{"
        + ",".join(signed(r) for r in ORDER_RANKS)
        + "};"
        + f"return bits(r.catalog_index_or(ranks[slot-2],{signed(INDEX_FALLBACK)}));}}"
    )
    s += "auto observe_entry(package::GraphEntryResult r,i64 slot)->u64{if(slot==0){return observe_status(r.status());}"
    for n, (method, fb) in enumerate(
        (("package_count_or", COUNT_FALLBACK), ("rank_or", RANK_FALLBACK), ("catalog_index_or", INDEX_FALLBACK)), 1
    ):
        s += f"if(slot=={n}){{return bits(r.{method}({signed(fb)}));}}"
    s += "const package::IdentityResult identity=r.identity_or_error();return observe_identity(identity,slot-4);}\n"
    # Keep the existing per-word observers, including their by-value copies.
    # A common bounded result type avoids duplicating large catalog initializers.
    for kind, width, result in (("order", ORDER_WIDTH, "GraphOrderResult"), ("entry", ENTRY_WIDTH, "GraphEntryResult")):
        s += (
            f"auto observe_{kind}_block(package::{result} r)->std::array<u64,{ENTRY_WIDTH}>{{"
            f"static_assert(size_of(std::array<u64,{ENTRY_WIDTH}>)=={ENTRY_WIDTH * 8});"
            f"std::array<u64,{ENTRY_WIDTH}> words=std::array<u64,{ENTRY_WIDTH}>();"
            f"i64 slot=0;while(slot<{width}){{words.set(slot,observe_{kind}(r,slot));slot=slot+1;}}return words;}}\n"
        )
    return s


def generated_graph_body(n):
    size = max(1, n * (37 + 16 * max(0, n - 1)))
    s = array("owner", bytes(size)) + index_arrays([], [])
    if n:
        s += (
            array("header", b"aurora-package 1\npackage ")
            + array("suffix", b"@0.0.0\n")
            + array("depends", b"depends ")
            + array("end", b"end\n")
        )
        s += (
            f"i64 catalog=0;i64 cursor=0;i64 permutation=argument2;while(catalog<{n}){{"
            f"const i64 vertex=permutation%{n};permutation=permutation/{n};offsets.set(catalog,cursor);"
            f"i64 j=0;while(j<25){{owner[cursor]=header[j];cursor=cursor+1;j=j+1;}}"
            f"owner[cursor]=u8(97+vertex);cursor=cursor+1;j=0;"
            f"while(j<7){{owner[cursor]=suffix[j];cursor=cursor+1;j=j+1;}}"
            f"i64 dep=0;while(dep<{n}){{if(dep!=vertex){{i64 edge=vertex*{n - 1}+dep;"
            f"if(dep>vertex){{edge=edge-1;}}if((u64(argument1)&(1u64<<edge))!=0u64){{"
            f"j=0;while(j<8){{owner[cursor]=depends[j];cursor=cursor+1;j=j+1;}}"
            f"owner[cursor]=u8(97+dep);cursor=cursor+1;j=0;"
            f"while(j<7){{owner[cursor]=suffix[j];cursor=cursor+1;j=j+1;}}}}}}dep=dep+1;}}"
            f"j=0;while(j<4){{owner[cursor]=end[j];cursor=cursor+1;j=j+1;}}"
            f"lengths.set(catalog,cursor-offsets.at(catalog));catalog=catalog+1;}}"
        )
    return s + finish_body(n)


def exhaustive_cases():
    cases = []
    for n in range(5):
        edges = list(itertools.permutations(range(n), 2))
        body = generated_graph_body(n)
        for mask in range(1 << len(edges)):
            manifests = [
                make_manifest(
                    bytes([97 + i]),
                    deps=tuple(
                        (bytes([97 + j]), (0, 0, 0)) for bit, (a, j) in enumerate(edges) if a == i and (mask >> bit) & 1
                    ),
                )
                for i in range(n)
            ]
            perms = list(itertools.permutations(range(n))) if n <= 3 else [tuple(range(n))]
            if n == 4 and (mask % 37 == 0 or mask in (0, 4095, 1, 2048)):
                perms.extend((tuple(reversed(range(n))), (2, 0, 3, 1)))
            for perm in dict.fromkeys(perms):
                data, offsets, lengths = pack([manifests[i] for i in perm])
                status, order, roots = graph(data, offsets, lengths, n)
                ranks = tuple(range(n)) if status == "success" and n else (0,)
                expected = expected_graph(data, offsets, lengths, n, ranks)
                encoding = sum(vertex * n**slot for slot, vertex in enumerate(perm))
                cases.append(
                    Case(
                        f"exhaustive/{n}/{mask}/{''.join(map(str, perm))}",
                        body,
                        expected,
                        arguments=(mask, encoding),
                        block_result=True,
                    )
                )
    return cases


def adversarial_cases(*, exhaustive=True):
    cases = []

    def add(label, ms=None, **kw):
        cases.append(catalog_case("adversarial/" + label, ms, **kw))

    a = make_manifest(b"a")
    b = make_manifest(b"b")
    c = make_manifest(b"c")
    for n in (0, 1, 2, 8):
        ms = [make_manifest(bytes([97 + i])) for i in range(n)]
        add(f"rank-boundaries/{n}", ms, ranks=(IMIN, -1, *range(n + 1), IMAX))
    for n in (IMIN, -1, 9, IMAX):
        add(f"count/{n}", data=b"X", offsets=[IMAX] * 8, lengths=[IMIN] * 8, count=n, ranks=(IMIN, 0, IMAX))
    for offset in (IMIN, -1, 0, 1, len(a), len(a) + 1, IMAX):
        for length in (IMIN, -1, 0, 1, len(a), len(a) + 1, IMAX):
            add(
                f"window/{offset}/{length}",
                data=a,
                offsets=[offset] + [IMIN] * 7,
                lengths=[length] + [IMAX] * 7,
                count=1,
                ranks=(-1, 0, IMAX),
            )
    # Every precedence pair between semantic errors, in both catalog directions.
    errors = {
        "malformed": [b"bad"],
        "duplicate_package": [make_manifest(b"dup"), make_manifest(b"dup", (1, 2, 3))],
        "missing_package": [make_manifest(b"missing-root", deps=((b"absent", (0, 0, 0)),))],
        "version_mismatch": [make_manifest(b"pin-root", deps=((b"pinned", (1, 0, 0)),)), make_manifest(b"pinned")],
        "cycle": [
            make_manifest(b"cycle-a", deps=((b"cycle-b", (0, 0, 0)),)),
            make_manifest(b"cycle-b", deps=((b"cycle-a", (0, 0, 0)),)),
        ],
    }
    for lower, higher in itertools.combinations(errors, 2):
        for reverse in (False, True):
            ms = errors[lower] + errors[higher]
            add(f"precedence/{lower}/{higher}/{reverse}", list(reversed(ms)) if reverse else ms, ranks=(IMIN, 0, IMAX))
    for name, ms in errors.items():
        data, offsets, lengths = pack(ms + [a])
        offsets[len(ms)] = IMAX
        add(
            "out-of-range-before-" + name, data=data, offsets=offsets, lengths=lengths, count=len(ms) + 1, ranks=(-1, 0)
        )
        add("isolated-" + name, ms, ranks=(IMIN, -1, 0, len(ms), IMAX))
    add("duplicate-same-version", [a, a])
    add("duplicate-overlapping-same-window", data=a, offsets=[0] * 8, lengths=[len(a)] * 8, count=2)
    add("self-name-different-version", [make_manifest(b"a", deps=((b"a", (1, 0, 0)),))])
    add("late-duplicate-dependency", [a, make_manifest(b"z", deps=((b"a", (0, 0, 0)), (b"a", (1, 0, 0))))])
    add(
        "late-malformed-dependency",
        [a, make_manifest(b"z", deps=((b"a", (0, 0, 0)),)).replace(b"a@0.0.0", b"a@00.0.0")],
    )
    # Full lexical tie breaker, including shorter-prefix and '-' before digits.
    names = (b"a", b"a-a", b"a0", b"aa", b"b", b"b-a", b"b0", b"z" * 24)
    versions = ((0, 0, 0), (U32, U32, U32), (1 << 31, 17, U32), (17, 1 << 31, 0)) * 2
    for shape in ("empty", "chain", "dense", "cycle", "disconnected-cycle", "diamond"):
        deps = {i: [] for i in range(8)}
        if shape == "chain":
            deps = {i: [i - 1] if i else [] for i in range(8)}
        if shape == "dense":
            deps = {i: list(range(i)) for i in range(8)}
        if shape == "cycle":
            deps = {i: [(i + 1) % 8] for i in range(8)}
        if shape == "disconnected-cycle":
            deps[6] = [7]
            deps[7] = [6]
        if shape == "diamond":
            deps[3] = [1, 2]
            deps[1] = [0]
            deps[2] = [0]
            deps[7] = [3, 6]
            deps[6] = [0]
        for perm in (tuple(range(8)), tuple(reversed(range(8))), (7, 2, 5, 0, 3, 6, 1, 4)):
            for reverse_deps in (False, True):
                ms = [
                    make_manifest(
                        names[i],
                        versions[i],
                        tuple((names[j], versions[j]) for j in (list(reversed(deps[i])) if reverse_deps else deps[i])),
                    )
                    for i in perm
                ]
                add(f"eight/{shape}/{perm}/{reverse_deps}", ms)
    add(
        "conflicting-exact-pins",
        [a, make_manifest(b"b", deps=((b"a", (0, 0, 0)),)), make_manifest(b"c", deps=((b"a", (0, 0, 1)),))],
    )
    for version in ((U32, 0, 0), (0, U32, 0), (0, 0, U32), (1 << 31, 1 << 31, 1 << 31)):
        add(
            "matching-version/" + str(version),
            [make_manifest(b"root", deps=((b"lib", version),)), make_manifest(b"lib", version)],
        )
        mismatch = tuple(0 if v else 1 for v in version)
        add(
            "mismatching-version/" + str(version),
            [make_manifest(b"root", deps=((b"lib", mismatch),)), make_manifest(b"lib", version)],
        )
    valid = make_manifest(b"root", deps=((b"lib", (1, 2, 3)),))
    if exhaustive:
        for cut in range(len(valid)):
            add(f"truncation/{cut}", data=valid, offsets=[0] * 8, lengths=[cut] + [0] * 7, count=1, ranks=(0,))
    invalid_tokens = (
        b"root@01.0.0",
        b"Root@0.0.0",
        b"a--b@0.0.0",
        b"a-@0.0.0",
        b"a@4294967296.0.0",
        b"a@0.0.-1",
        b"a@0.0.0x",
        b"1a@0.0.0",
        b"a" * 25 + b"@0.0.0",
        b"a@0.0.0\r",
        b"a\0@0.0.0",
    )
    for token in invalid_tokens:
        add("identity/" + repr(token), [b"aurora-package 1\npackage " + token + b"\nend\n"])
    for bad in (
        b"",
        b"\0",
        b"\xef\xbb\xbf" + a,
        a + b"\n",
        a[:-1],
        a.replace(b"\n", b"\r\n"),
        a.replace(b" 1\n", b" 01\n"),
        a.replace(b"package a", b"package  a"),
        a.replace(b"end\n", b"unknown\n"),
        b"X" + a[1:],
    ):
        add("grammar/" + repr(bad[:24]), [bad])
    # Mutations run against a shared source body; each byte position is poisoned.
    if exhaustive:
        base = catalog_case("unused", [a, b])
        data, offs, lens = pack([a, b])
        prefix = array("owner", data) + index_arrays(offs, lens)
        for position in range(len(data)):
            for byte in (0, 13, 255):
                mutated = data[:position] + bytes([byte]) + data[position + 1 :]
                body = prefix + "owner[argument1]=u8(argument2);" + finish_body(2, (0,))
                cases.append(
                    Case(
                        f"adversarial/byte-mutation/{position}/{byte}",
                        body,
                        expected_graph(mutated, offs, lens, 2, (0,)),
                        arguments=(position, byte),
                        block_result=True,
                    )
                )
    maxroot = b"z" * 24
    maxdeps = tuple((bytes([97 + i]) + b"q" * 23, (U32, U32, U32)) for i in range(8))
    maximum = make_manifest(maxroot, (U32, U32, U32), maxdeps)
    require(len(maximum) == 615, "maximum manifest fixture")
    add("maximum-manifest-missing-ninth-package", [maximum])
    add("dependency-over-cap", [make_manifest(b"z", deps=tuple((bytes([97 + i]), (0, 0, 0)) for i in range(9)))])
    # Out-of-order windows, ignored junk and poisoned unused selectors.
    data = b"\xff\x00" + a + b"\xff\xfe" + b + b"\x80"
    add(
        "unselected-junk",
        data=data,
        offsets=[2 + len(a) + 2, 2] + [IMIN] * 6,
        lengths=[len(b), len(a)] + [IMAX] * 6,
        count=2,
    )
    add(
        "empty-catalog-ignores-all",
        data=bytes([255]) * 4096,
        offsets=[IMIN] * 8,
        lengths=[IMAX] * 8,
        count=0,
        ranks=(IMIN, -1, 0, IMAX),
    )
    add(
        "large-owner-exact-window",
        data=bytes([255]) * (4096 - len(a)) + a,
        offsets=[4096 - len(a)] + [IMAX] * 7,
        lengths=[len(a)] + [IMIN] * 7,
        count=1,
    )
    return cases


def identity_source(name=b"copied-name", version=(U32, 1 << 31, 17), bad=None):
    src = "std::array<u8,24> name=std::array<u8,24>();" + "".join(f"name.set({i},{b}u8);" for i, b in enumerate(name))
    length = len(name)
    status = "success"
    if bad == "padding":
        src += "name.set(23,255u8);"
    if bad == "length":
        length = IMAX
    if bad == "version":
        version = (U64, 0, 0)
    if bad == "status":
        status = "out_of_range"
    src += (
        f"const package::IdentityResult identity="
        f"package::IdentityResult(package::IdentityStatus::{status},name,{signed(length)},"
        + ",".join(f"{v}u64" for v in version)
        + ");"
    )
    return src, Identity(name, version) if bad is None else None


def construction_cases():
    cases = []
    orders = [tuple(range(n)) + (0,) * (8 - n) for n in range(9)]
    poisons = [
        (IMIN,) + (0,) * 7,
        (IMAX,) + (0,) * 7,
        (1,) + (0,) * 7,
        (0, 0, 2, 3, 4, 5, 6, 7),
        tuple(reversed(range(8))),
        (0,) * 7 + (1,),
    ]
    for status in STATUSES:
        for n in (IMIN, -1, 0, 1, 2, 8, 9, IMAX):
            for no, order in enumerate((orders[min(max(n, 0), 8)], poisons[abs(n) % len(poisons)])):
                state = order_constructor(status, order, n)
                body = "std::array<i64,8> order=std::array<i64,8>();" + "".join(
                    f"order.set({i},{signed(v)});" for i, v in enumerate(order) if v
                )
                body += (
                    f"const package::GraphOrderResult original="
                    f"package::GraphOrderResult(package::GraphStatus::{status},order,{signed(n)});"
                    f"const package::GraphOrderResult r=original;order.set(0,9223372036854775807);"
                    f"return observe_order(r,slot);"
                )
                cases.append(Case(f"constructor/order/{status}/{n}/{no}", body, order_values(state, order, n)))
    # Each unused slot, duplicate position and selected bounds is independently poisoned.
    for n in range(9):
        for i in range(8):
            order = list(orders[n])
            order[i] = IMIN if i < n else 1
            state = order_constructor("success", order, n)
            body = (
                "std::array<i64,8> order=std::array<i64,8>();"
                + "".join(f"order.set({j},{signed(v)});" for j, v in enumerate(order) if v)
                + f"const package::GraphOrderResult r="
                f"package::GraphOrderResult(package::GraphStatus::success,order,{n});return observe_order(r,slot);"
            )
            cases.append(Case(f"constructor/order-each-slot/{n}/{i}", body, order_values(state, order, n)))
    for status in STATUSES:
        for n, rank, index in (
            (1, 0, 0),
            (8, 7, 7),
            (0, 0, 0),
            (9, 0, 0),
            (IMIN, 0, 0),
            (IMAX, 0, 0),
            (8, -1, 0),
            (8, 8, 0),
            (8, IMIN, 0),
            (8, IMAX, 0),
            (8, 0, -1),
            (8, 0, 8),
            (8, 0, IMIN),
            (8, 0, IMAX),
        ):
            for bad in (None, "padding", "length", "version", "status") if (n, rank, index) == (8, 7, 7) else (None,):
                body, ident = identity_source(bad=bad)
                state = entry_constructor(status, ident, n, rank, index)
                body += (
                    f"const package::GraphEntryResult original=package::GraphEntryResult("
                    f"package::GraphStatus::{status},identity,{signed(n)},{signed(rank)},{signed(index)});"
                    f"const package::GraphEntryResult r=original;name.set(0,255u8);return observe_entry(r,slot);"
                )
                cases.append(
                    Case(
                        f"constructor/entry/{status}/{n}/{rank}/{index}/{bad}",
                        body,
                        entry_values(state, ident, n, rank, index),
                    )
                )
    return cases


def ownership_cases():
    ms = [
        make_manifest(b"root", (U32, 1 << 31, 17), ((b"dep", (17, 1 << 31, U32)),)),
        make_manifest(b"dep", (17, 1 << 31, U32)),
    ]
    data, offsets, lengths = pack(ms)
    setup = array("owner", data) + index_arrays(offsets, lengths)
    model = graph(data, offsets, lengths, 2)
    expected = expected_graph(data, offsets, lengths, 2, (0,))
    helper = (
        "auto make_order()->package::GraphOrderResult{{" + setup + "const package::GraphOrderResult r="
        "package::order_manifests(borrow_bytes(owner),offsets,lengths,2);return r;}}"
        "auto make_entry()->package::GraphEntryResult{{" + setup + "const package::GraphEntryResult r="
        "package::ordered_manifest(borrow_bytes(owner),offsets,lengths,2,0);return r;}}"
        "auto copy_order(package::GraphOrderResult r)->package::GraphOrderResult{return r;}"
        "auto copy_entry(package::GraphEntryResult r)->package::GraphEntryResult{return r;}"
    )
    body = (
        f"if(slot<{ORDER_WIDTH}){{const package::GraphOrderResult a=make_order();"
        f"const package::GraphOrderResult r=copy_order(a);return observe_order(r,slot);}}"
        f"const package::GraphEntryResult a=make_entry();const package::GraphEntryResult r=copy_entry(a);"
        f"return observe_entry(r,slot-{ORDER_WIDTH});"
    )
    cases = [Case("ownership/scope-exit-and-function-copies", body, expected, helper)]
    helper = (
        "class Counter{i64 calls;public:Counter():calls(0){}"
        "auto next()->i64{calls=calls+1;return -81985529216486896;}auto count()const->i64{return calls;}};"
    )
    for good in (True, False):
        body = (
            setup
            + ("" if good else "owner[0]=0u8;")
            + "const package::GraphOrderResult o=package::order_manifests(borrow_bytes(owner),offsets,lengths,2);"
            "const package::GraphEntryResult e=package::ordered_manifest(borrow_bytes(owner),offsets,lengths,2,0);"
            "Counter c=Counter();const i64 a=o.package_count_or(c.next());const i64 b=o.catalog_index_or(0,c.next());"
            "const i64 d=e.package_count_or(c.next());const i64 f=e.rank_or(c.next());"
            "const i64 g=e.catalog_index_or(c.next());if(slot==0){return bits(c.count());}"
            "if(slot==1){return bits(a);}if(slot==2){return bits(b);}if(slot==3){return bits(d);}"
            "if(slot==4){return bits(f);}return bits(g);"
        )
        cases.append(
            Case(
                f"ownership/eager-fallback/{good}",
                body,
                (5, 2, 1, 2, 0, 1) if good else (5, *([INDEX_FALLBACK & U64] * 5)),
                helper,
            )
        )
    body = (
        setup + "const package::GraphEntryResult before="
        "package::ordered_manifest(borrow_bytes(owner),offsets,lengths,2,0);owner[0]=0u8;"
        "const package::GraphEntryResult after=package::ordered_manifest(borrow_bytes(owner),offsets,lengths,2,0);"
        "if(slot<33){return observe_entry(before,slot);}return observe_entry(after,slot-33);"
    )
    cases.append(
        Case(
            "ownership/independent-observations-after-mutation",
            body,
            entry_values("success", model[2][1], 2, 0, 1) + entry_values("malformed", None, 2, 0, 0),
        )
    )
    body = (
        setup + "const package::GraphEntryResult r=package::ordered_manifest(borrow_bytes(owner),offsets,lengths,2,0);"
        "const package::IdentityResult identity=r.identity_or_error();"
        "std::array<u8,24> name=identity.name_bytes_or_zero();i64 i=0;"
        "while(i<24){name.set(i,255u8);i=i+1;}return observe_entry(r,slot);"
    )
    cases.append(Case("ownership/getter-copy-isolation", body, entry_values("success", model[2][1], 2, 0, 1)))
    # Local named span ends before input overwrite; independent copies remain valid.
    body = (
        setup + "{const builtin::span<const u8> span=borrow_bytes(owner);{const builtin::span<const u8> child=span;"
        "const package::GraphOrderResult r=package::order_manifests(child,offsets,lengths,2);"
        "if(r.status()!=package::GraphStatus::success){return 0u64;}}}owner[0]=0u8;return 42u64;"
    )
    cases.append(Case("ownership/supported-lexical-borrow-release", body, (42,)))
    return cases


def binding_cases():
    helper = (
        "namespace package{auto graph_name_equal(IdentityResult a,IdentityResult b)->bool{return false;}"
        "auto graph_name_less(IdentityResult a,IdentityResult b)->bool{return false;}"
        "auto graph_identity_error()->IdentityResult{const std::array<u8,24> n=std::array<u8,24>();"
        "const IdentityResult r=IdentityResult(IdentityStatus::out_of_range,n,0,0u64,0u64,0u64);return r;}}"
    )
    cases = []
    for name, ms in (
        ("lexical", [make_manifest(b"z"), make_manifest(b"a"), make_manifest(b"a-a")]),
        ("duplicate", [make_manifest(b"a"), make_manifest(b"a")]),
        ("missing", [make_manifest(b"a", deps=((b"b", (0, 0, 0)),))]),
    ):
        c = catalog_case("defining-module-binding/" + name, ms)
        cases.append(Case(c.label, c.body, c.expected, helper, block_result=True))
    return cases


def negative_cases():
    data, offsets, lengths = pack([make_manifest(b"a")])
    setup = array("owner", data) + index_arrays(offsets, lengths)
    order = "const package::GraphOrderResult o=package::order_manifests(borrow_bytes(owner),offsets,lengths,1);"
    entry = "const package::GraphEntryResult e=package::ordered_manifest(borrow_bytes(owner),offsets,lengths,1,0);"

    def wrap(body, prefix=PREFIX):
        return prefix + "auto answer()->u64{" + setup + body + "return 0u64;}"

    cases = [
        (
            "supported-live-span-owner-mutation",
            wrap(
                "const builtin::span<const u8> span=borrow_bytes(owner);"
                "const package::GraphOrderResult o=package::order_manifests(span,offsets,lengths,1);owner[0]=0u8;"
            ),
            "cannot mutate a byte array while a span is live",
        ),
        (
            "supported-live-parent-after-child-exit",
            wrap(
                "const builtin::span<const u8> span=borrow_bytes(owner);{const builtin::span<const u8> child=span;"
                "const package::GraphEntryResult e=package::ordered_manifest(child,offsets,lengths,1,0);}owner[0]=0u8;"
            ),
            "cannot mutate a byte array while a span is live",
        ),
        (
            "unsupported-returned-span-syntax",
            PREFIX + "auto leak()->builtin::span<const u8>{" + setup + "return borrow_bytes(owner);}",
            "only scalar function results or scalar-field class values are supported (found '{')",
        ),
        (
            "unsupported-span-field-syntax",
            PREFIX + "class Leak{builtin::span<const u8> value;};",
            "unsupported class field type 'builtin::span<const u8>': class fields require scalar, class, private fixed-array or private owned-byte storage",
        ),
        (
            "graph-enum-no-integer-conversion",
            wrap("const u64 value=u64(package::GraphStatus::success);"),
            "expected distinct i64, u64 or u8 conversion types",
        ),
        (
            "graph-enum-no-mixed-status",
            wrap(
                "const std::array<i64,8> a=std::array<i64,8>();"
                "const package::GraphOrderResult o=package::GraphOrderResult(package::ManifestStatus::success,a,0);"
            ),
            "expected package::GraphStatus, got package::ManifestStatus",
        ),
        (
            "order-no-designated-construction",
            wrap("const package::GraphOrderResult o=package::GraphOrderResult{};"),
            "constructor-bearing class rejects designated initialization",
        ),
        (
            "entry-no-designated-construction",
            wrap("const package::GraphEntryResult e=package::GraphEntryResult{};"),
            "constructor-bearing class rejects designated initialization",
        ),
        (
            "order-no-byte-span-forgery",
            wrap(order + "const builtin::span<const u8> span=borrow_bytes(o);"),
            "borrow_bytes requires a named local byte array or owned bytes",
        ),
        (
            "entry-no-byte-span-forgery",
            wrap(entry + "const builtin::span<const u8> span=borrow_bytes(e);"),
            "borrow_bytes requires a named local byte array or owned bytes",
        ),
        (
            "graph-unsigned-count",
            wrap(
                "const package::GraphOrderResult o=package::order_manifests(borrow_bytes(owner),offsets,lengths,1u64);"
            ),
            "expected i64, got u64",
        ),
        (
            "graph-unsigned-rank",
            wrap(
                "const package::GraphEntryResult e="
                "package::ordered_manifest(borrow_bytes(owner),offsets,lengths,1,0u64);"
            ),
            "expected i64, got u64",
        ),
        ("graph-unsigned-fallback", wrap(order + "const i64 value=o.package_count_or(0u64);"), "expected i64, got u64"),
        (
            "graph-unsigned-order-selector",
            wrap(order + "const i64 value=o.catalog_index_or(0u64,0);"),
            "expected i64, got u64",
        ),
        (
            "graph-wrong-array-type",
            wrap(
                "const std::array<u64,8> wrong=std::array<u64,8>();"
                "const package::GraphOrderResult o=package::order_manifests(borrow_bytes(owner),wrong,lengths,1);"
            ),
            "expected std::array<i64,8>, got std::array<u64,8>",
        ),
        (
            "identity-import-required",
            wrap(entry, "module graph_oracle;import package.graph;import package.manifest;import std.array;\n"),
            "class type requires a direct visible import: package::GraphEntryResult",
        ),
        (
            "array-import-required",
            wrap(order, "module graph_oracle;import package.graph;import package.manifest;import package.identity;\n"),
            "unsupported type or unknown class template; expected a declared template: std::array",
        ),
        (
            "graph-import-required",
            wrap(order, PREFIX.replace("import package.graph;", "")),
            "unknown function 'package::order_manifests' in defining module graph_oracle",
        ),
        (
            "immutable-returned-name",
            wrap(
                entry + "const package::IdentityResult identity=e.identity_or_error();"
                "const std::array<u8,24> name=identity.name_bytes_or_zero();name.set(0,0u8);"
            ),
            "mutable method requires a mutable receiver",
        ),
    ]
    for field in ("outcome", "stored_order", "packages"):
        expr = (
            "if(o.outcome==package::GraphStatus::success){return 1u64;}"
            if field == "outcome"
            else (
                "const std::array<i64,8> value=o.stored_order;"
                if field == "stored_order"
                else "const i64 value=o.packages;"
            )
        )
        cases.append(("order-private-" + field, wrap(order + expr), "private class field is inaccessible"))
    for field in ("outcome", "stored_identity", "packages", "selected_rank", "selected_index"):
        expr = (
            "if(e.outcome==package::GraphStatus::success){return 1u64;}"
            if field == "outcome"
            else (
                "const package::IdentityResult value=e.stored_identity;"
                if field == "stored_identity"
                else f"const i64 value=e.{field};"
            )
        )
        cases.append(("entry-private-" + field, wrap(entry + expr), "private class field is inaccessible"))
    for helper, result, args in (
        ("graph_identity_error", "package::IdentityResult", ""),
        ("graph_failure", "package::GraphOrderResult", "package::GraphStatus::malformed"),
        ("graph_entry_failure", "package::GraphEntryResult", "package::GraphStatus::malformed"),
    ):
        cases.append(
            (
                "private-helper-" + helper,
                wrap(f"const {result} r=package::{helper}({args});"),
                "private function is not imported: package::" + helper,
            )
        )
    return cases


def observation_blocks(case):
    if not case.block_result:
        return 1, (1,) * len(case.expected)
    entries, remainder = divmod(len(case.expected) - ORDER_WIDTH, ENTRY_WIDTH)
    require(entries >= 1 and remainder == 0, "graph report observation widths")
    return ENTRY_WIDTH, (ORDER_WIDTH,) + (ENTRY_WIDTH,) * entries


class Runner(PackageRunner):
    def __init__(self, compiler, artifacts, cap=CAP):
        super().__init__(
            compiler,
            artifacts,
            cap,
            root=ROOT,
            prefix=PREFIX,
            shared=shared,
            validate=validate,
            function_prefix="graph_case",
            sentinel=b"keep existing graph output\n\x00\xff",
            blocks=observation_blocks,
        )


def batches(cases):
    current = []
    bodies = set()
    size = len(PREFIX + shared())
    for case in cases:
        extra = (len(case.body) + 180 if case.body not in bodies else 0) + len(case.helpers)
        if current and (len(current) >= BATCH or size + extra > SOURCE_CAP - 1024):
            yield current
            current = []
            bodies = set()
            size = len(PREFIX + shared())
            extra = len(case.body) + 180 + len(case.helpers)
        current.append(case)
        bodies.add(case.body)
        size += extra
    if current:
        yield current


def validate(output, expected, returncode=0):
    require(returncode == 0, f"native exit {returncode}")
    require(len(output) == 8 * len(expected), f"exact output length expected {8 * len(expected)}, got {len(output)}")
    observed = tuple(int.from_bytes(output[i : i + 8], "little") for i in range(0, len(output), 8))
    for i, (actual, wanted) in enumerate(zip(observed, expected)):
        require(actual == wanted, f"observation {i}: expected {wanted}, got {actual}")
    return observed


def all_cases():
    groups = (exhaustive_cases(), adversarial_cases(), construction_cases(), ownership_cases(), binding_cases())
    names = ("exhaustive_graph_cases", "adversarial_cases", "constructor_cases", "ownership_cases", "binding_cases")
    return [case for group in groups for case in group], dict(zip(names, map(len, groups)))


def self_test():
    cap_self_test()
    require(observation_blocks(Case("scalar", "", (1, 2))) == (1, (1, 1)), "scalar transport default")
    require(
        observation_blocks(Case("blocks", "", (0,) * 80, block_result=True)) == (33, (14, 33, 33)),
        "complete order and ranked entry blocks",
    )
    for length in (0, 14, 46, 48):
        try:
            observation_blocks(Case("invalid", "", (0,) * length, block_result=True))
        except AssertionError:
            continue
        raise AssertionError("invalid block observation count accepted")
    require(len(make_manifest()) == 37, "minimal manifest bytes")
    require(manifest(make_manifest()) == (Identity(b"a", (0, 0, 0)), ()), "minimum parser")
    for bad in (
        make_manifest() + b"\n",
        make_manifest()[:-1],
        make_manifest(b"a", deps=((b"a", (1, 2, 3)),)),
        make_manifest(b"a", deps=((b"b", (0, 0, 0)), (b"b", (1, 2, 3)))),
    ):
        require(manifest(bad) is None, "strict grammar control")
    data, offs, lens = pack(
        [make_manifest(b"c", deps=((b"a", (0, 0, 0)), (b"b", (0, 0, 0)))), make_manifest(b"b"), make_manifest(b"a")]
    )
    require(graph(data, offs, lens, 3)[:2] == ("success", (2, 1, 0)), "lexical topological control")
    data, offs, lens = pack(
        [make_manifest(b"a", deps=((b"b", (0, 0, 0)),)), make_manifest(b"b", deps=((b"a", (0, 0, 0)),))]
    )
    require(graph(data, offs, lens, 2)[0] == "cycle", "cycle control")
    require(graph(b"X", [IMAX] * 8, [IMAX] * 8, 9)[0] == "invalid_count", "count precedence")
    require(graph(b"X", [0, IMAX] + [0] * 6, [1, IMAX] + [0] * 6, 2)[0] == "out_of_range", "range precedes malformed")
    require(
        order_constructor("success", (0,) * 8, 0) == "success"
        and order_constructor("success", (0,) * 7 + (1,), 0) == "malformed",
        "unused order poisoning",
    )
    require(
        len(order_values("malformed", (), 0)) == 14 and len(entry_values("malformed", None, 0, 0, 0)) == 33,
        "observation widths",
    )
    validate(U64.to_bytes(8, "little"), (U64,))
    for output, expected, code in (
        (b"\xff" + bytes(7), (U64,), 0),
        (bytes(7), (0,), 0),
        (bytes(9), (0,), 0),
        (bytes(8), (0,), -4),
        (bytes(8), (0,), 1),
    ):
        try:
            validate(output, expected, code)
        except AssertionError:
            pass
        else:
            raise AssertionError("observer accepted broken high-bit/length/exit control")
    for path in (ROOT / "build" / ".." / "escaped", ROOT.parent / "escaped"):
        try:
            artifact_path(path)
        except AssertionError:
            pass
        else:
            raise AssertionError("path control failed")


def freeze_corpus(directory):
    require(not directory.exists(), "fresh corpus freeze directory required")
    directory.mkdir()
    cases, counts = all_cases()
    with gzip.open(directory / "corpus.jsonl.gz", "wt", encoding="utf-8") as out:
        for case in cases:
            out.write(json.dumps(case.__dict__, sort_keys=True) + "\n")
    shutil.copyfile(__file__, directory / "package_graph.py")
    report = dict(
        status="corpus-frozen",
        independent_reference_sha256=REFERENCE_SHA256,
        contract_sha256=CONTRACT_SHA256,
        oracle_sha256=sha(__file__),
        corpus_sha256=sha(directory / "corpus.jsonl.gz"),
        cases=len(cases),
        observations=sum(len(c.expected) for c in cases),
        counts=counts,
        utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        note=(
            "Independent reference v1 predates production inspection; "
            "later API-specific rejection/shadowing cases use actual exported/private names."
        ),
    )
    safe_receipt(directory / "freeze.json", report)
    print(json.dumps(report, indent=2))


def developer_cases():
    """Named graph shapes, precedence pairs and poisoned public constructors."""
    size = len(make_manifest())
    adversarial = select_cases(
        adversarial_cases(exhaustive=False),
        prefixes=(
            "adversarial/precedence/",
            "adversarial/out-of-range-before-",
            "adversarial/isolated-",
            "adversarial/rank-boundaries/",
            "adversarial/count/",
        ),
        labels=(
            *(
                f"adversarial/eight/{shape}/{perm}/{reverse}"
                for shape in ("empty", "chain", "dense", "cycle", "disconnected-cycle", "diamond")
                for perm, reverse in ((tuple(range(8)), False), (tuple(reversed(range(8))), True))
            ),
            *(f"adversarial/eight/{shape}/{tuple(range(8))}/True" for shape in ("dense", "diamond")),
            *(f"adversarial/eight/{shape}/{(7, 2, 5, 0, 3, 6, 1, 4)}/False" for shape in ("chain", "diamond")),
            *(
                f"adversarial/window/{offset}/{length}"
                for offset, length in (
                    (0, size),
                    (-1, size),
                    (0, -1),
                    (0, 0),
                    (1, size),
                    (IMIN, 0),
                    (0, IMAX),
                    (IMAX, IMAX),
                )
            ),
            *(
                "adversarial/" + label
                for label in (
                    "duplicate-same-version",
                    "duplicate-overlapping-same-window",
                    "self-name-different-version",
                    "late-duplicate-dependency",
                    "late-malformed-dependency",
                    "conflicting-exact-pins",
                    "maximum-manifest-missing-ninth-package",
                    "dependency-over-cap",
                    "unselected-junk",
                    "empty-catalog-ignores-all",
                    "large-owner-exact-window",
                )
            ),
        ),
    )
    # Small graph shapes exercise the same oracle without the exhaustive masks.
    for shape, dependencies in (
        ("chain", ((), (0,), (1,), (2,))),
        ("diamond", ((), (0,), (0,), (1, 2))),
        ("cycle", ((1,), (0,))),
        ("disconnected-cycle", ((), (), (3,), (2,))),
    ):
        manifests = [
            make_manifest(bytes([97 + i]), deps=tuple((bytes([97 + j]), (0, 0, 0)) for j in deps))
            for i, deps in enumerate(dependencies)
        ]
        for reverse in (False, True):
            adversarial.append(
                catalog_case(f"dev-small/{shape}/{reverse}", list(reversed(manifests)) if reverse else manifests)
            )
    construction = select_cases(
        construction_cases(),
        labels=(
            *(
                f"constructor/order/{status}/{count}/{poison}"
                for status in STATUSES
                for count, poison in ((1, 0), (8, 1))
            ),
            *(
                f"constructor/order/success/{count}/{poison}"
                for count, poison in ((IMIN, 0), (-1, 0), (0, 0), (2, 1), (9, 0), (IMAX, 0))
            ),
            *(f"constructor/order-each-slot/{count}/{slot}" for count in (2, 8) for slot in range(8)),
            *(
                f"constructor/entry/{status}/8/7/7/{bad}"
                for status in STATUSES
                for bad in (None, "padding", "length", "version", "status")
            ),
            *(
                f"constructor/entry/success/{count}/{rank}/{index}/None"
                for count, rank, index in (
                    (0, 0, 0),
                    (9, 0, 0),
                    (IMIN, 0, 0),
                    (IMAX, 0, 0),
                    (8, -1, 0),
                    (8, 8, 0),
                    (8, IMIN, 0),
                    (8, IMAX, 0),
                    (8, 0, -1),
                    (8, 0, 8),
                    (8, 0, IMIN),
                    (8, 0, IMAX),
                )
            ),
        ),
    )
    ownership, binding = ownership_cases(), binding_cases()
    require(
        tuple(map(len, (adversarial, construction, ownership, binding))) == (81, 97, 6, 3),
        "developer semantic group counts changed",
    )
    cases = adversarial + construction + ownership + binding
    select_cases(cases, prefixes=("",))
    return cases, dict(
        exhaustive_graph_cases=0,
        adversarial_cases=len(adversarial),
        constructor_cases=len(construction),
        ownership_cases=len(ownership),
        binding_cases=len(binding),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", nargs="?", type=Path, default=ROOT / "build/aurorac")
    parser.add_argument("--artifacts", "--artifact-root", dest="artifact_root", type=Path)
    parser.add_argument(
        "--quick", "--smoke", dest="smoke", action="store_true", help="development subset, not full acceptance"
    )
    parser.add_argument("--self-test-only", action="store_true")
    parser.add_argument("--freeze-reference", type=Path)
    add_identity_arguments(parser)
    parser.add_argument(
        "--candidate-cap-mib",
        type=int,
        default=256,
        help=(
            "per-invocation owned-output cap 256..1024 MiB; default 256; increases require explicit aggregate admission"
        ),
    )
    parser.add_argument(
        "--check-cap-only",
        action="store_true",
        help="configuration-only cap checks; no compiler, native test or acceptance receipt",
    )
    args = parser.parse_args()
    validate_identity_selection(args, preflight=args.self_test_only or args.check_cap_only)
    cap = candidate_cap(args.candidate_cap_mib)
    if args.check_cap_only:
        cap_self_test()
        print(
            json.dumps(
                dict(
                    status="configuration-only",
                    native_executed=False,
                    candidate_cap_mib=args.candidate_cap_mib,
                    cap_bytes=cap,
                    focused_default_mib=256,
                    maximum_cap_mib=1024,
                ),
                sort_keys=True,
            )
        )
        return
    if not args.self_test_only:
        compiler = args.compiler.resolve(strict=True)
        identity = resolve_identity(args, compiler, ROOT)
        expected_compiler_sha = identity.sha256
    self_test()
    frozen = ROOT / "evidence/package-graph/contract-before-implementation.md"
    reference = ROOT / "evidence/package-graph/oracle/reference-v1/reference.py"
    require(sha(frozen) == CONTRACT_SHA256, "frozen pre-implementation contract changed")
    require(sha(reference) == REFERENCE_SHA256, "independent pre-inspection reference changed")
    if args.self_test_only:
        print("PASS independent reference, full-width observer, grammar, precedence and path controls")
        return
    if args.freeze_reference:
        directory = artifact_path(args.freeze_reference)
        require(not directory.exists(), "fresh corpus freeze directory required")
        guard = Runner(compiler, directory, cap)
        guard.budget(RESERVE)
        freeze_report = dict(
            status="running",
            mode="corpus-freeze",
            compiler_identity=identity.record(),
            cap_bytes=cap,
            free_floor_bytes=FLOOR,
            reserve_bytes=RESERVE,
            observed_compiler_sha256=identity.sha256,
            expected_compiler_sha256=identity.expected,
        )
        try:
            freeze_corpus(directory)
            identity.verify()
            freeze_report["status"] = "passed"
        except BaseException as exc:
            freeze_report.update(status="failed", error=str(exc), exception_type=type(exc).__name__)
            raise
        finally:
            original_error_active = sys.exc_info()[0] is not None
            errors = finalize_report(guard, freeze_report, compiler, directory)
            if errors and not original_error_active:
                raise AssertionError("freeze finalization failed: " + "; ".join(errors))
        return
    artifacts = (
        developer_artifacts(args, "graph")
        if args.profile == "dev" or args.meson_selected_compiler
        else artifact_path(args.artifact_root or ROOT / f"build/package-graph-{os.getpid()}")
    )
    require(artifacts.parent.is_dir() and not artifacts.exists(), "fresh artifact root with existing parent required")
    runner = Runner(compiler, artifacts, cap)
    runner.budget(65536)
    artifacts.mkdir()
    inputs = [
        compiler,
        ROOT / "library/package/graph.au",
        ROOT / "library/package/manifest.au",
        ROOT / "library/package/identity.au",
        ROOT / "library/std/array.au",
        Path(__file__).resolve(),
        ROOT / "scripts/package_native_runner.py",
        ROOT / "scripts/owned_outputs.py",
        ROOT / "scripts/package_profiles.py",
        ROOT / "scripts/compiler_contract.py",
        frozen,
        reference,
        Path(sys.executable).resolve(strict=True),
        *runner.tools.values(),
    ]
    runner.pins = {p: sha(p) for p in inputs}
    report = dict(
        status="running",
        compiler_identity=identity.record(),
        pins={str(p): h for p, h in runner.pins.items()},
        tool_paths={name: str(path) for name, path in runner.tools.items()},
        observed_compiler_sha256=identity.sha256,
        expected_compiler_sha256=identity.expected,
        command=sys.argv,
        started_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        cap_bytes=cap,
        free_floor_bytes=FLOOR,
        reserve_bytes=RESERVE,
        per_source_cap_bytes=SOURCE_CAP,
        cases_per_batch=BATCH,
        smoke_only=args.smoke,
        model=(
            "Independent exact byte-line grammar, decimal roundtrip, arbitrary precision windows, "
            "exhaustive full permutation search in canonical-name lexical order"
        ),
        native="GNU as/ld x86-64, direct Linux write/exit, complete little-endian u64 observations; no target libc",
        compaction=(
            "Only completed successful batch directories: tar.xz exact member/mode/length/hash readback "
            "before deletion; all failures retained"
        ),
        limits="Finite bounded execution evidence; no universal memory safety, stack safety or performance proof",
    )
    try:
        for name, tool in {**runner.tools, "python": Path(sys.executable).resolve()}.items():
            runner.command([tool, "--version"], artifacts, "version-" + name)
        cases, counts = developer_cases() if args.profile == "dev" else all_cases()
        report.update(counts)
        if args.smoke:
            cases = (
                exhaustive_cases()[:12]
                + adversarial_cases()[:8]
                + construction_cases()[:8]
                + ownership_cases()
                + binding_cases()
            )
        report.update(profile_record(args, cases, negative_cases()))
        report.update(
            native_cases=len(cases),
            complete_u64_observations=sum(len(c.expected) for c in cases),
            rejection_cases=len(negative_cases()),
        )
        done = 0
        for number, batch in enumerate(batches(cases)):
            runner.batch(number, batch)
            done += len(batch)
            print(f"PASS package graph {done}/{len(cases)} native cases", flush=True)
        for number, (label, source, message) in enumerate(negative_cases()):
            runner.reject(number, label, source, message)
        identity.verify()
        report["compiler_identity"] = identity.record()
        report["status"] = "passed"
    except BaseException as exc:
        report.update(status="failed", error=str(exc), exception_type=type(exc).__name__)
        raise
    finally:
        original_error_active = sys.exc_info()[0] is not None
        final_errors = finalize_selected_identity(identity, report)
        final_errors += finalize_report(runner, report, compiler, artifacts)
        if final_errors and not original_error_active:
            raise AssertionError("run finalization failed: " + "; ".join(final_errors))
    scope = " [partial dev]" if args.profile == "dev" else ""
    print(
        f"PASS package graph{scope}: {len(cases)} native cases, "
        f"{report['complete_u64_observations']} complete u64 observations, "
        f"{2 * report['rejection_cases']} rejection runs; selected compiler identity unchanged",
        flush=True,
    )


if __name__ == "__main__":
    main()
