# Package identity checkpoint verification

Status: the combined PR16/package source passes the full aggregate and distinct
source/integration review. This is a local functional checkpoint. Publication and
acceptance into a later repository state are separate actions.

This index was added after the aggregate as one documentation-only file. Every
one of the 472 tested project files remains byte-identical; the sealed source
therefore contains 473 files. Earlier candidate-status annotations record the
pre-gate phase; this index records the completed checks without rewriting their
historical source identities.

## Reproduction and source boundary

The [library contract](../../docs/package-identity-contract.md),
[actual module](../../library/package/identity.au),
[example](../../library/examples/package_identity.au), and
[executable independent oracle](../../tests/compiler/package_identity.py) are
source-local links. The [pre-implementation contract](contract-before-implementation.md)
is a required, hash-checked test input.

With the accepted compiler at build/aurorac:

```
make test-package-identity
make test
```

The focused target uses a 128 MiB whole-candidate cap. The aggregate explicitly
selects 512 MiB for its package prerequisite. Both retain a 1 GiB free-space floor
and growth reserve. A separate aggregate supervisor accounts for both retained
integration workspaces. Development --quick/--self-test-only modes do not satisfy
the full gate. No compiler, kernel or UTF-8 implementation change is part of this
package feature.

Accepted compiler SHA256:
`e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e`.
Package module SHA256:
`20ddd8e3f6796d807a6b1854c91a3f49ca37a3f65cc6632dedb0fbbf0a81ffaa`.
Final package harness SHA256:
`93fa3f63b5bad085b7afc31220b1d47d3450eab97bf1114552cf37789ca6a085`.

## Exact base and integration

Base commit: `8eb84de1de8da28707a6ed35f6d26344711d5a32`.
Base tree: `47eefbd3161d80417a55caa7d1a80df15151cf81`.
The verified PR16 seal contains 467 files. All are preserved: 463 byte-identically,
and four shared files as their complete original contents plus package-only
appends. Five new feature/test/contract files formed the 472-input aggregate.
This evidence index is the sixth addition. Compiler/Makefile and every merged
UTF-8 module, test, example and evidence file are preserved exactly.

Literal `make test` passed from 2026-10-04 15:16:12 UTC through 15:28:21 UTC:

- All 472 project inputs and 486 total recorded source/tool/compiler pins stayed
  unchanged before, after and at independent audit.
- Package gate: 5,503 native cases, 199,213 complete-u64 observations, 230 compiled
  native batches and 40 exact-diagnostic rejection executions.
- Preserved PR16 range gate: 2,250 cases, 6,750 complete-i64 observations and six
  diagnostic rejection controls.
- Inherited compiler, IR, module, image, hosted-kernel and semantics targets passed.
- Combined retained-storage peak: 415,264,768 bytes. Adding the 67,108,864-byte
  reserve remains below the 536,870,912-byte cap; free storage remained above 1 GiB.

The distinct review also passed an independently authored 433-case native corpus
with 12,557 full-u64 observations, and four co-import/composition cases with 40
observations. The latter map a token after a multibyte UTF-8 prefix to checked byte
coordinates, parse it, overwrite the owner and verify the copied package facts.
Malformed Unicode, non-ASCII package names and fabricated huge range coordinates
are checked without granting authority. These are separately reported corpora;
repeated full runs are not added together as unique coverage.

Every package target binary has no unresolved symbol, ELF interpreter or dynamic
library dependency. Generated Aurora code is executed natively on Linux/x86-64;
GNU as/ld and a small syscall observation entry remain bootstrap dependencies.
This is finite execution evidence, not a safety/performance proof, a new emulator
or physical-platform qualification, full SemVer, full manifest support, a package
manager, source authentication, resolver or installer.

## Findings and preserved history

The production module did not change after its first successful compilation.
The original example needed an explicit std.array import under the existing
visibility rules. Two early oracle fixtures used unsupported class assignment or
chained receiver syntax; their failures were preserved, then replaced by supported
fixtures with exact semantic diagnostics.

Distinct review found and fixed two test-infrastructure issues:

1. Lexical artifact containment could admit a .. escape. V2 rejects traversal,
   rejects existing symlinks before canonical resolution, and checks containment.
   Separate CLI and self-test controls verify rejection before output creation.
2. A focused 128 MiB cap would reject ordinary make test after inherited products
   accumulated. The aggregate now selects a bounded 512 MiB cap automatically,
   while the focused target retains 128 MiB. The final literal aggregate verifies
   this default behavior without a cap override.

The historical focused and aggregate runs used contained artifact paths; traversal
controls rejected before creating output. Failed attempts remain available;
successful build products were compacted only after complete payload/mode/link
verification. Subsequent gzip-to-xz transcodes verified identical uncompressed tar
streams before removing redundant compressed encodings. The compiler and all
source/input fixtures were retained.

## Companion verification archive

The separate `aurora-package-identity-pr16-verification-20261004.tar.xz` contains
raw commands, source/expected/observed vectors, successful-build archives, original
failed fixtures, input pins and distinct-review reports. Paths below are relative
to that companion, not missing source-local hyperlinks:

- `combined/evidence/package-pr16-aggregate/make-test.json` and its stdout/stderr
- `combined/evidence/package-pr16-aggregate/prepared-inputs.json`
- `review/pr16-final-aggregate-audit.json`, `review/source-review.md`, and the native
  review/composition receipts
- `historical/evidence/package-aggregate*/` for the earlier PR15-based aggregates
- `historical/evidence/success-archive-transcode/` for lossless archive verification
- `author/evidence/package-identity/` for the independent oracle and retained
  first-compile/fixture failures

The final seal/verification manifests describe all source/archive identities and
any post-gate documentation addition explicitly. Earlier PR15 results remain
historical evidence; they are not relabeled as PR16 integration results.
