#pragma once
#include "handoff.hpp"
#include <array>
#include <optional>
#include <string_view>

namespace aurora::uefi {
class FirmwareRanges final {
    std::span<const std::byte> map_;
    std::size_t stride_;
    std::uint64_t arena_;
    unsigned physical_bits_;
public:
    FirmwareRanges(std::span<const std::byte> map, std::size_t stride,
                   std::uint64_t arena, unsigned bits)
        : map_(map), stride_(stride), arena_(arena), physical_bits_(bits) {}
    [[nodiscard]] auto readable(std::uint64_t begin, std::uint64_t bytes) const -> bool {
        if (physical_bits_ < 32 || physical_bits_ > 52 || bytes == 0
            || begin > ~std::uint64_t{0} - bytes)
            return false;
        const auto end = begin + bytes;
        if (end > (1ULL << physical_bits_)
            || (begin < arena_ + Handoff::arena_bytes && arena_ < end)
            || !MemoryMap{map_, stride_, 1}.valid())
            return false;
        auto cursor = begin;
        while (cursor < end) {
            bool advanced = false;
            for (std::size_t offset = 0; offset < map_.size(); offset += stride_) {
                const Bytes entry{map_.subspan(offset, stride_)};
                const auto start = entry.get(8),
                           limit = start + entry.get(24) * 4096,
                           type = entry.get(0, 4);
                if (cursor < start || cursor >= limit)
                    continue;
                // Firmware-data readability is not allocator ownership. Runtime data stays reserved.
                if (!(type == 2 || type == 4 || type == 6 || type == 9 || type == 10)
                    || !(entry.get(32) & 8) || (entry.get(32) & 0x8000))
                    return false;
                cursor = limit < end ? limit : end;
                advanced = true;
                break;
            }
            if (!advanced)
                return false;
        }
        return true;
    }
};

class ReadChunk final {
public:
    std::uint64_t page{}, offset{}, count{};
};

class ReadPlan final {
    std::uint64_t physical_, size_;
public:
    constexpr ReadPlan(std::uint64_t physical, std::uint64_t size)
        : physical_(physical), size_(size) {}
    [[nodiscard]] auto next(std::uint64_t done) const -> std::optional<ReadChunk> {
        if (size_ == 0 || size_ > 65536 || physical_ > ~std::uint64_t{0} - size_ || done >= size_)
            return std::nullopt;
        const auto cursor = physical_ + done, offset = cursor % 4096;
        return ReadChunk{cursor - offset, offset,
                         size_ - done < 4096 - offset ? size_ - done : 4096 - offset};
    }
};

class WindowTicket final {
    friend class WindowAuthority;
    std::uint64_t stamp_{};
    explicit WindowTicket(std::uint64_t stamp) : stamp_(stamp) {}
public:
    WindowTicket() = default;
};

class WindowAuthority final {
    inline static std::uint64_t next_ = 0;
    std::uint64_t active_{};
public:
    WindowAuthority() = default;
    WindowAuthority(const WindowAuthority&) = delete;
    auto operator=(const WindowAuthority&) -> WindowAuthority& = delete;
    [[nodiscard]] auto acquire() -> std::optional<WindowTicket> {
        if (active_ || next_ == ~std::uint64_t{0})
            return std::nullopt;
        active_ = ++next_;
        return WindowTicket{active_};
    }
    [[nodiscard]] auto accepts(WindowTicket ticket) const -> bool {
        return active_ && ticket.stamp_ == active_;
    }
    [[nodiscard]] auto revoke(WindowTicket ticket) -> bool {
        if (!accepts(ticket))
            return false;
        active_ = 0;
        return true;
    }
};

class AcpiRoots final {
    std::uint64_t root_{};
    bool failed_{};
public:
    [[nodiscard]] auto accept(std::span<const std::byte> entry) -> bool {
        if (failed_ || entry.size() != 24) {
            failed_ = true;
            return false;
        }
        constexpr std::array<unsigned char, 16> guid{
            0x71, 0xe8, 0x68, 0x88, 0xf1, 0xe4, 0xd3, 0x11,
            0xbc, 0x22, 0, 0x80, 0xc7, 0x3c, 0x88, 0x81};
        for (std::size_t i = 0; i < 16; ++i)
            if (std::to_integer<unsigned char>(entry[i]) != guid[i])
                return true;
        if (root_) {
            failed_ = true;
            return false;
        }
        root_ = Bytes{entry}.get(16);
        failed_ = root_ == 0;
        return !failed_;
    }
    [[nodiscard]] auto root() const -> std::uint64_t { return failed_ ? 0 : root_; }
};

class Acpi final {
public:
    static constexpr std::size_t maximum_table = 65536;
    static constexpr std::size_t maximum_entries = 128;
    [[nodiscard]] static auto signature(std::span<const std::byte> bytes, std::string_view name)
        -> bool {
        if (bytes.size() < name.size())
            return false;
        for (std::size_t i = 0; i < name.size(); ++i)
            if (std::to_integer<unsigned char>(bytes[i]) != static_cast<unsigned char>(name[i]))
                return false;
        return true;
    }
    [[nodiscard]] static auto checksum(std::span<const std::byte> bytes) -> bool {
        unsigned sum = 0;
        for (auto byte : bytes)
            sum += std::to_integer<unsigned char>(byte);
        return (sum & 255) == 0;
    }
    [[nodiscard]] static auto same_header(std::span<const std::byte> snapshot,
                                         std::span<const std::byte> header) -> bool {
        if (snapshot.size() < header.size() || header.empty())
            return false;
        for (std::size_t i = 0; i < header.size(); ++i)
            if (snapshot[i] != header[i])
                return false;
        return true;
    }
    [[nodiscard]] static auto rsdp(std::span<const std::byte> bytes)
        -> std::optional<std::uint64_t> {
        if (bytes.size() < 36 || bytes.size() > 4096 || !signature(bytes, "RSD PTR ")
            || Bytes{bytes}.get(15, 1) != 2 || Bytes{bytes}.get(20, 4) != bytes.size()
            || !checksum(bytes.first(20)) || !checksum(bytes))
            return std::nullopt;
        const auto root = Bytes{bytes}.get(24);
        if (!root || Bytes{bytes}.get(33, 3) != 0)
            return std::nullopt;
        return root;
    }
    [[nodiscard]] static auto table(std::span<const std::byte> bytes, std::string_view sig)
        -> bool {
        return bytes.size() >= 36 && bytes.size() <= maximum_table && signature(bytes, sig)
            && Bytes{bytes}.get(4, 4) == bytes.size() && checksum(bytes)
            && (sig == "XSDT"
                    ? Bytes{bytes}.get(8, 1) == 1
                    : sig != "APIC"
                        || (Bytes{bytes}.get(8, 1) >= 1 && Bytes{bytes}.get(8, 1) <= 6));
    }
    [[nodiscard]] static auto xsdt(std::span<const std::byte> bytes, std::uint64_t self) -> bool {
        if (!table(bytes, "XSDT") || (bytes.size() - 36) % 8
            || (bytes.size() - 36) / 8 > maximum_entries)
            return false;
        for (std::size_t i = 36; i < bytes.size(); i += 8) {
            const auto address = Bytes{bytes}.get(i);
            if (!address || address == self)
                return false;
            for (std::size_t j = 36; j < i; j += 8)
                if (Bytes{bytes}.get(j) == address)
                    return false;
        }
        return true;
    }
};

class Processor final {
public:
    std::uint32_t id{}, uid{};
    bool enabled{}, online_capable{}, extended{};
};

class Topology final {
    std::array<Processor, 256> processors_{};
    std::size_t count_{};
    std::uint64_t apic_{};
public:
    [[nodiscard]] auto count() const -> std::size_t { return count_; }
    [[nodiscard]] auto processors() const -> std::span<const Processor> {
        return {processors_.data(), count_};
    }
    [[nodiscard]] auto apic() const -> std::uint64_t { return apic_; }
    [[nodiscard]] static auto parse(std::span<const std::byte> bytes, unsigned physical_bits)
        -> std::optional<Topology> {
        if (!Acpi::table(bytes, "APIC") || bytes.size() < 44
            || physical_bits < 32 || physical_bits > 52 || (Bytes{bytes}.get(40, 4) & ~1ULL))
            return std::nullopt;
        Topology result;
        result.apic_ = Bytes{bytes}.get(36, 4);
        bool override_seen = false;
        for (std::size_t at = 44; at < bytes.size();) {
            if (bytes.size() - at < 2)
                return std::nullopt;
            const auto type = Bytes{bytes}.get(at, 1), length = Bytes{bytes}.get(at + 1, 1);
            if (length < 2 || length > bytes.size() - at)
                return std::nullopt;
            const auto record = bytes.subspan(at, length);
            const Bytes r{record};
            if (type == 0 || type == 9) {
                if (length != (type == 0 ? 8 : 16) || (type == 9 && r.get(2, 2) != 0)
                    || result.count_ == result.processors_.size())
                    return std::nullopt;
                Processor cpu;
                cpu.id = r.get(type == 0 ? 3 : 4, type == 0 ? 1 : 4);
                cpu.uid = r.get(type == 0 ? 2 : 12, type == 0 ? 1 : 4);
                const auto flags = r.get(type == 0 ? 4 : 8, 4);
                if (flags & ~3ULL)
                    return std::nullopt;
                cpu.enabled = flags & 1;
                cpu.online_capable = flags & 2;
                cpu.extended = type == 9;
                for (const auto& previous : result.processors())
                    if (previous.id == cpu.id || previous.uid == cpu.uid)
                        return std::nullopt;
                result.processors_[result.count_++] = cpu;
            } else if (type == 5) {
                if (length != 12 || override_seen || r.get(2, 2) != 0)
                    return std::nullopt;
                override_seen = true;
                result.apic_ = r.get(4);
            }
            at += length;
        }
        if (!result.apic_ || result.apic_ % 4096
            || result.apic_ > (1ULL << physical_bits) - 4096 || result.count_ == 0)
            return std::nullopt;
        return result;
    }
};
}
