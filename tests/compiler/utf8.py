#!/usr/bin/env python3
"""Bounded ordinary native checks for the pure-library std.utf8 contract.

The format reference is Unicode 17.0.0, section 3.9, Table 3-7:
https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-3/
The mathematical oracle uses shortest-length integer encodings and possible
scalar intervals, independently crosschecked against Python's strict decoder.
Its acceptance depends on scalar validity, never assignment or Unicode age.

Runtime loops cover all 1,112,064 Unicode scalar values, all 256 one-byte and
65,536 two-byte inputs, and a bounded Cartesian set of longer boundary classes.
This is finite native execution evidence, not a safety or performance proof.
No compiler, IR, kernel, signal-injection, or million-line fixture is required.
Source, assembly, executables, hashes, and receipts remain in --artifacts even
after failure. Limits are enforced with require(), including under Python -O.
Children have CPU soft/hard limits of 10/11 seconds, an 8 MiB regular-file limit,
and no core dumps. The compiler has 512 MiB address space; native/tools 128 MiB.
Only --sanitized-compiler omits compiler address limits for ASan shadow memory.
Compiler/tools have a 30-second wall limit; native execution defaults to 15.
Fixtures contain at most 12 checks and 64 KiB of generated source.

Run: python3 tests/compiler/utf8.py /path/to/aurorac
Harness control: python3 -O tests/compiler/utf8.py --self-test-only
"""

from __future__ import annotations

import argparse
import codecs
from dataclasses import asdict, dataclass, replace
import hashlib
import itertools
import json
import resource
import subprocess
from pathlib import Path
import signal
import sys
import tempfile
import time

from unsigned_oracle import Case, Observation, require, validate_values


ROOT = Path(__file__).resolve().parents[2]
MAX_U64 = (1 << 64) - 1
MIN_I64 = -(1 << 63)
MAX_I64 = (1 << 63) - 1
PASS = 0xA55A1234FFFF00AA
SCALARS = 0x110000 - 0x800
MAX_SOURCE_BYTES = 65536
MAX_BATCH = 12
STATUS = "std::Utf8Status::"
SPAN = "builtin::span<const u8>"
BOUNDARIES = (0, 0x7F, 0x80, 0x8F, 0x90, 0x9F, 0xA0, 0xBF, 0xC0, 0xFF)
LEADS = (
    0,
    0x7F,
    0x80,
    0xBF,
    0xC0,
    0xC1,
    0xC2,
    0xDF,
    0xE0,
    0xE1,
    0xEC,
    0xED,
    0xEE,
    0xEF,
    0xF0,
    0xF1,
    0xF3,
    0xF4,
    0xF5,
    0xF7,
    0xF8,
    0xFF,
)


@dataclass(frozen=True)
class Decode:
    status: str
    scalar: int = 0
    width: int = 0


@dataclass(frozen=True)
class Validation:
    status: str
    prefix_bytes: int = 0
    scalar_count: int = 0


def scalar(value):
    return 0 <= value <= 0x10FFFF and not 0xD800 <= value <= 0xDFFF


def encode(value):
    """Shortest positional-base encoding, independent of a decoder table."""
    require(scalar(value), "encoding model needs a Unicode scalar")
    if value < 128:
        return bytes((value,))
    width = next(width for width, limit in ((2, 2048), (3, 65536), (4, 0x110000)) if value < limit)
    parts = []
    number = value
    for _ in range(width - 1):
        parts.append(128 + number % 64)
        number //= 64
    return bytes((256 - 2 ** (8 - width) + number, *reversed(parts)))


def decode(data, offset, count, final):
    """A prefix is viable iff its possible integer interval contains a scalar."""
    if offset < 0 or count < 0 or offset > len(data) or count > len(data) - offset:
        return Decode("out_of_range")
    if count == 0:
        return Decode("end_of_input")
    first = data[offset]
    if first < 128:
        return Decode("success", first, 1)
    width = next((n for n in (2, 3, 4) if 256 - 2 ** (8 - n) <= first < 256 - 2 ** (7 - n)), None)
    if width is None:
        return Decode("invalid_sequence")
    value = first - (256 - 2 ** (8 - width))
    minimum = (128, 2048, 65536)[width - 2]
    for used in range(1, width + 1):
        remaining = 64 ** (width - used)
        low, high = max(minimum, value * remaining), min(0x10FFFF, (value + 1) * remaining - 1)
        if low > high or 0xD800 <= low <= high <= 0xDFFF:
            return Decode("invalid_sequence")
        if used == width:
            return Decode("success", value, width)
        if used == count:
            return Decode("truncated" if final else "need_more")
        byte = data[offset + used]
        if not 128 <= byte < 192:
            return Decode("invalid_sequence")
        value = value * 64 + byte - 128
    raise AssertionError("unreachable mathematical decoder state")


