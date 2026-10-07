#pragma once
#include "../diagnostics.hpp"
#include <filesystem>
#include <map>
#include <optional>

namespace aurora::lsp {
using Snapshots = std::map<std::filesystem::path, std::shared_ptr<const SourceText>>;
std::optional<Diagnostic> checkDocument(const std::filesystem::path &path,
                                        const std::vector<std::filesystem::path> &roots,
                                        const Snapshots &snapshots);
// Syntax-only formatting after the shared existing-file admission policy.
std::string formatDocument(const std::filesystem::path &path, const SourceText &snapshot);
} // namespace aurora::lsp
