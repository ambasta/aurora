# Bounded firmware framebuffer console

Output-only rendering and bounded graphical-session diagnostics have
independently accepted guest captures on exact pinned fixtures. The joined
capture-failure candidate, final GCC 16 `full` gate and merge review
remain pending; this is not a claim of whole-system readiness.
The current source join adds the reviewed GCC 14/GCC 16 portability machinery
and readable binary glyph spellings. Graphical compiler frames now bind exact
assembler symbols through `.ci` and complete `.su` source records, retaining
object/linked-byte checks and the separately proved paired alias. The raw
compiler alias name is retained through metadata joining; only the already proved
same-body pair is canonicalized afterward. The unchanged
legacy verifier's local visited-array invariant has a separately reviewed source
applicability check for the joined headers. This is source integration only:
changed-output image admission, failure-fixture guests and the GCC 16
final integrated gates remain pending. Capture admission now checks current
build provenance and bounded image/stack/state structure instead of replaying
historical compiler/object tuples or absolute capture instruction inventories.
This deliberately retires those capture machine-behavior proof claims; hosted
and actual guest behavior gates remain required. Historical receipts retain
only their original source/image scope and confer no new acceptance.
Firmware `SetMode` can clear its display before the controlled capture boundary.
No GPU driver, desktop, physical Framework display support, DMA or IOMMU claim
follows from this work.

## Developer preview

Run `make capture-framebuffer` to build the current framebuffer profile through
its normal image and mixed-stack checks, then capture one bounded QEMU guest.
No external manifest, machine-specific review receipt or Python image package is
needed. The command prints a fresh `build/framebuffer-preview/run-*/framebuffer.png`
path; the same directory keeps the raw PPM, physical before/after bytes and logs.
It uses the existing exact 800×600 q35/TCG/std-VGA fixture and pixel oracle, with a
90-second guest limit and bounded process cleanup. Other firmware geometries
fail closed. `QEMU`, `QEMU_DATA`, `OVMF`, `OVMF_CODE`/`OVMF_VARS`, `OVMF_DIR`, `CXX`
and `UEFI_LD` work as on the [other developer commands](local-development.md).
Missing prerequisites report `BLOCKED`; build, admission and guest failures remain
failures. The successful framebuffer image remains in `build/uefi`; normal boot
commands rebuild their own profile.

This is a developer preview, not independently qualified evidence. Its record
says `qualified: false`; it runs neither the three negative guests nor a normal
restoration boot. The stricter prebuilt qualification path remains
`scripts/kernel-framebuffer-capture.py` (see `--help`): it still requires the pinned
manifest, four independent approval roles, all four cases and an actual normal
restoration boot. A preview never creates those approvals.

## Current-source graphical smoke

`make smoke-graphical-console` builds and checks normal UEFI, production graphical
and capture graphical images sequentially, then runs eighteen fresh graphical
cases and one actual normal restoration. It reuses the existing v3 admission;
that receipt stays structure-only and never grants behavioral qualification.
No external approval receipts or historical compiler/address allowlists are needed
for this developer command. Independent review and final GCC 16 `full` remain
separate merge gates. This command creates new observations, not recovered evidence.

For review before execution, use `scripts/kernel-graphical-smoke.sh --build-only`.
It prints a fresh directory containing ordinary image copies and build logs,
then rebuilds normal UEFI in the shared `build/uefi` directory before returning.
Incoming and final shared outputs are retained as `previous-build` and `last-build`
inside the run directory, so stale profile objects cannot contaminate normal admission.
Then run `python3 -B scripts/kernel_graphical_smoke.py --images DIR/images
--evidence DIR/guests QEMU OVMF CODE VARS DATA`, using either a combined OVMF path
or the CODE/VARS pair and empty strings for unused inputs. The shell uses the
shared firmware selector; usual QEMU/firmware/compiler overrides apply.

