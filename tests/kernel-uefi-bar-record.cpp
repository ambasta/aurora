#include "../kernel/uefi/bar-record.hpp"
#include <array>
#include <cstdlib>
#include <iostream>
using namespace aurora::uefi;
using U64 = std::uint64_t;
using Header = std::array<std::byte, 64>;
using Record = std::array<std::byte, 4096>;
using Descriptor = std::array<std::byte, 48>;
unsigned checks{};
auto check(bool good) -> void {
    ++checks;
    if (!good) {
        std::cerr << "bar record failure " << checks << '\n';
        std::abort();
    }
}
auto write(std::span<std::byte> bytes, unsigned at, U64 value, unsigned width = 8) -> void {
    for (unsigned n = 0; n < width; ++n)
        bytes[at + n] = std::byte((value >> (n * 8)) & 255);
}
auto descriptor(U64 base, U64 length, bool wide, bool prefetch = false) -> Descriptor {
    Descriptor d{};
    write(d, 0, 0x2b8a, 3);
    write(d, 5, prefetch ? 6 : 0, 1);
    write(d, 6, wide ? 64 : 32);
    write(d, 14, base);
    write(d, 22, length - 1);
    write(d, 38, length);
    write(d, 46, 0x79, 2);
    return d;
}
auto config(U64 base, unsigned slot, bool wide, bool target = false, bool prefetch = false) -> Header {
    Header h{};
    write(h, 0, target ? 0x00101b36 : 0x11111234, 4);
    write(h, 4, 2, 2);
    write(h, 9, target ? 0x010802 : 0x030000, 3);
    write(h, 16 + slot * 4, (base & 0xfffffff0) | (wide ? 4 : 0) | (prefetch ? 8 : 0), 4);
    if (wide)
        write(h, 20 + slot * 4, base >> 32, 4);
    return h;
}
auto function(unsigned device, const Header &h) -> PciFunction {
    PciFunction f{};
    const Bytes b{h};
    f.device = device;
    f.vendor = b.get(0, 2);
    f.device_id = b.get(2, 2);
    f.command = b.get(4, 2);
    f.class_code = b.get(11, 1);
    f.subclass = b.get(10, 1);
    f.programming_interface = b.get(9, 1);
    return f;
}
auto row(Record &record, unsigned index, unsigned device, unsigned slot, const Header &header, const Descriptor &data)
    -> void {
    auto out = std::span<std::byte>{record}.subspan(2048 + index * 256, 256);
    write(out, 16, device);
    write(out, 32, slot);
    write(out, 40, 48);
    for (unsigned n = 0; n < 64; ++n)
        out[64 + n] = header[n];
    for (unsigned n = 0; n < 48; ++n)
        out[128 + n] = data[n];
}
auto main() -> int {
    constexpr U64 target_base = 0xc000000000ULL;
    const auto target_wire = descriptor(target_base, 0x4000, true);
    const auto parsed = PciResources::parse_edk2_bar(target_wire, 40);
    check(parsed.has_value());
    const auto &target = parsed->resources()[0];
    std::array<Header, 3> headers{
        config(0x80000000, 0, false, false, true), config(target_base, 0, true, true), config(0x81000000, 5, false)};
    std::array<PciFunction, 3> functions{function(1, headers[0]), function(2, headers[1]), function(3, headers[2])};
    Record original{};
    write(original, 0, 0x3152414241525541ULL);
    write(original, 8, 1, 4);
    write(original, 12, 4096, 4);
    write(original, 32, 2);
    write(original, 56, 48);
    write(original, 64, 48);
    write(original, 72, 64);
    write(original, 88, 2);
    row(original, 0, 1, 0, headers[0], descriptor(0x80000000, 0x1000000, false, true));
    row(original, 1, 3, 5, headers[2], descriptor(0x81000000, 0x2000, false));
    const auto validate = [&](const Record &record, const auto &items, const auto &values) {
        return BarRecord{record}.reservations(items, target, 40, [&](const PciFunction &f) -> std::optional<Header> {
            for (unsigned n = 0; n < 3; ++n)
                if (f.device == functions[n].device && f.bus == 0 && f.function == 0 && f.segment == 0)
                    return values[n];
            return std::nullopt;
        });
    };
    check(validate(original, functions, headers) == 2);
    for (unsigned at : {0U, 8U, 12U, 16U, 24U, 32U, 40U, 48U, 56U, 64U, 72U, 88U}) {
        auto bad = original;
        write(bad, at, at == 88 ? 9 : at == 64 ? 47 : 0xffff);
        check(!validate(bad, functions, headers));
    }
    for (unsigned size = 0; size < 4096; size += 127)
        check(!BarRecord{std::span<const std::byte>{original}.first(size)}.valid());
    for (unsigned count : {0U, 1U, 3U, 8U, 9U}) {
        auto bad = original;
        write(bad, 88, count);
        check(!validate(bad, functions, headers));
    }
    auto duplicate = original;
    for (unsigned n = 0; n < 256; ++n)
        duplicate[2304 + n] = duplicate[2048 + n];
    check(!validate(duplicate, functions, headers));
    auto extra = original;
    row(extra, 2, 31, 0, headers[0], descriptor(0x80000000, 0x1000000, false, true));
    write(extra, 88, 3);
    check(!validate(extra, functions, headers));
    for (unsigned candidate = 0; candidate < 2; ++candidate) {
        for (unsigned field : {0U, 8U, 16U, 24U, 32U, 40U}) {
            auto bad = original;
            write(bad, 2048 + candidate * 256 + field, 255);
            check(!validate(bad, functions, headers));
        }
        for (unsigned byte = 0; byte < 64; ++byte)
            for (unsigned bit = 0; bit < 8; ++bit) {
                auto bad = original;
                bad[2048 + candidate * 256 + 64 + byte] ^= std::byte(1U << bit);
                check(!validate(bad, functions, headers));
            }
    }
    auto items = functions;
    items[0].vendor ^= 1;
    check(!validate(original, items, headers));
    items = functions;
    items[0].command ^= 1;
    check(!validate(original, items, headers));
    items = functions;
    items[1] = items[0];
    check(!validate(original, items, headers));
    auto changed_headers = headers;
    changed_headers[0] = config(target_base, 0, true);
    auto overlap = original;
    row(overlap, 0, 1, 0, changed_headers[0], descriptor(target_base, 0x1000, true));
    const auto snapshot = PciBarSnapshot::parse(0, 0, 1, 0, changed_headers[0]);
    check(snapshot.has_value());
    const auto valid_overlap =
        PciBarReservation::parse_edk2(*snapshot, *snapshot, 0, descriptor(target_base, 0x1000, true), 40);
    check(valid_overlap && valid_overlap->overlaps(target.begin(), target.length()));
    check(!validate(overlap, functions, changed_headers));
    for (U64 base : {target_base - 0x1000, target_base + 0x4000}) {
        changed_headers = headers;
        changed_headers[0] = config(base, 0, true);
        auto adjacent = original;
        row(adjacent, 0, 1, 0, changed_headers[0], descriptor(base, 0x1000, true));
        check(validate(adjacent, functions, changed_headers) == 2);
    }
    check(!BarRecord{original}.reservations(
        std::span<const PciFunction>{}, target, 40, [](const PciFunction &) -> std::optional<Header> {
            return std::nullopt;
        }));
    check(!BarRecord{original}.reservations(functions, target, 40, [](const PciFunction &) -> std::optional<Header> {
        return std::nullopt;
    }));
    check(validate(original, functions, headers) == 2);
    std::cout << "PASS: " << checks
              << " BAR handoff identity, complete reservations, missing/duplicate/extra/conflict and snapshot mutation "
                 "checks\n";
}
