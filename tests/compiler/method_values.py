#!/usr/bin/env python3
"""Copied ordinary-method parameters (M022): native results, traps and rejections.

Cases are data on one native_runner.Suite: complete 64-bit results, exact trap
sites and diagnostic fragments (matched case-insensitively). Model expectations
use independent Python lists, not compiler output.

Run: python3 -O tests/compiler/method_values.py build/aurorac
"""

from __future__ import annotations

import argparse
from pathlib import Path
import random
import tempfile

from native_runner import LIBRARY, ROOT, Suite, Trap, require, run

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
    return "module app;" + imports + definitions + helpers + f"auto test()->{result}{{{body}}}"


def lit(scalar, value):
    if scalar == "bool":
        return "true" if value else "false"
    return str(value) + (scalar if scalar in ("u64", "u8") else "")


class MethodSuite(Suite):
    """`equivalent_source` must compile to the same assembly as the checked source."""

    def check(self, name, source, expected=42, error=None, *, equivalent_source=None, **options):
        if equivalent_source is not None:
            options["inspect"] = lambda text: self.same_assembly(name, text, equivalent_source)
        super().check(name, source, expected, error, **options)

    def same_assembly(self, name, text, equivalent):
        with tempfile.TemporaryDirectory(prefix="named-") as directory:
            source, output = Path(directory) / "named.au", Path(directory) / "named.s"
            source.write_text(equivalent)
            named = run([self.compiler, "--module-root", LIBRARY, source, "-o", output], 45)
            require(named.returncode == 0, name + ": named-local comparison failed: " + repr(named.stderr))
            require(output.read_text() == text, name + ": direct return differs from named-local assembly")


