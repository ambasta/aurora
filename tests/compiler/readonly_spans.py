#!/usr/bin/env python3
"""Independent native acceptance for bounded readonly byte spans and std.binary.

A Python byte-list model supplies expected values without inspecting compiler
layout or IR. Normal observations retain all 64 result bits; bounds failures
must be kernel-generated SIGILL at the exact named bounds UD2. Every rejected
program must exit normally with status 1 and preserve both an absent output and
an existing byte-exact output. Explicit require checks stay active under -O.

The lifetime fixtures use supported array writes after an acquired span. Source
array assignment expressions and global arrays are unavailable, so this suite
does not claim to prove later-argument mutation exclusion; direct IR tests cover
that boundary. This is bounded acceptance evidence, not a memory-safety proof.

Run: python3 tests/compiler/readonly_spans.py build/aurorac
Harness: python3 -O tests/compiler/readonly_spans.py --self-test-only
"""

from __future__ import annotations

import re
import argparse
from dataclasses import replace
from enum import Enum
import hashlib
from pathlib import Path
import random
import signal
import tempfile
import time

from unsigned_oracle import (
    Case,
    NativeRunner,
    Observation,
    UD2,
    command,
    rejected,
    require,
    validate_trap,
    validate_values,
)


ROOT = Path(__file__).resolve().parents[2]
SPAN = "builtin::span<const u8>"
CAPACITIES = (1, 3, 4, 8, 64, 4096)
MAX_U64 = (1 << 64) - 1
HIGH_BIT = 1 << 63
MIN_I64 = -(1 << 63)
MAX_I64 = (1 << 63) - 1


class Trap(Enum):
    BOUNDS = ".Laurora_bounds_trap"
    OVERFLOW = ".Laurora_overflow_trap"


def source(body, definitions="", helpers="", result="u64", imports=()):
    return (
        "module readonly_spans;"
        + "".join(f"import {name};" for name in imports)
        + definitions
        + helpers
        + f"auto test()->{result}{{{body}}}"
    )


def array(name, values, *, const=False, alias=False):
    require(1 <= len(values) <= 4096, "invalid model array capacity")
    require(all(0 <= value <= 255 for value in values), "invalid model byte")
    spelling = "array" if alias else "builtin::array"
    return (
        f"{'const ' if const else ''}{spelling}<u8,{len(values)}> {name}={{"
        + ",".join(f"{value}u8" for value in values)
        + "};"
    )


def view(name="view", owner="bytes"):
    return f"const {SPAN} {name}=borrow_bytes({owner});"


def checksum(values):
    return sum((index + 1) * value for index, value in enumerate(values))


def decode(values, offset, endian):
    if offset < 0 or len(values) < 4 or offset > len(values) - 4:
        return None
    return int.from_bytes(bytes(values[offset : offset + 4]), endian)


