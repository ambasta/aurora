#!/usr/bin/env bash
set -euo pipefail
caller="$PWD"
cd "$(dirname "$0")/.."
run_only= output_dir=
if [[ "${1-}" == --run-only ]]; then
    if (( $# < 4 )) || [[ -z "$2" || "$3" != --output-dir || -z "$4" ]]; then
        echo 'Expected --run-only <native profile directory> --output-dir <fresh directory>' >&2; exit 2
    fi
    run_only="$(cd "$caller" && realpath -e "$2")"; output_dir="$(cd "$caller" && realpath -m "$4")"; shift 4
fi
if (( $# > 1 )); then echo 'Expected one exact BIOS mode' >&2; exit 2; fi
mode="${1:-normal}"
profile="${mode#--}"
python3 -B scripts/kernel_profiles.py --canonical bios "$profile" >/dev/null || { echo 'Unknown kernel smoke mode' >&2; exit 2; }
snapshot=()
if [[ -n "$run_only" ]]; then
    python3 -B - "$mode" "$run_only" "$output_dir" <<'PYPATH'
from pathlib import Path
import sys
sys.path.insert(0, 'scripts')
from kernel_profiles import canonical_profile
image, output = map(Path, sys.argv[2:])
if (not image.is_absolute() or image.resolve(strict=True) != image or not image.is_dir()
        or image.parts[-3:] != ('kernel-images', 'bios', canonical_profile('bios', sys.argv[1].removeprefix('--')))):
    sys.exit('Run-only requires the resolved native directory for the exact BIOS profile')
if not output.is_absolute() or output.resolve() != output or image in output.parents:
    sys.exit('Run-only output must be an absolute resolved fresh directory outside the image directory')
output.mkdir()
PYPATH
    image_dir="$run_only"
    snapshot=(--snapshot)
else
    image_dir="$(scripts/kernel-image.sh bios "$profile")"
fi
output_dir="${output_dir:-$image_dir}"
if [[ "$mode" == normal ]]; then log="$output_dir/kernel-serial.log"
else log="$output_dir/kernel-${mode#--}.log"; fi
metadata="${log%.log}.metadata.json"
# The oracle reads the program set this mode runs.
python3 -B -c 'import json, sys
sets = json.load(open(sys.argv[1]))
json.dump(sets.get(sys.argv[2], sets["default"]), open(sys.argv[3], "w"), indent=2)' \
    "$image_dir/user-metadata.json" "$profile" "$metadata"
qemu="${QEMU:-qemu-system-x86_64}"
command -v "$qemu" >/dev/null || { echo 'BLOCKED: QEMU missing; image is built but emulator boot is unverified.' >&2; exit 2; }
mapfile -d '' -t qemu_argv < <(python3 -B scripts/qemu_transport.py argv --platform bios \
    --mode="$mode" --image "$image_dir/aurora.img" --qemu "$qemu" --data "${QEMU_DATA:-}" "${snapshot[@]}")
(( ${#qemu_argv[@]} )) || { echo 'FAIL: empty QEMU command' >&2; exit 2; }
startup_byte="$(python3 -B scripts/kernel_profiles.py --bios-fixture-byte "${mode#--}")"
startup_args=()
if [[ -n "$startup_byte" ]]; then startup_args+=(--startup-byte "$startup_byte"); fi
set +e
python3 -B scripts/qemu_transport.py run "${startup_args[@]}" --timeout 15 --log "$log" -- "${qemu_argv[@]}"
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
