#!/usr/bin/env python3
"""Native acceptance and fail-closed tests for bounded inline class composition.

The expected results are source-level values, never compiler metadata or assembly.
Cases are data for the shared native runner (native_runner.py): complete 64-bit
results, exact-site UD2 traps, and rejections that leave inputs and artifacts alone.

Run: python3 tests/compiler/composed_values.py build/aurorac
Optional deterministic stress: --seed 11011 --steps 64
"""

from __future__ import annotations

import argparse
from itertools import product
from pathlib import Path
import random

from native_runner import Suite as NativeSuite, Trap, require


ROOT = Path(__file__).resolve().parents[2]
SCALARS = ("i64", "u64", "bool")
EDGES = {
    "i64": (-(1 << 63), (1 << 63) - 1, -1, 0, 1, 42),
    "u64": (0, 1, 42, 1 << 63, (1 << 64) - 1),
    "bool": (False, True),
}


def literal(scalar, value):
    if scalar == "bool":
        return "true" if value else "false"
    return str(value) + ("u64" if scalar == "u64" else "")


def program(body, definitions="", helpers="", imports="", result="i64"):
    return "module app;" + imports + definitions + helpers + f"auto test()->{result}{{{body}}}"


LEAF = """class Leaf {
    i64 value;
public:
    Leaf(i64 initial):value(initial){}
    auto get()const->i64{return value;}
    auto add(i64 amount)->i64{value=value+amount;return value;}
};"""

WRAP = """class Wrap {
public:
    i64 head;
    Leaf item;
    i64 tail;
    Wrap(i64 a,Leaf source,i64 b):head(a),item(source),tail(b){}
};"""

PAIR = """template<Value T,Value U>class Pair {
public:
    T first;U second;
    Pair(T a,U b):first(a),second(b){}
};"""


def Suite(compiler, label="composed values"):
    """Composed-value suites match diagnostic fragments case-insensitively."""
    return NativeSuite(compiler, label, ignore_case=True)


def scalar_and_library_cases(suite):
    for first, second in product(SCALARS, repeat=2):
        a, b = EDGES[first][-1], EDGES[second][-1]
        concrete = f"std::pair<{first},{second}>"
        suite.check(
            f"Value scalar compatibility {first} {second}",
            program(
                f"const {concrete} source={concrete}({literal(first, a)},{literal(second, b)});"
                f"{concrete} copied=identity(source);"
                f"if(copied.first!={literal(first, a)}){{return 1;}}"
                f"if(copied.second!={literal(second, b)}){{return 2;}}return 42;",
                helpers=f"auto identity({concrete} source)->{concrete}{{return source;}}",
                imports="import std.utility;",
            ),
        )

    imports = "import std.utility;import std.numeric;"
    suite.check(
        "library pair with private MinMax and scalar",
        program(
            "const std::MinMax source=std::minmax(42,0);"
            "const std::pair<std::MinMax,i64> pair=std::pair<std::MinMax,i64>(source,0);"
            "const std::MinMax copy=pair.first;return std::range_width(copy)+pair.second;",
            imports=imports,
        ),
    )
    suite.check(
        "library class in second field with preceding u64",
        program(
            "const std::MinMax source=std::minmax(42,0);"
            "const std::pair<u64,std::MinMax> pair=std::pair<u64,std::MinMax>(18446744073709551615u64,source);"
            "const std::MinMax copy=pair.second;"
            "if(pair.first!=18446744073709551615u64){return 1;}return std::range_width(copy);",
            imports=imports,
        ),
    )
    suite.check(
        "two distinct library class fields retain independent private state",
        program(
            "std::Accumulator source=std::Accumulator(20);const std::MinMax limits=std::minmax(0,20);"
            "const std::pair<std::MinMax,std::Accumulator> pair=std::pair<std::MinMax,std::Accumulator>(limits,source);"
            "source.add(99);std::Accumulator copy=pair.second;copy.add(2);"
            "const std::Accumulator original=pair.second;const std::MinMax bounds=pair.first;"
            "if(original.value()!=20){return 1;}return copy.value()+std::range_width(bounds);",
            imports=imports,
        ),
    )
    suite.check(
        "class-valued specialization identity includes ordered arguments",
        program(
            "static_assert(type_id(std::pair<std::MinMax,i64>)!=type_id(std::pair<i64,std::MinMax>));"
            "static_assert(type_id(std::pair<std::Accumulator,i64>)!=type_id(std::pair<i64,std::Accumulator>));"
            "static_assert(size_of(std::pair<std::MinMax,i64>)==24);"
            "static_assert(field_count(std::pair<std::MinMax,i64>)==2);"
            "if(reflect_size(type_id(std::pair<std::MinMax,i64>))!=24){return 1;}"
            "if(reflect_field_count(type_id(std::pair<std::MinMax,i64>))!=2){return 2;}return 42;",
            imports=imports,
        ),
    )
    suite.check(
        "single Value parameter supports a named concrete class",
        program(
            "Leaf source=Leaf(42);Box<Leaf> value=Box<Leaf>(source);const Leaf copy=value.item;return copy.get();",
            LEAF + "template<Value T>class Box{public:T item;Box(T source):item(source){} };",
        ),
    )
    for constraint, concrete, construction, projection in (
        ("Scalar T,Value U", "Mixed<i64,Leaf>", "0,source", "second"),
        ("Value T,Scalar U", "Mixed<Leaf,i64>", "source,0", "first"),
    ):
        suite.check(
            "mixed constraints " + constraint,
            program(
                f"Leaf source=Leaf(42);{concrete} value={concrete}({construction});"
                f"const Leaf copy=value.{projection};return copy.get();",
                LEAF + PAIR.replace("Value T,Value U", constraint).replace("Pair", "Mixed"),
            ),
        )
    suite.check(
        "Value remains usable as an ordinary contextual class name",
        program(
            "Value source=Value{.value=42};Box<Value> outer=Box<Value>(source);"
            "const Value copy=outer.item;return copy.value;",
            "class Value{public:i64 value;};template<Value T>class Box{public:T item;Box(T source):item(source){} };",
        ),
    )
    suite.check(
        "qualified and local class arguments reuse one specialization",
        program(
            "geometry::Leaf source=geometry::Leaf(42);geometry::Box<geometr"
            "y::Leaf> value=geometry::Box<geometry::Leaf>(source);"
            "const geometry::Box<geometry::Leaf> copy=geometry::identity(value);"
            "const geometry::Leaf inner=copy.item;"
            "if(type_id(geometry::Box<geometry::Leaf>)!=geometry::identity_id()){return 1;}return inner.get();",
            "namespace geometry{" + LEAF + "template<Value T>class Box{public:T item;Box(T source):item(source){} };"
            "auto identity(Box<Leaf> source)->Box<Leaf>{return source;}"
            "auto identity_id()->i64{return type_id(Box<Leaf>);}}",
        ),
    )


