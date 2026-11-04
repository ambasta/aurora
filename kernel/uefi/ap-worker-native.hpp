#pragma once
#include "ap-worker-policy.hpp"
#include <cstddef>
#include <cstdint>

namespace aurora::uefi {
// One boot-pinned execution island. No method reclaims or resets this backing.
class ApWorkerLayout final {
public:
    static constexpr std::uint64_t page = 4096, bytes = 0x40000, table_pages = 16;
    static constexpr std::uint64_t startup = 0, permanent = 0x10000;
    static constexpr std::uint64_t request = 0x20000, reply = 0x21000;
    static constexpr std::uint64_t descriptors = 0x22000, idt = 0x23000;
    static constexpr std::uint64_t stack_bottom = 0x25000, stack_top = 0x29000;
    static constexpr std::uint64_t ist_bottom = 0x2a000, ist_top = 0x2c000;
    static constexpr std::uint64_t payload = 0x2d000;
    static constexpr std::uint64_t nx = 1ULL << 63;
};

enum class ApWorkerFixture : std::uint64_t {
    normal,
    fault,
    withheld,
    late,
    wrong_identity,
    wrong_root,
    stagnant_timer,
    no_readiness,
    malformed_status,
    overlap
};
enum class ApWorkerStatus : std::uint64_t {
    unavailable,
    ready,
    done,
    fault,
    timeout,
    rejected,
    pending
};

class ApWorkerResult final {
public:
    ApWorkerStatus status = ApWorkerStatus::unavailable;
    std::uint64_t apic = 0, incarnation = 0, sequence = 0;
    std::int64_t value = 0;
    std::uint64_t ordinal = 0, ticks = 0;
    bool started = false;
    std::uint64_t vector = 0, error = 0, rip = 0, cr2 = 0;
};

class ApWorkerNative final {
    const ApWorkerAdmission *grant_ = nullptr;
    std::uint64_t block_ = 0, low_ = 0, incarnation_ = 0, sequence_ = 0;
    std::uint64_t observation_ = 0, started_observation_ = 0;
    std::uint32_t previous_sample_ = 0;
    bool outstanding_ = false, terminal_ = false;
    unsigned startup_used_ = 0, permanent_used_ = 0;
    ApWorkerFixture fixture_ = ApWorkerFixture::normal;
    std::uint32_t frozen_timer_ = 0;
    bool prepared_ = false, sealed_ = false, started_ = false, ready_ = false, closed_ = false;
    bool ipi_attempted_ = false;
    [[nodiscard]] auto clock() const -> std::uint32_t;
    [[nodiscard]] auto wait_ticks(std::uint32_t ticks) const -> bool;
    [[nodiscard]] auto wait_icr() const -> bool;
    [[nodiscard]] auto send_ipi(std::uint32_t command) -> bool;
    [[nodiscard]] auto await_ready() -> ApWorkerResult;
    [[nodiscard]] auto fault_or_timeout(ApWorkerStatus status) -> ApWorkerResult;
    [[nodiscard]] auto bsp_leaf(std::uint64_t address) const -> std::uint64_t *;

public:
    ApWorkerNative() = default;
    ApWorkerNative(const ApWorkerNative &) = delete;
    auto operator=(const ApWorkerNative &) -> ApWorkerNative & = delete;
    [[nodiscard]] auto prepare(const ApWorkerAdmission &grant,
                               const MemoryMap &map,
                               std::uint64_t block,
                               std::uint64_t low_page,
                               std::uint64_t incarnation,
                               ApWorkerFixture fixture = ApWorkerFixture::normal) -> bool;
    // Only exact previously checked identity leaves change, before the first INIT.
    [[nodiscard]] auto seal() -> bool;
    [[nodiscard]] auto verify_roots() const -> bool;
    [[nodiscard]] auto start() -> ApWorkerResult;
    [[nodiscard]] auto
    publish(std::uint64_t incarnation, std::uint64_t sequence, std::int64_t offset, std::int64_t count)
        -> ApWorkerResult;
    // Each call consumes exactly one already source-reserved observation ordinal.
    [[nodiscard]] auto progress(std::uint64_t incarnation, std::uint64_t sequence, std::uint64_t ordinal)
        -> ApWorkerResult;
    [[nodiscard]] auto settle(std::uint64_t incarnation, std::uint64_t sequence) -> bool;
    [[nodiscard]] auto release_overlap(std::uint64_t incarnation, std::uint64_t sequence, std::uint64_t ordinal)
        -> bool;
    auto close() -> void;
    [[nodiscard]] auto closed() const -> bool {
        return closed_;
    }
    [[nodiscard]] auto retained() const -> bool {
        return prepared_;
    }
    [[nodiscard]] auto startup_attempted() const -> bool {
        return ipi_attempted_;
    }
    [[nodiscard]] auto late_completion_seen() const -> bool;
    [[nodiscard]] auto permanent_root() const -> std::uint64_t {
        return block_ + ApWorkerLayout::permanent;
    }
};
} // namespace aurora::uefi
