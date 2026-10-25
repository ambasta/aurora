// Dispatch models and policy observers linked with the real UEFI policy object.
#include "../kernel-dispatch.cpp"
#include "../kernel-client-disposal.cpp"
#include "../kernel-budget-native.cpp"
#include "../kernel-round-robin-native.cpp"
#include "../kernel-ipc-transition-native.cpp"
#include "../kernel-client-disposal-native.cpp"
#include "../kernel-terminal-event-native.cpp"
#include "driver.hpp"

auto main(int argc, char **argv) -> int {
    return native_driver::run(argc,
                              argv,
                              {
                                  {"kernel-dispatch", kernel_dispatch::main},
                                  {"kernel-client-disposal", kernel_client_disposal::main},
                                  {"kernel-budget-native", kernel_budget_native::main},
                                  {"kernel-round-robin-native", kernel_round_robin_native::main},
                                  {"kernel-ipc-transition-native", kernel_ipc_transition_native::main},
                                  {"kernel-client-disposal-native", kernel_client_disposal_native::main},
                                  {"kernel-terminal-event-native", kernel_terminal_event_native::main},
                              });
}
