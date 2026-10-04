"""Offline verifier; never launches QEMU or performs guest accesses.

The limited CTRL producer witness and the complete-run absence contract are
reported separately. Unexpected records are retained and make strict acceptance
fail. In particular, a valid CTRL write does not emit amdvi_mmio_write in the
pinned QEMU source; that event's absence proves nothing about valid writes.
"""
from collections import Counter
from pathlib import Path
import hashlib
import json
import re
import sys

ROOT = Path(__file__).resolve().parent


def main():
    read_json = lambda name: json.loads((ROOT / name).read_text())
    invocation = read_json('invocation.json')
    result = read_json('result.json')
    provenance = read_json('preflight-provenance.json')
    protocol = [json.loads(line) for line in (ROOT / 'protocol.jsonl').read_text().splitlines()]
    trace = (ROOT / 'trace.log').read_text().splitlines()
    for item in provenance['inputs']:
        assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest() == item['sha256']
    assert hashlib.sha256((ROOT / 'control.py').read_bytes()).hexdigest() == invocation['control_script_sha256']
    assert invocation['qemu_sha256'] == 'd3c1a558ad220e77a4412048c8d96b44f8c2b41c7ad2a4ecfe522a4b122fe067'
    assert read_json('process-result.json')['returncode'] == 0
    argv = invocation['argv']
    assert '-S' in argv and '-nodefaults' in argv
    for option, value in [('-machine', 'q35'), ('-accel', 'tcg'), ('-cpu', 'qemu64'),
                          ('-smp', '1'), ('-m', '128M'), ('-nic', 'none'),
                          ('-qmp', 'stdio'), ('-qtest', f'pipe:{ROOT}/qtest'),
                          ('-device', 'amd-iommu,pt=off,intremap=off,device-iotlb=off,xtsup=off')]:
        assert argv.count(option) == 1 and argv[argv.index(option) + 1] == value
    assert not set(argv) & {'-drive', '-blockdev', '-hda', '-hdb', '-cdrom', '-kernel', '-bios', '-enable-kvm'}
    assert not any('unix:' in value or 'tcp:' in value or 'nvme' in value for value in argv)
    enabled = (ROOT / 'trace-enable-events.txt').read_text().splitlines()
    help_events = (ROOT / 'trace-help-stdout.txt').read_text().splitlines() + (ROOT / 'trace-help-stderr.txt').read_text().splitlines()
    assert set(enabled) == {event for event in help_events if event.startswith('amdvi_')} | {'memory_region_ops_write', 'pci_cfg_write'}

    offsets = [0x18, 0x0, 0x8, 0x10, 0x20, 0x28, 0x38, 0x30, 0x2020]
    expected_reads = [f'readq {0xfed80000 + offset:#x}' for offset in offsets]
    expected_requests = expected_reads + ['writeq 0xfed80018 0x0', 'readq 0xfed80018'] + expected_reads
    requests = [entry['data'] for entry in protocol if entry['kind'] == 'qtest-request']
    responses = [entry['data'] for entry in protocol if entry['kind'] == 'qtest-response']
    expected_values = [0, 0, 0, 0, 0, 0, 0, 0x29d3, 0]
    expected_responses = [f'OK 0x{value:016x}' for value in expected_values] + ['OK', 'OK 0x0000000000000000'] + [f'OK 0x{value:016x}' for value in expected_values]
    assert requests == expected_requests and responses == expected_responses
    native = (ROOT / 'qtest-native.log').read_text().splitlines()
    assert [re.sub(r'^\[R [^]]+\] ', '', line) for line in native if line.startswith('[R ')] == requests
    assert [re.sub(r'^\[S [^]]+\] ', '', line) for line in native if line.startswith('[S ')] == responses
    allowed_qmp = {'qmp_capabilities', 'query-status', 'query-block', 'query-pci', 'human-monitor-command', 'quit'}
    qmp_requests = [entry['data'] for entry in protocol if entry['kind'] == 'qmp-request']
    assert all(request['execute'] in allowed_qmp for request in qmp_requests)
    assert [request['arguments']['command-line'] for request in qmp_requests if request['execute'] == 'human-monitor-command'] == ['info qtree', 'info mtree']
    qmp_responses = [entry['data'] for entry in protocol if entry['kind'] == 'qmp-response']
    assert not any(response.get('event') == 'RESUME' or 'error' in response for response in qmp_responses)
    statuses = [response['return'] for response in qmp_responses if isinstance(response.get('return'), dict) and 'running' in response['return']]
    assert statuses == [{'status': 'prelaunch', 'running': False}] * 2
    assert read_json('query-pci-before.json') == read_json('query-pci-after.json')
    assert result['registers_before'] == result['registers_after'] == read_json('registers-before.json') == read_json('registers-after.json')
    assert [item['value'] for item in result['registers_before'].values()] == expected_values
    assert result['control_register_checks_passed'] is True

    event_counts = Counter(line.split()[0] for line in trace)
    assert all(event in enabled for event in event_counts)
    generic_re = re.compile(r"^memory_region_ops_write cpu (-?\d+) mr (0x[0-9a-f]+) addr (0x[0-9a-f]+) value (0x[0-9a-f]+) size (\d+) name '([^']+)'$")
    generic_writes = []
    for index, line in enumerate(trace):
        if not line.startswith('memory_region_ops_write '):
            continue
        match = generic_re.fullmatch(line)
        assert match, line
        cpu, identity, address, value, size, name = match.groups()
        generic_writes.append({'trace_line': index + 1, 'cpu': int(cpu), 'region_identity': identity,
                               'address': int(address, 16), 'value': int(value, 16), 'width': int(size),
                               'region_name': name, 'raw': line})
    target_writes = [write for write in generic_writes if write['region_name'] == 'amdvi-mmio']
    assert len(target_writes) == 1
    target = target_writes[0]
    assert target['cpu'] == -1 and target['address'] == 0xfed80018 and target['value'] == 0 and target['width'] == 8
    target['region_base'] = 0xfed80000
    target['relative_offset'] = target['address'] - target['region_base']
    assert target['relative_offset'] == 0x18
    mtree = (ROOT / 'mtree.txt').read_text()
    assert '00000000fed80000-00000000fed83fff' in mtree and 'amdvi-mmio' in mtree
    index = target['trace_line'] - 1
    assert trace[index + 1:index + 4] == [
        'amdvi_mmio_read AMDVI_MMIO_CONTROL read addr 0x18, size 8 offset 0x18',
        'amdvi_control_status MMIO_STATUS state 0x0',
        'amdvi_command_error error: Executing commands with command buffer disabled 0x0',
    ]
    mmio_read_re = re.compile(r'^amdvi_mmio_read (\w+) read addr (0x[0-9a-f]+), size 8 offset (0x[0-9a-f]+)$')
    observed_offsets = []
    for line in trace:
        if line.startswith('amdvi_mmio_read '):
            match = mmio_read_re.fullmatch(line)
            assert match and match[2] == match[3], line
            observed_offsets.append(int(match[2], 16))
    assert observed_offsets == offsets + [0x18, 0x18] + offsets
    assert event_counts['amdvi_control_status'] == event_counts['amdvi_command_error'] == 1
    assert event_counts['amdvi_mmio_write'] == event_counts['pci_cfg_write'] == event_counts['amdvi_command_exec'] == 0

    expected_event_types = {'amdvi_iotlb_reset', 'amdvi_mmio_read', 'amdvi_control_status', 'amdvi_command_error'}
    unexpected = [{'trace_line': i + 1, 'raw': line} for i, line in enumerate(trace)
                  if line.split()[0] not in expected_event_types and i != index]
    verification = {
        'control_write_witness_passed': True,
        'protocol_and_state_checks_passed': True,
        'strict_whole_run_absence_contract_passed': not unexpected,
        'trace_event_counts': dict(sorted(event_counts.items())),
        'generic_writes': generic_writes,
        'control_write': target,
        'qtest_requests': len(requests), 'qtest_read_requests': 19, 'qtest_write_requests': 1,
        'qmp_status_before_after': statuses,
        'unexpected_records': unexpected,
        'named_mmio_write_event_limitation': 'The pinned source emits amdvi_mmio_write only on an invalid-range branch. Its absence does not establish absence of valid writes.',
        'expected_command_error_explanation': 'CTRL=0 causes amdvi_cmdbuf_run to emit disabled-buffer command_error(0) and return before executing any command.',
        'initialization_observation': 'The complete trace contains an amdvi-ir write and four IR trace records before the first qtest MMIO read. They are retained and fail the whole-run absence criterion.',
        'scope': 'Separate trace coverage evidence only; not a clean controller run, DMA isolation proof, or physical AMD validation.',
    }
    (ROOT / 'trace-verification.json').write_text(json.dumps(verification, indent=2) + '\n')
    print(json.dumps(verification, indent=2))
    return 0 if not unexpected else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (AssertionError, KeyError, ValueError) as exc:
        print(f'Verification assertion failed: {exc}', file=sys.stderr)
        raise
