#!/usr/bin/env bash
# Focused native replay only: no full kernel image, guest or compiler build.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${AURORAC:?Set AURORAC to the explicitly selected current-source compiler}"
[[ -x "$AURORAC" ]] || { echo 'Selected AURORAC is not executable' >&2; exit 2; }
[[ $# -le 1 ]] || { echo 'Expected at most one private output directory' >&2; exit 2; }
out="${1:-${KERNEL_SNAPSHOT_BUILD_DIR:-build/snapshot-focused}}"
mkdir -p "$out"
for part in client service; do
    "$AURORAC" --module-root kernel/policies "tests/kernel-programs/snapshot-$part.au" -o "$out/$part.s"
done
"$AURORAC" --module-root kernel/policies --module-root library examples/kernel-snapshot.au -o "$out/supervisor.s"
as --64 -L "$out/client.s" -o "$out/client.o"
as --64 -L kernel/uefi/ipc-user-entry.S -o "$out/client-entry.o"
as --64 -L --defsym SNAPSHOT_SERVICE=1 "$out/service.s" kernel/uefi/ipc-user-entry.S -o "$out/service.o"
as --64 -L "$out/supervisor.s" kernel/uefi/snapshot-entry.S -o "$out/supervisor.o"
for part in client service; do
    extra=()
    case "$part" in
        client) base=0x10000000000; extra+=("$out/client-entry.o") ;;
        service) base=0x10000001000 ;;
    esac
    ld -nostdlib --discard-none -T kernel/program.ld --defsym "USER_BASE=$base" -z max-page-size=0x1000 \
        "${extra[@]}" "$out/$part.o" -o "$out/$part.elf"
    objcopy -O binary "$out/$part.elf" "$out/$part.bin"
done
python3 -B tests/kernel-snapshot-abi.py "$out"
as --64 -L "$out/service.s" tests/kernel-snapshot-entry.S -o "$out/service-host.o"
as --64 -L "$out/client.s" -o "$out/client-host.o"
"$AURORAC" --module-root kernel/policies --module-root library tests/kernel-programs/call-snapshot-service.au -o "$out/checksum.s"
as --64 -L --defsym CHECKSUM_SERVICE=1 "$out/checksum.s" tests/kernel-snapshot-entry.S -o "$out/checksum-host.o"
# Production has separate address-space images. Only this hosted test links the
# roots together; localize their exact reflection exports to avoid collisions.
# Do not globalize source entries or alter any generated instruction.
for part in client service checksum; do
    nm -g --defined-only "$out/$part-host.o" \
        | awk '$3 ~ /^(aurora_reflect_|__au_reflect_)/ {print $3}' > "$out/$part-reflections.txt"
    objcopy --localize-symbols="$out/$part-reflections.txt" "$out/$part-host.o"
done
flags=(-std=c++23 -O1 -g -Wall -Wextra -Wpedantic -Werror -DNDEBUG -fno-exceptions -fno-rtti -no-pie)
case "${SANITIZE:-0}" in
    0) ;;
    1) flags+=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer) ;;
    *) echo 'SANITIZE must be 0 or 1' >&2; exit 2 ;;
esac
"${CXX:-g++}" "${flags[@]}" -DAURORA_UEFI_SNAPSHOT -DAURORA_UEFI_RUNTIME -DAURORA_UEFI_IPC \
    -DAURORA_UEFI_ACPI -DAURORA_UEFI_PCI tests/kernel-snapshot.cpp kernel/uefi/snapshot.cpp kernel/owned-bytes.cpp \
    "$out/client-host.o" "$out/service-host.o" "$out/checksum-host.o" "$out/supervisor.o" -o "$out/native"
ulimit -c 0
ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1:handle_sigill=0' \
    UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1' "$out/native"
cat > "$out/reject-mutation.au" <<'EOF'
module reject_snapshot;
import kernel.snapshot;
auto reject(kernel::Snapshot64 value) -> bool { return value.set(0, 1u8); }
EOF
cat > "$out/reject-private.au" <<'EOF'
module reject_snapshot;
import kernel.snapshot;
auto reject(kernel::Snapshot64 value) -> u8 { return value.bytes[0]; }
EOF
for rejected in mutation private; do
    if "$AURORAC" --module-root kernel/policies --check "$out/reject-$rejected.au" > "$out/reject-$rejected.log" 2>&1; then
        echo "FAIL: copied snapshot $rejected control accepted" >&2; exit 1
    fi
    grep -q 'AU3001' "$out/reject-$rejected.log"
done
wc -c "$out/client.bin" "$out/service.bin"
echo 'PASS: focused native replay; complete linked stack admission and guests remain unqualified'
