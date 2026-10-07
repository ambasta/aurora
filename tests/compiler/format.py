#!/usr/bin/env python3
"""CLI transport/rejection checks; all Aurora lexing/parsing stays in C++."""

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
            cases += 1
            return result

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
