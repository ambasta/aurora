#!/usr/bin/env python3
"""Connect three-domain user metadata to exact ELF bytes and probe ownership."""

from pathlib import Path
import argparse
import copy
import importlib.util
import json
import shutil
import struct
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("user_phase_image_builder", ROOT / "scripts/kernel-uefi-ipc-images.py")
fixture = load("user_phase_elf_fixture", ROOT / "tests/kernel-uefi-user-image.py")
smoke = load("user_phase_transcript", ROOT / "tests/kernel-uefi-user-phases-smoke.py")


def main():
    positives = negatives = 0

    def reject(action, label):
        nonlocal negatives
        try:
            action()
        except (ValueError, TypeError, KeyError):
            negatives += 1
        else:
            raise RuntimeError("Invalid user-phase image accepted: " + label)

    # Free fixture bytes after the trap helpers for each selectable probe.
    probe_at = {"mmio": 64, "softint": 66, "fpu": 68, "peer_code": 70, "unknown": 74}
    for mode in ("user-phases", "user-context", "user-unknown"):
        hostile_mode = mode in smoke.FIXTURE_MODES
        metadata = dict(images={}, kernel=dict(drain_begin=100, drain_end=104, text_end=4096, forged_pc=0))
        for domain, name in enumerate(smoke.NAMES):
            base = builder.BASE + domain * 16384
            data, blob, symbols = fixture.fixture(base)
            symbols["aurora_user_main"] = base + 20
            hostile = domain == 0 and hostile_mode
            if hostile:
                blob[2:8] = bytes.fromhex("48ff0c2475fa")
                symbols.update(aurora_budget_context_begin=base + 2, aurora_budget_context_end=base + 8)
                for kind, at in probe_at.items():
                    opcode = builder.PROBE_OPCODES[kind]
                    blob[at : at + len(opcode)] = opcode
                    symbols[f"aurora_probe_{kind}_pc"] = base + at
            data[4096:] = blob

            def verify(elf, installed, names):
                found = builder.verify(elf, installed, base, names, dispatcher=True)
                return builder.service_metadata(found, installed, names, 10)

            metadata["images"][name] = verify(data, blob, symbols)
            positives += 1
            # Even an ELF and binary changed together cannot introduce a forged
            # retained return/fault instruction or a fake register-probe loop.
            sites = [
                "aurora_program_return_pc",
                ".Laurora_bounds_trap",
                ".Laurora_overflow_trap",
                ".Laurora_division_zero_trap",
                ".Laurora_shift_count_trap",
            ]
            for symbol in sites:
                changed = blob.copy()
                changed[symbols[symbol] - base] = 0x90
                elf = data.copy()
                elf[4096:] = changed
                reject(lambda: verify(elf, changed, symbols), "retained opcode " + symbol)
                forged = dict(symbols)
                forged[symbol] = base + 4096
                reject(lambda: verify(data, blob, forged), "foreign exact site " + symbol)
            forged = dict(symbols, aurora_user_main=base + 30)
            reject(lambda: verify(data, blob, forged), "compiled function overlaps fault helpers")
            changed = blob.copy()
            changed[0] ^= 1
            reject(lambda: verify(data, changed, symbols), "installed bytes differ from linked RX")
            if hostile:
                for offset in range(2, 8):
                    changed = blob.copy()
                    changed[offset] ^= 1
                    elf = data.copy()
                    elf[4096:] = changed
                    reject(lambda: verify(elf, changed, symbols), "context loop byte")
                for kind, at in probe_at.items():
                    forged = dict(symbols, **{f"aurora_probe_{kind}_pc": symbols[".Laurora_bounds_trap"]})
                    reject(lambda: verify(data, blob, forged), kind + " probe aliases retained bounds")
                    changed = blob.copy()
                    changed[at] = 0x90
                    elf = data.copy()
                    elf[4096:] = changed
                    reject(lambda: verify(elf, changed, symbols), kind + " probe exact opcode")
                    forged = dict(symbols)
                    del forged[f"aurora_probe_{kind}_pc"]
                    reject(lambda: verify(data, blob, forged), kind + " probe missing from the set")
                forged = dict(symbols, aurora_probe_pc=base + 74)
                reject(lambda: verify(data, blob, forged), "single probe beside the set")
        smoke.metadata_valid(metadata, mode)
        positives += 1
        for source, target in (("clean", "bounds"), ("bounds", "peer"), ("peer", "clean")):
            changed = copy.deepcopy(metadata)
            changed["images"][target] = changed["images"][source]
            reject(lambda: smoke.metadata_valid(changed, mode), "cross-domain metadata authority")
        if hostile_mode:
            changed = copy.deepcopy(metadata)
            changed["images"]["clean"]["context_begin"] = changed["images"]["clean"]["context_end"] = 0
            reject(lambda: smoke.metadata_valid(changed, mode), "lost client register probe")
            changed = copy.deepcopy(metadata)
            del changed["images"]["clean"]["probes"]
            reject(lambda: smoke.metadata_valid(changed, mode), "lost client probe set")
    # Dedicated call authority is admitted only in the first two-domain image.
    builder.validate_composition("normal", True, False, True, False, False, True)
    for options in (
        (False, False, True, False, False, True),
        (True, True, True, False, False, True),
        (True, False, True, True, False, True),
        (True, False, True, False, True, True),
    ):
        reject(lambda: builder.validate_composition("normal", *options), "call composition")
    base = builder.BASE
    data, blob, symbols = fixture.fixture(base)
    blob[20:23] = b"\xcd\x82\xc3"
    data[4096:] = blob
    symbols.update(__au_runtime_call=base + 20, aurora_call_return_pc=base + 22, private_call=base + 24)
    builder.verify(data, blob, base, symbols, call_entry="private_call")
    positives += 1
    reject(lambda: builder.verify(data, blob, base, symbols), "call authority without call entry")
    reject(
        lambda: builder.verify(data, blob, base, symbols, dispatcher=True, call_entry="private_call"),
        "call in dispatcher",
    )
    for offset in (20, 21, 22):
        changed = blob.copy()
        changed[offset] ^= 1
        elf = data.copy()
        elf[4096:] = changed
        reject(lambda: builder.verify(elf, changed, base, symbols, call_entry="private_call"), "call opcode")
    for symbol in ("__au_runtime_call", "aurora_call_return_pc"):
        for value in (0, base + 16, base + 4096):
            changed = dict(symbols)
            changed[symbol] = value
            reject(lambda: builder.verify(data, blob, base, changed, call_entry="private_call"), "call site")
    entry = dict(
        source_name="aurora_user_main",
        receiver=None,
        receiver_mutable=None,
        borrowed_root_count=0,
        borrowed_roots=[],
        borrowed_root_abi=dict(
            kind="none", register=None, tuple_payload_bytes=0, tuple_reserved_bytes=0, saved_root_reserved_bytes=0
        ),
        parameter_bytes=40,
        parameters=[dict(offset=0, bytes=16, kind="service")]
        + [dict(offset=offset, bytes=8, kind="u64") for offset in (16, 24, 32)],
        result=dict(bytes=8, kind="u64"),
    )
    facts = dict(version=2, functions={"private_call": entry})
    builder.call_entry_abi(facts)
    positives += 1
    for field, value in (
        ("parameter_bytes", 32),
        ("receiver", "foreign"),
        ("borrowed_root_count", 1),
        ("result", dict(bytes=8, kind="i64")),
        ("parameters", entry["parameters"][:-1]),
    ):
        bad = copy.deepcopy(facts)
        bad["functions"]["private_call"][field] = value
        reject(lambda: builder.call_entry_abi(bad), "call entry ABI " + field)
    for index in range(4):
        for field, value in (("offset", 99), ("bytes", 99), ("kind", "class")):
            bad = copy.deepcopy(facts)
            bad["functions"]["private_call"]["parameters"][index][field] = value
            reject(lambda: builder.call_entry_abi(bad), "call entry ABI parameter")
    # The new copied envelope is opt-in and cannot enter a legacy/mixed profile.
    builder.validate_composition(
        "normal", service_budget=True, user_budget=True, ram_file=True, ram_scratchpad_console=True
    )
    positives += 1
    reject(
        lambda: builder.validate_composition(
            "normal", service_budget=True, user_budget=True, ram_scratchpad_console=True
        ),
        "scratchpad without retained service composition",
    )
    for extra in (
        dict(dispatcher=True),
        dict(snapshot=True),
        dict(blocking_call=True),
        dict(file_call=True),
        dict(program_console=True),
        dict(service_budget=False),
        dict(user_budget=False),
    ):
        options = dict(service_budget=True, user_budget=True, ram_file=True, ram_scratchpad_console=True) | extra
        reject(lambda: builder.validate_composition("normal", **options), "scratchpad mixed composition")
    reject(
        lambda: builder.call_entry_abi({"version": 2, "functions": {"private_call": dict(entry, parameter_bytes=96)}}),
        "legacy Call entry must not accept copied envelope",
    )
    builder.validate_composition(
        "normal",
        service_budget=True,
        user_budget=True,
        ram_file=True,
        ram_scratchpad_console=True,
        ram_scratchpad_fixture=True,
    )
    positives += 1
    reject(
        lambda: builder.validate_composition(
            "normal", service_budget=True, user_budget=True, ram_file=True, ram_scratchpad_fixture=True
        ),
        "scratchpad fixture without copied composition",
    )
    # Retained Serve is a distinct singleton role, never a broadened Call site.
    builder.validate_composition("normal", service_budget=True, user_budget=True, ram_file=True)
    for extra in (
        dict(dispatcher=True),
        dict(snapshot=True),
        dict(blocking_call=True),
        dict(file_call=True),
        dict(program_console=True),
        dict(service_budget=False),
        dict(user_budget=False),
    ):
        options = dict(service_budget=True, user_budget=True, ram_file=True) | extra
        reject(lambda: builder.validate_composition("normal", **options), "Serve mixed composition")
    base = builder.BASE + 16384
    data, blob, symbols = fixture.fixture(base)
    blob[20:23] = b"\xcd\x82\xc3"
    data[4096:] = blob
    symbols.update(__au_runtime_serve_exchange=base + 20, aurora_serve_return_pc=base + 22, private_serve=base + 24)
    builder.verify(data, blob, base, symbols, serve_entry="private_serve")
    positives += 1
    reject(lambda: builder.verify(data, blob, base, symbols), "Serve authority without Serve entry")
    reject(lambda: builder.verify(data, blob, base, symbols, call_entry="private_serve"), "Serve in Call role")
    for offset in (20, 21, 22):
        changed = blob.copy()
        changed[offset] ^= 1
        elf = data.copy()
        elf[4096:] = changed
        reject(lambda: builder.verify(elf, changed, base, symbols, serve_entry="private_serve"), "Serve stub opcode")
    for symbol in ("__au_runtime_serve_exchange", "aurora_serve_return_pc"):
        for value in (0, base + 16, symbols[".Laurora_bounds_trap"], base + 4096):
            changed = dict(symbols)
            changed[symbol] = value
            reject(lambda: builder.verify(data, blob, base, changed, serve_entry="private_serve"), "Serve exact site")
    mixed = dict(symbols, __au_runtime_call=base + 20, aurora_call_return_pc=base + 22)
    reject(lambda: builder.verify(data, blob, base, mixed, serve_entry="private_serve"), "Serve foreign Call stub")
    serve_entry = dict(
        entry,
        parameter_bytes=16,
        parameters=[dict(offset=0, bytes=16, kind="service", type_name="builtin::ServeSession")],
    )
    serve = dict(
        version=2,
        functions=dict(private_serve=serve_entry),
        enums=dict(private_status=dict(source_name="__au_serve_status", cases=dict(request=0, cancelled=1))),
        records=dict(
            private_request=dict(
                source_name="__au_serve_request",
                size=16,
                alignment=8,
                reserved=16,
                fields=[
                    dict(name="status", offset=0, bytes=8, array_length=0, kind="enum", type_name="private_status"),
                    dict(name="value", offset=8, bytes=8, array_length=0, kind="u64"),
                ],
            )
        ),
    )
    builder.serve_entry_abi(serve)
    positives += 1
    for key, value in (
        ("parameter_bytes", 40),
        ("result", dict(bytes=16, kind="class")),
        ("parameters", [dict(offset=0, bytes=16, kind="service", type_name="builtin::CallSession")]),
    ):
        bad = copy.deepcopy(serve)
        bad["functions"]["private_serve"][key] = value
        reject(lambda: builder.serve_entry_abi(bad), "Serve singleton entry")
    for key, value in (("size", 24), ("alignment", 16), ("reserved", True)):
        bad = copy.deepcopy(serve)
        bad["records"]["private_request"][key] = value
        reject(lambda: builder.serve_entry_abi(bad), "Serve copied layout")
    for index in range(2):
        for key, value in (("offset", 16), ("bytes", 4), ("kind", "i64")):
            bad = copy.deepcopy(serve)
            bad["records"]["private_request"]["fields"][index][key] = value
            reject(lambda: builder.serve_entry_abi(bad), "Serve copied field")
    for value in (2, 1 << 63, True):
        bad = copy.deepcopy(serve)
        bad["enums"]["private_status"]["cases"]["cancelled"] = value
        reject(lambda: builder.serve_entry_abi(bad), "Serve exact status ordinal")
    for selected in (False, True):
        module = "scratchpad_service_fixture" if selected else "ram_file_service"
        symbol = "__au_v_m1_" + str(len(module)) + module + "_n0__d16aurora_user_main"
        variant = copy.deepcopy(serve)
        variant["functions"] = {symbol: variant["functions"]["private_serve"]}
        builder.scratchpad_service_entry_abi(variant, fixture=selected)
        positives += 1
        reject(
            lambda: builder.scratchpad_service_entry_abi(variant, fixture=not selected),
            "scratchpad production/fixture source substitution",
        )
    print(f"PASS: user-phase images {positives} positive and {negatives} negative cases")


