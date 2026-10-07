#include "check.hpp"
#include "../frontend.hpp"

namespace aurora::lsp {
std::optional<Diagnostic> checkDocument(const std::filesystem::path &path,
                                        const std::vector<std::filesystem::path> &roots,
                                        const Snapshots &snapshots) {
    try {
        (void)checkSource(path, roots, snapshots);
    } catch (const Error &error) {
        return error.diagnostic;
    }
    return {};
}
} // namespace aurora::lsp
