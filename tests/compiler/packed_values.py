#!/usr/bin/env python3
"""Native source acceptance for compact bytes and mixed-width value boundaries.

Python lists and explicit source values determine expected results independently
of compiler layout helpers, IR, and assembly. Results are complete 64-bit values;
bounds faults must reach the exact named UD2 (native_runner.py). Rejections leave
no artifact and must not change an existing one.

This is bounded layout/copy evidence, not a safety or performance proof.
Run: python3 tests/compiler/packed_values.py build/aurorac
"""

from __future__ import annotations

import argparse
from enum import Enum
from pathlib import Path
import random
import re

from native_runner import DIAGNOSTIC, Suite as Runner, require


ROOT = Path(__file__).resolve().parents[2]
CAPACITIES = (1, 3, 4, 7, 8, 9, 64)
MAX_U64 = (1 << 64) - 1
EMPTY = "class Empty{public:Empty(){}auto answer()const->i64{return 42;}};"


class Trap(Enum):
    BOUNDS = ".Laurora_bounds_trap"
    OVERFLOW = ".Laurora_overflow_trap"


def source(body, definitions="", helpers="", result="u64", imports=()):
    return (
        "module packed;"
        + "".join(f"import {name};" for name in imports)
        + definitions
        + helpers
        + f"auto test()->{result}{{{body}}}"
    )


def byte_storage(name, capacity):
    return (
        f"class {name}{{builtin::array<u8,{capacity}> data;public:"
        f"{name}():data{{}}{{}}"
        "auto at(i64 index)const->u8{return data[index];}"
        "auto set(i64 index,u8 value)->u8{data[index]=value;return data[index];}"
        f"auto snapshot()const->{name}{{{name} result={name}();i64 i=0;"
        f"while(i<{capacity}){{result.set(i,data[i]);i=i+1;}}return result;}}}};"
    )


class Suite:
    """packed-module cases on one shared runner: `check`/`reject`, then `finish`."""

    def __init__(self, compiler, timeout=10, label="packed values"):
        self.runner = Runner(compiler, label, timeout=timeout, pattern=DIAGNOSTIC)

    def check(self, name, body, expected=42, definitions="", helpers="", result="u64", imports=(), inspect=None):
        self.runner.check(name, source(body, definitions, helpers, result, imports), expected, inspect=inspect)

    def reject(self, name, body, definitions="", helpers="", imports=()):
        self.runner.reject(name, source(body, definitions, helpers, imports=imports))

    def finish(self):
        return self.runner.finish()


