#!/usr/bin/env python3
"""Require stage 1 to rebuild its entire Aurora frontend and preserve outputs."""

from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile


def stage_modules(root, destination):
    # Import the actual build staging helper: both paths copy exported modules
    # exactly, without rewriting their namespaces or interface declarations.
    sys.path.insert(0, str(root / "scripts"))
    from bootstrap_frontend import stage_modules as stage

    stage(destination, root / "compiler/lexer.au", root / "compiler/expression_arena.au")


def require(value, message):
    if not value:
        raise AssertionError(message)


def sources(root):
    # Only checked-in source roots, never generated build or retained evidence.
    return sorted(
        path for name in ("compiler", "examples", "kernel", "library", "tests") for path in (root / name).rglob("*.au")
    )


def run(command):
    return subprocess.run(command, capture_output=True, timeout=30, check=True).stdout


def symbols(path, globals_only=False):
    command = ["nm", "--defined-only", "--format=posix", "--print-size"]
    if globals_only:
        command.append("--extern-only")
    return {row.split()[0]: row.split()[1:] for row in run([*command, str(path)]).decode().splitlines()}


def sections(path):
    # GNU objdump's file heading contains the output path; the actual section
    # addresses and bytes must match after static relocation, including .rodata.
    output = run(["objdump", "-s", str(path)])
    heading, separator, contents = output.partition(b"Contents of section ")
    require(separator and contents, "linked lexer has no section contents")
    return contents


def private_bootstrap(stage0, stage1, root, work, ordinary):
    bridge = root / "compiler/hosted_lexer.S"
    entry = "aurora_hosted_lexer_invoke"
    ordinary_unit = work / "ordinary.s"
    ordinary_unit.write_bytes(ordinary + b"\n" + bridge.read_bytes())
    units = [ordinary_unit]
    for number, compiler in enumerate((stage0, stage1)):
        output = work / f"private-stage{number}.s"
        run(
            [
                sys.executable,
                "-B",
                str(root / "scripts/bootstrap_lexer.py"),
                str(compiler),
                str(root / "compiler/lexer.au"),
                str(bridge),
                str(output),
            ]
        )
        units.append(output)
    require(
        units[1].read_bytes() == units[2].read_bytes(),
        "private stage 0/1 bootstrap assembly differs",
    )
    objects, executables = [], []
    for unit in units:
        obj = unit.with_suffix(".o")
        executable = unit.with_suffix(".elf")
        run(["as", "--64", str(unit), "-o", str(obj)])
        # Link, but do not execute: resolve both global and local call relocations
        # before comparing actual code/data, rather than assembly spelling.
        run(["ld", "--build-id=none", "-e", entry, str(obj), "-o", str(executable)])
        objects.append(obj)
        executables.append(executable)
    public = symbols(objects[0], globals_only=True)
    require(
        entry in public and len(public) > 1,
        "ordinary compiler binding control has no public helpers",
    )
    require(
        "aurora_reflect_size" in public and "aurora_reflect_field_count" in public,
        "ordinary compiler binding control has no public reflection entries",
    )
    ordinary_symbols = {name: [row[0].upper(), *row[1:]] for name, row in symbols(objects[0]).items()}
    for obj, executable in zip(objects[1:], executables[1:], strict=True):
        require(
            set(symbols(obj, globals_only=True)) == {entry},
            "private lexer exported a generated symbol",
        )
        local_symbols = {name: [row[0].upper(), *row[1:]] for name, row in symbols(obj).items()}
        require(
            local_symbols == ordinary_symbols,
            "private binding changed symbol locations, sizes or types",
        )
        require(
            sections(executable) == sections(executables[0]),
            "private binding changed linked code/data bytes",
        )
    output = work / "rejected-options.s"
    marker = b"preserve on argument rejection\n"
    for compiler in (stage0, stage1):
        for flags, message in (
            (("--local-symbols", "--local-symbols", "-o", str(output)), "duplicate --local-symbols option"),
            (("--check", "--local-symbols"), "--check does not accept --local-symbols"),
        ):
            output.write_bytes(marker)
            result = subprocess.run(
                [str(compiler), *flags, str(root / "compiler/lexer.au")],
                capture_output=True,
                timeout=30,
                check=False,
            )
            require(
                result.returncode == 2 and b"AU5001: " + message.encode() in result.stderr and not result.stdout,
                "local-symbols option combination did not produce its specific argument rejection",
            )
            require(output.read_bytes() == marker, "invalid local-symbols options changed output")
    print("PASS private bootstrap stage identity, sole shim export, symbol layouts and unchanged linked code/data")