class Suite:
    def __init__(self, directory, compiler, timeout, keep_going, *, compiler_timeout=None):
        self.runner = NativeRunner(directory, compiler, timeout)
        self.compiler_timeout = timeout if compiler_timeout is None else compiler_timeout
        self.keep_going = keep_going
        self.count = self.traps = self.rejections = 0
        self.failures = []

    def check(self, name, body, expected=MAX_U64, definitions="", helpers="", result="u64", imports=()):
        program = source(body, definitions, helpers, result, imports)
        path = self.runner.directory / "input.au"
        output = self.runner.directory / "compiled.s"
        path.write_text(program)
        output.unlink(missing_ok=True)
        try:
            command(
                [self.runner.compiler, "--module-root", ROOT / "library", path, "-o", output],
                timeout=self.compiler_timeout,
            )
            require(path.read_text() == program, name + ": compiler changed source")
            observed, symbols = self.runner.assemble(output.read_text(), ["test"])
            if isinstance(expected, Trap):
                validate_trap(observed, expected, symbols, name)
                self.traps += 1
            else:
                validate_values(observed, [Case(name, body, expected, result)])
            self.count += 1
            print("PASS readonly spans", name, flush=True)
        except AssertionError as failure:
            details = f"{name}: {failure}\nReproduction source:\n{program}"
            if not self.keep_going:
                raise AssertionError(details) from failure
            self.failures.append(details)
            print("FAIL readonly spans", details, flush=True)

    def reject(self, name, body, definitions="", helpers="", imports=(), diagnostic=None):
        self.reject_program(name, source(body, definitions, helpers, imports=imports), diagnostic)

    def reject_program(self, name, program, diagnostic=None):
        try:
            path = self.runner.directory / "invalid.au"
            path.write_text(program)
            output = self.runner.directory / "rejected.s"
            sentinel = b"readonly spans existing output\n\x00\xff"
            for existing in (False, True):
                output.unlink(missing_ok=True)
                if existing:
                    output.write_bytes(sentinel)
                observed = command(
                    [self.runner.compiler, "--module-root", ROOT / "library", path, "-o", output],
                    timeout=self.compiler_timeout,
                    allow_rejection=True,
                )
                require(
                    observed.returncode == 1
                    and re.fullmatch(
                        rf"(?:{re.escape(str(path))}:[1-9][0-9]*:[1-9][0-9]*|aurorac): error "
                        r"AU(?:100[12]|200[123]|3001|4001): [^\n]+\n",
                        observed.stderr.decode(errors="strict"),
                    )
                    is not None,
                    f"{name}: expected normal compiler rejection, got {observed.returncode}: {observed.stderr!r}",
                )
                if diagnostic is not None:
                    require(
                        diagnostic.encode() in observed.stderr,
                        f"{name}: wrong reason for rejection: {observed.stderr!r}",
                    )
                require(path.read_text() == program, name + ": compiler changed source")
                if existing:
                    require(output.read_bytes() == sentinel, name + ": rejection changed output")
                else:
                    require(not output.exists(), name + ": rejection created an artifact")
            self.rejections += 1
            print("PASS span rejection", name, flush=True)
        except AssertionError as failure:
            details = f"{failure}\nReproduction source:\n{program}"
            if not self.keep_going:
                raise AssertionError(details) from failure
            self.failures.append(details)
            print("FAIL span rejection", name, details, flush=True)


def self_tests(suite):
    require(checksum([0, 128, 255]) == 1021, "bad independent checksum")
    require(
        decode([1, 2, 3, 4], 0, "little") == 0x04030201 and decode([1, 2, 3, 4], 0, "big") == 0x01020304,
        "bad independent endian model",
    )
    for offset in (MIN_I64, -1, 1, MAX_I64):
        require(decode([1, 2, 3, 4], offset, "little") is None, "bad independent offset model")
    require(decode([1, 2, 3], 0, "little") is None, "short input accepted")
    full = Observation(MAX_U64.to_bytes(8, "little"), exit_code=0)
    validate_values(full, [Case("all 64 result bits", "", MAX_U64)])
    rejected(lambda: validate_values(full, [Case("low-byte-only result", "", 255)]), "truncated result")
    for observed in (
        replace(full, output=full.output[:-1]),
        replace(full, output=full.output + b"x"),
        replace(full, exit_code=1),
        replace(full, terminal_signal=signal.SIGILL),
    ):
        rejected(
            lambda observed=observed: validate_values(observed, [Case("invalid native result", "", MAX_U64)]),
            "invalid result",
        )
    symbols = {Trap.BOUNDS.value: 4096, Trap.OVERFLOW.value: 8192}
    good = Observation(
        b"", terminal_signal=signal.SIGILL, delivery_signal=signal.SIGILL, pc=4096, instruction=UD2, signal_code=2
    )
    validate_trap(good, Trap.BOUNDS, symbols, "bounds observer")
    for observed in (
        replace(good, pc=8192),
        replace(good, instruction=0x9090),
        replace(good, signal_code=0),
        replace(good, output=bytes(8)),
        replace(good, terminal_signal=signal.SIGSEGV),
        replace(good, delivery_signal=signal.SIGFPE),
    ):
        rejected(
            lambda observed=observed: validate_trap(observed, Trap.BOUNDS, symbols, "invalid bounds fault"),
            "invalid fault",
        )
    assembly = (
        ".text\n.globl test\ntest:\n.Laurora_bounds_trap:\nud2\n"
        ".Laurora_overflow_trap:\nud2\n"
        '.section .note.GNU-stack,"",@progbits\n'
    )
    observed, actual_symbols = suite.runner.assemble(assembly, ["test"])
    validate_trap(observed, Trap.BOUNDS, actual_symbols, "native exact bounds UD2")
    rejected(lambda: validate_trap(observed, Trap.OVERFLOW, actual_symbols, "wrong site"), "wrong native site")
    print("PASS span harness: independent model, 64-bit results, exact bounds UD2", flush=True)


