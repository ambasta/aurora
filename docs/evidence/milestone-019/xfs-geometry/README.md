# Bounded XFS geometry integration evidence

The reviewed nine-file delta was integrated after exact per-target baseline checks.
There were no target baseline exceptions. Ninety captured existing compiler,
library and ordinary-test inputs, including the original probe and M018 UTF-8
contracts, stayed unchanged. Concurrent authorized kernel/root-Makefile/scripts
work is outside that assertion; this is not a globally unchanged main snapshot.

The delta adds fs.xfs_geometry, its runnable example, test and precise contract,
plus the preserved approved proposal, observed fixture facts and source-reference
corroboration. Existing-file changes are compiler/Makefile (test registration and
flags) and library/README.md (new API plus stale historical-status corrections).
No compiler implementation, original probe, mutable-view or image-build change
was made by this integration.

## Acceptance receipts

Author isolated final aggregate: twelve known exit-zero commands and stable input
hashes. On each compiler, the new gate passed 586 header cases / 25,198 raw u64
observations, 40 layout observations, eight copy/fabricated-report checks, and
17 exact-stage negative fixtures preserving existing output. Those author
negatives do not claim absent-output coverage. Fifty-one deliberate mutant
copies were detected; 24 redundant guards are source-audited obligations.
Seven controlled mutants signal SIGILL, 44 differ in output. Ordinary baseline
header cases never signal or time out. Mutation signals are failures of the
intentionally damaged copy, never successful malformed-header handling.

Independent implementation review: 2,016 byte-distinct inputs per compiler,
451 narrow-profile successes and 1,565 recoverable failures, every report leaf,
input equality, copied-result lifetime, ten class layouts, eight privacy/type
fixtures with absent/existing outputs, fabricated reports and ten independent
mutation controls. These suites overlap; do not sum them as unique case counts.
The unchanged original report is independent/REVIEW.md.

Separate follow-on review covers final metadata, test recipe and optional compiler
pin controls. It found and corrected one wording error: only the independent
suite exercised both output-artifact modes. No implementation/test-code correction
was needed. The original implementation report is not retroactively expanded;
see follow-on-review/ADDENDUM.md and its independent audit/manifest.

Integrated main gates: all ten commands exited zero on exact inputs. Both new
geometry targets and old test-storage targets passed release/instrumented pins.
Old storage includes 254 model cases and 15 real-fixture native observations plus
17 canonical hex controls. The new example returns exactly 42; assembly is
identical from both compiler pins. Parent full repository/kernel acceptance is
separate, and no new full kernel-mode run is claimed by these library receipts.

Module SHA256:
c67c03928e0d4cf5896178906bd447523ec15b57cc95c4ade8b8330305a77864
Test SHA256:
fe375d75a7726a538f404f5d2b3f4240065f7d41c3334c104b535b5db2e1c95c
compiler/Makefile SHA256:
e1d7a88a42a591175d5792ecd76dc68e387c35c55be1f4a5ac24ecee456ec75a
Original probe SHA256:
9474dceea9c3dda66d5566396480e88979c6ea28c8d857b944f24e2e70603284
Release compiler SHA256:
14cbaa33b69b81240b5828b6893f4c150eeaa9a11d95a83726d32e417c1f8980
Instrumented compiler SHA256:
805567b1cac1e535d0951b4ddbc02b598d9bb546bea718f7afb74d482dab94bf

## Provenance and limitations

Primary-source semantics are pinned to Linux commit038d61fd642278bab63ee8ef722c50d10ab01e8f.
The API priority and log-sector admission clarifications are explicit local policy.
Admitted flags mean header interpretation only, not operation/mount support.
Facts are claimed arithmetic, not observed device length; CRC is not authentication.
There is no mounting, log replay/cleanliness, allocated-metadata validation, repair,
DMA or filesystem read/write claim. The builder re-reads a current owned-array
readonly span; asynchronous/device-backed mutation needs a separate future contract.
Publicly constructible reports are ordinary data, not capabilities or certificates.

The canonical real header remains the exact text transport and raw512 digest.
Original mkfs exit was not retained; later xfs_db was read-only and successful.
Package-index matching is not independent Debian Release-signature verification.
Repaired synthetic headers are never described as real filesystems.

All original failures remain preserved: initial direct-import smoke note, wrong
negative diagnostic expectation, unsuitable sparse-alignment mutation witness,
and independent initial unsupported-LSan runs. Only instrumentation's compiler
AS cap is omitted for shadow reservation; native/tool limits remain. Regular-file
limits do not bound pipes, and emitted target code is not ASan-instrumented merely
because its compiler is. No finite corpus is an all-header or whole-compiler proof.

Author, original independent and follow-on originals are archived byte-exact
outside distributed source. Their distribution.json files identify archive hashes
and omitted generated binaries/objects/assembly/raw output. Consolidated JSON
preserves parsed records; exact original bytes remain archived. No binary was
normalized or re-encoded into text. Archive tooling is not added to main.
