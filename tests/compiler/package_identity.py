#!/usr/bin/env python3
"""package.identity through one compiled driver fed every case as a record.

Inputs are generated here; expected results are the reviewed golden file
golden/package_identity.jsonl, frozen from the earlier independent regex/integer
model after it reproduced the old test's ordered expectations exactly. Each
golden row is the semantic result; `observations` expands it into the driver's
37-word observation layout. Rejections compile one source each.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random

import runtime_records as records

GOLDEN = Path(__file__).with_name("golden")
require = records.require
U32, U64 = (1 << 32) - 1, (1 << 64) - 1
IMIN, IMAX = records.MIN, records.MAX
FALLBACKS = (U64, 1 << 63, 0xFEDCBA9876543210)
BYTE_FALLBACK = 237
STATUSES = ("success", "malformed", "out_of_range")
OPERATIONS = ("parse", "construct", "compare", "normalized", "owned", "scoped", "eager")
SCALARS = ("operation", "length", "offset", "count", "right_length", "status", "name_length")
VERSION = ("major", "minor", "patch")


def signed(value):
    return "(-9223372036854775807-1)" if value == IMIN else str(value)


def observations(operation, expected):
    """The driver's observation words for one golden semantic result."""
    if operation in ("compare", "normalized", "eager"):
        return list(expected)
    # A failure is its status name; a success is [name, major, minor, patch].
    success = not isinstance(expected, str)
    status = "success" if success else expected
    name, version = (expected[0].encode("ascii"), tuple(expected[1:])) if success else (b"", (0, 0, 0))

    def at(index):
        return name[index] if 0 <= index < len(name) else BYTE_FALLBACK

    return [
        STATUSES.index(status) + 1,
        len(name),
        *(version if success else FALLBACKS),
        *name.ljust(24, b"\0"),
        *(at(index) for index in (0, len(name) - 1, len(name), -1, IMIN, IMAX, 23)),
        1,
    ]


