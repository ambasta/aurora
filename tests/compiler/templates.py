#!/usr/bin/env python3
"""Bounded Scalar class templates: execution and unsafe-instantiation rejections (native_runner.py)."""

from itertools import combinations, product
from pathlib import Path
import sys

from native_runner import Suite, Trap

SUITE = Suite(Path(sys.argv[1]), "templates", ignore_case=True)


def check(
    name, source, modules=None, expected=42, error=None, library=False, trap=False, existing_output=None, alone=False
):
    SUITE.check(
        name,
        source,
        Trap.OVERFLOW if trap else expected,
        error,
        modules=modules,
        existing_output=existing_output.encode() if existing_output else None,
        standalone=alone,
    )


PAIR = """template <Scalar T, Scalar U> class Pair {
public:
    T first;
    U second;
    Pair(T first_value, U second_value): first(first_value), second(second_value) {}
};"""

BOX = """template <Scalar T> class Box {
    T value;
public:
    Box(T initial): value(initial) {}
    auto get() const -> T { const T local=value; return local; }
    auto set(T replacement) -> T { value=replacement; return value; }
    auto echo(T argument) const -> T { T local=argument; return local; }
    auto facts() const -> i64 {
        static_assert(size_of(T)>0);
        static_assert(field_count(T)==0);
        return type_id(T)+reflect_size(type_id(T))+reflect_field_count(type_id(T));
    }
};"""


def program(body, definitions=PAIR, helpers="", imports="", result="i64"):
    return "module app;" + imports + definitions + helpers + "auto test()->" + result + "{" + body + "}"


SCALARS = ("i64", "u64", "bool")
VALUES = {"i64": "-9223372036854775808", "u64": "18446744073709551615u64", "bool": "true"}
OTHERS = {"i64": "9223372036854775807", "u64": "9223372036854775808u64", "bool": "false"}

# Every ordered tuple uses the same source definition and crosses constructors,
# complete result copies, immutable by-value parameters and independent locals.
for first, second in product(SCALARS, repeat=2):
    concrete = f"Pair<{first},{second}>"
    a, b = VALUES[first], OTHERS[second]
    changed_a, changed_b = OTHERS[first], VALUES[second]
    helpers = (
        f"auto make()->{concrete}{{const {concrete} p={concrete}({a},{b});return p;}}"
        f"auto copy({concrete} p)->{concrete}{{return p;}}"
        f"auto consume({concrete} p)->i64{{"
        f"if(p.first=={a}){{if(p.second=={b}){{return 42;}}}}return 0;}}"
    )
    body = (
        f"{concrete} original=make();{concrete} copied=copy(original);"
        f"{concrete} local=copied;local.first={changed_a};local.second={changed_b};"
        f"if(original.first!={a}){{return 1;}}if(original.second!={b}){{return 2;}}"
        f"if(local.first!={changed_a}){{return 3;}}if(local.second!={changed_b}){{return 4;}}"
        "return consume(copied);"
    )
    check(f"ordered tuple {first} {second} native copies and value ABI", program(body, helpers=helpers))

for scalar in SCALARS:
    concrete = f"Box<{scalar}>"
    value, replacement = VALUES[scalar], OTHERS[scalar]
    check(
        f"private {scalar} field placeholder locals arguments and results",
        program(
            f"const {concrete} original={concrete}({value});{concrete} copy=original;"
            f"copy.set({replacement});if(original.get()!={value}){{return 1;}}"
            f"if(copy.get()!={replacement}){{return 2;}}"
            f"if(copy.echo({value})!={value}){{return 3;}}"
            f"if(copy.facts()!=type_id({scalar})+size_of({scalar})){{return 4;}}"
            f"static_assert(field_count({concrete})==0);"
            f"return reflect_field_count(type_id({concrete}))+42;",
            BOX,
        ),
    )
    check(
        f"private {scalar} raw result preserves all bits",
        program(f"const {concrete} b={concrete}({value});return b.get();", BOX, result=scalar),
        expected={"i64": -(1 << 63), "u64": (1 << 64) - 1, "bool": 1}[scalar],
    )

for first, second in product(SCALARS, repeat=2):
    concrete = f"std::pair<{first},{second}>"
    a, b = VALUES[first], OTHERS[second]
    check(
        f"std.utility pair {first} {second}",
        program(
            f"{concrete} p={concrete}({a},{b});const {concrete} q=copy(p);"
            f"if(q.first!={a}){{return 1;}}if(q.second!={b}){{return 2;}}"
            f"static_assert(size_of({concrete})==16);"
            f"static_assert(field_count({concrete})==2);return 42;",
            "",
            f"auto copy({concrete} p)->{concrete}{{return p;}}",
            "import std.utility;",
        ),
        library=True,
    )

