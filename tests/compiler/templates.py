#!/usr/bin/env python3
"""Execute bounded Scalar class templates and reject unsafe instantiations."""
from itertools import combinations, product
from pathlib import Path
import resource
import signal
import subprocess
import sys
import tempfile


COMPILER = Path(sys.argv[1]).resolve()
LIBRARY = Path(__file__).resolve().parents[2] / "library"
COUNT = 0


def require(value, message):
    if not value:
        raise AssertionError(message)


def run(command, good=True):
    result = subprocess.run(
        [str(x) for x in command], capture_output=True, timeout=5,
        preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))
    if good:
        require(result.returncode == 0,
                f"{command}: {result.returncode}: {result.stderr!r}")
    return result


def check(name, source, modules=None, expected=42, error=None, library=False,
          trap=False, existing_output=None):
    global COUNT
    with tempfile.TemporaryDirectory(prefix="aurora-templates-") as directory:
        base = Path(directory)
        root = base / "modules"
        root.mkdir()
        for module, contents in (modules or {}).items():
            path = root / (module.replace(".", "/") + ".au")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents)
        source_path = base / "input.au"
        source_path.write_text(source)
        assembly = base / "program.s"
        if existing_output is not None:
            assembly.write_text(existing_output)
        command = [COMPILER, source_path, "-o", assembly, "--module-root", root]
        if library:
            command.extend(["--module-root", LIBRARY])
        compiled = run(command, good=error is None)
        require(source_path.read_text() == source, name + ": source changed")
        if error is not None:
            require(compiled.returncode == 1,
                    f"{name}: expected normal compiler rejection, got "
                    f"{compiled.returncode}: {compiled.stderr!r}")
            if existing_output is None:
                require(not assembly.exists(), name + ": artifact on rejection")
            else:
                require(assembly.read_text() == existing_output,
                        name + ": existing output changed on rejection")
            fragments = (error,) if isinstance(error, str) else error
            require(any(fragment.lower().encode() in compiled.stderr.lower()
                        for fragment in fragments), name + ": " + repr(compiled.stderr))
        else:
            bridge = base / "entry.s"
            bridge.write_text(""".text
.globl _start
_start:
    call test
    pushq %rax
    movq $1, %rax
    movq $1, %rdi
    movq %rsp, %rsi
    movq $8, %rdx
    syscall
    movq $60, %rax
    xorq %rdi, %rdi
    syscall
.section .note.GNU-stack,"",@progbits
""")
            run(["as", "--64", assembly, "-o", base / "program.o"])
            run(["as", "--64", bridge, "-o", base / "entry.o"])
            run(["ld", "-o", base / "program", base / "entry.o", base / "program.o"])
            executed = run([base / "program"], good=not trap)
            if trap:
                require(executed.returncode == -signal.SIGILL and not executed.stdout,
                        name + ": expected exact SIGILL without a result")
            else:
                require(len(executed.stdout) == 8, name + ": missing 64-bit result")
                actual = int.from_bytes(executed.stdout, "little", signed=False)
                require(actual == expected % (1 << 64),
                        f"{name}: expected {expected}, got {actual}")
        COUNT += 1
        print("PASS templates", name, flush=True)


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
    return ("module app;" + imports + definitions + helpers +
            "auto test()->" + result + "{" + body + "}")


SCALARS = ("i64", "u64", "bool")
VALUES = {"i64": "-9223372036854775808", "u64": "18446744073709551615u64",
          "bool": "true"}
OTHERS = {"i64": "9223372036854775807", "u64": "9223372036854775808u64",
          "bool": "false"}

# Every ordered tuple uses the same source definition and crosses constructors,
# complete result copies, immutable by-value parameters and independent locals.
for first, second in product(SCALARS, repeat=2):
    concrete = f"Pair<{first},{second}>"
    a, b = VALUES[first], OTHERS[second]
    changed_a, changed_b = OTHERS[first], VALUES[second]
    helpers = (f"auto make()->{concrete}{{const {concrete} p={concrete}({a},{b});return p;}}"
               f"auto copy({concrete} p)->{concrete}{{return p;}}"
               f"auto consume({concrete} p)->i64{{"
               f"if(p.first=={a}){{if(p.second=={b}){{return 42;}}}}return 0;}}")
    body = (f"{concrete} original=make();{concrete} copied=copy(original);"
            f"{concrete} local=copied;local.first={changed_a};local.second={changed_b};"
            f"if(original.first!={a}){{return 1;}}if(original.second!={b}){{return 2;}}"
            f"if(local.first!={changed_a}){{return 3;}}if(local.second!={changed_b}){{return 4;}}"
            "return consume(copied);")
    check(f"ordered tuple {first} {second} native copies and value ABI",
          program(body, helpers=helpers))

