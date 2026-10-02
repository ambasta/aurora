#!/usr/bin/env python3
"""Compile source, assemble/link directly, run native assembly, check diagnostics."""
from pathlib import Path
import random
import subprocess
import sys
import tempfile

COMPILER = Path(sys.argv[1] if len(sys.argv) > 1 else "build/aurorac").resolve()
PASS = 0

def require(condition, message):
    if not condition:
        raise AssertionError(message)

def command(args, good=True):
    result = subprocess.run([str(x) for x in args], capture_output=True, text=True)
    if good and result.returncode:
        raise AssertionError(f"{args}: exit {result.returncode}\n{result.stdout}{result.stderr}")
    return result

def check(name, body, expected=42, error=None):
    global PASS
    with tempfile.TemporaryDirectory(prefix="aurora-test-") as directory:
        root = Path(directory)
        source = root / "input.au"
        source.write_text(body if body.startswith("module ") else "module test; fn test() -> i64 { " + body + " }")
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
            command([root / "program"])
    PASS += 1
    print(f"PASS {name}")

check("leading zero decimal", "return 010 + 032;")
check("leading zero eight", "return 08;", 8)
check("leading zero reflection agreement", "static_assert(010 == 10); return 010;", 10)
check("precedence", "return 2 + 4 * 10;")
check("signed arithmetic", "return -8 * 3 + 2;", -22)
check("wrapping arithmetic", "return 9223372036854775807 + 1;", -9223372036854775808)
check("mutable scalar", "let mut x: i64 = 1; x = x + 41; return x;")
check("scalar shadowing", "let x: i64 = 42; { let x: bool = false; } return x;")
check("branch then", "if (3 < 4) { return 42; } else { return 9; }")
check("branch else", "if (3 >= 4) { return 9; } else { return 42; }")
check("bool comparison", "if (true == !false) { return 42; } return 0;")
check("nested functions", "module test; fn inc(x: i64) -> i64 { return x + 1; } fn test() -> i64 { return 2 * inc(20); }")
check("six argument ABI", "module test; fn sum(a: i64,b: i64,c: i64,d: i64,e: i64,f: i64) -> i64 { return a+b+c+d+e+f; } fn id(x: i64) -> i64 { return x; } fn test() -> i64 { return 1 + sum(id(1),2,3,4,5,id(26)); }")
check("forward call", "module test; fn test() -> i64 { return answer(); } fn answer() -> i64 { return 42; }")
check("bool function", "module test; fn yes(x: i64) -> bool { return x == 42; } fn test() -> i64 { if (yes(42)) { return 42; } else { return 0; } }")
check("adjacent generic initializer", "let a: own<i64>=own(42); return read(a);")
check("owned move", "let a: own<i64> = own(42); let b: own<i64> = move(a); return read(b);")
check("shared borrows", "let a: own<i64> = own(21); let b: ref<i64> = borrow(a); let c: ref<i64> = borrow(a); return read(b) + read(c);")
check("exclusive borrow", "let a: own<i64> = own(2); { let b: mutref<i64> = borrow_mut(a); write(b, read(b) * 21); } return read(a);")
check("borrow release", "let a: own<i64> = own(42); { let b: ref<i64> = borrow(a); } let c: own<i64> = move(a); return read(c);")
check("branch borrow release", "let a: own<i64> = own(42); if (true) { let b: ref<i64> = borrow(a); } let c: own<i64> = move(a); return read(c);")
check("return path excludes move", "let a: own<i64> = own(42); if (false) { let b: own<i64> = move(a); return read(b); } return read(a);")
check("return else excludes move", "let a: own<i64> = own(42); if (true) { } else { let b: own<i64> = move(a); return read(b); } return read(a);")
check("reflection constant", "static_assert(size_of(i64) == 8); static_assert(type_id(bool) != type_id(i64)); return size_of(i64) + 34;")
check("reflection dynamic", "module test; fn inspect(id: i64) -> i64 { return reflect_size(id); } fn test() -> i64 { return inspect(type_id(i64)) + 34; }")
check("reflection bool", "return reflect_size(type_id(bool));", 1)
check("reflection unknown", "return reflect_size(999);", 0)
check("reflection negative", "return reflect_size(-1);", 0)

