#!/usr/bin/env python3
"""Run one composer driver; GNU tools provide the reference, never production fallback."""

import argparse
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from bootstrap_frontend import PASS_ENTRIES, abi_function_symbol, frontend_bridge  # noqa: E402


def run(*command, **kwargs):
    return subprocess.run([str(part) for part in command], check=True, timeout=60, **kwargs)


def reference(driver, source, wrapper, selected, actual, directory):
    exposed, combined = directory / "exposed.o", directory / "gnu.o"
    run("objcopy", "--globalize-symbols=" + str(selected), source, exposed)
    run("ld", "-m", "elf_x86_64", "-r", "--build-id=none", exposed, wrapper, "-o", combined)
    run("objcopy", "--localize-symbols=" + str(selected), combined)
    run(driver, "--compare", source, actual, combined)
    return combined


def cli_checks(compiler, source, wrapper, selected, composed, directory):
    output = directory / "cli.o"
    command = [compiler, "--compose-private-object", source, wrapper, selected, "-o"]
    run(*command, output)
    if output.read_bytes() != composed.read_bytes():
        raise RuntimeError("CLI and in-process composition differ")
    for input_path in (source, wrapper, selected):
        before = input_path.read_bytes()
        alias = directory / "alias"
        os.link(input_path, alias)
        for destination in (input_path, alias):
            result = subprocess.run([*map(str, command), str(destination)], capture_output=True, timeout=20)
            if result.returncode != 1 or input_path.read_bytes() != before:
                raise RuntimeError("CLI input alias accepted or damaged")
        alias.unlink()
    invalid = directory / "invalid.o"
    invalid.write_bytes(b"not an ELF object")
    for previous in (None, b"previous artifact"):
        output.unlink(missing_ok=True)
        if previous is not None:
            output.write_bytes(previous)
        result = subprocess.run(
            [str(compiler), "--compose-private-object", str(invalid), str(wrapper), str(selected), "-o", str(output)],
            capture_output=True,
            timeout=20,
        )
        if result.returncode != 1 or (output.read_bytes() if output.exists() else None) != previous:
            raise RuntimeError("CLI published malformed composition")
    output.write_bytes(b"previous artifact")

    def output_limit():
        signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
        resource.setrlimit(resource.RLIMIT_FSIZE, (1, 1))

    result = subprocess.run([*map(str, command), str(output)], capture_output=True, timeout=20, preexec_fn=output_limit)
    if result.returncode != 1 or output.read_bytes() != b"previous artifact":
        raise RuntimeError("CLI partial write changed the destination")
    if list(directory.glob(".aurora-output-*.tmp")):
        raise RuntimeError("CLI left an abandoned artifact temporary")
    print("PASS private object CLI aliases, rejection and partial-write atomicity")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("driver", type=Path)
    parser.add_argument("compiler", type=Path)
    parser.add_argument("wrapper", type=Path)
    parser.add_argument("--frontend", nargs=3, type=Path, metavar=("SOURCE", "COMPOSED", "FACTS"))
    args = parser.parse_args()
    args.driver, args.compiler, args.wrapper = (path.resolve() for path in (args.driver, args.compiler, args.wrapper))
    with tempfile.TemporaryDirectory(prefix="aurora-private-object-") as temporary:
        directory = Path(temporary)
        run(
            args.driver,
            ROOT / "tests/compiler/ir/ir-tests/object.air",
            ROOT / "tests/compiler/private_object.cases",
            args.wrapper,
            directory,
        )
        source, composed, selected = (directory / name for name in ("source.o", "composed.o", "selected"))
        gnu = reference(args.driver, source, args.wrapper, selected, composed, directory)
        for name, object_path in (("source-composed", composed), ("gnu-composed", gnu)):
            executable = directory / name
            run(
                "ld",
                "-m",
                "elf_x86_64",
                "--build-id=none",
                "-e",
                "aurora_hosted_private_object_test",
                object_path,
                "-o",
                executable,
            )
            run(executable)
        print("PASS private object native local calls, literal relocation and wrapper entry")
        cli_checks(args.compiler, source, args.wrapper, selected, composed, directory)
        if args.frontend:
            raw, actual, facts_path = (path.resolve() for path in args.frontend)
            facts = json.loads(facts_path.read_text())
            assembly, wrapper, names = (directory / name for name in ("frontend.s", "frontend.o", "frontend.names"))
            assembly.write_text(frontend_bridge(None, facts) + '.section .note.GNU-stack,"",@progbits\n')
            names.write_text(
                "".join(
                    name + "\n"
                    for name in sorted(
                        abi_function_symbol(facts, "compiler_frontend::" + alias) for alias in PASS_ENTRIES
                    )
                )
            )
            run("as", "--64", assembly, "-o", wrapper)
            reference(args.driver, raw, wrapper, names, actual, directory)
            # The real frontend exceeds the language-source cap. This exercises
            # the distinct artifact read through the actual private CLI.
            run(args.compiler, "--compose-private-object", raw, wrapper, names, "-o", directory / "frontend-cli.o")
            if (directory / "frontend-cli.o").read_bytes() != actual.read_bytes():
                raise RuntimeError("real frontend private CLI differs from its build artifact")
            print("PASS real frontend private composition matches GNU and the artifact CLI")


if __name__ == "__main__":
    main()
