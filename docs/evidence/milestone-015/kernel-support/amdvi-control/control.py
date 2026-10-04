"""One disposable, stopped-CPU, same-zero AMD-Vi CTRL trace control.

Run at most once. This intentionally does not enable translation, queues,
interrupt remapping, or PCI bus mastering. QMP uses process pipes; qtest uses
local filesystem FIFOs. There are no sockets or guest storage backends.
"""
from pathlib import Path
import hashlib
import json
import os
import select
import subprocess
import time
import traceback

ROOT = Path(__file__).resolve().parent
QEMU = Path('/tmp/aurora-qemu/root/usr/bin/qemu-system-x86_64')
QEMU_SHA256 = 'd3c1a558ad220e77a4412048c8d96b44f8c2b41c7ad2a4ecfe522a4b122fe067'
BASE = 0xfed80000
# Only source-verified, aligned 64-bit registers with ordinary load semantics.
REGISTERS = {
    0x18: ('control', 0),
    0x00: ('device_table', 0),
    0x08: ('command_base', 0),
    0x10: ('event_base', 0),
    0x20: ('exclusion_base', 0),
    0x28: ('exclusion_limit', 0),
    0x38: ('ppr_base', 0),
    0x30: ('extended_features', 0x29d3),
    0x2020: ('status', 0),
}


def save(name, value):
    (ROOT / name).write_text(json.dumps(value, indent=2) + '\n')


