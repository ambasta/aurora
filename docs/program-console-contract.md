# Protected command console

This living guide covers the bounded two-domain command profile. Current behavior
and required checks are described below; run-specific results and failures remain
in Git/PR history and retained evidence. Historical passes do not replace the
[final-source qualification gates](../AGENTS.md#workflow).

## Observable gate

An opt-in UEFI `program-console` image accepts `upper`, then `text> Hello, Aurora 42!`,
and prints `HELLO, AURORA 42!` once before returning to `aurora>`. The uppercase
transformation executes in a separately compiled, one-page RX Aurora CPL3 client.
A separate CPL3 stream service validates and returns its requested output byte.
This is an embedded bounded application demonstration, not a general process or
syscall ABI, filesystem, terminal emulator, or hardware qualification.

## Aurora-owned console turns

`console.program_input` uses the existing sealed `ConsoleSession` to own one
command-reading turn: the shared `Line64` editor, echo, rejection, help/status,
`upper`'s `text>` prompt and exit presentation. The accepted command delimiter
is written before returning a copied `ProgramSubmission`; commands typed after
`text>` are payload, including empty
input and the words `help`, `status` and `exit`. The one-bit CR carry crosses
turns so a queued LF after a protected command does not submit another line.

The native adapter validates the copied result and releases the console grant
before note/file mutation or protected execution. It retains command dispatch,
authenticated lifecycle/publication and note/file commits. `console.program_output`
then presents a copied, bounded `ProgramResponse` and the following prompt through
the same sealed capability. Ready, saved, missing, stopped and unknown responses
carry no payload; output and local file replies carry at most 64 bytes. Presentation
preserves every payload byte, including NUL, control and non-ASCII values, as the
previous native output path did. Count, payload kind and zero suffix are checked
before writing. The private native ingress also checks raw enum representation
before Aurora observes a typed enum.

Each input or response turn gets a fresh grant only at the quiescent boundary;
the grant is released before proceeding. Response handoff copies are scrubbed
before continuing; copied submissions survive until their command handoff. UART
initialization happens only once, preserving damage latched by runtime diagnostics. No new service kind, pointer-bearing
source interface or execution authority is added to `ConsoleSession`.

The first output failure ends the turn without retrying bytes, emitting another
prompt or reading another command. A delimiter failure prevents dispatch. An
acknowledgement failure after a note/file commit does not undo or repeat that
commit; the session follows its existing quiet failure exit and clears session
stores. Native lifecycle and authority diagnostics remain outside these turns.

The private entries use compiler ABI facts alongside the existing linked-image
stack checks. These migrations are source-only; generated ABI, stack limits and
actual boots still need final-source qualification.

## Session-local protected note

The current source also accepts `write note <text>`, `cat note` and `upper note`. One RAM-only
note holds at most 53 printable ASCII bytes and is cleared on exit. It is a
copied value, not a RamSectorDevice, filesystem or persistent file. The existing `console::SessionNote` Aurora library owns exact command
matching, validation before replacement, missing/empty semantics and suffix
clearing. The supervisor-level Aurora wrapper classifies `upper note`; the native
adapter never computes the uppercase transformation.

An ordinary `update_note(SessionNote, BinaryBuffer64, i64) -> NoteUpdate` returns
a closed 72-byte note plus an explicitly mapped 8-byte event. The native bridge
commits that result only at the quiescent console boundary, with no Mailbox,
active domain, retained frame or bound read. Native initialization has an exact
private representation; a generated `SessionNote(empty)` constructor-equivalence
fixture checks it. Invalid input preserves the old value.

Each read freezes an Aurora `NoteRead64` projection: 64 payload bytes and a signed
length, with -1 representing missing. The small dependency-free module adds no
console, storage or runtime authority to CPL3. The service receives three scalar
launch words and that 72-byte value in an exact 96-byte record at stack-top-112.
The final qword belongs to this explicit note contract; the distinct snapshot
profile keeps its original zero-padding contract. The wrapper reserves 112 bytes
before its 48-byte envelope so generated calls grow below the copied record.
Upper uses the same typed service entry with a zero placeholder, without copying
the saved note into that command's domain.

Fresh endpoint generations bind each frozen read. After authenticated receive,
the adapter stages it through the retained, verified last stack-page lease under
both the domain and kernel mappings. The compiled client requests absolute
offsets (phase 12), the compiled service returns actual byte/EOF/missing data
(phase 11), and the compiled client validates each reply (phase 13). Byte replies
encode `1 | byte << 8`; EOF is 2 and missing is 3. A read includes one final EOF
round even when empty. No expected-pattern fallback or native payload oracle is
used. The shared Aurora command ledger validates order, closed encoding and exact
client acknowledgment. Native publication releases output only after Mailbox
revocation and both domain retirements. Missing is reported after the same
authenticated retirement boundary.

`write note Hello, Aurora`, `upper note`, `cat note` produces `HELLO, AURORA`.
For an existing note, Aurora selects a non-mutating upper action. Its copied
projection becomes the existing uppercase stream's input before domains are
created; no new program, mailbox phase or capability is introduced. A missing
note uses the authenticated missing-read path and remains missing. An empty
note completes the existing zero-byte stream lifecycle and remains valid empty.

Only a completely acknowledged stream, successful quiescent retirement of both
domains and successful whole-output extraction may reach replacement. Native
preparation bounds the completed output to 53 bytes and forms a `write note `
command for the same Aurora update bridge and `SessionNote.submit` policy. The
commit boundary rechecks no command owner, Mailbox, frames, bound projection or
active runtime. Partial faults, budgets, bad output and cleanup failures cannot
replace the original note. The completed output is acknowledged with `Note saved.`;
`cat note` performs the separate protected readback. There is no general protected
file-write API. Scratch records have separate lifetimes outside domain creation
and retirement; stack/image limits are unchanged.

Recoverable request/service/completion faults or budgets discard partial output,
release the frozen projection and return to the prompt. The saved note survives,
and a healthy retry uses fresh domains and grants. Invalid authority still fails
stop. Current PTY coverage adds missing, repeated, empty and 53-byte uppercase
saves/readbacks. Each recovery profile first interrupts `upper note` after partial
progress, verifies the original via `cat note`, then saves and reads the successful
retry before the retained upper cases. Hosted cancellation controls retain the
read-recovery cases. These additions require final-source linked/image, actual
guest and full qualification; historical results do not transfer to changed code.

Pre-guest checks cover aggregate/bridge/inventory consistency, real Mailbox
lifecycle and Aurora constructor equivalence, alongside source/ABI/stack and
transcript controls. Hosted ASan/UBSan does not instrument generated Aurora.
Every variant retains the 131,072-byte mapped-image limit and 15,360-byte
supervisor-plus-fault cap within the 16 KiB stack. Fresh exact-image accounting
must establish the current peaks; historical measurements cannot admit a rebuild.
Legacy scalar/snapshot wrapper checks are separate from actual snapshot guests.

## Protected named RAM files

The source-native named-file mechanism adds `write <name> <text>`, `cat <name>`,
`upper <name>`, `append <name> <text>`, `copy <source> <destination>`, `ls` and `rm <name>`. The existing `console::SessionFiles`
continues to own its exact grammar and four-slot, eight-character-name,
49-printable-byte content limits; `note` remains reserved for the separate note.
An existing file can be replaced when all four slots are occupied. Names are
case-sensitive, an empty existing file is distinct from missing, and all state
is volatile and cleared at console exit. Copy runs through the local quiescent
mutation path; it does not launch a protected program or grant new authority.

`console::ProtectedFiles` adds a copied private selection and a session mutation
revision around that unchanged store. Every successful write/removal/replacement,
including an identical write or self-copy, invalidates all old selections. This conservative
rule also invalidates a selection after an unrelated-file mutation. Deletion and
slot reuse cannot resurrect it. Revision exhaustion refuses mutation without
changing any saved byte and still permits reads/listing. Failed validation and
full-store refusal preserve the complete store and revision.

A selected file is projected by Aurora, bound to actual fresh Mailbox owners and
grants, and copied only into the authenticated service's verified stack record.
The protected client requests offsets and receives actual service bytes through
the same 12/11 read phases as the note. `upper <name>` uses completion phase 14:
its Aurora client returns the original encoded service byte in bits 0–15 and its
uppercase output in bits 16–23. The shared Aurora command ledger requires exact
original-byte acknowledgment, closed encoding and a printable output byte; it
never computes the transformation. EOF/missing retain their exact terminal encoding. Both
empty and nonempty files require a final authenticated EOF round; a missing
selection is read through IPC and cannot create a file.

Replacement authority is private, one-shot and bound to the actual client
incarnation, endpoint generation, selected file and exact stream run. A read-only
grant cannot mint it. The bounded stream run generation does not reset on
cancellation, so restarting the same ledger cannot reuse a live or retired
receipt; exhaustion refuses a new run without wrapping. Completion is recorded
only after the entire stream is acknowledged with an idle, scrubbed Mailbox.
After grants are revoked and both original domain incarnations are retired,
that receipt alone permits one extraction. Aurora rechecks the selected revision
and name, validates the complete output and atomically updates only that record.
The console reports `File saved.` after publication; `cat <name>` gives separate
protected exact readback. Faults, budgets and cancellation discard staged output
and authority while preserving every old file, then a healthy command starts
with fresh grants. This is a bounded command service, not a general file API,
filesystem, persistent store or proof of production security.

Existing native generated-code and PTY fixtures cover this path alongside the
note/scalar regressions. Compact aggregate copies, referenced-only supervisor
reflection emission and shared native cleanup retain the unchanged mapped-image
and stack caps. Both copied-value bridges use the shared image/ABI/stack admission
workflow; no separate admission workflow is introduced. Hosted checks and
transcript controls do not establish a booted named-file image. Changed source
still requires final linked-image, actual guest, full-native and independent-review
qualification.

## Shared copied command ledger

`console::CommandStream` owns copied bytes and request/reply/ack, read-terminal,
finish/cancel and scrub transitions. Native code retains only the opaque value,
noncopyable stream identity and nonwrapping run generation, with no duplicate
transition implementation. Scalar commands remain bounded to 64 bytes, reads to
53 bytes plus an acknowledged terminal round, and named-file publication to 49.

`Files` still binds the exact stream and run, requires an idle scrubbed Mailbox,
and permits one-shot publication only after revocation and both original domain
retirements. Copied library values grant none of that authority. The existing
copied bridge and ABI/stack admission also check the named operation mapping.
Direct host scripts now require a selected `AURORAC`. This migration was reviewed
only as source; compilation, runtime behavior and image/stack qualification remain
unverified.

## Authority and data

Exactly two real domains use `ipc::Mailbox`, not the three-domain dispatcher.
The Aurora reader returns checked copied input after its invocation-local editor
finishes. The native submission is cleared at the existing command handoff. This retires
live input state; it does not promise physical erasure of every temporary copy in
ended supervisor stack frames. Those frames are not mapped into protected domains.
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

## Checked images and local guest qualification

Meson builds each selected profile in its own `kernel-images/uefi/PROFILE`
directory. Declared source, compiler, generated-header and sidecar dependencies
invalidate the affected products. A profile build runs the shared image, private
ABI and stack checks before producing one artifact-bound admission report; it
does not launch a guest. There is no separate source/tool snapshot or reviewer
checksum workflow.

Stack accounting uses C++ `.su`/`.ci` and Aurora `.stack.json` emitted with the
actual compiled objects. The shared graph checks object/link association,
function and call membership, cycles and profile budgets. Handwritten bridge,
protected-entry and interrupt contracts remain explicit. The page-table walks
are iterative. Supported local PIC switches require a bounded read-only table,
exact in-function targets and no entry that bypasses their guard. Unknown
control-transfer forms reject. Compiler metadata and trusted inline assembly are
part of the assurance boundary; these checks do not independently prove compiler
correctness, memory authority or termination.

Native frames bound to an exact object compilation may name selected kernel
sources or readable headers under the canonical pinned `/usr/include/c++/16`
root. Kernel locations remain repository-relative; header locations are canonical
absolute paths, with source hashes and coordinates retained. Escaping symlinks,
other include roots/GCC versions and historical unbound header frames reject.
This recognizes the standard-library implementation already trusted when inlined;
it is a provenance/review scope, not an additional security proof. Protected
program profiles use size optimization within the unchanged 128 KiB payload
reservation; complete frame/edge checks and stack limits still apply.

Version 2 Aurora facts also describe the R11 packed-input/R10 copied-result ABI
for receiver-free dense non-owning values and qword scalar parameters. The four
note/file boundaries require those facts and retain independent source-entry
selection, private linkage and ordered native record sizes. Compiler-produced
`.abi.json` maps each selected source declaration to its emitted symbol for the
protected supervisor and copied CPL3 service bridges and admission; no mangling
recipe is duplicated there. Scalar policy exports live in `kernel-policy-entry.S`;
imported library helpers stay local. Compiler-local frames, spills and return
paths are not duplicated in their admission checks. Padded, owning, capability
and receiver signatures have no such fact. Version 1 remains supported only for
stack accounting; it cannot supply a copied-record boundary contract. These facts
trust compiler lowering; executable copy/canary and guest tests remain necessary.

Ordinary commands build and check the selected native profile before running the
same original-clock PTY and hostile transcript oracles:

```sh
make program-console-uefi
make smoke-program-console-uefi
./scripts/kernel-program-console-smoke.sh program-pending
```

For an independently reviewed, already built image, pass its explicit directory
to the same guest oracle. It checks admission before and after execution without
rebuilding that image or requiring a review token:

```sh
image_dir="$(UEFI_MODE=program-console ./scripts/kernel-uefi-build.sh --print-image-dir)"
# Review this image and its generated ABI/stack evidence before first-change qualification.
python3 -B tests/kernel-program-console-pty.py --mode program-console --build-dir "$image_dir"
./scripts/kernel-uefi-smoke.sh normal
```

Profile-local outputs leave the normal image untouched; the final normal command
above verifies an actual restoration boot. Each PTY attempt retains the admitted
report, clock command, raw transcript, stderr and metrics under
`build/program-console-evidence`. Its result does not replace independent review,
final-source `full` or affected guest gates. Missing tools/firmware are `BLOCKED`;
invalid controls, build/admission errors, wrong exits and failed oracles are `FAIL`.
Neither is a successful or skipped guest test.

Compiler-free controls in `tests/kernel-program-admission.py` and
`tests/kernel-program-console-entrypoints.py` cover artifact changes, profile
selection, stale-report rejection and public build/check/PTY routing. The
`diagnose` action produces stack diagnostics without issuing an admission report.
These controls do not establish compiler, guest or physical hardware qualification.

## Recovery and hostile-profile checks

Every program runtime/timer trace and input operation uses one sticky-latch UART
specialization so diagnostic LSR reads cannot clear errors before the editor sees
them. Other profiles retain their own routes. A source-routing guard covers the
include chain; hosted UART controls inject receive errors during runtime-style TX
before copied submission.

The guest oracle authenticates supervisor pending-drain records against the owned
arena/root, exact admitted drain PC interval, frame range, active epoch, terminal
state and paired drain evidence. Owner, ordinal, transaction and unknown-site
profiles must fail stop with no output or prompt recovery.

Request/service/completion fault and budget probes inject only at ordinal 1,
after one complete triplet stages a byte. The oracle requires that prefix and
the failing-phase prefix, no released partial output, retirement and a healthy
next command. Empty/one-byte inputs do not consume the probe; only actual injection
sets its one-shot flag. The note/uppercase recovery cases must also verify that
partial progress preserved the saved value and that retry uses fresh domains.

Independent qualification covers all twelve profiles, their exact source/images
and original-clock traces, plus actual normal BIOS/UEFI restoration and the final
native/review gates. A wrapper's normal-image rebuild is not that restoration boot.

Named-file `append NAME TEXT` uses the same Aurora `SessionFiles.append_file` operation
as ordinary console consumers. It requires an existing file, preserves the 49-byte
content bound, and commits at the existing quiescent update boundary. Empty suffixes
are successful writes; all successful appends advance the protected store revision.
Rejected appends preserve the complete store and revision. No grant or bridge layout
changes are involved; protected `cat` and `upper` consume the resulting file normally.
