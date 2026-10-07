#!/usr/bin/env python3
"""Execute the bounded nested concrete-template value contract.

The native observer, full-width result validation, exact UD2 attribution, and
source/module/library immutability checks are shared with composed_values.py.
Every negative fixture runs twice: with no output and a byte-exact saved output.
Assertions use require(), including under python3 -O. Counts are measured, never
inferred from a generator's intended coverage. All temporary files are placed in
this checkout's tmp directory. This is bounded evidence, not a safety proof.

Run: python3 -O tests/compiler/nested_values.py build/aurorac
Optional: --seed 18018 --steps 64 --keep-going --section native
"""
from __future__ import annotations

import argparse
import hashlib
from itertools import product
from pathlib import Path
import random
import tempfile
import time

from composed_values import (Suite as CompositionSuite, Trap, observer_self_test,
                             program, require)

ROOT = Path(__file__).resolve().parents[2]
IMPORTS = "import std.utility;import std.array;"
SCALARS = ("i64", "u64", "u8", "bool")
VALUES = {"i64": "-9223372036854775808", "u64": "18446744073709551615u64",
          "u8": "255u8", "bool": "true"}
OTHER = {"i64": "9223372036854775807", "u64": "9223372036854775808u64",
         "u8": "0u8", "bool": "false"}
EMPTY = "class Empty{public:Empty(){}auto answer()const->i64{return 42;}};"
LEAF = ("class Leaf{u8 value;public:Leaf(u8 n):value(n){}"
        "auto get()const->u8{return value;}auto set(u8 n)->u8{value=n;return value;}};")
BOX = ("template<Value T>class Box{public:T item;Box(T source):item(source){}"
       "auto get()const->T{const T copy=item;return copy;}"
       "auto snapshot()const->Box{const T copy=item;const Box result=Box(copy);return result;}};")
TAG = "template<Value T>class Tag{public:Tag(){} };"
PAIR = ("template<Value T,Value U>class Pair{public:T first;U second;"
        "Pair(T a,U b):first(a),second(b){} };")
PRESERVED = b"previous verified assembly\x00\xff\n"


class Suite(CompositionSuite):
    def __init__(self, directory, compiler, keep_going):
        super().__init__(directory, compiler, keep_going)
        self.negative_fixtures = 0

    def reject(self, name, source, error=True, modules=None):
        before = self.rejections
        for suffix, previous in (("absent output", None), ("saved output", PRESERVED)):
            self.check(name + ": " + suffix, source, error=error,
                       modules=modules, existing_output=previous)
        if self.rejections == before + 2:
            self.negative_fixtures += 1


def p(body, definitions="", helpers="", imports=IMPORTS, result="i64"):
    return program(body, definitions, helpers, imports, result)


