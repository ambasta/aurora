#!/usr/bin/env python3
"""Focused JSON scalar codecs, with independent CPython Unicode/JSON oracles.

Every status, scalar/fallback, extent, coordinate and byte is observed as a whole
64-bit native value. Generated sources, outputs, identities and failures remain.
This is neither complete native qualification nor sanitizer qualification.
"""

from __future__ import annotations

import argparse
import codecs
import hashlib
import itertools
import json
import os
import pathlib
import random
import re
import shlex
import sys
import tempfile

sys.dont_write_bytecode = True
import json_profile as profile
import owned_bytes
from compiler_contract import selected_flag_vectors
from package_profiles import SelectedCompiler, finalize_selected_identity

harness = profile.harness
require = harness.require
MIN, MAX = harness.MIN, harness.MAX
U64_MAX = (1 << 64) - 1
S, STATUSES = profile.S, profile.STATUSES
Case, Test, SPAN = profile.Case, profile.Test, profile.SPAN
INDICES = (MIN, -1, 0, 1, 2, 3, 4, 5, 6, MAX)
FALLBACKS = (0, 165, 255)
SHORT = {34: b'\\"', 92: b"\\\\", 8: b"\\b", 12: b"\\f", 10: b"\\n", 13: b"\\r", 9: b"\\t"}


def valid_scalar(value):
    return 0 <= value <= 0x10FFFF and not 0xD800 <= value <= 0xDFFF


def scalar_failure(status, position=0):
    return (S[status], 0, U64_MAX, 0, position)


def scalar_success(value, width):
    return (0, value, value, width, 0)


def decode_model(data, offset, count):
    """Recognize one scalar; CPython handles UTF-8 and decoded escape values."""
    if offset < 0 or count < 0 or offset > len(data) or count > len(data) - offset:
        return scalar_failure("invalid_window")
    raw = bytes(data[offset : offset + min(count, 12)])
    if count == 0:
        return scalar_failure("end_of_input")
    if raw[0] < 32 or raw[0] == 34:
        return scalar_failure("invalid_string", offset)
    if raw[0] != 92:
        decoder = codecs.getincrementaldecoder("utf-8")("strict")
        try:
            for width, byte in enumerate(raw, 1):
                decoded = decoder.decode(bytes([byte]), final=False)
                if decoded:
                    require(len(decoded) == 1, "incremental one-scalar oracle")
                    return scalar_success(ord(decoded), width)
            decoder.decode(b"", final=True)
        except UnicodeDecodeError as error:
            return scalar_failure(
                "truncated" if error.reason == "unexpected end of data" else "invalid_string",
                offset + count if error.reason == "unexpected end of data" else offset,
            )
        raise AssertionError("nonempty UTF-8 input must finish or fail")
    if len(raw) == 1:
        return scalar_failure("truncated", offset + count)
    if raw[1] in b'"\\/bfnrt':
        return scalar_success(ord(json.loads(b'"' + raw[:2] + b'"')), 2)
    if raw[1] != 117:
        return scalar_failure("invalid_string", offset + 1)
    # Diagnose a code-unit spelling independently before asking json.loads for
    # the value. CPython intentionally accepts lone surrogates; this API does not.
    for index in range(2, 6):
        if index >= len(raw):
            return scalar_failure("truncated", offset + count)
        if raw[index] not in b"0123456789abcdefABCDEF":
            return scalar_failure("invalid_string", offset + index)
    unit = int(raw[2:6], 16)
    if 0xDC00 <= unit <= 0xDFFF:
        return scalar_failure("invalid_string", offset)
    width = 6
    if 0xD800 <= unit <= 0xDBFF:
        if len(raw) == 6 or raw[6:] == b"\\":
            return scalar_failure("truncated", offset + count)
        if not raw[6:].startswith(b"\\u"):
            return scalar_failure("invalid_string", offset)
        for index in range(8, 12):
            if index >= len(raw):
                return scalar_failure("truncated", offset + count)
            if raw[index] not in b"0123456789abcdefABCDEF":
                return scalar_failure("invalid_string", offset + index)
        if not 0xDC00 <= int(raw[8:12], 16) <= 0xDFFF:
            return scalar_failure("invalid_string", offset)
        width = 12
    decoded = json.loads(b'"' + raw[:width] + b'"')
    require(len(decoded) == 1 and valid_scalar(ord(decoded)), "strict JSON escape oracle")
    return scalar_success(ord(decoded), width)


