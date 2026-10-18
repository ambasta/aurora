#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
clock_plan=false
if [[ "${1-}" == --clock-plan ]]; then clock_plan=true; shift; fi
# Compatibility alias: normal restoration now boots the isolated native image.
shared_normal=false
if [[ "${1-}" == --shared-normal ]]; then shared_normal=true; shift; fi
run_only= output_dir=
if [[ "${1-}" == --run-only ]]; then
    if (( $# < 4 )) || [[ -z "$2" || "$3" != --output-dir || -z "$4" || "$clock_plan" == true ]]; then
        echo 'Expected --run-only <absolute native profile directory> --output-dir <fresh directory>, without --clock-plan' >&2; exit 2
    fi
    run_only="$2"; output_dir="$4"; shift 4
fi
if (( $# > 1 )); then echo 'Expected one exact UEFI mode' >&2; exit 2; fi
mode="${1-normal}"
if [[ "$shared_normal" == true && "$mode" != normal ]]; then
    echo '--shared-normal requires the normal profile' >&2; exit 2
fi
case "$mode" in
 iommu-event-denial|iommu-event-success|iommu-event-overflow|iommu-event-command-error|iommu-event-observe)
    echo "UEFI mode '$mode' is build-only; the generic smoke launcher cannot run Event profiles." >&2
    echo "Build with: UEFI_MODE=$mode ./scripts/kernel-uefi-build.sh" >&2
    echo 'Run hosted Event behavior (synthetic transport, no guest DMA): meson test -C <configured-build> iommu-event-source-native --print-errorlogs' >&2
    echo 'Event guest execution requires the reviewed model/firmware, admitted raw ESP and supervised plan described in docs/iommu-dma-conformance.md.' >&2
    echo 'For the separate supported developer guest route, use make smoke-iommu-event with its explicit custom-model inputs.' >&2
    exit 2 ;;
esac
clock_profile="$(python3 scripts/kernel_emulator_clock.py profile "$mode")"
if [[ -n "$run_only" ]]; then
    python3 -B - "$mode" "$run_only" "$output_dir" <<'PYPATH'
from pathlib import Path
import sys
sys.path.insert(0, 'scripts')
from kernel_profiles import canonical_profile
image, output = map(Path, sys.argv[2:])
if (not image.is_absolute() or image.resolve(strict=True) != image or not image.is_dir()
        or image.parts[-3:] != ('kernel-images', 'uefi', canonical_profile('uefi', sys.argv[1]))):
    sys.exit('Run-only requires the resolved native directory for the exact UEFI profile')
if not output.is_absolute() or output.resolve() != output or image in output.parents:
    sys.exit('Run-only output must be an absolute resolved fresh directory outside the image directory')
output.mkdir()
PYPATH
fi
source ./scripts/uefi-firmware.sh
if [[ "$clock_plan" == true ]]; then
    uefi_firmware_select --plan
else
    uefi_firmware_select
fi
image_dir=build/uefi
qemu="${QEMU:-qemu-system-x86_64}"
if [[ "$clock_plan" == false ]]; then
    command -v "$qemu" >/dev/null || { echo 'BLOCKED: QEMU missing' >&2; exit 2; }
    if [[ -n "$run_only" ]]; then image_dir="$run_only"
    else image_dir="$(UEFI_MODE="$mode" ./scripts/kernel-uefi-build.sh --print-image-dir)"; fi
fi
output_dir="${output_dir:-$image_dir}"
mapfile -d '' -t qemu_argv < <(python3 -B scripts/qemu_transport.py argv --platform uefi \
    --mode="$mode" --image "$image_dir/esp" --qemu "$qemu" --data "${QEMU_DATA:-}" \
    --firmware "$UEFI_FIRMWARE_COMBINED" --code "$UEFI_FIRMWARE_CODE" --vars "$UEFI_FIRMWARE_VARS" \
    --clock "$clock_profile")
(( ${#qemu_argv[@]} )) || { echo 'FAIL: empty QEMU command' >&2; exit 2; }
clock_check=(python3 scripts/kernel_emulator_clock.py verify "$mode" "$clock_profile"
    "$qemu" "$UEFI_FIRMWARE_COMBINED" "$UEFI_FIRMWARE_CODE" "$UEFI_FIRMWARE_VARS"
    "${QEMU_DATA:-}" --esp "$image_dir/esp" -- "${qemu_argv[@]}")
if [[ "$clock_plan" == true ]]; then
    "${clock_check[@]}"
    exit 0
fi
# Fail closed before QEMU; this records a command, never a successful execution.
"${clock_check[@]}" >"$output_dir/$mode.clock.json"
log="$output_dir/$mode.log"
set +e
if [[ "$mode" == runtime-console-region || "$mode" == runtime-console-region-fault || "$mode" == runtime-console-region-output || "$mode" == runtime-console-region-cancel-ready ]]; then
    python3 -B tests/kernel-uefi-runtime-smoke.py --console-region-run "$mode" "$log" -- "${qemu_argv[@]}"
else
    python3 -B scripts/qemu_transport.py run --timeout 30 --log "$log" -- "${qemu_argv[@]}"
fi
status=$?
set -e
cat "$log"
if [[ "$mode" == budget* || "$mode" == dispatch* || "$mode" == user-* ]]; then
    python3 - "$mode" "$image_dir" "$output_dir" <<'PYMETA'
from pathlib import Path
import json,sys
root=Path(sys.argv[2])
timer=root/'service-timer-metadata.json'
if sys.argv[1]=='budget-noapic':
    if timer.exists(): raise ValueError('Early budget rejection has timer metadata')
    kernel=None
else:
    kernel=json.loads(timer.read_text())
(Path(sys.argv[3])/(sys.argv[1]+'.metadata.json')).write_text(json.dumps(dict(images=json.loads((root/'user-images.json').read_text()),kernel=kernel),indent=2)+'\n')
PYMETA
    if [[ "$mode" == user-* ]]; then
        python3 tests/kernel-uefi-user-phases-smoke.py "$status" "$log" "$mode" "$output_dir/$mode.metadata.json"
        if [[ "$mode" == user-resume ]]; then
            python3 tests/kernel-uefi-user-phases-smoke.py --resume-code "$log" "$image_dir/user-clean.elf"
        fi
    elif [[ "$mode" == dispatch* ]]; then
        python3 tests/kernel-uefi-dispatch-smoke.py "$status" "$log" "$mode" "$output_dir/$mode.metadata.json"
    else
        python3 tests/kernel-uefi-budget-smoke.py "$status" "$log" "$mode" "$output_dir/$mode.metadata.json"
    fi
elif [[ "$mode" == snapshot* ]]; then
    cp "$image_dir/user-images.json" "$output_dir/$mode.metadata.json"
    python3 tests/kernel-snapshot-smoke.py "$status" "$log" "$mode" "$output_dir/$mode.metadata.json"
elif [[ "$mode" == ipc* ]]; then
    cp "$image_dir/user-images.json" "$output_dir/$mode.metadata.json"
    python3 tests/kernel-uefi-ipc-smoke.py "$status" "$log" "$mode" "$output_dir/$mode.metadata.json"
elif [[ "$mode" == runtime-table-* ]]; then
    cp "$image_dir/user-images.json" "$output_dir/$mode.metadata.json"
    python3 tests/kernel-uefi-tables-smoke.py "$status" "$log" "$mode" "$output_dir/$mode.metadata.json"
elif [[ "$mode" == runtime-pin-* ]]; then
    cp "$image_dir/user-images.json" "$output_dir/$mode.metadata.json"
    python3 tests/kernel-uefi-pin-smoke.py "$status" "$log" "$mode" "$output_dir/$mode.metadata.json"
elif [[ "$mode" == runtime* ]]; then
    cp "$image_dir/user-images.json" "$output_dir/$mode.metadata.json"
    python3 tests/kernel-uefi-runtime-smoke.py "$status" "$log" "$mode" "$output_dir/$mode.metadata.json"
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
