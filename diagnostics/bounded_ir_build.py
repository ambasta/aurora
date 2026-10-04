#!/usr/bin/env python3
"""Recorded compiler-only limits for the approved minimal-debug IR test build."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        raise RuntimeError('missing compiler command')
    executable = shutil.which(command[0])
    if not executable:
        raise RuntimeError('compiler executable unavailable')
    command[0] = executable
    required = ('-O1', '-g1', '-fsanitize=address,undefined',
                '-fno-omit-frame-pointer', '-fno-sanitize-recover=all')
    if not all(flag in command for flag in required) or '-g' in command:
        raise RuntimeError('this recorded accommodation requires exact approved sanitizer/debug flags')
    root = Path(__file__).resolve().parents[1]
    test_source = root / 'tests/compiler/ir_tests.cpp'
    if not any(not value.startswith('-') and Path(value).resolve() == test_source for value in command[1:]):
        raise RuntimeError('bounded accommodation applies only to the IR test translation unit')
    evidence = args.evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    temporary = evidence / 'gcc-temporary'
    temporary.mkdir()
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    record = dict(command=command, cwd=os.getcwd(), tool_sha256=sha(Path(executable)),
                  driver_sha256=sha(Path(__file__)),
                  environment={'TMPDIR': str(temporary)},
                  limits={'address_space_bytes': 2 * 1024**3, 'cpu_seconds': [120, 130],
                          'wall_seconds': 180, 'regular_file_bytes': 512 * 1024**2, 'core_bytes': 0},
                  source_sha256={str(path.relative_to(root)): sha(path)
                                 for path in list((root / 'compiler').glob('*.hpp')) + [test_source]})
    (evidence / 'invocation.json').write_text(json.dumps(record, indent=2) + '\n')
    started = time.monotonic()
    pid = os.fork()
    if pid == 0:
        os.setsid()
        resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (120, 130))
        resource.setrlimit(resource.RLIMIT_FSIZE, (512 * 1024**2,) * 2)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        env = os.environ.copy()
        env['TMPDIR'] = str(temporary)
        with (evidence / 'stdout.log').open('wb') as out, (evidence / 'stderr.log').open('wb') as err:
            os.dup2(out.fileno(), 1)
            os.dup2(err.fileno(), 2)
            os.execve(executable, command, env)
    deadline = False
    while True:
        waited, status, usage = os.wait4(pid, os.WNOHANG)
        if waited:
            break
        if time.monotonic() - started > 180:
            deadline = True
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            _, status, usage = os.wait4(pid, 0)
            break
        time.sleep(0.1)
    record.update(exit_code=os.waitstatus_to_exitcode(status),
                  wall_seconds=time.monotonic() - started, max_rss_kib=usage.ru_maxrss,
                  user_seconds=usage.ru_utime, system_seconds=usage.ru_stime,
                  harness_deadline_kill=deadline)
    (evidence / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({key: record[key] for key in ('exit_code', 'wall_seconds', 'max_rss_kib',
                                                 'harness_deadline_kill')}), flush=True)
    if record['exit_code'] != 0:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
