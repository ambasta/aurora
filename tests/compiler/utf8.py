#!/usr/bin/env python3
"""std.utf8 decoding, validation and encoding through one compiled driver.

The format reference is Unicode 17.0.0, section 3.9, D92 and Table 3-7:
https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-3/
Every case is a record streamed through one compiled driver. Decode,
validation, replay and encoding expectations come from CPython's strict UTF-8
codec (incremental decoder, str.encode, chr/ord), never from the library code.
Forged-report masking and layout sizes have no standard reference; their
expectations are the reviewed golden file golden/utf8_reports.jsonl.

The normal profile covers every one-byte input, the 24,200 longer boundary-class
inputs, transition boundaries plus fixed-seed scalar and two-byte samples, all
2,048 surrogates, and every API case. --profile exhaustive adds all 65,536
two-byte inputs and a native sweep of all 1,114,112 code points, whose
encodings are compared through per-plane fingerprints with str.encode and
roundtripped through both decoder modes and validation.
"""

from __future__ import annotations

import argparse
import codecs
import itertools
from pathlib import Path
import random

import runtime_records as records
from unsigned_oracle import require

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = Path(__file__).with_name("golden")
MAX_U64 = (1 << 64) - 1
MIN_I64 = -(1 << 63)
MAX_I64 = (1 << 63) - 1
PASS = 0xA55A1234FFFF00AA
SCALARS = 0x110000 - 0x800
MODULUS = 1000000007
STATUSES = ("success", "end_of_input", "out_of_range", "invalid_sequence", "truncated", "need_more")
ENCODE_STATUSES = ("success", "invalid_scalar")
INDICES = (MIN_I64, -1, 0, 1, 2, 3, 4, 5, MAX_I64)
FALLBACKS = (0, 165, 255)
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
SAMPLE_SEED = 220104
DATA_BYTES = 32
OPERATIONS = (
    "check",
    "decode_report_scalar",
    "decode_report_width",
    "decode_copy",
    "validation_copy",
    "replay",
    "stream",
    "encode",
    "forged_encode",
    "factory_copy",
    "constructor_copy",
    "layout",
    "sweep",
)
I64_FIELDS = ("operation", "length", "fill", "fill_byte", "offset", "count", "final_input", "status", "width", "split")
U64_FIELDS = ("value", "last")
SPAN = "builtin::span<const u8>"
DECODE = "std::Utf8DecodeResult"
VALIDATION = "std::Utf8ValidationResult"
ENCODE = "std::Utf8EncodeResult"


def is_scalar(value):
    return 0 <= value <= 0x10FFFF and not 0xD800 <= value <= 0xDFFF


def encoded(value):
    """Python's strict encoding of one code point, or None when it is not a scalar."""
    try:
        return chr(value).encode("utf-8", "strict")
    except (UnicodeEncodeError, ValueError, OverflowError):
        return None


def sampled_scalars():
    transitions = (0, 128, 2048, 0xD800, 0xE000, *range(0x10000, 0x110001, 0x10000))
    boundaries = {value + delta for value in transitions for delta in (-1, 0, 1) if is_scalar(value + delta)}
    rng = random.Random(SAMPLE_SEED)
    # Sample scalar ordinals, skipping the surrogate gap without rejection bias.
    sample = {value if value < 0xD800 else value + 2048 for value in rng.sample(range(SCALARS), 1024)}
    return tuple(sorted(boundaries | sample))


def sampled_pairs():
    boundaries = {first * 256 + second for first in (*LEADS, *BOUNDARIES) for second in BOUNDARIES}
    return tuple(sorted(boundaries | set(random.Random(SAMPLE_SEED).sample(range(65536), 1024))))


def validation(data, final):
    """(status, prefix bytes, scalars) from CPython's strict incremental decoder."""
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    try:
        text = decoder.decode(bytes(data), final)
    except UnicodeDecodeError as error:
        status = "truncated" if error.reason == "unexpected end of data" else "invalid_sequence"
        return status, error.start, len(bytes(data[: error.start]).decode("utf-8", "strict"))
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
                return "invalid_sequence", len(data) - len(pending), len(text)
    return ("need_more" if pending else "success"), len(data) - len(pending), len(text)


