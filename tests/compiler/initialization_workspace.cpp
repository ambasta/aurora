#include "initialization_workspace.hpp"
#include "../../runtime/hosted_bytes.hpp"
#include "hosted_frontend_abi.hpp"
#include "initialization_probe_abi.hpp"
#include "ir.hpp"
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
        aurora_test_verification_create(&create, data());
        // Do not check a result here. The completed SourceOwner arms cleanup
        // before Capsule can throw for a refused pool or initialization step.
    }
    ~SourceOwner() {
        aurora_test_verification_release(&release_);
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
// A deliberately narrow raw-fixture encoder. It preserves the existing test
// Module builders, but it neither accesses private production Metadata nor
// decides whether any raw declaration is valid. Full source admission does that.
class MetadataInput final {
    meta::FlagMasks masks{};

    meta::ByteRange text(std::string_view value) {
        const meta::ByteRange range{argument(names.size()), argument(value.size())};
        names.insert(names.end(), value.begin(), value.end());
        return range;
    }
    meta::RawTypeRow type(const Type &value) {
        meta::RawTypeRow row{};
        row.typeKind = static_cast<std::int64_t>(value.kind);
        row.nameRange = text(value.className);
        row.rawTail.elementKind = static_cast<std::int64_t>(value.elementKind);
        row.rawTail.arrayLength = value.length;
        row.rawTail.elementParameterBytes = argument(value.elementParameter.size());
        row.rawTail.lengthParameterBytes = argument(value.lengthParameter.size());
        row.rawTail.templateArgumentCount = argument(value.templateArguments.size());
        return row;
    }
    std::int64_t appendType(const Type &value) {
        const auto position = argument(types.size());
        types.push_back(type(value));
        return position;
    }

public:
    std::vector<unsigned char> names;
    std::vector<meta::RawTypeRow> types;
    std::vector<meta::ClassRow> classes;
    std::vector<meta::FieldRow> fields;
    std::vector<meta::SlotRow> slots;
    meta::CallableRow callable{};
    meta::InputCounts counts{};
    std::uint64_t facts = 0;

    explicit MetadataInput(const ir::Module &module) {
        // Fail closed if a future regression introduces an unencoded input.
        // Do not silently erase it to make metadata admission succeed.
        if (module.functions.size() != 1 || !module.classStorage.empty() || !module.classArrayCarriers.empty() ||
            !module.descriptors.empty() || !module.enumCases.empty() || module.descriptorViews.size() != 1 ||
            !module.descriptorViews.contains(0) || !module.descriptorViews.at(0).empty())
            throw Error("unsupported initialization test metadata fixture shape");
        const auto &function = module.functions.front();
        if (!function.code.empty() || !function.arraySlots.empty() || !function.spanSlots.empty() ||
            !function.regionSlots.empty() || !function.byteSlots.empty() || !function.ownedValueTypes.empty() ||
            function.receiverSpanField)
            throw Error("unsupported initialization test callable fixture shape");
        for (const auto &[name, values] : module.classFields) {
            (void)values;
            if (!module.classLayouts.contains(name))
                throw Error("unsupported initialization test class fixture shape");
        }
        aurora_test_metadata_flag_masks(&masks);
        std::size_t leafCount = 0, fieldCount = 0;
        for (const auto &[name, leaves] : module.classLayouts) {
            (void)name;
            leafCount = count(static_cast<std::int64_t>(checkedSum(leafCount, leaves.size())));
        }
        for (const auto &[name, values] : module.classFields) {
            (void)name;
            fieldCount = count(static_cast<std::int64_t>(checkedSum(fieldCount, values.size())));
        }
        types.resize(count(static_cast<std::int64_t>(checkedSum(leafCount, fieldCount))));
        std::size_t leafPosition = 0;
        for (const auto &[name, leaves] : module.classLayouts) {
            meta::ClassRow row{};
            row.nameRange = text(name);
            row.membershipBits = masks.classLayout;
            row.leafRange = {argument(leafPosition), argument(leaves.size())};
            row.fieldRange = {argument(fields.size()), 0};
            row.suppliedStorage = -1;
            for (const auto &leaf : leaves)
                types.at(leafPosition++) = type(leaf);
            if (const auto found = module.classFields.find(name); found != module.classFields.end()) {
                row.membershipBits |= masks.classFields;
                row.fieldRange.indexCount = argument(found->second.size());
                for (const auto &field : found->second) {
                    const auto typeIndex = leafCount + fields.size();
                    types.at(typeIndex) = type(field.elementType);
                    fields.push_back(
                        {argument(typeIndex), field.firstLeaf, field.length, field.array, field.elementCount});
                }
            }
            classes.push_back(row);
        }
        callable.nameRange = text(function.name);
        callable.typeRange = {argument(types.size()), argument(function.parameters.size() + 1)};
        callable.borrowedRootCount = function.borrowedRootCount;
        callable.firstBorrowedMutable = function.firstBorrowedMutable;
        callable.moduleScope = function.moduleScope;
        callable.frameBytes = function.frameBytes;
        appendType(function.result);
        for (const auto &parameter : function.parameters)
            appendType(parameter);
        using SlotKind = hosted_abi::compiler_lowering::RecordKind;
        for (const auto &[offset, value] : function.slots)
            slots.push_back({static_cast<std::int64_t>(SlotKind::ScalarSlot), offset, appendType(value), 0, 0});
        for (const auto &[offset, value] : function.objectSlots)
            slots.push_back({static_cast<std::int64_t>(SlotKind::ObjectSlot),
                             offset,
                             appendType(Type(value.className)),
                             0,
                             value.mutableValue});
        for (const auto offset : function.serviceSlots)
            slots.push_back({static_cast<std::int64_t>(SlotKind::ServiceSlot), offset, 0, 0, 0});
        callable.slotRange = {0, argument(slots.size())};
        if (function.receiver) {
            const auto &receiver = *function.receiver;
            callable.flags |= masks.callableReceiver;
            callable.receiver.nameRange = text(receiver.className);
            callable.receiver.flags = (receiver.mutableValue ? masks.receiverMutable : 0) |
                                      (receiver.constructor ? masks.receiverConstructor : 0) |
                                      (receiver.publicAccess ? masks.receiverPublic : 0);
        }
        counts.coreCounts.bytes = argument(names.size());
        counts.coreCounts.types = argument(types.size());
        counts.coreCounts.classes = argument(classes.size());
        counts.coreCounts.fields = argument(fields.size());
        counts.coreCounts.leaves = argument(leafCount);
        counts.mapCounts.indices = 1; // The sole callable's independently checked name index.
        counts.mapCounts.views = 1;   // The actual root reflection scope, not an admission claim.
        facts = checkedSum(function.slots.size(), function.objectSlots.size());
        std::string receiverName;
        if (function.borrowedRootCount != 0 && !function.parameters.empty() && function.parameters.front().isClass())
            receiverName = function.parameters.front().className;
        else if (function.receiver)
            receiverName = function.receiver->className;
        if (!receiverName.empty()) {
            const auto explicitFields = module.classFields.find(receiverName);
            const auto leaves = module.classLayouts.find(receiverName);
            if (explicitFields != module.classFields.end())
                facts = checkedSum(facts, explicitFields->second.size());
            else if (leaves != module.classLayouts.end())
                facts = checkedSum(facts, leaves->second.size());
        }
    }
    std::uint64_t quota() const {
        std::uint64_t total = names.size();
        const auto add = [&](std::uint64_t rows, std::uint64_t stride) {
            total = checkedSum(total, checkedProduct(rows, stride));
        };
        add(types.size(), sizeof(meta::RawTypeRow));
        add(classes.size(), sizeof(meta::ClassRow));
        add(checkedSum(fields.size(), count(counts.coreCounts.leaves)), sizeof(meta::FieldRow));
        add(classes.size(), sizeof(meta::StorageRow));
        add(checkedSum(1, checkedSum(fields.size(), checkedProduct(2, count(counts.coreCounts.leaves)))),
            sizeof(meta::IndexRow));
        add(1, sizeof(meta::ViewRow));
        add(1, sizeof(meta::CallableRow));
        add(slots.size(), sizeof(meta::SlotRow));
        add(classes.size(), sizeof(meta::ClassResultRow));
        add(4, sizeof(meta::FrameRow));
        return total;
    }
};

class MetadataSourceOwner final {
    hosted_abi::MetadataRelease release_{};

public:
    explicit MetadataSourceOwner(std::uint64_t region) {
        release_.region = region;
        hosted_abi::MetadataCreate create{};
        create.region = region;
        aurora_test_metadata_create(&create, data());
    }
    ~MetadataSourceOwner() {
        aurora_test_metadata_release(&release_);
    }
    MetadataSourceOwner(const MetadataSourceOwner &) = delete;
    MetadataSourceOwner &operator=(const MetadataSourceOwner &) = delete;
    void *data() {
        return release_.store.storage.data();
    }
    const void *data() const {
        return release_.store.storage.data();
    }
    bytes::NativeOwner descriptor(std::size_t offset) const {
        if (offset > sizeof(release_.store) || sizeof(bytes::NativeOwner) > sizeof(release_.store) - offset)
            invalidInitialization();
        bytes::NativeOwner actual{};
        // Observe a descriptor created by source code. Never synthesize or alter
        // its allocation, generation, region, length or ownership identity.
        std::memcpy(&actual, release_.store.storage.data() + offset, sizeof(actual));
        return actual;
    }
    template <class Row> void set(std::size_t offset, std::size_t at, const Row &row) {
        static_assert(std::is_standard_layout_v<Row> && std::is_trivially_copyable_v<Row>);
        auto actual = descriptor(offset);
        if (bytes::__au_runtime_values_set(&actual, argument(at), sizeof(Row), &row) != 1)
            invalidInitialization();
    }
};
} // namespace

