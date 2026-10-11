#pragma once

#include <cstddef>
#include <cstdint>
#include <type_traits>
#include <limits>

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

// Compiler-private copied-value stride. The canonical class layout remains the
// sole producer; this bound merely validates the adapter's trusted ABI inputs.
inline constexpr std::int64_t maximum_value_stride = 520;
inline constexpr bool valid_value_stride(std::int64_t stride) noexcept {
    return stride > 0 && stride <= maximum_value_stride;
}
inline constexpr std::int64_t value_byte_length(std::int64_t count, std::int64_t stride) noexcept {
    return !valid_value_stride(stride) || count < 0 || count > std::numeric_limits<std::int64_t>::max() / stride
               ? -1
               : count * stride;
}

extern "C" {
void __au_runtime_values_allocate(
    std::uint64_t region, std::int64_t count, std::int64_t stride, const void *fill, NativeOwner *output) noexcept;
void __au_runtime_values_at(const NativeOwner *owner, std::int64_t index, std::int64_t stride, void *output) noexcept;
std::uint64_t
__au_runtime_values_set(NativeOwner *owner, std::int64_t index, std::int64_t stride, const void *value) noexcept;
std::uint64_t
__au_runtime_values_resize(NativeOwner *owner, std::int64_t count, std::int64_t stride, const void *fill) noexcept;
void __au_runtime_bytes_allocate(std::uint64_t region, std::int64_t length, NativeOwner *output) noexcept;
std::int64_t __au_runtime_bytes_borrow_length(const NativeOwner *owner) noexcept;
std::uint64_t __au_runtime_bytes_at(const NativeOwner *owner, std::int64_t index) noexcept;
std::uint64_t __au_runtime_bytes_set(NativeOwner *owner, std::int64_t index, std::uint64_t value) noexcept;
std::uint64_t __au_runtime_bytes_resize(NativeOwner *owner, std::int64_t length) noexcept;
void __au_runtime_bytes_drop(NativeOwner *owner) noexcept;
}

} // namespace aurora::hosted::bytes
