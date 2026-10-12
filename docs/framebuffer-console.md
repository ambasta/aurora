# Bounded framebuffer console

Aurora renders an output-only status page and a separate serial-input graphical
console after ExitBootServices. Both use sealed DisplaySession authority through
trusted C++/assembly adapters. These are experimental QEMU profiles, with no GPU
driver, keyboard, desktop, physical Framework display, DMA or IOMMU qualification.

| Route | What it establishes | What remains separate |
|---|---|---|
| `make capture-framebuffer` | Fresh output-only image admission and one PNG/physical capture | Negative guests, restoration boot and independent qualification |
| `make smoke-graphical-console` | Fresh production/capture image checks, twenty guest cases and a normal boot | Final-source GCC 16 `full` and independent review |
| Image admission v6 | Current build identity, image/private-ABI/stack/state structure | Selector, authority, pixel and diagnostic behavior |

This document describes current behavior and gates, not a completed run. Exact
commands, hashes, failures and past results belong in retained evidence and
Git/PR history. Earlier source or receipt schemas cannot qualify a changed image.

## Developer preview

Run `make capture-framebuffer` to build and admit the current output-only profile,
then capture one bounded guest. It prints
`build/framebuffer-preview/run-*/framebuffer.png`; the directory also retains raw
PPM, physical before/after bytes and logs. No external manifest, review token or
Python image package is needed. It uses the exact 800×600 q35/TCG/std-VGA fixture
and pixel oracle, with a 90-second guest limit and bounded process cleanup.
Other geometries fail closed. Use the
[local-development prerequisites and overrides](local-development.md), including
`QEMU`, `QEMU_DATA`, `OVMF`, `OVMF_CODE`/`OVMF_VARS`, `OVMF_DIR`, `CXX` and `UEFI_LD`.
Missing prerequisites are `BLOCKED`; build, admission and guest defects are failures.
The framebuffer image stays in its isolated native profile directory; normal
images coexist. Do not mutate an image profile while it is in use.

The result says `qualified: false`. Ordinary preview runs one positive guest.
For all four admitted native profiles, run the same entrypoint with
`scripts/kernel-framebuffer-preview.sh --full-smoke`. It checks the success scene
and all three no-write cases with the existing independent pixel/serial oracles,
then invokes the normal UEFI smoke entrypoint for an actual restoration boot,
even after a guest failure. An unreaped guest blocks restoration. Each attempt
retains its captures, admissions, normal boot log and summary in a fresh directory.
No external manifest, tool pins or approval-role receipts are required; final-source
GCC 16 full testing and independent review remain separate merge gates.

## Current-source graphical smoke

`make smoke-graphical-console` builds/checks normal UEFI, production graphical and
capture graphical images sequentially, executes twenty cases, then actually
boots retained normal UEFI. It needs no external approval receipts or historical
compiler/address allowlist. Its version-6 image receipt is structure-only.

For build-only inspection and retained review inputs:

```sh
AURORA_GRAPHICAL_KEEP_RUNS=all scripts/kernel-graphical-smoke.sh --build-only
python3 -B scripts/kernel_graphical_smoke.py --images DIR/images \
    --evidence DIR/guests QEMU OVMF CODE VARS DATA
```

Use the printed run directory for `DIR`, an OVMF combined path or CODE/VARS pair,
and empty strings for unused inputs. The shell uses the shared firmware selector
and standard overrides. Build-only stages the required isolated profile artifacts
and performs no guest qualification or shared-image restoration rebuild.

Coverage includes production commands/edit/exit; capture BS/DEL/CRLF,
rejection/recovery and an unconsumed sentinel; exact capacity 64, overflow 65,
event 80 and native idle 4096; fixture G; note readback, shorter/empty replacement,
malformed/control-byte preservation and maximum 53-byte content; invalid selector,
all C/D/c/d no-effect denials and F/I pixel failures. The 96-copy guard is hosted
only. Production synchronizes on observed viewport boundaries; capture sends only
the selector before PRE_SAMPLE 0, then synchronizes bytes on completed samples.
Idle receives no input or pause between release and its terminal marker.

Each physical/PPM pair checks scanout, modeled viewport, every outside byte and
the 1,024-byte tail against its real baseline. Selected editing/control/capacity
milestones are sampled, not continuously observed. F/I overlays exactly 0/55
successful stores and checks 1/56 attempts, without hosted A5-fill bytes.
Production starts with an already-painted baseline, so it cannot establish
outside-byte preservation before the initial paint. Production exit 33 differs
from capture QMP termination 0.