for scalar in SCALARS:
    concrete = f"Box<{scalar}>"
    value, replacement = VALUES[scalar], OTHERS[scalar]
    check(f"private {scalar} field placeholder locals arguments and results", program(
        f"const {concrete} original={concrete}({value});{concrete} copy=original;"
        f"copy.set({replacement});if(original.get()!={value}){{return 1;}}"
        f"if(copy.get()!={replacement}){{return 2;}}"
        f"if(copy.echo({value})!={value}){{return 3;}}"
        f"if(copy.facts()!=type_id({scalar})+size_of({scalar})){{return 4;}}"
        f"static_assert(field_count({concrete})==0);"
        f"return reflect_field_count(type_id({concrete}))+42;", BOX))
    check(f"private {scalar} raw result preserves all bits", program(
        f"const {concrete} b={concrete}({value});return b.get();", BOX,
        result=scalar), expected={"i64": -(1 << 63), "u64": (1 << 64)-1, "bool": 1}[scalar])

for first, second in product(SCALARS, repeat=2):
    concrete = f"std::pair<{first},{second}>"
    a, b = VALUES[first], OTHERS[second]
    check(f"std.utility pair {first} {second}", program(
        f"{concrete} p={concrete}({a},{b});const {concrete} q=copy(p);"
        f"if(q.first!={a}){{return 1;}}if(q.second!={b}){{return 2;}}"
        f"static_assert(size_of({concrete})==16);"
        f"static_assert(field_count({concrete})==2);return 42;", "",
        f"auto copy({concrete} p)->{concrete}{{return p;}}", "import std.utility;"),
        library=True)

concrete_types = [f"Pair<{a},{b}>" for a, b in product(SCALARS, repeat=2)]
identity_checks = "".join(f"static_assert(type_id({a})!=type_id({b}));"
                          for a, b in combinations(concrete_types, 2))
identity_checks += "".join(
    f"static_assert(size_of({name})==16);static_assert(field_count({name})==2);"
    f"if(reflect_size(type_id({name}))!=16){{return 1;}}"
    f"if(reflect_field_count(type_id({name}))!=2){{return 2;}}"
    for name in concrete_types)
check("ordered argument tuple nominal identity and runtime metadata", program(identity_checks+"return 42;"))
check("repeated specialization shares one nominal type", program(
    "Pair<i64,u64> p=Pair<i64,u64>(20,22u64);const Pair< i64 , u64 > q=p;"
    "static_assert(type_id(Pair<i64,u64>)==type_id(Pair< i64 , u64 >));"
    "return q.first+i64(q.second);"))
matrix_helpers = ""
matrix_body = ""
for index, (first, second) in enumerate(product(SCALARS, repeat=2)):
    concrete = f"Pair<{first},{second}>"
    a, b = VALUES[first], OTHERS[second]
    matrix_helpers += (f"auto make{index}()->{concrete}{{"
                       f"const {concrete} p={concrete}({a},{b});return p;}}"
                       f"auto copy{index}({concrete} p)->{concrete}{{return p;}}")
    matrix_body += (f"const {concrete} a{index}=make{index}();"
                    f"const {concrete} b{index}=copy{index}(a{index});"
                    f"if(b{index}.first!={a}){{return 1;}}"
                    f"if(b{index}.second!={b}){{return 2;}}")
check("all nine specializations coexist through constructor and value ABI",
      program(matrix_body+"return 42;", helpers=matrix_helpers))
