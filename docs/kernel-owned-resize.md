# Bounded raw kernel owner replacement resize

Candidate, not yet qualified. No new guest result is claimed.

The next dependency is the real CPU-only kernel adapter's existing OwnedBytes
resize helper. The observable gate is failure-atomic replacement with independent
host adversaries, exact six-helper graph/link admission and independently reviewed
linked stack/image evidence before any guest. Complete ByteBuffer graphs are not
admitted by this change.

## Contract

The private 32-byte owner ABI, four fixed allocation records, sixteen PageLease
pool pages, 3,072-byte Region metadata cap, supervisor mapping, 16 KiB stack and
1 MiB arena remain unchanged. An empty existing record becomes private preparing
storage. Public allocation is not called: final logical quota is checked as
new_length <= quota - (used - old_length), and staging does not charge used or
live_allocations. Region::page validates backing and that record's actual lease;
it does not mistake preparing storage for a committed logical owner. Descriptor
lookup exposes only live records.

Validation precedes every shortcut. Canonical failed owners never revive;
negative requests return false; same-size valid requests return true unchanged,
even when all four records are occupied or identities have exhausted. Changed
sizes require a free metadata slot, a fresh identity and representable counters.
Old and new rounded page sets must coexist. Page or metadata exhaustion can reject
shrink as well as growth. Resize to zero needs a free metadata slot but no new page.

Every new page is fully zeroed/read back, including padding. Every old lease is
preflighted; copied prefixes use checked logical page spans without assuming
physical contiguity. The preserved prefix is min(old_length,new_length). Shrunk
suffixes cannot revive after regrowth. After all recoverable work succeeds, old
pages are scrubbed/read back and released, then replacement identity and logical
accounting commit in the synchronous, single-CPU, nonreentrant adapter.

A changed-size success increments successful_allocations and releases once,
keeps live_allocations constant, and updates last identities. peak_used observes
committed logical use; peak_held_pages includes successful old+new staging.
Recoverable failure leaves all committed metrics, old descriptor and old bytes
unchanged. It scrubs/releases any acquired staging prefix and restores empty
record hygiene. Free-page contents and allocator lease generations need not be
unchanged after rollback.

Bad lease, scrub or unexpected release failure is terminal: both transaction
records are retained, including a zero-page peer, the Region faults permanently,
and the endpoint never returns or unwinds. Old bytes are not promised unchanged
after terminal retirement failure. Remaining leases cannot be reclaimed or
forgotten; unrelated owners/foreign holders remain untouched. Hosted fault
observers inspect state only and exit without unwinding.

## Acceptance and limits

The focused real-adapter tests cover boundaries, quota, metadata/full-pool and
partial-acquisition failure, fragmentation, fresh identities, stale/foreign/failed
and malformed descriptors, whole-page zeroing, retained transactions and cleanup.
Fatal host ASan/UBSan instrument C++ only, never generated Aurora assembly.

The exact object gate requires six helpers: allocate, at, set, drop, borrow_length
and resize. Graph definitions remain closed. Actual ELF-link controls must show
real resize resolution and reject unrelated runtime imports/mixed graphs. The
linked stack proof includes generated expression/cleanup pushes, resource/span
records, exact C++ frames and direct call edges, and the four-level page verifier.
The unchanged gate is normal peak +512 fault reserve <=15,360 of16,384 bytes;
the decoded fault path itself must fit512. Historical bounds are not current proof.

Independent source and exact admission/stack review precedes the narrowly extended
owned-bytes guest. Only bounded owned-bytes, runtime-span and normal regressions
are intended, with exact normal-image restoration and current-source receipts.
This is not general heap ownership, ByteBuffer graph admission, mutable escaping
views, DMA/IOMMU/device activation, physical qualification or a safety proof.
