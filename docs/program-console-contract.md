# Protected command console implementation contract

Status: scoped command, recovery and hostile-profile guest evidence independently accepted.
Publication additionally requires a matching final integrated dev/slow run.
Started at b3551be8 and composed the accepted compiler/repair source through main
1024f40e plus the qualified terminal-event and structural-formatter source joins.

## Observable gate

An opt-in UEFI `program-console` image accepts `upper`, then `text> Hello, Aurora 42!`,
and prints `HELLO, AURORA 42!` once before returning to `aurora>`. The uppercase
transformation executes in a separately compiled, one-page RX Aurora CPL3 client.
A separate CPL3 stream service validates and returns its requested output byte.
This is an embedded bounded application demonstration, not a general process or
syscall ABI, filesystem, terminal emulator, or hardware qualification.

## Authority and data

Exactly two real domains use `ipc::Mailbox`, not the three-domain dispatcher.
A checked input snapshot is copied before the 64-byte ASCII editor scrubs itself.
For each byte, a kernel-owned ordinal selects the copied input. The client request
returns a transformed byte; a mailbox request contains that byte and its ordinal.
The service validates the scalar values and returns the approved byte. A consumed
completion is acknowledged by the compiled client before one byte is staged.
No submitted pointer, caller number, output address, or UART authority exists.
Fresh command grants and transactions come from the existing monotonic mailbox
sequence. Complete output is released only after successful acknowledgements,
mailbox scrubbing/revocation, domain retirement and root/continuation restoration.
Cancellation discards every staged output byte. Empty input completes with empty
output; rejected input never starts a protected run.

## Timer ownership

Map/admit the xAPIC aperture once. A private mutually exclusive console/runtime
phase owns vector 64. Console polling retains the exact original three-byte
STI/HLT/CLI continuation and full ConsoleWakeContext frame checks. Runtime entry
retains domain/root/frame/compiled-site and immutable run-authority authentication.
Both client phases and the service receive bounded budgets. The new two-role
run authority cannot admit the dispatcher's second client or a third domain.

Transfer requires actual kernel CR3, IF clear, stopped/masked timer, empty ISR/IRR,
no active program or saved continuation, and no old owner. Pending runtime IRQs
are drained under the old authenticated runtime owner before retirement or transfer.
Timer epochs and domain/mailbox generations are never reset between commands.

Only authenticated emitted language faults or authenticated budget exhaustion may
recover. Cleanup cancels applicable mailbox state, consumes/scrubs cancellation,
revokes grants, retires/scrubs both domains, clears copied data and returns to the
prompt. Unknown sites, malformed frames, privilege/root/owner mismatches fail stop.

## Admission and evidence

First-change qualification requires independent review of exact generated image
metadata, PIC/relocations, PE permissions, bounded stack call paths including
interrupt reserve, and IRQ mappings in both roots before its qualification guest.
Routine developer launch and smoke instead rebuild locally and pass those
automated admission checks; they do not establish independent qualification.
Existing profiles must remain unchanged.
Run focused model/host and sanitizer tests before actual original-clock OVMF PTY
acceptance. Cover empty/64/65 bytes, editing, CRLF/UART rejection, repeated commands,
known request/service/completion faults and budget exhaustion, pending IRQ ownership
transfer, a healthy next command, and restoration of the normal boot image.
Preserve raw failures and receipts. A focused gate is not full native or hardware
qualification. Terminal-event policy work must be composed without losing its
Aurora classifier wrapper/import or weakening its trusted envelope checks.

## Current qualification

The original-clock QEMU 10.0.13/OVMF normal profile completed six commands and
363 authenticated CPL3 runs: `HELLO, AURORA 42!`, a repeated command, empty input,
edited input, 64-byte output and a healthy command after rejected input. Grants
were fresh and epochs monotonic; output followed zero-resource retirement. QEMU
exited 33 after the quiescent console exit. The normal boot image was rebuilt.

The original final oracle rejected startup CRCRLF produced by QEMU's PTY setup,
although its kernel-root value was correct. The raw failed metrics and transcript
are preserved. A narrowly corrected matcher accepts one or two CR bytes only at
that startup record; an explicit hash-bound offline replay passed. Independent
review accepted this original guest plus corrected-oracle replay as a composite.
It is not represented as a second guest run or an all-profile pass.

