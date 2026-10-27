#pragma once
#include "ir.hpp"
#include <cstddef>
#include <map>
#include <memory>
#include <optional>
#include <vector>

namespace aurora {
enum class AnalysisMode {
    Check,
    Lint
};
// Source declarations are observations only. Physical extents remain authority
// of the independently validated module and backend.
class AbiDeclaration {
public:
    std::string sourceName;
    std::vector<std::string> members;
};
class AbiDeclarations {
public:
    std::map<std::string, AbiDeclaration> records, enums, functions;
};
struct HostedResolvedSource {
    ir::ValidatedModule module;
    std::vector<Diagnostic> lintDiagnostics;
    AbiDeclarations abiDeclarations;
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
    resolve(std::size_t root, AnalysisMode mode = AnalysisMode::Check, bool collectAbiDeclarations = false);
    // Explicit-order compatibility API for already-admitted in-memory modules.
    HostedResolvedSource resolve(const std::vector<std::size_t> &dependencyOrder,
                                 std::size_t root,
                                 AnalysisMode mode = AnalysisMode::Check,
                                 bool collectAbiDeclarations = false);
};
} // namespace aurora