def main():
    assert hashlib.sha256(QEMU.read_bytes()).hexdigest() == QEMU_SHA256
    provenance = json.loads((ROOT / 'preflight-provenance.json').read_text())
    for item in provenance['inputs']:
        assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest() == item['sha256']
    # Exclusive marker prevents accidental execution of a second control.
    with (ROOT / 'runtime-started.json').open('x') as f:
        json.dump({'started_unix_ns': time.time_ns(), 'pid': os.getpid()}, f)
        f.write('\n')

    args = [str(QEMU), '-L', '/tmp/aurora-qemu/firmware',
            '-machine', 'q35', '-accel', 'tcg', '-cpu', 'qemu64',
            '-smp', '1', '-m', '128M', '-nodefaults', '-S', '-nic', 'none',
            '-display', 'none', '-serial', 'none', '-monitor', 'none',
            '-no-reboot', '-no-shutdown',
            '-device', 'amd-iommu,pt=off,intremap=off,device-iotlb=off,xtsup=off',
            '-qmp', 'stdio', '-qtest', f'pipe:{ROOT}/qtest',
            '-qtest-log', str(ROOT / 'qtest-native.log'),
            '-trace', f'events={ROOT}/trace-enable-events.txt,file={ROOT}/trace.log']
    env = os.environ.copy()
    env['LD_LIBRARY_PATH'] = '/tmp/aurora-qemu/root/usr/lib/x86_64-linux-gnu'
    save('invocation.json', {
        'argv': args,
        'environment_override': {'LD_LIBRARY_PATH': env['LD_LIBRARY_PATH']},
        'qemu_sha256': QEMU_SHA256,
        'control_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'transport': {'qmp': 'child stdin/stdout', 'qtest': 'local filesystem FIFOs'},
        'purpose': 'Separate trace coverage control; one already-zero CTRL write. CPUs never started; no guest firmware execution or guest storage.',
        'firmware_note': 'No explicit firmware image is supplied. Q35 default BIOS may be mapped from -L, but -S and absence of cont ensure it never executes.',
        'limitations': ['pt=off is not DMA isolation', 'amdvi_mmio_write event does not cover valid writes in the pinned source'],
    })

    protocol = (ROOT / 'protocol.jsonl').open('x')
    p = None
    fifo_fds = []
    error = None
    result = None

    def record(kind, data):
        protocol.write(json.dumps({'monotonic_ns': time.monotonic_ns(), 'kind': kind, 'data': data}) + '\n')
        protocol.flush()

    class Lines:
        def __init__(self, fd):
            self.fd = fd
            self.buffer = b''

        def read(self):
            deadline = time.monotonic() + 5
            while b'\n' not in self.buffer:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select([self.fd], [], [], remaining)[0]:
                    raise TimeoutError('Timed out waiting for local protocol response')
                data = os.read(self.fd, 65536)
                if not data:
                    raise EOFError('QEMU protocol reached EOF')
                self.buffer += data
            line, self.buffer = self.buffer.split(b'\n', 1)
            return line.decode()

    def qmp(name, arguments=None):
        request = {'execute': name}
        if arguments is not None:
            request['arguments'] = arguments
        record('qmp-request', request)
        p.stdin.write((json.dumps(request) + '\n').encode())
        p.stdin.flush()
        while True:
            answer = json.loads(qmp_lines.read())
            record('qmp-response', answer)
            if 'error' in answer:
                raise RuntimeError(answer)
            if 'return' in answer:
                return answer['return']

    writes = 0

    def qtest(line):
        nonlocal writes
        parts = line.split()
        if parts[0] == 'writeq':
            assert line == 'writeq 0xfed80018 0x0'
            assert writes == 0
            writes += 1
        else:
            assert len(parts) == 2 and parts[0] == 'readq'
            assert int(parts[1], 0) - BASE in REGISTERS
        record('qtest-request', line)
        os.write(qtest_in, (line + '\n').encode())
        response = qtest_lines.read().strip()
        record('qtest-response', response)
        assert response == 'OK' or response.startswith('OK '), response
        fields = response.split()
        return int(fields[1], 0) if len(fields) > 1 else None

    def read_snapshot():
        snapshot = {}
        for offset, (name, expected) in REGISTERS.items():
            value = qtest(f'readq {BASE + offset:#x}')
            snapshot[name] = {'offset': hex(offset), 'address': hex(BASE + offset), 'value': value}
            assert value == expected, (name, hex(value), hex(expected))
        return snapshot

    try:
        for suffix in ['in', 'out']:
            os.mkfifo(ROOT / f'qtest.{suffix}')
        qtest_in = os.open(ROOT / 'qtest.in', os.O_RDWR)
        fifo_fds.append(qtest_in)
        qtest_out = os.open(ROOT / 'qtest.out', os.O_RDWR)
        fifo_fds.append(qtest_out)
        qtest_lines = Lines(qtest_out)
        with (ROOT / 'stderr.log').open('x') as err:
            p = subprocess.Popen(args, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, bufsize=0)
            qmp_lines = Lines(p.stdout.fileno())
            greeting = json.loads(qmp_lines.read())
            record('qmp-greeting', greeting)
            qmp('qmp_capabilities')
            status_before = qmp('query-status')
            assert status_before['running'] is False and status_before['status'] == 'prelaunch'
            assert qmp('query-block') == []
            pci_before = qmp('query-pci')
            save('query-pci-before.json', pci_before)
            tree = qmp('human-monitor-command', {'command-line': 'info qtree'})
            (ROOT / 'qtree.txt').write_text(tree)
            mtree = qmp('human-monitor-command', {'command-line': 'info mtree'})
            (ROOT / 'mtree.txt').write_text(mtree)
            assert 'amdvi-mmio' in mtree
            assert '00000000fed80000-00000000fed83fff' in mtree
            before = read_snapshot()
            save('registers-before.json', before)
            # The only guest write authorized for this entire execution.
            qtest('writeq 0xfed80018 0x0')
            assert qtest('readq 0xfed80018') == 0
            after = read_snapshot()
            save('registers-after.json', after)
            assert after == before and writes == 1
            status_after = qmp('query-status')
            assert status_after['running'] is False and status_after['status'] == 'prelaunch'
            assert qmp('query-block') == []
            pci_after = qmp('query-pci')
            save('query-pci-after.json', pci_after)
            assert pci_after == pci_before
            result = {'control_register_checks_passed': True,
                      'single_write': {'address': hex(BASE + 0x18), 'relative_offset': '0x18', 'width': 8, 'value': 0},
                      'registers_before': before, 'registers_after': after,
                      'status_before': status_before, 'status_after': status_after,
                      'block_backends_before_after': [], 'pci_topology_unchanged': True,
                      'guest_firmware_executed': False, 'guest_pci_configuration_writes': 0,
                      'guest_other_mmio_writes': 0, 'bme_requested': False,
                      'iommu_translation_enabled': False, 'command_buffer_enabled': False,
                      'event_log_enabled': False, 'interrupts_enabled': False,
                      'trace_verification': 'Run verify-trace.py over preserved complete trace.'}
    except BaseException:
        error = traceback.format_exc()
        (ROOT / 'failure.txt').write_text(error)
    finally:
        if p is not None and p.poll() is None:
            try:
                qmp('quit')
                p.wait(timeout=5)
            except BaseException:
                (ROOT / 'shutdown-failure.txt').write_text(traceback.format_exc())
                p.terminate()
                p.wait(timeout=5)
        if p is not None:
            save('process-result.json', {'returncode': p.returncode, 'pid': p.pid})
        for fd in fifo_fds:
            os.close(fd)
        protocol.close()
    if error:
        print(error, end='')
        return 1
    assert p.returncode == 0, p.returncode
    save('result.json', result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
