# IPC transition native results and remaining integration gates

As of 2026-10-06, the exact full public developer **D** and pinned-prebuilt **P**
release native workflows have independent terminal/provenance and retained-corpus
approval. This is native acceptance of the tested candidate, not full IPC/kernel
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
not close that behavioral gap. Actual service-budget runtime evidence remains due.

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

## Restored QEMU identity is not guest qualification

Historical QEMU unavailability in the earlier static reports describes their
review time. QEMU **10.0.13** (`Debian 1:10.0.13+ds-0+deb13u1`) has now been
restored and durably read back: 146 historical executable/library/firmware pins,
main executable SHA256
`d3c1a558ad220e77a4412048c8d96b44f8c2b41c7ad2a4ecfe522a4b122fe067`.
Canonical activation verified 213 physical entries and one version-only probe
returned exit 0 at 2026-10-06 05:02:24 UTC. Its closure receipt is
`bfa38d5c7cffb235c3dce01a1329bde0f975d84b6201dfb46675a53fced20a78`.
No guest or firmware boot occurred. The runtime environment file is newly
constructed, not historically byte-matched. Optional braille, USB redirection
and smartcard modules/dependencies are absent and excluded. Exact runtime timing
premises, firmware/launcher bindings and guest qualification remain pending.
These QEMU receipts do not close recovery or durable backup of the historical
combined OVMF image; distinct CODE/VARS images cannot substitute for it.

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
Independent terminal/corpus/linkage review remains active and **acceptance is
pending**. This is a completed bounded supplement, with `native_complete=false`,
not a new full native aggregate. The release compiler and generated assembly are
uninstrumented, and `detect_leaks=0` cannot establish leak cleanliness. Fresh full **177 production
emulator modes + three BIOS capacity probes + two actual normal restoration boots**
remain pending. All 51 selected instruction-clock modes, 126 original-clock
production modes and five capacity/restoration exclusions retain their exact
command and strict validator obligations. No budget, loop or validator is weakened.

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
