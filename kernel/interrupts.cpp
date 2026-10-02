#include "interrupts.hpp"
#include <array>
#include <cstdint>

extern const std::array<std::uint64_t, 32> vectors asm("aurora_exception_vectors");
auto unexpected() -> void asm("aurora_unexpected_interrupt");

// Trusted x86 descriptor encoding is byte-explicit; no packed object layout ABI.
namespace {
alignas(16) constinit std::array<std::uint8_t, 256 * 16> idt{};
alignas(16) constinit std::array<std::uint8_t, 10> idtr{};
}
auto aurora::hardware::Interrupts::initialize() -> void {
    for (std::size_t vector = 0; vector < 256; ++vector) {
        const auto address = vector < 32 ? vectors[vector] : reinterpret_cast<std::uint64_t>(&unexpected);
        const auto slot = vector * 16;
        idt[slot] = address; idt[slot + 1] = address >> 8;
        idt[slot + 2] = 8; idt[slot + 3] = 0;
        idt[slot + 4] = 0; idt[slot + 5] = 0x8e;
        idt[slot + 6] = address >> 16; idt[slot + 7] = address >> 24;
        for (auto byte = 0; byte < 4; ++byte) idt[slot + 8 + byte] = address >> (32 + byte * 8);
    }
    const auto base = reinterpret_cast<std::uint64_t>(idt.data());
    idtr[0] = 0xff; idtr[1] = 0x0f;
    for (auto byte = 0; byte < 8; ++byte) idtr[byte + 2] = base >> (byte * 8);
    asm volatile("lidt %0" : : "m"(idtr) : "memory");
}
