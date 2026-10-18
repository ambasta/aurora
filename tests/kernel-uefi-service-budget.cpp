#include "../kernel/uefi/service-budget-policy.hpp"
#include "../kernel/uefi/tables.hpp"
#include "../kernel/uefi/runtime-tables.hpp"
#include <algorithm>
#include <array>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <string_view>
#include <type_traits>
#include <vector>

using namespace aurora::uefi;
using aurora::user::ProgramContract;
using aurora::user::ProgramEvent;
using aurora::user::ProgramLayout;
using U64 = std::uint64_t;
using Buffer = std::vector<std::byte>;
using Words = std::array<U64, ServiceContext::word_count>;
using Admission = LocalApicAdmission;
// -no-pie keeps this real supervisor-table backing below the tested 4 GiB
// allocation limit. No host page table is installed and no MMIO is touched.
alignas(4096) static std::array<U64, Handoff::arena_bytes / sizeof(U64)> mapping_arena{};
constexpr U64 arena = 0x2000000;
constexpr U64 code = RuntimeLayout::user_code;
constexpr U64 stack = RuntimeLayout::user_stack_bottom;
constexpr U64 bottom = arena + RuntimeLayout::rsp0_bottom;
constexpr U64 top = arena + RuntimeLayout::rsp0_top;
constexpr U64 frame = top - ServiceContext::byte_count;
constexpr U64 maximum = std::numeric_limits<U64>::max();
constexpr auto cpuid_edx = (1U << 5) | (1U << 9) | (1U << 16);
constexpr auto cpuid_ebx = (7U << 24) | (1U << 16);
constexpr U64 apic_base = Admission::physical_address | 0x900;
constexpr U64 pat = 0x0007040600070406ULL;
static_assert(!std::is_default_constructible_v<Admission> && !std::is_aggregate_v<Admission>);
static_assert(!std::is_constructible_v<Admission, U64, unsigned, std::uint32_t>);
static_assert(std::is_copy_constructible_v<Admission> && !std::is_copy_assignable_v<Admission>);
static_assert(!std::is_move_assignable_v<Admission>);
static_assert(!std::is_default_constructible_v<ServiceContext> && !std::is_aggregate_v<ServiceContext>);
static_assert(!std::is_constructible_v<ServiceContext, Words, U64, ProgramContract>);
static_assert(std::is_copy_constructible_v<ServiceContext> && !std::is_copy_assignable_v<ServiceContext>);
static_assert(!std::is_move_assignable_v<ServiceContext>);
static_assert(std::is_same_v<decltype(std::declval<ServiceContext &>().words()), const Words &>);
static_assert(Admission::physical_address == 0xfee00000 && Admission::virtual_address == 0xffff900000000000ULL);
static_assert(Admission::page_size == 4096 && Admission::pat_index == 3 &&
              Admission::leaf_flags == ((1ULL << 63) | 0x1b));
static_assert(ServiceContext::byte_count == 176 && ServiceContext::word_count == 22);

unsigned checks = 0;
auto check(bool result, std::string_view message) -> void {
    ++checks;
    if (!result) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}
auto checksum(Buffer &bytes) -> void {
    bytes[9] = std::byte{0};
    unsigned sum = 0;
    for (const auto byte : bytes)
        sum += std::to_integer<unsigned>(byte);
    bytes[9] = std::byte(0U - sum);
}
auto madt() -> Buffer {
    Buffer bytes(44);
    for (std::size_t i = 0; i < 4; ++i)
        bytes[i] = std::byte(std::string_view{"APIC"}[i]);
    put(bytes, 8, 1, 1);
    put(bytes, 36, Admission::physical_address, 4);
    put(bytes, 40, 1, 4);
    return bytes;
}
auto cpu(Buffer &bytes, std::uint32_t id, std::uint32_t uid, unsigned flags, bool extended = false) -> void {
    const auto at = bytes.size();
    bytes.resize(at + (extended ? 16 : 8));
    put(bytes, at, extended ? 9 : 0, 1);
    put(bytes, at + 1, extended ? 16 : 8, 1);
    put(bytes, at + (extended ? 4 : 3), id, extended ? 4 : 1);
    put(bytes, at + (extended ? 12 : 2), uid, extended ? 4 : 1);
    put(bytes, at + (extended ? 8 : 4), flags, 4);
    put(bytes, 4, bytes.size(), 4);
    checksum(bytes);
}
auto topology(Buffer bytes, unsigned bits = 40) -> Topology {
    put(bytes, 4, bytes.size(), 4);
    checksum(bytes);
    const auto parsed = Topology::parse(bytes, bits);
    check(parsed.has_value(), "valid topology fixture");
    return *parsed;
}
auto descriptor(Buffer &bytes, std::size_t stride, std::uint32_t type, U64 begin, U64 pages, U64 attributes) -> void {
    const auto at = bytes.size();
    bytes.resize(at + stride);
    put(bytes, at, type, 4);
    put(bytes, at + 8, begin);
    put(bytes, at + 24, pages);
    put(bytes, at + 32, attributes);
}
auto memory_map(std::size_t stride = 40) -> Buffer {
    Buffer map;
    descriptor(map, stride, 1, arena, Handoff::arena_bytes / 4096, 8);
    return map;
}
auto permit(const Topology &cpus,
            std::span<const std::byte> map,
            std::size_t stride = 40,
            std::uint32_t version = 1,
            U64 owned_arena = arena,
            unsigned bits = 40,
            std::uint32_t edx = cpuid_edx,
            std::uint32_t ebx = cpuid_ebx,
            U64 base = apic_base,
            U64 cache = pat) -> std::optional<Admission> {
    return Admission::authorize(cpus, map, stride, version, owned_arena, bits, edx, ebx, base, cache);
}
auto layout() -> ProgramLayout {
    return *ProgramLayout::create(code, code + 8192, 1, stack, stack + 16384, bottom, top);
}
auto contract(ProgramLayout policy = layout(),
              U64 entry = code,
              U64 size = 128,
              U64 ret = code + 32,
              U64 bounds = code + 64,
              U64 overflow = code + 66,
              U64 division = code + 68,
              U64 shift = code + 70) -> ProgramContract {
    return ProgramContract{policy, entry, size, ret, bounds, overflow, division, shift};
}
auto words(const ProgramContract &authority = contract(), U64 vector = 64) -> Words {
    Words result{};
    for (unsigned i = 0; i < 15; ++i)
        result[i] = maximum - i;
    result[15] = vector;
    result[16] = 0;
    result[17] = authority.entry();
    result[18] = 0x1b;
    result[19] = 0x202;
    result[20] = authority.layout().user_stack_top();
    result[21] = 0x23;
    return result;
}

