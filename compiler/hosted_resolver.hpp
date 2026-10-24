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
// Only copied source header metadata leaves a parsed module before resolution.
class HostedModule {
public:
    std::size_t id = 0;
    std::string moduleName;
    bool interfaceUnit = false;
    std::vector<Token> imports;
};

// Owns the Aurora graph session and the immutable diagnostic source snapshots.
// Aurora owns graph traversal; ModuleLoader retains file-opening authority.
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
    std::optional<std::string> nextImport(std::size_t root);
    HostedResolvedSource
    resolve(std::size_t root, AnalysisMode mode = AnalysisMode::Check, bool collectAbiDeclarations = false);
    // Explicit-order compatibility API for already-admitted in-memory modules.
    HostedResolvedSource resolve(const std::vector<std::size_t> &dependencyOrder,
                                 std::size_t root,
                                 AnalysisMode mode = AnalysisMode::Check,
                                 bool collectAbiDeclarations = false);
};
} // namespace aurora
