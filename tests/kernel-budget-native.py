#!/usr/bin/env python3
"""Full-width native Aurora policy oracle and independent transport observations."""
from pathlib import Path
import argparse
import hashlib
import itertools
import json
import os
import random
import shutil
import struct
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
ACCEPTED = '8d4099fe52a19307a266a6cbe5191203307462877cc94c7b6f3dae78f817c631'
MAX = (1 << 64) - 1


def need(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def allocated():
    return sum(p.stat().st_blocks * 512 for p in ROOT.rglob('*') if p.is_file())


def guard(cap):
    need(allocated() < cap * 1024 * 1024, 'Candidate allocation cap reached')
    need(shutil.disk_usage(ROOT).free >= 1024 ** 3, 'One GiB free-space floor reached')


def oracle(initial, remaining, used):
    # Independent set membership, with unbounded host arithmetic: a state is the
    # unique position of its used count in a finite interrupt sequence.
    if initial not in range(1, 129) or used not in range(initial):
        return 0
    if remaining != initial - used:
        return 0
    next_used = used + 1
    next_remaining = initial - next_used
    return (2 if next_used == initial else 1) * 65536 + next_used * 256 + next_remaining


def decoder_oracle(encoded, initial, remaining, used):
    if encoded >= 1 << 18 or initial not in range(1, 129):
        return 0
    action, payload = divmod(encoded, 65536)
    after_used, after_remaining = divmod(payload, 256)
    allowed = {(1 if left else 2, left, initial - left) for left in range(initial)}
    if (action, after_remaining, after_used) not in allowed:
        return 0
    if after_remaining >= remaining or after_used <= used:
        return 0
    return encoded


def run(command, folder, name, **kwargs):
    started = time.time()
    result = subprocess.run(command, cwd=ROOT, timeout=120, capture_output=True, **kwargs)
    (folder / (name + '.stdout')).write_bytes(result.stdout)
    (folder / (name + '.stderr')).write_bytes(result.stderr)
    (folder / (name + '.json')).write_text(json.dumps(dict(command=list(map(str, command)),
        returncode=result.returncode, elapsed_seconds=time.time() - started), indent=2) + '\n')
    need(result.returncode == 0, name + ' failed; original outputs retained')
    return result


def vector_gate(binary, out, name, vectors, model, cap, decode=False):
    guard(cap)
    inputs = out / (name + '.inputs.bin')
    expected = out / (name + '.expected.bin')
    width = 4 if decode else 3
    count = 0
    with inputs.open('wb') as source, expected.open('wb') as want:
        for values in vectors:
            source.write(struct.pack('<' + 'Q' * width, *values))
            want.write(struct.pack('<Q', model(*values)))
            count += 1
            if count % 16384 == 0:
                guard(cap)
    guard(cap)
    observed = out / (name + '.observed.bin')
    command = [str(binary)] + (['decode'] if decode else [])
    started = time.time()
    with inputs.open('rb') as source, observed.open('wb') as actual, (out / (name + '.stderr')).open('wb') as errors:
        result = subprocess.run(command, stdin=source, stdout=actual, stderr=errors, timeout=120, cwd=ROOT)
    receipt = dict(command=command, returncode=result.returncode, cases=count,
        elapsed_seconds=time.time() - started, files={p.name: dict(bytes=p.stat().st_size, sha256=sha(p))
        for p in (inputs, expected, observed)})
    (out / (name + '.json')).write_text(json.dumps(receipt, indent=2) + '\n')
    need(result.returncode == 0, name + ' did not exit normally')
    need(observed.read_bytes() == expected.read_bytes(), name + ' native observations differ')
    guard(cap)
    return count


def policy_vectors():
    for initial in range(1, 129):
        for used in range(initial):
            yield initial, initial - used, used
    values = (0, 1, 2, 3, 63, 64, 127, 128, 129, 255, 256, (1 << 63) - 1, 1 << 63, MAX)
    yield from itertools.product(values, repeat=3)
    for initial in range(1, 129):
        for remaining in range(0, 131):
            for offset in (-2, -1, 0, 1, 2):
                used = initial - remaining + offset
                if 0 <= used <= MAX:
                    yield initial, remaining, used
            for used in (1 << 63, MAX):
                yield initial, remaining, used
        for remaining in (1 << 63, MAX):
            for used in (0, 1, initial - 1, initial, MAX):
                yield initial, remaining, used
    rng = random.Random(20261004)
    for _ in range(16384):
        yield rng.getrandbits(64), rng.getrandbits(64), rng.getrandbits(64)


def decoder_vectors():
    # Exhaust all 18-bit encodings against the only possible conserved total.
    for encoded in range(1 << 18):
        total = (encoded & 255) + ((encoded >> 8) & 255)
        yield encoded, total, total, 0
    # Every valid output and every one-bit mutation at every valid source state.
    for initial in range(1, 129):
        for used in range(initial):
            remaining = initial - used
            word = oracle(initial, remaining, used)
            yield word, initial, remaining, used
            for bit in range(64):
                yield word ^ (1 << bit), initial, remaining, used
            yield word, initial, remaining - 1, used
            yield word, initial, remaining, used + 1
    for value in (0, 129, 255, 1 << 63, MAX):
        yield oracle(3, 3, 0), value, 3, 0


def rejection_gate(compiler, out):
    bodies = {
        'private_field': ('import kernel.interrupt_budget;\nauto answer() -> u64 { const kernel::TickDecision d = kernel::interrupt_tick(3u64, 3u64, 0u64); return d.remaining_count; }', 'private class field is inaccessible'),
        'signed_input': ('import kernel.interrupt_budget;\nauto answer() -> u64 { const kernel::TickDecision d = kernel::interrupt_tick(3, 3u64, 0u64); return d.remaining(); }', 'expected u64, got i64'),
        'numeric_action': ('import kernel.interrupt_budget;\nauto answer() -> bool { const kernel::TickDecision d = kernel::interrupt_tick(3u64, 3u64, 0u64); return d.action() == 1u64; }', 'expected kernel::TickAction, got u64'),
        'missing_import': ('auto answer() -> u64 { const kernel::TickDecision d = kernel::interrupt_tick(3u64, 3u64, 0u64); return d.remaining(); }', "unknown function 'kernel::interrupt_tick'"),
        'copied_parameter': ('import kernel.interrupt_budget;\nauto change(kernel::TickDecision d) -> u64 { d = kernel::TickDecision(kernel::TickAction::rejected, 0u64, 0u64); return d.remaining(); }', 'assignment requires a mutable scalar local'),
    }
    receipts = []
    for name, (body, diagnostic) in bodies.items():
        source = out / (name + '.au')
        source.write_text('module probe;\n' + body + '\n')
        for existing in (False, True):
            label = name + ('-existing' if existing else '-absent')
            output = out / (label + '.s')
            sentinel = b'prior complete artifact\n'
            if existing:
                output.write_bytes(sentinel)
            command = [str(compiler), '--module-root', str(ROOT / 'kernel/policies'), str(source), '-o', str(output)]
            result = subprocess.run(command, cwd=ROOT, timeout=30, capture_output=True)
            (out / (label + '.stdout')).write_bytes(result.stdout)
            (out / (label + '.stderr')).write_bytes(result.stderr)
            receipt = dict(command=command, returncode=result.returncode, expected_diagnostic=diagnostic,
                source_sha256=sha(source), output_exists=output.exists())
            receipts.append(receipt)
            (out / 'rejections.json').write_text(json.dumps(receipts, indent=2) + '\n')
            need(result.returncode == 1 and diagnostic.encode() in result.stderr, label + ' wrong rejection')
            need(output.read_bytes() == sentinel if existing else not output.exists(), label + ' output changed')
    return len(receipts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--compiler', default=str(ROOT / 'build/aurorac'))
    parser.add_argument('--compiler-sha256', default=ACCEPTED)
    parser.add_argument('--output')
    parser.add_argument('--candidate-cap-mib', type=int, default=128)
    args = parser.parse_args()
    compiler = Path(args.compiler).resolve()
    need(len(args.compiler_sha256) == 64 and all(c in '0123456789abcdef' for c in args.compiler_sha256), 'Invalid compiler pin')
    need(sha(compiler) == args.compiler_sha256, 'Compiler pin mismatch')
    guard(args.candidate_cap_mib)
    out = Path(args.output).resolve() if args.output else ROOT / 'build/kernel-budget-native' / str(time.time_ns())
    need(not out.exists(), 'Use a fresh output directory; never overwrite failed evidence')
    out.mkdir(parents=True)
    pins = {str(p.relative_to(ROOT)): sha(p) for p in
        (ROOT / 'kernel/policies/kernel/interrupt_budget.au', ROOT / 'examples/kernel.au',
         ROOT / 'kernel/uefi/budget-transport.hpp', Path(__file__), ROOT / 'tests/kernel-budget-native.cpp')}
    assembly, binary = out / 'language.s', out / 'observe'
    run([str(compiler), '--module-root', 'kernel/policies', 'examples/kernel.au', '-o', str(assembly)], out, 'compile')
    run(['g++', '-std=c++23', '-O2', '-Wall', '-Wextra', '-Wpedantic', '-Werror', '-no-pie',
         'tests/kernel-budget-native.cpp', str(assembly), '-o', str(binary)], out, 'link')
    counts = dict(policy=vector_gate(binary, out, 'policy', policy_vectors(), oracle, args.candidate_cap_mib),
        decoder=vector_gate(binary, out, 'decoder', decoder_vectors(), decoder_oracle, args.candidate_cap_mib, True))
    counts['rejections'] = rejection_gate(compiler, out)
    successful_words = {oracle(initial, initial - used, used) for initial in range(1, 129) for used in range(initial)}
    need(0 not in successful_words and len(successful_words) == 8256, 'Nonunique successful encoding')
    run(['objdump', '-drwC', str(binary)], out, 'disassembly')
    run(['readelf', '-sW', str(binary)], out, 'symbols')
    need(sha(compiler) == args.compiler_sha256, 'Compiler changed during test')
    need(pins == {name: sha(ROOT / name) for name in pins}, 'Source changed during test')
    guard(args.candidate_cap_mib)
    summary = dict(status='passed', compiler_sha256=sha(compiler), source_pins=pins, cases=counts,
        candidate_allocated_bytes=allocated(), free_bytes=shutil.disk_usage(ROOT).free,
        limits='Hosted observation only; not a QEMU, source-safety proof, or kernel acceptance result.')
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
