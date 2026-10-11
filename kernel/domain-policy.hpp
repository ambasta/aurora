#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>

namespace aurora::user {
class DomainRegistry;
class DomainHandle final {
    friend class DomainRegistry;
    std::size_t slot_ = 3;
    std::uint64_t stamp_ = 0;
    constexpr DomainHandle(std::size_t slot, std::uint64_t stamp) : slot_(slot), stamp_(stamp) {
    }

public:
    constexpr DomainHandle() = default;
};
// Single CPU, bounded authority. Unique stamps prevent stale-slot and registry-rebirth reuse.
class DomainRegistry final {
    enum class State {
        empty,
        ready,
        active
    };
    inline static std::uint64_t next_stamp_{};
    std::array<State, 3> states_{};
    std::array<std::uint64_t, 3> stamps_{};
    std::optional<std::size_t> active_{};

public:
    static constexpr std::size_t capacity = 3;
    DomainRegistry() = default;
    DomainRegistry(const DomainRegistry &) = delete;
    auto operator=(const DomainRegistry &) -> DomainRegistry & = delete;
    [[nodiscard]] auto index(DomainHandle handle) const -> std::optional<std::size_t> {
        if (handle.slot_ >= capacity || states_[handle.slot_] == State::empty || handle.stamp_ == 0 ||
            stamps_[handle.slot_] != handle.stamp_)
            return std::nullopt;
        return handle.slot_;
    }
    // Diagnostic identity only: a scalar stamp cannot construct a DomainHandle.
    [[nodiscard]] auto incarnation(DomainHandle handle) const -> std::optional<std::uint64_t> {
        const auto slot = index(handle);
        return slot ? std::optional<std::uint64_t>{stamps_[*slot]} : std::nullopt;
    }
    [[nodiscard]] auto create() -> std::optional<DomainHandle> {
        if (active_ || next_stamp_ == UINT64_MAX)
            return std::nullopt;
        for (std::size_t slot = 0; slot < capacity; ++slot) {
            if (states_[slot] == State::empty) {
                stamps_[slot] = ++next_stamp_;
                states_[slot] = State::ready;
                return DomainHandle{slot, stamps_[slot]};
            }
        }
        return std::nullopt;
    }
    [[nodiscard]] auto ready(DomainHandle handle) const -> bool {
        const auto slot = index(handle);
        return slot && states_[*slot] == State::ready && !active_;
    }
    [[nodiscard]] auto activate(DomainHandle handle) -> bool {
        if (!ready(handle))
            return false;
        active_ = *index(handle);
        states_[*active_] = State::active;
        return true;
    }
    [[nodiscard]] auto active(DomainHandle handle) const -> bool {
        const auto slot = index(handle);
        return slot && active_ && *slot == *active_ && states_[*slot] == State::active;
    }
    [[nodiscard]] auto deactivate(DomainHandle handle) -> bool {
        if (!active(handle))
            return false;
        states_[*active_] = State::ready;
        active_.reset();
        return true;
    }
    [[nodiscard]] auto destroy(DomainHandle handle) -> bool {
        if (!ready(handle))
            return false;
        states_[*index(handle)] = State::empty;
        return true;
    }
};
} // namespace aurora::user
