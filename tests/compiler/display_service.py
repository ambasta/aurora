#!/usr/bin/env python3
"""Bounded Display source, copied metadata, private ABI and fail-closed result gate."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
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
    with tempfile.TemporaryDirectory(prefix="display-service-") as scratch:
        work = Path(scratch)
        modules = work / "modules"
        (modules / "display").mkdir(parents=True)
        (modules / "display/helpers.au").write_text("""export module display.helpers;
export namespace display_test {
    auto pixel(builtin::DisplaySession& display, u64 x, u64 y, u8 r, u8 g, u8 b)
        -> builtin::DisplayPutResult { return display.pixel(x, y, r, g, b); }
    auto with_span(builtin::DisplaySession& display, builtin::span<const u8> text) -> builtin::DisplayPutResult {
        if (text.size() != 3) { return builtin::DisplayPutResult::out_of_bounds; }
        return pixel(display, 7u64, 9u64, text.at(0), text.at(1), text.at(2));
    }
    auto span_forward(builtin::DisplaySession& display, builtin::span<const u8> text) -> builtin::DisplayPutResult {
        return with_span(display, text);
    }
    auto odd(builtin::DisplaySession& display) -> bool {
        return true == (display.pixel(7u64, 9u64, 11u8, 13u8, 17u8) == builtin::DisplayPutResult::success);
    }
    auto metadata() -> bool {
        return reflect_size(type_id(builtin::DisplayPutResult)) == size_of(builtin::DisplayPutResult) &&
               reflect_size(type_id(builtin::DisplayCompletion)) == 8 &&
               reflect_field_count(type_id(builtin::DisplayPutResult)) == field_count(builtin::DisplayPutResult);
    }
    class Copied {
        builtin::DisplayPutResult value;
    public:
        Copied(builtin::DisplayPutResult result) : value(result) {}
        auto get() const -> builtin::DisplayPutResult { return value; }
    };
}
""")
        source = work / "display.au"
        source.write_text("""module display_test;
import display.helpers;
auto display_service(builtin::DisplaySession& display, u64 width, u64 height) -> builtin::DisplayCompletion {
    array<u8, 3> channels = {11u8, 13u8, 17u8};
    const display_test::Copied copied = display_test::Copied(builtin::DisplayPutResult::out_of_bounds);
    if (width != 19u64 || height != 23u64 || !display_test::metadata() ||
        copied.get() != builtin::DisplayPutResult::out_of_bounds ||
        reflect_size(type_id(builtin::DisplayPutResult)) != 8 ||
        reflect_size(type_id(builtin::DisplayCompletion)) != size_of(builtin::DisplayCompletion)) {
        return builtin::DisplayCompletion::output_failure;
    }
    if (display_test::span_forward(display, borrow_bytes(channels)) != builtin::DisplayPutResult::success ||
        !display_test::odd(display) ||
        display.pixel(width, 0u64, 11u8, 13u8, 17u8) != builtin::DisplayPutResult::out_of_bounds ||
        display.pixel(0u64, height, 11u8, 13u8, 17u8) != builtin::DisplayPutResult::out_of_bounds) {
        return builtin::DisplayCompletion::output_failure;
    }
    return builtin::DisplayCompletion::rendered;
}
auto aurora_kernel_value() -> i64 { return 42; }
""")
        assembly = work / "display.s"
        result = run([compiler, "--module-root", modules, source, "-o", assembly])
        require(result.returncode == 0, result.stderr.decode())
        text = assembly.read_text()
        symbol = "__au_v_m1_12display_test_n0__d15display_service"
        require(".local " + symbol in text, "Display entry must remain private")
        require(
            "__au_runtime_console_" not in text and "__au_runtime_bytes_" not in text,
            "Display graph unexpectedly links another service or owner runtime",
        )
        assembly.write_text(
            text
            + f"""
.text
.globl __au_runtime_display_entry
.hidden __au_runtime_display_entry
.type __au_runtime_display_entry,@function
__au_runtime_display_entry:
    pushq %rbp
    movq %rsp, %rbp
    movq %rdi, %r11
    call {symbol}
    leave
    ret
