#!/usr/bin/env bash
# Endpoint refinement acceptance; does not build or qualify the Aurora kernel.
set -euo pipefail
cd "$(dirname "$0")"
version=$(lean --version)
case "$version" in
  'Lean (version 4.24.0, '*'commit 797c613eb9b6d4ec95db23e3e00af9ac6657f24b, Release)') ;;
  *) printf 'Wrong Lean toolchain: %s\n' "$version" >&2; exit 1 ;;
esac
printf '%s\n' "$version"
lake build R
output=$(mktemp)
trap 'rm -f "$output"' EXIT
lake env lean R/Audit.lean | tee "$output"
python3 - "$output" <<'PY'
import re
import sys

# Check the ACTUAL kernel dependency report, not a source-code substring claim.
allowed = {"propext", "Quot.sound"}
count = 0
for line in open(sys.argv[1]):
    line = line.strip()
    if not line:
        continue
    no_axioms = re.fullmatch(r"'Aurora\.R\.[^']+' does not depend on any axioms", line)
    dependency = re.fullmatch(r"'Aurora\.R\.[^']+' depends on axioms: \[(.*)\]", line)
    if no_axioms:
        count += 1
    elif dependency:
        actual = set(filter(None, dependency[1].split(", ")))
        if actual - allowed:
            sys.exit(f"Unapproved theorem dependencies: {actual - allowed}")
        count += 1
    else:
        sys.exit(f"Unexpected axiom audit output: {line}")
if count == 0:
    sys.exit("No exported theorem audit output")
print(f"Checked {count} theorem dependency reports; only propext/Quot.sound permitted.")
PY
