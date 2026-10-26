#define AURORA_DORMANT_TABLE_TESTING 1
#include "../kernel/dormant-tables.hpp"
#include "amd310-translation-oracle.hpp"

#include <algorithm>
#include <array>
#include <cstdio>
#include <cstdlib>
#include <memory>

namespace {

class CopiedTables {
public:
    std::array<std::byte, 8192> dte{};
    std::array<std::byte, 4096> root{};
    std::array<std::uint64_t, 5> pages{};

    auto input() const -> amd310_oracle::Input {
        return {dte, root, pages[2], 1};
    }
};

} // namespace

namespace aurora::memory {

class DormantTableTestAccess final {
public:
    static void copy(const DormantTables &owner, CopiedTables &output) {
        // This trusted test adapter copies the constructor's bounded CPU views.
        // The oracle receives no owner, callback, lease, or physical pointer.
        const auto first = owner.page(0);
        const auto second = owner.page(1);
        const auto root = owner.page(2);
        std::copy(first.begin(), first.end(), output.dte.begin());
        std::copy(second.begin(), second.end(), output.dte.begin() + 4096);
        std::copy(root.begin(), root.end(), output.root.begin());
        output.pages = owner.pages_;
    }
};

} // namespace aurora::memory

namespace {

using namespace aurora;
using namespace amd310_oracle;
std::size_t checks = 0;

void check(bool value, const char *description) {
    ++checks;
    if (!value) {
        std::fprintf(stderr, "FAIL: %s\n", description);
        std::abort();
    }
}

class Fixture {
public:
    static constexpr std::uint64_t base = 0x100000;
    std::array<std::byte, 16 * 4096> bytes{};
    memory::PhysicalPagePool<> pool;
    user::DomainRegistry registry;
    memory::PinLedger ledger{pool, registry, scrub, this};
    memory::DormantTables tables{ledger, bytes, base};

    Fixture() {
        check(pool.initialize(base, 16), "initialize synthetic bounded CPU backing");
    }

    static auto scrub(void *context, std::uint64_t address, std::size_t length) -> bool {
        auto &fixture = *static_cast<Fixture *>(context);
        if (length != 4096 || address < base || address - base > fixture.bytes.size() - length) {
            return false;
        }
        std::fill_n(fixture.bytes.begin() + static_cast<std::ptrdiff_t>(address - base), length, std::byte{0});
        return true;
    }
};

void emitted_bytes() {
    auto fixture = std::make_unique<Fixture>();
    const auto owner = fixture->registry.create();
    check(owner.has_value(), "create actual live constructor owner");
    const std::array<std::uint64_t, 2> iovas{0x3000, 0x4000};
    const std::array<bool, 2> writable{false, true};
    check(fixture->tables.prepare(*owner, 32, iovas, writable), "prepare real dormant constructor bytes");
    CopiedTables copied;
    memory::DormantTableTestAccess::copy(fixture->tables, copied);
    // No canonical validate() prerequisite: the new reader decides from bytes.
    const auto input = copied.input();
    for (std::uint32_t rid = 0; rid <= 65535; ++rid) {
        if (rid == 16) {
            continue;
        }
        const auto result = translate(input, {static_cast<std::uint16_t>(rid), 0x3000, Access::read});
        const auto *fault = std::get_if<IoPageFault>(&result);
        check(fault && fault->cause == (rid < 256 ? FaultCause::permission : FaultCause::requester_range) &&
                  fault->domain == 0 && !fault->interrupt,
              "real constructor holes and declared table boundary deny distinctly");
    }
    for (std::size_t mapping = 0; mapping != 2; ++mapping) {
        for (const std::uint64_t offset : {0, 1, 4095}) {
            for (const auto access : {Access::read, Access::write}) {
                const auto result = translate(input, {16, iovas[mapping] + offset, access});
                if (access == Access::write && !writable[mapping]) {
                    const auto *fault = std::get_if<IoPageFault>(&result);
                    check(fault && fault->cause == FaultCause::permission && fault->domain == 1 &&
                              fault->present == true && fault->permission_denied == true && fault->write == true,
                          "real RO leaf denies writes with meaningful fields");
                } else {
                    const auto *value = std::get_if<Translation>(&result);
                    check(value && value->address == copied.pages[3 + mapping] + offset &&
                              value->rights == Rights{true, writable[mapping]},
                          "real emitted bytes translate with exact address and rights");
                }
            }
        }
    }
    const auto high = translate(input, {16, 0x203000, Access::read});
    const auto *high_fault = std::get_if<IoPageFault>(&high);
    check(high_fault && high_fault->cause == FaultCause::address_range, "actual root has no upper-address alias");
    const auto hole = translate(input, {16, 0x5000, Access::read});
    const auto *hole_fault = std::get_if<IoPageFault>(&hole);
    check(hole_fault && hole_fault->cause == FaultCause::not_present, "actual unused leaf is absent");
    check(fixture->tables.cancel(*owner), "cancel never-published actual constructor");
    check(fixture->pool.used() == 0 && fixture->ledger.pinned_pages() == 0, "constructor leases released after scrub");
    // The copied snapshot remains an ordinary value after the source is scrubbed.
    const auto after = translate(input, {16, 0x4001, Access::write});
    const auto *value = std::get_if<Translation>(&after);
    check(value && value->address == copied.pages[4] + 1, "snapshot has no retained live table view");
}

} // namespace

int main() {
    emitted_bytes();
    std::printf("PASS %zu copied dormant-constructor/oracle checks; no device operation\n", checks);
}
