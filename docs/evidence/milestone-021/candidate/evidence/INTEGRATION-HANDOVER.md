# M021 integration handover

Isolated candidate ready for parent-controlled adoption. No main/kernel changes
were made. Both full compiler gates and independent release/fatal-sanitizer review
passed. Main remains on the accepted M020 binary until parent adoption.

Candidate root: /workspace/scratch/48c5de6446f8/aurora-m021-function-candidate

## Exact adoption set

`change-manifest-final.json` contains exactly 18 changed/new paths and each exact
baseline/candidate SHA256. For an absent baseline path the value is null. Verify
all baseline identities immediately before applying the patch; stop on any drift.
`source-only-change.patch` modifies only those 18 paths, excludes generated output,
and passes `patch --dry-run -p1` against the accepted base. It does not replace the
canonical completeness matrix: its candidate fragment must be reconciled into
that matrix by the parent as an integration-documentation change.

- Baseline binary: e47a9f89369e4c0399f79f7da88cb5b4f099d7c8aa709bf108e594d7920e33c6
- Release binary: d866abc707349ca8652a966800d38bd920bd41345997f08e4b849c9bfc3b7b64
- ASan/UBSan binary: 423db8bcf0642263e445582107c73f967decdc13132f2bd98a973fce2db03d0f
- Compiler-source manifest: compiler-source.sha256
- Compiler-source manifest SHA256: 7d073cd0ec17d7da500baea3b66e6cf810fe21af235d6e99cc5ea4924df4d65e
- Source-only patch SHA256: 9db68ad990d4b07bc9b61959a98e869671c10113ff0479814d8cd3358da7f550

`INTEGRATION-SEAL.json` pins the adoption manifest, sources, patch, all final gate
receipts, review reports, baseline differential and resource summary.

## Passed gates

- Complete release and fatal host ASan/UBSan compiler `make ... test` targets,
  each exit 0. IR uses the explicitly permitted debug-only -g1 accommodation.
- Focused 227 fixtures / 349 executions: 81 native returns, 24 exact traps,
  122 negative fixtures in both output states. Additional focused fatal-abort
  replay passes. Repeat runs are overlapping coverage.
- 964 direct IR cases; 10 exhaustive controls and all existing native IR ABI,
  numerical/library/module/host-I/O suites.
- Independent 46-fixture release review and fatal replay, plus 22 absent-output
  checks each; both reported defects fixed, no unresolved findings.
- Baseline: 232 M020 contract fixtures (153 byte-exact accepted outputs,
  79 matching rejection statuses), plus 36 program-source comparisons; overlapping.

## Evidence and limitations

`VERIFICATION.md` is the full report, including preserved initial privacy and
review failures, test-diagnostic/harness fixes, intentionally deferred validity,
resource controls and preliminary uncapped small observer-build exceptions.
No safety proof, generated-code sanitizer instrumentation, performance parity,
new ABI, fresh 166-mode emulator run or physical hardware claim is made.

Successful generated XFS/UTF8 trees are losslessly archived with verified
path/mode/byte hashes and exact original paths; only duplicate expanded successful
outputs were removed under parent approval. Failures and historical compiler pins
remain. Final candidate is approximately 184 MiB; largest recorded size is
355,665,735 bytes and minimum recorded filesystem free space 1,541,660,672 bytes.

Parent owns exact-base adoption, fresh `make test`, the three existing UEFI spots,
restoration of a final normal image, and integration documentation. Record those
as spot gates rather than a fresh full 166-mode run.
