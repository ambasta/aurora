#!/usr/bin/env python3
"""Bounded explicit function templates (M021): native results, traps and rejections.

Cases are data on one native_runner.Suite: complete 64-bit results, exact trap
sites and diagnostic fragments (matched case-insensitively).

Run: python3 -O tests/compiler/function_templates.py build/aurorac
"""

from __future__ import annotations

import argparse
from itertools import product
from pathlib import Path
import random

from native_runner import ROOT, Suite, Trap, require

IMPORTS = "import std.utility;import std.array;"
SCALARS = ("i64", "u64", "u8", "bool")
VALUES = {"i64": "-9223372036854775808", "u64": "18446744073709551615u64", "u8": "255u8", "bool": "true"}
OTHER = {"i64": "9223372036854775807", "u64": "9223372036854775808u64", "u8": "0u8", "bool": "false"}
BITS = {"i64": -(1 << 63), "u64": (1 << 64) - 1, "u8": 255, "bool": 1}
COPY = "template<Value T>auto copy(T value)->T{const T result=value;return result;}"
PROBE = "template<Value T>auto probe()->i64{return 42;}"
MAKE = (
    "template<Value T,Value U>auto make(T x,U y)->std::pair<T,U>{"
    "const std::pair<T,U> result=std::pair<T,U>(x,y);return result;}"
)
LEAF = (
    "class Leaf{u8 value;public:Leaf(u8 n):value(n){}"
    "auto get()const->u8{return value;}auto set(u8 n)->u8{value=n;return value;}};"
)
EMPTY = "class Empty{public:Empty(){}auto answer()const->i64{return 42;}};"
BOX = "template<Value T>class Box{public:T item;Box(T x):item(x){} };"
TAG = "template<Value T>class Tag{public:Tag(){} };"


def p(body, definitions="", helpers="", imports=IMPORTS, result="i64"):
    return "module app;" + imports + definitions + helpers + f"auto test()->{result}{{{body}}}"


