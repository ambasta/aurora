#!/usr/bin/env python3
"""Owned UTF-8 invariants, transactional failures and real JSON consumption.

All programs are packed into one compiled, linked hosted binary (owned_bytes
deferred mode); each invocation selects a program and supplies its case as
arguments. Input samples are one table indexed by argument, not a program per
sample. Scalar bytes, initialization status and JSON output come from Python's
UTF-8 codec and json module. Rejections compile one source each.
"""

import argparse
import json
from pathlib import Path
import tempfile

from owned_bytes import ROOT, Suite

IMPORTS = """module text_test;
import std.utf8_text;
import std.utf8;
import std.array;
import std.json;
import std.json_write;
import std.byte_buffer;
import std.binary;
"""
CREATE = """
    builtin::OwnedBytes allocation = region.try_allocate(16);
    std::Utf8Text text = std::Utf8Text(region, move(allocation));
"""
TEXT_STATUSES = (
    "success",
    "unavailable",
    "not_empty",
    "invalid_utf8",
    "truncated",
    "invalid_scalar",
    "allocation_failed",
)
SAMPLES = (
    b"",
    b'A\0\n"\\',
    "é€😀".encode(),
    b"\x80",
    b"\xc0\x80",
    b"\xed\xa0\x80",
    b"\xf4\x90\x80\x80",
    b"\xe2\x82",
    b"\xf0\x9f\x98",
    b"\xff",
)
TRANSACTIONS = (("😀".encode(), "success"), (b"AAA\xff", "invalid_utf8"), (b"AAA\xe2\x82", "truncated"))


def program(body, helpers=""):
    return IMPORTS + helpers + "auto entry(builtin::ByteRegion region,i64 n,i64 flag)->i64 {\n" + body + "\n}"


def table(samples):
    """One byte pool plus start/size tables; `input` is sample n as a subspan."""
    pool = b"".join(samples) or b"\0"
    starts, at = [], 0
    for sample in samples:
        starts.append(at)
        at += len(sample)
    return (
        f"const array<u8,{len(pool)}> pool={{{','.join(f'{byte}u8' for byte in pool)}}};\n"
        f"const array<i64,{len(samples)}> starts={{{','.join(map(str, starts))}}};\n"
        f"const array<i64,{len(samples)}> sizes={{{','.join(str(len(s)) for s in samples)}}};\n"
        "const builtin::span<const u8> all=borrow_bytes(pool);\n"
        "const builtin::span<const u8> input=all.subspan(starts[n],sizes[n]);\n"
    )


def ordinal(name):
    status = "i64 code=0;"
    for number, value in enumerate(TEXT_STATUSES):
        status += f"if({name}==std::Utf8TextStatus::{value}){{code={number};}}"
    return status


def strict_status(data):
    try:
        data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        return "truncated" if error.reason == "unexpected end of data" else "invalid_utf8"
    return "success"


