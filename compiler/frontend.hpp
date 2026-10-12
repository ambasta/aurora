#pragma once
#include "modules.hpp"

namespace aurora {
// Both emitting and check-only clients cross the same resolver, lifetime/type
// analysis and verified-IR boundary. Checking does not construct an output writer.
class CheckedSource {
public:
    ir::ValidatedModule module;
    std::set<host::Identity> sourceIdentities;
    std::vector<Diagnostic> lintDiagnostics;
    AbiDeclarations abiDeclarations;
};
inline CheckedSource checkSource(const std::filesystem::path &input,
                                 const std::vector<std::filesystem::path> &roots = {},
                                 const SourceOverlays &overlays = {},
                                 AnalysisMode mode = AnalysisMode::Check,
                                 bool collectAbiDeclarations = false) {
    auto stage = DiagnosticCode::Module;
    try {
        ModuleLoader loader(roots, overlays);
        auto graph = loader.load(input);
        auto identities = graph.sourceIdentities;
        auto resolved = graph.resolve(mode, collectAbiDeclarations);
        return {std::move(resolved.module),
                std::move(identities),
                std::move(resolved.lintDiagnostics),
                std::move(resolved.abiDeclarations)};
    } catch (const Error &error) {
        throw error.withDefaultCode(stage);
    }
}
} // namespace aurora
