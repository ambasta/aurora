#!/usr/bin/env bash
# Public launch policy. Builders select kernel_profiles; existing oracles own success.
set -euo pipefail
usage() {
    printf '%s\n' \
        'Usage: scripts/kernel-run.sh [PROFILE] [--console|--smoke]' \
        'Profiles: bios, uefi, bios-console, uefi-console, program-console, program-*.' \
        'Default: bios --smoke. bios-console/uefi-console default to --console; program-* to --smoke.' \
        'bios/uefi --console selects the ordinary interactive console (300 seconds).' \
        'Normal boots are bounded self-tests, not an interactive OS shell (BIOS 15s/UEFI 30s).' \
        'Console --smoke uses the existing PTY oracle; protected fault profiles are smoke-only.' \
        'Overrides: CXX, UEFI_LD, QEMU, QEMU_DATA, OVMF, OVMF_CODE/OVMF_VARS, OVMF_DIR.' \
        'Specialized Event, BAR/IVRS and graphical/capture runners retain their own contracts.'
}
program_console_fail() { echo "FAIL: protected console: $*" >&2; exit 1; }
program_console_blocked() { echo "BLOCKED: protected console: $*" >&2; exit 2; }
if [[ $# == 1 && ( "$1" == --help || "$1" == -h ) ]]; then usage; exit 0; fi
if (( $# > 2 )) || [[ $# == 2 && -z "$2" ]]; then usage >&2; exit 2; fi
profile="${1:-bios}"; action="${2:-}"; protected=false
case "$profile" in
    bios|uefi) platform="$profile"; mode=normal; action="${action:---smoke}" ;;
    bios-console|uefi-console) platform="${profile%-console}"; mode=console; action="${action:---console}" ;;
    program-*) platform=uefi; mode="$profile"; protected=true; action="${action:---smoke}" ;;
    *) usage >&2; exit 2 ;;
esac
case "$action" in --console|--smoke) ;; *) usage >&2; exit 2 ;; esac
if [[ "$mode" == normal && "$action" == --console ]]; then mode=console; fi
cd "$(dirname "$0")/.."
if [[ "$protected" == true ]]; then
    case "$mode" in
        program-console|program-request-fault|program-service-fault|program-completion-fault|program-request-budget|program-service-budget|program-completion-budget|program-pending|program-owner|program-ordinal|program-unknown|program-transaction) ;;
        *) program_console_fail "unknown profile: $mode" ;;
    esac
    if [[ "$action" == --console && "$mode" != program-console ]]; then program_console_fail 'fault profiles are smoke-only'; fi
    controls=("${!KERNEL_TEST_@}" AURORA_TEST_CONTEXT KERNEL_USER_PROBE_MODE KERNEL_CONSOLE UEFI_MODE UEFI_CONSOLE_HANDOFF)
else
    if [[ -n "${AURORA_TEST_CONTEXT:-}" ]]; then
        echo 'This standalone shortcut rejects inherited AURORA_TEST_CONTEXT; start it outside the active supervised test run.' >&2
        exit 2
    fi
    controls=("${!KERNEL_TEST_@}" KERNEL_USER_PROBE_MODE KERNEL_CONSOLE UEFI_MODE)
    if [[ "$mode" == console && ( "$platform" == uefi || "$action" == --smoke ) ]]; then controls+=(UEFI_CONSOLE_HANDOFF); fi
fi
for name in "${controls[@]}"; do
    [[ -n "$name" && -n "${!name:-}" ]] || continue
    if [[ "$protected" == true ]]; then program_console_fail "unset $name before launch or smoke"; fi
    echo "Unset $name before a normal boot or console; use the smoke scripts for fault modes." >&2
    exit 2
done
qemu="${QEMU:-qemu-system-x86_64}"
# Keep each route's original prerequisite order and timeout ownership.
if [[ "$protected" == true ]]; then
    required=("$qemu" "${CXX:-g++}" make as ld objcopy objdump nm readelf python3)
elif [[ "$mode" == console && "$action" == --smoke ]]; then
    required=("$qemu" "${CXX:-g++}" make as ld objcopy nm python3)
    if [[ "$platform" == uefi ]]; then required+=(objdump readelf); fi
else
    required=("$qemu" timeout)
    if [[ "$mode" == console ]]; then required+=(python3); fi
fi
if [[ "$action" == --smoke && "$mode" != normal || "$protected" == true ]]; then export QEMU="$qemu"; fi
for tool in "${required[@]}"; do
    if ! command -v "$tool" >/dev/null; then
        if [[ "$protected" == true ]]; then program_console_blocked "missing dependency: $tool"; fi
        echo "Missing dependency: $tool" >&2; exit 2
    fi
done
if [[ "$action" == --smoke && "$mode" != normal || "$protected" == true ]] && [[ -n "${AURORAC:-}" ]]; then
    if ! command -v "$AURORAC" >/dev/null; then
        if [[ "$protected" == true ]]; then program_console_blocked "missing AURORAC: $AURORAC"; fi
        echo "Missing dependency: $AURORAC" >&2; exit 2
    fi
fi
if [[ "$platform" == uefi ]]; then source scripts/uefi-firmware.sh; fi
# Ordinary interactive UEFI historically selects firmware before checking data.
if [[ "$mode" == console && "$platform" == uefi && "$action" == --console ]]; then uefi_firmware_select; fi
if [[ -n "${QEMU_DATA:-}" && ! -d "$QEMU_DATA" ]]; then
    if [[ "$protected" == true ]]; then program_console_blocked 'QEMU_DATA directory is unavailable'; fi
    echo 'QEMU_DATA must name an existing directory.' >&2; exit 2
