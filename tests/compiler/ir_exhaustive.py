#!/usr/bin/env python3
"""Check fail-closed source verification and emission dispatch.

Temporary copies of the actual Aurora verifier and emitter observe hostile forms
or operators or lose a handler. Source dispatch has runtime rejection, not
compile-time exhaustiveness. The textual IR cases also supply separate native
ABI and exact-trap checks.
"""

from pathlib import Path
import argparse
import subprocess
import sys
import tempfile

from integer_oracle import command

ROOT = Path(__file__).resolve().parents[2]
# Verified textual IR cases; the aurora-ir-check driver prints their assembly.
AIR = ROOT / "tests/compiler/ir/ir-tests/abi.air"


BUILT = {}


def pipeline_probe(bootstrap, directory, args, modules, label):
    """Build a whole probe compiler from the staged, partly mutated module
    copies and the configured driver, linked as aurorac is. Both probes share
    the unchanged build."""
    if label == "unchanged" and label in BUILT:
        return BUILT[label]
    executable = directory / label
    command(
        [
            args.compiler,
            "--emit-object",
            "--runtime-root",
            args.runtime_root,
            "--module-root",
            modules,
            args.driver,
            "-o",
            executable.with_suffix(".o"),
        ],
        timeout=300,
    )
    command(["ld", "-static", "-e", "_start", "-o", executable, executable.with_suffix(".o")], timeout=45)
    BUILT[label] = executable
    return executable


def staged_modules(bootstrap, directory):
    modules = directory / "modules"
    bootstrap.stage_modules(
        modules,
        [
            *sorted(path for path in (ROOT / "compiler").glob("*.au") if path.name != "aurorac.au"),
            ROOT / "library/std/decimal_digits.au",
            ROOT / "library/std/binary.au",
        ],
    )
    return modules


def source_verifier_probes(directory, args):
    # Intentional mutation tests, as in the emitter probe below: a probe
    # compiler whose verifier copy observes a hostile form or lacks a handler;
    # every other module is the unchanged source.
    sys.path.insert(0, str(ROOT / "scripts"))
    import bootstrap_frontend as bootstrap

    directory.mkdir(parents=True)
    modules = staged_modules(bootstrap, directory)
    transfer = modules / "aurora/compiler/ir_verification_transfer.au"
    original_transfer = transfer.read_text()
    inputs = []
    for case, parameters, result, body in (
        ("constant", "", "i64", "return 42;"),
        ("branch", "bool b", "i64", "if (b) { return 42; } return 17;"),
    ):
        path = directory / (case + ".au")
        path.write_text(f"module verification_probe_fixture; auto test({parameters})->{result} {{ {body} }}\n")
        expected = directory / (case + "-expected.s")
        command([args.compiler, path, "-o", expected], timeout=30)
        inputs.append((case, path, expected.read_bytes()))
    for mutation in ("unchanged", "unknown-form", "missing-handler"):
        changed = original_transfer
        if mutation == "unknown-form":
            # Corrupt only the observation inside the real dynamic dispatcher,
            # after immutable instruction admission and CFG normalization.
            dispatcher = "    auto transfer(VerificationWorkspace& w,"
            if changed.count(dispatcher) != 1:
                raise AssertionError("dynamic dispatcher anchor is not unique")
            prefix, separator, body = changed.partition(dispatcher)
            changed = prefix + separator + replace_once(body, "const i64 form = row.form();", "const i64 form = 999;")
        elif mutation == "missing-handler":
            # Remove the actual Constant route while preserving all other routes.
            changed = replace_once(changed, "(form >= 5 && form <= 19)", "(form >= 6 && form <= 19)")
        transfer.write_text(changed)
        executable = pipeline_probe(bootstrap, directory, args, modules, mutation)
        for case, path, expected in inputs:
            for existing in (False, True):
                output = directory / (mutation + "-" + case + "-" + str(existing) + ".s")
                if existing:
                    output.write_bytes(b"preserve this artifact\n")
                observed = subprocess.run([executable, path, "-o", output], capture_output=True, text=True, timeout=5)
                if mutation == "unchanged":
                    if (
                        observed.returncode != 0
                        or observed.stdout
                        or observed.stderr
                        or output.read_bytes() != expected
                    ):
                        raise AssertionError(
                            f"{mutation}/{case}: positive verification control failed: {observed.stderr}"
                        )
                elif (
                    observed.returncode != 1
                    or observed.stdout
                    or observed.stderr != "aurorac: error AU9001: invalid hosted IR verification workspace\n"
                    or (output.read_bytes() != b"preserve this artifact\n" if existing else output.exists())
                ):
                    raise AssertionError(f"{mutation}/{case}: wrong verification rejection: {observed.stderr}")
            print(f"PASS source verifier {mutation}: {case}")


