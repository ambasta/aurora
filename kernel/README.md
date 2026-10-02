# Running kernel foundations

This is a **temporary trusted C++23/assembly bootstrap**, not Aurora's final
language-native kernel or a claim of Rust-level memory safety. It compiles and
executes the separate Aurora source-language program. No C source compatibility,
C runtime, libc, or exported C object model is supplied. Scalar assembly symbols
are a disposable bring-up seam, not a permanent platform ABI.

## Build and verify

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

Normal smoke requires exit 33, exact language result 42, E820/page/exception
self-test markers, and AURORA_BOOT_OK with no failure/fatal marker. Fault smoke
requires exit 35, the exact injected vector/error diagnostic, and fail-stop.
Logs: build/kernel-serial.log, kernel-fault.log, kernel-page-fault.log.
Missing QEMU means blocked verification, not a pass.

## Implemented and exercised

- A 512-byte BIOS sector loads 64 sectors to physical 0x10000.
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
symbols, with eight malformed-image controls. Shared smoke validation has 16
positive and 110 negative transcript regressions and stays active under Python -O.

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
W^X and one controlled ring-3 probe. External IRQs remain masked; scheduler,
APIC/timer setup and general SIMD/FPU contexts remain absent. Unexpected faults
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
  and returns i64 value 42.
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
all three pages are user RX without a writable alias. E820 must grant the image
regions. All fixtures share one user domain and can read/execute each other's
immutable code. They do not have independent address spaces or process identities.

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

Three additional fail-closed emulator modes distinguish containment from unsafe
recovery: --program-bad-return rejects INT 0x81 at an unauthorized return PC;
--program-unknown-trap rejects an unrelated user UD2; --program-kernel-trap executes
the exact known compiler trap at kernel privilege and verifies it remains fatal.
These test-only assembly injections do not add unsafe syntax to Aurora.

`./scripts/kernel-protection-smoke.sh` now runs 16 real emulator modes. A normal
image is restored after fault variants. Each log has an adjacent .metadata.json
receipt preserving that variant's linked trap addresses even after restoration.
The user-image verifier includes 27 malformed-image/metadata controls. Shared
transcript validation has 16 positive and 110 negative cases, including exact
containment order and clean execution after both faults. Hosted policy tests can
run under ASan/UBSan with `SANITIZE=1 ./scripts/kernel-tests.sh`.

For isolated compiler-integration experiments, AURORAC can select an already-built
compiler executable; ordinary builds still run `make -C compiler`. Record its
hash and rerun against the final compiler before claiming a checkpoint verified.

### Remaining assumptions

This is a trusted build-time image installer and a sequential integer-only test
runner. There is no arbitrary executable loader, timer/preemption, scheduler,
per-process isolation, cross-domain copy service, heap lifecycle or general
syscall API. A hung program cannot yet be interrupted by this runner. Unexpected
faults, stack exhaustion and invalid returns still fail-stop; only the two known
compiler traps are contained. FPU/SIMD and FS/GS/TLS lifecycle, asynchronous state,
SMP, DMA isolation and speculative-execution mitigations remain outside this gate.
The wrappers, kernel and toolchain are still trusted bootstrap machinery rather
than a verified language-native OS. Physical AMD hardware remains unqualified.
