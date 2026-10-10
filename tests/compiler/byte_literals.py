#!/usr/bin/env python3
"""Exact-u8 character spelling, native boundaries, diagnostics and numeric equivalence."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from unsigned_oracle import Case, NativeRunner, Trap, command, require


def app(body, result="u8"):
    return f"module test;auto test()->{result}{{{body}}}"


def byte_string_length_diagnostics(compiler, root):
    source, output = root / "string-length.au", root / "string-length.s"
    # Independent decoded counts distinguish bytes from spelling length,
    # Unicode characters and an imagined terminator.
    for spelling, actual, expected in [
        ('""', 0, 1),
        ('"a"', 1, 2),
        ('"hello"', 5, 4),
        ('"é"', 2, 1),
        ('"😀"', 4, 1),
        (r'"\x4142\01"', 5, 4),
        (r'"\0"', 1, 2),
        (r'"\x00\xff"', 2, 1),
    ]:
        prefix = f"module test;auto test()->u8{{const array<u8,{expected}> b="
        source.write_text(prefix + spelling + ";return b[0];}")
        message = (
            f"array initializer length does not match its declared type: expected {expected} bytes, "
            f"got {actual} decoded bytes"
        )
        output.write_bytes(b"preserved\n")
        result = subprocess.run([compiler, source, "-o", output], capture_output=True, text=True, timeout=10)
        require(
            result.returncode == 1 and message in result.stderr and output.read_bytes() == b"preserved\n",
            f"string length diagnostic or failed output preservation: {spelling!r}: {result.stderr}",
        )
        result = subprocess.run(
            [compiler, "--check", "--diagnostics=json", source], capture_output=True, text=True, timeout=10
        )
        require(result.returncode == 1, f"string length mismatch passed check: {spelling!r}")
        diagnostics = json.loads(result.stdout)["diagnostics"]
        require(len(diagnostics) == 1, f"string length diagnostic count: {diagnostics}")
        diagnostic = diagnostics[0]
        require(
            diagnostic["code"] == "AU3001"
            and diagnostic["message"] == message
            and diagnostic["range"]["start"]["offset"] == len(prefix.encode())
            and diagnostic["range"]["end"]["offset"] == len((prefix + spelling).encode()),
            f"string length diagnostic or source span: {diagnostic}",
        )
    print("PASS byte-string length diagnostics: 8 decoded byte counts, spans and preserved outputs")


def byte_strings(compiler, root, runner):
    # Strings reuse named array storage and the existing native value/trap oracle.
    spellings = [
        ('"IOMMU "', b"IOMMU "),
        (r'"\0\a\b\f\n\r\t\v\\\'\""', bytes([0, 7, 8, 12, 10, 13, 9, 11, 92, 39, 34])),
        ('"é中😀"', "é中😀".encode()),
        ('"' + "".join(f"\\x{value:02x}" for value in range(256)) + '"', bytes(range(256))),
        (r'"\x4142\01"', b"A42\x001"),  # Exactly two hex digits; zero is not octal.
        ('"' + "a" * 4096 + '"', b"a" * 4096),
    ]
    cases = []
    source, output = root / "string.au", root / "string.s"
    for spelling, expected in spellings:
        if len(expected) <= 256:
            body = f"const array<u8,{len(expected)}> b={spelling};"
            body += "const builtin::span<const u8> view=borrow_bytes(b);"
            body += f"if(view.size()!={len(expected)}){{return 1u64;}}"
            body += "".join(f"if(view.at({i})!={value}u8){{return 2u64;}}" for i, value in enumerate(expected))
            cases.append(Case("byte-string contents and exact borrowed extent", body + "return 0u64;", 0))

        # No hidden terminator, alternate storage, lifetime or backend operation.
        def assembly(initializer):
            source.write_text(app(f"const array<u8,{len(expected)}> b={initializer};return b[{len(expected) - 1}];"))
            command([compiler, source, "-o", output])
            return output.read_bytes()

        require(
            assembly(spelling) == assembly("{" + ",".join(f"{value}u8" for value in expected) + "}"),
            "string initializer changed assembly relative to explicit byte array",
        )
    runner.cases(cases)
    # The capacity boundary is compiled and executed without inflating source depth.
    runner.cases(
        [
            Case(
                "maximum string array",
                'array<u8,4096> b="' + "a" * 4096 + '";'
                "b[4095]='z';const array<u8,4096> copy=b;"
                "const builtin::span<const u8> view=borrow_bytes(copy);"
                "return u64(view.at(4095))+u64(view.size());",
                4218,
            )
        ]
    )
    byte_string_length_diagnostics(compiler, root)
    malformed = [
        b'"unclosed',
        b'"\\',
        b'"\\q"',
        b'"\\x"',
        b'"\\x0"',
        b'"\\xGG"',
        b'"\\u0041"',
        b'"\\U00000041"',
        b'"\\101"',
        b'"a"u8',
        b'"a"_suffix',
        b'"a"0',
        b'"\\\n"',
        b'"\\\r"',
        b'"' + b"a" * 4097 + b'"',
    ]
    malformed += [b'"' + bytes([value]) + b'"' for value in list(range(32)) + [127, 128, 191, 192, 193, 245, 255]]
    malformed += [
        b'"' + value + b'"'
        for value in [
            b"\xc2",
            b"\xc2A",
            b"\xe0\x80\x80",
            b"\xed\xa0\x80",
            b"\xf0\x80\x80\x80",
            b"\xf4\x90\x80\x80",
            b"\xe2\x82",
            b"\xf0\x90\x80",
        ]
    ]
    prefix = b"module test;\r\n\tauto test()->u8{const array<u8,1> b="
    for spelling in malformed:
        source.write_bytes(prefix + spelling + b";return b[0];}")
        output.write_bytes(b"preserved\n")
        result = subprocess.run([compiler, source, "-o", output], capture_output=True, timeout=10)
        require(
            result.returncode == 1 and output.read_bytes() == b"preserved\n",
            f"malformed string changed output: {spelling!r}",
        )
        result = subprocess.run([compiler, "--check", "--diagnostics=json", source], capture_output=True, timeout=10)
        require(result.returncode == 1, f"malformed string passed check: {spelling!r}")
        diagnostic = json.loads(result.stdout)["diagnostics"][0]
        require(
            diagnostic["code"] == "AU1003" and diagnostic["range"]["start"]["offset"] == len(prefix),
            f"string diagnostic or source span: {diagnostic}",
        )
    rejected = [
        'const array<u8,1> b="";return 0u8;',
        'const array<u8,2> b="a";return 0u8;',
        'const array<u8,1> b="ab";return 0u8;',
        'const array<u8,1> b="é";return 0u8;',
        'const array<i64,1> b="a";return 0u8;',
        'const array<u64,1> b="a";return 0u8;',
        'const array<bool,1> b="a";return 0u8;',
        'const u8 b="a";return b;',
        'return "a";',
        'const builtin::span<const u8> v=borrow_bytes("a");return 0u8;',
        'const builtin::span<const u8> v="a";return 0u8;',
        "array<u8,1> b=\"a\";const builtin::span<const u8> v=borrow_bytes(b);b[0]='b';return v.at(0);",
        'array<u8,1> b="a";b="b";return b[0];',
        'const array<u8,2> b="a" "b";return b[0];',
        'const array<u8,0> b="";return 0u8;',
        'const array<u8,4097> b="a";return 0u8;',
    ]
    for body in rejected:
        source.write_text(app(body))
        result = subprocess.run([compiler, "--check", source], capture_output=True, timeout=10)
        require(result.returncode == 1, f"string type/length/lifetime restriction accepted: {body}")
    source.write_text(
        "module test;class Box{builtin::OwnedBytes payload;public:"
        "Box(builtin::ByteRegion region,builtin::OwnedBytes initial):payload(move(initial)){}"
        "auto view()const->builtin::span<const u8>{"
        'const array<u8,1> b="a";return borrow_bytes(b);}};auto test()->u8{return 0u8;}'
    )
    result = subprocess.run([compiler, "--check", source], capture_output=True, timeout=10)
    require(
        result.returncode == 1 and b"returned span must derive directly" in result.stderr,
        "string-backed local array escaped through returned view",
    )
    for program, diagnostic in [
        (
            'module test;auto take(u8 value)->u8{return value;}auto test()->u8{return take("a");}',
            b"byte-string literals require a typed local u8 array initializer",
        ),
        (
            'module test;class Box{array<u8,1> data;public:Box():data("a"){} };auto test()->u8{return 0u8;}',
            b"array fields require explicit empty-brace zero initialization",
        ),
    ]:
        source.write_text(program)
        result = subprocess.run([compiler, "--check", source], capture_output=True, timeout=10)
        require(result.returncode == 1 and diagnostic in result.stderr, "string escaped its local initializer context")
    print(
        f"PASS byte-string arrays: 6 native values, {len(malformed)} lexical and "
        f"{len(rejected) + 3} length/type/lifetime rejections, 6 exact assembly comparisons"
    )


def main():
    compiler = Path(sys.argv[1]).resolve(strict=True)
    print(f"compiler_sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()}", flush=True)
    spellings = [(f"'\\x{value:02X}'", value) for value in range(256)]
    spellings += [("'" + chr(value) + "'", value) for value in range(32, 127) if value not in (39, 92)]
    spellings += [
        ("'\\" + escape + "'", value)
        for escape, value in [
            ("'", 39),
            ("\\", 92),
            ("0", 0),
            ("a", 7),
            ("b", 8),
            ("f", 12),
            ("n", 10),
            ("r", 13),
            ("t", 9),
            ("v", 11),
        ]
    ]
    spellings += [("'\\xff'", 255), ("'\\xAb'", 171)]
    cases = [
        Case(f"byte spelling {spelling}", f"static_assert({spelling}=={value}u8);return u64({spelling});", value)
        for spelling, value in spellings
    ]
    cases += [
        Case("byte operations", r"return u64((~'\0' & '\x0f') + '\x01');", 16),
        Case("signed widening", "return i64('[');", 91, result_type="i64"),
        Case("literal shift", r"return u64('\x01' << 7);", 128),
        Case("literal array", r"const array<u8,3> b={'[','\0','\xff'};return u64(b[2]);", 255),
        Case(
            "literal parameter and direct copied return",
            "const Box b=make('[');return u64(b.get());",
            91,
            prelude="class Box{u8 value;public:Box(u8 v):value(v){}auto get()const->u8{return value;}};"
            "auto make(u8 value)->Box{return Box(value);}",
        ),
    ]
    invalid = [
        "''",
        "'ab'",
        "'''",
        "'a",
        "'\\",
        "'\\q'",
        "'\\x'",
        "'\\x0'",
        "'\\x000'",
        "'\\x100'",
        "'\\xGG'",
        "'\\u0041'",
        "'\\U00000041'",
        "'\\101'",
        "'\\01'",
        "'\\\"'",
        "'é'",
        "'😀'",
        "'\t'",
        "'\0'",
        "'\x7f'",
        "'\n'",
        "'\r'",
        "'\\\n'",
        "'\\\r'",
        "'a'u8",
        "'a'u64",
        "'a'0",
        "'a'_suffix",
    ]
    # Every raw non-ASCII byte is rejected even when not valid UTF-8.
    invalid_bytes = [x.encode() for x in invalid] + [b"'" + bytes([n]) + b"'" for n in range(128, 256)]
    with tempfile.TemporaryDirectory(prefix="aurora-byte-literals-") as temporary:
        root = Path(temporary)
        runner = NativeRunner(root, compiler, 10)
        byte_strings(compiler, root, runner)
        for offset in range(0, len(cases) - 1, 32):
            runner.cases(cases[offset : min(offset + 32, len(cases) - 1)])
        runner.cases([cases[-1]])
        for body, trap in [
            (r"return u64('\xff'+ '\x01');", Trap.OVERFLOW),
            (r"return u64('\0' - '\x01');", Trap.OVERFLOW),
            (r"return u64('a' / '\0');", Trap.ZERO),
            (r"return u64('a' << 8);", Trap.COUNT),
        ]:
            runner.cases([Case("character preserves checked trap", body, trap)])
        path = root / "invalid.au"
        output = root / "preserved.s"
        prefix = b"module test;\r\n\tauto test()->u8{return "
        for spelling in invalid_bytes:
            original = prefix + spelling + b";}"
            path.write_bytes(original)
            result = subprocess.run([compiler, "--check", "--diagnostics=json", path], capture_output=True, timeout=10)
            require(result.returncode == 1 and not result.stderr, f"expected lexical rejection: {spelling!r}")
            diagnostic = json.loads(result.stdout)["diagnostics"][0]
            require(diagnostic["code"] == "AU1002", f"byte diagnostic: {diagnostic}")
            start = diagnostic["range"]["start"]
            require(start == {"offset": len(prefix), "line": 2, "column": 25}, f"byte location: {diagnostic}")
            output.unlink(missing_ok=True)
            missing = subprocess.run([compiler, path, "-o", output], capture_output=True, timeout=10)
            require(missing.returncode == 1 and not output.exists(), "invalid literal created assembly")
            expected_error = f"{path}:2:25: error AU1002: invalid byte literal\n".encode()
            require(
                not missing.stdout and missing.stderr == expected_error,
                "text and structured byte-literal diagnostics disagree",
            )
            output.write_bytes(b"preserve existing output\n")
            result = subprocess.run([compiler, path, "-o", output], capture_output=True, timeout=10)
            require(
                result.returncode == 1 and output.read_bytes() == b"preserve existing output\n",
                "invalid literal changed existing assembly",
            )
            require(
                not result.stdout and result.stderr == expected_error, "existing-output rejection diagnostic differs"
            )
            require(path.read_bytes() == original, "compiler modified invalid source")
        for body, result_type in [
            ("return 'a';", "i64"),
            ("return 'a';", "u64"),
            ("return 'a';", "bool"),
            ("return -'a';", "u8"),
            ("return 'a'+1;", "u8"),
            ("return 'a'==97;", "bool"),
            ("return u8('a');", "u8"),
            ("static_assert('a'==97);return 'a';", "u8"),
            ("i64 n='a';return 'a';", "u8"),
        ]:
            path.write_text(app(body, result_type))
            result = subprocess.run([compiler, "--check", "--diagnostics=json", path], capture_output=True, timeout=10)
            require(
                result.returncode == 1 and json.loads(result.stdout)["diagnostics"][0]["code"] == "AU3001",
                f"implicit widening/type error accepted: {body}",
            )
        dependency = root / "dependency.au"
        dependency.write_text("export module dependency;export auto invalid()->u8{return 'ab';}")
        path.write_text("module test;import dependency;auto test()->u8{return dependency::invalid();}")
        result = subprocess.run(
            [compiler, "--check", "--diagnostics=json", "--module-root", root, path], capture_output=True, timeout=10
        )
        require(result.returncode == 1, "imported malformed literal accepted")
        diagnostic = json.loads(result.stdout)["diagnostics"][0]
        require(
            diagnostic["code"] == "AU1002" and Path(diagnostic["path"]) == dependency,
            "imported byte literal lost source provenance",
        )
        # Exact generated assembly for every accepted spelling, under identical names.
        source = root / "equivalent.au"

        def assembly(literals):
            source.write_text(
                "module test;\n"
                + "\n".join(f"auto value_{index}()->u8{{return {value};}}" for index, value in enumerate(literals))
            )
            command([compiler, source, "-o", output])
            return output.read_bytes()

        require(
            assembly([s for s, _ in spellings]) == assembly([f"{v}u8" for _, v in spellings]),
            "byte literals changed assembly relative to decimal u8",
        )
    print(
        f"PASS byte literals: {len(cases)} native values, 4 checked traps, {len(invalid_bytes)} lexical and "
        f"9 exact-type rejections; {len(spellings)} assembly-equivalent spellings"
    )


if __name__ == "__main__":
    main()
