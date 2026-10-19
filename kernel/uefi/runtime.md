# Sequential protected programs after UEFI handoff

This slice brings the existing compiled-program isolation contract onto the
real OVMF handoff path. After ExitBootServices, owned paging and read-only
ACPI/PCI discovery, the payload runs two compiled Aurora programs at CPL3 under
separate CR3 roots. A known bounds trap is contained, clean execution follows,
and retired stack frames are scrubbed and reused. There is no scheduler, IPC,
controller activation, DMA ownership or general process lifecycle in this slice.

The clean fixture executes `std::pair<i64,u64>` template-generated code and,
in the next candidate, stores and reads that result through `std::array<i64,2>`
`set`/`at`, returning 42 through the same scalar transition. Trusted C++/assembly remains
temporary bootstrap machinery; this is not a language-native complete kernel.

## Relocation and ownership

[Bootstrap dimensions](../bootstrap-layout-values.inc) and
[image page policies](image-page-policies.inc) are shared tables for C++ and the
generated profile metadata. Host image and boot checks use the same metadata loader.

Handoff version 3 retains the allocated 1 MiB arena and adds an exact metadata
pointer at arena + 0x81000. Version 1 and 2 profiles remain valid with their
original layouts. The final firmware map must own the whole arena below 4 GiB.
Every runtime interval is checked for page alignment, overflow, overlap and
bounds. The domain builder receives only those owned physical frames.

Protected user images have 16 KiB virtual slots beginning at 0x10000000000.
Each slot contains at most three RX code pages followed by an unmapped guard.
These are chosen canonical lower-half virtual addresses, not physical load
addresses or BIOS constants. Their immutable, boot-owned physical slots occupy three pages each, beginning
at arena + 0xb0000 (then +0xb3000 and, for dispatch, +0xb6000). Link metadata, exact entry, segment permissions and every trap site
are validated before installation. `runtime-multipage` admits three pages per
image. Blocking-call profiles admit two pages for the caller and one for the
service; owned-text profiles (including console-region) admit three pages for
the first image and one for the second. Other profiles retain one-page image
allowances. Metadata cannot select its own allowance. The linker, image validator, loader and runtime independently
enforce the selected bound; BIOS remains one page. The loader zeros all slots
before publication. User roots map only the rounded validated byte extent, and
verification checks every required leaf plus absent unused/guard/foreign pages.
Trap authority remains bounded by actual bytes, not mapped padding. The UEFI payload is independently position
independent and relocates its trusted pointers from the actual arena address.

The GDT/TSS page is at +0x82000; RSP0 uses +0x84000..+0x88000 with an unmapped
lower guard; double-fault IST uses +0x89000..+0x8d000 with its own lower guard.
Two private table pools occupy +0x90000..+0xb0000, with at most 16 pages per
root. Sixteen allocator-owned stack frames occupy +0xc0000..+0xd0000. Each
active domain leases four frames. Its virtual stack begins at
0x10000200000 + domain_index * 0x200000 and spans four pages; surrounding pages
are absent. Metadata is supervisor RO/NX, image frames RX, and tables/stacks
supervisor RW/NX in the kernel mapping.

`ProgramLayout` is an immutable validated value copied into each contract.
Image metadata supplies no code/stack ranges and cannot widen the layout.
The original BIOS constructor still chooses its original profile; UEFI supplies
its separate checked profile and arena-owned entry stack.

## Page tables and privilege transitions

Each private root is rebuilt from the exact supervisor kernel leaves and its
own user RX image/RW-NX stack mappings. Firmware and ECAM window branches are
absent from user roots. Kernel-only mappings agree across roots. Image frames
have no writable supervisor alias. The complete table walk rejects foreign
links, cycles, table aliases, orphan/empty branches and incorrect permissions;
the adapter also checks every expected leaf so a missing mapping cannot pass.
PGE and PCID remain disabled; every root switch performs an actual CR3 load.

The payload installs its own GDT, TSS and IDT in owned memory. TSS.RSP0 and IST
are guarded supervisor stacks, the I/O bitmap is beyond the TSS limit, and only
the exact scalar-return interrupt gate is callable from CPL3. The image's
return PC must match its validated `int 0x81`/UD2 trampoline. Exact emitted
bounds/overflow/division/shift UD2 sites are distinct and bounded. Matching an
address alone does not grant fault-containment authority.

Entry scrubs all four stack frames, clears integer registers and enters with
IF and IOPL clear. CR0.TS blocks unsupported extended-state instructions;
FSGSBASE/OSXSAVE and unsupported paging modes are rejected. FS/GS selectors and
bases are cleared. Inherited SYSCALL and SYSENTER entry authority is disabled
and read back before user execution. This remains an integer-only, sequential
controlled-program boundary.

Every event must match the active registry handle, actual CR3, CPL, selectors,
RFLAGS, complete RSP0 frame, user stack range and exact return/trap site. The
trusted saved kernel continuation must lie on the owned main kernel stack.
A contained event loads the kernel CR3 before returning through the saved
kernel stack. The caller verifies both again before retirement. Users never
provide a kernel continuation address. Unexpected events fail-stop.

