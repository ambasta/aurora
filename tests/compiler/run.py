#!/usr/bin/env python3
"""Compile source, assemble/link directly, run native assembly, check diagnostics."""
from pathlib import Path
import random
import resource
import signal
import subprocess
import sys
import tempfile

COMPILER = Path(sys.argv[1] if len(sys.argv) > 1 else "build/aurorac").resolve()
PASS = 0

def require(condition, message):
    if not condition:
        raise AssertionError(message)

def command(args, good=True):
    result = subprocess.run([str(x) for x in args], capture_output=True, text=True, timeout=5, preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))
    if good and result.returncode:
        raise AssertionError(f"{args}: exit {result.returncode}\n{result.stdout}{result.stderr}")
    return result

def check(name, body, expected=42, error=None, trap=None):
    global PASS
    with tempfile.TemporaryDirectory(prefix="aurora-test-") as directory:
        root = Path(directory)
        source = root / "input.au"
        source.write_text(body if body.startswith("module ") else 'module test; auto test() -> i64 { ' + body + " }")
        assembly = root / "program.s"
        result = command([COMPILER, source, "-o", assembly], good=error is None)
        if error is not None:
            require(result.returncode != 0, f"{name}: accepted invalid program")
            require(error in result.stderr, f"{name}: expected {error!r}: {result.stderr}")
            require(not assembly.exists(), f"{name}: emitted output on rejection")
        else:
            # This bridge is assembly, not a C/C++ runtime. Nonzero exit means mismatch.
            bridge = root / "entry.s"
            bridge.write_text(f""".text
.globl _start
_start:
    call test
    movabsq ${expected}, %rcx
    cmpq %rcx, %rax
    setne %dil
    movzbq %dil, %rdi
    movq $60, %rax
    syscall
.section .note.GNU-stack,"",@progbits
""")
            command(["as", "--64", assembly, "-o", root / "program.o"])
            command(["as", "--64", bridge, "-o", root / "entry.o"])
            command(["ld", "-o", root / "program", root / "entry.o", root / "program.o"])
            run = command([root / "program"], good=trap is None)
            if trap is not None:
                require(run.returncode == -signal.SIGILL, f"{name}: expected SIGILL, got {run.returncode}")
                code = assembly.read_text()
                require(f".Laurora_{trap}_trap:" in code, f"{name}: missing defined trap target")
                jump = "jae" if trap == "bounds" else "jo"
                require(f"{jump} .Laurora_{trap}_trap" in code, f"{name}: missing {trap} guard")
                require("ud2" in command(["objdump", "-d", root / "program"]).stdout, f"{name}: no assembled UD2 trap")
    PASS += 1
    print(f"PASS {name}")

