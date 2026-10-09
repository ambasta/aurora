#!/usr/bin/env python3
"""Focused executable contract for bounded explicit function templates (M021).

Run: python3 -O tests/compiler/function_templates.py build/aurorac
     python3 tests/compiler/function_templates.py --plan-only

Native observations preserve all 64 result bits. Traps require a kernel SIGILL
at the exact named UD2 instruction, using composed_values/integer_oracle's
freestanding observer. Every negative fixture is compiled with both absent and
byte-exact pre-existing output; all source, module, and library inputs must remain
unchanged. require() stays active under -O. Successful cases are deleted; failing
source, modules, command, diagnostics and native artifacts remain under tmp/.
Counts are observed and disjoint (native returns, traps, rejection executions),
with unique negative fixture counts reported separately. This is bounded evidence,
not a language-equivalence or memory-safety proof. No kernel images are produced.
"""
from __future__ import annotations

import argparse
import hashlib
from itertools import product
import json
from pathlib import Path
import random
import re
import resource
import shutil
import subprocess
import tempfile
import time

from composed_values import (Trap, observer_self_test, program, require, signed_bits)
from integer_oracle import NativeRunner, validate_trap, validate_values

ROOT = Path(__file__).resolve().parents[2]
IMPORTS = "import std.utility;import std.array;"
SCALARS = ("i64", "u64", "u8", "bool")
VALUES = {"i64": "-9223372036854775808", "u64": "18446744073709551615u64",
          "u8": "255u8", "bool": "true"}
OTHER = {"i64": "9223372036854775807", "u64": "9223372036854775808u64",
         "u8": "0u8", "bool": "false"}
BITS = {"i64": -(1 << 63), "u64": (1 << 64)-1, "u8": 255, "bool": 1}
COPY = "template<Value T>auto copy(T value)->T{const T result=value;return result;}"
PROBE = "template<Value T>auto probe()->i64{return 42;}"
MAKE = ("template<Value T,Value U>auto make(T x,U y)->std::pair<T,U>{"
        "const std::pair<T,U> result=std::pair<T,U>(x,y);return result;}")
LEAF = ("class Leaf{u8 value;public:Leaf(u8 n):value(n){}"
        "auto get()const->u8{return value;}auto set(u8 n)->u8{value=n;return value;}};")
EMPTY = "class Empty{public:Empty(){}auto answer()const->i64{return 42;}};"
BOX = "template<Value T>class Box{public:T item;Box(T x):item(x){} };"
TAG = "template<Value T>class Tag{public:Tag(){} };"
PRESERVED = b"previous verified assembly\x00\xff\n"


def p(body, definitions="", helpers="", imports=IMPORTS, result="i64"):
    return program(body, definitions, helpers, imports, result)


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

    def check(self, name, source, expected=42, error=None, modules=None,
              existing_output=None, _selected=False):
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
            print("PLAN function templates", name, flush=True)
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
                self.runner.directory = directory
                observed, symbols = self.runner.assemble(output.read_text(), ["test"])
                if isinstance(expected, Trap):
                    validate_trap(observed, expected, symbols, name)
                    self.traps += 1
                else:
                    validate_values(observed, [signed_bits(expected)], [name])
            self.count += 1
            print("PASS function templates", name, flush=True)
        except (AssertionError, OSError, subprocess.TimeoutExpired) as failure:
            details = f"{name}: {failure}\nPreserved reproduction: {directory}"
            (directory / "failure.txt").write_text(details + "\n")
            self.failures.append(details)
            print("FAIL function templates", details, flush=True)
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


