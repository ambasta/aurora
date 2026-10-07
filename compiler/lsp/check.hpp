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
} // namespace aurora::lsp
