#!/usr/bin/env python3
"""package.graph through one compiled driver fed every case as a record.

Inputs are generated here; expected results are the reviewed golden file
golden/package_graph.jsonl, frozen from the earlier independent permutation-search
reference (evidence/package-graph/oracle/reference-v1) after it reproduced the
old test's ordered expectations exactly. Golden rows hold semantic results (a
failure status, or the order and catalog roots); `words` expands them into the
driver's observation layout. Rejections compile one source each.
"""

from __future__ import annotations

import argparse
import itertools
from pathlib import Path

import runtime_records as records

GOLDEN = Path(__file__).with_name("golden")
require = records.require
U32, U64 = (1 << 32) - 1, (1 << 64) - 1
IMIN, IMAX = records.MIN, records.MAX
COUNT_FALLBACK = IMIN + 123456789
INDEX_FALLBACK = -81985529216486896
RANK_FALLBACK = IMIN + 918273645
VERSION_FALLBACKS = (U64, 1 << 63, 0xFEDCBA9876543210)
ORDER_RANKS = tuple(range(8)) + (-1, 8, IMIN, IMAX)
ORDER_WIDTH = 2 + len(ORDER_RANKS)
ENTRY_WIDTH = 12
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
IDENTITY = ("success", "malformed", "out_of_range")
OPERATIONS = ("catalog", "order", "entry", "owned", "eager", "independent", "getters", "lexical")
SCALARS = (
    "operation",
    "length",
    "count",
    "rank_count",
    "status",
    "name_length",
    "identity_status",
    "rank",
    "index",
    *(f"offset{i}" for i in range(8)),
    *(f"extent{i}" for i in range(8)),
    *(f"order{i}" for i in range(8)),
    *(f"rank{i}" for i in range(12)),
)
VERSIONS = ("major", "minor", "patch")
# Driver calls per case; a catalog makes one for its order and one per rank.
CALLS = dict(order=1, entry=1, owned=1, eager=1, independent=1, getters=1, lexical=1)
SPAN = "builtin::span<const u8>"
ARRAY = "std::array<i64,8>"


def signed(value):
    return "(-9223372036854775807-1)" if value == IMIN else str(value)


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
    offsets, lengths, data = [], [], b""
    for value in manifests:
        offsets.append(len(data))
        lengths.append(len(value))
        data += value
    return data or b"\0", offsets + [0] * (8 - len(offsets)), lengths + [0] * (8 - len(lengths))


def name_words(name):
    """The 24 name bytes as three little-endian u64 words, as the driver packs them."""
    name = name.ljust(24, b"\0")
    return tuple(int.from_bytes(name[i : i + 8], "little") for i in range(0, 24, 8))


def identity_words(token):
    if token is None:
        return (2, 0, *VERSION_FALLBACKS, *name_words(b""))
    name, version = token.split("@")
    return (1, len(name), *(int(part) for part in version.split(".")), *name_words(name.encode("ascii")))


def order_words(status, order=(), count=0):
    good = status == "success"
    return (
        STATUSES.index(status) + 1,
        count if good else COUNT_FALLBACK & U64,
        *(order[r] if good and 0 <= r < count else INDEX_FALLBACK & U64 for r in ORDER_RANKS),
    )


def entry_words(status, count=0, rank=0, index=0, token=None):
    good = status == "success"
    return (
        STATUSES.index(status) + 1,
        count if good else COUNT_FALLBACK & U64,
        rank if good else RANK_FALLBACK & U64,
        index if good else INDEX_FALLBACK & U64,
        *identity_words(token if good else None),
    )


def catalog_words(expected, ranks):
    """A catalog result is a failure status, or [order, catalog root tokens]."""
    if isinstance(expected, str):
        return order_words(expected) + sum((entry_words(expected) for _ in ranks), ())
    order, roots = expected
    result = order_words("success", order, len(order))
    for rank in ranks:
        if 0 <= rank < len(order):
            result += entry_words("success", len(order), rank, order[rank], roots[order[rank]])
        else:
            result += entry_words("index_out_of_range")
    return result


def words(operation, values, expected):
    if operation == "catalog":
        return list(catalog_words(expected, values["ranks"]))
    if operation == "order":
        return list(order_words(*expected) if isinstance(expected, list) else order_words(expected))
    if operation == "entry":
        return list(entry_words(*expected) if isinstance(expected, list) else entry_words(expected))
    return list(expected)


