#include "../kernel/uefi/event-profile-policy.hpp"
#include "../kernel/uefi/ivrs-policy.hpp"
#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <source_location>
#include <type_traits>
#include <vector>

using namespace aurora::uefi;
using Buffer = std::vector<std::byte>;
unsigned checks = 0;
auto check(bool value, const std::source_location location = std::source_location::current()) -> void {
    ++checks;
    if (!value) {
        std::cerr << "FAIL at line " << location.line() << ", check " << checks << '\n';
        std::abort();
    }
}
auto repair(Buffer &bytes) -> void {
    put(bytes, 4, bytes.size(), 4);
    bytes[9] = std::byte{};
    unsigned sum = 0;
    for (auto byte : bytes)
        sum += std::to_integer<unsigned>(byte);
    bytes[9] = std::byte(0U - sum);
}

// Independent producer-derived wire fixture, not a guest capture. Its six
// SELECT entries are the pinned minimal Q35 topology with the automatically
// allocated IOMMU in the first free slot. Changing the chosen unit below tests
// derivation from matching copied/live facts rather than a fixed 00:03.0 rule.
auto table(unsigned iommu = 8) -> Buffer {
    Buffer bytes(176);
    for (unsigned i = 0; i < 4; ++i)
        bytes[i] = std::byte("IVRS"[i]);
    put(bytes, 8, 1, 1);
    put(bytes, 36, 0x2801, 4);
    std::array<unsigned, 6> ids{0, iommu, 0x20, 0xf8, 0xfa, 0xfb};
    std::sort(ids.begin(), ids.end());
    for (unsigned record = 0; record < 2; ++record) {
        const unsigned at = record == 0 ? 48 : 104, header = record == 0 ? 24 : 40;
        put(bytes, at, record == 0 ? 0x10 : 0x11, 1);
        put(bytes, at + 1, record == 0 ? 0xd1 : 0x11, 1);
        put(bytes, at + 2, header + 32, 2);
        put(bytes, at + 4, iommu, 2);
        put(bytes, at + 6, 0x40, 2);
        put(bytes, at + 8, 0xfed80000);
        put(bytes, at + 20, record == 0 ? 0x44 : 0, 4);
        if (record != 0)
            put(bytes, at + 24, 0x29d3);
        for (unsigned i = 0; i < ids.size(); ++i) {
            put(bytes, at + header + i * 4, 2, 1);
            put(bytes, at + header + i * 4 + 1, ids[i], 2);
        }
        // Literal source bytes, independent of policy's 64-bit comparison.
        const std::array<unsigned, 8> special{0x48, 0, 0, 0, 0, 0xa0, 0, 1};
        for (unsigned i = 0; i < special.size(); ++i)
            bytes[at + header + 24 + i] = std::byte(special[i]);
    }
    repair(bytes);
    return bytes;
}
auto pci(unsigned requester, unsigned id, unsigned class_revision, unsigned command) -> EventPciFact {
    EventPciFact fact;
    fact.device = static_cast<std::uint8_t>(requester >> 3);
    fact.function = static_cast<std::uint8_t>(requester & 7);
    put(fact.header, 0, id, 4);
    put(fact.header, 4, command, 2);
    put(fact.header, 8, class_revision, 4);
    return fact;
}
auto inventory(unsigned iommu = 8) -> std::array<EventPciFact, 6> {
    std::array<EventPciFact, 6> facts{pci(0, 0x29c08086, 0x06000000, 0),
                                      pci(iommu, 0x14191022, 0x08060000, 7),
                                      pci(0x20, 0x11e81234, 0x00ff0010, 2),
                                      pci(0xf8, 0x29188086, 0x06010002, 3),
                                      pci(0xfa, 0x29228086, 0x01060102, 3),
                                      pci(0xfb, 0x29308086, 0x0c050002, 1)};
    put(facts[1].header, 6, 0x10, 2);
    put(facts[1].header, 0x34, 0x60, 1);
    put(facts[2].header, 16, 0xc0000000, 4);
    put(facts[3].header, 14, 0x80, 1);
    put(facts[4].header, 32, 0x6041, 4);
    put(facts[4].header, 36, 0xc1000000, 4);
    put(facts[5].header, 32, 0x6001, 4);
    return facts;
}
auto capabilities() -> Buffer {
    Buffer caps(48);
    const std::array<unsigned, 12> words{
        0x1f03000f, 0xfed80000, 0, 0xff000000, 0x00182840, 0, 0x00004005, 0x00005808, 0x00805c05, 0, 0, 0};
    for (unsigned i = 0; i < words.size(); ++i)
        put(caps, i * 4, words[i], 4);
    return caps;
}
auto bar(unsigned requester, unsigned slot, std::uint64_t base, std::uint64_t length) -> EventBarFact {
    EventBarFact fact;
    fact.requester = static_cast<std::uint16_t>(requester);
    fact.index = slot;
    put(fact.descriptor, 0, 0x8a, 1);
    put(fact.descriptor, 1, 43, 2);
    put(fact.descriptor, 6, 32);
    put(fact.descriptor, 14, base);
    put(fact.descriptor, 22, length - 1);
    put(fact.descriptor, 38, length);
    put(fact.descriptor, 46, 0x79, 2);
    return fact;
}
auto root_bytes(std::uint64_t begin = 0xc0000000, std::uint64_t length = 0x20000000) -> Buffer {
    Buffer bytes(94);
    put(bytes, 0, 0x8a, 1);
    put(bytes, 1, 43, 2);
    put(bytes, 6, 32);
    put(bytes, 14, begin);
    put(bytes, 22, begin + length - 1);
    put(bytes, 38, length);
    put(bytes, 46, 0x8a, 1);
    put(bytes, 47, 43, 2);
    put(bytes, 49, 2, 1);
    put(bytes, 68, 255);
    put(bytes, 84, 256);
    put(bytes, 92, 0x79, 2);
    return bytes;
}
auto memory(unsigned type = 1, std::uint64_t base = 0x400000, std::uint64_t pages = 256, std::uint64_t flags = 0)
    -> Buffer {
    Buffer bytes(40);
    put(bytes, 0, type, 4);
    put(bytes, 8, base);
    put(bytes, 24, pages);
    put(bytes, 32, flags);
    return bytes;
}
auto ahci() -> EventAhciFacts {
    EventAhciFacts result;
    result.base = 0xc1000000;
    result.capability = 0xc0141f05;
    result.global_control = 0x80000000;
    result.implemented_ports = 0x3f;
    return result;
}

