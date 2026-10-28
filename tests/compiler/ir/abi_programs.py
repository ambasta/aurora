#!/usr/bin/env python3
"""Generate the large direct-IR programs of the native ABI runners as .air text.

Each program is a loop over call shapes, as the C++ producers it replaces were;
the output is one case file whose first case is the program for
`aurora-ir-check --output FILE CASE`. Modules are written in plain form
(tests/compiler/ir/README.md).

usage: abi_programs.py method-spans|borrowed-objects|logical-spans|sector-values|short-circuit OUT
"""

import sys

I64, U8, U64, BOOL, SPAN = "i64", "u8", "u64", "bool", "span"
BOX = "(class Box)"


def cls(name):
    return f"(class {name})"


def items(values):
    return "[" + " ".join(str(value) for value in values) + "]"


class Fn:
    def __init__(self, name, result=I64, params=()):
        self.name, self.result, self.params = name, result, list(params)
        self.frame, self.receiver, self.roots, self.rootmut, self.spanfield = 0, None, 0, 0, None
        self.slots, self.objects, self.arrays, self.spans, self.code = {}, {}, {}, set(), []

    def add(self, *code):
        """Append instructions; one string may hold several separated by "; "."""
        for text in code:
            self.code.extend(text.split("; "))

    def text(self):
        out = [f"function {self.name}", f"  result {self.result}"]
        if self.params:
            out.append(f"  params {items(self.params)}")
        out.append(f"  frame {self.frame}")
        if self.receiver:
            out.append(f"  receiver {self.receiver}")
        if self.roots:
            out.append(f"  roots {self.roots}")
        if self.rootmut:
            out.append(f"  rootmut {self.rootmut}")
        if self.spanfield is not None:
            out.append(f"  spanfield {self.spanfield}")
        out += [f"  slot {offset} {kind}" for offset, kind in sorted(self.slots.items())]
        out += [f"  object {offset} {name} {mutable}" for offset, (name, mutable) in sorted(self.objects.items())]
        out += [f"  array {offset} {length}" for offset, length in sorted(self.arrays.items())]
        out += [f"  span {offset}" for offset in sorted(self.spans)]
        out += ["    " + line for line in self.code]
        return "\n".join(out + ["end"]) + "\n"

    def copy(self, name):
        other = Fn(name, self.result, self.params)
        other.__dict__.update(
            {
                key: (value.copy() if hasattr(value, "copy") else value)
                for key, value in self.__dict__.items()
                if key != "name"
            }
        )
        return other


def program(case, header, functions):
    return f"; CASE: {case}\n; RUN: emit\n{header}" + "".join(f.text() for f in functions)


# Shared by the method-span, borrowed-object and logical-span producers: each new
# local takes the next 8-byte (56-byte span) slot and the frame stays 16-aligned.
def slot(f, cursor, kind, box="Box"):
    cursor[0] += 56 if kind == SPAN else 8
    at = cursor[0]
    if kind == SPAN:
        f.spans.add(at)
    elif kind.startswith("(class"):
        f.objects[at] = (box, "false")
        f.slots[at] = I64
    else:
        f.slots[at] = kind
    f.frame = (at + 15) & ~15
    return at


def bind(f, cursor, first=0):
    bound = []
    for index, kind in enumerate(f.params[first:]):
        at = slot(f, cursor, kind)
        bound.append(at)
        if kind == SPAN:
            f.add(f"BindSpanParameter {index} {at}")
        elif kind == BOX:
            f.add(f"BindObjectParameter {index} {at} Box")
        else:
            f.add(f"BindParameter {index} {at} {kind}")
    return bound


def close(f, bound, first=0):
    for kind, at in reversed(list(zip(f.params[first:], bound))):
        if kind == SPAN:
            f.add(f"EndSpan {at}")
        elif kind == BOX:
            f.add(f"EndObject {at}")


def save(f, depth, base=4294967313):
    for index in range(depth):
        f.add(f"Constant {base + index} i64", "Push")


def combine(f, depth):
    f.code += ["BinaryValue CheckedAdd"] * depth


RECEIVER_HEADER = """layout Box [i64]
layout Receiver [i64 i64]
fields Box [(i64 0 1 false)]
fields Receiver [(i64 0 1 false) (bytes 1 0 false) (i64 1 1 false)]
storage Box [0] [0] 8 8 8
storage Receiver [0 40] [0 8 40] 48 8 48
"""


def mixed(arity, mask):
    if mask < 0:
        return [I64] * arity
    return [SPAN if mask & (1 << i) else [BOX, U8, I64][i % 3] for i in range(arity)]


def span_children(f, cursor, bound, n, first, transform):
    """Spans forwarded as given or through a reborrowed 2-byte child window."""
    objects, spans, children = [0] * n, [0] * n, []
    for i in range(n):
        kind = f.params[first + i]
        if kind == SPAN:
            spans[i] = bound[i]
            if transform:
                copy, child = slot(f, cursor, SPAN), slot(f, cursor, SPAN)
                f.add(f"ReborrowSpan {bound[i]} {copy}; Constant 2 i64; Push; Constant 0 i64; Subspan {copy} {child}")
                spans[i] = child
                children += [copy, child]
        elif kind == BOX:
            objects[i] = bound[i]
    return objects, spans, children


