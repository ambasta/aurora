#!/usr/bin/env python3
"""Generated owner/receiver views with the real hosted allocation observer."""

from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
import signal
from pathlib import Path
import tempfile

from byte_buffer import BufferSuite
from owned_bytes import command
from unsigned_oracle import require

SPAN = "builtin::span<const u8>"
OWNER = "builtin::OwnedBytes"


def program(body, helpers="", imports=""):
    return (
        "module owned_spans;\n"
        + imports
        + helpers
        + "auto entry(builtin::ByteRegion region, i64 n, i64 flag) -> i64 {\n"
        + body
        + "\n}\n"
    )


class Suite(BufferSuite):
    runtime_traps = 0

    def failed_borrow(self, executable):
        if self.compile_only:
            self.skipped_native += 1
            return
        result = command([executable, 0, 0, 0])
        require(
            result.returncode == -signal.SIGABRT
            and result.stdout == b""
            and result.stderr == b"aurora owned bytes: bounds\n",
            f"failed borrow: wrong adapter trap {result.returncode}: {result.stderr!r}",
        )
        self.runtime_traps += 1

    def trap(self, *args, **kwargs):
        if self.compile_only:
            self.skipped_native += 1
        else:
            super().trap(*args, **kwargs)


def native_cases(s):
    helpers = f"""
    auto sum({SPAN} v) -> i64 {{
        i64 total = 0; i64 i = 0;
        while (i < v.size()) {{ total = total + i64(v.at(i)); i = i + 1; }}
        return total;
    }}
    auto count(i64 prefix, {SPAN} v, i64 suffix) -> i64 {{ return prefix + sum(v) + suffix; }}
    """
    p = s.compile(
        "owner-window",
        program(
            f"""
        {OWNER} a = region.try_allocate(n);
        i64 i=0; while(i<n) {{ a.set(i,u8(i%251)); i=i+1; }}
        const {SPAN} v = borrow_bytes(a);
        const {SPAN} copy = v;
        const {SPAN} window = copy.subspan(0,n);
        return count(100,window,200);
    """,
            helpers,
        ),
    )
    for n in (0, 1, 2, 17, 4097, 8193):
        s.run(p, n, n, 0, 300 + sum(i % 251 for i in range(n)), 1, 1)
    p = s.compile(
        "const-owner",
        program(
            f"""
        const {OWNER} a=region.try_allocate(3);
        const {SPAN} v=borrow_bytes(a); return v.size()+sum(v);
    """,
            helpers,
        ),
    )
    s.run(p, 3, 0, 0, 3, 1, 1)
    p = s.compile(
        "temporary-argument-lifetimes",
        program(
            f"""
        {OWNER} a=region.try_allocate(3); a.set(0,11u8); a.set(1,22u8); a.set(2,33u8);
        const i64 first = count(1,borrow_bytes(a),2);
        a.set(0,7u8);
        const i64 second = count(3,borrow_bytes(a).subspan(1,2),4);
        a.try_resize(4); return first+second+a.size();
    """,
            helpers,
        ),
    )
    s.run(p, 4, 0, 0, 135, 2, 1, release_order=[1, 2])
    p = s.compile(
        "scope-resize-move",
        program(f"""
        {OWNER} a=region.try_allocate(2); a.set(1,42u8);
        {{ const {SPAN} v=borrow_bytes(a); const {SPAN} w=v.subspan(1,1); if(w.at(0)!=42u8){{return -1;}} }}
        a.try_resize(3); {OWNER} moved=move(a);
        const {SPAN} v=borrow_bytes(moved); return i64(v.at(1))+v.size();
    """),
    )
    s.run(p, 3, 0, 0, 45, 2, 1, release_order=[1, 2])
    p = s.compile(
        "runtime-bounds",
        program(f"""
        {OWNER} a=region.try_allocate(n); const {SPAN} v=borrow_bytes(a); return i64(v.at(flag));
    """),
    )
    for n, index in ((0, 0), (1, -1), (1, 1), (4097, 4097)):
        s.trap(p, n, n, index)
    p = s.compile(
        "failed-borrow",
        program(f"""
        {OWNER} a=region.try_allocate(1); const {SPAN} v=borrow_bytes(a); return v.size();
    """),
    )
    s.failed_borrow(p)
    p = s.compile(
        "nested-owner-window",
        program(f"""
        {OWNER} a=region.try_allocate(5); a.set(3,42u8);
        const {SPAN} v=borrow_bytes(a); const {SPAN} w=v.subspan(2,3);
        const {SPAN} x=w.subspan(1,1); return i64(x.at(0));
    """),
    )
    s.run(p, 5, 0, 0, 42, 1, 1)


