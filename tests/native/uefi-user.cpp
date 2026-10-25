// UEFI user-run, run-authority, IPC and console-context models (one-page image policy).
#include "../kernel-uefi-user-run.cpp"
#include "../kernel-program-run-authority.cpp"
#include "../kernel-ipc.cpp"
#include "../kernel-uefi-console-context.cpp"
#include "driver.hpp"

auto main(int argc, char **argv) -> int {
    return native_driver::run(argc, argv, {
        {"kernel-uefi-user-run", kernel_uefi_user_run::main},
        {"kernel-program-run-authority", kernel_program_run_authority::main},
        {"kernel-ipc", kernel_ipc::main},
        {"kernel-uefi-console-context", kernel_uefi_console_context::main},
    });
}