def scalar_pushes(f, bound, n, first):
    for i in range(n):
        kind = f.params[first + i]
        if kind not in (SPAN, BOX):
            f.add(f"Load {bound[i]} {kind}", "Push")


def boxed_result(f, cursor):
    result = slot(f, cursor, BOX)
    f.add(f"BeginObject {result}; Constant 123 i64; Store {result} i64; ReturnObject {result}")


def method_spans():
    functions = [Fn("method_span_observe", I64, [SPAN])]
    observer = functions[0]
    observer.frame, observer.spans = 64, {56}
    observer.add("BindSpanParameter 0 56", "Constant 42 i64", "EndSpan 56", "Return")
    shapes = [(n, 1 << p) for n in range(1, 7) for p in range(n)] + [(6, 63), (6, 21), (6, 42)]
    for n, mask in shapes:
        for mode in range(3):
            suffix = f"{n}_{mask}_{mode}"
            target = Fn("method_span_target_" + suffix, [I64, BOX, SPAN][mode], mixed(n, mask))
            target.receiver = "Receiver false false"
            if mode == 2:
                target.spanfield = 1
            cursor = [0]
            close(target, bind(target, cursor))
            if mode == 0:
                target.add("Constant 42 i64", "Return")
            elif mode == 1:
                boxed_result(target, cursor)
            else:
                result = slot(target, cursor, SPAN)
                target.add(f"BorrowOwnedSpan 0 1 {result}", f"ReturnSpan {result}")
            functions.append(target)
            for depth in range(3):
                for transform in range(2):
                    f = Fn(f"method_span_forward_{suffix}_{depth}_{transform}", I64, target.params)
                    f.receiver = "Receiver false false"
                    cursor = [0]
                    bound = bind(f, cursor)
                    save(f, depth)
                    objects, spans, children = span_children(f, cursor, bound, n, 0, transform)
                    result = slot(f, cursor, target.result) if mode else 0
                    if mode == 1:
                        f.add(f"BeginObject {result}")
                    scalar_pushes(f, bound, n, 0)
                    f.add(f"MethodCall {target.name} 0 {items(objects)} {result} -1 {items(spans)}")
                    if mode == 1:
                        f.add(f"Load {result} i64", f"EndObject {result}")
                    if mode == 2:
                        f.add(f"AggregateCall method_span_observe [0] 0 [{result}]", f"EndSpan {result}")
                    combine(f, depth)
                    f.code += [f"EndSpan {child}" for child in reversed(children)]
                    close(f, bound)
                    f.add("Return")
                    functions.append(f)
    return program("method-spans-abi", RECEIVER_HEADER, functions)


def rooted(name, roots, rootmut, params, result=I64):
    f = Fn(name, result, params)
    f.roots, f.rootmut = roots, rootmut
    return f


def accumulate(f, total, value):
    f.add(f"Load {total} i64; Push; {value}; BinaryValue CheckedAdd; Store {total} i64")


def copied_second(f, saved, copied, receiver):
    f.add(f"Store {saved} i64; Call paired_scalar_clobber; BeginObject {copied}")
    f.add(f"MethodCall paired_copy_second {receiver} [] {copied}; Load {saved} i64; Push; Load {copied} i64")
    f.add(f"BinaryValue CheckedAdd; EndObject {copied}")


