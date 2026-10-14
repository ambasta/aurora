# Project status

## Current project state

None of the destination goals is complete. Compiler source-bootstrap builds are
restored; self-hosting and full kernel migration remain incomplete.

| Destination | Status |
|---|---|
| Modern safe kernel | Experimental mixed C++/Aurora kernel; general protected services, SMP and full native implementation incomplete. |
| Safe C++-like language with TypeScript-like types | Aurora frontend and partial verifier migration are present; the compiler remains mixed Aurora/C++. Self-hosting, native emission and richer type/concurrency features incomplete. |
| Ideal filesystem and XFS compatibility | RAM storage and offline readers exist; mounted durable services, recovery and XFS read-write incomplete. |
| Framework Laptop 13 AMD support | Emulator foundations exist; active drivers, DMA isolation, power/recovery and physical qualification incomplete. |
| Native binutils/glibc/Mesa alternatives | Bootstrap compiler and core libraries exist; working reproducible native rebuild, toolchain/runtime and graphics replacements incomplete. |
| Applications, terminal and tiling desktop | Bounded serial and graphical consoles exist. General apps, terminal sessions and desktop incomplete. |

Current gate: original repository check and final-source GCC16 full
suite, followed by affected image/guest checks. See [development and qualification](developer-test-contract.md).

The native verifier remains C++-owned in one shared compilation unit.

Component state: [compiler](../compiler/ARCHITECTURE.md), [libraries](../library/README.md),
[kernel](../kernel/README.md), [storage](storage.md). Next dependencies: [roadmap](roadmap.md).
