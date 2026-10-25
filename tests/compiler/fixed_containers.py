#!/usr/bin/env python3
"""Native source acceptance, rejection, and independent std::array model tests.

The sequence oracle stores ordinary Python lists and predicts every observed
element without consulting compiler IR, assembly, or metadata. Native results
retain all 64 bits and traps must reach the exact named UD2 (native_runner.py);
rejection must be a normal exit 1 and must not create or replace an artifact.

Run: python3 tests/compiler/fixed_containers.py build/aurorac
Optional deterministic stress: --seed 10010 --steps 128
"""

from __future__ import annotations

import argparse
from pathlib import Path
import random

from native_runner import Suite, Trap, require


ROOT = Path(__file__).resolve().parents[2]
SCALARS = ("i64", "u64", "bool")
CAPACITIES = (1, 2, 63, 64)
VALUES = {"i64": -(1 << 63), "u64": (1 << 64) - 1, "bool": True}
OTHERS = {"i64": (1 << 63) - 1, "u64": 1 << 63, "bool": False}


def literal(scalar, value):
    if scalar == "bool":
        return "true" if value else "false"
    return str(value) + ("u64" if scalar == "u64" else "")


def program(body, definitions="", helpers="", library=True, result="i64"):
    return (
        "module app;"
        + ("import std.array;" if library else "")
        + definitions
        + helpers
        + f"auto test()->{result}{{{body}}}"
    )


BUFFER = """template<Scalar T,i64 N>class Buffer {
    builtin::array<T,N> elements;
public:
    Buffer():elements{}{}
    auto at(i64 index)const->T{return elements[index];}
    auto set(i64 index,T value)->T{elements[index]=value;return elements[index];}
    auto size()const->i64{return N;}
};"""