check("leading zero decimal", "return 010 + 032;")
check("leading zero eight", "return 08;", 8)
check("leading zero reflection agreement", "static_assert(010 == 10); return 010;", 10)
check("precedence", "return 2 + 4 * 10;")
check("signed arithmetic", "return -8 * 3 + 2;", -22)
check("checked addition overflow", "return 9223372036854775807 + 1;", trap="overflow")
check("mutable scalar", 'i64 x = 1; x = x + 41; return x;')
check("scalar shadowing", 'const i64 x = 42; { const bool x = false; } return x;')
check("branch then", "if (3 < 4) { return 42; } else { return 9; }")
check("branch else", "if (3 >= 4) { return 9; } else { return 42; }")
check("bool comparison", "if (true == !false) { return 42; } return 0;")
check("nested functions", 'module test; auto inc(i64 x) -> i64 { return x + 1; } auto test() -> i64 { return 2 * inc(20); }')
check("six argument ABI", 'module test; auto sum(i64 a,i64 b,i64 c,i64 d,i64 e,i64 f) -> i64 { return a+b+c+d+e+f; } auto id(i64 x) -> i64 { return x; } auto test() -> i64 { return 1 + sum(id(1),2,3,4,5,id(26)); }')
check("forward call", 'module test; auto test() -> i64 { return answer(); } auto answer() -> i64 { return 42; }')
check("bool function", 'module test; auto yes(i64 x) -> bool { return x == 42; } auto test() -> i64 { if (yes(42)) { return 42; } else { return 0; } }')
check("owned initializer compact spacing", 'own<i64> a =own(42); return read(a);')
check("owned move", 'own<i64> a = own(42); own<i64> b = move(a); return read(b);')
check("shared borrows", 'own<i64> a = own(21); const ref<i64> b = borrow(a); const ref<i64> c = borrow(a); return read(b) + read(c);')
check("exclusive borrow", 'own<i64> a = own(2); { mutref<i64> b = borrow_mut(a); write(b, read(b) * 21); } return read(a);')
check("borrow release", 'own<i64> a = own(42); { const ref<i64> b = borrow(a); } own<i64> c = move(a); return read(c);')
check("branch borrow release", 'own<i64> a = own(42); if (true) { const ref<i64> b = borrow(a); } own<i64> c = move(a); return read(c);')
check("return path excludes move", 'own<i64> a = own(42); if (false) { own<i64> b = move(a); return read(b); } return read(a);')
check("return else excludes move", 'own<i64> a = own(42); if (true) { } else { own<i64> b = move(a); return read(b); } return read(a);')
check("reflection constant", "static_assert(size_of(i64) == 8); static_assert(type_id(bool) != type_id(i64)); return size_of(i64) + 34;")
check("reflection dynamic", 'module test; auto inspect(i64 id) -> i64 { return reflect_size(id); } auto test() -> i64 { return inspect(type_id(i64)) + 34; }')
check("reflection bool", "return reflect_size(type_id(bool));", 1)
check("reflection unknown", "return reflect_size(999);", 0)
check("reflection negative", "return reflect_size(-1);", 0)