def borrowed_objects():
    functions = []
    shapes = [(n, 1 << p) for n in range(1, 6) for p in range(n)] + [(5, 31), (5, 21), (5, 10)]
    shapes += [(n, -1) for n in range(6)]
    for n, mask in shapes:
        for mode in range(2):
            suffix = f"{n}_{'scalar' if mask < 0 else mask}_{mode}"
            params = [cls("Receiver")] + mixed(n, mask)
            target = rooted("borrow_object_target_" + suffix, 1, mode, params, [I64, BOX][mode])
            cursor = [0]
            close(target, bind(target, cursor, 1), 1)
            if mode == 0:
                target.add("Constant 42 i64", "Return")
            else:
                boxed_result(target, cursor)
            functions.append(target)
            for depth in range(3):
                for transform in range(2):
                    f = rooted(f"borrow_object_forward_{suffix}_{depth}_{transform}", 1, mode, target.params)
                    cursor = [0]
                    bound = bind(f, cursor, 1)
                    f.add(f"AcquireObjectLoan 1 0 {'true' if mode else 'false'}")
                    save(f, depth)
                    objects, spans, children = span_children(f, cursor, bound, n, 1, transform)
                    result = slot(f, cursor, target.result) if mode else 0
                    if mode == 1:
                        f.add(f"BeginObject {result}")
                    scalar_pushes(f, bound, n, 1)
                    if mask < 0:
                        objects = spans = []
                    f.add(f"BorrowedCall {target.name} [(0 1 -1)] {items(objects)} {result} {items(spans)}")
                    f.add("ReleaseObjectLoan 1")
                    if mode == 1:
                        f.add(f"Load {result} i64", f"EndObject {result}")
                    combine(f, depth)
                    f.code += [f"EndSpan {child}" for child in reversed(children)]
                    close(f, bound, 1)
                    f.add("Return")
                    functions.append(f)
    # Paired roots: first mutable, second readonly, saved across scalar clobbers.
    first = Fn("paired_read_first")
    first.receiver = "Receiver true false"
    first.add("ReceiverLoad 0 i64", "Return")
    second = first.copy("paired_read_second")
    second.receiver, second.code = "Receiver false false", ["ReceiverLoad 2 i64", "Return"]
    copied = second.copy("paired_copy_second")
    copied.result, copied.frame, copied.slots, copied.objects = BOX, 16, {8: I64}, {8: ("Box", "false")}
    copied.code = ["BeginObject 8", "ReceiverLoad 2 i64", "Store 8 i64", "ReturnObject 8"]
    single = rooted("paired_single_second", 1, 0, [cls("Receiver")])
    single.add("MethodCall paired_read_second 0", "Return")
    clobber = Fn("paired_scalar_clobber")
    clobber.add("Constant 0 i64", "Return")
    functions += [first, second, copied, single, clobber]
    for arity in range(5):
        target = rooted(f"paired_target_{arity}", 2, 1, [cls("Receiver")] * 2 + [I64] * arity)
        cursor = [0]
        bound = bind(target, cursor, 2)
        total, result = slot(target, cursor, I64), slot(target, cursor, BOX)
        target.add(f"MethodCall paired_read_first 0; Store {total} i64; Call paired_scalar_clobber")
        target.add(f"BeginObject {result}; MethodCall paired_copy_second -1 [] {result}")
        accumulate(target, total, f"Load {result} i64")
        target.add(f"EndObject {result}; AcquireObjectLoan 7 -1 false")
        target.add("BorrowedCall paired_single_second [(-1 7 -1)]; ReleaseObjectLoan 7; Push")
        target.add(f"Load {total} i64; BinaryValue CheckedAdd; Store {total} i64")
        for base in bound:
            accumulate(target, total, f"Load {base} i64")
        target.add(f"Load {total} i64", "Return")
        functions.append(target)
        for depth in range(3):
            f = rooted(f"paired_forward_{arity}_{depth}", 2, 1, target.params)
            cursor = [0]
            forwarded = bind(f, cursor, 2)
            saved, copied_result = slot(f, cursor, I64), slot(f, cursor, BOX)
            f.add("AcquireObjectLoan 1 0 true", "AcquireObjectLoan 2 -1 false")
            save(f, depth)
            for base in forwarded:
                f.add(f"Load {base} i64", "Push")
            f.add(f"BorrowedCall {target.name} [(0 1 -1) (-1 2 -1)] [] 0 []; ReleaseObjectLoan 2; ReleaseObjectLoan 1")
            copied_second(f, saved, copied_result, -1)
            combine(f, depth)
            f.add("Return")
            functions.append(f)
    # Bounded roots: one to four borrowed roots and up to six total parameters.
    for roots in range(1, 5):
        for mutable_mask in sorted({0, 1, 1 << (roots - 1), (1 << roots) - 1} | ({3, 10} if roots == 4 else set())):
            for tail in range(7 - roots):
                suffix = f"{roots}_{mutable_mask}_{tail}"
                params = [cls("Receiver")] * roots + [I64] * tail
                target = rooted("bounded_target_" + suffix, roots, mutable_mask, params)
                cursor = [0]
                inputs = bind(target, cursor, roots)
                total = slot(target, cursor, I64)
                target.add("Constant 0 i64", f"Store {total} i64")
                for ordinal in range(roots):
                    target.add(f"Call paired_scalar_clobber; MethodCall paired_read_second {-ordinal}; Push")
                    target.add(f"Load {total} i64; BinaryValue CheckedAdd; Store {total} i64")
                for at in inputs:
                    target.add(f"Load {at} i64; Push; Load {total} i64; BinaryValue CheckedAdd; Store {total} i64")
                target.add(f"Load {total} i64", "Return")
                functions.append(target)
                for depth in range(3):
                    f = rooted(f"bounded_forward_{suffix}_{depth}", roots, mutable_mask, params)
                    cursor = [0]
                    arguments = bind(f, cursor, roots)
                    saved, copied_result = slot(f, cursor, I64), slot(f, cursor, BOX)
                    for ordinal in range(roots):
                        mutable = "true" if mutable_mask & (1 << ordinal) else "false"
                        f.add(f"AcquireObjectLoan {ordinal + 1} {-ordinal} {mutable}")
                    save(f, depth)
                    for at in arguments:
                        f.add(f"Load {at} i64", "Push")
                    lanes = " ".join(f"({-ordinal} {ordinal + 1} -1)" for ordinal in range(roots))
                    f.add(f"BorrowedCall {target.name} [{lanes}]")
                    f.code += [f"ReleaseObjectLoan {ordinal}" for ordinal in range(roots, 0, -1)]
                    copied_second(f, saved, copied_result, 1 - roots)
                    combine(f, depth)
                    f.add("Return")
                    functions.append(f)
    return program("borrowed-objects-abi", RECEIVER_HEADER, functions)


