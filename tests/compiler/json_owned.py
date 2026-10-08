#!/usr/bin/env python3
"""Focused local JSON integration with accepted readonly owned-byte views.

Reuses the real hosted owner bridge; every report field is returned as full i64.
No fabricated span, target FFI addition, remote publication, or full qualification.
"""

from __future__ import annotations
import argparse
import hashlib
import json
import os
import resource
import signal
from pathlib import Path
import sys
import tempfile
import time

sys.dont_write_bytecode = True
import owned_bytes as host
import json_profile as oracle

require = oracle.require
ROOT = Path(__file__).resolve().parents[2]
SPAN = oracle.SPAN
OWNER = "builtin::OwnedBytes"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def program(body, helpers=""):
    return (
        "module json_owned;\nimport std.json;\nimport std.binary;\nimport std.byte_buffer;\n"
        + helpers
        + "auto entry(builtin::ByteRegion region,i64 n,i64 flag)->i64{"
        + body
        + "}"
    )


def observe():
    return (
        "if(flag<6){i64 field=flag;"
        + oracle.observe().replace("report.", "token.")
        + "}"
        + "i64 field=flag-6;"
        + oracle.observe(True).replace("report.", "document.")
    )


def reports(view, offset, count):
    return (
        f"const std::JsonTokenResult token=std::next_json_token({view},{offset},{count});"
        f"const std::JsonResult document=std::validate_json({view},{offset},{count});"
    )


def expected(raw, offset, count):
    return oracle.token_model(raw, offset, count) + oracle.document_model(raw, offset, count)


class Suite(host.Suite):
    def __init__(self, compiler, directory):
        super().__init__(compiler, directory, ROOT / "library", entry_name="entry")
        self.fields = []
        self.borrow_failures = 0

    def failed_borrow(self, executable):
        # The accepted hosted adapter traps failed-owner borrow in C++, before
        # any compiler-emitted span bounds check. Its contract is bounds+abort.
        result = host.command([executable, 0, 0, 0])
        require(
            result.returncode == -signal.SIGABRT
            and result.stdout == b""
            and result.stderr == b"aurora owned bytes: bounds\n",
            "failed borrow must be exact hosted bounds abort",
        )
        self.borrow_failures += 1

    def reject(self, name, source):
        before = len(host.command.results)
        super().reject(name, source)
        diagnostics = []
        for result in host.command.results[before:]:
            error = result.stderr.decode()
            require(
                "cannot mutate or move an owner while a readonly span is live" in error
                or "cannot move a borrowed owner" in error,
                "expected explicit live-borrow rejection: " + error,
            )
            diagnostics.append(error)
        require(len(diagnostics) == 2, "both fresh and preexisting output rejection diagnostics")
        (self.directory / ("reject-" + name) / "receipt.json").write_text(
            json.dumps(dict(status="passed", diagnostics=diagnostics, preserved_output=True), indent=2) + "\n"
        )

    def fields_run(self, executable, quota, length, wanted, allocations=1, peak=1):
        observed = []
        for field, value in enumerate(wanted):
            self.run(executable, quota, length, field, value, allocations, peak)
            row = [int(v) for v in self.last_observation.stdout.split()]
            signed = row[0] if row[0] < (1 << 63) else row[0] - (1 << 64)
            observed.append(signed)
        record = dict(
            program=executable.parent.name,
            quota=quota,
            length=length,
            expected=wanted,
            observed=observed,
            allocations=allocations,
            releases=allocations,
            peak=peak,
        )
        self.fields.append(record)
        (self.directory / "observations.json").write_text(json.dumps(self.fields, indent=2) + "\n")
        print(f"PASS owned JSON {executable.parent.name}: n={length}, {len(wanted)} complete i64 fields", flush=True)


