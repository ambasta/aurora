# AMD 3.10 event/completion oracle: focused hosted results

## Implementation and scope

The [bounded test-only reference](iommu-event-completion-oracle.md) passed both
complete normal and fatal-ASan/UBSan dormant hosted gates on 2026-10-07.
Independent normative/source review accepted the candidate without correction.
It adds copied code 2/5/6 event decoding, low status bits, single-ring append
arithmetic and an abstract DTE/pages/CompletionWait batch. Model drain facts are
caller-authored assumptions, never hardware observations or reuse authority.

The base was PR63 main `5ca45a87cd477a98c8556b0b57512aca76706142`, tree
`ab147c9bdcaf26d1e09204e34597faaea117dcdf`, with 747 verified files.
The executed 751-file candidate tree is
`856e00d653a2f5b821a1404d1e6b528e099dcd0a`; source manifest SHA256 is
`a9a647ad619038ea8c7c6396f375e3b3f557f0a10e9b8df6a49ae7baca211913`.
Its three changed test inputs are:

- New oracle: `a1e331c0dcf749d7c988fe8160c7dcaa1855d164b5d7455af5879b6738c8afdd`
- New fixtures: `87d780e3de86c9458e0ed503c81d22e832dcaa0354c82e4e51c1323e54c83e5f`
- Existing runner: `f37b1e0a5378f9c0d343b0bf4feefdc3f33a65b2a2d6f1778d3aa2037560ee58`

No production kernel implementation or image changed. The source was accepted
without correction; the first admitted execution completed successfully. The
results/contract/completeness edits afterward are documentation-only. They do
not claim another execution of changed code or transfer results to unrelated work.

## Completed window

The existing entrypoint ran serially from a fresh source copy:

```sh
make --no-print-directory test-dormant-tables
SANITIZE=1 make --no-print-directory test-dormant-tables
```

Original session `3761` exited zero with `HOSTED_GATE_PASSED` at 16:02:34 UTC.
The retained outer record is `hosted-001/run.json`, SHA256
`52feb84d37991a63bda339ed060d9f45c0372dc1e47e13cb832d7c494cfded9c`;
its terminal is `hosted-001/outer.log`. Each owned child session was quiescent
before finalization, with no cleanup signal needed. Total duration was 82.63
seconds: 27.55 seconds normal and 54.77 seconds sanitized.

Each mode completed 91 expected command outcomes:

- 290 new event/completion checks and sixteen new semantic mutants
- 147 retained translation checks and thirteen retained translation mutants
- 65,555 copied actual dormant-constructor comparisons
- 92,306 construction/ownership/independent-byte checks
- 164,313 canonical-decoder checks with zero failures
- Generation-bound-three checks: three complete constructions, seventeen rejections
- Production API, four invalid test/generation configurations, six paired
  private/public member controls, and inspector absence/rejection checks

Every mutant compiled, returned its expected semantic-failure status, included
its named failing fixture, reached its normal final summary and emitted no fatal
sanitizer diagnostic. The 29 mutants in each mode are negative controls, not
unexplained failing tests. Compilation failure or a crash cannot satisfy them.

The normal records are in
`hosted-001/source/build/kernel-dormant-1791388872542221317`;
the sanitized records are in
`hosted-001/source/build/kernel-dormant-1791388900107037370`.
Each retains command outcomes, input hashes, logs, mutant inputs and binaries.
All 230 runner receipt hashes match. All sixteen tracked inputs and all 751
frozen source contents/modes were unchanged throughout execution.

## Tools and resource limits

The observed compiler was Debian GNU C++ 14.2.0-19, executable SHA256
`6b3696e4dcb85e1c949c732a02befa50e3983ecf94ce7e8e58d9d503b954b79d`.
This is a host-tool identity, not proof of compiler correctness. The runner uses
C++23, O1, debug information and Wall/Wextra/Werror. Sanitized compilation adds
`-fsanitize=address,undefined -fno-sanitize-recover=all`. Leak detection is
disabled; no leak-check claim is made.

The reused serial owned-session supervisor imposed a 600-second wall bound,
256 MiB output cap, 8 MiB per-file limit and sampled process-tree limits. Peak
owned output was 45,834,240 bytes; sampled tree peak including its fixed outer
allowance was 503,840,768 bytes. Sampling is not a hard quota. No additional
native aggregate, guest runner or new test framework was introduced.

## Review and remaining qualification

Independent retained-evidence and final-claim review accepted both complete
runs, all 230 receipt hashes, all 58 actual mutant instances, source/tool
identity and quiescent cleanup. Passing these hosted checks establishes only
this bounded reference and the existing dormant dependency tests. It does not qualify pinned QEMU or physical IOMMUs,
validate encoded invalidation commands, observe actual cache/fabric drain,
provide completion freshness or backing-page reuse authority, or implement
live ring recovery, timeout/revocation quarantine or interrupt isolation.
No guest, device BME/IOMMU activation, actual DMA, physical hardware, full native
aggregate, broad-host or performance qualification is claimed.