def array_cases(suite):
    for capacity in CAPACITIES:
        values = [(i * 37 + 131) % 256 for i in range(capacity)]
        initializers = ",".join(f"{v}u8" for v in values)
        body = (
            f"array<u8,{capacity}> original={{{initializers}}};"
            f"const builtin::array<u8,{capacity}> saved=original;"
            f"array<u8,{capacity}> copy=saved;"
            f"static_assert(size_of(array<u8,{capacity}>)=={capacity});"
            f"static_assert(type_id(array<u8,{capacity}>)==type_id(builtin::array<u8,{capacity}>));"
            f"if(reflect_size(type_id(array<u8,{capacity}>))!={capacity}){{return 1u64;}}"
            f"i64 i=0;while(i<{capacity}){{copy[i]=u8(i);i=i+1;}}"
        )
        for index, value in enumerate(values):
            body += (
                f"if(original[{index}]!={value}u8){{return 2u64;}}"
                f"if(saved[{index}]!={value}u8){{return 3u64;}}"
                f"if(copy[{index}]!={index}u8){{return 4u64;}}"
            )
        suite.check(f"raw byte array {capacity}: exact size and independent adjacent bytes", body + "return 42u64;")

        concrete = f"Bytes{capacity}"
        definitions = byte_storage(concrete, capacity)
        helpers = (
            f"auto select({concrete} a,{concrete} b,{concrete} c,{concrete} d,"
            f"{concrete} e,{concrete} f)->{concrete}{{return f;}}"
        )
        body = (
            f"{concrete} original={concrete}();"
            f"static_assert(size_of({concrete})=={capacity});"
            f"static_assert(field_count({concrete})==0);"
            f"if(reflect_size(type_id({concrete}))!={capacity}){{return 1u64;}}"
            f"i64 i=0;while(i<{capacity}){{"
            "if(original.at(i)!=0u8){return 2u64;}"
            "original.set(i,u8((i*37+131)%256));i=i+1;}"
            f"const {concrete} snapshot=original.snapshot();"
            f"{concrete} copied=select(original,snapshot,original,snapshot,original,snapshot);"
            f"i64 j=0;while(j<{capacity}){{copied.set(j,u8(j));original.set(j,0u8);j=j+1;}}"
        )
        for index, value in enumerate(values):
            body += (
                f"if(snapshot.at({index})!={value}u8){{return 3u64;}}"
                f"if(copied.at({index})!={index}u8){{return 4u64;}}"
                f"if(original.at({index})!=0u8){{return 5u64;}}"
            )
        suite.check(
            f"byte class {capacity}: complete init, method result, six copied arguments",
            body + "return 42u64;",
            definitions=definitions,
            helpers=helpers,
        )
        suite.check(
            f"byte class {capacity}: reused storage reinitializes every byte",
            f"i64 pass=0;while(pass<4){{{concrete} value={concrete}();"
            f"i64 i=0;while(i<{capacity}){{if(value.at(i)!=0u8){{return 1u64;}}"
            "value.set(i,255u8);i=i+1;}pass=pass+1;}return 42u64;",
            definitions=definitions,
        )
        # Distinct bytes identify both the parameter and its element position;
        # reading every argument catches swapped registers and copy intervals.
        names = "abcdef"
        body = "".join(f"{concrete} {name}={concrete}();" for name in names)
        body += f"i64 i=0;while(i<{capacity}){{"
        body += "".join(f"{name}.set(i,u8(i+{(slot + 1) * 11}));" for slot, name in enumerate(names))
        body += "i=i+1;}return observe(a,b,c,d,e,f);"
        parameters = ",".join(f"{concrete} {name}" for name in names)
        helper = f"auto observe({parameters})->u64{{i64 i=0;while(i<{capacity}){{"
        helper += "".join(
            f"if({name}.at(i)!=u8(i+{(slot + 1) * 11})){{return {slot + 1}u64;}}" for slot, name in enumerate(names)
        )
        helper += f"i=i+1;}}return {MAX_U64}u64;}}"
        suite.check(
            f"byte class {capacity}: all six distinct argument snapshots are observed",
            body,
            expected=MAX_U64,
            definitions=definitions,
            helpers=helper,
        )


