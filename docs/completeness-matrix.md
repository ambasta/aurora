# Project status

## Current project state

None of the destination goals is complete. Compiler source-bootstrap builds are
restored; the complete validated-IR-to-x86 text backend runs in Aurora.
Self-hosting, final emitter qualification and full kernel migration remain incomplete.

| Destination | Status |
|---|---|
| Modern safe kernel | Experimental mixed C++/Aurora kernel; general protected services, SMP and full native implementation incomplete. |
| Safe C++-like language with TypeScript-like types | Aurora owns the frontend, static frame/call admission, initialization/service loans and x86 emission; C++ retains host conversion and dynamic verification; all 107 private bridge entries share one generated table/facts boundary; classes admit at most 8,192 direct fields, including no-leaf fields. Self-hosting and richer type/concurrency features remain incomplete. |
| Ideal filesystem and XFS compatibility | RAM storage and offline readers exist; mounted durable services, recovery and XFS read-write incomplete. |
| Framework Laptop 13 AMD support | Emulator foundations exist; active drivers, DMA isolation, power/recovery and physical qualification incomplete. |
| Native binutils/glibc/Mesa alternatives | Bootstrap compiler and core libraries exist; working reproducible native rebuild, toolchain/runtime and graphics replacements incomplete. |
| Applications, terminal and tiling desktop | Bounded serial and graphical consoles exist. General apps, terminal sessions and desktop incomplete. |

Current gate: original repository check and final-source GCC16 full
suite, followed by affected image/guest checks. See [development and qualification](developer-test-contract.md).

The BIOS console's bounded three-command session and editor are Aurora-owned;
native code retains sealed-session grants, PIC/UART transport and shutdown.

The native verifier remains C++-owned in one shared compilation unit; immutable
service authority is source-admitted and region identity is function-local, while
Aurora owns synchronous service-loan lifecycle and exact snapshot equality.
Local scalar initialization, logical object completion and receiver-field
initialization share that workspace with a fixed logical payload budget; resource
ownership and provenance remain native. The budget does not bound whole-process RSS.
Initialization/emission bridge declarations and register moves share one closed
bootstrap entry table; this removes duplicate host inventories, not the boundary.

Component state: [compiler](../compiler/ARCHITECTURE.md), [libraries](../library/README.md),
[kernel](../kernel/README.md), [storage](storage.md). Next dependencies: [roadmap](roadmap.md).