def native_cases(suite, seed, steps):
    example = ROOT / "examples/nested_token_values.au"
    original = example.read_bytes()
    suite.check("real bounded token and source-range example", original.decode())
    require(example.read_bytes() == original, "token example changed during execution")

    # Every ordered scalar tuple participates in an inner specialization. Copy
    # it through an outer specialization, a function result, and two projections.
    for first, second in product(SCALARS, repeat=2):
        inner = f"std::pair<{first},{second}>"
        outer = f"std::pair<{inner},u8>"
        suite.check(f"nested ordered scalar tuple {first}/{second}", p(
            f"{inner} source={inner}({VALUES[first]},{VALUES[second]});"
            f"{outer} value={outer}(source,7u8);source.first={OTHER[first]};"
            f"const {outer} returned=identity(value);{inner} changed=returned.first;"
            f"changed.second={OTHER[second]};const {inner} saved=value.first;"
            f"if(saved.first!={VALUES[first]}){{return 1;}}"
            f"if(saved.second!={VALUES[second]}){{return 2;}}"
            f"if(changed.second!={OTHER[second]}){{return 3;}}"
            f"if(returned.second!=7u8){{return 4;}}"
            f"static_assert(size_of({outer})=={3 if first == second == 'u8' else 24});"
            f"static_assert(field_count({outer})==2);return 42;",
            helpers=f"auto identity({outer} value)->{outer}{{return value;}}"))

    # Every permitted byte capacity is executed, including every initialized
    # element. Empty second fields permit the exact 64-leaf boundary.
    for scalar in SCALARS:
        capacities = range(1, 65) if scalar == "u8" else (1, 2, 16, 63, 64)
        for capacity in capacities:
            inner = f"std::array<{scalar},{capacity}>"
            outer = f"std::pair<{inner},Empty>"
            zero = "false" if scalar == "bool" else "0" + (scalar if scalar in ("u64", "u8") else "")
            size = capacity if scalar == "u8" else capacity * 8
            suite.check(f"private nested array {scalar} capacity {capacity}", p(
                f"{inner} storage={inner}();Empty empty=Empty();"
                f"{outer} value={outer}(storage,empty);"
                f"storage.set({capacity-1},{VALUES[scalar]});"
                f"const {outer} returned=identity(value);{inner} changed=returned.first;"
                "i64 i=0;while(i<changed.size()){"
                f"if(changed.at(i)!={zero}){{return 1;}}changed.set(i,{VALUES[scalar]});i=i+1;}}"
                f"const {inner} saved=returned.first;i64 j=0;while(j<saved.size()){{"
                f"if(saved.at(j)!={zero}){{return 2;}}"
                f"if(changed.at(j)!={VALUES[scalar]}){{return 3;}}j=j+1;}}"
                f"static_assert(size_of({outer})=={size});"
                f"static_assert(field_count({outer})==2);static_assert(field_count({inner})==0);"
                f"if(reflect_size(type_id({outer}))!={size}){{return 4;}}"
                f"if(reflect_field_count(type_id({outer}))!=2){{return 5;}}"
                "const Empty copied=returned.second;return copied.answer();", EMPTY,
                f"auto identity({outer} value)->{outer}{{return value;}}"))

    for enum_position in ("first", "second"):
        inner = "std::pair<Status,u8>" if enum_position == "first" else "std::pair<u8,Status>"
        args = "Status::ready,255u8" if enum_position == "first" else "255u8,Status::ready"
        outer = f"std::pair<{inner},Status>"
        suite.check("nested nominal enum " + enum_position, p(
            f"{inner} inner={inner}({args});{outer} value={outer}(inner,Status::failed);"
            f"const {outer} returned=identity(value);{inner} copy=returned.first;"
            f"copy.{enum_position}=Status::failed;const {inner} saved=value.first;"
            f"if(saved.{enum_position}!=Status::ready){{return 1;}}"
            "if(returned.second!=Status::failed){return 2;}return 42;",
            "enum class Status{ready,failed};",
            f"auto identity({outer} value)->{outer}{{return value;}}"))

    suite.check("injected self snapshot and substituted class result copies", p(
        "std::array<u8,3> source=std::array<u8,3>();source.set(2,40u8);"
        "Box<std::array<u8,3>> inner=Box<std::array<u8,3>>(source);"
        "Box<Box<std::array<u8,3>>> outer=Box<Box<std::array<u8,3>>>(inner);"
        "const Box<Box<std::array<u8,3>>> saved=outer.snapshot();"
        "Box<std::array<u8,3>> extracted=saved.get();std::array<u8,3> changed=extracted.get();"
        "changed.set(2,2u8);const Box<std::array<u8,3>> preserved=saved.item;"
        "const std::array<u8,3> bytes=preserved.item;return i64(bytes.at(2))+i64(changed.at(2));", BOX))
    suite.check("ordinary class private nested specialized field and method result", p(
        "std::array<u8,3> source=std::array<u8,3>();source.set(2,40u8);"
        "std::pair<std::array<u8,3>,u8> pair=std::pair<std::array<u8,3>,u8>(source,2u8);"
        "Holder holder=Holder(pair);const std::pair<std::array<u8,3>,u8> result=holder.copy();"
        "const std::array<u8,3> bytes=result.first;return i64(bytes.at(2))+i64(result.second);",
        "class Holder{std::pair<std::array<u8,3>,u8> value;public:"
        "Holder(std::pair<std::array<u8,3>,u8> source):value(source){}"
        "auto copy()const->std::pair<std::array<u8,3>,u8>{"
        "const std::pair<std::array<u8,3>,u8> result=value;return result;}};"))
    suite.check("empty nested descendants survive complete copy and method result", p(
        "Empty empty=Empty();Box<Empty> one=Box<Empty>(empty);"
        "Box<Box<Empty>> two=Box<Box<Empty>>(one);"
        "const Box<Box<Empty>> saved=two.snapshot();const Box<Empty> inner=saved.get();"
        "const Empty copy=inner.get();static_assert(field_count(Box<Box<Empty>>)==1);"
        "return copy.answer();", EMPTY + BOX))
    suite.check("adjacent and spaced closers canonicalize in all type positions", p(
        "std::pair<i64,u8> inner=std::pair<i64,u8>(40,2u8);"
        "std::pair<std::pair<i64,u8>,u8> value=std::pair<std::pair<i64,u8>,u8>(inner,0u8);"
        "const std::pair< std::pair< i64, u8 >, u8 > copied=identity(value);"
        "const std::pair<i64,u8> result=copied.first;"
        "static_assert(type_id(std::array<u8,03>)==type_id(std::array<u8,3>));"
        "static_assert(type_id(std::pair<std::array<u8,03>,u8>)=="
        "type_id(std::pair<std::array<u8,3>,u8>));return result.first+i64(result.second);",
        helpers="auto identity(std::pair< std::pair<i64,u8>,u8 > value)"
        "->std::pair<std::pair<i64,u8>,u8>{return value;}"))

    # Predict state solely with ordinary Python lists. A saved outer object and
    # extracted mutable bytes must never share storage with source/projections.
    rng = random.Random(seed)
    for capacity in (1, 3, 16, 63):
        inner = f"std::array<u8,{capacity}>"
        outer = f"std::pair<{inner},u8>"
        initial = [rng.randrange(256) for _ in range(capacity)]
        body = [f"{inner} source={inner}();"]
        body += [f"source.set({i},{v}u8);" for i, v in enumerate(initial)]
        body += [f"const {outer} saved={outer}(source,17u8);",
                 f"const {outer} returned=identity(saved);{inner} changed=returned.first;"]
        model = initial.copy()
        for _ in range(steps):
            index, value = rng.randrange(capacity), rng.randrange(256)
            body.append(f"changed.set({index},{value}u8);")
            model[index] = value
        body += [f"source.set(0,{(initial[0]+1)%256}u8);", f"const {inner} stable=saved.first;"]
        for i, (old, new) in enumerate(zip(initial, model)):
            body.append(f"if(stable.at({i})!={old}u8){{return 1;}}"
                        f"if(changed.at({i})!={new}u8){{return 2;}}")
        body.append("return 42;")
        suite.check(f"independent seeded byte projection model capacity {capacity}",
                    p("".join(body), helpers=f"auto identity({outer} value)->{outer}{{return value;}}"))

    # Snapshot side effects are scalar expressions after the named class input.
    suite.check("left-to-right constructor snapshot before later array mutation", p(
        "std::array<u8,1> source=std::array<u8,1>();source.set(0,20u8);"
        "std::pair<std::array<u8,1>,u8> value=std::pair<std::array<u8,1>,u8>(source,source.set(0,22u8));"
        "const std::array<u8,1> copy=value.first;return i64(copy.at(0))+i64(value.second);"))
    suite.check("left-to-right ordinary function snapshot before later mutation", p(
        "std::array<u8,1> source=std::array<u8,1>();source.set(0,20u8);"
        "std::pair<std::array<u8,1>,u8> value=std::pair<std::array<u8,1>,u8>(source,20u8);"
        "Snapshot snapshot=Snapshot(value,20u8);return consume(snapshot,snapshot.bump());",
        "class Snapshot{std::pair<std::array<u8,1>,u8> item;u8 count;public:"
        "Snapshot(std::pair<std::array<u8,1>,u8> input,u8 n):item(input),count(n){}"
        "auto bump()->u8{count=count+2u8;return count;}auto get()const->u8{return count;}};",
        helpers="auto consume(Snapshot value,u8 extra)->i64{return i64(value.get())+i64(extra);}"))


