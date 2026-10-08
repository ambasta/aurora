#include "../kernel/uefi/framebuffer-loader.hpp"
#include <cstdlib>
#include <iostream>
#include <type_traits>

namespace {
using namespace aurora::uefi;
using U64 = std::uint64_t;
alignas(8) std::array<std::byte, 376> boot{};
alignas(8) std::array<std::byte, 32> protocol{};
alignas(8) std::array<std::byte, 40> mode{};
alignas(8) std::array<std::byte, 36> info{};
unsigned checks{}, queries{}, frees{}, sets{};
bool set_failure{}, query_failure{}, locate_failure{}, fixture{};
unsigned fixture_mode = 3, fixture_format = 1;
auto need(bool value) -> void {
    ++checks;
    if (!value)
        std::abort();
}
U64 __attribute__((ms_abi)) locate(const void *guid, void *registration, void **result) {
    need(registration == nullptr && Bytes{{static_cast<const std::byte *>(guid), 16}}.get(0) == 0x4a3823dc9042a9deULL);
    if (locate_failure)
        return 1;
    *result = protocol.data();
    return 0;
}
U64 __attribute__((ms_abi)) query(void *self, std::uint32_t number, U64 *size, void **result) {
    need(self == protocol.data() && number < Bytes{mode}.get(0, 4));
    ++queries;
    if (query_failure)
        return 1;
    if (fixture) {
        const auto width = number < fixture_mode ? 1280U : 800U;
        put(info, 4, width, 4);
        put(info, 8, 600, 4);
        put(info, 32, width, 4);
        put(info, 12, fixture_format, 4);
    }
    *size = info.size();
    *result = info.data();
    return 0;
}
U64 __attribute__((ms_abi)) set(void *self, std::uint32_t number) {
    need(self == protocol.data());
    ++sets;
    if (set_failure)
        return 1;
    put(mode, 4, number, 4);
    return 0;
}
U64 __attribute__((ms_abi)) free_pool(void *allocation) {
    need(allocation == info.data());
    ++frees;
    return 0;
}
auto reset() -> void {
    boot.fill(std::byte{0});
    protocol.fill(std::byte{0});
    mode.fill(std::byte{0});
    info.fill(std::byte{0});
    queries = frees = sets = 0;
    set_failure = query_failure = locate_failure = fixture = false;
    fixture_mode = 3;
    fixture_format = 1;
    put(boot, 320, reinterpret_cast<U64>(&locate));
    put(boot, 72, reinterpret_cast<U64>(&free_pool));
    put(protocol, 0, reinterpret_cast<U64>(&query));
    put(protocol, 8, reinterpret_cast<U64>(&set));
    put(protocol, 24, reinterpret_cast<U64>(mode.data()));
    put(mode, 0, 2, 4);
    put(mode, 4, 1, 4);
    put(mode, 8, reinterpret_cast<U64>(info.data()));
    put(mode, 16, 36);
    put(mode, 24, 0xc0000000);
    put(mode, 32, 0x200000);
    put(info, 4, 800, 4);
    put(info, 8, 600, 4);
    put(info, 32, 800, 4);
}
auto fixture_reset() -> void {
    reset();
    fixture = true;
    put(mode, 0, 30, 4);
    put(mode, 24, 0x80000000);
    put(mode, 32, 1921024);
}
} // namespace
int main() {
    static_assert(!std::is_constructible_v<FramebufferResource, FramebufferDescription>);
    static_assert(!std::is_default_constructible_v<FramebufferResource>);
    reset();
    const auto capture = FramebufferLoader::capture(Bytes{boot}, 36);
    need(capture && capture->mode() == 0 && capture->mode_count() == 2);
    need(queries == 1 && frees == 1 && sets == 1);
    std::array<std::byte, 64> record{};
    need(FramebufferRecord::write(record, capture->description()));
    const auto description = FramebufferRecord::parse(record, 36);
    need(description && description->geometry().width() == 800);
    std::array<std::byte, 40> map{};
    put(map, 0, 1, 4);
    put(map, 8, 0x1000000);
    put(map, 24, 256);
    need(!FramebufferAdmission::authorize_described(
        capture->geometry(), map, 40, 1, 0x1000000, 36, (1U << 5) | (1U << 16), 0x0007040600070406ULL));
    // Proposed platform rule is tested independently, not enabled in a guest.
    need(!FramebufferAdmission::authorize_q35_ovmf_std_vga_fixture(
              *capture, map, 40, 1, 0x1000000, 36, (1U << 5) | (1U << 16), 0x0007040600070406ULL)
              .has_value());
    for (unsigned format : {2U, 3U, UINT32_MAX}) {
        reset();
        put(info, 12, format, 4);
        need(!FramebufferLoader::capture(Bytes{boot}, 36));
        need(queries == 2 && frees == 2 && sets == 0);
    }
    for (unsigned count : {0U, 65U, UINT32_MAX}) {
        reset();
        put(mode, 0, count, 4);
        need(!FramebufferLoader::capture(Bytes{boot}, 36));
        need(queries == 0 && frees == 0 && sets == 0);
    }
    reset();
    set_failure = true;
    need(!FramebufferLoader::capture(Bytes{boot}, 36));
    need(queries == frees);
    reset();
    query_failure = true;
    need(!FramebufferLoader::capture(Bytes{boot}, 36));
    need(sets == 0);
    reset();
    locate_failure = true;
    need(!FramebufferLoader::capture(Bytes{boot}, 36));
    need(queries == 0);
    reset();
    put(mode, 24, 0xc0000001);
    need(!FramebufferLoader::capture(Bytes{boot}, 36));
    need(queries == frees);
    fixture_reset();
    const auto measured = FramebufferLoader::capture(Bytes{boot}, 40);
    need(measured && measured->mode() == 3 && measured->mode_count() == 30);
    const auto qualify = [&](const FramebufferResource &value,
                             std::span<const std::byte> final_map,
                             unsigned bits = 40,
                             U64 pat = 0x0007040600070406ULL) {
        return FramebufferAdmission::authorize_q35_ovmf_std_vga_fixture(
            value, final_map, 40, 1, 0x1000000, bits, (1U << 5) | (1U << 16), pat);
    };
    need(qualify(*measured, map).has_value());
    need(!qualify(*measured, map, 39));
    need(!qualify(*measured, map, 41));
    need(!qualify(*measured, map, 40, 1ULL << 24));
    std::array<std::byte, 80> conflicting{};
    for (unsigned at = 0; at < 40; ++at)
        conflicting[at] = map[at];
    put(conflicting, 48, 0x80000000);
    put(conflicting, 64, 1);
    for (unsigned kind = 0; kind <= 15; ++kind) {
        put(conflicting, 40, kind, 4);
        need(qualify(*measured, conflicting).has_value() == (kind == 0 || kind == 11));
    }
    put(conflicting, 40, 11, 4);
    put(conflicting, 72, 1ULL << 63);
    need(!qualify(*measured, conflicting));
    for (U64 changed_base : {U64{0x80001000}, U64{0xfec00000}, U64{0xfee00000}, U64{0xe0000000}}) {
        fixture_reset();
        put(mode, 24, changed_base);
        const auto changed = FramebufferLoader::capture(Bytes{boot}, 40);
        need(changed.has_value());
        need(!qualify(*changed, map));
    }
    fixture_reset();
    fixture_mode = 4;
    const auto changed_mode = FramebufferLoader::capture(Bytes{boot}, 40);
    need(changed_mode.has_value());
    need(!qualify(*changed_mode, map));
    fixture_reset();
    put(mode, 0, 31, 4);
    const auto changed_count = FramebufferLoader::capture(Bytes{boot}, 40);
    need(changed_count.has_value());
    need(!qualify(*changed_count, map));
    fixture_reset();
    fixture_format = 0;
    const auto changed_format = FramebufferLoader::capture(Bytes{boot}, 40);
    need(changed_format.has_value());
    need(!qualify(*changed_format, map));
    fixture_reset();
    put(mode, 32, 1925120);
    const auto changed_size = FramebufferLoader::capture(Bytes{boot}, 40);
    need(changed_size.has_value());
    need(!qualify(*changed_size, map));
    std::cout << "PASS: framebuffer pre-exit GOP capture " << checks << " checks\n";
}