def driver_source():
    declarations, initializers, reader = records.byte_fields()
    source = (
        "module graph_driver;import package.graph;import package.manifest;import package.identity;import std.array;\n"
    )
    # Same-named private-helper shadows in the test module must not bind into
    # the defining module; every case runs with them present.
    source += (
        "namespace package{auto graph_name_equal(IdentityResult a,IdentityResult b)->bool{return false;}"
        "auto graph_name_less(IdentityResult a,IdentityResult b)->bool{return false;}"
        "auto graph_identity_error()->IdentityResult{const std::array<u8,24> n=std::array<u8,24>();"
        "const IdentityResult r=IdentityResult(IdentityStatus::out_of_range,n,0,0u64,0u64,0u64);return r;}}\n"
    )
    source += "auto bits(i64 x)->u64{if(x<0){return 9223372036854775808u64+u64(x-(-9223372036854775807-1));}"
    source += "return u64(x);}\nauto observe_status(package::GraphStatus s)->u64{"
    for n, status in enumerate(STATUSES):
        source += f"if(s==package::GraphStatus::{status}){{return {n + 1}u64;}}"
    source += (
        "return 0u64;}\nauto observe_identity(package::IdentityResult r,i64 slot)->u64{"
        "if(slot==0){if(r.status()==package::IdentityStatus::success){return 1u64;}"
        "if(r.status()==package::IdentityStatus::malformed){return 2u64;}return 3u64;}"
        "if(slot==1){return u64(r.name_size());}"
    )
    for n, (method, fallback) in enumerate(zip(("major_or", "minor_or", "patch_or"), VERSION_FALLBACKS), 2):
        source += f"if(slot=={n}){{return r.{method}({fallback}u64);}}"
    # Every name byte is observed, eight to a word, lowest index in the low byte.
    source += "const std::array<u8,24> name=r.name_bytes_or_zero();const i64 first=8*(slot-5);"
    source += "u64 word=0u64;i64 i=7;while(i>=0){word=(word<<8)|u64(name.at(first+i));i=i-1;}return word;}\n"
    source += "auto observe_order(package::GraphOrderResult r,i64 slot)->u64{"
    source += "if(slot==0){return observe_status(r.status());}"
    source += f"if(slot==1){{return bits(r.package_count_or({signed(COUNT_FALLBACK)}));}}"
    source += f"const array<i64,{len(ORDER_RANKS)}> ranks={{" + ",".join(signed(r) for r in ORDER_RANKS) + "};"
    source += f"return bits(r.catalog_index_or(ranks[slot-2],{signed(INDEX_FALLBACK)}));}}\n"
    source += "auto observe_entry(package::GraphEntryResult r,i64 slot)->u64{"
    source += "if(slot==0){return observe_status(r.status());}"
    for n, (method, fallback) in enumerate(
        (("package_count_or", COUNT_FALLBACK), ("rank_or", RANK_FALLBACK), ("catalog_index_or", INDEX_FALLBACK)), 1
    ):
        source += f"if(slot=={n}){{return bits(r.{method}({signed(fallback)}));}}"
    source += (
        "const package::IdentityResult identity=r.identity_or_error();return observe_identity(identity,slot-4);}\n"
    )
    source += "auto copy_order(package::GraphOrderResult r)->package::GraphOrderResult{return r;}\n"
    source += "auto copy_entry(package::GraphEntryResult r)->package::GraphEntryResult{return r;}\n"
    source += (
        "class Counter{i64 calls;public:Counter():calls(0){}"
        "auto next()->i64{calls=calls+1;return -81985529216486896;}auto count()const->i64{return calls;}};\n"
    )
    source += "class GraphInput{" + declarations + "".join(f"i64 {name};" for name in SCALARS)
    source += "".join(f"u64 {name};" for name in VERSIONS) + "builtin::array<u64,64> words;public:GraphInput():"
    source += ",".join(
        initializers + [f"{name}(0)" for name in SCALARS] + [f"{name}(0u64)" for name in VERSIONS] + ["words{}"]
    )
    source += "{}" + reader
    load = records.ZERO_OWNER + "i64 at=0;while(at<length){owner[at]=input_byte(at);at=at+1;}"
    for kind in ("offset", "extent", "order"):
        source += f"auto {kind}s()const->{ARRAY}{{{ARRAY} values={ARRAY}();"
        source += "".join(f"values.set({i},{kind}{i});" for i in range(8)) + "return values;}"
    source += "auto selected_rank(i64 k)const->i64{"
    source += "".join(f"if(k=={i}){{return rank{i};}}" for i in range(11)) + "return rank11;}"
    source += f"auto order_view({SPAN} bytes,{ARRAY} offsets,{ARRAY} lengths)const->package::GraphOrderResult{{"
    source += f"const {SPAN} whole=bytes.subspan(0,length);"
    source += "const package::GraphOrderResult r=package::order_manifests(whole,offsets,lengths,count);return r;}"
    source += f"auto entry_view({SPAN} bytes,{ARRAY} offsets,{ARRAY} lengths,i64 selected)const"
    source += f"->package::GraphEntryResult{{const {SPAN} whole=bytes.subspan(0,length);"
    source += "const package::GraphEntryResult r=package::ordered_manifest(whole,offsets,lengths,count,selected);"
    source += "return r;}"
    # Owners local to these calls are destroyed before their copied results are used.
    source += "auto make_order()const->package::GraphOrderResult{" + load
    source += "const package::GraphOrderResult r=order_view(borrow_bytes(owner),offsets(),extents());return r;}"
    source += "auto make_entry()const->package::GraphEntryResult{" + load
    source += "const package::GraphEntryResult r=entry_view(borrow_bytes(owner),offsets(),extents(),0);return r;}"
    source += "auto graph_status()const->package::GraphStatus{"
    source += "".join(f"if(status=={n}){{return package::GraphStatus::{name};}}" for n, name in enumerate(STATUSES))
    source += "return package::GraphStatus::index_out_of_range;}"
    source += "auto identity_state()const->package::IdentityStatus{"
    source += "".join(
        f"if(identity_status=={n}){{return package::IdentityStatus::{name};}}" for n, name in enumerate(IDENTITY)
    )
    source += "return package::IdentityStatus::out_of_range;}"
    # Each call computes one report and writes its whole observation block.
    for kind, result, width in (("order", "GraphOrderResult", ORDER_WIDTH), ("entry", "GraphEntryResult", ENTRY_WIDTH)):
        source += f"auto put_{kind}(package::{result} r,i64 at)->i64{{i64 slot=0;"
        source += f"while(slot<{width}){{words[at+slot]=observe_{kind}(r,slot);slot=slot+1;}}return at+{width};}}"
    source += "auto entry(i64 part)->i64{"
    # Each complete report is copied; the owner bytes and caller-owned
    # selection arrays are then poisoned before it is observed.
    poison = (
        "i64 p=0;while(p<length){owner[p]=255u8;p=p+1;}"
        "offsets.set(0,(-9223372036854775807-1));lengths.set(0,9223372036854775807);"
    )
    source += "if(operation==0){" + load + f"{ARRAY} offsets=offsets();{ARRAY} lengths=extents();"
    source += "if(part==0){const package::GraphOrderResult original="
    source += "order_view(borrow_bytes(owner),offsets,lengths);const package::GraphOrderResult r=original;"
    source += poison + "return put_order(r,0);}"
    source += "const package::GraphEntryResult original="
    source += "entry_view(borrow_bytes(owner),offsets,lengths,selected_rank(part-1));"
    source += "const package::GraphEntryResult r=original;" + poison + "return put_entry(r,0);}"
    source += f"if(operation==1){{{ARRAY} order=orders();"
    source += "const package::GraphOrderResult original=package::GraphOrderResult(graph_status(),order,count);"
    source += "const package::GraphOrderResult r=original;order.set(0,9223372036854775807);return put_order(r,0);}"
    source += "if(operation==2){std::array<u8,24> name=std::array<u8,24>();"
    source += "i64 i=0;while(i<24){name.set(i,input_byte(i));i=i+1;}"
    source += "const package::IdentityResult identity="
    source += "package::IdentityResult(identity_state(),name,name_length,major,minor,patch);"
    source += "const package::GraphEntryResult original="
    source += "package::GraphEntryResult(graph_status(),identity,count,rank,index);"
    source += "const package::GraphEntryResult r=original;name.set(0,255u8);return put_entry(r,0);}"
    source += "if(operation==3){const package::GraphOrderResult a=make_order();"
    source += "const package::GraphOrderResult o=copy_order(a);"
    source += "const package::GraphEntryResult b=make_entry();const package::GraphEntryResult e=copy_entry(b);"
    source += "return put_entry(e,put_order(o,0));}"
    source += "if(operation==7){" + load + f"{ARRAY} offsets=offsets();{ARRAY} lengths=extents();"
    # A local named span ends before the input overwrite.
    source += f"{{const {SPAN} span=borrow_bytes(owner);{{const {SPAN} child=span;"
    source += "const package::GraphOrderResult r=order_view(child,offsets,lengths);"
    source += "if(r.status()!=package::GraphStatus::success){words[0]=0u64;return 1;}}}"
    source += "owner[0]=0u8;words[0]=42u64;return 1;}"
    source += load + f"{ARRAY} offsets=offsets();{ARRAY} lengths=extents();"
    # Fallback arguments are evaluated eagerly, exactly once per call.
    source += "if(operation==4){const package::GraphOrderResult o=order_view(borrow_bytes(owner),offsets,lengths);"
    source += "const package::GraphEntryResult e=entry_view(borrow_bytes(owner),offsets,lengths,0);"
    source += "Counter c=Counter();const i64 a=o.package_count_or(c.next());const i64 b=o.catalog_index_or(0,c.next());"
    source += "const i64 d=e.package_count_or(c.next());const i64 f=e.rank_or(c.next());"
    source += "const i64 g=e.catalog_index_or(c.next());words[0]=bits(c.count());words[1]=bits(a);"
    source += "words[2]=bits(b);words[3]=bits(d);words[4]=bits(f);words[5]=bits(g);return 6;}"
    # Separate calls observe their own changed input; retained reports stay copied.
    source += (
        "if(operation==5){const package::GraphEntryResult before=entry_view(borrow_bytes(owner),offsets,lengths,0);"
    )
    source += "owner[0]=0u8;const package::GraphEntryResult after=entry_view(borrow_bytes(owner),offsets,lengths,0);"
    source += "return put_entry(after,put_entry(before,0));}"
    source += "const package::GraphEntryResult r=entry_view(borrow_bytes(owner),offsets,lengths,0);"
    source += "const package::IdentityResult identity=r.identity_or_error();"
    source += "std::array<u8,24> name=identity.name_bytes_or_zero();i64 i=0;"
    source += "while(i<24){name.set(i,255u8);i=i+1;}return put_entry(r,0);}};\n"
    return source


