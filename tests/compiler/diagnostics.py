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
    return run(["--check", "--diagnostics=json", *extra, path], status, code)


if len(sys.argv) > 2:
    frontend = subprocess.run([str(Path(sys.argv[2]).resolve())], capture_output=True, text=True, timeout=10)
    require(frontend.returncode == 0, f"frontend tests failed: {frontend.stdout}{frontend.stderr}")
    require(json.loads(frontend.stdout) == '\"\\\n\r\t\0 café 😀 ÿÀí\xa0\x80', "adversarial JSON round trip")
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
    offset = len(bad[:bad.index("@")].encode("utf-8"))
    require(diagnostic["range"] == {
        "start": {"offset": offset, "line": 3, "column": 1},
        "end": {"offset": offset + 1, "line": 3, "column": 2},
    }, f"multiline UTF-8 byte location: {diagnostic}")
    plain = run([source, "-o", root / "bad.s"], 1, json_mode=False)
    require(plain.stderr == "aurorac: line 3: unsupported character\n", "legacy lexical text changed")
    require(not (root / "bad.s").exists(), "error emitted assembly")

    source.write_text("module demo")
    diagnostic = check(source, 1, "AU2001")
    require(diagnostic["range"]["start"] == diagnostic["range"]["end"] ==
            {"offset": 11, "line": 1, "column": 12}, "EOF range")
    for truncated in ("module demo; auto demo() -> i64 { return", "module demo; auto demo() ->"):
        source.write_text(truncated)
        diagnostic = check(source, 1, "AU2001")
        require(diagnostic["range"]["start"]["offset"] == len(truncated) and
                diagnostic["range"]["start"] == diagnostic["range"]["end"], "truncated expression/type EOF")
    source.write_text("module demo; auto demo() -> i64 { return true; }")
    diagnostic = check(source, 1, "AU3001")
    require(diagnostic["path"] == str(source) and diagnostic["range"] is not None, "semantic source provenance")

    source.write_text("module demo; import dep; auto demo() -> i64 { return 1; }")
    dep = root / "dep.au"
    dep.write_text("export module dep;\n@")
    diagnostic = check(source, 1, "AU1001", ("--module-root", root))
    require(diagnostic["path"] == str(dep) and diagnostic["range"]["start"]["line"] == 2,
            "imported lexer provenance")
    require(diagnostic["message"] == "module dep: line 2: unsupported character", "imported legacy context")
    dep.write_text("export module dep;\nauto broken() -> i64 { return 0 }")
    diagnostic = check(source, 1, "AU2001", ("--module-root", root))
    require(diagnostic["path"] == str(dep) and diagnostic["range"]["start"]["line"] == 2,
            "imported parser provenance")
    dep.write_text("export module dep;\nauto broken() -> i64 { return true; }")
    diagnostic = check(source, 1, "AU3001", ("--module-root", root))
    require(diagnostic["path"] == str(dep), "imported semantic provenance")
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
    require(not (root / "never.s").exists(), "invalid CLI created output")
    # Check-only must reject output options before touching a pre-existing artifact.
    sentinel = root / "keep.s"
    sentinel.write_text("unchanged")
    run(["--check", "--diagnostics=json", source, "-o", sentinel], 2, "AU5001")
    require(sentinel.read_text() == "unchanged", "check-only changed existing output")
    check(root / "absent.au", 1, "AU4001")

    emitted = root / "good.s"
    plain = run([source, "-o", emitted], 0, json_mode=False)
    require(plain.stdout == plain.stderr == "" and emitted.stat().st_size > 0, "normal emission regression")

print(f"PASS {CASES} structured diagnostic CLI cases")
