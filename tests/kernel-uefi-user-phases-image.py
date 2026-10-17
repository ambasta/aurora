#!/usr/bin/env python3
"""Connect three-domain user metadata to exact ELF bytes and probe ownership."""

from pathlib import Path
import copy
import importlib.util

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
            base = builder.BASE + domain * 4096
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
    print(f"PASS: user-phase images {positives} positive and {negatives} negative cases")


if __name__ == "__main__":
    main()
