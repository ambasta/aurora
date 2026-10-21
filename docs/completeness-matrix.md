# Project status

None of the destination goals is complete. Qualification applies to the exact
source and toolchain recorded in the relevant PR; pending checks remain pending.

| Destination | Status |
|---|---|
| Modern safe kernel | Mixed C++/Aurora kernel with bounded protected programs, IPC, reusable RAM-file read-service incarnations and a bounded retained source-owned mutable RAM-file service; BIOS uses source UART policy through a fixed COM1 UART grant (Com1UartGrant), with runtime offset checks; driver migration is partial, with native UART policy for UEFI and serial for early boot; image-page policies are explicit build inputs; general scheduling, SMP and full Aurora implementation remain incomplete. |
| Safe C++-like language with TypeScript-like types | Aurora owns the frontend, formatter and x86 emitter, including mutable typed-buffer formatter append and bounded calls with up to three distinct owning roots, only the first optionally mutable; [linkage spelling](https://github.com/ambasta/aurora/pull/233) is source-owned with bounded local qualification; native host conversion and dynamic verification remain. Self-hosting and richer type/concurrency features are incomplete. |
| Ideal filesystem and XFS compatibility | Bounded RAM storage and offline readers exist; the opt-in retained CPL3 service-owned [49-byte volatile file](https://github.com/ambasta/aurora/pull/234) and its [interactive scratchpad consumer](https://github.com/ambasta/aurora/pull/235) have bounded local qualification. Mounted durable services, recovery and XFS read-write are incomplete. |
| Framework Laptop 13 AMD support | Emulator foundations include a pinned Debian source-packaging correction for the optional Event model; active drivers, DMA isolation, power/recovery and physical qualification are incomplete. |
| Native binutils/glibc/Mesa alternatives | Six pinned source-bootstrap predecessors have a reconstruction command and local digest/receipt checks, including the replacement final typed-buffer checkpoint; core libraries exist; standalone native rebuilding, toolchain/runtime and graphics replacements are incomplete. |
| Applications, terminal and tiling desktop | Bounded serial and graphical consoles exist; a separate [protected RAM scratchpad consumer](https://github.com/ambasta/aurora/pull/235) is implemented with bounded local qualification; general applications, terminal sessions and desktop are incomplete. |

Component details: [compiler](../compiler/ARCHITECTURE.md),
[libraries](../library/README.md), [kernel](../kernel/README.md),
[protected runtime](../kernel/uefi/runtime.md), [allocation](kernel-owned-bytes.md)
and [storage](storage.md).

Next dependencies: [roadmap](roadmap.md). Required checks:
[development and qualification](developer-test-contract.md).
