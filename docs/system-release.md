# Native whole-system release inventory

## Requested destination

Aurora is intended to supply the complete system stack in its own safe, C++-inspired language: kernel and drivers, toolchain, libraries, package building, graphical system, terminal and everyday system programs. All Zen CPU generations and Navi/RDNA onward GPUs are the hardware coverage target, with integrated/discrete variants qualified separately. This is broader than a kernel project. **None of the following system facilities is delivered by the scalar/QEMU bootstrap.**

The explicit desktop destination is a native Sway-like tiling desktop environment, a Foot-like terminal, and a Wayland-like display protocol. These names express functional inspiration, not a claim that the named projects run here or a request to copy their implementation. Names such as binutils and Portage likewise identify desired roles and useful capabilities. Aurora-native equivalents are redesigns under native object, package, process and IPC contracts, not promises to compile their existing C/C++ source, run Linux binaries, implement POSIX, or preserve a C ABI. Matching an external protocol or data format, if deliberately chosen, is distinct from adopting another OS's binary calling convention.

The requested native library stack has two distinct layers: a libc-responsibility replacement runtime and a safe C++-recognizable standard library, both eventually written in Aurora. See [library responsibilities and dependency gates](library-stack.md); existing host libraries satisfy neither target.

The current host C++ compiler, GNU tools, Python tests and assembly/C++ kernel bridge are visible temporary bootstrap dependencies. Their use does not satisfy the all-Aurora destination. Any irreducible machine instructions eventually need explicit, audited architecture intrinsics or a documented minimal machine-code boundary. Language safety cannot be obtained by hiding unchecked hardware operations behind renamed syntax.

## First testable system release

This is a proposed acceptance contract, not an estimate or a declaration that implementation exists. A first coherent release must build and run an explicitly listed native package set on a declared qualification platform; broader hardware coverage continues afterward.

| System component | Functional acceptance evidence |
|---|---|
| Compiler and native binary tools | Compiler compiles itself; assembler or native instruction encoder, linker, archive tool, symbol/section inspector and debugger information support build the kernel and applications without GNU tools on the target. Native ABI, relocations, TLS, unwind/error model and executable/module format are specified and tested. Dynamic linking may be deferred only if explicitly excluded from this release. |
| Native platform/runtime layer | Aurora-authored startup, capability-scoped allocation, threads, I/O, time, math and OS interfaces replace libc responsibilities without C API/ABI or POSIX compatibility. Separate freestanding core, kernel and user-runtime profiles; specify native ABI/service boundaries. Test startup/termination, allocation failure, cancellation and resource reclamation without a target C runtime. Dependency gates are in [library-stack.md](library-stack.md). |
| Safe C++-recognizable standard library | Aurora-authored strings, containers, algorithms, ranges, ownership, concurrency and reflection over the native core/runtime. Preserve lifetimes, checked indexing and visibility rather than copying unsafe API contracts. Test iterator/view invalidation, Unicode/numerics, errors, races and resource exhaustion on the declared package set. An existing libc++ implementation is not assumed reusable unchanged. |
| Kernel and driver services | Protected tasks, memory management, scheduling/SMP, capabilities/IPC, storage, input, network and the declared display/acceleration profile work together. Driver failures are contained, resources reclaimed and services restarted. Hardware gates remain those in [amd-support.md](amd-support.md). |
| Source-package system | Portage-like source recipes, dependency resolution, version/feature constraints, source integrity verification, build isolation, native toolchain selection and reproducible artifacts. Demonstrate bootstrap ordering, cycles/conflicts, offline cache use, interrupted builds and clear diagnostics. |
| Installation and updates | Explicit installation plan, recoverable boot entry, authenticated package/update provenance, atomic activation and rollback. Configuration migrations must state reversibility. User data is preserved by tested policies; disk selection and destructive steps require explicit approval. Failed boot/update recovery is demonstrated on disposable media before physical installation. |
| Tiling desktop and display protocol | Native Sway-like tiling environment over a Wayland-like Aurora protocol: isolated clients, explicit surface/buffer ownership, GPU compositing, output configuration, tiling/workspaces, focus and window lifecycle. Demonstrate input/output hotplug, keyboard layouts, clipboard/selection authority, text/input shaping, accessibility navigation, and declared pointer/touch support. Exercise faulty clients, compositor restart, device removal and suspend/resume. No Sway configuration or Wayland wire-compatibility promise is implied. |
| Fonts, rendering and audio | Text shaping/font rasterization and fallback display usable multilingual terminal/UI text; 2D composition and the declared GPU path are validated. Audio device discovery, mixing/streams, volume and hotplug have native services with bounded resource behavior. Third-party font/media assets and their licenses are distinguished from authored program code. |
| Terminal, shell and utilities | Native Foot-like terminal with specified terminal-emulation behavior, Unicode rendering, keyboard/input-method handling, resizing, scrollback and selection. A native PTY-equivalent channel defines process/session ownership, streaming/backpressure, EOF/hangup and resize notification. Shell parsing/quoting, pipelines, job control, signals or native equivalents, redirection and scripts work end to end. Provide file/process/text/archive/system-inspection utilities for installation, development and recovery. POSIX PTY APIs, Foot configuration compatibility and external escape-sequence coverage are not assumed; publish the tested behavior. |
| Services and user administration | Boot/service dependency management, supervised restart, logs, resource limits, authenticated user/session authority, clock configuration, network setup and recovery console. Test dependency failure, log exhaustion, session boundaries and restart loops. |
| Development and operations | Native build/test runner, package SDK/docs, debugger and usable crash diagnostics; security update/recovery procedure, release manifest, source identities and reproducible build records. Test developer edits through rebuilt application and updated system. |