def native_copy_cases(suite):
    definitions = LEAF + WRAP
    body = (
        "Leaf source=Leaf(20);Wrap original=Wrap(7,source,15);"
        "source.add(79);Wrap outer=original;Leaf inner=outer.item;inner.add(2);"
        "const Leaf stored=original.item;const Leaf untouched=outer.item;"
        "if(source.get()!=99){return 1;}if(stored.get()!=20){return 2;}"
        "if(untouched.get()!=20){return 3;}return inner.get()+outer.head+outer.tail-2;"
    )
    suite.check(
        "chained method call", program("Leaf source=Leaf(42);Wrap w=Wrap(0,source,0);return w.item.get();", LEAF + WRAP)
    )
    suite.check(
        "chained mutable method",
        program("Leaf source=Leaf(42);Wrap w=Wrap(0,source,0);return w.item.add(1);", LEAF + WRAP),
        expected=43,
    )
    suite.check(
        "whole nested field assignment",
        program("Leaf source=Leaf(42);Wrap w=Wrap(0,source,0);w.item=source;return 42;", LEAF + WRAP),
    )
    suite.check("constructor copy and public-field extraction are independent", program(body, definitions))
    suite.check(
        "composed value ordinary parameter and complete return",
        program(
            "Leaf source=Leaf(20);Wrap original=Wrap(7,source,15);Wrap copied=identity(original);"
            "copied.head=99;const Leaf value=copied.item;"
            "if(original.head!=7){return 1;}return value.get()+original.head+original.tail;",
            definitions,
            "auto identity(Wrap source)->Wrap{return source;}",
        ),
    )
    suite.check(
        "copy public class field from readonly value parameter",
        program(
            "Leaf source=Leaf(20);Wrap value=Wrap(7,source,15);return consume(value);",
            definitions,
            "auto consume(Wrap source)->i64{const Leaf value=source.item;return value.get()+source.head+source.tail;}",
        ),
    )
    suite.check(
        "factory result survives local frame and reinitialization loop",
        program(
            "i64 pass=0;i64 sum=0;while(pass<6){const Wrap value=make(pass);"
            "const Leaf inner=value.item;sum=sum+inner.get();pass=pass+1;}return sum;",
            definitions,
            "auto make(i64 input)->Wrap{Leaf source=Leaf(input);Wrap result=Wrap(100,source,200);return result;}",
        ),
        expected=15,
    )
    suite.check(
        "six mixed ordinary arguments preserve nested storage",
        program(
            "Leaf source=Leaf(20);Wrap value=Wrap(1,source,0);return consume(value,1,value,2,value,-1);",
            definitions,
            "auto consume(Wrap a,i64 b,Wrap c,i64 d,Wrap e,i64 f)->i64{"
            "const Leaf x=a.item;const Leaf y=c.item;const Leaf z=e.item;"
            "return x.get()+y.get()+z.get()+b+d+f-20;}",
        ),
    )
    suite.check(
        "composed result chooses complete branch",
        program(
            "Wrap value=choose(false);const Leaf inner=value.item;return inner.get();",
            definitions,
            "auto choose(bool first)->Wrap{Leaf a=Leaf(1);Wrap early=Wrap(0,a,0);if(first){return early;}"
            "Leaf b=Leaf(42);Wrap late=Wrap(0,b,0);return late;}",
        ),
    )
    suite.check(
        "result may shadow source only after argument snapshot",
        program(
            "Leaf inner=Leaf(20);Wrap value=Wrap(10,inner,12);{Wrap value=identity(value);"
            "const Leaf item=value.item;return item.get()+value.head+value.tail;}",
            definitions,
            "auto identity(Wrap value)->Wrap{return value;}",
        ),
    )
    suite.check(
        "ordinary function recursion preserves composed values",
        program(
            "Leaf source=Leaf(20);Wrap original=Wrap(1,source,0);Wrap result=step(original,21);"
            "const Leaf nested=result.item;return nested.get()+result.head;",
            definitions,
            "auto step(Wrap source,i64 remaining)->Wrap{if(remaining==0){return source;}"
            "Wrap local=source;local.head=local.head+1;Wrap result=step(local,remaining-1);return result;}",
        ),
    )
    for scalar in SCALARS:
        value = {"i64": -(1 << 63), "u64": (1 << 64) - 1, "bool": True}[scalar]
        definition = (
            f"class Bits{{{scalar} value;public:Bits({scalar} x):value(x){{}}"
            f"auto get()const->{scalar}{{return value;}}}};" + PAIR
        )
        suite.check(
            f"nested {scalar} raw return preserves bits",
            program(
                f"Bits bits=Bits({literal(scalar, value)});Pair<i64,Bits> pair=Pair<i64,Bits>(0,bits);"
                f"const Bits copy=pair.second;return copy.get();",
                definition,
                result=scalar,
            ),
            expected=value,
        )

    private = """class Private {
        Leaf item;
    public:
        Private(Leaf source):item(source){}
        auto get()const->i64{const Leaf copy=item;return copy.get();}
        auto changed()const->i64{Leaf copy=item;return copy.add(2);}
    };"""
    suite.check(
        "private nested receiver field projects into independent method local",
        program(
            "Leaf source=Leaf(20);Private value=Private(source);"
            "if(value.changed()!=22){return 1;}return value.get()+value.changed();",
            LEAF + private,
        ),
    )
    suite.check(
        "ordinary field and constructor accept concrete array specialization",
        program(
            "std::array<u64,2> source=std::array<u64,2>();source.set(1,18446744073709551615u64);"
            "ArrayWrap value=ArrayWrap(source);source.set(1,0u64);ArrayWrap returned=identity(value);"
            "std::array<u64,2> copy=returned.item;copy.set(0,42u64);"
            "const std::array<u64,2> original=value.item;"
            "if(original.at(0)!=0u64){return 1;}if(copy.at(1)!=184467440737"
            "09551615u64){return 2;}return i64(copy.at(0));",
            "class ArrayWrap{public:std::array<u64,2> item;ArrayWrap(std::array<u64,2> source):item(source){} };",
            "auto identity(ArrayWrap source)->ArrayWrap{return source;}",
            imports="import std.array;",
        ),
    )


