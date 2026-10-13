# Console services

The serial consoles are bounded, opt-in QEMU profiles. This is the living guide
to their commands, transport and trust boundaries. Run-specific results belong
in Git/PR history and retained evidence, not in the current behavior description.
No console is a general process shell, persistent filesystem or physical-machine
qualification. Do not write these images to a physical disk or change a bootloader.

| Profile | Current behavior | Boundary |
|---|---|---|
| BIOS | `help`, `status`, `exit`; IRQ4-woken serial editor | Aurora byte/command policy, trusted C++ storage/presentation and PIC/UART adapter |
| Simple UEFI | Aurora-owned editor, commands, RAM note and four named RAM files | Sealed ConsoleSession; trusted boot, UART, LAPIC and wake-frame checks |
| [Graphical](framebuffer-console.md) | Same RAM commands, two text rows and dirty-cell drawing; serial input | Separate ConsoleSession/DisplaySession grants; bounded emulator fixture |
| [Protected commands](program-console-contract.md) | `upper`, protected note read and uppercase replacement | Two CPL3 domains, authenticated copied IPC; retained legacy editor |

## Developer commands

Use the [local-development prerequisites and tool/firmware overrides](local-development.md).
Commands run from the repository root; do not mutate a profile image while it is in use.
Interactive sessions have a five-minute limit; `exit` closes QEMU sooner.

```sh
make console                 # BIOS interactive prompt
make console-uefi            # simple UEFI interactive prompt
make smoke-console          # BIOS PTY acceptance
make smoke-console-uefi     # simple UEFI PTY acceptance
./scripts/kernel-console-tests.sh
SANITIZE=1 ./scripts/kernel-console-tests.sh
```

`make run` and `make run-uefi` remain automatic boot self-tests. Console smokes
are included in `make smoke-all`; the native `make test` graph does not run QEMU.
Hosted sanitizers instrument the C++ adapters, not generated Aurora assembly.
Missing tools or firmware are blocked verification, never a pass.

## Input behavior

The 64-byte ASCII editor echoes printable bytes; backspace and DEL erase one
byte, with empty-line erase a no-op. CR, LF and CRLF each finish one line. Empty
input opens another prompt. Exact 64-byte lines are valid; a 65th printable byte,
other control byte, non-ASCII byte or observed UART receive error rejects the
whole line. Rejection stays latched through edits and suffixes until a delimiter.
Unsupported bytes are never echoed as terminal escapes. Commands are exact and
case-sensitive; BIOS supports only the three lowercase words in the table.

Simple UEFI and the graphical console import `console.line`; each invocation
owns a `console::Line64` with private bytes, length, rejection and CRLF state.
Accepted submissions expose copied bytes only until the next byte or damage
sample. The consumers keep their own prompts, echo, erase and responses.
The [sealed language service](../compiler/SERVICES.md) supplies copied input
observations and checked single-byte output. The linked simple-UEFI graph must
contain no C++ `Line`, `Presentation`, old byte/command wrappers or C++ command
response strings. Platform diagnostics remain trusted.

## Session-local RAM note

Simple UEFI and the graphical console share `console.session_note` for
`write note <text>` and `cat note`. The exact `write note ` prefix leaves at most
53 printable ASCII content bytes; its trailing space alone writes an empty note.
`cat note` reports missing or prints the content and a newline. Accepted writes
replace and clear the old suffix. Malformed, overlong or UART-damaged input
preserves the previous note.

