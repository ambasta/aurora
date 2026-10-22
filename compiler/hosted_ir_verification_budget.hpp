#pragma once

#include "hosted_frontend_abi.hpp"
#include "ir.hpp"
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <string_view>
#include <variant>

namespace aurora::ir {
namespace verification_budget {
// This is a checked allocation backstop over already admitted, normalized
// views, not another semantic verifier. In particular, loan IDs and loan types
// are instruction-time data: this boundary neither validates nor sizes by them.
inline constexpr std::uint64_t maximumExtent = static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max());
inline constexpr std::uint64_t retainedStates = 65536;
inline constexpr std::uint64_t retainedOperands = 262144;
inline constexpr std::uint64_t maximumInitializationPayload = 1209026560;

[[noreturn]] inline void invalid() {
    throw Error(DiagnosticCode::Internal, "invalid hosted IR verification quota");
}
// Overflow or an impossible admitted lookup is a boundary/integrity failure.
// A representable grant does not guarantee allocation: the source's separate
// allocation status and the runtime allocator remain authoritative for that.
constexpr std::uint64_t count(std::size_t value) {
    if (value > maximumExtent)
        invalid();
    return static_cast<std::uint64_t>(value);
}
constexpr std::size_t hostCount(std::uint64_t value) {
    if (value > maximumExtent || value > std::numeric_limits<std::size_t>::max())
        invalid();
    return static_cast<std::size_t>(value);
}
constexpr std::uint64_t sum(std::uint64_t left, std::uint64_t right) {
    if (left > maximumExtent || right > maximumExtent - left)
        invalid();
    return left + right;
}
constexpr std::uint64_t product(std::uint64_t left, std::uint64_t right) {
    if (left > maximumExtent || right > maximumExtent || (right != 0 && left > maximumExtent / right))
        invalid();
    return left * right;
}
constexpr std::uint64_t words(std::uint64_t facts) {
    if (facts > maximumExtent)
        invalid();
    return sum(facts / 64, facts % 64 != 0 ? 1 : 0);
}
// Match pool_capacity's saturation at floor(INT64_MAX / stride), rather
// than overflowing or inventing a smaller power-of-two allocation ceiling.
constexpr std::uint64_t geometricRows(std::uint64_t required, std::uint64_t stride) {
    if (stride == 0 || stride > maximumExtent || required > maximumExtent / stride)
        invalid();
    if (required == 0)
        return 0;
    const auto maximum = maximumExtent / stride;
    std::uint64_t next = 1;
    while (next < required)
        next = next > maximum / 2 ? maximum : product(next, 2);
    return next;
}
inline CallableView declaration(const Metadata &metadata, Metadata::CallableId callable) {
    (void)count(callable);
    if (callable >= metadata.callableCount())
        invalid();
    return metadata.callable(callable);
}
inline Metadata::ClassId classId(const Metadata &metadata, std::string_view name) {
    const auto id = metadata.findClass(name);
    if (!id)
        invalid();
    (void)count(*id);
    return *id;
}
inline std::uint64_t ownerFields(const Metadata &metadata, Metadata::ClassId nominal) {
    std::uint64_t result = 0;
    for (const auto field : metadata.fields(nominal))
        if (field.elementType.isOwnerStorage())
            result = sum(result, 1);
    return result;
}

static_assert(
    hosted_abi::verificationWordPairPhysicalBytes == 16 && hosted_abi::verificationCountPairPhysicalBytes == 16 &&
    hosted_abi::verificationServiceLoanPhysicalBytes == 32 && hosted_abi::verificationActiveFactPhysicalBytes == 200 &&
    hosted_abi::verificationFactRowPhysicalBytes == 192 && hosted_abi::verificationValueRowPhysicalBytes == 88 &&
    hosted_abi::verificationCodeStateRowPhysicalBytes == 152 && hosted_abi::verificationIndexRowPhysicalBytes == 8 &&
    hosted_abi::verificationControlRowPhysicalBytes == 352);

// Keep the original fixed-two-service initialization ceiling, independently of
// actual service capacity and independently of the seven added dynamic pools.
constexpr std::uint64_t initializationCap(std::uint64_t wordCount) {
    const auto snapshot = sum(product(wordCount, hosted_abi::verificationWordPairPhysicalBytes),
                              product(2, hosted_abi::verificationServiceLoanPhysicalBytes));
    const auto requested = sum(product(sum(retainedStates, 1), snapshot),
                               product(retainedStates, hosted_abi::verificationCountPairPhysicalBytes));
    return std::min(maximumInitializationPayload, requested);
}
static_assert(geometricRows(0, 192) == 0 && geometricRows(3, 192) == 4 &&
              geometricRows(retainedOperands, 88) == retainedOperands);
static_assert(initializationCap(0) == 5242944 &&
              initializationCap(1147) == maximumInitializationPayload - 65537ULL * 16 &&
              initializationCap(1148) == maximumInitializationPayload);
} // namespace verification_budget

