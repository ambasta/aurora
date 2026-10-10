#include "user-program.hpp"
#include <array>
namespace aurora::user {
namespace {
#include "kernel-user-images.hpp"
}
auto UserPrograms::install() -> bool {
    for (std::size_t index = 0; index < images.size(); ++index) {
        const auto &image = images[index];
        if (!image.valid() || image.contract().entry() != code_begin + index * 4096)
            return false;
    }
    for (const auto &image : images) {
        for (auto byte = std::uint64_t{0}; byte < 4096; ++byte) {
            const auto value = byte < image.bytes().size() ? std::to_integer<std::uint8_t>(image.bytes()[byte]) : 0;
            *reinterpret_cast<volatile std::uint8_t *>(image.contract().entry() + byte) = value;
        }
    }
    for (const auto &image : images) {
        for (auto byte = std::uint64_t{0}; byte < 4096; ++byte) {
            const auto expected = byte < image.bytes().size() ? std::to_integer<std::uint8_t>(image.bytes()[byte]) : 0;
            if (*reinterpret_cast<volatile const std::uint8_t *>(image.contract().entry() + byte) != expected)
                return false;
        }
    }
    return true;
}
auto UserPrograms::contract(std::size_t index) -> const ProgramContract * {
    return index < images.size() ? &images[index].contract() : nullptr;
}
} // namespace aurora::user