def check_expected(data, offset, count, final):
    """Decode then validate one window: status, scalar_or(max), width, status, prefix, scalars."""
    if offset < 0 or count < 0 or offset > len(data) or count > len(data) - offset:
        return [2, MAX_U64, 0, 2, 0, 0]
    window = bytes(data[offset : offset + count])
    status, prefix, scalars = validation(window, final)
    if count == 0:
        decoded = [1, MAX_U64, 0]
    elif prefix:
        first = window[:prefix].decode("utf-8", "strict")[0]
        decoded = [0, ord(first), len(first.encode("utf-8"))]
    else:
        decoded = [STATUSES.index(status), MAX_U64, 0]
    return [*decoded, STATUSES.index(status), prefix, scalars]


def access_expected(data, size, success=True):
    """Status, size, bytes_or_zero and byte_or(index, fallback) for one encoding report."""
    padded = (data[:size] if success else b"") + bytes(4 - (size if success else 0))
    values = [0 if success else 1, size if success else 0, *padded]
    for index, fallback in itertools.product(INDICES, FALLBACKS):
        values.append(padded[index] if success and 0 <= index < size else fallback)
    return values


def encode_expected(value):
    data = encoded(value)
    return access_expected(data, len(data)) if data is not None else access_expected(b"", 0, False)


def fingerprint(start, end):
    good = bad = value = 0
    for point in range(start, end):
        data = encoded(point)
        if data is None:
            bad += 1
            continue
        good += 1
        value = (value * 257 + len(data)) % MODULUS
        for byte in data:
            value = (value * 257 + byte) % MODULUS
    return [good, bad, value]


def check_case(label, data, offset, count, final):
    # Long inputs are a run of one repeated byte followed by at most DATA_BYTES.
    fill = max(0, len(data) - DATA_BYTES)
    require(data[:fill] == data[:1] * fill, "long check input must start with one repeated byte")
    fields = dict(fill=fill, fill_byte=data[0] if fill else 0, offset=offset, count=count, final_input=int(final))
    return label, dict(data=data[fill:], length=len(data) - fill, **fields), check_expected(data, offset, count, final)


def both_modes(label, data):
    for final in (True, False):
        yield check_case(f"{label}, final={final}", data, 0, len(data), final)


def sweep_cases(values, pairs):
    """Sampled or complete decoder input families, each in final and chunk mode."""
    for value in values:
        yield from both_modes(f"scalar U+{value:04X} decode/validate", encoded(value))
        yield f"scalar U+{value:04X} encoding and access", dict(operation=7, value=value), encode_expected(value)
    for value in range(0xD800, 0xE000):
        yield f"surrogate U+{value:04X} rejects", dict(operation=7, value=value), encode_expected(value)
    for value in range(256):
        yield from both_modes(f"one-byte input {value:02x}", bytes((value,)))
    for number in pairs:
        yield from both_modes(f"two-byte input {number:04x}", number.to_bytes(2, "big"))
    for width in (3, 4):
        for lead in LEADS:
            for tail in itertools.product(BOUNDARIES, repeat=width - 1):
                data = bytes((lead, *tail))
                yield from both_modes(f"length-{width} boundary-class input {data.hex()}", data)


