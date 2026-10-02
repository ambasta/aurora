# Native whole-system release inventory

## Requested destination

Aurora is intended to supply the complete system stack in its own safe, C++-inspired language: kernel and drivers, toolchain, libraries, package building, graphical system, terminal and everyday system programs. All Zen CPU generations and Navi/RDNA onward GPUs are the hardware coverage target, with integrated/discrete variants qualified separately. This is broader than a kernel project. **None of the following system facilities is delivered by the scalar/QEMU bootstrap.**

Names such as binutils, Portage and Wayland identify desired roles and useful capabilities. Aurora-native equivalents are redesigns under native object, package, process and IPC contracts, not promises to compile their existing C/C++ source, run Linux binaries, implement POSIX, or preserve a C ABI. Matching an external protocol or data format, if deliberately chosen, is distinct from adopting another OS's binary calling convention.

The current host C++ compiler, GNU tools, Python tests and assembly/C++ kernel bridge are visible temporary bootstrap dependencies. Their use does not satisfy the all-Aurora destination. Any irreducible machine instructions eventually need explicit, audited architecture intrinsics or a documented minimal machine-code boundary. Language safety cannot be obtained by hiding unchecked hardware operations behind renamed syntax.

## First testable system release

This is a proposed acceptance contract, not an estimate or a declaration that implementation exists. A first coherent release must build and run an explicitly listed native package set on a declared qualification platform; broader hardware coverage continues afterward.

| System component | Functional acceptance evidence |
|---|---|
| Compiler and native binary tools | Compiler compiles itself; assembler or native instruction encoder, linker, archive tool, symbol/section inspector and debugger information support build the kernel and applications without GNU tools on the target. Native ABI, relocations, TLS, unwind/error model and executable/module format are specified and tested. Dynamic linking may be deferred only if explicitly excluded from this release. |
| Runtime and standard libraries | Ownership-safe allocation/collections, text and Unicode, paths, streams, files, time, concurrency, errors and reflection support the package set. Target programs require no C runtime. Fault/resource-exhaustion tests cover library and trusted-runtime boundaries. |
| Kernel and driver services | Protected tasks, memory management, scheduling/SMP, capabilities/IPC, storage, input, network and the declared display/acceleration profile work together. Driver failures are contained, resources reclaimed and services restarted. Hardware gates remain those in [amd-support.md](amd-support.md). |
| Source-package system | Portage-like source recipes, dependency resolution, version/feature constraints, source integrity verification, build isolation, native toolchain selection and reproducible artifacts. Demonstrate bootstrap ordering, cycles/conflicts, offline cache use, interrupted builds and clear diagnostics. |
| Installation and updates | Explicit installation plan, recoverable boot entry, authenticated package/update provenance, atomic activation and rollback. Configuration migrations must state reversibility. User data is preserved by tested policies; disk selection and destructive steps require explicit approval. Failed boot/update recovery is demonstrated on disposable media before physical installation. |
| Display compositor and input | Native compositor/display-server role with isolated clients, surface/buffer ownership, output configuration, focus, keyboard layouts, pointer/touch where supported, clipboard authority, text input and accessibility foundations. Exercise a faulty client, compositor restart, hotplug and suspend/resume. No Wayland wire-compatibility claim is implied. |
| Fonts, rendering and audio | Text shaping/font rasterization and fallback display usable multilingual terminal/UI text; 2D composition and the declared GPU path are validated. Audio device discovery, mixing/streams, volume and hotplug have native services with bounded resource behavior. Third-party font/media assets and their licenses are distinguished from authored program code. |
| Terminal, shell and utilities | Terminal rendering/emulation, Unicode, keyboard input, shell parsing/quoting, pipelines, job control, signals or native equivalents, redirection and scripts work end to end. Provide native file/process/text/archive/system-inspection utilities sufficient for installation, development and recovery. Format/protocol compatibility is listed explicitly rather than assumed. |
| Services and user administration | Boot/service dependency management, supervised restart, logs, resource limits, authenticated user/session authority, clock configuration, network setup and recovery console. Test dependency failure, log exhaustion, session boundaries and restart loops. |
| Development and operations | Native build/test runner, package SDK/docs, debugger and usable crash diagnostics; security update/recovery procedure, release manifest, source identities and reproducible build records. Test developer edits through rebuilt application and updated system. |

## Release demonstration

From an audited bootstrap, build a target system, boot it on its named test platform, use its native terminal to rebuild the compiler and another application, resolve/build/install that application's dependencies, launch it graphically, exercise storage/network/audio, and perform a tested system update and rollback. Repeat critical paths with low memory, killed services, broken packages and interrupted operations. Publish excluded features and failed gates alongside successful logs.

Require an explicit list of trusted exceptions: firmware, CPU microcode, GPU firmware, language intrinsics and any remaining host build dependencies. Open cooperating firmware is a design assumption until a particular platform supplies and validates it. A wholly native OS implementation does not itself establish that every firmware component is written in Aurora or formally verified.

## Scope cannot be measured as “all Linux packages”

The Linux ecosystem is an evolving, externally maintained collection, not a fixed completion checklist. Name the native packages and workflows required for each release, then grow that inventory. Every claimed equivalent needs its own tests, security boundary and maintenance owner. The first coherent release above is a testable milestone; it does not replace the requested long-term complete ecosystem or full Zen/Navi-family qualification goal.
