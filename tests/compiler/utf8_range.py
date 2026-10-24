#!/usr/bin/env python3
"""std.utf8_range through one compiled driver fed every case as a record.

Subrange expectations come from CPython's strict UTF-8 decoder and string
slicing, never from the library's byte scan. Public-report masking has no
standard reference; its expectations are the reviewed golden file
golden/utf8_range_reports.jsonl. Rejections compile one source each.
"""

from __future__ import annotations

import argparse
import itertools
from pathlib import Path
import random

import runtime_records as records

MIN, MAX = records.MIN, records.MAX
GOLDEN = Path(__file__).with_name("golden")
STATUSES = ("success", "out_of_range", "invalid_sequence", "truncated")
SCALARS = ("operation", "length", "offset", "count", "first", "scalars", "status")
SPAN = "builtin::span<const u8>"
RESULT = "std::Utf8RangeResult"


def expected(data, offset, count, first, length):
    if first < 0 or length < 0 or offset < 0 or count < 0 or offset > len(data) or count > len(data) - offset:
        return (1, 0, 0)
    try:
        text = bytes(data[offset : offset + count]).decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        return (3 if error.reason == "unexpected end of data" else 2, 0, 0)
    if first > len(text) or length > len(text) - first:
        return (1, 0, 0)
    return (0, len(text[:first].encode("utf-8")), len(text[first : first + length].encode("utf-8")))


def cases():
    scalars = (
        0,
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
        0xFDD0,
        0x0378,
        0x0301,
        0x200D,
        0x1F642,
    )
    mixed = "".join(map(chr, scalars)).encode("utf-8")
    for first in range(len(scalars) + 2):
        for length in range(len(scalars) + 2):
            yield ("mixed scalar interval", b"\xff" + mixed + b"\xff", 1, len(mixed), first, length)
    for value in range(256):
        for first, length in ((0, 0), (0, 1), (1, 0)):
            yield ("every single byte", bytes((value,)), 0, 1, first, length)
    # Every byte window of a representative mixed-width sequence. These include
    # starts in continuation bytes and viable versus impossible truncated tails.
    window = b"A\xc2\xa2\xe2\x82\xac\xf0\x9f\x99\x82Z"
    for offset in range(len(window) + 1):
        for count in range(len(window) - offset + 1):
            for first, length in ((0, 0), (0, 1), (1, 1), (2, 0)):
                yield ("all mixed byte windows", window, offset, count, first, length)
    malformed = (
        b"\x80",
        b"\xbf",
        b"\xc0\x80",
        b"\xc1\xbf",
        b"\xc2",
        b"\xc2A",
        b"\xe0",
        b"\xe0\x9f",
        b"\xe0\xa0",
        b"\xed\xa0",
        b"\xed\xa0\x80",
        b"\xed\xbf\xbf",
        b"\xe1\x80A",
        b"\xf0",
        b"\xf0\x8f",
        b"\xf0\x90",
        b"\xf1\x80\x80",
        b"\xf4\x8f\xbf",
        b"\xf4\x90",
        b"\xf4\x90\x80\x80",
        b"\xf5",
        b"\xff",
        b"\xe1\x80\xff",
        b"\xf1\x80A",
    )
    for bad in malformed:
        for prefix in (b"", b"A", b"\xc2\xa2Z"):
            for first, length in ((0, 0), (0, 1), (1, 0), (MAX, MAX)):
                data = prefix + bad
                yield ("invalid whole window suppresses early match", data, 0, len(data), first, length)
    base = (b"A\xc2\xa2Z", 0, 4, 1, 1)
    for dimension in range(1, 5):
        for extreme in (MIN, -1, 0, 1, 2, 3, 4, 5, MAX):
            args = list(base)
            args[dimension] = extreme
            yield ("signed edge dimension", *args)
    for offset, count, first, length in itertools.product((MIN, MAX), repeat=4):
        yield ("combined signed extremes", b"\xff", offset, count, first, length)
    for first, length in ((-1, 0), (0, -1), (MAX, 0), (0, MAX)):
        yield ("range versus malformed precedence", b"\xff", 0, 1, first, length)
    for value in scalars:
        raw = chr(value).encode("utf-8")
        for first, length in ((0, 0), (0, 1), (1, 0), (1, 1)):
            yield ("scalar boundary value", b"\xff" + raw + b"\xff", 1, len(raw), first, length)
    rng = random.Random(20261004)
    for _ in range(160):
        values = [rng.choice(scalars) for _ in range(rng.randrange(17))]
        raw = "".join(map(chr, values)).encode("utf-8")
        yield ("seeded valid mixed scalars", b"\xff" + raw + b"\xff", 1, len(raw), rng.randrange(20), rng.randrange(20))
    for _ in range(128):
        raw = bytes(rng.randrange(256) for _ in range(rng.randrange(9)))
        yield ("seeded arbitrary bytes", raw or b"\xff", 0, len(raw), rng.randrange(4), rng.randrange(4))
    for first, length in ((0, 0), (0, 4093), (4092, 1), (4093, 0), (4093, 1), (MAX, MAX)):
        yield ("maximum 4096-byte owner", b"A" * 4092 + chr(0x10FFFF).encode(), 0, 4096, first, length)


