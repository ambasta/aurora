#!/usr/bin/env python3
"""Direct-IR native bounded-window oracle, with exact trap PC validation.

All inputs are wrappers in one linked binary: one run checks every in-range
result, and each out-of-range input runs once from argv (native_runner.py).
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse
import tempfile

from native_runner import Freestanding, check_trap, check_words, command, freestanding_glue, observe, run
from native_runner import NativeRunner, Trap, require, symbols_of, worker_count
from readonly_spans import MIN_I64, MAX_I64

# Verified textual IR cases; the aurora-ir-check driver prints their assembly.
AIR = Path(__file__).resolve().parent / "ir" / "readonly-windows-ir" / "abi.air"


def reflection_symbols(directory, encoded, expected, binding):
    path = directory / "reflection-inspect.o"
    path.write_bytes(encoded)
    rows = [line.split() for line in command(["readelf", "--wide", "--symbols", path]).stdout.decode().splitlines()]
    helpers = {
        row[7]: row
        for row in rows
        if len(row) == 8 and "reflect_" in row[7] and (row[7].startswith("aurora_") or row[7].startswith("__au_"))
    }
    require(set(helpers) == set(expected), "object reflection selection differs from expected helpers")
    for name, row in helpers.items():
        require(
            row[3] == "FUNC" and row[4] == binding and row[6] != "UND" and int(row[2]) > 0,
            f"reflection helper {name} has incorrect ELF type, binding, definition or size",
        )
    relocations = command(["readelf", "--wide", "--relocs", path]).stdout.decode().splitlines()
    for line in relocations:
        if "reflect_" in line:
            require(
                "R_X86_64_PLT32" in line and line.rstrip().endswith(" - 4"),
                "reflection call lacks the normal PC-relative call relocation",
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ir_tests", type=Path)
    parser.add_argument("--compiler", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="aurora-window-ir-") as temporary:
        directory = Path(temporary)
        assembly = command([args.ir_tests.resolve(), "--output", AIR, "native"]).stdout.decode()
        values = [11, 128, 255]
        names, expected, wrappers = [], [], []
        for offset in (MIN_I64, -1, 0, 1, 2, 3, 4, MAX_I64):
            for count in (MIN_I64, -1, 0, 1, 2, 3, 4, MAX_I64):
                valid = 0 <= offset <= 3 and 0 <= count <= 3 - offset
                for target, index in [
                    ("window_size", 0),
                    ("window_dynamic", -1),
                    ("window_dynamic", 0),
                    ("window_dynamic", count - 1),
                    ("window_dynamic", count),
                ]:
                    if not MIN_I64 <= index <= MAX_I64:
                        continue
                    number = len(names)
                    names.append(f"{target}({offset},{count},{index})")
                    wrappers.append(
                        f".text\n.globl window_case_{number}\nwindow_case_{number}:\n"
                        f"movabsq ${offset}, %rdi\nmovabsq ${count}, %rsi\nmovabsq ${index}, %rdx\njmp {target}\n"
                    )
                    if valid and (target == "window_size" or 0 <= index < count):
                        expected.append(count if target == "window_size" else values[offset + index])
                    else:
                        expected.append(Trap.BOUNDS)
        entries = [f"window_case_{number}" for number in range(len(names))]
        results = [number for number, value in enumerate(expected) if value is not Trap.BOUNDS]
        traps = [number for number, value in enumerate(expected) if value is Trap.BOUNDS]
        program = directory / "direct-ir.s"
        program.write_text(assembly + "\n" + "".join(wrappers) + freestanding_glue(entries, results, note=True))
        command(["as", "--64", "-L", program, "-o", directory / "direct-ir.o"])
        harness = Freestanding()
        harness.prepare(directory)
        binary = directory / "direct-ir"
        harness.link([directory / "direct-ir.o"], binary)
        check_words(observe(run([binary], 10)), [expected[n] for n in results], [names[n] for n in results])
        symbols = symbols_of(binary)

        def trap(number):
            check_trap(observe(run([binary, number], 10)), Trap.BOUNDS, symbols, names[number])

        with ThreadPoolExecutor(max_workers=worker_count()) as pool:
            list(pool.map(trap, traps))
    window_count = len(names)
    with tempfile.TemporaryDirectory(prefix="aurora-object-ir-") as temporary:
        directory = Path(temporary)
        object_cases = AIR.parent.parent / "ir-tests" / "object.air"
        encoded = command([args.ir_tests.resolve(), "--output", object_cases, "native object values"]).stdout
        names = [
            "object_minimum",
            "object_unsigned",
            "object_division",
            "object_remainder",
            "object_shift",
            "object_loop",
            "object_six_arguments",
            "object_bytes",
            "object_class_array",
            "object_six_bytes",
            "object_literal",
            "object_literal_repeated",
            "object_literal_empty",
            "object_span_arguments",
        ]
        expected = [MIN_I64, (1 << 64) - 1, -42, -1, 8, 21, 21, 128, 42, 21, 127, 128, 0, 42]
        # The same reviewed numeric boundary data is observed as complete 64-bit
        # results from the IR object sink, not inferred from its instruction text.
        for line in (AIR.parent.parent.parent / "emitter_mov.cases").read_text().splitlines():
            if line and not line.startswith("#"):
                kind, value, _, _ = line.split()
                names.append(f"object_constant_{kind}_{value.replace('-', 'n')}")
                expected.append(int(value))
        object_traps = [
            ("object_bounds", Trap.BOUNDS),
            ("object_zero", Trap.ZERO),
            ("object_overflow", Trap.OVERFLOW),
            ("object_count", Trap.COUNT),
            ("object_literal_empty_bounds", Trap.BOUNDS),
        ]
        entries = names + [name for name, _ in object_traps]
        observed, symbols = NativeRunner(directory, None, 10).assemble(encoded, entries, values=range(len(names)))
        check_words(observed, expected, names)
        for index, (name, expected_trap) in enumerate(object_traps, len(names)):
            check_trap(observe(run([directory / "program", index], 10)), expected_trap, symbols, name)
    with tempfile.TemporaryDirectory(prefix="aurora-reflection-object-") as temporary:
        directory = Path(temporary)
        reflected = AIR.parent.parent / "ir-tests" / "reflection-emission.air"
        encoded = command([args.ir_tests.resolve(), "--output", reflected, "native object reflection values"]).stdout
        reflection_names = [
            "reflect_root_size",
            "reflect_root_fields",
            "reflect_unknown",
            "reflect_scoped_size",
            "reflect_scoped_fields",
            "reflect_invisible",
            "reflect_empty",
            "reflect_last_size",
            "reflect_last_fields",
            "reflect_boundary_size",
            "reflect_boundary_invisible",
        ]
        reflection_symbols(
            directory,
            encoded,
            [
                "aurora_reflect_size",
                "aurora_reflect_field_count",
                "__au_reflect_s1_size",
                "__au_reflect_s1_field_count",
                "__au_reflect_s2_size",
                "__au_reflect_s64_size",
                "__au_reflect_s255_size",
                "__au_reflect_s255_field_count",
            ],
            "LOCAL",
        )
        observed, _ = NativeRunner(directory, None, 10).assemble(encoded, reflection_names)
        check_words(observed, [16, 1, 0, 16, 1, 0, 0, 24, 2, 16, 0], reflection_names)
    with tempfile.TemporaryDirectory(prefix="aurora-class-object-") as temporary:
        directory = Path(temporary)
        source = directory / "class_values.au"
        example = Path(__file__).resolve().parents[2] / "examples" / "class_values.au"
        # class_demo's successful branch never calls sample_size. Invoke the
        # actual example's helper explicitly, not merely its compiled body.
        source.write_text(
            example.read_text()
            + """
