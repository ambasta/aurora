#!/usr/bin/env python3
"""std.json through one compiled driver fed every case as a record.

One driver covers the tokenizer/validator, scalar codecs, integer readers and
decimal encoding, and root lookup. Expected values that the Python standard
library defines (json.dumps escapes, str() decimal spelling) are computed here;
grammar statuses, coordinates, limits and shape normalization come from the
reviewed golden file golden/json_library.jsonl, frozen from the earlier
independent grammar models after they agreed with native results and with
CPython's json decoder. Hosted ownership fixtures and the library examples run
through hosted_records against the real byte runtime; rejections compile one
source each.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

import hosted_records
import runtime_records as records

GOLDEN = Path(__file__).with_name("golden")
MIN, MAX, U64_MAX = records.MIN, records.MAX, records.U64_MAX
SPAN = "builtin::span<const u8>"

JSON_STATUSES = (
    "success",
    "end_of_input",
    "invalid_window",
    "input_limit",
    "invalid_byte",
    "invalid_string",
    "invalid_number",
    "invalid_literal",
    "truncated",
    "number_limit",
    "token_limit",
    "depth_limit",
    "invalid_structure",
)
TOKEN_KINDS = (
    "none",
    "left_brace",
    "right_brace",
    "left_bracket",
    "right_bracket",
    "colon",
    "comma",
    "string",
    "number",
    "true_value",
    "false_value",
    "null_value",
)
INTEGER_STATUSES = (
    "success",
    "invalid_window",
    "invalid_number",
    "number_limit",
    "unsupported_number_form",
    "out_of_range",
)
LOOKUP_STATUSES = (
    "success",
    "invalid_window",
    "input_limit",
    "invalid_byte",
    "invalid_string",
    "invalid_number",
    "invalid_literal",
    "truncated",
    "number_limit",
    "token_limit",
    "depth_limit",
    "invalid_structure",
    "invalid_key_window",
    "key_limit",
    "invalid_key",
    "invalid_index",
    "wrong_root",
    "not_found",
    "ambiguous",
)
VALUE_KINDS = ("none", "object", "array_value", "string", "number", "true_value", "false_value", "null_value")
ESCAPE_INDICES = (MIN, -1, 0, 1, 2, 3, 4, 5, 6, MAX)
DECIMAL_INDICES = (MIN, -1, *range(22), MAX)
FALLBACKS = (0, 165, 255)
OPERATIONS = {
    name: number
    for number, name in [
        *enumerate(("token", "document", "token_report", "document_report", "token_expired", "document_expired")),
        *enumerate(
            (
                "decode",
                "scalar_shape",
                "escape",
                "escape_shape",
                "decode_expired",
                "escape_expired",
                "escape_roundtrip",
            ),
            10,
        ),
        *enumerate(
            (
                "parse_i64",
                "parse_u64",
                "i64_shape",
                "u64_shape",
                "format_i64",
                "format_u64",
                "decimal_shape",
                "parse_i64_expired",
                "parse_u64_expired",
                "format_i64_expired",
                "format_i64_roundtrip",
                "format_u64_expired",
                "format_u64_roundtrip",
                "fallback_i64",
                "fallback_u64",
                "byte_fallback",
            ),
            20,
        ),
        *enumerate(
            ("element", "member", "lookup_shape", "member_expired", "element_expired", "alias", "validator"), 40
        ),
    ]
}
SIGNED = ("index", "status", "kind", "start", "used", "error", "tokens", "depth", "width", "signed_value")
WINDOWS = ("first", "first_size", "second", "second_size", "key_first", "key_size", "key_second", "key_last")
SCALARS = ("operation", "length", "offset", "count", "key_length", "key_offset", "key_count", *WINDOWS, *SIGNED)


# ---- Expected values defined by the Python standard library.


def scalar_bytes(value):
    """UTF-8 of one Unicode scalar, or None for surrogates and values outside the code space."""
    try:
        return chr(value).encode("utf-8", "strict")
    except (ValueError, OverflowError, UnicodeEncodeError):
        return None


def escape_bytes(value):
    # CPython's canonical JSON spelling, including the short escapes and lowercase hex.
    return None if scalar_bytes(value) is None else json.dumps(chr(value), ensure_ascii=False)[1:-1].encode()


def escape_observation(data):
    good = data is not None and 1 <= len(data) <= 6
    width = len(data) if good else 0
    values = [0 if good else 1, width]
    for fallback in FALLBACKS:
        values += [data[i] if good and 0 <= i < width else fallback for i in ESCAPE_INDICES]
    return values


def decimal_observation(data):
    count = len(data)
    values = [0, count]
    for fallback in FALLBACKS:
        values += [data[i] if 0 <= i < count else fallback for i in DECIMAL_INDICES]
    return values


def expected(row):
    """Every observation of one row as a complete u64."""
    op = row["op"]
    if op in ("escape", "escape_expired"):
        return escape_observation(escape_bytes(row["scalar"]))
    if op == "escape_roundtrip":
        value = row["scalar"]
        return [0, value, value, len(escape_bytes(value)), 0]
    if op.startswith("format_"):
        value = row["signed_value"] if op.startswith("format_i64") else row["scalar"]
        if op.endswith("_roundtrip"):
            return [0, value & U64_MAX, value & U64_MAX, value & U64_MAX, 0]
        return decimal_observation(str(value).encode("ascii"))
    return [value & U64_MAX for value in row["expected"]]


# ---- The driver.


def observe_json(document=False, report="report", selector="field"):
    body = f"if({selector}==0){{"
    for i, status in enumerate(JSON_STATUSES):
        body += f"if({report}.status()==std::JsonStatus::{status}){{return {i};}}"
    body += "return -777;}"
    if not document:
        body += f"if({selector}==1){{"
        for i, kind in enumerate(TOKEN_KINDS):
            body += f"if({report}.kind()==std::JsonTokenKind::{kind}){{return {i};}}"
        body += "return -778;}"
    names = (
        ("error_offset", "token_count", "max_depth")
        if document
        else (
            "byte_offset",
            "byte_count",
            "consumed_bytes",
            "error_offset",
        )
    )
    for i, name in enumerate(names, 1 if document else 2):
        body += f"if({selector}=={i}){{return {report}.{name}();}}"
    return body + "return -779;"


def observe_scalar():
    body = "if(field==0){"
    for number, status in enumerate(JSON_STATUSES):
        body += f"if(report.status()==std::JsonStatus::{status}){{return {number}u64;}}"
    body += f"return {U64_MAX - 1}u64;}}"
    body += "if(field==1){return report.scalar_or(0u64);}"
    body += f"if(field==2){{return report.scalar_or({U64_MAX}u64);}}"
    body += "if(field==3){return u64(report.consumed_bytes());}"
    body += "if(field==4){return u64(report.error_offset());}"
    return body + f"return {U64_MAX - 2}u64;"


def observe_escape():
    body = "if(field==0){if(report.status()==std::JsonEscapeStatus::success){return 0u64;}"
    body += "if(report.status()==std::JsonEscapeStatus::invalid_scalar){return 1u64;}"
    body += f"return {U64_MAX - 1}u64;}}if(field==1){{return u64(report.size());}}"
    field = 2
    for fallback in FALLBACKS:
        for index in ESCAPE_INDICES:
            body += f"if(field=={field}){{return u64(report.byte_or({index},{fallback}u8));}}"
            field += 1
    return body + f"return {U64_MAX - 2}u64;"


def literal(value, signed):
    return str(value) + ("" if signed else "u64")


def observe_integer(signed):
    body = "if(field==0){"
    for number, status in enumerate(INTEGER_STATUSES):
        body += f"if(report.status()==std::JsonIntegerStatus::{status}){{return {number}u64;}}"
    body += f"return {U64_MAX}u64;}}"
    for number, fallback in enumerate((0, MIN, MAX) if signed else (0, MAX + 1, U64_MAX), 1):
        value = f"report.value_or({literal(fallback, signed)})"
        body += f"if(field=={number}){{return " + (f"signed_bits({value})" if signed else value) + ";}"
    return body + f"if(field==4){{return u64(report.error_offset());}}return {U64_MAX}u64;"


def observe_encoding():
    n = len(DECIMAL_INDICES)
    return (
        "if(field==0){if(report.status()==std::DecimalEncodingStatus::success){return 0u64;}"
        "if(report.status()==std::DecimalEncodingStatus::invalid_shape){return 1u64;}"
        f"return {U64_MAX}u64;}}if(field==1){{return u64(report.size());}}"
        "i64 ordinal=field-2;u8 fallback=0u8;"
        f"if(ordinal>={2 * n}){{fallback=255u8;ordinal=ordinal-{2 * n};}}"
        f"else{{if(ordinal>={n}){{fallback=165u8;ordinal=ordinal-{n};}}}}"
        "return u64(report.byte_or(encoding_index(ordinal),fallback));"
    )


def observe_lookup(report="report", selector="field"):
    body = f"if({selector}==0){{"
    for number, status in enumerate(LOOKUP_STATUSES):
        body += f"if({report}.status()==std::JsonLookupStatus::{status}){{return {number};}}"
    body += f"return -777;}}if({selector}==1){{"
    for number, kind in enumerate(VALUE_KINDS):
        body += f"if({report}.kind()==std::JsonValueKind::{kind}){{return {number};}}"
    body += "return -778;}"
    for number, name in enumerate(("byte_offset", "byte_count", "error_offset"), 2):
        body += f"if({selector}=={number}){{return {report}.{name}();}}"
    return body + "return -779;"


def selector(name, enum, names, field, fallback):
    body = f"auto {name}() const -> std::{enum} {{"
    body += "".join(f"if({field}=={n}){{return std::{enum}::{value};}}" for n, value in enumerate(names))
    return body + f"return std::{enum}::{fallback};}}"


def owner(name, size):
    return f'builtin::array<u8,{size}> {name}="' + "\\0" * size + '";'


def load(name="owner", size=4096, reader="data_at", length="length"):
    return owner(name, size) + f"i64 at=0;while(at<{length}){{{name}[at]={reader}(at);at=at+1;}}"


def unchanged(name, reader, length, failure):
    return f"at=0;while(at<{length}){{if({name}[at]!={reader}(at)){{return {failure};}}at=at+1;}}"


def nested(parameter, prefix=""):
    """Whole input, then two checked nested windows, all formed inside AU."""
    length = "key_length" if prefix else "length"
    first, size, second, last = WINDOWS[4:] if prefix else WINDOWS[:4]
    return (
        f"const {SPAN} {prefix}whole={parameter}.subspan(0,{length});"
        f"const {SPAN} {prefix}view={prefix}whole.subspan({first},{size});"
        f"const {SPAN} {prefix}nested={prefix}view.subspan({second},{last});"
    )


def call(result, expression):
    return f"const {result} result={expression};return result;}}"


def driver_source(module="json_library_driver", imports=("std.json", "std.decimal", "std.array")):
    chunks = [f"{group}{i}" for group in ("data", "key") for i in range(8)]
    source = f"module {module};" + "".join(f"import {name};" for name in imports) + "\n"
    source += "auto signed_bits(i64 value)->u64{if(value<0){return 18446744073709551615u64-u64(-(value+1));}"
    source += "return u64(value);}\n"
    source += f"auto encoding_index(i64 ordinal)->i64{{if(ordinal==0){{return {MIN};}}"
    source += f"if(ordinal==1){{return -1;}}if(ordinal=={len(DECIMAL_INDICES) - 1}){{return {MAX};}}"
    source += "return ordinal-2;}\n"
    source += (
        "class Counter{i64 calls;public:Counter():calls(0){}"
        f"auto bump_i64()->i64{{calls=calls+1;return {MIN};}}"
        f"auto bump_u64()->u64{{calls=calls+1;return {U64_MAX}u64;}}"
        "auto bump_u8()->u8{calls=calls+1;return 165u8;}auto count()const->i64{return calls;}};\n"
    )
    # Two 4096-byte inputs fit the layout leaf limit as u64 words of eight bytes.
    source += "class JsonInput{" + "".join(f"i64 {name};" for name in SCALARS) + "u64 scalar;"
    source += "".join(f"builtin::array<u64,64> {name};" for name in chunks)
    source += "public:JsonInput():" + ",".join(
        [*(f"{name}(0)" for name in SCALARS), "scalar(0u64)", *(f"{name}{{}}" for name in chunks)]
    )
    source += "{}"
    for group in ("data", "key"):
        source += f"auto {group}_at(i64 index) const -> u8 {{"
        for i in range(7):
            word = f"{group}{i}[(index-{512 * i})/8]"
            source += f"if(index<{512 * (i + 1)}){{return u8(({word}>>((index%8)*8))&255u64);}}"
        source += f"return u8(({group}7[(index-3584)/8]>>((index%8)*8))&255u64);}}"
    if "std.json" in imports:
        source += selector("json_status", "JsonStatus", JSON_STATUSES, "status", "success")
        source += selector("token_kind", "JsonTokenKind", TOKEN_KINDS, "kind", "none")
        source += selector("integer_status", "JsonIntegerStatus", INTEGER_STATUSES, "status", "invalid_window")
        source += selector("lookup_status", "JsonLookupStatus", LOOKUP_STATUSES, "status", "success")
        source += selector("value_kind", "JsonValueKind", VALUE_KINDS, "kind", "none")
        source += "auto escape_status() const -> std::JsonEscapeStatus {"
        source += "if(status==0){return std::JsonEscapeStatus::success;}return std::JsonEscapeStatus::invalid_scalar;}"
        source += json_methods()
    source += integer_methods("std.json" in imports)
    source += "auto entry(i64 field) const -> u64 {"
    if "std.json" in imports:
        source += "if(operation>=40){return signed_bits(lookup_entry(field));}"
        source += "if(operation<10){return signed_bits(profile_entry(field));}"
        source += "if(operation<20){return codec_entry(field);}"
    source += "return integer_entry(field);}};\n"
    return source


def json_methods():
    # Library calls take their spans as parameters, so each borrow ends with the
    # call and the owner can then be checked and overwritten before observation.
    source = ""
    for name, result, function in (
        ("token", "std::JsonTokenResult", "next_json_token"),
        ("document", "std::JsonResult", "validate_json"),
    ):
        source += f"auto parse_{name}({SPAN} bytes) const -> {result} {{" + nested("bytes")
        source += call(result, f"std::{function}(nested,offset,count)")
        # The source owner is local to this call and destroyed before observation.
        source += f"auto expired_{name}() const -> {result} {{" + load(size=64)
        source += f"const {SPAN} all=borrow_bytes(owner);const {SPAN} whole=all.subspan(0,length);"
        source += call(result, f"std::{function}(whole,0,length)")
    source += f"auto whole_document({SPAN} bytes) const -> std::JsonResult {{"
    source += f"const {SPAN} whole=bytes.subspan(0,length);"
    source += call("std::JsonResult", "std::validate_json(whole,0,length)")
    source += "auto profile_entry(i64 field) const -> i64 {"
    for operation, name, result in ((0, "token", "std::JsonTokenResult"), (1, "document", "std::JsonResult")):
        source += f"if(operation=={operation}){{" + load()
        source += f"const {result} original=parse_{name}(borrow_bytes(owner));"
        source += unchanged("owner", "data_at", "length", -780) + "owner[0]=0u8;"
        source += f"const {result} report=original;" + observe_json(operation == 1) + "}"
    source += "if(operation==2){const std::JsonTokenResult original="
    source += "std::JsonTokenResult(json_status(),token_kind(),start,count,used,error);"
    source += "const std::JsonTokenResult report=original;" + observe_json() + "}"
    source += "if(operation==3){const std::JsonResult original=std::JsonResult(json_status(),error,tokens,depth);"
    source += "const std::JsonResult report=original;" + observe_json(True) + "}"
    source += "if(operation==4){const std::JsonTokenResult original=expired_token();"
    source += "const std::JsonTokenResult report=original;" + observe_json() + "}"
    source += "const std::JsonResult original=expired_document();"
    source += "const std::JsonResult report=original;" + observe_json(True) + "}"

    # Scalar codecs.
    source += f"auto decode({SPAN} bytes) const -> std::JsonScalarResult {{" + nested("bytes")
    source += call("std::JsonScalarResult", "std::decode_json_string_scalar(nested,offset,count)")
    source += "auto expired_decode() const -> std::JsonScalarResult {" + load(size=64)
    source += f"const {SPAN} all=borrow_bytes(owner);const {SPAN} whole=all.subspan(0,length);"
    source += call("std::JsonScalarResult", "std::decode_json_string_scalar(whole,0,length)")
    source += "auto expired_escape() const -> std::JsonEscapeResult {"
    source += call("std::JsonEscapeResult", "std::escape_json_scalar(scalar)")
    source += "auto codec_entry(i64 field) const -> u64 {"
    source += "if(operation==10){" + load() + "const std::JsonScalarResult original=decode(borrow_bytes(owner));"
    source += unchanged("owner", "data_at", "length", f"{U64_MAX - 3}u64")
    source += "owner[0]=0u8;const std::JsonScalarResult report=original;" + observe_scalar() + "}"
    source += "if(operation==11){const std::JsonScalarResult original="
    source += "std::JsonScalarResult(json_status(),scalar,width,error);"
    source += "const std::JsonScalarResult report=original;" + observe_scalar() + "}"
    source += "if(operation==12){const std::JsonEscapeResult original=std::escape_json_scalar(scalar);"
    source += "const std::JsonEscapeResult report=original;" + observe_escape() + "}"
    source += "if(operation==13){std::array<u8,6> stored=std::array<u8,6>();i64 at=0;"
    source += "while(at<6){stored.set(at,data_at(at));at=at+1;}"
    source += "const std::JsonEscapeResult original=std::JsonEscapeResult(escape_status(),stored,width);"
    source += "const std::JsonEscapeResult report=original;stored.set(0,17u8);stored.set(5,18u8);"
    source += observe_escape() + "}"
    source += "if(operation==14){const std::JsonScalarResult original=expired_decode();"
    source += "const std::JsonScalarResult report=original;" + observe_scalar() + "}"
    source += "if(operation==15){const std::JsonEscapeResult original=expired_escape();"
    source += "const std::JsonEscapeResult report=original;" + observe_escape() + "}"
    # The library's own escape output decodes back to the same scalar.
    source += "const std::JsonEscapeResult escaped=std::escape_json_scalar(scalar);" + owner("owner", 6)
    source += "i64 i=0;while(i<escaped.size()){owner[i]=escaped.byte_or(i,255u8);i=i+1;}"
    source += "const std::JsonScalarResult report="
    source += "std::decode_json_string_scalar(borrow_bytes(owner),0,escaped.size());" + observe_scalar() + "}"

    # Root lookup.
    result = "std::JsonLookupResult"
    source += f"auto select({SPAN} bytes,{SPAN} keys) const -> {result} {{" + nested("bytes") + nested("keys", "key_")
    source += f"if(operation==40){{const {result} element="
    source += "std::lookup_json_element(nested,offset,count,index);return element;}"
    source += call(result, "std::lookup_json_member(nested,offset,count,key_nested,key_offset,key_count)")
    source += f"auto expired_lookup() const -> {result} {{" + load(size=64)
    source += load("keys", 64, "key_at", "key_length").replace("i64 at=0;", "at=0;")
    source += f"const {SPAN} all=borrow_bytes(owner);const {SPAN} whole=all.subspan(0,length);"
    source += f"const {SPAN} all_keys=borrow_bytes(keys);const {SPAN} key_whole=all_keys.subspan(0,key_length);"
    source += f"if(operation==44){{const {result} element=std::lookup_json_element(whole,0,length,index);"
    source += "return element;}"
    source += call(result, "std::lookup_json_member(whole,0,length,key_whole,0,key_length)")
    # Document and key may synchronously alias one readonly owner.
    source += f"auto alias({SPAN} bytes) const -> {result} {{const {SPAN} whole=bytes.subspan(0,length);"
    source += call(result, "std::lookup_json_member(whole,0,length,whole,key_offset,key_count)")
    source += f"auto validated({SPAN} bytes,{SPAN} keys) const -> {result} {{"
    source += f"const {SPAN} whole=bytes.subspan(0,length);const {SPAN} key_whole=keys.subspan(0,key_length);"
    source += call(result, "std::lookup_json_member(whole,0,length,key_whole,0,key_length)")
    source += "auto lookup_entry(i64 field) const -> i64 {"
    source += f"if(operation==42){{const {result} original={result}(lookup_status(),value_kind(),start,count,error);"
    source += f"const {result} report=original;" + observe_lookup() + "}"
    source += f"if(operation==43||operation==44){{const {result} original=expired_lookup();"
    source += f"const {result} report=original;" + observe_lookup() + "}"
    source += load("bytes") + load("keys", reader="key_at", length="key_length").replace("i64 at=0;", "at=0;")
    source += f"if(operation==45){{const {result} original=alias(borrow_bytes(bytes));bytes[0]=255u8;"
    source += f"const {result} report=original;" + observe_lookup() + "}"
    # The validator's own diagnostics are unchanged by an intervening lookup.
    source += "if(operation==46){const std::JsonResult before=whole_document(borrow_bytes(bytes));"
    source += f"const {result} report=validated(borrow_bytes(bytes),borrow_bytes(keys));"
    source += "const std::JsonResult after=whole_document(borrow_bytes(bytes));"
    source += "if(field<5){" + observe_lookup() + "}i64 selected=field-5;"
    source += "if(field<9){" + observe_json(True, "before", "selected") + "}"
    source += "selected=field-9;" + observe_json(True, "after", "selected") + "}"
    source += f"const {result} original=select(borrow_bytes(bytes),borrow_bytes(keys));"
    source += unchanged("bytes", "data_at", "length", -780) + unchanged("keys", "key_at", "key_length", -781)
    source += f"bytes[0]=255u8;keys[0]=255u8;const {result} report=original;" + observe_lookup() + "}"
    return source


def integer_methods(with_json):
    source = ""
    for signed, typ in ((True, "i64"), (False, "u64")):
        value = "signed_value" if signed else "scalar"
        source += f"auto format_{typ}() const -> std::DecimalEncodingResult {{"
        source += call("std::DecimalEncodingResult", f"std::format_decimal_{typ}({value})")
    if not with_json:
        source += "auto integer_entry(i64 field) const -> u64 {"
        source += "if(operation==24){const std::DecimalEncodingResult report=format_i64();" + observe_encoding() + "}"
        source += "const std::DecimalEncodingResult report=format_u64();" + observe_encoding() + "}"
        return source
    for signed, typ in ((True, "i64"), (False, "u64")):
        result = f"std::Json{typ.upper()}Result"
        source += f"auto parse_{typ}({SPAN} bytes) const -> {result} {{" + nested("bytes")
        source += call(result, f"std::parse_json_{typ}(nested,offset,count)")
        source += f"auto expired_parse_{typ}() const -> {result} {{" + load(size=64)
        source += f"const {SPAN} all=borrow_bytes(owner);const {SPAN} whole=all.subspan(0,length);"
        source += call(result, f"std::parse_json_{typ}(whole,0,length)")
    source += "auto integer_entry(i64 field) const -> u64 {"
    for signed, typ, base in ((True, "i64", 20), (False, "u64", 21)):
        result = f"std::Json{typ.upper()}Result"
        value = "signed_value" if signed else "scalar"
        source += f"if(operation=={base}){{" + load() + f"const {result} original=parse_{typ}(borrow_bytes(owner));"
        source += unchanged("owner", "data_at", "length", f"{U64_MAX}u64") + "owner[0]=0u8;"
        source += f"const {result} report=original;" + observe_integer(signed) + "}"
        source += f"if(operation=={base + 2}){{const {result} original={result}(integer_status(),{value},error);"
        source += f"const {result} report=original;" + observe_integer(signed) + "}"
        source += f"if(operation=={base + 4}){{const std::DecimalEncodingResult original=format_{typ}();"
        source += "const std::DecimalEncodingResult report=original;" + observe_encoding() + "}"
        source += f"if(operation=={base + 7}){{const {result} original=expired_parse_{typ}();"
        source += f"const {result} report=original;" + observe_integer(signed) + "}"
    for typ, expired, roundtrip in (("i64", 29, 30), ("u64", 31, 32)):
        result = f"std::Json{typ.upper()}Result"
        source += f"if(operation=={expired}){{const std::DecimalEncodingResult report=format_{typ}();"
        source += observe_encoding() + "}"
        source += f"if(operation=={roundtrip}){{const std::DecimalEncodingResult encoded=format_{typ}();"
        source += owner("owner", 20) + "i64 i=0;while(i<encoded.size()){owner[i]=encoded.byte_or(i,255u8);i=i+1;}"
        source += f"const {result} report=std::parse_json_{typ}(borrow_bytes(owner),0,encoded.size());"
        source += observe_integer(typ == "i64") + "}"
    # Fallback arguments are evaluated exactly once, before the call.
    for typ, operation in (("i64", 33), ("u64", 34)):
        result = f"std::Json{typ.upper()}Result"
        zero, answer = ("0", "42") if typ == "i64" else ("0u64", "42u64")
        source += f"if(operation=={operation}){{{typ} supplied={zero};if(status==0){{supplied={answer};}}"
        source += f"const {result} report={result}(integer_status(),supplied,0);"
        source += f"Counter side=Counter();const {typ} value=report.value_or(side.bump_{typ}());"
        source += "if(field==0){return " + ("signed_bits(value)" if typ == "i64" else "value") + ";}"
        source += "return u64(side.count());}"
    source += "std::array<u8,20> stored=std::array<u8,20>();i64 at=0;"
    source += "while(at<20){stored.set(at,data_at(at));at=at+1;}"
    source += "if(operation==35){const std::DecimalEncodingResult report=std::DecimalEncodingResult(stored,count);"
    source += "Counter side=Counter();const u8 value=report.byte_or(index,side.bump_u8());"
    source += "if(field==0){return u64(value);}return u64(side.count());}"
    source += "const std::DecimalEncodingResult original=std::DecimalEncodingResult(stored,count);"
    source += "const std::DecimalEncodingResult report=original;stored.set(0,17u8);stored.set(19,18u8);"
    return source + observe_encoding() + "}"


def family(row):
    operation = OPERATIONS[row["op"]]
    return "profile" if operation < 10 else "codecs" if operation < 20 else "integers" if operation < 40 else "lookup"


def load_rows(lines):
    """Golden rows. Each line is one input with its observations keyed by operation:
    a list of expected values, or true where the standard library supplies them.
    A missing label repeats the previous line's; missing scalars are zero, lengths
    are the input lengths and windows default to the whole input."""
    rows, label = [], None
    for line in lines:
        if not line.strip():
            continue
        line = json.loads(line)
        label = line.setdefault("label", label)
        inputs = {name: value for name, value in line.items() if name not in OPERATIONS}
        for op in (name for name in line if name in OPERATIONS):
            row = dict(inputs, op=op)
            if line[op] is not True:
                row["expected"] = line[op]
            rows.append(load_row(row))
    return rows


def load_row(row):
    for prefix, group in (("", "data"), ("key_", "key")):
        length = row.setdefault(f"{prefix}length", len(records.decode_data(row.get(group, ""))))
        names = WINDOWS[4:] if prefix else WINDOWS[:4]
        if not any(name in row for name in names):
            row.update(zip(names, (0, length, 0, length)))
    for name in (*SCALARS, "scalar"):
        row.setdefault(name, 0)
    return row


def pack(program, row):
    values = {name: row[name] for name in (*SCALARS, "scalar")}
    values["operation"] = OPERATIONS[row["op"]]
    for group in ("data", "key"):
        if group in row:
            values[group] = records.decode_data(row[group])
    return program.pack(**values)


def run_rows(program, rows, scratch):
    wanted = [expected(row) for row in rows]
    observed = program.observe(((pack(program, row), len(values)) for row, values in zip(rows, wanted)), scratch)
    mismatches, at = [], 0
    for row, values in zip(rows, wanted):
        actual = observed[at : at + len(values)]
        at += len(values)
        if actual != values:
            mismatches.append((family(row), row["label"], values, actual))
    records.require(not mismatches, f"{len(mismatches)} mismatched cases, first: {mismatches[:3]}")
    return len(observed)


# ---- Hosted ownership fixtures and examples, against the real byte runtime.

SCALAR_APPEND = """module scalar_append;
import std.json;import std.array;import std.binary;import std.byte_buffer;
auto entry(builtin::ByteRegion region,i64 scalar_input,i64 observation)->i64{
    builtin::OwnedBytes initial=region.try_allocate(2);
    std::ByteBuffer buffer=std::ByteBuffer(region,move(initial));
    if(!buffer.ok() || !buffer.try_append(65u8) || !buffer.try_append(66u8)){return -901;}
    u64 scalar=18446744073709551615u64;
    if(scalar_input>=0){scalar=u64(scalar_input);}
    const std::JsonEscapeResult escaped=std::escape_json_scalar(scalar);
    bool appended=false;
    if(escaped.status()==std::JsonEscapeStatus::success && escaped.size()<=9223372036854775807-buffer.size()){
        if(buffer.try_reserve(buffer.size()+escaped.size())){
            i64 i=0;while(i<escaped.size()){
                if(!buffer.try_append(escaped.byte_or(i,0u8))){return -902;}
                i=i+1;
            }
            appended=true;
        }
    }
    if(observation==-1){if(appended){return 1;}return 0;}
    if(observation==-2){return buffer.size();}
    if(observation==-3){return buffer.capacity();}
    const std::ByteReadResult value=buffer.read_u8(observation);
    return i64(value.value_or(256u64));
}
"""
LARGE_INTEGER_WINDOW = """module large_integer_window;
import std.json;
auto host_bits(u64 value)->i64{
    if(value>9223372036854775807u64){return -1-i64(18446744073709551615u64-value);}return i64(value);
}
auto entry(builtin::ByteRegion region,i64 n,i64 observation)->i64{
    builtin::OwnedBytes owner=region.try_allocate(n);
    if(!owner.ok() || n<160){return -901;}
    i64 i=0;while(i<n){owner.set(i,49u8);i=i+1;}
    builtin::array<u8,20> digits={
        49u8,56u8,52u8,52u8,54u8,55u8,52u8,52u8,48u8,55u8,51u8,55u8,48u8,57u8,53u8,53u8,49u8,54u8,49u8,53u8
    };
    i=0;while(i<20){owner.set(n-20+i,digits[i]);i=i+1;}
    const std::JsonTokenResult token=std::next_json_token(borrow_bytes(owner),n-20,20);
    const std::JsonU64Result saved=std::parse_json_u64(borrow_bytes(owner),n-20,20);
    owner.set(n-20,48u8);
    const std::JsonU64Result fresh=std::parse_json_u64(borrow_bytes(owner),n-20,20);
    const std::JsonI64Result bounded=std::parse_json_i64(borrow_bytes(owner),0,n);
    const std::JsonI64Result invalid=std::parse_json_i64(borrow_bytes(owner),-9223372036854775808,9223372036854775807);
    if(observation==0){return host_bits(saved.value_or(0u64));}
    if(observation==1){if(fresh.status()==std::JsonIntegerStatus::invalid_number){return 2;}return -902;}
    if(observation==2){return fresh.error_offset();}
    if(observation==3){return token.byte_count();}
    if(observation==4){if(bounded.status()==std::JsonIntegerStatus::number_limit){return 3;}return -903;}
    if(observation==5){return bounded.error_offset();}
    if(observation==6){if(invalid.status()==std::JsonIntegerStatus::invalid_window){return 1;}return -904;}
    if(observation==7){return invalid.error_offset();}
    return -905;
}
"""
INTEGER_APPEND = """module integer_append;
import std.decimal;import std.array;import std.binary;import std.byte_buffer;
auto entry(builtin::ByteRegion region,i64 unused,i64 observation)->i64{
    builtin::OwnedBytes initial=region.try_allocate(2);
    std::ByteBuffer buffer=std::ByteBuffer(region,move(initial));
    if(!buffer.ok() || !buffer.try_append(65u8) || !buffer.try_append(66u8)){return -901;}
    const std::DecimalEncodingResult encoded=std::format_decimal_i64(-9223372036854775808);
    bool appended=false;
    if(encoded.status()==std::DecimalEncodingStatus::success && encoded.size()<=9223372036854775807-buffer.size()){
        if(buffer.try_reserve(buffer.size()+encoded.size())){
            i64 i=0;while(i<encoded.size()){
                if(!buffer.try_append(encoded.byte_or(i,0u8))){return -902;}i=i+1;
            }
            appended=true;
        }
    }
    if(observation==-1){if(appended){return 1;}return 0;}
    if(observation==-2){return buffer.size();}
    if(observation==-3){return buffer.capacity();}
    const std::ByteReadResult value=buffer.read_u8(observation);return i64(value.value_or(256u64));
}
"""


def example_bytes(source, name):
    block = re.search(name + r"\s*=\s*\{(.*?)\};", source, re.S)
    records.require(block is not None, f"example {name} fixture")
    return bytes(map(int, re.findall(r"(\d+)u8", block.group(1))))


def buffer_value(observation, data, success):
    """An appended buffer's success flag (-1), size (-2), capacity (-3) or byte, 256 outside."""
    return {-1: int(success), -2: len(data), -3: len(data)}.get(
        observation, data[observation] if 0 <= observation < len(data) else 256
    )


