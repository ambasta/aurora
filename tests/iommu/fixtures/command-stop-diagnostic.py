#!/usr/bin/env python3
"""Bounded dispatch-default command-stop diagnostic; runtime is separately gated.

Exact-pinned transport and frozen cases are vendored without byte changes.
Preparation/static mocks are not an emulator replay or architectural proof.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parent
PROFILE = 'aurora-amdvi-command-stop-v1'
SOURCE_SHA256 = 'a506dccf0c112cc791208724651b3aaca300f8b713362dfd07af2308e6f5a2d9'
IMPORT_PINS = {
    'transport-import-v1.py': '52f40383a50ddf437c9f240733af93f0722c3ae54092309f933ca658461dde80',
    'frozen-import.py': 'a380e4792cd50417b457e638fdfeb6e3f5efd3b8126dcf8915a0c88ef0c27e28',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pinned_import(filename, name):
    path = ROOT / filename
    if sha(path) != IMPORT_PINS[filename]:
        raise RuntimeError('Exact import identity mismatch: ' + filename)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


t = pinned_import('transport-import-v1.py', 'command_stop_transport_v1')
frozen = pinned_import('frozen-import.py', 'command_stop_frozen_cases')
# Only the transport pre-exec metadata label is rebound; imported source stays exact.
t.PROFILE = PROFILE
MMIO, EDU, DT, PT, EV, CMD, DONE = t.MMIO, t.EDU, t.DT, t.PT, t.EV, t.CMD, t.DONE
HEAD, TAIL, STATUS, CTRL = MMIO + 0x2000, MMIO + 0x2008, MMIO + 0x2020, MMIO + 0x18
EH, ET = MMIO + 0x2010, MMIO + 0x2018
CONTROL, CMD_EN, RUN, LOG_RUN, OVERFLOW, LOG_INT, COM_INT = t.CONTROL, 1 << 12, 16, 8, 1, 2, 4
OPCODES = (0, 9, 10, 11, 12, 13, 14, 15)
MODES = ('live', 'disabled', 'full')
CASES = [f'opcode_{op:x}_{mode}' for op in OPCODES for mode in MODES] + [
    'preexisting_overflow', 'positive_healthy_commands',
    'recovery_disable_repair_enable', 'recovery_same_value_control',
    'frozen_illegal_command_stops', 'frozen_revoke_invalidate_completion',
]
STORE_ADDRESSES = [DONE + 64 * i for i in range(8)]


def check(r, key, actual, expected, kind='command_state'):
    r.check(key, actual, expected, kind)


def raw(g, address, count):
    # Also usable with the unchanged frozen Guest, without replacing its methods.
    return t.Guest.read_bytes(g, address, count)


def capture(g, r, label):
    def regs():
        return {'command_head': g.read(HEAD), 'command_tail': g.read(TAIL),
                'event_head': g.read(EH), 'event_tail': g.read(ET),
                'status': g.read(STATUS), 'control': g.read(CTRL)}
    before = regs()
    value = {**before, 'event_ram_hex': raw(g, EV, 4096).hex(),
             'command_ram_hex': raw(g, CMD, 4096).hex(),
             'event_before_canary_hex': raw(g, EV - 16, 16).hex(),
             'event_after_canary_hex': raw(g, EV + 4096, 16).hex(),
             'stores': [raw(g, address - 16, 40).hex() for address in STORE_ADDRESSES]}
    after = regs()
    check(r, label + '_stable_registers', after, before, 'observation_control')
    r.snapshots[label] = value
    return value


def event_delta(r, key, before, after, records, overflow=None, check_canaries=True):
    """Keep/decode every changed OR cursor-advertised complete 16-byte record."""
    old, new = bytes.fromhex(before['event_ram_hex']), bytes.fromhex(after['event_ram_hex'])
    changed = [i for i in range(0, 4096, 16) if old[i:i + 16] != new[i:i + 16]]
    geometry = all(0 <= s[k] < 4096 and s[k] % 16 == 0
                   for s in (before, after) for k in ('event_head', 'event_tail'))
    check(r, key + '_valid_event_geometry', geometry, True, 'event_transport')
    advertised = ([(before['event_tail'] + i) % 4096 for i in
                   range(0, (after['event_tail'] - before['event_tail']) % 4096, 16)] if geometry else [])
    offsets = [(before['event_tail'] + i * 16) % 4096 for i in range(len(records))]
    observed = sorted(set(changed + advertised), key=lambda x: (x - before['event_tail']) % 4096)
    decoded = [{'offset': offset, 'changed': offset in changed, 'advertised': offset in advertised,
                **t.decode_event(new[offset:offset + 16])} for offset in observed]
    r.event_effects[key] = {'changed_slots': changed, 'advertised_slots': advertised,
                          'observed_records': decoded,
                          'expected_records_hex': [record.hex() for record in records]}
    check(r, key + '_event_head', after['event_head'], before['event_head'], 'event_transport')
    check(r, key + '_event_tail', after['event_tail'], (before['event_tail'] + 16 * len(records)) % 4096, 'event_transport')
    check(r, key + '_changed_slots', changed, sorted(offsets), 'event_transport')
    check(r, key + '_advertised_slots', advertised, offsets, 'event_transport')
    expected_page = bytearray(old)
    for index, (offset, record) in enumerate(zip(offsets, records)):
        expected_page[offset:offset + 16] = record
        check(r, f'{key}_record_{index}_observable', offset in observed, True, 'event_transport')
        if offset in observed:
            actual = new[offset:offset + 16]
            a, b = struct.unpack('<QQ', actual)
            ea, eb = struct.unpack('<QQ', record)
            check(r, f'{key}_record_{index}_code', a >> 60, ea >> 60, 'defined_event_fields')
            check(r, f'{key}_record_{index}_address', b, eb, 'defined_event_fields')
            # Table61 default-command event contains only code and aligned address.
            if ea >> 60 == 2:
                actual_fields, expected_fields = t.decode_event(actual), t.decode_event(record)
                for field in ('rid', 'domain', 'i', 'tr', 'gn', 'pr', 'rw', 'pe'):
                    check(r, f'{key}_record_{index}_{field}', actual_fields[field],
                          expected_fields[field], 'defined_event_fields')
            kind = 'defined_reserved_fields' if ea >> 60 == 5 else 'model_encoding_hypothesis'
            check(r, f'{key}_record_{index}_entire_record', actual.hex(), record.hex(), kind)
    check(r, key + '_entire_event_page', new.hex(), bytes(expected_page).hex(), 'event_transport')
    if overflow is None:
        overflow = before['status'] & OVERFLOW
    check(r, key + '_overflow', after['status'] & OVERFLOW, overflow, 'event_transport')
    check(r, key + '_log_interrupt', after['status'] & LOG_INT,
          (before['status'] & LOG_INT) | (LOG_INT if records else 0), 'event_transport')
    if check_canaries:
        for side, pattern in [('before', 'ring_before'), ('after', 'ring_after')]:
            check(r, key + f'_event_{side}_canary', after[f'event_{side}_canary_hex'],
                  t.PATTERNS[pattern].hex(), 'memory_bounds')


def illegal_record(offset):
    return struct.pack('<QQ', 5 << 60, CMD + offset)


def nonce(case_name, index):
    digest = hashlib.sha256((PROFILE + '/' + case_name + '/' + str(index)).encode()).digest()
    return int.from_bytes(digest[:8], 'little')


def poison(case_name, index):
    return nonce(case_name, index) ^ 0xFFFFFFFFFFFFFFFF


def prepare_stores(g, r, case_name):
    for i, address in enumerate(STORE_ADDRESSES):
        t.install_region(g, address, struct.pack('<Q', poison(case_name, i)))
        check_store(g, r, 'initial', case_name, i, False)
    check(r, 'initial_command_head_tail', [g.read(HEAD), g.read(TAIL)], [0, 0], 'observation_control')
    check(r, 'initial_status', g.read(STATUS), RUN | LOG_RUN, 'observation_control')
    check(r, 'initial_control', g.read(CTRL), CONTROL, 'observation_control')


def check_store(g, r, phase, case_name, index, stored):
    value = nonce(case_name, index) if stored else poison(case_name, index)
    t.check_region(g, r, f'{phase}_store_{index}', STORE_ADDRESSES[index], struct.pack('<Q', value),
                   'completion_store' if stored else 'blocked_completion_store')


def put(g, offset, first, second):
    if offset % 16 or not 0 <= offset < 4096:
        raise ValueError('Command offset outside aligned ring')
    g.write(CMD + offset, first)
    g.write(CMD + offset + 8, second)


def wait(g, offset, case_name, index, interrupt=False, store=True):
    put(g, offset, (1 << 60) | STORE_ADDRESSES[index] | 4 | int(store) | (2 if interrupt else 0),
        nonce(case_name, index))


def command_state(r, key, snap, head, tail, control, status):
    for label, expected in [('command_head', head), ('command_tail', tail),
                            ('control', control), ('status', status)]:
        check(r, key + '_' + label, snap[label], expected)


def setup_stop(g, r, case_name, op=0, mode='live', final_slot=False, preoverflow=False):
    prepare_stores(g, r, case_name)
    control = CONTROL & ~4 if mode == 'disabled' else CONTROL
    # Disable only the command engine during placement. Full control writes only.
    g.write(CTRL, control & ~CMD_EN)
    if mode == 'full':
        g.write(EH, 0)
        g.write(ET, 4080)
    if preoverflow:
        # Produce one live ordinary fault, then a real full-ring overflow.
        # The source is never previously translated, so no invalidation premise.
        g.leaf(3, (t.PA & ~4095) | 1 | (1 << 61))
        t.install_region(g, t.PA, t.PATTERNS['target'][:4])
        s0 = capture(g, r, 'preoverflow_live_before')
        g.dma(t.IOVA, 4, True, 'establish_live_fault', r)
        s1 = capture(g, r, 'preoverflow_live_after')
        event_delta(r, 'preoverflow_live_fault', s0, s1, [t.expected_event(t.IOVA, True)])
        g.write(ET, 4080)
        s2 = capture(g, r, 'preoverflow_full_before')
        check(r, 'preoverflow_actual_full_geometry', [s2['event_head'], s2['event_tail']], [0, 4080], 'observation_control')
        check(r, 'preoverflow_clean_before_full', s2['status'] & OVERFLOW, 0, 'observation_control')
        g.dma(t.IOVA, 4, True, 'establish_overflow', r)
        s3 = capture(g, r, 'preoverflow_full_after')
        event_delta(r, 'preoverflow_full_discard', s2, s3, [], overflow=1)
        # Free two slots without any STATUS write. Overflow must still suppress.
        g.write(EH, 32)
        check(r, 'preoverflow_target_unchanged', raw(g, t.PA, 4).hex(), t.PATTERNS['target'][:4].hex(), 'memory_denial')
    start, bad, following = (4064, 4080, 0) if final_slot else (0, 16, 32)
    tail = (following + 16) % 4096
    g.write(HEAD, start)
    g.write(TAIL, start)
    # Empty queue can be started safely before submission of the actual batch.
    g.write(CTRL, control)
    before = capture(g, r, 'before_batch')
    base_status = RUN | (0 if mode == 'disabled' else LOG_RUN)
    if preoverflow:
        base_status |= OVERFLOW | LOG_INT
    command_state(r, 'batch_prerequisite', before, start, start, control, base_status)
    check(r, 'batch_initial_event_geometry', [before['event_head'], before['event_tail']],
          [32, 4080] if preoverflow else [0, 4080] if mode == 'full' else [0, 0], 'observation_control')
    wait(g, start, case_name, 0, interrupt=True)
    # High nibble differs from first-qword opcode and is nonzero for opcode0.
    second_nibble = op ^ 0xF
    put(g, bad, (op << 60) | 0x02468ACE, (second_nibble << 60) | 0x123456789ABCDEF)
    wait(g, following, case_name, 1, interrupt=True)
    g.write(TAIL, tail)
    stopped = capture(g, r, 'after_stop')
    records = [illegal_record(bad)] if mode == 'live' and not preoverflow else []
    overflow = 1 if mode == 'full' or preoverflow else 0
    event_delta(r, 'illegal_stop', before, stopped, records, overflow)
    expected_status = (base_status & ~RUN) | COM_INT | (LOG_INT if records else 0) | overflow
    command_state(r, 'stopped', stopped, bad, tail, control, expected_status)
    check_store(g, r, 'stopped_prior', case_name, 0, True)
    check_store(g, r, 'stopped_following', case_name, 1, False)
    check_store(g, r, 'stopped_later', case_name, 2, False)
    r.observations['command_encoding'] = {'opcode': op, 'second_qword_high_nibble': second_nibble,
        'offending_offset': bad, 'following_offset': following,
        'kind': 'raw_observation', 'synchronous_no_prefetch_profile': True}
    return {'snapshot': stopped, 'head': bad, 'tail': tail, 'following': following,
            'control': control, 'status': expected_status, 'overflow': overflow}


def durable_notifications(g, r, name, context):
    old = context['snapshot']
    bad, tail, control, status = [context[k] for k in ('head', 'tail', 'control', 'status')]
    actions = [('same_tail', TAIL, tail), ('same_head', HEAD, bad),
               ('status_run_attempt', STATUS, status | RUN)]
    for label, register, value in actions:
        g.write(register, value)
        new = capture(g, r, label)
        command_state(r, label, new, bad, tail, control, status)
        event_delta(r, label, old, new, [], context['overflow'])
        check_store(g, r, label, name, 1, False)
        old = new
    wait(g, tail, name, 2, interrupt=True)
    tail = (tail + 16) % 4096
    g.write(TAIL, tail)
    new = capture(g, r, 'advanced_tail')
    command_state(r, 'advanced_tail', new, bad, tail, control, status)
    event_delta(r, 'advanced_tail', old, new, [], context['overflow'])
    for i in (1, 2):
        check_store(g, r, 'advanced_tail', name, i, False)
    old = new
    # Software may edit head while stopped; this intentionally skips the bad entry.
    # It still must not execute the healthy wait until a control write restarts.
    g.write(HEAD, context['following'])
    for label, register, value in [('head_skipped', TAIL, tail),
                                 ('repeat_status_run_attempt', STATUS, status | RUN)]:
        g.write(register, value)
        new = capture(g, r, label)
        command_state(r, label, new, context['following'], tail, control, status)
        event_delta(r, label, old, new, [], context['overflow'])
        for i in (1, 2):
            check_store(g, r, label, name, i, False)
        old = new
    check_store(g, r, 'durable_prior_preserved', name, 0, True)
    return old


def dma_liveness(g, r, name, before, context):
    for addr in (t.IOVA, t.OUT, t.HELPER_IOVA):
        t.install_region(g, addr, t.PATTERNS['decoy'][:4])
    t.output_liveness(g, r, 4, 'stopped_unrelated_dma')
    after = capture(g, r, 'after_unrelated_dma')
    event_delta(r, 'unrelated_dma_no_events', before, after, [], context['overflow'])
    command_state(r, 'unrelated_dma_still_stopped', after, before['command_head'],
                  before['command_tail'], context['control'], context['status'])
    for i in (1, 2):
        check_store(g, r, 'dma_did_not_complete_commands', name, i, False)
    # Independent first-touch source: no queued invalidation or cache-hit premise.
    g.leaf(3, (t.PA & ~4095) | 1 | (1 << 61))
    t.install_region(g, t.PA, t.PATTERNS['target'][:4])
    g.dma(t.IOVA, 4, True, 'stopped_denied_dma', r)
    denied = capture(g, r, 'after_stopped_denied_dma')
    visible = bool(context['control'] & 4) and not context['overflow']
    event_delta(r, 'stopped_denied_dma', after, denied,
                [t.expected_event(t.IOVA, True)] if visible else [], context['overflow'])
    t.check_region(g, r, 'stopped_denied_target', t.PA, t.PATTERNS['target'][:4], 'memory_denial')
    t.check_decoys(g, r, 'stopped_denied_decoys', 4)
    command_state(r, 'denied_dma_still_stopped', denied, before['command_head'],
                  before['command_tail'], context['control'], context['status'])
    for i in (1, 2):
        check_store(g, r, 'denied_dma_did_not_complete_commands', name, i, False)
    return denied


def restart_skipped(g, r, name, before, context):
    # Complete the exact skipped-head path, after all stop/durability/DMA checks.
    g.write(CTRL, context['control'])
    after = capture(g, r, 'skipped_head_explicit_restart')
    command_state(r, 'skipped_head_explicit_restart', after, before['command_tail'],
                  before['command_tail'], context['control'], context['status'] | RUN)
    event_delta(r, 'skipped_head_restart_no_events', before, after, [], context['overflow'])
    for i in (0, 1, 2):
        check_store(g, r, 'skipped_head_explicit_restart', name, i, True)


def healthy(g, r, name):
    prepare_stores(g, r, name)
    initial = capture(g, r, 'healthy_initial')
    wait(g, 0, name, 0)
    g.write(TAIL, 16)
    one = capture(g, r, 'healthy_one')
    command_state(r, 'healthy_one', one, 16, 16, CONTROL, RUN | LOG_RUN)
    check_store(g, r, 'healthy_one', name, 0, True)
    wait(g, 16, name, 1)
    wait(g, 32, name, 2, interrupt=True)
    g.write(TAIL, 48)
    many = capture(g, r, 'healthy_many')
    command_state(r, 'healthy_many', many, 48, 48, CONTROL, RUN | LOG_RUN | COM_INT)
    wait(g, 48, name, 3, store=False)
    g.write(TAIL, 64)
    no_store = capture(g, r, 'healthy_no_store')
    command_state(r, 'healthy_no_store', no_store, 64, 64, CONTROL, RUN | LOG_RUN | COM_INT)
    for i in (0, 1, 2):
        check_store(g, r, 'healthy_many', name, i, True)
    check_store(g, r, 'healthy_no_store', name, 3, False)
    g.write(CTRL, CONTROL & ~CMD_EN)
    wait(g, 64, name, 4)
    g.write(TAIL, 80)
    disabled = capture(g, r, 'healthy_disabled')
    command_state(r, 'healthy_disabled', disabled, 64, 80, CONTROL & ~CMD_EN, LOG_RUN | COM_INT)
    check_store(g, r, 'healthy_disabled', name, 4, False)
    g.write(CTRL, CONTROL)
    enabled = capture(g, r, 'healthy_enabled')
    command_state(r, 'healthy_enabled', enabled, 80, 80, CONTROL, RUN | LOG_RUN | COM_INT)
    check_store(g, r, 'healthy_enabled', name, 4, True)
    event_delta(r, 'healthy_no_events', initial, enabled, [])


def recovery(g, r, name, same_value):
    context = setup_stop(g, r, name)
    old = context['snapshot']
    # First restart the unchanged bad entry: a new event and another settled stop.
    if not same_value:
        g.write(CTRL, CONTROL & ~CMD_EN)
    g.write(CTRL, CONTROL)
    again = capture(g, r, 'bad_entry_restarted')
    event_delta(r, 'bad_entry_restarted', old, again, [illegal_record(context['head'])])
    command_state(r, 'bad_entry_restarted', again, context['head'], context['tail'], CONTROL, LOG_RUN | COM_INT | LOG_INT)
    check_store(g, r, 'bad_entry_restarted', name, 1, False)
    if not same_value:
        g.write(CTRL, CONTROL & ~CMD_EN)
    # Repair the very same command slot, without fabricating a hardware head update.
    wait(g, context['head'], name, 3)
    repaired = capture(g, r, 'repaired_before_restart')
    expected_control = CONTROL if same_value else CONTROL & ~CMD_EN
    command_state(r, 'repaired_before_restart', repaired, context['head'], context['tail'], expected_control, LOG_RUN | COM_INT | LOG_INT)
    for i in (1, 3):
        check_store(g, r, 'repaired_before_restart', name, i, False)
    g.write(TAIL, context['tail'])
    check_store(g, r, 'repaired_tail_notification', name, 1, False)
    check_store(g, r, 'repaired_tail_notification', name, 3, False)
    g.write(CTRL, CONTROL)  # An identical full write is enough; no enable edge required.
    restarted = capture(g, r, 'repaired_restarted')
    command_state(r, 'repaired_restarted', restarted, context['tail'], context['tail'], CONTROL, RUN | LOG_RUN | COM_INT | LOG_INT)
    for i in (0, 1, 3):
        check_store(g, r, 'repaired_restarted', name, i, True)
    event_delta(r, 'repair_adds_no_events', again, restarted, [])


def run_case(g, name):
    r = t.Results()
    if name.startswith('opcode_'):
        _, opcode, mode = name.split('_')
        context = setup_stop(g, r, name, int(opcode, 16), mode, int(opcode, 16) == 15)
        last = durable_notifications(g, r, name, context)
        # All log states get a same-requester independent positive DMA route.
        last = dma_liveness(g, r, name, last, context)
        restart_skipped(g, r, name, last, context)
        operations = 3
    elif name == 'preexisting_overflow':
        context = setup_stop(g, r, name, op=9, preoverflow=True)
        last = durable_notifications(g, r, name, context)
        last = dma_liveness(g, r, name, last, context)
        restart_skipped(g, r, name, last, context)
        operations = 5
    elif name == 'positive_healthy_commands':
        healthy(g, r, name)
        operations = 0
    elif name.startswith('recovery_'):
        recovery(g, r, name, name == 'recovery_same_value_control')
        operations = 0
    else:
        raise ValueError(name)
    check(r, 'exact_dma_operation_count', len(g.operations), operations, 'observation_control')
    check(r, 'all_dma_operations_completed', all(op['completed'] for op in g.operations), True, 'observation_control')
    return r.finish(g.operations)


def run_frozen(g, name):
    """Execute exact original run_case/Guest paths; append read-only observations."""
    r = t.Results()
    before = capture(g, r, 'frozen_before')
    original_name = name.removeprefix('frozen_')
    result = frozen.run_case(g, original_name)
    after = capture(g, r, 'frozen_after')
    old, new = bytes.fromhex(before['event_ram_hex']), bytes.fromhex(after['event_ram_hex'])
    changed = [i for i in range(0, 4096, 16) if old[i:i + 16] != new[i:i + 16]]
    advertised = [(before['event_tail'] + i) % 4096 for i in range(0, (after['event_tail'] - before['event_tail']) % 4096, 16)]
    r.event_effects['frozen_full_readback'] = {'changed_slots': changed, 'advertised_slots': advertised,
        'observed_records': [{'offset': i, **t.decode_event(new[i:i + 16])} for i in sorted(set(changed + advertised))]}
    if original_name == 'illegal_command_stops':
        command_state(r, 'frozen_stopped', after, 0, 48, CONTROL, LOG_RUN | LOG_INT)
        event_delta(r, 'frozen_illegal', before, after, [illegal_record(0)], check_canaries=False)
    else:
        # Original invalidation scope and 8-byte requests are not weakened/expanded.
        check(r, 'frozen_regression_command_head', after['command_head'], 64)
        check(r, 'frozen_regression_command_tail', after['command_tail'], 64)
        check(r, 'frozen_regression_running', after['status'] & RUN, RUN)
    result['frozen_case_source_sha256'] = IMPORT_PINS['frozen-import.py']
    result['supplement'] = r.finish([])
    # Preserve original check names/values exactly while including supplemental failures.
    result['original_frozen_case_pass'] = result['pass']
    result['pass'] = result['pass'] and result['supplement']['pass']
    return result


def validate_target(binary):
    # Deliberately absent during preparation. No guessed binary identity is usable.
    target = json.loads((ROOT / 'TARGET-BINARY.json').read_text())
    if target.get('source_c_sha256') != SOURCE_SHA256 or target.get('profile') != PROFILE:
        raise RuntimeError('Target source/profile mismatch')
    if Path(binary).resolve() != Path(target['binary_path']).resolve() or sha(binary) != target['binary_sha256']:
        raise RuntimeError('Target binary identity mismatch')
    return target


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--qemu', required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    if sys.byteorder != 'little':
        raise SystemExit('This diagnostic profile requires a little-endian host')
    target = validate_target(args.qemu)
    args.output.mkdir(parents=True, exist_ok=False)
    results = {}
    for name in CASES:
        guest = None
        try:
            cls = frozen.Guest if name.startswith('frozen_') else t.Guest
            guest = cls(args.qemu, args.output / name)
            results[name] = run_frozen(guest, name) if name.startswith('frozen_') else run_case(guest, name)
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
        t.json_write(args.output / 'partial-results.json', results)
        print(name, 'PASS' if results[name]['pass'] else 'FAIL', flush=True)
    report = {'schema': 1, 'profile': PROFILE, 'qemu_sha256': sha(args.qemu),
              'harness_sha256': sha(__file__), 'target': target, 'import_pins': IMPORT_PINS,
              'results': results, 'pass': all(item['pass'] for item in results.values()),
              'scope': 'Dispatch-default opcodes0,9–15 only; serialized ordinary-RAM command execution without prefetch; no physical DMA claim.',
              'known_broken_exclusions': ['recognized-command invalid fields', 'command-read failures',
                  'STATUS W1C and full overflow recovery'],
              'not_qualified': ['optional recognized-command capabilities', 'partial control writes',
                  'MMIO/reentrant command or event memory', 'prefetched hardware commands',
                  'IRQ/ATS', 'requester invalidation/cache hits', 'physical DMA/drain/reclamation']}
    t.json_write(args.output / 'report.json', report)
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
