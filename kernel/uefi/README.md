# UEFI handoff consumer

This separate x86-64 OVMF gate establishes a checked firmware-to-kernel handoff.
It does not port the BIOS scheduler into UEFI or qualify a physical Framework.
The BIOS image and its 28 protection/domain/preemption gates remain independent.
The loader is temporary trusted C++/assembly. The payload executes actual
Aurora-generated code after firmware services have ended.

## Run

```
./scripts/kernel-uefi-build.sh
meson test -C build/meson --suite full
meson test -C build/meson --suite guest-uefi
```

The build uses the existing g++, GNU as/ld/objcopy/nm/readelf, Python3 and Bash.
GNU ld's i386pep backend emits PE32+ EFI subsystem10 with DIR64 relocation.
Some native linkers omit that backend; select a capable PE linker with `UEFI_LD`
(see [dependencies](../../docs/local-development.md#tools-and-explicit-selections)).
A separate cross C++ compiler is not required. The loader and payload include
small assembly `memcpy`, `memset`, `memmove` and `memcmp` implementations for
compiler-generated freestanding calls. These are trusted bootstrap code, not
Aurora-language C compatibility. QEMU system x86 and OVMF are additional test
requirements. QEMU runs q35/TCG/qemu64, one CPU,128MiB RAM, selected OVMF firmware,
and a FAT directory with a temporary snapshot overlay. The source directory is
read-only, the overlay is discarded, and no host disk or firmware is changed.
Firmware discovery and explicit combined or split CODE/VARS overrides are
documented in [local development](../../docs/local-development.md#tools-and-explicit-selections).
Split VARS changes are discarded through a QEMU snapshot.
QEMU_DATA and LD_LIBRARY_PATH can select locally extracted dependencies; AURORAC
can pin a previously built compiler. All modes restore the normal UEFI image
when they finish; they do not rebuild or overwrite the BIOS disk image.

The verified local dependency was official Debian ovmf2025.02-8+deb13u1:
https://deb.debian.org/debian/pool/main/e/edk2/ovmf_2025.02-8+deb13u1_all.deb
SHA256:78e0d54df11fc77406cb7a0bc9a39e5bca6d1cbe06556b91d9a73491c52decdf,
checked against Debian's package index before extraction. The combined ROM used
is usr/share/ovmf/OVMF.fd. Dependencies stay outside the repository; there is no
host package installation. Firmware absence or timeout is a blocked/failed gate.

## Ownership and wire contract

The EFI entry validates the system and Boot Services table signatures, lengths,
revision and CRC, and checks the required service entries. The hardware ABI
adapter uses the specified x86-64 UEFI calling convention. No such interface is
exposed in Aurora source, and this does not establish language C compatibility.

AllocatePages allocates one1MiB EfiLoaderCode arena below4GiB. Code allocation
allows the copied transition to execute under firmware mappings before the
kernel takes over; final permissions are imposed by our own tables. Firmware
allocation success establishes ownership. The final memory map independently
checks the arena's coverage/type/runtime attributes; arbitrary EfiLoaderCode
records do not become authority to allocate somebody else's pages. Only the
specific allocated arena is handed to this bounded consumer.

The128-byte version1 header uses byte-explicit fields. Offsets relative to the
page-aligned arena are fixed and non-overlapping:

- Header at0, mapped read-only/NX
- Firmware descriptor copy at0x1000, maximum64KiB, read-only/NX
- At most16 private page-table pages at0x11000, supervisor RW/NX
- Copied position-independent transition/GDT at0x21000, supervisor RX
- Independent payload at0x22000, at most152KiB, separate RX/R-NX/RW-NX sections
- Owned IDT at0x48000, supervisor RW/NX
- Guard at0x49000, then stack0x4a000..0x4e000, supervisor RW/NX; 0x4e000..0x50000 absent
- Bounded16-page allocation pool at0x50000, supervisor RW/NX

Other arena pages stay absent. The map parser accepts version1 descriptors with
stride40..256 bytes in multiples of8, at most512 entries and64KiB total. It rejects
truncation, zero-length/unaligned/overflowing regions, unknown memory types and
all overlapping descriptors. Grant checks reject runtime-tagged arena records
and require full coverage by a loader-code record. Reserved, MMIO, ACPI and
runtime regions are never used for the pool. Valid runtime regions elsewhere in
the map are retained as reserved evidence, not incorrectly treated as malformed.

GetMemoryMap/ExitBootServices has a hard three-attempt bound. The last map key is
used immediately, with no intervening firmware allocation or unrelated service
call. After EFI_INVALID_PARAMETER, only another map/exit pair is attempted;
direct serial logging uses no firmware service. A too-large returned map length
is rejected before constructing a view. The stale-key test deliberately supplies
an incorrect first key; the exhaustion test supplies three incorrect keys.
No loader failure returns into firmware after a successful exit.

## Independent execution and protection

The payload is separately linked at zero and copied into the owned arena.
Offline validation permits only PC-relative relocations in its input objects;
no payload GOT, absolute-address fixup or unresolved runtime dependency is allowed.
Explicit hidden assembly-symbol declarations prevent an ELF linker relaxation
from silently replacing a supposedly relative entry-address reference with an
absolute address. The loader's PE DIR64 relocation is independently validated and
exercised by a relocated data pointer under OVMF.

The transition enters its own stack, installs an arena-owned IDT, switches CR3,
loads a private GDT and jumps to the independent payload. Descriptor Accessed
bits are pre-set because the GDT shares an RX page; a real QEMU page fault found
the initial attempt to let the CPU write those bits. Firmware PCIDE/LA57 modes
are rejected. PGE is explicitly cleared before switching roots, flushing global
translations that a plain CR3 write could retain. The payload independently
checks these modes, CR3, stack, IF, CR0.WP and EFER.NXE.

A bounded complete page-table walk rejects cycles, repeated table aliases,
out-of-pool links, unexpected flags and every extra leaf mapping. It checks all
expected arena pages and absent guards. Thus the successful payload depends on
its own mappings, rather than continuing under assumed firmware identity maps.
No firmware service pointer is present in the handoff. The old PE image and
firmware ranges are absent from the new tables, and no runtime services are used.

The payload allocates a page only from its retained arena, writes and reads every
byte, releases its ownership ticket and executes the generated kernel function,
requiring42. Real supervisor write-to-text and execute-data probes produce
page faults14/3 and14/17 on the private IDT, then fail-stop.

## Gates and limits

`uefi/production` is the one production UEFI image: this loader and payload with
ACPI, PCI, the protected runtime, IPC, budgets, the protected program console and
its graphical terminal, and no fixture selector, test hook or capture handshake
(`production-profile.hpp`, `graphical-profile.hpp`). Its loader captures the GOP
mode before the final map, admits it under the firmware rule on every exit
attempt and hands off version 7: a 136-byte header whose word 120 is the runtime
metadata and word 128 the read-only framebuffer record page at 0xe0000. Every
other image keeps the 128-byte header and rejects v7. After the shared timer maps
the LAPIC, the runtime restores the framebuffer admission from the record,
installs its leaves and verifies the paired tree before the console starts
([fixture consolidation](../../docs/kernel-fixture-consolidation.md#production-image)).

The eight OVMF modes are normal, stale, stale-exhausted, bad-handoff, bad-map,
bad-table, wp and nx. `normal` boots the ordinary image; the other seven, with
`acpi-duplicate-root`, are cases of the one `platform-fixture` image, which also
carries the ACPI, PCI, BAR and IVRS cases. Its loader reads a decimal selector
from the QEMU fw_cfg file `opt/aurora/fixture` at entry (before ExitBootServices,
while OVMF still owns the UART), echoes it as `AURORA_FIXTURE_SELECTED: value=N`,
and copies it into one extra handoff word that the payload admits only within the
image's interval; a missing, malformed or out-of-image file fails at entry. The
`display-fixture` (framebuffer and graphical-console), `device-fixture` (console
and owned-bytes), `storage-fixture` (RAM file, scratchpad and namespace), `snapshot-call-fixture`
(blocking Call and snapshot) and `text-fixture` (file-call console, owned text and console region)
images read the same row (`loader-fixture.hpp`). Ordinary images have neither the fw_cfg reader nor the word. They validate successful ownership transfer, bounded retry,
rejection before accepting malformed metadata, rejection of an extra low-memory
mapping, and actual hardware W^X enforcement. Hosted tests exercise124 descriptor,
header and complete-tree cases; image validation has14 negative PE/payload cases;
transcript validation has8 positive and148 negative cases under Python -O.

Firmware is part of the trusted computing base. This is not a cryptographic
attestation, arbitrary image loader, Secure Boot implementation, general ACPI/AML implementation,
UEFI runtime-services mapping, DMA/device-quiescence protocol or IOMMU boundary.
NMI/SMI behavior during the brief descriptor/root transition and physical-device
interrupt/DMA behavior are not qualified by this OVMF gate. The payload does not
run user domains or the scheduler yet. The BIOS path remains the evidence for
those mechanisms. Persistent storage, multi-user policy and Framework component
drivers remain separate future dependencies.

Primary sources:
[UEFI2.11 Boot Services](https://uefi.org/specs/UEFI/2.11/07_Services_Boot_Services.html),
[UEFI system table](https://uefi.org/specs/UEFI/2.11/04_EFI_System_Table.html),
[TianoCore OVMF](https://www.tianocore.org/tianocore-wiki.github.io/platforms-packages/platform-ports/ovmf.html),
and [Intel SDM Volume3A](https://cdrdv2-public.intel.com/671190/253668-sdm-vol-3a.pdf).

## Optional ACPI discovery profile

The [ACPI read-window gate](acpi.md) extends this handoff with a version2 RSDP
reference and bounded source-copy buffers. It discovers real OVMF processor/APIC
metadata after ExitBootServices, with read-only/NX mapping revocation and hostile
input/hardware-fault gates. The default version1 consumer remains available.
Run `meson test -C build/meson --suite guest-acpi`; this does not enable AML, interrupt routing or
a physical device driver.

The next read-only discovery slice is [MCFG/PCI ECAM inventory](pci.md), using
an explicit OVMF/q35 aperture and a revocable UC mapping window. It provides
controller identities, not device activation or physical Framework support.

[Sequential protected user domains](runtime.md) now have a separate version-3
handoff profile, backed entirely by the owned arena for the explicit OVMF profile.

The staged request/reply IPC profile is documented in [ipc.md](ipc.md) and
has its own protocol, authority and restoration gates.

The opt-in [UEFI service-budget profile](service-budget.md) adds verified local-timer
preemption and recovery of a non-yielding staged service. See its dedicated
acceptance gates and emulator-only boundaries.

The [three-domain staged dispatcher](dispatcher.md) provides bounded staged
request/reply scheduling. The [all-controlled-user-phase budget and retirement
contract](user-phases.md) adds isolated client recovery. All four, and the resume
row, are boot-selected rows of the one `service-fixture` test image
([fixture consolidation](../../docs/kernel-fixture-consolidation.md#service-fixture)).
These emulator profiles do not establish physical hardware support or a general scheduler.

## NVMe page preparation

The [fixed five-page CPU preparation contract](NVME-QUEUE-PREPARATION.md)
describes an opt-in, namespace-free BAR fixture using the existing allocation
pool. It does not activate NVMe or DMA.
