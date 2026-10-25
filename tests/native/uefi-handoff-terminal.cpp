// The handoff layout tables for the graphical-terminal (v7) header.
#include "../kernel-uefi-handoff.cpp"
#include "driver.hpp"

auto main(int argc, char **argv) -> int {
    return native_driver::run(argc, argv, {
        {"kernel-uefi-handoff", kernel_uefi_handoff::main},
    });
}
