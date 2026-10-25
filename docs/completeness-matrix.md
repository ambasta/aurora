# Project status

None of the destination goals is complete. Qualification applies to the exact
source and toolchain recorded in the relevant PR; pending checks remain pending.

| Destination | Status |
|---|---|
| Modern safe kernel | Mixed C++/Aurora kernel with bounded protected programs, IPC, reusable RAM-file read-service incarnations and a bounded retained source-owned mutable RAM-file service; BIOS and standalone UEFI consoles use source UART policy through a fixed COM1 UART grant (Com1UartGrant), with runtime offset checks; driver migration is partial, with native UART policy for protected/graphical UEFI and serial for early boot; image-page policies are explicit build inputs; general scheduling, SMP and full Aurora implementation remain incomplete. |
| Safe C++-like language with TypeScript-like types | Aurora owns the frontend, formatter and x86 emitter, including mutable typed-buffer formatter append and bounded calls with up to three distinct owning roots, only the first optionally mutable; [linkage spelling](https://github.com/ambasta/aurora/pull/233) is source-owned with bounded local qualification; whole-function dynamic verification is source-owned without a native fallback, with four derived borrowed-receiver contracts independently compared; flat sorted-snapshot restoration has passed integrated qualification; scalar key observation and operation-local control reuse have passed integrated qualification; compact key-only search storage and checked hosted contiguous-span name comparison are implemented; readonly typed views (`builtin::span<const T>` over `OwnedValues<T>`) validate a hosted owner once and read its elements inline; resolver hash lookup, sort-free ingest and list-based visibility bring the frontend compile below the native-verifier baseline (paired measurement and integrated qualification recorded in [25dd598](https://github.com/ambasta/aurora/commit/25dd598f4a795a2ee7502a3982de0c306182485c)). Qualification is revision-specific and reported with each change. Module import traversal now runs in Aurora over the existing resolver Session; native file authority, conversion, quota/report transport and runtime remain. Self-hosting and richer type/concurrency features are incomplete. |
| Ideal filesystem and XFS compatibility | Bounded RAM storage and offline readers exist; the opt-in retained CPL3 service-owned [49-byte volatile file](https://github.com/ambasta/aurora/pull/234) and its [interactive scratchpad consumer](https://github.com/ambasta/aurora/pull/235) now include source-owned atomic append with explicit admission rights and a caller-computed CRC32C read consumer. Mounted durable services, recovery and XFS read-write are incomplete. |
| Framework Laptop 13 AMD support | Emulator foundations include a pinned Debian source-packaging correction for the optional Event model; active drivers, DMA isolation, power/recovery and physical qualification are incomplete. |
| Native binutils/glibc/Mesa alternatives | One digest-pinned checkpoint compiler (C2 of main `d4cbabb`, one hop from the first checkpoint that the recorded six-stage source route rebuilt) builds C1 and C2 with a convergence check, and bumps are one hop; core libraries exist; standalone native rebuilding, toolchain/runtime and graphics replacements are incomplete. |
| Applications, terminal and tiling desktop | Bounded serial and graphical consoles exist, and the production image renders its protected program console on the framebuffer (80x24 output view, serial input only); a separate [protected RAM scratchpad consumer](https://github.com/ambasta/aurora/pull/235) is implemented with bounded local qualification; general applications, terminal sessions and desktop are incomplete. |

The retained-run authority and transcript deduplication passed integrated
qualification in [PR #242](https://github.com/ambasta/aurora/pull/242).

Component details: [compiler](../compiler/ARCHITECTURE.md),
[libraries](../library/README.md), [kernel](../kernel/README.md),
[protected runtime](../kernel/uefi/runtime.md), [allocation](kernel-owned-bytes.md)
and [storage](storage.md).

Validation cleanup passed independent integrated qualification in
[PR #244](https://github.com/ambasta/aurora/pull/244). [Fixture consolidation](kernel-fixture-consolidation.md)
now leaves 62 canonical images (43 UEFI, 19 BIOS): every fault mode is a
boot-selected fixture case (loader-stage faults through a fw_cfg early fixture),
test baselines are baseline selectors of their fixtures, and `uefi/production`
is the one fixture-free production UEFI image: the protected program console,
rendered on the firmware (GOP) framebuffer by the graphical terminal, under a
v7 handoff and a firmware-described framebuffer admission exercised only under
QEMU/OVMF (no physical display qualification). Payload-bank folding of compositions
that differ only in user images remains, so this is not yet the few-test-images target. Each image
build runs one compiler-fact stack check and one image/W^X/symbol-policy check
in place of the former per-profile admission scripts.
The compiler-semantics runners now compile one packed program per test through
`tests/compiler/native_runner.py`; the token-scan, UTF-8, JSON and package library
tests compile one driver per library surface and stream their cases as data.
Kernel policy, graphical console, display renderer, IOMMU event, protected
note/snapshot, pin/NVMe/dormant and executable-semantics tests build once in Meson
and compare golden results; their Python reimplementation oracles, mutant controls
and receipts are gone.
Hand-built verifier/emitter IR cases are textual IR data (`tests/compiler/ir`,
one `aurora-ir-check` driver) instead of 24 C++ fixture translation units; the
five shape-sweep ABI programs are generated per build by `abi_programs.py`.
IR cases and the sector/method native ABI runners pin only what bridges, harnesses
and the C++ runtime depend on (hidden-input registers, record/service facts,
host-call arity, documented verifier limits, diagnostics); frames, save slots,
probe totals, instruction IDs and verifier metrics are checked as bounds and
relations against the compiler's stack/ABI facts.

Next dependencies: [roadmap](roadmap.md). Required checks:
[development and qualification](developer-test-contract.md).
