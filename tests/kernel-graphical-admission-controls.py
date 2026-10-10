#!/usr/bin/env python3
"""Independent hostile combined-profile controls. Source prepared, not qualified.

No compiler, guest or subprocess is launched. All safety assertions use explicit
exceptions or unittest assertions and remain active under python -O.
"""

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "graphical_controls_target", ROOT / "scripts/kernel_graphical_console_admission.py"
)
graphical = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = graphical
spec.loader.exec_module(graphical)
decoder = graphical.load("graphical_controls_decoder", ROOT / "tests/kernel-uefi-owned-bytes-stack.py")


REFLECTION = (
    "aurora_reflect_size",
    "aurora_reflect_field_count",
    *(f"__au_reflect_s{module}_{field}" for module in (1, 2, 3, 4, 5, 6) for field in ("size", "field_count")),
)


def body(operations):
    return [decoder.Instruction(index, 1, op, args) for index, (op, args) in enumerate(operations)]


def fixture(specification, analyze=True):
    """Build machine-shaped fixtures only; the expected denials are below."""
    starts = {100 * index: name for index, name in enumerate(specification)}
    addresses = {name: address for address, name in starts.items()}
    symbols, code = {}, {}
    for name, rows in specification.items():
        base = addresses[name]
        symbols[name] = decoder.Symbol(name, base, len(rows), 1, 2)
        for index, (op, args) in enumerate(rows):
            if args.startswith("@"):
                target, _, offset = args[1:].partition("+")
                args = f"{addresses[target] + int(offset or 0):x} <{target}>"
            code[base + index] = decoder.Instruction(base + index, 1, op, args)
    functions = (
        {name: decoder.analyze_function(symbol, code, starts) for name, symbol in symbols.items()} if analyze else {}
    )
    return functions, symbols, code, starts


class NativeArtifacts(unittest.TestCase):
    def test_native_source_object_and_same_compilation_sidecars(self):
        with tempfile.TemporaryDirectory(prefix="native-admission-") as temporary:
            root = Path(temporary)
            source = root / "checkout"
            unit = source / "kernel/uefi/payload.cpp"
            unit.parent.mkdir(parents=True)
            unit.write_text("void local_fn() {}\n")
            build = root / "meson"
            directory = build / "kernel-images/uefi/test-profile"
            original = directory / "native/payload.p/payload.cpp.o"
            original.parent.mkdir(parents=True)
            exported = directory / "objects/payload.o"
            exported.parent.mkdir()
            spelling = os.path.relpath(unit, build)
            signature = "void local_fn()"
            location = spelling + ":1:1"
            label = signature + "\n" + location + "\n16 bytes (static)"
            graph = "graph: { title: " + json.dumps(spelling) + "\n"
            graph += "node: { title: " + json.dumps(spelling + ":local_fn") + " label: " + json.dumps(label) + " }\n}"
            contents = {
                ".o": b"one actual compilation",
                ".su": (location + ":" + signature + "\t16\tstatic\n").encode(),
                ".ci": graph.encode(),
            }
            for suffix, data in contents.items():
                original.with_suffix(suffix).write_bytes(data)
                exported.with_suffix(suffix).write_bytes(data)
            record = exported.with_suffix(".source.json")
            association = dict(
                source=str(unit),
                compile_directory=str(build),
                native_object=str(original),
                sidecars={suffix: str(original.with_suffix("." + suffix)) for suffix in ("su", "ci")},
            )
            record.write_text(json.dumps(association))

            def check():
                rows = decoder.object_stack_rows(directory, "payload", {"local_fn": object()}, source_root=source)
                self.assertEqual(rows["local_fn"].source, "kernel/uefi/payload.cpp")
                self.assertEqual(rows["local_fn"].signature, signature)

            check()
            for field, value in (
                ("source", str(source / "kernel/other.cpp")),
                ("compile_directory", str(root)),
                ("native_object", str(exported)),
                ("sidecars", {"su": str(original.with_suffix(".su")), "ci": str(exported.with_suffix(".ci"))}),
            ):
                record.write_text(json.dumps(dict(association, **{field: value})))
                with self.subTest(field=field), self.assertRaises((ValueError, OSError)):
                    check()
            record.write_text(json.dumps(association))
            for suffix in contents:
                exported.with_suffix(suffix).write_bytes(contents[suffix] + b"changed")
                with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                    check()
                exported.with_suffix(suffix).write_bytes(contents[suffix])
            record.unlink()
            with self.assertRaises(OSError):
                check()
            record.write_text(json.dumps(association))
            original.with_suffix(".su").unlink()
            original.with_suffix(".su").symlink_to(exported.with_suffix(".su"))
            with self.assertRaises(ValueError):
                check()
            original.with_suffix(".su").unlink()
            original.with_suffix(".su").write_bytes(contents[".su"])
            record.write_text(json.dumps(association)[:-1] + ', "source": ' + json.dumps(str(unit)) + "}")
            with self.assertRaises(ValueError):
                check()
            record.write_text(json.dumps(association))
            # Even coherent sidecar replacements cannot claim a foreign TU,
            # lose exact local assembler ownership or escape the source tree.
            for changed in (
                graph.replace(json.dumps(spelling), json.dumps("foreign.cpp"), 1),
                graph.replace(":local_fn", ":other_fn"),
                graph.replace(location, "/outside/kernel.hpp:1:1"),
            ):
                original.with_suffix(".ci").write_text(changed)
                exported.with_suffix(".ci").write_text(changed)
                with self.subTest(graph=changed), self.assertRaises((ValueError, OSError)):
                    check()
            original.with_suffix(".ci").write_bytes(contents[".ci"])
            exported.with_suffix(".ci").write_bytes(contents[".ci"])
            check()

    def test_source_and_build_hash_roots_are_explicit_and_confined(self):
        common = graphical.common
        with tempfile.TemporaryDirectory(prefix="admission-roots-") as temporary:
            base = Path(temporary)
            source, build = base / "source", base / "meson/kernel-images/uefi/graphical-console"
            source.mkdir()
            build.mkdir(parents=True)
            (source / "same").write_text("source")
            (build / "same").write_text("build")
            (base / "outside").write_text("outside")
            (source / "escape").symlink_to(base / "outside")
            with (
                patch.object(common, "ROOT", common.ROOT),
                patch.object(common, "BUILD", common.BUILD),
                patch.object(common, "RECEIPT", common.RECEIPT),
            ):
                common.configure_paths(build, source)
                self.assertEqual(set(common.hashes([source / "same", build / "same"])), {"source:same", "build:same"})
                self.assertEqual(common.include_directory(), "-Ikernel-images/uefi/graphical-console")
                self.assertEqual(
                    common.build_artifacts(["payload.o", "payload.su", "payload.ci"])[-1],
                    build / "objects/payload.source.json",
                )
                for path in (base / "outside", source / "escape"):
                    with self.assertRaises(ValueError):
                        common.hashes([path])
                with self.assertRaises(ValueError):
                    common.hashes([source / "same", source / "same"])
                (base / "link").symlink_to(build, target_is_directory=True)
                with self.assertRaises(ValueError):
                    common.configure_paths(base / "link", source)

    def test_begin_depfile_tracks_sources_and_directory_membership(self):
        common = graphical.common
        helper = (ROOT / "scripts/meson-native-fixture.py").read_text()
        with tempfile.TemporaryDirectory(prefix="admission dep$# ") as temporary:
            base = Path(temporary)
            source, build = base / "checkout", base / "build/kernel-images/uefi/console"
            build.mkdir(parents=True)
            files = (
                "Makefile",
                "meson.build",
                "meson_options.txt",
                "compiler/Makefile",
                "tests/meson.build",
                "tests/compiler-test-inventory.json",
                "kernel/uefi/payload.cpp",
                "kernel-images/meson.build",
                "kernel-images/profiles/meson.build",
                "scripts/meson-native-fixture.py",
            )
            for name in files:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(helper if name.endswith("meson-native-fixture.py") else "source")
            with (
                patch.object(common, "ROOT", common.ROOT),
                patch.object(common, "BUILD", common.BUILD),
                patch.object(common, "RECEIPT", common.RECEIPT),
            ):
                common.configure_paths(build, source)
                args = SimpleNamespace(
                    action="begin-build", depfile=build / "begin.d", depfile_target=build / "program-build-start.json"
                )
                common.check_depfile_options(args)
                common.write_build_depfile(args, "program-build-start.json")
                escaped = common.load("depfile_control_escape", source / "scripts/meson-native-fixture.py").escaped
                text = args.depfile.read_text()
                self.assertTrue(text.startswith(escaped(args.depfile_target) + ": "))
                for path in [
                    source,
                    source / "kernel",
                    source / "kernel/uefi",
                    source / "kernel-images/profiles",
                    *(source / name for name in files),
                ]:
                    self.assertIn(escaped(path), text)
                for changes in (dict(action="emit"), dict(depfile_target=None)):
                    with self.assertRaises(ValueError):
                        common.check_depfile_options(SimpleNamespace(**(vars(args) | changes)))
                for changes in (dict(depfile=base / "outside.d"), dict(depfile_target=build / "wrong.json")):
                    with self.assertRaises(ValueError):
                        common.write_build_depfile(
                            SimpleNamespace(**(vars(args) | changes)), "program-build-start.json"
                        )
                with self.assertRaises(ValueError):
                    common.configure_paths(base, source)
                self.assertEqual(common.BUILD, build)