def native_cases(suite, seed, steps):
    for first, second in product(SCALARS, repeat=2):
        pair = f"std::pair<{first},{second}>"
        suite.check(f"make_pair all ordered scalar tuples {first}/{second}", p(
            f"{pair} value=std::make_pair<{first},{second}>({VALUES[first]},{VALUES[second]});"
            f"{pair} changed=copy<{pair}>(value);changed.first={OTHER[first]};"
            f"changed.second={OTHER[second]};if(value.first!={VALUES[first]}){{return 1;}}"
            f"if(value.second!={VALUES[second]}){{return 2;}}"
            f"if(changed.first!={OTHER[first]}){{return 3;}}"
            f"if(changed.second!={OTHER[second]}){{return 4;}}return 42;", COPY))
    for scalar in SCALARS:
        suite.check("Scalar identity full-width native result " + scalar, p(
            f"return identity<{scalar}>({VALUES[scalar]});",
            "template<Scalar T>auto identity(T x)->T{return x;}", imports="", result=scalar),
            expected=BITS[scalar])
        suite.check("Value identity full-width native result " + scalar, p(
            f"return copy<{scalar}>({VALUES[scalar]});", COPY, imports="", result=scalar),
            expected=BITS[scalar])
    suite.check("mixed Scalar Value constraints and namespace-qualified explicit call", p(
        "Leaf leaf=Leaf(40u8);std::pair<u8,Leaf> value=tools::pack<u8,Leaf>(2u8,leaf);"
        "const Leaf result=value.second;return i64(value.first)+i64(result.get());", LEAF +
        "namespace tools{template<Scalar T,Value U>auto pack(T x,U y)->std::pair<T,U>{"
        "const std::pair<T,U> result=std::pair<T,U>(x,y);return result;}}"))
    suite.check("explicit calls in ordinary constructor initializer and method", p(
        "Ordinary value=Ordinary(42u8);return i64(value.get());", COPY +
        "class Ordinary{u8 value;public:Ordinary(u8 x):value(copy<u8>(x)){}"
        "auto get()const->u8{return copy<u8>(value);}};", imports=""))
    receiver_shadow = ("template<Scalar T>class Receiver{public:Receiver(){}"
        "auto helper(i64 x)const->i64{return x;}auto get()const->i64{return helper(42);}};")
    namespace_helper = "template<Scalar U>auto helper(U x)->i64{return 999;}"
    suite.check("class-template receiver method shadows local function-template name", p(
        "const Receiver<i64> value=Receiver<i64>();return value.get();",
        namespace_helper + receiver_shadow, imports=""))
    suite.check("class-template receiver method shadows imported function-template name", p(
        "const Receiver<i64> value=Receiver<i64>();return value.get();",
        receiver_shadow, imports="import helpers;"),
        modules={"helpers": "export module helpers;export " + namespace_helper})
    suite.check("same template many scalar specializations have independent substituted ASTs", p(
        "if(copy<i64>(-1)!=-1){return 1;}if(copy<u8>(255u8)!=255u8){return 2;}"
        "if(copy<bool>(true)!=true){return 3;}"
        "if(copy<u64>(18446744073709551615u64)!=18446744073709551615u64){return 4;}"
        "return copy<i64>(42);", COPY, imports=""))
    suite.check("Value closed nominal enum copies and pair fields", p(
        "Status original=Status::ready;Status copied=copy<Status>(original);"
        "std::pair<Status,u8> value=std::make_pair<Status,u8>(copied,42u8);"
        "if(value.first!=Status::ready){return 1;}return i64(value.second);",
        "enum class Status{ready,failed};" + COPY))
    suite.check("Value named private class snapshots and independent returned copy", p(
        "Leaf original=Leaf(20u8);Leaf copied=copy<Leaf>(original);original.set(1u8);"
        "copied.set(22u8);Leaf saved=copy<Leaf>(copied);copied.set(3u8);"
        "return i64(saved.get())+19+i64(original.get());", LEAF + COPY))
    suite.check("Value empty class result retains initialization and const methods", p(
        "Empty source=Empty();Empty result=copy<Empty>(source);"
        "std::pair<Empty,Empty> pair=std::make_pair<Empty,Empty>(source,result);"
        "const Empty projected=pair.second;return projected.answer();", EMPTY + COPY))
    suite.check("bare dependent class-template arguments in result local and constructor", p(
        "Leaf leaf=Leaf(40u8);std::pair<Leaf,u8> value=make<Leaf,u8>(leaf,2u8);"
        "const Leaf result=value.first;return i64(result.get())+i64(value.second);", LEAF + MAKE))
    suite.check("fully concrete nested class argument inside function template", p(
        "std::array<u8,3> bytes=std::array<u8,3>();bytes.set(2,40u8);"
        "std::pair<std::array<u8,3>,u8> inner=std::make_pair<std::array<u8,3>,u8>(bytes,2u8);"
        "std::pair<std::pair<std::array<u8,3>,u8>,u8> outer=wrap<u8>(inner,0u8);"
        "const std::pair<std::array<u8,3>,u8> saved=outer.first;"
        "const std::array<u8,3> copy=saved.first;return i64(copy.at(2))+i64(saved.second);",
        "template<Value T>auto wrap(std::pair<std::array<u8,3>,u8> source,T last)"
        "->std::pair<std::pair<std::array<u8,3>,u8>,T>{"
        "const std::pair<std::pair<std::array<u8,3>,u8>,T> result="
        "std::pair<std::pair<std::array<u8,3>,u8>,T>(source,last);return result;}"))
    suite.check("function argument syntax supports adjacent and spaced nested closers", p(
        "std::array<u8,03> source=std::array<u8,3>();source.set(2,42u8);"
        "const std::array<u8,3> a=copy<std::array<u8,03>>(source);"
        "const std::array<u8,3> b=copy< std::array< u8, 3 > >(a);return i64(b.at(2));", COPY))
    suite.check("left-to-right scalar argument side effects", p(
        "Leaf leaf=Leaf(0u8);std::pair<u8,u8> result=std::make_pair<u8,u8>(leaf.set(20u8),leaf.set(22u8));"
        "return i64(result.first)+i64(result.second);", LEAF))
    suite.check("left-to-right class snapshot precedes later argument mutation", p(
        "Leaf leaf=Leaf(20u8);std::pair<Leaf,u8> result=std::make_pair<Leaf,u8>(leaf,leaf.set(22u8));"
        "const Leaf saved=result.first;return i64(saved.get())+i64(result.second);", LEAF))
    suite.check("left-to-right array snapshot precedes later argument mutation", p(
        "std::array<u8,1> bytes=std::array<u8,1>();bytes.set(0,20u8);"
        "std::pair<std::array<u8,1>,u8> result=std::make_pair<std::array<u8,1>,u8>(bytes,bytes.set(0,22u8));"
        "const std::array<u8,1> saved=result.first;return i64(saved.at(0))+i64(result.second);"))
    suite.check("repeated class source arguments become independent snapshots", p(
        "Leaf source=Leaf(20u8);std::pair<Leaf,Leaf> pair=std::make_pair<Leaf,Leaf>(source,source);"
        "Leaf first=pair.first;Leaf second=pair.second;first.set(22u8);source.set(1u8);"
        "return i64(first.get())+i64(second.get());", LEAF))
    suite.check("function result binding observes outer same-name source", p(
        "Leaf source=Leaf(42u8);{Leaf source=copy<Leaf>(source);if(source.get()!=42u8){return 1;}}"
        "return i64(source.get());", LEAF + COPY))
    suite.check("returned class survives template frame and repeated loop calls", p(
        "Leaf source=Leaf(20u8);i64 i=0;while(i<12){Leaf saved=copy<Leaf>(source);"
        "saved.set(22u8);if(source.get()!=20u8){return 1;}i=i+1;}"
        "Leaf result=copy<Leaf>(source);return i64(result.get())+22;", LEAF + COPY))
    range_class = ("class SourceRange{i64 begin_offset;i64 end_offset;public:"
        "SourceRange(i64 a,i64 b):begin_offset(a),end_offset(b){}"
        "auto begin()const->i64{return begin_offset;}auto end()const->i64{return end_offset;}"
        "auto shift(i64 amount)->i64{begin_offset=begin_offset+amount;end_offset=end_offset+amount;return begin_offset;}};")
    suite.check("bounded token source-range make_pair owns independent sixteen bytes", p(
        "std::array<u8,16> bytes=std::array<u8,16>();bytes.set(0,105u8);bytes.set(1,100u8);"
        "SourceRange source=SourceRange(10,12);"
        "std::pair<std::array<u8,16>,SourceRange> token=std::make_pair<std::array<u8,16>,SourceRange>(bytes,source);"
        "const std::pair<std::array<u8,16>,SourceRange> returned=copy<std::pair<std::array<u8,16>,SourceRange>>(token);"
        "bytes.set(0,0u8);source.shift(100);std::array<u8,16> changed=returned.first;"
        "SourceRange moved=returned.second;changed.set(0,120u8);moved.shift(20);"
        "const std::array<u8,16> saved=token.first;const SourceRange range=token.second;"
        "if(saved.at(0)!=105u8){return 1;}if(saved.at(1)!=100u8){return 2;}"
        "if(range.begin()!=10){return 3;}if(changed.at(0)!=120u8){return 4;}"
        "i64 i=2;while(i<16){if(saved.at(i)!=0u8){return 5;}i=i+1;}"
        "static_assert(size_of(std::pair<std::array<u8,16>,SourceRange>)==32);"
        "static_assert(field_count(std::pair<std::array<u8,16>,SourceRange>)==2);"
        "return moved.begin()+range.end();", range_class + COPY))
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
        body.append(f"source.set(0,{(initial[0]+1)%256}u8);")
        for index, (old, new) in enumerate(zip(initial, model)):
            body.append(f"if(saved.at({index})!={old}u8){{return 1;}}if(changed.at({index})!={new}u8){{return 2;}}")
        suite.check(f"seeded independent generic byte-copy model capacity {capacity}", p("".join(body)+"return 42;", COPY))