.size __au_runtime_display_entry,.-__au_runtime_display_entry
"""
        )
        binary = work / "display"
        result = run(
            [
                os.environ.get("CXX", "g++"),
                "-std=c++23",
                "-O1",
                "-Wall",
                "-Wextra",
                "-Werror",
                ROOT / "tests/compiler/display_service_host.cpp",
                ROOT / "tests/compiler/display_service_abi.S",
                assembly,
                "-o",
                binary,
            ]
        )
        require(result.returncode == 0, result.stderr.decode())
        result = run([binary])
        require(result.returncode == 0, "Display ABI/metadata failed: " + result.stderr.decode())
        malformed = run([binary, "malformed"])
        require(malformed.returncode == -4, "noncanonical pixel result did not trap with SIGILL")
        negative = {
            "by-value": "auto f(builtin::DisplaySession s) -> i64 { return 0; }",
            "const": "auto f(const builtin::DisplaySession& s) -> i64 { return 0; }",
            "second": "auto f(i64 n, builtin::DisplaySession& s) -> i64 { return 0; }",
            "two": "auto f(builtin::DisplaySession& s, builtin::DisplaySession& t) -> i64 { return 0; }",
            "local": "auto f(builtin::DisplaySession& s) -> i64 { builtin::DisplaySession t = s; return 0; }",
            "cast": "auto f(builtin::DisplaySession& s) -> i64 { return i64(s); }",
            "reflect": "auto f() -> i64 { return size_of(builtin::DisplaySession); }",
            "reflect-id": "auto f() -> i64 { return type_id(builtin::DisplaySession); }",
            "reflect-fields": "auto f() -> i64 { return field_count(builtin::DisplaySession); }",
            "field": "class C { builtin::DisplaySession s; }; auto f() -> i64 { return 0; }",
            "construct": "auto f() -> i64 { const builtin::DisplaySession s = builtin::DisplaySession{}; return 0; }",
            "return": "auto f(builtin::DisplaySession& s) -> builtin::DisplaySession { return s; }",
            "region": "auto f(builtin::DisplaySession& s, builtin::ByteRegion r) -> i64 { return 0; }",
            "owner": "auto f(builtin::DisplaySession& s, builtin::OwnedBytes b) -> i64 { return 0; }",
            "mutable-span": "auto f(builtin::DisplaySession& s, builtin::span<u8> b) -> i64 { return 0; }",
            "next": (
                "auto f(builtin::DisplaySession& s) -> i64 { const builtin::ConsoleSample v = s.next(); return 0; }"
            ),
            "put": "auto f(builtin::DisplaySession& s) -> i64 { s.put(1u8); return 0; }",
            "console-pixel": "auto f(builtin::ConsoleSession& s) -> i64 { s.pixel(0u64,0u64,1u8,2u8,3u8); return 0; }",
            "wrong-coordinate": "auto f(builtin::DisplaySession& s) -> i64 { s.pixel(0,0u64,1u8,2u8,3u8); return 0; }",
            "wrong-channel": "auto f(builtin::DisplaySession& s) -> i64 { s.pixel(0u64,0u64,1u64,2u8,3u8); return 0; }",
            "wrong-result": (
                "auto f(builtin::DisplaySession& s) -> builtin::ConsolePutResult { "
                "return s.pixel(0u64,0u64,1u8,2u8,3u8); }"
            ),
            "unknown-case": "auto f() -> builtin::DisplayPutResult { return builtin::DisplayPutResult::timeout; }",
            "wrong-forward": (
                "auto g(builtin::ConsoleSession& s) -> i64 { return 0; } auto "
                "f(builtin::DisplaySession& s) -> i64 { return g(s); }"
            ),
            "reverse-forward": (
                "auto g(builtin::DisplaySession& s) -> i64 { return 0; } auto "
                "f(builtin::ConsoleSession& s) -> i64 { return g(s); }"
            ),
            "suspended": (
                "auto g(builtin::DisplaySession& s, builtin::DisplayPutResult r) -> i64 { return 0; } "
                "auto f(builtin::DisplaySession& s) -> i64 { return "
                "g(s,s.pixel(0u64,0u64,1u8,2u8,3u8)); }"
            ),
            "recursive": "auto f(builtin::DisplaySession& s) -> i64 { return f(s); }",
            "shadow": "namespace builtin { class DisplaySession {}; } auto f() -> i64 { return 0; }",
        }
        for symbol in (
            "__au_runtime_display_pixel",
            "__au_runtime_display_entry",
            "__au_runtime_console_next",
            "__au_runtime_console_put",
        ):
            negative[symbol + "-define"] = f"auto {symbol}() -> i64 {{ return 0; }}"
            negative[symbol + "-call"] = f"auto f() -> i64 {{ return {symbol}(); }}"
        for name, body in negative.items():
            source.write_text("module rejected; " + body)
            result = run([compiler, source, "-o", work / "rejected.s"])
            require(result.returncode != 0 and result.stderr, "invalid Display source accepted: " + name)
        grouped = run(
            [
                sys.executable,
                "-B",
                "-O",
                ROOT / "tests/compiler/service_group.py",
                compiler,
                "--artifacts",
                work / "service-group",
            ]
        )
        require(grouped.returncode == 0, grouped.stdout.decode() + grouped.stderr.decode())
        print(grouped.stdout.decode(), end="")
        print(
            "PASS Display source: ABI, cross-module copied metadata, canonical result, "
            f"{len(negative)} negative cases; {work}"
        )


if __name__ == "__main__":
    main()