def validate(data, offset, count, final):
    if offset < 0 or count < 0 or offset > len(data) or count > len(data) - offset:
        return Validation("out_of_range")
    used = total = 0
    while used < count:
        result = decode(data, offset + used, count - used, final)
        if result.status != "success":
            return Validation(result.status, used, total)
        used += result.width
        total += 1
    return Validation("success", used, total)


def python_validation(data, final):
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    try:
        text = decoder.decode(bytes(data), final)
    except UnicodeDecodeError as error:
        prefix = bytes(data[: error.start])
        status = "truncated" if error.reason == "unexpected end of data" else "invalid_sequence"
        return Validation(status, error.start, len(prefix.decode("utf-8", "strict")))
    pending, state = decoder.getstate()
    require(state == 0, "unexpected Python UTF-8 decoder state")
    if pending:
        # CPython's incremental decoder defers some known-invalid surrogate
        # prefixes (ED A0..BF) until the next feed. A strict final check of its
        # pending tail distinguishes that delay from a viable incomplete scalar.
        try:
            pending.decode("utf-8", "strict")
        except UnicodeDecodeError as error:
            if error.reason != "unexpected end of data":
                return Validation("invalid_sequence", len(data) - len(pending), len(text))
    return Validation("need_more" if pending else "success", len(data) - len(pending), len(text))


def crosscheck(data):
    for final in (False, True):
        modeled = validate(data, 0, len(data), final)
        expected = python_validation(data, final)
        require(
            modeled == expected, f"Python strict crosscheck {bytes(data).hex()} final={final}: {modeled} != {expected}"
        )


def must_fail(action, label):
    try:
        action()
    except AssertionError:
        return
    raise AssertionError("harness accepted " + label)


def self_tests():
    for value, encoded in (
        (0, b"\0"),
        (127, b"\x7f"),
        (128, b"\xc2\x80"),
        (2047, b"\xdf\xbf"),
        (2048, b"\xe0\xa0\x80"),
        (0xD7FF, b"\xed\x9f\xbf"),
        (0xE000, b"\xee\x80\x80"),
        (0x10000, b"\xf0\x90\x80\x80"),
        (0x10FFFF, b"\xf4\x8f\xbf\xbf"),
    ):
        require(encode(value) == encoded, "mathematical encoder anchor")
        require(
            decode(encoded, 0, len(encoded), True) == Decode("success", value, len(encoded)),
            "mathematical decoder anchor",
        )
    anchors = (
        (b"\xc0", "invalid_sequence"),
        (b"\xc2", "truncated"),
        (b"\xe0\x80", "invalid_sequence"),
        (b"\xed\xa0", "invalid_sequence"),
        (b"\xf0\x80", "invalid_sequence"),
        (b"\xf4\x90", "invalid_sequence"),
        (b"\xf5", "invalid_sequence"),
        (b"\xf0\x90\x80", "truncated"),
        (b"\xe1A", "invalid_sequence"),
        (b"\xf1\x80A", "invalid_sequence"),
    )
    for data, status in anchors:
        require(decode(data, 0, len(data), True) == Decode(status), "decoder status anchor")
        crosscheck(data)
    require(decode(b"\xff", 1, 0, True) == Decode("end_of_input"), "empty decode")
    require(validate(b"\xff", 1, 0, False) == Validation("success"), "empty validation")
    require(validate(b"A\xc2\xa2\xe1A", 0, 5, False) == Validation("invalid_sequence", 3, 2), "prefix anchor")
    for offset, count in ((MIN_I64, 0), (0, MIN_I64), (-1, -1), (2, 0), (1, MAX_I64), (MAX_I64, MAX_I64)):
        require(decode(b"\xff", offset, count, False) == Decode("out_of_range"), "range first")
        require(validate(b"\xff", offset, count, False) == Validation("out_of_range"), "range first")
    good = Observation(PASS.to_bytes(8, "little"), exit_code=0)
    case = Case("all result bits", "", PASS)
    validate_values(good, [case])
    for bad in (
        replace(good, output=good.output[:1]),
        replace(good, output=good.output + b"x"),
        replace(good, exit_code=1),
        replace(good, terminal_signal=signal.SIGILL),
        replace(good, output=(PASS ^ (1 << 40)).to_bytes(8, "little")),
    ):
        must_fail(lambda bad=bad: validate_values(bad, [case]), "bad native observation")
    must_fail(lambda: require(False, "deliberate assertion"), "disabled require")
    print("PASS UTF-8 harness controls (active under Python -O)", flush=True)