class Metadata::State final {
public:
    const std::uint64_t facts;
    bytes::Region region;
    MetadataSourceOwner owner;

    explicit State(const MetadataInput &input) : facts(input.facts), region(input.quota()), owner(region.id()) {
        hosted_abi::MetadataInitialize initialize{};
        initialize.counts = input.counts;
        initialize.callableCount = 1;
        initialize.slotCount = argument(input.slots.size());
        initialize.instructionBegin = argument(input.types.size());
        if (aurora_test_metadata_initialize(owner.data(), &initialize) != 1 ||
            aurora_test_metadata_allocated(owner.data()) != 1)
            allocationFailure();
        auto names = owner.descriptor(hosted_abi::metadataStore_bytesOffset);
        for (std::size_t at = 0; at < input.names.size(); ++at)
            if (bytes::__au_runtime_bytes_set(&names, argument(at), input.names[at]) != 1)
                invalidInitialization();
        for (std::size_t at = 0; at < input.types.size(); ++at)
            owner.set(hosted_abi::metadataStore_typesOffset, at, input.types[at]);
        for (std::size_t at = 0; at < input.classes.size(); ++at)
            owner.set(hosted_abi::metadataStore_classesOffset, at, input.classes[at]);
        for (std::size_t at = 0; at < input.fields.size(); ++at)
            owner.set(hosted_abi::metadataStore_fieldsOffset, at, input.fields[at]);
        for (std::size_t at = 0; at < input.slots.size(); ++at)
            owner.set(hosted_abi::metadataStore_slotsOffset, at, input.slots[at]);
        owner.set(hosted_abi::metadataStore_callablesOffset, 0, input.callable);
        owner.set(hosted_abi::metadataStore_indicesOffset, 0, meta::IndexRow{0});
        owner.set(hosted_abi::metadataStore_viewsOffset, 0, meta::ViewRow{});
        const auto status = aurora_test_metadata_run(owner.data());
        const auto reason = static_cast<meta::MetadataError>(aurora_test_metadata_error(owner.data()));
        if (status == static_cast<std::int64_t>(meta::MetadataStatus::allocation))
            allocationFailure();
        if (status == static_cast<std::int64_t>(meta::MetadataStatus::invalid)) {
            const auto message = meta::metadataErrorMessage(reason);
            if (reason == meta::MetadataError::none || !message)
                invalidInitialization();
            throw Error(message);
        }
        if (status != static_cast<std::int64_t>(meta::MetadataStatus::success) || reason != meta::MetadataError::none)
            invalidInitialization();
    }
};

