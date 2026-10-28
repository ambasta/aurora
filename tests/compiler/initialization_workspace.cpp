#include "initialization_workspace.hpp"
#include "../../runtime/hosted_bytes.hpp"
#include <array>
#include <cstdint>
#include <cstring>
#include <string_view>
#include <vector>
#include <limits>
#include <type_traits>

namespace aurora::testing {
namespace {
namespace wire = hosted_abi::compiler_ir_verification;
namespace bytes = hosted::bytes;
[[noreturn]] void invalidInitialization() {
    throw Error(DiagnosticCode::Internal, "invalid test source verification initialization workspace");
}
[[noreturn]] void allocationFailure() {
    throw Error(DiagnosticCode::Internal, "test source verification initialization allocation failed");
}
std::int64_t argument(std::size_t value) {
    if (value > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()))
        invalidInitialization();
    return static_cast<std::int64_t>(value);
}
std::size_t count(std::int64_t value) {
    if (value < 0 || static_cast<std::uint64_t>(value) > std::numeric_limits<std::size_t>::max())
        invalidInitialization();
    return static_cast<std::size_t>(value);
}
constexpr std::uint64_t checkedProduct(std::uint64_t left, std::uint64_t right) {
    const auto maximum = static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max());
    if (right != 0 && left > maximum / right)
        invalidInitialization();
    return left * right;
}
constexpr std::uint64_t checkedSum(std::uint64_t left, std::uint64_t right) {
    const auto maximum = static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max());
    if (left > maximum || right > maximum - left)
        invalidInitialization();
    return left + right;
}
constexpr std::uint64_t snapshotBytes(std::uint64_t facts) {
    const auto words = facts / 64 + (facts % 64 != 0);
    return checkedSum(checkedProduct(words, hosted_abi::verificationWordPairPhysicalBytes),
                      checkedProduct(2, hosted_abi::verificationServiceLoanPhysicalBytes));
}
// This independent allocation backstop bounds retained pools; Aurora admission caps direct fields.
constexpr std::uint64_t maximumWorkspacePayload = 1209026560;
static_assert(maximumWorkspacePayload == 65537ULL * 1152 * 16 + 65536ULL * 16);
constexpr std::uint64_t quota(std::uint64_t facts) {
    const auto snapshot = snapshotBytes(facts);
    const auto retained = checkedProduct(65536, snapshot);
    const auto counts = checkedProduct(65536, hosted_abi::verificationCountPairPhysicalBytes);
    // Owners start empty; the existing region refuses growth above this grant.
    // Two service rows are a ceiling, not a native inventory or allocation request.
    const auto requested = checkedSum(checkedSum(snapshot, retained), counts);
    return requested < maximumWorkspacePayload ? requested : maximumWorkspacePayload;
}
static_assert(quota(0) == 5242944);
static_assert(quota(73408) == maximumWorkspacePayload - 65537ULL * 16);
static_assert(quota(73409) == maximumWorkspacePayload);
static_assert(quota(73729) == maximumWorkspacePayload);
static_assert(std::is_standard_layout_v<wire::VerificationWorkspace> &&
              std::is_trivially_copyable_v<wire::VerificationWorkspace>);
static_assert(hosted_abi::verificationWordPairPhysicalBytes == 2 * sizeof(std::uint64_t) &&
              hosted_abi::verificationCountPairPhysicalBytes == 2 * sizeof(std::int64_t) &&
              hosted_abi::verificationServiceLoanPhysicalBytes == 4 * sizeof(std::int64_t));

class SourceOwner final {
    hosted_abi::VerificationRelease release_{};

public:
    explicit SourceOwner(std::uint64_t region) {
        release_.region = region;
        hosted_abi::VerificationCreate create{};
        create.region = region;
        aurora_hosted_verification_create(&create, data());
        // Do not check a result here. The completed SourceOwner arms cleanup
        // before Capsule can throw for a refused pool or initialization step.
    }
    ~SourceOwner() {
        aurora_hosted_verification_release(&release_);
    }
    SourceOwner(const SourceOwner &) = delete;
    SourceOwner &operator=(const SourceOwner &) = delete;
    void *data() {
        return release_.workspace.storage.data();
    }
    const void *data() const {
        return release_.workspace.storage.data();
    }
};
} // namespace

namespace {
namespace meta = hosted_abi::compiler_ir_metadata;
constexpr std::uint64_t metadataQuota = std::uint64_t{1} << 30;
} // namespace

