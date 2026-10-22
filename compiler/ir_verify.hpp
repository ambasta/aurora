#pragma once
#include "ir.hpp"
#include <cstddef>
#include <cstdint>

namespace aurora::ir::verification {
class Metrics {
public:
    std::size_t snapshots = 0;
    std::size_t peakOperandDepth = 0;
    std::size_t peakRetainedOperandFacts = 0;
    std::uint64_t peakRetainedValueFacts = 0;
    // Initialization must/may words and bounded service-loan rows across block entries.
    // Excludes the source domain, other source facts, current rows and allocator overhead.
    std::uint64_t peakRetainedInitializationPayloadBytes = 0;
};
} // namespace aurora::ir::verification
