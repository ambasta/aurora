#!/usr/bin/env python3
"""Require current compiler frontend convergence and pinned bootstrap selection."""

from pathlib import Path
import hashlib
import importlib.util
import json
import os
import shutil
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


def compiler_digest(compiler):
    return hashlib.sha256(compiler.read_bytes()).hexdigest()


def frontend_arguments(compiler, root, output):
    return [
        str(compiler),
        str(root / "compiler/lexer.au"),
        str(root / "compiler/expression_arena.au"),
        str(root / "compiler/expression_parser.au"),
        str(root / "compiler/hosted_lexer.S"),
        str(root / "compiler/hosted_parser.S"),
        str(output),
    ]


def compiler_pin_controls(compiler, root, work):
    driver_path = root / "scripts/bootstrap_frontend.py"
    command = [sys.executable, "-B", str(driver_path)]
    digest = compiler_digest(compiler)
    control = work / "pin-controls"
    control.mkdir()
    output = control / "frontend.s"
    raw = output.with_suffix(".generated.s")
    modules = control / "compiler-modules/aurora/compiler"
    modules.mkdir(parents=True)
    protected = [output, raw, modules / "lexer.au", modules / "expression_arena.au"]
    for index, path in enumerate(protected):
        path.write_bytes(f"preserve pinned selection {index}\n".encode())
    preserved = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in protected}
    nonexecutable = control / "nonexecutable"
    nonexecutable.write_text("not executable\n")
    nonexecutable.chmod(0o644)
    selected = control / "selected-compiler"
    shutil.copyfile(compiler, selected)
    selected.chmod(0o755)
    for accepted in (compiler, selected):
        result = subprocess.run(
            [*command, "--verify-compiler", str(accepted), digest], capture_output=True, timeout=30, check=True
        )
        require(not result.stdout and not result.stderr, "compiler verification wrote output")
    mismatch = ("0" if digest[0] != "0" else "1") + digest[1:]

    def require_preserved():
        for path, expected in preserved.items():
            require(
                (path.read_bytes(), path.stat().st_mtime_ns) == expected,
                f"rejected compiler selection changed output or staged module: {path.name}",
            )

    def reject(arguments):
        result = subprocess.run([*command, *arguments], cwd=control, capture_output=True, timeout=30, check=False)
        require(
            result.returncode == 1 and b"bootstrap frontend:" in result.stderr and not result.stdout,
            f"invalid compiler selection did not fail closed: {arguments[:3]}",
        )
        require_preserved()

    for invalid_compiler, invalid_digest in (
        (compiler, ""),
        (compiler, digest[:-1]),
        (compiler, "A" * 64),
        (compiler, "g" * 64),
        (compiler, mismatch),
        (control / "missing-compiler", digest),
        (control, digest),
        (nonexecutable, compiler_digest(nonexecutable)),
        (Path(selected.name), digest),
    ):
        reject(["--verify-compiler", str(invalid_compiler), invalid_digest])
        reject(["--compiler-sha256", invalid_digest, *frontend_arguments(invalid_compiler, root, output)])
        reject(
            [
                "--compiler-sha256",
                invalid_digest,
                "--lexer",
                str(invalid_compiler),
                str(root / "compiler/lexer.au"),
                str(root / "compiler/hosted_lexer.S"),
                str(output),
            ]
        )
    for arguments in (
        ["--compiler-sha256"],
        ["--compiler-sha256", digest],
        ["--verify-compiler"],
        ["--verify-compiler", str(compiler)],
        ["--compiler-sha256", digest, "--events", str(root / "compiler/lexer.au"), str(output)],
    ):
        reject(arguments)

    # Replace an already verified selection at exactly the same path. Its old
    # digest must fail in the CLI, without changing outputs or staged modules.
    selected.write_text("#!/bin/sh\nexit 99\n")
    reject(["--verify-compiler", str(selected), digest])
    reject(["--compiler-sha256", digest, *frontend_arguments(selected, root, output)])

    # Exercise the second check deterministically: staging replaces the selected
    # executable after main's first verification and before emit executes it.
    shutil.copyfile(compiler, selected)
    specification = importlib.util.spec_from_file_location("bootstrap_frontend_pin_control", driver_path)
    driver = importlib.util.module_from_spec(specification)
    original_dont_write_bytecode = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        specification.loader.exec_module(driver)
    finally:
        sys.dont_write_bytecode = original_dont_write_bytecode
    original_stage = driver.stage_modules
    staged = False

    def replace_after_staging(*arguments):
        nonlocal staged
        original_stage(*arguments)
        staged = True
        selected.write_text("#!/bin/sh\nexit 99\n")

    driver.stage_modules = replace_after_staging
    original_argv = sys.argv
    try:
        sys.argv = [str(driver_path), "--compiler-sha256", digest, *frontend_arguments(selected, root, output)]
        try:
            driver.main()
        except ValueError:
            require(staged, "compiler replacement control failed before staging")
        else:
            raise AssertionError("compiler replacement after staging was executed")
    finally:
        sys.argv = original_argv
        driver.stage_modules = original_stage
    for path in (output, raw):
        require(
            (path.read_bytes(), path.stat().st_mtime_ns) == preserved[path],
            "compiler replacement after staging changed generated output",
        )
    for name in ("lexer.au", "expression_arena.au"):
        require(
            (modules / name).read_bytes() == (root / "compiler" / name).read_bytes(),
            "compiler replacement control did not stage the exact exported modules",
        )
    print("PASS compiler pin validation, silent verification, rejection preservation and same-path replacement checks")


