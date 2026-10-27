#pragma once
#include "host_sources.hpp"
#include "lexer.hpp"
#include "hosted_resolver.hpp"
#include <filesystem>
#include <fstream>
#include <map>
#include <set>

namespace aurora {
// Keys and snapshot paths are absolute, lexically normalized paths. Overrides
// replace bytes only after the existing source-opening policy authorizes a file.
using SourceOverlays = std::map<std::filesystem::path, std::shared_ptr<const SourceText>>;
// Host bootstrap file reads are limited to named modules beneath explicit
// roots. No source construct performs arbitrary filesystem or network
// operations.
class ModuleLoader {
public:
    class Graph {
    public:
        std::size_t root = 0;
        std::set<host::Identity> sourceIdentities;
        std::unique_ptr<HostedResolution> resolution = std::make_unique<HostedResolution>();
        HostedResolvedSource resolve(AnalysisMode mode = AnalysisMode::Check, bool collectAbiDeclarations = false) {
            return resolution->resolve(root, mode, collectAbiDeclarations);
        }
    };

private:
    // Overlay limits; Aurora charges every captured source against the same
    // per-file and per-graph limits, which the host capture bound covers.
    static constexpr std::size_t maxFileBytes = 1024 * 1024;
    static constexpr std::size_t maxGraphBytes = 4 * 1024 * 1024;
    std::vector<host::Directory> roots;
    SourceOverlays overlays;
    Graph graph;
    std::shared_ptr<const SourceText> read(host::SourceFile file) {
        graph.sourceIdentities.insert(file.identity);
        if (!overlays.empty()) {
            const auto overlay = overlays.find(std::filesystem::absolute(file.displayPath).lexically_normal());
            if (overlay != overlays.end())
                return overlay->second;
        }
        auto contents = file.capture(maxFileBytes);
        return std::make_shared<const SourceText>(file.displayPath.string(), std::move(contents));
    }
    host::SourceFile open(const HostedImport &request) {
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
    explicit ModuleLoader(const std::vector<std::filesystem::path> &searchRoots, SourceOverlays sourceOverlays = {})
        : overlays(std::move(sourceOverlays)) {
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
    Graph load(const std::filesystem::path &rootPath) {
        graph.root = graph.resolution->add(read(host::SourceFile::explicitPath(rootPath))).id;
        while (const auto request = graph.resolution->nextImport(graph.root, roots.size())) {
            auto file = open(*request);
            try {
                graph.resolution->add(read(std::move(file)));
            } catch (const Error &error) {
                throw error.withContext("module " + request->name + ": ");
            }
        }
        return std::move(graph);
    }
};

} // namespace aurora
