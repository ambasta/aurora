#pragma once
#include "handoff.hpp"
#include <array>

namespace aurora::uefi {
class EventAdmission;

// Copied terminal evidence for a stopped supervisor. Addresses describe retained
// bytes, not capabilities. Serial failure never turns an incomplete result into
// a success. The ELF symbol binds this layout to the exact linked image.
class EventTerminal final {
public:
    std::uint64_t magic{}, version{}, selector{}, phase{}, failure{}, completion{};
    std::uint64_t backing{}, ring{}, before_ring{}, after_ring{}, ring_bytes{};
    std::uint64_t dma_submitted{}, dma_completed{}, readiness_reads{}, polls{}, acknowledgements{}, output_bytes{};
    // *_valid means a complete copy bracketed by equal register observations.
    // Only producer_quiet=1 admits stable event slots; a failed producer's
    // double-read snapshot is preserved evidence, not a coherence proof.
    std::uint64_t exposed{}, producer_quiet{}, entered{}, serial_failed{}, before_valid{}, after_valid{}, checks{};
    // DT base, command base, event base, control, EFR, command head/tail,
    // event head/tail, full-width status and EDU command/count.
    std::array<std::uint64_t, 12> before_registers{}, after_registers{};
    // Every byte of each 16-byte left guard, 4-byte value and 16-byte right guard.
    // These are data guards; they are not described as adjacent ring guards.
    std::array<std::byte, 144> before_data{}, after_data{};
};
static_assert(sizeof(EventTerminal) == 672 && alignof(EventTerminal) == 8 && offsetof(EventTerminal, backing) == 48 &&
              offsetof(EventTerminal, ring) == 56 && offsetof(EventTerminal, before_ring) == 64 &&
              offsetof(EventTerminal, after_ring) == 72 && offsetof(EventTerminal, ring_bytes) == 80 &&
              offsetof(EventTerminal, before_registers) == 192 && offsetof(EventTerminal, after_registers) == 288 &&
              offsetof(EventTerminal, before_data) == 384 && offsetof(EventTerminal, after_data) == 528);

[[noreturn]] auto run_event_intake(std::uint64_t arena, const Bytes &handoff, const EventAdmission &admission) -> void;
} // namespace aurora::uefi