class Admission(unittest.TestCase):
    def test_exact_compiler_metadata_keeps_session_kinds_and_methods_distinct(self):
        # Equal locations and sizes must still retain exact template signatures
        # and assembler symbols. No demangled name or typedef guessing occurs.
        records, nodes, symbols = [], [], {}
        source = "kernel/uefi/graphical-console.cpp"
        for space, transport in (("console", "ServiceTransport"), ("display", "DisplayTransport")):
            for method in ("open", "validate"):
                symbol = "_Z_" + space + "_" + method
                signature = f"aurora::{space}::Session<{transport}, ServicePlatform>::{method}()"
                location = "kernel/" + space + "-session.hpp:1:1"
                records.append(location + ":" + signature + "\t16\tstatic\n")
                label = signature + "\n" + location + "\n16 bytes (static)"
                nodes.append("node: { title: " + json.dumps(symbol) + " label: " + json.dumps(label) + " }")
                symbols[symbol] = object()
        text = "graph: { title: " + json.dumps(source) + "\n" + "\n".join(nodes) + "\n}"
        rows = decoder.stack_rows("".join(records))
        mapped = decoder.callgraph_frames(text, rows, symbols, source)
        self.assertEqual(set(mapped), set(symbols))
        self.assertEqual(len({row.identity for row in mapped.values()}), 4)
        for changed in (
            text.replace(nodes[0], nodes[1]),
            text.replace(nodes[0], ""),
            text.replace("16 bytes (static)", "32 bytes (static)", 1),
            text.replace("-session.hpp:1:1", "-session.hpp:2:1", 1),
            text.replace("_Z_console_open", "_Z_display_open", 1),
            text.replace("ServiceTransport", "DisplayTransport", 1),
        ):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                decoder.callgraph_frames(changed, rows, symbols, source)
        with self.assertRaises(ValueError):
            decoder.stack_rows("".join(records) + records[0])

    def test_session_frames_require_distinct_source_and_object_ownership(self):
        frames = {symbol: 16 for symbol in graphical.SESSION_VALIDATORS}
        associations = {
            symbol: [dict(object="graphical-console.o", source=source, bytes=16, compiler_symbol=symbol)]
            for symbol, source in graphical.SESSION_VALIDATORS.items()
        }
        graphical.verify_session_frames(frames, associations)
        spelled = deepcopy(associations)
        for records in spelled.values():
            records[0]["source"] = records[0]["source"].replace("kernel/", "kernel/uefi/../")
        graphical.verify_session_frames(frames, spelled)
        for symbol, source in graphical.SESSION_VALIDATORS.items():
            missing = dict(frames)
            del missing[symbol]
            with self.assertRaises(ValueError):
                graphical.verify_session_frames(missing, associations)
            for records in (
                [],
                associations[symbol] * 2,
                [dict(object="graphical-console.o", source=source, bytes=16)],
                [dict(object="graphical-console.o", source=source, bytes=24, compiler_symbol=symbol)],
                [
                    dict(
                        object="graphical-console.o",
                        source=source,
                        bytes=16,
                        compiler_symbol=next(other for other in graphical.SESSION_VALIDATORS if other != symbol),
                    )
                ],
                [dict(object="console.o", source=source, bytes=16)],
                [dict(object="graphical-console.o", source="kernel/foreign.hpp", bytes=16)],
            ):
                changed = deepcopy(associations)
                changed[symbol] = records
                with self.assertRaises(ValueError):
                    graphical.verify_session_frames(frames, changed)

    def test_graphical_only_validator_emission_attributes(self):
        declaration = "    static auto validate(const void *grant, std::uint64_t generation, bool operation) -> void {"
        guard = (
            "#ifdef AURORA_UEFI_GRAPHICAL_CONSOLE\n"
            "    // Preserve two independently bound bootstrap authority frames in the paired profile.\n"
            "    [[gnu::noinline, gnu::noclone, gnu::noipa]]\n"
            "#endif\n"
        )

        def check(text):
            if text.count(declaration) != 1 or text.count(guard + declaration) != 1:
                raise ValueError("Missing exact graphical-only validator emission declaration")
            if text.count("gnu::noipa") != 1:
                raise ValueError("Ambiguous validator emission attributes")

        for space in ("console", "display"):
            text = (ROOT / "kernel" / (space + "-session.hpp")).read_text()
            check(text)
            for changed in (
                text.replace(guard, ""),
                text.replace("gnu::noipa", "gnu::noinline"),
                text.replace("#ifdef AURORA_UEFI_GRAPHICAL_CONSOLE", "#if 1"),
                text.replace("#ifdef AURORA_UEFI_GRAPHICAL_CONSOLE", "#ifdef AURORA_UEFI_CONSOLE"),
                text.replace(guard, guard + guard),
            ):
                with self.subTest(space=space), self.assertRaises(ValueError):
                    check(changed)

    def test_cpp_metadata_cross_checks_edges_and_retains_full_frames(self):
        for transfer in ("call", "jmp"):
            _, symbols, code, starts = fixture(
                {"root": [("popcnt", "%rax,%rax"), (transfer, "@leaf")], "leaf": [("ret", "")]}, analyze=False
            )
            frames, edges = {"root": 32, "leaf": 16}, {("root", "leaf")}
            result = graphical.cpp_stack_functions(decoder, symbols, code, starts, b"", frames, edges)
            self.assertEqual(graphical.common.graph_peak(result, frames, "root")["peak"], 48)
            self.assertEqual(result["root"]["calls"][0]["live_bytes"], 32)
            for changed in (set(), edges | {("leaf", "root")}, {("root", "absent")}, {("unknown", "leaf")}):
                with self.subTest(edges=changed), self.assertRaises(ValueError):
                    graphical.cpp_stack_functions(decoder, symbols, code, starts, b"", frames, changed)
            for op, args in (
                ("call", "*%rax"),
                ("jmp", "*%rax"),
                ("call", "65 <leaf+1>"),
                ("notrack", "jmp *%rax"),
                ("bnd", "call *%rax"),
                ("lcall", "*%rax"),
                ("jrcxz", "0 <root>"),
            ):
                changed = dict(code)
                changed[0] = decoder.Instruction(0, 1, op, args)
                with self.subTest(transfer=(op, args)), self.assertRaises(ValueError):
                    graphical.cpp_stack_functions(decoder, symbols, changed, starts, b"", frames, edges)
        for kind in ("dynamic", "dynamic,bounded"):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                decoder.stack_rows("kernel/uefi/payload.cpp:1:1:root()\t32\t" + kind)
        allowed = decoder.stack_rows(
            "kernel/uefi/payload.cpp:1:1:root()\t32\tdynamic,bounded", allow_bounded=lambda _: True
        )
        self.assertEqual(next(iter(allowed.values())).size, 32)

    def test_cpp_inline_flags_adds_one_conservative_qword(self):
        symbols = {"root": decoder.Symbol("root", 0, 4, 1, 2)}
        code = {
            0: decoder.Instruction(0, 1, "pushf", ""),
            1: decoder.Instruction(1, 2, "pop", "%r11"),
            3: decoder.Instruction(3, 1, "ret", ""),
        }
        payload = bytes.fromhex("9c415bc3")
        check = lambda rows=code, raw=payload: graphical.cpp_stack_functions(
            decoder, symbols, rows, {0: "root"}, raw, {"root": 16}, set()
        )
        self.assertEqual((check()["root"]["local_peak"], check()["root"]["inline_stack_bytes"]), (24, 8))
        for op, args, size in (("pop", "%rsp", 2), ("pop", "%r11d", 2), ("nop", "", 2), ("pop", "%r11", 1)):
            changed = dict(code)
            changed[1] = decoder.Instruction(1, size, op, args)
            with self.subTest(pop=(op, args, size)), self.assertRaises(ValueError):
                check(changed)
        for index in range(3):
            changed = bytearray(payload)
            changed[index] ^= 1
            with self.assertRaises(ValueError):
                check(raw=bytes(changed))

    def test_exact_generated_signed_division_pairs(self):
        owners = (
            "__au_v_m1_24kernel_graphical_console_n0__d9draw_cell",
            "__au_m_m2_7console13session_files_n2_7console12SessionFiles_d6submit",
        )
        symbols = {name: decoder.Symbol(name, base, 10, 1, 2) for name, base in zip(owners, (0, 16))}
        pair = bytes.fromhex("489949f7fb")
        payload = pair * 2 + b"\x90" * 6 + pair * 2
        rows = {}
        for base in (0, 5, 16, 21):
            rows[base] = decoder.Instruction(base, 2, "cqto", "")
            rows[base + 2] = decoder.Instruction(base + 2, 3, "idiv", "%r11")
        verify = lambda symbols, rows, payload: graphical.verify_generated_divisions(decoder, symbols, rows, payload)
        evidence = verify(symbols, rows, payload)
        self.assertEqual([item["owner"] for item in evidence], [owners[0]] * 2 + [owners[1]] * 2)
        with self.assertRaises(ValueError):
            verify(symbols, rows, None)
        for position in (*range(10), *range(16, 26)):
            changed = bytearray(payload)
            changed[position] ^= 1
            with self.subTest(position=position), self.assertRaises(ValueError):
                verify(symbols, rows, changed)
        for address, row in rows.items():
            changed = dict(rows)
            del changed[address]
            with self.assertRaises(ValueError):
                verify(symbols, changed, payload)
            for args in ["%rsp", "%r14", "(%r11)", "%rax,%rdx", "$0"]:
                changed = dict(rows)
                changed[address] = decoder.Instruction(row.address, row.size, row.op, args)
                with self.subTest(address=address, args=args), self.assertRaises(ValueError):
                    verify(symbols, changed, payload)
            for delta in [-1, 1]:
                changed = dict(rows)
                changed[address] = decoder.Instruction(row.address + delta, row.size, row.op, row.args)
                with self.assertRaises(ValueError):
                    verify(symbols, changed, payload)
        for owner, base in zip(owners, (0, 16)):
            for replacement in (None, (base + 1, 9), (base, 7), (base, 9)):
                changed = dict(symbols)
                if replacement is None:
                    del changed[owner]
                else:
                    changed[owner] = decoder.Symbol(owner, *replacement, 1, 2)
                with self.subTest(owner=owner, replacement=replacement), self.assertRaises(ValueError):
                    verify(changed, rows, payload)
            changed = dict(symbols)
            changed["foreign"] = changed.pop(owner)
            with self.assertRaises(ValueError):
                verify(changed, rows, payload)
        # Keeping the total pair count cannot move a third pair to one owner.
        changed = {owners[0]: decoder.Symbol(owners[0], 0, 21, 1, 2), owners[1]: decoder.Symbol(owners[1], 21, 5, 1, 2)}
        with self.assertRaises(ValueError):
            verify(changed, rows, payload)
        changed = dict(rows)
        changed[26] = decoder.Instruction(26, 2, "cqto", "")
        with self.assertRaises(ValueError):
            verify(symbols, changed, payload + b"\x48\x99")

    def test_generated_imports_and_module_identity(self):
        names = graphical.expected_language_functions()  # Fixture construction only.
        imports = [
            decoder.Symbol(name, 0, 0, 0, 0) for name in ["__au_runtime_console_next", "__au_runtime_display_pixel"]
        ]
        bindings = "\n".join(
            f"""1: 000000 1 FUNC {
                "GLOBAL HIDDEN"
                if name in {graphical.BRIDGE, graphical.VALUE_BRIDGE}
                else "GLOBAL DEFAULT"
                if name in REFLECTION
                else "LOCAL DEFAULT"
            } 1 {name}"""
            for name in sorted(names)
        )

        def verify(functions=names, symbols=imports, table=bindings):
            with patch.object(graphical.subprocess, "check_output", return_value=table):
                return graphical.verify_language_object(
                    SimpleNamespace(functions=functions, symbols=symbols, path=Path("fixture.o"))
                )

        verify()
        for changed in [
            imports[:-1],
            imports + [decoder.Symbol("__au_runtime_console_put", 0, 0, 0, 0)],
            imports + [decoder.Symbol("unknown", 0, 0, 0, 0)],
        ]:
            with self.assertRaisesRegex(ValueError, "import inventory"):
                verify(symbols=changed)
        for extra in ["__au_v_m1_22kernel_display_service_n0__d15display_service", "unexpected_host"]:
            with self.assertRaisesRegex(ValueError, "module/function"):
                verify(functions=names | {extra})
        for missing in sorted(names):
            with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, "module/function inventory"):
                verify(functions=names - {missing})
        for table, reason in [
            (bindings.replace("LOCAL DEFAULT", "GLOBAL DEFAULT"), "private ELF binding"),
            (bindings.replace("GLOBAL HIDDEN", "GLOBAL DEFAULT"), "private ELF binding"),
            (bindings + "\n" + bindings.splitlines()[0], "Duplicate"),
            ("\n".join(bindings.splitlines()[1:]), "binding inventory"),
        ]:
            with self.assertRaisesRegex(ValueError, reason):
                verify(table=table)

    @staticmethod
    def reflection_fixture(name="aurora_reflect_size"):
        # Independent exact byte forms, including wide comparison, zero fallback
        # and two constant return arms. Branch offsets target whole return arms.
        base = 64
        specifications = [
            ("cmp", "$0x1,%rdi", "4883ff01"),
            ("je", "5b <reflection+0x1b>", "0f8411000000"),
            ("cmp", "$0x2dc6c1,%rdi", "4881ffc1c62d00"),
            ("je", "63 <reflection+0x23>", "0f840c000000"),
            ("xor", "%rax,%rax", "4831c0"),
            ("ret", "", "c3"),
            ("mov", "$0x8,%rax", "48c7c008000000"),
            ("ret", "", "c3"),
            ("mov", "$0x0,%rax", "48c7c000000000"),
            ("ret", "", "c3"),
        ]
        payload, rows = bytearray(base), []
        for op, args, hexbytes in specifications:
            raw = bytes.fromhex(hexbytes)
            rows.append(decoder.Instruction(len(payload), len(raw), op, args))
            payload.extend(raw)
        symbol = decoder.Symbol(name, base, len(payload) - base, 1, 2)
        return symbol, rows, bytes(payload)

    def test_reflection_lookup_exact_leaf_bytes_and_closure(self):
        for name in (*REFLECTION, "__au_reflect_s3_size", "__au_reflect_s19_field_count"):
            symbol, rows, payload = self.reflection_fixture(name)
            result = graphical.verify_reflection_body(decoder, symbol, rows, payload)
            self.assertEqual((result["cases"], result["calls"], result["data_accesses"]), (2, 0, 0))
        # An internal fail-stop arm is also data-only; no branch may escape it.
        symbol, rows, payload = self.reflection_fixture()
        trap = decoder.Instruction(rows[8].address, 2, "ud2", "")
        changed = rows[:8] + [trap]
        stopped = payload[: trap.address] + bytes.fromhex("0f0b")
        symbol = decoder.Symbol(symbol.name, symbol.address, len(stopped) - symbol.address, 1, 2)
        graphical.verify_reflection_body(decoder, symbol, changed, stopped)

    def test_reflection_rejects_authority_memory_and_control_injection(self):
        symbol, baseline, payload = self.reflection_fixture()
        graphical.verify_reflection_body(decoder, symbol, baseline, payload)
        changes = [
            (0, "cmp", "$0x1,(%rdi)"),
            (0, "cmp", "$0x1,%rsi"),
            (0, "call", "100 <__au_runtime_display_pixel>"),
            (0, "syscall", ""),
            (1, "jne", baseline[1].args),
            (4, "xor", "%rdi,%rdi"),
            (4, "xor", "%rax,(%rdi)"),
            (6, "mov", "(%rdi),%rax"),
            (6, "mov", "$0x8,(%rdi)"),
            (6, "lea", "(%rip),%rax"),
            (6, "mov", "$0x8,%rdi"),
            (6, "call", "100 <__au_runtime_console_next>"),
            (6, "jmp", "100 <foreign>"),
            (7, "ret", "$0x8"),
            (7, "push", "%rax"),
            (8, "mov", "$0x80000000,%rax"),
        ]
        for index, op, args in changes:
            rows = list(baseline)
            old = rows[index]
            rows[index] = decoder.Instruction(old.address, old.size, op, args)
            with self.subTest(index=index, op=op, args=args), self.assertRaises(ValueError):
                graphical.verify_reflection_body(decoder, symbol, rows, payload)
        for index in (0, 1, 4, 6, 7):
            raw = bytearray(payload)
            raw[baseline[index].address] ^= 1
            with self.subTest(byte_index=index), self.assertRaises(ValueError):
                graphical.verify_reflection_body(decoder, symbol, baseline, bytes(raw))
        # Coherent byte+decoded mutations, so rejection cannot rely on disagreement.
        for target in (
            0,
            baseline[1].address,
            baseline[0].address,
            baseline[7].address,
            baseline[8].address,
            len(payload) + 16,
        ):
            rows = list(baseline)
            old = rows[1]
            rows[1] = decoder.Instruction(old.address, old.size, "je", f"{target:x} <mutated>")
            raw = bytearray(payload)
            raw[old.address + 2 : old.address + 6] = (target - old.address - old.size).to_bytes(
                4, "little", signed=True
            )
            with self.subTest(target=target), self.assertRaises(ValueError):
                graphical.verify_reflection_body(decoder, symbol, rows, bytes(raw))
        for rows in (baseline[:-1], baseline[1:], baseline + [baseline[-1]]):
            with self.assertRaises(ValueError):
                graphical.verify_reflection_body(decoder, symbol, rows, payload)
        for name in ("aurora_reflect_extra", "__au_reflect_s0_size", "__au_reflect_s01_size", "__au_reflect_s3_put"):
            foreign = decoder.Symbol(name, symbol.address, symbol.size, 1, 2)
            with self.subTest(name=name), self.assertRaises(ValueError):
                graphical.verify_reflection_body(decoder, foreign, baseline, payload)

    def test_reflection_helper_exact_inventory_and_binding(self):
        self.assertEqual(graphical.REFLECTION_HELPERS, frozenset(REFLECTION))
        names = graphical.expected_language_functions()
        imports = [
            decoder.Symbol(name, 0, 0, 0, 0) for name in ("__au_runtime_console_next", "__au_runtime_display_pixel")
        ]

        def binding(name):
            return (
                "GLOBAL HIDDEN"
                if name in (graphical.BRIDGE, graphical.VALUE_BRIDGE)
                else ("GLOBAL DEFAULT" if name in REFLECTION else "LOCAL DEFAULT")
            )

        table = "\n".join(f"""1: 000000 1 FUNC {binding(name)} 1 {name}""" for name in sorted(names))

        def verify(rows=table, functions=names, symbols=imports):
            with patch.object(graphical.subprocess, "check_output", return_value=rows):
                return graphical.verify_language_object(
                    SimpleNamespace(functions=functions, symbols=symbols, path=Path("fixture.o"))
                )

        verify()
        for name in REFLECTION:
            for changed in ("GLOBAL HIDDEN", "LOCAL DEFAULT", "WEAK DEFAULT"):
                mutant = table.replace(f"GLOBAL DEFAULT 1 {name}", f"{changed} 1 {name}")
                with self.assertRaises(ValueError):
                    verify(rows=mutant)
            with self.assertRaises(ValueError):
                verify(symbols=imports + [decoder.Symbol(name, 0, 0, 0, 0)])
            with self.assertRaises(ValueError):
                verify(functions=names - {name})
        for extra in ("aurora_reflect_address", "__au_reflect_s7_size", "__au_reflect_s1_address"):
            with self.assertRaises(ValueError):
                verify(functions=names | {extra})

    def test_provisional_six_qword_pixel_and_value_bridge_machine_contract(self):
        # Entry stack touch follows retained consumer.s; linked disassembly and
        # the remaining synthetic ABI fixture still require allocated execution.
        entry = [
            ("push", "%rbp"),
            ("mov", "%rsp,%rbp"),
            ("sub", "$0x80,%rsp"),
            ("orq", "$0x0,(%rsp)"),
            ("mov", "%r11,-0x8(%rbp)"),
        ]
        read_indexes, write_indexes = [], []
        destinations = iter([0x18, 0x10, 0x28, 0x20, 0x30, 0x38])
        for group in [(0, 8), (16, 24), (32,), (40,)]:
            entry.append(("mov", "-0x8(%rbp),%r11"))
            for offset in group:
                read_indexes.append(len(entry))
                write_indexes.append(len(entry) + 1)
                entry += [
                    ("mov", ("" if offset == 0 else hex(offset)) + "(%r11),%rax"),
                    ("mov", f"%rax,-0x{next(destinations):x}(%rbp)"),
                ]
        pixel_name = "__au_v_m1_24kernel_graphical_console_pixel_fixture"
        pixel_base = 3
        pixel = [("push", "%rbp"), ("mov", "%rsp,%rbp"), ("sub", "$0x80,%rsp")]
        pixel += [("mov", "-0x40(%rbp),%rdi"), ("mov", "-0x38(%rbp),%rsi")]
        pixel += [("pop", r) for r in ["%r10", "%r9", "%r8", "%rcx", "%rdx"]]
        pixel += [
            ("sub", "$0x8,%rsp"),
            ("mov", "%r10,(%rsp)"),
            ("call", "@__au_runtime_display_pixel"),
            ("add", "$0x8,%rsp"),
            ("cmp", "$0x1,%rax"),
            ("ja", "@" + pixel_name + "+18"),
            ("leave", ""),
            ("ret", ""),
            ("ud2", ""),
        ]
        graph = {
            graphical.ENTRY: entry,
            graphical.VALUE_BRIDGE: [("jmp", "@" + graphical.VALUE_ENTRY)],
            graphical.VALUE_ENTRY: [("ret", "")],
            pixel_name: pixel,
            "__au_runtime_display_pixel": [("ret", "")],
        }

        def verify(rows, live_bytes=16):
            _, symbols, code, starts = fixture(rows, analyze=False)
            functions = {
                name: {
                    "calls": [
                        {"address": row.address, "live_bytes": live_bytes}
                        for row in code.values()
                        if symbol.address <= row.address < symbol.address + symbol.size and row.op == "call"
                    ]
                }
                for name, symbol in symbols.items()
            }
            return graphical.verify_private_abi(
                decoder,
                SimpleNamespace(functions=symbols),
                code,
                starts,
                {graphical.ENTRY, graphical.VALUE_BRIDGE, graphical.VALUE_ENTRY, pixel_name},
                functions,
            )

        verify(graph)
        # Missing, altered-width/opcode/value/address and displaced touches
        # must fail at the exact prologue boundary, not be skipped generically.
        changed = deepcopy(graph)
        del changed[graphical.ENTRY][3]
        with self.assertRaisesRegex(ValueError, "paired entry stack touch"):
            verify(changed)
        for operation in [
            ("nop", ""),
            ("orl", "$0x0,(%rsp)"),
            ("orq", "$0x1,(%rsp)"),
            ("orq", "$0x0,0x8(%rsp)"),
            ("orq", "$0x0,-0x8(%rsp)"),
            ("orq", "$0x0,(%rbp)"),
            ("orq", "$0x0,%rsp"),
        ]:
            changed = deepcopy(graph)
            changed[graphical.ENTRY][3] = operation
            with self.subTest(stack_touch=operation), self.assertRaisesRegex(ValueError, "paired entry stack touch"):
                verify(changed)
        changed = deepcopy(graph)
        changed[graphical.ENTRY][3:5] = list(reversed(changed[graphical.ENTRY][3:5]))
        with self.assertRaisesRegex(ValueError, "paired entry stack touch"):
            verify(changed)
        changed = deepcopy(graph)
        changed[graphical.ENTRY].insert(4, ("orq", "$0x0,(%rsp)"))
        with self.assertRaisesRegex(ValueError, "private record save"):
            verify(changed)
        for operation in [("call", "@" + graphical.VALUE_ENTRY), ("jmp", "@" + graphical.ENTRY), ("jmp", "*%rax")]:
            changed = deepcopy(graph)
            changed[graphical.VALUE_BRIDGE] = [operation]
            with self.assertRaisesRegex(ValueError, "value-only private bridge|direct"):
                verify(changed)
        changed = deepcopy(graph)
        changed[graphical.VALUE_BRIDGE].append(("ret", ""))
        with self.assertRaisesRegex(ValueError, "value-only private bridge"):
            verify(changed)
        for index in read_indexes:
            changed = deepcopy(graph)
            changed[graphical.ENTRY][index] = ("mov", "(%r11),%eax")
            with self.assertRaisesRegex(ValueError, "qword/width/order"):
                verify(changed)
        for index in write_indexes:
            changed = deepcopy(graph)
            changed[graphical.ENTRY][index] = ("mov", "%rax,-0x8(%rbp)")
            with self.assertRaisesRegex(ValueError, "parameter slot"):
                verify(changed)
        for destination in ["-0x9", "-0x11", "-0x88", "-0x0"]:
            changed = deepcopy(graph)
            changed[graphical.ENTRY][write_indexes[0]] = ("mov", f"%rax,{destination}(%rbp)")
            with self.assertRaisesRegex(ValueError, "Overlapping, unaligned or unallocated"):
                verify(changed)
        changed = deepcopy(graph)
        changed[pixel_name][pixel_base + 7] = ("sub", "$0x10,%rsp")
        changed[pixel_name][pixel_base + 10] = ("add", "$0x10,%rsp")
        with self.assertRaisesRegex(ValueError, "Misaligned pixel SysV"):
            verify(changed, live_bytes=24)
        for grant, generation in [("-0x41", "-0x39"), ("-0x88", "-0x80")]:
            changed = deepcopy(graph)
            changed[pixel_name][pixel_base] = ("mov", grant + "(%rbp),%rdi")
            changed[pixel_name][pixel_base + 1] = ("mov", generation + "(%rbp),%rsi")
            with self.assertRaisesRegex(ValueError, "unaligned or outside helper frame"):
                verify(changed)
        for index, replacement in [(11, ("cmp", "$0x2,%rax")), (12, ("ja", "@" + pixel_name + "+17"))]:
            changed = deepcopy(graph)
            changed[pixel_name][pixel_base + index] = replacement
            with self.assertRaisesRegex(ValueError, "completion validation"):
                verify(changed)
        for index, replacement, reason in [
            (1, ("mov", "-0x40(%rbp),%rsi"), "grant/generation"),
            (2, ("pop", "%rax"), "scalar ABI"),
            (8, ("mov", "%rax,(%rsp)"), "seventh argument"),
            (10, ("add", "$0x10,%rsp"), "seventh argument"),
        ]:
            changed = deepcopy(graph)
            changed[pixel_name][pixel_base + index] = replacement
            with self.assertRaisesRegex(ValueError, reason):
                verify(changed)

    def test_object_bytes_size_and_relocation_inventory(self):
        symbol = decoder.Symbol("leaf", 0, 5, 1, 2)
        linked = SimpleNamespace(functions={"leaf": symbol}, function_bytes=lambda _: b"\xe8\x11\x22\x33\x44")
        obj = SimpleNamespace(relocations=[(1, 1, 2, 0, 0)], function_bytes=lambda _: b"\xe8\x00\x00\x00\x00")
        decoder.associate_object(linked, obj, symbol)
        for relocation in [(1, 1, 1, 0, 0), (1, 2, 2, 0, 0), (2, 1, 2, 0, 0)]:
            with self.assertRaises(ValueError):
                decoder.associate_object(
                    linked, SimpleNamespace(relocations=[relocation], function_bytes=obj.function_bytes), symbol
                )
        with self.assertRaises(ValueError):
            decoder.associate_object(
                linked,
                SimpleNamespace(relocations=obj.relocations, function_bytes=lambda _: b"\xe9\x00\x00\x00\x00"),
                symbol,
            )
        with self.assertRaises(ValueError):
            decoder.associate_object(linked, obj, decoder.Symbol("leaf", 0, 4, 1, 2))

    def test_unreviewed_graph_cycles_are_never_bounded_by_accident(self):
        for graph in [
            {"root": [("call", "@root"), ("ret", "")]},
            {"root": [("call", "@leaf"), ("ret", "")], "leaf": [("call", "@root"), ("ret", "")]},
            {"root": [("call", "@leaf"), ("ret", "")], "leaf": [("jmp", "@root")]},
            {
                "root": [("call", "@" + "walker"), ("ret", "")],
                "walker": [("call", "@helper"), ("ret", "")],
                "helper": [("call", "@root"), ("ret", "")],
            },
            {"root": [("ret", "")], "unused": [("call", "@unused"), ("ret", "")]},
        ]:
            functions, *_ = fixture(graph)
            with self.assertRaises(ValueError):
                for name in functions:
                    graphical.common.graph_peak(functions, {}, name)

    def test_fixed_frame_loop_and_stack_growth(self):
        functions, *_ = fixture({"fixed": [("test", "%eax,%eax"), ("jne", "@fixed"), ("ret", "")]})
        self.assertEqual(graphical.common.graph_peak(functions, {}, "fixed")["peak"], 8)
        with self.assertRaisesRegex(ValueError, "Inconsistent or unbounded stack"):
            fixture({"growing": [("sub", "$0x8,%rsp"), ("jmp", "@growing")]})

    def test_explicit_failures_survive_optimization(self):
        with self.assertRaises(ValueError):
            graphical.need(False, "independent explicit denial")
        with self.assertRaises(ValueError):
            decoder.require(False, "independent explicit decoder denial")

    def test_bridge_target_and_record_forwarding_are_exact(self):
        ops = [
            ("push", "%rbp"),
            ("mov", "%rsp,%rbp"),
            ("mov", "%rdi,%r11"),
            ("call", "100 <entry>"),
            ("leave", ""),
            ("ret", ""),
        ]
        starts = {256: "__au_v_m1_24kernel_graphical_console_n0__d17graphical_console"}
        graphical.verify_bridge_body(decoder, body(ops), starts)
        for index, replacement in [
            (0, ("push", "%rbx")),
            (1, ("mov", "%rsp,%rbx")),
            (2, ("mov", "%rsi,%r11")),
            (2, ("mov", "%edi,%r11d")),
            (2, ("mov", "%rdi,%r10")),
            (3, ("call", "*%r11")),
            (3, ("jmp", "100 <entry>")),
            (3, ("call", "101 <interior>")),
            (4, ("nop", "")),
            (5, ("ret", "$0x8")),
        ]:
            changed = list(ops)
            changed[index] = replacement
            with self.subTest(index=index, replacement=replacement), self.assertRaises(ValueError):
                graphical.verify_bridge_body(decoder, body(changed), starts)
        for name in ["__au_v_m1_22kernel_display_service_n0__d15display_service", "__au_runtime_console_entry"]:
            with self.assertRaises(ValueError):
                graphical.verify_bridge_body(decoder, body(ops), {256: name})
        for changed in [ops[:-1], ops + [("nop", "")]]:
            with self.assertRaises(ValueError):
                graphical.verify_bridge_body(decoder, body(changed), starts)

    def test_irq_every_save_restore_and_dispatch(self):
        registers = "rax rbx rcx rdx rbp rsi rdi r8 r9 r10 r11 r12 r13 r14 r15".split()
        ops = [("push", "$0x0"), ("push", "$0x40"), ("cld", "")]
        ops += [("push", "%" + r) for r in registers]
        ops += [
            ("mov", "%rsp,%rdi"),
            ("mov", "%rsp,%rbx"),
            ("and", "$0xfffffffffffffff0,%rsp"),
            ("call", "100 <dispatch>"),
            ("mov", "%rbx,%rsp"),
        ]
        ops += [("pop", "%" + r) for r in reversed(registers)] + [("add", "$0x10,%rsp"), ("iretq", "")]
        starts = {256: "uefi_console_interrupt_dispatch"}
        graphical.verify_irq_body(decoder, body(ops), starts)
        for index in range(len(ops)):
            changed = list(ops)
            changed[index] = ("nop", "")
            with self.subTest(index=index), self.assertRaises(ValueError):
                graphical.verify_irq_body(decoder, body(changed), starts)
        for index, replacement in [
            (20, ("and", "$0xffffffffffffffe0,%rsp")),
            (21, ("call", "*%rax")),
            (22, ("mov", "%rax,%rsp")),
        ]:
            changed = list(ops)
            changed[index] = replacement
            with self.assertRaises(ValueError):
                graphical.verify_irq_body(decoder, body(changed), starts)

    def test_irq_excludes_language_and_service_on_every_branch(self):
        graph = {
            "uefi_console_interrupt_dispatch": {"calls": [{"target": "large"}, {"target": "small"}]},
            "large": {"calls": []},
            "small": {"calls": []},
        }
        graphical.verify_irq_reachability(graph, set())
        for target in [
            graphical.ENTRY,
            "__au_v_any",
            "__au_runtime_console_put",
            "__au_runtime_display_put",
            "generated_leaf",
        ]:
            changed = deepcopy(graph)
            changed["small"]["calls"] = [{"target": target}]
            changed[target] = {"calls": []}
            with self.subTest(target=target), self.assertRaises(ValueError):
                graphical.verify_irq_reachability(changed, {"generated_leaf", graphical.ENTRY})

    def test_unchanged_stack_and_separate_reserves(self):
        # Independently selected exact boundaries: 15360 total, 4096 IRQ/fault.
        for values in [(15000, 11000, 3736, 360), (15201, 720, 639, 159), (1, 12304, 2048, 1008), (1, 1, 4000, 96)]:
            graphical.verify_stack_budgets(*values)
        for values in [
            (15001, 11000, 3736, 360),
            (1, 11265, 3736, 360),
            (1, 1, 3737, 360),
            (1, 12305, 2048, 1008),
            (-1, 1, 1, 1),
            (True, 1, 1, 1),
            (1, False, 1, 1),
            (1, 1, -1, 1),
            (1, 1, 1, -1),
            (1, 1, 1, 1.0),
        ]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                graphical.verify_stack_budgets(*values)

    def test_generated_and_assembly_stack_forms_still_fail_closed(self):
        for op, args in [
            ("push", "(%rsp)"),
            ("push", "0x10(%rip)"),
            ("push", "(%rsp,%rax,8)"),
            ("sub", "$0xfffffffffffffff0,%rsp"),
            ("mov", "%rax,%rsp"),
            ("ret", "$0x8"),
            ("enter", "$0x10,$0x0"),
            ("opaque_new_opcode", ""),
        ]:
            row = decoder.Instruction(0, 1, op, args)
            with self.subTest(op=op, args=args), self.assertRaises(ValueError):
                decoder.analyze_function(
                    decoder.Symbol("sample", 0, 2, 1, 2),
                    {0: row, 1: decoder.Instruction(1, 1, "ret", "")},
                    {0: "sample"},
                )

    def test_wait_exact_bytes_decode_single_owner_and_single_sti(self):
        start = 10
        code = {start + i: decoder.Instruction(start + i, 1, op, "") for i, op in enumerate(["sti", "hlt", "cli"])}
        named = {
            "uefi_console_poll_begin": decoder.Symbol("begin", 10, 0, 1, 0),
            "uefi_console_poll_end": decoder.Symbol("end", 13, 0, 1, 0),
        }
        graph = {"uefi_console_interrupt_dispatch": {"calls": []}}
        owners = {"trusted_wait_for_sample": decoder.Symbol("trusted_wait_for_sample", 9, 5, 1, 2)}
        payload = b"\x90" * 10 + b"\xfb\xf4\xfa" + b"\x90"

        def verify(c=code, n=named, g=graph, p=payload, o=owners):
            return graphical.verify_wait_closure(c, n, g, set(), p, o)

        verify()
        for raw in [b"\xfa\xf4\xfb", b"\xfb\x90\xfa", b"\xfb\xf4\x90", b"\xfb\xf4"]:
            with self.assertRaises(ValueError):
                verify(p=b"\x90" * 10 + raw)
        for index in code:
            changed = dict(code)
            changed[index] = decoder.Instruction(index, 1, "nop", "")
            with self.assertRaises(ValueError):
                verify(c=changed)
            changed = dict(code)
            changed[index] = decoder.Instruction(index, 2, code[index].op, "")
            with self.assertRaises(ValueError):
                verify(c=changed)
        changed = dict(code)
        changed[1] = decoder.Instruction(1, 1, "sti", "")
        with self.assertRaises(ValueError):
            verify(c=changed)
        for changed in [
            {},
            {"wrong_owner": decoder.Symbol("wrong_owner", 9, 5, 1, 2)},
            dict(owners, second_wait_for_sample=decoder.Symbol("second_wait_for_sample", 9, 5, 1, 2)),
        ]:
            with self.assertRaises(ValueError):
                verify(o=changed)
        changed = deepcopy(named)
        changed["uefi_console_poll_end"] = decoder.Symbol("end", 14, 0, 1, 0)
        with self.assertRaises(ValueError):
            verify(n=changed)

    def test_each_wait_path_retains_paired_service_not_just_maximum(self):
        path = ["uefi_payload_entry", graphical.BRIDGE, graphical.ENTRY, "__au_runtime_console_next", "wait_for_sample"]
        graph = {
            name: {"calls": [{"target": path[index + 1]}] if index + 1 < len(path) else []}
            for index, name in enumerate(path)
        }
        graphical.verify_retained_wait_paths(graph, path[-1])
        for source, target in [(0, 2), (1, 3), (2, 4), (0, 4)]:
            changed = deepcopy(graph)
            changed[path[source]]["calls"].append({"target": path[target]})
            with self.subTest(source=source, target=target), self.assertRaisesRegex(ValueError, "bypasses retained"):
                graphical.verify_retained_wait_paths(changed, path[-1])

    def test_inventory_has_no_missing_unframed_or_extra_authority(self):
        fixed = {
            "uefi_payload_entry",
            "uefi_payload_fault",
            "uefi_payload_page_fault",
            "fault_common",
            "uefi_console_interrupt",
        }
        language = {
            graphical.ENTRY,
            graphical.BRIDGE,
            graphical.VALUE_BRIDGE,
            "generated_helper",
            *REFLECTION,
        }
        frames = {"trusted_cpp", "__au_runtime_console_next", "__au_runtime_console_put", "__au_runtime_display_pixel"}
        memory = {"memcpy", "memset"}
        linked = fixed | language | frames | memory
        graphical.verify_inventory(linked, frames, language, memory)
        for missing in sorted(linked):
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                graphical.verify_inventory(linked - {missing}, frames, language, memory)
        with self.assertRaises(ValueError):
            graphical.verify_inventory(linked | {"unframed"}, frames, language, memory)
        for extra in [
            "__au_runtime_display_clear",
            "uefi_runtime_unexpected",
            "aurora_user_fixture",
            "aurora_kernel_budget_fixture",
        ]:
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                graphical.verify_inventory(linked | {extra}, frames | {extra}, language, memory)
        for name in [graphical.ENTRY, graphical.BRIDGE, *REFLECTION]:
            with self.assertRaises(ValueError):
                graphical.verify_inventory(linked, frames | {name}, language - {name}, memory)
        self.assertEqual(graphical.CPP_OBJECTS, ("payload", "acpi", "pci", "runtime", "graphical-console"))
        self.assertEqual(graphical.ASSEMBLY_OBJECTS, ("payload-entry", "console-entry", "language", "memory"))

    def test_begin_invalidates_before_fallible_checks(self):
        with tempfile.TemporaryDirectory(prefix="graphical-invalidation-") as directory:
            root = Path(directory)
            names = [
                "graphical-console-admission.json",
                "graphical-console-build.json",
                "graphical-console-build-start.json",
            ]
            sentinel = root / "payload.elf"
            sentinel.write_bytes(b"preserved prior image")

            def stale():
                for name in names:
                    (root / name).write_text("previous metadata")

            with patch.object(graphical, "BUILD", root), patch.object(graphical, "RECEIPT", root / names[0]):
                stale()
                with self.assertRaisesRegex(ValueError, "Missing exact graphical build controls"):
                    graphical.begin("graphical-console", "compiler", "cxx", [])
                self.assertTrue(all(not (root / name).exists() for name in names))
                stale()
                with (
                    patch.object(graphical, "source_files", return_value=[]),
                    patch.object(graphical.common, "hashes", return_value={}),
                    patch.object(graphical.common, "executable", side_effect=RuntimeError("tool unavailable")),
                ):
                    with self.assertRaisesRegex(RuntimeError, "tool unavailable"):
                        graphical.begin(
                            "graphical-console", "compiler", "cxx", graphical.expected_flags("graphical-console")
                        )
                self.assertTrue(all(not (root / name).exists() for name in names))
                stale()
                with (
                    patch.object(Path, "unlink", side_effect=PermissionError("read-only metadata")),
                    patch.object(graphical.common, "executable") as executable,
                ):
                    with self.assertRaisesRegex(PermissionError, "read-only metadata"):
                        graphical.begin(
                            "graphical-console", "compiler", "cxx", graphical.expected_flags("graphical-console")
                        )
                    executable.assert_not_called()
                self.assertEqual(sentinel.read_bytes(), b"preserved prior image")

    def test_mode_flags_sources_artifacts_and_review_identity(self):
        with tempfile.TemporaryDirectory(prefix="graphical-controls-") as directory:
            root = Path(directory)
            paths = {name: root / name for name in ["source", "compiler", "cxx", "payload.bin", "tool", "pe_linker"]}
            for name, path in paths.items():
                path.write_text("original " + name)

            def hashes(items):
                return {str(path.relative_to(root)): graphical.digest(path) for path in items}

            record = dict(
                schema="aurora-graphical-console-build-v1",
                mode="graphical-console",
                flags=graphical.expected_flags("graphical-console"),
                translation_unit_flags=deepcopy(graphical.TU_FLAGS),
                objects=["payload.bin"],
                source_sha256=hashes([paths["source"]]),
                compiler=dict(path=str(paths["compiler"]), sha256=graphical.digest(paths["compiler"])),
                cxx=dict(path=str(paths["cxx"]), sha256=graphical.digest(paths["cxx"])),
                tools={
                    name: dict(path=str(paths["tool"]), sha256=graphical.digest(paths["tool"]))
                    for name in graphical.TOOLS
                },
                pe_linker=dict(path=str(paths["pe_linker"]), sha256=graphical.digest(paths["pe_linker"])),
                output_sha256=hashes([paths["payload.bin"]]),
            )
            # The actual shared-session header changes in an isolated source tree.
            # Reintroducing the old five-file token gate must reject this control.
            for name in (
                "kernel/graphical-session.hpp",
                "kernel/console-session.hpp",
                "kernel/display-session.hpp",
                "kernel/uefi/graphical-console.cpp",
                "kernel/uefi/graphical-capture-policy.hpp",
            ):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / name).read_bytes())
            for name in ("scripts", "tests"):
                (root / name).symlink_to(ROOT / name, target_is_directory=True)
            paths["source"] = root / "kernel/graphical-session.hpp"
            record["source_sha256"] = hashes([paths["source"]])
            build = root / "graphical-console-build.json"
            build.write_text(json.dumps(record))
            receipt = root / "graphical-console-admission.json"
            data = dict(
                schema="aurora-graphical-console-admission-v6",
                mode="graphical-console",
                status="requires-independent-review",
                clock="tcg-original-clock",
                build=record,
                image={"independent_image_result": 1},
                stack={"independent_stack_result": 456},
                sha256=hashes([paths["source"], paths["payload.bin"], build]),
            )
            receipt.write_text(json.dumps(data))
            real_image_evidence = graphical.image_evidence
            with (
                patch.object(graphical, "ROOT", root),
                patch.object(graphical, "BUILD", root),
                patch.object(graphical, "RECEIPT", receipt),
                patch.object(graphical, "build_files", return_value=[paths["payload.bin"]]),
                patch.object(graphical, "source_files", return_value=[paths["source"]]),
                patch.object(graphical.common, "hashes", side_effect=hashes),
                patch.object(graphical.common, "executable", side_effect=lambda name: record["tools"][name]),
                patch.object(graphical, "image_evidence", return_value={"independent_image_result": 1}),
                patch.object(graphical, "stack_evidence", return_value={"independent_stack_result": 456}),
                patch.dict(os.environ, {"GRAPHICAL_CONSOLE_REVIEW_SHA256": graphical.digest(receipt)}),
            ):
                graphical.verify_inputs(record, "graphical-console")
                graphical.checked("graphical-console")
                graphical.reviewed("graphical-console")
                for key in ["source", "compiler", "cxx", "payload.bin", "tool", "pe_linker"]:
                    path = paths[key]
                    saved = path.read_bytes()
                    path.write_bytes(saved + b" drift")
                    with self.subTest(drift=key), self.assertRaises(ValueError):
                        graphical.checked("graphical-console")
                    path.write_bytes(saved)
                for mode in ["graphical-console-capture", "console", "framebuffer", "graphical-console-stale"]:
                    with self.assertRaises(ValueError):
                        graphical.checked(mode)
                for flag in [
                    "-DAURORA_UEFI_CONSOLE",
                    "-DAURORA_UEFI_FRAMEBUFFER",
                    "-DAURORA_UEFI_GRAPHICAL_CAPTURE",
                    "-O0",
                    "-DUNKNOWN",
                ]:
                    changed = deepcopy(record)
                    changed["flags"].append(flag)
                    with self.subTest(flag=flag), self.assertRaises(ValueError):
                        graphical.verify_inputs(changed, "graphical-console")
                for mutate in [
                    lambda r: r["flags"].pop(),
                    lambda r: r["flags"].reverse(),
                    lambda r: r["objects"].append("console.o"),
                    lambda r: r["translation_unit_flags"].update(runtime=[]),
                    lambda r: r.update(schema="aurora-framebuffer-build-v1"),
                ]:
                    changed = deepcopy(record)
                    mutate(changed)
                    with self.assertRaises(ValueError):
                        graphical.verify_inputs(changed, "graphical-console")
                for pin in ["", "0" * 64, "A" * 64, graphical.digest(receipt)[:-1]]:
                    with (
                        patch.dict(os.environ, {"GRAPHICAL_CONSOLE_REVIEW_SHA256": pin}),
                        self.assertRaises(ValueError),
                    ):
                        graphical.reviewed("graphical-console")
                for version in (1, 2, 3, 4, 5):
                    old = dict(data, schema=f"aurora-graphical-console-admission-v{version}")
                    receipt.write_text(json.dumps(old))
                    with patch.dict(os.environ, {"GRAPHICAL_CONSOLE_REVIEW_SHA256": graphical.digest(receipt)}):
                        for check in (graphical.checked, graphical.reviewed):
                            with self.subTest(version=version, check=check.__name__):
                                with self.assertRaisesRegex(ValueError, "Unexpected graphical receipt"):
                                    check("graphical-console")
                receipt.write_text(json.dumps(data))
                # A caller cannot relabel automatic evidence as independent acceptance.
                changed = deepcopy(data)
                changed["status"] = "accepted"
                receipt.write_text(json.dumps(changed))
                with self.assertRaises(ValueError):
                    graphical.checked("graphical-console")
                receipt.write_text(json.dumps(data))
                for key in list(data):
                    changed = deepcopy(data)
                    del changed[key]
                    receipt.write_text(json.dumps(changed))
                    with self.subTest(missing_receipt_key=key), self.assertRaises(ValueError):
                        graphical.checked("graphical-console")
                for key, value in [
                    ("schema", "aurora-graphical-console-admission-v1"),
                    ("image", {}),
                    ("stack", {}),
                    ("image", {"independent_image_result": True}),
                    ("stack", {"independent_stack_result": 0}),
                    ("extra", True),
                ]:
                    changed = deepcopy(data)
                    changed[key] = value
                    receipt.write_text(json.dumps(changed))
                    with self.subTest(forged_receipt_key=key, value=value), self.assertRaises(ValueError):
                        graphical.checked("graphical-console")
                for raw in [
                    '{"mode":"graphical-console","mode":"graphical-console"}',
                    '{"nested":{"same":1,"same":1}}',
                    '{"number":NaN}',
                    '{"number":Infinity}',
                ]:
                    receipt.write_text(raw)
                    with self.assertRaises(ValueError):
                        graphical.read_json(receipt)
                receipt.write_text(json.dumps(data))
                build.write_text(json.dumps(dict(record, objects=["payload.bin", "console.o"])))
                with self.assertRaises(ValueError):
                    graphical.checked("graphical-console")
                build.write_text(json.dumps(record))
                original = paths["source"].read_text()
                changed = original.replace(
                    "if (active_ || incoming != &trusted)", "if (!incoming || active_ || incoming != &trusted)"
                )
                self.assertNotEqual(changed, original, "Exercise a real shared-session implementation edit")
                paths["source"].write_text(changed)
                with self.assertRaisesRegex(ValueError, "Graphical source changed since begin"):
                    graphical.provenance("graphical-console")
                # Re-enter the real image reader after fresh provenance. Invalid ELF
                # must fail there, not at a source-token gate; no compiler/guest runs.
                (root / "payload.elf").write_bytes(b"invalid ELF")
                pe = root / "esp/EFI/BOOT/BOOTX64.EFI"
                pe.parent.mkdir(parents=True)
                pe.write_bytes(b"invalid PE")
                for mode in ("graphical-console", "graphical-console-capture"):
                    fresh = dict(
                        record, mode=mode, flags=graphical.expected_flags(mode), source_sha256=hashes([paths["source"]])
                    )
                    build.write_text(json.dumps(fresh))
                    graphical.provenance(mode)
                    receipt.write_text(json.dumps(data))
                    with patch.object(graphical, "image_evidence", side_effect=real_image_evidence):
                        with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "Payload ELF architecture"):
                            graphical.emit(mode)
                    self.assertFalse(receipt.exists(), "Failed fresh image checks must remove stale PASS")


