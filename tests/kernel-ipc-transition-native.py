#!/usr/bin/env python3
"""Bounded genuine IPC producer, classified decoder, copy and hostile adapter gates.

Execution requires separate admission and one explicit pin or checked developer receipt.
Fatal ASan/UBSan disables LeakSanitizer for the verified executor ptrace restriction.
--check-cap-only is compiler-free configuration validation, never acceptance.
"""
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
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from compiler_contract import add_identity_arguments, resolve_identity, validate_identity_selection
MAX = (1 << 64) - 1
# Independent literal relation: operation -> phase -> state*2+scrubbed.
# No production branch, enum, invariant table or decoder is used as an oracle.
TABLE = (
    ((1,1,1,1,1,1,1,1,1,1,1,1),
     (0x010102,0x010102,1,1,1,1,1,1,1,1,1,1),
     (1,1,1,1,1,1,1,1,1,1,1,1),
     (1,1,1,1,1,1,1,1,1,1,1,1)),
    ((1,1,1,1,1,1,1,1,1,1,1,1),
     (1,1,1,1,1,1,1,1,1,1,1,1),
     (1,1,0x020202,0x020202,1,1,1,1,1,1,1,1),
     (1,1,1,1,1,1,1,1,1,1,1,1)),
    ((1,1,1,1,1,1,1,1,1,1,1,1),
     (1,1,1,1,1,1,1,1,1,1,1,1),
     (1,1,1,1,0x030302,0x030302,1,1,1,1,1,1),
     (1,1,1,1,1,1,1,1,1,1,1,1)),
    ((1,1,1,1,1,1,1,1,1,1,1,1),
     (1,1,1,1,1,1,1,1,1,1,1,1),
     (1,1,1,1,1,1,1,1,1,1,1,1),
     (1,1,1,1,1,1,0x040502,0x040502,0x050502,0x050502,1,1)),
    ((1,1,0x060402,0x060402,0x060402,0x060402,1,1,1,1,1,1),
     (1,1,1,1,1,1,1,1,1,1,1,1),
     (1,1,1,1,1,1,1,1,1,1,1,1),
     (1,1,1,1,1,1,1,1,1,1,1,1)),
    ((1,1,1,1,1,1,1,1,1,1,1,0x070002),
     (1,1,1,1,1,1,1,1,1,1,1,1),
     (1,1,1,1,1,1,1,1,1,1,1,1),
     (1,1,1,1,1,1,1,1,1,1,1,1)),
)
VALID_WORDS = (1, 0x010102, 0x020202, 0x030302, 0x040502, 0x050502, 0x060402, 0x070002)
EDGES = (0,1,2,3,4,5,6,7,8,15,127,128,255,256,65535,65536,
         (1 << 32) - 1, 1 << 32, (1 << 63) - 1, 1 << 63, MAX)


