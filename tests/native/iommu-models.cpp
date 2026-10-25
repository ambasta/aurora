// Dormant IOMMU tables, decoder and AMD IOMMU reference models.
#include "../kernel-dormant-tables.cpp"
#include "../kernel-dormant-decoder.cpp"
#include "../kernel-iommu-oracle.cpp"
#include "../kernel-iommu-event-completion.cpp"
#include "driver.hpp"

auto main(int argc, char **argv) -> int {
    return native_driver::run(argc, argv, {
        {"kernel-dormant-tables", kernel_dormant_tables::main},
        {"kernel-dormant-decoder", kernel_dormant_decoder::main},
        {"kernel-iommu-oracle", kernel_iommu_oracle::main},
        {"kernel-iommu-event-completion", kernel_iommu_event_completion::main},
    });
}
