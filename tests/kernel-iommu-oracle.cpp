#include "amd310-translation-oracle.hpp"

#include <algorithm>
#include <array>
#include <cstdio>
#include <limits>
#include <vector>

namespace kernel_iommu_oracle {
namespace {

using namespace amd310_oracle;
std::size_t checks = 0;
std::size_t failures = 0;

void check(bool value, const char *description) {
    ++checks;
    if (!value) {
        ++failures;
        std::fprintf(stderr, "FAIL: %s\n", description);
    }
}

void put(std::span<std::byte> bytes, std::size_t offset, std::uint64_t value) {
    for (std::size_t i = 0; i != 8; ++i) {
        bytes[offset + i] = std::byte((value >> (8 * i)) & 255);
    }
}

class Fixture {
public:
    std::array<std::byte, 8192> dte{};
    std::array<std::byte, 4096> root{};
    Input input{dte, root, 0x5000, 1};
    Request request{16, 0x3123, Access::read};

    Fixture() {
        // Independently handwritten little-endian known-answer bytes.
        dte[512] = std::byte{3};
        dte[513] = std::byte{0x52};
        dte[519] = std::byte{0x60};
        dte[520] = std::byte{0x34};
        dte[521] = std::byte{0x12};
        root[24] = std::byte{1};
        root[25] = std::byte{0x90};
        root[31] = std::byte{0x60};
    }

    Fixture(const Fixture &) = delete;
    auto operator=(const Fixture &) -> Fixture & = delete;

