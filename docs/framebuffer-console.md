# Bounded firmware framebuffer console

Integrated output-only rendering checkpoint with independently accepted guest
capture on the exact pinned fixture. Final joined developer/slow/full-Make gates
and merge review remain pending; this is not a claim of whole-system readiness.
Firmware `SetMode` can clear its display before the controlled capture boundary.
No GPU driver, desktop, physical Framework display support, DMA or IOMMU claim
follows from this work.

## Dependency and outcome

The candidate is a native Aurora-rendered graphical status page after
`ExitBootServices`, through sealed `DisplaySession` on accepted NativeConsole
PR97/main `916fd18f18995241c1da367db6a04e7eb3cfce63`. The compiler extension
retains kind-checked exclusive synchronous borrowing and existing readonly byte
windows. Its focused compiler/Console regression review is separate from final
integrated acceptance. Aurora owns the project-authored font, rasterization,
colors, clipping, cursor/layout and all human-facing content.
The trusted host boundary only authenticates, bounds-checks, packs pixels and
perform ordered volatile stores. No raw pointer, mutable framebuffer span or
`OwnedBytes` video-memory surrogate is introduced.

## Provisional transport and authority

Handoff v5 retains the 128-byte header and reserves its own record at arena offset
`0xe0000`, supervisor read-only/NX. The other versions retain their existing
meaning. The output-only build rejects combination with ACPI, runtime, BAR and
console profiles; mixed input/display borrowing is a later explicit extension.
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
required before a mapping/rendering guest.

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
required. The qualification-only pre-store UART gate follows private paging,
accepts exactly byte `0x47`, and has a ten-million-iteration bound. It gives
Aurora no input capability. The host pauses QEMU, captures all 469 pages, releases
the gate, then pauses the completed or fail-stopped image for comparison. Record,
permission and stale-grant injections occur only after that baseline gate.
The record negative corrupts the local copied record; it never makes the owned
record page writable or disables CR0.WP. The existing generic smoke oracle does not qualify this new mode.

The accepted hosted/native evidence covers independent generated-Aurora pixels,
RGB/BGR guard/padding, source/IR/private-ABI authority, exact linked mixed-stack and
image checks, reviewed guest admission, real screenshot/physical before-and-after
capture and denied grants with no stores. Final joined Meson developer/slow,
complete root Make and independent merge review are still required.

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
mixed-stack/fault cap. Final exact-image pins are required before every guest.

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

## Unqualified serial-input graphical session

A separate unqualified draft combines distinct ConsoleSession and DisplaySession
borrows in one synchronous invocation. `examples/kernel-graphical-console.au`
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
Closed graphical completion values are independently checked and explicitly
mapped when both original sessions close. Pixel failure stops without retry or
rollback. No source capability contains or replaces the other.

The new native source profile uses handoff v6, independent Console/Display
preflight, exact paired LAPIC/framebuffer whole-tree verification and observational
timer/interrupt/UART quiet checks. Versions 1–5 retain their original contracts.
The 1 MiB arena, 16 page-table pages and 16 KiB stack stay unchanged; combined
linked-stack/interrupt/fault bounds have not yet been measured or admitted.

Developer entry remains `UEFI_MODE=graphical-console ./scripts/kernel-uefi-build.sh`
(with `graphical-console-capture` reserved for controlled capture). The combined linked-stack/image checker has independent source review and
focused hostile controls. Both modes require their own begin/end/emit admission;
every new attempt invalidates prior combined receipts before build work. Missing
or failed checks reject. Automatic evidence still requires independent exact-image
review and cannot authorize a guest or borrow a legacy profile's qualification.
The capture draft separates a bounded pre-store release byte
from editor input, emits completed-sample/store markers, and leaves terminal or
failed scanout intact for external physical capture and normal-image restoration.

`make test-graphical-console` now shares the controlled build-once compiler and
includes the paired paging model and ordinary/optimized admission controls.
Meson `slow`/`full` includes the complete hosted runner; `dev`/`full` includes
paging and admission controls. A directly pinned run uses
`python3 -B -O tests/kernel-graphical-console.py --run /path/to/aurorac
--compiler-sha256 REVIEWED_SHA256`; a controlled `--developer-build-receipt`
is also supported. Registration alone is not aggregate qualification.

The earlier actual generated consumer passed
67 hosted cases: 39 transcript/geometry cases, six baseline/output-failure cases,
and 22 pre-entry denials. Intermediate and final pixels, exact ordered stores,
untouched guards/padding, bounded completion and no-retry behavior were checked
against a separate model. Independent receipt/source review confirmed that scope;
most successful raw outputs were compacted into comparison receipts and hashes.

Native mapping/timer/lifecycle mutations, exact linked-stack/image admission,
PTY-to-physical-pixel/screenshot correlation for editing and responses, guest
no-write failures, actual normal restoration, final dev/slow/root Make and
independent review remain required. Hosted tests and earlier static-frame/serial
profile evidence do not establish interactive graphical guest qualification.
