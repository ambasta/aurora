#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
clock_plan=false
if [[ "${1-}" == --clock-plan ]]; then clock_plan=true; shift; fi
if (( $# > 1 )); then echo 'Expected one exact UEFI mode' >&2; exit 2; fi
mode="${1-normal}"
clock_profile="$(python3 scripts/kernel_emulator_clock.py profile "$mode")"
source ./scripts/uefi-firmware.sh
if [[ "$clock_plan" == true ]]; then
    uefi_firmware_select --plan
else
    uefi_firmware_select
fi
qemu="${QEMU:-qemu-system-x86_64}"
if [[ "$clock_plan" == false ]]; then
    command -v "$qemu" >/dev/null || { echo 'BLOCKED: QEMU missing' >&2; exit 2; }
    # Snapshot failures must also restore a normal image if its image gate fails.
    if [[ "$mode" == snapshot* ]]; then trap 'UEFI_MODE=normal ./scripts/kernel-uefi-build.sh >/dev/null' EXIT; fi
    UEFI_MODE="$mode" ./scripts/kernel-uefi-build.sh
    if [[ "$mode" != normal ]]; then trap 'UEFI_MODE=normal ./scripts/kernel-uefi-build.sh >/dev/null' EXIT; fi
fi
cpus=1
cpu=qemu64
if [[ "$mode" == runtime-sysenter ]]; then cpu=qemu64,vendor=GenuineIntel,+sep; fi
if [[ "$mode" == acpi-two || "$mode" == budget-smp ]]; then cpus=2; fi
args=()
if [[ -n "${QEMU_DATA:-}" ]]; then args+=(-L "$QEMU_DATA"); fi
case "$mode" in
 bar-state) args+=(-device nvme,serial=AURORA_READ_ONLY) ;;
 pci-devices) args+=(-device nvme,serial=AURORA_READ_ONLY -device qemu-xhci -device e1000e,romfile=) ;;
 pci-bridge|pci-cycle) args+=(-device pcie-root-port,id=aurora_port,chassis=1,slot=2 -device nvme,bus=aurora_port,serial=AURORA_READ_ONLY) ;;
esac
case "$clock_profile" in
 tcg-original-clock) ;;
 tcg-fixed0-noalign-nosleep) args+=(-icount shift=0,align=off,sleep=off) ;;
 *) echo 'Unknown emulator clock profile' >&2; exit 2 ;;
esac
qemu_argv=("$qemu" "${args[@]}" -machine q35 -accel tcg -cpu "$cpu" -smp "$cpus" -m 128M \
    "${UEFI_FIRMWARE_ARGS[@]}" -drive format=raw,file=fat:ro:build/uefi/esp,snapshot=on \
    -nic none -display none -serial stdio -monitor none -no-reboot \
    -device isa-debug-exit,iobase=0xf4,iosize=0x04)
clock_check=(python3 scripts/kernel_emulator_clock.py verify "$mode" "$clock_profile"
    "$qemu" "$UEFI_FIRMWARE_COMBINED" "$UEFI_FIRMWARE_CODE" "$UEFI_FIRMWARE_VARS"
    "${QEMU_DATA:-}" -- "${qemu_argv[@]}")
if [[ "$clock_plan" == true ]]; then
    "${clock_check[@]}"
    exit 0
fi
# Fail closed before QEMU; this records a command, never a successful execution.
"${clock_check[@]}" >"build/uefi/$mode.clock.json"
log="build/uefi/$mode.log"
set +e
# Keep QEMU off the terminal: timeout's background process group would be
# stopped by SIGTTOU when -serial stdio changes a terminal's mode.
timeout 30 "${qemu_argv[@]}" </dev/null >"$log" 2>&1
status=$?
set -e
cat "$log"
if [[ "$mode" == budget* || "$mode" == dispatch* || "$mode" == user-* ]]; then
    python3 - "$mode" <<'PYMETA'
from pathlib import Path
import json,sys
root=Path('build/uefi')
(root/(sys.argv[1]+'.metadata.json')).write_text(json.dumps(dict(images=json.loads((root/'user-images.json').read_text()),kernel=json.loads((root/'service-timer-metadata.json').read_text())),indent=2)+'\n')
PYMETA
    if [[ "$mode" == user-* ]]; then
        python3 tests/kernel-uefi-user-phases-smoke.py "$status" "$log" "$mode" "build/uefi/$mode.metadata.json"
    elif [[ "$mode" == dispatch* ]]; then
        python3 tests/kernel-uefi-dispatch-smoke.py "$status" "$log" "$mode" "build/uefi/$mode.metadata.json"
    else
        python3 tests/kernel-uefi-budget-smoke.py "$status" "$log" "$mode" "build/uefi/$mode.metadata.json"
    fi
elif [[ "$mode" == snapshot* ]]; then
    cp build/uefi/user-images.json "build/uefi/$mode.metadata.json"
    python3 tests/kernel-snapshot-smoke.py "$status" "$log" "$mode" "build/uefi/$mode.metadata.json"
elif [[ "$mode" == ipc* ]]; then
    cp build/uefi/user-images.json "build/uefi/$mode.metadata.json"
    python3 tests/kernel-uefi-ipc-smoke.py "$status" "$log" "$mode" "build/uefi/$mode.metadata.json"
elif [[ "$mode" == runtime-table-* ]]; then
    cp build/uefi/user-images.json "build/uefi/$mode.metadata.json"
    python3 tests/kernel-uefi-tables-smoke.py "$status" "$log" "$mode" "build/uefi/$mode.metadata.json"
elif [[ "$mode" == runtime-pin-* ]]; then
    cp build/uefi/user-images.json "build/uefi/$mode.metadata.json"
    python3 tests/kernel-uefi-pin-smoke.py "$status" "$log" "$mode" "build/uefi/$mode.metadata.json"
elif [[ "$mode" == runtime* ]]; then
    cp build/uefi/user-images.json "build/uefi/$mode.metadata.json"
    python3 tests/kernel-uefi-runtime-smoke.py "$status" "$log" "$mode" "build/uefi/$mode.metadata.json"
elif [[ "$mode" == bar-state ]]; then
    python3 tests/kernel-uefi-bar-state.py "$status" "$log"
elif [[ "$mode" == pci* ]]; then
    python3 tests/kernel-pci-smoke.py "$status" "$log" "$mode"
elif [[ "$mode" == acpi* ]]; then
    python3 tests/kernel-acpi-smoke.py "$status" "$log" "$mode"
else
    python3 tests/kernel-uefi-smoke.py "$status" "$log" "$mode"
fi
echo "PASS: actual OVMF UEFI gate ($mode)"
