#include "../kernel/uefi/acpi-policy.hpp"
#include "../kernel/uefi/ap-worker-policy.hpp"
#include <cassert>
#include <iostream>
#include <type_traits>
#include <vector>

namespace kernel_acpi {
using namespace aurora::uefi;
using Buffer = std::vector<std::byte>;
unsigned checks = 0;
auto check(bool condition) -> void {
    ++checks;
    assert(condition);
}
auto checksum(Buffer &buffer, std::size_t field = 9) -> void {
    buffer[field] = std::byte{0};
    unsigned total = 0;
    for (auto b : buffer)
        total += std::to_integer<unsigned>(b);
    buffer[field] = std::byte(0U - total);
}
auto table(std::string_view signature, std::size_t size) -> Buffer {
    Buffer result(size);
    for (std::size_t i = 0; i < signature.size(); ++i)
        result[i] = std::byte(signature[i]);
    put(result, 4, size, 4);
    put(result, 8, 1, 1);
    return result;
}
static_assert(!std::is_default_constructible_v<ApWorkerTopology> && !std::is_aggregate_v<ApWorkerTopology>);
static_assert(std::is_copy_constructible_v<ApWorkerTopology> && !std::is_copy_assignable_v<ApWorkerTopology>);
static_assert(!std::is_default_constructible_v<PmTimerAdmission> && !std::is_aggregate_v<PmTimerAdmission>);
static_assert(!std::is_constructible_v<PmTimerAdmission, unsigned>);
static_assert(std::is_copy_constructible_v<PmTimerAdmission> && !std::is_copy_assignable_v<PmTimerAdmission>);
static_assert(!std::is_default_constructible_v<ApWorkerAdmission> && !std::is_aggregate_v<ApWorkerAdmission>);
static_assert(std::is_copy_constructible_v<ApWorkerAdmission> && !std::is_copy_assignable_v<ApWorkerAdmission>);

auto worker_madt(unsigned count = 2, bool extended = false) -> Buffer {
    const unsigned record_bytes = extended ? 16 : 8;
    auto result = table("APIC", 44 + count * record_bytes);
    put(result, 36, ApWorkerAdmission::physical_address, 4);
    for (unsigned cpu = 0; cpu < count; ++cpu) {
        const auto at = 44 + cpu * record_bytes;
        put(result, at, extended ? 9 : 0, 1);
        put(result, at + 1, record_bytes, 1);
        put(result, at + (extended ? 4 : 3), cpu, extended ? 4 : 1);
        put(result, at + (extended ? 12 : 2), cpu, extended ? 4 : 1);
        put(result, at + (extended ? 8 : 4), 1, 4);
    }
    checksum(result);
    return result;
}
auto worker_fadt(bool extended = true) -> Buffer {
    auto result = table("FACP", extended ? 244 : 116);
    put(result, 8, extended ? 3 : 1, 1);
    put(result, 76, 0x608, 4);
    put(result, 91, 4, 1);
    if (extended) {
        put(result, 208, 1, 1);
        put(result, 209, 32, 1);
        put(result, 212, 0x608);
    }
    checksum(result);
    return result;
}
auto ap_worker_cases() -> void {
    auto fadt = worker_fadt();
    const auto timer = PmTimerAdmission::parse_q35(fadt);
    check(timer && timer->port() == 0x608 && timer->counter_bits() == 24 && timer->counter_mask() == 0xffffff);
    check(PmTimerAdmission::parse_q35(worker_fadt(false)).has_value());
    check(timer->delta(0xfffff0, 0x10) == 32 && timer->delta(100, 100) == 0);
    check(timer->delta(10, 727) == PmTimerAdmission::ticks_200us);
    check(timer->bounded_ticks(35797) && timer->bounded_ticks(717) && timer->bounded_ticks(0x7fffff));
    check(!timer->bounded_ticks(0) && !timer->bounded_ticks(0x800000));
    check(PmTimerAdmission::frequency == 3579545 && PmTimerAdmission::ticks_10ms == 35797 &&
          PmTimerAdmission::ticks_200us == 717);
    auto timer32_bytes = fadt;
    put(timer32_bytes, 112, 1U << 8, 4);
    checksum(timer32_bytes);
    const auto timer32 = PmTimerAdmission::parse_q35(timer32_bytes);
    check(timer32 && timer32->counter_bits() == 32 && timer32->counter_mask() == 0xffffffff);
    check(timer32->delta(0xfffffff0, 0x10) == 32 && timer32->bounded_ticks(0x7fffffff));
    check(!timer32->bounded_ticks(0x80000000));
    for (const unsigned port : {0U, 0x600U, 0x604U, 0x60cU, 0xcf8U, 0xffffU, 0x10000U}) {
        auto bad = fadt;
        put(bad, 76, port, 4);
        put(bad, 212, port);
        checksum(bad);
        check(!PmTimerAdmission::parse_q35(bad));
    }
    for (const auto field : {8U, 91U, 208U, 209U, 210U, 211U}) {
        auto bad = fadt;
        put(bad, field, field == 8 ? 2 : field == 91 ? 3 : field == 208 ? 0 : field == 209 ? 24 : 1, 1);
        checksum(bad);
        check(!PmTimerAdmission::parse_q35(bad));
    }
    for (const auto access : {0U, 3U}) {
        auto good = fadt;
        put(good, 211, access, 1);
        checksum(good);
        check(PmTimerAdmission::parse_q35(good).has_value());
    }
    auto changed = fadt;
    put(changed, 76, 0, 4);
    checksum(changed);
    check(PmTimerAdmission::parse_q35(changed).has_value()); // Extended takes precedence.
    put(changed, 76, 0x604, 4);
    checksum(changed);
    check(!PmTimerAdmission::parse_q35(changed)); // Conflicting nonzero legacy address.
    changed = fadt;
    put(changed, 212, 0);
    checksum(changed);
    check(!PmTimerAdmission::parse_q35(changed)); // Partial GAS is not a legacy fallback.
    put(changed, 208, 0, 4);
    checksum(changed);
    check(PmTimerAdmission::parse_q35(changed).has_value());
    for (const auto address : {0x100000608ULL, ~0ULL}) {
        changed = fadt;
        put(changed, 76, 0, 4);
        put(changed, 212, address);
        checksum(changed);
        check(!PmTimerAdmission::parse_q35(changed));
    }
    for (const auto length : {0U, 35U, 115U, 116U, 207U, 219U, 243U, 277U}) {
        changed = fadt;
        changed.resize(length);
        if (length >= 36) {
            put(changed, 4, length, 4);
            checksum(changed);
        }
        check(!PmTimerAdmission::parse_q35(changed));
    }
    changed = fadt;
    changed[9] ^= std::byte{1};
    check(!PmTimerAdmission::parse_q35(changed));
    changed = fadt;
    put(changed, 112, 1U << 20, 4);
    checksum(changed);
    check(!PmTimerAdmission::parse_q35(changed));
    changed = fadt;
    put(changed, 4, 116, 4);
    checksum(changed);
    check(!PmTimerAdmission::parse_q35(changed));

    const auto topology = Topology::parse(worker_madt(), 40);
    check(topology.has_value());
    const auto copied = ApWorkerTopology::copy(*topology);
    check(copied && copied->processors().size() == 2 && copied->processors()[0].id == 0 &&
          copied->processors()[1].id == 1 && copied->apic() == ApWorkerAdmission::physical_address);
    // Copy remains independent after the backing bytes and temporary parser die.
    const auto independent = [] {
        auto bytes = worker_madt();
        const auto parsed = Topology::parse(bytes, 40);
        const auto facts = ApWorkerTopology::copy(*parsed);
        for (auto &byte : bytes)
            byte = std::byte{0};
        return facts;
    }();
    check(independent && independent->processors()[1].uid == 1);
    for (const unsigned count : {1U, 3U}) {
        const auto parsed = Topology::parse(worker_madt(count), 40);
        check(parsed && !ApWorkerTopology::copy(*parsed));
    }
    check(!Topology::parse(worker_madt(0), 40));
    const auto extended = Topology::parse(worker_madt(2, true), 40);
    check(extended && !ApWorkerTopology::copy(*extended));
    for (const unsigned flags : {0U, 2U, 3U}) {
        auto bad = worker_madt();
        put(bad, 56, flags, 4);
        checksum(bad);
        const auto parsed = Topology::parse(bad, 40);
        check(parsed && !ApWorkerTopology::copy(*parsed));
    }
    for (const unsigned offset : {54U, 55U}) {
        auto bad = worker_madt();
        put(bad, offset, 0, 1);
        checksum(bad);
        check(!Topology::parse(bad, 40)); // Duplicate UID or LAPIC ID.
    }
    auto broadcast = worker_madt();
    put(broadcast, 55, 255, 1);
    checksum(broadcast);
    const auto broadcast_topology = Topology::parse(broadcast, 40);
    check(broadcast_topology && !ApWorkerTopology::copy(*broadcast_topology));

    using Admission = ApWorkerAdmission;
    constexpr std::uint64_t arena = 0x2000000, root = arena + Handoff::tables_offset;
    constexpr std::uint32_t features = (1U << 5) | (1U << 6) | (1U << 9) | (1U << 16);
    constexpr std::uint32_t extended_features = (1U << 20) | (1U << 29);
    constexpr std::uint64_t pat = 0x0007040600070406ULL;
    Buffer map(80);
    put(map, 0, 1, 4);
    put(map, 8, arena);
    put(map, 24, Handoff::arena_bytes / 4096);
    put(map, 32, 8);
    put(map, 40, 0, 4);
    put(map, 48, Admission::physical_address);
    put(map, 64, 1);
    put(map, 72, 1);
    const auto admit = [&](std::span<const std::byte> final_map,
                           std::uint32_t ebx = 2U << 16,
                           std::uint32_t edx = (1U << 5) | (1U << 6) | (1U << 9) | (1U << 16),
                           std::uint32_t ext = (1U << 20) | (1U << 29),
                           std::uint64_t base = Admission::physical_address | 0x900,
                           std::uint64_t current_pat = 0x0007040600070406ULL,
                           std::uint64_t current_root = 0x2000000 + Handoff::tables_offset,
                           std::uint32_t vendor = 0x756e6547,
                           unsigned bits = 40,
                           unsigned version = 1,
                           std::size_t stride = 40) {
        return Admission::authorize(*copied,
                                    *timer,
                                    final_map,
                                    stride,
                                    version,
                                    arena,
                                    current_root,
                                    bits,
                                    vendor,
                                    0x49656e69,
                                    0x6c65746e,
                                    edx,
                                    ebx,
                                    ext,
                                    base,
                                    current_pat);
    };
    const auto grant = admit(map);
    check(grant && grant->bsp_id() == 0 && grant->ap_id() == 1 && grant->owned_arena() == arena &&
          grant->kernel_root() == root && grant->physical_bits() == 40 && grant->pm_timer().port() == 0x608);
    const auto second_bsp = admit(map, (1U << 24) | (2U << 16));
    check(second_bsp && second_bsp->bsp_id() == 1 && second_bsp->ap_id() == 0);
    check(!admit(map, (2U << 24) | (2U << 16)));
    for (const auto count : {0U, 1U, 3U, 255U})
        check(!admit(map, count << 16));
    for (const unsigned bit : {5U, 6U, 9U, 16U})
        check(!admit(map, 2U << 16, features & ~(1U << bit)));
    for (const unsigned bit : {20U, 29U})
        check(!admit(map, 2U << 16, features, extended_features & ~(1U << bit)));
    for (const auto base : {Admission::physical_address,
                            Admission::physical_address | 0x800,
                            Admission::physical_address | 0xd00,
                            std::uint64_t{0xfec00900}})
        check(!admit(map, 2U << 16, features, extended_features, base));
    check(!admit(map, 2U << 16, features, extended_features, Admission::physical_address | 0x900, pat | (6ULL << 24)));
    check(!admit(map, 2U << 16, features, extended_features, Admission::physical_address | 0x900, pat, root + 4096));
    check(
        !admit(map, 2U << 16, features, extended_features, Admission::physical_address | 0x900, pat, root, 0x68747541));
    for (const unsigned bits : {31U, 53U})
        check(!admit(map,
                     2U << 16,
                     features,
                     extended_features,
                     Admission::physical_address | 0x900,
                     pat,
                     root,
                     0x756e6547,
                     bits));
    check(!Admission::authorize(*copied,
                                *timer32,
                                map,
                                40,
                                1,
                                arena,
                                root,
                                40,
                                0x756e6547,
                                0x49656e69,
                                0x6c65746e,
                                features,
                                2U << 16,
                                extended_features,
                                Admission::physical_address | 0x900,
                                pat));
    check(grant->matches_registers(0, 0x50014) && !grant->matches_registers(1U << 24, 0x50014));
    check(!grant->matches_registers(0, 0x40014) && !grant->matches_registers(0, 0x5000f));
    check(grant->admits(Admission::virtual_address, Admission::physical_address, 4096, Admission::leaf_flags));
    check(!grant->admits(Admission::virtual_address, Admission::physical_address, 8192, Admission::leaf_flags));
    check(!grant->admits(Admission::virtual_address, Admission::physical_address, 4096, 3));
    check(grant->mapping(Admission::virtual_address) == (Admission::physical_address | Admission::leaf_flags) &&
          grant->mapping(Admission::virtual_address + 4096) == 0);
    for (unsigned type = 0; type <= 15; ++type) {
        auto candidate = map;
        put(candidate, 40, type, 4);
        check(admit(candidate).has_value() == (type == 0 || type == 11));
    }
    for (const std::uint64_t attribute : {0ULL, 1ULL, 0x4000ULL, 0x4001ULL, 8ULL, 2ULL, 0x8000ULL, 1ULL << 63}) {
        auto candidate = map;
        put(candidate, 72, attribute);
        check(admit(candidate).has_value() == ((attribute & ~0x4001ULL) == 0));
    }
    auto bad_map = map;
    put(bad_map, 0, 7, 4);
    check(!admit(bad_map));
    bad_map = map;
    put(bad_map, 32, 8ULL | (1ULL << 63));
    check(!admit(bad_map));
    bad_map = map;
    put(bad_map, 24, Handoff::arena_bytes / 4096 - 1);
    check(!admit(bad_map));
    bad_map = map;
    put(bad_map, 48, 1ULL << 40);
    check(!admit(bad_map));
    check(admit(std::span{map}.first(40)).has_value()); // q35 omitted LAPIC resource descriptor.
    check(!admit(std::span{map}.first(79)));
}
auto main() -> int {
    std::array<std::byte, 120> raw{};
    const auto descriptor =
        [&](unsigned n, unsigned type, std::uint64_t start, std::uint64_t pages, std::uint64_t flags = 8) {
            put(raw, n * 40, type, 4);
            put(raw, n * 40 + 8, start);
            put(raw, n * 40 + 24, pages);
            put(raw, n * 40 + 32, flags);
        };
    descriptor(0, 9, 0x100000, 1);
    descriptor(1, 6, 0x101000, 1, 8 | (1ULL << 63));
    descriptor(2, 1, 0x400000, 256);
    FirmwareRanges ranges{raw, 40, 0x400000, 40};
    check(ranges.readable(0x100ff0, 32));
    check(ranges.readable(0x101000, 4096));
    check(!ranges.readable(0x400000, 1));
    check(!ranges.readable(0x0fffff, 1));
    check(!ranges.readable(0x101fff, 2));
    check(!ranges.readable(0x100000, 0));
    check(!ranges.readable(~0ULL, 2));
    for (unsigned type = 0; type <= 15; ++type) {
        descriptor(0, type, 0x100000, 1);
        check(ranges.readable(0x100000, 4096) == (type == 2 || type == 4 || type == 6 || type == 9 || type == 10));
    }
    descriptor(0, 6, 0x100000, 1, 8 | 0x8000);
    check(!ranges.readable(0x100000, 1));
    descriptor(0, 9, 0x100000, 1, 0);
    check(!ranges.readable(0x100000, 1));
    descriptor(0, 9, (1ULL << 40) - 4096, 1);
    check(ranges.readable((1ULL << 40) - 1, 1));
    check(!ranges.readable(1ULL << 40, 1));
    for (unsigned bits : {0, 31, 53, 64})
        check(!FirmwareRanges{raw, 40, 0x400000, bits}.readable((1ULL << 40) - 4096, 1));
    descriptor(0, 9, 0x100000, 1);
    for (std::uint64_t offset = 0; offset < 4096; ++offset) {
        ReadPlan plan{0x100000 + offset, 8193};
        std::uint64_t done = 0;
        while (done < 8193) {
            const auto chunk = plan.next(done);
            check(chunk && chunk->page % 4096 == 0 && chunk->offset < 4096 && chunk->count > 0 &&
                  chunk->count <= 4096 - chunk->offset && chunk->page + chunk->offset == 0x100000 + offset + done);
            done += chunk->count;
        }
        check(done == 8193 && !plan.next(done));
    }
    check(!ReadPlan{~0ULL - 7, 16}.next(0));
    check(!ReadPlan{0x100000, 65537}.next(0));
    check(!ReadPlan{0x100000, 0}.next(0));
    WindowAuthority first, second;
    auto ticket = first.acquire();
    check(ticket.has_value());
    check(first.accepts(*ticket));
    check(!first.acquire());
    check(!second.accepts(*ticket));
    check(!second.revoke(*ticket));
    check(first.revoke(*ticket));
    check(!first.accepts(*ticket));
    check(!first.revoke(*ticket));
    auto next = first.acquire();
    check(next && !first.accepts(*ticket));
    check(first.revoke(*next));
    std::optional<WindowAuthority> lifetime;
    lifetime.emplace();
    const auto stale = lifetime->acquire();
    check(stale.has_value());
    lifetime.reset();
    lifetime.emplace();
    const auto fresh = lifetime->acquire();
    check(fresh && !lifetime->accepts(*stale) && !lifetime->revoke(*stale) && lifetime->accepts(*fresh));
    std::array<std::byte, 24> root{};
    constexpr std::array<unsigned char, 16> guid{
        0x71, 0xe8, 0x68, 0x88, 0xf1, 0xe4, 0xd3, 0x11, 0xbc, 0x22, 0, 0x80, 0xc7, 0x3c, 0x88, 0x81};
    for (unsigned i = 0; i < 16; ++i)
        root[i] = std::byte(guid[i]);
    put(root, 16, 0x100000);
    AcpiRoots roots;
    check(roots.accept(root));
    check(roots.root() == 0x100000);
    check(!roots.accept(root));
    check(roots.root() == 0);
    put(root, 16, 0x101000);
    check(!roots.accept(root));
    Buffer rsdp(36);
    const std::string_view rsdp_sig = "RSD PTR ";
    for (std::size_t i = 0; i < 8; ++i)
        rsdp[i] = std::byte(rsdp_sig[i]);
    put(rsdp, 15, 2, 1);
    put(rsdp, 20, 36, 4);
    put(rsdp, 24, 0x101000);
    Buffer first20(rsdp.begin(), rsdp.begin() + 20);
    checksum(first20, 8);
    rsdp[8] = first20[8];
    checksum(rsdp, 32);
    check(Acpi::rsdp(rsdp) == 0x101000);
    check(Acpi::same_header(rsdp, rsdp));
    auto invalid = rsdp;
    invalid[0] ^= std::byte{1};
    check(!Acpi::rsdp(invalid));
    invalid = rsdp;
    invalid[32] ^= std::byte{1};
    check(!Acpi::rsdp(invalid));
    invalid = rsdp;
    invalid[8] ^= std::byte{1};
    checksum(invalid, 32);
    check(!Acpi::rsdp(invalid));
    invalid = rsdp;
    put(invalid, 20, 4097, 4);
    checksum(invalid, 32);
    check(!Acpi::rsdp(invalid));
    auto xsdt = table("XSDT", 52);
    put(xsdt, 36, 0x102000);
    put(xsdt, 44, 0x103000);
    checksum(xsdt);
    check(Acpi::xsdt(xsdt, 0x101000));
    invalid = xsdt;
    put(invalid, 44, 0x102000);
    checksum(invalid);
    check(!Acpi::xsdt(invalid, 0x101000));
    invalid = xsdt;
    put(invalid, 44, 0x101000);
    checksum(invalid);
    check(!Acpi::xsdt(invalid, 0x101000));
    invalid = xsdt;
    put(invalid, 44, 0);
    checksum(invalid);
    check(!Acpi::xsdt(invalid, 0x101000));
    invalid = xsdt;
    put(invalid, 8, 0, 1);
    checksum(invalid);
    check(!Acpi::xsdt(invalid, 0x101000));
    invalid = xsdt;
    // Former acpi-changed-header: repaired checksum cannot authorize a changed header.
    invalid[10] ^= std::byte{1};
    checksum(invalid);
    check(!Acpi::same_header(invalid, std::span{xsdt}.first(36)));
    auto madt = table("APIC", 44 + 8 + 16 + 12 + 2);
    put(madt, 36, 0xfee00000, 4);
    put(madt, 44, 0, 1);
    put(madt, 45, 8, 1);
    put(madt, 46, 0, 1);
    put(madt, 47, 0, 1);
    put(madt, 48, 1, 4);
    put(madt, 52, 9, 1);
    put(madt, 53, 16, 1);
    put(madt, 56, 256, 4);
    put(madt, 60, 2, 4);
    put(madt, 64, 1, 4);
    put(madt, 68, 5, 1);
    put(madt, 69, 12, 1);
    put(madt, 72, 0xfec00000);
    put(madt, 80, 255, 1);
    put(madt, 81, 2, 1);
    checksum(madt);
    auto topology = Topology::parse(madt, 40);
    check(topology.has_value());
    check(topology->count() == 2 && topology->apic() == 0xfec00000);
    check(topology->processors()[0].enabled && !topology->processors()[1].enabled &&
          topology->processors()[1].online_capable);
    check(topology->processors()[1].extended && topology->processors()[1].id == 256);
    // Includes former acpi-bad-entry (first record length zero).
    for (auto at : {45U, 53U, 69U, 81U}) {
        for (auto length : {0U, 1U, 255U}) {
            invalid = madt;
            put(invalid, at, length, 1);
            checksum(invalid);
            check(!Topology::parse(invalid, 40));
        }
    }
    // Former acpi-duplicate: reject either duplicate APIC ID or duplicate UID.
    for (auto field : {56U, 64U}) {
        invalid = madt;
        put(invalid, field, 0, 4);
        checksum(invalid);
        check(!Topology::parse(invalid, 40));
    }
    invalid = madt;
    put(invalid, 54, 1, 2);
    checksum(invalid);
    check(!Topology::parse(invalid, 40));
    invalid = madt;
    put(invalid, 60, 4, 4);
    checksum(invalid);
    check(!Topology::parse(invalid, 40));
    invalid = madt;
    put(invalid, 72, 0xfec00001);
    checksum(invalid);
    check(!Topology::parse(invalid, 40));
    invalid = madt;
    put(invalid, 72, 1ULL << 40);
    checksum(invalid);
    check(!Topology::parse(invalid, 40));
    invalid = madt;
    put(invalid, 8, 7, 1);
    checksum(invalid);
    check(!Topology::parse(invalid, 40));
    invalid = madt;
    invalid.back() ^= std::byte{1};
    check(!Topology::parse(invalid, 40));
    for (std::size_t count : {128U, 129U}) {
        auto large = table("XSDT", 36 + count * 8);
        for (std::size_t i = 0; i < count; ++i)
            put(large, 36 + i * 8, 0x200000 + i * 4096);
        checksum(large);
        check(Acpi::xsdt(large, 0x100000) == (count == 128));
    }
    for (std::size_t count : {256U, 257U}) {
        auto large = table("APIC", 44 + count * 16);
        put(large, 36, 0xfee00000, 4);
        for (std::size_t i = 0; i < count; ++i) {
            const auto at = 44 + i * 16;
            put(large, at, 9, 1);
            put(large, at + 1, 16, 1);
            put(large, at + 4, i, 4);
            put(large, at + 8, 1, 4);
            put(large, at + 12, i, 4);
        }
        checksum(large);
        check(Topology::parse(large, 40).has_value() == (count == 256));
    }
    ap_worker_cases();
    std::cout << "PASS: " << checks << " ACPI root/checksum/topology/range/window-authority cases\n";
    return 0;
}
} // namespace kernel_acpi
