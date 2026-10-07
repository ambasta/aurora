# UEFI console focused results — 2026-10-07

## Qualified scope

`make console-uefi` opens a bounded serial prompt after the normal private-memory, protection, language and ACPI
self-tests. It uses the shared copied 64-byte editor and Aurora policies. UART interrupts stay disabled; admitted
LAPIC one-shots wake polling under the normal original QEMU clock. The fourteen-byte receive trigger avoids QEMU's
one-byte backend cadence while preserving the BIOS IRQ profile's one-byte trigger. All continuing console LSR reads
share sticky receive-error handling, including output polling and delimiter-loss recovery.

The final compiler is SHA-256 `762ba74b8b58d4c6ae7c335507a7b06560a90f44c98d268defa36e086fa41630`, with the complete
PR53 compiler implementation verified unchanged. The qualified source manifest is
`266d26f354af3ec7764015b23ee63d5ab90f40663562ab0439c994cea4936a11` (697 files). The later PR54 library/test/docs join
preserves every kernel, script, example and compiler implementation byte; its XFS registrations are retained.

QEMU SHA-256 is `d3c1a558ad220e77a4412048c8d96b44f8c2b41c7ad2a4ecfe522a4b122fe067`; combined OVMF is
`14954040cc754ade0c625ac3470ea46d4c14318b5b1396de4ef77090203d76db`. All 146 historical runtime entries and 83 static
dependency nodes were checked. No firmware template was modified.

## Actual gates

- Shared editor/policy and presentation: passed; presentation has 212 observations.
- UART error injection/recovery: 224 observations for each of the independently specified one/fourteen triggers,
  normal and fatal C++ ASan/UBSan. Generated Aurora assembly is not sanitizer-instrumented.
- Unchanged copied-frame tests: 66,971 observations, including an independent RF-positive case and forbidden-bit
  controls, normal/fatal sanitizers. Existing emulator-clock and developer-command routing controls passed in normal
  and optimized Python; the dedicated console-clock controls passed in normal Python.
- Both final-compiler console builds and the initial service build passed warning-clean image/layout checks.
- Independent linked review verified actual page-touch probes, unchanged ABI/register constraints, exact wait bytes,
  complete restore/IRET behavior and regenerated fault/return metadata before guests.
- Final UEFI PTY interaction passed short/one-byte input, help/status/exit, editing, CR/LF, exact/over-capacity lines,
  malformed/control input, pasted-line rejection, recovery and explicit exit 33.
- UEFI measured responses were 3.12–20.77 ms after the final send, below the unchanged 250 ms paced-input limit.
  The 0.600105-second idle sample accumulated 0.01 CPU seconds at host scheduler resolution. There were 78
  authenticated wakes before the checked masked/empty ISR/IRR exit. The timer count remains 1,250,000; it is not a
  physical-time calibration. No `-icount` or `sleep=off` was added to this interactive profile.
- BIOS interaction regression passed, with 3.11–3.13 ms measured responses and zero CPU ticks over 0.600098 seconds.
- Existing `user-phases`, `user-root`, `user-pending` and `user-retire-pending` gates passed their original clocks and
  strict validators. The root case rejected as intended. Each actual image passed established build/image checks
  before QEMU; `user-phases` also reproduced its independently admitted ELF hash.
- Actual normal BIOS and UEFI boots passed afterward; console symbols, UEFI console metadata and prompt markers were
  absent. All owned children were reaped and source/compiler/runtime pins held.

The final nine-step guest successor ended successfully after 62.19 seconds. Peak sampled whole-tree memory charge
was 397,762,560 bytes, including a 192 MiB outer allowance; owned outputs peaked 18,595,840 bytes. The admitted model
used a 2 GiB sampled tree allowance, 7.5 GiB entry threshold, 5.5 GiB continuing reserve/floor, 256 MiB output cap,
8 MiB file cap, ordinary 1.5 GiB address space and unlimited reserved VA with sampled 512 MiB RSS ceilings for QEMU
and sanitizers. These samples are not hard kernel memory quotas.

## Linked stack scope

The final UEFI console ELF is `bbaf0c12fa44941195a39b7e8940d975623279efe5f3a87e1aed090f6fd5236d`;
BIOS is `6cd3421d1e3d10345b6d71056e2c92e885c93102448357aace6a45d7504c886c`;
service image is `02a36b9d18f6942fd2b37a9daa5e668ca60677cc463574f9d37ec06d8b506131`.

The independently accounted console IF-off peak is at most 6,888 bytes within 16 KiB. Its IRQ entry and full closure
are at most 632 bytes, below the separate 4 KiB reserve. The BIOS console chain is at most 328 bytes within 32 KiB.
For service-profile pre-runtime ACPI/PCI discovery, the conservative bound is 15,064 bytes within 16 KiB; runtime plus
drain/IRQ closure is below 9,216 bytes. Generated service policy chains peak at 512 bytes. These are linked chain
budgets, not runtime high-water measurements or arbitrary nested-fault/early-bootstrap overflow guarantees.

## Preserved failures and limits

The first recovered preflight stopped before a child because its directory inventory mishandled the pinned keymaps
symlink and included unrelated historical directories. That failed receipt remains separate from the corrected run.
The first real interaction opened its prompt but failed the unchanged latency bound: 274.469 ms for a 64-byte line.
The FIFO-trigger correction then passed interaction/idle/recovery, but a later service build exposed an unreferenced
`timer_write` wrapper under `-Werror`; deleting it preserved warning enforcement. A final-compiler native/linked
controller reached its review-wait deadline without running guests. Its native outputs and accepted linked images
were retained, then a fresh bounded successor completed the actual guests. That timed-out controller is not relabeled
as passed. Earlier pre-recovery finite-handoff raw evidence is unavailable and is not used as current qualification.

This is focused emulator qualification. It does not establish the full native aggregate, full boot matrix, calibrated
hardware timing, physical Framework/AMD support, IOAPIC UART routing, a graphical desktop or general process shell.