auto mapping_boundaries(const Topology &cpus) -> void {
    const auto actual = reinterpret_cast<U64>(mapping_arena.data());
    check(RuntimeLayout::valid(actual), "-no-pie aligned host arena satisfies dynamic owned allocation bounds");
    auto storage = std::as_writable_bytes(std::span{mapping_arena});
    auto header = storage.first(Handoff::header);
    put(header, 0, Handoff::magic);
    put(header, 8, 3, 4);
    put(header, 12, Handoff::header, 4);
    put(header, 16, Handoff::arena_bytes);
    put(header, 24, actual);
    put(header, 32, 40);
    put(header, 40, 40);
    put(header, 48, 1, 4);
    put(header, 52, 1, 4);
    put(header, 56, 8192);
    put(header, 64, 4096);
    put(header, 72, 8192);
    put(header, 80, 12288);
    put(header, 88, actual + Handoff::tables_offset);
    put(header, 96, 1);
    put(header, 104, actual + Handoff::payload_offset);
    put(header, 112, actual + 0x60000);
    put(header, 120, actual + RuntimeLayout::metadata_offset);
    check(Handoff::valid(header, actual), "complete runtime handoff for mapping boundary tests");
    Buffer final_map;
    descriptor(final_map, 40, 1, actual, Handoff::arena_bytes / 4096, 8);
    const auto granted = permit(cpus, final_map, 40, 1, actual);
    check(granted.has_value(), "capability tied to actual host arena");
    const auto foreign_grant = permit(cpus, memory_map());
    check(foreign_grant && foreign_grant->owned_arena() != actual, "independently valid foreign arena capability");
    const auto table_base = actual + Handoff::tables_offset;
    PageTables kernel{table_base};
    for (U64 offset = 0; offset < Handoff::arena_bytes; offset += 4096) {
        const auto flags = expected_flags(offset, Bytes{header});
        if (flags)
            check(kernel.map(actual + offset, flags), "map normal protected arena leaf");
    }
    check(kernel.prepare_window() && kernel.prepare_interrupts(),
          "preallocate separate empty firmware and interrupt branches");
    put(header, 96, kernel.used());
    check(kernel.used() <= Handoff::table_pages && Handoff::valid(header, actual),
          "both branches fit fixed handoff table pool");
    check(kernel.verify(actual, Bytes{header}), "empty interrupt branch grants no MMIO authority");
    check(!kernel.verify(actual, Bytes{header}, &*granted), "present capability requires its exact leaf");
    check(!kernel.verify(actual, Bytes{header}, &*foreign_grant),
          "foreign arena capability denied before MMIO mapping");
    auto *const interrupt = kernel.interrupt_slot();
    auto *const firmware = kernel.window_slot();
    check(interrupt && firmware && interrupt != firmware && *interrupt == 0 && *firmware == 0,
          "independent empty leaves");
    check(kernel.entry(Admission::virtual_address) == 0 && kernel.entry(PageTables::window_address) == 0,
          "neither reserved branch is mapped");
    const auto used = kernel.used();
    *interrupt = granted->mapping(Admission::virtual_address);
    check(kernel.used() == used && Bytes{header}.get(96) == used,
          "MMIO activation cannot change final handoff allocation count");
    check(kernel.verify(actual, Bytes{header}, &*granted),
          "exact supervisor RW NX UC leaf admitted by matching capability");
    check(!kernel.verify(actual, Bytes{header}) && !kernel.verify(actual, Bytes{header}, &*foreign_grant),
          "mapped MMIO needs exact arena capability");
    check(kernel.entry(Admission::virtual_address) == granted->mapping(Admission::virtual_address),
          "exact live APIC mapping");
    const auto expected_leaf = *interrupt;
    const auto restore_leaf = [&]() {
        *interrupt = expected_leaf;
        check(kernel.verify(actual, Bytes{header}, &*granted), "restored exact kernel MMIO leaf");
    };
    for (unsigned bit = 0; bit < 64; ++bit) {
        *interrupt = expected_leaf ^ (1ULL << bit);
        check(kernel.verify(actual, Bytes{header}, &*granted) == (bit == 5 || bit == 6),
              "kernel MMIO denies every leaf mutation except hardware accessed/dirty bits");
        restore_leaf();
    }
    for (const auto flags : std::array<U64, 8>{1,
                                               3,
                                               5,
                                               7,
                                               1 | PageTables::nx,
                                               3 | PageTables::nx,
                                               Admission::leaf_flags | 4,
                                               Admission::leaf_flags & ~PageTables::nx}) {
        *interrupt = Admission::physical_address | flags;
        check(!kernel.verify(actual, Bytes{header}, &*granted),
              "kernel rejects wrong cache, user, readonly, absent-NX and writable executable APIC leaf");
        restore_leaf();
    }
    for (std::size_t neighbor = 1; neighbor < 512; ++neighbor) {
        interrupt[neighbor] = expected_leaf;
        check(!kernel.verify(actual, Bytes{header}, &*granted), "no neighboring APIC physical alias is authorized");
        interrupt[neighbor] = 0;
    }
    *firmware = expected_leaf;
    check(!kernel.verify(actual, Bytes{header}, &*granted), "firmware window cannot alias the admitted APIC page");
    *firmware = 0;
    const auto link_at = [&](U64 va, unsigned wanted_level) -> U64 * {
        auto current = table_base;
        for (unsigned level = 3; level > wanted_level; --level) {
            const auto link = reinterpret_cast<U64 *>(current)[(va >> (12 + 9 * level)) & 511];
            current = link & RuntimeTables::address_mask;
        }
        return &reinterpret_cast<U64 *>(current)[(va >> (12 + 9 * wanted_level)) & 511];
    };
    for (unsigned level = 1; level <= 3; ++level) {
        auto *const link = link_at(Admission::virtual_address, level);
        const auto original = *link;
        for (const auto physical : std::array<U64, 5>{table_base - 4096,
                                                      table_base + used * 4096,
                                                      table_base + Handoff::table_pages * 4096,
                                                      table_base,
                                                      0xfee00000}) {
            *link = physical | 3;
            check(!kernel.verify(actual, Bytes{header}, &*granted),
                  "APIC link cannot reach foreign, unused or cyclic table backing");
            *link = original;
        }
        for (const auto bit : {1ULL, 2ULL, 4ULL, 8ULL, 16ULL, 128ULL, 256ULL, 1ULL << 52, 1ULL << 63}) {
            *link = original ^ bit;
            check(!kernel.verify(actual, Bytes{header}, &*granted),
                  "MMIO table links retain exact supervisor permissions and shape");
            *link = original;
        }
        *link = original | 0x60;
        check(kernel.verify(actual, Bytes{header}, &*granted) && kernel.interrupt_slot() == interrupt,
              "hardware accessed/dirty link changes preserve MMIO authority");
        *link = original;
    }
    auto *const root = reinterpret_cast<U64 *>(table_base);
    constexpr auto interrupt_root = (Admission::virtual_address >> 39) & 511;
    check(root[interrupt_root + 1] == 0, "unused high-half alias branch");
    root[interrupt_root + 1] = root[interrupt_root];
    check(!kernel.verify(actual, Bytes{header}, &*granted), "duplicate parent cannot alias admitted MMIO tables");
    root[interrupt_root + 1] = 0;
    *interrupt = 0;
    check(kernel.verify(actual, Bytes{header}) && !kernel.verify(actual, Bytes{header}, &*granted) &&
              kernel.entry(Admission::virtual_address) == 0 && kernel.used() == used,
          "revocation restores empty mapping without changing owned pool");

    std::array<U64, RuntimeTables::max_pages * RuntimeTables::words_per_page> runtime_storage{};
    const auto runtime_base = actual + RuntimeLayout::table_offset(0);
    RuntimeTables runtime{runtime_storage, runtime_base};
    const auto code_leaf = (actual + RuntimeLayout::image_offset) | 5;
    const auto ram_leaf = actual | 3 | RuntimeTables::nx;
    const auto expected = [&](U64 va) -> U64 {
        if (va == RuntimeLayout::user_code)
            return code_leaf;
        if (va == actual)
            return ram_leaf;
        return granted->mapping(va);
    };
    check(runtime.map(actual, actual, 3 | RuntimeTables::nx) &&
              runtime.map(RuntimeLayout::user_code, actual + RuntimeLayout::image_offset, 5) &&
              runtime.map(Admission::virtual_address, Admission::physical_address, Admission::leaf_flags),
          "runtime root maps user RX, kernel RW NX and separately authorized APIC UC");
    check(runtime.verify(expected) && runtime.entry(Admission::virtual_address) == expected_leaf,
          "runtime exact expected callback admits MMIO");
    check(!runtime.verify([&](U64 va) -> U64 {
        return va == Admission::virtual_address ? 0 : expected(va);
    }),
          "runtime callback must explicitly authorize APIC leaf");
    const auto saved = runtime_storage;
    const auto runtime_used = runtime.used();
    const auto runtime_index = [&](U64 va, unsigned wanted_level) -> std::size_t {
        std::size_t table = 0;
        for (unsigned level = 3; level > wanted_level; --level) {
            const auto link = runtime_storage[table * 512 + ((va >> (12 + 9 * level)) & 511)];
            table = static_cast<std::size_t>(((link & RuntimeTables::address_mask) - runtime_base) / 4096);
        }
        return table * 512 + ((va >> (12 + 9 * wanted_level)) & 511);
    };
    const auto mmio_at = runtime_index(Admission::virtual_address, 0);
    for (unsigned bit = 0; bit < 64; ++bit) {
        check(!runtime.map(Admission::virtual_address + 4096,
                           Admission::physical_address,
                           Admission::leaf_flags ^ (1ULL << bit)),
              "runtime map accepts only exact new UC flag combination");
        check(runtime_storage == saved && runtime.used() == runtime_used,
              "rejected UC flags cannot mutate runtime tables");
        runtime_storage[mmio_at] = expected_leaf ^ (1ULL << bit);
        check(runtime.verify(expected) == (bit == 5 || bit == 6),
              "runtime expected callback catches every MMIO leaf mutation");
        runtime_storage = saved;
    }
    for (const auto flags : std::array<U64, 7>{0x19 | RuntimeTables::nx,
                                               0x1f | RuntimeTables::nx,
                                               0x1b,
                                               0x1f,
                                               0x13 | RuntimeTables::nx,
                                               0xb | RuntimeTables::nx,
                                               0x9 | RuntimeTables::nx}) {
        check(!runtime.map(Admission::virtual_address + 4096, Admission::physical_address, flags),
              "runtime UC mapping excludes readonly, user, executable and partial cache flags");
        check(runtime_storage == saved, "bad runtime MMIO flag combination is atomic");
    }
    // RuntimeTables owns tree integrity; the full expected-address callback owns
    // leaf identity. Even structurally valid extra MMIO aliases must fail it.
    check(runtime.map(Admission::virtual_address + 4096, Admission::physical_address, Admission::leaf_flags),
          "generic runtime mapper can construct a structurally valid same-table alias");
    check(!runtime.verify(expected), "policy callback rejects neighboring physical MMIO alias");
    runtime_storage = saved;
    check(runtime.used() == runtime_used && runtime.verify(expected),
          "same-table alias removed without changing allocation count");
    for (const auto va : std::array<U64, 3>{RuntimeLayout::user_code, actual, Admission::virtual_address}) {
        const auto at = runtime_index(va, 0);
        runtime_storage[at] = expected_leaf;
        check(runtime.verify(expected) == (va == Admission::virtual_address),
              "UC permission alone cannot replace code or RAM authority");
        runtime_storage = saved;
    }
    for (unsigned level = 1; level <= 3; ++level) {
        const auto at = runtime_index(Admission::virtual_address, level);
        for (const auto physical :
             std::array<U64, 4>{runtime_base - 4096, runtime_base + runtime_used * 4096, runtime_base, table_base}) {
            runtime_storage[at] = physical | 3;
            check(!runtime.verify(expected), "runtime MMIO tree rejects foreign, unused and cyclic links");
            runtime_storage = saved;
        }
        runtime_storage[at] |= 4;
        check(!runtime.verify(expected), "supervisor MMIO branch cannot gain an unnecessary user link");
        runtime_storage = saved;
    }
    check(runtime.reset() && runtime.used() == 1 && runtime.entry(Admission::virtual_address) == 0 &&
              runtime.verify([](U64) -> U64 {
                  return 0;
              }),
          "runtime reset removes APIC mapping and scrubs owned table storage");
    check(std::all_of(runtime_storage.begin(),
                      runtime_storage.end(),
                      [](U64 value) {
                          return value == 0;
                      }),
          "no stale MMIO authority survives reset");
}

