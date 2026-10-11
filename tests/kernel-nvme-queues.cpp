#include "../kernel/uefi/nvme-queues.hpp"
#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <source_location>
#include <type_traits>
#include <vector>

using namespace aurora::uefi;
using aurora::memory::PageLease;
using aurora::memory::PhysicalPages;
using Bundle = NvmeQueueBundle;
using Handle = NvmeQueueHandle;
using Role = Bundle::Role;
using Direction = Bundle::Direction;
using Header = std::array<std::byte, 64>;
using Buffer = std::vector<std::byte>;
std::size_t checks{};
constexpr std::uint64_t pool_base = 0x450000;
constexpr std::uint64_t bar_base = 0xc0000000;
constexpr std::uint64_t capabilities = (1ULL << 37) | (4ULL << 52) | 7;

auto check(bool value, const std::source_location location = std::source_location::current()) -> void {
    ++checks;
    if (!value) {
        std::cerr << "FAIL: line " << location.line() << ", check " << checks << '\n';
        std::abort();
    }
}

auto config() -> Header {
    Header header{};
    put(header, 0, 0x00101b36, 4);
    put(header, 4, 2, 2);
    put(header, 9, 0x010802, 3);
    put(header, 16, bar_base | 4, 4);
    return header;
}

auto snapshot(const Header &header = config(),
              unsigned device = 2,
              unsigned bus = 0,
              unsigned function = 0,
              unsigned segment = 0) -> PciBarSnapshot {
    const auto result = PciBarSnapshot::parse(segment, bus, device, function, header);
    check(result.has_value());
    return *result;
}

auto descriptor(unsigned type, std::uint64_t begin, std::uint64_t length, unsigned granularity) -> Buffer {
    Buffer result(46);
    put(result, 0, 0x8a, 1);
    put(result, 1, 43, 2);
    put(result, 3, type, 1);
    put(result, 6, granularity);
    put(result, 14, begin);
    put(result, 22, begin + length - 1);
    put(result, 38, length);
    return result;
}

auto resources(std::initializer_list<Buffer> records) -> PciResources {
    Buffer bytes;
    for (const auto &record : records)
        bytes.insert(bytes.end(), record.begin(), record.end());
    bytes.insert(bytes.end(), {std::byte{0x79}, std::byte{0}});
    const auto result = PciResources::parse(bytes, 40);
    check(result.has_value());
    return *result;
}

class Fixture final {
public:
    WindowAuthority authority;
    std::optional<WindowTicket> ticket = authority.acquire();
    PhysicalPages pool;
    alignas(4096) std::array<std::byte, Bundle::pool_pages * Bundle::page_bytes> backing{};
    PciBarSnapshot current = snapshot();
    Fixture() {
        check(ticket.has_value());
        check(pool.initialize(pool_base, Bundle::pool_pages));
        backing.fill(std::byte{0xa5});
    }
    [[nodiscard]] auto grant(std::uint64_t cap = capabilities, unsigned device = 2) -> NvmeBarGrant {
        const auto identity = snapshot(config(), device);
        const auto bar = resources({descriptor(0, bar_base, 16384, 64)});
        const auto root = resources({descriptor(0, bar_base, 16384, 64), descriptor(2, 0, 256, 0)});
        std::array<std::byte, 40> map{};
        put(map, 0, 1, 4);
        put(map, 8, 0x400000);
        put(map, 24, 256);
        const auto probe = NvmeBarProbe::authorize(
            identity, identity, bar, root, 0, map, 40, 0x400000, 0xfee00000, authority, *ticket);
        check(probe.has_value());
        const auto result = probe->finish(authority, identity, cap, 0x10400, 0, 0, 0, 0, 0);
        check(result.has_value());
        return *result;
    }
};

auto bytes_are(std::span<const std::byte> bytes, std::byte value) -> bool {
    return std::all_of(bytes.begin(), bytes.end(), [value](auto byte) {
        return byte == value;
    });
}

auto hold(PhysicalPages &pool, std::optional<PageLease> &destination) -> void {
    auto lease = pool.acquire();
    check(lease.has_value());
    destination.emplace(std::move(*lease));
}

