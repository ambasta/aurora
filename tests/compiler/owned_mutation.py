#!/usr/bin/env python3
"""Direct owned class-field replacement and synchronous nested receivers.

Reuses the full-width native observer, exact trap-site oracle and rejection
artifact checks. No unchecked pointer, escaping reference or new test controller.
"""

import argparse
import hashlib
from pathlib import Path
import tempfile

from composed_values import Suite, Trap, program
from packed_values import byte_storage


LEAF = """
class Leaf {
    i64 value;
public:
    Leaf(i64 initial): value(initial) {}
    auto get() const -> i64 { return value; }
    auto set(i64 replacement) -> i64 { value = replacement; return value; }
    auto exchange(Leaf replacement) -> Leaf {
        const Leaf previous = Leaf(value);
        value = replacement.get();
        return previous;
    }
};
"""
HOLDER = """
class Holder {
public:
    u8 before;
    Leaf item;
    u64 after;
    Holder(Leaf initial): before(197u8), item(initial), after(18446744073709551615u64) {}
};
"""
SETUP = "Leaf value=Leaf(7);Holder holder=Holder(value);Leaf replacement=Leaf(42);"


def positive_cases(suite):
    definitions = LEAF + HOLDER
    suite.check(
        "direct replacement is a complete independent copy",
        program(
            SETUP + "holder.item=replacement;replacement.set(3);"
            "if(holder.before!=197u8||holder.after!=18446744073709551615u64){return 0;}"
            "return holder.item.get();",
            definitions,
        ),
    )
    suite.check(
        "nested mutation updates parent but not original or copied parent",
        program(
            SETUP + "const Holder saved=holder;holder.item.set(42);"
            "if(value.get()!=7||saved.item.get()!=7){return 0;}return holder.item.get();",
            definitions,
        ),
    )
    suite.check(
        "copied method result may be assigned back in a separate statement",
        program(
            SETUP + "const Leaf old=holder.item.exchange(replacement);"
            "if(holder.item.get()!=42||old.get()!=7){return 0;}holder.item=old;"
            "return holder.item.get()+35;",
            definitions,
        ),
    )
    suite.check(
        "readonly argument is independent even when sourced from root",
        program(
            SETUP + "return holder.item.inspect(holder,holder.item.set(5));",
            LEAF.replace(
                "    auto exchange",
                """    auto inspect(Holder snapshot, i64 delta) -> i64 {
        const Leaf old = snapshot.item;
        value = value + delta;
        return old.get() * 100 + value;
    }
    auto exchange""",
            )
            + HOLDER,
        ),
        expected=710,
    )
    suite.check(
        "result binding shadow preserves captured root and snapshot timing",
        program(
            SETUP + "i64 total=0;{Holder holder=holder.item.copy_holder(holder,holder.item.set(8));"
            "total=holder.item.get();}return total+holder.item.get();",
            LEAF.replace(
                "    auto exchange",
                """    auto copy_holder(Holder snapshot, i64 changed) -> Holder {
        value = changed;
        return snapshot;
    }
    auto exchange""",
            )
            + HOLDER,
        ),
        expected=15,
    )
    suite.check(
        "later scalar replacement preserves field storage identity",
        program(
            SETUP + "return holder.item.inspect(holder,holder.replace(replacement));",
            LEAF.replace(
                "    auto exchange",
                """    auto inspect(Holder snapshot, i64 delta) -> i64 {
        const Leaf old = snapshot.item;
        value = value + delta;
        return old.get() * 100 + value;
    }
    auto exchange""",
            )
            + HOLDER.replace(
                "    Holder(Leaf initial)",
                "    auto replace(Leaf next)->i64{item=next;return 1;}\n    Holder(Leaf initial)",
            ),
        ),
        expected=743,
    )
    suite.check(
        "nested scalar-only method with independent class result",
        program(
            SETUP + "const Leaf copied=holder.item.plus(35);holder.item.set(0);return copied.get();",
            LEAF.replace(
                "    auto exchange",
                """    auto plus(i64 delta) const -> Leaf {
        const Leaf result = Leaf(value + delta);
        return result;
    }
    auto exchange""",
            )
            + HOLDER,
        ),
    )
    private = """
class Owner {
    Leaf item;
public:
    Owner(Leaf source): item(source) {}
    auto replace(Leaf replacement) -> i64 { item = replacement; return item.get(); }
    auto set(i64 replacement) -> i64 { return item.set(replacement); }
    auto get() const -> i64 { return item.get(); }
    auto swap(Leaf replacement) -> Leaf { const Leaf old = item.exchange(replacement); return old; }
};
"""
    suite.check(
        "private implicit owned field replacement and receiver",
        program(
            "Leaf initial=Leaf(7);Owner owner=Owner(initial);Leaf next=Leaf(22);"
            "owner.replace(next);next.set(3);owner.set(42);return owner.get();",
            LEAF + private,
        ),
    )
    suite.check(
        "private nested combined method result",
        program(
            "Leaf initial=Leaf(42);Owner owner=Owner(initial);Leaf next=Leaf(22);"
            "const Leaf old=owner.swap(next);if(owner.get()!=22){return 0;}return old.get();",
            LEAF + private,
        ),
    )
    suite.check(
        "readonly parameter permits const nested call",
        program(
            SETUP + "return read_holder(holder)+35;",
            definitions,
            "auto read_holder(Holder input)->i64{return input.item.get();}",
        ),
    )
    suite.check(
        "local binding shadows private owned receiver field",
        program(
            "Leaf initial=Leaf(7);Owner owner=Owner(initial);return owner.shadow();",
            LEAF
            + private.replace(
                "    auto get()",
                """    auto shadow() -> i64 {
        Leaf item = Leaf(42);
        item.set(42);
        return item.get();
    }
    auto get()""",
            ),
        ),
    )
    suite.check(
        "replacement in branch and loop preserves initialized root",
        program(
            SETUP + "i64 index=0;while(index<3){if(index==1){holder.item=replacement;}"
            "else{holder.item=value;}index=index+1;}holder.item=replacement;return holder.item.get();",
            definitions,
        ),
    )
    empty = """
class Empty { public: Empty() {} auto answer() -> i64 { return 42; } };
class EmptyHolder {
public:
    u8 before;
    Empty first;
    Empty second;
    u64 after;
    EmptyHolder(Empty initial): before(19u8), first(initial), second(initial), after(77u64) {}
};
"""
    suite.check(
        "distinct logical empty fields share no mutable payload",
        program(
            "Empty empty=Empty();EmptyHolder holder=EmptyHolder(empty);holder.first=empty;holder.second=empty;"
            "if(holder.before!=19u8||holder.after!=77u64){return 0;}return holder.second.answer();",
            empty,
        ),
    )
    packed = """
enum class Tag { zero, one };
class Packed {
    u8 byte;
    u64 word;
    bool flag;
    Tag tag;
public:
    Packed(u8 a,u64 b,bool c,Tag d):byte(a),word(b),flag(c),tag(d){}
    auto check()const->u64{if(byte!=255u8||!flag||tag!=Tag::one){return 0u64;}return word;}
};
class PackedHolder {
public:
    u8 before;
    Packed item;
    u8 after;
    PackedHolder(Packed initial):before(197u8),item(initial),after(223u8){}
};
"""
    suite.check(
        "canonical packed bytes bool enum and full u64 remain exact",
        program(
            "Packed old=Packed(0u8,0u64,false,Tag::zero);PackedHolder holder=PackedHolder(old);"
            "const Packed replacement=Packed(255u8,18446744073709551615u64,true,Tag::one);"
            "holder.item=replacement;if(holder.before!=197u8||holder.after!=223u8){return 0u64;}"
            "return holder.item.check();",
            packed,
            result="u64",
        ),
        expected=(1 << 64) - 1,
    )
    sector = (
        byte_storage("Sector", 512)
        + """
class Device {
    Sector stored;
public:
    Device(Sector input):stored(input){}
    auto replace(Sector input)->i64{stored=input;return 0;}
    auto write_byte(i64 offset,u8 value)->u8{return stored.set(offset,value);}
    auto read_byte(i64 offset)const->u8{return stored.at(offset);}
};
"""
    )
    suite.check(
        "all 512 bytes copied replaced and independently mutated",
        program(
            "Sector source=Sector();i64 i=0;while(i<512){source.set(i,u8((i*73+19)%256));i=i+1;}"
            "Device device=Device(source);Sector zero=Sector();device.replace(zero);i=0;"
            "while(i<512){if(device.read_byte(i)!=0u8){return 0;}i=i+1;}device.replace(source);"
            "i=0;while(i<512){device.write_byte(i,u8((i*73+20)%256));"
            "if(source.at(i)!=u8((i*73+19)%256)||device.read_byte(i)!=u8((i*73+20)%256)){return 0;}i=i+1;}"
            "return 42;",
            sector,
        ),
    )
    for index in (-1, 512):
        suite.check(
            f"nested checked array trap {index}",
            program(
                f"Sector value=Sector();Device device=Device(value);return i64(device.write_byte({index},255u8));",
                sector,
            ),
            expected=Trap.BOUNDS,
        )
    suite.check(
        "real Sector512 consumer no raw storage duplication",
        program(
            "storage::Sector512 initial=storage::Sector512();Device device=Device(initial);"
            "device.replace(initial);device.write_byte(511,42u8);return i64(device.read_byte(511));",
            """
class Device {
    storage::Sector512 stored;
public:
    Device(storage::Sector512 source):stored(source){}
    auto replace(storage::Sector512 source)->i64{stored=source;return 0;}
    auto write_byte(i64 offset,u8 value)->std::ByteWriteStatus{return stored.write_byte(offset,value);}
    auto read_byte(i64 offset)const->u8{
        const std::ByteReadResult result=stored.read_byte(offset);return u8(result.value_or(0u64));
    }
};
""",
            imports="import std.binary;import std.binary_buffer;import storage.sector;",
        ),
    )


