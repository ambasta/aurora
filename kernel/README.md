# Running kernel foundations

This is a **temporary trusted C++23/assembly bootstrap**, not Aurora's final
language-native kernel or a claim of Rust-level memory safety. It compiles and
executes the separate Aurora source-language program. No C source compatibility,
C runtime, libc, or exported C object model is supplied. Scalar assembly symbols
are a disposable bring-up seam, not a permanent platform ABI.

## Runtime-sized CPU byte owners

The separately selected `owned-bytes` UEFI profile grants Aurora runtime-sized
allocations from the existing physical page pool, with four fixed owner records,
whole-page scrubbing and explicit cleanup. See the
[bounded contract](../docs/kernel-owned-bytes.md) and
[focused results](../docs/kernel-owned-bytes-results.md) for current gates and limits.
Raw kernel resize is a [bounded extension](../docs/kernel-owned-resize.md) with
[fresh focused qualification](../docs/kernel-owned-resize-results.md). User allocation and device activation remain outside this profile.
A reconstructed [readonly-view increment](../docs/kernel-owned-views-results.md)
has fresh local build/host/guest gates; final acceptance is recorded separately.

## Build and verify

For the shortest normal-boot commands and tool overrides, see
[local development](../docs/local-development.md): `make run` and `make run-uefi`
build and verify bounded, headless boot self-tests.

The separate opt-in `make console` profile opens a bounded BIOS serial prompt
with `help`, `status` and `exit`. It uses a 64-byte ASCII line editor and sleeps
on UART interrupts while idle. See the [console contract](../docs/kernel-console-contract.md)
for its trust boundary and focused checks. `make console-uefi` adds a normal-payload
serial prompt with admitted LAPIC-woken polling and UART interrupts disabled; see
the [UEFI contract](../docs/uefi-console.md) and [results](../docs/uefi-console-results.md).
The simple UEFI profile now owns its line editor, command parsing and human
presentation in one persistent Aurora frame, using the
[sealed console service](../docs/native-console-service.md). Its trusted adapter
retains boot, MMIO, interrupt/wake and quiescence authority. BIOS and the protected
command profile have separate, explicitly retained legacy editors.

The ordinary run commands remain self-tests. Neither console is a desktop or general process shell.

From the repository root:

    ./scripts/kernel-build.sh
    ./scripts/kernel-tests.sh
    SANITIZE=1 ./scripts/kernel-tests.sh
    ./scripts/kernel-smoke.sh
    ./scripts/kernel-smoke.sh --fault
    ./scripts/kernel-smoke.sh --page-fault

Build dependencies: x86-64 GNU g++ with C++23 support, Make, GNU binutils
(including nm), Python 3, Bash. Emulator tests also require QEMU system x86-64,
PC BIOS firmware, and GNU timeout. `QEMU` selects an executable; `QEMU_DATA`
selects its firmware directory. Tests use software emulation without root/KVM.
Do not run image-mutating scripts concurrently; they share build outputs.
Fault tests restore a normal image on exit, including failure exits.


### Host-toolchain boot layout

The supported build workflow targets x86-64 Linux with GNU tools selected on
`PATH`: `g++` with C++23, GNU Make, `as` supporting `--32` and `--64`, GNU `ld`
with `elf_i386`/`elf_x86_64` emulations and `--orphan-handling=error`, `objcopy`,
`objdump`, `nm`, Python 3 and Bash. The focused regression also requires assembler
`-mx86-used-note` (available since binutils 2.32) and
`--generate-missing-build-notes`. This is a tool-capability contract, not a claim
that every GNU release or distribution has passed the full kernel suite. A
C++ compiler configured for a distribution is not itself a target-hardware limit.

UEFI PE linking explicitly requests `--dynamicbase --nxcompat`; the required
relocation/NX header flags must not depend on the linker build defaults.
Freestanding C++ flags explicitly select `-fcf-protection=none` and
`-mstringop-strategy=libcall`: distro CET defaults must not add unmodeled
instructions, and compiler-generated bulk copies/clears use the admitted memory
primitives. UEFI stack admission retains both GCC `-fstack-usage` (`.su`) and
`-fcallgraph-info=su` (`.ci`) output. Each complete source location and signature
must join one exact assembler symbol in that object; ambiguous clones fail closed.
The object/link byte and relocation checks and linked-instruction stack analysis
remain authoritative. Profile build manifests include both metadata files;
standalone stack reports record current source hashes but are not compilation
provenance. Missing `.ci` files require rebuilding, not a display-name fallback.
Console admission profiles share one scalar instruction configuration, including
GCC's byte `orb` form; stack-pointer writes, frame balance and unknown instructions
still pass through the same operand/control-flow guards. Shared qword `testq`
reads preserve register/carrier facts and invalidate tracked flags, with plain
64-bit registers or base/displacement memory operands; other forms fail closed.
Register-only qword `bts` invalidates destination/flag facts; memory bit-set forms
remain unsupported. This models stack effects, not memory authority or copied-field
provenance.
A PE/ELF layout check alone does not establish those stack guarantees.

BAR preparation retains its reviewed outer paths and reserves. Its queue-helper
bound sums a finite acyclic GCC `.ci`/`.su` closure with exact object/link joins
and matching linked direct edges. Unknown/indirect callees, cycles and missing
frames reject; absorbed bodies are charged to their callers. Existing machinery
checks assembly leaves. This trusts compiler-local switches, unlike the console
CFG proof; standalone reports are not fresh-build receipts. The native queue
runner checks fresh PCI emission and representative corruptions.

The recursion proof tracks the actual callee-saved level register and its
entry-relative spill lifetime across the CFG, including untouched early returns.
Its sole nonlocal byte-marker store depends explicitly on the reviewed C++
`visited` array's private lifetime and checked slot bound. Fixed source hashes
and exact compiler/object associations bind that invariant; this is not an
independent arbitrary-pointer memory proof. Other nonlocal stores reject.

Graphical capture admission v3 binds current build provenance and checks bounded
image/stack/private-ABI structure plus fourteen typed, aligned, disjoint BSS
state fields. Its capture evidence explicitly says `structure-only` with hosted
and guest behavior qualification pending. Historical capture object/tool hashes,
absolute instruction replay and encoded whole-build test snapshots are retired;
selector/authority/pixel/diagnostic behavior still requires hosted and actual
guest gates. The separate paired-walker exact-body/storage/recursion fixtures
remain narrow compiler-emission assumptions, not blanket compiler independence
or arbitrary machine-safety proof. See the [capture contract](../docs/framebuffer-console.md).