def native_cases(suite):
    for scalar in SCALARS:
        zero = literal(scalar, False if scalar == "bool" else 0)
        value, other = literal(scalar, VALUES[scalar]), literal(scalar, OTHERS[scalar])
        for capacity in CAPACITIES:
            concrete = f"std::array<{scalar},{capacity}>"
            # Visit every initialized element, including the interior of 63/64-word values.
            body = (
                f"{concrete} a={concrete}();const {concrete} empty=a;"
                f"if(a.size()!={capacity}){{return 1;}}"
                f"static_assert(size_of({concrete})=={capacity * 8});"
                f"static_assert(field_count({concrete})==0);"
                f"if(reflect_size(type_id({concrete}))!={capacity * 8}){{return 2;}}"
                f"if(reflect_field_count(type_id({concrete}))!=0){{return 3;}}"
                f"i64 index=0;while(index<a.size()){{"
                f"if(a.at(index)!={zero}){{return 4;}}"
                f"if(a.set(index,{value})!={value}){{return 5;}}index=index+1;}}"
                f"i64 next=0;while(next<a.size()){{"
                f"if(a.at(next)!={value}){{return 6;}}"
                f"if(empty.at(next)!={zero}){{return 7;}}next=next+1;}}return 42;"
            )
            suite.check(f"{scalar} capacity {capacity}: full zero initialization, set, at, size", program(body))
            helpers = (
                f"auto make()->{concrete}{{{concrete} value={concrete}();"
                f"value.set(0,{value});value.set({capacity - 1},{value});return value;}}"
                f"auto select({concrete} a,{concrete} b,{concrete} c,{concrete} d,"
                f"{concrete} e,{concrete} f)->{concrete}{{return f;}}"
            )
            suite.check(
                f"{scalar} capacity {capacity}: six complete snapshots and independent result",
                program(
                    f"const {concrete} original=make();"
                    f"{concrete} copy=select(original,original,original,original,original,original);"
                    f"copy.set({capacity - 1},{other});"
                    f"if(original.at({capacity - 1})!={value}){{return 1;}}"
                    f"if(copy.at({capacity - 1})!={other}){{return 2;}}"
                    f"const {scalar} saved=original.at(0);copy.set(0,{other});"
                    f"if(saved!={value}){{return 3;}}return 42;",
                    helpers=helpers,
                ),
            )
        suite.check(
            f"{scalar} raw result preserves all bits",
            program(
                f"std::array<{scalar},64> a=std::array<{scalar},64>();a.set(63,{value});"
                f"const {scalar} saved=a.at(63);a.set(63,{other});return saved;",
                result=scalar,
            ),
            expected=VALUES[scalar],
        )
        suite.check(
            f"{scalar} all 64 slots reinitialize after reuse",
            program(
                "i64 pass=0;while(pass<3){"
                f"std::array<{scalar},64> a=std::array<{scalar},64>();i64 index=0;"
                f"while(index<a.size()){{if(a.at(index)!={zero}){{return 1;}}"
                f"a.set(index,{value});index=index+1;}}pass=pass+1;}}return 42;"
            ),
        )
        suite.check(
            f"{scalar} independent user template uses the actual N parameter",
            program(
                f"Buffer<{scalar},4> a=Buffer<{scalar},4>();a.set(3,{value});"
                f"if(a.at(0)!={zero}){{return 1;}}if(a.at(3)!={value}){{return 2;}}"
                "return a.size()+38;",
                BUFFER,
                library=False,
            ),
        )
        local_alias = BUFFER.replace(
            "return elements[index];}",
            "array<T,N> local={elements[0],elements[1]};const builtin::array<T,N> copy=local;return copy[index];}",
            1,
        )
        suite.check(
            f"{scalar} dependent local builtin alias and copy",
            program(
                f"Buffer<{scalar},2> a=Buffer<{scalar},2>();a.set(1,{value});return a.at(1);",
                local_alias,
                library=False,
                result=scalar,
            ),
            expected=VALUES[scalar],
        )

    suite.check(
        "private array length query returns a scalar copy",
        program(
            "const Buffer<i64,4> a=Buffer<i64,4>();return a.size()+38;",
            BUFFER.replace("return N;", "return len(elements);"),
            library=False,
        ),
    )

    mixed = """class Mixed {
        i64 head; builtin::array<i64,2> left; builtin::array<u64,3> right;
        builtin::array<bool,2> flags; i64 tail;
    public:
        Mixed():head(19),left{},right{},flags{},tail(23){}
        auto clean()const->bool {
            if(head!=19){return false;}if(tail!=23){return false;}
            if(left[0]!=0){return false;}if(left[1]!=0){return false;}
            if(right[0]!=0u64){return false;}if(right[1]!=0u64){return false;}
            if(right[2]!=0u64){return false;}if(flags[0]!=false){return false;}
            return flags[1]==false;
        }
        auto fill()->i64 {
            left[0]=-9223372036854775808;left[1]=9223372036854775807;
            right[0]=18446744073709551615u64;right[1]=9223372036854775808u64;
            right[2]=42u64;flags[0]=true;flags[1]=false;return head+tail;
        }
        auto intact()const->bool {
            if(head!=19){return false;}if(tail!=23){return false;}
            if(left[0]!=-9223372036854775808){return false;}
            if(left[1]!=9223372036854775807){return false;}
            if(right[0]!=18446744073709551615u64){return false;}
            if(right[1]!=9223372036854775808u64){return false;}
            if(right[2]!=42u64){return false;}if(flags[0]!=true){return false;}
            return flags[1]==false;
        }
        auto clear()->i64{left[0]=0;right[1]=0u64;flags[0]=false;tail=1;return tail;}
    };"""
    suite.check(
        "multiple typed arrays plus leading and trailing scalar offsets",
        program(
            "Mixed a=Mixed();if(!a.clean()){return 1;}if(a.fill()!=42){return 2;}const Mixed b=copy(a);a.clear();"
            "if(b.intact()){return 42;}return 2;",
            mixed,
            "auto copy(Mixed value)->Mixed{return value;}",
            library=False,
        ),
    )

    for count in (33, 34):
        definition = (
            f"class Split{{builtin::array<u64,30> first;builtin::array<bool,{count}> flags;"
            "i64 tail;public:Split():first{},flags{},tail(42){}"
            f"auto set()->i64{{first[29]=18446744073709551615u64;flags[{count - 1}]=true;return tail;}}"
            f"auto get()const->i64{{if(first[29]!=18446744073709551615u64){{return 1;}}"
            f"if(flags[{count - 1}]!=true){{return 2;}}return tail;}}}};"
        )
        suite.check(
            f"multiple array fields flatten to {31 + count} boundary words",
            program(
                "Split a=Split();a.set();const Split b=copy(a);return b.get();",
                definition,
                "auto copy(Split value)->Split{return value;}",
                library=False,
            ),
            error=None if count == 33 else ("64", "boundary", "fields", "words"),
        )

    namespace_array = BUFFER.replace("Buffer", "array")
    suite.check(
        "unqualified array alias cannot be shadowed by namespace template",
        program(
            "return std::answer();",
            "namespace std{" + namespace_array + "auto answer()->i64{array<i64,2> raw={20,22};"
            "builtin::array<i64,2> copied=raw;"
            "static_assert(type_id(array<i64,2>)==type_id(builtin::array<i64,2>));"
            "std::array<i64,2> wrapped=std::array<i64,2>();wrapped.set(1,copied[1]);"
            "return copied[0]+wrapped.at(1);}}",
            library=False,
        ),
        standalone=True,  # Defines the root namespace std; nesting it would change the rule under test.
    )
    suite.check(
        "builtin alias retains original large local capacity",
        program("builtin::array<i64,4096> a={" + ",".join(["0"] * 4095 + ["42"]) + "};return a[4095];", library=False),
    )