def native_cases(suite):
    for label, body, helpers in (
        ("constructor temporary class argument", "return receiver.inspect(Counter(42));", ""),
        (
            "function result temporary class argument",
            "return receiver.inspect(make());",
            "auto make()->Counter{Counter x=Counter(42);return x;}",
        ),
        ("method result temporary class argument", "return receiver.inspect(receiver.copy(source));", ""),
    ):
        suite.check(label, p("Counter source=Counter(42);Counter receiver=Counter(0);" + body, COUNTER, helpers))
    for receiver_const in (False, True):
        for argument_const in (False, True):
            for result_const in (False, True):
                suite.check(
                    f"readonly copy receiver={receiver_const} argument={argument_const} result={result_const}",
                    p(
                        f"{'const ' if receiver_const else ''}Counter receiver=Counter(0);"
                        f"{'const ' if argument_const else ''}Counter source=Counter(42);"
                        f"{'const ' if result_const else ''}Counter copied=receiver.copy(source);"
                        "if(receiver.inspect(source)!=42){return 1;}"
                        + ("if(copied.add(1)!=43){return 2;}" if not result_const else "")
                        + "return source.get();",
                        COUNTER,
                    ),
                )
    six = (
        "class Six{ i64 value; public:Six(i64 n):value(n){}"
        "auto mix(Counter a,i64 n,Counter b,Status state,u64 big,u8 byte)->Counter{"
        "if(n!=7){const Counter failed=Counter(1);return failed;}"
        "if(state!=Status::ready){const Counter failed=Counter(2);return failed;}"
        "if(big!=18446744073709551615u64){const Counter failed=Counter(3);return failed;}"
        "if(byte!=255u8){const Counter failed=Counter(4);return failed;}"
        "value=value+1;const Counter answer=Counter(a.get()+b.get()+value);return answer;}"
        "auto check(bool yes,Counter a,u8 byte,Counter b,u64 big,Status state)const->bool{"
        "if(!yes){return false;}if(byte!=255u8){return false;}"
        "if(big!=18446744073709551615u64){return false;}"
        "if(state!=Status::ready){return false;}return a.get()+b.get()==41;} };"
    )
    suite.check(
        "six mixed scalar enum class parameters with class result",
        p(
            "Six receiver=Six(0);Counter a=Counter(20);Counter b=Counter(21);"
            "Counter result=receiver.mix(a,7,b,Status::ready,18446744073709551615u64,255u8);"
            "if(!receiver.check(true,a,255u8,b,18446744073709551615u64,Status::ready)){return 9;}"
            "return result.get();",
            ENUMS + COUNTER + six,
        ),
    )
    order = COUNTER.replace(
        "};",
        "auto order(Counter before,i64 first,Counter between,i64 second,Counter after,bool yes)->i64{"
        "if(before.get()!=1){return 1;}if(first!=2){return 2;}if(between.get()!=2){return 3;}"
        "if(second!=3){return 4;}if(after.get()!=3){return 5;}if(!yes){return 6;}"
        "if(value!=3){return 7;}value=99;"
        "if(before.get()!=1){return 8;}if(after.get()!=3){return 9;}return 42;}};",
    )
    suite.check(
        "class snapshots scalar effects and receiver acquire left to right",
        p(
            "Counter source=Counter(1);return source.order(source,source.add(1),source,source.add(1),source,true);",
            order,
        ),
    )
    sibling = (
        "class Sibling{i64 value;auto take(Counter source,i64 extra)const->Counter{"
        "const Counter result=Counter(source.get()+extra+value);return result;}"
        "auto advance(Counter source)->Counter{value=value+1;const Counter result=take(source,1);return result;}"
        "public:Sibling(i64 n):value(n){}auto get(Counter source)const->Counter{"
        "const Counter result=take(source,2);return result;}"
        "auto change(Counter source)->Counter{const Counter result=advance(source);return result;}};"
    )
    for method in ("get", "change"):
        suite.check(
            "private sibling copied argument and result " + method,
            p(
                f"Counter source=Counter(20);Sibling receiver=Sibling(20);Counter result=receiver.{method}(source);"
                "source.set(99);return result.get();",
                COUNTER + sibling,
            ),
        )
    for scalar, value in (("i64", -(1 << 63)), ("u64", (1 << 64) - 1), ("u8", 255), ("bool", True)):
        definition = (
            f"class Value{{{scalar} item;public:Value({scalar} n):item(n){{}}"
            f"auto get()const->{scalar}{{return item;}}auto copy(Value source)const->Value{{return source;}}}};"
        )
        suite.check(
            "full-width copied method parameter " + scalar,
            p(
                f"Value value=Value({lit(scalar, value)});const Value result=value.copy(value);return result.get();",
                definition,
                result=scalar,
            ),
            expected=int(value),
        )
    direct = p(
        "std::array<u8,3> bytes=std::array<u8,3>();bytes.set(0,255u8);bytes.set(2,40u8);"
        "Empty empty=Empty();Packet source=Packet(7u8,bytes,Status::ready,empty,2u8);"
        "const Receiver receiver=Receiver(source);Packet result=receiver.copy(source);bytes.set(2,0u8);"
        "std::array<u8,3> changed=result.data;changed.set(2,1u8);"
        "const std::array<u8,3> saved=result.data;"
        "if(saved.at(0)!=255u8){return 1;}if(result.state!=Status::ready){return 2;}"
        "if(result.head!=7u8){return 3;}const Empty zero=result.zero;if(zero.answer()!=42){return 4;}"
        "result.data.set(2,1u8);source.data.set(2,0u8);const Packet again=receiver.copy(source);"
        "const std::array<u8,3> retained=again.data;if(retained.at(2)!=40u8){return 5;}"
        "return i64(saved.at(2))+i64(result.tail);",
        ENUMS + EMPTY + "class Packet{public:u8 head;std::array<u8,3> data;Status state;Empty zero;u8 tail;"
        "Packet(u8 h,std::array<u8,3> b,Status s,Empty e,u8 t):head(h),data(b),state(s),zero(e),tail(t){} };"
        "class Receiver{Packet item;public:Receiver(Packet source):item(source){}"
        "auto copy(Packet value)const->Packet{return item;}};",
        imports="import std.array;",
    )
    suite.check(
        "packed nested enum empty and private array payload all copy",
        direct.replace("return item;", "return value;").replace("if(retained.at(2)!=40u8)", "if(retained.at(2)!=0u8)"),
    )
    suite.check(
        "direct receiver field copies packed nested enum empty and private array payload",
        direct,
        equivalent_source=direct.replace("return item;", "const Packet result=item;return result;"),
    )
    suite.check(
        "qualified wrapper self means exact active instance and bare array stays storage",
        p(
            "std::array<u8,1> one=std::array<u8,1>();std::array<u64,3> three=std::array<u64,3>();"
            "const std::array<u8,1> saved1=one.copy(one);const std::array<u64,3> saved3=three.copy(three);"
            "static_assert(size_of(std::array<u8,1>)==1);static_assert(size_of(std::array<u64,3>)==24);"
            "if(saved1.get(0)!=0u8){return 1;}if(saved3.get(2)!=0u64){return 2;}return 42;",
            "namespace std{template<Scalar T,i64 N>class array{array<T,N> elements;public:array():elements{}{}"
            "auto get(i64 index)const->T{return elements[index];}"
            "auto copy(std::array source)const->std::array{const std::array result=source;return result;}};}",
        ),
        # Its own root-level std namespace; a pack would nest it and import std.array beside it.
        standalone=True,
    )

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

    holder = "class Holder{public:Counter item;Holder(Counter source):item(source){}};"
    field_direct = p(
        "Counter source=Counter(42);Holder holder=Holder(source);Counter result=forward(holder,source);"
        "holder.item.set(7);source.set(9);return result.get();",
        COUNTER + holder,
        "auto forward(Holder holder,Counter source)->Counter{return holder.item.copy(source);}",
    )
    suite.check(
        "direct public field method result matches named-local assembly",
        field_direct,
        equivalent_source=field_direct.replace(
            "return holder.item.copy(source);", "const Counter result=holder.item.copy(source);return result;"
        ),
    )
    for mutable, method in ((False, "copy"), (True, "replace")):
        qualifier = "" if mutable else "const"
        direct = p(
            "Counter initial=Counter(42);Counter source=Counter(7);Holder holder=Holder(initial);"
            "Counter result=holder.forward(source);source.set(9);"
            + f"if(!holder.intact()||holder.get()!={7 if mutable else 42}){{return 0;}}return result.get();",
            COUNTER + "class Holder{u8 first;Counter item;u8 last;public:"
            "Holder(Counter source):first(13u8),item(source),last(29u8){}"
            "auto intact()const->bool{return first==13u8&&last==29u8;}"
            "auto get()const->i64{return item.get();}"
            + f"auto forward(Counter source){qualifier}->Counter{{return item.{method}(source);}}}};",
        )
        suite.check(
            "direct padded private field method result " + method,
            direct,
            expected=42 if mutable else 7,
            equivalent_source=direct.replace(
                f"return item.{method}(source);", f"const Counter result=item.{method}(source);return result;"
            ),
        )
    direct = p(
        "Counter result=forward();return result.get();",
        COUNTER.replace(
            "};",
            "auto merge(Counter before,i64 ignored,Counter after)->Counter{"
            "value=99;return Counter(before.get()+after.get());}};",
        )
        + holder,
        "auto forward()->Counter{Counter source=Counter(20);Holder holder=Holder(source);"
        "return holder.item.merge(source,source.add(2),source);}",
    )
    suite.check(
        "direct field method preserves left-to-right snapshots",
        direct,
        equivalent_source=direct.replace(
            "return holder.item.merge(source,source.add(2),source);",
            "const Counter result=holder.item.merge(source,source.add(2),source);return result;",
        ),
    )
    direct = p(
        "Counter source=Counter(0);Holder holder=Holder(source);Counter result=holder.forward();return result.get();",
        COUNTER + "class Holder{Counter item;public:Holder(Counter source):item(source){}"
        "auto forward()const->Counter{builtin::array<u8,1> bytes={42u8};"
        "const builtin::span<const u8> view=borrow_bytes(bytes);Counter source=Counter(i64(view.at(0)));"
        "return item.copy(source);}};",
    )
    suite.check(
        "direct field method closes live array and span",
        direct,
        equivalent_source=direct.replace(
            "return item.copy(source);", "const Counter result=item.copy(source);return result;"
        ),
    )
    direct = p(
        "Empty source=Empty();Holder holder=Holder(source);Empty result=forward(holder,source);return result.answer();",
        EMPTY.replace("};", "auto copy(Empty source)const->Empty{return source;}};")
        + "class Holder{public:Empty item;Holder(Empty source):item(source){}};",
        "auto forward(Holder holder,Empty source)->Empty{return holder.item.copy(source);}",
    )
    suite.check(
        "direct empty field method result keeps logical completeness",
        direct,
        equivalent_source=direct.replace(
            "return holder.item.copy(source);", "const Empty result=holder.item.copy(source);return result;"
        ),
    )
    direct = p(
        "Empty source=Empty();const Holder holder=Holder(source);Empty result=holder.copy();return result.answer();",
        EMPTY + "class Holder{Empty item;public:Holder(Empty source):item(source){}"
        "auto copy()const->Empty{return item;}};",
    )
    suite.check(
        "direct empty receiver field result keeps logical completeness",
        direct,
        equivalent_source=direct.replace("return item;", "const Empty result=item;return result;"),
    )
    for mutable in (False, True):
        change = (
            "builtin::array<u8,1> bytes={1u8};const builtin::span<const u8> view=borrow_bytes(bytes);"
            "item.add(i64(view.at(0)));"
            if mutable
            else ""
        )
        direct = p(
            f"Counter source=Counter({41 if mutable else 42});"
            + ("" if mutable else "const ")
            + "Holder holder=Holder(source);Counter result=holder.copy(source);source.set(9);"
            "if(result.get()!=42){return 2;}result.set(7);"
            "if(!holder.intact()){return 1;}return holder.get();",
            COUNTER + "class Holder{u8 first;Counter item;u8 last;public:"
            "Holder(Counter source):first(13u8),item(source),last(29u8){}"
            "auto intact()const->bool{return first==13u8&&last==29u8;}"
            "auto get()const->i64{return item.get();}auto copy(Counter ignored)"
            + ("" if mutable else "const")
            + "->Counter{"
            + change
            + "return item;}};",
        )
        suite.check(
            "direct private padded receiver field return " + ("mutable with live span" if mutable else "const"),
            direct,
            equivalent_source=direct.replace("return item;", "const Counter result=item;return result;"),
        )
    direct = p(
        "Counter source=Counter(22);const Holder holder=Holder(source);i64 n=0;i64 total=0;"
        "while(n<2){Counter result=holder.select(n==0);total=total+result.get();result.set(9);n=n+1;}"
        "return total;",
        COUNTER + "class Holder{Counter item;public:Holder(Counter source):item(source){}"
        "auto select(bool local)const->Counter{if(local){Counter item=Counter(20);return item;}"
        "i64 n=0;while(n<1){n=n+1;return item;}return item;}};",
    )
    suite.check(
        "direct receiver field branch and loop returns keep local shadowing",
        direct,
        equivalent_source=direct.replace(
            "n=n+1;return item;", "n=n+1;const Counter result=item;return result;"
        ).replace("}return item;", "}const Counter result=item;return result;"),
    )


