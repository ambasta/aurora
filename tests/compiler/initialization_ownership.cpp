// Current source workspace ownership coverage, separated from the parser graph.
// This fixture links only the test-only initialization source root and runtime.
#include "hosted_frontend_abi.hpp"
#include "../../runtime/hosted_bytes.hpp"
#include <array>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>

namespace {
constexpr std::uint64_t canary = 0xa3159f274c86be02ULL;
std::size_t cases = 0;
std::string context;
void require(bool value, const std::string &message) {
    if (!value)
        throw std::runtime_error(context + ": " + message);
}
class Allocations {
public:
    std::size_t allowed = std::numeric_limits<std::size_t>::max(), successful = 0, released = 0, attempted = 0;
    std::array<void *, 12> initialOwners{}, releasedOwners{};
    static void *allocate(void *context, std::size_t bytes) noexcept {
        auto &state = *static_cast<Allocations *>(context);
        ++state.attempted;
        auto *result = state.successful < state.allowed ? std::malloc(bytes) : nullptr;
        if (state.attempted <= state.initialOwners.size())
            state.initialOwners[state.attempted - 1] = result;
        if (result)
            ++state.successful;
        return result;
    }
    static void deallocate(void *context, void *address) noexcept {
        auto &state = *static_cast<Allocations *>(context);
        if (state.released < state.releasedOwners.size())
            state.releasedOwners[state.released] = address;
        ++state.released;
        std::free(address);
    }
    aurora::hosted::bytes::Allocator allocator() {
        return {this, allocate, deallocate};
    }
};
void createMetadata(std::uint64_t region, const aurora::hosted_abi::MetadataInitialize &input, void *store) {
    aurora::hosted_abi::MetadataCreate create{};
    create.region = region;
    aurora_hosted_metadata_create(&create, store);
    aurora_hosted_metadata_initialize(store, &input);
}

void rawVerificationOwnership(bool serviceSignature) {
    namespace abi = aurora::hosted_abi;
    namespace meta = abi::compiler_ir_metadata;
    namespace wire = abi::compiler_ir_verification;
    namespace bytes = aurora::hosted::bytes;
    context = "twelve-owner verification creation, initialization growth prefixes and exception cleanup";
    context += serviceSignature ? " with service signature" : " without service signature";
    static_assert(sizeof(wire::VerificationWorkspace) == 520 && sizeof(abi::VerificationRelease) == 528 &&
                  sizeof(wire::VerificationReport) == 72 && sizeof(wire::VerificationError) == 16);
    const std::int64_t parameterCount = serviceSignature ? 1 : 0;
    bytes::Region metadataRegion(1048576);
    struct MetadataOwner {
        abi::MetadataRelease value{};
        ~MetadataOwner() {
            aurora_hosted_metadata_release(&value);
        }
    } metadata;
    metadata.value.region = metadataRegion.id();
    abi::MetadataInitialize create{};
    create.counts.coreCounts.bytes = 8;
    create.counts.coreCounts.types = 66 + parameterCount;
    create.counts.mapCounts.indices = 1;
    create.counts.mapCounts.views = 1;
    create.callableCount = 1;
    create.slotCount = 65;
    create.instructionBegin = 66 + parameterCount;
    auto *declarations = metadata.value.store.storage.data();
    createMetadata(metadataRegion.id(), create, declarations);
    require(aurora_hosted_metadata_allocated(declarations) == 1, "initialization metadata fixture allocation failed");
    const auto descriptor = [&](std::size_t offset) {
        bytes::NativeOwner result;
        std::memcpy(&result, declarations + offset, sizeof(result));
        return result;
    };
    const auto set = [&](std::size_t pool, std::int64_t at, const auto &row) {
        auto owner = descriptor(pool);
        require(bytes::__au_runtime_values_set(&owner, at, sizeof(row), &row) == 1,
                "initialization fixture escaped metadata row storage");
    };
    auto names = descriptor(abi::metadataStore_bytesOffset);
    const std::array<std::uint8_t, 8> nameBytes{'f', 0x80, 0xff, 'a', 'a', 'b', 'a', 'b'};
    for (std::size_t at = 0; at < nameBytes.size(); ++at)
        require(bytes::__au_runtime_bytes_set(&names, at, nameBytes[at]) == 1,
                "initialization name comparison fixture write failed");
    set(abi::metadataStore_typesOffset, 0, meta::RawTypeRow{});
    if (serviceSignature) {
        meta::RawTypeRow service{};
        service.typeKind = static_cast<std::int64_t>(meta::MetadataTypeKind::ConsoleSession);
        set(abi::metadataStore_typesOffset, 1, service);
    }
    meta::RawTypeRow byte{};
    byte.typeKind = static_cast<std::int64_t>(meta::MetadataTypeKind::U8);
    for (std::int64_t at = 0; at < 65; ++at)
        set(abi::metadataStore_typesOffset, at + 1 + parameterCount, byte);
    meta::CallableRow callable{};
    callable.nameRange = {0, 1};
    callable.typeRange = {0, 1 + parameterCount};
    callable.frameBytes = 80;
    callable.slotRange = {0, 65};
    set(abi::metadataStore_callablesOffset, 0, callable);
    for (std::int64_t at = 0; at < 65; ++at)
        set(abi::metadataStore_slotsOffset,
            at,
            meta::SlotRow{static_cast<std::int64_t>(abi::compiler_lowering::RecordKind::ScalarSlot),
                          at + 1,
                          at + 1 + parameterCount,
                          0,
                          0});
    set(abi::metadataStore_indicesOffset, 0, meta::IndexRow{0});
    set(abi::metadataStore_viewsOffset, 0, meta::ViewRow{});
    require(aurora_hosted_metadata_run(declarations) == static_cast<std::int64_t>(meta::MetadataStatus::success),
            "initialization fixture metadata did not admit");

    std::size_t successful = 0, partialKeyFailures = 0;
    const auto exercise = [&](std::size_t allowed,
                              std::uint64_t quota,
                              int stop,
                              std::int64_t expectedPublished = -1,
                              bool dynamic = false,
                              std::uint64_t expectedUsed = std::numeric_limits<std::uint64_t>::max()) {
        Allocations allocations;
        allocations.allowed = allowed;
        bytes::Region region(quota, allocations.allocator());
        std::int64_t published = 0;
        bool completed = false, caught = false, releasedIntact = false;
        try {
            struct Owner {
                std::uint64_t before = canary;
                abi::VerificationRelease value{};
                std::uint64_t after = canary;
                bool &releasedIntact;
                Owner(std::uint64_t region, bool &intact) : releasedIntact(intact) {
                    value.region = region;
                    abi::VerificationCreate input{};
                    input.region = region;
                    aurora_hosted_verification_create(&input, value.workspace.storage.data());
                }
                ~Owner() {
                    aurora_hosted_verification_release(&value);
                    releasedIntact = before == canary && after == canary;
                }
            } owner(region.id(), releasedIntact);
            auto *workspace = owner.value.workspace.storage.data();
            // The test-only probe borrows the real generated workspace. It exposes
            // no production initialization entry or host semantic authority.
            if (aurora_hosted_initialization_allocated(workspace) == 1)
                require(allocations.successful == 12 && region.metrics().live_allocations == 12,
                        "verification creation did not retain twelve distinct source owners");
            if (allowed < 12)
                require(allocations.attempted == 12 && allocations.successful == allowed,
                        "failed initial verification owner skipped a declared allocation");
            const std::array<const void *, 2> roots{workspace, declarations};
            const auto status = aurora_hosted_initialization_initialize(roots.data(), 0);
            if (status == static_cast<std::int64_t>(wire::InitializationStatus::success)) {
                // Same real admitted metadata owner; cover ordered high-bit bytes,
                // overlapping windows and the unchanged malformed-range sentinel.
                for (const auto &test : std::array<std::array<std::int64_t, 4>, 12>{{{0, 0, 8, 0},
                                                                                     {1, 2, 1, -1},
                                                                                     {1, 0, 1, 1},
                                                                                     {3, 4, 2, -1},
                                                                                     {4, 3, 2, 1},
                                                                                     {4, 6, 2, 0},
                                                                                     {-1, 0, 1, -1},
                                                                                     {-1, -2, 1, 0},
                                                                                     {8, 9, 2, 0},
                                                                                     {7, 5, 2, -1},
                                                                                     {-1, 100, 0, 0},
                                                                                     {1, 2, -1, 0}}})
                    require(aurora_hosted_initialization_compare_metadata_bytes(
                                roots.data(), test[0], test[1], test[2]) == test[3],
                            "metadata byte comparison boundary/sentinel changed");

                require(aurora_hosted_initialization_word_count(workspace) == 2 &&
                            aurora_hosted_initialization_payload_bytes(workspace) == (serviceSignature ? 64 : 32) &&
                            aurora_hosted_initialization_write_scalar(roots.data(), 64) == 0 &&
                            aurora_hosted_initialization_write_scalar(roots.data(), 65) == 0,
                        "word-boundary seed failed before retention");
                if (dynamic) {
                    completed = aurora_hosted_initialization_restore_facts(workspace, 33) == 1;
                    published = aurora_hosted_initialization_retained_count(workspace);
                    require(published == (completed ? 2 : -1),
                            "dynamic restore lost its real retained count or terminal state");
                } else {
                    while (published < 130) {
                        const auto retained = aurora_hosted_initialization_retain(workspace);
                        if (retained == -1)
                            break;
                        require(retained == published++, "failed resize published a partial ordinal");
                    }
                    completed = published == 130;
                }
                if (completed) {
                    require(aurora_hosted_initialization_load(workspace, 0) == 1 &&
                                aurora_hosted_initialization_current_count(workspace) == 4 &&
                                aurora_hosted_initialization_retained_count_at(workspace, dynamic ? 1 : 129) == 4,
                            "owner relocation lost an early row, high-bit fact or cached count");
                    if (stop == 1) {
                        require(aurora_hosted_initialization_load(workspace, published) == 0 &&
                                    aurora_hosted_initialization_status(workspace) ==
                                        static_cast<std::int64_t>(wire::InitializationStatus::invalid),
                                "invalid retained ordinal did not enter terminal failure");
                    } else if (stop == 2)
                        throw std::runtime_error("injected native exception after retention");
                }
            }
            if (dynamic && !completed) {
                bytes::NativeOwner facts{}, keys{};
                std::memcpy(&facts, workspace + abi::verificationWorkspace_currentFactsOffset, sizeof(facts));
                std::memcpy(&keys, workspace + abi::verificationWorkspace_currentKeysOffset, sizeof(keys));
                if (facts.success == 1 && keys.success == 1 &&
                    facts.length / abi::verificationActiveFactPhysicalBytes >
                        keys.length / abi::verificationFactKeyPhysicalBytes) {
                    require(facts.length % abi::verificationActiveFactPhysicalBytes == 0 &&
                                keys.length % abi::verificationFactKeyPhysicalBytes == 0,
                            "partial key resize left an invalid physical owner extent");
                    ++partialKeyFailures;
                }
            }
            if (!completed || stop == 1) {
                const auto attempts = allocations.attempted;
                require(aurora_hosted_initialization_retain(workspace) == -1 &&
                            aurora_hosted_initialization_load(workspace, 0) == 0 &&
                            aurora_hosted_initialization_join(workspace, 0) ==
                                static_cast<std::int64_t>(wire::InitializationJoin::error) &&
                            aurora_hosted_initialization_retained_count(workspace) == -1 &&
                            allocations.attempted == attempts,
                        "terminal owner retried allocation, revived a row or changed its published count");
                if (!completed)
                    require(aurora_hosted_initialization_status(workspace) ==
                                static_cast<std::int64_t>(wire::InitializationStatus::allocation),
                            "initial or partial-growth allocation failure lost its reason");
                struct Report {
                    std::uint64_t before = canary;
                    wire::VerificationReport value{};
                    std::uint64_t after = canary;
                } report;
                aurora_hosted_verification_report(workspace, &report.value);
                require(
                    report.before == canary && report.after == canary &&
                        report.value.statusValue ==
                            (completed ? wire::VerificationStatus::invalid : wire::VerificationStatus::allocation) &&
                        report.value.errorValue.firstValue == (completed ? wire::VerificationErrorFirst::internal
                                                                         : wire::VerificationErrorFirst::allocation) &&
                        report.value.errorValue.secondValue == wire::VerificationErrorSecond::none &&
                        report.value.metricsStarted == 0 && report.value.metricsValue.snapshotsValue == 0 &&
                        report.value.metricsValue.peakOperandDepth == 0 &&
                        report.value.metricsValue.peakRetainedOperandFacts == 0 &&
                        report.value.metricsValue.peakRetainedValueFacts == 0 &&
                        report.value.metricsValue.peakRetainedInitializationPayloadBytes == 0,
                    "failed verification owner lost its terminal report or escaped the copied report extent");
            }
            if (expectedUsed != std::numeric_limits<std::uint64_t>::max())
                require(region.metrics().used == expectedUsed,
                        "control-row quota boundary charged the wrong live payload before release");
            require(owner.before == canary && owner.after == canary, "verification owner escaped generated extent");
        } catch (const std::runtime_error &error) {
            caught = std::string(error.what()) == "injected native exception after retention";
            require(caught && stop == 2, "unexpected native exception in owner sweep");
        }
        if (allowed == std::numeric_limits<std::size_t>::max() && quota != 0 && expectedPublished < 0 &&
            expectedUsed == std::numeric_limits<std::uint64_t>::max()) {
            require(completed && caught == (stop == 2), "successful owner did not reach its requested stop");
            successful = allocations.successful;
            if (!dynamic)
                require(successful == 12 + (serviceSignature ? 2u : 1u) + (serviceSignature ? 3u : 2u) * 9,
                        "retained owners did not grow through capacities 1, 2, 4, ..., 256");
        } else
            require(!completed, "allocation prefix unexpectedly completed");
        if (expectedPublished >= 0)
            require(published == expectedPublished, "quota refusal published the wrong retained ordinal");
        const auto metrics = region.metrics();
        require(releasedIntact, "verification release escaped generated owner extent");
        require(allocations.successful == allocations.released && metrics.used == 0 && metrics.live_allocations == 0 &&
                    metrics.releases == metrics.successful_allocations && metrics.peak_used <= quota && region.close(),
                "creation, partial resize, terminal failure or native exception leaked an owner");
        if (allowed < 12)
            for (std::size_t index = 0; index < allowed; ++index)
                require(allocations.releasedOwners[index] == allocations.initialOwners[allowed - index - 1],
                        "failed initial verification owner did not release its actual prefix in reverse order");
        ++cases;
    };
    exercise(std::numeric_limits<std::size_t>::max(), 1048576, 0);
    // This includes all twelve initial pools, current-word/service resizes, every
    // retained-word/count/service growth and refusal after earlier pools resize.
    for (std::size_t allowed = 0; allowed < successful; ++allowed)
        exercise(allowed, 1048576, 0);
    exercise(std::numeric_limits<std::size_t>::max(), 0, 0);
    // Two retained rows plus the current word/service prefixes. One byte short
    // refuses the second growth after an earlier pool has already resized.
    const std::uint64_t exact = serviceSignature ? 224 : 128;
    for (const auto &[quota, rows] : {std::pair{exact - 1, 1}, std::pair{exact, 2}})
        exercise(std::numeric_limits<std::size_t>::max(), quota, 0, rows);
    exercise(std::numeric_limits<std::size_t>::max(), 1048576, 1);
    exercise(std::numeric_limits<std::size_t>::max(), 1048576, 2);

    context += " and dynamic fact restoration";
    exercise(std::numeric_limits<std::size_t>::max(), 1048576, 0, -1, true);
    // Use the actual successful run to sweep control, code-state, active-fact, compact-key and
    // retained-fact allocations as well as the initialization owners.
    for (std::size_t allowed = 0; allowed < successful; ++allowed)
        exercise(allowed, 1048576, 0, -1, true);
    require(partialKeyFailures != 0, "allocation sweep did not exercise key refusal after successful fact growth");
    const std::uint64_t initialPayload = serviceSignature ? 64 : 32;
    const auto controlQuota = initialPayload + abi::verificationControlRowPhysicalBytes;
    // One byte short refuses the control row. Exact fit admits it but refuses
    // the following two code-state rows (304 bytes); neither publishes a state.
    exercise(std::numeric_limits<std::size_t>::max(), controlQuota - 1, 0, -1, true, initialPayload);
    exercise(std::numeric_limits<std::size_t>::max(), controlQuota, 0, -1, true, controlQuota);
}

} // namespace

std::size_t initializationOwnershipChecks() {
    cases = 0;
    rawVerificationOwnership(false);
    rawVerificationOwnership(true);
    return cases;
}
