#!/usr/bin/env python3
"""Focused source admission and lifetime rejections for owned readonly spans.

This gate compiles real source to validated native assembly, without executing it.
It does not establish the owned-span runtime or whole-project acceptance gates.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import tempfile

SPAN = "builtin::span<const u8>"
REGION = "builtin::ByteRegion"
OWNER = "builtin::OwnedBytes"


def program(body, helpers=""):
    return f"module owned_spans_source; {helpers} auto entry({REGION} region) -> i64 {{ {body} }}"


def box(methods="", view="return borrow_bytes(payload);", signature="const", params=""):
    return f"""
    class Box {{
        {OWNER} payload;
        {OWNER} sibling;
    public:
        Box({REGION} region, {OWNER} first, {OWNER} second) : payload(move(first)), sibling(move(second)) {{}}
        auto bytes({params}) {signature} -> {SPAN} {{ {view} }}
        auto touch() -> i64 {{ payload.set(0, 8u8); return 0; }}
        auto resize() -> bool {{ return payload.try_resize(2); }}
        {methods}
    }};
    """


CREATE = f"{OWNER} first = region.try_allocate(4); {OWNER} second = region.try_allocate(4); "
CREATE += "Box item = Box(region, move(first), move(second)); "
ALLOCATE = f"{OWNER} owner = region.try_allocate(4); "
OBSERVE = f"auto observe({SPAN} bytes, bool value) -> i64 {{ return bytes.size(); }}"
REVERSE = f"auto reverse(bool value, {SPAN} bytes) -> i64 {{ return bytes.size(); }}"
LENGTH = f"auto length({SPAN} bytes) -> i64 {{ return bytes.size(); }}"
CONSUME = f"auto consume({REGION} region, {OWNER} bytes) -> i64 {{ return bytes.size(); }}"


def cases():
    accepted = {
        "array-still-supported": program(
            f"builtin::array<u8, 2> a = {{1u8, 2u8}}; const {SPAN} bytes = borrow_bytes(a); return bytes.size();"
        ),
        "named-owner": program(ALLOCATE + f"const {SPAN} bytes = borrow_bytes(owner); return bytes.size();"),
        "const-owner": program(
            f"const {OWNER} owner = region.try_allocate(4); "
            f"const {SPAN} bytes = borrow_bytes(owner); return bytes.size();"
        ),
        "copy-and-subspan": program(
            ALLOCATE + f"const {SPAN} bytes = borrow_bytes(owner); const {SPAN} copy = bytes; "
            f"const {SPAN} tail = copy.subspan(1, 2); return i64(tail.at(0));"
        ),
        "direct-temporary-subspan": program(
            ALLOCATE + f"const {SPAN} bytes = borrow_bytes(owner).subspan(1, 2); return bytes.size();"
        ),
        "nested-temporary-subspans": program(
            ALLOCATE + f"const {SPAN} bytes = borrow_bytes(owner).subspan(1, 2).subspan(0, 1); return bytes.size();"
        ),
        "post-scope-mutation": program(
            ALLOCATE + f"{{ const {SPAN} bytes = borrow_bytes(owner); bytes.size(); }} "
            "owner.try_resize(2); owner.set(0, 9u8); return owner.size();"
        ),
        "temporary-argument": program(ALLOCATE + "length(borrow_bytes(owner)); owner.try_resize(2); return 1;", LENGTH),
        "mutation-before-borrow": program(
            ALLOCATE + "return reverse(owner.try_resize(2), borrow_bytes(owner));", REVERSE
        ),
        "returned-view": program(CREATE + f"const {SPAN} bytes = item.bytes(); return bytes.size();", box()),
        "returned-temporary-argument": program(CREATE + "return length(item.bytes());", box() + LENGTH),
        "returned-subspan": program(
            CREATE + f"const {SPAN} bytes = item.bytes().subspan(0, 2); return bytes.size();", box()
        ),
        "returned-named-prefix": program(
            CREATE + f"const {SPAN} bytes = item.bytes(); return bytes.size();",
            box(view=f"const {SPAN} raw = borrow_bytes(payload); return raw.subspan(0, 2);"),
        ),
        "returned-direct-prefix": program(
            CREATE + f"const {SPAN} bytes = item.bytes(); return bytes.size();",
            box(view="return borrow_bytes(payload).subspan(0, 2);"),
        ),
        "same-field-branches": program(
            CREATE + f"const {SPAN} bytes = item.bytes(); return bytes.size();",
            box(
                view="if (payload.size() > 2) { return borrow_bytes(payload).subspan(0, 2); } "
                "return borrow_bytes(payload);"
            ),
        ),
        "sibling-field-independent": program(
            CREATE + "return item.inspect();",
            box(
                methods=f"auto inspect() -> i64 {{ const {SPAN} bytes = borrow_bytes(payload); "
                "sibling.set(0, 8u8); sibling.try_resize(2); return bytes.size(); }"
            ),
        ),
        "receiver-scalar-helper": program(
            CREATE + f"const {SPAN} bytes = item.bytes(); return bytes.size();",
            box(
                methods="auto count() const -> i64 { return 2; }",
                view="return borrow_bytes(payload).subspan(0, count());",
            ),
        ),
        "unrelated-local-return-cleanup": program(
            CREATE + f"const {SPAN} bytes = item.bytes(); return bytes.size();",
            box(
                view=f"builtin::array<u8, 1> data = {{1u8}}; const {SPAN} scratch = borrow_bytes(data); "
                "scratch.size(); return borrow_bytes(payload);"
            ),
        ),
        "overloaded-returned-argument": program(
            CREATE + "return length(item.bytes());", box() + LENGTH + "auto length(i64 value) -> i64 { return value; }"
        ),
        "returned-view-copied-parameter": program(
            CREATE + f"const Flag index = Flag(1); const {SPAN} bytes = item.bytes(index); return bytes.size();",
            "class Flag { i64 value; public: Flag(i64 input) : value(input) {} "
            "auto get() const -> i64 { return value; } };"
            + box(params="Flag index", view="return borrow_bytes(payload).subspan(index.get(), 1);"),
        ),
        "returned-view-copied-local": program(
            CREATE + f"const {SPAN} bytes = item.bytes(); return bytes.size();",
            "class Flag { i64 value; public: Flag(i64 input) : value(input) {} "
            "auto get() const -> i64 { return value; } };"
            + box(view="const Flag index = Flag(1); return borrow_bytes(payload).subspan(index.get(), 1);"),
        ),
        "returned-view-post-scope": program(
            CREATE + f"{{ const {SPAN} bytes = item.bytes(); bytes.size(); }} item.resize(); return item.touch();",
            box(),
        ),
    }
    rejected = {
        "write-owner": program(ALLOCATE + f"const {SPAN} bytes = borrow_bytes(owner); owner.set(0, 2u8); return 0;"),
        "resize-owner": program(ALLOCATE + f"const {SPAN} bytes = borrow_bytes(owner); owner.try_resize(0); return 0;"),
        "move-owner": program(
            ALLOCATE + f"const {SPAN} bytes = borrow_bytes(owner); {OWNER} moved = move(owner); return 0;"
        ),
        "consume-owner": program(
            ALLOCATE + f"const {SPAN} bytes = borrow_bytes(owner); return consume(region, move(owner));", CONSUME
        ),
        "temporary-argument-mutation": program(
            ALLOCATE + "return observe(borrow_bytes(owner), owner.try_resize(2));", OBSERVE
        ),
        "temporary-subspan-argument-mutation": program(
            ALLOCATE + "return observe(borrow_bytes(owner).subspan(0, 1), owner.set(0, 1u8));", OBSERVE
        ),
        "subspan-offset-consumption": program(
            ALLOCATE + f"const {SPAN} bytes = borrow_bytes(owner).subspan(consume(region, move(owner)), 0); return 0;",
            CONSUME,
        ),
        "return-owner-while-borrowed": program(
            "return 0;",
            f"auto bounce({REGION} region, {OWNER} owner) -> {OWNER} {{ "
            f"const {SPAN} bytes = borrow_bytes(owner); return move(owner); }}",
        ),
        "mutable-span": program(ALLOCATE + f"{SPAN} bytes = borrow_bytes(owner); return 0;"),
        "span-rebind": program(
            ALLOCATE + f"const {SPAN} bytes = borrow_bytes(owner); bytes = borrow_bytes(owner); return 0;"
        ),
        "use-moved-owner": program(
            ALLOCATE + f"{OWNER} moved = move(owner); const {SPAN} bytes = borrow_bytes(owner); return 0;"
        ),
        "ordinary-span-result": program("return 0;", f"auto escape({SPAN} bytes) -> {SPAN} {{ return bytes; }}"),
        "mutable-method-result": program("return 0;", box(signature="")),
        "different-return-fields": program(
            "return 0;", box(view="if (payload.ok()) { return borrow_bytes(payload); } return borrow_bytes(sibling);")
        ),
        "local-array-return": program(
            "return 0;", box(view="builtin::array<u8, 1> data = {1u8}; return borrow_bytes(data);")
        ),
        "method-forwarding": program(
            "return 0;",
            box(view="return other();", methods=f"auto other() const -> {SPAN} {{ return borrow_bytes(payload); }}"),
        ),
        "method-indirect-forwarding": program(
            "return 0;",
            box(
                view=f"const {SPAN} bytes = other(); return bytes;",
                methods=f"auto other() const -> {SPAN} {{ return borrow_bytes(payload); }}",
            ),
        ),
        "root-mutable-method": program(CREATE + f"const {SPAN} bytes = item.bytes(); return item.touch();", box()),
        "returned-copy-blocks-root": program(
            CREATE
            + f"const {SPAN} bytes = item.bytes(); const {SPAN} copy = bytes; item.resize(); return copy.size();",
            box(),
        ),
        "returned-root-move": program(
            CREATE + f"const {SPAN} bytes = item.bytes(); Box moved = move(item); return bytes.size();", box()
        ),
        "returned-argument-root-mutation": program(
            CREATE + "return observe(item.bytes(), item.resize());", box() + OBSERVE
        ),
        "returned-subspan-root-mutation": program(
            CREATE + f"const {SPAN} bytes = item.bytes().subspan(item.touch(), 0); return bytes.size();", box()
        ),
        "private-field-access": program(CREATE + f"const {SPAN} bytes = borrow_bytes(item.payload); return 0;", box()),
        "same-receiver-field-write": program(
            "return 0;",
            box(
                methods=f"auto inspect() -> i64 {{ const {SPAN} bytes = borrow_bytes(payload); "
                "payload.set(0, 2u8); return 0; }"
            ),
        ),
        "same-receiver-field-resize": program(
            "return 0;",
            box(
                methods=f"auto inspect() -> i64 {{ const {SPAN} bytes = borrow_bytes(payload); "
                "payload.try_resize(2); return 0; }"
            ),
        ),
        "implicit-root-mutation": program(
            "return 0;",
            box(methods=f"auto inspect() -> i64 {{ const {SPAN} bytes = borrow_bytes(payload); return touch(); }}"),
        ),
        "temporary-receiver": program(
            CREATE + f"const {SPAN} bytes = Box(region, move(first), move(second)).bytes(); return 0;", box()
        ),
        "receiver-consumed-in-argument": program(
            CREATE + f"const {SPAN} bytes = item.bytes(consume_box(region, move(item))); return 0;",
            box(params="i64 count", view="return borrow_bytes(payload).subspan(0, count);")
            + f"auto consume_box({REGION} region, Box value) -> i64 {{ return 0; }}",
        ),
        "array-temporary-borrow": program(
            f"builtin::array<u8, 1> data = {{1u8}}; const {SPAN} bytes = borrow_bytes(data).subspan(0, 1); return 0;"
        ),
        "array-temporary-chain": program(
            f"builtin::array<u8, 1> data = {{1u8}}; const {SPAN} bytes = borrow_bytes(data); "
            f"const {SPAN} child = bytes.subspan(0, 1).subspan(0, 1); return 0;"
        ),
        "parameter-temporary-chain": program(
            "return 0;",
            f"auto window({SPAN} bytes) -> i64 {{ const {SPAN} child = bytes.subspan(0, 1).subspan(0, 1); return 0; }}",
        ),
        "array-field-origin": program(
            "return 0;",
            "class Value { builtin::array<u8, 1> data; public: Value() : data{} {} "
            + f"auto count() const -> i64 {{ const {SPAN} bytes = borrow_bytes(data); return bytes.size(); }} }};",
        ),
    }
    accepted["array-field-origin"] = rejected.pop("array-field-origin")
    return accepted, rejected


REJECTION_DIAGNOSTICS = {
    "ordinary-span-result": "only scalar function results",
    "mutable-method-result": "span results require a const",
    "different-return-fields": "same receiver byte-storage field",
    "local-array-return": "returned span must derive directly",
    "method-forwarding": "cannot forward another method's returned view",
    "method-indirect-forwarding": "cannot forward another method's returned view",
    "mutable-span": "span bindings must be const",
    "span-rebind": "assignment requires a mutable scalar local",
    "use-moved-owner": "use after move",
    "private-field-access": "private class field is inaccessible",
    "temporary-receiver": "method receiver requires a class local",
    "receiver-consumed-in-argument": "method arguments consumed the receiver",
    "array-temporary-borrow": "temporary subspan chains require an owned-byte origin",
    "array-temporary-chain": "temporary subspan chains require an owned-byte origin",
    "parameter-temporary-chain": "temporary subspan chains require an owned-byte origin",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("compiler", type=Path)
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    with tempfile.TemporaryDirectory(prefix="aurora-owned-span-source-") as scratch:
        directory = Path(scratch)
        accepted, rejected = cases()
        for expected, fixtures in ((True, accepted), (False, rejected)):
            for name, source in fixtures.items():
                path = directory / f"{name}.au"
                path.write_text(source)
                run = subprocess.run(
                    [str(compiler), str(path), "-o", str(path.with_suffix(".s"))],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                path.with_suffix(".stderr").write_text(run.stderr)
                path.with_suffix(".stdout").write_text(run.stdout)
                if (run.returncode == 0) != expected:
                    raise RuntimeError(f"{name}: expected {'acceptance' if expected else 'rejection'}: {run.stderr}")
                if path.read_text() != source:
                    raise RuntimeError(f"{name}: compiler changed the source")
                assembly = path.with_suffix(".s")
                if expected:
                    if not assembly.is_file() or not assembly.stat().st_size:
                        raise RuntimeError(f"{name}: accepted source produced no assembly")
                else:
                    if run.returncode != 1 or assembly.exists():
                        raise RuntimeError(f"{name}: rejection did not fail closed with exit 1")
                    diagnostic = REJECTION_DIAGNOSTICS.get(
                        name, "cannot mutate or move an owner while a readonly span is live"
                    )
                    if diagnostic not in run.stderr:
                        raise RuntimeError(f"{name}: wrong rejection diagnostic, wanted {diagnostic!r}: {run.stderr}")
        print(f"PASS owned readonly span source: {len(accepted)} accepted, {len(rejected)} rejected; {directory}")


if __name__ == "__main__":
    main()