// Scalar observations only: nothing here retains a native mirror of source
// owners or dynamic state, and none of these values is fed back as authority.
inline std::size_t checkedVerificationInitializationFacts(const Metadata &metadata, Metadata::CallableId callable) {
    using namespace verification_budget;
    const auto signature = declaration(metadata, callable);
    const auto frame = metadata.frame(callable);
    auto result = sum(count(frame.scalarSlots().size()), count(frame.objectSlots().size()));
    // receiver() deliberately observes the first borrowed class root when there
    // is one; a builtin borrowed owner has no receiver initialization fields.
    // This matches source initialization, not the genuine lexical receiver test
    // used below for dynamic owning-root facts.
    if (const auto receiver = signature.receiver())
        result = sum(result, count(metadata.fields(classId(metadata, receiver->className)).size()));
    return hostCount(result);
}

inline std::size_t checkedVerificationServiceCapacity(const Metadata &metadata, Metadata::CallableId callable) {
    using namespace verification_budget;
    const auto parameters = declaration(metadata, callable).parameters();
    (void)count(parameters.size());
    std::uint64_t result = 0;
    for (const auto type : parameters) {
        if (!type.isService())
            break;
        result = sum(result, 1);
    }
    return hostCount(result);
}

inline std::size_t
checkedVerificationDynamicFacts(const Metadata &metadata, const InstructionRange &code, Metadata::CallableId callable) {
    using namespace verification_budget;
    const auto signature = declaration(metadata, callable);
    const auto frame = metadata.frame(callable);
    const auto objects = frame.objectSlots();
    auto result = sum(count(objects.size()), count(frame.arraySlots().size()));
    result = sum(result, count(frame.spanSlots().size()));
    result = sum(result, count(frame.byteSlots().size()));
    for (const auto slot : objects) {
        const auto fields = ownerFields(metadata, classId(metadata, slot.second.className));
        if (fields != 0)
            result = sum(result, sum(1, fields));
    }
    const auto roots = signature.borrowedRootCount();
    (void)count(roots);
    if (roots == 0) {
        // This branch alone admits a genuine lexical receiver contribution.
        if (const auto receiver = signature.receiver()) {
            const auto fields = ownerFields(metadata, classId(metadata, receiver->className));
            if (fields != 0)
                result = sum(result, sum(1, fields));
        }
    } else {
        for (std::size_t at = 0; at < roots; ++at) {
            const auto type = signature.borrowedRootType(at);
            // The builtin OwnedValues case is one borrowed-owner fact instead
            // of one class-root fact. Invalid combinations remain source errors;
            // counting a root here neither validates it nor grants authority.
            result = sum(result, 1);
            if (type.isClass())
                result = sum(result, ownerFields(metadata, classId(metadata, type.className)));
        }
    }
    const auto instructions = code.size();
    (void)count(instructions);
    for (std::size_t at = 0; at < instructions; ++at)
        if (std::holds_alternative<AcquireObjectLoan>(code.at(at)))
            result = sum(result, 1);
    return hostCount(result);
}

// This is the source metrics definition, not allocated pool capacity: one W-row
// initialization bitset and C service rows, excluding CountPair and growth slack.
inline std::size_t checkedVerificationInitializationPayload(const Metadata &metadata, Metadata::CallableId callable) {
    using namespace verification_budget;
    return hostCount(sum(product(words(count(checkedVerificationInitializationFacts(metadata, callable))),
                                 hosted_abi::verificationWordPairPhysicalBytes),
                         product(count(checkedVerificationServiceCapacity(metadata, callable)),
                                 hosted_abi::verificationServiceLoanPhysicalBytes)));
}