## Desktop workflow gates

The native desktop is a future release requirement, not an implemented bootstrap feature. Its acceptance suite must demonstrate:

- Tiling, workspace changes, focus traversal and window close/restart while application ownership and session boundaries remain intact.
- Keyboard and pointing-device hotplug, multiple keyboard layouts and input methods, repeat/modifier behavior, and recovery when a device disappears mid-input.
- Clipboard and selection transfer between two isolated clients with explicit authority, bounded payloads, cancellation, and no stale access after a session ends.
- Multilingual text shaping, combining characters, bidirectional text, font fallback and input-method composition in both UI and terminal workflows; specify behavior for ambiguous terminal cell widths.
- Keyboard-only navigation, focus reporting and a native accessibility interface usable by assistive clients; record gaps rather than claiming accessibility from a single navigation demo.
- GPU composition with validated buffer lifetimes and synchronization across resize, output hotplug, scaling and device reset, with an explicitly declared recovery or fallback path.
- Terminal/process integration across child exit, EOF, hangup, resize, sustained output, Unicode input, selection and shell job control through the native PTY-equivalent contract.

## Later runtime and FOSS ports

Once the language, native ABI, libraries, protected process model, package system and relevant device APIs are mature, select language runtimes, libraries and FOSS applications for native ports. This is a later workstream, not evidence that existing source packages compile today.

For each candidate, inventory dependencies and unsupported assumptions first. A port may require an Aurora-native compiler backend, runtime/OS API adaptation, replacement of a C-facing integration layer, or a safety-oriented rewrite in Aurora. Where an external language's semantics require its own runtime, specify how its memory, exceptions, threads and object lifetimes interact with Aurora capabilities. Do not import a C/source/ABI compatibility layer as an unreviewed shortcut or promise POSIX behavior. If a proposed port conflicts with the all-Aurora implementation goal, make that tradeoff explicit before accepting it.

Require an identified source version, license review and attribution plan before reusing any upstream code or assets; project names alone authorize neither copying nor a particular license treatment. Define port-specific functional tests, resource-exhaustion and isolation tests, packaging, update ownership, and remaining unsupported features. Prioritize a small useful package set whose native dependencies are ready instead of promising all FOSS at once.

## Release demonstration

From an audited bootstrap, build a target system, boot it on its named test platform, use its native terminal to rebuild the compiler and another application, resolve/build/install that application's dependencies, launch it graphically, exercise storage/network/audio, and perform a tested system update and rollback. Repeat critical paths with low memory, killed services, broken packages and interrupted operations. Publish excluded features and failed gates alongside successful logs.

Require an explicit list of trusted exceptions: firmware, CPU microcode, GPU firmware, language intrinsics and any remaining host build dependencies. Open cooperating firmware is a design assumption until a particular platform supplies and validates it. A wholly native OS implementation does not itself establish that every firmware component is written in Aurora or formally verified.

## Scope cannot be measured as “all Linux packages”

The Linux ecosystem is an evolving, externally maintained collection, not a fixed completion checklist. Name the native packages and workflows required for each release, then grow that inventory. Every claimed equivalent needs its own tests, security boundary and maintenance owner. The first coherent release above is a testable milestone; it does not replace the requested long-term complete ecosystem or full Zen/Navi-family qualification goal.

## Evidence history

Keep the milestone001 source manifest as a historical record of that exact checkpoint. Later desktop, porting or kernel work gets its own source identity, test evidence and release manifest; do not rewrite the earlier manifest to imply it contained later features. Report passed and missing gates rather than speculative completion percentages.

## Independent package metadata prerequisite candidate

The library-only [package identity token](package-identity-contract.md) candidate
implements bounded canonical name/version reading and comparisons in Aurora.
It deliberately grants no authority and handles no complete manifests, sources,
dependency constraints, build execution, installation, authentication or updates.
Its freestanding example and full independent oracle/focused Make gates pass with
the accepted M022 compiler; parent aggregate is required before acceptance. The native
source-package release row above remains a requirement.