`kernel/boot.ld` fixes the BIOS `.text` at 0x7c00 and requires exactly 512 bytes
with `_boot` first. The linker helper explicitly disables generated build IDs,
discards only named GNU metadata, rejects other orphan sections, and rejects
separate initialized/uninitialized storage. It does not truncate or pad a bad
binary to disguise a layout failure. Existing image validation still checks the
BIOS signature, packet and complete kernel image before packaging.

Run the actual production linker and its adversarial layout checks without
building the compiler or kernel:

    make test-boot

The regression tests host-default, forced-off and forced-on GNU x86 property
notes, generated GNU build attributes, byte equality with the previous relocated
BIOS text, exact entry/signature/EDD packet and nine rejected invalid layouts.
Checks remain active under `python3 -O`; all scratch outputs are temporary.
Debian GNU binutils 2.44 passes these focused checks. Gentoo binutils 2.47p1
(2.47.0) was reported to produce a 512-byte `.text` plus an allocated 40-byte
`.note.gnu.property`, yielding a 1064-byte raw image with the previous default
linker layout. The affected failure class was reproduced with forced GNU notes. The fix then
passed a production kernel build, ordinary/optimized image validation, actual
normal BIOS boot and controlled divide-fault BIOS boot, using the unchanged
accepted compiler. The fault script restored the exact initial normal image
bytes. Boot size is 512 bytes and the normal kernel payload is 45,808 bytes.
Independent focused review also verified the preserved instruction bytes and
additional rejected layouts. The user reported a successful PR25 Gentoo rebuild
on 2026-10-05; this is not an independently observed log or a boot result. The
standalone linker fix did not rerun the full aggregate. The later
[combined checkpoint](../docs/kernel-round-robin-integration-results.md) passed
fresh full native and all-mode emulator qualification.

For a host-toolchain failure, retain the failed files and report:

    as --version | head -n 1
    ld --version | head -n 1
    objdump -h build/boot.o
    wc -c build/boot.bin

Host toolchain verification is separate from target-machine qualification.
Physical AMD support remains unverified; the Zen/Navi/RDNA target and the
emulator-only safety boundary below are unchanged.

Normal smoke requires exit 33, exact language result 42, E820/page/exception
self-test markers, and AURORA_BOOT_OK with no failure/fatal marker. Fault smoke
requires exit 35, the exact injected vector/error diagnostic, and fail-stop.
Logs: build/kernel-serial.log, kernel-fault.log, kernel-page-fault.log.
Missing QEMU means blocked verification, not a pass.

## Implemented and exercised

- A 512-byte BIOS sector loads 127 sectors (65,024 bytes) to physical 0x10000.
- BIOS E820 discovery passes up to 32 entries in a bounded buffer. Bad signatures,
  short entries, and capacity overflow invalidate the map. EBX zero or BIOS CF
  ends enumeration; an empty map fails the kernel's arena verification.
- Three zeroed tables at 0x1000/0x2000/0x3000 map the first 2 MiB; A20, PAE,
  long mode and a private GDT are enabled. The stack begins at 0x90000.
- Kernel entry clears BSS before entering C++.
- A real 256-entry IDT routes CPU exceptions through register-preserving assembly.
  A breakpoint probe resumes and checks all 15 general-purpose registers and
  the direction flag. Unexpected vectors emit diagnostics and halt.
- Separate QEMU images inject divide-by-zero (vector 0, no CPU error code) and
  an unmapped read (vector 14, CPU-pushed error code), exercising both frame paths.
- An allocator owns 128 physical 4 KiB frames in [0x100000,0x180000). E820 must
  describe this entire range as usable, with no overlapping enabled reserved
  entries. The pool is disjoint from the loaded kernel, tables, handoff and stack.
- Move-only, generation-tagged leases validate owner, live state, index and
  generation, and allocator-incarnation epoch. Copy and move-assignment are
  disabled. Release invalidates a lease; dropped leases leak rather than permit
  aliasing. Generation wrap retires a slot; exhausted incarnation IDs reject
  initialization.
  Same-address allocator replacement cannot resurrect an old token.
- Runtime tests write every byte in all 128 physical pages, check frame identity,
  fill the pool, reject exhaustion/foreign ownership/double release/moved and
  retired leases, recycle pages and return to zero live allocations.
- Hosted tests cover invalid ranges/overflow and 10,000 deterministic model steps
  with pairwise alias checks; optional AddressSanitizer/UBSan instrument this
  actual shared allocator implementation.
- COM1 prints the compiled Aurora function's actual return value, 42.

Image validation checks exact ELF fields, loader bounds and zero unresolved
symbols, with 14 malformed-image/BIOS-packet controls. Shared smoke validation has 19
positive and 134 negative transcript regressions and stays active under Python -O.

## Deliberate limits

This fixed BIOS transport is disposable emulator scaffolding, not Aurora's
proposed firmware contract, installer, filesystem or general disk driver. Never
write this image to a physical disk. Scripts create a regular 1 MiB file only;
they do not alter any host bootloader or kernel.

The allocator is single-CPU, bounded and explicitly released; it is not a heap,
virtual-memory manager, or concurrent allocator. Recycled frames are not yet
scrubbed: the pool must not cross security domains. The C++ bootstrap can still
forge raw addresses and is trusted. Lease validation is not hardware isolation.

The newer protection milestone below adds a TSS, dedicated double-fault IST,
W^X and one controlled ring-3 probe. That gate keeps external IRQs masked.
The later opt-in preemption gate below adds a bounded local APIC scheduler;
general SIMD/FPU context management remains absent. Unexpected faults
fail-stop. There is no complete process isolation, IOMMU, IPC or SMP, and no
storage/network/GPU/input driver compatibility is claimed.

All Zen generations and Navi/RDNA integrated/discrete GPUs are target families,
not verified hardware support. The QEMU baseline uses no optional AMD extensions.
Capability services, isolated/restartable drivers, device protocol negotiation,
secure page domains and language-native implementation remain future work.