def logical_probe(name, params):
    f = Fn(name, I64, params)
    cursor, spans = [0], []
    for index, kind in enumerate(params):
        at = slot(f, cursor, kind)
        if kind == SPAN:
            f.add(f"BindSpanParameter {index} {at}")
            spans.append(at)
        else:
            f.add(f"BindParameter {index} {at} {kind}")
    f.add("Constant 42 i64")
    f.code += [f"EndSpan {at}" for at in spans]
    f.add("Return")
    return f


def logical_forwarding():
    functions = []
    shapes = [(n, 1 << p) for n in range(1, 7) for p in range(n)] + [(2, 3), (3, 5), (4, 10), (6, 63), (6, 21)]
    for arity, mask in shapes:
        params = [SPAN if mask & (1 << i) else [I64, U8, BOOL][i % 3] for i in range(arity)]
        suffix = f"{arity}_{mask}"
        target = "abi_probe_" + suffix
        functions.append(logical_probe(target, params))
        for transform in range(3):
            for depth in range(3):
                f = Fn(f"abi_forward_{suffix}_{transform}_{depth}", I64, params)
                cursor, slots, spans, lifetimes = [0], [], [0] * arity, []
                for i, kind in enumerate(params):
                    at = slot(f, cursor, kind)
                    slots.append(at)
                    if kind == SPAN:
                        f.add(f"BindSpanParameter {i} {at}")
                        spans[i] = at
                        lifetimes.append(at)
                    else:
                        f.add(f"BindParameter {i} {at} {kind}")
                save(f, depth)
                for i, kind in enumerate(params):
                    if kind != SPAN:
                        continue
                    if transform >= 1:
                        copy = slot(f, cursor, SPAN)
                        f.add(f"ReborrowSpan {spans[i]} {copy}")
                        spans[i] = copy
                        lifetimes.append(copy)
                    if transform == 2:
                        for offset, count in ((3, 7), (2, 3)):
                            child = slot(f, cursor, SPAN)
                            f.add(f"Constant {offset} i64; Push; Constant {count} i64; Subspan {spans[i]} {child}")
                            spans[i] = child
                            lifetimes.append(child)
                for i, kind in enumerate(params):
                    if kind != SPAN:
                        f.add(f"Load {slots[i]} {kind}", "Push")
                f.add(f"AggregateCall {target} {items([0] * arity)} 0 {items(spans)}")
                combine(f, depth)
                f.code += [f"EndSpan {at}" for at in reversed(lifetimes)]
                f.add("Return")
                functions.append(f)
    functions.append(logical_probe("abi_probe_one", [SPAN]))
    for depth in range(4):
        f = Fn(f"abi_read_{depth}", I64, [SPAN])
        f.frame, f.spans = 64, {56}
        f.add("BindSpanParameter 0 56")
        save(f, depth)
        f.add("Constant 4 i64", "SpanLoad 56", "Convert u8 i64")
        combine(f, depth)
        f.add("EndSpan 56", "Return")
        functions.append(f)
    for depth in range(3):
        f = Fn(f"abi_array_mint_{depth}")
        f.frame, f.arrays, f.spans = 208, {32: 32}, {88, 144, 200}
        f.add("BeginArray 32")
        for i in range(32):
            f.slots[32 - i] = U8
            f.add(f"Constant {(11 + i * 7) % 256} u8", f"Store {32 - i} u8")
        save(f, depth)
        f.add("BorrowSpan 32 88; ReborrowSpan 88 144; Constant 3 i64; Push; Constant 7 i64; Subspan 144 200")
        f.add("AggregateCall abi_probe_one [0] 0 [200]")
        combine(f, depth)
        f.add("EndSpan 200", "EndSpan 144", "EndSpan 88", "EndArray 32", "Return")
        functions.append(f)
    return functions


def result_parameters(mode):
    return [[], [I64], [I64] * 6, [BOX, I64, BOX, U8, I64, BOOL]][mode]


