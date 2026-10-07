# Test-only AMD 3.10 event and completion reference

## Dependency and gate

After the independent [translation oracle](iommu-translation-oracle.md), the
next dependency is distinguishing ordinary-memory fault reporting from completion
of earlier invalidations. `tests/amd310-event-completion-oracle.hpp` interprets
stable copied values and explicitly supplied test assumptions. It has no
production includes, MMIO access, physical dereference, table publication,
DMA authority or reclaimable-page token. It is included only by hosted tests.

Acceptance requires independent normative/source review, then the existing
normal and fatal-ASan/UBSan `make test-dormant-tables` gates. They retain the
existing translation, constructor, ownership, decoder, privacy and generation
checks and add handwritten event/completion fixtures and sixteen isolated
semantic mutants. Independent source review and both complete hosted modes
passed. The [results](iommu-event-completion-oracle-results.md) retain the exact
source/tool identities and scoped evidence. Independent retained-evidence and
final-claim review accepted this bounded checkpoint.

## Copied event profile

Exactly one 16-byte little-endian record is accepted, including an unaligned
host copy. Code 2 is an ordinary-memory IO_PAGE_FAULT with no PASID, guest,
ATS/translation request, interrupt, user/execute prefix or virtualized context.
Out-of-profile fields, reserved payload and all other event codes except 5/6
return unsupported; that is a model limit, not an invented hardware error.

The decoded requester, DomainID, attempted DVA and all flag bits are raw values.
The record cannot reveal which fault condition was encountered, whether an
invalid DTE supplied meaningful permissions, or how far a walk progressed.
`FaultExpectation` compares only optional fields explicitly defined by a known
fixture. It never turns absent PR/PE/RW/RZ into false. PR=0 fixtures intentionally
carry nonzero uninterpreted PE/RW/RZ payload. The existing translation oracle is
used by a fixture only through its independent descriptive result; neither
header includes the other, and no production encoder/decoder is used.

Table 57 defines I=0 for memory and DomainID at +04 bits15:0 when GN=0; DomainID
is zero when unavailable. PR-qualified meaning and RW's additional TR=0/I=0
conditions do not permit a decoder to reconstruct a fault cause or priority.
The test suite imposes no unique winner among simultaneous hardware faults.

Codes 5 and 6 decode the command-error kind and encoded command address.
COMMAND_HARDWARE_ERROR accepts only non-SNP Type 1/2/3. Table 62 qualifies
address validity with SR=0 without supplying an SR field in this entry; the
model deliberately labels the address raw rather than asserting its validity.
Hardware error register fallback, suppressed logs and other error kinds are not
modeled. Unknown and unsupported events can never become completion signals.

## Single event-ring effect

`Status` reports raw low-bit meanings: EventOverflow=bit0, EventLogInt=bit1,
ComWaitInt=bit2, EventLogRun=bit3, CmdBufRun=bit4. Higher bits remain unmodeled;
ring and batch operations reject them. No interrupt-delivery or W1C register
access is implemented. A copied ComWaitInt=1 can be stale and does not identify
which command completed.

`append_event` models one append's arithmetic/status effects, without reading
or writing ring data. EventLen 8 through 15 describes 256 through 32768 entries;
head and tail are aligned byte offsets. Equal pointers are empty. Advancing
16 bytes to the head would consume the reserved unused slot, so a full ring
preserves its pointers, discards the new record and sets EventOverflow. A valid
append advances only tail modulo the buffer length and sets EventLogInt. It
never creates ComWaitInt. Disabled or overflowed logging discards the record;
existing status remains otherwise unchanged. EventLogRun need not clear at the
same instant as overflow, so no instantaneous run-bit change is fabricated.
Malformed offsets, lengths and unmodeled status profiles return unsupported.

No consumer, copying race, coherent write visibility, allocation ownership,
software pointer publication, dual-buffer mode or overflow-restart procedure
is implemented. Empty/full arithmetic is not proof that a live log is complete.

## One abstract invalidation batch

