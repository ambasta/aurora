#!/usr/bin/env python3
"""Ordinary enum, copied method-result, and std.decimal execution/type checks.

The decimal reference uses unbounded Python integers. Cases are data for the
shared native runner (native_runner.py), which compares all eight result bytes,
including values above the signed range.

Run: python3 tests/compiler/decimal_values.py build/aurorac
Optional reproducible sequence: --seed 10011 --steps 96
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import random

from native_runner import Suite


ROOT = Path(__file__).resolve().parents[2]
MAX_U64 = (1 << 64) - 1
HIGH_U64 = 1 << 63
STATUS = "std::DecimalStatus::"
ENUM = "enum class State { ready, done, failed };"


def program(body, definitions="", helpers="", imports="", result="i64"):
    return "module app;" + imports + definitions + helpers + f"auto test()->{result}{{{body}}}"


def enum_cases(suite):
    for left in ("ready", "done", "failed"):
        for right in ("ready", "done", "failed"):
            for operator in ("==", "!="):
                value = left == right if operator == "==" else left != right
                suite.check(
                    f"enum {left} {operator} {right}",
                    program(f"return State::{left}{operator}State::{right};", ENUM, result="bool"),
                    expected=int(value),
                )

    suite.check(
        "enum locals and assignment",
        program(
            "const State first=State::ready;State next=first;next=State::done;"
            "if(first!=State::ready){return 1;}if(next!=State::done){return 2;}return 42;",
            ENUM,
        ),
    )
    suite.check(
        "enum compile time equality",
        program(
            "static_assert(State::ready==State::ready);"
            "static_assert(State::ready!=State::done);"
            "static_assert(!(State::failed==State::done));return 42;",
            ENUM,
        ),
    )
    suite.check(
        "builtin Scalar template remains available",
        program(
            "Pair<u64> p=Pair<u64>(42u64);return p.value;",
            "template<Scalar T>class Pair{public:T value;Pair(T n):value(n){}};",
            result="u64",
        ),
    )
    suite.check(
        "enum fields and independent class copies",
        program(
            "Flag first=Flag{.state=State::ready};Flag second=first;"
            "second.state=State::done;if(first.state!=State::ready){return 1;}"
            "if(second.state!=State::done){return 2;}return 42;",
            ENUM + "class Flag{public:State state;};",
        ),
    )
    suite.check(
        "enum constructor and mutable method boundary",
        program(
            "Flag flag=Flag(State::ready);const State old=flag.set(State::done);"
            "if(old!=State::ready){return 1;}if(flag.get()!=State::done){return 2;}return 42;",
            ENUM + "class Flag{State state;public:Flag(State initial):state(initial){}"
            "auto get()const->State{return state;}auto set(State next)->State{"
            "const State old=state;state=next;return old;}};",
        ),
    )
    suite.check(
        "enum ordinary function parameters and result",
        program(
            "const State selected=choose(State::ready,State::done,true);if(selected==State::done){return 42;}return 0;",
            ENUM,
            "auto choose(State a,State b,bool second)->State{if(second){return b;}return a;}",
        ),
    )
    suite.check(
        "six enum function arguments",
        program(
            "if(last(State::ready,State::failed,State::ready,State::ready,"
            "State::failed,State::done)==State::done){return 42;}return 0;",
            ENUM,
            "auto last(State a,State b,State c,State d,State e,State f)->State{return f;}",
        ),
    )
    suite.check(
        "enum field copied across function result",
        program(
            "Flag first=Flag{.state=State::ready};const Flag second=copy(first);"
            "first.state=State::failed;if(second.state==State::ready){return 42;}return 0;",
            ENUM + "class Flag{public:State state;};",
            "auto copy(Flag value)->Flag{return value;}",
        ),
    )
    suite.check(
        "enum reflection nominal identity",
        program(
            "static_assert(size_of(State)==8);static_assert(field_count(State)==0);"
            "static_assert(type_id(State)!=type_id(Other));"
            "static_assert(type_id(State)!=type_id(i64));"
            "static_assert(type_id(State)!=type_id(u64));"
            "static_assert(type_id(State)!=type_id(bool));"
            "static_assert(type_id(State)!=type_id(Box));"
            "if(reflect_size(type_id(State))!=8){return 1;}"
            "if(reflect_field_count(type_id(State))!=0){return 2;}return 42;",
            ENUM + "enum class Other{ready,done,failed};class Box{public:State state;};",
        ),
    )
    suite.check(
        "enum field reflection matches class layout",
        program(
            "static_assert(size_of(Box)==16);static_assert(field_count(Box)==1);"
            "if(reflect_size(type_id(Box))!=16){return 1;}"
            "if(reflect_field_count(type_id(Box))!=1){return 2;}return 42;",
            ENUM + "class Box{State hidden;public:State shown;Box(State a,State b):hidden(a),shown(b){}};",
        ),
    )
    exported = (
        "export module states;export namespace items{"
        "enum class State{ready,done};"
        "auto ready()->State{return State::ready;}"
        "auto same(State a,State b)->bool{return a==b;}}"
    )
    suite.check(
        "exported enum module boundary",
        program(
            "const items::State state=items::ready();if(items::same(state,items::State::ready)){return 42;}return 0;",
            imports="import states;",
        ),
        modules={"states": exported},
    )
    suite.check(
        "imported enum reflection",
        program(
            "static_assert(size_of(items::State)==8);"
            "static_assert(field_count(items::State)==0);"
            "if(reflect_size(type_id(items::State))!=8){return 1;}"
            "if(reflect_field_count(type_id(items::State))!=0){return 2;}return 42;",
            imports="import states;",
        ),
        modules={"states": exported},
    )
    suite.check(
        "namespace enums keep nominal identity",
        program(
            "static_assert(type_id(left::State)!=type_id(right::State));"
            "if(left::State::ready==left::State::ready){return 42;}return 0;",
            "namespace left{enum class State{ready};}namespace right{enum class State{ready};}",
        ),
    )
    # Lowering names every case once; the duplicate check was cubic in the case count.
    widest = "enum class Wide{" + ",".join(f"case_{index}" for index in range(256)) + "};"
    suite.check(
        "widest enum lowers distinct cases",
        program("if(Wide::case_255!=Wide::case_0&&Wide::case_128==Wide::case_128){return 42;}return 0;", widest),
    )

    invalid_bodies = [
        ("wrong enum local", "State s=Other::ready;return 42;"),
        ("wrong enum assignment", "State s=State::ready;s=Other::ready;return 42;"),
        ("different enum equality", "if(State::ready==Other::ready){return 42;}return 0;"),
        ("different enum inequality", "if(State::ready!=Other::ready){return 42;}return 0;"),
        ("integer enum initialization", "State s=0;return 42;"),
        ("unsigned enum initialization", "State s=0u64;return 42;"),
        ("boolean enum initialization", "State s=false;return 42;"),
        ("enum integer local", "i64 s=State::ready;return s;"),
        ("enum unsigned local", "u64 s=State::ready;return 42;"),
        ("enum boolean local", "bool s=State::ready;return 42;"),
        ("enum condition", "if(State::ready){return 42;}return 0;"),
        ("enum logical negation", "if(!State::ready){return 42;}return 0;"),
        ("enum signed conversion", "return i64(State::ready);"),
        ("enum unsigned conversion", "u64 n=u64(State::ready);return 42;"),
        ("signed enum construction", "State s=State(0);return 42;"),
        ("unsigned enum construction", "State s=State(0u64);return 42;"),
        ("enum designated construction", "State s=State{};return 42;"),
        ("unknown enum case", "State s=State::missing;return 42;"),
        ("unqualified enum case", "State s=ready;return 42;"),
        ("immutable enum local", "const State s=State::ready;s=State::done;return 42;"),
        ("enum builtin array", "array<State,1> values={State::ready};return 42;"),
        ("enum scalar template argument", "Pair<State> p=Pair<State>(State::ready);return 42;"),
    ]
    for operator in ("+", "-", "*", "/", "%", "&", "|", "^", "<<", ">>"):
        invalid_bodies.append(
            ("enum numeric operator " + operator, f"State s=State::ready{operator}State::done;return 42;")
        )
    for operator in ("<", "<=", ">", ">="):
        invalid_bodies.append(
            ("enum ordering " + operator, f"if(State::ready{operator}State::done){{return 42;}}return 0;")
        )
    for operator in ("-", "~"):
        invalid_bodies.append(("enum unary " + operator, f"State s={operator}State::ready;return 42;"))
    extras = "enum class Other{ready,done};template<Scalar T>class Pair{public:T value;Pair(T n):value(n){}};"
    for name, body in invalid_bodies:
        suite.check(name, program(body, ENUM + extras), error=True)
    for name, definition in [
        ("duplicate enum case", "enum class State{ready,ready};"),
        ("explicit enum numeric value", "enum class State{ready=0,done};"),
        ("enum underlying numeric type", "enum class State:u64{ready,done};"),
        ("unscoped enum syntax", "enum State{ready,done};"),
    ]:
        suite.check(name, program("return 42;", definition), error=True)
    for name, helper, body in [
        ("wrong enum function argument", "auto take(State s)->i64{return 42;}", "return take(Other::ready);"),
        ("wrong enum function return", "auto make()->State{return Other::ready;}", "const State s=make();return 42;"),
        ("enum returned as integer", "auto make()->i64{return State::ready;}", "return make();"),
        (
            "enum function parameter immutable",
            "auto take(State s)->i64{s=State::done;return 42;}",
            "return take(State::ready);",
        ),
    ]:
        suite.check(name, program(body, ENUM + extras, helper), error=True)
    suite.check(
        "wrong enum class field",
        program("Flag f=Flag{.state=Other::ready};return 42;", ENUM + extras + "class Flag{public:State state;};"),
        error=True,
    )
    suite.check(
        "same named enums in modules are distinct",
        program("a::State state=b::State::ready;return 42;", imports="import one;import two;"),
        error=True,
        modules={
            "one": "export module one;export namespace a{enum class State{ready};}",
            "two": "export module two;export namespace b{enum class State{ready};}",
        },
    )
    flag = (
        ENUM + "enum class Other{ready};class Flag{State state;public:"
        "Flag(State initial):state(initial){}"
        "auto set(State next)->State{state=next;return state;}};"
    )
    suite.check("wrong enum constructor argument", program("Flag f=Flag(Other::ready);return 42;", flag), error=True)
    suite.check(
        "wrong enum method argument",
        program("Flag f=Flag(State::ready);f.set(Other::ready);return 42;", flag),
        error=True,
    )
    suite.check(
        "false enum equality static assertion",
        program("static_assert(State::ready==State::done);return 42;", ENUM),
        error=True,
    )


REPORT = """class Report {
    u64 payload;
public:
    Report(u64 value):payload(value){}
    auto get()const->u64{return payload;}
    auto set(u64 value)->u64{payload=value;return payload;}
};
class Counter {
    u64 value;
public:
    Counter(u64 initial):value(initial){}
    auto get()const->u64{return value;}
    auto add(u64 n)->u64{value=value+n;return value;}
    auto snapshot()const->Report{const Report result=Report(value);return result;}
    auto advance(u64 n)->Report{value=value+n;const Report result=Report(value);return result;}
    auto forwarded()const->Report{const Report result=snapshot();return result;}
};"""


def method_result_cases(suite):
    for name, body, expected in [
        ("const method class result", "const Counter c=Counter(42u64);const Report r=c.snapshot();return r.get();", 42),
        ("mutable method class result", "Counter c=Counter(40u64);const Report r=c.advance(2u64);return r.get();", 42),
        (
            "method result independent after receiver changes",
            "Counter c=Counter(42u64);const Report r=c.snapshot();c.add(9u64);return r.get();",
            42,
        ),
        (
            "method result local may independently mutate",
            "Counter c=Counter(40u64);Report r=c.snapshot();r.set(2u64);return c.get()+r.get();",
            42,
        ),
        (
            "mutable method result independent after next call",
            "Counter c=Counter(40u64);"
            "const Report r=c.advance(2u64);const Report next=c.advance(99u64);return r.get();",
            42,
        ),
        (
            "bound sibling class result",
            "const Counter c=Counter(42u64);const Report r=c.forwarded();return r.get();",
            42,
        ),
        ("class result survives receiver block exit", "const Report r=make();return r.get();", 42),
        (
            "method full unsigned result",
            f"const Counter c=Counter({MAX_U64}u64);const Report r=c.snapshot();return r.get();",
            MAX_U64,
        ),
        (
            "copied method result through function",
            "Counter c=Counter(42u64);"
            "const Report r=c.snapshot();const Report copy=identity(r);"
            "c.add(1u64);return copy.get();",
            42,
        ),
        (
            "method result in loop",
            "Counter c=Counter(18u64);u64 sum=0u64;i64 i=0;"
            "while(i<2){const Report r=c.advance(2u64);sum=sum+r.get();i=i+1;}return sum;",
            42,
        ),
    ]:
        suite.check(
            name,
            program(
                body,
                REPORT,
                "auto make()->Report{Counter c=Counter(42u64);"
                "const Report r=c.snapshot();return r;}"
                "auto identity(Report r)->Report{return r;}",
                result="u64",
            ),
            expected,
        )
    suite.check(
        "method arguments evaluate left to right",
        program(
            "Counter c=Counter(10u64);const Report r=c.combine(c.add(1u64),c.add(2u64));return r.get();",
            REPORT.replace(
                "auto forwarded()",
                "auto combine(u64 a,u64 b)const->Report{"
                "const Report r=Report(a*100u64+b*10u64+value);return r;}auto forwarded()",
            ),
            result="u64",
        ),
        expected=1243,
    )
    suite.check(
        "six explicit arguments with receiver and class result",
        program(
            "Counter c=Counter(1u64);const Report r=c.combine(1u64,2u64,3u64,4u64,5u64,26u64);return r.get();",
            REPORT.replace(
                "auto forwarded()",
                "auto combine(u64 a,u64 b,u64 c,u64 d,u64 e,u64 f)"
                "const->Report{const Report r=Report(value+a+b+c+d+e+f);return r;}"
                "auto forwarded()",
            ),
            result="u64",
        ),
    )
    suite.check(
        "enum explicit argument and class result",
        program(
            "const Factory f=Factory();const Flag r=f.make(State::done);if(r.state==State::done){return 42;}return 0;",
            ENUM + "class Flag{public:State state;};class Factory{public:Factory(){}"
            "auto make(State state)const->Flag{const Flag result=Flag{.state=state};return result;}};",
        ),
    )
    suite.check(
        "empty class method result",
        program(
            "Factory f=Factory();const Empty result=f.make();return 42;",
            "class Empty{public:Empty(){}};class Factory{public:Factory(){}"
            "auto make()const->Empty{const Empty value=Empty();return value;}};",
        ),
    )
    suite.check(
        "class method result through module",
        program(
            "const items::Counter c=items::Counter(42u64);const items::Report r=c.snapshot();return r.get();",
            imports="import reports;",
            result="u64",
        ),
        modules={"reports": "export module reports;export namespace items{" + REPORT + "}"},
    )
    suite.check(
        "class result remains independent of another result",
        program(
            "Counter c=Counter(21u64);Report first=c.snapshot();Report second=c.snapshot();"
            "first.set(0u64);return second.get()+c.get();",
            REPORT,
            result="u64",
        ),
    )
    suite.check(
        "const binding copied into mutable method result",
        program(
            "const Counter c=Counter(40u64);Report result=c.snapshot();result.set(42u64);return result.get();",
            REPORT,
            result="u64",
        ),
    )
    suite.check(
        "class result method calls ordinary aggregate function",
        program(
            "const Counter c=Counter(21u64);const Report r=c.copied();return r.get();",
            REPORT.replace(
                "auto forwarded()",
                "auto copied()const->Report{"
                "const Report base=Report(value);const Report copy=copy_report(base);"
                "const Report result=Report(copy.get()+get());return result;}"
                "auto forwarded()",
            ),
            "auto copy_report(Report r)->Report{return r;}",
            result="u64",
        ),
    )
    suite.check(
        "mutable result method calls nested result methods and function",
        program(
            "Counter c=Counter(10u64);const Report r=c.updated(6u64);return r.get();",
            REPORT.replace(
                "auto forwarded()",
                "auto updated(u64 delta)->Report{"
                "const Report initial=snapshot();const Report after=advance(delta);"
                "const Report copy=copy_report(after);"
                "const Report result=Report(initial.get()+copy.get()+value);"
                "return result;}auto forwarded()",
            ),
            "auto copy_report(Report r)->Report{return r;}",
            result="u64",
        ),
    )
    suite.check(
        "method result copies private fixed array leaves",
        program(
            "const Factory f=Factory();std::array<u64,3> first=f.make();"
            "const std::array<u64,3> second=first;first.set(0,0u64);"
            "if(second.at(1)!=42u64){return 0u64;}"
            "if(second.at(2)!=9223372036854775808u64){return 0u64;}return second.at(0);",
            "class Factory{public:Factory(){}auto make()const->std::array<u64,3>{"
            "std::array<u64,3> r=std::array<u64,3>();r.set(0,18446744073709551615u64);"
            "r.set(1,42u64);r.set(2,9223372036854775808u64);return r;}};",
            imports="import std.array;",
            result="u64",
        ),
        expected=MAX_U64,
    )

    for width in (1, 64):
        fields = "".join(f"u64 f{i};" for i in range(width))
        initializers = ",".join(f".f{i}={MAX_U64 - i}u64" for i in range(width))
        definitions = (
            "class Wide{public:" + fields + "};class Factory{u64 seed;public:"
            "Factory(u64 n):seed(n){}auto make()const->Wide{"
            f"const Wide result=Wide{{{initializers}}};return result;}}}};"
        )
        body = "const Factory f=Factory(42u64);const Wide result=f.make();"
        for index in range(width):
            body += f"if(result.f{index}!={MAX_U64 - index}u64){{return 0u64;}}"
        body += f"return result.f{width - 1};"
        suite.check(
            f"method class result {width} scalar leaves", program(body, definitions, result="u64"), MAX_U64 - width + 1
        )

    suite.check(
        "method result copied temporary argument",
        program(
            "Counter c=Counter(1u64);return consume(c.snapshot());",
            REPORT + "class Other{public:u64 value;};",
            "auto consume(Report r)->i64{return 42;}",
        ),
    )
    for name, body in [
        (
            "mutable result method on const receiver",
            "const Counter c=Counter(1u64);const Report r=c.advance(1u64);return 42;",
        ),
        ("class result cannot initialize scalar", "Counter c=Counter(1u64);u64 n=c.snapshot();return 42;"),
        ("method result requires typed local", "Counter c=Counter(1u64);c.snapshot();return 42;"),
        ("method result wrong nominal class", "Counter c=Counter(1u64);Other r=c.snapshot();return 42;"),
        (
            "const method result cannot mutate",
            "Counter c=Counter(1u64);const Report r=c.snapshot();r.set(42u64);return 42;",
        ),
    ]:
        helpers = "auto consume(Report r)->i64{return 42;}"
        suite.check(name, program(body, REPORT + "class Other{public:u64 value;};", helpers), error=True)
    suite.check(
        "direct copied method return preserves payload",
        program(
            "Counter c=Counter(1u64);const Report r=forward(c);return r.get();",
            REPORT,
            "auto forward(Counter c)->Report{return c.snapshot();}",
            result="u64",
        ),
        expected=1,
    )
    suite.check(
        "explicit method class parameter copies independent result",
        program(
            "Counter receiver=Counter(0u64);Report source=Report(42u64);Report result=receiver.take(source);"
            "source.set(0u64);return i64(result.get());",
            REPORT.replace("auto forwarded()", "auto take(Report r)const->Report{return r;}auto forwarded()"),
        ),
    )
    suite.check(
        "class method constructor return copies independent value",
        program(
            "Counter c=Counter(42u64);Report r=c.snapshot();c.add(1u64);return i64(r.get());",
            REPORT.replace("const Report result=Report(value);return result;", "return Report(value);", 1),
        ),
    )


@dataclass(frozen=True)
class DecimalReport:
    status: str
    position: int
    value: int

    def value_or(self, fallback):
        return self.value if self.status == "success" else fallback


class DecimalModel:
    """Mathematical reference: append first, then compare with the u64 domain."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.report = DecimalReport("empty", 0, 0)
        return "empty"

    def push(self, digit):
        previous = self.report
        if previous.status in ("invalid_digit", "out_of_range"):
            return previous.status
        if digit not in range(10):
            self.report = DecimalReport("invalid_digit", previous.position, 0)
        else:
            mathematical = previous.value * 10 + digit
            if mathematical > MAX_U64:
                self.report = DecimalReport("out_of_range", previous.position, 0)
            else:
                self.report = DecimalReport("success", previous.position + 1, mathematical)
        return self.report.status


