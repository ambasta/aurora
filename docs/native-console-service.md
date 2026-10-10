# Persistent Aurora console service

The simple-UEFI console profile migrates the complete 64-byte editor,
command parsing and human-facing presentation into one persistent Aurora entry
frame. `examples/kernel-console-service.au` owns `Line64` for the entire session:
private bytes, length, sticky rejection and CRLF state. It implements exact
`help`, `status` and `exit`, one session-local RAM note, echo, erase,
empty/unknown/rejected lines and prompts.
The [sealed language service contract](../compiler/SERVICES.md) supplies only
copied input observations and checked single-byte output.

## Session-local RAM note

Simple UEFI and the graphical console share `console.session_note` for
`write note <text>` and `cat note`. The exact prefix
`write note ` leaves at most 53 printable ASCII content bytes in a 64-byte line;
its trailing space alone writes an empty note. `cat note` reports missing or
prints the content and a newline. Accepted writes replace and clear the old
suffix; malformed, overlong or UART-damaged input preserves the previous note.

One invocation-local `BinaryBuffer64` owns the RAM-only note across idle waits
and other commands. Exit or output failure ends its lifetime; a new invocation
starts missing. This adds no disk access, persistence, heap or runtime authority,
and claims no secure RAM erasure. The graphical view renders the same content
through its ordinary response row and dirty-cell painter. Fresh
final-source qualification is required; historical results below do not cover it.

## Trusted boundary

`kernel/console-session.hpp` authenticates the exact active host grant, closed
kind, nonzero monotonic generation and non-reentrant operation before transport
work. Pointer equality is checked before dereference. Opening rejects an existing
active invocation and generation exhaustion. Polling revalidates the operation
across each trusted wait. Closing checks the closed completion code and exact
active invocation once. Output timeout terminates rather than retrying a partial
response. Traps retain the existing fail-stop behavior; there is no invented
unwinder or restarted editor.

The UEFI adapter still owns platform admission, UART registers, APIC one-shot
arming, CR3, interrupt masking, exact wake PC/frame/stack checks, EOI and
quiescence. IRQ code never calls Aurora or touches its editor. The bridge carries
only the private grant/generation record; source never receives a pointer.

The UART transport no longer includes or requires a C++ `Line`. Its copied
sample applies damage before byte processing. All LSR reads, including transmit
polls, retain receive errors. An error exposed after a popped CR/LF damages both
that line and the next sample. FIFO reset behavior is retained. Explicit legacy
`poll(editor)`/`put` wrappers remain for BIOS and protected-program profiles.

The migrated simple-UEFI linked graph must contain no C++ `Line`, `Presentation`,
old byte/command policy wrappers or C++ human-command response strings. Bootstrap
platform diagnostics remain trusted. BIOS and protected-program console editor
migration are outside this checkpoint.

## Verification and acceptance gates

Five exact original-clock images completed independently reviewed prebuilt PTY
qualification: normal interaction, stale captured generation, operation reentry,
17-byte output timeout and noncanonical copied-report trapping. Every attempt
was followed by an actual normal-profile restoration boot. Normal interaction
observed 78 authenticated wakes, response samples below 21 ms and 0.01 CPU seconds
over a 0.6001-second idle sample; these are measurements on the qualified emulator,
not timing guarantees or evidence of physical hardware support.

Whole linked stack accounting measured 6,912 bytes for the maximum normal path,
1,136 for the Aurora session root and at most 1,534 for the retained wait frame
plus IRQ and synchronous-fault reserve. The unchanged whole-stack cap is 15,360
bytes within the 16 KiB stack; the separate IRQ-plus-fault reserve remains 4,096
bytes. Admission checks both, including their boundary mutation tests.

The final PR96 library/test/documentation join and stricter explicit IRQ-reserve
check retain the original guest receipts only through fresh byte-identical
execution-output and call-graph applicability checks; they are not relabeled as
new guest executions. Exact hashes, commands and final developer/slow outcomes
belong to the accompanying reviewed qualification evidence and pull request.

Required before qualification or merge:

1. Join the independently accepted protected-console and ASCII-byte-literal
   checkpoints. Preserve their changes and receipts.
2. Fresh source-positive/negative editor tests, hostile independently authored IR,
   handwritten packed-ABI/callee-save tests, canonical host-report traps,
   host-grant lifetime/reentry tests and UART/error-latch models.
3. Exact generated and mixed-language linked-stack accounting, including the
   interrupt reserve, under existing budgets; PIC/ELF/PE admission and evidence
   that legacy editor/presentation policy references are absent.
4. Actual simple-UEFI PTY editing, full/overlong/malformed input, CRLF, commands,
   idle wake and output evidence. Injected authority/transport faults must fail
   as intended, followed by a fresh normal-image restoration boot.
5. The [complete final-source native gate](../AGENTS.md#workflow), then independent
   source and evidence review. Any later source change invalidates dependent gates.

No hardware qualification, full-native release, general OS service framework or
self-hosted compiler claim follows from this bounded migration. The C++23
bootstrap compiler remains permitted tooling; the migrated behavior is native
Aurora code in the actual guest.

## First-change qualification and routine use

`kernel-uefi-build.sh` automatically runs exact ELF/PIC/PE, linked C++ retirement,
private bridge, complete mixed-stack, IRQ closure and normal/IRQ-plus-fault budget
checks for this profile. Ordinary public build/console commands remain usable
without an assistant-issued token.

For this implementation's first changed-image qualification, an independent
reviewer must inspect the exact admission JSON and supply its digest separately.
`tests/kernel-console-service-qualification.py --mode MODE` verifies that external
`CONSOLE_SERVICE_REVIEW_SHA256` pin before starting any guest, never rebuilds the
reviewed console image, rechecks its bytes after the PTY run, and retains a separate
qualification receipt only with the reviewed provenance. Each admitted attempt
then builds and actually boots the normal profile for restoration, even when its
PTY test fails. A routine unreviewed run cannot produce this qualification receipt.

The four explicit fault images exercise stale captured generation after
close/reopen, operation reentry from the trusted wait hook, checked transmit
failure after exactly 17 output bytes, and a noncanonical copied damage boolean.
The timeout is a deliberate transport-result injection, not a claim of real
UART hardware fault induction. Hostile source/IR and fake-port UART tests remain
separate mandatory controls.
