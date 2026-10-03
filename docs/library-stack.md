# Native runtime and standard library

## Required destination and present boundary

Aurora requires two native layers, eventually authored in Aurora:

1. A platform/runtime layer replacing the responsibilities normally expected from libc: program startup, allocation, threads, I/O, time, math and operating-system interfaces.
2. A safe, modern C++-recognizable standard library: strings, containers, algorithms, ranges, ownership types, concurrency and reflection.

“libc++-like” describes the second layer's role and API inspiration. It does not name the platform/runtime layer or mean adopting an existing implementation unchanged. Neither layer offers C source/API/ABI compatibility, POSIX compatibility or unchecked operations for compatibility's sake. Safety can require a different signature or an explicit failure result even where the operation feels familiar to a C++ programmer.

Most of these remain requirements. A first real freestanding `std.core` module now implements scalar `std::min`, `std::max` and checked `std::abs` in Aurora; it is exercised through imports and protected user images. See [core library](../library/README.md). It is not a general runtime or standard-library package set. The C++ host compiler's standard library and trusted kernel bootstrap helpers remain construction dependencies. Typed IR and controlled execution of compiled code in a user domain are prerequisites, not a native runtime, general process service or standard-library implementation. Exact current verification belongs to [verification.md](verification.md); no empty module tree or placeholder API counts as delivery.

## Three execution profiles

**Freestanding core:** value operations, checked numeric primitives, fixed-size storage, optional/result values and borrowed views whose required language features are available. It has no hidden allocator, filesystem, clock, scheduler, locale or process startup dependency. Allocating functionality is a separate layer. The eventual core must build and run tests with no host C runtime linked into target programs.

**Kernel profile:** uses selected core facilities plus explicit kernel mechanisms for physical/virtual memory, interrupts, synchronization and diagnostics. IRQ-safe APIs declare that they neither block nor allocate unpredictably. Kernel allocation is not user allocation; a kernel-only physical-memory capability must never appear in an ordinary application interface. Shared implementation is acceptable where the contracts agree, but kernel code must not acquire a dependency on user-space service startup.

**User runtime:** establishes a validated entry context, owned arguments/configuration and explicitly granted capabilities. It manages per-task/thread state, allocation domains, native service calls and orderly termination. Thread-local storage, initialization/destruction order, cancellation, panic/fault behavior and abandoned resources need specified contracts. A faulted process cannot be assumed to run destructors; the kernel/service layer still reclaims its authority. Loading dynamic modules remains a separate gated feature with type/descriptor lifetime rules.

## Native binary and service boundary

Specify an Aurora-native ABI for type layout, alignment, calls, returns, modules, relocation and lifetime/error conventions. Stable service messages must not depend on compiler-private class layout. Native syscalls or IPC stubs carry checked scalar fields and scoped handles, with versioned schemas, bounded messages, explicit failure and cancellation behavior. The temporary scalar bootstrap register convention is not that mature ABI.

A pointer supplied by a user task is not authority to access memory. A service must validate or copy the permitted buffer under a specified ownership protocol; asynchronous operations retain a grant/lease rather than a dangling borrow. Handle generations, rights and lifetime are checked at the boundary. The runtime cannot turn a guessed integer into a capability, bypass access through reflection, or silently reacquire a revoked resource.

## Allocation and lifetime safety

Allocators receive explicit region/quota capabilities and return ownership-bearing storage. Layout arithmetic checks multiplication, addition, size and alignment before committing resources. Construction failure releases only initialized state; moves transfer ownership; destruction and deallocation happen exactly once under the specified lifetime model. Exhaustion is an explicit result with tested cleanup, not unchecked null storage.

Arena reset must be impossible while live references escape, or use a defined checked invalidation scheme that cannot access reclaimed storage. Collections must specify borrow/iterator invalidation across growth, erase and mutation. Reallocation must not leave a valid-looking stale view. Shared ownership and cross-thread storage require synchronization and a declared cycle policy. A C++-familiar API does not authorize raw-pointer escape, unchecked indexing or unsafe allocator hooks.

## Text, numerics and everyday APIs

Strings distinguish bytes, Unicode scalar values and user-visible graphemes. Borrowed slices cannot split an encoded scalar silently. Specify encoding validity, normalization, case mapping, comparison and the version of Unicode data; locale-dependent behavior must be explicit. Length/capacity APIs state their units. Formatting and parsing have bounded allocation and unambiguous failure, including invalid input. UI shaping and terminal cell-width behavior build on these contracts but are not solved by a string container alone.

Numeric contracts cover checked integer arithmetic, conversions, parsing/formatting and eventual floating-point/math support. Specify rounding, NaN/infinity, domain/range failures and reproducibility expectations before implementing those APIs. Compare against trustworthy reference results and publish allowed error bounds where exact answers are not promised. Math APIs must not imply that unsupported compiler numeric types already exist.

Containers/algorithms/ranges preserve ownership and access rights during iteration, adaptors and callbacks. Lazy views cannot outlive their backing storage. Blocking I/O, clocks, files, networking and threads require explicit services/effects; pure algorithms must not gain ambient system authority. Concurrency APIs depend on a defined language memory model, checked transfer/share rules, synchronization and cancellation, not merely on a kernel thread primitive. Reflection follows the same visibility, lifetime and effect checks as direct calls.

## Dependency and acceptance gates

| Stage | Required dependencies | Acceptance evidence |
|---|---|---|
| Core types | Specified value/initialization semantics, aggregates and needed generics/lifetimes | Real modules used by compiled programs; positive/negative, overflow, bounds and lifetime tests without a target C runtime |
| Allocation layer | Checked ownership/drop rules, layout semantics, region/quota authority | Exhaustion, partial construction, alignment, stale view, arena reset and double-release tests; no ambient physical-memory access |
| Native user runtime | Native ABI/loader, protected task lifecycle, checked service boundary | Start/run/exit and abnormal termination; validated arguments/handles; cancellation and resource reclamation; no host runtime symbols |
| Collections and text | Core, allocation, generics/borrows, defined text data model | Reallocation/iterator tests, malformed encoding, text corpus tests, bounded parsing and reproducible data-version records |
| Threads and system I/O | Scheduler, IPC/service capabilities, language memory model | Concurrency/race-model tests, quotas, blocking/cancellation, partial I/O, clock semantics and service restart recovery |
| Full package-set library | Required layers plus reflection/effects and math contracts | Native compiler/application rebuilds use actual library APIs; equivalent-workload performance and failure tests; documented exclusions |

These are dependency gates, not a requirement to finish every layer before a small vertical slice. A useful first slice implements a real core operation, uses it from compiled Aurora and verifies its boundary. A prototype with a hard-coded result or an empty package manifest does not satisfy a library gate.

## Bootstrap removal, ports and licensing

Keep host build/test dependencies explicitly separate from target dependencies. Gradually replace them as the native compiler, encoder/linker, core and runtime can rebuild their successors. Prove absence of unintended target host-library/runtime dependencies with link/import inspection and isolated target execution. Self-hosting must rebuild a meaningful package set, not merely compile one file.

Native source ports may need language conversion, new backends, capability-based OS adaptation or safe rewrites. Existing binary ports are not promised: neither C ABI nor Linux/POSIX behavior follows from a familiar API. Do not add a compatibility shim without resolving its conflict with the clean-break requirement.

Before reusing upstream implementation code, algorithms expressed as code, tests or data, identify source versions and review applicable licenses, attribution and redistribution obligations. A familiar project name does not authorize copying. Prefer a traceable native design; any reuse needs a recorded decision and a maintenance/security owner. Historical milestone manifests remain immutable evidence for their original source snapshots.
