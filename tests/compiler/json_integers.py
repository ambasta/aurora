#!/usr/bin/env python3
"""Exact JSON integer readers and generic decimal encoding, with independent oracles.

Regex prefix viability supplies syntax coordinates; CPython JSON separately audits
whole-spelling grammar, and arbitrary-precision int/str supplies values and bytes.
No float is constructed. Native observations retain all 64 bits, including signed
minima and unsigned maxima. Generated inputs, outputs and failed receipts remain.
This focused library gate is not full-native or sanitizer qualification.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import pathlib
import random
import re
import sys
import tempfile

sys.dont_write_bytecode = True
import json_profile as profile
import json_codecs as codecs
from compiler_contract import selected_flag_vectors
from package_profiles import SelectedCompiler, finalize_selected_identity

harness = profile.harness
require = harness.require
MIN, MAX = harness.MIN, harness.MAX
U64_MAX = (1 << 64) - 1
Case, Test, SPAN = profile.Case, profile.Test, profile.SPAN
STATUSES = ("success", "invalid_window", "invalid_number", "number_limit", "unsupported_number_form", "out_of_range")
S = {name: number for number, name in enumerate(STATUSES)}
NUMBER = re.compile(rb"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
# A regular expression for every viable prefix, including empty, minus, trailing
# dot/exponent/sign. Unlike the implementation, this has no numeric DFA states.
PREFIX = re.compile(rb"-?(?:(?:0|[1-9][0-9]*)(?:\.[0-9]*)?|(?:0|[1-9][0-9]*)(?:\.[0-9]+)?[eE][+-]?[0-9]*)?")
BOUNDARIES = b" \t\r\n{}[]:,"
INDICES = (MIN, -1, *range(22), MAX)
BYTE_FALLBACKS = (0, 165, 255)
SEED = 202610081


def fallback_values(signed):
    return (0, MIN, MAX) if signed else (0, MAX + 1, U64_MAX)


def integer_result(signed, status, value=0, error=0):
    return (S[status], *((value if status == "success" else v) & U64_MAX for v in fallback_values(signed)), error)


def integer_model(data, offset, count, signed):
    if offset < 0 or count < 0 or offset > len(data) or count > len(data) - offset:
        return integer_result(signed, "invalid_window")
    raw = bytes(data[offset : offset + count])
    # Check only the bounded spelling prefix. Syntax at the next byte precedes
    # the spelling limit; a valid 129th transition is number_limit instead.
    for index, byte in enumerate(raw[:129]):
        if byte in BOUNDARIES or PREFIX.fullmatch(raw[: index + 1]) is None:
            return integer_result(signed, "invalid_number", error=offset + index)
        if index == 128:
            return integer_result(signed, "number_limit", error=offset + index)
    if NUMBER.fullmatch(raw) is None:
        return integer_result(signed, "invalid_number", error=offset + count)
    if any(byte in raw for byte in (b".", b"e", b"E")):
        return integer_result(signed, "unsupported_number_form", error=offset)
    value = int(raw, 10)
    low, high = (MIN, MAX) if signed else (0, U64_MAX)
    if not low <= value <= high:
        return integer_result(signed, "out_of_range", error=offset)
    return integer_result(signed, "success", value)


def integer_shape(signed, status, value, error):
    if status == S["invalid_window"] or error < 0 or (status == 0 and error != 0) or (status != 0 and value != 0):
        return integer_result(signed, "invalid_window")
    return integer_result(signed, STATUSES[status], value, error)


def encoding_model(data, count):
    good = 1 <= count <= 20
    return (
        0 if good else 1,
        count if good else 0,
        *(data[index] if good and 0 <= index < count else fallback for fallback in BYTE_FALLBACKS for index in INDICES),
    )


def literal(value, signed):
    return str(value) + ("" if signed else "u64")


def integer_type(signed):
    return "JsonI64Result" if signed else "JsonU64Result"


def integer_function(signed):
    return "parse_json_i64" if signed else "parse_json_u64"


def observe_integer(signed):
    body = "if(field==0){"
    for number, status in enumerate(STATUSES):
        body += f"if(report.status()==std::JsonIntegerStatus::{status}){{return {number}u64;}}"
    body += f"return {U64_MAX}u64;}}"
    for number, fallback in enumerate(fallback_values(signed), 1):
        value = f"report.value_or({literal(fallback, signed)})"
        body += f"if(field=={number}){{return " + (f"signed_bits({value})" if signed else value) + ";}"
    return body + f"if(field==4){{return u64(report.error_offset());}}return {U64_MAX}u64;"


def observe_encoding():
    return (
        "if(field==0){if(report.status()==std::DecimalEncodingStatus::success){return 0u64;}"
        "if(report.status()==std::DecimalEncodingStatus::invalid_shape){return 1u64;}"
        f"return {U64_MAX}u64;}}if(field==1){{return u64(report.size());}}"
        "i64 ordinal=field-2;u8 fallback=0u8;"
        f"if(ordinal>={2 * len(INDICES)}){{fallback=255u8;ordinal=ordinal-{2 * len(INDICES)};}}"
        f"else{{if(ordinal>={len(INDICES)}){{fallback=165u8;ordinal=ordinal-{len(INDICES)};}}}}"
        "return u64(report.byte_or(encoding_index(ordinal),fallback));"
    )


def source_case(case, signed):
    result = "std::" + integer_type(signed)
    helper = f"auto input_CASE({SPAN} bytes)->{result}{{"
    parent = "bytes"
    for index, (start, count) in enumerate(case.windows):
        name = f"view{index}"
        helper += f"const {SPAN} {name}={parent}.subspan({start},{count});"
        parent = name
    helper += f"const {result} r=std::{integer_function(signed)}({parent},{case.offset},{case.extent()});return r;}}"
    body = harness.array(case.data) + f"const builtin::array<u8,{max(1, len(case.data))}> saved=owner;"
    body += f"const {result} original=input_CASE(borrow_bytes(owner));"
    body += f"i64 i=0;while(i<len(owner)){{if(owner[i]!=saved[i]){{return {U64_MAX}u64;}}i=i+1;}}owner[0]=0u8;"
    body += f"const {result} report=original;" + observe_integer(signed)
    expected = integer_model(case.span(), case.offset, case.extent(), signed)
    return Test(("i64 " if signed else "u64 ") + case.label, body, expected, helper)


def numeric_values(signed):
    low, high = (MIN, MAX) if signed else (0, U64_MAX)
    values = {low, high, 0, 1, 9, 10, 99, 100}
    for base in [*(1 << n for n in range(65)), *(10**n for n in range(21))]:
        for sign in (-1, 1) if signed else (1,):
            values.update(sign * base + delta for delta in (-1, 0, 1) if low <= sign * base + delta <= high)
    rng = random.Random(SEED + int(signed))
    values.update(rng.randrange(low, high + 1) for _ in range(64))
    return sorted(values)


def parse_cases():
    values = set(numeric_values(True)) | set(numeric_values(False))
    values.update(bound + delta for bound in (MIN, MAX, U64_MAX, -U64_MAX) for delta in range(-3, 4))
    for value in sorted(values):
        raw = str(value).encode("ascii")
        yield Case("full-width mathematical integer " + str(value), b"\xff" + raw + b"\xff", 1, len(raw))
    for raw in (
        b"0",
        b"-0",
        str(MIN).encode(),
        str(MAX).encode(),
        str(U64_MAX).encode(),
        b"-1",
        b"18446744073709551616",
    ):
        yield Case(
            "nested span relative coordinate " + repr(raw),
            b"\xff!?" + raw + b"X\xff",
            1,
            len(raw),
            ((1, len(raw) + 4), (1, len(raw) + 2)),
        )
        for count in range(len(raw) + 1):
            yield Case("every fullwidth spelling cutoff " + repr(raw), b"\xff" + raw + b"\xff", 1, count)
    malformed = (
        b"",
        b"-",
        b"+0",
        b"+1",
        b"--1",
        b"-+1",
        b"00",
        b"01",
        b"-00",
        b"-01",
        b".0",
        b"-.0",
        b"1.",
        b"1e",
        b"1E",
        b"1e+",
        b"1E-",
        b"1.e1",
        b"1e+-1",
        b"1.2.3",
        b"1e2e3",
        b"1e2.3",
        b"1_000",
        b"0x10",
        b"NaN",
        b"Infinity",
        b"-Infinity",
        b"null",
        b"true",
        b"false",
        b'"1"',
        b"[1]",
        b" 1",
        b"\t1",
        b"\r1",
        b"\n1",
        b"1 ",
        b"1,2",
        b"1\x00",
        b"1\xff",
        b"\xef\xbb\xbf1",
        b"\xd9\xa1",
        b"\xef\xbc\x91",
        b"\xe2\x88\x921",
        b"0\\u0000",
        b"1/2",
    )
    forms = (
        b"0.0",
        b"-0.0",
        b"1.0",
        b"-1.00",
        b"1e0",
        b"1E+0",
        b"-0E-0",
        b"1e-0",
        b"1e-1",
        b"1e99999999999999999999999",
        b"1e-99999999999999999999999",
        b"184467440737095516160.0",
    )
    for raw in (*malformed, *forms):
        yield Case("exact spelling syntax/form " + repr(raw), b"\xff" + raw + b"\xff", 1, len(raw))
    for byte in range(256):
        yield Case("each byte alone " + str(byte), bytes((byte,)))
        yield Case("each byte after integer " + str(byte), b"1" + bytes((byte,)))
    for prefix in (b"-", b"0", b"1.", b"1e", b"1e+", b"1e1", b"1.2"):
        for byte in b"-+0129.eEx_\x00\x80\xff \t\r\n{}[]:,":
            yield Case("grammar transition byte " + repr(prefix) + " " + str(byte), prefix + bytes((byte,)))
    for width in (126, 127, 128, 129, 130):
        for raw in (
            b"9" * width,
            b"-" + b"9" * (width - 1),
            b"0." + b"0" * (width - 2),
            b"1e" + b"0" * (width - 2),
            b"1e+" + b"9" * (width - 3),
        ):
            yield Case("128-byte limit versus form/range width " + str(width), b"\xff" + raw + b"\xff", 1, width)
    for prefix in (b"9" * 128, b"0." + b"0" * 126, b"1e" + b"9" * 126, b"9" * 127 + b"e", b"9" * 126 + b"e+"):
        for suffix in (b"", b"9", b".", b"e", b"+", b"-", b"x", b"\xff", b" ", b",", b"]"):
            raw = prefix + suffix
            yield Case("next-byte syntax versus spelling-limit precedence", b"\xff" + raw + b"\xff", 1, len(raw))
    for suffix in (b"", b"0", b".0", b"e0", b"x", b",", b" "):
        raw = b"18446744073709551616" + suffix
        yield Case("syntax/form before integer overflow " + repr(suffix), b"\xff" + raw, 1, len(raw))
    for offset, count in itertools.product((MIN, -1, 0, 1, 2, 128, 4096, MAX), repeat=2):
        yield Case("subtraction-first signed window edges", b"0", offset, count)
    for offset, count in ((0, 0), (0, 1), (1, 0), (MIN, MAX), (MAX, MAX)):
        yield Case("actual empty nested span", b"\xff", offset, count, ((1, 0), (0, 0)))
    yield Case("maximum owner spelling bounded by 128", b"1" * 4096)
    yield Case("maximum owner final exact integer", b"\xff" * 4076 + str(U64_MAX).encode(), 4076, 20)
    rng = random.Random(SEED)
    for _ in range(64):
        raw = bytes(rng.choice(b"0123456789-.eE+, \xff") for _ in range(rng.randrange(31)))
        yield Case("seeded arbitrary numeric spelling", raw or b"\xff", 0, len(raw))


def shape_tests():
    for signed in (True, False):
        values = (MIN, -1, 0, 1, MAX) if signed else (0, 1, MAX, MAX + 1, U64_MAX)
        for status, value, error in itertools.product(range(len(STATUSES)), values, (MIN, -1, 0, 1, MAX)):
            cls = "std::" + integer_type(signed)
            body = f"const {cls} original={cls}(std::JsonIntegerStatus::{STATUSES[status]},"
            body += f"{literal(value, signed)},{error});"
            # Whole-class assignment is outside the current Aurora surface.
            # Separate source-owner/payload mutations and expired-scope probes
            # exercise lifetime independence; these fixtures certify shape.
            body += f"const {cls} report=original;"
            yield Test(
                "forged integer constructor shape and copied report",
                body + observe_integer(signed),
                integer_shape(signed, status, value, error),
            )


def stored_array(data):
    require(len(data) == 20, "encoding payload shape")
    return "std::array<u8,20> stored=std::array<u8,20>();" + "".join(
        f"stored.set({index},{byte}u8);" for index, byte in enumerate(data)
    )


def encoding_tests():
    for signed in (True, False):
        for value in numeric_values(signed):
            raw = str(value).encode("ascii")
            body = "const std::DecimalEncodingResult original="
            body += f"std::format_decimal_{'i64' if signed else 'u64'}({literal(value, signed)});"
            body += "const std::DecimalEncodingResult report=original;"
            yield Test(
                "canonical generic decimal " + str(value), body + observe_encoding(), encoding_model(raw, len(raw))
            )
    for count, data in itertools.product(
        (MIN, -1, 0, *range(1, 22), MAX), (bytes(20), b"0123456789ABCDEFGHIJ", b"\xff" * 20)
    ):
        body = stored_array(data)
        body += "const std::DecimalEncodingResult original=std::DecimalEncodingResult(stored," + str(count) + ");"
        body += "const std::DecimalEncodingResult report=original;stored.set(0,17u8);stored.set(19,18u8);"
        yield Test(
            "forged decimal payload certifies shape only and copies bytes",
            body + observe_encoding(),
            encoding_model(data, count),
        )


def lifetime_and_roundtrip_tests():
    for signed in (True, False):
        cls = "std::" + integer_type(signed)
        for raw in (b"0", b"-0", str(MIN).encode(), str(U64_MAX).encode(), b"1e0", b"01"):
            helper = f"auto expired_CASE()->{cls}{{" + harness.array(raw)
            helper += f"const {cls} r=std::{integer_function(signed)}(borrow_bytes(owner),0,{len(raw)});return r;}}"
            body = f"const {cls} original=expired_CASE();const {cls} report=original;"
            yield Test(
                "integer report outlives source scope",
                body + observe_integer(signed),
                integer_model(raw, 0, len(raw), signed),
                helper,
            )
        values = (MIN, -1, 0, 1, MAX) if signed else (0, 1, MAX, MAX + 1, U64_MAX)
        for value in values:
            raw = str(value).encode("ascii")
            helper = "auto expired_CASE()->std::DecimalEncodingResult{"
            helper += "const std::DecimalEncodingResult r="
            helper += f"std::format_decimal_{'i64' if signed else 'u64'}({literal(value, signed)});return r;}}"
            body = "const std::DecimalEncodingResult report=expired_CASE();"
            yield Test(
                "decimal encoding outlives factory scope",
                body + observe_encoding(),
                encoding_model(raw, len(raw)),
                helper,
            )
            body = "const std::DecimalEncodingResult encoded=expired_CASE();" + harness.array(bytes(20)) + "i64 i=0;"
            body += "while(i<encoded.size()){owner[i]=encoded.byte_or(i,255u8);i=i+1;}"
            body += f"const {cls} report=std::{integer_function(signed)}(borrow_bytes(owner),0,encoded.size());"
            yield Test(
                "decimal factory JSON roundtrip supplements independent bytes",
                body + observe_integer(signed),
                integer_result(signed, "success", value),
                helper,
            )


def eager_fallback_tests():
    for signed in (True, False):
        typ, cls = ("i64" if signed else "u64"), "std::" + integer_type(signed)
        fallback = MIN if signed else U64_MAX
        helper = "class Counter_CASE{i64 calls;public:Counter_CASE():calls(0){}"
        helper += f"auto bump()->{typ}{{calls=calls+1;return {literal(fallback, signed)};}}"
        helper += "auto count()const->i64{return calls;}};"
        for status in STATUSES:
            success = status == "success"
            body = (
                f"const {cls} report={cls}(std::JsonIntegerStatus::{status},{literal(42 if success else 0, signed)},0);"
            )
            body += f"Counter_CASE side=Counter_CASE();const {typ} value=report.value_or(side.bump());"
            body += (
                "if(field==0){return " + ("signed_bits(value)" if signed else "value") + ";}return u64(side.count());"
            )
            yield Test(
                "integer fallback eagerly evaluated once " + status,
                body,
                ((42 if success else fallback) & U64_MAX, 1),
                helper,
            )
    helper = (
        "class Counter_CASE{i64 calls;public:Counter_CASE():calls(0){}"
        "auto bump()->u8{calls=calls+1;return 165u8;}auto count()const->i64{return calls;}};"
    )
    for count, index in itertools.product((0, 1, 20, 21), (MIN, -1, 0, 19, 20, MAX)):
        body = stored_array(b"0123456789ABCDEFGHIJ")
        body += f"const std::DecimalEncodingResult report=std::DecimalEncodingResult(stored,{count});"
        body += "Counter_CASE side=Counter_CASE();"
        body += f"const u8 value=report.byte_or({index},side.bump());"
        body += "if(field==0){return u64(value);}return u64(side.count());"
        value = b"0123456789ABCDEFGHIJ"[index] if 1 <= count <= 20 and 0 <= index < count else 165
        yield Test("decimal byte fallback eagerly evaluated once", body, (value, 1), helper)


def all_tests():
    for case in parse_cases():
        for signed in (True, False):
            yield source_case(case, signed)
    yield from shape_tests()
    yield from encoding_tests()
    yield from lifetime_and_roundtrip_tests()
    yield from eager_fallback_tests()


def rejections(json_source, decimal_source):
    head = "module rejection;import std.json;import std.decimal;import std.array;"
    for signed in (True, False):
        cls, typ = integer_type(signed), "i64" if signed else "u64"
        setup = f"const std::{cls} r=std::{cls}(std::JsonIntegerStatus::success,{literal(0, signed)},0);"
        block = re.search(r"class " + cls + r"\s*\{(.*?)public:", json_source, re.S)
        require(block is not None, "integer report declaration")
        fields = re.findall(r"(?:JsonIntegerStatus|u64|i64)\s+(\w+)\s*;", block.group(1))
        require(len(fields) == 3, "three private integer fields")
        for field in fields:
            yield ("private integer field", head + "auto test()->u64{" + setup + f"return r.{field};}}", "private")
        for fallback in ("0u64", "0u8", "false") if signed else ("0", "0u8", "false"):
            yield (
                "exact integer fallback type",
                head + "auto test()->u64{" + setup + f"return r.value_or({fallback});}}",
                "expected " + typ,
            )
        for method in ("consumed_bytes", "byte_count", "size", "scalar_or"):
            yield (
                "integer result has no unrelated extent or scalar API",
                head + "auto test()->u64{" + setup + f"return r.{method}();}}",
                "unknown",
            )
        for args in ("0u64,1", "0,1u64", "0u8,1", "0,1u8", "false,1", "0,false"):
            yield (
                "exact signed integer window",
                head
                + "auto test()->u64{builtin::array<u8,1> b={48u8};"
                + f"const std::{cls} r=std::{integer_function(signed)}(borrow_bytes(b),{args});return 0u64;}}",
                "expected i64",
            )
        yield (
            "integer parser needs explicit span",
            head
            + "auto test()->u64{builtin::array<u8,1> b={48u8};"
            + f"const std::{cls} r=std::{integer_function(signed)}(b,0,1);return 0u64;}}",
            "span",
        )
        yield (
            "integer parser byte owner only",
            head
            + "auto test()->u64{builtin::array<i64,1> b={48};"
            + f"const std::{cls} r=std::{integer_function(signed)}(borrow_bytes(b),0,1);return 0u64;}}",
            "byte",
        )
        yield (
            "live integer input borrow prevents source mutation",
            head
            + "auto test()->u64{builtin::array<u8,1> b={48u8};"
            + f"const {SPAN} view=borrow_bytes(b);"
            + f"const std::{cls} r=std::{integer_function(signed)}(view,0,1);b[0]=0u8;return 0u64;}}",
            "span is live",
        )
        for args, diagnostic in (
            (f"0,{literal(0, signed)},0", "expected"),
            (f"std::JsonStatus::success,{literal(0, signed)},0", "expected"),
            (f"std::JsonIntegerStatus::success,{literal(0, not signed)},0", "expected " + typ),
            (f"std::JsonIntegerStatus::success,{literal(0, signed)},0u64", "expected i64"),
            (f"std::JsonIntegerStatus::success,{literal(0, signed)}", "argument"),
        ):
            yield (
                "integer constructor exact types and arity",
                head + f"auto test()->u64{{const std::{cls} r=std::{cls}({args});return 0u64;}}",
                diagnostic,
            )
        for value in ("0u64", "0u8", "false") if signed else ("0", "0u8", "false"):
            yield (
                "decimal formatter exact scalar type",
                head
                + "auto test()->u64{const std::DecimalEncodingResult r="
                + f"std::format_decimal_{typ}({value});return 0u64;}}",
                "expected " + typ,
            )
    block = re.search(r"class DecimalEncodingResult\s*\{(.*?)public:", decimal_source, re.S)
    require(block is not None, "decimal encoding declaration")
    fields = re.findall(r"(?:i64|(?:std::)?array<u8,\s*20>)\s+(\w+)\s*;", block.group(1))
    require(len(fields) == 2, "two private encoding fields")
    encoding = "const std::DecimalEncodingResult r=std::format_decimal_u64(42u64);"
    for field in fields:
        yield ("private encoding field", head + "auto test()->u64{" + encoding + f"return r.{field};}}", "private")
    for index in ("0u64", "0u8", "false"):
        yield (
            "encoding exact signed index",
            head + "auto test()->u64{" + encoding + f"return u64(r.byte_or({index},0u8));}}",
            "expected i64",
        )
    for fallback in ("0", "0u64", "false"):
        yield (
            "encoding exact byte fallback",
            head + "auto test()->u64{" + encoding + f"return u64(r.byte_or(0,{fallback}));}}",
            "expected u8",
        )
    for helper in sorted(set(re.findall(r"\bauto\s+((?:json_|decimal_)\w+)\s*\(", json_source + decimal_source))):
        yield (
            "private numeric helper " + helper,
            head + f"auto test()->u64{{return std::{helper}();}}",
            "private function is not imported",
        )
    for count in ("0u64", "0u8", "false"):
        yield (
            "encoding constructor signed count",
            head
            + "auto test()->u64{std::array<u8,20> a=std::array<u8,20>();"
            + f"const std::DecimalEncodingResult r=std::DecimalEncodingResult(a,{count});return 0u64;}}",
            "expected i64",
        )
    for width in (19, 21):
        yield (
            "encoding constructor exact array width",
            head
            + f"auto test()->u64{{std::array<u8,{width}> a=std::array<u8,{width}>();"
            + "const std::DecimalEncodingResult r=std::DecimalEncodingResult(a,20);return 0u64;}",
            "expected",
        )
    yield (
        "decimal module does not reexport JSON result",
        "module rejection;import std.decimal;auto test()->u64{"
        "const std::JsonU64Result r=std::JsonU64Result(std::JsonIntegerStatus::success,0u64,0);return 0u64;}",
        "unknown",
    )


def decimal_only_tests():
    for signed, value in ((True, MIN), (False, U64_MAX)):
        raw = str(value).encode("ascii")
        body = "const std::DecimalEncodingResult report="
        body += f"std::format_decimal_{'i64' if signed else 'u64'}({literal(value, signed)});"
        yield Test(
            "generic decimal works with no JSON import", body + observe_encoding(), encoding_model(raw, len(raw))
        )


def hosted_tests(suite):
    expected_bytes = json.dumps([MIN, U64_MAX, 0], separators=(",", ":")).encode("ascii")
    require(len(expected_bytes) == 45, "independent example wire length")
    source = (suite.root / "library/examples/json_integers.au").read_text()
    directory = codecs.hosted_compile(suite, "hosted-example", source, "json_integers_example")
    for initial in (0, 1, 44, 45, 64):
        for observation in (MIN, -3, -2, -1, *range(46), MAX):
            expected = {-1: 45, -2: max(45, initial)}.get(
                observation, expected_bytes[observation] if 0 <= observation < 45 else 256
            )
            codecs.hosted_observe(
                suite,
                directory,
                "example exact canonical bytes and reserve once",
                128,
                initial,
                observation,
                expected,
                1 + int(initial < 45),
                1,
            )
    for quota, initial, fail_after, expected, allocations, peak in (
        (128, -1, None, -4, 0, 0),
        (0, 1, None, -4, 0, 0),
        (128, 0, 0, -4, 0, 0),
        (128, 0, 1, -5, 1, 1),
        (0, 0, None, -5, 1, 1),
        (44, 1, None, -5, 1, 1),
        (45, 1, None, 45, 2, 1),
        (45, 45, 1, 45, 1, 1),
    ):
        codecs.hosted_observe(
            suite,
            directory,
            "example allocation/quota failure and cleanup",
            quota,
            initial,
            -1,
            expected,
            allocations,
            peak,
            fail_after,
        )
    source = """module large_integer_window;