def escape_bytes(value):
    if not valid_scalar(value):
        return None
    # CPython supplies the canonical JSON spelling, including lowercase hex and
    # the standard short escapes. Its default slash spelling is deliberately raw.
    return json.dumps(chr(value), ensure_ascii=False)[1:-1].encode("utf-8", "strict")


def escape_model(status, data, width):
    good = status == 0 and 1 <= width <= 6
    result = [0 if good else 1, width if good else 0]
    for fallback in FALLBACKS:
        result += [data[i] if good and 0 <= i < width else fallback for i in INDICES]
    return tuple(result)


def observe_scalar():
    body = "if(field==0){"
    for number, status in enumerate(STATUSES):
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
    for field, (fallback, index) in enumerate(itertools.product(FALLBACKS, INDICES), 2):
        body += f"if(field=={field}){{return u64(report.byte_or({index},{fallback}u8));}}"
    return body + f"return {U64_MAX - 2}u64;"


def decode_test(case):
    helper = f"auto input_CASE({SPAN} bytes)->std::JsonScalarResult{{"
    parent = "bytes"
    for i, (start, size) in enumerate(case.windows):
        name = f"view{i}"
        helper += f"const {SPAN} {name}={parent}.subspan({start},{size});"
        parent = name
    helper += f"const std::JsonScalarResult r=std::decode_json_string_scalar({parent},{case.offset},{case.extent()});"
    helper += "return r;}"
    body = harness.array(case.data) + f"const builtin::array<u8,{max(1, len(case.data))}> saved=owner;"
    body += "const std::JsonScalarResult original=input_CASE(borrow_bytes(owner));"
    body += f"i64 i=0;while(i<len(owner)){{if(owner[i]!=saved[i]){{return {U64_MAX - 3}u64;}}i=i+1;}}"
    body += "owner[0]=0u8;const std::JsonScalarResult report=original;" + observe_scalar()
    return Test(case.label, body, decode_model(case.span(), case.offset, case.extent()), helper)


