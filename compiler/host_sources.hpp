#pragma once
// The language server's Linux source adapter (aurorac reads through HostFiles).
// These OS interfaces are not exposed to Aurora.
#include "diagnostics.hpp"
#include <algorithm>
#include <array>
#include <cerrno>
#include <fcntl.h>
#include <filesystem>
#include <linux/openat2.h>
#include <optional>
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
namespace detail {
// Source reads use the hardened descriptor and one bounded read loop.
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
class Directory {
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
} // namespace aurora::host
