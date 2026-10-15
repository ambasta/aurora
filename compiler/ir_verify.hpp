#pragma once
#include "ir.hpp"
#include <cstddef>
#include <cstdint>

namespace aurora::ir::verification {
// Limits on retained block-entry snapshots, not a global memory/time proof.
// Account before copying a State; revisits retain the same exact operand stack.
class BlockRetentionBudget {
    std::size_t states_ = 0, operands_ = 0;

public:
    static constexpr std::size_t maximumStates = 65536;
    static constexpr std::size_t maximumOperands = 262144;
    void retain(std::size_t operands);
    std::size_t states() const {
        return states_;
    }
    std::size_t operands() const {
        return operands_;
    }
};
class Metrics {
public:
    std::size_t snapshots = 0;
    std::size_t peakOperandDepth = 0;
    std::size_t peakRetainedOperandFacts = 0;
    std::uint64_t peakRetainedValueFacts = 0;
    // Initialization must/may words and bounded service-loan rows across block entries.
    // Excludes the source domain, other native facts, current rows and allocator overhead.
    std::uint64_t peakRetainedInitializationPayloadBytes = 0;
};
void verifyFunction(FunctionBody &function, const Metadata &metadata, Metrics *metrics = nullptr);
} // namespace aurora::ir::verification