def model_cases(suite, seed, steps):
    rng = random.Random(seed)
    for capacity in CAPACITIES:
        values = [rng.randrange(256) for _ in range(capacity)]
        values[0] = 255
        if capacity > 1:
            values[-1] = 128
        body = array("bytes", values, alias=(capacity % 2 == 1)) + view()
        body += (
            f"if(view.size()!={capacity}){{return 1u64;}}"
            "i64 i=0;u64 total=0u64;while(i<view.size()){"
            "total=total+u64(view.at(i))*u64(i+1);i=i+1;}"
            f"return {HIGH_BIT}u64+total;"
        )
        suite.check(f"seed {seed}: every byte and exact size at capacity {capacity}", body, HIGH_BIT + checksum(values))
        suite.check(
            f"const owner and signed size at capacity {capacity}",
            array("bytes", values, const=True) + view() + f"if(view.at(0)!=255u8){{return -1;}}return view.size();",
            capacity,
            result="i64",
        )

        # Each round acquires two shared views, checks Python's current byte
        # state, releases them lexically, and only then updates the real owner.
        model = values.copy()
        body = array("bytes", model)
        for step in range(steps):
            index = rng.randrange(capacity)
            replacement = rng.randrange(256)
            body += (
                "{" + view() + f"const {SPAN} copy=view;"
                f"if(copy.size()!={capacity}){{return 1u64;}}"
                f"if(copy.at({index})!={model[index]}u8){{return 2u64;}}"
                "i64 i=0;u64 sum=0u64;while(i<copy.size()){"
                "sum=sum+u64(copy.at(i))*u64(i+1);i=i+1;}"
                f"if(sum!={checksum(model)}u64){{return 3u64;}}"
                f"}}bytes[{index}]={replacement}u8;"
            )
            model[index] = replacement
        body += view() + "i64 i=0;u64 total=0u64;while(i<view.size()){"
        body += "total=total+u64(view.at(i))*u64(i+1);i=i+1;}"
        body += f"return {HIGH_BIT}u64+total;"
        suite.check(
            f"seed {seed}: {steps} acquire/copy/release/write rounds {capacity}", body, HIGH_BIT + checksum(model)
        )