def decode_cases():
    for byte in range(256):
        yield Case("every initial byte", bytes([byte]))
        yield Case("every short escape code", bytes([92, byte]))
    scalars = (
        0,
        8,
        9,
        10,
        12,
        13,
        31,
        32,
        34,
        47,
        92,
        127,
        128,
        0x7FF,
        0x800,
        0xD7FF,
        0xE000,
        0xFFFF,
        0x10000,
        0x10FFFF,
        0xFEFF,
        0xFDD0,
        0x378,
        0x301,
        0x200D,
        0x1F642,
    )
    for value in scalars:
        spellings = {chr(value).encode(), escape_bytes(value), json.dumps(chr(value), ensure_ascii=True)[1:-1].encode()}
        for raw in sorted(spellings):
            for end in range(len(raw) + 1):
                yield Case("every Unicode and escape cut", b"\xff" + raw + b"\xff", 1, end)
            yield Case("one scalar ignores malformed trailing content", raw + b'\xff"\\uD800\x00')
            yield Case(
                "nested span-relative coordinates",
                b"\xff!?" + raw + b"\xff",
                1,
                len(raw),
                ((1, len(raw) + 3), (1, len(raw) + 2)),
            )
    malformed = (
        b"\\",
        b"\\u",
        b"\\u000g",
        b"\\ud800",
        b"\\ud800x",
        b"\\ud800\\",
        b"\\ud800\\x",
        b"\\ud800\\u",
        b"\\ud800\\u0000",
        b"\\ud800\\ud800",
        b"\\udc00",
        b"\\uDFFF",
        b"\\uDBFF\\uDFFF",
        b"\\uD800\\uDC00",
        b"\\uD800\\uDC0G",
        b"\\uD800\\uG000",
        b"\xc0\x80",
        b"\xc1\xbf",
        b"\xc2A",
        b"\xe0\x9f\xbf",
        b"\xed\xa0\x80",
        b"\xf0\x8f\xbf\xbf",
        b"\xf4\x90\x80\x80",
        b"\xf5\x80\x80\x80",
        b"\xe2\x82",
        b"\xf0\x90\x80",
    )
    for raw in malformed:
        for end in range(len(raw) + 1):
            yield Case("malformed and viable prefix diagnostics", b"\xff" + raw + b"\xff", 1, end)
    for raw in (b"A\xc2\xa2\xe2\x82\xac\xf0\x9f\x99\x82Z", b"\\uD834\\uDD1eA"):
        for offset in range(len(raw) + 1):
            for count in range(len(raw) - offset + 1):
                yield Case("every mixed sequence byte window", raw, offset, count)
    for offset, count in itertools.product((MIN, -1, 0, 1, 2, 12, 4096, 4097, MAX), repeat=2):
        yield Case("signed window validation precedence", b"\xff", offset, count)
    for offset, count in ((0, 0), (0, 1), (1, 0), (MIN, MAX), (MAX, MAX)):
        yield Case("actual empty nested span", b"\xff", offset, count, ((1, 0), (0, 0)))
    yield Case("maximum source owner does constant single-scalar work", b"A" + b"\xff" * 4095)
    yield Case("maximum owner final scalar coordinate", b"\xff" * 4092 + chr(0x10FFFF).encode(), 4092, 4)
    rng = random.Random(20261008)
    for _ in range(100):
        raw = bytes(rng.randrange(256) for _ in range(rng.randrange(17)))
        yield Case("seeded arbitrary scalar prefixes", raw or b"\xff", 0, len(raw))


def scalar_shape_model(status, scalar, width, error):
    if status == S["invalid_window"]:
        return scalar_failure("invalid_window")
    if status == 0 and valid_scalar(scalar) and 1 <= width <= 12 and error == 0:
        return scalar_success(scalar, width)
    if scalar == width == 0 and error >= 0:
        if status == S["end_of_input"] and error == 0:
            return scalar_failure("end_of_input")
        if status in (S["invalid_string"], S["truncated"]):
            return scalar_failure(STATUSES[status], error)
    return scalar_failure("invalid_window")


def scalar_shapes():
    seeds = ((0, 0, 1, 0), (0, 0x10FFFF, 12, 0), (1, 0, 0, 0), (S["invalid_string"], 0, 0, 9))
    rows = set(seeds)
    for seed in seeds:
        for field, values in (
            (0, range(len(STATUSES))),
            (1, (0, 1, 0xD7FF, 0xD800, 0xDFFF, 0xE000, 0x10FFFF, 0x110000, MAX, MAX + 1, U64_MAX)),
            (2, (MIN, -1, 0, 1, 4, 6, 12, 13, MAX)),
            (3, (MIN, -1, 0, 1, MAX)),
        ):
            for value in values:
                row = list(seed)
                row[field] = value
                rows.add(tuple(row))
    for status, scalar, width, error in sorted(rows):
        body = f"const std::JsonScalarResult original=std::JsonScalarResult(std::JsonStatus::{STATUSES[status]},"
        body += f"{scalar}u64,{width},{error});const std::JsonScalarResult report=original;" + observe_scalar()
        yield Test(
            "forged scalar report normalizes shape and masks payload",
            body,
            scalar_shape_model(status, scalar, width, error),
        )


def stored_array(data):
    return "std::array<u8,6> stored=std::array<u8,6>();" + "".join(
        f"stored.set({i},{byte}u8);" for i, byte in enumerate(data)
    )


