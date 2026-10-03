# AMD platform support: target and evidence

Status: planning requirements, researched 2026-10-02. **No physical AMD platform or AMD GPU is currently supported or tested.** The existing BIOS/QEMU bootstrap reports 42; it does not enumerate a GPU, implement a UEFI loader, or establish a hardware support claim. Do not install its disk image on hardware.

The requested coverage is **all Zen CPU generations and Navi/RDNA onward GPUs, both integrated and discrete where applicable**. This defines the target family range, not a tested device list. Inventory actual product/PCI identities and IP versions within that range rather than assuming every family name is a complete hardware specification. Later generations enter the support matrix only when documentation and conformance evidence exist; no future device capabilities are assumed. Pre-Navi GPU support is not a requirement merely because an in-scope Zen CPU can be paired with one. CDNA-only accelerators are not automatically included by the Navi/RDNA requirement.

## Two deployment contracts

1. **Cooperating new platforms:** vendors implement Aurora's [device contract](device-contract.md), with open firmware, versioned discovery, queue protocols, isolation guarantees, and conformance tests. This permits a native ABI throughout the system. Vendor cooperation is an assumption, not an achieved implementation.
2. **Existing AMD PCs:** preserve hardware programming requirements and the platform's actual firmware interfaces through deliberately narrow adapters. Removing C source/binary compatibility does not remove register layouts, firmware calling conventions, DMA protocols, or device microcode requirements. If all legacy firmware ABIs are forbidden, those platforms need replacement firmware exposing the native contract before Aurora can boot them.

Open firmware does not make different silicon identical. AMD's [openSIL description](https://www.amd.com/en/blogs/2023/empowering-the-industry-with-open-system-firmware-.html) concerns silicon initialization; it is not evidence that every AMD board and GPU has fully replaceable, open firmware. Existing GPU firmware validation/loading is part of the hardware-specific driver model below.

## CPU and platform work

The AMD64 system-programming baseline covers mode transitions, paging, exceptions, interrupts, processor initialization, and multiprocessing. Aurora must discover CPU capabilities rather than assume optional instructions or uniform topology. Required work includes per-CPU stacks/state, IDT/TSS, page faults, memory protection, cache attributes, atomic ordering, timer calibration, AP startup, TLB shootdowns, and saving enabled extended register state. CPU family/model/stepping errata and microcode policy belong in each hardware qualification record. See the [AMD64 System Programming Manual](https://docs.amd.com/v/u/en-US/24593_3.44_APM_Vol2).

For existing UEFI machines, implement memory-map acquisition, a correct ExitBootServices transition, reserved/runtime memory handling, and explicit runtime-service policy. Boot services cannot remain the OS's permanent driver layer after that transition. See [UEFI boot services](https://uefi.org/specs/UEFI/2.10/07_Services_Boot_Services.html?highlight=exitbootservice).

Discover interrupt controllers/topology through validated firmware data; implement required ACPI tables and AML methods for the supported board profile, including enumeration, power and wake behavior. ACPI is a separate requirement from AMD64 instruction support. See the [ACPI software programming model](https://uefi.org/specs/ACPI/6.6/05_ACPI_Software_Programming_Model.html).

Aurora engineering requirements for an existing-PC profile additionally include PCI/PCIe enumeration, configuration access, resource/BAR mapping, MSI/MSI-X, bridge topology, reset and hotplug; storage, USB/input, network and audio drivers are separate tasks even on an AMD-branded machine. Components may come from other vendors.

The isolated-driver profile requires DMA translation and interrupt isolation appropriate to the platform. Specify IVRS discovery, device identity mapping, translation invalidation, fault handling, teardown completion, and peer-to-peer/isolation-group behavior against the [AMD IOMMU specification](https://www.amd.com/content/dam/amd/en/documents/processor-tech-docs/specifications/48882_IOMMU.pdf). A GPU virtual address space alone is not the platform's complete DMA security boundary. Unknown isolation behavior must fail qualification rather than silently downgrade the promised security profile.

## GPU support is several independently tested facilities

AMD GPUs combine versioned IP blocks, with ASIC-specific initialization/reset behavior. The primary driver documentation distinguishes memory management, interrupts, PSP firmware validation/loading, SMU power management, display, SDMA, graphics/compute and media engines. APUs share platform components with the CPU and require coordinated power transitions. Dedicated versus shared memory also affects buffer placement. Queue management, indirect command buffers, GPU page tables and doorbells require hardware-specific handling. These are implementation constraints, not a requirement to copy Linux's ABI. See [official amdgpu driver architecture](https://docs.kernel.org/6.17/gpu/amdgpu/driver-core.html).

Treat GCN, RDNA and CDNA as architecture families, not one interchangeable device. The [upstream amdgpu overview](https://www.kernel.org/doc/html/latest/gpu/amdgpu/index.html?highlight=driver) identifies those families. Record the PCI identity, revision and actual IP versions for every qualified device; do not infer capabilities solely from its marketing name. A compute accelerator need not provide a display output.

- **Early pixels:** a firmware-provided linear framebuffer may permit a boot console after a validated handoff. GOP's pixel output is not a shader, command-submission or compute driver. Handle pixel format/stride, bounds, mapping attributes and unavailable linear buffers. [UEFI graphics output](https://uefi.org/specs/UEFI/2.11/12_Protocols_Console_Support.html)
- **Native display:** add modesetting, connector detection, EDID, link training, scanout/page flips, hotplug and display power transitions for each supported display block. Test actual connectors/monitors. [AMD display manager](https://cdn.kernel.org/doc/html/latest/gpu/amdgpu/display/display-manager.html)
- **Acceleration:** Aurora's proposed gate requires allocator and GPU-VM isolation, validated submissions, fences, scheduling/preemption, shader compilation, hang detection and reset recovery. A triangle or compute result alone is insufficient; hostile workloads and stale mappings must also be contained.
- **Additional features:** media codecs, audio over display, advanced display features and performance/power tuning each need explicit capability reporting and tests. Unsupported features must return an error.

AMD publishes [architecture/ISA documentation](https://gpuopen.com/amd-gpu-architecture-programming-documentation/) for shader programming. ISA documentation alone does not provide a complete display, memory, scheduling and firmware driver.

## Qualification order and stopping rules

The full coverage target is set. The user selected Framework Laptop 13 with Ryzen 7 7840U as the first complete-machine target on 2026-10-03; exact board/firmware and replaceable-component identities remain pending. See the [Framework qualification inventory](framework-13-7840u.md). Selecting an initial test tuple sequences engineering without narrowing the requested final family range. Define whether it uses native cooperating firmware or existing interfaces. Then qualify CPU/memory/interrupts, SMP/isolation, PCIe/DMA, minimal device services, display, acceleration, and power/recovery, in that order where dependencies require it. Use simulation before destructive fault scenarios on dedicated test equipment.

For each release, publish exact hardware revisions, firmware identities, build identity, supported features, test logs, fault-injection outcomes and exclusions. Expand a support list only after another tuple passes. All Zen and Navi/RDNA onward is the coverage objective, not a present acceptance result or a finitely testable promise about unknown future devices.
