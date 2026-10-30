// Handoff layouts as data. Built twice: with AURORA_UEFI_GRAPHICAL_TERMINAL (the
// production composition's 184-byte v10 header, where word 120 is the runtime
// metadata, word 128 the framebuffer record and words 136/144 the boot volume) and without it (the 128-byte
// header of every other image, which must keep rejecting v7 and keep each older
// version exactly as strict).
#include "../kernel/uefi/tables.hpp"
#include "../kernel/uefi/fw-cfg-fixture.hpp"
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
    if (version == 3 || version == Handoff::terminal_version)
        put(h, 120, arena + RuntimeLayout::metadata_offset);
    else if (version == 4)
        put(h, 120, arena + Handoff::bar_record_offset);
    else if (version == 5 || version == 6)
        put(h, 120, record);
#ifdef AURORA_UEFI_GRAPHICAL_TERMINAL
    if (version == Handoff::terminal_version)
        put(h, Handoff::framebuffer_word, record);
#endif
#ifdef AURORA_PRODUCTION
    if (version == Handoff::terminal_version) {
        put(h, Handoff::composition_word, 1);
        put(h, Handoff::volume_word, 0x20000000);
        put(h, Handoff::volume_bytes_word, 8192);
    }
#endif
    return h;
}
auto valid(const std::array<std::byte, Handoff::header> &h) -> bool {
    return Handoff::valid(h, arena);
}
} // namespace
int main() {
#ifdef AURORA_UEFI_GRAPHICAL_TERMINAL
#ifdef AURORA_PRODUCTION
    static_assert(Handoff::header == 184 && Handoff::volume_word == 136 && Handoff::volume_bytes_word == 144);
#else
    static_assert(Handoff::header == 136);
#endif
    static_assert(Handoff::framebuffer_word == 128);
    constexpr unsigned admitted = Handoff::terminal_version;
#else
    static_assert(Handoff::header == 128);
    constexpr unsigned admitted = 0;
#endif
    // Each version is admitted exactly where its layout exists.
    for (unsigned version = 0; version <= 11; ++version) {
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
    const auto good = header(admitted);
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
#ifdef AURORA_PRODUCTION
    for (const Field field : {Field{136, 8, 0},
                              Field{136, 8, 0x20000001},
                              Field{136, 8, (1ULL << 52) - Handoff::volume_limit},
                              Field{144, 8, 0},
                              Field{144, 8, Handoff::volume_limit + 1},
                              Field{12, 4, 136},
                              Field{8, 4, 7},
                              Field{8, 4, 9},
                              Field{12, 4, 152},
                              Field{152, 8, 1},
                              Field{160, 8, arena + Handoff::bar_record_offset},
                              Field{168, 8, 1},
                              Field{176, 8, 0},
                              Field{176, 8, 2},
                              Field{176, 8, 3},
                              Field{176, 8, 4}}) {
        auto h = good;
        put(h, field.offset, field.value, field.width);
        need(!valid(h));
    }
#endif
#if defined(AURORA_PRODUCTION) && defined(AURORA_UEFI_NVME)
    // One production image: only the closed tag4 composition gains the separate
    // RO/NX capture page. Runtime metadata at 0x81000 remains untouched.
    auto storage = good;
    put(storage, Handoff::composition_word, 4);
    put(storage, Handoff::bar_record_word, arena + Handoff::production_bar_record_offset);
    need(valid(storage) && Handoff::runtime(Bytes{storage}) && Handoff::framebuffer(Bytes{storage}) &&
         Handoff::bar(Bytes{storage}));
    need(Handoff::bar_offset(Bytes{storage}) == Handoff::production_bar_record_offset);
    need(expected_flags(Handoff::production_bar_record_offset, Bytes{storage}) == (1 | PageTables::nx));
    need(expected_flags(RuntimeLayout::metadata_offset, Bytes{storage}) == (1 | PageTables::nx));
    need(!expected_flags(Handoff::production_bar_record_offset, Bytes{good}) && !Handoff::bar(Bytes{good}));
    BootStorageSelection boot;
    need(!boot.claim_recovery());
    need(!boot.select(false, 2) && !boot.select(true, 4));
    need(boot.select(true, 2) && boot.block() && boot.readonly_profile() == 1 && boot.claim_recovery());
    // Reattachment and owner loss do not replenish the boot-global claim.
    need(boot.select(true, 2) && !boot.claim_recovery());
    need(!boot.select(true, 1) && !boot.select(false, 0));
    need(boot.select(true, 2) && !boot.claim_recovery());
    for (unsigned mode = 0; mode < 2; ++mode) {
        BootStorageSelection readonly;
        need(readonly.select(true, mode) && readonly.block() && readonly.readonly_profile() == mode &&
             !readonly.claim_recovery());
        need(readonly.select(true, mode) && !readonly.select(true, 2) && !readonly.claim_recovery());
    }
    BootStorageSelection mounted;
    need(!mounted.claim_mounted() && !mounted.select(false, 3));
    need(mounted.select(true, 3) && mounted.mounted() && mounted.readonly_profile() == 1 && !mounted.claim_recovery() &&
         mounted.claim_mounted());
    need(mounted.select(true, 3) && !mounted.claim_mounted() && !mounted.claim_recovery());
    need(!mounted.select(true, 2) && !mounted.select(false, 0) && !mounted.claim_mounted());
    BootStorageSelection ram;
    need(ram.select(false, 0) && !ram.block() && ram.readonly_profile() == 0 && !ram.select(true, 0) &&
         !ram.claim_recovery());
    auto clean_storage = storage;
    put(clean_storage, Handoff::readonly_profile_word, 1);
    need(valid(clean_storage));
    auto recovery_storage = storage;
    put(recovery_storage, Handoff::readonly_profile_word, 2);
    need(valid(recovery_storage));
    auto mounted_storage = storage;
    put(mounted_storage, Handoff::readonly_profile_word, 3);
    need(valid(mounted_storage));
    for (const Field field : {Field{152, 8, 4}, Field{152, 8, UINT64_MAX}, Field{176, 8, 1}, Field{160, 8, 0}}) {
        auto bad = clean_storage;
        put(bad, field.offset, field.value, field.width);
        need(!valid(bad));
    }
    for (const Field field : {Field{160, 8, 0},
                              Field{160, 8, arena + Handoff::bar_record_offset},
                              Field{160, 8, arena + Handoff::framebuffer_record_offset},
                              Field{160, 8, arena + Handoff::production_bar_record_offset + 4096},
                              Field{152, 8, 10},
                              Field{168, 8, 252},
                              Field{176, 8, 1},
                              Field{176, 8, 3},
                              Field{120, 8, arena + Handoff::production_bar_record_offset}}) {
        auto bad = storage;
        put(bad, field.offset, field.value, field.width);
        need(!valid(bad));
    }
    auto false_bar = good;
    put(false_bar, Handoff::bar_record_word, arena + Handoff::production_bar_record_offset);
    need(!valid(false_bar) && !Handoff::bar(Bytes{false_bar}) &&
         !expected_flags(Handoff::production_bar_record_offset, Bytes{false_bar}));
    constexpr std::array choice{std::byte{'n'}, std::byte{'v'}, std::byte{'m'}, std::byte{'e'}};
    constexpr std::array terminated{std::byte{'n'}, std::byte{'v'}, std::byte{'m'}, std::byte{'e'}, std::byte{0}};
    need(!fw_cfg::FwCfg::storage_word(terminated));
    need(fw_cfg::FwCfg::storage_word(choice) == fw_cfg::Storage::nvme);
    for (std::size_t size = 0; size < choice.size(); ++size)
        need(!fw_cfg::FwCfg::storage_word(std::span{choice}.first(size)));
    for (std::size_t at = 0; at < choice.size(); ++at) {
        auto bad = choice;
        bad[at] ^= std::byte{1};
        need(!fw_cfg::FwCfg::storage_word(bad));
    }
    constexpr char clean_choice[] = "nvme-linux-6.12-clean";
    const auto clean_bytes = std::as_bytes(std::span{clean_choice});
    need(fw_cfg::FwCfg::storage_word(clean_bytes.first(21)) == fw_cfg::Storage::nvme_linux_6_12_clean);
    need(!fw_cfg::FwCfg::storage_word(clean_bytes));
    for (std::size_t size = 0; size < 21; ++size)
        need(fw_cfg::FwCfg::storage_word(clean_bytes.first(size)) ==
             (size == 4 ? std::optional{fw_cfg::Storage::nvme} : std::nullopt));
    for (std::size_t at = 0; at < 21; ++at) {
        std::array<std::byte, 21> bad{};
        for (std::size_t i = 0; i < bad.size(); ++i)
            bad[i] = clean_bytes[i];
        bad[at] ^= std::byte{1};
        need(!fw_cfg::FwCfg::storage_word(bad));
        bad[at] = std::byte{0};
        need(!fw_cfg::FwCfg::storage_word(bad));
    }
    constexpr char mounted_choice[] = "nvme-linux-6.12-write";
    const auto mounted_bytes = std::as_bytes(std::span{mounted_choice});
    need(fw_cfg::FwCfg::storage_word(mounted_bytes.first(21)) == fw_cfg::Storage::nvme_linux_6_12_write);
    need(!fw_cfg::FwCfg::storage_word(mounted_bytes));
    for (std::size_t at = 0; at < 21; ++at) {
        std::array<std::byte, 21> bad{};
        for (std::size_t i = 0; i < bad.size(); ++i)
            bad[i] = mounted_bytes[i];
        bad[at] ^= std::byte{1};
        need(!fw_cfg::FwCfg::storage_word(bad));
    }
    constexpr char recovery_choice[] = "nvme-linux-6.12-recover";
    const auto recovery_bytes = std::as_bytes(std::span{recovery_choice});
    need(fw_cfg::FwCfg::storage_word(recovery_bytes.first(23)) == fw_cfg::Storage::nvme_linux_6_12_recover);
    need(!fw_cfg::FwCfg::storage_word(recovery_bytes));
    for (std::size_t size = 0; size < 23; ++size)
        need(fw_cfg::FwCfg::storage_word(recovery_bytes.first(size)) ==
             (size == 4 ? std::optional{fw_cfg::Storage::nvme} : std::nullopt));
    for (std::size_t at = 0; at < 23; ++at) {
        std::array<std::byte, 23> bad{};
        for (std::size_t i = 0; i < bad.size(); ++i)
            bad[i] = recovery_bytes[i];
        bad[at] ^= std::byte{1};
        need(!fw_cfg::FwCfg::storage_word(bad));
        bad[at] = std::byte{0};
        need(!fw_cfg::FwCfg::storage_word(bad));
    }

#endif
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
    std::cout << "PASS: handoff layout " << (admitted ? "terminal" : "v1-v6") << ' ' << checks << " checks\n";
    return 0;
}
} // namespace kernel_uefi_handoff
