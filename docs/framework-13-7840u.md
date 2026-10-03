# First complete-machine target: Framework Laptop 13 / Ryzen 7 7840U

Selected by the user on 2026-10-03. **Target, not supported hardware. No Aurora
physical-machine qualification has run.** The existing emulator image must not
be installed on a laptop. This profile sequences the broader all-Zen and
Navi/RDNA-onward goal; it does not replace that goal.

## Identity and source baseline

The selected model is Framework Laptop 13 (AMD Ryzen 7040 Series), Ryzen 7
7840U. Framework identifies it as an 8-core/16-thread Zen 4 processor with
Radeon 780M, 12-compute-unit RDNA 3 graphics. Its launch documentation names
RZ616 or a compatible replacement Wi-Fi card and DDR5 memory. These facts do
not identify the exact devices installed in a particular upgradeable laptop.
[Framework's model announcement](https://frame.work/blog/announcing-the-framework-laptop-13-powered-by-amd-ryzen).

The four expansion positions are not interchangeable: the two rear positions
provide USB4; front-left provides USB 3.2 and DisplayPort Alt Mode; front-right
provides USB 3.2 without display Alt Mode. Qualification must test each position
and supported card combination, including charging and hotplug, rather than
claiming all ports have every capability. See the same announcement and the
[vendor port matrix](https://knowledgebase.frame.work/usb-port-definition-matrix-framework-laptop-13-HkHVUHaTge).

Framework publishes mainboard/module documentation, connector information and
links to embedded-controller firmware and expansion-card projects in its
[hardware repository](https://github.com/FrameworkComputer/Framework-Laptop-13).
Published partial schematics and open EC sources are not evidence that every
component's firmware or complete programming specification is open. Aurora's
cooperative-firmware assumption remains a design option; a claim about an actual
stock laptop must use its actual interfaces and available firmware.

Before physical qualification, record board revision, CPU stepping, BIOS/EC and
microcode versions, RAM configuration, PCI IDs/revisions/subsystems, USB IDs and
interface descriptors, ACPI identities, panel/EDID, SSD model/firmware, wireless
module, audio/input/camera/fingerprint components, battery and expansion cards.
Record relevant capabilities without collecting user files, passwords, network
credentials, serial numbers or other unnecessary identifiers. Exact replaceable
parts remain pending. Do not guess controller IDs from the CPU's marketing name.

## User-provided component inventory

On 2026-10-03 the user supplied these identifiers verbatim: `mt7921e`,
`PIXA3854`, `Goodix USB2.0`, `generic webcam`, `r8152`. They take precedence
over an assumed factory wireless/adapter configuration. Treat them as reported
identifiers, not independently enumerated hardware or tested Aurora drivers.
`mt7921e` is the requested wireless-driver target and `r8152` the requested
wired-adapter driver target; exact supported chip/revision identities still need
verification. Preserve `PIXA3854` exactly until its device path/transport is
confirmed. The Goodix and webcam labels need VID/PID/interface descriptors;
do not infer a biometric or camera protocol solely from a display name.

The historical vendor reference to RZ616 does not override this inventory.
Additional board, storage, display, audio and firmware details remain pending.
Framework's [touchpad documentation](https://github.com/FrameworkComputer/linux-docs/blob/main/touchpad.md)
includes the PIXA3854 touchpad identity; the target's actual HID descriptor and
transport must still be recorded. The upstream
[mt7921 PCI driver](https://github.com/torvalds/linux/blob/master/drivers/net/wireless/mediatek/mt76/mt7921/pci.c)
and [r8152 driver](https://github.com/torvalds/linux/blob/master/drivers/net/usb/r8152.c)
are reference points for device-ID discovery, not authorization to reuse their
code without license review or a promise of Linux driver binary compatibility.

## Acceptance inventory

Every row below is **unqualified on physical hardware**. Requirements are Aurora
engineering acceptance criteria, not claims extracted from vendor documentation.
Each implementation must have simulator/host adversarial tests followed by
recorded tests on the exact hardware/firmware tuple.

| Area | Required behavior and failure gates |
|---|---|
| Boot/mainboard | UEFI loader and memory-map handoff; firmware-table validation; reserved memory preserved; repeatable cold/warm boot and recovery media; native firmware adapter boundary documented |
| Boot/update trust and recovery | Define the authenticated boot and package/firmware trust chain, key enrollment/revocation and recovery authority; qualify the selected Secure Boot policy and any measured-boot/TPM dependency on the actual firmware. Document antirollback policy, including authorized recovery to older images, vulnerability exposure and data-format compatibility; test corrupt, interrupted and rejected updates without relying on irreversible version locks |
| Firmware lifecycle | Inventory trusted BIOS, EC, CPU microcode and device firmware; validate provenance and compatibility before activation. Qualify supported update/recovery paths and interrupted-update behavior on dedicated equipment; do not assume stock firmware is replaceable or that an OS rollback also rolls firmware back |
| CPU/memory | Discover all enabled cores/threads; SMP startup, preemption, atomics, TLB shootdowns and complete enabled extended-state isolation; quota/exhaustion tests; no dependency on the emulator's fixed APIC base or memory map |
| Interrupts/time | ACPI-discovered topology and routing, feature-detected timers, calibration where time units are promised, MSI/MSI-X and interrupt-storm containment; no fixed clock assumptions |
| PCIe/DMA | Enumerate bridges/resources; validated BAR mappings; IOMMU/interrupt isolation, mapping revocation and quiescent teardown; malicious/stale DMA and device-reset tests |
| External-device trust | Establish DMA protection before enabling bus mastering or USB4 PCIe tunneling, including boot, hotplug and resume; define authorization while locked and during recovery. Reject unsupported isolation topologies rather than silently enabling unisolated devices; exercise pending DMA and interrupts across revocation and frame reuse |
| Storage | Exact NVMe controller/firmware support; bounded queues, timeout/reset recovery, flush/durability ordering, discard semantics, error propagation and media/full-device handling |
| Persistent filesystem | Native ownership/permission-aware file service; documented crash-consistency model, atomic operations, quotas, corruption detection/recovery and power-loss fault injection on disposable images before dedicated disks |
| Multi-user | Accounts, authentication, session lifecycle, authority delegation/revocation, per-user storage and resource quotas; two simultaneous users cannot read each other's protected files, IPC, clipboard, input or device streams; administrative actions audited |
| Credentials and data at rest | Validate entropy readiness before generating keys; use reviewed credential derivation/storage and bounded authentication attempts. Specify encrypted storage, key isolation and explicit recovery-key handling; test lost credentials, unavailable security devices and interrupted key changes. State protection limits for unlocked sessions, suspend, any hibernation/swap and crash dumps; recovery must neither silently bypass user protection nor imply guaranteed recovery without keys |
| Graphics/display | Radeon 780M-specific discovery/firmware/IP handling; internal panel brightness/modesetting, external outputs/hotplug, GPU memory/submission isolation, rendering/shader support, fences and reset recovery; framebuffer-only output is insufficient |
| Wired networking | User-reported r8152 adapter target and its actual controller/USB identity; link changes, packet validation, IPv4/IPv6, address configuration, DNS and native socket-equivalent capabilities; unplug/reset without stale authority |
| Wi-Fi | User-reported mt7921e target, exact installed chip/revision to verify; separately qualified replacement cards; scanning, association, WPA2/WPA3 profiles, regulatory constraints, reconnect/roaming and power transitions; actual radio/firmware identities recorded |
| Bluetooth | Exact controller and firmware; pairing/security, reconnect, input/audio profiles selected for release, radio coexistence, suspend/resume and user/session ownership |
| USB/USB4/cards | Host controllers, hubs, Type-C/PD coordination and applicable tunneling; every supported slot/card pairing, data/display/charging role changes, unplug and malformed descriptors; DMA authority revoked before reuse |
| Keyboard/touchpad | Actual transport/controllers; keyboard layout, modifiers, repeats, gestures, backlight, wake and hotplug; only authorized session receives input |
| Audio | Actual codec/controller path; speakers, microphones, headset detect and display audio; mixing, stream isolation, underrun/recovery, mute and privacy controls |
| Camera/sensors | Camera capture and privacy switches; any enumerated ambient/light or other sensors; bounded buffers, permission revocation and no continued capture after revocation |
| Fingerprint/security devices | Identify actual devices and available protocol; secure enrollment/template handling and authentication integration; ordinary password login remains usable; do not mark omitted hardware complete |
| Battery/EC/thermal | AC/battery reporting, charging policy, fan/thermal safeguards, CPU/GPU power policy, low-battery action and safe shutdown; preserve firmware safety limits |
| Sleep/wake | Supported platform sleep states, lid and authorized wake sources; repeated battery/AC and docked/undocked cycles; restore device isolation and protected sessions before exposing input/output |
| Desktop/developer system | Native tiling desktop, display protocol, terminal/shell, package management, installer and recoverable updates; multi-user graphical sessions and native developer builds |

Optional peripherals and unsupported configurations must be named explicitly.
Their exclusion cannot silently redefine the user's whole-laptop target. A
release may claim a narrower tested stage while the complete-machine gate stays
open. Performance and energy budgets must be measured and published, including
idle, interactive, sustained load, suspend drain and recovery latency.

## Dependency order and completion rule

1. Emulator nucleus: validated language/libraries, isolation, preemption, IPC,
   authority and resource accounting.
2. Firmware/platform discovery, UEFI boot, SMP and DMA-safe driver framework.
3. Persistent storage/filesystem and multi-user services; basic input/network.
4. Native graphics and desktop; audio, wireless, camera and remaining devices.
5. Complete power management, suspend/resume, adversarial multi-user/device
   recovery, installer/update rollback and sustained physical-machine testing.

Work may overlap when prerequisites permit. No calendar completion estimate is
implied. A Framework-complete claim requires every mandatory row to pass on a
recorded configuration with reproducible build identity, logs, known limitations
and recovery procedures. A QEMU pass, boot screen, or successful CPU instruction
is not a substitute. Physical installation and destructive tests need a later
explicitly authorized dedicated test setup; no current permission is inferred.