class CaptureAdmission(unittest.TestCase):
    capture = "graphical-console-capture"

    def test_capture_structure_gate_cannot_be_cleared_by_source_or_pin(self):
        graphical.require_capture_structure("graphical-console")
        with self.assertRaisesRegex(ValueError, "Missing current capture structure evidence"):
            graphical.require_capture_structure(self.capture)
        with tempfile.TemporaryDirectory(prefix="graphical-capture-pending-") as directory:
            receipt = Path(directory) / "admission.json"
            receipt.write_text("stale receipt")
            with (
                patch.object(graphical, "RECEIPT", receipt),
                patch.object(graphical, "provenance", return_value={}),
                patch.object(graphical, "image_evidence", return_value={"source": "accepted"}),
                patch.object(graphical, "stack_evidence", return_value={"normal": 1}),
                patch.dict(os.environ, {"GRAPHICAL_CONSOLE_REVIEW_SHA256": "0" * 64}),
            ):
                with self.assertRaisesRegex(ValueError, "Missing current capture structure evidence"):
                    graphical.emit(self.capture)
                self.assertFalse(receipt.exists(), "A source check cannot leave a capture admission receipt")
                data = dict(
                    schema="aurora-graphical-console-admission-v6",
                    mode=self.capture,
                    status="requires-independent-review",
                    clock="tcg-original-clock",
                    build={},
                    image={"source": "accepted"},
                    stack={"normal": 1},
                    sha256={},
                )
                receipt.write_text(json.dumps(data))
                with (
                    patch.object(graphical.common, "hashes", return_value={}),
                    patch.dict(os.environ, {"GRAPHICAL_CONSOLE_REVIEW_SHA256": graphical.digest(receipt)}),
                ):
                    for check in (graphical.checked, graphical.reviewed):
                        with (
                            self.subTest(check=check.__name__),
                            self.assertRaisesRegex(ValueError, "Missing current capture structure evidence"),
                        ):
                            check(self.capture)

    def test_unknown_emission_reports_original_bytes_and_unproved_effect(self):
        symbol = decoder.Symbol("unreviewed_capture_emission", 0, 5, 1, 2)
        rows = {
            0: decoder.Instruction(0, 4, "enter", "$0x20,$0"),
            4: decoder.Instruction(4, 1, "ret", ""),
        }
        with self.assertRaisesRegex(ValueError, "Unknown instruction semantics: enter") as rejected:
            decoder.analyze_function(symbol, rows, {0: symbol.name})
        report = graphical.unreviewed_linked_function(symbol, rows, b"\xc8\x20\0\0\xc3", rejected.exception)
        self.assertIn(symbol.name, report)
        self.assertIn("call/stack effect remains unproved", report)
        self.assertIn('"bytes":"c8200000"', report)
        self.assertIn('"operands":"$0x20,$0"', report)
        self.assertNotIn('"operation":"ret"', report)


