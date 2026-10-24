#!/usr/bin/env python3
"""Execute the actual source-owned one-file policy through the native runner.

Only request/reply assertions live here; there is no native storage mutation
model. These source checks do not establish retained-domain or guest behavior.
"""

import argparse
from pathlib import Path
import shutil
import tempfile

from unsigned_oracle import Case, NativeRunner, Rejection


IMPORTS = ("console.volatile_file",)
ROOT = Path(__file__).resolve().parents[2]
INITIAL = "console::VolatileFile file = console::VolatileFile();\n"
A = bytes((0, 255, 128, 65, 127))
B = bytes((227, 0, 90))


def step(word, reply, variable="file"):
    return f"if ({variable}.request({word}u64) != {reply}u64) {{ return 0u64; }}\n"


def replace(content, variable="file", tag=3):
    source = step(tag | (len(content) << 8), 1, variable)
    for index, byte in enumerate(content):
        source += step(4 | (index << 8) | (byte << 16), 1, variable)
    return source + step(5, 5, variable)


def read(content, variable="file"):
    source = step(1, 1, variable)
    if content is None:
        return source + step(2, 4, variable)
    for index, byte in enumerate(content):
        source += step(2 | (index << 8), 2 | (byte << 8), variable)
    return source + step(2 | (len(content) << 8), 3, variable)


def case(name, body):
    return Case(name, INITIAL + body + "return 42u64;", 42, imports=IMPORTS)


def value_cases():
    yield case(
        "wire tag decoder isolates all 256 tags without validating requests",
        "u64 tag = 0u64; while (tag < 256u64) {"
        "if (console::volatile_file_tag(tag) != tag"
        " || console::volatile_file_tag(18446744073709551360u64 | tag) != tag) { return 0u64; }"
        "tag = tag + 1u64; }",
    )
    yield case("initial missing, repeated missing, present empty", read(None) + read(None) + replace(b"") + read(b""))
    yield case("binary replacement, different non-prefix replacement", replace(A) + read(A) + replace(B) + read(B))
    yield case(
        "one high byte, empty, subsequent binary",
        replace(b"\xff") + read(b"\xff") + replace(b"") + read(b"") + replace(A) + read(A),
    )
    maximum = bytes((index * 73 + 19) & 255 for index in range(49))
    yield case("49 byte replacement and read each use exactly 51 requests", replace(maximum) + read(maximum))
    yield case("shorter replacement does not expose prior suffix", replace(maximum) + replace(B) + read(B))
    # Cover every byte value without a printable/text policy or signed-byte path.
    for start in range(0, 256, 49):
        content = bytes(range(start, min(start + 49, 256)))
        yield case(f"all binary values starting at {start}", replace(content) + read(content))
    yield case(
        "new incarnation is missing, independent surviving source local retains bytes",
        replace(A)
        + "console::VolatileFile restarted = console::VolatileFile();\n"
        + read(None, "restarted")
        + replace(B, "restarted")
        + read(B, "restarted")
        + read(A),
    )


def rejection_cases():
    # Each malformed command is followed by a fresh read of the complete old
    # file, not merely a status assertion. Reserved bits are checked full-width.
    idle_words = (
        0,
        6,
        7,
        255,
        2,
        4,
        5,
        1 | (1 << 8),
        1 | (1 << 63),
        3 | (50 << 8),
        3 | (255 << 8),
        3 | (1 << 16),
        (1 << 64) - 1,
    )
    for word in idle_words:
        yield case(f"idle closed encoding/order {word}", replace(A) + step(word, 6) + read(A))
    read_sequences = (
        ("read skipped initial offset", step(1, 1) + step(2 | (1 << 8), 6)),
        ("read reserved bit", step(1, 1) + step(2 | (1 << 16), 6)),
        ("read maximum offset ceiling", step(1, 1) + step(2 | (50 << 8), 6)),
        ("read duplicate offset", step(1, 1) + step(2, 2) + step(2, 6)),
        ("new read while read is open", step(1, 1) + step(1, 6)),
        ("replacement while read is open", step(1, 1) + step(3, 6)),
        ("commit while read is open", step(1, 1) + step(5, 6)),
    )
    for name, sequence in read_sequences:
        yield case(name + " preserves", replace(A) + sequence + read(A))
    begin = step(3 | (2 << 8), 1)
    first = step(4 | (227 << 16), 1)
    write_sequences = (
        ("commit before all bytes", begin + first + step(5, 6)),
        ("write initial gap", begin + step(4 | (1 << 8), 6)),
        ("write duplicate", begin + first + step(4, 6)),
        ("write reserved high bit", begin + step(4 | (1 << 24), 6)),
        ("write high-bit encoding", begin + step(4 | (1 << 63), 6)),
        ("write offset ceiling", begin + step(4 | (50 << 8), 6)),
        ("write extra after target", step(3, 1) + step(4, 6)),
        ("begin while staging", begin + first + step(3, 6)),
        ("read while staging", begin + first + step(1, 6)),
        ("commit reserved bits", begin + first + step(4 | (1 << 8), 1) + step(5 | (1 << 8), 6)),
    )
    for name, sequence in write_sequences:
        yield case(name + " preserves and clears protocol", replace(A) + sequence + read(A) + replace(B) + read(B))
    yield case("repeated commit rejected after successful publication", replace(A) + step(5, 6) + read(A))
    yield case("repeated read byte rejected after terminal", read(None) + step(2, 6) + read(None))


