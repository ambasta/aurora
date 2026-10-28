#pragma once
#include "diagnostics.hpp"
#include "hosted_frontend_abi.hpp"
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <vector>

namespace aurora {
// These choices affect symbol visibility and retained reflection helpers only.
enum class SymbolBinding {
    Default,
    Local
};
enum class ReflectionEmission {
    All,
    Referenced
};
enum class CodeEmission {
    Assembly,
    Object
};
// What a compilation produces after verification; without emit it only checks.
class EmissionRequest {
public:
    bool emit = false;
    SymbolBinding binding = SymbolBinding::Default;
    ReflectionEmission reflection = ReflectionEmission::All;
    CodeEmission format = CodeEmission::Assembly;
    bool stackFacts = false;
    bool abiFacts = false;
};
class PipelineOutput {
public:
    // Unread-local warnings, ordered by source offset.
    std::vector<Diagnostic> lints;
    std::string code, stackFacts, abiFacts;
};
// The source snapshot of a diagnostic's source index.
using ReportSource = std::function<std::shared_ptr<const SourceText>(std::int64_t)>;
// Copies one diagnostic Aurora rendered; `read` returns its Report from a
// message offset on. Throws Internal on a malformed or inconsistent report.
Diagnostic copyReport(const std::function<hosted_abi::compiler_resolver::Report(std::int64_t)> &read,
                      const ReportSource &source);

// One Aurora call projects the lowered Session, admits, structures and verifies
// every function, checks the call graph, publishes and emits the requested
// artifacts. It consumes `session`, an owner in `region` the caller must then
// treat as moved. The host copies the result out, with lint warnings located
// in `sources`, or renders its first failure with the former message and code.
PipelineOutput runHostedPipeline(std::uint64_t region,
                                 const hosted_abi::compiler_resolver::Session &session,
                                 std::int64_t root,
                                 std::int64_t diagnostic,
                                 const EmissionRequest &request,
                                 const ReportSource &sources = {});
} // namespace aurora
