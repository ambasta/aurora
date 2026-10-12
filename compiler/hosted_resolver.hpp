#pragma once
#include "syntax.hpp"
#include <cstddef>
#include <memory>
#include <vector>

namespace aurora {
// Only copied source header metadata leaves a parsed module before resolution.
class HostedModule {
public:
    std::size_t id = 0;
    std::string moduleName;
    bool interfaceUnit = false;
    std::vector<Token> imports;
};

// Owns the Aurora graph session and the immutable diagnostic source snapshots.
// File opening and import graph authority stay in ModuleLoader.
class HostedResolution {
    class Impl;
    std::unique_ptr<Impl> implementation;

public:
    HostedResolution();
    ~HostedResolution();
    HostedResolution(const HostedResolution &) = delete;
    HostedResolution &operator=(const HostedResolution &) = delete;
    HostedModule add(std::shared_ptr<const SourceText> source);
    Program resolve(const std::vector<std::size_t> &dependencyOrder, std::size_t root);
};
} // namespace aurora