def field_count_cases(suite):
    empty = "class Empty{public:Empty(){}};"
    for count in (8191, 8192):
        fields = "".join(f"Empty f{index};" for index in range(count))
        initializers = ",".join(f"f{index}(e)" for index in range(count))
        declaration = f"class Fields{{{fields}public:Fields(Empty e):{initializers}{{}}}};"
        parent = "class Parent{Fields child;public:Parent(Fields value):child(value){} };"
        suite.check(
            f"{count} empty direct fields retain nested constructor completion",
            program(
                "Empty e=Empty();Fields value=Fields(e);Parent nested=Parent(value);return 42;",
                empty + declaration + parent,
            ),
        )
    suite.check(
        "last empty field still needs initialization at the direct-field cap",
        program("return 42;", empty + declaration.replace(",f8191(e)", "")),
        error="constructor must initialize",
    )
    # Keep the source boundary here; initialization-facts also rejects 73,729 raw fields.
    fields = "".join(f"Empty f{index};" for index in range(8193))
    suite.check(
        "oversized no-leaf child with 8193 fields rejects before receiver allocation",
        program("return 42;", empty + f"class Child{{{fields}}};class Parent{{Child child;}};"),
        error="class exceeds 8192 direct fields",
        existing_output=b"preserve prior output",
    )


def empty_class_cases(suite):
    empty = "class Empty{public:Empty(){}auto answer()const->i64{return 42;}};"
    holder = "class Holder{public:Empty item;Holder(Empty source):item(source){} };"
    suite.check(
        "empty nested value remains complete through constructor projection and ABI",
        program(
            "Empty original=Empty();Holder value=Holder(original);Holder copied=identity(value);"
            "const Empty projected=copied.item;const Empty returned=empty_identity(projected);"
            "static_assert(size_of(Empty)==8);static_assert(size_of(Holder)==8);"
            "static_assert(field_count(Holder)==1);return returned.answer();",
            empty + holder,
            "auto identity(Holder source)->Holder{return source;}"
            "auto empty_identity(Empty source)->Empty{return source;}",
        ),
    )
    suite.check(
        "two empty fields initialize and project as distinct logical fields",
        program(
            "Empty a=Empty();Empty b=Empty();Pair<Empty,Empty> value=Pair<Empty,Empty>(a,b);"
            "const Pair<Empty,Empty> result=identity(value);const Empty first=result.first;"
            "const Empty second=result.second;static_assert(size_of(Pair<Empty,Empty>)==8);"
            "static_assert(field_count(Pair<Empty,Empty>)==2);return first.answer()+second.answer()-42;",
            empty + PAIR,
            "auto identity(Pair<Empty,Empty> source)->Pair<Empty,Empty>{return source;}",
        ),
    )
    suite.check(
        "empty field does not shift neighboring scalar payload",
        program(
            "Empty source=Empty();Mixed value=Mixed(19,source,23);const Mixed result=identity(value);"
            "const Empty copy=result.item;if(copy.answer()!=42){return 1;}"
            "static_assert(size_of(Mixed)==16);return result.head+result.tail;",
            empty + "class Mixed{public:i64 head;Empty item;i64 tail;"
            "Mixed(i64 a,Empty source,i64 b):head(a),item(source),tail(b){} };",
            "auto identity(Mixed source)->Mixed{return source;}",
        ),
    )
    suite.check(
        "empty constructor snapshot survives repeated loop lifetimes",
        program(
            "i64 index=0;i64 total=0;while(index<3){Empty source=Empty();Holder value=Holder(source);"
            "Holder result=identity(value);const Empty copy=result.item;total=total+copy.answer();index=index+1;}"
            "return total;",
            empty + holder,
            "auto identity(Holder value)->Holder{return value;}",
        ),
        expected=126,
    )
    for label, initializer in (
        ("missing", ""),
        ("empty braces", ":item{}"),
        ("duplicate", ":item(source),item(source)"),
    ):
        suite.check(
            "empty child still requires exactly one initialization: " + label,
            program("return 42;", empty + f"class Bad{{Empty item;public:Bad(Empty source){initializer}{{}} }};"),
            error=True,
        )
    suite.check(
        "empty siblings are not interchangeable constructor arguments",
        program(
            "Other source=Other();Holder value=Holder(source);return 42;",
            empty + empty.replace("Empty", "Other") + holder,
        ),
        error=True,
    )
    suite.check(
        "empty siblings are not interchangeable projections",
        program(
            "Empty source=Empty();Holder value=Holder(source);Other copy=value.item;return 42;",
            empty + empty.replace("Empty", "Other") + holder,
        ),
        error=True,
    )
    for depth in (4, 5):
        definitions = empty
        body = "Empty source1=Empty();"
        previous = "Empty"
        for level in range(2, depth + 1):
            current = f"Empty{level}"
            definitions += f"class {current}{{public:{previous} item;{current}({previous} source):item(source){{}}}};"
            body += f"{current} source{level}={current}(source{level - 1});"
            previous = current
        suite.check(
            f"zero-leaf composition still enforces class-depth {depth}",
            program(body + f"static_assert(size_of({previous})==8);return 42;", definitions),
            error=None if depth == 4 else ("depth", "four", "4"),
        )