def source_emitter_probes(directory, args):
    # The same probes with the emitter's copies mutated: it observes
    # unknown forms or operators, or loses the scalar family's handler, while
    # admission and verification run unchanged sources.
    sys.path.insert(0, str(ROOT / "scripts"))
    import bootstrap_frontend as bootstrap

    directory.mkdir(parents=True)
    # The constant positive control checks successful handler admission here;
    # packed numeric execution and GNU-reference tests check its value/encoding.
    inputs = {}
    for case, parameters, result, expression, expected in (
        ("constant", "", "i64", "42", ""),
        ("unary", "i64 x", "i64", "-x", "negq %rax"),
        ("binary", "i64 x, i64 y", "i64", "x+y", "addq "),
        ("comparison", "i64 x, i64 y", "bool", "x==y", "sete %al"),
    ):
        path = directory / (case + ".au")
        path.write_text(f"module emitter_probe_fixture; auto test({parameters})->{result} {{ return {expression}; }}\n")
        inputs[case] = (path, expected)
    # Every operator of every scalar family must reach a handler; signed and
    # unsigned operands take different emitter paths. Behaviour is the oracles'.
    operators = [
        ("unary-negate", "i64 x", "i64", "-x"),
        ("unary-not", "bool b", "bool", "!b"),
        ("unary-bitnot", "u64 x", "u64", "~x"),
    ]
    for scalar in ("i64", "u64"):
        for name, symbol in (("add", "+"), ("subtract", "-"), ("multiply", "*"), ("divide", "/"), ("remainder", "%")):
            operators.append((f"binary-{name}-{scalar}", f"{scalar} x, {scalar} y", scalar, f"x{symbol}y"))
        for name, symbol in (("eq", "=="), ("ne", "!="), ("lt", "<"), ("gt", ">"), ("le", "<="), ("ge", ">=")):
            operators.append((f"comparison-{name}-{scalar}", f"{scalar} x, {scalar} y", "bool", f"x{symbol}y"))
    for name, symbol in (("and", "&"), ("or", "|"), ("xor", "^")):
        operators.append((f"binary-{name}-u64", "u64 x, u64 y", "u64", f"x{symbol}y"))
    for name, symbol in (("shl", "<<"), ("shr", ">>")):
        operators.append((f"binary-{name}-u64", "u64 x, i64 n", "u64", f"x{symbol}n"))
    for case, parameters, result, expression in operators:
        path = directory / (case + ".au")
        path.write_text(f"module emitter_probe_fixture; auto test({parameters})->{result} {{ return {expression}; }}\n")
        inputs[case] = (path, "")
    modules = staged_modules(bootstrap, directory)
    emitters = sorted((modules / "aurora/compiler").glob("x86_*.au"))
    originals = {path: path.read_text() for path in emitters}
    scalar = modules / "aurora/compiler/x86_scalar.au"
    for mutation, cases in (
        ("unchanged", tuple(inputs)),
        ("unknown-form", ("constant",)),
        ("unknown-operators", ("unary", "binary", "comparison")),
        ("missing-handler", ("constant",)),
    ):
        for path, text in originals.items():
            changed = text
            if mutation == "unknown-form":
                # Every form the emitter reads, in every emitter module, is unknown.
                changed = text.replace(".form()", ".form() * 0 + 999")
            elif mutation == "unknown-operators":
                for accessor in ("unary_operation", "binary_operation", "comparison_operation"):
                    changed = changed.replace("." + accessor + "()", "." + accessor + "() * 0 + 999")
            path.write_text(changed)
        if mutation == "unknown-form" and all(originals[path] == path.read_text() for path in emitters):
            raise AssertionError("probe mutation found no emitter form read")
        if mutation == "missing-handler":
            # Remove one real family, not an independently enumerated form list.
            prefix, signature = originals[scalar].split("    auto emit_scalar(", 1)
            scalar.write_text(prefix + "    auto emit_scalar(" + signature.split("{", 1)[0] + "{ return false; }\n}\n")
        executable = pipeline_probe(bootstrap, directory, args, modules, mutation)
        for case in cases:
            path, expected = inputs[case]
            for existing in (True,) if mutation == "unchanged" else (False, True):
                output = directory / (mutation + "-" + case + "-" + str(existing) + ".s")
                if existing:
                    output.write_bytes(b"preserve this artifact\n")
                observed = subprocess.run([executable, path, "-o", output], capture_output=True, text=True, timeout=5)
                if mutation == "unchanged":
                    if observed.returncode != 0 or observed.stderr or expected not in output.read_text():
                        raise AssertionError(f"{mutation}/{case}: positive emitter control failed: {observed.stderr}")
                elif (
                    observed.returncode != 1
                    or observed.stdout
                    or observed.stderr != "aurorac: error AU9001: invalid hosted x86 emission transport\n"
                    or (output.read_bytes() != b"preserve this artifact\n" if existing else output.exists())
                ):
                    raise AssertionError(f"{mutation}/{case}: wrong emitter rejection: {observed.stderr}")
            print(f"PASS source emitter {mutation}: {case}")


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise AssertionError("probe mutation anchor is not unique: " + old)
    return source.replace(old, new)


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("ir_tests", type=Path, nargs="?")
parser.add_argument("--compiler", type=Path, required=True)
parser.add_argument("--driver", type=Path, required=True, help="the configured compiler/aurorac.au")
parser.add_argument("--runtime-root", type=Path, required=True)
args = parser.parse_args()


