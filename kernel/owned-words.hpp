#pragma once
#include <bit>
#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <span>
#include "../runtime/bytes_abi.hpp"

namespace aurora::words {
using U64 = std::uint64_t;
// The platform checks physical reachability and execution serialization, never
// allocator state. The root and this binding remain mapped while backing sleeps.
[[nodiscard]] auto accessible() -> bool;
[[noreturn]] auto fail() -> void;
class alignas(16) Descriptor final {
public:
    const void *binding = nullptr;
    U64 epoch = 0;
};
enum class Access {
    read,
    write,
    consume
};
class Binding final {
    U64 *backing_ = nullptr;
    U64 count_ = 0, epoch_ = 0;
    const std::byte *root_ = nullptr;
    bool attached_ = false, live_ = false;
    Access access_ = Access::read;
    static inline Binding *current_ = nullptr;
    static inline Binding *owner_ = nullptr;
    static inline U64 next_epoch_ = 0;
    static void require(bool value) {
        if (!value)
            fail();
    }
    [[nodiscard]] auto identity() const -> bool {
        if (!root_)
            return false;
        std::array<std::byte, sizeof(Descriptor)> bytes{};
        __builtin_memcpy(bytes.data(), root_, bytes.size());
        const auto value = std::bit_cast<Descriptor>(bytes);
        return value.binding == this && value.epoch == epoch_;
    }

public:
    Binding() = default;
    Binding(const Binding &) = delete;
    auto operator=(const Binding &) -> Binding & = delete;
    Binding(Binding &&) = delete;
    auto operator=(Binding &&) -> Binding & = delete;
    // Native admission only: no source pointer adoption. The platform has
    // established this exact, private RW/NX bank before this one-shot handoff.
    [[nodiscard]] auto bind(std::span<U64> words, void *root, std::size_t root_bytes) -> Descriptor {
        const auto bank = reinterpret_cast<std::uintptr_t>(words.data());
        const auto owner = reinterpret_cast<std::uintptr_t>(root);
        const auto descriptor = reinterpret_cast<std::uintptr_t>(this);
        constexpr auto limit = std::numeric_limits<std::uintptr_t>::max();
        require(!epoch_ && !live_ && !current_ && !owner_ && root && words.data() && !words.empty() &&
                words.size() <= std::numeric_limits<std::uint32_t>::max() &&
                words.size() <= (limit - bank) / sizeof(U64) && root_bytes >= sizeof(Descriptor) &&
                root_bytes <= limit - owner && sizeof(Binding) <= limit - descriptor &&
                (owner + root_bytes <= bank || bank + words.size_bytes() <= owner) &&
                (descriptor + sizeof(Binding) <= bank || bank + words.size_bytes() <= descriptor) &&
                (owner + root_bytes <= descriptor || descriptor + sizeof(Binding) <= owner) &&
                reinterpret_cast<std::uintptr_t>(words.data()) % alignof(U64) == 0 &&
                reinterpret_cast<std::uintptr_t>(root) % alignof(Descriptor) == 0 && accessible() &&
                next_epoch_ != std::numeric_limits<U64>::max());
        backing_ = words.data();
        count_ = words.size();
        root_ = static_cast<const std::byte *>(root);
        owner_ = this;
        epoch_ = ++next_epoch_;
        attached_ = live_ = true;
        return {this, epoch_};
    }
    [[nodiscard]] auto created() const -> bool {
        return epoch_ != 0;
    }
    [[nodiscard]] auto live() const -> bool {
        return live_;
    }
    // Close access BEFORE the page-table change. No word pointer is formed by
    // the source adapter until resume has authenticated the restored same bank.
    auto suspend() -> void {
        require(live_ && attached_ && !current_ && identity() && accessible());
        attached_ = false;
    }
    auto resume(const U64 *backing, U64 count) -> void {
        require(live_ && !attached_ && !current_ && identity() && backing == backing_ && count == count_ &&
                accessible());
        attached_ = true;
    }
    class Scope final {
        Binding &binding_;

    public:
        Scope(Binding &binding, Access access) : binding_(binding) {
            require(!current_ && binding.live_ && binding.attached_ && binding.identity() && accessible());
            binding.access_ = access;
            current_ = &binding;
        }
        Scope(const Scope &) = delete;
        ~Scope() {
            require(current_ == &binding_ && accessible() && (binding_.live_ || binding_.access_ == Access::consume));
            current_ = nullptr;
        }
    };
    // Compare the untrusted binding value with the current admitted scope
    // BEFORE dereferencing it. Stale/detached/foreign access never touches data.
    [[nodiscard]] static auto admitted(const void *binding, U64 epoch) -> Binding & {
        require(current_ && binding == current_);
        auto &value = *current_;
        require(value.live_ && value.attached_ && epoch && epoch == value.epoch_ && value.identity());
        return value;
    }
    // Compiler-private readonly loan. The independent source verifier pins the
    // exact owner and closes calls for its lexical lifetime; Scope is not a
    // dynamic span counter. No address is published before grant authentication.
    [[nodiscard]] static auto borrow_span(const void *binding, U64 epoch) -> hosted::bytes::NativeSpan {
        auto &value = admitted(binding, epoch);
        require(accessible());
        hosted::bytes::NativeSpan result{};
        result.payload[0] = reinterpret_cast<std::uintptr_t>(value.backing_);
        result.length = static_cast<std::int64_t>(value.count_);
        return result;
    }
    [[nodiscard]] static auto size(const void *binding, U64 epoch) -> U64 {
        return admitted(binding, epoch).count_;
    }
    [[nodiscard]] static auto at(const void *binding, U64 epoch, U64 index) -> U64 {
        auto &value = admitted(binding, epoch);
        require(index < value.count_);
        return value.backing_[index];
    }
    [[nodiscard]] static auto set(const void *binding, U64 epoch, U64 index, U64 word) -> bool {
        auto &value = admitted(binding, epoch);
        require(value.access_ != Access::read && index < value.count_);
        value.backing_[index] = word;
        return true;
    }
    [[nodiscard]] static auto finish(const void *binding, U64 epoch) -> bool {
        auto &value = admitted(binding, epoch);
        require(value.access_ == Access::consume);
        require(owner_ == &value);
        owner_ = nullptr;
        value.live_ = value.attached_ = false;
        value.backing_ = nullptr;
        value.count_ = 0;
        // The compiler scrubs the consumed field after this returns. Only
        // Scope teardown is permitted after revocation; reserved pages stay put.
        return true;
    }
};
static_assert(sizeof(Descriptor) == 16 && alignof(Descriptor) == 16);
} // namespace aurora::words