def catalog(label, manifests=None, *, data=None, offsets=None, lengths=None, count=None, ranks=None):
    if data is None:
        data, offsets, lengths = pack(manifests)
    count = len(manifests) if count is None else count
    if ranks is None:
        ranks = tuple(range(count)) if 0 < count <= 8 else (0,)
    return (label, "catalog", dict(data=data, offsets=offsets, lengths=lengths, count=count, ranks=ranks))


def exhaustive_cases():
    """Every dependency mask over up to four packages, in several catalog orders."""
    cases = []
    for n in range(5):
        edges = list(itertools.permutations(range(n), 2))
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
                label = f"exhaustive/{n}/{mask}/{''.join(map(str, perm))}"
                cases.append(catalog(label, [manifests[i] for i in perm]))
    return cases


def adversarial_cases():
    cases = []

    def add(label, ms=None, **kw):
        cases.append(catalog("adversarial/" + label, ms, **kw))

    a = make_manifest(b"a")
    b = make_manifest(b"b")
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
    for cut in range(len(valid)):
        add(f"truncation/{cut}", data=valid, offsets=[0] * 8, lengths=[cut] + [0] * 7, count=1, ranks=(0,))
    for token in (
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
    ):
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
    # Every byte position of a two-package catalog, poisoned with 0, CR and 255.
    data, offsets, lengths = pack([a, b])
    for position in range(len(data)):
        for byte in (0, 13, 255):
            mutated = data[:position] + bytes([byte]) + data[position + 1 :]
            add(f"byte-mutation/{position}/{byte}", data=mutated, offsets=offsets, lengths=lengths, count=2, ranks=(0,))
    maximum = make_manifest(
        b"z" * 24, (U32, U32, U32), tuple((bytes([97 + i]) + b"q" * 23, (U32, U32, U32)) for i in range(8))
    )
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

    def order(label, status, values, count):
        fields = {f"order{i}": value for i, value in enumerate(values)}
        cases.append((label, "order", dict(status=STATUSES.index(status), count=count, **fields)))

    for status in STATUSES:
        for n in (IMIN, -1, 0, 1, 2, 8, 9, IMAX):
            for number, values in enumerate((orders[min(max(n, 0), 8)], poisons[abs(n) % len(poisons)])):
                order(f"constructor/order/{status}/{n}/{number}", status, values, n)
    # Each unused slot, duplicate position and selected bound is independently poisoned.
    for n in range(9):
        for i in range(8):
            values = list(orders[n])
            values[i] = IMIN if i < n else 1
            order(f"constructor/order-each-slot/{n}/{i}", "success", values, n)
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
                name = bytearray(b"copied-name".ljust(24, b"\0"))
                length, version, identity = len(b"copied-name"), (U32, 1 << 31, 17), "success"
                if bad == "padding":
                    name[23] = 255
                if bad == "length":
                    length = IMAX
                if bad == "version":
                    version = (U64, 0, 0)
                if bad == "status":
                    identity = "out_of_range"
                values = dict(status=STATUSES.index(status), count=n, rank=rank, index=index, name_length=length)
                values.update(identity_status=IDENTITY.index(identity), **dict(zip(VERSIONS, version)))
                cases.append(
                    (f"constructor/entry/{status}/{n}/{rank}/{index}/{bad}", "entry", dict(data=bytes(name), **values))
                )
    return cases


