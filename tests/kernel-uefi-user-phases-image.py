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


builder = load('user_phase_image_builder', ROOT / 'scripts/kernel-uefi-ipc-images.py')
fixture = load('user_phase_elf_fixture', ROOT / 'tests/kernel-uefi-user-image.py')
smoke = load('user_phase_transcript', ROOT / 'tests/kernel-uefi-user-phases-smoke.py')


def main():
    positives = negatives = 0

    def reject(action, label):
        nonlocal negatives
        try:
            action()
        except (ValueError, TypeError, KeyError):
            negatives += 1
        else:
            raise RuntimeError('Invalid user-phase image accepted: ' + label)

    for mode in ('user-phases', 'user-context', 'user-unknown'):
        metadata = dict(images={}, kernel=dict(drain_begin=100, drain_end=104,
                                               text_end=4096, forged_pc=0))
        for domain, name in enumerate(smoke.NAMES):
            base = builder.BASE + domain * 4096
            data, blob, symbols = fixture.fixture(base)
            symbols['aurora_user_main'] = base + 20
            if domain == 0 and mode == 'user-context':
                blob[2:8] = bytes.fromhex('48ff0c2475fa')
                symbols.update(aurora_budget_context_begin=base + 2,
                               aurora_budget_context_end=base + 8)
            if domain == 0 and mode == 'user-unknown':
                blob[10:12] = bytes.fromhex('0f0b')
                symbols['aurora_probe_pc'] = base + 10
            data[4096:] = blob

            def verify(elf, installed, names):
                found = builder.verify(elf, installed, base, names, dispatcher=True)
                return builder.service_metadata(found, installed, names, 10)

            metadata['images'][name] = verify(data, blob, symbols)
            positives += 1
            # Even an ELF and binary changed together cannot introduce a forged
            # retained return/fault instruction or a fake register-probe loop.
            sites = ['aurora_program_return_pc', '.Laurora_bounds_trap',
                     '.Laurora_overflow_trap', '.Laurora_division_zero_trap',
                     '.Laurora_shift_count_trap']
            for symbol in sites:
                changed = blob.copy()
                changed[symbols[symbol] - base] = 0x90
                elf = data.copy()
                elf[4096:] = changed
                reject(lambda: verify(elf, changed, symbols), 'retained opcode ' + symbol)
                forged = dict(symbols)
                forged[symbol] = base + 4096
                reject(lambda: verify(data, blob, forged), 'foreign exact site ' + symbol)
            forged = dict(symbols, aurora_user_main=base + 30)
            reject(lambda: verify(data, blob, forged), 'compiled function overlaps fault helpers')
            changed = blob.copy()
            changed[0] ^= 1
            reject(lambda: verify(data, changed, symbols), 'installed bytes differ from linked RX')
            if domain == 0 and mode == 'user-context':
                for offset in range(2, 8):
                    changed = blob.copy()
                    changed[offset] ^= 1
                    elf = data.copy()
                    elf[4096:] = changed
                    reject(lambda: verify(elf, changed, symbols), 'context loop byte')
            if domain == 0 and mode == 'user-unknown':
                forged = dict(symbols, aurora_probe_pc=symbols['.Laurora_bounds_trap'])
                reject(lambda: verify(data, blob, forged), 'unknown UD2 aliases retained bounds')
                changed = blob.copy()
                changed[10] = 0x90
                elf = data.copy()
                elf[4096:] = changed
                reject(lambda: verify(elf, changed, symbols), 'unknown UD2 exact opcode')
        smoke.metadata_valid(metadata, mode)
        positives += 1
        for source, target in (('clean', 'bounds'), ('bounds', 'peer'), ('peer', 'clean')):
            changed = copy.deepcopy(metadata)
            changed['images'][target] = changed['images'][source]
            reject(lambda: smoke.metadata_valid(changed, mode), 'cross-domain metadata authority')
        if mode == 'user-context':
            changed = copy.deepcopy(metadata)
            changed['images']['clean']['context_begin'] = changed['images']['clean']['context_end'] = 0
            reject(lambda: smoke.metadata_valid(changed, mode), 'lost client register probe')
        if mode == 'user-unknown':
            changed = copy.deepcopy(metadata)
            changed['images']['clean']['probe_pc'] = 0
            reject(lambda: smoke.metadata_valid(changed, mode), 'lost unknown-site probe')
    print(f'PASS: user-phase images {positives} positive and {negatives} negative cases')


if __name__ == '__main__':
    main()