def boundary_cases(suite):
    for count in (1, 2):
        signature = COPY if count == 1 else "template<Scalar T,Scalar U>auto choose(T x,U y)->T{return x;}"
        call = "copy<i64>(42)" if count == 1 else "choose<i64,u8>(42,0u8)"
        suite.check(f"function template parameter count {count}", p("return " + call + ";", signature, imports=""))
    for depth in (3, 4, 5):
        concrete = "i64"
        for _ in range(depth):
            concrete = f"Tag<{concrete}>"
        source = p(f"return probe<{concrete}>();", TAG + PROBE, imports="")
        if depth <= 4:
            suite.check(f"function explicit argument list does not consume nominal depth {depth}", source)
        else:
            suite.reject("function argument nominal template depth five rejected", source, error=("depth", "four", "4", "nesting", "nested"))
    for depth in (3, 4):
        concrete = "i64"
        for _ in range(depth):
            concrete = f"Tag<{concrete}>"
        source = p(f"return expanded<{concrete}>();", TAG +
            "template<Value T>auto expanded()->i64{static_assert(size_of(Tag<T>)==8);return 42;}", imports="")
        if depth == 3:
            suite.check("substitution produces exactly four nominal template levels", source)
        else:
            suite.reject("substitution cannot conceal fifth nominal template level", source,
                         error=("depth", "four", "4", "nesting", "nested"))
    for named_leaf in (False, True):
        concrete = "Leaf" if named_leaf else "u8"
        body = "Leaf value0=Leaf(42u8);" if named_leaf else "u8 value0=42u8;"
        for level in range(1, 5):
            concrete = f"Box<{concrete}>"
            body += f"{concrete} value{level}={concrete}(value{level-1});"
        body += f"const {concrete} result=copy<{concrete}>(value4);return 42;"
        source = p(body, LEAF + BOX + COPY, imports="")
        if named_leaf:
            suite.reject("four nominal template levels cannot bypass containment five", source,
                         error=("depth", "four", "4"))
        else:
            suite.check("generic copy at exactly four independent containment levels", source)
    for leaves in (63, 64, 65):
        capacity = leaves-1
        inner, outer = f"std::array<u8,{capacity}>", f"std::pair<std::array<u8,{capacity}>,u8>"
        source = p(f"{inner} bytes={inner}();bytes.set({capacity-1},40u8);"
            f"{outer} value=std::make_pair<{inner},u8>(bytes,2u8);"
            f"const {outer} returned=copy<{outer}>(value);const {inner} saved=returned.first;"
            f"return i64(saved.at({capacity-1}))+i64(returned.second);", COPY)
        suite.check(f"function-template copied byte result flattened leaves {leaves}", source)
    for count in (6, 7):
        parameters = ",".join(f"T a{i}" for i in range(count))
        arguments = ",".join("7" for _ in range(count))
        body = "+".join(f"a{i}" for i in range(count))
        source = p(f"return sum<i64>({arguments});", f"template<Scalar T>auto sum({parameters})->T{{return {body};}}", imports="")
        if count == 6:
            suite.check("instantiated function exactly six ordinary scalar parameters", source)
        else:
            suite.reject("instantiated function seven ordinary parameters", source, error=("six", "parameter"))
    suite.check("instantiated function exactly six independent class parameters", p(
        "Leaf source=Leaf(42u8);Leaf result=last<Leaf>(source,source,source,source,source,source);return i64(result.get());",
        LEAF + "template<Value T>auto last(T a,T b,T c,T d,T e,T f)->T{return f;}", imports=""))
    # i64 parameter (8) + 4096 i64 elements (32768) + 4095 i64 elements
    # (32760) is exactly 65536 bytes. One additional i64 exceeds the frame cap.
    frame_body = ("const array<i64,4096> first={" + ",".join(["0"]*4096) + "};"
                  "const array<i64,4095> second={" + ",".join(["0"]*4095) + "};")
    for extra in (False, True):
        source = p("return frame<i64>(42);", "template<Scalar T>auto frame(T value)->T{" +
            frame_body + ("const i64 overflow=0;" if extra else "") + "return value;}", imports="")
        if extra:
            suite.reject("instantiated function frame 65544 rejects beyond 65536", source, error=("frame", "65536"))
        else:
            suite.check("instantiated function frame exactly 65536 bytes", source)
    for count in (64, 65):
        classes = [TAG.replace("Tag", f"Tag{i}") for i in range(32)]
        functions = [PROBE.replace("probe", f"probe{i}") for i in range(count-32)]
        definitions = "".join(classes + functions)
        body = "return probe0<Tag0<u8>>();"
        source = p(body, definitions, imports="")
        if count == 64:
            suite.check("combined class plus function definitions exactly 64", source)
        else:
            suite.reject("combined class plus function definitions 65", source, error=("64", "template"))
        modules = {"classes": "export module classes;" + "".join("export " + x for x in classes),
                   "functions": "export module functions;" + "".join("export " + x for x in functions)}
        source = p(body, imports="import classes;import functions;")
        if count == 64:
            suite.check("combined 64 definitions counted across module graph", source, modules=modules)
        else:
            suite.reject("combined 65 definitions rejected across module graph", source,
                         modules=modules, error=("64", "template"))
    # Each of 128 distinct std::array types and its probe specialization is one
    # instance: exactly 128 class + 128 function = 256, with no pair requests.
    types = [f"std::array<{scalar},{capacity}>" for scalar in ("u8", "i64") for capacity in range(1, 65)]
    requests = [f"probe<{concrete}>();" for concrete in types]
    suite.check("combined 128 class plus 128 function specializations exactly 256",
        p("".join(requests)+"return 42;", PROBE, imports="import std.array;"))
    suite.reject("combined instance 257 one extra function specialization",
        p("".join(requests)+"probe<u8>();return 42;", PROBE, imports="import std.array;"),
        error=("256", "instantiat", "specializ"))
    suite.reject("combined instance 257 one extra class specialization",
        p("".join(requests)+"static_assert(size_of(Tag<u8>)==8);return 42;", PROBE + TAG, imports="import std.array;"),
        error=("256", "instantiat", "specializ"))
    repeated = "probe< std::array< u8, 03 > >();probe<std::array<u8,3>>();" * 150
    suite.check("canonical repeated requests share exact combined 256 instance budget",
        p("".join(requests)+repeated+"return 42;", PROBE, imports="import std.array;"))
    modules = {"generic": "export module generic;export " + PROBE,
               "left": "export module left;import generic;import std.array;export auto left_value()->i64{" +
                       "".join(requests[:64])+"return 20;}",
               "right": "export module right;import generic;import std.array;export auto right_value()->i64{" +
                        "".join(requests[64:])+"return 22;}"}
    suite.check("combined 256 specializations counted across modules",
        p("return left_value()+right_value();", imports="import left;import right;"), modules=modules)
    too_many = dict(modules)
    too_many["right"] = too_many["right"].replace("return 22;", "probe<bool>();return 22;")
    suite.reject("combined 257 specializations rejected across modules",
        p("return left_value()+right_value();", imports="import left;import right;"), modules=too_many,
        error=("256", "instantiat", "specializ"))


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
        ("function partial specialization", COPY + "template<Value T>auto copy<Box<T>>(Box<T> x)->Box<T>{return x;}", "return 42;"),
        ("overloaded function template", COPY + "template<Value T>auto copy(T a,T b)->T{return a;}", "return 42;"),
        ("ordinary function same name", COPY + "auto copy(i64 x)->i64{return x;}", "return 42;"),
        ("generic method", "class Bad{public:Bad(){}template<Value T>auto f(T x)->T{return x;}};", "return 42;"),
        ("local function template", "", "template<Value T>auto local(T x)->T{return x;}return 42;"),
        ("type constructor T value", "template<Value T>auto construct(T x)->T{const T result=T(x);return result;}", "return 42;"),
        ("dependent scoped member", "template<Value T>auto member()->T{return T::ready;}", "return 42;"),
    ):
        suite.reject("unsupported declaration " + label, p(body, definition, imports=""))
    for call in ("copy(42)", "copy<>(42)", "copy<i64,u8>(42)", "copy<i64,u8,bool>(42)",
                 "copy<i64>()", "copy<i64>(42,1)", "copy<u8>(42)", "copy<Unknown>(42)",
                 "copy<42>(42)", "copy<own<i64>>(42)", "copy<ref<i64>>(42)",
                 "copy<span<u8>>(42)", "copy<array<u8,3>>(42)", "copy<builtin::array<u8,3>>(42)",
                 "copy<std::array<u8,0>>(42)", "copy<std::array<u8,65>>(42)",
                 "copy<i64,>(42)", "copy<i64>>(42)", "copy<i64(42)"):
        suite.reject("explicit function call rejected " + call, p("return " + call + ";", COPY))
    for concrete, setup, argument in (("Leaf", "Leaf value=Leaf(42u8);", "value"),
                                      ("Empty", "Empty value=Empty();", "value"),
                                      ("Status", "Status value=Status::ready;", "value"),
                                      ("std::array<u8,3>", "std::array<u8,3> value=std::array<u8,3>();", "value")):
        suite.reject("Scalar function constraint excludes " + concrete, p(setup + f"identity<{concrete}>({argument});return 42;",
            LEAF + EMPTY + "enum class Status{ready};template<Scalar T>auto identity(T x)->T{return x;}"))
    for label, definition in (
        ("nested dependent result", "template<Value T>auto bad(T x)->Box<Box<T>>{return x;}"),
        ("nested dependent parameter", "template<Value T>auto bad(Box<Box<T>> x)->i64{return 42;}"),
        ("nested dependent local", "template<Value T>auto bad(T x)->i64{Box<Box<T>> result=x;return 42;}"),
        ("nested dependent constructor", "template<Value T>auto bad(T x)->i64{Box<u8> result=Box<Box<T>>(x);return 42;}"),
        ("nested dependent query", "template<Value T>auto bad()->i64{return size_of(Box<Box<T>>);}"),
        ("dependent capacity tree", "template<Value T,Value U>auto bad(T x,U y)->std::pair<std::array<T,16>,U>{return x;}"),
    ):
        suite.reject("unused function structurally rejects " + label, p("return 42;", BOX + definition))
    # Qualified dependent names must be rejected while checking the unused
    # definition, including names hidden inside an otherwise-concrete argument
    # tree. Requested variants also verify the ordinary expansion path rejects.
    qualified_arguments = [
        ("local", "template<Value T>auto bad()->i64{const Tag<T::Hidden> value=Tag<T::Hidden>();return 42;}",
         "return bad<u8>();"),
        ("nested local", "template<Value T>auto bad()->i64{const Tag<Tag<T::Hidden>> value=Tag<Tag<T::Hidden>>();return 42;}",
         "return bad<u8>();"),
        ("constructor expression", "template<Value T>auto bad()->i64{const Tag<u8> value=Tag<T::Hidden>();return 42;}",
         "return bad<u8>();"),
        ("parameter signature", "template<Value T>auto bad(Tag<T::Hidden> source)->i64{return 42;}",
         "Tag<u8> source=Tag<u8>();return bad<u8>(source);"),
        ("result signature", "template<Value T>auto bad()->Tag<T::Hidden>{const Tag<T::Hidden> result=Tag<T::Hidden>();return result;}",
         "const Tag<u8> result=bad<u8>();return 42;"),
    ]
    for query in ("size_of", "type_id", "field_count"):
        qualified_arguments.append(("reflected type " + query,
            f"template<Value T>auto bad()->i64{{return {query}(Tag<T::Hidden>);}}",
            "return bad<u8>();"))
    for position, definition, request in qualified_arguments:
        for used in (False, True):
            suite.reject("dependent qualified template argument " + position +
                         (" requested" if used else " unused"),
                         p(request if used else "return 42;", TAG + definition, imports=""))
    # The name T is a parameter here, even when an unrelated namespace with
    # that spelling would make T::Hidden a resolvable concrete nominal type.
    namespace_collision = ("namespace T{class Hidden{public:Hidden(){} };}" + TAG +
        "template<Value T>auto bad()->i64{const Tag<T::Hidden> result=Tag<T::Hidden>();return 42;}")
    for used in (False, True):
        suite.reject("dependent qualified argument cannot bind same-name namespace " +
                     ("requested" if used else "unused"),
                     p("return bad<i64>();" if used else "return 42;", namespace_collision, imports=""))
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
        suite.reject("unused function template forbids function-template call in " + label,
            p("return 42;", COPY + f"template<Value T>auto bad(T x)->i64{{{body}}}",
              helpers="auto helper(i64 x)->i64{return x;}"))
    for label, body in (
        ("return", "return copy<i64>(42);"),
        ("dead branch", "if(false){copy<i64>(42);}return 42;"),
        ("local initializer", "const i64 result=copy<i64>(42);return result;"),
        ("static assertion", "static_assert(copy<i64>(42)==42);return 42;"),
    ):
        suite.reject("unused class template forbids function-template call in " + label,
            p("return 42;", COPY + "template<Value T>class Bad{public:Bad(){}auto get()const->i64{" + body + "}};"))
    for qualified in (False, True):
        helper = "template<Scalar U>auto helper(U x)->U{return x;}"
        spelling = "api::helper" if qualified else "helper"
        definition = (("namespace api{" + helper + "}" if qualified else helper) +
            "template<Scalar T>class Receiver{public:Receiver(){}"
            "auto helper(i64 x)const->i64{return x;}auto get()const->i64{return " +
            spelling + "<i64>(42);}};")
        for used in (False, True):
            suite.reject("receiver method cannot conceal explicit " +
                ("qualified" if qualified else "unqualified") + " function-template call " +
                ("requested" if used else "unused"),
                p("const Receiver<i64> value=Receiver<i64>();return value.get();" if used else "return 42;",
                  definition, imports=""))
    suite.reject("unused class constructor forbids function-template initializer call", p("return 42;", COPY +
        "template<Value T>class Bad{i64 value;public:Bad():value(copy<i64>(42)){} };"))
    suite.reject("nonempty template constructor body remains unsupported", p("return 42;", COPY +
        "template<Value T>class Bad{public:Bad(){copy<i64>(42);} };"))
    prefix = "Leaf source=Leaf(42u8);"
    suite.check("class return constructor copies complete value", p(
        prefix + "Leaf result=make<Leaf>(source);source.set(0u8);return i64(result.get());",
        LEAF + "template<Value T>auto make(T x)->Leaf{return Leaf(42u8);}"))
    suite.check(
        "direct copied template call preserves exact nominal result",
        p(
            prefix + "Leaf result=wrap(source);source.set(0u8);return i64(result.get());",
            LEAF + COPY + "auto wrap(Leaf x)->Leaf{return copy<Leaf>(x);}",
        ),
    )
    suite.check(
        "direct copied call inside function template",
        p(
            prefix + "Leaf result=forward<Leaf>(source);source.set(0u8);return i64(result.get());",
            LEAF
            + "auto identity(Leaf x)->Leaf{return x;}"
            + "template<Value T>auto forward(T x)->T{return identity(x);}",
        ),
    )
    for label, body, generic in (
        ("mutable parameter field", "return mutate<Leaf>(source);", "template<Value T>auto mutate(T x)->i64{x.value=1u8;return 42;}"),
        ("mutable parameter method", "return mutate<Leaf>(source);", "template<Value T>auto mutate(T x)->i64{x.set(1u8);return 42;}"),
        ("private field access", "return expose<Leaf>(source);", "template<Value T>auto expose(T x)->i64{return i64(x.value);}"),
        ("class argument temporary", "Leaf result=copy<Leaf>(Leaf(42u8));return 42;", COPY),
        ("class nested result argument", "Leaf result=copy<Leaf>(copy<Leaf>(source));return 42;", COPY),
        ("wrong nominal argument", "Empty result=copy<Empty>(source);return 42;", COPY),
        ("wrong nominal result", "Empty result=copy<Leaf>(source);return 42;", COPY),
        ("resource result", "return bad<i64>(42);", "template<Value T>auto bad(T x)->own<i64>{return new i64(x);}"),
    ):
        suite.reject("ordinary value restrictions preserved " + label, p(prefix + body, LEAF + EMPTY + generic))
    suite.reject("class parameter publicly writable field is still readonly", p(
        "Public source=Public(42u8);return mutate<Public>(source);",
        "class Public{public:u8 value;Public(u8 n):value(n){} };"
        "template<Value T>auto mutate(T x)->i64{x.value=0u8;return 42;}", imports=""))
    suite.reject("private method stays private after type substitution", p(prefix + "return expose<Leaf>(source);",
        "class Leaf{u8 value;auto secret()const->u8{return value;}public:Leaf(u8 n):value(n){} };"
        "template<Value T>auto expose(T x)->i64{return i64(x.secret());}", imports=""))
    suite.reject("equal-layout reordered nominal function arguments stay distinct", p(
        "std::pair<i64,u64> source=std::pair<i64,u64>(20,22u64);"
        "std::pair<u64,i64> result=copy<std::pair<u64,i64>>(source);return 42;", COPY))
    suite.reject("function template is not a class reflection type", p("return type_id(copy<i64>);", COPY, imports=""))
    suite.reject("function template cannot become a value pointer", p("const i64 address=copy<i64>;return address;", COPY, imports=""))