check("three getter and local substitutions coexist without AST aliasing", program(
    "Box<i64> signed_value=Box<i64>(-9223372036854775808);"
    "Box<u64> unsigned_value=Box<u64>(18446744073709551615u64);"
    "Box<bool> flag=Box<bool>(true);"
    "if(signed_value.get()!=-9223372036854775808){return 1;}"
    "if(unsigned_value.get()!=18446744073709551615u64){return 2;}"
    "if(flag.get()!=true){return 3;}"
    "if(signed_value.echo(42)!=42){return 4;}"
    "if(unsigned_value.echo(9223372036854775808u64)!=9223372036854775808u64){return 5;}"
    "if(flag.echo(false)!=false){return 6;}"
    "flag.set(false);unsigned_value.set(42u64);signed_value.set(-42);"
    "if(flag.get()!=false){return 7;}if(unsigned_value.get()!=42u64){return 8;}"
    "if(signed_value.get()!=-42){return 9;}return 42;", BOX))
check("generic constructor parameter shadows same-named field", program(
    "Box<i64> b=Box<i64>(42);return b.get();",
    BOX.replace("Box(T initial): value(initial)", "Box(T value): value(value)")))
check("generic aggregate designated initialization", program(
    "Pair<i64,u64> p=Pair<i64,u64>{.first=20,.second=22u64};"
    "return p.first+i64(p.second);", PAIR[:PAIR.index("    Pair(")]+"};"))
check("generic empty class has bounded layout", program(
    "Empty<bool> e=Empty<bool>();Empty<bool> copy=identity(e);"
    "static_assert(size_of(Empty<bool>)==8);"
    "return reflect_size(type_id(Empty<bool>))+34;",
    "template<Scalar T>class Empty{public:Empty(){}};",
    "auto identity(Empty<bool> e)->Empty<bool>{return e;}"))
check("generic argument snapshot precedes later receiver mutation", program(
    "Box<i64> b=Box<i64>(20);return sum(b,b.set(22));", BOX,
    "auto sum(Box<i64> b,i64 later)->i64{return b.get()+later;}"))
check("generic six mixed ordinary parameters preserve complete values", program(
    "Pair<i64,u64> a=Pair<i64,u64>(10,11u64);"
    "Pair<bool,i64> b=Pair<bool,i64>(true,20);return sum(a,1,b,2u64,a,-2);",
    helpers="auto sum(Pair<i64,u64> a,i64 x,Pair<bool,i64> b,u64 y,"
            "Pair<i64,u64> c,i64 z)->i64{if(b.first){"
            "return a.first+x+b.second+i64(y)+c.first+z+1;}return 0;}"))
check("generic result lifetime repeats through loop", program(
    "i64 i=0;i64 total=0;while(i<2){const Box<i64> b=make(21);"
    "total=total+b.get();i=i+1;}return total;", BOX,
    "auto make(i64 n)->Box<i64>{const Box<i64> b=Box<i64>(n);return b;}"))
wide_fields = "".join(f"T f{i};" for i in range(64))
wide_values = ",".join(f".f{i}={18446744073709551615-i}u64" for i in range(64))
check("maximum-width generic value survives six parameter snapshots and result", program(
    "const Wide<u64> original=Wide<u64>{"+wide_values+"};"
    "Wide<u64> copied=select(original,original,original,original,original,original);"
    "copied.f0=0u64;if(original.f0!=18446744073709551615u64){return 0u64;}"
    "return copied.f63;", "template<Scalar T>class Wide{public:"+wide_fields+"};",
    "auto select(Wide<u64> a,Wide<u64> b,Wide<u64> c,Wide<u64> d,"
    "Wide<u64> e,Wide<u64> f)->Wide<u64>{return f;}", result="u64"),
    expected=(1 << 64)-64)

# Instantiated methods retain the definition's scope, including private helpers.
MODULE_BOX = "export module boxes;export "+BOX
check("imported generic getter", program(
    "Box<i64> b=Box<i64>(42);return b.get();", "", imports="import boxes;"),
    {"boxes": MODULE_BOX})
check("namespace generic constructor and qualified signature", program(
    "items::Box<i64> b=make();return b.get();", "",
    "auto make()->items::Box<i64>{items::Box<i64> b=items::Box<i64>(42);return b;}",
    "import boxes;"), {"boxes": "export module boxes;export namespace items{"+BOX+"}"})