## Verified emulator environment

Tests passed with QEMU 10.0.13 (Debian 1:10.0.13+ds-0+deb13u1), SeaBIOS 1.16.3,
`pc` machine and `qemu64` CPU. Official Debian HTTPS packages and dependencies
were checked against package-index SHA-256 digests and extracted into /tmp;
nothing was installed into the host or bundled with this project.

On the original workspace, prefix each smoke command with:

    LD_LIBRARY_PATH=/tmp/aurora-qemu/root/usr/lib/x86_64-linux-gnu \
    QEMU=/tmp/aurora-qemu/root/usr/bin/qemu-system-x86_64 \
    QEMU_DATA=/tmp/aurora-qemu/firmware

Elsewhere use a normal QEMU installation including PC BIOS firmware. Version
output alone does not verify boot. Local temporary packages are not a portable
dependency cache or part of the product.

## Protected mapping and controlled ring-3 milestone

The newer checkpoint replaces the earlier permissive long-mode mapping after
initial bring-up. The boot sector still needs a temporary writable/executable
huge page; no user code runs during that phase. Protection activation is mandatory
before any controlled ring-3 entry. CPUs without CPUID NX support fail closed.

The replacement uses explicit 4 KiB identity pages, with all unspecified leaves
absent. CR0.WP enforces supervisor write permissions; EFER.NXE enforces NX.
ELF sections are page-separated and validated as RX, R and RW segments.

- Kernel text: supervisor read/execute, never writable
- Constants and E820 handoff: supervisor read-only, non-executable
- Kernel data, page tables, allocator arena: supervisor read/write, non-executable
- Main stack: [0x88000, 0x90000), with absent guard below
- TSS.RSP0 entry stack: [0x82000, 0x86000), with absent guard below
- Double-fault IST1 stack: [0x7c000, 0x80000), with absent guard below
- Controlled user code: [0x1d0000, 0x1d1000), user read/execute, never writable
- Controlled user stack: [0x1e0000, 0x1e4000), user read/write, NX, guard below

The mapping API permits no writable-executable mode, no duplicate remapping and
no physical aliases. It remains bounded to the first 2 MiB and is not yet a
runtime address-space manager. Upper levels permit user traversal; each leaf
applies the actual domain permission. Null and unused pages are absent. Kernel
image, stacks and user buffers are checked against E820 before protection setup;
contradictory usable/reserved records are rejected regardless of ordering.
The handoff decoder is shared with sanitizer-tested hostile-map unit tests.

A private GDT includes ring-0/ring-3 descriptors and a 64-bit TSS. Ring-3 entry
uses a sanitized integer-register context, RFLAGS with IOPL=0/IF=0, a dedicated
user stack, and copied relocation-free assembly test code. The TSS I/O-map offset
lies beyond its limit, denying user port access. An explicit DPL3 interrupt gate
provides exactly one controlled test return. It validates the saved CPL, expected
probe state, user instruction range, value 42 and privileged entry-stack range;
assembly resumes only a kernel-owned saved continuation. User-supplied stack
frames are not used to choose the privileged return target.

Run all actual CPU gates sequentially:

    ./scripts/kernel-protection-smoke.sh

Individual new modes for kernel-smoke.sh:

- --wp: supervisor text write rejected, page fault error 3
- --nx: supervisor data execution rejected, page fault error 17
- --stack: corrupted main stack causes double fault on the dedicated IST
- --no-nx: unsupported CPU rejected before protected/user execution
- --user-read / --user-write: kernel text denied, page fault errors 5/7
- --user-cli / --user-io: privileged operation denied, general protection error 0
- --user-code-write: user executable page write denied, page fault error 7
- --user-nx: user stack execution denied, page fault error 21

The original protection suite included normal/divide/unmapped-page gates, 13 total.
The compiled-program extension below adds three more adversarial modes. Fault
validation checks exact vector/error bits, origin privilege, handler-stack range,
and CR2 denied address where applicable. Expected failure is not enough without
these checks. Fault builds restore the normal image. Hosted tests cover 511 page
mappings, invalid/default-deny/W^X rules, malformed and conflicting firmware
records; transcript checks are extended by the compiled-program milestone below.

### What this still does not establish

The assembly probe is an integer-only privilege-boundary check in trusted temporary
C++/assembly. The compiled-image runner below extends it, but does not provide a general executable loader, process/task model,
general syscall interface, scheduler, multi-address-space isolation or security
proof. FPU/SIMD state, FS/GS/TLS lifecycle, preemption, SMP, speculative-execution
mitigations, DMA isolation, teardown and resource accounting remain unimplemented.
Do not run arbitrary applications under this boundary. External IRQs remain
masked. IST is assigned to double fault only; nested NMI/IST fault handling is
not a general recovery mechanism. Other unexpected faults terminate the emulator
test rather than restart a service. Physical AMD support is still unverified.

## Compiled safe-C++ user images and contained language faults

The kernel now runs three separately compiled and linked Aurora safe-C++ programs
from tests/kernel-programs/. This extends the assembly protection probe; it does
not replace the older adversarial tests.

- clean.au initializes a fixed array, traverses it with a checked while loop,
  calls imported std.core/std::max, and returns i64 value 42.
- bounds.au reaches the compiler's bounds-check trap on an index equal to length.
- overflow.au reaches the compiler's signed-arithmetic overflow trap.

Each image combines compiler output with a narrow trusted no-argument launcher.
It is linked independently at one of 0x1b0000, 0x1b1000, 0x1b2000. The build rejects
writable global storage, unresolved symbols, non-RX load segments, wrong entries,
and images larger than 4 KiB. The verifier checks extracted bytes against the ELF
load segment. `as -L` and `ld --discard-none` retain the emitted bounds/overflow
labels; verification requires both labels to point to distinct UD2 opcodes and
the authorized return label to follow the exact INT 0x81 instruction.

Before protection activation, the static installer checks every contract, copies
all image bytes, zeros page padding and verifies the complete copy. Thereafter
the immutable images have no writable alias. E820 must grant their backing regions.
The first compiled-image checkpoint shared one user domain; the separate-domain
extension below now maps only each active owner's image and private stack.

### Scalar return authority