def ownership_cases():
    data, offsets, lengths = pack(
        [
            make_manifest(b"root", (U32, 1 << 31, 17), ((b"dep", (17, 1 << 31, U32)),)),
            make_manifest(b"dep", (17, 1 << 31, U32)),
        ]
    )
    common = dict(offsets=offsets, lengths=lengths, count=2)
    return [
        ("ownership/scope-exit-and-function-copies", "owned", dict(data=data, **common)),
        ("ownership/eager-fallback/True", "eager", dict(data=data, **common)),
        ("ownership/eager-fallback/False", "eager", dict(data=b"\0" + data[1:], **common)),
        ("ownership/independent-observations-after-mutation", "independent", dict(data=data, **common)),
        ("ownership/getter-copy-isolation", "getters", dict(data=data, **common)),
        ("ownership/supported-lexical-borrow-release", "lexical", dict(data=data, **common)),
    ]


def binding_cases():
    return [
        catalog("defining-module-binding/" + name, ms)
        for name, ms in (
            ("lexical", [make_manifest(b"z"), make_manifest(b"a"), make_manifest(b"a-a")]),
            ("duplicate", [make_manifest(b"a"), make_manifest(b"a")]),
            ("missing", [make_manifest(b"a", deps=((b"b", (0, 0, 0)),))]),
        )
    ]


