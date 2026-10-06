# Provisional UEFI emulator clock qualification

## Status and preserved failure

**Source preparation only, not a newly qualified kernel checkpoint.** The clock
selection, command binding and native-free source tests below are authored for
independent review. This combined IPC/tooling/clock candidate has not inherited
acceptance from the earlier round-robin checkpoint or the separate portable
native-test workflow. Its tooling base is accepted PR27 main
`772b9c8a6291aa3cc656b409ce0263f73d45b034`, tree
`62a2728942d9c36df16bd00189260f6a94cb847e` (merged 2026-10-05 22:52:33 UTC).
The combined IPC/clock reconciliation still needs independent review and a new
source/tool/command freeze before new acceptance. This document authorizes
no compiler, native, image-building or QEMU workload.

The original 177-mode IPC aggregate remains **FAIL**: mode 163,
`user-retire-pending`, exhausted an ordinary 128-interrupt service run and exited
35 where 33 was required, after 162 partial passes. Both original normal
restoration boots remain separately preserved. A later, instrumented single
attempt on the retained failed image exited 33; it is an inconclusive diagnostic,
not a repair, proof of host-contention causality or acceptance credit. The original
failure remains unresolved stress evidence. Neither the 162-mode prefix nor the
traced success transfers to this changed scheduling contract. Historical 173-mode
and earlier passing checkpoints retain their original source and clock identities.

The related earlier failure is also preserved: a warmed wall-clock TCG run could
finish the old 100,000-iteration dispatcher service before a compiled-code
interrupt. Its existing million-iteration replacement remains unchanged. Neither
historical failure supports tuning a loop, budget or clock until a test passes.

## Exact closed scope

`scripts/kernel_emulator_clock.py` explicitly enumerates every current
family/mode pair. Exactly **51 UEFI modes** select
`tcg-fixed0-noalign-nosleep`: the 19 service-budget, 15 dispatcher and 17 user-phase
modes. The selected-name set is bound to the reviewed scope map SHA-256
`efd2c6c057d85bdd05cc66b0bbef7db629abdf797361347a96fee6aa1732dc99`.
It is the complete existing UEFI timer mechanism/control family, not a prefix
heuristic, success-only subset or selection by observed failures.

- Budget: `budget`, `budget-fault`, `budget-context`, `budget-pending`,
  `budget-noapic`, `budget-smp`, `budget-discovery`, `budget-cache`, `budget-alias`,
  `budget-forged`, `budget-root`, `budget-mmio`, `budget-softint`, `budget-fpu`,
  `budget-epoch`, `budget-policy-zero`, `budget-policy-counts`,
  `budget-policy-wide`, `budget-policy-output`.
- Dispatcher: `dispatch`, `dispatch-budget`, `dispatch-fault`, `dispatch-mixed`,
  `dispatch-pending`, `dispatch-cross-reply`, `dispatch-client-owner`,
  `dispatch-stale`, `dispatch-duplicate`, `dispatch-full`, `dispatch-root`,
  `dispatch-peer-code`, `dispatch-policy-cursor`, `dispatch-policy-mask`,
  `dispatch-policy-output`.
- User phases: `user-phases`, `user-context`, `user-retire-pending`,
  `user-request-budget`, `user-completion-budget`, `user-request-bounds`,
  `user-completion-bounds`, `user-request-overflow`, `user-completion-overflow`,
  `user-pending`, `user-role`, `user-phase`, `user-transaction`, `user-epoch`,
  `user-root`, `user-unknown`, `user-stale-grant`.

All **126 other modes** retain `tcg-original-clock`: 37 BIOS, 71 ordinary UEFI,
7 BAR and 11 IVRS. This includes the four new IPC transition-policy negatives.
The three separately counted BIOS capacity probes (`full-127`,
`old-96-negative`, `last-sector-negative`) and both final normal BIOS/UEFI
restoration boots retain their original clock too. The BIOS nine-mode scheduling
family is separate and still has its historical wall-time assumption; no universal
timer-test repair is claimed. The existing non-normal EXIT traps rebuild a normal
image; they do not substitute for the two required actual normal restoration boots.

## Effective command, not a friendly label

The selected profile adds exactly:

```text
-icount shift=0,align=off,sleep=off
```

The pre-reset independent review found that its identified QEMU binary supported
this fixed instruction-derived virtual clock and selected single-thread/round-robin
TCG execution, including with one guest CPU. These are historical findings about
that binary, not installed-tool qualification of the reconstructed environment.
The previously reviewed executable is absent after the executor reset, and QEMU
is currently unavailable for this reconstructed workspace. Any future execution
requires restored and verified QEMU/firmware identities and fresh admission.

The changed execution model remains part of the proposed qualification identity.
`budget-smp` deliberately keeps `-smp 2` and its original pre-timer admission
rejection. Retirement's one-CPU envelope does not apply to that control. Other
selected modes retain one guest CPU.

The common launcher retains q35, TCG, qemu64 (and its existing special CPU for
`runtime-sysenter`), 128 MiB, firmware, devices, drive, network/display/monitor,
serial, debug-exit and the 30-second timeout. `acpi-two` still uses two CPUs.
Separate BIOS/BAR/IVRS launchers and BIOS capacity code are unchanged. There is
no new clock or arbitrary-QEMU-argument environment override, adaptive shift,
retry-based tuning or fallback. Existing `QEMU`, `QEMU_DATA` and `OVMF` still
select their original executable/data/firmware inputs; an acceptance runner must
continue to pin their real identities.

