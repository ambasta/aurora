#!/usr/bin/env bash
set -euo pipefail
out="${PIN_REVIEW_GATE_OUT:?}"
mkdir -p "$out"
cp build/uefi/esp/EFI/BOOT/BOOTX64.EFI "$out/BOOTX64.EFI"
cp build/uefi/payload.elf "$out/payload.elf"
cp build/uefi/payload.bin "$out/payload.bin"
cp build/uefi/user-images.json "$out/user-images.json"
cp build/uefi/runtime.su "$out/runtime.su"
sha256sum "$AURORAC" "$out/BOOTX64.EFI" "$out/payload.elf" "$out/payload.bin" "$out/user-images.json" > "$out/image-sha256.txt"
printf '%s\n' "$@" > "$out/qemu-arguments.txt"
set +e
"${PIN_REVIEW_REAL_QEMU:?}" "$@"
status=$?
printf '%s\n' "$status" > "$out/qemu-status.txt"
exit "$status"
