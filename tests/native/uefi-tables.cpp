// UEFI runtime layout, page-table and service-budget models (one-page image policy).
#include "../kernel-uefi-runtime.cpp"
#include "../kernel-uefi-dispatch-layout.cpp"
#include "../kernel-uefi-service-budget.cpp"
#include "../kernel-uefi-handoff.cpp"
#include "driver.hpp"

auto main(int argc, char **argv) -> int {
    return native_driver::run(argc, argv, {
        {"kernel-uefi-runtime", kernel_uefi_runtime::main},
        {"kernel-uefi-dispatch-layout", kernel_uefi_dispatch_layout::main},
        {"kernel-uefi-service-budget", kernel_uefi_service_budget::main},
        {"kernel-uefi-handoff", kernel_uefi_handoff::main},
    });
}
