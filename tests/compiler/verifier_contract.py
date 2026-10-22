#!/usr/bin/env python3
"""Compare real-ingress verifier contracts with frozen independent JSONL.

The original 59 rows came from native verifier commit
114ad127ab7d848355b71f758bd077036f4c1e04; four bound-root rows came from the
same native verifier. These historical expectations do not qualify current source.
The golden records preserve exact diagnostics, partial/sentinel/null metrics and
independently derived resource bounds: 262144 operands, 65536 states, and the
revisit's four snapshots, 192 operands, 193 value facts and 64 payload bytes.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("expected", type=Path)
    parser.add_argument("--artifacts", required=True, type=Path)
    args = parser.parse_args()
    expected = args.expected.read_bytes()
    records = [json.loads(line) for line in expected.splitlines()]
    if not records:
        raise ValueError("empty verifier expectations")
    input_bytes = "".join(f"{row['protocol']}\t{row['fixture']}\n" for row in records).encode("ascii")
    args.artifacts.mkdir(parents=True, exist_ok=True)
    with (args.artifacts / "input.txt").open("xb") as stream:
        stream.write(input_bytes)
    stdout = args.artifacts / "candidate.jsonl"
    stderr = args.artifacts / "candidate.stderr"
    # This fixture verifies IR without executing it or spawning descendants.
    # subprocess.run kills and reaps it on timeout.
    with stdout.open("xb") as output, stderr.open("xb") as error:
        result = subprocess.run(
            [str(args.executable.resolve())], input=input_bytes, stdout=output, stderr=error, timeout=90, check=False
        )
    if result.returncode != 0:
        raise ValueError(f"fixture exited {result.returncode}")
    if stderr.read_bytes():
        raise ValueError("fixture produced unexpected stderr")
    actual = stdout.read_bytes()
    if actual != expected:
        expected_lines, actual_lines = expected.splitlines(keepends=True), actual.splitlines(keepends=True)
        for index in range(max(len(expected_lines), len(actual_lines))):
            want = expected_lines[index] if index < len(expected_lines) else b""
            got = actual_lines[index] if index < len(actual_lines) else b""
            if want != got:
                fixture = records[index]["fixture"] if index < len(records) else "extra output"
                raise ValueError(f"{fixture}, row {index + 1}: expected {want!r}; got {got!r}")
    print(f"{len(records)} verifier contracts passed: exact diagnostics, partial metrics and null distinctions")


if __name__ == "__main__":
    try:
        main()
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        print(f"verifier contract failed: {error}", file=sys.stderr)
        sys.exit(1)