def boundary_cases(suite):
    for levels in (3, 4, 5):
        concrete = "i64"
        for _ in range(levels):
            concrete = f"Tag<{concrete}>"
        source = p(f"static_assert(size_of({concrete})==8);{concrete} value={concrete}();return 42;",
                   TAG, imports="")
        if levels <= 4:
            suite.check(f"template-id syntax depth {levels} independent of containment", source)
        else:
            suite.reject("template-id syntax depth five with zero-leaf classes", source,
                         error=("depth", "four", "4", "nested"))
    for leaf_class in (False, True):
        concrete = "Leaf" if leaf_class else "u8"
        body = "Leaf value0=Leaf(42u8);" if leaf_class else "u8 value0=42u8;"
        for level in range(1, 5):
            concrete = f"Box<{concrete}>"
            body += f"{concrete} value{level}={concrete}(value{level-1});"
        if leaf_class:
            body += "return 42;"
        else:
            child = concrete
            for level in range(3, -1, -1):
                child = child[4:-1]
                origin = "value4" if level == 3 else f"copy{level+1}"
                body += f"const {child} copy{level}={origin}.item;"
            body += "return i64(copy0);"
        source = p(body, LEAF + BOX, imports="")
        if leaf_class:
            suite.reject("four template ids plus named class exceeds containment depth", source,
                         error=("depth", "four", "4"))
        else:
            suite.check("four template ids and exactly four containment levels", source)
    for leaves in (63, 64, 65):
        capacity = leaves - 1
        inner = f"std::array<u8,{capacity}>"
        outer = f"std::pair<{inner},u8>"
        source = p(f"{inner} bytes={inner}();bytes.set({capacity-1},40u8);"
                   f"{outer} value={outer}(bytes,2u8);const {outer} result=identity(value);"
                   f"const {inner} copy=result.first;"
                   f"static_assert(size_of({outer})=={leaves});return i64(copy.at({capacity-1}))+i64(result.second);",
                   helpers=f"auto identity({outer} value)->{outer}{{return value;}}")
        suite.check(f"nested generic copied byte leaves {leaves}", source)
        if leaves == 65:
            suite.check("unused local nested generic admits 65 byte leaves",
                        p(f"{inner} bytes={inner}();{outer} value={outer}(bytes,2u8);return 42;"))
    for capacity in (0, 65, -1, 9223372036854775808):
        suite.reject(f"nested inner array capacity {capacity} rejected", p(
            f"static_assert(size_of(std::pair<std::array<u8,{capacity}>,u8>)>0);return 42;"))

    for count in (64, 65):
        definitions = "".join(TAG.replace("Tag", f"Tag{i}") for i in range(count))
        body = "Tag0<Tag1<u8>> value=Tag0<Tag1<u8>>();return 42;"
        source = p(body, definitions, imports="")
        if count == 64:
            suite.check("exactly 64 template definitions with nested request", source)
        else:
            suite.reject("65 template definitions with nested request", source, error=("64", "template"))
        midpoint = count // 2
        modules = {"left": "export module left;" + "".join("export " + TAG.replace("Tag", f"Tag{i}")
                    for i in range(midpoint)),
                   "right": "export module right;" + "".join("export " + TAG.replace("Tag", f"Tag{i}")
                    for i in range(midpoint, count))}
        source = p(body, imports="import left;import right;")
        if count == 64:
            suite.check("64 template definitions across module graph", source, modules=modules)
        else:
            suite.reject("65 template definitions across module graph", source,
                         error=("64", "template"), modules=modules)

    # Each unique inner array plus its Tag specialization consumes two entries.
    # 128 nested requests therefore make 256 instances, not merely 128. Tag
    # deliberately has no field so width limits cannot mask this graph budget.
    types = [f"std::array<{scalar},{capacity}>" for scalar in ("u8", "i64")
             for capacity in range(1, 65)]
    requests = [f"static_assert(size_of(Tag<{inner}>)==8);" for inner in types]
    source = p("".join(requests) + "return 42;", TAG)
    suite.check("256 specializations includes all 128 inner requests", source)
    suite.reject("257 specializations rejects one further distinct outer request",
                 p("".join(requests) + "static_assert(size_of(Tag<u8>)==8);return 42;", TAG),
                 error=("256", "instantiat", "specializ"))
    dedup = ("static_assert(type_id(Tag<std::array<u8,03>>)==type_id(Tag<std::array<u8,3>>));" * 300)
    suite.check("canonical 03 and 3 repeated nested requests preserve exact 256 budget",
                p("".join(requests) + dedup + "return 42;", TAG))
    modules = {"tags": "export module tags;export " + TAG,
               "left": "export module left;import tags;import std.array;export auto left_value()->i64{" +
                       "".join(requests[:64]) + "return 20;}",
               "right": "export module right;import tags;import std.array;export auto right_value()->i64{" +
                        "".join(requests[64:]) + "return 22;}"}
    suite.check("256 specializations across modules includes nested requests",
                p("return left_value()+right_value();", imports="import left;import right;"), modules=modules)
    too_many = dict(modules)
    too_many["right"] = too_many["right"].replace("return 22;", "static_assert(size_of(Tag<u8>)==8);return 22;")
    suite.reject("257 specializations across modules rejected globally",
                 p("return left_value()+right_value();", imports="import left;import right;"),
                 error=("256", "instantiat", "specializ"), modules=too_many)


