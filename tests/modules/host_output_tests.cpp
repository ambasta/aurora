#include "host_sources.hpp"
#include <csignal>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sys/resource.h>
#include <sys/wait.h>

using namespace aurora;
namespace fs = std::filesystem;
namespace {
int passed = 0;
void require(bool value, const std::string &message) {
    if (!value)
        throw Error(message);
}
void writeFile(const fs::path &path, const std::string &value) {
    std::ofstream stream(path);
    stream << value;
    if (!stream)
        throw Error("fixture write failed");
}
std::string readFile(const fs::path &path) {
    std::ifstream stream(path);
    return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
}
void pass(const std::string &name) {
    ++passed;
    std::cout << "PASS artifact adapter " << name << '\n';
}
template <class Operation> void rejects(const std::string &name, Operation operation) {
    try {
        operation();
    } catch (const Error &) {
        pass(name);
        return;
    }
    throw Error(name + ": unexpectedly succeeded");
}
} // namespace
int main(int argc, char **argv) {
    try {
        require(argc == 2, "pass one owned temporary fixture directory");
        const fs::path base = argv[1], output = base / "output.s", source = base / "source.au";
        writeFile(source, "source bytes");
        writeFile(output, "old artifact");
        auto captured = host::SourceFile::explicitPath(source);
        const std::set<host::Identity> sources{captured.identity};
        const auto collision = base / (".aurora-output-" + std::to_string(::getpid()) + "-0.tmp");
        {
            host::ArtifactWriter writer(collision, sources);
            require(!fs::exists(collision), "temporary creation exposed destination");
            writer.write("complete collision-safe artifact");
            require(!fs::exists(collision), "partial output exposed at destination");
            writer.commit();
        }
        require(readFile(collision) == "complete collision-safe artifact",
                "collision-safe commit failed");
        pass("destination cannot be its own temporary");
        {
            host::ArtifactWriter writer(output, sources);
            writer.write("new artifact");
            require(readFile(output) == "old artifact", "output changed before commit");
            writer.commit();
        }
        require(readFile(output) == "new artifact" && readFile(source) == "source bytes",
                "normal replacement");
        pass("atomic complete replacement");
        rejects("root source alias", [&] { host::ArtifactWriter writer(source, sources); });
        fs::create_hard_link(source, base / "hardlink.s");
        rejects("hardlink source alias",
                [&] { host::ArtifactWriter writer(base / "hardlink.s", sources); });
        fs::create_symlink(source, base / "symlink.s");
        rejects("symlink output policy",
                [&] { host::ArtifactWriter writer(base / "symlink.s", sources); });
        fs::create_directory(base / "directory.s");
        rejects("nonregular output policy",
                [&] { host::ArtifactWriter writer(base / "directory.s", sources); });
        rejects("filename leaf required",
                [&] { host::ArtifactWriter writer(base / "..", sources); });
        std::string cancelled;
        {
            host::ArtifactWriter writer(output, sources);
            cancelled = writer.temporaryName();
            writer.write("cancelled");
        }
        require(readFile(output) == "new artifact" && !fs::exists(base / cancelled),
                "abandoned output was not preserved/cleaned");
        pass("abandoned write preserves old output");
        std::string displaced;
        {
            host::ArtifactWriter writer(output, sources);
            writer.write("pending");
            displaced = writer.temporaryName();
            fs::rename(base / displaced, base / "displaced-own.tmp");
            writeFile(base / displaced, "replacement owned by fixture");
            rejects("changed temporary rejected", [&] { writer.commit(); });
        }
        require(readFile(base / displaced) == "replacement owned by fixture",
                "cleanup removed replacement entry");
        require(readFile(output) == "new artifact", "changed temp altered destination");
        pass("cleanup preserves unrelated replacement entry");
        {
            host::ArtifactWriter writer(output, sources);
            writer.write("pending");
            fs::remove(output);
            fs::create_hard_link(source, output);
            rejects("destination hardlink swap", [&] { writer.commit(); });
        }
        require(readFile(source) == "source bytes" && readFile(output) == "source bytes",
                "hardlink swap changed source");
        fs::remove(output);
        writeFile(output, "old artifact");
        {
            host::ArtifactWriter writer(output, sources);
            writer.write("pending");
            fs::remove(output);
            fs::create_symlink(source, output);
            rejects("destination symlink swap", [&] { writer.commit(); });
        }
        require(fs::is_symlink(output) && readFile(source) == "source bytes",
                "symlink swap changed source");
        fs::remove(output);
        writeFile(output, "old artifact");
        const auto original = base / "parent", pinned = base / "pinned-parent",
                   replacement = base / "replacement-parent";
        fs::create_directories(original);
        fs::create_directories(replacement);
        writeFile(original / "result.s", "old pinned");
        writeFile(replacement / "result.s", "untouched replacement");
        {
            host::ArtifactWriter writer(original / "result.s", sources);
            writer.write("new pinned");
            fs::rename(original, pinned);
            fs::create_directory_symlink(replacement, original);
            writer.commit();
        }
        require(readFile(pinned / "result.s") == "new pinned" &&
                    readFile(replacement / "result.s") == "untouched replacement",
                "parent replacement redirected write");
        pass("pinned output parent survives replacement");
        {
            host::ArtifactWriter writer(output, sources);
            writer.write("once");
            rejects("write once", [&] { writer.write("twice"); });
            rejects("misused writer cannot commit", [&] { writer.commit(); });
        }
        {
            host::ArtifactWriter writer(output, sources);
            rejects("commit requires complete write", [&] { writer.commit(); });
            rejects("out-of-order commit poisons writer", [&] { writer.write("later"); });
        }
        {
            host::ArtifactWriter writer(base / "empty.s", sources);
            writer.write("");
            writer.commit();
        }
        require(readFile(base / "empty.s").empty(), "empty artifact not committed correctly");
        pass("empty artifact replacement");
        {
            host::ArtifactWriter writer(output, sources);
            const std::string tooLarge(64 * 1024 * 1024 + 1, 'x');
            rejects("artifact byte budget", [&] { writer.write(tooLarge); });
        }
        // A private child-process limit forces an actual partial-write/EFBIG failure.
        // No persistent process/system settings or non-fixture files are changed.
        const auto child = ::fork();
        require(child >= 0, "fork failed");
        if (child == 0) {
            std::signal(SIGXFSZ, SIG_IGN);
            const rlimit limit{1, 1};
            if (::setrlimit(RLIMIT_FSIZE, &limit) != 0)
                std::_Exit(2);
            bool failed = false, retryRejected = false, commitRejected = false;
            {
                host::ArtifactWriter writer(output, sources);
                try {
                    writer.write("more than one byte");
                } catch (const Error &error) {
                    failed = std::string(error.what()).find("cannot write artifact temporary") !=
                             std::string::npos;
                }
                try {
                    writer.write("");
                } catch (const Error &) {
                    retryRejected = true;
                }
                try {
                    writer.commit();
                } catch (const Error &) {
                    commitRejected = true;
                }
            }
            std::_Exit(failed && retryRejected && commitRejected ? 0 : 3);
        }
        int status = 0;
        require(::waitpid(child, &status, 0) == child, "wait failed");
        require(WIFEXITED(status) && WEXITSTATUS(status) == 0,
                "write-failure injection did not fail as intended");
        require(readFile(output) == "old artifact" && readFile(source) == "source bytes",
                "write failure changed previous files");
        pass("partial OS write failure preserves output");
        pass("failed writer rejects empty retry and commit");
        // This permission-failure gate intentionally requires an unprivileged test user.
        require(::geteuid() != 0, "rename-denial gate requires an unprivileged test user");
        const auto denied = base / "denied-parent";
        fs::create_directory(denied);
        writeFile(denied / "output.s", "original");
        {
            host::ArtifactWriter writer(denied / "output.s", sources);
            writer.write("replacement");
            fs::permissions(denied, fs::perms::owner_read | fs::perms::owner_exec);
            bool failed = false;
            try {
                writer.commit();
            } catch (const Error &error) {
                failed = std::string(error.what()).find("cannot atomically replace artifact") !=
                         std::string::npos;
            }
            fs::permissions(denied, fs::perms::owner_all);
            require(failed, "rename failure injection did not reach expected OS failure");
        }
        require(readFile(denied / "output.s") == "original", "rename failure replaced destination");
        pass("OS rename failure preserves output");
        std::cout << passed << " artifact adapter tests passed\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
