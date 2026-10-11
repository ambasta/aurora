#!/usr/bin/env python3
"""Require current compiler frontend convergence and exact source diagnostics."""

from pathlib import Path
from copy import deepcopy
import hashlib
import json
import os
import subprocess
import sys
import tempfile


def stage_modules(root, destination):
    # Import the actual build staging helper: both paths copy exported modules
    # exactly, without rewriting their namespaces or interface declarations.
    sys.path.insert(0, str(root / "scripts"))
    from bootstrap_frontend import stage_modules as stage

    stage(destination, root / "compiler/lexer.au", root / "compiler/syntax_arena.au")


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
        str(root / "compiler/lexer.au"),
        str(root / "compiler/syntax_arena.au"),
        str(root / "compiler/parser.au"),
        str(root / "compiler/hosted_lexer.S"),
        str(root / "compiler/hosted_parser.S"),
        str(output),
    ]


def symbols(path, globals_only=False):
    command = ["nm", "--defined-only", "--format=posix", "--print-size"]
    if globals_only:
        command.append("--extern-only")
    return {row.split()[0]: row.split()[1:] for row in run([*command, str(path)]).decode().splitlines()}


def abi_generation(facts):
    from bootstrap_frontend import abi_declaration, frontend_abi_header

    # An additional copied record and a renamed field need no renderer schema.
    changed = deepcopy(facts)
    symbol, node = abi_declaration(changed, "records", "compiler_parser::AstNode")
    extra = deepcopy(node)
    extra["source_name"] = "fixture::AdditionalRecord"
    extra["fields"][1]["name"] = "_replacement_index"
    changed["records"][symbol + "_fixture"] = extra
    generated = frontend_abi_header(changed)
    require("namespace aurora::hosted_abi::fixture {" in generated, "new record namespace was omitted")
    require("struct alignas(8) AdditionalRecord {" in generated, "new copied record was omitted")
    require("std::int64_t _replacement_index{};" in generated, "Aurora field spelling was not preserved")
    require("i64_type = 1," in generated, "Aurora enum case spelling was not preserved")
    _, nested = abi_declaration(facts, "records", "compiler_parser::TypeResult")
    require(
        "aurora::hosted_abi::compiler_parser::ParseToken next_token{};" in generated
        and nested["fields"][-1]["kind"] == "class",
        "nested copied record was flattened or omitted",
    )
    for kind in ("result_extent", "field_extent", "unsupported_array"):
        changed = deepcopy(facts)
        if kind == "result_extent":
            _, entry = abi_declaration(changed, "functions", "compiler_parser::read_node")
            entry["result"]["bytes"] += 8
        else:
            _, entry = abi_declaration(changed, "records", "compiler_parser::AstNode")
            entry["fields"][1]["bytes" if kind == "field_extent" else "array_length"] += 1
        try:
            frontend_abi_header(changed)
        except ValueError:
            continue
        raise AssertionError(f"unsupported or unsafe ABI facts accepted: {kind}")
    print("PASS generic source-spelled ABI records/enums, nested layout and bridge extent rejection")


def frontend_bootstrap(current1, current2, root, work, built_a, built_b):
    abi_generation(json.loads(built_b.with_suffix(".abi.json").read_text()))
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
        "aurora_hosted_parser_statements",
        "aurora_hosted_parser_statement",
        "aurora_hosted_parser_release",
    }
    # A is predecessor-generated and need not equal B. Both actual build
    # objects must expose exactly the private host shim contract.
    for unit in (built_a, built_b):
        require(
            set(symbols(unit.with_suffix(".o"), globals_only=True)) == entries,
            f"built frontend leaked a generated symbol or lost a shim: {unit}",
        )

    def header(unit):
        return unit.parent / (unit.stem.replace("-", "_") + "_abi.hpp")

    require(
        header(built_a).read_bytes() == header(built_b).read_bytes(),
        "A/B generated layout differs for reused host objects",
    )
    units = []
    for number, compiler in enumerate((current1, current2), start=1):
        output = work / f"frontend-c{number}.s"
        run(
            [
                sys.executable,
                "-B",
                str(root / "scripts/bootstrap_frontend.py"),
                *frontend_arguments(compiler, root, output),
            ]
        )
        units.append(output)
        obj = output.with_suffix(".o")
        run(["as", "--64", str(output), "-o", str(obj)])
        require(set(symbols(obj, globals_only=True)) == entries, "frontend leaked a generated symbol or lost a shim")
        for name in ("lexer.au", "syntax_arena.au"):
            require(
                (work / "compiler-modules/aurora/compiler" / name).read_bytes()
                == (root / "compiler" / name).read_bytes(),
                f"staged compiler module changed exported source: {name}",
            )
    for suffix, description in (
        (".s", "assembly"),
        (".generated.s", "generated graph"),
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
    run(
        [
            sys.executable,
            "-B",
            str(root / "scripts/bootstrap_frontend.py"),
            *frontend_arguments(current1, root, units[0]),
        ]
    )
    require(
        generated_header.read_bytes() == expected and generated_header.stat().st_mtime_ns == old_mtime,
        "unchanged compiler ABI header was rewritten",
    )
    print(
        "PASS generated ABI facts/header and frontend B/C convergence, built-B identity, "
        "exact exported module staging and private shim-only exports"
    )


def main():
    current1, current2, root, built_a, built_b = (Path(value).resolve() for value in sys.argv[1:])
    with tempfile.TemporaryDirectory(prefix="hosted-lexer-bootstrap-") as temporary:
        work = Path(temporary)
        outputs = [work / "current-c1.s", work / "current-c2.s"]
        module_root = work / "compiler-modules"
        stage_modules(root, module_root)
        records = []
        corpus = sources(root)
        require(root / "compiler/lexer.au" in corpus, "lexer self-rebuild input is missing")
        require(root / "compiler/parser.au" in corpus, "whole frontend self-rebuild input is missing")
        for source in corpus:
            runs = []
            for compiler, output in zip((current1, current2), outputs, strict=True):
                output.write_bytes(b"preserve on rejection\n")
                runs.append(
                    subprocess.run(
                        [
                            str(compiler),
                            "--module-root",
                            str(module_root if source == root / "compiler/parser.au" else root / "library"),
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
            if source == root / "compiler/parser.au":
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
