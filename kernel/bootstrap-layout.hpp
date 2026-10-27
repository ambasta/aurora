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
    // The relocated kernel reservation is independent of the low runtime owners.
    // These relations protect every handoff version, not only runtime profiles.
    static_assert(arena_bytes % page_size == 0 && kernel_payload_offset % page_size == 0 && kernel_payload_limit != 0 &&
                  kernel_payload_limit % page_size == 0);
    static_assert(kernel_payload_offset < arena_bytes && kernel_payload_limit <= arena_bytes - kernel_payload_offset);
    static_assert(kernel_payload_offset + kernel_payload_limit == kernel_idt_offset);
    static_assert(kernel_idt_offset + 2 * page_size == kernel_stack_bottom);
    static_assert(kernel_stack_top == kernel_stack_bottom + stack_pages * page_size);
    static_assert(kernel_stack_top < arena_bytes && page_size <= arena_bytes - kernel_stack_top);
    static_assert(stack_cap <= kernel_stack_top - kernel_stack_bottom);
};
} // namespace aurora
