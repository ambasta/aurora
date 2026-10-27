#pragma once
// Trusted Linux-host bootstrap adapter. These OS interfaces are not exposed to Aurora.
#include "types.hpp"
#include <algorithm>
#include <array>
#include <atomic>
#include <cerrno>
#include <fcntl.h>
#include <filesystem>
#include <linux/openat2.h>
#include <optional>
#include <set>
#include <string_view>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <system_error>
#include <unistd.h>

namespace aurora::host {
using Identity = std::pair<std::uint64_t, std::uint64_t>;
using FileStatus = class ::stat; // Existing Linux/POSIX status record, confined to the host adapter.
class Handle {
    int value = -1;

public:
    explicit Handle(int descriptor) : value(descriptor) {
    }
    Handle(const Handle &) = delete;
    Handle &operator=(const Handle &) = delete;
    Handle(Handle &&other) noexcept : value(std::exchange(other.value, -1)) {
    }
    Handle &operator=(Handle &&other) noexcept {
        if (this != &other) {
            if (value >= 0)
                ::close(value);
            value = std::exchange(other.value, -1);
        }
        return *this;
    }
    ~Handle() {
        if (value >= 0)
            ::close(value);
    }
    int get() const {
        return value;
    }
};
class ReadLimit : public Error {
public:
    explicit ReadLimit(const std::string &message = "bounded source read limit exceeded") : Error(message) {
    }
};
inline std::string systemMessage(int error) {
    return std::error_code(error, std::generic_category()).message();
}
inline int openPolicy(int directory, const std::filesystem::path &path, bool isDirectory, bool beneath) {
    const auto text = path.string();
    if (text.find('\0') != std::string::npos)
        throw Error("source path contains a NUL byte");
    open_how policy{};
    policy.flags = O_RDONLY | O_CLOEXEC | (isDirectory ? O_DIRECTORY : O_NONBLOCK);
    policy.resolve = RESOLVE_NO_SYMLINKS | RESOLVE_NO_MAGICLINKS | (beneath ? RESOLVE_BENEATH : 0);
    const auto descriptor = ::syscall(SYS_openat2, directory, text.c_str(), &policy, sizeof(policy));
    if (descriptor < 0 && (errno == ENOSYS || errno == EINVAL))
        throw Error("hardened source access requires Linux openat2 beneath-root/no-symlink support");
    return static_cast<int>(descriptor);
}
inline FileStatus regular(int descriptor) {
    FileStatus status{};
    if (::fstat(descriptor, &status) < 0)
        throw Error("cannot inspect opened source: " + systemMessage(errno));
    if (!S_ISREG(status.st_mode))
        throw Error("source is not a regular file");
    return status;
}
inline constexpr std::size_t artifactLimit = 64 * 1024 * 1024;
namespace detail {
// Both input authorities use the same hardened descriptor and bounded read loop.
// Without a limit message, a longer input returns its first limit + 1 bytes.
inline std::string readAtMost(int descriptor, std::size_t limit, const char *limitMessage) {
    std::array<char, 4096> buffer{};
    std::string result;
    int interruptions = 0;
    while (true) {
        const auto requested = std::min(buffer.size(), limit - result.size() + 1);
        const auto count = ::read(descriptor, buffer.data(), requested);
        if (count < 0) {
            if (errno == EINTR && ++interruptions <= 128)
                continue;
            throw Error("cannot read opened source: " + systemMessage(errno));
        }
        if (count == 0)
            return result;
        const bool beyond = static_cast<std::size_t>(count) > limit - result.size();
        if (beyond && limitMessage)
            throw ReadLimit(limitMessage);
        result.append(buffer.data(), static_cast<std::size_t>(count));
        if (beyond)
            return result;
    }
}
} // namespace detail
class SourceFile {
    Handle descriptor;

public:
    std::filesystem::path displayPath;
    Identity identity;
    SourceFile(Handle handle, std::filesystem::path path)
        : descriptor(std::move(handle)), displayPath(std::move(path)) {
        const auto status = regular(descriptor.get());
        identity = {static_cast<std::uint64_t>(status.st_dev), static_cast<std::uint64_t>(status.st_ino)};
    }
    SourceFile(SourceFile &&) = default;
    SourceFile &operator=(SourceFile &&) = default;
    SourceFile(const SourceFile &) = delete;
    static SourceFile explicitPath(const std::filesystem::path &path) {
        const int file = openPolicy(AT_FDCWD, path, false, false);
        if (file < 0)
            throw Error("cannot open input under no-symlink source policy: " + systemMessage(errno));
        return SourceFile(Handle(file), path);
    }
    std::string readAtMost(std::size_t limit) {
        if (limit > 1024 * 1024)
            throw Error("source read bound exceeds adapter limit");
        return detail::readAtMost(descriptor.get(), limit, "bounded source read limit exceeded");
    }
    // Captures at most limit bytes, or limit + 1 for a longer file, so the
    // caller's byte policy rejects it.
    std::string capture(std::size_t limit) {
        if (limit > 1024 * 1024)
            throw Error("source read bound exceeds adapter limit");
        return detail::readAtMost(descriptor.get(), limit, nullptr);
    }
};
// Binary inputs are not source files: their independent bound is the existing
// artifact ceiling, while SourceFile remains capped at 1 MiB.
class ArtifactFile {
    Handle descriptor;

public:
    Identity identity;
    explicit ArtifactFile(const std::filesystem::path &path) : descriptor(openPolicy(AT_FDCWD, path, false, false)) {
        if (descriptor.get() < 0)
            throw Error("cannot open artifact input under no-symlink policy: " + systemMessage(errno));
        const auto status = regular(descriptor.get());
        identity = {static_cast<std::uint64_t>(status.st_dev), static_cast<std::uint64_t>(status.st_ino)};
    }
    std::string readAtMost(std::size_t limit = artifactLimit) {
        if (limit > artifactLimit)
            throw Error("artifact read bound exceeds adapter limit");
        return detail::readAtMost(descriptor.get(), limit, "bounded artifact read limit exceeded");
    }
};
class Directory {
    friend class ArtifactWriter;
    Handle descriptor;

public:
    std::filesystem::path displayPath;
    Identity identity;
    explicit Directory(const std::filesystem::path &path)
        : descriptor(openPolicy(AT_FDCWD, path, true, false)), displayPath(path) {
        if (descriptor.get() < 0)
            throw Error("module root is not an accessible no-symlink directory: " + systemMessage(errno));
        FileStatus status{};
        if (::fstat(descriptor.get(), &status) < 0)
            throw Error("cannot inspect module root: " + systemMessage(errno));
        identity = {static_cast<std::uint64_t>(status.st_dev), static_cast<std::uint64_t>(status.st_ino)};
        // Probe the exact relative policy once for every pinned root; never fall back.
        Handle probe(openPolicy(descriptor.get(), ".", true, true));
        if (probe.get() < 0)
            throw Error("cannot establish beneath-root source policy: " + systemMessage(errno));
    }
    Directory(Directory &&) = default;
    Directory &operator=(Directory &&) = default;
    Directory(const Directory &) = delete;
    std::optional<SourceFile> open(const std::filesystem::path &relative) const {
        const int file = openPolicy(descriptor.get(), relative, false, true);
        if (file < 0) {
            const int error = errno;
            if (error == ENOENT || error == ENOTDIR)
                return std::nullopt;
            if (error == EXDEV || error == ELOOP)
                throw Error("module path is a symlink or escapes its explicit search root");
            throw Error("cannot open module under beneath-root source policy: " + systemMessage(error));
        }
        return SourceFile(Handle(file), displayPath / relative);
    }
};
// Atomic artifact replacement uses a separate caller-selected directory authority.
// Existing files are never opened for writing or truncated.
class ArtifactWriter {
    Directory parent;
    std::string leaf;
    std::set<Identity> sourceIdentities;
    std::optional<Handle> temporary;
    std::string temporaryLeaf;
    Identity temporaryIdentity{};
    enum class Phase {
        Empty,
        Failed,
        Ready,
        Committed
    };
    Phase phase = Phase::Empty;
    static inline std::atomic<std::uint64_t> sequence{0};
    static constexpr std::size_t maxArtifactBytes = artifactLimit;
    static Identity identityOf(const FileStatus &status) {
        return {static_cast<std::uint64_t>(status.st_dev), static_cast<std::uint64_t>(status.st_ino)};
    }
    std::optional<FileStatus> entry(const std::string &name) const {
        FileStatus status{};
        if (::fstatat(parent.descriptor.get(), name.c_str(), &status, AT_SYMLINK_NOFOLLOW) == 0)
            return status;
        if (errno == ENOENT)
            return std::nullopt;
        throw Error("cannot inspect artifact entry: " + systemMessage(errno));
    }
    void destination() const {
        if (const auto status = entry(leaf)) {
            if (!S_ISREG(status->st_mode))
                throw Error("artifact destination must be a regular file, not a symlink or directory");
            if (sourceIdentities.contains(identityOf(*status)))
                throw Error("artifact destination aliases a root or imported source file");
        }
    }
    bool ownsTemporaryName() const {
        const auto status = entry(temporaryLeaf);
        return status && S_ISREG(status->st_mode) && identityOf(*status) == temporaryIdentity;
    }
    void cleanup() noexcept {
        if (phase == Phase::Committed || !temporary || temporaryLeaf.empty())
            return;
        try {
            // Do not remove a replacement entry belonging to another writer. A hostile
            // same-authority directory writer remains outside artifact-integrity guarantees.
            if (ownsTemporaryName())
                ::unlinkat(parent.descriptor.get(), temporaryLeaf.c_str(), 0);
        } catch (...) {
        } // Never replace the original I/O failure with a cleanup error.
    }

public:
    ArtifactWriter(const std::filesystem::path &path, std::set<Identity> sources)
        : parent(path.parent_path().empty() ? std::filesystem::path(".") : path.parent_path()),
          leaf(path.filename().string()), sourceIdentities(std::move(sources)) {
        if (leaf.empty() || leaf == "." || leaf == ".." || leaf.find('/') != std::string::npos ||
            leaf.find('\0') != std::string::npos)
            throw Error("artifact output requires one filename leaf");
        destination();
        for (int attempt = 0; attempt < 32; ++attempt) {
            const auto candidate =
                ".aurora-output-" + std::to_string(::getpid()) + "-" + std::to_string(sequence.fetch_add(1)) + ".tmp";
            if (candidate == leaf)
                continue; // Never expose the destination as its own temporary.
            open_how policy{};
            policy.flags = O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW;
            policy.mode = 0600;
            policy.resolve = RESOLVE_BENEATH | RESOLVE_NO_SYMLINKS | RESOLVE_NO_MAGICLINKS;
            const auto file =
                ::syscall(SYS_openat2, parent.descriptor.get(), candidate.c_str(), &policy, sizeof(policy));
            if (file < 0) {
                if (errno == EEXIST)
                    continue;
                throw Error("cannot create exclusive artifact temporary: " + systemMessage(errno));
            }
            Handle owned(static_cast<int>(file));
            temporaryIdentity = identityOf(regular(owned.get()));
            temporaryLeaf = candidate;
            temporary.emplace(std::move(owned));
            return;
        }
        throw Error("artifact temporary-name retry limit exceeded");
    }
    ArtifactWriter(const ArtifactWriter &) = delete;
    ArtifactWriter &operator=(const ArtifactWriter &) = delete;
    ~ArtifactWriter() {
        cleanup();
    }
    bool sameDestination(const ArtifactWriter &other) const {
        return parent.identity == other.parent.identity && leaf == other.leaf;
    }
    const std::string &temporaryName() const {
        return temporaryLeaf;
    }
    void write(std::string_view bytes) {
        if (phase != Phase::Empty) {
            if (phase != Phase::Committed)
                phase = Phase::Failed;
            throw Error("artifact bytes may be supplied exactly once");
        }
        phase = Phase::Failed; // Any exception permanently poisons this transaction.
        if (bytes.size() > maxArtifactBytes)
            throw Error("artifact exceeds 67108864 bytes");
        std::size_t offset = 0;
        int calls = 0, interruptions = 0;
        while (offset < bytes.size()) {
            if (++calls > 8192)
                throw Error("artifact write-call budget exceeded");
            const auto count =
                ::write(temporary->get(), bytes.data() + offset, std::min<std::size_t>(65536, bytes.size() - offset));
            if (count < 0) {
                if (errno == EINTR && ++interruptions <= 128)
                    continue;
                throw Error("cannot write artifact temporary: " + systemMessage(errno));
            }
            if (count == 0)
                throw Error("artifact write made no progress");
            offset += static_cast<std::size_t>(count);
        }
        phase = Phase::Ready;
    }
    void commit() {
        if (phase != Phase::Ready) {
            if (phase != Phase::Committed)
                phase = Phase::Failed;
            throw Error("artifact commit requires one complete write");
        }
        phase = Phase::Failed;
        destination();
        if (!ownsTemporaryName())
            throw Error("artifact temporary entry changed before commit");
        if (::renameat(parent.descriptor.get(), temporaryLeaf.c_str(), parent.descriptor.get(), leaf.c_str()) < 0)
            throw Error("cannot atomically replace artifact: " + systemMessage(errno));
        phase = Phase::Committed;
    }
};
} // namespace aurora::host
