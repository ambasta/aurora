#pragma once
#include "service-budget-policy.hpp"
#include "../console.hpp"

namespace aurora::uefi {
// Trusted, shared single-BSP xAPIC transport. The caller must first establish
// LocalApicAdmission and the exact supervisor mapping. This creates no grant.
// Service/domain ownership and console phase/context checks stay with callers.
class LocalApicTimerIo final {
public:
    static constexpr std::uint32_t vector = 64;

    [[nodiscard]] static auto read(unsigned offset) -> std::uint32_t {
        return *reinterpret_cast<volatile std::uint32_t*>(LocalApicAdmission::virtual_address + offset);
    }
    static auto write(unsigned offset, std::uint32_t value) -> void {
        *reinterpret_cast<volatile std::uint32_t*>(LocalApicAdmission::virtual_address + offset) = value;
        static_cast<void>(read(0x20));
    }
    [[nodiscard]] static auto irq_off() -> bool {
        std::uint64_t flags;
        asm volatile("pushfq; pop %0" : "=r"(flags));
        return (flags & 0x200) == 0;
    }
    [[nodiscard]] static auto quiet(unsigned bank, bool permit_timer) -> bool {
        for (unsigned part = 0; part < 8; ++part) {
            const auto allowed = permit_timer && part == vector / 32 ? 1U << (vector % 32) : 0;
            if (read(bank + part * 16) & ~allowed) { return false; }
        }
        return true;
    }
    [[nodiscard]] static auto pending() -> bool {
        return (read(0x200 + (vector / 32) * 16) & (1U << (vector % 32))) != 0;
    }
    [[nodiscard]] static auto stop() -> bool {
        if (!irq_off()) { return false; }
        write(0x320, 0x10000 | vector);
        write(0x380, 0);
        return read(0x390) == 0 && (read(0x320) & 0x700ff) == (0x10000 | vector);
    }
    [[nodiscard]] static auto arm(std::uint32_t count) -> bool {
        if (!irq_off() || count == 0 || !quiet(0x100, false) || !quiet(0x200, false)) { return false; }
        write(0x320, vector);
        write(0x380, count);
        return (read(0x320) & 0x700ff) == vector;
    }
    [[nodiscard]] static auto acknowledge() -> bool {
        if (!irq_off() || !(read(0x100 + (vector / 32) * 16) & (1U << (vector % 32)))
            || !quiet(0x100, true) || !quiet(0x200, true) || !stop()) {
            return false;
        }
        write(0xb0, 0);
        return quiet(0x100, false);
    }
    [[nodiscard]] static auto initialize(std::uint32_t version) -> bool {
        if (!irq_off()) { return false; }
        hardware::Io::write(0x21, 0xff);
        hardware::Io::write(0xa1, 0xff);
        write(0x320, 0x10000 | vector);
        write(0x380, 0);
        for (const unsigned offset : {0x330U, 0x340U, 0x350U, 0x360U, 0x370U}) { write(offset, 0x10000); }
        if (((version >> 16) & 255) >= 6) { write(0x2f0, 0x10000); }
        write(0x80, 0);
        write(0xf0, 0x1ff);
        write(0x3e0, 3);
        return read(0x80) == 0 && (read(0xf0) & 0x1ff) == 0x1ff && (read(0x3e0) & 0xb) == 3
            && quiet(0x100, false) && quiet(0x200, false);
    }
};
}
