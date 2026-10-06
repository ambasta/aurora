# Evidence and historical results

Current checkpoint summaries are indexed in [verification](../verification.md).
Current build and test instructions are in [local development](../local-development.md)
and the [developer-test contract](../developer-test-contract.md).

Milestone 001–022 raw outputs, receipt manifests, original failures, review probes
and candidate snapshots are available in the
[unchanged published Git archive](https://github.com/ambasta/aurora/tree/2b1776f13cd02df6588f9e3213815f13c28a71e0/docs/evidence).
The milestone links in the verification record point directly to those files.
They are historical observations, not new results for the current source.

To reproduce an old result, use its recorded tested source revision, compiler,
commands and environment. The archive commit holds the published evidence;
it is not a claim that every milestone tested that commit's later source.
Historical source-checksum commands require the matching source and evidence
snapshot. Do not run them against an evidence-trimmed current checkout.

The [publication-integrity record](../publication-integrity.md) explains older
newline differences and the separate original source-archive authorities.
Those original archives remain unchanged; this Git archive preserves the
published Git bytes and executable modes, not every external original artifact.

Executable tests, reusable live fixtures and frozen package contracts remain in
`tests/`, `fixtures/` and top-level `evidence/`. Historical candidate copies and
review-only reproducers stay together with their original receipts in the archive.
The smaller current checkout does not reduce a full historical Git clone.
