#!/usr/bin/env python3
"""Native source acceptance for compact bytes and mixed-width value boundaries.

Python lists and explicit source values determine expected results independently
of compiler layout helpers, IR, and assembly. Every normal observation retains
all eight result bytes. Bounds faults must terminate with kernel-generated
SIGILL at the exact named UD2 instruction; failures and timeouts do not pass.
Each rejection must exit normally with status 1 and preserve both an absent
output and an existing byte-exact output. Checks remain active under python -O.

This is bounded layout/copy evidence, not a safety or performance proof.
Run: python3 tests/compiler/packed_values.py build/aurorac
Harness only: python3 tests/compiler/packed_values.py --self-test-only
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from enum import Enum
import hashlib
from pathlib import Path
import random
import signal
import tempfile
import time

from unsigned_oracle import (Case, NativeRunner, Observation, Rejection, UD2,
                             command, rejected, require, validate_trap,
                             validate_values)


ROOT = Path(__file__).resolve().parents[2]
CAPACITIES = (1, 3, 4, 7, 8, 9, 64)
MAX_U64 = (1 << 64) - 1
EMPTY = "class Empty{public:Empty(){}auto answer()const->i64{return 42;}};"
PAIR = ("template<Value T,Value U>class Pair{public:T first;U second;"
        "Pair(T a,U b):first(a),second(b){} };")
CELL = ("class Cell{u8 value;public:Cell(u8 n):value(n){}"
        "auto get()const->u8{return value;}"
        "auto set(u8 n)->u8{value=n;return value;}"
        "auto snapshot()const->Cell{const Cell result=Cell(value);return result;}};")


class Trap(Enum):
    BOUNDS = ".Laurora_bounds_trap"
    OVERFLOW = ".Laurora_overflow_trap"


def source(body, definitions="", helpers="", result="u64", imports=()):
    return ("module packed;" + "".join(f"import {name};" for name in imports) +
            definitions + helpers + f"auto test()->{result}{{{body}}}")


def byte_storage(name, capacity):
    return (f"class {name}{{builtin::array<u8,{capacity}> data;public:"
            f"{name}():data{{}}{{}}"
            "auto at(i64 index)const->u8{return data[index];}"
            "auto set(i64 index,u8 value)->u8{data[index]=value;return data[index];}"
            f"auto snapshot()const->{name}{{{name} result={name}();i64 i=0;"
            f"while(i<{capacity}){{result.set(i,data[i]);i=i+1;}}return result;}}}};")


class Suite:
    def __init__(self, directory, compiler, timeout, keep_going):
        self.runner = NativeRunner(directory, compiler, timeout)
        self.keep_going = keep_going
        self.count = self.traps = self.rejections = 0
        self.failures = []

    def check(self, name, body, expected=42, definitions="", helpers="",
              result="u64", imports=()):
        program = source(body, definitions, helpers, result, imports)
        runner = self.runner
        path = runner.directory / "input.au"
        output = runner.directory / "compiled.s"
        path.write_text(program)
        output.unlink(missing_ok=True)
        try:
            command([runner.compiler, "--module-root", ROOT / "library", path,
                     "-o", output], timeout=runner.timeout)
            require(path.read_text() == program, name + ": source changed")
            observed, symbols = runner.assemble(output.read_text(), ["test"])
            if isinstance(expected, Trap):
                validate_trap(observed, expected, symbols, name)
                self.traps += 1
            else:
                validate_values(observed, [Case(name, body, expected, result)])
            self.count += 1
            print("PASS packed values", name, flush=True)
        except AssertionError as failure:
            details = f"{name}: {failure}\nReproduction source:\n{program}"
            if not self.keep_going:
                raise AssertionError(details) from failure
            self.failures.append(details)
            print("FAIL packed values", details, flush=True)

    def reject(self, name, body, definitions="", helpers="", imports=()):
        program = source(body, definitions, helpers, imports=imports)
        try:
            self.runner.rejection(Rejection(name, program))
            self.rejections += 1
            print("PASS packed rejection", name, flush=True)
        except AssertionError as failure:
            if not self.keep_going:
                raise
            self.failures.append(str(failure))
            print("FAIL packed rejection", name, str(failure), flush=True)


def self_tests(suite):
    full = Observation(MAX_U64.to_bytes(8, "little"), exit_code=0)
    validate_values(full, [Case("all 64 result bits", "", MAX_U64)])
    rejected(lambda: validate_values(full, [Case("low-byte-only result", "", 255)]),
             "truncated result")
    for observed in (replace(full, output=full.output[:-1]),
                     replace(full, output=full.output + b"x"),
                     replace(full, exit_code=1),
                     replace(full, terminal_signal=signal.SIGILL)):
        rejected(lambda observed=observed: validate_values(
            observed, [Case("invalid native result", "", MAX_U64)]), "invalid result")
    symbols = {Trap.BOUNDS.value: 4096, Trap.OVERFLOW.value: 8192}
    good = Observation(b"", terminal_signal=signal.SIGILL, delivery_signal=signal.SIGILL,
                       pc=4096, instruction=UD2, signal_code=2)
    validate_trap(good, Trap.BOUNDS, symbols, "bounds observer")
    for observed in (replace(good, pc=8192), replace(good, instruction=0x9090),
                     replace(good, signal_code=0), replace(good, output=bytes(8)),
                     replace(good, terminal_signal=signal.SIGSEGV),
                     replace(good, delivery_signal=signal.SIGFPE)):
        rejected(lambda observed=observed: validate_trap(
            observed, Trap.BOUNDS, symbols, "invalid bounds fault"), "invalid fault")
    assembly = (".text\n.globl test\ntest:\n.Laurora_bounds_trap:\nud2\n"
                ".Laurora_overflow_trap:\nud2\n"
                '.section .note.GNU-stack,"",@progbits\n')
    observed, actual_symbols = suite.runner.assemble(assembly, ["test"])
    validate_trap(observed, Trap.BOUNDS, actual_symbols, "native exact bounds UD2")
    rejected(lambda: validate_trap(observed, Trap.OVERFLOW, actual_symbols, "wrong site"),
             "wrong native site")
    print("PASS packed harness: full-width results and exact bounds trap attribution", flush=True)


def array_cases(suite):
    for capacity in CAPACITIES:
        values = [(i * 37 + 131) % 256 for i in range(capacity)]
        initializers = ",".join(f"{v}u8" for v in values)
        body = (f"array<u8,{capacity}> original={{{initializers}}};"
                f"const builtin::array<u8,{capacity}> saved=original;"
                f"array<u8,{capacity}> copy=saved;"
                f"static_assert(size_of(array<u8,{capacity}>)=={capacity});"
                f"static_assert(type_id(array<u8,{capacity}>)==type_id(builtin::array<u8,{capacity}>));"
                f"if(reflect_size(type_id(array<u8,{capacity}>))!={capacity}){{return 1u64;}}"
                f"i64 i=0;while(i<{capacity}){{copy[i]=u8(i);i=i+1;}}")
        for index, value in enumerate(values):
            body += (f"if(original[{index}]!={value}u8){{return 2u64;}}"
                     f"if(saved[{index}]!={value}u8){{return 3u64;}}"
                     f"if(copy[{index}]!={index}u8){{return 4u64;}}")
        suite.check(f"raw byte array {capacity}: exact size and independent adjacent bytes",
                    body + "return 42u64;")

        concrete = f"Bytes{capacity}"
        definitions = byte_storage(concrete, capacity)
        helpers = (f"auto select({concrete} a,{concrete} b,{concrete} c,{concrete} d,"
                   f"{concrete} e,{concrete} f)->{concrete}{{return f;}}")
        body = (f"{concrete} original={concrete}();"
                f"static_assert(size_of({concrete})=={capacity});"
                f"static_assert(field_count({concrete})==0);"
                f"if(reflect_size(type_id({concrete}))!={capacity}){{return 1u64;}}"
                f"i64 i=0;while(i<{capacity}){{"
                "if(original.at(i)!=0u8){return 2u64;}"
                "original.set(i,u8((i*37+131)%256));i=i+1;}"
                f"const {concrete} snapshot=original.snapshot();"
                f"{concrete} copied=select(original,snapshot,original,snapshot,original,snapshot);"
                f"i64 j=0;while(j<{capacity}){{copied.set(j,u8(j));original.set(j,0u8);j=j+1;}}")
        for index, value in enumerate(values):
            body += (f"if(snapshot.at({index})!={value}u8){{return 3u64;}}"
                     f"if(copied.at({index})!={index}u8){{return 4u64;}}"
                     f"if(original.at({index})!=0u8){{return 5u64;}}")
        suite.check(f"byte class {capacity}: complete init, method result, six copied arguments",
                    body + "return 42u64;", definitions=definitions, helpers=helpers)
        suite.check(f"byte class {capacity}: reused storage reinitializes every byte",
                    f"i64 pass=0;while(pass<4){{{concrete} value={concrete}();"
                    f"i64 i=0;while(i<{capacity}){{if(value.at(i)!=0u8){{return 1u64;}}"
                    "value.set(i,255u8);i=i+1;}pass=pass+1;}return 42u64;",
                    definitions=definitions)
        # Distinct bytes identify both the parameter and its element position;
        # reading every argument catches swapped registers and copy intervals.
        names = "abcdef"
        body = "".join(f"{concrete} {name}={concrete}();" for name in names)
        body += f"i64 i=0;while(i<{capacity}){{"
        body += "".join(f"{name}.set(i,u8(i+{(slot + 1) * 11}));"
                        for slot, name in enumerate(names))
        body += "i=i+1;}return observe(a,b,c,d,e,f);"
        parameters = ",".join(f"{concrete} {name}" for name in names)
        helper = f"auto observe({parameters})->u64{{i64 i=0;while(i<{capacity}){{"
        helper += "".join(f"if({name}.at(i)!=u8(i+{(slot + 1) * 11}))"
                          f"{{return {slot + 1}u64;}}" for slot, name in enumerate(names))
        helper += f"i=i+1;}}return {MAX_U64}u64;}}"
        suite.check(f"byte class {capacity}: all six distinct argument snapshots are observed",
                    body, expected=MAX_U64, definitions=definitions, helpers=helper)


def scalar_and_layout_cases(suite):
    for scalar, value, literal in (("i64", -(1 << 63), "-9223372036854775808"),
                                   ("u64", MAX_U64, f"{MAX_U64}u64"),
                                   ("bool", 1, "true")):
        zero = "false" if scalar == "bool" else "0u64" if scalar == "u64" else "0"
        suite.check(f"old {scalar} storage width and complete result bits",
                    f"static_assert(size_of({scalar})=={1 if scalar == 'bool' else 8});"
                    f"static_assert(size_of(array<{scalar},3>)==24);"
                    f"static_assert(size_of(Old)==24);"
                    f"const Old a=Old(1u8,{literal},255u8);const Old b=identity(a);"
                    "if(b.first!=1u8){return " + zero + ";}"
                    "if(b.last!=255u8){return " + zero + ";}"
                    "return b.value;", expected=value, result=scalar,
                    definitions=f"class Old{{public:u8 first;{scalar} value;u8 last;"
                    f"Old(u8 a,{scalar} b,u8 c):first(a),value(b),last(c){{}}}};",
                    helpers="auto identity(Old value)->Old{return value;}")
    suite.check("u8 uses one byte while bool and enum retain eight-byte storage",
                "static_assert(size_of(u8)==1);static_assert(size_of(bool)==1);"
                "static_assert(size_of(array<bool,1>)==8);"
                "static_assert(size_of(Status)==8);static_assert(size_of(Flags)==32);"
                "const Flags a=Flags(255u8,true,128u8,Status::error);Flags b=identity(a);"
                "if(b.first!=255u8){return 1u64;}if(!b.flag){return 2u64;}"
                "if(b.last!=128u8){return 3u64;}if(b.code!=Status::error){return 4u64;}"
                "b.flag=false;if(b.flag){return 5u64;}if(!a.flag){return 6u64;}"
                "if(b.first!=255u8){return 7u64;}if(b.last!=128u8){return 8u64;}"
                "return 42u64;", definitions="enum class Status{ok,error};"
                "class Flags{public:u8 first;bool flag;u8 last;Status code;"
                "Flags(u8 a,bool b,u8 c,Status d):first(a),flag(b),last(c),code(d){} };",
                helpers="auto identity(Flags value)->Flags{return value;}")
    definitions = ("class Inner{public:u8 first;u64 word;u8 last;"
                   "Inner(u8 a,u64 b,u8 c):last(c),word(b),first(a){} };"
                   "class Outer{public:u8 lead;Inner payload;u8 tail;"
                   "Outer(u8 a,Inner b,u8 c):tail(c),payload(b),lead(a){} };")
    suite.check("nested mixed-width values use field alignment and tail rounding",
                "static_assert(size_of(Inner)==24);static_assert(size_of(Outer)==40);"
                f"Inner inner=Inner(128u8,{MAX_U64}u64,255u8);"
                "Outer original=Outer(17u8,inner,19u8);Outer returned=identity(original);"
                "inner.first=0u8;returned.lead=99u8;Inner projected=returned.payload;"
                "projected.last=1u8;const Inner saved=original.payload;"
                "const Inner untouched=returned.payload;"
                "if(original.lead!=17u8){return 1u64;}if(returned.tail!=19u8){return 2u64;}"
                "if(saved.first!=128u8){return 3u64;}if(saved.last!=255u8){return 4u64;}"
                "if(untouched.last!=255u8){return 5u64;}return saved.word;",
                expected=MAX_U64, definitions=definitions,
                helpers="auto identity(Outer source)->Outer{return source;}")
    definitions = byte_storage("Bytes4", 4) + "enum class Status{ok,error};" + (
        "class Report{Status state;Bytes4 data;public:"
        "Report(Status s,Bytes4 bytes):data(bytes),state(s){}"
        "auto status()const->Status{return state;}"
        "auto bytes()const->Bytes4{const Bytes4 result=data;return result;}"
        "auto snapshot()const->Report{const Bytes4 copy=data;"
        "const Report result=Report(state,copy);return result;}};")
    suite.check("four byte payload and enum report keep independent compact results",
                "static_assert(size_of(Bytes4)==4);static_assert(size_of(Report)==16);"
                "Bytes4 data=Bytes4();data.set(0,255u8);data.set(1,128u8);"
                "data.set(2,17u8);data.set(3,42u8);"
                "const Report original=Report(Status::error,data);const Report copy=original.snapshot();"
                "data.set(0,0u8);Bytes4 changed=copy.bytes();changed.set(3,0u8);"
                "const Bytes4 saved=original.bytes();"
                "if(copy.status()!=Status::error){return 1u64;}"
                "return u64(saved.at(0))*16777216u64+u64(saved.at(1))*65536u64+"
                "u64(saved.at(2))*256u64+u64(saved.at(3));",
                expected=0xFF80112A, definitions=definitions)
    for constraint in ("Scalar", "Value"):
        suite.check(f"{constraint} template instantiates compact u8 storage",
                    "const Box<u8> first=Box<u8>(255u8);const Box<u8> second=identity(first);"
                    "static_assert(size_of(Box<u8>)==1);return u64(second.get());", expected=255,
                    definitions=f"template<{constraint} T>class Box{{T value;public:"
                    "Box(T n):value(n){}auto get()const->T{return value;}};",
                    helpers="auto identity(Box<u8> value)->Box<u8>{return value;}")


def small_call_cases(suite):
    helpers = ("auto preserve(Cell a,u8 b,Cell c,u64 d,Cell e,bool f)->Cell{return a;}"
               "auto identity(Cell value)->Cell{return value;}"
               "auto clobber()->u8{Cell a=Cell(11u8);Cell b=identity(a);return b.get();}")
    suite.check("one-byte call result cannot overlap caller or argument snapshots",
                "Cell before=Cell(17u8);Cell original=Cell(128u8);Cell after=Cell(19u8);"
                "Cell copy=preserve(original,original.set(255u8),original,"
                f"{MAX_U64}u64,original,true);"
                "if(before.get()!=17u8){return 1u64;}if(after.get()!=19u8){return 2u64;}"
                "if(original.get()!=255u8){return 3u64;}if(copy.get()!=128u8){return 4u64;}"
                "copy.set(1u8);return u64(original.get());", expected=255,
                definitions=CELL, helpers=helpers)
    suite.check("one-byte constructor snapshot survives later returned temporary",
                "Cell item=Cell(128u8);const Pair<Cell,u8> value=Pair<Cell,u8>(item,clobber());"
                "item.set(255u8);const Cell saved=value.first;"
                "return u64(saved.get())*256u64+u64(value.second);", expected=32779,
                definitions=CELL + PAIR, helpers=helpers)
    suite.check("one-byte returned locals remain independent across nested scopes and loops",
                "Cell outside=Cell(255u8);i64 i=0;u64 total=0u64;while(i<32){"
                "Cell source=Cell(u8(i));Cell a=identity(source);const Cell b=a.snapshot();"
                "a.set(128u8);source.set(129u8);"
                "{Cell a=identity(b);total=total+u64(a.get());}"
                "if(outside.get()!=255u8){return 1u64;}i=i+1;}return total;",
                expected=496, definitions=CELL, helpers=helpers)
    suite.check("constructor byte snapshots follow expression order",
                "Cell item=Cell(128u8);const Pair<Cell,u8> early=Pair<Cell,u8>(item,item.set(255u8));"
                "const Pair<u8,Cell> late=Pair<u8,Cell>(item.set(1u8),item);"
                "const Cell a=early.first;const Cell b=late.second;"
                "return u64(a.get())*256u64+u64(b.get());", expected=32769,
                definitions=CELL + PAIR)


def maximum_leaf_cases(suite):
    definitions = ("class Mixed64{u8 head;builtin::array<u8,60> bytes;u64 wide;bool flag;u8 tail;public:"
                   "Mixed64(u8 a,u64 b,bool c,u8 d):tail(d),bytes{},head(a),wide(b),flag(c){}"
                   "auto at(i64 i)const->u8{return bytes[i];}"
                   "auto set(i64 i,u8 n)->u8{bytes[i]=n;return bytes[i];}"
                   "auto first()const->u8{return head;}auto last()const->u8{return tail;}"
                   "auto word()const->u64{return wide;}auto enabled()const->bool{return flag;}};")
    helpers = ("auto inspect(Mixed64 a,u8 changed,Mixed64 b,u64 wide,Mixed64 c,bool yes)->u64{"
               "if(changed!=200u8){return 1u64;}if(!yes){return 2u64;}"
               "if(a.first()!=255u8){return 3u64;}if(c.last()!=128u8){return 4u64;}"
               "if(!b.enabled()){return 5u64;}if(a.word()!=wide){return 6u64;}"
               "i64 i=0;while(i<60){if(a.at(i)!=u8(i)){return 7u64;}"
               "if(i<59){if(b.at(i)!=u8(i)){return 8u64;}if(c.at(i)!=u8(i)){return 9u64;}}"
               "i=i+1;}if(b.at(59)!=200u8){return 10u64;}if(c.at(59)!=200u8){return 11u64;}"
               "return wide;}"
               "auto identity(Mixed64 value)->Mixed64{return value;}")
    suite.check("six mixed arguments preserve every leaf of a 64-leaf packed class",
                "static_assert(size_of(Mixed64)==88);"
                f"Mixed64 original=Mixed64(255u8,{MAX_U64}u64,true,128u8);"
                "i64 i=0;while(i<60){original.set(i,u8(i));i=i+1;}"
                f"const u64 answer=inspect(original,original.set(59,200u8),original,{MAX_U64}u64,original,true);"
                "Mixed64 copied=identity(original);copied.set(0,255u8);"
                "if(original.at(0)!=0u8){return 12u64;}return answer;",
                expected=MAX_U64, definitions=definitions, helpers=helpers)
    suite.reject("65 scalar leaves cannot cross a value-call boundary",
                 f"Mixed64 original=Mixed64(255u8,{MAX_U64}u64,true,128u8);"
                 "Mixed64 copy=identity(original);return copy.word();",
                 definitions.replace("array<u8,60>", "array<u8,61>"),
                 "auto identity(Mixed64 value)->Mixed64{return value;}")


def empty_cases(suite):
    definitions = EMPTY + (
        "class EmptyNest{public:Empty value;EmptyNest(Empty a):value(a){} };"
        "class Tiny{public:u8 first;EmptyNest empty;u8 last;"
        "Tiny(u8 a,EmptyNest b,u8 c):last(c),empty(b),first(a){}"
        "auto snapshot()const->Tiny{const EmptyNest e=empty;"
        "const Tiny result=Tiny(first,e,last);return result;}};")
    helpers = ("auto empty_copy(EmptyNest value)->EmptyNest{return value;}"
               "auto identity(Tiny value)->Tiny{return value;}")
    suite.check("empty descendants reserve standalone storage but no embedded payload",
                "static_assert(size_of(Empty)==8);static_assert(size_of(EmptyNest)==8);"
                "static_assert(size_of(Tiny)==2);static_assert(field_count(Tiny)==3);"
                "Empty empty=Empty();EmptyNest nest=EmptyNest(empty);const EmptyNest standalone=empty_copy(nest);"
                "Tiny original=Tiny(128u8,standalone,255u8);Tiny copy=identity(original);"
                "copy.first=0u8;const Tiny returned=original.snapshot();const EmptyNest projected=returned.empty;"
                "const Empty leaf=projected.value;if(leaf.answer()!=42){return 1u64;}"
                "return u64(original.first)*256u64+u64(returned.last);",
                expected=33023, definitions=definitions, helpers=helpers)
    suite.check("empty siblings preserve old word layouts beside byte layouts",
                "Empty e=Empty();const Pair<Empty,Empty> pair=Pair<Empty,Empty>(e,e);"
                "const Legacy legacy=Legacy(19,pair,23);const Legacy copy=identity(legacy);"
                "static_assert(size_of(Pair<Empty,Empty>)==8);static_assert(size_of(Legacy)==16);"
                "const Pair<Empty,Empty> projected=copy.empty;const Empty a=projected.first;"
                "const Empty b=projected.second;if(a.answer()!=b.answer()){return 1u64;}"
                "return u64(copy.first+copy.last);", definitions=EMPTY + PAIR +
                "class Legacy{public:i64 first;Pair<Empty,Empty> empty;i64 last;"
                "Legacy(i64 a,Pair<Empty,Empty> b,i64 c):first(a),empty(b),last(c){} };",
                helpers="auto identity(Legacy value)->Legacy{return value;}")


def model_cases(suite, seed, steps):
    rng = random.Random(seed)
    for capacity in (3, 9):
        concrete = f"Bytes{capacity}"
        state = [0] * capacity
        body = [f"{concrete} original={concrete}();"]
        for step in range(steps):
            index = rng.randrange(capacity)
            value = rng.randrange(256)
            if step % 3 == 0:
                state[index] = value
                body.append(f"original.set({index},{value}u8);")
            else:
                changed = list(state)
                changed[index] = value
                body.append(f"{{const {concrete} saved=original.snapshot();"
                            f"{concrete} copy=identity(saved);copy.set({index},{value}u8);")
                for offset, expected in enumerate(state):
                    body.append(f"if(original.at({offset})!={expected}u8){{return {100+step}u64;}}"
                                f"if(saved.at({offset})!={expected}u8){{return {200+step}u64;}}"
                                f"if(copy.at({offset})!={changed[offset]}u8){{return {300+step}u64;}}")
                body.append("}")
        suite.check(f"independent byte snapshot list model capacity={capacity}, seed={seed}, steps={steps}",
                    "".join(body) + "return 42u64;", definitions=byte_storage(concrete, capacity),
                    helpers=f"auto identity({concrete} value)->{concrete}{{return value;}}")


def bounds_cases(suite):
    for capacity in CAPACITIES:
        concrete = f"Bytes{capacity}"
        definitions = byte_storage(concrete, capacity)
        for index in (-1, capacity):
            suite.check(f"byte class {capacity} read bounds {index}",
                        f"{concrete} bytes={concrete}();return u64(bytes.at({index}));",
                        expected=Trap.BOUNDS, definitions=definitions)
            suite.check(f"byte class {capacity} write bounds {index}",
                        f"{concrete} bytes={concrete}();return u64(bytes.set({index},255u8));",
                        expected=Trap.BOUNDS, definitions=definitions)
    for index in (-(1 << 63), (1 << 63) - 1):
        suite.check(f"byte array extreme signed bounds {index}",
                    f"array<u8,3> bytes={{1u8,2u8,3u8}};return u64(bytes[{index}]);",
                    expected=Trap.BOUNDS)


def rejection_cases(suite):
    for name, body, definitions, helpers in (
        ("private byte remains inaccessible", "Cell a=Cell(1u8);return u64(a.value);", CELL, ""),
        ("const byte receiver cannot mutate", "const Cell a=Cell(1u8);return u64(a.set(2u8));", CELL, ""),
        ("byte argument snapshot is readonly", "Cell a=Cell(1u8);return mutate(a);", CELL,
         "auto mutate(Cell a)->u64{return u64(a.set(2u8));}"),
        ("private packed array remains inaccessible", "Bytes4 a=Bytes4();return u64(a.data[0]);",
         byte_storage("Bytes4", 4), ""),
        ("packed array element type stays exact", "Bytes4 a=Bytes4();return u64(a.set(0,1u64));",
         byte_storage("Bytes4", 4), ""),
        ("const packed array cannot mutate", "const array<u8,3> a={1u8,2u8,3u8};a[1]=4u8;return 42u64;", "", ""),
        ("packed value copy remains nominal", "Cell a=Cell(1u8);Other b=a;return 42u64;",
         CELL + CELL.replace("Cell", "Other"), ""),
        ("byte constructor requires complete fields", "return 42u64;",
         "class Bad{u8 a;u8 b;public:Bad(u8 n):a(n){} };", ""),
        ("byte constructor rejects repeated initialization", "return 42u64;",
         "class Bad{u8 a;public:Bad(u8 n):a(n),a(n){} };", ""),
        ("packed array requires initialization", "return 42u64;",
         "class Bad{array<u8,4> a;public:Bad(){} };", ""),
        ("zero-size embedded class still requires initialization", "return 42u64;",
         EMPTY + "class Bad{u8 first;Empty empty;u8 last;public:Bad():first(1u8),last(2u8){} };", ""),
        ("zero-size embedded class requires nominal source", "return 42u64;",
         EMPTY + "class Bad{u8 first;Empty empty;public:Bad():first(1u8),empty{}{} };", ""),
        ("missing designated byte remains incomplete", "const Bad a=Bad{.first=1u8};return 42u64;",
         "class Bad{public:u8 first;u8 last;};", ""),
        ("enum stays outside Scalar constraint", "const Box<State> a=Box<State>(State::ok);return 42u64;",
         "enum class State{ok,error};template<Scalar T>class Box{T value;public:Box(T n):value(n){} };", ""),
        ("enum is not a builtin scalar-array element", "array<State,1> a={State::ok};return 42u64;",
         "enum class State{ok,error};", ""),
        ("class method aggregate parameters remain unsupported", "return 42u64;",
         CELL + "class Bad{public:Bad(){}auto take(Cell a)->u64{return u64(a.get());}};", ""),
    ):
        suite.reject(name, body, definitions, helpers)
    for capacity in (0, 65):
        suite.reject(f"packed array capacity {capacity} remains unsupported", "return 42u64;",
                     byte_storage("Bad", capacity))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", nargs="?", type=Path, default=ROOT / "build/aurorac")
    parser.add_argument("--self-test-only", action="store_true")
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument("--seed", type=int, default=13013)
    parser.add_argument("--steps", type=int, default=24)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()
    require(args.timeout > 0 and 1 <= args.steps <= 128, "invalid timeout or steps")
    compiler = args.compiler.resolve()
    started = time.monotonic()
    if not args.self_test_only:
        print(f"INFO packed values compiler={compiler} "
              f"sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()}", flush=True)
    with tempfile.TemporaryDirectory(prefix="aurora-packed-values-") as temporary:
        suite = Suite(Path(temporary), compiler, args.timeout, args.keep_going)
        self_tests(suite)
        if args.self_test_only:
            return
        array_cases(suite)
        scalar_and_layout_cases(suite)
        small_call_cases(suite)
        maximum_leaf_cases(suite)
        empty_cases(suite)
        model_cases(suite, args.seed, args.steps)
        bounds_cases(suite)
        rejection_cases(suite)
        require(not suite.failures, f"{len(suite.failures)} packed-value cases failed")
        print(f"PASS packed values: {suite.count} native cases including {suite.traps} exact traps; "
              f"{suite.rejections} rejection cases, each with absent and existing output; "
              f"{time.monotonic()-started:.2f}s", flush=True)


if __name__ == "__main__":
    main()
