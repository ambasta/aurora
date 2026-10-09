#pragma once
#include "acpi-policy.hpp"
#include "../console.hpp"
namespace aurora::uefi {
// Temporary UEFI64 transport only. No PCI writes, driver connection, MMIO or DMA
// call is exposed here. Protocol offsets follow UEFI PCI bus-support interfaces.
class BarLoader final {
    using U64 = std::uint64_t;
    using Map = U64(__attribute__((ms_abi)) *)(U64 *, void *, U64 *, U64 *, std::uint32_t *);
    using Locate = U64(__attribute__((ms_abi)) *)(unsigned, const void *, void *, U64 *, U64 *);
    using Handle = U64(__attribute__((ms_abi)) *)(void *, const void *, U64 *);
    using Free = U64(__attribute__((ms_abi)) *)(void *);
    using ReadConfig = U64(__attribute__((ms_abi)) *)(void *, unsigned, std::uint32_t, U64, void *);
    using Location = U64(__attribute__((ms_abi)) *)(void *, U64 *, U64 *, U64 *, U64 *);
    using Bar = U64(__attribute__((ms_abi)) *)(void *, std::uint8_t, U64 *, U64 *);
    using Configuration = U64(__attribute__((ms_abi)) *)(void *, U64 *);
    Bytes boot_;
    U64 arena_, map_size_{}, stride_{};
    unsigned bits_{};
    [[nodiscard]] static auto view(U64 address, std::size_t size) -> std::span<std::byte> {
        return {reinterpret_cast<std::byte *>(address), size};
    }
    [[nodiscard]] auto refresh() -> bool {
        U64 size = MemoryMap::max_bytes, key{}, stride{};
        std::uint32_t version{};
        if (!boot_.get(56) ||
            reinterpret_cast<Map>(boot_.get(56))(
                &size, reinterpret_cast<void *>(arena_ + Handoff::map_offset), &key, &stride, &version) ||
            size == 0 || size > MemoryMap::max_bytes)
            return false;
        if (!MemoryMap{view(arena_ + Handoff::map_offset, size), stride, version}.valid())
            return false;
        map_size_ = size;
        stride_ = stride;
        return true;
    }
    [[nodiscard]] auto readable(U64 address, std::size_t count) const -> bool {
        return FirmwareRanges{view(arena_ + Handoff::map_offset, map_size_), stride_, arena_, bits_}.readable(address,
                                                                                                              count);
    }
    [[nodiscard]] auto release(U64 pointer) const -> bool {
        return pointer && boot_.get(72) &&
               reinterpret_cast<Free>(boot_.get(72))(reinterpret_cast<void *>(pointer)) == 0;
    }
    [[nodiscard]] auto locate(const std::array<std::byte, 16> &guid, U64 &count, U64 &handles) -> bool {
        return boot_.get(312) &&
               reinterpret_cast<Locate>(boot_.get(312))(2, guid.data(), nullptr, &count, &handles) == 0 && count > 0 &&
               count <= 128 && refresh() && readable(handles, count * 8);
    }
    [[nodiscard]] auto protocol(U64 handle, const std::array<std::byte, 16> &guid, std::size_t size)
        -> std::optional<U64> {
        U64 result{};
        if (!boot_.get(152) ||
            reinterpret_cast<Handle>(boot_.get(152))(reinterpret_cast<void *>(handle), guid.data(), &result) ||
            !refresh() || result % 8 || !readable(result, size))
            return std::nullopt;
        return result;
    }
    [[nodiscard]] auto descriptors(U64 source, std::span<std::byte> destination, unsigned maximum)
        -> std::optional<std::size_t> {
        if (!refresh() || source == 0)
            return std::nullopt;
        std::size_t size = 0;
        for (unsigned count = 0; count <= maximum; ++count) {
            if (size > destination.size() - 2 || !readable(source + size, 2))
                return std::nullopt;
            const auto head = Bytes{view(source + size, 2)}.get(0, 2);
            if ((head & 255) == 0x79) {
                size += 2;
                break;
            }
            if (count == maximum || (head & 255) != 0x8a || size > destination.size() - 46 ||
                !readable(source + size, 46) || Bytes{view(source + size, 46)}.get(1, 2) != 43)
                return std::nullopt;
            size += 46;
        }
        if (size < 48 || size > destination.size() || !readable(source, size))
            return std::nullopt;
        for (std::size_t i = 0; i < size; ++i)
            destination[i] = view(source, size)[i];
        for (std::size_t i = 0; i < size; ++i)
            if (destination[i] != view(source, size)[i])
                return std::nullopt;
        if (Bytes{destination.first(size)}.get(size - 2, 2) != 0x79)
            return std::nullopt;
        return size;
    }
    static auto print_descriptor(std::string_view kind, std::span<const std::byte> data) -> void {
        hardware::Serial::text("AURORA_BAR_DESCRIPTOR: kind=");
        hardware::Serial::text(kind);
        hardware::Serial::text(" bytes=");
        hardware::Serial::number(data.size());
        hardware::Serial::text(" data=");
        constexpr std::string_view hex = "0123456789abcdef";
        for (const auto value : data) {
            const auto byte = std::to_integer<unsigned>(value);
            hardware::Serial::text(hex.substr(byte >> 4, 1));
            hardware::Serial::text(hex.substr(byte & 15, 1));
        }
        hardware::Serial::text("\r\n");
    }

public:
    static constexpr U64 offset = Handoff::bar_record_offset, record_bytes = 4096, magic = 0x3152414241525541ULL;
    BarLoader(const Bytes &boot, U64 arena, unsigned bits) : boot_(boot), arena_(arena), bits_(bits) {
    }

#ifdef AURORA_UEFI_IOMMU_EVENT
private:
    [[nodiscard]] auto capture_profile(bool event) -> bool {
#else
    [[nodiscard]] auto capture() -> bool {
#endif
        if (bits_ < 32 || bits_ > 52 || !boot_.get(72))
            return false;
        std::array<std::byte, 16> pci_guid{}, root_guid{};
        put(pci_guid, 0, 0x4ca568b84cf5b200ULL);
        put(pci_guid, 8, 0x9a02503f3eb2ec9eULL);
        put(root_guid, 0, 0x11d44a1a2f707ebbULL);
        put(root_guid, 8, 0x4dc13f279000389aULL);
        U64 handles{}, count{};
        if (!locate(pci_guid, count, handles))
            return false;
        auto record = view(arena_ + offset, record_bytes);
        unsigned found = 0;
        for (U64 index = 0; index < count; ++index) {
            const auto current = protocol(Bytes{view(handles, count * 8)}.get(index * 8), pci_guid, 160);
            if (!current)
                return false;
            const Bytes io{view(*current, 160)};
            if (!io.get(48) || !io.get(112) || !io.get(128))
                return false;
            std::array<std::byte, 64> config{}, second{};
            const auto read = reinterpret_cast<ReadConfig>(io.get(48));
            if (read(reinterpret_cast<void *>(*current), 2, 0, 16, config.data()) ||
                read(reinterpret_cast<void *>(*current), 2, 0, 16, second.data()) || config != second)
                return false;
            const Bytes header{config};
            std::array<U64, 4> where{};
            if (reinterpret_cast<Location>(io.get(112))(
                    reinterpret_cast<void *>(*current), &where[0], &where[1], &where[2], &where[3]) ||
                where[0] != 0 || where[1] > 255 || where[2] > 31 || where[3] > 7)
                return false;
#ifdef AURORA_UEFI_IOMMU_EVENT
            const bool target = event ? header.get(0, 4) == 0x11e81234 && header.get(9, 3) == 0x00ff00 &&
                                            header.get(14, 1) == 0 && where[1] == 0 && where[2] == 4 && where[3] == 0
                                      : header.get(0, 4) == 0x00101b36 && header.get(9, 3) == 0x010802 &&
                                            header.get(14, 1) == 0 && where[1] == 0 && where[2] == 2 && where[3] == 0;
            if (!event && header.get(9, 3) == 0x010802 && !target)
                return false;
            if (event) {
                const auto facts = Bytes{record}.get(96);
                if (facts >= 6)
                    return false;
                auto fact = record.subspan(576 + facts * 72, 72);
                put(fact, 0, where[0], 2);
                put(fact, 2, where[1], 1);
                put(fact, 3, where[2], 1);
                put(fact, 4, where[3], 1);
                for (std::size_t byte = 0; byte < 64; ++byte)
                    fact[8 + byte] = config[byte];
                put(record, 96, facts + 1);
                if (header.get(0, 4) == 0x14191022) {
                    if (Bytes{record}.get(104) != 0)
                        return false;
                    std::array<std::byte, 48> capability{}, again{};
                    if (read(reinterpret_cast<void *>(*current), 2, 0x40, 12, capability.data()) ||
                        read(reinterpret_cast<void *>(*current), 2, 0x40, 12, again.data()) || capability != again)
                        return false;
                    put(record, 104, 1);
                    put(record, 112, (where[1] << 8) | (where[2] << 3) | where[3]);
                    for (std::size_t byte = 0; byte < 48; ++byte)
                        record[128 + byte] = capability[byte];
                }
            }
#else
            const bool target = header.get(0, 4) == 0x00101b36 && header.get(9, 3) == 0x010802 &&
                                header.get(14, 1) == 0 && where[1] == 0 && where[2] == 2 && where[3] == 0;
            if (header.get(9, 3) == 0x010802 && !target)
                return false;
#endif
            const auto header_type = header.get(14, 1) & 127;
            if (header_type > 1)
                return false;
            const unsigned slots = header_type == 0 ? 6 : 2;
            for (unsigned bar_index = 0; bar_index < slots; ++bar_index) {
                const auto low = header.get(16 + bar_index * 4, 4);
                if (!low || (low & 1))
                    continue;
                const auto type = (low >> 1) & 3;
                if ((type != 0 && type != 2) || (type == 2 && bar_index + 1 >= slots))
                    return false;
                const auto physical = (low & ~15ULL) | (type == 2 ? header.get(20 + bar_index * 4, 4) << 32 : 0);
                if (!physical)
                    return false;
                if (!(target && bar_index == 0)) {
                    const auto reservation_count = Bytes{record}.get(88);
                    if (reservation_count >= 8)
                        return false;
                    auto reservation = record.subspan(2048 + reservation_count * 256, 256);
                    U64 source{}, supported{};
                    if (reinterpret_cast<Bar>(io.get(128))(reinterpret_cast<void *>(*current),
                                                           static_cast<std::uint8_t>(bar_index),
                                                           &supported,
                                                           &source))
                        return false;
                    const auto copied = descriptors(source, reservation.subspan(128, 48), 1);
                    if (!copied || !release(source))
                        return false;
                    for (unsigned field = 0; field < 4; ++field)
                        put(reservation, field * 8, where[field]);
                    put(reservation, 32, bar_index);
                    put(reservation, 40, *copied);
                    for (std::size_t byte = 0; byte < 64; ++byte)
                        reservation[64 + byte] = config[byte];
                    put(record, 88, reservation_count + 1);
                }
                if (type == 2)
                    ++bar_index;
            }
#ifdef AURORA_UEFI_IOMMU_EVENT
            if (event ? !target
                      : (header.get(0, 4) != 0x00101b36 || header.get(9, 3) != 0x010802 || header.get(14, 1) != 0))
#else
            if (header.get(0, 4) != 0x00101b36 || header.get(9, 3) != 0x010802 || header.get(14, 1) != 0)
#endif
                continue;
            if (++found != 1)
                return false;
            U64 resources{}, supports{};
            if (reinterpret_cast<Bar>(io.get(128))(reinterpret_cast<void *>(*current), 0, &supports, &resources))
                return false;
            const auto size = descriptors(resources, record.subspan(512, 512), 1);
            if (!size || !release(resources))
                return false;
#ifdef AURORA_UEFI_IOMMU_EVENT
            put(record, 0, event ? event_magic : magic);
#else
            put(record, 0, magic);
#endif
            put(record, 8, 1, 4);
            put(record, 12, record_bytes, 4);
            for (unsigned i = 0; i < 4; ++i)
                put(record, 16 + i * 8, where[i]);
            put(record, 56, *size);
            put(record, 72, 64);
            put(record, 80, supports);
            for (std::size_t i = 0; i < config.size(); ++i)
                record[256 + i] = config[i];
            print_descriptor("bar", record.subspan(512, *size));
        }
        if (!release(handles) || found != 1)
            return false;
        if (!locate(root_guid, count, handles))
            return false;
        unsigned roots = 0;
        for (U64 index = 0; index < count; ++index) {
            const auto current = protocol(Bytes{view(handles, count * 8)}.get(index * 8), root_guid, 152);
            if (!current)
                return false;
            const Bytes root{view(*current, 152)};
            if (root.get(144, 4) != Bytes{record}.get(16))
                continue;
            U64 resources{};
            if (!root.get(136) ||
                reinterpret_cast<Configuration>(root.get(136))(reinterpret_cast<void *>(*current), &resources))
                return false;
            std::array<std::byte, 738> copied{};
            const auto size = descriptors(resources, copied, 16);
            if (!size)
                return false;
            bool covers_bus = false;
            for (std::size_t at = 0; at + 46 <= *size; at += 46) {
                const Bytes descriptor{std::span<const std::byte>{copied}.subspan(at, 46)};
                if (descriptor.get(3, 1) == 2 && descriptor.get(14) <= Bytes{record}.get(24) &&
                    descriptor.get(22) >= Bytes{record}.get(24) && descriptor.get(30) == 0)
                    covers_bus = true;
            }
            if (!covers_bus)
                continue;
            if (++roots != 1)
                return false;
            put(record, 48, root.get(144, 4));
            put(record, 64, *size);
            for (std::size_t i = 0; i < *size; ++i)
                record[1024 + i] = copied[i];
            print_descriptor("root", record.subspan(1024, *size));
        }
#ifdef AURORA_UEFI_IOMMU_EVENT
        return release(handles) && roots == 1 &&
               (!event || (Bytes{record}.get(96) == 6 && Bytes{record}.get(104) == 1));
#else
        return release(handles) && roots == 1;
#endif
    }

#ifdef AURORA_UEFI_IOMMU_EVENT
public:
    static constexpr U64 event_magic = 0x3154564541525541ULL;
    [[nodiscard]] auto capture() -> bool {
        return capture_profile(false);
    }
    [[nodiscard]] auto capture_event() -> bool {
        return capture_profile(true);
    }
#endif
};
} // namespace aurora::uefi
