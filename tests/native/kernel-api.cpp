// Public dormant-table and pin-ledger APIs without their testing hooks.
#include "../kernel-dormant-api.cpp"
#include "../kernel-pin-api.cpp"
#include "driver.hpp"

auto main(int argc, char **argv) -> int {
    return native_driver::run(argc, argv, {
        {"kernel-dormant-api", kernel_dormant_api::main},
        {"kernel-pin-api", kernel_pin_api::main},
    });
}
