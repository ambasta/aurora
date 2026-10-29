#pragma once
// The file service of the running process (kernel/uefi/process.md#files):
// the storage behind kernel.process_files's decisions. It keeps the handle
// and output table, the overlay records and the frames that hold the
// overlay's bytes, applies each Aurora decision after its decoder admitted
// its closed shape, and copies bytes. Each overlay record's bytes live in
// data frames listed by up to 32 index frames of 512 entries (64 MiB). The
// Store supplies charged frames and copies through them: the process's
// frames through the kernel's window in the image (process.cpp), heap pages
// in the hosted driver (tests/kernel-process.cpp).
#include "process-policy.hpp"

namespace aurora::uefi {
[[nodiscard]] constexpr auto least(std::uint64_t first, std::uint64_t second) -> std::uint64_t {
    return first < second ? first : second;
}
template <class Store> class FileService final {
public:
    using U64 = std::uint64_t;
    using Status = process::FileStatus;
    // Handle states 1 directory, 2 volume file, 3 overlay file; output
    // states 1 open, 2 failed; record states 1 pending, 2 linked, 3 unlinked
    // while open (kernel.process_files's layouts).
    class Handle final {
    public:
        U64 state = 0, generation = 0, target = 0, extent = 0;
    };
    class Output final {
    public:
        U64 state = 0, generation = 0, file = 0, written = 0, reserved[4]{};
    };
    class Table final {
    public:
        std::array<Handle, process::file_handles> handles{};
        std::array<Output, process::file_outputs> outputs{};
        U64 inodes = 0, reserved[7]{};
    };
    class Record final {
    public:
        U64 state = 0, first = 0, depth = 0, leaf_length = 0, size = 0, inode = 0, opens = 0, frames = 0;
        std::array<std::byte, 256> leaf{};
    };
    static_assert(sizeof(Table) == 1344 && sizeof(Record) == 320);
    static constexpr U64 frame_bytes = 4096, index_frames = process::file_output_limit / frame_bytes / 512;
    // An operation's result: 0 or a negative HostStatus in value, and the
    // 48-byte result record of the opens and create_output.
    class Result final {
    public:
        U64 value = 0;
        std::array<U64, 6> record{};
        bool broken = false;
    };

private:
    std::span<const std::byte> volume_{};
    Store *store_ = nullptr;
    Table table_{};
    std::array<Record, process::file_records> records_{};
    std::array<std::array<U64, index_frames>, process::file_records> index_{};

    [[nodiscard]] auto table_bytes() const -> std::span<const std::byte> {
        return std::as_bytes(std::span{&table_, 1});
    }
    [[nodiscard]] auto overlay_bytes() const -> std::span<const std::byte> {
        return std::as_bytes(std::span{records_});
    }
    [[nodiscard]] static auto status(Status value) -> U64 {
        return ~static_cast<U64>(value) + 1;
    }
    [[nodiscard]] static auto broken() -> Result {
        Result result;
        result.broken = true;
        return result;
    }
    // The data frame of page of record, or 0.
    [[nodiscard]] auto data_frame(U64 record, U64 page) -> U64 {
        const auto index = index_[record][page / 512];
        return index ? store_->read_word(index, page % 512) : 0;
    }
    // Releases every frame of a record and frees it.
    [[nodiscard]] auto free_record(U64 record) -> bool {
        auto &held = records_[record];
        const auto pages = (held.size + frame_bytes - 1) / frame_bytes;
        U64 released = 0;
        for (U64 page = 0; page < pages; ++page) {
            const auto frame = data_frame(record, page);
            if (!frame || !store_->give(frame))
                return false;
            ++released;
        }
        for (auto &index : index_[record]) {
            if (index && !store_->give(index))
                return false;
            released += index != 0;
            index = 0;
        }
        if (released != held.frames || !store_->uncharge(released))
            return false;
        held = Record{};
        return true;
    }
    // Appends bytes to a pending record with the frames its decision charged.
    [[nodiscard]] auto append(U64 record, std::span<const std::byte> bytes, U64 charged) -> bool {
        auto &held = records_[record];
        U64 taken = 0;
        for (U64 done = 0; done < bytes.size();) {
            const auto page = held.size / frame_bytes, offset = held.size % frame_bytes;
            U64 frame = 0;
            if (page / 512 >= index_frames)
                return false;
            if (offset == 0) {
                auto &index = index_[record][page / 512];
                if (page % 512 == 0) {
                    const auto made = index ? std::optional<U64>{} : store_->take();
                    if (!made)
                        return false;
                    index = *made;
                    ++taken;
                }
                const auto made = store_->take();
                if (!made || !store_->write_word(index, page % 512, *made))
                    return false;
                frame = *made;
                ++taken;
            } else {
                frame = data_frame(record, page);
            }
            const auto count = least(frame_bytes - offset, bytes.size() - done);
            if (!frame || !store_->copy_in(frame, offset, bytes.subspan(done, count)))
                return false;
            done += count;
            held.size += count;
            held.frames += offset == 0 ? 1 + (page % 512 == 0) : 0;
        }
        return taken == charged;
    }
    // Ends an output; its pending record is freed when release.
    [[nodiscard]] auto end_output(U64 slot, bool release) -> bool {
        auto &output = table_.outputs[slot];
        const auto record = output.file;
        output.state = 0;
        output.file = output.written = 0;
        return !release || (records_[record].state == 1 && free_record(record));
    }

public:
    constexpr FileService() = default;
    FileService(const FileService &) = delete;
    auto operator=(const FileService &) -> FileService & = delete;
    // One process's service over the admitted volume, with no handle,
    // output or record (each finish leaves it so).
    [[nodiscard]] auto begin(std::span<const std::byte> volume, Store &store) -> bool {
        if (store_)
            return false;
        for (const auto &held : records_)
            if (held.state)
                return false;
        volume_ = volume;
        store_ = &store;
        return true;
    }

    // open_directory (0), open_beneath (1) or open_file (2) of path; a path
    // above 4095 bytes arrives empty (invalid_path in the same order).
    [[nodiscard]] auto open(U64 operation, U64 directory, std::span<const std::byte> path) -> Result {
        const auto decided =
            process::file_open(volume_, overlay_bytes(), table_bytes(), path, operation, directory);
        if (!decided)
            return broken();
        Result result;
        if (decided->status != 0) {
            result.value = status(static_cast<Status>(decided->status));
            return result;
        }
        auto &handle = table_.handles[decided->slot];
        if (handle.state || handle.generation + 1 != decided->generation ||
            (decided->kind == 3 && records_[decided->target].state != 2) ||
            (decided->kind == 3 && records_[decided->target].size != decided->size))
            return broken();
        handle = {decided->kind, decided->generation, decided->target, decided->extent};
        if (decided->kind == 3)
            ++records_[decided->target].opens;
        result.record = {decided->id, decided->size, decided->device, decided->inode, 0, 0};
        return result;
    }
    [[nodiscard]] auto create(std::span<const std::byte> path) -> Result {
        const auto decided = process::file_create(volume_, overlay_bytes(), table_bytes(), path);
        if (!decided)
            return broken();
        Result result;
        if (decided->status != 0) {
            result.value = status(static_cast<Status>(decided->status));
            return result;
        }
        auto &output = table_.outputs[decided->slot];
        auto &record = records_[decided->file];
        if (output.state || output.generation + 1 != decided->generation || record.state)
            return broken();
        output = {1, decided->generation, decided->file, 0, {}};
        record = {1, decided->first, decided->depth, decided->leaf_length, 0, 0, 0, 0, {}};
        for (U64 at = 0; at < decided->leaf_length; ++at)
            record.leaf[at] = path[decided->leaf + at];
        result.record = {decided->id, 0, decided->device, decided->inode, decided->directory_device,
                         decided->directory_inode};
        return result;
    }
    // Up to 504 bytes into chunk; the count, or a negative HostStatus.
    [[nodiscard]] auto read(U64 id, U64 offset, std::span<std::byte, process::file_chunk> chunk) -> Result {
        const auto decided = process::file_read(table_bytes(), id, offset);
        if (!decided)
            return broken();
        Result result;
        if (decided->status != 0) {
            result.value = status(static_cast<Status>(decided->status));
            return result;
        }
        if (decided->kind == 2) {
            const auto entry = process::volume_extent(volume_, decided->target);
            if (!entry || (decided->count && (offset > entry->size() || decided->count > entry->size() - offset)))
                return broken();
            for (U64 at = 0; at < decided->count; ++at)
                chunk[at] = (*entry)[offset + at];
        } else {
            const auto record = decided->target;
            if (records_[record].state != 2 && records_[record].state != 3)
                return broken();
            for (U64 done = 0; done < decided->count;) {
                const auto at = offset + done, page = at / frame_bytes, within = at % frame_bytes;
                const auto count = least(frame_bytes - within, decided->count - done);
                const auto frame = data_frame(record, page);
                if (at + count > records_[record].size || !frame ||
                    !store_->copy_out(frame, within, chunk.subspan(done, count)))
                    return broken();
                done += count;
            }
        }
        result.value = decided->count;
        return result;
    }
    [[nodiscard]] auto write(U64 id, std::span<const std::byte> bytes) -> Result {
        const auto decided = process::file_write(table_bytes(), id, bytes.size(), store_->charged(), store_->quota());
        if (!decided)
            return broken();
        Result result;
        if (decided->slot) {
            auto &output = table_.outputs[decided->slot - 1];
            if (!output.state || output.file + 1 != decided->file || records_[output.file].state != 1)
                return broken();
            output.state = decided->state;
            if (decided->status == 0) {
                if (decided->size != output.written + bytes.size() || !store_->charge(decided->frames) ||
                    !append(output.file, bytes, decided->frames))
                    return broken();
                output.written = decided->size;
            }
        }
        result.value = decided->status ? status(static_cast<Status>(decided->status)) : 0;
        return result;
    }
    [[nodiscard]] auto commit(U64 id) -> Result {
        const auto decided = process::file_commit(volume_, overlay_bytes(), table_bytes(), id);
        if (!decided)
            return broken();
        Result result;
        result.value = decided->status ? status(static_cast<Status>(decided->status)) : 0;
        if (!decided->slot)
            return result;
        const auto slot = decided->slot - 1, record = table_.outputs[slot].file;
        if (!table_.outputs[slot].state || record + 1 != decided->file || records_[record].state != 1)
            return broken();
        if (decided->status == 0) {
            if (decided->inode != table_.inodes + 1)
                return broken();
            if (decided->replaced) {
                auto &replaced = records_[decided->replaced - 1];
                if (replaced.state != 2 || (replaced.opens != 0) != (decided->state == 3))
                    return broken();
                if (decided->state == 3)
                    replaced.state = 3;
                else if (!free_record(decided->replaced - 1))
                    return broken();
            }
            records_[record].state = 2;
            records_[record].inode = table_.inodes = decided->inode;
        }
        if (!end_output(slot, decided->release))
            return broken();
        return result;
    }
    [[nodiscard]] auto discard(U64 id) -> Result {
        const auto decided = process::file_discard(table_bytes(), id);
        if (!decided)
            return broken();
        Result result;
        if (!decided->slot) {
            result.value = status(Status::invalid_handle);
            return result;
        }
        const auto slot = decided->slot - 1;
        if (!table_.outputs[slot].state || table_.outputs[slot].file + 1 != decided->file ||
            !end_output(slot, true))
            return broken();
        return result;
    }
    [[nodiscard]] auto close(U64 id) -> Result {
        const auto decided = process::file_close(overlay_bytes(), table_bytes(), id);
        if (!decided)
            return broken();
        Result result;
        if (!decided->slot) {
            result.value = status(Status::invalid_handle);
            return result;
        }
        auto &handle = table_.handles[decided->slot - 1];
        if (!handle.state || (handle.state == 3) != (decided->file != 0) ||
            (decided->file && handle.target + 1 != decided->file))
            return broken();
        if (decided->file) {
            auto &record = records_[handle.target];
            if ((record.state != 2 && record.state != 3) || record.opens == 0 ||
                decided->release != (record.state == 3 && record.opens == 1))
                return broken();
            --record.opens;
            if (decided->release && !free_record(handle.target))
                return broken();
        }
        handle.state = 0;
        return result;
    }
    // The process ended: every output ends and every handle closes, as the
    // Linux binding's finish does; then each committed file, in record order,
    // goes to export(record) and every record is freed. False when an
    // invariant broke or a frame stays held.
    template <class Export> [[nodiscard]] auto finish(Export export_file) -> bool {
        for (U64 slot = 0; slot < process::file_outputs; ++slot)
            if (table_.outputs[slot].state && !end_output(slot, true))
                return false;
        for (auto &handle : table_.handles) {
            if (handle.state == 3) {
                if (!records_[handle.target].opens)
                    return false;
                --records_[handle.target].opens;
            }
            handle.state = 0;
        }
        for (U64 record = 0; record < process::file_records; ++record) {
            if (records_[record].state == 2 && !export_file(record))
                return false;
            if (records_[record].state && (records_[record].opens || !free_record(record)))
                return false;
        }
        table_ = Table{};
        const auto clean = store_->charged_files() == 0;
        store_ = nullptr;
        return clean;
    }
    [[nodiscard]] auto record(U64 index) const -> const Record & {
        return records_[index];
    }
    // A committed record's path: its directory's bytes in the volume, "/"
    // unless that is the root, and the leaf.
    template <class Put> [[nodiscard]] auto path(U64 index, Put put) const -> bool {
        const auto &held = records_[index];
        const auto prefix = process::directory_prefix(volume_, held.first, held.depth);
        const auto name = process::volume_name(volume_, held.first);
        if (!prefix || (held.depth && (!name || *prefix > name->size())))
            return false;
        for (U64 at = 0; at < *prefix; ++at)
            put(std::to_integer<std::uint8_t>((*name)[at]));
        if (held.depth)
            put(std::uint8_t{'/'});
        for (U64 at = 0; at < held.leaf_length; ++at)
            put(std::to_integer<std::uint8_t>(held.leaf[at]));
        return true;
    }
    // Bytes [offset, offset + out.size()) of a linked record.
    [[nodiscard]] auto bytes(U64 index, U64 offset, std::span<std::byte> out) -> bool {
        const auto &held = records_[index];
        if (offset > held.size || out.size() > held.size - offset)
            return false;
        for (U64 done = 0; done < out.size();) {
            const auto at = offset + done, within = at % frame_bytes;
            const auto count = least(frame_bytes - within, out.size() - done);
            const auto frame = data_frame(index, at / frame_bytes);
            if (!frame || !store_->copy_out(frame, within, out.subspan(done, count)))
                return false;
            done += count;
        }
        return true;
    }
};
} // namespace aurora::uefi
