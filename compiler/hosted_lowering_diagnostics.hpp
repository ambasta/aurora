#pragma once
#include "types.hpp"
#include "hosted_frontend_abi.hpp"
#include <cstdint>
#include <functional>
#include <span>

namespace aurora {
// The fixed rejection report a failed lowering publishes.
struct HostedLoweringInput {
    std::span<const hosted_abi::compiler_lowering::OutputRow> rows;
    std::span<const hosted_abi::compiler_lowering::OperandRow> operands;
    std::int64_t sourceByteCount = 0;
    std::int64_t moduleRoot = -1;
    std::int64_t diagnosticRow = -1;
};
// Mechanical, bounded views of identities already selected by Aurora. Each
// callback checks its Session ID and exact domain before indexing or rendering;
// none performs lookup, chooses another name, or rechecks source semantics.
struct HostedLoweringDiagnosticServices {
    // Returns the retained token for an existing source-reference row. Source
    // references keep their immutable SourceText alive. Synthetic reports still
    // validate this identity, but deliberately discard any source-backed span.
    std::function<Token(std::int64_t)> sourceReference;
    // Existing typeName spelling for the selected resolved type identity.
    std::function<std::string(std::int64_t)> typeName;
    // The reason fixes the name domain: original field/local/binding/call
    // spelling, canonical nominal name, or already selected callable name.
    // It never authorizes choosing between native and source names anew.
    std::function<std::string(hosted_abi::compiler_lowering::LoweringError, std::int64_t)> name;
};

// Render only a published semantic rejection or one of the selected IR-layout
// integrity failures. Success, storage failure, invalid entry without a selected
// reason, malformed payloads and unknown enums are not semantic diagnostics.
// Input holds the published copied pools; the sole report is row 0 / operands
// 0..2, with no module root. Inactive row/operand fields are ignored.
// Throws Internal on malformed transport. Callback/allocation exceptions remain
// owned by the caller's armed Session guard; no partial diagnostic is published.
Diagnostic renderHostedLoweringDiagnostic(const hosted_abi::compiler_lowering::LoweringResult &result,
                                          const HostedLoweringInput &input,
                                          const HostedLoweringDiagnosticServices &services);
} // namespace aurora
