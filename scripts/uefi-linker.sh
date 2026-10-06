#!/usr/bin/env bash
# PE/COFF is not enabled in every distribution's native GNU linker.
uefi_linker_select() {
    UEFI_LINKER=
    local candidate emulation emulations
    local -a candidates=()
    if [[ -n "${UEFI_LD:-}" ]]; then candidates=("$UEFI_LD")
    else candidates=(ld x86_64-w64-mingw32-ld); fi
    for candidate in "${candidates[@]}"; do
        command -v "$candidate" >/dev/null || continue
        if ! emulations=$("$candidate" -V 2>/dev/null); then continue; fi
        while IFS= read -r emulation; do
            if [[ "$emulation" =~ ^[[:space:]]*i386pep[[:space:]]*$ ]]; then
                UEFI_LINKER="$candidate"
                return 0
            fi
        done <<< "$emulations"
    done
    echo 'Missing UEFI PE linker: set UEFI_LD to GNU ld with i386pep support (for example x86_64-w64-mingw32-ld; Gentoo also provides binutils[multitarget]).' >&2
    return 2
}