def lifetime_cases(suite):
    initial = array("bytes", [17, 128, 255])
    done = f"return {MAX_U64}u64;"
    suite.check(
        "private receiver array supports a local readonly span",
        "Hidden h=Hidden();return h.get();",
        expected=0,
        definitions="class Hidden{array<u8,3> bytes;public:Hidden():bytes{}{}auto get()const->u64{"
        + view()
        + "return u64(view.at(0));}};",
    )
    suite.check(
        "shared views permit owner reads and independent mutable array copies",
        initial + view("first") + view("second") + "array<u8,3> independent=bytes;independent[1]=9u8;"
        "if(bytes[1]!=128u8){return 1u64;}"
        "if(first.at(1)!=128u8){return 2u64;}"
        "if(second.at(2)!=255u8){return 3u64;}"
        "if(independent[1]!=9u8){return 4u64;}" + done,
    )
    suite.check(
        "nested span copies retain outer view and release before owner write",
        initial
        + "{"
        + view()
        + "{"
        + f"const {SPAN} copy=view;"
        + "{"
        + f"const {SPAN} third=copy;"
        + "if(third.at(2)!=255u8){return 1u64;}}"
        "if(copy.at(1)!=128u8){return 2u64;}}"
        "if(view.at(0)!=17u8){return 3u64;}}"
        "bytes[2]=42u8;" + "{" + view("again") + "if(again.at(2)!=42u8){return 4u64;}}" + done,
    )
    for condition in ("true", "false"):
        suite.check(
            f"both branch-local copies expire at join ({condition})",
            initial + f"if({condition}){{" + view() + f"const {SPAN} copy=view;if(copy.at(0)!=17u8){{return 1u64;}}"
            "}else{" + view() + f"const {SPAN} copy=view;"
            "if(copy.at(2)!=255u8){return 2u64;}}"
            "bytes[1]=42u8;if(bytes[1]!=42u8){return 3u64;}" + done,
        )
    suite.check(
        "loop scopes release all copies on every backedge",
        initial + "i64 pass=0;while(pass<8){{" + view() + f"const {SPAN} copy=view;"
        "if(copy.at(0)!=u8(pass+17)){return 1u64;}"
        "}bytes[0]=u8(pass+18);pass=pass+1;}"
        "bytes[2]=42u8;if(bytes[0]!=25u8){return 2u64;}" + done,
    )
    suite.check(
        "zero-iteration loop leaves owner writable",
        initial + "while(false){" + view() + "if(view.at(0)==0u8){return 1u64;}}"
        "bytes[0]=42u8;if(bytes[0]!=42u8){return 2u64;}" + done,
    )
    for condition in ("true", "false"):
        helper = (
            f"auto choose(bool early)->u64{{{initial}if(early){{{view()}"
            f"const {SPAN} copy=view;return u64(copy.at(2));}}"
            "bytes[2]=42u8;return u64(bytes[2]);}"
        )
        suite.check(
            f"returning borrow path permits continuing owner write ({condition})",
            f"return choose({condition});",
            255 if condition == "true" else 42,
            helpers=helper,
        )
    suite.check(
        "return inside loop releases nested views on caller return",
        "return early();",
        255,
        helpers=f"auto early()->u64{{{initial}i64 pass=0;while(pass<2){{" + view() + f"const {SPAN} copy=view;"
        "if(pass==1){return u64(copy.at(2));}pass=pass+1;}return 0u64;}",
    )
    suite.check(
        "same local name in sibling scopes has independent provenance",
        "{" + array("bytes", [255]) + view() + "if(view.at(0)!=255u8){return 1u64;}}"
        "{"
        + array("bytes", [128, 42])
        + view()
        + "if(view.size()!=2){return 2u64;}if(view.at(1)!=42u8){return 3u64;}}"
        + done,
    )


