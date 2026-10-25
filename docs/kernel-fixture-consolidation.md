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
to 62 (43 UEFI, 19 BIOS) by folding test baselines into their fixtures, and to
57 (38 UEFI, 19 BIOS) by folding the four IOMMU Event cases into one image and
dropping the framebuffer probe and Event observation images, which nothing booted,
then to 41 (38 UEFI, 3 BIOS) by folding every BIOS test image into `bios-fixture`, then
to 37 (34 UEFI, 3 BIOS) by folding the span, multipage, pin and table images into
`runtime-fixture`, and to 30 (27 UEFI, 3 BIOS) by folding the early, ACPI, PCI,
IVRS, BAR, BAR-state, BAR-capture and NVMe-preparation images into
`platform-fixture`, and to 26 (23 UEFI, 3 BIOS) by folding the framebuffer and
graphical-console images into `display-fixture` and the console and owned-bytes
images into `device-fixture`, and to 22 (19 UEFI, 3 BIOS) by folding the IPC,
budget, dispatcher, user-phase and user-resume images into `service-fixture`. Every
fault mode keeps its own guest run and exact oracle. A source image count is not a
measured build or execution saving; the PR records those.

## Selection

- Serial selector: a fixture image prints `AURORA_FIXTURE_READY`, waits for one
  byte and accepts only its family's interval; anything else fails closed. Each
  family reads it at a fixed phase (before timer initialization for the
  protected-runtime families, at the top of `run_console` for the console), and
  each oracle checks that phase.
- fw_cfg file (`kernel/uefi/fw-cfg-fixture.hpp`): the loader-stage faults inject before ExitBootServices, when
  OVMF's terminal driver owns and buffers the UART, so `platform-fixture` reads a
  decimal selector from the QEMU fw_cfg file `opt/aurora/fixture` (I/O ports
  0x510/0x511) at loader entry and echoes it as `AURORA_FIXTURE_SELECTED` on the
  line after loader entry, before any other record. The harnesses add
  `-fw_cfg name=opt/aurora/fixture,string=N` from the table
  (`kernel_profiles.fw_cfg_fixture`, machine variants included). The loader copies
  the value into one extra handoff word (offset 128, present only in these images)
  that the payload admits only within the image's interval, so every payload case
  shares the image (see below). `display-fixture` and `device-fixture` use the
  same loader row (`loader-fixture.hpp`), because their subsystems differ from the
  loader onward and their interactive console sessions cannot take a serial byte. The
  `iommu-event` image reads the same file at Event entry, because its harness
  writes serial output to a file and cannot send a selector byte.
- Capture bytes: the framebuffer capture gate waits for `G`, which only releases
  the case its row selected. The graphical capture gate's byte still selects one
  capture scenario of the `graphical-console-capture` row.
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
  `user-phases`, `user-resume`, `snapshot`, `runtime`, `runtime-span`, `runtime-multipage`, `runtime-owned-text`,
  `runtime-console-region`, `user-call`, `framebuffer`, `graphical-console`,
  `console`, `owned-bytes` and BIOS `schedule`. Machine variants
  (`acpi-two`, `pci-devices`, `pci-bridge`, `budget-smp`, `schedule-smp`,
  `schedule-no-apic`) inherit their baseline's image and selector. Oracles
  separate a family's fault cases (`kernel_profiles.fixture_cases`) from every
  selected mode (`selected_modes`, optionally one row family): a baseline run
  requires the READY receipt at its phase (the loader echo on `platform-fixture`)
  and the fixture image's probe metadata, while other oracles reusing
  a baseline name for a prefix check keep its selector-free meaning.

The smoke images (`normal` UEFI and BIOS) and the production image contain no
selector or injection state.

## Production image

`uefi/production` is the one production UEFI configuration: ACPI, PCI, the
protected runtime, IPC, service and user budgets, the protected program console
(`program-console` is its alias) and the graphical terminal that renders it.
`production-profile.hpp` makes any fixture, test, capture or probe flag a compile
error in its loader and payload, `graphical-profile.hpp` admits the graphical
terminal only with that complete runtime stack and no test flag, the image policy
forbids fixture or capture state in its linked payload, and
`guest-uefi-production` (`make smoke-production`) exercises both consoles (see
below). Capture, probe and BAR/IVRS conformance images remain test images.

