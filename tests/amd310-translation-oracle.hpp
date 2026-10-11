#ifndef AURORA_TEST_AMD310_TRANSLATION_ORACLE_HPP
#define AURORA_TEST_AMD310_TRANSLATION_ORACLE_HPP

#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
#include <variant>

// Test-only interpretation of stable copied bytes, never a hardware capability.
// AMD 48882-PUB rev 3.10: sections 2.2.2-2.2.3, Tables 7/8/16/17/44/57, and
// MMIO 0000h in 3.4.1. See docs/iommu-models.md for the fixed profile.
// No production table encoder, canonical validator, or physical dereference.
namespace amd310_oracle {

class Input {
public:
    std::span<const std::byte> device_table{};
    std::span<const std::byte> root{};
    std::uint64_t root_physical_base{};
    std::uint16_t device_table_size{}; // Raw Size[8:0], not a byte/entry count.
};

enum class Access {
    read,
    write
};

class Request {
public:
    std::uint16_t requester{};
    std::uint64_t address{};
    Access access = Access::read;
};

class Rights {
public:
    bool read{};
    bool write{};
    auto operator==(const Rights &) const -> bool = default;
};

class Bypass {
public:
    std::uint64_t address{};
};

class Translation {
public:
    std::uint64_t address{};
    Rights rights{};
};

enum class FaultCause {
    requester_range,
    translation_invalid,
    address_range,
    not_present,
    permission,
    reserved_pte
};

class IoPageFault {
public:
    FaultCause cause{};
    std::uint16_t requester{};
    std::uint64_t address{};
    std::uint16_t domain{}; // Zero when no DTE supplied a valid DomainID.
    // Table 57 fields, not an encoded event or a promise that logging occurred.
    std::uint8_t event_code = 2;
    bool interrupt = false;
    bool translation_request = false;
    bool guest = false;
    std::optional<bool> present{};
    std::optional<bool> permission_denied{};
    std::optional<bool> write{};
    std::optional<bool> reserved_bit{};
};

enum class UnsupportedCause {
    size_field,
    identity_width,
    transaction_class,
    copied_backing,
    dte_profile,
    paging_mode,
    pte_profile
};

class Unsupported {
public:
    UnsupportedCause cause{};
};

using Result = std::variant<Bypass, Translation, IoPageFault, Unsupported>;

namespace detail {

inline auto word(std::span<const std::byte> bytes, std::size_t offset) -> std::uint64_t {
    std::uint64_t result = 0;
    for (std::size_t i = 0; i != 8; ++i) {
        result |= std::uint64_t{std::to_integer<unsigned char>(bytes[offset + i])} << (8 * i);
    }
    return result;
}

inline auto permissions(std::uint64_t entry) -> Rights {
    return {(entry >> 61 & 1) != 0, (entry >> 62 & 1) != 0};
}

inline auto denied(Rights rights, Access access) -> bool {
    return access == Access::write ? !rights.write : !rights.read;
}

inline auto special(std::uint64_t address) -> bool {
    // Exclude MSI and all HT special addresses, rather than interpreting them
    // as ordinary memory. HTRangeIgnore=0; no PASID or pretranslated requests.
    return (address >= 0xfee00000ULL && address <= 0xfeefffffULL) ||
           (address >= 0xfd00000000ULL && address <= 0xffffffffffULL);
}

inline auto fault(const Request &request,
                  FaultCause cause,
                  std::uint16_t domain,
                  std::optional<bool> present,
                  std::optional<Rights> rights = {}) -> IoPageFault {
    IoPageFault result;
    result.cause = cause;
    result.requester = request.requester;
    result.address = request.address;
    result.domain = domain;
    result.present = present;
    if (present == true) {
        result.write = request.access == Access::write;
        if (rights) {
            result.permission_denied = denied(*rights, request.access);
        }
    }
    return result;
}

} // namespace detail

[[nodiscard]] inline auto translate(const Input &input, const Request &request) -> Result {
    using namespace detail;
    if (special(request.address)) {
        return Unsupported{UnsupportedCause::transaction_class};
    }
    if (input.device_table_size > 511) {
        return Unsupported{UnsupportedCause::size_field};
    }
    const auto entries = (std::uint32_t{input.device_table_size} + 1) * 128;
    if (request.requester >= entries) {
        return fault(request, FaultCause::requester_range, 0, {});
    }
    const auto offset = std::size_t{request.requester} * 32;
    if (input.device_table.size() > 2097152 || offset > input.device_table.size() ||
        input.device_table.size() - offset < 32) {
        return Unsupported{UnsupportedCause::copied_backing};
    }
    const auto control = word(input.device_table, offset);
    if ((control & 1) == 0) {
        if (request.address > 0x000fffffffffffffULL) {
            return Unsupported{UnsupportedCause::identity_width};
        }
        return Bypass{request.address};
    }
    const auto domain_word = word(input.device_table, offset + 8);
    // This is a profile filter, not an architectural reserved-bit fault mask.
    // Root/mode/rights are permitted here even when TV=0 makes them invalid.
    if ((control & ~0x600ffffffffffe03ULL) != 0 || (domain_word >> 16) != 0 ||
        word(input.device_table, offset + 16) != 0 || word(input.device_table, offset + 24) != 0) {
        return Unsupported{UnsupportedCause::dte_profile};
    }
    const auto domain = static_cast<std::uint16_t>(domain_word);
    if ((control & 2) == 0) {
        return fault(request, FaultCause::translation_invalid, domain, true);
    }
    const auto mode = (control >> 9) & 7;
    if (mode > 1) {
        return Unsupported{UnsupportedCause::paging_mode};
    }
    const auto parent = permissions(control);
    if (mode == 0) {
        if (request.address > 0x000fffffffffffffULL) {
            return Unsupported{UnsupportedCause::identity_width};
        }
        if (denied(parent, request.access)) {
            return fault(request, FaultCause::permission, domain, true, parent);
        }
        return Translation{request.address, parent};
    }
    if (request.address >= 2097152) {
        return fault(request, FaultCause::address_range, domain, true, parent);
    }
    const auto root_base = control & 0x000ffffffffff000ULL;
    if (root_base != input.root_physical_base || input.root.size() != 4096) {
        return Unsupported{UnsupportedCause::copied_backing};
    }
    const auto index = static_cast<std::size_t>((request.address >> 12) & 511);
    const auto entry = word(input.root, index * 8);
    if ((entry & 1) == 0) {
        return fault(request, FaultCause::not_present, domain, false);
    }
    const auto leaf = permissions(entry);
    const Rights cumulative{parent.read && leaf.read, parent.write && leaf.write};
    if ((entry & 0x07f0000000000000ULL) != 0) {
        auto result = fault(request, FaultCause::reserved_pte, domain, true, cumulative);
        result.reserved_bit = true; // TMPMSup=0: bits 58:52 are reserved.
        return result;
    }
    if (((entry >> 9) & 7) != 0 || (entry & 0x1800000000000000ULL) != 0) {
        return Unsupported{UnsupportedCause::pte_profile};
    }
    // A completed one-level walk is the selected policy. Hardware may stop
    // earlier for a restrictive parent; no universal multifault priority claim.
    if (denied(cumulative, request.access)) {
        return fault(request, FaultCause::permission, domain, true, cumulative);
    }
    const auto address = (entry & 0x000ffffffffff000ULL) | (request.address & 4095);
    if (special(address)) {
        return Unsupported{UnsupportedCause::transaction_class};
    }
    return Translation{address, cumulative};
}

} // namespace amd310_oracle

#endif
