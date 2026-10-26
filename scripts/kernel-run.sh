#!/usr/bin/env bash
# Public launch policy. Builders select kernel_profiles; existing oracles own success.
set -euo pipefail
usage() {
    printf '%s\n' \
        'Usage: scripts/kernel-run.sh [PROFILE] [--console|--smoke]' \
        'Profiles: bios, uefi, bios-console, uefi-console, production, program-console, program-*.' \
        'production boots the one production UEFI image; its console is the protected program console.' \
        '--ram-scratchpad-console selects the bounded RAM scratchpad: put/append/get/help/status/exit.' \
        'Default: bios --smoke. bios-console/uefi-console default to --console; program-* to --smoke.' \
        'bios/uefi --console selects the ordinary interactive console (300 seconds).' \
        'Normal boots are bounded self-tests, not an interactive OS shell (BIOS 15s/UEFI 60s).' \
        'Console --smoke uses the existing PTY oracle; protected fault profiles are smoke-only.' \
        'Overrides: CXX, UEFI_LD, QEMU, QEMU_DATA, OVMF, OVMF_CODE/OVMF_VARS, OVMF_DIR.' \
        'Specialized profiles: iommu-event, graphical-console, framebuffer, bar, ivrs, bar-*, ivrs-*.' \
        'Event/graphical: --smoke (default) or --build-only; their existing oracles own restoration.' \
        'Framebuffer defaults to one PNG preview: Not qualified evidence. --smoke/--full-smoke runs all cases.' \
        'BAR/IVRS: bar or ivrs runs the family; one mode takes --output DIR and --run-only IMAGE.'
}
profile_fail() { echo "FAIL: $label: $*" >&2; exit 1; }
profile_blocked() { echo "BLOCKED: $label: $*" >&2; exit 2; }
if [[ $# == 1 && ( "$1" == --help || "$1" == -h ) ]]; then usage; exit 0; fi
profile="${1:-bios}"; label='protected console'
case "$profile" in
    bar|ivrs|bar-state|bar-capture|bar-inherited|bar-read|bar-prepare|bar-write|bar-revoked|bar-alias|ivrs-default|ivrs-read|ivrs-write|ivrs-revoked|ivrs-missing)
        shift
        if [[ ${1-} == --smoke ]]; then shift; fi
        [[ ${1-} != --console ]] || { usage >&2; exit 2; }
        cd "$(dirname "$0")/.."
        exec python3 -B scripts/kernel-uefi-device-run.py "$profile" "$@" ;;
esac
if (( $# > 2 )) || [[ $# == 2 && -z "$2" ]]; then usage >&2; exit 2; fi
action="${2:-}"; protected=false; strict=false; scratchpad=false
case "$profile" in
    bios|uefi) platform="$profile"; mode=normal; action="${action:---smoke}" ;;
    bios-console|uefi-console) platform="${profile%-console}"; mode=console; action="${action:---console}" ;;
    --ram-scratchpad-console|ram-scratchpad-console) platform=uefi; mode=ram-scratchpad-console; profile=ram-scratchpad-console; scratchpad=true; strict=true; label='RAM scratchpad Console'; action="${action:---console}" ;;
    production) platform=uefi; mode=program-console; protected=true; strict=true; action="${action:---smoke}" ;;
    program-*) platform=uefi; mode="$profile"; protected=true; strict=true; action="${action:---smoke}" ;;
    graphical-console|iommu-event) platform=uefi; mode="$profile"; action="${action:---smoke}" ;;
    framebuffer) platform=uefi; mode="$profile"; strict=true; label='framebuffer preview'; action="${action:-preview}" ;;
    *) usage >&2; exit 2 ;;
esac
case "$action:$profile" in
    --console:bios|--console:uefi|--console:bios-console|--console:uefi-console|--console:production|--console:program-*|--console:ram-scratchpad-console|--smoke:*) ;;
    --build-only:iommu-event|--build-only:graphical-console) ;;
    preview:framebuffer) [[ $# == 1 ]] || { usage >&2; exit 2; } ;;
    --full-smoke:framebuffer) action=--smoke ;;
    *) usage >&2; exit 2 ;;
esac
if [[ "$mode" == normal && "$action" == --console ]]; then mode=console; fi
cd "$(dirname "$0")/.."
if [[ "$mode" == iommu-event ]]; then
    options=()
    if [[ "$action" == --build-only ]]; then options=(--build-only); fi
    exec python3 -B scripts/kernel_iommu_event_smoke.py "${options[@]}"