def driver_source():
    declarations, initializers, reader = records.byte_fields()
    source = "module identity_driver;import package.identity;import std.array;\n"
    # A same-named private-helper shadow in the test module must not bind into
    # the defining module's parser; every case runs with it present.
    source += (
        "namespace package{auto lowercase(u8 value)->bool{return true;}auto digit(u8 value)->bool{return true;}}\n"
    )
    source += "auto observe(package::IdentityResult r,i64 slot)->u64{"
    source += "if(slot==0){if(r.status()==package::IdentityStatus::success){return 1u64;}"
    source += "if(r.status()==package::IdentityStatus::malformed){return 2u64;}"
    source += "if(r.status()==package::IdentityStatus::out_of_range){return 3u64;}return 999u64;}"
    source += "if(slot==1){return u64(r.name_size());}"
    for slot, (method, fallback) in enumerate(zip(("major_or", "minor_or", "patch_or"), FALLBACKS), 2):
        source += f"if(slot=={slot}){{return r.{method}({fallback}u64);}}"
    source += (
        "const std::array<u8,24> bytes=r.name_bytes_or_zero();if(slot>=5){if(slot<29){return u64(bytes.at(slot-5));}}"
    )
    for slot, index in enumerate(("0", "r.name_size()-1", "r.name_size()", "-1", signed(IMIN), signed(IMAX), "23"), 29):
        source += f"if(slot=={slot}){{return u64(r.name_byte_or({index},{BYTE_FALLBACK}u8));}}"
    source += (
        "if(slot==36){std::array<u8,24> changed=r.name_bytes_or_zero();"
        "i64 i=0;while(i<24){changed.set(i,255u8);i=i+1;}"
        "const std::array<u8,24> again=r.name_bytes_or_zero();"
        "i64 j=0;while(j<24){if(again.at(j)!=bytes.at(j)){return 0u64;}j=j+1;}return 1u64;}"
        "return 998u64;}\n"
    )
    source += "auto pass_copy(package::IdentityResult r)->package::IdentityResult{return r;}\n"
    source += (
        "class Counter{i64 calls;public:Counter():calls(0){}"
        "auto next()->u64{calls=calls+1;return 18446744073709551615u64;}"
        "auto byte()->u8{calls=calls+1;return 237u8;}auto count()const->i64{return calls;}};\n"
    )
    source += "class IdentityInput{" + declarations + "".join(f"i64 {name};" for name in SCALARS)
    source += "".join(f"u64 {name};" for name in VERSION) + "public:IdentityInput():"
    source += ",".join(initializers + [f"{name}(0)" for name in SCALARS] + [f"{name}(0u64)" for name in VERSION]) + "{}"
    source += reader
    span = "builtin::span<const u8>"
    load = records.ZERO_OWNER + "i64 at=0;while(at<length){owner[at]=input_byte(at);at=at+1;}"
    source += f"auto window({span} bytes)const->package::IdentityResult{{const {span} whole=bytes.subspan(0,length);"
    source += "const package::IdentityResult r=package::parse_identity(whole,offset,count);return r;}"
    source += f"auto whole_token({span} bytes,i64 size)const->package::IdentityResult{{"
    source += f"const {span} whole=bytes.subspan(0,size);"
    source += "const package::IdentityResult r=package::parse_identity(whole,0,size);return r;}"
    # The parsing owner is local to the call that returns the copied result.
    source += "auto make_owned()const->package::IdentityResult{" + load
    source += "const package::IdentityResult r=whole_token(borrow_bytes(owner),length);return r;}"
    source += "auto make_scoped()const->package::IdentityResult{{" + load
    source += "const package::IdentityResult r=whole_token(borrow_bytes(owner),length);return r;}}"
    source += "auto selected_status()const->package::IdentityStatus{"
    source += "".join(f"if(status=={n}){{return package::IdentityStatus::{name};}}" for n, name in enumerate(STATUSES))
    source += "return package::IdentityStatus::out_of_range;}"
    source += "auto storage()const->std::array<u8,24>{std::array<u8,24> bytes=std::array<u8,24>();"
    source += "i64 i=0;while(i<24){bytes.set(i,input_byte(i));i=i+1;}return bytes;}"
    source += "auto entry(i64 slot)const->u64{"
    source += "if(operation==0){" + load + "const package::IdentityResult parsed=window(borrow_bytes(owner));"
    source += "const package::IdentityResult r=parsed;i64 index=0;while(index<length){owner[index]=0u8;index=index+1;}"
    source += "return observe(r,slot);}"
    source += "if(operation==1){std::array<u8,24> bytes=storage();"
    source += "const package::IdentityResult r="
    source += "package::IdentityResult(selected_status(),bytes,name_length,major,minor,patch);"
    source += "i64 index=0;while(index<24){bytes.set(index,255u8);index=index+1;}return observe(r,slot);}"
    source += "if(operation==2){" + load
    source += 'builtin::array<u8,64> right="' + "\\0" * 64 + '";i64 r_at=0;'
    source += "while(r_at<right_length){right[r_at]=input_byte(length+r_at);r_at=r_at+1;}"
    source += "const package::IdentityResult l=whole_token(borrow_bytes(owner),length);"
    source += "const package::IdentityResult r=whole_token(borrow_bytes(right),right_length);"
    source += "if(slot==0){if(package::same_identity(l,r)){return 1u64;}return 0u64;}"
    source += "const package::VersionOrder order=package::compare_versions(l,r);"
    source += "if(order==package::VersionOrder::less){return 0u64;}"
    source += "if(order==package::VersionOrder::equal){return 1u64;}"
    source += "if(order==package::VersionOrder::greater){return 2u64;}return 3u64;}"
    # Forged invalid reports must normalize before comparison, in both orders.
    source += "if(operation==3){std::array<u8,24> name=std::array<u8,24>();name.set(0,97u8);"
    source += (
        "const package::IdentityResult l=package::IdentityResult(selected_status(),name,name_length,1u64,2u64,3u64);"
    )
    source += "const package::IdentityResult r="
    source += "package::IdentityResult(package::IdentityStatus::success,name,1,1u64,2u64,3u64);"
    source += "if(slot==0){if(package::same_identity(l,r)){return 1u64;}return 0u64;}"
    source += "if(slot==1){if(package::same_identity(r,l)){return 1u64;}return 0u64;}"
    source += (
        "if(slot==2){if(package::compare_versions(l,r)==package::VersionOrder::invalid){return 1u64;}return 0u64;}"
    )
    source += "if(package::compare_versions(r,l)==package::VersionOrder::invalid){return 1u64;}return 0u64;}"
    source += "if(operation==4){const package::IdentityResult local=make_owned();"
    source += "const package::IdentityResult r=pass_copy(local);return observe(r,slot);}"
    source += "if(operation==5){const package::IdentityResult r=make_scoped();return observe(r,slot);}"
    # Fallback arguments are evaluated eagerly, exactly once per call.
    source += "const package::IdentityResult r=make_owned();"
    source += "Counter counter=Counter();const u64 a=r.major_or(counter.next());"
    source += "const u64 b=r.minor_or(counter.next());const u64 c=r.patch_or(counter.next());"
    source += "const u8 d=r.name_byte_or(0,counter.byte());"
    source += "if(slot==0){return u64(counter.count());}if(slot==1){return a;}"
    source += "if(slot==2){return b;}if(slot==3){return c;}return u64(d);}};\n"
    return source


