#pragma once
#include "types.hpp"
#include <algorithm>
#include <bit>
#include <limits>
#include <memory>
#include <optional>

namespace aurora::ir::verification {
// A function's already validated scalar-slot offsets, sorted into a dense domain.
// Even a non-const owner cannot mutate this domain after facts refer to it.
class InitializationSlotUniverse {
    const std::vector<int> offsets_;

    static std::vector<int> checkedOffsets(std::vector<int> offsets, int frameBytes) {
        // These bounds follow from the existing frame and disjoint-slot checks;
        // they do not impose a new limit on admitted functions.
        if (frameBytes < 0 || frameBytes > 65536 ||
            offsets.size() > static_cast<std::size_t>(frameBytes))
            throw Error("invalid initialization slot universe extent");
        for (int offset : offsets)
            if (offset <= 0 || offset > frameBytes)
                throw Error("invalid initialization slot universe offset");
        std::sort(offsets.begin(), offsets.end());
        if (std::adjacent_find(offsets.begin(), offsets.end()) != offsets.end())
            throw Error("duplicate initialization slot universe offset");
        return offsets;
    }

  public:
    explicit InitializationSlotUniverse(std::vector<int> offsets, int frameBytes)
        : offsets_(checkedOffsets(std::move(offsets), frameBytes)) {}

    std::size_t size() const { return offsets_.size(); }
    std::size_t wordCount() const { return size() / 64 + (size() % 64 != 0); }
    std::optional<std::size_t> index(int offset) const {
        const auto found = std::lower_bound(offsets_.begin(), offsets_.end(), offset);
        if (found == offsets_.end() || *found != offset)
            return std::nullopt;
        return static_cast<std::size_t>(found - offsets_.begin());
    }
    int offset(std::size_t index) const { return offsets_.at(index); }
    bool operator==(const InitializationSlotUniverse &other) const {
        return offsets_ == other.offsets_;
    }
};

class InitializationFacts {
    std::shared_ptr<const InitializationSlotUniverse> universe_;
    std::vector<std::uint64_t> words_;
    std::size_t size_ = 0;

    static std::size_t checkedWordCount(
        const std::shared_ptr<const InitializationSlotUniverse> &universe) {
        if (!universe)
            throw Error("missing initialization slot universe");
        const auto count = universe->wordCount();
        if (count > std::numeric_limits<std::size_t>::max() / sizeof(std::uint64_t) ||
            count > std::vector<std::uint64_t>{}.max_size())
            throw Error("initialization fact allocation overflow");
        return count;
    }
    std::optional<std::size_t> index(int offset) const {
        return universe_ ? universe_->index(offset) : std::nullopt;
    }
    bool sameUniverse(const InitializationFacts &other) const {
        return universe_ == other.universe_ ||
               (universe_ && other.universe_ && *universe_ == *other.universe_);
    }
    template <class Visitor> void forEachOffset(Visitor visit) const {
        for (std::size_t word = 0; word < words_.size(); ++word) {
            auto remaining = words_[word];
            while (remaining != 0) {
                const auto bit = static_cast<std::size_t>(std::countr_zero(remaining));
                visit(universe_->offset(word * 64 + bit));
                remaining &= remaining - 1;
            }
        }
    }

  public:
    // A default or moved-from value is an empty set without an insertion domain.
    InitializationFacts() = default;
    explicit InitializationFacts(std::shared_ptr<const InitializationSlotUniverse> universe)
        : universe_(std::move(universe)), words_(checkedWordCount(universe_), 0) {}
    InitializationFacts(const InitializationFacts &) = default;
    InitializationFacts &operator=(const InitializationFacts &other) {
        if (this != &other) {
            InitializationFacts copy(other);
            *this = std::move(copy);
        }
        return *this;
    }
    InitializationFacts(InitializationFacts &&other) noexcept
        : universe_(std::move(other.universe_)), words_(std::move(other.words_)),
          size_(std::exchange(other.size_, 0)) {
        other.words_.clear();
    }
    InitializationFacts &operator=(InitializationFacts &&other) noexcept {
        if (this != &other) {
            universe_ = std::move(other.universe_);
            words_ = std::move(other.words_);
            size_ = std::exchange(other.size_, 0);
            other.words_.clear();
        }
        return *this;
    }

    bool contains(int offset) const {
        const auto bit = index(offset);
        return bit && (words_[*bit / 64] & (std::uint64_t{1} << (*bit % 64))) != 0;
    }
    // Return whether a new fact was inserted. Unknown offsets are malformed;
    // unlike membership/removal, silently ignoring them would lose evidence.
    bool insert(int offset) {
        const auto bit = index(offset);
        if (!bit)
            throw Error("initialization fact requires a validated scalar slot");
        auto &word = words_[*bit / 64];
        const auto mask = std::uint64_t{1} << (*bit % 64);
        if ((word & mask) != 0)
            return false;
        word |= mask;
        ++size_;
        return true;
    }
    std::size_t erase(int offset) {
        const auto bit = index(offset);
        if (!bit)
            return 0;
        auto &word = words_[*bit / 64];
        const auto mask = std::uint64_t{1} << (*bit % 64);
        if ((word & mask) == 0)
            return 0;
        word &= ~mask;
        --size_;
        return 1;
    }
    std::size_t size() const { return size_; }
    std::size_t wordCount() const { return words_.size(); }
    // Logical word payload only: excludes allocator overhead, shared universe
    // and the containing object. This is not RSS.
    std::size_t payloadBytes() const { return wordCount() * sizeof(std::uint64_t); }
    bool operator==(const InitializationFacts &other) const {
        if (size_ != other.size_)
            return false;
        if (sameUniverse(other))
            return words_ == other.words_;
        bool equal = true;
        forEachOffset([&](int offset) { equal = equal && other.contains(offset); });
        return equal;
    }

    void intersectWith(const InitializationFacts &other) {
        if (!sameUniverse(other)) {
            forEachOffset([&](int offset) {
                if (!other.contains(offset))
                    erase(offset);
            });
            return;
        }
        size_ = 0;
        for (std::size_t word = 0; word < words_.size(); ++word) {
            words_[word] &= other.words_[word];
            size_ += static_cast<std::size_t>(std::popcount(words_[word]));
        }
    }
    void unionWith(const InitializationFacts &other) {
        if (!sameUniverse(other)) {
            // Check the entire incoming set before mutating on a domain mismatch.
            other.forEachOffset([&](int offset) {
                if (!index(offset))
                    throw Error("initialization fact requires a validated scalar slot");
            });
            other.forEachOffset([&](int offset) { insert(offset); });
            return;
        }
        size_ = 0;
        for (std::size_t word = 0; word < words_.size(); ++word) {
            words_[word] |= other.words_[word];
            size_ += static_cast<std::size_t>(std::popcount(words_[word]));
        }
    }
    // Only checked dense indices can set bits. Zero construction, removal, AND
    // and OR therefore preserve zero unused bits in the last word, including
    // across copies and moves; no raw offset is ever used as a shift or index.
};
} // namespace aurora::ir::verification
