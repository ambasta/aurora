#!/usr/bin/env bash
# Disposable opt-in BIOS console. The ordinary run commands remain self-tests.
set -euo pipefail
if [[ $# != 0 ]]; then
    echo 'Usage: scripts/kernel-console.sh (BIOS serial console; five-minute session limit)' >&2
    exit 2
fi
cd "$(dirname "$0")/.."
if [[ -n "${AURORA_TEST_CONTEXT:-}" ]]; then
    echo 'Run this interactive session outside the supervised native tests.' >&2
    exit 2
fi
for name in "${!KERNEL_TEST_@}" KERNEL_USER_PROBE_MODE KERNEL_CONSOLE UEFI_MODE; do
    [[ -n "$name" ]] || continue
    if [[ -n "${!name:-}" ]]; then
        echo "Unset $name before starting the interactive console." >&2
        exit 2
    fi
done
qemu="${QEMU:-qemu-system-x86_64}"
for tool in "$qemu" timeout python3; do
    command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; exit 2; }
done
if [[ -n "${QEMU_DATA:-}" && ! -d "$QEMU_DATA" ]]; then
    echo 'QEMU_DATA must name an existing directory.' >&2; exit 2
fi
image_dir="$(KERNEL_CONSOLE=1 ./scripts/kernel-build.sh --print-image-dir)"
mapfile -d '' -t qemu_argv < <(python3 -B scripts/qemu_transport.py argv --platform bios \
    --mode console --image "$image_dir/aurora.img" --qemu "$qemu" --data "${QEMU_DATA:-}" --snapshot)
(( ${#qemu_argv[@]} )) || { echo 'FAIL: empty QEMU command' >&2; exit 2; }
echo 'BIOS serial console in QEMU: type help or exit. Session limit: five minutes.'
set +e
# Keep QEMU in the terminal's foreground process group so serial stdio cannot
# stop itself with SIGTTOU. No monitor, network interface or host disk is exposed.
python3 -B scripts/qemu_transport.py run --foreground --timeout 300 -- "${qemu_argv[@]}"
status=$?
set -e
if [[ "$status" == 33 ]]; then exit 0; fi
if [[ "$status" == 124 ]]; then echo 'Console session reached its five-minute limit.' >&2; fi
exit "$status"
