#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mode="${1:-normal}"
source ./scripts/uefi-firmware.sh
uefi_firmware_select
qemu="${QEMU:-qemu-system-x86_64}"
command -v "$qemu" >/dev/null || { echo 'BLOCKED: QEMU missing' >&2; exit 2; }
UEFI_MODE="$mode" ./scripts/kernel-uefi-build.sh
if [[ "$mode" != normal ]]; then trap './scripts/kernel-uefi-build.sh >/dev/null' EXIT; fi
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
log="build/uefi/$mode.log"
set +e
timeout 30 "$qemu" "${args[@]}" -machine q35 -accel tcg -cpu "$cpu" -smp "$cpus" -m 128M \
    "${UEFI_FIRMWARE_ARGS[@]}" -drive format=raw,file=fat:ro:build/uefi/esp,snapshot=on \
    -nic none -display none -serial stdio -monitor none -no-reboot \
    -device isa-debug-exit,iobase=0xf4,iosize=0x04 >"$log" 2>&1
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