def byte_run_cases(suite):
    # Each boundary compiles once and observes every byte in loops. The empty
    # case is already exercised by empty_cases; zero-capacity arrays stay invalid.
    for capacity in (1, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 63, 64, 65, 511, 512):
        definitions = byte_storage("Bytes", capacity)
        helpers = "auto identity(Bytes value)->Bytes{return value;}"
        body = (
            "Bytes original=Bytes();i64 i=0;"
            f"while(i<{capacity}){{original.set(i,u8((i*37+131)%256));i=i+1;}}"
            "const Bytes saved=original;Bytes returned=identity(saved);"
            "const Bytes method=returned.snapshot();"
            "original.set(0,0u8);"
            f"returned.set({capacity - 1},1u8);i=0;while(i<{capacity}){{"
            "const u8 expected=u8((i*37+131)%256);"
            "if(saved.at(i)!=expected){return 1u64;}"
            "if(method.at(i)!=expected){return 2u64;}"
            "if(i==0){if(original.at(i)!=0u8){return 3u64;}}"
            "else{if(original.at(i)!=expected){return 4u64;}}"
            f"if(i=={capacity - 1}){{if(returned.at(i)!=1u8){{return 5u64;}}}}"
            "else{if(returned.at(i)!=expected){return 6u64;}}i=i+1;}return 42u64;"
        )
        suite.check(
            f"byte-run boundary {capacity}: complete copies and exact final byte",
            body,
            definitions=definitions,
            helpers=helpers,
        )

    definitions = (
        byte_storage("Bytes9", 9)
        + "enum class State{ok,error};"
        + (
            "class Envelope{public:u8 lead;Bytes9 payload;u8 tail;bool flag;State state;u64 word;"
            "Envelope(u8 a,Bytes9 b,u8 c,bool d,State e,u64 f):"
            "word(f),state(e),flag(d),tail(c),payload(b),lead(a){}"
            "auto replace(Bytes9 value)->u8{payload=value;return tail;}"
            "auto project()const->Bytes9{const Bytes9 copy=payload;return copy;}"
            "auto snapshot(Bytes9 value,u8 changed,u64 wide,bool yes,i64 negative,State code)const->Envelope{"
            "if(changed!=211u8){return Envelope(1u8,value,tail,flag,state,word);}"
            "if(wide!=word){return Envelope(2u8,value,tail,flag,state,word);}"
            "if(!yes){return Envelope(3u8,value,tail,flag,state,word);}"
            "if(negative!=-42){return Envelope(4u8,value,tail,flag,state,word);}"
            "if(code!=State::error){return Envelope(5u8,value,tail,flag,state,word);}"
            "return Envelope(lead,value,tail,flag,state,word);}};"
        )
    )
    helpers = (
        "auto identity(Envelope value)->Envelope{return value;}"
        "auto scalar_first(u64 word,Bytes9 value,u8 byte,bool flag,i64 negative,State code)->u64{"
        f"if(word!={MAX_U64}u64){{return 21u64;}}"
        "if(byte!=241u8){return 22u64;}if(!flag){return 23u64;}"
        "if(negative!=-42){return 24u64;}if(code!=State::error){return 25u64;}"
        "return u64(value.at(8));}"
    )
    body = (
        "static_assert(size_of(Envelope)==40);Bytes9 original=Bytes9();"
        "i64 i=0;while(i<9){original.set(i,u8(i+128));i=i+1;}"
        f"Envelope envelope=Envelope(17u8,original,19u8,true,State::error,{MAX_U64}u64);"
        "Envelope local=identity(envelope);const Bytes9 projected=local.payload;"
        "Bytes9 replacement=projected;replacement.set(8,7u8);local.payload=replacement;"
        "if(local.replace(projected)!=19u8){return 7u64;}"
        "const Bytes9 receiver_copy=local.project();"
        "i64 pass=0;while(pass<4){original.set(8,136u8);"
        "const Envelope snapshot=envelope.snapshot(original,original.set(8,211u8),"
        f"{MAX_U64}u64,true,-42,State::error);"
        "if(snapshot.lead!=17u8){return 8u64;}if(snapshot.tail!=19u8){return 9u64;}"
        "if(!snapshot.flag){return 10u64;}if(snapshot.state!=State::error){return 11u64;}"
        f"if(snapshot.word!={MAX_U64}u64){{return 12u64;}}"
        "const Bytes9 saved=snapshot.payload;i=0;while(i<9){"
        "if(saved.at(i)!=u8(i+128)){return 13u64;}"
        "if(projected.at(i)!=u8(i+128)){return 14u64;}"
        "if(receiver_copy.at(i)!=u8(i+128)){return 15u64;}i=i+1;}"
        "if(original.at(8)!=211u8){return 16u64;}pass=pass+1;}"
        f"return scalar_first({MAX_U64}u64,receiver_copy,241u8,true,-42,State::error);"
    )
    suite.check(
        "unaligned nested byte runs preserve canaries, mixed scalar registers and method snapshots",
        body,
        expected=136,
        definitions=definitions,
        helpers=helpers,
    )

    definitions = (
        byte_storage("Bytes65", 65) + "class Packet{public:u8 head;Bytes65 data;u8 tail;u64 number;"
        "Packet(u8 a,Bytes65 b,u8 c,u64 d):head(a),data(b),tail(c),number(d){}"
        "auto snapshot()const->Packet{const Bytes65 copied=data;"
        "const Packet saved=Packet(head,copied,tail,number);return saved;}};"
        "class Packets{array<Packet,2> items;public:"
        "Packets(Packet a,Packet b):items{a,b}{}"
        "auto at(i64 index)const->Packet{const Packet value=items[index];return value;}"
        "auto replace(i64 index,Packet value)->i64{items[index]=value;return index;}};"
    )
    helpers = (
        "auto checked(Packet value,u64 a,u8 b,bool c,i64 d,u64 e)->Packet{Packet result=value;"
        f"if(a!={MAX_U64}u64){{result.head=1u8;}}"
        "if(b!=241u8){result.head=2u8;}if(!c){result.head=3u8;}"
        "if(d!=-42){result.head=4u8;}if(e!=123456u64){result.head=5u8;}return result;}"
    )
    suite.check(
        "compact mixed payload preserves padding boundaries, argument registers and class arrays",
        "static_assert(size_of(Packet)==80);Bytes65 bytes=Bytes65();i64 i=0;"
        "while(i<65){bytes.set(i,u8(i+128));i=i+1;}"
        f"Packet original=Packet(17u8,bytes,19u8,{MAX_U64}u64);"
        f"const Packet saved=checked(original,{MAX_U64}u64,241u8,true,-42,123456u64);"
        "Packets packets=Packets(original,saved);original.head=0u8;"
        "const Packet extracted=packets.at(1);Packet changed=extracted;changed.tail=7u8;"
        "packets.replace(0,changed);const Packet replaced=packets.at(0);"
        "const Packet untouched=packets.at(1);const Packet method=untouched.snapshot();"
        "if(saved.head!=17u8){return 1u64;}if(extracted.tail!=19u8){return 2u64;}"
        "if(replaced.tail!=7u8){return 3u64;}if(untouched.tail!=19u8){return 4u64;}"
        f"if(method.number!={MAX_U64}u64){{return 5u64;}}"
        "const Bytes65 method_data=method.data;const Bytes65 replaced_data=replaced.data;"
        "i=0;while(i<65){if(method_data.at(i)!=u8(i+128)){return 6u64;}"
        "if(replaced_data.at(i)!=u8(i+128)){return 7u64;}i=i+1;}return 42u64;",
        definitions=definitions,
        helpers=helpers,
        inspect=compact_copy,
    )


