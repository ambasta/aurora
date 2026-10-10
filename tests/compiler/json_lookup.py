#!/usr/bin/env python3
"""Bounded root JSON lookup with independent ordered-pair and byte-range oracles.

CPython preserves duplicate members, scalar values and number spellings. A separate
regular-expression token inventory pairs brackets and indexes byte extents; it is
used only after whole-document decoding. The established independent JSON grammar
oracle supplies failure coordinates and policy limits. Every native field keeps
all 64 bits; failed sources, tool logs, observations and identities are retained.
This focused gate is not full-native, sanitizer or general parser qualification.
"""

from __future__ import annotations

import argparse
import dataclasses
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

harness, require = profile.harness, profile.require
MIN, MAX, SPAN = profile.MIN, profile.MAX, profile.SPAN
Case, Test = profile.Case, profile.Test
RESULT = "std::JsonLookupResult"
SEED = 202610082
STATUSES = (
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
KINDS = ("none", "object", "array_value", "string", "number", "true_value", "false_value", "null_value")
S, K = ({name: index for index, name in enumerate(names)} for names in (STATUSES, KINDS))
TOKEN = re.compile(
    r'"(?:[^"\\]|\\.)*"|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|true|false|null|[{}\[\]:,]', re.S
)


class Pairs(list):
    """Distinguish ordered object pairs from arrays, including empty containers."""


class Number(str):
    """Preserve decimal spelling without constructing a float or rounding."""


def reject_constant(text):
    raise ValueError(text)


def decode(raw):
    result = json.loads(
        raw.decode("utf-8", "strict"),
        object_pairs_hook=Pairs,
        parse_int=Number,
        parse_float=Number,
        parse_constant=reject_constant,
    )

    def scalar_check(value):
        if isinstance(value, str):
            require(not any(0xD800 <= ord(char) <= 0xDFFF for char in value), "oracle lone surrogate")
        elif isinstance(value, (list, tuple)):
            for child in value:
                scalar_check(child)

    scalar_check(result)
    return result


def value_kind(value):
    if isinstance(value, Pairs):
        return K["object"]
    if isinstance(value, list):
        return K["array_value"]
    if isinstance(value, Number):
        return K["number"]
    if isinstance(value, str):
        return K["string"]
    if value is True:
        return K["true_value"]
    if value is False:
        return K["false_value"]
    require(value is None, "oracle value domain")
    return K["null_value"]


def root_ranges(raw):
    """Independent valid-document token inventory, bracket pairing and byte map.

    No target tokenizer, lookup traversal or failure state machine is copied.
    The standard decoder is authority for validity and ordered semantic values.
    The inventory supplies only source ranges, audited by decoding every slice.
    """
    root = decode(raw)
    text = raw.decode("utf-8", "strict")
    offsets = [0]
    for char in text:
        offsets.append(offsets[-1] + len(char.encode("utf-8")))
    tokens = list(TOKEN.finditer(text))
    require(tokens, "valid JSON has a token")
    last = 0
    for token in tokens:
        require(not text[last : token.start()].strip(" \t\r\n"), "token inventory covers source")
        last = token.end()
    require(not text[last:].strip(" \t\r\n"), "token inventory covers final trivia")
    stack, mates = [], {}
    for index, token in enumerate(tokens):
        spelling = token.group()
        if spelling in ("{", "["):
            stack.append(index)
        elif spelling in ("}", "]"):
            opening = stack.pop()
            require((tokens[opening].group(), spelling) in (("{", "}"), ("[", "]")), "paired extent")
            mates[opening] = index
    require(not stack, "balanced extent inventory")

    def extent(index, value):
        final = mates.get(index, index)
        first, end = offsets[tokens[index].start()], offsets[tokens[final].end()]
        require(decode(raw[first:end]) == value, "independent selected source slice matches semantic value")
        return (value_kind(value), first, end - first), final + 1

    records = []
    cursor = 1
    if isinstance(root, Pairs):
        for key, value in root:
            require(json.loads(tokens[cursor].group()) == key, "ordered duplicate key correspondence")
            key_at = offsets[tokens[cursor].start()]
            require(tokens[cursor + 1].group() == ":", "member separator")
            item, cursor = extent(cursor + 2, value)
            records.append((key, key_at, item))
            if tokens[cursor].group() == ",":
                cursor += 1
    elif isinstance(root, list):
        for index, value in enumerate(root):
            item, cursor = extent(cursor, value)
            records.append((index, 0, item))
            if tokens[cursor].group() == ",":
                cursor += 1
    return value_kind(root), records


def failure(status, error=0):
    return (S[status], 0, 0, 0, error)


def valid_window(data, offset, count):
    return offset >= 0 and count >= 0 and offset <= len(data) and count <= len(data) - offset


def key_error(raw, offset):
    try:
        raw.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        # A viable final UTF-8 prefix points at the endpoint, all other failures
        # point at the leading byte. ASCII controls, quotes and slashes are data.
        return offset + (len(raw) if error.reason == "unexpected end of data" else error.start)
    return None


def lookup_model(data, offset, count, key=None, key_offset=0, key_count=None, index=0):
    if not valid_window(data, offset, count):
        return failure("invalid_window")
    if count > 4096:
        return failure("input_limit", offset)
    if key is not None:
        key_count = len(key) if key_count is None else key_count
        if not valid_window(key, key_offset, key_count):
            return failure("invalid_key_window")
        if key_count > 4096:
            return failure("key_limit", key_offset)
        raw_key = bytes(key[key_offset : key_offset + key_count])
        error = key_error(raw_key, key_offset)
        if error is not None:
            return failure("invalid_key", error)
        query = raw_key.decode("utf-8", "strict")
    else:
        if index < 0:
            return failure("invalid_index")
        query = index
    document = profile.document_model(data, offset, count)
    if document[0]:
        return failure(profile.STATUSES[document[0]], document[1])
    kind, records = root_ranges(bytes(data[offset : offset + count]))
    if kind != K["object" if key is not None else "array_value"]:
        return failure("wrong_root")
    matches = [record for record in records if record[0] == query]
    if len(matches) > 1:
        return failure("ambiguous", offset + matches[1][1])
    if not matches:
        return failure("not_found")
    selected = matches[0][2]
    return (0, selected[0], offset + selected[1], selected[2], 0)


@dataclasses.dataclass(frozen=True)
class Query:
    label: str
    document: Case
    key: Case | None = None
    index: int = 0

    def expected(self):
        return lookup_model(
            self.document.span(),
            self.document.offset,
            self.document.extent(),
            None if self.key is None else self.key.span(),
            0 if self.key is None else self.key.offset,
            None if self.key is None else self.key.extent(),
            self.index,
        )


def member(label, raw, key=b"k"):
    return Query(label, Case(label, raw), Case(label, key))


def element(label, raw, index=0):
    return Query(label, Case(label, raw), index=index)


def observe(report="report", field="field"):
    body = f"if({field}==0){{"
    for number, status in enumerate(STATUSES):
        body += f"if({report}.status()==std::JsonLookupStatus::{status}){{return {number};}}"
    body += f"return -777;}}if({field}==1){{"
    for number, kind in enumerate(KINDS):
        body += f"if({report}.kind()==std::JsonValueKind::{kind}){{return {number};}}"
    body += "return -778;}"
    for number, name in enumerate(("byte_offset", "byte_count", "error_offset"), 2):
        body += f"if({field}=={number}){{return {report}.{name}();}}"
    return body + "return -779;"


def sliced(case, parameter, prefix):
    parent, source = parameter, ""
    windows = case.windows if case.data else ((0, 0), *case.windows)
    for index, (start, count) in enumerate(windows):
        name = prefix + str(index)
        source += f"const {SPAN} {name}={parent}.subspan({start},{count});"
        parent = name
    return parent, source


def invocation(query, data="bytes", key="key"):
    args = f"{data},{query.document.offset},{query.document.extent()}"
    if query.key is None:
        return f"std::lookup_json_element({args},{query.index})"
    return f"std::lookup_json_member({args},{key},{query.key.offset},{query.key.extent()})"


def source_case(query):
    helper = f"auto input_CASE({SPAN} bytes"
    if query.key is not None:
        helper += f",{SPAN} key"
    helper += f")->{RESULT}{{"
    data, source = sliced(query.document, "bytes", "view")
    helper += source
    key = "key"
    if query.key is not None:
        key, source = sliced(query.key, "key", "keyview")
        helper += source
    helper += f"const {RESULT} result={invocation(query, data, key)};return result;}}"
    body = harness.array(query.document.data)
    body += f"const builtin::array<u8,{max(1, len(query.document.data))}> saved=owner;"
    args = "borrow_bytes(owner)"
    if query.key is not None:
        body += harness.array(query.key.data).replace("owner", "keyowner")
        body += f"const builtin::array<u8,{max(1, len(query.key.data))}> savedkey=keyowner;"
        args += ",borrow_bytes(keyowner)"
    body += f"const {RESULT} original=input_CASE({args});"
    body += "i64 i=0;while(i<len(owner)){if(owner[i]!=saved[i]){return -780;}i=i+1;}owner[0]=255u8;"
    if query.key is not None:
        body += "i=0;while(i<len(keyowner)){if(keyowner[i]!=savedkey[i]){return -781;}i=i+1;}keyowner[0]=255u8;"
    body += f"const {RESULT} report=original;" + observe()
    return Test(query.label, body, query.expected(), helper)


def query_cases():
    values = (
        b"{}",
        b"[]",
        b'""',
        b'"x\\n\\ud834\\udd1e"',
        b"0",
        b"-0",
        b"12.3e+99",
        b"true",
        b"false",
        b"null",
        b'{"deep":[0,{"k":1}]}',
        b"[[],{},[1,2]]",
    )
    for value in values:
        raw = b' {"k" : \t' + value + b' \r\n, "other":9} '
        yield member("each exact member kind and extent", raw)
        yield element("each exact element kind and extent", b" \t[ 9, " + value + b" ,null] \r\n", 1)
        for query in (
            member("nested document and key coordinates", raw),
            element("nested array coordinates", b" [ " + value + b" ] "),
        ):
            doc = query.document.data
            nested = Case(query.label, b"\xff!?" + doc + b"x\xff", 1, len(doc), ((1, len(doc) + 4), (1, len(doc) + 2)))
            key = None if query.key is None else Case(query.label, b"\xff!?kX\xff", 1, 1, ((1, 5), (1, 3)))
            yield dataclasses.replace(query, document=nested, key=key)
    raw = b'{"k":0,"z":{"k":1,"k":2},"a":[{"k":3},4]}'
    for key in (b"k", b"z", b"a", b"missing", b"K", b"k.k", b"k/", b""):
        yield member("root-only object lookup", raw, key)
    for index in (MIN, -1, 0, 1, 2, 3, MAX):
        yield element("root-only array lookup and full-width index", b'[{"k":0},[1,2],null]', index)
    for raw in (b"{}", b"[]", b"0", b'"k"', b"true", b"false", b"null"):
        yield member("validated wrong root or empty object", raw)
        yield element("validated wrong root or empty array", raw)

    # Ordered duplicates are retained by the decoder rather than collapsed into
    # a Python dict. Only duplicate members equal to the query are ambiguous.
    for raw in (
        b'{"k":0,"k":1}',
        b'{"k":0,"k":1,"k":2}',
        b'{"k":0,"\\u006b":1}',
        b'{"\\u006b":0,"k":1}',
        b'{"x":0,"x":1,"k":2}',
        b'{"k":{"k":1,"k":2},"z":0}',
        b'{"":0,"":1}',
        b'{"\\u0000":0,"\\u0000":1}',
        b'{"\\ud834\\udd1e":0,"' + chr(0x1D11E).encode() + b'":1}',
    ):
        for key in (b"k", b"x", b"", b"\0", chr(0x1D11E).encode(), b"missing"):
            yield member("ordered duplicate scalar equality", raw, key)
    scalars = (
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
    )
    texts = [chr(code) for code in scalars] + ["", "a\0b", "é", "e\u0301", "ab", "a/b", "a\\b", "A", "a"]
    for text in texts:
        for ascii_only in (False, True):
            spelling = json.dumps(text, ensure_ascii=ascii_only).encode()
            raw = b"{" + spelling + b":1}"
            yield member("plain key matches independently encoded JSON scalar sequence", raw, text.encode())
            yield member("key matching requires complete scalar sequence", raw, (text + "x").encode())
    for key in (b"\\u006b", b"k", b"\\k", b'"k"'):
        yield member("plain query has no JSON escape decoding", b'{"\\u006b":0,"\\\\u006b":1}', key)
    for key in ("é", "e\u0301", "É", "E\u0301"):
        yield member("no Unicode normalization or case folding", '{"é":0,"é":1,"É":2}'.encode(), key.encode())
    for byte in range(256):
        yield member("every one-byte plain key", b'{"":0,"\\u0000":1,"k":2}', bytes([byte]))
    mixed = b"A\xc2\xa2\xe2\x82\xac\xf0\x9f\x99\x82Z"
    raw = b"{" + json.dumps(mixed.decode(), ensure_ascii=False).encode() + b":0}"
    for offset in range(len(mixed) + 1):
        for count in range(len(mixed) - offset + 1):
            yield Query("every plain UTF8 key window", Case("document", raw), Case("key", mixed, offset, count))
    malformed_keys = (
        b"\x80",
        b"\xbf",
        b"\xc0\x80",
        b"\xc1\xbf",
        b"\xc2",
        b"\xc2A",
        b"\xe0\x9f",
        b"\xed\xa0\x80",
        b"\xe0\xa0",
        b"\xe1\x80A",
        b"\xf0\x8f\xbf\xbf",
        b"\xf0\x90",
        b"\xf4\x8f\xbf",
        b"\xf4\x90",
        b"\xf5",
        b"\xff",
    )
    for bad in malformed_keys:
        for prefix in (b"", b"k", b"\xc2\xa2Z"):
            key = prefix + bad
            yield Query(
                "invalid whole key overrides early matching prefix and malformed document",
                Case("document", b'{"k":0,]'),
                Case("key", b"\xff" + key + b"\xff", 1, len(key)),
            )
    # Existing independent grammar corpus covers every malformed byte, viable
    # escape/UTF8 prefix, token and depth policy edge, and scalar root grammar.
    for case in profile.cases():
        yield Query("member full validation: " + case.label, case, Case("key", b"k"))
        yield Query("element full validation: " + case.label, case, index=0)
    for raw in (
        b'{"k":0,"z":',
        b'{"k":0,"k":1,}',
        b'{"k":0,"k":1} true',
        b'{"k":0,"other":"\xff"}',
        b"[0,1,]",
        b'[0,"\\ud800"]',
    ):
        for key in (b"k", b"missing"):
            yield member("whole document failure overrides found duplicate or absent query", raw, key)
        yield element("whole document failure overrides wrong root and absent index", raw, MAX)
        yield Query("invalid key window precedes malformed document", Case("document", raw), Case("key", b"k", MAX, 1))
        yield element("negative index precedes malformed document", raw, MIN)
    for offset, count in itertools.product((MIN, -1, 0, 1, 2, 3, 4096, 4097, MAX), repeat=2):
        yield Query(
            "subtraction-first key window extremes", Case("document", b'{"k":0}'), Case("key", b"k", offset, count)
        )
    for offset, count in itertools.product((MIN, -1, 0, 1, 2, 3, MAX), repeat=2):
        yield Query(
            "document window precedes every key error",
            Case("document", b"[]", offset, count),
            Case("key", b"\xff", MAX, MAX),
        )
    for raw in ('{"k":[0,{"q":"é"}]}'.encode(), b'[0,{"k":true}]'):
        for offset in range(len(raw) + 1):
            for count in range(len(raw) - offset + 1):
                yield Query(
                    "every document byte window",
                    Case("document", raw, offset, count),
                    Case("key", b"k") if raw[:1] == b"{" else None,
                    0,
                )
    for size in (4095, 4096):
        yield member("maximal valid key compared without hidden count cap", b'{"k":0}', b"k" * size)
        raw = b'{"' + b"k" * (size - 6) + b'":0}'
        require(len(raw) == size, "maximal member fixture")
        yield member("maximal matched root-member spelling", raw, b"k" * (size - 6))
    for offset, count in ((0, 0), (0, 1), (1, 0), (MIN, MAX), (MAX, 0)):
        yield Query(
            "actual empty key nested span",
            Case("document", b'{"":0}'),
            Case("key", b"\xff", offset, count, ((1, 0), (0, 0))),
        )
    alphabet = (b"[", b"]", b"{", b"}", b"0", b",", b":", b" ")
    for size in range(3):
        for letters in itertools.product(alphabet, repeat=size):
            raw = b"".join(letters)
            yield member("exhaustive short grammar fragments", raw)
            yield element("exhaustive short grammar fragments", raw)
    rng = random.Random(SEED)
    for _ in range(64):
        pairs = [(rng.choice(texts), rng.choice(values)) for unused in range(rng.randrange(7))]
        raw = (
            b"{"
            + b",".join(
                json.dumps(key, ensure_ascii=bool(rng.randrange(2))).encode() + b":" + value for key, value in pairs
            )
            + b"}"
        )
        for query in (rng.choice(texts), pairs[0][0] if pairs else ""):
            yield member("seeded duplicate-preserving serialized object", raw, query.encode())
        yield element("seeded ordered array", b"[" + b",".join(value for key, value in pairs) + b"]", rng.randrange(8))


def shape_model(status, kind, start, count, error):
    bad = failure("invalid_window")
    if status == S["invalid_window"] or min(start, count, error) < 0 or count > 4096 or start + count > MAX:
        return bad
    if status == 0:
        good_count = (
            (kind in (K["object"], K["array_value"], K["string"]) and count >= 2)
            or (kind == K["number"] and 1 <= count <= 128)
            or (kind in (K["true_value"], K["null_value"]) and count == 4)
            or (kind == K["false_value"] and count == 5)
        )
        return (status, kind, start, count, error) if good_count and error == 0 else bad
    if (
        kind
        or start
        or count
        or (status in (S["invalid_key_window"], S["invalid_index"], S["wrong_root"], S["not_found"]) and error != 0)
    ):
        return bad
    return (status, 0, 0, 0, error)


def shape_tests():
    rows = set()
    edges = (MIN, -1, 0, 1, 2, 3, 4, 5, 6, 127, 128, 129, 4095, 4096, 4097, MAX)
    for kind, count in itertools.product(range(len(KINDS)), edges):
        rows.add((0, kind, 0, count, 0))
    for kind in range(len(KINDS)):
        seed = (0, kind, 7, {0: 0, 1: 2, 2: 2, 3: 2, 4: 1, 5: 4, 6: 5, 7: 4}[kind], 0)
        rows.add(seed)
        for field in (2, 3, 4):
            for edge in edges:
                row = list(seed)
                row[field] = edge
                rows.add(tuple(row))
        for start in (MAX, MAX - 1, MAX - 4, MAX - 5, MAX - 128, MAX - 4096):
            for count in (0, 1, 2, 4, 5, 128, 4096):
                rows.add((0, kind, start, count, 0))
    for status in range(1, len(STATUSES)):
        for error in edges:
            rows.add((status, 0, 0, 0, error))
        for kind in range(len(KINDS)):
            rows.add((status, kind, 0, 0, 7))
        for field in (2, 3):
            for edge in edges:
                row = [status, 0, 0, 0, MAX]
                row[field] = edge
                rows.add(tuple(row))
    for row in sorted(rows):
        status, kind, start, count, error = row
        body = f"const {RESULT} original={RESULT}(std::JsonLookupStatus::{STATUSES[status]},"
        body += f"std::JsonValueKind::{KINDS[kind]},{start},{count},{error});const {RESULT} report=original;"
        yield Test(
            "public copied constructor validates shape without source authority", body + observe(), shape_model(*row)
        )


def lifetime_tests():
    for query in (
        member("expired document and key", b'{"k":[0,1]}'),
        member("expired ambiguity", b'{"k":0,"k":1}'),
        member("expired invalid key", b'{"k":0}', b"\xff"),
        element("expired array", b" [ null, {} ] ", 1),
    ):
        helper = f"auto expired_CASE()->{RESULT}{{" + harness.array(query.document.data)
        args = "borrow_bytes(owner)"
        if query.key is not None:
            helper += harness.array(query.key.data).replace("owner", "keyowner")
            args += ",borrow_bytes(keyowner)"
        call = invocation(query, "borrow_bytes(owner)", "borrow_bytes(keyowner)")
        helper += f"const {RESULT} report={call};return report;}}"
        body = f"const {RESULT} original=expired_CASE();const {RESULT} report=original;" + observe()
        yield Test(query.label, body, query.expected(), helper)


def alias_tests():
    raw = b'{"k":[0,1],"z":2}'
    for key_offset, key_count in ((2, 1), (12, 1), (len(raw), 0), (0, len(raw))):
        body = harness.array(raw)
        body += (
            f"const {RESULT} original=std::lookup_json_member(borrow_bytes(o"
            f"wner),0,{len(raw)},borrow_bytes(owner),{key_offset},{key_count}"
            f");"
        )
        body += f"owner[0]=255u8;const {RESULT} report=original;" + observe()
        yield Test(
            "document and key may synchronously alias one readonly owner",
            body,
            lookup_model(raw, 0, len(raw), raw, key_offset, key_count),
        )


def validator_tests():
    for raw in (b'{"k":0,"k":1}', b'[{"k":[0]},null]', b'{"k":0,}', b'"x"', b"[" * 33 + b"0" + b"]" * 33):
        setup = harness.array(raw) + harness.array(b"k").replace("owner", "keyowner")
        setup += f"const std::JsonResult before=std::validate_json(borrow_bytes(owner),0,{len(raw)});"
        setup += (
            f"const {RESULT} report=std::lookup_json_member(borrow_bytes(own"
            f"er),0,{len(raw)},borrow_bytes(keyowner),0,1);"
        )
        setup += f"const std::JsonResult after=std::validate_json(borrow_bytes(owner),0,{len(raw)});"
        body = setup + "if(field<5){" + observe() + "}i64 selected=field-5;"
        body += "if(field<9){" + profile.observe(True).replace("report.", "before.").replace("field", "selected") + "}"
        body += "selected=field-9;" + profile.observe(True).replace("report.", "after.").replace("field", "selected")
        stats = profile.document_model(raw, 0, len(raw))
        yield Test(
            "existing validator diagnostics token count and depth remain unchanged",
            body,
            lookup_model(raw, 0, len(raw), b"k") + stats + stats,
        )


def all_tests():
    yield from map(source_case, query_cases())
    yield from shape_tests()
    yield from lifetime_tests()
    yield from alias_tests()
    yield from validator_tests()


def rejections(source):
    head = "module rejection;import std.json;import std.binary;import std.byte_buffer;"
    setup = "builtin::array<u8,2> d={123u8,125u8};builtin::array<u8,1> k={107u8};"
    args = ["borrow_bytes(d)", "0", "2", "borrow_bytes(k)", "0", "1"]
    block = re.search(r"class JsonLookupResult\s*\{(.*?)public:", source, re.S)
    require(block is not None, "private lookup report declaration")
    fields = re.findall(r"\b(?:JsonLookupStatus|JsonValueKind|i64)\s+(\w+)\s*;", block.group(1))
    require(len(fields) == 5, "exactly five private copied lookup fields")
    report = f"const {RESULT} r=std::lookup_json_member(" + ",".join(args) + ");"
    for field in fields:
        yield (
            "private lookup report field",
            head + "auto test()->i64{" + setup + report + f"return r.{field};}}",
            "private",
        )
    for method in ("bytes", "value", "size", "token_count", "consumed_bytes", "scalar_or"):
        yield (
            "lookup exposes copied coordinates only",
            head + "auto test()->i64{" + setup + report + f"return r.{method}();}}",
            "unknown",
        )
    for function, arity, positions in (("lookup_json_member", 6, (1, 2, 4, 5)), ("lookup_json_element", 4, (1, 2, 3))):
        base = args if arity == 6 else args[:3] + ["0"]
        for position, wrong in itertools.product(positions, ("0u8", "0u64", "false")):
            actual = list(base)
            actual[position] = wrong
            body = f"const {RESULT} r=std::{function}(" + ",".join(actual) + ");return r.byte_count();}"
            yield "exact signed lookup parameters", head + "auto test()->i64{" + setup + body, "expected i64"
    for position in (0, 3):
        actual = list(args)
        actual[position] = "d" if position == 0 else "k"
        yield (
            "lookup requires explicit readonly byte span",
            head
            + "auto test()->i64{"
            + setup
            + f"const {RESULT} r=std::lookup_json_member("
            + ",".join(actual)
            + ");return r.byte_count();}",
            "span",
        )
    for which in ("d", "k"):
        body = setup + f"const {SPAN} view=borrow_bytes({which});"
        actual = list(args)
        actual[0 if which == "d" else 3] = "view"
        body += (
            f"const {RESULT} r=std::lookup_json_member("
            + ",".join(actual)
            + f");{which}[0]=0u8;return r.byte_count();}}"
        )
        yield (
            "document and query named spans independently freeze their owners",
            head + "auto test()->i64{" + body,
            "span is live",
        )
        body = setup + f"const {SPAN} whole=borrow_bytes({which});const {SPAN} view=whole.subspan(1,0);"
        body += f"const {RESULT} r=std::lookup_json_member(view,0,0,view,0,0);{which}[0]=0u8;return r.byte_count();}}"
        yield "empty nested query or document keeps owner borrowed", head + "auto test()->i64{" + body, "span is live"
    for position, wrong in itertools.product((2, 3, 4), ("0u64", "0u8", "false")):
        actual = ["std::JsonLookupStatus::success", "std::JsonValueKind::number", "0", "1", "0"]
        actual[position] = wrong
        yield (
            "constructor coordinates use exact i64",
            head + "auto test()->i64{" + f"const {RESULT} r={RESULT}(" + ",".join(actual) + ");return 0;}",
            "expected i64",
        )
    for actual in (
        ("std::JsonStatus::success", "std::JsonValueKind::number"),
        ("std::JsonLookupStatus::success", "std::JsonTokenKind::number"),
    ):
        yield (
            "distinct lookup enums cannot be substituted",
            head + "auto test()->i64{" + f"const {RESULT} r={RESULT}({actual[0]},{actual[1]},0,1,0);return 0;}}",
            "expected",
        )
    for private_type in ("JsonWalkRequest", "JsonWalkResult"):
        yield (
            "internal copied walk types are not imported",
            head + f"auto test()->i64{{const std::{private_type} hidden=std::{private_type}();return 0;}}",
            "private type is not imported",
        )
    for helper in sorted(
        set(re.findall(r"\bauto\s+(json_(?:lookup_\w+|walk(?:_\w+)?|query_failure|value_kind|key_equal))\s*\(", source))
    ):
        yield (
            "private lookup helper " + helper,
            head + f"auto test()->i64{{return std::{helper}();}}",
            "private function is not imported",
        )
    yield (
        "lookup cannot introduce retained source fields",
        head + f"class Bad{{{SPAN} source;}};auto test()->i64{{return 0;}}",
        "class fields require",
    )
    for owner in ("document", "key"):
        for operation in (
            f"{owner}.set(0,0u8);",
            f"{owner}.try_resize(9);",
            f"builtin::OwnedBytes moved=move({owner});",
        ):
            body = "builtin::OwnedBytes document=region.try_allocate(8);builtin::OwnedBytes key=region.try_allocate(8);"
            body += f"const {SPAN} view=borrow_bytes({owner});"
            body += (
                f"const {RESULT} r=std::lookup_json_member(view,0,0,view,0,0);" + operation + "return r.byte_count();}"
            )
            yield (
                "lookup does not release a live named owned span",
                head + "auto entry(builtin::ByteRegion region)->i64{" + body,
                "span is live",
            )

    for owner in ("document", "key"):
        body = "builtin::OwnedBytes document=region.try_allocate(8);builtin::OwnedBytes key=region.try_allocate(8);"
        offset = "as_offset(document.try_resize(9))" if owner == "document" else "0"
        key_offset = "as_offset(key.try_resize(9))" if owner == "key" else "0"
        body += (
            f"const {RESULT} r=std::lookup_json_member(borrow_bytes(document"
            f"),{offset},8,borrow_bytes(key),{key_offset},1);return r.byte_c"
            f"ount();}}"
        )
        yield (
            "later argument cannot mutate an earlier borrowed owner",
            head + "auto as_offset(bool ignored)->i64{return 0;}auto entry(builtin::ByteRegion region)->i64{" + body,
            "span is live",
        )


def hosted_program(body, helpers=""):
    return (
        "module lookup_owned;import std.json;import std.binary;import std.byte_buffer;"
        + helpers
        + "auto lookup_owned(builtin::ByteRegion region,i64 n,i64 field)->i64{"
        + body
        + "}"
    )


def hosted_vectors(suite, name, source, vectors):
    directory = codecs.hosted_compile(suite, name, source, "lookup_owned")
    for quota, n, expected, allocations, peak in vectors:
        for field, value in enumerate(expected):
            codecs.hosted_observe(suite, directory, name, quota, n, field, value, allocations, peak)


def hosted_tests(suite):
    # Runtime-sized owners actually exceed the fixed-array maximum. Both query
    # and source extents are checked against logical size, not physical capacity.
    doc = b'{"k":[0,1]}'
    setup = "builtin::OwnedBytes document=region.try_allocate(n);builtin::OwnedBytes key=region.try_allocate(n);"
    setup += (
        "if(!document.ok() || !key.ok()){return -901;}i64 i=0;while(i<n){document.set(i,32u8);key.set(i,107u8);i=i+1;}"
    )
    setup += "".join(f"document.set(n-{len(doc)}+{i},{byte}u8);" for i, byte in enumerate(doc))
    for name, args, key_start, key_count, count in (
        ("hosted-full-document-cap", "borrow_bytes(document),0,n,borrow_bytes(key),n-1,1", "tail", 1, "full"),
        (
            "hosted-selected-large-owner",
            f"borrow_bytes(document),n-{len(doc)},{len(doc)},borrow_bytes(key),n-1,1",
            "tail",
            1,
            "tail",
        ),
        ("hosted-key-cap", f"borrow_bytes(document),n-{len(doc)},{len(doc)},borrow_bytes(key),0,n", 0, "full", "tail"),
    ):
        source = hosted_program(setup + f"const {RESULT} report=std::lookup_json_member({args});" + observe())
        vectors = []
        for n in (4095, 4096, 4097, 8193):
            raw = b" " * (n - len(doc)) + doc
            wanted = lookup_model(
                raw,
                0 if count == "full" else n - len(doc),
                n if count == "full" else len(doc),
                b"k" * n,
                n - 1 if key_start == "tail" else 0,
                n if key_count == "full" else 1,
            )
            vectors.append((2 * n, n, wanted, 2, 2))
        hosted_vectors(suite, name, source, vectors)

    n = 8193
    raw = bytearray(b" " * n)
    raw[4096 : 4096 + len(doc)] = doc
    raw[0] = 255
    key = bytearray(b"k" * n)
    key[4096] = 255
    setup = f"builtin::OwnedBytes document=region.try_allocate({n});builtin::OwnedBytes key=region.try_allocate({n});"
    setup += (
        f"i64 i=0;while(i<{n}){{document.set(i,32u8);key.set(i,107u8);i="
        f"i+1;}}document.set(0,255u8);key.set(4096,255u8);"
    )
    setup += "".join(f"document.set({4096 + i},{byte}u8);" for i, byte in enumerate(doc))
    specs = (
        (MIN, MAX, MAX, MAX),
        (0, 4097, MAX, MAX),
        (1, 4097, 0, 4097),
        (4096, len(doc), MAX, MAX),
        (4096, len(doc), 1, 4097),
        (4096, len(doc), 4096, 1),
        (4096, len(doc), 0, 4096),
        (4096, len(doc), 8192, 1),
        (8193, 0, 0, 1),
        (4096, len(doc), 8193, 0),
    )
    body, vectors = setup, []
    for index, (start, count, ks, kc) in enumerate(specs):
        body += (
            f"if(n=={index}){{const {RESULT} report=std::lookup_json_member("
            f"borrow_bytes(document),{start},{count},borrow_bytes(key),{ks},"
            f"{kc});" + observe() + "}"
        )
        vectors.append((2 * n, index, lookup_model(raw, start, count, key, ks, kc), 2, 2))
    body += f"const {RESULT} report=std::lookup_json_element(borrow_bytes(document),1,4097,-1);" + observe()
    vectors.append((2 * n, len(specs), lookup_model(raw, 1, 4097, index=-1), 2, 2))
    hosted_vectors(suite, "hosted-full-precedence-and-endpoints", hosted_program(body), vectors)

    doc = b'{"":0,"k":[1,2],"\xc2\xa2":3}'
    setup = "builtin::OwnedBytes d=region.try_allocate(8193);builtin::OwnedBytes k=region.try_allocate(8193);"
    setup += "d.set(0,255u8);d.set(8192,255u8);k.set(0,107u8);k.set(8192,255u8);"
    setup += (
        "std::ByteBuffer document=std::ByteBuffer(region,move(d));std::ByteBuffer key=std::ByteBuffer(region,move(k));"
    )
    setup += "".join(f"document.try_append({byte}u8);" for byte in doc)
    setup += "if(n==1){key.try_append(107u8);}if(n==2){key.try_append(107u8);key.clear();}if(n==3){document.clear();}"
    setup += "if(n==4){document.try_truncate(document.size()-1);}"
    setup += "if(n==5){key.try_append(194u8);key.try_append(162u8);key.try_truncate(1);}"
    setup += "if(n==6){key.try_append(107u8);key.try_append(255u8);key.try_truncate(1);}"
    setup += (
        f"const {RESULT} report=std::lookup_json_member(document.bytes(),0,document.size(),key.bytes(),0,key.size());"
    )
    vectors = []
    for mode in range(7):
        visible_doc = b"" if mode == 3 else doc[:-1] if mode == 4 else doc
        visible_key = b"k" if mode in (1, 6) else b"\xc2" if mode == 5 else b""
        vectors.append((16386, mode, lookup_model(visible_doc, 0, len(visible_doc), visible_key), 2, 2))
    hosted_vectors(suite, "hosted-hidden-document-and-key-capacity", hosted_program(setup + observe()), vectors)

    # Returning only copied coordinates ends both synchronous parameter borrows.
    # Mutate, resize and move the actual owners before reading any report field.
    helper = (
        f"auto copied({SPAN} document,{SPAN} key)->{RESULT}{{const {RESULT}"
        f" report=std::lookup_json_member(document,0,document.size(),key"
        f",0,key.size());return report;}}"
    )
    setup = (
        f"builtin::OwnedBytes document=region.try_allocate({len(doc)});builtin::OwnedBytes key=region.try_allocate(1);"
    )
    setup += "".join(f"document.set({i},{byte}u8);" for i, byte in enumerate(doc)) + "key.set(0,107u8);"
    setup += f"const {RESULT} original=copied(borrow_bytes(document),borrow_bytes(key));"
    setup += (
        "document.set(0,255u8);key.set(0,255u8);if(!document.try_resize(8193) || !key.try_resize(8193)){return -902;}"
    )
    setup += "builtin::OwnedBytes moved_document=move(document);builtin::OwnedBytes moved_key=move(key);"
    setup += f"moved_document.set(0,0u8);moved_key.set(0,0u8);const {RESULT} report=original;"
    hosted_vectors(
        suite,
        "hosted-copy-survives-both-owner-mutations",
        hosted_program(setup + observe(), helper),
        [(16386, 0, lookup_model(doc, 0, len(doc), b"k"), 4, 2)],
    )

    # End real owner lifetimes in a nested block. A resource function cannot
    # return a copied aggregate in the existing compiler; no such extension is
    # needed to show that scalar-only lookup reports outlive both allocations.
    body = setup.split(f"const {RESULT} original=")[0]
    body += f"const {RESULT} original=copied(borrow_bytes(document),borrow_bytes(key));"
    body += "{builtin::OwnedBytes moved_document=move(document);builtin::OwnedBytes moved_key=move(key);}"
    body += f"const {RESULT} report=original;" + observe()
    hosted_vectors(
        suite,
        "hosted-copy-outlives-both-owner-scopes",
        hosted_program(body, helper),
        [(16386, 0, lookup_model(doc, 0, len(doc), b"k"), 2, 2)],
    )
    print(f"PASS lookup hosted ownership: {suite.hosted_observations} full-width values with exact cleanup", flush=True)


def example_tests(suite):
    source = (suite.root / "library/examples/json_lookup.au").read_text()
    wire = re.search(r"\bwire\s*=\s*\{(.*?)\};", source, re.S)
    require(wire is not None, "example wire fixture is present")
    raw = bytes(map(int, re.findall(r"(\d+)u8", wire.group(1))))
    report = lookup_model(raw, 0, len(raw), b"payload")
    extents = list(report[2:4])
    report = lookup_model(raw, report[2], report[3], b"items")
    extents.extend(report[2:4])
    report = lookup_model(raw, report[2], report[3], index=1)
    extents.extend(report[2:4])
    report = lookup_model(raw, report[2], report[3], b"name")
    extents.extend(report[2:4])
    extents.append(len(raw))
    scalars = [ord(char) for char in json.loads(raw[report[2] : report[2] + report[3]])]
    require(extents == [17, 47, 26, 37, 32, 30, 40, 21, 81], "independent example nested extents")
    require(scalars == [65, 0, 128512], "independent example scalar sequence")
    directory = codecs.hosted_compile(suite, "hosted-real-example", source, "json_lookup_example")
    for capacity in (0, 81, 128):
        expected = [(-index - 1, value) for index, value in enumerate(extents)]
        expected += list(enumerate(scalars)) + [(MIN, -8), (3, -8), (MAX, -8)]
        for observation, value in expected:
            codecs.hosted_observe(
                suite,
                directory,
                "actual example complete nested coordinates and scalars",
                256,
                capacity,
                observation,
                value,
                2 if capacity < 81 else 1,
                1,
            )
    for quota, capacity, fail_after, value, allocations in (
        (256, -1, None, -1, 0),
        (80, 81, None, -1, 0),
        (80, 0, None, -2, 1),
        (256, 81, 0, -1, 0),
        (256, 0, 1, -2, 1),
        (81, 81, 1, 17, 1),
    ):
        codecs.hosted_observe(
            suite,
            directory,
            "actual example recoverable allocation failure and cleanup",
            quota,
            capacity,
            -1,
            value,
            allocations,
            int(allocations > 0),
            fail_after,
        )


def compare(observed, expected):
    require(len(observed) == len(expected), "complete observation count")
    require(observed == expected, "full-width lookup observation mismatch")


def self_test():
    require(lookup_model(b'{"k":0,"\\u006b":1}', 0, 18, b"k") == failure("ambiguous", 7), "escaped duplicate quote")
    raw = b'\xff {"k" : [0, {"x":1}]} \xff'
    require(lookup_model(raw, 1, len(raw) - 2, b"k") == (0, K["array_value"], 9, 12, 0), "exact nested value extent")
    require(
        lookup_model(b'{"k":0,"k":1,}', 0, 14, b"k")[0] == S["invalid_structure"], "full validation before duplicates"
    )
    require(lookup_model(b"[", 0, 1, index=MIN) == failure("invalid_index"), "index before validation")
    require(lookup_model(b"[", 0, 1, b"\xe0\xa0") == failure("invalid_key", 2), "viable key endpoint")
    require(lookup_model(b"[", 0, 1, b"\xe0\x9f") == failure("invalid_key", 0), "impossible key lead")
    require(lookup_model(b"[", MIN, MAX, b"\xff", MAX, MAX) == failure("invalid_window"), "document window wins")
    require(lookup_model(b"\xff" * 4097, 0, 4097, b"\xff", MAX, MAX) == failure("input_limit"), "document cap wins")
    require(lookup_model(b"[", 0, 1, b"\xff" * 4097) == failure("key_limit"), "key cap before key decoding")
    controls = 0
    for expected in ((0, K["number"], MAX - 1, 1, 0), failure("invalid_key", MAX), failure("ambiguous", 7)):
        for field, mask in itertools.product(range(5), (1, 1 << 32, 1 << 63)):
            mutant = list(expected)
            mutant[field] ^= mask
            caught = False
            try:
                compare(mutant, list(expected))
            except AssertionError:
                caught = True
            require(caught, "comparator bit mutation escaped")
            controls += 1
        for mutant in (list(expected[:-1]), [*expected, 0]):
            caught = False
            try:
                compare(mutant, list(expected))
            except AssertionError:
                caught = True
            require(caught, "comparator length mutation escaped")
            controls += 1
    return controls


def oracle_audit():
    counts = dict(
        valid_documents=0,
        syntax_failures=0,
        policy_or_window=0,
        selected_ranges=0,
        ambiguities=0,
        invalid_keys=0,
        no_normalization=True,
        duplicate_pairs_preserved=True,
    )
    for query in query_cases():
        result = query.expected()
        counts["selected_ranges"] += result[0] == 0
        counts["ambiguities"] += result[0] == S["ambiguous"]
        counts["invalid_keys"] += result[0] == S["invalid_key"]
        case = query.document
        document = profile.document_model(case.span(), case.offset, case.extent())
        if document[0] in (
            profile.S["invalid_window"],
            profile.S["input_limit"],
            profile.S["number_limit"],
            profile.S["token_limit"],
            profile.S["depth_limit"],
        ):
            counts["policy_or_window"] += 1
            continue
        accepted = True
        try:
            decode(case.span()[case.offset : case.offset + case.extent()])
        except (ValueError, UnicodeError, AssertionError):
            accepted = False
        require(accepted == (document[0] == 0), "independent whole-decoder grammar audit: " + query.label)
        counts["valid_documents" if accepted else "syntax_failures"] += 1
        if accepted:
            root_ranges(case.span()[case.offset : case.offset + case.extent()])
    return counts


class Suite(profile.Suite):
    def __init__(self, args, identity):
        super().__init__(args, identity)
        self.hosted_observations = 0
        for name in (
            "tests/compiler/json_lookup.py",
            "tests/compiler/json_codecs.py",
            "tests/compiler/owned_bytes.py",
            "tests/compiler/unsigned_oracle.py",
            "runtime/hosted_bytes.cpp",
            "runtime/hosted_bytes.hpp",
        ):
            self.inputs[name] = harness.sha(self.root / name)

    def batch(self, items):
        super().batch(items)
        # The mutation-controlled comparator also checks the actual native byte
        # stream, independently of the inherited harness receipt construction.
        raw = (self.output / f"batch-{self.batches - 1:04d}" / "native.stdout").read_bytes()
        require(len(raw) % 8 == 0, "native fields are complete i64 words")
        observed = [int.from_bytes(raw[index : index + 8], "little", signed=True) for index in range(0, len(raw), 8)]
        compare(observed, [value for item in items for value in item.expected])


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
            f"PASS independent ordered-pair/range/grammar lookup oracles: {controls} comparator controls; "
            + json.dumps(audit, sort_keys=True)
        )
        return
    source = (args.repo_root / "library/std/json.au").read_text()
    if args.describe:
        groups = list(profile.batches(all_tests()))
        print(
            json.dumps(
                dict(
                    cases=sum(map(len, groups)),
                    batches=len(groups),
                    full_64bit_observations=sum(len(item.expected) for group in groups for item in group),
                    rejections=len(list(rejections(source))),
                    compiler_free_mutation_controls=controls,
                    independent_oracle_audit=audit,
                    random_seed=SEED,
                    budget_mib=args.budget_mib,
                ),
                indent=2,
            )
        )
        return
    require(args.compiler is not None, "compiler required")
    if args.artifacts is None:
        args.artifacts = pathlib.Path(tempfile.mkdtemp(prefix="aurora-json-lookup-")) / "gate"
        print("Retained JSON lookup artifacts: " + str(args.artifacts), flush=True)
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
        independent_oracle_audit=audit,
        limits=[
            "Focused lookup gate, not full-native or sanitizer qualification",
            "Fixed-array windows are supplemented by real 8193-byte document and key owners",
            "Constructors certify copied result shape, not source provenance or validity",
            "No DOM, recursive selector, normalization, source-view return or new compiler semantics",
        ],
    )
    try:
        for group in profile.batches(all_tests()):
            suite.batch(group)
        for item in rejections(source):
            suite.reject(*item)
        hosted_tests(suite)
        example_tests(suite)
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
        errors = finalize_selected_identity(identity, manifest)
        manifest["compiler_identity"] = identity.record()
        manifest.update(
            completed_cases=suite.count,
            completed_rejections=suite.rejections,
            completed_hosted_observations=suite.hosted_observations,
            allocated_bytes=suite.budget(0),
        )
        (suite.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        require(not errors, "; ".join(errors))


if __name__ == "__main__":
    main()