def native_cases(suite, seed, steps):
    for first, second in product(SCALARS, repeat=2):
        pair = f"std::pair<{first},{second}>"
        suite.check(
            f"make_pair all ordered scalar tuples {first}/{second}",
            p(
                f"{pair} value=std::make_pair<{first},{second}>({VALUES[first]},{VALUES[second]});"
                f"{pair} changed=copy<{pair}>(value);changed.first={OTHER[first]};"
                f"changed.second={OTHER[second]};if(value.first!={VALUES[first]}){{return 1;}}"
                f"if(value.second!={VALUES[second]}){{return 2;}}"
                f"if(changed.first!={OTHER[first]}){{return 3;}}"
                f"if(changed.second!={OTHER[second]}){{return 4;}}return 42;",
                COPY,
            ),
        )
    for scalar in SCALARS:
        suite.check(
            "Scalar identity full-width native result " + scalar,
            p(
                f"return identity<{scalar}>({VALUES[scalar]});",
                "template<Scalar T>auto identity(T x)->T{return x;}",
                imports="",
                result=scalar,
            ),
            expected=BITS[scalar],
        )
        suite.check(
            "Value identity full-width native result " + scalar,
            p(f"return copy<{scalar}>({VALUES[scalar]});", COPY, imports="", result=scalar),
            expected=BITS[scalar],
        )
    suite.check(
        "Value empty class result retains initialization and const methods",
        p(
            "Empty source=Empty();Empty result=copy<Empty>(source);"
            "std::pair<Empty,Empty> pair=std::make_pair<Empty,Empty>(source,result);"
            "const Empty projected=pair.second;return projected.answer();",
            EMPTY + COPY,
        ),
    )
    suite.check(
        "bare dependent class-template arguments in result local and constructor",
        p(
            "Leaf leaf=Leaf(40u8);std::pair<Leaf,u8> value=make<Leaf,u8>(leaf,2u8);"
            "const Leaf result=value.first;return i64(result.get())+i64(value.second);",
            LEAF + MAKE,
        ),
    )
    range_class = (
        "class SourceRange{i64 begin_offset;i64 end_offset;public:"
        "SourceRange(i64 a,i64 b):begin_offset(a),end_offset(b){}"
        "auto begin()const->i64{return begin_offset;}auto end()const->i64{return end_offset;}"
        "auto shift(i64 amount)->i64{begin_offset=begin_offset+amount;e"
        "nd_offset=end_offset+amount;return begin_offset;}};"
    )
    suite.check(
        "bounded token source-range make_pair owns independent sixteen bytes",
        p(
            "std::array<u8,16> bytes=std::array<u8,16>();bytes.set(0,105u8);bytes.set(1,100u8);"
            "SourceRange source=SourceRange(10,12);"
            "std::pair<std::array<u8,16>,SourceRange> token=std::make_pair<"
            "std::array<u8,16>,SourceRange>(bytes,source);"
            "const std::pair<std::array<u8,16>,SourceRange> returned=copy<s"
            "td::pair<std::array<u8,16>,SourceRange>>(token);"
            "bytes.set(0,0u8);source.shift(100);std::array<u8,16> changed=returned.first;"
            "SourceRange moved=returned.second;changed.set(0,120u8);moved.shift(20);"
            "const std::array<u8,16> saved=token.first;const SourceRange range=token.second;"
            "if(saved.at(0)!=105u8){return 1;}if(saved.at(1)!=100u8){return 2;}"
            "if(range.begin()!=10){return 3;}if(changed.at(0)!=120u8){return 4;}"
            "i64 i=2;while(i<16){if(saved.at(i)!=0u8){return 5;}i=i+1;}"
            "static_assert(size_of(std::pair<std::array<u8,16>,SourceRange>)==32);"
            "static_assert(field_count(std::pair<std::array<u8,16>,SourceRange>)==2);"
            "return moved.begin()+range.end();",
            range_class + COPY,
        ),
    )
    rng = random.Random(seed)
    for capacity in (1, 3, 16, 63, 64):
        concrete = f"std::array<u8,{capacity}>"
        initial = [rng.randrange(256) for _ in range(capacity)]
        body = [f"{concrete} source={concrete}();"]
        body += [f"source.set({i},{v}u8);" for i, v in enumerate(initial)]
        body += [f"const {concrete} saved=copy<{concrete}>(source);", f"{concrete} changed=copy<{concrete}>(saved);"]
        model = initial.copy()
        for _ in range(steps):
            index, value = rng.randrange(capacity), rng.randrange(256)
            body.append(f"changed.set({index},{value}u8);")
            model[index] = value
        body.append(f"source.set(0,{(initial[0] + 1) % 256}u8);")
        for index, (old, new) in enumerate(zip(initial, model)):
            body.append(f"if(saved.at({index})!={old}u8){{return 1;}}if(changed.at({index})!={new}u8){{return 2;}}")
        suite.check(
            f"seeded independent generic byte-copy model capacity {capacity}", p("".join(body) + "return 42;", COPY)
        )


