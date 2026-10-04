# Bounded package graph verification index

This source adds a library-only dependency consistency/order candidate on exact
PR19 commit 7e3fe6da7f5ddff8d0d580e429035c4a64196e31, tree
db79101fe6f0dc45a21625594396bade8ea2c2ff. The accepted M022 compiler SHA256 is
e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e.

The [pre-implementation contract](contract-before-implementation.md), SHA256
2272fba3b7163550f5dabef95c5b54c0d1039063b84545ef0c0b20f93928e01c,
is frozen and is a required independent-oracle input. The [public contract](../../docs/package-graph-contract.md)
records the exact supported API and bounds.

The first native four-package example compiles and returns complete u64 value 42,
checking a permuted shared/transitive dependency graph and independent copies
after input mutation. No target host runtime dependencies were observed. Initial
contract review also independently recovered every member of the early source
archive. Full oracle and corrected actual Make replay pass 5,548 native cases,
333,671 complete-u64 observations and 60 diagnostic-specific absent/existing-output
rejection runs. They replay one corpus and are not additive counts. Separate
handwritten review passes 47 cases/2,230 full-width observations and 8 negative
compilations. Fresh full make test and final independent integration seal remain
pending; focused results alone are not final acceptance.

Development receipts, early recoverable source, independently frozen oracle and
review material are kept in the companion verification archive rather than all
being copied into the publication delta. Preserve every failure, source revision
and historical checkpoint; later success does not relabel earlier evidence.

## Independent reference and retained failures

The [independent reference](oracle/reference-v1/reference.py), SHA256
6a54b890a7b33abd378c9ca7a0de05c179cb4448c2fc2daaf5a33c677aeafa42,
is a required source input, included with the test harness. The final focused
harness SHA256 is 2c26a26428778db55f77bf64ce8a81ca5c83558bf7addb7cd122964f2802760a.
Its model enumerates whole topological permutations in canonical-name order,
independently of the production ready-node selection implementation.

One early rejection fixture expected the wrong exact diagnostic; the actual
compiler rejection was correct. A distinct review then found that development
corpus-freeze mode checked its expected compiler hash too late. The host harness
now checks the supplied hash before every mode return and enforces reserve/floor
limits on corpus creation too. Wrong/malformed-pin, resource/finalizer and original
failure-preservation controls pass. No graph implementation edit was required.
Pre-fix sources, receipts and recovery archives remain historical; the corrected
full Make replay supplies the focused acceptance input. No old run is relabeled.
