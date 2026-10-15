#pragma once

#include "hosted_ir_metadata.hpp"
#include <cstddef>
#include <memory>
#include <optional>

namespace aurora::ir {

// One per-function owning capsule. Metadata outlives this immovable workspace;
// every semantic operation borrows that same admitted source owner. The three
// source pools may grow, so no native descriptor, word or payload view is kept.
class InitializationWorkspace final {
public:
    using Id = std::size_t;

    InitializationWorkspace(const Metadata &metadata, Metadata::CallableId callable);
    ~InitializationWorkspace();
    InitializationWorkspace(const InitializationWorkspace &) = delete;
    InitializationWorkspace &operator=(const InitializationWorkspace &) = delete;
    InitializationWorkspace(InitializationWorkspace &&) = delete;
    InitializationWorkspace &operator=(InitializationWorkspace &&) = delete;

    void load(Id id);
    Id retain();
    bool join(Id id);
    std::size_t currentCount() const;
    std::size_t retainedCountAt(Id id) const;
    std::size_t retainedCount() const;
    std::size_t slotCount() const;
    std::size_t wordCount() const;
    std::size_t logicalPayloadBytesPerSnapshot() const;

    // Copied scalar state: must = 1, may = 2. A write returns the previous state.
    unsigned scalarState(int offset);
    unsigned writeScalar(int offset);
    bool objectInitialized(int base);
    bool objectPristine(int base);
    // Whole construction is separate from physical scalar initialization.
    // physical means no logical marker is required, not that the leaves are initialized.
    enum class ObjectCompletion {
        whole,
        physical,
        missing_nested,
        missing_empty
    };
    bool objectWasConstructed(int base);
    ObjectCompletion objectCompletion(int base);
    void markObject(int base);
    void clearObject(int base);
    // A missing element is its forward ordinal; an empty result means complete.
    std::optional<int> arrayFirstMissing(int offset, int length, int width);
    void clearArray(int offset, int length, int width);

private:
    class Capsule;
    std::unique_ptr<Capsule> capsule_;
};

} // namespace aurora::ir