def call_cases(suite):
    helpers = (
        f"auto leaf({SPAN} bytes,i64 index)->u64{{const {SPAN} copy=bytes;"
        "return u64(copy.at(index));}"
        f"auto middle({SPAN} bytes,i64 index)->u64{{const {SPAN} copy=bytes;"
        "return leaf(copy,index);}"
        f"auto outer({SPAN} bytes,i64 index)->u64{{return middle(bytes,index);}}"
    )
    suite.check(
        "nested ordinary calls forward existing span and local copies",
        array("bytes", [0, 128, 255, 17]) + view() + "return outer(view,2);",
        255,
        helpers=helpers,
    )
    suite.check(
        "temporary borrow arguments end before following owner write",
        array("bytes", [0, 128, 255, 17]) + "if(outer(borrow_bytes(bytes),2)!=255u64){return 1u64;}"
        "bytes[2]=42u8;return outer(borrow_bytes(bytes),2);",
        42,
        helpers=helpers,
    )
    suite.check(
        "synchronous forwarding accepts const local origin",
        array("bytes", [0, 128, 255, 17], const=True) + "return outer(borrow_bytes(bytes),1);",
        128,
        helpers=helpers,
    )

    names = "abcdef"
    groups = [
        [(slot * 37 + index * 13 + 128) % 256 for index in range(capacity)] for slot, capacity in enumerate(CAPACITIES)
    ]
    helper = "auto six(" + ",".join(f"{SPAN} {name}" for name in names) + ")->u64{"
    for name, values in zip(names, groups):
        helper += f"if({name}.size()!={len(values)}){{return 1u64;}}"
    helper += f"u64 total={HIGH_BIT}u64;"
    for slot, (name, values) in enumerate(zip(names, groups)):
        helper += (
            f"total=total+u64({name}.at(0))*{slot * 2 + 1}u64;"
            f"total=total+u64({name}.at({len(values) - 1}))*{slot * 2 + 2}u64;"
        )
    helper += "return total;}"
    expected = HIGH_BIT + sum(
        values[0] * (slot * 2 + 1) + values[-1] * (slot * 2 + 2) for slot, values in enumerate(groups)
    )
    for temporary in (False, True):
        body = "".join(array(name, values) for name, values in zip(names, groups))
        if not temporary:
            body += "".join(view(f"v{name}", name) for name in names)
        arguments = ",".join(f"borrow_bytes({name})" if temporary else f"v{name}" for name in names)
        suite.check(
            f"six distinct source span parameters ({'temporary' if temporary else 'named'})",
            body + f"return six({arguments});",
            expected,
            helpers=helper,
        )

    definitions = (
        "class Tiny{public:u8 value;Tiny(u8 n):value(n){} };"
        "class Report{public:u8 first;u64 wide;u8 last;"
        "Report(u8 a,u64 b,u8 c):last(c),wide(b),first(a){} };"
    )
    helper = (
        f"auto collect(u64 wide,{SPAN} first,Tiny small,{SPAN} second,i64 index,"
        f"{SPAN} third)->Report{{"
        "if(first.size()!=3){const Report bad=Report(0u8,1u64,0u8);return bad;}"
        "if(second.size()!=4){const Report bad=Report(0u8,2u64,0u8);return bad;}"
        "if(third.size()!=8){const Report bad=Report(0u8,3u64,0u8);return bad;}"
        "const Report result=Report(first.at(index),wide+u64(small.value)"
        "+u64(second.at(3)),third.at(7));return result;}"
        f"auto forward({SPAN} a,{SPAN} b,{SPAN} c,Tiny small)->Report{{"
        f"const {SPAN} copy=a;const Report result=collect({HIGH_BIT}u64,copy,small,b,1,c);"
        "return result;}"
    )
    suite.check(
        "nested mixed scalar/class/span arguments preserve a copied class result",
        array("a", [1, 128, 3])
        + array("b", [4, 5, 6, 255])
        + array("c", [7, 8, 9, 10, 11, 12, 13, 254])
        + "Tiny small=Tiny(42u8);"
        "const Report report=forward(borrow_bytes(a),borrow_bytes(b),borrow_bytes(c),small);"
        "small.value=0u8;a[1]=0u8;b[3]=0u8;c[7]=0u8;"
        "if(report.first!=128u8){return 1u64;}if(report.last!=254u8){return 2u64;}"
        "return report.wide;",
        HIGH_BIT + 42 + 255,
        definitions=definitions,
        helpers=helper,
    )


def bounds_cases(suite):
    for capacity in CAPACITIES:
        values = [(index * 29 + 128) % 256 for index in range(capacity)]
        for index in (0, capacity - 1):
            suite.check(
                f"in-range span boundary {index} of {capacity}",
                array("bytes", values) + view() + f"return u64(view.at({index}));",
                values[index],
            )
        for index in (MIN_I64, -1, capacity, MAX_I64):
            suite.check(
                f"exact span bounds failure {index} of {capacity}",
                array("bytes", values) + view() + f"return u64(view.at({index}));",
                Trap.BOUNDS,
            )
    suite.check(
        "forwarded span retains length at checked read",
        array("bytes", [128, 255, 42]) + "return at(borrow_bytes(bytes),3);",
        Trap.BOUNDS,
        helpers=f"auto at({SPAN} bytes,i64 index)->u64{{return u64(bytes.at(index));}}",
    )


