#!/usr/bin/env bash
# Shared public/qualification preflight. No build or guest starts here.
program_console_fail() { echo "FAIL: protected console: $*" >&2; return 1; }
program_console_blocked() { echo "BLOCKED: protected console: $*" >&2; return 2; }
program_console_controls() {
    local mode="$1" name
    case "$mode" in
        program-console|program-request-fault|program-service-fault|program-completion-fault|program-request-budget|program-service-budget|program-completion-budget|program-pending|program-owner|program-ordinal|program-unknown|program-transaction) ;;
        *) program_console_fail "unknown profile: $mode"; return 1 ;;
    esac
    for name in "${!KERNEL_TEST_@}" AURORA_TEST_CONTEXT KERNEL_USER_PROBE_MODE KERNEL_CONSOLE UEFI_MODE UEFI_CONSOLE_HANDOFF; do
        [[ -n "$name" ]] || continue
        if [[ -n "${!name:-}" ]]; then
            program_console_fail "unset $name before launch or smoke"; return 1
        fi
    done
}
program_console_preflight() {
    local tool
    qemu="${QEMU:-qemu-system-x86_64}"
    export QEMU="$qemu"
    for tool in "$qemu" "${CXX:-g++}" make as ld objcopy objdump nm readelf python3; do
        command -v "$tool" >/dev/null || { program_console_blocked "missing dependency: $tool"; return 2; }
    done
    if [[ -n "${AURORAC:-}" ]]; then
        command -v "$AURORAC" >/dev/null || { program_console_blocked "missing AURORAC: $AURORAC"; return 2; }
    fi
    if [[ -n "${QEMU_DATA:-}" && ! -d "$QEMU_DATA" ]]; then
        program_console_blocked 'QEMU_DATA directory is unavailable'; return 2
    fi
    # Distinguish invalid selectors from unavailable firmware before using the
    # shared discovery contract. Never reinterpret a build/check exit 2 as BLOCKED.
    if [[ -n "${OVMF:-}" && ( -n "${OVMF_CODE:-}" || -n "${OVMF_VARS:-}" || -n "${OVMF_DIR:-}" ) ]] ||
       [[ -n "${OVMF_DIR:-}" && ( -n "${OVMF_CODE:-}" || -n "${OVMF_VARS:-}" ) ]]; then
        program_console_fail 'choose only one firmware selector'; return 1
    fi
    if [[ -n "${OVMF_CODE:-}" && -z "${OVMF_VARS:-}" || -z "${OVMF_CODE:-}" && -n "${OVMF_VARS:-}" ]]; then
        program_console_fail 'OVMF_CODE and OVMF_VARS must be supplied together'; return 1
    fi
    if [[ -n "${OVMF_CODE:-}" && ( "$OVMF_CODE" == "$OVMF_VARS" || "$OVMF_CODE" -ef "$OVMF_VARS" ) ]]; then
        program_console_fail 'OVMF_CODE and OVMF_VARS must be separate files'; return 1
    fi
    source scripts/uefi-firmware.sh
    uefi_firmware_select || { program_console_blocked 'UEFI firmware unavailable'; return 2; }
    source scripts/uefi-linker.sh
    uefi_linker_select || { program_console_blocked 'UEFI PE linker unavailable'; return 2; }
}