Focused hosted tests passed, including 40,000 stream-model steps, 471 two-role
run-authority checks, real Mailbox/Aurora-policy composition, copied editor/UART
boundaries and existing IPC/run/disposal regressions. Fatal ASan/UBSan passed for
the same trusted C++ scope. Generated Aurora assembly is unsanitized; leak checks
are disabled. The revised UART suite has 574 observations for each FIFO profile.
The current guest-oracle model has 148 positive/refusal controls.

Independent exact-image admission verified two one-page RX images, actual
compiled uppercase instructions, PE/PIC, owner/phase/IRQ mappings and linked
stack bounds. Accepted normal-image peaks were 14,847 bytes including boot fault,
2,839 for polling plus IRQ, 2,991 for pending drain plus IRQ, 1,559 for the separate
IRQ path, and 128 for each user entry/compiled path. The cap is 15,360 bytes within
the unchanged 16 KiB stack. The separately admitted pending variant uses 1,575
bytes for its IRQ path, 2,855 for poll plus IRQ and 3,007 for drain plus IRQ.
These numbers qualify only their exact admitted images.

Eleven additional original-clock guests passed independent raw-evidence replay.
Each request/service/completion fault or budget mode completed one byte before
failing at ordinal 1, discarded all staged output, retired both domains and ran
six healthy commands afterward. Their traces contain 367/368/369 runs and exit
33. The pending-IRQ mode completed six commands/363 runs with authenticated
old-owner drains. Owner, ordinal, transaction and unknown-site probes each failed
stop at the exact admitted site/reason, exit 35, without output or prompt recovery.
Every profile restored the normal image. A separate actual normal UEFI boot then
passed exit 33 on exact bytes independently rebound to prior terminal admission.

Final repository acceptance requires both dev and slow on this final integrated
source, including its documentation; the matching external receipts record that
result. No full-native, broad kernel or physical-hardware qualification is
claimed; full make test remains required before release.

Bulk evidence, original failures and exact source/compiler/image/replay hashes
are retained in the external checkpoint evidence package. The first build's
unused-stack-accessor failure was corrected by checking the actual kernel stack;
no failed command is reported as a passing build.

## Routine local admission and separate first-change qualification

`scripts/kernel-uefi-build.sh` records program-profile source inputs, Aurora/host
compiler hashes and selected flags before compilation, verifies they did not
change during compilation, and binds the resulting objects, stack records, user
images and EFI image in `build/uefi/program-build.json`. Profile builds do not
start a guest. Every program-profile build automatically emits admission evidence
and rejects missing or stale provenance, unsupported decoder instructions, image
violations and exhausted stack budgets before any public launch can proceed.

`python3 -B scripts/kernel_program_console_admission.py emit --mode program-console`
prepares `build/uefi/program-console-admission.json`. It rechecks PE/PIC and user
image metadata, the exact poll/drain instructions, object-to-link associations,
compiler frames, actual linked call-site stack depths, separately owned CPL3
stacks and the full IRQ frame/alignment/dispatch reserve. Its RuntimeTables
recursion bound relies on the pinned C++ four-level contract; exact emitted
walker bodies are retained for independent review. The PageTables walker also
retains its machine-level decreasing-level proof. Unknown indirect branches are
rejected; the terminal classifier's one six-entry PIC switch has a checked bound,
read-only table, in-function instruction targets and all target paths decoded.

Ordinary developer commands need no historical or assistant-issued digest:

```sh
make program-console-uefi
make smoke-program-console-uefi
./scripts/kernel-program-console-smoke.sh program-pending
```

They preflight tools, firmware and inherited controls, build the selected local
profile and verify the complete current-source/output receipt before execution.
The stack decoder remains fail closed, including its narrowly reviewed copied-IF
instruction normalization. There is no generic unsupported-instruction exemption.
Smoke uses the same original-clock PTY and hostile transcript oracles as before,
rechecks image/source identity afterward and rebuilds the normal image on success,
failure or handled interruption. That restoration is a build, not a normal boot.
Prerequisite rejection occurs before image mutation or restoration. Unavailable
tools/firmware are `BLOCKED` (exit 2); invalid controls, build/admission failures,
wrong guest exits or failed oracles are `FAIL`, including a build/check exit 2.
Neither outcome is a skipped or successful guest test.

