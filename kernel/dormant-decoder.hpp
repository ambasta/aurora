#ifndef AURORA_AMD310_INDEPENDENT_DECODER_HPP
#define AURORA_AMD310_INDEPENDENT_DECODER_HPP

#include <array>
#include <cstddef>
#include <cstdint>
#include <span>

// An independently authored, CPU-only reader of the AMD310Host4KBus0 profile.
// Reference: AMD 48882-PUB revision 3.10, February 2025, sections 2.2.2 and
// 2.2.2.1 (pp. 63, 71-74), and 2.2.3 (pp. 81-84). This deliberately accepts
// fewer encodings than the architecture: even architecturally ignored fields
// and non-present entries must have the profile's canonical zero values.
//
// The caller supplies a stable copied snapshot and trusted role descriptions.
// Input does not establish ownership, provenance, requester identity, lifetime,
// IOMMU capability, cache visibility, or authority to activate a device. It must
// never be accepted as a service capability or as proof of hardware isolation.
// Concurrent changes to the backing bytes are outside this interface's contract.
// No encoded physical pointer is ever converted into a host pointer.
namespace independent {

class Input {
public:
    std::span<const std::byte> dte{};
    std::span<const std::byte> root{};
    // Physical bases: contiguous DTE pages, root, first data, optional second data.
    std::array<std::uint64_t, 5> pages{};
    std::size_t data_count{};
    std::uint8_t physical_bits{};
    std::array<std::uint64_t, 2> iovas{};
    std::array<bool, 2> writable{};
};

namespace detail {

inline constexpr std::uint64_t page_size = 4096;
inline constexpr std::uint64_t iova_limit = 2097152;
inline constexpr std::uint64_t address_field = 0x000ffffffffff000ULL;
inline constexpr std::uint64_t read_bit = std::uint64_t{1} << 61;
inline constexpr std::uint64_t write_bit = std::uint64_t{1} << 62;

// Bounds are checked before every caller reaches this function. Byte assembly
// makes the interpretation independent of CPU byte order and host alignment.
inline std::uint64_t read_le64(std::span<const std::byte> bytes,
                              std::size_t offset) noexcept {
    std::uint64_t value = 0;
    for (std::size_t byte = 0; byte != 8; ++byte) {
        value |= std::uint64_t{std::to_integer<std::uint8_t>(bytes[offset + byte])}
                 << (byte * 8);
    }
    return value;
}

inline bool complete_physical_page(std::uint64_t base,
                                   std::uint64_t maximum) noexcept {
    return (base & (page_size - 1)) == 0 &&
           base <= maximum - (page_size - 1);
}

} // namespace detail

[[nodiscard]] inline bool validate(const Input& input) noexcept {
    using namespace detail;
    if (input.dte.size() != 8192 || input.root.size() != 4096 ||
        input.physical_bits < 32 || input.physical_bits > 52 ||
        (input.data_count != 1 && input.data_count != 2)) {
        return false;
    }
    if (input.data_count == 1 &&
        (input.pages[4] != 0 || input.iovas[1] != 0 || input.writable[1])) {
        return false;
    }

    const auto maximum = (std::uint64_t{1} << input.physical_bits) - 1;
    const auto used_pages = std::size_t{3} + input.data_count;
    for (std::size_t role = 0; role != used_pages; ++role) {
        if (!complete_physical_page(input.pages[role], maximum)) {
            return false;
        }
        // Equal-size aligned pages overlap exactly when their bases match.
        for (std::size_t other = 0; other != role; ++other) {
            if (input.pages[role] == input.pages[other]) {
                return false;
            }
        }
    }
    // The preceding whole-page check proves this addition cannot wrap.
    if (input.pages[1] != input.pages[0] + page_size) {
        return false;
    }
    for (std::size_t mapping = 0; mapping != input.data_count; ++mapping) {
        if ((input.iovas[mapping] & (page_size - 1)) != 0 ||
            input.iovas[mapping] >= iova_limit) {
            return false;
        }
    }
    if (input.data_count == 2 && input.iovas[0] == input.iovas[1]) {
        return false;
    }

    for (std::size_t rid = 0; rid != 256; ++rid) {
        const auto offset = rid * 32;
        const auto control = read_le64(input.dte, offset);
        const auto domain_and_flags = read_le64(input.dte, offset + 8);
        if (read_le64(input.dte, offset + 16) != 0 ||
            read_le64(input.dte, offset + 24) != 0) {
            return false;
        }
        if (rid != 0x10) {
            // V=TV=1, Mode=0, IR=IW=0, DomainID=0. An all-zero DTE
            // would permit ordinary memory passthrough and is not a denial.
            if (control != 3 || domain_and_flags != 0) {
                return false;
            }
            continue;
        }
        if (domain_and_flags != 1 || (control & address_field) != input.pages[2] ||
            (control & ~address_field) != (read_bit | write_bit | (1ULL << 9) | 3)) {
            return false;
        }
    }

    for (std::size_t index = 0; index != 512; ++index) {
        const auto entry = read_le64(input.root, index * 8);
        std::size_t mapping = 0;
        for (; mapping != input.data_count; ++mapping) {
            if (input.iovas[mapping] / page_size == index) {
                break;
            }
        }
        if (mapping == input.data_count) {
            if (entry != 0) {
                return false;
            }
            continue;
        }
        const auto permissions = read_bit | (input.writable[mapping] ? write_bit : 0);
        if ((entry & address_field) != input.pages[3 + mapping] ||
            (entry & ~address_field) != (permissions | 1)) {
            return false;
        }
    }
    return true;
}

// This is a whole-interval software-model query, never a live-device access.
// Cross-page intervals are accepted only if every touched page is present and
// every page grants the access. Physical contiguity is unnecessary. A hole,
// restrictive leaf, empty interval, upper-address alias, or overflow rejects.
// Validation covers the entire snapshot on every call, including unused slots.
[[nodiscard]] inline bool permits(const Input& input, std::uint16_t rid,
                                 std::uint64_t iova, std::uint64_t length,
                                 bool write) noexcept {
    using namespace detail;
    if (!validate(input) || rid != 0x10 || length == 0 || iova >= iova_limit ||
        length > iova_limit - iova) {
        return false;
    }

    const auto parent = read_le64(input.dte, 0x10 * 32);
    const auto required = write ? write_bit : read_bit;
    if ((parent & required) == 0) {
        return false;
    }
    auto cursor = iova;
    auto remaining = length;
    while (remaining != 0) {
        const auto index = static_cast<std::size_t>(cursor / page_size);
        const auto entry = read_le64(input.root, index * 8);
        if ((entry & 1) == 0 || (entry & required) == 0) {
            return false;
        }
        const auto available = page_size - (cursor & (page_size - 1));
        const auto part = remaining < available ? remaining : available;
        remaining -= part;
        cursor += part;
    }
    return true;
}

} // namespace independent

#endif
