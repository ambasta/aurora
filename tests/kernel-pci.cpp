#include "../kernel/uefi/pci-policy.hpp"
#include <cassert>
#include <iostream>
#include <map>
#include <type_traits>
#include <vector>
using namespace aurora::uefi;
using Buffer = std::vector<std::byte>;
using Header = std::array<std::byte, 64>;
unsigned checks = 0;
auto check(bool condition) -> void {
    ++checks;
    assert(condition);
}
auto checksum(Buffer &bytes) -> void {
    bytes[9] = std::byte{0};
    unsigned sum = 0;
    for (const auto byte : bytes)
        sum += std::to_integer<unsigned>(byte);
    bytes[9] = std::byte(0U - sum);
}
auto mcfg(std::initializer_list<EcamAllocation> allocations) -> Buffer {
    Buffer bytes(44 + allocations.size() * 16);
    bytes[0] = std::byte{'M'};
    bytes[1] = std::byte{'C'};
    bytes[2] = std::byte{'F'};
    bytes[3] = std::byte{'G'};
    put(bytes, 4, bytes.size(), 4);
    put(bytes, 8, 1, 1);
    std::size_t at = 44;
    for (const auto &allocation : allocations) {
        put(bytes, at, allocation.base);
        put(bytes, at + 8, allocation.segment, 2);
        put(bytes, at + 10, allocation.start_bus, 1);
        put(bytes, at + 11, allocation.end_bus, 1);
        at += 16;
    }
    checksum(bytes);
    return bytes;
}
auto descriptor(
    Buffer &map, unsigned index, unsigned type, std::uint64_t begin, std::uint64_t pages, std::uint64_t flags = 0)
    -> void {
    const auto at = index * 40;
    put(map, at, type, 4);
    put(map, at + 8, begin);
    put(map, at + 24, pages);
    put(map, at + 32, flags);
}
auto endpoint(unsigned vendor = 0x1234, unsigned device = 0xabcd, unsigned header = 0) -> Header {
    Header bytes{};
    put(bytes, 0, vendor, 2);
    put(bytes, 2, device, 2);
    put(bytes, 4, 7, 2);
    put(bytes, 8, 3, 1);
    put(bytes, 9, 2, 1);
    put(bytes, 10, 1, 1);
    put(bytes, 11, 4, 1);
    put(bytes, 14, header, 1);
    return bytes;
}
auto bridge(unsigned primary, unsigned secondary, unsigned subordinate) -> Header {
    auto bytes = endpoint(0x1b36, 0x000c, 1);
    put(bytes, 10, 4, 1);
    put(bytes, 11, 6, 1);
    put(bytes, 24, primary, 1);
    put(bytes, 25, secondary, 1);
    put(bytes, 26, subordinate, 1);
    return bytes;
}
class Config final {
public:
    std::map<unsigned, Header> headers;
    std::vector<unsigned> reads;
    std::optional<unsigned> failed;
    auto set(unsigned bus, unsigned device, unsigned function, Header header) -> void {
        headers[(bus << 8) + (device << 3) + function] = header;
    }
    auto operator()(std::uint64_t physical) -> std::optional<Header> {
        check(physical >= Q35Ecam::base && physical < Q35Ecam::end && physical % 4096 == 0);
        const auto key = static_cast<unsigned>((physical - Q35Ecam::base) >> 12);
        reads.push_back(key);
        if (failed && *failed == key)
            return std::nullopt;
        const auto found = headers.find(key);
        if (found != headers.end())
            return found->second;
        Header absent{};
        absent.fill(std::byte{0xff});
        return absent;
    }
    [[nodiscard]] auto read(unsigned bus, unsigned device, unsigned function) const -> bool {
        const auto wanted = (bus << 8) + (device << 3) + function;
        for (auto value : reads)
            if (value == wanted)
                return true;
        return false;
    }
};
auto main() -> int {
    auto bytes = mcfg({{Q35Ecam::base, 0, 0, 255}});
    auto allocation = Mcfg::parse(bytes, 40);
    check(allocation.has_value());
    check(allocation->count() == 1);
    check(allocation->address(0, 0, 0, 0) == Q35Ecam::base);
    check(allocation->address(0, 255, 31, 7) == Q35Ecam::end - 4096);
    for (unsigned bus = 0; bus < 256; ++bus)
        for (unsigned device = 0; device < 32; ++device)
            for (unsigned function = 0; function < 8; ++function) {
                check(allocation->address(0, bus, device, function) == Q35Ecam::base + (std::uint64_t{bus} << 20) +
                                                                           (std::uint64_t{device} << 15) +
                                                                           (std::uint64_t{function} << 12));
            }
    check(!allocation->address(1, 0, 0, 0));
    check(!allocation->address(65536, 0, 0, 0));
    check(!allocation->address(0, 256, 0, 0));
    check(!allocation->address(0, 0, 32, 0));
    check(!allocation->address(0, 0, 0, 8));
    // A nonzero start bus still uses the base for absolute bus zero.
    auto partial = Mcfg::parse(mcfg({{0x80000000, 9, 128, 191}}), 32);
    check(partial && partial->address(9, 128, 3, 2) == 0x8801a000);
    check(partial && !partial->address(9, 127, 0, 0) && !partial->address(9, 192, 0, 0));
    for (auto bits : {0U, 31U, 53U, 64U})
        check(!Mcfg::parse(bytes, bits));
    for (auto bits : {32U, 36U, 40U, 48U, 52U}) {
        const auto last_base = (1ULL << bits) - 0x10000000ULL;
        auto last = Mcfg::parse(mcfg({{last_base, 65535, 255, 255}}), bits);
        check(last && last->address(65535, 255, 31, 7) == (1ULL << bits) - 4096);
        check(!Mcfg::parse(mcfg({{1ULL << bits, 0, 0, 0}}), bits));
    }
    check(!Mcfg::parse(mcfg({{0xfffffffff0000000ULL, 0, 0, 255}}), 52));
    check(!Mcfg::parse(mcfg({{Q35Ecam::base + 4096, 0, 0, 255}}), 40));
    check(!Mcfg::parse(mcfg({{Q35Ecam::base, 0, 8, 7}}), 40));
    check(!Mcfg::parse(mcfg({}), 40));
    auto copied_table = bytes;
    const auto independent = Mcfg::parse(copied_table, 40);
    copied_table.assign(copied_table.size(), std::byte{});
    check(independent && independent->address(0, 0, 0, 0) == Q35Ecam::base);
    // Nonzero MCFG reserved bytes are rejected before any ECAM authority exists.
    // This includes the former pci-reserved guest mutation at byte 36.
    for (auto field : {8U, 36U, 37U, 38U, 39U, 40U, 41U, 42U, 43U, 56U, 57U, 58U, 59U}) {
        auto invalid = bytes;
        put(invalid, field, 2, 1);
        checksum(invalid);
        check(!Mcfg::parse(invalid, 40));
    }
    auto invalid = bytes;
    invalid[0] = std::byte{'N'};
    checksum(invalid);
    check(!Mcfg::parse(invalid, 40));
    invalid = bytes;
    invalid[35] ^= std::byte{1};
    check(!Mcfg::parse(invalid, 40));
    invalid = bytes;
    put(invalid, 4, bytes.size() - 1, 4);
    checksum(invalid);
    check(!Mcfg::parse(invalid, 40));
    invalid = bytes;
    invalid.push_back(std::byte{});
    put(invalid, 4, invalid.size(), 4);
    checksum(invalid);
    check(!Mcfg::parse(invalid, 40));
    for (std::size_t length = 0; length < 60; ++length)
        check(!Mcfg::parse(std::span{bytes}.first(length), 40));
    // Duplicate allocations (formerly pci-overlap) violate these same bus and
    // physical overlap checks; exercise both predicates independently.
    check(!Mcfg::parse(mcfg({{0x80000000, 0, 0, 127}, {0x90000000, 0, 127, 255}}), 40)); // Segment/bus overlap.
    check(!Mcfg::parse(mcfg({{0x80000000, 0, 0, 127}, {0x80000000, 1, 127, 255}}),
                       40)); // Physical overlap across segments.
    check(Mcfg::parse(mcfg({{0x80000000, 0, 0, 127}, {0x80000000, 0, 128, 255}}), 40).has_value());
    check(
        Mcfg::parse(
            mcfg({{0x80000000, 0, 0, 255}, {0x90000000, 1, 0, 255}, {0xa0000000, 2, 0, 255}, {0xb0000000, 3, 0, 255}}),
            40)
            .has_value());
    check(!Mcfg::parse(mcfg({{0x70000000, 0, 0, 255},
                             {0x80000000, 1, 0, 255},
                             {0x90000000, 2, 0, 255},
                             {0xa0000000, 3, 0, 255},
                             {0xb0000000, 4, 0, 255}}),
                       40));
    Buffer map(40);
    descriptor(map, 0, 1, 0x400000, 256);
    auto aperture = Q35Ecam::authorize(*allocation, map, 40, 0x400000);
    check(aperture.has_value());
    check(aperture->admits_page(Q35Ecam::base) && aperture->admits_page(Q35Ecam::end - 4096));
    check(aperture->contains(Q35Ecam::base, Q35Ecam::bytes));
    check(!aperture->contains(Q35Ecam::base, 0));
    check(!aperture->contains(Q35Ecam::base, Q35Ecam::bytes + 1));
    check(!aperture->contains(Q35Ecam::base, ~0ULL));
    check(!aperture->contains(~0ULL, 2));
    check(!aperture->admits_page(Q35Ecam::base + 1));
    check(!aperture->admits_page(Q35Ecam::base - 4096));
    check(!aperture->admits_page(Q35Ecam::end));
    check(!aperture->address(0, 256, 0, 0));
    check(!aperture->address(1, 0, 0, 0));
    check(!aperture->address(0, 0, 32, 0));
    check(!aperture->address(0, 0, 0, 8));
    check(aperture->address(0, 255, 31, 7) == Q35Ecam::end - 4096);
    check(!Q35Ecam::authorize(*partial, map, 40, 0x400000));
    // A zero MCFG base is parseable, but never authorizes q35 ECAM. This is
    // the former pci-range guest decision, not an MCFG syntax rejection.
    for (const auto candidate : {EcamAllocation{0, 0, 0, 255},
                                 EcamAllocation{0xa0000000, 0, 0, 255},
                                 EcamAllocation{0xb0000000, 0, 0, 255},
                                 EcamAllocation{Q35Ecam::base, 1, 0, 255},
                                 EcamAllocation{Q35Ecam::base, 0, 1, 255},
                                 EcamAllocation{Q35Ecam::base, 0, 0, 254}}) {
        const auto parsed = Mcfg::parse(mcfg({candidate}), 40);
        check(parsed && !Q35Ecam::authorize(*parsed, map, 40, 0x400000));
    }
    const auto two = Mcfg::parse(mcfg({{Q35Ecam::base, 0, 0, 255}, {0xc0000000, 1, 0, 255}}), 40);
    check(two && !Q35Ecam::authorize(*two, map, 40, 0x400000));
    for (unsigned type = 0; type <= 15; ++type)
        for (auto flags : {0ULL, 8ULL, 0x8000ULL, 0x8008ULL, 1ULL << 63, (1ULL << 63) | 8ULL}) {
            descriptor(map, 0, type, Q35Ecam::base, 65536, flags);
            check(Q35Ecam::authorize(*allocation, map, 40, 0x400000).has_value() ==
                  ((type == 0 || type == 11) && !(flags & ((1ULL << 63) | 0x8000ULL))));
        }
    // Detect even a single protected page, with absent/reserved neighbors.
    map.resize(120);
    descriptor(map, 0, 0, Q35Ecam::base, 3);
    descriptor(map, 1, 9, Q35Ecam::base + 3 * 4096, 1);
    descriptor(map, 2, 11, Q35Ecam::base + 4 * 4096, 1);
    check(!Q35Ecam::authorize(*allocation, map, 40, 0x400000));
    descriptor(map, 1, 0, Q35Ecam::base + 3 * 4096, 1);
    check(Q35Ecam::authorize(*allocation, map, 40, 0x400000).has_value());
    descriptor(map, 1, 0, Q35Ecam::base + 2 * 4096, 1);
    check(!Q35Ecam::authorize(*allocation, map, 40, 0x400000)); // Invalid map overlap.
    map.resize(40);
    descriptor(map, 0, 1, Q35Ecam::base - 4096, 2);
    check(!Q35Ecam::authorize(*allocation, map, 40, 0x400000));
    descriptor(map, 0, 9, Q35Ecam::end - 4096, 2);
    check(!Q35Ecam::authorize(*allocation, map, 40, 0x400000));
    descriptor(map, 0, 1, Q35Ecam::base - 4096, 1);
    check(Q35Ecam::authorize(*allocation, map, 40, 0x400000).has_value());
    descriptor(map, 0, 6, Q35Ecam::end, 1, 1ULL << 63);
    check(Q35Ecam::authorize(*allocation, map, 40, 0x400000).has_value());
    descriptor(map, 0, 1, 0x400000, 256);
    for (auto arena : std::array<std::uint64_t, 6>{Q35Ecam::base,
                                                   Q35Ecam::base - Handoff::arena_bytes + 4096,
                                                   Q35Ecam::end - 4096,
                                                   ~0ULL - 4095,
                                                   1ULL << 40,
                                                   0x400001ULL})
        check(!Q35Ecam::authorize(*allocation, map, 40, arena));
    check(Q35Ecam::authorize(*allocation, map, 40, Q35Ecam::base - Handoff::arena_bytes).has_value());
    check(Q35Ecam::authorize(*allocation, map, 40, Q35Ecam::end).has_value());
    for (auto stride : {0U, 8U, 39U, 41U, 264U})
        check(!Q35Ecam::authorize(*allocation, map, stride, 0x400000));
    check(!Q35Ecam::authorize(*allocation, {}, 40, 0x400000));
    descriptor(map, 0, 0, 1ULL << 40, 1);
    check(!Q35Ecam::authorize(*allocation, map, 40, 0x400000));
    descriptor(map, 0, 0, ~0ULL - 4095, 1);
    check(!Q35Ecam::authorize(*allocation, map, 40, 0x400000));
    Config empty;
    auto inventory = PciInventory::scan(*aperture, empty);
    check(inventory && inventory->count() == 0 && inventory->bus_count() == 1 && empty.reads.size() == 32);
    Config single;
    single.set(0, 2, 0, endpoint());
    single.set(0, 2, 1, endpoint());
    single.set(0, 3, 1, endpoint());
    inventory = PciInventory::scan(*aperture, single);
    check(inventory && inventory->count() == 1 && inventory->bus_count() == 1 && single.reads.size() == 32);
    check(!single.read(0, 2, 1) && !single.read(0, 3, 1));
    const auto &copied = inventory->functions()[0];
    check(copied.bus == 0 && copied.device == 2 && copied.function == 0 && copied.segment == 0 &&
          copied.vendor == 0x1234 && copied.device_id == 0xabcd && copied.command == 7 && copied.class_code == 4 &&
          copied.subclass == 1 && copied.programming_interface == 2 && copied.revision == 3 && copied.header_type == 0);
    single.headers.clear();
    check(inventory->functions()[0].vendor == 0x1234); // Independent final snapshot.
    static_assert(std::is_same_v<decltype(inventory->functions()), std::span<const PciFunction>>);
    Config multi;
    multi.set(0, 1, 0, endpoint(1, 2, 0x80));
    multi.set(0, 1, 3, endpoint(3, 4));
    multi.set(0, 1, 7, endpoint(5, 6));
    inventory = PciInventory::scan(*aperture, multi);
    check(inventory && inventory->count() == 3 && multi.reads.size() == 39);
    check(multi.read(0, 1, 7));
    Config tree;
    tree.set(0, 1, 0, bridge(0, 2, 7));
    tree.set(0, 2, 0, bridge(0, 8, 9));
    tree.set(2, 0, 0, bridge(2, 4, 5));
    tree.set(2, 1, 0, endpoint());
    tree.set(4, 0, 0, endpoint());
    tree.set(8, 0, 0, endpoint());
    tree.set(5, 0, 0, endpoint());
    tree.set(9, 0, 0, endpoint()); // Unreachable buses must not be blindly scanned.
    inventory = PciInventory::scan(*aperture, tree);
    check(inventory && inventory->bus_count() == 4 && inventory->count() == 6);
    check(!tree.read(5, 0, 0) && !tree.read(9, 0, 0) && !tree.read(1, 0, 0));
    check(inventory->functions()[0].secondary_bus == 2 && inventory->functions()[0].subordinate_bus == 7);
    Config unconfigured;
    unconfigured.set(0, 0, 0, bridge(0, 0, 0));
    inventory = PciInventory::scan(*aperture, unconfigured);
    check(inventory && inventory->count() == 1 && inventory->bus_count() == 1);
    Config zero_vendor;
    zero_vendor.set(0, 0, 0, endpoint(0, 2));
    check(!PciInventory::scan(*aperture, zero_vendor));
    Config false_bridge;
    false_bridge.set(0, 0, 0, endpoint(1, 2, 1));
    check(!PciInventory::scan(*aperture, false_bridge));
    Config false_endpoint;
    auto contradiction = bridge(0, 1, 1);
    put(contradiction, 14, 0, 1);
    false_endpoint.set(0, 0, 0, contradiction);
    check(!PciInventory::scan(*aperture, false_endpoint));
    for (auto type : {2U, 3U, 127U, 130U, 255U}) {
        Config bad;
        bad.set(0, 0, 0, endpoint(1, 2, type));
        check(!PciInventory::scan(*aperture, bad));
    }
    for (auto tuple :
         {std::array{1U, 2U, 3U}, std::array{0U, 0U, 1U}, std::array{0U, 2U, 1U}, std::array{0U, 2U, 0U}}) {
        Config bad;
        bad.set(0, 0, 0, bridge(tuple[0], tuple[1], tuple[2]));
        check(!PciInventory::scan(*aperture, bad));
    }
    Config duplicate;
    duplicate.set(0, 0, 0, bridge(0, 2, 5));
    duplicate.set(0, 1, 0, bridge(0, 2, 5));
    check(!PciInventory::scan(*aperture, duplicate));
    Config overlap;
    overlap.set(0, 0, 0, bridge(0, 2, 5));
    overlap.set(0, 1, 0, bridge(0, 4, 7));
    check(!PciInventory::scan(*aperture, overlap));
    Config cross_parent;
    cross_parent.set(0, 0, 0, bridge(0, 2, 5));
    cross_parent.set(2, 0, 0, bridge(2, 6, 7));
    check(!PciInventory::scan(*aperture, cross_parent));
    Config oversized_child;
    oversized_child.set(0, 0, 0, bridge(0, 2, 5));
    oversized_child.set(2, 0, 0, bridge(2, 3, 6));
    check(!PciInventory::scan(*aperture, oversized_child));
    for (auto secondary : {0U, 1U, 2U}) {
        Config cycle;
        cycle.set(0, 0, 0, bridge(0, 1, 5));
        cycle.set(1, 0, 0, bridge(1, 2, 5));
        cycle.set(2, 0, 0, bridge(2, secondary, 5));
        check(!PciInventory::scan(*aperture, cycle));
    }
    Config bad_primary;
    bad_primary.set(0, 0, 0, bridge(0, 1, 5));
    bad_primary.set(1, 0, 0, bridge(0, 2, 5));
    check(!PciInventory::scan(*aperture, bad_primary));
    Config failure;
    failure.set(0, 0, 0, endpoint());
    failure.failed = 1U << 3;
    check(!PciInventory::scan(*aperture, failure));
    // Both bounds allow their exact maximum and reject the next discovered item.
    for (unsigned buses : {64U, 65U}) {
        Config chain;
        for (unsigned bus = 0; bus + 1 < buses; ++bus)
            chain.set(bus, 0, 0, bridge(bus, bus + 1, 255));
        inventory = PciInventory::scan(*aperture, chain);
        check(inventory.has_value() == (buses == 64));
        if (inventory)
            check(inventory->bus_count() == 64 && inventory->count() == 63);
        check(chain.reads.size() <= 64 * 32 * 8);
    }
    for (unsigned count : {256U, 257U}) {
        Config full;
        for (unsigned device = 0; device < 32; ++device)
            for (unsigned function = 0; function < 8; ++function)
                full.set(0, device, function, endpoint(1, 2, function == 0 ? 0x80 : 0));
        if (count == 257) {
            auto route = bridge(0, 1, 1);
            put(route, 14, 0x81, 1);
            full.set(0, 0, 0, route);
            full.set(1, 0, 0, endpoint());
        }
        inventory = PciInventory::scan(*aperture, full);
        check(inventory.has_value() == (count == 256));
        if (inventory)
            check(inventory->count() == 256 && full.reads.size() == 256);
    }
    // A bridge at a nonzero function is discovered only after function zero advertises it.
    Config function_bridge;
    function_bridge.set(0, 0, 0, endpoint(1, 2, 0x80));
    function_bridge.set(0, 0, 7, bridge(0, 255, 255));
    function_bridge.set(255, 31, 0, endpoint());
    inventory = PciInventory::scan(*aperture, function_bridge);
    check(inventory && inventory->count() == 3 && inventory->bus_count() == 2);
    std::cout << "PASS: " << checks << " PCI MCFG/aperture/snapshot/topology/boundary cases\n";
}
