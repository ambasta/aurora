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
HEADERS = ("types.hpp", "ir.hpp", "ir_layout.hpp", "initialization_facts.hpp", "ir_verify.hpp", "x86.hpp")
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

    with tempfile.TemporaryDirectory(prefix="aurora-ir-method-results-native-") as temporary:
        directory = Path(temporary)
        assembly = command([Path(sys.argv[1]).resolve(), "--emit-method-results"]).stdout.decode()
        runner = NativeRunner(directory, None, 5)
        names = ["test", "method_result_header", "method_result_first_array",
                 "method_result_enum", "method_result_bool", "method_source_snapshot",
                 "method_source_header", "method_result_independence", "method_forwarded_result",
                 "method_empty_result", "method_empty_from_result", "method_enum_receiver_read",
                 "method_result_saved_operand"]
        observed, _ = runner.assemble(assembly, names)
        validate_values(observed, [42, 29, 11, 1, 1, 99, 12, 42, 29, 42, 42, 1, 45], names)
        print(f"{len(names)} native enum/composed-method-result IR checks passed "
              "(two-element arrays, enum and empty descendants, constructor snapshots, "
              "independent projection, forwarded receivers and nested hidden-register clobbers)")

    class ByteTrap(Enum):
        ZERO = ".Laurora_division_zero_trap"
        OVERFLOW = ".Laurora_overflow_trap"
        COUNT = ".Laurora_shift_count_trap"

    # Direct IR width tests use Python's unbounded integers, including checks of
    # the full returned 64-bit word. Test input parameters obey the closed source
    # ABI's canonical-u8 contract; wide-to-byte conversions accept wide inputs.
    with tempfile.TemporaryDirectory(prefix="aurora-ir-u8-native-") as temporary:
        directory = Path(temporary)
        assembly = command([Path(sys.argv[1]).resolve(), "--emit-u8"]).stdout.decode()
        runner = NativeRunner(directory, None, 5)
        cases = [("byte_aggregate", (), 42), ("byte_receiver", (), 255),
                 ("byte_local_array", (), 255)]
        edges = (0, 1, 2, 15, 16, 127, 128, 254, 255)
        for a in edges:
            for b in edges:
                results = [a + b, a - b, a * b,
                           a // b if b else ByteTrap.ZERO,
                           a % b if b else ByteTrap.ZERO, a & b, a | b, a ^ b]
                for operation, value in enumerate(results):
                    if isinstance(value, int) and not 0 <= value <= 255:
                        value = ByteTrap.OVERFLOW
                    cases.append((f"byte_op{operation}", (a, b), value))
                for operation, value in enumerate((a == b, a != b, a < b, a > b,
                                                    a <= b, a >= b)):
                    cases.append((f"byte_compare{operation}", (a, b), int(value)))
            for count in (-(1 << 63), -1, 0, 1, 2, 6, 7, 8, 63, 64, (1 << 63) - 1):
                for left in (True, False):
                    if count < 0 or count > 7:
                        value = ByteTrap.COUNT
                    else:
                        value = a << count if left else a >> count
                        if value > 255:
                            value = ByteTrap.OVERFLOW
                    cases.append((f"byte_op{8 if left else 9}", (a, count), value))
        for value in range(256):
            cases.append(("byte_not", (value,), value ^ 255))
            for target in ("u8_to_i64", "u8_to_u64", "i64_to_u8", "u64_to_u8"):
                cases.append((target, (value,), value))
        for target in ("i64_to_u8", "u64_to_u8"):
            for value in (256, 257, 65535, (1 << 63) - 1):
                cases.append((target, (value,), ByteTrap.OVERFLOW))
        for value in (-(1 << 63), -1):
            cases.append(("i64_to_u8", (value,), ByteTrap.OVERFLOW))
        for value in (1 << 63, (1 << 64) - 1):
            cases.append(("u64_to_u8", (value,), ByteTrap.OVERFLOW))

        def byte_wrapper(name, target, arguments):
            registers = ("%rdi", "%rsi")
            lines = ["\n.text", f".globl {name}", f"{name}:"]
            lines += [f"    movabsq ${value}, {registers[index]}"
                      for index, value in enumerate(arguments)]
            lines += [f"    jmp {target}", ""]
            return "\n".join(lines)

        positives = [(target, args, value) for target, args, value in cases
                     if not isinstance(value, ByteTrap)]
        traps = [(target, args, value) for target, args, value in cases
                 if isinstance(value, ByteTrap)]
        for offset in range(0, len(positives), 200):
            batch = positives[offset:offset + 200]
            names = [f"byte_probe_{index}" for index in range(len(batch))]
            wrappers = "".join(byte_wrapper(name, target, args)
                               for name, (target, args, _) in zip(names, batch))
            observed, _ = runner.assemble(assembly + wrappers, names)
            validate_values(observed, [value for _, _, value in batch],
                            [f"{target}{args}" for target, args, _ in batch])
        for target, args, trap in traps:
            wrapper = byte_wrapper("byte_trap_probe", target, args)
            observed, symbols = runner.assemble(assembly + wrapper, ["byte_trap_probe"])
            validate_trap(observed, trap, symbols, f"{target}{args}")
        print(f"{len(cases)} native u8 numerical IR checks passed "
              f"({len(traps)} exact-site traps; every complement/conversion byte, "
              "boundary arithmetic and shifts, canonical results, packed-storage calls/copies)")

    with tempfile.TemporaryDirectory(prefix="aurora-ir-packed-method-native-") as temporary:
        directory = Path(temporary)
        assembly = command([Path(sys.argv[1]).resolve(), "--emit-packed-methods"]).stdout.decode()
        runner = NativeRunner(directory, None, 5)
        names = ["packed_result_array", "packed_result_header", "packed_result_first",
                 "packed_result_enum", "packed_result_bool", "packed_source_array",
                 "packed_source_header", "packed_result_independence", "packed_forwarded_result",
                 "packed_empty_result", "packed_tiny_roundtrip"]
        expected = [42, 29, 11, 1, 1, 99, 12, 42, 29, 42, 128]
        # The private ABI bridge supplies canonical leaves and a pristine result.
        # Nonzero input padding must not be copied as data or clobber its neighbor.
        source_word = 0x7EADBEEF00FF8007
        neighbor = 0x1122334455667788
        for index, (offset, value) in enumerate(((8, 0xFF8007), (16, neighbor), (0, source_word))):
            name = f"packed_record_probe{index}"
            names.append(name)
            expected.append(value)
            assembly += (f"\n.text\n.globl {name}\n{name}:\n"
                         "    subq $40, %rsp\n"
                         f"    movabsq ${source_word}, %rax\n    movq %rax, (%rsp)\n"
                         "    movq $0, 8(%rsp)\n"
                         f"    movabsq ${neighbor}, %rax\n    movq %rax, 16(%rsp)\n"
                         "    leaq (%rsp), %r11\n    leaq 8(%rsp), %r10\n"
                         "    call packed_copy_tiny\n"
                         f"    movq {offset}(%rsp), %rax\n    addq $40, %rsp\n    ret\n")
        observed, _ = runner.assemble(assembly, names)
        validate_values(observed, expected, names)
        print(f"{len(names)} native packed-byte IR checks passed "
              "(mixed alignment, enum and empty descendants, receiver/result hidden registers, "
              "constructor snapshots, nested copies, compact aggregate records and padding isolation)")

    with tempfile.TemporaryDirectory(prefix="aurora-ir-span-native-") as temporary:
        directory = Path(temporary)
        assembly = command([Path(sys.argv[1]).resolve(), "--emit-spans"]).stdout.decode()
        runner = NativeRunner(directory, None, 5)
        names = ["span_local", "span_length", "span_preserve_current", "span_mixed_sum",
                 "span_mixed_first", "span_mixed_last", "span_mixed_saved_operand"]
        observed, _ = runner.assemble(assembly, names)
        validate_values(observed, [128, 3, 255, 299, 31, 77, 1299], names)
        native_count = len(names)
        trap_count = 0
        for index in (0, 1, 2, -1, 3, -(1 << 63), (1 << 63) - 1):
            wrapper = ("\n.text\n.globl ir_span_probe\nir_span_probe:\n"
                       f"    movabsq ${index}, %rdi\n    jmp span_dynamic\n")
            observed, symbols = runner.assemble(assembly + wrapper, ["ir_span_probe"])
            if index in (0, 1, 2):
                validate_values(observed, [(11, 128, 255)[index]], [f"span_dynamic({index})"])
            else:
                validate_trap(observed, ArrayTrap.BOUNDS, symbols, f"span_dynamic({index})")
                trap_count += 1
            native_count += 1
        print(f"{native_count} native readonly-span IR checks passed "
              f"({trap_count} exact-site traps; capability forwarding, six mixed scalar/class/span "
              "positions, class returns, saved operands and bounds before payload access)")