def ram_file_linked_controls(directory, *, scratchpad=False, scratchpad_fixture=False):
    """Mutate copied actual role artifacts, never the build's admitted inputs."""
    import kernel_stack as stack

    positives = negatives = 0
    with tempfile.TemporaryDirectory(prefix="aurora-ram-file-image-") as temporary:
        for role, service in (("clean", False), ("bounds", True)):
            source = directory / ("user-" + role)
            prefix = Path(temporary) / ("user-" + role)
            host = "__au_runtime_serve_exchange" if service else "__au_runtime_call"
            status_max = 1 if service else 2
            copied = scratchpad and not service

            def admit():
                return (
                    builder.scratchpad_user_stack(prefix)
                    if copied
                    else builder.ram_file_user_stack(
                        prefix,
                        service=service,
                        scratchpad_fixture=scratchpad_fixture if scratchpad else None,
                    )
                )

            def reset():
                for suffix in (".elf", ".bin", ".stack.json", ".abi.json"):
                    shutil.copyfile(source.with_suffix(suffix), prefix.with_suffix(suffix))
                if copied:
                    (prefix.parent / "objects").mkdir(exist_ok=True)
                    shutil.copyfile(directory / "objects/user-clean.o", prefix.parent / "objects/user-clean.o")

            def reject(mutate, label):
                nonlocal negatives
                reset()
                mutate()
                try:
                    admit()
                except (ValueError, TypeError, KeyError):
                    negatives += 1
                else:
                    raise RuntimeError("Invalid linked RAM-file image accepted: " + role + " " + label)

            def change_facts(mutate):
                path = prefix.with_suffix(".stack.json")
                document = json.loads(path.read_text())
                mutate(document["functions"])
                path.write_text(json.dumps(document))

            def change_symbol(name, mutate):
                path = prefix.with_suffix(".elf")
                image = stack.Elf(path)
                data = bytearray(path.read_bytes())
                found = []
                for section in image.sections:
                    if section[1] != 2:
                        continue
                    strings = image.section_data(section[6])
                    for position in range(section[4], section[4] + section[5], section[9]):
                        offset = struct.unpack_from("<I", data, position)[0]
                        end = strings.find(b"\0", offset)
                        if strings[offset:end].decode() == name:
                            found.append(position)
                if len(found) != 1:
                    raise RuntimeError("Mutation lacks one exact linked symbol: " + name)
                mutate(data, found[0])
                path.write_bytes(data)

            def inject_import(name, *, undefined):
                # Extend only non-load metadata in the temporary ELF. This adds
                # an otherwise unused hidden symbol without deleting any code,
                # function, wrapper label, or compiler fact.
                path = prefix.with_suffix(".elf")
                image = stack.Elf(path)
                data = bytearray(path.read_bytes())
                tables = [(index, section) for index, section in enumerate(image.sections) if section[1] == 2]
                if len(tables) != 1:
                    raise RuntimeError("Import mutation requires one exact symbol table")
                index, table = tables[0]
                strings = image.section_data(table[6])
                string_data = strings + name.encode() + b"\0"
                symbols_data = image.section_data(index) + struct.pack(
                    "<IBBHQQ", len(strings), 0x10, 2, 0 if undefined else 1, 0, 0
                )
                string_offset = len(data)
                data.extend(string_data)
                symbol_offset = len(data)
                data.extend(symbols_data)
                section_offset = struct.unpack_from("<Q", data, 40)[0]
                struct.pack_into("<QQ", data, section_offset + table[6] * 64 + 24, string_offset, len(string_data))
                struct.pack_into("<QQ", data, section_offset + index * 64 + 24, symbol_offset, len(symbols_data))
                path.write_bytes(data)

            def change_instruction(address, value):
                # Keep linked ELF and installed bytes consistent so this tests
                # the handwritten instruction contract, not a stale-bin check.
                path = prefix.with_suffix(".elf")
                image = stack.Elf(path)
                data = bytearray(path.read_bytes())
                sections = [s for s in image.sections if s[1] == 1 and s[3] <= address < s[3] + s[5]]
                if len(sections) != 1:
                    raise RuntimeError("Mutation lacks one exact code section")
                section = sections[0]
                data[section[4] + address - section[3]] = value
                path.write_bytes(data)
                base = next(s.address for s in image.symbols if s.name == "aurora_program_entry")
                binary = bytearray(prefix.with_suffix(".bin").read_bytes())
                binary[address - base] = value
                prefix.with_suffix(".bin").write_bytes(binary)
                if copied:
                    # Mutate the temporary combined object as well, so exact
                    # wrapper/stub rejection is not merely object-byte mismatch.
                    object_path = prefix.parent / "objects/user-clean.o"
                    original = stack.Elf(object_path)
                    entry = next(s for s in original.symbols if s.name == "aurora_program_entry")
                    section = original.sections[entry.section]
                    payload = bytearray(object_path.read_bytes())
                    payload[section[4] + entry.address - section[3] + address - base] = value
                    object_path.write_bytes(payload)

            reset()
            admitted = admit()
            if copied and (
                admitted["peak_with_wrapper"] != admitted["peak"] + 240
                or admitted["fixed_regions"]
                != dict(argument=[-192, -96], result=[-96, -16], sentinel=[-16, 0], envelope=[-240, -192])
            ):
                raise RuntimeError("Copied Call changed independent fixed-stack accounting")
            positives += 1
            facts = json.loads(source.with_suffix(".stack.json").read_text())["functions"]
            callers = [name for name, fact in facts.items() if host in fact["calls"]]
            if not callers:
                raise RuntimeError("Linked control lacks a generated host caller")
            caller = callers[0]
            for field, value in (
                ("sysv_arguments", 2),
                ("sysv_arguments", 4),
                ("sysv_arguments", True),
                ("result_max", 0),
                ("result_max", status_max + 1),
                ("result_max", True),
            ):
                reject(
                    lambda: change_facts(
                        lambda rows: rows[caller]["service_abi"]["calls"][host].__setitem__(field, value)
                    ),
                    "register contract " + field,
                )
            reject(lambda: change_facts(lambda rows: rows[caller].pop("service_abi")), "missing register contract")
            reject(
                lambda: change_facts(lambda rows: rows.__setitem__("foreign_generated", copy.deepcopy(rows[caller]))),
                "foreign generated function fact",
            )
            reject(
                lambda: change_symbol("bad_entry", lambda data, at: data.__setitem__(at + 4, data[at + 4] | 2)),
                "unaccounted linked function",
            )
            reject(
                lambda: change_symbol(host, lambda data, at: struct.pack_into("<H", data, at + 6, 0)),
                "undefined foreign import",
            )
            reset()
            image = stack.Elf(prefix.with_suffix(".elf"))
            code, _ = stack.disassemble(image.path)
            stub = image.functions[host]
            base = next(s.address for s in image.symbols if s.name == "aurora_program_entry")
            reserve = "$0x10,%rsp" if service else "$0xc0,%rsp" if copied else "$0x30,%rsp"
            record = [
                row
                for address, row in code.items()
                if base <= address < stub.address and (row.op, row.args) == ("sub", reserve)
            ]
            if len(record) != 1:
                raise RuntimeError("Linked control lacks exact copied entry reservation")
            reject(
                lambda: change_instruction(record[0].next - 1, 32 if service else 64),
                "altered handwritten record reservation",
            )
            if copied:
                for foreign in ("__au_runtime_console_put", "__au_runtime_serve_exchange"):
                    for undefined in (False, True):
                        reject(lambda: inject_import(foreign, undefined=undefined), "hidden unused foreign import")
                abi = json.loads(source.with_suffix(".abi.json").read_text())
                entry = builder.scratchpad_call_entry_abi(abi)

                def change_abi(mutate):
                    path = prefix.with_suffix(".abi.json")
                    document = json.loads(path.read_text())
                    mutate(document)
                    path.write_text(json.dumps(document))

                reject(
                    lambda: change_abi(
                        lambda doc: doc["functions"].__setitem__(
                            "injected_unused_function",
                            dict(doc["functions"][entry], source_name="injected_unused_function"),
                        )
                    ),
                    "copied Call injected generic function fact",
                )
                for field, value in (
                    ("parameter_bytes", 88),
                    ("result", dict(bytes=80, kind="u64")),
                    ("borrowed_root_count", 1),
                    ("injected", 0),
                ):
                    reject(
                        lambda: change_abi(lambda doc: doc["functions"][entry].__setitem__(field, value)),
                        "copied Call exact entry " + field,
                    )
                for index in (0, 1):
                    for field, value in (("offset", 8), ("bytes", 16), ("kind", "pointer"), ("injected", 0)):
                        if index == 0 and field == "bytes":
                            value = 8
                        reject(
                            lambda: change_abi(
                                lambda doc: doc["functions"][entry]["parameters"][index].__setitem__(field, value)
                            ),
                            "copied Call parameter field " + field,
                        )
                for foreign in ("builtin::ConsoleSession", "builtin::ServeSession"):
                    reject(
                        lambda: change_abi(
                            lambda doc: doc["functions"][entry]["parameters"][0].__setitem__("type_name", foreign)
                        ),
                        "copied Call same-width nominal substitution",
                    )
                for symbol, record in abi["records"].items():
                    if record["source_name"] not in ("console::ScratchpadCommand", "console::ScratchpadResult"):
                        continue
                    for field, value in (("size", 88), ("alignment", True), ("reserved", 80.0), ("injected", 0)):
                        reject(
                            lambda: change_abi(lambda doc: doc["records"][symbol].__setitem__(field, value)),
                            "copied Call record " + field,
                        )
                    for index in range(len(record["fields"])):
                        for field, value in (
                            ("offset", 99),
                            ("bytes", 4),
                            ("array_length", True),
                            ("kind", "reference"),
                            ("injected", 0),
                        ):
                            reject(
                                lambda: change_abi(
                                    lambda doc: doc["records"][symbol]["fields"][index].__setitem__(field, value)
                                ),
                                "copied Call nested field " + field,
                            )
                for symbol, enum in abi["enums"].items():
                    if not enum["source_name"].startswith("console::Scratchpad"):
                        continue
                    # Only declarations referenced by transported records are
                    # required when the compiler prunes unused nominal records.
                    if enum["source_name"] not in ("console::ScratchpadOperation", "console::ScratchpadResultKind"):
                        continue
                    for case in enum["cases"]:
                        for value in (True, 0.0, 99):
                            reject(
                                lambda: change_abi(lambda doc: doc["enums"][symbol]["cases"].__setitem__(case, value)),
                                "copied Call enum ordinal",
                            )
                reject(
                    lambda: prefix.with_suffix(".abi.json").write_text(
                        '{"version":2,' + source.with_suffix(".abi.json").read_text()[1:]
                    ),
                    "copied Call duplicate ABI key",
                )
                reject(
                    lambda: change_facts(
                        lambda rows: rows[entry].__setitem__(
                            "service_abi",
                            dict(record=dict(parameters=[["builtin::ConsoleSession", 16]], result_bytes=8), calls={}),
                        )
                    ),
                    "copied Call invented Console service record",
                )
                reject(
                    lambda: change_facts(
                        lambda rows: rows[entry].__setitem__(
                            "copied_record", dict(parameter_bytes=[16, 80], result_bytes=80)
                        )
                    ),
                    "copied Call invented scalar-record shortcut",
                )
                for op, args, immediate_bytes, value in (
                    ("lea", "0x30(%rsp),%r11", 1, 0x38),
                    ("lea", "0x90(%rsp),%r10", 4, 0x30),
                    ("lea", "0x90(%rsp),%r10", 4, 0xA0),
                    ("mov", "%rax,0x30(%rsp)", 1, 0x40),
                    ("mov", "%rax,0x38(%rsp)", 1, 0x48),
                    ("sub", "$0xc0,%rsp", 4, 0xB0),
                    ("add", "$0xc0,%rsp", 4, 0xB0),
                    ("mov", "$0x1,%eax", 4, 2),
                    ("mov", "$0x1,%esi", 4, 2),
                ):
                    matches = [
                        row
                        for address, row in code.items()
                        if base <= address < stub.address and (row.op, row.args) == (op, args)
                    ]
                    if len(matches) != 1:
                        raise RuntimeError("Copied mutation lacks exact wrapper instruction " + op + " " + args)
                    reject(
                        lambda: change_instruction(matches[0].next - immediate_bytes, value),
                        "copied Call fixed pointer/prefix/reservation/restoration/marker",
                    )
                terminal = next(symbol.address for symbol in image.symbols if symbol.name == "aurora_program_return_pc")
                reject(
                    lambda: change_symbol(
                        "aurora_program_return_pc", lambda data, at: struct.pack_into("<Q", data, at + 8, terminal + 2)
                    ),
                    "copied Call shifted terminal PC",
                )
                for at in range(stub.address, stub.address + 3):
                    reject(lambda: change_instruction(at, 0x90), "copied Call wrong INT82/ret opcode")
            returned = "aurora_serve_return_pc" if service else "aurora_call_return_pc"
            reject(
                lambda: change_symbol(
                    returned,
                    lambda data, at: struct.pack_into("<Q", data, at + 8, stub.address + 1),
                ),
                "interior exchange continuation",
            )
    print(f"PASS: linked RAM-file role admission {positives} positive and {negatives} negative cases")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ram-file-build-dir", type=Path)
    parser.add_argument("--ram-scratchpad-build-dir", type=Path)
    parser.add_argument("--ram-scratchpad-fixture", action="store_true")
    args = parser.parse_args()
    if args.ram_scratchpad_fixture and not args.ram_scratchpad_build_dir:
        parser.error("--ram-scratchpad-fixture requires --ram-scratchpad-build-dir")
    main()
    if args.ram_file_build_dir:
        ram_file_linked_controls(args.ram_file_build_dir.resolve(strict=True))
    if args.ram_scratchpad_build_dir:
        ram_file_linked_controls(
            args.ram_scratchpad_build_dir.resolve(strict=True),
            scratchpad=True,
            scratchpad_fixture=args.ram_scratchpad_fixture,
        )
