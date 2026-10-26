#define AURORA_DORMANT_TABLE_TESTING 1
#include "../kernel/dormant-tables.hpp"
#include "../kernel/dormant-decoder.hpp"
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <memory>

namespace aurora::memory {
class DormantTableTestAccess final {
public:
    static auto input(DormantTables &owner) -> independent::Input {
        independent::Input result;
        result.dte = owner.arena_.subspan(owner.pages_[0] - owner.arena_base_, 8192);
        result.root = owner.page(2);
        result.pages = owner.pages_;
        result.data_count = owner.data_count_;
        result.physical_bits = owner.physical_bits_;
        result.iovas = owner.iovas_;
        result.writable = owner.writable_;
        return result;
    }
    static auto flip(DormantTables &owner, std::size_t role, std::size_t byte, unsigned bit) -> void {
        owner.page(role)[byte] ^= std::byte(1U << bit);
    }
};
} // namespace aurora::memory

namespace kernel_dormant_tables {
using namespace aurora;
std::size_t checks{};
auto check(bool value) -> void {
    ++checks;
    if (!value) {
        std::fprintf(stderr, "FAIL check%zu\n", checks);
        std::abort();
    }
}
class Fixture final {
public:
    alignas(4096) std::array<std::byte, 16 * 4096> bytes{};
    memory::PhysicalPagePool<> pool;
    user::DomainRegistry registry;
    std::optional<user::DomainHandle> owner, peer;
    std::array<std::optional<memory::PageLease>, 16> held{};
    std::size_t scrub_calls{}, fail{}, held_count{};
    memory::PinLedger ledger;
    memory::DormantTables tables;
    Fixture(std::size_t spare = 8) : ledger(pool, registry, scrub, this), tables(ledger, bytes, base()) {
        bytes.fill(std::byte{0xa5});
        check(pool.initialize(base(), 16));
        owner = registry.create();
        peer = registry.create();
        check(owner.has_value() && peer.has_value());
        for (std::size_t i = 0; i < 16 - spare; ++i)
            hold();
    }
    auto base() const -> std::uint64_t {
        return reinterpret_cast<std::uintptr_t>(bytes.data());
    }
    auto hold() -> void {
        auto p = pool.acquire();
        check(p.has_value());
        held[held_count++].emplace(std::move(*p));
    }
    static auto scrub(void *ptr, std::uint64_t pa, std::size_t size) -> bool {
        auto &f = *static_cast<Fixture *>(ptr);
        check(size == 4096 && pa >= f.base() && pa - f.base() <= f.bytes.size() - size && (pa - f.base()) % 4096 == 0);
        for (const auto &p : f.held)
            if (p)
                check(f.pool.address(*p) != pa);
        if (++f.scrub_calls == f.fail)
            return false;
        std::fill_n(f.bytes.begin() + static_cast<std::ptrdiff_t>(pa - f.base()), size, std::byte{0});
        return true;
    }
    auto stacks_unchanged() const -> bool {
        for (const auto &p : held)
            if (p) {
                const auto pa = pool.address(*p);
                if (!pa)
                    return false;
                for (std::size_t i = 0; i < 4096; ++i)
                    if (bytes[*pa - base() + i] != std::byte{0xa5})
                        return false;
            }
        return true;
    }
    auto prepare() -> bool {
        const std::array<std::uint64_t, 2> addresses{0x1000, 0x1ff000};
        const std::array<bool, 2> permissions{false, true};
        return tables.prepare(*owner, 52, addresses, permissions);
    }
};
auto ordinary_and_mutations() -> void {
    auto f = std::make_unique<Fixture>();
    check(f->prepare());
    check(f->pool.used() == 13);
    check(f->ledger.used_entries() == 3);
    check(f->tables.validate(*f->owner));
    check(!f->tables.validate(*f->peer));
    check(!f->prepare());
    auto snapshot = memory::DormantTableTestAccess::input(f->tables);
    check(independent::validate(snapshot));
    check(independent::permits(snapshot, 16, 0x1000, 4096, false));
    check(!independent::permits(snapshot, 16, 0x1000, 1, true));
    check(independent::permits(snapshot, 16, 0x1ff000, 4096, true));
    for (unsigned rid = 0; rid < 65536; ++rid)
        if (rid != 16)
            check(!independent::permits(snapshot, static_cast<std::uint16_t>(rid), 0x1000, 1, false));
    check(!independent::permits(snapshot, 16, 0x201000, 1, false));
    check(!independent::permits(snapshot, 16, UINT64_MAX, 2, false));
    check(!independent::permits(snapshot, 16, 0x1ff000, 4097, false));
    // Every DTE slot and every root slot is checked, including all holes.
    for (std::size_t rid = 0; rid < 256; ++rid) {
        memory::DormantTableTestAccess::flip(f->tables, rid / 128, (rid % 128) * 32, 0);
        check(!f->tables.validate(*f->owner));
        check(!independent::validate(snapshot));
        memory::DormantTableTestAccess::flip(f->tables, rid / 128, (rid % 128) * 32, 0);
    }
    for (std::size_t slot = 0; slot < 512; ++slot) {
        memory::DormantTableTestAccess::flip(f->tables, 2, slot * 8, 0);
        check(!f->tables.validate(*f->owner));
        check(!independent::validate(snapshot));
        memory::DormantTableTestAccess::flip(f->tables, 2, slot * 8, 0);
    }
    // All256 bits of selected DTE and64 bits of mapped leaf must be exact.
    for (std::size_t byte = 0; byte < 32; ++byte)
        for (unsigned bit = 0; bit < 8; ++bit) {
            memory::DormantTableTestAccess::flip(f->tables, 0, 16 * 32 + byte, bit);
            check(!f->tables.validate(*f->owner));
            check(!independent::validate(snapshot));
            memory::DormantTableTestAccess::flip(f->tables, 0, 16 * 32 + byte, bit);
        }
    for (std::size_t byte = 0; byte < 8; ++byte)
        for (unsigned bit = 0; bit < 8; ++bit) {
            memory::DormantTableTestAccess::flip(f->tables, 2, 8 + byte, bit);
            check(!f->tables.validate(*f->owner));
            check(!independent::validate(snapshot));
            memory::DormantTableTestAccess::flip(f->tables, 2, 8 + byte, bit);
        }
    check(!f->tables.cancel(*f->peer));
    check(f->tables.cancel(*f->owner));
    check(!f->tables.validate(*f->owner));
    check(f->pool.used() == 8 && f->ledger.pinned_pages() == 0);
    check(f->stacks_unchanged());
    for (std::size_t n = 8 * 4096; n < 13 * 4096; ++n)
        check(f->bytes[n] == std::byte{0});
    check(f->prepare());
    check(f->tables.cancel(*f->owner));
}
auto exhaustion_and_scrub() -> void {
    for (std::size_t spare = 0; spare <= 8; ++spare)
        for (std::size_t failure = 0; failure <= 6; ++failure) {
            auto f = std::make_unique<Fixture>(spare);
            f->fail = failure;
            const auto prepared = f->prepare();
            check(prepared == (spare >= 5));
            if (prepared)
                static_cast<void>(f->tables.cancel(*f->owner));
            check(f->pool.used() == 16 - spare + f->ledger.quarantined_pages());
            check(f->ledger.pinned_pages() == f->ledger.quarantined_pages());
            check(f->stacks_unchanged());
            const auto retained = f->ledger.quarantined_pages();
            check(f->registry.destroy(*f->owner));
            check(f->ledger.reap_dead() == 0);
            check(f->ledger.quarantined_pages() == retained);
        }
    auto f = std::make_unique<Fixture>();
    const auto first = f->ledger.grant(*f->peer, 1), second = f->ledger.grant(*f->peer, 1);
    check(first && second);
    check(!f->prepare());
    check(f->pool.used() == 10);
    check(f->ledger.pinned_pages() == 2);
    check(f->ledger.cancel(*first, *f->peer));
    check(f->ledger.cancel(*second, *f->peer));
    check(f->prepare());
    check(f->tables.cancel(*f->owner));
}
auto fragmented_and_lifetime() -> void {
    auto f = std::make_unique<Fixture>();
    // First free pages8 and10 are noncontiguous. Retain page9 independently.
    auto eight = f->pool.acquire();
    check(eight.has_value());
    f->hold();
    check(f->pool.release(*eight));
    check(!f->prepare());
    check(f->pool.used() == 9 && f->ledger.pinned_pages() == 0);
    check(f->stacks_unchanged());
    check(f->pool.release(*f->held[8]));
    f->held[8].reset();
    check(f->prepare());
    const auto old = *f->owner;
    check(f->registry.destroy(old));
    const auto reborn = f->registry.create();
    check(reborn.has_value());
    check(!f->tables.validate(*reborn));
    check(!f->tables.cancel(*reborn));
    check(f->ledger.reap_dead() == 3);
    check(f->pool.used() == 8);
    check(!f->tables.validate(old));
    // Dropping the typed constructor cannot implicitly release its retained pages.
    auto g = std::make_unique<Fixture>();
    {
        memory::DormantTables temporary(g->ledger, g->bytes, g->base());
        const std::array<std::uint64_t, 1> io{0};
        const std::array<bool, 1> rw{true};
        check(temporary.prepare(*g->owner, 52, io, rw));
        check(temporary.validate(*g->owner));
        check(independent::validate(memory::DormantTableTestAccess::input(temporary)));
    }
    check(g->pool.used() == 12 && g->ledger.pinned_pages() == 4);
    check(g->ledger.borrower_dispose(*g->owner) == 3);
    check(g->pool.used() == 8);
}
auto malformed_requests() -> void {
    auto f = std::make_unique<Fixture>();
    const std::array<bool, 2> rw{false, true};
    for (const auto io : std::array<std::array<std::uint64_t, 2>, 5>{
             {{0, 0}, {1, 4096}, {0, 0x200000}, {UINT64_MAX, 4096}, {0, UINT64_MAX - 4095}}})
        check(!f->tables.prepare(*f->owner, 52, io, rw));
    const std::array<std::uint64_t, 2> good{0, 4096};
    for (unsigned width : std::array<unsigned, 4>{0, 31, 53, 255})
        check(!f->tables.prepare(*f->owner, static_cast<std::uint8_t>(width), good, rw));
    check(!f->tables.prepare(user::DomainHandle{}, 52, good, rw));
    check(f->pool.used() == 8);
    check(f->prepare());
    check(f->tables.cancel(*f->owner));
}
auto main() -> int {
    ordinary_and_mutations();
    exhaustion_and_scrub();
    fragmented_and_lifetime();
    malformed_requests();
    std::printf("PASS %zu dormant construction/ownership/independent-byte checks; no device operation\n", checks);
    return 0;
}
} // namespace kernel_dormant_tables