def rejection_cases(suite):
    base = array("bytes", [1, 128, 255])
    done = f"return {MAX_U64}u64;"
    # These are real supported array assignment statements. Each program first
    # acquires a valid span, making the rejection lifetime evidence.
    lifetime_bodies = (
        ("owner write with one live view", view() + "bytes[0]=2u8;" + done),
        (
            "owner write after last read still has lexical view",
            view() + "const u8 read=view.at(0);bytes[1]=2u8;return u64(read);",
        ),
        (
            "nested copy cannot release original owner loan",
            view() + "{" + f"const {SPAN} copy=view;}}bytes[0]=2u8;" + done,
        ),
        (
            "independent second loan survives inner release",
            view("first") + "{" + view("second") + "}bytes[0]=2u8;" + done,
        ),
        ("branch write conflicts with outer loan", view() + "if(true){bytes[0]=2u8;}" + done),
        ("loop write conflicts with outer loan", view() + "i64 i=0;while(i<1){bytes[0]=2u8;i=i+1;}" + done),
        (
            "nested copies prevent write in innermost scope",
            view() + "{" + f"const {SPAN} copy=view;{{const {SPAN} third=copy;bytes[0]=2u8;}}}}" + done,
        ),
        ("ordinary forwarding does not end named view loan", view() + "consume(view);bytes[0]=2u8;" + done),
    )
    consume = f"auto consume({SPAN} bytes)->u64{{return u64(bytes.at(0));}}"
    for name, body in lifetime_bodies:
        suite.reject(name, base + body, helpers=consume, diagnostic="cannot mutate a byte array while a span is live")

    bodies = (
        ("span binding must be const", f"{SPAN} v=borrow_bytes(bytes);" + done),
        ("span copy binding must be const", view() + f"{SPAN} copy=view;" + done),
        ("span cannot be rebound", view() + "view=borrow_bytes(bytes);" + done),
        (
            "inner origin cannot escape by outer assignment",
            view("outer") + "{" + array("inner", [42]) + "outer=borrow_bytes(inner);}" + done,
        ),
        ("view cannot escape its lexical scope", "{" + view() + "}return u64(view.at(0));"),
        ("span requires an initializer", f"const {SPAN} v;" + done),
        ("span origin cannot be an array element", f"const {SPAN} v=borrow_bytes(bytes[0]);" + done),
        ("span origin cannot be an array literal", f"const {SPAN} v=borrow_bytes({{1u8}});" + done),
        ("span origin cannot be an existing span", view() + view("copy", "view") + done),
        ("span cannot be forged from an integer", f"const {SPAN} v=0;" + done),
        ("span cannot be used as scalar result", view() + "return view;"),
        ("span cannot be explicitly converted to scalar", view() + "return u64(view);"),
        ("span cannot participate in arithmetic", view() + "return view+1u64;"),
        ("span cannot participate in scalar equality", view() + "if(view==view){return 1u64;}" + done),
        ("span cannot be used as condition", view() + "if(view){return 1u64;}" + done),
        ("span cannot use general indexing", view() + "return u64(view[0]);"),
        ("span read cannot be an assignment target", view() + "view.at(0)=2u8;" + done),
        ("span has no mutable setter", view() + "view.set(0,2u8);" + done),
        ("span subspan requires a binding or call argument", view() + "view.subspan(0,1);" + done),
        ("span index requires signed i64", view() + "return u64(view.at(0u64));"),
        ("span index rejects a byte", view() + "return u64(view.at(0u8));"),
        ("span index rejects bool", view() + "return u64(view.at(false));"),
        ("span at requires one argument", view() + "return u64(view.at());"),
        ("span size requires no argument", view() + "return u64(view.size(0));"),
        ("span is not accepted by array len", view() + "return u64(len(view));"),
        ("span has no public pointer", view() + "return view.data;"),
        ("span cannot convert to array", view() + "array<u8,3> copy=view;" + done),
    )
    for name, body in bodies:
        suite.reject(name, base + body)
    for scalar, literal in (("i64", "42"), ("u64", "42u64"), ("bool", "true")):
        suite.reject(
            f"borrow origin array element type {scalar} rejected",
            f"array<{scalar},1> values={{{literal}}};" + view("v", "values") + done,
        )
    suite.reject("borrow origin cannot be a byte scalar", "u8 bytes=42u8;" + view() + done)
    for spelling in ("builtin::span<u8>", "builtin::span<const i64>", "span<const u8>", "std::span<const u8>"):
        suite.reject(f"unsupported span type {spelling}", base + f"const {spelling} v=borrow_bytes(bytes);" + done)
    for query in ("size_of", "type_id", "field_count"):
        suite.reject(f"span rejects {query} reflection", f"const i64 fact={query}({SPAN});return u64(fact);")
    suite.reject("span rejects runtime metadata through type id", f"return u64(reflect_size(type_id({SPAN})));")
    for constraint in ("Value", "Scalar"):
        suite.reject(
            f"span is not a {constraint} template argument",
            base + view() + f"const Box<{SPAN}> box=Box<{SPAN}>(view);" + done,
            definitions=f"template<{constraint} T>class Box{{T payload;public:Box(T value):payload(value){{}}}};",
        )
    for visibility in ("", "public:"):
        suite.reject(
            "span cannot be a " + ("public" if visibility else "private") + " field",
            done,
            definitions=f"class Bad{{{visibility}{SPAN} payload;}};",
        )
    suite.reject_program(
        "span cannot be returned from local origin", f"module bad;auto leak()->{SPAN}{{{base}{view()}return view;}}"
    )
    suite.reject_program(
        "span parameter cannot escape through return", f"module bad;auto leak({SPAN} input)->{SPAN}{{return input;}}"
    )
    suite.reject_program(
        "span cannot be global", f"module bad;const {SPAN} global=borrow_bytes(bytes);auto test()->u64{{{done}}}"
    )
    suite.reject(
        "span parameter is immutable",
        base + "return mutate(borrow_bytes(bytes));",
        helpers=f"auto mutate({SPAN} input)->u64{{input=input;return 0u64;}}",
    )
    suite.reject(
        "seven source parameters exceed the bounded call contract",
        base + "return many(borrow_bytes(bytes),1,2,3,4,5,6);",
        helpers=f"auto many({SPAN} a,i64 b,i64 c,i64 d,i64 e,i64 f,i64 g)->u64{{return u64(a.at(0));}}",
    )
    suite.reject(
        "method span parameter cannot be rebound",
        done,
        definitions=f"class Bad{{public:Bad(){{}}auto take({SPAN} bytes)const->u64{{"
        f"bytes=bytes;return u64(bytes.at(0));}}}};",
    )
    suite.reject(
        "span parameter cannot appear on a constructor", done, definitions=f"class Bad{{public:Bad({SPAN} bytes){{}}}};"
    )
    suite.reject(
        "private class array cannot be borrowed by caller",
        "Hidden h=Hidden();" + f"const {SPAN} v=borrow_bytes(h.bytes);" + done,
        definitions="class Hidden{array<u8,3> bytes;public:Hidden():bytes{}{} };",
    )
    suite.reject(
        "std array private storage cannot become an alias",
        "std::array<u8,3> bytes=std::array<u8,3>();" + f"const {SPAN} v=borrow_bytes(bytes.elements);" + done,
        imports=("std.array",),
    )
    suite.reject(
        "std array value is not a builtin byte-array origin",
        "std::array<u8,3> bytes=std::array<u8,3>();" + view() + done,
        imports=("std.array",),
    )
    for capacity in (0, 4097):
        suite.reject(
            f"builtin byte array capacity {capacity} rejected",
            f"builtin::array<u8,{capacity}> bytes={{1u8}};" + view() + done,
        )


