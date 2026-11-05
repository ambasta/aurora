#!/usr/bin/env bash
# Focused source-binding proof gate; not compiler/kernel qualification.
set -euo pipefail
cd "$(dirname "$0")"
case "$(lean --version)" in
  'Lean (version 4.24.0, '*'commit 797c613eb9b6d4ec95db23e3e00af9ac6657f24b, Release)') ;;
  *) echo 'Wrong Lean toolchain' >&2; exit 1 ;;
esac
# Audit-only migration proofs are deliberately absent from the production root.
# Build their dependency closure explicitly so this gate also works from clean caches.
lake build SourceBinding.LegacyLeafCompatibility SourceBinding.LegacyEffectEquivalence SourceBinding SourceBinding.Tests SourceBinding.CallProjectionTests SourceBinding.BitTests SourceBinding.LeafTests SourceBinding.StringTests SourceBinding.FreeTests SourceBinding.RuntimePrimitiveTests SourceBinding.LocalBindingTests SourceBinding.FramePolicySpec SourceBinding.RuntimeExpressionTests SourceBinding.RuntimeEvaluationTests SourceBinding.RuntimeEntryTests SourceBinding.RuntimeCallTests SourceBinding.RuntimeNestedCallTests SourceBinding.RuntimeStatementTests SourceBinding.RuntimeBodyExecutionTests SourceBinding.OwnedWordsTests SourceBinding.EffectScopeTests SourceBinding.EffectMachineBoundaryTests source-binding-probe
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
lake env lean SourceBinding/CallProjectionTests.lean
lake env lean SourceBinding/CallFootprintTests.lean
lake env lean SourceBinding/RequestBounds.lean
lake env lean SourceBinding/RequestShape.lean
lake env lean SourceBinding/BitTests.lean
lake env lean SourceBinding/LeafTests.lean
lake env lean SourceBinding/StringTests.lean
lake env lean SourceBinding/FreeTests.lean
lake env lean SourceBinding/RuntimePrimitiveTests.lean
lake env lean SourceBinding/LocalBindingTests.lean
lake env lean SourceBinding/RuntimeExpressionTests.lean
lake env lean SourceBinding/RuntimeEvaluationTests.lean
lake env lean SourceBinding/RuntimeEntryTests.lean
lake env lean SourceBinding/RuntimeStatementTests.lean
lake env lean SourceBinding/RuntimeBodyExecutionTests.lean
lake env lean SourceBinding/RuntimeCallTests.lean
lake env lean SourceBinding/RuntimeNestedCallTests.lean
lake env lean SourceBinding/OwnedWordsTests.lean
lake env lean SourceBinding/EffectScopeTests.lean
lake env lean SourceBinding/EffectMachineBoundaryTests.lean
output=$(mktemp)
spec_output=$(mktemp)
trap 'rm -f "$output" "$spec_output"' EXIT
lake env lean SourceBinding/Audit.lean | tee "$output"
lake env lean SourceBinding/FramePolicyAudit.lean | tee "$spec_output"
python3 - "$output" "$spec_output" <<'PY'
import re
import sys
allowed = {'propext', 'Quot.sound'}
for path, expected, label, prefix in [
    (sys.argv[1], 664, 'source-binding', 'Aurora.SourceBinding.'),
    (sys.argv[2], 20, 'independent frame-policy specification', 'Aurora.SourceBinding.FramePolicy.'),
]:
    count = 0
    # Lean wraps long dependency lists after commas. Normalize only that
    # whitespace; the complete report grammar, count, and allowlist stay strict.
    reports = re.sub(r",\n[ \t]+", ", ", open(path).read())
    for line in reports.splitlines():
        line = line.strip()
        if not line:
            continue
        empty = re.fullmatch(r"'" + re.escape(prefix) + r"[^']+' does not depend on any axioms", line)
        deps = re.fullmatch(r"'" + re.escape(prefix) + r"[^']+' depends on axioms: \[(.*)\]", line)
        if empty:
            count += 1
        elif deps:
            actual = set(filter(None, deps[1].split(', ')))
            if actual - allowed:
                sys.exit(f'Unapproved {label} dependencies: {actual - allowed}')
            count += 1
        else:
            sys.exit(f'Unexpected {label} audit output: {line}')
    if count != expected:
        sys.exit(f'Expected {expected} {label} theorem audits, got {count}')
    print(f'Checked {count} {label} theorem dependency reports.')
PY
