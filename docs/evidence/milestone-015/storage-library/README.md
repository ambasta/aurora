# Storage-library evidence

`integrated/` contains fresh main-checkout compiler/library gate receipts and
exact input/executable identities. `author/` and `independent/` retain isolated
pre-integration execution receipts. The isolated validation/review reports are
historical records whose original paths and commands remain intact.

`baseline-m014.json` records copied pre-edit bytes; `integration-delta.json`
identifies the exact five-file reviewed source/test delta. The main integration
first verified all 36 baseline files. `frozen-tree.json` describes the isolated
artifact tree, not the current combined main repository.

Real mkfs fixture provenance and preserved initial LSan failure are under
`fixtures/xfs-offline` at the repository root. The original mkfs exit status is
unknown; read-only xfs_db and native/oracle observations are recorded separately.
No mount, recovery, feature-support or filesystem-write acceptance is claimed.
