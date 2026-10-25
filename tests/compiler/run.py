#!/usr/bin/env python3
"""Frontend acceptance, diagnostics, checked traps and native results (native_runner.py)."""

from pathlib import Path
import random
import sys

from native_runner import Suite, Trap

COMPILER = Path(sys.argv[1] if len(sys.argv) > 1 else "build/aurorac").resolve()
SUITE = Suite(COMPILER, "frontend")
TRAPS = {"overflow": Trap.OVERFLOW, "bounds": Trap.BOUNDS}


def check(name, body, expected=42, error=None, trap=None, options=(), modules=None, standalone=False):
    source = body if body.startswith("module ") else "module test; auto test() -> i64 { " + body + " }"
    SUITE.check(
        name, source, TRAPS[trap] if trap else expected, error, options=options, modules=modules, standalone=standalone
    )


check("leading zero decimal", "return 010 + 032;")
check("leading zero eight", "return 08;", 8)
check("leading zero reflection agreement", "static_assert(010 == 10); return 010;", 10)
check("precedence", "return 2 + 4 * 10;")
check("signed arithmetic", "return -8 * 3 + 2;", -22)
check("checked addition overflow", "return 9223372036854775807 + 1;", trap="overflow")
check("mutable scalar", "i64 x = 1; x = x + 41; return x;")
check("scalar shadowing", "const i64 x = 42; { const bool x = false; } return x;")
check("branch then", "if (3 < 4) { return 42; } else { return 9; }")
check("branch else", "if (3 >= 4) { return 9; } else { return 42; }")
check("bool comparison", "if (true == !false) { return 42; } return 0;")
check("forward call", "module test; auto test() -> i64 { return answer(); } auto answer() -> i64 { return 42; }")
check("owned initializer compact spacing", "own<i64> a =own(42); return read(a);")
check("owned move", "own<i64> a = own(42); own<i64> b = move(a); return read(b);")
check(
    "shared borrows",
    "own<i64> a = own(21); const ref<i64> b = borrow(a); const ref<i64> c = borrow(a); return read(b) + read(c);",
)
check(
    "exclusive borrow",
    "own<i64> a = own(2); { mutref<i64> b = borrow_mut(a); write(b, read(b) * 21); } return read(a);",
)
check("borrow release", "own<i64> a = own(42); { const ref<i64> b = borrow(a); } own<i64> c = move(a); return read(c);")
check(
    "branch borrow release",
    "own<i64> a = own(42); if (true) { const ref<i64> b = borrow(a); } own<i64> c = move(a); return read(c);",
)
check(
    "return path excludes move",
    "own<i64> a = own(42); if (false) { own<i64> b = move(a); return read(b); } return read(a);",
)
check(
    "return else excludes move",
    "own<i64> a = own(42); if (true) { } else { own<i64> b = move(a); return read(b); } return read(a);",
)
check(
    "reflection constant",
    "static_assert(size_of(i64) == 8); static_assert(type_id(bool) != type_id(i64)); return size_of(i64) + 34;",
)
check("reflection bool", "return reflect_size(type_id(bool));", 1)
# Class type IDs are numbered from 100 per graph: a fixed "unknown" ID needs its own graph.
check("reflection unknown", "return reflect_size(999);", 0, standalone=True)
check("reflection negative", "return reflect_size(-1);", 0)
check(
    "closed reflection preserves nonzero public fields and unknown IDs",
    "module test;class Box{u64 hidden;public:u8 shown;Box():hidden(0u64),shown(0u8){}};"
    "auto test()->i64{if(reflect_field_count(type_id(Box))!=1){return 1;}"
    "if(reflect_size(type_id(Box))!=16){return 2;}"
    "if(reflect_field_count(-1)!=0){return 3;}if(reflect_size(999999)!=0){return 4;}return 42;}",
    options=("--referenced-reflection-only",),
    standalone=True,
)
check(
    "closed scoped reflection preserves defining-module private visibility",
    "module test;import hidden;auto test()->i64{const i64 id=hidden_id();"
    "if(reflect_size(id)!=0){return 1;}if(hidden_size(id)!=8){return 2;}"
    "if(hidden_size(-1)!=0){return 3;}if(hidden_size(999999)!=0){return 4;}return 42;}",
    options=("--referenced-reflection-only",),
    modules={
        "hidden": "export module hidden;class Secret{public:i64 value;};"
        "export auto hidden_id()->i64{return type_id(Secret);}"
        "export auto hidden_size(i64 id)->i64{return reflect_size(id);}"
    },
)
check(
    "closed emission still rejects malformed unused imports",
    "module test;import malformed;auto test()->i64{return 42;}",
    error="unknown local",
    options=("--referenced-reflection-only",),
    modules={"malformed": "export module malformed;auto unused()->i64{return absent;}"},
)


