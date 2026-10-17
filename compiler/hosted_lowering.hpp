#pragma once
#include "ir.hpp"
#include <cstdint>
#include <functional>
#include <span>
#include <string>
#include <vector>

namespace aurora {
// Maximum of the two exact typed preludes (historical 15, Call-enabled 16).
// Each selected prelude is checked explicitly; no arbitrary prefix is exempted
// from the output graph's ownership contract.
inline constexpr std::int64_t hostedLoweringPreludeRows = 16;

// Failure diagnostics copy only their fixed report prefix while the consuming
// Session owner is armed. These views own no Session descriptor.
struct HostedLoweringInput {
    std::span<const hosted_abi::compiler_lowering::OutputRow> rows;
    std::span<const hosted_abi::compiler_lowering::OperandRow> operands;
    std::int64_t sourceByteCount = 0;
    std::int64_t moduleRoot = -1;
    std::int64_t diagnosticRow = -1;
};

// Success borrows the sealed Session only until the consuming owner releases it.
// Each checked read returns a copied record; no pool view or descriptor escapes.
class HostedProjectionInput {
    const void *session;
    std::int64_t rows, operands;

public:
    const std::int64_t sourceByteCount, moduleRoot;
    HostedProjectionInput(const void *session, std::uint64_t payloadBytes, std::int64_t sourceBytes, std::int64_t root);
    std::int64_t rowCount() const {
        return rows;
    }
    std::int64_t operandCount() const {
        return operands;
    }
    hosted_abi::compiler_lowering::OutputRow row(std::int64_t id) const;
    hosted_abi::compiler_lowering::OperandRow operand(std::int64_t id) const;
    void checkOperands(std::int64_t begin, std::int64_t count) const;
};

// Existing in-process resolution renderers, not Aurora callbacks or semantic
// queries. Every renderer must bounds-check its Session ID and exact domain:
// concrete type, callable symbol, class symbol, enum symbol, source reference,
// assigned module scope, or entry in the exact immutable seeded service catalog.
// They only spell already-chosen identities. Their cached source/type/name views
// remain shared with diagnostic and ABI rendering; no Program is reconstructed.
struct HostedLoweringServices {
    std::function<Type(std::int64_t)> type;
    std::function<std::string(std::int64_t)> functionName;
    std::function<std::string(std::int64_t)> className;
    std::function<std::string(std::int64_t)> enumName;
    std::function<Token(std::int64_t)> identifier;
    std::function<void(std::int64_t)> checkModuleScope;
    std::function<service::Kind(std::int64_t)> serviceKind;
    std::function<service::Operation(std::int64_t)> serviceOperation;
};

struct HostedLoweringOutput {
    ir::InstructionIngress instructions;
    std::vector<Diagnostic> diagnostics;
};

std::uint64_t projectionQuota(const HostedProjectionInput &input, std::span<const std::uint8_t> table);
std::vector<std::uint8_t> renderProjectionIdentities(const void *plan, const HostedLoweringServices &services);

// Call only for a checked LoweringResult success. Checks transport integrity and
// fills paired raw instruction/metadata owners; does not publish views or
// call ir::validate. The caller retains Session through projection and rendering,
// then destroys these views and releases Session before independently validating
// the owned result.
HostedLoweringOutput projectHostedLowering(const HostedProjectionInput &input,
                                           const HostedLoweringServices &services,
                                           const void *projectionPlan);
} // namespace aurora