def cases(suite):
    fill = (
        f"{OWNER} owner=region.try_allocate(n);if(!owner.ok()){{return -800;}}"
        "i64 i=0;while(i<n){owner.set(i,32u8);i=i+1;}if(n>0){owner.set(n-1,48u8);}"
    )
    exe = suite.compile(
        "owner-full-window",
        program(fill + f"const {SPAN} view=borrow_bytes(owner);" + reports("view", "0", "n") + observe()),
    )
    for n in (0, 1, 4095, 4096, 4097, 8193):
        raw = (b" " * (n - 1) + b"0") if n else b""
        suite.fields_run(exe, max(1, n), n, expected(raw, 0, n))

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
        ("signed-window-extreme", str(oracle.MAX), str(oracle.MAX), (0,)),
        ("valid-empty-endpoint", "8193", "0", (0,)),
    )
    raw = bytearray(8193)
    raw[0] = 255
    raw[4096] = 48
    for label, start, count, ns in specs:
        exe = suite.compile(
            label,
            program(fill_bad + f"const {SPAN} view=borrow_bytes(owner);" + reports("view", start, count) + observe()),
        )
        for n in ns:
            suite.fields_run(exe, 8193, n, expected(raw, int(start), n if count == "n" else int(count)))

    data = b'xx {"a":[true,null]} yy'
    setup = f"{OWNER} owner=region.try_allocate({len(data)});"
    setup += "".join(f"owner.set({i},{byte}u8);" for i, byte in enumerate(data))
    nested = (
        f"const {SPAN} whole=borrow_bytes(owner);const {SPAN} first=whole.subspan(2,{len(data) - 4});"
        f"const {SPAN} inner=first.subspan(1,{len(data) - 6});"
    )
    exe = suite.compile(
        "nested-subspan-relative", program(setup + nested + reports("inner", "0", str(len(data) - 6)) + observe())
    )
    sliced = data[3:-3]
    suite.fields_run(exe, len(data), 0, expected(sliced, 0, len(sliced)))

    for index, data in enumerate((b'xx {"a":[0,]} yy', b'xx {"a":["\xff"]} yy')):
        setup = f"{OWNER} owner=region.try_allocate({len(data)});"
        setup += "".join(f"owner.set({i},{byte}u8);" for i, byte in enumerate(data))
        nested = (
            f"const {SPAN} whole=borrow_bytes(owner);"
            f"const {SPAN} first=whole.subspan(2,{len(data) - 4});"
            f"const {SPAN} inner=first.subspan(1,{len(data) - 6});"
        )
        exe = suite.compile(
            f"nested-prefix-error-{index}",
            program(setup + nested + reports("inner", "0", str(len(data) - 6)) + observe()),
        )
        sliced = data[3:-3]
        wanted = expected(sliced, 0, len(sliced))
        require(
            wanted[6] != 0 and wanted[7] > 0 and wanted[8] > 0 and wanted[9] == 2,
            "nested failure fixture includes error, prefix tokens and admitted depth",
        )
        suite.fields_run(exe, len(data), 0, wanted)

    # Reports returned from helper calls retain no borrow; mutate, resize and move
    # the actual source before observing every copied result field.
    helpers = (
        f"auto token_copy({SPAN} bytes)->std::JsonTokenResult{{"
        "const std::JsonTokenResult r=std::next_json_token(bytes,0,bytes.size());return r;}"
        f"auto document_copy({SPAN} bytes)->std::JsonResult{{"
        "const std::JsonResult r=std::validate_json(bytes,0,bytes.size());return r;}"
    )
    data = b' [0,{"x":false}] '
    setup = f"{OWNER} owner=region.try_allocate({len(data)});"
    setup += "".join(f"owner.set({i},{byte}u8);" for i, byte in enumerate(data))
    copy = (
        "const std::JsonTokenResult original=token_copy(borrow_bytes(owner));"
        "const std::JsonResult original_document=document_copy(borrow_bytes(owner));"
        "const std::JsonTokenResult token=original;const std::JsonResult document=original_document;"
        "owner.set(0,255u8);if(!owner.try_resize(8193)){return -802;}"
        f"{OWNER} moved=move(owner);moved.set(1,255u8);"
    )
    exe = suite.compile("owner-report-survives-mutate-resize-move", program(setup + copy + observe(), helpers))
    suite.fields_run(exe, 8193, 0, expected(data, 0, len(data)), allocations=2)

    # Buffer has logical length zero despite nonzero dirty backing capacity.
    base = (
        f"{OWNER} owner=region.try_allocate(8193);owner.set(0,255u8);owner.set(8192,255u8);"
        "std::ByteBuffer buffer=std::ByteBuffer(region,move(owner));"
    )
    exe = suite.compile(
        "buffer-logical-not-capacity",
        program(base + f"const {SPAN} view=buffer.bytes();" + reports("view", "0", "view.size()") + observe()),
    )
    suite.fields_run(exe, 8193, 0, expected(b"", 0, 0))
    append = "i64 i=0;while(i<n){if(!buffer.try_append(32u8)){return -803;}i=i+1;}"
    append += "if(n>0){buffer.try_write_u8(n-1,48u8);}"
    exe = suite.compile(
        "buffer-logical-window-boundaries",
        program(base + append + f"const {SPAN} view=buffer.bytes();" + reports("view", "0", "view.size()") + observe()),
    )
    for n in (1, 4095, 4096, 4097):
        suite.fields_run(exe, 8193, n, expected(b" " * (n - 1) + b"0", 0, n))
    data = b'{"a":[]}'
    append = "".join(f"buffer.try_append({byte}u8);" for byte in data)
    copy = (
        "const std::JsonTokenResult original=token_copy(buffer.bytes());"
        "const std::JsonResult original_document=document_copy(buffer.bytes());"
        "const std::JsonTokenResult token=original;const std::JsonResult document=original_document;"
        "buffer.try_write_u8(0,255u8);buffer.clear();if(!buffer.try_reserve(8194)){return -804;}"
        "std::ByteBuffer moved=move(buffer);moved.try_append(255u8);"
    )
    exe = suite.compile("buffer-report-survives-clear-reserve-move", program(base + append + copy + observe(), helpers))
    suite.fields_run(exe, 8194, 0, expected(data, 0, len(data)), allocations=2)

    for buffer in (False, True):
        setup = f"{OWNER} owner=region.try_allocate(1);"
        if buffer:
            setup += "std::ByteBuffer buffer=std::ByteBuffer(region,move(owner));"
        view = "buffer.bytes()" if buffer else "borrow_bytes(owner)"
        exe = suite.compile(
            "failed-" + ("buffer" if buffer else "owner") + "-borrow-traps",
            program(setup + f"const {SPAN} view={view};" + reports("view", "0", "0") + observe()),
        )
        suite.failed_borrow(exe)


