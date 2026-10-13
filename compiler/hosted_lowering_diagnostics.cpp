#include "hosted_lowering_diagnostics.hpp"
#include <string_view>
#include <utility>

namespace aurora {
namespace {
namespace wire = hosted_abi::compiler_lowering;
using wire::LoweringStatus;
using wire::MessageOrigin;
using wire::OperandRole;

[[noreturn]] void invalidDiagnostic() {
    throw Error(DiagnosticCode::Internal, "invalid hosted lowering diagnostic");
}

class DiagnosticRenderer {
    const wire::LoweringResult &result;
    const HostedLoweringInput &input;
    const HostedLoweringDiagnosticServices &services;
    SourceSpan span;

    void check(LoweringStatus status, MessageOrigin origin, OperandRole first, OperandRole second) {
        if (result.result_status != status || input.operands[1].operandRole != first ||
            input.operands[2].operandRole != second)
            invalidDiagnostic();
        for (std::size_t index = 1; index != 3; ++index) {
            const auto &value = input.operands[index];
            if (value.operandRole != OperandRole::NoDiagnosticValue && value.signedValue < 0)
                invalidDiagnostic();
        }
        const auto &source = input.operands[0];
        if (origin == MessageOrigin::unlocated) {
            if (source.operandRole != OperandRole::NoDiagnosticSource)
                invalidDiagnostic();
            return;
        }
        if (source.operandRole != OperandRole::DiagnosticSyntheticRef &&
            (origin != MessageOrigin::source_or_synthetic || source.operandRole != OperandRole::DiagnosticSourceRef))
            invalidDiagnostic();
        if (source.signedValue < 0 || !services.sourceReference)
            invalidDiagnostic();
        const auto token = services.sourceReference(source.signedValue);
        if (source.operandRole == OperandRole::DiagnosticSourceRef) {
            const auto &location = token.span;
            if (!location.source || location.begin.offset > location.end.offset ||
                location.end.offset > location.source->text.size() || location.begin.line < 1 ||
                location.begin.column < 1 || location.end.line < location.begin.line || location.end.column < 1 ||
                (location.begin.line == location.end.line && location.end.column < location.begin.column))
                invalidDiagnostic();
            span = location;
        }
        // The synthetic role preserves Token(name, line)'s empty SourceSpan.
        // Never recover a source span from a same-spelled or backing token.
    }

public:
    DiagnosticRenderer(const wire::LoweringResult &value,
                       const HostedLoweringInput &pools,
                       const HostedLoweringDiagnosticServices &renderers)
        : result(value), input(pools), services(renderers) {
        if ((result.result_status != LoweringStatus::semantic_failure &&
             result.result_status != LoweringStatus::invalid) ||
            result.root_row != -1 || input.moduleRoot != -1 || result.diagnostic_row != 0 || input.diagnosticRow != 0 ||
            input.rows.empty() || input.operands.size() < 3)
            invalidDiagnostic();
        const auto &row = input.rows[0];
        if (row.recordKind != wire::RecordKind::DiagnosticPayload || row.operandBegin != 0 || row.operandCount != 3)
            invalidDiagnostic();
    }

    Diagnostic finish(std::string message) const {
        // Layout guard errors used to receive this default code at the semantic
        // frontend stage too; their invalid status must not change that timing.
        return {DiagnosticCode::Semantic, std::move(message), span};
    }
    // Check the payload against its generated message entry, then fill each
    // {name}/{type}/{integer} placeholder from the payload values in order.
    Diagnostic render(const wire::LoweringMessage &message) {
        check(message.integrity ? LoweringStatus::invalid : LoweringStatus::semantic_failure,
              message.origin,
              message.values[0],
              message.values[1]);
        std::string text;
        std::size_t value = 0;
        for (std::string_view rest = message.text; !rest.empty();) {
            const auto open = rest.find('{');
            text += rest.substr(0, open);
            if (open == std::string_view::npos)
                break;
            const auto close = rest.find('}', open);
            if (close == std::string_view::npos || value >= message.values.size())
                invalidDiagnostic();
            const auto hole = rest.substr(open + 1, close - open - 1);
            text += hole == "name" ? name(value) : hole == "type" ? type(value) : integer(value);
            ++value;
            rest.remove_prefix(close + 1);
        }
        return finish(std::move(text));
    }
    std::string name(std::size_t index) const {
        if (!services.name)
            invalidDiagnostic();
        return services.name(result.result_reason, input.operands[index + 1].signedValue);
    }
    std::string type(std::size_t index) const {
        if (!services.typeName)
            invalidDiagnostic();
        return services.typeName(input.operands[index + 1].signedValue);
    }
    std::string integer(std::size_t index) const {
        return std::to_string(input.operands[index + 1].signedValue);
    }
};
} // namespace

Diagnostic renderHostedLoweringDiagnostic(const wire::LoweringResult &result,
                                          const HostedLoweringInput &input,
                                          const HostedLoweringDiagnosticServices &services) {
    DiagnosticRenderer render(result, input, services);
    // Aurora has already selected the reason; its message comes from the table
    // generated out of lowering_errors.au.
    const auto reason = static_cast<std::size_t>(result.result_reason);
    if (reason >= wire::loweringMessages.size() || !wire::loweringMessages[reason].text)
        invalidDiagnostic();
    return render.render(wire::loweringMessages[reason]);
}
} // namespace aurora