def observe():
    body = "if(field==0){"
    for number, status in enumerate(STATUSES):
        body += f"if(report.status()==std::Utf8RangeStatus::{status}){{return {number};}}"
    return body + "return -777;}if(field==1){return report.byte_offset();}return report.byte_count();"


def driver_source():
    declarations, initializers, reader = records.byte_fields()
    source = "module utf8_range_driver;import std.utf8_range;\nclass RangeInput{" + declarations
    source += "".join(f"i64 {name};" for name in SCALARS)
    source += "public:RangeInput():" + ",".join(initializers + [f"{name}(0)" for name in SCALARS]) + "{}" + reader
    # The span is a parameter, so its borrow ends before the owner is mutated.
    source += f"auto subrange({SPAN} bytes) const -> {RESULT} {{const {SPAN} whole=bytes.subspan(0,length);"
    source += f"const {RESULT} result=std::utf8_subrange(whole,offset,count,first,scalars);return result;}}"
    source += "auto selected_status() const -> std::Utf8RangeStatus {"
    source += "".join(f"if(status=={n}){{return std::Utf8RangeStatus::{name};}}" for n, name in enumerate(STATUSES))
    source += "return std::Utf8RangeStatus::out_of_range;}"
    source += "auto entry(i64 field) const -> i64 {if(operation==0){" + records.ZERO_OWNER
    source += "i64 at=0;while(at<length){owner[at]=input_byte(at);at=at+1;}"
    source += f"const {RESULT} original=subrange(borrow_bytes(owner));"
    source += "at=0;while(at<length){if(owner[at]!=input_byte(at)){return -778;}at=at+1;}"
    # Mutation after the call-bounded borrow; the saved report is copied data.
    source += f"owner[0]=0u8;const {RESULT} report=original;" + observe() + "}"
    source += f"const {RESULT} original={RESULT}(selected_status(),offset,count);"
    source += f"const {RESULT} report=original;" + observe() + "}};\n"
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    args = parser.parse_args()
    with records.scratch("utf8-range") as scratch:
        driver = records.Driver(args.compiler, scratch)
        program = driver.build(driver_source(), "RangeInput")
        rows = [
            (
                label,
                program.pack(data=data, length=len(data), offset=offset, count=count, first=first, scalars=length),
                expected(data, offset, count, first, length),
            )
            for label, data, offset, count, first, length in cases()
        ]
        reports = records.load_jsonl(GOLDEN / "utf8_range_reports.jsonl")
        rows += [
            (
                row["label"],
                program.pack(operation=1, status=row["status"], offset=row["offset"], count=row["count"]),
                row["expected"],
            )
            for row in reports
        ]
        count, observations = program.check(rows, scratch)
        rejections = records.load_jsonl(GOLDEN / "utf8_range_rejections.jsonl")
        for row in rejections:
            driver.reject(row["label"], row["source"], row["diagnostic"])
    print(f"PASS UTF-8 ranges: {count} cases, {observations} i64 observations, {len(rejections)} rejections")


if __name__ == "__main__":
    main()
