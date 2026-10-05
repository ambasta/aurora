# Two-slot policy / short-circuit checkpoint evidence

The [integration record](../../kernel-round-robin-integration-results.md) describes
the implemented boundary, actual gates, preserved failures and limits.
[receipts.json](receipts.json) is the SHA-256 identity index for the separately
retained source, compiler, focused/native and emulator evidence.

The tested source has 566 files. Finalization changes six result documents and
adds three result/evidence documents only; every other tested file and mode is
unchanged. The final source manifest/archive is sealed separately to avoid a
self-referential source hash. Publication preserves all unlisted repository
history. Build products and runtime binaries are not committed as source.

The original native build was archived and verified before emulator writes.
It is retained byte/mode/path-exact, with its inventory and terminal binding.
The final emulator evidence has 1,240 sealed paths and all 178 actual executions;
independent replay additionally verifies the original native archive and final
normal image identities. Private backup storage identities are handoff metadata,
not a substitute for these content hashes or a public download promise.

Historical failed, interrupted and blocked-before-execution stages retain their
original status. No prefix from them is credited to the final fresh aggregate or
single-run emulator acceptance. Sanitizer, configuration-only, emulator and
user-reported Gentoo rebuild observations have their separate scopes in the
integration record.
