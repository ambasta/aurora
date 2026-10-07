#include "server.hpp"
#include <iostream>

int main(int argc, char **argv) {
    try {
        std::vector<std::filesystem::path> roots;
        for (int i = 1; i < argc; ++i) {
            const std::string argument = argv[i];
            if (argument == "--module-root" && i + 1 < argc) {
                if (roots.size() >= 16)
                    throw aurora::lsp::ProtocolError("at most 16 module roots are supported");
                const auto root = std::filesystem::path(argv[++i]);
                aurora::lsp::rejectParentTraversal(root);
                roots.push_back(std::filesystem::absolute(root).lexically_normal());
            } else if (argument == "--help" && argc == 2) {
                std::cerr << "usage: aurora-lsp [--module-root PATH]...\n"
                             "Full-sync UTF-16 diagnostics and formatting over stdio. Existing local files only.\n";
                return 0;
            } else
                throw aurora::lsp::ProtocolError("usage: aurora-lsp [--module-root PATH]...");
        }
        aurora::lsp::Session session(
            [&](const auto &path, const aurora::lsp::Snapshots &snapshots) -> std::optional<aurora::Diagnostic> {
                return aurora::lsp::checkDocument(path, roots, snapshots);
            },
            std::cout,
            std::cerr);
        return session.run(std::cin);
    } catch (const aurora::lsp::ProtocolError &failure) {
        std::cerr << "aurora-lsp: " << failure.what() << '\n';
        return 1;
    } catch (const std::exception &) {
        std::cerr << "aurora-lsp: startup or internal failure\n";
        return 1;
    }
}
