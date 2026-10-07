# Call-scoped readonly sector windows

The dependency is reading a real bounded source window through the consolidated
sector result, without another device representation. The acceptance gate is
native execution of every admitted sector and signed-address/length boundary,
complete byte comparisons, unchanged input and owned-copy checks, existing
consumer masking regressions, then independent source and evidence review.

## One operation on the existing contract

`storage::read_sector_window(bytes, base_lba, requested_lba)` in
`storage.sector_window` takes a call-scoped `builtin::span<const u8>`, a `u64`
absolute base LBA and an exact `i64` requested absolute LBA. It returns the
existing owned `SectorReadResult` (520 bytes), containing one copied `Sector512`.
There is no handle, retained span, new backend, geometry or write operation.
The span describes only this window; its length is not full-device capacity.

The error domain remains `SectorIoStatus`, with one appended `invalid_source`
outcome. Existing `success`, `out_of_range` and `read_only` meanings are unchanged.
`SectorReadResult.sector_or_zero()` already masks every non-success outcome;
`fs.xfs_sector` preserves that exact I/O status and rejects it before parsing.
The focused regressions exercise nonzero failure payloads and every public XFS
report status with the new outcome, including fabricated success reports.

## Ordered preflight and copying

1. An empty span, a length not divisible by 512, or a length greater than 4096
   returns `invalid_source` before any request conversion, subtraction or read.
2. A negative request returns `out_of_range` before conversion to `u64`.
3. An unsigned request below the base returns `out_of_range` before subtraction.
4. Subtract the base and compare the relative index against `length / 512`.
   An index outside the window returns `out_of_range` before multiplication.
5. Convert only the admitted relative index (0 through 7), multiply by 512,
   and copy 512 bytes through checked span reads and `Sector512.write_byte`.

No `base_lba + count` is computed. Bases above signed-i64 maximum have no
addressable request. Negative requests never wrap into that range. A window
beginning at signed maximum may still supply its first sector; later sectors
are simply not expressible through this signed request API. Source alignment
is relative to the span: a 512-byte subspan can start at any valid owner offset.

The one byte loop is the necessary readonly-span-to-owned-value boundary. It
is not a second RAM transport loop or an adapter between duplicate storage
values. Full length and address preflight precede it. The source remains
unchanged, and report/sector copies survive owner mutation and destruction.
All failures return a zero-initialized owned sector. No view escapes the call.

## Bounded tests and limits

`tests/compiler/sector_window.py` uses an independent Python address-enumeration
oracle and compares every returned byte. It covers every sector in each 1–8
sector length, first/last/interior bytes, zero/short/nonmultiple lengths,
endpoint-empty and unaligned subspans, below-base and one-past requests,
signed endpoints, full-width bases, unchanged sources, local-owner lifetime,
retained snapshots and exact 512/520-byte layouts. Rejections cover exact
argument types, private payloads, owned-result typing and the source-array cap.
All rejection checks preserve absent and existing output artifacts.

Local builtin arrays are capped at 4096 bytes and spans cannot be fabricated
by supported Aurora code. Thus the production greater-than-4096 length guard
is a source-reviewed defensive check, not a reachable native test. The Python
model checks that rule, while a compiler rejection checks a 4097-byte owner.
Neither is described as native execution of an oversized span.

Run `python3 -B tests/compiler/sector_window.py build/aurorac`, or select
`sector-window` in Meson's `bytes` suite. The complete compiler Make recipe also
registers the runner. Dependency gates are the existing `block_io.py`,
`sector.py`, `xfs_sector.py` and readonly-span/window checks on the unchanged
reviewed compiler. Focused native results are recorded separately after review.

This source has no disk/file access, transport driver, writable window,
filesystem mount, data authentication, persistence or full-device provenance.
It adds no compiler semantics, heap storage, larger values, aggregate/sanitizer
qualification, kernel change or physical-hardware claim. Genuine file-data
fixtures and checked XFS extent interpretation remain separate dependencies.

## Focused results — 2026-10-07

Independent source review accepted the exact PR57-based candidate before native
execution. The new runner passed all 110 native cases and nine rejections in
normal Python, then again in optimized Python through Meson. Existing changed
consumers passed 39 device-I/O cases/13 rejections and their example, plus 121
XFS-sector cases/five rejections, in both modes. The owned-sector dependency
passed 46 cases/nine rejections in optimized Python. All four selected Meson
runners passed with at most two workers; this is not the complete dev/bytes suite.

The unchanged readonly-span runner also passed 91 native cases including 25
exact bounds traps, plus 69 rejection cases. Readonly windows passed 132 native
cases including 66 exact traps, plus 21 rejections. These dependency replays ran
in optimized Python. Rejection fixtures check absent and existing output files.

The original outer process completed with exit zero. All 706 frozen source
hashes and three byte-identical compiler copies held through completion; the
owned temporary directory was empty and no matching native test process remained.
The reused compiler SHA256 is
`f44ecd5ae4cad266ca8cff62d42cd3970c61a4bcc04e025cd68e2b5f0656cdbd`;
all 18 compiler-directory C++ source/header files matched its reviewed source.
No compiler was rebuilt. GCC 14.2, binutils 2.44, Python 3.12.14 and Meson 1.12.1
were used. Logs and the exact source freeze are retained; the existing runners
do not preserve a complete per-case native-product archive. Final documentation
edits are separate from the tested freeze and claim no additional execution.
Independent terminal evidence review accepted these focused results.