def snapshot_cases(suite):
    definitions = LEAF + WRAP + PAIR
    suite.check(
        "constructor snapshots class before later scalar mutation",
        program(
            "Leaf source=Leaf(20);Wrap value=Wrap(0,source,source.add(2));"
            "const Leaf snapshot=value.item;return snapshot.get()+value.tail;",
            definitions,
        ),
    )
    suite.check(
        "constructor snapshots class after earlier scalar mutation",
        program(
            "Leaf source=Leaf(20);Wrap value=Wrap(source.add(2),source,0);"
            "const Leaf snapshot=value.item;return snapshot.get()+value.head-2;",
            definitions,
        ),
    )
    repeated = """class Repeated{public:Leaf first;i64 observed;Leaf second;
        Repeated(Leaf a,i64 middle,Leaf b):first(a),observed(middle),second(b){}
    };"""
    suite.check(
        "same constructor source creates separate left-to-right snapshots",
        program(
            "Leaf source=Leaf(20);Repeated value=Repeated(source,source.add(2),source);"
            "Leaf a=value.first;Leaf b=value.second;a.add(100);"
            "const Leaf saved=value.first;if(saved.get()!=20){return 1;}"
            "if(b.get()!=22){return 2;}if(value.observed!=22){return 3;}return saved.get()+b.get();",
            definitions + repeated,
        ),
    )
    reversed_initializers = repeated.replace(
        "first(a),observed(middle),second(b)", "second(b),observed(middle),first(a)"
    )
    suite.check(
        "declaration order cannot change constructor argument snapshots",
        program(
            "Leaf source=Leaf(20);Repeated value=Repeated(source,source.add(2),source);"
            "const Leaf a=value.first;const Leaf b=value.second;return a.get()+b.get();",
            definitions + reversed_initializers,
        ),
    )
    suite.check(
        "constructor snapshot cannot be overwritten by later class-return call",
        program(
            "Leaf source=Leaf(20);Wrap value=Wrap(0,source,clobber());"
            "const Leaf snapshot=value.item;return snapshot.get()+value.tail;",
            definitions,
            "auto make()->Leaf{Leaf local=Leaf(999);return local;}"
            "auto clobber()->i64{Leaf temporary=make();return temporary.get()-977;}",
        ),
    )
    suite.check(
        "scalar field mutation after class-field copy cannot alter snapshot",
        program(
            "Leaf source=Leaf(20);Wrap value=Wrap(0,source,0);"
            "const Leaf first=value.item;value.head=999;Leaf second=value.item;second.add(2);"
            "return first.get()+second.get();",
            definitions,
        ),
    )
    suite.check(
        "constructor class parameter supports readonly scalar observations",
        program(
            "Leaf source=Leaf(20);Observed value=Observed(source);const Leaf copy=value.item;"
            "if(copy.get()!=20){return 1;}return value.head+value.tail;",
            LEAF + "class Observed{public:i64 head;Leaf item;i64 tail;"
            "Observed(Leaf source):head(source.get()),item(source),tail(source.get()+2){} };",
        ),
    )


def storage_class(name, scalar, capacity):
    return (
        f"class {name}{{{scalar} head;builtin::array<{scalar},{capacity}> data;{scalar} tail;public:"
        f"{name}({scalar} a,{scalar} b):head(a),data{{}},tail(b){{}}"
        f"auto at(i64 index)const->{scalar}{{return data[index];}}"
        f"auto set(i64 index,{scalar} value)->{scalar}{{data[index]=value;return data[index];}}"
        f"auto first()const->{scalar}{{return head;}}auto last()const->{scalar}{{return tail;}}}};"
    )


def array_and_model_cases(suite, seed, steps):
    for scalar in SCALARS:
        for capacity in (1, 2, 61):
            edges = EDGES[scalar]
            a, b = edges[0], edges[-1]
            definitions = storage_class("Storage", scalar, capacity) + PAIR
            concrete = "Pair<Storage,i64>"
            suite.check(
                f"nested {scalar} array {capacity}: full zero and complete boundary copy",
                program(
                    f"Storage source=Storage({literal(scalar, a)},{literal(scalar, b)});"
                    f"i64 index=0;while(index<{capacity}){{if(source.at(index)!={literal(scalar, 0)}){{return 1;}}"
                    f"source.set(index,{literal(scalar, b)});index=index+1;}}"
                    f"{concrete} original={concrete}(source,42);{concrete} result=identity(original);"
                    f"Storage copy=result.first;source.set({capacity - 1},{literal(scalar, a)});"
                    f"if(copy.first()!={literal(scalar, a)}){{return 2;}}"
                    f"if(copy.last()!={literal(scalar, b)}){{return 3;}}"
                    f"i64 next=0;while(next<{capacity}){{if(copy.at(next)!="
                    f"{literal(scalar, b)}){{return 4;}}next=next+1;}}"
                    f"static_assert(size_of({concrete})=={(capacity + 3) * 8});"
                    f"static_assert(field_count({concrete})==2);return result.second;",
                    definitions,
                    f"auto identity({concrete} value)->{concrete}{{return value;}}",
                ),
            )

        rng = random.Random(seed + SCALARS.index(scalar) * 1000)
        capacity = 5
        state = [0] * capacity
        body = [f"Storage source=Storage({literal(scalar, EDGES[scalar][0])},{literal(scalar, EDGES[scalar][-1])});"]
        for step in range(steps):
            index = rng.randrange(capacity)
            value = rng.choice(EDGES[scalar])
            if step % 3 == 0:
                state[index] = value
                body.append(f"source.set({index},{literal(scalar, value)});")
            else:
                snapshot = list(state)
                body.append(
                    "{const Pair<Storage,i64> original=Pair<Storage,i64>(source,42);"
                    "const Pair<Storage,i64> returned=identity(original);Storage copied=returned.first;"
                )
                body.append(f"copied.set({index},{literal(scalar, value)});")
                changed = list(snapshot)
                changed[index] = value
                for offset in range(capacity):
                    body.append(
                        f"if(copied.at({offset})!={literal(scalar, changed[offset])}){{return {100 + step};}}"
                        f"if(source.at({offset})!={literal(scalar, snapshot[offset])}){{return {200 + step};}}"
                    )
                body.append("const Storage untouched=original.first;")
                for offset in range(capacity):
                    body.append(
                        f"if(untouched.at({offset})!={literal(scalar, snapshot[offset])}){{return {300 + step};}}"
                    )
                body.append("}")
        body.append("return 42;")
        suite.check(
            f"independent nested list model {scalar}, seed={seed + SCALARS.index(scalar) * 1000}, steps={steps}",
            program(
                "".join(body),
                storage_class("Storage", scalar, capacity) + PAIR,
                "auto identity(Pair<Storage,i64> value)->Pair<Storage,i64>{return value;}",
            ),
        )