def boundary_cases(suite):
    for depth in (3, 4, 5):
        concrete = "i64"
        for _ in range(depth):
            concrete = f"Tag<{concrete}>"
        source = p(f"return probe<{concrete}>();", TAG + PROBE, imports="")
        if depth <= 4:
            suite.check(f"function explicit argument list does not consume nominal depth {depth}", source)
        else:
            suite.reject(
                "function argument nominal template depth five rejected",
                source,
                error=("depth", "four", "4", "nesting", "nested"),
            )
    for named_leaf in (False, True):
        concrete = "Leaf" if named_leaf else "u8"
        body = "Leaf value0=Leaf(42u8);" if named_leaf else "u8 value0=42u8;"
        for level in range(1, 5):
            concrete = f"Box<{concrete}>"
            body += f"{concrete} value{level}={concrete}(value{level - 1});"
        body += f"const {concrete} result=copy<{concrete}>(value4);return 42;"
        source = p(body, LEAF + BOX + COPY, imports="")
        if named_leaf:
            suite.reject(
                "four nominal template levels cannot bypass containment five", source, error=("depth", "four", "4")
            )
        else:
            suite.check("generic copy at exactly four independent containment levels", source)
    for leaves in (63, 64, 65):
        capacity = leaves - 1
        inner, outer = f"std::array<u8,{capacity}>", f"std::pair<std::array<u8,{capacity}>,u8>"
        source = p(
            f"{inner} bytes={inner}();bytes.set({capacity - 1},40u8);"
            f"{outer} value=std::make_pair<{inner},u8>(bytes,2u8);"
            f"const {outer} returned=copy<{outer}>(value);const {inner} saved=returned.first;"
            f"return i64(saved.at({capacity - 1}))+i64(returned.second);",
            COPY,
        )
        suite.check(f"function-template copied byte result flattened leaves {leaves}", source)
    for leaves in (4095, 4096):
        body = "const array<i64,4096> first={" + ",".join(["0"] * 4096) + "};"
        body += f"const array<i64,{leaves}> second={{" + ",".join(["0"] * leaves) + "};"
        source = p(
            body + "return take_word(Word(42));",
            "class Word{public:i64 value;Word(i64 n):value(n){}};auto take_word(Word value)->i64{return value.value;}",
            imports="",
        )
        if leaves == 4095:
            suite.check("copied temporary occupies final eight frame bytes", source)
        else:
            suite.reject("copied temporary exceeds full frame", source, error="65536")
    # i64 parameter (8) + 4096 i64 elements (32768) + 4095 i64 elements
    # (32760) is exactly 65536 bytes. One additional i64 exceeds the frame cap.
    frame_body = (
        "const array<i64,4096> first={" + ",".join(["0"] * 4096) + "};"
        "const array<i64,4095> second={" + ",".join(["0"] * 4095) + "};"
    )
    for extra in (False, True):
        source = p(
            "return frame<i64>(42);",
            "template<Scalar T>auto frame(T value)->T{"
            + frame_body
            + ("const i64 overflow=0;" if extra else "")
            + "return value;}",
            imports="",
        )
        if extra:
            suite.reject("instantiated function frame 65544 rejects beyond 65536", source, error=("frame", "65536"))
        else:
            suite.check("instantiated function frame exactly 65536 bytes", source)
    for count in (64, 65):
        classes = [TAG.replace("Tag", f"Tag{i}") for i in range(32)]
        functions = [PROBE.replace("probe", f"probe{i}") for i in range(count - 32)]
        definitions = "".join(classes + functions)
        body = "return probe0<Tag0<u8>>();"
        source = p(body, definitions, imports="")
        if count == 64:
            suite.check("combined class plus function definitions exactly 64", source)
        else:
            suite.reject("combined class plus function definitions 65", source, error=("64", "template"))
        modules = {
            "classes": "export module classes;" + "".join("export " + x for x in classes),
            "functions": "export module functions;" + "".join("export " + x for x in functions),
        }
        source = p(body, imports="import classes;import functions;")
        if count == 64:
            suite.check("combined 64 definitions counted across module graph", source, modules=modules)
        else:
            suite.reject(
                "combined 65 definitions rejected across module graph",
                source,
                modules=modules,
                error=("64", "template"),
            )
    # Each of 128 distinct std::array types and its probe specialization is one
    # instance: exactly 128 class + 128 function = 256, with no pair requests.
    types = [f"std::array<{scalar},{capacity}>" for scalar in ("u8", "i64") for capacity in range(1, 65)]
    requests = [f"probe<{concrete}>();" for concrete in types]
    suite.check(
        "combined 128 class plus 128 function specializations exactly 256",
        p("".join(requests) + "return 42;", PROBE, imports="import std.array;"),
    )
    suite.reject(
        "combined instance 257 one extra function specialization",
        p("".join(requests) + "probe<u8>();return 42;", PROBE, imports="import std.array;"),
        error=("256", "instantiat", "specializ"),
    )
    suite.reject(
        "combined instance 257 one extra class specialization",
        p(
            "".join(requests) + "static_assert(size_of(Tag<u8>)==8);return 42;",
            PROBE + TAG,
            imports="import std.array;",
        ),
        error=("256", "instantiat", "specializ"),
    )
    repeated = "probe< std::array< u8, 03 > >();probe<std::array<u8,3>>();" * 150
    suite.check(
        "canonical repeated requests share exact combined 256 instance budget",
        p("".join(requests) + repeated + "return 42;", PROBE, imports="import std.array;"),
    )
    modules = {
        "generic": "export module generic;export " + PROBE,
        "left": "export module left;import generic;import std.array;export auto left_value()->i64{"
        + "".join(requests[:64])
        + "return 20;}",
        "right": "export module right;import generic;import std.array;export auto right_value()->i64{"
        + "".join(requests[64:])
        + "return 22;}",
    }
    suite.check(
        "combined 256 specializations counted across modules",
        p("return left_value()+right_value();", imports="import left;import right;"),
        modules=modules,
    )
    too_many = dict(modules)
    too_many["right"] = too_many["right"].replace("return 22;", "probe<bool>();return 22;")
    suite.reject(
        "combined 257 specializations rejected across modules",
        p("return left_value()+right_value();", imports="import left;import right;"),
        modules=too_many,
        error=("256", "instantiat", "specializ"),
    )


