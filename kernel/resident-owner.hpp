#pragma once
#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <limits>

namespace aurora::resident {
using U64 = std::uint64_t;
enum class OperationKind : U64 {
    prepare,
    run,
    console,
    reject,
    shutdown
};
class alignas(16) Descriptor final {
public:
    const void *binding = nullptr;
    U64 epoch = 0;
};
class Parent final {
public:
    const void *context = nullptr;
    U64 epoch = 0;
};
// Only native composition creates an operation. Its immutable input remains
// outside Aurora; possession of a slot alone cannot select a client command.
template <class Input, class Platform> class Root final {
    class Binding final {
    public:
        U64 epoch = 0;
        bool active = false;
    } binding_;
    alignas(16) std::array<std::byte, 16> storage_{};
    U64 next_operation_ = 0;
    bool finishing_ = false;

    static auto require(bool valid) -> void {
        if (!valid)
            Platform::fail();
    }
    auto descriptor() const -> Descriptor {
        return std::bit_cast<Descriptor>(storage_);
    }
    auto scrub() -> void {
        for (auto &byte : storage_)
            *static_cast<volatile std::byte *>(&byte) = std::byte{0};
    }

public:
    class Operation final {
        friend class Root;
        Root *owner_ = nullptr;
        U64 epoch_ = 0, pins_ = 0;
        bool active_ = false, busy_ = false, spent_ = false;
        OperationKind kind_;
        Input &input_;

    public:
        Operation(OperationKind kind, Input &input) : kind_(kind), input_(input) {
        }
        Operation(const Operation &) = delete;
        auto operator=(const Operation &) -> Operation & = delete;
        Operation(Operation &&) = delete;
        auto operator=(Operation &&) -> Operation & = delete;
        ~Operation() {
            require(!active_ && !pins_ && !busy_);
        }
        auto input() -> Input & {
            return input_;
        }
        auto kind() const -> OperationKind {
            return kind_;
        }
    };

private:
    Operation *operation_ = nullptr;

public:
    Root() = default;
    Root(const Root &) = delete;
    auto operator=(const Root &) -> Root & = delete;
    Root(Root &&) = delete;
    auto operator=(Root &&) -> Root & = delete;
    auto active() const -> bool {
        return binding_.active;
    }
    auto created() const -> bool {
        return binding_.epoch != 0;
    }
    auto storage() -> void * {
        return storage_.data();
    }
    auto initialize() -> void {
        require(!binding_.active && !operation_ && !finishing_ && binding_.epoch == 0 && Platform::quiet());
        scrub();
        ++binding_.epoch;
        Descriptor input{&binding_, binding_.epoch};
        // This is the emitted complete constructor, not a borrow of uninitialized
        // storage. Activation follows its complete field-transfer admission.
        Platform::construct(storage_.data(), &input);
        require(!input.binding && !input.epoch && descriptor().binding == &binding_ &&
                descriptor().epoch == binding_.epoch && Platform::quiet());
        binding_.active = true;
    }
    auto open(Operation &operation) -> void {
        require(binding_.active && !operation_ && !finishing_ && !operation.active_ &&
                next_operation_ != std::numeric_limits<U64>::max() && Platform::quiet());
        operation.owner_ = this;
        operation.epoch_ = ++next_operation_;
        operation.active_ = true;
        operation_ = &operation;
        finishing_ = operation.kind_ == OperationKind::shutdown;
    }
    auto close(Operation &operation) -> void {
        require(operation_ == &operation && operation.owner_ == this && operation.active_ && operation.spent_ &&
                !operation.busy_ && !operation.pins_ && !finishing_ && binding_.active && Platform::quiet());
        operation.active_ = false;
        operation.owner_ = nullptr;
        operation_ = nullptr;
    }
    auto enter(const void *binding, U64 epoch, const void *field, OperationKind kind, bool continuation = false)
        -> Operation & {
        require(binding == &binding_ && binding_.active && epoch && epoch == binding_.epoch &&
                field == storage_.data() && descriptor().binding == binding && descriptor().epoch == epoch &&
                operation_ && operation_->owner_ == this && operation_->active_ && !operation_->busy_ &&
                operation_->kind_ == kind && (continuation ? operation_->spent_ : !operation_->spent_) &&
                finishing_ == (kind == OperationKind::shutdown) && Platform::quiet());
        operation_->spent_ = true;
        operation_->busy_ = true;
        return *operation_;
    }
    auto leave(Operation &operation) -> void {
        require(operation_ == &operation && operation.active_ && operation.busy_ && !operation.pins_ &&
                Platform::quiet());
        operation.busy_ = false;
    }
    auto capture_parent() -> Parent {
        require(binding_.active && operation_ && operation_->active_ && operation_->busy_ &&
                operation_->kind_ != OperationKind::shutdown && operation_->pins_ != ~U64{0});
        ++operation_->pins_;
        return {operation_, operation_->epoch_};
    }
    auto parent_valid(Parent parent) const -> bool {
        return binding_.active && operation_ && parent.context == operation_ && parent.epoch &&
               parent.epoch == operation_->epoch_ && operation_->owner_ == this && operation_->active_ &&
               operation_->busy_ && operation_->pins_ && !finishing_;
    }
    auto release_parent(Parent parent) -> void {
        require(parent_valid(parent));
        --operation_->pins_;
    }
    // Called only by the checked consuming field effect after actual physical
    // cleanup. A failed close may consume here, but cannot skip that cleanup.
    auto consume(Operation &operation) -> void {
        require(operation_ == &operation && finishing_ && binding_.active && operation.active_ && operation.busy_ &&
                operation.kind_ == OperationKind::shutdown && !operation.pins_);
        scrub();
        binding_.active = false;
    }
    auto finish(Operation &operation) -> void {
        require(operation_ == &operation && finishing_ && !binding_.active && operation.active_ && operation.spent_ &&
                !operation.busy_ && !operation.pins_ && !descriptor().binding && !descriptor().epoch &&
                Platform::quiet());
        operation.active_ = false;
        operation.owner_ = nullptr;
        operation_ = nullptr;
        finishing_ = false;
        scrub();
    }
};

// Existing isolated component adapters need no retained parent. Production
// platforms implement all three hooks, so every child grant captures and checks
// the exact enclosing owner operation rather than a copied authorization flag.
template <class Platform> class ParentBoundary final {
public:
    static auto capture() -> Parent {
        if constexpr (requires { Platform::capture_parent(); })
            return Platform::capture_parent();
        else
            return {};
    }
    static auto valid(Parent parent) -> bool {
        if constexpr (requires { Platform::parent_valid(parent); })
            return Platform::parent_valid(parent);
        else
            return !parent.context && !parent.epoch;
    }
    static auto release(Parent parent) -> void {
        if constexpr (requires { Platform::release_parent(parent); })
            Platform::release_parent(parent);
        else if (parent.context || parent.epoch)
            Platform::fail();
    }
};
static_assert(sizeof(Descriptor) == 16 && alignof(Descriptor) == 16);
} // namespace aurora::resident
