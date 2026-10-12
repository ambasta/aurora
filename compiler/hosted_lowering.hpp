#pragma once
#include "ir.hpp"
#include <cstdint>
#include <functional>
#include <span>
#include <string>
#include <vector>

namespace aurora {
// The fixed typed prelude is checked explicitly, never an arbitrary prefix of
// rows exempted from the output graph's ownership contract.
inline constexpr std::int64_t hostedLoweringPreludeRows = 15;

// These views own no Session descriptor. HostedResolution copies each published
// output pool once while its consuming owner is armed, then keeps the copies
// alive for this call. Source bytes stay in Session; only requested immutable
// already-decoded literal intervals are copied by the mechanical renderer.
struct HostedLoweringInput {
    std::span<const hosted_abi::compiler_lowering::OutputRow> rows;
    std::span<const hosted_abi::compiler_lowering::OperandRow> operands;
    std::int64_t sourceByteCount = 0;
    std::int64_t moduleRoot = -1;
    std::int64_t diagnosticRow = -1;
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
    // Read exactly count retained bytes starting at begin through the existing
    // source accessor, preserving embedded zeros. Projection bounds-checks the
    // interval before calling and requires the returned length to match exactly.
    std::function<std::vector<std::uint8_t>(std::int64_t begin, std::int64_t count)> literalBytes;
};

struct HostedLoweringOutput {
    ir::Module module;
    std::vector<Diagnostic> diagnostics;
};

// Call only for a checked LoweringResult success. Checks transport integrity and
// materializes privately; deliberately does not call ir::validate. The caller
// retains Session through projection and rendering, then destroys these views
// and releases Session before independently validating the owned result.
HostedLoweringOutput projectHostedLowering(const HostedLoweringInput &input, const HostedLoweringServices &services);
} // namespace aurora