negative = [
    ("use after move", "own<i64> a = own(42); own<i64> b = move(a); return read(a);", "use after move"),
    ("double move", "own<i64> a = own(42); own<i64> b = move(a); own<i64> c = move(a); return 0;", "use after move"),
    ("copy owner", "own<i64> a = own(42); const i64 b = a; return b;", "cannot be implicitly copied"),
    ("implicit owned initialization", "own<i64> a = own(42); own<i64> b = a; return 0;", "explicit constructor"),
    (
        "move shared borrowed",
        "own<i64> a = own(42); const ref<i64> b = borrow(a); own<i64> c = move(a); return 0;",
        "cannot move a borrowed",
    ),
    (
        "move mutably borrowed",
        "own<i64> a = own(42); mutref<i64> b = borrow_mut(a); own<i64> c = move(a); return 0;",
        "cannot move a borrowed",
    ),
    (
        "shared then mutable",
        "own<i64> a = own(42); const ref<i64> b = borrow(a); mutref<i64> c = borrow_mut(a); return 0;",
        "conflicting borrow",
    ),
    (
        "mutable then shared",
        "own<i64> a = own(42); mutref<i64> b = borrow_mut(a); const ref<i64> c = borrow(a); return 0;",
        "conflicting borrow",
    ),
    (
        "two mutable borrows",
        "own<i64> a = own(42); mutref<i64> b = borrow_mut(a); mutref<i64> c = borrow_mut(a); return 0;",
        "conflicting borrow",
    ),
    (
        "owner read during exclusive borrow",
        "own<i64> a = own(42); mutref<i64> b = borrow_mut(a); return read(a);",
        "exclusively borrowed",
    ),
    (
        "write shared ref",
        "own<i64> a = own(42); const ref<i64> b = borrow(a); write(b, 0); return 0;",
        "expected mutref",
    ),
    (
        "borrow expired scope",
        "own<i64> a = own(42); { const ref<i64> b = borrow(a); } return read(b);",
        "unknown local",
    ),
    (
        "moved on then path",
        "own<i64> a = own(42); if (true) { own<i64> b = move(a); } return read(a);",
        "use after move",
    ),
    (
        "moved on else path",
        "own<i64> a = own(42); if (false) { } else { own<i64> b = move(a); } return read(a);",
        "use after move",
    ),
    (
        "nested branch move",
        "own<i64> a = own(42); if (true) { if (true) { own<i64> b = move(a); } } return read(a);",
        "use after move",
    ),
    ("immutable assignment", "const i64 a = 1; a = 42; return a;", "mutable scalar"),
    ("type mismatch", "const bool a = 42; return 42;", "expected bool"),
    ("nonboolean condition", "if (42) { return 1; } return 0;", "expected bool"),
    ("missing return", "const i64 a = 42;", "every path"),
    ("missing branch return", "if (true) { return 42; }", "every path"),
    ("uninitialized local", "const i64 a ; return a;", "expected '='"),
    ("out of scope", "{ const i64 a = 42; } return a;", "unknown local"),
    ("duplicate local", "const i64 a = 1; const i64 a = 2; return a;", "duplicate local"),
    ("failed assertion", "static_assert(size_of(i64) == 4); return 42;", "static assertion failed"),
    ("nonconstant assertion", "const i64 a = 8; static_assert(a == 8); return 42;", "static_assert supports"),
    ("overflow literal", "return 9223372036854775808;", "out of range"),
    ("unknown function", "return missing();", "unknown function"),
    ("borrow scalar", "const i64 a = 42; const ref<i64> b = borrow(a); return 42;", "expected own"),
    (
        "reference escape",
        "module test; auto test() -> ref<i64> { own<i64> a = own(42); return borrow(a); }",
        "only scalar function results",
    ),
    ("unsupported pointer", "const ptr<i64> x = 0; return 42;", "unsupported type"),
    (
        "class declaration needs semicolon",
        "module test; class A { public: auto f() -> i64 { return 1; } }",
        "expected ';'",
    ),
    ("unreachable code", "return 42; return 0;", "unreachable statement"),
    (
        "duplicate function",
        "module test; auto test() -> i64 { return 42; } auto test() -> i64 { return 0; }",
        "duplicate or reserved",
    ),
    ("builtin collision", "module test; auto reflect_size() -> i64 { return 42; }", "duplicate or reserved"),
    (
        "argument type",
        "module test; auto f(bool x) -> i64 { return 42; } auto test() -> i64 { return f(1); }",
        "expected bool",
    ),
    (
        "argument count",
        "module test; auto f(i64 x) -> i64 { return x; } auto test() -> i64 { return f(); }",
        "wrong argument count",
    ),
]
for name, body, diagnostic in negative:
    check(name, body, error=diagnostic)
