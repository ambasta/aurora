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


def main():
    compiler = Path(sys.argv[1]).resolve(strict=True)
    print(f"compiler_sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()}", flush=True)
    spellings = [(f"'\\x{value:02X}'", value) for value in range(256)]
    spellings += [("'" + chr(value) + "'", value) for value in range(32, 127) if value not in (39, 92)]
    spellings += [("'\\" + escape + "'", value) for escape, value in
                  [("'", 39), ("\\", 92), ("0", 0), ("a", 7), ("b", 8), ("f", 12),
                   ("n", 10), ("r", 13), ("t", 9), ("v", 11)]]
    spellings += [("'\\xff'", 255), ("'\\xAb'", 171)]
    cases = [Case(f"byte spelling {spelling}", f"static_assert({spelling}=={value}u8);return u64({spelling});", value)
             for spelling, value in spellings]
    cases += [
        Case("byte operations", r"return u64((~'\0' & '\x0f') + '\x01');", 16),
        Case("signed widening", "return i64('[');", 91, result_type="i64"),
        Case("literal shift", r"return u64('\x01' << 7);", 128),
        Case("literal array", r"const array<u8,3> b={'[','\0','\xff'};return u64(b[2]);", 255),
        Case("literal parameter and direct copied return", "const Box b=make('[');return u64(b.get());", 91,
             prelude="class Box{u8 value;public:Box(u8 v):value(v){}auto get()const->u8{return value;}};"
                     "auto make(u8 value)->Box{return Box(value);}"),
    ]
    invalid = ["''", "'ab'", "'''", "'a", "'\\", "'\\q'", "'\\x'", "'\\x0'", "'\\x000'",
               "'\\x100'", "'\\xGG'", "'\\u0041'", "'\\U00000041'", "'\\101'", "'\\01'", "'\\\"'",
               "'é'", "'😀'", "'\t'", "'\0'", "'\x7f'", "'\n'", "'\r'", "'\\\n'", "'\\\r'",
               "'a'u8", "'a'u64", "'a'0", "'a'_suffix"]
    # Every raw non-ASCII byte is rejected even when not valid UTF-8.
    invalid_bytes = [x.encode() for x in invalid] + [b"'" + bytes([n]) + b"'" for n in range(128, 256)]
    with tempfile.TemporaryDirectory(prefix="aurora-byte-literals-") as temporary:
        root = Path(temporary)
        runner = NativeRunner(root, compiler, 10)
        for offset in range(0, len(cases) - 1, 32):
            runner.cases(cases[offset:min(offset + 32, len(cases) - 1)])
        runner.cases([cases[-1]])
        for body, trap in [(r"return u64('\xff'+ '\x01');", Trap.OVERFLOW),
                           (r"return u64('\0' - '\x01');", Trap.OVERFLOW),
                           (r"return u64('a' / '\0');", Trap.ZERO),
                           (r"return u64('a' << 8);", Trap.COUNT)]:
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
            require(not missing.stdout and missing.stderr == expected_error,
                    "text and structured byte-literal diagnostics disagree")
            output.write_bytes(b"preserve existing output\n")
            result = subprocess.run([compiler, path, "-o", output], capture_output=True, timeout=10)
            require(result.returncode == 1 and output.read_bytes() == b"preserve existing output\n",
                    "invalid literal changed existing assembly")
            require(not result.stdout and result.stderr == expected_error,
                    "existing-output rejection diagnostic differs")
            require(path.read_bytes() == original, "compiler modified invalid source")
        for body, result_type in [("return 'a';", "i64"), ("return 'a';", "u64"), ("return 'a';", "bool"),
                                  ("return -'a';", "u8"), ("return 'a'+1;", "u8"),
                                  ("return 'a'==97;", "bool"), ("return u8('a');", "u8"),
                                  ("static_assert('a'==97);return 'a';", "u8"),
                                  ("i64 n='a';return 'a';", "u8")]:
            path.write_text(app(body, result_type))
            result = subprocess.run([compiler, "--check", "--diagnostics=json", path], capture_output=True, timeout=10)
            require(result.returncode == 1 and json.loads(result.stdout)["diagnostics"][0]["code"] == "AU3001",
                    f"implicit widening/type error accepted: {body}")
        dependency = root / "dependency.au"
        dependency.write_text("export module dependency;export auto invalid()->u8{return 'ab';}")
        path.write_text("module test;import dependency;auto test()->u8{return dependency::invalid();}")
        result = subprocess.run([compiler, "--check", "--diagnostics=json", "--module-root", root, path],
                                capture_output=True, timeout=10)
        require(result.returncode == 1, "imported malformed literal accepted")
        diagnostic = json.loads(result.stdout)["diagnostics"][0]
        require(diagnostic["code"] == "AU1002" and Path(diagnostic["path"]) == dependency,
                "imported byte literal lost source provenance")
        # Exact generated assembly for every accepted spelling, under identical names.
        source = root / "equivalent.au"
        def assembly(literals):
            source.write_text("module test;\n" + "\n".join(
                f"auto value_{index}()->u8{{return {value};}}" for index, value in enumerate(literals)))
            command([compiler, source, "-o", output])
            return output.read_bytes()
        require(assembly([s for s, _ in spellings]) == assembly([f"{v}u8" for _, v in spellings]),
                "byte literals changed assembly relative to decimal u8")
    print(f"PASS byte literals: {len(cases)} native values, 4 checked traps, {len(invalid_bytes)} lexical and "
          f"9 exact-type rejections; {len(spellings)} assembly-equivalent spellings")


if __name__ == "__main__":
    main()