Metadata::Metadata(const ir::Module &module) : state_(std::make_unique<State>(MetadataInput(module))) {
}
Metadata::~Metadata() = default;
std::unique_ptr<Metadata> Metadata::import(const ir::Module &module) {
    return std::unique_ptr<Metadata>(new Metadata(module));
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
    return state_->owner.data();
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
        if (aurora_test_initialization_allocated(owner.data()) != 1)
            failure();
        const auto result = aurora_test_initialization_initialize(roots.data(), argument(callable));
        if (result != static_cast<std::int64_t>(wire::InitializationStatus::success))
            failure();
    }
    // Successful semantic operations cross once. Status distinguishes allocation
    // from integrity failure only after an error sentinel or invalid result.
    [[noreturn]] void failure() const {
        if (aurora_test_initialization_status(owner.data()) ==
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
    capsule_->succeeded(aurora_test_initialization_load(capsule_->owner.data(), argument(id)));
}
InitializationWorkspace::Id InitializationWorkspace::retain() {
    return capsule_->counted(aurora_test_initialization_retain(capsule_->owner.data()), 65535);
}
bool InitializationWorkspace::join(Id id) {
    const auto result = aurora_test_initialization_join(capsule_->owner.data(), argument(id));
    if (result == static_cast<std::int64_t>(wire::InitializationJoin::unchanged))
        return false;
    if (result == static_cast<std::int64_t>(wire::InitializationJoin::changed))
        return true;
    capsule_->failure();
}
bool InitializationWorkspace::restoreFacts(std::size_t count) {
    return capsule_->boolean(aurora_test_initialization_restore_facts(capsule_->owner.data(), argument(count)));
}
std::size_t InitializationWorkspace::currentCount() const {
    return capsule_->counted(aurora_test_initialization_current_count(capsule_->owner.data()),
                             static_cast<std::int64_t>(checkedSum(checkedProduct(capsule_->facts, 2), 2)));
}
std::size_t InitializationWorkspace::retainedCountAt(Id id) const {
    return capsule_->counted(aurora_test_initialization_retained_count_at(capsule_->owner.data(), argument(id)),
                             static_cast<std::int64_t>(checkedSum(checkedProduct(capsule_->facts, 2), 2)));
}
std::size_t InitializationWorkspace::retainedCount() const {
    return capsule_->counted(aurora_test_initialization_retained_count(capsule_->owner.data()), 65536);
}
std::size_t InitializationWorkspace::slotCount() const {
    return capsule_->counted(aurora_test_initialization_slot_count(capsule_->owner.data()), 65536);
}
std::size_t InitializationWorkspace::wordCount() const {
    return capsule_->counted(aurora_test_initialization_word_count(capsule_->owner.data()),
                             static_cast<std::int64_t>(capsule_->facts / 64 + (capsule_->facts % 64 != 0)));
}
std::size_t InitializationWorkspace::logicalPayloadBytesPerSnapshot() const {
    return capsule_->counted(aurora_test_initialization_payload_bytes(capsule_->owner.data()),
                             static_cast<std::int64_t>(snapshotBytes(capsule_->facts)));
}
bool InitializationWorkspace::acquireServiceLoan(int id, int root, service::Kind kind) {
    return capsule_->boolean(aurora_test_initialization_acquire_service_loan(
        capsule_->owner.data(), id, root, static_cast<std::int64_t>(kind)));
}
bool InitializationWorkspace::releaseServiceLoan(int id, service::Kind kind) {
    return capsule_->boolean(
        aurora_test_initialization_release_service_loan(capsule_->owner.data(), id, static_cast<std::int64_t>(kind)));
}
bool InitializationWorkspace::serviceUnsuspended(int root) const {
    return capsule_->boolean(aurora_test_initialization_service_unsuspended(capsule_->owner.data(), root));
}
InitializationWorkspace::ServiceCallState InitializationWorkspace::validateServiceCall(int first,
                                                                                       service::Kind firstKind,
                                                                                       int second,
                                                                                       service::Kind secondKind) const {
    switch (static_cast<wire::ServiceCallState>(
        aurora_test_initialization_validate_service_call(capsule_->owner.data(),
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
    capsule_->succeeded(aurora_test_initialization_complete_service_call(capsule_->owner.data(), first, second));
}
bool InitializationWorkspace::serviceLoansClosed() const {
    return capsule_->boolean(aurora_test_initialization_service_loans_closed(capsule_->owner.data()));
}
bool InitializationWorkspace::sameServiceLoans(Id snapshot) const {
    return capsule_->boolean(aurora_test_initialization_same_service_loans(capsule_->owner.data(), argument(snapshot)));
}
unsigned InitializationWorkspace::scalarState(int offset) {
    return capsule_->scalar(aurora_test_initialization_scalar_state(capsule_->roots.data(), offset));
}
unsigned InitializationWorkspace::writeScalar(int offset) {
    return capsule_->scalar(aurora_test_initialization_write_scalar(capsule_->roots.data(), offset));
}
bool InitializationWorkspace::objectInitialized(int base) {
    return capsule_->boolean(aurora_test_initialization_object_initialized(capsule_->roots.data(), base));
}
bool InitializationWorkspace::objectPristine(int base) {
    return capsule_->boolean(aurora_test_initialization_object_pristine(capsule_->roots.data(), base));
}
bool InitializationWorkspace::objectWasConstructed(int base) {
    return capsule_->boolean(aurora_test_initialization_object_was_constructed(capsule_->roots.data(), base));
}
InitializationWorkspace::ObjectCompletion InitializationWorkspace::objectCompletion(int base) {
    switch (static_cast<wire::ObjectCompletion>(
        aurora_test_initialization_object_completion(capsule_->roots.data(), base))) {
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
    capsule_->succeeded(aurora_test_initialization_mark_object(capsule_->roots.data(), base));
}
void InitializationWorkspace::clearObject(int base) {
    capsule_->succeeded(aurora_test_initialization_clear_object(capsule_->roots.data(), base));
}
unsigned InitializationWorkspace::receiverFieldState(int field) {
    return static_cast<unsigned>(
        capsule_->counted(aurora_test_initialization_receiver_field_state(capsule_->roots.data(), field), 15));
}
unsigned InitializationWorkspace::writeReceiverField(int field) {
    return static_cast<unsigned>(
        capsule_->counted(aurora_test_initialization_write_receiver_field(capsule_->roots.data(), field), 15));
}
InitializationWorkspace::ReceiverCompletion InitializationWorkspace::receiverCompletion() {
    switch (
        static_cast<wire::ReceiverCompletion>(aurora_test_initialization_receiver_completion(capsule_->roots.data()))) {
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
    const auto result = aurora_test_initialization_array_first_missing(capsule_->roots.data(), offset, length, width);
    if (result == -1)
        return std::nullopt;
    if (result < 0 || result >= length || result > std::numeric_limits<int>::max())
        capsule_->failure();
    return static_cast<int>(result);
}
void InitializationWorkspace::clearArray(int offset, int length, int width) {
    capsule_->succeeded(aurora_test_initialization_clear_array(capsule_->roots.data(), offset, length, width));
}
} // namespace aurora::testing
