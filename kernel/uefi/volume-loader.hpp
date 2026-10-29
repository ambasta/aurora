#pragma once
// Firmware-only boot volume reader (kernel/uefi/process.md#boot-volume). Before
// the final map, the loader opens one file of its own ESP through the loaded
// image's EFI_SIMPLE_FILE_SYSTEM_PROTOCOL, bounds it, reads it into fresh
// EfiLoaderData pages, zeroes the last page's tail and closes every handle.
// Only the page address and byte length cross into the handoff; the kernel
// confirms both against the final map and admits the bytes in Aurora.
#include "handoff.hpp"
#include <array>
#include <initializer_list>

namespace aurora::uefi {
class VolumeLoader final {
    using U64 = std::uint64_t;
    using HandleProtocol = U64(__attribute__((ms_abi)) *)(void *, const void *, void **);
    using OpenVolume = U64(__attribute__((ms_abi)) *)(void *, void **);
    using Open = U64(__attribute__((ms_abi)) *)(void *, void **, const char16_t *, U64, U64);
    using Close = U64(__attribute__((ms_abi)) *)(void *);
    using Read = U64(__attribute__((ms_abi)) *)(void *, U64 *, void *);
    using Info = U64(__attribute__((ms_abi)) *)(void *, const void *, U64 *, void *);
    using Allocate = U64(__attribute__((ms_abi)) *)(unsigned, unsigned, U64, U64 *);
    static constexpr auto guid(std::uint32_t a, std::uint16_t b, std::uint16_t c, std::array<std::uint8_t, 8> d)
        -> std::array<std::byte, 16> {
        std::array<std::byte, 16> result{};
        for (unsigned i = 0; i < 4; ++i)
            result[i] = std::byte(a >> (8 * i));
        for (unsigned i = 0; i < 2; ++i) {
            result[4 + i] = std::byte(b >> (8 * i));
            result[6 + i] = std::byte(c >> (8 * i));
        }
        for (unsigned i = 0; i < 8; ++i)
            result[8 + i] = std::byte(d[i]);
        return result;
    }
    static auto view(U64 address, std::size_t size) -> std::span<const std::byte> {
        return {reinterpret_cast<const std::byte *>(address), size};
    }
    // A protocol interface whose first `size` bytes hold nonzero 8-byte-aligned entries at `entries`.
    [[nodiscard]] static auto interface(void *pointer, std::size_t size, std::initializer_list<std::size_t> entries)
        -> std::optional<Bytes> {
        const auto address = reinterpret_cast<U64>(pointer);
        if (!address || address % 8)
            return std::nullopt;
        const Bytes bytes{view(address, size)};
        for (const auto offset : entries)
            if (!bytes.get(offset))
                return std::nullopt;
        return bytes;
    }
    [[nodiscard]] static auto read_file(const Bytes &boot, void *file, U64 bytes) -> std::optional<U64> {
        U64 address = 0;
        if (reinterpret_cast<Allocate>(boot.get(40))(0, 2, (bytes + 4095) / 4096, &address) != 0 || !address ||
            address % 4096)
            return std::nullopt;
        const auto file_protocol = interface(file, 72, {32});
        if (!file_protocol)
            return std::nullopt;
        // Bounded: each successful read makes progress, and the file has `bytes` bytes.
        for (U64 done = 0; done < bytes;) {
            U64 size = bytes - done;
            if (reinterpret_cast<Read>(file_protocol->get(32))(file, &size, reinterpret_cast<void *>(address + done)) !=
                    0 ||
                size == 0 || size > bytes - done)
                return std::nullopt;
            done += size;
        }
        auto *tail = reinterpret_cast<std::byte *>(address);
        for (auto at = bytes; at % 4096; ++at)
            tail[at] = std::byte{0};
        return address;
    }

public:
    static constexpr U64 limit = Handoff::volume_limit;
    class Volume final {
    public:
        U64 address = 0, bytes = 0;
    };
    // The ESP file `path` of the loaded image's own device, or nullopt.
    [[nodiscard]] static auto read(const Bytes &boot, void *image, const char16_t *path) -> std::optional<Volume> {
        static constexpr auto loaded_image =
            guid(0x5b1b31a1, 0x9562, 0x11d2, {0x8e, 0x3f, 0x00, 0xa0, 0xc9, 0x69, 0x72, 0x3b});
        static constexpr auto file_system =
            guid(0x964e5b22, 0x6459, 0x11d2, {0x8e, 0x39, 0x00, 0xa0, 0xc9, 0x69, 0x72, 0x3b});
        static constexpr auto file_info =
            guid(0x09576e92, 0x6d3f, 0x11d2, {0x8e, 0x39, 0x00, 0xa0, 0xc9, 0x69, 0x72, 0x3b});
        if (!boot.get(152) || !boot.get(40))
            return std::nullopt;
        const auto handle = reinterpret_cast<HandleProtocol>(boot.get(152));
        void *loaded = nullptr, *system = nullptr, *root = nullptr, *file = nullptr;
        if (handle(image, loaded_image.data(), &loaded) != 0)
            return std::nullopt;
        const auto image_protocol = interface(loaded, 32, {24});
        if (!image_protocol ||
            handle(reinterpret_cast<void *>(image_protocol->get(24)), file_system.data(), &system) != 0)
            return std::nullopt;
        const auto volume_protocol = interface(system, 16, {8});
        if (!volume_protocol || reinterpret_cast<OpenVolume>(volume_protocol->get(8))(system, &root) != 0)
            return std::nullopt;
        const auto root_protocol = interface(root, 72, {8, 16});
        if (!root_protocol)
            return std::nullopt;
        std::optional<Volume> result;
        if (reinterpret_cast<Open>(root_protocol->get(8))(root, &file, path, 1, 0) == 0) {
            const auto file_protocol = interface(file, 72, {16, 32, 64});
            // EFI_FILE_INFO: Size, FileSize, PhysicalSize, three times, Attribute, FileName.
            alignas(8) std::array<std::byte, 256> info{};
            U64 info_size = info.size();
            if (file_protocol &&
                reinterpret_cast<Info>(file_protocol->get(64))(file, file_info.data(), &info_size, info.data()) == 0 &&
                info_size >= 82 && info_size <= info.size()) {
                const Bytes fields{std::span<const std::byte>{info}};
                const auto bytes = fields.get(8);
                if (fields.get(0) >= 82 && fields.get(0) <= info_size && (fields.get(72) & 0x10) == 0 && bytes &&
                    bytes <= limit)
                    if (const auto address = read_file(boot, file, bytes))
                        result = Volume{*address, bytes};
            }
            if (!file_protocol || reinterpret_cast<Close>(file_protocol->get(16))(file) != 0)
                result.reset();
        }
        if (reinterpret_cast<Close>(root_protocol->get(16))(root) != 0)
            return std::nullopt;
        return result;
    }
};
} // namespace aurora::uefi
