#pragma once
#include <cstddef>
namespace aurora::uefi {
// Two closed firmware observations, not live device grants. Version 1 remains
// the six-function EDU/NVMe schema; version 2 adds only the fixed VGA function.
template <bool graphics> class DmaCaptureLayout final {
public:
    static constexpr unsigned version = graphics ? 2 : 1;
    static constexpr std::size_t functions = graphics ? 7 : 6;
    static constexpr std::size_t headers = 576, header_bytes = 72;
    static constexpr std::size_t root = graphics ? 1152 : 1024, root_bytes = 738;
    static constexpr std::size_t reservations = 2048, reservation_bytes = 256;
    static constexpr std::size_t reservation_count = graphics ? 3 : 1;
    static constexpr std::size_t bytes = 4096;
    static_assert(512 + 48 <= headers);
    static_assert(headers + functions * header_bytes <= root);
    static_assert(root + root_bytes <= reservations);
    static_assert(reservations + reservation_count * reservation_bytes <= bytes);
};
} // namespace aurora::uefi
