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
symbols, with six malformed-image controls. Shared smoke validation has three
positive and 17 negative transcript regressions and stays active under Python -O.

## Deliberate limits

This fixed BIOS transport is disposable emulator scaffolding, not Aurora's
proposed firmware contract, installer, filesystem or general disk driver. Never
write this image to a physical disk. Scripts create a regular 1 MiB file only;
they do not alter any host bootloader or kernel.

The allocator is single-CPU, bounded and explicitly released; it is not a heap,
virtual-memory manager, or concurrent allocator. Recycled frames are not yet
scrubbed: the pool must not cross security domains. The C++ bootstrap can still
forge raw addresses and is trusted. Lease validation is not hardware isolation.

The IDT is diagnostic infrastructure: external IRQs remain masked, no scheduler,
APIC/timer setup, TSS/IST emergency stack or SIMD/FPU context exists. Double faults
caused by stack corruption cannot be assumed recoverable. Only controlled
breakpoints resume. Kernel code uses general registers only. The 2 MiB mapping is
writable and executable; no W^X, user mode, process isolation, IOMMU, IPC or SMP
exists yet. No storage/network/GPU/input driver compatibility is claimed.

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
