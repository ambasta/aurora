#pragma once
#include "modules.hpp"

namespace aurora {
// Both emitting and check-only clients cross the same resolver, lifetime/type
// analysis and verified-IR boundary. Checking does not construct an output writer.
class CheckedSource {
public:
    std::set<host::Identity> sourceIdentities;
    std::vector<Diagnostic> lintDiagnostics;
    // Present only when requested: emitted code, stack facts and ABI facts.
    std::string code, stackFacts, abiFacts;
};
inline CheckedSource checkSource(const std::filesystem::path &input,
                                 const std::vector<std::filesystem::path> &roots = {},
                                 const SourceOverlays &overlays = {},
                                 AnalysisMode mode = AnalysisMode::Check,
                                 const EmissionRequest &request = {}) {
    auto stage = DiagnosticCode::Module;
    try {
        ModuleLoader loader(roots, overlays);
        auto graph = loader.load(input);
        auto identities = graph.sourceIdentities;
        auto resolved = graph.resolve(mode, request);
        return {std::move(identities),
                std::move(resolved.lintDiagnostics),
                std::move(resolved.code),
                std::move(resolved.stackFacts),
                std::move(resolved.abiFacts)};
    } catch (const Error &error) {
        throw error.withDefaultCode(stage);
    }
}
} // namespace aurora