def module_cases(suite):
    generic = {"generic": "export module generic;export " + COPY}
    suite.check("exported template accepts caller-private nominal class without member access", p(
        "Leaf source=Leaf(42u8);const Leaf result=copy<Leaf>(source);return i64(result.get());",
        LEAF, imports="import generic;"), modules=generic)
    suite.check("exported template accepts caller-private nominal enum", p(
        "Status source=Status::ready;Status result=copy<Status>(source);if(result==Status::ready){return 42;}return 0;",
        "enum class Status{ready,failed};", imports="import generic;"), modules=generic)
    suite.check("exported template accepts caller-private class inside concrete tree", p(
        "Leaf leaf=Leaf(40u8);std::pair<Leaf,u8> source=std::make_pair<Leaf,u8>(leaf,2u8);"
        "const std::pair<Leaf,u8> result=copy<std::pair<Leaf,u8>>(source);"
        "const Leaf value=result.first;return i64(value.get())+i64(result.second);",
        LEAF, imports="import generic;import std.utility;"), modules=generic)
    helpers = {"generic": "export module generic;auto helper()->i64{return 22;}"
               "export template<Scalar T>auto plus_helper(T x)->i64{return i64(x)+helper();}"}
    suite.check("fixed helper binds defining module rather than caller shadow", p(
        "return plus_helper<u8>(20u8);", helpers="auto helper()->i64{return 999;}", imports="import generic;"), modules=helpers)
    scoped = {"generic": "export module generic;namespace detail{auto helper()->i64{return 22;}"
              "export template<Scalar T>auto plus_helper(T x)->i64{return i64(x)+helper();}}"}
    suite.check("fixed helper binds template defining namespace", p(
        "return detail::plus_helper<u8>(20u8);", helpers="auto helper()->i64{return 999;}", imports="import generic;"), modules=scoped)
    private = {"generic": "export module generic;" + COPY +
               "export auto ordinary()->i64{return copy<i64>(42);}"}
    suite.check("private template is callable by ordinary defining-module helper", p(
        "return ordinary();", imports="import generic;"), modules=private)
    suite.reject("private function template cannot be named outside defining module", p(
        "return copy<i64>(42);", imports="import generic;"), modules=private,
        error=("private", "visible", "unknown", "template"))
    transitive = dict(generic)
    transitive["bridge"] = "export module bridge;import generic;export auto answer()->i64{return copy<i64>(42);}"
    suite.check("ordinary wrapper may use directly imported function template", p(
        "return answer();", imports="import bridge;"), modules=transitive)
    suite.reject("transitive import cannot name function template", p(
        "return copy<i64>(42);", imports="import bridge;"), modules=transitive)
    suite.check("direct import restores function-template visibility", p(
        "return copy<i64>(42);", imports="import bridge;import generic;"), modules=transitive)
    for hidden_kind, hidden, hidden_value in (
        ("class", LEAF.replace("Leaf", "Hidden"), "Hidden(42u8)"),
        ("enum", "enum class Hidden{ready};", "Hidden::ready"),
    ):
        for label, template in (
            ("fixed parameter", "template<Value T>auto bad(Hidden secret,T x)->T{return x;}"),
            ("fixed result", "template<Value T>auto bad(T x)->Hidden{const Hidden result=" + hidden_value + ";return result;}"),
            ("nested fixed parameter", "template<Value T>auto bad(std::pair<Hidden,T> x)->T{const T result=x.second;return result;}"),
            ("nested fixed result", "template<Value T>auto bad(T x)->std::pair<Hidden,T>{const Hidden secret=" + hidden_value + ";const std::pair<Hidden,T> result=std::pair<Hidden,T>(secret,x);return result;}"),
        ):
            suite.reject(f"exported function template cannot launder private {hidden_kind} in {label}",
                p("return 42;", imports="import hidden;"),
                modules={"hidden": "export module hidden;import std.utility;" + hidden + "export " + template},
                error=("private", "visible", "export"))
    suite.reject("exported template signature cannot launder private template declaration", p("return 42;", imports="import hidden;"),
        modules={"hidden": "export module hidden;" + BOX +
            "export template<Value T>auto bad(Box<T> x)->T{const T result=x.item;return result;}"},
        error=("private", "visible", "export"))
    signature_modules = {
        "types": "export module types;export " + LEAF,
        "generic": "export module generic;import types;export template<Value T>auto identity(Leaf source,T extra)->Leaf{return source;}"}
    suite.check("fixed signature type works with explicit direct type import", p(
        "Leaf source=Leaf(42u8);Leaf result=identity<u8>(source,0u8);return i64(result.get());",
        imports="import types;import generic;"), modules=signature_modules)
    suite.reject("fixed signature type cannot be obtained through transitive import", p(
        "Leaf source=Leaf(42u8);Leaf result=identity<u8>(source,0u8);return i64(result.get());",
        imports="import generic;"), modules=signature_modules)
    specialized = {"generic": "export module generic;import std.utility;export " + MAKE,
        "bridge": "export module bridge;import generic;import std.utility;"
                  "export auto pair_id()->i64{std::pair<i64,u8> value=make<i64,u8>(40,2u8);return type_id(std::pair<i64,u8>);}"}
    suite.check("runtime reflection hides transitive specialization declaration", p(
        "if(reflect_size(pair_id())!=0){return 1;}if(reflect_field_count(pair_id())!=0){return 2;}return 42;",
        imports="import bridge;"), modules=specialized)
    suite.check("directly imported specialization metadata matches instantiated class", p(
        "if(reflect_size(pair_id())!=16){return 1;}if(reflect_field_count(pair_id())!=2){return 2;}return 42;",
        imports="import bridge;import std.utility;"), modules=specialized)
    same_names = {}
    for module, value in (("left", 20), ("right", 22)):
        same_names[module] = (f"export module {module};import generic;import std.utility;" + LEAF.replace("Leaf", "Point") +
            f"export auto {module}_value()->i64{{Point source=Point({value}u8);"
            "Point result=copy<Point>(source);return i64(result.get());}"
            f"export auto {module}_id()->i64{{Point source=Point({value}u8);"
            "std::pair<Point,u8> result=std::make_pair<Point,u8>(source,0u8);return type_id(std::pair<Point,u8>);}")
    same_names.update(generic)
    suite.check("same-spelling caller-private class arguments use distinct module identities", p(
        "if(left_id()==right_id()){return 1;}return left_value()+right_value();",
        imports="import left;import right;"), modules=same_names)
    suite.check("runtime reflection stays closed over private function specialization arguments", p(
        "if(reflect_size(left_id())!=0){return 1;}if(reflect_field_count(right_id())!=0){return 2;}return 42;",
        imports="import left;import right;import std.utility;"), modules=same_names)
    suite.reject("imported generic copy confers no private member access", p(
        "Leaf source=Leaf(42u8);Leaf result=copy<Leaf>(source);return i64(result.value);", LEAF,
        imports="import generic;"), modules=generic)
    exposed = {"generic": "export module generic;export template<Value T>auto expose(T x)->u8{return x.value;}"}
    suite.reject("imported template cannot inspect private caller class field", p(
        "Leaf source=Leaf(42u8);return i64(expose<Leaf>(source));", LEAF, imports="import generic;"), modules=exposed)


