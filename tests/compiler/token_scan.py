#!/usr/bin/env python3
"""std.token_scan through one compiled driver fed every case as a record.

Expected reports are the reviewed golden file golden/token_scan.jsonl, frozen
from the earlier independent regex model after it agreed with native results.
Rejections compile one source each; examples/token_scan.au must return 42.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import runtime_records as records

GOLDEN = Path(__file__).with_name("golden")
STATUSES = ("success", "end_of_input", "invalid_byte", "invalid_window")
KINDS = ("none", "identifier", "digit_word", "punctuation", "operator_pair")
ACCESSORS = ("byte_offset", "byte_count", "consumed_bytes", "skipped_lf")
OPERATIONS = ("scan", "expired", "report", "trace")
SCALARS = (
    "operation",
    "length",
    "offset",
    "count",
    "windows",
    "first_offset",
    "first_count",
    "second_offset",
    "second_count",
    "status",
    "kind",
    "consumed",
    "lf",
)
SPAN = "builtin::span<const u8>"
RESULT = "std::TokenResult"


def observe(selector="field"):
    body = f"if({selector}==0){{"
    for number, status in enumerate(STATUSES):
        body += f"if(report.status()==std::TokenStatus::{status}){{return {number};}}"
    body += f"return -777;}}if({selector}==1){{"
    for number, kind in enumerate(KINDS):
        body += f"if(report.kind()==std::TokenKind::{kind}){{return {number};}}"
    body += "return -778;}"
    for number, accessor in enumerate(ACCESSORS, 2):
        body += f"if({selector}=={number}){{return report.{accessor}();}}"
    return body + "return -779;"


# The owner must be unchanged by the readonly scan; the copied report must not
# depend on it afterwards.
PRESERVED = (
    "i64 check=0;while(check<length){if(owner[check]!=input_byte(check)){return -780;}check=check+1;}"
    f"owner[0]=0u8;const {RESULT} report=original;"
)
LOAD = records.ZERO_OWNER + "i64 at=0;while(at<length){owner[at]=input_byte(at);at=at+1;}"


def driver_source():
    declarations, initializers, reader = records.byte_fields()
    source = "module token_scan_driver;import std.token_scan;\nclass TokenInput{" + declarations
    source += "".join(f"i64 {name};" for name in SCALARS)
    source += "public:TokenInput():" + ",".join(initializers + [f"{name}(0)" for name in SCALARS]) + "{}"
    source += reader
    # Scanning takes its span as a parameter, so the borrow ends with the call.
    source += f"auto scan({SPAN} bytes) const -> {RESULT} {{const {SPAN} whole=bytes.subspan(0,length);"
    source += f"if(windows==0){{const {RESULT} direct=std::next_token(whole,offset,count);return direct;}}"
    source += f"const {SPAN} view0=whole.subspan(first_offset,first_count);"
    source += f"const {SPAN} view1=view0.subspan(second_offset,second_count);"
    source += f"const {RESULT} nested=std::next_token(view1,offset,count);return nested;}}"
    source += f"auto step({SPAN} bytes, i64 used) const -> {RESULT} {{const {SPAN} whole=bytes.subspan(0,length);"
    source += f"const {RESULT} result=std::next_token(whole,used,length-used);return result;}}"
    # The source owner is local to this call and destroyed before observation.
    source += f"auto expired() const -> {RESULT} {{" + LOAD
    source += f"const {SPAN} all=borrow_bytes(owner);const {SPAN} whole=all.subspan(0,length);"
    source += f"const {RESULT} result=std::next_token(whole,0,length);return result;}}"
    source += "auto selected_status() const -> std::TokenStatus {"
    source += "".join(f"if(status=={n}){{return std::TokenStatus::{name};}}" for n, name in enumerate(STATUSES))
    source += "return std::TokenStatus::invalid_window;}"
    source += "auto selected_kind() const -> std::TokenKind {"
    source += "".join(f"if(kind=={n}){{return std::TokenKind::{name};}}" for n, name in enumerate(KINDS))
    source += "return std::TokenKind::none;}"
    source += "auto entry(i64 field) const -> i64 {"
    source += "if(operation==0){" + LOAD + f"const {RESULT} original=scan(borrow_bytes(owner));"
    source += PRESERVED + observe() + "}"
    source += f"if(operation==1){{const {RESULT} original=expired();const {RESULT} report=original;" + observe() + "}"
    source += f"if(operation==2){{const {RESULT} original={RESULT}(selected_status(),selected_kind(),"
    source += f"offset,count,consumed,lf);const {RESULT} report=original;" + observe() + "}"
    # Repeated scanning: each call rescans from the start, checks the partition,
    # LF count and progress, and returns field `field` of the whole trace.
    source += LOAD + "i64 used=offset;i64 selected=field;i64 calls=0;bool stopped=false;"
    source += "while(!stopped){if(calls>length){return -781;}"
    source += f"const {RESULT} original=step(borrow_bytes(owner),used);"
    source += (
        "if(original.status()==std::TokenStatus::invalid_window){return -782;}"
        "if(original.consumed_bytes()<0){return -783;}"
        "if(original.consumed_bytes()>length-used){return -784;}"
        "if(original.byte_offset()<used){return -785;}"
        "if(original.byte_count()<0){return -786;}"
        "if(original.byte_offset()+original.byte_count()!=used+original.consumed_bytes()){return -787;}"
        "i64 lf_seen=0;i64 pos=used;while(pos<original.byte_offset()){"
        "if(owner[pos]==10u8){lf_seen=lf_seen+1;}pos=pos+1;}"
        "if(lf_seen!=original.skipped_lf()){return -788;}"
        "if(original.status()==std::TokenStatus::end_of_input){"
        "if(used+original.consumed_bytes()!=length){return -789;}stopped=true;"
        "}else{if(original.consumed_bytes()<=0){return -790;}}"
        "if(selected<6){" + PRESERVED + observe("selected") + "}"
        "used=used+original.consumed_bytes();selected=selected-6;calls=calls+1;}"
        "return -791;}};\n"
    )
    return source


def packet(program, row):
    data = records.decode_data(row.get("data", ""))
    values = dict(operation=OPERATIONS.index(row["op"]), length=len(data))
    for name in ("offset", "count", "status", "kind", "consumed", "lf"):
        if name in row:
            values[name] = row[name]
    windows = row.get("windows", [])
    if windows:
        records.require(len(windows) == 2, "two nested windows")
        (first_offset, first_count), (second_offset, second_count) = windows
        values.update(windows=2, first_offset=first_offset, first_count=first_count)
        values.update(second_offset=second_offset, second_count=second_count)
    return program.pack(data=data, **values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    args = parser.parse_args()
    with records.scratch("token-scan") as scratch:
        driver = records.Driver(args.compiler, scratch)
        program = driver.build(driver_source(), "TokenInput")
        cases = records.load_jsonl(GOLDEN / "token_scan.jsonl")
        count, observations = program.check(
            ((row["label"], packet(program, row), row["expected"]) for row in cases), scratch
        )
        rejections = driver.reject_all(GOLDEN / "token_scan_rejections.jsonl")
        example = (records.ROOT / "examples/token_scan.au").read_text()
        records.require(driver.run_main(example) == 42, "examples/token_scan.au returns 42")
    print(f"PASS token scan: {count} cases, {observations} i64 observations, {rejections} rejections, example")


if __name__ == "__main__":
    main()
