#include "interrupts.hpp"
#include "protection.hpp"
#include <array>
#include <cstdint>

extern const std::array<std::uint64_t, 32> vectors asm("aurora_exception_vectors");
auto user_return() -> void asm("aurora_user_return");
auto unexpected() -> void asm("aurora_unexpected_interrupt");

// Trusted x86 descriptor encoding is byte-explicit; no packed object layout ABI.
namespace {
alignas(16) constinit std::array<std::uint8_t, 256 * 16> idt{};
alignas(16) constinit std::array<std::uint8_t, 10> idtr{};
alignas(16) constinit std::array<std::uint8_t, 104> tss{};
alignas(16) constinit std::array<std::uint64_t, 7> gdt{
    0, 0x00af9a000000ffff, 0x00cf92000000ffff,
    0x00affa000000ffff, 0x00cff2000000ffff, 0, 0};
alignas(16) constinit std::array<std::uint8_t, 10> gdtr{};
auto write_tss(std::size_t offset, std::uint64_t value) -> void {
    for (auto byte = 0U; byte < 8; ++byte) tss[offset + byte] = value >> (byte * 8);
}
}
auto aurora::hardware::Interrupts::initialize() -> void {
    write_tss(4, Protection::entry_stack_top);
    write_tss(36, Protection::emergency_stack_top);
    tss[102] = 104; // I/O map begins beyond the descriptor limit: all user ports denied.
    const auto tss_base = reinterpret_cast<std::uint64_t>(tss.data());
    gdt[5] = 103 | ((tss_base & 0xffffff) << 16) | (std::uint64_t{0x89} << 40)
        | (((tss_base >> 24) & 0xff) << 56);
    gdt[6] = tss_base >> 32;
    gdtr[0] = 55;
    const auto gdt_base = reinterpret_cast<std::uint64_t>(gdt.data());
    for (auto byte = 0U; byte < 8; ++byte) gdtr[byte + 2] = gdt_base >> (byte * 8);
    asm volatile("lgdt %0" : : "m"(gdtr) : "memory");
    asm volatile("ltr %0" : : "r"(static_cast<std::uint16_t>(40)) : "memory");
    for (std::size_t vector = 0; vector < 256; ++vector) {
        const auto address = vector < 32 ? vectors[vector] : vector == 128
            ? reinterpret_cast<std::uint64_t>(&user_return) : reinterpret_cast<std::uint64_t>(&unexpected);
        const auto slot = vector * 16;
        idt[slot] = address; idt[slot + 1] = address >> 8;
        idt[slot + 2] = 8; idt[slot + 3] = 0;
        idt[slot + 4] = vector == 8 ? 1 : 0;
        idt[slot + 5] = vector == 128 ? 0xee : 0x8e;
        idt[slot + 6] = address >> 16; idt[slot + 7] = address >> 24;
        for (auto byte = 0; byte < 4; ++byte) idt[slot + 8 + byte] = address >> (32 + byte * 8);
    }
    const auto base = reinterpret_cast<std::uint64_t>(idt.data());
    idtr[0] = 0xff; idtr[1] = 0x0f;
    for (auto byte = 0; byte < 8; ++byte) idtr[byte + 2] = base >> (byte * 8);
    asm volatile("lidt %0" : : "m"(idtr) : "memory");
}