auto basics() -> void {
    Fixture f;
    Bundle bundle(f.pool, f.backing, pool_base);
    const auto grant = f.grant();
    check(!f.pool.initialize(pool_base, Bundle::pool_pages));
    check(!bundle.cancel(Handle{}));
    const auto handle = bundle.prepare(grant, f.authority, f.current);
    check(handle && handle->generation() == 1 && f.pool.used() == 5 && bundle.held_pages() == 5);
    check(!bundle.prepare(grant, f.authority, f.current));
    check(bytes_are(std::span{f.backing}.first(5 * 4096), std::byte{0}));
    check(bytes_are(std::span{f.backing}.subspan(5 * 4096), std::byte{0xa5}));
    for (unsigned role = 0; role < 8; ++role)
        for (unsigned direction = 0; direction < 4; ++direction) {
            const bool expected = role < 5 && direction == ((role == 0 || role == 2) ? 0U : 1U);
            check(bundle.ready(
                      *handle, f.authority, f.current, static_cast<Role>(role), static_cast<Direction>(direction)) ==
                  expected);
        }
    WindowAuthority foreign;
    check(foreign.acquire().has_value());
    check(!bundle.ready(*handle, foreign, f.current, Role::data, Direction::device_writes));
    check(!bundle.ready(Handle{}, f.authority, f.current, Role::data, Direction::device_writes));
    Bundle other(f.pool, f.backing, pool_base);
    check(!other.cancel(*handle));
    for (std::size_t at = 0; at < 64; ++at)
        for (unsigned bit = 0; bit < 8; ++bit) {
            auto header = config();
            header[at] ^= std::byte{static_cast<unsigned char>(1U << bit)};
            const auto changed = snapshot(header);
            check(!bundle.ready(*handle, f.authority, changed, Role::data, Direction::device_writes));
        }
    for (const auto &changed : {snapshot(config(), 2, 1), snapshot(config(), 2, 0, 1), snapshot(config(), 2, 0, 0, 1)})
        check(!bundle.ready(*handle, f.authority, changed, Role::data, Direction::device_writes));
    check(!bundle.ready(*handle, f.authority, snapshot(config(), 3), Role::data, Direction::device_writes));
    std::fill_n(f.backing.begin(), 5 * 4096, std::byte{0x5a});
    check(bundle.cancel(*handle));
    check(f.pool.used() == 0 && bundle.held_pages() == 0 && !bundle.retained());
    check(bytes_are(std::span{f.backing}.first(5 * 4096), std::byte{0}));
    check(!bundle.cancel(*handle));
    check(!bundle.ready(*handle, f.authority, f.current, Role::data, Direction::device_writes));
    auto replacement = bundle.prepare(grant, f.authority, f.current);
    check(replacement && replacement->generation() == 2 && !bundle.cancel(*handle));
    check(bundle.cancel(*replacement));
    std::array<std::optional<PageLease>, 5> reacquired;
    for (std::size_t index = 0; index < 5; ++index) {
        hold(f.pool, reacquired[index]);
        check(reacquired[index] && f.pool.address(*reacquired[index]) == pool_base + index * 4096);
        check(bytes_are(std::span{f.backing}.subspan(index * 4096, 4096), std::byte{0}));
    }
    for (auto &lease : reacquired)
        check(f.pool.release(*lease));
}

auto session_lifetime() -> void {
    Fixture f;
    Bundle bundle(f.pool, f.backing, pool_base);
    const auto old_grant = f.grant();
    const auto handle = bundle.prepare(old_grant, f.authority, f.current);
    check(handle.has_value());
    check(f.authority.revoke(*f.ticket));
    check(!bundle.ready(*handle, f.authority, f.current, Role::data, Direction::device_writes));
    f.ticket = f.authority.acquire();
    check(f.ticket.has_value());
    check(!bundle.ready(*handle, f.authority, f.current, Role::data, Direction::device_writes));
    check(bundle.cancel(*handle));
    check(!bundle.prepare(old_grant, f.authority, f.current));
    const auto fresh = bundle.prepare(f.grant(), f.authority, f.current);
    check(fresh && !bundle.cancel(*handle));
    check(bundle.cancel(*fresh));
}