negative = [
    ("use after move", 'own<i64> a = own(42); own<i64> b = move(a); return read(a);', "use after move"),
    ("double move", 'own<i64> a = own(42); own<i64> b = move(a); own<i64> c = move(a); return 0;', "use after move"),
    ("copy owner", 'own<i64> a = own(42); const i64 b = a; return b;', "cannot be implicitly copied"),
    ("implicit owned initialization", 'own<i64> a = own(42); own<i64> b = a; return 0;', "explicit constructor"),
    ("move shared borrowed", 'own<i64> a = own(42); const ref<i64> b = borrow(a); own<i64> c = move(a); return 0;', "cannot move a borrowed"),
    ("move mutably borrowed", 'own<i64> a = own(42); mutref<i64> b = borrow_mut(a); own<i64> c = move(a); return 0;', "cannot move a borrowed"),
    ("shared then mutable", 'own<i64> a = own(42); const ref<i64> b = borrow(a); mutref<i64> c = borrow_mut(a); return 0;', "conflicting borrow"),
    ("mutable then shared", 'own<i64> a = own(42); mutref<i64> b = borrow_mut(a); const ref<i64> c = borrow(a); return 0;', "conflicting borrow"),
    ("two mutable borrows", 'own<i64> a = own(42); mutref<i64> b = borrow_mut(a); mutref<i64> c = borrow_mut(a); return 0;', "conflicting borrow"),
    ("owner read during exclusive borrow", 'own<i64> a = own(42); mutref<i64> b = borrow_mut(a); return read(a);', "exclusively borrowed"),
    ("write shared ref", 'own<i64> a = own(42); const ref<i64> b = borrow(a); write(b, 0); return 0;', "expected mutref"),
    ("borrow expired scope", 'own<i64> a = own(42); { const ref<i64> b = borrow(a); } return read(b);', "unknown local"),
    ("moved on then path", 'own<i64> a = own(42); if (true) { own<i64> b = move(a); } return read(a);', "use after move"),
    ("moved on else path", 'own<i64> a = own(42); if (false) { } else { own<i64> b = move(a); } return read(a);', "use after move"),
    ("nested branch move", 'own<i64> a = own(42); if (true) { if (true) { own<i64> b = move(a); } } return read(a);', "use after move"),
    ("immutable assignment", 'const i64 a = 1; a = 42; return a;', "mutable scalar"),
    ("type mismatch", 'const bool a = 42; return 42;', "expected bool"),
    ("nonboolean condition", "if (42) { return 1; } return 0;", "expected bool"),
    ("missing return", 'const i64 a = 42;', "every path"),
    ("missing branch return", "if (true) { return 42; }", "every path"),
    ("uninitialized local", 'const i64 a ; return a;', "expected '='"),
    ("out of scope", '{ const i64 a = 42; } return a;', "unknown local"),
    ("duplicate local", 'const i64 a = 1; const i64 a = 2; return a;', "duplicate local"),
    ("failed assertion", "static_assert(size_of(i64) == 4); return 42;", "static assertion failed"),
    ("nonconstant assertion", 'const i64 a = 8; static_assert(a == 8); return 42;', "static_assert supports"),
    ("overflow literal", "return 9223372036854775808;", "out of range"),
    ("unknown function", "return missing();", "unknown function"),
    ("borrow scalar", 'const i64 a = 42; const ref<i64> b = borrow(a); return 42;', "expected own"),
    ("reference escape", 'module test; auto test() -> ref<i64> { own<i64> a = own(42); return borrow(a); }', "only scalar function results"),
    ("unsupported pointer", 'const ptr<i64> x = 0; return 42;', "unsupported type"),
    ("class declaration needs semicolon", 'module test; class A { public: auto f() -> i64 { return 1; } }', "expected ';'"),
    ("unreachable code", "return 42; return 0;", "unreachable statement"),
    ("duplicate function", 'module test; auto test() -> i64 { return 42; } auto test() -> i64 { return 0; }', "duplicate or reserved"),
    ("builtin collision", 'module test; auto reflect_size() -> i64 { return 42; }', "duplicate or reserved"),
    ("argument type", 'module test; auto f(bool x) -> i64 { return 42; } auto test() -> i64 { return f(1); }', "expected bool"),
    ("argument count", 'module test; auto f(i64 x) -> i64 { return x; } auto test() -> i64 { return f(); }', "wrong argument count"),
]
for name, body, diagnostic in negative:
    check(name, body, error=diagnostic)
# Class values: all storage belongs to the current stack frame; scalar fields copy.
class_prefix = 'module test; class Point { public: i64 x; i64 y; }; '
def class_check(name, body, expected=42, error=None):
    check(name, class_prefix + 'auto test() -> i64 { ' + body + " }", expected, error)

