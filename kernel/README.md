# Kernel bootstrap

The kernel is trusted freestanding C++23/assembly with bounded Aurora programs
and policies. It is not a language-native kernel, general process system or
proof of Rust-equivalent safety. Images are disposable emulator inputs. Never
write them to a physical disk, attach user data or modify a host bootloader.

## Build and verify

`make run` and `make run-uefi` build and check normal BIOS/UEFI boots.
[Local development](../docs/local-development.md) owns dependency selection,
firmware discovery, commands, clocks and cleanup. `make test` is native-only;
actual QEMU smokes remain separate. Normal boot requires exit 33, exact result
42 and the complete success transcript. Fault modes require their exact event,
status and fail-stop sequence; a timeout or missing prerequisite never passes.

[Serial consoles](../docs/native-console-service.md),
[graphical output](../docs/framebuffer-console.md) and
[protected commands](../docs/program-console-contract.md) define their own
bounded grammar and authority. A prompt is not general terminal/job control.

### Host-toolchain boot layout

Use x86-64 Linux, GCC 16 C++23, GNU Make/binutils, Python and Bash. GNU as must
support --32/--64; ld needs elf_i386/elf_x86_64, orphan rejection and the selected
UEFI PE backend. Host-note controls additionally need -mx86-used-note and
--generate-missing-build-notes. Distribution name or tool presence is not
qualification. Select matching gcc/g++ and record actual compiler/binutils.

Freestanding builds set -fcf-protection=none and -mstringop-strategy=libcall.
UEFI PE links require dynamic-base and NX compatibility. Native profile outputs
export each exact object with its .su, .ci and .source.json sidecars from the same
compilation. Admission validates the actual compiler working directory and original
object/sidecar bytes; source and build hash namespaces are distinct. Missing or
ambiguous source/symbol/object/link associations reject.

Graphical C++ stack bounds trust GCC .su frame sizes and .ci call facts, retain
the complete reported frame through calls and tail transfers, and check compiler
versus linked direct-edge agreement. Each frame containing checked adjacent
pushfq/register-pop receives an eight-byte reserve. Arbitrary inline assembly is
not covered by compiler metadata. C++ instruction-by-instruction stack/CFG replay
is not performed. Generated Aurora, private ABI, assembly and IRQ/fault checks
and all existing stack/image budgets remain separate requirements.

Service-budget and copied-snapshot profiles finish ACPI parsing before starting PCI discovery, using
separate native frames and the existing owned MCFG snapshot. A failed PCI discovery
clears the copied timer topology. Call and snapshot image admission check that the preparation
frame cannot reach PCI discovery; the existing stack cap and fault reserve remain
unchanged. This reduces overlapping temporary lifetimes without new persistent
kernel storage or changes to the service-call authority boundary.

The bounded Call consumer reuses the owned snapshot producer and authenticated
SnapshotSlot staging. Its scalar request selects an offset/count, never a pointer
or storage capability. The service runs std::crc32c over a receiver-bound readonly
snapshot view; no producer owner survives publication. Admission checks both user
call chains, the exact copied ABI, canonical reply encoding and unchanged image
and kernel-stack caps. Retirement clears snapshot publication as well as wait
authority. This remains one call per incarnation between a fixed pair.

PageTables::verify and RuntimeTables::inspect use fixed-four-slot DFS/postorder
walks. Call-graph cycles reject; no legacy recursion-source hash, line or register
carrier exception remains. Traversal termination, memory authority, storage
ownership and general C++ correctness remain reviewed source/compiler trust,
checked by independent recursive-reference boolean/callback-order comparisons
and hostile hosted tests. These are not arbitrary-memory-safety proofs. Actual
final image and affected guest/restoration gates are still required.

## BIOS boot and physical pages

The 512-byte sector starts at 0x7c00 with _boot first and a valid signature.
The linker disables build IDs, discards only named GNU metadata, rejects other
orphan/storage sections, and does not truncate or pad an invalid boot binary.
A single EDD packet reads 127 sectors (65,024 bytes) from LBA 1 to
[0x10000,0x1fe00), inside one 64 KiB window. A 65,025-byte payload rejects.
Growth beyond this requires a separately checked multi-read/stage-two loader.
512-byte sectors and EDD are assumed; loading and BSS initialization precede
runtime memory-map grant verification. No physical BIOS compatibility is claimed.

ELF validation reconstructs initialized physical spans, checks exact flat bytes
and zero alignment gaps, requires physical/virtual load agreement and coverage of
the complete padded transfer. BSS and loads remain below the 0x70000 protected
stack reservation. Startup clears BSS before C++. Initial 0x1000/0x2000/0x3000
tables map 2 MiB for bring-up; no user code executes under that temporary mapping.

