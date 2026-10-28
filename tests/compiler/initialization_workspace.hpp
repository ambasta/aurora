#pragma once

#include "diagnostics.hpp"
#include "hosted_frontend_abi.hpp"
#include <cstddef>
#include <memory>
#include <optional>
#include <string>

namespace aurora::testing {

using ServiceKind = hosted_abi::compiler_catalog::ServiceKind;
// One callable's metadata read from textual IR by the Aurora reader into a real
// source-created store, which must pass full source metadata admission. facts
// is the fixture's tracked domain size, its retained-pool budget.
class Metadata final {
public:
    static std::unique_ptr<Metadata> read(const std::string &module, std::uint64_t facts);
    ~Metadata();
    Metadata(const Metadata &) = delete;
    Metadata &operator=(const Metadata &) = delete;
    std::size_t callableCount() const noexcept;
    std::uint64_t domainFacts(std::size_t callable) const;

private:
    class State;
    std::unique_ptr<State> state_;
    Metadata(const std::string &module, std::uint64_t facts);
    const void *sourceOwner() const;
    friend class InitializationWorkspace;
};

// Test-only convenience API over the current source VerificationWorkspace. No
// native lattice or service semantics exist here. Metadata outlives the owner;
// the source owns all eleven pools, even when only initialization is exercised.
class InitializationWorkspace final {
public:
    using Id = std::size_t;

    InitializationWorkspace(const Metadata &metadata, std::size_t callable);
    ~InitializationWorkspace();
    InitializationWorkspace(const InitializationWorkspace &) = delete;
    InitializationWorkspace &operator=(const InitializationWorkspace &) = delete;
    InitializationWorkspace(InitializationWorkspace &&) = delete;
    InitializationWorkspace &operator=(InitializationWorkspace &&) = delete;

    void load(Id id);
    Id retain();
    bool join(Id id);
    bool restoreFacts(std::size_t count);
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
    bool acquireServiceLoan(int id, int root, ServiceKind kind);
    bool releaseServiceLoan(int id, ServiceKind kind);
    bool serviceUnsuspended(int root) const;
    enum class ServiceCallState {
        ready,
        missing,
        provenance
    };
    ServiceCallState validateServiceCall(int first,
                                         ServiceKind firstKind,
                                         int second = 0,
                                         ServiceKind secondKind = ServiceKind::Console) const;
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

} // namespace aurora::testing
