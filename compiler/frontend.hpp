#pragma once
#include "modules.hpp"
#include "semantics.hpp"

namespace aurora {
// Both emitting and check-only clients cross the same resolver, lifetime/type
// analysis and verified-IR boundary. Checking does not construct an output writer.
class CheckedSource {
public:
    ir::ValidatedModule module;
    std::set<host::Identity> sourceIdentities;
    std::vector<Diagnostic> lintDiagnostics;
};
inline CheckedSource checkSource(const std::filesystem::path &input,
                                 const std::vector<std::filesystem::path> &roots = {},
                                 const SourceOverlays &overlays = {},
                                 AnalysisMode mode = AnalysisMode::Check) {
    auto stage = DiagnosticCode::Module;
    try {
        ModuleLoader loader(roots, overlays);
        auto graph = loader.load(input);
        auto identities = graph.sourceIdentities;
        ModuleResolver resolver(std::move(graph));
        auto resolved = resolver.resolve();
        stage = DiagnosticCode::Semantic;
        SemanticAnalyzer analyzer(std::move(resolved), mode);
        auto module = analyzer.analyze();
        return {std::move(module), std::move(identities), analyzer.takeLintDiagnostics()};
    } catch (const Error &error) {
        throw error.withDefaultCode(stage);
    }
}
} // namespace aurora
