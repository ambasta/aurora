# Project status

None of the destination goals is complete. Qualification applies to the exact
source and toolchain recorded in the relevant PR; pending checks remain pending.

| Destination | Status |
|---|---|
| Modern safe kernel | Mixed C++/Aurora kernel with bounded protected programs, IPC, reusable RAM-file read-service incarnations with shared bounded call transport/accounting and a bounded retained source-owned mutable RAM-file service; BIOS and standalone UEFI consoles use source UART policy through a fixed COM1 UART grant (Com1UartGrant), with runtime offset checks; driver migration is partial, with native UART policy for protected/graphical UEFI and serial for early boot; image-page policies are explicit build inputs; general scheduling, SMP and full Aurora implementation remain incomplete. |
| Safe C++-like language with TypeScript-like types | Aurora owns the frontend, formatter and x86 emitter, with direct checked relocatable-object output for ordinary source UART, standalone UEFI console/session, production terminal painter and hosted frontend forms, including readonly literals, scoped size/public-field-count reflection and a retained text backend, including mutable typed-buffer formatter append and bounded calls with up to four distinct owning roots with per-root mutability; [linkage spelling](https://github.com/ambasta/aurora/pull/233) is source-owned with bounded local qualification; whole-function dynamic verification is source-owned without a native fallback, with four derived borrowed-receiver contracts independently compared; flat sorted-snapshot restoration has passed integrated qualification; scalar key observation and operation-local control reuse have passed integrated qualification; compact key-only search storage and checked hosted contiguous-span name comparison are implemented; readonly typed views (`builtin::span<const T>` over `OwnedValues<T>`) validate a hosted owner once and read its elements inline; resolver hash lookup, sort-free ingest and list-based visibility bring the frontend compile below the native-verifier baseline (paired measurement and integrated qualification recorded in [25dd598](https://github.com/ambasta/aurora/commit/25dd598f4a795a2ee7502a3982de0c306182485c)). Qualification is revision-specific and reported with each change. Source lexing, parsing, admission and ingestion, the formatter's parse, layout and output verification, module import traversal and loading policy (names, paths, byte limits, headers and interfaces) run in Aurora over the existing resolver Session; after lowering, one Aurora call projects, admits, verifies, graph-checks, publishes and emits code with the requested stack and ABI facts (including the source declaration spellings), with no native success fallback. The built-in type and sealed service catalog and the admission and layout limits live only in Aurora, which seeds the resolver, admission and lowering from them, and Aurora renders every module-loading, source, resolver, lowering, pipeline, formatter and lint diagnostic. The native host keeps only command lines, file authority, diagnostic printing, allocation and artifact transport and the byte runtime; textual-IR fixtures are read in Aurora and run the same pipeline stages. Hosted programs receive a sealed [`builtin::HostFiles`](../compiler/SERVICES.md#hosted-files) capability (confined directory reads, atomic outputs, stdout/stderr) implemented by the Aurora Linux binding `runtime/linux/aurora/host.au` over compiler-emitted inline system calls and a compiler-emitted `_start`, so they link with `ld` alone; `main` may also take a 4 GiB [`ByteRegion`](../compiler/SERVICES.md#hosted-memory) whose owners run on the Aurora memory runtime `runtime/linux/aurora/memory.au` (one anonymous mapping per allocation, through checked memory primitives), so programs with `OwnedBytes`/`OwnedValues` need no C++ either; the C++ byte adapter remains only under the C++-hosted aurorac, aurora-fmt and C++ test drivers. The compiler itself adopts these only at a checkpoint bump, and a kernel-service binding is future work. Self-hosting and richer type/concurrency features are incomplete. |
| Ideal filesystem and XFS compatibility | Bounded RAM storage and offline readers exist; production named-file append pairs one live Call-only caller with one live Serve-only producer retaining a once-constructed candidate, then publishes once to the supervisor store after terminal EOF parking, clean caller return and both retirements, with final-source qualification required; the opt-in retained CPL3 service-owned [49-byte volatile file](https://github.com/ambasta/aurora/pull/234) and its [interactive scratchpad consumer](https://github.com/ambasta/aurora/pull/235) now include source-owned atomic append with explicit admission rights and a caller-computed CRC32C read consumer. Mounted durable services, recovery and XFS read-write are incomplete. |
| Framework Laptop 13 AMD support | Emulator foundations include a pinned Debian source-packaging correction for the optional Event model; active drivers, DMA isolation, power/recovery and physical qualification are incomplete. |
| Native binutils/glibc/Mesa alternatives | One checkpoint compiler named by source commit (C2 of main `ab255328`, one hop from `d4cbabb`; `scripts/bootstrap.py rebuild` builds it from source with no binary) builds C1 and C2 with a convergence check, and bumps are one hop; the source UART policy, ordinary UEFI console/session, production terminal painter and C1-built frontend B emit ELF objects directly, B runs in C2 and converges with C2-produced frontend C; Aurora is the sole composer for the admitted frontend, ordinary UEFI console/session, production terminal painter and existing BIOS console/UEFI device-fixture/hosted UART objects, preserving source LOCAL symbols and remapping wrapper relocations without a general linker; frontend B/C wrappers now emit directly from the single table/ABI-derived closed recipe; predecessor-built frontend A, console/UART/painter wrapper assembly, other native object consumers and final links still use GNU tools; core libraries exist; standalone native rebuilding, toolchain/runtime and graphics replacements are incomplete. |
| Applications, terminal and tiling desktop | Bounded serial and graphical consoles exist, with retained Aurora-owned protected-console session routing and fail-closed completion state; the production image renders its protected program console on the framebuffer (80x24 output view, serial input only); a separate [protected RAM scratchpad consumer](https://github.com/ambasta/aurora/pull/235) is implemented with bounded local qualification; general applications, terminal sessions and desktop are incomplete. |

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
symbol-address materialization or relocation policy. Qualification remains revision-specific.
Contiguous canonical u8 receiver arrays use compact exact zero initialization
with register/arithmetic-flag preservation and emitted transient-stack facts; array bytes,
neighboring fields and padding semantics are unchanged.

Component details: [compiler](../compiler/ARCHITECTURE.md),
[libraries](../library/README.md), [kernel](../kernel/README.md),
[protected runtime](../kernel/uefi/runtime.md), [allocation](kernel-owned-bytes.md)
and [storage](storage.md).

Validation cleanup passed independent integrated qualification in
[PR #244](https://github.com/ambasta/aurora/pull/244). [Fixture consolidation](kernel-fixture-consolidation.md)
now leaves 15 canonical images (12 UEFI, 3 BIOS): every fault mode is a
boot-selected fixture case (loader, ACPI, PCI, BAR and IVRS cases through the fw_cfg
platform fixture; framebuffer, graphical-console, console and owned-bytes rows
through the display and device fixtures; IPC, budget, dispatcher, user-phase and
resume rows through the one service fixture; RAM file, RAM scratchpad and protected
namespace rows through the storage fixture; blocking Call and snapshot rows through
the snapshot-call fixture; file-call, owned-text and
console-region rows through the text fixture, each row running its former image's
user images from a packed bank),
test baselines are baseline selectors of their fixtures, and `uefi/production`
is the one fixture-free production UEFI image: the protected program console,
rendered on the firmware (GOP) framebuffer by the graphical terminal, under a
v7 handoff and a firmware-described framebuffer admission exercised only under
QEMU/OVMF (no physical display qualification). The shared 2 MiB arena now reserves
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
programs are generated per build by `abi_programs.py`.
IR cases and the sector/method native ABI runners pin only what bridges, harnesses
and the C++ runtime depend on (hidden-input registers, record/service facts,
host-call arity, documented verifier limits, diagnostics); frames, save slots,
probe totals, instruction IDs and verifier metrics are checked as bounds and
relations against the compiler's stack/ABI facts.

The console adapters share one typed four-record namespace core without command
parsing or reply presentation. The opt-in [protected volatile namespace](native-console-service.md#protected-volatile-namespace)
now retains that core in a CPL3 Aurora owner across bounded `write`/`cat` commands.
It uses copied caller windows and explicit commit/loss outcomes, never a supervisor
copy of committed file contents. Owner failure/reset loses all data; this is not
mounted or durable storage. Production console storage is unchanged. Image/stack
admission and guest qualification remain revision-specific.

Next dependencies: [roadmap](roadmap.md). Required checks:
[development and qualification](developer-test-contract.md).
