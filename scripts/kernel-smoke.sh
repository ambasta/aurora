#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mode="${1:-normal}"
case "$mode" in
  normal) ./scripts/kernel-build.sh; log=build/kernel-serial.log ;;
  --fault)
    trap './scripts/kernel-build.sh >/dev/null' EXIT
    KERNEL_TEST_DIVIDE_ERROR=1 ./scripts/kernel-build.sh
    log=build/kernel-fault.log ;;
  --page-fault)
    trap './scripts/kernel-build.sh >/dev/null' EXIT
    KERNEL_TEST_PAGE_FAULT=1 ./scripts/kernel-build.sh
    log=build/kernel-page-fault.log ;;
  *) echo 'usage: kernel-smoke.sh [--fault|--page-fault]' >&2; exit 2 ;;
esac
qemu="${QEMU:-qemu-system-x86_64}"
command -v "$qemu" >/dev/null || { echo 'BLOCKED: QEMU missing; image is built but emulator boot is unverified.' >&2; exit 2; }
args=()
if [[ -n "${QEMU_DATA:-}" ]]; then args+=(-L "$QEMU_DATA"); fi
set +e
timeout 15 "$qemu" "${args[@]}" -machine pc -accel tcg -cpu qemu64 -m 32M \
    -drive file=build/aurora.img,format=raw,if=ide -boot c \
    -nic none -display none -serial stdio -monitor none -no-reboot \
    -device isa-debug-exit,iobase=0xf4,iosize=0x04 > "$log" 2>&1
status=$?
set -e
cat "$log"
python3 tests/kernel-smoke.py "$status" "$log" "$mode"
echo "PASS: kernel emulator verification ($mode)"
