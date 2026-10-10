#pragma once

#include "ipc-policy.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <span>

namespace aurora::ipc {

// Representation validation only. The protected service owns range/byte policy.
[[nodiscard]] constexpr bool snapshot_reply_valid(std::uint64_t word) noexcept {
    return word == 2 || word == 3 || word == 4 || word == 5 || (word & ~std::uint64_t{0xff00}) == 1;
}

enum class SnapshotPublication {
    ready,
    unavailable,
    malformed
};

class SnapshotSlot final {
    std::array<std::byte, 64> bytes_{};
    std::uint64_t generation_ = 0;
    bool valid_ = false;

public:
    static constexpr std::size_t record_bytes = 96;
    static constexpr std::size_t stack_reservation = 112;
    using Record = std::span<std::byte, record_bytes>;

    void clear() noexcept {
        valid_ = false;
        generation_ = 0;
        volatile std::byte *data = bytes_.data();
        for (std::size_t byte = 0; byte < bytes_.size(); ++byte) {
            data[byte] = std::byte{0};
        }
    }
    [[nodiscard]] bool ready() const noexcept {
        return valid_;
    }
    [[nodiscard]] bool bound() const noexcept {
        return valid_ && generation_ != 0;
    }

    // The caller has closed the actual region and checked its owner/lease ledger.
    // No returned byte may be inspected before that boundary.
    [[nodiscard]] SnapshotPublication publish(std::span<const std::byte, 72> output) noexcept {
        clear();
        std::uint64_t status = 0;
        for (unsigned byte = 0; byte < 8; ++byte) {
            status |= std::uint64_t(std::to_integer<unsigned char>(output[byte])) << (byte * 8);
        }
        if (status != 0) {
            if (status != 1 && status != 3) {
                return SnapshotPublication::malformed;
            }
            for (std::size_t byte = 8; byte < output.size(); ++byte) {
                if (output[byte] != std::byte{0}) {
                    return SnapshotPublication::malformed;
                }
            }
            return SnapshotPublication::unavailable;
        }
        for (std::size_t byte = 0; byte < bytes_.size(); ++byte) {
            bytes_[byte] = output[8 + byte];
        }
        valid_ = true;
        return SnapshotPublication::ready;
    }
    [[nodiscard]] bool bind(Endpoint service) noexcept {
        if (!valid_ || generation_ != 0 || service.slot() != 1 || service.generation() == 0) {
            return false;
        }
        generation_ = service.generation();
        return true;
    }
    [[nodiscard]] bool matches(Endpoint service) const noexcept {
        return bound() && service.slot() == 1 && service.generation() == generation_;
    }
    // This destination is supplied only through a verified retained stack lease,
    // after authenticated receive and a complete per-launch stack scrub.
    [[nodiscard]] bool stage(Record record, Endpoint service, std::uint64_t phase, Request request) const noexcept {
        if (!matches(service)) {
            return false;
        }
        const std::array words{phase, request.first(), request.second()};
        for (std::size_t word = 0; word < words.size(); ++word) {
            for (unsigned byte = 0; byte < 8; ++byte) {
                record[word * 8 + byte] = std::byte(words[word] >> (byte * 8));
            }
        }
        for (std::size_t byte = 0; byte < bytes_.size(); ++byte) {
            record[24 + byte] = bytes_[byte];
        }
        for (std::size_t byte = 88; byte < record.size(); ++byte) {
            record[byte] = std::byte{0};
        }
        return true;
    }
};

} // namespace aurora::ipc