Composition. The image links two closed Aurora objects with separate bridges and
import policies: the program console (`examples/kernel-program-console.au`,
Console imports only) and the terminal painter
(`examples/kernel-graphical-terminal.au`, whose only import is the Display pixel
service; `imports:terminal` in the image policy). The protected program console
is the only owner of COM1 input and of the LAPIC timer and stays the command
surface: there is one input consumer and one timer user, so nothing is routed
between consoles. Every byte its sealed Console session delivers is also copied
into an 80x24 cell grid (`kernel/terminal-grid.hpp`, data only); native
diagnostics are not. Changed cells are painted through one DisplaySession loan
before the console's poll wait and after each Console turn releases its grant,
never during a protected run, with the paired LAPIC/framebuffer tree verified at
each paint and the leaf rechecked per store (`kernel/uefi/graphical-terminal.inc`).
The display fixture's standalone graphical console keeps its own line editor and capture
cases; both consoles draw cells through the shared `graphics.text_cells` library.

Handoff. Version 7 is the production layout: word 112 is the copied RSDP, word
120 the runtime metadata (as in v3) and word 128 the framebuffer record, in a
136-byte header. Only the production header admits v7 and it admits nothing
else; every other image keeps its 128-byte header, rejects v7 and validates
v1-v6 unchanged (`native-kernel-uefi-handoff[-terminal]`). The platform fixture's
word 128 exists only in its own image, which can never compose the terminal.

Framebuffer admission. The loader and the payload's restoration use the firmware
rule (`FramebufferAdmission::authorize_firmware`): the source-bound GOP resource
with its own base, size, geometry and pixel format, rechecked against every
ExitBootServices retry's final map and again from the immutable record. It keeps
every check of the std-VGA fixture rule except the emulator identity tuple: no
RAM, runtime, ACPI or persistent overlap, no owned arena, LAPIC, IOAPIC or q35
ECAM, physical width, PAT index 3 UC, supervisor RW/NX/UC leaves with absent
guards and whole-tree verification. Firmware omits PCI apertures from the memory
map, so the aperture must be either wholly absent from or wholly described by
reserved/MMIO descriptors; a partial description denies. A missing GOP or a
framebuffer in firmware RAM (QEMU ramfb) fails closed in the loader. The std-VGA
fixture rule remains for the display fixture's framebuffer and graphical-console rows.
This is exercised only under QEMU/OVMF; it is not physical-hardware support.

Guest. `scripts/kernel_production_smoke.py` runs the program-console PTY oracle
on the image, then one q35/OVMF/std-VGA guest with QMP: the commands in
`tests/kernel-production-console.json` over serial, whose Console output must
equal that reviewed transcript (only whole native diagnostic lines may
interleave), and the framebuffer viewport, which must equal the real host painter's
rendering of the transcript (`tests/graphical-terminal-host --viewport`) in
physical memory and in the screendump, before a clean `exit`. It then boots the
no-display and ramfb machines and requires the loader refusals. The harness, not
the kernel, pins the std-VGA environment. Hosted cases: `graphical-terminal-native`
(grid, wrap, scroll, erase, schedule-independent frames, painter geometry and
cell bounds, a foreign Console grant), `uefi-framebuffer-loader` (the firmware
rule as data) and the compile-fail guards.

Payload reservation. The production payload had reached the former 128 KiB
reservation exactly, so it is now 152 KiB (`kernel_payload_limit` 0x26000): the
IDT moves to 0x48000, the guard to 0x49000 and the 16 KiB kernel stack to
0x4a000..0x4e000, with 0x4e000..0x50000 still absent above it. Oracles read these
values from `kernel/bootstrap-layout-values.inc`.

## Moved checks

