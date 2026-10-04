# Independent M015 AMD-Vi discovery review

Date: 2026-10-03. Reviewer: independent AMD-Vi/IVRS task. Repository: `/workspace/scratch/48c5de6446f8/aurora`.

## Decision and status

The existing stopped-CPU control is acceptable **only as a bounded positive witness that the pinned QEMU binary records a valid 64-bit, same-zero CTRL write through the generic memory-region producer**. Its original whole-run no-interrupt criterion failed and remains failed. No new control run was requested or performed.

The read-only admission implementation is coherent with its narrowly selected QEMU profile. Independent host-policy execution passed 121,025 cases in both release and ASan/UBSan. The actual developmental read and write-fault streams also passed independent revalidation. All eleven independent actual modes now pass, the review findings below are closed, and the reviewed runtime/build source remained unchanged across the run. This approves the bounded M015 AMD-Vi discovery slice for the parent's separate full158 integration run; it does not claim that integration run has passed.

## Scope and ownership

Read AGENTS.md, README.md, completeness matrix, the IVRS observation contract, implementation, validators, source-provenance material, complete control protocol/trace, and developmental guest traces. Coordinated with the build owner before compiling only the policy test into this review's private temporary directory. Initial work was read-only plus isolated host tests. After an explicit exclusive image handover, this reviewer rebuilt and ran the eleven approved read-only/fault QEMU modes using fresh output directories, then verified normal-image restoration and handed ownership back. No additional positive write/control experiment, firmware-source modification, network configuration, socket, host-security setting or publication action was performed. Public pinned QEMU source files were read through the existing GitHub connector. No socket-denial retry occurred.

The build owner owns kernel/runtime/image changes; its validator worker owns IVRS smoke/trace/provenance validators. Review findings were sent to those owners rather than editing their files.

## Actual table, configuration and authority

- The captured table is 168 bytes, revision 1, checksum-correct, IVinfo 0x2801. It contains IVHD10 at offset48 (length52) and IVHD11 at offset100 (length68), representing one physical IOMMU. Both name segment0, requester0x18, capability0x40 and base0xfed80000.
- Both requester sets contain exactly 0x0000, 0x0008, 0x0010, 0x0018, 0x00f8, 0x00fa and 0x00fb. Duplicate same-type records, duplicate SELECT claims, mismatched pairs, unsupported aliases/ranges/special records and every IVMD fail closed. Independent live inventory equality is required, including the chosen NVMe requester and IOMMU identity.
- The actual PCI identity is 1022:1419, class0806, interface0, BDF0000:00:03.0. The bounded capability chain is 0x60 MSI -> 0x5c HT -> 0x58 MSI stub -> 0x40 AMD. Full header and capability bytes are each read twice and copied; no ECAM pointer escapes.
- Architectural admission rejects MMIO Enable=0 before installing an IOMMU window. The distinct compile-selected Qemu10_0_13AmdViCold path is not an automatic fallback. It requires the pinned profile's disabled bit and exact relevant capability constants; the launch/provenance validators bind the exact QEMU binary, options, clean firmware and pristine VARS.
- The parser's IVHD10 feature0x44 and IVHD11 EFR0x29d3 are intentionally different producer constants. QEMU truncates its IVHD10 HATS/GATS expression when serializing 32bits. This is not generic architectural equivalence. Physical AMD qualification still lacks a complete normative-specification review.
- Full [0xfed80000,0xfed84000) exclusion checks precede mapping, including both unobserved pages. Checked physical width, map classification/cache/runtime attributes, arena, ECAM, APIC/IOAPIC and independently reconciled assigned memory BARs constrain admission. The prior NVMe inactive-state check and BME-clear state are separately required.
- The supervisor UC, R/NX, nonglobal window performs only 64-bit reads at +0x18, +0x30 and +0x2020, expecting 0, 0x29d3 and 0. The two pages are unmapped with INVLPG between use; fresh PCI snapshots precede final revocation. The write probe targets a read-only PTE and must fault before device access. The revoked-read probe targets the already unmapped window. Exact linked opcodes, RIP, CR2 and page-fault codes are validated.

No IOMMU activation, translation tables, queue setup or DMA-isolation claim follows. In the pinned producer, CTRL.IommuEn=0 permits identity DMA regardless of the pt=off option. The IOMMU's own PCI command7 is distinct from the target NVMe command2; unrelated firmware-enabled bus masters are outside this observation contract.

## Separate control: what is actually established

