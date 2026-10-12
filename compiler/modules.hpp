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
    class Unit {
    public:
        HostedModule program;
        std::filesystem::path path;
    };
    class Graph {
    public:
        std::map<std::string, std::unique_ptr<Unit>> units;
        std::vector<std::string> order;
        std::string root;
        std::set<host::Identity> sourceIdentities;
        std::unique_ptr<HostedResolution> resolution = std::make_unique<HostedResolution>();
        Program resolve() {
            std::vector<std::size_t> modules;
            modules.reserve(order.size());
            for (const auto &name : order)
                modules.push_back(units.at(name)->program.id);
            return resolution->resolve(modules, units.at(root)->program.id);
        }
    };

private:
    static constexpr std::size_t maxFileBytes = 1024 * 1024;
    static constexpr std::size_t maxGraphBytes = 4 * 1024 * 1024;
    std::vector<host::Directory> roots;
    SourceOverlays overlays;
    std::size_t bytesRead = 0;
    Graph graph;
    std::set<std::string> active;
    std::shared_ptr<const SourceText> read(host::SourceFile file) {
        graph.sourceIdentities.insert(file.identity);
        const auto remaining = maxGraphBytes - bytesRead;
        try {
            const auto overlay = overlays.empty()
                                     ? overlays.end()
                                     : overlays.find(std::filesystem::absolute(file.displayPath).lexically_normal());
            std::shared_ptr<const SourceText> snapshot;
            if (overlay != overlays.end()) {
                snapshot = overlay->second;
                if (snapshot->text.size() > std::min(maxFileBytes, remaining))
                    throw host::ReadLimit();
            } else {
                auto contents = file.readAtMost(std::min(maxFileBytes, remaining));
                snapshot = std::make_shared<const SourceText>(file.displayPath.string(), std::move(contents));
            }
            bytesRead += snapshot->text.size();
            return snapshot;
        } catch (const host::ReadLimit &) {
            throw Error(remaining < maxFileBytes ? "module graph exceeds 4194304 bytes"
                                                 : "module file exceeds 1048576 bytes");
        }
    }
    host::SourceFile resolve(const std::string &name) {
        if (roots.empty())
            throw Error("imports require an explicit --module-root");
        std::filesystem::path relative;
        std::size_t start = 0, components = 0;
        while (start < name.size()) {
            auto end = name.find('.', start);
            const auto part = name.substr(start, end == std::string::npos ? name.size() - start : end - start);
            if (part.empty() || part.size() > 128 || ++components > 32)
                throw Error("invalid or excessive module name");
            for (char c : part)
                if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_'))
                    throw Error("invalid module path component");
            relative /= part;
            if (end == std::string::npos)
                break;
            start = end + 1;
        }
        relative += ".au";
        std::vector<host::SourceFile> found;
        for (const auto &root : roots) {
            auto file = root.open(relative);
            if (file)
                found.push_back(std::move(*file));
        }
        if (found.empty())
            throw Error("module not found in explicit roots: " + name);
        if (found.size() != 1)
            throw Error("ambiguous module found in multiple roots: " + name);
        return std::move(found.front());
    }
    void visit(const std::string &name, int depth) {
        if (depth > 16)
            throw Error("module import depth exceeds 16");
        if (active.contains(name))
            throw Error("module import cycle involving " + name);
        if (std::find(graph.order.begin(), graph.order.end(), name) != graph.order.end())
            return;
        active.insert(name);
        auto &unit = *graph.units.at(name);
        std::set<std::string> imports;
        for (const auto &import : unit.program.imports) {
            if (!imports.insert(import.text).second)
                throw Error("duplicate import in " + name + ": " + import.text);
            if (!graph.units.contains(import.text)) {
                if (graph.units.size() >= 64)
                    throw Error("module graph exceeds 64 files");
                auto imported = std::make_unique<Unit>();
                auto file = resolve(import.text);
                imported->path = file.displayPath;
                try {
                    imported->program = graph.resolution->add(read(std::move(file)));
                } catch (const Error &error) {
                    throw error.withContext("module " + import.text + ": ");
                }
                if (imported->program.moduleName != import.text)
                    throw Error("module header mismatch: expected " + import.text + ", got " +
                                imported->program.moduleName);
                if (!imported->program.interfaceUnit)
                    throw Error("imported module requires an export module interface: " + import.text);
                graph.units.emplace(import.text, std::move(imported));
            }
            visit(import.text, depth + 1);
        }
        active.erase(name);
        graph.order.push_back(name);
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
        auto root = std::make_unique<Unit>();
        root->path = rootPath;
        root->program = graph.resolution->add(read(host::SourceFile::explicitPath(rootPath)));
        graph.root = root->program.moduleName;
        graph.units.emplace(graph.root, std::move(root));
        visit(graph.root, 0);
        return std::move(graph);
    }
};

} // namespace aurora