class CaptureStructure(unittest.TestCase):
    """Hand-authored ELF symbol/section records, never compiled build snapshots."""

    @staticmethod
    def linked(base=0x2000, section_index=1, local=""):
        fields = (
            ("capture_scenario", 1),
            ("pixel_attempts", 8),
            ("consumer_entries", 8),
            ("sample_calls", 8),
            ("output_attempts", 8),
            ("completed_samples", 8),
            ("stores", 8),
            ("wakes", 8),
            ("active_operation", 4),
        )
        symbols = [
            decoder.Symbol(
                f"_ZN6aurora4uefi12_GLOBAL__N_1{local}{len(name)}{name}E", base + index * 8, size, section_index, 1
            )
            for index, (name, size) in enumerate(fields)
        ]
        # Authority identities/sizes are written independently of the checker.
        authorities = (
            (
                "_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE6grant_E",
                80,
                24,
            ),
            (
                "_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE11generation_E",
                104,
                8,
            ),
            (
                "_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE6grant_E",
                112,
                48,
            ),
            (
                "_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE11generation_E",
                160,
                8,
            ),
            (
                "_ZN6aurora9graphical5EntryINS_7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS5_15ServicePlatformEEENS_7display7SessionINS5_16DisplayTransportES7_EES7_E7active_E",
                168,
                1,
            ),
        )
        symbols += [decoder.Symbol(name, base + offset, size, section_index, 1) for name, offset, size in authorities]
        sections = [(0,) * 10] * section_index + [(0, 8, 3, base, 0, 256, 0, 0, 8, 0)]
        functions = {
            name: None
            for name in (
                "_ZN6aurora4uefi21run_graphical_consoleEmRKNS0_5BytesE",
                "__au_runtime_console_next",
                "__au_runtime_console_put",
                "__au_runtime_display_pixel",
            )
        }
        return SimpleNamespace(symbols=symbols, sections=sections, functions=functions)

    def test_relocated_storage_and_both_local_spellings(self):
        for base, section, local in ((0x2000, 1, ""), (0x9800, 3, "L")):
            evidence = graphical.capture_structure_evidence(self.linked(base, section, local))
            self.assertEqual(evidence["schema"], "aurora-graphical-capture-structure-v1")
            self.assertEqual(evidence["status"], "structure-only")
            self.assertEqual(evidence["behavior_qualification"], "pending-hosted-and-guest-gates")
            self.assertEqual(evidence["states"]["capture_scenario"]["address"], base)
            self.assertEqual(len(evidence["states"]), 14)
            graphical.require_capture_structure("graphical-console-capture", evidence)
            with self.assertRaises(ValueError):
                graphical.require_capture_structure("graphical-console", evidence)

    def test_missing_duplicate_and_crossed_state_owners(self):
        original = self.linked()
        for index in range(14):
            for change in ("missing", "duplicate", "other-spelling"):
                linked = deepcopy(original)
                if change == "missing":
                    del linked.symbols[index]
                elif change == "duplicate":
                    linked.symbols.append(linked.symbols[index])
                else:
                    linked.symbols.append(self.linked(local="L").symbols[index])
                with self.subTest(index=index, change=change), self.assertRaises(ValueError):
                    graphical.capture_structure_evidence(linked)

    def test_state_size_type_section_and_bounds(self):
        for field, value in (
            ("size", 4),
            ("kind", 2),
            ("section", 0),
            ("section", 2),
            ("address", 0x1FF8),
            ("address", 0x2100),
            ("address", 0x2009),
        ):
            linked = self.linked()
            row = linked.symbols[1]
            values = dict(name=row.name, address=row.address, size=row.size, section=row.section, kind=row.kind)
            values[field] = value
            linked.symbols[1] = decoder.Symbol(**values)
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                graphical.capture_structure_evidence(linked)
        for field, value in ((1, 1), (2, 0), (2, 2), (2, 6), (2, 7), (5, 32)):
            linked = self.linked()
            section = list(linked.sections[1])
            section[field] = value
            linked.sections[1] = tuple(section)
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                graphical.capture_structure_evidence(linked)

    def test_overlapping_state_and_missing_functions(self):
        linked = self.linked()
        row = linked.symbols[1]
        linked.symbols[1] = decoder.Symbol(row.name, 0x2000, row.size, row.section, row.kind)
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            graphical.capture_structure_evidence(linked)
        for name in self.linked().functions:
            linked = self.linked()
            del linked.functions[name]
            with self.subTest(function=name), self.assertRaises(ValueError):
                graphical.capture_structure_evidence(linked)

    def test_production_absence_and_orphan_capture_counter(self):
        linked = self.linked()
        linked.symbols = linked.symbols[2:]
        self.assertIsNone(graphical.capture_structure_evidence(linked))
        graphical.require_capture_structure("graphical-console")
        linked = self.linked()
        del linked.symbols[0]
        with self.assertRaisesRegex(ValueError, "without scenario"):
            graphical.capture_structure_evidence(linked)

    def test_incomplete_or_overclaimed_structure_evidence(self):
        evidence = graphical.capture_structure_evidence(self.linked())
        for key in evidence:
            changed = deepcopy(evidence)
            del changed[key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                graphical.require_capture_structure("graphical-console-capture", changed)
        for key, value in (
            ("schema", "aurora-graphical-capture-linked-gcc16-v1"),
            ("status", "machine-behavior-proved"),
            ("behavior_qualification", "passed"),
            ("states", {}),
        ):
            changed = deepcopy(evidence)
            changed[key] = value
            with self.subTest(field=key), self.assertRaises(ValueError):
                graphical.require_capture_structure("graphical-console-capture", changed)

    def test_all_console_profiles_use_shared_scalar_stack_rules(self):
        for profile in ("program", "service", "framebuffer", "graphical"):
            shared = graphical.load("shared_scalar_" + profile, ROOT / "tests/kernel-uefi-owned-bytes-stack.py")
            shared.configure_console(profile)
            self.assertTrue(shared.CONSOLE_SCALAR <= shared.NEUTRAL)
            self.assertTrue({"testb", "testl", "testw"} <= shared.READ_ONLY)
            symbol = shared.Symbol("pci_byte_flag", 0, 2, 1, 2)
            for op, args, accepted in (
                ("orb", "$0x1,(%rax)", True),
                ("orb", "$0x1,%spl", False),
                ("unknown_new_instruction", "", False),
            ):
                code = {0: shared.Instruction(0, 1, op, args), 1: shared.Instruction(1, 1, "ret", "")}
                with self.subTest(profile=profile, operation=op, operands=args):
                    if accepted:
                        self.assertEqual(shared.analyze_function(symbol, code, {0: symbol.name})["local_peak"], 8)
                    else:
                        with self.assertRaises(ValueError):
                            shared.analyze_function(symbol, code, {0: symbol.name})
            with self.assertRaises(ValueError):
                shared.configure_console("unknown")


if __name__ == "__main__":
    unittest.main()