def rejection_cases(suite):
    for label, definition, body in (
        ("empty parameter list", "template<>auto f(i64 x)->i64{return x;}", "return 42;"),
        ("third type parameter", "template<Value T,Value U,Value V>auto f(T x)->T{return x;}", "return 42;"),
        ("capacity function parameter", "template<Scalar T,i64 N>auto f(T x)->T{return x;}", "return 42;"),
        ("class keyword constraint", "template<class T>auto f(T x)->T{return x;}", "return 42;"),
        ("typename keyword constraint", "template<typename T>auto f(T x)->T{return x;}", "return 42;"),
        ("duplicate parameter name", "template<Value T,Value T>auto f(T x)->T{return x;}", "return 42;"),
        ("default type argument", "template<Value T=i64>auto f(T x)->T{return x;}", "return 42;"),
        ("variadic type arguments", "template<Value... T>auto f()->i64{return 42;}", "return 42;"),
        ("function explicit specialization", COPY + "template<>auto copy<i64>(i64 x)->i64{return x;}", "return 42;"),
        (
            "function partial specialization",
            COPY + "template<Value T>auto copy<Box<T>>(Box<T> x)->Box<T>{return x;}",
            "return 42;",
        ),
        ("overloaded function template", COPY + "template<Value T>auto copy(T a,T b)->T{return a;}", "return 42;"),
        ("ordinary function same name", COPY + "auto copy(i64 x)->i64{return x;}", "return 42;"),
        ("generic method", "class Bad{public:Bad(){}template<Value T>auto f(T x)->T{return x;}};", "return 42;"),
        ("local function template", "", "template<Value T>auto local(T x)->T{return x;}return 42;"),
        (
            "type constructor T value",
            "template<Value T>auto construct(T x)->T{const T result=T(x);return result;}",
            "return 42;",
        ),
        ("dependent scoped member", "template<Value T>auto member()->T{return T::ready;}", "return 42;"),
    ):
        suite.reject("unsupported declaration " + label, p(body, definition, imports=""))
    for call in (
        "copy(42)",
        "copy<>(42)",
        "copy<i64,u8>(42)",
        "copy<i64,u8,bool>(42)",
        "copy<i64>()",
        "copy<i64>(42,1)",
        "copy<u8>(42)",
        "copy<Unknown>(42)",
        "copy<42>(42)",
        "copy<own<i64>>(42)",
        "copy<ref<i64>>(42)",
        "copy<span<u8>>(42)",
        "copy<array<u8,3>>(42)",
        "copy<builtin::array<u8,3>>(42)",
        "copy<std::array<u8,0>>(42)",
        "copy<std::array<u8,65>>(42)",
        "copy<i64,>(42)",
        "copy<i64>>(42)",
        "copy<i64(42)",
    ):
        suite.reject("explicit function call rejected " + call, p("return " + call + ";", COPY))
    for concrete, setup, argument in (
        ("Leaf", "Leaf value=Leaf(42u8);", "value"),
        ("Empty", "Empty value=Empty();", "value"),
        ("Status", "Status value=Status::ready;", "value"),
        ("std::array<u8,3>", "std::array<u8,3> value=std::array<u8,3>();", "value"),
    ):
        suite.reject(
            "Scalar function constraint excludes " + concrete,
            p(
                setup + f"identity<{concrete}>({argument});return 42;",
                LEAF + EMPTY + "enum class Status{ready};template<Scalar T>auto identity(T x)->T{return x;}",
            ),
        )
    for label, definition in (
        ("nested dependent result", "template<Value T>auto bad(T x)->Box<Box<T>>{return x;}"),
        ("nested dependent parameter", "template<Value T>auto bad(Box<Box<T>> x)->i64{return 42;}"),
        ("nested dependent local", "template<Value T>auto bad(T x)->i64{Box<Box<T>> result=x;return 42;}"),
        (
            "nested dependent constructor",
            "template<Value T>auto bad(T x)->i64{Box<u8> result=Box<Box<T>>(x);return 42;}",
        ),
        ("nested dependent query", "template<Value T>auto bad()->i64{return size_of(Box<Box<T>>);}"),
        (
            "dependent capacity tree",
            "template<Value T,Value U>auto bad(T x,U y)->std::pair<std::array<T,16>,U>{return x;}",
        ),
    ):
        suite.reject("unused function structurally rejects " + label, p("return 42;", BOX + definition))
    # Qualified dependent names must be rejected while checking the unused
    # definition, including names hidden inside an otherwise-concrete argument
    # tree. Requested variants also verify the ordinary expansion path rejects.
    qualified_arguments = [
        (
            "local",
            "template<Value T>auto bad()->i64{const Tag<T::Hidden> value=Tag<T::Hidden>();return 42;}",
            "return bad<u8>();",
        ),
        (
            "nested local",
            "template<Value T>auto bad()->i64{const Tag<Tag<T::Hidden>> value=Tag<Tag<T::Hidden>>();return 42;}",
            "return bad<u8>();",
        ),
        (
            "constructor expression",
            "template<Value T>auto bad()->i64{const Tag<u8> value=Tag<T::Hidden>();return 42;}",
            "return bad<u8>();",
        ),
        (
            "parameter signature",
            "template<Value T>auto bad(Tag<T::Hidden> source)->i64{return 42;}",
            "Tag<u8> source=Tag<u8>();return bad<u8>(source);",
        ),
        (
            "result signature",
            "template<Value T>auto bad()->Tag<T::Hidden>{const Tag<T::Hidden> result=Tag<T::Hidden>();return result;}",
            "const Tag<u8> result=bad<u8>();return 42;",
        ),
    ]
    for query in ("size_of", "type_id", "field_count"):
        qualified_arguments.append(
            (
                "reflected type " + query,
                f"template<Value T>auto bad()->i64{{return {query}(Tag<T::Hidden>);}}",
                "return bad<u8>();",
            )
        )
    for position, definition, request in qualified_arguments:
        for used in (False, True):
            suite.reject(
                "dependent qualified template argument " + position + (" requested" if used else " unused"),
                p(request if used else "return 42;", TAG + definition, imports=""),
            )
    # The name T is a parameter here, even when an unrelated namespace with
    # that spelling would make T::Hidden a resolvable concrete nominal type.
    namespace_collision = (
        "namespace T{class Hidden{public:Hidden(){} };}"
        + TAG
        + "template<Value T>auto bad()->i64{const Tag<T::Hidden> result=Tag<T::Hidden>();return 42;}"
    )
    for used in (False, True):
        suite.reject(
            "dependent qualified argument cannot bind same-name namespace " + ("requested" if used else "unused"),
            p("return bad<i64>();" if used else "return 42;", namespace_collision, imports=""),
        )
    # All enclosing bodies are unused. A concrete request is still a forbidden
    # function-template call and must not be deferred until instantiation.
    for label, body in (
        ("return", "return copy<i64>(42);"),
        ("local initializer", "const i64 result=copy<i64>(42);return result;"),
        ("dead branch", "if(false){copy<i64>(42);}return 42;"),
        ("dead loop", "while(false){copy<i64>(42);}return 42;"),
        ("static assertion", "static_assert(copy<i64>(42)==42);return 42;"),
        ("nested ordinary call", "return helper(copy<i64>(42));"),
        ("dependent call", "return copy<T>(x);"),
        ("self recursion", "return bad<T>(x);"),
        ("qualified library call", "std::pair<i64,u8> result=std::make_pair<i64,u8>(40,2u8);return 42;"),
    ):
        suite.reject(
            "unused function template forbids function-template call in " + label,
            p(
                "return 42;",
                COPY + f"template<Value T>auto bad(T x)->i64{{{body}}}",
                helpers="auto helper(i64 x)->i64{return x;}",
            ),
        )
    for label, body in (
        ("return", "return copy<i64>(42);"),
        ("dead branch", "if(false){copy<i64>(42);}return 42;"),
        ("local initializer", "const i64 result=copy<i64>(42);return result;"),
        ("static assertion", "static_assert(copy<i64>(42)==42);return 42;"),
    ):
        suite.reject(
            "unused class template forbids function-template call in " + label,
            p("return 42;", COPY + "template<Value T>class Bad{public:Bad(){}auto get()const->i64{" + body + "}};"),
        )
    suite.reject(
        "unused class constructor forbids function-template initializer call",
        p("return 42;", COPY + "template<Value T>class Bad{i64 value;public:Bad():value(copy<i64>(42)){} };"),
    )
    suite.reject(
        "nonempty template constructor body remains unsupported",
        p("return 42;", COPY + "template<Value T>class Bad{public:Bad(){copy<i64>(42);} };"),
    )
    prefix = "Leaf source=Leaf(42u8);"
    for label, body, generic in (
        ("class argument temporary", "Leaf result=copy<Leaf>(Leaf(42u8));return 42;", COPY),
        ("class nested result argument", "Leaf result=copy<Leaf>(copy<Leaf>(source));return 42;", COPY),
    ):
        suite.check("copied template " + label, p(prefix + body, LEAF + EMPTY + generic))
    suite.check(
        "copied template constructor method and function nesting",
        p(
            "Leaf source=Leaf(42u8);Leaf result=copy<Leaf>(forward(copy<Leaf>(Leaf(source.get()))));"
            "source.set(0u8);return i64(result.get());",
            LEAF.replace("};", "auto copied()const->Leaf{return Leaf(value);}};")
            + COPY
            + "auto forward(Leaf value)->Leaf{return value.copied();}",
        ),
    )
    for label, body, generic in (
        (
            "mutable parameter field",
            "return mutate<Leaf>(source);",
            "template<Value T>auto mutate(T x)->i64{x.value=1u8;return 42;}",
        ),
        (
            "mutable parameter method",
            "return mutate<Leaf>(source);",
            "template<Value T>auto mutate(T x)->i64{x.set(1u8);return 42;}",
        ),
        (
            "private field access",
            "return expose<Leaf>(source);",
            "template<Value T>auto expose(T x)->i64{return i64(x.value);}",
        ),
        ("wrong nominal argument", "Empty result=copy<Empty>(source);return 42;", COPY),
        ("wrong nominal result", "Empty result=copy<Leaf>(source);return 42;", COPY),
        ("resource result", "return bad<i64>(42);", "template<Value T>auto bad(T x)->own<i64>{return new i64(x);}"),
    ):
        suite.reject("ordinary value restrictions preserved " + label, p(prefix + body, LEAF + EMPTY + generic))
    suite.reject("function template is not a class reflection type", p("return type_id(copy<i64>);", COPY, imports=""))


