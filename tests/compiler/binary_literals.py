#!/usr/bin/env python3
"""Exact binary spelling, rejection boundaries and decimal assembly equivalence."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from unsigned_oracle import Case, NativeRunner, Trap, command, require


def binary(value, suffix="", group=5, prefix="0b"):
    digits = f"{value:b}"
    first = len(digits) % group or group
    return (
        prefix
        + digits[:first]
        + "".join("'" + digits[i : i + group] for i in range(first, len(digits), group))
        + suffix
    )


def main():
    compiler = Path(sys.argv[1]).resolve(strict=True)
    print(f"compiler_sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()}", flush=True)
    # Independent Python values cover all byte payloads and every u64 bit position.
    spellings = [(binary(value, "u8", 4), f"{value}u8", "u8", value) for value in range(256)]
    for value in sorted({0, 42, (1 << 64) - 1} | {1 << bit for bit in range(64)}):
        spellings.append((binary(value, "u64"), f"{value}u64", "u64", value))
    for value in (0, 1, 42, (1 << 63) - 1):
        spellings.append((binary(value, prefix="0B"), str(value), "i64", value))
    spellings += [
        ("-" + binary(1 << 63), str(-(1 << 63)), "i64", -(1 << 63)),
        ("0b0000'0000'1010u64", "10u64", "u64", 10),
        ("0B11111111u8", "255u8", "u8", 255),
        ("0b" + "0" * 128 + "1", "1", "i64", 1),
    ]
    cases = [
        Case(
            f"binary spelling {spelling}",
            f"static_assert({spelling}=={decimal});return " + (f"u64({spelling});" if kind == "u8" else f"{spelling};"),
            value,
            result_type="i64" if kind == "i64" else "u64",
        )
        for spelling, decimal, kind, value in spellings
        if value >= 0
    ]
    # Restricted static_assert still excludes unary minus; runtime supports -2^63.
    cases += [
        Case("binary signed minimum", "return -" + binary(1 << 63) + ";", -(1 << 63), result_type="i64"),
        Case(
            "binary byte array and operators", "const array<u8,2> a={0b0001u8,0B1111u8};return u64((a[0]<<3)|a[1]);", 15
        ),
        Case(
            "binary class and parameter",
            "const Box b=Box(0b10'1010u64);return b.get();",
            42,
            prelude="class Box{u64 v;public:Box(u64 n):v(n){}auto get()const->u64{return v;}};",
        ),
    ]
    malformed = [
        "0b",
        "0B",
        "0bu8",
        "0Bu64",
        "0b2",
        "0b102u64",
        "0b12u8",
        "0b'1u64",
        "0b1''0u64",
        "0b1'",
        "0b1'u64",
        "0b1u64'0",
        "0b1_0",
        "0b1ul",
        "0b1u",
        "0b1u8x",
        "0b1u64u8",
        "0b1i64",
        "0b1U64",
        "0b1'a'",
        "0b1" + "0" * 64 + "u64",
        binary(256, "u8"),
        binary(1 << 63),
        "0b1111'1111'1111'1111'1111'1111'1111'1111'1111'1111'1111'1111'1111'1111'1111'1111'1u64",
    ]
    with tempfile.TemporaryDirectory(prefix="aurora-binary-literals-") as temporary:
        root = Path(temporary)
        runner = NativeRunner(root, compiler, 10)
        for offset in range(0, len(cases) - 1, 32):
            runner.cases(cases[offset : min(offset + 32, len(cases) - 1)])
        runner.cases([cases[-1]])
        for body, trap in [
            ("return " + binary((1 << 64) - 1, "u64") + "+0b1u64;", Trap.OVERFLOW),
            ("return u64(0b1u8<<8);", Trap.COUNT),
            ("return 0b1u64/0b0u64;", Trap.ZERO),
        ]:
            runner.cases([Case("binary preserves checked trap", body, trap)])
        source, output = root / "literal.au", root / "literal.s"
        prefix = "module test;\r\n\tauto value()->u64{return "
        for spelling in malformed:
            text = prefix + spelling + ";}"
            source.write_text(text)
            result = subprocess.run(
                [compiler, "--check", "--diagnostics=json", source], capture_output=True, timeout=10
            )
            require(result.returncode == 1 and not result.stderr, f"invalid binary accepted: {spelling}")
            diagnostic = json.loads(result.stdout)["diagnostics"][0]
            require(
                diagnostic["code"] == "AU3001" and "integer literal" in diagnostic["message"],
                f"binary rejection changed: {diagnostic}",
            )
            require(
                diagnostic["range"]["start"]["offset"] == len(prefix)
                and diagnostic["range"]["end"]["offset"] == len(prefix) + len(spelling),
                f"binary diagnostic is not the complete token: {diagnostic}",
            )
            for sentinel in (None, b"preserve existing output\n"):
                output.unlink(missing_ok=True)
                if sentinel is not None:
                    output.write_bytes(sentinel)
                rejected = subprocess.run([compiler, source, "-o", output], capture_output=True, timeout=10)
                require(rejected.returncode == 1, "malformed literal emitted assembly")
                require(
                    not output.exists() if sentinel is None else output.read_bytes() == sentinel,
                    "malformed literal changed assembly",
                )
        decimal_prefix = "module test;auto value()->i64{return "
        for spelling, token, message in [
            ("-1foo", "1foo", "integer literal out of range or invalid suffix"),
            ("-1_0", "1_0", "integer literal out of range or invalid suffix"),
            ("-9223372036854775808abc", "9223372036854775808abc", "integer literal out of range or invalid suffix"),
            ("-9223372036854775809", "9223372036854775809", "integer literal out of range or invalid suffix"),
            ("-18446744073709551616", "-", "integer literal out of range"),
            ("18446744073709551616", "18446744073709551616", "integer literal out of range or invalid suffix"),
        ]:
            source.write_text(decimal_prefix + spelling + ";}")
            rejected = subprocess.run(
                [compiler, "--check", "--diagnostics=json", source], capture_output=True, timeout=10
            )
            require(rejected.returncode == 1 and not rejected.stderr, "malformed decimal accepted")
            diagnostic = json.loads(rejected.stdout)["diagnostics"][0]
            start = len(decimal_prefix) + spelling.index(token)
            require(
                diagnostic["code"] == "AU3001"
                and diagnostic["message"] == message
                and diagnostic["range"]["start"]["offset"] == start
                and diagnostic["range"]["end"]["offset"] == start + len(token),
                f"decimal diagnostic changed: {spelling}: {diagnostic}",
            )
        rejections = [
            ("return -" + binary((1 << 63) + 1) + ";", "i64", "integer literal", ""),
            ("return -0b1u64;", "u64", "expected", ""),
            ("return -0b1u8;", "u8", "expected", ""),
            ("return 0b1;", "u64", "expected", ""),
            ("return 0b1u8;", "i64", "expected", ""),
            ("return 0b1u64+1;", "u64", "expected", ""),
            ("return 0b1u64<<0b1u64;", "u64", "expected", ""),
            ("return 0x10u64;", "u64", "integer literal", ""),
            ("return 1_0u64;", "u64", "integer literal", ""),
            ("return 1'0u64;", "u64", "invalid byte literal", ""),
        ]
        # Capacities retain their explicit decimal-only grammar, including prefixes
        # that an unchecked decimal parser could incorrectly accept as zero.
        for capacity in ("0b10", "0B1'0", "0b10u64"):
            rejections += [
                (f"const array<u64,{capacity}> a={{0u64,1u64}};return a[0];", "u64", "decimal integer literal", ""),
                (
                    f"const std::array<u64,{capacity}> a=std::array<u64,{capacity}>();return a.at(0);",
                    "u64",
                    "decimal literals",
                    "import std.array;",
                ),
            ]
        for body, kind, message, imports in rejections:
            source.write_text(f"module test;{imports}auto value()->{kind}{{{body}}}")
            rejected = subprocess.run(
                [compiler, "--check", "--module-root", Path(__file__).resolve().parents[2] / "library", source],
                capture_output=True,
                timeout=10,
            )
            require(
                rejected.returncode == 1 and message.encode() in rejected.stderr,
                f"literal boundary accepted or changed: {body}: {rejected.stderr!r}",
            )

        def assembly(binary_spelling):
            source.write_text(
                "module test;\n"
                + "\n".join(
                    f"auto value_{index}()->{kind}{{return {spelling if binary_spelling else decimal};}}"
                    for index, (spelling, decimal, kind, _) in enumerate(spellings)
                )
            )
            command([compiler, source, "-o", output], timeout=10)
            return output.read_bytes()

        require(assembly(True) == assembly(False), "binary spellings changed decimal-equivalent assembly")
    print(
        f"PASS binary literals: {len(cases)} native values, 3 checked traps, {len(malformed)} malformed and "
        f"{len(rejections)} boundary rejections, 6 decimal diagnostics; {len(spellings)} assembly-equivalent spellings"
    )


if __name__ == "__main__":
    main()
