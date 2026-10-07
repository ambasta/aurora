#include "check.hpp"
#include "../frontend.hpp"
#include "../format.hpp"

namespace aurora::lsp {
std::vector<Diagnostic> checkDocument(const std::filesystem::path &path,
                                      const std::vector<std::filesystem::path> &roots,
                                      const Snapshots &snapshots,
                                      bool lint) {
    try {
        return checkSource(path, roots, snapshots, lint ? AnalysisMode::Lint : AnalysisMode::Check).lintDiagnostics;
    } catch (const Error &error) {
        return {error.diagnostic};
    }
}
std::string formatDocument(const std::filesystem::path &path, const SourceText &snapshot) {
    // Reauthorize the named file at request time, but never read disk bytes in
    // place of the accepted editor snapshot. Imports are irrelevant to layout.
    try {
        const auto file = host::SourceFile::explicitPath(path);
        (void)file;
    } catch (const Error &error) {
        throw error.withDefaultCode(DiagnosticCode::Module);
    }
    return format::source(snapshot.text, path.string()).text;
}
} // namespace aurora::lsp
