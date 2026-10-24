#!/usr/bin/env python3
"""std.utf8_lines through one compiled driver fed every case as a record.

Line expectations come from CPython's strict UTF-8 decoder applied to the bytes
through the first LF; repeated-scan traces repeat that reference. Public-report
masking has no standard reference; its expectations are the reviewed golden file
golden/utf8_lines_reports.jsonl. Rejections compile one source each.
"""

from __future__ import annotations

import argparse
import itertools
from pathlib import Path
import random

import runtime_records as records

MIN, MAX = records.MIN, records.MAX
GOLDEN = Path(__file__).with_name("golden")
STATUSES = ("success", "end_of_input", "out_of_range", "invalid_sequence", "truncated")
ENDINGS = ("none", "lf", "crlf")
SCALARS = ("operation", "length", "offset", "count", "status", "ending")
SPAN = "builtin::span<const u8>"
RESULT = "std::Utf8LineResult"


def expected(data, offset, count):
    if offset < 0 or count < 0 or offset > len(data) or count > len(data) - offset:
        return (2, 0, 0, 0)
    if count == 0:
        return (1, 0, 0, 0)
    window = bytes(data[offset : offset + count])
    before, found, after = window.partition(b"\n")
    consumed = before + found
    try:
        consumed.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        return (4 if error.reason == "unexpected end of data" else 3, 0, 0, 0)
    ending = 2 if found and before.endswith(b"\r") else 1 if found else 0
    return (0, len(consumed) - ending, len(consumed), ending)


def trace(raw):
    """Repeated reads over the whole input: final status, lines, content and consumed bytes."""
    used = lines = content = 0
    status = 1
    while used < len(raw):
        status, line_content, consumed, _ = expected(raw, used, len(raw) - used)
        if status:
            break
        used += consumed
        content += line_content
        lines += 1
    if used == len(raw):
        status = 1
    return (status, lines, content, used)


def cases():
    seeds = (
        b"",
        b"A",
        b"\n",
        b"\r",
        b"\r\n",
        b"A\n",
        b"A\r\n",
        b"A\r",
        b"\n\n",
        b"\r\r\n",
        b"A\n\xff",
        b"A\r\n\xe2",
        b"\n\xff",
        b"\0\x1b\xef\xbb\xbf\n",
        b"\xc2\x85\xe2\x80\xa8\xe2\x80\xa9",
        b"A\xc2\xa2\r\nB\xe2\x82\xac\n\xf0\x9f\x99\x82",
    )
    for data in seeds:
        owner = b"\xff" + data + b"\xff"
        for offset in range(len(data) + 1):
            for count in range(len(data) - offset + 1):
                yield ("all seed byte windows", owner, 1 + offset, count)
    for byte in range(256):
        for ending in (b"", b"\n", b"\r\n"):
            raw = bytes((byte,)) + ending
            yield ("every byte before final/LF/CRLF", raw, 0, len(raw))
    # Incomplete leading sequences followed by a delimiter must be invalid,
    # never accepted by treating LF as an independent boundary before validation.
    bad = (
        b"\xc0",
        b"\xc1",
        b"\xc2",
        b"\xdf",
        b"\xe0",
        b"\xe0\xa0",
        b"\xe0\x9f",
        b"\xed\xa0",
        b"\xed\x9f",
        b"\xe1\x80",
        b"\xf0\x90",
        b"\xf0\x90\x80",
        b"\xf4\x8f\xbf",
        b"\xf4\x90",
        b"\xf5",
        b"\x80",
        b"\xff",
    )
    for fragment, prefix, suffix in itertools.product(bad, (b"", b"Z", b"\xe2\x82\xac"), (b"", b"\n", b"\r\n")):
        raw = prefix + fragment + suffix
        yield ("malformed or incomplete first line", raw, 0, len(raw))
        if suffix:
            raw = b"valid" + suffix + fragment
            yield ("unconsumed invalid suffix is deferred", raw, 0, len(raw))
    scalars = (
        0,
        27,
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
        0x2028,
        0x2029,
        0x85,
    )
    for scalar, suffix in itertools.product(scalars, (b"", b"\n", b"\r\n")):
        raw = chr(scalar).encode() + suffix
        yield ("scalar policies and boundaries", b"\xff" + raw + b"\xff", 1, len(raw))
    for offset, count in itertools.product((MIN, -1, 0, 1, 2, 3, 4, MAX), repeat=2):
        yield ("signed window extremes", b"\xff\nA", offset, count)
    rng = random.Random(20261005)
    for _ in range(128):
        raw = "".join(chr(rng.choice((*scalars, 10, 13))) for _ in range(rng.randrange(20))).encode()
        yield ("seeded mixed valid sequences", b"\xff" + raw + b"\xff", 1, len(raw))
    for _ in range(128):
        raw = bytes(rng.randrange(256) for _ in range(rng.randrange(16)))
        yield ("seeded arbitrary bytes", raw or b"\xff", 0, len(raw))
    for data in (
        b"A" * 4096,
        b"A" * 4095 + b"\n",
        b"A" * 4094 + b"\r\n",
        b"\n" + b"\xff" * 4095,
        b"A" * 4092 + chr(0x10FFFF).encode(),
        b"A" * 4093 + b"\xe2\x82\n",
    ):
        yield ("maximum 4096-byte owner", data, 0, len(data))


