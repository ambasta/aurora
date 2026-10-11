#pragma once
#include "modules.hpp"
#include "semantics.hpp"

namespace aurora {
// Names retained from resolved declarations for optional compiler-produced ABI facts.
// Physical extents still come only from the validated module/backend.
class AbiDeclaration {
public:
    std::string sourceName;
    std::vector<std::string> members;
};
class AbiDeclarations {
public:
    std::map<std::string, AbiDeclaration> records, enums, functions;
};
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
        ModuleResolver resolver(std::move(graph));
        auto resolved = resolver.resolve();
        AbiDeclarations declarations;
        if (collectAbiDeclarations) {
            const auto name = [](const auto &definition) {
                return definition.scope.empty() ? definition.token.text
                                                : definition.scope + "::" + definition.token.text;
            };
            const auto function = [&](const Function &definition) {
                declarations.functions.emplace(definition.name, AbiDeclaration{name(definition), {}});
            };
            for (const auto &definition : resolved.functions)
                function(definition);
            for (const auto &definition : resolved.classes) {
                AbiDeclaration record{name(definition), {}};
                for (const auto &field : definition.fields)
                    record.members.push_back(field.token.text);
                declarations.records.emplace(definition.name, std::move(record));
                for (const auto &method : definition.methods)
                    function(method);
            }
            for (const auto &definition : resolved.enums) {
                AbiDeclaration enumeration{name(definition), {}};
                for (const auto &value : definition.cases)
                    enumeration.members.push_back(value.text);
                declarations.enums.emplace(definition.name, std::move(enumeration));
            }
        }
        stage = DiagnosticCode::Semantic;
        SemanticAnalyzer analyzer(std::move(resolved), mode);
        auto module = analyzer.analyze();
        return {std::move(module), std::move(identities), analyzer.takeLintDiagnostics(), std::move(declarations)};
    } catch (const Error &error) {
        throw error.withDefaultCode(stage);
    }
}
} // namespace aurora
