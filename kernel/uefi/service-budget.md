# UEFI service-budget preemption

This optional profile interrupts a compiled non-yielding IPC service, resumes it
twice, then cancels it on the third verified timer interrupt. It restores the
owned kernel root, drains pending timer delivery, delivers cancellation to the
client, revokes and scrubs the old service, and completes a new request with a
fresh service incarnation. A finite compiled service must also receive an
interrupt inside its compiled function and still return 42.

This is single-CPU service-budget recovery within the staged IPC harness. It is
not a general scheduler, wall-clock deadline, arbitrary suspended-call interface,
SMP implementation or physical Framework qualification.

## Discovery and mapping authority

The ACPI path retains an owned immutable copy of its successfully validated MADT
topology after closing firmware/config windows. Timer admission requires exactly
one enabled legacy processor record matching the executing CPUID BSP ID, MSR,
APIC and PAT support, the expected enabled BSP xAPIC base, a valid physical width,
and a final firmware map owning the complete runtime arena. Disabled or merely
online-capable records do not count as enabled processors. Enabled x2APIC records,
multiple enabled CPUs, inconsistent IDs and unsupported register versions reject.

The physical aperture is explicitly the tested q35 page at 0xfee00000. MADT does
not grant general MMIO authority. Admission rejects owned-arena overlap and any
overlapping RAM, runtime, persistent or conflicting-cache descriptor. A missing
firmware descriptor is accepted only under this exact emulator resource contract.
Generic firmware resource reconciliation remains unimplemented.

The loader reserves an empty branch at virtual 0xffff900000000000 inside its
existing owned page-table pool before ExitBootServices. After admission, the
adapter installs one supervisor RW/NX, nonglobal leaf using PAT index3, checked
to mean UC. It verifies the entire kernel tree against the immutable grant and
its arena identity before reading APIC registers. MMIO ID/version checks then
complete hardware identification. Every private domain has the identical
supervisor-only leaf. Full tree checks deny extra leaves, aliases and alternate
cache/privilege permissions. The firmware/ECAM window remains absent from users.

## Timer and continuation authority

The profile requires already-enabled xAPIC, masks other supported local-vector
sources and the emulated legacy PIC, and programs a one-shot timer on vector64.
It does not program IOAPIC routes or activate DMA controllers. Count 20,000 with
divide16 is deliberately uncalibrated: a budget counts interrupts, not time.
Unexpected sources and spurious interrupts fail-stop in this bounded harness.

Each service launch receives a fresh checked run epoch bound to its live domain
handle, actual CR3, kernel-selected service phase and delivered IPC transaction.
Only service execution enables IF. The interrupt gate remains DPL0; user software
interrupts cannot claim timer authority. Each accepted tick additionally requires
the real timer ISR bit, no unrelated ISR/IRR sources, the exact user selectors,
allowed IF/IOPL/flags, a complete owned RSP0 frame, an in-image PC and that domain's
validated dynamic user stack. No BIOS fixed stack address is reused.

All 15 GPRs and the hardware return frame are captured on the supervisor stack.
A copied immutable context validates them before the existing assembly entry
restores the original frame with iretq. The register probe sets distinct sentinels
and DF, survives actual interrupts, checks them after resumption and then executes
the compiled service. CR0.TS, cleared FS/GS bases and disabled unsupported extended
state remain mandatory; this is integer-only execution.

The timer is stopped/masked and acknowledged before rearming. On budget exhaustion,
a trusted ProgramRun cancellation removes the active run without manufacturing a
compiler-fault classification. The handler switches to the kernel CR3 before
returning through the saved kernel continuation. The service's stack is preserved
across timer resumption, but scrubbed for a fresh staged invocation.

## Terminal races and teardown

Ordinary service return or a recognized bounds trap stops the timer while kernel
interrupts are disabled. Terminal classification permits IF only after validating
the complete original service context; the existing exact return/UD2 and DF rules
still apply. Reply/cancel state transitions remain serialized and first-terminal-wins.
A pending timer after a reply cannot cancel that reply.

Before a service continuation can finish, the adapter restores the kernel root,
masks/stops the timer and drains any latched timer request. A drain interrupt is
authorized only inside a four-byte owned kernel STI/NOP/NOP/CLI interval, with
CPL0, the owned main stack, the kernel root, the still-live old run epoch/domain
and real timer ISR authority. It does not decrement a service budget. Drain is
bounded; leftover or unrelated ISR/IRR state fails closed. No new run can arm and
no domain can be retired/reused before successful quiescence.

