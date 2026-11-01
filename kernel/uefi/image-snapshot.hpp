#pragma once
#include "memory-manager.hpp"

namespace aurora::uefi {
// The loader's handle contains no frames, mapping tags, mutable aliases or
// seal state. The manager owns the complete snapshot lifetime and authenticates
// this epoch on every operation, including fill after a loader callback.
class ImageSnapshot final {
public:
    using U64 = std::uint64_t;
    static constexpr U64 limit = U64{1} << 26;

private:
    MemoryManager &manager_;
    const U64 epoch_;

public:
    ImageSnapshot(MemoryManager &manager, U64 epoch) : manager_(manager), epoch_(epoch) {
    }
    ImageSnapshot(const ImageSnapshot &) = delete;
    auto operator=(const ImageSnapshot &) -> ImageSnapshot & = delete;
    ImageSnapshot(ImageSnapshot &&) = delete;
    auto operator=(ImageSnapshot &&) -> ImageSnapshot & = delete;

    [[nodiscard]] auto owner() const -> U64 {
        return manager_.snapshot_value(epoch_, 0);
    }
    [[nodiscard]] auto size() const -> U64 {
        return manager_.snapshot_value(epoch_, 1);
    }
    [[nodiscard]] auto held() const -> U64 {
        return manager_.snapshot_value(epoch_, 2);
    }
    [[nodiscard]] auto epoch() const -> U64 {
        return epoch_;
    }

    // The input pin is synchronous and closes before return. The caller may
    // invoke the service only between fills, with no destination alias alive.
    [[nodiscard]] auto fill(U64 offset, std::span<const std::byte> bytes) -> bool {
        return manager_.fill_snapshot(epoch_, offset, bytes);
    }
    [[nodiscard]] auto verify() const -> bool {
        return manager_.verify_snapshot(epoch_);
    }
    [[nodiscard]] auto seal() -> bool {
        return manager_.seal_snapshot(epoch_);
    }
    [[nodiscard]] auto release() -> bool {
        return manager_.discard_snapshot(epoch_);
    }
};
} // namespace aurora::uefi