Guests use original-clock q35/TCG, one CPU and disposable snapshot media, without
network or physical-device access. Each graphical guest has a 90-second wall
limit; restoration has 30 seconds. Production probes at most 80 small 56,032-byte
states per chunk, taking full pairs only at matches. Serial is limited to 1 MiB,
cumulative QMP and each child output file to 4 MiB. First failure stops remaining
cases and retains raw pairs/input/serial/QMP/stderr/summary; owned QEMU is reaped
and retained normal UEFI boots in `finally`.

### Restoration and retention

Image products are isolated by profile. A separately staged normal image is
actually booted after graphical cases; changing the selected profile needs no
shared normal-image rebuild. A failure retains its original status and diagnostics;
normal-boot failure makes an otherwise successful qualification fail. Staging and
retention errors are reported, without substituting image bytes for a guest boot.

After both guest execution and the normal restoration boot succeed, managed runs discard
only known physical/PPM dumps and viewport probes from that run. Summaries,
serial/QMP/stderr, build logs, staged images and unknown files remain. Build,
guest/restoration failure, interruption or explicit keep retains raw captures.
Known capture files are checked before deletion. Cleanup errors warn without
changing completed test results; an interruption preserves remaining dumps but
cannot recover removed captures. Keep review windows before starting cleanup.
No screen-hash receipt replaces discarded pixels; logs record actual comparisons.
Standalone outputs and historical windows are never adopted for this cleanup.

