#!/usr/bin/env python3
"""Run one composer driver; GNU tools provide the reference, never production fallback."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from bootstrap_frontend import (  # noqa: E402
    PASS_ENTRIES,
    abi_function_symbol,
    frontend_bridge,
    frontend_wrapper_recipe,
    encode_frontend_recipes,
    render_frontend_recipes,
)
from meson_aurora_assembly import compose_object_bridge, render_bridge  # noqa: E402


def run(*command, **kwargs):
    return subprocess.run([str(part) for part in command], check=True, timeout=60, **kwargs)


def reference(driver, source, wrapper, selected, actual, directory):
    exposed, combined = directory / "exposed.o", directory / "gnu.o"
    run("objcopy", "--globalize-symbols=" + str(selected), source, exposed)
    run("ld", "-m", "elf_x86_64", "-r", "--build-id=none", exposed, wrapper, "-o", combined)
    run("objcopy", "--localize-symbols=" + str(selected), combined)
    run(driver, "--compare", source, actual, combined)
    return combined


def wrapper_boundaries(driver, directory):
    shapes = []
    for line in (ROOT / "tests/compiler/frontend_wrapper_valid.cases").read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        name, *operations, expected = line.split()
        if expected != "accept":
            raise ValueError("unknown wrapper recipe expectation: " + name)
        shapes.append(tuple(tuple(int(part) for part in operation.split(":")) for operation in operations))
    # One packed recipe reaches both independent bounds. Cases are instruction
    # data; GNU as, rather than a second encoder, remains the byte oracle.
    entries = [
        (
            (f"aurora_hosted_boundary_{index:03}_").ljust(1024, "x"),
            (f"boundary_target_{index:03}_").ljust(1024, "x"),
            shapes[index % len(shapes)],
        )
        for index in range(256)
    ]
    recipe, assembly, reference, actual = (
        directory / name for name in ("boundary.recipe", "boundary.s", "boundary-gnu.o", "boundary-native.o")
    )
    recipe.write_bytes(encode_frontend_recipes(entries))
    assembly.write_text("\n".join(render_frontend_recipes(entries)) + '\n.section .note.GNU-stack,"",@progbits\n')
    run("as", "--64", "-mx86-used-note=no", assembly, "-o", reference)
    run(driver, "--wrapper-boundaries", recipe, reference, actual)
    print("PASS frontend wrapper all transport shapes at 256 rows and 1024-byte names")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("driver", type=Path)
    parser.add_argument("compiler", type=Path)
    parser.add_argument("wrapper", type=Path)
    parser.add_argument("ir_check", type=Path)
    parser.add_argument("--frontend", nargs=3, type=Path, metavar=("SOURCE", "COMPOSED", "FACTS"))
    parser.add_argument("--uart", type=Path, metavar="COMPOSED")
    parser.add_argument("--terminal", type=Path, metavar="COMPOSED")
    args = parser.parse_args()
    args.driver, args.compiler, args.wrapper = (path.resolve() for path in (args.driver, args.compiler, args.wrapper))
    with tempfile.TemporaryDirectory(prefix="aurora-private-object-") as temporary:
        directory = Path(temporary)
        # The source object is the Aurora pipeline's emission of one textual IR case.
        native = directory / "native.o"
        run(args.ir_check.resolve(), "--output", ROOT / "tests/compiler/ir/ir-tests/object.air", "native object values",
            native)
        run(
            args.driver,
            native,
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
        cli = directory / "private-object-cli.o"
        run(args.compiler, "--compose-private-object", source, args.wrapper, selected, "-o", cli)
        if cli.read_bytes() != composed.read_bytes():
            raise RuntimeError("CLI and in-process private object differ")
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
            run("as", "--64", "-mx86-used-note=no", assembly, "-o", wrapper)
            recipe, native_wrapper = directory / "frontend.recipe", directory / "frontend-native.o"
            recipe.write_bytes(frontend_wrapper_recipe(facts))
            run(
                args.driver,
                "--wrapper",
                recipe,
                ROOT / "tests/compiler/frontend_wrapper.cases",
                ROOT / "tests/compiler/frontend_wrapper_elf.cases",
                wrapper,
                raw,
                names,
                native_wrapper,
            )
            wrapper_boundaries(args.driver, directory)
            cli = directory / "frontend-wrapper-cli.o"
            run(args.compiler, "--emit-frontend-wrapper", recipe, "-o", cli)
            if cli.read_bytes() != native_wrapper.read_bytes():
                raise RuntimeError("CLI and in-process frontend wrapper differ")
            reference(args.driver, raw, wrapper, names, actual, directory)
            # The real frontend exceeds the language-source cap. This exercises
            # the distinct artifact read through the actual private CLI.
            run(
                args.compiler,
                "--compose-private-object",
                raw,
                native_wrapper,
                names,
                "-o",
                directory / "frontend-cli.o",
            )
            if (directory / "frontend-cli.o").read_bytes() != actual.read_bytes():
                raise RuntimeError("real frontend private CLI differs from its build artifact")
            print("PASS real frontend emitted wrapper and private composition match GNU and the artifact CLI")
        if args.uart:
            raw, facts_path, assembly, wrapper, names = (
                directory / name for name in ("uart-source.o", "uart.abi.json", "uart.s", "uart.o", "uart.names")
            )
            run(
                args.compiler,
                "--emit-object",
                "--local-symbols",
                "--referenced-reflection-only",
                "--module-root",
                ROOT / "kernel/policies",
                "--abi-facts",
                facts_path,
                ROOT / "examples/kernel-uart.au",
                "-o",
                raw,
            )
            facts = json.loads(facts_path.read_text())
            assembly.write_text(render_bridge((ROOT / "kernel/uart-policy-entry.S").read_text(), facts))
            names.write_text(
                "".join(
                    name + "\n"
                    for name in sorted(
                        abi_function_symbol(facts, entry) for entry in ("uart_initialize", "uart_next", "uart_put")
                    )
                )
            )
            run("as", "--64", "-mx86-used-note=no", assembly, "-o", wrapper)
            reference(args.driver, raw, wrapper, names, args.uart.resolve(), directory)
            run(args.compiler, "--compose-private-object", raw, wrapper, names, "-o", directory / "uart-cli.o")
            if (directory / "uart-cli.o").read_bytes() != args.uart.read_bytes():
                raise RuntimeError("real UART private CLI differs from its build artifact")
            print("PASS real UART private composition matches GNU and the artifact CLI")
        consumers = [("console", "console-service", ("console_service", "aurora_kernel_value"), None)]
        if args.terminal:
            consumers.append(("terminal", "graphical-terminal", ("paint_terminal_cell",), args.terminal.resolve()))
        for label, stem, entries, artifact in consumers:
            raw, facts_path, assembly, wrapper, names = (
                directory / (label + suffix) for suffix in ("-source.o", ".abi.json", ".s", ".o", ".names")
            )
            run(
                args.compiler,
                "--emit-object",
                "--local-symbols",
                "--referenced-reflection-only",
                "--module-root",
                ROOT / "library",
                "--abi-facts",
                facts_path,
                ROOT / ("examples/kernel-" + stem + ".au"),
                "-o",
                raw,
            )
            facts = json.loads(facts_path.read_text())
            bridge = ROOT / ("kernel/uefi/" + stem + "-entry.S")
            assembly.write_text(render_bridge(bridge.read_text(), facts) + '\n.section .note.GNU-stack,"",@progbits\n')
            names.write_text(
                "".join(name + "\n" for name in sorted(abi_function_symbol(facts, entry) for entry in entries))
            )
            run("as", "--64", "-mx86-used-note=no", assembly, "-o", wrapper)
            actual = artifact or directory / (label + "-composed.o")
            if artifact is None:
                actual.write_bytes(raw.read_bytes())
                compose_object_bridge(actual, [bridge], facts, compiler=args.compiler)
            reference(args.driver, raw, wrapper, names, actual, directory)
            cli = directory / (label + "-cli.o")
            run(args.compiler, "--compose-private-object", raw, wrapper, names, "-o", cli)
            if cli.read_bytes() != actual.read_bytes():
                raise RuntimeError("real " + label + " private CLI differs from its bridge-helper artifact")
            print("PASS real " + label + " private composition matches GNU and the artifact CLI")


if __name__ == "__main__":
    main()
