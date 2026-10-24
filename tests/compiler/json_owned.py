#!/usr/bin/env python3
"""Owned std.json: token, document and codec paths over real hosted owners.

One packed driver (hosted_records.py) holds every program; each observed report
field is a row. Token/document reports have no standard-library reference, so
their expectations are the reviewed golden file golden/json_owned.jsonl, frozen
from the earlier independent grammar model after it agreed with native results.
Codec expectations come from Python's json module. Failed-owner borrows must
end in the hosted adapter's bounds abort. Rejections are
golden/json_owned_rejections.jsonl, one compile each.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import hosted_records
import runtime_records as records

require = records.require
ROOT = records.ROOT
GOLDEN = Path(__file__).with_name("golden")
MAX = records.MAX
SPAN = "builtin::span<const u8>"
OWNER = "builtin::OwnedBytes"
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
TOKEN_FIELDS = ("byte_offset", "byte_count", "consumed_bytes", "error_offset")
DOCUMENT_FIELDS = ("error_offset", "token_count", "max_depth")


def program(body, helpers=""):
    return (
        "module json_owned;\nimport std.json;\nimport std.binary;\nimport std.byte_buffer;\n"
        + helpers
        + "auto entry(builtin::ByteRegion region,i64 n,i64 flag)->i64{"
        + body
        + "}"
    )


def observe_report(name, document):
    body = "if(field==0){"
    body += "".join(f"if({name}.status()==std::JsonStatus::{s}){{return {i};}}" for i, s in enumerate(STATUSES))
    body += "return -777;}"
    if not document:
        body += "if(field==1){"
        body += "".join(f"if({name}.kind()==std::JsonTokenKind::{k}){{return {i};}}" for i, k in enumerate(KINDS))
        body += "return -778;}"
    fields = DOCUMENT_FIELDS if document else TOKEN_FIELDS
    body += "".join(f"if(field=={i}){{return {name}.{f}();}}" for i, f in enumerate(fields, 1 if document else 2))
    return body + "return -779;"


def observe():
    """Flag 0..5 selects a token report field, 6..9 a document report field."""
    return (
        "if(flag<6){i64 field=flag;"
        + observe_report("token", False)
        + "}i64 field=flag-6;"
        + observe_report("document", True)
    )


def reports(view, offset, count):
    return (
        f"const std::JsonTokenResult token=std::next_json_token({view},{offset},{count});"
        f"const std::JsonResult document=std::validate_json({view},{offset},{count});"
    )


def owner_with(data):
    return f"{OWNER} owner=region.try_allocate({len(data)});" + "".join(
        f"owner.set({i},{byte}u8);" for i, byte in enumerate(data)
    )


def cases(pack, vectors):
    """Programs and report vectors: (program, quota, n, allocations); fields come from the golden file."""
    fill = (
        f"{OWNER} owner=region.try_allocate(n);if(!owner.ok()){{return -800;}}"
        "i64 i=0;while(i<n){owner.set(i,32u8);i=i+1;}if(n>0){owner.set(n-1,48u8);}"
    )
    exe = pack.program(
        "owner-full-window",
        program(fill + f"const {SPAN} view=borrow_bytes(owner);" + reports("view", "0", "n") + observe()),
    )
    for n in (0, 1, 4095, 4096, 4097, 8193):
        vectors.append((exe, max(1, n), n, 1))

    # Oversize must dominate malformed first byte; no zero-count read occurs.
    fill_bad = (
        f"{OWNER} owner=region.try_allocate(8193);if(!owner.ok()){{return -801;}}"
        "owner.set(0,255u8);owner.set(4096,48u8);"
    )
    specs = (
        ("oversize-invalid-prefix", "0", "n", (4097, 8193)),
        ("valid-small-inside-large", "4096", "1", (0,)),
        ("input-limit-nonzero-coordinate", "1", "4097", (0,)),
        ("invalid-window-precedence", "-1", "8194", (0,)),
        ("signed-window-extreme", str(MAX), str(MAX), (0,)),
        ("valid-empty-endpoint", "8193", "0", (0,)),
    )
    for label, start, count, ns in specs:
        exe = pack.program(
            label,
            program(fill_bad + f"const {SPAN} view=borrow_bytes(owner);" + reports("view", start, count) + observe()),
        )
        for n in ns:
            vectors.append((exe, 8193, n, 1))

    for name, data in (
        ("nested-subspan-relative", b'xx {"a":[true,null]} yy'),
        ("nested-prefix-error-0", b'xx {"a":[0,]} yy'),
        ("nested-prefix-error-1", b'xx {"a":["\xff"]} yy'),
    ):
        nested = (
            f"const {SPAN} whole=borrow_bytes(owner);const {SPAN} first=whole.subspan(2,{len(data) - 4});"
            f"const {SPAN} inner=first.subspan(1,{len(data) - 6});"
        )
        exe = pack.program(
            name, program(owner_with(data) + nested + reports("inner", "0", str(len(data) - 6)) + observe())
        )
        vectors.append((exe, len(data), 0, 1))

    # Reports returned from helper calls retain no borrow; mutate, resize and move
    # the actual source before observing every copied result field.
    helpers = (
        f"auto token_copy({SPAN} bytes)->std::JsonTokenResult{{"
        "const std::JsonTokenResult r=std::next_json_token(bytes,0,bytes.size());return r;}"
        f"auto document_copy({SPAN} bytes)->std::JsonResult{{"
        "const std::JsonResult r=std::validate_json(bytes,0,bytes.size());return r;}"
    )
    copy = (
        "const std::JsonTokenResult original=token_copy(borrow_bytes(owner));"
        "const std::JsonResult original_document=document_copy(borrow_bytes(owner));"
        "const std::JsonTokenResult token=original;const std::JsonResult document=original_document;"
        "owner.set(0,255u8);if(!owner.try_resize(8193)){return -802;}"
        f"{OWNER} moved=move(owner);moved.set(1,255u8);"
    )
    exe = pack.program(
        "owner-report-survives-mutate-resize-move",
        program(owner_with(b' [0,{"x":false}] ') + copy + observe(), helpers),
    )
    vectors.append((exe, 8193, 0, 2))

    # Buffer has logical length zero despite nonzero dirty backing capacity.
    base = (
        f"{OWNER} owner=region.try_allocate(8193);owner.set(0,255u8);owner.set(8192,255u8);"
        "std::ByteBuffer buffer=std::ByteBuffer(region,move(owner));"
    )
    exe = pack.program(
        "buffer-logical-not-capacity",
        program(base + f"const {SPAN} view=buffer.bytes();" + reports("view", "0", "view.size()") + observe()),
    )
    vectors.append((exe, 8193, 0, 1))
    append = "i64 i=0;while(i<n){if(!buffer.try_append(32u8)){return -803;}i=i+1;}"
    append += "if(n>0){buffer.try_write_u8(n-1,48u8);}"
    exe = pack.program(
        "buffer-logical-window-boundaries",
        program(base + append + f"const {SPAN} view=buffer.bytes();" + reports("view", "0", "view.size()") + observe()),
    )
    for n in (1, 4095, 4096, 4097):
        vectors.append((exe, 8193, n, 1))
    append = "".join(f"buffer.try_append({byte}u8);" for byte in b'{"a":[]}')
    copy = (
        "const std::JsonTokenResult original=token_copy(buffer.bytes());"
        "const std::JsonResult original_document=document_copy(buffer.bytes());"
        "const std::JsonTokenResult token=original;const std::JsonResult document=original_document;"
        "buffer.try_write_u8(0,255u8);buffer.clear();if(!buffer.try_reserve(8194)){return -804;}"
        "std::ByteBuffer moved=move(buffer);moved.try_append(255u8);"
    )
    exe = pack.program("buffer-report-survives-clear-reserve-move", program(base + append + copy + observe(), helpers))
    vectors.append((exe, 8194, 0, 2))

    for buffer in (False, True):
        setup = f"{OWNER} owner=region.try_allocate(1);"
        if buffer:
            setup += "std::ByteBuffer buffer=std::ByteBuffer(region,move(owner));"
        view = "buffer.bytes()" if buffer else "borrow_bytes(owner)"
        exe = pack.program(
            "failed-" + ("buffer" if buffer else "owner") + "-borrow-traps",
            program(setup + f"const {SPAN} view={view};" + reports("view", "0", "0") + observe()),
        )
        pack.abort(exe, 0, 0, 0, b"aurora owned bytes: bounds\n")


LARGE_WINDOW = """module large_json_scalar;
import std.json; import std.array;
auto entry(builtin::ByteRegion region,i64 n,i64 flag)->i64 {
    builtin::OwnedBytes input=region.try_allocate(n);
    if(!input.ok()){ return -1; }
    input.set(0,65u8);
    input.set(n-1,92u8);
    const builtin::span<const u8> all=borrow_bytes(input);
    const std::JsonScalarResult first=std::decode_json_string_scalar(all,0,n);
    if(first.status()!=std::JsonStatus::success || first.scalar_or(0u64)!=65u64 ||
       first.consumed_bytes()!=1){ return -2; }
    const std::JsonScalarResult cut=std::decode_json_string_scalar(all,n-1,1);
    if(cut.status()!=std::JsonStatus::truncated || cut.error_offset()!=n){ return -3; }
    const builtin::span<const u8> tail=all.subspan(n-1,1);
    const std::JsonScalarResult nested=std::decode_json_string_scalar(tail,0,1);
    if(nested.status()!=std::JsonStatus::truncated || nested.error_offset()!=1){ return -4; }
    return 42;
}"""


def codec_cases(hosted, pack):
    """Owner-backed codec windows beyond 4096 bytes and the shipped codec example."""
    exe = pack.program("large-owned-window", LARGE_WINDOW)
    for n in (4096, 4097, 5000, 8192):
        pack.run(exe, n, n, 0, 42, 1, 1)
    example = hosted.pack((ROOT / "library/examples/json_codecs.au").read_text(), entry="json_codecs_example")
    raw = b'"A\\u0000\\n\\/\\"\\\\\xc3\xa9\\uD83D\\uDE00"'
    decoded = json.loads(raw).encode()
    encoded = json.dumps(json.loads(raw), ensure_ascii=False, separators=(",", ":")).encode()
    for index, value in [(-1, len(decoded)), (-2, len(encoded)), (-(2**63), 256), *enumerate(decoded + encoded)]:
        example.run(0, 128, 64, index, value, 2, 2, release_order=[2, 1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    args = parser.parse_args()
    golden = records.load_jsonl(GOLDEN / "json_owned.jsonl")
    with records.scratch("json-owned") as scratch:
        hosted = hosted_records.Hosted(args.compiler, scratch)
        pack = hosted.pack()
        vectors = []
        cases(pack, vectors)
        require(len(vectors) == len(golden), "one golden report vector per owned JSON run")
        for (exe, quota, n, allocations), row in zip(vectors, golden):
            require((pack.names[exe], quota, n) == (row["program"], row["quota"], row["n"]), "golden vector order")
            for field, value in enumerate(row["expected"]):
                pack.run(exe, quota, n, field, value, allocations, 1)
        for row in golden:
            if row["program"].startswith("nested-prefix-error"):
                wanted = row["expected"]
                require(
                    wanted[6] != 0 and wanted[7] > 0 and wanted[8] > 0 and wanted[9] == 2,
                    "nested failure fixture includes error, prefix tokens and admitted depth",
                )
        codec_cases(hosted, pack)
        hosted.finish()
        rejections = records.load_jsonl(GOLDEN / "json_owned_rejections.jsonl")
        hosted_records.reject_all(args.compiler, scratch, rejections)
    print(
        f"PASS owned JSON: {len(pack.names)} programs and the codec example, {hosted.rows} runs, "
        f"{hosted.aborted} bounds aborts, {len(rejections)} rejections"
    )


if __name__ == "__main__":
    main()
