#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "${KERNEL_CONSOLE:-0}" != 0 ]]; then
    echo 'Self-test smoke rejects KERNEL_CONSOLE; use the separate console profile.' >&2
    exit 2
fi
mode="${1:-normal}"
build_environment=()
case "$mode" in
  normal) ;;
  --division-zero) build_environment+=(KERNEL_TEST_DIVISION=zero) ;;
  --division-remainder-zero) build_environment+=(KERNEL_TEST_DIVISION=remainder-zero) ;;
  --division-overflow) build_environment+=(KERNEL_TEST_DIVISION=overflow) ;;
  --division-remainder-min) build_environment+=(KERNEL_TEST_DIVISION=remainder-min) ;;
  --division-kernel-trap) build_environment+=(KERNEL_TEST_DIVISION=kernel-trap) ;;
  --unsigned-valid) build_environment+=(KERNEL_TEST_UNSIGNED=valid) ;;
  --unsigned-shift-count) build_environment+=(KERNEL_TEST_UNSIGNED=shift-count) ;;
  --unsigned-conversion-overflow) build_environment+=(KERNEL_TEST_UNSIGNED=conversion-overflow) ;;
  --unsigned-kernel-trap) build_environment+=(KERNEL_TEST_UNSIGNED=kernel-trap) ;;
  --schedule) build_environment+=(KERNEL_TEST_SCHEDULE=1) ;;
  --schedule-smp) build_environment+=(KERNEL_TEST_SCHEDULE=1) ;;
  --schedule-mmio) build_environment+=(KERNEL_TEST_SCHEDULE=1 KERNEL_TEST_PROGRAM_APIC_READ=1) ;;
  --schedule-no-apic) build_environment+=(KERNEL_TEST_SCHEDULE=1) ;;
  --schedule-forged) build_environment+=(KERNEL_TEST_SCHEDULE=1 KERNEL_TEST_SCHEDULE_FORGED=1) ;;
  --schedule-context) build_environment+=(KERNEL_TEST_SCHEDULE=1 KERNEL_TEST_SCHEDULE_CONTEXT=1) ;;
  --schedule-root) build_environment+=(KERNEL_TEST_SCHEDULE=1 KERNEL_TEST_SCHEDULE_ROOT=1) ;;
  --schedule-softint) build_environment+=(KERNEL_TEST_SCHEDULE=1 KERNEL_TEST_PROGRAM_SOFTINT=1) ;;
  --schedule-fpu) build_environment+=(KERNEL_TEST_SCHEDULE=1 KERNEL_TEST_PROGRAM_FPU=1) ;;
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
  --program-terminal-input) build_environment+=(KERNEL_TEST_TERMINAL_EVENT_INPUT=1) ;;
  --program-terminal-output) build_environment+=(KERNEL_TEST_TERMINAL_EVENT_OUTPUT=1) ;;
  --program-bad-return) build_environment+=(KERNEL_TEST_PROGRAM_BAD_RETURN=1) ;;
  --program-unknown-trap) build_environment+=(KERNEL_TEST_PROGRAM_UNKNOWN_TRAP=1) ;;
  --program-kernel-trap) build_environment+=(KERNEL_TEST_PROGRAM_KERNEL_TRAP=1) ;;
  --domain-code) build_environment+=(KERNEL_TEST_PROGRAM_FOREIGN_CODE=1) ;;
  --domain-stack) build_environment+=(KERNEL_TEST_PROGRAM_FOREIGN_STACK=1) ;;
  --domain-root-mismatch) build_environment+=(KERNEL_TEST_DOMAIN_ROOT_MISMATCH=1) ;;
  --no-nx) ;;
  *) echo 'Unknown kernel smoke mode' >&2; exit 2 ;;
esac
image_dir="$(env "${build_environment[@]}" ./scripts/kernel-build.sh --print-image-dir)"
if [[ "$mode" == normal ]]; then log="$image_dir/kernel-serial.log"
else log="$image_dir/kernel-${mode#--}.log"; fi
metadata="${log%.log}.metadata.json"
cp "$image_dir/user-metadata.json" "$metadata"
qemu="${QEMU:-qemu-system-x86_64}"
command -v "$qemu" >/dev/null || { echo 'BLOCKED: QEMU missing; image is built but emulator boot is unverified.' >&2; exit 2; }
mapfile -d '' -t qemu_argv < <(python3 -B scripts/qemu_transport.py argv --platform bios \
    --mode="$mode" --image "$image_dir/aurora.img" --qemu "$qemu" --data "${QEMU_DATA:-}")
(( ${#qemu_argv[@]} )) || { echo 'FAIL: empty QEMU command' >&2; exit 2; }
set +e
python3 -B scripts/qemu_transport.py run --timeout 15 --log "$log" -- "${qemu_argv[@]}"
status=$?
set -e
cat "$log"
if [[ "$mode" == --division-* ]]; then
    python3 tests/kernel-division-smoke.py "$status" "$log" "$mode" "$metadata"
elif [[ "$mode" == --unsigned-* ]]; then
    python3 tests/kernel-unsigned-smoke.py "$status" "$log" "$mode" "$metadata"
elif [[ "$mode" == --schedule* ]]; then
    python3 tests/kernel-schedule-smoke.py "$status" "$log" "$mode" "$metadata"
else
    python3 tests/kernel-smoke.py "$status" "$log" "$mode" "$metadata"
fi
echo "PASS: kernel emulator verification ($mode)"
