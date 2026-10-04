# Bounded XFS v5 header geometry

Implementation status: integrated and verified in milestone019. Focused author,
independent source/functional review and coordinating aggregate gates passed on
the identified immutable compiler pins. This is a pure-library header-fact API,
not an XFS mount, replay, read/write or device-capacity validation implementation.

The original approved proposal is preserved unchanged in
[xfs-geometry-proposal.md](xfs-geometry-proposal.md), SHA256
`40021cf66fba001094c9f0762475075967b64bd4f55b8be845490ddf37fc5b86`.
Its exact Linux commit, source/blob table, field offsets, arithmetic obligations,
real fixture facts and exclusions are normative for this candidate, with the
explicit local API clarifications below. No upstream implementation is copied.

## Reviewed clarification of first-error order

This ordering is Aurora's local API priority, not a claim about universal XFS
error ordering or every upstream mount validator:

1. Run the unchanged old probe. A rejected probe produces `probe_rejected/none`;
   the nested probe copy retains its original status and raw diagnostic behavior.
   All new raw observations, mask diagnostics and geometry facts are zero.
2. After successful integrity probing, decode raw observations and every extended
   unsupported/unknown mask before selecting a new error.
3. Required legacy version bits, then required features2 bits.
4. Excluded legacy version bits, then excluded features2 bits.
5. NEEDSREPAIR, then other extended mask exclusions and missing local FTYPE.
6. features2 mirror mismatch, then inprogress.
7. Nonzero realtime data, external log, stripe fields, quota/misc flags.
8. Block, inode and directory scalar geometry.
9. AG count/size/address-bit geometry and final-AG length.
10. Representability of claimed data bytes.
11. Zero-realtime ancillary geometry, then inode alignment.
12. Log sector declarations, log size, encoded address/range and AG-header exclusion.
13. `imax_pct` and `shared_vn`, together as `inconsistent_header/misc_geometry`.
14. Success only after all checks pass.

The final miscellaneous check intentionally follows log geometry and data-size
errors. Multiple faults are tested to pin this order. The original proposal's
looser placement of these two bytes does not override this addendum.

With SECTORBIT present, **any** stored log-sector pair other than 512/9 yields
`unsupported_layout/log_geometry`. This is deliberately only profile admission,
not a diagnosis of whether some other pair is coherent in general XFS. With the
bit absent, any nonzero log-sector size/log pair yields
`inconsistent_header/log_geometry`. Absent-bit zero/zero reports effective 512.
There is no general-sector validator hidden behind this narrow rule.

## Source-level API and reports

Callers must directly import both modules because the public report includes the
existing independently defined probe class:

```cpp
import fs.xfs_geometry;
import fs.xfs_probe;

// Exported from fs.xfs_geometry, in namespace fs:
auto inspect_xfs_v5_512_geometry(builtin::span<const u8> bytes)
    -> fs::XfsGeometryReport;
```

No implicit re-export or compiler visibility exception is introduced.
`XfsGeometryStatus` and `XfsGeometryIssue` use the names listed in the proposal.
Report const accessors are `status()`, `issue()`, `probe()`, `raw()`, `masks()` and
`facts()`. Raw observations expose `versionnum()`, `features2()`,
`bad_features2()`. Diagnostics expose copied `unsupported()`/`unknown()` mask
groups with `compat()`, `ro_compat()`, `incompat()`, `log_incompat()` getters.
Facts expose copied `blocks()`, `inodes()`, `data()`, `ags()` and `log()` groups;
each scalar getter has exactly the unit-bearing name in the proposal.

Use named typed locals for copied projections, as required by the existing
language subset. Classes have private fields and ordinary complete public
constructors, at most six source parameters each. The public report has 42 scalar
leaves and three levels of class containment; source/runtime layout observations
are part of acceptance rather than inferred proof from this count.

`facts()` masks every non-success status to a newly constructed all-zero value,
even when a caller manually constructs a failed report with nonzero facts.
Raw observations, masks and nested probe copies remain explicitly untrusted
report data. A freely constructed success report can still hold arbitrary facts;
it is neither a validation certificate nor an I/O capability.

## Implementation boundary

The old probe runs once. Two private helpers return only a two-field verdict:
profile admission first, geometry checks second. This avoids allocating a full
42-leaf report at every rejection branch and keeps the validation frame bounded
under the existing compiler limits.

Only after both verdicts succeed does a private builder re-read fixed fields and
construct the fact groups. These reads use the **same immutable borrowed span**;
there are no callbacks, external reads, mutation or retained/returned references.
The current span is backed by an owned array under the existing language
subset. This reasoning does not cover asynchronously mutable or device-backed
buffers; any future I/O layer needs a separate stable-snapshot contract.
The builder's arithmetic preconditions are established by those checks; it is not
an exported alternative entry point. Tests must reject direct source access to
private helpers. This is a library reasoning boundary, not a new compiler proof
that arbitrary calls to an unchecked helper would be safe.

