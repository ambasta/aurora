#!/usr/bin/env python3
"""Copied-class fixed arrays: native values, exact traps and fail-closed bounds.

Uses the shared full-width observer and source/output preservation checks.
Rejections run with absent and pre-existing output, including under python -O.
This is finite layout, initialization and copy evidence, not a safety proof.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import random
import tempfile

from composed_values import Suite, Trap, observer_self_test, program, require
from packed_values import byte_storage


LEAF = """
class Leaf {
    i64 value;
public:
    Leaf(i64 initial): value(initial) {}
    auto get() const -> i64 { return value; }
    auto set(i64 replacement) -> i64 { value=replacement;return value; }
};
"""
EMPTY = "class Empty{public:Empty(){}auto answer()const->i64{return 42;}};"
HOLDER = """
class Holder {
    array<Leaf,2> items;
public:
    Holder(Leaf first,Leaf second): items{first,second} {}
    auto at(i64 index) const -> Leaf { const Leaf result=items[index];return result; }
    auto set(i64 index,Leaf replacement) -> i64 { items[index]=replacement;return len(items); }
    auto sum() const -> i64 {
        const Leaf first=items[0];const Leaf second=items[1];return first.get()+second.get();
    }
};
"""
SETUP = "Leaf first=Leaf(7);Leaf second=Leaf(35);array<Leaf,2> items={first,second};"
PRESERVED = b"previous-verified-assembly\x00\xff\n"


def reject(suite, name, source, error=True, modules=None):
    for suffix, previous in (("absent output", None), ("saved output", PRESERVED)):
        suite.check(name + ": " + suffix, source, error=error, modules=modules, existing_output=previous)


def local_cases(suite, seed, steps):
    suite.check(
        "local projections are independent of initializer and array copies",
        program(
            SETUP + "const array<Leaf,2> saved=items;first.set(0);second.set(0);"
            "Leaf extracted=items[0];extracted.set(99);items[0]=second;"
            "const Leaf a=saved[0];const Leaf b=saved[1];const Leaf changed=items[0];"
            "if(changed.get()!=0||extracted.get()!=99){return 0;}return a.get()+b.get();",
            LEAF,
        ),
    )
    suite.check(
        "replacement copies a complete named readonly argument",
        program(
            SETUP + "const Leaf replacement=Leaf(42);items[1]=replacement;"
            "const Leaf result=items[1];return consume(result);",
            LEAF,
            "auto consume(Leaf value)->i64{return value.get();}",
        ),
    )
    suite.check(
        "index is evaluated once for read and store",
        program(
            SETUP + "Counter counter=Counter();const Leaf a=items[counter.next()];"
            "items[counter.next()]=first;const Leaf b=items[1];"
            "if(counter.count()!=2||a.get()!=7||b.get()!=7){return 0;}return 42;",
            LEAF + "class Counter{i64 value;public:Counter():value(0){}"
            "auto next()->i64{const i64 old=value;value=value+1;return old;}"
            "auto count()const->i64{return value;}};",
        ),
    )
    suite.check(
        "store snapshots named source after index effects",
        program(
            SETUP + "items[first.set(1)]=first;first.set(9);"
            "const Leaf a=items[0];const Leaf b=items[1];return a.get()+b.get();",
            LEAF,
        ),
        expected=8,
    )
    suite.check(
        "loops branches and shadowing retain independent storage",
        program(
            SETUP + "Leaf replacement=Leaf(21);i64 i=0;while(i<len(items)){"
            "if(i==0){items[i]=replacement;}else{items[i]=replacement;}i=i+1;}"
            "{const array<Leaf,2> items=items;const Leaf first=items[0];"
            "if(first.get()!=21){return 0;}}"
            "const Leaf a=items[0];const Leaf b=items[1];return a.get()+b.get();",
            LEAF,
        ),
    )
    for capacity in (1, 2, 63, 64):
        values = ",".join(["source"] * capacity)
        suite.check(
            f"class array capacity {capacity} complete scalar leaves",
            program(
                f"Leaf source=Leaf(42);array<Leaf,{capacity}> items={{{values}}};"
                f"static_assert(size_of(array<Leaf,{capacity}>)=={capacity * 8});"
                "const i64 identity=type_id(array<Leaf," + str(capacity) + ">);"
                f"if(reflect_size(identity)!={capacity * 8}){{return 0;}}"
                "i64 i=0;while(i<len(items)){const Leaf copy=items[i];"
                "if(copy.get()!=42){return 0;}i=i+1;}return 42;",
                LEAF,
            ),
        )
    rng = random.Random(seed)
    for capacity in (1, 3, 8):
        initial = [rng.randrange(-100, 100) for _ in range(capacity)]
        names = [f"v{i}" for i in range(capacity)]
        body = [f"Leaf {name}=Leaf({value});" for name, value in zip(names, initial)]
        body += [f"array<Leaf,{capacity}> items={{{','.join(names)}}};", f"const array<Leaf,{capacity}> saved=items;"]
        model = initial.copy()
        for step in range(steps):
            index, value = rng.randrange(capacity), rng.randrange(-100, 100)
            body.append(
                f"Leaf replacement{step}=Leaf({value});items[{index}]=replacement{step};replacement{step}.set(999);"
            )
            model[index] = value
        for index, (old, new) in enumerate(zip(initial, model)):
            body.append(
                f"const Leaf old{index}=saved[{index}];const Leaf new{index}=items[{index}];"
                f"if(old{index}.get()!={old}||new{index}.get()!={new}){{return 0;}}"
            )
        body.append("return 42;")
        suite.check(f"seeded independent class array model capacity {capacity}", program("".join(body), LEAF))


def field_cases(suite):
    suite.check(
        "private array constructor and copied containing class boundaries",
        program(
            "Leaf first=Leaf(7);Leaf second=Leaf(35);Holder original=Holder(first,second);"
            "const Holder saved=identity(original);Leaf replacement=Leaf(99);original.set(0,replacement);"
            "replacement.set(0);Leaf extracted=original.at(0);extracted.set(0);"
            "const Leaf stored=original.at(0);if(stored.get()!=99){return 0;}return saved.sum();",
            LEAF + HOLDER,
            "auto identity(Holder value)->Holder{return value;}",
        ),
    )
    suite.check(
        "constructor snapshots class parameters before later mutation",
        program(
            "Leaf source=Leaf(7);Snapshot saved=Snapshot(source,source.set(42));"
            "if(source.get()!=42||saved.get()!=7){return 0;}return saved.marker();",
            LEAF + "class Snapshot{array<Leaf,2> items;i64 code;public:"
            "Snapshot(Leaf source,i64 marker):items{source,source},code(marker){}"
            "auto get()const->i64{const Leaf value=items[1];return value.get();}"
            "auto marker()const->i64{return code;}};",
        ),
    )
    suite.check(
        "private field read and replacement evaluate sibling indices once",
        program(
            "Leaf source=Leaf(7);Leaf next=Leaf(42);Indexed items=Indexed(source);return items.exercise(next);",
            LEAF + "class Indexed{array<Leaf,2> items;i64 index;public:"
            "Indexed(Leaf source):items{source,source},index(0){}"
            "auto next()->i64{const i64 old=index;index=index+1;return old;}"
            "auto exercise(Leaf replacement)->i64{const Leaf old=items[next()];"
            "items[next()]=replacement;const Leaf result=items[1];"
            "if(index!=2||old.get()!=7){return 0;}return result.get();}};",
        ),
    )
    suite.check(
        "readonly method class argument snapshots before source mutation",
        program(
            "Leaf source=Leaf(42);Holder items=Holder(source,source);"
            "items.replace(source,source.set(7));const Leaf result=items.at(1);return result.get();",
            LEAF
            + HOLDER.replace(
                "    auto sum()",
                "    auto replace(Leaf source,i64 changed)->i64{items[1]=source;return changed;}auto sum()",
            ),
        ),
    )
    suite.check(
        "private array len and lexical local shadow",
        program(
            "Leaf source=Leaf(42);Holder holder=Holder(source,source);return holder.shadow();",
            LEAF
            + HOLDER.replace(
                "    auto sum()",
                "    auto shadow()const->i64{const Leaf source=items[0];"
                "const array<Leaf,1> items={source};const Leaf result=items[0];"
                "if(len(items)!=1){return 0;}return result.get();}auto sum()",
            ),
        ),
    )


def layout_cases(suite):
    packed = (
        "class Packed{u8 a;u8 b;u8 c;public:Packed(u8 x,u8 y,u8 z):a(x),b(y),c(z){}"
        "auto code()const->i64{return i64(a)*65536+i64(b)*256+i64(c);}};"
    )
    suite.check(
        "three byte class stride has no rounded gaps or overcopy",
        program(
            "Packed a=Packed(1u8,2u8,3u8);Packed b=Packed(4u8,5u8,6u8);"
            "Packed c=Packed(7u8,8u8,9u8);array<Packed,3> items={a,b,c};"
            "const array<Packed,3> saved=items;items[1]=a;"
            "static_assert(size_of(array<Packed,3>)==9);"
            "const Packed first=items[0];const Packed middle=items[1];const Packed last=items[2];"
            "const Packed old=saved[1];if(first.code()!=66051||middle.code()!=66051||"
            "last.code()!=460809||old.code()!=263430){return 0;}return 42;",
            packed,
        ),
    )
    suite.check(
        "private three byte elements preserve adjacent padded sentinels",
        program(
            "Packed a=Packed(1u8,2u8,3u8);Packed b=Packed(4u8,5u8,6u8);"
            "PackedHolder holder=PackedHolder(a);const PackedHolder saved=holder;holder.set(b);"
            "if(holder.code()!=263430||saved.code()!=66051||!holder.intact()||!saved.intact()){return 0;}return 42;",
            packed + "class PackedHolder{u8 before;array<Packed,3> items;u64 after;public:"
            "PackedHolder(Packed source):before(197u8),items{source,source,source},"
            "after(18446744073709551615u64){}"
            "auto set(Packed source)->i64{items[1]=source;return 0;}"
            "auto code()const->i64{const Packed value=items[1];return value.code();}"
            "auto intact()const->bool{return before==197u8&&after==18446744073709551615u64;}};",
        ),
    )
    wide = "enum class Tag{zero,one};class Wide{u8 byte;bool flag;u64 value;Tag tag;public:"
    wide += "Wide(u8 a,bool b,u64 c,Tag d):byte(a),flag(b),value(c),tag(d){}"
    wide += "auto word()const->u64{if(byte!=255u8||!flag||tag!=Tag::one){return 0u64;}return value;}};"
    suite.check(
        "padded bool enum byte and fullwidth u64 element payload",
        program(
            "Wide empty=Wide(0u8,false,0u64,Tag::zero);"
            "Wide full=Wide(255u8,true,18446744073709551615u64,Tag::one);"
            "array<Wide,2> values={empty,empty};values[1]=full;"
            "const Wide result=values[1];return result.word();",
            wide,
            result="u64",
        ),
        expected=(1 << 64) - 1,
    )
    for element, definitions, construction, leaves, size in (
        ("Empty", EMPTY, "Empty()", 64, 8),
        ("Byte8", byte_storage("Byte8", 8), "Byte8()", 64, 512),
    ):
        body = f"{element} source={construction};array<{element},{leaves}> values={{{','.join(['source'] * leaves)}}};"
        body += f"const array<{element},{leaves}> saved=values;values[63]=source;"
        body += f"static_assert(size_of(array<{element},{leaves}>)=={size});"
        if element == "Byte8":
            body += "source.set(7,255u8);values[63]=source;const Byte8 old=saved[63];const Byte8 changed=values[63];"
            body += "if(old.at(7)!=0u8||changed.at(7)!=255u8){return 0;}return 42;"
        else:
            body += "const Empty value=values[63];return value.answer();"
        suite.check(f"maximum {element} class array payload", program(body, definitions))
        for index in (-1, 64):
            for operation in ("read", "store"):
                invalid = f"{element} source={construction};"
                invalid += f"array<{element},64> values={{{','.join(['source'] * 64)}}};"
                invalid += (
                    f"const {element} result=values[{index}];return 42;"
                    if operation == "read"
                    else f"values[{index}]=source;return 42;"
                )
                suite.check(
                    f"{element} {operation} has exact bounds at {index}",
                    program(invalid, definitions),
                    expected=Trap.BOUNDS,
                )
    suite.check(
        "empty class array private field carries logical initialization",
        program(
            "Empty source=Empty();EmptyHolder value=EmptyHolder(source);const EmptyHolder copied=value;"
            "const Empty result=copied.at(1);return result.answer();",
            EMPTY + "class EmptyHolder{array<Empty,2> values;public:EmptyHolder(Empty a):values{a,a}{}"
            "auto at(i64 i)const->Empty{const Empty result=values[i];return result;}};",
        ),
    )
    suite.check(
        "three class levels plus array reach exact containment depth four",
        program(
            "One one=One();Two two=Two(one);Three source=Three(two);"
            "array<Three,1> items={source};const Three a=items[0];const Two b=a.child;"
            "const One result=b.child;return result.value;",
            "class One{public:i64 value;One():value(42){} };"
            "class Two{public:One child;Two(One source):child(source){} };"
            "class Three{public:Two child;Three(Two source):child(source){} };",
        ),
    )
    for index in (-1, 2, -(1 << 63), (1 << 63) - 1):
        for operation in ("read", "store"):
            body = SETUP + (
                f"const Leaf value=items[{index}];return value.get();"
                if operation == "read"
                else f"items[{index}]=first;return 42;"
            )
            suite.check(f"local {operation} exact bounds index {index}", program(body, LEAF), expected=Trap.BOUNDS)
            body = "Leaf value=Leaf(42);Holder holder=Holder(value,value);"
            body += (
                f"const Leaf result=holder.at({index});return result.get();"
                if operation == "read"
                else f"holder.set({index},value);return 42;"
            )
            suite.check(
                f"field {operation} exact bounds index {index}", program(body, LEAF + HOLDER), expected=Trap.BOUNDS
            )


def module_template_cases(suite):
    modules = {
        "leaf": "export module leaf;namespace values{export " + LEAF + "}",
        "holder": "export module holder;import leaf;export class Collection{"
        "array<values::Leaf,2> items;public:Collection(values::Leaf source):items{source,source}{}"
        "auto at(i64 i)const->values::Leaf{const values::Leaf result=items[i];return result;}};",
    }
    suite.check(
        "directly imported nominal elements across class and function boundaries",
        program(
            "values::Leaf source=values::Leaf(42);Collection collection=Collection(source);"
            "array<values::Leaf,2> local={source,source};const values::Leaf old=local[1];"
            "const values::Leaf result=collection.at(0);if(old.get()!=42){return 0;}return result.get();",
            imports="import leaf;import holder;",
        ),
        modules=modules,
    )
    suite.check(
        "concrete nested template array identity normalizes capacity spelling",
        program(
            "std::pair<i64,u8> inner=std::pair<i64,u8>(40,2u8);"
            "std::pair<std::pair<i64,u8>,u8> source=std::pair<std::pair<i64,u8>,u8>(inner,0u8);"
            "array<std::pair<std::pair<i64,u8>,u8>,02> items={source,source};"
            "const array<std::pair<std::pair<i64,u8>,u8>,2> saved=items;"
            "const std::pair<std::pair<i64,u8>,u8> outer=saved[1];"
            "const std::pair<i64,u8> result=outer.first;return result.first+i64(result.second);",
            imports="import std.utility;",
        ),
    )
    suite.check(
        "fixed class elements inside scalar class template stay concrete",
        program(
            "Leaf source=Leaf(42);Fixed<i64> fixed=Fixed<i64>(source);const Leaf value=fixed.at(1);return value.get();",
            LEAF + "template<Scalar T>class Fixed{array<Leaf,2> items;public:"
            "Fixed(Leaf source):items{source,source}{}"
            "auto at(i64 i)const->Leaf{const Leaf result=items[i];return result;}};",
        ),
    )
    suite.check(
        "fixed concrete array element survives function template substitution",
        program(
            "return fixed<i64>(42);",
            LEAF,
            "template<Scalar T>auto fixed(T number)->i64{Leaf source=Leaf(number);"
            "array<Leaf,1> items={source};const Leaf result=items[0];return result.get();}",
        ),
    )
    reject(
        suite,
        "transitive nominal visibility stays closed",
        program("array<values::Leaf,1> values={};return 42;", imports="import holder;"),
        modules=modules,
    )
    reject(
        suite,
        "private imported element type stays private",
        program("array<Secret,1> values={};return 42;", imports="import secret;"),
        modules={"secret": "export module secret;class Secret{};"},
    )
    reject(
        suite,
        "same layout specialization is not an exact element",
        program(
            "std::pair<i64,u64> first=std::pair<i64,u64>(1,2u64);"
            "std::pair<u64,i64> other=std::pair<u64,i64>(2u64,1);"
            "array<std::pair<i64,u64>,1> values={other};return 42;",
            imports="import std.utility;",
        ),
    )
    reject(
        suite,
        "std array Scalar wrapper still rejects copied classes",
        program("std::array<Leaf,2> values=std::array<Leaf,2>();return 42;", LEAF, imports="import std.array;"),
    )
    reject(
        suite,
        "Value class template substitution cannot create class element storage",
        program(
            "Generic<Leaf> values=Generic<Leaf>();return 42;",
            LEAF + "template<Value T>class Generic{array<T,2> items;public:Generic():items{}{} };",
        ),
    )
    reject(
        suite,
        "Value function substitution cannot create class element storage",
        program(
            "Leaf source=Leaf(42);return generic<Leaf>(source);",
            LEAF,
            "template<Value T>auto generic(T source)->i64{array<T,1> values={source};return 42;}",
        ),
    )


def rejection_cases(suite):
    bodies = {
        "missing complete elements": "Leaf source=Leaf(42);array<Leaf,2> values={source};return 42;",
        "extra elements": "Leaf source=Leaf(42);array<Leaf,1> values={source,source};return 42;",
        "class arrays have no zero initialization": "array<Leaf,1> values={};return 42;",
        "class initializer temporary": "array<Leaf,1> values={Leaf(42)};return 42;",
        "class initializer scalar": "array<Leaf,1> values={42};return 42;",
        "class assignment temporary": SETUP + "items[0]=Leaf(42);return 42;",
        "class assignment indexed temporary": SETUP + "items[0]=items[1];return 42;",
        "class assignment scalar": SETUP + "items[0]=42;return 42;",
        "wrong array copy capacity": SETUP + "array<Leaf,1> values=items;return 42;",
        "wrong array copy nominal identity": SETUP + "array<Other,2> values=items;return 42;",
        "indexed method receiver": SETUP + "return items[0].get();",
        "indexed field mutation": SETUP + "items[0].value=42;return 42;",
        "class element is not scalar": SETUP + "return items[0];",
        "const local array mutation": SETUP.replace("array<Leaf,2>", "const array<Leaf,2>")
        + "items[0]=first;return 42;",
        "whole array assignment": SETUP + "items=items;return 42;",
        "whole array function argument": SETUP + "return consume(items);",
        "wrong index type": SETUP + "const Leaf value=items[true];return value.get();",
        "wrong nominal initializer": "Other source=Other(42);array<Leaf,1> items={source};return 42;",
        "wrong nominal replacement": SETUP + "Other source=Other(42);items[0]=source;return 42;",
        "capacity above64": "Leaf source=Leaf(42);array<Leaf,65> items={source};return 42;",
        "capacity zero": "array<Leaf,0> items={};return 42;",
        "enum array": "array<Status,1> items={Status::yes};return 42;",
        "nested builtin array": "array<array<i64,1>,1> items={};return 42;",
        "resource array": "array<builtin::OwnedBytes,1> items={};return 42;",
        "authority array": "array<builtin::ConsoleSession,1> items={};return 42;",
        "readonly span array": "array<builtin::span<const u8>,1> items={};return 42;",
        "source reference array": "array<ref<i64>,1> items={};return 42;",
        "element method temporary initializer": SETUP + "array<Leaf,1> values={make(first)};return 42;",
    }
    definitions = LEAF + "class Other{i64 value;public:Other(i64 n):value(n){} };enum class Status{yes,no};"
    helpers = "auto consume(Leaf value)->i64{return value.get();}auto make(Leaf value)->Leaf{return value;}"
    for name, body in bodies.items():
        reject(suite, name, program(body, definitions, helpers))
    reject(
        suite,
        "empty payload local still requires complete named initializers",
        program("array<Empty,64> values={};return 42;", EMPTY),
    )
    reject(
        suite,
        "empty payload field cannot use implicit zero initialization",
        program("return 42;", EMPTY + "class Holder{array<Empty,2> values;public:Holder():values{}{} };"),
    )
    reject(
        suite,
        "scalar field nonempty braces remain unsupported",
        program("return 42;", "class Holder{array<i64,2> values;public:Holder():values{1,2}{} };"),
    )
    fields = {
        "public class array field": HOLDER.replace("    array<Leaf,2> items;", "public:array<Leaf,2> items;"),
        "private class array zero initialization": HOLDER.replace("items{first,second}", "items{}"),
        "missing constructor element": HOLDER.replace("items{first,second}", "items{first}"),
        "extra constructor element": HOLDER.replace("items{first,second}", "items{first,second,first}"),
        "constructor element temporary": HOLDER.replace("items{first,second}", "items{Leaf(7),second}"),
        "constructor element index": HOLDER.replace("items{first,second}", "items{items[0],second}"),
        "const receiver mutation": HOLDER.replace(
            "auto set(i64 index,Leaf replacement) -> i64", "auto set(i64 index,Leaf replacement) const -> i64"
        ),
        "receiverless class array constructor": "class Missing{array<Leaf,1> items;};",
        "duplicate class array initialization": HOLDER.replace(
            "items{first,second}", "items{first,second},items{second,first}"
        ),
    }
    for name, definition in fields.items():
        reject(suite, name, program("return 42;", LEAF + definition))
    reject(
        suite,
        "private field inaccessible externally",
        program(
            "Leaf source=Leaf(42);Holder holder=Holder(source,source);"
            "const Leaf value=holder.items[0];return value.get();",
            LEAF + HOLDER,
        ),
    )
    for name, definition, element, capacity, setup in (
        (
            "nonbyte leaves exceed64",
            "class Two{public:i64 a;i64 b;Two():a(0),b(0){} };",
            "Two",
            33,
            "Two source=Two();",
        ),
        ("byte leaves exceed512", byte_storage("Byte9", 9), "Byte9", 57, "Byte9 source=Byte9();"),
        (
            "canonical padded extent exceeds520",
            "class Padded{public:u8 a;i64 b;Padded():a(0u8),b(0){} };",
            "Padded",
            33,
            "Padded source=Padded();",
        ),
        (
            "containment depth includes local array",
            "class One{public:i64 a;One():a(0){} };"
            "class Two{One a;public:Two(One x):a(x){} };class Three{Two a;public:Three(Two x):a(x){} };"
            "class Four{Three a;public:Four(Three x):a(x){} };",
            "Four",
            1,
            "One one=One();Two two=Two(one);Three three=Three(two);Four source=Four(three);",
        ),
    ):
        for query in ("field_count", "size_of", "type_id"):
            reject(
                suite,
                name + " metadata query " + query,
                program(f"return {query}(array<{element},{capacity}>);", definition),
                error=("bound", "limit", "leaf", "leaves", "depth", "bytes", "64", "512", "520"),
            )
        values = ",".join(["source"] * capacity)
        reject(
            suite,
            name,
            program(setup + f"array<{element},{capacity}> values={{{values}}};return 42;", definition),
            error=("bound", "limit", "leaf", "leaves", "depth", "bytes", "64", "512", "520"),
        )
    owner = "class Owner{builtin::OwnedBytes bytes;public:"
    owner += "Owner(builtin::ByteRegion region,builtin::OwnedBytes value):bytes(move(value)){} };"
    for query in ("field_count", "size_of", "type_id"):
        reject(
            suite,
            "owning class array metadata query " + query,
            program(f"return {query}(array<Owner,1>);", owner),
            error=("own", "resource", "copied"),
        )
    suite.check(
        "valid class-array reflection preserves nominal identity and canonical extent",
        program(
            "if (size_of(array<Leaf,2>) != 16 || field_count(array<Leaf,2>) != 0) { return 0; }"
            "if (type_id(array<Leaf,02>) != type_id(array<Leaf,2>)) { return 1; }"
            "if (type_id(array<Leaf,2>) == type_id(array<Other,2>)) { return 2; } return 42;",
            LEAF + "class Other { i64 value; public: Other(i64 n):value(n){} };",
        ),
    )
    reject(
        suite,
        "class elements cannot own resources",
        program("array<Owner,1> values={};return 42;", owner),
        error=("own", "resource", "copied"),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    parser.add_argument("--seed", type=int, default=64064)
    parser.add_argument("--steps", type=int, default=12)
    parser.add_argument("--keep-going", action="store_true")
    args = parser.parse_args()
    require(1 <= args.steps <= 64, "steps must be from 1 through 64")
    compiler = args.compiler.resolve()
    print(f"compiler_sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()}", flush=True)
    with tempfile.TemporaryDirectory(prefix="aurora-class-arrays-") as temporary:
        suite = Suite(Path(temporary), compiler, args.keep_going)
        observer_self_test(suite)
        local_cases(suite, args.seed, args.steps)
        field_cases(suite)
        layout_cases(suite)
        module_template_cases(suite)
        rejection_cases(suite)
        require(not suite.failures, "\n".join(suite.failures))
        print(f"PASS class arrays: {suite.count} cases, {suite.rejections} rejections, {suite.traps} exact traps")


if __name__ == "__main__":
    main()
