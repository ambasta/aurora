#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mode="${1:-normal}"
firmware="${OVMF:-/usr/share/ovmf/OVMF.fd}"
qemu="${QEMU:-qemu-system-x86_64}"
[[ -r "$firmware" ]] || { echo 'BLOCKED: OVMF firmware missing' >&2; exit 2; }
command -v "$qemu" >/dev/null || { echo 'BLOCKED: QEMU missing' >&2; exit 2; }
UEFI_MODE="$mode" ./scripts/kernel-uefi-build.sh
if [[ "$mode" != normal ]]; then trap './scripts/kernel-uefi-build.sh >/dev/null' EXIT; fi
args=()
if [[ -n "${QEMU_DATA:-}" ]]; then args+=(-L "$QEMU_DATA"); fi
log="build/uefi/$mode.log"
set +e
timeout 30 "$qemu" "${args[@]}" -machine q35 -accel tcg -cpu qemu64 -smp 1 -m 128M \
    -bios "$firmware" -drive format=raw,file=fat:ro:build/uefi/esp,snapshot=on \
    -nic none -display none -serial stdio -monitor none -no-reboot \
    -device isa-debug-exit,iobase=0xf4,iosize=0x04 >"$log" 2>&1
status=$?
set -e
cat "$log"
python3 tests/kernel-uefi-smoke.py "$status" "$log" "$mode"
echo "PASS: actual OVMF UEFI gate ($mode)"