def module_cases(suite):
    generic = {"generic": "export module generic;export " + COPY}
    helpers = {
        "generic": "export module generic;auto helper()->i64{return 22;}"
        "export template<Scalar T>auto plus_helper(T x)->i64{return i64(x)+helper();}"
    }
    suite.check(
        "fixed helper binds defining module rather than caller shadow",
        p("return plus_helper<u8>(20u8);", helpers="auto helper()->i64{return 999;}", imports="import generic;"),
        modules=helpers,
    )
    scoped = {
        "generic": "export module generic;namespace detail{auto helper()->i64{return 22;}"
        "export template<Scalar T>auto plus_helper(T x)->i64{return i64(x)+helper();}}"
    }
    suite.check(
        "fixed helper binds template defining namespace",
        p(
            "return detail::plus_helper<u8>(20u8);",
            helpers="auto helper()->i64{return 999;}",
            imports="import generic;",
        ),
        modules=scoped,
    )
    private = {"generic": "export module generic;" + COPY + "export auto ordinary()->i64{return copy<i64>(42);}"}
    suite.check(
        "private template is callable by ordinary defining-module helper",
        p("return ordinary();", imports="import generic;"),
        modules=private,
    )
    suite.reject(
        "private function template cannot be named outside defining module",
        p("return copy<i64>(42);", imports="import generic;"),
        modules=private,
        error=("private", "visible", "unknown", "template"),
    )
    transitive = dict(generic)
    transitive["bridge"] = "export module bridge;import generic;export auto answer()->i64{return copy<i64>(42);}"
    suite.check(
        "ordinary wrapper may use directly imported function template",
        p("return answer();", imports="import bridge;"),
        modules=transitive,
    )
    suite.reject(
        "transitive import cannot name function template",
        p("return copy<i64>(42);", imports="import bridge;"),
        modules=transitive,
    )
    suite.check(
        "direct import restores function-template visibility",
        p("return copy<i64>(42);", imports="import bridge;import generic;"),
        modules=transitive,
    )
    for hidden_kind, hidden, hidden_value in (
        ("class", LEAF.replace("Leaf", "Hidden"), "Hidden(42u8)"),
        ("enum", "enum class Hidden{ready};", "Hidden::ready"),
    ):
        for label, template in (
            ("fixed parameter", "template<Value T>auto bad(Hidden secret,T x)->T{return x;}"),
            (
                "fixed result",
                "template<Value T>auto bad(T x)->Hidden{const Hidden result=" + hidden_value + ";return result;}",
            ),
            (
                "nested fixed parameter",
                "template<Value T>auto bad(std::pair<Hidden,T> x)->T{const T result=x.second;return result;}",
            ),
            (
                "nested fixed result",
                "template<Value T>auto bad(T x)->std::pair<Hidden,T>{const Hidden secret="
                + hidden_value
                + ";const std::pair<Hidden,T> result=std::pair<Hidden,T>(secret,x);return result;}",
            ),
        ):
            suite.reject(
                f"exported function template cannot launder private {hidden_kind} in {label}",
                p("return 42;", imports="import hidden;"),
                modules={"hidden": "export module hidden;import std.utility;" + hidden + "export " + template},
                error=("private", "visible", "export"),
            )
    signature_modules = {
        "types": "export module types;export " + LEAF,
        "generic": (
            "export module generic;import types;export template<Value T>auto identity(Leaf source,T extra)->Lea"
            "f{return source;}"
        ),
    }
    suite.check(
        "fixed signature type works with explicit direct type import",
        p(
            "Leaf source=Leaf(42u8);Leaf result=identity<u8>(source,0u8);return i64(result.get());",
            imports="import types;import generic;",
        ),
        modules=signature_modules,
    )
    suite.reject(
        "fixed signature type cannot be obtained through transitive import",
        p(
            "Leaf source=Leaf(42u8);Leaf result=identity<u8>(source,0u8);return i64(result.get());",
            imports="import generic;",
        ),
        modules=signature_modules,
    )
    specialized = {
        "generic": "export module generic;import std.utility;export " + MAKE,
        "bridge": "export module bridge;import generic;import std.utility;"
        "export auto pair_id()->i64{std::pair<i64,u8> value=make<i64,u8>(40,2u8);return type_id(std::pair<i64,u8>);}",
    }
    suite.check(
        "runtime reflection hides transitive specialization declaration",
        p(
            "if(reflect_size(pair_id())!=0){return 1;}if(reflect_field_count(pair_id())!=0){return 2;}return 42;",
            imports="import bridge;",
        ),
        modules=specialized,
        # Visibility depends on this unit's own imports; a pack's union import would widen it.
        standalone=True,
    )
    suite.check(
        "directly imported specialization metadata matches instantiated class",
        p(
            "if(reflect_size(pair_id())!=16){return 1;}if(reflect_field_count(pair_id())!=2){return 2;}return 42;",
            imports="import bridge;import std.utility;",
        ),
        modules=specialized,
    )
    same_names = {}
    for module, value in (("left", 20), ("right", 22)):
        same_names[module] = (
            f"export module {module};import generic;import std.utility;"
            + LEAF.replace("Leaf", "Point")
            + f"export auto {module}_value()->i64{{Point source=Point({value}u8);"
            "Point result=copy<Point>(source);return i64(result.get());}"
            f"export auto {module}_id()->i64{{Point source=Point({value}u8);"
            "std::pair<Point,u8> result=std::make_pair<Point,u8>(source,0u8);return type_id(std::pair<Point,u8>);}"
        )
    same_names.update(generic)
    suite.check(
        "same-spelling caller-private class arguments use distinct module identities",
        p(
            "if(left_id()==right_id()){return 1;}return left_value()+right_value();",
            imports="import left;import right;",
        ),
        modules=same_names,
    )
    suite.check(
        "runtime reflection stays closed over private function specialization arguments",
        p(
            "if(reflect_size(left_id())!=0){return 1;}if(reflect_field_count(right_id())!=0){return 2;}return 42;",
            imports="import left;import right;import std.utility;",
        ),
        modules=same_names,
    )
    exposed = {"generic": "export module generic;export template<Value T>auto expose(T x)->u8{return x.value;}"}
    suite.reject(
        "imported template cannot inspect private caller class field",
        p("Leaf source=Leaf(42u8);return i64(expose<Leaf>(source));", LEAF, imports="import generic;"),
        modules=exposed,
    )