Retirement requires an inactive domain and actual kernel root. It scrubs and
checks stack pages, clears tables, revokes the generation-stamped handle, and
releases leases. Normal execution tests active/stale retirement rejection,
reuse of the same physical frame with zeros, partial-create rollback after only
two free frames, and final zero outstanding leases.

The exception entry code is shared with BIOS, but the UEFI build omits the
unused BIOS absolute-address vector table. Its active handler table uses
RIP-relative offsets. The strict PIC verifier checks runtime C++, entry glue
and shared exception object relocations; absolute relocations are rejected.

## Gates and honest limits

- `scripts/kernel-uefi-runtime-tests.sh`: hosted immutable-layout/table checks,
  image metadata and strict transcript controls. Set `SANITIZE=1` for ASan/UBSan.
- `scripts/kernel-uefi-runtime-all.sh`: fourteen actual OVMF modes using the
  dependency setup from [the UEFI guide](README.md), restoring normal afterward.
- `runtime`: clean42, contained bounds fault, clean42, scrub/retire/reuse, clean42,
  rollback and final cleanup.
- `runtime-code`, `runtime-stack`: cross-domain fetch/read denial.
- `runtime-kernel`, `runtime-window`: supervisor arena and absent ECAM-window
  read denial. The kernel-read fixture contains a narrowly validated test-only
  address literal patched to the actual arena before its image becomes RX.
- `runtime-root`: an otherwise valid return under the wrong actual root fails.
- `runtime-kernel-trap`: a known emitted UD2 reached at CPL0 remains fatal.
- `runtime-entry-stack`: a deliberately guarded RSP0 transition reaches double
  fault on the separate IST, with exact instruction and CR2 evidence.
- `runtime-write`, `runtime-nx`: user image write and stack execution denial.
- `runtime-return`, `runtime-unknown`: forged return and unrecognized UD2 denial.
- `runtime-syscall`, `runtime-sysenter`: alternate inherited entry mechanisms
  cannot transfer user execution to firmware/kernel targets.

The 66 earlier modes remain acceptance gates. These tests establish this
bounded emulator mechanism, not arbitrary firmware correctness, DMA quiescence,
physical AMD support, SMP, hotplug, preemption, extended-state switching or
service APIs. Resource reservation, IOMMU isolation and interrupt ownership must
precede actual device activation.

The SYSENTER negative fixture selects
`qemu64,vendor=GenuineIntel,+sep` so that the instruction reaches the architectural
zero-CS check and produces #GP(0). QEMU's default AMD-vendor long-mode profile
rejects SYSENTER with #UD before that check. The separate fixture therefore
checks the disabled entry mechanism, rather than treating an unsupported
instruction as proof of the CS reset. This is an emulator-only CPU profile,
not an Intel or AMD physical qualification claim. See QEMU's
[decode check](https://github.com/qemu/qemu/blob/v10.0.0/target/i386/tcg/decode-new.c.inc)
and [SYSENTER helper](https://github.com/qemu/qemu/blob/v10.0.0/target/i386/tcg/seg_helper.c).

The independent corrected-source run on compiler
`351a46e42c1ad2e0b224d01a57f249039c37ffe44e051a5d67b420eae54c9174`
passed all fourteen runtime modes. Hosted checks include 1,274 arena/table cases
and immutable-layout policy tests under ASan/UBSan; image validation has three
positive and 64 negative cases, and transcript validation has fourteen positive
and 716 negative cases. The transcript policy independently constrains metadata
shape, integer types, fixed virtual layout, bounded/distinct sites and test
probe ranges before comparing events.

Development caught and fixed a stale stack word on repeated entry, an unused
absolute BIOS vector table rejected by the strict PIC gate, a short-image probe
patch subtraction underflow, and a receipt validator that previously allowed a
zero return PC when both metadata and event text were changed. These findings
remain recorded in the review evidence; earlier failed runs are not counted as
acceptance.

## Bounded multi-page consumer

`runtime-multipage` runs allocation-free incremental CRC32C over `123456789`
and decodes, counts and re-encodes a fixed UTF-8 array. Both images use the same
source; the second deliberately indexes past its array after completing the
work. The existing driver contains its emitted bounds trap, runs the healthy
image again, retires both domains, recreates one and checks zero outstanding
leases. Admission requires real called code and the bounds trap on page three.
Linked stack checks reuse the existing compiler-fact and disassembly validators.
Image backing is retained by the boot arena; teardown clears every mapping before
releasing stack leases. Hosted controls cover incomplete page construction and
reset/recreation. No executable allocator, writable executable alias, larger
stack, page-table pool, arena or kernel payload limit is introduced.

Protected runtime profiles end ACPI parsing temporaries before PCI discovery,
using the existing noinline preparation route and arena-owned MCFG snapshot.
For multipage, Call and snapshot admission, the shared linked discovery gate
rejects a parser-to-PCI call path and bounds the wrapper, parser and PCI frames.
Stack and fault-reserve caps are unchanged.