def model_cases(suite, seed, steps):
    rng = random.Random(seed)
    edges = {
        "i64": [-(1 << 63), (1 << 63) - 1, -1, 0, 1, 42],
        "u64": [0, 1, 42, 1 << 63, (1 << 64) - 1],
        "u8": [0, 1, 42, 127, 128, 255],
        "bool": [False, True],
    }
    for scalar in SCALARS:
        for capacity in (1, 2, 3, 16, 63, 64):
            concrete = f"std::array<{scalar},{capacity}>"
            arrays = {name: [rng.choice(edges[scalar]) for _ in range(capacity)] for name in ("left", "right")}
            body = [f"{concrete} left={concrete}();{concrete} right={concrete}();"]
            for name, values in arrays.items():
                body += [f"{name}.set({i},{lit(scalar, v)});" for i, v in enumerate(values)]
            for step in range(steps):
                target = "left" if step % 2 == 0 else "right"
                source = target if step % 3 == 0 else ("right" if target == "left" else "left")
                old = arrays[target].copy()
                arrays[target] = arrays[source].copy()
                # Every third operation is self-exchange. Independent result mutations
                # and mutations of the replacement after the call test all aliases.
                body.append("if(true){")
                body.append(f"{concrete} saved={target}.exchange({source});")
                for i, v in enumerate(old):
                    body.append(f"if(saved.at({i})!={lit(scalar, v)}){{return 1;}}")
                index = rng.randrange(capacity)
                value = rng.choice([v for v in edges[scalar] if v != arrays[source][index]])
                body.append(f"{source}.set({index},{lit(scalar, value)});")
                arrays[source][index] = value
                changed = rng.choice([v for v in edges[scalar] if v != old[0]])
                body.append(f"saved.set(0,{lit(scalar, changed)});")
                old[0] = changed
                for name, values in arrays.items():
                    for i, v in enumerate(values):
                        body.append(f"if({name}.at({i})!={lit(scalar, v)}){{return 2;}}")
                for i, v in enumerate(old):
                    body.append(f"if(saved.at({i})!={lit(scalar, v)}){{return 3;}}")
                body.append("}")
            body.append("return 42;")
            suite.check(
                f"seeded exchange snapshot model {scalar} capacity {capacity}",
                p("".join(body), imports="import std.array;"),
            )
    for scalar in SCALARS:
        value = edges[scalar][-1]
        concrete = f"std::array<{scalar},64>"
        suite.check(
            "array exchange accepts readonly replacement " + scalar,
            p(
                f"{concrete} seed={concrete}();seed.set(63,{lit(scalar, value)});"
                f"const {concrete} replacement=seed;{concrete} receiver={concrete}();"
                f"const {concrete} old=receiver.exchange(replacement);"
                f"if(receiver.at(63)!={lit(scalar, value)}){{return 1;}}"
                f"if(old.at(63)!={lit(scalar, False if scalar == 'bool' else 0)}){{return 2;}}"
                "return 42;",
                imports="import std.array;",
            ),
        )


