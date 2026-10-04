# Bounded package graph: final aggregate results

The complete fresh `make test` passed on 2026-10-04, from 18:26:32 to
18:53:08 UTC. The independently reviewed native graph implementation remains
unchanged from its first successful compile. This result record supersedes the
pre-aggregate pending labels in the frozen candidate documentation; it does not
retroactively change any earlier receipt.

## Exact scope and source

- Baseline PR19 commit: `7e3fe6da7f5ddff8d0d580e429035c4a64196e31`.
- Baseline tree: `db79101fe6f0dc45a21625594396bade8ea2c2ff`.
- The later verified PR19 main merge, `1e3499e6a72c6a392a74e70c770724a3ec019080`,
  has that same tree; remote state must be rechecked before publication.
- Accepted M022 compiler SHA256:
  `e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e`.
- Graph source SHA256:
  `f9371489d899b02b114e141583e222f617139c4ac9591475df105877cefc3bf6`.
- Final focused/aggregate harness SHA256:
  `2c26a26428778db55f77bf64ce8a81ca5c83558bf7addb7cd122964f2802760a`.

All 520 tested project source files and all 537 captured source/tool/controller
pins stayed unchanged through the aggregate. The copied accepted compiler was
used unchanged; no compiler rebuild or compiler feature was needed. This document
is the sole post-gate source addition, giving a 521-file final source inventory.
Independent final review and exact archive/publication manifests identify that
append separately. No main write or remote publication is implied by local tests.

## Executed evidence

The full graph gate passes **5,548 native cases, 333,671 complete u64 observations,
and 60 absent/existing-output rejection runs**. It covers every simple directed
graph through four vertices, smaller catalog permutations, larger adversarial
catalogs, missing/conflicting exact pins, cycles, whole-set error precedence,
empty catalogs, copied results, poisoned constructors, eager fallbacks, privacy,
import and lifetime controls. All 63 native batch archives retain complete inputs,
binaries and expected/observed vectors. The independent model enumerates complete
orders lexically instead of mirroring the production ready-node algorithm.

The focused full Make replay and final aggregate replay the same corpus; their
counts are not additive. A separately handwritten reviewer gate passes 47 cases,
2,230 complete observations and eight diagnostic-specific negative compilations.
Generated binaries have no undefined symbols, ELF interpreter or dynamic target
library dependency. GNU tools and the observation entry remain host bootstrap tools.

Inherited compiler/IR/module/image/hosted-kernel and semantics gates passed too.
The aggregate includes package.identity (5,503 cases / 199,213 complete observations
/ 40 rejection runs) and package.manifest (20,022 cases / 1,827,671 observations /
58 rejection runs), plus the accepted UTF-8 and XFS prerequisites. This library-only
change adds no emulator mode or physical-device qualification claim.

Full aggregate receipt SHA256:
`704af229f3f92fab552292337264375160f2cb35490a456abb714b3c2668237d`.
Fresh graph-gate receipt SHA256:
`87b1811688833eb2965d8b5f17a80f47bf4dc946c27872b80b7f9931516bd78f`.
Independent aggregate-audit SHA256:
`272ea9c0a85fa5fe87341005557e1adcd6e8fd10d72bcffbf7edcdc039e4c438`.
The actual original execution session ended with exit 0. Exact commands, complete
logs, tool versions, source identities and all raw observations are retained in
the companion verification archive; finite tests are not a safety/security proof.

## Resource and recovery boundary

The focused candidate used a 256 MiB cap. The separately approved aggregate
accounted for both author and fresh integration roots under a 512 MiB cap, with
64 MiB reserved and a 1 GiB free-space floor. Measured initial allocation was
48,562,176 bytes; peak allocation was 412,196,864 bytes. Peak plus reserve remained
below the cap, and free space at completion was 28,049,002,496 bytes.

Completed UTF-8 output duplication was retired only after actual successful recipe
fences, absent writers, stable membership and exact recoverable archive verification.
Post-terminal compaction likewise requires complete success, stable source/tool pins,
no active/future consumers and exact byte/mode recovery. A transformed nested archive
must reproduce its original compressed bytes and hash. Every failed attempt remains
retained; accepted baseline artifacts are untouched.

The first negative-fixture failure was an exact diagnostic expectation mismatch.
Separate review also found a host-harness compiler-pin check occurring after a
corpus-freeze early return; validation now precedes every mode, with wrong/malformed-
pin no-output controls. Freeze-mode resource/failure-finalizer guards were hardened.
Prelaunch review added fail-closed temporary-directory containment. None required a
graph production edit. Earlier sources, failures and corrected receipts remain
separate historical records.

## Supported mechanism and limits

See the [exact API/contract](../../docs/package-graph-contract.md) and
[frozen pre-implementation specification](contract-before-implementation.md).
The module validates an entire caller-supplied set of zero to eight exact-version
manifests and computes a deterministic dependency-first permutation. It rejects
duplicate roots, missing names, exact-version mismatches and cycles before exposing
copied successful facts. Lexicographically smallest ready canonical ASCII names
make identity order independent of catalog and dependency-line order.

Results are ordinary forgeable data values, not parsing certificates, snapshots
across separate calls, trust claims or capabilities. Source retrieval, general
version/feature solving, scripts, build execution, filesystem/network authority,
installation and authentication remain outside this bounded prerequisite.