    auto run() const -> Result {
        return translate(input, request);
    }
};

void translated(const Result &result, std::uint64_t address, Rights rights, const char *description) {
    const auto *value = std::get_if<Translation>(&result);
    check(value && value->address == address && value->rights == rights, description);
}

void unsupported(const Result &result, UnsupportedCause cause, const char *description) {
    const auto *value = std::get_if<Unsupported>(&result);
    check(value && value->cause == cause, description);
}

void fault_fields(const Result &result,
                  const Request &request,
                  FaultCause cause,
                  std::uint16_t domain,
                  std::optional<bool> present,
                  std::optional<bool> permission,
                  std::optional<bool> reserved,
                  const char *description) {
    const auto *value = std::get_if<IoPageFault>(&result);
    const bool write_matches =
        value && (present == true ? value->write == (request.access == Access::write) : !value->write.has_value());
    check(value && value->cause == cause && value->requester == request.requester &&
              value->address == request.address && value->domain == domain && value->present == present &&
              value->permission_denied == permission && write_matches && value->reserved_bit == reserved &&
              value->event_code == 2 && !value->interrupt && !value->translation_request && !value->guest,
          description);
}

void requester_and_size() {
    Fixture fixture;
    for (const auto access : {Access::read, Access::write}) {
        fixture.request.access = access;
        fixture.request.requester = 255;
        put(fixture.dte, 255 * 32, 0x6000000000000003ULL);
        translated(fixture.run(), 0x3123, {true, true}, "RID 255 fits Size=1");
        for (const std::uint16_t rid : {256, 65535}) {
            fixture.request.requester = rid;
            fault_fields(fixture.run(),
                         fixture.request,
                         FaultCause::requester_range,
                         0,
                         {},
                         {},
                         {},
                         "requester length precedes backing lookup");
        }
    }
    // Extra host bytes must never extend the declared architectural table.
    std::vector<std::byte> all(2097152);
    put(all, 256 * 32, 0x6000000000000003ULL);
    put(all, 65535 * 32, 0x6000000000000003ULL);
    fixture.input.device_table = all;
    for (const std::uint16_t rid : {256, 65535}) {
        fixture.request.requester = rid;
        fault_fields(fixture.run(),
                     fixture.request,
                     FaultCause::requester_range,
                     0,
                     {},
                     {},
                     {},
                     "declared size wins over excessive backing");
    }
    fixture.input.device_table_size = 511;
    translated(fixture.run(), 0x3123, {true, true}, "maximum table admits RID 65535");
    fixture.input.device_table_size = 0;
    fixture.request.requester = 127;
    check(std::holds_alternative<Bypass>(fixture.run()), "Size zero means 128 entries");
    fixture.request.requester = 128;
    fault_fields(fixture.run(), fixture.request, FaultCause::requester_range, 0, {}, {}, {}, "Size zero boundary");
    fixture.input.device_table_size = 512;
    unsupported(fixture.run(), UnsupportedCause::size_field, "out-of-field Size unsupported");
}

void address_and_presence() {
    Fixture fixture;
    fixture.request.address = 0x3000;
    translated(fixture.run(), 0x9000, {true, true}, "low IOVA maps literal leaf");
    for (const auto address : {0x203000ULL, 0x200000ULL, 0xffffffffffffffffULL}) {
        fixture.request.address = address;
        fault_fields(fixture.run(),
                     fixture.request,
                     FaultCause::address_range,
                     0x1234,
                     true,
                     false,
                     {},
                     "upper address must not alias low leaf");
    }
    for (const auto access : {Access::read, Access::write}) {
        fixture.request = {16, 0x3000, access};
        for (const auto payload : {0ULL, 0xfffffffffffffffeULL, 0x6000000000009000ULL}) {
            put(fixture.root, 24, payload);
            fault_fields(fixture.run(),
                         fixture.request,
                         FaultCause::not_present,
                         0x1234,
                         false,
                         {},
                         {},
                         "PR clear ignores every payload bit");
        }
    }
    // Entry boundaries, host alignment, and the complete translated offset.
    put(fixture.root, 0, 0x6000000000000001ULL);
    put(fixture.root, 511 * 8, 0x600ffffffffff001ULL);
    fixture.request.address = 0;
    translated(fixture.run(), 0, {true, true}, "zero physical page is a valid translation");
    fixture.request.address = 0x1fffff;
    translated(fixture.run(), 0xfffffffffffffULL, {true, true}, "last root slot and 52-bit address");
    std::array<std::byte, 8193> shifted_dte{};
    std::array<std::byte, 4097> shifted_root{};
    std::copy(fixture.dte.begin(), fixture.dte.end(), shifted_dte.begin() + 1);
    std::copy(fixture.root.begin(), fixture.root.end(), shifted_root.begin() + 1);
    fixture.input.device_table = std::span<const std::byte>{shifted_dte}.subspan(1);
    fixture.input.root = std::span<const std::byte>{shifted_root}.subspan(1);
    translated(fixture.run(), 0xfffffffffffffULL, {true, true}, "unaligned copied host bytes");
}

void permissions() {
    for (unsigned parent = 0; parent != 4; ++parent) {
        for (unsigned leaf = 0; leaf != 4; ++leaf) {
            Fixture fixture;
            put(fixture.dte, 512, (std::uint64_t{parent} << 61) | 0x5203);
            put(fixture.root, 24, (std::uint64_t{leaf} << 61) | 0x9001);
            const Rights rights{(parent & leaf & 1) != 0, (parent & leaf & 2) != 0};
            for (const auto access : {Access::read, Access::write}) {
                fixture.request.access = access;
                const auto allowed = access == Access::read ? rights.read : rights.write;
                if (allowed) {
                    translated(fixture.run(), 0x9123, rights, "parent and leaf cumulative rights");
                } else {
                    fault_fields(fixture.run(),
                                 fixture.request,
                                 FaultCause::permission,
                                 0x1234,
                                 true,
                                 true,
                                 {},
                                 "cumulative permission denies access");
                }
            }
        }
    }
}

void validity_and_mode_zero() {
    Fixture fixture;
    fixture.dte.fill(std::byte{0xff});
    fixture.dte[512] = std::byte{0xfe};
    fixture.input.root = {};
    fixture.request.address = 0x123456789abcULL;
    const auto bypass = fixture.run();
    const auto *value = std::get_if<Bypass>(&bypass);
    check(value && value->address == fixture.request.address, "V zero ignores noncanonical fields and bypasses");
    fixture.dte.fill(std::byte{0});
    put(fixture.dte, 520, 0x4321);
    put(fixture.dte, 512, 0x600ffffffffffE01ULL); // TV=0: Mode7/root/rights are ignored.
    for (const auto access : {Access::read, Access::write}) {
        fixture.request.access = access;
        fault_fields(fixture.run(),
                     fixture.request,
                     FaultCause::translation_invalid,
                     0x4321,
                     true,
                     {},
                     {},
                     "TV zero faults without interpreting mode root or rights");
    }
    for (unsigned parent = 0; parent != 4; ++parent) {
        put(fixture.dte, 512, (std::uint64_t{parent} << 61) | 0xabcdef003ULL);
        for (const auto access : {Access::read, Access::write}) {
            fixture.request.access = access;
            const Rights rights{(parent & 1) != 0, (parent & 2) != 0};
            if (access == Access::read ? rights.read : rights.write) {
                translated(fixture.run(), fixture.request.address, rights, "Mode zero identity preserves DTE rights");
            } else {
                fault_fields(fixture.run(),
                             fixture.request,
                             FaultCause::permission,
                             0x4321,
                             true,
                             true,
                             {},
                             "Mode zero enforces DTE rights");
            }
        }
    }
}

void identity_width() {
    for (const auto control : {0ULL, 0x6000000000000003ULL}) {
        for (const auto access : {Access::read, Access::write}) {
            Fixture fixture;
            put(fixture.dte, 512, control);
            fixture.request = {16, 0x000fffffffffffffULL, access};
            if (control == 0) {
                const auto result = fixture.run();
                const auto *value = std::get_if<Bypass>(&result);
                check(value && value->address == fixture.request.address, "V zero last 52-bit identity address");
            } else {
                translated(fixture.run(), fixture.request.address, {true, true}, "Mode zero last 52-bit address");
            }
            for (const auto address : {0x0010000000000000ULL, 0xffffffffffffffffULL}) {
                fixture.request.address = address;
                unsupported(fixture.run(), UnsupportedCause::identity_width, "identity exceeds abstract PAsize52");
            }
        }
    }
}

void profile_and_fault_fields() {
    for (const auto access : {Access::read, Access::write}) {
        Fixture fixture;
        fixture.request.access = access;
        for (unsigned bit = 52; bit <= 58; ++bit) {
            put(fixture.root, 24, 0x6000000000009001ULL | (1ULL << bit));
            fault_fields(fixture.run(),
                         fixture.request,
                         FaultCause::reserved_pte,
                         0x1234,
                         true,
                         false,
                         true,
                         "present leaf reserved bit has defined RZ and request fields");
        }
        // Permission evidence is cumulative even when a reserved-bit error ends this walk.
        put(fixture.dte, 512, 0x5203);
        fault_fields(fixture.run(),
                     fixture.request,
                     FaultCause::reserved_pte,
                     0x1234,
                     true,
                     true,
                     true,
                     "fault PE reflects accomplished cumulative permissions");
        fixture.request.address = 0x203000;
        fault_fields(fixture.run(),
                     fixture.request,
                     FaultCause::address_range,
                     0x1234,
                     true,
                     true,
                     {},
                     "high-address fault carries only valid parent permission evidence");
    }
    for (unsigned bit = 1; bit <= 8; ++bit) {
        Fixture fixture;
        fixture.root[24] |= std::byte(bit < 8 ? 1U << bit : 0U);
        if (bit == 8)
            fixture.root[25] |= std::byte{1};
        translated(fixture.run(), 0x9123, {true, true}, "PTE ignored and inactive AD bits accepted");
    }
    Fixture ignored;
    ignored.root[31] |= std::byte{0x80};
    translated(ignored.run(), 0x9123, {true, true}, "PTE bit 63 ignored");
    for (unsigned mode = 2; mode != 8; ++mode) {
        Fixture fixture;
        put(fixture.dte, 512, 0x6000000000005003ULL | (std::uint64_t{mode} << 9));
        unsupported(fixture.run(), UnsupportedCause::paging_mode, "other DTE modes remain unsupported");
    }
    for (unsigned next = 1; next != 8; ++next) {
        Fixture fixture;
        put(fixture.root, 24, 0x6000000000009001ULL | (std::uint64_t{next} << 9));
        unsupported(fixture.run(), UnsupportedCause::pte_profile, "other leaf levels remain unsupported");
    }
    for (unsigned bit : {59, 60}) {
        Fixture fixture;
        put(fixture.root, 24, 0x6000000000009001ULL | (1ULL << bit));
        unsupported(fixture.run(), UnsupportedCause::pte_profile, "unmodeled leaf attributes unsupported");
    }
    for (const std::size_t offset : {512, 520, 528, 536}) {
        Fixture fixture;
        fixture.dte[offset + 2] |= std::byte{0x80};
        // At word0 choose HAD instead of a legitimate root-address bit.
        if (offset == 512)
            fixture.dte[512] |= std::byte{0x80};
        unsupported(fixture.run(), UnsupportedCause::dte_profile, "unmodeled DTE fields unsupported");
    }
    for (const auto address : {0xfee00000ULL, 0xfeefffffULL, 0xfd00000000ULL, 0xffffffffffULL}) {
        for (const auto control : {0ULL, 3ULL, 0x6000000000005203ULL}) {
            Fixture fixture;
            fixture.request.address = address;
            put(fixture.dte, 512, control);
            unsupported(fixture.run(), UnsupportedCause::transaction_class, "special address never ordinary memory");
        }
        Fixture fixture;
        put(fixture.root, 24, 0x6000000000000001ULL | (address & ~4095ULL));
        unsupported(fixture.run(), UnsupportedCause::transaction_class, "special output address outside profile");
    }
}

void bounded_copies() {
    Fixture fixture;
    fixture.input.device_table = fixture.input.device_table.first(543);
    unsupported(
        fixture.run(), UnsupportedCause::copied_backing, "incomplete DTE is missing test input, not hardware fault");
    fixture.input.device_table = fixture.dte;
    fixture.input.root = fixture.input.root.first(4095);
    unsupported(fixture.run(), UnsupportedCause::copied_backing, "incomplete root is missing test input");
    fixture.input.root = fixture.root;
    fixture.input.root_physical_base = 0x6000;
    unsupported(fixture.run(), UnsupportedCause::copied_backing, "encoded root must match bounded backing");
    fixture.input.root_physical_base = 0x5001;
    unsupported(fixture.run(), UnsupportedCause::copied_backing, "misaligned root description cannot match");
    fixture.input.device_table = {};
    fixture.request.requester = 65535;
    fault_fields(fixture.run(),
                 fixture.request,
                 FaultCause::requester_range,
                 0,
                 {},
                 {},
                 {},
                 "requester architectural bound needs no host backing");
}

} // namespace

int main() {
    requester_and_size();
    address_and_presence();
    permissions();
    validity_and_mode_zero();
    identity_width();
    profile_and_fault_fields();
    bounded_copies();
    std::printf(
        "%s %zu independent AMD310 translation checks; no device operation\n", failures ? "FAIL" : "PASS", checks);
    return failures ? 1 : 0;
}
} // namespace kernel_iommu_oracle