auto parser_controls() -> void {
    static_assert(!std::is_default_constructible_v<EventIvrs>);
    const auto bytes = table();
    const auto parsed = EventIvrs::parse_qemu_default(bytes, 40);
    check(parsed && parsed->unit().device_id() == 8 && parsed->unit().base() == 0xfed80000);
    check(parsed->covers(0, 0, 4, 0) && !parsed->covers(0, 0, 20, 0));
    check(!parsed->covers(1, 0, 4, 0) && !parsed->covers(0, 1, 4, 0) && !parsed->covers(0, 0, 32, 0) &&
          !parsed->covers(0, 0, 4, 8));
    for (unsigned bits : {0U, 31U, 53U, 64U, ~0U})
        check(!EventIvrs::parse_qemu_default(bytes, bits));
    for (unsigned bits : {32U, 40U, 52U})
        check(EventIvrs::parse_qemu_default(bytes, bits).has_value());
    for (unsigned unit : {8U, 16U, 24U, 40U, 240U})
        check(EventIvrs::parse_qemu_default(table(unit), 40).has_value());
    for (unsigned unit : {0U, 9U, 32U, 160U, 248U, 256U})
        check(!EventIvrs::parse_qemu_default(table(unit), 40));
    for (std::size_t size = 0; size < bytes.size(); ++size)
        check(!EventIvrs::parse_qemu_default(std::span{bytes}.first(size), 40));
    auto longer = bytes;
    longer.push_back(std::byte{});
    repair(longer);
    check(!EventIvrs::parse_qemu_default(longer, 40));
    // Every bit of both exact special entries must be preserved. This includes
    // type, reserved/setting bytes, handle, synthetic requester and variety.
    for (unsigned start : {96U, 168U})
        for (unsigned offset = 0; offset < 8; ++offset) {
            for (unsigned bit = 0; bit < 8; ++bit) {
                auto changed = bytes;
                changed[start + offset] ^= std::byte(1U << bit);
                repair(changed);
                check(!EventIvrs::parse_qemu_default(changed, 40));
            }
        }
    for (unsigned offset : {8U,   36U,  40U,  48U,  49U,  50U,  54U,  56U,  64U,  66U, 68U,
                            104U, 105U, 106U, 108U, 110U, 112U, 120U, 124U, 128U, 136U}) {
        auto changed = bytes;
        changed[offset] ^= std::byte{1};
        repair(changed);
        check(!EventIvrs::parse_qemu_default(changed, 40));
    }
    for (unsigned start : {72U, 144U})
        for (unsigned entry = 0; entry < 6; ++entry) {
            for (unsigned type : {0U, 1U, 3U, 4U, 0x42U, 0x43U, 0x46U, 0x48U, 0xffU}) {
                auto changed = bytes;
                changed[start + entry * 4] = std::byte(type);
                repair(changed);
                check(!EventIvrs::parse_qemu_default(changed, 40));
            }
            auto changed = bytes;
            changed[start + entry * 4 + 3] = std::byte{1};
            repair(changed);
            check(!EventIvrs::parse_qemu_default(changed, 40));
            if (entry) {
                changed = bytes;
                put(changed, start + entry * 4 + 1, Bytes{bytes}.get(start + 1, 2), 2);
                repair(changed);
                check(!EventIvrs::parse_qemu_default(changed, 40));
            }
        }
    auto corrupt = bytes;
    corrupt[9] ^= std::byte{1};
    check(!EventIvrs::parse_qemu_default(corrupt, 40));
    // Historical SELECT-only parser remains closed against the default special
    // entry; a separately generated old-profile shape remains accepted there.
    check(!Ivrs::parse_qemu_10_0_13(bytes, 40));
    auto old = bytes;
    old.erase(old.begin() + 168, old.begin() + 176);
    old.erase(old.begin() + 96, old.begin() + 104);
    put(old, 50, 48, 2);
    put(old, 98, 64, 2);
    repair(old);
    check(Ivrs::parse_qemu_10_0_13(old, 40).has_value());
    check(!EventIvrs::parse_qemu_default(old, 40));
}