def compact_copy(assembly):
    # Observe the copy count, not the width used to materialize it: these
    # nonnegative counts have the same RCX value after either MOV form.
    counts = [int(value) for value in re.findall(r"mov(?:abs)?[ql] \$(\d+), %[er]cx\n\s+cld\n\s+rep movsb", assembly)]
    require(67 in counts, "compact run stopped at representation padding")
    require(80 not in counts, "compact copy included representation padding")


def scalar_and_layout_cases(suite):
    for scalar, value, literal in (
        ("i64", -(1 << 63), "-9223372036854775808"),
        ("u64", MAX_U64, f"{MAX_U64}u64"),
        ("bool", 1, "true"),
    ):
        zero = "false" if scalar == "bool" else "0u64" if scalar == "u64" else "0"
        suite.check(
            f"old {scalar} storage width and complete result bits",
            f"static_assert(size_of({scalar})=={1 if scalar == 'bool' else 8});"
            f"static_assert(size_of(array<{scalar},3>)==24);"
            f"static_assert(size_of(Old)==24);"
            f"const Old a=Old(1u8,{literal},255u8);const Old b=identity(a);"
            "if(b.first!=1u8){return " + zero + ";}"
            "if(b.last!=255u8){return " + zero + ";}"
            "return b.value;",
            expected=value,
            result=scalar,
            definitions=f"class Old{{public:u8 first;{scalar} value;u8 last;"
            f"Old(u8 a,{scalar} b,u8 c):first(a),value(b),last(c){{}}}};",
            helpers="auto identity(Old value)->Old{return value;}",
        )
    definitions = (
        "class Inner{public:u8 first;u64 word;u8 last;"
        "Inner(u8 a,u64 b,u8 c):last(c),word(b),first(a){} };"
        "class Outer{public:u8 lead;Inner payload;u8 tail;"
        "Outer(u8 a,Inner b,u8 c):tail(c),payload(b),lead(a){} };"
    )
    suite.check(
        "nested mixed-width values use field alignment and tail rounding",
        "static_assert(size_of(Inner)==24);static_assert(size_of(Outer)==40);"
        f"Inner inner=Inner(128u8,{MAX_U64}u64,255u8);"
        "Outer original=Outer(17u8,inner,19u8);Outer returned=identity(original);"
        "inner.first=0u8;returned.lead=99u8;Inner projected=returned.payload;"
        "projected.last=1u8;const Inner saved=original.payload;"
        "const Inner untouched=returned.payload;"
        "if(original.lead!=17u8){return 1u64;}if(returned.tail!=19u8){return 2u64;}"
        "if(saved.first!=128u8){return 3u64;}if(saved.last!=255u8){return 4u64;}"
        "if(untouched.last!=255u8){return 5u64;}return saved.word;",
        expected=MAX_U64,
        definitions=definitions,
        helpers="auto identity(Outer source)->Outer{return source;}",
    )
    definitions = (
        byte_storage("Bytes4", 4)
        + "enum class Status{ok,error};"
        + (
            "class Report{Status state;Bytes4 data;public:"
            "Report(Status s,Bytes4 bytes):data(bytes),state(s){}"
            "auto status()const->Status{return state;}"
            "auto bytes()const->Bytes4{const Bytes4 result=data;return result;}"
            "auto snapshot()const->Report{const Bytes4 copy=data;"
            "const Report result=Report(state,copy);return result;}};"
        )
    )
    suite.check(
        "four byte payload and enum report keep independent compact results",
        "static_assert(size_of(Bytes4)==4);static_assert(size_of(Report)==16);"
        "Bytes4 data=Bytes4();data.set(0,255u8);data.set(1,128u8);"
        "data.set(2,17u8);data.set(3,42u8);"
        "const Report original=Report(Status::error,data);const Report copy=original.snapshot();"
        "data.set(0,0u8);Bytes4 changed=copy.bytes();changed.set(3,0u8);"
        "const Bytes4 saved=original.bytes();"
        "if(copy.status()!=Status::error){return 1u64;}"
        "return u64(saved.at(0))*16777216u64+u64(saved.at(1))*65536u64+"
        "u64(saved.at(2))*256u64+u64(saved.at(3));",
        expected=0xFF80112A,
        definitions=definitions,
    )


