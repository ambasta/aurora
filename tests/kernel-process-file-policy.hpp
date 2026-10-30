#pragma once
// Test-only copied-policy ABI and closed result decoder for the existing
// native reference driver; no kernel image includes these file-policy roots.
#include "../kernel/uefi/process-policy.hpp"
namespace aurora::uefi::process {
// The file service (process.md#files): kernel.process_files's decisions. The
// statuses are the HostStatus ordinals; the kernel returns them negated.
enum class FileStatus : U64 {
    success,
    invalid_handle,
    not_found,
    denied,
    escape,
    not_regular,
    exhausted,
    too_large,
    invalid_path,
    failed
};
inline constexpr U64 file_handles = 32, file_outputs = 4, file_records = 64, file_generation_limit = U64{1} << 58;
class FileOpen final {
public:
    U64 status = 0, slot = 0, generation = 0, id = 0, kind = 0, target = 0, extent = 0, size = 0, device = 0, inode = 0;
};
class FileCreate final {
public:
    U64 status = 0, slot = 0, generation = 0, id = 0, file = 0, first = 0, depth = 0, leaf = 0, leaf_length = 0,
        device = 0, inode = 0, directory_device = 0, directory_inode = 0;
};
class FileRead final {
public:
    U64 status = 0, kind = 0, target = 0, offset = 0, count = 0;
};
class FileChange final {
public:
    U64 status = 0, slot = 0, file = 0, release = 0, state = 0, frames = 0, size = 0, replaced = 0, inode = 0;
};
class FileOpenArguments final {
public:
    PolicySpan volume, overlay, table, path;
    U64 operation, directory;
};
class FileCreateArguments final {
public:
    PolicySpan volume, overlay, table, path;
};
class FileReadArguments final {
public:
    PolicySpan table;
    U64 id, offset;
};
class FileCloseArguments final {
public:
    PolicySpan overlay, table;
    U64 id;
};
class FileWriteArguments final {
public:
    PolicySpan table;
    U64 id, bytes, charged, quota;
};
class FileCommitArguments final {
public:
    PolicySpan volume, overlay, table;
    U64 id;
};
class EntryPrefixArguments final {
public:
    PolicySpan volume;
    U64 first, depth;
};
class FileDiscardArguments final {
public:
    PolicySpan table;
    U64 id;
};
static_assert(sizeof(FileOpen) == 80 && sizeof(FileCreate) == 104 && sizeof(FileRead) == 40 &&
              sizeof(FileChange) == 72 && sizeof(FileOpenArguments) == 240 && sizeof(FileCreateArguments) == 224 &&
              sizeof(FileReadArguments) == 72 && sizeof(FileCloseArguments) == 120 &&
              sizeof(FileWriteArguments) == 88 && sizeof(FileCommitArguments) == 176 &&
              sizeof(FileDiscardArguments) == 64);

namespace bridge {
auto file_open(const FileOpenArguments *, FileOpen *) -> void asm("__au_runtime_process_file_open")
    __attribute__((visibility("hidden")));
auto file_create(const FileCreateArguments *, FileCreate *) -> void asm("__au_runtime_process_file_create")
    __attribute__((visibility("hidden")));
auto file_read(const FileReadArguments *, FileRead *) -> void asm("__au_runtime_process_file_read")
    __attribute__((visibility("hidden")));
auto file_close(const FileCloseArguments *, FileChange *) -> void asm("__au_runtime_process_file_close")
    __attribute__((visibility("hidden")));
auto file_write(const FileWriteArguments *, FileChange *) -> void asm("__au_runtime_process_file_write")
    __attribute__((visibility("hidden")));
auto file_commit(const FileCommitArguments *, FileChange *) -> void asm("__au_runtime_process_file_commit")
    __attribute__((visibility("hidden")));
auto file_discard(const FileDiscardArguments *, FileChange *) -> void asm("__au_runtime_process_file_discard")
    __attribute__((visibility("hidden")));
auto directory_prefix(const EntryPrefixArguments *) -> U64 asm("__au_runtime_process_directory_prefix")
    __attribute__((visibility("hidden")));
} // namespace bridge
// File decisions in their closed shapes (process.md#files); nullopt for any
// other encoding. A failure names nothing; a success names a slot of its
// table with the next generation and the id that slot and generation make.
[[nodiscard]] inline auto file_status(U64 raw) -> std::optional<FileStatus> {
    return verdict<FileStatus, 9>(raw);
}
[[nodiscard]] inline auto file_open(std::span<const std::byte> volume,
                                    std::span<const std::byte> overlay,
                                    std::span<const std::byte> table,
                                    std::span<const std::byte> path,
                                    U64 operation,
                                    U64 directory) -> std::optional<FileOpen> {
    const FileOpenArguments arguments{
        PolicySpan{volume}, PolicySpan{overlay}, PolicySpan{table}, PolicySpan{path}, operation, directory};
    FileOpen result{~U64{0}, ~U64{0}, ~U64{0}, ~U64{0}, ~U64{0}, ~U64{0}, ~U64{0}, ~U64{0}, ~U64{0}, ~U64{0}};
    bridge::file_open(&arguments, &result);
    const auto status = file_status(result.status);
    if (!status)
        return std::nullopt;
    if (*status != FileStatus::success)
        return result.slot || result.generation || result.id || result.kind || result.target || result.extent ||
                       result.size || result.device || result.inode
                   ? std::nullopt
                   : std::optional<FileOpen>{result};
    const auto directory_shape = result.kind == 1 && operation == 0 && result.size == 0 && result.extent <= 127 &&
                                 result.target < 4096 && result.device == 1 &&
                                 result.inode == 65536 + result.target * 256 + result.extent;
    const auto volume_shape = result.kind == 2 && operation != 0 && result.size == result.extent &&
                              result.target < 4096 && result.device == 1 && result.inode == result.target + 1;
    const auto overlay_shape = result.kind == 3 && operation != 0 && result.size == result.extent &&
                               result.size <= file_output_limit && result.target < file_records && result.device == 2 &&
                               result.inode != 0;
    if (result.slot >= file_handles || result.generation == 0 || result.generation >= file_generation_limit ||
        result.id != result.generation * 64 + result.slot + 1 || !(directory_shape || volume_shape || overlay_shape))
        return std::nullopt;
    return result;
}
[[nodiscard]] inline auto file_create(std::span<const std::byte> volume,
                                      std::span<const std::byte> overlay,
                                      std::span<const std::byte> table,
                                      std::span<const std::byte> path) -> std::optional<FileCreate> {
    const FileCreateArguments arguments{PolicySpan{volume}, PolicySpan{overlay}, PolicySpan{table}, PolicySpan{path}};
    FileCreate result;
    for (auto *word : {&result.status,
                       &result.slot,
                       &result.generation,
                       &result.id,
                       &result.file,
                       &result.first,
                       &result.depth,
                       &result.leaf,
                       &result.leaf_length,
                       &result.device,
                       &result.inode,
                       &result.directory_device,
                       &result.directory_inode})
        *word = ~U64{0};
    bridge::file_create(&arguments, &result);
    const auto status = file_status(result.status);
    if (!status)
        return std::nullopt;
    if (*status != FileStatus::success)
        return result.slot || result.generation || result.id || result.file || result.first || result.depth ||
                       result.leaf || result.leaf_length || result.device || result.inode || result.directory_device ||
                       result.directory_inode
                   ? std::nullopt
                   : std::optional<FileCreate>{result};
    if (result.slot >= file_outputs || result.generation == 0 || result.generation >= file_generation_limit ||
        result.id != result.generation * 64 + file_handles + result.slot + 1 || result.file >= file_records ||
        result.first >= 4096 || result.depth > 127 || result.leaf_length == 0 || result.leaf_length > 255 ||
        result.leaf > path.size() || result.leaf_length != path.size() - result.leaf ||
        (result.leaf && std::to_integer<unsigned>(path[result.leaf - 1]) != '/') || result.directory_device != 1 ||
        result.directory_inode != 65536 + result.first * 256 + result.depth ||
        (result.device == 0) != (result.inode == 0) || result.device > 2)
        return std::nullopt;
    for (const auto byte : path.subspan(result.leaf))
        if (std::to_integer<unsigned>(byte) == '/' || std::to_integer<unsigned>(byte) == 0)
            return std::nullopt;
    return result;
}
[[nodiscard]] inline auto file_read(std::span<const std::byte> table, U64 id, U64 offset) -> std::optional<FileRead> {
    const FileReadArguments arguments{PolicySpan{table}, id, offset};
    FileRead result{~U64{0}, ~U64{0}, ~U64{0}, ~U64{0}, ~U64{0}};
    bridge::file_read(&arguments, &result);
    const auto status = file_status(result.status);
    if (!status)
        return std::nullopt;
    if (*status != FileStatus::success)
        return (*status == FileStatus::invalid_handle || *status == FileStatus::failed) && !result.kind &&
                       !result.target && !result.offset && !result.count
                   ? std::optional<FileRead>{result}
                   : std::nullopt;
    if ((result.kind != 2 && result.kind != 3) || result.offset != offset || result.count > file_chunk ||
        (result.kind == 3 && result.target >= file_records) || (result.kind == 2 && result.target >= 4096))
        return std::nullopt;
    return result;
}
// A change names at most its own slot (+ 1) and one record (+ 1), and a
// replaced record (+ 1) other than that one.
[[nodiscard]] inline auto file_change(const FileChange &result, U64 slots) -> std::optional<FileChange> {
    const auto status = file_status(result.status);
    if (!status || result.slot > slots || result.file > file_records || result.release > 1 || result.state > 3 ||
        result.replaced > file_records || (result.replaced && result.replaced == result.file))
        return std::nullopt;
    return result;
}
[[nodiscard]] inline auto unchanged() -> FileChange {
    return {~U64{0}, ~U64{0}, ~U64{0}, ~U64{0}, ~U64{0}, ~U64{0}, ~U64{0}, ~U64{0}, ~U64{0}};
}
[[nodiscard]] inline auto file_close(std::span<const std::byte> overlay, std::span<const std::byte> table, U64 id)
    -> std::optional<FileChange> {
    const FileCloseArguments arguments{PolicySpan{overlay}, PolicySpan{table}, id};
    auto result = unchanged();
    bridge::file_close(&arguments, &result);
    const auto decided = file_change(result, file_handles);
    if (!decided || decided->state || decided->frames || decided->size || decided->replaced || decided->inode)
        return std::nullopt;
    const auto success = decided->status == static_cast<U64>(FileStatus::success);
    if (success ? !decided->slot || (!decided->file && decided->release)
                : decided->status != static_cast<U64>(FileStatus::invalid_handle) || decided->slot || decided->file ||
                      decided->release)
        return std::nullopt;
    return decided;
}
[[nodiscard]] inline auto file_write(std::span<const std::byte> table, U64 id, U64 bytes, U64 charged, U64 quota)
    -> std::optional<FileChange> {
    const FileWriteArguments arguments{PolicySpan{table}, id, bytes, charged, quota};
    auto result = unchanged();
    bridge::file_write(&arguments, &result);
    const auto decided = file_change(result, file_outputs);
    if (!decided || decided->release || decided->replaced || decided->inode)
        return std::nullopt;
    const auto status = static_cast<FileStatus>(decided->status);
    if (status == FileStatus::invalid_handle)
        return decided->slot || decided->file || decided->state || decided->frames || decided->size ? std::nullopt
                                                                                                    : decided;
    if (!decided->slot || !decided->file ||
        (status == FileStatus::success
             ? decided->state != 1 || decided->size > file_output_limit || decided->size < bytes || charged > quota ||
                   decided->frames > quota - charged
             : (status != FileStatus::too_large && status != FileStatus::failed) || decided->state != 2 ||
                   decided->frames || decided->size))
        return std::nullopt;
    return decided;
}
[[nodiscard]] inline auto file_commit(std::span<const std::byte> volume,
                                      std::span<const std::byte> overlay,
                                      std::span<const std::byte> table,
                                      U64 id) -> std::optional<FileChange> {
    const FileCommitArguments arguments{PolicySpan{volume}, PolicySpan{overlay}, PolicySpan{table}, id};
    auto result = unchanged();
    bridge::file_commit(&arguments, &result);
    const auto decided = file_change(result, file_outputs);
    if (!decided || decided->frames || decided->size)
        return std::nullopt;
    const auto status = static_cast<FileStatus>(decided->status);
    if (status == FileStatus::invalid_handle)
        return decided->slot || decided->file || decided->release || decided->state || decided->replaced ||
                       decided->inode
                   ? std::nullopt
                   : decided;
    if (!decided->slot || !decided->file ||
        (status == FileStatus::success
             ? decided->release || decided->inode == 0 || (decided->state != 0 && decided->state != 3) ||
                   (!decided->replaced && decided->state)
             : (status != FileStatus::failed && status != FileStatus::not_regular) || !decided->release ||
                   decided->state || decided->replaced || decided->inode))
        return std::nullopt;
    return decided;
}
[[nodiscard]] inline auto file_discard(std::span<const std::byte> table, U64 id) -> std::optional<FileChange> {
    const FileDiscardArguments arguments{PolicySpan{table}, id};
    auto result = unchanged();
    bridge::file_discard(&arguments, &result);
    const auto decided = file_change(result, file_outputs);
    if (!decided || decided->state || decided->frames || decided->size || decided->replaced || decided->inode)
        return std::nullopt;
    const auto success = decided->status == static_cast<U64>(FileStatus::success);
    if (success ? !decided->slot || !decided->file || !decided->release
                : decided->status != static_cast<U64>(FileStatus::invalid_handle) || decided->slot || decided->file ||
                      decided->release)
        return std::nullopt;
    return decided;
}
// The bytes of directory (first, depth)'s path at the start of entry first's
// name, or nullopt.
[[nodiscard]] inline auto directory_prefix(std::span<const std::byte> volume, U64 first, U64 depth)
    -> std::optional<U64> {
    const EntryPrefixArguments arguments{PolicySpan{volume}, first, depth};
    const auto prefix = bridge::directory_prefix(&arguments);
    if (prefix == 0 || prefix > 256 || (depth == 0) != (prefix == 1))
        return std::nullopt;
    return prefix - 1;
}
} // namespace aurora::uefi::process
