#include "../kernel/uefi/acpi-policy.hpp"
#include <cassert>
#include <iostream>
#include <vector>
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
    std::cout << "PASS: " << checks << " ACPI root/checksum/topology/range/window-authority cases\n";
}