def trap_cases(suite):
    definitions = LEAF + WRAP
    suite.check(
        "checked arithmetic after copying private nested value",
        program(
            "Leaf source=Leaf(9223372036854775807);Wrap wrap=Wrap(0,source,0);"
            "Leaf copied=wrap.item;return copied.add(1);",
            definitions,
        ),
        expected=Trap.OVERFLOW,
    )
    suite.check(
        "constructor later scalar trap remains exact overflow",
        program("Leaf source=Leaf(9223372036854775807);Wrap wrap=Wrap(0,source,source.add(1));return 42;", definitions),
        expected=Trap.OVERFLOW,
    )
    suite.check(
        "constructor later scalar trap remains exact division zero",
        program(
            "Leaf source=Leaf(20);Wrap wrap=Wrap(0,source,divide(0));return 42;",
            definitions,
            "auto divide(i64 value)->i64{return 42/value;}",
        ),
        expected=Trap.ZERO,
    )
    for scalar in SCALARS:
        for index in (-1, 2, -(1 << 63), (1 << 63) - 1):
            suite.check(
                f"copied nested {scalar} array exact bounds at {index}",
                program(
                    f"Storage source=Storage({literal(scalar, 0)},{literal(scalar, 0)});"
                    "Pair<Storage,i64> outer=Pair<Storage,i64>(source,42);const Storage copy=outer.first;"
                    f"return copy.at({index});",
                    storage_class("Storage", scalar, 2) + PAIR,
                    result=scalar,
                ),
                expected=Trap.BOUNDS,
            )
    suite.check(
        "nested copy bounds check precedes overflowing store RHS",
        program(
            "Storage source=Storage(0,0);Pair<Storage,i64> outer=Pair<Storage,i64>(source,42);"
            "Storage copy=outer.first;return copy.guarded(-1);",
            storage_class("Storage", "i64", 2).replace(
                "auto first()", "auto guarded(i64 index)->i64{data[index]=9223372036854775807+1;return 42;}auto first()"
            )
            + PAIR,
        ),
        expected=Trap.BOUNDS,
    )


def depth_and_leaf_cases(suite):
    for depth in (1, 2, 3, 4, 5):
        definitions = LEAF
        body = "Leaf value1=Leaf(42);"
        previous = "Leaf"
        for level in range(2, depth + 1):
            current = f"Level{level}"
            definitions += f"class {current}{{public:{previous} item;{current}({previous} source):item(source){{}}}};"
            body += f"{current} value{level}={current}(value{level - 1});"
            previous = current
        body += f"const {previous} returned=identity(value{depth});"
        for level in range(depth - 1, 0, -1):
            current = "Leaf" if level == 1 else f"Level{level}"
            source = "returned" if level == depth - 1 else f"copy{level + 1}"
            body += f"const {current} copy{level}={source}.item;"
        body += "return " + ("returned" if depth == 1 else "copy1") + ".get();"
        suite.check(
            f"composition class-depth boundary {depth}",
            program(body, definitions, f"auto identity({previous} source)->{previous}{{return source;}}"),
            error=None if depth <= 4 else ("depth", "four", "4"),
        )
    for leaves in (63, 64, 65):
        capacity = leaves - 1
        definitions = (
            f"class Wide{{builtin::array<i64,{capacity}> data;public:Wide():data{{}}{{}}"
            f"auto at(i64 index)const->i64{{return data[index];}}"
            f"auto set(i64 index,i64 value)->i64{{data[index]=value;return data[index];}}}};" + PAIR
        )
        suite.check(
            f"composition flattened leaf boundary {leaves}",
            program(
                f"Wide source=Wide();source.set({capacity - 1},40);Pair<Wide,i64> value=Pair<Wide,i64>(source,2);"
                "const Pair<Wide,i64> result=identity(value);const Wide copy=result.first;"
                f"static_assert(size_of(Pair<Wide,i64>)=={leaves * 8});return copy.at({capacity - 1})+result.second;",
                definitions,
                "auto identity(Pair<Wide,i64> value)->Pair<Wide,i64>{return value;}",
            ),
            error=None if leaves <= 64 else ("64", "leaves", "leaf", "composition"),
        )
        if leaves == 65:
            suite.check(
                "composed local alone cannot exceed 64 leaves",
                program("Wide source=Wide();Pair<Wide,i64> value=Pair<Wide,i64>(source,2);return 42;", definitions),
                error=("64", "leaves", "leaf", "composition"),
            )
    wide = (
        "class Wide{builtin::array<i64,63> data;public:Wide():data{}{}"
        "auto last()const->i64{return data[62];}"
        "auto set(i64 value)->i64{data[62]=value;return data[62];}};" + PAIR
    )
    suite.check(
        "six maximum-width composed function arguments",
        program(
            "Wide inner=Wide();inner.set(7);Pair<Wide,i64> value=Pair<Wide,i64>(inner,0);"
            "return consume(value,value,value,value,value,value);",
            wide,
            "auto consume(Pair<Wide,i64> a,Pair<Wide,i64> b,Pair<Wide,i64> c,"
            "Pair<Wide,i64> d,Pair<Wide,i64> e,Pair<Wide,i64> f)->i64{"
            "const Wide aa=a.first;const Wide bb=b.first;const Wide cc=c.first;"
            "const Wide dd=d.first;const Wide ee=e.first;const Wide ff=f.first;"
            "return aa.last()+bb.last()+cc.last()+dd.last()+ee.last()+ff.last();}",
        ),
    )


