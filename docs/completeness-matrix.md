# Project status

None of the destination goals is complete. Qualification applies to the exact
source and toolchain recorded in the relevant PR; pending checks remain pending.

| Destination | Status |
|---|---|
| Modern safe kernel | Mixed C++/Aurora kernel with bounded protected programs, IPC and reusable RAM-file read-service incarnations; BIOS uses source UART policy through fixed PortRange admission; native UART policy remains for UEFI consumers; general scheduling, SMP and full Aurora implementation remain incomplete. |
| Safe C++-like language with TypeScript-like types | Aurora owns the frontend, formatter and x86 emitter, including mutable typed-buffer formatter append and bounded calls with two distinct mutable owning roots and matching ABI-facts normalization; linkage spelling is source-owned with final-source qualification pending; native host conversion and dynamic verification remain. Self-hosting and richer type/concurrency features are incomplete. |
| Ideal filesystem and XFS compatibility | Bounded RAM storage and offline readers exist; mounted durable services, recovery and XFS read-write are incomplete. |
| Framework Laptop 13 AMD support | Emulator foundations include a pinned Debian source-packaging correction for the optional Event model; active drivers, DMA isolation, power/recovery and physical qualification are incomplete. |
| Native binutils/glibc/Mesa alternatives | Six source-bootstrap predecessors include a replacement final checkpoint for typed-buffer borrows; core libraries exist; standalone native rebuilding, toolchain/runtime and graphics replacements are incomplete. |
| Applications, terminal and tiling desktop | Bounded serial and graphical consoles exist; general applications, terminal sessions and desktop are incomplete. |

Component details: [compiler](../compiler/ARCHITECTURE.md),
[libraries](../library/README.md), [kernel](../kernel/README.md),
[protected runtime](../kernel/uefi/runtime.md), [allocation](kernel-owned-bytes.md)
and [storage](storage.md).

Next dependencies: [roadmap](roadmap.md). Required checks:
[development and qualification](developer-test-contract.md).