fi
if [[ "$protected" == true ]]; then
    case "$mode" in
        program-file-call|program-file-call-fault|program-file-call-budget|program-console|program-request-fault|program-service-fault|program-completion-fault|program-request-budget|program-service-budget|program-completion-budget|program-pending|program-owner|program-ordinal|program-unknown|program-transaction|program-append-response|program-append-before-fault|program-append-before-budget|program-append-eof-fault|program-append-eof-budget|program-append-copy|program-append-backing|program-append-root|program-append-site) ;;
        *) profile_fail "unknown profile: $mode" ;;
    esac
    if [[ "$action" == --console && "$mode" != program-console && "$mode" != program-file-call ]]; then profile_fail 'fault profiles are smoke-only'; fi
fi
if [[ "$strict" == true || "$mode" == graphical-console ]]; then
    controls=(AURORA_TEST_CONTEXT UEFI_MODE UEFI_CONSOLE_HANDOFF)
else
    if [[ -n "${AURORA_TEST_CONTEXT:-}" ]]; then
        echo 'This standalone shortcut rejects inherited AURORA_TEST_CONTEXT; start it outside the active supervised test run.' >&2
        exit 2
    fi
    controls=(UEFI_MODE)
    if [[ "$mode" == console && ( "$platform" == uefi || "$action" == --smoke ) ]]; then controls+=(UEFI_CONSOLE_HANDOFF); fi
fi
for name in "${controls[@]}"; do
    [[ -n "$name" && -n "${!name:-}" ]] || continue
    if [[ "$strict" == true ]]; then profile_fail "unset $name before launch or smoke"; fi
    echo "Unset $name before a normal boot or console; use the smoke scripts for fault modes." >&2
    exit 2
done
qemu="${QEMU:-qemu-system-x86_64}"
# Keep each route's original prerequisite order and timeout ownership.
if [[ "$strict" == true || "$mode" == graphical-console ]]; then
    required=("$qemu" "${CXX:-g++}" make as ld objcopy objdump nm readelf python3)
elif [[ "$mode" == console && "$action" == --smoke ]]; then
    required=("$qemu" "${CXX:-g++}" make as ld objcopy nm python3)
    if [[ "$platform" == uefi ]]; then required+=(objdump readelf); fi
else
    required=("$qemu" timeout)
    if [[ "$mode" == console ]]; then required+=(python3); fi
fi
if [[ "$mode" == console && "$action" == --smoke || "$protected" == true || "$scratchpad" == true ]]; then export QEMU="$qemu"; fi
for tool in "${required[@]}"; do
    if ! command -v "$tool" >/dev/null; then
        if [[ "$strict" == true ]]; then profile_blocked "missing dependency: $tool"; fi
        if [[ "$mode" == graphical-console ]]; then echo "BLOCKED: missing dependency: $tool" >&2; exit 2; fi
        echo "Missing dependency: $tool" >&2; exit 2
    fi
done
if [[ "$mode" == console && "$action" == --smoke || "$strict" == true ]] && [[ -n "${AURORAC:-}" ]]; then
    if ! command -v "$AURORAC" >/dev/null; then
        if [[ "$strict" == true ]]; then profile_blocked "missing AURORAC: $AURORAC"; fi
        echo "Missing dependency: $AURORAC" >&2; exit 2
    fi
fi
if [[ "$platform" == uefi ]]; then source scripts/uefi-firmware.sh; fi
# Ordinary interactive UEFI historically selects firmware before checking data.
if [[ "$mode" == console && "$platform" == uefi && "$action" == --console ]]; then uefi_firmware_select; fi
if [[ "$mode" != graphical-console && -n "${QEMU_DATA:-}" && ! -d "$QEMU_DATA" ]]; then
    if [[ "$strict" == true ]]; then profile_blocked 'QEMU_DATA directory is unavailable'; fi
    echo 'QEMU_DATA must name an existing directory.' >&2; exit 2