def logical_owned():
    functions = []
    for mode in range(4):
        f = Fn(f"abi_result_{mode}", SPAN, result_parameters(mode))
        f.receiver, f.spanfield = "Receiver false false", 1
        cursor, parameters = [0], []
        for index, kind in enumerate(f.params):
            at = slot(f, cursor, kind)
            parameters.append(at)
            f.add(f"BindObjectParameter {index} {at} Box" if kind == BOX else f"BindParameter {index} {at} {kind}")
        root, copy, window = (slot(f, cursor, SPAN) for _ in range(3))
        f.add(f"BorrowOwnedSpan 0 1 {root}", f"ReborrowSpan {root} {copy}")
        f.add("Constant 3 i64" if mode == 0 else f"Load {parameters[{3: 4, 2: 5}.get(mode, 0)]} i64", "Push")
        f.add(f"Load {parameters[0]} i64" if mode == 3 else "Constant 7 i64", f"Subspan {copy} {window}")
        f.code += [f"EndObject {at}" for kind, at in zip(f.params, parameters) if kind == BOX]
        f.add(f"ReturnSpan {window}")
        functions.append(f)
        for depth in range(3):
            g = Fn(f"abi_use_result_{mode}_{depth}")
            g.receiver = "Receiver false false"
            cursor, objects, parameters = [0], [], result_parameters(mode)
            for index, kind in enumerate(parameters):
                if kind == BOX:
                    at = slot(g, cursor, BOX)
                    g.add(f"BeginObject {at}", f"Constant {7 if index == 0 else 19} i64", f"Store {at} i64")
                    objects.append(at)
                else:
                    objects.append(0)
            result = slot(g, cursor, SPAN)
            save(g, depth)
            for index, kind in enumerate(parameters):
                if kind != BOX:
                    three = mode == 1 or (mode == 2 and index == 5) or (mode == 3 and index == 4)
                    value = 3 if three else 1 if kind == BOOL else 71 + index
                    g.add(f"Constant {value} {kind}", "Push")
            g.add(f"MethodCall abi_result_{mode} 0 {items(objects if mode == 3 else [])} {result}")
            g.add(f"AggregateCall abi_probe_one [0] 0 [{result}]")
            combine(g, depth)
            g.add(f"EndSpan {result}")
            g.code += [f"EndObject {at}" for at in objects if at]
            g.add("Return")
            functions.append(g)
    for depth in range(4):
        f = Fn(f"abi_borrow_{depth}")
        f.receiver, f.frame, f.spans, f.slots = "Receiver false false", 192, {56, 112, 168}, {176: I64}
        save(f, depth)
        f.add("Constant 123456789 i64; BorrowOwnedSpan 0 1 56; Store 176 i64; ReborrowSpan 56 112")
        f.add("Constant 3 i64; Push; Constant 7 i64; Subspan 112 168; AggregateCall abi_probe_one [0] 0 [168]")
        f.add("Load 176 i64")
        combine(f, depth)
        f.add("EndSpan 168", "EndSpan 112", "EndSpan 56", "Return")
        functions.append(f)
    return functions


def logical_spans():
    forwarding = logical_forwarding()
    owner = program("logical-spans-owner", RECEIVER_HEADER, forwarding + logical_owned())
    return program("logical-spans-array", "", forwarding) + owner


# Owned sectors: literal 512-byte Block and 520-byte Report records (status
# word then payload) through six-argument function, constructor and method ABIs.
def sector_status(record):
    return 0x1100000000000000 + record


