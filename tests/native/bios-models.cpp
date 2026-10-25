// Kernel memory, domain and program lifecycle models linked with the BIOS policy object;
// the lifecycle cases also link with the UEFI policy object.
#include "../kernel-pages.cpp"
#include "../kernel-protection.cpp"
#include "../kernel-program.cpp"
#include "../kernel-program-layout.cpp"
#include "../kernel-domain.cpp"
#include "../kernel-schedule.cpp"
#include "driver.hpp"

auto main(int argc, char **argv) -> int {
    return native_driver::run(argc,
                              argv,
                              {
                                  {"kernel-pages", kernel_pages::main},
                                  {"kernel-protection", kernel_protection::main},
                                  {"kernel-program", kernel_program::main},
                                  {"kernel-program-layout", kernel_program_layout::main},
                                  {"kernel-domain", kernel_domain::main},
                                  {"kernel-schedule", kernel_schedule::main},
                              });
}
