# IPC transition native and runtime results

As of 2026-10-06, the exact full public developer **D** and pinned-prebuilt **P**
release native workflows, the separate fatal sanitizer supplement and the full
182-boot runtime regression have independent scoped acceptance. The two input-guard
linked reviews remain blocked and unaccepted, so this is not full IPC/kernel
acceptance. PR28 remains draft; accepted main remains PR27
`772b9c8a6291aa3cc656b409ce0263f73d45b034`.

The tested source has **586 files**, manifest SHA256
`2b4da2190713a207e53e54c597e722ce1ad3cf8a51d438af6072bfae729ebabf`,
published draft head `073c8aeb8af49a38ead95a809cf5c5d595d97dd1`, tree
`93ac7b4ed0a846ccc56fbfa305180d4bc7d6fde6`. This later status overlay changes
documentation/evidence only. It does not claim execution of its new source
manifest, change an earlier terminal, or independently approve its own composition.
Compiler, kernel, libraries, scripts, tests and product inputs remain byte-exact.

The [compact receipt index](evidence/ipc-transition-policy/receipts.json) records
full report, approval, seal, product and archive hashes. Its paths identify retained
external evidence, not additional repository files. Separate raw and audit Library
archives preserve the original evidence; giant logs and binaries are not copied here.

## Completed full public native workflows

Both workflows ran the complete default release graph on the captured GNU/Linux
GCC 14 host: 34 root prerequisites including shared context, 39 direct compiler
recipes and five compound gates, reconciled against 83 retained recipe echoes.
Newly completed matching product receipts, original supervisor exits and positive
quiescent closure establish the result; echoes and Make exit alone do not.

| Workflow | Actual command and provenance | Original completion | Independent terminal report SHA256 |
|---|---|---|---|
| D | `/usr/bin/make --jobs=1 test`; current-source compiler built once; developer receipt has no external expected pin | Session 37204, exit 0 | `c60e8814410cc97e99948212a50eb8c0ff712e14689fa7d3b98df94fcbc2b4a8` |
| P | `/usr/bin/make --jobs=1 test-acceptance` with the independently selected private compiler and expected digest; `externally-pinned-prebuilt`, zero bootstrap builds | Session 2804, exit 0 | `63a6877c7fb274008640ee82d28140634de3b70805628684648bb0292eaa2964` |

Both use compiler SHA256
`66bb719d0ad1622e97b7e448a724d153bb370080f0ce4aa1e5a0b6b322a4a298`.
P's immutable input and run-owned mode-0555 copy have distinct identities; P
does not claim a fresh compiler build. D's terminal is
`4075601769c99a6b6fb8f90bf79f5dac0ac5959cb0b50c2deee831c5031502a3`;
P's is `00ee5b98512bba0f64a36791f00451e61d7647a966264687816bbc54bac48d56`.
The exact P argv and both product/context hashes are in the receipt index.

Each full workflow includes both ordinary and optimized 76-method contract suites
and 192-case cap-configuration checks per Python mode. Those configuration checks
explicitly execute no native work. Separately, all six **actual native consumers**
pass with their configured **1024 MiB sampled storage caps**, using the selected
run-owned compiler. The caps are not aggregate RSS limits or filesystem quotas.

| Native family, per workflow | Retained cases/observations | Rejection runs |
|---|---|---:|
| Package identity | 5,503 cases; 199,213 u64 observations | 40 |
| Package manifest | 20,022 cases; 1,827,671 observations | 58 |
| Package graph | 5,548 cases; 333,671 observations | 60 |
| Kernel budget | 104,120 policy rows; 815,301 decoder rows | 10 |
| Round robin | 17,672 policy rows; 1,051,016 decoder rows; 4,096 copies | 10 |
| IPC transition | 114,613 policy rows; 401,488 decoder rows; 288 finite contexts: 15 accepted, 273 refused | 32 |

Counts include repeated input vectors and overlapping coverage. D and P are not
additive unique-case totals. IPC's 4,096 copy executions repeat one probe. Independent
corpus reviews join complete retained streams to contract arithmetic, package
lineage and genuine generated-root linkage, including all 314 retained
manifest/graph archives and 8,792 archive members per workflow.

Hosted IPC, dispatcher and client-disposal models and hostile adapters exercise
the genuine policy under their finite contracts. Individual refused/malformed
Mailbox operations preserve target/peer bytes and generation behavior. Previously
committed composite prefixes remain committed; no aggregate rollback is promised.
The **6,726-check service-budget host gate instantiates neither Mailbox nor
Dispatcher and calls neither IPC nor round robin**. Its APIC/context/authority
checks do not demonstrate IPC cancellation or restart. Whole-root linkage does
not close that behavioral gap. The separately reviewed actual guest lifecycle
results below supply runtime evidence without relabeling this hosted model.

