# Byte effects over conserved authority (B)

B is a **one-page, single-copy-per-use interpretation** of unchanged A. It is
not a proof of the native copy routine, page-table decoder, compiler, DMA,
weak-memory execution, or the binding from a source-language request to an A
use. The latter binding remains an explicit obligation: numeric request bounds
cannot manufacture authority.

## Boundary and state

All source, destination and control addresses inhabit one canonical `Nat` cell
space; bytes are `Fin 256`. A supplies an arbitrary finite managed allocation.
`Config.Valid` requires the registered source interval outside that **entire**
allocation, and control cells outside both. Numeric descriptors are nonempty,
within the source extent and unsigned-64 bounds, and fit one 4096-byte physical
destination page. These are mathematical physical addresses, not a proved
interpretation of virtual aliases or native page tables.

Source stability is scoped to **one admitted source-loan trace and its initial
heap**. The native registered endpoint buffer is overwritten between requests;
registration does not make its contents eternally immutable. Such writes require
another initial interpretation, or a future explicit source-loan protocol. Not
every native execution, or every A trace, is claimed to lift to B.

`Admission` constructs actual request, registration, grant delivery, publication
and work submission from an arbitrary reachable owner gate and local free
footprint. `Entry` instantiates a numeric interval and derives concrete use,
grant and outstanding work checks for `beginCopy`. It assumes neither `Enabled`
nor a byte-safety conclusion.

Each use ticket has at most one retained cursor and a permanent spent marker.
This deliberately restricts A's sequential stream to one copy per ticket.
`payload` reads the **current** source byte and advances one cell; it does not
consult a global safety predicate or read from a saved snapshot. Retained
metadata/work must justify its A effect. Other A writers may interleave on their
authorized cells, but cannot issue arbitrary writes under a held copy ticket.
Only actual `finishOne` of that ticket is prohibited while held: close and queued
work drainage remain possible. Done/faulted cursors must be released before a
separate protocol completion, receipt or authority return.

Fault preserves the partial heap and authority. It does not roll back bytes,
close a scratch window, manufacture a completion receipt, or run cleanup.
Control writes are explicit events in the same heap, not hidden non-payload
stuttering. B does **not** model window-open/window-close states or prove the
scratch-PTE protocol.

## Proof families and status

`Aurora.B.invariant` (`Completion.lean`) proves the combined induction over every admitted lifted
trace from reachable A authority and an initial heap. `trace_erases` projects it
to A; the converse is deliberately not claimed. `copied_prefix` and
`completed_copy` derive initial-source equality from current reads and source
stability, including arbitrary admitted interleaving. `frozen_trace_heap` derives
byte stability from frozen authority along syntactic `NoReuse` traces; it does
not assume that frozen cells are unwritten. Phase coherence, retained work and
metadata, exact full-heap replay and permanent spent markers are also checked.

Global heap framing excludes **all actual write events**, not merely one
cursor's destination. A different disjoint writer legitimately changes its own
bytes. Copied-prefix ownership lasts while the cursor remains held. A frozen
byte theorem is lifetime-local: physical reuse may subsequently change bytes.

`Witnesses` constructs reachable A root/publication/admission, a successful
two-byte copy, a one-byte partial fault, and close-before-drain followed by an
actual payload step. `Interleaving` admits two real writer uses and changes a
disjoint byte while the first cursor remains held. `Mutants` distinguishes guard/invariant counterexamples
from a same-ticket corrupting write followed by the original second payload
step, producing a wrong completed copy. Small fixtures are Lean-kernel checked;
they are not a native execution receipt.

## Actual implementation obligations left open

- `kernel/uefi/mapping-authority.hpp:267–306,487–498`: registered-source page
  validation and loan acquisition. PR353 enforces physical exclusion natively;
  there is no proof that the page-table decoder denotes B addresses or that
  native exclusion is maintained under every hardware actor.
- `mapping-authority.hpp:793–842`: whole-chunk loop, actual destination
  directory/ticket resolution, bounds, volatile copying and partial failure.
  A native/page-loop-to-B simulation, destination ownership binding and
  source-loan lifetime correspondence remain unproved.
- `kernel/uefi/kernel-space.hpp:248–268`: scratch PTE writes and invalidation.
  B separates their physical footprint, but does not prove mapping lifetime,
  TLB semantics, alias absence or a control-write implementation refinement.
- `formal/publication/SourceBinding/RequestPolicy.lean`: checked first-request
  bounds and exact arguments are useful upstream facts, not a descriptor/use
  capability. Their connection to `Aurora.B.admit_begin_copy` is not yet proved.

No new product behavior or hardware support is supplied by this layer.

## Acceptance

Run `PATH=<pinned Lean 4.24.0>/bin:$PATH ./verify-b.sh` from
`formal/reclamation`. The gate checks the exact toolchain and actual exported
kernel axiom reports, allowing only `propext` and `Quot.sound`. No `sorry`, custom
axiom, `native_decide`, raised proof limits or native result is used as proof.
Whole-repository/native qualification is separate and revision-specific.