def run_hosted(compiler, scratch):
    examples = records.ROOT / "library/examples"
    hosted = hosted_records.Hosted(compiler, scratch)
    fixtures = hosted.pack()

    # json_codecs example: the decoded text and its JSON spelling, from CPython.
    source = (examples / "json_codecs.au").read_text()
    raw = example_bytes(source, "source")
    text = json.loads(raw.decode("utf-8", "strict"))
    decoded = text.encode("utf-8")
    escaped = json.dumps(text, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    records.require(len(decoded) == 12 and len(escaped) == 22, "codec example sizes")
    combined = decoded + escaped
    example = hosted.pack(source, "json_codecs_example")
    for initial in (0, 1, 11, 12, 21, 22, 32):
        allocations = 2 + (initial < len(decoded)) + (initial < len(escaped))
        for observation in (MIN, -7, -3, -2, -1, *range(len(combined) + 1), MAX):
            value = {-1: len(decoded), -2: len(escaped)}.get(
                observation, combined[observation] if 0 <= observation < len(combined) else 256
            )
            example.run(0, 128, initial, observation, value, allocations, 2)
    for quota, initial, fail_after, value, allocations, peak in (
        (128, -1, None, -4, 0, 0),
        (0, 1, None, -4, 0, 0),
        (128, 0, 0, -4, 0, 0),
        (128, 0, 1, -4, 1, 1),
        (128, 0, 2, -5, 2, 2),
        (128, 0, 3, -5, 3, 2),
        (0, 0, None, -5, 2, 2),
        (11, 0, None, -5, 2, 2),
        (33, 0, None, -5, 3, 2),
        (34, 0, None, len(decoded), 4, 2),
        (128, 22, 2, len(decoded), 2, 2),
    ):
        example.run(0, quota, initial, -1, value, allocations, peak, fail_after)

    # Per-scalar reserve before append keeps a preexisting prefix on failure.
    program = fixtures.program("scalar-append", SCALAR_APPEND)
    for scalar in (-1, 0, 34, 65, 0x1F600):
        encoded = escape_bytes(scalar) if scalar >= 0 else None
        for quota, fail_after in ((128, None), (2, None), (128, 1)):
            success = encoded is not None and quota == 128 and fail_after is None
            data = b"AB" + (encoded if success else b"")
            for observation in (MIN, -3, -2, -1, *range(len(data) + 1), MAX):
                value = buffer_value(observation, data, success)
                fixtures.run(program, quota, scalar, observation, value, 2 if success else 1, 1, fail_after)

    # json_integers example: CPython's canonical wire form.
    wire = json.dumps([MIN, U64_MAX, 0], separators=(",", ":")).encode("ascii")
    records.require(len(wire) == 45, "integer example wire length")
    example = hosted.pack((examples / "json_integers.au").read_text(), "json_integers_example")
    for initial in (0, 1, 44, 45, 64):
        for observation in (MIN, -3, -2, -1, *range(46), MAX):
            value = {-1: 45, -2: max(45, initial)}.get(observation, wire[observation] if 0 <= observation < 45 else 256)
            example.run(0, 128, initial, observation, value, 1 + int(initial < 45), 1)
    for quota, initial, fail_after, value, allocations, peak in (
        (128, -1, None, -4, 0, 0),
        (0, 1, None, -4, 0, 0),
        (128, 0, 0, -4, 0, 0),
        (128, 0, 1, -5, 1, 1),
        (0, 0, None, -5, 1, 1),
        (44, 1, None, -5, 1, 1),
        (45, 1, None, 45, 2, 1),
        (45, 45, 1, 45, 1, 1),
    ):
        example.run(0, quota, initial, -1, value, allocations, peak, fail_after)

    # Real owners beyond the fixed-array limit: exact window, bounded spelling limit.
    program = fixtures.program("large-integer-window", LARGE_INTEGER_WINDOW)
    for count in (160, 4096, 4097, 8192):
        for observation, value in enumerate((U64_MAX, 2, count - 19, 20, 3, 128, 1, 0)):
            fixtures.run(program, 8192, count, observation, value, 1, 1)
    program = fixtures.program("integer-append", INTEGER_APPEND)
    for quota, fail_after in ((22, None), (21, None), (2, None), (128, 1)):
        success = quota == 22
        data = b"AB" + (str(MIN).encode("ascii") if success else b"")
        for observation in (MIN, -3, -2, -1, *range(23), MAX):
            fixtures.run(
                program,
                quota,
                0,
                observation,
                buffer_value(observation, data, success),
                2 if success else 1,
                1,
                fail_after,
            )

    # json_lookup example: reviewed nested extents; the selected name's scalars from CPython.
    source = (examples / "json_lookup.au").read_text()
    raw = example_bytes(source, r"\bwire")
    extents = [17, 47, 26, 37, 32, 30, 40, 21, len(raw)]
    records.require(len(raw) == 81, "lookup example wire length")
    scalars = [ord(char) for char in json.loads(raw[extents[6] : extents[6] + extents[7]])]
    example = hosted.pack(source, "json_lookup_example")
    for capacity in (0, 81, 128):
        wanted = [(-index - 1, value) for index, value in enumerate(extents)]
        wanted += list(enumerate(scalars)) + [(MIN, -8), (3, -8), (MAX, -8)]
        for observation, value in wanted:
            example.run(0, 256, capacity, observation, value, 2 if capacity < 81 else 1, 1)
    for quota, capacity, fail_after, value, allocations in (
        (256, -1, None, -1, 0),
        (80, 81, None, -1, 0),
        (80, 0, None, -2, 1),
        (256, 81, 0, -1, 0),
        (256, 0, 1, -2, 1),
        (81, 81, 1, 17, 1),
    ):
        example.run(0, quota, capacity, -1, value, allocations, int(allocations > 0), fail_after)

    # Lookup ownership fixtures over runtime-sized owners: reviewed golden vectors.
    for row in records.load_jsonl(GOLDEN / "json_library_hosted.jsonl"):
        program = fixtures.program(row["program"], row["source"])
        for quota, n, wanted, allocations, peak in row["vectors"]:
            for field, value in enumerate(wanted):
                fixtures.run(program, quota, n, field, value, allocations, peak)
    hosted.finish()
    return hosted.rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    args = parser.parse_args()
    with records.scratch("json-library") as scratch:
        driver = records.Driver(args.compiler, scratch)
        program = driver.build(driver_source(), "JsonInput", kind="u64", segmented=True)
        rows = load_rows((GOLDEN / "json_library.jsonl").read_text().splitlines())
        observations = run_rows(program, rows, scratch)
        # Generic decimal encoding works with no JSON import.
        (scratch / "decimal").mkdir()
        decimal = driver.build(
            driver_source("json_decimal_driver", ("std.decimal", "std.array")),
            "JsonInput",
            kind="u64",
            name="decimal-driver",
            segmented=True,
        )
        decimal_rows = load_rows((GOLDEN / "json_library_decimal.jsonl").read_text().splitlines())
        observations += run_rows(decimal, decimal_rows, scratch / "decimal")
        (scratch / "hosted").mkdir()
        hosted = run_hosted(args.compiler, scratch / "hosted")
        rejections = records.load_jsonl(GOLDEN / "json_library_rejections.jsonl")
        hosted_records.reject_all(args.compiler, scratch, rejections)
    print(
        f"PASS JSON library: {len(rows) + len(decimal_rows)} cases, {observations} 64-bit observations, "
        f"{hosted} hosted results, {len(rejections)} rejections"
    )


if __name__ == "__main__":
    main()