Every untrusted byte read is at a fixed offset after the old probe establishes
exact 512-byte length. Only CRC and bounded bit-width loops inspect repeated
input; no loop iterates over the declared AG count or data size. Checked arithmetic
remains enabled throughout. Intended malformed-input behavior is a recoverable
report; any signal, compiler crash or timeout fails the test gate. Finite tests
are not exhaustive enumeration of all 4096-bit headers or a total compiler proof.

Some explicit product bounds are mathematically redundant after u32 fields or
prior data-size bounds. Such guards are source-audited obligations, not falsely
reported as killed single-guard mutations. Executable controls target observable
nonredundant guards or clearly named guard families; surviving redundant
mutations do not become claimed test coverage.

## Meaning of an admitted header

The field mask policy admits only the listed header calculations. It does not
promise operations on finobt, rmapbt, refcount, sparse inode, timestamp, extent,
directory, log or any other metadata. It must never become a mount allowlist.
Claimed device sizes are arithmetic facts, not observations of device length.
A correct CRC is error detection, not authentication. No log cleanliness,
transaction reservation, allocation non-overlap, secondary-header applicability,
mountability, recovery, repair or read/write filesystem support follows.

Real fixture provenance remains unchanged: the original mkfs exit code was not
retained, later read-only xfs_db succeeded, package-index hashes matched but the
Debian Release signature was not independently checked. Synthetic CRC-repaired
headers are never described as real filesystems. The canonical ASCII hex and
strict decoder are used without introducing a binary source-transport copy.


## Frozen focused evidence

Module SHA256: `c67c03928e0d4cf5896178906bd447523ec15b57cc95c4ade8b8330305a77864`.
Test SHA256: `fe375d75a7726a538f404f5d2b3f4240065f7d41c3334c104b535b5db2e1c95c`.

The final author aggregate recorded twelve known successful command exits and
stable implementation/test/fixture hashes. On each compiler, the geometry gate
passed 586 header cases and 25,198 complete native u64 observations (42 leaves
plus the combined repeated-call/direct-probe/input-equality check per header).
It also passed 40 static/runtime layout observations, eight copied/fabricated
report checks and 17 specific-stage negative fixtures, each preserving an
existing output artifact. Absent-output cases are covered separately by the
independent eight-fixture/two-mode suite, not by these author rejection runs. A return-span syntax denial is explicitly a
callable-type-surface exclusion, not mislabeled as a lifetime-check proof.

The 51 author mutation controls detected deliberately damaged library copies:
seven produced retained native SIGILL failures and 44 full-output mismatches.
No ordinary unmodified-library header case produced a signal or timeout.
Twenty-four redundant guards are recorded as source-audited obligations, not
claimed single-deletion mutation kills. An initial sparse-alignment mutation
witness still violated another relation; the failed control was retained and its
witness corrected. An earlier negative test expected the wrong wording for an
already-correct span-result rejection; that harness failure is retained too.
The library implementation required no correction.

Independent review separately passed 2,016 byte-distinct headers per compiler:
451 admitted narrow-profile headers and 1,565 recoverable failures. It checked
all 42 leaves, repeated calls, input preservation, copied reports surviving their
local source-array lifetime, fabricated high-bit reports, ten class layouts,
eight privacy/type-boundary fixtures with absent/existing artifacts, and ten
independent mutation controls. These counts overlap author coverage and must
not be added as unique cases. The complete report is preserved with its pins,
commands, limits and initial unsupported-LSan failure receipt.

Existing test-storage gates passed on both pins: 254 storage model cases plus
15 native observations on the preserved real header and 17 canonical-transport
controls. The new running example returns exactly 42; its assembly is identical
from release and instrumented compilers. Compiler implementation and old probe
remain unchanged. Full main-repository aggregate and kernel acceptance are
separate parent gates; no new kernel run is claimed by this focused evidence.

The generic new test accepts future compiler builds while recording and checking
run-stable hashes. `--compiler-sha256` optionally enforces the exact acceptance
pin. Release compiler AS is capped at 512 MiB, native/tool AS at 128 MiB, CPU at
10/11 seconds, regular files at 8 MiB and core files at zero. Tools have 30-second
wall limits; native cases default to 15 seconds. Fixtures have at most four
headers and 64 KiB source; the observed largest normal fixture is 18,841 bytes.
Only `--sanitized-compiler` omits the compiler AS cap for sanitizer shadow
reservation. `ASAN_OPTIONS=detect_leaks=0:halt_on_error=1` is explicit; unsupported
leak checking is not passed. Captured pipes have no separate memory cap. The
instrumented compiler does not make emitted Aurora programs ASan-instrumented.
