#pragma once
#include "ir.hpp"
#include <cstdint>
#include <functional>
#include <span>
#include <string>
#include <vector>

namespace aurora {
// Diagnostic, configuration, seven scalar contracts, layout, then service operations.
// Each selected prelude is checked explicitly; no arbitrary prefix is exempted
// from the output graph's ownership contract.
inline constexpr std::int64_t hostedLoweringPreludeRows = 10 + service::operations.size();
inline constexpr std::int64_t
hostedLoweringPrefixRows(bool includeCall, bool includePort = false, bool includeServe = false) {
    return 10 + service::operationCount(includeCall, includePort, includeServe);
}

// These views own no Session descriptor. HostedResolution copies each published
// output pool once while its consuming owner is armed, then keeps the copies
// alive for this call. Source bytes stay in Session; only requested immutable
// already-decoded literal bytes are read by index during direct owner fill.
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
    // Read one already-decoded retained byte through the existing Session
    // accessor. Projection bounds-checks each immutable interval; direct fill
    // streams bytes into the Aurora owner without a native payload copy.
    std::function<std::uint8_t(std::int64_t index)> literalByte;
};

struct HostedLoweringOutput {
    ir::InstructionIngress instructions;
    std::vector<Diagnostic> diagnostics;
};

// Call only for a checked LoweringResult success. Checks transport integrity and
// fills paired raw instruction/metadata owners; does not publish views or
// call ir::validate. The caller retains Session through projection and rendering,
// then destroys these views and releases Session before independently validating
// the owned result.
HostedLoweringOutput projectHostedLowering(const HostedLoweringInput &input, const HostedLoweringServices &services);
} // namespace aurora
