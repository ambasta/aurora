#include "apic.hpp"
#include "protection.hpp"
#include <array>
#include <cstddef>
namespace {
using aurora::hardware::Apic;
alignas(4096) constinit std::array<std::uint64_t, 512> directory{};
alignas(4096) constinit std::array<std::uint64_t, 512> leaves{};
constinit bool ready = false;
constinit bool mapped = false;
constinit bool draining = false;
constexpr auto nx = 1ULL << 63;
auto read(std::size_t offset) -> std::uint32_t {
    return *reinterpret_cast<volatile std::uint32_t *>(Apic::base + offset);
}
auto write(std::size_t offset, std::uint32_t value) -> void {
    *reinterpret_cast<volatile std::uint32_t *>(Apic::base + offset) = value;
    static_cast<void>(read(0x20)); // Complete posted MMIO before relying on state.
}
auto msr(std::uint32_t index) -> std::uint64_t {
    std::uint32_t low, high;
    asm volatile("rdmsr" : "=a"(low), "=d"(high) : "c"(index));
    return (std::uint64_t{high} << 32) | low;
}
auto quiet_bank(std::size_t offset, bool allow_timer) -> bool {
    for (std::size_t part = 0; part < 8; ++part) {
        const auto allowed = allow_timer && part == Apic::vector / 32 ? 1U << (Apic::vector % 32) : 0U;
        if ((read(offset + part * 16) & ~allowed) != 0)
            return false;
    }
    return true;
}
auto interrupts_disabled() -> bool {
    std::uint64_t flags;
    asm volatile("pushfq; pop %0" : "=r"(flags));
    return (flags & 0x200) == 0;
}
auto pending() -> bool {
    return (read(0x200 + (Apic::vector / 32) * 16) & (1U << (Apic::vector % 32))) != 0;
}
extern const std::byte drain_begin asm("aurora_drain_begin");
extern const std::byte drain_end asm("aurora_drain_end");
} // namespace
auto Apic::mapping() -> std::uint64_t {
    if (mapped)
        return reinterpret_cast<std::uint64_t>(directory.data()) | 3;
    mapped = true;
    directory[(base >> 21) & 511] = reinterpret_cast<std::uint64_t>(leaves.data()) | 3;
    leaves[(base >> 12) & 511] = base | nx | 0x1b; // P,RW,PCD,PWT; PAT index3 must be UC.
    return reinterpret_cast<std::uint64_t>(directory.data()) | 3;
}
auto Apic::mapping_valid() -> bool {
    for (std::size_t i = 0; i < 512; ++i) {
        const auto expected_d = i == ((base >> 21) & 511) ? reinterpret_cast<std::uint64_t>(leaves.data()) | 3 : 0;
        const auto expected_l = i == ((base >> 12) & 511) ? base | nx | 0x1b : 0;
        if ((directory[i] & ~0x60ULL) != expected_d || (leaves[i] & ~0x60ULL) != expected_l)
            return false;
    }
    return true;
}
auto Apic::initialize() -> bool {
    std::uint32_t a, b, c, d;
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(1), "c"(0));
    if (ready || !interrupts_disabled() || ((b >> 16) & 0xff) > 1 ||
        (d & ((1U << 9) | (1U << 16) | (1U << 5))) != ((1U << 9) | (1U << 16) | (1U << 5)))
        return false;
    const auto control = msr(0x1b);
    if ((control & 0xfffffffffffff000ULL) != base || (control & 0xd00) != 0x900 || ((msr(0x277) >> 24) & 0xff) != 0 ||
        !mapping_valid())
        return false;
    const auto version = read(0x30);
    if ((version & 0xff) < 0x10 || ((version >> 16) & 0xff) < 5)
        return false;
    // Disposable PC transport only: both legacy PIC masks, no external interrupt routing.
    asm volatile("outb %0, $0x21; outb %0, $0xa1" : : "a"(std::uint8_t{0xff}) : "memory");
    write(0x320, 0x10000 | vector);
    write(0x380, 0);
    write(0x340, 0x10000);
    write(0x350, 0x10000);
    write(0x360, 0x10000);
    write(0x370, 0x10000);
    write(0x330, 0x10000);
    if (((version >> 16) & 0xff) >= 6)
        write(0x2f0, 0x10000);
    write(0x80, 0);
    write(0xf0, 0x1ff);
    write(0x3e0, 3); // divide16; intentionally uncalibrated.
    if (read(0x80) != 0 || (read(0xf0) & 0x1ff) != 0x1ff || (read(0x3e0) & 0xb) != 3 || !quiet_bank(0x100, false) ||
        !quiet_bank(0x200, false))
        return false;
    ready = true;
    return true;
}
auto Apic::arm() -> bool {
    if (!ready || !interrupts_disabled() || draining || !quiet_bank(0x100, false) || !quiet_bank(0x200, false))
        return false;
    write(0x320, vector);
    write(0x380, 20000);
    return (read(0x320) & 0x700ff) == vector;
}
auto Apic::stop() -> bool {
    if (!ready)
        return false;
    write(0x320, 0x10000 | vector);
    write(0x380, 0);
    return read(0x390) == 0 && (read(0x320) & 0x700ff) == (0x10000 | vector);
}
auto Apic::acknowledge() -> bool {
    if (!ready || (read(0x100 + (vector / 32) * 16) & (1U << (vector % 32))) == 0 || !quiet_bank(0x100, true) ||
        !quiet_bank(0x200, true) || !stop())
        return false;
    write(0xb0, 0);
    return quiet_bank(0x100, false);
}
auto Apic::drain_interrupt(std::uint64_t pc, std::uint64_t code, std::uint64_t frame) -> bool {
    return draining && code == 8 && frame >= Protection::main_stack_bottom &&
           frame <= Protection::main_stack_top - 176 && frame % 8 == 0 &&
           Protection::current_root() == Protection::kernel_root() &&
           pc >= reinterpret_cast<std::uint64_t>(&drain_begin) && pc <= reinterpret_cast<std::uint64_t>(&drain_end) &&
           acknowledge();
}
auto Apic::drain() -> bool {
    if (!interrupts_disabled() || !stop() || !quiet_bank(0x100, false) || !quiet_bank(0x200, true))
        return false;
    draining = true;
    // Only a latched local-timer interrupt is authorized in this narrow CPL0 window.
    for (unsigned tries = 0; pending() && tries < 10000; ++tries) {
        asm volatile(".global aurora_drain_begin\naurora_drain_begin:\nsti\nnop\nnop\ncli\n.global "
                     "aurora_drain_end\naurora_drain_end:"
                     :
                     :
                     : "memory");
    }
    draining = false;
    return quiet_bank(0x100, false) && quiet_bank(0x200, false);
}

auto aurora::hardware::Apic::pending_test() -> bool {
    if (!arm())
        return false;
    auto seen = false;
    for (unsigned tries = 0; tries < 1000000; ++tries)
        if (pending()) {
            seen = true;
            break;
        }
    return seen && stop() && pending() && drain() && !pending();
}