auto main() -> int {
    auto bytes = madt();
    cpu(bytes, 7, 0, 1);
    const auto cpus = topology(bytes);
    const auto map = memory_map();
    const auto grant = permit(cpus, map);
    check(grant.has_value(), "tested q35 single BSP admitted before MMIO access");
    check(grant->owned_arena() == arena && grant->physical_bits() == 40 && grant->apic_id() == 7,
          "grant captures evidence");
    check(grant->mapping(Admission::virtual_address) == (Admission::physical_address | Admission::leaf_flags),
          "exact MMIO leaf");
    check(grant->admits(Admission::virtual_address, Admission::physical_address, 4096, Admission::leaf_flags),
          "exact mapping authority");
    for (const auto va : std::array<U64, 8>{0,
                                            Admission::physical_address,
                                            Admission::virtual_address - 4096,
                                            Admission::virtual_address + 4096,
                                            Admission::virtual_address + 1,
                                            0xffff800000000000ULL,
                                            1ULL << 47,
                                            maximum})
        check(grant->mapping(va) == 0 && !grant->admits(va, Admission::physical_address, 4096, Admission::leaf_flags),
              "no VA widening");
    for (const auto pa : std::array<U64, 6>{0,
                                            Admission::physical_address - 4096,
                                            Admission::physical_address + 4096,
                                            Admission::physical_address + 1,
                                            1ULL << 52,
                                            maximum})
        check(!grant->admits(Admission::virtual_address, pa, 4096, Admission::leaf_flags), "no PA widening");
    for (const auto size : std::array<U64, 6>{0, 1, 4095, 4097, 8192, maximum})
        check(!grant->admits(Admission::virtual_address, Admission::physical_address, size, Admission::leaf_flags),
              "exact 4 KiB extent");
    for (unsigned bit = 0; bit < 64; ++bit)
        check(!grant->admits(
                  Admission::virtual_address, Admission::physical_address, 4096, Admission::leaf_flags ^ (1ULL << bit)),
              "no cache, permissions, physical or reserved leaf mutation");
    for (unsigned revision = 0; revision < 256; ++revision)
        check(grant->matches_registers(7U << 24, (5U << 16) | revision) == (revision >= 0x10 && revision <= 0x15),
              "integrated APIC revision bound");
    for (unsigned lvt = 0; lvt < 256; ++lvt)
        check(grant->matches_registers(7U << 24, (lvt << 16) | 0x14) == (lvt == 5 || lvt == 6), "supported LVT count");
    check(grant->matches_registers(7U << 24, 0x01060014), "EOI-broadcast capability bit admitted");
    for (unsigned bit = 0; bit < 32; ++bit) {
        check(!grant->matches_registers((7U << 24) ^ (1U << bit), 0x00050014), "MMIO APIC ID and reserved bits match");
        if ((0x01ff00ffU & (1U << bit)) == 0)
            check(!grant->matches_registers(7U << 24, 0x00050014 | (1U << bit)), "APIC version reserved bits");
    }
    for (const auto feature : {5U, 9U, 16U})
        check(!permit(cpus, map, 40, 1, arena, 40, cpuid_edx ^ (1U << feature)), "CPU feature missing");
    check(permit(cpus, map, 40, 1, arena, 40, ~0U).has_value(), "unrelated CPU features do not broaden grant");
    for (unsigned count = 0; count < 4; ++count)
        check(permit(cpus, map, 40, 1, arena, 40, cpuid_edx, (7U << 24) | (count << 16)).has_value() == (count <= 1),
              "CPUID processor count");
    check(!permit(cpus, map, 40, 1, arena, 40, cpuid_edx, (8U << 24) | (1U << 16)), "CPUID and MADT ID mismatch");
    for (unsigned bit = 0; bit < 64; ++bit)
        check(!permit(cpus, map, 40, 1, arena, 40, cpuid_edx, cpuid_ebx, apic_base ^ (1ULL << bit)),
              "MSR base, BSP, enable, x2APIC and reserved bits");
    for (unsigned cache = 0; cache < 256; ++cache)
        check(permit(cpus, map, 40, 1, arena, 40, cpuid_edx, cpuid_ebx, apic_base, pat | (U64{cache} << 24))
                      .has_value() == (cache == 0),
              "PAT index3 is exactly UC");
    for (unsigned bits : {0, 1, 31, 32, 40, 48, 52, 53, 63, 64, 255})
        check(permit(cpus, map, 40, 1, arena, bits).has_value() == (bits >= 32 && bits <= 52),
              "physical address width validated before shifts");

    auto disabled = bytes;
    cpu(disabled, 8, 1, 0);
    cpu(disabled, 9, 2, 2);
    cpu(disabled, 300, 3, 2, true);
    check(permit(topology(disabled), map).has_value(), "disabled and online-only processors never count as enabled");
    auto smp = bytes;
    cpu(smp, 8, 1, 1);
    check(!permit(topology(smp), map), "two enabled CPUs denied");
    auto only_disabled = madt();
    cpu(only_disabled, 7, 0, 2);
    check(!permit(topology(only_disabled), map), "online-capable BSP is not enabled");
    auto extended = madt();
    cpu(extended, 7, 0, 1, true);
    check(!permit(topology(extended), map), "enabled x2APIC topology denied");
    auto wrong_address = bytes;
    put(wrong_address, 36, 0xfec00000, 4);
    check(!permit(topology(wrong_address), map), "different MADT APIC base denied");
    auto override = bytes;
    const auto override_at = override.size();
    override.resize(override_at + 12);
    put(override, override_at, 5, 1);
    put(override, override_at + 1, 12, 1);
    put(override, override_at + 4, 0x100000000ULL);
    check(!permit(topology(override), map), "parsed 64-bit APIC override cannot enlarge tested physical contract");
    auto malformed = bytes;
    malformed.back() ^= std::byte{1};
    check(!Topology::parse(malformed, 40), "invalid checksum never creates topology");
    malformed = bytes;
    put(malformed, 48, 4, 4);
    checksum(malformed);
    check(!Topology::parse(malformed, 40), "invalid processor flags rejected");

    for (const auto version : {0U, 2U, 0xffffffffU})
        check(!permit(cpus, map, 40, version), "final map version checked");
    check(!permit(cpus, {}), "empty map denied");
    for (const auto stride : {0U, 1U, 39U, 41U, 264U})
        check(!permit(cpus, map, stride), "malformed descriptor stride");
    for (const auto stride : {40U, 48U, 256U})
        check(permit(cpus, memory_map(stride), stride).has_value(), "valid extended descriptor stride");
    check(!permit(cpus, std::span{map}.first(map.size() - 1)), "partial descriptor rejected");
    for (const auto base :
         std::array<U64, 7>{0, 0xff000, arena + 1, 0xfff01000, 0x100000000ULL, maximum - 4095, maximum})
        check(!permit(cpus, map, 40, 1, base), "unowned or malformed arena rejected");
    auto at_apic = Buffer{};
    descriptor(at_apic, 40, 1, Admission::physical_address, 256, 8);
    check(!permit(cpus, at_apic, 40, 1, Admission::physical_address), "owned arena cannot overlap APIC");
    auto before_apic = Buffer{};
    descriptor(before_apic, 40, 1, Admission::physical_address - Handoff::arena_bytes + 4096, 256, 8);
    check(!permit(cpus, before_apic, 40, 1, Admission::physical_address - Handoff::arena_bytes + 4096),
          "partial arena/APIC overlap rejected");
    for (unsigned type = 0; type <= 16; ++type) {
        auto mapped = map;
        descriptor(mapped, 40, type, Admission::physical_address, 1, 1);
        check(permit(cpus, mapped).has_value() == (type == 0 || type == 11),
              "RAM, firmware, ACPI, persistent and invalid type overlap rejected");
    }
    for (const auto flags : std::array<U64, 4>{0, 1, 0x4000, 0x4001}) {
        auto mapped = map;
        descriptor(mapped, 40, 11, Admission::physical_address, 1, flags);
        check(permit(cpus, mapped).has_value(), "explicit MMIO permits absent, UC and XP attributes");
    }
    for (unsigned bit = 0; bit < 64; ++bit) {
        auto mapped = map;
        descriptor(mapped, 40, 11, Admission::physical_address, 1, 1ULL << bit);
        check(permit(cpus, mapped).has_value() == (bit == 0 || bit == 14),
              "cache, NV, runtime, protected and unknown MMIO attributes rejected");
    }
    for (const auto type : {0U, 2U, 4U, 7U, 11U}) {
        auto unowned = map;
        put(unowned, 0, type, 4);
        check(!permit(cpus, unowned), "arena must remain loader-owned");
    }
    auto runtime = map;
    put(runtime, 32, (1ULL << 63) | 8);
    check(!permit(cpus, runtime), "runtime arena not owned");
    for (const auto start :
         std::array<U64, 4>{Admission::physical_address - 4096, Admission::physical_address + 4096, 0, 1ULL << 39}) {
        auto adjacent = map;
        descriptor(adjacent, 40, 7, start, 1, 8);
        check(permit(cpus, adjacent).has_value(), "nonoverlapping RAM remains outside APIC grant");
    }
    auto spans = map;
    descriptor(spans, 40, 7, Admission::physical_address - 4096, 3, 8);
    check(!permit(cpus, spans), "RAM descriptor covering APIC denied");
    auto duplicate = map;
    descriptor(duplicate, 40, 11, Admission::physical_address, 1, 1);
    descriptor(duplicate, 40, 0, Admission::physical_address, 1, 0);
    check(!permit(cpus, duplicate), "overlapping final descriptors rejected");
    for (const auto pages : std::array<U64, 3>{0, maximum, maximum / 4096}) {
        auto invalid = map;
        descriptor(invalid, 40, 0, Admission::physical_address, pages, 0);
        check(!permit(cpus, invalid), "zero or overflowing descriptor range");
    }
    auto unaligned = map;
    descriptor(unaligned, 40, 11, Admission::physical_address + 1, 1, 1);
    check(!permit(cpus, unaligned), "unaligned descriptor rejected");
    for (const auto bits : {32U, 40U, 52U}) {
        auto edge = map;
        descriptor(edge, 40, 0, (1ULL << bits) - 4096, 1, 0);
        check(permit(cpus, edge, 40, 1, arena, bits).has_value(), "last physical page accepted without overflow");
        put(edge, 40 + 24, 2);
        check(!permit(cpus, edge, 40, 1, arena, bits), "range beyond physical width denied");
    }
    auto mutable_map = map;
    auto mutable_topology = std::optional{cpus};
    auto copied = permit(*mutable_topology, mutable_map);
    mutable_map.clear();
    mutable_topology.reset();
    check(copied && copied->mapping(Admission::virtual_address) == grant->mapping(Admission::virtual_address),
          "grant independent of original evidence lifetime");

    const auto authority = contract();
    const auto original = words(authority);
    const auto captured = ServiceContext::capture(original, frame, authority);
    check(captured && captured->valid_for(authority) && captured->timer_frame(authority),
          "valid integer-only UEFI IRQ frame");
    check(captured->words() == original && captured->frame() == frame, "exact 22 words and frame copied");
    check(!captured->terminal_context(authority) && captured->terminal(authority) == ProgramEvent::rejected,
          "IRQ cannot become terminal authority");
    auto call_words = original;
    call_words[15] = 130;
    const auto call_pc = call_words[17];
    const auto call = ServiceContext::capture_call(call_words, frame, authority, call_pc);
    check(call && call->call_frame(authority, call_pc), "exact dedicated call capture");
    check(!ServiceContext::capture(call_words, frame, authority) && !call->valid_for(authority) &&
              !call->timer_frame(authority) && !call->terminal_context(authority),
          "call cannot become timer or terminal");
    check(!ServiceContext::capture_call(original, frame, authority, call_pc) &&
              !ServiceContext::capture_call(call_words, frame, authority, 0) &&
              !ServiceContext::capture_call(call_words, frame, authority, call_pc + 1),
          "call vector and exact site");
    for (const auto index : {16U, 18U, 20U, 21U}) {
        auto hostile = call_words;
        hostile[index] ^= 1;
        check(!ServiceContext::capture_call(hostile, frame, authority, call_pc), "call rejects malformed frame");
    }
    check(!ServiceContext::capture_call(call_words, frame + 1, authority, call_pc), "call rejects unaligned frame");
    for (unsigned index = 0; index < ServiceContext::word_count; ++index) {
        auto source = original;
        auto snapshot = ServiceContext::capture(source, frame, authority);
        source[index] ^= maximum;
        check(snapshot && snapshot->words() == original && snapshot->valid_for(authority),
              "later mutation of any source word cannot alter saved context");
        if (index < 15) {
            const auto arbitrary = ServiceContext::capture(source, frame, authority);
            check(arbitrary && arbitrary->words() == source, "all general integer register bits are preserved");
        }
    }
    for (const auto count : {0U, 1U, 15U, 21U})
        check(!ServiceContext::capture(std::span{original}.first(count), frame, authority),
              "truncated snapshot rejected");
    std::array<U64, 23> long_words{};
    std::copy(original.begin(), original.end(), long_words.begin());
    check(!ServiceContext::capture(long_words, frame, authority), "extended snapshot rejected");
    for (unsigned bit = 0; bit < 64; ++bit) {
        auto source = original;
        source[19] |= 1ULL << bit;
        check(ServiceContext::capture(source, frame, authority).has_value() ==
                  ((ServiceContext::allowed_flags & (1ULL << bit)) != 0),
              "complete RFLAGS whitelist including IOPL0");
        source = original;
        source[16] = 1ULL << bit;
        check(!ServiceContext::capture(source, frame, authority), "all error-code bits rejected");
    }
    for (const auto required : {2ULL, 0x200ULL}) {
        auto source = original;
        source[19] &= ~required;
        check(!ServiceContext::capture(source, frame, authority), "architectural bit1 and original IF1 required");
    }
    for (const auto vector : std::array<U64, 9>{0, 8, 13, 14, 32, 63, 65, 128, maximum}) {
        auto source = original;
        source[15] = vector;
        check(!ServiceContext::capture(source, frame, authority),
              "only budget IRQ and compiled terminal vectors admitted");
    }
    for (const auto selector : std::array<U64, 7>{0, 8, 0x18, 0x19, 0x1a, 0x1001b, maximum}) {
        auto source = original;
        source[18] = selector;
        check(!ServiceContext::capture(source, frame, authority), "exact ring3 CS");
    }
    for (const auto selector : std::array<U64, 7>{0, 0x10, 0x20, 0x21, 0x22, 0x10023, maximum}) {
        auto source = original;
        source[21] = selector;
        check(!ServiceContext::capture(source, frame, authority), "exact ring3 SS");
    }
    for (U64 offset = 0; offset < authority.size(); ++offset) {
        auto source = original;
        source[17] = code + offset;
        check(ServiceContext::capture(source, frame, authority).has_value(),
              "IRQ PC inclusive first through last image byte");
    }
    for (const auto pc : std::array<U64, 7>{0, code - 1, code + 128, code + 4096, 0x1b0000, 1ULL << 47, maximum}) {
        auto source = original;
        source[17] = pc;
        check(!ServiceContext::capture(source, frame, authority), "IRQ PC cannot leave exact image");
    }
    for (U64 sp = stack; sp <= stack + 16384; sp += 8) {
        auto source = original;
        source[20] = sp;
        check(ServiceContext::capture(source, frame, authority).has_value(), "all aligned user-stack endpoints");
    }
    for (const auto sp : std::array<U64, 7>{0, stack - 8, stack + 1, stack + 16385, stack + 16392, 0x1e4000, maximum}) {
        auto source = original;
        source[20] = sp;
        check(!ServiceContext::capture(source, frame, authority), "BIOS, overflow, alignment and user-stack bounds");
    }
    for (U64 location = bottom; location <= frame; location += 8)
        check(ServiceContext::capture(original, location, authority).has_value(),
              "full RSP0 frame interval inclusive endpoints");
    for (const auto location : std::array<U64, 10>{
             0, bottom - 8, bottom + 1, frame + 1, frame + 8, top, top + 8, 0x85f50, maximum - 175, maximum})
        check(!ServiceContext::capture(original, location, authority),
              "full frame cannot reach guard, wrap, misalign or use BIOS constants");
    const auto high_top = maximum - 4095;
    const auto high_layout =
        ProgramLayout::create(code, code + 8192, 1, stack, stack + 16384, high_top - 16384, high_top);
    check(high_layout.has_value(), "canonical high RSP0 fixture");
    const auto high_contract = contract(*high_layout);
    check(ServiceContext::capture(original, high_top - 176, high_contract).has_value(),
          "full high-half frame uses subtraction bounds");
    check(!ServiceContext::capture(original, maximum - 175, high_contract),
          "near-maximum frame cannot overflow into valid interval");

    for (const auto &other :
         std::array{contract(layout(), code, 127),
                    contract(layout(), code, 128, code + 34),
                    contract(layout(), code, 128, code + 32, code + 62),
                    contract(layout(), code, 128, code + 32, code + 64, code + 72),
                    contract(layout(), code, 128, code + 32, code + 64, code + 66, 0),
                    contract(layout(), code, 128, code + 32, code + 64, code + 66, code + 68, 0),
                    contract(*ProgramLayout::create(code - 4096, code + 8192, 1, stack, stack + 16384, bottom, top)),
                    contract(*ProgramLayout::create(code, code + 12288, 1, stack, stack + 16384, bottom, top)),
                    contract(*ProgramLayout::create(code, code + 8192, 2, stack, stack + 16384, bottom, top)),
                    contract(*ProgramLayout::create(code, code + 8192, 1, stack + 4096, stack + 16384, bottom, top)),
                    contract(*ProgramLayout::create(code, code + 8192, 1, stack, stack + 12288, bottom, top)),
                    contract(*ProgramLayout::create(code, code + 8192, 1, stack, stack + 16384, bottom + 4096, top)),
                    contract(*ProgramLayout::create(code, code + 8192, 1, stack, stack + 16384, bottom, top - 4096))}) {
        check(other.valid(), "altered contract fixture remains independently valid");
        check(!captured->valid_for(other) && !captured->timer_frame(other) && !captured->terminal_context(other),
              "captured contract authority cannot be substituted");
    }
    for (const auto &invalid : std::array{contract(layout(), code, 0),
                                          contract(layout(), code, maximum),
                                          contract(layout(), maximum),
                                          contract(layout(), code, 128, maximum),
                                          ProgramContract{code, 128, code + 32, code + 64, code + 66}})
        check(!ServiceContext::capture(original, frame, invalid) && !captured->valid_for(invalid),
              "invalid or BIOS-default metadata rejected");
    auto mutable_contract = std::optional{authority};
    auto source = original;
    const auto stable = ServiceContext::capture(source, frame, *mutable_contract);
    mutable_contract.reset();
    mutable_contract.emplace(contract(layout(), code, 127));
    source.fill(0);
    check(stable && stable->valid_for(authority) && stable->words() == original &&
              !stable->valid_for(*mutable_contract),
          "snapshot owns complete immutable contract");

    for (const auto pair : std::array<std::array<U64, 2>, 5>{{{129, 32}, {6, 64}, {6, 66}, {6, 68}, {6, 70}}}) {
        auto terminal = original;
        terminal[15] = pair[0];
        terminal[17] = code + pair[1];
        const auto snapshot = ServiceContext::capture(terminal, frame, authority);
        const auto expected = pair[0] == 129  ? ProgramEvent::returned
                              : pair[1] == 64 ? ProgramEvent::bounds
                              : pair[1] == 66 ? ProgramEvent::overflow
                              : pair[1] == 68 ? ProgramEvent::division_zero
                                              : ProgramEvent::shift_count;
        check(snapshot && snapshot->terminal(authority) == expected &&
                  snapshot->terminal_context(authority).has_value(),
              "exact compiled terminal site after validated IF normalization");
        check(!snapshot->timer_frame(authority) && snapshot->words()[19] == 0x202,
              "terminal normalization never changes saved flags");
        terminal[19] |= 1ULL << 10;
        const auto direction = ServiceContext::capture(terminal, frame, authority);
        check(direction && direction->terminal(authority) == ProgramEvent::rejected,
              "terminal DF stays rejected after only IF normalization");
        terminal[19] = ServiceContext::allowed_flags & ~(1ULL << 10);
        const auto arithmetic = ServiceContext::capture(terminal, frame, authority);
        check(arithmetic && arithmetic->terminal(authority) == expected,
              "arithmetic and RF bits survive terminal validation");
        terminal[19] &= ~0x200ULL;
        check(!ServiceContext::capture(terminal, frame, authority), "IF-clear terminal not laundered by normalization");
    }
    auto direction = original;
    direction[19] = ServiceContext::allowed_flags;
    const auto saved_direction = ServiceContext::capture(direction, frame, authority);
    check(saved_direction && saved_direction->timer_frame(authority) && saved_direction->words() == direction,
          "IRQ resumes exact arithmetic, DF and RF state");
    auto wrong_site = words(authority, 129);
    wrong_site[17] = code + 34;
    const auto nonterminal = ServiceContext::capture(wrong_site, frame, authority);
    check(nonterminal && nonterminal->terminal(authority) == ProgramEvent::rejected,
          "origin validation does not invent a return site");
    wrong_site[17] = authority.return_pc();
    wrong_site[20] -= 8;
    const auto wrong_stack = ServiceContext::capture(wrong_site, frame, authority);
    check(wrong_stack && wrong_stack->terminal(authority) == ProgramEvent::rejected,
          "scalar return still requires exact stack top");
    const auto domain1_layout = ProgramLayout::create(code + 16384,
                                                      code + 28672,
                                                      1,
                                                      RuntimeLayout::user_stack_begin(1),
                                                      RuntimeLayout::user_stack_end(1),
                                                      bottom,
                                                      top);
    const auto domain1 = contract(*domain1_layout,
                                  code + 16384,
                                  128,
                                  code + 16384 + 32,
                                  code + 16384 + 64,
                                  code + 16384 + 66,
                                  code + 16384 + 68,
                                  code + 16384 + 70);
    check(ServiceContext::capture(words(domain1), frame, domain1).has_value(), "second dynamic UEFI domain accepted");
    check(!ServiceContext::capture(original, frame, domain1) && !captured->valid_for(domain1),
          "foreign domain context denied");
    // Captured PCs are bounded by exact bytes, even when a copied layout permits
    // three pages. Include instruction sites in the second and third pages.
    const auto large_layout = ProgramLayout::create(code, code + 12288, 3, stack, stack + 16384, bottom, top);
    check(large_layout.has_value(), "bounded three-page context fixture");
    for (const U64 size : {4096ULL, 4097ULL, 8192ULL, 8193ULL, 12288ULL}) {
        const auto image = contract(*large_layout, code, size);
        check(image.valid(), "one through three-page contract valid");
        for (const U64 offset : {0ULL, 4095ULL, 4096ULL, 8191ULL, 8192ULL, 12287ULL, 12288ULL, 16384ULL}) {
            auto source = words(image);
            source[17] = code + offset;
            check(ServiceContext::capture(source, frame, image).has_value() == (offset < size),
                  "IRQ PC excludes padding, guard and neighbor image slot");
        }
        auto source = words(image, 129);
        const auto terminal_image = contract(*large_layout, code, size, code + size - 2);
        source[17] = code + size - 2;
        const auto terminal = ServiceContext::capture(source, frame, terminal_image);
        check(terminal && terminal->terminal(terminal_image) == ProgramEvent::returned,
              "exact return PC may occupy final image page");
    }
    check(!contract(*large_layout, code, 12289).valid(), "fourth-page extent rejected");
    mapping_boundaries(cpus);
    std::cout << "PASS: " << checks
              << " UEFI service-budget APIC admission, immutable integer context and adversarial authority checks\n";
}