lexical_box = BOX.replace("return local; }", "return adjust(local); }", 1)
check("defining module private helper beats root shadow", program(
    "Box<i64> b=Box<i64>(40);return b.get();", "",
    "auto adjust(i64 n)->i64{return 999;}", "import boxes;"),
    {"boxes": "export module boxes;auto adjust(i64 n)->i64{return n+2;}export "+lexical_box})
check("generic helper cannot resolve into caller", program(
    "Box<i64> b=Box<i64>(40);return b.get();", "",
    "auto adjust(i64 n)->i64{return 42;}", "import boxes;"),
    {"boxes": "export module boxes;export "+lexical_box}, error="unknown function")
check("private template unavailable to importing caller", program(
    "Box<i64> b=Box<i64>(42);return b.get();", "", imports="import boxes;"),
    {"boxes": "export module boxes;"+BOX}, error=("private", "unknown", "visible"))
check("private generic usable inside defining module", program(
    "return answer();", "", imports="import boxes;"),
    {"boxes": "export module boxes;"+BOX+
     "export auto answer()->i64{Box<i64> b=Box<i64>(42);return b.get();}"})
for signature in (
    "export auto make()->Box<i64>{Box<i64> b=Box<i64>(42);return b;}",
    "export auto consume(Box<i64> b)->i64{return b.get();}",
):
    check("export cannot expose private specialization "+("result" if "make" in signature else "parameter"),
          program("return 42;", "", imports="import boxes;"),
          {"boxes": "export module boxes;"+BOX+signature}, error="exposes private type")

TRANSITIVE = {
    "boxes": MODULE_BOX,
    "factory": "export module factory;import boxes;"
               "export auto make()->Box<i64>{Box<i64> b=Box<i64>(42);return b;}",
}
check("transitive specialization does not become directly visible", program(
    "return make();", "", imports="import factory;"), TRANSITIVE,
    error="direct visible import")
check("direct template import permits concrete factory result", program(
    "Box<i64> b=make();return b.get();", "", imports="import factory;import boxes;"), TRANSITIVE)
check("same imported specialization unifies across modules", program(
    "Box<i64> b=make();return consume(b);", "", imports="import factory;import boxes;import consumer;"),
    dict(TRANSITIVE, consumer="export module consumer;import boxes;"
         "export auto consume(Box<i64> b)->i64{return b.get();}"))
check("private generic metadata hidden in caller view", program(
    "return reflect_size(hidden_id())+reflect_field_count(hidden_id())+42;", "", imports="import boxes;"),
    {"boxes": "export module boxes;"+BOX+
     "export auto hidden_id()->i64{return type_id(Box<i64>);}"})

for definitions, imports, modules, error, label in [
    (PAIR+PAIR, "", None, "duplicate", "duplicate template definition"),
    (PAIR+"class Pair{public:i64 n;};", "", None, ("duplicate", "conflict"), "template ordinary class collision"),
    (PAIR+"auto Pair()->i64{return 42;}", "", None, ("duplicate", "conflict", "reserved"), "template function collision"),
    ("", "import left;import right;", {"left":"export module left;export "+PAIR,
       "right":"export module right;export "+PAIR}, ("ambiguous", "ambiguity"), "imported template ambiguity"),
]:
    check(label, program("Pair<i64,u64> p=Pair<i64,u64>(20,22u64);return 42;",
                         definitions, imports=imports), modules, error=error)
check("qualified different template definitions retain identity", program(
    "left::Pair<i64,u64> a=left::Pair<i64,u64>(20,22u64);"
    "right::Pair<i64,u64> b=right::Pair<i64,u64>(20,22u64);"
    "static_assert(type_id(left::Pair<i64,u64>)!=type_id(right::Pair<i64,u64>));"
    "return a.first+i64(b.second);", "", imports="import left;import right;"),
    {"left":"export module left;export namespace left{"+PAIR+"}",
     "right":"export module right;export namespace right{"+PAIR+"}"})