with tempfile.TemporaryDirectory(prefix="aurora-ir-exhaustive-") as scratch:
    source_verifier_probes(Path(scratch) / "verification-dispatch", args)
    source_emitter_probes(Path(scratch) / "emitter-dispatch", args)


# When the direct-IR executable is supplied, exercise the same validated module
# as actual native code. Keep this receipt separate from compile-time exhaustiveness.
if args.ir_tests is not None:
    from enum import Enum
    from integer_oracle import NativeRunner, command, validate_trap, validate_values

    class ArrayTrap(Enum):
        BOUNDS = ".Laurora_bounds_trap"
        RHS_ZERO = ".Laurora_division_zero_trap"

    with tempfile.TemporaryDirectory(prefix="aurora-ir-array-native-") as temporary:
        directory = Path(temporary)
        assembly = command([args.ir_tests.resolve(), "--output", AIR, "array-fields"]).stdout.decode()
        runner = NativeRunner(directory, None, 5)
        names = [
            "test",
            "array_scalar_mapping",
            "array_bool_mapping",
            "array_bool_zero",
            "array_bool_store",
            "array_copy",
        ]
        observed, _ = runner.assemble(assembly, names)
        validate_values(observed, [42, 7, 1, 0, 1, 42], names)
        native_count = len(names)
        trap_count = 0
        for target in ("array_dynamic", "array_store_dynamic"):
            for index in (0, 1, -1, 2, -(1 << 63), (1 << 63) - 1):
                name = f"{target}({index})"
                wrapper = (
                    f"\n.text\n.globl ir_array_probe\nir_array_probe:\n    movabsq ${index}, %rdi\n    jmp {target}\n"
                )
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
        print(
            f"{native_count} native receiver-array IR checks passed "
            f"({trap_count} exact-site traps; scalar mapping, bool stride, zero init, "
            "copy ABI and bounds-before-RHS)"
        )

    with tempfile.TemporaryDirectory(prefix="aurora-ir-composed-native-") as temporary:
        directory = Path(temporary)
        assembly = command([args.ir_tests.resolve(), "--output", AIR, "composed-fields"]).stdout.decode()
        runner = NativeRunner(directory, None, 5)
        names = [
            "test",
            "nested_receiver_projection",
            "nested_scalar_mapping",
            "nested_snapshot_independence",
            "nested_projection_independence",
            "nested_bool_mapping",
            "nested_distinct_receiver_record",
            "nested_empty_copy",
        ]
        observed, _ = runner.assemble(assembly, names)
        validate_values(observed, [42, 42, 12, 9, 42, 1, 36, 42], names)
        print(
            f"{len(names)} native composed-value IR checks passed "
            "(nominal projection, independent snapshots/copies, bool stride, empty values "
            "and distinct receiver/argument records)"
        )

    with tempfile.TemporaryDirectory(prefix="aurora-ir-method-results-native-") as temporary:
        directory = Path(temporary)
        assembly = command([args.ir_tests.resolve(), "--output", AIR, "method-results"]).stdout.decode()
        runner = NativeRunner(directory, None, 5)
        names = [
            "test",
            "method_result_header",
            "method_result_first_array",
            "method_result_enum",
            "method_result_bool",
            "method_source_snapshot",
            "method_source_header",
            "method_result_independence",
            "method_forwarded_result",
            "method_empty_result",
            "method_empty_from_result",
            "method_enum_receiver_read",
            "method_result_saved_operand",
        ]
        observed, _ = runner.assemble(assembly, names)
        validate_values(observed, [42, 29, 11, 1, 1, 99, 12, 42, 29, 42, 42, 1, 45], names)
        print(
            f"{len(names)} native enum/composed-method-result IR checks passed "
            "(two-element arrays, enum and empty descendants, constructor snapshots, "
            "independent projection, forwarded receivers and nested hidden-register clobbers)"
        )

    class ByteTrap(Enum):
        ZERO = ".Laurora_division_zero_trap"
        OVERFLOW = ".Laurora_overflow_trap"
        COUNT = ".Laurora_shift_count_trap"

    # Direct IR width tests use Python's unbounded integers, including checks of
    # the full returned 64-bit word. Test input parameters obey the closed source
    # ABI's canonical-u8 contract; wide-to-byte conversions accept wide inputs.
    with tempfile.TemporaryDirectory(prefix="aurora-ir-u8-native-") as temporary:
        directory = Path(temporary)
        assembly = command([args.ir_tests.resolve(), "--output", AIR, "u8"]).stdout.decode()
        runner = NativeRunner(directory, None, 5)
        cases = [("byte_aggregate", (), 42), ("byte_receiver", (), 255), ("byte_local_array", (), 255)]
        edges = (0, 1, 2, 15, 16, 127, 128, 254, 255)
        for a in edges:
            for b in edges:
                results = [
                    a + b,
                    a - b,
                    a * b,
                    a // b if b else ByteTrap.ZERO,
                    a % b if b else ByteTrap.ZERO,
                    a & b,
                    a | b,
                    a ^ b,
                ]
                for operation, value in enumerate(results):
                    if isinstance(value, int) and not 0 <= value <= 255:
                        value = ByteTrap.OVERFLOW
                    cases.append((f"byte_op{operation}", (a, b), value))
                for operation, value in enumerate((a == b, a != b, a < b, a > b, a <= b, a >= b)):
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
            lines += [f"    movabsq ${value}, {registers[index]}" for index, value in enumerate(arguments)]
            lines += [f"    jmp {target}", ""]
            return "\n".join(lines)

        positives = [(target, args, value) for target, args, value in cases if not isinstance(value, ByteTrap)]
        traps = [(target, args, value) for target, args, value in cases if isinstance(value, ByteTrap)]
        for offset in range(0, len(positives), 200):
            batch = positives[offset : offset + 200]
            names = [f"byte_probe_{index}" for index in range(len(batch))]
            wrappers = "".join(byte_wrapper(name, target, args) for name, (target, args, _) in zip(names, batch))
            observed, _ = runner.assemble(assembly + wrappers, names)
            validate_values(
                observed, [value for _, _, value in batch], [f"{target}{args}" for target, args, _ in batch]
            )
        for target, arguments, trap in traps:
            wrapper = byte_wrapper("byte_trap_probe", target, arguments)
            observed, symbols = runner.assemble(assembly + wrapper, ["byte_trap_probe"])
            validate_trap(observed, trap, symbols, f"{target}{arguments}")
        print(
            f"{len(cases)} native u8 numerical IR checks passed "
            f"({len(traps)} exact-site traps; every complement/conversion byte, "
            "boundary arithmetic and shifts, canonical results, packed-storage calls/copies)"
        )

    with tempfile.TemporaryDirectory(prefix="aurora-ir-packed-method-native-") as temporary:
        directory = Path(temporary)
        assembly = command([args.ir_tests.resolve(), "--output", AIR, "packed-methods"]).stdout.decode()
        runner = NativeRunner(directory, None, 5)
        names = [
            "packed_result_array",
            "packed_result_header",
            "packed_result_first",
            "packed_result_enum",
            "packed_result_bool",
            "packed_source_array",
            "packed_source_header",
            "packed_result_independence",
            "packed_forwarded_result",
            "packed_empty_result",
            "packed_tiny_roundtrip",
        ]
        expected = [42, 29, 11, 1, 1, 99, 12, 42, 29, 42, 128]
        # The private ABI bridge supplies canonical leaves and a pristine result.
        # Nonzero input padding must not be copied as data or clobber its neighbor.
        source_word = 0x7EADBEEF00FF8007
        neighbor = 0x1122334455667788
        for index, (offset, value) in enumerate(((8, 0xFF8007), (16, neighbor), (0, source_word))):
            name = f"packed_record_probe{index}"
            names.append(name)
            expected.append(value)
            assembly += (
                f"\n.text\n.globl {name}\n{name}:\n"
                "    subq $40, %rsp\n"
                f"    movabsq ${source_word}, %rax\n    movq %rax, (%rsp)\n"
                "    movq $0, 8(%rsp)\n"
                f"    movabsq ${neighbor}, %rax\n    movq %rax, 16(%rsp)\n"
                "    leaq (%rsp), %r11\n    leaq 8(%rsp), %r10\n"
                "    call packed_copy_tiny\n"
                f"    movq {offset}(%rsp), %rax\n    addq $40, %rsp\n    ret\n"
            )
        observed, _ = runner.assemble(assembly, names)
        validate_values(observed, expected, names)
        print(
            f"{len(names)} native packed-byte IR checks passed "
            "(mixed alignment, enum and empty descendants, receiver/result hidden registers, "
            "constructor snapshots, nested copies, compact aggregate records and padding isolation)"
        )

    with tempfile.TemporaryDirectory(prefix="aurora-ir-span-native-") as temporary:
        directory = Path(temporary)
        assembly = command([args.ir_tests.resolve(), "--output", AIR, "spans"]).stdout.decode()
        runner = NativeRunner(directory, None, 5)
        names = [
            "span_local",
            "span_length",
            "span_preserve_current",
            "span_mixed_sum",
            "span_mixed_first",
            "span_mixed_last",
            "span_mixed_saved_operand",
        ]
        observed, _ = runner.assemble(assembly, names)
        validate_values(observed, [128, 3, 255, 299, 31, 77, 1299], names)
        native_count = len(names)
        trap_count = 0
        for index in (0, 1, 2, -1, 3, -(1 << 63), (1 << 63) - 1):
            wrapper = (
                f"\n.text\n.globl ir_span_probe\nir_span_probe:\n    movabsq ${index}, %rdi\n    jmp span_dynamic\n"
            )
            observed, symbols = runner.assemble(assembly + wrapper, ["ir_span_probe"])
            if index in (0, 1, 2):
                validate_values(observed, [(11, 128, 255)[index]], [f"span_dynamic({index})"])
            else:
                validate_trap(observed, ArrayTrap.BOUNDS, symbols, f"span_dynamic({index})")
                trap_count += 1
            native_count += 1
        print(
            f"{native_count} native readonly-span IR checks passed "
            f"({trap_count} exact-site traps; capability forwarding, six mixed scalar/class/span "
            "positions, class returns, saved operands and bounds before payload access)"
        )