INT 0x81 has exactly one meaning: finish the outstanding image and return one i64
bit pattern in the temporary result register. It accepts no pointers, buffers,
lengths, object handles or user-selected privileged continuations. The fixture
entry signature is fixed by the trusted build (`auto aurora_user_main() -> i64`);
this is not a public source-level foreign-call or C ABI facility.

Before each entry, the kernel scrubs and reads back the entire guarded user stack.
The assembly launcher zeros all 15 integer registers, uses fixed user selectors
and IOPL=0/IF=0 flags, and stores its own privileged continuation. The user-side
launcher checks zeroed registers and the top stack word before calling generated
code with the compiler's required stack alignment.

A single outstanding run owns an immutable value-copy of its verified contract.
The gate requires the exact user CS/SS, an aligned in-range user stack, permitted
flags, a complete aligned exception frame on TSS.RSP0's supervisor stack, and
the precise linked return instruction address. The ordinary return requires the
original user stack top. All i64 bit patterns are valid; the test separately
checks the computed value is 42. Knowing the return instruction is not a secret
capability or a proof of program correctness. Authority is only to finish the
currently active run with a scalar result.

Assembly resumes the kernel-owned saved stack and register continuation; it never
uses a user pointer as a privileged return address. The accepted event consumes
the outstanding authority. Host tests reject nested/replayed events, wrong image
addresses, selectors, privilege, flags, stack/frame ranges and changed metadata.
Contracts are copied, so caller lifetime or later edits cannot alter an active run.

### Narrow containment, demonstrated continuation

Only a user-origin #UD at the active image's exact verified bounds or overflow
label is classified as that language fault. Error codes, selectors, flags and
stack context are checked before accepting it. The observed fault PC is compared
against linked metadata again in the emulator validator. This identifies a
compiler trap site; it is not a generic illegal-instruction catcher or a formal
proof of the whole compiler's semantics.

The normal gate executes this order:

1. Clean array/loop image returns 42
2. Bounds image faults and returns a typed bounds outcome to the kernel
3. Clean image returns 42 again after fresh stack/register setup
4. Overflow image faults and returns a typed overflow outcome
5. Clean image returns 42 again
6. The clean domain is torn down and recreated with scrubbed reused frames; its new handle runs the clean image again

Three additional fail-closed emulator modes distinguish containment from unsafe
recovery: --program-bad-return rejects INT 0x81 at an unauthorized return PC;
--program-unknown-trap rejects an unrelated user UD2; --program-kernel-trap executes
the exact known compiler trap at kernel privilege and verifies it remains fatal.
These test-only assembly injections do not add unsafe syntax to Aurora.

`./scripts/kernel-protection-smoke.sh` now runs 19 real emulator modes. A normal
image is restored after fault variants. Each log has an adjacent .metadata.json
receipt preserving that variant's linked trap addresses even after restoration.
The user-image verifier includes 27 malformed-image/metadata controls. Shared
transcript validation has 19 positive and 134 negative cases, including exact
containment order and clean execution after both faults. Hosted policy tests can
run under ASan/UBSan with `SANITIZE=1 ./scripts/kernel-tests.sh`.

For isolated compiler-integration experiments, AURORAC can select an already-built
compiler executable; ordinary builds still run `make -C compiler`. Record its
hash and rerun against the final compiler before claiming a checkpoint verified.

### Remaining assumptions

This is a trusted build-time image installer and a sequential integer-only test
runner. This historical sequential gate has no arbitrary executable loader or
complete process model, cross-domain copy service, heap lifecycle or general
syscall API. A hung program cannot be interrupted by this sequential runner;
the separate preemption mode below adds bounded timer cancellation. Unexpected
faults, stack exhaustion and invalid returns still fail-stop; only the two known
compiler traps are contained. FPU/SIMD and FS/GS/TLS lifecycle, asynchronous state,
SMP, DMA isolation and speculative-execution mitigations remain outside this gate.
The wrappers, kernel and toolchain are still trusted bootstrap machinery rather
than a verified language-native OS. Physical AMD hardware remains unqualified.

## Sequential private address spaces

Three bounded domain slots now own distinct CR3 roots and separate leased stack
frames. Each run still executes one controlled build-time fixture synchronously.
This is a hardware address-space foundation, not a preemptive scheduler or a
complete process lifecycle.

### Resource and mapping contract

Each slot owns four static, supervisor-only page-table pages (PML4, PDPT, PD and
4 KiB leaf table). These table pages are never returned to the general frame pool.
Each live domain also holds four move-only physical-page leases for its 16 KiB
user stack. At most three domains and twelve stack frames are live. Each image
has one live owner; its immutable code backing is pinned, not allocator-recycled.

The manager accepts only the initialized, empty 128-frame arena at
[0x100000,0x180000), already checked against E820. Frame addresses are checked
again before raw memory access. The allocator object must live for the whole
kernel session; main supplies its static kernel allocator. There is no public
user API for injecting an allocator, constructing a root or selecting a CR3.

A private root contains exactly:

- The common supervisor kernel text, constants, data, privileged stacks, E820
  handoff and non-executable supervisor frame-pool view, with unchanged permissions
- Its own linked image page as user RX
- The guarded user-stack virtual range [0x1e0000,0x1e4000), mapped to that owner's
  four leased physical frames as user RW/NX

The old assembly-probe user mappings are omitted. Other compiled image pages are
absent. There is no shared user-executable trampoline page: every image contains
its own narrow launcher. The kernel root's read-only views of pinned image backing
are explicitly user-resource views and are not copied into other private roots.
Kernel handler/return code is common supervisor RX, never user accessible.

The kernel can inspect private stack frames through supervisor RW/NX direct
mappings, but user code cannot. Mapping policy rejects a writable/executable
physical alias in either insertion order, including supervisor writable aliases
to user executable code. Private code has no writable alias in any root.

### Active-root and teardown authority

Before activation, the root is checked against the entire expected leaf policy,
including identical common kernel mappings, exact owner stack frames, no extra
user mappings and no global leaves. CR4.PCIDE must be clear. Every CR3 switch
flushes this CPU's nonglobal translations; no PCID reuse is attempted. The root
read back from hardware must equal the selected owner root.

