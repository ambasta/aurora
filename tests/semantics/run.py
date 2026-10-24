#!/usr/bin/env python3
"""Bounded executable-semantics cases with reviewed golden results.

Deterministic families (boundary arithmetic, array bounds, ownership traces,
invalid and truncated sources) are generated below; 128 random programs are
checked in as generated.cases. Every case's expected result (a value, an exact
trap site, or a rejection) is in run.golden. The shared native runner packs
the accepted cases into a few compiled programs and compiles each rejection
once.
"""

import argparse
import itertools
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[0] / "compiler"))
from native_runner import Suite, Trap  # noqa: E402

MIN, MAX = -(1 << 63), (1 << 63) - 1
TRAPS = {"trap overflow": Trap.OVERFLOW, "trap bounds": Trap.BOUNDS}


def source(body):
    return "module semantics; auto test() -> i64 {\n" + body + "\n}\n"


def fixed_cases():
    values = [MIN, MIN + 1, -3037000500, -1, 0, 1, 3037000500, MAX - 1, MAX]
    for op in ["+", "-", "*"]:
        for a, b in itertools.product(values, repeat=2):
            yield f"boundary-{op}-{a}-{b}", source(f"return ({a} {op} {b});")
    for value in values:
        yield f"neg-{value}", source(f"return (-({value}));")
    for n in (1, 2, 8):
        for index in (MIN, -1, 0, n - 1, n, MAX):
            for store in (False, True):
                body = f"array<i64, {n}> a = {{{', '.join(str(i) for i in range(n))}}}; "
                body += f"a[{index}] = 42; return a[{index}];" if store else f"return a[{index}];"
                yield f"bounds-{n}-{index}-{store}", source(body)
    yield (
        "bool-array-loop",
        source(
            "array<bool, 3> a = {true, false, true}; i64 i = 0; i64 x = 0; while (i < 3) { if (!a[i]) { x ="
            " x + 2; } else { x = x + 1; } a[i] = !a[i]; i = i + 1; } if (a[1]) { return x; } return -1;"
        ),
    )


def ownership_cases():
    """All 4^3 operation traces over one owner, then scope release and loop moves."""
    statements = {
        "read": "i64 value{0} = read(owner);",
        "shared": "ref<i64> reference{0} = borrow(owner);",
        "exclusive": "mutref<i64> reference{0} = borrow_mut(owner);",
        "move": "own<i64> moved{0} = move(owner);",
    }
    for trace in itertools.product(statements, repeat=3):
        lines = ["own<i64> owner = own(42);"] + [statements[action].format(i) for i, action in enumerate(trace)]
        yield "ownership-" + "-".join(trace), source(" ".join(lines) + " return 42;")
    for borrow in ("ref<i64> r = borrow(owner);", "mutref<i64> r = borrow_mut(owner);"):
        yield (
            "scope-release-" + borrow.split()[0],
            source("own<i64> owner = own(42); { " + borrow + " } own<i64> moved = move(owner); return read(moved);"),
        )
    for condition in ("true", "false"):
        yield (
            "loop-backedge-" + condition,
            source(f"own<i64> owner = own(42); while ({condition}) {{ own<i64> moved = move(owner); }} return 0;"),
        )
        yield (
            "returning-move-" + condition,
            source(
                f"own<i64> owner = own(42); while ({condition}) {{ own<i64> moved = move(owner);"
                " return read(moved); } return read(owner);"
            ),
        )


def invalid_cases():
    bodies = [
        "bool x = 3; return 0;",
        "i64 x = true; return x;",
        "if (1) { return 0; } return 1;",
        "while (0) {} return 0;",
        "array<i64, 1> a = {0}; return a[false];",
        "array<bool, 1> a = {false}; a[0] = 1; return 0;",
        "const array<i64, 1> a = {0}; a[0] = 1; return 0;",
        "array<i64, 0> a = {}; return 0;",
        "array<i64, 4097> a = {}; return 0;",
        "array<i64, 2> a = {1}; return 0;",
        "return 9223372036854775808;",
        "return -9223372036854775809;",
        "i64 x; return x;",
        "return missing;",
        "return 0; return 1;",
    ]
    for index, body in enumerate(bodies):
        yield f"invalid-type-{index}", source(body)
    complete = source("array<i64, 2> a = {1, 2}; i64 x = 0; while (x < 2) { x = x + 1; } return a[1];").rstrip()
    # Every proper character prefix lacks a complete module/function.
    for index in range(len(complete)):
        yield f"truncated-{index}", complete[:index]
    for index, token in enumerate(["@", "#", "\x00", '"', "'", "`", "\\", "/*", "/* unfinished"]):
        yield f"malformed-token-{index}", source(token + " return 0;")


def generated_cases():
    text = (HERE / "generated.cases").read_text()
    for chunk in text.split("\n// case ")[1:]:
        name, _, body = chunk.partition("\n")
        yield name, body if body.endswith("\n") else body + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    args = parser.parse_args()
    golden = [line.split("\t") for line in (HERE / "run.golden").read_text().splitlines()]
    cases = list(itertools.chain(fixed_cases(), ownership_cases(), invalid_cases(), generated_cases()))
    assert [name for name, _ in cases] == [name for name, _ in golden], "run.golden lists every case in order"
    suite = Suite(args.compiler, "semantics", module_roots=())
    for (name, code), (_, expected) in zip(cases, golden):
        if expected == "reject":
            suite.reject(name, code)
        elif expected in TRAPS:
            suite.check(name, code, TRAPS[expected])
        else:
            kind, value = expected.split(" ")
            assert kind == "value", f"{name}: unknown golden result {expected!r}"
            suite.check(name, code, int(value))
    suite.finish()


if __name__ == "__main__":
    main()
