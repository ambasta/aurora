// UEFI handoff, ACPI and PCI policy models.
#include "../kernel-uefi.cpp"
#include "../kernel-acpi.cpp"
#include "../kernel-pci.cpp"
#include "driver.hpp"

auto main(int argc, char **argv) -> int {
    return native_driver::run(argc,
                              argv,
                              {
                                  {"kernel-uefi", kernel_uefi::main},
                                  {"kernel-acpi", kernel_acpi::main},
                                  {"kernel-pci", kernel_pci::main},
                              });
}
