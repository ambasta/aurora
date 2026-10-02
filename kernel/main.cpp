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
auto user_program(std::uint64_t entry) -> std::uint64_t asm("aurora_user_program");
namespace aurora::hardware {
using Byte = unsigned char;
using Port = unsigned short;
class Io final {
public:
    static auto write(Port port, Byte value) -> void {
        asm volatile("outb %0, %1" : : "a"(value), "Nd"(port) : "memory");
    }
    static auto read(Port port) -> Byte {
        Byte result;
        asm volatile("inb %1, %0" : "=a"(result) : "Nd"(port) : "memory");
        return result;
    }
};
class Serial final {
public:
    static auto initialize() -> void {
        Io::write(0x3f9, 0); Io::write(0x3fb, 0x80);
        Io::write(0x3f8, 1); Io::write(0x3f9, 0);
        Io::write(0x3fb, 3); Io::write(0x3fa, 0xc7); Io::write(0x3fc, 0x0b);
    }
    static auto put(Byte value) -> void {
        // A broken serial device must not permanently stall kernel boot.
        for (auto remaining = 1000000; remaining > 0; --remaining) {
            if ((Io::read(0x3fd) & 0x20) != 0) { Io::write(0x3f8, value); return; }
        }
    }
    static auto text(std::string_view value) -> void {
        for (const auto character : value) put(static_cast<Byte>(character));
    }
    static auto number(unsigned long long value) -> void {
        std::array<char, 20> digits{}; auto length = 0;
        do { digits[length++] = static_cast<char>('0' + value % 10); value /= 10; } while (value);
        while (length > 0) put(static_cast<Byte>(digits[--length]));
    }
};
}
namespace {
constinit aurora::memory::PhysicalPages pages;
constinit aurora::memory::PhysicalPages foreign_pages;
constinit std::array<std::optional<aurora::memory::PageLease>, aurora::memory::PhysicalPages::capacity> leases{};
#ifdef AURORA_TEST_NX
alignas(4096) constinit std::array<std::uint8_t, 4096> nx_probe{};
#endif
constinit aurora::user::ProgramRun program_run;
constinit std::size_t program_index = 0;
volatile bool user_expected = false;
volatile unsigned user_returns = 0;
volatile bool breakpoint_expected = false;
volatile unsigned breakpoint_count = 0;
[[noreturn]] auto fail(std::string_view message) -> void {
    aurora::hardware::Serial::text(message);
    aurora::hardware::Serial::text("\r\nAURORA_BOOT_FAIL\r\n");
    aurora::hardware::Io::write(0xf4, 0x11);
    for (;;) asm volatile("cli; hlt");
}
auto require(bool condition, std::string_view message) -> void {
    if (!condition) fail(message);
}
// Trusted physical-memory transport: E820 bytes and page mappings only.
auto physical_read(std::uint64_t address, unsigned bytes) -> std::uint64_t {
    auto result = std::uint64_t{0};
    for (auto index = 0U; index < bytes; ++index)
        result |= static_cast<std::uint64_t>(*reinterpret_cast<volatile const std::uint8_t*>(address + index)) << (index * 8);
    return result;
}
auto arena_is_usable(std::uint64_t start, std::uint64_t end) -> bool {
    const auto bytes = std::span{reinterpret_cast<const std::byte*>(0x5000), std::size_t{8 + 32 * 24}};
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
            *reinterpret_cast<volatile std::uint8_t*>(*address + byte) = static_cast<std::uint8_t>(index);
    }
    require(pages.used() == count && !pages.acquire(), "Exhaustion accounting failed");
    for (std::size_t index = 0; index < count; ++index) {
        const auto address = pages.address(*leases[index]);
        require(address.has_value() && physical_read(*address, 1) == index
            && physical_read(*address + page_size - 1, 1) == index, "Allocated physical pages alias or are inaccessible");
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
    using aurora::user::UserPrograms;
    using aurora::user::ProgramEvent;
    using aurora::hardware::Serial;
    const auto* contract = UserPrograms::contract(index);
    require(contract != nullptr && !user_expected && !program_run.running(), "Invalid or nested user program run");
    require(UserPrograms::scrub_stack(), "User stack reset failed");
    require(program_run.begin(*contract), "Program contract rejected");
    program_index = index;
    Serial::text("AURORA_PROGRAM_ENTER: image="); Serial::number(index); Serial::text("\r\n");
#ifdef AURORA_TEST_PROGRAM_KERNEL_TRAP
    asm volatile("jmp *%0" : : "r"(contract->bounds_pc()) : "memory");
    fail("Kernel UD2 unexpectedly returned");
#endif
    const auto resumed = user_program(contract->entry());
    require(resumed == 1 && !program_run.running() && program_run.event() == expected,
        "Program did not finish with the required typed outcome");
    require(aurora::hardware::Protection::verify(), "Program altered protected mapping state");
    if (expected == ProgramEvent::returned) {
        require(program_run.value() == 42, "Compiled user program returned wrong result");
        Serial::text("AURORA_PROGRAM_RETURN: image="); Serial::number(index);
        Serial::text(" value="); Serial::number(program_run.value()); Serial::text("\r\n");
    } else {
        Serial::text("AURORA_PROGRAM_CONTAINED: image="); Serial::number(index);
        Serial::text(expected == ProgramEvent::bounds ? " kind=bounds\r\n" : " kind=overflow\r\n");
    }
}
auto compiled_program_self_test() -> void {
    using aurora::user::ProgramEvent;
    execute_program(0, ProgramEvent::returned);
    execute_program(1, ProgramEvent::bounds);
    execute_program(0, ProgramEvent::returned);
    execute_program(2, ProgramEvent::overflow);
    execute_program(0, ProgramEvent::returned);
    aurora::hardware::Serial::text("AURORA_COMPILED_USER_OK: arrays, loop, bounds, overflow, clean restart\r\n");
}
}
auto exception_dispatch(std::uint64_t vector, std::uint64_t error, std::uint64_t instruction,
    std::uint64_t code, std::uint64_t frame, std::uint64_t user_value) -> std::uint64_t asm("aurora_exception_dispatch");
