#pragma once
#include <cstdint>
namespace aurora::uefi {
[[noreturn]] auto run_framebuffer(std::uint64_t arena) -> void;
// The Display pixel service of the framebuffer rows; the display fixture's one
// __au_runtime_display_pixel import forwards here until the graphical console runs.
[[nodiscard]] auto framebuffer_display_pixel(const void *grant,
                                             std::uint64_t generation,
                                             std::uint64_t x,
                                             std::uint64_t y,
                                             std::uint64_t red,
                                             std::uint64_t green,
                                             std::uint64_t blue) -> std::uint64_t;
} // namespace aurora::uefi
