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

    for mode in ("user-phases", "user-context", "user-unknown"):
        metadata = dict(images={}, kernel=dict(drain_begin=100, drain_end=104, text_end=4096, forged_pc=0))
        for domain, name in enumerate(smoke.NAMES):
            base = builder.BASE + domain * 16384
            data, blob, symbols = fixture.fixture(base)
            symbols["aurora_user_main"] = base + 20
            if domain == 0 and mode == "user-context":
                blob[2:8] = bytes.fromhex("48ff0c2475fa")
                symbols.update(aurora_budget_context_begin=base + 2, aurora_budget_context_end=base + 8)
            if domain == 0 and mode == "user-unknown":
                blob[10:12] = bytes.fromhex("0f0b")
                symbols["aurora_probe_pc"] = base + 10
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
            if domain == 0 and mode == "user-context":
                for offset in range(2, 8):
                    changed = blob.copy()
                    changed[offset] ^= 1
                    elf = data.copy()
                    elf[4096:] = changed
                    reject(lambda: verify(elf, changed, symbols), "context loop byte")
            if domain == 0 and mode == "user-unknown":
                forged = dict(symbols, aurora_probe_pc=symbols[".Laurora_bounds_trap"])
                reject(lambda: verify(data, blob, forged), "unknown UD2 aliases retained bounds")
                changed = blob.copy()
                changed[10] = 0x90
                elf = data.copy()
                elf[4096:] = changed
                reject(lambda: verify(elf, changed, symbols), "unknown UD2 exact opcode")
        smoke.metadata_valid(metadata, mode)
        positives += 1
        for source, target in (("clean", "bounds"), ("bounds", "peer"), ("peer", "clean")):
            changed = copy.deepcopy(metadata)
            changed["images"][target] = changed["images"][source]
            reject(lambda: smoke.metadata_valid(changed, mode), "cross-domain metadata authority")
        if mode == "user-context":
            changed = copy.deepcopy(metadata)
            changed["images"]["clean"]["context_begin"] = changed["images"]["clean"]["context_end"] = 0
            reject(lambda: smoke.metadata_valid(changed, mode), "lost client register probe")
        if mode == "user-unknown":
            changed = copy.deepcopy(metadata)
            changed["images"]["clean"]["probe_pc"] = 0
            reject(lambda: smoke.metadata_valid(changed, mode), "lost unknown-site probe")
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
    print(f"PASS: user-phase images {positives} positive and {negatives} negative cases")


def ram_file_linked_controls(directory):
    """Mutate copied actual role artifacts, never the build's admitted inputs."""
    import kernel_stack as stack

    positives = negatives = 0
    with tempfile.TemporaryDirectory(prefix="aurora-ram-file-image-") as temporary:
        for role, service in (("clean", False), ("bounds", True)):
            source = directory / ("user-" + role)
            prefix = Path(temporary) / ("user-" + role)
            host = "__au_runtime_serve_exchange" if service else "__au_runtime_call"
            status_max = 1 if service else 2

            def reset():
                for suffix in (".elf", ".bin", ".stack.json", ".abi.json"):
                    shutil.copyfile(source.with_suffix(suffix), prefix.with_suffix(suffix))

            def reject(mutate, label):
                nonlocal negatives
                reset()
                mutate()
                try:
                    builder.ram_file_user_stack(prefix, service=service)
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

            reset()
            builder.ram_file_user_stack(prefix, service=service)
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
            reserve = "$0x10,%rsp" if service else "$0x30,%rsp"
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
    args = parser.parse_args()
    main()
    if args.ram_file_build_dir:
        ram_file_linked_controls(args.ram_file_build_dir.resolve(strict=True))
