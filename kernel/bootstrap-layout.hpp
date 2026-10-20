#pragma once
#include <cstdint>

namespace aurora {
// One numeric table also generates metadata for the host-side image/boot tools.
class BootstrapLayout {
public:
#define AURORA_LAYOUT(name, value) static constexpr std::uint64_t name = value;
#include "bootstrap-layout-values.inc"
#undef AURORA_LAYOUT
    static_assert(fault_frame_size == fault_frame_words * sizeof(std::uint64_t));
    static_assert(image_slot_bytes == max_code_pages * page_size);
    static_assert(code_stride == image_slot_bytes + page_size);
    static_assert(user_stack_top == user_stack_bottom + stack_pages * page_size);
    static_assert(user_stack_guard + page_size == user_stack_bottom);
};
} // namespace aurora