// Independent report bounds. Logical retained value facts include semantic
// facts, operand values, both initialization lattices, and live service loans;
// they do not count traversal marks or allocation slack. Joins can change the
// lattice contribution but cannot exceed two facts per initialization slot.
inline std::uint64_t checkedVerificationRetainedValueFactBound(const Metadata &metadata,
                                                               const InstructionRange &code,
                                                               Metadata::CallableId callable) {
    using namespace verification_budget;
    const auto f = count(checkedVerificationInitializationFacts(metadata, callable));
    const auto c = count(checkedVerificationServiceCapacity(metadata, callable));
    const auto d = count(checkedVerificationDynamicFacts(metadata, code, callable));
    return sum(product(retainedStates, sum(d, sum(product(2, f), c))), retainedOperands);
}

inline std::uint64_t checkedVerificationRetainedInitializationPayloadBound(const Metadata &metadata,
                                                                           Metadata::CallableId callable) {
    using namespace verification_budget;
    return product(retainedStates, count(checkedVerificationInitializationPayload(metadata, callable)));
}

inline std::size_t
checkedVerificationQuota(const Metadata &metadata, const InstructionRange &code, Metadata::CallableId callable) {
    using namespace verification_budget;
    const auto n = count(code.size());
    const auto f = count(checkedVerificationInitializationFacts(metadata, callable));
    const auto w = words(f);
    const auto c = count(checkedVerificationServiceCapacity(metadata, callable));
    const auto d = count(checkedVerificationDynamicFacts(metadata, code, callable));

    // Four initialization owners: current words, retained words, retained
    // counts, and a service pool containing the current prefix plus snapshots.
    // The source checks the old cap after EACH replacement, including partial
    // growth; the minimum therefore also bounds terminal partial-owner states.
    auto initialization = product(w, hosted_abi::verificationWordPairPhysicalBytes);
    initialization =
        sum(initialization, product(product(retainedStates, w), hosted_abi::verificationWordPairPhysicalBytes));
    initialization = sum(initialization, product(retainedStates, hosted_abi::verificationCountPairPhysicalBytes));
    initialization = sum(initialization,
                         product(product(sum(retainedStates, 1), c), hosted_abi::verificationServiceLoanPhysicalBytes));
    auto total = std::min(initialization, initializationCap(w));

    // Current facts and the FIFO explicitly clamp geometric growth to their
    // derived caps. Other dynamic pools retain pool_capacity's geometric slack.
    total = sum(total, product(d, hosted_abi::verificationActiveFactPhysicalBytes));
    // retain_state appends once per new block, after B/R checks. Exact joins
    // only weaken inline current and replace initialization bits in place;
    // they NEVER append another fact/operand slice for an existing block.
    // Hence retained fact high-water <= B*D and operand high-water <= R even
    // across arbitrarily many changed joins or a terminal partial allocation.
    total = sum(total,
                product(geometricRows(product(retainedStates, d), hosted_abi::verificationFactRowPhysicalBytes),
                        hosted_abi::verificationFactRowPhysicalBytes));
    total = sum(total,
                product(geometricRows(n, hosted_abi::verificationValueRowPhysicalBytes),
                        hosted_abi::verificationValueRowPhysicalBytes));
    total = sum(total,
                product(geometricRows(retainedOperands, hosted_abi::verificationValueRowPhysicalBytes),
                        hosted_abi::verificationValueRowPhysicalBytes));
    total = sum(total, product(n, hosted_abi::verificationCodeStateRowPhysicalBytes));
    const auto queueRows = product(std::min(n, retainedStates), sum(product(2, f), 2));
    total = sum(total, product(queueRows, hosted_abi::verificationIndexRowPhysicalBytes));
    total = sum(total, hosted_abi::verificationControlRowPhysicalBytes);

    // Region::resize charges final logical used = other owners + replacement,
    // not old+new transient storage. Do not inflate this grant for allocator
    // staging: one resize at a time has a separate payload peak <= total plus
    // its old pool (conservatively <= 2*total, a mathematical bound, not a
    // potentially overflowing machine expression). Allocator headers, native
    // views, owner descriptors and process RSS are not part of either payload.
    return hostCount(total);
}
} // namespace aurora::ir
