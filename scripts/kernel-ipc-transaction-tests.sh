#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
compiler="${AURORAC:-build/aurorac}"
# An observed binary hash is not an externally approved acceptance identity.
# The portable developer receipt route is reconciled when that independent
# workflow is accepted; this standalone lane requires an explicit selected pin.
: "${IPC_TRANSACTION_COMPILER_SHA256:?Set the reviewed compiler identity explicitly}"
if [[ -z "${AURORAC:-}" ]]; then make -C compiler; fi
identity=(--compiler-sha256 "$IPC_TRANSACTION_COMPILER_SHA256")
python3 -B -O tests/kernel-ipc-transition-native.py --compiler "$compiler" \
    "${identity[@]}" --candidate-cap-mib "${IPC_TRANSACTION_CAP_MIB:-128}"
