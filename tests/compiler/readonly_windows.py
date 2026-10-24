#!/usr/bin/env python3
"""Readonly subspan source/native oracle with exact named traps (native_runner.py).

Expected bytes come from Python slice arithmetic, never emitted IR/layout. Existing
whole-span and single-span APIs are exercised without edits.
"""

import argparse
from pathlib import Path
import random

from readonly_spans import Suite, Trap, SPAN, array, view, checksum, MIN_I64, MAX_I64, HIGH_BIT


def window(name="part", parent="view", start=0, count=0):
    return f"const {SPAN} {name}={parent}.subspan({start},{count});"


def model(suite, seed):
    rng = random.Random(seed)
    for size in (1, 3, 4, 8, 64, 4096):
        values = [rng.randrange(256) for _ in range(size)]
        pairs = {(0, 0), (0, size), (size, 0), (size - 1, 1), (size // 2, size - size // 2)}
        for _ in range(7):
            offset = rng.randrange(size + 1)
            pairs.add((offset, rng.randrange(size - offset + 1)))
        for offset, count in sorted(pairs):
            body = array("bytes", values) + view() + window(start=offset, count=count)
            body += (
                f"if(part.size()!={count}){{return 1u64;}}"
                "i64 i=0;u64 sum=0u64;while(i<part.size()) {"
                "sum=sum+u64(i+1)*u64(part.at(i));i=i+1;}"
                f"return {HIGH_BIT}u64+sum;"
            )
            suite.check(
                f"window bytes n={size} offset={offset} count={count}",
                body,
                HIGH_BIT + checksum(values[offset : offset + count]),
            )
        # Dynamic input through the ordinary internal span call boundary.
        helper = (
            f"auto window_read({SPAN} v,i64 off,i64 n)->u64{{" + window("x", "v", "off", "n") + "return u64(x.size());}"
        )
        for off, count in {
            (MIN_I64, 0),
            (-1, 0),
            (size + 1, 0),
            (MAX_I64, 0),
            (0, -1),
            (0, MIN_I64),
            (0, MAX_I64),
            (1, size),
            (size, 1),
        }:
            suite.check(
                f"bad dynamic window n={size} off={off} count={count}",
                array("bytes", values) + f"return window_read(borrow_bytes(bytes),{off},{count});",
                Trap.BOUNDS,
                helpers=helper,
            )
    suite.check(
        "nested offsets stay relative to parent",
        array("bytes", [10, 20, 30, 40, 50, 60])
        + view()
        + window("middle", "view", 1, 4)
        + window("inside", "middle", 1, 2)
        + "return u64(inside.at(0))*100u64+u64(inside.at(1));",
        3040,
    )
    for index in (MIN_I64, -1, 0, 1, MAX_I64):
        suite.check(
            f"empty endpoint never dereferences index {index}",
            array("bytes", [42]) + view() + window(start=1, count=0) + f"return u64(part.at({index}));",
            Trap.BOUNDS,
        )
    suite.check(
        "nested empty endpoint remains empty",
        array("bytes", [42]) + view() + window("a", "view", 1, 0) + window("b", "a", 0, 0) + "return u64(b.size());",
        0,
    )
    suite.check(
        "child cannot regain excluded prefix",
        array("bytes", [9, 42, 8])
        + view()
        + window(start=1, count=1)
        + window("widen", "part", -1, 2)
        + "return u64(widen.size());",
        Trap.BOUNDS,
    )
    suite.check(
        "child cannot regain excluded suffix",
        array("bytes", [9, 42, 8])
        + view()
        + window(start=1, count=1)
        + window("widen", "part", 0, 2)
        + "return u64(widen.size());",
        Trap.BOUNDS,
    )
    for index in (-1, 2, MIN_I64, MAX_I64):
        suite.check(
            f"nonempty child own bounds {index}",
            array("bytes", [1, 2, 3, 4]) + view() + window(start=1, count=2) + f"return u64(part.at({index}));",
            Trap.BOUNDS,
        )


def calls(suite):
    helpers = (
        f"auto sum({SPAN} a)->u64{{i64 i=0;u64 v=0u64;while(i<a.size()){{"
        "v=v+u64(a.at(i));i=i+1;}return v;}"
        f"auto relay({SPAN} a)->u64{{return sum(a.subspan(1,2));}}"
    )
    suite.check(
        "call temporary nested forwarding",
        array("bytes", [7, 10, 20, 30, 40, 9]) + view() + "return relay(view.subspan(1,4));",
        50,
        helpers=helpers,
    )
    overloads = f"auto pick({SPAN} a)->u64{{return u64(a.at(0));}}auto pick(i64 n)->u64{{return u64(n);}}"
    suite.check(
        "overload selects span temporary",
        array("bytes", [1, 42]) + view() + "return pick(view.subspan(1,1));",
        42,
        helpers=overloads,
    )
    definitions = "class Regular { public: auto subspan(i64 a,i64 b) const ->i64{return a+b;} };"
    suite.check(
        "ordinary class method named subspan unchanged",
        "const Regular r=Regular{};return pick(r.subspan(20,22));",
        42,
        definitions=definitions,
        helpers=overloads,
    )
    definitions = (
        "class Sequence {private:i64 position;public:Sequence():position(0){}"
        "auto next()->i64{const i64 old=position;position=position+1;return old;}};"
    )
    suite.check(
        "receiver then offset count and later call arguments left to right",
        array("bytes", [41, 42, 43]) + view() + "Sequence s=Sequence();"
        "return observe(view.subspan(s.next(),s.next()),s.next());",
        412,
        definitions=definitions,
        helpers=f"auto observe({SPAN} a,i64 n)->u64{{return u64(a.at(0))*10u64+u64(n);}}",
    )
    # The bounds operation follows evaluation of both arguments.
    suite.check(
        "count expression evaluated before invalid offset trap",
        array("bytes", [42]) + view() + window(start=-1, count=f"{MAX_I64}+1") + "return 0u64;",
        Trap.OVERFLOW,
    )
    suite.check(
        "offset expression evaluated before count expression",
        array("bytes", [42]) + view() + window(start=f"{MAX_I64}+1", count=-1) + "return 0u64;",
        Trap.OVERFLOW,
    )
    suite.check(
        "multiple child arguments retain separate extents",
        array("bytes", [1, 2, 3, 4]) + view() + "return two(view.subspan(0,1),view.subspan(2,2));",
        18,
        helpers=f"auto two({SPAN} a,{SPAN} b)->u64{{return u64(a.at(0))*11u64+u64(b.at(0))+u64(b.at(1));}}",
    )
    suite.check(
        "subspan copied binary result outlives owner borrow",
        array("bytes", [9, 1, 2, 3, 4, 8])
        + "u64 value=0u64;{"
        + view()
        + "const std::ByteReadResult report=std::read_le32(view.subspan(1,4),0);"
        "value=report.value_or(0u64);}bytes[1]=99u8;return value;",
        0x04030201,
        imports=("std.binary",),
    )
    suite.check(
        "binary reader empty window is recoverable",
        array("bytes", [42]) + view() + "const std::ByteReadResult r=std::read_le32(view.subspan(1,0),0);"
        "if(r.status()!=std::ByteReadStatus::out_of_range){return 1u64;}return r.value_or(42u64);",
        42,
        imports=("std.binary",),
    )
    # Exercise six positions with class/scalar/span call-record packing and class results.
    definitions = "class Result {public:u64 v;};"
    helper = (
        f"auto mixed(i64 n,{SPAN} a,Result r,{SPAN} b,u8 byte,u64 tail)->Result{{"
        "const Result out=Result{.v=u64(n)+u64(a.at(0))+r.v+u64(b.at(0))+u64(byte)+tail};return out;}"
    )
    suite.check(
        "six mixed arguments class result and saved scalar operand",
        array("bytes", [3, 5, 7])
        + view()
        + (
            "const Result r=Result{.v=11u64};const Result out=mixed(2,view.subspan(1,1),r,view.subspan(2,1),13u"
            "8,17u64);return out.v;"
        ),
        55,
        definitions=definitions,
        helpers=helper,
    )


def lifetimes(suite):
    suite.check(
        "lexical children release before parent and owner mutation",
        array("bytes", [1, 42, 3]) + "{" + view() + window(start=1, count=1) + "const " + SPAN + " copy=part;"
        "if(copy.at(0)!=42u8){return 1u64;}}bytes[1]=17u8;return u64(bytes[1]);",
        17,
    )
    suite.check(
        "branch and closed loop subwindows release",
        array("bytes", [10, 20, 30])
        + view()
        + "u64 sum=0u64;i64 i=0;while(i<3){"
        + window(start="i", count=1)
        + "if(i==1){"
        + window("b", "part", 0, 1)
        + "sum=sum+u64(b.at(0));}"
        "else{sum=sum+u64(part.at(0));}i=i+1;}return sum;",
        60,
    )
    helper = (
        f"auto window_read({SPAN} a,bool early)->u64{{"
        + window("b", "a", 0, 1)
        + "if(early){return u64(b.at(0));}return 0u64;}"
    )
    suite.check(
        "early return releases invocation windows",
        array("bytes", [42])
        + "u64 value=0u64;{"
        + view()
        + "value=window_read(view.subspan(0,1),true);}bytes[0]=1u8;return value;",
        42,
        helpers=helper,
    )
    for label, body, diag in (
        (
            "owner write with child",
            array("bytes", [1, 2]) + view() + window(start=1, count=1) + "bytes[0]=3u8;return 0u64;",
            "cannot mutate a byte array while a span is live",
        ),
        (
            "empty child still borrows owner",
            array("bytes", [1]) + view() + window(start=1, count=0) + "bytes[0]=3u8;return 0u64;",
            "cannot mutate a byte array while a span is live",
        ),
        (
            "mutable child binding",
            array("bytes", [1]) + view() + f"{SPAN} part=view.subspan(0,1);return 0u64;",
            "span bindings must be const",
        ),
        ("child rebinding", array("bytes", [1]) + view() + window(start=0, count=1) + "part=view;return 0u64;", None),
        (
            "child leaks from block",
            array("bytes", [1]) + view() + "{" + window(start=0, count=1) + "}return u64(part.size());",
            None,
        ),
        (
            "temporary receiver chain",
            array("bytes", [1]) + view() + f"const {SPAN} part=view.subspan(0,1).subspan(0,1);return 0u64;",
            None,
        ),
        (
            "whole borrow temporary receiver",
            array("bytes", [1]) + f"const {SPAN} part=borrow_bytes(bytes).subspan(0,1);return 0u64;",
            None,
        ),
        (
            "array receiver",
            array("bytes", [1]) + f"const {SPAN} part=bytes.subspan(0,1);return 0u64;",
            "subspan requires a named live readonly span",
        ),
        (
            "scalar use",
            array("bytes", [1]) + view() + "return view.subspan(0,1);",
            "subspan requires a span binding or span argument",
        ),
        (
            "comparison",
            array("bytes", [1]) + view() + window(start=0, count=1) + "if(part==view){return 1u64;}return 0u64;",
            None,
        ),
    ):
        suite.reject(label, body, diagnostic=diag)
    for args in ("", "0", "0,1,2", "0u64,1", "0,1u8", "true,1", "0,false"):
        suite.reject(
            "wrong subspan arity or types " + args,
            array("bytes", [1]) + view() + f"const {SPAN} part=view.subspan({args});return 0u64;",
        )
    suite.reject_program(
        "span result still forbidden", f"module bad;auto escape({SPAN} a)->{SPAN}{{return a.subspan(0,0);}}"
    )
    suite.reject_program(
        "span class field still forbidden", f"module bad;class Box{{public:{SPAN} a;}};auto test()->i64{{return 0;}}"
    )
    suite.reject_program(
        "method span parameter cannot be rebound",
        f"module bad;class Box{{public:auto take({SPAN} a)->i64{{a=a;ret"
        f"urn a.size();}}}};auto test()->i64{{return 0;}}",
    )
    suite.reject(
        "span reflection still forbidden",
        array("bytes", [1]) + view() + window(start=0, count=1) + f"return u64(size_of({SPAN}));",
        diagnostic="span capabilities are unavailable to reflection",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    parser.add_argument("--artifacts", type=Path, help="scratch directory for the generated programs")
    parser.add_argument("--seed", type=int, default=23023)
    args = parser.parse_args()
    suite = Suite(args.compiler, 15, label="readonly windows")
    if args.artifacts:
        suite.runner.directory = args.artifacts.resolve()
    model(suite, args.seed)
    calls(suite)
    lifetimes(suite)
    suite.finish()


if __name__ == "__main__":
    main()