def receiver_cases(s):
    helpers = f"""
    class Slice {{
        {OWNER} payload;
    public:
        Slice(builtin::ByteRegion region,{OWNER} initial):payload(move(initial)){{}}
        auto view(i64 start,i64 count) const -> {SPAN} {{
            const {SPAN} v=borrow_bytes(payload); const {SPAN} w=v.subspan(start,count); return w;
        }}
        auto first() const -> i64 {{ const {SPAN} v=view(0,1); return i64(v.at(0)); }}
        auto set_byte(i64 at,u8 value)->bool{{return payload.set(at,value);}}
    }};
    """
    p = s.compile(
        "receiver-subspan",
        program(
            f"""
        {OWNER} a=region.try_allocate(4); a.set(0,17u8); a.set(2,42u8);
        Slice box=Slice(region,move(a));
        const i64 first=box.first();
        {{ const {SPAN} v=box.view(1,3); const {SPAN} w=v.subspan(1,1); if(w.at(0)!=42u8){{return -1;}} }}
        box.set_byte(0,23u8); const Slice moved=move(box);
        const {SPAN} v=moved.view(0,4); return first+i64(v.at(0))+v.size();
    """,
            helpers,
        ),
    )
    s.run(p, 4, 0, 0, 44, 1, 1)
    helpers2 = f"""
    class Flag {{ i64 value; public: Flag(i64 x):value(x){{}} auto get() const->i64{{return value;}} }};
    class Slice {{ {OWNER} payload; public:
        Slice(builtin::ByteRegion region,{OWNER} input):payload(move(input)){{}}
        auto view(Flag f) const -> {SPAN} {{
            const {SPAN} all=borrow_bytes(payload); const {SPAN} part=all.subspan(f.get(),1); return part;
        }}
    }};
    """
    p = s.compile(
        "receiver-class-argument-hidden-result",
        program(
            f"""
        {OWNER} a=region.try_allocate(3); a.set(2,42u8); Slice box=Slice(region,move(a));
        const Flag f=Flag(2); const {SPAN} v=box.view(f); return i64(v.at(0));
    """,
            helpers2,
        ),
    )
    s.run(p, 3, 0, 0, 42, 1, 1)
    p = s.compile(
        "byte-buffer-logical-prefix",
        program(
            f"""
        {OWNER} a=region.try_allocate(8); a.set(7,255u8);
        std::ByteBuffer buffer=std::ByteBuffer(region,move(a));
        buffer.try_append(1u8); buffer.try_append(2u8); buffer.try_append(3u8); buffer.try_append(4u8);
        {{ const {SPAN} v=buffer.bytes(); if(v.size()!=4){{return -1;}}
           const std::ByteReadResult r=std::read_le32(v,0); if(r.value_or(0u64)!=67305985u64){{return -2;}} }}
        buffer.try_truncate(1); {{ const {SPAN} v=buffer.bytes(); if(v.size()!=1){{return -3;}} }}
        buffer.clear(); {{ const {SPAN} v=buffer.bytes(); if(v.size()!=0){{return -4;}} }}
        buffer.try_append(42u8); const {SPAN} v=buffer.bytes(); return i64(v.at(0));
    """,
            imports="import std.binary; import std.byte_buffer;\n",
        ),
    )
    s.run(p, 8, 0, 0, 42, 1, 1)
    p = s.compile(
        "utf8-binary-owner-crossing",
        program(
            f"""
        {OWNER} a=region.try_allocate(8193);
        a.set(4094,240u8);a.set(4095,159u8);a.set(4096,153u8);a.set(4097,130u8);
        const {SPAN} all=borrow_bytes(a);const {SPAN} v=all.subspan(4094,4);
        const std::Utf8DecodeResult text=std::decode_utf8(v,0,4,true);
        const std::ByteReadResult binary=std::read_be32(v,0);
        if(text.scalar_or(0u64)!=128578u64 || binary.value_or(0u64)!=4036991362u64){{return -1;}}
        return 42;
    """,
            imports="import std.array; import std.utf8; import std.binary;\n",
        ),
    )
    s.run(p, 8193, 0, 0, 42, 1, 1)


def rejection_cases(s):
    helper = f"auto consume(builtin::ByteRegion r,{OWNER} x)->i64{{return x.size();}}"
    start = f"{OWNER} a=region.try_allocate(1); const {SPAN} v=borrow_bytes(a);"
    for name, body in {
        "write": "a.set(0,1u8);",
        "resize": "a.try_resize(2);",
        "move": f"{OWNER} x=move(a);",
        "consume": "consume(region,move(a));",
        "rebind": "v=v;",
        "descendant-write": f"const {SPAN} child=v.subspan(0,0); a.set(0,1u8);",
    }.items():
        s.reject(name, program(start + body + "return 0;", helper))
    s.reject(
        "later-argument-consume",
        program(
            f"{OWNER} a=region.try_allocate(1);return use(borrow_bytes(a),consume(region,move(a)));",
            helper + f"auto use({SPAN} v,i64 x)->i64{{return v.size()+x;}}",
        ),
    )
    s.reject("ordinary-span-return", f"module bad;auto f({SPAN} v)->{SPAN}{{return v;}}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("compiler", type=Path)
    p.add_argument("--artifacts", type=Path)
    p.add_argument("--compile-only", action="store_true")
    a = p.parse_args()
    if a.artifacts:
        a.artifacts.mkdir(parents=True, exist_ok=False)
    with nullcontext(a.artifacts) if a.artifacts else tempfile.TemporaryDirectory(prefix="aurora-owned-spans-") as d:
        s = Suite(a.compiler.resolve(), Path(d), a.compile_only)
        native_cases(s)
        receiver_cases(s)
        rejection_cases(s)
        print(
            f"PASS owned spans: {s.programs} programs, {s.native} native cases, "
            f"{s.traps} exact bounds traps, {s.runtime_traps} exact adapter traps, "
            f"{s.rejections} rejections, {s.skipped_native} skipped"
        )
        print("compiler_sha256=" + hashlib.sha256(a.compiler.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
