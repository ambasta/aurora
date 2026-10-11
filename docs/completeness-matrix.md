# Project status

## Current project state

Update this table in place. None of the six destination goals is complete.
Current behavior and limitations live with each component; historical results
belong in Git/PR history and retained run/CI evidence when available. A prior
passing checkpoint does not qualify changed source.

| Destination | Implemented foundation | Remaining acceptance gap |
|---|---|---|
| Modern safe kernel | BIOS/UEFI emulator boot, protected-domain fixtures, bounded scheduling and copied request/reply IPC; five Aurora policies plus a persistent Aurora-owned simple-UEFI console, within trusted C++/assembly hardware adapters | General protected-program lifecycle, capability/file services, SMP, broader native implementation and assurance |
| Safe C++-like language with TypeScript-like types | Checked values, modules, classes, direct copied method returns through one class field, bounded generics/overloads, readonly views, runtime-sized byte and copied-class ownership, typed AST/frame/argument arena and hosted Aurora scalar/byte-string, call, postfix and non-template aggregate parsing with constructor initializer expressions, move-only classes, synchronous owning-object helpers and sealed exclusive ConsoleSession/DisplaySession borrows | General ownership/borrowing, concurrency, key/mapped/conditional types, richer checked reflection, optimizer and self-hosting; no general safety/performance proof |
| Ideal filesystem and XFS compatibility | Host crash model, runtime-capacity RAM sector device, offline XFS geometry/root/inline-extent readers | Real transport, mounted file services, persistence/recovery/GC and XFS read-write; no target filesystem is usable yet |
| Framework Laptop 13 AMD system | Emulator boot/discovery, owned page/pin preparation, test-only AMD references and bounded emulator model diagnostics | Actual DMA conformance/isolation, active drivers, device power/recovery and complete-machine physical qualification; no supported physical tuple |
| Native binutils/glibc/Mesa alternatives | Host-bootstrap compiler with compact payload copies, copied-record ABI facts and explicit referenced-reflection image emission, Aurora core/byte/text/JSON modules and bounded package metadata tools | Native assembler/linker/toolchain, complete platform runtime and standard library, graphics stack and reproducible native rebuilds; no C/POSIX/ABI compatibility promise |
| Useful apps, terminal and tiling desktop | Aurora-owned simple-UEFI serial editor/presentation and bounded serial-input graphical console; BIOS diagnostic prompt and scoped protected uppercase, volatile note and typed named RAM-file reads/atomic replacement with revision invalidation, authority fail-stop and fault/budget recovery; bounded text/JSON consumers | General program and file services, terminal sessions, display/input/compositor, text shaping, tiling/workspaces and usable packaged apps |


## Qualification boundary

Every merge/release still requires final-source GCC 16 `full`, independent review,
normal BIOS/UEFI images and real smokes, plus affected admission/fault/recovery/
restoration gates. See [development and qualification](developer-test-contract.md).
Validation runs locally with the selected pinned tools; container packaging is
separate. Meson cleans its owned successful test scratch while retaining failed
or explicitly kept runs. Graphical and Event smoke share successful-output
retention while preserving failures and explicit keeps; cleanup does not reduce
qualification coverage.
The Make shortcuts preflight pinned tools and refresh old default build options
without wiping files; explicitly selected configurations remain user-controlled.
No CI replacement, physical AMD support, general memory-safety proof or
measured equivalent-C performance is established.

Implementation: [compiler](../compiler/README.md), [libraries](../library/README.md),
[kernel](../kernel/README.md), [consoles](native-console-service.md),
[graphical output](framebuffer-console.md), [storage](storage.md).
Next dependencies and acceptance gates: [roadmap](roadmap.md).
