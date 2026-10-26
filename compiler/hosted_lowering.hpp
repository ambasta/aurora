#pragma once
#include "ir.hpp"
#include <cstdint>
#include <span>
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

// The native diagnostic renderer sees only the fixed rejection report. The
// successful projection reads Session directly through source readonly methods.
struct HostedLoweringInput {
    std::span<const hosted_abi::compiler_lowering::OutputRow> rows;
    std::span<const hosted_abi::compiler_lowering::OperandRow> operands;
    std::int64_t sourceByteCount = 0;
    std::int64_t moduleRoot = -1;
    std::int64_t diagnosticRow = -1;
};
struct HostedLoweringOutput {
    ir::InstructionIngress instructions;
    std::vector<std::int64_t> lintReferences;
};

// The one successful projection route counts/fills pending source-owned stores.
// Temporary projection storage is gone on return; Session remains owned by the
// caller only for retained SourceSpan rendering, then dies before ir::validate.
HostedLoweringOutput projectHostedLowering(const void *session,
                                           std::uint64_t payloadBytes,
                                           std::int64_t moduleRoot,
                                           std::int64_t diagnosticRow);
} // namespace aurora