def boundary_cases(suite):
    for leaves in (1, 63, 64, 65):
        fields = "".join(f"i64 f{i};" for i in range(leaves))
        initializers = ",".join(f".f{i}={7 if i == leaves - 1 else i}" for i in range(leaves))
        wide = "class Wide{public:" + fields + "};"
        receiver = (
            "class Receiver{public:Receiver(){}auto sum(Wide a,Wide b,Wide "
            "c,Wide d,Wide e,Wide f)const->i64{"
            f"return a.f{leaves - 1}+b.f{leaves - 1}+c.f{leaves - 1}+d.f"
            f"{leaves - 1}+e.f{leaves - 1}+f.f{leaves - 1};}}}};"
        )
        source = p(
            "Wide source=Wide{" + initializers + "};Receiver receiver=Receiver();"
            "return receiver.sum(source,source,source,source,source,source);",
            wide + receiver,
        )
        if leaves <= 64:
            suite.check(f"six copied arguments each with {leaves} scalar leaves", source)
        else:
            suite.reject("method parameter rejects 65 scalar leaves", source)
    for depth in (4, 5):
        definitions = COUNTER
        body = "Counter value0=Counter(42);"
        current = "Counter"
        for level in range(1, depth):
            name = f"Wrap{level}"
            definitions += f"class {name}{{public:{current} item;{name}({current} x):item(x){{}}}};"
            body += f"{name} value{level}={name}(value{level - 1});"
            current = name
        definitions += (
            f"class Receiver{{public:Receiver(){{}}auto copy({current} value)const->{current}{{return value;}}}};"
        )
        body += f"Receiver receiver=Receiver();{current} result=receiver.copy(value{depth - 1});return 42;"
        if depth == 4:
            suite.check("copied method parameter containment depth four", p(body, definitions))
        else:
            suite.reject("copied method parameter containment depth five rejected", p(body, definitions))