Graphical and Event smoke use one shared output-retention helper. Default retention
keeps the newest two successful managed windows and preserves all failed windows.
`AURORA_GRAPHICAL_KEEP_RUNS=N` accepts 1..999 for the successful-run limit; `all` skips pruning
and pins the new window. A `.keep` pins one window. Successful runs are ordered by
the modification time of their status marker; existing successful markers use the
same policy, without a schema migration. Unmarked, malformed, active and failed
windows remain outside the count bound. Pruning happens only after the run finishes.
Reusing staged images does not create a pin or change their owner's status marker.
Finish image readers before another run completes, or explicitly add `.keep` to
the image directory's run before using it concurrently. See
[explicit local cleanup](local-development.md#reclaiming-old-local-output-explicitly).

## Rendering and authority

Aurora owns the font, rasterization, colors, clipping, layout and human-facing
content. The trusted host boundary authenticates and bounds-checks, packs pixels
and performs ordered volatile stores. No raw pointer, mutable framebuffer span
or `OwnedBytes` video-memory surrogate reaches source.

`graphics.font5x7` provides A–Z, 0–9, space, colon, hyphen and fallback glyphs as
seven five-bit groups with documented packed-bit orientation. The graphical
consumer adds lowercase/punctuation and unit-scale drawing; the status page uses
3x/2x scaling. Hosted tests compare all 256 base-font byte mappings to independent
visual rows and both consumers to pixel oracles.

### Firmware handoff and mapping

Output-only handoff v5 retains the 128-byte header and its record at arena offset
`0xe0000`, supervisor read-only/NX. It rejects combination with ACPI, runtime, BAR
and console profiles; combined input/display uses v6 below. The 64-byte version-1
graphics record holds magic/version/length, physical base/resource size,
width/height/pitch/format, mode/count and zero reserved bytes, with no firmware pointer.

Before final memory-map/exit, bounded GOP discovery frees every successful query
buffer and prefers 800×600, otherwise the first supported mode. Limits are
1024×768, pitch 1024 pixels, 64 queried modes and 3 MiB/768 mapped pages. Only the
two UEFI 32-bit RGB/BGR formats are accepted, with canonical zero reserved bytes
on writes. Page-aligned base and rounded mapped pages must fit the resource;
bitmask and BLT-only modes reject. See the
[UEFI GOP definition](https://uefi.org/specs/UEFI/2.10/12_Protocols_Console_Support.html#graphics-output-protocol).
Firmware SetMode may clear the display before the controlled capture boundary.

Ordinary admission requires complete reserved/MMIO final-map coverage. It denies
RAM, runtime/ACPI overlap, unsupported attributes, the owned arena, LAPIC, IOAPIC
and q35 ECAM. Physical width and PAT index 3 UC are checked without changing
PAT/MTRRs. Every exit retry rechecks the final map.

The explicit q35/OVMF/std-VGA fixture has a separate admission rule; missing
descriptors never select it automatically. `FramebufferRecord::parse` gives a
description, not resource authority. The pre-exit loader can mint the token;
payload restoration first establishes the current root, immutable owned record
and complete tree. The exact tuple is base `0x80000000`, 1,921,024 bytes/469 pages,
800×600, pitch 800, BGR format 1, mode 3 of 30 and physical width 40. Every field
drift rejects. External qualification separately pins q35/TCG, qemu64, one CPU,
128 MiB, std VGA, QEMU, OVMF and tool data; guest metadata cannot prove host identities.

The mapping starts at `0xffffa00000001000` with absent end guards. Its maximum
extent needs four extra intermediate pages within the 16-page pool/1 MiB arena.
Leaves must match physical pages and supervisor RW/NX/UC flags. Whole-tree checks
reject extra leaves, aliases, shared/cyclic paths, changed permissions and missing
pages. No user mapping or relaxed strict-verifier rule is introduced.

### Output-only capture

The output-only image gate retains the shared fail-closed CFG/object decoder.
It permits only checked immediate-push encodings `6a00`/`6a28`; memory pushes and
wide signed stack normalizations reject. Legacy lookup/walker emission retains
unambiguous object identity, a four-level root and decreasing-level/restore checks.
The mixed-stack plus fault cap remains 15,360 bytes within the 16 KiB stack.

Hosted geometry/packing, coverage splits/holes, forbidden intersections,
PAT/width, mocked GOP/freeing and tree/guard/alias controls are bootstrap models.
Generated-Aurora pixel tests cover native BGR, padded RGB, clipped odd surfaces and
maximum geometry, with independent glyph/byte oracles and guard/padding/tail checks.
Hosted cross-kind, stale-generation, reentry, lifetime and mapping denials remain
separate from guest captures.

The prebuilt probe runner requires pinned QEMU/firmware/EFI, original clock and
ordered firmware-exit/private-paging markers; it neither builds nor approves an
image. The capture-only pre-store UART gate accepts exactly `0x47` within ten
million iterations after private paging and grants Aurora no input capability.
The host pauses QEMU, samples all 469 pages, releases the gate and samples the
completed/fail-stopped image. Copied-record, NX-permission and stale-generation
injections occur after the baseline. Record corruption never makes the owned
record writable or disables CR0.WP. The generic boot oracle does not qualify
this mode; positive/three denied captures and a normal boot are separate gates.

## Bounded serial-input graphical session

`examples/kernel-graphical-console.au` combines distinct ConsoleSession and
DisplaySession borrows in one synchronous invocation. It reuses Aurora Line64
and all printable ASCII, with two rows of 68 cells, underline cursor and dirty
redraw. The prompt holds 64 bytes, BS/DEL and CR/LF/CRLF; damaged/invalid/overflow
lines reject until submission. The second row keeps only the latest response.
The [shared note/file grammar](native-console-service.md#session-local-ram-note)
applies, with invocation-local storage and copied FileReply presentation.

The viewport is 408×18 at (32,128), requiring at least 440×146. Outside pixels
and padding stay untouched. At most 80 events and 96 copied samples permit 82
changed paint passes/992,938 stores under the million-store cap. Source exhaustion
renders a final response; native 4096-total-wake exhaustion fail-stops without
inventing input. Clean absent UART polls do not consume samples. The 96-sample
guard is exercised through hosted damaged observations. Closed completion values
are checked/mapped when both original sessions close; pixel failure never retries
or rolls back. Neither source capability contains the other.

Maximum note write/read/exit with LF costs 79 events; edits/CRLF may exhaust the
budget. Two-file todo/ideas plus exit fits 75. An eight-byte name and 49-byte content
fill one 64-byte command, but write/read/exit costs 83; clean-exit maximum-name and
maximum-content cases are separate, and the combined case uses bounded completion.

Handoff v6 independently preflights both grants, paired LAPIC/framebuffer mappings
and observational timer/interrupt/UART quiet checks. Earlier handoffs are unchanged.
The arena/page pool/stack remain 1 MiB/16 pages/16 KiB. Exact images must fit normal
plus fault and wait plus IRQ/fault within 15,360 bytes, and IRQ plus fault within
4,096, including the 176-byte IRQ frame and alignment.

### Build admission and trust limits

Use `UEFI_MODE=graphical-console ./scripts/kernel-uefi-build.sh`; the separate
`graphical-console-capture` mode is for controlled capture. Each mode requires
its own combined linked-stack/image begin/end/emit admission; starting a build
invalidates prior combined receipts. Source/tool/flags/output identity binds
begin/end/admission. Mixed or stale inputs reject; historical token/object/compiler
allowlists and earlier receipt schemas cannot satisfy current checked/reviewed gates.

Version-6 receipts (`aurora-graphical-console-admission-v6`) check PE/ELF/PIC,
exact source/symbol/object/link associations, compiler-reported C++ frame/call
bounds, generated-Aurora control-flow/stack, private ABI and production capture
absence. Capture requires fourteen typed, sized, aligned, contained and disjoint
BSS fields: nine state/counters, Console/Display grants and generations, and the
entry active flag. Addresses and section indexes are measured. The result is
`structure-only`, with `behavior_qualification: pending-hosted-and-guest-gates`.

The C++ bound trusts GCC .su/.ci metadata, conservatively retaining complete
frames at calls and tail transfers with exact compiler-versus-linked direct-edge
agreement. Checked adjacent pushfq/register-pop pairs add eight bytes per
containing frame; arbitrary inline assembly is outside that metadata guarantee.
Unresolved targets, unsupported transfers, unbounded/unapproved dynamic frames
and graph cycles reject. Both page-table walkers use four fixed local slots.
Generated-Aurora, private ABI, assembly and IRQ/fault checks and budgets remain.

Graphical builds require separate non-inlined/non-cloned Console and Display
validators with matching frame/source/symbol ownership. C++ instruction-by-
instruction stack/CFG replay and the special memory-push hook are retired.
Traversal termination, snapshot ordering, local-storage independence, bitmap
bounds, helper memory effects and arbitrary C++ correctness trust reviewed source
and compilation, with independent reference parity, hostile hosted and guest
checks. Receipt versions 1–5 cannot qualify this boundary. Fresh image, behavioral,
restoration and final-source GCC 16 full/review gates remain necessary.

### Capture selectors and behavioral gates

Capture selects one scenario before grants, consumer entry or stores:

| Byte | Release code | Fixed action |
|---|---|---|
| G | 1 | Both live grants |
| C | 2 | Live Display grant in local Console field |
| D | 3 | Live Console grant in local Display field |
| c | 4 | Close/reopen Console, then its saved generation |
| d | 5 | Close/reopen Display, then its saved generation |
| F | 6 | Fail first pixel attempt before a store |
| I | 7 | Fail after exactly 55 successful stores |

Other bytes reject with `capture selector`, without release. Valid selectors emit
`AURORA_GRAPHICAL_CAPTURE_RELEASED: selector=N`; zero never releases. The gate has
a ten-million-iteration bound, rejects UART damage and never selects again.
Capture preserves terminal/failed scanout for physical sampling and normal restoration.

Failure records append `completed=N wakes=W pixel_attempts=P`; completion records
append `entries=E samples=R output_attempts=O completed=N pixel_attempts=P` after
their completion/wakes/stores fields. Production diagnostic format is unchanged.
C/D/c/d require zero counters and an unchanged framebuffer. F/I complete with code
2, one entry, zero samples/output attempts, 1/56 attempts and 0/55 stores before
PRE_SAMPLE. I preserves a 6×9 background cell and first glyph pixel. These inject
transport failure at valid coordinates, not geometry or synchronous faults.

Select the hosted/paging/admission checks from the configured Meson build:

```sh
meson test -C BUILD graphical-console-native graphical-paging \
    graphical-admission-controls graphical-smoke-controls
```

Meson `slow`/`full` includes the hosted runner; `dev`/`full` includes paging,
admission and compiler-free smoke controls (`make test-graphical-controls`).
For a pinned hosted run:

```sh
python3 -B -O tests/kernel-graphical-console.py --run /path/to/aurorac \
    --compiler-sha256 REVIEWED_SHA256
```

A controlled `--developer-build-receipt` is also supported. Each run recompiles
the observer and hashes its recursive quoted-header closure, including capture
policy. The inventory requires 145 generated-consumer cases: 108 transcript/
geometry, two session resets, 13 output failures and 22 entry denials.

Qualification assigns each claim to its actual check:

- Hosted real policy checks all 256 selectors, independent numeric codes/names and
  fixed 0/55 failure ordinals, including nearby/wide counts. Real sessions/entry
  check identity, both preflights, wrong/duplicate kinds, stale generations,
  geometry, lifetime and reentry.
- Current image/stack admission checks the structure above, including compiled
  imports, distinct frame ownership and absence of capture state in production.
- Actual production/capture guests check release/sample ordering, diagnostics,
  counters, denials, failed-store prefixes, unexpected writes and normal restoration.
- Source review retains responsibility for privileged UART predicates, selector
  bounds, counter increments and pre-store ordering. Hosted tests do not execute
  privileged I/O; sampled guest pixels cannot establish every intermediate write.

Registration or structural admission alone establishes no pass. Fresh source,
hosted, image, affected guest/restoration and
[final GCC 16 full/review gates](../AGENTS.md#workflow) remain required. Partial/null
pairs and deterministic synchronous faults are separate from these seven selectors.