One invocation-local `BinaryBuffer64` owns the note across idle waits and other
commands. Exit or output failure loses it; a new invocation starts missing.
The graphical consumer uses its ordinary response row and dirty-cell painter.
There is no disk access, persistence, heap, extra runtime authority or secure
RAM-erasure guarantee. Protected note commands have their own
[authenticated read and commit boundary](program-console-contract.md#session-local-protected-note).

## Session-local named files

The simple UEFI and graphical consumers share `console.session_files`:
`write NAME TEXT`, `cat NAME`, `rm NAME` and exact `ls`. Four named slots are
separate from `note`; note commands run first and keep their 53-byte limit.
`note` is reserved, `rm note` reports that reservation, and `ls` lists only named
files. Profiles share policy, never live storage between invocations.

Names are case-sensitive, 1–8 ASCII letters, digits, dots, underscores or hyphens.
`.` and `..`, paths and whitespace reject. Content is 0–49 printable ASCII bytes.
The space after the name is required for `write`, even with empty content; spaces
in content are preserved. There is no truncation or normalization. Malformed
commands, missing reads/removals and full-directory creation preserve all files.
Replacement succeeds when all four slots are occupied. Listing follows slot
order; deletion clears the complete record and the first free slot is reused.
Successful writes return `wrote NAME: N bytes` (`1 byte` for one), at most
24 display bytes.

Each workspace owns four 64-byte records and an occupancy mask (264 bytes total).
Each record contains one-byte name/content lengths, eight name bytes, 49 content
bytes and zero padding. A zeroed replacement is staged before direct record
commit; the constructor reuses one supplied zero buffer and starts unoccupied.
An 80-byte `FileReply` carries the closed outcome and display bytes. Presentation
receives the reply, not a workspace copy. Receivers are synchronously borrowed;
logical command-length checks remain separate from the 64-byte backing.

Exit or output failure loses the workspace; an already committed write is not
rolled back on output failure. No secure erasure, concurrent transaction or
general filesystem is promised. The 16 KiB stack, 15,360-byte mixed-stack cap and
4,096-byte IRQ/fault reserve remain unchanged.

## Trusted boundary

`kernel/console-session.hpp` authenticates the exact active host grant, closed
kind, nonzero monotonic generation and non-reentrant operation before transport
work. Pointer equality precedes dereference. Opening rejects an active invocation
and generation exhaustion. Polling revalidates across each trusted wait; closing
checks the closed completion code and exact active invocation once. Output timeout
terminates rather than retrying a partial response. Traps fail stop; no unwinder
or restarted editor is supplied. Source receives no pointer or device authority.

Every console LSR read, including transmit polling, latches receive errors.
RX-only flushing invalidates the old data-ready sample. Damage applies before
byte processing; an error exposed after a popped CR/LF also poisons the next line.
A lost pasted delimiter needs a later explicit newline for recovery. Ordinary
non-console serial behavior is unchanged. Explicit legacy `poll(editor)`/`put`
wrappers remain for BIOS and protected-command profiles.

## BIOS transport

`kernel.console` decides byte actions and classifies copied command prefixes.
The trusted C++ adapter owns the 64-byte array, validates each storage action and
provides presentation plus UART/PIC I/O. Only COM1 received-data interrupts are
enabled. A private IRQ4 gate acknowledges the remapped legacy PIC; foreground
code drains bytes with interrupts masked. `sti; hlt; cli` waits atomically when
idle. Sustained input still consumes CPU; storage, per-byte policy, writes and
session duration are bounded. This single-CPU QEMU PC transport is not a general
interrupt-controller or device driver. It has no note/file or process commands.

For a build-only check, use `KERNEL_CONSOLE=1 ./scripts/kernel-build.sh`.
BIOS admission retains the 65,024-byte transport payload limit; historical image
sizes are not current measurements.

## UEFI wake and authority

The simple profile runs ordinary private-memory, protection, language and ACPI
checks before its separate console-ready marker, without first running user
service fixtures. It enables ACPI and console, with no user runtime or service
budget fixture. There are no firmware calls after ExitBootServices.

- Copied ACPI topology, CPUID, MSRs, the final memory map and LocalApicAdmission
  must admit the fixed xAPIC aperture. Complete private mappings are checked
  before and after mapping it.
- UART interrupts stay disabled. Timer-woken polling uses a fourteen-byte FIFO
  trigger; BIOS IRQ input retains one byte. Idle waits arm a LAPIC one-shot for
  1,250,000 divided counts. This is not a physical-time calibration.
- The launcher retains normal UEFI's original QEMU clock, without `-icount` or
  `sleep=off`. Prompt latency and idle CPU require actual emulator measurement.
- Only the exact three-byte `sti; hlt; cli` region enables interrupts. The shadow
  permits the following CLI as the sole saved continuation. CR3, exact RSP/frame
  geometry, CS/SS, vector/error, flags, waiting phase, counter and LAPIC ISR state
  are independently checked before EOI. RF is permitted; TF, DF, IOPL and
  unrelated flags are forbidden.
- Timer mask/count, ISR and IRR quiescence are checked before waits, after receipts,
  during receive processing and at exit. Assembly restores all 15 GPRs and IRETQ
  on the same kernel stack. IRQ code never calls Aurora or touches the editor.

The adapter retains boot/MMIO, interrupt masking, wake authentication and
quiescence authority. The bridge carries only a private grant/generation record.

## Verification and acceptance gates

Routine `kernel-uefi-build.sh` runs ELF/PIC/PE, legacy-C++ retirement, private bridge,
complete mixed-stack and IRQ-closure checks. Ordinary build/console commands need
no external review token. Qualification of changed code additionally requires:

1. Source-positive/negative editor tests, hostile IR, packed ABI/callee-save
   controls, canonical copied-report traps, lifetime/reentry and UART models.
2. Exact generated and linked C++/assembly/Aurora stack accounting, including
   hidden/operand/return/alignment storage. Normal plus fault and wait plus
   IRQ/fault must fit 15,360 bytes within 16 KiB; IRQ plus fault must fit 4,096.
   Linked bounds are not runtime high-water measurements or arbitrary nested-fault
   and early-bootstrap overflow guarantees.
3. Actual original-clock PTY commands, editing, exact/overlong/malformed input,
   CRLF, note/file state, UART/pasted-delimiter recovery and exit checks. The PTY
   runner has a 30-second deadline, less than 250 ms paced/partial-response and
   less than 1,000 ms burst-recovery limits. Its 0.6-second idle sample permits
   at most 0.2 CPU seconds plus one scheduler tick. These are emulator acceptance
   limits, not hardware timing guarantees. Authority/transport faults must fail
   as intended.
4. Fresh normal-profile restoration boots, the
   [complete final-source GCC 16 gates](../AGENTS.md#workflow), and independent
   source/evidence review. Changed source invalidates its dependent results.

## First-change qualification and routine use

The build and guest driver use one checked artifact-bound image. To run the
existing qualification driver against an explicitly selected native profile:

```sh
image_dir="$(UEFI_MODE=console ./scripts/kernel-uefi-build.sh --print-image-dir)"
python3 -B tests/kernel-console-service-qualification.py --mode console --build-dir "$image_dir"
```

The driver validates that image before the guest, leaves it unrebuilt, and checks
its admitted artifacts afterward. It retains the transcript and result, and
builds and actually boots normal UEFI for restoration even after a PTY failure.
No externally supplied reviewer digest is required. Independent source/image
review and the final-source gates above remain requirements for changed code;
a generated report or successful guest does not replace them.

The four fault images exercise stale generation after close/reopen, operation
reentry from a wait hook, transmit failure after exactly 17 output bytes and a
noncanonical copied damage boolean. The timeout is a transport-result injection,
not actual UART hardware fault induction. Hostile source/IR and fake-port UART
controls remain separate. Historical passes cover only their recorded source,
toolchain and emulator; they do not qualify a later image or prove OS readiness.

`SessionFiles` exposes checked copied `FileName` and `FileValue` inputs for const
reads and atomic writes/removals. Names retain the eight-byte grammar and values
the 49-byte printable-ASCII limit; invalid values cannot alias a valid empty file.
The console `submit` adapter preserves the same transcripts and four-slot order.
`ProtectedFiles` selects a copied name and projects it directly without copying
the store or synthesizing commands. Replacements use the same typed write path;
revision invalidation/exhaustion and native authenticated one-shot authority are
unchanged. These copied values carry policy data, never mailbox authority.