def rejection_cases(suite):
    prefix = "Counter source=Counter(42);Counter receiver=Counter(0);"
    for label, body, helpers in (
        ("designated copied argument remains unsupported", "return receiver.inspect(Counter{.value=42});", ""),
        (
            "indexed copied argument remains unsupported",
            "array<Counter,1> values={source};return receiver.inspect(values[0]);",
            "",
        ),
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
        (
            "class argument outside lexical lifetime",
            "if(true){Counter gone=Counter(42);}return receiver.inspect(gone);",
            "",
        ),
        ("new result binding not visible in own argument", "Counter result=receiver.copy(result);return 42;", ""),
        ("method extraction remains unsupported", "auto method=receiver.read;return 42;", ""),
    ):
        suite.reject(label, p(prefix + body, COUNTER, helpers))
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
            "readonly field receiver forbids mutable method",
            COUNTER + "class Holder{public:Counter item;Holder(Counter source):item(source){}};",
            "auto forward(Holder holder,Counter source)->Counter{return holder.item.replace(source);}",
            "mutable receiver",
        ),
        (
            "private field receiver stays inaccessible",
            COUNTER + "class Holder{Counter item;public:Holder(Counter source):item(source){}};",
            "auto forward(Holder holder,Counter source)->Counter{return holder.item.copy(source);}",
            "private",
        ),
        (
            "chained field receiver remains unsupported",
            COUNTER + "class Holder{public:Counter item;Holder(Counter source):item(source){}};"
            "class Outer{public:Holder holder;Outer(Holder source):holder(source){}};",
            "auto forward(Outer outer,Counter source)->Counter{return outer.holder.item.copy(source);}",
            "method receiver",
        ),
        (
            "temporary containing receiver remains unsupported",
            COUNTER + "class Holder{public:Counter item;Holder(Counter source):item(source){}};",
            "auto forward(Counter source)->Counter{return Holder(source).item.copy(source);}",
            "method receiver",
        ),
        (
            "field receiver exact nominal result",
            COUNTER + "class Holder{public:Counter item;Holder(Counter source):item(source){}};"
            "class Other{public:i64 value;};",
            "auto forward(Holder holder,Counter source)->Other{return holder.item.copy(source);}",
            "expected Other",
        ),
        (
            "implicit method cannot override parameter binding",
            COUNTER.replace("};", "auto forward(Counter copy)const->Counter{return copy(copy);}};"),
            "",
            "callable",
        ),
    ):
        suite.reject("direct method " + label, p("return 42;", definition, helper), error=diagnostic)
    owning_field = (
        COUNTER + "class Owner{builtin::OwnedBytes bytes;public:"
        "Owner(builtin::ByteRegion region,builtin::OwnedBytes source):bytes(move(source)){}"
        "auto copy(Counter source)const->Counter{return source;}};"
        "class Holder{Owner item;public:Holder(builtin::ByteRegion region,Owner source):item(move(source)){}"
        "auto forward(Counter source)const->Counter{return item.copy(source);}};"
    )
    suite.reject(
        "direct field call does not admit nested owning classes",
        p("return 42;", owning_field),
        error="nested owning class fields are unsupported",
    )
    suite.reject(
        "wrong nominal class result destination",
        p(prefix + "Other result=receiver.copy(source);return 42;", COUNTER + "class Other{public:i64 value;};"),
    )
    for label, code in (
        ("mutable method on readonly class parameter", "return source.add(1);"),
        ("parameter rebinding", "Counter other=Counter(1);source=other;return 42;"),
        ("parameter scalar field write", "source.value=42;return 42;"),
        ("parameter array mutation", "source.set(0,42u8);return 42;"),
    ):
        concrete = "std::array<u8,1>" if "array" in label else "Counter"
        initial = "std::array<u8,1>()" if "array" in label else "Counter(42)"
        definitions = (
            COUNTER.replace("i64 value;", "public:i64 value;", 1)
            + f"class Receiver{{public:Receiver(){{}}auto take({concrete} source)->i64{{{code}}}}};"
        )
        suite.reject(
            label,
            p(
                f"{concrete} source={initial};Receiver receiver=Receiver();return receiver.take(source);",
                definitions,
                imports="import std.array;",
            ),
        )
    for type_name in ("own<i64>", "ref<i64>", "mut<i64>", "builtin::array<u8,1>", "builtin::span<u8>"):
        suite.reject(
            "unsupported ordinary method parameter " + type_name,
            p(
                "return 42;",
                f"class Receiver{{public:Receiver(){{}}auto take({type_name} x)const->i64{{return 42;}}}};",
            ),
        )
    for spelling in ("array", "builtin::array"):
        for position, declaration in (
            ("parameter", f"auto take({spelling} source)const->i64{{return 42;}}"),
            ("result", f"auto take(std::array source)const->{spelling}{{return source;}}"),
            ("local", f"auto take(std::array source)const->i64{{{spelling} value=source;return 42;}}"),
            ("constructor", f"auto take(std::array source)const->i64{{std::array value={spelling}();return 42;}}"),
        ):
            suite.reject(
                f"reserved {spelling} never injected wrapper self in {position}",
                p(
                    "std::array<u8,1> value=std::array<u8,1>();return 42;",
                    (
                        "namespace std{template<Scalar T,i64 N>class array{builtin::array<T,N> elements;public:"
                        "array():elements{}{}"
                    )
                    + declaration
                    + "};}",
                ),
            )
    for label, parameter, body, error in (
        ("scalar parameter", "i64 item", "return item;", "expected Counter"),
        ("wrong nominal local", "", "Other item=Other(42);return item;", "expected Counter"),
        (
            "moved local",
            "",
            "own<i64> item=own(42);own<i64> moved=move(item);return item;",
            "use after move",
        ),
    ):
        suite.reject(
            "failed shadowing " + label + " cannot fall back to receiver field",
            p(
                "return 42;",
                COUNTER
                + COUNTER.replace("Counter", "Other")
                + "class Holder{Counter item;public:Holder(Counter source):item(source){}"
                + f"auto copy({parameter})const->Counter{{{body}}}}};",
            ),
            error=error,
        )
    for label, field_type, expression, error in (
        ("wrong nominal receiver field", "Other", "item", "expected Counter"),
        ("qualified receiver field spelling", "Counter", "Holder::item", True),
    ):
        suite.reject(
            "direct field return rejects " + label,
            p(
                "return 42;",
                COUNTER
                + COUNTER.replace("Counter", "Other")
                + f"class Holder{{{field_type} item;public:Holder({field_type} source):item(source){{}}"
                + f"auto copy()const->Counter{{return {expression};}}}};",
            ),
            error=error,
        )


