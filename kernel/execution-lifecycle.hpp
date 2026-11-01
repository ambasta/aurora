#pragma once
#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>

namespace aurora::lifecycle {
using U64 = std::uint64_t;
enum class Phase : U64 {
    empty,
    prepared,
    executing,
    parked,
    retiring
};
enum class Event : U64 {
    none,
    prepared,
    timer,
    exchange,
    request,
    output,
    exited,
    invalid_call,
    fault,
    output_failed,
    expired,
    cancelled,
    unavailable,
    completed,
    forced
};
enum class EffectKind : U64 {
    prepare,
    activate,
    complete,
    force,
    retire,
    finish
};
enum class Field : U64 {
    phase,
    generation,
    epoch,
    root,
    service,
    initial,
    saved,
    mode,
    event,
    detail,
    exhausted,
    pending,
    terminal,
    terminal_detail,
    reserved14,
    reserved15
};
class alignas(16) Descriptor final {
public:
    const void *binding = nullptr;
    U64 epoch = 0;
};
class Observation final {
public:
    U64 event = 0, detail = 0, exhausted = 0, epoch = 0, root = 0, service = 0, initial = 0, saved = 0;
};
class Result final {
public:
    U64 event = 0, detail = 0, generation = 0;
};
extern "C" {
void __au_runtime_lifecycle_construct(void *, Descriptor *);
bool __au_runtime_lifecycle_can_prepare(const void *, U64);
bool __au_runtime_lifecycle_prepare(void *, U64);
void __au_runtime_lifecycle_execute(void *, U64, Result *);
void __au_runtime_lifecycle_force(void *, U64, Result *);
bool __au_runtime_lifecycle_complete(void *, U64);
U64 __au_runtime_lifecycle_phase(const void *, U64);
U64 __au_runtime_lifecycle_generation(const void *, U64);
U64 __au_runtime_lifecycle_pending(const void *, U64);
bool __au_runtime_lifecycle_finish(void *);
}

// Native owns storage identity and synchronous exclusion, never a second slot
// phase/entry/retirement ledger. Canonical reads occur only inside an admitted
// field effect, with the entire source root loaned exclusively to that effect.
template <class Platform> class Root final {
    class Binding final {
    public:
        U64 epoch = 0;
        bool active = false;
    } binding_;
    alignas(16) std::array<std::byte, 272> storage_{};
    bool entered_ = false, busy_ = false, consumed_ = false;
    EffectKind operation_ = EffectKind::prepare;
    U64 slot_ = 0;
    static auto require(bool valid) -> void {
        if (!valid)
            Platform::fail();
    }
    auto descriptor() const -> Descriptor {
        std::array<std::byte, 16> value{};
        for (std::size_t i = 0; i < value.size(); ++i)
            value[i] = storage_[i];
        return std::bit_cast<Descriptor>(value);
    }
    auto open(EffectKind kind, U64 slot) -> void {
        require(binding_.active && !entered_ && !busy_ && !consumed_ && slot < 2 && Platform::quiet());
        entered_ = true;
        operation_ = kind;
        slot_ = slot;
    }
    auto close() -> void {
        require(entered_ && !busy_ && binding_.active && !consumed_ && Platform::quiet());
        entered_ = false;
    }
    auto scrub() -> void {
        for (auto &byte : storage_)
            *static_cast<volatile std::byte *>(&byte) = std::byte{};
    }

public:
    constexpr Root() = default;
    Root(const Root &) = delete;
    Root(Root &&) = delete;
    auto operator=(const Root &) -> Root & = delete;
    auto operator=(Root &&) -> Root & = delete;
    auto busy() const -> bool {
        return busy_;
    }
    auto created() const -> bool {
        return binding_.epoch != 0;
    }
    auto entered() const -> bool {
        return entered_;
    }
    auto initialize() -> void {
        require(!binding_.epoch && !binding_.active && !entered_ && !busy_ && Platform::quiet());
        Descriptor input{&binding_, 1};
        __au_runtime_lifecycle_construct(storage_.data(), &input);
        require(!input.binding && !input.epoch && descriptor().binding == &binding_ && descriptor().epoch == 1 &&
                Platform::quiet());
        binding_.epoch = 1;
        binding_.active = true;
    }
    auto can_prepare(U64 slot) -> bool {
        open(EffectKind::prepare, slot);
        const bool result = __au_runtime_lifecycle_can_prepare(storage_.data(), slot);
        close();
        return result;
    }
    auto prepare(U64 slot) -> bool {
        open(EffectKind::prepare, slot);
        const bool result = __au_runtime_lifecycle_prepare(storage_.data(), slot);
        close();
        return result;
    }
    auto execute(U64 slot) -> Result {
        open(EffectKind::activate, slot);
        Result result;
        __au_runtime_lifecycle_execute(storage_.data(), slot, &result);
        close();
        return result;
    }
    auto force(U64 slot) -> Result {
        open(EffectKind::force, slot);
        Result result;
        __au_runtime_lifecycle_force(storage_.data(), slot, &result);
        close();
        return result;
    }
    auto complete(U64 slot) -> bool {
        open(EffectKind::complete, slot);
        const bool result = __au_runtime_lifecycle_complete(storage_.data(), slot);
        close();
        return result;
    }
    auto phase(U64 slot) -> Phase {
        open(EffectKind::prepare, slot);
        const auto result = static_cast<Phase>(__au_runtime_lifecycle_phase(storage_.data(), slot));
        close();
        return result;
    }
    auto pending(U64 slot) -> U64 {
        open(EffectKind::prepare, slot);
        const auto result = __au_runtime_lifecycle_pending(storage_.data(), slot);
        close();
        return result;
    }
    auto generation(U64 slot) -> U64 {
        open(EffectKind::prepare, slot);
        const auto result = __au_runtime_lifecycle_generation(storage_.data(), slot);
        close();
        return result;
    }
    auto enter(const void *binding, U64 epoch, const void *field, EffectKind kind, U64 slot) -> void {
        require(entered_ && !busy_ && !consumed_ && slot == slot_ &&
                (kind == operation_ || (kind == EffectKind::retire &&
                                        (operation_ == EffectKind::activate || operation_ == EffectKind::force))));
        require(binding == &binding_ && binding_.active && epoch && epoch == binding_.epoch &&
                field == storage_.data() && Platform::quiet());
        require(descriptor().binding == binding && descriptor().epoch == epoch);
        busy_ = true;
    }
    auto canonical(U64 slot, Field field) const -> U64 {
        require(entered_ && busy_ && !consumed_ && (slot == slot_ || operation_ == EffectKind::finish) && slot < 2 &&
                static_cast<U64>(field) < 16);
        std::array<std::byte, 8> value{};
        const auto offset = 16 + slot * 128 + static_cast<U64>(field) * 8;
        for (std::size_t i = 0; i < value.size(); ++i)
            value[i] = storage_[offset + i];
        return std::bit_cast<U64>(value);
    }
    auto leave() -> void {
        require(entered_ && busy_ && Platform::quiet());
        busy_ = false;
    }
    auto consume() -> void {
        require(entered_ && busy_ && operation_ == EffectKind::finish && binding_.active && !consumed_);
        consumed_ = true;
        binding_.active = false;
    }
    auto finish() -> bool {
        open(EffectKind::finish, 0);
        const bool result = __au_runtime_lifecycle_finish(storage_.data());
        require(entered_ && !busy_ && Platform::quiet());
        require(result && consumed_ && !binding_.active && !descriptor().binding && !descriptor().epoch);
        scrub();
        entered_ = false;
        return true;
    }
};
static_assert(sizeof(Descriptor) == 16 && alignof(Descriptor) == 16 && sizeof(Observation) == 64 &&
              sizeof(Result) == 24);
} // namespace aurora::lifecycle