def rejection_cases(suite):
    definitions = LEAF + WRAP + PAIR
    for name, body in (
        ("nested constructor temporary argument", "Wrap w=Wrap(0,Leaf(42),0);return 42;"),
        ("nested constructor result argument", "Wrap w=Wrap(0,make(),0);return 42;"),
    ):
        suite.check(
            name,
            program(
                body,
                definitions,
                "auto consume(Leaf source)->i64{return source.get();}"
                "auto make()->Leaf{Leaf source=Leaf(42);return source;}",
            ),
        )
    for name, body in (
        ("chained scalar read", "Leaf source=Leaf(42);Wrap w=Wrap(0,source,0);return w.item.value;"),
        ("chained scalar mutation", "Leaf source=Leaf(42);Wrap w=Wrap(0,source,0);w.item.value=0;return 42;"),
        (
            "const whole nested field assignment",
            "Leaf source=Leaf(42);const Wrap w=Wrap(0,source,0);w.item=source;return 42;",
        ),
        ("nested field passed directly", "Leaf source=Leaf(42);Wrap w=Wrap(0,source,0);return consume(w.item);"),
        (
            "nested field constructor argument requires local copy",
            "Leaf source=Leaf(42);Wrap w=Wrap(0,source,0);Wrap other=Wrap(0,w.item,0);return 42;",
        ),
        ("nested constructor scalar mismatch", "Wrap w=Wrap(0,42,0);return 42;"),
        ("nested copy scalar mismatch", "Leaf source=Leaf(42);Wrap w=Wrap(0,source,0);i64 local=w.item;return local;"),
        (
            "nested field borrow",
            "Leaf source=Leaf(42);Wrap w=Wrap(0,source,0);const ref<i64> r=borrow(w.item);return 42;",
        ),
        ("nested field move", "Leaf source=Leaf(42);Wrap w=Wrap(0,source,0);own<i64> r=move(w.item);return 42;"),
        (
            "nested class designated initializer",
            "Leaf source=Leaf(42);Wrap w=Wrap{.head=0,.item=source,.tail=0};return 42;",
        ),
        ("nested field cannot be scalar arithmetic", "Leaf source=Leaf(42);Wrap w=Wrap(0,source,0);return w.item+1;"),
    ):
        suite.check(
            name,
            program(
                body,
                definitions,
                (
                    "auto consume(Leaf source)->i64{return source.get();}auto make()->Leaf{Leaf source=Leaf(42)"
                    ";return source;}"
                ),
            ),
            error=True,
        )
    for name, definition in (
        ("missing class field initialization", "class Bad{Leaf item;public:Bad(Leaf source){} };"),
        (
            "duplicate class field initialization",
            "class Bad{Leaf item;public:Bad(Leaf source):item(source),item(source){} };",
        ),
        ("class field zero braces", "class Bad{Leaf item;public:Bad():item{}{} };"),
        ("class field constructor expression", "class Bad{Leaf item;public:Bad():item(Leaf(42)){} };"),
        ("class field function expression", "class Bad{Leaf item;public:Bad():item(make()){} };"),
        ("class field scalar initializer", "class Bad{Leaf item;public:Bad():item(42){} };"),
        ("class field no complete constructor", "class Bad{public:Leaf item;};"),
        (
            "mutable constructor class parameter",
            "class Bad{i64 value;Leaf item;public:Bad(Leaf source):value(source.add(1)),item(source){} };",
        ),
        ("direct inline self cycle", "class Bad{Bad item;public:Bad(Bad source):item(source){} };"),
        (
            "indirect inline cycle",
            (
                "class Bad{Other item;public:Bad(Other source):item(source){} };class Other{Bad item;public:Oth"
                "er(Bad source):item(source){} };"
            ),
        ),
        ("owning field remains unsupported", "class Bad{own<i64> item;public:Bad():item(42){} };"),
        ("reference field remains unsupported", "class Bad{ref<i64> item;public:Bad():item(42){} };"),
    ):
        suite.check(
            name,
            program("return 42;", LEAF + definition, "auto make()->Leaf{Leaf source=Leaf(42);return source;}"),
            error=True,
        )
    suite.check(
        "method class parameter snapshot is independent",
        program(
            (
                "Leaf source=Leaf(42);Factory factory=Factory();Leaf result=factory.take(source);source.add(1);"
                "return result.get();"
            ),
            LEAF + "class Factory{public:Factory(){}auto take(Leaf input)const->Leaf{return input;}};",
        ),
    )
    suite.check(
        "method class result copies into typed local",
        program(
            "Factory factory=Factory();Leaf result=factory.get();return result.get();",
            LEAF + "class Factory{public:Factory(){}auto get()->Leaf{Leaf value=Leaf(42);return value;}};",
        ),
    )
    for argument in ("own<i64>", "ref<i64>", "array<i64,2>", "builtin::array<i64,2>", "Unknown", "42", ""):
        suite.check(
            "unsupported Value argument " + repr(argument),
            program(
                f"static_assert(size_of(Pair<{argument},i64>)>0);return 42;", definitions, imports="import std.array;"
            ),
            error=True,
        )
    for argument, size in (("Pair<i64,i64>", 24), ("std::array<i64,2>", 24)):
        suite.check(
            "concrete nested Value argument " + argument,
            program(
                f"static_assert(size_of(Pair<{argument},i64>)=={size});return 42;",
                definitions,
                imports="import std.array;",
            ),
        )
    for spelling in (
        "template<Value T=Leaf>",
        "template<Value... T>",
        "template<Value>",
        "template<Value T,Value T>",
        "template<Value T,Value U,Value V>",
        "template<Value T,i64 N>",
    ):
        suite.check(
            "malformed Value parameter " + spelling,
            program("return 42;", LEAF + spelling + "class Bad{T item;public:Bad(T source):item(source){} };"),
            error=True,
        )
    suite.check(
        "Scalar constraint still rejects concrete classes",
        program(
            "Leaf source=Leaf(42);Only<Leaf> value=Only<Leaf>(source);return 42;",
            LEAF + "template<Scalar T>class Only{T item;public:Only(T source):item(source){} };",
        ),
        error=True,
    )
    suite.check(
        "Value class method directly returns independent receiver field copy",
        program(
            "Leaf source=Leaf(42);const Only<Leaf> value=Only<Leaf>(source);Leaf copied=value.get();"
            "copied.add(1);source.add(2);const Leaf retained=value.get();"
            "if(copied.get()!=43){return 1;}return retained.get();",
            LEAF
            + (
                "template<Value T>class Only{T item;public:Only(T source):item(source){}auto get()const->T{retu"
                "rn item;}};"
            ),
        ),
    )
    suite.check(
        "Value substitution cannot authorize builtin arrays of classes",
        program(
            "Storage<Leaf> value=Storage<Leaf>();return 42;",
            LEAF + "template<Value T>class Storage{builtin::array<T,2> data;public:Storage():data{}{} };",
        ),
        error=True,
    )
    suite.check(
        "returning nested field requires a complete local copy",
        program(
            "Leaf source=Leaf(42);Wrap value=Wrap(0,source,0);Leaf copied=extract(value);return copied.get();",
            definitions,
            "auto extract(Wrap source)->Leaf{return source.item;}",
        ),
        error=True,
    )
    suite.check(
        "private field remains private after extraction",
        program(
            "Leaf source=Leaf(42);Wrap outer=Wrap(0,source,0);const Leaf copy=outer.item;return copy.value;",
            definitions,
        ),
        error=("private", "field"),
    )
    suite.check(
        "private class field cannot be extracted by caller",
        program(
            "Leaf source=Leaf(42);Private outer=Private(source);const Leaf copy=outer.item;return copy.get();",
            LEAF + "class Private{Leaf item;public:Private(Leaf source):item(source){} };",
        ),
        error=("private", "field"),
    )
    suite.check(
        "wrong constructor nominal type despite equal bytes",
        program(
            "Other source=Other(42);Wrap value=Wrap(0,source,0);return 42;", definitions + LEAF.replace("Leaf", "Other")
        ),
        error=("expected", "type"),
    )
    suite.check(
        "wrong extracted nominal type despite equal bytes",
        program(
            "Leaf source=Leaf(42);Wrap value=Wrap(0,source,0);Other copy=value.item;return 42;",
            definitions + LEAF.replace("Leaf", "Other"),
        ),
        error=("expected", "type"),
    )
    for operation, helper in (
        ("argument", "auto consume(Pair<i64,Leaf> value)->i64{return 42;}"),
        ("result", "auto consume(Pair<Leaf,i64> value)->Pair<i64,Leaf>{return value;}"),
    ):
        body = "Leaf source=Leaf(42);Pair<Leaf,i64> value=Pair<Leaf,i64>(source,0);"
        body += (
            "return consume(value);" if operation == "argument" else "Pair<i64,Leaf> result=consume(value);return 42;"
        )
        suite.check("same-byte reordered nominal " + operation, program(body, definitions, helper), error=True)
    preserved = b"previous verified assembly\x00\xff\n"
    suite.check(
        "readonly class-field copy leaves previous artifact byte-exact",
        program("Leaf source=Leaf(42);const Wrap value=Wrap(0,source,0);value.item=source;return 42;", definitions),
        error=True,
        existing_output=preserved,
    )


