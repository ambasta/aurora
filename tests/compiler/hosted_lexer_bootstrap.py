#!/usr/bin/env python3
"""Require current compiler frontend convergence and exact source diagnostics."""

from pathlib import Path
import hashlib
import io
import json
import os
import signal
import subprocess
import sys
import tempfile


def stage_modules(root, destination):
    # Use the shared staging helper, including explicit frontend scaffold expansion.
    sys.path.insert(0, str(root / "scripts"))
    from bootstrap_frontend import stage_modules as stage

    stage(destination, frontend_modules(root))


# Every .au file in compiler/ is a frontend module.
COMPILER_MODULES = tuple(sorted(path.name for path in (Path(__file__).resolve().parents[2] / "compiler").glob("*.au")))
FRONTEND_LIBRARY_MODULES = ("std/decimal_digits.au",)


def frontend_modules(root):
    return [root / "compiler" / name for name in COMPILER_MODULES] + [
        root / "library" / name for name in FRONTEND_LIBRARY_MODULES
    ]


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


def frontend_arguments(compiler, root, output):
    return [
        str(compiler),
        "--output-mode",
        "object",
        "--output",
        str(output),
        *(str(source) for source in frontend_modules(root)),
    ]


def symbols(path, globals_only=False):
    command = ["nm", "--defined-only", "--format=posix", "--print-size"]
    if globals_only:
        command.append("--extern-only")
    return {row.split()[0]: row.split()[1:] for row in run([*command, str(path)]).decode().splitlines()}


def frontend_bootstrap(current1, current2, root, work, built_a, built_b):
    from bootstrap_frontend import write_frontend_header
    from frontend_bridge import render
    from qemu_transport import run_logged

    def regenerate(compiler, output):
        stdout, stderr = io.BytesIO(), io.BytesIO()
        # Reuse owned-process cleanup for the wrapper and its compiler child.
        status = run_logged(
            [
                sys.executable,
                "-B",
                str(root / "scripts/bootstrap_frontend.py"),
                *frontend_arguments(compiler, root, output),
            ],
            stdout,
            stderr=stderr,
            timeout=90,
            timeout_status=False,
        )
        diagnostic = stderr.getvalue()
        require(
            status == 0,
            f"whole frontend self-rebuild failed: {compiler}: {status}: {diagnostic.decode(errors='replace')}",
        )
        require(b"AU9001" not in diagnostic, f"internal compiler failure: {root / 'compiler/frontend.au'}")
        return stdout.getvalue(), diagnostic

    def private_exports(obj):
        # The frontend object exports only its private host shim entries.
        return all(name.startswith("aurora_hosted_") for name in symbols(obj, globals_only=True))

    # A is predecessor-generated and need not equal B.
    for unit in (built_a, built_b):
        require(private_exports(unit.with_suffix(".o")), f"built frontend leaked a generated symbol: {unit}")

    def header(unit):
        return unit.parent / (unit.stem.replace("-", "_") + "_abi.hpp")

    require(
        header(built_a).read_bytes() == header(built_b).read_bytes(),
        "A/B generated layout differs for reused host objects",
    )
    units, diagnostics = [], []
    for number, compiler in enumerate((current1, current2), start=1):
        output = work / f"frontend-c{number}.o"
        diagnostics.append(regenerate(compiler, output))
        units.append(output)
        obj = output.with_suffix(".o")
        require(private_exports(obj), "frontend leaked a generated symbol")
        for name in COMPILER_MODULES:
            require(
                (work / f"frontend-c{number}-modules/aurora/compiler" / name).read_bytes()
                == render((root / "compiler" / name).read_text()).encode(),
                f"staged compiler module changed exported source: {name}",
            )
        for name in FRONTEND_LIBRARY_MODULES:
            require(
                (work / f"frontend-c{number}-modules" / name).read_bytes() == (root / "library" / name).read_bytes(),
                f"staged frontend library module changed exported source: {name}",
            )
    require(diagnostics[0] == diagnostics[1], "whole frontend compiler diagnostics differ")
    for suffix, description in (
        (".generated.o", "direct source object"),
        (".stack.json", "stack facts"),
        (".o", "object bytes"),
        (".abi.json", "ABI facts"),
    ):
        regenerated_b = units[0].with_suffix(suffix).read_bytes()
        require(
            regenerated_b == built_b.with_suffix(suffix).read_bytes(),
            f"regenerated frontend B differs from the actual B consumed by current C2: {description}",
        )
        require(
            regenerated_b == units[1].with_suffix(suffix).read_bytes(),
            f"current compiler frontend B/C convergence differs: {description}",
        )
    require(
        header(units[0]).read_bytes() == header(built_b).read_bytes() == header(units[1]).read_bytes(),
        "generated ABI header convergence differs",
    )
    generated_header = header(units[0])
    expected = generated_header.read_bytes()
    old_mtime = 1_000_000_000_000_000_000
    os.utime(generated_header, ns=(old_mtime, old_mtime))
    # Both real stage compilations and all convergence comparisons above remain
    # mandatory. Header idempotence needs only the writer and those emitted facts,
    # not a third complete compilation of the same frontend.
    emitted_facts = json.loads(units[0].with_suffix(".abi.json").read_text())
    message_sources = (
        root / "compiler/lowering_errors.au",
        root / "compiler/ir_metadata_storage.au",
        root / "compiler/ir_instruction_storage.au",
    )
    write_frontend_header(
        emitted_facts,
        generated_header,
        *message_sources,
        header(built_b),
        verification_source=root / "compiler/ir_verification_errors.au",
    )
    require(
        generated_header.read_bytes() == expected and generated_header.stat().st_mtime_ns == old_mtime,
        "unchanged compiler ABI header was rewritten",
    )
    incompatible = work / "incompatible-shared.hpp"
    incompatible.write_bytes(b"incompatible shared host ABI\n")
    rejected_header = work / "rejected-output.hpp"
    sentinel = b"preserve prior header on incompatible ABI\n"
    rejected_header.write_bytes(sentinel)
    os.utime(rejected_header, ns=(old_mtime, old_mtime))
    try:
        write_frontend_header(
            emitted_facts,
            rejected_header,
            *message_sources,
            incompatible,
            verification_source=root / "compiler/ir_verification_errors.au",
        )
    except ValueError as error:
        require("stage2 ABI header differs" in str(error), "wrong shared-header compatibility rejection")
    else:
        raise AssertionError("incompatible shared-host ABI header was accepted")
    require(
        rejected_header.read_bytes() == sentinel and rejected_header.stat().st_mtime_ns == old_mtime,
        "incompatible shared-host ABI changed an existing header before rejection",
    )
    print(
        "PASS generated ABI facts/header and frontend B/C convergence, built-B identity, "
        "exact exported module staging and private shim-only exports"
    )


