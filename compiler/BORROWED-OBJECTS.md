# Synchronous borrowed owning-object parameters

Status: the fresh focused source/native, independent IR, handwritten ABI and
regression gates passed. Exact identities and limits are recorded in the
[results](../docs/borrowed-objects-results.md). This is not general reference
support or a safety proof.

## Dependency and observable gate

Reusable free serializers need to append to the caller's existing `ByteBuffer`
without owning it. The bounded increment is one leading named `T&` or `const T&`
parameter, for a concrete already-supported owning class. The observable consumer
is `std.json_write::append_json_scalar`: it composes the existing copied scalar
encoder and one atomic bulk append. Allocation-free `std.json` keeps its existing
imports and does not gain an allocator dependency.

This is not general C++ reference support. Additional reference parameters,
temporary/projected arguments, reference locals/fields/results, reference
function templates or overloads, ownership-transfer boundaries and pointer syntax
remain unsupported. Remaining arguments retain existing scalar/enum, readonly
span and copied-class semantics. Results are scalars/enums or copied classes.

## Authority and argument evaluation

The first argument names a complete owning root or the current named borrowed
formal. The loan begins before any later argument is evaluated, and remains live
through the synchronous call. A mutable loan excludes every other access to its
root during argument evaluation. Precompute a size or other observation before
passing it as a later argument. Shared loans permit readonly aliasing but cannot
mutate, move or end their root. Distinct owners in the same region are disjoint;
empty or disjoint windows of one owner retain the same root identity.

Callees can invoke public methods and forward the named formal synchronously.
Nested mutable reborrows suspend the parent's independent access until release.
Const authority cannot be upgraded. Views produced by public const methods remain
tied to the borrowed root and must expire before mutation or function exit.
The formal grants no lexical private-field or private-method privilege.

A loan never transfers ownership, creates region authority or registers the formal
for cleanup. No extraction, reassignment, move, drop, field storage or borrowed
return is added. Local owners and copied argument snapshots retain existing
normal cleanup. Fail-stop faults do not unwind.

## Typed IR and machine boundary

`AcquireObjectLoan` and `ReleaseObjectLoan` are verifier-only operations with
positive loan identities, exact root/lifetime provenance, nominal class identity
and mutable/shared authority. A loan may authorize one `BorrowedCall`, then must
be released. It is not a scalar value or stack address. Active loans must match
at control-flow joins. No normal return may retain one.

The bound formal reuses receiver-like hidden storage, marked explicitly as a
borrowed free parameter. Direct receiver-field instructions are forbidden for
that mode. Method access uses actual visibility metadata. Only a verified public
span-returning method may derive the formal's internal owner-field provenance.

The existing private method ABI is reused: R10 holds the root; packed copied/span
arguments use R11; copied results use RAX with a packed record, or R11 without
one. Scalar arguments retain their existing registers. Hidden saves, stack
alignment/probes, 56-byte spans and 32-byte owned descriptors remain unchanged.
Source symbols cannot expose this as a scalar C-callable boundary. Existing
resource-graph checks and receiver call-cycle restrictions include borrowed calls.

## Failure and verification scope

`append_json_scalar` validates/encodes before mutating and appends a local fixed
array window in one `try_append_bytes` operation. Invalid scalars do not mutate
output. Recoverable allocation failure preserves size, capacity, bytes and
committed accounting. Completed argument side effects are outside rollback.
This does not establish atomicity for a future serializer that makes multiple
appends; that needs its own sizing/reservation or partial-progress contract.

The focused gates cover source/native alias/evaluation/privacy/cleanup
cases, independently constructed malformed IR, handwritten incoming/outgoing ABI
checks, injected allocation failure, copied-result independence and affected
method-span/owning/span/value/library regressions. All 29 existing kernel source
graphs, including native client disposal, produce identical assembly with the accepted old and new compiler. No new guest run is
claimed. Nested owning layouts, complete native qualification, performance and a memory-safety proof are separate.