Evidence generation is not independent approval. First-change qualification is
explicit, against an already built image that the reviewer inspected:

```sh
UEFI_MODE=program-console ./scripts/kernel-uefi-build.sh
# An independent reviewer inspects the resulting admission evidence and supplies its digest.
PROGRAM_CONSOLE_REVIEW_SHA256=<independently-reviewed-digest> make qualify-program-console-uefi
# For another separately built/reviewed profile:
PROGRAM_CONSOLE_REVIEW_SHA256=<independently-reviewed-digest> \
    ./scripts/kernel-program-console-smoke.sh --qualification program-pending
```

Only this explicit route uses `reviewed --mode PROFILE`; it never computes or
fills its own approval and never rebuilds the reviewed image before the guest.
Missing approval blocks qualification; a malformed/mismatched pin fails it.
The review checks the exact receipt, selected profile, provenance and complete
source/object/image inventory, again after execution. A supplied pin does not
silently turn an ordinary developer run into qualification.

Each PTY attempt retains a fresh directory under `build/program-console-evidence`
with the original admission bytes, clock command, raw transcript, stderr and
metrics. Developer metrics have `purpose: developer` and
`qualification_eligible: false`; only a passing explicitly pinned guest may have
`qualification_eligible: true`. A successful guest metric does not override a
failed wrapper/restoration result or replace independent review/final merge gates.
The `diagnose` action produces stack diagnostics only, without an admission
receipt, and can inspect an old image while implementation continues.

Compiler-free regression controls are in `tests/kernel-program-admission.py`
and `tests/kernel-program-console-entrypoints.py`. They reject changed source,
image, compiler, profile, incomplete receipt coverage and fabricated approval;
record public build/check/PTY routes, no-rebuild qualification and restoration;
and distinguish unavailable prerequisites from actual failures. These synthetic
controls do not establish a new guest, compiler/toolchain or hardware qualification.

## Pre-guest review repairs

Independent source review found that runtime diagnostics used raw serial LSR
reads, which could clear receive-error bits before the console saw them. The new
program profile now routes every runtime/timer trace and input operation through
one sticky-latch UART specialization. Other profiles keep their original route.
A source-routing guard covers the actual runtime/include chain; a hosted UART
regression injects errors during runtime-style trace TX before copied submission.
The final joined hosted and fatal sanitizer reruns passed these controls.

The guest oracle also now authenticates supervisor pending-drain records against
the owned arena/root, exact reviewed drain PC interval, frame range, active epoch,
terminal state and immediately paired drain evidence. The guest-free positive
and refusal controls also reject malformed supervisor drain records. Four additional opt-in hostile-envelope profiles
(owner, ordinal, transaction and unknown site) require fail stop with no output
or prompt recovery. Exact compiled images and actual guest traces passed these gates.

The formatter/diagnostic repair and direct copied-constructor return source join
is hash-verified against its frozen upstream manifest. A later pending-profile
build was rejected by the stack decoder on one new memory `andq` instruction.
Independent review approved normalization of exactly
`andq $0xfffffffffffffdff,0x50(%rsp)` to the existing stack-neutral `and` model.
Other masks, displacements and stack-pointer operands still reject. The original
failure is preserved; corrected diagnostics and refusal controls passed. This
verifier change invalidated the first unused variant receipts. All eleven were
rebuilt, independently readmitted and only then executed; old receipts remain
preserved as superseded evidence.

Fault/budget probes now execute only at ordinal 1, after one complete request /
service / completion triplet has staged a byte. The oracle requires that prefix
and then the failing-phase prefix, no released output, retirement and a healthy
next command. Empty/one-byte inputs do not consume the probe: only actual
injection flips the one-shot flag. The six actual recovery guests passed this
staged-prefix scope; empty/one-byte probe non-consumption is source evidence,
not an additional claimed guest case.
The newest structural formatter/AU2003 diagnostic repair is also composed from
its frozen hash-checked delta. The accepted eleven-image matrix uses the fresh
matching compiler, rather than rebinding stale pre-repair objects.