def trap_cases(suite):
    for scalar in SCALARS:
        value = literal(scalar, VALUES[scalar])
        for capacity in CAPACITIES:
            concrete = f"std::array<{scalar},{capacity}>"
            for index in (-1, capacity):
                for operation in ("at", "set"):
                    arguments = str(index) + ("," + value if operation == "set" else "")
                    suite.check(
                        f"{scalar} {capacity} {operation} bounds {index}",
                        program(f"{concrete} a={concrete}();a.{operation}({arguments});return 42;"),
                        expected=Trap.BOUNDS,
                    )
    for index in (-(1 << 63), (1 << 63) - 1):
        for operation in ("at", "set"):
            arguments = str(index) + (",42" if operation == "set" else "")
            suite.check(
                f"full signed index {operation} {index}",
                program(f"std::array<i64,64> a=std::array<i64,64>();return a.{operation}({arguments});"),
                expected=Trap.BOUNDS,
            )
    field_store = BUFFER.replace("elements[index]=value;", "elements[index]=1/0;")
    suite.check(
        "private field bounds precede store RHS evaluation",
        program("Buffer<i64,2> a=Buffer<i64,2>();return a.set(2,42);", field_store, library=False),
        expected=Trap.BOUNDS,
    )


def rejection_cases(suite):
    errors = ("array", "scalar", "template", "argument", "literal", "expected", "type")
    for label, concrete in (
        ("zero capacity", "std::array<i64,0>"),
        ("negative capacity", "std::array<i64,-1>"),
        ("capacity 65", "std::array<i64,65>"),
        ("enormous capacity", "std::array<i64,99999999999999999999999999999>"),
        ("u64 capacity", "std::array<i64,4u64>"),
        ("boolean capacity", "std::array<i64,true>"),
        ("expression capacity", "std::array<i64,2+2>"),
        ("parenthesized capacity", "std::array<i64,(4)>"),
        ("hex capacity", "std::array<i64,0x4>"),
        ("type capacity", "std::array<i64,i64>"),
        ("variable capacity", "std::array<i64,n>"),
        ("missing capacity", "std::array<i64>"),
        ("extra capacity", "std::array<i64,4,4>"),
        ("missing scalar", "std::array<4>"),
        ("class element", "std::array<Cell,4>"),
        ("nested class element", "std::array<std::array<i64,1>,4>"),
        ("builtin array element", "std::array<array<i64,1>,4>"),
        ("owner element", "std::array<own<i64>,4>"),
        ("reference element", "std::array<ref<i64>,4>"),
        ("unknown element", "std::array<Missing,4>"),
    ):
        suite.check(
            label, program(f"i64 n=4;return size_of({concrete});", "class Cell{public:i64 value;};"), error=errors
        )

    invalid_fields = (
        ("missing array initialization", "class Bad{builtin::array<i64,2> data;public:Bad(){} };"),
        ("duplicate zero initialization", "class Bad{builtin::array<i64,2> data;public:Bad():data{},data{}{} };"),
        ("nonzero brace initialization", "class Bad{builtin::array<i64,2> data;public:Bad():data{42,0}{} };"),
        ("explicit zero list still unsupported", "class Bad{builtin::array<i64,2> data;public:Bad():data{0,0}{} };"),
        ("parenthesized array initialization", "class Bad{builtin::array<i64,2> data;public:Bad():data(0){} };"),
        ("no implicit array constructor", "class Bad{builtin::array<i64,2> data;};"),
        ("public builtin array field", "class Bad{public:builtin::array<i64,2> data;Bad():data{}{} };"),
        ("public legacy array alias field", "class Bad{public:array<i64,2> data;Bad():data{}{} };"),
        ("array field capacity 65", "class Bad{builtin::array<i64,65> data;public:Bad():data{}{} };"),
        ("array field capacity zero", "class Bad{builtin::array<i64,0> data;public:Bad():data{}{} };"),
        ("nested class rejects array zero initializer", "class Bad{std::array<i64,2> data;public:Bad():data{}{} };"),
        ("nested builtin array field", "class Bad{builtin::array<array<i64,1>,2> data;public:Bad():data{}{} };"),
        ("owning array field", "class Bad{builtin::array<own<i64>,2> data;public:Bad():data{}{} };"),
        ("reference array field", "class Bad{builtin::array<ref<i64>,2> data;public:Bad():data{}{} };"),
        ("slice field", "class Bad{slice<i64> data;public:Bad():data{}{} };"),
        ("scalar field cannot use array zero initializer", "class Bad{i64 value;public:Bad():value{}{} };"),
    )
    for label, definition in invalid_fields:
        suite.check(
            label,
            program("Bad a=Bad();return 42;", definition),
            error=("field", "array", "constructor", "initializer", "expected", "scalar"),
        )

    for label, replacement in (
        ("const private array store", "auto set(i64 index,T value)const->T"),
        ("non-i64 constant parameter", "template<Scalar T,u64 N>"),
        ("reversed parameter order", "template<i64 N,Scalar T>"),
        ("duplicate constant parameter name", "template<Scalar T,i64 T>"),
        ("default constant parameter", "template<Scalar T,i64 N=4>"),
        ("bare constant parameter", "template<i64 N>"),
    ):
        definition = (
            BUFFER.replace("auto set(i64 index,T value)->T", replacement)
            if label.startswith("const")
            else BUFFER.replace("template<Scalar T,i64 N>", replacement)
        )
        suite.check(
            label,
            program("Buffer<i64,4> a=Buffer<i64,4>();return a.set(0,42);", definition, library=False),
            error=("const", "mutable", "template", "parameter", "expected", "duplicate"),
        )
    for label, definition in (
        ("capacity shadowed by scalar field", BUFFER.replace("elements;", "elements;i64 N;")),
        ("capacity shadowed by method", BUFFER.replace("auto size()", "auto N()")),
        ("capacity shadowed by method parameter", BUFFER.replace("i64 index,T value", "i64 index,T N")),
        ("capacity shadowed by constructor parameter", BUFFER.replace("Buffer()", "Buffer(i64 N)")),
        ("capacity shadowed by local", BUFFER.replace("return N;", "i64 N=4;return N;")),
        ("capacity shadowed by nested local", BUFFER.replace("return N;", "{i64 N=4;return N;}")),
        ("capacity assignment", BUFFER.replace("return N;", "N=4;return N;")),
        ("capacity move", BUFFER.replace("return N;", "own<i64> x=move(N);return N;")),
        ("capacity borrow", BUFFER.replace("return N;", "const ref<i64> x=borrow(N);return N;")),
        ("capacity callable", BUFFER.replace("return N;", "return N();")),
        ("capacity used as type", BUFFER.replace("return N;", "N local=4;return 42;")),
    ):
        suite.check(
            label,
            program("Buffer<i64,4> a=Buffer<i64,4>();return a.size();", definition, library=False),
            error=("capacity", "shadow", "parameter", "local", "type", "expected"),
        )
    for label, body in (
        ("implicit private field cannot escape via builtin copy", "array<T,N> local=elements;return local[index];"),
        ("implicit private field cannot be borrowed", "const ref<i64> local=borrow(elements);return elements[index];"),
        ("implicit private field is not scalar", "return elements;"),
    ):
        definition = BUFFER.replace("return elements[index];}", body + "}", 1)
        suite.check(
            label,
            program("Buffer<i64,4> a=Buffer<i64,4>();return a.at(0);", definition, library=False),
            error=("array", "local", "scalar", "own", "field"),
        )
    for declaration in (
        "namespace builtin{}",
        "namespace builtin::extra{}",
        "namespace builtin{class array{};}",
        "class builtin{};",
        "auto builtin()->i64{return 42;}",
    ):
        suite.check(
            "reserved builtin spelling " + declaration,
            program("return 42;", declaration, library=False),
            error=("reserved", "builtin", "namespace"),
        )
    suite.check(
        "malformed container preserves existing output",
        program("std::array<i64,65> a=std::array<i64,65>();return 42;"),
        error=errors,
        existing_output=b"previous known-good assembly\n",
    )


