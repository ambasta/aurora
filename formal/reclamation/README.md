# First abstract reclamation proof slice

This directory is a standalone abstract model of obligation Q in
[formal foundations](../../docs/formal-foundations.md). It is not a kernel proof,
implementation refinement, or hardware qualification. The model received independent review. Inductive safety, future-extension safe
reuse, a successful Closing-activation/reuse witness and negative controls are
kernel-checked. These are results about this abstract transition system, not a
discharge of every implementation obligation in Q.

## Model and boundary

There is one physical backing root. Every logical alias, mapping and CPU gate for
that backing uses the same registry. `Cpu` is an arbitrary type; thus any finite
population is admitted, without fixing two CPUs as the architectural limit.
Generations and identities are mathematical naturals, with no wraparound.
Fresh gate *activation* identities are distinct from CPU identity. The centralized
registry is an abstract specification, not a required global runtime lock. Atomic
registration/activation steps are specification linearization points; arbitrary
CPU cardinality does not itself prove concurrent SMP execution or refinement.

An entry's immutable identity/generation/tag identifies either an admission gate,
a use/mapping, or a transfer to a CPU. The tags have distinct effects: a gate can
admit uses and send delegation, a use can access backing, and a transfer can
activate its destination. Physical possibility, live protocol liability and
accepted completion receipt are separate fields. Access and activation do not
consult the current generation or the obligation ledger. Registration precedes
physical exposure. Resolving a transfer atomically registers its receiver and
preserves other liabilities. Entries are never forgotten: resolved entries are
replay tombstones, not a bounded runtime-storage prescription.

Closing freezes root creation, not existing gates. Its global phase denotes a
fence request covering all registered gates, including activation during Closing;
fence-request transport/progress is not modeled. Hardware stopping precedes the
matching generation/identity receipt and liability retirement. Authority
retirement need not wait for child/use retirement: those liabilities remain
independently live. Quiescence checks protocol emptiness and gate receipts, not
physical state. Reuse is the atomic reclaim/new-generation step.

Delayed delivery is nondeterministic activation of an unresolved transfer.
Duplicate/reordered messages carry the same identity; resolved transfers cannot
activate again. No explicit network packet queue is needed for this abstract
safety relation. Loss, delay, timeout, rejected stale messages and crash without
forgetting liability are stutters. This does not establish durable recovery,
message authentication, or the implementation of duplicate suppression.

**Hardware-semantic assumption:** stopping an exact gate prevents every later
admission through that activation; stopping a use excludes all later effects of
that mapping/work; stopping a transfer means cancellation at every possible
destination. These are different obligations despite sharing a record-update
operator. A received acknowledgment alone is not a hardware stopping event. `receiveAck`
is an abstract completion-oracle dispatcher, not an implemented receipt verifier.
Unmapping alone, epoch advancement, timeout and loss do not satisfy this contract.

Excluded: reader/writer race freedom and authority attenuation (obligation A),
general overlapping extents, weak-memory/compiler semantics, GPU/DMA target
semantics, device reset, bounded replay storage, persistent crash recovery,
progress/fairness and costs. The concrete kernel's fixed CPU/process structures
are not claimed to refine this model.

## Checked results

Inductive preservation for arbitrary identities, generations and finite traces;
coverage of physical effects/admission/activation by live liabilities; quiescence
implies no physical possibility; every future trace after reuse excludes old
accesses. A successful trace must activate a transferred gate during Closing,
fence and retire authority while uses remain, drain the uses, then reuse.
Six kernel-checked mutant counterexamples violate the inductive invariant:
uncovered publication, premature fence/drain ACKs, lost transfer liability,
duplicate subtraction of another ticket and replay resurrection. They are not
all physical-unsafety witnesses or proofs that every guard is necessary. Two
additional witnesses establish actual old-generation physical accesses: epoch-only
reuse, and a false drain receipt followed by the original retire, Quiesce and
Reuse rules. The latter is an abstract analogue of unmapping without effective completion;
there is no literal unmap instruction in this model.

The [endpoint protocol refinement](R/README.md) now derives this abstract
receipt premise from local close/drain state and packet provenance, and forward
simulates Q. Its endpoint primitives and atomic per-root coordinator remain
explicit assumptions; it is not a target-hardware or decentralized recovery proof.

## Tools and trust

Use the official Lean 4.24.0 Linux release, without additional packages:

```sh
cd formal/reclamation
lake build
lake env lean Q/Audit.lean
./verify.sh
```

`./verify.sh` checks the exact toolchain, builds the proof and audits 24 exported
theorem dependency reports. This is a separate mandatory proof gate for changes
to this artifact; ordinary repository `make test` does not run or install Lean.
It rejects dependencies outside the stated standard
axioms, including admitted-result axioms. The trusted boundary is the
pinned Lean kernel/toolchain, imported core/Std proofs and the execution platform,
plus the explicitly stated hardware interpretation above. Exported theorem axiom
dependencies currently report only `propext` and `Quot.sound` (some results
need neither); project axioms, admitted results and
compiler-backed proof shortcuts are forbidden. A theorem about this model does
not prove its premises hold on a real machine.

For orientation, [Achermann et al.](https://arxiv.org/abs/1703.06571) model address
spaces/translation and motivate identifying shared backing rather than equating
addresses with identities; that is not a dynamic revocation proof.
[Rajapaksha et al.](https://past.date-conference.com/proceedings-archive/2024/DATA/734_pdf_upload.pdf)
study stale IOTLB access after unmapping with a QEMU-based exploit/mitigation
experiment; this motivates the premature-completion negative control, not a
claim that this CPU-only abstraction proves an IOMMU implementation.
