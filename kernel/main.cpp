// Temporary trusted hardware bootstrap, not the Aurora language or its safety model.
// No C runtime, heap allocation, or object ABI export.
// Standard-library views/arrays are compile-time-only bootstrap conveniences.
#include <array>
#include <string_view>
#include "pages.hpp"
#include "interrupts.hpp"
#include "protection.hpp"
#include "firmware-memory.hpp"
#include "user-program.hpp"
#include "address-spaces.hpp"
auto user_program(std::uint64_t entry) -> std::uint64_t asm("aurora_user_program");
#include "console.hpp"
#include "scheduler.hpp"
#include "bios-fixture.hpp"
#ifdef AURORA_INTERACTIVE_CONSOLE
#include "interactive-console.hpp"
#endif

namespace {
constinit aurora::memory::PhysicalPages pages;
constinit aurora::memory::PhysicalPages foreign_pages;
constinit std::array<std::optional<aurora::memory::PageLease>, aurora::memory::PhysicalPages::capacity> leases{};
#ifdef AURORA_BIOS_FIXTURE
alignas(4096) constinit std::array<std::uint8_t, 4096> nx_probe{};
#endif
constinit aurora::user::ProgramRun program_run;
constinit std::size_t program_index = 0;
constinit std::array<aurora::user::DomainHandle, 3> domains{};
volatile bool user_expected = false;
volatile unsigned user_returns = 0;
volatile bool breakpoint_expected = false;
volatile unsigned breakpoint_count = 0;
[[noreturn]] auto fail(std::string_view message) -> void {
    aurora::hardware::Serial::text(message);
    aurora::hardware::Serial::text("\r\nAURORA_BOOT_FAIL\r\n");
    aurora::hardware::Io::write(0xf4, 0x11);
    for (;;)
        asm volatile("cli; hlt");
}
auto require(bool condition, std::string_view message) -> void {
    if (!condition)
        fail(message);
}
auto program_fault_kind(aurora::user::ProgramEvent event) -> std::string_view {
    using aurora::user::ProgramEvent;
    switch (event) {
    case ProgramEvent::bounds:
        return "bounds";
    case ProgramEvent::overflow:
        return "overflow";
    case ProgramEvent::division_zero:
        return "division_zero";
    case ProgramEvent::shift_count:
        return "shift_count";
    case ProgramEvent::rejected:
    case ProgramEvent::returned:
        fail("Non-fault event has no fault kind");
    }
    fail("Invalid fault event");
}
// Trusted physical-memory transport: E820 bytes and page mappings only.
auto physical_read(std::uint64_t address, unsigned bytes) -> std::uint64_t {
    auto result = std::uint64_t{0};
    for (auto index = 0U; index < bytes; ++index)
        result |= static_cast<std::uint64_t>(*reinterpret_cast<volatile const std::uint8_t *>(address + index))
                  << (index * 8);
    return result;
}
auto arena_is_usable(std::uint64_t start, std::uint64_t end) -> bool {
    const auto bytes = std::span{reinterpret_cast<const std::byte *>(0x5000), std::size_t{8 + 32 * 24}};
    return aurora::memory::FirmwareMemory::grants(bytes, start, end);
}
auto page_self_test() -> void {
    constexpr auto base = std::uint64_t{0x100000};
    constexpr auto count = aurora::memory::PhysicalPages::capacity;
    constexpr auto page_size = aurora::memory::PhysicalPages::page_size;
    require(arena_is_usable(base, base + count * page_size), "Firmware does not grant bootstrap page arena");
    aurora::hardware::Serial::text("AURORA_E820_OK\r\n");
    require(!pages.initialize(base + 1, count), "Unaligned arena accepted");
    require(!pages.initialize(base, 0), "Empty arena accepted");
    require(!pages.initialize(base, count + 1), "Oversized arena accepted");
    require(pages.initialize(base, count), "Page allocator initialization failed");
    require(!pages.initialize(base, count), "Live arena reinitialization accepted");
    require(foreign_pages.initialize(0x180000, 1), "Foreign allocator initialization failed");
    for (std::size_t index = 0; index < count; ++index) {
        auto page = pages.acquire();
        require(page.has_value(), "Allocation failed before exhaustion");
        const auto address = pages.address(*page);
        require(address.has_value() && *address == base + index * page_size, "Invalid or duplicate frame address");
        leases[index].emplace(std::move(*page));
        require(!page->valid(), "Move left an owning alias");
        // Touch every allocated byte through the architecture boundary.
        for (std::uint64_t byte = 0; byte < page_size; ++byte)
            *reinterpret_cast<volatile std::uint8_t *>(*address + byte) = static_cast<std::uint8_t>(index);
    }
    require(pages.used() == count && !pages.acquire(), "Exhaustion accounting failed");
    for (std::size_t index = 0; index < count; ++index) {
        const auto address = pages.address(*leases[index]);
        require(address.has_value() && physical_read(*address, 1) == index &&
                    physical_read(*address + page_size - 1, 1) == index,
                "Allocated physical pages alias or are inaccessible");
    }
    require(!foreign_pages.release(*leases[0]), "Foreign ownership accepted");
    require(pages.release(*leases[0]), "First release failed");
    require(!pages.release(*leases[0]) && !pages.address(*leases[0]), "Double release or retired lease accepted");
    auto recycled = pages.acquire();
    require(recycled.has_value() && pages.address(*recycled) == base, "Released frame not reused");
    require(!pages.release(*leases[0]), "Retired lease released recycled frame");
    auto moved = std::move(*recycled);
    require(!pages.release(*recycled) && pages.release(moved), "Moved ownership was not enforced");
    for (std::size_t index = 1; index < count; ++index)
        require(pages.release(*leases[index]), "Page release failed");
    require(pages.used() == 0, "Page leak after self-test");
    aurora::hardware::Serial::text("AURORA_PAGES_OK: 128 frames, exhaustion, reuse, ownership, double-free\r\n");
}
auto execute_program(std::size_t index, aurora::user::ProgramEvent expected) -> void {
    using aurora::hardware::Serial;
    using aurora::user::ProgramEvent;
    using aurora::user::UserPrograms;
    const auto *contract = UserPrograms::contract(index);
    require(contract != nullptr && !user_expected && !program_run.running(), "Invalid or nested user program run");
    require(aurora::user::AddressSpaces::scrub(domains[index]), "Private user stack reset failed");
    require(program_run.begin(*contract), "Program contract rejected");
    program_index = index;
    require(aurora::user::AddressSpaces::activate(domains[index]), "Domain activation failed");
    require(!aurora::user::AddressSpaces::destroy(domains[index]), "Active domain teardown accepted");
    Serial::text("AURORA_DOMAIN_ENTER: image=");
    Serial::number(index);
    Serial::text(" root=");
    Serial::number(aurora::hardware::Protection::current_root());
    Serial::text("\r\n");
    Serial::text("AURORA_PROGRAM_ENTER: image=");
    Serial::number(index);
    Serial::text("\r\n");
#ifdef AURORA_BIOS_FIXTURE
    if (aurora::bios::selected(aurora::bios::Fixture::bios_program_kernel_trap)) {
        asm volatile("jmp *%0" : : "r"(contract->bounds_pc()) : "memory");
        fail("Kernel UD2 unexpectedly returned");
    }
#endif
#ifdef AURORA_BIOS_FIXTURE
    if (aurora::bios::selected(aurora::bios::Fixture::bios_division_kernel_trap)) {
        require(contract->division_zero_pc() != 0, "Missing division trap authority");
        asm volatile("jmp *%0" : : "r"(contract->division_zero_pc()) : "memory");
        fail("Kernel division UD2 unexpectedly returned");
    }
#endif
#ifdef AURORA_BIOS_FIXTURE
    if (aurora::bios::selected(aurora::bios::Fixture::bios_unsigned_kernel_trap)) {
        require(contract->shift_count_pc() != 0, "Missing shift-count trap authority");
        asm volatile("jmp *%0" : : "r"(contract->shift_count_pc()) : "memory");
        fail("Kernel shift-count UD2 unexpectedly returned");
    }
#endif
    const auto resumed = user_program(contract->entry());
    require(aurora::user::AddressSpaces::deactivate(domains[index]), "Kernel root restoration failed");
    Serial::text("AURORA_DOMAIN_RESTORED: root=");
    Serial::number(aurora::hardware::Protection::current_root());
    Serial::text("\r\n");
    require(resumed == 1 && !program_run.running() && program_run.event() == expected,
            "Program did not finish with the required typed outcome");
    require(aurora::hardware::Protection::verify(), "Program altered protected mapping state");
    if (expected == ProgramEvent::returned) {
        require(program_run.value() == 42, "Compiled user program returned wrong result");
        Serial::text("AURORA_PROGRAM_RETURN: image=");
        Serial::number(index);
        Serial::text(" value=");
        Serial::number(program_run.value());
        Serial::text("\r\n");
    } else {
        Serial::text("AURORA_PROGRAM_CONTAINED: image=");
        Serial::number(index);
        Serial::text(" kind=");
        Serial::text(program_fault_kind(expected));
        Serial::text("\r\n");
    }
}
[[maybe_unused]] auto compiled_program_self_test() -> void {
    using aurora::hardware::Protection;
    using aurora::hardware::Serial;
    using aurora::user::AddressSpaces;
    using aurora::user::ProgramEvent;
#ifdef AURORA_BIOS_FIXTURE
    if (aurora::bios::selected(aurora::bios::Fixture::bios_division_kernel_trap))
        Serial::text("AURORA_DIVISION_FIXTURE: kernel-trap\r\n");
#endif
#ifdef AURORA_BIOS_FIXTURE
    if (!aurora::bios::division().empty()) {
        Serial::text("AURORA_DIVISION_FIXTURE: ");
        Serial::text(aurora::bios::division());
        Serial::text("\r\n");
    }
    if (!aurora::bios::unsigned_case().empty()) {
        Serial::text("AURORA_UNSIGNED_FIXTURE: ");
        Serial::text(aurora::bios::unsigned_case());
        Serial::text("\r\n");
    }
#endif
    require(!AddressSpaces::initialize(foreign_pages), "Out-of-arena allocator accepted by domain manager");
    require(AddressSpaces::initialize(pages), "Domain manager initialization failed");
    std::array<std::uint64_t, 3> roots{};
    for (std::size_t index = 0; index < domains.size(); ++index) {
        auto domain = AddressSpaces::create(index);
        require(domain.has_value(), "Domain creation failed");
        domains[index] = *domain;
        roots[index] = *AddressSpaces::root(*domain);
        require(AddressSpaces::stack_zero(*domain), "New private stack not zero");
        for (std::size_t prior = 0; prior < index; ++prior)
            require(roots[index] != roots[prior], "Domains share a page-table root");
    }
    require(pages.used() == 12 && !AddressSpaces::create(0), "Domain ownership/resource bound failed");
    require(!AddressSpaces::activate(aurora::user::DomainHandle{}), "Invalid domain handle accepted");
    Serial::text("AURORA_DOMAINS_READY: kernel=");
    Serial::number(Protection::kernel_root());
    for (std::size_t index = 0; index < domains.size(); ++index) {
        Serial::text(" root");
        Serial::number(index);
        Serial::text("=");
        Serial::number(roots[index]);
        Serial::text(" frame");
        Serial::number(index);
        Serial::text("=");
        Serial::number(*AddressSpaces::stack_frame(domains[index], 0));
    }
    Serial::text("\r\n");
    require(AddressSpaces::stack_frame(domains[1], 0) == 0x104000,
            "Cross-domain test address does not name second owner's frame");
    // Image 1 traps on bounds unless its program set replaces it with a
    // division-by-zero or shift-count program.
    auto second = ProgramEvent::bounds;
#ifdef AURORA_BIOS_FIXTURE
    using aurora::bios::Fixture;
    if (aurora::bios::selected(Fixture::bios_division_zero) ||
        aurora::bios::selected(Fixture::bios_division_remainder_zero))
        second = ProgramEvent::division_zero;
    else if (aurora::bios::selected(Fixture::bios_unsigned_shift_count))
        second = ProgramEvent::shift_count;
#endif
    execute_program(0, ProgramEvent::returned);
    execute_program(1, second);
    execute_program(0, ProgramEvent::returned);
    execute_program(2, ProgramEvent::overflow);
    execute_program(0, ProgramEvent::returned);
    for (const auto domain : domains)
        require(!AddressSpaces::stack_zero(domain), "Compiled program did not use its own leased stack memory");
    const auto stale = domains[0];
    std::array<std::uint64_t, 4> released_frames{};
    for (std::size_t page = 0; page < 4; ++page)
        released_frames[page] = *AddressSpaces::stack_frame(stale, page);
    require(AddressSpaces::destroy(stale) && pages.used() == 8, "Inactive domain teardown failed");
    for (const auto frame : released_frames)
        for (std::uint64_t byte = 0; byte < 4096; byte += 8)
            require(physical_read(frame + byte, 8) == 0, "Released frame still contains user bytes");
    require(!AddressSpaces::activate(stale) && !AddressSpaces::destroy(stale) && !AddressSpaces::scrub(stale),
            "Destroyed domain authority retained");
    // Leave only two free frames: creation must roll back a partial four-frame stack.
    for (std::size_t index = 0; index < 118; ++index) {
        auto page = pages.acquire();
        require(page.has_value(), "Rollback test setup failed");
        leases[index].emplace(std::move(*page));
    }
    require(physical_read(0x17e000, 1) == 126 && physical_read(0x17f000, 1) == 127,
            "Rollback fixture lost recognizable prior bytes");
    require(pages.used() == 126 && !AddressSpaces::create(0) && pages.used() == 126,
            "Partial domain creation leaked frames");
    for (std::uint64_t address = 0x17e000; address < 0x180000; address += 8)
        require(physical_read(address, 8) == 0, "Rollback released unsanitized frame bytes");
    for (std::size_t index = 0; index < 118; ++index)
        require(pages.release(*leases[index]), "Rollback test cleanup failed");
    auto replacement = AddressSpaces::create(0);
    require(replacement.has_value(), "Domain slot reuse failed");
    domains[0] = *replacement;
    require(AddressSpaces::stack_frame(domains[0], 0) == released_frames[0] && AddressSpaces::stack_zero(domains[0]),
            "Physical frame reuse was not sanitized");
    require(!AddressSpaces::activate(stale) && !AddressSpaces::destroy(stale),
            "Stale handle resurrected after slot reuse");
    Serial::text("AURORA_DOMAIN_REUSE_OK: stale denied, released bytes zero, partial rollback, same frames\r\n");
    execute_program(0, ProgramEvent::returned);
    for (const auto domain : domains)
        require(AddressSpaces::destroy(domain), "Final domain teardown failed");
    require(pages.used() == 0 && Protection::verify(), "Domain teardown leaked memory or active root");
    Serial::text("AURORA_DOMAINS_OK: private CR3, private stacks, zero reuse, clean teardown\r\n");
    Serial::text("AURORA_COMPILED_USER_OK: arrays, loop, ");
    Serial::text(program_fault_kind(second));
    Serial::text(", overflow, clean restart\r\n");
#ifdef AURORA_BIOS_FIXTURE
    if (!aurora::bios::division().empty())
        Serial::text("AURORA_DIVISION_OK: exact typed trap, clean restart, private teardown\r\n");
    if (!aurora::bios::unsigned_case().empty())
        Serial::text("AURORA_UNSIGNED_OK: full-width values, exact typed trap, clean restart, private teardown\r\n");
#endif
}
} // namespace
auto exception_dispatch(std::uint64_t vector,
                        std::uint64_t error,
                        std::uint64_t instruction,
                        std::uint64_t code,
                        std::uint64_t frame,
                        std::uint64_t user_value) -> std::uint64_t asm("aurora_exception_dispatch");