// The Aurora textual IR reader fills the pending store; full source metadata
// admission decides whether the fixture is valid.
// The read store, released before its Region closes, also when admission throws.
class MetadataOwner final {
public:
    hosted_abi::MetadataRelease owner{};
    bool live = false;
    explicit MetadataOwner(std::uint64_t region) {
        owner.region = region;
    }
    ~MetadataOwner() {
        if (live)
            aurora_hosted_metadata_release(&owner);
    }
    MetadataOwner(const MetadataOwner &) = delete;
    MetadataOwner &operator=(const MetadataOwner &) = delete;
};

class Metadata::State final {
public:
    const std::uint64_t facts;
    bytes::Region region;
    MetadataOwner store;
    hosted_abi::MetadataRelease &owner = store.owner;

    State(const std::string &module, std::uint64_t domain) : facts(domain), region(metadataQuota), store(region.id()) {
        hosted_abi::AirRelease reader{};
        reader.region = region.id();
        hosted_abi::AirStart start{};
        start.region = region.id();
        aurora_hosted_air_start(&start, reader.reader.storage.data());
        hosted_abi::AirRead text{};
        text.source.backing = module.data();
        text.source.length = argument(module.size());
        if (aurora_hosted_air_read(reader.reader.storage.data(), &text) != 1) {
            aurora_hosted_air_release(&reader);
            throw Error("unreadable initialization test metadata fixture");
        }
        hosted_abi::AirMetadata input{};
        input.region = region.id();
        input.reader = reader.reader;
        aurora_hosted_air_metadata(&input, owner.store.storage.data());
        store.live = true;
        if (aurora_hosted_metadata_allocated(owner.store.storage.data()) != 1)
            allocationFailure();
        const auto status = aurora_hosted_metadata_run(owner.store.storage.data());
        const auto reason = static_cast<meta::MetadataError>(aurora_hosted_metadata_error(owner.store.storage.data()));
        if (status == static_cast<std::int64_t>(meta::MetadataStatus::allocation))
            allocationFailure();
        if (status != static_cast<std::int64_t>(meta::MetadataStatus::success) || reason != meta::MetadataError::none)
            invalidInitialization();
    }
    State(const State &) = delete;
    State &operator=(const State &) = delete;
};

Metadata::Metadata(const std::string &module, std::uint64_t facts) : state_(std::make_unique<State>(module, facts)) {
}
Metadata::~Metadata() = default;
std::unique_ptr<Metadata> Metadata::read(const std::string &module, std::uint64_t facts) {
    return std::unique_ptr<Metadata>(new Metadata(module, facts));
}
std::size_t Metadata::callableCount() const noexcept {
    return 1;
}
std::uint64_t Metadata::domainFacts(std::size_t callable) const {
    if (callable >= callableCount())
        invalidInitialization();
    return state_->facts;
}
const void *Metadata::sourceOwner() const {
    return state_->owner.store.storage.data();
}

class InitializationWorkspace::Capsule final {
public:
    // Declaration order is destruction order in reverse: actual current owners
    // are consumed before Region closes on every ordinary exception. A runtime
    // invariant trap is fail-stop and never unwinds through generated frames.
    const std::uint64_t facts;
    bytes::Region region;
    SourceOwner owner;
    const Metadata &metadata;
    const std::size_t callable;
    const std::array<const void *, 2> roots;

    Capsule(const Metadata &input, std::size_t id, const void *metadataOwner)
        : facts(input.domainFacts(id)), region(quota(facts)), owner(region.id()), metadata(input), callable(id),
          roots{owner.data(), metadataOwner} {
        if (aurora_hosted_initialization_allocated(owner.data()) != 1)
            failure();
        const auto result = aurora_hosted_initialization_initialize(roots.data(), argument(callable));
        if (result != static_cast<std::int64_t>(wire::InitializationStatus::success))
            failure();
    }
    // Successful semantic operations cross once. Status distinguishes allocation
    // from integrity failure only after an error sentinel or invalid result.
    [[noreturn]] void failure() const {
        if (aurora_hosted_initialization_status(owner.data()) ==
            static_cast<std::int64_t>(wire::InitializationStatus::allocation))
            allocationFailure();
        invalidInitialization();
    }
    bool boolean(std::int64_t value) const {
        if (value != 0 && value != 1)
            failure();
        return value == 1;
    }
    void succeeded(std::int64_t value) const {
        if (value != 1)
            failure();
    }
    // Retain result bounds before host conversion, including error sentinels and observation bits.
    std::size_t counted(std::int64_t value, std::int64_t maximum) const {
        if (value < 0 || value > maximum)
            failure();
        return count(value);
    }
    unsigned scalar(std::int64_t value) const {
        if (value < 0 || value > 3 || value == 1)
            failure();
        return static_cast<unsigned>(value);
    }
};