Artifacts: `/tmp/aurora-m015-amdvi-control`. The preserved SHA256SUMS binds complete raw artifacts, including the original failed `trace-verification.json`. That file explicitly contains `strict_whole_run_absence_contract_passed: false`.

The invocation uses TCG/q35/qemu64/singleCPU/128MiB, -S, no default devices, no NIC, no drives, no serial/display/monitor, QMP stdio and local qtest pipes. QMP requests are strictly bounded and contain no `cont`. Both status observations are prelaunch/running=false; query-block is empty before and after. Nine register reads precede the sole `writeq 0xfed80018 0x0`; an immediate CTRL read and all nine post-read values agree with the before state. Native qtest and host protocol independently record the same 20 requests: 19 reads and one write. The standalone IOMMU is at00:01.0 because there is no NVMe device, which is explicitly checked rather than confused with the guest fixture's00:03.0.

There are exactly30 complete trace records:

1. Two initial IOTLB-reset events.
2. One CPU-1, width4 write to `amdvi-ir`, absolute0xfee00000, value0, followed by four interrupt-remap/pass-through events, with requester0xa0 and unchanged destination/data.
3. Nine pre-control register reads.
4. The sole CPU-1, width8 generic `amdvi-mmio` write to absolute0xfed80018, value0.
5. A misleadingly named `amdvi_mmio_read ... CONTROL` emitted by the valid write handler's shared trace helper; control_status0; disabled-buffer command_error0; immediate CTRL readback; nine unchanged post-reads.

The two generic writes have distinct region identities in the original trace. Mtree binds the register region to the complete16KiB physical aperture. The source's generic write accessor emits absolute address, region pointer/name, width and value immediately before dispatching `mr->ops->write`. For the aligned register region, valid writes cannot disappear merely because `amdvi_mmio_write` named events are absent. The named event is emitted only by the invalid-range branch. Register read events alone therefore cannot distinguish reads from valid writes; the generic-write producer is essential.

`amdvi_handle_control_write` sets the enable/queue flags from zero, updates zero status bits, emits control_status, and calls `amdvi_cmdbuf_run`. Its disabled-buffer branch emits command_error0 and returns before command execution, DTE/page-table access or queue traversal. Thus the expected error-named trace event is not evidence that a command ran.

The narrow witness does not establish whole-run interrupt absence, a clean global machine state, DMA isolation, physical behavior, cryptographic execution attestation or source-reproducible QEMU binaries. No before/after APIC state comparison was performed. The raw event list and original failure remain required evidence.

## Startup causality: source-derived explanation

The following is an inference from the exact pinned source and recorded device topology, corroborated by both full and no-IOMMU startup traces. It is not an independently instrumented call-stack trace.

1. QOM zero-initializes instance storage. The recorded main-system-bus order is AMD-IOMMU, PS2 devices, HPET, IOAPIC, q35-pcihost. Bus reset iterates its child list; reset hold handles children before the parent, and legacy reset is installed as the hold method.
2. AMDVI realization initializes once; its later device reset initializes again, accounting for the two initial IOTLB resets and devtab_len=0.
3. HPET reset calls `qemu_set_irq(pit_enabled,1)` before IOAPIC and the PCIhost/ISA PIT reset. The PC wiring connects this to `pit_irq_control`, which updates PIT channel0. Its initial zero mode0/count0 state makes `pit_get_out` return1, even with CPUs stopped. HPET forwards the legacy PIT IRQ0 to GSI0.
4. IOAPIC maps IRQ0 to pin2. Before its own reset, the initial redirection entry is zero/unmasked, yielding an edge fixed-delivery message with vector0 and destination0. `ioapic_service` performs a 32-bit store to0xfee00000 with data0 using `ioapic_as`.
5. With AMDVI, realization sets ioapic_as to the0xa0 pseudo-device address space. The `amdvi-ir` region receives offset0, reconstructs absolute0xfee00000, and enters `amdvi_int_remap_msi`. Since devtab_len=0, it copies the original message without DTE lookup and calls APIC send_msi. These are the observed four pass-through trace records. The access never enters the IOMMU register handler at0xfed80000.
6. Without AMDVI, pc.c leaves ioapic_as as address_space_memory. The same initialization path reaches `apic-msi` directly. The actual missing-IVRS run therefore begins with CPU-1, width4, address0xfee00000, value0, regionapic-msi, followed by NVMe reset at index1 and no AMD events. This justifies an exact missing-only startup sequence, not an arbitrary APIC whitelist.
7. pc_machine_reset subsequently resets APIC state after device resets. This source fact explains why startup IRQ effects need not survive initialization, but the control did not independently measure every APIC state field.