def rejection_cases(suite):
    valid = ("std::array<u8,3> bytes=std::array<u8,3>();"
             "std::pair<std::array<u8,3>,u8> value=std::pair<std::array<u8,3>,u8>(bytes,42u8);")
    for name, body in (
        ("nested call chaining", "return i64(value.first.at(0));"),
        ("whole nested-field replacement", "value.first=bytes;return 42;"),
        ("nested resource borrowing", "const ref<i64> r=borrow(value.first);return 42;"),
        ("nested resource move", "own<i64> r=move(value.first);return 42;"),
        ("private inner array storage remains private", "const std::array<u8,3> copy=value.first;return i64(copy.elements[0]);"),
        ("mutable call on const projected value", "const std::array<u8,3> copy=value.first;copy.set(0,1u8);return 42;"),
        ("readonly function parameter mutation", "return mutate(value);"),
        ("projection cannot be passed directly", "return consume(value.first);"),
        ("wrong nominal projection capacity", "std::array<u8,4> wrong=value.first;return 42;"),
        ("wrong nominal projection element", "std::array<i64,3> wrong=value.first;return 42;"),
    ):
        helpers = ("auto mutate(std::pair<std::array<u8,3>,u8> value)->i64{value.second=0u8;return 42;}"
                   if name == "readonly function parameter mutation" else
                   "auto consume(std::array<u8,3> value)->i64{return 42;}")
        suite.reject(name, p(valid + body, helpers=helpers))
    for argument in ("own<i64>", "ref<i64>", "span<u8>", "array<u8,3>", "builtin::array<u8,3>",
                     "Unknown", "42", "", "std::array<u8,3> const"):
        suite.reject("unsupported recursive Value argument " + repr(argument), p(
            f"static_assert(size_of(std::pair<std::pair<{argument},u8>,u8>)>0);return 42;"))
    for concrete in ("std::array<std::array<u8,3>,3>", "std::array<std::pair<i64,u8>,3>",
                     "std::array<Status,3>", "Only<std::pair<i64,u8>>"):
        suite.reject("Scalar still excludes nested class or enum " + concrete, p(
            f"static_assert(size_of({concrete})>0);return 42;",
            "enum class Status{ready};template<Scalar T>class Only{T value;public:Only(T n):value(n){} };"))
    for capacity in ("N", "1+2", "u8", "3u8", "true", "std::array<u8,3>"):
        suite.reject("inner capacity remains literal-only " + capacity, p(
            f"static_assert(size_of(std::pair<std::array<u8,{capacity}>,u8>)>0);return 42;"))
    for concrete in ("std::pair<std::array<u8,3>,>", "std::pair<std::array<u8,3>>",
                     "std::pair<std::array<u8,3>,u8,u8>", "std::pair<std::array<u8>,u8>",
                     "std::pair<std::array<u8,3>,u8>>", "std::pair<std::array<u8,3>,u8",
                     "std::pair<std::array<u8,3>,u8>>>", "std::pair<std::array<u8,3>>,u8>",
                     "std::pair<std::array<u8,3>,u8>=", "std::pair<std::array<u8,3> >u8>"):
        suite.reject("malformed nested closers or arity " + concrete,
                     p(f"static_assert(size_of({concrete})>0);return 42;"))

    # Explicit specialization requests inside an uninstantiated definition are
    # still outside the supported language, even if the request is concrete.
    for label, definition in (
        ("concrete field", "template<Value T>class Bad{std::pair<u8,u8> item;};"),
        ("dependent field", "template<Value T>class Bad{Box<T> item;};"),
        ("recursive field", "template<Value T>class Bad{Bad<T> item;};"),
        ("dependent method local", "template<Value T>class Bad{public:Bad(){}auto f()->i64{Box<T> x=Box<T>(0);return 42;}};"),
        ("concrete reflection", "template<Value T>class Bad{public:Bad(){}auto f()->i64{return size_of(Box<u8>);}};"),
        ("nested concrete method result", "template<Value T>class Bad{public:Bad(){}auto f()->Box<Box<u8>>{return missing;}};"),
        ("explicit specialization definition", "template<>class Box<std::array<u8,3>>{};"),
        ("partial specialization definition", "template<Value T>class Box<std::pair<T,u8>>{};"),
        ("nested dependent function-template result", "template<Value T>auto make()->Box<Box<T>>{return missing;}"),
    ):
        suite.reject("unsupported template-body or template form: " + label, p("return 42;", BOX + definition))

    a, b = "std::pair<i64,u64>", "std::pair<u64,i64>"
    aa, bb = f"std::pair<{a},u8>", f"std::pair<{b},u8>"
    prefix = f"{a} inner={a}(20,22u64);{aa} value={aa}(inner,0u8);"
    for label, body, helpers in (
        ("copy", f"{bb} wrong=value;return 42;", ""),
        ("argument", "return consume(value);", f"auto consume({bb} value)->i64{{return 42;}}"),
        ("result", f"{bb} result=wrong(value);return 42;", f"auto wrong({aa} value)->{bb}{{return value;}}"),
        ("constructor", f"{bb} wrong={bb}(inner,0u8);return 42;", ""),
    ):
        suite.reject("equal-byte reordered nested nominal " + label, p(prefix + body, helpers=helpers))
    suite.check("nested class method parameters make independent snapshots", p(
        "std::array<u8,3> bytes=std::array<u8,3>();bytes.set(2,40u8);"
        "std::pair<std::array<u8,3>,u8> source=std::pair<std::array<u8,3>,u8>(bytes,2u8);"
        "Receiver receiver=Receiver();return receiver.consume(source);",
        "class Receiver{public:Receiver(){}auto consume(std::pair<std::array<u8,3>,u8> value)const->i64{"
        "const std::array<u8,3> bytes=value.first;return i64(bytes.at(2))+i64(value.second);}};"))
    suite.reject("direct nested projection result remains unsupported", p(valid +
        "const std::array<u8,3> result=extract(value);return 42;", helpers=
        "auto extract(std::pair<std::array<u8,3>,u8> value)->std::array<u8,3>{return value.first;}"))