TRACES = (
    b"",
    b"\n",
    b"\n\n",
    b"A\r\nB\nC",
    b"A\rB\r\n\r",
    b"\xe2\x82\xac\n\xf0\x9f\x99\x82",
    b"\0\n\xef\xbb\xbf\r\n\x1b",
    b"good\n\xff",
    b"\n\xc2",
    b"A\nB\r\n\xe2\x82",
    b"\n" * 4096,
)


def observe():
    s = "if(field==0){"
    for value, status in enumerate(STATUSES):
        s += f"if(report.status()==std::Utf8LineStatus::{status}){{return {value};}}"
    s += "return -777;}if(field==1){return report.content_bytes();}if(field==2){return report.consumed_bytes();}"
    for value, ending in enumerate(ENDINGS):
        s += f"if(report.ending()==std::Utf8LineEnding::{ending}){{return {value};}}"
    return s + "return -778;"


def driver_source():
    declarations, initializers, reader = records.byte_fields()
    source = "module utf8_lines_driver;import std.utf8_lines;\nclass LineInput{" + declarations
    source += "".join(f"i64 {name};" for name in SCALARS)
    source += "public:LineInput():" + ",".join(initializers + [f"{name}(0)" for name in SCALARS]) + "{}" + reader
    # Spans are parameters, so each borrow ends before the owner is mutated.
    source += f"auto line({SPAN} bytes,i64 start,i64 size) const -> {RESULT} {{"
    source += f"const {SPAN} whole=bytes.subspan(0,length);"
    source += f"const {RESULT} result=std::read_utf8_line(whole,start,size);return result;}}"
    source += "auto selected_status() const -> std::Utf8LineStatus {"
    source += "".join(f"if(status=={n}){{return std::Utf8LineStatus::{name};}}" for n, name in enumerate(STATUSES))
    source += "return std::Utf8LineStatus::out_of_range;}"
    source += "auto selected_ending() const -> std::Utf8LineEnding {"
    source += "".join(f"if(ending=={n}){{return std::Utf8LineEnding::{name};}}" for n, name in enumerate(ENDINGS))
    source += "return std::Utf8LineEnding::none;}"
    load = records.ZERO_OWNER + "i64 at=0;while(at<length){owner[at]=input_byte(at);at=at+1;}"
    source += "auto entry(i64 field) const -> i64 {if(operation==0){" + load
    source += f"const {RESULT} original=line(borrow_bytes(owner),offset,count);"
    source += "at=0;while(at<length){if(owner[at]!=input_byte(at)){return -779;}at=at+1;}"
    source += f"owner[0]=0u8;const {RESULT} report=original;" + observe() + "}"
    source += f"if(operation==1){{const {RESULT} report={RESULT}(selected_status(),count,selected_ending());"
    source += observe() + "}"
    # Repeated scanning: progress, LF/CRLF reconstruction from the owner and
    # zeroed failure reports, then status, lines, content and consumed bytes.
    source += load + "i64 used=0;i64 lines=0;i64 content=0;i64 outcome=1;bool stopped=false;while(!stopped){"
    source += f"const {RESULT} next=line(borrow_bytes(owner),used,length-used);"
    source += "if(next.status()==std::Utf8LineStatus::success){if(next.consumed_bytes()<=0){return -781;}"
    source += "if(next.consumed_bytes()>length-used){return -782;}"
    source += "if(next.ending()==std::Utf8LineEnding::lf){if(owner[used+next.content_bytes()]!=10u8){return -783;}}"
    source += (
        "if(next.ending()==std::Utf8LineEnding::crlf){if(owner[used+next.content_bytes()]!=13u8){return -784;}"
        "if(owner[used+next.content_bytes()+1]!=10u8){return -785;}}"
    )
    source += "content=content+next.content_bytes();used=used+next.consumed_bytes();lines=lines+1;}else{"
    for number, name in enumerate(STATUSES[1:], 1):
        source += f"if(next.status()==std::Utf8LineStatus::{name}){{outcome={number};}}"
    source += (
        "if(next.content_bytes()!=0){return -786;}if(next.consumed_bytes()!=0){return -787;}"
        "if(next.ending()!=std::Utf8LineEnding::none){return -788;}stopped=true;}}"
    )
    source += "if(field==0){return outcome;}if(field==1){return lines;}if(field==2){return content;}return used;}};\n"
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    args = parser.parse_args()
    with records.scratch("utf8-lines") as scratch:
        driver = records.Driver(args.compiler, scratch)
        program = driver.build(driver_source(), "LineInput")
        rows = [
            (
                label,
                program.pack(data=data, length=len(data), offset=offset, count=count),
                expected(data, offset, count),
            )
            for label, data, offset, count in cases()
        ]
        reports = records.load_jsonl(GOLDEN / "utf8_lines_reports.jsonl")
        rows += [
            (
                row["label"],
                program.pack(operation=1, status=row["status"], count=row["count"], ending=row["ending"]),
                row["expected"],
            )
            for row in reports
        ]
        rows += [
            (
                "repeated scanning/progress/reconstruction",
                program.pack(data=raw, operation=2, length=len(raw)),
                trace(raw),
            )
            for raw in TRACES
        ]
        count, observations = program.check(rows, scratch)
        rejections = records.load_jsonl(GOLDEN / "utf8_lines_rejections.jsonl")
        for row in rejections:
            driver.reject(row["label"], row["source"], row["diagnostic"])
    print(f"PASS UTF-8 lines: {count} cases, {observations} i64 observations, {len(rejections)} rejections")


if __name__ == "__main__":
    main()
