# Milestone020: bounded concrete nested generic values

Functional acceptance passed locally on 2026-10-03. This record separates author,
independent compiler and coordinating integration evidence from archive integrity
and any later remote publication. No network or publication action is represented
by this checkpoint.

## Accepted scope and gates

The implementation accepts fully concrete nested template-id value arguments to
syntax depth four. Class-containment depth four, 64 leaves, 64 template definitions,
256 total instances including children, and capacities 1..64 remain independent
bounds. Existing nominal identity, transitive visibility, defining-module lookup,
inline construction and independent value copies are reused. The real bounded
token/source-range example returns 42. There is no new IR/ABI, dependent template
body expansion, recursive instantiation, deduction, owner/reference argument,
heap/string implementation or kernel functionality.

- Author: complete release and fatal ASan/UBSan compiler targets exited 0 on frozen
  implementation inputs. The 313 focused checks and 960 typed IR checks are part
  of those aggregates, not separate unique populations.
- Independent compiler review: 78 cases per compiler, 31 native successes and
  47 rejections; independent 694-source arithmetic differential control. The same
  repeated compiler cases and overlapping corpora are not additive coverage.
- Parent: exact-base adoption of 18 paths, fresh release rebuild to the reviewed
  SHA256, complete `make test`, then `runtime-span`, `runtime-pin-fault`, `normal`
  UEFI profiles, all exit 0. Normal image restored. All 359 captured source inputs
  and 183 external pins remained unchanged during those runs.
- M019 is the historical full 166-mode kernel checkpoint. M020 has three fresh
  integration spots, not a fresh full suite or physical-device qualification.

Release SHA256: `e47a9f89369e4c0399f79f7da88cb5b4f099d7c8aa709bf108e594d7920e33c6`.
Instrumented SHA256: `78379d081bfae56608a6a60e72bc290e9abd68e88b1a9c3e96f93d25b007cfb5`.

## Evidence map

- `nested-values/receipts/VERIFICATION.md`: original detailed compiler acceptance,
  commands, tool versions, resource limits, counters and retained failures.
- `nested-values/receipts/INTEGRATION.md`: historical pre-adoption handoff; its
  pending-integration language is superseded by this checkpoint's parent results.
- `nested-values/review/independent-compiler/REPORT.md`: unchanged independent
  source/adversarial report, accompanied by exact probe generators and receipts.
- `nested-values/tmp/*.log`: only four selected original development logs; this
  is not a copy of the candidate's temporary output tree.
- `parent/`: exact parent stdout, status files, before-input manifests, adoption
  record, compiler pin and after-verification result. `parent/README.md` explains
  the subsequent documentation-only changes.
- `curation-manifest.json`: exact size/hash binding for 145 candidate files and
  15 parent files copied without newline normalization. Raw CRLF and ANSI bytes
  in emulator logs are preserved.
- `candidate-package-verification.json`: safe unique relative regular-path audit
  of 153 ZIP entries, all matching their originals. The 152 hash-listed evidence
  members plus their manifest explain the package's two different counts.
- `omitted-generated-products.json`: 10 excluded receipt products and 307 other
  generated files, all with exact hashes/sizes and retained external originals.
  Six retained archive-member JSON manifests describe omitted native products;
  they must not be interpreted as files included in this source distribution.

Original candidate ZIPs/tarballs, binaries, generated assembly, source copies and
full build/tmp products stay outside this tree. No third-party reference extract,
credential or private key was added. The archives referenced by historical records
were not changed or deleted. Source/test implementation identities remain pinned;
final public status prose is recorded separately in `parent/final-documentation.json`.

## Limits and later archive status

Finite tests and review do not prove whole-language safety or performance.
Instrumented compiler execution does not instrument emitted Aurora native code.
Build caps and the `-g1` IR-test debug accommodation, with fatal sanitizers retained,
are documented in the original receipts. Failed attempts remain nonzero historical
observations, not passes. No full system, AMD hardware or active DMA claim follows.

The source-distribution audit is a separate, bounded stream audit over this final
source, with a 1 GiB payload ceiling. Its exact archive hashes, inventories, Git
tree, process exit and independent final review live beside the external M020
archives. The archive builder alone may add `archive-mode-representation.json`:
that single note records the inherited test script's archive-only 0700-to-0755
Git representation and never changes the original live permission. Prior M019
archives remain immutable. Functional acceptance does not imply publication.