def cases(suite):
    scalar = suite.compile(
        "scalars",
        program(
            CREATE
            + """
        u64 scalar=18446744073709551615u64;
        if(n>=0){scalar=u64(n);}
        const std::Utf8TextStatus status=text.try_append_scalar(scalar);
        if(flag==1) {
            if(status!=std::Utf8TextStatus::invalid_scalar || text.size()!=0 || text.capacity()!=16){return -1;}
            return 42;
        }
        if(status!=std::Utf8TextStatus::success){return -2;}
        const builtin::span<const u8> view=text.bytes();
        i64 result=0;
        i64 index=0;
        while(index<view.size()){result=result*256+i64(view.at(index));index=index+1;}
        return result;
    """
        ),
    )
    for value in (0, 1, 31, 34, 92, 127, 128, 2047, 2048, 55295, 57344, 65535, 65536, 1114111):
        suite.run(scalar, 128, value, 0, int.from_bytes(chr(value).encode(), "big"), 1, 1)
    for value in (55296, 57343, 1114112, -1):
        suite.run(scalar, 128, value, 1, 42, 1, 1)

    # Flag -2 reports the first initialization status (and, after success, a
    # repeated initialization) and checks a failed one left the text unchanged;
    # flag -1 is the JSON size and flag >= 0 one JSON byte.
    samples = suite.compile(
        "samples",
        program(
            CREATE
            + table(SAMPLES)
            + "const std::Utf8TextStatus first=text.try_initialize(input);"
            + ordinal("first")
            + """
            if(first!=std::Utf8TextStatus::success){
                if(text.size()!=0 || text.capacity()!=16){return -2;}
                return code;
            }
            const i64 initial=code;
            const std::Utf8TextStatus repeat=text.try_initialize(input);
            """
            + ordinal("repeat").replace("i64 code=0;", "code=0;")
            + """
            if(flag==-2){return initial+16*code;}
            builtin::OwnedBytes other=region.try_allocate(64);
            std::ByteBuffer output=std::ByteBuffer(region,move(other));
            if(std::append_json_text(output,text)!=std::JsonStringAppendStatus::success){return -3;}
            const builtin::span<const u8> bytes=output.bytes();
            if(flag==-1){return bytes.size();}
            return i64(bytes.at(flag));
        """
        ),
    )
    for index, data in enumerate(SAMPLES):
        status = strict_status(data)
        if status != "success":
            suite.run(samples, 128, index, -2, TEXT_STATUSES.index(status), 1, 1)
            continue
        repeat = "success" if not data else "not_empty"
        suite.run(samples, 128, index, -2, 16 * TEXT_STATUSES.index(repeat), 1, 1)
        expected = json.dumps(data.decode("utf-8", "strict"), ensure_ascii=False).encode()
        suite.run(samples, 128, index, -1, len(expected), 2, 2)
        for offset, byte in enumerate(expected):
            suite.run(samples, 128, index, offset, byte, 2, 2)

    failure = suite.compile(
        "allocation-transaction",
        program("""
        builtin::OwnedBytes allocation=region.try_allocate(1);
        std::Utf8Text text=std::Utf8Text(region,move(allocation));
        if(!text.ok()){return 41;}
        const array<u8,2> pair={65u8,66u8};
        const builtin::span<const u8> input=borrow_bytes(pair);
        if(flag==0){
            if(text.try_initialize(input)!=std::Utf8TextStatus::allocation_failed){return -1;}
            if(text.size()!=0 || text.capacity()!=1){return -2;}
            const builtin::span<const u8> one=input.subspan(0,1);
            if(text.try_initialize(one)!=std::Utf8TextStatus::success){return -8;}
        }else{
            if(text.try_append_scalar(65u64)!=std::Utf8TextStatus::success){return -3;}
            if(text.try_append_scalar(128512u64)!=std::Utf8TextStatus::allocation_failed){return -4;}
            if(text.size()!=1 || text.capacity()!=1){return -5;}
            if(text.try_initialize(input)!=std::Utf8TextStatus::not_empty){return -6;}
            const builtin::span<const u8> bytes=text.bytes();
            if(bytes.at(0)!=65u8){return -7;}
        }
        return 42;
    """),
    )
    suite.run(failure, 0, 0, 0, 41, 0, 0)
    for flag in (0, 1):
        suite.run(failure, 1, 0, flag, 42, 1, 1)
        suite.run(failure, 128, 0, flag, 42, 1, 1, fail_after=1)

    growth = suite.compile(
        "successful-growth",
        program("""
        builtin::OwnedBytes allocation=region.try_allocate(1);
        std::Utf8Text text=std::Utf8Text(region,move(allocation));
        if(text.try_append_scalar(65u64)!=std::Utf8TextStatus::success){return -1;}
        if(text.try_append_scalar(128512u64)!=std::Utf8TextStatus::success){return -2;}
        const builtin::span<const u8> bytes=text.bytes();
        if(bytes.size()!=5 || bytes.at(0)!=65u8 || bytes.at(4)!=128u8){return -3;}
        return 42;
    """),
    )
    suite.run(growth, 128, 0, 0, 42, 2, 1, release_order=[1, 2])
    json_failure = suite.compile(
        "json-transaction",
        program(
            CREATE
            + """
        text.try_append_scalar(65u64);
        i64 capacity=1;
        if(flag==1){capacity=1000;}
        builtin::OwnedBytes other=region.try_allocate(capacity);
        std::ByteBuffer output=std::ByteBuffer(region,move(other));
        if(flag==0){output.try_append(33u8);}
        if(std::append_json_text(output,text)!=std::JsonStringAppendStatus::append_failed){return -1;}
        if(text.size()!=1 || text.capacity()!=16){return -2;}
        if(flag==0){
            if(output.size()!=1 || output.capacity()!=1){return -3;}
            const builtin::span<const u8> bytes=output.bytes();
            if(bytes.at(0)!=33u8){return -4;}
        }else{if(output.ok() || output.size()!=0){return -5;}}
        return 42;
    """
        ),
    )
    suite.run(json_failure, 17, 0, 0, 42, 2, 2)
    suite.run(json_failure, 128, 0, 0, 42, 2, 2, fail_after=2)
    suite.run(json_failure, 128, 0, 1, 42, 1, 1)
    unavailable = suite.compile(
        "unavailable",
        program(
            CREATE
            + """
        const array<u8,1> data={65u8};
        const builtin::span<const u8> input=borrow_bytes(data);
        if(text.ok() || text.try_initialize(input)!=std::Utf8TextStatus::unavailable){return -1;}
        if(text.try_append_scalar(65u64)!=std::Utf8TextStatus::unavailable){return -2;}
        builtin::OwnedBytes other=region.try_allocate(0);
        std::ByteBuffer output=std::ByteBuffer(region,move(other));
        if(std::append_json_text(output,text)!=std::JsonStringAppendStatus::append_failed){return -3;}
        if(output.size()!=0 || output.capacity()!=0){return -4;}
        return 42;
    """
        ),
    )
    suite.run(unavailable, 0, 0, 0, 42, 1, 1)
    # A one-byte allocation must grow for a valid sample and stay untouched for
    # an invalid one. Returns the status, or 42 plus the copied-byte check.
    transaction = suite.compile(
        "initialization-transaction",
        program(
            CREATE.replace("try_allocate(16)", "try_allocate(1)")
            + table([data for data, _ in TRANSACTIONS])
            + "const std::Utf8TextStatus status=text.try_initialize(input);"
            + ordinal("status")
            + """
            if(status!=std::Utf8TextStatus::success){
                if(text.size()!=0 || text.capacity()!=1){return -2;}
                return code;
            }
            const builtin::span<const u8> bytes=text.bytes();
            if(bytes.size()!=input.size()){return -2;}
            i64 index=0;
            while(index<bytes.size()){if(bytes.at(index)!=input.at(index)){return -3;}index=index+1;}
            return 42;
        """
        ),
    )
    for index, (data, status) in enumerate(TRANSACTIONS):
        if strict_status(data) != status:
            raise AssertionError(f"transaction sample {data!r} is not {status}")
        # The existing native adapter allocates a 32-byte header plus payload.
        success = status == "success"
        suite.run(
            transaction,
            128,
            index,
            0,
            42 if success else TEXT_STATUSES.index(status),
            2 if success else 1,
            1,
            attempted_sizes=[33, 32 + len(data)] if success else [33],
        )
    moved = suite.compile(
        "move-and-release",
        program(
            CREATE
            + """
        text.try_append_scalar(65u64);
        {const builtin::span<const u8> first=text.bytes();if(first.at(0)!=65u8){return -1;}}
        std::Utf8Text next=move(text);
        next.try_append_scalar(66u64);
        const builtin::span<const u8> view=next.bytes();
        return i64(view.at(0))+i64(view.at(1));
    """
        ),
    )
    suite.run(moved, 128, 0, 0, 131, 1, 1, release_order=[1])
    view = "const builtin::span<const u8> view=text.bytes();"
    rejects = {
        "copy": "std::Utf8Text copied=text;",
        "private-storage": "text.payload.set(0,65u8);",
        "mutable-view": view + "view.set(0,65u8);",
        "view-move": view + "std::Utf8Text moved=move(text);return view.size();",
        "view-append": view + "text.try_append_scalar(65u64);return view.size();",
        "self-initialize": view + "text.try_initialize(view);",
        "moved-access": "std::Utf8Text moved=move(text);return text.size();",
        "const-mutation": "const std::Utf8Text frozen=move(text);frozen.try_append_scalar(65u64);",
    }
    suite.reject(
        "escaping-view",
        IMPORTS
        + """
        auto escape(builtin::ByteRegion region,builtin::OwnedBytes allocation)->builtin::span<const u8>{
            std::Utf8Text text=std::Utf8Text(region,move(allocation));
            return text.bytes();
        }
    """,
    )
    for name, body in rejects.items():
        suite.reject(name, program(CREATE + body + "return 0;"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="aurora-utf8-text-") as directory:
        suite = Suite(
            args.compiler.resolve(strict=True), directory, ROOT / "library", entry_name="entry", deferred=True
        )
        cases(suite)
        suite.finish()
        print(f"PASS UTF-8 text: {suite.programs} programs, {suite.native} native cases, {suite.rejections} rejections")


if __name__ == "__main__":
    main()