def decimal_checks(variable, report, fallback, failed):
    return (
        f"if({variable}.status()!={STATUS}{report.status}){{return {failed}u64;}}"
        f"if({variable}.position()!={report.position}){{return {failed}u64;}}"
        f"if({variable}.value_or({fallback}u64)!={report.value_or(fallback)}u64)"
        f"{{return {failed}u64;}}"
    )


def modeled_sequence(suite, name, actions, fallback=MAX_U64):
    model = DecimalModel()
    expected_reports = []
    for action in actions:
        expected_status = model.reset() if action is None else model.push(action)
        expected_reports.append((expected_status, model.report))
    expected = model.report.value_or(fallback)
    failed = 0 if expected != 0 else MAX_U64
    body = "std::DecimalAccumulator accumulator=std::DecimalAccumulator();"
    body += "const std::DecimalResult initial=accumulator.finish();"
    body += decimal_checks("initial", DecimalReport("empty", 0, 0), fallback, failed)
    saved = []
    for index, (action, (status, report)) in enumerate(zip(actions, expected_reports)):
        expression = "accumulator.reset()" if action is None else f"accumulator.push_digit({action}u64)"
        body += f"if({expression}!={STATUS}{status}){{return {failed}u64;}}"
        variable = f"report{index}"
        body += f"const std::DecimalResult {variable}=accumulator.finish();"
        body += decimal_checks(variable, report, fallback, failed)
        saved.append((variable, report))
    # Every earlier finish() must remain a snapshot after all later input/resets.
    for variable, report in saved:
        body += decimal_checks(variable, report, fallback, failed)
    body += decimal_checks("initial", DecimalReport("empty", 0, 0), fallback, failed)
    body += "const std::DecimalResult final=accumulator.finish();"
    body += f"return final.value_or({fallback}u64);"
    suite.check(name, program(body, imports="import std.decimal;", result="u64"), expected)


