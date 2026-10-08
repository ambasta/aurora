# Synchronous method spans and bulk append — 2026-10-08

The [bounded contract](../compiler/METHOD-SPANS.md) adds invocation-only readonly
method arguments and Aurora-authored ByteBuffer.try_append_bytes. It reuses the
existing receiver authority, 56-byte span layout and runtime helpers. Mutable
receiver calls reject every live same-root view, including empty self-append.
Bulk append reserves once before copying and commits length after all writes.
No object references, nested ownership, mutable spans or method overloads are added.

## Fresh focused evidence

- New source/native gate: 12 programs, 23 hosted native cases and 12 diagnostic
  rejections in normal and optimized Python; independent terminal replay confirms
  both modes. Compile-only admission explicitly skipped native executions.
  Three seeded append/truncate models compare complete bytes after each operation;
  quota and injected allocation failure preserve state/accounting. Real owner
  inputs exceed 4096 bytes. Receiver-only result provenance is checked after
  unrelated input-owner resize and movement.
- Independent source review/probes: six native programs and three exact rejection
  controls, including six-position mixed records, self-view const calls,
  receiver consumption in later arguments and implicit empty self-alias rejection.
- Independent typed IR: five accepted and 27 malformed cases rejected. Independent
  handwritten ABI: 1,512 boundary cases and 15 exact corruption controls per Python
  mode, with all seven words, R10/R11/RAX roles, canaries, empty forwarding,
  mixed classes/scalars and odd/even pending operand depths. The reviewer replayed
  all 34 retained native ABI executables and the complete malformed-IR transcript.
- Direct normal/optimized regressions: owned spans source/native, ByteBuffer,
  owning classes, readonly spans/windows, copied methods and short-circuit gates.
  General IR passes 964 cases; copied-method IR passes five/46 cases and its old
  handwritten ABI passes 21 native boundaries.
- The joined accepted PR79 JSON codecs pass 1,942 cases, 19,781 full-width
  observations, 45 rejections and 431 hosted checks per Python mode using the
  new compiler. Real owned codec inputs pass 41 cases per mode. The selected
  Meson graph also runs the complete existing JSON scanner oracle.
- All 28 existing kernel entry/program assemblies, including accepted PR80's
  owner-view entry, are byte-identical against the accepted fde0877e compiler.
  Runtime sources/helpers and representation remain unchanged. This is graph
  continuity evidence; no new guest feature or new guest run is claimed.

The first selected Meson core/bytes run completed with 41 passing tests and one
receipt-generation failure. That ABI test had passed all runtime/control checks,
then failed normalizing a relative script path for source hashes. The original
failure is retained; a path-only correction and selected replay complete the
focused composite. This is not an all-green original aggregate claim.

## Preserved corrections and scope

Three old negative source fixtures prohibited all method spans; they now check
still-illegal method parameter rebinding or mutable span syntax. Existing IR
fixtures still reject missing capability vectors and ordinary calls incorrectly
targeting receiver methods, with updated expected diagnostics. No lifetime check
was weakened. Earlier fixture failures from reserved method names and direct
copied-result return expressions remain preserved; fixes changed fixtures only.
An initial formatter command used unsupported option combinations; the corrected
check passed without changing Aurora source.

The standalone warning-clean GNU C++23/O2 compiler SHA-256 is
`512050d547be364fe859031417994fe5c2de69814eed4fffd801ba1e2e92fe7c`.
Rebuilding after pinned formatting produced the identical binary. Meson's separately
configured compiler SHA-256 is
`f0dee7330d02dfff6e145e1f8a6fbf78291c986667c0c07448140f294d5a1a65`.
Both use the same reviewed production sources. Pinned clang-format 22.1.8 and
Ruff 0.16.7 pass changed production/new test files; the existing Aurora formatter
accepts ByteBuffer. Full native, host sanitizer, performance, physical hardware
and general memory-safety qualification are outside this focused checkpoint.