class_check("parenthesized class field", 'const Point p = Point { .x = 20, .y = 22 }; return (p).x + (p).y;')
class_check("class construct and fields", 'const Point p = Point { .x = 20, .y = 22 }; return p.x + p.y;')
class_check("class reordered fields", 'const Point p = Point { .y = 22, .x = 20 }; return p.x + p.y;')
class_check("class independent copy", 'Point p = Point { .x = 20, .y = 22 }; const Point q = p; p.x = 100; return q.x + q.y;')
class_check("class mutable field", 'Point p = Point { .x = 1, .y = 2 }; p.x = 40; return p.x + p.y;')
class_check("class shadow copy", 'const Point p = Point { .x = 20, .y = 22 }; { const Point p = p; return p.x + p.y; }')
class_check("class branch field update", 'Point p = Point { .x = 20, .y = 2 }; if (true) { p.y = 22; } return p.x + p.y;')
class_check("class reflection static", "static_assert(size_of(Point) == 16); static_assert(field_count(Point) == 2); return 42;")
class_check("class reflection runtime", 'const i64 id = type_id(Point); return reflect_size(id) + reflect_field_count(id) + 24;')
check("class runtime dynamic id", class_prefix + 'auto inspect(i64 id) -> i64 { return reflect_size(id) + reflect_field_count(id); } auto test() -> i64 { return inspect(type_id(Point)); }', 18)
check("class bool field", 'module test; class Flag { public: bool enabled; i64 value; }; auto test() -> i64 { Flag f = Flag { .value = 42, .enabled = false }; f.enabled = true; if (f.enabled) { return f.value; } return 0; }')
check("empty class", 'module test; class Empty { public:}; auto test() -> i64 { const Empty e = Empty {}; const Empty f = e; static_assert(field_count(Empty) == 0); return size_of(Empty); }', 8)
check("classes declared after function", 'module test; auto test() -> i64 { const Pair p = Pair { .x = 42 }; return p.x; } class Pair { public: i64 x; };')
check("class call fields", class_prefix + 'auto id(i64 x) -> i64 { return x; } auto test() -> i64 { const Point p = Point { .y = id(22), .x = id(20) }; return p.x + p.y; }')
check("multiple class type IDs", 'module test; class A { public: i64 x; }; class B { public: i64 x; i64 y; }; auto test() -> i64 { static_assert(type_id(A) != type_id(B)); return reflect_size(type_id(A)) + reflect_size(type_id(B)); }', 24)
class_check("missing class field", 'const Point p = Point { .x = 42 }; return 0;', error="every class field")
class_check("duplicate class initializer", 'const Point p = Point { .x = 42, .x = 0 }; return 0;', error="duplicate field initializer")
class_check("unknown class initializer", 'const Point p = Point { .x = 42, .z = 0 }; return 0;', error="unknown field")
class_check("class field type mismatch", 'const Point p = Point { .x = false, .y = 0 }; return 0;', error="expected i64")
class_check("class unknown field read", 'const Point p = Point { .x = 20, .y = 22 }; return p.z;', error="unknown field")
class_check("class immutable mutation", 'const Point p = Point { .x = 20, .y = 22 }; p.x = 0; return 0;', error="mutable class local")
class_check("class mutation type mismatch", 'Point p = Point { .x = 20, .y = 22 }; p.x = false; return 0;', error="expected i64")
class_check("class local uninitialized read", 'const Point p = Point { .x = p.x, .y = 22 }; return 0;', error="unknown local")
class_check("class wrong constructor", 'const Point p = Other { .x = 20, .y = 22 }; return 0;', error="expected Point")
class_check("class unknown type", 'const Other p = Other {}; return 0;', error="unknown class type")
class_check("class unavailable outside scope", '{ const Point p = Point { .x = 20, .y = 22 }; } return p.x;', error="unknown local")
class_check("class wrong scalar context", 'const Point p = Point { .x = 20, .y = 22 }; return p;', error="class values are only")
class_check("class borrow not yet supported", 'const Point p = Point { .x = 20, .y = 22 }; const ref<i64> r = borrow(p); return 0;', error="expected own<i64>")
class_check("class unknown reflection", "return size_of(Missing);", error="unknown class type")
check("class duplicate declaration", 'module test; class A { public:}; class A { public:}; auto test() -> i64 { return 0; }', error="duplicate or reserved class")
check("class duplicate fields", 'module test; class A { public: i64 x; bool x; }; auto test() -> i64 { return 0; }', error="duplicate class field")
check("class owned field rejected", 'module test; class A { public: own<i64> x; }; auto test() -> i64 { return 0; }', error="class fields currently require")
check("class nested field rejected", 'module test; class A { public: Point x; }; auto test() -> i64 { return 0; }', error="class fields currently require")
check("class reserved name", 'module test; class i64 { public:}; auto test() -> i64 { return 0; }', error="duplicate or reserved class")
check("class function name collision", 'module test; class A { public:}; auto A() -> i64 { return 0; }', error="duplicate or reserved function")
check("class wrong copy type", 'module test; class A { public: i64 x; }; class B { public: i64 x; }; auto test() -> i64 { const A a = A { .x = 1 }; const B b = a; return 0; }', error="expected B")
check("class parameter value copy", 'module test; class A { public:i64 value;}; auto get(A a)->i64{return a.value;} auto test()->i64{A a=A{.value=42};return get(a);}')
check("class return requires named local", 'module test; class A { public:}; auto test() -> A { return A {}; }', error="complete local name")
check("scalar field count", "return reflect_field_count(type_id(i64));", 0)
check("unknown field count", "return reflect_field_count(77);", 0)