# Class values: all storage belongs to the current stack frame; scalar fields copy.
class_prefix = "module test; class Point { public: i64 x; i64 y; }; "


def class_check(name, body, expected=42, error=None):
    check(name, class_prefix + "auto test() -> i64 { " + body + " }", expected, error)


class_check("parenthesized class field", "const Point p = Point { .x = 20, .y = 22 }; return (p).x + (p).y;")
class_check("class construct and fields", "const Point p = Point { .x = 20, .y = 22 }; return p.x + p.y;")
class_check("class reordered fields", "const Point p = Point { .y = 22, .x = 20 }; return p.x + p.y;")
class_check(
    "class independent copy", "Point p = Point { .x = 20, .y = 22 }; const Point q = p; p.x = 100; return q.x + q.y;"
)
class_check("class mutable field", "Point p = Point { .x = 1, .y = 2 }; p.x = 40; return p.x + p.y;")
class_check("class shadow copy", "const Point p = Point { .x = 20, .y = 22 }; { const Point p = p; return p.x + p.y; }")
class_check(
    "class branch field update", "Point p = Point { .x = 20, .y = 2 }; if (true) { p.y = 22; } return p.x + p.y;"
)
class_check(
    "class reflection static", "static_assert(size_of(Point) == 16); static_assert(field_count(Point) == 2); return 42;"
)
class_check(
    "class reflection runtime", "const i64 id = type_id(Point); return reflect_size(id) + reflect_field_count(id) + 24;"
)
class_check("missing class field", "const Point p = Point { .x = 42 }; return 0;", error="every class field")
class_check(
    "duplicate class initializer",
    "const Point p = Point { .x = 42, .x = 0 }; return 0;",
    error="duplicate field initializer",
)
class_check("unknown class initializer", "const Point p = Point { .x = 42, .z = 0 }; return 0;", error="unknown field")
class_check(
    "class field type mismatch", "const Point p = Point { .x = false, .y = 0 }; return 0;", error="expected i64"
)
class_check(
    "class unknown field read", "const Point p = Point { .x = 20, .y = 22 }; return p.z;", error="unknown field"
)
class_check(
    "class immutable mutation",
    "const Point p = Point { .x = 20, .y = 22 }; p.x = 0; return 0;",
    error="mutable class local",
)
class_check(
    "class mutation type mismatch", "Point p = Point { .x = 20, .y = 22 }; p.x = false; return 0;", error="expected i64"
)
class_check(
    "class local uninitialized read", "const Point p = Point { .x = p.x, .y = 22 }; return 0;", error="unknown local"
)
class_check("class wrong constructor", "const Point p = Other { .x = 20, .y = 22 }; return 0;", error="expected Point")
class_check("class unknown type", "const Other p = Other {}; return 0;", error="unknown class type")
class_check(
    "class unavailable outside scope",
    "{ const Point p = Point { .x = 20, .y = 22 }; } return p.x;",
    error="unknown local",
)
class_check(
    "class wrong scalar context", "const Point p = Point { .x = 20, .y = 22 }; return p;", error="class values are only"
)
class_check(
    "class borrow not yet supported",
    "const Point p = Point { .x = 20, .y = 22 }; const ref<i64> r = borrow(p); return 0;",
    error="expected own<i64>",
)
class_check("class unknown reflection", "return size_of(Missing);", error="unknown class type")
check("scalar field count", "return reflect_field_count(type_id(i64));", 0)
check("unknown field count", "return reflect_field_count(77);", 0)