auto exception_dispatch(std::uint64_t vector, std::uint64_t error, std::uint64_t instruction,
    std::uint64_t code, std::uint64_t frame, std::uint64_t user_value) -> std::uint64_t {
    using aurora::hardware::Protection;
    const auto cpl = code & 3;
    if (vector == 3 && breakpoint_expected && cpl == 0) {
        breakpoint_count = breakpoint_count + 1;
        return 0;
    }
    const auto on_entry_stack = frame >= Protection::entry_stack_bottom && frame < Protection::entry_stack_top;
    if (vector == 128 && user_expected && cpl == 3 && on_entry_stack && user_value == 42
        && instruction >= Protection::user_code && instruction < Protection::user_code + 4096) {
        user_returns = user_returns + 1;
        return 1; // Dedicated assembly continuation restores only the saved privileged stack.
    }
    using aurora::hardware::Serial;
    if (program_run.running() && code == 0x1b && frame >= Protection::entry_stack_bottom
        && frame <= Protection::entry_stack_top - 176 && frame % 8 == 0) {
        const auto flags = physical_read(frame + 152, 8);
        const auto stack = physical_read(frame + 160, 8);
        const auto ss = physical_read(frame + 168, 8);
        const auto context = aurora::user::ProgramContext{vector, error, instruction, code, ss, stack, flags, frame};
        if (program_run.accept(context, user_value)) {
            if (program_run.event() != aurora::user::ProgramEvent::returned) {
                Serial::text("AURORA_PROGRAM_FAULT: image="); Serial::number(program_index);
                Serial::text(program_run.event() == aurora::user::ProgramEvent::bounds ? " kind=bounds" : " kind=overflow");
                Serial::text(" vector="); Serial::number(vector);
                Serial::text(" rip="); Serial::number(instruction);
                Serial::text(" cpl=3 frame="); Serial::number(frame); Serial::text("\r\n");
            }
            return 1;
        }
    }
    Serial::text("AURORA_EXCEPTION_FATAL: "); Serial::number(vector);
    Serial::text(" error="); Serial::number(error);
    Serial::text(" rip="); Serial::number(instruction); Serial::text("\r\n");
    std::uint64_t cr2;
    asm volatile("mov %%cr2, %0" : "=r"(cr2));
    Serial::text("AURORA_EXCEPTION_CONTEXT: cpl="); Serial::number(cpl);
    Serial::text(" frame="); Serial::number(frame);
    Serial::text(" cr2="); Serial::number(cr2); Serial::text("\r\n");
    if (cpl == 3 && on_entry_stack) Serial::text("AURORA_TSS_ENTRY_OK\r\n");
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
    require(arena_is_usable(0x10000, reinterpret_cast<std::uint64_t>(&protected_image_end))
        && arena_is_usable(Protection::emergency_stack_bottom, Protection::main_stack_top)
        && arena_is_usable(aurora::user::UserPrograms::code_begin, aurora::user::UserPrograms::code_end)
        && arena_is_usable(Protection::user_code, Protection::user_code + 4096)
        && arena_is_usable(Protection::user_stack_bottom, Protection::user_stack_top), "Firmware does not grant protected image, stacks or controlled user pages");
    require(Protection::activate(), "Required NX capability or protected mapping validation failed");
    Serial::text("AURORA_WX_OK: RX text, R-NX constants, RW-NX data, NXE, WP, guards\r\n");
    breakpoint_expected = true;
    const auto registers_preserved = breakpoint_probe();
    breakpoint_expected = false;
    require(breakpoint_count == 1 && registers_preserved == 1, "Breakpoint dispatch did not resume correctly");
    Serial::text("AURORA_EXCEPTION_OK: breakpoint, 15 GPRs, direction flag\r\n");
    page_self_test();
#ifdef AURORA_TEST_DIVIDE_ERROR
    asm volatile("xor %%edx, %%edx; mov $1, %%eax; xor %%ecx, %%ecx; div %%rcx" : : : "rax", "rdx", "rcx", "memory");
    fail("Divide exception failed to dispatch");
#endif
#ifdef AURORA_TEST_PAGE_FAULT
    static_cast<void>(*reinterpret_cast<volatile const std::uint8_t*>(0x400000));
    fail("Page fault failed to dispatch");
#endif
#ifdef AURORA_TEST_WP
    *reinterpret_cast<volatile std::uint8_t*>(0x10000) = 0;
    fail("Supervisor write protection failed");
#endif
#ifdef AURORA_TEST_NX
    nx_probe[0] = 0xc3;
    Serial::text("AURORA_FAULT_TARGET: "); Serial::number(reinterpret_cast<std::uint64_t>(nx_probe.data())); Serial::text("\r\n");
    reinterpret_cast<void (*)()>(nx_probe.data())();
    fail("Data execution was permitted");
#endif
#ifdef AURORA_TEST_STACK
    asm volatile("mov $0x88000, %%rsp; pushq $0" : : : "memory");
    fail("Stack guard failed");
#endif
    user_expected = true;
    Serial::text("AURORA_USER_ENTER: "); Serial::number(AURORA_USER_PROBE_MODE); Serial::text("\r\n");
    const auto user_result = user_probe(AURORA_USER_PROBE_MODE);
    user_expected = false;
    require(user_result == 1 && user_returns == 1 && Protection::verify(), "Controlled user boundary did not return intact");
    Serial::text("AURORA_USER_OK: ring3, own stack, TSS entry, controlled return\r\n");
    compiled_program_self_test();
    const auto value = language_value();
    Serial::text("Aurora language result: ");
    Serial::number(static_cast<unsigned long long>(value));
    Serial::text("\r\n");
    if (value == 42) {
        Serial::text("AURORA_BOOT_OK\r\n");
        aurora::hardware::Io::write(0xf4, 0x10);
    } else {
        Serial::text("AURORA_BOOT_FAIL\r\n");
        aurora::hardware::Io::write(0xf4, 0x11);
    }
}
