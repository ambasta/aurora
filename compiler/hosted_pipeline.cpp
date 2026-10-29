#include "hosted_pipeline.hpp"
#include <algorithm>
#include <tuple>

namespace aurora {
namespace {
namespace wire = hosted_abi::compiler_pipeline;
namespace x86 = hosted_abi::compiler_x86;
constexpr std::int64_t artifactLimit = 64 * 1024 * 1024;

[[noreturn]] void internal(const char *message) {
    throw Error(DiagnosticCode::Internal, message);
}
} // namespace

std::uint64_t pipelineOptions(const EmissionRequest &request) {
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
    if (request.listing)
        result |= 64;
    if (request.kernelTarget)
        result |= 128;
    return result;
}

Diagnostic copyReport(const std::function<hosted_abi::compiler_resolver::Report(std::int64_t)> &read,
                      const ReportSource &source) {
    const auto first = read(0);
    constexpr auto chunk = static_cast<std::int64_t>(std::tuple_size_v<decltype(first.payload)>);
    Diagnostic result;
    for (auto report = first;; report = read(static_cast<std::int64_t>(result.message.size()))) {
        if (report.byteCount < 0 || report.byteCount > chunk || result.message.size() > artifactLimit)
            internal("invalid hosted resolution result");
        result.message.append(reinterpret_cast<const char *>(report.payload.data()),
                              static_cast<std::size_t>(report.byteCount));
        if (report.byteCount < chunk)
            break;
    }
    result.code = static_cast<DiagnosticCode>(static_cast<int>(first.family));
    result.severity = first.warning ? DiagnosticSeverity::Warning : DiagnosticSeverity::Error;
    if (first.source < 0)
        return result;
    if (!source)
        internal("invalid hosted resolution result");
    const auto position = [](std::int64_t offset, std::int64_t line, std::int64_t column) {
        return SourcePosition{static_cast<std::size_t>(offset), static_cast<int>(line), static_cast<int>(column)};
    };
    result.span = {source(first.source),
                   position(first.begin, first.begin_line, first.begin_column),
                   position(first.end, first.end_line, first.end_column)};
    return result;
}

PipelineResult::PipelineResult(std::uint64_t region) {
    release_.region = region;
}
PipelineResult::~PipelineResult() {
    aurora_hosted_pipeline_release(&release_);
}
void *PipelineResult::data() {
    return release_.result.storage.data();
}
wire::Report PipelineResult::report() {
    wire::Report report{};
    aurora_hosted_pipeline_report(data(), &report);
    return report;
}
namespace {
std::string artifact(PipelineResult &result, x86::Artifact kind, std::int64_t size) {
    if (size < 0 || (kind != x86::Artifact::stack && size > artifactLimit))
        internal("invalid hosted x86 emission transport");
    std::string text(static_cast<std::size_t>(size), '\0');
    for (std::int64_t offset = 0; offset < size;) {
        x86::EmitChunk chunk{};
        aurora_hosted_pipeline_chunk(result.data(), static_cast<std::int64_t>(kind), offset, &chunk);
        if (chunk.byteCount <= 0 || chunk.byteCount > 512 || chunk.byteCount > size - offset)
            internal("invalid hosted x86 emission transport");
        std::copy_n(chunk.payload.begin(), static_cast<std::size_t>(chunk.byteCount), text.begin() + offset);
        offset += chunk.byteCount;
    }
    return text;
}
} // namespace
PipelineOutput
PipelineResult::output(const wire::Report &report, const EmissionRequest &request, const ReportSource &sources) {
    // An incomplete run's only diagnostic is its failure; a complete run's are its lint warnings.
    const auto diagnostic = [&](std::int64_t index) {
        return copyReport(
            [&](std::int64_t offset) {
                hosted_abi::compiler_resolver::Report part{};
                aurora_hosted_pipeline_diagnostic(data(), index, offset, &part);
                return part;
            },
            sources);
    };
    if (report.stageValue != wire::Stage::complete)
        throw Error(diagnostic(0));
    const auto &sizes = report.sizesValue;
    PipelineOutput output;
    for (std::int64_t at = 0; at < sizes.lintCount; ++at)
        output.lints.push_back(diagnostic(at));
    if (request.emit || request.listing)
        output.code = artifact(*this, x86::Artifact::assembly, sizes.codeBytes);
    if (request.emit && request.stackFacts)
        output.stackFacts = artifact(*this, x86::Artifact::stack, sizes.stackBytes);
    if (request.emit && request.abiFacts)
        output.abiFacts = artifact(*this, x86::Artifact::abi, sizes.abiBytes);
    return output;
}

PipelineOutput runHostedPipeline(std::uint64_t region,
                                 const hosted_abi::compiler_resolver::Session &session,
                                 std::int64_t root,
                                 std::int64_t diagnostic,
                                 const EmissionRequest &request,
                                 const ReportSource &sources) {
    PipelineResult result(region);
    hosted_abi::PipelineRun run{};
    run.region = region;
    run.session = session;
    run.root = root;
    run.diagnostic = diagnostic;
    run.options = pipelineOptions(request);
    aurora_hosted_pipeline_run(&run, result.data());
    return result.output(result.report(), request, sources);
}
} // namespace aurora
