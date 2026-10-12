#!/usr/bin/env python3
"""Bounded native JSON profile; independent Python grammar/Unicode oracle.

Complete i64 observations, generated sources, tool logs and identity are retained.
Python's decoder is used only with explicit strict UTF-8 and surrogate checks.
This gate is focused evidence, not full native or sanitizer qualification.
"""

from __future__ import annotations
import argparse, dataclasses, hashlib, itertools, os, pathlib, random, re, sys
import json

sys.dont_write_bytecode = True
import utf8_range as harness
from compiler_contract import selected_flag_vectors
from package_profiles import SelectedCompiler, finalize_selected_identity

require = harness.require
MIN, MAX = harness.MIN, harness.MAX
STATUSES = (
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
KINDS = (
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
S = {v: i for i, v in enumerate(STATUSES)}
K = {v: i for i, v in enumerate(KINDS)}
WS = b"\x09\x0a\x0d "
PUNCT = b"{}[]:,"
NUMBER = re.compile(rb"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
SPAN = "builtin::span<const u8>"


def failed(status, at):
    return (S[status], 0, 0, 0, 0, at)


def string_end(raw, start):
    """Use strict Python scalar decoding and independent escape recognition."""
    i = start + 1
    while i < len(raw):
        c = raw[i]
        if c == 34:
            # A successful token must also agree with the standard decoder.
            decoded = json.loads(raw[start : i + 1].decode("utf-8", "strict"))
            require(not any(0xD800 <= ord(x) <= 0xDFFF for x in decoded), "oracle lone surrogate")
            return i + 1, None
        if c < 32:
            return None, ("invalid_string", i)
        if c == 92:
            slash = i
            i += 1
            if i == len(raw):
                return None, ("truncated", i)
            if raw[i] in b'"\\/bfnrt':
                i += 1
                continue
            if raw[i] != 117:
                return None, ("invalid_string", i)
            digits = raw[i + 1 : i + 5]
            for j, d in enumerate(digits):
                if d not in b"0123456789abcdefABCDEF":
                    return None, ("invalid_string", i + 1 + j)
            if len(digits) < 4:
                return None, ("truncated", len(raw))
            unit = int(digits, 16)
            i += 5
            if 0xDC00 <= unit <= 0xDFFF:
                return None, ("invalid_string", slash)
            if 0xD800 <= unit <= 0xDBFF:
                # Missing continuation is truncation only for viable final prefixes.
                tail = raw[i:]
                if not tail or tail == b"\\":
                    return None, ("truncated", len(raw))
                if not tail.startswith(b"\\u"):
                    return None, ("invalid_string", slash)
                digits = raw[i + 2 : i + 6]
                for j, d in enumerate(digits):
                    if d not in b"0123456789abcdefABCDEF":
                        return None, ("invalid_string", i + 2 + j)
                if len(digits) < 4:
                    return None, ("truncated", len(raw))
                if not 0xDC00 <= int(digits, 16) <= 0xDFFF:
                    return None, ("invalid_string", slash)
                i += 6
            continue
        if c < 128:
            i += 1
            continue
        # Decode the maximal raw run through the next JSON ASCII syntax byte.
        end = i
        while end < len(raw) and raw[end] >= 128:
            end += 1
        # Include ASCII until a delimiter; decoder error positions still refer
        # to the lead byte, never implementation continuation-byte indexing.
        try:
            raw[i:end].decode("utf-8", "strict")
        except UnicodeDecodeError as error:
            at = i + error.start
            if error.reason == "unexpected end of data" and end == len(raw):
                return None, ("truncated", len(raw))
            return None, ("invalid_string", at)
        i = end
    return None, ("truncated", len(raw))


def token_model(data, offset, count):
    if offset < 0 or count < 0 or offset > len(data) or count > len(data) - offset:
        return failed("invalid_window", 0)
    if count > 4096:
        return failed("input_limit", offset)
    raw = bytes(data[offset : offset + count])
    i = len(raw) - len(raw.lstrip(WS))
    if i == len(raw):
        return (S["end_of_input"], 0, offset + count, 0, count, 0)
    first = raw[i]
    if first in PUNCT:
        end, kind = i + 1, 1 + PUNCT.index(first)
    elif first == 34:
        end, error = string_end(raw, i)
        if error:
            return failed(error[0], offset + error[1])
        kind = K["string"]
    elif first in b"-0123456789":
        # Regex gives complete grammar prefix; the suffix distinguishes malformed
        # continuations from ordinary token boundaries without numeric conversion.
        match = NUMBER.match(raw, i)
        end = match.end() if match else i
        if match and end - i > 128:
            return failed("number_limit", offset + i + 128)
        if match and end < len(raw) and raw[end] in b".eE":
            spelling = raw[i:end]
            allowed = (raw[end] in b"eE" and not any(c in spelling for c in b"eE")) or (
                raw[end] == 46 and not any(c in spelling for c in b".eE")
            )
            if not allowed:
                return failed("invalid_number", offset + end)
            end += 1
            if end - i > 128:
                return failed("number_limit", offset + i + 128)
            if raw[end - 1] in b"eE" and end < len(raw) and raw[end] in b"+-":
                end += 1
                if end - i > 128:
                    return failed("number_limit", offset + i + 128)
            return failed("invalid_number", offset + end)
        if not match:
            end = i + 1
            return failed("invalid_number", offset + end)
        if end - i > 128:
            return failed("number_limit", offset + i + 128)
        if end < len(raw) and raw[end] not in WS + PUNCT:
            return failed("invalid_number", offset + end)
        kind = K["number"]
    elif first in b"tfn":
        word, kind = {116: (b"true", 9), 102: (b"false", 10), 110: (b"null", 11)}[first]
        fragment = raw[i : i + len(word)]
        for n, (actual, wanted) in enumerate(zip(fragment, word)):
            if actual != wanted:
                return failed("invalid_literal", offset + i + n)
        if len(fragment) < len(word):
            return failed("truncated", offset + len(raw))
        end = i + len(word)
        if end < len(raw) and raw[end] not in WS + PUNCT:
            return failed("invalid_literal", offset + end)
    else:
        return failed("invalid_byte", offset + i)
    return (0, kind, offset + i, end - i, end, 0)


class ParseFailure(Exception):
    def __init__(self, status, at):
        self.status, self.at = status, at


def document_model(data, offset, count):
    initial = token_model(data, offset, count)
    if initial[0] in (S["invalid_window"], S["input_limit"]):
        return (initial[0], initial[5], 0, 0)
    used = offset
    tokens = 0
    maximum = 0

    def take():
        nonlocal used, tokens
        r = token_model(data, used, offset + count - used)
        if r[0] == S["end_of_input"]:
            return r
        if r[0] != 0:
            raise ParseFailure(r[0], r[5])
        if tokens == 1024:
            raise ParseFailure(S["token_limit"], r[2])
        tokens += 1
        used += r[4]
        return r

    def need(r):
        if r[0] == S["end_of_input"]:
            raise ParseFailure(S["truncated"], offset + count)

    def value(r, depth):
        nonlocal maximum
        need(r)
        kind = r[1]
        if kind in (7, 8, 9, 10, 11):
            return
        if kind not in (1, 3):
            raise ParseFailure(S["invalid_structure"], r[2])
        if depth == 32:
            raise ParseFailure(S["depth_limit"], r[2])
        depth += 1
        maximum = max(maximum, depth)
        close = 2 if kind == 1 else 4
        r = take()
        need(r)
        if r[1] == close:
            return
        while True:
            if kind == 1:
                if r[1] != 7:
                    raise ParseFailure(S["invalid_structure"], r[2])
                colon = take()
                need(colon)
                if colon[1] != 5:
                    raise ParseFailure(S["invalid_structure"], colon[2])
                r = take()
            value(r, depth)
            r = take()
            need(r)
            if r[1] == close:
                return
            if r[1] != 6:
                raise ParseFailure(S["invalid_structure"], r[2])
            r = take()
            need(r)

    try:
        value(take(), 0)
        r = take()
        if r[0] != S["end_of_input"]:
            raise ParseFailure(S["invalid_structure"], r[2])
        return (0, 0, tokens, maximum)
    except ParseFailure as error:
        return (error.status, error.at, tokens, maximum)


@dataclasses.dataclass(frozen=True)
class Case:
    label: str
    data: bytes
    offset: int = 0
    count: int | None = None
    windows: tuple = ()

    def span(self):
        raw = self.data
        for start, size in self.windows:
            raw = raw[start : start + size]
        return raw

    def extent(self):
        return len(self.span()) if self.count is None else self.count


@dataclasses.dataclass(frozen=True)
class Test:
    label: str
    body: str
    expected: tuple
    helper: str = ""


def observe(document=False):
    body = "if(field==0){"
    for i, status in enumerate(STATUSES):
        body += f"if(report.status()==std::JsonStatus::{status}){{return {i};}}"
    body += "return -777;}"
    if not document:
        body += "if(field==1){"
        for i, kind in enumerate(KINDS):
            body += f"if(report.kind()==std::JsonTokenKind::{kind}){{return {i};}}"
        body += "return -778;}"
    names = (
        ("error_offset", "token_count", "max_depth")
        if document
        else ("byte_offset", "byte_count", "consumed_bytes", "error_offset")
    )
    for i, name in enumerate(names, 1 if document else 2):
        body += f"if(field=={i}){{return report.{name}();}}"
    return body + "return -779;"


def source_case(case, document):
    result = "std::JsonResult" if document else "std::JsonTokenResult"
    function = "validate_json" if document else "next_json_token"
    expected = (document_model if document else token_model)(case.span(), case.offset, case.extent())
    helper = f"auto input_CASE({SPAN} bytes)->{result}{{"
    parent = "bytes"
    for i, (start, size) in enumerate(case.windows):
        name = f"view{i}"
        helper += f"const {SPAN} {name}={parent}.subspan({start},{size});"
        parent = name
    helper += f"const {result} r=std::{function}({parent},{case.offset},{case.extent()});return r;}}"
    body = harness.array(case.data) + f"const builtin::array<u8,{max(1, len(case.data))}> saved=owner;"
    body += f"const {result} original=input_CASE(borrow_bytes(owner));"
    body += "i64 i=0;while(i<len(owner)){if(owner[i]!=saved[i]){return -780;}i=i+1;}owner[0]=0u8;"
    body += f"const {result} report=original;" + observe(document)
    return Test(("document " if document else "token ") + case.label, body, expected, helper)


def cases():
    valid = (
        b"null",
        b"true",
        b"false",
        b"0",
        b"-0",
        b"12.34e-56",
        b"1E+999999999999999999999999999999999999",
        b'""',
        b'"a\\n\\t\\/\\\\\\""',
        b'"\\u0000\\ud834\\udd1e"',
        b"[]",
        b"{}",
        b'{"a":0,"a":[true,false,null,{"z":"x"}]}',
    )
    for raw in valid:
        yield Case("valid grammar " + repr(raw), raw)
        yield Case("nonzero clipped window", b"\xff \t" + raw + b"\xff", 3, len(raw))
        yield Case(
            "nested subspan coordinates",
            b"\xff!? " + raw + b" \xff",
            1,
            len(raw),
            ((1, len(raw) + 5), (2, len(raw) + 2)),
        )
    for raw in (
        b"",
        b" \t\r\n",
        b"//comment",
        b"/*x*/",
        b"\v",
        b"\f",
        b"NaN",
        b"Infinity",
        b"+1",
        b".1",
        b"01",
        b"-01",
        b"-",
        b"1.",
        b"1e",
        b"1e+",
        b"1e-",
        b"1eX",
        b"1.e1",
        b"1.2.3",
        b"1e2e3",
        b"1e2.3",
        b"trueX",
        b"truefalse",
        b"null0",
        b"False",
        b"nulL",
        b"tr",
        b'"\\x"',
        b'"\\u0x00"',
        b'"\\ud800"',
        b'"\\udc00"',
        b'"\\ud800\\u0000"',
        b'"\\ud800x"',
        b'"\x00"',
        b'"\n"',
        b'"abc',
        b"[",
        b"{",
        b"[1,]",
        b'{"a":}',
        b'{"a" 1}',
        b"{1:0}",
        b"[1 2]",
        b"[,]",
        b"{}{}",
        b"null true",
        b"}",
        b"]",
        b":",
        b",",
    ):
        yield Case("malformed or empty " + repr(raw), raw or b"\xff", 0, len(raw))
        yield Case("clipped malformed coordinate " + repr(raw), b"\xff \t" + raw + b"\xff", 3, len(raw))
    for byte in range(256):
        yield Case("each byte outside string", bytes([byte]))
        yield Case("each byte inside string", b'"' + bytes([byte]) + b'"')
    escapes = (b'"\\u1234"', b'"\\ud834\\udd1e"', b'"\\n"', b'"\\\\"', b'"' + chr(0x10FFFF).encode() + b'"')
    for raw in escapes:
        for size in range(len(raw) + 1):
            yield Case("every final escape/UTF8 byte cutoff", raw, 0, size)
    for scalar in (0x7F, 0x80, 0x7FF, 0x800, 0xD7FF, 0xE000, 0xFFFF, 0x10000, 0x10FFFF, 0xFEFF, 0xFDD0):
        yield Case("strict Unicode scalar boundary", b'"' + chr(scalar).encode() + b'"')
    for bad in (
        b"\x80",
        b"\xc0\x80",
        b"\xc1\xbf",
        b"\xc2",
        b"\xc2A",
        b"\xe0\x9f\xbf",
        b"\xed\xa0\x80",
        b"\xf0\x8f\xbf\xbf",
        b"\xf4\x90\x80\x80",
        b"\xf5\x80\x80\x80",
        b"\xff",
        b"\xe2\x82",
        b"\xf0\x90\x80",
    ):
        yield Case("bad UTF8 terminated", b'"a' + bad + b'"')
        yield Case("bad UTF8 final window", b'"a' + bad)
    for n in (127, 128, 129):
        for raw in (b"1" * n, b"1e" + b"9" * (n - 2), b"-" + b"1" * (n - 1)):
            yield Case("number spelling limit", raw)
    for suffix in (b".", b"e", b"e+", b"x", b"1"):
        yield Case("number transition and limit precedence", b"1" * 128 + suffix)
    for depth in (31, 32, 33):
        yield Case("array nesting limit", b"[" * depth + b"0" + b"]" * depth)
        yield Case("object nesting limit", b'{"k":' * depth + b"0" + b"}" * depth)
    for n in (510, 511, 512):
        yield Case("token limit odd", b"[" + b",".join([b"0"] * n) + b"]")
    # 1024 tokens is achieved with one nested empty array and 510 values.
    yield Case("token limit exact 1024", b"[" + b",".join([b"[]"] + [b"0"] * 510) + b"]")
    exact = b"[" + b",".join([b"[]"] + [b"0"] * 510) + b"]"
    for suffix in (b" 0", b" \xff", b" [", b' "'):
        yield Case("lexing before token-budget before syntax", exact + suffix)
    for depth in (31, 32, 33):
        opening = b""
        closing = b""
        for i in range(depth):
            opening += b"[" if i % 2 else b'{"k":'
            closing = (b"]" if i % 2 else b"}") + closing
        yield Case("mixed nesting limit", opening + b"0" + closing)
    for n in (4095, 4096):
        yield Case("maximal input string", b'"' + b"a" * (n - 2) + b'"')
        yield Case("maximal input whitespace", b" " * (n - 1) + b"0")
    for dimension in (0, 1):
        for value in (MIN, -1, 0, 1, 2, 3, 4096, 4097, MAX):
            args = [0, 1]
            args[dimension] = value
            yield Case("signed window dimension", b"0", *args)
    for start, size in itertools.product((MIN, -1, MAX), repeat=2):
        yield Case("combined malformed window", b"\xff", start, size)
    for start, size in ((0, 0), (0, 1), (1, 0), (MIN, MAX), (MAX, 0)):
        yield Case("actual empty nested span", b"\xff", start, size, ((1, 0), (0, 0)))
    rng = random.Random(20261007)

    def generated(depth):
        leaves = [None, True, False, rng.randrange(-1000, 1000), "", chr(rng.choice([0x80, 0x800, 0x1F642])), "x\n\t"]
        if depth == 0 or rng.randrange(4) == 0:
            return rng.choice(leaves)
        children = [generated(depth - 1) for _ in range(rng.randrange(4))]
        if rng.randrange(2):
            return children
        return {"k" + str(i): value for i, value in enumerate(children)}

    for n in range(40):
        obj = generated(n % 6)
        raw = json.dumps(obj, ensure_ascii=bool(rng.randrange(2)), separators=(",", ":")).encode()
        require(len(raw) <= 4096, "bounded serializer fixture")
        yield Case("seeded nested Python independent serializer", raw)


def expired_tests():
    for document in (False, True):
        result = "std::JsonResult" if document else "std::JsonTokenResult"
        function = "validate_json" if document else "next_json_token"
        for raw in (b"null", b'"\\ud834\\udd1e"', b" [0] ", b'"\\x"'):
            helper = (
                f"auto expired_CASE()->{result}{{"
                + harness.array(raw)
                + f"const {result} r=std::{function}(borrow_bytes(owner),0,{len(raw)});return r;}}"
            )
            body = f"const {result} original=expired_CASE();const {result} report=original;" + observe(document)
            yield Test(
                "copied report outlives source owner",
                body,
                (document_model if document else token_model)(raw, 0, len(raw)),
                helper,
            )


def token_report_model(status, kind, start, count, used, error):
    bad = failed("invalid_window", 0)
    if status == S["invalid_window"]:
        return bad
    if min(start, count, used, error) < 0 or count > 4096 or used > 4096 or start + count > MAX:
        return bad
    if status in (0, 1):
        if error or used < count or used - count > start:
            return bad
        if status == 0 and (kind == 0 or count == 0):
            return bad
        if status == 1 and (kind != 0 or count != 0):
            return bad
        return (status, kind, start, count, used, error)
    if status in (S["token_limit"], S["depth_limit"], S["invalid_structure"]):
        return bad
    if kind or start or count or used:
        return bad
    return (status, 0, 0, 0, 0, error)


def document_report_model(status, error, tokens, depth):
    if (
        status in (S["invalid_window"], S["end_of_input"])
        or min(error, tokens, depth) < 0
        or tokens > 1024
        or depth > 32
        or (status == 0 and (error != 0 or tokens == 0))
    ):
        return (S["invalid_window"], 0, 0, 0)
    return (status, error, tokens, depth)


def public_reports():
    for document in (False, True):
        seeds = (
            ((0, 0, 1, 0), (0, 0, 1024, 32), (S["invalid_string"], 7, 5, 2))
            if document
            else ((0, 8, 2, 1, 3, 0), (1, 0, 4096, 0, 4096, 0), (S["invalid_string"], 0, 0, 0, 0, 9))
        )
        rows = set(seeds)
        for seed in seeds:
            for dimension in range(1 if document else 2, len(seed)):
                for edge in (MIN, -1, 0, 1, 32, 33, 1024, 1025, 4096, 4097, MAX):
                    row = list(seed)
                    row[dimension] = edge
                    rows.add(tuple(row))
        for status in range(len(STATUSES)):
            rows.add((status, 7, 2, 1) if document else (status, 0, 0, 0, 0, 7))
            if not document:
                for kind in range(len(KINDS)):
                    rows.add((status, kind, 0, 1, 1, 0))
        for row in sorted(rows):
            result = "std::JsonResult" if document else "std::JsonTokenResult"
            values = [f"std::JsonStatus::{STATUSES[row[0]]}"]
            if document:
                values += list(map(str, row[1:]))
            else:
                values += [f"std::JsonTokenKind::{KINDS[row[1]]}"] + list(map(str, row[2:]))
            body = (
                f"const {result} original={result}("
                + ",".join(values)
                + f");const {result} report=original;"
                + observe(document)
            )
            expected = (document_report_model if document else token_report_model)(*row)
            yield Test("public copied shape is not source certification", body, expected)


def lexical_sequences():
    # Every successful token is requested from a new suffix, including terminal
    # trivia. Coordinates remain relative to the original supplied span.
    for raw in (b' {"a": [0,-1.5e+2,true,false,null,"\\ud834\\udd1e"]} \n', b"[]{}:,"):
        data = b"\xff" + raw + b"\xff"
        used = 1
        end = len(data) - 1
        while True:
            case = Case("repeated lexical suffix coordinates", data, used, end - used)
            yield source_case(case, False)
            r = token_model(data, used, end - used)
            if r[0] == 1:
                break
            require(r[0] == 0 and r[4] > 0, "sequence fixture must progress")
            used += r[4]


def all_tests():
    for case in cases():
        yield source_case(case, False)
        yield source_case(case, True)
    yield from expired_tests()
    yield from public_reports()
    yield from lexical_sequences()


def batches(items):
    group = []
    size = 0
    for item in items:
        cost = len(item.body) + len(item.helper) + 120
        require(cost < 62000, "single generated source exceeds cap")
        if group and (len(group) >= 16 or size + cost > 62000):
            yield group
            group = []
            size = 0
        group.append(item)
        size += cost
    if group:
        yield group


class Suite(harness.Suite):
    def __init__(self, args, identity):
        super().__init__(args, identity)
        self.observations = 0
        for name in (
            "tests/compiler/json_profile.py",
            "tests/compiler/utf8_range.py",
            "scripts/compiler_contract.py",
            "scripts/package_profiles.py",
        ):
            self.inputs[name] = harness.sha(self.root / name)

    def batch(self, items):
        self.budget()
        d = self.output / f"batch-{self.batches:04d}"
        d.mkdir()
        self.batches += 1
        source = "module json_test;import std.json;\n"
        for i, item in enumerate(items):
            source += item.helper.replace("_CASE", f"_{i}") + "\n"
            source += f"auto json_case_{i}(i64 field)->i64{{" + item.body.replace("_CASE", f"_{i}") + "}\n"
        require(len(source.encode()) <= 65536, "source-size cap")
        (d / "input.au").write_text(source)
        wanted = [v for item in items for v in item.expected]
        receipt = dict(
            labels=[item.label for item in items],
            expected=wanted,
            source_sha256=harness.sha(d / "input.au"),
            status="running",
        )
        try:
            self.command(
                [self.compiler, "--module-root", self.root / "library", d / "input.au", "-o", d / "compiled.s"],
                d,
                "compiler",
            )
            entry = [".text", ".globl _start", "_start:"]
            for i, item in enumerate(items):
                for field in range(len(item.expected)):
                    entry += [
                        f"movq ${field},%rdi",
                        f"call json_case_{i}",
                        "pushq %rax",
                        "movq $1,%rax",
                        "movq $1,%rdi",
                        "movq %rsp,%rsi",
                        "movq $8,%rdx",
                        "syscall",
                        "addq $8,%rsp",
                    ]
            entry += ["movq $60,%rax", "xorq %rdi,%rdi", "syscall", '.section .note.GNU-stack,"",@progbits']
            (d / "entry.s").write_text("\n".join(entry) + "\n")
            self.command(["as", "--64", d / "compiled.s", "-o", d / "program.o"], d, "assemble")
            self.command(["as", "--64", d / "entry.s", "-o", d / "entry.o"], d, "entry")
            require(
                not self.command(["nm", "-u", d / "program.o"], d, "undefined-object").strip(),
                "unresolved runtime import",
            )
            self.command(["ld", "-o", d / "program", d / "entry.o", d / "program.o"], d, "link")
            require(
                not self.command(["nm", "-u", d / "program"], d, "undefined-native").strip(), "unresolved native import"
            )
            raw = self.command([d / "program"], d, "native")
            require(len(raw) == 8 * len(wanted), "complete i64 observation length")
            observed = [int.from_bytes(raw[i : i + 8], "little", signed=True) for i in range(0, len(raw), 8)]
            receipt.update(observed=observed, output_sha256=hashlib.sha256(raw).hexdigest())
            require(
                observed == wanted,
                f"native mismatch {[(i, a, b) for i, (a, b) in enumerate(zip(observed, wanted)) if a != b][:16]}",
            )
            receipt["status"] = "passed"
            self.count += len(items)
            self.observations += len(wanted)
        except Exception as error:
            receipt.update(status="failed", error=str(error))
            raise
        finally:
            (d / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(f"PASS JSON batch {self.batches}: {len(items)} cases, {len(wanted)} full i64 observations", flush=True)


def rejections(source):
    head = "module rejection;import std.json;"
    for cls, arity in (("JsonTokenResult", 6), ("JsonResult", 4)):
        block = re.search(r"class " + cls + r"\s*\{(.*?)public:", source, re.S)
        require(block is not None, "private report declaration")
        fields = re.findall(r"\b(?:JsonStatus|JsonTokenKind|i64)\s+(\w+)\s*;", block.group(1))
        require(len(fields) == arity, "private copied report field count")
        args = "std::JsonStatus::success," + ("std::JsonTokenKind::number,0,1,1,0" if arity == 6 else "0,1,0")
        for field in fields:
            yield (
                "private report field",
                head + f"auto test()->i64{{const std::{cls} r=std::{cls}({args});return r.{field};}}",
                "private",
            )
    helpers = sorted(set(re.findall(r"\bauto\s+(json_\w+)\s*\(", source)))
    require(helpers, "private JSON helpers available")
    for helper in helpers:
        yield (
            "private helper " + helper,
            head + f"auto test()->i64{{return std::{helper}();}}",
            "private function is not imported",
        )
    for result, base in (
        ("JsonTokenResult", ["std::JsonStatus::success", "std::JsonTokenKind::number", "0", "1", "1", "0"]),
        ("JsonResult", ["std::JsonStatus::success", "0", "1", "0"]),
    ):
        for dimension in range(2 if result == "JsonTokenResult" else 1, len(base)):
            args = base.copy()
            args[dimension] = "0u64"
            yield (
                "exact constructor signed metadata type",
                head
                + f"auto test()->i64{{const std::{result} r=std::{result}("
                + ",".join(args)
                + ");return r.error_offset();}",
                "expected i64",
            )
        for dimension in range(2 if result == "JsonTokenResult" else 1):
            args = base.copy()
            args[dimension] = "17"
            yield (
                "closed nominal enum constructor",
                head
                + f"auto test()->i64{{const std::{result} r=std::{result}("
                + ",".join(args)
                + ");return r.error_offset();}",
                "expected",
            )
        yield (
            "constructor exact arity",
            head
            + f"auto test()->i64{{const std::{result} r=std::{result}("
            + ",".join(base[:-1])
            + ");return r.error_offset();}",
            "argument",
        )
    for function, result in (("next_json_token", "JsonTokenResult"), ("validate_json", "JsonResult")):
        for args in ("0u64,1", "0,1u64", "0u8,1", "0,1u8", "false,1", "0,false"):
            yield (
                "exact signed window type",
                head
                + "auto test()->i64{builtin::array<u8,1> b={48u8};"
                + f"const std::{result} r=std::{function}(borrow_bytes(b),{args});return r.error_offset();}}",
                "expected i64",
            )
        yield (
            "source borrow prevents mutation",
            head
            + "auto test()->i64{builtin::array<u8,1> b={48u8};"
            + f"const {SPAN} v=borrow_bytes(b);const std::{result} r=std::{function}(v,0,1);"
            + "b[0]=0u8;return r.error_offset();}",
            "span is live",
        )
    yield (
        "raw array is not span",
        head
        + "auto test()->i64{builtin::array<u8,1> b={48u8};"
        + "const std::JsonResult r=std::validate_json(b,0,1);return r.error_offset();}",
        "span",
    )
    yield (
        "nonbyte owner rejected",
        head
        + "auto test()->i64{builtin::array<i64,1> b={48};"
        + "const std::JsonResult r=std::validate_json(borrow_bytes(b),0,1);return r.error_offset();}",
        "byte",
    )
    yield (
        "nested empty span retains borrow",
        head
        + "auto test()->i64{builtin::array<u8,1> b={48u8};"
        + f"const {SPAN} v=borrow_bytes(b);const {SPAN} e=v.subspan(1,0);"
        + "const std::JsonResult r=std::validate_json(e,0,0);b[0]=0u8;return r.error_offset();}",
        "span is live",
    )
    yield ("owner cap above profile", head + "auto test()->i64{builtin::array<u8,4097> b={};return 0;}", "4096")
    yield (
        "span cannot escape in class",
        head + f"class Bad{{{SPAN} bytes;}};auto test()->i64{{return 0;}}",
        "class fields require",
    )


def self_test():
    require(token_model(b" \tnull", 0, 6) == (0, 11, 2, 4, 6, 0), "literal coordinates")
    require(document_model(b'{"a":0,"a":[]}', 0, 14) == (0, 0, 10, 2), "duplicate keys and depth")
    require(token_model(b'"\\ud800"', 0, 8) == failed("invalid_string", 1), "strict surrogate rejection")
    require(token_model(b'"\\u0x00"', 0, 8) == failed("invalid_string", 4), "hex diagnostic coordinate")
    require(document_model(b"[1,]", 0, 4) == (S["invalid_structure"], 3, 4, 1), "trailing comma")
    # Compiler-free mutation controls exercise the actual comparator, never count
    # as native semantic mutation qualification.
    good = token_model(b" \tnull", 0, 6)
    for field in range(len(good)):
        mutant = list(good)
        mutant[field] += 1
        detected = False
        try:
            require(tuple(mutant) == good, "deliberate observation mutation")
        except AssertionError:
            detected = True
        require(detected, "oracle comparison mutation escaped")


def oracle_audit():
    """Cross-check successes AND syntax failures with a separate whole decoder.

    Exclude only invalid windows and explicit policy limits. Preserve duplicate
    pairs so a discarded duplicate value cannot hide an unpaired surrogate.
    parse callbacks retain number spellings without host numeric conversion.
    """
    counts = dict(accepted=0, rejected=0, profile_excluded=0)

    def scalars(item):
        if isinstance(item, str):
            if any(0xD800 <= ord(c) <= 0xDFFF for c in item):
                raise ValueError("unpaired surrogate")
        elif isinstance(item, (list, tuple)):
            for child in item:
                scalars(child)

    for case in cases():
        report = document_model(case.span(), case.offset, case.extent())
        if report[0] in (S["invalid_window"], S["input_limit"], S["number_limit"], S["token_limit"], S["depth_limit"]):
            counts["profile_excluded"] += 1
            continue
        raw = case.span()[case.offset : case.offset + case.extent()]
        accepted = True
        try:
            value = json.loads(
                raw.decode("utf-8", "strict"),
                parse_int=lambda text: text,
                parse_float=lambda text: text,
                parse_constant=lambda text: (_ for _ in ()).throw(ValueError(text)),
                object_pairs_hook=lambda pairs: pairs,
            )
            scalars(value)
        except (ValueError, UnicodeError):
            accepted = False
        require(accepted == (report[0] == 0), "independent whole-decoder classification: " + case.label)
        counts["accepted" if accepted else "rejected"] += 1
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
    require(not (args.compiler and args.compiler_pos), "select positional compiler or --compiler, not both")
    args.compiler = args.compiler or args.compiler_pos
    if args.developer_selected_compiler:
        require(
            args.compiler_sha256 is None,
            "developer-selected compiler cannot claim a pin",
        )
    else:
        harness.validate_identity_selection(args, preflight=args.self_test_only or args.describe)
    self_test()
    audit = oracle_audit()
    if args.self_test_only:
        print("PASS JSON independent grammar/Unicode and comparator controls")
        return
    if args.describe:
        groups = list(batches(all_tests()))
        print(
            json.dumps(
                dict(
                    cases=sum(map(len, groups)),
                    batches=len(groups),
                    complete_i64_observations=sum(len(i.expected) for g in groups for i in g),
                    largest_batch_source_estimate=max(
                        sum(len(i.body) + len(i.helper) + 120 for i in g) for g in groups
                    ),
                    budget_mib=args.budget_mib,
                ),
                indent=2,
            )
        )
        return
    require(args.compiler is not None, "compiler required")
    if args.artifacts is None:
        import tempfile

        args.artifacts = pathlib.Path(tempfile.mkdtemp(prefix="aurora-json-profile-")) / "gate"
        print("Retained JSON artifacts: " + str(args.artifacts), flush=True)
    require(32 <= args.budget_mib <= 1024, "artifact budget must be 32..1024 MiB")
    args.sanitized_compiler = args.sanitized_compiler or any(
        f.startswith("-fsanitize=") for f in selected_flag_vectors(__import__("os").environ)["CXXFLAGS"]
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
        independent_decoder_audit=audit,
    )
    try:
        for group in batches(all_tests()):
            suite.batch(group)
        for item in rejections((args.repo_root / "library/std/json.au").read_text()):
            suite.reject(*item)
        suite.verify_inputs()
        identity.verify()
        manifest.update(
            status="passed",
            cases=suite.count,
            full_i64_observations=suite.observations,
            batches=suite.batches,
            rejections=suite.rejections,
        )
    except Exception as error:
        manifest.update(status="failed", error=str(error))
        raise
    finally:
        identity_errors = finalize_selected_identity(identity, manifest)
        manifest["compiler_identity"] = identity.record()
        manifest.update(
            completed_cases=suite.count, completed_rejections=suite.rejections, allocated_bytes=suite.budget(0)
        )
        (suite.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        require(not identity_errors, "; ".join(identity_errors))


if __name__ == "__main__":
    main()