def parsing_cases():
    cases = []

    def add(label, data, offset=0, count=None):
        # A zero selected window is representable; accepted spans have no empty owner.
        data = data or b"\0"
        cases.append((label, "parse", dict(data=data, offset=offset, count=len(data) if count is None else count)))

    for token in (
        b"a@0.0.0",
        b"package-name@1.2.3",
        b"a1-b2@12.34.56",
        b"abcdefghijklmnopqrstuvwxyz"[:24] + b"@4294967295.4294967295.4294967295",
        b"a0-b1-c2-d3-e4-f5-g6-h7-i@0.0.0",
    ):
        add("canonical/" + token.decode(), token)
    for length in range(1, 27):
        add(f"name-length/{length}", b"a" * length + b"@0.0.0")
    for number in (0, 1, 9, 10, 99, 2147483647, 2147483648, U32 - 1, U32, U32 + 1, U64, 10**10):
        for component in range(3):
            parts = [b"2", b"3", b"4"]
            parts[component] = str(number).encode()
            add(f"component/{component}/{number}", b"a@" + b".".join(parts))
    for name in (
        b"",
        b"-",
        b"0",
        b"1a",
        b"A",
        b"a-",
        b"a--b",
        b"-a",
        b"a_b",
        b"a.b",
        b"a/b",
        b"a b",
        b"a\0b",
        "café".encode(),
        b"\xffa",
    ):
        add("invalid-name/" + name.hex(), name + b"@1.2.3")
    for value in (
        b"",
        b"00",
        b"01",
        b"0000000000",
        b"00000000000",
        b"+1",
        b"-1",
        b"1e2",
        b"0x1",
        b"1_0",
        b" 1",
        b"1 ",
        b"\x001",
        b"4294967296",
        b"9999999999",
    ):
        for component in range(3):
            parts = [b"1", b"2", b"3"]
            parts[component] = value
            add(f"invalid-component/{component}/{value.hex()}", b"a@" + b".".join(parts))
    for suffix in (b"\0", b"\n", b"\r", b"\r\n", b" ", b"\t", b"-pre", b"+build", b".4", b"@1.2.3", b";"):
        add("trailing/" + suffix.hex(), b"a@1.2.3" + suffix)
        add("leading/" + suffix.hex(), suffix + b"a@1.2.3")
    for token in (b"a@0.0.0", b"a1-b2@12.34.56", b"a" * 24 + b"@4294967295.4294967295.4294967295"):
        for cut in range(len(token)):
            add(f"prefix/{token.hex()}/{cut}", token, 0, cut)
            add(f"suffix/{token.hex()}/{cut}", token, cut + 1, len(token) - cut - 1)
    # Every byte at every position of a representative token: lowercase name,
    # name digit, internal hyphen, separator @, numeric starts/tails, both dots.
    token = b"a1-b2@12.34.56"
    for position in range(len(token)):
        for value in records.SAMPLE_BYTES:
            add(f"all-byte-substitution/{position}/{value}", token[:position] + bytes([value]) + token[position + 1 :])
    maximum = b"a@4294967295.4294967295.4294967295"
    for position in (11, 22, 33):
        for value in records.SAMPLE_BYTES:
            add(f"max-component-byte/{position}/{value}", maximum[:position] + bytes([value]) + maximum[position + 1 :])
    owner = b"\xff\0a@1.2.3\n\xff"
    for offset in (IMIN, -57, -1, 0, 1, 2, 3, len(owner) - 1, len(owner), len(owner) + 1, IMAX):
        for count in (IMIN, -1, 0, 1, 7, 57, len(owner), len(owner) + 1, IMAX):
            add(f"window/{offset}/{count}", owner, offset, count)
    add("window/exact-delimited", owner, 2, 7)
    for length in (58, 64, 128, 4096):
        add(f"bounded-long/{length}", b"a" * length)
        add(f"large-owner-small-window/{length}", b"\xff" * (length - 7) + b"a@1.2.3", length - 7, 7)
    rng = random.Random(220104)
    for index in range(128):
        name = bytes([rng.randrange(97, 123)]) + bytes(
            rng.choice(b"abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(rng.randrange(24))
        )
        version = tuple(rng.randrange(1 << 32) for _ in range(3))
        token = name + b"@" + b".".join(str(v).encode() for v in version)
        add(f"seed220104-valid/{index}", token)
        bad = bytearray(token)
        bad[rng.randrange(len(bad))] = rng.randrange(256)
        add(f"seed220104-mutation/{index}", bytes(bad))
    return cases


def construction_cases():
    cases = []

    def add(label, name=b"a", length=None, version=(1, 2, 3), status="success", tail=None):
        storage = bytearray(name[:24].ljust(24, b"\0"))
        if tail is not None:
            storage[tail[0]] = tail[1]
        major, minor, patch = version
        values = dict(status=STATUSES.index(status), name_length=len(name) if length is None else length)
        cases.append((label, "construct", dict(data=bytes(storage), major=major, minor=minor, patch=patch, **values)))

    for status in STATUSES:
        for length in (IMIN, -1, 0, 1, 24, 25, IMAX):
            add(f"constructor/{status}/length/{length}", length=length, status=status)
        add(f"constructor/{status}/poisoned", b"\xff" * 24, IMAX, (U64, U64, U64), status)
    for name in (b"a", b"a" * 24, b"a0-b9", b"1", b"A", b"a-", b"a--b", b"-a", b"a\0b", b"a_b"):
        add("constructor/name/" + name.hex(), name)
    for position in range(1, 24):
        for value in (1, 255):
            add(f"constructor/unused-tail/{position}/{value}", tail=(position, value))
    for value in (0, U32, U32 + 1, 1 << 63, U64):
        for component in range(3):
            version = [1, 2, 3]
            version[component] = value
            add(f"constructor/component/{component}/{value}", version=tuple(version))
    for value in records.SAMPLE_BYTES:
        add(f"constructor/first-byte/{value}", bytes([value]))
    return cases


def comparison_cases():
    tokens = (
        b"a@0.0.0",
        b"a@0.0.1",
        b"a@0.1.0",
        b"a@1.0.0",
        b"b@1.0.0",
        b"a@4294967295.0.0",
        b"a@0.4294967295.0",
        b"a@0.0.4294967295",
        b"a@4294967295.4294967295.4294967295",
        b"A@1.0.0",
        b"a@01.0.0",
    )
    cases = [
        (f"comparison/{i}/{j}", "compare", dict(data=left + right, right_length=len(right)))
        for i, left in enumerate(tokens)
        for j, right in enumerate(tokens)
    ]
    for i, (status, length) in enumerate((("success", 0), ("malformed", 1), ("out_of_range", 1))):
        values = dict(status=STATUSES.index(status), name_length=length)
        cases.append((f"comparison/normalized-invalid/{status}", "normalized", values))
    return cases


def ownership_cases():
    token = b"owned-name@4294967295.2147483648.17"
    cases = [
        ("ownership/function-owner-scope-exit", "owned", dict(data=token)),
        ("ownership/nested-owner-scope-exit", "scoped", dict(data=token)),
        ("eager-fallback/True", "eager", dict(data=b"a@1.2.3")),
        ("eager-fallback/False", "eager", dict(data=b"a@01.2.3")),
    ]
    for token in (b"A@1.2.3", b"a@x.2.3", b"a@1.2.3"):
        cases.append(("private-helper-shadow/" + token.decode(), "parse", dict(data=token, offset=0, count=len(token))))
    return cases


def all_cases():
    return parsing_cases() + construction_cases() + comparison_cases() + ownership_cases()


def packet(program, operation, values):
    values = dict(values)
    data = values.pop("data", b"")
    if operation == "compare":
        values["length"] = len(data) - values["right_length"]
    else:
        values["length"] = len(data)
    return program.pack(data=data, operation=OPERATIONS.index(operation), **values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    args = parser.parse_args()
    cases = all_cases()
    golden = records.load_jsonl(GOLDEN / "package_identity.jsonl")
    require(len(golden) == len(cases), f"{len(cases)} generated cases, {len(golden)} golden rows")
    for (label, _, _), row in zip(cases, golden):
        require(row["label"] == label, f"golden row {row['label']!r} for case {label!r}")
    with records.scratch("package-identity") as scratch:
        driver = records.Driver(args.compiler, scratch)
        program = driver.build(driver_source(), "IdentityInput", kind="u64")
        count, words = program.check(
            (
                (label, packet(program, operation, values), observations(operation, row["expected"]))
                for (label, operation, values), row in zip(cases, golden)
            ),
            scratch,
        )
        rejections = driver.reject_all(GOLDEN / "package_identity_rejections.jsonl")
    print(f"PASS package identity: {count} cases, {words} u64 observations, {rejections} rejections")


if __name__ == "__main__":
    main()