def escape_tests():
    rng = random.Random(71829)
    values = set(range(160)) | {
        0x7FE,
        0x7FF,
        0x800,
        0x801,
        0xD7FF,
        0xD800,
        0xDBFF,
        0xDC00,
        0xDFFF,
        0xE000,
        0xFFFE,
        0xFFFF,
        0x10000,
        0x10FFFF,
        0x110000,
        1 << 32,
        MAX,
        MAX + 1,
        U64_MAX,
    }
    values.update(rng.randrange(0x110000) for _ in range(100))
    for value in sorted(values):
        data = escape_bytes(value)
        body = f"const std::JsonEscapeResult original=std::escape_json_scalar({value}u64);"
        body += "const std::JsonEscapeResult report=original;" + observe_escape()
        yield Test(
            "canonical escape and exact byte fallbacks",
            body,
            escape_model(1 if data is None else 0, data or b"", len(data or b"")),
        )
    for status, width, data in itertools.product(
        (0, 1), (MIN, -1, 0, 1, 2, 3, 4, 5, 6, 7, MAX), (bytes(6), b"ABCDEF", b"\xff" * 6, b"\xc0\x80\xed\xa0\x80\x00")
    ):
        body = stored_array(data)
        body += "const std::JsonEscapeResult original=std::JsonEscapeResult(std::JsonEscapeStatus::"
        body += f"{'success' if status == 0 else 'invalid_scalar'},stored,{width});"
        body += "const std::JsonEscapeResult report=original;stored.set(0,17u8);stored.set(5,18u8);"
        yield Test(
            "copied escape reports validate shape without certifying forged bytes",
            body + observe_escape(),
            escape_model(status, data, width),
        )


def lifetime_tests():
    for raw in (b"A", b"\\u0000", b"\\uD834\\uDD1E", b"\xf4\x8f\xbf\xbf", b"\\x"):
        helper = "auto expired_CASE()->std::JsonScalarResult{" + harness.array(raw)
        helper += f"const std::JsonScalarResult r=std::decode_json_string_scalar(borrow_bytes(owner),0,{len(raw)});"
        helper += "return r;}"
        body = "const std::JsonScalarResult original=expired_CASE();const std::JsonScalarResult report=original;"
        yield Test(
            "scalar report outlives its source owner", body + observe_scalar(), decode_model(raw, 0, len(raw)), helper
        )
    for value in (0, 34, 92, 0x80, 0x10FFFF, U64_MAX):
        helper = "auto expired_CASE()->std::JsonEscapeResult{"
        helper += f"const std::JsonEscapeResult r=std::escape_json_scalar({value}u64);return r;}}"
        body = "const std::JsonEscapeResult original=expired_CASE();const std::JsonEscapeResult report=original;"
        data = escape_bytes(value)
        yield Test(
            "escape report outlives factory scope",
            body + observe_escape(),
            escape_model(1 if data is None else 0, data or b"", len(data or b"")),
            helper,
        )


def roundtrip_tests():
    for value in (
        0,
        1,
        8,
        9,
        10,
        12,
        13,
        31,
        32,
        34,
        47,
        92,
        127,
        128,
        0x7FF,
        0x800,
        0xD7FF,
        0xE000,
        0xFFFF,
        0x10000,
        0x10FFFF,
        0xFEFF,
        0xFDD0,
        0x1F642,
    ):
        body = f"const std::JsonEscapeResult escaped=std::escape_json_scalar({value}u64);"
        body += "builtin::array<u8,6> owner={0u8,0u8,0u8,0u8,0u8,0u8};i64 i=0;"
        body += "while(i<escaped.size()){owner[i]=escaped.byte_or(i,255u8);i=i+1;}"
        body += (
            "const std::JsonScalarResult report=std::decode_json_string_scalar(borrow_bytes(owner),0,escaped.size());"
        )
        yield Test(
            "factory roundtrip complements independent byte oracle",
            body + observe_scalar(),
            scalar_success(value, len(escape_bytes(value))),
        )


def all_tests():
    yield from map(decode_test, decode_cases())
    yield from scalar_shapes()
    yield from escape_tests()
    yield from lifetime_tests()
    yield from roundtrip_tests()


