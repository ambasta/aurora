# Scoped UEFI emulator clock qualification

## Current integration addendum — 2026-10-06

The old 586-file `2b4da219…` source has separately accepted 177+3+2 runtime boots
and bounded static review of all 28 images; the same-reviewer reconsideration closed
the two-input-image static gate. Its interrupted predecessor remains unaccepted.
The fresh composition on main `25d76b1799c2a29d21b175b6b720c7a256e97b9e` has no
execution acceptance. Current `memory.S`, linked addresses, source/tool bindings
and native/runtime behavior require fresh qualification; old bounds do not carry
over. See the [dated results addendum](kernel-ipc-transition-integration-results.md).
The wall-clock retirement failure is still unresolved stress evidence.

The current firmware/clock join preserves the 51 fixed/126 original production
partition. A plan accepts nonexistent explicit combined or complete CODE/VARS
paths; runtime still requires readable, nonempty files. Directory/automatic plans
use real discovery and fail if unresolved, with no fixed Debian default.
Selectors must remain complete and nonconflicting; identical files are rejected.
Independent command validation reconstructs the full argv, including readonly
CODE, snapshot VARS, each image's raw/qcow2 format and comma escaping.
The current 13 clock and 15 firmware test methods are authored, **not executed**.
Fresh full 177+3+2 qualification will explicitly select the historical combined
OVMF for common UEFI modes, preserving separate BAR/IVRS fixture selection.
A separately proposed split-firmware gate covers normal, `budget-smp` and normal
restoration, including unchanged pristine VARS and strict serial/argv checks;
it is not a completed run or expansion of the full matrix.

## Historical clock status before input-review reconsideration

**The exact 182-boot runtime regression has passed independent terminal and
raw-corpus review.** All 177 production modes, three capacity probes and two
actual normal restoration boots completed on the tested 586-file `2b4da219…`
source. The 51 instruction-clock modes and 131 original-clock boots were checked
against complete admitted argv, expected statuses and strict traces. Native and
scoped sanitizer acceptance remain separate. Both supplemental input-guard
linked reviews are still platform-blocked and unaccepted, so overall IPC/kernel
acceptance remains incomplete. See [integration results](kernel-ipc-transition-integration-results.md).

The tooling base remains accepted PR27 main
`772b9c8a6291aa3cc656b409ce0263f73d45b034`, tree
`62a2728942d9c36df16bd00189260f6a94cb847e` (merged 2026-10-05 22:52:33 UTC).
The 586-file combined source manifest
`2b4da2190713a207e53e54c597e722ce1ad3cf8a51d438af6072bfae729ebabf`
has fresh full default D/P release native acceptance, not full IPC/kernel
acceptance. [Integration results](kernel-ipc-transition-integration-results.md)
bind exact reports and distinguish this later documentation-only overlay from
the executed source. This document itself authorizes no workload.

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
That executable was absent immediately after the reset and during the new static
reviews. It has since been restored: 146 historical executable/library/firmware
pins, including main executable SHA256
`d3c1a558ad220e77a4412048c8d96b44f8c2b41c7ad2a4ecfe522a4b122fe067`,
have durable exact readback. Canonical activation and one version-only probe
closed at 2026-10-06 05:02:24 UTC, exit 0, reporting QEMU 10.0.13
(`Debian 1:10.0.13+ds-0+deb13u1`), with zero guest/firmware boots. Optional
braille/USB-redirection/smartcard dependencies and modules are absent and excluded;
the runtime environment file is new, not historically byte-matched. See the
[receipt index](evidence/ipc-transition-policy/receipts.json). This establishes
identity and loader/version viability only. A later independently reviewed exact-runtime
APIC/MMIO/interrupt/IRET companion and fresh admission bound the completed
182-boot run, including combined OVMF SHA256 `14954040cc754ade0c625ac3470ea46d4c14318b5b1396de4ef77090203d76db`,
clean environment, absent default QEMU configuration and excluded optional modules.

The changed execution model remains part of the exact qualification identity.
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
80 is **not an acceptance bound**, exact count or family-wide result.
A fresh 22-driver emitted-instruction review now conditionally covers the
100,000-iteration budget fixture, million-iteration dispatch fixture, service/client
countdowns, ordinary/resume tails and forced-pending loops against exact newly
constructed image identities. The separate 26-image linked review addresses its
bounded stack, mapping, authority and output-guard scope. Both retain their stated
assumptions. The later exact-runtime premise companion and actual 51-mode family
results are separately reviewed. Raw recount found 141 armed runs, 3,652 charged
ticks, 14 kernel drains and nine context samples. These observations do not turn
conditional instruction arithmetic into a general timing or performance guarantee.

## Source controls and remaining acceptance

These four actual outer command rows completed in the separately admitted
compiler-free stage. For compactness, the retained `/usr/bin/timeout` and clean
`/usr/bin/env -i` wrappers are omitted below; their exact argv and cwd are in the
[receipt index](evidence/ipc-transition-policy/receipts.json):

```sh
/usr/bin/bash -n scripts/kernel-uefi-smoke.sh
/usr/bin/make --no-print-directory -j1 test-emulator-clock
/usr/bin/bash scripts/kernel-uefi-smoke.sh --clock-plan user-retire-pending
/usr/bin/bash scripts/kernel-uefi-smoke.sh --clock-plan
```

The one public Make row contains the ordinary and optimized Python recipes,
each with `PYTHONDONTWRITEBYTECODE=1`; they are not separate outer command rows.
Independent terminal review accepted launcher syntax, all eight methods in each
Python mode, and both complete plans. No compiler, native test, image or guest
boot ran in that stage.

`--clock-plan [mode]` prints the validated command receipt without building,
launching a guest or writing a receipt file. Under the current join only explicit
combined or complete split selections skip file-availability checks; directory
and automatic plans require successful discovery. The new focused suite methods
remain unexecuted, as stated in the addendum above.

The historical eight-method native-free suite exercised all 177 mode identities,
every one of the 140 UEFI build-mode command paths with/without QEMU data, all
five exclusions, duplicate/unknown/empty selections and hostile declaration/argv
pairs. Byte pins preserve the separate BIOS/BAR/IVRS/capacity launchers and original
three timer validators. These controls cannot establish runtime preemption or
replace actual firmware boots.

The clock-control stage used manifest
`e6c08e72e9764615043b4ef7c5a726c5a5dda12c6f1de9f8735ec0fe8b6230b7`;
the later native-tested `2b4da219…` source differs only in documentation. Complete
D/P native workflows and the separate five-row fatal ASan/UBSan supplement now
have independent scoped acceptance. The complete fresh 177+3+2 runtime run is
also independently accepted, with no prefix reuse. Its reviewed adapter, exact
source/tool/command bindings, four preboot output guards and owned-process closure
remain part of that old result. The later reconsidered two-input-image review
closed its separate static gate, as recorded in the addendum above. The fresh
current-main composition remains unqualified. All 128/3 budgets, loops and strict
validators remain unchanged;
no selective retry, larger budget, physical-hardware or performance-equivalence
claim follows. The original wall-clock failure remains unresolved stress evidence.
