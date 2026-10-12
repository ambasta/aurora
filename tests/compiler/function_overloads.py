#!/usr/bin/env python3
"""Exact ordinary overload source/native gate. Checks survive Python -O.

All 64 native return bits and exact trap sites are observed. Rejections run with
absent and preserved output; source and library inputs stay byte-identical.
Failures are retained. This finite suite is not a language safety proof.
"""

from pathlib import Path
import argparse, hashlib, json, random, re, resource, shutil, subprocess, tempfile, time
from itertools import product
from composed_values import Trap, observer_self_test, program, require, signed_bits
from integer_oracle import NativeRunner, validate_trap, validate_values

ROOT = Path(__file__).resolve().parents[2]
PRESERVED = b"previous verified assembly\x00\xff\n"
SCALARS = ("i64", "u64", "u8", "bool")
VALUES = {"i64": "-7", "u64": "18446744073709551615u64", "u8": "255u8", "bool": "true"}
COUNTER = (
    "class Counter{i64 value;public:Counter(i64 n):value(n){}auto get()const->i64{return value;}auto add(i64 n)"
    "->i64{value=value+n;return value;}};"
)


def p(body, definitions="", imports="", result="i64"):
    return program(body, definitions, imports=imports, result=result)


class Suite:
    def __init__(self, directory, compiler, keep_going=False, fixture="", plan_only=False):
        self.directory, self.compiler = directory, compiler
        self.keep_going, self.fixture, self.plan_only = keep_going, fixture, plan_only
        self.runner = None if plan_only else NativeRunner(directory, compiler, 5)
        self.library_inputs = (
            {} if plan_only else {path: path.read_bytes() for path in (ROOT / "library").rglob("*.au")}
        )
        self.count = self.traps = self.rejections = self.negative_fixtures = 0
        self.attempts = self.selected_fixtures = 0
        self.failures, self.names = [], set()

    def check(self, name, source, expected=42, error=None, modules=None, existing_output=None, _selected=False):
        if not _selected:
            require(name not in self.names, "duplicate fixture name: " + name)
            self.names.add(name)
            if self.fixture and self.fixture.lower() not in name.lower():
                return
            self.selected_fixtures += 1
        self.attempts += 1
        if self.plan_only:
            self.count += 1
            self.rejections += int(error is not None)
            self.traps += int(isinstance(expected, Trap) and error is None)
            print("PLAN function overloads", name, flush=True)
            return
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", name)[:75].strip("-")
        directory = Path(tempfile.mkdtemp(prefix=slug + "-", dir=self.directory))
        source_path, output = directory / "input.au", directory / "compiled.s"
        source_path.write_text(source)
        inputs = dict(self.library_inputs)
        inputs[source_path] = source.encode()
        roots = [ROOT / "library"]
        if modules:
            root = directory / "modules"
            root.mkdir()
            roots.insert(0, root)
            for module, content in modules.items():
                path = root / (module.replace(".", "/") + ".au")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
                inputs[path] = content.encode()
        if existing_output is not None:
            output.write_bytes(existing_output)
        command = [str(self.compiler), str(source_path), "-o", str(output)]
        for root in roots:
            command.extend(["--module-root", str(root)])
        (directory / "command.json").write_text(json.dumps(command, indent=2) + "\n")
        original_runner_directory = self.runner.directory
        try:
            compiled = subprocess.run(
                command,
                capture_output=True,
                timeout=10,
                preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)),
            )
            (directory / "stdout.bin").write_bytes(compiled.stdout)
            (directory / "stderr.bin").write_bytes(compiled.stderr)
            for path, before in inputs.items():
                require(path.read_bytes() == before, name + ": input changed: " + str(path))
            if error is not None:
                require(
                    compiled.returncode == 1,
                    f"{name}: expected compiler exit 1, got {compiled.returncode}: {compiled.stderr!r}",
                )
                require(bool(compiled.stderr), name + ": missing rejection diagnostic")
                if existing_output is None:
                    require(not output.exists(), name + ": artifact created on rejection")
                else:
                    require(output.read_bytes() == existing_output, name + ": previous output changed on rejection")
                if error is not True:
                    fragments = (error,) if isinstance(error, str) else error
                    require(
                        any(x.lower().encode() in compiled.stderr.lower() for x in fragments),
                        name + ": unexpected diagnostic: " + repr(compiled.stderr),
                    )
                self.rejections += 1
            else:
                require(compiled.returncode == 0, f"{name}: compiler exit {compiled.returncode}: {compiled.stderr!r}")
                self.runner.directory = directory
                observed, symbols = self.runner.assemble(output.read_text(), ["test"])
                if isinstance(expected, Trap):
                    validate_trap(observed, expected, symbols, name)
                    self.traps += 1
                else:
                    validate_values(observed, [signed_bits(expected)], [name])
            self.count += 1
            print("PASS function overloads", name, flush=True)
        except (AssertionError, OSError, subprocess.TimeoutExpired) as failure:
            details = f"{name}: {failure}\nPreserved reproduction: {directory}"
            (directory / "failure.txt").write_text(details + "\n")
            self.failures.append(details)
            print("FAIL function overloads", details, flush=True)
            if not self.keep_going:
                raise AssertionError(details) from failure
        else:
            shutil.rmtree(directory)
        finally:
            self.runner.directory = original_runner_directory

    def reject(self, name, source, error=True, modules=None):
        require(name not in self.names, "duplicate fixture name: " + name)
        self.names.add(name)
        if self.fixture and self.fixture.lower() not in name.lower():
            return
        self.selected_fixtures += 1
        before = self.rejections
        for suffix, previous in (("absent output", None), ("saved output", PRESERVED)):
            self.check(
                name + ": " + suffix, source, error=error, modules=modules, existing_output=previous, _selected=True
            )
        if self.rejections == before + 2:
            self.negative_fixtures += 1