| Case | Was | Same property now enforced by |
| --- | --- | --- |
| IPC owner/version/phase/transaction/site/unknown | hostile client images | `service-fixture`'s IPC rows alter the trapped exit before the unchanged kernel checks (site moves the trapped RIP off the return site; unknown resumes the client at the wrapper's `bad_entry` UD2, an unregistered address); `tests/kernel-uefi-ipc-smoke.py` |
| snapshot owner, reply byte/reserved; program ordinal/owner/transaction/unknown | hostile client/service images | same exit hook in `snapshot-fixture`/`program-fixture` (program unknown also faults at `bad_entry`); their transcript oracles |
| stale, stale-exhausted, bad-table, bad-handoff, bad-map, wp, nx, acpi-duplicate-root | eight kernel builds | `platform-fixture`; each injection sits where its build did (bad-table still maps 0x10000 before exit, so the payload's complete-tree check is unchanged). The image includes ACPI for `acpi-duplicate-root`, so bad-handoff swaps the handoff version between its RSDP-free and RSDP-bearing forms instead of writing 2; the payload's version/content check still rejects it. `tests/kernel-uefi-smoke.py`, `tests/kernel-acpi-smoke.py`, which also require the selector echo before any exit record |
| runtime code/stack/kernel/window/write/nx/return/unknown/syscall/sysenter | one client image per probe | probe set in `runtime-fixture`'s clean client; `tests/kernel-uefi-runtime-smoke.py` |
| runtime terminal input/output | two kernel builds | `runtime-fixture` mutation, as the BIOS fault fixture already did |
| budget mmio/softint/fpu/context | service image per probe | probe word in `service-fixture`'s budget service; `tests/kernel-uefi-budget-smoke.py` |
| budget no-APIC | kernel build plus a link-time check that no launch or timer symbol survived | the CPUID bit is cleared when selected. The link-time property cannot hold in a shared image (it only held because the rejection was constant folded); what remains is the weaker run-time form: the guest oracle requires the rejection to be the only record after firmware discovery, before any timer, IPC or domain record |
| dispatch peer-code; user context/unknown | client images | probe word in `service-fixture`'s dispatcher peer and user client; dispatch and user-phase oracles |
| console stale/reentry/timeout/report | four kernel builds | `device-fixture` rows; `tests/kernel-console-service-qualification.py`, which requires the loader echo immediately before the bootstrap it used to require before the serial READY |
| framebuffer record/permissions/stale | three kernel builds | `display-fixture` rows; `scripts/framebuffer_capture_oracle.py` |
| IVRS default/read | two kernel builds | `platform-fixture` selects the architectural or explicit cold profile (never a fallback); IVRS serial/trace/provenance oracles, which now require both linked fault sites in every IVRS image |
| BAR read/inherited/write/revoked/alias | four kernel builds | `platform-fixture`; BAR serial/trace/provenance oracles, including the stock-firmware control |

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

- Interactive products with fixture siblings: `program-file-call` and
  `ram-scratchpad-console` also open foreground serial sessions, where no harness
  can send a serial selector; they stay fixture-free until they take a fw_cfg row.
- Baselines whose fixture runs different user images: `user-ram-file` and
  `ram-scratchpad-console` (their fixture services carry always-on hostile
  requests) and `program-file-call` (the fixture client, and the kernel's
  operation rewrite whenever the fixture is compiled). Folding these needs a
  payload bank: the kernel compiles user-image sites (`images::*_pc`, compiled
  ranges) in as constants and the loader installs the images before exit, so
  several image sets need generated per-set records selected at boot.
- `display-fixture` and `device-fixture` cannot share one image: their union
  (graphical console, framebuffer, console service, UART policy and owned bytes:
  the two payloads less one shared 17 KiB base, about 242 KiB) exceeds the
  152 KiB payload reservation, and `device-fixture` alone is 147,472 bytes.

## BIOS program bank

`bios-fixture` carries every BIOS fault, program-set and scheduler case. Its user
programs are a bank (`kernel_profiles.BIOS_PROGRAMS`), each linked at its own page
in 0x1B0000..0x1C8000 and installed once; a row of `kernel_profiles.BIOS_SETS`
names the three bank programs that act as images 0, 1 and 2 for one selector, and
every other selector uses the ordinary clean/bounds/overflow set
(`UserPrograms::select`). Domains still map only their own image's page. The
entry-probe variants (bad return, unknown trap, foreign code/stack, APIC read,
softint, FPU) fault in image 0's entry stub before program code runs, so they are
built on the small bounds program; the image is 62,192 bytes of the 65,024-byte
BIOS transport. `kernel-smoke.sh` hands each oracle its mode's set metadata.

## Runtime image bank

`runtime-fixture` co-hosts the plain runtime cases, the span and multipage
baselines and the pin and dormant-table supervisors. Its loader installs a bank
of user images (`kernel_profiles.RUNTIME_BANK`: clean, bounds, span, multipage
clean and faulting) in five read-only arena slots (0xb0000..0xbf000), each
linked for domain image 0 or 1 and capped at its own page count; `RUNTIME_SETS`
names the slots acting as images 0 and 1 for `runtime-span` and
`runtime-multipage`, and every other row runs clean and bounds. Every image-0
entry carries the probe dispatch, which a zero launch word skips. Before any
domain exists the kernel picks the slots, the multipage rollback self-test and
the supervisor from the selector: pin rows the pin ledger, table rows the dormant
tables, other rows neither, retaining no pages. The image admits three code pages
per image for every row, as `runtime-multipage` did; the other bank images stay
one page by their link-time cap and their oracles' size bounds. Pin uncertainty
and dormant-table test access are now separated at run time, not compile time;
production and the graphical terminal still reject both flags.
`kernel-uefi-smoke.sh` hands each oracle its mode's set (`user-sets.json`). Rows
that differ only in image set or supervisor have identical domain records, so the
image echoes `AURORA_FIXTURE_SELECTED: value=N` right after READY and the runtime,
pin and table oracles require it to be their mode's selector.

## Service fixture

`service-fixture` co-hosts five compositions that were separate builds, each
selected by its row before timer admission: the untimed two-domain IPC rows,
the IPC budget rows, the three-domain dispatcher rows, the user-run rows and the
`user-resume` row (newly a baseline row; its oracle now requires the selector).
`select_service_row` picks the composition; `timed`, `dispatching`, `user_runs`
and `resuming` stand for the former `SERVICE_BUDGET`, `DISPATCH`, `USER_BUDGET`
and `USER_RESUME` choices (mailbox or dispatcher, service-only or user run
authority, LAPIC admission and mapping, the service's RFLAGS, the resume park),
and `run_protected` calls the row's flow. The image is three-domain
(`RuntimeLayoutProfile<3, 11>`): two-domain rows never create the third domain,
so their transcripts are unchanged (same roots, frames and stacks); only the
third table pool and image slot are reserved and kernel-mapped. The loader
installs an 11-slot bank of one-page user images (`kernel_profiles.SERVICE_BANK`,
packed one page apart at 0xb0000..0xbb000) and `SERVICE_SETS` names each row
family's images 0, 1 and 2; `budget-client` is `ipc-client` with the
service-timer ranges the budget oracle requires and the IPC oracle forbids. The
service timer reads each slot's compiled and context ranges
(`images::slot_ranges`). The image echoes `AURORA_FIXTURE_SELECTED` after READY,
and the IPC, budget, dispatcher and user oracles require it to be their mode's
row; `kernel-uefi-smoke.sh` hands each oracle its mode's set. The kernel metadata
now carries the budget family's forged-interrupt site for every row, so the
dispatcher and user oracles require it present on this image instead of absent.
The payload is 131,104 bytes; the stack total is 11,471 of 15,360 bytes. A guard
in `runtime.cpp` keeps these compositions out of every other image, and
production and the graphical terminal reject the flag.

## Platform fixture

`platform-fixture` co-hosts the loader handoff faults and the ACPI, PCI, BAR,
BAR-state, BAR-capture, NVMe-preparation and IVRS cases: 32 rows, with new rows
for `bar-state`, `bar-capture`, `bar-prepare` and `ivrs-missing`, which had no
selector before. Only the loader faults and the BAR capture change the loader, so
the one selector is the fw_cfg row read at loader entry, and every phase branches
on the copied handoff word (`platform-fixture.hpp`). Early and ACPI rows stop
after ACPI discovery and never require MCFG; PCI rows scan PCI; `bar-capture`,
the later BAR rows and every IVRS row capture the firmware BAR record (handoff
v4); only `bar-capture` keeps the generic resource parser, which must refuse the
EDK2 producer; only `bar-prepare` prepares NVMe pages; only `bar-state` prints
the admission refusal; only IVRS rows require the IVRS table and the q35 LAPIC.
The device phase runs in `noinline` functions after the ACPI frame has
returned, so the union of every path is 11,551 of 15,360 stack bytes
(`pci-fixture` and `bar-state` alone were 14,719 and 14,871, because their PCI
scan ran inside the ACPI frame). The payload is 76,500 bytes. The ACPI, PCI, BAR,
BAR-state and IVRS oracles require the loader echo with their row instead of a
serial READY receipt at their old phase; their behavioural assertions are
unchanged. A guard in `pci.cpp` keeps BAR capture, NVMe preparation and IVRS out
of every other image.

## Display and device fixtures

`display-fixture` co-hosts the framebuffer rows (`framebuffer` and its record,
permissions and stale faults) and the standalone graphical console
(`graphical-console`, `graphical-console-capture`); `device-fixture` co-hosts the
UEFI console, its four service faults and owned bytes. Both read the loader row
(`loader-fixture.hpp`), so the console and graphical interactive flows boot their
baseline rows. Framebuffer and owned-bytes rows skip ACPI in the loader and the
payload and hand over v5 and v1 as their images did; the other rows hand over v6
and v2. The payload runs only its row's subsystem; the graphical console decides
capture mode (capture gate, counters, no exit write) from its row, and the one
`__au_runtime_display_pixel` import reaches the framebuffer session until the
graphical console has entered. The second Aurora object of each image (the
display service, the owned-bytes graph) is compiled like the production terminal,
with local symbols, referenced reflection only and its own `imports:STEM` policy.
Payloads are 117,393 and 147,472 bytes; stack totals are 8,247 and 13,743 of
15,360 bytes. The framebuffer, graphical, console-PTY, console-service and
owned-bytes oracles require the loader echo with their row; their behavioural
assertions are unchanged. Guards in `loader.cpp`, `graphical-profile.hpp` and
`owned-bytes.cpp` keep each subsystem out of every other image, and production
rejects both images' flags.

The 30-second generic, 60-second IVRS/BAR and 180-second console deadlines are
unchanged. Grouping does not widen user-image, stack or page admission.