auto admission() -> void {
    Fixture f;
    const auto grant = f.grant();
    for (auto base : {pool_base + 1, pool_base + 4096, UINT64_MAX}) {
        Bundle invalid(f.pool, f.backing, base);
        check(!invalid.prepare(grant, f.authority, f.current) && f.pool.used() == 0);
    }
    for (std::size_t length : {std::size_t{0}, std::size_t{4096}, f.backing.size() - 1}) {
        Bundle invalid(f.pool, std::span{f.backing}.first(length), pool_base);
        check(!invalid.prepare(grant, f.authority, f.current) && f.pool.used() == 0);
    }
    alignas(4096) std::array<std::byte, Bundle::pool_pages * Bundle::page_bytes + 1> misaligned{};
    Bundle invalid(f.pool, std::span{misaligned}.subspan(1), pool_base);
    check(!invalid.prepare(grant, f.authority, f.current) && f.pool.used() == 0);
    PhysicalPages empty;
    Bundle uninitialized(empty, f.backing, pool_base);
    check(!uninitialized.prepare(grant, f.authority, f.current));
    PhysicalPages short_pool;
    check(short_pool.initialize(pool_base, 15));
    Bundle wrong_extent(short_pool, f.backing, pool_base);
    check(!wrong_extent.prepare(grant, f.authority, f.current));
    Bundle bundle(f.pool, f.backing, pool_base);
    check(!bundle.prepare(f.grant(capabilities, 3), f.authority, snapshot(config(), 3)));
    for (std::uint64_t minimum = 1; minimum <= 4; ++minimum)
        check(!bundle.prepare(f.grant(capabilities | (minimum << 48)), f.authority, f.current));
    check(f.pool.used() == 0 && bytes_are(f.backing, std::byte{0xa5}));
}

auto partial_allocation() -> void {
    for (std::size_t available = 0; available < 5; ++available) {
        Fixture f;
        std::array<std::optional<PageLease>, Bundle::pool_pages> independent;
        const auto used = Bundle::pool_pages - available;
        for (std::size_t index = 0; index < used; ++index)
            hold(f.pool, independent[index]);
        Bundle bundle(f.pool, f.backing, pool_base);
        check(!bundle.prepare(f.grant(), f.authority, f.current));
        check(bundle.held_pages() == 0 && !bundle.retained() && f.pool.used() == used);
        check(bytes_are(std::span{f.backing}.first(used * 4096), std::byte{0xa5}));
        check(bytes_are(std::span{f.backing}.subspan(used * 4096), std::byte{0}));
        for (std::size_t index = 0; index < used; ++index)
            check(f.pool.release(*independent[index]));
        const auto retry = bundle.prepare(f.grant(), f.authority, f.current);
        check(retry && bundle.cancel(*retry) && f.pool.used() == 0);
    }
}

auto fragmented_pool() -> void {
    Fixture f;
    std::array<std::optional<PageLease>, Bundle::pool_pages> independent;
    for (auto &lease : independent)
        hold(f.pool, lease);
    for (std::size_t index = 1; index < independent.size(); index += 2) {
        check(f.pool.release(*independent[index]));
        independent[index].reset();
    }
    Bundle bundle(f.pool, f.backing, pool_base);
    const auto handle = bundle.prepare(f.grant(), f.authority, f.current);
    check(handle && f.pool.used() == 13 && bundle.held_pages() == 5);
    for (std::size_t index = 0; index < Bundle::pool_pages; ++index) {
        auto bytes = std::span{f.backing}.subspan(index * 4096, 4096);
        const bool owned = index % 2 == 1 && index <= 9;
        check(bytes_are(bytes, owned ? std::byte{0} : std::byte{0xa5}));
        if (owned)
            std::fill(bytes.begin(), bytes.end(), std::byte{0x5a});
        if (independent[index])
            check(f.pool.address(*independent[index]) == pool_base + index * 4096);
    }
    check(bundle.cancel(*handle) && f.pool.used() == 8);
    for (std::size_t index = 0; index < Bundle::pool_pages; ++index) {
        const bool owned = index % 2 == 1 && index <= 9;
        check(bytes_are(std::span{f.backing}.subspan(index * 4096, 4096), owned ? std::byte{0} : std::byte{0xa5}));
        if (independent[index])
            check(f.pool.release(*independent[index]));
    }
    check(f.pool.used() == 0);
}

