#!/usr/bin/env python3
"""Prove new, unhandled IR variants fail both trusted consumers at compile time.

Only temporary header copies are modified. Positive controls first compile the
unchanged headers, then an injected variant must trigger the specific exhaustive
visitor assertion, rather than an unrelated C++ error. An optional direct-IR
executable also enables separate native receiver-array ABI and exact-trap checks.
"""
from pathlib import Path
import os
import re
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
COMPILER = shlex.split(os.environ.get("CXX", "g++"))
HEADERS = ("types.hpp", "ir.hpp", "ir_verify.hpp", "x86.hpp")
CONSUMERS = (("ir_verify.hpp", "unhandled typed IR verifier operation"),
             ("x86.hpp", "unhandled typed IR backend operation"))


def compile_probe(directory, header):
    probe = directory / "probe.cpp"
    probe.write_text(f'#include "{header}"\nint main() {{ return 0; }}\n')
    return subprocess.run(COMPILER + ["-std=c++23", "-Werror=switch", "-fsyntax-only", "-I", str(directory), str(probe)],
                          capture_output=True, text=True, timeout=45)


with tempfile.TemporaryDirectory(prefix="aurora-ir-exhaustive-") as temporary:
    directory = Path(temporary)
    for name in HEADERS:
        (directory / name).write_text((ROOT / "compiler" / name).read_text())
    for header, _ in CONSUMERS:
        result = compile_probe(directory, header)
        if result.returncode:
            raise AssertionError(f"{header}: unchanged positive control did not compile:\n{result.stderr}")
        print(f"PASS IR exhaustive unchanged {header} control")
    original = (directory / "ir.hpp").read_text()
    pattern = re.compile(r"(using\s+Instruction\s*=\s*std::variant<)(.*?)(>;)", re.DOTALL)
    if len(pattern.findall(original)) != 1:
        raise AssertionError("could not uniquely locate the Instruction variant for injection")
    injected = pattern.sub(lambda match: "class ExhaustivenessProbe {};\n" + match[1] +
                           match[2] + ", ExhaustivenessProbe" + match[3], original)
    (directory / "ir.hpp").write_text(injected)
    for header, diagnostic in CONSUMERS:
        result = compile_probe(directory, header)
        expected = re.compile(r"static assertion failed[^\n]*" + re.escape(diagnostic))
        if result.returncode == 0 or not expected.search(result.stderr):
            raise AssertionError(f"{header}: missing specific exhaustive-dispatch rejection:\n{result.stderr}")
        print(f"PASS IR exhaustive unknown variant rejected by {header}")
    for enumeration in ("Unary", "Binary", "Comparison"):
        enum_pattern = re.compile(r"(enum class " + enumeration + r"\s*\{)(.*?)(\};)", re.DOTALL)
        if len(enum_pattern.findall(original)) != 1:
            raise AssertionError(f"could not uniquely locate {enumeration} operation enumeration")
        enum_injected = enum_pattern.sub(lambda match: match[1] + match[2].rstrip() +
                                        ", ExhaustivenessProbe " + match[3], original)
        (directory / "ir.hpp").write_text(enum_injected)
        for header, _ in CONSUMERS:
            result = compile_probe(directory, header)
            if result.returncode == 0 or "ExhaustivenessProbe" not in result.stderr or "not handled in switch" not in result.stderr:
                raise AssertionError(f"{header}: missing {enumeration}-enum exhaustive rejection:\n{result.stderr}")
            print(f"PASS IR exhaustive unknown {enumeration} enum rejected by {header}")
print("10 exhaustive IR dispatch checks passed")

# When the direct-IR executable is supplied, exercise the same validated module
# as actual native code. Keep this receipt separate from compile-time exhaustiveness.
if len(sys.argv) > 1:
    from enum import Enum
    from integer_oracle import NativeRunner, command, validate_trap, validate_values

    if len(sys.argv) != 2:
        raise AssertionError("usage: ir_exhaustive.py [path-to-ir-tests]")

    class ArrayTrap(Enum):
        BOUNDS = ".Laurora_bounds_trap"
        RHS_ZERO = ".Laurora_division_zero_trap"

    with tempfile.TemporaryDirectory(prefix="aurora-ir-array-native-") as temporary:
        directory = Path(temporary)
        assembly = command([Path(sys.argv[1]).resolve(), "--emit-array-fields"]).stdout.decode()
        runner = NativeRunner(directory, None, 5)
        names = ["test", "array_scalar_mapping", "array_bool_mapping",
                 "array_bool_zero", "array_bool_store", "array_copy"]
        observed, _ = runner.assemble(assembly, names)
        validate_values(observed, [42, 7, 1, 0, 1, 42], names)
        native_count = len(names)
        trap_count = 0
        for target in ("array_dynamic", "array_store_dynamic"):
            for index in (0, 1, -1, 2, -(1 << 63), (1 << 63) - 1):
                name = f"{target}({index})"
                wrapper = ("\n.text\n.globl ir_array_probe\nir_array_probe:\n"
                           f"    movabsq ${index}, %rdi\n    jmp {target}\n")
                observed, symbols = runner.assemble(assembly + wrapper, ["ir_array_probe"])
                if index not in (0, 1):
                    validate_trap(observed, ArrayTrap.BOUNDS, symbols, name)
                    trap_count += 1
                elif target == "array_store_dynamic":
                    # A valid index reaches the deliberately trapping RHS; an
                    # invalid one above must stop at the bounds site first.
                    validate_trap(observed, ArrayTrap.RHS_ZERO, symbols, name)
                    trap_count += 1
                else:
                    validate_values(observed, [0], [name])
                native_count += 1
        print(f"{native_count} native receiver-array IR checks passed "
              f"({trap_count} exact-site traps; scalar mapping, bool stride, zero init, "
              "copy ABI and bounds-before-RHS)")

    with tempfile.TemporaryDirectory(prefix="aurora-ir-composed-native-") as temporary:
        directory = Path(temporary)
        assembly = command([Path(sys.argv[1]).resolve(), "--emit-composed-fields"]).stdout.decode()
        runner = NativeRunner(directory, None, 5)
        names = ["test", "nested_receiver_projection", "nested_scalar_mapping",
                 "nested_snapshot_independence", "nested_projection_independence",
                 "nested_bool_mapping", "nested_distinct_receiver_record", "nested_empty_copy"]
        observed, _ = runner.assemble(assembly, names)
        validate_values(observed, [42, 42, 12, 9, 42, 1, 36, 42], names)
        print(f"{len(names)} native composed-value IR checks passed "
              "(nominal projection, independent snapshots/copies, bool stride, empty values "
              "and distinct receiver/argument records)")