def sector_payload(record, byte):
    return (byte * 37 + record * 53 + (byte // 256) * 17) % 256


def compare_current(f, value, kind):
    f.add("Push", f"Constant {value} {kind}", f"Compare Equal {kind}", "BranchFalse 1")


def check_report(f, base, record):
    f.add(f"Load {base} u64")
    compare_current(f, sector_status(record), U64)
    for byte in range(512):
        f.add(f"Load {base - 8 - byte} u8")
        compare_current(f, sector_payload(record, byte), U8)


def block_slot(f, base, name="Block"):
    f.objects[base] = (name, "false")
    for byte in range(512):
        f.slots[base - byte] = U8


def report_slot(f, base, name="Report"):
    f.objects[base] = (name, "false")
    f.slots[base] = U64
    for byte in range(512):
        f.slots[base - 8 - byte] = U8


def six_reports(f):
    for record in range(6):
        base = (record + 1) * 520
        f.params.append(cls("Report"))
        report_slot(f, base)
        f.add(f"BindObjectParameter {record} {base} Report")


def sector_tail(f):
    f.add("Constant 42 i64; Jump 2; Label 1; Constant -2 i64; Label 2; BinaryValue CheckedAdd; Return")


SECTOR_HEADER = """layout Block [u8*512]
layout CopyBytes9 [u8*9]
layout CopyMixed [u8*11 bool (enum CopyState) u64 u8*7]
layout GapChild [u64 u8*7]
layout GapOuter [u64 u8*8]
layout Receiver [u64]
layout Report [u64 u8*512]
layout WrappedReport [u64 u8*512]
fields Block [(u8 0 512 true)]
fields CopyBytes9 [(u8 0 9 true)]
fields CopyMixed [(u8 0 1 false) ((class CopyBytes9) 1 9 false) (u8 10 1 false) (bool 11 1 false) \
((enum CopyState) 12 1 false) (u64 13 1 false) (u8 14 7 true)]
fields GapChild [(u64 0 1 false) (u8 1 7 true)]
fields GapOuter [((class GapChild) 0 8 false) (u8 8 1 false)]
fields Report [(u64 0 1 false) ((class Block) 1 512 false)]
fields WrappedReport [((class Report) 0 513 false)]
enum CopyState 2
"""


def sector_values():
    clobber = Fn("sector_clobber")
    clobber.add("Constant 0 i64", "Return")
    functions = [clobber]
    for kind in ("function", "constructor", "method"):
        incoming = Fn("sector_in_" + kind, I64 if kind == "constructor" else cls("Report"))
        incoming.frame = 3120
        six_reports(incoming)
        incoming.receiver = {"constructor": "WrappedReport true true", "method": "Receiver false false"}.get(kind)
        incoming.add("Call sector_clobber")
        for record in range(6):
            check_report(incoming, (record + 1) * 520, record)
        if kind == "method":
            incoming.add("ReceiverLoad 0 u64")
            compare_current(incoming, 1000, U64)
        if kind == "constructor":
            incoming.add("InitializeObjectField 0 0 3120; Constant 0 i64; Return")
            incoming.add("Label 1; InitializeObjectField 0 0 520; Constant 0 i64; Return")
        else:
            incoming.add("ReturnObject 3120", "Label 1", "ReturnObject 520")
        functions.append(incoming)
        # The matching outgoing case replaces this target with handwritten assembly.
        target = incoming.copy("sector_target_" + kind)
        target.code = target.code[:6]
        if kind == "constructor":
            target.add("InitializeObjectField 0 0 3120; Constant 0 i64; Return")
        else:
            target.add("ReturnObject 3120")
        functions.append(target)
        outgoing = Fn("sector_out_" + kind)
        outgoing.frame = 3648
        six_reports(outgoing)
        report_slot(outgoing, 3640, "WrappedReport" if kind == "constructor" else "Report")
        outgoing.objects[3648] = ("Receiver", "false")
        outgoing.slots[3648] = U64
        outgoing.add("BeginObject 3640; BeginObject 3648; Constant 1000 u64; Store 3648 u64; Constant 1 i64; Push")
        arguments = items(range(520, 3121, 520))
        if kind == "function":
            outgoing.add(f"AggregateCall {target.name} {arguments} 3640")
        else:
            receiver, result = (3640, 0) if kind == "constructor" else (3648, 3640)
            outgoing.add(f"MethodCall {target.name} {receiver} {arguments} {result}")
        check_report(outgoing, 3640, 5)
        sector_tail(outgoing)
        functions.append(outgoing)
    block = Fn("sector_in_block", cls("Block"), [cls("Block")])
    block.frame = 512
    block_slot(block, 512)
    block.add("BindObjectParameter 0 512 Block", "ReturnObject 512")
    functions += [block, block.copy("sector_target_block")]
    block_out = Fn("sector_out_block", I64, [cls("Block")])
    block_out.frame = 1024
    block_slot(block_out, 512)
    block_slot(block_out, 1024)
    block_out.add("BindObjectParameter 0 512 Block; BeginObject 1024; Constant 1 i64; Push")
    block_out.add("AggregateCall sector_target_block [512] 1024")
    for byte in range(512):
        block_out.add(f"Load {1024 - byte} u8")
        compare_current(block_out, sector_payload(5, byte), U8)
    sector_tail(block_out)
    functions.append(block_out)
    # Literal canonical offsets: the final seven bytes may not widen into padding.
    mixed_copy = Fn("sector_in_mixed", cls("CopyMixed"), [cls("CopyMixed")])
    mixed_copy.frame, mixed_copy.objects = 48, {48: ("CopyMixed", "false")}
    leaves = [U8] * 11 + [BOOL, "(enum CopyState)", U64] + [U8] * 7
    offsets = list(range(11)) + [16, 24, 32] + list(range(40, 47))
    for offset, leaf in zip(offsets, leaves):
        mixed_copy.slots[48 - offset] = leaf
    mixed_copy.add("BindObjectParameter 0 48 CopyMixed", "Label 70", "ReturnObject 48")
    gap = Fn("sector_in_gap", cls("GapOuter"), [cls("GapOuter")])
    gap.frame, gap.objects, gap.slots = 32, {24: ("GapOuter", "false")}, {24: U64}
    for byte in (8, 9, 10, 11, 12, 13, 14, 16):
        gap.slots[24 - byte] = U8
    gap.add("BindObjectParameter 0 24 GapOuter", "Label 70", "ReturnObject 24")
    functions += [mixed_copy, gap]
    return program("abi", SECTOR_HEADER, functions)


# Short-circuit bool operators around every call shape, with saved prefix
# values above both 32-bit ranges (Python checks the expected arithmetic).
PREFIX = 1099511627793
CALL_KINDS = "scalar aggregate aggregate_result method method_value method_result metadata span subspan".split()


def probe_signatures():
    scalar = Fn("sc_probe_scalar", BOOL, [BOOL])
    scalar.frame, scalar.slots = 16, {8: BOOL}
    scalar.add("BindParameter 0 8 bool", "Load 8 bool", "Return")
    method = scalar.copy("sc_probe_method")
    method.receiver = "ProbeBox true false"
    aggregate = Fn("sc_probe_aggregate", BOOL, [cls("ProbeBox"), BOOL])
    aggregate.frame, aggregate.slots, aggregate.objects = 32, {16: I64, 8: I64, 24: BOOL}, {16: ("ProbeBox", "false")}
    aggregate.add("BindObjectParameter 0 16 ProbeBox", "BindParameter 1 24 bool", "Load 24 bool", "Return")
    value = aggregate.copy("sc_probe_method_value")
    value.receiver = "ProbeBox true false"
    result = aggregate.copy("sc_probe_aggregate_result")
    result.result = cls("ProbeBox")
    result.code = ["BindObjectParameter 0 16 ProbeBox", "BindParameter 1 24 bool", "ReturnObject 16"]
    method_result = result.copy("sc_probe_method_result")
    method_result.receiver = "ProbeBox true false"
    span = Fn("sc_probe_span", BOOL, [SPAN, BOOL])
    span.frame, span.spans, span.slots = 128, {120}, {24: BOOL}
    span.add("BindSpanParameter 0 120", "BindParameter 1 24 bool", "Load 24 bool", "EndSpan 120", "Return")
    return [scalar, method, aggregate, value, result, method_result, span]


class Labels:
    def __init__(self, first=1):
        self.next = first

    def __call__(self):
        self.next += 1
        return self.next - 1


def probe(f, kind, boolean, label):
    if kind == "metadata":
        no, done = label(), label()
        f.add(f"Load {boolean} bool; BranchFalse {no}; Constant 17 i64; Jump {done}; Label {no}; Constant 18 i64")
        f.add(f"Label {done}; MetadataQuery Size; Push; Constant 0 i64; Compare NotEqual i64")
        return
    if kind == "subspan":
        f.add("Constant 1 i64", "Push", "Constant 1 i64", "Subspan 176 232")
    f.add(f"Load {boolean} bool", "Push")
    if kind == "scalar":
        f.add("Call sc_probe_scalar")
    elif kind == "aggregate":
        f.add("AggregateCall sc_probe_aggregate [40 0] 0")
    elif kind == "method":
        f.add("MethodCall sc_probe_method 56")
    elif kind == "method_value":
        f.add("MethodCall sc_probe_method_value 56 [40 0]")
    elif kind in ("aggregate_result", "method_result"):
        f.add("BeginObject 112")
        if kind == "aggregate_result":
            f.add("AggregateCall sc_probe_aggregate_result [40 0] 112")
        else:
            f.add("MethodCall sc_probe_method_result 56 [40 0] 112")
        f.add("Load 112 i64; Push; Constant 0 i64; Compare NotEqual i64; EndObject 112")
    else:
        f.add(f"AggregateCall sc_probe_span [0 0] 0 [{176 if kind == 'span' else 232} 0]")
        if kind == "subspan":
            f.add("EndSpan 232")


def logical(f, kind, shape, label):
    no, done = label(), label()
    f.add("Load 8 bool", f"BranchFalse {no}")
    if shape == "or":
        f.add("Constant 1 bool", f"Jump {done}", f"Label {no}")
        probe(f, kind, 16, label)
        f.add(f"Label {done}")
        return
    probe(f, kind, 16, label)
    f.add(f"Jump {done}", f"Label {no}", "Constant 0 bool", f"Label {done}")
    if shape == "nested":
        rhs, joined = label(), label()
        f.add(f"BranchFalse {rhs}", "Constant 1 bool", f"Jump {joined}", f"Label {rhs}")
        probe(f, kind, 24, label)
        f.add(f"Label {joined}")


def bool_to_integer(f, label):
    no, done = label(), label()
    f.add(f"BranchFalse {no}; Constant 1 i64; Jump {done}; Label {no}; Constant 0 i64; Label {done}")


BIND_THREE = "BindParameter 0 8 bool; BindParameter 1 16 bool; BindParameter 2 24 bool"
MINT_ARRAY = "BeginArray 64; Constant 11 u8; Store 64 u8; Constant 22 u8; Store 63 u8; Constant 33 u8; Store 62 u8"


def native_function(kind, shape, depth):
    f = Fn(f"sc_{kind}_{shape}_{depth}", I64, [BOOL] * 3)
    f.frame = 240
    f.slots = {8: BOOL, 16: BOOL, 24: BOOL, 40: I64, 32: I64, 56: I64, 48: I64, 112: I64, 104: I64}
    f.objects = {40: ("ProbeBox", "false"), 56: ("ProbeBox", "true"), 112: ("ProbeBox", "false")}
    f.add(BIND_THREE, "BeginObject 40; Constant 17 i64; Store 40 i64; Constant 19 i64; Store 32 i64")
    f.add("BeginObject 56; Constant 23 i64; Store 56 i64; Constant 29 i64; Store 48 i64")
    spans = kind in ("span", "subspan")
    if spans:
        f.arrays, f.spans = {64: 3}, {176, 232}
        f.slots.update({64: U8, 63: U8, 62: U8})
        f.add(MINT_ARRAY, "BorrowSpan 64 176")
    save(f, depth, PREFIX)
    label = Labels()
    logical(f, kind, shape, label)
    if spans:
        f.add("EndSpan 176", "EndArray 64")
    bool_to_integer(f, label)
    if kind.startswith("method"):
        # Native probes mutate a real receiver field; its value shows committed RHS effects.
        f.add("Push; Load 48 i64; Push; Constant 100 i64; BinaryValue CheckedMultiply; BinaryValue CheckedAdd")
    combine(f, depth)
    f.add("EndObject 56", "EndObject 40", "Return")
    return f


TRAPS = {
    "bounds": "Constant 1 i64; BoundsGuard 40 1 i64; IndexLoad 40 1 i64",
    "overflow": "Constant 9223372036854775807 i64; Push; Constant 1 i64; BinaryValue CheckedAdd",
    "zero": "Constant 42 i64; Push; Constant 0 i64; BinaryValue CheckedDivide",
    "shift": "Constant 1 u64; Push; Constant 64 i64; BinaryValue ShiftLeft u64; Convert u64 i64",
}


def trap_function(trap, shape, depth):
    f = Fn(f"sc_trap_{trap}_{shape}_{depth}", I64, [BOOL] * 3)
    f.frame, f.slots = 48, {8: BOOL, 16: BOOL, 24: BOOL, 40: I64}
    f.add(BIND_THREE, "Constant 7 i64; Store 40 i64")
    save(f, depth, PREFIX)
    f.add("Load 8 bool", "BranchFalse 1")
    if shape == "or":
        f.add("Constant 1 bool", "Jump 2", "Label 1")
    f.add(TRAPS[trap], "Push; Constant 0 i64; Compare NotEqual i64")
    if shape == "and":
        f.add("Jump 2", "Label 1", "Constant 0 bool")
    f.add("Label 2")
    bool_to_integer(f, Labels(3))
    combine(f, depth)
    f.add("Return")
    return f


def short_circuit():
    functions = probe_signatures()
    shapes = [(kind, shape, depth) for kind in CALL_KINDS for shape in ("and", "or", "nested") for depth in range(4)]
    functions += [native_function(*shape) for shape in shapes]
    # A checked local-index token remains below a complete nested bool result.
    guard = Fn("sc_guarded_store", I64, [BOOL] * 3)
    guard.frame, guard.slots = 48, {8: BOOL, 16: BOOL, 24: BOOL, 40: BOOL, 32: BOOL}
    guard.add(BIND_THREE, "Constant 0 bool; Store 40 bool; Store 32 bool; Constant 1 i64; BoundsGuard 40 2 bool; Push")
    label = Labels()
    logical(guard, "scalar", "nested", label)
    guard.add("IndexStore 40 2 bool", "Load 32 bool")
    bool_to_integer(guard, label)
    guard.add("Return")
    # The subspan offset is stacked while its count's bool expression branches and calls.
    window = native_function("subspan", "nested", 0)
    window.name = "sc_window_count"
    window.code = []
    window.add(BIND_THREE, MINT_ARRAY, "BorrowSpan 64 176; Constant 1 i64; Push")
    label = Labels()
    logical(window, "scalar", "nested", label)
    bool_to_integer(window, label)
    window.add("Subspan 176 232", "SpanLength 232", "EndSpan 232", "EndSpan 176", "EndArray 64", "Return")
    receiver_guard = guard.copy("sc_receiver_guard_method")
    receiver_guard.receiver = "ProbeBits true false"
    receiver_guard.code = []
    receiver_guard.add(BIND_THREE, "Constant 1 i64; ReceiverBoundsGuard 0; Push")
    label = Labels()
    logical(receiver_guard, "scalar", "nested", label)
    receiver_guard.add("ReceiverIndexStore 0")
    bool_to_integer(receiver_guard, label)
    receiver_guard.add("Return")
    receiver_caller = guard.copy("sc_receiver_guarded_store")
    receiver_caller.objects = {40: ("ProbeBits", "true")}
    receiver_caller.code = []
    receiver_caller.add(BIND_THREE, "BeginObject 40; Constant 0 bool; Store 40 bool; Store 32 bool")
    receiver_caller.add("Load 8 bool; Push; Load 16 bool; Push; Load 24 bool; Push")
    receiver_caller.add("MethodCall sc_receiver_guard_method 40; Load 32 bool")
    bool_to_integer(receiver_caller, Labels())
    receiver_caller.add("EndObject 40", "Return")
    functions += [guard, window, receiver_guard, receiver_caller]
    traps = [(trap, shape, depth) for trap in TRAPS for shape in ("and", "or") for depth in (1, 2)]
    functions += [trap_function(*trap) for trap in traps]
    header = (
        "layout ProbeBits [bool bool]\nlayout ProbeBox [i64 i64]\nfields ProbeBits [(bool 0 2 true)]\n"
        "descriptor 17 1 0\ndescriptor 18 0 0\nviews [(0 [17 18])]\n"
    )
    return program("native", header, functions)


PROGRAMS = {"method-spans": method_spans, "borrowed-objects": borrowed_objects, "logical-spans": logical_spans}
PROGRAMS |= {"sector-values": sector_values, "short-circuit": short_circuit}


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in PROGRAMS:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    with open(sys.argv[2], "w", encoding="utf-8") as output:
        output.write(PROGRAMS[sys.argv[1]]())
    return 0


if __name__ == "__main__":
    sys.exit(main())