Return/fault acceptance requires both the existing exact scalar/trap contract and
the active handle's actual hardware CR3. The kernel restores its own root before
reporting an ordinary result or contained bounds/overflow outcome. The saved
privileged continuation and TSS entry-stack contract remain unchanged.

Opaque handles use monotonically unique stamps. A destroyed/reused slot or even
a same-address reconstructed registry cannot resurrect an old handle. Stamp
exhaustion fails closed. Active-root creation, scrubbing and teardown are rejected.
Teardown requires the inactive ready state and the verified kernel root, scrubs
and reads back every stack byte, clears the old tables, revokes the handle, then
releases leases. Failed partial allocation similarly scrubs acquired frames before
releasing them; unverifiable state is retained rather than silently reused.

This reasoning is deliberately single-CPU with interrupts masked. It is not an
SMP TLB-shootdown protocol or asynchronous revocation mechanism.

### Executed acceptance gates

The normal boot records distinct physical roots and disjoint leased stacks,
runs all three compiler-generated programs under their own CR3, and checks each
program actually wrote its own physical stack. Every accepted return and language
fault records the matching active root followed by kernel-root restoration.

After the clean domain has run, the gate destroys it, reads the released frames
to confirm zeroing, rejects its stale handle, then exhausts the pool until only
two frames remain. A four-frame creation must roll back without leaking either
frame; recognizable old bytes in both rollback frames must be zero afterward.
Recreation reuses the earlier physical frames with a new handle, rejects the old
handle again, and executes the clean program successfully. Final teardown returns
the allocator to zero live leases and leaves the kernel root active.

Three new actual-CPU denial modes extend the earlier sixteen gates:

- --domain-code: executing another domain's image faults with user instruction-fetch
  page-fault error 20 at the foreign image address
- --domain-stack: reading another owner's physical stack via the supervisor direct
  mapping faults with page-fault error 5 at the verified foreign frame
- --domain-root-mismatch: a test-only kernel injection changes CR3 before an
  otherwise valid user return; the gate rejects it rather than accepting stale
  domain authority

These are trusted adversarial test shims, not unsafe language features. The clean
fixture now imports std.core and executes std::max inside its private RX image;
all fixtures still use the source language's ordinary checked operations.

Run all nineteen modes with ./scripts/kernel-protection-smoke.sh. Hosted domain
policy and alias tests are included in ./scripts/kernel-tests.sh and its sanitizer
mode. Emulator transcript checks require exact CR3 transitions, nonoverlapping
stack ownership, both code/data denials, reuse evidence and final teardown.

The enlarged bootstrap remains bounded: its EDD packet now reads 127 sectors (63.5 KiB)
from LBA 1 to physical 0x10000, within one 64 KiB transfer window. Image validation
checks the actual assembler-located packet's alignment, count, destination and window plus
malformed-packet controls. No host disk or bootloader is modified.

### Still outside the claim

Roots and code slots are static; stacks are explicitly leased and reclaimed.
There is no arbitrary image loading, pageable VM, user heap, general threads,
permissions service, signal delivery, shared-memory service, SMP, DMA isolation,
FPU/TLS lifecycle or speculative-execution assurance. Only the specified compiler
traps are contained. Other faults remain fail-stop. This checkpoint demonstrates
bounded sequential hardware domains on QEMU, not complete process isolation or
qualification of physical Zen/RDNA hardware.


## Bounded single-CPU preemption gate

This opt-in mechanism extends the owned-address-space foundation with an actual
local APIC timer and a small round-robin integer-context runner. Build with
`KERNEL_TEST_SCHEDULE=1 ./scripts/kernel-build.sh`, or run
`./scripts/kernel-scheduling-smoke.sh` for its nine real emulator modes. The
existing `./scripts/kernel-protection-smoke.sh` still runs all nineteen earlier
modes. Neither wrapper substitutes transcript-only fixtures for emulator runs.

### Platform and architectural contract

The harness requires a single QEMU `pc` BSP, xAPIC CPUID/MSR/PAT support, an already
enabled xAPIC at IA32_APIC_BASE address `0xfee00000`, no x2APIC mode, and PAT index3
encoded UC. Advertised multi-logical-CPU configurations are rejected; the runner
also explicitly launches QEMU with `-smp 1`. A zero CPUID logical-count field is
accepted for older non-HT CPU models where that field is not meaningful. This is
a checked emulator platform contract, not ACPI/MADT discovery or a claim that a
Framework 13 Ryzen 7840U has been qualified.

The additional shared page-table branch maps exactly one MMIO page supervisor
RW/NX, nonglobal, with PCD/PWT selecting the verified UC PAT entry. It is identical
in every root. The first-2-MiB ordinary-memory policy remains unchanged. The
adapter validates the complete aperture tables and avoids cacheable aliases.
User access to this page has a real protection-fault gate.

A one-shot countdown uses divide16 and an arbitrary bounded initial count. The
count is not milliseconds or a scheduler timing guarantee; no APIC frequency,
ARAT, invariant TSC, TSC-deadline feature or physical Zen behavior is assumed.
The legacy PC PIC and unrelated local sources are masked. Unsupported startup
state, unexpected interrupts and spurious vectors fail-stop.