InitializationWorkspace::InitializationWorkspace(const Metadata &metadata, std::size_t callable)
    : capsule_(std::make_unique<Capsule>(metadata, callable, metadata.sourceOwner())) {
}
InitializationWorkspace::~InitializationWorkspace() = default;
void InitializationWorkspace::load(Id id) {
    capsule_->succeeded(aurora_hosted_initialization_load(capsule_->owner.data(), argument(id)));
}
InitializationWorkspace::Id InitializationWorkspace::retain() {
    return capsule_->counted(aurora_hosted_initialization_retain(capsule_->owner.data()), 65535);
}
bool InitializationWorkspace::join(Id id) {
    const auto result = aurora_hosted_initialization_join(capsule_->owner.data(), argument(id));
    if (result == static_cast<std::int64_t>(wire::InitializationJoin::unchanged))
        return false;
    if (result == static_cast<std::int64_t>(wire::InitializationJoin::changed))
        return true;
    capsule_->failure();
}
bool InitializationWorkspace::restoreFacts(std::size_t count) {
    return capsule_->boolean(aurora_hosted_initialization_restore_facts(capsule_->owner.data(), argument(count)));
}
std::size_t InitializationWorkspace::currentCount() const {
    return capsule_->counted(aurora_hosted_initialization_current_count(capsule_->owner.data()),
                             static_cast<std::int64_t>(checkedSum(checkedProduct(capsule_->facts, 2), 2)));
}
std::size_t InitializationWorkspace::retainedCountAt(Id id) const {
    return capsule_->counted(aurora_hosted_initialization_retained_count_at(capsule_->owner.data(), argument(id)),
                             static_cast<std::int64_t>(checkedSum(checkedProduct(capsule_->facts, 2), 2)));
}
std::size_t InitializationWorkspace::retainedCount() const {
    return capsule_->counted(aurora_hosted_initialization_retained_count(capsule_->owner.data()), 65536);
}
std::size_t InitializationWorkspace::slotCount() const {
    return capsule_->counted(aurora_hosted_initialization_slot_count(capsule_->owner.data()), 65536);
}
std::size_t InitializationWorkspace::wordCount() const {
    return capsule_->counted(aurora_hosted_initialization_word_count(capsule_->owner.data()),
                             static_cast<std::int64_t>(capsule_->facts / 64 + (capsule_->facts % 64 != 0)));
}
std::size_t InitializationWorkspace::logicalPayloadBytesPerSnapshot() const {
    return capsule_->counted(aurora_hosted_initialization_payload_bytes(capsule_->owner.data()),
                             static_cast<std::int64_t>(snapshotBytes(capsule_->facts)));
}
bool InitializationWorkspace::acquireServiceLoan(int id, int root, ServiceKind kind) {
    return capsule_->boolean(aurora_hosted_initialization_acquire_service_loan(
        capsule_->owner.data(), id, root, static_cast<std::int64_t>(kind)));
}
bool InitializationWorkspace::releaseServiceLoan(int id, ServiceKind kind) {
    return capsule_->boolean(
        aurora_hosted_initialization_release_service_loan(capsule_->owner.data(), id, static_cast<std::int64_t>(kind)));
}
bool InitializationWorkspace::serviceUnsuspended(int root) const {
    return capsule_->boolean(aurora_hosted_initialization_service_unsuspended(capsule_->owner.data(), root));
}
InitializationWorkspace::ServiceCallState InitializationWorkspace::validateServiceCall(int first,
                                                                                       ServiceKind firstKind,
                                                                                       int second,
                                                                                       ServiceKind secondKind) const {
    switch (static_cast<wire::ServiceCallState>(
        aurora_hosted_initialization_validate_service_call(capsule_->owner.data(),
                                                           first,
                                                           static_cast<std::int64_t>(firstKind),
                                                           second,
                                                           static_cast<std::int64_t>(secondKind)))) {
    case wire::ServiceCallState::ready:
        return ServiceCallState::ready;
    case wire::ServiceCallState::missing:
        return ServiceCallState::missing;
    case wire::ServiceCallState::provenance:
        return ServiceCallState::provenance;
    default:
        capsule_->failure();
    }
}
void InitializationWorkspace::completeServiceCall(int first, int second) {
    capsule_->succeeded(aurora_hosted_initialization_complete_service_call(capsule_->owner.data(), first, second));
}
bool InitializationWorkspace::serviceLoansClosed() const {
    return capsule_->boolean(aurora_hosted_initialization_service_loans_closed(capsule_->owner.data()));
}
bool InitializationWorkspace::sameServiceLoans(Id snapshot) const {
    return capsule_->boolean(
        aurora_hosted_initialization_same_service_loans(capsule_->owner.data(), argument(snapshot)));
}
unsigned InitializationWorkspace::scalarState(int offset) {
    return capsule_->scalar(aurora_hosted_initialization_scalar_state(capsule_->roots.data(), offset));
}
unsigned InitializationWorkspace::writeScalar(int offset) {
    return capsule_->scalar(aurora_hosted_initialization_write_scalar(capsule_->roots.data(), offset));
}
bool InitializationWorkspace::objectInitialized(int base) {
    return capsule_->boolean(aurora_hosted_initialization_object_initialized(capsule_->roots.data(), base));
}
bool InitializationWorkspace::objectPristine(int base) {
    return capsule_->boolean(aurora_hosted_initialization_object_pristine(capsule_->roots.data(), base));
}
bool InitializationWorkspace::objectWasConstructed(int base) {
    return capsule_->boolean(aurora_hosted_initialization_object_was_constructed(capsule_->roots.data(), base));
}
InitializationWorkspace::ObjectCompletion InitializationWorkspace::objectCompletion(int base) {
    switch (static_cast<wire::ObjectCompletion>(
        aurora_hosted_initialization_object_completion(capsule_->roots.data(), base))) {
    case wire::ObjectCompletion::whole:
        return ObjectCompletion::whole;
    case wire::ObjectCompletion::physical:
        return ObjectCompletion::physical;
    case wire::ObjectCompletion::missing_nested:
        return ObjectCompletion::missing_nested;
    case wire::ObjectCompletion::missing_empty:
        return ObjectCompletion::missing_empty;
    default:
        capsule_->failure();
    }
}
void InitializationWorkspace::markObject(int base) {
    capsule_->succeeded(aurora_hosted_initialization_mark_object(capsule_->roots.data(), base));
}
void InitializationWorkspace::clearObject(int base) {
    capsule_->succeeded(aurora_hosted_initialization_clear_object(capsule_->roots.data(), base));
}
unsigned InitializationWorkspace::receiverFieldState(int field) {
    return static_cast<unsigned>(
        capsule_->counted(aurora_hosted_initialization_receiver_field_state(capsule_->roots.data(), field), 15));
}
unsigned InitializationWorkspace::writeReceiverField(int field) {
    return static_cast<unsigned>(
        capsule_->counted(aurora_hosted_initialization_write_receiver_field(capsule_->roots.data(), field), 15));
}
InitializationWorkspace::ReceiverCompletion InitializationWorkspace::receiverCompletion() {
    switch (static_cast<wire::ReceiverCompletion>(
        aurora_hosted_initialization_receiver_completion(capsule_->roots.data()))) {
    case wire::ReceiverCompletion::complete:
        return ReceiverCompletion::complete;
    case wire::ReceiverCompletion::missing_physical:
        return ReceiverCompletion::missing_physical;
    case wire::ReceiverCompletion::missing_logical:
        return ReceiverCompletion::missing_logical;
    default:
        capsule_->failure();
    }
}
std::optional<int> InitializationWorkspace::arrayFirstMissing(int offset, int length, int width) {
    const auto result = aurora_hosted_initialization_array_first_missing(capsule_->roots.data(), offset, length, width);
    if (result == -1)
        return std::nullopt;
    if (result < 0 || result >= length || result > std::numeric_limits<int>::max())
        capsule_->failure();
    return static_cast<int>(result);
}
void InitializationWorkspace::clearArray(int offset, int length, int width) {
    capsule_->succeeded(aurora_hosted_initialization_clear_array(capsule_->roots.data(), offset, length, width));
}
} // namespace aurora::testing