def python_exhaustive():
    count = 0
    for value in range(0x110000):
        if scalar(value):
            data = encode(value)
            require(data == chr(value).encode("utf-8", "strict"), "scalar encoder crosscheck")
            require(data.decode("utf-8", "strict") == chr(value), "scalar strict decoder crosscheck")
            count += 1
    require(count == SCALARS, "wrong scalar enumeration count")
    for first in range(256):
        crosscheck(bytes((first,)))
        for second in range(256):
            crosscheck(bytes((first, second)))
    longer = 0
    for width in (3, 4):
        for lead in LEADS:
            for tail in itertools.product(BOUNDARIES, repeat=width - 1):
                crosscheck(bytes((lead, *tail)))
                longer += 1
    print(
        f"PASS Python strict crosscheck: {count} scalars, 256 one-byte, 65536 two-byte, "
        f"{longer} longer boundary inputs",
        flush=True,
    )
    return longer


# Native mathematical model: possible integer intervals intersect shortest-form
# scalar values. This deliberately does not copy Unicode lead/second-byte tables.
MODEL = r"""
auto model_decode(builtin::span<const u8> bytes,i64 count,bool final_input)->std::Utf8DecodeResult{
    if(count==0){const std::Utf8DecodeResult r=std::Utf8DecodeResult(std::Utf8Status::end_of_input,0u64,0);return r;}
    const u64 first=u64(bytes.at(0));
    if(first<128u64){const std::Utf8DecodeResult r=std::Utf8DecodeResult(std::Utf8Status::success,first,1);return r;}
    i64 width=0;u64 value=0u64;u64 minimum=0u64;
    if(both(first>=192u64,first<224u64)){width=2;value=first-192u64;minimum=128u64;}
    if(both(first>=224u64,first<240u64)){width=3;value=first-224u64;minimum=2048u64;}
    if(both(first>=240u64,first<248u64)){width=4;value=first-240u64;minimum=65536u64;}
    if(width==0){const std::Utf8DecodeResult r=std::Utf8DecodeResult(std::Utf8Status::invalid_sequence,0u64,0);return r;}
    i64 used=1;
    while(used<=width){
        u64 scale=1u64;i64 remaining=used;
        while(remaining<width){scale=scale*64u64;remaining=remaining+1;}
        u64 low=value*scale;u64 high=(value+1u64)*scale-1u64;
        if(low<minimum){low=minimum;}if(high>1114111u64){high=1114111u64;}
        if(either(low>high,both(low>=55296u64,high<=57343u64))){
            const std::Utf8DecodeResult r=std::Utf8DecodeResult(std::Utf8Status::invalid_sequence,0u64,0);return r;
        }
        if(used==width){const std::Utf8DecodeResult r=std::Utf8DecodeResult(std::Utf8Status::success,value,width);return r;}
        if(used==count){
            if(final_input){const std::Utf8DecodeResult r=std::Utf8DecodeResult(std::Utf8Status::truncated,0u64,0);return r;}
            const std::Utf8DecodeResult r=std::Utf8DecodeResult(std::Utf8Status::need_more,0u64,0);return r;
        }
        const u64 next=u64(bytes.at(used));
        if(either(next<128u64,next>=192u64)){const std::Utf8DecodeResult r=std::Utf8DecodeResult(std::Utf8Status::invalid_sequence,0u64,0);return r;}
        value=value*64u64+next-128u64;used=used+1;
    }
    const std::Utf8DecodeResult impossible=std::Utf8DecodeResult(std::Utf8Status::out_of_range,0u64,0);return impossible;
}
auto model_check(builtin::span<const u8> bytes,i64 count,bool final_input)->u64{
    const std::Utf8DecodeResult expected=model_decode(bytes,count,final_input);
    const std::Utf8DecodeResult actual=std::decode_utf8(bytes,0,count,final_input);
    if(actual.status()!=expected.status()){return 1u64;}
    if(actual.width()!=expected.width()){return 2u64;}
    if(actual.scalar_or(18446744073709551615u64)!=expected.scalar_or(18446744073709551615u64)){return 3u64;}
    const std::Utf8ValidationResult validation=std::validate_utf8(bytes,0,count,final_input);
    i64 prefix=0;i64 scalars=0;
    std::Utf8Status outcome=std::Utf8Status::success;
    bool stopped=false;
    while(both(prefix<count,!stopped)){
        builtin::array<u8,4> tail={0u8,0u8,0u8,0u8};i64 j=0;
        while(j<count-prefix){tail[j]=bytes.at(prefix+j);j=j+1;}
        const std::Utf8DecodeResult part=model_decode(borrow_bytes(tail),count-prefix,final_input);
        if(part.status()!=std::Utf8Status::success){outcome=part.status();stopped=true;}
        else{prefix=prefix+part.width();scalars=scalars+1;}
    }
    if(validation.status()!=outcome){return 4u64;}
    if(validation.prefix_bytes()!=prefix){return 5u64;}
    if(validation.scalar_count()!=scalars){return 6u64;}
    return 0u64;
}
"""  # noqa: E501 - Preserve exact embedded Aurora source bytes.