auto resource_controls() -> void {
    static_assert(!std::is_default_constructible_v<EventResources>);
    static_assert(!std::is_default_constructible_v<EventAdmission>);
    static_assert(!std::is_convertible_v<EventResources, EventAdmission>);
    const auto ivrs = EventIvrs::parse_qemu_default(table(), 40);
    const auto facts = inventory();
    const auto caps = capabilities();
    const std::array<EventBarFact, 2> bars{bar(0x20, 0, 0xc0000000, 0x100000), bar(0xfa, 5, 0xc1000000, 0x1000)};
    const auto root = PciResources::parse_edk2_root(root_bytes(), 40);
    check(ivrs && root);
    const auto admit = [&](std::span<const EventPciFact> copied,
                           std::span<const EventPciFact> current,
                           std::span<const EventBarFact> resources,
                           const Buffer &map,
                           const Buffer &copied_caps,
                           const Buffer &current_caps,
                           std::uint64_t arena = 0x400000,
                           std::uint64_t apic = 0xfee00000) {
        return EventResources::admit_qemu_default(
            *ivrs, copied, current, copied_caps, current_caps, resources, *root, 0, map, 40, arena, apic);
    };
    const auto good = admit(facts, facts, bars, memory(), caps, caps);
    check(good && good->edu_base() == 0xc0000000 && good->ahci_base() == 0xc1000000 &&
          good->edu_initial_command() == 2 && good->iommu_device_id() == 8);
    // A BME-bearing description can authorize only bounded read-only observation.
    // Even a fully cold observation cannot become EventAdmission.
    for (unsigned i = 0; i < facts.size(); ++i) {
        auto inherited = facts;
        put(inherited[i].header, 4, Bytes{inherited[i].header}.get(4, 2) | 4, 2);
        const auto observation = EventResources::admit_qemu_default(*ivrs,
                                                                    inherited,
                                                                    inherited,
                                                                    caps,
                                                                    caps,
                                                                    bars,
                                                                    *root,
                                                                    0,
                                                                    memory(),
                                                                    40,
                                                                    0x400000,
                                                                    0xfee00000,
                                                                    EventResources::Purpose::read_only_observation);
        check(observation.has_value() == (i != 2)); // EDU must remain cold.
        if (observation)
            check(!EventAdmission::admit(*observation, ahci()));
    }
    const auto cold_observation = EventResources::admit_qemu_default(*ivrs,
                                                                     facts,
                                                                     facts,
                                                                     caps,
                                                                     caps,
                                                                     bars,
                                                                     *root,
                                                                     0,
                                                                     memory(),
                                                                     40,
                                                                     0x400000,
                                                                     0xfee00000,
                                                                     EventResources::Purpose::read_only_observation);
    check(cold_observation && !EventAdmission::admit(*cold_observation, ahci()));
    const auto admission = EventAdmission::admit(*good, ahci());
    check(admission && admission->edu_base() == 0xc0000000 && admission->iommu_base() == 0xfed80000 &&
          admission->edu_config_address() == 0xe0020000 && admission->physical_bits() == 40);
    // Complete inventory equality includes every byte, not just selected IDs.
    for (unsigned i = 0; i < facts.size(); ++i)
        for (unsigned offset = 0; offset < 64; ++offset) {
            auto changed = facts;
            changed[i].header[offset] ^= std::byte{1};
            check(!admit(changed, facts, bars, memory(), caps, caps));
            check(!admit(facts, changed, bars, memory(), caps, caps));
        }
    auto reordered = facts;
    std::reverse(reordered.begin(), reordered.end());
    check(admit(reordered, facts, bars, memory(), caps, caps).has_value());
    check(admit(facts, reordered, bars, memory(), caps, caps).has_value());
    check(!admit(std::span{facts}.first(5), facts, bars, memory(), caps, caps));
    check(!admit(facts, std::span{facts}.first(5), bars, memory(), caps, caps));
    for (unsigned i = 0; i < facts.size(); ++i) {
        auto changed = facts;
        changed[i] = facts[(i + 1) % facts.size()];
        check(!admit(changed, changed, bars, memory(), caps, caps));
        changed = facts;
        changed[i].segment = 1;
        check(!admit(changed, changed, bars, memory(), caps, caps));
        changed = facts;
        changed[i].bus = 1;
        check(!admit(changed, changed, bars, memory(), caps, caps));
        changed = facts;
        put(changed[i].header, 4, Bytes{changed[i].header}.get(4, 2) ^ 4, 2);
        check(!admit(changed, changed, bars, memory(), caps, caps));
        for (unsigned offset : {0U, 2U, 8U, 9U, 10U, 11U, 14U, 48U}) {
            changed = facts;
            changed[i].header[offset] ^= std::byte{1};
            check(!admit(changed, changed, bars, memory(), caps, caps));
        }
    }
    for (unsigned command : {0U, 1U, 3U, 4U, 6U, 7U, 0x400U, 0xffffU}) {
        auto changed = facts;
        put(changed[2].header, 4, command, 2);
        check(!admit(changed, changed, bars, memory(), caps, caps));
    }
    for (unsigned unit : {16U, 24U, 40U}) {
        const auto dynamic = EventIvrs::parse_qemu_default(table(unit), 40);
        const auto dynamic_facts = inventory(unit);
        const auto result = EventResources::admit_qemu_default(
            *dynamic, dynamic_facts, dynamic_facts, caps, caps, bars, *root, 0, memory(), 40, 0x400000, 0xfee00000);
        check(result && result->iommu_device_id() == unit);
        check(!EventResources::admit_qemu_default(
            *dynamic, facts, facts, caps, caps, bars, *root, 0, memory(), 40, 0x400000, 0xfee00000));
    }
    for (unsigned offset = 0; offset < caps.size(); ++offset)
        for (unsigned bit = 0; bit < 8; ++bit) {
            auto changed = caps;
            changed[offset] ^= std::byte(1U << bit);
            check(!admit(facts, facts, bars, memory(), changed, caps));
            check(!admit(facts, facts, bars, memory(), caps, changed));
            check(!admit(facts, facts, bars, memory(), changed, changed));
        }
    for (unsigned length = 0; length < 48; ++length) {
        auto short_caps = caps;
        short_caps.resize(length);
        check(!admit(facts, facts, bars, memory(), short_caps, short_caps));
    }
    auto long_caps = caps;
    long_caps.push_back(std::byte{});
    check(!admit(facts, facts, bars, memory(), long_caps, long_caps));
    for (unsigned i = 0; i < bars.size(); ++i)
        for (unsigned offset = 0; offset < 48; ++offset) {
            auto changed = bars;
            changed[i].descriptor[offset] ^= std::byte{1};
            check(!admit(facts, facts, changed, memory(), caps, caps));
        }
    check(!admit(facts, facts, {}, memory(), caps, caps));
    check(!admit(facts, facts, std::span{bars}.first(1), memory(), caps, caps));
    auto changed_bars = bars;
    changed_bars[1] = changed_bars[0];
    check(!admit(facts, facts, changed_bars, memory(), caps, caps));
    changed_bars = bars;
    changed_bars[1].index = 4;
    check(!admit(facts, facts, changed_bars, memory(), caps, caps));
    // Correlated malicious descriptor/config changes still fail ownership,
    // exact geometry, known-slot and full-aperture conflict checks.
    for (std::uint64_t address : {0xc0001000ULL, 0xe0000000ULL, 0xfed00000ULL, 0x400000ULL, 0ULL}) {
        auto changed = facts;
        put(changed[2].header, 16, address, 4);
        changed_bars = bars;
        changed_bars[0] = bar(0x20, 0, address, 0x100000);
        check(!admit(changed, changed, changed_bars, memory(), caps, caps));
    }
    auto changed = facts;
    put(changed[4].header, 36, 0xc0000000, 4);
    changed_bars = bars;
    changed_bars[1] = bar(0xfa, 5, 0xc0000000, 0x1000);
    check(!admit(changed, changed, changed_bars, memory(), caps, caps));
    for (unsigned low : {1U, 2U, 4U, 8U}) {
        changed = facts;
        put(changed[2].header, 16, 0xc0000000U | low, 4);
        check(!admit(changed, changed, bars, memory(), caps, caps));
    }
    for (auto base : {0xc0000000ULL, 0xc00ff000ULL, 0xc1000000ULL, 0xfed80000ULL, 0xfed83000ULL}) {
        for (unsigned type = 0; type < 15; ++type)
            check(admit(facts, facts, bars, memory(type, base, 1), caps, caps).has_value() ==
                  (type == 0 || type == 11));
        for (unsigned bit = 0; bit < 64; ++bit)
            check(admit(facts, facts, bars, memory(11, base, 1, 1ULL << bit), caps, caps).has_value() ==
                  (bit == 0 || bit == 14 || bit == 17));
    }
    for (auto arena : {0ULL, 1ULL, 0xc0000000ULL, 0xc1000000ULL, 0xfed80000ULL, ~0ULL})
        check(!admit(facts, facts, bars, memory(), caps, caps, arena));
    for (auto apic : {0ULL, 1ULL, 0xc0000000ULL, 0xc1000000ULL, 0xfed80000ULL, ~0ULL})
        check(!admit(facts, facts, bars, memory(), caps, caps, 0x400000, apic));
    check(!admit(facts, facts, bars, memory(1, 0x400001, 1), caps, caps));
    check(!admit(facts, facts, bars, memory(1, (1ULL << 40) - 4096, 2), caps, caps));
    const auto narrow_root = PciResources::parse_edk2_root(root_bytes(0xc0000000, 0x100000), 40);
    check(narrow_root.has_value());
    check(!EventResources::admit_qemu_default(
        *ivrs, facts, facts, caps, caps, bars, *narrow_root, 0, memory(), 40, 0x400000, 0xfee00000));
    check(!EventResources::admit_qemu_default(
        *ivrs, facts, facts, caps, caps, bars, *root, 1, memory(), 40, 0x400000, 0xfee00000));
    for (unsigned port = 0; port < 6; ++port) {
        for (unsigned bit : {0U, 4U, 14U, 15U}) {
            auto busy = ahci();
            busy.ports[port].command |= 1U << bit;
            check(!EventAdmission::admit(*good, busy));
        }
        for (unsigned bit = 0; bit < 32; ++bit) {
            auto busy = ahci();
            busy.ports[port].command_issue = 1U << bit;
            check(!EventAdmission::admit(*good, busy));
            busy = ahci();
            busy.ports[port].sata_active = 1U << bit;
            check(!EventAdmission::admit(*good, busy));
        }
    }
    for (unsigned bit = 0; bit < 32; ++bit) {
        auto wrong = ahci();
        wrong.capability ^= 1U << bit;
        check(!EventAdmission::admit(*good, wrong));
        wrong = ahci();
        wrong.global_control ^= 1U << bit;
        check(!EventAdmission::admit(*good, wrong));
        wrong = ahci();
        wrong.implemented_ports ^= 1U << bit;
        check(!EventAdmission::admit(*good, wrong));
    }
    auto wrong = ahci();
    wrong.base += 4096;
    check(!EventAdmission::admit(*good, wrong));
    check(!EventAdmission::admit(*good, {}));
}