fi
if [[ "$protected" == true ]]; then
    # Malformed selectors FAIL; unavailable prerequisites BLOCK. Build/admission
    # status is never reclassified by this preflight.
    if [[ -n "${OVMF:-}" && ( -n "${OVMF_CODE:-}" || -n "${OVMF_VARS:-}" || -n "${OVMF_DIR:-}" ) ]] ||
       [[ -n "${OVMF_DIR:-}" && ( -n "${OVMF_CODE:-}" || -n "${OVMF_VARS:-}" ) ]]; then
        program_console_fail 'choose only one firmware selector'
    fi
    if [[ -n "${OVMF_CODE:-}" && -z "${OVMF_VARS:-}" || -z "${OVMF_CODE:-}" && -n "${OVMF_VARS:-}" ]]; then
        program_console_fail 'OVMF_CODE and OVMF_VARS must be supplied together'
    fi
    if [[ -n "${OVMF_CODE:-}" && ( "$OVMF_CODE" == "$OVMF_VARS" || "$OVMF_CODE" -ef "$OVMF_VARS" ) ]]; then
        program_console_fail 'OVMF_CODE and OVMF_VARS must be separate files'
    fi
    uefi_firmware_select || program_console_blocked 'UEFI firmware unavailable'
    source scripts/uefi-linker.sh
    uefi_linker_select || program_console_blocked 'UEFI PE linker unavailable'
    if [[ "$action" == --console ]]; then
        command -v timeout >/dev/null || program_console_blocked 'missing dependency: timeout'
    fi
elif [[ "$platform" == uefi && ( "$mode" == normal || "$action" == --smoke ) ]]; then
    uefi_firmware_select
    if [[ "$mode" == console ]]; then source scripts/uefi-linker.sh; uefi_linker_select; fi
fi
if [[ "$mode" == normal ]]; then
    if [[ "$platform" == uefi ]]; then
        echo 'Running normal UEFI boot self-tests in QEMU (30-second limit).'
        exec ./scripts/kernel-uefi-smoke.sh normal
    fi
    echo 'Running normal BIOS boot self-tests in QEMU (15-second limit).'
    exec ./scripts/kernel-smoke.sh normal
fi
if [[ "$action" == --smoke ]]; then trap 'exit 130' INT; trap 'exit 143' TERM; fi
build_console() {
    if [[ "$platform" == bios ]]; then KERNEL_CONSOLE=1 ./scripts/kernel-build.sh --print-image-dir
    else UEFI_MODE="$mode" ./scripts/kernel-uefi-build.sh --print-image-dir; fi
}
if image_dir="$(build_console)"; then :; else
    status=$?
    if [[ "$protected" == true ]]; then echo "FAIL: protected-console image build/admission exited $status" >&2; fi
    exit "$status"
fi
if [[ "$action" == --smoke ]]; then
    if [[ "$protected" == true ]]; then
        if python3 -B tests/kernel-program-console-pty.py --mode "$mode" --build-dir "$image_dir"; then :; else
            status=$?; echo "FAIL: protected-console PTY exited $status" >&2; exit "$status"
        fi
    else
        args=(); if [[ "$platform" == uefi ]]; then args+=(--uefi); fi
        python3 -B tests/kernel-console-pty.py "${args[@]}" --build-dir "$image_dir"
    fi
    exit 0
fi
if [[ "$protected" == true ]]; then
    python3 -B scripts/kernel_program_console_admission.py checked --mode "$mode" --build-dir "$image_dir"
fi
if [[ "$platform" == bios ]]; then
    options=(--image "$image_dir/aurora.img" --snapshot)
else
    options=(--image "$image_dir/esp" --firmware "$UEFI_FIRMWARE_COMBINED" --code "$UEFI_FIRMWARE_CODE" --vars "$UEFI_FIRMWARE_VARS")
fi
mapfile -d '' -t qemu_argv < <(python3 -B scripts/qemu_transport.py argv --platform "$platform" \
    --mode "$mode" "${options[@]}" --qemu "$qemu" --data "${QEMU_DATA:-}")
if (( ${#qemu_argv[@]} == 0 )); then
    if [[ "$protected" == true ]]; then program_console_fail 'empty QEMU command'; fi
    echo 'FAIL: empty QEMU command' >&2; exit 2
fi
if [[ "$platform" == uefi ]]; then
    clock=console; python_flags=()
    if [[ "$protected" == true ]]; then clock=program-console-interactive; python_flags=(-B); fi
    python3 "${python_flags[@]}" scripts/kernel_uefi_console_clock.py "$qemu" "$UEFI_FIRMWARE_COMBINED" \
        "$UEFI_FIRMWARE_CODE" "$UEFI_FIRMWARE_VARS" "${QEMU_DATA:-}" --esp "$image_dir/esp" -- "${qemu_argv[@]}" \
        >"$image_dir/$clock.clock.json"
fi
if [[ "$protected" == true ]]; then echo 'Protected Aurora console: upper, then a line of text; exit closes QEMU.'
else echo "${platform^^} serial console in QEMU: type help or exit. Session limit: five minutes."; fi
set +e
# Foreground preserves terminal serial stdio; transport owns the disposable guest.
python3 -B scripts/qemu_transport.py run --foreground --timeout 300 -- "${qemu_argv[@]}"
status=$?
set -e
if [[ "$status" == 33 ]]; then exit 0; fi
if [[ "$protected" == true ]]; then
    echo "FAIL: protected console guest exited $status" >&2
    if [[ "$status" == 0 ]]; then exit 1; fi
elif [[ "$status" == 124 ]]; then echo 'Console session reached its five-minute limit.' >&2; fi
exit "$status"
