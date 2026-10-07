# Test-only AMD 3.10 translation oracle

## Dependency and gate

Before installing any dormant table, independently model ordinary-memory
translation from raw bytes. The existing canonical decoder verifies a narrow
constructor policy; it cannot evaluate restrictive parents or ignored payloads
that violate that policy. The new `tests/amd310-translation-oracle.hpp` has no
production includes, encoder calls, canonical-validation prerequisite, physical
pointer conversion, publication operation, completion token, or hardware access.
It is included only by hosted tests.

Acceptance requires independent source review, followed by the existing
`make test-dormant-tables` and `SANITIZE=1 make test-dormant-tables` runners.
They must execute the handwritten architectural fixtures, actual-constructor
comparison, existing ownership/decoder/privacy/generation tests, and thirteen
isolated mutants that compile but fail the corresponding semantic fixture.
Independent source review accepted the implementation after tightening the
identity-address profile bound and mutant normal-terminal checks. The
[focused hosted results](iommu-translation-oracle-results.md) record passing
normal/fatal-sanitizer runs and the preserved initial compile failure. Independent
retained-evidence and final claim review accepted this bounded checkpoint.

## Fixed semantic profile

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

## Results and fault meaning

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

## Evidence and independence

The normative source is AMD 48882-PUB, revision 3.10, February 2025:
[the user-supplied PDF](https://kib.kiev.ua/x86docs/AMD/IOMMU/48882-3.10.pdf),
SHA256 `cd7559334b3f46a72d56e9f2fac786fcbf5d6a2c41e7770a46fcacc080bc8a12`.
The PDF was checked independently before implementation and is not distributed.

- §2.2.2, p63 and §3.4.1, p208: 32-byte DTE indexing and `(Size+1)*4096` bytes
- Table 7, pp71–74 and Table 8, p74: V/TV, Mode, root, IR/IW and DomainID
- §2.2.3, p81 and Tables 15–17, pp82–84: high address bits, PR, page fields and cumulative rights
- Table 44, pp144–145: ordinary untranslated memory IO_PAGE_FAULT conditions
- §2.1.3, pp53–54 and Table 57, pp153–154: partial walks and meaningful fault fields
- Table 3, p53 and §2.2.9, p120: excluded special/MSI address classes

`tests/kernel-iommu-oracle.cpp` uses independent handwritten bytes, all sixteen
parent/leaf permission combinations for both accesses, RID 255/256/65535 at
Size=1, maximum/minimum table sizes, `0x3000` versus `0x203000`, zero/nonzero
PR-clear payloads, V=0, TV=0, Mode 0, ignored fields, unsupported inputs, and fault
field applicability. Mutants remove requester/high-address/PR checks, each
parent permission, V/TV semantics, Mode 0 rights, root binding, reserved-leaf
checking, transaction-class exclusion, memory-event I and DomainID reporting.
Each must produce its expected fixture failure and reach its normal final
summary. Sanitizer diagnostics are rejected; a compile error, crash or earlier
fixture failure followed by undefined behavior cannot satisfy the gate.

`tests/kernel-dormant-oracle.cpp` copies bytes actually emitted by DormantTables,
then interprets them without calling its validator. It checks every other RID,
RO/RW mappings and offsets, holes/high addresses, DomainID and snapshot stability
after never-published cancellation. The trusted test adapter is separate from
the oracle. Existing ownership tests remain separate evidence; architectural
translation alone cannot prove ownership or DMA isolation.

No production kernel code or image is changed. Event-ring, invalidation/completion,
interrupt isolation, publication visibility, timeout and uncertain-revocation
quarantine qualification remain prerequisites to any activation. No device BME,
IOMMU enable, guest, physical-hardware or performance claim is added.