## Other closed evidence, each with its own scope

- Compiler-free clock controls: ordinary and optimized eight-method suites plus
  retirement/normal command plans passed. Their 586-file source manifest is
  `e6c08e72e9764615043b4ef7c5a726c5a5dda12c6f1de9f8735ec0fe8b6230b7`;
  the later tested `2b4da219…` composition changed documentation only.
- Separate portable controls: all 76 methods and all 192 cap cases per Python
  mode passed. These controls are native-free and do not establish broad-host support.
- Image construction: 54 closed commands produced and preserved 26 variants,
  followed by separate six-command construction of the two IPC input variants.
  Each stage's final normal image construction is not a restoration boot.
- The 26-image linked review accepted its bounded static IPC/ABI, both-stack,
  mapping and four-output-guard scope under stated bootstrap assumptions. Its
  measured generated IPC chain is 512 bytes; independent 16 KiB stacks have
  maxima of 2,120 bytes for RSP0, a conservative 3,416-byte supervisor drain
  bound, and 14,664 bytes for pre-runtime supervisor discovery. These are scoped
  bounds, not whole-kernel safety or observed guest behavior.
- The 22-driver emitted-instruction review supports the unchanged 128 budget
  only conditionally on exact fixed0/APIC/MMIO/interrupt/IRET premises. It keeps
  nine genuine three-tick/two-resume exhaustion obligations. No new numeric gate,
  runtime timing guarantee or family-wide acceptance follows.
- The two new input images have accepted construction/terminal evidence. Their
  separate linked-image review is **platform-blocked and UNACCEPTED**. This status
  overlay neither inspected nor continued that review or its quarantined helper.

## Completed 177+3+2 runtime regression — 2026-10-06

One newly admitted run completed all 177 production modes, three BIOS capacity
probes and two additional normal restoration boots. Original supervisor session
13448 exited 0; terminal completion is 2026-10-06 10:32:21.906857 UTC. Independent
terminal/control and guest-corpus reviews passed, and the parent accepted their
scoped result. No failed prefix or diagnostic attempt supplies credit.

| Evidence | SHA256 |
|---|---|
| Actual terminal | `95bdf3904e3abf9705c8bebec64e971036867fea397eaa2ea44e472e14f58339` |
| Independent runtime approval | `9516ab78fa562aa7f39de2604854276bee3f800377862f2bb5a60a3f0baeb16d` |
| Terminal/control report | `bd9e61fb85d78e3faab13adb0ce5b97f6c75a8157d0ab2848ff90d27f2ba6e54` |
| Raw-corpus report | `04d3dc5b98d3d6142e01565655f9dc1d3d46abf07bba910f4fcdbb01e3c9de4b` |
| Run seal: 1,299 files and 84 directories | `99c1a041e8b234873c7d34a822c7d681261bbc78eaddf253cae2dc616ffc2694` |

All 182 complete QEMU arrays and expected statuses matched: 54 exits of 33 and
128 intended exits of 35. Exactly 51 timer-family modes used
`-icount shift=0,align=off,sleep=off`; 126 other production modes and all five
capacity/restoration boots kept the original clock. No guest loop, 128/3 budget
or strict validator was weakened. Both normal restoration boots actually ran.

Normal IPC returned and consumed 42; dispatch returned 42/73/42 in client order
0,1,0. Mixed dispatch preserved an already committed reply while cancelling its
peer. Cancellation consumption, service restart, retirement and rebinding passed.
The request input/output faults stopped after a valid envelope and before submit;
the cancellation input/output faults stopped after delivery, authenticated service
bounds failure and supervisor restoration, before cancel commit. All four matched
output-image guards passed before their guest launches. Input-mode runtime passes
do not replace the blocked linked reviews.

The independent timer recount covered 141 armed runs, 3,652 charged ticks,
14 kernel drains and nine context samples. Nine modes retained genuine three-tick
exhaustion; context and pending-drain requirements stayed distinct. Retirement's
instruction-clock service runs recorded 78 compiled ticks, including the required
old-owner drain before disposal/rebind and preserved peer completion. These are
observations, not new acceptance thresholds or performance measurements. They do
not explain or repair the historical wall-clock failure.