def array(name, data, const=False):
    require(1 <= len(data) <= 4096, "fixture array must contain 1..4096 bytes")
    return (
        f"{'const ' if const else ''}builtin::array<u8,{len(data)}> {name}={{" + ",".join(f"{b}u8" for b in data) + "};"
    )


def check_result(name, data, offset, count, final):
    expected = decode(data, offset, count, final)
    validation = validate(data, offset, count, final)
    flag = "true" if final else "false"
    body = array("bytes", data, const=True)
    body += f"const {SPAN} view=borrow_bytes(bytes);"
    body += f"const std::Utf8DecodeResult d=std::decode_utf8(view,{offset},{count},{flag});"
    body += f"if(d.status()!={STATUS}{expected.status}){{return 1u64;}}"
    body += f"if(d.width()!={expected.width}){{return 2u64;}}"
    payload = expected.scalar if expected.status == "success" else MAX_U64
    body += f"if(d.scalar_or({MAX_U64}u64)!={payload}u64){{return 3u64;}}"
    body += f"const std::Utf8ValidationResult v=std::validate_utf8(view,{offset},{count},{flag});"
    body += f"if(v.status()!={STATUS}{validation.status}){{return 4u64;}}"
    body += f"if(v.prefix_bytes()!={validation.prefix_bytes}){{return 5u64;}}"
    body += f"if(v.scalar_count()!={validation.scalar_count}){{return 6u64;}}"
    body += f"return {PASS}u64;"
    return Case(name, body, PASS)


def scalar_loop():
    return Case(
        "all 1112064 Unicode scalars in native runtime loop",
        r"""
        builtin::array<u8,4> bytes={255u8,255u8,255u8,255u8};
        u64 value=0u64;u64 visited=0u64;
        while(value<1114112u64){
            if(either(value<55296u64,value>57343u64)){
                i64 width=1;
                if(value>=128u64){width=2;}if(value>=2048u64){width=3;}if(value>=65536u64){width=4;}
                u64 remaining=value;i64 position=width-1;
                while(position>0){bytes[position]=u8(128u64+remaining%64u64);remaining=remaining/64u64;position=position-1;}
                u64 leading=0u64;
                if(width==2){leading=192u64;}if(width==3){leading=224u64;}if(width==4){leading=240u64;}
                bytes[0]=u8(leading+remaining);
                {
                    const builtin::span<const u8> view=borrow_bytes(bytes);
                    const std::Utf8DecodeResult d=std::decode_utf8(view,0,width,true);
                    if(d.status()!=std::Utf8Status::success){return value*32u64+1u64;}
                    if(d.scalar_or(18446744073709551615u64)!=value){return value*32u64+2u64;}
                    if(d.width()!=width){return value*32u64+3u64;}
                    const std::Utf8DecodeResult chunk=std::decode_utf8(view,0,width,false);
                    if(chunk.status()!=std::Utf8Status::success){return value*32u64+4u64;}
                    if(chunk.scalar_or(18446744073709551615u64)!=value){return value*32u64+5u64;}
                    if(chunk.width()!=width){return value*32u64+6u64;}
                    const std::Utf8ValidationResult v=std::validate_utf8(view,0,width,true);
                    if(v.status()!=std::Utf8Status::success){return value*32u64+7u64;}
                    if(v.prefix_bytes()!=width){return value*32u64+8u64;}
                    if(v.scalar_count()!=1){return value*32u64+9u64;}
                    const std::Utf8ValidationResult c=std::validate_utf8(view,0,width,false);
                    if(c.status()!=std::Utf8Status::success){return value*32u64+10u64;}
                    if(either(c.prefix_bytes()!=width,c.scalar_count()!=1)){return value*32u64+11u64;}
                }
                visited=visited+1u64;
            }
            value=value+1u64;
        }
        return 11914855783004569770u64+visited;
    """,  # noqa: E501 - Preserve exact embedded Aurora source bytes.
        PASS + SCALARS,
    )


def short_loop(width):
    limit = 256**width
    assignments = "bytes[0]=u8(number);" if width == 1 else "bytes[0]=u8(number/256);bytes[1]=u8(number%256);"
    return Case(
        f"all {limit} inputs of length {width}, final and chunk",
        f"""
        {array("bytes", bytes(width))}i64 number=0;u64 visited=0u64;
        while(number<{limit}){{
            {assignments}
            {{const {SPAN} view=borrow_bytes(bytes);
                const u64 final_failure=model_check(view,{width},true);
                if(final_failure!=0u64){{return u64(number)*32u64+final_failure;}}
                const u64 chunk_failure=model_check(view,{width},false);
                if(chunk_failure!=0u64){{return u64(number)*32u64+16u64+chunk_failure;}}
            }}
            visited=visited+1u64;number=number+1;
        }}
        return {PASS}u64+visited;
    """,
        PASS + limit,
        prelude=MODEL,
    )


