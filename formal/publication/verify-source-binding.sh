#!/usr/bin/env bash
# Focused source-binding proof gate; not compiler/kernel qualification.
set -euo pipefail
cd "$(dirname "$0")"
case "$(lean --version)" in
  'Lean (version 4.24.0, '*'commit 797c613eb9b6d4ec95db23e3e00af9ac6657f24b, Release)') ;;
  *) echo 'Wrong Lean toolchain' >&2; exit 1 ;;
esac
lake build SourceBinding SourceBinding.Tests source-binding-probe
lake env lean SourceBinding/RuntimeTests.lean
lake env lean SourceBinding/MethodTests.lean
lake env lean SourceBinding/IdentityTests.lean
lake env lean SourceBinding/PrimitiveTests.lean
lake env lean SourceBinding/EntryTests.lean
lake env lean SourceBinding/GuardTests.lean
lake env lean SourceBinding/SafetyTests.lean
lake env lean SourceBinding/StatefulTests.lean
lake env lean SourceBinding/BodySyntaxTests.lean
lake env lean SourceBinding/EffectCodeTests.lean
lake env lean SourceBinding/BodyProofTests.lean
lake env lean SourceBinding/ArgumentValueTests.lean
lake env lean SourceBinding/CallTests.lean
lake env lean SourceBinding/CallMachineTests.lean
output=$(mktemp)
trap 'rm -f "$output"' EXIT
lake env lean SourceBinding/Audit.lean | tee "$output"
python3 - "$output" <<'PY'
import re
import sys
allowed = {'propext', 'Quot.sound'}
count = 0
for line in open(sys.argv[1]):
    line = line.strip()
    if not line:
        continue
    empty = re.fullmatch(r"'Aurora\.SourceBinding\.[^']+' does not depend on any axioms", line)
    deps = re.fullmatch(r"'Aurora\.SourceBinding\.[^']+' depends on axioms: \[(.*)\]", line)
    if empty:
        count += 1
    elif deps:
        actual = set(filter(None, deps[1].split(', ')))
        if actual - allowed:
            sys.exit(f'Unapproved dependencies: {actual - allowed}')
        count += 1
    else:
        sys.exit(f'Unexpected audit output: {line}')
if count != 111:
    sys.exit(f'Expected one hundred eleven theorem audits, got {count}')
print(f'Checked {count} source-binding theorem dependency reports.')
PY
