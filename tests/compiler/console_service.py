#!/usr/bin/env python3
"""Complete bounded service source/editor/canonical-report gate. No guest claim."""

import argparse
import json
import os
import shlex
from pathlib import Path
import subprocess
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from meson_aurora_assembly import compose_object_bridge, render_bridge


def service_bridge(facts):
    return render_bridge((ROOT / "kernel/uefi/console-service-entry.S").read_text(), json.loads(facts.read_text()))


def require(value, message):
    if not value:
        raise RuntimeError(message)


def run(command, **kwargs):
    return subprocess.run(list(map(str, command)), cwd=ROOT, capture_output=True, timeout=120, **kwargs)


MIXED_SOURCE = r"""
module kernel_console_service;
import std.utf8_text;
import console.io;
auto region_check(builtin::ByteRegion region) -> bool {
    builtin::OwnedBytes scratch = region.try_allocate(1);
    return scratch.ok();
}
auto emit_text(builtin::ConsoleSession& session, builtin::ByteRegion region,
    builtin::span<const u8> value) -> bool {
    if (!region_check(region)) {
        return false;
    }
    const console::WriteResult result = console::write_bytes(session, value);
    return result.complete();
}
auto console_service(builtin::ConsoleSession& session, builtin::ByteRegion region) -> u64 {
    builtin::OwnedBytes storage = region.try_allocate(8);
    std::Utf8Text text = std::Utf8Text(region, move(storage));
    if (!text.ok()) {
        return 1u64;
    }
    if (text.try_append_scalar(79u64) != std::Utf8TextStatus::success
        || text.try_append_scalar(75u64) != std::Utf8TextStatus::success) {
        return 1u64;
    }
    const builtin::span<const u8> output = text.bytes();
    if (!emit_text(session, region, output)) {
        return 1u64;
    }
    if (text.size() != 2) {
        return 1u64;
    }
    return 0u64;
}
auto aurora_kernel_value() -> i64 { return 0; }
"""


def mixed_region(compiler, work):
    source = work / "mixed.au"
    source.write_text(MIXED_SOURCE)
    assembly = work / "mixed.s"
    facts = work / "mixed.abi.json"
    result = run([compiler, "--module-root", ROOT / "library", source, "-o", assembly, "--abi-facts", facts])
    require(result.returncode == 0, result.stderr.decode())
    functions = json.loads(facts.read_text())["functions"]
    mixed = [
        row for row in functions.values() if len(row["parameters"]) >= 2 and row["parameters"][1]["kind"] == "region"
    ]
    require(len(mixed) == 2, "missing mixed entry/helper facts")
    for row in mixed:
        require(
            row["parameters"][:2]
            == [
                {"offset": 0, "bytes": 16, "kind": "service", "type_name": "builtin::ConsoleSession"},
                {"offset": 16, "bytes": 8, "kind": "region", "type_name": "builtin::ByteRegion"},
            ],
            "mixed capability nominal kind/layout changed",
        )
    bridge = work / "mixed-bridge.s"
    bridge.write_text(assembly.read_text() + service_bridge(facts))
    binary = work / "mixed"
    result = link(bridge, HOSTS["region"], binary)
    require(result.returncode == 0, result.stderr.decode())
    for quota, limit, status, output, allocations, peak in [
        (16, 100, 0, b"OK", 2, 9),
        (9, 100, 0, b"OK", 2, 9),
        (8, 100, 1, b"", 1, 8),
        (7, 100, 1, b"", 0, 0),
        (16, 0, 1, b"", 2, 9),
        (16, 1, 1, b"O", 2, 9),
    ]:
        result = run([binary, limit, 0, 1, quota])
        require(
            result.returncode == status and result.stdout == output, f"mixed output/quota failure: {result.stderr!r}"
        )
        require(
            f"allocations={allocations} releases={allocations} peak={peak}".encode() in result.stderr,
            "mixed owner lifetime/quota mismatch",
        )

    invalid = [
        "auto f(builtin::DisplaySession& s, builtin::ByteRegion r) -> i64 { return 0; }",
        "auto f(builtin::CallSession& s, builtin::ByteRegion r) -> i64 { return 0; }",
        "auto f(builtin::ConsoleSession& s, builtin::ByteRegion r, builtin::ByteRegion q) -> i64 { return 0; }",
        "auto f(builtin::ConsoleSession& s, builtin::ByteRegion r, builtin::OwnedBytes b) -> i64 { return 0; }",
        "auto f(builtin::ConsoleSession& s, builtin::ByteRegion r) -> builtin::OwnedBytes "
        "{ return r.try_allocate(1); }",
        "auto f(builtin::ByteRegion r, builtin::ConsoleSession& s) -> i64 { return 0; }",
        "auto g(builtin::ConsoleSession& s, builtin::ByteRegion r, builtin::ConsolePutResult v) -> i64 { return 0; } "
        "auto f(builtin::ConsoleSession& s, builtin::ByteRegion r) -> i64 { return g(s, r, s.put(65u8)); }",
    ]
    for index, body in enumerate(invalid):
        path = work / f"mixed-reject-{index}.au"
        path.write_text("module mixed_reject; " + body)
        result = run([compiler, "--check", path])
        require(result.returncode != 0 and b"error AU" in result.stderr, f"mixed capability rejection {index}")


HOSTS = {}


