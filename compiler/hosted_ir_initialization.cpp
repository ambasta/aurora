#include "hosted_ir_initialization.hpp"
#include "../runtime/hosted_bytes.hpp"
#include "hosted_frontend_abi.hpp"
#include <array>
#include <cstdint>
#include <limits>
#include <type_traits>

extern "C" {
void aurora_hosted_initialization_create(const void *, void *) noexcept;
void aurora_hosted_initialization_release(void *) noexcept;
std::int64_t aurora_hosted_initialization_allocated(const void *) noexcept;
std::int64_t aurora_hosted_initialization_status(const void *) noexcept;
std::int64_t aurora_hosted_initialization_initialize(const void *, std::int64_t) noexcept;
std::int64_t aurora_hosted_initialization_load(void *, std::int64_t) noexcept;
std::int64_t aurora_hosted_initialization_retain(void *) noexcept;
std::int64_t aurora_hosted_initialization_join(void *, std::int64_t) noexcept;
std::int64_t aurora_hosted_initialization_current_count(const void *) noexcept;
std::int64_t aurora_hosted_initialization_retained_count_at(const void *, std::int64_t) noexcept;
std::int64_t aurora_hosted_initialization_retained_count(const void *) noexcept;
std::int64_t aurora_hosted_initialization_slot_count(const void *) noexcept;
std::int64_t aurora_hosted_initialization_word_count(const void *) noexcept;
std::int64_t aurora_hosted_initialization_scalar_state(const void *, std::int64_t) noexcept;
std::int64_t aurora_hosted_initialization_write_scalar(const void *, std::int64_t) noexcept;
std::int64_t aurora_hosted_initialization_object_initialized(const void *, std::int64_t) noexcept;
std::int64_t aurora_hosted_initialization_object_pristine(const void *, std::int64_t) noexcept;
std::int64_t aurora_hosted_initialization_mark_object(const void *, std::int64_t) noexcept;
std::int64_t aurora_hosted_initialization_clear_object(const void *, std::int64_t) noexcept;
std::int64_t aurora_hosted_initialization_array_first_missing(const void *, std::int64_t, std::int64_t,
                                                          std::int64_t) noexcept;
std::int64_t aurora_hosted_initialization_clear_array(const void *, std::int64_t, std::int64_t,
                                                  std::int64_t) noexcept;
}

namespace aurora::ir {
namespace {
namespace wire = hosted_abi::compiler_ir_initialization;
namespace bytes = hosted::bytes;
[[noreturn]] void invalidInitialization() {
    throw Error(DiagnosticCode::Internal, "invalid hosted IR initialization workspace");
}
[[noreturn]] void allocationFailure() {
    throw Error(DiagnosticCode::Internal, "hosted IR initialization allocation failed");
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
std::uint64_t checkedProduct(std::uint64_t left, std::uint64_t right) {
    const auto maximum = static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max());
    if (right != 0 && left > maximum / right)
        invalidInitialization();
    return left * right;
}
std::uint64_t checkedSum(std::uint64_t left, std::uint64_t right) {
    const auto maximum = static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max());
    if (left > maximum || right > maximum - left)
        invalidInitialization();
    return left + right;
}
std::uint64_t quota(const Metadata &metadata, Metadata::CallableId callable) {
    if (callable >= metadata.callableCount())
        invalidInitialization();
    const auto slots = metadata.frame(callable).scalarSlots().size();
    if (slots > 65536)
        invalidInitialization();
    const auto words = (slots + 63) / 64;
    const auto snapshot = checkedProduct(words, hosted_abi::initializationWordPairPhysicalBytes);
    const auto retained = checkedProduct(65536, snapshot);
    const auto counts = checkedProduct(65536, hosted_abi::initializationCountPairPhysicalBytes);
    // This is a logical ceiling, not an allocation request. At the largest
    // domain it is 1,074,806,784 bytes (about 1.001 GiB); owners start empty and
    // retained capacity grows 1, 2, 4, ... . Runtime resize stages old and new
    // blocks together outside logical quota (about 1.501 GiB at the extreme).
    return checkedSum(checkedSum(snapshot, retained), counts);
}
static_assert(std::is_standard_layout_v<wire::InitializationWorkspace> &&
              std::is_trivially_copyable_v<wire::InitializationWorkspace>);
static_assert(hosted_abi::initializationWordPairPhysicalBytes == 2 * sizeof(std::uint64_t) &&
              hosted_abi::initializationCountPairPhysicalBytes == 2 * sizeof(std::int64_t));

class SourceOwner final {
    hosted_abi::InitializationRelease release_;

public:
    explicit SourceOwner(std::uint64_t region) {
        release_.region = region;
        hosted_abi::InitializationCreate create;
        create.region = region;
        aurora_hosted_initialization_create(&create, data());
        // Do not check a result here. The completed SourceOwner arms cleanup
        // before Capsule can throw for a refused pool or initialization step.
    }
    ~SourceOwner() {
        aurora_hosted_initialization_release(&release_);
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

class InitializationWorkspace::Capsule final {
public:
    // Declaration order is destruction order in reverse: actual current owners
    // are consumed before Region closes on every ordinary exception. A runtime
    // invariant trap is fail-stop and never unwinds through generated frames.
    bytes::Region region;
    SourceOwner owner;
    const Metadata &metadata;
    const Metadata::CallableId callable;
    const std::array<const void *, 2> roots;

    Capsule(const Metadata &input, Metadata::CallableId id, const void *metadataOwner)
        : region(quota(input, id)), owner(region.id()), metadata(input), callable(id),
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

InitializationWorkspace::InitializationWorkspace(const Metadata &metadata, Metadata::CallableId callable)
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
std::size_t InitializationWorkspace::currentCount() const {
    return capsule_->counted(aurora_hosted_initialization_current_count(capsule_->owner.data()), 131072);
}
std::size_t InitializationWorkspace::retainedCountAt(Id id) const {
    return capsule_->counted(
        aurora_hosted_initialization_retained_count_at(capsule_->owner.data(), argument(id)), 131072);
}
std::size_t InitializationWorkspace::retainedCount() const {
    return capsule_->counted(aurora_hosted_initialization_retained_count(capsule_->owner.data()), 65536);
}
std::size_t InitializationWorkspace::slotCount() const {
    return capsule_->counted(aurora_hosted_initialization_slot_count(capsule_->owner.data()), 65536);
}
std::size_t InitializationWorkspace::wordCount() const {
    return capsule_->counted(aurora_hosted_initialization_word_count(capsule_->owner.data()), 1024);
}
std::size_t InitializationWorkspace::logicalPayloadBytesPerSnapshot() const {
    const auto value = checkedProduct(wordCount(), hosted_abi::initializationWordPairPhysicalBytes);
    if (value > std::numeric_limits<std::size_t>::max())
        invalidInitialization();
    return static_cast<std::size_t>(value);
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
void InitializationWorkspace::markObject(int base) {
    capsule_->succeeded(aurora_hosted_initialization_mark_object(capsule_->roots.data(), base));
}
void InitializationWorkspace::clearObject(int base) {
    capsule_->succeeded(aurora_hosted_initialization_clear_object(capsule_->roots.data(), base));
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
} // namespace aurora::ir
