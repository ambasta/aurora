# Test-only AMD IOMMU models

The independent test-only models in `tests/amd310-translation-oracle.hpp` and `tests/amd310-event-completion-oracle.hpp` interpret copied bytes and caller-supplied assumptions. They perform no MMIO, DMA, publication or reclamation. Their reference is [AMD 48882-PUB revision 3.10, February 2025](https://kib.kiev.ua/x86docs/AMD/IOMMU/48882-3.10.pdf), SHA256 `cd7559334b3f46a72d56e9f2fac786fcbf5d6a2c41e7770a46fcacc080bc8a12`.

`make test-dormant-tables` and its `SANITIZE=1` variant check handwritten raw-byte fixtures, real constructor snapshots, existing ownership controls and deliberate semantic mutants. A mutant must compile, reach its intended failing fixture and normal summary, and emit no sanitizer diagnostic. Model outcomes never substitute for actual hardware/guest completion or page-reuse authority.

## Translation semantics

### Fixed semantic profile

The input is a stable copied device-table span, a copied 4 KiB root span with its
synthetic physical base, the raw nine-bit Size field, a 16-bit requester ID, one
IOVA and read/write access. This is point-address interpretation, not a
whole-interval validator. Zero-byte reads and atomics are outside the API.
Supplied bytes are bounded host snapshots; they do not
establish identity, ownership, live mappings, memory visibility or backing
lifetime. No DMA data access is performed. Data-page ownership is not an input:
a translation result only describes the encoded address and rights.

The modeled IOMMU is enabled, unsegmented, without guest translation, PASID,
ATS/pretranslated requests, exclusion, page migration or virtualization. HAD is
zero. Only ordinary memory, Mode 0 identity and Mode 1 with 4 KiB leaves are
supported. MSI addresses `0xfee00000–0xfeefffff`, HT special addresses
`0xfd00000000–0xffffffffff` (HTRangeIgnore=0), and translated addresses in those
ranges return unsupported. This is deliberately not a transaction classifier for
all possible platforms. Special requests and other device/request classes must
not be submitted as ordinary requests by a caller.

For V=1, the accepted DTE subset contains only V/TV, Mode, the host root pointer,
IR/IW and DomainID. Other DTE bits return unsupported, not guessed architectural
faults. V=0 bypasses ordinary memory regardless of the remaining DTE payload.
TV=0 faults while ignoring Mode/root/IR/IW. Mode 0 ignores the root and applies
DTE permissions. Modes 2–7 are unsupported; the oracle does not pretend that
all unsupported encodings are architecturally valid or architecturally faulting.

A Mode 1 leaf must have NextLevel=0 and FC=U=0. Present-leaf bits 63 and 8:1
are ignored or inactive A/D state. Bits 58:52 are reserved in the fixed
TMPMSup=0 profile. Other next levels/leaf attributes are unsupported. PR=0 is
checked before all remaining payload, including reserved bits and next level.
The abstract address capabilities are VAsize=64 and PAsize=52. Mode 1 uses the
52-bit page fields; V=0 and Mode 0 addresses above `0x000fffffffffffff` return
unsupported rather than claiming physical-width behavior. Mode 1 high addresses
still take the defined upper-address fault. No hardware PAsize capability or
allocation-width claim is inferred from the constructor's 32-bit allocation bound.

A declared Size `n` bounds RID to `(n + 1) * 128` entries, independently of copied
backing length. Out-of-table RIDs fault before any fetch; a missing in-range DTE,
an unmatched root base, or a missing full root page is unsupported test input,
never a fabricated hardware-read fault. DTE bytes beyond the declared length
cannot enlarge the architecture's table. Mode 1 rejects IOVAs at or above 2 MiB
before selecting a leaf. Read and write rights each AND the DTE and leaf bits.
An allowed result preserves the complete cumulative rights, even the other
access right which was not requested.

### Results and fault meaning

A result is one of bypass, translated address with cumulative rights,
`IoPageFault`, or unsupported-profile/input. Fault information is descriptive:
EventCode=2, DeviceID, attempted IOVA, DomainID (zero if unavailable), I=0,
TR=0 and GN=0. It is not an encoded event entry and does not claim logging,
interrupt delivery, ring capacity or actual target-abort execution.

PR, PE, RW and RZ are optional values. An absent value means no field value is
claimed. Out-of-range RID has no DTE, so DomainID=0 and no PR/PE/RW/RZ claim.
TV=0 has PR=1 and meaningful RW, but no PE because IR/IW are invalid. A high
address has PR=1 and PE from the valid parent. A non-present leaf has PR=0 with
PE/RW/RZ omitted. Permission faults use PR=1, cumulative PE and actual RW.
Present-leaf reserved-bit faults additionally have RZ=1. RZ is not inferred for
unrelated causes. Logging-suppression controls and other event fields are outside
this profile.

The oracle chooses to complete a supported one-level walk before testing leaf
permissions. Hardware may stop earlier at a restrictive parent; this model does
not impose a universal priority among simultaneous faults. Single-cause golden
fixtures establish the required architectural outcomes. A separate multifault
fixture checks only the explicitly selected walk's cumulative PE reporting.

## Event and completion semantics

### Copied event profile

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

### Single event-ring effect

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

### One abstract invalidation batch

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