The model has exactly three typed command meanings, fetched in this order:
INVALIDATE_DEVTAB_ENTRY, INVALIDATE_IOMMU_PAGES, COMPLETION_WAIT. The commands
are assumed to target the intended requester/domain, with GN=0, no PASID/ATS,
no peripheral IOTLB and f=1. This is not a raw command decoder or validation of
encoded targets, page ranges, cache contents or a hardware queue. Fetching all
three commands never means their execution completed.

Caller-authored facts separately establish DTE-cache invalidation, page-cache
invalidation, matching old read drain and matching old write drain. Page-cache
invalidation cannot execute before the DTE-cache fact. DTE invalidation does
not stand in for invalidating translations. The model chooses a simple schedule
where drain facts are recorded after page-cache invalidation; it does not require
all hardware to perform independent work in that order. Each drain fact asserts
all applicable section 2.4.11.2 fabric requirements, not a measured transaction
count. The model neither observes nor verifies those assertions.

Only a fetched wait with all four facts can complete. That transition produces
a modeled 64-bit store when s=1 and sets ComWaitInt when i=1. All four s/i
combinations are allowed. An s=1 target must fit the model's aligned ordinary
52-bit system-memory-address profile; this checks no actual backing allocation.
With s=0 the unused target is uninterpreted. No output constitutes authority to
unpin, reuse or reclaim memory. No generation or freshness proof is added.

A modeled ordinary fault can be logged while the batch remains pending and
does not stop its commands. A stale status bit and a new ordinary event do not
finish the wait. A command error before wait fetch stops further fetches even
if its log record is discarded. That bounded error transition represents a
settled stopped state, with CmdBufRun=0; transient stopping and the fate of any
already-fetched commands are not simulated. It cannot fetch a later wait or
produce completion. An error after wait fetch is unsupported because modeling
concurrent waits and errors would require a broader contract. Further event
reporting remains possible after the command stop. Restart, retry, batch reuse,
timeouts and uncertain revocation remain unsupported.

## Evidence and negative controls

Normative source: AMD 48882-PUB revision 3.10, February 2025,
[the supplied PDF](https://kib.kiev.ua/x86docs/AMD/IOMMU/48882-3.10.pdf),
SHA256 `cd7559334b3f46a72d56e9f2fac786fcbf5d6a2c41e7770a46fcacc080bc8a12`.
The PDF is not distributed. Checked references use printed page numbers:

- Section 2.1.3, pp53-54: partial walks and fault information
- Figure 56/Table 57, pp152-154: IO_PAGE_FAULT encoding and field applicability
- Sections 2.5.6-2.5.7, Tables 61-62, pp158-160: command errors and stop-fetch rule
- Section 3.4.16, pp248-250: status; low-bit field definitions are on p250
- Sections 2.5-2.5.1, pp139-141: event tail, one unused slot, overflow and restart
- Section 3.4.1, p210 and section 3.4.15, pp247-248: length and pointer encoding
- Section 2.4, pp122-123: FIFO fetch versus concurrent execution and command stop
- Section 2.4.1, Figure 44/Table 34, pp123-125: CompletionWait ordering and s/i/f
- Sections 2.4.2-2.4.3, pp125-128: separate DTE and translation-cache invalidations
- Section 2.4.11, pp138-139: DTE ordering and matching-read/write fabric requirements

Fixtures cover literal RID/domain/address asymmetry, field definedness, all eight
ring sizes, wrap/fullness, lost records, stale status, fetch/execute separation,
independent drain prerequisites, s/i effects, error-stop behavior and unsupported
profiles. Sixteen isolated mutants target I, DomainID, unknown-field comparison,
status confusion, tail, fullness, overflow suppression, prior-DTE ordering,
DTE/page confusion, fetch/completion confusion, each drain, s, i, error stopping
and ordinary-fault/completion confusion. Each must compile, fail its intended
fixture, reach its normal terminal summary and emit no sanitizer diagnostic.

This reference does not qualify the pinned QEMU implementation or any physical
IOMMU. No production kernel/image, guest execution, device BME, IOMMU enable,
interrupt remapping/isolation, hardware drain, timeout/quarantine protocol or
performance claim is added. Those remain prerequisites before activation.