def maximum_leaf_cases(suite):
    definitions = (
        "class Mixed64{u8 head;builtin::array<u8,60> bytes;u64 wide;bool flag;u8 tail;public:"
        "Mixed64(u8 a,u64 b,bool c,u8 d):tail(d),bytes{},head(a),wide(b),flag(c){}"
        "auto at(i64 i)const->u8{return bytes[i];}"
        "auto set(i64 i,u8 n)->u8{bytes[i]=n;return bytes[i];}"
        "auto first()const->u8{return head;}auto last()const->u8{return tail;}"
        "auto word()const->u64{return wide;}auto enabled()const->bool{return flag;}};"
    )
    helpers = (
        "auto inspect(Mixed64 a,u8 changed,Mixed64 b,u64 wide,Mixed64 c,bool yes)->u64{"
        "if(changed!=200u8){return 1u64;}if(!yes){return 2u64;}"
        "if(a.first()!=255u8){return 3u64;}if(c.last()!=128u8){return 4u64;}"
        "if(!b.enabled()){return 5u64;}if(a.word()!=wide){return 6u64;}"
        "i64 i=0;while(i<60){if(a.at(i)!=u8(i)){return 7u64;}"
        "if(i<59){if(b.at(i)!=u8(i)){return 8u64;}if(c.at(i)!=u8(i)){return 9u64;}}"
        "i=i+1;}if(b.at(59)!=200u8){return 10u64;}if(c.at(59)!=200u8){return 11u64;}"
        "return wide;}"
        "auto identity(Mixed64 value)->Mixed64{return value;}"
    )
    suite.check(
        "six mixed arguments preserve every leaf of a 64-leaf packed class",
        "static_assert(size_of(Mixed64)==88);"
        f"Mixed64 original=Mixed64(255u8,{MAX_U64}u64,true,128u8);"
        "i64 i=0;while(i<60){original.set(i,u8(i));i=i+1;}"
        f"const u64 answer=inspect(original,original.set(59,200u8),original,{MAX_U64}u64,original,true);"
        "Mixed64 copied=identity(original);copied.set(0,255u8);"
        "if(original.at(0)!=0u8){return 12u64;}return answer;",
        expected=MAX_U64,
        definitions=definitions,
        helpers=helpers,
    )
    suite.check(
        "65 mixed byte/scalar leaves now cross a value-call boundary",
        f"Mixed64 original=Mixed64(255u8,{MAX_U64}u64,true,128u8);Mixed64 copy=identity(original);return copy.word();",
        expected=MAX_U64,
        definitions=definitions.replace("array<u8,60>", "array<u8,61>"),
        helpers="auto identity(Mixed64 value)->Mixed64{return value;}",
    )