def event_generation(root, work):
    source, output = work / "events.au", work / "events.inc"
    command = [sys.executable, "-B", str(root / "scripts/bootstrap_frontend.py"), "--events", str(source), str(output)]
    original = (root / "compiler/lexer.au").read_text()
    original = original.replace("export module aurora.compiler.lexer;", "module aurora.compiler.lexer;", 1).replace(
        "export namespace compiler_lexer {", "namespace compiler_lexer {", 1
    )
    source.write_text(original)
    run(command)
    expected = output.read_bytes()
    require(b"Token = 0," in expected and b"InvalidCursor = 7," in expected, "event wire endpoints changed")
    old_mtime = 1_000_000_000_000_000_000
    os.utime(output, ns=(old_mtime, old_mtime))
    source.write_text(
        original.replace("module aurora.compiler.lexer;", "export module aurora.compiler.lexer;", 1).replace(
            "namespace compiler_lexer {", "export namespace compiler_lexer {", 1
        )
    )
    run(command)
    require(output.read_bytes() == expected, "module visibility changed generated event entries")
    require(output.stat().st_mtime_ns == old_mtime, "unchanged event entries rewrote the output")
    output.write_bytes(b"\xff stale event entries\n")
    os.utime(output, ns=(old_mtime, old_mtime))
    run(command)
    require(output.read_bytes() == expected, "stale event entries were not replaced")
    require(output.stat().st_mtime_ns != old_mtime, "replaced event entries kept the stale mtime")
    source.write_text("enum class Event { second_case, first_case, };")
    run(command)
    require(output.read_text().endswith("    SecondCase = 0,\n    FirstCase = 1,\n"), "event order was not preserved")
    for declaration in (
        "",
        "enum class Event {};",
        "enum class Event { token = 0 };",
        "enum class Event { token, token };",
        "enum class Event { token,, };",
        "enum class Event { Token };",
        "enum class Event { case1, case_1 };",
        "enum class Event { token };\nenum class Event { whitespace };",
    ):
        source.write_text(declaration)
        output.write_bytes(b"preserve on rejection\n")
        result = subprocess.run(command, capture_output=True, timeout=30, check=False)
        require(result.returncode == 1 and b"bootstrap frontend:" in result.stderr, "unsupported Event syntax accepted")
        require(output.read_bytes() == b"preserve on rejection\n", "rejected Event syntax changed output")
    print(
        "PASS generated event ordering, content-stable writes, exported module parity and unsupported-syntax rejection"
    )


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


