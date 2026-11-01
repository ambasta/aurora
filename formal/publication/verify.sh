#!/usr/bin/env bash
# Standalone artifact-consumer proof gate; not a kernel/compiler qualification.
set -euo pipefail
cd "$(dirname "$0")"
case "$(lean --version)" in
  'Lean (version 4.24.0, '*'commit 797c613eb9b6d4ec95db23e3e00af9ac6657f24b, Release)') ;;
  *) echo 'Wrong Lean toolchain' >&2; exit 1 ;;
esac
lake build Publication Publication.Tests publication-probe
lake env lean Publication/RuntimeTests.lean
output=$(mktemp)
trap 'rm -f "$output"' EXIT
lake env lean Publication/Audit.lean | tee "$output"
python3 - "$output" <<'PY'
import re
import sys
allowed = {'propext', 'Quot.sound'}
count = 0
for line in open(sys.argv[1]):
    line = line.strip()
    if not line:
        continue
    empty = re.fullmatch(r"'Aurora\.Publication\.[^']+' does not depend on any axioms", line)
    deps = re.fullmatch(r"'Aurora\.Publication\.[^']+' depends on axioms: \[(.*)\]", line)
    if empty:
        count += 1
    elif deps:
        actual = set(filter(None, deps[1].split(', ')))
        if actual - allowed:
            sys.exit(f'Unapproved dependencies: {actual - allowed}')
        count += 1
    else:
        sys.exit(f'Unexpected audit output: {line}')
if count != 26:
    sys.exit(f'Expected twenty-six theorem audits, got {count}')
print(f'Checked {count} theorem dependency reports.')
PY