def ordinary_cases():
    # Complete scalar boundaries, NUL, BOM, noncharacters and unassigned scalars.
    values = (0, 1, 0x7F, 0x80, 0x7FF, 0x800, 0xD7FF, 0xE000, 0xFFFF, 0x10000, 0x10FFFF)
    values += (0xFEFF, 0xFFFD, 0xFDD0, 0xFDEF, 0x1FFFE, 0x0378)
    for value in values:
        raw = encoded(value)
        for final in (False, True):
            for cut in range(len(raw) + 1):
                label = f"scalar U+{value:04X} window prefix {cut}, final={final}"
                yield check_case(label, b"\xff" + raw + b"\xff", 1, cut, final)
    # Range rejection must precede decoding and avoid signed addition overflow.
    for offset, count in itertools.product((MIN_I64, -1, 0, 1, 3, 4, 5, MAX_I64), (MIN_I64, -1, 0, 1, 2, 4, MAX_I64)):
        for final in (False, True):
            yield check_case(
                f"range offset={offset} count={count} final={final}", b"\xff\xc2\xa2\xff", offset, count, final
            )
    # All complete leading bytes/scalars are counted, failing scalar is untouched.
    prefix = encoded(0) + encoded(0xFEFF) + encoded(0x1F642) + b"A"
    endings = (b"", b"\x80", b"\xc0", b"\xc1\xbf", b"\xc2", b"\xe0\x9f", b"\xed\xa0", b"\xed\xbf\xbf", b"\xf0\x8f")
    endings += (b"\xf4\x90", b"\xf5", b"\xff", b"\xe1A", b"\xf1\x80A", b"\xe1\x80", b"\xf1\x80", b"\xf1\x80\x80")
    endings += (b"\xf4\x8f\xbf", b"\xffA")
    for ending in endings:
        for final in (False, True):
            data = b"\xff" + prefix + ending + b"\x00"
            label = f"validated prefix before {ending.hex()} final={final}"
            yield check_case(label, data, 1, len(prefix) + len(ending), final)
    data = b"A" * 4092 + encoded(0x10FFFF)
    yield check_case("full maximum-capacity 4096-byte span", data, 0, len(data), True)
    yield check_case("four-byte scalar at maximum-capacity span tail", data, 4092, 4, False)
    yield "decode report copies and input owner stay independent", dict(operation=3), [0x1F642]
    yield "validation reports are independent ordinary signed-count values", dict(operation=4), [PASS]


def replay_cases():
    # Every split replays the unconsumed suffix; a four-byte pending owner then
    # receives one byte at a time and must hold at most three bytes.
    examples = ((0, 0x7F, 0x80, 0x800, 0x10000, 0x10FFFF, 0xFEFF, 0xFDD0), (0x1F642, 65, 0xD7FF, 0xE000, 0x0378, 0))
    for values in examples:
        data = b"".join(encoded(value) for value in values)
        for split in range(len(data) + 1):
            first = validation(data[:split], False)
            last = validation(data[first[1] :], True)
            expected = [STATUSES.index(first[0]), first[1], first[2], STATUSES.index(last[0]), last[1], last[2]]
            yield (
                f"stateless two-chunk replay {data.hex()} split={split}",
                dict(operation=5, data=data, length=len(data), split=split),
                expected,
            )
        scalars = [ord(character) for character in data.decode("utf-8", "strict")]
        widest = max(len(chr(value).encode("utf-8")) for value in scalars) - 1
        yield (
            f"one-byte chunk replay with at most three retained bytes {data.hex()}",
            dict(operation=6, data=data, length=len(data)),
            [len(scalars), len(data), 0, widest, *scalars],
        )


def encode_cases():
    # Surrogate neighbors, every width edge, BOM, NUL, noncharacters, unassigned.
    values = (0, 1, 0x7E, 0x7F, 0x80, 0x81, 0x7FE, 0x7FF, 0x800, 0x801, 0xD7FF, 0xE000, 0xFFFE, 0xFFFF, 0x10000)
    values += (0x10001, 0x10FFFE, 0x10FFFF, 0xFEFF, 0xFFFD, 0xFDD0, 0xFDEF, 0x1FFFE, 0x1FFFF, 0x0378)
    for value in values:
        label = f"scalar U+{value:04X}: exact encoding, padding and extreme access"
        yield label, dict(operation=7, value=value), encode_expected(value)
    invalid = (0xD800, 0xD801, 0xDBFF, 0xDC00, 0xDFFE, 0xDFFF, 0x110000, 0x110001, 0x1FFFFF, 0xFFFFFFFF)
    for value in (*invalid, 1 << 32, 1 << 63, MAX_U64 - 1, MAX_U64):
        yield (
            f"invalid scalar {value}: normalized failure and extreme access",
            dict(operation=7, value=value),
            (encode_expected(value)),
        )
    for value in (0, 0x7F, 0x80, 0x800, 0x10000, 0x10FFFF):
        padded = list(encoded(value).ljust(4, b"\0"))
        label = f"factory U+{value:04X}: result and returned arrays are independent copies"
        yield label, dict(operation=9, value=value), padded * 3


