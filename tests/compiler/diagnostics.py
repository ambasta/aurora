#!/usr/bin/env python3
"""Focused check-only CLI contract. Does not assemble, link, or execute Aurora code."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile

COMPILER = Path(sys.argv[1]).resolve()
CASES = 0


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def run(arguments, status, code=None, json_mode=True):
    global CASES
    result = subprocess.run([str(COMPILER), *map(str, arguments)], capture_output=True, text=True, timeout=10)
    require(result.returncode == status, f"exit {result.returncode}, expected {status}: {result.stdout}{result.stderr}")
    CASES += 1
    if not json_mode:
        return result
    require(result.stderr == "", f"JSON command wrote stderr: {result.stderr}")
    data = json.loads(result.stdout)
    require(data["schemaVersion"] == 1 and data["success"] == (status == 0), "JSON status envelope")
    require(len(data["diagnostics"]) == (0 if code is None else 1), "first-error diagnostic count")
    if code is not None:
        require(data["diagnostics"][0]["code"] == code, f"wrong code: {data}")
        require(data["diagnostics"][0]["severity"] == "error", "severity")
        return data["diagnostics"][0]
    return data


def check(path, status=0, code=None, extra=()):
    diagnostic = run(["--check", "--diagnostics=json", *extra, path], status, code)
    if code is not None:
        plain = run(["--check", "--diagnostics=text", *extra, path], status, json_mode=False)
        text_matches(plain, diagnostic, "aurorac")
        output = Path(path).parent / "preserved-output.s"
        output.write_bytes(b"keep existing assembly\n")
        before = output.stat().st_mtime_ns
        emission = run([*extra, path, "-o", output], status, json_mode=False)
        text_matches(emission, diagnostic, "aurorac")
        require(
            output.read_bytes() == b"keep existing assembly\n" and output.stat().st_mtime_ns == before,
            "source rejection changed an existing assembly output",
        )
        output.unlink()
    return diagnostic


def text_matches(result, diagnostic, tool):
    if diagnostic["range"] is None:
        prefix = tool
    else:
        start = diagnostic["range"]["start"]
        prefix = f"{diagnostic['path']}:{start['line']}:{start['column']}"
    expected = f"{prefix}: {diagnostic['severity']} {diagnostic['code']}: {diagnostic['message']}\n"
    require(result.stdout == "" and result.stderr == expected, f"shared text/JSON payload mismatch: {result.stderr!r}")


if len(sys.argv) > 2:
    frontend = subprocess.run([str(Path(sys.argv[2]).resolve())], capture_output=True, text=True, timeout=10)
    require(frontend.returncode == 0, f"frontend tests failed: {frontend.stdout}{frontend.stderr}")
    require(json.loads(frontend.stdout) == '"\\\n\r\t\0 café 😀 ÿÀí\xa0\x80', "adversarial JSON round trip")
    print(frontend.stderr.strip())

with tempfile.TemporaryDirectory(prefix="aurora-diagnostics-") as directory:
    root = Path(directory)
    source = root / 'café-"-\\-\n.au'
    good = "module demo; auto demo() -> i64 { return 42; }\n"
    source.write_text(good)
    before = sorted(root.iterdir())
    check(source)
    require(sorted(root.iterdir()) == before, "--check created an output artifact")
    plain = run(["--check", source], 0, json_mode=False)
    require(plain.stdout == plain.stderr == "", "successful text check must be quiet")
    run(["--check", "--diagnostics=text", source], 0, json_mode=False)

    bad = "// café 😀\r\n\tmodule demo;\r\n@"
    source.write_text(bad)
    diagnostic = check(source, 1, "AU1001")
    require(diagnostic["path"] == str(source), "escaped Unicode source path")
    offset = len(bad[: bad.index("@")].encode("utf-8"))
    require(
        diagnostic["range"]
        == {
            "start": {"offset": offset, "line": 3, "column": 1},
            "end": {"offset": offset + 1, "line": 3, "column": 2},
        },
        f"multiline UTF-8 byte location: {diagnostic}",
    )
    plain = run([source, "-o", root / "bad.s"], 1, json_mode=False)
    require(diagnostic["message"] == "unsupported character", "location-neutral lexer message")
    text_matches(plain, diagnostic, "aurorac")
    require(not (root / "bad.s").exists(), "error emitted assembly")

    source.write_text("module demo")
    diagnostic = check(source, 1, "AU2001")
    require(
        diagnostic["range"]["start"] == diagnostic["range"]["end"] == {"offset": 11, "line": 1, "column": 12},
        "EOF range",
    )
    require(diagnostic["message"] == "expected ';' (found '<eof>')", "location-neutral parser message")
    for truncated in ("module demo; auto demo() -> i64 { return", "module demo; auto demo() ->"):
        source.write_text(truncated)
        diagnostic = check(source, 1, "AU2001")
        require(
            diagnostic["range"]["start"]["offset"] == len(truncated)
            and diagnostic["range"]["start"] == diagnostic["range"]["end"],
            "truncated expression/type EOF",
        )
    source.write_text("module demo; auto demo() -> i64 { return true; }")
    diagnostic = check(source, 1, "AU3001")
    require(diagnostic["path"] == str(source) and diagnostic["range"] is not None, "semantic source provenance")

    require(diagnostic["message"] == "expected i64, got bool", "location-neutral semantic message")
    source.write_text("module demo;\n\nauto demo() -> i64 {\n    return missing();\n}\n")
    diagnostic = check(source, 1, "AU4001")
    require(diagnostic["message"] == "unknown function 'missing' in defining module demo", "resolver message")
    require(
        diagnostic["path"] == str(source) and diagnostic["range"]["start"] == {"offset": 46, "line": 4, "column": 12},
        "resolver attaches the real source token",
    )
    nested = "module demo; auto demo() -> i64 { return " + "(" * 130 + "1" + ")" * 130 + "; }"
    source.write_text(nested)
    diagnostic = check(source, 1, "AU2002")
    require(diagnostic["message"] == "expression parser nesting exceeds 128", "location-neutral nesting message")

    source.write_text("module demo; import dep; auto demo() -> i64 { return 1; }")
    dep = root / "dep.au"
    dep.write_text("export module dep;\n@")
    diagnostic = check(source, 1, "AU1001", ("--module-root", root))
    require(diagnostic["path"] == str(dep) and diagnostic["range"]["start"]["line"] == 2, "imported lexer provenance")
    require(diagnostic["message"] == "module dep: unsupported character", "location-neutral imported context")
    dep.write_text("export module dep;\nauto broken() -> i64 { return 0 }")
    diagnostic = check(source, 1, "AU2001", ("--module-root", root))
    require(diagnostic["path"] == str(dep) and diagnostic["range"]["start"]["line"] == 2, "imported parser provenance")
    dep.write_text("export module dep;\nauto broken() -> i64 { return true; }")
    diagnostic = check(source, 1, "AU3001", ("--module-root", root))
    require(diagnostic["path"] == str(dep), "imported semantic provenance")
    dep.write_text("export module dep;\nauto broken() -> i64 { return missing(); }")
    diagnostic = check(source, 1, "AU4001", ("--module-root", root))
    require(
        diagnostic["path"] == str(dep) and diagnostic["range"]["start"]["line"] == 2, "imported resolver provenance"
    )
    require(diagnostic["message"] == "unknown function 'missing' in defining module dep", "imported resolver context")
    diagnostic = check(source, 1, "AU4001")
    require(diagnostic["range"] is None and diagnostic["path"] is None, "unlocated errors must not invent ranges")

    source.write_text(good)
    for options in (
        ["--unknown", "--check", "--diagnostics=json", source],
        ["--check", "--diagnostics=json"],
        ["--check", "--check", "--diagnostics=json", source],
        ["--check", "--diagnostics=json", "--diagnostics=text", source],
        ["--check", "--diagnostics=json", source, "-o", root / "never.s"],
        ["--check", "--diagnostics=json", source, "-o", ""],
        ["--check", "--diagnostics=json", source, "-o", "", "-o", root / "never.s"],
        ["--check", "--diagnostics=json", "", source],
        ["--diagnostics=json", source, "-o", root / "never.s"],
        ["--check", "--diagnostics=json", source, "--module-root"],
        ["--check", "--diagnostics=json", source, source],
    ):
        diagnostic = run(options, 2, "AU5001")
        require(diagnostic["range"] is None, "CLI error source range")
        # JSON outside check mode is invalid, while text is allowed during emission.
        if "--check" in options:
            plain = run(
                [str(option).replace("--diagnostics=json", "--diagnostics=text") for option in options],
                2,
                json_mode=False,
            )
            text_matches(plain, diagnostic, "aurorac")
    require(not (root / "never.s").exists(), "invalid CLI created output")
    # Check-only must reject output options before touching a pre-existing artifact.
    sentinel = root / "keep.s"
    sentinel.write_text("unchanged")
    run(["--check", "--diagnostics=json", source, "-o", sentinel], 2, "AU5001")
    require(sentinel.read_text() == "unchanged", "check-only changed existing output")
    check(root / "absent.au", 1, "AU4001")

    diagnostic = run(["--check", "--diagnostics=json", "--line 4: literal", source], 2, "AU5001")
    require(
        diagnostic["message"] == "unknown or duplicate command-line argument: --line 4: literal",
        "user-supplied location-like text is not stripped",
    )
    plain = run(["--check", "--line 4: literal", source], 2, json_mode=False)
    text_matches(plain, diagnostic, "aurorac")

    if len(sys.argv) > 3:
        formatter = str(Path(sys.argv[3]).resolve())
        source.write_text("module demo;\n@")
        for mode in ("--check", "--lint"):
            command = [formatter, mode, "--diagnostics=json", str(source)]
            structured = subprocess.run(command, capture_output=True, text=True, timeout=10)
            require(structured.returncode == 2 and structured.stdout == "", "formatter error transport")
            diagnostic = json.loads(structured.stderr)["diagnostics"][0]
            require(diagnostic["message"] == "unsupported character", "formatter location-neutral message")
            command[2] = "--diagnostics=text"
            plain = subprocess.run(command, capture_output=True, text=True, timeout=10)
            require(plain.returncode == 2, "formatter text error status")
            text_matches(plain, diagnostic, "aurora-fmt")
            CASES += 2
        source.write_text(good)

    emitted = root / "good.s"
    plain = run([source, "-o", emitted], 0, json_mode=False)
    require(plain.stdout == plain.stderr == "" and emitted.stat().st_size > 0, "normal emission regression")

print(f"PASS {CASES} structured diagnostic CLI cases")
