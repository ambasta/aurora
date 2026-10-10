#!/usr/bin/env bash
set -euxo pipefail
cd "$(dirname "$0")/.."

# This is a clean CI run. Developers can use ordinary incremental Meson commands.
# Keep native and emulator scopes visible, with separate original Meson logs.
meson setup build/container -Dlsp=true
meson compile -C build/container -j 2 --verbose
meson test -C build/container --suite full --no-rebuild --num-processes 2 \
    --verbose --print-errorlogs --logbase full
meson test -C build/container --suite lsp --no-rebuild --num-processes 2 \
    --verbose --print-errorlogs --logbase lsp

export AURORAC="$PWD/build/container/aurorac"
./scripts/kernel-run.sh bios
./scripts/kernel-run.sh uefi
