# Synchronous readonly method span parameters — unverified candidate

This draft extends nonconstructor methods with readonly byte-span parameters.
It is not accepted until source/native, malformed-IR, handwritten-ABI and direct
regression gates pass fresh independent review. Runtime layout and helpers are
unchanged. No new kernel capability or general object reference is introduced.

Arguments evaluate left-to-right after resolving receiver identity. Each span
acquires authority at its evaluation position and retains it through the call.
After all arguments, the receiver must still be live and mutable calls require
an unborrowed root. Self-append rejects even for empty views and disjoint windows.
Readonly arguments may alias one another; const receivers may receive their own
views. Distinct buffers may share a region without aliasing their owners.

Callee parameters are invocation-only capabilities with exact parent provenance.
They can be read and synchronously forwarded but never stored in fields, rebound,
returned as argument-derived views or converted to ownership. Existing span
results remain tied exclusively to one verified direct receiver owner field.
Constructors, ordinary owning-function span signatures, mutable spans, owning
method parameters, nested owning fields and method overloads remain unsupported.

MethodCall records positional span spills independently from copied-object
snapshots. The verifier checks exact types, active roots and parents, vector
shape, zero entries at other positions, and final receiver authority. Every
span record remains 56 bytes. Packed methods use R10 for receiver and R11 for
arguments; class/span results additionally use RAX for their hidden destination.
These private entry points are never exported as scalar C-callable boundaries.

## Bulk append

ByteBuffer.try_append_bytes(input) accepts only a disjoint readonly input.
Invalid destinations return false, including for empty input. Valid empty input
succeeds without allocation. Overflow is checked before adding input length.
Growth makes one failure-atomic resize to max(required, saturated double current
capacity), with a zero-capacity geometric target of one. All writes follow the
successful reserve; logical length commits only after all bytes are copied.
Recoverable failure preserves size, capacity, bytes and committed accounting.
Fail-stop faults do not unwind or promise rollback; completed argument side
effects are outside the operation's rollback guarantee.

## Observable acceptance

Append an array window and a different buffer's logical view into one destination,
verify complete bytes across growth, observe injected allocation failure leaving
state unchanged, and reject self-append and later argument invalidation. Exercise
all private ABI parameter positions, mixed copied/scalar arguments and hidden
results with independent literal-layout canaries. Compare existing kernel graphs'
assembly before deciding whether additional guest regression is required.