def empty_cases(suite):
    definitions = EMPTY + (
        "class EmptyNest{public:Empty value;EmptyNest(Empty a):value(a){} };"
        "class Tiny{public:u8 first;EmptyNest empty;u8 last;"
        "Tiny(u8 a,EmptyNest b,u8 c):last(c),empty(b),first(a){}"
        "auto snapshot()const->Tiny{const EmptyNest e=empty;"
        "const Tiny result=Tiny(first,e,last);return result;}};"
    )
    helpers = "auto empty_copy(EmptyNest value)->EmptyNest{return value;}auto identity(Tiny value)->Tiny{return value;}"
    suite.check(
        "empty descendants reserve standalone storage but no embedded payload",
        "static_assert(size_of(Empty)==8);static_assert(size_of(EmptyNest)==8);"
        "static_assert(size_of(Tiny)==2);static_assert(field_count(Tiny)==3);"
        "Empty empty=Empty();EmptyNest nest=EmptyNest(empty);const EmptyNest standalone=empty_copy(nest);"
        "Tiny original=Tiny(128u8,standalone,255u8);Tiny copy=identity(original);"
        "copy.first=0u8;const Tiny returned=original.snapshot();const EmptyNest projected=returned.empty;"
        "const Empty leaf=projected.value;if(leaf.answer()!=42){return 1u64;}"
        "return u64(original.first)*256u64+u64(returned.last);",
        expected=33023,
        definitions=definitions,
        helpers=helpers,
    )


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
                body.append(
                    f"{{const {concrete} saved=original.snapshot();"
                    f"{concrete} copy=identity(saved);copy.set({index},{value}u8);"
                )
                for offset, expected in enumerate(state):
                    body.append(
                        f"if(original.at({offset})!={expected}u8){{return {100 + step}u64;}}"
                        f"if(saved.at({offset})!={expected}u8){{return {200 + step}u64;}}"
                        f"if(copy.at({offset})!={changed[offset]}u8){{return {300 + step}u64;}}"
                    )
                body.append("}")
        suite.check(
            f"independent byte snapshot list model capacity={capacity}, seed={seed}, steps={steps}",
            "".join(body) + "return 42u64;",
            definitions=byte_storage(concrete, capacity),
            helpers=f"auto identity({concrete} value)->{concrete}{{return value;}}",
        )


def bounds_cases(suite):
    for capacity in (2, 4, 8):
        concrete = f"std::Bytes{capacity}"
        for index in (-(1 << 63), -1, capacity, (1 << 63) - 1):
            suite.check(
                f"owned codec {capacity} read bounds {index}",
                f"{concrete} bytes={concrete}();return u64(bytes.at({index}));",
                expected=Trap.BOUNDS,
                imports=("std.bytes",),
            )
            suite.check(
                f"owned codec {capacity} write bounds {index}",
                f"{concrete} bytes={concrete}();return u64(bytes.set({index},255u8));",
                expected=Trap.BOUNDS,
                imports=("std.bytes",),
            )
    for capacity in CAPACITIES:
        concrete = f"Bytes{capacity}"
        definitions = byte_storage(concrete, capacity)
        for index in (-1, capacity):
            suite.check(
                f"byte class {capacity} read bounds {index}",
                f"{concrete} bytes={concrete}();return u64(bytes.at({index}));",
                expected=Trap.BOUNDS,
                definitions=definitions,
            )
            suite.check(
                f"byte class {capacity} write bounds {index}",
                f"{concrete} bytes={concrete}();return u64(bytes.set({index},255u8));",
                expected=Trap.BOUNDS,
                definitions=definitions,
            )
    for index in (-(1 << 63), (1 << 63) - 1):
        suite.check(
            f"byte array extreme signed bounds {index}",
            f"array<u8,3> bytes={{1u8,2u8,3u8}};return u64(bytes[{index}]);",
            expected=Trap.BOUNDS,
        )


def rejection_cases(suite):
    for capacity in (0, 513):
        suite.reject(
            f"packed array capacity {capacity} remains unsupported", "return 42u64;", byte_storage("Bad", capacity)
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", nargs="?", type=Path, default=ROOT / "build/aurorac")
    parser.add_argument("--seed", type=int, default=13013)
    parser.add_argument("--steps", type=int, default=24)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()
    require(args.timeout > 0 and 1 <= args.steps <= 128, "invalid timeout or steps")
    suite = Suite(args.compiler, args.timeout)
    suite.runner.load(Path(__file__).with_suffix(".cases"), EMPTY=EMPTY)
    array_cases(suite)
    byte_run_cases(suite)
    scalar_and_layout_cases(suite)
    maximum_leaf_cases(suite)
    empty_cases(suite)
    model_cases(suite, args.seed, args.steps)
    bounds_cases(suite)
    rejection_cases(suite)
    suite.finish()


if __name__ == "__main__":
    main()
