#include "user-program.hpp"
#include <array>
namespace aurora::user {
namespace {
#include "kernel-user-images.hpp"
constinit std::size_t selected = 0;
} // namespace
auto UserPrograms::install() -> bool {
    static_assert(bank.size() * 4096 <= code_end - code_begin && !sets.empty());
    for (const auto &set : sets)
        for (const auto image : set.images)
            if (image >= bank.size())
                return false;
    for (std::size_t index = 0; index < bank.size(); ++index) {
        const auto &image = bank[index];
        if (!image.valid() || image.contract().entry() != code_begin + index * 4096)
            return false;
    }
    for (const auto &image : bank) {
        for (auto byte = std::uint64_t{0}; byte < 4096; ++byte) {
            const auto value = byte < image.bytes().size() ? std::to_integer<std::uint8_t>(image.bytes()[byte]) : 0;
            *reinterpret_cast<volatile std::uint8_t *>(image.contract().entry() + byte) = value;
        }
    }
    for (const auto &image : bank) {
        for (auto byte = std::uint64_t{0}; byte < 4096; ++byte) {
            const auto expected = byte < image.bytes().size() ? std::to_integer<std::uint8_t>(image.bytes()[byte]) : 0;
            if (*reinterpret_cast<volatile const std::uint8_t *>(image.contract().entry() + byte) != expected)
                return false;
        }
    }
    selected = 0;
    return true;
}
auto UserPrograms::select(unsigned selector) -> void {
    for (std::size_t index = 0; index < sets.size(); ++index)
        if (sets[index].selector == selector)
            selected = index;
}
auto UserPrograms::contract(std::size_t index) -> const ProgramContract * {
    return index < sets[selected].images.size() ? &bank[sets[selected].images[index]].contract() : nullptr;
}
auto UserPrograms::probe() -> std::array<std::uint64_t, 2> {
    return {sets[selected].probe_begin, sets[selected].probe_end};
}
} // namespace aurora::user