def main():
    # Keep fast lexer and whole-frontend convergence independent.
    arguments = sys.argv[1:]
    current1, current2, root, built_a, built_b = (Path(value).resolve() for value in arguments)
    with tempfile.TemporaryDirectory(prefix="hosted-lexer-bootstrap-") as temporary:
        work = Path(temporary)
        outputs = [work / "current-c1.s", work / "current-c2.s"]
        module_root = work / "compiler-modules"
        stage_modules(root, module_root)
        records = []
        corpus = sources(root)
        require(root / "compiler/lexer.au" in corpus, "lexer self-rebuild input is missing")
        require(root / "compiler/frontend.au" in corpus, "whole frontend self-rebuild input is missing")
        compiler_sources = {root / "compiler" / name for name in COMPILER_MODULES}
        compiler_dependency_fixtures = {
            root / "tests/compiler/initialization_probe.au",
        }
        require(compiler_sources.issubset(corpus), "a real compiler module is missing from self-rebuild coverage")
        frontend_library_sources = {root / "library" / name for name in FRONTEND_LIBRARY_MODULES}
        require(
            frontend_library_sources.issubset(corpus), "a frontend library module is missing from self-rebuild coverage"
        )
        convergence = {root / "compiler/lexer.au", root / "compiler/frontend.au"}
        corpus = [source for source in corpus if source in convergence]
        for source in corpus:
            if source == root / "compiler/frontend.au":
                # The dedicated path compiles this graph with local bindings and
                # ABI facts. Lexer and corpus checks retain ordinary emission.
                frontend_bootstrap(current1, current2, root, work, built_a, built_b)
                records.append({"source": str(source.relative_to(root)), "status": 0})
                continue
            runs = []
            for compiler, output in zip((current1, current2), outputs, strict=True):
                output.write_bytes(b"preserve on rejection\n")
                runs.append(
                    subprocess.run(
                        [
                            str(compiler),
                            "--module-root",
                            str(
                                module_root
                                if source in compiler_sources | compiler_dependency_fixtures
                                else root / "library"
                            ),
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
            # Vocabulary/result-only modules have no concrete free function;
            # the complete frontend graph compiles and covers their declarations.
            vocabulary_modules = {"resolution_kinds.au", "lowering_kinds.au", "lowering_errors.au"}
            if source in compiler_sources and source.name not in vocabulary_modules:
                require(runs[0].returncode == 0, f"compiler module self-rebuild failed: {source.name}")
            if source in frontend_library_sources:
                require(runs[0].returncode == 0, f"frontend library module self-rebuild failed: {source.name}")
            records.append({"source": str(source.relative_to(root)), "status": runs[0].returncode})
        require(len(records) > 1, "source corpus is empty")
        print(
            "PASS current C1/C2 lexer and frontend"
            + " diagnostics, assembly and output preservation: "
            + json.dumps(
                {
                    "sources": len(records),
                    "accepted": sum(row["status"] == 0 for row in records),
                }
            )
        )


if __name__ == "__main__":

    def terminate(signum, frame):
        # Let owned-process cleanup finish when Meson's outer deadline expires.
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminate)
    main()
