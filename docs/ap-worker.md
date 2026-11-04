# Bounded second-CPU execution

The standalone UEFI `ap-worker` image executes compiled Aurora arithmetic on a
second processor. It is a multicore kernel substrate, not production SMP
scheduling. The ordinary process/console timer admission still requires one
enabled processor; this mode does not run those consumers.

## Contract

The admitted platform is pinned QEMU 10.0.13, TCG, q35, two legacy-xAPIC CPUs,
`qemu64,vendor=GenuineIntel`, and the pinned OVMF firmware. The vendor string is
an explicit emulator contract, not physical Intel or AMD qualification. A
checked copied MADT must describe exactly two distinct enabled processors.
Actual BSP CPUID, APIC MSR and register observations select the other processor;
neither a numeric selector nor the firmware description itself grants access.

`kernel::ApWorkerOwner` remains exclusively on the BSP. It owns the single
startup attempt, lifecycle, eight nonreused job sequences and 4096 cumulative
work units. Reservation spends the allowance before publication. The native
adapter authenticates the exact retained root, BSP and CR3, with interrupts
disabled, before and after each synchronous loan. No loan crosses MMIO,
polling, a CPU switch or AP execution. Native sequence tracking authenticates
the physical mailbox protocol; it does not duplicate source quota policy.

The AP runs one closed scalar operation: sum the squares of `count` consecutive
integers beginning at `start`. Admission requires `0 <= start <= 65535` and
`1 <= count <= 1024`; every intermediate and result fits signed 64-bit
arithmetic. The helper has no imports, allocation, callbacks, pointers or
borrowed owners. This does not introduce concurrent Aurora objects or a general
language memory model.

## Startup and memory

The loader allocates a startup page below 1 MiB and a separate 64-page worker
block below 4 GiB. Each ExitBootServices attempt rechecks ownership in its final
map. The payload authenticates the copied handoff and map again. Neither region
enters a reclaimable allocator.

Startup and permanent AP roots have independent, software-frozen ancestors.
Their whitelist contains only the page-separated AP code/helper, private
descriptors, guarded stack/IST, readonly request and writable reply. The
permanent root omits the low startup page. BSP owner state, allocators, general
kernel data, firmware windows and page-table storage are absent. The complete
BSP tree is checked after sealing the low page and all worker pages readonly,
except its writable request page. No writable executable alias is admitted.
Expected hardware accessed/dirty updates do not confer software mutation rights.

Directed INIT/SIPI occurs after ExitBootServices. A unique checked FADT admits
only the pinned q35 PM-timer port `0x608`, read with a 32-bit input instruction.
This emulator has a 24-bit counter at 3,579,545 Hz. The Intel startup minimums
are implemented with conservative thresholds of 35,797 ticks for 10 ms and 717
ticks for 200 microseconds. Width-masked differences and bounded polling are
used; a stagnant or unsupported timer refuses startup, never substitutes an
instruction count for elapsed time. ICR delivery completion does not establish
AP readiness.

The AP establishes its own mode, descriptors, control state and CPU-local fault
path. It checks CPUID's initial APIC ID and APIC_BASE/BSP-clear, CR3 and stack
before publishing readiness. The AP does not map or read LAPIC-ID MMIO; this
identity check assumes the pinned emulator's IDs are not reprogrammed.
The trusted privileged shim is not isolation from arbitrary malicious ring-0
instructions. Firmware correctness, emulator timing and this closed code graph
are named assumptions. The early trampoline before its private IDT is installed
is not independently fault/NMI-contained; a fault there may fail the boot.
Recoverable AP-fault acceptance applies after readiness, not to that interval.

## Completion and failure

Aligned lock-free release/acquire publication orders the copied scalar request
and result. The AP publishes completion only after its final result store and
stops touching that job until the next request. The BSP validates exact
incarnation, sequence, CPU/root/stack evidence and completion state before
source acceptance and reuse. This protocol establishes job quiescence, not a
proof that the processor halted.

A fault, malformed response or uncertain timeout closes publication permanently.
All startup-reachable backing remains pinned, including the trampoline and
temporary tables. Late completion cannot reopen the source owner or spend a
new sequence. There is no reset, replay, cancellation-as-stop or reclamation.
An uncertain source fault does not prove that source `fail()` executed; its
separate native path fail-stops the BSP. Finite arithmetic work and finite BSP
observation counts do not promise an AP wall-clock deadline.

## Running and qualification

Build `kernel-uefi-ap-worker` in the configured native Meson graph. Run
`meson test -C BUILD --suite guest-ap-worker --print-errorlogs`, or use
`scripts/kernel-ap-worker-smoke.py --run-only BUILD/kernel-images/uefi/ap-worker
--output-dir BUILD/ap-worker-guests` for focused development. The driver uses
one unchanged image, the existing fw_cfg case word and the existing QEMU
transport, with a 30-second cap for each cold boot.

Normal acceptance requires actual BSP0/AP1 execution with distinct roots, eight
different exact results, source exhaustion and subsequent BSP page
allocation/write/read/release and language execution. Other rows exercise a
real AP invalid-opcode fault, withheld/late completion, expected-identity/root
mismatch, nonadvancing timing, invalid copied low-page ownership, malformed
copied MADT/FADT, malformed AP completion, and unsupported topology/vendor.
Hosted tests execute the compiled owner/helper and cover stale/foreign/duplicate
receipts and boundary arithmetic; they do not replace physical guest evidence.
The checked startup-attempt record denotes the native ICR-write boundary, not
proof of device completion. Full final qualification is recorded per revision.

Primary contracts: [Intel SDM Volume 3A, sections 8.4 and 10.6](https://www.intel.com/content/dam/www/public/us/en/documents/manuals/64-ia-32-architectures-software-developer-vol-3a-part-1-manual.pdf),
[ACPI PM timer](https://uefi.org/specs/ACPI/6.5/04_ACPI_Hardware_Specification.html),
[UEFI page allocation](https://uefi.org/specs/UEFI/2.10/07_Services_Boot_Services.html),
[pinned QEMU PM timer](https://github.com/qemu/qemu/blob/v10.0.13/hw/acpi/core.c),
and [OVMF PMBASE](https://github.com/tianocore/edk2/blob/edk2-stable202502/OvmfPkg/Include/OvmfPlatforms.h).
