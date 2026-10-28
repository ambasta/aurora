#pragma once
#include "hosted_parser_abi.hpp"
#include "hosted_pipeline.hpp"
#include "types.hpp"
#include <cstddef>
#include <memory>
#include <optional>
#include <vector>

namespace aurora {
enum class AnalysisMode {
    Check,
    Lint
};
// Lint warnings and the requested artifacts of one verified compilation.
struct HostedResolvedSource {
    std::vector<Diagnostic> lintDiagnostics;
    std::string code, stackFacts, abiFacts;
};
// Only the copied module header leaves an admitted source before resolution;
// Aurora keeps its imports and finds them by name.
class HostedModule {
public:
    std::size_t id = 0;
    std::string moduleName;
};

// An import Aurora requests: its normalized name and the relative module file
// path it maps to.
class HostedImport {
public:
    std::string name, path;
};

// The diagnostic Aurora renders for the first rejection of a source admission;
// `stop` is the stop of the grammar entry that reported a grammar status.
Diagnostic sourceDiagnostic(const std::shared_ptr<const SourceText> &source,
                            const hosted_abi::compiler_resolver::SourceResult &result,
                            hosted_parser::Stop stop = hosted_parser::Stop::module_definition);
// Throws that diagnostic for a rejected admission; returns for an admitted module.
void rejectSource(const std::shared_ptr<const SourceText> &source,
                  const hosted_abi::compiler_resolver::SourceResult &result);

// Owns the Aurora graph session and the immutable diagnostic source snapshots.
// Aurora owns graph traversal and module policy; ModuleLoader retains
// file-opening authority.
class HostedResolution {
    class Impl;
    std::unique_ptr<Impl> implementation;

public:
    HostedResolution();
    ~HostedResolution();
    HostedResolution(const HostedResolution &) = delete;
    HostedResolution &operator=(const HostedResolution &) = delete;
    HostedModule add(std::shared_ptr<const SourceText> source);
    // Advances source-owned traversal to its next host read, or completion.
    std::optional<HostedImport> nextImport(std::size_t root, std::size_t moduleRoots);
    HostedResolvedSource
    resolve(std::size_t root, AnalysisMode mode = AnalysisMode::Check, const EmissionRequest &request = {});
    // Explicit-order compatibility API for already-admitted in-memory modules.
    HostedResolvedSource resolve(const std::vector<std::size_t> &dependencyOrder,
                                 std::size_t root,
                                 AnalysisMode mode = AnalysisMode::Check,
                                 const EmissionRequest &request = {});
};
} // namespace aurora