auto observation_controls() -> void {
    std::vector<unsigned> offsets;
    const auto read = [&](unsigned at) {
        offsets.push_back(at);
        return at + 1;
    };
    const auto first = EventAhciFacts::sample<true>(0xc1000000, read);
    std::vector<unsigned> expected{0, 4, 12};
    for (unsigned port = 0; port < 6; ++port) {
        const auto at = 0x100 + port * 0x80;
        for (unsigned offset : {0x18U, 0x34U, 0x38U, 0x20U, 0U, 4U, 8U, 12U})
            expected.push_back(at + offset);
        const auto &fact = first.ports[port];
        check(fact.command == at + 0x19 && fact.command_issue == at + 0x39 && fact.sata_active == at + 0x35 &&
              fact.task_file == at + 0x21);
        check(fact.command_list == (std::uint64_t{at + 5} << 32 | (at + 1)) &&
              fact.received_fis == (std::uint64_t{at + 13} << 32 | (at + 9)));
        for (unsigned field = 0; field < 6; ++field) {
            auto changed = first;
            auto &entry = changed.ports[port];
            if (field == 0)
                ++entry.command;
            if (field == 1)
                ++entry.command_issue;
            if (field == 2)
                ++entry.sata_active;
            if (field == 3)
                ++entry.task_file;
            if (field == 4)
                ++entry.command_list;
            if (field == 5)
                ++entry.received_fis;
            check(first != changed);
        }
    }
    check(offsets == expected);
    offsets.clear();
    check(first == EventAhciFacts::sample<true>(0xc1000000, read));
    check(offsets == expected);
    offsets.clear();
    const auto basic = EventAhciFacts::sample<false>(0xc1000000, read);
    check(offsets.size() == 21 && basic.ports[0].task_file == 0 && basic.ports[0].command_list == 0);
    check(first != basic);
}

auto main() -> int {
    observation_controls();
    parser_controls();
    resource_controls();
    std::cout << "UEFI Event profile: " << checks << " checks passed\n";
}
