#!/usr/bin/env python3
"""Direct owning-class source admission and real hosted allocation/cleanup tests.

--compile-only emits assembly and checks rejection/output preservation. It does
not link or execute a generated program and reports that boundary explicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from owned_bytes import OWNER, REGION, Suite, command, program
from unsigned_oracle import require

ENTRY = "__au_v_m1_11owned_bytes_n0__d5entry"
BOX = f"""
class Box {{
    u8 prefix;
    {OWNER} payload;
    u64 suffix;
    bool locked;
public:
    i64 marker;
    Box({REGION} region, {OWNER} initial, u8 tag)
        : prefix(tag), payload(move(initial)), suffix(101u64), locked(false), marker(7) {{}}
    auto ok() const -> bool {{ return payload.ok(); }}
    auto size() const -> i64 {{ return payload.size(); }}
    auto at(i64 index) const -> u8 {{ return payload.at(index); }}
    auto set(i64 index, u8 value) -> bool {{ return payload.set(index, value); }}
    auto check() const -> bool {{ return prefix == 23u8 && suffix == 101u64 && !locked && marker == 7; }}
    auto lock() -> bool {{ locked = true; return locked; }}
}};
"""
PAIR = f"""
class Pair {{
    {OWNER} first;
    u8 middle;
    {OWNER} second;
public:
    Pair({REGION} region, {OWNER} a, {OWNER} b)
        : first(move(a)), middle(19u8), second(move(b)) {{}}
    auto size() const -> i64 {{ return first.size() + second.size() + i64(middle); }}
}};
"""
CREATE = f"{OWNER} bytes = region.try_allocate(n); Box box = Box(region, move(bytes), 23u8);"
CONSUME = f"auto consume({REGION} region, Box box) -> i64 {{ return box.size(); }}"
BOUNCE = f"auto bounce({REGION} region, Box box) -> Box {{ return move(box); }}"


class OwningSuite(Suite):
    def __init__(self, compiler, directory, compile_only):
        super().__init__(compiler, directory, entry_name="entry")
        self.compile_only = compile_only
        self.skipped_native = 0

    def compile(self, name, source):
        if not self.compile_only:
            return super().compile(name, source)
        folder = self.directory / name
        folder.mkdir()
        input_path = folder / "input.au"
        assembly = folder / "output.s"
        input_path.write_text(source)
        result = command([self.compiler, input_path, "-o", assembly])
        require(result.returncode == 0, f"{name}: compile failed: {result.stderr.decode()}")
        text = assembly.read_text()
        require(f".local {ENTRY}\n" in text, f"{name}: missing private entry")
        self.programs += 1
        return folder / "native-not-built"

    def run(self, *args, **kwargs):
        if self.compile_only:
            self.skipped_native += 1
        else:
            super().run(*args, **kwargs)

    def trap(self, *args, **kwargs):
        if self.compile_only:
            self.skipped_native += 1
        else:
            super().trap(*args, **kwargs)

    def imported_diagnostic_locations(self):
        folder = self.directory / "reject-imported-copy-location"
        folder.mkdir()
        imported = folder / "owners.au"
        imported.write_text("export module owners;\nexport namespace owners {\n" + BOX + "\n}\n")
        source = folder / "input.au"
        contents = (
            "module copied;\nimport owners;\n"
            f"auto entry({REGION} region)->i64 {{\n"
            f"    {OWNER} bytes = region.try_allocate(1);\n"
            "    owners::Box box = owners::Box(region, move(bytes), 23u8);\n"
            "    owners::Box copy = box;\n"
            "    return 0;\n}\n"
        )
        source.write_text(contents)
        result = command([self.compiler, "--check", "--diagnostics=json", "--module-root", folder, source])
        require(result.returncode == 1 and not result.stderr, "imported owning copy has structured rejection")
        data = json.loads(result.stdout)
        diagnostic = data["diagnostics"][0]
        line = contents.splitlines()[5]
        column = line.index("box;") + 1
        offset = contents.index("box;", contents.index("owners::Box copy"))
        require(
            diagnostic["path"] == str(source)
            and diagnostic["range"]["start"] == {"line": 6, "column": column, "offset": offset},
            f"illegal owning copy must identify use site, not imported class: {diagnostic}",
        )
        require(diagnostic["message"] == "owning class cannot be copied; use move(named_local)", "copy diagnostic")
        output = folder / "output.s"
        output.write_bytes(b"preserve prior assembly\n")
        plain = command([self.compiler, "--module-root", folder, source, "-o", output])
        prefix = f"{source}:6:{column}: error AU3001: ".encode()
        require(plain.returncode == 1 and plain.stderr.startswith(prefix), "text copy diagnostic exact use site")
        require(output.read_bytes() == b"preserve prior assembly\n", "copy rejection preserves output")
        (folder / "copy.json").write_bytes(result.stdout)
        (folder / "copy.stderr").write_bytes(plain.stderr)
        self.rejections += 1

        folder = self.directory / "reject-imported-declaration-location"
        folder.mkdir()
        imported = folder / "owners.au"
        source = folder / "input.au"
        imported.write_text(
            f"export module owners;\nexport namespace owners {{\n    class Broken {{ {OWNER} value; }};\n}}\n"
        )
        source.write_text("module copied;\nimport owners;\nauto entry()->i64 { return 0; }\n")
        result = command([self.compiler, "--check", "--diagnostics=json", "--module-root", folder, source])
        require(result.returncode == 1 and not result.stderr, "invalid imported declaration rejects")
        diagnostic = json.loads(result.stdout)["diagnostics"][0]
        require(
            diagnostic["path"] == str(imported)
            and diagnostic["range"]["start"]["line"] == 3
            and diagnostic["range"]["start"]["column"] == 11,
            f"invalid imported declaration must keep its own location: {diagnostic}",
        )
        (folder / "declaration.json").write_bytes(result.stdout)
        self.rejections += 1

    def cases(self):
        dynamic = self.compile(
            "dynamic-private-field",
            program(
                CREATE
                + """
                if (!box.ok() || !box.check() || size_of(Box) != 64) { return -1; }
                if (n > 0) {
                    if (!box.set(n - 1, 42u8) || box.at(n - 1) != 42u8) { return -2; }
                    if (box.set(n, 33u8) || box.set(-1, 33u8)) { return -3; }
                }
                return box.size();
                """,
                BOX,
            ),
        )
        for length in (0, 1, 65, 513, 4097):
            self.run(dynamic, length, length, 0, length, 1, 1, release_order=[1])

        failed = self.compile(
            "inert-failed-field",
            program(CREATE + "if (box.ok() || box.set(0, 1u8)) { return -1; } return box.size();", BOX),
        )
        self.run(failed, 0, 1, 0, 0, 0, 0)
        self.run(failed, 100, 1, 0, 0, 0, 0, fail_after=0)

        move = self.compile(
            "local-function-return-move",
            program(
                CREATE
                + "Box second = move(box); Box third = bounce(region, move(second)); "
                + "if (!third.check()) { return -1; } return third.size();",
                BOX + BOUNCE,
            ),
        )
        self.run(move, 513, 513, 0, 513, 1, 1, release_order=[1])

        factory = self.compile(
            "factory-owner-return",
            program(
                "Box box = create(region, n); return box.size();",
                BOX + f"auto create({REGION} region, i64 n) -> Box {{ {CREATE} return move(box); }}",
            ),
        )
        self.run(factory, 65, 65, 0, 65, 1, 1)

        pair = self.compile(
            "two-fields-reverse-cleanup",
            program(
                f"{OWNER} a = region.try_allocate(2); {OWNER} b = region.try_allocate(3); "
                "Pair pair = Pair(region, move(a), move(b)); Pair moved = move(pair); return moved.size();",
                PAIR,
            ),
        )
        self.run(pair, 5, 0, 0, 24, 2, 2, release_order=[2, 1])

        pair_failed = self.compile(
            "partial-allocation-normal-cleanup",
            program(
                f"{OWNER} a = region.try_allocate(2); {OWNER} b = region.try_allocate(3); "
                "Pair pair = Pair(region, move(a), move(b)); return pair.size();",
                PAIR,
            ),
        )
        self.run(pair_failed, 2, 0, 0, 21, 1, 1, release_order=[1])

        resource_only = f"""
        class EmptyPayload {{
            {OWNER} payload;
        public:
            EmptyPayload({REGION} region, {OWNER} value) : payload(move(value)) {{}}
            auto ok() const -> bool {{ return payload.ok(); }}
        }};
        """
        empty = self.compile(
            "resource-only-class-is-not-empty",
            program(
                f"{OWNER} bytes = region.try_allocate(0); "
                "EmptyPayload empty = EmptyPayload(region, move(bytes)); "
                "if (!empty.ok() || size_of(EmptyPayload) != 32) { return -1; } return 42;",
                resource_only,
            ),
        )
        self.run(empty, 0, 0, 0, 42, 1, 1)

        mixed = self.compile(
            "mixed-reverse-local-cleanup",
            program(
                f"{OWNER} outer = region.try_allocate(1); "
                + CREATE
                + f"{OWNER} after = region.try_allocate(1); return box.size() + 40;",
                BOX,
            ),
        )
        self.run(mixed, 4, 2, 0, 42, 3, 3, release_order=[3, 2, 1])

        branched = self.compile(
            "returning-branch-transfer",
            program(
                CREATE + "if (flag == 0) { return consume(region, move(box)); } return box.size() + 1;",
                BOX + CONSUME,
            ),
        )
        self.run(branched, 3, 3, 0, 3, 1, 1)
        self.run(branched, 3, 3, 1, 4, 1, 1)

        loop = self.compile(
            "loop-local-quota-reuse",
            program(
                "i64 index = 0; while (index < 3) { " + CREATE + "index = index + box.size(); } return index;",
                BOX,
            ),
        )
        self.run(loop, 1, 1, 0, 3, 3, 1, release_order=[1, 2, 3])

        const = self.compile(
            "const-owner-reads-and-drops",
            program(
                f"{OWNER} bytes = region.try_allocate(n); const Box box = Box(region, move(bytes), 23u8); "
                "return box.size();",
                BOX,
            ),
        )
        self.run(const, 3, 3, 0, 3, 1, 1)

        scalar_stack = self.compile(
            "cleanup-preserves-saved-operands",
            program(
                CREATE + "return 10 + consume(region, move(box)) + 30;",
                BOX + CONSUME,
            ),
        )
        self.run(scalar_stack, 2, 2, 0, 42, 1, 1)

        mixed_args = self.compile(
            "six-mixed-resource-arguments",
            program(
                CREATE + f"{OWNER} other = region.try_allocate(1); "
                "return mixed(region, 23u8, move(box), 99u64, move(other), true);",
                BOX
                + f"""
                auto mixed({REGION} region, u8 first, Box box, u64 fourth, {OWNER} bytes, bool last)->i64 {{
                    if (first != 23u8 || fourth != 99u64 || !last || !box.check()) {{ return -1; }}
                    return box.size() + bytes.size() + 40;
                }}
                """,
            ),
        )
        self.run(mixed_args, 2, 1, 0, 42, 2, 2, release_order=[2, 1])

        unused_parameter = self.compile(
            "constructor-unused-owner-cleanup",
            program(
                f"{OWNER} a=region.try_allocate(1); {OWNER} b=region.try_allocate(2); "
                "Select selected=Select(region,move(a),move(b)); return selected.size();",
                f"""
                class Select {{
                    {OWNER} selected;
                public:
                    Select({REGION} region, {OWNER} first, {OWNER} unused):selected(move(first)){{}}
                    auto size() const->i64{{return selected.size();}}
                }};
                """,
            ),
        )
        self.run(unused_parameter, 3, 0, 0, 1, 2, 2, release_order=[2, 1])

        report = """
        class Report {
            i64 value;
        public:
            Report(i64 code):value(code){}
            auto get() const->i64{return value;}
            auto set(i64 code)->i64{value=code;return value;}
        };
        """
        holder = (
            report
            + f"""
        class Holder {{
            {OWNER} payload;
        public:
            Report child;
            Holder({REGION} region, {OWNER} bytes, Report initial):payload(move(bytes)),child(initial){{}}
            auto size() const->i64{{return payload.size();}}
            auto report(Report argument,i64 number)->Report{{
                child.set(number);
                const Report result=argument;
                return result;
            }}
            auto child_value() const->i64{{return child.get();}}
        }};
        """
        )
        holder_start = (
            f"{OWNER} bytes=region.try_allocate(n); Report initial=Report(7); "
            "Holder holder=Holder(region,move(bytes),initial);"
        )
        copied_methods = self.compile(
            "copied-constructor-and-method-boundaries",
            program(
                holder_start + "Report input=Report(42); const Report output=holder.report(input,99); "
                "if (holder.child_value()!=99 || initial.get()!=7 || input.get()!=42) { return -1; } "
                "return output.get();",
                holder,
            ),
        )
        self.run(copied_methods, 2, 2, 0, 42, 1, 1)
        shadow = self.compile(
            "fresh-result-shadows-owning-receiver",
            program(
                holder_start + "{ Report input=Report(42); const Report holder=holder.report(input,99); "
                "return holder.get(); }",
                holder,
            ),
        )
        self.run(shadow, 2, 2, 0, 42, 1, 1)
        consume_holder = f"auto consume_holder({REGION} r,Holder h)->i64{{return h.size();}}"
        self.reject(
            "child-receiver-containing-root-consumed",
            program(
                holder_start + "return holder.child.set(consume_holder(region,move(holder)));",
                holder + consume_holder,
            ),
        )
        self.reject(
            "unused-owning-template-argument",
            program(
                CREATE + "Tag<Box> tag=Tag<Box>(); return 0;", BOX + "template<Value T> class Tag {public:Tag(){}};"
            ),
        )

        bounds = self.compile("field-exact-bounds-trap", program(CREATE + "return i64(box.at(n));", BOX))
        self.trap(bounds, 3, 3)
        self.trap(bounds, 0, 0)

        bad = {
            "implicit-copy": "Box copy = box; return 0;",
            "implicit-argument": "return consume(region, box);",
            "double-move": "Box copy = move(box); Box again = move(box); return 0;",
            "method-after-move": "Box copy = move(box); return box.size();",
            "scalar-after-move": "Box copy = move(box); return box.marker;",
            "scalar-write-after-move": "Box copy = move(box); box.marker = 1; return 0;",
            "reassignment": "box = move(box); return 0;",
            "receiver-consumed-index": "return i64(box.at(consume(region, move(box))));",
            "receiver-consumed-value": "box.set(0, u8(consume(region, move(box)))); return 0;",
            "scalar-store-consumed-root": "box.marker = consume(region, move(box)); return 0;",
            "conditional-move": "if (flag == 0) { consume(region, move(box)); } return 0;",
            "logical-move": "bool value = flag == 0 && consume(region, move(box)) == 0; return 0;",
            "loop-condition-move": "while (consume(region, move(box)) == 0) { return 1; } return 0;",
            "loop-backedge-move": "while (flag == 0) { consume(region, move(box)); } return 0;",
            "private-extraction": f"{OWNER} extracted = move(box.payload); return 0;",
            "private-copy": f"{OWNER} extracted = box.payload; return 0;",
            "field-reassignment": "box.payload = move(bytes); return 0;",
            "discard-owner-result": "bounce(region, move(box)); return 0;",
        }
        for name, body in bad.items():
            self.reject(name, program(CREATE + body, BOX + CONSUME + BOUNCE))
        self.reject("implicit-return", program("return 0;", BOX + f"auto bad({REGION} r, Box b)->Box{{return b;}}"))
        self.reject("missing-region", program("return 0;", BOX + "auto bad(Box b)->i64{return 0;}"))
        self.reject(
            "const-move",
            program(
                f"{OWNER} bytes=region.try_allocate(1); const Box box=Box(region,move(bytes),23u8); "
                "Box moved=move(box); return 0;",
                BOX,
            ),
        )
        self.reject(
            "const-write",
            program(
                f"{OWNER} bytes=region.try_allocate(1); const Box box=Box(region,move(bytes),23u8); "
                "box.set(0, 1u8); return 0;",
                BOX,
            ),
        )
        self.reject("nested-owning-field", program("return 0;", BOX + "class Outer { Box box; };"))
        self.reject("public-owner-field", program("return 0;", f"class Bad {{ public: {OWNER} bytes; }};"))
        self.reject(
            "constructor-implicit-owner",
            program("return 0;", f"class Bad {{{OWNER} b;public:Bad({REGION} r,{OWNER} a):b(a){{}}}};"),
        )
        self.imported_diagnostic_locations()
        return {
            "mode": "compile-only" if self.compile_only else "native",
            "compiled_programs": self.programs,
            "source_rejections": self.rejections,
            "native_cases": self.native,
            "exact_bounds_traps": self.traps,
            "native_checks_not_run": self.skipped_native,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--compile-only", action="store_true")
    args = parser.parse_args()
    compiler = args.compiler.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="aurora-owning-classes-") as temporary:
        directory = args.artifact_dir.resolve() if args.artifact_dir else Path(temporary)
        directory.mkdir(parents=True, exist_ok=True)
        summary = OwningSuite(compiler, directory, args.compile_only).cases()
        summary["compiler_sha256"] = hashlib.sha256(compiler.read_bytes()).hexdigest()
        (directory / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
