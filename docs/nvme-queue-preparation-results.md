# CPU-only NVMe queue preparation results — 2026-10-07

This checkpoint prepares and cancels real owned pages in the existing
namespace-free QEMU BAR fixture. It does not initialize NVMe, publish a DMA
address, submit a command, read a disk or qualify DMA isolation.

## Source and scope

The ownership candidate began from PR58, commit
`f7aab2362c34bcabe62732aa58ac7f33f459de66`. Final composition preserves PR59's XFS
file consumer and PR60's host-build controls, based on main
`0c72576672f97296b7a9903806eaa3fb76eb4db7`. The existing `PhysicalPages` pool is
initialized once and passed through the trusted discovery chain. `PinLedger`
and the protected-runtime pool keep their existing contracts.

The initial independently admitted 711-file manifest was
`5dd0645bd430381a904cbf794382d1a5fc6bbd26481ef3cb23989295fcaa6468`.
The corrected 712-file manifest used for linked/guest qualification was
`53a3632abc9f9574cfd176f326d5b2c7e5abb36b511e8bbd5d3ef50f1687d465`.
Both exact manifests and their source copies are retained with the evidence.
The final join preserves all tested kernel and UEFI build inputs byte-for-byte;
its overlapping developer-command test retains both the NVMe context checks and
PR60's host-control rejection. Results documentation does not change compiled inputs.

See the [ownership and lifecycle contract](../kernel/uefi/NVME-QUEUE-PREPARATION.md).

## Hosted qualification

GCC 14.2.0-19 built the focused tests with warnings as errors. All 14 original
hosted steps passed in 84.87 seconds, with quiescent owned-child cleanup and all
711 source hashes unchanged:

- Queue lifecycle: 1,871 checks and 1,901 generation-bound checks, each normally
  and under fatal ASan/UBSan, plus production API and invalid-profile controls
- Existing page/protection/domain/scheduling checks, normally and sanitized
- Existing PinLedger: 165/294 checks and API controls, normally and sanitized
- BAR policy: 142,075 descriptor/read/lifetime checks and 1,101 reservation checks
- Serial parser: eight positives/1,010 rejections; trace parser: eight synthetic
  positives/1,296 rejections, in normal and optimized Python
- Provenance launch parser: four synthetic profiles/194 rejections in both modes
- Developer routing controls in both modes, including rejection before work when
  either new Make target receives an invalid inherited test context

ASan used `detect_leaks=0:halt_on_error=1:abort_on_error=1`; UBSan used
`halt_on_error=1`, including the existing page runner. No leak checking or
sanitizer coverage of generated Aurora assembly is claimed.

After the lifetime correction below, the queue tests and sanitizer configuration
were replayed. The new stack guard passed two positive and 41 rejecting controls
in both Python modes, including missing/inflated frames, unmodeled large
subordinates, missing direct edges and an improperly retained ACPI parser.

## Rejected linked image and corrected stack lifetime

The first image build passed layout checks but failed independent stack review.
Its maximum-frame sum through preparation was 16,960 bytes. Actual fixed frames
and live outgoing slots already required 16,672 bytes before preparation, so
this was a real overflow of the unchanged 16 KiB bootstrap stack. No guest was
started with that image. Its source, ELF, disassembly, frame reports and rejection
remain preserved.

The fix ends the BAR ACPI parser's lifetime before PCI discovery, using the
existing IVRS/table wrapper pattern. It neither increases the stack/arena nor
introduces another allocator. Seven affected BAR profiles and normal were rebuilt.
The corrected preparation ELF SHA-256 is:

`472f8a71e140a8677df70855f6a3638369fd54d731dace6fdef62149166acb6f`

Independent linked review confirmed the wrapper restores before its PCI
transfer, inspected subordinate calls and bounded the fault path below 192 bytes.
The conservative preparation bound is 14,960 bytes including a 512-byte fault
reserve, leaving 1,424 bytes unused. Affected BAR controls are bounded at 13,520
bytes or less. The build now checks the actual preparation frame reports and
linked edges. The original image is explicitly rejected by that guard.

All 19 corrected replay steps passed with unchanged source hashes. The normal
ELF remained byte-identical across builds. No BIOS, full native aggregate or
complete historical boot-matrix qualification is added.

## Actual guest and trace qualification

Exact restored QEMU 10.0.13, clean/stock firmware, patch and trace-control inputs
were verified. Four coverage-file path references were relocated; their original
bytes and the unchanged referenced controls remain retained. The enabled event
inventory still contains all 218 required events. No historical control program
was re-executed or credited as a new qualification.

The first preparation guest returned 33 and passed strict serial validation, but
its trace was truncated at the existing 8 MiB file bound. That run remains a
failed, unqualified trace gate. The preserved failure was not relabeled as a pass.

A separately approved replay allowed 32 MiB trace files while retaining the
256 MiB invocation-owned aggregate and the existing memory/wall limits. Other
files kept an 8 MiB sampled bound. Two fresh output roots bounded three and four
traces respectively; event coverage and validators were unchanged. Both original
sessions exited zero with quiescent cleanup:

- Preparation, clean BAR read, inherited-controller refusal, then actual normal
  restoration: 27.14 seconds; peak owned output 40,652,800 bytes
- Read-only write fault, revoked-window fault, alias rejection, resource-profile
  refusal, then actual normal restoration: 34.22 seconds; peak output 54,378,496 bytes

The complete preparation trace is 12,393,632 bytes. The guest allocates five real
pages, verifies all 20,480 initialized bytes, poisons and cancels them, verifies
scrubbing and zero held/pool counts, revokes the BAR window, and completes the
existing allocation/language self-test. Every guest ELF equals its linked-reviewed
image. Source and runtime pins remain unchanged.

Unchanged strict serial, complete trace and artifact-provenance checks passed
all seven modes. Clean traces show only the admitted seven NVMe register reads
(or zero reads for early rejection), no Aurora PCI configuration/controller/
queue/doorbell writes, and the inactive BME-clear handoff. The known firmware
PCI-enumeration transient BME probe remains explicitly distinguished from Aurora
activity. Stock firmware initialization supplies a refusal control, not permission
to activate a controller in Aurora.

Independent retained-evidence review replayed all seven strict validators and
verified both source copies, image/runtime identities, terminal records and both
actual normal restorations. It did not rerun a guest or native workload.

Both groups actually booted their normal restoration image, whose ELF SHA-256 is
`ed9eb0a2c1ce186c9e6931698d29c75a4ced9647dbba7bc11365388f1e693484`.

## Limits and next dependency

These are focused CPU ownership, copied authority, image-stack and disposable
QEMU observations. Memory/output sampling is not a hard kernel quota. The private
source/evidence capsule preserves raw logs, exact hashes, both original failures,
independent reviews and corrected runs; no third-party binary is added to the
repository.

The existing roadmap still requires a real IOMMU oracle, observed translation/
invalidation/completion qualification and a separately reviewed publication/
quarantine lifecycle before activation. There is no actual Identify/read command,
namespace backend, filesystem mount, persistent storage, physical AMD qualification
or performance comparison in this checkpoint.