concrete_types = [f"Pair<{a},{b}>" for a, b in product(SCALARS, repeat=2)]
identity_checks = "".join(f"static_assert(type_id({a})!=type_id({b}));" for a, b in combinations(concrete_types, 2))
identity_checks += "".join(
    f"static_assert(size_of({name})==16);static_assert(field_count({name})==2);"
    f"if(reflect_size(type_id({name}))!=16){{return 1;}}"
    f"if(reflect_field_count(type_id({name}))!=2){{return 2;}}"
    for name in concrete_types
)
check("ordered argument tuple nominal identity and runtime metadata", program(identity_checks + "return 42;"))
matrix_helpers = ""
matrix_body = ""
for index, (first, second) in enumerate(product(SCALARS, repeat=2)):
    concrete = f"Pair<{first},{second}>"
    a, b = VALUES[first], OTHERS[second]
    matrix_helpers += (
        f"auto make{index}()->{concrete}{{"
        f"const {concrete} p={concrete}({a},{b});return p;}}"
        f"auto copy{index}({concrete} p)->{concrete}{{return p;}}"
    )
    matrix_body += (
        f"const {concrete} a{index}=make{index}();"
        f"const {concrete} b{index}=copy{index}(a{index});"
        f"if(b{index}.first!={a}){{return 1;}}"
        f"if(b{index}.second!={b}){{return 2;}}"
    )
check(
    "all nine specializations coexist through constructor and value ABI",
    program(matrix_body + "return 42;", helpers=matrix_helpers),
)
check(
    "generic constructor parameter shadows same-named field",
    program(
        "Box<i64> b=Box<i64>(42);return b.get();",
        BOX.replace("Box(T initial): value(initial)", "Box(T value): value(value)"),
    ),
)
check(
    "generic aggregate designated initialization",
    program(
        "Pair<i64,u64> p=Pair<i64,u64>{.first=20,.second=22u64};return p.first+i64(p.second);",
        PAIR[: PAIR.index("    Pair(")] + "};",
    ),
)
wide_fields = "".join(f"T f{i};" for i in range(64))
wide_values = ",".join(f".f{i}={18446744073709551615 - i}u64" for i in range(64))
check(
    "maximum-width generic value survives six parameter snapshots and result",
    program(
        "const Wide<u64> original=Wide<u64>{" + wide_values + "};"
        "Wide<u64> copied=select(original,original,original,original,original,original);"
        "copied.f0=0u64;if(original.f0!=18446744073709551615u64){return 0u64;}"
        "return copied.f63;",
        "template<Scalar T>class Wide{public:" + wide_fields + "};",
        "auto select(Wide<u64> a,Wide<u64> b,Wide<u64> c,Wide<u64> d,Wide<u64> e,Wide<u64> f)->Wide<u64>{return f;}",
        result="u64",
    ),
    expected=(1 << 64) - 64,
)

# Instantiated methods retain the definition's scope, including private helpers.
MODULE_BOX = "export module boxes;export " + BOX
check(
    "imported generic getter",
    program("Box<i64> b=Box<i64>(42);return b.get();", "", imports="import boxes;"),
    {"boxes": MODULE_BOX},
)
check(
    "private template unavailable to importing caller",
    program("Box<i64> b=Box<i64>(42);return b.get();", "", imports="import boxes;"),
    {"boxes": "export module boxes;" + BOX},
    error=("private", "unknown", "visible"),
)
for signature in (
    "export auto make()->Box<i64>{Box<i64> b=Box<i64>(42);return b;}",
    "export auto consume(Box<i64> b)->i64{return b.get();}",
):
    check(
        "export cannot expose private specialization " + ("result" if "make" in signature else "parameter"),
        program("return 42;", "", imports="import boxes;"),
        {"boxes": "export module boxes;" + BOX + signature},
        error="exposes private type",
    )

TRANSITIVE = {
    "boxes": MODULE_BOX,
    "factory": "export module factory;import boxes;export auto make()->Box<i64>{Box<i64> b=Box<i64>(42);return b;}",
}
check(
    "transitive specialization does not become directly visible",
    program("return make();", "", imports="import factory;"),
    TRANSITIVE,
    error="direct visible import",
)
check(
    "direct template import permits concrete factory result",
    program("Box<i64> b=make();return b.get();", "", imports="import factory;import boxes;"),
    TRANSITIVE,
)
check(
    "same imported specialization unifies across modules",
    program("Box<i64> b=make();return consume(b);", "", imports="import factory;import boxes;import consumer;"),
    dict(
        TRANSITIVE, consumer="export module consumer;import boxes;export auto consume(Box<i64> b)->i64{return b.get();}"
    ),
)


