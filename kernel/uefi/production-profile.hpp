#pragma once
// The production UEFI image ships only running mechanisms: no boot selector,
// injected fault, conformance capture or diagnostic probe is compiled into its
// loader or payload. Test images keep those cases (see runtime-fixtures.inc).
#ifdef AURORA_PRODUCTION
#if defined(AURORA_PLATFORM_FIXTURE) || defined(AURORA_RUNTIME_FIXTURE) || defined(AURORA_RUNTIME_CONTROL_FIXTURE) ||  \
                                                                                                                       \
    defined(AURORA_IPC_FIXTURE) || defined(AURORA_BUDGET_FIXTURE) || defined(AURORA_DISPATCH_FIXTURE) ||               \
    defined(AURORA_USER_FIXTURE) || defined(AURORA_PROGRAM_FIXTURE) || defined(AURORA_SNAPSHOT_FIXTURE) ||             \
    defined(AURORA_PIN_FIXTURE) || defined(AURORA_TABLE_FIXTURE) || defined(AURORA_SCRATCHPAD_FIXTURE) ||              \
    defined(AURORA_CONSOLE_SERVICE_FIXTURE) || defined(AURORA_UEFI_GRAPHICAL_FIXTURE) ||                               \
    defined(AURORA_UEFI_GRAPHICAL_CAPTURE) || defined(AURORA_UEFI_FRAMEBUFFER_FIXTURE) ||                              \
    defined(AURORA_UEFI_FRAMEBUFFER_CAPTURE) || defined(AURORA_UEFI_BAR_CAPTURE) ||                                    \
    defined(AURORA_UEFI_NVME_PREPARE) || defined(AURORA_UEFI_IVRS) || defined(AURORA_UEFI_IOMMU_EVENT) ||              \
    defined(AURORA_DORMANT_TABLE_TESTING) || defined(AURORA_PIN_LEDGER_TESTING) ||                                     \
    defined(AURORA_KERNEL_BYTES_TESTING) || defined(AURORA_NVME_QUEUE_TESTING) ||                                      \
    defined(AURORA_NVME_QUEUE_GENERATION_LIMIT) || defined(AURORA_RUNTIME_IMAGE_BANK) ||                               \
    defined(AURORA_RUNTIME_MULTIPAGE)
#error "The production image rejects fixture selectors, test hooks and capture handshakes"
#endif
#if !defined(AURORA_UEFI_RUNTIME) || !defined(AURORA_UEFI_PROGRAM_CONSOLE) || !defined(AURORA_UEFI_GRAPHICAL_TERMINAL)
#error "The production image carries the protected runtime, the program console and its graphical terminal"
#endif
#endif
