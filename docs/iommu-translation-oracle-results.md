# IOMMU translation oracle: focused hosted results

## Accepted implementation and scope

The test-only [AMD 3.10 Mode 0/1 oracle](iommu-translation-oracle.md) passed the
existing dormant hosted runner normally and with fatal ASan/UBSan on
2026-10-07. It interprets stable copied bytes independently of production masks,
encoders and canonical validation. No production kernel implementation or image
changed. These results do not establish DMA isolation or authorize activation.

The starting source was PR61, main `ead19843993e6338e48f5d794d67bec5907f1c63`.
Independent source review checked the pinned AMD PDF and cleared the bounded
semantics, constructor comparison and mutation gates. Review tightened two points:
V=0/Mode 0 addresses above 52 bits are unsupported in this profile, and an expected
mutant failure must reach the normal fixture terminal without sanitizer errors.

The executed 734-file snapshot has manifest SHA256
`9a7eab74ae88da11c9ce437f27c54c504c8f47ad9b6ccbfaa271fc3a9aa8cc64`.
The implementation hashes are:

- Oracle: `12bc71eb40e7365964f4cb20fd571789e79d464504a52cb2f6ab24a11fc7a10e`
- Architectural fixtures: `a0ad17dd33c150f594028132c86deabb65e1115fd468d27e7fb64bf55dde5bea`
- Constructor comparison: `d3e1a8c3f37c9c22c036c87933bcae754302060f41ddb2d37cc7ebbc6a802ec2`
- Existing runner extension: `3fd4a00379ffff9b06e62ed19dc1f4458d3023fd1b2536d96bc436492a4a9f63`

The results/contract/completeness documentation written afterward is a
publication-only overlay. It does not claim another execution of changed
implementation bytes.

## Complete corrected window

The invocation ran the existing entrypoint serially:

```sh
bash scripts/kernel-dormant-tests.sh
SANITIZE=1 bash scripts/kernel-dormant-tests.sh
```

Original session `77273` finished at 15:15:38 UTC with exit zero and
`HOSTED_GATE_PASSED`. The retained outer record is `hosted-002/run.json`;
its original terminal is `hosted-002/outer.log`. Every owned child session was
quiescent before finalization, with no cleanup signal needed. The full window
took 49.15 seconds: 16.83 seconds normal and 32.00 seconds sanitized.

Each mode completed 57 expected command outcomes:

- 147 independent translation/fault/profile checks
- 65,555 comparisons against copied actual dormant-constructor bytes
- All thirteen isolated mutants compiled and failed their intended fixture,
  reached the normal failure summary, and emitted no sanitizer diagnostic
- 92,306 existing construction/ownership/independent-byte checks
- 164,313 existing canonical-decoder checks, with zero failures
- Generation-bound-three checks: three complete constructions and seventeen rejections
- Production API, four invalid test/generation configurations, six paired private/public
  member probes, and inspector absence/rejection checks

Normal results reside in
`hosted-002/source/build/kernel-dormant-1791386089860957095`;
sanitized results in
`hosted-002/source/build/kernel-dormant-1791386106697476624`.
Each includes actual command outcomes, source before/after hashes, test logs,
compiled binaries and mutation inputs. All 734 frozen source contents/modes,
observed compiler bytes and fourteen runner-tracked input hashes held unchanged.

The observed host compiler was Debian GNU C++ 14.2.0-19, executable SHA256
`6b3696e4dcb85e1c949c732a02befa50e3983ecf94ce7e8e58d9d503b954b79d`.
This is an observed host-tool pin, not an independently proven compiler.
The runner uses C++23, O1, debug information, Wall/Wextra/Werror. Sanitized
compilation adds `-fsanitize=address,undefined -fno-sanitize-recover=all`.
Leak detection is disabled; no leak-check claim is made.

The existing owned-session supervisor imposed a 600-second wall bound,
256 MiB invocation-output cap, 8 MiB per-file limit and sampled process-tree
limits. Peak owned output was 28,856,320 bytes; the sampled tree peak including
its fixed outer allowance was 508,162,048 bytes. Sampling is not a hard quota.
No new test framework or additional native aggregate was introduced.

## Preserved failed attempt

Original session `23074`, `hosted-001`, failed with exit one at 15:11:03 UTC.
The normal ownership and existing decoder prefix passed, but GCC14 stopped
compilation of the new fixture under `-Werror=maybe-uninitialized`: its
conditional temporary `std::optional<bool>` expected-RW value triggered the
warning. The new oracle had not executed and the sanitizer run had not started.
That failed window is retained as failure, not credited as acceptance.

The correction directly compares the optional RW field when PR is true and
requires absence otherwise, after a null guard. Independent review confirmed
that only this expected-field expression changed, with no weakened coverage,
warning suppression or oracle behavior change. The corrected window reran both
complete modes from fresh outputs. The first snapshot's manifest is
`978c48c51c034c7ed2caa0f47033f3fcbcf8a530a69aa166f651083a64423b0b`.

## Remaining qualification

Independent retained-evidence and final claim review accepted both complete
runs, all 160 runner receipt hashes, all 26 exact mutant instances, source/tool
identity and quiescent cleanup. The review establishes only this hosted
point-address model and the existing dormant ownership tests.
Event-ring behavior, invalidation and completion, interrupt isolation,
publication visibility, bounded timeouts and quarantine after uncertain revocation
remain separate prerequisites. No guest, active IOMMU, BME, actual DMA, physical
hardware, full native aggregate, broad-host or performance qualification is added.
