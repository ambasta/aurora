#pragma once
#include <cstddef>
#include <cstdint>
#ifdef AURORA_RUNTIME_ROW_POLICY
#include <array>
#endif

#ifndef AURORA_RUNTIME_IMAGE_POLICY
#error "Select an explicit AURORA_RUNTIME_IMAGE_POLICY"
#endif

namespace aurora::uefi {
class ImagePagePolicy final {
public:
#define AURORA_IMAGE_POLICY(name, first, second, third)                                                                \
    static constexpr auto name(std::size_t image) -> std::uint64_t {                                                   \
        return image == 0 ? first : image == 1 ? second : image == 2 ? third : 0;                                      \
    }
#include "image-page-policies.inc"
#undef AURORA_IMAGE_POLICY
    // The widest pages any row of this image admits; it bounds the layout.
    static constexpr auto ceiling(std::size_t image) -> std::uint64_t {
        return AURORA_RUNTIME_IMAGE_POLICY(image);
    }
#ifdef AURORA_RUNTIME_ROW_POLICY
    // A packed test image's rows each admit their former image's named policy,
    // chosen once before any domain exists; nothing is admitted until then.
    template <auto Policy> static auto choose() -> void {
        static_assert(Policy(0) <= ceiling(0) && Policy(1) <= ceiling(1) && Policy(2) <= ceiling(2));
        row = {Policy(0), Policy(1), Policy(2)};
    }
    [[nodiscard]] static auto pages(std::size_t image) -> std::uint64_t {
        return image < row.size() ? row[image] : 0;
    }

private:
    static inline std::array<std::uint64_t, 3> row{};
#else
    static constexpr auto pages(std::size_t image) -> std::uint64_t {
        return AURORA_RUNTIME_IMAGE_POLICY(image);
    }
#endif
};
} // namespace aurora::uefi