# Safe C++-style surface, const ownership, and visibility are language rules.
check("obsolete fn declaration rejected", "module test; fn test() -> i64 { return 42; }", error="expected 'auto'")
check("obsolete let declaration rejected", "let value: i64 = 42; return value;", error="unsupported or reserved type spelling")
check("C function declaration rejected", "module test; i64 test() { return 42; }", error="expected 'auto'")
check("C int type rejected", "int value = 42; return value;", error="unsupported or reserved type spelling")
check("raw pointer rejected", "i64* value = 0; return 0;", error="expected identifier")
check("unsafe block rejected", "unsafe { return 42; }", error="expected '.'")
check("private class construction rejected", "module test; class Secret { i64 value; }; auto test() -> i64 { const Secret s = Secret{.value = 42}; return 0; }", error="class construction requires public fields")
check("explicit private class construction rejected", "module test; class Secret { public: i64 x; private: i64 y; }; auto test() -> i64 { const Secret s = Secret{.x = 1, .y = 2}; return 0; }", error="class construction requires public fields")
check("private metadata hides field count", "module test; class Secret { i64 value; public: bool visible; }; auto test() -> i64 { static_assert(field_count(Secret) == 1); return reflect_field_count(type_id(Secret)); }", 1)
check("const owner shared read", "const own<i64> a = own(42); const ref<i64> r = borrow(a); return read(r);")
check("const owner mutable borrow rejected", "const own<i64> a = own(42); mutref<i64> r = borrow_mut(a); return 0;", error="cannot mutably borrow a const owner")
check("const owner move preserved", "const own<i64> a = own(42); const own<i64> b = move(a); return read(b);")
check("const owner move cannot thaw", "const own<i64> a = own(42); own<i64> b = move(a); return 0;", error="cannot move a const owner")
check("const mutable reference cannot write", "own<i64> a = own(42); const mutref<i64> r = borrow_mut(a); write(r, 0); return 0;", error="non-const mutable reference")
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

# Loop state analysis accounts for zero iterations and every continuing backedge.
check("while sum", "i64 i = 0; i64 sum = 0; while (i < 7) { sum = sum + i; i = i + 1; } return sum * 2;")
check("while zero iterations", "i64 value = 42; while (false) { value = 0; } return value;")
check("nested while", "i64 i = 0; i64 sum = 0; while (i < 6) { i64 j = 0; while (j < 7) { sum = sum + 1; j = j + 1; } i = i + 1; } return sum;")
check("while local ownership", "i64 i = 0; i64 sum = 0; while (i < 2) { own<i64> a = own(21); own<i64> b = move(a); sum = sum + read(b); i = i + 1; } return sum;")
check("while mutable borrowing", "own<i64> a = own(0); i64 i = 0; while (i < 6) { mutref<i64> r = borrow_mut(a); write(r, read(r) + 7); i = i + 1; } return read(a);")
check("while existing borrow", "own<i64> a = own(0); mutref<i64> r = borrow_mut(a); i64 i = 0; while (i < 6) { write(r, read(r) + 7); i = i + 1; } return read(r);")
check("while returning move", "own<i64> a = own(42); while (true) { own<i64> b = move(a); return read(b); } return read(a);")
check("while branch returning move", "own<i64> a = own(42); i64 i = 0; while (i < 2) { if (i == 1) { own<i64> b = move(a); return read(b); } i = i + 1; } return read(a);")
check("while zero path retains owner", "own<i64> a = own(42); while (false) { own<i64> b = move(a); return read(b); } return read(a);")
check("while backedge move rejected", "own<i64> a = own(42); while (false) { own<i64> b = move(a); } return 0;", error="loop backedge cannot move")
check("while branch backedge move rejected", "own<i64> a = own(42); while (true) { if (true) { own<i64> b = move(a); } } return 0;", error="loop backedge cannot move")
check("while condition type", "while (1) { return 42; } return 0;", error="expected bool")
check("while cannot escape borrow", "own<i64> a = own(42); while (false) { const ref<i64> r = borrow(a); } return read(r);", error="unknown local")
check("while does not prove return", "while (true) { return 42; }", error="every path")
check("while local move use rejected", "while (true) { own<i64> a = own(42); own<i64> b = move(a); return read(a); } return 0;", error="use after move")
check("while break deferred", "while (true) { break; } return 42;", error="unknown local")

