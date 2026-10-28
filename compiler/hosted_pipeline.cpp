#include "hosted_pipeline.hpp"
#include <algorithm>
#include <limits>
#include <tuple>

namespace aurora {
namespace {
namespace wire = hosted_abi::compiler_pipeline;
namespace x86 = hosted_abi::compiler_x86;
namespace verifier = hosted_abi::compiler_ir_verification;
using Stage = wire::Stage;
constexpr std::int64_t artifactLimit = 64 * 1024 * 1024;

[[noreturn]] void internal(const char *message) {
    throw Error(DiagnosticCode::Internal, message);
}
// The emitter's own status decides unless it stopped cleanly; then the object writer's does.
[[noreturn]] void emissionFailure(x86::EmitStatus emitter, x86::EmitStatus object) {
    auto status = emitter;
    if (status == x86::EmitStatus::pending || status == x86::EmitStatus::running || status == x86::EmitStatus::complete)
        status = object;
    if (status == x86::EmitStatus::allocation)
        internal("hosted x86 emission allocation failed");
    if (status == x86::EmitStatus::limit)
        internal("hosted x86 emission exceeded its bounded output or workspace");
    if (status == x86::EmitStatus::unsupported)
        internal("x86 object emission does not support this instruction or data form");
    internal("invalid hosted x86 emission transport");
}
[[noreturn]] void reject(const wire::Report &report) {
    const auto &failure = report.failureValue;
    switch (report.stageValue) {
    case Stage::allocation:
        internal("hosted compiler pipeline allocation failed");
    case Stage::projection_allocation:
        internal("hosted lowering projection allocation failed");
    case Stage::projection:
        internal("invalid hosted lowering result");
    case Stage::metadata_allocation:
        internal("hosted IR metadata allocation failed");
    case Stage::metadata_transport:
        internal("invalid hosted IR metadata transport");
    case Stage::metadata:
        if (const auto *message = hosted_abi::compiler_ir_metadata::metadataErrorMessage(failure.metadataValue))
            throw Error(message);
        internal("invalid hosted IR metadata transport");
    case Stage::instruction_allocation:
        internal("hosted IR instruction allocation failed");
    case Stage::instruction_transport:
        internal("invalid hosted IR instruction transport");
    case Stage::instruction:
        if (const auto *message =
                hosted_abi::compiler_ir_instructions::instructionErrorMessage(failure.instructionValue))
            throw Error(message);
        internal("invalid hosted IR instruction transport");
    case Stage::body_count:
        throw Error("invalid typed IR: callable body count mismatch");
    case Stage::verification: {
        // Allocator and integrity refusals stay Internal; semantic rejections take the caller's default.
        const auto first = failure.verificationValue.firstValue;
        const auto *message = verifier::verificationErrorMessage(failure.verificationValue);
        if (!message)
            internal("invalid hosted IR verification workspace");
        throw Error(first == verifier::VerificationErrorFirst::allocation ||
                            first == verifier::VerificationErrorFirst::internal
                        ? DiagnosticCode::Internal
                        : DiagnosticCode::Unclassified,
                    message);
    }
    case Stage::graph:
        if (failure.graphValue == hosted_abi::compiler_ir_graph::GraphStatus::recursive)
            throw Error("invalid typed IR: recursive receiver call cycle");
        internal("invalid hosted IR graph result");
    case Stage::declarations:
        internal("invalid hosted resolution result");
    case Stage::emission:
        emissionFailure(failure.emitterValue, failure.objectValue);
    default:
        internal("invalid hosted compiler pipeline result");
    }
}
std::uint64_t options(const EmissionRequest &request) {
    std::uint64_t result = 0;
    if (request.emit)
        result |= 1;
    if (request.binding == SymbolBinding::Local)
        result |= 2;
    if (request.reflection == ReflectionEmission::Referenced)
        result |= 4;
    if (request.format == CodeEmission::Object)
        result |= 8;
    if (request.stackFacts)
        result |= 16;
    if (request.abiFacts)
        result |= 32;
    return result;
}
class Result {
    hosted_abi::PipelineRelease release_{};

public:
    Result(std::uint64_t region,
           const hosted_abi::compiler_resolver::Session &session,
           std::int64_t root,
           std::int64_t diagnostic,
           std::uint64_t options) {
        release_.region = region;
        hosted_abi::PipelineRun run{};
        run.region = region;
        run.session = session;
        run.root = root;
        run.diagnostic = diagnostic;
        run.options = options;
        aurora_hosted_pipeline_run(&run, data());
    }
    ~Result() {
        aurora_hosted_pipeline_release(&release_);
    }
    Result(const Result &) = delete;
    Result &operator=(const Result &) = delete;
    void *data() {
        return release_.result.storage.data();
    }
    std::string artifact(x86::Artifact kind, std::int64_t size) {
        if (size < 0 || (kind != x86::Artifact::stack && size > artifactLimit))
            internal("invalid hosted x86 emission transport");
        std::string result(static_cast<std::size_t>(size), '\0');
        for (std::int64_t offset = 0; offset < size;) {
            x86::EmitChunk chunk{};
            aurora_hosted_pipeline_chunk(data(), static_cast<std::int64_t>(kind), offset, &chunk);
            if (chunk.byteCount <= 0 || chunk.byteCount > 512 || chunk.byteCount > size - offset)
                internal("invalid hosted x86 emission transport");
            std::copy_n(chunk.payload.begin(), static_cast<std::size_t>(chunk.byteCount), result.begin() + offset);
            offset += chunk.byteCount;
        }
        return result;
    }
};
} // namespace

Diagnostic copyReport(const std::function<hosted_abi::compiler_resolver::Report(std::int64_t)> &read,
                      const ReportSource &source) {
    const auto first = read(0);
    const auto header = [](const auto &report) {
        return std::tuple{report.family,
                          report.warning,
                          report.source,
                          report.begin,
                          report.begin_line,
                          report.begin_column,
                          report.end,
                          report.end_line,
                          report.end_column};
    };
    constexpr auto chunk = static_cast<std::int64_t>(std::tuple_size_v<decltype(first.payload)>);
    Diagnostic result;
    for (auto report = first;; report = read(static_cast<std::int64_t>(result.message.size()))) {
        if (report.byteCount < 0 || report.byteCount > chunk || header(report) != header(first) ||
            result.message.size() > artifactLimit)
            internal("invalid hosted resolution result");
        result.message.append(reinterpret_cast<const char *>(report.payload.data()),
                              static_cast<std::size_t>(report.byteCount));
        if (report.byteCount < chunk)
            break;
    }
    if (first.warning < 0 || first.warning > 1 || first.source < -1)
        internal("invalid hosted resolution result");
    // Aurora names the code by its number; the host keeps the family table.
    const auto number = std::to_string(first.family);
    const auto name = "AU" + std::string(number.size() < 4 ? 4 - number.size() : 0, '0') + number;
    while (diagnosticCode(result.code) != name) {
        if (result.code == DiagnosticCode::UnreadLocal)
            internal("invalid hosted resolution result");
        result.code = static_cast<DiagnosticCode>(static_cast<int>(result.code) + 1);
    }
    result.severity = first.warning ? DiagnosticSeverity::Warning : DiagnosticSeverity::Error;
    if (first.source == -1)
        return result;
    if (!source)
        internal("invalid hosted resolution result");
    auto text = source(first.source);
    const auto size = static_cast<std::int64_t>(text->text.size());
    const auto position = [&](std::int64_t offset, std::int64_t line, std::int64_t column) {
        if (offset < 0 || offset > size || line < 1 || line > std::numeric_limits<int>::max() || column < 1 ||
            column - 1 > offset)
            internal("invalid hosted resolution result");
        return SourcePosition{static_cast<std::size_t>(offset), static_cast<int>(line), static_cast<int>(column)};
    };
    result.span = {std::move(text),
                   position(first.begin, first.begin_line, first.begin_column),
                   position(first.end, first.end_line, first.end_column)};
    if (result.span.end.offset < result.span.begin.offset || result.span.end.line < result.span.begin.line)
        internal("invalid hosted resolution result");
    return result;
}

PipelineOutput runHostedPipeline(std::uint64_t region,
                                 const hosted_abi::compiler_resolver::Session &session,
                                 std::int64_t root,
                                 std::int64_t diagnostic,
                                 const EmissionRequest &request,
                                 const ReportSource &sources) {
    Result result(region, session, root, diagnostic, options(request));
    wire::Report report{};
    aurora_hosted_pipeline_report(result.data(), &report);
    if (report.stageValue != Stage::complete)
        reject(report);
    const auto &sizes = report.sizesValue;
    PipelineOutput output;
    if (sizes.lintCount < 0 || static_cast<std::uint64_t>(sizes.lintCount) > output.lints.max_size())
        internal("invalid hosted lowering result");
    output.lints.reserve(static_cast<std::size_t>(sizes.lintCount));
    for (std::int64_t at = 0; at < sizes.lintCount; ++at)
        output.lints.push_back(copyReport(
            [&](std::int64_t offset) {
                hosted_abi::compiler_resolver::Report report{};
                aurora_hosted_pipeline_lint(result.data(), at, offset, &report);
                return report;
            },
            sources));
    if (request.emit)
        output.code = result.artifact(x86::Artifact::assembly, sizes.codeBytes);
    if (request.emit && request.stackFacts)
        output.stackFacts = result.artifact(x86::Artifact::stack, sizes.stackBytes);
    if (request.emit && request.abiFacts)
        output.abiFacts = result.artifact(x86::Artifact::abi, sizes.abiBytes);
    return output;
}
} // namespace aurora
