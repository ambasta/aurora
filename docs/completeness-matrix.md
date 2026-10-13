# Project status

## Current project state

None of the six destination goals is complete. Component guides describe current
behavior and limits; Git/PR history and retained run evidence hold past results.

| Destination | Current status |
|---|---|
| Modern safe kernel | Emulator boot, bounded Aurora policies, scheduling and copied IPC work; Aurora command-stream migration is source-reviewed only. General protected services, SMP and full native implementation remain incomplete. |
| Safe C++-like language with TypeScript-like types | Checked values, classes, modules, bounded generics/borrowing and Aurora parsing, resolution and typed lowering; Aurora metadata/layout and graph verification are source-only candidates awaiting qualification. Aurora-native CFG verification and emission, general borrowing, concurrency, type transformations and self-hosting remain incomplete. |
| Ideal filesystem and XFS compatibility | Host crash models, RAM sectors and offline XFS readers work; mounted persistent file services, recovery and XFS read-write remain incomplete. |
| Framework Laptop 13 AMD system | Emulator discovery and bounded device models work; active drivers, DMA isolation, power/recovery and physical machine qualification remain incomplete. |
| Native binutils/glibc/Mesa alternatives | Source-bootstrapped compiler, ABI metadata, core libraries and bounded package tools work; native toolchain/runtime, graphics stack and reproducible native rebuilds remain incomplete. |
| Useful apps, terminal and tiling desktop | Bounded serial/graphical consoles and protected volatile note/file commands work; general app/file services, terminal sessions and a usable tiling desktop remain incomplete. |

## Qualification boundary

Changed source requires final-source GCC 16 `full`, independent review, normal
BIOS/UEFI images and real smokes, plus affected admission/fault/recovery/restoration
gates. See [development and qualification](developer-test-contract.md). No physical
AMD support, general memory-safety proof or equivalent-C performance is established.

Implementation: [compiler](../compiler/README.md), [libraries](../library/README.md),
[kernel](../kernel/README.md), [consoles](native-console-service.md),
[graphical output](framebuffer-console.md), [storage](storage.md).
Next dependencies and acceptance gates: [roadmap](roadmap.md).
