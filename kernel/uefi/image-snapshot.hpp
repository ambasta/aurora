#pragma once
#include "kernel-space.hpp"

namespace aurora::uefi {
// A bounded loader copy, never a filesystem. A service handle pins the source
// version while this supervisor-only snapshot is filled. Its future process
// owner holds every frame; the exact walk and mapping words account for it
// before that process exists. Release precedes the process's first full walk.
class ImageSnapshot final {
public:
    using U64 = std::uint64_t;
    static constexpr U64 base = KernelSpace::extension + (U64{2} << 30), limit = U64{1} << 26;
    static constexpr U64 rw = 3 | PageTables::nx, ro = 1 | PageTables::nx;

private:
    KernelSpace &space_;
    frames::Table &frames_;
    const frames::Ranges &ranges_;
    std::span<U64> mappings_;
    U64 owner_, bytes_, directory_ = 0, held_ = 0;
    bool sealed_ = false;

    [[nodiscard]] static constexpr auto data_word(U64 page) -> U64 {
        return (base + page * frames::page) | 3;
    }
    [[nodiscard]] static constexpr auto table_word(U64 index) -> U64 {
        return (base + index * 2097152) | 4;
    }
    static constexpr U64 directory_word = base | 5;
    [[nodiscard]] auto own(U64 physical, U64 mapping) const -> bool {
        const auto index = ranges_.index(physical);
        if (!index || *index >= mappings_.size())
            return false;
        const auto record = frames_.record(*index);
        return frames::state(record) == static_cast<U64>(frames::State::allocated) && frames::word(record) == owner_ &&
               mappings_[*index] == mapping;
    }
    [[nodiscard]] auto make(U64 mapping) -> U64 {
        const auto frame = frames_.allocate(owner_);
        if (!frame)
            return 0;
        const auto physical = frames_.address(frame->index);
        auto *view = physical ? space_.open(*physical) : nullptr;
        if (!view || mappings_[frame->index])
            return 0;
        for (U64 at = 0; at < frames::page / 8; ++at)
            reinterpret_cast<volatile U64 *>(view)[at] = 0;
        space_.close();
        mappings_[frame->index] = mapping;
        ++held_;
        return *physical;
    }
    [[nodiscard]] auto read(U64 physical, U64 slot) const -> std::optional<U64> {
        auto *view = space_.open(physical);
        if (!view || slot >= 512)
            return std::nullopt;
        const U64 value = reinterpret_cast<volatile U64 *>(view)[slot];
        space_.close();
        return value;
    }
    [[nodiscard]] auto write(U64 physical, U64 slot, U64 value) -> bool {
        auto *view = space_.open(physical);
        if (!view || slot >= 512)
            return false;
        reinterpret_cast<volatile U64 *>(view)[slot] = value;
        space_.close();
        return true;
    }
    [[nodiscard]] auto drop(U64 physical, U64 mapping) -> bool {
        if (!own(physical, mapping))
            return false;
        const auto index = ranges_.index(physical);
        auto *view = space_.open(physical);
        if (!view)
            return false;
        for (U64 at = 0; at < frames::page / 8; ++at)
            reinterpret_cast<volatile U64 *>(view)[at] = 0;
        space_.close();
        mappings_[*index] = 0;
        if (frames_.release({*index, frames::generation(frames_.record(*index))}, owner_) != frames::Rejection::none)
            return false;
        --held_;
        return true;
    }
    static auto flush() -> void {
        U64 root;
        asm volatile("mov %%cr3, %0; mov %0, %%cr3" : "=r"(root) : : "memory");
    }

public:
    ImageSnapshot(KernelSpace &space,
                  frames::Table &frames,
                  const frames::Ranges &ranges,
                  std::span<U64> mappings,
                  U64 owner,
                  U64 bytes)
        : space_(space), frames_(frames), ranges_(ranges), mappings_(mappings), owner_(owner), bytes_(bytes) {
    }
    ImageSnapshot(const ImageSnapshot &) = delete;
    auto operator=(const ImageSnapshot &) -> ImageSnapshot & = delete;
    [[nodiscard]] static constexpr auto cost(U64 bytes) -> U64 {
        const U64 pages = (bytes + frames::page - 1) / frames::page;
        return pages + (pages + 511) / 512 + 1;
    }
    [[nodiscard]] auto held() const -> U64 {
        return held_;
    }
    [[nodiscard]] auto owner() const -> U64 {
        return owner_;
    }
    [[nodiscard]] auto bytes() const -> std::span<const std::byte> {
        return {reinterpret_cast<const std::byte *>(base), bytes_};
    }
    [[nodiscard]] auto writable() -> std::span<std::byte> {
        return sealed_ ? std::span<std::byte>{} : std::span<std::byte>{reinterpret_cast<std::byte *>(base), bytes_};
    }
    [[nodiscard]] auto begin() -> bool {
        if (!bytes_ || bytes_ > limit || directory_ || KernelSpace::table_view(0)[2])
            return false;
        directory_ = make(directory_word);
        if (!directory_)
            return false;
        const U64 pages = (bytes_ + frames::page - 1) / frames::page;
        for (U64 page = 0; page < pages;) {
            const U64 index = page / 512, table = make(table_word(index));
            if (!table || !write(directory_, index, table | KernelSpace::table_flags))
                return false;
            for (U64 slot = 0; slot < 512 && page < pages; ++slot, ++page) {
                const U64 data = make(data_word(page));
                if (!data || !write(table, slot, data | rw))
                    return false;
            }
        }
        KernelSpace::table_view(0)[2] = directory_ | KernelSpace::table_flags;
        flush();
        return verify();
    }
    [[nodiscard]] auto verify() const -> bool {
        if (!directory_ || !own(directory_, directory_word) ||
            (KernelSpace::table_view(0)[2] & ~KernelSpace::hardware_bits) != (directory_ | KernelSpace::table_flags))
            return false;
        const U64 pages = (bytes_ + frames::page - 1) / frames::page, tables = (pages + 511) / 512;
        U64 seen = 1;
        for (U64 index = 0; index < 512; ++index) {
            const auto entry = read(directory_, index);
            if (!entry)
                return false;
            if (index >= tables) {
                if (*entry)
                    return false;
                continue;
            }
            const U64 table = *entry & KernelSpace::address_mask;
            if ((*entry & ~KernelSpace::address_mask & ~KernelSpace::hardware_bits) != KernelSpace::table_flags ||
                !own(table, table_word(index)))
                return false;
            ++seen;
            for (U64 slot = 0; slot < 512; ++slot) {
                const auto leaf = read(table, slot);
                if (!leaf)
                    return false;
                const U64 page = index * 512 + slot;
                if (page >= pages) {
                    if (*leaf)
                        return false;
                } else {
                    if ((*leaf & ~KernelSpace::address_mask & ~KernelSpace::hardware_bits) != (sealed_ ? ro : rw) ||
                        !own(*leaf & KernelSpace::address_mask, data_word(page)))
                        return false;
                    ++seen;
                }
            }
        }
        return seen == held_ && held_ == cost(bytes_);
    }
    [[nodiscard]] auto seal() -> bool {
        if (!verify() || sealed_)
            return false;
        const U64 pages = (bytes_ + frames::page - 1) / frames::page;
        for (U64 page = 0; page < pages; ++page) {
            const auto directory = read(directory_, page / 512);
            const U64 table = *directory & KernelSpace::address_mask;
            const auto leaf = read(table, page % 512);
            if (!write(table, page % 512, (*leaf & KernelSpace::address_mask) | ro))
                return false;
        }
        sealed_ = true;
        flush();
        return verify();
    }
    [[nodiscard]] auto release() -> bool {
        if (!directory_)
            return held_ == 0;
        KernelSpace::table_view(0)[2] = 0;
        flush();
        for (U64 index = 0; index < 512; ++index) {
            const auto entry = read(directory_, index);
            if (!entry)
                return false;
            if (!*entry)
                continue;
            const U64 table = *entry & KernelSpace::address_mask;
            if (!own(table, table_word(index)))
                return false;
            for (U64 slot = 0; slot < 512; ++slot) {
                const auto leaf = read(table, slot);
                if (!leaf || (*leaf && !drop(*leaf & KernelSpace::address_mask, data_word(index * 512 + slot))))
                    return false;
            }
            if (!drop(table, table_word(index)))
                return false;
        }
        if (!drop(directory_, directory_word))
            return false;
        directory_ = 0;
        return held_ == 0;
    }
};
} // namespace aurora::uefi