def boundary_loop(width):
    count = len(LEADS) * len(BOUNDARIES) ** (width - 1)
    radix = len(BOUNDARIES)
    tail = "i64 encoded=number; i64 position=" + str(width - 1) + ";"
    tail += (
        f"while(position>0){{bytes[position]=boundary[encoded%{radix}];encoded=encoded/{radix};position=position-1;}}"
    )
    return Case(
        f"{count} length-{width} boundary-class inputs, final and chunk",
        f"""
        {array("leads", LEADS, const=True)}{array("boundary", BOUNDARIES, const=True)}
        {array("bytes", bytes(width))}
        i64 lead=0;u64 visited=0u64;
        while(lead<{len(LEADS)}){{
            i64 number=0;
            while(number<{radix ** (width - 1)}){{
                bytes[0]=leads[lead];{tail}
                {{const {SPAN} view=borrow_bytes(bytes);
                    const u64 f=model_check(view,{width},true);
                    if(f!=0u64){{return visited*32u64+f;}}
                    const u64 c=model_check(view,{width},false);
                    if(c!=0u64){{return visited*32u64+16u64+c;}}
                }}
                visited=visited+1u64;number=number+1;
            }}
            lead=lead+1;
        }}
        return {PASS}u64+visited;
    """,
        PASS + count,
        prelude=MODEL,
    )


def ordinary_cases():
    # Complete scalar boundaries, NUL, BOM, noncharacters and unassigned scalars.
    values = (
        0,
        1,
        0x7F,
        0x80,
        0x7FF,
        0x800,
        0xD7FF,
        0xE000,
        0xFFFF,
        0x10000,
        0x10FFFF,
        0xFEFF,
        0xFFFD,
        0xFDD0,
        0xFDEF,
        0x1FFFE,
        0x0378,
    )
    for value in values:
        raw = encode(value)
        owner = b"\xff" + raw + b"\xff"
        for final in (False, True):
            for cut in range(len(raw) + 1):
                yield check_result(f"scalar U+{value:04X} window prefix {cut}, final={final}", owner, 1, cut, final)
    # Range rejection must precede decoding and avoid signed addition overflow.
    data = b"\xff\xc2\xa2\xff"
    for offset, count in itertools.product((MIN_I64, -1, 0, 1, 3, 4, 5, MAX_I64), (MIN_I64, -1, 0, 1, 2, 4, MAX_I64)):
        for final in (False, True):
            yield check_result(f"range offset={offset} count={count} final={final}", data, offset, count, final)
    # All complete leading bytes/scalars are counted, failing scalar is untouched.
    prefix = encode(0) + encode(0xFEFF) + encode(0x1F642) + b"A"
    endings = (
        b"",
        b"\x80",
        b"\xc0",
        b"\xc1\xbf",
        b"\xc2",
        b"\xe0\x9f",
        b"\xed\xa0",
        b"\xed\xbf\xbf",
        b"\xf0\x8f",
        b"\xf4\x90",
        b"\xf5",
        b"\xff",
        b"\xe1A",
        b"\xf1\x80A",
        b"\xe1\x80",
        b"\xf1\x80",
        b"\xf1\x80\x80",
        b"\xf4\x8f\xbf",
        b"\xffA",
    )
    for ending in endings:
        for final in (False, True):
            data = b"\xff" + prefix + ending + b"\x00"
            yield check_result(
                f"validated prefix before {ending.hex()} final={final}", data, 1, len(prefix) + len(ending), final
            )
    # Public reports contain ordinary, forgeable data; scalar fallback remains safe.
    for status in ("success", "end_of_input", "out_of_range", "invalid_sequence", "truncated", "need_more"):
        for value in (0, 0xD7FF, 0xD800, 0xDFFF, 0xE000, 0x10FFFF, 0x110000, MAX_U64):
            expected = value if status == "success" and scalar(value) else MAX_U64 - 1
            yield Case(
                f"public {status} report scalar {value}",
                f"const std::Utf8DecodeResult report=std::Utf8DecodeResult({STATUS}{status},{value}u64,0);"
                f"return report.scalar_or({MAX_U64 - 1}u64);",
                expected,
            )
        for width in (MIN_I64, -1, 0, 1, 4, MAX_I64):
            expected_width = width if status == "success" else 0
            yield Case(
                f"public {status} report width {width} is ordinary data",
                f"const std::Utf8DecodeResult report=std::Utf8DecodeResult({STATUS}{status},65u64,{width});"
                "return report.width();",
                expected_width,
                result_type="i64",
            )
    yield Case(
        "decode report copies and input owner stay independent",
        f"""
        builtin::array<u8,4> bytes={{240u8,159u8,153u8,130u8}};
        const std::Utf8DecodeResult saved=std::decode_utf8(borrow_bytes(bytes),0,4,true);
        {{const {SPAN} view=borrow_bytes(bytes);
          const std::Utf8DecodeResult original=saved;
          if(original.scalar_or(0u64)!=128578u64){{return 1u64;}}
          const std::Utf8ValidationResult valid=std::validate_utf8(view,0,4,true);
          if(either(valid.prefix_bytes()!=4,valid.scalar_count()!=1)){{return 1u64;}}
          if(either(either(view.at(0)!=240u8,view.at(1)!=159u8),either(view.at(2)!=153u8,view.at(3)!=130u8))){{return 2u64;}}
        }}
        bytes[0]=65u8;bytes[1]=0u8;bytes[2]=0u8;bytes[3]=0u8;
        const std::Utf8DecodeResult copy=saved;
        if(either(copy.status()!=std::Utf8Status::success,copy.width()!=4)){{return 3u64;}}
        return copy.scalar_or(0u64);
    """,  # noqa: E501 - Preserve exact embedded Aurora source bytes.
        0x1F642,
    )
    yield Case(
        "validation reports are independent ordinary signed-count values",
        f"""
        const std::Utf8ValidationResult original=std::Utf8ValidationResult(std::Utf8Status::success,{MIN_I64},{MAX_I64});
        const std::Utf8ValidationResult copy=original;
        if(copy.status()!=std::Utf8Status::success){{return 1u64;}}
        if(either(copy.prefix_bytes()!={MIN_I64},copy.scalar_count()!={MAX_I64})){{return 2u64;}}
        return {PASS}u64;
    """,  # noqa: E501 - Preserve exact embedded Aurora source bytes.
        PASS,
    )
    data = b"A" * 4092 + encode(0x10FFFF)
    yield check_result("full maximum-capacity 4096-byte span", data, 0, len(data), True)
    yield check_result("four-byte scalar at maximum-capacity span tail", data, 4092, 4, False)


