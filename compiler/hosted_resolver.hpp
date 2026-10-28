#pragma once
#include "hosted_pipeline.hpp"
#include <cstddef>
#include <memory>
#include <optional>
#include <vector>

namespace aurora {
enum class AnalysisMode {
    Check,
    Lint
};
// A module Aurora admitted, by its index in the graph.
class HostedModule {
public:
    std::size_t id = 0;
};

// An import Aurora requests: its normalized name, the relative module file
// path it maps to, and whether the name is reserved to the compiler's runtime
// root (aurora.* outside the compiler's own sources).
class HostedImport {
public:
    std::string name, path;
    bool reserved = false;
};

// The diagnostic Aurora renders for the first rejection of a source admission;
// `stop` is the stop of the grammar entry that reported a grammar status.
Diagnostic
sourceDiagnostic(const std::shared_ptr<const SourceText> &source,
                 const hosted_abi::compiler_resolver::SourceResult &result,
                 hosted_abi::compiler_parser::Stop stop = hosted_abi::compiler_parser::Stop::module_definition);

// Owns the Aurora graph session and the immutable diagnostic source snapshots.
// Aurora loads each source, owns graph traversal and module policy and renders
// every rejection; ModuleLoader retains file-opening authority.
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
    PipelineOutput
    resolve(std::size_t root, AnalysisMode mode = AnalysisMode::Check, const EmissionRequest &request = {});
    // Explicit-order compatibility API for already-admitted in-memory modules.
    PipelineOutput resolve(const std::vector<std::size_t> &dependencyOrder,
                           std::size_t root,
                           AnalysisMode mode = AnalysisMode::Check,
                           const EmissionRequest &request = {});
};
} // namespace aurora