def decimal_cases(suite, seed, steps):
    modeled_sequence(suite, "decimal empty", [])
    for value in (
        0,
        1,
        9,
        10,
        42,
        99,
        100,
        1000,
        HIGH_U64 - 1,
        HIGH_U64,
        HIGH_U64 + 1,
        MAX_U64 // 10,
        MAX_U64 - 1,
        MAX_U64,
    ):
        modeled_sequence(suite, f"decimal exact value {value}", [int(x) for x in str(value)])
    for name, actions in [
        ("decimal leading zeros", [0, 0, 0, 4, 2]),
        ("decimal repeated zero success", [0] * 32),
        ("decimal many leading zeros at maximum", [0] * 24 + [int(x) for x in str(MAX_U64)]),
        ("decimal invalid first digit", [10]),
        ("decimal invalid high unsigned digit", [MAX_U64]),
        ("decimal invalid after zero", [0, 10]),
        ("decimal invalid after accepted digits", [4, 2, 10]),
        ("decimal invalid stays latched", [4, 2, 10, 9, 0, MAX_U64]),
        ("decimal maximum plus one", [int(x) for x in str(MAX_U64 + 1)]),
        ("decimal maximum then digit", [int(x) for x in str(MAX_U64)] + [0]),
        ("decimal overflow stays latched", [int(x) for x in str(MAX_U64 + 1)] + [9, 10, 0]),
        ("decimal reset empty", [None, None]),
        ("decimal reset success", [4, 2, None, 0]),
        ("decimal reset invalid", [4, 2, 10, None, 9]),
        ("decimal reset overflow", [int(x) for x in str(MAX_U64 + 1)] + [None, 4, 2]),
        ("decimal repeated resets and snapshots", [None, 0, None, 10, None, 4, 2, None]),
    ]:
        modeled_sequence(suite, name, actions)
    for last_digit in range(10):
        modeled_sequence(
            suite, f"decimal final boundary digit {last_digit}", [int(x) for x in str(MAX_U64 // 10)] + [last_digit]
        )
    for fallback in (0, 1, HIGH_U64, MAX_U64):
        for label, actions in (
            ("empty", []),
            ("zero", [0]),
            ("success", [4, 2]),
            ("invalid", [10]),
            ("overflow", [int(x) for x in str(MAX_U64 + 1)]),
        ):
            modeled_sequence(suite, f"decimal {label} fallback {fallback}", actions, fallback)

    rng = random.Random(seed)
    for sequence in range(8):
        actions = []
        while len(actions) < steps:
            actions.append(None)
            choice = rng.randrange(5)
            if choice == 0:
                actions.extend(int(x) for x in str(rng.randrange(MAX_U64 + 1)))
            elif choice == 1:
                actions.extend(int(x) for x in str(MAX_U64 + rng.randrange(1, 1000000)))
            elif choice == 2:
                actions.extend([0] * rng.randrange(1, 20))
                actions.extend(int(x) for x in str(rng.randrange(1000000)))
            elif choice == 3:
                actions.extend(rng.randrange(10) for _ in range(rng.randrange(0, 8)))
                actions.append(rng.choice((10, 11, 255, HIGH_U64, MAX_U64)))
                actions.extend(rng.randrange(10) for _ in range(3))
            else:
                actions.extend(rng.randrange(10) for _ in range(rng.randrange(1, 27)))
        modeled_sequence(
            suite, f"decimal modeled sequence {sequence} seed {seed}", actions[:steps], rng.randrange(MAX_U64 + 1)
        )

    suite.check(
        "decimal accumulator copies have independent input",
        program(
            "std::DecimalAccumulator first=std::DecimalAccumulator();first.push_digit(4u64);"
            "std::DecimalAccumulator second=first;first.push_digit(2u64);second.push_digit(3u64);"
            "const std::DecimalResult a=first.finish();const std::DecimalResult b=second.finish();"
            "if(a.value_or(0u64)!=42u64){return 0u64;}return b.value_or(0u64);",
            imports="import std.decimal;",
            result="u64",
        ),
        expected=43,
    )
    suite.check(
        "decimal result ordinary function copy",
        program(
            "std::DecimalAccumulator a=std::DecimalAccumulator();a.push_digit(4u64);"
            "a.push_digit(2u64);const std::DecimalResult first=a.finish();"
            "const std::DecimalResult second=copy(first);a.reset();return second.value_or(0u64);",
            helpers="auto copy(std::DecimalResult r)->std::DecimalResult{return r;}",
            imports="import std.decimal;",
            result="u64",
        ),
    )
    suite.check(
        "decimal finish accepts const copied accumulator",
        program(
            "std::DecimalAccumulator a=std::DecimalAccumulator();a.push_digit(4u64);"
            "a.push_digit(2u64);const std::DecimalAccumulator frozen=a;"
            "a.reset();const std::DecimalResult r=frozen.finish();return r.value_or(0u64);",
            imports="import std.decimal;",
            result="u64",
        ),
    )
    for label, digits, expected in (
        ("success", (4, 2), 42),
        ("empty", (), 1),
        ("invalid", (10,), 1),
        ("overflow", tuple(int(x) for x in str(MAX_U64 + 1)), 1),
    ):
        body = "std::DecimalAccumulator a=std::DecimalAccumulator();"
        body += "".join(f"a.push_digit({digit}u64);" for digit in digits)
        body += (
            "const std::DecimalResult r=a.finish();Counter side=Counter(0u64);"
            "const u64 value=r.value_or(side.add(1u64));"
            "if(side.get()!=1u64){return 0u64;}return value;"
        )
        suite.check(
            f"decimal {label} fallback evaluates eagerly",
            program(body, REPORT, imports="import std.decimal;", result="u64"),
            expected,
        )
    suite.check(
        "decimal result status nominal reflection",
        program(
            "static_assert(size_of(std::DecimalStatus)==8);"
            "static_assert(field_count(std::DecimalStatus)==0);"
            "static_assert(type_id(std::DecimalStatus)!=type_id(std::DecimalResult));"
            "static_assert(type_id(std::DecimalStatus)!=type_id(std::DecimalAccumulator));"
            "if(reflect_size(type_id(std::DecimalStatus))!=8){return 1;}return 42;",
            imports="import std.decimal;",
        ),
    )
    for name, body in [
        (
            "decimal digit must be unsigned",
            "std::DecimalAccumulator a=std::DecimalAccumulator();a.push_digit(1);return 42;",
        ),
        (
            "decimal fallback must be unsigned",
            "std::DecimalAccumulator a=std::DecimalAccumulator();"
            "const std::DecimalResult r=a.finish();return r.value_or(0);",
        ),
        (
            "decimal status cannot mix other enum",
            "std::DecimalAccumulator a=std::DecimalAccumulator();"
            "const std::DecimalResult r=a.finish();if(r.status()==State::ready){return 42;}return 0;",
        ),
        (
            "decimal push requires mutable accumulator",
            "const std::DecimalAccumulator a=std::DecimalAccumulator();a.push_digit(1u64);return 42;",
        ),
        (
            "decimal reset requires mutable accumulator",
            "const std::DecimalAccumulator a=std::DecimalAccumulator();a.reset();return 42;",
        ),
        (
            "decimal finish requires result local",
            "std::DecimalAccumulator a=std::DecimalAccumulator();a.finish();return 42;",
        ),
    ]:
        suite.check(name, program(body, ENUM, imports="import std.decimal;"), error=True)


def decimal_projection_cases(suite):
    # Python decimal strings are independent of the library's divide/remainder loops.
    values = set(range(256)) | {MAX_U64, HIGH_U64, HIGH_U64 - 1}
    for exponent in range(1, 20):
        values.update((10**exponent - 1, 10**exponent, 10**exponent + 1))
    values = sorted(values)
    for start in range(0, len(values), 16):
        checks = []
        for value in values[start : start + 16]:
            digits = str(value)
            checks.append(f"if(std::format_decimal_width_u64({value}u64)!={len(digits)}){{return 1;}}")
            for place in (-9223372036854775808, -1, *range(len(digits) + 1), 9223372036854775807):
                expected = ord(digits[-1 - place]) if 0 <= place < len(digits) else 0
                checks.append(f"if(std::format_decimal_digit_at_u64({value}u64,{place})!={expected}u8){{return 2;}}")
        suite.check(
            "scalar decimal width and digit projections",
            program("".join(checks) + "return 42;", imports="import std.decimal;"),
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    parser.add_argument("--seed", type=int, default=10011)
    parser.add_argument("--steps", type=int, default=96)
    arguments = parser.parse_args()
    if not 1 <= arguments.steps <= 256:
        parser.error("--steps must be between 1 and 256")
    suite = Suite(arguments.compiler, "decimal values")
    enum_cases(suite)
    method_result_cases(suite)
    decimal_cases(suite, arguments.seed, arguments.steps)
    decimal_projection_cases(suite)
    suite.finish()


if __name__ == "__main__":
    main()