def golden_cases():
    for row in records.load_jsonl(GOLDEN / "utf8_reports.jsonl"):
        values = {name: row[name] for name in ("status", "width", "value") if name in row}
        if "data" in row:
            values["data"] = bytes.fromhex(row["data"])
        yield row["label"], dict(operation=OPERATIONS.index(row["op"]), **values), row["expected"]


def exhaustive_sweeps():
    for plane in range(17):
        start, end = plane * 65536, (plane + 1) * 65536
        label = f"plane {plane}: every code point encodes, roundtrips and validates"
        yield label, dict(operation=12, value=start, last=end), fingerprint(start, end)


def driver_source():
    declarations, initializers, reader = records.byte_fields(chunks=1, width=DATA_BYTES)
    status_of = "auto status_of(std::Utf8Status status)->u64{"
    status_of += "".join(f"if(status==std::Utf8Status::{name}){{return {n}u64;}}" for n, name in enumerate(STATUSES))
    status_of += "return 777u64;}\n"
    access = f"auto access({ENCODE} report,i64 field)->u64{{"
    access += "if(field==0){if(report.status()==std::Utf8EncodeStatus::success){return 0u64;}"
    access += "if(report.status()==std::Utf8EncodeStatus::invalid_scalar){return 1u64;}return 777u64;}"
    access += "if(field==1){return bits(report.size());}"
    access += "if(field<6){const std::array<u8,4> output=report.bytes_or_zero();return u64(output.at(field-2));}"
    access += f"const builtin::array<i64,{len(INDICES)}> indices={{{','.join(map(str, INDICES))}}};"
    access += f"const builtin::array<u8,{len(FALLBACKS)}> fallbacks={{{','.join(f'{v}u8' for v in FALLBACKS)}}};"
    access += "const i64 slot=field-6;return u64(report.byte_or(indices[slot/3],fallbacks[slot%3]));}\n"
    source = (
        "module utf8_driver;import std.utf8;import std.array;\n"
        "auto both(bool a,bool b)->bool{if(a){return b;}return false;}\n"
        "auto either(bool a,bool b)->bool{if(a){return true;}return b;}\n"
        "auto bits(i64 value)->u64{if(value<0){return 18446744073709551615u64-u64(-(value+1));}return u64(value);}\n"
        "class ArrayLayoutProbe{u8 head;std::array<u8,4> owned;u8 tail;public:"
        "ArrayLayoutProbe(u8 a,std::array<u8,4> b,u8 c):head(a),owned(b),tail(c){} };\n"
        f"class ReportLayoutProbe{{u8 head;{ENCODE} owned;u8 tail;public:"
        f"ReportLayoutProbe(u8 a,{ENCODE} b,u8 c):head(a),owned(b),tail(c){{}} }};\n" + status_of + access
    )
    source += "class Utf8Input{" + declarations + "".join(f"i64 {name};" for name in I64_FIELDS)
    source += "".join(f"u64 {name};" for name in U64_FIELDS) + "public:Utf8Input():"
    source += ",".join(initializers + [f"{n}(0)" for n in I64_FIELDS] + [f"{n}(0u64)" for n in U64_FIELDS])
    source += "{}" + reader
    source += "auto selected_status() const -> std::Utf8Status {"
    source += "".join(f"if(status=={n}){{return std::Utf8Status::{name};}}" for n, name in enumerate(STATUSES))
    source += "return std::Utf8Status::out_of_range;}"
    source += "auto selected_encode() const -> std::Utf8EncodeStatus {if(status==0){"
    source += "return std::Utf8EncodeStatus::success;}return std::Utf8EncodeStatus::invalid_scalar;}"
    source += "auto stored() const -> std::array<u8,4> {std::array<u8,4> bytes=std::array<u8,4>();"
    source += "i64 at=0;while(at<4){bytes.set(at,input_byte(at));at=at+1;}return bytes;}"
    # Decode then validate the selected window of the whole input.
    source += f"auto check({SPAN} bytes,i64 field) const -> u64 {{const {SPAN} whole=bytes.subspan(0,fill+length);"
    source += f"if(field<3){{const {DECODE} d=std::decode_utf8(whole,offset,count,final_input!=0);"
    source += "if(field==0){return status_of(d.status());}if(field==1){return d.scalar_or(18446744073709551615u64);}"
    source += "return bits(d.width());}"
    source += f"const {VALIDATION} v=std::validate_utf8(whole,offset,count,final_input!=0);"
    source += "if(field==3){return status_of(v.status());}if(field==4){return bits(v.prefix_bytes());}"
    source += "return bits(v.scalar_count());}"
    source += f"auto replay({SPAN} bytes,i64 field) const -> u64 {{const {SPAN} view=bytes.subspan(0,length);"
    source += f"const {VALIDATION} first=std::validate_utf8(view,0,split,false);"
    source += "if(field==0){return status_of(first.status());}if(field==1){return bits(first.prefix_bytes());}"
    source += "if(field==2){return bits(first.scalar_count());}"
    source += f"const {VALIDATION} last=std::validate_utf8(view,first.prefix_bytes(),length-first.prefix_bytes(),true);"
    source += "if(field==3){return status_of(last.status());}if(field==4){return bits(last.prefix_bytes());}"
    source += "return bits(last.scalar_count());}"
    source += "auto entry(i64 field) const -> u64 {"
    source += "if(either(operation==0,operation==5)){" + records.ZERO_OWNER
    source += "i64 at=0;while(at<fill){owner[at]=u8(fill_byte);at=at+1;}"
    source += "while(at<fill+length){owner[at]=input_byte(at-fill);at=at+1;}"
    source += "if(operation==5){return replay(borrow_bytes(owner),field);}return check(borrow_bytes(owner),field);}"
    source += f"if(operation==1){{const {DECODE} report={DECODE}(selected_status(),value,width);"
    source += "return report.scalar_or(18446744073709551614u64);}"
    source += f"if(operation==2){{const {DECODE} report={DECODE}(selected_status(),value,width);"
    source += "return bits(report.width());}"
    source += f"""if(operation==3){{
        builtin::array<u8,4> bytes={{240u8,159u8,153u8,130u8}};
        const {DECODE} saved=std::decode_utf8(borrow_bytes(bytes),0,4,true);
        {{const {SPAN} view=borrow_bytes(bytes);
          const {DECODE} original=saved;
          if(original.scalar_or(0u64)!=128578u64){{return 1u64;}}
          const {VALIDATION} valid=std::validate_utf8(view,0,4,true);
          if(either(valid.prefix_bytes()!=4,valid.scalar_count()!=1)){{return 1u64;}}
          if(either(view.at(0)!=240u8,view.at(1)!=159u8)){{return 2u64;}}
          if(either(view.at(2)!=153u8,view.at(3)!=130u8)){{return 2u64;}}
        }}
        bytes[0]=65u8;bytes[1]=0u8;bytes[2]=0u8;bytes[3]=0u8;
        const {DECODE} copy=saved;
        if(either(copy.status()!=std::Utf8Status::success,copy.width()!=4)){{return 3u64;}}
        return copy.scalar_or(0u64);}}"""
    source += f"""if(operation==4){{
        const {VALIDATION} original={VALIDATION}(std::Utf8Status::success,{MIN_I64},{MAX_I64});
        const {VALIDATION} copy=original;
        if(copy.status()!=std::Utf8Status::success){{return 1u64;}}
        if(either(copy.prefix_bytes()!={MIN_I64},copy.scalar_count()!={MAX_I64})){{return 2u64;}}
        return {PASS}u64;}}"""
    # One byte at a time into a four-byte pending owner, appended only after
    # the previous borrow has ended: count, committed, final and widest carry,
    # then each decoded scalar.
    source += f"""if(operation==6){{
        builtin::array<u8,4> pending={{0u8,0u8,0u8,0u8}};
        i64 used=0;i64 input=0;i64 decoded=0;i64 committed=0;i64 widest=0;u64 selected=18446744073709551615u64;
        while(input<length){{pending[used]=input_byte(input);used=used+1;input=input+1;
            {{const {SPAN} view=borrow_bytes(pending);
              const {DECODE} result=std::decode_utf8(view,0,used,false);
              if(result.status()==std::Utf8Status::success){{
                  if(result.width()!=used){{return 18446744073709551614u64;}}
                  if(decoded==field-4){{selected=result.scalar_or(18446744073709551615u64);}}
                  decoded=decoded+1;committed=committed+used;used=0;
              }}else{{
                  if(result.status()!=std::Utf8Status::need_more){{return 18446744073709551613u64;}}
                  if(result.width()!=0){{return 18446744073709551613u64;}}
              }}
            }}
            if(used>widest){{widest=used;}}
            if(used>3){{return 18446744073709551612u64;}}
        }}
        if(field==0){{return bits(decoded);}}if(field==1){{return bits(committed);}}
        if(field==2){{return bits(used);}}if(field==3){{return bits(widest);}}return selected;}}"""
    source += f"if(operation==7){{const {ENCODE} report=std::encode_utf8(value);return access(report,field);}}"
    source += f"if(operation==8){{const {ENCODE} report={ENCODE}(selected_encode(),stored(),width);"
    source += "return access(report,field);}"
    source += f"""if(operation==9){{
        const {ENCODE} original=std::encode_utf8(value);const {ENCODE} saved=original;
        std::array<u8,4> first=original.bytes_or_zero();std::array<u8,4> second=saved.bytes_or_zero();
        first.set(0,255u8);first.set(1,254u8);first.set(2,253u8);first.set(3,252u8);
        if(field<4){{return u64(second.at(field));}}
        second.set(0,251u8);second.set(1,250u8);second.set(2,249u8);second.set(3,248u8);
        const std::array<u8,4> third=original.bytes_or_zero();const std::array<u8,4> fourth=saved.bytes_or_zero();
        if(field<8){{return u64(third.at(field-4));}}return u64(fourth.at(field-8));}}"""
    source += f"""if(operation==10){{
        std::array<u8,4> supplied=stored();
        const {ENCODE} original={ENCODE}(selected_encode(),supplied,width);const {ENCODE} saved=original;
        supplied.set(0,255u8);supplied.set(1,254u8);supplied.set(2,253u8);supplied.set(3,252u8);
        std::array<u8,4> first=original.bytes_or_zero();std::array<u8,4> second=saved.bytes_or_zero();
        if(field<4){{return u64(first.at(field));}}
        first.set(0,251u8);first.set(1,250u8);first.set(2,249u8);first.set(3,248u8);
        if(field<8){{return u64(second.at(field-4));}}return access(saved,field-8);}}"""
    # Compile-time and runtime size facts; no align_of or raw object bytes.
    source += """if(operation==11){
        static_assert(size_of(builtin::array<u8,4>)==4);
        static_assert(size_of(std::array<u8,4>)==4);
        static_assert(size_of(std::Utf8EncodeStatus)==8);
        static_assert(size_of(std::Utf8EncodeResult)==24);
        static_assert(field_count(std::array<u8,4>)==0);
        static_assert(field_count(std::Utf8EncodeResult)==0);
        static_assert(size_of(ArrayLayoutProbe)==6);
        static_assert(size_of(ReportLayoutProbe)==40);
        if(field==0){return u64(reflect_size(type_id(std::array<u8,4>)));}
        if(field==1){return u64(reflect_size(type_id(std::Utf8EncodeResult)));}
        if(field==2){return u64(reflect_size(type_id(ArrayLayoutProbe)));}
        return u64(reflect_size(type_id(ReportLayoutProbe)));}"""
    # Every code point in [value,last): encoding bytes, padding and fallbacks,
    # both decoder modes and both validation modes of the encoded bytes, and an
    # ordered fingerprint of the encodings for comparison with str.encode.
    failure = "{return 9000000000000000000u64+point*16u64+"
    source += f"""u64 point=value;u64 good=0u64;u64 bad=0u64;u64 digest=0u64;
        while(point<last){{
            const {ENCODE} report=std::encode_utf8(point);
            if(report.status()==std::Utf8EncodeStatus::success){{
                const i64 size=report.size();
                if(either(size<1,size>4)){failure}1u64;}}
                const std::array<u8,4> bytes=report.bytes_or_zero();
                builtin::array<u8,4> roundtrip={{0u8,0u8,0u8,0u8}};i64 index=0;
                digest=(digest*257u64+u64(size))%{MODULUS}u64;
                while(index<4){{
                    roundtrip[index]=bytes.at(index);
                    if(index<size){{
                        if(report.byte_or(index,255u8)!=bytes.at(index)){failure}2u64;}}
                        digest=(digest*257u64+u64(bytes.at(index)))%{MODULUS}u64;
                    }}else{{
                        if(bytes.at(index)!=0u8){failure}3u64;}}
                        if(report.byte_or(index,255u8)!=255u8){failure}4u64;}}
                    }}
                    index=index+1;
                }}
                {{const {SPAN} view=borrow_bytes(roundtrip);
                  const {DECODE} decoded=std::decode_utf8(view,0,size,true);
                  if(either(decoded.status()!=std::Utf8Status::success,decoded.width()!=size)){failure}5u64;}}
                  if(decoded.scalar_or({MAX_U64}u64)!=point){failure}6u64;}}
                  const {DECODE} chunk=std::decode_utf8(view,0,size,false);
                  if(either(chunk.status()!=std::Utf8Status::success,chunk.width()!=size)){failure}7u64;}}
                  if(chunk.scalar_or({MAX_U64}u64)!=point){failure}8u64;}}
                  const {VALIDATION} whole=std::validate_utf8(view,0,size,true);
                  if(either(whole.status()!=std::Utf8Status::success,whole.prefix_bytes()!=size)){failure}9u64;}}
                  if(whole.scalar_count()!=1){failure}10u64;}}
                  const {VALIDATION} part=std::validate_utf8(view,0,size,false);
                  if(either(part.status()!=std::Utf8Status::success,part.prefix_bytes()!=size)){failure}11u64;}}
                  if(part.scalar_count()!=1){failure}12u64;}}
                }}
                good=good+1u64;
            }}else{{
                if(report.size()!=0){failure}13u64;}}
                const std::array<u8,4> bytes=report.bytes_or_zero();i64 index=0;
                while(index<4){{
                    if(either(bytes.at(index)!=0u8,report.byte_or(index,165u8)!=165u8)){failure}14u64;}}
                    index=index+1;
                }}
                if(either(report.byte_or({MIN_I64},165u8)!=165u8,report.byte_or({MAX_I64},165u8)!=165u8)){failure}15u64;}}
                bad=bad+1u64;
            }}
            point=point+1u64;
        }}
        if(field==0){{return good;}}if(field==1){{return bad;}}return digest;}}}};
"""
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--profile", choices=("full", "exhaustive"), default="full")
    args = parser.parse_args()
    exhaustive = args.profile == "exhaustive"
    with records.scratch("utf8") as scratch:
        driver = records.Driver(args.compiler, scratch)
        program = driver.build(driver_source(), "Utf8Input", kind="u64")
        families = [
            sweep_cases(sampled_scalars(), range(65536) if exhaustive else sampled_pairs()),
            ordinary_cases(),
            replay_cases(),
            encode_cases(),
            golden_cases(),
        ]
        if exhaustive:
            families.append(exhaustive_sweeps())
        rows = [(label, program.pack(**values), expected) for label, values, expected in itertools.chain(*families)]
        count, observations = program.check(rows, scratch)
        rejections = records.load_jsonl(GOLDEN / "utf8_rejections.jsonl")
        for row in rejections:
            driver.reject(row["label"], row["source"], row["diagnostic"])
    print(f"PASS UTF-8 ({args.profile}): {count} cases, {observations} u64 observations, {len(rejections)} rejections")


if __name__ == "__main__":
    main()
