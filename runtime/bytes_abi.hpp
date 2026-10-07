#pragma once

#include <cstddef>
#include <cstdint>
#include <type_traits>

// Compiler-private bootstrap ABI shared by mutually exclusive runtime adapters.
// The historical C++ namespace is retained for mechanical hosted compatibility.
// This header supplies no allocator, host services, foreign owner API or authority.
namespace aurora::hosted::bytes {

// Generated code reserves an opaque 32-byte slot. Only this trusted adapter and
// the compiler's private lowering may interpret it; no payload address is stored.
struct alignas(8) NativeOwner {
    std::uint64_t region = 0;
    std::uint64_t allocation = 0;
    std::int64_t length = 0;
    std::uint64_t success = 0;
};

static_assert(std::is_standard_layout_v<NativeOwner>);
static_assert(std::is_trivially_copyable_v<NativeOwner>);
static_assert(sizeof(NativeOwner) == 32 && alignof(NativeOwner) == 8);
static_assert(offsetof(NativeOwner, region) == 0 && offsetof(NativeOwner, allocation) == 8);
static_assert(offsetof(NativeOwner, length) == 16 && offsetof(NativeOwner, success) == 24);

extern "C" {
void __au_runtime_bytes_allocate(std::uint64_t region, std::int64_t length, NativeOwner *output) noexcept;
std::uint64_t __au_runtime_bytes_at(const NativeOwner *owner, std::int64_t index) noexcept;
std::uint64_t __au_runtime_bytes_set(NativeOwner *owner, std::int64_t index, std::uint64_t value) noexcept;
std::uint64_t __au_runtime_bytes_resize(NativeOwner *owner, std::int64_t length) noexcept;
void __au_runtime_bytes_drop(NativeOwner *owner) noexcept;
}

} // namespace aurora::hosted::bytes