The pending-delivery fixture also exercises the natural case where IRR was
already set when the service returned. It preserves that request rather than
assuming that stopping the counter cleared it. Cancellation and service restart
continue to use the copied-message rights/generation/scrubbing rules in [ipc.md](ipc.md).

## Acceptance gates

- `SANITIZE=1 scripts/kernel-uefi-budget-tests.sh`: admission, immutable context,
  real kernel/private mapping policy, exact image intervals and strict transcripts.
- `scripts/kernel-uefi-budget-all.sh`: nineteen actual OVMF modes, restoring the
  normal image after each. The prior 95 modes remain acceptance gates.
- `budget`: compiled non-yielding service exhausts three interrupts, then a fresh
  finite service is preempted and completes the copied request.
- `budget-fault`: an actual emitted bounds UD2 with IF enabled is contained,
  followed by cancellation, fresh service execution and successful reply.
- `budget-context`: all15 GPRs and DF survive interrupts in the exact probe loop,
  then compiled service execution completes.
- `budget-pending`: a latched timer is drained after reply under the old epoch,
  with unchanged reply outcome and no new-run charge.
- `budget-noapic`, `budget-discovery`, `budget-cache`: test-only corruption of the
  CPU feature/base/PAT snapshots rejects admission before MMIO access.
- `budget-smp`: actual two-CPU OVMF topology rejects the single-BSP profile.
- `budget-alias`: an injected second mapping fails complete-tree verification
  before APIC register access.
- `budget-forged`: a kernel software interrupt lacks valid user/run/ISR authority.
- `budget-root`, `budget-epoch`: actual timer delivery rejects the wrong active
  root or deliberately stale run epoch.
- `budget-mmio`, `budget-softint`, `budget-fpu`: actual supervisor-MMIO read,
  forbidden interrupt instruction and unsupported extended-state instruction fail.

Transcript validation first binds every tick or drain to its immediately preceding
hardware frame and checks epoch, budget, origin, mapping, flags and terminal order.
Only then does it project validated timer recovery into the separately checked IPC
state sequence. Compiler faults and budget exhaustion are distinct original events.
Compiled-function/probe/drain metadata is bounded independently and checked against
actual ELF symbols and instruction bytes during image construction.

Primary references: [Intel SDM Volume3A, APIC chapter](https://cdrdv2-public.intel.com/671190/253668-sdm-vol-3a.pdf)
and [AMD APM Volume2 revision3.44, chapter16](https://docs.amd.com/api/khub/documents/sD1_QL~h4Afq2_tvzxqqSQ/content).
AMD specifies divider/LVT initialization before starting the counter, zero initial
count stopping it, and EOI clearing the serviced ISR bit. It also says software
APIC disable retains pending ISR/IRR state. Official indexed AMD excerpts were
available during review; the direct PDF fetch returned404. Product-specific timer
frequency and power behavior require the relevant AMD product documentation and
physical qualification, which this emulator profile does not provide.

### Kernel stack selector regression

The strict pending-drain gate exposed an incomplete trusted continuation: after
a user interrupt, both the saved drain SS and live SS were measured as zero.
Intel SDM Volume3A, stack switching in 64-bit mode, and AMD APM Volume2 chapter8
(page283, revision3.44) specify clearing SS on a privilege change. The continuation
now restores SS=0x10 alongside DS/ES before restoring its owned kernel stack,
with interrupts disabled. The drain predicate still requires exactly SS=0x10;
the actual pending-drain gate and its selector-mutation receipt tests cover this
regression. This normalizes the intended kernel state rather than widening the
set of authorized interrupt frames.

### Verified Aurora policy checkpoint

The [pure interrupt-count transition](../../docs/kernel-budget-contract.md) is
now compiled from Aurora and called in the actual timer path after authority and
ISR checks. The bootstrap adapter validates its private scalar transport before
committing counts or selecting the existing resume/cancel mechanism. Four new
`budget-policy-*` modes cover rejected state and corrupted transport. A fresh
full native aggregate, all 170 actual emulator modes and two additional normal
boots passed on the reconciled source, followed by independent terminal reviews.
The four policy modes include actual pre-commit fail-stop checks; the output mode
also passes the linked-image guard. See the
[exact evidence index](../../docs/evidence/kernel-budget-policy/README.md).
Earlier failed/interrupted attempts remain separate and supply no mode credit.

## Provisional emulator clock qualification

The 19 budget modes are included in the explicit 51-mode UEFI clock candidate.
Budgets 128/3, compiled-service interruption, context/DF checks, exact exhaustion,
pending drains and all negative reasons remain unchanged. New qualification is
pending; historical passing receipts do not establish the changed clock. See the
[clock contract](../../docs/kernel-emulator-clock-contract.md).
