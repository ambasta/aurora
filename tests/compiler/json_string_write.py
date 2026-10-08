#!/usr/bin/env python3
"""Transactional whole-string JSON append on real hosted ByteBuffer owners.

Python's strict UTF-8 decoder and json.dumps are independent byte/status oracles.
The full profile exhausts all one-byte inputs, all controls and UTF-8 lead/second
boundary families; it is not an exhaustive Unicode or compiler proof. --smoke
selects three native programs and seven admission rejections. Every rejection
preserves absent/existing assembly, and all native cases check real allocation
identities, release counts and cleanup. Arithmetic-overflow paths require sizes
unrepresentable by practical valid owners and are explicitly not runtime-covered.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import shutil
import tempfile

import borrowed_objects
from borrowed_objects import BorrowSuite, PRESERVED
import byte_buffer
from byte_buffer import CREATE, ROOT, check_state
import owned_bytes
from unsigned_oracle import require

MAX_I64 = (1 << 63) - 1
MIN_I64 = -(1 << 63)
SPAN = "builtin::span<const u8>"
STATUS = "std::JsonStringAppendStatus"
RESULT = "std::JsonStringAppendResult"
SMOKE_PROGRAMS = ("canonical-windows", "allocation-transaction", "borrowed-result-lifetime")
SMOKE_REJECTIONS = (
    "direct-self-input",
    "named-empty-self-input",
    "disjoint-self-input",
    "later-output-size",
    "forwarded-self-input",
    "private-result-count",
    "const-output",
)


def program(body, helpers=""):
    return (
        "module json_string_write_test;\nimport std.json_write;\nimport std.byte_buffer;\nimport std.binary;\n"
        + helpers
        + "\nauto entry(builtin::ByteRegion region, i64 n, i64 flag) -> i64 {\n"
        + body
        + "\n}\n"
    )


def array(name, data):
    values = ", ".join(f"{b}u8" for b in data) or "0u8"
    return f"const builtin::array<u8, {max(1, len(data))}> {name} = {{{values}}};\n"


def oracle(data):
    return json.dumps(data.decode("utf-8", errors="strict"), ensure_ascii=False).encode("utf-8")


def status_oracle(data):
    try:
        data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        return "truncated" if error.reason == "unexpected end of data" else "invalid_utf8"
    return "success"


def report(status, count=0, name="result"):
    return f"if ({name}.status() != {STATUS}::{status} || {name}.appended_bytes() != {count}) {{ return 0; }}\n"


class StringSuite(BorrowSuite):
    def __init__(self, *args):
        super().__init__(*args)
        # Extend only this suite's trusted driver: once:N fails allocation N+1
        # exactly once, then allows a real retry. Plain N retains sticky faults.
        driver = self.driver.read_text()
        driver = driver.replace("std::int64_t remaining = -1;", "std::int64_t remaining = -1;\n    bool once = false;")
        driver = driver.replace(
            "if (trace.remaining == 0)\n        return nullptr;",
            (
                "if (trace.remaining == 0) {\n        if (trace.once) trace.remaining = -1;\n        "
                "return nullptr;\n    }"
            ),
        )
        marker = "trace.remaining = argc == 5 ? std::strtoll(argv[4], nullptr, 10) : -1;"
        driver = driver.replace(
            marker,
            marker + "\n    if (argc == 5 && argv[4][0] == 'o') {\n"
            "        trace.once = true; trace.remaining = std::strtoll(argv[4] + 5, nullptr, 10);\n    }",
        )
        require("bool once = false;" in driver and "if (trace.once)" in driver, "driver extension failed")
        self.driver.write_text(driver)

    def select_program(self, name):
        selected = self.profile == "full" or name in SMOKE_PROGRAMS
        names = self.selected_programs if selected else self.omitted_programs
        require(name not in names, f"duplicate program fixture: {name}")
        names.append(name)
        self.save_selection()
        return selected

    def reject(self, name, source, diagnostic=None):
        selected = self.profile == "full" or name in SMOKE_REJECTIONS
        names = self.selected_rejections if selected else self.omitted_rejections
        require(name not in names, f"duplicate rejection fixture: {name}")
        names.append(name)
        self.save_selection()
        if not selected:
            return
        folder = self.directory / ("reject-" + name)
        folder.mkdir()
        path, output = folder / "input.au", folder / "output.s"
        path.write_text(source)
        for attempt, prior in enumerate((None, PRESERVED)):
            if prior is not None:
                output.write_bytes(prior)
            result = owned_bytes.command([self.compiler, *self.module_args, path, "-o", output])
            (folder / f"stderr-{attempt}.txt").write_bytes(result.stderr)
            (folder / f"stdout-{attempt}.bin").write_bytes(result.stdout)
            require(
                result.returncode == 1 and bool(result.stderr), f"{name}: expected clean rejection: {result.stderr!r}"
            )
            if diagnostic is not None:
                require(diagnostic in result.stderr.decode(), f"{name}: wrong diagnostic: {result.stderr!r}")
            require(not output.exists() if prior is None else output.read_bytes() == prior, f"{name}: changed output")
            require(path.read_text() == source, f"{name}: modified source")
        self.rejections += 1

    def check_selection(self):
        require(self.programs == len(self.selected_programs), "selected program did not compile")
        require(self.rejections == len(self.selected_rejections), "selected rejection did not complete")
        require(len(self.cases) == self.native + self.skipped_native, "runtime accounting mismatch")
        require({case["program"] for case in self.cases} == set(self.selected_programs), "program has no runtime case")
        if self.profile == "smoke":
            require(set(self.selected_programs) == set(SMOKE_PROGRAMS), "smoke program selection changed")
            require(set(self.selected_rejections) == set(SMOKE_REJECTIONS), "smoke rejection selection changed")
        else:
            require(not self.omitted_programs and not self.omitted_rejections, "full profile omitted fixtures")


def canonical_cases(suite):
    fixtures = [
        (b"", 0, 0),
        (b"abc", 3, 0),
        (b"abc", 1, 0),
        (b"\xff\xe2\x82\xac\xf0\x80", 2, 0),
        (b"\xff\xe2\x82\xac\xf0\x80", 4, 0),
        (b"ordinary ASCII / stays raw", 0, len(b"ordinary ASCII / stays raw")),
        (b'\x00\b\t\n\f\r"\\/', 0, 9),
        (bytes(range(32)), 0, 32),
        (bytes(range(32, 128)), 0, 96),
        (b"\xff\x80" + "A\u00a2\u20ac\U0001f642".encode() + b"\xc0", 2, 10),
        ("\u007f\u0080\u07ff\u0800\ud7ff\ue000\uffff\U00010000\U0010ffff".encode(), 0, 26),
        ("\ufeff\ufffd\u2028\u2029\ufdd0\U0001fffe\U0010fffe".encode(), 0, 23),
    ]
    # Derive lengths rather than hand-maintain Unicode fixture widths.
    fixtures[-2] = (fixtures[-2][0], 0, len(fixtures[-2][0]))
    fixtures[-1] = (fixtures[-1][0], 0, len(fixtures[-1][0]))
    prefix = b"p\x00\xff"
    body = CREATE
    required = []
    for raw, offset, count in fixtures:
        escaped = oracle(raw[offset : offset + count])
        required.append(len(prefix) + len(escaped))
        body += "{\nif (!buffer.clear()) { return 0; }\n"
        body += "".join(f"if (!buffer.try_append({b}u8)) {{ return 0; }}\n" for b in prefix)
        body += array("input", raw)
        body += f"const {SPAN} all = borrow_bytes(input); const {SPAN} view = all.subspan(0, {len(raw)});\n"
        body += f"const {RESULT} result = std::append_json_string(buffer, view, {offset}, {count});\n"
        body += report("success", len(escaped)) + check_state(prefix + escaped, "n") + "}\n"
    exe = suite.compile("canonical-windows", program(body + "return 42;"))
    capacity = max(required)
    for extra in (0, 11):
        suite.run(exe, capacity + extra, capacity + extra, 0, 42, 1, 1, fail_after=1)

    randomizer = random.Random(0x4A534F4E)
    scalars = [0, 34, 92, 127, 128, 2047, 2048, 55295, 57344, 65535, 65536, 1114111]
    while len(scalars) < 192:
        scalar = randomizer.randrange(0x110000)
        if not 0xD800 <= scalar <= 0xDFFF:
            scalars.append(scalar)
    raw = "".join(map(chr, scalars)).encode()
    escaped = oracle(raw)
    body = CREATE + array("input", raw)
    body += f"const {RESULT} result = std::append_json_string(buffer, borrow_bytes(input), 0, {len(raw)});\n"
    body += report("success", len(escaped)) + check_state(escaped, len(escaped)) + "return 42;"
    exe = suite.compile("seeded-unicode-byte-oracle", program(body))
    suite.run(exe, len(escaped), len(escaped), 0, 42, 1, 1, fail_after=1)


def byte_and_boundary_cases(suite):
    expected = [oracle(bytes([value])) for value in range(128)]
    offsets, widths, combined = [], [], b""
    for value in expected:
        offsets.append(len(combined))
        widths.append(len(value))
        combined += value
    body = CREATE + "const builtin::array<u8, 1> input = {u8(n)};\n"
    body += f"const {RESULT} result = std::append_json_string(buffer, borrow_bytes(input), 0, 1);\n"
    body += "if (n < 128) {\n" + array("expected", combined)
    body += "const builtin::array<i64, 128> offsets = {" + ", ".join(map(str, offsets)) + "};\n"
    body += "const builtin::array<i64, 128> widths = {" + ", ".join(map(str, widths)) + "};\n"
    body += (
        f"if (result.status() != {STATUS}::success || result.appended_bytes() != widths[n] || "
        f"buffer.size() != widths[n]) {{ return 0; }}\n"
    )
    body += (
        "i64 index = 0; while (index < widths[n]) { const std::ByteReadResult byte = "
        "buffer.read_u8(index); if (byte.value_or(256u64) != u64(expected[offsets[n] + index]))"
        " { return 0; } index = index + 1; }\n"
    )
    body += (
        f"}} else {{ if (result.status() != {STATUS}::invalid_utf8 && flag == 0) {{ return 0; "
        f"}} if (result.status() != {STATUS}::truncated && flag == 1) {{ return 0; }} if "
        f"(result.appended_bytes() != 0 || buffer.size() != 0) {{ return 0; }} }}\n"
    )
    body += "if (buffer.capacity() != 8) { return 0; } return 42;"
    # n is the input byte, so allocate a fixed owner rather than CREATE's n.
    body = body.replace("region.try_allocate(n)", "region.try_allocate(8)")
    exe = suite.compile("all-single-byte-inputs", program(body))
    for value in range(256):
        status = status_oracle(bytes([value]))
        suite.run(exe, 8, value, int(status == "truncated"), 42, 1, 1, fail_after=1)

    families = set()
    for lead in range(0xC0, 0x100):
        for second in (0, 0x7F, 0x80, 0x8F, 0x90, 0x9F, 0xA0, 0xBF, 0xC0, 0xFF):
            families.add(bytes([lead, second]))
            families.add(bytes([lead, second, 0x80]))
            families.add(bytes([lead, second, 0x80, 0x80]))
    # Python emits a compact status table for independently generated real inputs.
    cases = sorted(families)
    statuses = [{"success": 0, "invalid_utf8": 1, "truncated": 2}[status_oracle(value)] for value in cases]
    # Fixed arrays are capped at 4096. Split corpus without reducing coverage.
    for batch, start in enumerate(range(0, len(cases), 256)):
        values = cases[start : start + 256]
        corpus = b"".join(value.ljust(4, b"\x00") for value in values)
        local_statuses = statuses[start : start + 256]
        body = CREATE.replace("try_allocate(n)", "try_allocate(8)") + array("corpus", corpus)
        body += array("lengths", [len(value) for value in values]) + array("statuses", local_statuses)
        body += "i64 sample = 0; while (sample < " + str(len(values)) + ") {\nif (!buffer.clear()) { return 0; }\n"
        body += (
            f"const {RESULT} result = std::append_json_string(buffer, borrow_bytes(corpus), sample"
            f" * 4, i64(lengths[sample]));\n"
        )
        body += (
            f"if (statuses[sample] == 0u8) {{ if (result.status() != {STATUS}::success || "
            f"result.appended_bytes() != i64(lengths[sample]) + 2 || buffer.size() != "
            f"i64(lengths[sample]) + 2) {{ return 0; }}\n"
        )
        body += (
            "const std::ByteReadResult first = buffer.read_u8(0); const std::ByteReadResult last = "
            "buffer.read_u8(buffer.size() - 1); if (first.value_or(256u64) != 34u64 || "
            "last.value_or(256u64) != 34u64) { return 0; }\n"
        )
        body += (
            "i64 index = 0; while (index < i64(lengths[sample])) { const std::ByteReadResult byte ="
            " buffer.read_u8(index + 1); if (byte.value_or(256u64) != u64(corpus[sample * 4 + "
            "index])) { return 0; } index = index + 1; }\n"
        )
        body += (
            f"}} else {{ if (result.appended_bytes() != 0 || buffer.size() != 0) {{ return 0; }} "
            f"if (statuses[sample] == 1u8 && result.status() != {STATUS}::invalid_utf8) {{ return "
            f"0; }} if (statuses[sample] == 2u8 && result.status() != {STATUS}::truncated) {{ "
            f"return 0; }} }}\n"
        )
        body += "if (buffer.capacity() != 8) { return 0; } sample = sample + 1; } return 42;"
        exe = suite.compile(f"utf8-boundary-family-{batch}", program(body))
        suite.run(exe, 8, 0, 0, 42, 1, 1, fail_after=1)


def invalid_and_window_cases(suite):
    cases = [
        b"\xc0\x80",
        b"\xc1\xbf",
        b"\xe0\x9f\xbf",
        b"\xed\xa0\x80",
        b"\xed\xbf\xbf",
        b"\xf0\x8f\xbf\xbf",
        b"\xf4\x90\x80\x80",
        b"\xf5\x80\x80\x80",
        b"\xff",
        b"\xc2",
        b"\xe0",
        b"\xe0\xa0",
        b"\xf0",
        b"\xf0\x90",
        b"\xf0\x90\x80",
        b"\xe0\x80",
        b"\xf0\x80",
        b"\xe2A",
        b"\xf0\x90A",
        b"\xf0\x90\x80A",
        b"\xff\xc2",
        b"\xc2\xe2",
        b"\xe2\x82\xff",
        b"\xe2\x82\xac\xc2",
        b"\xe2\x82\xac\xff\xf0",
    ]
    body = CREATE + "if (!buffer.try_append(17u8) || !buffer.try_append(255u8)) { return 0; }\n"
    for value in cases:
        for prefix in (b"", b"ok\x00\n" + "\u20ac".encode()):
            raw = prefix + value
            body += "{\n" + array("input", raw)
            body += f"const {RESULT} result = std::append_json_string(buffer, borrow_bytes(input), 0, {len(raw)});\n"
            body += report(status_oracle(raw)) + check_state([17, 255], "n") + "}\n"
    # Invalid input plus invalid windows establishes window-before-decoding precedence.
    for offset, count in (
        (MIN_I64, 0),
        (-1, 1),
        (0, -1),
        (0, MIN_I64),
        (2, 0),
        (1, 1),
        (0, 2),
        (MAX_I64, 0),
        (0, MAX_I64),
        (MAX_I64, MAX_I64),
    ):
        body += "{\n" + array("input", b"\xff")
        body += f"const {RESULT} result = std::append_json_string(buffer, borrow_bytes(input), {offset}, {count});\n"
        body += report("out_of_range") + check_state([17, 255], "n") + "}\n"
    body += "return 42;"
    exe = suite.compile("invalid-truncated-late-and-window", program(body))
    for capacity in (2, 32):
        suite.run(exe, capacity, capacity, 0, 42, 1, 1, fail_after=1)


def allocation_cases(suite):
    raw = b'A\x00"\\\n' + "\u20ac".encode()
    escaped = oracle(raw)
    prefix = b"p\xff"
    required = len(prefix) + len(escaped)
    body = CREATE + "if (!buffer.try_append(112u8) || !buffer.try_append(255u8)) { return 0; }\n" + array("input", raw)
    body += f"const {RESULT} result = std::append_json_string(buffer, borrow_bytes(input), 0, {len(raw)});\n"
    body += "if (flag == 0) {\n" + report("success", len(escaped))
    body += check_state(prefix + escaped, f"{required}") + "} else {\n" + report("append_failed")
    body += check_state(prefix, "n")
    body += "if (flag == 2) {\n"
    body += f"const {RESULT} retried = std::append_json_string(buffer, borrow_bytes(input), 0, {len(raw)});\n"
    body += report("success", len(escaped), "retried") + check_state(prefix + escaped, required)
    body += report("append_failed") + "}\n} return 42;"
    exe = suite.compile("allocation-transaction", program(body))
    # Exact capacity under a disabled allocator; growth must be exactly required,
    # not ByteBuffer's doubling policy, and make exactly one replacement allocation.
    suite.run(exe, required, required, 0, 42, 1, 1, fail_after=1, release_order=[1])
    for initial in (2, required - 1):
        suite.run(exe, required, initial, 0, 42, 2, 1, release_order=[1, 2])
        suite.run(exe, required - 1, initial, 1, 42, 1, 1, release_order=[1])
        suite.run(exe, required, initial, 1, 42, 1, 1, fail_after=1, release_order=[1])
        suite.run(exe, required, initial, 2, 42, 2, 1, fail_after="once:1", release_order=[1, 2])

    body = CREATE + array("valid", b"a") + array("invalid", b"\xff") + array("truncated", b"\xf0\x90\x80")
    for name, view, offset, count, expected in (
        ("window", "invalid", -1, 1, "out_of_range"),
        ("invalid", "invalid", 0, 1, "invalid_utf8"),
        ("truncated", "truncated", 0, 3, "truncated"),
        ("valid", "valid", 0, 1, "append_failed"),
        ("empty", "valid", 0, 0, "append_failed"),
    ):
        body += (
            f"{{ const {RESULT} result = std::append_json_string(buffer, borrow_bytes({view}), {offset}, {count});\n"
        )
        body += report(expected) + "if (buffer.ok() || buffer.size() != 0 || buffer.capacity() != 0) { return 0; } }\n"
    exe = suite.compile("failed-owner-validation-precedence", program(body + "return 42;"))
    suite.run(exe, 0, 1, 0, 42, 0, 0)
    suite.run(exe, 8, 8, 0, 42, 0, 0, fail_after=0)

    # A scoped quota blocker is released between failure and retry. The retry can
    # succeed only if the failed reserve retained the old owner/accounting.
    body = CREATE.replace("try_allocate(n)", "try_allocate(2)")
    body += "if (!buffer.try_append(112u8) || !buffer.try_append(255u8)) { return 0; }\n" + array("input", raw)
    body += "{ builtin::OwnedBytes blocker = region.try_allocate(1); if (!blocker.ok()) { return 0; }\n"
    body += f"const {RESULT} failed = std::append_json_string(buffer, borrow_bytes(input), 0, {len(raw)});\n"
    body += report("append_failed", name="failed") + check_state(prefix, 2) + "}\n"
    body += f"const {RESULT} result = std::append_json_string(buffer, borrow_bytes(input), 0, {len(raw)});\n"
    body += report("success", len(escaped)) + check_state(prefix + escaped, required) + "return 42;"
    exe = suite.compile("quota-release-and-retry", program(body))
    suite.run(exe, required, 0, 0, 42, 3, 2, release_order=[2, 1, 3])

    body = CREATE + array("input", b"x")
    body += f"const {RESULT} result = std::append_json_string(buffer, borrow_bytes(input), 1, 0);\n"
    body += "if (flag >= 0) {\n" + report("success", 2) + check_state(b'""', "flag")
    body += "} else {\n" + report("append_failed") + check_state([], "n") + "} return 42;"
    exe = suite.compile("empty-zero-capacity-and-spare", program(body))
    suite.run(exe, 2, 0, 2, 42, 2, 1, release_order=[1, 2])
    for capacity in (2, 17):
        suite.run(exe, capacity, capacity, capacity, 42, 1, 1, fail_after=1)
    suite.run(exe, 1, 0, -1, 42, 1, 1)
    suite.run(exe, 8, 0, -1, 42, 1, 1, fail_after=1)


def ownership_cases(suite):
    helper = f"""
    auto forward(std::ByteBuffer& output, {SPAN} input, i64 offset, i64 count) -> {RESULT} {{
        const {RESULT} result = std::append_json_string(output, input, offset, count);
        return result;
    }}
    auto twice(std::ByteBuffer& output, {SPAN} input) -> {RESULT} {{
        const {RESULT} result = forward(output, input, 0, input.size());
        return result;
    }}
    """
    body = CREATE + array("input", b"\x00A")
    body += f"const {RESULT} original = twice(buffer, borrow_bytes(input));\nconst {RESULT} copied = original;\n"
    body += report("success", 9, "original") + report("success", 9, "copied")
    body += check_state(oracle(b"\x00A"), 12)
    body += (
        "if (!buffer.clear()) { return 0; } std::ByteBuffer moved = move(buffer); if "
        "(!moved.try_append(77u8)) { return 0; }\n"
    )
    body += report("success", 9, "original") + report("success", 9, "copied") + check_state([77], 12, "moved")
    for status in ("success", "out_of_range", "invalid_utf8", "truncated", "overflow", "append_failed"):
        for value in (MIN_I64, -1, 0, 1, 2, 9, MAX_I64):
            effective = "append_failed" if status == "success" and value < 2 else status
            count = value if effective == "success" else 0
            body += (
                f"{{ const {RESULT} result = {RESULT}({STATUS}::{status}, {value});\n"
                + report(effective, count)
                + "}\n"
            )
    exe = suite.compile("borrowed-result-lifetime", program(body + "return 42;", helper))
    suite.run(exe, 12, 12, 0, 42, 1, 1, fail_after=1)

    body = CREATE.replace("try_allocate(n)", "try_allocate(1)")
    body += "if (!buffer.try_append(80u8)) { return 0; } builtin::OwnedBytes input_owner = region.try_allocate(n);\n"
    body += (
        "if (!input_owner.ok()) { return 0; } i64 index = 0; while (index < n) { if "
        "(!input_owner.set(index, 65u8)) { return 0; } index = index + 1; }\n"
    )
    body += f"{{ const {SPAN} view = borrow_bytes(input_owner); const {RESULT} result = forward(buffer, view, 0, n);\n"
    body += (
        f"if (result.status() != {STATUS}::success || result.appended_bytes() != n + 2 || "
        f"buffer.size() != n + 3 || buffer.capacity() != n + 3) {{ return 0; }} }}\n"
    )
    body += (
        "if (!input_owner.set(0, 90u8)) { return 0; } index = 0; while (index < buffer.size()) "
        "{ const std::ByteReadResult byte = buffer.read_u8(index); u64 expected = 65u64; if "
        "(index == 0) { expected = 80u64; } if (index == 1 || index == n + 2) { expected = "
        "34u64; } if (byte.value_or(256u64) != expected) { return 0; } index = index + 1; } "
        "return 42;"
    )
    exe = suite.compile("large-distinct-real-owner", program(body, helper))
    for size in (4097, 16385):
        suite.run(exe, 2 * size + 3, size, 0, 42, 3, 2, release_order=[1, 2, 3])

    body = CREATE.replace("try_allocate(n)", "try_allocate(8)")
    body += (
        "builtin::OwnedBytes other_allocation = region.try_allocate(3); std::ByteBuffer other ="
        " std::ByteBuffer(region, move(other_allocation));\n"
    )
    body += "if (!other.try_append(34u8) || !other.try_append(0u8) || !other.try_append(65u8)) { return 0; }\n"
    body += f"const {RESULT} result = forward(buffer, other.bytes(), 0, 3);\n" + report("success", 11)
    body += check_state(oracle(b'"\x00A'), 11) + check_state([34, 0, 65], 3, "other")
    body += "if (!other.clear() || !other.try_append(90u8)) { return 0; }\n" + report("success", 11) + "return 42;"
    exe = suite.compile("distinct-buffers-same-region", program(body, helper))
    suite.run(exe, 14, 0, 0, 42, 3, 2, release_order=[1, 2, 3])

    pattern = oracle(b"\x00")[1:-1]
    body = CREATE.replace("try_allocate(n)", "try_allocate(1)") + array("pattern", pattern)
    body += "if (!buffer.try_append(80u8)) { return 0; } builtin::OwnedBytes input_owner = region.try_allocate(n);\n"
    body += (
        "if (!input_owner.ok()) { return 0; } i64 index = 0; while (index < n) { if "
        "(!input_owner.set(index, 0u8)) { return 0; } index = index + 1; }\n"
    )
    body += f"const {RESULT} result = std::append_json_string(buffer, borrow_bytes(input_owner), 0, n);\n"
    body += (
        f"if (result.status() != {STATUS}::success || result.appended_bytes() != n * "
        f"{len(pattern)} + 2 || buffer.size() != n * {len(pattern)} + 3 || buffer.capacity() "
        f"!= buffer.size()) {{ return 0; }}\n"
    )
    body += (
        f"index = 0; while (index < buffer.size()) {{ const std::ByteReadResult byte = "
        f"buffer.read_u8(index); u64 expected = 34u64; if (index == 0) {{ expected = 80u64; }}"
        f" if (index >= 2 && index < buffer.size() - 1) {{ expected = u64(pattern[(index - 2) "
        f"% {len(pattern)}]); }} if (byte.value_or(256u64) != expected) {{ return 0; }} index "
        f"= index + 1; }} return 42;"
    )
    exe = suite.compile("large-owner-control-expansion", program(body))
    suite.run(exe, 4097 * 7 + 3, 4097, 0, 42, 3, 2, release_order=[1, 2, 3])


def example_case(suite):
    source = ROOT / "library/examples/json_string_write.au"
    expected = b"[" + oracle(b'A\x00\n"\\' + "\U0001f600".encode()) + b"]"
    exe = suite.compile("library-example", source.read_text(), entry_name="json_string_write_example")
    for observation, wanted in [
        (-1, len(expected) - 2),
        (-2, len(expected)),
        *enumerate(expected),
        (len(expected), 256),
        (MAX_I64, 256),
    ]:
        suite.run(exe, 73, 64, observation, wanted, 2, 2, fail_after=2, release_order=[2, 1])


def rejection_cases(suite):
    setup = CREATE + array("input", b"A") + f"const {SPAN} view = borrow_bytes(input);\n"
    setup += "buffer.try_append(65u8); buffer.try_append(66u8);\n"
    exclusive = "owning object is exclusively borrowed for a call"
    live = "cannot mutate or move an owner while a readonly span is live"
    fixtures = {
        "direct-self-input": ("std::append_json_string(buffer, buffer.bytes(), 0, 2)", exclusive),
        "direct-empty-self-input": ("std::append_json_string(buffer, buffer.bytes().subspan(0, 0), 0, 0)", exclusive),
        "named-self-input": (
            f"const {SPAN} self = buffer.bytes();",
            "std::append_json_string(buffer, self, 0, 2)",
            live,
        ),
        "named-empty-self-input": (
            f"const {SPAN} self = buffer.bytes().subspan(0, 0);",
            "std::append_json_string(buffer, self, 0, 0)",
            live,
        ),
        "disjoint-self-input": (
            f"const {SPAN} self = buffer.bytes().subspan(0, 1);",
            "std::append_json_string(buffer, buffer.bytes().subspan(1, 1), 0, 1)",
            live,
        ),
        "later-output-size": ("std::append_json_string(buffer, view, 0, buffer.size())", exclusive),
        "later-output-read": ("std::append_json_string(buffer, view, i64(buffer.ok()), 1)", exclusive),
        "later-output-mutation": ("std::append_json_string(buffer, view, i64(buffer.clear()), 1)", exclusive),
        "const-output": (
            "const std::ByteBuffer frozen = move(buffer);",
            "std::append_json_string(frozen, view, 0, 1)",
            "mutable borrowed parameter requires a mutable owning object",
        ),
    }
    for name, fixture in fixtures.items():
        before, call, diagnostic = ("", *fixture) if len(fixture) == 2 else fixture
        suite.reject(name, program(setup + before + f"const {RESULT} result = {call}; return 0;"), diagnostic)
    helper = (
        f"auto bad(std::ByteBuffer& output) -> {RESULT} {{ const {RESULT} result = "
        f"std::append_json_string(output, output.bytes(), 0, 0); return result; }}"
    )
    suite.reject("forwarded-self-input", program("return 0;", helper), exclusive)
    for field in ("count", "outcome"):
        source = program(f"const {RESULT} result = {RESULT}({STATUS}::success, 2); return i64(result.{field});")
        suite.reject("private-result-" + field, source, "private")
    for field, value in (("count", "7"), ("outcome", STATUS + "::success")):
        source = program(f"{RESULT} result = {RESULT}({STATUS}::success, 2); result.{field} = {value}; return 0;")
        suite.reject("private-result-write-" + field, source, "private")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    parser.add_argument("--compile-only", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="partial: three native programs, seven rejections")
    parser.add_argument("--artifacts", type=Path, help="retain receipts in a new directory")
    args = parser.parse_args()
    compiler = args.compiler.resolve(strict=True)
    before = hashlib.sha256(compiler.read_bytes()).hexdigest()
    directory = args.artifacts or Path(tempfile.mkdtemp(prefix="aurora-json-string-write-"))
    if args.artifacts:
        directory.mkdir(parents=True, exist_ok=False)
    paths = [
        Path(__file__).resolve(),
        *(ROOT / "library").rglob("*.au"),
        *(
            ROOT / "tests/compiler" / name
            for name in ("borrowed_objects.py", "byte_buffer.py", "owned_bytes.py", "unsigned_oracle.py")
        ),
        ROOT / "runtime/hosted_bytes.cpp",
        ROOT / "runtime/hosted_bytes.hpp",
    ]
    inputs = {path: path.read_bytes() for path in paths}
    commands = []
    original_command = owned_bytes.command

    def recorded_command(argv, **kwargs):
        record = {"argv": [str(value) for value in argv], "kwargs": kwargs}
        commands.append(record)
        (directory / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        result = original_command(argv, **kwargs)
        record.update(returncode=result.returncode, stdout_hex=result.stdout.hex(), stderr_hex=result.stderr.hex())
        (directory / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        if result.returncode == 0:
            if str(argv[0]) == str(compiler) or "-std=c++23" in argv:
                require(
                    not result.stdout and not result.stderr,
                    f"unexpected positive compiler/link diagnostic: {result.stdout!r} {result.stderr!r}",
                )
            else:
                require(not result.stderr, f"unexpected native stderr: {result.stderr!r}")
        return result

    owned_bytes.command = byte_buffer.command = recorded_command
    passed = False
    try:
        suite = StringSuite(compiler, directory, args.compile_only, args.smoke)
        (directory / "inputs.json").write_text(
            json.dumps(
                {
                    "compiler_sha256": before,
                    "profile": suite.profile,
                    "compile_only": args.compile_only,
                    "partial_coverage": args.smoke,
                    "inputs": {str(path): hashlib.sha256(data).hexdigest() for path, data in inputs.items()},
                    "oracle": "Python strict UTF-8 decoding and json.dumps(ensure_ascii=False)",
                    "runtime_uncovered": ["i64 escaped-size overflow", "i64 output-size overflow"],
                },
                indent=2,
            )
            + "\n"
        )
        canonical_cases(suite)
        byte_and_boundary_cases(suite)
        invalid_and_window_cases(suite)
        allocation_cases(suite)
        ownership_cases(suite)
        example_case(suite)
        rejection_cases(suite)
        suite.check_selection()
        require(hashlib.sha256(compiler.read_bytes()).hexdigest() == before, "compiler changed during gate")
        for path, data in inputs.items():
            require(path.read_bytes() == data, f"bound input changed: {path}")
        summary = {
            "compiler_sha256": before,
            "profile": suite.profile,
            "partial_coverage": args.smoke,
            "full_json_string_write_gate": not args.smoke and not args.compile_only,
            "programs": suite.programs,
            "native_cases": suite.native,
            "rejection_fixtures": suite.rejections,
            "rejection_executions": 2 * suite.rejections,
            "skipped_native_cases": suite.skipped_native,
            "compile_only": args.compile_only,
            "selected_programs": suite.selected_programs,
            "selected_rejections": suite.selected_rejections,
            "omitted_programs": suite.omitted_programs,
            "omitted_rejections": suite.omitted_rejections,
            "passed": True,
        }
        (directory / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(
            f"PASS JSON string append [profile={suite.profile}, compile_only={args.compile_only}]: "
            f"{suite.programs} programs, {suite.native} native cases, {suite.rejections} rejections"
        )
        print(f"compiler_sha256={before}")
        passed = True
    finally:
        owned_bytes.command = byte_buffer.command = original_command
        if passed and args.artifacts is None:
            shutil.rmtree(directory)
        else:
            print(f"artifacts={directory}")


if __name__ == "__main__":
    main()