for label, body, error in [
    ("private substituted field read", "Box<i64> b=Box<i64>(42);return b.value;", "private class field"),
    ("private substituted field write", "Box<i64> b=Box<i64>(42);b.value=1;return 42;", "private class field"),
    ("const generic receiver", "const Box<i64> b=Box<i64>(42);return b.set(1);", "mutable receiver"),
    ("method substituted scalar argument", "Box<u64> b=Box<u64>(42u64);return b.set(1);", "expected"),
    ("generic ownership escape", "Box<i64> b=Box<i64>(42);const ref<i64> r=borrow(b);return read(r);", "expected own"),
]:
    check(label, program(body, BOX), error=error)

# These definitions become invalid under ordinary semantic checks once used.
for label, definition, body, error in [
    (
        "missing field initialization after substitution",
        PAIR.replace(", second(second_value)", ""),
        "Pair<i64,u64> p=Pair<i64,u64>(1,2u64);return 42;",
        "every field",
    ),
    (
        "duplicate initializer after substitution",
        PAIR.replace("first(first_value)", "first(first_value),first(first_value)"),
        "Pair<i64,u64> p=Pair<i64,u64>(1,2u64);return 42;",
        "duplicate constructor",
    ),
    (
        "wrong initializer type after substitution",
        PAIR.replace("second(second_value)", "second(first_value)"),
        "Pair<i64,u64> p=Pair<i64,u64>(1,2u64);return 42;",
        "expected",
    ),
    (
        "const method mutation after substitution",
        BOX.replace("const T local=value;", "value=value;const T local=value;"),
        "Box<i64> b=Box<i64>(42);return b.get();",
        "const method",
    ),
    (
        "wrong method result after substitution",
        BOX.replace("const T local=value; return local;", "return true;"),
        "Box<i64> b=Box<i64>(42);return b.get();",
        "expected",
    ),
    (
        "wrong generic local after substitution",
        BOX.replace("const T local=value;", "const T local=true;"),
        "Box<u64> b=Box<u64>(42u64);return 42;",
        "expected",
    ),
    (
        "generic method cycle after substitution",
        BOX.replace("const T local=value; return local;", "return get();"),
        "Box<i64> b=Box<i64>(42);return b.get();",
        "cycle",
    ),
    (
        "generic body owner move while borrowed",
        BOX.replace(
            "const T local=value; return local;",
            "own<i64> n=own(42);const ref<i64> r=borrow(n);own<i64> moved=move(n);return read(r);",
        ),
        "Box<i64> b=Box<i64>(42);return b.get();",
        "borrow",
    ),
    (
        "private generic constructor",
        BOX.replace("public:\n    Box", "private:\n    Box").replace("    auto get", "public: auto get", 1),
        "Box<i64> b=Box<i64>(42);return b.get();",
        "private constructor",
    ),
]:
    check(label, program(body, definition), error=error)

for scalar, value in (("i64", "9223372036854775807"), ("u64", "18446744073709551615u64")):
    increment = "1" if scalar == "i64" else "1u64"
    definition = BOX.replace("value=replacement;", f"value=replacement+{increment};")
    check(
        f"generic {scalar} method retains checked overflow",
        program(f"Box<{scalar}> b=Box<{scalar}>({value});return b.set({value});", definition, result=scalar),
        trap=True,
    )
check(
    "bool generic arithmetic rejected",
    program(
        "Box<bool> b=Box<bool>(true);if(b.set(false)){return 42;}return 0;",
        BOX.replace("value=replacement;", "value=replacement+replacement;"),
    ),
    error="expected",
)

for label, concrete in [
    ("zero arguments", "Pair<>"),
    ("one argument", "Pair<i64>"),
    ("three arguments", "Pair<i64,u64,bool>"),
    ("unknown argument", "Pair<Missing,i64>"),
    ("class argument", "Pair<Other,i64>"),
    ("array argument", "Pair<array<i64,1>,i64>"),
    ("owner argument", "Pair<own<i64>,i64>"),
    ("reference argument", "Pair<ref<i64>,i64>"),
    ("nested specialization argument", "Pair<Box<i64>,i64>"),
    ("value argument", "Pair<42,i64>"),
    ("qualified scalar argument", "Pair<std::i64,i64>"),
]:
    check(
        "unsupported template " + label,
        program(f"return size_of({concrete});", PAIR + BOX + "class Other{public:i64 value;};"),
        error=("scalar", "template", "argument", "expected"),
    )

