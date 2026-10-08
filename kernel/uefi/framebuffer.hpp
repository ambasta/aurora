#pragma once
#include <cstdint>
namespace aurora::uefi {
[[noreturn]] auto run_framebuffer(std::uint64_t arena) -> void;
}