def rejections(source):
    head = "module rejection;import std.json;import std.array;"
    scalar = "const std::JsonScalarResult r=std::JsonScalarResult(std::JsonStatus::success,65u64,1,0);"
    escape = "const std::JsonEscapeResult r=std::escape_json_scalar(65u64);"
    for cls, setup, arity in (("JsonScalarResult", scalar, 4), ("JsonEscapeResult", escape, 3)):
        block = re.search(r"class " + cls + r"\s*\{(.*?)public:", source, re.S)
        require(block is not None, "codec class declaration")
        fields = re.findall(r"(?:JsonStatus|JsonEscapeStatus|u64|i64|std::array<u8,\s*6>)\s+(\w+)\s*;", block.group(1))
        require(len(fields) == arity, "private codec field count")
        for field in fields:
            yield ("private codec field", head + "auto test()->u64{" + setup + f"return r.{field};}}", "private")
    for function in sorted(set(re.findall(r"\bauto\s+(json_\w+)\s*\(", source))):
        yield (
            "private JSON helper",
            head + f"auto test()->u64{{return std::{function}();}}",
            "private function is not imported",
        )
    for value in ("65", "65u8", "false"):
        yield (
            "escape exact u64 scalar",
            head + f"auto test()->u64{{const std::JsonEscapeResult r=std::escape_json_scalar({value});return 0u64;}}",
            "expected u64",
        )
        yield (
            "scalar exact u64 fallback",
            head + "auto test()->u64{" + scalar + f"return r.scalar_or({value});}}",
            "expected u64",
        )
    for index in ("0u64", "0u8", "false"):
        yield (
            "escape exact signed index",
            head + "auto test()->u64{" + escape + f"return u64(r.byte_or({index},0u8));}}",
            "expected i64",
        )
    for fallback in ("0", "0u64", "false"):
        yield (
            "escape exact byte fallback",
            head + "auto test()->u64{" + escape + f"return u64(r.byte_or(0,{fallback}));}}",
            "expected u8",
        )
    for args in ("0u64,1", "0,1u64", "0u8,1", "0,1u8", "false,1", "0,false"):
        yield (
            "decode exact signed window",
            head
            + "auto test()->u64{builtin::array<u8,1> b={65u8};"
            + f"const std::JsonScalarResult r=std::decode_json_string_scalar(borrow_bytes(b),{args});return 0u64;}}",
            "expected i64",
        )
    for arguments in (
        "std::JsonStatus::success,65,1,0",
        "std::JsonStatus::success,65u64,1u64,0",
        "std::JsonStatus::success,65u64,1,0u64",
        "0,65u64,1,0",
    ):
        yield (
            "scalar constructor exact nominal types",
            head
            + "auto test()->u64{"
            + f"const std::JsonScalarResult r=std::JsonScalarResult({arguments});return 0u64;}}",
            "expected",
        )
    for wrong in ("std::array<u8,5>", "std::array<u64,6>"):
        yield (
            "escape constructor exact payload shape",
            head
            + f"auto test()->u64{{const {wrong} b={wrong}();"
            + "const std::JsonEscapeResult r=std::JsonEscapeResult(std::JsonEscapeStatus::success,b,1);return 0u64;}",
            "expected std::array<u8,6>",
        )
    yield (
        "decode live borrow bars mutation",
        head
        + "auto test()->u64{builtin::array<u8,1> b={65u8};"
        + f"const {SPAN} v=borrow_bytes(b);const std::JsonScalarResult r=std::decode_json_string_scalar(v,0,1);"
        + "b[0]=0u8;return r.scalar_or(0u64);}",
        "span is live",
    )
    yield (
        "decode requires span",
        head
        + "auto test()->u64{builtin::array<u8,1> b={65u8};"
        + "const std::JsonScalarResult r=std::decode_json_string_scalar(b,0,1);return 0u64;}",
        "span",
    )
    yield (
        "copied codec contains no escaped source view",
        head + f"class Bad{{{SPAN} retained;}};auto test()->u64{{return 0u64;}}",
        "class fields require",
    )