import std.json;
auto host_bits(u64 value)->i64{
    if(value>9223372036854775807u64){return -1-i64(18446744073709551615u64-value);}return i64(value);
}
auto large_integer_window(builtin::ByteRegion region,i64 n,i64 observation)->i64{
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
    directory = codecs.hosted_compile(suite, "hosted-large-windows", source, "large_integer_window")
    for count in (160, 4096, 4097, 8192):
        for observation, expected in enumerate((U64_MAX, 2, count - 19, 20, 3, 128, 1, 0)):
            codecs.hosted_observe(
                suite,
                directory,
                "real owner exact window, bounded limit, copied token is not source authority",
                8192,
                count,
                observation,
                expected,
                1,
                1,
            )
    source = """module integer_append;
import std.decimal;import std.array;import std.binary;import std.byte_buffer;
auto integer_append(builtin::ByteRegion region,i64 unused,i64 observation)->i64{
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
    directory = codecs.hosted_compile(suite, "hosted-reserve-prefix", source, "integer_append")
    for quota, fail_after in ((22, None), (21, None), (2, None), (128, 1)):
        success = quota == 22
        raw = b"AB" + (str(MIN).encode("ascii") if success else b"")
        for observation in (MIN, -3, -2, -1, *range(23), MAX):
            expected = {-1: int(success), -2: len(raw), -3: len(raw)}.get(
                observation, raw[observation] if 0 <= observation < len(raw) else 256
            )
            codecs.hosted_observe(
                suite,
                directory,
                "complete reserve preserves preexisting prefix on failure",
                quota,
                0,
                observation,
                expected,
                2 if success else 1,
                1,
                fail_after,
            )
    print(
        f"PASS JSON integer hosted composition: {suite.hosted_observations} results with real allocation cleanup",
        flush=True,
    )


def compare(observed, expected):
    require(len(observed) == len(expected), "exact complete native observation count")
    require(
        observed == expected,
        f"native mismatch {[(i, a, b) for i, (a, b) in enumerate(zip(observed, expected)) if a != b][:16]}",
    )


def self_test():
    for signed in (True, False):
        for raw, status, error in (
            (b"", "invalid_number", 1),
            (b"-0", "success", 0),
            (b" 1", "invalid_number", 1),
            (b"1 ", "invalid_number", 2),
            (b"-", "invalid_number", 2),
            (b"01", "invalid_number", 2),
            (b"1e+", "invalid_number", 4),
            (b"1.e1", "invalid_number", 3),
            (b"1.0", "unsupported_number_form", 1),
            (b"1e999999999", "unsupported_number_form", 1),
            (b"9" * 128, "out_of_range", 1),
            (b"9" * 129, "number_limit", 129),
            (b"9" * 128 + b"x", "invalid_number", 129),
            (b"9" * 128 + b".", "number_limit", 129),
            (b"9" * 128 + b" ", "invalid_number", 129),
            (b"9" * 127 + b"e", "invalid_number", 129),
            (b"9" * 127 + b"e+", "number_limit", 129),
            (b"9" * 126 + b"e+", "invalid_number", 129),
            (b"9" * 126 + b"e+x", "invalid_number", 129),
        ):
            actual = integer_model(b"\xff" + raw, 1, len(raw), signed)
            require(
                actual[0] == S[status] and actual[-1] == error, "independent syntax/form/limit coordinate " + repr(raw)
            )
        require(
            integer_model(b"\xff", MIN, MAX, signed) == integer_result(signed, "invalid_window"),
            "window guard precedence",
        )
        require(
            integer_model(b"0", 1, 0, signed) == integer_result(signed, "invalid_number", error=1), "empty endpoint"
        )
    require(
        integer_model(str(MIN).encode(), 0, 20, True) == integer_result(True, "success", MIN), "minimum signed exact"
    )
    require(
        integer_model(str(U64_MAX).encode(), 0, 20, False) == integer_result(False, "success", U64_MAX),
        "maximum unsigned exact",
    )
    require(integer_model(b"-1", 0, 2, False) == integer_result(False, "out_of_range"), "unsigned negative nonzero")
    require(
        integer_model(str(MAX + 1).encode(), 0, 19, True) == integer_result(True, "out_of_range"),
        "signed maximum plus one",
    )
    for signed in (True, False):
        for status in range(len(STATUSES)):
            require(
                integer_shape(signed, status, 0, -1) == integer_result(signed, "invalid_window"),
                "negative forged error",
            )
        require(
            integer_shape(signed, S["invalid_window"], 1, MAX) == integer_result(signed, "invalid_window"),
            "invalid window masks all fields",
        )
    require(
        encoding_model(b"\xff" * 20, 20)[2:27] == (0, 0, *([255] * 20), 0, 0, 0),
        "forged payload shape is not spelling certification",
    )
    controls = 0
    for expected in (
        integer_result(True, "success", MIN),
        integer_result(False, "out_of_range", error=MAX),
        encoding_model(str(U64_MAX).encode(), 20),
    ):
        for index in range(len(expected)):
            for mask in (1, 1 << 32, 1 << 63):
                mutant = list(expected)
                mutant[index] ^= mask
                caught = False
                try:
                    compare(mutant, list(expected))
                except AssertionError:
                    caught = True
                require(caught, "full-width comparator mutation escaped")
                controls += 1
        for mutant in (list(expected[:-1]), [*expected, 0]):
            caught = False
            try:
                compare(mutant, list(expected))
            except AssertionError:
                caught = True
            require(caught, "observation length mutation escaped")
            controls += 1
    return controls


def oracle_audit():
    counts = dict(syntax_accepted=0, syntax_rejected=0, window_or_limit_excluded=0, exact_integer_values=0)
    # Both callbacks preserve spelling, so there is no host float, rounding,
    # infinity, or integral-float coercion anywhere in the independent audit.
    decoder = json.JSONDecoder(
        parse_int=lambda text: ("integer", text),
        parse_float=lambda text: ("form", text),
        parse_constant=lambda text: ("constant", text),
    )
    for case in parse_cases():
        data, offset, count = case.span(), case.offset, case.extent()
        report = integer_model(data, offset, count, False)
        if report[0] in (S["invalid_window"], S["number_limit"]):
            counts["window_or_limit_excluded"] += 1
            continue
        raw = data[offset : offset + count]
        accepted = False
        decoded = None
        try:
            decoded, end = decoder.raw_decode(raw.decode("ascii", "strict"))
            accepted = isinstance(decoded, tuple) and decoded[0] in ("integer", "form") and end == len(raw)
        except (ValueError, UnicodeError):
            pass
        require(accepted == (report[0] != S["invalid_number"]), "independent CPython exact grammar " + case.label)
        counts["syntax_accepted" if accepted else "syntax_rejected"] += 1
        if accepted:
            require(
                (decoded[0] == "form") == (report[0] == S["unsupported_number_form"]),
                "independent number form classification",
            )
            if decoded[0] == "integer":
                value = int(decoded[1], 10)
                for signed in (True, False):
                    observed = integer_model(data, offset, count, signed)
                    low, high = (MIN, MAX) if signed else (0, U64_MAX)
                    require((observed[0] == 0) == (low <= value <= high), "independent arbitrary precision range")
                    if observed[0] == 0:
                        require(observed[1:4] == (value & U64_MAX,) * 3, "independent arbitrary precision value")
                        counts["exact_integer_values"] += 1
    return counts


class Suite(profile.Suite):
    def __init__(self, args, identity):
        super().__init__(args, identity)
        self.hosted_observations = 0
        for name in (
            "tests/compiler/json_integers.py",
            "tests/compiler/json_codecs.py",
            "tests/compiler/owned_bytes.py",
            "tests/compiler/unsigned_oracle.py",
            "runtime/hosted_bytes.cpp",
            "runtime/hosted_bytes.hpp",
        ):
            self.inputs[name] = harness.sha(self.root / name)

    def batch(self, items, decimal_only=False):
        self.budget()
        directory = self.output / f"batch-{self.batches:04d}"
        directory.mkdir()
        self.batches += 1
        source = "module json_integer_test;import std.decimal;import std.array;\n"
        if not decimal_only:
            source += "import std.json;\n"
        source += (
            "auto signed_bits(i64 value)->u64{if(value<0){return 18446744073709551615u64-u64(-(value+1));}"
            "return u64(value);}\n"
        )
        source += f"auto encoding_index(i64 ordinal)->i64{{if(ordinal==0){{return {MIN};}}"
        source += f"if(ordinal==1){{return -1;}}if(ordinal=={len(INDICES) - 1}){{return {MAX};}}return ordinal-2;}}\n"
        for index, item in enumerate(items):
            source += item.helper.replace("_CASE", f"_{index}") + "\n"
            source += f"auto integer_case_{index}(i64 field)->u64{{" + item.body.replace("_CASE", f"_{index}") + "}\n"
        require(len(source.encode()) <= 65536, "generated source byte cap")
        (directory / "input.au").write_text(source)
        expected = [value for item in items for value in item.expected]
        receipt = dict(
            labels=[item.label for item in items],
            expected=expected,
            source_sha256=harness.sha(directory / "input.au"),
            status="running",
        )
        try:
            self.command(
                [
                    self.compiler,
                    "--module-root",
                    self.root / "library",
                    directory / "input.au",
                    "-o",
                    directory / "compiled.s",
                ],
                directory,
                "compiler",
            )
            entry = [".text", ".globl _start", "_start:"]
            for index, item in enumerate(items):
                for field in range(len(item.expected)):
                    entry += [
                        f"movq ${field},%rdi",
                        f"call integer_case_{index}",
                        "pushq %rax",
                        "movq $1,%rax",
                        "movq $1,%rdi",
                        "movq %rsp,%rsi",
                        "movq $8,%rdx",
                        "syscall",
                        "addq $8,%rsp",
                    ]
            entry += ["movq $60,%rax", "xorq %rdi,%rdi", "syscall", '.section .note.GNU-stack,"",@progbits']
            (directory / "entry.s").write_text("\n".join(entry) + "\n")
            self.command(["as", "--64", directory / "compiled.s", "-o", directory / "program.o"], directory, "assemble")
            self.command(["as", "--64", directory / "entry.s", "-o", directory / "entry.o"], directory, "entry")
            require(
                not self.command(["nm", "-u", directory / "program.o"], directory, "undefined-object").strip(),
                "unresolved runtime import",
            )
            self.command(
                ["ld", "-o", directory / "program", directory / "entry.o", directory / "program.o"], directory, "link"
            )
            require(
                not self.command(["nm", "-u", directory / "program"], directory, "undefined-native").strip(),
                "unresolved native import",
            )
            output = self.command([directory / "program"], directory, "native")
            require(len(output) == 8 * len(expected), "exact full 64-bit native output length")
            observed = [int.from_bytes(output[i : i + 8], "little", signed=False) for i in range(0, len(output), 8)]
            receipt.update(observed=observed, output_sha256=hashlib.sha256(output).hexdigest())
            compare(observed, expected)
            receipt["status"] = "passed"
            self.count += len(items)
            self.observations += len(expected)
        except Exception as error:
            receipt.update(status="failed", error=str(error))
            raise
        finally:
            (directory / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(
            f"PASS JSON integer batch {self.batches}: {len(items)} cases, {len(expected)} full 64-bit observations",
            flush=True,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler_pos", nargs="?", type=pathlib.Path)
    parser.add_argument("--compiler", type=pathlib.Path)
    parser.add_argument("--developer-selected-compiler", action="store_true")
    harness.add_identity_arguments(parser)
    parser.add_argument("--repo-root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--artifacts", type=pathlib.Path)
    parser.add_argument("--budget-root", type=pathlib.Path)
    parser.add_argument("--budget-mib", type=int, default=512)
    parser.add_argument("--sanitized-compiler", action="store_true")
    parser.add_argument("--self-test-only", action="store_true")
    parser.add_argument("--describe", action="store_true")
    args = parser.parse_args()
    require(not (args.compiler and args.compiler_pos), "select one compiler path")
    args.compiler = args.compiler or args.compiler_pos
    if args.developer_selected_compiler:
        require(
            args.compiler_sha256 is None and args.developer_build_receipt is None,
            "developer-selected compiler cannot claim pin or build receipt",
        )
        require(not os.environ.get("AURORA_TEST_CONTEXT"), "developer-selected compiler cannot enter aggregate")
    else:
        harness.validate_identity_selection(args, preflight=args.self_test_only or args.describe)
    controls, audit = self_test(), oracle_audit()
    if args.self_test_only:
        print(
            f"PASS JSON integer independent grammar/int/str oracles: {controls} comparator mutation controls; "
            + json.dumps(audit, sort_keys=True)
        )
        return
    source = (args.repo_root / "library/std/json.au").read_text()
    decimal_source = (args.repo_root / "library/std/decimal.au").read_text()
    if args.describe:
        groups = [*profile.batches(all_tests()), list(decimal_only_tests())]
        print(
            json.dumps(
                dict(
                    cases=sum(map(len, groups)),
                    batches=len(groups),
                    full_64bit_observations=sum(len(item.expected) for group in groups for item in group),
                    rejections=len(list(rejections(source, decimal_source))),
                    compiler_free_mutation_controls=controls,
                    independent_grammar_audit=audit,
                    random_seed=SEED,
                    budget_mib=args.budget_mib,
                ),
                indent=2,
            )
        )
        return
    require(args.compiler is not None, "compiler required")
    if args.artifacts is None:
        args.artifacts = pathlib.Path(tempfile.mkdtemp(prefix="aurora-json-integers-")) / "gate"
        print("Retained JSON integer artifacts: " + str(args.artifacts), flush=True)
    require(32 <= args.budget_mib <= 1024, "artifact budget must be 32..1024 MiB")
    args.sanitized_compiler = args.sanitized_compiler or any(
        flag.startswith("-fsanitize=") for flag in selected_flag_vectors(os.environ)["CXXFLAGS"]
    )
    identity = (
        SelectedCompiler(args.compiler)
        if args.developer_selected_compiler
        else harness.resolve_identity(args, args.compiler, args.repo_root)
    )
    suite = Suite(args, identity)
    manifest = dict(
        compiler_identity=identity.record(),
        compiler_sha256=suite.pin,
        inputs=suite.inputs,
        python=sys.version,
        optimized=not __debug__,
        status="running",
        random_seed=SEED,
        native_semantic_mutations=0,
        compiler_free_mutation_controls=controls,
        independent_grammar_audit=audit,
        limits=[
            "Focused integer/encoding gate, not complete native or sanitizer qualification",
            "Fixed-array sources cover at most 4096 bytes; separate hosted owner fixtures reach 8192 bytes",
            "Public constructors certify shape, not source provenance or canonical decimal payload",
            "Roundtrips supplement independent Python integer and spelling observations",
        ],
    )
    try:
        for group in profile.batches(all_tests()):
            suite.batch(group)
        suite.batch(list(decimal_only_tests()), decimal_only=True)
        for item in rejections(source, decimal_source):
            suite.reject(*item)
        hosted_tests(suite)
        suite.verify_inputs()
        identity.verify()
        manifest.update(
            status="passed",
            cases=suite.count,
            full_64bit_observations=suite.observations,
            batches=suite.batches,
            rejections=suite.rejections,
            hosted_observations=suite.hosted_observations,
        )
    except Exception as error:
        manifest.update(status="failed", error=str(error))
        raise
    finally:
        identity_errors = finalize_selected_identity(identity, manifest)
        manifest["compiler_identity"] = identity.record()
        manifest.update(
            completed_cases=suite.count,
            completed_rejections=suite.rejections,
            completed_hosted_observations=suite.hosted_observations,
            allocated_bytes=suite.budget(0),
        )
        (suite.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        require(not identity_errors, "; ".join(identity_errors))


if __name__ == "__main__":
    main()
