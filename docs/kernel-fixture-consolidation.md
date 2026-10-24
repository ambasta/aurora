# Kernel fixture consolidation

Fault and hostile cases are boot-selected rows in
[`kernel/uefi/runtime-fixtures.inc`](../kernel/uefi/runtime-fixtures.inc), not
separate kernel builds. Each row names a guest mode, the one test image that runs
it and its selector value. `kernel_profiles.FIXTURE_MODES` and every oracle derive
their mode lists from that table; tests check that each family's selectors stay
one contiguous range, not their numeric values.

The source catalog went from 233 canonical images (196 UEFI, 37 BIOS) to 125
(105 UEFI, 20 BIOS) in PR #244, and to 81 (61 UEFI, 20 BIOS) here. Every fault
mode keeps its own guest run and exact oracle. A source image count is not a
measured build or execution saving; the PR records those.

## Selection

- Serial selector: a fixture image prints `AURORA_FIXTURE_READY`, waits for one
  byte and accepts only its family's interval; anything else fails closed. Each
  family reads it at a fixed phase (after ACPI closure for PCI/IVRS/BAR, before
  timer initialization for the protected-runtime families, at the top of
  `run_console` for the console), and each oracle checks that phase.
- Capture release byte: the framebuffer capture gate already waited for one
  reviewed byte; `G` releases the normal frame and the three framebuffer fault
  selectors release their cases.
- Launch probe word: hostile user code lives in one fixture client per family.
  The trusted launcher passes the selected probe in a launch argument (the
  runtime client's first argument, or one extra word loaded into `%rax` for the
  IPC wrapper, which bounds it and still checks every other unused register is
  zero). Probe addresses are generator-admitted metadata (`probes`), checked
  for exact opcodes, image bounds and site aliasing, and accepted by the oracle
  only on the one image that carries them.

Ordinary baselines (`normal`, `runtime`, `ipc`, `budget`, `dispatch`, ...)
contain no selector or injection state.

## Moved checks

| Case | Was | Same property now enforced by |
| --- | --- | --- |
| IPC owner/version/phase/transaction/site/unknown | hostile client images | `ipc-fixture` alters the trapped exit before the unchanged kernel checks (site moves the trapped RIP off the return site; unknown resumes the client at the wrapper's `bad_entry` UD2, an unregistered address); `tests/kernel-uefi-ipc-smoke.py` |
| snapshot owner, reply byte/reserved; program ordinal/owner/transaction/unknown | hostile client/service images | same exit hook in `snapshot-fixture`/`program-fixture` (program unknown also faults at `bad_entry`); their transcript oracles |
| runtime code/stack/kernel/window/write/nx/return/unknown/syscall/sysenter | one client image per probe | probe set in `runtime-fixture`'s clean client; `tests/kernel-uefi-runtime-smoke.py` |
| runtime terminal input/output | two kernel builds | `runtime-fixture` mutation, as the BIOS fault fixture already did |
| budget mmio/softint/fpu/context | service image per probe | probe word in `budget-fixture`; `tests/kernel-uefi-budget-smoke.py` |
| budget no-APIC | kernel build plus a link-time check that no launch or timer symbol survived | the CPUID bit is cleared when selected. The link-time property cannot hold in a shared image (it only held because the rejection was constant folded); what remains is the weaker run-time form: the guest oracle requires the rejection to be the only record after firmware discovery, before any timer, IPC or domain record |
| dispatch peer-code; user context/unknown | client images | probe word in `dispatch-fixture`/`user-fixture`; dispatch and user-phase oracles |
| console stale/reentry/timeout/report | four kernel builds | `console-fixture`; `tests/kernel-console-service-qualification.py` |
| framebuffer record/permissions/stale | three kernel builds | capture release byte; `scripts/framebuffer_capture_oracle.py` |
| IVRS default/read | two kernel builds | `ivrs-fixture` selects the architectural or explicit cold profile (never a fallback); IVRS serial/trace/provenance oracles, which now require both linked fault sites in every IVRS image |
| BAR read/inherited/write/revoked/alias | four kernel builds | `bar-fixture`; BAR serial/trace/provenance oracles, including the stock-firmware control |

Before this change `full` built only eleven images; the rest were built only by
the guest smoke that selected them. `native-kernel-profile-images` now makes
`full` build every canonical profile and check its boot artifacts.

## Copied-input assertions moved to hosted tests (PR #244)

- PCI reserved: `kernel-pci.cpp` nonzero reserved-field loop. PCI overlap:
  independent bus and physical overlap rejection. PCI range: zero base remains
  structurally valid but the existing Q35 aperture-authority loop rejects it.
- ACPI bad-entry: `kernel-acpi.cpp` zero record-length rejection. Changed-header:
  the same checksum-repaired byte 10 mutation fails `same_header`. Duplicate:
  duplicate APIC ID and UID are independently rejected.
- IVRS pair: `kernel-uefi-ivrs.cpp` companion identity mismatch rejection. Alias:
  unsupported SELECT type 0x42. Reserved: unsupported IVMD block type 0x20 before
  its range can carry authority. Capability: copied capability byte 4 bit 1 is
  rejected. Range: type 7/four pages/WB at the aperture is rejected. Scope:
  agreeing requester 16→17 substitutions parse but cannot match the actual PCI
  inventory; this last positive-parse/negative-coverage assertion is retained.
- IPC request/cancel input, dispatch cursor/mask/output, user disposal
  input/output and budget zero/counts/wide/output: the native producer and
  production-decoder tests (`native-policy-ipc-transition`, `-round-robin`,
  `-client-disposal` and `-budget`, golden vector families) and their adapters'
  preserve-on-denial loops.

Historical synthetic transcript cases remain rejection controls, not boot
profiles; the clock catalog and launch lists reject the retired modes.

## Still separate

- Baselines and their fixture siblings (`ipc`/`ipc-fixture`, ...), and distinct
  compositions: one-page/multipage, owned-text/call, resume, console-region,
  plain/pin/table supervisors, BAR state/capture/NVMe preparation. Merging them
  needs either a selectable baseline case in each fixture or a payload bank in
  the generator/loader; neither is implemented.
- Loader-stage faults: `stale`, `stale-exhausted`, `acpi-duplicate-root` and
  `bad-table` inject before ExitBootServices, when OVMF's serial terminal driver
  owns and buffers the UART, so the serial selector cannot reach them.
  `bad-handoff`, `bad-map`, `wp` and `nx` run after exit but are split between
  the loader and the payload.
- `iommu-event-*`: their guests need the patched QEMU AMD-Vi model in
  `tools/qemu-amdvi`, which is not built here, so they were not folded.
- Capture/probe conformance images (`graphical-console-capture`,
  `framebuffer-probe`, `bar-capture`) belong to the production-image step.

The 30-second generic, 60-second IVRS/BAR and 180-second console deadlines are
unchanged. Grouping does not widen user-image, stack or page admission.