def all_cases():
    return exhaustive_cases() + adversarial_cases() + construction_cases() + ownership_cases() + binding_cases()


def packet(program, operation, values):
    values = dict(values)
    data = values.pop("data", b"\0")
    for name, prefix in (("offsets", "offset"), ("lengths", "extent")):
        values.update({f"{prefix}{i}": value for i, value in enumerate(values.pop(name, ()))})
    ranks = values.pop("ranks", ())
    values.update({f"rank{i}": value for i, value in enumerate(ranks)}, rank_count=len(ranks))
    return program.pack(data=data, operation=OPERATIONS.index(operation), length=len(data), **values)


def sampled(label):
    # Merge keeps every graph of up to three packages and samples those of four.
    if not label.startswith("exhaustive/4/"):
        return True
    mask = int(label.split("/")[2])
    return mask % 37 == 0 or mask in (0, 1, 2048, 4095)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    records.profile(parser)
    args = parser.parse_args()
    golden = records.load_jsonl(GOLDEN / "package_graph.jsonl")
    cases = all_cases()
    require(len(golden) == len(cases), f"{len(cases)} generated cases, {len(golden)} golden rows")
    for (label, _, _), row in zip(cases, golden):
        require(row["label"] == label, f"golden row {row['label']!r} for case {label!r}")
    if args.profile == "merge":
        cases, golden = zip(*((case, row) for case, row in zip(cases, golden) if sampled(case[0])))
    with records.scratch("package-graph") as scratch:
        driver = records.Driver(args.compiler, scratch)
        program = driver.build(driver_source(), "GraphInput", kind="u64", words="words")
        count, observed = program.check(
            (
                (
                    label,
                    packet(program, operation, values),
                    words(operation, values, row["expected"]),
                    CALLS.get(operation) or 1 + len(values["ranks"]),
                )
                for (label, operation, values), row in zip(cases, golden)
            ),
            scratch,
        )
        rejections = driver.reject_all(GOLDEN / "package_graph_rejections.jsonl")
    print(f"PASS package graph ({args.profile}): {count} cases, {observed} u64 observations, {rejections} rejections")


if __name__ == "__main__":
    main()