Coverage includes production help/status/note write/read/edit/exit; capture BS/DEL/CRLF,
rejection/recovery/exit and a sent but unconsumed sentinel; exact capacity 64,
overflow 65 locking/recovery, event 80 and native idle 4096; an explicit fixture-G
regression; note readback, shorter/empty replacement, malformed/control-byte
preservation and the maximum 53-byte note; invalid selector, all four C/D/c/d
no-effect authority denials and F/I
pixel failures. The 96-copy guard remains hosted-only. Idle has no input or pause
from release through its terminal marker. Production uses observed viewport
boundaries because it has no PRE_SAMPLE markers. Capture sends only the selector
before PRE_SAMPLE 0, then synchronizes every byte on completed-sample markers.

Every saved physical/PPM pair checks scanout, the model viewport, every outside
byte and the 1,024-byte tail against a real baseline. Captures retain selected
editing/control/capacity milestones and final state; this is sampled evidence,
not continuous memory observation. F/I overlays exactly 0/55 successful model
stores on that baseline and checks 1/56 attempts, without hosted A5-fill bytes.
The production baseline is its already-painted initial state; it cannot establish
pre-initial-paint outside-byte preservation. Production's actual exit 33 is
separate from the capture guests' QMP quit 0.

Guests use original-clock q35/TCG, one CPU and disposable snapshot media, with
no network or physical-device access. Each graphical guest has a 90-second wall
limit (production also has at most 80 small 56,032-byte state probes per chunk,
with full pairs only at matches); restoration has
30 seconds. Serial is limited to 1 MiB, cumulative QMP and each child output file
to 4 MiB. Per-case raw pairs, input, serial, QMP, stderr and summary are preserved
on first failure; remaining cases stop, owned QEMU is reaped, and the retained
normal image is actually booted in `finally`. Separately, the shell rebuilds
normal UEFI in shared `build/uefi` on success, build-only, and failure or handled
INT/TERM after staging starts. Foreground work finishes before shell restoration;
the original failure status is preserved, and a restoration failure is reported
with its retained build log and makes an otherwise successful command fail.
This rebuild does not replace the staged-normal boot validation. This isolated
window leaves no persistent guest state, so one final boot suffices.
Ordinary/optimized compiler-free runner
controls belong to Meson `dev`/`full` and `make test-graphical-controls`.

The graphical console shares `console.session_note` with the simple serial
console: exact `write note <text>` replaces one RAM-only note, and `cat note`
renders its content or a missing message. Content is at most 53 printable ASCII
bytes; empty content is valid and replacement clears the previous suffix. A new
invocation starts missing. The hosted transcript oracle additionally covers
UART damage, invalid bytes and same-process session reset. These source changes
require fresh qualification; this paragraph records no new execution.

The existing 68 response cells, 80 input events, 96 copied samples and pixel,
stack and image limits are unchanged. Maximum-length write/read/exit with LF
uses 79 events; extra editing or CRLF bytes can exhaust that budget. Input is
still serial, with no physical keyboard, filesystem, disk persistence or new
device authority.

## Dependency and outcome

The output-only checkpoint is a native Aurora-rendered graphical status page after
`ExitBootServices`, through sealed `DisplaySession` on accepted NativeConsole
PR97/main `916fd18f18995241c1da367db6a04e7eb3cfce63`. The compiler extension
retains kind-checked exclusive synchronous borrowing and existing readonly byte
windows. Its focused compiler/Console regression review is separate from final
integrated acceptance. Aurora owns the project-authored font, rasterization,
colors, clipping, cursor/layout and all human-facing content.
The trusted host boundary only authenticates, bounds-checks, packs pixels and
performs ordered volatile stores. No raw pointer, mutable framebuffer span or
`OwnedBytes` video-memory surrogate is introduced.