for label, body, helpers, error in [
    ("copy cross specialization", "Pair<i64,u64> a=Pair<i64,u64>(1,2u64);Pair<u64,i64> b=a;return 42;", "", "expected"),
    ("argument cross specialization", "Pair<i64,u64> a=Pair<i64,u64>(1,2u64);return consume(a);", "auto consume(Pair<u64,i64> p)->i64{return 42;}", "expected"),
    ("result cross specialization", "Pair<u64,i64> a=make();return 42;", "auto make()->Pair<u64,i64>{Pair<i64,u64> p=Pair<i64,u64>(1,2u64);return p;}", "expected"),
    ("constructor cross specialization", "Pair<i64,u64> a=Pair<u64,i64>(1u64,2);return 42;", "", ("expected", "constructor")),
    ("constructor substituted scalar argument", "Pair<i64,u64> a=Pair<i64,u64>(1,2);return 42;", "", "expected"),
    ("constructor omitted argument", "Pair<i64,u64> a=Pair<i64,u64>(1);return 42;", "", "argument count"),
    ("constructor designated initialization bypass", "Pair<i64,u64> a=Pair<i64,u64>{.first=1,.second=2u64};return 42;", "", "designated"),
    ("constructor deduction unsupported", "Pair<i64,u64> a=Pair(1,2u64);return 42;", "", ("template", "constructor", "argument")),
    ("temporary generic argument", "return consume(Pair<i64,u64>(1,2u64));", "auto consume(Pair<i64,u64> p)->i64{return 42;}", "complete local name"),
    ("direct generic result nominal mismatch", "Pair<u64,i64> a=make();return 42;", "auto make()->Pair<u64,i64>{return Pair<i64,u64>(1,2u64);}", "expected"),
    ("immutable generic parameter", "Pair<i64,u64> a=Pair<i64,u64>(1,2u64);return change(a);", "auto change(Pair<i64,u64> p)->i64{p.first=42;return 42;}", "mutable class local"),
    ("const generic field write", "const Pair<i64,u64> a=Pair<i64,u64>(1,2u64);a.first=42;return 42;", "", "mutable class local"),
]:
    check(label, program(body, helpers=helpers), error=error)

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
    ("missing field initialization after substitution", PAIR.replace(
        ", second(second_value)", ""), "Pair<i64,u64> p=Pair<i64,u64>(1,2u64);return 42;", "every field"),
    ("duplicate initializer after substitution", PAIR.replace(
        "first(first_value)", "first(first_value),first(first_value)"),
        "Pair<i64,u64> p=Pair<i64,u64>(1,2u64);return 42;", "duplicate constructor"),
    ("wrong initializer type after substitution", PAIR.replace("second(second_value)", "second(first_value)"),
        "Pair<i64,u64> p=Pair<i64,u64>(1,2u64);return 42;", "expected"),
    ("const method mutation after substitution", BOX.replace("const T local=value;", "value=value;const T local=value;"),
        "Box<i64> b=Box<i64>(42);return b.get();", "const method"),
    ("wrong method result after substitution", BOX.replace("const T local=value; return local;", "return true;"),
        "Box<i64> b=Box<i64>(42);return b.get();", "expected"),
    ("wrong generic local after substitution", BOX.replace("const T local=value;", "const T local=true;"),
        "Box<u64> b=Box<u64>(42u64);return 42;", "expected"),
    ("generic method cycle after substitution", BOX.replace("const T local=value; return local;", "return get();"),
        "Box<i64> b=Box<i64>(42);return b.get();", "cycle"),
    ("generic body owner move while borrowed", BOX.replace("const T local=value; return local;",
        "own<i64> n=own(42);const ref<i64> r=borrow(n);own<i64> moved=move(n);return read(r);"),
        "Box<i64> b=Box<i64>(42);return b.get();", "borrow"),
    ("private generic constructor", BOX.replace("public:\n    Box", "private:\n    Box").replace(
        "    auto get", "public: auto get", 1), "Box<i64> b=Box<i64>(42);return b.get();", "private constructor"),
]:
    check(label, program(body, definition), error=error)

for scalar, value in (("i64", "9223372036854775807"), ("u64", "18446744073709551615u64")):
    increment = "1" if scalar == "i64" else "1u64"
    definition = BOX.replace("value=replacement;", f"value=replacement+{increment};")
    check(f"generic {scalar} method retains checked overflow", program(
        f"Box<{scalar}> b=Box<{scalar}>({value});return b.set({value});",
        definition, result=scalar), trap=True)
