// The runtime and user-run models again under the multipage image policy.
#include "../kernel-uefi-runtime.cpp"
#include "../kernel-uefi-user-run.cpp"
#include "driver.hpp"

auto main(int argc, char **argv) -> int {
    return native_driver::run(argc, argv, {
        {"kernel-uefi-runtime", kernel_uefi_runtime::main},
        {"kernel-uefi-user-run", kernel_uefi_user_run::main},
    });
}
