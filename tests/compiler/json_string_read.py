#!/usr/bin/env python3
"""Transactional JSON decoding with real owners and independent exact-byte oracles.

Reuse the existing hosted allocation adapter. Impractically large i64 overflow
branches are source-reviewed, not claimed as runtime-covered.
"""

import argparse
import json
from pathlib import Path
import shutil
import tempfile

from owned_bytes import ROOT, Suite

IMPORTS = """module json_read_test;
import std.json_read;
import std.byte_buffer;
import std.binary;
"""
CREATE = """builtin::OwnedBytes allocation=region.try_allocate(n);
std::ByteBuffer output=std::ByteBuffer(region,move(allocation));
"""


def program(body, helpers=""):
    return IMPORTS + helpers + "auto entry(builtin::ByteRegion region,i64 n,i64 flag)->i64 {\n" + body + "\n}"


def array(name, data):
    values = ",".join(f"{byte}u8" for byte in data) or "0u8"
    return f"const builtin::array<u8,{max(1, len(data))}> {name}={{{values}}};\n"


def cases(suite):
    samples = [
        b'"\\u0022"',
        b'""',
        b'"ASCII"',
        b'"\\u0000\\b\\f\\n\\r\\t\\/\\\\\\""',
        '"é€😀"'.encode(),
        b'"\\uD800\\uDC00\\uDBFF\\uDFFF"',
        b'"\\u007f\\u0080\\u07ff\\u0800\\ud7ff\\ue000\\uffff"',
    ]
    for index, raw in enumerate(samples):
        expected = b"P" + json.loads(raw).encode("utf-8")
        body = (
            CREATE
            + array("data", b"\xff" + raw + b"\xff")
            + array("expected", expected)
            + f"""
        output.try_append(80u8);
        const builtin::span<const u8> input=borrow_bytes(data);
        const std::JsonStringReadResult result=std::append_decoded_json_string(output,input,1,{len(raw)});
        if(result.status()!=std::JsonStringReadStatus::success ||
            result.appended_bytes()!={len(expected) - 1}){{return -1;}}
        if(output.size()!={len(expected)}){{return -2;}}
        const builtin::span<const u8> bytes=output.bytes();
        i64 i=0;
        while(i<bytes.size()){{if(bytes.at(i)!=expected[i]){{return -3;}}i=i+1;}}
        return 42;
        """
        )
        executable = suite.compile(f"exact-{index}", program(body))
        for capacity in (1, 128):
            grows = capacity < len(expected)
            suite.run(
                executable,
                512,
                capacity,
                0,
                42,
                2 if grows else 1,
                1,
                attempted_sizes=[32 + capacity] + ([32 + len(expected)] if grows else []),
            )

    invalid = [
        (bytes([34, 92, 34]), 1),
        (b"", 1),
        (b'"', 1),
        (b'"abc', 1),
        (b'"\\', 1),
        (b'"\\u12', 1),
        (b'"\\uD800', 1),
        (b'"abc"tail', 2),
        (b' "a"', 2),
        (b'"a" ', 2),
        (b'"a""b"', 2),
        (b'"\\x"', 2),
        (b'"\\uD800x"', 2),
        (b'"\\uDC00"', 2),
        (b'"AAA\xff"', 2),
        (b'"AAA\xe2\x82', 1),
        (b'"AAA\xe2\x82"', 2),
        (b'"\xc0\x80"', 2),
        (b'"\xed\xa0\x80"', 2),
        (b'"\xf4\x90\x80\x80"', 2),
    ]
    invalid += [(b'"' + bytes([byte]) + b'"', 2) for byte in range(32)]
    data = b"".join(raw for raw, _ in invalid)
    body = (
        CREATE.replace("try_allocate(n)", "try_allocate(1)")
        + array("data", data)
        + """
    output.try_append(80u8);
    const builtin::span<const u8> input=borrow_bytes(data);
    const std::JsonStringReadResult result=std::append_decoded_json_string(output,input,n,flag);
    if(result.appended_bytes()!=0 || output.size()!=1 || output.capacity()!=1){return -1;}
    const builtin::span<const u8> bytes=output.bytes();
    if(bytes.at(0)!=80u8){return -2;}
    if(result.status()==std::JsonStringReadStatus::truncated){return 1;}
    if(result.status()==std::JsonStringReadStatus::invalid_string){return 2;}
    if(result.status()==std::JsonStringReadStatus::invalid_window){return 3;}
    return -3;
    """
    )
    executable = suite.compile("invalid-before-allocation", program(body))
    offset = 0
    for raw, status in invalid:
        suite.run(executable, 512, offset, len(raw), status, 1, 1, attempted_sizes=[33])
        offset += len(raw)
    for offset, count in [(-1, 1), (0, -1), (len(data) + 1, 0), (len(data), 1), (0, 2**63 - 1), (2**63 - 1, 1)]:
        suite.run(executable, 512, offset, count, 3, 1, 1, attempted_sizes=[33])

    body = (
        CREATE
        + array("data", b'"AB"')
        + """
    output.try_append(80u8);
    const builtin::span<const u8> input=borrow_bytes(data);
    const std::JsonStringReadResult result=std::append_decoded_json_string(output,input,0,4);
    if(result.status()!=std::JsonStringReadStatus::append_failed || result.appended_bytes()!=0){return -1;}
    if(output.size()!=1 || output.capacity()!=1){return -2;}
    {const builtin::span<const u8> bytes=output.bytes();if(bytes.at(0)!=80u8){return -3;}}
    // Reuse the retained allocation after failure, without another allocation.
    output.clear();
    const std::JsonStringReadResult empty=std::append_decoded_json_string(output,input,1,0);
    if(empty.status()!=std::JsonStringReadStatus::truncated){return -4;}
    const builtin::array<u8,3> small={34u8,90u8,34u8};
    const builtin::span<const u8> retry=borrow_bytes(small);
    const std::JsonStringReadResult retried=std::append_decoded_json_string(output,retry,0,3);
    if(retried.status()!=std::JsonStringReadStatus::success){return -5;}
    const builtin::span<const u8> bytes=output.bytes();
    if(bytes.size()!=1 || bytes.at(0)!=90u8 || output.capacity()!=1){return -6;}
    return 42;
    """
    )
    executable = suite.compile("allocation-failure-retry", program(body))
    suite.run(executable, 1, 1, 0, 42, 1, 1, attempted_sizes=[33])
    suite.run(executable, 512, 1, 0, 42, 1, 1, fail_after=1, attempted_sizes=[33, 35])

    body = (
        CREATE
        + array("data", b'""')
        + """
    const builtin::span<const u8> input=borrow_bytes(data);
    const std::JsonStringReadResult result=std::append_decoded_json_string(output,input,0,2);
    if(output.size()!=0 || output.capacity()!=0 || result.appended_bytes()!=0){return -1;}
    if(output.ok() && result.status()==std::JsonStringReadStatus::success){return 42;}
    if(!output.ok() && result.status()==std::JsonStringReadStatus::append_failed){return 41;}
    return -2;
    """
    )
    executable = suite.compile("empty-and-inert", program(body))
    suite.run(executable, 0, 0, 0, 42, 1, 1)
    suite.run(executable, 0, 1, 0, 41, 0, 0)
    suite.run(executable, 512, 0, 0, 41, 0, 0, fail_after=0)

    body = """
    const std::JsonStringReadResult negative=std::JsonStringReadResult(std::JsonStringReadStatus::success,-1);
    const std::JsonStringReadResult failed=std::JsonStringReadResult(std::JsonStringReadStatus::append_failed,123);
    if(negative.status()!=std::JsonStringReadStatus::invalid_window || negative.appended_bytes()!=0){return -1;}
    if(failed.appended_bytes()!=0){return -2;}
    return 42;
    """
    executable = suite.compile("copied-reports", program(body))
    suite.run(executable, 0, 0, 0, 42, 0, 0)

    view = "const builtin::span<const u8> input=output.bytes();"
    for name, body in {
        "self-direct": "std::append_decoded_json_string(output,output.bytes(),0,0);",
        "self-named": view + "std::append_decoded_json_string(output,input,0,0);",
        "self-subspan": view
        + "const builtin::span<const u8> empty=input.subspan(0,0);std::append_decoded_json_string(output,empty,0,0);",
        "const-output": "const std::ByteBuffer frozen=move(output);"
        "const builtin::array<u8,2> data={34u8,34u8};"
        "const builtin::span<const u8> input=borrow_bytes(data);"
        "std::append_decoded_json_string(frozen,input,0,2);",
        "live-view": view + "const builtin::array<u8,2> data={34u8,34u8};"
        "const builtin::span<const u8> other=borrow_bytes(data);"
        "std::append_decoded_json_string(output,other,0,2);return input.size();",
        "private-report": "std::JsonStringReadResult result=std::JsonStringReadResult("
        "std::JsonStringReadStatus::success,0);"
        "return result.count;",
    }.items():
        suite.reject(name, program(CREATE + body + "return 0;"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    args = parser.parse_args()
    directory = Path(tempfile.mkdtemp(prefix="aurora-json-string-read-"))
    print(f"Artifacts: {directory}", flush=True)
    suite = Suite(args.compiler.resolve(), directory, ROOT / "library", entry_name="entry")
    cases(suite)
    print(
        f"PASS JSON string read: {suite.programs} programs, {suite.native} native cases, {suite.rejections} rejections"
    )
    shutil.rmtree(directory)


if __name__ == "__main__":
    main()
