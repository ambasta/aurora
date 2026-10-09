#!/usr/bin/env python3
"""Versioned, test-only 4/8/16-byte AMD-Vi/EDU diagnostic. Never a hardware gate.

Runtime requires separate review and allocation through the pinned outer plan.
This file is self-contained and does not import or modify the historical harness.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import struct
import subprocess
import time

PROFILE = 'aurora-amdvi-aligned-access-granularity-v1-combined-v2'
BINARY_SHA256 = '81eb4ea516d85888112356f6a371c72e8fb1aa6c68a5819ecb5ec4fef8286ea7'
ROM_SHA256 = '4752c6521258b1d2025a81605797c8a76b4ffc27589c812ff267c1d0e649ce15'
MMIO, EDU, DT, PT, EV, CMD, DONE = 0xFED80000, 0xF0000000, 0x100000, 0x102000, 0x104000, 0x106000, 0x108000
# Every transfer is aligned, wholly inside one 4 KiB Mode1 page and below 40 bits.
OFFSET = 0x100
PA, SINK, HELPER = 0x200000 + OFFSET, 0x201000 + OFFSET, 0x202000 + OFFSET
IOVA, OUT, HELPER_IOVA = 0x3000 + OFFSET, 0x4000 + OFFSET, 0x5000 + OFFSET
RID, DOMAIN, RW, RING_BYTES, GUARD_BYTES = 0x20, 0x1234, 3 << 61, 4096, 16
CONTROL = 5 | (1 << 12)  # IOMMU, event log and command buffer; no IRQ enables.
NONCE, DONE_POISON = 0xDB1937456280ACEF, 0x3759BED12468ACF0
PATTERNS = {name: bytes.fromhex(value) for name, value in {
    'prime': '17395b7d9fb1d3f527496b8dafc1e315',
    'secret': '82a4c6e81a3c5e7092b4d6f82a4c6e80',
    'target': '416385a7c9eb1d3f527496b8dafc2e50',
    'poison': 'd2b496785a3d1ef0d1b39577593b1def',
    'helper': '6f4d2b19370583a1cfeac8a68462402e',
    'decoy': 'b1c3d5e7192b3d4f61738597a9cbed0f',
    'before': 'a65c3e197b2d4f6082b4d6e8fa1c3d5f',
    'after': '59a3c1e684d2b09f7d4b291705e3c2a0',
    'ring_before': '3155799dc1e5092d517599bde105294d',
    'ring_after': 'ceaA86623e1af6d2ae8a66421efaD6b2',
}.items()}
# Poison each complete record with invalid code F and slot-varying address.
RING_POISON = b''.join(struct.pack('<QQ', 0xF5A55A5ADEAD0000 | i,
                                  0xBAD0000000000000 | (i * 16)) for i in range(256))
CASES = [f'positive_{n}' for n in (4, 8, 16)] + [
    f'denied_{direction}_{n}' for n in (4, 8, 16) for direction in ('read', 'write')
] + ['transport_append_4', 'transport_disabled_then_live_4',
     'transport_last_slot_wrap_4', 'transport_full_then_suppressed_4']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def json_write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def decode_event(raw):
    a, b = struct.unpack('<QQ', raw)
    return {'raw_hex': raw.hex(), 'raw_qwords': [a, b], 'code': a >> 60,
            'rid': a & 0xFFFF, 'domain': (a >> 32) & 0xFFFF, 'address': b,
            'pr': (a >> 52) & 1, 'rw': (a >> 53) & 1,
            'pe': (a >> 54) & 1, 'rz': (a >> 55) & 1,
            'i': (a >> 51) & 1, 'tr': (a >> 56) & 1, 'gn': (a >> 48) & 1}


def expected_event(address, write):
    # Exact combined-v2 encoding prediction, separate from defined-field claims.
    return struct.pack('<QQ', (2 << 60) | (1 << 54) | (int(write) << 53) |
                       (1 << 52) | (DOMAIN << 32) | RID, address)


class Results:
    def __init__(self):
        self.checks, self.observations, self.snapshots, self.event_effects = {}, {}, {}, {}

    def check(self, key, actual, expected, kind):
        if key in self.checks:
            raise ValueError('Duplicate check: ' + key)
        self.checks[key] = actual == expected
        self.observations[key] = {'actual': actual, 'expected': expected, 'kind': kind}

    def finish(self, operations):
        groups = {}
        for key, passed in self.checks.items():
            kind = self.observations[key]['kind']
            groups[kind] = groups.get(kind, True) and passed
        return {'checks': self.checks, 'observations': self.observations,
                'components': groups, 'snapshots': self.snapshots,
                'event_effects': self.event_effects, 'dma_operations': operations,
                'pass': all(self.checks.values()),
                'interpretation': 'Bounded sentinels and model hypotheses; no universal PCI transaction, internal cache-hit, physical drain or hardware claim.'}


class Guest:
    def __init__(self, binary, output):
        self.output, self.p, self.command_tail = output, None, 0
        self.operations, self.rx = [], b''
        output.mkdir(parents=True, exist_ok=False)
        self.log = (output / 'qtest.jsonl').open('x', buffering=1)
        self.err = (output / 'qemu.stderr').open('x')
        rom = bytearray(65536)
        rom[-16:-12] = bytes.fromhex('faf4ebfd')
        bios = output / 'reset.bin'
        bios.write_bytes(rom)
        if sha(bios) != ROM_SHA256:
            raise RuntimeError('Reset ROM construction mismatch')
        self.argv = [binary, '-machine', 'q35', '-accel', 'tcg', '-m', '64M',
                     '-nodefaults', '-display', 'none', '-bios', str(bios),
                     '-device', 'amd-iommu', '-device',
                     'edu,addr=04.0,dma_mask=0xffffffffffffffff', '-qtest', 'stdio']
        json_write(output / 'before-exec.json', {'argv': self.argv, 'cwd': os.getcwd(),
                   'environment': dict(os.environ), 'binary_sha256': sha(binary),
                   'reset_rom_sha256': sha(bios), 'profile': PROFILE})
        try:
            self.p = subprocess.Popen(self.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=self.err, bufsize=0)
            self.pci(0x10, EDU)
            self.pci(4, 6)
            if self.read(EDU, 'l') != 0x010000ED:
                raise RuntimeError('EDU identity mismatch')
            # Initialize complete backed structures, not stale host/guest content.
            self.write_bytes(DT, bytes(8192))
            self.write_bytes(PT, bytes(4096))
            self.write_bytes(CMD, bytes(4096))
            self.write(DT + RID * 32, PT | 3 | (1 << 9) | RW)
            self.write(DT + RID * 32 + 8, DOMAIN)
            for index, address in [(3, PA), (4, SINK), (5, HELPER)]:
                self.leaf(index, (address & ~4095) | 1 | RW)
            self.write(MMIO, DT | 1)
            self.write(MMIO + 0x10, EV | (8 << 56))
            self.write(MMIO + 8, CMD | (8 << 56))
            self.write_bytes(EV - 16, PATTERNS['ring_before'])
            self.write_bytes(EV, RING_POISON)
            self.write_bytes(EV + RING_BYTES, PATTERNS['ring_after'])
            self.write(MMIO + 0x18, CONTROL)
        except BaseException as exc:
            try:
                self.close()
            except BaseException as cleanup:
                exc.add_note('Construction cleanup failed: ' + repr(cleanup))
            raise

    def q(self, command):
        deadline = time.monotonic() + 5
        try:
            self.p.stdin.write((command + '\n').encode('ascii'))
            while b'\n' not in self.rx:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select([self.p.stdout], [], [], remaining)[0]:
                    raise RuntimeError('qtest response timeout')
                chunk = os.read(self.p.stdout.fileno(), 65536)
                if not chunk:
                    raise RuntimeError('qtest EOF')
                self.rx += chunk
                if len(self.rx) > 131072:
                    raise RuntimeError('Oversized qtest response')
            line, self.rx = self.rx.split(b'\n', 1)
            reply = line.decode('ascii').strip()
        except BaseException as exc:
            self.log.write(json.dumps({'request': command, 'response': None,
                                       'error': repr(exc)}) + '\n')
            raise
        self.log.write(json.dumps({'request': command, 'response': reply}) + '\n')
        if reply != 'OK' and not reply.startswith('OK '):
            raise RuntimeError('Unexpected qtest reply: ' + reply)
        return reply[2:].strip()

    def write(self, address, value):
        self.q(f'writeq {address:#x} {value:#x}')

    def read(self, address, width='q'):
        return int(self.q(f'read{width} {address:#x}'), 16)

    def read_bytes(self, address, count):
        if not 0 < count <= 8192:
            raise ValueError('Bulk read size outside fixture bounds')
        response = self.q(f'read {address:#x} {count:#x}')
        if len(response) != 2 + count * 2 or not response.startswith('0x'):
            raise RuntimeError('Malformed qtest bulk-read length/prefix')
        return bytes.fromhex(response[2:])

    def write_bytes(self, address, data):
        if not 0 < len(data) <= 8192:
            raise ValueError('Bulk write size outside fixture bounds')
        self.q(f'write {address:#x} {len(data):#x} 0x{data.hex()}')

    def pci(self, offset, value):
        self.q(f'outl 0xcf8 {0x80000000 + (RID << 8) + offset:#x}')
        self.q(f'outl 0xcfc {value:#x}')

    def leaf(self, index, value):
        self.write(PT + index * 8, value)

    def dma(self, address, count, write, role, result):
        if count not in (4, 8, 16) or address % count or address // 4096 != (address + count - 1) // 4096:
            raise ValueError('DMA exceeds aligned fixture profile')
        key = f'dma_{len(self.operations):02d}_{role}'
        command = 3 if write else 1
        self.write(EDU + 0x80, 0x40000 if write else address)
        self.write(EDU + 0x88, address if write else 0x40000)
        self.write(EDU + 0x90, count)
        observed_count = self.read(EDU + 0x90)
        result.check(key + '_declared_count', observed_count, count, 'observation_control')
        if observed_count != count:
            raise RuntimeError('EDU count mismatch before submission')
        record = {'index': len(self.operations), 'role': role, 'address': address,
                  'direction': 'write' if write else 'read', 'declared_bytes': count,
                  'count_before_submit': observed_count, 'command': command, 'completed': False}
        self.operations.append(record)
        json_write(self.output / 'dma-operations.json', self.operations)
        self.write(EDU + 0x98, command)
        deadline = time.monotonic() + 3
        polls = []
        while True:
            value = self.read(EDU + 0x98)
            polls.append(value)
            if not value & 1:
                break
            if time.monotonic() > deadline:
                raise RuntimeError('EDU DMA timer did not finish')
            time.sleep(0.02)
        after_count = self.read(EDU + 0x90)
        record.update(completed=True, command_polls=polls, count_after=after_count,
                      final_command=value)
        result.check(key + '_completed_command', value, command & ~1, 'observation_control')
        result.check(key + '_retained_count', after_count, count, 'observation_control')
        json_write(self.output / 'dma-operations.json', self.operations)

    def invalidate(self, result):
        self.write(DONE, DONE_POISON)
        result.check('fresh_completion_poison', self.read(DONE), DONE_POISON, 'observation_control')
        for a, b in [((2 << 60) | RID, 0),
                     ((3 << 60) | (DOMAIN << 32), 0x7FFFFFFFFFFFF001),
                     ((1 << 60) | DONE | 5, NONCE)]:
            self.write(CMD + self.command_tail, a)
            self.write(CMD + self.command_tail + 8, b)
            self.command_tail += 16
        self.write(MMIO + 0x2008, self.command_tail)
        result.check('fresh_invalidation_completion', self.read(DONE), NONCE, 'observation_control')
        result.check('invalidation_command_head', self.read(MMIO + 0x2000), self.command_tail, 'observation_control')

    def close(self):
        try:
            if self.p is not None:
                if self.p.poll() is None:
                    self.p.terminate()
                    try:
                        self.p.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.p.kill()
                        self.p.wait(timeout=5)
                self.p.stdin.close()
                self.p.stdout.close()
        finally:
            self.err.close()
            self.log.close()


def install_region(g, address, payload):
    g.write_bytes(address - GUARD_BYTES, PATTERNS['before'] + payload + PATTERNS['after'])


def check_region(g, r, key, address, payload, kind):
    actual = g.read_bytes(address - GUARD_BYTES, len(payload) + 2 * GUARD_BYTES)
    r.check(key + '_payload', actual[16:-16].hex(), payload.hex(), kind)
    r.check(key + '_before_guard', actual[:16].hex(), PATTERNS['before'].hex(), 'memory_bounds')
    r.check(key + '_after_guard', actual[-16:].hex(), PATTERNS['after'].hex(), 'memory_bounds')
    return actual[16:-16]


def check_guards(g, r, key, address, count):
    r.check(key + '_before_guard', g.read_bytes(address - 16, 16).hex(), PATTERNS['before'].hex(), 'memory_bounds')
    r.check(key + '_after_guard', g.read_bytes(address + count, 16).hex(), PATTERNS['after'].hex(), 'memory_bounds')


def check_decoys(g, r, key, count):
    for label, address in [('input', IOVA), ('output', OUT), ('helper', HELPER_IOVA)]:
        check_region(g, r, key + '_' + label + '_decoy', address, PATTERNS['decoy'][:count], 'memory_denial_or_routing')


def snapshot(g, r, label):
    def registers():
        return {'head': g.read(MMIO + 0x2010), 'tail': g.read(MMIO + 0x2018),
                'status': g.read(MMIO + 0x2020), 'control': g.read(MMIO + 0x18)}
    before = registers()
    raw = g.read_bytes(EV, RING_BYTES)
    left = g.read_bytes(EV - 16, 16)
    right = g.read_bytes(EV + RING_BYTES, 16)
    after = registers()
    r.check(label + '_stable_registers', before, after, 'observation_control')
    r.check(label + '_ring_before_canary', left.hex(), PATTERNS['ring_before'].hex(), 'event_transport')
    r.check(label + '_ring_after_canary', right.hex(), PATTERNS['ring_after'].hex(), 'event_transport')
    value = {**after, 'event_ram_hex': raw.hex(), 'before_canary_hex': left.hex(),
             'after_canary_hex': right.hex()}
    r.snapshots[label] = value
    return value


def event_effect(r, key, before, after, addresses, write, overflow=0):
    """Inspect full page and every changed/cursor-advertised record, even on failure."""
    old, new = bytes.fromhex(before['event_ram_hex']), bytes.fromhex(after['event_ram_hex'])
    changed = [i for i in range(0, RING_BYTES, 16) if old[i:i + 16] != new[i:i + 16]]
    geometry = all(isinstance(s[p], int) and 0 <= s[p] < RING_BYTES and s[p] % 16 == 0
                   for s in (before, after) for p in ('head', 'tail'))
    r.check(key + '_valid_geometry', geometry, True, 'event_transport')
    advertised = []
    if geometry:
        distance = (after['tail'] - before['tail']) % RING_BYTES
        advertised = [(before['tail'] + i) % RING_BYTES for i in range(0, distance, 16)]
    expected_offsets = [(before['tail'] + i * 16) % RING_BYTES for i in range(len(addresses))]
    # The union captures even out-of-cursor writes and unchanged advertised records.
    observed_offsets = sorted(set(changed + advertised), key=lambda x: (x - before['tail']) % RING_BYTES)
    records = [{'offset': i, 'changed': i in changed, 'advertised': i in advertised,
                **decode_event(new[i:i + 16])} for i in observed_offsets]
    r.event_effects[key] = {'changed_slots': changed, 'advertised_slots': advertised,
                          'records': records, 'predicted_addresses': addresses,
                          'predicted_offsets': expected_offsets}
    r.check(key + '_head_preserved', after['head'], before['head'], 'event_transport')
    r.check(key + '_tail', after['tail'], (before['tail'] + len(addresses) * 16) % RING_BYTES, 'model_granularity' if len(addresses) > 1 else 'event_transport')
    r.check(key + '_changed_slots', changed, sorted(expected_offsets), 'model_granularity' if len(addresses) > 1 else 'event_transport')
    r.check(key + '_advertised_slots', advertised, expected_offsets, 'model_granularity' if len(addresses) > 1 else 'event_transport')
    r.check(key + '_overflow', after['status'] & 1, overflow, 'event_transport')
    expected_int = (before['status'] & 2) | (2 if addresses else 0)
    r.check(key + '_event_log_int', after['status'] & 2, expected_int, 'event_transport')
    r.check(key + '_no_unintended_comwait', after['status'] & 4, before['status'] & 4, 'event_transport')
    r.check(key + '_control_preserved', after['control'], before['control'], 'event_transport')
    untouched = bytearray(new)
    for offset in expected_offsets:
        untouched[offset:offset + 16] = old[offset:offset + 16]
    r.check(key + '_all_other_ring_bytes_unchanged', bytes(untouched).hex(), old.hex(), 'event_transport')
    # A missing predicted record is a count/hypothesis failure, not invented
    # evidence of malformed producer flags in poison RAM. Inspect all records
    # actually changed or advertised, including any unexpected extra record.
    for index, offset in enumerate(expected_offsets):
        r.check(f'{key}_predicted_record_{index}_observable', offset in observed_offsets, True,
                'model_granularity' if len(addresses) > 1 else 'event_transport')
    if addresses:
        for observed_index, offset in enumerate(observed_offsets):
            event = decode_event(new[offset:offset + 16])
            fields = {'code': 2, 'rid': RID, 'domain': DOMAIN,
                      'i': 0, 'tr': 0, 'gn': 0, 'pr': 1, 'rw': int(write), 'pe': 1}
            for field, wanted in fields.items():
                r.check(f'{key}_observed_record_{observed_index}_{field}', event[field], wanted, 'defined_event_fields')
            if offset in expected_offsets:
                index = expected_offsets.index(offset)
                address = addresses[index]
                r.check(f'{key}_record_{index}_address', event['address'], address,
                        'model_granularity' if index > 0 else 'defined_event_fields')
                r.check(f'{key}_record_{index}_exact_model_encoding', event['raw_hex'],
                        expected_event(address, write).hex(), 'model_encoding_hypothesis')


def prepare(g, r, count):
    for address, name in [(PA, 'prime'), (SINK, 'poison'), (HELPER, 'helper'),
                          (IOVA, 'decoy'), (OUT, 'decoy'), (HELPER_IOVA, 'decoy')]:
        install_region(g, address, PATTERNS[name][:count])
        check_region(g, r, f'initial_{address:x}', address, PATTERNS[name][:count], 'observation_control')
    initial = snapshot(g, r, 'initial')
    r.check('initial_event_ram_poison', initial['event_ram_hex'], RING_POISON.hex(), 'observation_control')
    r.check('initial_head_tail', [initial['head'], initial['tail']], [0, 0], 'event_transport')
    r.check('initial_low_status_clear', initial['status'] & 7, 0, 'event_transport')
    r.check('initial_control', initial['control'], CONTROL, 'observation_control')
    # Observe the same-requester output route independently of the source to be denied.
    output_liveness(g, r, count, 'initial_liveness')
    g.dma(IOVA, count, False, 'fresh_permitted_prime', r)
    install_region(g, SINK, PATTERNS['poison'][:count])
    g.dma(OUT, count, True, 'observe_fresh_prime', r)
    check_region(g, r, 'fresh_prime_observed', SINK, PATTERNS['prime'][:count], 'observation_control')
    check_region(g, r, 'fresh_prime_source_unchanged', PA, PATTERNS['prime'][:count], 'memory_bounds')
    check_decoys(g, r, 'after_prime', count)
    before = snapshot(g, r, 'after_permitted_prime')
    event_effect(r, 'permitted_preparation_no_event', initial, before, [], False)


def output_liveness(g, r, count, key):
    install_region(g, HELPER, PATTERNS['helper'][:count])
    install_region(g, SINK, PATTERNS['poison'][:count])
    g.dma(HELPER_IOVA, count, False, key + '_read', r)
    g.dma(OUT, count, True, key + '_dump', r)
    check_region(g, r, key + '_exact_bytes', SINK, PATTERNS['helper'][:count], 'observation_control')
    check_region(g, r, key + '_helper_source', HELPER, PATTERNS['helper'][:count], 'memory_bounds')
    check_decoys(g, r, key, count)


def prepare_denial(g, r, count, write):
    prepare(g, r, count)
    g.leaf(3, (PA & ~4095) | 1 | ((1 << 61) if write else (1 << 62)))
    g.invalidate(r)
    install_region(g, PA, PATTERNS['target' if write else 'secret'][:count])
    # Fresh secret bytes all differ from old prime, helper, decoy and output poison.
    if not write:
        install_region(g, SINK, PATTERNS['poison'][:count])
    no_fault = snapshot(g, r, 'after_restriction')
    event_effect(r, 'restriction_no_event', r.snapshots['after_permitted_prime'], no_fault, [], write)


def attempt_denial(g, r, count, write, key):
    g.dma(IOVA, count, write, key + '_attempt', r)
    check_region(g, r, key + '_source_or_target_unchanged', PA,
                 PATTERNS['target' if write else 'secret'][:count], 'memory_denial')
    if not write:
        g.dma(OUT, count, True, key + '_denied_read_dump', r)
        observed = g.read_bytes(SINK, count)
        r.observations[key + '_denied_read_bytes'] = {'actual': observed.hex(),
            'fresh_secret_hex': PATTERNS['secret'][:count].hex(),
            'old_prime_hex': PATTERNS['prime'][:count].hex(),
            'output_poison_hex': PATTERNS['poison'][:count].hex(),
            'kind': 'raw_observation', 'note': 'No assumption that EDU preserves its old buffer on read error.'}
        for i, value in enumerate(observed):
            r.check(f'{key}_byte_{i}_does_not_match_fresh_secret', value != PATTERNS['secret'][i], True, 'memory_denial')
            r.check(f'{key}_byte_{i}_dump_replaced_poison', value != PATTERNS['poison'][i], True, 'observation_control')
        check_guards(g, r, key + '_read_dump', SINK, count)
    check_decoys(g, r, key, count)


def run_case(g, name):
    r = Results()
    if name.startswith('positive_'):
        count = int(name.rsplit('_', 1)[1])
        prepare(g, r, count)
        check_region(g, r, 'positive_exact_output', SINK, PATTERNS['prime'][:count], 'positive_data')
        final = snapshot(g, r, 'positive_final')
        event_effect(r, 'positive_no_events', r.snapshots['initial'], final, [], False)
    elif name.startswith('denied_'):
        _, direction, size = name.split('_')
        count, write = int(size), direction == 'write'
        prepare_denial(g, r, count, write)
        before = snapshot(g, r, 'before_denied_transfer')
        attempt_denial(g, r, count, write, 'denial')
        after = snapshot(g, r, 'after_denied_transfer')
        event_effect(r, 'denial', before, after, list(range(IOVA, IOVA + count, 4)), write)
        # Liveness remains a separate control even if denial/event checks fail.
        output_liveness(g, r, count, 'final_liveness')
        final = snapshot(g, r, 'after_final_liveness')
        event_effect(r, 'liveness_added_no_events', after, final, [], False)
    else:
        count, write = 4, True
        prepare_denial(g, r, count, write)
        if name == 'transport_disabled_then_live_4':
            g.write(MMIO + 0x18, CONTROL & ~4)
            before = snapshot(g, r, 'disabled_before')
            r.check('disabled_control_written', before['control'], CONTROL & ~4, 'observation_control')
            r.check('disabled_clean_status', before['status'] & 7, 0, 'event_transport')
            attempt_denial(g, r, count, write, 'disabled')
            after = snapshot(g, r, 'disabled_after')
            event_effect(r, 'disabled', before, after, [], write)
            g.write(MMIO + 0x18, CONTROL)
            before = snapshot(g, r, 'reenabled_before')
            r.check('reenabled_control_written', before['control'], CONTROL, 'observation_control')
            r.check('reenable_preserved_ram', before['event_ram_hex'], after['event_ram_hex'], 'event_transport')
            r.check('reenable_preserved_pointers', [before['head'], before['tail']], [after['head'], after['tail']], 'event_transport')
            attempt_denial(g, r, count, write, 'reenabled')
            after = snapshot(g, r, 'reenabled_after')
            event_effect(r, 'reenabled', before, after, [IOVA], write)
        elif name in ('transport_last_slot_wrap_4', 'transport_full_then_suppressed_4'):
            full = name == 'transport_full_then_suppressed_4'
            g.write(MMIO + 0x18, CONTROL & ~4)
            g.write(MMIO + 0x2010, 0 if full else 32)
            g.write(MMIO + 0x2018, 4080)
            g.write(MMIO + 0x18, CONTROL)
            before = snapshot(g, r, 'boundary_before')
            r.check('boundary_exact_head_tail', [before['head'], before['tail']], [0 if full else 32, 4080], 'observation_control')
            r.check('boundary_logging_enabled', before['control'], CONTROL, 'observation_control')
            r.check('boundary_clean_status', before['status'] & 7, 0, 'event_transport')
            attempt_denial(g, r, count, write, 'boundary_first')
            after = snapshot(g, r, 'boundary_after_first')
            event_effect(r, 'boundary_first', before, after, [] if full else [IOVA], write, int(full))
            if full:
                # Free room without clearing overflow: test suppression, NOT restart.
                g.write(MMIO + 0x2010, 32)
            before = snapshot(g, r, 'boundary_before_second')
            r.check('boundary_second_exact_head_tail', [before['head'], before['tail']], [32, 4080 if full else 0], 'observation_control')
            r.check('between_attempts_ring_unchanged', before['event_ram_hex'], after['event_ram_hex'], 'event_transport')
            r.check('before_second_overflow_latched', before['status'] & 1, int(full), 'event_transport')
            attempt_denial(g, r, count, write, 'boundary_second')
            after = snapshot(g, r, 'boundary_after_second')
            event_effect(r, 'boundary_second', before, after, [] if full else [IOVA], write, int(full))
        elif name == 'transport_append_4':
            before = snapshot(g, r, 'append_before')
            attempt_denial(g, r, count, write, 'append')
            after = snapshot(g, r, 'append_after')
            event_effect(r, 'append', before, after, [IOVA], write)
        else:
            raise ValueError(name)
        output_liveness(g, r, count, 'transport_final_liveness')
        final = snapshot(g, r, 'transport_final')
        event_effect(r, 'transport_liveness_no_new_events', after, final, [], False, int(name == 'transport_full_then_suppressed_4'))
    expected_operations = (4 if name.startswith('positive_') else
                           8 if name.startswith('denied_read_') or name in
                           ('transport_disabled_then_live_4', 'transport_last_slot_wrap_4',
                            'transport_full_then_suppressed_4') else 7)
    r.check('exact_declared_dma_operation_count', len(g.operations), expected_operations, 'observation_control')
    r.check('all_operations_completed', all(op['completed'] for op in g.operations), True, 'observation_control')
    return r.finish(g.operations)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    # No alternate cases/model can silently replace this pinned full-suite plan.
    if sha(args.qemu) != BINARY_SHA256:
        raise SystemExit('QEMU identity mismatch; separate model review/plan required')
    args.output.mkdir(parents=True, exist_ok=False)
    results = {}
    for name in CASES:
        guest = None
        try:
            guest = Guest(args.qemu, args.output / name)
            results[name] = run_case(guest, name)
        except BaseException as exc:
            results[name] = {'pass': False, 'infrastructure_error': repr(exc),
                             'exception_notes': list(getattr(exc, '__notes__', []))}
        finally:
            if guest is not None:
                try:
                    guest.close()
                except BaseException as exc:
                    results[name]['pass'] = False
                    results[name]['cleanup_error'] = repr(exc)
        json_write(args.output / 'partial-results.json', results)
        print(name, 'PASS' if results[name]['pass'] else 'FAIL', flush=True)
    report = {'schema': 2, 'profile': PROFILE, 'qemu_sha256': sha(args.qemu),
              'harness_sha256': sha(__file__), 'reset_rom_sha256': ROM_SHA256,
              'results': results, 'pass': all(item['pass'] for item in results.values()),
              'historical_fixture_unchanged': True,
              'scope': 'Aligned 4/8/16-byte ordinary-memory/common40-bit/no-exclusion Mode1; separate sentinel denial, event transport, defined fields and model granularity results.',
              'not_claimed': ['universal PCI transaction boundary', 'direct translation callback instrumentation',
                  'internal cache hit', 'all 255 usable ring entries', 'overflow restart', 'MSI delivery',
                  'command-stop correction', 'other modes', 'physical DMA/drain/reclamation']}
    json_write(args.output / 'report.json', report)
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