auto retention() -> void {
    for (std::size_t failed = 0; failed < 5; ++failed) {
        for (bool preparing : {false, true}) {
            Fixture f;
            {
                Bundle bundle(f.pool, f.backing, pool_base);
                if (preparing)
                    bundle.fail_scrub_for_test(failed);
                const auto handle = bundle.prepare(f.grant(), f.authority, f.current);
                if (preparing) {
                    check(!handle);
                } else {
                    check(handle.has_value());
                    f.backing.fill(std::byte{0x5a});
                    bundle.fail_scrub_for_test(failed);
                    check(!bundle.cancel(*handle));
                    check(!bundle.ready(*handle, f.authority, f.current, Role::data, Direction::device_writes));
                    check(!bundle.cancel(*handle));
                }
                check(bundle.retained() && bundle.held_pages() == 5 && f.pool.used() == 5);
                check(!bundle.prepare(f.grant(), f.authority, f.current));
                check(f.backing[failed * 4096 + 4095] == std::byte{1});
            }
            check(f.pool.used() == 5); // Destruction does not release retained leases.
        }
    }
    for (std::size_t available = 1; available < 5; ++available) {
        Fixture f;
        std::array<std::optional<PageLease>, Bundle::pool_pages> independent;
        const auto used = Bundle::pool_pages - available;
        for (std::size_t index = 0; index < used; ++index)
            hold(f.pool, independent[index]);
        Bundle bundle(f.pool, f.backing, pool_base);
        bundle.fail_scrub_for_test(available - 1);
        check(!bundle.prepare(f.grant(), f.authority, f.current));
        check(bundle.retained() && bundle.held_pages() == available && f.pool.used() == Bundle::pool_pages);
        check(bytes_are(std::span{f.backing}.first(used * 4096), std::byte{0xa5}));
        for (std::size_t index = 0; index < used; ++index)
            check(f.pool.release(*independent[index]));
        check(f.pool.used() == available);
    }
    Fixture f;
    {
        Bundle dropped(f.pool, f.backing, pool_base);
        check(dropped.prepare(f.grant(), f.authority, f.current).has_value());
    }
    check(f.pool.used() == 5); // Even accidental destruction of prepared state leaks safely.
}

auto generations() -> void {
    Fixture f;
    alignas(Bundle) std::array<std::byte, sizeof(Bundle)> storage{};
    auto *bundle = std::construct_at(reinterpret_cast<Bundle *>(storage.data()), f.pool, f.backing, pool_base);
    const auto old = bundle->prepare(f.grant(), f.authority, f.current);
    check(old && bundle->cancel(*old));
    std::destroy_at(bundle);
    bundle = std::construct_at(reinterpret_cast<Bundle *>(storage.data()), f.pool, f.backing, pool_base);
    auto fresh = bundle->prepare(f.grant(), f.authority, f.current);
    check(fresh && fresh->generation() == old->generation() && !bundle->cancel(*old));
    check(bundle->cancel(*fresh));
#ifdef AURORA_NVME_QUEUE_GENERATION_LIMIT
    for (std::uint64_t generation = 2; generation <= AURORA_NVME_QUEUE_GENERATION_LIMIT; ++generation) {
        fresh = bundle->prepare(f.grant(), f.authority, f.current);
        check(fresh && fresh->generation() == generation && bundle->cancel(*fresh));
    }
    for (unsigned attempt = 0; attempt < 3; ++attempt)
        check(!bundle->prepare(f.grant(), f.authority, f.current) && f.pool.used() == 0);
#endif
    std::destroy_at(bundle);
}

auto main() -> int {
    static_assert(!std::is_copy_constructible_v<Bundle> && !std::is_move_constructible_v<Bundle>);
    static_assert(std::is_copy_constructible_v<Handle>);
    static_assert(!std::is_constructible_v<Handle, Bundle &, std::uint64_t, std::uint64_t>);
    basics();
    session_lifetime();
    admission();
    partial_allocation();
    fragmented_pool();
    retention();
    generations();
    std::cout << "PASS: NVMe unpublished page preparation " << checks << " checks\n";
}