def cancellation_cases():
    cancel = "if (file.cancel() != 7u64) { return 0u64; }\n"
    for content in (None, b"", A):
        prefix = "" if content is None else replace(content)
        for count in (0, 1, 2):
            staged = step(3 | (2 << 8), 1)
            for index in range(count):
                staged += step(4 | (index << 8) | (255 << 16), 1)
            yield case(
                f"abort before COMMIT keeps {content!r}, staged {count}",
                prefix + staged + cancel + read(content) + replace(B) + read(B),
            )
    yield case(
        "cancel read preserves and resets sequential offset",
        replace(A) + step(1, 1) + step(2, 2) + cancel + read(A),
    )
    yield case("idle and repeated cancellation never removes committed bytes", replace(A) + cancel + cancel + read(A))
    yield case("cancellation after commit cannot roll back publication", replace(A) + cancel + read(A))
    maximum_stage = step(3 | (49 << 8), 1)
    for index in range(49):
        maximum_stage += step(4 | (index << 8) | (255 << 16), 1)
    yield case(
        "abort a completely staged maximum replacement before COMMIT",
        replace(A) + maximum_stage + cancel + read(A) + replace(b"") + read(b""),
    )


def append_cases():
    cancel = "if (file.cancel() != 7u64) { return 0u64; }\n"

    def append(content):
        return replace(content, tag=8)

    yield case("append missing is rejected including empty suffix", step(8, 6) + step(264, 6) + read(None))
    yield case(
        "append text then empty suffix", replace(b"Hello") + append(b", Aurora") + append(b"") + read(b"Hello, Aurora")
    )
    yield case("append to present empty", replace(b"") + append(A) + read(A))
    maximum = bytes(range(49))
    yield case("full binary suffix uses 51 exchanges", replace(b"") + append(maximum) + read(maximum))
    yield case("replacement after append resets prefix", replace(A) + append(B) + replace(b"Z") + read(b"Z"))
    yield case(
        "append exact capacity and empty suffix at capacity",
        replace(maximum[:20]) + append(maximum[20:]) + append(b"") + read(maximum),
    )
    yield case("append overflow preserves whole file", replace(maximum) + step(264, 6) + read(maximum))
    yield case(
        "append overflow does not permit partial capacity", replace(maximum[:48]) + step(520, 6) + read(maximum[:48])
    )
    for word in (8 | (50 << 8), 8 | (1 << 16), 8 | (1 << 63)):
        yield case(f"append invalid begin {word}", replace(A) + step(word, 6) + read(A))
    begin = step(520, 1)
    first = step(4 | (227 << 16), 1)
    for word in (5, 4, 4 | (2 << 8), 4 | (1 << 24), 4 | (1 << 63), 1, 3, 8):
        yield case(
            f"append invalid sequence {word}",
            replace(A) + begin + first + step(word, 6) + read(A) + append(B) + read(A + B),
        )
    for count in (0, 1, 2):
        staged = begin
        for index in range(count):
            staged += step(4 | (index << 8) | (255 << 16), 1)
        yield case(
            f"append abort staged {count}, explicit retry exactly once",
            replace(A) + staged + cancel + read(A) + append(B) + read(A + B),
        )
    yield case("cancel after append cannot roll back", replace(A) + append(B) + cancel + read(A + B))


def privacy_cases():
    for field in ("committed[0]", "staging[0]", "length", "prefix", "target", "next", "mode"):
        yield Rejection(
            f"private file storage {field}",
            "module private_file; import console.volatile_file; auto test() -> u64 {"
            + INITIAL
            + f"return u64(file.{field});"
            + "}",
        )
    yield Rejection(
        "readonly file cannot mutate protocol",
        "module readonly_file; import console.volatile_file; auto test() -> u64 {"
        "const console::VolatileFile file = console::VolatileFile(); return file.request(1u64); }",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("compiler", type=Path)
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    cases = list(value_cases()) + list(rejection_cases()) + list(cancellation_cases()) + list(append_cases())
    rejections = list(privacy_cases())
    work = Path(tempfile.mkdtemp(prefix="volatile-file-"))
    print(f"artifacts={work}", flush=True)
    runner = NativeRunner(work, compiler, 10)
    runner.cases(cases)
    for rejection in rejections:
        runner.rejection(rejection)
    print(f"PASS volatile file: {len(cases)} generated-code cases, {len(rejections)} source rejections", flush=True)
    shutil.rmtree(work)


if __name__ == "__main__":
    main()