def cases(s):
    s.check(
        "class temporary selects copied overload",
        p(
            "return pick(Counter(42));",
            COUNTER + "auto pick(Counter c)->i64{return c.get();}auto pick(i64 c)->i64{return c;}",
        ),
        42,
    )
    definitions = "".join(f"auto pick({t} x)->i64{{return {i + 39};}}" for i, t in enumerate(SCALARS))
    for i, t in enumerate(SCALARS):
        s.check("four exact scalars " + t, p(f"return pick({VALUES[t]});", definitions), i + 39)
    for left, right in product(SCALARS, repeat=2):
        defs = "".join(
            f"auto pick({a} x,{b} y)->i64{{return {n};}}" for n, (a, b) in enumerate(product(SCALARS, repeat=2))
        )
        expected = list(product(SCALARS, repeat=2)).index((left, right))
        s.check(
            "ordered scalar tuple " + left + "/" + right,
            p(f"return pick({VALUES[left]},{VALUES[right]});", defs),
            expected,
        )
    for declarations in (
        definitions,
        "".join(reversed([f"auto pick({t} x)->i64{{return {i + 39};}}" for i, t in enumerate(SCALARS)])),
    ):
        s.check("declaration permutation " + str(len(s.names)), p("return pick(true);", declarations))
    s.check(
        "zero through six parameters",
        p(
            "return pick()+pick(1,2,3,4,5,6);",
            "auto pick()->i64{return 21;}auto pick(i64 a,i64 b,i64 c,i64 d,i64 e,i64 f)->i64{return a+b+c+d+e+f;}",
        ),
    )
    s.check(
        "nested exact selection",
        p(
            "return pick(inc(41));",
            (
                "auto inc(i64 x)->i64{return x+1;}auto inc(u8 x)->u8{return x;}auto pick(i64 x)->i64{return x;}"
                "auto pick(u8 x)->i64{return 0;}"
            ),
        ),
    )
    s.check(
        "scalar arguments evaluate once left to right",
        p(
            "Counter c=Counter(0);return pick(c.add(1),c.add(10),c.add(100));",
            COUNTER
            + (
                "auto pick(i64 a,i64 b,i64 c)->i64{if(a==1){if(b==11){if(c==111){return 42;}}}return 0;}auto pi"
                "ck(u8 a,u8 b,u8 c)->i64{return 1;}"
            ),
        ),
    )
    s.check(
        "class snapshot before later mutation",
        p(
            "Counter c=Counter(41);return pick(c,c.add(1));",
            COUNTER
            + (
                "auto pick(Counter c,i64 v)->i64{if(c.get()==41){return v;}return 0;}auto pick(i64 c,i64 v)->i6"
                "4{return 0;}"
            ),
        ),
    )
    s.check(
        "class snapshot after earlier mutation",
        p(
            "Counter c=Counter(41);return pick(c.add(1),c);",
            COUNTER
            + (
                "auto pick(i64 v,Counter c)->i64{if(c.get()==42){return v;}return 0;}auto pick(i64 v,i64 c)->i6"
                "4{return 0;}"
            ),
        ),
    )
    s.check(
        "copied class results",
        p(
            "Counter c=Counter(42);Counter result=pick(c);c.add(1);return result.get();",
            COUNTER + "auto pick(Counter c)->Counter{return c;}auto pick(i64 c)->i64{return c;}",
        ),
    )
    s.check(
        "result type irrelevant but distinct arguments",
        p(
            "Counter c=pick(42);return c.get();",
            COUNTER
            + "auto pick(i64 n)->Counter{const Counter c=Counter(n);return c;}auto pick(u8 n)->bool{return true;}",
        ),
    )
    s.check(
        "nominal enums",
        p(
            "return pick(B::ready);",
            "enum class A{ready};enum class B{ready};auto pick(A x)->i64{return 0;}auto pick(B x)->i64{return 42;}",
        ),
    )
    s.check(
        "nominal empty classes",
        p(
            "B b=B();return pick(b);",
            "class A{public:A(){}};class B{public:B(){}};auto pick(A x)->i64{return 0;}auto pick(B x)->i64{return 42;}",
        ),
    )
    s.check(
        "readonly span and scalar dispatch",
        p(
            "array<u8,1> a={42u8};return pick(borrow_bytes(a));",
            "auto pick(builtin::span<const u8> a)->i64{return i64(a.at(0));}auto pick(i64 x)->i64{return x;}",
        ),
    )
    s.check(
        "readonly span reborrow cleanup",
        p(
            (
                "array<u8,1> a={41u8};{const builtin::span<const u8> b=borrow_bytes(a);pick(b);}a[0]=42u8;retur"
                "n pick(borrow_bytes(a));"
            ),
            "auto pick(builtin::span<const u8> a)->i64{return i64(a.at(0));}auto pick(i64 x)->i64{return x;}",
        ),
    )
    s.check(
        "ordinary calls in generic body",
        p(
            "return relay<u8>(42u8);",
            (
                "auto pick(i64 x)->i64{return 0;}auto pick(u8 x)->i64{return i64(x);}template<Scalar T>auto rel"
                "ay(T x)->i64{return pick(x);}"
            ),
        ),
    )
    s.check(
        "ordinary overload calls explicit generic result",
        p(
            "return pick(identity<u8>(42u8));",
            (
                "auto pick(i64 x)->i64{return 0;}auto pick(u8 x)->i64{return i64(x);}template<Scalar T>auto ide"
                "ntity(T x)->T{return x;}"
            ),
        ),
    )
    s.check(
        "constructor initializer uses overload",
        p(
            "Counter c=Counter(pick(40u8));return c.get();",
            COUNTER + "auto pick(i64 x)->i64{return 0;}auto pick(u8 x)->i64{return i64(x)+2;}",
        ),
    )
    s.check(
        "ordinary overload call from method",
        p(
            "Box b=Box();return b.run();",
            (
                "auto pick(i64 x)->i64{return x;}auto pick(u8 x)->i64{return 0;}class Box{public:Box(){}auto ru"
                "n()const->i64{return pick(42);}};"
            ),
        ),
    )
    for count in (31, 32):
        defs = "".join(f"class C{i}{{public:C{i}(){{}}}};auto pick(C{i} x)->i64{{return {i};}}" for i in range(count))
        s.check("overload budget " + str(count), p(f"C{count - 1} c=C{count - 1}();return pick(c);", defs), count - 1)
    module = (
        "export module helpers;export namespace api{auto pick(i64 n)->i64{return 0;}auto pick(u8 n)->i64{return"
        " i64(n);}}"
    )
    s.check(
        "imported exported set", p("return api::pick(42u8);", imports="import helpers;"), modules={"helpers": module}
    )
    module = (
        "export module helpers;namespace api{auto pick(i64 n)->i64{return n;}export auto pick(u8 n)->i64{return"
        " pick(i64(n));}}"
    )
    s.check(
        "private overload available to defining body",
        p("return api::pick(42u8);", imports="import helpers;"),
        modules={"helpers": module},
    )
    s.reject(
        "private overload unavailable to importer",
        p("return api::pick(42);", imports="import helpers;"),
        "no exact",
        modules={"helpers": module},
    )
    for name, defs, body, error in [
        (
            "same tuple duplicate",
            "auto pick(i64 x)->i64{return x;}auto pick(i64 y)->i64{return y;}",
            "return 42;",
            "duplicate",
        ),
        (
            "return cannot discriminate",
            "auto pick(i64 x)->i64{return x;}auto pick(i64 x)->u8{return 1u8;}",
            "return 42;",
            "duplicate",
        ),
        (
            "no implicit conversion",
            "auto pick(u64 x)->i64{return 42;}auto pick(u8 x)->i64{return 42;}",
            "return pick(42);",
            "no exact",
        ),
        (
            "nominal class mismatch",
            (
                "class A{public:A(){}};class B{public:B(){}};class C{public:C(){}};auto pick(A a)->i64{return 1"
                ";}auto pick(B b)->i64{return 2;}"
            ),
            "C c=C();return pick(c);",
            "no exact",
        ),
        (
            "wrong arity before unknown argument",
            "auto pick(i64 a)->i64{return a;}auto pick(u8 a)->i64{return 0;}",
            "return pick(missing,missing);",
            "wrong argument count",
        ),
        (
            "wrong arity before invalid literal",
            "auto pick(i64 a)->i64{return a;}auto pick(u8 a)->i64{return 0;}",
            "return pick(999999999999999999999999999999,1);",
            "wrong argument count",
        ),
        (
            "scalar result cannot initialize class",
            COUNTER + "auto pick(i64 x)->i64{return x;}auto pick(u8 x)->Counter{const Counter c=Counter(42);return c;}",
            "Counter c=pick(42);return c.get();",
            "expected",
        ),
        (
            "class result cannot be scalar",
            COUNTER
            + "auto pick(i64 x)->Counter{const Counter c=Counter(x);return c;}auto pick(u8 x)->i64{return i64(x);}",
            "return pick(42);",
            "typed local",
        ),
        (
            "private field remains inaccessible",
            (
                "class C{i64 secret;public:C():secret(42){}};auto pick(i64 c)->i64{return c;}auto pick(u8 c)->i"
                "64{return i64(c);}"
            ),
            "C c=C();return pick(c.secret);",
            "private",
        ),
        (
            "ordinary template collision",
            "template<Scalar T>auto pick(T x)->T{return x;}auto pick(i64 x)->i64{return x;}",
            "return 42;",
            "duplicate",
        ),
        (
            "ordinary template set collision",
            (
                "template<Scalar T>auto pick(T x)->T{return x;}auto pick(i64 x)->i64{return x;}auto pick(u8 x)-"
                ">i64{return i64(x);}"
            ),
            "return 42;",
            "duplicate",
        ),
        (
            "method overload remains rejected",
            "class C{public:C(){}auto run(i64 x)->i64{return x;}auto run(u8 x)->i64{return i64(x);}};",
            "return 42;",
            "duplicate",
        ),
        (
            "overloaded root answer",
            "auto answer()->i64{return 42;}auto answer(i64 x)->i64{return x;}",
            "return 42;",
            "entrypoint",
        ),
        (
            "seventh parameter remains rejected",
            "auto pick(i64 a,i64 b,i64 c,i64 d,i64 e,i64 f,i64 g)->i64{return 42;}auto pick()->i64{return 42;}",
            "return 42;",
            "six",
        ),
        (
            "namespace name collision",
            "namespace pick{}auto pick(i64 a)->i64{return a;}auto pick(u8 a)->i64{return 0;}",
            "return 42;",
            "collide",
        ),
        (
            "nonmatching narrower scope blocks outer",
            definitions
            + (
                "namespace n{auto pick(u8 a)->i64{return 0;}auto pick(u64 a)->i64{return 0;}auto run()->i64{ret"
                "urn pick(true);}}"
            ),
            "return n::run();",
            "no exact",
        ),
    ]:
        s.reject(name, p(body, defs), error)
    defs = "".join(f"class C{i}{{public:C{i}(){{}}}};auto pick(C{i} x)->i64{{return {i};}}" for i in range(33))
    s.reject("33 declaration budget rejected", p("return 42;", defs), "32")
    s.reject(
        "unused cross-module overload collision",
        p("return 42;", imports="import left;import right;"),
        "ambiguous",
        modules={
            "left": "export module left;export auto pick(i64 n)->i64{return n;}",
            "right": "export module right;export auto pick(u8 n)->i64{return i64(n);}",
        },
    )
    s.check(
        "nested argument overflow exact trap",
        p(
            "return pick(9223372036854775807+1);",
            "auto pick(i64 n)->i64{return n;}auto pick(u8 n)->i64{return i64(n);}",
        ),
        Trap.OVERFLOW,
    )
    s.check(
        "nested argument bounds exact trap",
        p(
            "array<i64,1> a={42};return pick(a[1]);",
            "auto pick(i64 n)->i64{return n;}auto pick(u8 n)->i64{return i64(n);}",
        ),
        Trap.BOUNDS,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    parser.add_argument("--keep-going", action="store_true")
    args = parser.parse_args()
    (ROOT / "tmp").mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="function-overloads-", dir=ROOT / "tmp"))
    s = Suite(directory, args.compiler.resolve(), args.keep_going)
    print("INFO overload compiler sha256=" + hashlib.sha256(s.compiler.read_bytes()).hexdigest(), flush=True)
    observer_self_test(s)
    cases(s)
    require(s.count + len(s.failures) == s.attempts, "execution accounting mismatch")
    require(s.rejections == 2 * s.negative_fixtures, "rejection accounting mismatch")
    print(
        f"INFO overloads {s.selected_fixtures} fixtures; {s.count} execu"
        f"tions; {s.count - s.traps - s.rejections} native returns; "
        f"{s.traps} exact-site traps; {s.negative_fixtures} negative fix"
        f"tures; {s.rejections} rejection runs; {len(s.failures)} failures",
        flush=True,
    )
    require(not s.failures, "failed fixtures remain in " + str(directory))
    shutil.rmtree(directory)
    print("PASS function overloads complete", flush=True)


if __name__ == "__main__":
    main()
