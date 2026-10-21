#pragma once
#include <cstddef>
#include <cstdint>

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
    static constexpr auto pages(std::size_t image) -> std::uint64_t {
        return AURORA_RUNTIME_IMAGE_POLICY(image);
    }
};
} // namespace aurora::uefi
