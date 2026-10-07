#!/usr/bin/env bash
# Friendly normal-boot entrypoint; the existing smoke runners own QEMU and checks.
set -euo pipefail
usage() {
    cat <<'HELP'
Usage: scripts/kernel-run.sh [bios|uefi]

Build and verify one normal, headless QEMU boot (default: bios).
The boot self-tests finish automatically; this is not an interactive OS shell.
Serial output is printed after QEMU exits. The existing smoke runner validates it.

Overrides (environment, one executable/path each):
  CXX        GNU C++23 compiler (default: g++)
  UEFI_LD    GNU PE linker with i386pep (auto-detected when omitted)
  QEMU       QEMU executable (default: qemu-system-x86_64)
  QEMU_DATA  Optional QEMU firmware/data directory
  OVMF       Explicit combined OVMF ROM (otherwise discover installed firmware)
  OVMF_CODE  Split firmware code, with OVMF_VARS from the same build
  OVMF_VARS  Split variable-store template (changes are discarded)
  OVMF_DIR   Search only this directory for a supported firmware pair/ROM

Examples:
  ./scripts/kernel-run.sh
  OVMF=/path/to/OVMF.fd ./scripts/kernel-run.sh uefi
  CXX=g++-16 QEMU=/path/to/qemu-system-x86_64 ./scripts/kernel-run.sh bios
HELP
}
if [[ $# == 1 && ( "$1" == --help || "$1" == -h ) ]]; then usage; exit 0; fi
if [[ $# -gt 1 ]]; then usage >&2; exit 2; fi
mode="${1:-bios}"
case "$mode" in bios|uefi) ;; *) usage >&2; exit 2 ;; esac
# These convenience commands start standalone runs; never inherit a sealed run.
if [[ -n "${AURORA_TEST_CONTEXT:-}" ]]; then
    echo 'This standalone shortcut rejects inherited AURORA_TEST_CONTEXT; start it outside the active supervised test run.' >&2
    exit 2
fi
cd "$(dirname "$0")/.."
# Never silently turn the normal developer command into a fault-injection run.
for name in "${!KERNEL_TEST_@}" KERNEL_USER_PROBE_MODE KERNEL_CONSOLE UEFI_MODE; do
    [[ -n "$name" ]] || continue
    if [[ -n "${!name:-}" ]]; then
        echo "Unset $name before a normal boot; use the smoke scripts for fault modes." >&2
        exit 2
    fi
done
qemu="${QEMU:-qemu-system-x86_64}"
for tool in "$qemu" timeout; do
    command -v "$tool" >/dev/null || { echo "Missing dependency: $tool; QEMU boot was not started." >&2; exit 2; }
done
if [[ -n "${QEMU_DATA:-}" && ! -d "$QEMU_DATA" ]]; then
    echo 'QEMU_DATA must name an existing QEMU firmware/data directory.' >&2
    exit 2
fi
if [[ "$mode" == uefi ]]; then
    source ./scripts/uefi-firmware.sh
    uefi_firmware_select
    echo 'Running normal UEFI boot self-tests in QEMU (30-second limit).'
    exec ./scripts/kernel-uefi-smoke.sh normal
fi
echo 'Running normal BIOS boot self-tests in QEMU (15-second limit).'
exec ./scripts/kernel-smoke.sh normal
