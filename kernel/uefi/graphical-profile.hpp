#pragma once
// Dedicated source-only profile. The same rejection boundary applies to the
// firmware loader, payload dispatch and combined service implementation.
// No legacy profile or negative selector is a qualification of this graph.
#ifdef AURORA_UEFI_GRAPHICAL_CONSOLE
#if !defined(AURORA_UEFI_ACPI) || !defined(AURORA_UEFI_GRAPHICAL_FIXTURE)
#error "Graphical Console requires its dedicated ACPI/fixture profile"
#endif
#if defined(AURORA_ACPI_BAD_ENTRY) || defined(AURORA_ACPI_BAD_SOURCE) || defined(AURORA_ACPI_CHANGED_HEADER) ||        \
    defined(AURORA_ACPI_CHECKSUM) || defined(AURORA_ACPI_DISABLED) || defined(AURORA_ACPI_DUPLICATE) ||                \
    defined(AURORA_ACPI_DUPLICATE_ROOT) || defined(AURORA_ACPI_REVOKED) || defined(AURORA_ACPI_WRITE) ||               \
    defined(AURORA_BUDGET_PENDING) || defined(AURORA_BUDGET_ROOT) || defined(AURORA_CONSOLE_SERVICE_REENTRY) ||        \
    defined(AURORA_CONSOLE_SERVICE_REPORT) || defined(AURORA_CONSOLE_SERVICE_STALE) ||                                 \
    defined(AURORA_CONSOLE_SERVICE_TIMEOUT) || defined(AURORA_DISPATCH_PENDING) || defined(AURORA_DISPATCH_ROOT) ||    \
    defined(AURORA_DORMANT_TABLE_TESTING) || defined(AURORA_FRAMEBUFFER_PERMISSIONS) ||                                \
    defined(AURORA_FRAMEBUFFER_RECORD) || defined(AURORA_FRAMEBUFFER_STALE) || defined(AURORA_IPC_ROOT) ||             \
    defined(AURORA_IVRS_ALIAS) || defined(AURORA_IVRS_PAIR) || defined(AURORA_IVRS_RESERVED) ||                        \
    defined(AURORA_IVRS_SCOPE) || defined(AURORA_KERNEL_BYTES_TESTING) ||                                              \
    defined(AURORA_NVME_QUEUE_GENERATION_LIMIT) || defined(AURORA_NVME_QUEUE_TESTING) ||                               \
    defined(AURORA_PCI_CHECKSUM) || defined(AURORA_PCI_CYCLE) || defined(AURORA_PCI_OVERLAP) ||                        \
    defined(AURORA_PCI_RANGE) || defined(AURORA_PCI_RESERVED) || defined(AURORA_PCI_REVOKED) ||                        \
    defined(AURORA_PCI_WRITE) || defined(AURORA_PIN_FAULT) || defined(AURORA_PROGRAM_PENDING) ||                       \
    defined(AURORA_RUNTIME_ENTRY_STACK) || defined(AURORA_RUNTIME_KERNEL_TRAP) || defined(AURORA_RUNTIME_ROOT) ||      \
    defined(AURORA_UEFI_BAD_HANDOFF) || defined(AURORA_UEFI_BAD_MAP) || defined(AURORA_UEFI_BAD_TABLE) ||              \
    defined(AURORA_UEFI_BAR_ADMISSION) || defined(AURORA_UEFI_BAR_CAPTURE) || defined(AURORA_UEFI_BAR_EDK2) ||         \
    defined(AURORA_UEFI_CONSOLE) || defined(AURORA_UEFI_DISPATCH) || defined(AURORA_UEFI_EXHAUSTED) ||                 \
    defined(AURORA_UEFI_FRAMEBUFFER) || defined(AURORA_UEFI_FRAMEBUFFER_CAPTURE) ||                                    \
    defined(AURORA_UEFI_FRAMEBUFFER_FIXTURE) || defined(AURORA_UEFI_FRAMEBUFFER_PROBE) || defined(AURORA_UEFI_IPC) ||  \
    defined(AURORA_UEFI_IVRS) || defined(AURORA_UEFI_NVME_PREPARE) || defined(AURORA_UEFI_NX) ||                       \
    defined(AURORA_UEFI_OWNED_BYTES) || defined(AURORA_UEFI_PCI) || defined(AURORA_UEFI_PINS) ||                       \
    defined(AURORA_UEFI_PROGRAM_CONSOLE) || defined(AURORA_UEFI_RUNTIME) || defined(AURORA_UEFI_SERVICE_BUDGET) ||     \
    defined(AURORA_UEFI_STALE) || defined(AURORA_UEFI_TABLES) || defined(AURORA_UEFI_USER_BUDGET) ||                   \
    defined(AURORA_UEFI_WP) || defined(AURORA_USER_PENDING) || defined(AURORA_USER_RETIRE_PENDING) ||                  \
    defined(AURORA_USER_ROOT)
#error "Graphical Console rejects legacy profile and fault selectors"
#endif
#elif defined(AURORA_UEFI_GRAPHICAL_FIXTURE) || defined(AURORA_UEFI_GRAPHICAL_CAPTURE)
#error "Graphical fixture/capture requires the dedicated graphical Console profile"
#endif
