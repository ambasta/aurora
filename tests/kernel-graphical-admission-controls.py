#!/usr/bin/env python3
"""Independent hostile combined-profile controls. Source prepared, not qualified.

No compiler, guest or subprocess is launched. All safety assertions use explicit
exceptions or unittest assertions and remain active under python -O.
"""

from copy import deepcopy
import hashlib
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
decoder = graphical.load("graphical_controls_decoder", ROOT / "scripts/kernel_stack.py")


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
    def test_aurora_stack_facts_bind_symbols_edges_and_budget(self):
        with tempfile.TemporaryDirectory(prefix="aurora-facts-") as directory:
            path = Path(directory) / "language.stack.json"
            _, symbols, code, starts = fixture(
                {"root": [("call", "@leaf"), ("call", "@leaf"), ("ret", "")], "leaf": [("ret", "")]}, analyze=False
            )
            facts = {
                "version": 1,
                "functions": {
                    "root": {"local_bytes": 64, "calls": {"leaf": 48}},
                    "leaf": {"local_bytes": 32, "calls": {}},
                },
            }

            def check(value=facts, instructions=code, names=symbols):
                path.write_text(json.dumps(value))
                return decoder.aurora_stack_functions(path, symbols, instructions, starts, names)

            functions = check()
            self.assertEqual(graphical.common.graph_peak(functions, "root")["peak"], 80)
            self.assertEqual([row["live_bytes"] for row in functions["root"]["calls"]], [48, 48])
            # Source/local instructions are compiler-trusted; the consumer does
            # not bring back a second Aurora opcode interpreter.
            changed = dict(code)
            leaf = symbols["leaf"].address
            changed[leaf] = decoder.Instruction(leaf, 1, "compiler-local-op", "")
            self.assertEqual(check(instructions=changed)["leaf"]["local_peak"], 32)
            for mutate in (
                lambda r: r.update(version=True),
                lambda r: r.update(extra=1),
                lambda r: r["functions"].pop("leaf"),
                lambda r: r["functions"]["root"].update(extra=1),
                lambda r: r["functions"]["root"].update(local_bytes=7),
                lambda r: r["functions"]["root"].update(local_bytes=15361),
                lambda r: r["functions"]["root"].update(local_bytes=True),
                lambda r: r["functions"]["root"].update(calls={}),
                lambda r: r["functions"]["root"].update(calls={"missing": 8}),
                lambda r: r["functions"]["root"].update(calls={"leaf": 65}),
                lambda r: r["functions"]["leaf"].update(calls={"root": 8}),
            ):
                changed_facts = deepcopy(facts)
                mutate(changed_facts)
                with self.assertRaises(ValueError):
                    check(changed_facts)
            with self.assertRaises(ValueError):
                check(names={"root"})
            changed = dict(code)
            changed[0] = decoder.Instruction(0, 1, "call", "*%rax")
            with self.assertRaises(ValueError):
                check(instructions=changed)
            path.write_text('{"version":1,"version":1,"functions":{}}')
            with self.assertRaises(ValueError):
                decoder.aurora_stack_functions(path, symbols, code, starts, symbols)
            path.unlink()
            with self.assertRaises(OSError):
                decoder.aurora_stack_functions(path, symbols, code, starts, symbols)
            functions["leaf"]["calls"] = [dict(target="root", live_bytes=8, kind="call")]
            with self.assertRaises(ValueError):
                graphical.common.graph_peak(functions, "root")
            # The unchanged finite admission cap accepts equality and rejects +1.
            graphical.verify_stack_budgets(14848, 0, 0, 512)
            with self.assertRaises(ValueError):
                graphical.verify_stack_budgets(14849, 0, 0, 512)

    def test_service_facts_are_closed_and_match_concrete_edges(self):
        with tempfile.TemporaryDirectory(prefix="aurora-service-facts-") as directory:
            path = Path(directory) / "language.stack.json"
            _, symbols, code, starts = fixture(
                {
                    "entry": [("call", "@__au_runtime_display_pixel"), ("ret", "")],
                    "__au_runtime_display_pixel": [("ret", "")],
                },
                analyze=False,
            )
            abi = dict(
                record=dict(parameters=[["builtin::DisplaySession", 16]], result_bytes=8),
                calls={"__au_runtime_display_pixel": dict(sysv_arguments=7, result_max=1)},
            )
            fact = dict(local_bytes=64, calls={"__au_runtime_display_pixel": 32}, copied_record=None, service_abi=abi)
            document = dict(version=2, functions={"entry": fact})

            def check(value=document):
                path.write_text(json.dumps(value))
                return decoder.aurora_stack_functions(path, symbols, code, starts, {"entry"})["entry"]["service_abi"]

            self.assertEqual(check(), abi)
            for mutate in (
                lambda a: a.update(extra=1),
                lambda a: a.pop("record"),
                lambda a: a.pop("calls"),
                lambda a: a.update(record=[]),
                lambda a: a.update(calls=[]),
                lambda a: a["record"].update(parameters=[]),
                lambda a: a["record"].update(parameters=[["scalar", 8]]),
                lambda a: a["record"].update(parameters=[["builtin::DisplaySession", 16]] * 7),
                lambda a: a["record"].update(extra=1),
                lambda a: a["calls"].clear(),
                lambda a: a["calls"].update(unknown=dict(sysv_arguments=7, result_max=1)),
                lambda a: a["calls"]["__au_runtime_display_pixel"].update(extra=1),
            ):
                changed = deepcopy(document)
                mutate(changed["functions"]["entry"]["service_abi"])
                with self.assertRaises(ValueError):
                    check(changed)
            for row in (["unknown", 16], ["builtin::DisplaySession", 8], ["scalar", True], ["scalar"], None):
                changed = deepcopy(document)
                changed["functions"]["entry"]["service_abi"]["record"]["parameters"] = [row]
                with self.assertRaises(ValueError):
                    check(changed)
            for field, values in (("sysv_arguments", (True, -1, 1, 8, "7")), ("result_max", (True, -1, 3, "1"))):
                for value in values:
                    changed = deepcopy(document)
                    changed["functions"]["entry"]["service_abi"]["calls"]["__au_runtime_display_pixel"][field] = value
                    with self.assertRaises(ValueError):
                        check(changed)
            mixed = deepcopy(document)
            record = mixed["functions"]["entry"]["service_abi"]["record"]
            prefix = [["builtin::ConsoleSession", 16], ["builtin::ByteRegion", 8]]
            for parameters in (prefix, prefix + [["scalar", 8]]):
                record["parameters"] = parameters
                self.assertEqual(check(mixed)["record"]["parameters"], parameters)
            for parameters in (
                list(reversed(prefix)),
                prefix * 2,
                prefix + [["builtin::ByteRegion", 8]],
                [["builtin::DisplaySession", 16], ["builtin::ByteRegion", 8]],
                [["builtin::CallSession", 16], ["builtin::ByteRegion", 8]],
                [["builtin::ConsoleSession", 16], ["scalar", 8], ["builtin::ByteRegion", 8]],
                [["builtin::ConsoleSession", 16], ["builtin::ByteRegion", 16]],
                prefix + [["builtin::DisplaySession", 16]],
            ):
                record["parameters"] = parameters
                with self.assertRaises(ValueError):
                    check(mixed)
            historical = deepcopy(document)
            del historical["functions"]["entry"]["service_abi"]
            self.assertIsNone(check(historical))
            historical["version"] = 1
            del historical["functions"]["entry"]["copied_record"]
            self.assertIsNone(check(historical))

    def test_call_facts_require_exact_register_contract(self):
        with tempfile.TemporaryDirectory(prefix="aurora-call-facts-") as directory:
            path = Path(directory) / "language.stack.json"
            _, symbols, code, starts = fixture(
                {
                    "entry": [("call", "@__au_runtime_call"), ("ret", "")],
                    "__au_runtime_call": [("ret", "")],
                },
                analyze=False,
            )
            abi = dict(
                record=dict(parameters=[["builtin::CallSession", 16], ["scalar", 8]], result_bytes=8),
                calls={"__au_runtime_call": dict(sysv_arguments=3, result_max=2)},
            )
            fact = dict(local_bytes=64, calls={"__au_runtime_call": 32}, copied_record=None, service_abi=abi)

            def check(value):
                path.write_text(json.dumps(dict(version=2, functions={"entry": value})))
                return decoder.aurora_stack_functions(path, symbols, code, starts, {"entry"})

            self.assertEqual(check(fact)["entry"]["service_abi"], abi)
            for mutate in (
                lambda f: f.pop("service_abi"),
                lambda f: f["service_abi"]["calls"].clear(),
                lambda f: f["service_abi"]["calls"]["__au_runtime_call"].update(sysv_arguments=2),
                lambda f: f["service_abi"]["calls"]["__au_runtime_call"].update(result_max=1),
                lambda f: f["service_abi"]["record"]["parameters"].append(["builtin::ConsoleSession", 16]),
                lambda f: f["service_abi"]["record"]["parameters"].append(["builtin::CallSession", 16]),
                lambda f: f["service_abi"]["record"]["parameters"].reverse(),
            ):
                changed = deepcopy(fact)
                mutate(changed)
                with self.assertRaises(ValueError):
                    check(changed)

    def test_port_facts_keep_copied_shapes_and_exact_raw_operation_bounds(self):
        with tempfile.TemporaryDirectory(prefix="aurora-port-facts-") as directory:
            path = Path(directory) / "language.stack.json"
            read, write = "__au_runtime_port_read8", "__au_runtime_port_write8"
            _, symbols, code, starts = fixture(
                {
                    "entry": [("call", "@" + read), ("call", "@" + write), ("ret", "")],
                    read: [("ret", "")],
                    write: [("ret", "")],
                },
                analyze=False,
            )
            record = dict(
                parameters=[["builtin::PortRange", 16], ["copied_class", 48]],
                result_bytes=48,
                result_kind="copied_class",
            )
            fact = dict(
                local_bytes=256,
                calls={read: 128, write: 128},
                copied_record=None,
                service_abi=dict(
                    record=record,
                    calls={read: dict(sysv_arguments=3, result_max=255), write: dict(sysv_arguments=4, result_max=0)},
                ),
            )

            def check(value):
                path.write_text(json.dumps(dict(version=2, functions={"entry": value})))
                return decoder.aurora_stack_functions(path, symbols, code, starts, {"entry"})["entry"]

            self.assertEqual(check(fact)["service_abi"], fact["service_abi"])
            # Generic parsing must not bake the current UART record's 48 into the schema.
            # Concrete UART ABI equality is checked separately by its admission gate.
            for size in (8, 24, 48, 65536):
                changed = deepcopy(fact)
                changed["service_abi"]["record"].update(
                    parameters=[["builtin::PortRange", 16], ["copied_class", size]], result_bytes=size
                )
                self.assertEqual(check(changed)["service_abi"]["record"]["result_bytes"], size)
            for mutate in (
                lambda f: f.pop("service_abi"),
                lambda f: f["service_abi"]["calls"].pop(read),
                lambda f: f["service_abi"]["calls"].pop(write),
                lambda f: f["service_abi"]["record"].pop("result_kind"),
                lambda f: f["service_abi"]["record"].update(result_kind="scalar"),
                lambda f: f["service_abi"]["record"]["parameters"].reverse(),
                lambda f: f["service_abi"]["record"]["parameters"].append(["builtin::PortRange", 16]),
                lambda f: f["service_abi"]["record"]["parameters"].append(["builtin::ConsoleSession", 16]),
                lambda f: f["service_abi"]["record"]["parameters"].append(["builtin::ByteRegion", 8]),
                lambda f: f["service_abi"]["record"]["parameters"][0].__setitem__(0, "builtin::ConsoleSession"),
            ):
                changed = deepcopy(fact)
                mutate(changed)
                with self.assertRaises(ValueError):
                    check(changed)
            for size in (0, 1, 7, 9, 65544, 1 << 64, True, "48"):
                for result in (False, True):
                    changed = deepcopy(fact)
                    if result:
                        changed["service_abi"]["record"]["result_bytes"] = size
                    else:
                        changed["service_abi"]["record"]["parameters"][1][1] = size
                    with self.subTest(size=size, result=result), self.assertRaises(ValueError):
                        check(changed)
            for host, field, bad in (
                (read, "sysv_arguments", 4),
                (write, "sysv_arguments", 3),
                (read, "result_max", 0),
                (read, "result_max", 256),
                (write, "result_max", 1),
                (write, "result_max", 255),
                (read, "result_max", True),
                (write, "result_max", False),
            ):
                changed = deepcopy(fact)
                changed["service_abi"]["calls"][host][field] = bad
                with self.subTest(host=host, field=field, bad=bad), self.assertRaises(ValueError):
                    check(changed)
            # Missing/extra function maps and duplicate JSON keys fail before graph use.
            for mapping in ({}, {"entry": fact, "unowned": fact}):
                path.write_text(json.dumps(dict(version=2, functions=mapping)))
                with self.assertRaises(ValueError):
                    decoder.aurora_stack_functions(path, symbols, code, starts, {"entry"})
            path.write_text(
                '{"version":2,"functions":{"entry":' + json.dumps(fact) + ',"entry":' + json.dumps(fact) + "}}"
            )
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                decoder.aurora_stack_functions(path, symbols, code, starts, {"entry"})
            path.unlink()
            with self.assertRaises(FileNotFoundError):
                decoder.aurora_stack_functions(path, symbols, code, starts, {"entry"})

    def test_copied_record_facts_are_versioned_and_closed(self):
        with tempfile.TemporaryDirectory(prefix="aurora-abi-facts-") as directory:
            path = Path(directory) / "language.stack.json"
            _, symbols, code, starts = fixture({"entry": [("ret", "")]}, analyze=False)
            copied = dict(parameter_bytes=[72, 64, 8], result_bytes=80)
            fact = dict(local_bytes=512, calls={}, copied_record=copied)
            document = dict(version=2, functions={"entry": fact})

            def check(value=document):
                path.write_text(json.dumps(value))
                return decoder.aurora_stack_functions(path, symbols, code, starts, symbols)["entry"]["copied_record"]

            self.assertEqual(check(), copied)
            for mutate in (
                lambda d: d.update(version=1),
                lambda d: d.update(version=3),
                lambda d: d.update(version=True),
                lambda d: d["functions"]["entry"].pop("copied_record"),
                lambda d: d["functions"]["entry"].update(copied_record=[]),
                lambda d: d["functions"]["entry"]["copied_record"].update(extra=8),
                lambda d: d["functions"]["entry"]["copied_record"].pop("result_bytes"),
                lambda d: d["functions"]["entry"]["copied_record"].update(parameter_bytes={}),
                lambda d: d["functions"]["entry"]["copied_record"].update(parameter_bytes=[8] * 7),
            ):
                changed = deepcopy(document)
                mutate(changed)
                with self.assertRaises(ValueError):
                    check(changed)
            for size in (True, False, 0, -8, 1, 9, 65544, "8", 8.0, None):
                for field in ("parameter_bytes", "result_bytes"):
                    changed = deepcopy(document)
                    changed["functions"]["entry"]["copied_record"][field] = (
                        [size] if field == "parameter_bytes" else size
                    )
                    with self.assertRaises(ValueError):
                        check(changed)
            # Unsupported V2 signatures and historical V1 stack-only facts
            # carry no copied ABI. Required native boundaries reject null.
            null = deepcopy(document)
            null["functions"]["entry"]["copied_record"] = None
            self.assertIsNone(check(null))
            null["version"] = 1
            del null["functions"]["entry"]["copied_record"]
            self.assertIsNone(check(null))
            zero = deepcopy(document)
            zero["functions"]["entry"]["copied_record"]["parameter_bytes"] = []
            self.assertEqual(check(zero), dict(parameter_bytes=[], result_bytes=80))
            path.write_text(
                json.dumps(document).replace('"result_bytes": 80', '"result_bytes": 80, "result_bytes": 80')
            )
            with self.assertRaises(ValueError):
                decoder.aurora_stack_functions(path, symbols, code, starts, symbols)

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

            def check(expected="kernel/uefi/payload.cpp"):
                rows = decoder.object_stack_rows(directory, "payload", {"local_fn": object()}, source_root=source)
                self.assertEqual(rows["local_fn"].source, expected)
                self.assertEqual(rows["local_fn"].signature, signature)

            def frame_source(path, line=1, column=1):
                # Both original and exported sidecars agree, so negative origins
                # reach the source policy rather than failing the .su/.ci join.
                for suffix in (".su", ".ci"):
                    changed = contents[suffix].decode().replace(location, f"{path}:{line}:{column}")
                    original.with_suffix(suffix).write_text(changed)
                    exported.with_suffix(suffix).write_text(changed)

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
            ):
                original.with_suffix(".ci").write_text(changed)
                exported.with_suffix(".ci").write_text(changed)
                with self.subTest(graph=changed), self.assertRaises((ValueError, OSError)):
                    check()
            original.with_suffix(".ci").write_bytes(contents[".ci"])
            exported.with_suffix(".ci").write_bytes(contents[".ci"])
            check()

            headers = root / "include/c++/16"
            header = headers / "string_view"
            headers.mkdir(parents=True)
            header.write_text("void local_fn() {}\n")
            outside = root / "outside.hpp"
            outside.write_text("void local_fn() {}\n")
            other_version = headers.parent / "17/string_view"
            other_version.parent.mkdir()
            other_version.write_text(header.read_text())
            escape = headers / "escape"
            escape.symlink_to(outside)
            with patch.object(decoder, "cpp_header_root", return_value=headers):
                frame_source(header)
                check(str(header))
                obj = SimpleNamespace(type=1, functions={"local_fn": object()}, path=exported)
                with (
                    patch.object(decoder, "Elf", return_value=obj),
                    patch.object(decoder, "compiler_witnesses", side_effect=lambda _, __, variants: variants),
                ):
                    frames, receipts = decoder.cpp_frames(directory, obj, objects=("payload",), source_root=source)
                    self.assertEqual(frames, {"local_fn": 16})
                    receipt = receipts["local_fn"][0]
                    self.assertEqual(receipt["source"], str(header))
                    self.assertEqual(receipt["source_sha256"], hashlib.sha256(header.read_bytes()).hexdigest())
                    self.assertEqual((receipt["line"], receipt["column"], receipt["record"]), (1, 1, signature))
                    for line, column in ((2, 1), (1, len(header.read_text().splitlines()[0]) + 2)):
                        frame_source(header, line, column)
                        with (
                            self.subTest(line=line, column=column),
                            self.assertRaisesRegex(ValueError, "Invalid frame location"),
                        ):
                            decoder.cpp_frames(directory, obj, objects=("payload",), source_root=source)
                    frame_source(header)
                    # The second confinement check independently rejects a header
                    # on a weaker historical path, even with a normalized row.
                    row = decoder.StackRecord(str(header), 1, 1, signature, 16, "static")
                    with patch.object(decoder, "object_stack_rows", return_value={"local_fn": row}):
                        with self.assertRaisesRegex(ValueError, "Historical compiler frame"):
                            decoder.cpp_frames(root / "historical", obj, objects=("payload",), source_root=source)
                alias = headers / "alias"
                alias.symlink_to(header)
                su = exported.with_suffix(".su").read_text()
                ci = exported.with_suffix(".ci").read_text()
                alias_node = ci.splitlines()[1].replace(":local_fn", ":other_fn").replace(str(header), str(alias))
                replacements = {
                    ".su": su + su.replace(str(header), str(alias)),
                    ".ci": ci[:-1] + alias_node + "\n}",
                }
                for suffix, data in replacements.items():
                    original.with_suffix(suffix).write_text(data)
                    exported.with_suffix(suffix).write_text(data)
                with self.assertRaisesRegex(ValueError, "Aliased compiler source record"):
                    decoder.object_stack_rows(
                        directory, "payload", {"local_fn": object(), "other_fn": object()}, source_root=source
                    )
                frame_source(header)
                for path, error in (
                    (outside, "outside selected kernel"),
                    (other_version, "outside selected kernel"),
                    (escape, "escaped supported root"),
                    (headers, "not a regular file"),
                ):
                    frame_source(path)
                    with self.subTest(source=path), self.assertRaisesRegex(ValueError, error):
                        check()
                frame_source(headers / "missing")
                with self.assertRaises(FileNotFoundError):
                    check()
                frame_source(header)
                real_open = Path.open

                def unreadable(path, *args, **kwargs):
                    if path == header:
                        raise PermissionError("unreadable fixture header")
                    return real_open(path, *args, **kwargs)

                with patch.object(Path, "open", unreadable), self.assertRaises(PermissionError):
                    check()
                relocated = headers.with_name("relocated")
                headers.rename(relocated)
                headers.symlink_to(relocated, target_is_directory=True)
                with self.assertRaisesRegex(ValueError, "Noncanonical compiler header root"):
                    check()
                headers.unlink()
                relocated.rename(headers)
                # The earlier normalization boundary also keeps historical
                # coherent compiler exports kernel-only.
                historical = root / "historical"
                (historical / "objects").mkdir(parents=True)
                for suffix in (".su", ".ci"):
                    changed = exported.with_suffix(suffix).read_text().replace(spelling, "kernel/uefi/payload.cpp")
                    (historical / ("objects/payload" + suffix)).write_text(changed)
                with self.assertRaisesRegex(ValueError, "Historical compiler frame"):
                    decoder.object_stack_rows(historical, "payload", {"local_fn": object()}, source_root=source)
            frame_source(unit)
            check()

    def test_artifact_hash_roots_are_explicit_and_confined(self):
        common = graphical.common
        with tempfile.TemporaryDirectory(prefix="admission-roots-") as temporary:
            base = Path(temporary)
            source, build = base / "source", base / "meson/kernel-images/uefi/graphical-console"
            source.mkdir()
            build.mkdir(parents=True)
            (build / "same").write_text("build")
            (base / "outside").write_text("outside")
            (build / "escape").symlink_to(base / "outside")
            with (
                patch.object(common, "ROOT", common.ROOT),
                patch.object(common, "BUILD", common.BUILD),
                patch.object(common, "RECEIPT", common.RECEIPT),
            ):
                common.configure_paths(build, source)
                self.assertEqual(set(common.hashes([build / "same"])), {"build:same"})
                self.assertEqual(
                    common.build_artifacts(["payload.o", "payload.su", "payload.ci"])[-1],
                    build / "objects/payload.source.json",
                )
                for path in (base / "outside", build / "escape"):
                    with self.assertRaises(ValueError):
                        common.hashes([path])
                with self.assertRaises(ValueError):
                    common.hashes([build / "same", build / "same"])
                (base / "link").symlink_to(build, target_is_directory=True)
                with self.assertRaises(ValueError):
                    common.configure_paths(base / "link", source)
                with self.assertRaises(ValueError):
                    common.configure_paths(base, source)


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
            result = decoder.cpp_stack_functions(symbols, code, starts, b"", frames, edges)
            self.assertEqual(graphical.common.graph_peak(result, "root")["peak"], 48)
            self.assertEqual(result["root"]["calls"][0]["live_bytes"], 32)
            for changed in (set(), edges | {("leaf", "root")}, {("root", "absent")}, {("unknown", "leaf")}):
                with self.subTest(edges=changed), self.assertRaises(ValueError):
                    decoder.cpp_stack_functions(symbols, code, starts, b"", frames, changed)
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
                    decoder.cpp_stack_functions(symbols, changed, starts, b"", frames, edges)
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
        check = lambda rows=code, raw=payload: decoder.cpp_stack_functions(
            symbols, rows, {0: "root"}, raw, {"root": 16}, set()
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

    def test_module_decoding_and_actual_reflection_inventory(self):
        for symbol, module in (
            ("__au_m_m2_3std13binary_buffer_n2_3std14BinaryBuffer64_d5equal", "std.binary_buffer"),
            ("__au_k_m2_3std5array_n2_3std5array_d5array_t2_u8_v20", "std.array"),
            ("__au_v_m2_3std7decimal_n1_3std_d18format_decimal_i64", "std.decimal"),
        ):
            self.assertEqual(decoder.aurora_module(symbol), module)
        for malformed in ("__au_v_m2_3std99bytes_n0__d1x", "__au_v_m1_0_n0__d1x", "__au_v_m1_3stdx_n0__d1x"):
            self.assertIsNone(decoder.aurora_module(malformed))
        helpers = set(REFLECTION) | {"__au_reflect_s8_size", "__au_reflect_s8_field_count"}
        self.assertEqual(decoder.reflection_inventory(helpers), helpers)
        for removed in ("aurora_reflect_size", "__au_reflect_s8_size"):
            with self.assertRaises(ValueError):
                decoder.reflection_inventory(helpers - {removed})

    def test_generated_imports_and_private_reflection_bindings(self):
        names = set(graphical.LANGUAGE_ROOTS) | set(REFLECTION)  # Fixture construction only.
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
        # Additional generated locals are admitted by exact compiler-fact/object
        # coverage, not a second handwritten source-module list.
        extra = "__au_v_m1_22kernel_display_service_n0__d15display_service"
        verify(functions=names | {extra}, table=bindings + f"\n1: 000000 1 FUNC LOCAL DEFAULT 1 {extra}")
        with self.assertRaisesRegex(ValueError, "binding inventory"):
            verify(functions=names | {extra})
        for missing in sorted(names):
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                verify(functions=names - {missing})
        for table, reason in [
            (bindings.replace("LOCAL DEFAULT", "GLOBAL DEFAULT"), "private ELF binding"),
            (bindings.replace("GLOBAL HIDDEN", "GLOBAL DEFAULT"), "private ELF binding"),
            (bindings + "\n" + bindings.splitlines()[0], "Duplicate"),
            ("\n".join(bindings.splitlines()[1:]), "binding inventory"),
        ]:
            with self.assertRaisesRegex(ValueError, reason):
                verify(table=table)

        for name in REFLECTION:
            for changed in ("GLOBAL HIDDEN", "LOCAL DEFAULT", "WEAK DEFAULT"):
                mutant = bindings.replace(f"GLOBAL DEFAULT 1 {name}", f"{changed} 1 {name}")
                with self.assertRaises(ValueError):
                    verify(table=mutant)
            with self.assertRaises(ValueError):
                verify(symbols=imports + [decoder.Symbol(name, 0, 0, 0, 0)])
            with self.assertRaises(ValueError):
                verify(functions=names - {name})
        for extra in ("aurora_reflect_address", "__au_reflect_s7_size", "__au_reflect_s1_address"):
            with self.assertRaises(ValueError):
                verify(functions=names | {extra})

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

    def test_native_service_contract_uses_bound_compiler_facts(self):
        graph = {
            graphical.ENTRY: [("ret", "")],
            graphical.VALUE_BRIDGE: [("jmp", "@" + graphical.VALUE_ENTRY)],
            graphical.VALUE_ENTRY: [("ret", "")],
            "pixel": [("call", "@__au_runtime_display_pixel"), ("ret", "")],
            "__au_runtime_display_pixel": [("ret", "")],
        }
        _, symbols, code, starts = fixture(graph, analyze=False)
        record = dict(
            parameters=[["builtin::ConsoleSession", 16], ["builtin::DisplaySession", 16], ["scalar", 8], ["scalar", 8]],
            result_bytes=8,
        )
        functions = {name: dict(calls=[], service_abi=None) for name in symbols}
        functions[graphical.ENTRY]["service_abi"] = dict(record=record, calls={})
        functions["pixel"] = dict(
            calls=[dict(target="__au_runtime_display_pixel", address=symbols["pixel"].address, live_bytes=32)],
            service_abi=dict(record=None, calls={"__au_runtime_display_pixel": dict(sysv_arguments=7, result_max=1)}),
        )
        names = set(symbols) - {"__au_runtime_display_pixel"}

        def verify(value=functions, instructions=code):
            return graphical.verify_private_abi(
                decoder, SimpleNamespace(functions=symbols), instructions, starts, names, value
            )

        self.assertEqual(verify()["entry_record"], record)
        for mutate in (
            lambda f: f[graphical.ENTRY].update(service_abi=None),
            lambda f: f[graphical.ENTRY]["service_abi"].update(record=None),
            lambda f: f[graphical.ENTRY]["service_abi"]["record"].update(
                parameters=list(reversed(record["parameters"]))
            ),
            lambda f: f[graphical.ENTRY]["service_abi"]["record"].update(result_bytes=1),
            lambda f: f["pixel"].update(service_abi=None),
            lambda f: f["pixel"]["service_abi"]["calls"].clear(),
            lambda f: f["pixel"]["service_abi"]["calls"]["__au_runtime_display_pixel"].update(sysv_arguments=6),
            lambda f: f["pixel"]["service_abi"]["calls"]["__au_runtime_display_pixel"].update(result_max=2),
            lambda f: f["pixel"]["calls"][0].update(live_bytes=24),
            lambda f: f["pixel"]["calls"].clear(),
        ):
            changed = deepcopy(functions)
            mutate(changed)
            with self.assertRaises(ValueError):
                verify(changed)
        for operation in [("call", "0"), ("jmp", "*%rax"), ("ret", "")]:
            changed = dict(code)
            at = symbols[graphical.VALUE_BRIDGE].address
            changed[at] = decoder.Instruction(at, 1, *operation)
            with self.assertRaises(ValueError):
                verify(instructions=changed)

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

    @staticmethod
    def bios_absolute_fixture(kind=10, target=0x20000, addend=0, constant=bytes(range(32)), flags=2, entry=0):
        # Real Elf byte accessors over explicit section bytes; only ELF-file parsing
        # is outside this unit's scope. No relocation validator is mocked.
        original = b"\xb8" + bytes(4) + b"\xc3"
        installed = b"\xb8" + ((target + addend) & 0xFFFFFFFF).to_bytes(4, "little") + b"\xc3"
        null = (0,) * 10
        obj, linked = decoder.Elf.__new__(decoder.Elf), decoder.Elf.__new__(decoder.Elf)
        obj.type, linked.type = 1, 2
        obj.path = Path("fixture.o")
        linked.path = Path("/fixture/kernel-images/bios/console/kernel.elf")
        obj.data, linked.data = original + constant, installed + constant
        obj.sections = [null, (0, 1, 6, 0, 0, 6, 0, 0, 1, 0), (0, 1, flags, 0, 6, len(constant), 0, 0, 1, entry)]
        linked.sections = [null, (0, 1, 6, 0x10000, 0, 6, 0, 0, 1, 0), (0, 1, 2, target, 6, len(constant), 0, 0, 1, 0)]
        symbol = decoder.Symbol("leaf", 0, 6, 1, 2)
        obj.functions = {"leaf": symbol}
        linked.functions = {"leaf": decoder.Symbol("leaf", 0x10000, 6, 1, 2)}
        reference = decoder.Symbol("target", 0, len(constant), 2, 1)
        obj.symbols = [symbol, reference]
        linked.symbols = [linked.functions["leaf"], decoder.Symbol("target", target, len(constant), 2, 1)]
        obj.relocations = [(1, 1, kind, "target", addend)]
        obj.relocation_symbols = {(1, 1): reference}
        return linked, obj, symbol

    def test_bios_absolute_named_relocations_bind_signedness_target_and_addend(self):
        for kind, target, addend in ((10, 0xF0000000, 7), (11, 0x20000, -0x20010), (11, 0x20000, 8)):
            linked, obj, symbol = self.bios_absolute_fixture(kind, target, addend)
            self.assertTrue(decoder.object_matches(linked, obj, symbol))
            for changed in ("target", "addend", "byte", "missing", "ambiguous"):
                image, source = deepcopy(linked), deepcopy(obj)
                if changed == "target":
                    image.symbols[-1] = decoder.Symbol("target", target + 1, 32, 2, 1)
                elif changed == "addend":
                    source.relocations[0] = (1, 1, kind, "target", addend + 1)
                elif changed == "byte":
                    image.data = image.data[:1] + bytes([image.data[1] ^ 1]) + image.data[2:]
                elif changed == "missing":
                    image.symbols.pop()
                else:
                    image.symbols.append(decoder.Symbol("target", target + 32, 32, 2, 1))
                with self.subTest(kind=kind, changed=changed):
                    self.assertFalse(decoder.object_matches(image, source, symbol))
            if target == 0xF0000000 or addend < 0:
                obj.relocations[0] = (1, 1, 11 if kind == 10 else 10, "target", addend)
                self.assertFalse(decoder.object_matches(linked, obj, symbol))
        for kind, target, addend in ((10, 1 << 32, 0), (10, 0xFFFFFFFF, 1), (11, 1 << 31, 0), (11, 0, -(1 << 31) - 1)):
            linked, obj, symbol = self.bios_absolute_fixture(kind, target, addend)
            with self.subTest(kind=kind, target=target, addend=addend):
                self.assertFalse(decoder.object_matches(linked, obj, symbol))
        for kind in (1, 8, 9, 12):  # R64 and unreviewed relocation forms remain closed.
            linked, obj, symbol = self.bios_absolute_fixture(kind)
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "Unsupported text relocation"):
                decoder.object_matches(linked, obj, symbol)
        for path in (
            "/fixture/kernel-images/uefi/console/kernel.elf",
            "/fixture/kernel-images/uefi/console/payload.elf",
            "/fixture/kernel-images/bios/normal/kernel.elf",
        ):
            linked, obj, symbol = self.bios_absolute_fixture()
            linked.path = Path(path)
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "Unsupported text relocation"):
                decoder.object_matches(linked, obj, symbol)

    def test_bios_absolute_constants_bind_exact_bytes_and_reviewed_merge_shapes(self):
        for constant, flags, entry in ((bytes(range(32)), 0x12, 32), (b"UART constant\0", 0x32, 1)):
            linked, obj, symbol = self.bios_absolute_fixture(constant=constant, flags=flags, entry=entry)
            obj.relocation_symbols[1, 1] = decoder.Symbol("", 0, 0, 2, 3)
            self.assertTrue(decoder.object_matches(linked, obj, symbol))
            linked.data = linked.data[:6] + bytes([linked.data[6] ^ 1]) + linked.data[7:]
            self.assertFalse(decoder.object_matches(linked, obj, symbol))
        for flags, entry, addend in ((0x12, 16, 0), (0x13, 32, 0), (0x12, 32, 1), (0x32, 2, 0)):
            linked, obj, symbol = self.bios_absolute_fixture(flags=flags, entry=entry, addend=addend)
            obj.relocation_symbols[1, 1] = decoder.Symbol("", 0, 0, 2, 3)
            with self.subTest(flags=flags, entry=entry, addend=addend), self.assertRaises(ValueError):
                decoder.object_matches(linked, obj, symbol)
        linked, obj, symbol = self.bios_absolute_fixture(constant=b"unterminated", flags=0x32, entry=1)
        obj.relocation_symbols[1, 1] = decoder.Symbol("", 0, 0, 2, 3)
        with self.assertRaisesRegex(ValueError, "Unterminated"):
            decoder.object_matches(linked, obj, symbol)

    def test_bios_absolute_section_identity_requires_unambiguous_retained_anchor(self):
        linked, obj, symbol = self.bios_absolute_fixture()
        obj.relocation_symbols[1, 1] = decoder.Symbol("", 0, 0, 2, 3)
        self.assertTrue(decoder.object_matches(linked, obj, symbol))
        for changed in ("missing-source", "missing-linked", "ambiguous", "outside"):
            image, source = deepcopy(linked), deepcopy(obj)
            if changed == "missing-source":
                source.symbols.pop()
            elif changed == "missing-linked":
                image.symbols.pop()
            elif changed == "ambiguous":
                image.symbols.append(decoder.Symbol("target", 0x30000, 32, 2, 1))
            else:
                image.sections[2] = (0, 1, 2, 0x20001, 6, 32, 0, 0, 1, 0)
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                decoder.object_matches(image, source, symbol)

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
                    graphical.common.graph_peak(functions, name)

    def test_fixed_frame_loop_and_stack_growth(self):
        functions, *_ = fixture({"fixed": [("test", "%eax,%eax"), ("jne", "@fixed"), ("ret", "")]})
        self.assertEqual(graphical.common.graph_peak(functions, "fixed")["peak"], 8)
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

    def test_handwritten_assembly_stack_forms_still_fail_closed(self):
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

    def test_checked_artifacts_and_semantics(self):
        with tempfile.TemporaryDirectory(prefix="graphical-controls-") as directory:
            root = Path(directory)
            output = root / "payload.bin"
            output.write_bytes(b"checked image")

            def hashes(items):
                return {str(path.relative_to(root)): graphical.digest(path) for path in items}

            receipt = root / "graphical-console-admission.json"
            data = dict(
                schema="aurora-graphical-console-admission-v6",
                mode="graphical-console",
                status="requires-independent-review",
                clock="tcg-original-clock",
                image={"image_result": 1},
                stack={"stack_result": 456},
                sha256=hashes([output]),
            )
            receipt.write_text(json.dumps(data))
            with (
                patch.object(graphical, "BUILD", root),
                patch.object(graphical, "RECEIPT", receipt),
                patch.object(graphical, "build_files", return_value=[output]),
                patch.object(graphical.common, "hashes", side_effect=hashes),
                patch.object(graphical, "image_evidence", return_value=data["image"]),
                patch.object(graphical, "stack_evidence", return_value=data["stack"]),
            ):
                self.assertEqual(graphical.checked("graphical-console"), data)
                output.write_bytes(b"changed image")
                with self.assertRaises(ValueError):
                    graphical.checked("graphical-console")
                output.write_bytes(b"checked image")
                for mode in ["graphical-console-capture", "console", "framebuffer", "graphical-console-stale"]:
                    with self.subTest(mode=mode), self.assertRaises(ValueError):
                        graphical.checked(mode)
                for key, value in (
                    ("schema", "aurora-graphical-console-admission-v1"),
                    ("status", "accepted"),
                    ("clock", "accelerated"),
                    ("image", {}),
                    ("stack", {}),
                    ("image", {"image_result": True}),
                    ("stack", {"stack_result": 0}),
                    ("sha256", {}),
                    ("sha256", {**data["sha256"], "foreign": "0" * 64}),
                ):
                    receipt.write_text(json.dumps(data | {key: value}))
                    with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                        graphical.checked("graphical-console")
                receipt.write_text(json.dumps(data))
                self.assertEqual(graphical.checked("graphical-console"), data)

    def test_unambiguous_json_and_failed_image_invalidates_admission(self):
        with tempfile.TemporaryDirectory(prefix="graphical-invalid-image-") as directory:
            root = Path(directory)
            receipt = root / "graphical-console-admission.json"
            for raw in (
                '{"mode":"graphical-console","mode":"graphical-console"}',
                '{"nested":{"same":1,"same":1}}',
                '{"number":NaN}',
                '{"number":Infinity}',
            ):
                receipt.write_text(raw)
                with self.assertRaises(ValueError):
                    graphical.read_json(receipt)
            (root / "payload.bin").write_bytes(b"invalid image")
            (root / "payload.elf").write_bytes(b"invalid ELF")
            pe = root / "esp/EFI/BOOT/BOOTX64.EFI"
            pe.parent.mkdir(parents=True)
            pe.write_bytes(b"invalid PE")
            with (
                patch.object(graphical, "BUILD", root),
                patch.object(graphical.common, "BUILD", root),
                patch.object(graphical, "RECEIPT", receipt),
                patch.object(graphical, "build_files", return_value=[root / "payload.bin", root / "payload.elf", pe]),
            ):
                for mode in ("graphical-console", "graphical-console-capture"):
                    receipt.write_text("stale admission")
                    with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "Payload ELF architecture"):
                        graphical.emit(mode)
                    self.assertFalse(receipt.exists(), "Failed fresh image checks must remove stale admission")