def module_and_budget_cases(suite):
    module = "export module buffers;export " + BUFFER
    helpers = {
        "buffers": module,
        "factory": "export module factory;import buffers;"
        "export auto make()->Buffer<u64,64>{Buffer<u64,64> a=Buffer<u64,64>();"
        "a.set(63,18446744073709551615u64);return a;}",
    }
    suite.check(
        "same specialization unifies across importing modules",
        program(
            "Buffer<u64,64> a=make();const Buffer<u64,64> b=a;return b.at(63);",
            "import buffers;import factory;",
            library=False,
            result="u64",
        ),
        modules=helpers,
        expected=(1 << 64) - 1,
    )
    suite.check(
        "transitive array template import is not public visibility",
        program("Buffer<u64,64> a=make();return 42;", "import factory;", library=False),
        modules=helpers,
        error=("visible", "unknown", "import"),
    )
    for count in (64, 65):
        definitions = "".join(BUFFER.replace("Buffer", f"Buffer{index}") for index in range(count))
        suite.check(
            f"constant-parameter template definition budget {count}",
            program("Buffer0<i64,1> a=Buffer0<i64,1>();return a.set(0,42);", definitions, library=False),
            error=None if count == 64 else ("64", "template limit"),
            standalone=True,  # Exhausts the per-graph template budget by itself.
        )
    for count in (256, 257):
        types = [
            f"{name}<{scalar},{capacity}>"
            for name in ("Left", "Right")
            for scalar in SCALARS
            for capacity in range(1, 65)
        ][:count]
        assertions = "".join(
            f"static_assert(size_of({concrete})=={int(concrete.rsplit(',', 1)[1][:-1]) * 8});" for concrete in types
        )
        definitions = BUFFER.replace("Buffer", "Left") + BUFFER.replace("Buffer", "Right")
        suite.check(
            f"scalar-and-capacity specialization budget {count}",
            program(assertions + "return 42;", definitions, library=False),
            error=None if count == 256 else ("256", "limit", "classes", "specialization"),
            standalone=True,  # Exhausts the per-graph specialization budget by itself.
        )
    suite.check(
        "canonical repeated capacities do not consume specialization budget",
        program(
            "".join(f"static_assert(size_of(Buffer<i64,{('0' * (index % 8))}4>)==32);" for index in range(300))
            + "return 42;",
            BUFFER,
            library=False,
        ),
    )