def rejections(suite):
    for buffer in (False, True):
        setup = f"{OWNER} owner=region.try_allocate(8);"
        if buffer:
            setup += "std::ByteBuffer buffer=std::ByteBuffer(region,move(owner));"
        view = "buffer.bytes()" if buffer else "borrow_bytes(owner)"
        setup += f"const {SPAN} view={view};" + reports("view", "0", "0")
        operations = (
            ("buffer.try_append(48u8);", "buffer.try_reserve(9);", "std::ByteBuffer moved=move(buffer);")
            if buffer
            else ("owner.set(0,48u8);", "owner.try_resize(9);", f"{OWNER} moved=move(owner);")
        )
        for name, operation in zip(("mutate", "resize", "move"), operations):
            suite.reject(
                ("buffer-" if buffer else "owner-") + name,
                program(setup + operation + "return document.token_count();"),
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--compiler-sha256")
    args = parser.parse_args()
    compiler = args.compiler.resolve(strict=True)
    pin = sha(compiler)
    if args.compiler_sha256:
        require(pin == args.compiler_sha256, "compiler pin mismatch")
    output = (
        args.artifacts.absolute() if args.artifacts else Path(tempfile.mkdtemp(prefix="aurora-json-owned-")) / "gate"
    )
    require(not output.exists(), "fresh artifacts required")
    output.mkdir(parents=True)
    inputs = {str(p.relative_to(ROOT)): sha(p) for p in (ROOT / "library").rglob("*.au")}
    for name in (
        "tests/compiler/json_owned.py",
        "tests/compiler/json_profile.py",
        "tests/compiler/owned_bytes.py",
        "runtime/hosted_bytes.cpp",
        "runtime/hosted_bytes.hpp",
    ):
        inputs[name] = sha(ROOT / name)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    original_command = host.command
    commands = []

    def recorded(command, timeout=30):
        index = len(commands)
        started = time.monotonic()
        result = original_command(command, timeout)
        recorded.results.append(result)
        stem = output / f"command-{index:04d}"
        stem.with_suffix(".stdout").write_bytes(result.stdout)
        stem.with_suffix(".stderr").write_bytes(result.stderr)
        row = dict(
            command=list(map(str, command)),
            timeout_seconds=timeout,
            returncode=result.returncode,
            elapsed_seconds=time.monotonic() - started,
        )
        commands.append(row)
        stem.with_suffix(".json").write_text(json.dumps(row, indent=2) + "\n")
        require(sum(p.stat().st_size for p in output.rglob("*") if p.is_file()) < 128 << 20, "128 MiB output cap")
        return result

    recorded.results = []
    host.command = recorded
    suite = Suite(compiler, output)
    manifest = dict(
        status="running",
        compiler_sha256=pin,
        external_expected_sha256=args.compiler_sha256,
        optimized=not __debug__,
        inputs=inputs,
        scope="local focused owned-input JSON integration",
    )
    try:
        rejections(suite)
        cases(suite)
        require(sha(compiler) == pin, "compiler changed")
        for name, digest in inputs.items():
            require(sha(ROOT / name) == digest, "input changed: " + name)
        manifest.update(
            status="passed",
            programs=suite.programs,
            native_i64_observations=suite.native,
            report_vectors=len(suite.fields),
            rejections=suite.rejections,
            exact_hosted_bounds_aborts=suite.borrow_failures,
        )
    except Exception as error:
        manifest.update(status="failed", error=str(error))
        raise
    finally:
        manifest.update(completed_native=suite.native, completed_programs=suite.programs, commands=len(commands))
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        host.command = original_command
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