def binary_cases(suite, seed, steps):
    rng = random.Random(seed ^ 0xB14A)
    for capacity in CAPACITIES:
        values = [rng.randrange(256) for _ in range(capacity)]
        if capacity >= 4:
            values[:4] = [0, 128, 255, 1]
        # Signed extremes must fail before addition or indexing. Duplicate
        # boundaries collapse only within this particular byte-array model.
        offsets = {MIN_I64, -1, 0, capacity - 4, capacity - 3, capacity - 1, capacity, MAX_I64}
        offsets.update(rng.randrange(-4, capacity + 5) for _ in range(steps))
        for endian, native in (("little", "le"), ("big", "be")):
            body = array("bytes", values) + view()
            for index, offset in enumerate(sorted(offsets)):
                expected = decode(values, offset, endian)
                status = "out_of_range" if expected is None else "success"
                body += (
                    f"const std::ByteReadResult r{index}=std::read_{native}32(view,{offset});"
                    f"if(r{index}.status()!=std::ByteReadStatus::{status}){{return 1u64;}}"
                    f"if(r{index}.value_or(0u64)!={0 if expected is None else expected}u64){{return 2u64;}}"
                    f"if(r{index}.value_or({MAX_U64}u64)!={MAX_U64 if expected is None else expected}u64)"
                    "{return 3u64;}"
                )
            body += f"return {MAX_U64}u64;"
            suite.check(
                f"std.binary {native} capacity {capacity}: {len(offsets)} independent offsets",
                body,
                imports=("std.binary",),
            )
    for native in ("le", "be"):
        for values in ([0, 0, 0, 0], [255, 255, 255, 255], [1, 2, 3, 4]):
            expected = decode(values, 0, "little" if native == "le" else "big")
            suite.check(
                f"std.binary {native} copied result survives owner rewrite {values}",
                array("bytes", values)
                + f"const std::ByteReadResult report=std::read_{native}32(borrow_bytes(bytes),0);"
                "bytes[0]=17u8;const std::ByteReadResult copy=report;"
                "if(copy.status()!=std::ByteReadStatus::success){return 18446744073709551615u64;}"
                "return copy.value_or(99u64);",
                expected,
                imports=("std.binary",),
            )
    suite.check(
        "ByteReadResult failure masks a deliberately nonzero payload",
        f"const std::ByteReadResult report=std::ByteReadResult(std::ByteReadStatus::out_of_range,{MAX_U64}u64);"
        "if(report.status()!=std::ByteReadStatus::out_of_range){return 1u64;}"
        "if(report.value_or(0u64)!=0u64){return 2u64;}"
        f"return report.value_or({HIGH_BIT + 42}u64);",
        HIGH_BIT + 42,
        imports=("std.binary",),
    )
    suite.check(
        "ByteReadResult success preserves all 64 payload bits",
        f"const std::ByteReadResult report=std::ByteReadResult(std::ByteReadStatus::success,{MAX_U64}u64);"
        "return report.value_or(0u64);",
        imports=("std.binary",),
    )
    for expression in ("std::read_le32(view,0u64)", "std::read_be32(view,0u8)", "std::read_le32(bytes,0)"):
        suite.reject(
            "std.binary exact parameter types: " + expression,
            array("bytes", [1, 2, 3, 4])
            + view()
            + f"const std::ByteReadResult result={expression};return result.value_or(0u64);",
            imports=("std.binary",),
        )
    for field, expression in (
        ("outcome", "report.outcome==std::ByteReadStatus::success"),
        ("value", "report.value==42u64"),
    ):
        suite.reject(
            f"ByteReadResult {field} remains private",
            "const std::ByteReadResult report=std::ByteReadResult(std::ByteReadStatus::success,42u64);"
            + f"if({expression}){{return 1u64;}}return 0u64;",
            imports=("std.binary",),
            diagnostic="private class field is inaccessible",
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", nargs="?", type=Path, default=ROOT / "build/aurorac")
    parser.add_argument("--self-test-only", action="store_true")
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument("--seed", type=int, default=14014)
    parser.add_argument("--steps", type=int, default=16)
    parser.add_argument(
        "--timeout", type=float, help="override both compiler and native watchdogs (defaults: 45 and 10 seconds)"
    )
    args = parser.parse_args()
    require((args.timeout is None or args.timeout > 0) and 1 <= args.steps <= 64, "invalid timeout or steps")
    # Omission separates host compilation from native execution; an explicit
    # legacy --timeout still controls both, as do existing imported Suite callers.
    native_timeout = 10 if args.timeout is None else args.timeout
    compiler_timeout = 45 if args.timeout is None else args.timeout
    compiler = args.compiler.resolve()
    started = time.monotonic()
    if not args.self_test_only:
        print(
            f"INFO readonly spans compiler={compiler} "
            f"sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()} "
            f"seed={args.seed} steps={args.steps}",
            flush=True,
        )
    with tempfile.TemporaryDirectory(prefix="aurora-readonly-spans-") as temporary:
        suite = Suite(Path(temporary), compiler, native_timeout, args.keep_going, compiler_timeout=compiler_timeout)
        self_tests(suite)
        if args.self_test_only:
            return
        model_cases(suite, args.seed, args.steps)
        lifetime_cases(suite)
        call_cases(suite)
        bounds_cases(suite)
        rejection_cases(suite)
        binary_cases(suite, args.seed, args.steps)
        require(not suite.failures, f"{len(suite.failures)} readonly-span cases failed")
        print(
            f"PASS readonly spans: {suite.count} native cases including {suite.traps} exact bounds traps; "
            f"{suite.rejections} rejection cases, each with absent and existing output; "
            f"{time.monotonic() - started:.2f}s",
            flush=True,
        )


if __name__ == "__main__":
    main()