class Suite(profile.Suite):
    def __init__(self, args, identity):
        super().__init__(args, identity)
        self.hosted_observations = 0
        for name in (
            "tests/compiler/json_codecs.py",
            "tests/compiler/owned_bytes.py",
            "tests/compiler/unsigned_oracle.py",
            "runtime/hosted_bytes.cpp",
            "runtime/hosted_bytes.hpp",
        ):
            self.inputs[name] = harness.sha(self.root / name)

    def batch(self, items):
        self.budget()
        directory = self.output / f"batch-{self.batches:04d}"
        directory.mkdir()
        self.batches += 1
        source = "module json_codecs_test;import std.json;import std.array;\n"
        for index, item in enumerate(items):
            source += item.helper.replace("_CASE", f"_{index}") + "\n"
            source += f"auto json_case_{index}(i64 field)->u64{{" + item.body.replace("_CASE", f"_{index}") + "}\n"
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
                        f"call json_case_{index}",
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
            require(len(output) == 8 * len(expected), "exact complete native observation length")
            observed = [int.from_bytes(output[i : i + 8], "little", signed=False) for i in range(0, len(output), 8)]
            receipt.update(observed=observed, output_sha256=hashlib.sha256(output).hexdigest())
            require(
                observed == expected,
                f"native mismatch {[(i, a, b) for i, (a, b) in enumerate(zip(observed, expected)) if a != b][:16]}",
            )
            receipt["status"] = "passed"
            self.count += len(items)
            self.observations += len(expected)
        except Exception as error:
            receipt.update(status="failed", error=str(error))
            raise
        finally:
            (directory / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(
            f"PASS JSON codec batch {self.batches}: {len(items)} cases, {len(expected)} full 64-bit observations",
            flush=True,
        )


def hosted_compile(suite, name, source, entry_name):
    directory = suite.output / name
    directory.mkdir()
    (directory / "input.au").write_text(source)
    assembly = directory / "compiled.s"
    suite.command(
        [suite.compiler, "--module-root", suite.root / "library", directory / "input.au", "-o", assembly],
        directory,
        "compiler",
    )
    text = assembly.read_text()
    symbols = re.findall(r"^\.type ([A-Za-z_][A-Za-z_0-9]*), @function$", text, re.M)
    matching = [
        symbol for symbol in symbols if symbol == entry_name or symbol.endswith(f"__d{len(entry_name)}{entry_name}")
    ]
    require(len(matching) == 1, "one hosted example entry")
    require(f".local {matching[0]}\n" in text, "hosted resource entry remains private")
    (directory / "bridged.s").write_text(owned_bytes.bridged_assembly(text, matching[0]))
    (directory / "driver.cpp").write_text(owned_bytes.DRIVER)
    cxx = shlex.split(os.environ.get("CXX", "g++"))
    flags = selected_flag_vectors(os.environ)["CXXFLAGS"]
    suite.command(
        [
            *cxx,
            *flags,
            "-I",
            suite.root,
            directory / "driver.cpp",
            suite.root / "runtime/hosted_bytes.cpp",
            directory / "bridged.s",
            "-o",
            directory / "program",
        ],
        directory,
        "host-link",
    )
    return directory


def hosted_observe(suite, directory, label, quota, n, observation, expected, allocations, peak, fail_after=None):
    argv = [directory / "program", quota, n, observation]
    if fail_after is not None:
        argv.append(fail_after)
    name = f"observation-{suite.hosted_observations:04d}"
    receipt = dict(label=label, expected=[expected & U64_MAX, allocations, allocations, peak], status="running")
    try:
        output = suite.command(argv, directory, name)
        actual = [int(part) for part in output.split()]
        receipt["observed"] = actual
        require(actual[:4] == receipt["expected"], f"{label}: hosted result/allocation mismatch {actual}")
        require(sorted(actual[4:]) == list(range(1, allocations + 1)), "every allocation released exactly once")
        receipt["status"] = "passed"
        suite.hosted_observations += 1
    except Exception as error:
        receipt.update(status="failed", error=str(error))
        raise
    finally:
        (directory / (name + "-observation.json")).write_text(json.dumps(receipt, indent=2) + "\n")


def hosted_tests(suite):
    example_source = (suite.root / "library/examples/json_codecs.au").read_text()
    block = re.search(r"source\s*=\s*\{(.*?)\};", example_source, re.S)
    require(block is not None, "example byte fixture")
    raw = bytes(map(int, re.findall(r"(\d+)u8", block.group(1))))
    decoded_text = json.loads(raw.decode("utf-8", "strict"))
    decoded = decoded_text.encode("utf-8", "strict")
    escaped = json.dumps(decoded_text, ensure_ascii=False, separators=(",", ":")).encode("utf-8", "strict")
    require(len(decoded) == 12 and len(escaped) == 22, "example independent decoded and escaped sizes")
    combined = decoded + escaped
    directory = hosted_compile(suite, "hosted-example", example_source, "json_codecs_example")
    for initial in (0, 1, 11, 12, 21, 22, 32):
        allocations = 2 + (initial < len(decoded)) + (initial < len(escaped))
        for observation in (MIN, -7, -3, -2, -1, *range(len(combined) + 1), MAX):
            expected = {-1: len(decoded), -2: len(escaped)}.get(
                observation, combined[observation] if 0 <= observation < len(combined) else 256
            )
            hosted_observe(
                suite,
                directory,
                "example exact output and extreme observation",
                128,
                initial,
                observation,
                expected,
                allocations,
                2,
            )
    for quota, initial, fail_after, expected, allocations, peak in (
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
        hosted_observe(
            suite,
            directory,
            "example real allocation and quota failure cleanup",
            quota,
            initial,
            -1,
            expected,
            allocations,
            peak,
            fail_after,
        )
    # A preexisting prefix proves failed per-scalar reserve leaves size, capacity
    # and all readable bytes unchanged. There is no cross-buffer atomicity claim.
    source = """module json_append_test;
import std.json;import std.array;import std.binary;import std.byte_buffer;
auto json_append_test(builtin::ByteRegion region,i64 scalar_input,i64 observation)->i64{
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
    directory = hosted_compile(suite, "hosted-scalar-append", source, "json_append_test")
    for scalar in (-1, 0, 34, 65, 0x1F600):
        encoded = escape_bytes(scalar)
        for quota, fail_after in ((128, None), (2, None), (128, 1)):
            success = encoded is not None and quota == 128 and fail_after is None
            expected_bytes = b"AB" + (encoded if success else b"")
            expected_capacity = len(expected_bytes)
            allocations = 2 if success else 1
            for observation in (MIN, -3, -2, -1, *range(len(expected_bytes) + 1), MAX):
                expected = {-1: int(success), -2: len(expected_bytes), -3: expected_capacity}.get(
                    observation, expected_bytes[observation] if 0 <= observation < len(expected_bytes) else 256
                )
                hosted_observe(
                    suite,
                    directory,
                    "per-scalar reserve-before-append state and failure atomicity",
                    quota,
                    scalar,
                    observation,
                    expected,
                    allocations,
                    1,
                    fail_after,
                )
    print(f"PASS JSON hosted composition: {suite.hosted_observations} results with real allocation cleanup", flush=True)


def self_test():
    require(decode_model(b"\\uD834\\uDD1EX", 0, 13) == scalar_success(0x1D11E, 12), "surrogate scalar value")
    require(decode_model(b"\xff\\u0x00", 1, 6) == scalar_failure("invalid_string", 4), "escape error coordinate")
    require(decode_model(b"\xff\\uD800\\", 1, 7) == scalar_failure("truncated", 8), "viable surrogate cutoff")
    require(decode_model(b"\xff\xe0\x9f", 1, 2) == scalar_failure("invalid_string", 1), "impossible Unicode prefix")
    require(decode_model(b"\xff\xe0\xa0", 1, 2) == scalar_failure("truncated", 3), "viable Unicode cutoff")
    require(decode_model(b"A\xff", 0, 2) == scalar_success(65, 1), "remaining input is not validated")
    require(decode_model(b"\xff", MIN, MAX) == scalar_failure("invalid_window"), "subtraction-first window")
    for value, spelling in SHORT.items():
        require(escape_bytes(value) == spelling, "canonical short spelling")
    require(escape_bytes(31) == b"\\u001f" and escape_bytes(47) == b"/", "lowercase hex and raw slash")
    require(escape_bytes(U64_MAX) is None, "fullwidth invalid scalar")
    good = scalar_failure("invalid_string", MAX)
    for field in range(len(good)):
        mutation = list(good)
        mutation[field] ^= 1
        caught = False
        try:
            require(tuple(mutation) == good, "deliberate comparison mutation")
        except AssertionError:
            caught = True
        require(caught, "fullwidth observation mutation detected")


def oracle_audit():
    counts = dict(success=0, rejected=0, window_or_empty=0)
    for case in decode_cases():
        result = decode_model(case.span(), case.offset, case.extent())
        if result[0] in (S["invalid_window"], S["end_of_input"]):
            counts["window_or_empty"] += 1
            continue
        raw = case.span()[case.offset : case.offset + case.extent()]
        matches = []
        # A separate exhaustive prefix-wrapper test audits success/failure
        # classification without depending on diagnostic-selection logic above.
        for width in range(1, min(12, len(raw)) + 1):
            try:
                text = json.loads((b'"' + raw[:width] + b'"').decode("utf-8", "strict"))
            except (ValueError, UnicodeError):
                continue
            if len(text) == 1 and valid_scalar(ord(text)):
                matches.append((ord(text), width))
        require(bool(matches) == (result[0] == 0), "independent JSON prefix acceptance: " + case.label)
        if matches:
            require(matches[0] == (result[1], result[3]), "independent JSON prefix value and consumption")
        counts["success" if matches else "rejected"] += 1
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler_pos", nargs="?", type=pathlib.Path)
    parser.add_argument("--compiler", type=pathlib.Path)
    parser.add_argument("--developer-selected-compiler", action="store_true")
    harness.add_identity_arguments(parser)
    parser.add_argument("--repo-root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--artifacts", type=pathlib.Path)
    parser.add_argument("--budget-root", type=pathlib.Path)
    parser.add_argument("--budget-mib", type=int, default=256)
    parser.add_argument("--sanitized-compiler", action="store_true")
    parser.add_argument("--self-test-only", action="store_true")
    parser.add_argument("--describe", action="store_true")
    args = parser.parse_args()
    require(not (args.compiler and args.compiler_pos), "select one compiler path")
    args.compiler = args.compiler or args.compiler_pos
    if args.developer_selected_compiler:
        require(
            args.compiler_sha256 is None and args.developer_build_receipt is None,
            "developer-selected compiler cannot claim a pin or fresh-build receipt",
        )
        require(not os.environ.get("AURORA_TEST_CONTEXT"), "developer-selected compiler cannot enter aggregate")
    else:
        harness.validate_identity_selection(args, preflight=args.self_test_only or args.describe)
    self_test()
    audit = oracle_audit()
    if args.self_test_only:
        print("PASS JSON scalar codec independent Unicode/JSON and comparator controls")
        return
    if args.describe:
        groups = list(profile.batches(all_tests()))
        print(
            json.dumps(
                dict(
                    cases=sum(map(len, groups)),
                    batches=len(groups),
                    complete_64bit_observations=sum(len(i.expected) for g in groups for i in g),
                    rejections=len(list(rejections((args.repo_root / "library/std/json.au").read_text()))),
                    independent_prefix_audit=audit,
                    budget_mib=args.budget_mib,
                ),
                indent=2,
            )
        )
        return
    require(args.compiler is not None, "compiler required")
    if args.artifacts is None:
        args.artifacts = pathlib.Path(tempfile.mkdtemp(prefix="aurora-json-codecs-")) / "gate"
        print("Retained JSON codec artifacts: " + str(args.artifacts), flush=True)
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
        native_semantic_mutations=0,
        independent_prefix_audit=audit,
        limits=[
            "Focused codec gate, not full native or sanitizer qualification",
            "Valid source-created spans cover at most 4096 bytes under the fixed-owner limit",
            "Public result constructors certify shape, not byte spelling or source provenance",
        ],
    )
    try:
        for group in profile.batches(all_tests()):
            suite.batch(group)
        for item in rejections((args.repo_root / "library/std/json.au").read_text()):
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
