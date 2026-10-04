# Storage design verification receipt

Date: 2026-10-03 UTC. Workspace: the supplied cloud task directory.
Scope: documentation provenance/traceability and a finite host-only durability
model. No target Aurora source, controller, filesystem mount, XFS image or
physical disk was changed or tested.

## Commands and results

Run from the `aurora-storage-design` package directory:

```sh
python3 model/test_durability.py
python3 -O model/test_durability.py
python3 model/check_traceability.py
python3 -O model/check_traceability.py
python3 model/test_traceability.py
python3 -O model/test_traceability.py
python3 -m py_compile model/*.py
```

Python: 3.12.14. Final model runs: **14 tests pass** both normally and with
optimization, preserving the explicit runtime checks. Logs are
`host-model-tests-v2.txt` and `host-model-tests-optimized-v2.txt`.

- Safe two-fence model: 181 crash-image evaluations, zero invariant violations,
  four evaluations that recover a new version without an acknowledgement.
- Deliberately broken single-final-flush: 684 evaluations, 126 diagnosed
  violations. A full commit can persist while its manifest/data are absent.
- Deliberately broken premature acknowledgement: 186 evaluations, three
  durability violations. The acknowledgement can survive in the observation
  while its commit does not survive on modeled media.

These counts are evaluations over overlapping prefix states in the bounded
two-sector abstraction. They are not counts of disjoint physical faults or
proof coverage. Mutant failures are expected positive controls, not unexplained
failures of the chosen protocol. `model/README.md` defines all assumptions and
important missing mechanisms.

The structural checker passes exact input bytes/hash, source sections 1–56,
adapted sections 1–57, all 56 traceability rows plus the explicit XFS addition,
A1–A8, and valid S0–S11/X0–X3 stage references. Its log is
`traceability-v2.txt`, with an optimized run in `traceability-optimized-v2.txt`.
The hardened checker uses explicit failures, never removable Python assertions.
Eight checker-control tests pass normally and with an optimized test runner;
each invokes the checker both normally and with `-O`. They cover an unchanged
package, same-length mutated input, missing/duplicate trace rows, an unknown
referenced gate, unknown adapted section and unknown/duplicate roadmap stage.
Logs are `traceability-negative-controls-v2.txt` and
`traceability-negative-controls-optimized-v2.txt`. Structural validation is not
semantic review.

## Independent review finding and correction

The parent independently reran the original 12-test model normally and with `-O`,
then found that a None terminal outcome was indistinguishable from a missing
OutcomeWindow entry. A second identical-key call could overwrite that terminal
result. The exact pre-fix reproduction is preserved in
`model-review-null-outcome.txt`; passing original tests had not covered this case.

The corrected helper has an explicit narrow result type: positive u64 durable
commit sequence. It rejects None, bool, floats, strings, out-of-range integers
and other unsupported outcomes before mutating state. Capacity is an integer
1–64; request/expiry and digest bounds are explicit. Two permanent tests cover
the reproduction, first-wins behavior and invalid types/ranges. The final 14-test
runs pass. The defect and fix apply only to this host model; no target filesystem
implementation or user data was involved. Parent re-review of the corrected
package is recorded by the parent separately.

The parent also identified that the initial traceability script's bare assertions
were disabled by `python -O`, which could print PASS without validating anything.
The hardened checker above fixes this and adds negative controls in both modes.
`traceability-v1.txt` and the parent's original `parent-verification.txt` are
pre-hardening receipts and are retained unchanged, not relabeled final evidence.

## Provenance and limits

Original user input: 26,360 bytes, SHA-256
`72ff3628f4d8043560c5a2055b507e4881178b29fc95a9212f6955804aa64bf6`.
`package-sha256.txt` identifies the package files at the final author checkpoint;
`aurora-context-sha256.txt` captures the local project context files at receipt
creation; concurrent project work is not included in the model's verification.
The supplied Aurora directory has no Git metadata, so no source commit is invented.

Only primary source research and Python standard-library execution were needed.
mkfs.xfs and xfs_db were absent; no xfsprogs differential test ran. Exact-source
upstream XFS references for the future parser slice were retrieved through a
read-only GitHub connector and are identified in `xfs-v6.16-provenance.json`.
No remote publication, credential change, software installation, device mount,
raw NVMe command, kernel aggregate rerun or physical qualification occurred.

S0 is a design/model artifact, pending the parent's final integration decision.
All implementation stages S1 onward and all XFS support stages remain open.
