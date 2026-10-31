#pragma once
#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <span>
#include "../runtime/bytes_abi.hpp"

namespace aurora::uefi {
class MappingAuthority;
}

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
public:
    static constexpr std::size_t max_banks = 4;
    class BankGrant final {
    public:
        std::span<U64> words;
        std::size_t field_offset = 0;
    };
    class Backing final {
    public:
        const U64 *words = nullptr;
        U64 count = 0;
    };
    class Grants final {
    public:
        std::array<Descriptor, max_banks> banks{};
        Descriptor authority{};
    };

private:
    friend class aurora::uefi::MappingAuthority;
    class Bank final {
    public:
        U64 *backing = nullptr;
        U64 count = 0;
        std::size_t field_offset = 0;
        bool live = false;
    };
    std::array<Bank, max_banks> banks_{};
    std::size_t bank_count_ = 0;
    U64 epoch_ = 0;
    const std::byte *root_ = nullptr;
    std::size_t root_bytes_ = 0, authority_offset_ = 0;
    bool attached_ = false, live_ = false, has_authority_ = false, authority_live_ = false;
    Access access_ = Access::read;
    static inline Binding *current_ = nullptr;
    static inline Binding *owner_ = nullptr;
    static inline U64 next_epoch_ = 0;
    static void require(bool value) {
        if (!value)
            fail();
    }
    [[nodiscard]] auto token(std::size_t bank) const -> const void * {
        return bank == 0 ? static_cast<const void *>(this) : static_cast<const void *>(&banks_[bank]);
    }
    [[nodiscard]] auto authority_token() const -> const void * {
        return &authority_live_;
    }
    [[nodiscard]] static auto
    disjoint(std::uintptr_t first, std::size_t first_bytes, std::uintptr_t second, std::size_t second_bytes) -> bool {
        return first + first_bytes <= second || second + second_bytes <= first;
    }
    [[nodiscard]] auto field_identity(std::size_t offset, const void *expected) const -> bool {
        std::array<std::byte, sizeof(Descriptor)> bytes{};
        __builtin_memcpy(bytes.data(), root_ + offset, bytes.size());
        const auto value = std::bit_cast<Descriptor>(bytes);
        return value.binding == expected && value.epoch == epoch_;
    }
    [[nodiscard]] auto identity() const -> bool {
        if (!root_)
            return false;
        for (std::size_t index = 0; index < bank_count_; ++index)
            if (banks_[index].live && !field_identity(banks_[index].field_offset, token(index)))
                return false;
        return !authority_live_ || field_identity(authority_offset_, authority_token());
    }
    // Issuer revocation is one terminal event. Individual consuming operations
    // retire source fields, but cannot let a partially consumed owner escape its
    // exclusive terminal scope.
    auto revoke_if_consumed() -> void {
        if (authority_live_)
            return;
        for (std::size_t index = 0; index < bank_count_; ++index)
            if (banks_[index].live)
                return;
        require(owner_ == this);
        owner_ = nullptr;
        live_ = attached_ = false;
    }
    [[nodiscard]] static auto admitted_bank(const void *binding, U64 epoch) -> Bank & {
        require(current_ && accessible());
        auto &value = *current_;
        require(value.live_ && value.attached_ && epoch && epoch == value.epoch_ && value.identity());
        // Compare the untrusted token before dereferencing any bank or backing.
        for (std::size_t index = 0; index < value.bank_count_; ++index)
            if (binding == value.token(index)) {
                require(value.banks_[index].live);
                return value.banks_[index];
            }
        fail();
    }

