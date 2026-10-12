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

from owned_bytes import OWNER, REGION, ROOT, Suite, command, program
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

RESIZABLE_BOX = BOX.replace(
    "    auto ok() const -> bool",
    "    auto try_resize(i64 count) -> bool { return payload.try_resize(count); }\n    auto ok() const -> bool",
)

COPIED_PACKET = """
class Packet {
    builtin::array<u8, 64> bytes;
    i64 code;
public:
    Packet(i64 status) : bytes{}, code(status) {}
    auto status() const -> i64 { return code; }
    auto at(i64 index) const -> u8 { return bytes[index]; }
    auto set(i64 index, u8 value) -> bool { bytes[index] = value; return true; }
};
"""


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
        result = command([self.compiler, *self.module_args, input_path, "-o", assembly])
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

    def producing_field_initializers(self):
        helpers = f"""
        auto fixed({REGION} region) -> {OWNER} {{
            {OWNER} result = region.try_allocate(3); return move(result);
        }}
        auto keep({REGION} region, bool first, bool second, {OWNER} input) -> {OWNER} {{
            if (input.ok() && (!first || !second || input.at(0) != 99u8)) {{
                {OWNER} failed = region.try_allocate(-1); return move(failed);
            }}
            return move(input);
        }}
        class Six {{
            {OWNER} a; {OWNER} b; {OWNER} c; {OWNER} d; {OWNER} e; {OWNER} f;
        public:
            Six({REGION} region, {OWNER} first, {OWNER} incoming)
                : f(region.try_allocate(0)), e(region.try_allocate(5)),
                  d(keep(region, incoming.set(0, 42u8), incoming.set(0, 99u8), move(incoming))),
                  c(fixed(region)), b(region.try_allocate(2)), a(move(first)) {{}}
            auto status() const -> i64 {{
                if (a.size() != i64(a.ok()) || b.size() != 2 * i64(b.ok()) ||
                    c.size() != 3 * i64(c.ok()) || d.size() != 4 * i64(d.ok()) ||
                    e.size() != 5 * i64(e.ok()) || f.size() != 0) {{ return -1; }}
                if (d.ok() && d.at(0) != 99u8) {{ return -2; }}
                return i64(a.ok()) + 2 * i64(b.ok()) + 4 * i64(c.ok()) +
                    8 * i64(d.ok()) + 16 * i64(e.ok()) + 32 * i64(f.ok());
            }}
        }};
        auto forward({REGION} region, Six input) -> Six {{ return move(input); }}
        """
        mixed = self.compile(
            "produced-fields-declaration-order-six-owners",
            program(
                f"{OWNER} first = region.try_allocate(1); {OWNER} incoming = region.try_allocate(4); "
                "Six box = Six(region, move(first), move(incoming)); "
                "const Six result = forward(region, move(box)); "
                "if (size_of(Six) != 192) { return -3; } return result.status();",
                helpers,
            ),
        )
        # The host adapter adds a 32-byte allocation record even for zero capacity.
        # Caller allocations precede field-order producers; d keeps caller allocation 2.
        for allowed in range(7):
            self.run(
                mixed,
                32,
                0,
                0,
                sum([1, 8, 2, 4, 16, 32][:allowed]),
                allowed,
                allowed,
                fail_after=allowed,
                release_order=[i for i in [6, 5, 2, 4, 3, 1] if i <= allowed],
                attempted_sizes=[33, 36, 34, 35, 37, 32],
            )
        self.run(mixed, 7, 0, 0, 43, 4, 4, release_order=[4, 2, 3, 1], attempted_sizes=[33, 36, 34, 32])

        bad_initializers = {
            "implicit-copy": "first(input), second(region.try_allocate(2))",
            "duplicate-move": "first(keep(region, true, true, move(input))), second(move(input))",
            "consumed-argument-read": (
                "first(keep(region, true, true, move(input))), second(region.try_allocate(input.size()))"
            ),
            "temporary-owner-argument": "first(keep(region, true, true, fixed(region))), second(move(input))",
            "receiver-read": "first(region.try_allocate(1)), second(region.try_allocate(first.size()))",
            "scalar-result": "first(42), second(move(input))",
            "conditional-producer": "first(true ? fixed(region) : fixed(region)), second(move(input))",
            "missing-field": "first(fixed(region))",
            "duplicate-field": "first(fixed(region)), first(fixed(region)), second(move(input))",
        }
        for name, initializers in bad_initializers.items():
            self.reject(
                "produced-field-" + name,
                program(
                    "return 0;",
                    helpers
                    + f"""
                    class Bad {{ {OWNER} first; {OWNER} second;
                    public: Bad({REGION} region, {OWNER} input) : {initializers} {{}} }};
                """,
                ),
            )
        self.reject(
            "produced-field-second-region",
            program(
                "return 0;",
                f"class Bad {{ {OWNER} value; public: "
                f"Bad({REGION} first, {REGION} other) : value(other.try_allocate(1)) {{}} }};",
            ),
        )
        later_trap = self.compile(
            "produced-field-later-bounds-trap",
            program(
                "Trap result = Trap(region, n); return 0;",
                f"""
                auto fail({REGION} region, i64 index) -> {OWNER} {{
                    {OWNER} source = region.try_allocate(1);
                    {OWNER} result = region.try_allocate(i64(source.at(index))); return move(result);
                }}
                class Trap {{ {OWNER} first; {OWNER} second;
                public: Trap({REGION} region, i64 index)
                    : second(fail(region, index)), first(region.try_allocate(2)) {{}} }};
            """,
            ),
        )
        # Fail-stop subprocess observation makes no claim about unwinding live owners.
        self.trap(later_trap, 16, 1)

    def copied_resource_results(self):
        snapshots = self.compile(
            "copied-resource-result-left-to-right-snapshots",
            program(
                """
                i64 iteration = 0;
                while (iteration < 2) {
                    const Packet saved = make_packet(region);
                    if (saved.status() != 42 || saved.at(63) != 201u8) { return -1; }
                    Packet changed = saved;
                    changed.set(0, 123u8);
                    i64 index = 0;
                    while (index < 63) {
                        if (saved.at(index) != u8((index * 53 + 7) % 256)) { return -2; }
                        index = index + 1;
                    }
                    iteration = iteration + 1;
                }
                return 42;
                """,
                COPIED_PACKET
                + f"""
                auto select_packet(Packet before, bool changed, Packet after, u64 wide, u8 byte, i64 number)
                    -> Packet {{
                    if (!changed || before.at(0) != 7u8 || after.at(0) != 99u8 ||
                        wide != 18364758544493064720u64 || byte != 201u8 || number != -4294967313) {{
                        const Packet failed = Packet(-1);
                        return failed;
                    }}
                    i64 index = 1;
                    while (index < 64) {{
                        const u8 expected = u8((index * 53 + 7) % 256);
                        if (before.at(index) != expected || after.at(index) != expected) {{
                            const Packet failed = Packet(-2);
                            return failed;
                        }}
                        index = index + 1;
                    }}
                    Packet result = before;
                    result.set(63, byte);
                    return result;
                }}
                auto make_packet({REGION} region) -> Packet {{
                    {OWNER} local = region.try_allocate(1);
                    if (!local.ok()) {{ const Packet failed = Packet(-3); return failed; }}
                    Packet source = Packet(42);
                    i64 index = 0;
                    while (index < 64) {{
                        source.set(index, u8((index * 53 + 7) % 256));
                        index = index + 1;
                    }}
                    const Packet result = select_packet(
                        source, source.set(0, 99u8), source, 18364758544493064720u64, 201u8, -4294967313);
                    return result;
                }}
                """,
            ),
        )
        self.run(snapshots, 1, 0, 0, 42, 2, 1, release_order=[1, 2])

        packed = self.compile(
            "copied-resource-result-packed-scalar-and-owner-arguments",
            program(
                CREATE
                + """
                box.set(0, 42u8);
                const Packet result = consume_packet(region, box.at(0), box.set(0, 99u8),
                    move(box), 18364758544493064720u64, -4294967313);
                if (result.status() != 42 || result.at(0) != 42u8 || result.at(63) != 99u8) { return -1; }
                return 42;
                """,
                BOX
                + COPIED_PACKET
                + f"""
                auto consume_packet({REGION} region, u8 before, bool written, Box owner, u64 wide, i64 number)
                    -> Packet {{
                    {OWNER} temporary = region.try_allocate(1);
                    if (!temporary.ok() || before != 42u8 || !written || owner.at(0) != 99u8 ||
                        wide != 18364758544493064720u64 || number != -4294967313) {{
                        const Packet failed = Packet(-1);
                        return failed;
                    }}
                    Packet result = Packet(42);
                    result.set(0, before);
                    result.set(63, owner.at(0));
                    return result;
                }}
                """,
            ),
        )
        self.run(packed, 2, 1, 0, 42, 2, 2, release_order=[2, 1])

        empty = self.compile(
            "empty-copied-resource-result-cleans-owner",
            program(
                "const Empty result = make_empty(region); return result.answer();",
                f"""
                class Empty {{ public: Empty() {{}} auto answer() const -> i64 {{ return 42; }} }};
                auto make_empty({REGION} region) -> Empty {{
                    {OWNER} bytes = region.try_allocate(1);
                    const Empty result = Empty();
                    return result;
                }}
                """,
            ),
        )
        self.run(empty, 1, 0, 0, 42, 1, 1, release_order=[1])

        factory = f"""
            auto packet({REGION} region) -> Packet {{
                const Packet result = Packet(42);
                return result;
            }}
        """
        other = COPIED_PACKET.replace("Packet", "OtherPacket")
        rejected_bodies = {
            "wrong-nominal-initializer": "const OtherPacket wrong = packet(region); return 0;",
            "discarded-result": "packet(region); return 0;",
            "temporary-receiver": "return packet(region).status();",
            "temporary-copied-argument": "return inspect(packet(region));",
            "scalar-initializer": "const i64 wrong = packet(region); return wrong;",
            "reassignment": "Packet result = Packet(0); result = packet(region); return 0;",
        }
        for name, body in rejected_bodies.items():
            self.reject(
                "copied-resource-" + name,
                program(
                    body,
                    COPIED_PACKET + other + factory + "auto inspect(Packet value) -> i64 { return value.status(); }",
                ),
            )
        rejected_helpers = {
            "direct-call-return": f"auto forward({REGION} region) -> Packet {{ return packet(region); }}",
            "wrong-nominal-return": f"auto wrong({REGION} region) -> Packet {{ "
            "const OtherPacket result = OtherPacket(42); return result; }",
            "copied-parameter": f"auto wrong({REGION} region, Packet value) -> Packet {{ return value; }}",
            "span-parameter": f"auto wrong({REGION} region, builtin::span<const u8> view) -> Packet {{ "
            "const Packet result = Packet(42); return result; }",
            "region-result": f"auto wrong({REGION} region) -> {REGION} {{ return region; }}",
            "span-result": f"auto wrong({REGION} region) -> builtin::span<const u8> {{ "
            f"{OWNER} bytes = region.try_allocate(1); "
            "const builtin::span<const u8> view = borrow_bytes(bytes); return view; }",
            "owning-result-copy": f"auto wrong({REGION} region, Box value) -> Box {{ return value; }}",
            "oversized-result": f"auto wrong({REGION} region) -> TooLarge {{ "
            "const TooLarge result = TooLarge(); return result; }",
        }
        too_large = "class TooLarge { builtin::array<i64, 64> words; i64 extra; "
        too_large += "public: TooLarge() : words{}, extra(0) {} };"
        for name, helper in rejected_helpers.items():
            self.reject(
                "copied-resource-" + name,
                program("return 0;", BOX + COPIED_PACKET + other + too_large + factory + helper),
            )

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

    def resize_cases(self):
        cycle = self.compile(
            "field-resize-cycle-and-transfer",
            program(
                CREATE
                + """
                if (!box.ok() || !box.check()) { return -1; }
                i64 index = 0;
                while (index < n) { box.set(index, u8((index * 17 + 3) % 256)); index = index + 1; }
                if (!box.try_resize(n + 3) || box.size() != n + 3 || !box.check()) { return -2; }
                index = 0;
                while (index < n) {
                    if (box.at(index) != u8((index * 17 + 3) % 256)) { return -3; }
                    index = index + 1;
                }
                while (index < n + 3) { if (box.at(index) != 0u8) { return -4; } index = index + 1; }
                if (!box.try_resize(1)) { return -5; }
                if ((n == 0 && box.at(0) != 0u8) || (n > 0 && box.at(0) != 3u8)) { return -5; }
                if (!box.try_resize(0) || !box.ok() || box.size() != 0 || box.set(0, 1u8)) { return -6; }
                if (!box.try_resize(n) || box.size() != n || !box.check()) { return -7; }
                index = 0;
                while (index < n) { if (box.at(index) != 0u8) { return -8; } index = index + 1; }
                Box moved = bounce(region, move(box));
                if (!moved.check()) { return -9; }
                return moved.size();
                """,
                RESIZABLE_BOX + BOUNCE,
            ),
        )
        for length in (0, 1, 65, 513, 4097):
            count = 4 if length == 0 else 5
            self.run(cycle, length + 3, length, 0, length, count, 1, release_order=list(range(1, count + 1)))

        preserved = self.compile(
            "field-resize-failure-preservation",
            program(
                CREATE
                + """
                box.set(0, 17u8); box.set(1, 33u8); box.set(2, 99u8);
                bool changed = box.try_resize(flag);
                if (changed != (flag == n)) { return -1; }
                if (!box.ok() || box.size() != n || !box.check()) { return -2; }
                if (box.at(0) != 17u8 || box.at(1) != 33u8 || box.at(2) != 99u8) { return -3; }
                return 42;
                """,
                RESIZABLE_BOX,
            ),
        )
        for length in (-1, -(1 << 63), 4, (1 << 63) - 1):
            self.run(preserved, 3, 3, length, 42, 1, 1, release_order=[1])
        for length in (0, 1, 3, 4):
            self.run(preserved, 4, 3, length, 42, 1, 1, fail_after=1, release_order=[1])

        failed = self.compile(
            "field-resize-inert-owner",
            program(
                CREATE + "if (box.try_resize(flag) || box.ok() || box.size() != 0 || !box.check()) { return -1; } "
                "Box moved = move(box); if (moved.try_resize(0) || moved.ok()) { return -2; } return 42;",
                RESIZABLE_BOX,
            ),
        )
        for length in (-1, 0, 65):
            self.run(failed, 128, -1, length, 42, 0, 0)
        self.run(failed, 128, 3, 65, 42, 0, 0, fail_after=0)

        pair_helpers = PAIR.replace(
            "    auto size() const -> i64",
            "    auto resize_first(i64 count) -> bool { return first.try_resize(count); }\n"
            "    auto resize_second(i64 count) -> bool { return second.try_resize(count); }\n"
            "    auto first_size() const -> i64 { return first.size(); }\n"
            "    auto second_size() const -> i64 { return second.size(); }\n"
            "    auto first_at(i64 index) const -> u8 { return first.at(index); }\n"
            "    auto second_at(i64 index) const -> u8 { return second.at(index); }\n"
            "    auto size() const -> i64",
        )
        pair = self.compile(
            "field-resize-exact-second-selector",
            program(
                f"{OWNER} a = region.try_allocate(3); {OWNER} b = region.try_allocate(2); "
                """
                a.set(0, 17u8); a.set(2, 99u8); b.set(0, 33u8); b.set(1, 55u8);
                Pair pair = Pair(region, move(a), move(b));
                if (!pair.resize_second(n) || pair.second_size() != n || pair.first_size() != 3) { return -1; }
                if (pair.first_at(0) != 17u8 || pair.first_at(2) != 99u8 ||
                    pair.second_at(0) != 33u8 || pair.second_at(1) != 55u8) { return -2; }
                i64 index = 2;
                while (index < n) { if (pair.second_at(index) != 0u8) { return -3; } index = index + 1; }
                if (!pair.resize_first(1) || pair.first_size() != 1 || pair.first_at(0) != 17u8 ||
                    pair.second_size() != n || pair.second_at(1) != 55u8) { return -4; }
                return pair.size();
                """,
                pair_helpers,
            ),
        )
        for length in (3, 65, 513):
            self.run(pair, length + 3, length, 0, length + 20, 4, 2, release_order=[2, 1, 3, 4])

        stack = self.compile(
            "field-resize-expression-stack",
            program(
                CREATE + "return 7 + score(box.size(), box.try_resize(3), box.size()) + "
                "(9 + score(box.size(), box.try_resize(4), box.size()));",
                RESIZABLE_BOX + "auto score(i64 before, bool success, i64 after)->i64 {"
                "if (!success) {return -1000;} return before * 100 + after;}",
            ),
        )
        self.run(stack, 4, 1, 0, 423, 3, 1, release_order=[1, 2, 3])

        shadow = self.compile(
            "field-resize-result-shadows-root",
            program(
                CREATE + "{ const bool box = box.try_resize(2); if (!box) { return -1; } } return box.size();",
                RESIZABLE_BOX,
            ),
        )
        self.run(shadow, 2, 1, 0, 2, 2, 1, release_order=[1, 2])

        sibling = self.compile(
            "field-resize-length-consumes-sibling",
            program(
                CREATE + f"{OWNER} extra = region.try_allocate(65); Box sibling = Box(region, move(extra), 23u8); "
                "box.set(0, 199u8); if (!box.try_resize(consume(region, move(sibling)))) { return -1; } "
                "if (box.size() != 65 || box.at(0) != 199u8 || box.at(64) != 0u8) { return -2; } return 42;",
                RESIZABLE_BOX + CONSUME,
            ),
        )
        self.run(sibling, 66, 1, 0, 42, 3, 2, release_order=[2, 1, 3])

        bounds = self.compile(
            "field-resize-shrunk-bounds",
            program(CREATE + "if (!box.try_resize(flag)) { return -1; } return i64(box.at(flag));", RESIZABLE_BOX),
        )
        self.trap(bounds, 3, 3, 0)
        self.trap(bounds, 3, 3, 1)

        for name, body in {
            "field-resize-receiver-consumed-length": "box.try_resize(consume(region, move(box))); return 0;",
            "field-resize-after-move": "Box moved = move(box); box.try_resize(2); return 0;",
            "field-resize-private-access": "box.payload.try_resize(2); return 0;",
        }.items():
            self.reject(name, program(CREATE + body, RESIZABLE_BOX + CONSUME))
        self.reject(
            "field-resize-const-owner",
            program(
                f"{OWNER} bytes = region.try_allocate(1); const Box box = Box(region, move(bytes), 23u8); "
                "box.try_resize(2); return 0;",
                RESIZABLE_BOX,
            ),
        )
        self.reject(
            "field-resize-const-method",
            program("return 0;", RESIZABLE_BOX.replace("try_resize(i64 count) ->", "try_resize(i64 count) const ->")),
        )
        for name, arguments in {
            "u64": "2u64",
            "u8": "2u8",
            "bool": "true",
            "missing": "",
            "extra": "1, 2",
        }.items():
            self.reject(
                "field-resize-" + name + "-length",
                program(
                    "return 0;", RESIZABLE_BOX.replace("payload.try_resize(count)", f"payload.try_resize({arguments})")
                ),
            )
        self.reject(
            "field-resize-bool-result",
            program(
                "return 0;",
                RESIZABLE_BOX.replace(
                    "auto try_resize(i64 count) -> bool { return payload.try_resize(count); }",
                    "auto bad_result(i64 count) -> i64 { i64 bad_size = payload.try_resize(count); return bad_size; }",
                ),
            ),
        )

        # Raw byte owners may resize before transfer, but the device still requires
        # whole-sector backing and must not expose resizing through either API.
        saved_module_args = self.module_args
        self.module_args = ["--module-root", ROOT / "library"]
        try:
            imports = (
                "import std.binary; import std.binary_buffer; import storage.sector; "
                "import storage.block_io; import storage.ram_sector;"
            )
            setup = (
                f"{OWNER} bytes = region.try_allocate(512); "
                "storage::RamSectorDevice device = storage::RamSectorDevice(region, move(bytes));"
            )
            for name, action in {
                "ram-device-resize-unexposed": "device.try_resize(513);",
                "ram-device-payload-resize-private": "device.payload.try_resize(513);",
            }.items():
                self.reject(name, program(setup + action + "return 0;", imports))
            unaligned = self.compile(
                "resized-backing-retains-whole-sector-invariant",
                program(
                    f"{OWNER} bytes = region.try_allocate(512); "
                    "if (!bytes.try_resize(n)) { return -1; } "
                    "storage::RamSectorDevice device = storage::RamSectorDevice(region, move(bytes)); "
                    "const storage::SectorGeometry geometry = device.geometry(); "
                    "if (device.status() != storage::SectorIoStatus::invalid_source || "
                    "geometry.sector_count() != 0u64 || geometry.can_write()) { return -2; } return 42;",
                    imports,
                ),
            )
            for length in (1, 511, 513, 1023):
                self.run(unaligned, max(512, length), length, 0, 42, 2, 1, release_order=[1, 2])
        finally:
            self.module_args = saved_module_args

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
        self.reject(
            "direct-owning-constructor-return",
            program(
                "return 0;",
                BOX + f"auto make({REGION} region,{OWNER} bytes)->Box{{return Box(region,move(bytes),23u8);}}",
            ),
        )
        self.reject("nested-owning-field", program("return 0;", BOX + "class Outer { Box box; };"))
        self.reject("public-owner-field", program("return 0;", f"class Bad {{ public: {OWNER} bytes; }};"))
        self.reject(
            "constructor-implicit-owner",
            program("return 0;", f"class Bad {{{OWNER} b;public:Bad({REGION} r,{OWNER} a):b(a){{}}}};"),
        )
        self.imported_diagnostic_locations()
        self.resize_cases()
        self.copied_resource_results()
        self.producing_field_initializers()
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
