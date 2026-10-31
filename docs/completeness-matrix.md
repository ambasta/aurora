# Project status

None of the destination goals is complete. Qualification applies to the source,
toolchain and consumer recorded in the relevant PR. Evidence for an unchanged
path is distinguished from an actual guest run of the final binary.

| Destination | Status |
|---|---|
| Modern safe kernel | Mixed C++/Aurora kernel with Aurora admission and policy, native privileged execution and audited frame/page-table ownership. The retained source MemoryManager owns allocation and mapping ledgers, both fixed resident reservation catalogs, cross-resident quota admission and loader snapshot lifecycle. Four fixed-extent word grants and a private synchronous mapping authority share one atomic issuer and operation scope. Native code validates exact physical effects, root/slot generations and clear/invalidate-before-release ordering; it retains no mutable mapping or reservation catalog. Source audits classify copied table observations through lexical readonly bank views. A charged metadata-tail page and separate scratch page preserve the two-slot reservation capacity. The bounded read-only ELF parser pin remains an explicit effect-closed bridge; private source policy remains trusted. This is boot-admitted fixed storage, not general heap ownership, COW, mutable views or SMP. Process and loader timer allowances now reside in retained Aurora roots, initialized into unique opaque native storage and borrowed only for synchronous effect-free transitions; native code retains physical timer/identity evidence, not a copied allowance ledger. This is not a general asynchronous owner or SMP contract. The [process runtime](../kernel/uefi/process.md) runs static ELF programs at CPL3 with private address spaces, demand-backed memory quotas, timer-bounded execution and two resident slots. A separate Serve-authorized Aurora program owns file namespaces, handles and retained RAM contents; the kernel copies bounded messages and authenticates process/service incarnations, without a kernel file-store fallback. Existing file/compiler rows use this owner, with cross-client retention, stale/foreign authority rejection, allocation refusal, cancellation and service-loss/restart cases. Production `run PATH [args]` loads a committed executable through the service and returns to the existing console after exit, fault or watchdog expiry. Its command sequencing, pending file-request progress and terminal-result selection now run in one retained Aurora invocation over a sealed synchronous effects loan; native code still owns endpoint transport and physical resident lifetimes. A retained Aurora incarnation root now owns service generation allocation, startup/readiness, loss and authenticated cleanup eligibility, with one fresh attempt per runtime API operation and no replay; native bindings and cleanup effects are not a mirrored lifecycle policy. Command admission is represented by a scoped linear `ExecutionLease`: all results require explicit consuming finalization, including inert refusal and failed loading with a close obligation. Local moves preserve issuer provenance, and a live lease pins its issuer loan. Explicit cancellation retains source-owned draining of dispatched requests under existing budgets; no automatic destructor hides an RPC loop or claims rollback. The synchronous command groups that lease and its phase/result state in a source-owned CommandExecution, with complete field initialization before constructor-body access and an ordinary in-place consuming source finish. The containing object preserves the original lexical issuer pin; it represents refused preparation and pending close as well as a live child. This is not an escaping owned-child or asynchronous process API. A distinct linear bootstrap lease now drives the complete source-owned file-service startup sequence and resolves one unpublished owner through authenticated publication or cleanup; native code retains physical receipts rather than a second startup cursor. This is not a general service composer or init manager. A stable Aurora ServiceOwner now holds the unique resident-slot capability across runtime calls; an admitted complete constructor transfers its retained-native input, and an explicit consuming receiver drives shutdown and reclamation before consuming that field. Native bindings authenticate the exact root, field and epoch, while incarnation and budget roots remain separate owners. This is the fixed production file-service lifetime, not general owned children, arbitrary owner transfer or asynchronous supervision. Production note/named-file state also belongs to the source service; native console code retains only transient projections and authenticated worker state. Private-volume production cases cover writable/sealed executable-snapshot rollback and real source commits followed by owner exit or rejected replies, with fresh generations and console recovery. General scheduling, SMP, full Aurora implementation and physical-platform qualification remain open. |
| Safe C++-like language with TypeScript-like types | Aurora owns the frontend, formatter and x86 emitter, with direct checked relocatable-object output for ordinary source UART, standalone UEFI console/session, production terminal painter and hosted frontend forms, including readonly literals, scoped size/public-field-count reflection and a retained text backend, including mutable typed-buffer formatter append and bounded calls with up to four distinct owning roots with per-root mutability; [linkage spelling](https://github.com/ambasta/aurora/pull/233) is source-owned with bounded local qualification; whole-function dynamic verification is source-owned without a native fallback, with four derived borrowed-receiver contracts independently compared; flat sorted-snapshot restoration has passed integrated qualification; scalar key observation and operation-local control reuse have passed integrated qualification; compact key-only search storage and checked hosted contiguous-span name comparison are implemented; readonly typed views (`builtin::span<const T>` over `OwnedValues<T>`) validate a hosted owner once and read its elements inline; resolver hash lookup, sort-free ingest and list-based visibility bring the frontend compile below the native-verifier baseline (paired measurement and integrated qualification recorded in [25dd598](https://github.com/ambasta/aurora/commit/25dd598f4a795a2ee7502a3982de0c306182485c)). Qualification is revision-specific and reported with each change. Source lexing, parsing, admission and ingestion, the formatter's parse, layout and output verification, module import traversal and loading policy (names, paths, byte limits, headers and interfaces, graphs of up to 256 files) run in Aurora over the existing resolver Session; after lowering, one Aurora call projects, admits, verifies, graph-checks, publishes and emits code with the requested stack and ABI facts (including the source declaration spellings), with no native success fallback. The built-in type and sealed service catalog and the admission and layout limits live only in Aurora, which seeds the resolver, admission and lowering from them, and Aurora renders every module-loading, source, resolver, lowering, pipeline, formatter and lint diagnostic. aurorac (and aurora-fmt, the same program under another name) is itself a hosted Aurora program: command line, file authority, diagnostic rendering and atomic artifacts run in Aurora over `HostFiles` and the Aurora memory runtime, and it links with `ld` alone with no C or C++, and C1 has the inline memory-access fast path (0.63x the cycles) when its first compiler does: always from the seed, and from a cached compiler built from `a62c3c45` on; textual-IR fixtures are read in Aurora and run the same pipeline stages. Hosted programs receive a sealed [`builtin::HostFiles`](../compiler/SERVICES.md#hosted-files) capability (confined directory and file reads with close and device/inode identities, atomic outputs, stdout/stderr) implemented by the Aurora Linux binding `runtime/linux/aurora/host.au` over compiler-emitted inline system calls and a compiler-emitted `_start`, so they link with `ld` alone; `main` may also take a 4 GiB [`ByteRegion`](../compiler/SERVICES.md#hosted-memory) whose owners run on the Aurora memory runtime `runtime/linux/aurora/memory.au` (one anonymous mapping per allocation, through checked memory primitives), so programs with `OwnedBytes`/`OwnedValues` need no C++ either; the C++ byte adapter remains only under the C++ test drivers and the optional language server; `--target aurora` selects the Aurora kernel binding `runtime/aurora/aurora/host.au` (print, exit, the file operations and the memory runtime's map, remap and unmap through the kernel's INT 0x83 gate). Self-hosting and richer type/concurrency features are incomplete. |
| Ideal filesystem and XFS compatibility | The external Aurora file owner provides bounded volatile commits, immutable open-file versions and per-client cleanup; owner loss visibly loses RAM data and never replays a failed command. A real DMA-backed NVMe path has exercised Identify/read/write/Flush and cold-boot persistence on disposable emulator disks. A separate retained read-only block grant connects the source file service to a strict fresh-format XFS mount: complete supported-log and root/inode admission precedes `/disk` reads. Actual process guests read binary files across clients while the entire read-only image remains unchanged. Production NVMe/GOP guests also exercise eager mount readiness, cross-client reads and unsupported-log refusal while preserving the RAM service and graphical console. A separate explicit Linux 6.12.107 clean-log profile has whole-image used/wrapped reads and dirty-log refusal both hosted and through the protected source owner; production defaults stay fresh-format, while an explicit clean-profile opt-in passes shipped-client, graphical and dirty-refusal guests without changing the images. Qualification and budget acceptance remain revision-specific. A bounded CORE-only recovery source consumer has pure-sector, private-copy Linux interoperability, device publication and completed-command-boundary restart checks. A separate exact root CORE+LOCAL name-permutation mode passes Linux-derived golden/admission tests, actual forward production and reverse process recovery, and four completed-command cut/reentry pairs with independently Linux-accepted completion bytes. Explicit production dirty recovery, completed-marker reentry and controlled refusal pass the shipped-command and graphical-console gates; a private source-owner fixture also passes one genuine commit-loss and independent readonly remount without reminting the writer. A separate clean-only mounted owner now replaces existing `/disk/hello` with 1–4096 bytes once per boot using two preallocated one-block files; staging remains private, open readers retain their inode, and owner loss permits only a RAM-only restart, never writer renewal. Actual 777-byte replacement, cold-boot 113-byte replacement and shipped-compiler object persistence passed targeted process/production gates and independent Linux acceptance. All 16 completed-write cuts, five Flush cuts and 16 readonly recovery boots passed with old/new target visibility checked through HostFiles. A nested read-only extension now walks checked shortform directories, retains directory-bound handles and enforces component-wise private-name and relative-path confinement; component and production guests exercise nested reads, sibling module loading, compile/link/run and unchanged disk bytes. It validates deeper metadata on demand, not by recursively scrubbing the tree, and does not broaden the fixed mounted-write or recovery profiles. These bounded operations do not provide full disk continuity after owner loss, allocation, arbitrary namespace mutation or general writable XFS. General clean-log/namespace coverage, replay, native filesystem transactions, recovery/GC and physical-device qualification remain open. See [storage](../storage/README.md). |
| Framework Laptop 13 AMD support | Emulator foundations include a pinned Debian source-packaging correction for the optional Event model; active drivers, DMA isolation, power/recovery and physical qualification are incomplete. |
| Native binutils/glibc/Mesa alternatives | The compiler bootstraps from its Aurora sources through the GCC-built seed or an explicitly selected cached first compiler, with current-stage convergence checks. Aurora emits its bounded ELF objects and now links the complete supported emitter object into a static executable through `--link-object` or `--emit-executable`; guest compile/link/run no longer requires host `ld`. This is a checked single-object linker for the supported sections, defined symbols and PC32/PLT32 relocations, not a general GNU linker replacement. Existing kernel/bridge assembly and final native image links still use GNU tools. Core libraries and Linux/Aurora runtime bindings exist; complete native rebuilding, general assembler/linker, runtime/library ecosystem and graphics replacements remain open. |
| Applications, terminal and tiling desktop | The one production UEFI image combines its protected command console, serial input and 80x24 framebuffer output with `run PATH [args]`. Shipped compiler/tools can compile, link and execute a retained file in the same boot; faulting and resource-limited children return to the console. The source file owner also retains the bounded legacy note/named-file state. These are bounded emulator mechanisms, not general terminal sessions, job control, input devices, windowing or a tiling desktop; those application goals remain open. |

The retained-run authority and transcript deduplication passed integrated
qualification in [PR #242](https://github.com/ambasta/aurora/pull/242).

Native copied-record consumers retain one consolidated artifact-build ABI
admission over compiler facts; removing those consumers remains future work.

Native retained state now projects validated ACPI topology into immutable timer
evidence and sizes private physical-page metadata to each pool's capacity,
without changing parsing, diagnostics, admission or page-lease ownership. Final
image and guest qualification remains revision-specific.

Boot-exclusive ordinary and RAM callers now use one private typed continuation
owner with a write-once composition kind, full empty-state admission and member-only
scrubbing. Overlapping service/console/domain continuations remain independent;
this owner sharing alone establishes no mapped-page saving.

Generated calls preserve complete span descriptors with compact copies and
initialize service-record gaps without redundant payload clearing. This recovers
production executable-page headroom without changing image caps or call authority;
qualification and compile-time measurements remain revision-specific.

Numeric scalar register immediates select compact, flag-preserving MOV forms in
both text and direct-object output, without changing scalar bits, stack facts,
symbol-address materialization or relocation policy. Ordinary const methods with
no arguments or borrowed roots and an exact unsigned u32-range literal-return
body may emit that literal after full verification; receiver evaluation, callee
retention and actual emitted-call stack facts remain intact. Qualification remains revision-specific.
Contiguous canonical u8 receiver arrays use compact exact zero initialization
with register/arithmetic-flag preservation and emitted transient-stack facts; array bytes,
neighboring fields and padding semantics are unchanged.

Component details: [compiler](../compiler/ARCHITECTURE.md),
[libraries](../library/README.md), [kernel](../kernel/README.md),
[protected runtime](../kernel/uefi/runtime.md), [allocation](kernel-owned-bytes.md)
and [storage](storage.md).

Validation cleanup passed independent integrated qualification in
[PR #244](https://github.com/ambasta/aurora/pull/244). [Fixture consolidation](kernel-fixture-consolidation.md)
now leaves 16 canonical images (13 UEFI, 3 BIOS): every fault mode is a
boot-selected fixture case (loader, ACPI, PCI, BAR and IVRS cases through the fw_cfg
platform fixture; framebuffer, graphical-console, console and owned-bytes rows
through the display and device fixtures; IPC, budget, dispatcher, user-phase and
resume rows through the one service fixture; RAM file, RAM scratchpad and protected
namespace rows through the storage fixture; blocking Call and snapshot rows through
the snapshot-call fixture; file-call, owned-text and
console-region rows through the text fixture, each row running its former image's
user images from a packed bank; boot-volume, frame and export rows through the
[process fixture](../kernel/uefi/process.md)),
test baselines are baseline selectors of their fixtures, and `uefi/production`
is the one fixture-free production UEFI image: the protected program console,
rendered on the firmware (GOP) framebuffer by the graphical terminal, under a
closed v10 handoff carrying the runtime, framebuffer and boot volume. Explicit
NVMe storage adds a separately admitted composition, not another production image.
Framebuffer qualification remains QEMU/OVMF-only (no physical display qualification). The shared 2 MiB arena now reserves
512 KiB for the kernel, with relocated IDT and guarded main stack; low owners,
user-image caps and the 15,360-byte stack admission cap do not change. Existing
fixture compositions remain [separate](kernel-fixture-consolidation.md#still-separate). Each image
build runs one compiler-fact stack check and one image/W^X/symbol-policy check
in place of the former per-profile admission scripts.
The storage bank reserves twelve pages for seven slots, including the namespace's
two-page caller and three-page owner under its closed 2/3/1 row policy. The separate
snapshot-call bank holds four one-page slots; its small Call client retains the
stricter one-page link cap and the unchanged 2/1/1 runtime Call policy. The shared
runtime is not forked. The layout capacity change and fixture composition add no
product storage/restart behavior; final linked images and guests require fresh
qualification rather than inherited receipts.
The compiler-semantics runners now compile one packed program per test through
`tests/compiler/native_runner.py`, with fixed cases as `.cases` data beside each
runner; the token-scan, UTF-8, JSON and package library
tests compile one driver per library surface and stream their cases as data.
Scratchpad/namespace transcript tests share one runtime-mode host and compile each
source once; namespace-owner scenarios are readable request/reply data expanded by
the existing packed runner, with malformed words kept explicit.
Kernel policy, graphical console, display renderer, IOMMU event, protected
note/snapshot, pin/NVMe/dormant and executable-semantics tests build once in Meson
and compare golden results; their Python reimplementation oracles, mutant controls
and receipts are gone.
Parser grammar cases are data (`tests/compiler/hosted_parser.cases`) checked by
one driver against a reviewed golden dump of the Aurora parser's own records; the
C++ syntax adapter, reference lexer and their forged-entry tests are removed.
Hand-built verifier/emitter IR cases are textual IR data (`tests/compiler/ir`,
one `aurora-ir-check` driver) read by an Aurora test module into the compiler's
own stores and pipeline; there is no C++ IR model. The five shape-sweep ABI
programs are generated per build by `abi_programs.py`. The sector-value native
ABI cases share one runtime-selected executable, including owned snapshots,
full payload/status and poisoned-padding checks; oracle self-controls are removed.
IR cases and the sector/method native ABI runners pin only what bridges, harnesses
and the C++ runtime depend on (hidden-input registers, record/service facts,
host-call arity, documented verifier limits, diagnostics); frames, save slots,
probe totals, instruction IDs and verifier metrics are checked as bounds and
relations against the compiler's stack/ABI facts.

Next dependencies: [roadmap](roadmap.md). Required checks:
[development and qualification](developer-test-contract.md).