# Safe C++-style surface, const ownership, and visibility are language rules.
check("obsolete fn declaration rejected", "module test; fn test() -> i64 { return 42; }", error="expected 'auto'")
check(
    "obsolete let declaration rejected",
    "let value: i64 = 42; return value;",
    error="unsupported or reserved type spelling",
)
check("C function declaration rejected", "module test; i64 test() { return 42; }", error="expected 'auto'")
check("C int type rejected", "int value = 42; return value;", error="unsupported or reserved type spelling")
check("raw pointer rejected", "i64* value = 0; return 0;", error="expected identifier")
check("unsafe block rejected", "unsafe { return 42; }", error="expected '.'")
check("const owner shared read", "const own<i64> a = own(42); const ref<i64> r = borrow(a); return read(r);")
check(
    "const owner mutable borrow rejected",
    "const own<i64> a = own(42); mutref<i64> r = borrow_mut(a); return 0;",
    error="cannot mutably borrow a const owner",
)
check("const owner move preserved", "const own<i64> a = own(42); const own<i64> b = move(a); return read(b);")
check(
    "const owner move cannot thaw",
    "const own<i64> a = own(42); own<i64> b = move(a); return 0;",
    error="cannot move a const owner",
)
check(
    "const mutable reference cannot write",
    "own<i64> a = own(42); const mutref<i64> r = borrow_mut(a); write(r, 0); return 0;",
    error="non-const mutable reference",
)
check("owner never rebound", "own<i64> a = own(42); a = own(1); return 0;", error="mutable scalar")

# Checked integer operations fail-stop instead of silently wrapping.
check("signed maximum boundary", "return 9223372036854775807;", 9223372036854775807)
check("signed minimum literal", "return -9223372036854775808;", -9223372036854775808)
check("signed minimum literal negation", "return -(-9223372036854775808);", trap="overflow")
check("signed minimum literal leading zeros", "return -009223372036854775808;", -9223372036854775808)
check("signed literal below minimum", "return -9223372036854775809;", error="integer literal out of range")
check("signed minimum boundary", "return -9223372036854775807 - 1;", -9223372036854775808)
check("checked subtraction overflow", "return (-9223372036854775807 - 1) - 1;", trap="overflow")
check("checked multiplication overflow", "return 9223372036854775807 * 2;", trap="overflow")
check("checked negation overflow", "const i64 minimum = -9223372036854775807 - 1; return -minimum;", trap="overflow")
check("minimum times negative one", "return (-9223372036854775807 - 1) * -1;", trap="overflow")
check("minimum times one", "return (-9223372036854775807 - 1) * 1;", -9223372036854775808)

check("while zero iterations", "i64 value = 42; while (false) { value = 0; } return value;")
check(
    "while returning move",
    "own<i64> a = own(42); while (true) { own<i64> b = move(a); return read(b); } return read(a);",
)
check(
    "while zero path retains owner",
    "own<i64> a = own(42); while (false) { own<i64> b = move(a); return read(b); } return read(a);",
)
check(
    "while backedge move rejected",
    "own<i64> a = own(42); while (false) { own<i64> b = move(a); } return 0;",
    error="loop backedge cannot move",
)
check(
    "while branch backedge move rejected",
    "own<i64> a = own(42); while (true) { if (true) { own<i64> b = move(a); } } return 0;",
    error="loop backedge cannot move",
)
check("while condition type", "while (1) { return 42; } return 0;", error="expected bool")
check(
    "while cannot escape borrow",
    "own<i64> a = own(42); while (false) { const ref<i64> r = borrow(a); } return read(r);",
    error="unknown local",
)
check("while does not prove return", "while (true) { return 42; }", error="every path")
check(
    "while local move use rejected",
    "while (true) { own<i64> a = own(42); own<i64> b = move(a); return read(a); } return 0;",
    error="use after move",
)
check("while break deferred", "while (true) { break; } return 42;", error="unknown local")

