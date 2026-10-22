#!/usr/bin/env python3
"""Bounded ordinary native checks for the owned std.utf8 encoding contract.

Format reference: Unicode 17.0.0 section 3.9, D92 and Tables 3-6/3-7:
https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-3/
Full covers transition boundaries plus 1,024 fixed-seed scalar samples.
--profile exhaustive restores all 1,112,064 scalar values. Seventeen bounded
native plane loops compare every byte, width and zero tail with arithmetic, and
compare ordered fingerprints with Python's strict encoded bytes. Decoder
roundtrips are additional evidence, never the sole encoding oracle. All 2,048
surrogates are rejected; above-maximum u64 values have bounded explicit checks.

Public reports are ordinary forgeable data. Only success plus width 1..4 is
normalized success; this does not certify that manually supplied bytes encode
Unicode. Accessors mask failed reports and unused tails and return owned copies.

The process runner is shared with utf8.py. Each compiler has a 512 MiB address
limit; native executables/tools 128 MiB; every child CPU soft/hard 10/11 seconds,
regular files 8 MiB, core dumps zero. Compiler/tools wall limit is 30 seconds,
native wall limit 15. --sanitized-compiler omits only compiler address limits.
Sources have at most 12 checks and 64 KiB; all failure artifacts are retained.
This is finite Linux/x86-64 functional evidence, not a safety/performance proof.

Run: python3 tests/compiler/utf8_encoding.py /path/to/aurorac
Harness control: python3 -O tests/compiler/utf8_encoding.py --self-test-only
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import itertools
import json
from pathlib import Path
import signal
import sys
import tempfile
import time

from unsigned_oracle import Case, Observation, require, validate_values
from utf8 import Suite as ProcessSuite, sampled_scalars, SAMPLE_SEED

ROOT = Path(__file__).resolve().parents[2]
MAX_U64 = (1 << 64) - 1
MIN_I64 = -(1 << 63)
MAX_I64 = (1 << 63) - 1
PASS = 0xA55A1234FFFF00AA
SCALARS = 0x110000 - 0x800
MAX_SOURCE_BYTES = 65536
MAX_BATCH = 12
STATUS = "std::Utf8EncodeStatus::"
MODULUS = 1000000007
WIDTH_COUNTS = (128, 1920, 61440, 1048576)


def is_scalar(value):
    return 0 <= value < 0x110000 and not 0xD800 <= value <= 0xDFFF


def encode_reference(value):
    require(is_scalar(value), "encoding reference requires a Unicode scalar")
    return chr(value).encode("utf-8", "strict")


def report_model(status, data, width):
    require(status in ("success", "invalid_scalar"), "unknown report status")
    require(len(data) == 4, "report model requires four stored bytes")
    if status != "success" or not 1 <= width <= 4:
        return "invalid_scalar", 0, bytes(4)
    return "success", width, bytes(data[:width]) + bytes(4 - width)


def fingerprint_step(value, data):
    value = (value * 257 + len(data)) % MODULUS
    for byte in data:
        value = (value * 257 + byte) % MODULUS
    return value


def must_fail(action, label):
    try:
        action()
    except AssertionError:
        return
    raise AssertionError("harness accepted " + label)


def self_tests():
    for value, expected in (
        (0, b"\0"),
        (127, b"\x7f"),
        (128, b"\xc2\x80"),
        (2047, b"\xdf\xbf"),
        (2048, b"\xe0\xa0\x80"),
        (0xD7FF, b"\xed\x9f\xbf"),
        (0xE000, b"\xee\x80\x80"),
        (0xFFFF, b"\xef\xbf\xbf"),
        (0x10000, b"\xf0\x90\x80\x80"),
        (0x10FFFF, b"\xf4\x8f\xbf\xbf"),
    ):
        require(encode_reference(value) == expected, "strict encoder anchor")
    for value in (-1, 0xD800, 0xDFFF, 0x110000, MAX_U64):
        must_fail(lambda value=value: encode_reference(value), "invalid scalar in model")
    require(
        report_model("success", b"ABCD", 1) == ("success", 1, b"A\0\0\0"), "success report masks unused stored bytes"
    )
    require(
        report_model("success", b"\xff" * 4, 4) == ("success", 4, b"\xff" * 4),
        "report is ordinary bytes, not Unicode authority",
    )
    for width in (MIN_I64, -1, 0, 5, MAX_I64):
        require(
            report_model("success", b"ABCD", width) == ("invalid_scalar", 0, bytes(4)),
            "malformed successful width is normalized",
        )
    for width in (MIN_I64, 0, 1, 4, MAX_I64):
        require(
            report_model("invalid_scalar", b"ABCD", width) == ("invalid_scalar", 0, bytes(4)),
            "failure masks width and stored bytes",
        )
    must_fail(lambda: report_model("unknown", bytes(4), 1), "unknown modeled status")
    good = Observation(PASS.to_bytes(8, "little"), exit_code=0)
    case = Case("all result bits", "", PASS)
    validate_values(good, [case])
    for bad in (
        replace(good, output=good.output[:1]),
        replace(good, output=good.output + b"x"),
        replace(good, exit_code=1),
        replace(good, terminal_signal=signal.SIGILL),
        replace(good, output=(PASS ^ (1 << 40)).to_bytes(8, "little")),
    ):
        must_fail(lambda bad=bad: validate_values(bad, [case]), "bad native observation")
    must_fail(lambda: require(False, "deliberate assertion"), "disabled require")
    print("PASS UTF-8 encoding harness controls (active under Python -O)", flush=True)


def python_crosscheck(values=None):
    fingerprints = [0] * 17
    counts = [0] * 4
    count = 0
    for value in range(0x110000) if values is None else (*values, *range(0xD800, 0xE000)):
        if is_scalar(value):
            expected = chr(value).encode("utf-8", "strict")
            counts[len(expected) - 1] += 1
            plane = value // 65536
            fingerprints[plane] = fingerprint_step(fingerprints[plane], expected)
            count += 1
        else:
            try:
                chr(value).encode("utf-8", "strict")
            except UnicodeEncodeError:
                continue
            raise AssertionError(f"Python strict accepted surrogate U+{value:04X}")
    require(count == (SCALARS if values is None else len(values)), "wrong scalar enumeration count")
    if values is None:
        require(tuple(counts) == WIDTH_COUNTS, "wrong shortest-width population")
    print(f"PASS Python strict encoding: {count} scalars, 2048 rejected surrogates", flush=True)
    return fingerprints, counts


def scalar_loop(plane, fingerprint, values=None):
    start, end = plane * 65536, (plane + 1) * 65536
    count = 65536 - (2048 if plane == 0 else 0)
    case = Case(
        f"all scalar encodings in plane {plane}: {count} values, byte model and strict fingerprint",
        f"""
        u64 value={start}u64;u64 visited=0u64;u64 fingerprint=0u64;
        while(value<{end}u64){{
            if(either(value<55296u64,value>57343u64)){{
                i64 width=1;
                if(value>=128u64){{width=2;}}if(value>=2048u64){{width=3;}}if(value>=65536u64){{width=4;}}
                builtin::array<u8,4> expected={{0u8,0u8,0u8,0u8}};
                u64 remaining=value;i64 position=width-1;
                while(position>0){{expected[position]=u8(128u64+remaining%64u64);remaining=remaining/64u64;position=position-1;}}
                u64 prefix=0u64;
                if(width==2){{prefix=192u64;}}if(width==3){{prefix=224u64;}}if(width==4){{prefix=240u64;}}
                expected[0]=u8(prefix+remaining);
                const std::Utf8EncodeResult actual=std::encode_utf8(value);
                if(actual.status()!=std::Utf8EncodeStatus::success){{return value*64u64+1u64;}}
                if(actual.size()!=width){{return value*64u64+2u64;}}
                const std::array<u8,4> bytes=actual.bytes_or_zero();
                builtin::array<u8,4> roundtrip={{0u8,0u8,0u8,0u8}};i64 index=0;
                fingerprint=(fingerprint*257u64+u64(width))%{MODULUS}u64;
                while(index<4){{
                    if(bytes.at(index)!=expected[index]){{return value*64u64+3u64;}}
                    roundtrip[index]=bytes.at(index);
                    if(index<width){{
                        if(actual.byte_or(index,255u8)!=expected[index]){{return value*64u64+4u64;}}
                        fingerprint=(fingerprint*257u64+u64(bytes.at(index)))%{MODULUS}u64;
                    }}else{{if(actual.byte_or(index,255u8)!=255u8){{return value*64u64+5u64;}}}}
                    index=index+1;
                }}
                {{const builtin::span<const u8> view=borrow_bytes(roundtrip);
                    const std::Utf8DecodeResult decoded=std::decode_utf8(view,0,width,true);
                    if(decoded.status()!=std::Utf8Status::success){{return value*64u64+6u64;}}
                    if(decoded.width()!=width){{return value*64u64+7u64;}}
                    if(decoded.scalar_or({MAX_U64}u64)!=value){{return value*64u64+8u64;}}
                    const std::Utf8DecodeResult chunk=std::decode_utf8(view,0,width,false);
                    if(chunk.status()!=std::Utf8Status::success){{return value*64u64+9u64;}}
                    if(chunk.width()!=width){{return value*64u64+10u64;}}
                    if(chunk.scalar_or({MAX_U64}u64)!=value){{return value*64u64+11u64;}}
                }}
                visited=visited+1u64;
            }}
            value=value+1u64;
        }}
        if(visited!={count}u64){{return 12u64;}}
        return {PASS}u64+fingerprint;
    """,
        PASS + fingerprint,
    )

    if values is None:
        return case
    selected = tuple(value for value in values if start <= value < end)
    body = case.body.replace(
        f"u64 value={start}u64;u64 visited=0u64;",
        "const builtin::array<u64,"
        + str(len(selected))
        + "> selected={"
        + ",".join(f"{value}u64" for value in selected)
        + "};i64 sample=0;u64 visited=0u64;",
    )
    body = body.replace(f"while(value<{end}u64){{", f"while(sample<{len(selected)}){{const u64 value=selected[sample];")
    body = body.replace("value=value+1u64;", "sample=sample+1;")
    body = body.replace(f"if(visited!={count}u64)", f"if(visited!={len(selected)}u64)")
    return replace(case, name=f"plane {plane} boundary/seed{SAMPLE_SEED}: {len(selected)} scalars", body=body)


def surrogate_loop():
    return Case(
        "all 2048 surrogate code points reject with zero output",
        f"""
        u64 value=55296u64;u64 visited=0u64;
        while(value<=57343u64){{
            const std::Utf8EncodeResult result=std::encode_utf8(value);
            if(result.status()!=std::Utf8EncodeStatus::invalid_scalar){{return value*16u64+1u64;}}
            if(result.size()!=0){{return value*16u64+2u64;}}
            const std::array<u8,4> bytes=result.bytes_or_zero();i64 index=0;
            while(index<4){{
                if(bytes.at(index)!=0u8){{return value*16u64+3u64;}}
                if(result.byte_or(index,165u8)!=165u8){{return value*16u64+4u64;}}
                index=index+1;
            }}
            if(result.byte_or({MIN_I64},165u8)!=165u8){{return value*16u64+5u64;}}
            if(result.byte_or({MAX_I64},165u8)!=165u8){{return value*16u64+6u64;}}
            visited=visited+1u64;value=value+1u64;
        }}
        return {PASS}u64+visited;
    """,
        PASS + 2048,
    )


def access_checks(report, status, data, width):
    expected_status, size, expected_bytes = report_model(status, data, width)
    body = f"if({report}.status()!={STATUS}{expected_status}){{return 1u64;}}"
    body += f"if({report}.size()!={size}){{return 2u64;}}"
    body += f"const std::array<u8,4> output={report}.bytes_or_zero();"
    for index, byte in enumerate(expected_bytes):
        body += f"if(output.at({index})!={byte}u8){{return 3u64;}}"
    for index, fallback in itertools.product((MIN_I64, -1, 0, 1, 2, 3, 4, 5, MAX_I64), (0, 165, 255)):
        expected = expected_bytes[index] if 0 <= index < size else fallback
        body += f"if({report}.byte_or({index},{fallback}u8)!={expected}u8){{return 4u64;}}"
    return body


def scalar_cases():
    # Surrogate neighbors, every width edge, BOM, NUL, noncharacters, unassigned.
    values = (
        0,
        1,
        0x7E,
        0x7F,
        0x80,
        0x81,
        0x7FE,
        0x7FF,
        0x800,
        0x801,
        0xD7FF,
        0xE000,
        0xFFFE,
        0xFFFF,
        0x10000,
        0x10001,
        0x10FFFE,
        0x10FFFF,
        0xFEFF,
        0xFFFD,
        0xFDD0,
        0xFDEF,
        0x1FFFE,
        0x1FFFF,
        0x0378,
    )
    for value in values:
        data = encode_reference(value)
        body = f"const std::Utf8EncodeResult report=std::encode_utf8({value}u64);"
        body += access_checks("report", "success", data + bytes(4 - len(data)), len(data))
        body += f"return {PASS}u64;"
        yield Case(f"scalar U+{value:04X}: exact encoding, padding and extreme access", body, PASS)
    for value in (
        0xD800,
        0xD801,
        0xDBFF,
        0xDC00,
        0xDFFE,
        0xDFFF,
        0x110000,
        0x110001,
        0x1FFFFF,
        0xFFFFFFFF,
        1 << 32,
        1 << 63,
        MAX_U64 - 1,
        MAX_U64,
    ):
        body = f"const std::Utf8EncodeResult report=std::encode_utf8({value}u64);"
        body += access_checks("report", "invalid_scalar", bytes(4), 0)
        body += f"return {PASS}u64;"
        yield Case(f"invalid scalar {value}: normalized failure and extreme access", body, PASS)


def stored_array(data):
    return "std::array<u8,4> stored=std::array<u8,4>();" + "".join(
        f"stored.set({index},{byte}u8);" for index, byte in enumerate(data)
    )


def layout_cases():
    yield Case(
        "owned array/report static and runtime size/visibility facts",
        f"""
        static_assert(size_of(builtin::array<u8,4>)==4);
        static_assert(size_of(std::array<u8,4>)==4);
        static_assert(size_of(std::Utf8EncodeStatus)==8);
        static_assert(size_of(std::Utf8EncodeResult)==24);
        static_assert(field_count(std::array<u8,4>)==0);
        static_assert(field_count(std::Utf8EncodeResult)==0);
        if(reflect_size(type_id(std::array<u8,4>))!=4){{return 1u64;}}
        if(reflect_size(type_id(std::Utf8EncodeResult))!=24){{return 2u64;}}
        return {PASS}u64;
    """,
        PASS,
    )
    # No align_of or raw object-byte API is claimed. U8-surrounded owners give
    # alignment-sensitive size observations under the existing layout rules.
    yield Case(
        "u8-surrounded owned array has six-byte layout",
        f"""
        static_assert(size_of(ArrayLayoutProbe)==6);
        if(reflect_size(type_id(ArrayLayoutProbe))!=6){{return 1u64;}}
        return {PASS}u64;
    """,
        PASS,
        prelude="class ArrayLayoutProbe{u8 head;std::array<u8,4> owned;u8 tail;public:"
        "ArrayLayoutProbe(u8 a,std::array<u8,4> b,u8 c):head(a),owned(b),tail(c){} };",
    )
    yield Case(
        "u8-surrounded encoding report has forty-byte layout",
        f"""
        static_assert(size_of(ReportLayoutProbe)==40);
        if(reflect_size(type_id(ReportLayoutProbe))!=40){{return 1u64;}}
        return {PASS}u64;
    """,
        PASS,
        prelude="class ReportLayoutProbe{u8 head;std::Utf8EncodeResult owned;u8 tail;public:"
        "ReportLayoutProbe(u8 a,std::Utf8EncodeResult b,u8 c):head(a),owned(b),tail(c){} };",
    )


def forged_cases():
    patterns = (bytes(4), b"ABCD", b"\xff" * 4, b"\xc0\x80\xab\xcd", b"\xed\xa0\x80\x7f", b"\xf4\x90\x80\x80")
    widths = (MIN_I64, -1, 0, 1, 2, 3, 4, 5, MAX_I64)
    for status, width, data in itertools.product(("success", "invalid_scalar"), widths, patterns):
        body = stored_array(data)
        body += f"const std::Utf8EncodeResult report=std::Utf8EncodeResult({STATUS}{status},stored,{width});"
        body += access_checks("report", status, data, width)
        body += f"return {PASS}u64;"
        yield Case(f"forged {status}, width {width}, bytes {data.hex()}: normalized access", body, PASS)


def copy_cases():
    for value in (0, 0x7F, 0x80, 0x800, 0x10000, 0x10FFFF):
        expected = encode_reference(value) + bytes(4 - len(encode_reference(value)))
        body = f"const std::Utf8EncodeResult original=std::encode_utf8({value}u64);"
        body += "const std::Utf8EncodeResult saved=original;"
        body += "std::array<u8,4> first=original.bytes_or_zero();"
        body += "std::array<u8,4> second=saved.bytes_or_zero();"
        body += "first.set(0,255u8);first.set(1,254u8);first.set(2,253u8);first.set(3,252u8);"
        for index, byte in enumerate(expected):
            body += f"if(second.at({index})!={byte}u8){{return 1u64;}}"
        body += "second.set(0,251u8);second.set(1,250u8);second.set(2,249u8);second.set(3,248u8);"
        body += "const std::array<u8,4> third=original.bytes_or_zero();"
        body += "const std::array<u8,4> fourth=saved.bytes_or_zero();"
        for index, byte in enumerate(expected):
            body += f"if(third.at({index})!={byte}u8){{return 2u64;}}"
            body += f"if(fourth.at({index})!={byte}u8){{return 3u64;}}"
        body += f"return {PASS}u64;"
        yield Case(f"factory U+{value:04X}: result and returned arrays are independent copies", body, PASS)
    for status, width in itertools.product(("success", "invalid_scalar"), (0, 1, 2, 3, 4, 5)):
        data = b"ABCD"
        _, _, expected = report_model(status, data, width)
        body = stored_array(data)
        body += f"const std::Utf8EncodeResult original=std::Utf8EncodeResult({STATUS}{status},stored,{width});"
        body += "const std::Utf8EncodeResult saved=original;"
        body += "stored.set(0,255u8);stored.set(1,254u8);stored.set(2,253u8);stored.set(3,252u8);"
        body += "std::array<u8,4> first=original.bytes_or_zero();"
        body += "std::array<u8,4> second=saved.bytes_or_zero();"
        for index, byte in enumerate(expected):
            body += f"if(first.at({index})!={byte}u8){{return 1u64;}}"
        body += "first.set(0,251u8);first.set(1,250u8);first.set(2,249u8);first.set(3,248u8);"
        for index, byte in enumerate(expected):
            body += f"if(second.at({index})!={byte}u8){{return 2u64;}}"
        body += access_checks("saved", status, data, width)
        body += f"return {PASS}u64;"
        yield Case(f"constructor {status}, width {width}: input, report and output copies are independent", body, PASS)


def rejection_cases():
    for value, kind in (("65", "i64"), ("true", "bool"), ("65u8", "u8")):
        yield (
            f"encode_utf8 rejects implicit {kind} argument",
            f"const std::Utf8EncodeResult r=std::encode_utf8({value});return 0u64;",
            (f"expected u64, got {kind}",),
        )
    report = "const std::Utf8EncodeResult r=std::encode_utf8(65u64);"
    for index, kind in (("0u64", "u64"), ("0u8", "u8"), ("false", "bool")):
        yield (
            f"byte_or rejects {kind} index",
            report + f"return u64(r.byte_or({index},0u8));",
            (f"expected i64, got {kind}",),
        )
    for fallback, kind in (("0", "i64"), ("0u64", "u64"), ("false", "bool")):
        yield (
            f"byte_or rejects {kind} fallback",
            report + f"return u64(r.byte_or(0,{fallback}));",
            (f"expected u8, got {kind}",),
        )
    yield (
        "report payload remains private",
        report + "const std::array<u8,4> copy=r.payload;return 0u64;",
        ("private class field is inaccessible",),
    )
    for scalar, capacity in (("u8", 3), ("u64", 4)):
        wrong = f"std::array<{scalar},{capacity}>"
        yield (
            f"constructor rejects wrong nominal {wrong}",
            f"const {wrong} bytes={wrong}();const std::Utf8EncodeResult r="
            "std::Utf8EncodeResult(std::Utf8EncodeStatus::success,bytes,1);return 0u64;",
            ("expected std::array<u8,4>", "got " + wrong),
        )


class Suite(ProcessSuite):
    def __init__(self, compiler, directory, timeout, sanitized_compiler):
        super().__init__(compiler, directory, timeout, sanitized_compiler)
        self.rejections = 0

    # Override only source rendering/receipts. Execution and hard limits remain
    # the established runner; direct imports prevent accidental reexport reliance.
    def check(self, cases):
        require(1 <= len(cases) <= MAX_BATCH, "native batch size limit")
        require(len(cases) == 1 or all(not item.prelude for item in cases), "prelude isolation")
        functions = [f"utf8_encoding_case_{index}" for index in range(len(cases))]
        source = (
            "module utf8_encoding_test;import std.utf8;import std.array;\n"
            "auto both(bool a,bool b)->bool{if(a){return b;}return false;}\n"
            "auto either(bool a,bool b)->bool{if(a){return true;}return b;}\n"
        )
        for function, case in zip(functions, cases):
            source += case.prelude + f"\nauto {function}()->{case.result_type}{{{case.body}}}\n"
        require(len(source.encode()) <= MAX_SOURCE_BYTES, "generated source byte limit")
        directory = self.directory / f"batch-{self.batches:04d}"
        directory.mkdir()
        self.batches += 1
        path, output = directory / "input.au", directory / "compiled.s"
        path.write_text(source)
        receipt = {
            "cases": [case.name for case in cases],
            "source_bytes": len(source.encode()),
            "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "status": "running",
        }
        started = time.monotonic()
        try:
            self.command(
                [self.compiler, "--module-root", ROOT / "library", path, "-o", output],
                directory,
                "compiler",
                compiler=True,
            )
            require(output.is_file(), "successful compiler did not create assembly")
            require(path.read_text() == source, "compiler modified its source")
            observed = self.execute(directory, functions)
            receipt["observation"] = {key: value for key, value in asdict(observed).items() if key != "output"}
            validate_values(observed, cases)
            receipt["status"] = "passed"
            self.count += len(cases)
            print(f"PASS native UTF-8 encoding batch {self.batches}: {len(cases)} checks; {cases[0].name}", flush=True)
        except Exception as error:
            receipt.update(status="failed", error=str(error))
            raise AssertionError(f"UTF-8 encoding failure; retained artifacts: {directory}\n{error}") from error
        finally:
            receipt["seconds"] = round(time.monotonic() - started, 6)
            (directory / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
            self.receipts.append(receipt)

    def reject(self, name, body, diagnostics):
        source = f"module utf8_encoding_rejection;import std.utf8;import std.array;\nauto rejected()->u64{{{body}}}\n"
        require(len(source.encode()) <= MAX_SOURCE_BYTES, "rejection source byte limit")
        for existing in (False, True):
            directory = self.directory / f"rejection-{self.rejections:04d}"
            directory.mkdir()
            path, output = directory / "input.au", directory / "compiled.s"
            path.write_text(source)
            sentinel = b"existing assembly must survive rejected source\n"
            if existing:
                output.write_bytes(sentinel)
            receipt = {
                "case": name,
                "existing_output": existing,
                "status": "running",
                "source_bytes": len(source.encode()),
                "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            }
            try:
                try:
                    self.command(
                        [self.compiler, "--module-root", ROOT / "library", path, "-o", output],
                        directory,
                        "compiler",
                        compiler=True,
                    )
                except AssertionError:
                    # The shared runner expects success. Its immutable command
                    # receipt must instead establish this exact ordinary exit.
                    pass
                command = json.loads((directory / "compiler.command.json").read_text())
                require(command.get("returncode") == 1, "rejection requires exact compiler exit 1")
                require(not command.get("timeout"), "timeout is not a rejection")
                require((directory / "compiler.stdout").read_bytes() == b"", "rejection wrote unexpected stdout")
                stderr = (directory / "compiler.stderr").read_text()
                for expected in diagnostics:
                    require(expected in stderr, f"rejection diagnostic missing {expected!r}: {stderr}")
                require(path.read_text() == source, "rejected source was modified")
                if existing:
                    require(output.read_bytes() == sentinel, "rejection modified existing output")
                else:
                    require(not output.exists(), "rejection published an output")
                receipt.update(status="passed", diagnostics=list(diagnostics))
                self.rejections += 1
            except Exception as error:
                receipt.update(status="failed", error=str(error))
                raise AssertionError(
                    f"UTF-8 encoding rejection failure; retained artifacts: {directory}\n{error}"
                ) from error
            finally:
                (directory / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(f"PASS UTF-8 encoding rejection: {name}; absent/existing output preserved", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", nargs="?", type=Path)
    parser.add_argument("--self-test-only", action="store_true")
    parser.add_argument("--profile", choices=("full", "exhaustive"), default="full")
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument(
        "--sanitized-compiler", action="store_true", help="omit only compiler RLIMIT_AS for sanitizer shadow memory"
    )
    args = parser.parse_args()
    self_tests()
    if args.self_test_only:
        return
    require(args.compiler is not None, "compiler argument required for native execution")
    compiler = args.compiler.resolve()
    paths = {
        "compiler": compiler,
        "utf8": ROOT / "library/std/utf8.au",
        "array": ROOT / "library/std/array.au",
        "test": Path(__file__),
        "runner": Path(__file__).with_name("utf8.py"),
        "observation": Path(__file__).with_name("unsigned_oracle.py"),
    }
    identities = {name + "_sha256": hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    if args.artifacts:
        directory = args.artifacts.resolve()
        directory.mkdir(parents=True, exist_ok=False)
    else:
        (ROOT / "build").mkdir(exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix="utf8-encoding-native-", dir=ROOT / "build"))
    manifest = {
        **identities,
        "python": sys.version,
        "optimized_python": not __debug__,
        "native_wall_seconds": 15,
        "tool_wall_seconds": 30,
        "cpu_soft_hard_seconds": [10, 11],
        "core_bytes": 0,
        "compiler_address_space_bytes": None if args.sanitized_compiler else 512 << 20,
        "other_address_space_bytes": 128 << 20,
        "regular_file_bytes": 8 << 20,
        "max_source_bytes": MAX_SOURCE_BYTES,
        "max_cases_per_batch": MAX_BATCH,
        "unicode_format": "17.0.0 section 3.9 D92 Tables 3-6/3-7",
        "oracle_comparisons": [
            "Every native scalar byte/width/tail compared with independent arithmetic model",
            "Arithmetic model compared byte-for-byte with Python strict encoder for every scalar",
            "Ordered native/Python per-plane fingerprints compared; not a direct native/Python byte comparison",
            "Both Aurora decoder modes roundtrip every scalar as additional evidence",
        ],
        "layout_scope": "static/runtime sizes and alignment-sensitive wrapper sizes; no raw object padding observation",
        "scope": "ordinary functional Linux/x86-64 execution; no safety/performance proof",
        "status": "running",
    }
    print(json.dumps({**identities, "artifacts": str(directory)}), flush=True)
    suite = None
    try:
        values = None if args.profile == "exhaustive" else sampled_scalars()
        fingerprints, widths = python_crosscheck(values)
        manifest["python_strict_plane_fingerprints"] = fingerprints
        suite = Suite(compiler, directory, 15, args.sanitized_compiler)
        for case in layout_cases():
            suite.check([case])
        for plane, fingerprint in enumerate(fingerprints):
            suite.check([scalar_loop(plane, fingerprint, values)])
        suite.check([surrogate_loop()])
        batch = []
        for case in itertools.chain(scalar_cases(), forged_cases(), copy_cases()):
            batch.append(case)
            if len(batch) == MAX_BATCH:
                suite.check(batch)
                batch = []
        if batch:
            suite.check(batch)
        for name, body, diagnostics in rejection_cases():
            suite.reject(name, body, diagnostics)
        for name, path in paths.items():
            require(
                hashlib.sha256(path.read_bytes()).hexdigest() == identities[name + "_sha256"],
                f"{name} identity changed during test",
            )
        manifest.update(
            status="passed",
            native_checks=suite.count,
            native_batches=suite.batches,
            rejection_compilations=suite.rejections,
            profile=args.profile,
            sample_seed=SAMPLE_SEED,
            scalar_values=SCALARS if values is None else len(values),
            surrogate_values=2048,
            shortest_width_counts=widths,
            decoder_modes_per_scalar=2,
        )
        print(
            f"PASS UTF-8 encoding: {suite.count} native checks in {suite.batches} bounded fixtures; "
            f"{suite.rejections} rejection compilations; {manifest['scalar_values']} scalars and 2048 surrogates "
            f"({args.profile}); "
            f"artifacts={directory}",
            flush=True,
        )
    except Exception as error:
        manifest.update(status="failed", error=str(error))
        raise
    finally:
        if suite is not None:
            manifest["completed_native_checks"] = suite.count
            manifest["native_batches_attempted"] = suite.batches
            manifest["completed_rejection_compilations"] = suite.rejections
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
