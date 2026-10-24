# Kernel fixture consolidation

Fault and hostile cases are boot-selected rows in
[`kernel/uefi/runtime-fixtures.inc`](../kernel/uefi/runtime-fixtures.inc), not
separate kernel builds. Each row names a guest mode, the one test image that runs
it and its selector value. `kernel_profiles.FIXTURE_MODES` and every oracle derive
their mode lists from that table. `kernel_profiles` rejects the table at configure
time unless every value is a distinct byte and each image's rows are one run of
consecutive values (the interval `read_fixture` admits); numeric values are not pinned.

The source catalog went from 233 canonical images (196 UEFI, 37 BIOS) to 125
(105 UEFI, 20 BIOS) in PR #244, to 81 (61 UEFI, 20 BIOS) in the
per-component driver change, then to 74 (54 UEFI, 20 BIOS) with the early fixture
and to 62 (43 UEFI, 19 BIOS) by folding test baselines into their fixtures. Every
fault mode keeps its own guest run and exact oracle. A source image count is not a
measured build or execution saving; the PR records those.

## Selection

- Serial selector: a fixture image prints `AURORA_FIXTURE_READY`, waits for one
  byte and accepts only its family's interval; anything else fails closed. Each
  family reads it at a fixed phase (after ACPI closure for PCI/IVRS/BAR, before
  timer initialization for the protected-runtime families, at the top of
  `run_console` for the console), and each oracle checks that phase.
- fw_cfg file: the loader-stage faults inject before ExitBootServices, when
  OVMF's terminal driver owns and buffers the UART, so `early-fixture` reads a
  decimal selector from the QEMU fw_cfg file `opt/aurora/fixture` (I/O ports
  0x510/0x511) at loader entry and echoes it before any exit attempt. The
  harness adds `-fw_cfg name=opt/aurora/fixture,string=N` from the table
  (`kernel_profiles.fw_cfg_fixture`). The loader copies the value into one extra
  handoff word (offset 128, present only in this image) that the payload admits
  only within the family, so the payload's `wp`/`nx` cases share the image.
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

- Baseline row: where a family's ordinary image was only a test baseline, the
  first row of its interval (`*_baseline`) selects the unchanged normal flow, so
  the mode boots the fixture image: `acpi`, `pci`, `ipc`, `budget`, `dispatch`,
  `user-phases`, `snapshot`, `runtime`, `runtime-owned-text`,
  `runtime-console-region`, `user-call` and BIOS `schedule`. Machine variants
  (`acpi-two`, `pci-devices`, `pci-bridge`, `budget-smp`, `schedule-smp`,
  `schedule-no-apic`) inherit their baseline's image and selector. Oracles
  separate a family's fault cases (`kernel_profiles.fixture_cases`) from every
  selected mode (`selected_modes`): a baseline run requires the READY receipt at
  its phase and the fixture image's probe metadata, while other oracles reusing
  a baseline name for a prefix check keep its selector-free meaning.

The smoke images (`normal` UEFI and BIOS) and the production image contain no
selector or injection state.

## Production image

`uefi/production` is the one production UEFI configuration: ACPI, PCI, the
protected runtime, IPC, service and user budgets and the protected program
console (`program-console` is its alias). `production-profile.hpp` makes any
fixture, test, capture or probe flag a compile error in its loader and payload,
the image policy forbids fixture or capture state in its linked payload, and
`guest-uefi-production` (`make smoke-production`) runs the program-console PTY
oracle on it. Capture, probe and BAR/IVRS conformance images remain test images.

The graphical console is not in it. That needs kernel integration, not profile
flags: (1) an image links one Aurora supervisor module and bridge, and the
graphical and program consoles are separate root modules
(`examples/kernel-graphical-console.au`, `examples/kernel-program-console.au`);
(2) handoff word 120 is the runtime metadata in version 3 and the framebuffer
record in version 6, and `run_graphical_console` requires version 6, so a
combined handoff version and table verification are needed; (3) the graphical
console admits only QEMU's std-VGA through
`authorize_q35_ovmf_std_vga_fixture` and its bridge is unqualified, so
`graphical-profile.hpp` requires `AURORA_UEFI_GRAPHICAL_FIXTURE` and rejects the
runtime/IPC/program-console flags; (4) both consoles own COM1 input and their own
LAPIC timer setup, with no arbitration between them.

## Moved checks

| Case | Was | Same property now enforced by |
| --- | --- | --- |
| IPC owner/version/phase/transaction/site/unknown | hostile client images | `ipc-fixture` alters the trapped exit before the unchanged kernel checks (site moves the trapped RIP off the return site; unknown resumes the client at the wrapper's `bad_entry` UD2, an unregistered address); `tests/kernel-uefi-ipc-smoke.py` |
| snapshot owner, reply byte/reserved; program ordinal/owner/transaction/unknown | hostile client/service images | same exit hook in `snapshot-fixture`/`program-fixture` (program unknown also faults at `bad_entry`); their transcript oracles |
| stale, stale-exhausted, bad-table, bad-handoff, bad-map, wp, nx, acpi-duplicate-root | eight kernel builds | `early-fixture`; each injection sits where its build did (bad-table still maps 0x10000 before exit, so the payload's complete-tree check is unchanged). The image includes ACPI for `acpi-duplicate-root`, so bad-handoff swaps the handoff version between its RSDP-free and RSDP-bearing forms instead of writing 2; the payload's version/content check still rejects it. `tests/kernel-uefi-smoke.py`, `tests/kernel-acpi-smoke.py`, which also require the selector echo before any exit record |
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

- Interactive products with fixture siblings: `console`, `program-file-call`
  and `ram-scratchpad-console` also open foreground serial sessions, where no
  harness can send a selector, so they stay fixture-free.
- Baselines whose fixture runs different user images: `user-ram-file` and
  `ram-scratchpad-console` (their fixture services carry always-on hostile
  requests) and `program-file-call` (the fixture client, and the kernel's
  operation rewrite whenever the fixture is compiled). Folding these needs a
  payload bank: the kernel compiles user-image sites (`images::*_pc`, compiled
  ranges) in as constants and the loader installs the images before exit, so
  several image sets need generated per-set records selected at boot.
- Distinct compositions: one-page/multipage/span, resume, pin/table
  supervisors, BAR state/capture/NVMe preparation, owned bytes, framebuffer
  probe and graphical capture, and BIOS images that differ in user programs or
  entry probes (division, unsigned, scheduler mmio/softint/fpu, program
  bad-return/unknown-trap, domain code/stack).
- `iommu-event-*`: their guests need the patched QEMU AMD-Vi model in
  `tools/qemu-amdvi`, which is not built here, so they were not folded.

The 30-second generic, 60-second IVRS/BAR and 180-second console deadlines are
unchanged. Grouping does not widen user-image, stack or page admission.