def need(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def candidate_cap(mib):
    need(type(mib) is int and 128 <= mib <= 1024,
         'candidate cap must be an integer between 128 and 1024 MiB; increases require explicit aggregate admission')
    return mib << 20


def cap_self_test():
    for mib in (128, 512, 513, 1023, 1024):
        need(candidate_cap(mib) == mib << 20, 'candidate cap boundary conversion')
    for mib in (-1, 0, 127, 1025, 1 << 30, True, 512.0, '1024', None):
        try:
            candidate_cap(mib)
        except RuntimeError:
            continue
        raise RuntimeError('invalid candidate cap accepted')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def allocated():
    return sum(path.stat().st_blocks * 512 for path in ROOT.rglob('*') if path.is_file())


def guard(cap):
    need(allocated() < candidate_cap(cap), 'Candidate allocation cap reached')
    need(shutil.disk_usage(ROOT).free >= 1024 ** 3, 'One GiB free-space floor reached')


def contexts():
    return itertools.product(range(6), range(4), range(6), range(2))


def oracle(operation, phase, state, scrubbed):
    if operation > 5 or phase > 3 or state > 5 or scrubbed > 1:
        return 0
    return TABLE[operation][phase][state * 2 + scrubbed]


def decoder_oracle(word, operation, phase, state, scrubbed):
    genuine = oracle(operation, phase, state, scrubbed)
    if genuine == 0:
        return (0, 0, 0)
    if word == 1:
        return (1, 0, 0)
    if genuine != 1 and word == genuine:
        return (2, (genuine >> 8) & 255, (genuine >> 16) & 255)
    return (0, 0, 0)


def policy_vectors():
    yield from contexts()
    # Every raw field independently, then simultaneous invalid fields.
    for values in contexts():
        for field in range(4):
            for value in EDGES:
                changed = list(values); changed[field] = value
                yield tuple(changed)
            for bit in range(64):
                changed = list(values); changed[field] ^= 1 << bit
                yield tuple(changed)
    for value in EDGES:
        yield (value,) * 4
    rng = random.Random(202610051)
    for _ in range(16384):
        yield tuple(rng.getrandbits(64) for _ in range(4))


def decoder_vectors():
    # Exactly 288 * 4 * 8 * 8 = 73,728 compact classified observations.
    for values in contexts():
        for action, state, effect in itertools.product(range(4), range(8), range(8)):
            yield (action | (state << 8) | (effect << 16), *values)
    for values in contexts():
        for word in VALID_WORDS:
            for bit in range(64):
                yield (word ^ (1 << bit), *values)
            # Full byte boundaries, field overflow and upper reserved bits.
            for shift in (0, 8, 16, 24, 32, 56):
                for edge in (0, 1, 2, 3, 7, 8, 127, 128, 254, 255, 256):
                    yield ((word | (edge << shift)) & MAX, *values)
        for word in EDGES:
            yield (word, *values)
    # Invalid ORIGINAL contexts must reject even refusal/plausible success.
    for field, limit in enumerate((5, 3, 5, 1)):
        for value in EDGES:
            if value <= limit:
                continue
            for base in ((0,1,0,1), (1,2,1,0), (2,2,2,1), (3,3,3,0),
                         (3,3,4,1), (4,0,1,0), (4,0,2,1), (5,0,5,1)):
                changed = list(base); changed[field] = value
                for word in (0, *VALID_WORDS, 1 << 63, MAX):
                    yield (word, *changed)
    rng = random.Random(202610052)
    valid = tuple(contexts())
    for iteration in range(16384):
        values = valid[iteration % len(valid)] if iteration % 2 else tuple(rng.getrandbits(64) for _ in range(4))
        yield (rng.getrandbits(64), *values)


def run(command, folder, name, cap, timeout=120, expect=0):
    guard(cap)
    started = time.time()
    environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
                       UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    try:
        result = subprocess.run(command, cwd=ROOT, timeout=timeout, capture_output=True, env=environment)
    except subprocess.TimeoutExpired as error:
        (folder / (name + '.stdout')).write_bytes(error.stdout or b'')
        (folder / (name + '.stderr')).write_bytes(error.stderr or b'')
        (folder / (name + '.json')).write_text(json.dumps(dict(command=list(map(str, command)), timeout=True,
            elapsed_seconds=time.time() - started), indent=2) + '\n')
        raise
    (folder / (name + '.stdout')).write_bytes(result.stdout)
    (folder / (name + '.stderr')).write_bytes(result.stderr)
    (folder / (name + '.json')).write_text(json.dumps(dict(command=list(map(str, command)),
        returncode=result.returncode, elapsed_seconds=time.time() - started), indent=2) + '\n')
    need(result.returncode == expect, name + ' failed; original outputs retained')
    guard(cap)
    return result


def vector_gate(binary, out, label, vectors, model, cap, decode=False):
    inputs, expected, observed = (out / (label + suffix) for suffix in ('.inputs.bin', '.expected.bin', '.observed.bin'))
    count = 0
    with inputs.open('wb') as source, expected.open('wb') as want:
        for values in vectors:
            source.write(struct.pack('<' + 'Q' * len(values), *values))
            result = model(*values)
            want.write(struct.pack('<QQQ', *result) if decode else struct.pack('<Q', result))
            count += 1
            if count % 16384 == 0:
                guard(cap)
    command = [str(binary)] + (['decode'] if decode else [])
    started = time.time()
    with inputs.open('rb') as source, observed.open('wb') as actual, (out / (label + '.stderr')).open('wb') as errors:
        try:
            result = subprocess.run(command, stdin=source, stdout=actual, stderr=errors, timeout=120, cwd=ROOT,
                env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1',
                         UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1'))
        except subprocess.TimeoutExpired:
            (out / (label + '.json')).write_text(json.dumps(dict(command=command, cases=count, timeout=True,
                elapsed_seconds=time.time() - started), indent=2) + '\n')
            raise
    receipt = dict(command=command, returncode=result.returncode, cases=count,
        elapsed_seconds=time.time() - started, files={p.name: dict(bytes=p.stat().st_size, sha256=sha(p)) for p in (inputs, expected, observed)})
    (out / (label + '.json')).write_text(json.dumps(receipt, indent=2) + '\n')
    need(result.returncode == 0, label + ' failed')
    need(observed.read_bytes() == expected.read_bytes(), label + ' native observations differ')
    guard(cap)
    return count


def rejection_gate(compiler, out, cap):
    prefix = 'const kernel::TransactionSnapshot s = kernel::TransactionSnapshot(1u64, 0u64, 1u64); '
    decision = prefix + 'const kernel::TransactionDecision d = kernel::transaction_transition(0u64, s); '
    bodies = {
        'snapshot_private': ('auto answer() -> u64 { ' + prefix + 'return s.phase_value; }', 'private class field'),
        'decision_private': ('auto answer() -> u64 { ' + decision + 'return d.following_state; }', 'private class field'),
        'signed_operation': ('auto answer() -> u64 { ' + prefix + 'const kernel::TransactionDecision d = kernel::transaction_transition(0, s); return d.next(); }', 'expected u64, got i64'),
        'signed_phase': ('auto answer() -> u64 { const kernel::TransactionSnapshot s = kernel::TransactionSnapshot(1, 0u64, 1u64); return s.phase(); }', 'expected u64, got i64'),
        'signed_state': ('auto answer() -> u64 { const kernel::TransactionSnapshot s = kernel::TransactionSnapshot(1u64, 0, 1u64); return s.state(); }', 'expected u64, got i64'),
        'bool_scrubbed': ('auto answer() -> u64 { const kernel::TransactionSnapshot s = kernel::TransactionSnapshot(1u64, 0u64, true); return s.scrubbed(); }', 'expected u64, got bool'),
        'numeric_action': ('auto answer() -> bool { ' + decision + 'return d.action() == 2u64; }', 'expected kernel::TransactionAction, got u64'),
        'numeric_effect': ('auto answer() -> bool { ' + decision + 'return d.effect() == 1u64; }', 'expected kernel::TransactionEffect, got u64'),
        'mixed_enums': ('auto answer() -> bool { ' + decision + 'return d.action() == d.effect(); }', 'expected kernel::TransactionAction, got kernel::TransactionEffect'),
        'snapshot_parameter_field': ('auto change(kernel::TransactionSnapshot s) -> u64 { s.phase_value = 0u64; return s.phase(); }', 'field assignment requires a mutable class local'),
        'decision_parameter_field': ('auto change(kernel::TransactionDecision d) -> u64 { d.following_state = 0u64; return d.next(); }', 'field assignment requires a mutable class local'),
        'snapshot_const_field': ('auto answer() -> u64 { ' + prefix + 's.phase_value = 0u64; return s.phase(); }', 'field assignment requires a mutable class local'),
        'decision_const_field': ('auto answer() -> u64 { ' + decision + 'd.following_state = 0u64; return d.next(); }', 'field assignment requires a mutable class local'),
        'readonly_snapshot': ('auto change(kernel::TransactionSnapshot s) -> u64 { const kernel::TransactionSnapshot other = kernel::TransactionSnapshot(0u64, 0u64, 0u64); s = other; return s.phase(); }', 'assignment requires a mutable scalar local'),
        'readonly_decision': ('auto change(kernel::TransactionDecision d) -> u64 { const kernel::TransactionDecision other = kernel::TransactionDecision(kernel::TransactionAction::refused, 0u64, kernel::TransactionEffect::none); d = other; return d.next(); }', 'assignment requires a mutable scalar local'),
        'nominal_snapshot': ('auto answer() -> u64 { ' + decision + 'const kernel::TransactionDecision other = kernel::transaction_transition(0u64, d); return other.next(); }', 'expected kernel::TransactionSnapshot'),
    }
    receipts = []
    for name, (body, diagnostic) in bodies.items():
        source = out / (name + '.au')
        source.write_text('module probe;\nimport kernel.ipc_transition;\n' + body + '\n')
        for existing in (False, True):
            label = name + ('-existing' if existing else '-absent')
            output = out / (label + '.s')
            sentinel = b'prior complete artifact\n'
            if existing:
                output.write_bytes(sentinel)
            command = [str(compiler), '--module-root', str(ROOT / 'kernel/policies'), str(source), '-o', str(output)]
            result = run(command, out, label, cap, timeout=30, expect=1)
            receipts.append(dict(command=command, returncode=result.returncode, expected_diagnostic=diagnostic,
                source_sha256=sha(source), output_exists=output.exists()))
            (out / 'rejections.json').write_text(json.dumps(receipts, indent=2) + '\n')
            need(diagnostic.encode() in result.stderr, label + ' wrong rejection')
            need(output.read_bytes() == sentinel if existing else not output.exists(), label + ' output changed')
    return len(receipts)


def symbol_map(data):
    return {fields[0]: tuple(fields[1:]) for line in data.decode().splitlines() if (fields := line.split())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--compiler', default=str(ROOT / 'build/aurorac'))
    add_identity_arguments(parser)
    parser.add_argument('--output')
    parser.add_argument('--candidate-cap-mib', type=int, default=128, help='whole-candidate cap 128..1024 MiB; increases require explicit aggregate admission')
    parser.add_argument('--check-cap-only', action='store_true', help='compiler-free configuration check; no acceptance receipt')
    parser.add_argument('--sanitize', action='store_true', default=os.environ.get('SANITIZE') == '1', help='fatal hosted ASan/UBSan; generated Aurora assembly remains uninstrumented')
    args = parser.parse_args()
    validate_identity_selection(args, preflight=args.check_cap_only)
    cap_bytes = candidate_cap(args.candidate_cap_mib)
    cap_self_test()
    if args.check_cap_only:
        print(json.dumps(dict(status='configuration-only', native_executed=False,
            candidate_cap_mib=args.candidate_cap_mib, cap_bytes=cap_bytes,
            focused_default_mib=128, maximum_cap_mib=1024), sort_keys=True))
        return
    compiler = Path(args.compiler).resolve(strict=True)
    identity = resolve_identity(args, compiler, ROOT)
    guard(args.candidate_cap_mib)
    out = Path(args.output).resolve() if args.output else ROOT / 'build/kernel-ipc-transition-native' / str(time.time_ns())
    need(out.is_relative_to(ROOT), 'Output must remain inside the bounded candidate')
    need(not out.exists(), 'Use a fresh output directory; never overwrite failed evidence')
    out.mkdir(parents=True)
    members = ('kernel/policies/kernel/ipc_transition.au', 'examples/kernel.au', 'kernel/ipc-transition-transport.hpp',
               'kernel/ipc-policy.hpp', 'kernel/dispatch-policy.hpp', 'kernel/domain-policy.hpp',
               'kernel/round-robin-transport.hpp', 'tests/kernel-ipc-transition-native.cpp',
               'tests/kernel-ipc-transition-native.py', 'tests/kernel-ipc-transition-adapter.cpp',
               'tests/kernel-programs/ipc-transition-copy.au', 'tests/kernel-ipc-transition-copy.cpp')
    # Pin the entire imported policy graph, not just the tested module.
    members = tuple(sorted(set(members) | {str(path.relative_to(ROOT)) for path in (ROOT / 'kernel/policies').rglob('*.au')}))
    pins = {name: sha(ROOT / name) for name in members}
    finite = [oracle(*values) for values in contexts()]
    need(len(finite) == 288 and finite.count(1) == 273 and sum(word > 1 for word in finite) == 15, 'Literal relation cardinality changed')
    (out / 'inputs.json').write_text(json.dumps(dict(compiler_identity=identity.record(), compiler_sha256=identity.sha256, source_pins=pins,
        candidate_cap_mib=args.candidate_cap_mib, sanitize=args.sanitize), indent=2) + '\n')
    assembly, obj, binary = out / 'language.s', out / 'language.o', out / 'observe'
    cap = args.candidate_cap_mib
    flags = ['g++', '-std=c++23', '-O1' if args.sanitize else '-O2', '-Wall', '-Wextra', '-Wpedantic', '-Werror', '-no-pie']
    if args.sanitize:
        flags += ['-g', '-fno-omit-frame-pointer', '-fsanitize=address,undefined', '-fno-sanitize-recover=all']
    run([str(compiler), '--module-root', 'kernel/policies', 'examples/kernel.au', '-o', str(assembly)], out, 'compile', cap)
    run(['g++', '-c', str(assembly), '-o', str(obj)], out, 'assemble', cap)
    run(flags + ['tests/kernel-ipc-transition-native.cpp', str(obj), '-o', str(binary)], out, 'link', cap)
    counts = dict(finite_contexts=288, finite_accepted=15, finite_refused=273, decoder_compact=73728,
        policy=vector_gate(binary, out, 'policy', policy_vectors(), oracle, cap),
        decoder=vector_gate(binary, out, 'decoder', decoder_vectors(), decoder_oracle, cap, True))
    counts['rejections'] = rejection_gate(compiler, out, cap)
    copy_assembly, copy_binary = out / 'copy.s', out / 'copy'
    run([str(compiler), '--module-root', 'kernel/policies', 'tests/kernel-programs/ipc-transition-copy.au', '-o', str(copy_assembly)], out, 'copy-compile', cap)
    run(flags + ['tests/kernel-ipc-transition-copy.cpp', str(copy_assembly), '-o', str(copy_binary)], out, 'copy-link', cap)
    run([str(copy_binary)], out, 'copy-observe', cap)
    counts['copy_repetitions'] = 4096
    substituted, adapter = out / 'adapter-language.o', out / 'adapter'
    old, new = 'aurora_kernel_ipc_transition', 'aurora_kernel_ipc_transition_real'
    before = symbol_map(run(['nm', '--defined-only', '--format=posix', str(obj)], out, 'root-symbols', cap).stdout)
    need(old in before and new not in before and 'aurora_kernel_round_robin_next' in before, 'Expected genuine producer symbols missing')
    run(['objcopy', '--redefine-sym', old + '=' + new, str(obj), str(substituted)], out, 'rename-only-ipc', cap)
    after = symbol_map(run(['nm', '--defined-only', '--format=posix', str(substituted)], out, 'adapter-root-symbols', cap).stdout)
    renamed = dict(before); renamed[new] = renamed.pop(old)
    need(after == renamed, 'Only IPC producer may be renamed; round-robin and all other symbols must remain genuine')
    run(flags + ['tests/kernel-ipc-transition-adapter.cpp', str(substituted), '-o', str(adapter)], out, 'adapter-link', cap)
    run([str(adapter)], out, 'adapter-observe', cap)
    for name, artifact in (('native', binary), ('adapter', adapter), ('copy', copy_binary)):
        run(['objdump', '-drwC', str(artifact)], out, name + '-disassembly', cap)
        run(['readelf', '-sW', str(artifact)], out, name + '-symbols', cap)
    need(sha(compiler) == identity.sha256, 'Compiler changed during test')
    need(pins == {name: sha(ROOT / name) for name in pins}, 'Source changed during test')
    guard(cap)
    identity.verify()
    summary = dict(status='passed', compiler_identity=identity.record(), compiler_sha256=sha(compiler), source_pins=pins, cases=counts,
        candidate_cap_mib=cap, cap_bytes=cap_bytes, sanitize=args.sanitize,
        candidate_allocated_bytes=allocated(), free_bytes=shutil.disk_usage(ROOT).free,
        limits='Hosted observations only; no QEMU, whole-language safety proof, whole-kernel stack or acceptance claim. Generated assembly is not sanitizer-instrumented. LeakSanitizer is disabled for the executor ptrace restriction; no leak-clean claim.')
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
