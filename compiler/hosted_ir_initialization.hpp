#pragma once

#include "hosted_ir_metadata.hpp"
#include "services.hpp"
#include <cstddef>
#include <memory>
#include <optional>

namespace aurora::ir {

// One per-function owning capsule. Metadata outlives this immovable workspace;
// every semantic operation borrows that same admitted source owner. The four
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
    // Source-derived observations preserve vacuous physical completion of
    // leafless fields independently of their logical class completion.
    enum ReceiverFieldFact : unsigned {
        physical_initialized = 1,
        physical_written = 2,
        logical_initialized = 4,
        logical_written = 8
    };
    unsigned receiverFieldState(int field);
    unsigned writeReceiverField(int field);
    enum class ReceiverCompletion {
        complete,
        missing_physical,
        missing_logical
    };
    ReceiverCompletion receiverCompletion();
    bool acquireServiceLoan(int id, int root, service::Kind kind);
    bool releaseServiceLoan(int id, service::Kind kind);
    bool serviceUnsuspended(int root) const;
    enum class ServiceCallState {
        ready,
        missing,
        provenance
    };
    ServiceCallState validateServiceCall(int first,
                                         service::Kind firstKind,
                                         int second = 0,
                                         service::Kind secondKind = service::Kind::Console) const;
    void completeServiceCall(int first, int second = 0);
    bool serviceLoansClosed() const;
    bool sameServiceLoans(Id snapshot) const;
    // A missing element is its forward ordinal; an empty result means complete.
    std::optional<int> arrayFirstMissing(int offset, int length, int width);
    void clearArray(int offset, int length, int width);

private:
    class Capsule;
    std::unique_ptr<Capsule> capsule_;
};

} // namespace aurora::ir