def frontend_bootstrap(stage0, stage1, root, work):
    entries = {
        "aurora_hosted_lexer_invoke",
        "aurora_hosted_parser_create",
        "aurora_hosted_parser_parse",
        "aurora_hosted_parser_count",
        "aurora_hosted_parser_read",
        "aurora_hosted_parser_release",
    }
    units = []
    for number, compiler in enumerate((stage0, stage1)):
        output = work / f"frontend-stage{number}.s"
        run(
            [
                sys.executable,
                "-B",
                str(root / "scripts/bootstrap_frontend.py"),
                str(compiler),
                str(root / "compiler/lexer.au"),
                str(root / "compiler/expression_arena.au"),
                str(root / "compiler/expression_parser.au"),
                str(root / "compiler/hosted_lexer.S"),
                str(root / "compiler/hosted_parser.S"),
                str(output),
            ]
        )
        units.append(output)
        obj = output.with_suffix(".o")
        run(["as", "--64", str(output), "-o", str(obj)])
        require(set(symbols(obj, globals_only=True)) == entries, "frontend leaked a generated symbol or lost a shim")
        for name in ("lexer.au", "expression_arena.au"):
            require(
                (work / "compiler-modules/aurora/compiler" / name).read_bytes()
                == (root / "compiler" / name).read_bytes(),
                f"staged compiler module changed exported source: {name}",
            )
    require(units[0].read_bytes() == units[1].read_bytes(), "whole frontend stage 0/1 bootstrap assembly differs")
    require(
        units[0].with_suffix(".generated.s").read_bytes() == units[1].with_suffix(".generated.s").read_bytes(),
        "whole frontend stage 0/1 generated graph differs",
    )
    require(
        units[0].with_suffix(".o").read_bytes() == units[1].with_suffix(".o").read_bytes(),
        "whole frontend stage 0/1 object bytes differ",
    )
    print("PASS whole frontend stage identity, exact exported module staging and private shim-only exports")


def main():
    stage0, stage1, root = (Path(value).resolve() for value in sys.argv[1:])
    with tempfile.TemporaryDirectory(prefix="hosted-lexer-bootstrap-") as temporary:
        work = Path(temporary)
        outputs = [work / "stage0.s", work / "stage1.s"]
        module_root = work / "compiler-modules"
        stage_modules(root, module_root)
        records = []
        corpus = sources(root)
        require(root / "compiler/lexer.au" in corpus, "lexer self-rebuild input is missing")
        require(root / "compiler/expression_parser.au" in corpus, "whole frontend self-rebuild input is missing")
        for source in corpus:
            runs = []
            for compiler, output in zip((stage0, stage1), outputs, strict=True):
                output.write_bytes(b"preserve on rejection\n")
                runs.append(
                    subprocess.run(
                        [
                            str(compiler),
                            "--module-root",
                            str(module_root if source == root / "compiler/expression_parser.au" else root / "library"),
                            str(source),
                            "-o",
                            str(output),
                        ],
                        capture_output=True,
                        timeout=30,
                        check=False,
                    )
                )
            for run, output in zip(runs, outputs, strict=True):
                require(
                    run.returncode in (0, 1),
                    f"compiler crash or invocation failure: {source}: {run.returncode}",
                )
                require(b"AU9001" not in run.stderr, f"internal compiler failure: {source}")
                if run.returncode == 1:
                    require(
                        output.read_bytes() == b"preserve on rejection\n",
                        f"rejected output changed: {source}",
                    )
            require(
                (runs[0].returncode, runs[0].stdout, runs[0].stderr)
                == (runs[1].returncode, runs[1].stdout, runs[1].stderr),
                f"compiler diagnostics differ: {source}",
            )
            require(
                outputs[0].read_bytes() == outputs[1].read_bytes(),
                f"assembly/output preservation differs: {source}",
            )
            if source == root / "compiler/lexer.au":
                require(runs[0].returncode == 0, "lexer self-rebuild failed")
                print("PASS stage 1 lexer self-rebuild SHA256 " + hashlib.sha256(outputs[1].read_bytes()).hexdigest())
                private_bootstrap(stage0, stage1, root, work, outputs[0].read_bytes())
            if source == root / "compiler/expression_parser.au":
                require(runs[0].returncode == 0, "whole frontend self-rebuild failed")
                frontend_bootstrap(stage0, stage1, root, work)
            records.append({"source": str(source.relative_to(root)), "status": runs[0].returncode})
        require(len(records) > 1, "source corpus is empty")
        print(
            "PASS stage0/stage1 diagnostics, assembly and output preservation: "
            + json.dumps(
                {
                    "sources": len(records),
                    "accepted": sum(row["status"] == 0 for row in records),
                }
            )
        )


if __name__ == "__main__":
    main()