fi
if [[ "$strict" == true ]]; then
    # Malformed selectors FAIL; unavailable prerequisites BLOCK. Build/admission
    # status is never reclassified by this preflight.
    if [[ -n "${OVMF:-}" && ( -n "${OVMF_CODE:-}" || -n "${OVMF_VARS:-}" || -n "${OVMF_DIR:-}" ) ]] ||
       [[ -n "${OVMF_DIR:-}" && ( -n "${OVMF_CODE:-}" || -n "${OVMF_VARS:-}" ) ]]; then
        profile_fail 'choose only one firmware selector'
    fi
    if [[ -n "${OVMF_CODE:-}" && -z "${OVMF_VARS:-}" || -z "${OVMF_CODE:-}" && -n "${OVMF_VARS:-}" ]]; then
        profile_fail 'OVMF_CODE and OVMF_VARS must be supplied together'
    fi
    if [[ -n "${OVMF_CODE:-}" && ( "$OVMF_CODE" == "$OVMF_VARS" || "$OVMF_CODE" -ef "$OVMF_VARS" ) ]]; then
        profile_fail 'OVMF_CODE and OVMF_VARS must be separate files'
    fi
    uefi_firmware_select || profile_blocked 'UEFI firmware unavailable'
    source scripts/uefi-linker.sh
    uefi_linker_select || profile_blocked 'UEFI PE linker unavailable'
    if [[ "$action" == --console ]]; then
        command -v timeout >/dev/null || profile_blocked 'missing dependency: timeout'
    fi
elif [[ "$platform" == uefi && ( "$mode" == normal || "$action" == --smoke || "$mode" == graphical-console ) ]]; then
    uefi_firmware_select
    if [[ "$mode" == console || "$mode" == graphical-console ]]; then source scripts/uefi-linker.sh; uefi_linker_select; fi
fi
if [[ "$mode" == normal ]]; then
    if [[ "$platform" == uefi ]]; then
        echo 'Running normal UEFI boot self-tests in QEMU (60-second limit).'
        exec ./scripts/kernel-uefi-smoke.sh normal
    fi
    echo 'Running normal BIOS boot self-tests in QEMU (15-second limit).'
    exec ./scripts/kernel-smoke.sh normal
fi
build_profile() {
    if [[ "$platform" == bios ]]; then scripts/kernel-image.sh bios console
    else UEFI_MODE="${1:-$mode}" ./scripts/kernel-uefi-build.sh --print-image-dir; fi
}
if [[ "$mode" == graphical-console ]]; then
    [[ ! -L build && ! -L build/uefi && ! -L build/graphical-smoke ]] || { echo 'FAIL: symlink in shared graphical build paths' >&2; exit 2; }
    mkdir -p build/graphical-smoke
    window=$(mktemp -d "$PWD/build/graphical-smoke/run-XXXXXX")
    echo "Graphical smoke files: $window"
    python3 -B scripts/kernel_graphical_smoke.py --start-run "$window"
    finish_run() {
        local status=$?
        trap - EXIT INT TERM
        set +e
        python3 -B scripts/kernel_graphical_smoke.py --finish-run "$window" --status "$status" || {
            echo "FAIL: graphical smoke retention; evidence remains in $window" >&2
            if (( status == 0 )); then status=1; fi
        }
        exit "$status"
    }
    trap finish_run EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    for selected_mode in normal graphical-console graphical-console-capture; do
        if image_dir="$(build_profile "$selected_mode" 2>"$window/build-$selected_mode.log")"; then :; else
            status=$?; echo "FAIL: $selected_mode build/admission exited $status; see $window/build-$selected_mode.log" >&2; exit "$status"
        fi
        python3 -B scripts/kernel_graphical_smoke.py --stage "$selected_mode" --build-dir "$image_dir" --images "$window/images"
    done
    [[ "$action" != --build-only ]] || exit 0
    # Guest captures are compared with the real consumer run on the host.
    build_root="${image_dir%/kernel-images/*}"
    meson compile -C "$build_root" tests/graphical-console-host >"$window/build-renderer.log"
    python3 -B scripts/kernel_graphical_smoke.py --images "$window/images" --evidence "$window/guests" \
        --renderer "$build_root/tests/graphical-console-host" \
        "$qemu" "$UEFI_FIRMWARE_COMBINED" "$UEFI_FIRMWARE_CODE" "$UEFI_FIRMWARE_VARS" "${QEMU_DATA:-}"
    exit 0