public:
    Binding() = default;
    Binding(const Binding &) = delete;
    auto operator=(const Binding &) -> Binding & = delete;
    Binding(Binding &&) = delete;
    auto operator=(Binding &&) -> Binding & = delete;
    // Native admission only. All backing and emitted source-field extents are
    // checked before any descriptor is published. The constructor runs inactive
    // and moves these descriptors into the exact admitted private root fields.
    [[nodiscard]] auto bind_set(std::span<const BankGrant> grants,
                                void *root,
                                std::size_t root_bytes,
                                std::size_t authority_offset = std::numeric_limits<std::size_t>::max()) -> Grants {
        const auto owner = reinterpret_cast<std::uintptr_t>(root);
        const auto descriptor = reinterpret_cast<std::uintptr_t>(this);
        constexpr auto limit = std::numeric_limits<std::uintptr_t>::max();
        const bool authority = authority_offset != std::numeric_limits<std::size_t>::max();
        require(!epoch_ && !live_ && !current_ && !owner_ && root && !grants.empty() && grants.size() <= max_banks &&
                root_bytes >= sizeof(Descriptor) && root_bytes <= limit - owner &&
                sizeof(Binding) <= limit - descriptor && disjoint(owner, root_bytes, descriptor, sizeof(Binding)) &&
                owner % alignof(Descriptor) == 0 && accessible() && next_epoch_ != std::numeric_limits<U64>::max());
        if (authority)
            require(grants.size() == max_banks && authority_offset <= root_bytes - sizeof(Descriptor) &&
                    authority_offset % alignof(Descriptor) == 0);
        for (std::size_t index = 0; index < grants.size(); ++index) {
            const auto &grant = grants[index];
            const auto bank = reinterpret_cast<std::uintptr_t>(grant.words.data());
            require(
                grant.words.data() && !grant.words.empty() &&
                grant.words.size() <= std::numeric_limits<std::uint32_t>::max() &&
                grant.words.size() <= (limit - bank) / sizeof(U64) && bank % alignof(U64) == 0 &&
                grant.field_offset <= root_bytes - sizeof(Descriptor) &&
                grant.field_offset % alignof(Descriptor) == 0 &&
                disjoint(owner, root_bytes, bank, grant.words.size_bytes()) &&
                disjoint(descriptor, sizeof(Binding), bank, grant.words.size_bytes()) &&
                (!authority || disjoint(grant.field_offset, sizeof(Descriptor), authority_offset, sizeof(Descriptor))));
            for (std::size_t other = 0; other < index; ++other)
                require(
                    disjoint(bank,
                             grant.words.size_bytes(),
                             reinterpret_cast<std::uintptr_t>(grants[other].words.data()),
                             grants[other].words.size_bytes()) &&
                    disjoint(grant.field_offset, sizeof(Descriptor), grants[other].field_offset, sizeof(Descriptor)));
        }
        bank_count_ = grants.size();
        root_ = static_cast<const std::byte *>(root);
        root_bytes_ = root_bytes;
        epoch_ = ++next_epoch_;
        authority_offset_ = authority_offset;
        has_authority_ = authority_live_ = authority;
        Grants result;
        for (std::size_t index = 0; index < bank_count_; ++index) {
            banks_[index] = {grants[index].words.data(), grants[index].words.size(), grants[index].field_offset, true};
            result.banks[index] = {token(index), epoch_};
        }
        if (authority)
            result.authority = {authority_token(), epoch_};
        owner_ = this;
        attached_ = live_ = true;
        return result;
    }
    [[nodiscard]] auto bind(std::span<U64> words, void *root, std::size_t root_bytes) -> Descriptor {
        const std::array<BankGrant, 1> banks{{{words, 0}}};
        return bind_set(banks, root, root_bytes).banks[0];
    }
    [[nodiscard]] auto created() const -> bool {
        return epoch_ != 0;
    }
    [[nodiscard]] auto live() const -> bool {
        return live_;
    }
    auto suspend() -> void {
        require(live_ && attached_ && !current_ && identity() && accessible());
        attached_ = false;
    }
    auto resume_set(std::span<const Backing> backing) -> void {
        require(live_ && !attached_ && !current_ && identity() && backing.size() == bank_count_ && accessible());
        for (std::size_t index = 0; index < bank_count_; ++index)
            require(banks_[index].live && backing[index].words == banks_[index].backing &&
                    backing[index].count == banks_[index].count);
        attached_ = true;
    }
    auto resume(const U64 *backing, U64 count) -> void {
        const std::array<Backing, 1> banks{{{backing, count}}};
        resume_set(banks);
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
            require(current_ == &binding_ && accessible() &&
                    (binding_.access_ == Access::consume ? !binding_.live_ : binding_.live_));
            current_ = nullptr;
        }
    };
    // Compiler-private readonly loan. Independent IR pins the exact owner and
    // closes calls for its lexical lifetime; Scope is not a dynamic loan counter.
    [[nodiscard]] static auto borrow_span(const void *binding, U64 epoch) -> hosted::bytes::NativeSpan {
        auto &bank = admitted_bank(binding, epoch);
        hosted::bytes::NativeSpan result{};
        result.payload[0] = reinterpret_cast<std::uintptr_t>(bank.backing);
        result.length = static_cast<std::int64_t>(bank.count);
        return result;
    }
    [[nodiscard]] static auto size(const void *binding, U64 epoch) -> U64 {
        return admitted_bank(binding, epoch).count;
    }
    [[nodiscard]] static auto at(const void *binding, U64 epoch, U64 index) -> U64 {
        auto &bank = admitted_bank(binding, epoch);
        require(index < bank.count);
        return bank.backing[index];
    }
    [[nodiscard]] static auto set(const void *binding, U64 epoch, U64 index, U64 word) -> bool {
        auto &bank = admitted_bank(binding, epoch);
        require(current_->access_ != Access::read && index < bank.count);
        bank.backing[index] = word;
        return true;
    }
    [[nodiscard]] static auto finish(const void *binding, U64 epoch) -> bool {
        auto &bank = admitted_bank(binding, epoch);
        require(current_->access_ == Access::consume);
        bank.live = false;
        bank.backing = nullptr;
        bank.count = 0;
        current_->revoke_if_consumed();
        return true;
    }
    // MappingAuthority is a separate private resource of the same issuer. Its
    // normal effect entry requires a writable whole-owner scope; it cannot be
    // substituted for a bank token or consumed while another owner is active.
    [[nodiscard]] static auto admitted_authority(const void *binding, U64 epoch, bool terminal = false) -> Binding & {
        require(current_ && binding == current_->authority_token() && accessible());
        auto &value = *current_;
        require(value.live_ && value.attached_ && value.has_authority_ && value.authority_live_ &&
                value.access_ != Access::read && epoch && epoch == value.epoch_ && value.identity());
        for (std::size_t index = 0; index < value.bank_count_; ++index)
            require(terminal ? !value.banks_[index].live : value.banks_[index].live);
        return value;
    }
    [[nodiscard]] static auto finish_authority(const void *binding, U64 epoch) -> bool {
        auto &value = admitted_authority(binding, epoch, true);
        require(value.access_ == Access::consume);
        for (std::size_t index = 0; index < value.bank_count_; ++index)
            require(!value.banks_[index].live);
        value.authority_live_ = false;
        value.revoke_if_consumed();
        return true;
    }
};
static_assert(sizeof(Descriptor) == 16 && alignof(Descriptor) == 16);
} // namespace aurora::words
