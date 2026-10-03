#include "host_sources.hpp"
#include <atomic>
#include <fstream>
#include <iostream>
#include <thread>

using namespace aurora;
namespace fs = std::filesystem;
namespace {
void require(bool condition, const std::string &message) {
    if (!condition)
        throw Error(message);
}
void write(const fs::path &path, const std::string &value) {
    std::ofstream output(path);
    output << value;
    if (!output)
        throw Error("fixture write failed");
}
template <class Action> void rejects(const std::string &name, Action action) {
    try {
        action();
    } catch (const Error &) {
        std::cout << "PASS source adapter " << name << '\n';
        return;
    }
    throw Error(name + ": policy unexpectedly allowed operation");
}
} // namespace
int main(int argc, char **argv) {
    try {
        require(argc == 2, "pass one owned temporary fixture directory");
        const fs::path base = argv[1];
        const auto original = base / "root", pinned = base / "pinned", outside = base / "outside";
        fs::create_directories(original);
        fs::create_directories(outside);
        write(original / "good.au", "inside");
        write(outside / "evil.au", "outside");
        host::Directory root(original);
        require(root.open("good.au")->readAtMost(6) == "inside", "bounded exact read");
        std::cout << "PASS source adapter exact bounded read\n";
        rejects("read byte cap", [&] { root.open("good.au")->readAtMost(5); });
        rejects("excessive read request",
                [&] { root.open("good.au")->readAtMost(static_cast<std::size_t>(-1)); });
        rejects("relative parent escape", [&] { root.open("../outside/evil.au"); });
        rejects("absolute escape", [&] { root.open(outside / "evil.au"); });
        rejects("directory not a source file", [&] { root.open("."); });
        fs::create_symlink("good.au", original / "inside-link.au");
        fs::create_symlink(outside / "evil.au", original / "escape.au");
        rejects("contained symlink", [&] { root.open("inside-link.au"); });
        rejects("external symlink", [&] { root.open("escape.au"); });
        rejects("explicit root source symlink",
                [&] { host::SourceFile::explicitPath(original / "inside-link.au"); });
        require(!root.open("missing.au"), "missing module should remain missing");
        std::cout << "PASS source adapter missing module\n";

        // The authority is the retained descriptor, not the directory name supplied earlier.
        fs::rename(original, pinned);
        fs::create_directory_symlink(outside, original);
        require(root.open("good.au")->readAtMost(32) == "inside",
                "root replacement changed authority");
        std::cout << "PASS source adapter pinned root survives replacement\n";
        rejects("new symlink root rejected", [&] { host::Directory replacement(original); });

        // Atomic directory-entry replacement races a safe hard link against an escaping
        // symlink. Every successful open/read must still return the inside inode.
        fs::create_hard_link(pinned / "good.au", pinned / "race.au");
        std::atomic<bool> failed = false;
        std::thread writer([&] {
            try {
                for (int iteration = 0; iteration < 400; ++iteration) {
                    const auto next = pinned / "next.au";
                    fs::create_symlink(outside / "evil.au", next);
                    fs::rename(next, pinned / "race.au");
                    fs::create_hard_link(pinned / "good.au", next);
                    fs::rename(next, pinned / "race.au");
                }
            } catch (...) {
                failed = true;
            }
        });
        int safe = 0, denied = 0;
        for (int iteration = 0; iteration < 800; ++iteration) {
            try {
                auto source = root.open("race.au");
                if (source) {
                    if (source->readAtMost(32) != "inside")
                        failed = true;
                    ++safe;
                } else
                    ++denied;
            } catch (const Error &) {
                ++denied;
            }
        }
        writer.join();
        require(!failed, "replacement race escaped or fixture mutation failed");
        require(safe > 0, "race failed to exercise a successful safe read");
        std::cout << "PASS source adapter replacement race: safe=" << safe << ", denied=" << denied
                  << '\n';
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
