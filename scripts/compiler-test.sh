#!/usr/bin/env bash
# Convenience entrypoint to the canonical dependency-tracked compiler graph.
set -euo pipefail
if [[ $# == 1 && ( "$1" == --help || "$1" == -h ) ]]; then
    cat <<'HELP'
Usage: scripts/compiler-test.sh

Run the complete compiler-only Meson suite with an incremental current-source build.
Equivalent to make -C compiler test. No historical compiler hash is required.
Use environment overrides, for example CXX=g++-16 ./scripts/compiler-test.sh.
The existing developer-test contract validates compiler and flag selections.
Use make test for the full native aggregate; QEMU gates remain separate.
HELP
    exit 0
fi
if [[ $# != 0 ]]; then echo 'Usage: scripts/compiler-test.sh (or --help)' >&2; exit 2; fi
# These convenience commands start standalone runs; never inherit a sealed run.
if [[ -n "${AURORA_TEST_CONTEXT:-}" ]]; then
    echo 'This standalone shortcut rejects inherited AURORA_TEST_CONTEXT; start it outside the active supervised test run.' >&2
    exit 2
fi
cd "$(dirname "$0")/.."
for tool in make python3 "${CXX:-g++}"; do
    command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; exit 2; }
done
exec make -C compiler test