def link(assembly, host, binary):
    """Link generated assembly with one Meson-built host library."""
    return run([*shlex.split(os.environ.get("CXX", "g++")), assembly, host, "-o", binary])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("compiler", type=Path)
    for name in ("console", "region", "note", "files"):
        parser.add_argument(f"--{name}-host", type=Path, required=True, help="Meson-built host library")
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    for name in ("console", "region", "note", "files"):
        HOSTS[name] = getattr(args, f"{name}_host").resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="console-service-") as scratch:
        work = Path(scratch)
        mixed_region(compiler, work)
        assembly = work / "console.o"
        facts = work / "console.abi.json"
        result = run(
            [
                compiler,
                "--emit-object",
                "--local-symbols",
                "--referenced-reflection-only",
                "--module-root",
                ROOT / "library",
                ROOT / "examples/kernel-console-service.au",
                "-o",
                assembly,
                "--abi-facts",
                facts,
            ]
        )
        require(result.returncode == 0, result.stderr.decode())
        compose_object_bridge(
            assembly, [ROOT / "kernel/uefi/console-service-entry.S"], json.loads(facts.read_text()), compiler=compiler
        )
        binary = work / "editor"
        result = link(assembly, HOSTS["console"], binary)
        require(result.returncode == 0, result.stderr.decode())
        ready = b"AURORA_CONSOLE_READY: UEFI, ASCII, 64-byte lines\r\naurora> "
        exit_output = b"exit\r\nAURORA_CONSOLE_EXIT\r\n"

        def execute(samples, limit=2**64 - 1, malformed=0, sessions=1):
            data = "".join(f"{present} {byte} {damage}\n" for present, byte, damage in samples).encode()
            return run([binary, limit, malformed, sessions], input=data)

        def samples(value):
            return [(1, byte, 0) for byte in value]

        normal = execute(samples(b"help\r\nstatus\nexit\n"))
        require(normal.returncode == 0, normal.stderr.decode())
        require(normal.stdout.startswith(ready) and normal.stdout.endswith(exit_output), "normal transcript boundaries")
        require(normal.stdout.count(b"help    Show commands") == 1, "CRLF submitted twice")
        require(b"timer-woken polling; line capacity=64" in normal.stdout, "missing Aurora status presentation")
        for data in [b"e\x08exit\n", b"x\x7fexit\n", b"\x08\x7fexit\n"]:
            result = execute(samples(data))
            require(result.returncode == 0 and result.stdout.endswith(exit_output), "edit/empty-backspace regression")
        for bad in [b"x" * 64, b"x" * 65 + b"\x08exit", b"exit ", b"\x1bexit", b"\xffexit", b"a\x00exit"]:
            result = execute(samples(bad + b"\nexit\n"))
            require(result.returncode == 0 and result.stdout.endswith(exit_output), "bad-line recovery failed")
            expected = b"Unknown command." if bad in [b"x" * 64, b"exit "] else b"Line rejected:"
            require(expected in result.stdout, "line rejection/unknown distinction changed")
        for byte in range(256):
            if 32 <= byte <= 126 or byte in (8, 10, 13, 127):
                continue
            result = execute(samples(bytes([byte]) + b"exit\nexit\n"))
            require(result.returncode == 0 and b"Line rejected:" in result.stdout, f"unsafe input byte {byte}")
        for delimiter in (10, 13):
            value = samples(b"exit") + [(1, delimiter, 1), (0, 0, 1)] + samples(b"exit\nexit\n")
            result = execute(value)
            require(
                result.returncode == 0 and result.stdout.count(b"Line rejected:") == 2, "damage delimiter propagation"
            )
        result = execute([(0, 0, 1)] + samples(b"exit\nexit\n"))
        require(result.returncode == 0 and result.stdout.count(b"Line rejected:") == 1, "absent damage ignored")
        # The real generated service owns one bounded RAM-only note per invocation.
        written = b"note: RAM-only; lost when session exits.\r\n"
        missing = b"note: not found (RAM-only).\r\n"

        def readback(content):
            return b"cat note\r\n" + content + b"\r\naurora> "

        result = execute(samples(b"cat note\nexit\n"))
        require(result.returncode == 0 and missing in result.stdout, "fresh note should be missing")
        script = samples(b"write note first value\r\n") + [(0, 0, 0)] * 20
        script += samples(b"status\nhelp\nunknown\n\ncat note\ncat note\nexit\n")
        result = execute(script)
        require(result.returncode == 0 and result.stdout.count(written) == 1, "write replayed after CRLF/idle/commands")
        require(result.stdout.count(readback(b"first value")) == 2, "note did not survive idle/other commands")
        for content in (b"", b"x", b" " * 53, b"!" * 53, b"a b "):
            script = samples(b"write note longer old suffix\nwrite note " + content + b"\ncat note\nexit\n")
            result = execute(script)
            require(result.returncode == 0 and readback(content) in result.stdout, f"exact replacement {content!r}")
            require(result.stdout.count(written) == 2, "accepted write count changed")
        malformed_writes = (
            b"write note",
            b"write notes new",
            b"write noteX new",
            b"write  note new",
            b"Write note new",
            b"write note " + b"x" * 54,
            b"write note " + b"x" * 54 + b"\b",
            b"write note new\x00",
            b"write note new\xff",
            b"write note new\x1b",
        )
        for value in malformed_writes:
            result = execute(samples(b"write note saved\n" + value + b"\ncat note\nexit\n"))
            require(
                result.returncode == 0 and readback(b"saved") in result.stdout, f"bad write mutated note: {value!r}"
            )
            require(result.stdout.count(written) == 1, "bad write was acknowledged")
        for damage in ([(0, 0, 1)], [(1, ord("x"), 1)], [(1, 10, 1)], [(1, 13, 1)]):
            script = samples(b"write note saved\nwrite note replacement") + damage
            script += samples(b"\ncat note\nexit\n")
            result = execute(script)
            require(result.returncode == 0 and readback(b"saved") in result.stdout, "UART damage mutated note")
            require(result.stdout.count(written) == 1, "damaged write was acknowledged")
        script = samples(b"write note saved\r") + [(1, 10, 1)]
        script += samples(b"write note replacement\n\ncat note\nexit\n")
        result = execute(script)
        require(result.returncode == 0 and readback(b"saved") in result.stdout, "damaged suppressed LF lost rejection")
        require(result.stdout.count(written) == 1, "damage or empty line replayed a write")
        result = execute(samples(b"write notf\be edited\ncat note\nexit\n"))
        require(result.returncode == 0 and readback(b"edited") in result.stdout, "edited write failed")
        result = execute(samples(b"write note secret\nexit\ncat note\nexit\n"), sessions=2)
        require(result.returncode == 0 and result.stdout.count(ready) == 2, "second invocation did not run")
        require(result.stdout.count(missing) == 1, "note survived session exit in the same process")

        # Named files share this session without changing the separate note policy.
        def file_written(name, count):
            return b"wrote " + name + b": " + str(count).encode() + (b" byte\r\n" if count == 1 else b" bytes\r\n")

        def file_read(name, content):
            return b"cat " + name + b"\r\n" + content + b"\r\naurora> "

        result = execute(
            samples(b"append absent x\nwrite a lower\nappend a case\nappend a \ncat a\nappend note x\nexit\n")
        )
        require(
            result.returncode == 0
            and file_read(b"a", b"lowercase") in result.stdout
            and file_written(b"a", 4) in result.stdout
            and file_written(b"a", 0) in result.stdout
            and b"files: not found (RAM-only)." in result.stdout
            and b"files: note is reserved." in result.stdout,
            "shared append command semantics",
        )
        result = execute(samples(b"write a original\ncopy a b\nwrite a changed\ncat b\ncat a\ncopy a a\nexit\n"))
        require(
            result.returncode == 0
            and file_read(b"b", b"original") in result.stdout
            and file_read(b"a", b"changed") in result.stdout
            and file_written(b"b", 8) in result.stdout,
            "copy retains independent source/destination bytes",
        )
        for command in (
            b"copy",
            b"copy ",
            b"copy a",
            b"copy a ",
            b"copy  a",
            b"copy a  b",
            b"copy a b ",
            b"copy a b c",
            b"copy a .",
            b"copy .. b",
            b"copy a abcdefghi",
            b"copy a/b c",
        ):
            result = execute(samples(b"write a saved\n" + command + b"\ncat a\nls\nexit\n"))
            require(
                result.returncode == 0
                and b"files: invalid name or content." in result.stdout
                and file_read(b"a", b"saved") in result.stdout
                and b"files: a\r\n" in result.stdout,
                f"copy grammar changed store: {command!r}",
            )
        script = b"write a first\nwrite b second\nwrite c third\nwrite d fourth\nwrite e fifth\n"
        script += b"write a x\ncat a\nrm b\nwrite e \nls\ncat e\nrm absent\ncat absent\nrm note\nexit\n"
        result = execute(samples(script))
        require(result.returncode == 0 and result.stdout.count(b"\r\nwrote ") == 6, "four-file write/replacement count")
        for expected in (
            b"files: full (4 files).\r\n",
            b"files: a e c d\r\n",
            b"files: note is reserved.\r\n",
            file_written(b"a", 5),
            file_written(b"b", 6),
            file_written(b"c", 5),
            file_written(b"d", 6),
            file_written(b"a", 1),
            file_written(b"e", 0),
            file_read(b"a", b"x"),
            file_read(b"e", b""),
        ):
            require(expected in result.stdout, "named-file capacity, slot reuse or exact readback")
        require(result.stdout.count(b"files: not found (RAM-only).\r\n") == 2, "missing cat/rm outcomes")
        for name in (b"x", b"abcdefgh", b"A._-09z", b"notes", b"Note"):
            for content in (b"", b"x", b"x" * 9, b"x" * 10, b" " * 49, b"!" * 49, b"space and suffix "):
                result = execute(samples(b"write " + name + b" " + content + b"\ncat " + name + b"\nexit\n"))
                require(
                    result.returncode == 0
                    and file_read(name, content) in result.stdout
                    and file_written(name, len(content)) in result.stdout,
                    "name/content boundary and exact write confirmation",
                )
        result = execute(samples(b"write a first\nwrite ab second\nwrite a x\ncat a\ncat ab\nrm a\ncat ab\nexit\n"))
        require(
            result.returncode == 0
            and file_read(b"a", b"x") in result.stdout
            and result.stdout.count(file_read(b"ab", b"second")) == 2,
            "filename equality must distinguish a complete name from its prefix",
        )
        bad_files = (
            b"w",
            b"wr",
            b"wri",
            b"writ",
            b"writeX a x",
            b"ca",
            b"catX a",
            b"r",
            b"rmX a",
            b"l",
            b"lsX",
            b"write a",
            b"write  a x",
            b"write abcdefghi x",
            b"write . x",
            b"write .. x",
            b"write a/b x",
            b"write a\\b x",
            b"write a " + b"x" * 50,
            b"cat a ",
            b"rm a x",
            b"ls extra",
            b"write",
            b"cat",
            b"rm",
            b"write a bad\x00",
            b"write a bad\xff",
        )
        for command in bad_files:
            result = execute(samples(b"write a saved\n" + command + b"\ncat a\nls\nexit\n"))
            require(
                result.returncode == 0 and file_read(b"a", b"saved") in result.stdout, "bad file command mutated state"
            )
            require(
                result.stdout.count(file_written(b"a", 5)) == 1 and b"files: a\r\n" in result.stdout,
                "failed command created file",
            )
        result = execute(samples(b"write a lower\nwrite A upper\nwrite aa prefix\ncat a\ncat A\ncat aa\nexit\n"))
        require(
            all(
                file_read(name, value) in result.stdout
                for name, value in ((b"a", b"lower"), (b"A", b"upper"), (b"aa", b"prefix"))
            ),
            "case/prefix distinctions",
        )
        for damage in ([(0, 0, 1)], [(1, ord("x"), 1)], [(1, 13, 1)]):
            result = execute(samples(b"write a saved\nwrite a bad") + damage + samples(b"\ncat a\nexit\n"))
            require(
                result.returncode == 0 and file_read(b"a", b"saved") in result.stdout,
                "damaged file command mutated state",
            )
        result = execute(samples(b"write a valueX\b!\r\ncat a\r\nexit\n"))
        require(result.returncode == 0 and file_read(b"a", b"value!") in result.stdout, "file edit/CRLF")
        result = execute(samples(b"write a secret\nexit\ncat a\nls\nexit\n"), sessions=2)
        require(
            result.returncode == 0
            and b"files: not found (RAM-only).\r\n" in result.stdout
            and b"files: empty (RAM-only).\r\n" in result.stdout,
            "files survived session exit",
        )
        file_script = samples(b"write a x\ncat a\nrm a\nls\nexit\n")
        file_normal = execute(file_script)
        require(file_normal.returncode == 0, "file output baseline failed")
        for position in range(len(file_normal.stdout)):
            result = execute(file_script, position)
            require(
                result.returncode == 1 and result.stdout == file_normal.stdout[:position],
                f"file output timeout retried or changed prefix at {position}",
            )
        note_script = samples(b"cat note\nwrite note abc\ncat note\nwrite note \ncat note\nexit\n")
        note_normal = execute(note_script)
        require(note_normal.returncode == 0, "note output baseline failed")
        for position in range(len(note_normal.stdout)):
            result = execute(note_script, position)
            require(
                result.returncode == 1 and result.stdout == note_normal.stdout[:position],
                f"note output timeout retried or changed prefix at {position}",
            )
        for position in range(len(normal.stdout)):
            result = execute(samples(b"help\r\nstatus\nexit\n"), position)
            require(
                result.returncode == 1 and result.stdout == normal.stdout[:position],
                f"output timeout retried, ignored or changed prefix at {position}",
            )
        for malformed in range(1, 6):
            result = execute(samples(b"exit\n"), malformed=malformed)
            require(result.returncode < 0, f"noncanonical report {malformed} accepted")
        # Exercise the reusable note policy without trusting the line editor to
        # sanitize its public copied-buffer/count input or preserve copied values.
        policy = work / "note-policy.au"
        policy.write_text("""module note_policy;
import console.session_note;
import std.binary_buffer;
import std.binary;
auto note_contract() -> i64 {
    const std::BinaryBuffer64 empty = std::BinaryBuffer64();
    console::SessionNote note = console::SessionNote(empty);
    if (note.size() != -1) { return 1; }
    std::BinaryBuffer64 command = std::BinaryBuffer64();
    array<u8, 13> text = "write note xy";
    i64 index = 0;
    while (index < 13) { command.write_u8(index, text[index]); index = index + 1; }
    if (note.submit(command, 13) != console::NoteEvent::written) { return 2; }
    const console::SessionNote copy = note;
    if (note.submit(command, -1) != console::NoteEvent::unknown
        || note.submit(command, 65) != console::NoteEvent::unknown) { return 3; }
    i64 byte = 0;
    while (byte < 256) {
        if (byte < 32 || byte > 126) {
            command.write_u8(12, u8(byte));
            if (note.submit(command, 13) != console::NoteEvent::unknown
                || note.size() != 2 || note.at(1) != 'y') { return 4; }
        }
        byte = byte + 1;
    }
    if (note.submit(command, 12) != console::NoteEvent::written
        || note.size() != 1 || note.at(0) != 'x' || copy.size() != 2 || copy.at(1) != 'y') { return 5; }
    index = 1;
    while (index < 64) { if (note.at(index) != '\\0') { return 6; } index = index + 1; }
    return 0;
}
""")
        policy_assembly, policy_binary = work / "note-policy.s", work / "note-policy"
        result = run([compiler, "--module-root", ROOT / "library", policy, "-o", policy_assembly])
        require(result.returncode == 0, result.stderr.decode())
        result = link(policy_assembly, HOSTS["note"], policy_binary)
        require(result.returncode == 0, result.stderr.decode())
        result = run([policy_binary])
        require(result.returncode == 0, "shared note policy count/content/copy/suffix contract")
        # Existing hosted policy fixture also observes complete private copied records.
        files_source = work / "files-policy.au"
        files_source.write_text("""module files_policy;
import std.bytes;
import console.session_files;
import console.protected_files;
import std.binary_buffer;
import std.binary;
auto pack(builtin::span<const u8> text) -> std::BinaryBuffer64 {
    std::BinaryBuffer64 command = std::BinaryBuffer64();
    i64 index = 0;
    while (index < text.size()) { command.write_u8(index, text.at(index)); index = index + 1; }
    return command;
}
auto span_compare_contract() -> i64 {
    array<u8, 5> source = "a\\0\\xffbc";
    array<u8, 3> pattern = "a\\0\\xff";
    const builtin::span<const u8> bytes = borrow_bytes(source);
    const builtin::span<const u8> prefix = borrow_bytes(pattern);
    const builtin::span<const u8> empty = bytes.subspan(5, 0);
    if (!std::starts_with(bytes, prefix) || std::equal(bytes, prefix)
        || !std::equal(bytes.subspan(0, 3), prefix)
        || !std::equal(bytes, bytes) || !std::equal(empty, prefix.subspan(1, 0))
        || !std::starts_with(bytes, empty) || !std::starts_with(empty, empty)
        || std::starts_with(empty, prefix) || std::starts_with(prefix, bytes)) { return 1; }
    array<u8, 3> different = "a\\0\\xfe";
    if (std::equal(prefix, borrow_bytes(different))
        || std::starts_with(bytes, borrow_bytes(different))) { return 2; }
    i64 value = 0;
    while (value < 256) {
        array<u8, 1> left = {u8(value)};
        array<u8, 1> same = {u8(value)};
        array<u8, 1> other = {u8((value + 1) % 256)};
        std::BinaryBuffer64 current = std::BinaryBuffer64();
        current.write_u8(0, u8(value));
        if (!current.equal(0, 1, borrow_bytes(same))
            || current.equal(0, 1, borrow_bytes(other))) { return 10; }
        if (!std::equal(borrow_bytes(left), borrow_bytes(same))
            || !std::starts_with(borrow_bytes(left), borrow_bytes(same))
            || std::equal(borrow_bytes(left), borrow_bytes(other))
            || std::starts_with(borrow_bytes(left), borrow_bytes(other))) { return 3; }
        value = value + 1;
    }
    std::BinaryBuffer64 buffer = std::BinaryBuffer64();
    array<u8, 65> full = "                                                                 ";
    const builtin::span<const u8> all = borrow_bytes(full);
    i64 index = 0;
    while (index < 64) { buffer.write_u8(index, ' '); index = index + 1; }
    if (!buffer.starts_with(64, all.subspan(0, 64)) || !buffer.starts_with(64, empty)
        || buffer.starts_with(64, all) || buffer.starts_with(64, prefix)) { return 4; }
    if (!buffer.starts_with(0, empty) || buffer.starts_with(63, all.subspan(0, 64))
        || buffer.starts_with(-1, empty) || buffer.starts_with(65, empty)
        || buffer.starts_with(-9223372036854775808, empty)
        || buffer.starts_with(9223372036854775807, empty)) { return 8; }
    if (!buffer.equal(0, 64, all.subspan(0, 64)) || !buffer.equal(64, 0, empty)
        || buffer.equal(0, 64, all) || buffer.equal(63, 2, all.subspan(0, 2))
        || buffer.equal(-1, 0, empty) || buffer.equal(65, 0, empty)
        || buffer.equal(0, -1, empty) || buffer.equal(0, 65, empty)
        || buffer.equal(-9223372036854775808, 0, empty)
        || buffer.equal(9223372036854775807, 0, empty)
        || buffer.equal(0, -9223372036854775808, empty)
        || buffer.equal(0, 9223372036854775807, empty)) { return 9; }
    buffer.write_u8(63, 'x');
    if (buffer.starts_with(64, all.subspan(0, 64))) { return 5; }
    buffer.write_u8(63, ' ');
    if (!buffer.starts_with(64, all.subspan(0, 64))) { return 6; }
    buffer.write_u8(0, 'x');
    if (buffer.starts_with(64, all.subspan(0, 64))) { return 7; }
    return 0;
}
auto append_contract() -> i64 {
    const std::BinaryBuffer64 zero = std::BinaryBuffer64();
    console::SessionFiles files = console::SessionFiles(zero);
    const console::FileName name = console::FileName(pack("abcdefgh"), 8);
    const console::FileName reserved = console::FileName(pack("note"), 4);
    const console::FileValue empty = console::FileValue(zero, 0);
    if (files.append_file(name, empty) != console::FileEvent::missing
        || files.append_file(reserved, empty) != console::FileEvent::reserved) { return 1; }
    i64 length = 0;
    while (length <= 49) {
        std::BinaryBuffer64 content = std::BinaryBuffer64();
        i64 index = 0;
        while (index < length) { content.write_u8(index, 'a'); index = index + 1; }
        if (files.write_file(name, console::FileValue(content, length)) != console::FileEvent::written) { return 2; }
        std::BinaryBuffer64 suffix = std::BinaryBuffer64();
        index = 0;
        while (index < 49 - length) { suffix.write_u8(index, 'b'); index = index + 1; }
        if (files.append_file(name, console::FileValue(suffix, 49 - length)) != console::FileEvent::written
            || files.append_file(name, empty) != console::FileEvent::written
            || files.append_file(name, console::FileValue(pack("x"), 1)) != console::FileEvent::invalid) { return 3; }
        const console::FileReply read = files.read_file(name);
        if (read.size() != 49) { return 4; }
        index = 0;
        while (index < 49) {
            if ((index < length && read.at(index) != 'a') || (index >= length && read.at(index) != 'b')) { return 5; }
            index = index + 1;
        }
        length = length + 1;
    }
    array<i64, 5> bad = {-9223372036854775808, -1, 50, 65, 9223372036854775807};
    i64 index = 0;
    while (index < 5) {
        if (files.append_file(name, console::FileValue(zero, bad[index])) != console::FileEvent::invalid
            || files.append_file(console::FileName(zero, bad[index]), empty) != console::FileEvent::invalid) {
            return 6;
        }
        index = index + 1;
    }
    if (files.append_file(name, console::FileValue(zero, 1)) != console::FileEvent::invalid) { return 7; }
    const console::FileReply unchanged = files.read_file(name);
    if (unchanged.size() != 49 || unchanged.at(48) != 'a') { return 8; }
    return 0;
}
auto copy_contract() -> i64 {
    const std::BinaryBuffer64 zero = std::BinaryBuffer64();
    console::SessionFiles files = console::SessionFiles(zero);
    const console::FileName source = console::FileName(pack("Source"), 6);
    const console::FileName destination = console::FileName(pack("abcdefgh"), 8);
    const console::FileName absent = console::FileName(pack("source"), 6);
    const console::FileName reserved = console::FileName(pack("note"), 4);
    const console::FileValue empty = console::FileValue(zero, 0);
    i64 length = 49;
    while (length >= 0) {
        std::BinaryBuffer64 bytes = zero;
        i64 index = 0;
        while (index < length) { bytes.write_u8(index, u8(32 + index)); index = index + 1; }
        if (files.write_file(source, console::FileValue(bytes, length)) != console::FileEvent::written) { return 1; }
        const console::FileReply copied = files.copy_file(source, destination);
        const console::FileReply same = files.copy_file(source, source);
        const console::FileReply original = files.read_file(source);
        const console::FileReply duplicate = files.read_file(destination);
        if (copied.status() != console::FileEvent::written || same.status() != console::FileEvent::written
            || original.size() != length || duplicate.size() != length || duplicate.at(length) != '\\0') { return 2; }
        index = 0;
        while (index < length) {
            if (original.at(index) != u8(32 + index) || duplicate.at(index) != original.at(index)) { return 3; }
            index = index + 1;
        }
        length = length - 1;
    }
    files.write_file(console::FileName(pack("c"), 1), empty);
    files.write_file(console::FileName(pack("d"), 1), empty);
    files.write_file(source, console::FileValue(pack("keep"), 4));
    files.write_file(destination, console::FileValue(pack("other"), 5));
    const console::FileReply full = files.copy_file(source, absent);
    const console::FileReply missing = files.copy_file(absent, destination);
    const console::FileReply kept_source = files.read_file(source);
    const console::FileReply kept_destination = files.read_file(destination);
    const console::FileReply kept_absent = files.read_file(absent);
    if (kept_source.size() != 4 || kept_source.at(3) != 'p'
        || kept_destination.size() != 5 || kept_destination.at(4) != 'r'
        || kept_absent.status() != console::FileEvent::missing) { return 9; }
    const console::FileReply replaced = files.copy_file(source, destination);
    const console::FileReply self = files.copy_file(source, source);
    if (full.status() != console::FileEvent::full || missing.status() != console::FileEvent::missing
        || replaced.status() != console::FileEvent::written || self.status() != console::FileEvent::written) {
            return 4;
        }
    array<i64, 7> invalid = {-9223372036854775808, -1, 0, 9, 64, 65, 9223372036854775807};
    i64 index = 0;
    while (index < 7) {
        const console::FileName bad = console::FileName(pack("Source"), invalid[index]);
        const console::FileReply left = files.copy_file(bad, reserved);
        const console::FileReply right = files.copy_file(reserved, bad);
        if (left.status() != console::FileEvent::invalid || right.status() != console::FileEvent::invalid) { return 5; }
        index = index + 1;
    }
    const console::FileReply reserved_source = files.copy_file(reserved, destination);
    const console::FileReply reserved_destination = files.copy_file(source, reserved);
    if (reserved_source.status() != console::FileEvent::reserved
        || reserved_destination.status() != console::FileEvent::reserved) { return 6; }
    console::ProtectedFiles protected_store = console::ProtectedFiles(files);
    const console::FileSelection selected = protected_store.select(pack("upper Source"), 12);
    const console::FileReply rejected = protected_store.submit(pack("copy Source source"), 18);
    const console::FileReply retained = protected_store.project(selected);
    const console::FileReply successful = protected_store.submit(pack("copy Source abcdefgh"), 20);
    const console::FileReply stale = protected_store.project(selected);
    if (rejected.status() != console::FileEvent::full || retained.status() != console::FileEvent::read
        || successful.status() != console::FileEvent::written || stale.status() != console::FileEvent::invalid) {
            return 7;
        }
    const console::FileSelection fresh = protected_store.select(pack("upper Source"), 12);
    const console::FileReply self_copy = protected_store.submit(pack("copy Source Source"), 18);
    const console::FileReply stale_self = protected_store.replace(fresh, pack("wrong"), 5);
    if (self_copy.status() != console::FileEvent::written || stale_self.status() != console::FileEvent::invalid) {
            return 8;
        }
    return 0;
}
auto typed_files_contract() -> i64 {
    const std::BinaryBuffer64 zero = std::BinaryBuffer64();
    const std::BinaryBuffer64 a = pack("a");
    const std::BinaryBuffer64 saved_bytes = pack("saved");
    const std::BinaryBuffer64 dot = pack(".");
    const std::BinaryBuffer64 dots = pack("..");
    const std::BinaryBuffer64 note = pack("note");
    console::SessionFiles files = console::SessionFiles(zero);
    const console::FileName name = console::FileName(a, 1);
    const console::FileValue empty = console::file_value(zero, 64, 0);
    const console::FileValue saved = console::FileValue(saved_bytes, 5);
    if (files.write_file(name, saved) != console::FileEvent::written) { return 1; }
    const console::SessionFiles copy = files;
    array<i64, 7> bad_counts = {-9223372036854775808, -1, 50, 64, 65, 255, 9223372036854775807};
    i64 index = 0;
    while (index < 7) {
        const console::FileValue bad = console::FileValue(zero, bad_counts[index]);
        const console::FileName invalid = console::FileName(a, bad_counts[index]);
        const console::FileReply read = files.read_file(invalid);
        const console::FileReply formatted_name =
            console::file_write_reply(invalid, empty.size(), console::FileEvent::written);
        const console::FileReply formatted_value =
            console::file_write_reply(name, bad.size(), console::FileEvent::written);
        if (files.write_file(name, bad) != console::FileEvent::invalid
            || files.write_file(invalid, empty) != console::FileEvent::invalid
            || files.remove(invalid) != console::FileEvent::invalid
            || read.status() != console::FileEvent::invalid
            || formatted_name.status() != console::FileEvent::invalid
            || formatted_value.status() != console::FileEvent::invalid) { return 2; }
        index = index + 1;
    }
    array<i64, 4> bad_offsets = {-9223372036854775808, -1, 65, 9223372036854775807};
    index = 0;
    while (index < 4) {
        const console::FileName bad_name = console::file_name(a, bad_offsets[index], 1);
        const console::FileValue bad_value = console::file_value(zero, bad_offsets[index], 0);
        if (bad_name.valid() || bad_value.valid()) { return 3; }
        index = index + 1;
    }
    const console::FileName off_end = console::file_name(a, 64, 1);
    const console::FileValue crosses_end = console::file_value(zero, 63, 2);
    const console::FileName one_dot = console::FileName(dot, 1);
    const console::FileName two_dots = console::FileName(dots, 2);
    const console::FileName long_name = console::FileName(a, 9);
    const console::FileName no_name = console::FileName(a, 0);
    if (off_end.valid() || crosses_end.valid() || one_dot.valid()
        || two_dots.valid() || long_name.valid() || no_name.valid()) { return 4; }
    std::BinaryBuffer64 input = pack("ax");
    i64 byte = 0;
    while (byte < 256) {
        input.write_u8(1, u8(byte));
        const console::FileName candidate = console::FileName(input, 2);
        const bool allowed = (byte >= 97 && byte <= 122) || (byte >= 65 && byte <= 90)
            || (byte >= 48 && byte <= 57) || byte == 46 || byte == 95 || byte == 45;
        if (candidate.valid() != allowed) { return 5; }
        const console::FileValue value = console::file_value(input, 1, 1);
        if (value.valid() != (byte >= 32 && byte <= 126)) { return 6; }
        if (!allowed && files.write_file(candidate, empty) != console::FileEvent::invalid) { return 7; }
        if (!value.valid() && files.write_file(name, value) != console::FileEvent::invalid) { return 8; }
        byte = byte + 1;
    }
    const console::FileName reserved = console::FileName(note, 4);
    const console::FileValue invalid = console::FileValue(zero, 1);
    const console::FileReply reserved_read = files.read_file(reserved);
    if (files.write_file(reserved, invalid) != console::FileEvent::invalid
        || files.write_file(reserved, empty) != console::FileEvent::reserved
        || reserved_read.status() != console::FileEvent::reserved
        || files.remove(reserved) != console::FileEvent::reserved) { return 9; }
    const console::FileReply unchanged = files.read_file(name);
    const console::FileReply copied = copy.read_file(name);
    if (unchanged.size() != 5 || unchanged.at(4) != 'd'
        || copied.size() != 5 || !empty.valid() || empty.size() != 0) { return 10; }
    if (files.write_file(name, empty) != console::FileEvent::written) { return 11; }
    const console::FileReply blank = files.read_file(name);
    if (blank.size() != 0 || files.remove(name) != console::FileEvent::removed) { return 12; }
    const console::FileReply missing = files.read_file(name);
    const console::FileReply retained = copy.read_file(name);
    if (missing.status() != console::FileEvent::missing || retained.size() != 5) { return 13; }
    std::BinaryBuffer64 malformed = zero;
    malformed.write_u8(0, 255u8);
    if (name.matches(malformed)) { return 14; }
    return 0;
}
auto files_contract() -> i64 {
    if (size_of(console::SessionFiles) != 264 || size_of(console::FileReply) != 80) { return 1; }
    const std::BinaryBuffer64 zero = std::BinaryBuffer64();
    console::SessionFiles files = console::SessionFiles(zero);
    std::BinaryBuffer64 command = std::BinaryBuffer64();
    array<u8, 64> maximum = "write abcdefgh xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx";
    i64 index = 0;
    while (index < 64) { command.write_u8(index, maximum[index]); index = index + 1; }
    const console::FileReply first = files.submit(command, 64);
    if (first.status() != console::FileEvent::written || first.size() != 24) { return 2; }
    // The backing still contains a complete write; only count defines the command.
    i64 count = 0;
    while (count < 8) {
        const console::FileReply truncated = files.submit(command, count);
        if ((count < 5 && truncated.status() != console::FileEvent::unknown)
            || (count >= 5 && truncated.status() != console::FileEvent::invalid)) { return 7; }
        count = count + 1;
    }
    console::SessionFiles copy = files;
    const console::FileReply negative = files.submit(command, -1);
    const console::FileReply oversized = files.submit(command, 65);
    if (negative.status() != console::FileEvent::invalid
        || oversized.status() != console::FileEvent::invalid) { return 3; }
    array<u8, 12> read = "cat abcdefgh";
    i64 byte = 0;
    while (byte < 256) {
        if (byte < 32 || byte > 126) {
            command.write_u8(63, u8(byte));
            const console::FileReply invalid = files.submit(command, 64);
            const std::BinaryBuffer64 command_unchanged = pack(borrow_bytes(read));
            const console::FileReply unchanged = files.submit(command_unchanged, 12);
            if (invalid.status() != console::FileEvent::invalid || unchanged.size() != 49
                || unchanged.at(48) != 'x') { return 4; }
        }
        byte = byte + 1;
    }
    array<u8, 16> shorter = "write abcdefgh y";
    const std::BinaryBuffer64 command_replaced = pack(borrow_bytes(shorter));
    const console::FileReply replaced = files.submit(command_replaced, 16);
    const std::BinaryBuffer64 command_saved = pack(borrow_bytes(read));
    const console::FileReply saved = copy.submit(command_saved, 12);
    const std::BinaryBuffer64 command_current = pack(borrow_bytes(read));
    const console::FileReply current = files.submit(command_current, 12);
    if (replaced.status() != console::FileEvent::written || saved.size() != 49
        || current.size() != 1 || current.at(0) != 'y' || current.at(-1) != '\\0'
        || current.at(64) != '\\0') { return 5; }
    std::BinaryBuffer64 poison = std::BinaryBuffer64();
    poison.write_u8(0, 255u8);
    console::SessionFiles hidden = console::SessionFiles(poison);
    array<u8, 2> list = "ls";
    const std::BinaryBuffer64 command_empty = pack(borrow_bytes(list));
    const console::FileReply empty = hidden.submit(command_empty, 2);
    const std::BinaryBuffer64 command_absent = pack(borrow_bytes(read));
    const console::FileReply absent = hidden.submit(command_absent, 12);
    if (empty.size() != 24 || absent.status() != console::FileEvent::missing) { return 6; }
    return 0;
}
auto files_snapshot(i64 stage) -> console::SessionFiles {
    const std::BinaryBuffer64 zero = std::BinaryBuffer64();
    console::SessionFiles files = console::SessionFiles(zero);
    if (stage > 0) {
        array<u8, 64> maximum = "write abcdefgh xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx";
        const std::BinaryBuffer64 command_written = pack(borrow_bytes(maximum));
        const console::FileReply written = files.submit(command_written, 64);
    }
    if (stage > 1) {
        array<u8, 16> shorter = "write abcdefgh y";
        const std::BinaryBuffer64 command_written = pack(borrow_bytes(shorter));
        const console::FileReply written = files.submit(command_written, 16);
    }
    if (stage > 2) {
        array<u8, 15> empty = "write abcdefgh ";
        const std::BinaryBuffer64 command_written = pack(borrow_bytes(empty));
        const console::FileReply written = files.submit(command_written, 15);
    }
    if (stage > 3) {
        array<u8, 11> remove = "rm abcdefgh";
        const std::BinaryBuffer64 command_removed = pack(borrow_bytes(remove));
        const console::FileReply removed = files.submit(command_removed, 11);
    }
    if (stage > 4) {
        const console::FileReply source = files.submit(pack("write src x"), 11);
        const console::FileReply destination = files.submit(pack("write dest old suffix"), 21);
        if (stage == 6) { const console::FileReply blank = files.submit(pack("write src "), 10); }
        const console::FileReply copied = files.submit(pack("copy src dest"), 13);
    }
    return files;
}
""")
        files_assembly, files_binary = work / "files-policy.s", work / "files-policy"
        result = run([compiler, "--module-root", ROOT / "library", files_source, "-o", files_assembly])
        require(result.returncode == 0, result.stderr.decode())
        with files_assembly.open("a") as stream:
            stream.write("""
.text
.global checked_files_snapshot
.type checked_files_snapshot,@function
checked_files_snapshot:
    pushq %rbp
    movq %rsp,%rbp
    subq $16,%rsp
    movq %rdi,(%rsp)
    movq %rsp,%r11
    movq %rsi,%r10
    call __au_v_m1_12files_policy_n0__d14files_snapshot
    leave
    ret
.size checked_files_snapshot,.-checked_files_snapshot
""")
        result = link(files_assembly, HOSTS["files"], files_binary)
        require(result.returncode == 0, result.stderr.decode())
        result = run([files_binary])
        require(
            result.returncode == 0, f"shared files policy count/content/copy/zero-suffix contract: {result.returncode}"
        )
        # Reuse the six-formal mixed ABI graph for copied nested/array/enum inputs
        # and results. Independent snapshots cross two calls beside scalars/spans;
        # the host put also retains its odd scalar-expression-depth coverage.
        abi_source = work / "mixed-abi.au"
        abi_source.write_text("""module kernel_console_service;
    enum class Marker { okay, wrong };
    class Payload {
        builtin::ConsoleSample observation;
        array<u8, 3> bytes;
        Marker marker;
    public:
        Payload(builtin::ConsoleSample sample) : observation(sample), bytes{}, marker(Marker::okay) {}
        auto initialize() -> bool { bytes[0] = 'A'; bytes[2] = 255u8; return true; }
        auto matches(u8 first, Marker expected) const -> bool {
            const builtin::ConsoleSample sample = observation;
            return sample.byte_present && sample.byte == 'A' && !sample.damaged
                && bytes[0] == first && bytes[1] == 0u8 && bytes[2] == 255u8 && marker == expected;
        }
        auto change() -> bool { bytes[0] = 'B'; marker = Marker::wrong; return true; }
    };
    class Reply {
        builtin::ConsoleSample observation;
        i64 copied_count;
        Payload copied_payload;
    public:
        Reply(builtin::ConsoleSample sample, i64 count, Payload value)
            : observation(sample), copied_count(count), copied_payload(value) {}
        auto sample() const -> builtin::ConsoleSample {
            return observation;
        }
        auto count() const -> i64 { return copied_count; }
        auto payload() const -> Payload {
            return copied_payload;
        }
    };
    auto number(builtin::ConsolePutResult status) -> i64 {
        if (status == builtin::ConsolePutResult::success) { return 7; }
        return -100;
    }
    auto odd(builtin::ConsoleSession& session) -> i64 {
        return 1 + number(session.put('z'));
    }
    auto leaf(builtin::ConsoleSession& session, u8 a, Payload value, builtin::span<const u8> text,
              i64 b, Marker marker) -> Reply {
        const builtin::ConsoleSample report = session.next();
        Payload changed = value;
        if (!changed.change() || !value.matches('A', Marker::okay)
            || !changed.matches('B', Marker::wrong) || text.size() != 3 || text.at(1) != 'y'
            || a != 'A' || b != 41 || marker != Marker::okay) {
            session.put('!');
        }
        const Reply result = Reply(report, b, changed);
        return result;
    }
    auto forward(builtin::ConsoleSession& session, Payload value, builtin::span<const u8> text,
                 i64 b, bool flag, Marker marker) -> Reply {
        u8 a = '?';
        if (flag) { a = 'A'; }
        const Reply result = leaf(session, a, value, text, b, marker);
        if (!value.matches('A', Marker::okay)) { session.put('!'); }
        return result;
    }
    auto console_service(builtin::ConsoleSession& session) -> builtin::ConsoleCompletion {
        const builtin::ConsoleSample sample = builtin::ConsoleSample{
            .byte_present = true, .byte = 'A', .damaged = false};
        Payload original = Payload(sample);
        original.initialize();
        const Reply result = forward(session, original, "xyz", 41, true, Marker::okay);
        const builtin::ConsoleSample report = result.sample();
        const Payload copied = result.payload();
        if (!original.matches('A', Marker::okay) || !copied.matches('B', Marker::wrong)
            || !report.byte_present || report.byte != 'Q' || report.damaged || result.count() != 41 || \
odd(session) != 8) {
            session.put('?');
        }
        return builtin::ConsoleCompletion::requested_exit;
    }
    auto aurora_kernel_value() -> i64 { return 42; }
    """)
        abi_assembly = work / "mixed-abi.s"
        abi_facts = work / "mixed-abi.json"
        result = run([compiler, abi_source, "-o", abi_assembly, "--abi-facts", abi_facts])
        require(result.returncode == 0, result.stderr.decode())
        abi_assembly.write_text(abi_assembly.read_text() + service_bridge(abi_facts))
        abi_binary = work / "mixed-abi"
        result = link(abi_assembly, HOSTS["console"], abi_binary)
        require(result.returncode == 0, result.stderr.decode())
        result = run([abi_binary], input=b"1 81 0\n")
        require(
            result.returncode == 0 and result.stdout == b"z", "mixed copied service input/result/span/odd-depth failure"
        )
        modules = work / "modules"
        (modules / "service").mkdir(parents=True)
        (modules / "service/helpers.au").write_text("""export module service.helpers;
    export namespace service_test {
        auto fetch(builtin::ConsoleSession& session) -> builtin::ConsoleSample {
            const builtin::ConsoleSample report = session.next();
            return report;
        }
        auto reflection() -> bool {
            return reflect_size(type_id(builtin::ConsoleSample)) == size_of(builtin::ConsoleSample) &&
                   reflect_field_count(type_id(builtin::ConsoleSample)) == 3 &&
                   reflect_size(type_id(builtin::ConsolePutResult)) == 8 &&
                   reflect_size(type_id(builtin::ConsoleCompletion)) == 8;
        }
        auto copied(builtin::ConsoleSample report) -> bool {
            return !report.byte_present && report.byte == 0u8 && report.damaged;
        }
        class Holder {
            builtin::ConsoleSample sample;
            builtin::ConsolePutResult status;
        public:
            Holder(builtin::ConsoleSample input, builtin::ConsolePutResult result)
                : sample(input), status(result) {}
            auto get() const -> builtin::ConsoleSample {
                const builtin::ConsoleSample saved = sample;
                return saved;
            }
            auto outcome() const -> builtin::ConsolePutResult { return status; }
        };
        auto fetch_saved(builtin::ConsoleSession& session) -> Holder {
            const builtin::ConsoleSample sample = fetch(session);
            const Holder saved = Holder(sample, builtin::ConsolePutResult::success);
            return saved;
        }
    }
    """)
        imported = work / "imported.au"
        imported.write_text("""module kernel_console_service;
    import service.helpers;
    auto console_service(builtin::ConsoleSession& session) -> builtin::ConsoleCompletion {
        const service_test::Holder saved = service_test::fetch_saved(session);
        const builtin::ConsoleSample returned = saved.get();
        const builtin::ConsoleSample synthetic = builtin::ConsoleSample{
            .byte_present = false, .byte = 0u8, .damaged = true};
        if (!service_test::reflection() || !service_test::copied(synthetic) ||
            reflect_size(type_id(builtin::ConsoleSample)) != 24 ||
            reflect_field_count(type_id(builtin::ConsoleSample)) != 3 ||
            !returned.byte_present || returned.byte != 'Q' || !returned.damaged ||
            saved.outcome() != builtin::ConsolePutResult::success) { session.put('?'); }
        session.put('K');
        return builtin::ConsoleCompletion::requested_exit;
    }
    auto aurora_kernel_value() -> i64 { return 42; }
    """)
        imported_assembly = work / "imported.s"
        imported_facts = work / "imported.abi.json"
        result = run(
            [compiler, "--module-root", modules, imported, "-o", imported_assembly, "--abi-facts", imported_facts]
        )
        require(result.returncode == 0, result.stderr.decode())
        imported_assembly.write_text(imported_assembly.read_text() + service_bridge(imported_facts))
        imported_binary = work / "imported"
        result = link(imported_assembly, HOSTS["console"], imported_binary)
        require(result.returncode == 0, result.stderr.decode())
        result = run([imported_binary], input=b"1 81 1\n")
        require(result.returncode == 0 and result.stdout == b"K", "cross-module copied-report/reflection inconsistency")
        write_source = work / "write-result.au"
        write_source.write_text("""module kernel_console_service;
    import console.io;
    auto console_service(builtin::ConsoleSession& session) -> builtin::ConsoleCompletion {
        const builtin::ConsoleSample request = session.next();
        const builtin::ConsoleSample expected = session.next();
        const array<u8, 5> payload = "A\\0\\xffz!";
        const builtin::span<const u8> bytes = borrow_bytes(payload);
        const console::WriteResult result = console::write_bytes(session, bytes.subspan(0, i64(request.byte)));
        const console::WriteResult copied = result;
        const console::WriteResult empty = console::write_bytes(session, bytes.subspan(0, 0));
        const bool complete = expected.byte == request.byte;
        if (result.written() != i64(expected.byte) || copied.written() != result.written()
            || copied.status() != result.status() || copied.complete() != result.complete()
            || result.complete() != complete
            || (complete && result.status() != console::WriteStatus::complete)
            || (!complete && result.status() != console::WriteStatus::timeout)
            || empty.written() != 0 || !empty.complete() || empty.status() != console::WriteStatus::complete) {
            session.put('?');
            return builtin::ConsoleCompletion::output_failure;
        }
        if (!result.complete()) { return builtin::ConsoleCompletion::output_failure; }
        return builtin::ConsoleCompletion::requested_exit;
    }
    auto aurora_kernel_value() -> i64 { return 42; }
    """)
        write_assembly, write_binary = work / "write-result.s", work / "write-result"
        write_facts = work / "write-result.abi.json"
        result = run(
            [
                compiler,
                "--module-root",
                ROOT / "library",
                write_source,
                "-o",
                write_assembly,
                "--abi-facts",
                write_facts,
            ]
        )
        require(result.returncode == 0, result.stderr.decode())
        write_assembly.write_text(write_assembly.read_text() + service_bridge(write_facts))
        result = link(write_assembly, HOSTS["console"], write_binary)
        require(result.returncode == 0, result.stderr.decode())
        # Every short prefix, including NUL/high bytes, first/final-byte timeout,
        # empty calls after timeout, copied reports and exactly one failed attempt.
        for length in range(6):
            for limit in range(length + 1):
                result = run([write_binary, limit], input=f"1 {length} 0\n1 {limit} 0\n".encode())
                failed = int(limit < length)
                require(
                    result.returncode == failed
                    and result.stdout == b"A\x00\xffz!"[:limit]
                    and result.stderr == f"completion={failed} attempts={limit + failed}\n".encode(),
                    f"copied WriteResult prefix/count/status/no-retry contract: length={length}, limit={limit}",
                )
        negative = {
            "by-value": "auto f(builtin::ConsoleSession s) -> i64 { return 0; }",
            "const": "auto f(const builtin::ConsoleSession& s) -> i64 { return 0; }",
            "second": "auto f(i64 n, builtin::ConsoleSession& s) -> i64 { return 0; }",
            "two": "auto f(builtin::ConsoleSession& s, builtin::ConsoleSession& t) -> i64 { return 0; }",
            "local": "auto f(builtin::ConsoleSession& s) -> i64 { builtin::ConsoleSession x = s; return 0; }",
            "value": "auto f(builtin::ConsoleSession& s) -> i64 { return i64(s); }",
            "reflect": "auto f() -> i64 { return size_of(builtin::ConsoleSession); }",
            "reflect-id": "auto f() -> i64 { return type_id(builtin::ConsoleSession); }",
            "reflect-fields": "auto f() -> i64 { return field_count(builtin::ConsoleSession); }",
            "field": "class C { builtin::ConsoleSession session; }; auto f() -> i64 { return 0; }",
            "return": "auto f(builtin::ConsoleSession& s) -> builtin::ConsoleSession { return s; }",
            "region": "auto f(builtin::ConsoleSession& s, i64 n, builtin::ByteRegion r) -> i64 { return n; }",
            "owner": "auto f(builtin::ConsoleSession& s, builtin::OwnedBytes b) -> i64 { return 0; }",
            "owned-class": (
                "class Owner { builtin::OwnedBytes bytes; public: "
                "Owner(builtin::ByteRegion region, builtin::OwnedBytes value) : bytes(move(value)) {} }; "
                "auto f(builtin::ConsoleSession& s, Owner value) -> i64 { return 0; }"
            ),
            "seven-formals": (
                "class Value { public: i64 count; }; "
                "auto f(builtin::ConsoleSession& s, Value value, i64 a, i64 b, i64 c, i64 d, i64 e) "
                "-> i64 { return 0; }"
            ),
            "recursive": "auto f(builtin::ConsoleSession& s) -> i64 { return f(s); }",
            "scalar-cycle": (
                "auto again() -> i64 { return again(); } auto f(builtin::ConsoleSession& s) -> i64 { return again(); }"
            ),
            "suspended": (
                "auto g(builtin::ConsoleSession& s, builtin::ConsolePutResult n) -> i64 { return 0; } "
                "auto f(builtin::ConsoleSession& s) -> i64 { return g(s, s.put(65u8)); }"
            ),
            "overload": "auto f(builtin::ConsoleSession& s) -> i64 { return 0; } auto f(i64 s) -> i64 { return 0; }",
            "forged": "auto g(builtin::ConsoleSession& s) -> i64 { return 0; } auto f() -> i64 { return g(0); }",
            "wrong-put": "auto f(builtin::ConsoleSession& s) -> i64 { s.put(65); return 0; }",
            "unknown-op": "auto f(builtin::ConsoleSession& s) -> i64 { return s.read_port(1); }",
            "shadow": "namespace builtin { class ConsoleSession {}; } auto f() -> i64 { return 0; }",
            "template": (
                "template<Scalar T> auto f(builtin::ConsoleSession& s, T n) -> i64 { return 0; } "
                "auto answer() -> i64 { return 0; }"
            ),
            "owner-result": "auto f(builtin::ConsoleSession& s) -> builtin::OwnedBytes { return 0; }",
            "span-result": (
                "auto f(builtin::ConsoleSession& s, builtin::span<const u8> bytes) "
                "-> builtin::span<const u8> { return bytes; }"
            ),
            "reference-result": (
                "class Reply { public: i64 count; }; auto f(builtin::ConsoleSession& s) -> Reply& { return s; }"
            ),
            "copied-result-incomplete": (
                "class Reply { public: i64 count; }; "
                "auto f(builtin::ConsoleSession& s, bool ready) -> Reply { "
                "if (ready) { const Reply result = Reply{.count = 0}; return result; } }"
            ),
            "copied-result-suspended": (
                "class Reply { public: i64 count; }; "
                "auto g(builtin::ConsoleSession& s, builtin::ConsolePutResult status) -> Reply { "
                "const Reply result = Reply{.count = 0}; return result; } "
                "auto f(builtin::ConsoleSession& s) -> Reply { const Reply result = g(s, s.put(65u8)); return result; }"
            ),
            "copied-input-suspended": (
                "class Value { builtin::ConsolePutResult status; public: "
                "Value(builtin::ConsolePutResult result) : status(result) {} }; "
                "auto use(builtin::ConsoleSession& s, Value value) -> i64 { return 0; } "
                "auto f(builtin::ConsoleSession& s) -> i64 { return use(s, Value(s.put(65u8))); }"
            ),
        }
        borrowed_parameter_error = (
            "AU2001: borrowed parameters require a supported leading ownership reference signature "
            "on an ordinary function"
        )
        expected_errors = {
            "by-value": "AU3001: service functions require one leading exclusive sealed service reference",
            "const": "AU3001: service functions require one leading exclusive sealed service reference",
            "field": "AU2003: unsupported class field type 'builtin::ConsoleSession'",
            "forged": "AU3001: service forwarding requires a named exclusive service parameter",
            "local": "AU3001: service capability cannot be stored in a local",
            "overload": "AU4001: borrowed-object functions cannot be overloaded",
            "owner": "AU3001: service helper parameters require scalars, enums, copied values or readonly byte spans",
            "owned-class": (
                "AU3001: service helper parameters require scalars, enums, copied values or readonly byte spans"
            ),
            "seven-formals": "AU3001: at most six parameters supported",
            "recursive": "AU3001: invalid typed IR: recursive receiver call cycle",
            "reflect": "AU3001: resource capabilities are unavailable to reflection",
            "reflect-id": "AU3001: resource capabilities are unavailable to reflection",
            "reflect-fields": "AU3001: resource capabilities are unavailable to reflection",
            "region": "AU3001: service helper parameters require scalars, enums, copied values or readonly byte spans",
            "return": "AU2001: only scalar function results or scalar-field class values are supported",
            "scalar-cycle": "AU3001: invalid typed IR: recursive receiver call cycle",
            "second": borrowed_parameter_error,
            "shadow": "AU2001: reserved builtin storage name",
            "suspended": "AU3001: service operation requires an active named exclusive service parameter",
            "template": borrowed_parameter_error,
            "two": borrowed_parameter_error,
            "unknown-op": "AU3001: unknown operation for sealed service kind",
            "value": "AU3001: service capability is not a value",
            "wrong-put": "AU3001: expected u8, got i64",
            "owner-result": (
                "AU3001: service functions require a leading exclusive sealed service group and copied result"
            ),
            "span-result": "AU2001: only scalar function results or scalar-field class values are supported",
            "reference-result": "expected '{'",
            "copied-result-incomplete": "AU3001: function must return on every path",
            "copied-result-suspended": "AU3001: service operation requires an active named exclusive service parameter",
            "copied-input-suspended": "AU3001: service operation requires an active named exclusive service parameter",
        }
        for name, body in negative.items():
            source = work / f"{name}.au"
            source.write_text("module rejected;\n" + body + "\n")
            output = work / "preserved.s"
            output.write_bytes(b"previous output\x00\xff")
            result = run([compiler, source, "-o", output])
            require(
                result.returncode == 1 and expected_errors[name].encode() in result.stderr,
                f"{name}: unexpected status or diagnostic: {result.stderr.decode(errors='replace')}",
            )
            require(output.read_bytes() == b"previous output\x00\xff", f"{name}: damaged prior output")
        print(
            "PASS console service: generated editor, exhaustive rejected bytes, "
            f"{len(normal.stdout)} timeout prefixes, "
            f"RAM-note lifetime/replacement/rejection and {len(note_normal.stdout)} note timeout prefixes, "
            "byte-span comparisons, four-file policy/records/lifetime/rejections and "
            f"{len(file_normal.stdout)} file timeout prefixes, "
            "canonical host reports, copied service inputs/results/WriteResult prefixes and "
            f"{len(negative)} source rejections; "
            f"evidence {work}"
        )


if __name__ == "__main__":
    main()
