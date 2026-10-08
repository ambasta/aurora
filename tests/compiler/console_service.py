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
    result = run([compiler, ROOT / "examples/kernel-console-service.au", "-o", assembly])
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

    def execute(samples, limit=2**64 - 1, malformed=0):
        data = "".join(f"{present} {byte} {damage}\n" for present, byte, damage in samples).encode()
        return run([binary, limit, malformed], input=data)

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
    for position in range(len(normal.stdout)):
        result = execute(samples(b"help\r\nstatus\nexit\n"), position)
        require(
            result.returncode == 1 and result.stdout == normal.stdout[:position],
            f"output timeout retried, ignored or changed prefix at {position}",
        )
    for malformed in range(1, 6):
        result = execute(samples(b"exit\n"), malformed=malformed)
        require(result.returncode < 0, f"noncanonical report {malformed} accepted")
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
        f"canonical host reports and {len(negative)} source rejections; evidence {work}"
    )


if __name__ == "__main__":
    main()