def module_cases(suite):
    modules = {
        "leaves": "export module leaves;export " + LEAF,
        "pairs": "export module pairs;export " + PAIR,
        "factory": "export module factory;import leaves;import pairs;"
        "export auto make()->Pair<Leaf,i64>{Leaf leaf=Leaf(20);Pair<Lea"
        "f,i64> result=Pair<Leaf,i64>(leaf,22);return result;}",
    }
    suite.check(
        "imported signature unifies template and class identities",
        program(
            "Pair<Leaf,i64> pair=make();const Leaf leaf=pair.first;return leaf.get()+pair.second;",
            imports="import leaves;import pairs;import factory;",
        ),
        modules=modules,
    )
    for imports in ("import pairs;import factory;", "import leaves;import factory;", "import factory;"):
        suite.check(
            "signature requires each direct visible type " + imports,
            program("Pair<Leaf,i64> pair=make();return 42;", imports=imports),
            modules=modules,
            error=("visible", "import", "unknown", "type"),
        )
    private = {
        "hidden": "export module hidden;"
        + LEAF
        + "export "
        + PAIR
        + (
            "export auto make()->Pair<Leaf,i64>{Leaf leaf=Leaf(20);Pair<Leaf,i64> value=Pair<Leaf,i64>(leaf,22)"
            ";return value;}"
        )
    }
    suite.check(
        "exported specialization result cannot expose private class argument",
        program("return 42;", imports="import hidden;"),
        modules=private,
        error=("private", "visible", "export"),
    )
    private_parameter = {
        "hidden": "export module hidden;"
        + LEAF
        + "export "
        + PAIR
        + "export auto consume(Pair<Leaf,i64> value)->i64{return value.second;}"
    }
    suite.check(
        "exported specialization parameter cannot expose private class argument",
        program("return 42;", imports="import hidden;"),
        modules=private_parameter,
        error=("private", "visible", "export"),
    )
    suite.check(
        "exported public class field cannot expose private nominal type",
        program("return 42;", imports="import hidden;"),
        modules={
            "hidden": "export module hidden;"
            + LEAF
            + "export class Exposed{public:Leaf item;private:Exposed(Leaf source):item(source){} };"
        },
        error=("private", "visible", "export"),
    )
    suite.check(
        "exported constructor signature cannot expose private nominal type",
        program("return 42;", imports="import hidden;"),
        modules={
            "hidden": "export module hidden;"
            + LEAF
            + "export class Exposed{Leaf item;public:Exposed(Leaf source):item(source){} };"
        },
        error=("private", "visible", "export"),
    )
    suite.check(
        "private nested representation and private constructor stay encapsulated",
        program(
            "static_assert(size_of(Opaque)==8);static_assert(field_count(Opaque)==0);return 42;",
            imports="import hidden;",
        ),
        modules={
            "hidden": "export module hidden;"
            + LEAF
            + "export class Opaque{Leaf item;Opaque(Leaf source):item(source){} };"
        },
    )
    suites = {
        "left": "export module left;export namespace left{" + LEAF + "}",
        "right": "export module right;export namespace right{" + LEAF + "}",
        "pairs": "export module pairs;export " + PAIR,
    }
    suite.check(
        "equal-byte imported class arguments remain nominally distinct",
        program(
            "left::Leaf source=left::Leaf(42);Pair<left::Leaf,i64> value=Pair<left::Leaf,i64>(source,0);"
            "Pair<right::Leaf,i64> wrong=value;return 42;",
            imports="import left;import right;import pairs;",
        ),
        modules=suites,
        error=("expected", "type", "copy"),
    )
    suite.check(
        "equal-byte imported template identities reflected distinctly",
        program(
            "static_assert(size_of(Pair<left::Leaf,i64>)==size_of(Pair<right::Leaf,i64>));"
            "static_assert(type_id(Pair<left::Leaf,i64>)!=type_id(Pair<right::Leaf,i64>));return 42;",
            imports="import left;import right;import pairs;",
        ),
        modules=suites,
    )
    suite.check(
        "import rejection preserves all inputs and prior artifact",
        program("Pair<Leaf,i64> pair=make();return 42;", imports="import factory;"),
        modules=modules,
        error=True,
        existing_output=b"saved output before invalid import\n",
    )
    suite.check(
        "template helpers bind in defining module and class arguments in caller",
        program(
            "Leaf source=Leaf(20);Box<Leaf> value=Box<Leaf>(source);const Leaf copy=value.item;"
            "return copy.get()+value.offset();",
            LEAF,
            "auto helper()->i64{return 999;}",
            imports="import boxes;",
        ),
        modules={
            "boxes": "export module boxes;"
            + LEAF
            + "auto helper()->i64{return 22;}export template<Value T>class Box{public:T item;"
            "Box(T source):item(source){}auto offset()const->i64{return helper();}};"
        },
    )
    shared_pair = {}
    for module, initial in (("left", 20), ("right", 22)):
        shared_pair[module] = (
            f"export module {module};import std.utility;"
            + LEAF.replace("Leaf", "Point")
            + f"export auto {module}_id()->i64{{return type_id(std::pair<Point,i64>);}}"
            f"export auto {module}_value()->i64{{Point point=Point({initial});"
            "std::pair<Point,i64> value=std::pair<Point,i64>(point,0);"
            "const Point copy=value.first;return copy.get();}"
        )
    suite.check(
        "same-spelling private class arguments from two modules remain distinct",
        program(
            "if(left_id()==right_id()){return 1;}return left_value()+right_value();",
            imports="import left;import right;",
        ),
        modules=shared_pair,
    )
    hidden_field = {
        "provider": "export module provider;class Hidden{public:i64 value;};"
        "export template<Value T>class Box{public:Hidden item;T extra;"
        "Box(Hidden source,T x):item(source),extra(x){} };"
    }
    for label, body, definitions in (
        ("local", "Box<i64> value=Box<i64>(1,2);return 42;", ""),
        ("reflection", "return size_of(Box<i64>);", ""),
        ("construction", "Box<i64>(1,2);return 42;", ""),
        ("ordinary field", "return 42;", "class Local{Box<i64> item;public:Local(Box<i64> source):item(source){} };"),
    ):
        suite.check(
            "specialization hard-coded hidden public type rejected in " + label,
            program(body, definitions, imports="import provider;"),
            modules=hidden_field,
            error="direct visible import",
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path, nargs="?", default=ROOT / "build/aurorac")
    parser.add_argument("--seed", type=int, default=11011)
    parser.add_argument("--steps", type=int, default=24)
    args = parser.parse_args()
    require(1 <= args.steps <= 128, "steps must be between 1 and 128")
    suite = Suite(args.compiler)
    scalar_and_library_cases(suite)
    native_copy_cases(suite)
    field_count_cases(suite)
    empty_class_cases(suite)
    snapshot_cases(suite)
    array_and_model_cases(suite, args.seed, args.steps)
    trap_cases(suite)
    depth_and_leaf_cases(suite)
    rejection_cases(suite)
    module_cases(suite)
    suite.finish()


if __name__ == "__main__":
    main()