check("array mutate", "array<i64, 2> values = {1, 2}; values[0] = 40; return values[0] + values[1];")
check(
    "array shadow copy",
    "const array<i64, 2> values = {20, 22}; { const array<i64, 2> values = values; return values[0] + values[1]; }",
)
check("array reflection fields", "return reflect_field_count(type_id(array<i64, 3>));", 0)
check("array parenthesized indexing", "const array<i64, 1> values = {42}; return (values)[0];")
check("array negative index traps", "const array<i64, 1> values = {42}; return values[-1];", trap="bounds")
check("array upper index traps", "const array<i64, 1> values = {42}; return values[1];", trap="bounds")
check(
    "array maximum index traps", "const array<i64, 1> values = {42}; return values[9223372036854775807];", trap="bounds"
)
check(
    "array minimum index traps",
    "const array<i64, 1> values = {42}; return values[-9223372036854775807 - 1];",
    trap="bounds",
)
check("array negative store traps", "array<i64, 1> values = {42}; values[-1] = 0; return 42;", trap="bounds")
check("array upper store traps", "array<i64, 1> values = {42}; values[1] = 0; return 42;", trap="bounds")
check(
    "array immutable assignment",
    "const array<i64, 1> values = {42}; values[0] = 0; return 0;",
    error="mutable array local",
)
check("array bool index rejected", "const array<i64, 1> values = {42}; return values[true];", error="expected i64")
check("array element type rejected", "const array<i64, 1> values = {true}; return 0;", error="expected i64")
check("array store type rejected", "array<bool, 1> values = {false}; values[0] = 1; return 0;", error="expected bool")
check("array short initializer", "const array<i64, 2> values = {42}; return 0;", error="initializer length")
check("array long initializer", "const array<i64, 1> values = {42, 0}; return 0;", error="initializer length")
check("array zero length rejected", "const array<i64, 0> values = {}; return 0;", error="between 1 and 4096")
check("array oversized rejected", "const array<i64, 4097> values = {}; return 0;", error="between 1 and 4096")
check(
    "array enormous length rejected",
    "const array<i64, 9999999999999999999999> values = {}; return 0;",
    error="decimal integer literal",
)
check(
    "array nested element rejected",
    "const array<array<i64, 1>, 1> values = {}; return 0;",
    error="array elements require",
)
check("array owned element rejected", "const array<own<i64>, 1> values = {}; return 0;", error="array elements require")
check(
    "array wrong copy length",
    "const array<i64, 1> a = {42}; const array<i64, 2> b = a; return 0;",
    error="expected array<i64, 2>",
)
check(
    "array wrong copy element",
    "const array<bool, 1> a = {true}; const array<i64, 1> b = a; return 0;",
    error="expected array<i64, 1>",
)
check(
    "array borrowing rejected",
    "array<i64, 1> a = {42}; const ref<i64> r = borrow(a); return 0;",
    error="expected own<i64>",
)
check(
    "array element borrowing rejected",
    "array<i64, 1> a = {42}; const ref<i64> r = borrow(a[0]); return 0;",
    error="requires a local name",
)
check("array returned rejected", "const array<i64, 1> a = {42}; return a;", error="array values are only")
check("array lifetime ends", "{ const array<i64, 1> a = {42}; } return a[0];", error="unknown local")
check("array initializer cannot see itself", "const array<i64, 1> a = {a[0]}; return 0;", error="unknown local")
check("scalar cannot index", "const i64 a = 42; return a[0];", error="indexing requires an array")
check("scalar cannot len", "const i64 a = 42; return len(a);", error="len requires an array")
# Both per-array and aggregate frame resource limits are checked before offset arithmetic.
large_init = ",".join("1" for _ in range(4096))
check("maximum supported array", "const array<i64, 4096> a = {" + large_init + "}; return a[4095] + 41;")
check(
    "stack layout cap",
    "const array<i64, 4096> a = {" + large_init + "}; const array<i64, 4096> b = a; const i64 c = 0; return c;",
    error="stack frame exceeds 65536",
)

# Accepted boundary cases accompany separate adversarial depth-rejection fixtures.
check("deep bounded parentheses", "return " + "(" * 100 + "42" + ")" * 100 + ";")
check("deep bounded blocks", "{" * 100 + "return 42;" + "}" * 100)
check("bounded skew expression", "return 42" + "+0" * 100 + ";")
check(
    "mixed bounded block and expression depths", "{" * 100 + "return " + "(" * 100 + "42" + ")" * 100 + ";" + "}" * 100
)

random.seed(42)
for i in range(12):
    a, b, c, d = (random.randrange(-1000, 1000) for _ in range(4))
    check(f"arithmetic differential {i}", f"return ({a} + {b}) * ({c} - {d});", (a + b) * (c - d))
SUITE.load(Path(__file__).with_suffix(".cases"))
SUITE.finish()
