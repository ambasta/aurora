#pragma once
// Dedicated source-only profile. The same rejection boundary applies to the
// firmware loader, payload dispatch and combined service implementation.
// No legacy profile or negative selector is a qualification of this graph.
#ifdef AURORA_UEFI_GRAPHICAL_CONSOLE
#if !defined(AURORA_UEFI_ACPI) || !defined(AURORA_UEFI_GRAPHICAL_FIXTURE)
#error "Graphical Console requires its dedicated ACPI/fixture profile"
#endif
#if defined(AURORA_IVRS_FIXTURE) || defined(AURORA_IPC_FIXTURE) || defined(AURORA_BUDGET_FIXTURE) ||                   \
    defined(AURORA_DISPATCH_FIXTURE) || defined(AURORA_USER_FIXTURE) || defined(AURORA_ACPI_FIXTURE) ||                \
    defined(AURORA_EARLY_FIXTURE) || defined(AURORA_CONSOLE_SERVICE_FIXTURE) ||                                        \
    defined(AURORA_DORMANT_TABLE_TESTING) || defined(AURORA_KERNEL_BYTES_TESTING) ||                                   \
    defined(AURORA_NVME_QUEUE_GENERATION_LIMIT) || defined(AURORA_NVME_QUEUE_TESTING) ||                               \
    defined(AURORA_PCI_FIXTURE) || defined(AURORA_RUNTIME_CONTROL_FIXTURE) || defined(AURORA_PIN_FIXTURE) ||           \
    defined(AURORA_TABLE_FIXTURE) || defined(AURORA_PROGRAM_FIXTURE) || defined(AURORA_SNAPSHOT_FIXTURE) ||            \
    defined(AURORA_UEFI_BAR_ADMISSION) || defined(AURORA_UEFI_BAR_CAPTURE) || defined(AURORA_UEFI_BAR_EDK2) ||         \
    defined(AURORA_UEFI_CONSOLE) || defined(AURORA_UEFI_DISPATCH) || defined(AURORA_UEFI_FRAMEBUFFER) ||               \
    defined(AURORA_UEFI_FRAMEBUFFER_CAPTURE) || defined(AURORA_UEFI_FRAMEBUFFER_FIXTURE) ||                            \
    defined(AURORA_UEFI_FRAMEBUFFER_PROBE) || defined(AURORA_UEFI_IPC) || defined(AURORA_UEFI_IVRS) ||                 \
    defined(AURORA_UEFI_NVME_PREPARE) || defined(AURORA_UEFI_OWNED_BYTES) || defined(AURORA_UEFI_PCI) ||               \
    defined(AURORA_UEFI_PINS) || defined(AURORA_UEFI_PROGRAM_CONSOLE) || defined(AURORA_UEFI_RUNTIME) ||               \
    defined(AURORA_UEFI_SERVICE_BUDGET) || defined(AURORA_UEFI_TABLES) || defined(AURORA_UEFI_USER_BUDGET)
#error "Graphical Console rejects legacy profile and fault selectors"
#endif
#elif defined(AURORA_UEFI_GRAPHICAL_FIXTURE) || defined(AURORA_UEFI_GRAPHICAL_CAPTURE)
#error "Graphical fixture/capture requires the dedicated graphical Console profile"
#endif