negative = [
    ("use after move", "let a: own<i64> = own(42); let b: own<i64> = move(a); return read(a);", "use after move"),
    ("double move", "let a: own<i64> = own(42); let b: own<i64> = move(a); let c: own<i64> = move(a); return 0;", "use after move"),
    ("copy owner", "let a: own<i64> = own(42); let b: i64 = a; return b;", "cannot be implicitly copied"),
    ("implicit owned initialization", "let a: own<i64> = own(42); let b: own<i64> = a; return 0;", "explicit constructor"),
    ("move shared borrowed", "let a: own<i64> = own(42); let b: ref<i64> = borrow(a); let c: own<i64> = move(a); return 0;", "cannot move a borrowed"),
    ("move mutably borrowed", "let a: own<i64> = own(42); let b: mutref<i64> = borrow_mut(a); let c: own<i64> = move(a); return 0;", "cannot move a borrowed"),
    ("shared then mutable", "let a: own<i64> = own(42); let b: ref<i64> = borrow(a); let c: mutref<i64> = borrow_mut(a); return 0;", "conflicting borrow"),
    ("mutable then shared", "let a: own<i64> = own(42); let b: mutref<i64> = borrow_mut(a); let c: ref<i64> = borrow(a); return 0;", "conflicting borrow"),
    ("two mutable borrows", "let a: own<i64> = own(42); let b: mutref<i64> = borrow_mut(a); let c: mutref<i64> = borrow_mut(a); return 0;", "conflicting borrow"),
    ("owner read during exclusive borrow", "let a: own<i64> = own(42); let b: mutref<i64> = borrow_mut(a); return read(a);", "exclusively borrowed"),
    ("write shared ref", "let a: own<i64> = own(42); let b: ref<i64> = borrow(a); write(b, 0); return 0;", "expected mutref"),
    ("borrow expired scope", "let a: own<i64> = own(42); { let b: ref<i64> = borrow(a); } return read(b);", "unknown local"),
    ("moved on then path", "let a: own<i64> = own(42); if (true) { let b: own<i64> = move(a); } return read(a);", "use after move"),
    ("moved on else path", "let a: own<i64> = own(42); if (false) { } else { let b: own<i64> = move(a); } return read(a);", "use after move"),
    ("nested branch move", "let a: own<i64> = own(42); if (true) { if (true) { let b: own<i64> = move(a); } } return read(a);", "use after move"),
    ("immutable assignment", "let a: i64 = 1; a = 42; return a;", "mutable scalar"),
    ("type mismatch", "let a: bool = 42; return 42;", "expected bool"),
    ("nonboolean condition", "if (42) { return 1; } return 0;", "expected bool"),
    ("missing return", "let a: i64 = 42;", "every path"),
    ("missing branch return", "if (true) { return 42; }", "every path"),
    ("uninitialized local", "let a: i64; return a;", "expected '='"),
    ("out of scope", "{ let a: i64 = 42; } return a;", "unknown local"),
    ("duplicate local", "let a: i64 = 1; let a: i64 = 2; return a;", "duplicate local"),
    ("failed assertion", "static_assert(size_of(i64) == 4); return 42;", "static assertion failed"),
    ("nonconstant assertion", "let a: i64 = 8; static_assert(a == 8); return 42;", "static_assert supports"),
    ("overflow literal", "return 9223372036854775808;", "out of range"),
    ("unknown function", "return missing();", "unknown function"),
    ("borrow scalar", "let a: i64 = 42; let b: ref<i64> = borrow(a); return 42;", "expected own"),
    ("reference escape", "module test; fn test() -> ref<i64> { let a: own<i64> = own(42); return borrow(a); }", "only scalar function results"),
    ("unsupported pointer", "let x: ptr<i64> = 0; return 42;", "unsupported type"),
    ("unsupported class methods", "module test; class A { fn f() -> i64 { return 1; } }", "reserved identifier"),
    ("unreachable code", "return 42; return 0;", "unreachable statement"),
    ("duplicate function", "module test; fn test() -> i64 { return 42; } fn test() -> i64 { return 0; }", "duplicate or reserved"),
    ("builtin collision", "module test; fn reflect_size() -> i64 { return 42; }", "duplicate or reserved"),
    ("argument type", "module test; fn f(x: bool) -> i64 { return 42; } fn test() -> i64 { return f(1); }", "expected bool"),
    ("argument count", "module test; fn f(x: i64) -> i64 { return x; } fn test() -> i64 { return f(); }", "wrong argument count"),
]
for name, body, diagnostic in negative:
    check(name, body, error=diagnostic)
# Class values: all storage belongs to the current stack frame; scalar fields copy.
class_prefix = "module test; class Point { x: i64; y: i64; } "
def class_check(name, body, expected=42, error=None):
    check(name, class_prefix + "fn test() -> i64 { " + body + " }", expected, error)

