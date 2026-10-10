#!/usr/bin/env python3
"""Complete bounded service source/editor/canonical-report gate. No guest claim."""

import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def require(value, message):
    if not value:
        raise RuntimeError(message)


def run(command, **kwargs):
    return subprocess.run(list(map(str, command)), cwd=ROOT, capture_output=True, timeout=120, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("compiler", type=Path)
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    (ROOT / "build").mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="console-service-", dir=ROOT / "build"))
    assembly = work / "console.s"
    result = run(
        [compiler, "--module-root", ROOT / "library", ROOT / "examples/kernel-console-service.au", "-o", assembly]
    )
    require(result.returncode == 0, result.stderr.decode())
    text = assembly.read_text()
    require("__au_runtime_bytes_" not in text, "service graph unexpectedly requires owning-byte runtime")
    require(".local aurora_kernel_value" in text, "service graph contains an ordinary public root")
    binary = work / "editor"
    combined = work / "console-bridge.s"
    combined.write_text(text + (ROOT / "kernel/uefi/console-service-entry.S").read_text())
    result = run(
        [
            os.environ.get("CXX", "g++"),
            "-std=c++23",
            "-O1",
            "-Wall",
            "-Wextra",
            "-Werror",
            ROOT / "tests/compiler/console_service_host.cpp",
            ROOT / "tests/compiler/console_service_abi.S",
            combined,
            "-o",
            binary,
        ]
    )
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
        require(result.returncode == 0 and result.stdout.count(b"Line rejected:") == 2, "damage delimiter propagation")
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
        require(result.returncode == 0 and readback(b"saved") in result.stdout, f"bad write mutated note: {value!r}")
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
    file_written = b"files: RAM-only; lost when session exits.\r\n"

    def file_read(name, content):
        return b"cat " + name + b"\r\n" + content + b"\r\naurora> "

    script = b"write a first\nwrite b second\nwrite c third\nwrite d fourth\nwrite e fifth\n"
    script += b"write a x\ncat a\nrm b\nwrite e \nls\ncat e\nrm absent\ncat absent\nrm note\nexit\n"
    result = execute(samples(script))
    require(result.returncode == 0 and result.stdout.count(file_written) == 6, "four-file write/replacement count")
    for expected in (
        b"files: full (4 files).\r\n",
        b"files: a e c d\r\n",
        b"files: note is reserved.\r\n",
        file_read(b"a", b"x"),
        file_read(b"e", b""),
    ):
        require(expected in result.stdout, "named-file capacity, slot reuse or exact readback")
    require(result.stdout.count(b"files: not found (RAM-only).\r\n") == 2, "missing cat/rm outcomes")
    for name in (b"x", b"abcdefgh", b"A._-09z", b"notes", b"Note"):
        for content in (b"", b"x", b" " * 49, b"!" * 49, b"space and suffix "):
            result = execute(samples(b"write " + name + b" " + content + b"\ncat " + name + b"\nexit\n"))
            require(result.returncode == 0 and file_read(name, content) in result.stdout, "name/content boundary")
    bad_files = (
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
        require(result.returncode == 0 and file_read(b"a", b"saved") in result.stdout, "bad file command mutated state")
        require(
            result.stdout.count(file_written) == 1 and b"files: a\r\n" in result.stdout, "failed command created file"
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
            result.returncode == 0 and file_read(b"a", b"saved") in result.stdout, "damaged file command mutated state"
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
    policy_assembly, policy_host, policy_binary = (work / ("note-policy" + suffix) for suffix in (".s", ".cpp", ""))
    policy_host.write_text('extern "C" long note_contract();\nint main() { return int(note_contract()); }\n')
    result = run([compiler, "--module-root", ROOT / "library", policy, "-o", policy_assembly])
    require(result.returncode == 0, result.stderr.decode())
    result = run([os.environ.get("CXX", "g++"), policy_host, policy_assembly, "-o", policy_binary])
    require(result.returncode == 0, result.stderr.decode())
    result = run([policy_binary])
    require(result.returncode == 0, "shared note policy count/content/copy/suffix contract")
    # Existing hosted policy fixture also observes complete private copied records.
    files_source = work / "files-policy.au"
    files_source.write_text("""module files_policy;
import console.session_files;
import std.binary_buffer;
import std.binary;
auto pack(builtin::span<const u8> text) -> std::BinaryBuffer64 {
    std::BinaryBuffer64 command = std::BinaryBuffer64();
    i64 index = 0;
    while (index < text.size()) { command.write_u8(index, text.at(index)); index = index + 1; }
    return command;
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
    if (first.status() != console::FileEvent::written) { return 2; }
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
    return files;
}
""")
    files_assembly, files_host, files_binary = (work / ("files-policy" + suffix) for suffix in (".s", ".cpp", ""))
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
    files_host.write_text("""#include <array>
#include <cstdint>
extern "C" long files_contract();
extern "C" void checked_files_snapshot(long, void*);
int main() {
    if (const auto result = files_contract()) return int(result);
    for (long stage = 0; stage != 5; ++stage) {
        std::array<unsigned char, 280> storage{};
        storage.fill(0xa5);
        checked_files_snapshot(stage, storage.data() + 8);
        std::array<unsigned char, 264> expected{};
        if (stage > 0 && stage < 4) {
            expected[0] = 8;
            expected[1] = stage == 1 ? 49 : stage == 2 ? 1 : 0;
            for (unsigned i = 0; i != 8; ++i) expected[2 + i] = "abcdefgh"[i];
            for (unsigned i = 0; i != expected[1]; ++i) expected[10 + i] = stage == 1 ? 'x' : 'y';
            expected[256] = 1;
        }
        for (unsigned i = 0; i != storage.size(); ++i) {
            if (storage[i] != (i < 8 || i >= 272 ? 0xa5 : expected[i - 8])) return 10 + int(stage);
        }
    }
}
""")
    result = run([os.environ.get("CXX", "g++"), "-std=c++23", files_host, files_assembly, "-o", files_binary])
    require(result.returncode == 0, result.stderr.decode())
    result = run([files_binary])
    require(result.returncode == 0, f"shared files policy count/content/copy/zero-suffix contract: {result.returncode}")
    # Separate positive ABI graph: a copied report crosses two service calls,
    # five mixed value/span positions follow the capability, and a host put runs
    # with an odd outstanding scalar-expression depth.
    abi_source = work / "mixed-abi.au"
    abi_source.write_text("""module kernel_console_service;
    enum class Marker { okay, wrong };
    auto number(builtin::ConsolePutResult status) -> i64 {
        if (status == builtin::ConsolePutResult::success) { return 7; }
        return -100;
    }
    auto odd(builtin::ConsoleSession& session) -> i64 {
        return 1 + number(session.put('z'));
    }
    auto leaf(builtin::ConsoleSession& session, u8 a, builtin::span<const u8> text,
              i64 b, bool flag, Marker marker) -> builtin::ConsoleSample {
        const builtin::ConsoleSample report = session.next();
        if (a != 'A' || text.size() != 3 || text.at(1) != 'y' || b != 41 || !flag || marker != Marker::okay) {
            session.put('!');
        }
        return report;
    }
    auto forward(builtin::ConsoleSession& session, u8 a, builtin::span<const u8> text,
                 i64 b, bool flag, Marker marker) -> builtin::ConsoleSample {
        const builtin::ConsoleSample report = leaf(session, a, text, b, flag, marker);
        return report;
    }
    auto console_service(builtin::ConsoleSession& session) -> builtin::ConsoleCompletion {
        array<u8, 3> text = {'x', 'y', 'z'};
        const builtin::ConsoleSample report = forward(session, 'A', borrow_bytes(text), 41, true, Marker::okay);
        if (!report.byte_present || report.byte != 'Q' || report.damaged || odd(session) != 8) {
            session.put('?');
        }
        return builtin::ConsoleCompletion::requested_exit;
    }
    auto aurora_kernel_value() -> i64 { return 42; }
    """)
    abi_assembly = work / "mixed-abi.s"
    result = run([compiler, abi_source, "-o", abi_assembly])
    require(result.returncode == 0, result.stderr.decode())
    abi_assembly.write_text(abi_assembly.read_text() + (ROOT / "kernel/uefi/console-service-entry.S").read_text())
    abi_binary = work / "mixed-abi"
    result = run(
        [
            os.environ.get("CXX", "g++"),
            "-std=c++23",
            "-O1",
            "-Wall",
            "-Wextra",
            "-Werror",
            ROOT / "tests/compiler/console_service_host.cpp",
            ROOT / "tests/compiler/console_service_abi.S",
            abi_assembly,
            "-o",
            abi_binary,
        ]
    )
    require(result.returncode == 0, result.stderr.decode())
    result = run([abi_binary], input=b"1 81 0\n")
    require(result.returncode == 0 and result.stdout == b"z", "mixed service ABI/report/odd-depth failure")
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
    }
    """)
    imported = work / "imported.au"
    imported.write_text("""module kernel_console_service;
    import service.helpers;
    auto console_service(builtin::ConsoleSession& session) -> builtin::ConsoleCompletion {
        const builtin::ConsoleSample actual = service_test::fetch(session);
        const service_test::Holder saved = service_test::Holder(actual, builtin::ConsolePutResult::success);
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
    result = run([compiler, "--module-root", modules, imported, "-o", imported_assembly])
    require(result.returncode == 0, result.stderr.decode())
    imported_assembly.write_text(
        imported_assembly.read_text() + (ROOT / "kernel/uefi/console-service-entry.S").read_text()
    )
    imported_binary = work / "imported"
    result = run(
        [
            os.environ.get("CXX", "g++"),
            "-std=c++23",
            "-O1",
            "-Wall",
            "-Wextra",
            "-Werror",
            ROOT / "tests/compiler/console_service_host.cpp",
            ROOT / "tests/compiler/console_service_abi.S",
            imported_assembly,
            "-o",
            imported_binary,
        ]
    )
    require(result.returncode == 0, result.stderr.decode())
    result = run([imported_binary], input=b"1 81 1\n")
    require(result.returncode == 0 and result.stdout == b"K", "cross-module copied-report/reflection inconsistency")
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
        "region": "auto f(builtin::ConsoleSession& s, builtin::ByteRegion r) -> i64 { return 0; }",
        "owner": "auto f(builtin::ConsoleSession& s, builtin::OwnedBytes b) -> i64 { return 0; }",
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
    }
    expected_errors = {
        "by-value": "AU3001: service functions require one leading exclusive sealed service reference",
        "const": "AU3001: service functions require one leading exclusive sealed service reference",
        "field": "AU2003: unsupported class field type 'builtin::ConsoleSession'",
        "forged": "AU3001: service forwarding requires a named exclusive service parameter",
        "local": "AU3001: service capability cannot be stored in a local",
        "overload": "AU4001: borrowed-object functions cannot be overloaded",
        "owner": "AU3001: service helper parameters require scalars, enums or readonly byte spans",
        "recursive": "AU3001: invalid typed IR: recursive receiver call cycle",
        "reflect": "AU3001: resource capabilities are unavailable to reflection",
        "reflect-id": "AU3001: resource capabilities are unavailable to reflection",
        "reflect-fields": "AU3001: resource capabilities are unavailable to reflection",
        "region": "AU3001: service helper parameters require scalars, enums or readonly byte spans",
        "return": "AU2001: only scalar function results or scalar-field class values are supported",
        "scalar-cycle": "AU3001: invalid typed IR: recursive receiver call cycle",
        "second": "AU2001: borrowed parameters require one leading concrete owning class",
        "shadow": "AU2001: reserved builtin storage name",
        "suspended": "AU3001: service operation requires an active named exclusive service parameter",
        "template": "AU2001: borrowed parameters require one leading concrete owning class",
        "two": "AU2001: borrowed parameters require one leading concrete owning class",
        "unknown-op": "AU3001: unknown operation for sealed service kind",
        "value": "AU3001: service capability is not a value",
        "wrong-put": "AU3001: expected u8, got i64",
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
        f"PASS console service: generated editor, exhaustive rejected bytes, {len(normal.stdout)} timeout prefixes, "
        f"RAM-note lifetime/replacement/rejection and {len(note_normal.stdout)} note timeout prefixes, "
        f"four-file policy/records/lifetime/rejections and {len(file_normal.stdout)} file timeout prefixes, "
        f"canonical host reports and {len(negative)} source rejections; evidence {work}"
    )


if __name__ == "__main__":
    main()
