// Temporary trusted hardware bootstrap, not the Aurora language or its safety model.
// No C runtime, heap allocation, or object ABI export.
// Standard-library views/arrays are compile-time-only bootstrap conveniences.
#include <array>
#include <string_view>
#include "pages.hpp"
#include "interrupts.hpp"
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
    const auto entries = physical_read(0x5000, 2);
    if (entries == 0 || entries > 32) return false;
    auto covered = false;
    for (auto index = std::uint64_t{0}; index < entries; ++index) {
        const auto entry = 0x5008 + index * 24;
        const auto base = physical_read(entry, 8);
        const auto size = physical_read(entry + 8, 8);
        const auto type = physical_read(entry + 16, 4);
        const auto attributes = physical_read(entry + 20, 4);
        if ((attributes & 1) == 0 || size == 0) continue;
        if (base > UINT64_MAX - size) return false;
        if (base < end && base + size > start && type != 1) return false;
        if (type == 1 && base <= start && base + size >= end) covered = true;
    }
    return covered;
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
}
auto exception_dispatch(std::uint64_t vector, std::uint64_t error, std::uint64_t instruction) -> void asm("aurora_exception_dispatch");
auto exception_dispatch(std::uint64_t vector, std::uint64_t error, std::uint64_t instruction) -> void {
    if (vector == 3 && breakpoint_expected) {
        breakpoint_count = breakpoint_count + 1;
        return;
    }
    using aurora::hardware::Serial;
    Serial::text("AURORA_EXCEPTION_FATAL: "); Serial::number(vector);
    Serial::text(" error="); Serial::number(error);
    Serial::text(" rip="); Serial::number(instruction); Serial::text("\r\n");
    fail("Exception halted safely");
}
// Deliberately narrow temporary assembly symbols, not a supported C source/ABI contract.
auto language_value() -> long long asm("aurora_kernel_value");
auto breakpoint_probe() -> unsigned long long asm("aurora_breakpoint_probe");
auto kernel_main() -> void asm("aurora_kernel_main");
auto kernel_main() -> void {
    using aurora::hardware::Serial;
    Serial::initialize();
    Serial::text("Aurora bootstrap: x86-64 long mode\r\n");
    aurora::hardware::Interrupts::initialize();
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
