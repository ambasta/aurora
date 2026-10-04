# Bounded manifest: combined verification result

The library-only manifest checkpoint passed its final focused tests, distinct
source/oracle review, fresh combined-source aggregate and independent aggregate
readback. Publication and the final archive seal are separate recorded actions.

This file is the sole post-aggregate source addition. All 512 tested project files
remain byte-identical, producing a 513-file final source set. The earlier source
annotations identify their original author-freeze phase; they do not override this
later integration result.

## Exact base and preservation

The combined source uses the independently sealed 506-file UTF-8 line checkpoint,
whose source archive SHA256 is
`b4f93c7fada95f585282ddc8fdf935549371137004cbe88a8ca8c0358a336980`.
All line files are preserved: 502 unchanged and four as their complete original
contents followed only by the manifest lane's frozen additions. Six new files
formed the 512-file aggregate; this result document is the seventh addition.

The prepared source checkpoint was PR18 head
`3b21f4a89df6905af282f61c4aa0ddd416caf2d9`, tree
`f91811efa49ab599c02e567774ef585e2b61ab3a`. Subsequent read-only remote verification
confirmed PR17 and PR18 merged, with main
`6d78551688feb4c4be3a833028f98b78ae3173eb` carrying exactly the same tree. This is an
identical-tree ancestry update, not a source change or a new test claim. Publication
must preserve every unlisted remote path and reverify the base if it changes again.

## Actual final aggregate

Literal `make test` ran from 2026-10-04 16:54:24 UTC to 17:18:59 UTC and exited zero.
All 512 project files and 529 total recorded source/compiler/tool/controller inputs
matched before, after and at independent audit. The rebuilt compiler retained the
accepted SHA256:
`e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e`.

- Manifest: 20,022 native cases, 1,827,671 complete-u64 observations, 251 compiled
  native batches and 58 exact compiler-rejection/output-preservation executions.
- Preserved identity gate: 5,503 cases, 199,213 complete-u64 observations and 40
  rejection/output-preservation executions.
- Preserved UTF-8 line gate: 1,815 cases, 7,260 complete-i64 observations and seven
  rejection controls. Preserved range gate: 2,250 cases, 6,750 observations and six
  rejection controls.
- All inherited compiler, IR, module, image, hosted-kernel and semantics stages
  passed. No test flag substituted a development subset for a full gate.

The final direct, focused Make and aggregate manifest corpora overlap; they are
not added together as unique coverage. Independent review inspected every final
manifest vector and binary's freestanding ELF evidence, all rejection records and
all aggregate pins. A separate co-import check passed four native cases /384
complete-u64 observations: a multibyte CRLF prefix line selects the manifest window,
owned facts survive full input overwrite, and late overflow, manifest CRLF and an
invalid tail remain malformed before index selection. The manifest module itself
still imports only package.identity and std.array.

Aggregate receipt SHA256:
`ed57c4ac217826c8e9db4d54637758ae273a1511922c30ed5f2ddb24b2d2b367`.
Independent aggregate audit SHA256:
`146052e2d855c9f1b3190952e23c2617618ed84d701db5f74b7c3822065d2c61`.
Independent manifest-vector audit SHA256:
`b7618d51db4314c83a41f8afcf8c6268e7c0d3b3854f07e07787741a31d6fe8a`.
These records are in the companion verification archive, not missing source-local
links. The [source-local index](README.md) and [API contract](../../docs/package-manifest-contract.md)
provide reproduction instructions and the exact format/ownership boundary.

## Bounds and retained evidence

The aggregate accounted for both author and fresh integration workspaces. It
admitted 380 MiB of growth, retained a 64 MiB reserve and enforced a 1 GiB free
floor under a 512 MiB combined ceiling. Observed peak allocation was 418,594,816
bytes; adding the reserve gives 485,703,680 bytes, below 536,870,912. Final free
storage was 28,598,370,304 bytes.

Only completed successful UTF-8 range/line outputs were compacted during the run.
Exact ordered Make completion lines, passed manifests and same-namespace process/
write-descriptor checks preceded archival. All 6,031 file/directory members were
verified for exact bytes, lengths, modes and membership before duplicate removal,
then independently audited. Source files and recipes were never changed.

After the original exec session terminated successfully, generated build/temp
outputs were archived and verified before retirement. The accepted compiler stayed
in place. The recovery archive preserves 14,808 members /1,064,562,366 payload bytes;
251 successful manifest batch compression encodings were replaced by their exact
raw tar streams. Its SHA256 is
`06843d36b81ed2706e06c8fe78df7065bc9c0227f27750c231b6865c77a8ada6`.
Recovery maps retain original encoding hashes, paths and modes. The fresh process
scan is explicitly limited to its own PID namespace; original-session completion
and the synchronous Make result supply the recorded operational completion evidence.

The pre-admission controller review fixed non-exact/out-of-order completion-fence
matching and failure finalization that could mask an earlier exception. Exact
controls and the actual recipe's double-slash spelling were tested before launch.
The original drafts and counterexamples remain preserved alongside the earlier
CRLF-oracle and failed-receipt defects described in the source index. No behavioral
production-parser defect was reproduced. All failed artifacts remain available.

## Claim boundary

This is a bounded declarative metadata profile: one canonical package identity and
zero to eight pinned direct dependencies, with copied observations after full
validation. It supplies no resolver, source retrieval, version ranges, build or
script execution, installation, network/filesystem authority, cryptographic trust,
native runtime or self-hosting. Public constructors remain forgeable data rather
than provenance or capabilities. There is no new emulator/physical-device gate,
whole-language safety proof or measured equivalent-C performance claim.
