#!/usr/bin/env python3
"""Executable copied ordinary-method parameter contract (M022).

Run: python3 -O tests/compiler/method_values.py build/aurorac
     python3 -O tests/compiler/method_values.py --plan-only

Native results preserve all 64 bits. Traps require kernel SIGILL at the exact
named UD2 instruction. Every rejection preserves absent and byte-exact existing
output, and all source/module/library inputs. Explicit require() checks survive
-O. Successful temporary artifacts are deleted; failures retain reproduction
source, modules, command, diagnostics and native artifacts under this checkout's
evidence/. Model expectations use independent Python lists, not compiler output.
These are finite regression/model checks, not a safety or performance proof.
No kernel images or historical artifacts are created or removed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import resource
import shutil
import subprocess
import tempfile
import time

from composed_values import Trap, observer_self_test, program, require, signed_bits
from integer_oracle import NativeRunner, validate_trap, validate_values

ROOT = Path(__file__).resolve().parents[2]
PRESERVED = b"previous verified assembly\x00\xff\n"
SCALARS = ("i64", "u64", "u8", "bool")
ENUMS = "enum class Status{ready,failed};enum class Other{ready,failed};"
EMPTY = "class Empty{public:Empty(){}auto answer()const->i64{return 42;}};"
COUNTER = """class Counter{
    i64 value;
public:
    Counter(i64 n):value(n){}
    auto get()const->i64{return value;}
    auto set(i64 n)->i64{value=n;return value;}
    auto add(i64 n)->i64{value=value+n;return value;}
    auto inspect(Counter source)const->i64{return source.get();}
    auto copy(Counter source)const->Counter{return source;}
    auto replace(Counter source)->Counter{
        const Counter old=Counter(value);value=source.get();return old;
    }
};"""


def p(body, definitions="", helpers="", imports="", result="i64"):
    return program(body, definitions, helpers, imports, result)


def lit(scalar, value):
    if scalar == "bool":
        return "true" if value else "false"
    return str(value) + (scalar if scalar in ("u64", "u8") else "")


class Suite:
    def __init__(self, directory, compiler, keep_going=False, fixture="", plan_only=False):
        self.directory, self.compiler = directory, compiler
        self.keep_going, self.fixture, self.plan_only = keep_going, fixture, plan_only
        self.runner = None if plan_only else NativeRunner(directory, compiler, 5)
        self.library_inputs = {} if plan_only else {
            path: path.read_bytes() for path in (ROOT / "library").rglob("*.au")}
        self.count = self.traps = self.rejections = self.negative_fixtures = 0
        self.attempts = self.selected_fixtures = 0
        self.failures, self.names = [], set()

    def check(
        self,
        name,
        source,
        expected=42,
        error=None,
        modules=None,
        existing_output=None,
        _selected=False,
        equivalent_source=None,
    ):
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
            print("PLAN method values", name, flush=True)
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
            compiled = subprocess.run(command, capture_output=True, timeout=10,
                preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))
            (directory / "stdout.bin").write_bytes(compiled.stdout)
            (directory / "stderr.bin").write_bytes(compiled.stderr)
            for path, before in inputs.items():
                require(path.read_bytes() == before, name + ": input changed: " + str(path))
            if error is not None:
                require(compiled.returncode == 1,
                        f"{name}: expected compiler exit 1, got {compiled.returncode}: {compiled.stderr!r}")
                require(bool(compiled.stderr), name + ": missing rejection diagnostic")
                if existing_output is None:
                    require(not output.exists(), name + ": artifact created on rejection")
                else:
                    require(output.read_bytes() == existing_output,
                            name + ": previous output changed on rejection")
                if error is not True:
                    fragments = (error,) if isinstance(error, str) else error
                    require(any(x.lower().encode() in compiled.stderr.lower() for x in fragments),
                            name + ": unexpected diagnostic: " + repr(compiled.stderr))
                self.rejections += 1
            else:
                require(compiled.returncode == 0,
                        f"{name}: compiler exit {compiled.returncode}: {compiled.stderr!r}")
                if equivalent_source is not None:
                    named_input, named_output = directory / "named.au", directory / "named.s"
                    named_input.write_text(equivalent_source)
                    named_command = [str(self.compiler), str(named_input), "-o", str(named_output)]
                    for root in roots:
                        named_command.extend(["--module-root", str(root)])
                    (directory / "named-command.json").write_text(json.dumps(named_command, indent=2) + "\n")
                    named = subprocess.run(
                        named_command,
                        capture_output=True,
                        timeout=10,
                        preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)),
                    )
                    (directory / "named-stderr.bin").write_bytes(named.stderr)
                    require(named.returncode == 0, name + ": named-local comparison failed: " + repr(named.stderr))
                    require(named_input.read_text() == equivalent_source, name + ": named input changed")
                    for path, before in inputs.items():
                        require(path.read_bytes() == before, name + ": input changed: " + str(path))
                    require(
                        output.read_bytes() == named_output.read_bytes(),
                        name + ": direct return differs from named-local assembly",
                    )
                self.runner.directory = directory
                observed, symbols = self.runner.assemble(output.read_text(), ["test"])
                if isinstance(expected, Trap):
                    validate_trap(observed, expected, symbols, name)
                    self.traps += 1
                else:
                    validate_values(observed, [signed_bits(expected)], [name])
            self.count += 1
            print("PASS method values", name, flush=True)
        except (AssertionError, OSError, subprocess.TimeoutExpired) as failure:
            details = f"{name}: {failure}\nPreserved reproduction: {directory}"
            (directory / "failure.txt").write_text(details + "\n")
            self.failures.append(details)
            print("FAIL method values", details, flush=True)
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
            self.check(name + ": " + suffix, source, error=error, modules=modules,
                       existing_output=previous, _selected=True)
        if self.rejections == before + 2:
            self.negative_fixtures += 1


def native_cases(suite):
    for receiver_const in (False, True):
        for argument_const in (False, True):
            for result_const in (False, True):
                suite.check(f"readonly copy receiver={receiver_const} argument={argument_const} result={result_const}", p(
                    f"{'const ' if receiver_const else ''}Counter receiver=Counter(0);"
                    f"{'const ' if argument_const else ''}Counter source=Counter(42);"
                    f"{'const ' if result_const else ''}Counter copied=receiver.copy(source);"
                    "if(receiver.inspect(source)!=42){return 1;}"
                    + ("if(copied.add(1)!=43){return 2;}" if not result_const else "")
                    + "return source.get();", COUNTER))
    suite.check("parenthesized named-local argument retains independent copy semantics", p(
        "Counter source=Counter(42);Counter receiver=Counter(0);Counter result=receiver.copy((source));"
        "source.set(7);return result.get();", COUNTER))
    suite.check("mutable receiver and returned parameter are independent", p(
        "Counter receiver=Counter(20);Counter source=Counter(22);"
        "Counter old=receiver.replace(source);source.set(99);old.add(1);"
        "if(source.get()!=99){return 1;}return old.get()+receiver.get()-1;", COUNTER))
    suite.check("mutable self argument copied before receiver acquisition", p(
        "Counter receiver=Counter(42);Counter old=receiver.replace(receiver);"
        "receiver.set(7);return old.get();", COUNTER))
    suite.check("readonly self argument and class result are distinct", p(
        "Counter receiver=Counter(42);Counter saved=receiver.copy(receiver);"
        "receiver.set(7);return saved.get();", COUNTER))
    six = ("class Six{ i64 value; public:Six(i64 n):value(n){}"
           "auto mix(Counter a,i64 n,Counter b,Status state,u64 big,u8 byte)->Counter{"
           "if(n!=7){const Counter failed=Counter(1);return failed;}"
           "if(state!=Status::ready){const Counter failed=Counter(2);return failed;}"
           "if(big!=18446744073709551615u64){const Counter failed=Counter(3);return failed;}"
           "if(byte!=255u8){const Counter failed=Counter(4);return failed;}"
           "value=value+1;const Counter answer=Counter(a.get()+b.get()+value);return answer;}"
           "auto check(bool yes,Counter a,u8 byte,Counter b,u64 big,Status state)const->bool{"
           "if(!yes){return false;}if(byte!=255u8){return false;}"
           "if(big!=18446744073709551615u64){return false;}"
           "if(state!=Status::ready){return false;}return a.get()+b.get()==41;} };" )
    suite.check("six mixed scalar enum class parameters with class result", p(
        "Six receiver=Six(0);Counter a=Counter(20);Counter b=Counter(21);"
        "Counter result=receiver.mix(a,7,b,Status::ready,18446744073709551615u64,255u8);"
        "if(!receiver.check(true,a,255u8,b,18446744073709551615u64,Status::ready)){return 9;}"
        "return result.get();", ENUMS+COUNTER+six))
    order = COUNTER.replace("};", "auto order(Counter before,i64 first,Counter between,i64 second,Counter after,bool yes)->i64{"
        "if(before.get()!=1){return 1;}if(first!=2){return 2;}if(between.get()!=2){return 3;}"
        "if(second!=3){return 4;}if(after.get()!=3){return 5;}if(!yes){return 6;}"
        "if(value!=3){return 7;}value=99;"
        "if(before.get()!=1){return 8;}if(after.get()!=3){return 9;}return 42;}};")
    suite.check("class snapshots scalar effects and receiver acquire left to right", p(
        "Counter source=Counter(1);return source.order(source,source.add(1),source,source.add(1),source,true);", order))
    suite.check("scalar side effect before first class argument is visible", p(
        "Counter source=Counter(1);Reader reader=Reader();return reader.inspect(source.add(1),source);",
        COUNTER+"class Reader{public:Reader(){}auto inspect(i64 n,Counter copy)const->i64{"
        "if(n!=2){return 1;}if(copy.get()!=2){return 2;}return 42;}};"))
    suite.check("repeated class snapshots independently copied into mutable locals", p(
        "Counter source=Counter(20);Reader reader=Reader();return reader.inspect(source,source);",
        COUNTER+"class Reader{public:Reader(){}auto inspect(Counter a,Counter b)const->i64{"
        "Counter changed=a;changed.add(2);return changed.get()+b.get();}};"))
    suite.check("inner result binding reads outer same-name argument and receiver", p(
        "Counter value=Counter(42);if(true){Counter value=value.copy(value);"
        "value.set(0);}return value.get();", COUNTER))
    suite.check("class parameter shadows receiver scalar field", p(
        "Counter source=Counter(42);Shadow receiver=Shadow(99);return receiver.inspect(source);",
        COUNTER+"class Shadow{i64 source;public:Shadow(i64 n):source(n){}"
        "auto inspect(Counter source)const->i64{return source.get();}};"))
    suite.check("local class shadows readonly method parameter in inner scope", p(
        "Counter source=Counter(42);Reader receiver=Reader();return receiver.inspect(source);",
        COUNTER+"class Reader{public:Reader(){}auto inspect(Counter source)const->i64{"
        "if(true){Counter source=source;source.add(1);}return source.get();}};"))
    sibling = ("class Sibling{i64 value;auto take(Counter source,i64 extra)const->Counter{"
               "const Counter result=Counter(source.get()+extra+value);return result;}"
               "auto advance(Counter source)->Counter{value=value+1;const Counter result=take(source,1);return result;}"
               "public:Sibling(i64 n):value(n){}auto get(Counter source)const->Counter{"
               "const Counter result=take(source,2);return result;}"
               "auto change(Counter source)->Counter{const Counter result=advance(source);return result;}};")
    for method in ("get", "change"):
        suite.check("private sibling copied argument and result " + method, p(
            f"Counter source=Counter(20);Sibling receiver=Sibling(20);Counter result=receiver.{method}(source);"
            "source.set(99);return result.get();", COUNTER+sibling))
    suite.check("method parameter forwarded through ordinary function and receiver restored", p(
        "Counter source=Counter(20);Forward receiver=Forward(22);Counter result=receiver.take(source);return result.get();",
        COUNTER+"class Forward{i64 value;public:Forward(i64 n):value(n){}"
        "auto take(Counter source)const->Counter{Counter result=identity(source);result.add(value);return result;}};",
        "auto identity(Counter source)->Counter{return source;}"))
    suite.check("class-result destination independent across loop lifetimes", p(
        "Counter source=Counter(20);Counter receiver=Counter(0);i64 total=0;i64 i=0;"
        "while(i<2){Counter result=receiver.copy(source);total=total+result.add(1);i=i+1;}return total;", COUNTER))
    for scalar, value in (("i64",-(1<<63)),("u64",(1<<64)-1),("u8",255),("bool",True)):
        definition=(f"class Value{{{scalar} item;public:Value({scalar} n):item(n){{}}"
                    f"auto get()const->{scalar}{{return item;}}auto copy(Value source)const->Value{{return source;}}}};")
        suite.check("full-width copied method parameter " + scalar, p(
            f"Value value=Value({lit(scalar,value)});const Value result=value.copy(value);return result.get();",
            definition, result=scalar), expected=int(value))
    suite.check("nominal enum result with copied class parameter", p(
        "Tagged source=Tagged(Status::ready);Tagged receiver=Tagged(Status::failed);"
        "if(receiver.status(source)!=Status::ready){return 1;}return 42;", ENUMS+
        "class Tagged{Status value;public:Tagged(Status n):value(n){}"
        "auto status(Tagged source)const->Status{return source.value;}};"))
    suite.check("empty parameter and result preserve nominal completeness", p(
        "Empty source=Empty();Receiver receiver=Receiver();Empty result=receiver.copy(source,source);return result.answer();",
        EMPTY+"class Receiver{public:Receiver(){}auto copy(Empty a,Empty b)const->Empty{return b;}};"))
    suite.check("packed nested enum empty and private array payload all copy", p(
        "std::array<u8,3> bytes=std::array<u8,3>();bytes.set(0,255u8);bytes.set(2,40u8);"
        "Empty empty=Empty();Packet source=Packet(7u8,bytes,Status::ready,empty,2u8);"
        "Receiver receiver=Receiver();Packet result=receiver.copy(source);bytes.set(2,0u8);"
        "std::array<u8,3> changed=result.data;changed.set(2,1u8);"
        "const std::array<u8,3> saved=result.data;"
        "if(saved.at(0)!=255u8){return 1;}if(result.state!=Status::ready){return 2;}"
        "if(result.head!=7u8){return 3;}const Empty zero=result.zero;if(zero.answer()!=42){return 4;}"
        "return i64(saved.at(2))+i64(result.tail);", ENUMS+EMPTY+
        "class Packet{public:u8 head;std::array<u8,3> data;Status state;Empty zero;u8 tail;"
        "Packet(u8 h,std::array<u8,3> b,Status s,Empty e,u8 t):head(h),data(b),state(s),zero(e),tail(t){} };"
        "class Receiver{public:Receiver(){}auto copy(Packet value)const->Packet{return value;}};",
        imports="import std.array;"))
    suite.check("class template injected self supports ordinary copied parameter", p(
        "Box<i64> source=Box<i64>(20);Box<i64> receiver=Box<i64>(22);"
        "Box<i64> old=receiver.exchange(source);source.set(99);return old.get()+receiver.get();",
        "template<Scalar T>class Box{T value;public:Box(T n):value(n){}"
        "auto get()const->T{return value;}auto set(T n)->T{value=n;return value;}"
        "auto exchange(Box source)->Box{const Box old=Box(value);value=source.get();return old;}};"))
    suite.check("qualified wrapper self means exact active instance and bare array stays storage", p(
        "std::array<u8,1> one=std::array<u8,1>();std::array<u64,3> three=std::array<u64,3>();"
        "const std::array<u8,1> saved1=one.copy(one);const std::array<u64,3> saved3=three.copy(three);"
        "static_assert(size_of(std::array<u8,1>)==1);static_assert(size_of(std::array<u64,3>)==24);"
        "if(saved1.get(0)!=0u8){return 1;}if(saved3.get(2)!=0u64){return 2;}return 42;",
        "namespace std{template<Scalar T,i64 N>class array{array<T,N> elements;public:array():elements{}{}"
        "auto get(i64 index)const->T{return elements[index];}"
        "auto copy(std::array source)const->std::array{const std::array result=source;return result;}};}"))
    suite.check("Value substitution method argument and result use exact nested type", p(
        "Counter source=Counter(42);Box<Counter> receiver=Box<Counter>(source);"
        "Counter result=receiver.copy(source);source.set(99);return result.get();", COUNTER+
        "template<Value T>class Box{T item;public:Box(T n):item(n){}"
        "auto copy(T source)const->T{return source;}};"))
    suite.check("nested class template argument copied through ordinary method", p(
        "std::array<u8,3> bytes=std::array<u8,3>();bytes.set(2,40u8);"
        "std::pair<std::array<u8,3>,u8> source=std::pair<std::array<u8,3>,u8>(bytes,2u8);"
        "Receiver receiver=Receiver();const std::pair<std::array<u8,3>,u8> result=receiver.copy(source);"
        "const std::array<u8,3> saved=result.first;return i64(saved.at(2))+i64(result.second);",
        "class Receiver{public:Receiver(){}auto copy(std::pair<std::array<u8,3>,u8> value)const"
        "->std::pair<std::array<u8,3>,u8>{return value;}};",
        imports="import std.array;import std.utility;"))

    direct = p(
        "const Counter source=Counter(42);Counter result=forward(source);result.set(7);return source.get();",
        COUNTER,
        "auto forward(Counter source)->Counter{const Counter receiver=Counter(0);return receiver.copy(source);}",
    )
    suite.check(
        "direct method result matches named-local assembly",
        direct,
        equivalent_source=direct.replace(
            "return receiver.copy(source);", "const Counter result=receiver.copy(source);return result;"
        ),
    )
    sibling_direct = sibling.replace("const Counter result=take(source,1);return result;", "return take(source,1);")
    sibling_direct = sibling_direct.replace(
        "const Counter result=take(source,2);return result;", "return take(source,2);"
    )
    sibling_direct = sibling_direct.replace(
        "const Counter result=advance(source);return result;", "return advance(source);"
    )
    for method in ("get", "change"):
        source = p(
            f"Counter source=Counter(20);Sibling receiver=Sibling(20);"
            f"Counter result=receiver.{method}(source);source.set(99);return result.get();",
            COUNTER + sibling_direct,
        )
        suite.check(
            "direct private implicit sibling result " + method,
            source,
            equivalent_source=source.replace(sibling_direct, sibling),
        )
    suite.check(
        "direct mutable method keeps self-argument result independent",
        p(
            "Counter receiver=Counter(42);Counter old=receiver.relay(receiver);receiver.set(7);return old.get();",
            COUNTER.replace("};", "auto relay(Counter source)->Counter{return replace(source);}};"),
        ),
    )
    suite.check(
        "direct method snapshots arguments before acquiring mutable receiver",
        p(
            "Counter result=forward();return result.get();",
            COUNTER.replace(
                "};",
                "auto merge(Counter before,i64 ignored,Counter after)->Counter{"
                "value=99;return Counter(before.get()+after.get());}};",
            ),
            "auto forward()->Counter{Counter receiver=Counter(20);"
            "return receiver.merge(receiver,receiver.add(2),receiver);}",
        ),
    )
    suite.check(
        "direct method branch results have independent loop lifetimes",
        p(
            "Counter receiver=Counter(0);Counter a=Counter(20);Counter b=Counter(22);i64 n=0;i64 total=0;"
            "while(n<2){Counter result=receiver.select(a,b,n==0);total=total+result.get();n=n+1;}return total;",
            COUNTER.replace(
                "};",
                "auto select(Counter a,Counter b,bool first)const->Counter{"
                "if(first){return copy(a);}return copy(b);}};",
            ),
        ),
    )
    loan = p(
        "Receiver receiver=Receiver();Counter result=receiver.capture_value();return result.get();",
        COUNTER + "class Receiver{public:Receiver(){}auto take(Counter value)const->Counter{return value;}"
        "auto capture_value()const->Counter{builtin::array<u8,1> bytes={42u8};"
        "const builtin::span<const u8> view=borrow_bytes(bytes);Counter source=Counter(i64(view.at(0)));"
        "return take(source);}};",
    )
    suite.check(
        "direct method return closes live array and span",
        loan,
        equivalent_source=loan.replace("return take(source);", "const Counter result=take(source);return result;"),
    )
    suite.check(
        "direct empty method result retains initialization",
        p(
            "Empty source=Empty();Empty result=source.forward(source);return result.answer();",
            EMPTY.replace(
                "};",
                "auto copy(Empty source)const->Empty{return source;}"
                "auto forward(Empty source)const->Empty{return copy(source);}};",
            ),
        ),
    )


def model_cases(suite, seed, steps):
    rng = random.Random(seed)
    edges = {"i64": [-(1<<63), (1<<63)-1, -1, 0, 1, 42],
             "u64": [0, 1, 42, 1<<63, (1<<64)-1],
             "u8": [0, 1, 42, 127, 128, 255], "bool": [False, True]}
    for scalar in SCALARS:
        for capacity in (1, 2, 3, 16, 63, 64):
            concrete = f"std::array<{scalar},{capacity}>"
            arrays = {name: [rng.choice(edges[scalar]) for _ in range(capacity)] for name in ("left", "right")}
            body = [f"{concrete} left={concrete}();{concrete} right={concrete}();"]
            for name, values in arrays.items():
                body += [f"{name}.set({i},{lit(scalar,v)});" for i,v in enumerate(values)]
            for step in range(steps):
                target = "left" if step % 2 == 0 else "right"
                source = target if step % 3 == 0 else ("right" if target == "left" else "left")
                old = arrays[target].copy()
                arrays[target] = arrays[source].copy()
                # Every third operation is self-exchange. Independent result mutations
                # and mutations of the replacement after the call test all aliases.
                body.append("if(true){")
                body.append(f"{concrete} saved={target}.exchange({source});")
                for i,v in enumerate(old):
                    body.append(f"if(saved.at({i})!={lit(scalar,v)}){{return 1;}}")
                index = rng.randrange(capacity)
                value = rng.choice([v for v in edges[scalar] if v != arrays[source][index]])
                body.append(f"{source}.set({index},{lit(scalar,value)});")
                arrays[source][index] = value
                changed = rng.choice([v for v in edges[scalar] if v != old[0]])
                body.append(f"saved.set(0,{lit(scalar,changed)});")
                old[0] = changed
                for name, values in arrays.items():
                    for i,v in enumerate(values):
                        body.append(f"if({name}.at({i})!={lit(scalar,v)}){{return 2;}}")
                for i,v in enumerate(old):
                    body.append(f"if(saved.at({i})!={lit(scalar,v)}){{return 3;}}")
                body.append("}")
            body.append("return 42;")
            suite.check(f"seeded exchange snapshot model {scalar} capacity {capacity}", p(
                "".join(body), imports="import std.array;"))
    for scalar in SCALARS:
        value = edges[scalar][-1]
        concrete = f"std::array<{scalar},64>"
        suite.check("array exchange accepts readonly replacement " + scalar, p(
            f"{concrete} seed={concrete}();seed.set(63,{lit(scalar,value)});"
            f"const {concrete} replacement=seed;{concrete} receiver={concrete}();"
            f"const {concrete} old=receiver.exchange(replacement);"
            f"if(receiver.at(63)!={lit(scalar,value)}){{return 1;}}"
            f"if(old.at(63)!={lit(scalar,False if scalar=='bool' else 0)}){{return 2;}}"
            "return 42;", imports="import std.array;"))


def boundary_cases(suite):
    for leaves in (1, 63, 64, 65):
        fields="".join(f"i64 f{i};" for i in range(leaves))
        initializers=",".join(f".f{i}={7 if i==leaves-1 else i}" for i in range(leaves))
        wide="class Wide{public:"+fields+"};"
        receiver=("class Receiver{public:Receiver(){}auto sum(Wide a,Wide b,Wide c,Wide d,Wide e,Wide f)const->i64{"
                  f"return a.f{leaves-1}+b.f{leaves-1}+c.f{leaves-1}+d.f{leaves-1}+e.f{leaves-1}+f.f{leaves-1};}}}};")
        source=p("Wide source=Wide{"+initializers+"};Receiver receiver=Receiver();"
                 "return receiver.sum(source,source,source,source,source,source);", wide+receiver)
        if leaves<=64:
            suite.check(f"six copied arguments each with {leaves} scalar leaves",source)
        else:
            suite.reject("method parameter rejects 65 scalar leaves",source)
    suite.check("six maximum-width class args plus receiver and class result", p(
        "std::array<u64,64> source=std::array<u64,64>();source.set(63,18446744073709551615u64);"
        "Receiver receiver=Receiver(42);const std::array<u64,64> result=receiver.pick(source,source,source,source,source,source);"
        "if(result.at(63)!=18446744073709551615u64){return 1;}return receiver.get();",
        "class Receiver{i64 value;public:Receiver(i64 n):value(n){}auto get()const->i64{return value;}"
        "auto pick(std::array<u64,64> a,std::array<u64,64> b,std::array<u64,64> c,"
        "std::array<u64,64> d,std::array<u64,64> e,std::array<u64,64> f)const->std::array<u64,64>{return f;}};",
        imports="import std.array;"))
    suite.reject("seventh explicit class method parameter exceeds limit",p("return 42;",COUNTER+
        "class Receiver{public:Receiver(){}auto bad(Counter a,Counter b,Counter c,Counter d,Counter e,Counter f,Counter g)"
        "const->i64{return 42;}};"), error="six")
    for depth in (4,5):
        definitions=COUNTER
        body="Counter value0=Counter(42);"
        current="Counter"
        for level in range(1,depth):
            name=f"Wrap{level}"
            definitions+=f"class {name}{{public:{current} item;{name}({current} x):item(x){{}}}};"
            body+=f"{name} value{level}={name}(value{level-1});"
            current=name
        definitions+=f"class Receiver{{public:Receiver(){{}}auto copy({current} value)const->{current}{{return value;}}}};"
        body+=f"Receiver receiver=Receiver();{current} result=receiver.copy(value{depth-1});return 42;"
        if depth==4:
            suite.check("copied method parameter containment depth four",p(body,definitions))
        else:
            suite.reject("copied method parameter containment depth five rejected",p(body,definitions))


def rejection_cases(suite):
    prefix="Counter source=Counter(42);Counter receiver=Counter(0);"
    for label, body, helpers in (
        ("constructor temporary class argument", "return receiver.inspect(Counter(42));", ""),
        ("function result temporary class argument", "return receiver.inspect(make());", "auto make()->Counter{Counter x=Counter(42);return x;}"),
        ("method result temporary class argument", "return receiver.inspect(receiver.copy(source));", ""),
        ("scalar literal cannot be copied class argument", "return receiver.inspect(42);", ""),
        ("scalar local cannot be copied class argument", "i64 wrong=42;return receiver.inspect(wrong);", ""),
        ("class argument cannot enter scalar slot", "return receiver.add(source);", ""),
        ("missing class argument", "return receiver.inspect();", ""),
        ("extra class argument", "return receiver.inspect(source,source);", ""),
        ("result discarded", "receiver.copy(source);return 42;", ""),
        ("result reassigned into existing class", "source=receiver.copy(source);return 42;", ""),
        ("result cannot initialize scalar", "i64 result=receiver.copy(source);return result;", ""),
        ("result cannot initialize inferred binding", "auto result=receiver.copy(source);return 42;", ""),
        ("temporary receiver remains unsupported", "return Counter(0).inspect(source);", ""),
        ("class argument outside lexical lifetime", "if(true){Counter gone=Counter(42);}return receiver.inspect(gone);", ""),
        ("new result binding not visible in own argument", "Counter result=receiver.copy(result);return 42;", ""),
        ("method extraction remains unsupported", "auto method=receiver.read;return 42;", ""),
    ):
        suite.reject(label,p(prefix+body,COUNTER,helpers))
    for label, definition, helper, diagnostic in (
        (
            "exact nominal result",
            COUNTER + "class Other{public:i64 value;};",
            "auto forward(Counter source)->Other{return source.copy(source);}",
            "expected Other",
        ),
        (
            "scalar result cannot fill class",
            COUNTER,
            "auto forward(Counter source)->Counter{return source.get();}",
            "expected Counter",
        ),
        (
            "readonly receiver forbids mutable method",
            COUNTER,
            "auto forward(Counter source)->Counter{return source.replace(source);}",
            "mutable receiver",
        ),
        (
            "const implicit sibling forbids mutable method",
            COUNTER.replace("};", "auto forward(Counter source)const->Counter{return replace(source);}};"),
            "",
            "mutable",
        ),
        (
            "private method stays inaccessible",
            "class Receiver{auto copy(Counter source)const->Counter{return source;}public:Receiver(){}};" + COUNTER,
            "auto forward(Counter source)->Counter{Receiver receiver=Receiver();return receiver.copy(source);}",
            "private",
        ),
        (
            "temporary method receiver remains unsupported",
            COUNTER,
            "auto forward(Counter source)->Counter{return Counter(0).copy(source);}",
            "method receiver",
        ),
        (
            "nested class-result argument remains unsupported",
            COUNTER,
            "auto forward(Counter source)->Counter{return source.copy(source.copy(source));}",
            "complete local name",
        ),
        (
            "field receiver remains unsupported",
            COUNTER + "class Holder{public:Counter item;Holder(Counter source):item(source){}};",
            "auto forward(Holder holder,Counter source)->Counter{return holder.item.copy(source);}",
            "complete receiver",
        ),
        (
            "implicit method cannot override parameter binding",
            COUNTER.replace("};", "auto forward(Counter copy)const->Counter{return copy(copy);}};"),
            "",
            "callable",
        ),
    ):
        suite.reject("direct method " + label, p("return 42;", definition, helper), error=diagnostic)
    suite.reject(
        "direct service operation result dispatch remains rejected",
        p(
            "return 42;",
            helpers="auto forward(builtin::ConsoleSession& session)->builtin::ConsoleSample{return session.next();}",
        ),
        error="ordinary method",
    )
    suite.reject("equal-layout nominal mismatch remains rejected",p(prefix+
        "Other source2=Other{.value=42};return receiver.inspect(source2);",COUNTER+"class Other{public:i64 value;};"))
    suite.reject("wrong nominal class result destination",p(prefix+
        "Other result=receiver.copy(source);return 42;",COUNTER+"class Other{public:i64 value;};"))
    suite.reject("nested field argument requires projected named local",p(prefix+
        "Holder outer=Holder(source);return receiver.inspect(outer.item);",COUNTER+
        "class Holder{public:Counter item;Holder(Counter x):item(x){} };"))
    suite.reject("private field remains inaccessible through copied parameter",p(
        "Counter source=Counter(42);Reader receiver=Reader();return receiver.inspect(source);",COUNTER+
        "class Reader{public:Reader(){}auto inspect(Counter source)const->i64{return source.value;}};"),error="private")
    for label, code in (
        ("mutable method on readonly class parameter","return source.add(1);"),
        ("parameter rebinding","Counter other=Counter(1);source=other;return 42;"),
        ("parameter scalar field write","source.value=42;return 42;"),
        ("parameter array mutation","source.set(0,42u8);return 42;"),
    ):
        concrete="std::array<u8,1>" if "array" in label else "Counter"
        initial="std::array<u8,1>()" if "array" in label else "Counter(42)"
        definitions=COUNTER.replace("i64 value;","public:i64 value;",1)+f"class Receiver{{public:Receiver(){{}}auto take({concrete} source)->i64{{{code}}}}};"
        suite.reject(label,p(f"{concrete} source={initial};Receiver receiver=Receiver();return receiver.take(source);",
                             definitions,imports="import std.array;"))
    suite.reject("mutable receiver method rejects const receiver with copied arg",p(
        "const Counter receiver=Counter(0);Counter source=Counter(42);Counter result=receiver.replace(source);return 42;",COUNTER))
    suite.reject("const sibling cannot forward to mutable sibling",p("return 42;",COUNTER+
        "class Receiver{public:Receiver(){}auto take(Counter x)->Counter{return x;}"
        "auto bad(Counter x)const->Counter{const Counter result=take(x);return result;}};"))
    for type_name in ("own<i64>","ref<i64>","mut<i64>","builtin::array<u8,1>","builtin::span<u8>"):
        suite.reject("unsupported ordinary method parameter " + type_name,p("return 42;",
            f"class Receiver{{public:Receiver(){{}}auto take({type_name} x)const->i64{{return 42;}}}};"))
    suite.reject("copied parameter name shadows sibling method callable",p("return 42;",COUNTER+
        "class Receiver{auto select(Counter source)const->Counter{return source;}public:Receiver(){}"
        "auto take(Counter select)const->Counter{const Counter result=select(select);return result;}};"))
    suite.reject("scalar parameter in copied signature remains immutable",p("return 42;",COUNTER+
        "class Receiver{public:Receiver(){}auto take(Counter source,i64 n)const->i64{n=42;return n;}};"))
    suite.reject("enum parameter in copied signature remains immutable",p("return 42;",ENUMS+COUNTER+
        "class Receiver{public:Receiver(){}auto take(Counter source,Status state)const->i64{state=Status::failed;return 42;}};"))
    for spelling in ("array", "builtin::array"):
        for position, declaration in (
            ("parameter",f"auto take({spelling} source)const->i64{{return 42;}}"),
            ("result",f"auto take(std::array source)const->{spelling}{{return source;}}"),
            ("local",f"auto take(std::array source)const->i64{{{spelling} value=source;return 42;}}"),
            ("constructor",f"auto take(std::array source)const->i64{{std::array value={spelling}();return 42;}}"),
        ):
            suite.reject(f"reserved {spelling} never injected wrapper self in {position}",p(
                "std::array<u8,1> value=std::array<u8,1>();return 42;",
                "namespace std{template<Scalar T,i64 N>class array{builtin::array<T,N> elements;public:array():elements{}{}"
                +declaration+"};}"))
    suite.reject("qualified wrapper name outside template still requires type arguments",p(
        "std::array value=std::array();return 42;",imports="import std.array;"))
    suite.reject("qualified injected wrapper self rejects another active instance",p(
        "std::array<u8,1> one=std::array<u8,1>();std::array<u8,2> two=std::array<u8,2>();"
        "std::array<u8,1> result=one.copy(two);return 42;",
        "namespace std{template<Scalar T,i64 N>class array{builtin::array<T,N> elements;public:array():elements{}{}"
        "auto copy(std::array source)const->std::array{return source;}};}"))
    suite.reject("generic methods remain unsupported",p("return 42;",
        "class Receiver{public:Receiver(){}template<Value T>auto copy(T x)const->T{return x;}};"))
    suite.reject("readonly class field reassignment remains rejected",p(
        "Counter source=Counter(42);const Holder value=Holder(source);value.item=source;return 42;",COUNTER+
        "class Holder{public:Counter item;Holder(Counter x):item(x){} };"))
    suite.reject("direct receiver class field return remains unsupported",p("return 42;",COUNTER+
        "class Holder{Counter item;public:Holder(Counter x):item(x){}auto copy(Counter ignored)const->Counter{return item;}};"))
    for label, methods, helpers in (
        ("direct receiver cycle", "auto take(Counter x)const->Counter{return take(x);}", ""),
        (
            "mutual receiver cycle",
            "auto take(Counter x)const->Counter{const Counter result=other(x);return result;}"
            "auto other(Counter x)const->Counter{const Counter result=take(x);return result;}",
            "",
        ),
        (
            "ordinary helper receiver cycle",
            "auto take(Counter x)const->Counter{const Counter result=helper(x);return result;}",
            "auto helper(Counter x)->Counter{Receiver receiver=Receiver();"
            "Counter result=receiver.take(x);return result;}",
        ),
    ):
        suite.reject(label,p("return 42;",COUNTER+"class Receiver{public:Receiver(){}"+methods+"};",helpers),error="cycle")
    suite.reject("self containment still rejected",p("return 42;",
        "class Bad{Bad field;public:Bad(Bad x):field(x){}auto copy(Bad source)const->Bad{return source;}};"))
    suite.reject("enum method argument retains exact nominal type",p(
        "Counter source=Counter(42);Receiver receiver=Receiver();return receiver.take(source,Other::ready);",ENUMS+COUNTER+
        "class Receiver{public:Receiver(){}auto take(Counter x,Status s)const->i64{return x.get();}};"))
    for label, body in (
        ("const receiver","const std::array<u8,3> receiver=std::array<u8,3>();std::array<u8,3> source=std::array<u8,3>();std::array<u8,3> old=receiver.exchange(source);"),
        ("capacity mismatch","std::array<u8,3> receiver=std::array<u8,3>();std::array<u8,2> source=std::array<u8,2>();std::array<u8,3> old=receiver.exchange(source);"),
        ("scalar type mismatch","std::array<u8,3> receiver=std::array<u8,3>();std::array<i64,3> source=std::array<i64,3>();std::array<u8,3> old=receiver.exchange(source);"),
        ("temporary replacement","std::array<u8,3> receiver=std::array<u8,3>();std::array<u8,3> old=receiver.exchange(std::array<u8,3>());"),
        ("private storage stays private","std::array<u8,3> receiver=std::array<u8,3>();std::array<u8,3> old=receiver.exchange(receiver);return old.elements[0];"),
    ):
        suite.reject("array exchange " + label,p(body+"return 42;",imports="import std.array;"))

def module_cases(suite):
    modules={"values":"export module values;export "+COUNTER,
             "receivers":"export module receivers;import values;export class Receiver{public:Receiver(){}"
             "auto copy(Counter value)const->Counter{return value;}auto inspect(Counter value)const->i64{return value.get();}};"}
    suite.check("direct imports preserve private payload through copied method signature",p(
        "Counter source=Counter(42);Receiver receiver=Receiver();Counter result=receiver.copy(source);"
        "source.set(99);return receiver.inspect(result);",imports="import receivers;import values;"),modules=modules)
    suite.reject("transitive method signature type requires direct visible import",p(
        "Counter source=Counter(42);Receiver receiver=Receiver();Counter result=receiver.copy(source);return result.get();",
        imports="import receivers;"),modules=modules)
    private_type="class Hidden{public:i64 value;};"
    for signature in ("auto inspect(Hidden value)const->i64{return value.value;}",
                      "auto copy(Hidden value)const->Hidden{return value;}"):
        suite.reject("exported public method cannot expose private type " + ("result" if "->Hidden" in signature else "parameter"),p(
            "return 42;",imports="import api;"),modules={"api":"export module api;"+private_type+
            "export class Receiver{public:Receiver(){}"+signature+"};"})
    suite.reject("public copied method signature cannot hide private nested template argument",p(
        "return 42;",imports="import api;"),modules={"api":"export module api;import std.utility;"+private_type+
        "export class Receiver{public:Receiver(){}auto take(std::pair<Hidden,u8> source)const->i64{return 42;}};"})
    suite.check("private copied method may use defining-module private type",p(
        "Receiver receiver=Receiver();return receiver.answer();",imports="import api;"),modules={"api":
        "export module api;"+private_type+"export class Receiver{"
        "auto inspect(Hidden value)const->i64{return value.value;}public:Receiver(){}"
        "auto answer()const->i64{Hidden value=Hidden{.value=42};return inspect(value);}};"})
    suite.reject("private copied method inaccessible to importing caller",p(
        "Counter value=Counter(42);Receiver receiver=Receiver();return receiver.inspect(value);",imports="import api;"),modules={"api":
        "export module api;export "+COUNTER+"export class Receiver{auto inspect(Counter value)const->i64{return value.get();}"
        "public:Receiver(){} };"})
    suite.check(
        "namespace private sibling binding cannot be hijacked by caller helper",
        p(
            "api::Value source=api::Value(42);api::Receiver receiver=api::Receiver();"
            "api::Value result=receiver.copy(source);return result.get();",
            helpers="auto internal(api::Value value)->api::Value{const api::Value wrong=api::Value(0);return wrong;}",
            imports="import api;",
        ),
        modules={
            "api": "export module api;namespace api{auto hidden(i64 value)->i64{return value;}"
            "export class Value{i64 value;public:Value(i64 n):value(n){}auto get()const->i64{return value;}};"
            "export class Receiver{auto internal(Value value)const->Value{return value;}public:Receiver(){}"
            "auto copy(Value value)const->Value{return internal(value);}};}"
        },
    )
    same={"left":"export module left;export namespace left{"+COUNTER+"}",
          "right":"export module right;export namespace right{"+COUNTER+"}"}
    suite.reject("same layout same basename across modules remains nominal",p(
        "left::Counter receiver=left::Counter(0);right::Counter source=right::Counter(42);return receiver.inspect(source);",
        imports="import left;import right;"),modules=same)
    suite.check("imported class-template injected self parameter and result",p(
        "api::Box<i64> source=api::Box<i64>(42);api::Box<i64> receiver=api::Box<i64>(0);"
        "api::Box<i64> result=receiver.copy(source);return result.get();",imports="import api;"),modules={"api":
        "export module api;export namespace api{template<Scalar T>class Box{T value;public:Box(T n):value(n){}"
        "auto get()const->T{return value;}auto copy(Box source)const->Box{return source;}};}"})
    suite.check("module class result and caller mutable copies preserve privacy",p(
        "api::Secret source=api::make();api::Receiver receiver=api::Receiver();"
        "api::Secret result=receiver.copy(source);return result.get();",imports="import api;"),modules={"api":
        "export module api;export namespace api{class Secret{i64 value;public:Secret(i64 n):value(n){}"
        "auto get()const->i64{return value;}auto copy(Secret value)const->Secret{return value;}};"
        "auto make()->Secret{Secret value=Secret(42);return value;}"
        "class Receiver{public:Receiver(){}auto copy(Secret value)const->Secret{return value;}};}"})


def trap_cases(suite):
    for scalar in SCALARS:
        concrete=f"std::array<{scalar},3>"
        for index in (-1,3):
            suite.check(f"copied method parameter exact bounds trap {scalar}/{index}",p(
                f"{concrete} source={concrete}();Receiver receiver=Receiver();return receiver.inspect(source,{index});",
                f"class Receiver{{public:Receiver(){{}}auto inspect({concrete} source,i64 index)const->{scalar}{{return source.at(index);}}}};",
                imports="import std.array;",result=scalar),expected=Trap.BOUNDS)
    suite.check("class snapshot then scalar argument overflow precedes callee trap",p(
        "Counter source=Counter(9223372036854775807);Receiver receiver=Receiver();"
        "return receiver.inspect(source,source.add(1));",COUNTER+
        "class Receiver{public:Receiver(){}auto inspect(Counter value,i64 ignored)const->i64{return 1/0;}};"),expected=Trap.OVERFLOW)
    suite.check("early scalar bounds trap precedes later scalar overflow",p(
        "Counter source=Counter(9223372036854775807);std::array<i64,1> values=std::array<i64,1>();"
        "Receiver receiver=Receiver();return receiver.inspect(source,values.at(1),source.add(1));",COUNTER+
        "class Receiver{public:Receiver(){}auto inspect(Counter value,i64 first,i64 second)const->i64{return 42;}};",
        imports="import std.array;"),expected=Trap.BOUNDS)
    suite.check("checked arithmetic on mutable copy of readonly method parameter",p(
        "Counter source=Counter(9223372036854775807);Receiver receiver=Receiver();return receiver.inspect(source);",COUNTER+
        "class Receiver{public:Receiver(){}auto inspect(Counter value)const->i64{Counter copy=value;return copy.add(1);}};"),expected=Trap.OVERFLOW)
    suite.check("class-result method trap has no successful scalar observation",p(
        "Counter source=Counter(9223372036854775807);Receiver receiver=Receiver();Counter result=receiver.inspect(source);return result.get();",COUNTER+
        "class Receiver{public:Receiver(){}auto inspect(Counter value)const->Counter{Counter copy=value;copy.add(1);return copy;}};"),expected=Trap.OVERFLOW)
    suite.check("exchange result retains exact independent bounds behavior",p(
        "std::array<u8,64> source=std::array<u8,64>();std::array<u8,64> receiver=std::array<u8,64>();"
        "std::array<u8,64> old=receiver.exchange(source);return i64(old.at(64));",imports="import std.array;"),expected=Trap.BOUNDS)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler",type=Path,nargs="?",default=ROOT/"build/aurorac")
    parser.add_argument("--seed",type=int,default=22022)
    parser.add_argument("--steps",type=int,default=12)
    parser.add_argument("--section",choices=("all","native","models","boundaries","rejections","modules","traps"),default="all")
    parser.add_argument("--fixture",default="")
    parser.add_argument("--self-test-only",action="store_true")
    parser.add_argument("--plan-only",action="store_true")
    parser.add_argument("--keep-going",action="store_true")
    args=parser.parse_args()
    require(1<=args.steps<=48,"steps must be between 1 and 48")
    require(not(args.plan_only and args.self_test_only),"plan-only and self-test-only are exclusive")
    compiler=args.compiler.resolve()
    started=time.monotonic()
    if not args.plan_only and not args.self_test_only:
        require(compiler.is_file(),f"compiler unavailable: {compiler}")
        print(f"INFO method values compiler={compiler} sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()}",flush=True)
        for relative in ("tests/compiler/method_values.py","library/std/array.au"):
            print(f"INFO method values {relative} sha256={hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()}",flush=True)
    # Only this run's successful artifacts are deleted. Historical evidence is untouched.
    evidence=Path(tempfile.gettempdir())
    evidence.mkdir(exist_ok=True)
    directory=Path(tempfile.mkdtemp(prefix="method-values-",dir=evidence))
    clean=False
    try:
        suite=Suite(directory,compiler,args.keep_going,args.fixture,args.plan_only)
        if not args.plan_only:
            observer_self_test(suite)
        if args.self_test_only:
            print("PASS method values observer self-tests; no compiler acceptance claimed",flush=True)
            clean=True
            return
        sections={"native":lambda:native_cases(suite),"models":lambda:model_cases(suite,args.seed,args.steps),
                  "boundaries":lambda:boundary_cases(suite),"rejections":lambda:rejection_cases(suite),
                  "modules":lambda:module_cases(suite),"traps":lambda:trap_cases(suite)}
        for name,run in sections.items():
            if args.section in ("all",name):
                before=(suite.count,suite.traps,suite.rejections,suite.selected_fixtures)
                run()
                print(f"INFO method values section={name} fixtures={suite.selected_fixtures-before[3]} executions={suite.count-before[0]} "
                      f"traps={suite.traps-before[1]} rejection-runs={suite.rejections-before[2]}",flush=True)
        require(suite.selected_fixtures>0,"no fixtures selected")
        native=suite.count-suite.traps-suite.rejections
        label="planned" if args.plan_only else "passed"
        print(f"INFO method values: {suite.selected_fixtures} selected fixtures; {suite.count} {label} executions; "
              f"{native} native returns; {suite.traps} exact-site traps; {suite.negative_fixtures} rejection fixtures / "
              f"{suite.rejections} rejection runs; {len(suite.failures)} failed executions; section={args.section}; "
              f"seed={args.seed}; steps={args.steps}; elapsed={time.monotonic()-started:.2f}s",flush=True)
        require(suite.count+len(suite.failures)==suite.attempts,"execution accounting mismatch")
        require(suite.rejections==2*suite.negative_fixtures or bool(suite.failures),"rejection accounting mismatch")
        require(not suite.failures,f"{len(suite.failures)} failed executions; artifacts: {directory}")
        print("PLAN method values complete (not executed)" if args.plan_only else "PASS method values complete",flush=True)
        clean=True
    finally:
        if clean:
            shutil.rmtree(directory)
        else:
            print("INFO method values retained artifacts:",directory,flush=True)


if __name__=="__main__":
    main()
