// BAR, IVRS and NVMe queue API models (NDEBUG builds).
#include "../kernel-uefi-bar.cpp"
#include "../kernel-uefi-bar-record.cpp"
#include "../kernel-uefi-ivrs.cpp"
#include "../kernel-nvme-queues-api.cpp"
#include "driver.hpp"

auto main(int argc, char **argv) -> int {
    return native_driver::run(argc, argv, {
        {"kernel-uefi-bar", kernel_uefi_bar::main},
        {"kernel-uefi-bar-record", kernel_uefi_bar_record::main},
        {"kernel-uefi-ivrs", kernel_uefi_ivrs::main},
        {"kernel-nvme-queues-api", kernel_nvme_queues_api::main},
    });
}