elif [[ "$mode" == framebuffer ]]; then
    python3 -B scripts/kernel_framebuffer_preview.py --preflight
    # The four capture cases boot display-fixture; --smoke selects each by its fw_cfg row.
    options=()
    if [[ "$action" == --smoke ]]; then options=(--full-smoke); fi
    if image_dir="$(build_profile framebuffer)"; then :; else
        status=$?; echo "FAIL: framebuffer image build/admission exited $status" >&2; exit "$status"
    fi
    if [[ ${#options[@]} != 0 && ${image_dir##*/} != display-fixture ]]; then profile_fail 'unexpected native framebuffer profile'; fi
    exec python3 -B scripts/kernel_framebuffer_preview.py "${options[@]}" --build-dir "$image_dir" "$qemu" "$UEFI_FIRMWARE_COMBINED" \
        "$UEFI_FIRMWARE_CODE" "$UEFI_FIRMWARE_VARS" "${QEMU_DATA:-}"
fi
if [[ "$action" == --smoke ]]; then trap 'exit 130' INT; trap 'exit 143' TERM; fi
if image_dir="$(build_profile)"; then :; else
    status=$?
    if [[ "$protected" == true ]]; then echo "FAIL: protected-console image build/admission exited $status" >&2; fi
    exit "$status"
fi
if [[ "$action" == --smoke ]]; then
    if [[ "$scratchpad" == true ]]; then
        exec python3 -B tests/kernel-scratchpad-console-pty.py --build-dir "$image_dir"
    fi
    if [[ "$mode" == program-console ]]; then
        # The production image (program-console is its alias) has both consoles:
        # the PTY oracle, then serial commands with the framebuffer.
        build_root="${image_dir%/kernel-images/*}"
        meson compile -C "$build_root" tests/graphical-terminal-host >/dev/null
        exec python3 -B scripts/kernel_production_smoke.py --build-dir "$image_dir" \
            --renderer "$build_root/tests/graphical-terminal-host"
    fi
    if [[ "$protected" == true ]]; then
        if python3 -B tests/kernel-program-console-pty.py --mode "$mode" --build-dir "$image_dir"; then :; else
            status=$?; echo "FAIL: protected-console PTY exited $status" >&2; exit "$status"
        fi
        case "$mode" in
            program-file-call*|program-append-*) ;;
            program-*-fault|program-*-budget)
                python3 -B tests/kernel-program-console-pty.py --mode "$mode" --build-dir "$image_dir" --read-only-recovery
                python3 -B tests/kernel-program-console-pty.py --mode "$mode" --build-dir "$image_dir" --append-recovery
                ;;
            program-ordinal|program-owner|program-transaction|program-unknown)
                python3 -B tests/kernel-program-console-pty.py --mode "$mode" --build-dir "$image_dir" --append-recovery
                ;;
        esac
    else
        args=(); if [[ "$platform" == uefi ]]; then args+=(--uefi); fi
        python3 -B tests/kernel-console-pty.py "${args[@]}" --build-dir "$image_dir"
    fi
    exit 0
fi
if [[ "$platform" == bios ]]; then
    options=(--image "$image_dir/aurora.img" --snapshot)
else
    options=(--image "$image_dir/esp" --firmware "$UEFI_FIRMWARE_COMBINED" --code "$UEFI_FIRMWARE_CODE" --vars "$UEFI_FIRMWARE_VARS")
fi
mapfile -d '' -t qemu_argv < <(python3 -B scripts/qemu_transport.py argv --platform "$platform" \
    --mode "$mode" "${options[@]}" --qemu "$qemu" --data "${QEMU_DATA:-}")
if (( ${#qemu_argv[@]} == 0 )); then
    if [[ "$protected" == true ]]; then profile_fail 'empty QEMU command'; fi
    echo 'FAIL: empty QEMU command' >&2; exit 2
fi
if [[ "$scratchpad" == true ]]; then
    echo 'RAM scratchpad: put [text], get, help, status, exit; 49 printable ASCII bytes, 64 commands.'
    echo 'All data is lost on service reset or exit. External five-minute timeout is not verified teardown.'
elif [[ "$protected" == true ]]; then echo 'Protected Aurora console: upper, then a line of text; exit closes QEMU.'
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
elif [[ "$status" == 124 ]]; then
    if [[ "$scratchpad" == true ]]; then echo 'Scratchpad external timeout: interrupted session, teardown unverified.' >&2
    else echo 'Console session reached its five-minute limit.' >&2; fi
elif [[ "$scratchpad" == true && "$status" == 0 ]]; then
    echo 'FAIL: scratchpad guest exited without its verified exit status.' >&2; exit 1
fi
exit "$status"