for label, definition in [
    ("missing constraint", "template<T>class Bad{public:T value;};"),
    ("unknown constraint", "template<Numeric T>class Bad{public:T value;};"),
    ("three parameters", "template<Scalar T,Scalar U,Scalar V>class Bad{public:T value;};"),
    ("duplicate parameter", "template<Scalar T,Scalar T>class Bad{public:T value;};"),
    ("builtin parameter name", "template<Scalar i64>class Bad{public:i64 value;};"),
    ("function capacity template parameter", "template<Scalar T,i64 N>auto identity(T value)->T{return value;}"),
    ("explicit specialization", "template<>class Bad{public:i64 value;};"),
    ("default argument", "template<Scalar T=i64>class Bad{public:T value;};"),
    ("non-type parameter", "template<i64 N>class Bad{public:i64 value;};"),
]:
    check(
        "unsupported template declaration " + label,
        program("return 42;", definition),
        error=("template", "parameter", "scalar", "expected", "duplicate", "reserved"),
    )

for label, inside in [
    ("nested field", "Box<i64> value;"),
    ("recursive field", "Bad<i64> value;"),
    ("method local", "public:auto get()->i64{Box<i64> b=Box<i64>(42);return b.get();}"),
    ("reflection query", "public:auto get()->i64{return size_of(Box<i64>);}"),
]:
    check(
        "template-local instantiation rejected " + label,
        program("return size_of(Bad<i64>);", BOX + "template<Scalar T>class Bad{" + inside + "};"),
        error=("template", "nested", "recursive", "scalar", "expected"),
    )


def template_definitions(start, count, exported=False):
    return "".join(
        ("export " if exported else "") + PAIR.replace("Pair", f"Generic{i}") for i in range(start, start + count)
    )


for count in (64, 65):
    check(
        f"template declaration boundary {count}",
        program(
            "Generic0<i64,u64> p=Generic0<i64,u64>(20,22u64);return p.first+i64(p.second);",
            template_definitions(0, count),
        ),
        error=None if count == 64 else ("64", "template limit"),
        alone=True,  # uses the whole graph's template budget
    )
    split = count // 2
    check(
        f"template graph declaration boundary {count}",
        program("return size_of(Generic0<i64,u64>)+26;", "", imports="import left;import right;"),
        {
            "left": "export module left;" + template_definitions(0, split, True),
            "right": "export module right;" + template_definitions(split, count - split, True),
        },
        error=None if count == 64 else ("64", "template limit"),
        alone=True,  # uses the whole graph's template budget
    )

# Twenty-nine templates provide 261 distinct tuples; instantiate exactly the
# boundary count through reflection so every concrete class is actually created.
for count in (256, 257):
    types = [f"Generic{i}<{a},{b}>" for i in range(29) for a, b in product(SCALARS, repeat=2)][:count]
    body = "".join(f"static_assert(size_of({name})==16);" for name in types) + "return 42;"
    check(
        f"concrete class boundary {count}",
        program(body, template_definitions(0, 29)),
        error=None if count == 256 else ("256", "class limit", "classes"),
        alone=True,  # uses the whole graph's instantiation budget
    )
    check(
        f"concrete graph class boundary {count}",
        program(body, "", imports="import left;import right;"),
        {
            "left": "export module left;" + template_definitions(0, 14, True),
            "right": "export module right;" + template_definitions(14, 15, True),
        },
        error=None if count == 256 else ("256", "class limit", "classes"),
        alone=True,  # uses the whole graph's instantiation budget
    )

check(
    "repeated concrete use does not consume instantiation budget",
    program("".join("static_assert(size_of(Pair<i64,u64>)==16);" for _ in range(300)) + "return 42;"),
)
check(
    "template rejection preserves existing artifact",
    program("Pair<i64,u64> p=Pair<i64,u64>(1,2);return 42;"),
    error="expected",
    existing_output="previous known-good output\n",
)

check(
    "injected self type constructor and reflection",
    """module app;
template <Scalar T> class Holder { T value; public: Holder(T n):value(n){}
 auto compute(T n) const -> T { static_assert(size_of(Holder)==8);
   const Holder local=Holder(n); return local.value; }
};
auto test()->i64 { const Holder<i64> x=Holder<i64>(0); return x.compute(42); }
""",
)
check(
    "injected self type designated construction",
    """module app;
template <Scalar T> class Holder { public: T value;
 auto compute(T n) const -> T { const Holder local=Holder{.value=n}; return local.value; }
};
auto test()->u64 { const Holder<u64> x=Holder<u64>{.value=0u64}; return x.compute(18446744073709551615u64); }
""",
    expected=(1 << 64) - 1,
)


SUITE.load(Path(__file__).with_suffix(".cases"), BOX=BOX, PAIR=PAIR)
SUITE.finish()
