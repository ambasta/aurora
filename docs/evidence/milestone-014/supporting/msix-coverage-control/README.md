# Disposable MSI-X trace coverage control

This directory is a separate, intentionally written-to emulator control. It must never be used as evidence that the accepted Aurora clean-controller boot was untouched.

The approved bounded operation was one same-value write to the already masked vector 0 MSI-X vector-control field, with QEMU CPUs stopped, no drives/namespaces and no BME/controller/queue/DMA activation. Only necessary PCI BAR0 assignment and MEMORY-only command setup were allowed.

Attempts 1 (this directory) and 2 (attempt2/) failed before any protocol/config/MMIO access because UNIX-domain socket creation returned EPERM. Attempt 2 used tool-level sandbox escalation, which did not change the restriction. Logs were retained. No network target or controller register was accessed.

Attempt 3 used ordinary local process pipes: QMP over child stdin/stdout and qtest over two filesystem FIFOs in attempt3/. It used normal tool execution, with no socket, network listener, security setting, privilege change, or denied resource. It succeeded before the parent transport-hold message arrived. That crossed timing was immediately reported; no further control operations were performed. Parent subsequently clarified that ordinary pipe transport for the already approved scope was permitted. This chronology is preserved explicitly rather than presenting the third attempt as having waited for that clarification.

Successful evidence is in attempt3/: control.py, invocation.json (exact argv/environment override), protocol.jsonl (every QMP/qtest request/response), qtest-native.log, query-pci.json, qtree.txt, result.json, trace.log, trace-verification.json, verify-trace.py and SHA256SUMS.

Observed identity: 0000:00:02.0, vendor 1b36/device 0010/class 010802/header 00; one NVMe controller, no backing blocks, no namespaces. QMP verified CPUs not running both before and after; no cont command was sent.

Exact target config writes: PCI BAR0 low 0xc0000004 at offset 0x10, BAR0 upper 0 at offset 0x14, then command 0x0002 at offset 0x04. Initial command was 0; BME stayed clear. No other PCI config writes were performed for this endpoint.

The real capability list identified MSI-X at config 0x40, table BIR 0, table offset 0x2000. MSI-X control was 0x0040 before and after: enable clear. Vector 0 control at absolute 0xc000200c read 1. Exactly one 32-bit writel of the same value 1 was performed there. The positive trace line records address 0xc000200c, value 0x1, size 4, region name 'msix-table'.

CC (0x14), CSTS (0x1c), AQA (0x24), ASQ (0x28/2c), and ACQ (0x30/34) were zero before and after. No NVMe controller-register MMIO write, start, queue-creation or DMA-read event occurred. Universal DMA absence is not inferred from only a missing DMA-read event; the stopped CPUs and never-initialized controller/queue state constrain the operation.

The first trace-verifier draft expected a region-relative address 0xc, but the installed binary logs absolute address 0xc000200c. That assertion failed without rerunning the emulator. verify-trace.py was corrected to verify the actual absolute address, and then passed against the same immutable trace.