class_check("parenthesized class field", "let p: Point = Point { x: 20, y: 22 }; return (p).x + (p).y;")
class_check("class construct and fields", "let p: Point = Point { x: 20, y: 22 }; return p.x + p.y;")
class_check("class reordered fields", "let p: Point = Point { y: 22, x: 20 }; return p.x + p.y;")
class_check("class independent copy", "let mut p: Point = Point { x: 20, y: 22 }; let q: Point = p; p.x = 100; return q.x + q.y;")
class_check("class mutable field", "let mut p: Point = Point { x: 1, y: 2 }; p.x = 40; return p.x + p.y;")
class_check("class shadow copy", "let p: Point = Point { x: 20, y: 22 }; { let p: Point = p; return p.x + p.y; }")
class_check("class branch field update", "let mut p: Point = Point { x: 20, y: 2 }; if (true) { p.y = 22; } return p.x + p.y;")
class_check("class reflection static", "static_assert(size_of(Point) == 16); static_assert(field_count(Point) == 2); return 42;")
class_check("class reflection runtime", "let id: i64 = type_id(Point); return reflect_size(id) + reflect_field_count(id) + 24;")
check("class runtime dynamic id", class_prefix + "fn inspect(id: i64) -> i64 { return reflect_size(id) + reflect_field_count(id); } fn test() -> i64 { return inspect(type_id(Point)); }", 18)
check("class bool field", "module test; class Flag { enabled: bool; value: i64; } fn test() -> i64 { let mut f: Flag = Flag { value: 42, enabled: false }; f.enabled = true; if (f.enabled) { return f.value; } return 0; }")
check("empty class", "module test; class Empty {} fn test() -> i64 { let e: Empty = Empty {}; let f: Empty = e; static_assert(field_count(Empty) == 0); return size_of(Empty); }", 8)
check("classes declared after function", "module test; fn test() -> i64 { let p: Pair = Pair { x: 42 }; return p.x; } class Pair { x: i64; }")
check("class call fields", class_prefix + "fn id(x: i64) -> i64 { return x; } fn test() -> i64 { let p: Point = Point { y: id(22), x: id(20) }; return p.x + p.y; }")
check("multiple class type IDs", "module test; class A { x: i64; } class B { x: i64; y: i64; } fn test() -> i64 { static_assert(type_id(A) != type_id(B)); return reflect_size(type_id(A)) + reflect_size(type_id(B)); }", 24)
class_check("missing class field", "let p: Point = Point { x: 42 }; return 0;", error="every class field")
class_check("duplicate class initializer", "let p: Point = Point { x: 42, x: 0 }; return 0;", error="duplicate field initializer")
class_check("unknown class initializer", "let p: Point = Point { x: 42, z: 0 }; return 0;", error="unknown field")
class_check("class field type mismatch", "let p: Point = Point { x: false, y: 0 }; return 0;", error="expected i64")
class_check("class unknown field read", "let p: Point = Point { x: 20, y: 22 }; return p.z;", error="unknown field")
class_check("class immutable mutation", "let p: Point = Point { x: 20, y: 22 }; p.x = 0; return 0;", error="mutable class local")
class_check("class mutation type mismatch", "let mut p: Point = Point { x: 20, y: 22 }; p.x = false; return 0;", error="expected i64")
class_check("class local uninitialized read", "let p: Point = Point { x: p.x, y: 22 }; return 0;", error="unknown local")
class_check("class wrong constructor", "let p: Point = Other { x: 20, y: 22 }; return 0;", error="expected Point")
class_check("class unknown type", "let p: Other = Other {}; return 0;", error="unknown class type")
class_check("class unavailable outside scope", "{ let p: Point = Point { x: 20, y: 22 }; } return p.x;", error="unknown local")
class_check("class wrong scalar context", "let p: Point = Point { x: 20, y: 22 }; return p;", error="class values are only")
class_check("class borrow not yet supported", "let p: Point = Point { x: 20, y: 22 }; let r: ref<i64> = borrow(p); return 0;", error="expected own<i64>")
class_check("class unknown reflection", "return size_of(Missing);", error="unknown class type")
check("class duplicate declaration", "module test; class A {} class A {} fn test() -> i64 { return 0; }", error="duplicate or reserved class")
check("class duplicate fields", "module test; class A { x: i64; x: bool; } fn test() -> i64 { return 0; }", error="duplicate class field")
check("class owned field rejected", "module test; class A { x: own<i64>; } fn test() -> i64 { return 0; }", error="class fields currently require")
check("class nested field rejected", "module test; class A { x: Point; } fn test() -> i64 { return 0; }", error="class fields currently require")
check("class reserved name", "module test; class i64 {} fn test() -> i64 { return 0; }", error="duplicate or reserved class")
check("class function name collision", "module test; class A {} fn A() -> i64 { return 0; }", error="duplicate or reserved function")
check("class wrong copy type", "module test; class A { x: i64; } class B { x: i64; } fn test() -> i64 { let a: A = A { x: 1 }; let b: B = a; return 0; }", error="expected B")
check("class parameter deferred", "module test; class A {} fn test(a: A) -> i64 { return 0; }", error="only scalar function parameters")
check("class return deferred", "module test; class A {} fn test() -> A { return A {}; }", error="only scalar function results")
check("scalar field count", "return reflect_field_count(type_id(i64));", 0)
check("unknown field count", "return reflect_field_count(77);", 0)

random.seed(42)
for i in range(12):
    a,b,c,d = (random.randrange(-1000, 1000) for _ in range(4))
    check(f"arithmetic differential {i}", f"return ({a} + {b}) * ({c} - {d});", (a+b)*(c-d))
print(f"{PASS} compiler tests passed")