E820 has at most 32 entries; invalid signatures, short records and overflow
invalidate it. The complete [0x100000,0x180000) pool must be usable and free of
contradictory enabled reservations. Its 128 physical 4 KiB frames use move-only,
generation/incarnation-tagged PageLeases. Wrong owner, stale/moved/double release
and same-address allocator replacement reject. Generation wrap retires slots;
incarnation exhaustion rejects initialization. Dropping an unreleased lease leaks
rather than silently freeing aliased storage. The allocator is single-CPU and
not a general heap. The raw pool does not scrub automatically: security-domain
consumers must perform their checked scrub before release.

## Protection and controlled programs

NX support is mandatory. Replacement 4 KiB mappings default-deny, enforce
CR0.WP/EFER.NXE, reject W+X and physical writable/executable aliases, and keep
kernel text RX, constants R/NX, data/tables RW/NX. BIOS guarded ranges are:

| Region | Range |
|---|---|
| Main stack | 0x88000..0x90000 |
| TSS.RSP0 | 0x82000..0x86000 |
| Double-fault IST1 | 0x7c000..0x80000 |
| User stack virtual range | 0x1e0000..0x1e4000 |

A private GDT/TSS denies user port I/O. Compiled user fixtures occupy separately
linked immutable RX pages, each at most 4 KiB, with no writable globals,
relocations or unresolved symbols. Exact return and distinct compiler UD2 sites
are bound to linked metadata. Before entry, registers and the guarded stack are
scrubbed and checked; the kernel retains its own privileged continuation.

INT 0x81 returns one scalar bit pattern from the exact active return site.
Acceptance validates actual domain/root, CPL/selectors/flags, saved frame bounds,
stack alignment/top and active run. It accepts no user pointer or privileged
continuation. Only exact known user-origin compiler trap sites are contained;
wrong sites, kernel-origin traps and unexpected faults fail-stop. Double-fault
IST is not a general nested-fault recovery mechanism.

Three static domain slots own distinct CR3 roots and four private stack leases
each. Each root maps only its own user image/stack plus common supervisor state.
Before switching, complete leaf policy, actual root readback and PCIDE-clear
conditions are checked; CR3 switching flushes this CPU’s nonglobal translations.
Monotonic handles prevent stale slot/registry resurrection. Teardown requires an
inactive ready domain under the verified kernel root, complete stack scrub/readback,
table clearing, handle revocation and then lease release. Partial allocation must
scrub/release its prefix; unverifiable backing is retained. This is not SMP
TLB shootdown, pageable VM or asynchronous revocation.

## Integer-only preemption

The BIOS scheduling profile requires one BSP, enabled xAPIC at 0xfee00000,
no x2APIC and UC PAT entry 3. Its shared supervisor RW/NX MMIO page is verified
in every root. A one-shot divide-16 count is an instruction/test budget, not
milliseconds or physical timer calibration. Unrelated local/PIC sources stay
masked. Vector 64 needs exact run/domain/CR3/frame/RIP/selector/flags and a real
APIC ISR bit; software interrupts cannot mint timer authority.

The kernel saves all 15 GPRs and integer continuation state, restores its root
before selection/retirement, and keeps kernel execution nonpreemptible except
for the exact bounded pending-drain window. Stop/mask is not IRR drain. Pending
ticks authenticate the kernel root/stack/window, clear real ISR without charging
a task and must settle before rearm or teardown. CR0.TS rejects unsupported
x87/MMX/SIMD, and FSGSBASE/OSXSAVE configurations reject; general FPU/TLS lifecycle
is absent. Slice caps and exact policy outcomes remain profile-specific.

## UEFI and device components

- [Firmware handoff](uefi/README.md), [protected runtime](uefi/runtime.md)
- [ACPI](uefi/acpi.md), [PCI](uefi/pci.md), [BAR resources](uefi/BAR-RESOURCE-CONTRACT.md)
- [IPC](uefi/ipc.md), [dispatch](uefi/dispatcher.md), [user phases](uefi/user-phases.md), [service budgets](uefi/service-budget.md)
- [Copied Aurora policies](POLICIES.md), [CPU byte owners](../docs/kernel-owned-bytes.md)
- [Page-pin ownership](uefi/PIN-OWNERSHIP-CONTRACT.md), [dormant tables](uefi/DORMANT-TABLE-CONTRACT.md), [queue preparation](uefi/NVME-QUEUE-PREPARATION.md)
- [Read-only IVRS](uefi/IVRS-OBSERVATION-CONTRACT.md), [test-only AMD models](../docs/iommu-models.md), [emulated Event diagnostics](../docs/iommu-dma-conformance.md)

Discovery, CPU-only page/queue preparation and copied models do not establish
DMA isolation, invalidation/drain completion, safe reclamation or active drivers.
No physical Zen/Navi/RDNA tuple is qualified. General process/services, SMP,
network/storage/GPU/input drivers, persistent files and language-native ownership
of the complete kernel remain open.