The shared `graphics.font5x7` library module supplies the base A-Z, 0-9, space,
colon and hyphen glyphs and the original unsupported-byte fallback. Constants
retain seven readable five-bit binary groups and their documented packed-bit
orientation. The graphical consumer adds its lowercase/punctuation glyphs and
draws at unit scale directly; the status page retains its 3x/2x scale selection.
The hosted gate checks all 256 base-font byte mappings against independent visual
rows and both consumers against their existing pixel oracles. Historical guest
captures retain their original source/compiler scope; extraction and simplified
unit-scale drawing require fresh integrated image/stack and guest gates.

## Provisional transport and authority

Handoff v5 retains the 128-byte header and reserves its own record at arena offset
`0xe0000`, supervisor read-only/NX. The other versions retain their existing
meaning. The output-only build rejects combination with ACPI, runtime, BAR and
console profiles; combined input/display borrowing uses the separate v6 contract
below.
The 64-byte version-1 graphics record contains magic/version/length, physical
base/resource bytes, width/height/pixel pitch/format, selected mode/mode count and
zero reserved bytes. It carries no firmware pointer.

The loader performs bounded GOP discovery, mode queries and selection before the
final memory-map/exit loop. Every successful query buffer is freed. It prefers
800×600, otherwise the first supported mode. Limits are 1024×768, pitch at most
1024 pixels, 64 queried modes and at most 3 MiB/768 mapped pages. Only UEFI's two
32-bit RGB/BGR formats are accepted; the reserved byte is canonical zero on pixel
writes. Base must be page-aligned and every rounded mapped page must lie entirely
inside the reported resource. Unsupported alignment, bitmasks and BLT-only modes
fail closed. See the [UEFI GOP definition](https://uefi.org/specs/UEFI/2.10/12_Protocols_Console_Support.html#graphics-output-protocol).

Ordinary admission requires complete reserved/MMIO final-map coverage. It denies
RAM, runtime and ACPI overlaps, unsupported memory attributes, the complete owned
arena, LAPIC, IOAPIC and the q35 ECAM aperture. It checks physical width and PAT
index 3 is UC, without changing PAT/MTRRs. Every exit retry rechecks its final map.

A separately named q35/OVMF/std-VGA fixture rule is now source-prepared from an
independently accepted probe and is called only by the explicit fixture build. Actual rendering and no-write failure capture are qualified only for this fixture. Missing descriptor coverage never selects it automatically.
`FramebufferRecord::parse` yields only a description; it cannot mint the resource
token accepted by that rule. The pre-exit loader can mint that token. The
payload restoration adapter establishes the current root, owned immutable
record and complete tree before constructing its counterpart. Its exact resource tuple is base `0x80000000`, 1,921,024 bytes (469 pages),
800×600, pitch 800, BGR format 1, mode 3 of 30 and physical width 40. Every
field drift rejects. The external qualification additionally pins q35/TCG,
qemu64, one CPU, 128 MiB, std VGA, QEMU, OVMF and tool data; guest metadata cannot
prove those environment identities. Source/model and final-image reviews remain
required for independent qualification; developer previews retain the automated
image, stack and runtime guards.

The mapping window begins at `0xffffa00000001000`; both end guards are absent.
Its maximum extent requires four additional intermediate table pages, within the
unchanged 16-page pool and 1 MiB arena. Leaves must match exact physical pages and
supervisor RW/NX/UC flags. Whole-tree validation rejects all extra leaves, aliases,
shared/cyclic table paths, changed permissions and missing pages. Handoff v5 alone
does not relax the strict verifier. No user mapping is created.

## Evidence and required remaining gates

Hosted source tests cover geometry, independent byte packing, strict coverage,
map splits/holes, forbidden resource intersections, PAT/width failures, mocked
GOP calls/freeing and complete-tree/guard/alias corruption. These are bootstrap
models, not graphics or physical-device qualification.

The dedicated probe runner accepts only explicitly pinned QEMU/firmware/EFI
inputs, uses disposable q35/TCG/std-VGA with the original clock, records its exact
command/output and requires ordered firmware-exit/private-paging markers. It does
not build or approve an image. A separate normal-image restoration remains
required. The capture-only pre-store UART gate follows private paging,
accepts exactly byte `0x47`, and has a ten-million-iteration bound. It gives
Aurora no input capability. The host pauses QEMU, captures all 469 pages, releases
the gate, then pauses the completed or fail-stopped image for comparison. Record,
permission and stale-grant injections occur only after that baseline gate.
The record negative corrupts the local copied record; it never makes the owned
record page writable or disables CR0.WP. The existing generic smoke oracle does not qualify this new mode.

The accepted hosted/native evidence covers independent generated-Aurora pixels,
RGB/BGR guard/padding, source/IR/private-ABI authority, exact linked mixed-stack and
image checks, reviewed guest admission, real screenshot/physical before-and-after
capture and denied grants with no stores. The final integrated GCC 16 Meson
`full` suite and independent merge review are still required.

### Accepted aperture probe, 2026-10-08

The independently admitted probe EFI was
`2ba93fcb453c1cd1a18fedabbbe6b2a880f07dc270757a049a258ddaf0586626`;
payload ELF `0dcff4bf8b402af061d646e44a16100dfc80be2deb5ba506c41be9498b82762c`.
QEMU was `d3c1a558ad220e77a4412048c8d96b44f8c2b41c7ad2a4ecfe522a4b122fe067`,
OVMF `14954040cc754ade0c625ac3470ea46d4c14318b5b1396de4ef77090203d76db`.
The exact 469-page GOP resource above had no overlapping final-map descriptor;
ordinary described admission correctly denied it. ExitBootServices succeeded on
attempt 1; private paging and matching geometry were verified with eight table
pages. An independently reviewed receipt bound source/compiler/tool-data hashes,
ordered markers, geometry and map arithmetic. A separate fresh normal image
actually booted through the standard success oracle afterward. These results
qualify the aperture observation only; they do not establish Aurora pixel output.

### Current hosted and image preparation

Five actual-generated-Aurora byte cases cover native 800×600 BGR, padded RGB,
two clipped odd surfaces and the maximum 1024×768 geometry. Their independent
font-row/byte oracle matches all visible pixels, reserved bytes, guard regions,
row padding and page tail; the native-size scene issues 484,711 stores. A real
Console grant supplied to the generated Display entry fails before stores.
Native session controls also reject cross-kind grants in the opposite direction,
stale generations, raw channel overflow, reentry, geometry/mapping drift and
invalid lifetime/completion. These are hosted results, not guest capture proof.

The new exact image gate reuses the fail-closed CFG/object decoder without its
old image measurements. It admits only two verified immediate-push encodings
(`6a00`, `6a28`); memory pushes and wide signed stack normalizations stay rejected.
The shared walker checker additionally accepts one exact save/level-move order,
with r14 saved before assignment and unchanged root-3/decrement/restore proof.
The lookup and recursive walker prohibit IPA cloning/partial inlining to retain
unambiguous object identities and exact four-level roots. Original decoder
controls plus new mutations pass; budgets remain 16 KiB stack and 15,360-byte
mixed-stack/fault cap. Independent qualification requires final exact-image
review pins; the developer preview binds the automatic admission to current
source and image bytes.

### Accepted native capture, 2026-10-08

Execution manifest `8bbb3356d0939cc5d13eb79128feaeb01e934016c5c306106e4d842790260171`
bound the independently reviewed images, source-equivalence wrappers, compiler,
runner, firmware, QEMU/data/runtime and four explicit approval roles. The current
Aurora formatter changed whitespace only; independently regenerated assembly was
byte-identical. Original build receipts remain intact; no rebuilt-image claim
was made for those source-only rebindings.

The positive guest exited firmware, validated private paging, waited for the
baseline capture, and then executed 484,711 Aurora pixel operations. The raw
1,921,024-byte framebuffer and real 800×600 screenshot matched the independent
pixel oracle; all 1,024 rounded tail bytes equaled the baseline. Screenshot RGB
SHA-256 was `aa54951e2adf263c9e1c8abe47f85b03165f97cdbb6dd5a6bb8c3d01fc61d74e`.
There is no native row padding at pitch 800; padded-row preservation is hosted
evidence only. QMP pause acknowledgements and exact release ordering were checked.

Three fresh denied guests (malformed copied record, NX-missing mapping and stale
generation) retained all 1,921,024 resource bytes and their screenshots unchanged,
with zero Aurora stores. Each fail-stop was captured before termination. A
separate normal image then actually booted through the standard normal oracle
(exit 33). Independent raw review SHA-256 was
`87d128213af579dec28b8f5f1850ad4c030ec560ddb1fec9bf574669571d98f6`.
No new CPU/GPU device activation, DMA/IOMMU progress, physical hardware support,
interactive graphical input or general compositor follows from this checkpoint.

## Bounded serial-input graphical session

A separate profile combines distinct ConsoleSession and DisplaySession borrows
in one synchronous invocation. `examples/kernel-graphical-console.au`
reuses the exact Aurora Line64 editor and project font, adding all printable ASCII,
two rows of 68 text cells, an underline cursor and dirty-cell redraw. The prompt
accepts 64 bytes, BS/DEL, CR/LF/CRLF and the existing help/status/exit commands;
invalid/damaged/overflow lines reject until submission. The second row retains
only the latest response. There is no scrolling terminal or keyboard driver.

The viewport is 408x18 pixels at (32,128), requiring at least 440x146 geometry.
Outside pixels and padding remain untouched. At most 80 byte events and 96 copied
samples yield at most 82 changed paint passes and 992,938 pixel stores, below the
unchanged million-store cap. Source exhaustion renders a final response; the
separate native 4096-total-wake ceiling fail-stops without inventing input.
The 96-sample guard has hosted-only coverage through damaged copied observations;
clean absent UART polls stay inside the native session and do not consume it.
Closed graphical completion values are independently checked and explicitly
mapped when both original sessions close. Pixel failure stops without retry or
rollback. No source capability contains or replaces the other.

The native source profile uses handoff v6, independent Console/Display
preflight, exact paired LAPIC/framebuffer whole-tree verification and observational
timer/interrupt/UART quiet checks. Versions 1–5 retain their original contracts.
The 1 MiB arena, 16 page-table pages and 16 KiB stack stay unchanged. Each exact
image must establish normal + fault <= 15,360, wait + IRQ + fault <= 15,360 and
IRQ + fault <= 4,096 bytes, including the 176-byte IRQ frame and alignment.

Developer entry remains `UEFI_MODE=graphical-console ./scripts/kernel-uefi-build.sh`
(with `graphical-console-capture` reserved for controlled capture). Both modes
require their own combined linked-stack/image begin/end/emit admission;
every new attempt invalidates prior combined receipts before build work. Missing
or failed checks reject. Automatic evidence still requires independent exact-image
review and cannot authorize a guest or borrow a legacy profile's qualification.
Version-3 image receipts separate capture source/artifact and measured state
structure by mode. Capture state evidence says `structure-only` and
`behavior_qualification: pending-hosted-and-guest-gates`; emitting or checking a
receipt does not mark those gates passed. The
`source --mode graphical-console-capture` action checks only the source contract.
The capture profile separates its bounded pre-store selector from editor input,
emits completed-sample/store markers, and leaves terminal or failed scanout intact
for external physical capture and ordinary normal-image restoration.

`make test-graphical-console` now shares the controlled build-once compiler and
includes the paired paging model and ordinary/optimized admission controls.
Meson `slow`/`full` includes the complete hosted runner; `dev`/`full` includes
paging and admission controls. A directly pinned run uses
`python3 -B -O tests/kernel-graphical-console.py --run /path/to/aurorac
--compiler-sha256 REVIEWED_SHA256`; a controlled `--developer-build-receipt`
is also supported. Every invocation recompiles the observer and hashes its
recursive quoted-header closure, including the capture policy. Existing routes
remain sufficient; registration alone is not aggregate qualification.

The earlier actual generated consumer passed
67 hosted cases: 39 transcript/geometry cases, six baseline/output-failure cases,
and 22 pre-entry denials. Intermediate and final pixels, exact ordered stores,
untouched guards/padding, bounded completion and no-retry behavior were checked
against a separate model. Independent receipt/source review confirmed that scope;
most successful raw outputs were compacted into comparison receipts and hashes.

The independently accepted positive three-boot window 004 covers the original
988-file production and capture source snapshots and their exact admitted images.
Actual PTY input exercised editing, help/status, rejection locking, CRLF and exit.
All 17 physical/PPM capture pairs matched: two production initial/help captures
and fifteen capture-profile baseline/intermediate/final captures. The capture
guest consumed 31 samples, left its sentinel unconsumed and made 26,163 stores;
the production guest completed with 16,321 stores and exit 33. A separate ordinary
normal image passed its existing serial oracle with actual exit 33. Independent
review `interactive-results-review-004/review.json` has SHA-256
`e28aacf7b586aca97a8583cc61d6ba71d450067042751097e79d9c73ac148f43`.
This accepts that positive interaction only; it preserves failed earlier attempts
and the restoration's sampled-process-provenance limit, with no continuous or
post-entry mapping claim.

Four separate windows on the preserved capture image also qualified exact
64-byte capacity, 65th-byte overflow locking and recovery, 80-event termination
and the native 4096-wake idle deadline. Their 22 additional physical/PPM capture
pairs matched exact model stores or unchanged initial pixels. Idle reached
4,097 raw polls with zero copied samples and retained the initial 7,826 stores;
this fail-stop is distinct from the hosted-only 96-copy guard. Each window had
its own actual ordinary normal restoration with exit 33; capture termination by
QMP is not native debug-exit 35. Independent review
`remaining-guest-results-review-001/review.json` has SHA-256
`4a2e9b38ea04e9ec6c1e2a141ffd6e5f9ad55145429821282cfceb338cfaf143`.
These results retain the same sampled-provenance limits and qualify only those
preserved images, not the numeric-selector candidate below.

The joined capture-only failure extension is unqualified. Its pure closed policy
accepts exactly seven selector bytes before any grant, consumer entry or store:

| Byte | Release code | Scenario | Fixed action |
|---|---|---|---|
| G | 1 | normal | Use both live grants |
| C | 2 | cross-console | Put the live Display grant in the local Console field |
| D | 3 | cross-display | Put the live Console grant in the local Display field |
| c | 4 | stale-console | Close/reopen Console and invoke with its saved old generation |
| d | 5 | stale-display | Close/reopen Display and invoke with its saved old generation |
| F | 6 | first-pixel-error | Fail the first pixel attempt, before any store |
| I | 7 | interior-pixel-error | Fail after exactly 55 successful stores |

All other 249 bytes reject with `capture selector` and no release marker.
A valid byte emits `AURORA_GRAPHICAL_CAPTURE_RELEASED: selector=N` through the
existing decimal-number writer, with exactly the code above; invalid code 0 is
never released. The source-contract receipt is
`aurora-graphical-capture-source-v2`. The ten-million-iteration gate and UART-error
rejection are unchanged. No later byte selects a scenario.
The hosted observer independently checks all 256 selector values, literal numeric
codes, exact names and fixed failure predicates. The complete hosted runner now
requires 68 cases: 39 transcript/geometry, seven baseline/output-failure cases
(including ordinal 55) and 22 pre-entry denials. This inventory is prepared, not
a claim of a new hosted pass.

Failure lines retain their original fields and append capture-only
`completed=N wakes=W pixel_attempts=P`; completion lines append
`entries=E samples=R output_attempts=O completed=N pixel_attempts=P` after their
existing completion/wakes/stores fields. Production diagnostics retain their
original format. C/D/c/d must fail paired-service preflight with zero counters
and an unchanged full framebuffer; an invalid selector also has no release.
F/I return graphical completion 2 with one entry, zero samples/output attempts and
respectively 1/56 pixel attempts and 0/55 stores, before any pre-sample marker.
I preserves exactly the first 55 model stores: a 6x9 background cell and the
first glyph pixel.
These inject the existing transport failure result at valid coordinates; no
geometry fault, retry, rollback or synchronous fault is claimed.

The new candidate requires focused generated-consumer verification, exact
production/capture reconstruction and independent image admission, separate
guest denial/pixel-failure windows and positive regression, actual normal
restoration, then the final integrated full Meson graph on GCC 16 and independent
review. GCC 14 checks are optional targeted compatibility evidence.
Original 988-file image receipts and preserved-image guest results do not qualify
the new joined source. Partial/null-pair denials and deterministic synchronous faults
remain separate from the seven selectors; no new keyboard, desktop or physical
hardware qualification follows.

The paired verifier also has a separate, closed GCC16 emission proof. Its actual
single walker definition remains bound through raw `.ci`/`.su`, object and linked
bytes; no second alias is synthesized. The eight exact bodies require distinct
root and walker save-slot, snapshot, six-guard, indexed bitmap and decreasing-level
proofs. Unknown or mixed layouts reject, and existing stack/IRQ/wait budgets stay
unchanged. Source controls and retained-body analysis do not qualify a fresh
image or guest; complete current-source admission and independent review remain
required for each toolchain.

Only the graphical profile requires the private Console and Display validators
to remain separate non-inlined, non-cloned bootstrap functions. Their raw compiler
symbols, source ownership and frame sizes must agree with object/linked evidence;
the validation predicates are unchanged. Other profiles do not enable these
emission attributes. This boundary changes paired generated inputs, so fresh
image/stack and capture-contract review is required before qualification reuse.

The graphical stack adapter may authorize only a pair of direct RSP-relative
qword argument pushes in the existing graphical entry owner. Actual instruction
sites, unique ownership and four-byte opcodes replace historical function sizes
and instruction offsets. Only positive, aligned disp8 sources are admitted.
The shared decoder otherwise rejects memory pushes. For an authorized
site it bounds the complete eight-byte source against the old live frame before
adding eight bytes of stack consumption; stale or unused sites and unbalanced
paths reject. This proves bounded stack effects, not copied-value initialization
or authority. Existing save/return checks and whole-image budgets remain in force.

Current capture admission retains PE/ELF/PIC checks, `.su`/`.ci` associations,
object/linked-byte binding, bounded stack/control-flow and private-ABI checks,
source capture-policy controls, and production fixture absence. Fourteen named
BSS fields must have the expected type, size, alignment, containment and disjoint
storage: nine counters/state fields, Console and Display grants and generations,
and the graphical entry's active flag. Addresses and section indexes are measured;
current source/tool/output hashes bind the local build rather than select an
allowlisted historical machine.

The removed capture checker replayed exact instruction/file/tool tuples to claim
selector, authority, pixel-failure, diagnostic and inline UART/text/decimal
behavior. The replacement does not establish those semantics or validate every
historical GCC16 state global. Hosted grant/state/failure tests and actual guest
capture, denial, pixel-failure and normal-restoration gates remain required.
Compiler-free controls use small hand-authored structural/negative fixtures;
complete encoded build snapshots are no longer repository test inputs.
The separate paired-walker exact-body/storage/recursion fixtures and narrow
memory-push assumptions above remain unchanged. This is bounded stack/layout
evidence, not arbitrary machine safety or complete compiler independence.
