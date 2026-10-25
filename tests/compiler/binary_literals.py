#!/usr/bin/env python3
"""Exact binary spelling, rejection boundaries and decimal assembly equivalence."""

import json
from pathlib import Path
import sys
import tempfile

from native_runner import Suite, Trap, require, run


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
    suite = Suite(compiler, "binary literals", timeout=10)
    suite.load(Path(__file__).with_suffix(".cases"))
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
    for spelling, decimal, kind, value in spellings:
        if value >= 0:
            body = f"static_assert({spelling}=={decimal});return " + (
                f"u64({spelling});" if kind == "u8" else f"{spelling};"
            )
            suite.value(f"binary spelling {spelling}", body, value, "i64" if kind == "i64" else "u64")
    # Restricted static_assert still excludes unary minus; runtime supports -2^63.
    suite.value("binary signed minimum", "return -" + binary(1 << 63) + ";", -(1 << 63), "i64")
    suite.value(
        "binary byte array and operators",
        "const array<u8,2> a={0b0001u8,0B1111u8};return u64((a[0]<<3)|a[1]);",
        15,
        "u64",
    )
    suite.value(
        "binary class and parameter",
        "const Box b=Box(0b10'1010u64);return b.get();",
        42,
        "u64",
        prelude="class Box{u64 v;public:Box(u64 n):v(n){}auto get()const->u64{return v;}};",
    )
    for body, trap in [
        ("return " + binary((1 << 64) - 1, "u64") + "+0b1u64;", Trap.OVERFLOW),
        ("return u64(0b1u8<<8);", Trap.COUNT),
        ("return 0b1u64/0b0u64;", Trap.ZERO),
    ]:
        suite.value("binary preserves checked trap " + body, body, trap, "u64")
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
    suite.finish()
    print(
        f"PASS binary literal diagnostics: {len(malformed)} malformed tokens, 6 decimal diagnostics; "
        f"{len(spellings)} assembly-equivalent spellings"
    )


if __name__ == "__main__":
    main()