Unknown/explicitly empty modes and extra/duplicate positional arguments fail
before any image build or receipt write. Omission alone defaults to `normal`.
The helper rejects unknown/duplicate/conflicting clock declarations, absent or
repeated icount, auto/altered/alias options and unintended clocks on exclusions.
The common-launcher check compares the complete effective QEMU argv byte-for-byte
against the closed canonical command for that mode and its selected paths. Thus
a matching label with wrong/missing options, CPU count, device, firmware, network,
monitor or other argument cannot pass. The validated Bash array is the same quoted
array executed by `timeout`; it is never reconstructed through shell word splitting.

Before execution, `build/uefi/<mode>.clock.json` records the family, mode, profile,
complete QEMU argv, complete timeout argv and canonical 177-mode clock-map digest.
This is only a validated command receipt. Its execution-status field explicitly
establishes no runtime outcome. The unchanged raw QEMU/timeout exit is still
passed directly to the original strict serial validators: the selected modes
retain 19 required exit-33 successes and 32 distinct exit-35 negatives.

`mode_clock_sha256()` hashes UTF-8 JSON of `mode_clock_rows()`, sorted by
`(family, mode)`, with sorted object keys and compact separators. The 182-entry
qualification includes the separately explicit five capacity/restoration
exclusions as well; acceptance must independently bind those commands. The helper's
`validate_clock_options` is only a clock check for already command-bound external
receipts; it is not a replacement for their complete argv/provenance validators.

## Unchanged guest obligations

No guest/kernel C++, assembly or Aurora source, loop, timer constant, budget,
strict validator or expected outcome changes. Ordinary phases retain the original
128-interrupt bound, and a finite service must finish with `used < 128` wherever
that was required. The nine real exhaustion modes remain `budget`,
`budget-context`, `budget-pending`, `dispatch-budget`, `dispatch-mixed`,
`dispatch-stale`, `user-request-budget`, `user-completion-budget` and
`user-stale-grant`: each controlled infinite stage still requires exactly three
charged authenticated hardware interrupts and two resumes, followed by its
original cancellation/restart or disposal/rebinding behavior.

Every existing compiled-service hit, authority/frame/epoch/ISR check, exact trap
site, ordered IPC transition, pending drain, scrub, retirement and cleanup gate
remains. `budget-context` still needs its service sentinel/DF interruption;
`user-context` needs both client-0 request countdown interruptions and restored
sentinels/DF. Short client runs gain no invented compiled-hit requirement.
`budget-pending`, `dispatch-pending`, `user-pending` and `user-retire-pending`
still require real IRR latching and old-owner kernel drains, never synthetic ticks
or a drain charged to the next user run. Late-negative `dispatch-cross-reply` and
`dispatch-stale` must reach their exact envelope failures; they do not acquire
post-return hit assertions that their denied paths never reach. The completed
peer service before `user-stale-grant` still requires its compiled hit.

The pre-reset independent static review conditionally supported the fixed clock
for the exact then-retained retirement image and its post-arm tail. This historical
account does not assert recovery of raw diagnostic logs or revalidation of the
image/tool evidence in the reconstructed environment. Its explanatory estimate of
80 is **not an acceptance bound**, exact count or family-wide result. The other
finite, context and macro-profile tails need their own exact generated-image
review, including the 100,000-iteration budget fixture, million-iteration dispatch
fixture, service/client countdowns, ordinary/resume tails and forced-pending loops.
Shared source does not prove identical generated bytes or timing margins. Actual
new image identities must be checked, not assumed from a launcher-only change.

## Source controls and remaining acceptance

The following focused commands are prepared, **not run by this source-authoring
checkpoint**:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tests/kernel-emulator-clock.py
PYTHONDONTWRITEBYTECODE=1 python3 -O tests/kernel-emulator-clock.py
./scripts/kernel-uefi-smoke.sh --clock-plan user-retire-pending
./scripts/kernel-uefi-smoke.sh --clock-plan
```

`--clock-plan [mode]` prints the validated command receipt with no firmware
availability check, build, guest execution or receipt-file write. The native-free
tests exercise all 177 mode identities, every one of the 140 UEFI build-mode
command paths with/without QEMU data, all five exclusions, duplicate/unknown/empty
selections and hostile declaration/argv pairs. Byte pins preserve the separate
BIOS/BAR/IVRS/capacity launchers and original three timer validators. They cannot
establish runtime preemption or replace actual firmware boots.

Before claiming qualification: independently review this source/clock/argv
contract and combined accepted-tooling reconciliation; rebuild the source/control
manifest and resource admission; run freshly authorized native/ABI/linked-image
and distinct-path reviews; then admit a complete fresh 177-mode emulator run,
three capacity probes and two actual normal restoration boots. All prior caps,
owned-process cleanup, failed-build retention and evidence ancestry requirements
remain. The pinned external launcher adapter must be rebuilt and independently
inverse-transform/guard-placement reviewed; its `cpus=1` insertion anchor is
preserved. Both fixed-clock output guards and both original-clock IPC output
guards must remain effective. Old source digests/mode-order-only digests cannot
authorize the changed argv. No partial-prefix reuse, larger budget, selective
retry, performance equivalence, physical hardware or full-177 passing claim follows.