def replay_cases():
    # A fixed four-byte pending owner holds at most three bytes after a feed;
    # each arriving byte is appended only after the previous borrow has ended.
    examples = ((0, 0x7F, 0x80, 0x800, 0x10000, 0x10FFFF, 0xFEFF, 0xFDD0), (0x1F642, 65, 0xD7FF, 0xE000, 0x0378, 0))
    for values in examples:
        data = b"".join(encode(value) for value in values)
        # Every split is replayed from the unconsumed suffix. Separate fixtures
        # give exact split and expected prefix information on failure.
        for split in range(len(data) + 1):
            first = validate(data, 0, split, False)
            remaining = split - first.prefix_bytes
            require(remaining <= 3, "chunk carry exceeded three bytes")
            body = array("bytes", data, const=True)
            body += f"const {SPAN} view=borrow_bytes(bytes);"
            body += f"const std::Utf8ValidationResult first=std::validate_utf8(view,0,{split},false);"
            body += f"if(first.status()!={STATUS}{first.status}){{return 1u64;}}"
            body += (
                f"if(either(first.prefix_bytes()!={first.prefix_bytes},first.sca"
                f"lar_count()!={first.scalar_count})){{return 2u64;}}"
            )
            body += f"if({split}-first.prefix_bytes()>3){{return 3u64;}}"
            body += (
                f"const std::Utf8ValidationResult last=std::validate_utf8(view,f"
                f"irst.prefix_bytes(),{len(data)}-first.prefix_bytes(),true);"
            )
            body += "if(last.status()!=std::Utf8Status::success){return 4u64;}"
            body += f"if(last.prefix_bytes()+first.prefix_bytes()!={len(data)}){{return 5u64;}}"
            body += f"if(last.scalar_count()+first.scalar_count()!={len(values)}){{return 6u64;}}"
            body += f"return {PASS}u64;"
            yield Case(f"stateless two-chunk replay {data.hex()} split={split}", body, PASS)
        body = array("stream", data, const=True)
        body += "builtin::array<u8,4> pending={0u8,0u8,0u8,0u8};i64 used=0;i64 input=0;i64 count=0;i64 committed=0;"
        body += f"while(input<{len(data)}){{pending[used]=stream[input];used=used+1;input=input+1;"
        body += "{const builtin::span<const u8> view=borrow_bytes(pending);"
        body += "const std::Utf8DecodeResult result=std::decode_utf8(view,0,used,false);"
        body += "if(result.status()==std::Utf8Status::success){"
        body += "if(result.width()!=used){return 1u64;}"
        for index, value in enumerate(values):
            body += f"if(both(count=={index},result.scalar_or({MAX_U64}u64)!={value}u64)){{return 2u64;}}"
        body += "count=count+1;committed=committed+used;used=0;"
        body += "}else{if(either(result.status()!=std::Utf8Status::need_more,result.width()!=0)){return 3u64;}}}"
        body += "if(used>3){return 4u64;}}"
        body += (
            f"if(either(either(used!=0,committed!={len(data)}),count!={len(values)})){{return 5u64;}}return {PASS}u64;"
        )
        yield Case(f"one-byte chunk replay with at most three retained bytes {data.hex()}", body, PASS)