The run used exact restored QEMU 10.0.13 (`Debian 1:10.0.13+ds-0+deb13u1`),
executable SHA256 `d3c1a558ad220e77a4412048c8d96b44f8c2b41c7ad2a4ecfe522a4b122fe067`,
and the historical 4 MiB combined OVMF image, SHA256
`14954040cc754ade0c625ac3470ea46d4c14318b5b1396de4ef77090203d76db`.
Firmware came directly from authenticated package bytes, not CODE/VARS
concatenation. Effective argv, clean environment, absent default configuration
and excluded optional modules remain bound. The earlier version-only probe was
not a guest result; the separately admitted run supplies the new guest evidence.

All 181 supervised commands used the observed-owned-leader namespace branch,
with recorded actual exits and empty cleanup remaining/signals. The reduced
terminal-source-assumed branch was unused in this run. These are sampled
observations, not lifetime or descendant-wide namespace proofs. Source/runtime
identity, canonical lease closure and all 1,383 sealed entries were verified.
The running allocation sample peaked at 1,658,089,472 bytes; a later preterminal
sample was 1,658,368,000 bytes. Neither is a whole-lifecycle physical peak.
The 4 GiB plan retained its 64 MiB terminal reserve and separately charged
64 MiB unlinked-snapshot engineering allowance; no hard physical quota is claimed.

Raw and final-audit evidence have private Library receipts with exact full
readback. These locators do not grant access to other readers:

| Archive | Library file | Bytes | SHA256 |
|---|---|---:|---|
| Closed raw source/run evidence | `libfile_74fddefa6d688191a1f6516dbf7f308e` | 10,399,397 | `df3feae7d7b2ec24b12cfe47575d6d61625717cc9e574c52e885ea6804bfc8cc` |
| Final independent audits | `libfile_54992a2480c08191bed106e9775635b7` | 92,249 | `f0d2484992251ac7f7e0cb7f8dfc26ecd530cd09a2915c644d7b31abf451ca19` |

The raw readback verified 2,451 original regular files, 153 directories and its
manifest; the audit readback verified all 21 members. Exact receipt and report
paths/hashes are in the [index](evidence/ipc-transition-policy/receipts.json).
The earlier full-run preflight failed because its new comparator omitted SAN's
sealed absent `tmp` sentinel; all native bytes/modes were unchanged. That failure
remains preserved. A narrowly reviewed successor and one ten-method mocked
control passed before the new preflight and sole actual runtime run.


## Preserved failures, remaining gates and evidence limits

The original wall-clock aggregate remains **failed at mode 163,
`user-retire-pending`, after 162 partial passes**. The later single traced success
is inconclusive and spent, not a repair or host-contention diagnosis. No old
prefix, old boot or lost diagnostic is reconstructed or transferred. Historical
PR27 five-consumer results and their original developer-audit failure/composite
retain their distinct identities in [workflow results](developer-test-workflow-results.md).

The exact five-entrypoint fatal ASan/UBSan supplement has now completed using a
separately selected copy of the accepted D compiler. All five rows passed; original
supervisor session **14420** returned actual exit **0**, observed at 2026-10-06
05:37:15 UTC. Terminal SHA256 is
`6b69bd0378e222c560dfcf6109d0dfc978b94d88f850830c1f7522a2a0c0dc09`.
Independent sanitizer review accepted its 140 scoped checks, approval
`a250ffba5445a31f8f445d8b242a90f799e80e6a82d4f21af86d3f5432488019`.
It remains `native_complete=false`, not another full aggregate. The release
compiler and generated assembly are uninstrumented; `detect_leaks=0` gives no
leak-clean result. The tiny copy wrapper contains ASan initialization/registration
only, without operation-level load/store or UBSan handler instrumentation.

The required remaining technical gate is the **platform-blocked, unaccepted
linked review of both input-guard images**. Runtime acceptance does not waive it.
PR28 remains draft and `overall_merge_qualified=false`. This docs-only successor
of `d6891c9d6a09dd154df9e11a7a2d7e800e617252` preserves executable inputs; it is
not relabeled as the executed 586-file manifest.

Successful package-identity assembly/object/executable products were deliberately
deleted by the unchanged producer: 1,150 files per workflow remain absent, with
hashes only. Nothing is reconstructed. Hosted model summaries are aggregate
observations, not per-step raw traces. P's host audit joins the prior D independent
full-byte pass, exact capture equality, and current metadata/membership/executable
checks; it is not a fresh full-host-byte scan or continuous library attestation.
The 7,200-second deadlines apply to polled owned commands; preflight, blocking
checks, cleanup and final hashing can extend outside them. Sampled resource and
namespace checks are not hard quotas, aggregate RSS bounds or exhaustive process
attestation. No CI, ready/merge, Gentoo make-test, broad-host, full Linux/device,
physical-platform, performance-equivalence or whole-language/kernel safety claim
follows from these results.