def trap_cases(suite):
    for scalar, maximum, one in (("i64", "9223372036854775807", "1"),
                                 ("u64", "18446744073709551615u64", "1u64"),
                                 ("u8", "255u8", "1u8")):
        suite.check("generic checked addition exact overflow trap " + scalar, p(
            f"return add<{scalar}>({maximum},{one});",
            "template<Scalar T>auto add(T a,T b)->T{return a+b;}", imports="", result=scalar), expected=Trap.OVERFLOW)
    for scalar, one, zero in (("i64", "1", "0"), ("u64", "1u64", "0u64"), ("u8", "1u8", "0u8")):
        suite.check("generic checked division exact zero trap " + scalar, p(
            f"return divide<{scalar}>({one},{zero});",
            "template<Scalar T>auto divide(T a,T b)->T{return a/b;}", imports="", result=scalar), expected=Trap.ZERO)
    for capacity in (1, 16, 64):
        for index in (-1, capacity, 9223372036854775807):
            for operation in ("at", "set"):
                concrete = f"std::array<u8,{capacity}>"
                arguments = str(index) + (",1u8" if operation == "set" else "")
                suite.check(f"generic array result exact bounds trap {operation}/{capacity}/{index}", p(
                    f"{concrete} source={concrete}();{concrete} result=copy<{concrete}>(source);"
                    f"return i64(result.{operation}({arguments}));", COPY), expected=Trap.BOUNDS)
    for scalar, value, shift, expected in (("u64", "18446744073709551615u64", 1, (1 << 63)-1),
                                          ("u8", "255u8", 1, 127),
                                          ("u64", "9223372036854775808u64", 63, 1),
                                          ("u8", "128u8", 7, 1)):
        suite.check(f"explicit function type closers preserve ordinary right shift {scalar}/{shift}", p(
            f"return copy<{scalar}>({value}) >> {shift};", COPY, imports="", result=scalar), expected=expected)
    suite.check("explicit type argument parsing preserves ordinary comparisons", p(
        "const i64 value=copy<i64>(40);if(value<41){if(value<=40){if(value>39){if(value>=40){return 42;}}}}return 0;",
        COPY, imports=""))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path, nargs="?", default=ROOT / "build/aurorac")
    parser.add_argument("--seed", type=int, default=21021)
    parser.add_argument("--steps", type=int, default=24)
    parser.add_argument("--section", choices=("all", "native", "boundaries", "rejections", "modules", "traps"), default="all")
    parser.add_argument("--fixture", default="", help="case-insensitive fixture-name substring")
    parser.add_argument("--self-test-only", action="store_true")
    parser.add_argument("--plan-only", action="store_true", help="enumerate/count fixtures without compiling anything")
    parser.add_argument("--keep-going", action="store_true")
    args = parser.parse_args()
    require(1 <= args.steps <= 128, "steps must be between 1 and 128")
    require(not (args.self_test_only and args.plan_only), "choose self-test-only or plan-only")
    compiler = args.compiler.resolve()
    started = time.monotonic()
    if not args.self_test_only and not args.plan_only:
        print(f"INFO function templates compiler={compiler} sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()}", flush=True)
        for relative in ("tests/compiler/function_templates.py", "library/std/utility.au", "library/std/array.au"):
            print(f"INFO function templates {relative} sha256={hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()}", flush=True)
    temporary_root = Path(tempfile.gettempdir())
    temporary_root.mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="function-templates-", dir=temporary_root))
    clean = False
    try:
        suite = Suite(directory, compiler, args.keep_going, args.fixture, args.plan_only)
        if not args.plan_only:
            observer_self_test(suite)
        if args.self_test_only:
            print("PASS function templates observer self-tests; no compiler acceptance claimed", flush=True)
            clean = True
            return
        sections = {"native": lambda: native_cases(suite, args.seed, args.steps),
                    "boundaries": lambda: boundary_cases(suite),
                    "rejections": lambda: rejection_cases(suite),
                    "modules": lambda: module_cases(suite),
                    "traps": lambda: trap_cases(suite)}
        for name, run in sections.items():
            if args.section in ("all", name):
                before = (suite.count, suite.traps, suite.rejections, suite.selected_fixtures)
                run()
                print(f"INFO function templates section={name} fixtures={suite.selected_fixtures-before[3]} "
                      f"executions={suite.count-before[0]} traps={suite.traps-before[1]} "
                      f"rejection-runs={suite.rejections-before[2]}", flush=True)
        require(suite.selected_fixtures > 0, "no fixtures selected")
        native = suite.count-suite.traps-suite.rejections
        label = "planned" if args.plan_only else "passed"
        print(f"INFO function templates: {suite.selected_fixtures} selected fixtures; {suite.count} {label} executions; "
              f"{native} native returns; {suite.traps} exact-site traps; {suite.negative_fixtures} rejection fixtures / "
              f"{suite.rejections} rejection runs; {len(suite.failures)} failed executions; "
              f"section={args.section}; seed={args.seed}; steps={args.steps}; elapsed={time.monotonic()-started:.2f}s", flush=True)
        require(suite.count+len(suite.failures) == suite.attempts, "execution accounting mismatch")
        require(suite.rejections == 2*suite.negative_fixtures or bool(suite.failures), "rejection accounting mismatch")
        require(not suite.failures, f"{len(suite.failures)} failed executions; artifacts: {directory}")
        print("PLAN function templates complete (not executed)" if args.plan_only else "PASS function templates complete", flush=True)
        clean = True
    finally:
        if clean:
            shutil.rmtree(directory)
        else:
            print("INFO function templates retained artifacts:", directory, flush=True)


if __name__ == "__main__":
    main()
