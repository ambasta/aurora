# Read-only trace capability findings

No VM has been booted by this fixture builder. This is trace preparation, not runtime evidence.

Installed binary: /tmp/aurora-qemu/root/usr/bin/qemu-system-x86_64, reports QEMU 10.0.13 (Debian 1:10.0.13+ds-0+deb13u1). It needs LD_LIBRARY_PATH=/tmp/aurora-qemu/root/usr/lib/x86_64-linux-gnu and firmware search directory -L /tmp/aurora-qemu/firmware.

The installed binary's `-trace help` output is saved as qemu-trace-events.txt. trace-enable-events.txt includes 218 events: pci_cfg_read/write, every pci_nvme_* event supported by this binary, msix_write_config, and memory_region_ops_write. Enable it on the initial QEMU invocation with `-trace events=/tmp/aurora-clean-ovmf/provenance/trace-enable-events.txt,file=RUN_TRACE_PATH`; do not attach tracing after firmware execution starts. Capture OVMF DEBUG markers with `-debugcon file:RUN_DEBUG_PATH -global isa-debugcon.iobase=0x402`.

Official QEMU v10.0.13 reference files were fetched from https://raw.githubusercontent.com/qemu/qemu/v10.0.13/ and retained in the original local audit. The five complete C references are omitted from this source distribution; see SOURCE-DISTRIBUTION-OMISSIONS.json for exact hashes, source URLs and retained-original locations. These reference files explain event coverage; they are not a claim to contain every downstream Debian patch. Direct binary event enumeration confirms names are present.

- hw/pci/pci_host.c: pci_host_config_write_common emits pci_cfg_write before dispatch; pci_host_config_read_common emits pci_cfg_read after dispatch. Legacy config accesses use these helpers.
- hw/pci/pcie_host.c: ECAM accesses use the same pci_host_config_*_common helpers.
- hw/nvme/ctrl.c: pci_nvme_mmio_write is emitted at controller MMIO write entry. Specific events cover CC, AQA, ASQ, ACQ, doorbells, start/stop, resets, queue operations, and DMA read helpers.
- hw/pci/msix.c: MSI-X table memory region is named msix-table; PBA region is msix-pba. Table writes are not covered by pci_nvme_mmio_write. generic memory_region_ops_write includes region name, address, value and width. The binary format string was inspected directly. msix_write_config also reports enable/mask changes.

Limits: pci_nvme_dma_read is not a universal DMA tracer. For example, NVMe completion posting directly calls pci_dma_write without a matching universal DMA trace event. Absence of that one event cannot prove absence of all DMA. The intended argument uses cold reset, namespace-free exact topology, no controller MMIO initialization/queue/doorbell/MSI-X writes from reset, no controller-start events, the firmware's mandatory exact-endpoint marker, and the unchanged kernel's final inactive-state checks. Complete trace and identity must be retained. A separate positive coverage control is required by the reviewer; it must never be described as the accepted untouched-controller boot.

Generic PCI enumeration may temporarily set PCI Command.BME during capability probing and restore it. Never claim BME was never transiently set. Required handoff state is MSE=1/BME=0 with no NVMe controller or queue initialization.