class Suite:
    def __init__(self, compiler, directory, timeout, sanitized_compiler):
        self.compiler = compiler
        self.directory = directory
        self.timeout = timeout
        self.sanitized_compiler = sanitized_compiler
        self.count = 0
        self.batches = 0
        self.receipts = []

    def command(self, args, directory, name, compiler=False, native=False):
        address_limit = None if compiler and self.sanitized_compiler else (512 if compiler else 128) << 20

        def limits():
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            resource.setrlimit(resource.RLIMIT_CPU, (10, 11))
            resource.setrlimit(resource.RLIMIT_FSIZE, (8 << 20, 8 << 20))
            if address_limit is not None:
                resource.setrlimit(resource.RLIMIT_AS, (address_limit, address_limit))

        receipt = {
            "command": [str(arg) for arg in args],
            "cpu_soft_seconds": 10,
            "cpu_hard_seconds": 11,
            "address_space_bytes": address_limit,
            "file_size_bytes": 8 << 20,
            "wall_seconds": self.timeout if native else 30,
        }
        try:
            with (
                (directory / f"{name}.stdout").open("wb") as stdout,
                (directory / f"{name}.stderr").open("wb") as stderr,
            ):
                result = subprocess.run(
                    [str(arg) for arg in args],
                    stdout=stdout,
                    stderr=stderr,
                    timeout=receipt["wall_seconds"],
                    preexec_fn=limits,
                )
            receipt["returncode"] = result.returncode
            require(
                result.returncode == 0,
                f"{name}: expected exit 0, got {result.returncode}: "
                + (directory / f"{name}.stderr").read_bytes()[:4096].decode(errors="replace"),
            )
            require(
                (directory / f"{name}.stderr").stat().st_size == 0, f"{name}: unexpected stderr; see retained artifact"
            )
            return (directory / f"{name}.stdout").read_bytes()
        except subprocess.TimeoutExpired as error:
            receipt["timeout"] = True
            raise AssertionError(f"{name}: wall timeout is a failure") from error
        finally:
            (directory / f"{name}.command.json").write_text(json.dumps(receipt, indent=2) + "\n")

    def execute(self, directory, functions):
        instructions = [".text", ".globl _start", "_start:"]
        for function in functions:
            instructions.extend(
                [
                    f"call {function}",
                    "pushq %rax",
                    "movq $1,%rax",
                    "movq $1,%rdi",
                    "movq %rsp,%rsi",
                    "movq $8,%rdx",
                    "syscall",
                    "addq $8,%rsp",
                ]
            )
        instructions.extend(["movq $60,%rax", "xorq %rdi,%rdi", "syscall", '.section .note.GNU-stack,"",@progbits'])
        (directory / "entry.s").write_text("\n".join(instructions) + "\n")
        self.command(["as", "--64", directory / "compiled.s", "-o", directory / "program.o"], directory, "assemble")
        self.command(["as", "--64", directory / "entry.s", "-o", directory / "entry.o"], directory, "entry")
        self.command(
            ["ld", "-o", directory / "program", directory / "entry.o", directory / "program.o"], directory, "link"
        )
        output = self.command([directory / "program"], directory, "native", native=True)
        return Observation(output, exit_code=0)

    def check(self, cases):
        require(1 <= len(cases) <= MAX_BATCH, "native batch size limit")
        require(len(cases) == 1 or all(not item.prelude for item in cases), "prelude isolation")
        functions = [f"utf8_case_{index}" for index in range(len(cases))]
        source = (
            "module utf8_test;import std.utf8;\n"
            "auto both(bool a,bool b)->bool{if(a){return b;}return false;}\n"
            "auto either(bool a,bool b)->bool{if(a){return true;}return b;}\n"
        )
        for function, case in zip(functions, cases):
            source += case.prelude + f"\nauto {function}()->{case.result_type}{{{case.body}}}\n"
        require(len(source.encode()) <= MAX_SOURCE_BYTES, "generated source byte limit")
        directory = self.directory / f"batch-{self.batches:04d}"
        directory.mkdir()
        self.batches += 1
        path, output = directory / "input.au", directory / "compiled.s"
        path.write_text(source)
        receipt = {
            "cases": [case.name for case in cases],
            "source_bytes": len(source.encode()),
            "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "status": "running",
        }
        started = time.monotonic()
        try:
            self.command(
                [self.compiler, "--module-root", ROOT / "library", path, "-o", output],
                directory,
                "compiler",
                compiler=True,
            )
            require(output.is_file(), "successful compiler did not create assembly")
            require(path.read_text() == source, "compiler modified its source")
            observed = self.execute(directory, functions)
            receipt["observation"] = {k: v for k, v in asdict(observed).items() if k != "output"}
            validate_values(observed, cases)
            receipt["status"] = "passed"
            self.count += len(cases)
            print(f"PASS native UTF-8 batch {self.batches}: {len(cases)} checks; {cases[0].name}", flush=True)
        except Exception as error:
            receipt["status"] = "failed"
            receipt["error"] = str(error)
            raise AssertionError(f"UTF-8 failure; retained artifacts: {directory}\n{error}") from error
        finally:
            receipt["seconds"] = round(time.monotonic() - started, 6)
            (directory / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
            self.receipts.append(receipt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", nargs="?", type=Path)
    parser.add_argument("--self-test-only", action="store_true")
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--timeout", type=int, default=15, help="native wall timeout; CPU stays capped at 10/11s")
    parser.add_argument(
        "--sanitized-compiler", action="store_true", help="omit only compiler RLIMIT_AS for sanitizer shadow memory"
    )
    args = parser.parse_args()
    require(5 <= args.timeout <= 90, "native wall timeout must be between 5 and 90 seconds")
    self_tests()
    if args.self_test_only:
        return
    require(args.compiler is not None, "compiler argument required for native execution")
    compiler = args.compiler.resolve()
    library = ROOT / "library/std/utf8.au"
    identities = {
        "compiler_sha256": hashlib.sha256(compiler.read_bytes()).hexdigest(),
        "utf8_sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
        "test_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    if args.artifacts:
        directory = args.artifacts.resolve()
        directory.mkdir(parents=True, exist_ok=False)
    else:
        (ROOT / "build").mkdir(exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix="utf8-native-", dir=ROOT / "build"))
    manifest = {
        **identities,
        "python": sys.version,
        "optimized_python": not __debug__,
        "native_wall_seconds": args.timeout,
        "tool_wall_seconds": 30,
        "cpu_soft_hard_seconds": [10, 11],
        "compiler_address_space_bytes": None if args.sanitized_compiler else 512 << 20,
        "other_address_space_bytes": 128 << 20,
        "regular_file_bytes": 8 << 20,
        "max_source_bytes": MAX_SOURCE_BYTES,
        "max_cases_per_batch": MAX_BATCH,
        "unicode_format": "17.0.0 section 3.9 Table 3-7",
        "scope": "ordinary functional Linux/x86-64 execution; no safety/performance proof",
        "status": "running",
    }
    print(json.dumps({**identities, "artifacts": str(directory)}), flush=True)
    suite = None
    try:
        longer = python_exhaustive()
        suite = Suite(compiler, directory, args.timeout, args.sanitized_compiler)
        for case in (scalar_loop(), short_loop(1), short_loop(2), boundary_loop(3), boundary_loop(4)):
            suite.check([case])
        batch = []
        for case in itertools.chain(ordinary_cases(), replay_cases()):
            batch.append(case)
            if len(batch) == MAX_BATCH:
                suite.check(batch)
                batch = []
        if batch:
            suite.check(batch)
        require(
            hashlib.sha256(compiler.read_bytes()).hexdigest() == identities["compiler_sha256"],
            "compiler identity changed during test",
        )
        require(
            hashlib.sha256(library.read_bytes()).hexdigest() == identities["utf8_sha256"],
            "UTF-8 library changed during test",
        )
        manifest.update(
            status="passed",
            native_checks=suite.count,
            native_batches=suite.batches,
            scalar_values=SCALARS,
            one_byte_inputs=256,
            two_byte_inputs=65536,
            longer_boundary_inputs=longer,
            final_modes_per_input=2,
        )
        print(
            f"PASS UTF-8: {suite.count} native checks in {suite.batches} bounded fixtures; "
            f"all {SCALARS} scalars, 256 one-byte, 65536 two-byte, {longer} longer boundary inputs; "
            f"artifacts={directory}",
            flush=True,
        )
    except Exception as error:
        manifest.update(status="failed", error=str(error))
        raise
    finally:
        if suite is not None:
            manifest["completed_native_checks"] = suite.count
            manifest["native_batches_attempted"] = suite.batches
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
