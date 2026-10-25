#!/usr/bin/env python3
"""Copied-class fixed arrays: native values, exact traps and fail-closed bounds.

Cases are data for the shared native runner (native_runner.py). This is finite
layout, initialization and copy evidence, not a safety proof.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import random

from composed_values import Suite, Trap, program, require
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


def reject(suite, name, source, error=True, modules=None):
    suite.check(name, source, error=error, modules=modules)


def local_cases(suite, seed, steps):
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
    reject(
        suite,
        "transitive nominal visibility stays closed",
        program("array<values::Leaf,1> values={};return 42;", imports="import holder;"),
        modules=modules,
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
    args = parser.parse_args()
    require(1 <= args.steps <= 64, "steps must be from 1 through 64")
    suite = Suite(args.compiler, "class arrays")
    suite.load(Path(__file__).with_suffix(".cases"), EMPTY=EMPTY, HOLDER=HOLDER, LEAF=LEAF, SETUP=SETUP)
    local_cases(suite, args.seed, args.steps)
    field_cases(suite)
    layout_cases(suite)
    module_template_cases(suite)
    rejection_cases(suite)
    suite.finish()


if __name__ == "__main__":
    main()