check("bool generic arithmetic rejected", program(
    "Box<bool> b=Box<bool>(true);if(b.set(false)){return 42;}return 0;",
    BOX.replace("value=replacement;", "value=replacement+replacement;")), error="expected")

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
    check("unsupported template "+label, program(
        f"return size_of({concrete});", PAIR+BOX+"class Other{public:i64 value;};"),
        error=("scalar", "template", "argument", "expected"))

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
    check("unsupported template declaration "+label, program("return 42;", definition),
          error=("template", "parameter", "scalar", "expected", "duplicate", "reserved"))

for label, inside in [
    ("nested field", "Box<i64> value;"),
    ("recursive field", "Bad<i64> value;"),
    ("method local", "public:auto get()->i64{Box<i64> b=Box<i64>(42);return b.get();}"),
    ("reflection query", "public:auto get()->i64{return size_of(Box<i64>);}"),
]:
    check("template-local instantiation rejected "+label, program(
        "return size_of(Bad<i64>);", BOX+"template<Scalar T>class Bad{"+inside+"};"),
        error=("template", "nested", "recursive", "scalar", "expected"))

def template_definitions(start, count, exported=False):
    return "".join(("export " if exported else "")+PAIR.replace("Pair", f"Generic{i}")
                   for i in range(start, start+count))


for count in (64, 65):
    check(f"template declaration boundary {count}", program(
        "Generic0<i64,u64> p=Generic0<i64,u64>(20,22u64);return p.first+i64(p.second);",
        template_definitions(0, count)), error=None if count==64 else ("64", "template limit"))
    split = count // 2
    check(f"template graph declaration boundary {count}", program(
        "return size_of(Generic0<i64,u64>)+26;", "", imports="import left;import right;"),
        {"left":"export module left;"+template_definitions(0, split, True),
         "right":"export module right;"+template_definitions(split, count-split, True)},
        error=None if count==64 else ("64", "template limit"))

# Twenty-nine templates provide 261 distinct tuples; instantiate exactly the
# boundary count through reflection so every concrete class is actually created.
for count in (256, 257):
    types = [f"Generic{i}<{a},{b}>" for i in range(29)
             for a, b in product(SCALARS, repeat=2)][:count]
    body = "".join(f"static_assert(size_of({name})==16);" for name in types)+"return 42;"
    check(f"concrete class boundary {count}", program(body, template_definitions(0, 29)),
          error=None if count==256 else ("256", "class limit", "classes"))
    check(f"concrete graph class boundary {count}", program(body, "", imports="import left;import right;"),
          {"left":"export module left;"+template_definitions(0, 14, True),
           "right":"export module right;"+template_definitions(14, 15, True)},
          error=None if count==256 else ("256", "class limit", "classes"))

check("repeated concrete use does not consume instantiation budget", program(
    "".join("static_assert(size_of(Pair<i64,u64>)==16);" for _ in range(300))+"return 42;"))
check("template rejection preserves existing artifact", program(
    "Pair<i64,u64> p=Pair<i64,u64>(1,2);return 42;"), error="expected",
    existing_output="previous known-good output\n")

check("injected self type constructor and reflection", """module app;
template <Scalar T> class Holder { T value; public: Holder(T n):value(n){}
 auto compute(T n) const -> T { static_assert(size_of(Holder)==8);
   const Holder local=Holder(n); return local.value; }
};
auto test()->i64 { const Holder<i64> x=Holder<i64>(0); return x.compute(42); }
""")
check("injected self type designated construction", """module app;
template <Scalar T> class Holder { public: T value;
 auto compute(T n) const -> T { const Holder local=Holder{.value=n}; return local.value; }
};
auto test()->u64 { const Holder<u64> x=Holder<u64>{.value=0u64}; return x.compute(18446744073709551615u64); }
""", expected=(1<<64)-1)

check("direct generic constructor result", program(
    "Pair<i64,u64> a=make();return a.first+i64(a.second);",
    helpers="auto make()->Pair<i64,u64>{return Pair<i64,u64>(20,22u64);}"))

print(f"{COUNT} scalar template checks passed")
