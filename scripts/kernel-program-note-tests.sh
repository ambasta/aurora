#!/usr/bin/env bash
# Focused source-native replay only: no compiler build, full image or guest.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${AURORAC:?Set AURORAC to the explicitly selected current-source compiler}"
[[ -x "$AURORAC" ]] || { echo 'Selected AURORAC is not executable' >&2; exit 2; }
[[ $# -le 1 ]] || { echo 'Expected at most one private output directory' >&2; exit 2; }
out="${1:-${KERNEL_PROGRAM_NOTE_BUILD_DIR:-build/note-native-focused}}"
mkdir -p "$out"
"$AURORAC" tests/kernel-programs/program-upper-client.au -o "$out/client.s"
"$AURORAC" --module-root kernel/policies tests/kernel-programs/program-stream-service.au -o "$out/service.s" --abi-facts "$out/service.abi.json"
"$AURORAC" --local-symbols --module-root kernel/policies tests/kernel-programs/file-call-service.au \
    -o "$out/file-service.s" --abi-facts "$out/file-service.abi.json"
"$AURORAC" --local-symbols --module-root kernel/policies --module-root library \
    examples/kernel-program-console.au -o "$out/supervisor.s" --abi-facts "$out/supervisor.abi.json"
"$AURORAC" --module-root library --module-root kernel/policies tests/kernel-programs/program-command-stream.au \
    -o "$out/stream.s" --abi-facts "$out/stream.abi.json"
# Test the native initial representation against the real library constructor.
# This is a separate test-only root; all production inputs above are unchanged.
cat > "$out/initial.au" <<'SOURCE'
module program_note_initial;
import console.session_note;
import console.session_files;
import console.protected_files;
import std.binary_buffer;
import std.binary;
auto initial_note() -> console::SessionNote {
    const std::BinaryBuffer64 empty = std::BinaryBuffer64();
    const console::SessionNote note = console::SessionNote(empty);
    return note;
}
auto initial_files() -> console::ProtectedFiles {
    const std::BinaryBuffer64 empty = std::BinaryBuffer64();
    const console::SessionFiles records = console::SessionFiles(empty);
    const console::ProtectedFiles files = console::ProtectedFiles(records);
    return files;
}
SOURCE
"$AURORAC" --module-root library "$out/initial.au" -o "$out/initial.s"
as --64 -L "$out/client.s" -o "$out/client.o"
as --64 -L kernel/uefi/ipc-user-entry.S -o "$out/client-entry.o"
python3 -B scripts/meson_aurora_assembly.py --render-bridge "$out/service.abi.json" kernel/uefi/ipc-user-entry.S "$out/service-entry.s"
as --64 -L --defsym PROGRAM_NOTE_SERVICE=1 "$out/service.s" "$out/service-entry.s" -o "$out/service.o"
for part in client service; do
    extra=()
    case "$part" in
        client) base=0x10000000000; extra+=("$out/client-entry.o") ;;
        service) base=0x10000004000 ;;
    esac
    ld -nostdlib --discard-none -T kernel/program.ld --defsym "USER_BASE=$base" -z max-page-size=0x1000 \
        "${extra[@]}" "$out/$part.o" -o "$out/$part.elf"
    objcopy -O binary "$out/$part.elf" "$out/$part.bin"
done
python3 -B tests/kernel-snapshot-abi.py "$out" --note
python3 -B scripts/meson_aurora_assembly.py --render-bridge "$out/supervisor.abi.json" kernel/uefi/program-note-entry.S "$out/supervisor-entry.s"
as --64 -L "$out/supervisor.s" "$out/supervisor-entry.s" kernel/uefi/kernel-policy-entry.S -o "$out/supervisor-host.o"
as --64 -L "$out/service.s" tests/kernel-program-note-entry.S -o "$out/service-host.o"
as --64 -L --defsym NOTE_TEST_INITIAL=1 "$out/initial.s" tests/kernel-program-note-entry.S -o "$out/initial-host.o"
python3 -B scripts/meson_aurora_assembly.py --render-bridge "$out/stream.abi.json" tests/kernel-program-note-entry.S "$out/stream-entry.s"
as --64 -L --defsym STREAM_TEST_INITIAL=1 "$out/stream.s" "$out/stream-entry.s" -o "$out/stream-host.o"
as --64 -L "$out/client.s" -o "$out/client-host.o"
python3 -B scripts/meson_aurora_assembly.py --render-bridge "$out/file-service.abi.json" tests/kernel-file-call-entry.S "$out/file-service-entry.s"
as --64 -L "$out/file-service.s" "$out/file-service-entry.s" -o "$out/file-service-host.o"
# Production roots live in distinct images. Localize only reflection exports
# for this hosted link; never globalize private entries or rewrite instructions.
for part in client service initial stream; do
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
"${CXX:-g++}" "${flags[@]}" tests/kernel-program-note.cpp \
    "$out/client-host.o" "$out/service-host.o" "$out/supervisor-host.o" "$out/initial-host.o" \
    "$out/stream-host.o" "$out/file-service-host.o" -o "$out/native"
ulimit -c 0
ASAN_OPTIONS='detect_leaks=0:halt_on_error=1:abort_on_error=1:handle_sigill=0' \
    UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1' "$out/native"
# The source projection remains readonly to copied consumers and keeps storage private.
cat > "$out/reject-mutation.au" <<'SOURCE'
module reject_note;
import kernel.note_read;
auto reject(kernel::NoteRead64 value) -> bool { return value.set(0, 1u8); }
SOURCE
cat > "$out/reject-private-bytes.au" <<'SOURCE'
module reject_note;
import kernel.note_read;
auto reject(kernel::NoteRead64 value) -> u8 { return value.bytes[0]; }
SOURCE
cat > "$out/reject-private-length.au" <<'SOURCE'
module reject_note;
import kernel.note_read;
auto reject(kernel::NoteRead64 value) -> i64 { return value.length; }
SOURCE
for rejected in mutation private-bytes private-length; do
    if "$AURORAC" --module-root kernel/policies --check "$out/reject-$rejected.au" > "$out/reject-$rejected.log" 2>&1; then
        echo "FAIL: copied note $rejected control accepted" >&2; exit 1
    fi
    grep -q 'AU3001' "$out/reject-$rejected.log"
done
wc -c "$out/client.bin" "$out/service.bin"
echo 'PASS: focused source-native note replay; complete linked kernel stack, images and guests remain unqualified'