auto exception_dispatch(std::uint64_t vector,
                        std::uint64_t error,
                        std::uint64_t instruction,
                        std::uint64_t code,
                        std::uint64_t frame,
                        std::uint64_t user_value) -> std::uint64_t {
#ifdef AURORA_INTERACTIVE_CONSOLE
    // A trap inside the source/transport boundary cannot safely reenter it or
    // consume destructive LSR through the bootstrap diagnostic UART reader.
    if (aurora::console::Interactive::owns_uart())
        aurora::console::Interactive::fail();
#endif
    using aurora::hardware::Protection;
    const auto cpl = code & 3;
    if (vector == 3 && breakpoint_expected && cpl == 0) {
        breakpoint_count = breakpoint_count + 1;
        return 0;
    }
    const auto on_entry_stack = frame >= Protection::entry_stack_bottom && frame < Protection::entry_stack_top;
    if (vector == 128 && user_expected && cpl == 3 && on_entry_stack && user_value == 42 &&
        instruction >= Protection::user_code && instruction < Protection::user_code + 4096) {
        user_returns = user_returns + 1;
        return 1; // Dedicated assembly continuation restores only the saved privileged stack.
    }
    using aurora::hardware::Serial;
    const auto scheduled = aurora::user::Scheduler::interrupt(vector, code, instruction, frame);
    if (scheduled >= 0)
        return static_cast<std::uint64_t>(scheduled);
#ifdef AURORA_BIOS_FIXTURE
    if (aurora::bios::selected(aurora::bios::Fixture::bios_domain_root_mismatch)) {
        if (program_run.running() && code == 0x1b) {
            const auto root = Protection::kernel_root();
            asm volatile("mov %0, %%cr3" : : "r"(root) : "memory");
            Serial::text("AURORA_DOMAIN_ROOT_MISMATCH_INJECTED\r\n");
        }
    }
#endif
    if (program_run.running() && program_index < domains.size() &&
        aurora::user::AddressSpaces::active(domains[program_index]) && code == 0x1b &&
        frame >= Protection::entry_stack_bottom && frame <= Protection::entry_stack_top - 176 && frame % 8 == 0) {
        const auto flags = physical_read(frame + 152, 8);
        const auto stack = physical_read(frame + 160, 8);
        const auto ss = physical_read(frame + 168, 8);
        const auto context = aurora::user::ProgramContext{vector, error, instruction, code, ss, stack, flags, frame};
        if (program_run.accept(context, user_value)) {
            Serial::text("AURORA_DOMAIN_EVENT: image=");
            Serial::number(program_index);
            Serial::text(" root=");
            Serial::number(Protection::current_root());
            Serial::text("\r\n");
            if (program_run.event() != aurora::user::ProgramEvent::returned) {
                Serial::text("AURORA_PROGRAM_FAULT: image=");
                Serial::number(program_index);
                Serial::text(" kind=");
                Serial::text(program_fault_kind(program_run.event()));
                Serial::text(" vector=");
                Serial::number(vector);
                if (program_run.event() == aurora::user::ProgramEvent::division_zero ||
                    program_run.event() == aurora::user::ProgramEvent::shift_count) {
                    Serial::text(" error=");
                    Serial::number(error);
                }
                Serial::text(" rip=");
                Serial::number(instruction);
                Serial::text(" cpl=3 frame=");
                Serial::number(frame);
                Serial::text("\r\n");
            }
            return 1;
        }
    }
    if (program_run.running()) {
        Serial::text("AURORA_DOMAIN_FAULT_ROOT: root=");
        Serial::number(Protection::current_root());
        Serial::text("\r\n");
    }
    Serial::text("AURORA_EXCEPTION_FATAL: ");
    Serial::number(vector);
    Serial::text(" error=");
    Serial::number(error);
    Serial::text(" rip=");
    Serial::number(instruction);
    Serial::text("\r\n");
    std::uint64_t cr2;
    asm volatile("mov %%cr2, %0" : "=r"(cr2));
    Serial::text("AURORA_EXCEPTION_CONTEXT: cpl=");
    Serial::number(cpl);
    Serial::text(" frame=");
    Serial::number(frame);
    Serial::text(" cr2=");
    Serial::number(cr2);
    Serial::text("\r\n");
    if (cpl == 3 && on_entry_stack)
        Serial::text("AURORA_TSS_ENTRY_OK\r\n");
    if (vector == 8 && frame >= Protection::emergency_stack_bottom && frame < Protection::emergency_stack_top)
        Serial::text("AURORA_IST_OK\r\n");
    fail("Exception halted safely");
}
// Deliberately narrow temporary assembly symbols, not a supported C source/ABI contract.
extern const std::byte protected_image_end asm("__write_end");
auto language_value() -> long long asm("aurora_kernel_value");
auto user_probe(unsigned long long mode) -> unsigned long long asm("aurora_user_probe");
auto breakpoint_probe() -> unsigned long long asm("aurora_breakpoint_probe");
auto kernel_main() -> void asm("aurora_kernel_main");
auto kernel_main() -> void {
    using aurora::hardware::Serial;
    Serial::initialize();
    Serial::text("Aurora bootstrap: x86-64 long mode\r\n");
    aurora::hardware::Interrupts::initialize();
    using aurora::hardware::Protection;
    require(arena_is_usable(0x10000, reinterpret_cast<std::uint64_t>(&protected_image_end)) &&
                arena_is_usable(Protection::emergency_stack_bottom, Protection::main_stack_top) &&
                arena_is_usable(aurora::user::UserPrograms::code_begin, aurora::user::UserPrograms::code_end) &&
                arena_is_usable(Protection::user_code, Protection::user_code + 4096) &&
                arena_is_usable(Protection::user_stack_bottom, Protection::user_stack_top),
            "Firmware does not grant protected image, stacks or controlled user pages");
    require(Protection::activate(), "Required NX capability or protected mapping validation failed");
    Serial::text("AURORA_WX_OK: RX text, R-NX constants, RW-NX data, NXE, WP, guards\r\n");
    breakpoint_expected = true;
    const auto registers_preserved = breakpoint_probe();
    breakpoint_expected = false;
    require(breakpoint_count == 1 && registers_preserved == 1, "Breakpoint dispatch did not resume correctly");
    Serial::text("AURORA_EXCEPTION_OK: breakpoint, 15 GPRs, direction flag\r\n");
    page_self_test();
#ifdef AURORA_BIOS_FIXTURE
    const auto selected = aurora::bios::read_fixture(aurora::bios::first, aurora::bios::last);
    require(selected.has_value(), "fixture selector outside BIOS image family");
    aurora::bios::fixture = *selected;
    aurora::user::UserPrograms::select(static_cast<unsigned>(*selected));
#endif
#ifdef AURORA_BIOS_FIXTURE
    if (aurora::bios::selected(aurora::bios::Fixture::bios_fault)) {
        asm volatile("xor %%edx, %%edx; mov $1, %%eax; xor %%ecx, %%ecx; div %%rcx"
                     :
                     :
                     : "rax", "rdx", "rcx", "memory");
        fail("Divide exception failed to dispatch");
    }
#endif
#ifdef AURORA_BIOS_FIXTURE
    if (aurora::bios::selected(aurora::bios::Fixture::bios_page_fault)) {
        static_cast<void>(*reinterpret_cast<volatile const std::uint8_t *>(0x400000));
        fail("Page fault failed to dispatch");
    }
#endif
#ifdef AURORA_BIOS_FIXTURE
    if (aurora::bios::selected(aurora::bios::Fixture::bios_wp)) {
        *reinterpret_cast<volatile std::uint8_t *>(0x10000) = 0;
        fail("Supervisor write protection failed");
    }
#endif
#ifdef AURORA_BIOS_FIXTURE
    if (aurora::bios::selected(aurora::bios::Fixture::bios_nx)) {
        nx_probe[0] = 0xc3;
        Serial::text("AURORA_FAULT_TARGET: ");
        Serial::number(reinterpret_cast<std::uint64_t>(nx_probe.data()));
        Serial::text("\r\n");
        reinterpret_cast<void (*)()>(nx_probe.data())();
        fail("Data execution was permitted");
    }
#endif
#ifdef AURORA_BIOS_FIXTURE
    if (aurora::bios::selected(aurora::bios::Fixture::bios_stack)) {
        asm volatile("mov $0x88000, %%rsp; pushq $0" : : : "memory");
        fail("Stack guard failed");
    }
#endif
    user_expected = true;
    Serial::text("AURORA_USER_ENTER: ");
    auto probe_mode = static_cast<unsigned>(AURORA_USER_PROBE_MODE);
#ifdef AURORA_BIOS_FIXTURE
    const auto fixture = static_cast<unsigned>(aurora::bios::fixture);
    if (fixture >= static_cast<unsigned>(aurora::bios::Fixture::bios_user_read) &&
        fixture <= static_cast<unsigned>(aurora::bios::Fixture::bios_user_io))
        probe_mode = fixture - static_cast<unsigned>(aurora::bios::Fixture::bios_user_read) + 1;
#endif
    Serial::number(probe_mode);
    Serial::text("\r\n");
    const auto user_result = user_probe(probe_mode);
    user_expected = false;
    require(user_result == 1 && user_returns == 1 && Protection::verify(),
            "Controlled user boundary did not return intact");
    Serial::text("AURORA_USER_OK: ring3, own stack, TSS entry, controlled return\r\n");
#ifdef AURORA_BIOS_FIXTURE
    if (aurora::bios::schedule())
        require(aurora::user::Scheduler::run(pages), "Scheduling test failed");
    else
        compiled_program_self_test();
#else
    compiled_program_self_test();
#endif
    const auto value = language_value();
    Serial::text("Aurora language result: ");
    Serial::number(static_cast<unsigned long long>(value));
    Serial::text("\r\n");
    if (value == 42) {
        Serial::text("AURORA_BOOT_OK\r\n");
#ifdef AURORA_INTERACTIVE_CONSOLE
        aurora::console::Interactive::run();
#endif
        aurora::hardware::Io::write(0xf4, 0x10);
    } else {
        Serial::text("AURORA_BOOT_FAIL\r\n");
        aurora::hardware::Io::write(0xf4, 0x11);
    }
}
