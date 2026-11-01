#!/usr/bin/env python3
"""Mutation runner for the SAME Lean executable; not a parser/semantic validator.
Requires a separately captured full production artifact, not a host-pruned AST.
"""
import json
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time

source = Path(sys.argv[1]).read_bytes()
exe = Path(__file__).parent / '.lake/build/bin/publication-probe'
lines = source.splitlines(keepends=True)

def change_line(tag, change):
    changed = list(lines)
    index = next(i for i, line in enumerate(changed) if line.startswith(tag))
    changed[index] = change(changed[index])
    return b''.join(changed)

def field(line, index, value):
    words = line.rstrip(b'\n').split(b' ')
    words[index] = value
    return b' '.join(words) + b'\n'

cases = [
    ('original', source, True),
    ('unknown-tag', b'unknown\n' + source, False),
    ('missing-final-LF', source[:-1], False),
    ('trailing-display', source + b'origin harmless\n', False),
    ('duplicate-type', change_line(b'ir-type 0 ', lambda x: x + x), False),
    ('missing-type', change_line(b'ir-type 0 ', lambda _: b''), False),
    ('bad-type-id', change_line(b'ir-type 0 ', lambda x: field(x, 1, b'-1')), False),
    ('bad-type-range', change_line(b'ir-type 0 ', lambda x: field(x, 3, b'9223372036854775807')), False),
    ('overflow', change_line(b'ir-counts ', lambda x: field(x, 1, b'9223372036854775808')), False),
    ('bad-body-position', change_line(b'ir-code ', lambda x: field(x, 2, b'1')), False),
    ('missing-body-end', change_line(b'ir-end-body ', lambda _: b''), False),
    ('wrong-body-count', change_line(b'ir-end-body ', lambda x: field(x, 2, b'0')), False),
    ('wrong-trailer', change_line(b'ir-end ', lambda x: field(x, 1, b'0')), False),
    ('control-byte', change_line(b'origin ', lambda x: x[:-1] + b'\x00\n'), False),
    # D1 does not validate operation semantics/CFG outside a selected closure.
    ('opaque-unselected-form', change_line(b'ir-code ', lambda x: field(x, 7, b'999')), True),
    ('opaque-unselected-target', change_line(b'ir-code ', lambda x: field(x, 4, b'999')), True),
]
results = []
with tempfile.TemporaryDirectory() as temporary:
    for name, content, expected in cases:
        path = Path(temporary) / (name + '.ir')
        path.write_bytes(content)
        start = time.monotonic()
        run = subprocess.run([str(exe), str(path)], capture_output=True, text=True, timeout=30)
        if run.returncode not in (0, 1):
            raise SystemExit(f'{name}: abnormal termination {run.returncode}: {run.stderr}')
        if run.returncode == 1 and run.stderr.strip() != 'uncaught exception: artifact structure rejected':
            raise SystemExit(f'{name}: unexpected failure: {run.stderr}')
        passed = run.returncode == 0
        result = dict(case=name, expected=expected, accepted=passed,
                      wall_seconds=time.monotonic()-start, stdout=run.stdout.strip(),
                      stderr=run.stderr.strip())
        results.append(result)
        if passed != expected:
            print(json.dumps(results, indent=2))
            raise SystemExit('mutation outcome mismatch')
print(json.dumps(dict(scope='native execution checks, not concrete kernel proofs',
                     cases=results, max_child_rss_KiB=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss), indent=2))
