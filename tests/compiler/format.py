#!/usr/bin/env python3
"""CLI transport/rejection checks for the source-owned formatter."""

import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    binary = pathlib.Path(sys.argv[1]).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="aurora-format-", dir=binary.parent) as name:
        root = pathlib.Path(name)
        source = root / "input.au"
        source.write_text("module x;auto f()->i64{return 1+2;}")
        before = source.read_bytes()
        original_hash = hashlib.sha256(before).hexdigest()
        cases = 0

        def run(arguments, status, code=None):
            nonlocal cases
            result = subprocess.run([str(binary), *map(str, arguments)], capture_output=True, timeout=20, check=False)
            require(result.returncode == status, f"status for {arguments}: {result.returncode}: {result.stderr!r}")
            if code is not None:
                record = json.loads(result.stderr)
                require(not record["success"], "error reported success")
                require(record["diagnostics"][0]["code"] == code, f"wrong diagnostic: {record}")
                require(not result.stdout, "diagnostic command emitted source")
                if code != "AU5001":
                    diagnostic = record["diagnostics"][0]
                    plain = run(
                        ["--diagnostics=text" if str(arg) == "--diagnostics=json" else arg for arg in arguments], status
                    )
                    if diagnostic["range"] is None:
                        prefix = "aurora-fmt"
                    else:
                        start = diagnostic["range"]["start"]
                        prefix = f"{diagnostic['path']}:{start['line']}:{start['column']}"
                    expected = f"{prefix}: {diagnostic['severity']} {diagnostic['code']}: {diagnostic['message']}\n"
                    require(not plain.stdout and plain.stderr.decode() == expected, "shared error text/JSON parity")
            cases += 1
            return result

        repository = pathlib.Path(__file__).resolve().parents[2]
        for relative in (
            "library/examples/json_integers.au",
            "library/examples/ram_sector_record.au",
            "library/std/json.au",
            "library/std/json_write.au",
        ):
            run(["--check", repository / relative], 0)

        unsupported = root / "field.au"
        field_text = "module x; class Bad { builtin::span<const u8> view; };"
        unsupported.write_text(field_text)
        field = json.loads(run(["--check", "--diagnostics=json", unsupported], 2, "AU2003").stderr)["diagnostics"][0]
        require(
            field["message"] == "unsupported class field type 'builtin::span<const u8>': "
            "class fields require scalar, class, private fixed-array or private owned-byte storage",
            "specific unsupported field type diagnostic",
        )
        require(
            field["range"]["start"]["offset"] == field_text.index("builtin")
            and field["range"]["end"]["offset"] == field_text.index(" view"),
            "field type diagnostic range",
        )
        require(unsupported.read_text() == field_text, "field rejection changed source")

        formatted = run([source], 0).stdout
        require(formatted == b"module x;\nauto f() -> i64 {\n    return 1 + 2;\n}\n", "CLI golden differs")
        require(source.read_bytes() == before, "formatter changed input")
        check = run(["--check", "--diagnostics=json", source], 1)
        record = json.loads(check.stderr)
        require(record["mode"] == "format-check" and record["changed"], "missing formatting status")
        require(not check.stdout, "check emitted source")
        good = root / "good.au"
        good.write_bytes(formatted)
        record = json.loads(run(["--check", "--diagnostics=json", good], 0).stderr)
        require(record["success"] and not record["changed"], "formatted source not accepted")
        require(run([good], 0).stdout == formatted, "CLI not idempotent")
        require(json.loads(run(["--lint", "--diagnostics=json", good], 0).stderr)["success"], "semantic check failed")
        separated = root / "separated.au"
        separated.write_bytes(
            b"\nmodule x;\r\n \t\r\n\r\nauto f()->i64{\n\ni64 value=1; // value \t\r\n\n"
            b"// return group\n\nreturn value;\n\n}\n\n// footer\n\n"
        )
        separated_before = separated.read_bytes()
        separated_expected = (
            b"module x;\n\nauto f() -> i64 {\n    i64 value = 1; // value \t\r\n\n"
            b"    // return group\n\n    return value;\n}\n\n// footer\n"
        )
        require(run([separated], 0).stdout == separated_expected, "CLI deleted intentional blank lines")
        require(separated.read_bytes() == separated_before, "blank-line formatting changed input")
        separated.write_bytes(separated_expected)
        require(run([separated], 0).stdout == separated_expected, "CLI blank-line layout is not idempotent")
        record = json.loads(run(["--check", "--diagnostics=json", separated], 1).stderr)
        require(not record["changed"], "canonical blank lines still report a formatting difference")
        require(record["diagnostics"], "preserved comment whitespace keeps its existing style finding")
        separated.write_bytes(separated_expected.replace(b" \t\r\n", b"\n"))
        record = json.loads(run(["--check", "--diagnostics=json", separated], 0).stderr)
        require(record["success"] and not record["changed"], "clean canonical blank lines fail --check")
        qualified = root / "qualified.au"
        qualified.write_text(
            "module x;auto " + "f" * 100 + "()->std::ByteWriteStatus{return std::ByteWriteStatus::success;}"
        )
        qualified_before = qualified.read_bytes()
        qualified_expected = (
            "module x;\nauto " + "f" * 100 + "() ->\n    std::ByteWriteStatus {\n"
            "    return std::ByteWriteStatus::success;\n}\n"
        ).encode()
        require(run([qualified], 0).stdout == qualified_expected, "CLI split a qualified name at the soft limit")
        require(qualified.read_bytes() == qualified_before, "qualified-name formatting changed input")
        qualified.write_bytes(qualified_expected)
        require(run([qualified], 0).stdout == qualified_expected, "qualified-name CLI output is not idempotent")
        record = json.loads(run(["--check", "--diagnostics=json", qualified], 0).stderr)
        require(record["success"] and not record["changed"], "canonical qualified-name layout fails --check")
        literal = root / "literal.au"
        literal.write_text('module x;auto f()->i64{return g("' + "x" * 119 + '");}')
        record = json.loads(run(["--check", "--diagnostics=json", literal], 1).stderr)
        require(record["changed"], "oversized literal hid noncanonical layout")
        literal.write_bytes(run([literal], 0).stdout)
        record = json.loads(run(["--check", "--diagnostics=json", literal], 0).stderr)
        require(record["success"] and not record["diagnostics"], "canonical oversized literal fails check")
        literal.write_text(literal.read_text().replace("x" * 119, "x" * 118))
        record = json.loads(run(["--check", "--diagnostics=json", literal], 0).stderr)
        require(record["success"] and not record["changed"], "canonical indented literal fails check")
        bad = root / "bad.au"
        for text, code in [
            ("module x;auto f()->i64{return @;}", "AU1001"),
            ("module x;auto f()->i64{return ;}", "AU2001"),
        ]:
            bad.write_text(text)
            result = run([bad], 2)
            require(not result.stdout and code.encode() in result.stderr, "bad input leaked output or lost code")
            run(["--check", "--diagnostics=json", bad], 2, code)
        bad.write_text("module x;auto f()->i64{return missing;}")
        require(run([bad], 0).stdout, "parse-only formatter unexpectedly resolved names")
        run(["--lint", "--diagnostics=json", bad], 2, "AU3001")
        modules = root / "modules"
        modules.mkdir()
        (modules / "dep.au").write_text("export module dep;export namespace dep { auto answer()->i64{return 7;} }")
        bad.write_text("module x;import dep;auto f()->i64{return dep::answer();}")
        run(["--lint", "--diagnostics=json", bad], 2, "AU4001")
        run(["--lint", "--diagnostics=json", "--module-root", modules, bad], 0)
        (modules / "dep.au").write_text("export module dep;export namespace dep { auto answer()->i64{return @;} }")
        imported = run(["--lint", "--diagnostics=json", "--module-root", modules, bad], 2, "AU1001")
        require(json.loads(imported.stderr)["diagnostics"][0]["path"].endswith("dep.au"), "import origin lost")
        run(["--check", "--diagnostics=json", root / "missing.au"], 2, "AU4001")
        link = root / "link.au"
        link.symlink_to(good)
        run(["--check", "--diagnostics=json", link], 2, "AU4001")
        run(["--check", "--diagnostics=json", root], 2, "AU4001")
        bad.write_bytes(b" " * (1024 * 1024 + 1))
        run(["--check", "--diagnostics=json", bad], 2, "AU4001")
        prefix = b"module x;\nauto f() -> i64 {\n    return 1;\n}\n//"
        exact = prefix + b"x" * (1024 * 1024 - len(prefix) - 1)
        bad.write_bytes(exact)
        require(run([bad], 0).stdout == exact + b"\n", "exact output cap changed comment bytes")
        bad.write_bytes(exact + b"x")
        overflow = run([bad], 2)
        require(
            not overflow.stdout and b"formatted output exceeds 1 MiB bound" in overflow.stderr,
            "final newline crossed output cap or published partial output",
        )
        bad.write_text("module x;auto f()->i64{" + "{" * 128 + "return 1;" + "}" * 129)
        run(["--check", "--diagnostics=json", bad], 2, "AU2002")
        bad.write_text("module x;auto f()->i64{" + "{" * 127 + "x;" * 2100 + "}" * 127 + "return 1;}")
        expansion = run([bad], 2)
        require(
            not expansion.stdout and b"formatted output exceeds 1 MiB bound" in expansion.stderr,
            "output expansion bound did not reject before stdout",
        )
        for arguments in [
            [],
            ["--check", "--lint", source],
            ["-i", source],
            ["-o", good, source],
            ["--check", "--check", source],
            [source, good],
            ["--module-root"],
            ["--module-root", modules, source],
            ["--runtime-root", modules, source],
            ["--lint", "--runtime-root", "", source],
            ["--lint", "--runtime-root", modules, "--runtime-root", modules, source],
            ["--diagnostics=json", source],
            ["--diagnostics=text", "--diagnostics=json", source],
        ]:
            # Append JSON only when it is not already present, preserving duplicates being tested.
            if "--diagnostics=json" not in arguments:
                arguments = ["--diagnostics=json", *arguments]
            run(arguments, 2, "AU5001")
        require(hashlib.sha256(source.read_bytes()).hexdigest() == original_hash, "input changed during CLI tests")
        print(
            f"PASS {cases} formatter CLI cases; unchanged input, no error source output, original diagnostic families"
        )


if __name__ == "__main__":
    main()