Pinned commit: `98f88efe8f07067667b8d9b1a5ce9551d34036c1`. Newly fetched source files and verified Git blob identities are in `source/provenance.json`. Relevant paths/lines: system/memory.c413-432,480-518; hw/i386/amd_iommu.c575-581,631-663,763-782,1233-1263,1374-1403,1533-1558,1625-1668; hw/i386/pc.c1024,1192-1197,1223-1233,1725-1739; hw/timer/hpet.c627-670; hw/timer/i8254.cpit_irq_control/pit_irq_timer_update; hw/timer/i8254_common.cpit_get_out; hw/intc/ioapic.cioapic_set_irq/ioapic_service; hw/core/bus.c89-99; hw/core/resettable.c143-164; hw/core/qdev.c772-795. The QOM zeroing excerpt is separately labeled as an excerpt, not a full-blob reproduction.

## Findings and closure

1. **Stack regression omitted inspect_bar.** The original regression checker bounded ACPI preparation, scan and IOMMU observation but omitted the function implicated in the actual guard fault. Reported to owner. Owner added a BAR path and is making inspect_bar explicitly noinline for IVRS to preserve an unambiguous .su frame. Closed by all eleven final .su sets and linked images: inspect_bar2272, discover_pci5552. A second non-peak subtotal omission, Topology::parse3184 under ACPI preparation, was then found and corrected in the checker only. See the final calculation below.
2. **Malformed control timing accepted.** Independent in-memory, manifest-resigned mutations showed that noninteger/backward `monotonic_ns` values and `[R corrupted]` native timestamp text passed. Protocol order still supports the original valid witness; the malformed-input acceptance weakens the claimed strictness. Closed: validator now requires exact protocol keys, positive strictly increasing integer monotonic timestamps, and nondecreasing numeric native timestamps with explicit relative-time syntax. The original counterexamples independently reject.
3. **Post-exit IRQ writes accepted.** Appended generic writes to APIC0xfee00300 and IOAPIC0xfec00010 passed the trace validator. Actual read receipts have firmware APIC EOIs/timer writes between loader entry and ExitBootServices, but none after its successful exit marker. Closed: validator rejects APIC/IOAPIC/HPET writes after the first byte of the successful exit marker, using both region identity and address overlap, including injected interleaving within that marker. Legitimate pre-exit firmware activity remains distinct, and startup sequences stay exact. This is coverage of those named controllers/apertures, not an assertion that every possible legacy interrupt-controller port or MSR is traced; reviewed M015 code performs no such programming.
4. **Missing-IOMMU startup assumption.** First eleven-mode development run's missing mode exited35 with the correct refusal but the old reset-index assumption failed. The measured direct APIC startup event is explained above. Closed: original captured evidence was retained unmodified, strict offline validation passed after the exact missing-only sequence correction, and the independent fresh missing-mode boot then passed.

## Historical stack fault limits

`/tmp/aurora-m015-profile/fault-debug.log` records a write page fault at RSP/CR2=0x6115f40, followed by double-fault delivery and another fault. Given the recorded arena0x60d2000 and fixed stack bottom arena+0x44000=0x6116000, the fault is exactly192 bytes below the16KiB stack bottom. The fix shortens ACPI and scan-temporary lifetimes; the fixed stack and guards are not widened.

The failed ELF and compiler .su files were not preserved before rebuild (the failure preceded stack-usage instrumentation). The build owner reports captured pre-fix disassembly frames inspect_bar0x868, discover_pci0x2948 and discover_acpi0xd88. This review independently confirms the measured guard fault but cannot bind that function attribution to a retained original ELF hash. Do not reconstruct a new binary and label it the original failed artifact.

## Independent executed checks

- Private release and ASan/UBSan builds of tests/kernel-uefi-ivrs.cpp:121025 each.
- Python optimized validators at initial reviewed revision: trace11 positive/650 adversarial; provenance11/532; serial11/1168; stack1/24.
- Raw stopped-CPU control manifest/protocol/trace: narrow witness accepted, whole-run interrupt absence explicitly false.
- Actual developmental read: `/tmp/aurora-m015-profile/read.{log,trace,status}`, read-firmware.log; status33, exactly3 IOMMU reads and closure.
- Actual developmental write-fault: `/tmp/aurora-m015-write-dev`; status35, exact page-fault/error3 and no generic aperture write.
- Source identity at this stage: `source-review-start.sha256`. Logs and privately compiled policy test binaries remain in this review directory.