def private_bootstrap(current1, current2, root, work, ordinary):
    bridge = root / "compiler/hosted_lexer.S"
    entry = "aurora_hosted_lexer_invoke"
    ordinary_unit = work / "ordinary.s"
    ordinary_unit.write_bytes(ordinary + b"\n" + bridge.read_bytes())
    units = [ordinary_unit]
    for number, compiler in enumerate((current1, current2), start=1):
        output = work / f"private-c{number}.s"
        run(
            [
                sys.executable,
                "-B",
                str(root / "scripts/bootstrap_frontend.py"),
                "--compiler-sha256",
                compiler_digest(compiler),
                "--lexer",
                str(compiler),
                str(root / "compiler/lexer.au"),
                str(bridge),
                str(output),
            ]
        )
        units.append(output)
    require(
        units[1].read_bytes() == units[2].read_bytes(),
        "private current C1/C2 lexer bootstrap assembly differs",
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
    for compiler in (current1, current2):
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
    print("PASS current C1/C2 private lexer identity, sole shim export, symbol layouts and unchanged linked code/data")


def frontend_bootstrap(current1, current2, root, work, built_a, built_b):
    entries = {
        "aurora_hosted_lexer_invoke",
        "aurora_hosted_parser_create",
        "aurora_hosted_parser_parse",
        "aurora_hosted_parser_count",
        "aurora_hosted_parser_read",
        "aurora_hosted_parser_edges",
        "aurora_hosted_parser_edge",
        "aurora_hosted_parser_types",
        "aurora_hosted_parser_type",
        "aurora_hosted_parser_release",
    }
    # A is predecessor-generated and need not equal B. Both actual build
    # objects must expose exactly the private host shim contract.
    for unit in (built_a, built_b):
        require(
            set(symbols(unit.with_suffix(".o"), globals_only=True)) == entries,
            f"built frontend leaked a generated symbol or lost a shim: {unit}",
        )
    units = []
    for number, compiler in enumerate((current1, current2), start=1):
        output = work / f"frontend-c{number}.s"
        run(
            [
                sys.executable,
                "-B",
                str(root / "scripts/bootstrap_frontend.py"),
                "--compiler-sha256",
                compiler_digest(compiler),
                *frontend_arguments(compiler, root, output),
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
    for suffix, description in ((".s", "assembly"), (".generated.s", "generated graph"), (".o", "object bytes")):
        regenerated_b = units[0].with_suffix(suffix).read_bytes()
        require(
            regenerated_b == built_b.with_suffix(suffix).read_bytes(),
            f"regenerated frontend B differs from the actual B consumed by current C2: {description}",
        )
        require(
            regenerated_b == units[1].with_suffix(suffix).read_bytes(),
            f"current compiler frontend B/C convergence differs: {description}",
        )
    print(
        "PASS frontend B/C convergence, built-B identity, exact exported module staging and private shim-only exports"
    )


def main():
    current1, current2, root, built_a, built_b = (Path(value).resolve() for value in sys.argv[1:])
    with tempfile.TemporaryDirectory(prefix="hosted-lexer-bootstrap-") as temporary:
        work = Path(temporary)
        compiler_pin_controls(current1, root, work)
        event_generation(root, work)
        outputs = [work / "current-c1.s", work / "current-c2.s"]
        module_root = work / "compiler-modules"
        stage_modules(root, module_root)
        records = []
        corpus = sources(root)
        require(root / "compiler/lexer.au" in corpus, "lexer self-rebuild input is missing")
        require(root / "compiler/expression_parser.au" in corpus, "whole frontend self-rebuild input is missing")
        for source in corpus:
            runs = []
            for compiler, output in zip((current1, current2), outputs, strict=True):
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
                print("PASS current C2 lexer rebuild SHA256 " + hashlib.sha256(outputs[1].read_bytes()).hexdigest())
                private_bootstrap(current1, current2, root, work, outputs[0].read_bytes())
            if source == root / "compiler/expression_parser.au":
                require(runs[0].returncode == 0, "whole frontend self-rebuild failed")
                frontend_bootstrap(current1, current2, root, work, built_a, built_b)
            records.append({"source": str(source.relative_to(root)), "status": runs[0].returncode})
        require(len(records) > 1, "source corpus is empty")
        print(
            "PASS current C1/C2 diagnostics, assembly and output preservation: "
            + json.dumps(
                {
                    "sources": len(records),
                    "accepted": sum(row["status"] == 0 for row in records),
                }
            )
        )


if __name__ == "__main__":
    main()
