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
from native_runner import NativeRunner, Trap, symbols_of, worker_count
from readonly_spans import MIN_I64, MAX_I64

# Verified textual IR cases; the aurora-ir-check driver prints their assembly.
AIR = Path(__file__).resolve().parent / "ir" / "readonly-windows-ir" / "abi.air"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ir_tests", type=Path)
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
        ]
        expected = [MIN_I64, (1 << 64) - 1, -42, -1, 8, 21, 21, 128, 42, 21, 127, 128, 0]
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
    print(f"PASS direct object native: {len(names)} values, {len(object_traps)} traps; one object emission and link")
    print(f"PASS readonly window direct IR native: {window_count} cases, {len(traps)} exact bounds traps; one link")


if __name__ == "__main__":
    main()