class HiddenFields {
    i64 secret;
public:
    HiddenFields(i64 value) : secret(value) {}
};
auto sample_size_probe() -> i64 { return sample_size(type_id(Sample)); }
auto sample_fields_probe() -> i64 { return reflect_field_count(type_id(Sample)); }
auto hidden_fields_probe() -> i64 { return reflect_field_count(type_id(HiddenFields)); }
auto hidden_size_probe() -> i64 { return reflect_size(type_id(HiddenFields)); }
auto unknown_size_probe() -> i64 { return sample_size(999999); }
"""
        )
        output = directory / "classes.o"
        command([args.compiler.resolve(), "--emit-object", source, "-o", output])
        reflection_symbols(
            directory, output.read_bytes(), ["aurora_reflect_size", "aurora_reflect_field_count"], "GLOBAL"
        )
        source_names = [
            "class_demo",
            "sample_size_probe",
            "sample_fields_probe",
            "hidden_fields_probe",
            "hidden_size_probe",
            "unknown_size_probe",
        ]
        observed, _ = NativeRunner(directory, None, 10).assemble(output.read_bytes(), source_names)
        check_words(observed, [42, 16, 2, 0, 8, 0], source_names)
    print("PASS direct object reflection: 9 scoped IR values and 6 class example/privacy values")
    print(f"PASS direct object native: {len(names)} values, {len(object_traps)} traps; one object emission and link")
    print(f"PASS readonly window direct IR native: {window_count} cases, {len(traps)} exact bounds traps; one link")


if __name__ == "__main__":
    main()