Primary architectural reference checked for implementation: [Intel SDM Volume3A,
chapter10](https://www.intel.com/content/dam/www/public/us/en/documents/manuals/64-ia-32-architectures-software-developer-vol-3a-part-1-manual.pdf),
especially §10.5.4 (countdown/divide and stop semantics), §10.8.5 (IRR/ISR/EOI)
and §10.9 (spurious interrupts), plus chapters6 and11 for interrupt entry and
memory types. This defines the adapter mechanics; emulator tests establish only
the behavior of the tested QEMU model. AMD physical qualification still requires
its current APM/PPR, firmware discovery and machine-specific tests.

### Context, continuation and timer authority

Kernel code remains non-preemptible: IF is clear except in the tiny labeled
pending-IRQ drain window. User IRET frames have IF set. Vector64 is a DPL0
interrupt gate. A user software INT64 faults; a privileged software-forged INT64
also cannot acquire scheduling authority. Delivery requires the active domain's
actual CR3, a complete aligned frame on the guarded TSS.RSP0 stack, approved
selectors/stack/RFLAGS and an RIP inside that domain's exact linked image. The
APIC timer ISR bit must be set, with no unrelated in-service/pending source.

All15 GPRs, RIP/RSP/selectors and RFLAGS are copied into privileged value storage.
Each resumption revalidates the saved context and live domain ticket. It builds
its IRET frame on the trusted kernel launch stack, restoring every integer
register. No user address selects a privileged continuation. The shared TSS
entry stack is used serially; no suspended task owns a kernel stack. Kernel
root restoration occurs after every timer interruption, return and contained
fault, before selecting another domain or reclaiming memory.

Masking/stopping the timer does not imply clearing an already latched IRR.
After restoring the kernel root, the runner drains only an actual pending timer
in a bounded STI/NOP/CLI window. The handler additionally requires CPL0, a PC in
that exact window, the privileged main stack and kernel root. It acknowledges
the real ISR without charging a task. ISR/IRR must be empty before rearm or
retirement. TPR stays zero; IF is clear on every ordinary exit. The test forces
pending interrupts before task creation, between teardown and reuse, and after
final cleanup rather than assuming this race never happens.

The controlled compiled images contain integer-only instructions. CR0.TS is set
so unsupported x87/MMX/SIMD use traps instead of sharing such state; FSGSBASE and
OSXSAVE-enabled configurations are rejected. An x87 probe demonstrates fail-stop.
This does not implement general extended-state or TLS lifecycle.

### Observable acceptance

Three private domains run a compiled finite loop, a compiled non-yielding loop,
and a known bounds-failing program. The finite loop must return exactly42 after
at least two preemptions. A linked trusted probe additionally loads15 distinct
GPR values, sets DF, and checks them after repeated asynchronous resumptions.
The infinite loop is cancelled at24 charged slices; the ordinary tasks have a
hard256-slice cap. Only exact compiler UD2 metadata can produce a contained
bounds/overflow event. Other faults remain fatal.

Every terminal task is retired only under the kernel root with an empty APIC
queue. Its saved context is cleared, stale handles are rejected, and leased
stack pages are zeroed/read back before release. Once all three are gone, a
fresh clean task reuses the first physical stack frames, verifies they are zero,
and completes again under preemption. There is no user pointer, raw syscall,
unsafe-language interface or user-selected return target in this protocol.

New QEMU modes are `--schedule`, `--schedule-no-apic`, `--schedule-smp`,
`--schedule-forged`, `--schedule-context`, `--schedule-root`,
`--schedule-softint`, `--schedule-fpu`, and `--schedule-mmio`. The latter modes
check absent/unsupported configuration, forged authority, malformed saved CS,
actual root mismatch, DPL enforcement, unsupported state and supervisor MMIO
protection. Hosted tests cover context/flag/range rejection, reset and budget
exhaustion. The separate transcript suite currently has9 positive and185
negative cases and still works with Python optimization enabled.

This is a bounded single-CPU preemption foundation. It does not provide calibrated
wall-clock time, arbitrary executables, dynamic thread creation, per-task kernel
stacks, a general process lifecycle, SMP, IPC, persistent storage or device
drivers. The trusted bootstrap remains C++23 and assembly; the computational
workloads are actual Aurora safe-C++ compiler output.

## Separate UEFI firmware handoff

The independent [UEFI consumer](uefi/README.md) now has its own PE32+ loader,
validated bounded firmware map, ExitBootServices retry, dynamically allocated
below4GiB arena, private stack/page tables and compiled-language payload. Run
`scripts/kernel-uefi-all.sh` for its OVMF gates and
`SANITIZE=1 scripts/kernel-uefi-tests.sh` for hosted policy checks. It does not yet
run the BIOS path's domain/scheduler self-tests through UEFI; those remain the
28 separate BIOS gates. No Framework hardware or peripheral support follows from
this emulator-only firmware milestone.

## Bounded firmware topology discovery

The optional [ACPI profile](uefi/acpi.md) now reads actual OVMF RSDP/XSDT/MADT
through a supervisor read-only/NX window after firmware exit, validates copied
snapshots and processor metadata, then revokes the mapping. Run
`scripts/kernel-acpi-all.sh` for11 additional actual emulator modes and
`SANITIZE=1 scripts/kernel-acpi-tests.sh` for range/parser/lifetime checks.
This discovers metadata; it does not program APICs, start secondary CPUs,
evaluate AML or provide Framework peripheral drivers.

## Checked division faults in compiled user programs

The scalar return/fault contract now recognizes the compiler's distinct
`.Laurora_division_zero_trap` only when linked metadata identifies an in-image
UD2 site separate from return, bounds and overflow sites. Older development
images without that optional site receive no division-fault authority. CPL0,
wrong-vector, wrong-PC and malformed-image cases remain rejected; hardware
vector0 is never accepted as a compiler division outcome.

`scripts/kernel-division-smoke.sh` runs five dedicated BIOS modes: quotient by
zero, remainder by zero, signed minimum divided by minus one, signed minimum
remainder minus one, and a kernel-origin jump to the exact division trap. The
first two produce a contained typed division_zero event, the quotient overflow
uses the existing overflow event, the remainder edge case returns zero within a
clean42 computation, and the kernel-origin trap fails closed. Successful cases
retain domain/root restoration, clean runs after faults, scrubbed reuse and
teardown checks. The wrapper finishes with an ordinary normal boot.

`scripts/kernel-division-tests.sh` adds hosted contract, image metadata and
transcript checks. These fixtures exercise the controlled sequential user runner;
they do not add an unsafe operation, a raw syscall or general arithmetic-fault
recovery for arbitrary executables.

The UEFI consumer also has an [MCFG/PCI ECAM inventory gate](uefi/pci.md).
It discovers configured emulated controllers through a read-only UC window;
resource reconciliation, DMA isolation and drivers remain subsequent work.

### Unsigned compiled-program boundary

`scripts/kernel-unsigned-tests.sh` validates the optional exact
`.Laurora_shift_count_trap` metadata, context policy, native fixture execution
and transcript evidence. `SANITIZE=1` enables hosted ASan/UBSan.
`scripts/kernel-unsigned-smoke.sh` runs four additional controlled BIOS modes
and restores a normal image:

- `--unsigned-valid`: MAX-u64 values, logical shifts, bit operations, unsigned
  comparisons/division/remainder, checked conversions and an unsigned-array
  loop return 42 from protected user mode.
- `--unsigned-shift-count`: a negative shift count reaches the exact emitted
  shift-count UD2, is contained, and a subsequent clean program returns 42.
- `--unsigned-conversion-overflow`: MAX-u64 to i64 reaches the existing exact
  overflow UD2, is contained, and clean execution follows.
- `--unsigned-kernel-trap`: the exact shift-count UD2 reached at CPL0 remains
  fatal; a matching address alone never authorizes user fault containment.

A zero optional shift site grants no authority. A nonzero site must lie inside
the image, differ from every return/trap site, contain UD2, and pass the existing
CPL, active-domain/CR3, stack and saved-frame checks. Hosted native tests cover
both negative and 64 shift counts. The scalar return transition is unchanged;
no user pointer or generic hardware access facility was added. These are still
bounded controlled programs, not a general process or syscall interface.

The protected compiled-program contract also runs after the UEFI handoff:
[sequential UEFI domains](uefi/runtime.md) use owned physical backing, distinct
virtual layouts/roots, guarded privileged stacks and checked scalar returns.

The UEFI [staged request/reply IPC foundation](uefi/ipc.md) adds bounded copied
scalar messages and revocable endpoint authority between controlled domains.
See its dedicated gates and limitations; it is not a general scheduler or service stack.

The opt-in [UEFI service-budget profile](uefi/service-budget.md) adds verified local-timer
preemption and recovery of a non-yielding staged service. See its dedicated
acceptance gates and emulator-only boundaries.

The [three-domain staged dispatcher](uefi/dispatcher.md) has passed all 12 new actual
OVMF modes independently and in the full 122-mode exact-source run (37 BIOS and
85 UEFI modes). The earlier 110 gates remain passing. Hosted policy/layout tests
also passed fatal ASan/UBSan. Fresh parent aggregate, sanitizer and selected
BIOS/dispatcher/recovery/drain checks passed. See the milestone012 verification
record for exact provenance. These tests do not establish physical hardware
support or a general scheduler.

The opt-in [all-controlled-user-phase budget and retirement contract](uefi/user-phases.md)
adds isolated client recovery. All 17 new modes passed independent review, and the
final 139-mode integration passed with the packed-byte compiler. Parent aggregate and selected spot checks passed; see the contract for exact
compiler provenance and limits.

## Read-only resource handoff development

The bounded BAR slice and its separate cold-reset firmware fixture are described
in [BAR-RESOURCE-CONTRACT.md](uefi/BAR-RESOURCE-CONTRACT.md). Seven actual BAR
gates and the span gate passed both author and independent execution on the
M014 compiler 2d86780c. The final integrated 147-mode run passed with 225 input
hashes unchanged; parent fresh aggregate and M014 archive acceptance also passed. A separate 449-byte protected
readonly-span fixture preserves the historical clean program and existing 4KiB
RX bound; it returns 42, survives a separate contained bounds program, runs again
and cleans up. No controller activation or filesystem implementation is claimed.

M014 final worker evidence: `/tmp/aurora-m014-kernel-receipts` contains 498 verified
receipt hashes and pre/post source manifests. The source manifest SHA256 is
`ee257b35c474eca2c9578265e6712d7e19e115d8da5ff9824796b6f5c85acd3d`.
The 147 modes preserve 37 BIOS gates on their BIOS/QEMU path and 102 historical
UEFI gates on packaged OVMF; span also uses packaged OVMF. BAR state/capture/
inherited modes use packaged firmware, while read/write/revoked/alias use the
explicit custom cold-reset fixture. The filtered distributable evidence omits
third-party firmware bytes while retaining their hashes and local audit copies.

## AMD-Vi observation development

The explicitly selected read-only QEMU profile is described in
[IVRS-OBSERVATION-CONTRACT.md](uefi/IVRS-OBSERVATION-CONTRACT.md). It copies and
reconciles paired IVRS records with live PCI identity, refuses the disabled
architectural aperture by default, and grants three static reads only under the
separate emulator profile. It provides no DMA protection or device activation.
Independent execution passed all eleven new modes. The final integrated run
passed all 158 modes with 257 project inputs and 178 external inputs unchanged;
parent fresh aggregate, selected actual spots and archive verification subsequently passed.

M015 receipts are in `/tmp/aurora-m015-kernel-receipts` (708 verified file
hashes). Source manifest SHA256:
`9fd392b5682cee4639f90870922056ebd1c2361ec62250af2c4154953ff60b3b`.
External tool/firmware/control manifest SHA256:
`c4efd3e2b74a3b7243ce9479a6f4383c3d9107de2a61ba4636b8c44a3a42878d`.
The separate control still fails its original broader whole-run absence
criterion; only its independently reviewed bounded write witness supplies
trace coverage. No DMA protection or physical AMD support is established.

## CPU-only pin ownership candidate

The [pin ownership contract](uefi/PIN-OWNERSHIP-CONTRACT.md) records a bounded
real-PageLease ledger exercised through four UEFI modes: cancellation/scrubbed
reuse, persistent quarantine through a known service fault and same-slot restart,
stale incarnation rejection, and separate ledger/pool exhaustion. Independent
review passed all four on final compiler 14cbaa33. The final worker run passed all 162
modes with 266 project inputs and 182 external pins unchanged; 720 receipt hashes
were verified and normal images restored. Parent aggregate, selected actual spots
and archive verification subsequently passed. No hardware publication/completion adapter or
DMA protection is implemented.

The CPU-only dormant-table candidate is described in
[the dormant-table contract](uefi/DORMANT-TABLE-CONTRACT.md). Its four explicit
`runtime-table-*` gates use real leased guest RAM and preserve the existing memory
budget. These results concern constructed bytes and a software translation model;
no IOMMU publication, interrupt isolation or DMA containment is established.
Independent final review passed all four modes on the integrated source. The final
worker run passed166 distinct modes (37 BIOS and129 UEFI-family) on compiler
14cbaa33, with288 project inputs and183 external pins unchanged. All757 receipt
hashes verified; normal images restored with inspector/code absence checks. Each
new mode's measured stack bound is13136/16384 bytes including1024 fault reserve.
Parent fresh aggregate and readback/quarantine/normal smoke checks passed.
The immutable source archive has a separate byte/inventory/Git-tree audit;
functional acceptance does not itself claim remote publication.

Final receipt directory: `/workspace/scratch/48c5de6446f8/aurora-m019-kernel-receipts`.
Source manifest SHA256:
`c563aa97e3c585cca5688331c62748d1e16a2f71d95b4cc8fbf8ab721f0f023b`.
External manifest SHA256:
`ef6336767f277b6cbf36af3eed36986300b9cf6a8eedd684a771bf40c662d651`.
Independent guest report SHA256:
`880d75406270894050ceb36b8b4b6ce311f7384f1ba3db1e34f7d152e7123a34`.


## Bounded BIOS transport capacity and host code generation

The actual one-read EDD packet, flat-image validator and disk padding now agree
on 127 sectors (65,024 bytes), the conservative [Phoenix EDD 1.1](https://www.t10.org/ftp/t10/document.95/95-153r0.pdf)
block-count ceiling. Loading
at segment:offset `1000:0000` touches physical `[0x10000,0x1fe00)`, leaving 512
bytes before the 64 KiB window ends. The packet, BIOS signature, initial 2 MiB
mapping, E820 buffer, BSS zeroing, RX/R/RW page separation and protected stack
bounds remain unchanged. Zero padding extends through the last requested sector;
it may cover early BSS, which startup clears again before calling C++.

This fixes an actual capacity mismatch exposed by Gentoo GCC 16.2.1: its accepted
kernel has 35,396 text bytes and a 49,904-byte flat payload, including permission
alignment gaps. That needs 98 sectors. The former 96-sector transfer was too small;
removing the unused UEFI policy alone would not bring its text under the previous
page boundary. The 127-sector contract leaves 15,120 bytes of margin for that
reported image, without changing optimization flags or treating BSS as file data.

The validator reconstructs every initialized ELF load span at its physical
address, checks exact flat bytes and zero alignment gaps, and checks that the
protected image memory covers the whole read, including padding. Physical and
virtual load addresses must agree. BSS and all loaded segments must remain below
the unchanged aligned `0x70000` protected-stack reservation.

    make test-boot-capacity
    make smoke-boot-capacity

The first command checks matching ELF/raw fixtures of 49,153, 49,904 and 65,024
bytes, exact disk padding and malformed packet/layout controls, normally and
under Python -O. It assembles a real maximum-capacity probe. The smoke command
requires QEMU and tests sentinels beyond the old limit and in the final sector.
An old-96-sector packet and a corrupt final-sector sentinel must both fail on
the actual emulated CPU. `make test` and `make smoke-all` include these gates.
The host-note boot-link regression remains separate and still runs unchanged
apart from its expected actual packet count.

Focused normal/optimized-Python gates pass, including 20 malformed-input controls
and additional independent layout probes. Actual QEMU execution reads both exact
sentinel values with the 127-sector loader; the old-96 and corrupted-last-sector
controls print their distinct failure observations. A fresh production kernel
build using the unchanged accepted compiler, normal/fault BIOS boots, exact
normal-image restoration and both image-validator modes also pass. All owned
processes closed and implementation inputs stayed unchanged during those gates.
The user reported that the PR25 Gentoo GCC 16.2.1/binutils 2.47 rebuild succeeded
on 2026-10-05. No independent log, new boot or physical-machine result is inferred.
The standalone transport fix did not rerun the full aggregates; the later
[combined checkpoint](../docs/kernel-round-robin-integration-results.md) passed
fresh full native, scheduling and all-mode emulator qualification.

This is a bounded emulator bootstrap, not a general kernel-loading mechanism.
A payload of 65,025 bytes still fails closed. Further growth requires a separately
reviewed multi-read or stage-two loader with bounded destination/LBA arithmetic,
per-transfer boundary checks and total memory authority. Increasing a test limit
again would not implement that loader. Existing firmware assumptions remain:
512-byte sectors and EDD are assumed; the first read and BSS initialization occur
before runtime E820 grant validation. No physical BIOS compatibility is claimed.

## Copied IPC transition candidate

The six production Mailbox operations now request a copied Aurora decision and
validate its canonical effect before mutation. The trusted adapter keeps all
identity, right, transaction, generation and storage authority. `bind` and
`revoke` retain their accepted implementation. Invalid producer/input boundaries
are distinct from canonical ordinary refusal; both deny before an individual
operation mutates a mailbox or mints a stamp. Accepted composite prefixes are
not rolled back after a later denial. See the [contract](../docs/kernel-ipc-transition-contract.md)
for the complete state relation and pending acceptance obligations.

Four additional IPC profiles cover real request and restored service-fault
cancellation boundaries: `ipc-policy-request-input`, `ipc-policy-request-output`,
`ipc-policy-cancel-input`, `ipc-policy-cancel-output`. They corrupt only a copied
phase or actual producer result, not live state. Normal IPC/dispatcher/restart
behavior, full-width payloads, isolated BIOS root and all existing gates remain
required. Source changes alone do not qualify these profiles or this policy.

### IPC integration status — 2026-10-06

The earlier 586-file `2b4da219…` source has separately accepted full D/P native,
five-entrypoint fatal sanitizer, 28 bounded static image and 177+3+2 actual boot
results. The same-reviewer reconsideration closed the two-input-image static
gate; the interrupted attempt remains unaccepted. This fresh current-main
composition is unqualified and needs new linked review and native/runtime
integration. See the [dated results](../docs/kernel-ipc-transition-integration-results.md).


## Copied client-disposal recovery plan

The existing `Dispatcher::dispose_client` now depends on a copied Aurora plan
before choosing empty disposal, retained completion receipt, cancellation plus
consumption, or consumption of an existing terminal result. Trusted live owner,
quiescence, selected-client, grant, exact transaction and receipt checks still
guard real effects, revocation and retirement. Existing committed-prefix failure
semantics are preserved. This is a narrow policy port, not a dispatcher rewrite.

See [contract](../docs/kernel-client-disposal-contract.md) and
[focused qualification and final-review status](../docs/kernel-client-disposal-results.md).
`make test-client-disposal` runs the bounded focused native oracle, copied-value
and rejection checks and hostile actual-dispatcher controls with the shared
selected compiler. Existing user-run gates remain part of qualification.