def module_cases(suite):
    modules = {"leaves": "export module leaves;export " + LEAF,
               "boxes": "export module boxes;export " + BOX,
               "factory": "export module factory;import leaves;import boxes;export auto make()->Box<Box<Leaf>>{"
                          "Leaf leaf=Leaf(42u8);Box<Leaf> inner=Box<Leaf>(leaf);"
                          "Box<Box<Leaf>> outer=Box<Box<Leaf>>(inner);return outer;}"}
    body = "const Box<Box<Leaf>> value=make();const Box<Leaf> inner=value.item;const Leaf leaf=inner.item;return i64(leaf.get());"
    suite.check("direct imports recursively unify nested function result identity",
                p(body, imports="import leaves;import boxes;import factory;"), modules=modules)
    for imports in ("import boxes;import factory;", "import leaves;import factory;", "import factory;"):
        suite.reject("transitive dependency is not visible: " + imports,
                     p(body, imports=imports), modules=modules, error=("visible", "import", "unknown", "type"))
    library_modules = {"factory": "export module factory;" + IMPORTS +
                       "export auto make()->std::pair<std::array<u8,3>,u8>{std::array<u8,3> a=std::array<u8,3>();"
                       "a.set(2,40u8);std::pair<std::array<u8,3>,u8> result=std::pair<std::array<u8,3>,u8>(a,2u8);return result;}"}
    body = ("const std::pair<std::array<u8,3>,u8> value=make();"
            "const std::array<u8,3> bytes=value.first;return i64(bytes.at(2))+i64(value.second);")
    suite.check("both direct library template imports permit nested result", p(body, imports=IMPORTS+"import factory;"),
                modules=library_modules)
    for imports in ("import std.utility;import factory;", "import std.array;import factory;", "import factory;"):
        suite.reject("nested library template dependency needs direct import " + imports,
                     p(body, imports=imports), modules=library_modules)

    for hidden_kind, hidden in (("class", LEAF), ("enum", "enum class Leaf{ready};")):
        nested = "Pair<Pair<Leaf,u8>,u8>"
        make_leaf = "Leaf leaf=Leaf(42u8);" if hidden_kind == "class" else "Leaf leaf=Leaf::ready;"
        make_body = (make_leaf + "Pair<Leaf,u8> inner=Pair<Leaf,u8>(leaf,0u8);" +
                     f"{nested} result={nested}(inner,0u8);return result;")
        for label, signature in (
            ("parameter", f"export auto consume({nested} value)->i64{{return 42;}}"),
            ("result", f"export auto make()->{nested}{{{make_body}}}"),
        ):
            suite.reject(f"export rejects private {hidden_kind} recursively in nested {label}",
                         p("return 42;", imports="import hidden;"),
                         modules={"hidden": "export module hidden;" + hidden + "export " + PAIR + signature},
                         error=("private", "visible", "export"))
    for label, signature in (
        ("function parameter", "export auto consume(Pair<Secret<u8>,u8> value)->i64{return 42;}"),
        ("public field", "export class Exposed{public:Pair<Secret<u8>,u8> value;private:Exposed(Pair<Secret<u8>,u8> x):value(x){} };"),
        ("public constructor", "export class Exposed{Pair<Secret<u8>,u8> value;public:Exposed(Pair<Secret<u8>,u8> x):value(x){} };"),
    ):
        suite.reject("export rejects private inner template in " + label, p("return 42;", imports="import hidden;"),
                     modules={"hidden": "export module hidden;" + TAG.replace("Tag", "Secret") + "export " + PAIR + signature},
                     error=("private", "visible", "export"))

    helpers = {"boxes": "export module boxes;auto helper()->i64{return 22;}export template<Value T>class Box{"
                       "public:T item;Box(T input):item(input){}auto offset()const->i64{return helper();}};"}
    suite.check("nested imported template body uses defining-module helper", p(
        "std::array<u8,3> source=std::array<u8,3>();source.set(2,20u8);"
        "Box<std::array<u8,3>> value=Box<std::array<u8,3>>(source);"
        "const std::array<u8,3> copied=value.item;return i64(copied.at(2))+value.offset();",
        helpers="auto helper()->i64{return 999;}", imports="import std.array;import boxes;"), modules=helpers)
    same_names = {}
    for module, initial in (("left", 20), ("right", 22)):
        same_names[module] = (f"export module {module};import std.utility;" + LEAF.replace("Leaf", "Point") +
            f"export auto {module}_id()->i64{{return type_id(std::pair<std::pair<Point,u8>,u8>);}}"
            f"export auto {module}_value()->i64{{Point point=Point({initial}u8);"
            "std::pair<Point,u8> inner=std::pair<Point,u8>(point,0u8);"
            "std::pair<std::pair<Point,u8>,u8> outer=std::pair<std::pair<Point,u8>,u8>(inner,0u8);"
            "const std::pair<Point,u8> copied=outer.first;const Point leaf=copied.first;return i64(leaf.get());}")
    suite.check("nested cache keys preserve module identity for same-spelling private leaves", p(
        "if(left_id()==right_id()){return 1;}return left_value()+right_value();",
        imports="import left;import right;"), modules=same_names)
    suite.check("runtime reflection cannot expose private recursively nested argument", p(
        "if(reflect_size(left_id())!=0){return 1;}if(reflect_field_count(right_id())!=0){return 2;}return 42;",
        imports="import left;import right;import std.utility;"), modules=same_names)

    concrete_names = {"left": "export module left;export namespace left{" + LEAF + "}",
                      "right": "export module right;export namespace right{" + LEAF + "}"}
    imports = "import left;import right;" + IMPORTS
    suite.check("qualified inner nominal types have equal bytes and distinct nested identities", p(
        "static_assert(size_of(std::pair<std::pair<left::Leaf,u8>,u8>)==3);"
        "static_assert(size_of(std::pair<std::pair<right::Leaf,u8>,u8>)==3);"
        "static_assert(type_id(std::pair<std::pair<left::Leaf,u8>,u8>)!="
        "type_id(std::pair<std::pair<right::Leaf,u8>,u8>));return 42;", imports=imports), modules=concrete_names)
    suite.reject("qualified inner nominal types cannot copy by equal layout", p(
        "left::Leaf leaf=left::Leaf(42u8);std::pair<left::Leaf,u8> inner=std::pair<left::Leaf,u8>(leaf,0u8);"
        "std::pair<std::pair<left::Leaf,u8>,u8> value=std::pair<std::pair<left::Leaf,u8>,u8>(inner,0u8);"
        "std::pair<std::pair<right::Leaf,u8>,u8> wrong=value;return 42;", imports=imports), modules=concrete_names)


