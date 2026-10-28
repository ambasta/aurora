#pragma once
#include "host_sources.hpp"
#include "hosted_resolver.hpp"
#include <filesystem>
#include <map>
#include <set>

// The compiler's runtime root, fixed when aurorac is configured (runtime/linux
// of its source tree); empty leaves every reserved import unresolvable.
#ifndef AURORA_RUNTIME_ROOT
#define AURORA_RUNTIME_ROOT ""
#endif

namespace aurora {
// Keys and snapshot paths are absolute, lexically normalized paths. Overrides
// replace bytes only after the existing source-opening policy authorizes a file.
using SourceOverlays = std::map<std::filesystem::path, std::shared_ptr<const SourceText>>;
// Both emitting and check-only clients cross the same resolver, lifetime/type
// analysis and verified-IR boundary. Checking does not construct an output writer.
class CheckedSource {
public:
    std::set<host::Identity> sourceIdentities;
    std::vector<Diagnostic> lintDiagnostics;
    // Present only when requested: emitted code, stack facts and ABI facts.
    std::string code, stackFacts, abiFacts;
};
// Host bootstrap file reads are limited to named modules beneath explicit
// roots. No source construct performs arbitrary filesystem or network
// operations. Aurora decides which module each import names and checks every
// byte limit; the host finds that file in exactly one root and reads it. A name
// Aurora reserves (aurora.host and the other compiler-owned aurora.* modules)
// is read only from the compiler's own runtime root, never from a module root
// or an overlay, and is an error if any module root also holds it.
class ModuleLoader {
    // Overlay limits; Aurora charges every captured source against the same
    // per-file and per-graph limits, which the host capture bound covers.
    static constexpr std::size_t maxFileBytes = 1024 * 1024;
    static constexpr std::size_t maxGraphBytes = 4 * 1024 * 1024;
    std::vector<host::Directory> roots;
    std::filesystem::path runtimePath;
    std::optional<host::Directory> runtime;
    SourceOverlays overlays;
    std::set<host::Identity> identities;
    std::shared_ptr<const SourceText> read(host::SourceFile file, bool reserved = false) {
        identities.insert(file.identity);
        if (!overlays.empty() && !reserved) {
            const auto overlay = overlays.find(std::filesystem::absolute(file.displayPath).lexically_normal());
            if (overlay != overlays.end())
                return overlay->second;
        }
        auto contents = file.capture(maxFileBytes);
        return std::make_shared<const SourceText>(file.displayPath.string(), std::move(contents));
    }
    host::SourceFile open(const HostedImport &request) {
        if (request.reserved) {
            for (const auto &root : roots)
                if (root.open(request.path))
                    throw Error("reserved compiler module found in a module root: " + request.name +
                                " (aurora.* modules load only from the compiler's runtime root)");
            if (runtimePath.empty())
                throw Error("reserved compiler module requires the compiler's runtime root: " + request.name);
            if (!runtime)
                runtime.emplace(runtimePath);
            auto file = runtime->open(request.path);
            if (!file)
                throw Error("module not found in the compiler's runtime root: " + request.name);
            return std::move(*file);
        }
        std::vector<host::SourceFile> found;
        for (const auto &root : roots) {
            auto file = root.open(request.path);
            if (file)
                found.push_back(std::move(*file));
        }
        if (found.empty())
            throw Error("module not found in explicit roots: " + request.name);
        if (found.size() != 1)
            throw Error("ambiguous module found in multiple roots: " + request.name);
        return std::move(found.front());
    }

public:
    explicit ModuleLoader(const std::vector<std::filesystem::path> &searchRoots,
                          SourceOverlays sourceOverlays = {},
                          std::filesystem::path runtimeRoot = {})
        : runtimePath(std::move(runtimeRoot)), overlays(std::move(sourceOverlays)) {
        if (overlays.size() > 64)
            throw Error("source overlays exceed 64 files");
        std::size_t overlayBytes = 0;
        for (const auto &[path, snapshot] : overlays) {
            if (!snapshot || !path.is_absolute() || path.native() != path.lexically_normal().native() ||
                path.string().find('\0') != std::string::npos || snapshot->path != path.string())
                throw Error("source overlay requires an absolute normalized path matching its snapshot");
            if (snapshot->text.size() > maxFileBytes)
                throw Error("source overlay exceeds 1048576 bytes");
            if (snapshot->text.size() > maxGraphBytes - overlayBytes)
                throw Error("source overlays exceed 4194304 bytes");
            overlayBytes += snapshot->text.size();
        }
        if (searchRoots.size() > 16)
            throw Error("at most 16 explicit module roots are supported");
        std::set<std::pair<std::uint64_t, std::uint64_t>> unique;
        for (const auto &path : searchRoots) {
            host::Directory root(path);
            if (!unique.insert(root.identity).second)
                throw Error("duplicate module search root");
            roots.push_back(std::move(root));
        }
    }
    // Loads the graph of the root file and runs the requested compilation.
    CheckedSource check(const std::filesystem::path &rootPath, AnalysisMode mode, const EmissionRequest &request) {
        HostedResolution resolution;
        const auto root = resolution.add(read(host::SourceFile::explicitPath(rootPath))).id;
        while (const auto wanted = resolution.nextImport(root, roots.size())) {
            auto file = open(*wanted);
            std::shared_ptr<const SourceText> source;
            try {
                source = read(std::move(file), wanted->reserved);
            } catch (const Error &error) {
                throw error.withContext("module " + wanted->name + ": ");
            }
            resolution.add(std::move(source));
        }
        auto output = resolution.resolve(root, mode, request);
        return {std::move(identities),
                std::move(output.lints),
                std::move(output.code),
                std::move(output.stackFacts),
                std::move(output.abiFacts)};
    }
};
inline CheckedSource checkSource(const std::filesystem::path &input,
                                 const std::vector<std::filesystem::path> &roots = {},
                                 const SourceOverlays &overlays = {},
                                 AnalysisMode mode = AnalysisMode::Check,
                                 const EmissionRequest &request = {},
                                 const std::filesystem::path &runtimeRoot = {}) {
    try {
        return ModuleLoader(roots, overlays, runtimeRoot).check(input, mode, request);
    } catch (const Error &error) {
        throw error.withDefaultCode(DiagnosticCode::Module);
    }
}
} // namespace aurora