def rejection_cases(suite):
    definitions = LEAF + HOLDER
    bodies = [
        (
            "readonly root replacement",
            SETUP.replace("Holder holder", "const Holder holder") + "holder.item=replacement;return 42;",
            "mutable",
        ),
        (
            "readonly root mutable nested method",
            SETUP.replace("Holder holder", "const Holder holder") + "return holder.item.set(42);",
            "mutable",
        ),
        ("temporary nested receiver", "Leaf value=Leaf(7);return Holder(value).item.get();", "receiver"),
        ("temporary class replacement", SETUP + "holder.item=Leaf(42);return 42;", "complete local"),
        ("direct projection replacement", SETUP + "holder.item=holder.item;return 42;", "complete local"),
        (
            "class result replacement requires explicit local",
            SETUP + "holder.item=holder.item.exchange(replacement);return 42;",
            "complete local",
        ),
        ("whole local reassignment remains rejected", SETUP + "holder=holder;return 42;", "scalar"),
        ("nested scalar mutation remains rejected", SETUP + "holder.item.value=42;return 42;", "assignment"),
        ("private child remains private", SETUP + "return holder.item.hidden();", "private"),
        ("private owned field remains private", SETUP + "return holder.item.get();", "private"),
        ("scalar field is not a nested receiver", SETUP + "return holder.before.get();", "class field"),
        (
            "same-layout nominal replacement rejected",
            SETUP + "Other other=Other(42);holder.item=other;return 42;",
            "expected",
        ),
    ]
    for name, body, diagnostic in bodies:
        variant = definitions
        if name == "private child remains private":
            variant = variant.replace("    i64 value;", "    i64 value;auto hidden()const->i64{return value;}")
        if name == "private owned field remains private":
            variant = variant.replace("    Leaf item;", "private:Leaf item;public:")
        if name == "same-layout nominal replacement rejected":
            variant += "class Other{ i64 value;public:Other(i64 n):value(n){} };"
        for existing in (None, b"prior-output-must-survive"):
            suite.check(name, program(body, variant), error=diagnostic, existing_output=existing)
    for action in ("input.item=value;", "input.item.set(42);"):
        suite.check(
            "readonly function parameter cannot supply mutable field",
            program(
                SETUP + "return bad(holder,replacement);",
                definitions,
                f"auto bad(Holder input,Leaf value)->i64{{{action}return 42;}}",
            ),
            error="mutable",
        )
    for action in ("item=value;", "item.set(42);"):
        suite.check(
            "const implicit receiver cannot supply mutable field",
            program(
                "return 42;",
                LEAF + "class Owner{Leaf item;public:Owner(Leaf value):item(value){}"
                f"auto bad(Leaf value)const->i64{{{action}return 42;}}}};",
            ),
            error="const" if "=" in action else "mutable",
        )
    deeper = definitions + "class Outer{public:Holder middle;Outer(Holder value):middle(value){} };"
    for body in ("return outer.middle.item.get();", "outer.middle.item=replacement;return 42;"):
        suite.check(
            "deeper path remains rejected",
            program(SETUP + "Outer outer=Outer(holder);" + body, deeper),
            error=("receiver", "assignment"),
        )
    suite.check(
        "private array replacement remains rejected",
        program(
            "return 42;",
            byte_storage("Bytes", 3).replace(
                "auto at(",
                "auto replace()->i64{builtin::array<u8,3> values={0u8,0u8,0u8};data=values;return 42;}auto at(",
            ),
        ),
        error="aggregate",
    )
    modules = {
        "inner": "export module inner;export " + LEAF,
        "outer": "export module outer;import inner;export " + HOLDER,
    }
    suite.check(
        "transitive class visibility cannot be widened by nested call",
        program(
            "return 42;", helpers="auto hidden(Holder input)->i64{return input.item.get();}", imports="import outer;"
        ),
        modules=modules,
        error=("visible", "import"),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    print(f"compiler_sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()}", flush=True)
    with tempfile.TemporaryDirectory(prefix="aurora-owned-mutation-") as temporary:
        suite = Suite(Path(temporary), compiler)
        positive_cases(suite)
        rejection_cases(suite)
        print(f"PASS owned mutation: {suite.count} cases, {suite.rejections} rejections, {suite.traps} exact traps")


if __name__ == "__main__":
    main()
