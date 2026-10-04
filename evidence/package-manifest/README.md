# Declarative package manifest verification

Status at author-source freeze: final focused execution and distinct source/oracle
review pass. Acceptance of the later combined source additionally requires a fresh
unchanged-input aggregate and final independent seal. Its final outcome is recorded
in `final-verification.md`, added only after those integration checks complete.
Earlier candidate annotations and receipts are historical source-specific records.

## Source and reproduction

- [Frozen initial contract](contract-before-implementation.md)
- [Current library contract](../../docs/package-manifest-contract.md)
- [Native module](../../library/package/manifest.au)
- [Native example](../../library/examples/package_manifest.au)
- [Independent executable oracle](../../tests/compiler/package_manifest.py)

With the accepted M022 compiler at build/aurorac:

```
make test-package-manifest
make test
```

The focused target uses Python -B -O and its default whole-candidate 256 MiB cap.
The aggregate recipe selects 512 MiB for this prerequisite, while a separate
supervisor accounts for the retained author and fresh integration together, with a
64 MiB reserve and a 1 GiB free-space floor. The --quick and --self-test-only modes
are development controls, not substitutes for full execution.

Compiler SHA256:
`e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e`.
Manifest module SHA256:
`ac844af8982dbbabfeb874b0a31c9f946cc04171fff4973db4fea050d53326bd`.
Final harness SHA256:
`402de696328fa754c0e415858538d5b27cc843ab1d9be66422d3234b3568e1e1`.

The author baseline is published PR17 checkpoint
`d8222ad235fa218629266aa28e7b42ba87f4ee5e`, tree
`b8369852f9b316680bb24ee54ed228f1b4b5a095`. Its 473 local source files were
verified against the sealed publication input. The planned combined source will preserve the later UTF-8 line checkpoint only
after its independent seal; this module does not depend on that API. Future publication must apply only a narrow reviewed delta and preserve
all unlisted remote historical paths.

## Focused execution and independent review

The final direct replay and literal focused Make command each passed:

- 20,022 native cases and 1,827,671 complete-u64 observations
- 251 compiled/assembled/linked freestanding native batches
- 29 exact compiler-rejection fixtures run with absent and existing outputs,
  totaling 58 normal rejection/output-preservation checks
- Empty Make stderr, exit zero, and unchanged compiler/source/tool/Make pins
- No unresolved symbols, ELF interpreter or dynamic target-library dependencies

Repeated corpora are not added together as unique coverage. Tests use independently
authored Python byte-regex/line grammar, arbitrary-precision integers and name-set
uniqueness against actual x86-64 execution. They cover both APIs at every byte
substitution position, all truncations of the 615-byte profile, signed extremes,
late error masking, duplicate/self names, version overflow, constructors, copies,
eager fallbacks, helper shadowing and privacy/lifetime/import rejection.

A separate reviewer authored 49 manifest/window cases with 4,508 full-u64
observations and 53 constructor/ownership/binding cases with 2,429 observations,
plus 24 absent/existing-output rejection runs. It independently re-read every final
oracle batch, raw output vector, compiler-rejection record and pin. The maximum
eight-dependency profile and 4,096-byte input owners were exercised.

The first example returned complete u64 42 after owner mutation. GNU tools and a
small Linux write/exit observation entry are host bootstrap dependencies; the
module supplies no target runtime, IO, allocation, resolver, installer, scripts,
network/filesystem authority, cryptography, package trust or performance proof.
No new emulator or physical-platform qualification is claimed.

## Reproduced defects and retained history

No behavioral parser defect was reproduced. Its initial compilation rejected missing
borrow_bytes wrappers; the original source/diagnostic and corrected native run
are retained. Initial oracle/review negative fixtures also needed exact diagnostic
matcher corrections; these failures remain distinct from passing replays.

Distinct review reproduced two substantive independent-test defects:

1. Python splitlines() stripped a CR from a dependency line and incorrectly modeled
   dependency-only CRLF as valid. Exact LF splitting preserves the CR for rejection;
   explicit regression and optimized self-tests now enforce the frozen grammar.
   The original reference freeze and revised freezes are retained.
2. An enforcing budget check in finally could hide an original failure and prevent
   writing the failed-run manifest. Finalization now records measurements/resource
   errors separately and attempts the receipt without masking the original error.
   Independent fault injection covers combined, resource-only, measurement and
   receipt-write failures.

The earlier full run passed 19,948 cases / 1,823,126 observations before the final
receipt hardening and additional constructor controls. It remains an earlier
harness gate rather than being relabeled as final acceptance.

Successful batch artifacts are compacted only after exact member count, byte
length, mode and SHA256 readback. Completed full-run archives may replace their
compression encodings with exact verified raw tar streams in a combined xz archive.
Recovery maps retain original encoding hashes; payload and tar-stream bytes remain
recoverable. All failed artifacts remain intact. This is evidence preservation,
not source package authenticity.

## Companion evidence

The separate verification archive contains the early source backup, all frozen
reference/harness versions, original failures, exact commands and statuses, raw
expected/observed vectors, ELF audits, reviewed success compactions and independent
review reports. In the author evidence tree, useful names are:

- `oracle-authorship.md`, `oracle-final-summary.json`
- `oracle-make-final-command.json` and `oracle-make-final/manifest.json`
- `oracle-full-01-verified-success.*`, `oracle-full-02-verified-success.*`
- `review/source-review.md` and the vector/finalization/compaction audit records

The integrated aggregate and final seal identify their own exact source/tool pins;
a focused pass is not a substitute for that later gate.
