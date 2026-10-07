# Opt-in UEFI serial console

The opt-in profile adds `make console-uefi` beside the existing `make console` BIOS prompt.
The interactive profile uses the normal UEFI payload and its ordinary private-memory, protection, language and
ACPI checks. It does not first run timing-sensitive user service fixtures. A successful ordinary self-test marker
precedes the separate console-ready marker.

This is an experimental QEMU serial interface, not a graphical terminal or a hardware-qualified Framework driver.
There are no firmware calls after ExitBootServices. It accepts the existing bounded ASCII editor and Aurora command
policy: `help`, `status`, `exit`, backspace/delete, and CR/LF/CRLF. Storage remains a copied 64-byte kernel-owned line.
No parser or raw user-memory access is added.

## Wake and authority contract

- The new build profile enables ACPI and the console only. It links no user runtime or service-budget fixture.
- Copied ACPI topology, CPUID, MSRs, the firmware memory map and the existing LocalApicAdmission policy must admit
  the fixed xAPIC aperture. The complete private mapping tree is checked before and after that mapping.
- The UART interrupt-enable register stays zero. This is timer-woken UART polling, not UART interrupt support.
  Its fourteen-byte FIFO trigger lets QEMU admit batches; the BIOS received-data IRQ profile keeps one byte.
  Each idle wait arms one LAPIC one-shot for 1,250,000 divided timer counts. That count is not a physical-time
  calibration; actual prompt latency and idle CPU must be measured on the qualified emulator.
- The launcher uses the existing normal UEFI original-clock command. It adds no `-icount` or `sleep=off` setting and
  changes none of the existing timer test modes or their validators. The terminal session is limited to five minutes.
- The only interrupt-enabled console region is the exact three-byte `sti; hlt; cli` sequence. Its interrupt shadow
  admits the following CLI as the sole saved continuation. CR3, exact RSP/frame geometry, CS/SS, vector/error,
  integer flags, waiting phase, counter and LAPIC ISR state are independently checked before EOI.
- RF is permitted like the existing supervisor service-frame policy. Historical QEMU 10.0.13 diagnostic evidence
  observed RF in a hardware timer's saved flags. TF, DF, IOPL and unrelated flag bits remain forbidden.
- Timer mask/count, ISR and IRR quiescence are checked before waiting, after each receipt, during receive processing
  and at exit. The dedicated assembly entry restores all 15 GPRs and returns through IRETQ on the same kernel stack.

## UART error recovery

The console-only UART wrapper observes receive errors on every LSR read, including output-side polling. An error
latches rejection and flushes RX only, invalidating the old data-ready sample. A delimiter popped just before a new
error also poisons the next line so finishing the old line cannot erase the rejection. A lost pasted delimiter
requires a later explicit newline before recovery. Ordinary non-console serial behavior is unchanged. The BIOS
console shares this correction so its existing rejection promise also covers output-side LSR reads.

## Qualification boundaries

The [focused results](uefi-console-results.md) record hosted, fatal sanitizer, linked and actual guest passes.
Future executable changes must re-establish
both the complete IF-off main/editor/Aurora call chains against the 16 KiB stack and the complete IRQ closure against
its separate 4 KiB checked reserve. Account for generated frame/hidden/operand/return/alignment storage. These are
linked stack budgets, not runtime high-water measurements or a guarantee of arbitrary nested fault recovery.

The completed focused gates cover shared editor/presentation/UART tests, copied-frame flags including an independent RF
positive case, command/clock controls, image layout and real UEFI/BIOS PTY interaction. PTY acceptance measures
post-last-send response latency, a 0.6-second idle CPU sample, pasted-line rejection with lost-delimiter recovery,
clean exit and actual normal-image restoration. Affected user timer-origin and pending-drain controls also passed.
The full boot matrix and physical AMD/Framework qualification are outside this increment.

## Recovery provenance

The initial reconstruction started from PR50 commit `e1d776b2cd25a5fd4f997dcc3c931be6bbbe8fbb`.
The executable qualification used PR53 commit `92e28a823afe56af774a128df8f9093083f26e29`, tree
`3801b9524589ce363f7ce00aae505c88c7d86679`, with its qualified source-matching page-probing compiler.
The prior finite handoff
milestone had reported successful focused qualification, including an RF-only correction after a preserved
fail-closed frame result. Its local raw logs/archive are unavailable after the workspace view change; this source
candidate does not treat that report as fresh runtime evidence. The interactive candidate had reached hosted
checks only and stopped on an unrelated stale BIOS smoke-script pin before any image or guest build. The pin is
now corrected with closed full-file provenance, unchanged executable-body identity, and an early-guard behavior test.

## First fresh latency attempt

The reconstructed source passed hosted normal/fatal-sanitizer, routing/clock and image gates. Independent linked
review bounded the full UEFI IF-off chain at 6,888 bytes and the IRQ closure including entry at 632 bytes. The real
original-clock guest opened its prompt and handled commands/editing, but its 64-byte response took 274.469 ms,
exceeding the unchanged 250 ms test bound. Idle CPU and later rejection/recovery cases were not reached. Actual
normal BIOS and UEFI restoration passed afterward. The next narrow source correction selects a fourteen-byte FIFO
trigger only for UEFI polling and preserves it across RX-only error flushes. It leaves the clock/count and latency
limit unchanged; the subsequent focused passes are recorded below and in the results.

## Corrected interaction and final compiler join

With only the five UEFI FIFO immediate values changed, the original-clock interaction passed all commands,
short-input, invalid/pasted-input rejection and recovery controls. Responses measured 3.10–20.64 ms after the final
send. The idle sample observed zero scheduler CPU ticks over 0.60013 seconds, not proof of zero work. There were
78 authenticated wakes before quiet exit. The unchanged BIOS payload passed its interaction regression; both actual
normal restorations passed. A subsequent service-profile build failed -Werror on an unused timer_write wrapper,
before its guest ran. Removing that dead wrapper preserves the warning gate and all timer-origin checks.

This source is now joined to PR53's page-probing compiler. Generated frame/record allocations touch each reserved
page before proceeding. Those probes neither replace the trusted C++/assembly stack budgets nor establish reliable
early-bootstrap overflow diagnosis. Fresh emitted-code/layout/fault-phase review, linked accounting,
full interactions, focused
console/timer guests and actual normal restorations passed on this exact final compiler. See the
[results](uefi-console-results.md) for measured latency/idle CPU, preserved failures and limits.
