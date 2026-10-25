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

    field_text = "module x; class Bad { builtin::span<const u8> view; };"
    source.write_text(field_text)
    field = check(source, 1, "AU2003")
    require(
        field["message"] == "unsupported class field type 'builtin::span<const u8>': "
        "class fields require scalar, class, private fixed-array or private owned-byte storage",
        "specific unsupported class field type",
    )
    require(
        field["range"]["start"]["offset"] == field_text.index("builtin")
        and field["range"]["end"]["offset"] == field_text.index(" view"),
        "complete field type range",
    )
    require(source.read_text() == field_text, "field rejection changed source")

    field_text = "// café 😀\r\nmodule demo; class Bad { builtin :: span < const u8 > view; };"
    source.write_text(field_text)
    field = check(source, 1, "AU2003")
    require(
        field["range"]["start"]["offset"] == len(field_text[: field_text.index("builtin")].encode())
        and field["range"]["end"]["offset"] == len(field_text[: field_text.index(" view")].encode()),
        "spaced full type range after non-ASCII comment uses byte offsets",
    )

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
    dep.write_text("export module dep;\nclass Bad { builtin::span<const u8> view; };")
    diagnostic = check(source, 1, "AU2003", ("--module-root", root))
    require(
        diagnostic["path"] == str(dep) and diagnostic["range"]["start"]["line"] == 2,
        "imported unsupported-field code and full type provenance",
    )
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

    original_assembly = emitted.read_bytes()
    facts_path = root / "good.stack.json"
    run([source, "-o", emitted, "--stack-facts", facts_path], 0, json_mode=False)
    require(emitted.read_bytes() == original_assembly, "stack facts changed ordinary assembly bytes")
    facts = json.loads(facts_path.read_text())
    require(
        facts
        == {
            "version": 2,
            "functions": {
                "demo": {"local_bytes": 16, "calls": {}, "copied_record": None},
                "aurora_reflect_size": {"local_bytes": 8, "calls": {}, "copied_record": None},
                "aurora_reflect_field_count": {"local_bytes": 8, "calls": {}, "copied_record": None},
            },
        },
        "simple emitted stack facts",
    )
    original_facts = facts_path.read_bytes()
    for options in (
        ["--referenced-reflection-only", source, "-o", emitted],
        [source, "--referenced-reflection-only", "-o", emitted],
        [source, "-o", emitted, "--referenced-reflection-only"],
    ):
        run([*options, "--stack-facts", facts_path], 0, json_mode=False)
        closed = json.loads(facts_path.read_text())["functions"]
        require(set(closed) == {"demo"}, "query-free closed mode retained helper facts")
        require(b"aurora_reflect_" not in emitted.read_bytes(), "query-free closed mode retained helper symbols")
    closed_assembly, closed_facts = emitted.read_bytes(), facts_path.read_bytes()
    object_path = root / "good.o"
    object_stack = root / "good.object.stack.json"
    object_abi = root / "good.object.abi.json"
    run(
        [
            source,
            "--emit-object",
            "--referenced-reflection-only",
            "-o",
            object_path,
            "--stack-facts",
            object_stack,
            "--abi-facts",
            object_abi,
        ],
        0,
        json_mode=False,
    )
    require(object_path.read_bytes().startswith(b"\x7fELF"), "object mode did not publish ELF")
    require(object_stack.read_bytes() == closed_facts, "object mode changed stack facts")
    require(json.loads(object_abi.read_text())["version"] > 0, "object mode omitted ABI facts")
    for options in (
        [source, "--emit-object", "--emit-object", "-o", object_path],
        [source, "--emit-object=yes", "-o", object_path],
        ["--check", "--emit-object", source],
    ):
        before_object = object_path.read_bytes()
        run(options, 2, json_mode=False)
        require(object_path.read_bytes() == before_object, "invalid object option replaced output")
    for options in (
        [source, "-o", emitted, "--referenced-reflection-only", "--referenced-reflection-only"],
        [source, "-o", emitted, "--referenced-reflection-only=yes"],
        ["--check", "--referenced-reflection-only", source],
        ["--referenced-reflection-only", source, "--check"],
    ):
        run(options, 2, json_mode=False)
        require(
            emitted.read_bytes() == closed_assembly and facts_path.read_bytes() == closed_facts,
            "invalid reflection emission options changed existing artifacts",
        )
    run([source, "-o", emitted, "--stack-facts", facts_path], 0, json_mode=False)
    require(
        emitted.read_bytes() == original_assembly and facts_path.read_bytes() == original_facts,
        "default reflection output changed after closed-mode use",
    )
    for options in (
        ["--stack-facts"],
        [source, "-o", emitted, "--stack-facts", ""],
        [source, "-o", emitted, "--stack-facts", facts_path, "--stack-facts", facts_path],
        [source, "-o", emitted, "--stack-facts", emitted.parent / "." / emitted.name],
    ):
        run(options, 2, json_mode=False)
    run(["--check", "--diagnostics=json", source, "--stack-facts", facts_path], 2, "AU5001")
    require(
        emitted.read_bytes() == original_assembly and facts_path.read_bytes() == original_facts,
        "rejected stack-facts option changed artifacts",
    )
    # Output authority applies equally to the sidecar; source aliases and symlinks fail.
    run([source, "-o", emitted, "--stack-facts", source], 1, json_mode=False)
    link = root / "facts-link"
    link.symlink_to(facts_path)
    run([source, "-o", emitted, "--stack-facts", link], 1, json_mode=False)
    source.write_text("module demo; auto demo() -> i64 { return missing; }\n")
    run([source, "-o", emitted, "--stack-facts", facts_path], 1, json_mode=False)
    require(
        emitted.read_bytes() == original_assembly and facts_path.read_bytes() == original_facts,
        "failed stack-facts emission changed artifacts",
    )
    require(not list(root.glob(".aurora-output-*.tmp")), "stack-facts failure left temporary files")

    # Private adapter layouts come from the same validated module as assembly.
    source.write_text("""module demo;
namespace abi {
    enum class Mode { ready, done };
    class Child { public: u8 small; i64 wide; };
    class Record {
    public:
        u8 tag; bool valid; Child nested; Mode mode;
        Record(Child value) : tag(1u8), valid(true), nested(value), mode(Mode::ready) {}
    };
    class Owner {
        u8 prefix; builtin::OwnedBytes payload; i64 suffix;
    public:
        Owner(builtin::ByteRegion region, builtin::OwnedBytes bytes)
            : prefix(1u8), payload(move(bytes)), suffix(2) {}
    };
    auto copied(Record value) -> Record { return value; }
    auto released(builtin::ByteRegion region, Owner value) -> i64 { return 0; }
    auto scan(builtin::span<const u8> source, i64 value) -> i64 { return source.size() + value; }
}
auto demo() -> i64 { return 42; }
""")
    abi_path = root / "good.abi.json"
    run([source, "-o", emitted], 0, json_mode=False)
    abi_assembly = emitted.read_bytes()
    run([source, "-o", emitted, "--abi-facts", abi_path, "--stack-facts", facts_path], 0, json_mode=False)
    require(emitted.read_bytes() == abi_assembly, "ABI facts changed generated assembly")
    abi = json.loads(abi_path.read_text())
    require(abi["version"] == 2 and abi["span_bytes"] == 56, "ABI facts schema/span")

    def declaration(group, name):
        matches = [(symbol, value) for symbol, value in abi[group].items() if value["source_name"] == name]
        require(len(matches) == 1, f"ambiguous/missing ABI declaration: {name}")
        return matches[0]

    _, child = declaration("records", "abi::Child")
    _, record = declaration("records", "abi::Record")
    _, owner = declaration("records", "abi::Owner")
    require((child["size"], child["alignment"], child["reserved"]) == (16, 8, 16), "nested ABI layout")
    require((record["size"], record["alignment"], record["reserved"]) == (40, 8, 40), "copied ABI layout")
    require(
        [(field["name"], field["offset"], field["bytes"], field["kind"]) for field in record["fields"]]
        == [("tag", 0, 1, "u8"), ("valid", 8, 8, "bool"), ("nested", 16, 16, "class"), ("mode", 32, 8, "enum")],
        "ABI physical widths/offsets, including eight-byte bool",
    )
    require(
        owner["size"] == owner["reserved"] == 48
        and [(field["offset"], field["bytes"]) for field in owner["fields"]] == [(0, 1), (8, 32), (40, 8)],
        "opaque owning ABI extent",
    )
    _, enumeration = declaration("enums", "abi::Mode")
    require(enumeration["cases"] == {"ready": 0, "done": 1}, "resolved enum names/values")
    copied_symbol, copied = declaration("functions", "abi::copied")
    _, released = declaration("functions", "abi::released")
    _, scan = declaration("functions", "abi::scan")
    require(copied_symbol.encode() + b":" in abi_assembly, "source name maps to emitted symbol")
    require(copied["parameter_bytes"] == copied["result"]["bytes"] == 40, "copied call record extents")
    require(
        released["parameter_bytes"] == 56
        and [(part["offset"], part["bytes"]) for part in released["parameters"]] == [(0, 8), (8, 48)],
        "owning release record extents",
    )
    require(
        scan["parameter_bytes"] == 64
        and [(part["offset"], part["bytes"]) for part in scan["parameters"]] == [(0, 56), (56, 8)],
        "span call record extents",
    )
    original_abi, original_stack = abi_path.read_bytes(), facts_path.read_bytes()
    for options in (
        ["--abi-facts"],
        [source, "-o", emitted, "--abi-facts", ""],
        [source, "-o", emitted, "--abi-facts", abi_path, "--abi-facts", abi_path],
        [source, "-o", emitted, "--abi-facts", emitted.parent / "." / emitted.name],
        [source, "-o", emitted, "--stack-facts", facts_path, "--abi-facts", facts_path],
    ):
        run(options, 2, json_mode=False)
    run(["--check", "--diagnostics=json", source, "--abi-facts", abi_path], 2, "AU5001")
    run([source, "-o", emitted, "--abi-facts", source], 1, json_mode=False)
    abi_link = root / "abi-link"
    abi_link.symlink_to(abi_path)
    run([source, "-o", emitted, "--abi-facts", abi_link], 1, json_mode=False)
    source.write_text("module demo; auto demo() -> i64 { return missing; }\n")
    run([source, "-o", emitted, "--abi-facts", abi_path], 1, json_mode=False)
    require(
        emitted.read_bytes() == abi_assembly
        and abi_path.read_bytes() == original_abi
        and facts_path.read_bytes() == original_stack,
        "failed ABI generation changed assembly or sidecars",
    )
    require(not list(root.glob(".aurora-output-*.tmp")), "ABI failure left temporary files")

print(f"PASS {CASES} structured diagnostic CLI cases")