## Final independent evidence and source identity

The fresh independent eleven-mode run finished with wrapper status0. Every mode passed serial, full hardware trace/control and provenance/linked-ELF validation:

- ivrs-default35: architectural MMIO-disabled refusal, no IOMMU register access
- ivrs-read33: exactly three approved reads and complete window/ticket closure
- ivrs-write35: linked write instruction faults with page-fault error3 before any device write
- ivrs-revoked35: linked revoked read faults with error0 after closure
- ivrs-pair35, ivrs-alias35, ivrs-reserved35: copied-table failures stop before PCI/MMIO observation
- ivrs-scope35: inventory-scope mismatch stops before BAR observation
- ivrs-capability35, ivrs-range35: capability/resource failures stop before IOMMU reads
- ivrs-missing35: exact no-IOMMU startup sequence and missing-table refusal

Receipts: `actual-eleven/<mode>/receipt.json`; each directory retains actual .su, stack-usage.json, payload.bin, payload.elf, fault metadata, loaded EFI image, raw serial/firmware/hardware traces, firmware VARS and invocation. `actual-eleven.log`, `.status` and `actual-eleven-summary.json` summarize the run. No additional valid IOMMU write was introduced by this independent run.

All261 tracked source/build/test inputs were unchanged before and after the actual run. `final-source-before.json` and `final-source-after.json` are byte-identical, SHA256 `34f5523ae4dd54d90ce4b0fd94da70044bcb2b142b83fa839ffd22c368d25260`. The compiler was pinned to `/tmp/aurora-m014-compiler-corrected`, SHA256 `2d86780c0082d861e7031955737eef81bb36936c7971d5032b6a1abbb4a24bf8`. Tools: GCC14.2.0 Debian14.2.0-19, GNU ld2.44, Python3.12.14. The QEMU binary remains SHA256 `d3c1a558ad220e77a4412048c8d96b44f8c2b41c7ad2a4ecfe522a4b122fe067`.

Normal restoration was verified before handback: payload SHA256 `1efd83fe4487f86d52755ce16b9fff8e7e607095c2892da3a253a7241da3d75a`; EFI loader SHA256 `4dd16765fae1bf2f5cb78cf20d2e6d5b493cbd390dfc704b6bb3320eadb5c2fb`; no IVRS symbols/markers, fault_offsets empty, payload text extent16384.

After handback, the **only** tracked change was the stack-checker correction for the Topology frame: tests/kernel-uefi-ivrs-stack.py changed from SHA256 `2429de52be491a450c2732890c5845133a01f41ff082d48e17b17b512a445bef` to `22f7ed6c7c2c4569e03ef82ae93f14d794309b41b569418a1bd7cdd67acc32c7`. Its27-negative self-test passed independently, and all eleven preserved .su sets matched the corrected checker without modifying their original records. `post-run-harness-correction.json` records this targeted revalidation; `source-after-harness-correction.json` records the resulting source identity.

Independent `recalculate-stack.py` reads all original .su sets separately from the project checker. It also accounts for Topology::parse and checks the actual640-byte resource parser,112-byte reservation parser,208-byte page verifier and four96-byte recursive walker frames. Maximum reviewed path subtotals are:

- ACPI preparation including Topology:8064
- PCI scan:12264
- BAR observation:9120
- IOMMU observation:9792

Adding the512-byte fault-delivery reserve gives a maximum12776 bytes, leaving3608 of the unchanged16384-byte stack unused. The linked default-mode disassembly confirms the inspected calls. The page-fault trampoline and48-byte payload_fail frame plus bounded serial routines fit well within the fault reserve. This remains a reviewed-call-path regression bound, not a whole-program stack-safety proof.

Final validator self-tests independently passed: serial11/4236 negatives, trace11/723 negatives, provenance11/532 negatives, stack1/27 negatives. The review's own regression script accepts the real bounded control and all eleven synthetic modes while rejecting69 independent timing/IRQ/aperture mutations. Host policy release and ASan/UBSan each passed121025 unchanged policy cases.

Remaining limits: full158 integration is the parent's next gate; no physical AMD qualification, IOMMU activation, DMA isolation, general driver support, complete normative-spec review, general stack proof or production safety proof is established. The original broad control failure and original stack-failure artifacts retain the limitations described above.
