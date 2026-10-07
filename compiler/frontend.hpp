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
};
inline CheckedSource checkSource(const std::filesystem::path &input,
                                 const std::vector<std::filesystem::path> &roots = {},
                                 const SourceOverlays &overlays = {}) {
    auto stage = DiagnosticCode::Module;
    try {
        ModuleLoader loader(roots, overlays);
        auto graph = loader.load(input);
        auto identities = graph.sourceIdentities;
        ModuleResolver resolver(std::move(graph));
        auto resolved = resolver.resolve();
        stage = DiagnosticCode::Semantic;
        SemanticAnalyzer analyzer(std::move(resolved));
        return {analyzer.analyze(), std::move(identities)};
    } catch (const Error &error) {
        throw error.withDefaultCode(stage);
    }
}
} // namespace aurora
