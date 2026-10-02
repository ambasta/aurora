#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mode="${1:-normal}"
build_environment=()
cpu=qemu64
case "$mode" in
  normal) ;;
  --fault) build_environment+=(KERNEL_TEST_DIVIDE_ERROR=1) ;;
  --page-fault) build_environment+=(KERNEL_TEST_PAGE_FAULT=1) ;;
  --wp) build_environment+=(KERNEL_TEST_WP=1) ;;
  --nx) build_environment+=(KERNEL_TEST_NX=1) ;;
  --stack) build_environment+=(KERNEL_TEST_STACK=1) ;;
  --user-read) build_environment+=(KERNEL_USER_PROBE_MODE=1) ;;
  --user-write) build_environment+=(KERNEL_USER_PROBE_MODE=2) ;;
  --user-cli) build_environment+=(KERNEL_USER_PROBE_MODE=3) ;;
  --user-code-write) build_environment+=(KERNEL_USER_PROBE_MODE=4) ;;
  --user-nx) build_environment+=(KERNEL_USER_PROBE_MODE=5) ;;
  --user-io) build_environment+=(KERNEL_USER_PROBE_MODE=6) ;;
  --program-bad-return) build_environment+=(KERNEL_TEST_PROGRAM_BAD_RETURN=1) ;;
  --program-unknown-trap) build_environment+=(KERNEL_TEST_PROGRAM_UNKNOWN_TRAP=1) ;;
  --program-kernel-trap) build_environment+=(KERNEL_TEST_PROGRAM_KERNEL_TRAP=1) ;;
  --no-nx) cpu=qemu64,-nx ;;
  *) echo 'Unknown kernel smoke mode' >&2; exit 2 ;;
esac
if [[ "$mode" == normal ]]; then log=build/kernel-serial.log
else
  log="build/kernel-${mode#--}.log"
  trap './scripts/kernel-build.sh >/dev/null' EXIT
fi
env "${build_environment[@]}" ./scripts/kernel-build.sh
metadata="${log%.log}.metadata.json"
cp build/user-metadata.json "$metadata"
qemu="${QEMU:-qemu-system-x86_64}"
command -v "$qemu" >/dev/null || { echo 'BLOCKED: QEMU missing; image is built but emulator boot is unverified.' >&2; exit 2; }
args=()
if [[ -n "${QEMU_DATA:-}" ]]; then args+=(-L "$QEMU_DATA"); fi
set +e
timeout 15 "$qemu" "${args[@]}" -machine pc -accel tcg -cpu "$cpu" -m 32M \
    -drive file=build/aurora.img,format=raw,if=ide -boot c \
    -nic none -display none -serial stdio -monitor none -no-reboot \
    -device isa-debug-exit,iobase=0xf4,iosize=0x04 > "$log" 2>&1
status=$?
set -e
cat "$log"
python3 tests/kernel-smoke.py "$status" "$log" "$mode" "$metadata"
echo "PASS: kernel emulator verification ($mode)"
