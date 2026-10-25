// Handoff layouts as data. Built twice: with AURORA_UEFI_GRAPHICAL_TERMINAL (the
// production composition's 136-byte v7 header, where word 120 is the runtime
// metadata and word 128 the framebuffer record) and without it (the 128-byte
// header of every other image, which must keep rejecting v7 and keep each older
// version exactly as strict).
#include "../kernel/uefi/tables.hpp"
#include <array>
#include <cstdlib>
#include <iostream>

namespace kernel_uefi_handoff {
namespace {
using namespace aurora::uefi;
using U64 = std::uint64_t;
unsigned checks{};
auto need(bool value) -> void {
    ++checks;
    if (!value)
        std::abort();
}
constexpr U64 arena = 0x1000000;
class Field final {
public:
    std::size_t offset;
    unsigned width;
    U64 value;
};
// One complete header of the given version; every field is valid for it.
auto header(unsigned version) -> std::array<std::byte, Handoff::header> {
    std::array<std::byte, Handoff::header> h{};
    const std::array<Field, 17> fields{{
        {0, 8, Handoff::magic},
        {8, 4, version},
        {12, 4, Handoff::header},
        {16, 8, Handoff::arena_bytes},
        {24, 8, arena},
        {32, 8, 4800},
        {40, 8, 48},
        {48, 4, 1},
        {52, 4, 1},
        {56, 8, 8192},
        {64, 8, 4096},
        {72, 8, 8192},
        {80, 8, 12288},
        {88, 8, arena + Handoff::tables_offset},
        {96, 8, 9},
        {104, 8, arena + Handoff::payload_offset},
        {112, 8, version == 1 || version == 5 ? U64{0} : U64{0xf5e10}},
    }};
    for (const auto &field : fields)
        put(h, field.offset, field.value, field.width);
    const auto record = arena + Handoff::framebuffer_record_offset;
    if (version == 3 || version == 7)
        put(h, 120, arena + RuntimeLayout::metadata_offset);
    else if (version == 4)
        put(h, 120, arena + Handoff::bar_record_offset);
    else if (version == 5 || version == 6)
        put(h, 120, record);
#ifdef AURORA_UEFI_GRAPHICAL_TERMINAL
    if (version == 7)
        put(h, Handoff::framebuffer_word, record);
#endif
    return h;
}
auto valid(const std::array<std::byte, Handoff::header> &h) -> bool {
    return Handoff::valid(h, arena);
}
} // namespace
int main() {
#ifdef AURORA_UEFI_GRAPHICAL_TERMINAL
    static_assert(Handoff::header == 136 && Handoff::framebuffer_word == 128);
    constexpr unsigned admitted = 7;
#else
    static_assert(Handoff::header == 128);
    constexpr unsigned admitted = 0;
#endif
    // Each version is admitted exactly where its layout exists.
    for (unsigned version = 0; version <= 9; ++version) {
#ifdef AURORA_UEFI_GRAPHICAL_TERMINAL
        need(valid(header(version)) == (version == admitted));
#else
        need(valid(header(version)) == (version >= 1 && version <= 6));
#endif
    }
#ifndef AURORA_UEFI_GRAPHICAL_TERMINAL
    // A v7 header with the v6 or v3 word-120 meaning still rejects here.
    for (const U64 word : {arena + RuntimeLayout::metadata_offset, arena + Handoff::framebuffer_record_offset}) {
        auto h = header(7);
        put(h, 112, 0xf5e10);
        put(h, 120, word);
        need(!valid(h));
    }
    for (unsigned version = 1; version <= 6; ++version) {
        const auto good = header(version);
        need(valid(good));
        // Word 120 has one meaning per version; any other value denies.
        for (const U64 word : {U64{0},
                               arena + RuntimeLayout::metadata_offset,
                               arena + Handoff::bar_record_offset,
                               arena + Handoff::framebuffer_record_offset,
                               arena + Handoff::framebuffer_record_offset + 4096}) {
            auto h = good;
            put(h, 120, word);
            need(valid(h) == (word == Bytes{good}.get(120)));
        }
        auto h = good;
        put(h, 112, Bytes{good}.get(112) ? 0 : 1);
        need(!valid(h));
    }
    need(!PageTables::paired_records(Bytes{header(3)}, arena) && PageTables::paired_records(Bytes{header(6)}, arena));
    need(!expected_flags(Handoff::framebuffer_record_offset, Bytes{header(3)}));
#else
    const auto good = header(7);
    need(valid(good) && Handoff::runtime(Bytes{good}) && Handoff::framebuffer(Bytes{good}));
    // Every word keeps its meaning and bound; each invalid value denies.
    const std::array<Field, 32> invalid{{
        {0, 8, 0},
        {8, 4, 3},
        {8, 4, 6},
        {12, 4, 128},
        {16, 8, Handoff::arena_bytes - 4096},
        {24, 8, arena + 4096},
        {32, 8, 0},
        {32, 8, MemoryMap::max_bytes + 1},
        {40, 8, 39},
        {40, 8, 257},
        {48, 4, 2},
        {52, 4, 0},
        {52, 4, 4},
        {56, 8, 0},
        {56, 8, 12289},
        {64, 8, 0},
        {64, 8, 4097},
        {64, 8, 16384},
        {72, 8, 4096 + 1},
        {80, 8, Handoff::payload_limit + 4096},
        {88, 8, arena},
        {96, 8, 0},
        {96, 8, Handoff::table_pages + 1},
        {104, 8, arena + Handoff::payload_offset + 4096},
        {112, 8, 0},
        {120, 8, 0},
        {120, 8, arena + Handoff::framebuffer_record_offset},
        {120, 8, arena + RuntimeLayout::metadata_offset + 4096},
        {128, 8, 0},
        {128, 8, arena + RuntimeLayout::metadata_offset},
        {128, 8, arena + Handoff::framebuffer_record_offset + 4096},
        {128, 8, arena + Handoff::bar_record_offset},
    }};
    for (const auto &field : invalid) {
        auto h = good;
        put(h, field.offset, field.value, field.width);
        need(!valid(h));
    }
    // Words 120 and 128 never swap or share meanings.
    const std::array<std::array<U64, 2>, 6> words{{
        {arena + Handoff::framebuffer_record_offset, arena + RuntimeLayout::metadata_offset},
        {arena + Handoff::framebuffer_record_offset, arena + Handoff::framebuffer_record_offset},
        {arena + RuntimeLayout::metadata_offset, arena + RuntimeLayout::metadata_offset},
        {arena + RuntimeLayout::metadata_offset, 0},
        {0, arena + Handoff::framebuffer_record_offset},
        {arena + RuntimeLayout::metadata_offset, arena + Handoff::bar_record_offset},
    }};
    for (const auto &[runtime, record] : words) {
        auto h = good;
        put(h, 120, runtime);
        put(h, 128, record);
        need(!valid(h) && !PageTables::paired_records(Bytes{h}, arena));
    }
    auto absent = good;
    put(absent, 112, 0);
    need(!valid(absent));
    need(!Handoff::valid(std::span<const std::byte>{good}.first(128), arena));
    need(PageTables::paired_records(Bytes{good}, arena) && !PageTables::paired_records(Bytes{good}, arena + 4096));
    // v7 maps the runtime pages and the read-only record page; v6-only meaning absent.
    need(expected_flags(Handoff::framebuffer_record_offset, Bytes{good}) == (1 | PageTables::nx));
    need(expected_flags(RuntimeLayout::metadata_offset, Bytes{good}) == (1 | PageTables::nx));
    need(expected_flags(RuntimeLayout::gdt_offset, Bytes{good}) == (3 | PageTables::nx));
    need(expected_flags(Handoff::bar_record_offset, Bytes{good}) ==
         RuntimeLayout::kernel_flags(Handoff::bar_record_offset));
#endif
    std::cout << "PASS: handoff layout " << (admitted ? "v7 terminal" : "v1-v6") << ' ' << checks << " checks\n";
    return 0;
}
} // namespace kernel_uefi_handoff