def model_case(scalar, capacity, seed, steps):
    """Build operations from list state, independent of compiler representation."""
    rng = random.Random(seed)
    state = [False if scalar == "bool" else 0 for _ in range(capacity)]
    concrete = f"std::array<{scalar},{capacity}>"
    body = [f"{concrete} a={concrete}();"]
    edges = (
        {
            "i64": [-(1 << 63), (1 << 63) - 1, -1, 0, 1, 42],
            "u64": [0, 1, 42, 1 << 63, (1 << 64) - 1],
            "bool": [False, True],
        }
    )[scalar]
    for step in range(steps):
        index = rng.randrange(capacity)
        operation = rng.choice(("set", "set", "get", "snapshot"))
        if operation == "get":
            body.append(f"if(a.at({index})!={literal(scalar, state[index])}){{return {100 + step};}}")
            continue
        if scalar == "bool" or rng.randrange(3) == 0:
            value = rng.choice(edges)
        else:
            value = rng.randrange(-(1 << 63), 1 << 63) if scalar == "i64" else rng.randrange(1 << 64)
        if operation == "set":
            state[index] = value
            body.append(
                f"if(a.set({index},{literal(scalar, value)})!={literal(scalar, value)}){{return {100 + step};}}"
            )
        else:
            snapshot = list(state)
            snapshot[index] = value
            body.append(f"{{{concrete} copied=identity(a);copied.set({index},{literal(scalar, value)});")
            for offset, expected in enumerate(snapshot):
                body.append(f"if(copied.at({offset})!={literal(scalar, expected)}){{return {100 + step};}}")
            body.append(f"if(a.at({index})!={literal(scalar, state[index])}){{return {100 + step};}}}}")
    for index, expected in enumerate(state):
        body.append(f"if(a.at({index})!={literal(scalar, expected)}){{return 1000;}}")
    body.append(f"if(a.size()!={capacity}){{return 1001;}}return 42;")
    return program("".join(body), helpers=f"auto identity({concrete} a)->{concrete}{{return a;}}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path, nargs="?", default=ROOT / "build/aurorac")
    parser.add_argument("--seed", type=int, default=10010)
    parser.add_argument("--steps", type=int, default=64)
    args = parser.parse_args()
    require(1 <= args.steps <= 256, "steps must be between 1 and 256")
    suite = Suite(args.compiler, "fixed containers", ignore_case=True)
    suite.load(Path(__file__).with_suffix(".cases"))
    native_cases(suite)
    trap_cases(suite)
    rejection_cases(suite)
    module_and_budget_cases(suite)
    for type_index, scalar in enumerate(SCALARS):
        for capacity in CAPACITIES:
            seed = args.seed + type_index * 1000 + capacity
            suite.check(
                f"independent sequence model {scalar} {capacity}, seed={seed}, steps={args.steps}",
                model_case(scalar, capacity, seed, args.steps),
            )
    suite.finish()


if __name__ == "__main__":
    main()
