# AMD-Vi same-zero CTRL trace coverage control

A single disposable stopped-CPU QEMU control ran with normal tool execution and exited 0. Its bounded CTRL producer witness and pre/post state checks pass. The complete-run no-interrupt-event criterion fails because the trace also records an initialization interrupt path before the first qtest MMIO read. This report does not broaden acceptance or hide that sequence.

## Artifacts

- `control.py`: exclusive one-run guard, exact argv, source/QEMU hash preconditions, local QMP process pipes and qtest FIFOs; no sockets or network listeners.
- `invocation.json`, `preflight-provenance.json`: exact command/environment override and input SHA-256 hashes.
- `protocol.jsonl`, `qtest-native.log`: all QMP and qtest requests/responses; exactly nineteen readq requests and one writeq request.
- `trace.log`, `trace-enable-events.txt`, `trace-help-*.txt`: complete unfiltered trace and all 39 available AMD-Vi events plus memory_region_ops_write and pci_cfg_write enabled.
- `result.json`, `registers-before.json`, `registers-after.json`, `query-pci-before.json`, `query-pci-after.json`, `qtree.txt`, `mtree.txt`: state and device evidence.
- `process-result.json`, `control-tool-result.json`: QEMU exit 0 and normal control tool result (chunk fcabae).
- `verify-trace.py`, `trace-verification.json`, `verifier-tool-result.json`: independent offline evidence validation. The verifier intentionally exits 1 for the failed whole-run absence criterion (chunk 806660); it never launches QEMU.
- `preflight-result.json`, `source-excerpts.txt`: original static trace-contract mismatch and pinned source excerpts. Preflight was paused before launch, then the observation contract was revised without changing the single authorized write.
- `SHA256SUMS`: hashes of all regular artifact files except the manifest itself. FIFOs are not regular files and are excluded.

## Exact bounded witness

Trace line 17 records `memory_region_ops_write cpu -1 mr 0x56292ba5c1c0 addr 0xfed80018 value 0x0 size 8 name 'amdvi-mmio'`. The region aperture is [0xfed80000, 0xfed84000), so its relative offset is 0x18. It is immediately followed by the CTRL helper trace, `amdvi_control_status MMIO_STATUS state 0x0`, and `amdvi_command_error error: Executing commands with command buffer disabled 0x0`.

QMP status before and after is prelaunch/running=false. Both block backend queries are empty, PCI topology is unchanged, and no cont/resume or guest PCI configuration write was requested. Pre/post CTRL, device-table base, command base, event base, exclusion base/limit, PPR base, and status are all zero; EFR stays 0x29d3. The one write is width 8, zero to already-zero CTRL. The immediate readback is zero. Source shows that the expected command_error is the disabled-buffer early return before command execution.

## Preserved whole-run failure

Trace lines 3–7 precede the first qtest MMIO read and contain:

- A generic write at 0xfee00000, width 4, value 0, region identity 0x56292ba5c4f0, name amdvi-ir.
- amdvi_mem_ir_write_req
- amdvi_ir_remap_msi_req
- amdvi_ir_remap_msi
- amdvi_mem_ir_write

These are present in the raw trace and enumerated as unexpected records by the strict verifier. They are not an issued qtest write and are not caused by the later CTRL write. Nevertheless, a whole-run claim of zero interrupt-path events would be false. No rerun, changed machine, filtered trace, or alternative route was attempted.

## Producer and scope limits

In the pinned QEMU source, the event named amdvi_mmio_write exists only in the out-of-range branch. Valid writes use the confusingly named amdvi_mmio_read helper event. Absence of amdvi_mmio_write therefore does not establish absence of valid writes. The generic memory event is the actual width/value/address/region witness.

This is separate coverage evidence, not an accepted clean-controller run, proof of DMA isolation, command-queue exercise, or physical AMD validation. pt=off is not isolation. No explicit firmware image is supplied; Q35 may map its default BIOS from -L, but the CPUs remain stopped and no firmware executes.