class CaptureAdmission(unittest.TestCase):
    capture = "graphical-console-capture"

    def test_capture_structure_gate_is_required_by_emit_and_checked(self):
        graphical.require_capture_structure("graphical-console")
        with self.assertRaisesRegex(ValueError, "Missing current capture structure evidence"):
            graphical.require_capture_structure(self.capture)
        with tempfile.TemporaryDirectory(prefix="graphical-capture-pending-") as directory:
            receipt = Path(directory) / "admission.json"
            receipt.write_text("stale admission")
            with (
                patch.object(graphical, "RECEIPT", receipt),
                patch.object(graphical, "image_evidence", return_value={"image_result": 1}),
                patch.object(graphical, "stack_evidence", return_value={"normal": 1}),
                patch.object(graphical, "build_files", return_value=[]),
                patch.object(graphical.common, "hashes", return_value={}),
            ):
                with self.assertRaisesRegex(ValueError, "Missing current capture structure evidence"):
                    graphical.emit(self.capture)
                self.assertFalse(receipt.exists(), "Missing structure cannot leave a capture admission report")
                data = dict(
                    schema="aurora-graphical-console-admission-v6",
                    mode=self.capture,
                    status="requires-independent-review",
                    clock="tcg-original-clock",
                    image={"image_result": 1},
                    stack={"normal": 1},
                    sha256={},
                )
                receipt.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError, "Missing current capture structure evidence"):
                    graphical.checked(self.capture)


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


if __name__ == "__main__":
    unittest.main()