def trap_and_shift_cases(suite):
    for capacity in (1, 3, 16, 63):
        for index in (-1, capacity, 9223372036854775807):
            for operation in ("at", "set"):
                inner = f"std::array<u8,{capacity}>"
                outer = f"std::pair<{inner},u8>"
                args = str(index) + (",1u8" if operation == "set" else "")
                suite.check(f"copied nested array {operation} exact bounds site {capacity}/{index}", p(
                    f"{inner} source={inner}();{outer} value={outer}(source,0u8);"
                    f"{inner} copy=value.first;return i64(copy.{operation}({args}));"), expected=Trap.BOUNDS)
    for scalar, initial, count, expected in (("u64", "18446744073709551615u64", 1, (1<<63)-1),
                                             ("u8", "255u8", 1, 127),
                                             ("u64", "9223372036854775808u64", 63, 1),
                                             ("u8", "128u8", 7, 1)):
        inner = f"std::pair<{scalar},{scalar}>"
        outer = f"std::pair<{inner},u8>"
        suite.check(f"shift token unchanged next to nested type closers {scalar}/{count}", p(
            f"{inner} inner={inner}({initial},{initial});{outer} outer={outer}(inner,0u8);"
            f"const {inner} copy=outer.first;return copy.first >> {count};", result=scalar), expected=expected)
    suite.check("nested type expressions do not change ordinary comparison parsing", p(
        "std::pair<i64,u8> inner=std::pair<i64,u8>(40,2u8);"
        "std::pair<std::pair<i64,u8>,u8> value=std::pair<std::pair<i64,u8>,u8>(inner,0u8);"
        "const std::pair<i64,u8> copy=value.first;"
        "if(copy.first>=40){if(copy.first>39){if(copy.first<41){if(copy.first<=40){return 42;}}}}return 0;"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path, nargs="?", default=ROOT / "build/aurorac")
    parser.add_argument("--seed", type=int, default=18018)
    parser.add_argument("--steps", type=int, default=24)
    parser.add_argument("--section", choices=("all", "native", "boundaries", "rejections", "modules", "traps"), default="all")
    parser.add_argument("--self-test-only", action="store_true")
    parser.add_argument("--keep-going", action="store_true")
    args = parser.parse_args()
    require(1 <= args.steps <= 128, "steps must be between 1 and 128")
    compiler = args.compiler.resolve()
    started = time.monotonic()
    if not args.self_test_only:
        print(f"INFO nested values compiler={compiler} sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()}", flush=True)
        for relative in ("tests/compiler/nested_values.py", "examples/nested_token_values.au",
                         "library/std/utility.au", "library/std/array.au"):
            print(f"INFO nested values {relative} sha256={hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()}", flush=True)
    temporary_root = Path(tempfile.gettempdir())
    temporary_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nested-values-", dir=temporary_root) as temporary:
        suite = Suite(Path(temporary), compiler, args.keep_going)
        observer_self_test(suite)
        if args.self_test_only:
            print("PASS nested values harness self-tests (no compiler acceptance claimed)", flush=True)
            return
        sections = {"native": lambda: native_cases(suite, args.seed, args.steps),
                    "boundaries": lambda: boundary_cases(suite),
                    "rejections": lambda: rejection_cases(suite),
                    "modules": lambda: module_cases(suite),
                    "traps": lambda: trap_and_shift_cases(suite)}
        for name, run in sections.items():
            if args.section in ("all", name):
                before = (suite.count, suite.traps, suite.rejections)
                run()
                print(f"INFO nested values section={name} passed={suite.count-before[0]} "
                      f"traps={suite.traps-before[1]} rejection-runs={suite.rejections-before[2]}", flush=True)
        native = suite.count - suite.traps - suite.rejections
        print(f"INFO nested values: {suite.count} passed; {native} native returns; {suite.traps} exact-site traps; "
              f"{suite.negative_fixtures} rejection fixtures / {suite.rejections} rejection runs; "
              f"{len(suite.failures)} failures; section={args.section}; seed={args.seed}; steps={args.steps}; "
              f"elapsed={time.monotonic()-started:.2f}s", flush=True)
        require(not suite.failures, f"{len(suite.failures)} nested-value checks failed")
        print("PASS nested values complete", flush=True)


if __name__ == "__main__":
    main()