def module_cases(suite):
    modules = {
        "values": "export module values;export " + COUNTER,
        "receivers": "export module receivers;import values;export class Receiver{public:Receiver(){}"
        "auto copy(Counter value)const->Counter{return value;}auto insp"
        "ect(Counter value)const->i64{return value.get();}};",
    }
    suite.check(
        "direct imports preserve private payload through copied method signature",
        p(
            "Counter source=Counter(42);Receiver receiver=Receiver();Counter result=receiver.copy(source);"
            "source.set(99);return receiver.inspect(result);",
            imports="import receivers;import values;",
        ),
        modules=modules,
    )
    suite.reject(
        "transitive method signature type requires direct visible import",
        p(
            (
                "Counter source=Counter(42);Receiver receiver=Receiver();Counter result=receiver.copy(source);r"
                "eturn result.get();"
            ),
            imports="import receivers;",
        ),
        modules=modules,
    )
    same = {
        "left": "export module left;export namespace left{" + COUNTER + "}",
        "right": "export module right;export namespace right{" + COUNTER + "}",
    }
    suite.reject(
        "same layout same basename across modules remains nominal",
        p(
            (
                "left::Counter receiver=left::Counter(0);right::Counter source=right::Counter(42);return receiv"
                "er.inspect(source);"
            ),
            imports="import left;import right;",
        ),
        modules=same,
    )


