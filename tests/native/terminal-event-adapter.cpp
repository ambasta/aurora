// The terminal-event observer against a hostile substituted producer.
#include "../kernel-terminal-event-native.cpp"
#include "driver.hpp"

auto main(int argc, char **argv) -> int {
    return native_driver::run(argc,
                              argv,
                              {
                                  {"kernel-terminal-event-native", kernel_terminal_event_native::main},
                              });
}