# Arrays have value semantics, checked indexes, and no reference escape surface.
check("array load", "const array<i64, 3> values = {10, 20, 12}; return values[0] + values[1] + values[2];")
check("array mutate", "array<i64, 2> values = {1, 2}; values[0] = 40; return values[0] + values[1];")
check("array copy independent", "array<i64, 2> values = {20, 22}; const array<i64, 2> snapshot = values; values[0] = 100; return snapshot[0] + snapshot[1];")
check("array shadow copy", "const array<i64, 2> values = {20, 22}; { const array<i64, 2> values = values; return values[0] + values[1]; }")
check("array sum loop", "const array<i64, 4> values = {10, 20, 5, 7}; i64 i = 0; i64 sum = 0; while (i < len(values)) { sum = sum + values[i]; i = i + 1; } return sum;")
check("array bool storage", "array<bool, 3> values = {false, true, false}; values[0] = true; if (values[0] == values[1]) { return 42; } return 0;")
check("array reflection", "const array<bool, 3> values = {true, false, true}; static_assert(size_of(array<bool, 3>) == 24); static_assert(type_id(array<bool, 3>) != type_id(array<i64, 3>)); return reflect_size(type_id(array<bool, 3>)) + 18;")
check("array reflection fields", "return reflect_field_count(type_id(array<i64, 3>));", 0)
check("array calls initialization", "module test; auto id(i64 value) -> i64 { return value; } auto test() -> i64 { const array<i64, 3> values = {id(10), id(20), id(12)}; return values[0] + values[1] + values[2]; }")
check("array index exactly once", "own<i64> counter = own(0); mutref<i64> r = borrow_mut(counter); const array<i64, 3> values = {0, 41, 0}; return values[write(r, read(r) + 1)] + read(r);")
check("array assignment index before rhs", "own<i64> counter = own(0); mutref<i64> r = borrow_mut(counter); array<i64, 3> values = {0, 0, 0}; values[write(r, 1)] = write(r, 42); return values[1];")
check("array initializer written order", "own<i64> counter = own(0); mutref<i64> r = borrow_mut(counter); const array<i64, 2> values = {write(r, 20), write(r, read(r) + 2)}; return values[0] + values[1];")
check("array parenthesized indexing", "const array<i64, 1> values = {42}; return (values)[0];")
check("array negative index traps", "const array<i64, 1> values = {42}; return values[-1];", trap="bounds")
check("array upper index traps", "const array<i64, 1> values = {42}; return values[1];", trap="bounds")
check("array maximum index traps", "const array<i64, 1> values = {42}; return values[9223372036854775807];", trap="bounds")
check("array minimum index traps", "const array<i64, 1> values = {42}; return values[-9223372036854775807 - 1];", trap="bounds")
check("array negative store traps", "array<i64, 1> values = {42}; values[-1] = 0; return 42;", trap="bounds")
check("array upper store traps", "array<i64, 1> values = {42}; values[1] = 0; return 42;", trap="bounds")
check("array bounds before RHS", "module test; auto spin() -> i64 { while (true) {} return 0; } auto test() -> i64 { array<i64, 1> values = {42}; values[1] = spin(); return 42; }", trap="bounds")
check("array immutable assignment", "const array<i64, 1> values = {42}; values[0] = 0; return 0;", error="mutable array local")
check("array bool index rejected", "const array<i64, 1> values = {42}; return values[true];", error="expected i64")
check("array element type rejected", "const array<i64, 1> values = {true}; return 0;", error="expected i64")
check("array store type rejected", "array<bool, 1> values = {false}; values[0] = 1; return 0;", error="expected bool")
check("array short initializer", "const array<i64, 2> values = {42}; return 0;", error="initializer length")
check("array long initializer", "const array<i64, 1> values = {42, 0}; return 0;", error="initializer length")
check("array zero length rejected", "const array<i64, 0> values = {}; return 0;", error="between 1 and 4096")
check("array oversized rejected", "const array<i64, 4097> values = {}; return 0;", error="between 1 and 4096")
check("array enormous length rejected", "const array<i64, 9999999999999999999999> values = {}; return 0;", error="decimal integer literal")
check("array nested element rejected", "const array<array<i64, 1>, 1> values = {}; return 0;", error="elements currently require")
check("array owned element rejected", "const array<own<i64>, 1> values = {}; return 0;", error="elements currently require")
check("array wrong copy length", "const array<i64, 1> a = {42}; const array<i64, 2> b = a; return 0;", error="expected array<i64, 2>")
check("array wrong copy element", "const array<bool, 1> a = {true}; const array<i64, 1> b = a; return 0;", error="expected array<i64, 1>")
check("array borrowing rejected", "array<i64, 1> a = {42}; const ref<i64> r = borrow(a); return 0;", error="expected own<i64>")
check("array element borrowing rejected", "array<i64, 1> a = {42}; const ref<i64> r = borrow(a[0]); return 0;", error="requires a local name")
check("array returned rejected", "const array<i64, 1> a = {42}; return a;", error="array values are only")
check("array parameter deferred", "module test; auto test(array<i64, 1> a) -> i64 { return 0; }", error="only scalar function parameters")
check("array lifetime ends", "{ const array<i64, 1> a = {42}; } return a[0];", error="unknown local")
check("array initializer cannot see itself", "const array<i64, 1> a = {a[0]}; return 0;", error="unknown local")
check("scalar cannot index", "const i64 a = 42; return a[0];", error="indexing requires an array")
check("scalar cannot len", "const i64 a = 42; return len(a);", error="len requires an array")
check("class public array field rejected", "module test; class A { public: array<i64, 1> a; }; auto test() -> i64 { return 0; }", error="array fields must be private")
check("array reserved class name", "module test; class array {}; auto test() -> i64 { return 0; }", error="reserved builtin storage name")
# Both per-array and aggregate frame resource limits are checked before offset arithmetic.
large_init = ",".join("1" for _ in range(4096))
check("maximum supported array", "const array<i64, 4096> a = {" + large_init + "}; return a[4095] + 41;")
check("stack layout cap", "const array<i64, 4096> a = {" + large_init + "}; const array<i64, 4096> b = a; const i64 c = 0; return c;", error="stack frame exceeds 65536")

# Accepted boundary cases accompany separate adversarial depth-rejection fixtures.
check("deep bounded parentheses", "return " + "(" * 100 + "42" + ")" * 100 + ";")
check("deep bounded blocks", "{" * 100 + "return 42;" + "}" * 100)
check("bounded skew expression", "return 42" + "+0" * 100 + ";")
check("mixed bounded block and expression depths", "{" * 100 + "return " + "(" * 100 + "42" + ")" * 100 + ";" + "}" * 100)

random.seed(42)
for i in range(12):
    a,b,c,d = (random.randrange(-1000, 1000) for _ in range(4))
    check(f"arithmetic differential {i}", f"return ({a} + {b}) * ({c} - {d});", (a+b)*(c-d))
print(f"{PASS} compiler tests passed")