def trap_cases(suite):
    for scalar, maximum, one in (
        ("i64", "9223372036854775807", "1"),
        ("u64", "18446744073709551615u64", "1u64"),
        ("u8", "255u8", "1u8"),
    ):
        suite.check(
            "generic checked addition exact overflow trap " + scalar,
            p(
                f"return add<{scalar}>({maximum},{one});",
                "template<Scalar T>auto add(T a,T b)->T{return a+b;}",
                imports="",
                result=scalar,
            ),
            expected=Trap.OVERFLOW,
        )
    for scalar, one, zero in (("i64", "1", "0"), ("u64", "1u64", "0u64"), ("u8", "1u8", "0u8")):
        suite.check(
            "generic checked division exact zero trap " + scalar,
            p(
                f"return divide<{scalar}>({one},{zero});",
                "template<Scalar T>auto divide(T a,T b)->T{return a/b;}",
                imports="",
                result=scalar,
            ),
            expected=Trap.ZERO,
        )
    for capacity in (1, 16, 64):
        for index in (-1, capacity, 9223372036854775807):
            for operation in ("at", "set"):
                concrete = f"std::array<u8,{capacity}>"
                arguments = str(index) + (",1u8" if operation == "set" else "")
                suite.check(
                    f"generic array result exact bounds trap {operation}/{capacity}/{index}",
                    p(
                        f"{concrete} source={concrete}();{concrete} result=copy<{concrete}>(source);"
                        f"return i64(result.{operation}({arguments}));",
                        COPY,
                    ),
                    expected=Trap.BOUNDS,
                )
    for scalar, value, shift, expected in (
        ("u64", "18446744073709551615u64", 1, (1 << 63) - 1),
        ("u8", "255u8", 1, 127),
        ("u64", "9223372036854775808u64", 63, 1),
        ("u8", "128u8", 7, 1),
    ):
        suite.check(
            f"explicit function type closers preserve ordinary right shift {scalar}/{shift}",
            p(f"return copy<{scalar}>({value}) >> {shift};", COPY, imports="", result=scalar),
            expected=expected,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path, nargs="?", default=ROOT / "build/aurorac")
    parser.add_argument("--seed", type=int, default=21021)
    parser.add_argument("--steps", type=int, default=24)
    args = parser.parse_args()
    require(1 <= args.steps <= 128, "steps must be between 1 and 128")
    suite = Suite(args.compiler, "function templates", ignore_case=True, pack_templates=32)
    suite.load(Path(__file__).with_suffix(".cases"), COPY=COPY, LEAF=LEAF)
    native_cases(suite, args.seed, args.steps)
    boundary_cases(suite)
    rejection_cases(suite)
    module_cases(suite)
    trap_cases(suite)
    suite.finish()


if __name__ == "__main__":
    main()
