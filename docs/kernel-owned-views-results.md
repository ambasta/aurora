# Reconstructed kernel readonly-owner views: focused results (2026-10-08)

Fresh local guest and host gates passed. This reconstructs the bounded increment
lost in the October 7 workspace rollback; no erased results are reused as current
evidence. Final independent evidence review and publication are separate.

## Source and dependency

The change composes the independently accepted reconstructed owned-span/PR77 JSON
prerequisite, tree `80b099b1c03bc5a9c6b92b2c649d95a77c1a3670`, with twelve
changed/added kernel fixture, admission, host-test and documentation files.
Compiler/runtime implementations remain unchanged. The explicitly reused compiler
SHA256 is `fde0877e0b3326bc8e6e500bb6d3a8ed9daef814af4f46ae1d319da31d707fe3`.

The guest-tested 842-file manifest SHA256 is
`d05684cb54b2988bbe23a985aed279f7904be7d6fd8283fd1ee1ed781156c754`.
The final 843-file source reconciles seven prerequisite documentation/test/routing
files and updates these results; no generated-code, runtime, kernel profile or
image dependency changes after the guest runs. Exact manifests and applicability
comparisons are retained with the evidence. The [contract](kernel-owned-bytes.md)
describes the unchanged authority, quota, stack and cleanup bounds.

## Running mechanism

The existing exclusive owned-bytes UEFI profile now requires exactly five real
imports: allocate, at, set, drop and borrow_length. Three Aurora functions stay
local; the private scalar bridge and existing reflection symbols are unchanged.
The consumer copies and narrows the 56-byte logical span, reads every byte, and
checks a two-byte window crossing logical offsets 4,095/4,096. Its success result
is the observed view length, compared against the independently supplied owner
length. A mistakenly empty view cannot pass a nonempty case.

Three exact 64-byte aligned span-call records are checked at source and link.
The consumer can call only the copied-read helper; it cannot allocate/drop an
owner. The complete linked proof includes generated expression/cleanup records,
exact C++ stack records and call edges, borrow_length and the bounded page-table
verifier. Bound: 2,416 +512 synchronous-fault reserve =2,928 <=15,360 bytes in the
unchanged 16,384-byte stack. The exact emitted `rep movsl` form is stack-neutral;
its acceptance conservatively invalidates tracked ECX facts, with controls.

Eight real even-page holders force two 4,097-byte owners onto physical pages
1/3 and 5/7 in the existing sixteen-page pool. The consumer crosses the first
owner's noncontiguous boundary. Every released owner page, including padding,
must be zero; every other page retains its poison and every foreign holder keeps
its exact identity/address before explicit release. Original65/513/4,097 cases
remain; successful-empty ownership adds one identity and no page. Exact final
counts are nine allocations and nine releases, zero retained use and a closed
grant. The quota stays8,194 bytes. No second allocator or public pointer ABI.

## Fresh completed gates

- Normal and optimized Python: exact import admission1 positive/28 negatives;
  linked-stack controls7/49; serial-oracle controls9/195.
- Fresh build-only owned-bytes, runtime-span and normal image admission; each
  includes14 negative PE/PIC images. Runtime-span independently admits high-VA
  RX user images. Real resize and mixed-graph negative links remain rejected.
- Exact Aurora fixture host replay: three modes,41 checks each, normally and under
  fatal ASan/UBSan. Both runs reject nonempty-to-empty borrow-length poisoning
  with exact exit1/stderr and no stdout. That wrapper first validates through the
  real helper, and exists only in the deliberately corrupted host executable.
- Independent pre-guest review reproduces2,928-byte linked bound and PE/PIC checks,
  validates source/link record agreement, and adds69 import/definition mutations
  plus12 wrong span-record extent rejections in both Python modes.
- Actual public owned-bytes guest passes fragmented/crossing/empty observations,
  exact counters, cleanup and close. The actual guest build's complete linked
  receipt is byte-identical to the previously admitted receipt.
- Actual public runtime-span and normal regressions pass. Both special launchers
  restore the normal image; five normal artifact hashes match fresh admission
  after EVERY guest. Runtime-span's retained user artifacts match admission.
- Canonical Aurora formatting is assembly-identical; pinned Ruff0.16.7 and
  clang-format22.1.8 checks pass. Final source applicability is checked separately.

Implementation build/host/guest commands completed successfully. An initial
independent-review replay rejected concurrent formatting drift; its initial
optimized draft was uncredited until corrected. The review-fixture correction is
retained separately and does not indicate a production defect. A build-lane
coordination mistake was corrected: process visibility is not proof of available capacity.
Completed correctness gates have no quiet/timing precondition and were retained;
subsequent lane use was explicitly coordinated. No timing result is inferred.

The restored QEMU executable SHA256 is
`d3c1a558ad220e77a4412048c8d96b44f8c2b41c7ad2a4ecfe522a4b122fe067`; combined OVMF
SHA256 is `14954040cc754ade0c625ac3470ea46d4c14318b5b1396de4ef77090203d76db`.
Fourteen official Debian package hashes were checked against signed metadata.
Public clock receipts verify original TCG clock, q35/qemu64, one CPU and128MiB.
No external target or system installation was used.

## Limits

The independent prerequisite's failed/stale/malformed owner and generated receiver
host tests remain separate evidence. This increment adds no owner-span guest fault
mode, receiver-return guest view, kernel resize, userspace owner allocation,
DMA/IOMMU/device activation, full native aggregate, full emulator matrix or physical
qualification. Sanitizers instrument host C++, not generated Aurora assembly;
leak checking is excluded. Tests are not a general memory-safety proof.