def trap_cases(suite):
    for scalar in SCALARS:
        concrete = f"std::array<{scalar},3>"
        for index in (-1, 3):
            suite.check(
                f"copied method parameter exact bounds trap {scalar}/{index}",
                p(
                    f"{concrete} source={concrete}();Receiver receiver=Receiver();re"
                    f"turn receiver.inspect(source,{index});",
                    f"class Receiver{{public:Receiver(){{}}auto inspect({concrete} s"
                    f"ource,i64 index)const->{scalar}{{return source.at(index);}}}};",
                    imports="import std.array;",
                    result=scalar,
                ),
                expected=Trap.BOUNDS,
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path, nargs="?", default=ROOT / "build/aurorac")
    parser.add_argument("--seed", type=int, default=22022)
    # Three steps cover self-exchange and both cross directions (step % 3, step % 2).
    parser.add_argument("--steps", type=int, default=3)
    args = parser.parse_args()
    require(1 <= args.steps <= 48, "steps must be between 1 and 48")
    suite = MethodSuite(args.compiler, "method values", ignore_case=True, pack_templates=32)
    suite.load(Path(__file__).with_suffix(".cases"), COUNTER=COUNTER, EMPTY=EMPTY, ENUMS=ENUMS)
    native_cases(suite)
    model_cases(suite, args.seed, args.steps)
    boundary_cases(suite)
    rejection_cases(suite)
    module_cases(suite)
    trap_cases(suite)
    suite.finish()


if __name__ == "__main__":
    main()
