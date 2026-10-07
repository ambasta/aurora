#!/usr/bin/env bash
# Shared QEMU firmware selection. Source this file, then call uefi_firmware_select.
# Never write installed firmware: split VARS uses QEMU's disposable snapshot.
# --plan permits unchecked explicit file paths. Discovery still needs real files;
# an unresolved plan fails instead of inventing a firmware path or command.
uefi_firmware_select() {
    UEFI_FIRMWARE_ARGS=()
    UEFI_FIRMWARE_COMBINED= UEFI_FIRMWARE_CODE= UEFI_FIRMWARE_VARS=
    local plan=false
    if (( $# )); then
        if [[ $# != 1 || "$1" != --plan ]]; then
            echo 'Expected no firmware argument or --plan.' >&2
            return 2
        fi
        plan=true
    fi
    local combined="${OVMF:-}" code="${OVMF_CODE:-}" vars="${OVMF_VARS:-}"
    local directory="${OVMF_DIR:-}" dir pair candidate code_format vars_format
    local -a directories=() pairs=(
        'OVMF_CODE_4M.fd:OVMF_VARS_4M.fd'
        'OVMF_CODE.4m.fd:OVMF_VARS.4m.fd'
        'OVMF_CODE.fd:OVMF_VARS.fd'
        'OVMF_CODE_4M.qcow2:OVMF_VARS_4M.qcow2'
    )
    if [[ -n "$combined" && ( -n "$code" || -n "$vars" || -n "$directory" ) ]] ||
       [[ -n "$directory" && ( -n "$code" || -n "$vars" ) ]]; then
        echo 'Choose one firmware selector: OVMF, OVMF_CODE plus OVMF_VARS, or OVMF_DIR.' >&2
        return 2
    fi
    if [[ -n "$code" || -n "$vars" ]]; then
        if [[ -z "$code" || -z "$vars" ]]; then
            echo 'Set both OVMF_CODE and OVMF_VARS to a matching x86-64 firmware pair.' >&2
            return 2
        fi
    elif [[ -z "$combined" ]]; then
        if [[ -n "$directory" ]]; then
            [[ -d "$directory" ]] || { echo 'OVMF_DIR must name an existing firmware directory.' >&2; return 2; }
            directories=("$directory")
        else
            directories=(/usr/share/OVMF /usr/share/ovmf /usr/share/edk2/ovmf
                         /usr/share/edk2-ovmf /usr/share/edk2/x64
                         /usr/share/edk2-ovmf/x64 /usr/share/qemu)
            if [[ -n "${QEMU_DATA:-}" ]]; then directories=("$QEMU_DATA" "${directories[@]}"); fi
        fi
        # Only named non-Secure-Boot x86-64 pairs; never mix directories/sizes.
        for dir in "${directories[@]}"; do
            for pair in "${pairs[@]}"; do
                code="$dir/${pair%%:*}"; vars="$dir/${pair#*:}"
                if [[ -f "$code" && -r "$code" && -s "$code" && -f "$vars" && -r "$vars" && -s "$vars" ]]; then break 2; fi
                code=; vars=
            done
        done
        if [[ -z "$code" ]]; then
            for dir in "${directories[@]}"; do
                for candidate in OVMF.fd OVMF.4m.fd; do
                    if [[ -f "$dir/$candidate" && -r "$dir/$candidate" && -s "$dir/$candidate" ]]; then
                        combined="$dir/$candidate"; break 2
                    fi
                done
            done
        fi
        if [[ -z "$combined" && -z "$code" ]]; then
            echo 'OVMF firmware not found. Set OVMF to a combined OVMF.fd ROM, OVMF_CODE and OVMF_VARS to a matching pair, or OVMF_DIR to their directory.' >&2
            if [[ "$plan" == true ]]; then
                echo 'Clock plan unresolved: supply explicit OVMF or OVMF_CODE plus OVMF_VARS paths to plan without installed firmware.' >&2
            fi
            return 2
        fi
    fi
    if [[ -n "$combined" ]]; then
        if [[ "$plan" == false && ( ! -f "$combined" || ! -r "$combined" || ! -s "$combined" ) ]]; then
            echo 'OVMF must name a readable, nonempty combined OVMF.fd ROM.' >&2
            return 2
        fi
        UEFI_FIRMWARE_ARGS=(-bios "$combined")
    else
        for candidate in "$code" "$vars"; do
            if [[ "$plan" == false && ( ! -f "$candidate" || ! -r "$candidate" || ! -s "$candidate" ) ]]; then
                echo 'OVMF_CODE and OVMF_VARS must name readable, nonempty firmware files.' >&2
                return 2
            fi
        done
        if [[ "$code" == "$vars" || "$code" -ef "$vars" ]]; then
            echo 'OVMF_CODE and OVMF_VARS must be separate files from a matching firmware build.' >&2
            return 2
        fi
        code_format=raw; vars_format=raw
        [[ "$code" != *.qcow2 ]] || code_format=qcow2
        [[ "$vars" != *.qcow2 ]] || vars_format=qcow2
        # QEMU's key/value syntax escapes a literal comma by doubling it.
        UEFI_FIRMWARE_ARGS=(
            -drive "if=pflash,unit=0,format=$code_format,readonly=on,file=${code//,/,,}"
            -drive "if=pflash,unit=1,format=$vars_format,snapshot=on,file=${vars//,/,,}"
        )
    fi
    # Resolved semantic inputs, separate from the argv verified by the launcher.
    UEFI_FIRMWARE_COMBINED="$combined"
    UEFI_FIRMWARE_CODE="$code"
    UEFI_FIRMWARE_VARS="$vars"
}
