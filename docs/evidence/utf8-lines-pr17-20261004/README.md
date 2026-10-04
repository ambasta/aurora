# Read-only UTF-8 line scanner evidence

The frozen implementation is accepted after independent native/source review and
a fresh full top-level aggregate. This is a library-only checkpoint. No product,
test, or build correction followed the frozen gate; the final changes are result
and evidence documentation only.

## Baseline and tested source

This work started from the exact 473-file sealed PR17 package-identity checkpoint:
commit `d8222ad235fa218629266aa28e7b42ba87f4ee5e`, tree
`b8369852f9b316680bb24ee54ed228f1b4b5a095`. PR17 remained open/unmerged when checked
for publication planning; main adoption is not assumed. The byte inventory in
`baseline-inputs.json` is the local recovered source subset, not permission to
replace an entire remote tree. Every unlisted historical remote path must survive
incremental publication.

The tested v1 freeze contains 477 source files, SHA256
`a50baa8175acae6b308d1ab3212ff796c6298139b76f91d2fec8062b93549c8f`.
The early source archive has SHA256
`8a4c528340bb79a604e74e80602785b5762121d962c992064370905810381623`.
All archive members were byte/hash/length/mode checked against live source.

Accepted M022 compiler SHA256:
`e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e`.
Only the compiler Makefile's test wiring changes; all compiler implementation,
kernel, old UTF-8 APIs, package identity code, and previous tests are unchanged.
The exact module/test/docs delta is in the freeze inventory.

## Passed gates

- Author line gate: 1,815 native cases, 7,260 complete i64 observations, and seven
  diagnostic-specific rejection/output-preservation controls.
- Executable example: exact native return 42 for CRLF, empty LF, and unterminated
  multibyte content with explicit end-of-input and positive progress.
- Existing decoding/validation, scalar encoding, and scalar-range Make targets
  passed separately on the accepted compiler. The unchanged range gate reports
  2,250 cases, 6,750 exact i64 observations, and six rejection controls.
- Fresh full top-level `make test` passed through compiler, IR, module, storage,
  image, hosted kernel/UEFI, final 630-case semantics, and the package-identity
  prerequisite: 5,503 cases, 199,213 full-u64 observations, 40 rejection executions.
- Independent review: 875 cases, 3,500 exact i64 observations, 15 compile-time
  rejection controls, and one checked-bounds SIGILL control. Complete repeated
  scans check every line tuple and progress, including maximum-size LF/CRLF input.

These repeated and independent populations overlap. They are not added together
as unique test cases or a safety proof. The gate source defines the finite corpus.
No general Unicode line-breaking or terminal interpretation is claimed.

`parent-make-test.json/stdout/stderr` preserve the exact command and terminal exit 0.
Every one of the 477 frozen source files and the accepted compiler were unchanged
before/after. Available tool executable hashes also stayed unchanged. Successful
Python unittest output remains in stderr. The aggregate pre-admitted 416 MiB of
growth, enforced 512 MiB total storage and 1 GiB free floor, and recorded peak
411,308,032 allocated bytes. Completed success duplication was losslessly compacted
without weakening or skipping a gate. The supervisor source is retained.

The [independent report](independent-review.md) is copied verbatim, SHA256
`003749f5bb64ffc86846b6500bd4ddd4eb7ae4a1a3ed82067042cb401f1aadf2`.
Its separate aggregate audit verifies the terminal command/logs, exact source
hashes/sizes/modes, compiler pin, and all 7,518 archived UTF-8 aggregate members.

## Preserved failures and companion evidence

The first author attempt passed all 1,815 native cases, then failed a diagnostic
expectation for calling a private helper. Actual rejection was `private function
is not imported`; the expected substring was too general. Only that expected text
changed before the complete successful rerun. `utf8_lines-first.py` retains the
exact initial runner, checked against its initial manifest. The failure log and
first manifest remain preserved. No product code changed.

The companion verification archive retains generated source, assembly, binaries,
full expected/observed output bytes, per-command receipts, original failures,
independent probes, and compacted successful artifacts. Each compacted file's path,
SHA256, length and mode was checked from its tar before removing its duplicate;
independent review rechecked the archives. Large generated products are excluded
from product source, not discarded as evidence.

## Scope

This observes the first consumed UTF-8 line of a final byte window using the
explicit LF/CRLF policy. A subsequent malformed line is checked on a subsequent
call. The result is forgeable copied data, never a borrow, validity certificate,
owner binding, or indexing authority. Empty-line progress and failure masking do
not confer whole-file validity; callers can explicitly validate the whole input.

No new optional, extent, framebuffer, compiler, kernel, allocator, returned view,
stream buffer, escape execution, grapheme/display-width, normalization, performance,
physical-device, or emulator/sanitizer qualification is included. QEMU was absent
from the inspected PATH; actual emulator execution was not attempted for this
library-only change. Publication is separate from local functional acceptance.
