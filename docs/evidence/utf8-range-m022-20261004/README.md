# Read-only UTF-8 scalar-range checkpoint evidence

This library-only delta is based on accepted PR15 main commit
`b151aec6c4d98adfb542da91e5a34cff279dc832`, tree
`f82a724d2b1bbe69aa4021bef8689d546acd8b9a`.
The 430-file baseline inventory is preserved in `baseline-inputs.json`.
Seven copied pre-existing temporary artifacts were kept separately and excluded
from the product source inventory; no accepted source was modified in place.

## Exact implementation

- Reviewed source freeze v2: 434 files, SHA256
  `401f19344f0f33dc56a686833ee3e19f310e6657b2240a3db9d584e4c24aa731`.
- Reviewed source archive: `readonly-text-source-v2.tar.gz`, SHA256
  `09ce6bd126a55e8fed813f31f23a87adbb22bc50c57b3f1b930bcb54f2debff7`.
- New library module: SHA256
  `7e05a05ec4c622737804fdd8aac62e7328539c2280e5b9c0dc17d27a83d51030`.
- Corrected author runner: SHA256
  `8c8f4a9bac782bcf24ffeda01099c98ec8fa3643efa83d3bb6f9b5ff953821ec`.
- Accepted unchanged M022 compiler: SHA256
  `e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e`.

Only `compiler/Makefile` changed under compiler; all compiler implementation,
kernel, old library APIs, and old tests are byte-identical to the accepted base.
Final status/evidence edits follow the frozen review and do not alter those
implementation or test pins.

## Gates

The corrected focused gate passed 2,250 native cases / 6,750 exact signed 64-bit
status/offset/count observations and six diagnostic-specific rejection controls.
It verifies whole-window malformed-suffix rejection, relative coordinates, every
one-byte input, scalar/window/range boundaries, empty selections, copied/forged
reports, input stability and misuse rejection. The executable example returns 42.
The Python oracle strictly decodes/slices/re-encodes text independently of the
Aurora byte walk.

The unchanged UTF-8 gates passed: decoder/validator 406 native checks plus its
existing exhaustive scalar/short-input loops; encoding 186 native checks,
24 rejection compilations and its existing scalar/surrogate loops. The fresh
full top-level `make test` then passed, including another complete range gate,
existing compiler/IR/module/storage tests, image checks, hosted kernel/UEFI tests,
and final 630-case semantics run. Counts from repeated and independent runs overlap.

`parent-make-test.json/stdout/stderr` preserve the full aggregate invocation,
terminal exit 0, source-freeze identity and compiler pin. All 434 source hashes and
all available inventoried tool hashes remained unchanged. Expected successful
Python unittest output is retained in stderr. Peak allocated bytes were 360,194,048,
under the approved 384 MiB total cap with 1 GiB global free-space floor. The supervisor
preserved command output and stopped-on-failure behavior; no gate was weakened.

The [independent report](independent-review.md) is copied verbatim, SHA256
`491deb3f723edef30a535cf029a72429359ab8ca688eea109a5fd994f13918f3`.
It accepts the frozen library-only candidate after 588 independently generated
native cases / 1,764 exact i64 observations, ten rejection controls, full source,
archive, and parent aggregate audits. No product defect was found.

## Failures and retained artifacts

The first author run passed all native cases but failed an expected diagnostic
substring. Three short rejection probes exposed the other overly general expected
diagnostic strings. Only those four strings changed; native cases and library
code did not. `initial-runner-hash-recovered.py` is exactly hash-checked against
the first run's manifest, with the recovery method documented. All initial failure
logs/fixtures remain preserved. Independent reviewer fixture corrections and their
retained failed attempts are described in the verbatim review.

Completed duplicate artifacts were losslessly compacted to preserve the disk
budget. Every file's path, byte count, SHA256 and mode was verified from each tar
before removing its live duplicate. The independent reviewer then reverified the
corrected focused, prior-UTF8 and aggregate-range archives. Complete source,
assembly, expected/observed native bytes and per-command receipts remain in the
companion verification archive under their original paths. No failed evidence was
discarded. The large build products/archives are not embedded in product source.

## Limits

This is a read-only scalar-index-to-byte-range observation API, not a string
container, grapheme/normalization/display-width implementation, terminal, heap,
returned borrow, optional feature, compiler milestone, XFS extent feature,
filesystem service, safety proof, or equivalent-C performance qualification.
There is no new emulator or sanitizer acceptance; QEMU is absent from the current
PATH and actual emulation was not attempted. Historical M022 qualification remains
historical. Local review does not imply main-branch adoption or remote publication.
