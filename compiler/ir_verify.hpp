#pragma once
#include "hosted_graph.hpp"
#include "hosted_ir_instructions.hpp"
#include "initialization_facts.hpp"
#include "ir_layout.hpp"
#include "byte_literal.hpp"
#include <algorithm>
#include <deque>
#include <functional>
#include <type_traits>

namespace aurora::ir {
namespace verification {
[[noreturn]] inline void fail(const std::string &message) {
    throw Error("invalid typed IR: " + message);
}
class Guard {
public:
    int offset;
    int length;
    Type elementType;
    bool operator==(const Guard &) const = default;
};
// Only the implicit receiver can mint this evidence. Its identity and lifetime
// are fixed for the whole invocation; calls may mutate contents but cannot alter
// its nominal shape or end that lifetime. Local-array evidence is a distinct kind.
class ReceiverGuard {
public:
    std::string className;
    int fieldIndex;
    int firstLeaf;
    int length;
    Type elementType;
    bool operator==(const ReceiverGuard &) const = default;
};
// Class-element evidence has a separate kind from scalar-array guards. Root zero
// is the invocation receiver; positive roots are exact active object slots.
class ClassArrayGuard {
public:
    int objectOffset;
    std::string className;
    int fieldIndex;
    Type elementType;
    int elementCount;
    bool operator==(const ClassArrayGuard &) const = default;
};
using BoundsEvidence = std::variant<Guard, ReceiverGuard, ClassArrayGuard>;
class Value {
public:
    Type type;
    std::optional<BoundsEvidence> guard;
    bool operator==(const Value &) const = default;
};
// Region identity comes only from an entry binding. Ownership tokens are minted
// internally from stable instruction IDs, never supplied by an IR operand or runtime
// descriptor. A failed allocation still creates one live logical ownership token.
class RegionIdentity {
public:
    int offset;
    InstructionId site;
    bool borrowed = false; // symbolic receiver provenance never grants allocation authority
    bool operator==(const RegionIdentity &) const = default;
};
class ByteToken {
public:
    InstructionId site;
    RegionIdentity region;
    int fieldOrdinal = -1; // distinct tokens for one call or parameter owning several fields
    bool operator==(const ByteToken &) const = default;
};
// Static creation sites distinguish lifetimes restarted in the same storage on
// different control-flow paths. They are not dynamic invocation generations:
// a loop may reuse one creation site after ending every derived capability.
// Origins name a local array or bound parameter, with its own creation site;
// direct-parent storage and site preserve exact lexical reborrow authority.
class SpanCapability {
public:
    bool parameterOrigin;
    int origin;
    InstructionId originSite;
    int parent;
    InstructionId parentSite;
    InstructionId site;
    // Owned views capture the exact owner token and direct-field selector. The
    // origin/site still identify the lifetime of the standalone binding or root.
    std::optional<ByteToken> ownedToken = {};
    int ownedField = -1;
    bool literalOrigin = false;
    int arrayField = -1; // direct fixed u8 field of an exact receiver/object lifetime
    bool operator==(const SpanCapability &) const = default;
};
enum class ByteDisposition {
    Pristine,
    Live,
    Consumed
};
class ByteBinding {
public:
    InstructionId site;
    ByteDisposition disposition;
    std::optional<ByteToken> token;
    bool operator==(const ByteBinding &) const = default;
};
class OwnedObjectBinding {
public:
    InstructionId site;
    ByteDisposition disposition;
    std::map<int, ByteBinding> fields;
    bool operator==(const OwnedObjectBinding &) const = default;
};
class ObjectLoan {
public:
    int root;
    InstructionId rootSite;
    std::string className;
    bool mutableValue;
    bool called = false;
    bool operator==(const ObjectLoan &) const = default;
};
class ServiceIdentity {
public:
    InstructionId site;
    service::Kind kind;
    bool operator==(const ServiceIdentity &) const = default;
};
class ServiceLoan {
public:
    int offset;
    ServiceIdentity identity;
    bool called = false;
    bool operator==(const ServiceLoan &) const = default;
};
class State {
public:
    std::optional<Value> current;
    std::vector<Value> stack;
    InitializationFacts initialized;
    // Must-initialized facts intersect at joins; may-written facts union. The
    // latter prevent an alternate path or backedge from hiding a second init.
    InitializationFacts maybeInitialized;
    std::set<int> receiverInitialized;
    std::set<int> receiverMaybeInitialized;
    std::set<int> maybeConstructedObjects;
    std::map<int, InstructionId> activeObjects; // object base -> creation/binding site
    std::map<int, InstructionId> activeArrays;  // array base -> BeginArray site
    std::map<int, SpanCapability> activeSpans;
    std::map<int, ServiceIdentity> activeServices;
    std::map<int, ServiceLoan> serviceLoans;
    std::map<int, RegionIdentity> activeRegions;
    std::map<int, ByteBinding> activeBytes;
    std::map<int, ObjectLoan> objectLoans;
    std::map<int, OwnedObjectBinding> ownedObjects; // 0/-1 are the two distinct bound roots
    // Logical completion is independent of leaf initialization: empty embedded
    // values also require one complete, nominally checked initialization.
    // Ordinal -1 is whole-object completion minted by markObject. Like nested
    // completion, it is a must-fact at joins, including for leafless snapshots.
    std::set<std::pair<int, int>> objectClassesInitialized;
    std::set<int> receiverClassesInitialized;
    std::set<int> receiverClassesMaybeInitialized;
    explicit State(const std::shared_ptr<const InitializationSlotUniverse> &universe)
        : initialized(universe), maybeInitialized(universe) {
    }
    bool operator==(const State &) const = default;
};
inline void require(bool condition, const std::string &message) {
    if (!condition)
        fail(message);
}
// Limits on retained block-entry snapshots, not a global memory/time proof.
// Account before copying a State; revisits retain the same exact operand stack.
class BlockRetentionBudget {
    std::size_t states_ = 0, operands_ = 0;

public:
    static constexpr std::size_t maximumStates = 65536;
    static constexpr std::size_t maximumOperands = 262144;
    void retain(std::size_t operands) {
        require(states_ < maximumStates, "block-entry state retention limit exceeds 65536");
        require(operands_ <= maximumOperands && operands <= maximumOperands - operands_,
                "block-entry operand retention limit exceeds 262144");
        ++states_;
        operands_ += operands;
    }
    std::size_t states() const {
        return states_;
    }
    std::size_t operands() const {
        return operands_;
    }
};
inline bool scalarValueType(const Type &type, const Metadata &metadata) {
    return scalar(type) ||
           (type.isEnum() && type == Type::enumeration(type.className) && metadata.findEnum(type.className));
}
// A typed owner carries exactly one canonical copied-class identity. Descriptor
// shape alone never authorizes scalar reinterpretation, a carrier or resource payload.
inline void verifyOwnerType(const Type &type, const Metadata &metadata) {
    if (type == Type::OwnedBytes)
        return;
    require(type.isOwnedValues() && type == Type::ownedValues(Type(type.className)),
            "invalid canonical owned value type");
    const auto id = metadata.findClass(type.className);
    require(id.has_value(), "owned value element requires known canonical class layout");
    require(!metadata.isOwning(*id) && !metadata.isCarrier(*id),
            "owned value element must be a copied class, not an owner or carrier");
    require(copiedClassLeavesSupported(metadata.leaves(*id)),
            "owned value element exceeds copied class leaf limits");
    const auto storage = metadata.storage(*id);
    require(storage.sizeBytes >= 1 && storage.sizeBytes <= maximumCopiedClassBytes &&
                storage.reservedBytes <= maximumCopiedClassBytes,
            "owned value element storage exceeds 520 bytes");
}
class Metrics {
public:
    std::size_t snapshots = 0;
    std::size_t peakOperandDepth = 0;
    std::size_t peakRetainedOperandFacts = 0;
    std::size_t peakRetainedValueFacts = 0;
    // Both scalar initialization word payloads across retained block entries.
    // Excludes shared universe, other facts, current/merge states and allocator overhead.
    std::size_t peakRetainedInitializationPayloadBytes = 0;
};
// Entry admission has already certified these at-most-six normalized rows.
// Borrow their roots on demand; no native binding index or Type graph survives.
class EntryBindings {
    const InstructionRange &code_;
    std::size_t count_;

public:
    EntryBindings(const InstructionRange &code, std::size_t count) : code_(code), count_(count) {
    }
    template<class Binding>
    std::optional<int> root(int position) const {
        if (position < 0 || static_cast<std::size_t>(position) >= count_)
            return {};
        const auto instruction = code_[static_cast<CodePosition>(position)];
        if (const auto *binding = std::get_if<Binding>(&instruction))
            return binding->offset;
        return {};
    }
    template<class... Binding>
    bool contains(int offset) const {
        for (CodePosition position = 0; position < count_; ++position) {
            const auto instruction = code_[position];
            if (((std::get_if<Binding>(&instruction) && std::get<Binding>(instruction).offset == offset) || ...))
                return true;
        }
        return false;
    }
    std::optional<int> region() const {
        return root<BindRegionParameter>(0);
    }
};
inline void verifyFunction(FunctionBody &function,
                           const Metadata &metadata,
                           Metrics *metrics = nullptr) {
    const auto signature = metadata.callable(function.callableId);
    const auto frame = metadata.frame(function.callableId);
    const auto slots = frame.scalarSlots();
    const auto objectSlots = frame.objectSlots();
    const auto arraySlots = frame.arraySlots();
    const auto spanSlots = frame.spanSlots();
    const auto regionSlots = frame.regionSlots();
    const auto byteSlots = frame.byteSlots();
    const auto ownedValueTypes = frame.ownedValueTypes();
    const auto parameters = signature.parameters();
    const EntryBindings entryBindings(function.code, parameters.size());
    // Receiver observations are copied values. Keep them alive for boundRoot's
    // reference result throughout this body verification.
    const auto functionReceiver = signature.receiver();
    const auto secondReceiver = signature.secondBorrowedParameter();
    const auto classLeaves = [&](const std::string &name) {
        return metadata.leaves(metadata.findClass(name).value());
    };
    const auto logicalFields = [&](const std::string &name) {
        return metadata.fields(metadata.findClass(name).value());
    };
    const auto physicalStorage = [&](const std::string &name) {
        return metadata.storage(metadata.findClass(name).value());
    };
    const auto carrier = [&](const std::string &name) {
        const auto id = metadata.findClass(name);
        return id && metadata.isCarrier(*id);
    };
    auto ownerType = [&](int base) {
        require(byteSlots.contains(base), "owner type requires exact typed spill");
        return ownedValueTypes.contains(base) ? Type::ownedValues(Type(ownedValueTypes.at(base))) : Type::OwnedBytes;
    };
    auto objectLeaf = [&](int base, std::size_t leaf) {
        return base - physicalStorage(objectSlots.at(base).className).leafOffsets.at(leaf);
    };
    const auto owningType = [&](const Type &type) {
        return type.isClass() && owningClass(metadata, type.className);
    };
    const bool owningConstructor =
        functionReceiver && functionReceiver->constructor && owningClass(metadata, functionReceiver->className);
    std::optional<TypeRange> receiverLayout;
    std::optional<FieldRange> receiverFields;
    if (functionReceiver) {
        receiverLayout = classLeaves(functionReceiver->className);
        receiverFields = logicalFields(functionReceiver->className);
    }
    // Declaration admission belongs to the Aurora metadata owner. These indexes
    // associate instruction addresses with already-admitted object/array origins;
    // they neither reserve storage nor recheck declaration validity.
    std::map<int, int> objectBases;
    std::set<int> nestedObjectLeaves;
    for (const auto &[base, object] : objectSlots) {
        const auto layout = classLeaves(object.className);
        for (const auto &field : logicalFields(object.className))
            if (field.elementType.isClass())
                for (int leaf = 0; leaf < field.length; ++leaf)
                    nestedObjectLeaves.insert(objectLeaf(base, field.firstLeaf + leaf));
        for (std::size_t index = 0; index < layout.size(); ++index)
            objectBases.emplace(objectLeaf(base, index), base);
    }
    std::map<int, int> arrayBases;
    for (const auto &[base, length] : arraySlots)
        for (int element = 0; element < length; ++element)
            arrayBases.emplace(base - element, base);
    // The admitted scalar offsets form the immutable initialization domain shared
    // by this function's CFG snapshots. This contains no declaration payloads.
    std::vector<int> initializationOffsets;
    initializationOffsets.reserve(slots.size());
    for (const auto &[offset, type] : slots) {
        (void)type;
        initializationOffsets.push_back(offset);
    }
    const auto initializationUniverse =
        std::make_shared<const InitializationSlotUniverse>(std::move(initializationOffsets), frame.frameBytes());
    for (CodePosition index = 0; index < function.code.size(); ++index) {
        const auto instruction = function.code[index];
        if (const auto *literal = std::get_if<BorrowLiteralSpanObservation>(&instruction)) {
            require(literal->bytes.size() <= maxByteStringBytes, "literal span exceeds byte-string bound");
            require(spanSlots.contains(literal->resultOffset), "literal span requires exact typed spill");
        }
    }
    std::map<int, std::pair<int, service::Kind>> serviceLoanRoots;
    for (CodePosition index = 0; index < function.code.size(); ++index) {
        const auto instruction = function.code[index];
        if (const auto *loan = std::get_if<AcquireServiceLoan>(&instruction)) {
            const auto root = std::pair{loan->offset, loan->kind};
            require(loan->loanId > 0 &&
                        (!serviceLoanRoots.contains(loan->loanId) || serviceLoanRoots.at(loan->loanId) == root),
                    "service loan identity cannot change static root or kind");
            serviceLoanRoots.emplace(loan->loanId, root);
        }
    }
    // Source normalization already checked every body and fixed its retained
    // order. Native worklist entries use those zero-based positions, never IDs.
    // Only block entries retain snapshots. Saving a full state at every instruction
    // makes a straight-line N-element initializer retain O(N^2) stack/set contents.
    // Depths alone are linear-sized. Full operand/provenance states still live
    // only at basic-block entries, never once per instruction.
    std::vector<std::size_t> stackBefore(function.code.size()), stackAfter(function.code.size());
    std::vector<std::optional<State>> states(function.code.size());
    BlockRetentionBudget retention;
    retention.retain(0);
    states[0] = State{initializationUniverse};
    if (functionReceiver && owningClass(metadata, functionReceiver->className)) {
        OwnedObjectBinding receiver{
            0, functionReceiver->constructor ? ByteDisposition::Pristine : ByteDisposition::Live, {}};
        const RegionIdentity borrowed{0, 0, true};
        for (std::size_t field = 0; field < receiverFields->size(); ++field)
            if ((*receiverFields)[field].elementType.isOwnerStorage()) {
                ByteBinding binding{0, receiver.disposition, {}};
                if (!functionReceiver->constructor)
                    binding.token = ByteToken{0, borrowed, static_cast<int>(field)};
                receiver.fields.emplace(static_cast<int>(field), binding);
            }
        states[0]->ownedObjects.emplace(0, std::move(receiver));
    }
    if (secondReceiver) {
        OwnedObjectBinding second{0, ByteDisposition::Live, {}};
        // The selector distinguishes symbolic provenance even when both formal
        // classes and field ordinals match. It is never allocation authority.
        const RegionIdentity borrowed{-1, 0, true};
        const auto fields = logicalFields(secondReceiver->className);
        for (std::size_t field = 0; field < fields.size(); ++field)
            if (fields[field].elementType.isOwnerStorage())
                second.fields.emplace(static_cast<int>(field),
                                      ByteBinding{0,
                                                  ByteDisposition::Live,
                                                  ByteToken{0, borrowed, static_cast<int>(field)}});
        states[0]->ownedObjects.emplace(-1, std::move(second));
    }
    if (functionReceiver && !functionReceiver->constructor) {
        for (std::size_t field = 0; field < receiverLayout->size(); ++field) {
            states[0]->receiverInitialized.insert(static_cast<int>(field));
            states[0]->receiverMaybeInitialized.insert(static_cast<int>(field));
        }
        for (std::size_t field = 0; field < receiverFields->size(); ++field)
            if ((*receiverFields)[field].elementType.isClass()) {
                states[0]->receiverClassesInitialized.insert(static_cast<int>(field));
                states[0]->receiverClassesMaybeInitialized.insert(static_cast<int>(field));
            }
    }
    std::deque<CodePosition> pending{0};
    std::size_t retainedValueFacts = 0;
    if (metrics) {
        *metrics = Metrics{};
        metrics->snapshots = 1;
    }
    auto slot = [&](int offset, const Type &type) {
        require(slots.contains(offset) && slots.at(offset) == type, "slot type/layout mismatch");
    };
    auto facts = [](const State &state) {
        std::size_t ownedFields = 0;
        for (const auto &[unused, object] : state.ownedObjects) {
            (void)unused;
            ownedFields += object.fields.size();
        }
        return ownedFields + state.stack.size() + state.initialized.size() + state.maybeInitialized.size() +
               state.receiverInitialized.size() + state.receiverMaybeInitialized.size() +
               state.maybeConstructedObjects.size() + state.activeObjects.size() +
               state.objectClassesInitialized.size() + state.receiverClassesInitialized.size() +
               state.receiverClassesMaybeInitialized.size() + state.activeArrays.size() + state.activeSpans.size() +
               state.activeRegions.size() + state.activeBytes.size() + state.ownedObjects.size() +
               state.objectLoans.size() + state.activeServices.size() + state.serviceLoans.size();
    };
    retainedValueFacts = facts(*states[0]);
    auto initializationPayload = [](const State &state) {
        return state.initialized.payloadBytes() + state.maybeInitialized.payloadBytes();
    };
    std::size_t retainedInitializationPayloadBytes = initializationPayload(*states[0]);
    if (metrics) {
        metrics->peakRetainedValueFacts = retainedValueFacts;
        metrics->peakRetainedInitializationPayloadBytes = retainedInitializationPayloadBytes;
    }
    auto intersection = [](const auto &left, const auto &right) {
        std::decay_t<decltype(left)> result;
        std::set_intersection(
            left.begin(), left.end(), right.begin(), right.end(), std::inserter(result, result.end()));
        return result;
    };
    auto enqueue = [&](CodePosition index, const State &state) {
        require(function.code.flowAt(index).blockEntry, "worklist target is not a basic-block entry");
        if (!states[index]) {
            // Check before the snapshot allocation, whether metrics are enabled
            // or not. These retained counts never grow on worklist revisits.
            retention.retain(state.stack.size());
            retainedValueFacts += facts(state);
            retainedInitializationPayloadBytes += initializationPayload(state);
            if (metrics) {
                ++metrics->snapshots;
                metrics->peakRetainedOperandFacts = retention.operands();
                metrics->peakRetainedValueFacts = std::max(metrics->peakRetainedValueFacts, retainedValueFacts);
                metrics->peakRetainedInitializationPayloadBytes =
                    std::max(metrics->peakRetainedInitializationPayloadBytes, retainedInitializationPayloadBytes);
            }
            states[index] = state;
            pending.push_back(index);
            return;
        }
        const auto &existing = *states[index];
        require(existing.activeObjects == state.activeObjects,
                "incompatible active object lifetimes at control-flow join");
        require(existing.activeArrays == state.activeArrays,
                "incompatible active array lifetimes at control-flow join");
        require(existing.activeSpans == state.activeSpans,
                "incompatible active span capabilities at control-flow join");
        require(existing.activeServices == state.activeServices && existing.serviceLoans == state.serviceLoans,
                "incompatible service provenance or loans at control-flow join");
        require(existing.activeRegions == state.activeRegions,
                "incompatible active region authority at control-flow join");
        require(existing.activeBytes == state.activeBytes,
                "incompatible owned byte lifetimes or ownership at control-flow join");
        require(existing.ownedObjects == state.ownedObjects,
                "incompatible owning object lifetimes or field ownership at control-flow join");
        require(existing.objectLoans == state.objectLoans, "incompatible object loans at control-flow join");
        require(existing.stack == state.stack, "incompatible value/guard stacks at control-flow join");
        State merged = existing;
        if (merged.current != state.current)
            merged.current.reset();
        merged.initialized.intersectWith(state.initialized);
        merged.receiverInitialized = intersection(merged.receiverInitialized, state.receiverInitialized);
        merged.objectClassesInitialized = intersection(merged.objectClassesInitialized, state.objectClassesInitialized);
        merged.receiverClassesInitialized =
            intersection(merged.receiverClassesInitialized, state.receiverClassesInitialized);
        merged.receiverClassesMaybeInitialized.insert(state.receiverClassesMaybeInitialized.begin(),
                                                      state.receiverClassesMaybeInitialized.end());
        merged.maybeInitialized.unionWith(state.maybeInitialized);
        merged.receiverMaybeInitialized.insert(state.receiverMaybeInitialized.begin(),
                                               state.receiverMaybeInitialized.end());
        merged.maybeConstructedObjects.insert(state.maybeConstructedObjects.begin(),
                                              state.maybeConstructedObjects.end());
        if (merged != *states[index]) {
            retainedValueFacts -= facts(*states[index]);
            retainedValueFacts += facts(merged);
            if (metrics)
                metrics->peakRetainedValueFacts = std::max(metrics->peakRetainedValueFacts, retainedValueFacts);
            states[index] = std::move(merged);
            pending.push_back(index);
        }
    };
    while (!pending.empty()) {
        auto index = pending.front();
        pending.pop_front();
        State state = *states[index];
        while (true) {
            const auto instruction = function.code[index];
            const auto flow = function.code.flowAt(index);
            // Provenance names the immutable row, independently of retained order.
            const InstructionId instructionId = function.code.idAt(index);
            stackBefore[index] = state.stack.size();
            auto current = [&](const Type &expected) -> Value {
                require(state.current && state.current->type == expected, "missing or mistyped current value");
                return *state.current;
            };
            auto pop = [&]() -> Value {
                require(!state.stack.empty(), "value stack underflow");
                auto value = state.stack.back();
                state.stack.pop_back();
                return value;
            };
            // Only the validated BorrowedCallObservation may exercise its one or two loans.
            const auto *borrowedCall = std::get_if<BorrowedCallObservation>(&instruction);
            auto loanAccess = [&](int root, bool writing) {
                for (const auto &[id, loan] : state.objectLoans) {
                    if (loan.root != root ||
                        (borrowedCall && (id == borrowedCall->loanId || id == borrowedCall->secondLoanId)))
                        continue;
                    require(!writing && !loan.mutableValue, "object access conflicts with active synchronous loan");
                }
            };
            auto activeObjectField = [&](int offset) {
                require(!objectBases.contains(offset) || state.activeObjects.contains(objectBases.at(offset)),
                        "object field access outside active lifetime");
                if (objectBases.contains(offset)) {
                    const int root = objectBases.at(offset);
                    loanAccess(root, false);
                    require(!state.ownedObjects.contains(root) ||
                                state.ownedObjects.at(root).disposition != ByteDisposition::Consumed,
                            "field access through consumed owning object");
                }
            };
            auto activeArrayElement = [&](int offset) {
                require(!arrayBases.contains(offset) || state.activeArrays.contains(arrayBases.at(offset)),
                        "array element access outside active lifetime");
            };
            auto arrayWritable = [&](int offset) {
                if (objectBases.contains(offset)) {
                    const int root = objectBases.at(offset);
                    const auto &name = objectSlots.at(root).className;
                    for (const auto &[unused, capability] : state.activeSpans) {
                        (void)unused;
                        if (capability.arrayField < 0 || capability.origin != root)
                            continue;
                        const int first = physicalStorage(name).fieldOffsets.at(capability.arrayField);
                        const int length = logicalFields(name).at(capability.arrayField).length;
                        require(root - offset < first || root - offset >= first + length,
                                "fixed array field write with live readonly span");
                    }
                }
                if (!arrayBases.contains(offset))
                    return;
                const int base = arrayBases.at(offset);
                for (const auto &[unused, capability] : state.activeSpans) {
                    (void)unused;
                    require(capability.literalOrigin || capability.ownedToken || capability.parameterOrigin ||
                                capability.origin != base,
                            "write to byte array with live readonly span");
                }
            };
            // Call contracts already admit their frame roots. Non-call wrappers
            // keep declaration diagnostics around these live-state mechanisms.
            auto liveSpan = [&](int base) -> const SpanCapability & {
                require(state.activeSpans.contains(base), "span capability is not active");
                const auto &capability = state.activeSpans.at(base);
                if (capability.literalOrigin) {
                    require(!capability.parameterOrigin && !capability.ownedToken && capability.ownedField == -1,
                            "literal span cannot carry another origin kind");
                    const auto origin = function.code.instructionById(capability.originSite);
                    const auto *literal = std::get_if<BorrowLiteralSpanObservation>(&origin);
                    require(literal && literal->resultOffset == capability.origin &&
                                literal->bytes.size() <= maxByteStringBytes,
                            "literal span must retain its exact immutable origin");
                } else if (capability.arrayField >= 0) {
                    require(!capability.parameterOrigin && !capability.ownedToken && capability.ownedField == -1,
                            "fixed array span cannot carry another origin kind");
                    loanAccess(capability.origin, false);
                    if (capability.origin == 0) {
                        require(functionReceiver && !functionReceiver->constructor && capability.originSite == 0,
                                "fixed array span receiver lifetime is not active");
                    } else {
                        require(state.activeObjects.contains(capability.origin) &&
                                    state.activeObjects.at(capability.origin) == capability.originSite,
                                "fixed array span object lifetime is not active");
                    }
                    const auto &name = capability.origin == 0 ? functionReceiver->className
                                                              : objectSlots.at(capability.origin).className;
                    const auto fields = logicalFields(name);
                    require(static_cast<std::size_t>(capability.arrayField) < fields.size() &&
                                fields[capability.arrayField].array &&
                                fields[capability.arrayField].elementType == Type::U8,
                            "fixed array span field provenance mismatch");
                } else if (capability.ownedToken) {
                    loanAccess(capability.origin, false);
                    require(!capability.parameterOrigin, "owned span cannot have parameter origin");
                    const ByteBinding *owner = nullptr;
                    if (capability.ownedField == -1) {
                        const auto binding = state.activeBytes.find(capability.origin);
                        require(binding != state.activeBytes.end() && binding->second.site == capability.originSite,
                                "span owned byte origin lifetime is not active");
                        owner = &binding->second;
                    } else {
                        const auto root = state.ownedObjects.find(capability.origin);
                        require(root != state.ownedObjects.end() && root->second.site == capability.originSite &&
                                    root->second.disposition == ByteDisposition::Live &&
                                    root->second.fields.contains(capability.ownedField),
                                "span owning root lifetime is not active");
                        owner = &root->second.fields.at(capability.ownedField);
                    }
                    require(owner->disposition == ByteDisposition::Live && owner->token == capability.ownedToken,
                            "span owner token is not active");
                    const auto &identity = capability.ownedToken->region;
                    if (identity.borrowed)
                        require(capability.origin == 0 && capability.ownedField >= 0 && functionReceiver,
                                "span borrowed receiver provenance mismatch");
                    else
                        require(state.activeRegions.contains(identity.offset) &&
                                    state.activeRegions.at(identity.offset) == identity,
                                "span owner region identity is not active");
                } else if (capability.parameterOrigin) {
                    const auto parameterRoot = entryBindings.root<BindSpanParameter>(capability.origin);
                    require(parameterRoot.has_value(), "span parameter origin does not exist");
                    const auto root = state.activeSpans.find(*parameterRoot);
                    require(root != state.activeSpans.end() && root->second.site == capability.originSite &&
                                root->second.parameterOrigin && root->second.origin == capability.origin &&
                                root->second.originSite == capability.originSite && root->second.parent == 0,
                            "span parameter origin lifetime is not active");
                } else {
                    require(state.activeArrays.contains(capability.origin) &&
                                state.activeArrays.at(capability.origin) == capability.originSite,
                            "span array origin lifetime is not active");
                }
                if (capability.parent != 0) {
                    const auto parent = state.activeSpans.find(capability.parent);
                    require(parent != state.activeSpans.end() && parent->second.site == capability.parentSite,
                            "span direct parent lifetime is not active");
                    require(parent->second.parameterOrigin == capability.parameterOrigin &&
                                parent->second.origin == capability.origin &&
                                parent->second.originSite == capability.originSite &&
                                parent->second.ownedToken == capability.ownedToken &&
                                parent->second.ownedField == capability.ownedField &&
                                parent->second.arrayField == capability.arrayField &&
                                parent->second.literalOrigin == capability.literalOrigin,
                            "span direct parent origin mismatch");
                }
                return capability;
            };
            auto span = [&](int base) -> const SpanCapability & {
                require(spanSlots.contains(base), "span requires exact typed spill");
                return liveSpan(base);
            };
            auto inactiveSpanTarget = [&](int base) {
                require(!state.activeSpans.contains(base), "span spill is already active");
            };
            auto spanTarget = [&](int base) {
                require(spanSlots.contains(base), "span requires exact typed spill");
                require(!entryBindings.contains<BindSpanParameter>(base), "span parameter cannot be rebound");
                inactiveSpanTarget(base);
            };
            auto ownerWritable = [&](int root, std::optional<int> field = {}) {
                loanAccess(root, true);
                for (const auto &[unused, capability] : state.activeSpans) {
                    (void)unused;
                    const int ordinal = capability.arrayField >= 0 ? capability.arrayField : capability.ownedField;
                    require((!capability.ownedToken && capability.arrayField < 0) || capability.origin != root ||
                                (field && ordinal != *field),
                            "owned byte or root mutation with live readonly span");
                }
            };
            auto activeRegion = [&](int base) -> RegionIdentity {
                require(state.activeRegions.contains(base), "region authority is not active");
                return state.activeRegions.at(base);
            };
            auto region = [&](int base) -> RegionIdentity {
                require(regionSlots.contains(base), "region requires exact typed spill");
                return activeRegion(base);
            };
            auto activeByteBinding = [&](int base) -> ByteBinding & {
                require(state.activeBytes.contains(base), "owned byte lifetime is not active");
                return state.activeBytes.at(base);
            };
            auto byteBinding = [&](int base) -> ByteBinding & {
                require(byteSlots.contains(base), "owned byte operation requires exact typed spill");
                return activeByteBinding(base);
            };
            auto liveBytes = [&](int base) -> ByteBinding & {
                auto &binding = activeByteBinding(base);
                require(binding.disposition == ByteDisposition::Live && binding.token.has_value(),
                        "owned byte binding does not hold live ownership");
                require(region(binding.token->region.offset) == binding.token->region,
                        "owned byte region identity does not match active authority");
                return binding;
            };
            auto bytes = [&](int base, bool mutableAccess) -> ByteBinding & {
                require(byteSlots.contains(base), "owned byte operation requires exact typed spill");
                auto &binding = liveBytes(base);
                require(!mutableAccess || byteSlots.at(base),
                        "const owned byte binding cannot be mutated or moved");
                if (mutableAccess)
                    ownerWritable(base, -1);
                return binding;
            };
            auto pristineBytes = [&](int base) -> ByteBinding & {
                auto &binding = activeByteBinding(base);
                require(binding.disposition == ByteDisposition::Pristine && !binding.token,
                        "owned byte result requires pristine binding");
                return binding;
            };
            auto byteTarget = [&](int base) -> ByteBinding & {
                require(byteSlots.contains(base), "owned byte operation requires exact typed spill");
                return pristineBytes(base);
            };
            auto freshToken = [&](const RegionIdentity &origin, int ordinal) {
                auto distinct = [&](const ByteBinding &other) {
                    require(!other.token || other.token->region.borrowed || other.token->site != instructionId ||
                                other.token->fieldOrdinal != ordinal,
                            "ownership creation site still has a live token");
                };
                for (const auto &[unused, other] : state.activeBytes) {
                    (void)unused;
                    distinct(other);
                }
                for (const auto &[unused, object] : state.ownedObjects) {
                    (void)unused;
                    for (const auto &[field, other] : object.fields) {
                        (void)field;
                        distinct(other);
                    }
                }
                return ByteToken{instructionId, origin, ordinal};
            };
            auto mintByteBinding = [&](ByteBinding &binding, const RegionIdentity &origin) {
                const auto token = freshToken(origin, -1);
                binding.disposition = ByteDisposition::Live;
                binding.token = token;
            };
            auto mintBytes = [&](int base, const RegionIdentity &origin) {
                mintByteBinding(byteTarget(base), origin);
            };
            auto consumeByteBinding = [&](ByteBinding &binding) {
                binding.disposition = ByteDisposition::Consumed;
                binding.token.reset();
            };
            auto consumeBytes = [&](int base) {
                ownerWritable(base, -1);
                consumeByteBinding(byteBinding(base));
            };
            auto store = [&](int offset, const Type &type) {
                slot(offset, type);
                activeObjectField(offset);
                if (objectBases.contains(offset))
                    loanAccess(objectBases.at(offset), true);
                activeArrayElement(offset);
                arrayWritable(offset);
                require(!nestedObjectLeaves.contains(offset), "scalar store cannot write nested class field");
                require(!entryBindings.contains<BindParameter>(offset) || !state.maybeInitialized.contains(offset),
                        "write to immutable scalar parameter");
                require(!objectBases.contains(offset) || objectSlots.at(objectBases.at(offset)).mutableValue ||
                            !state.maybeInitialized.contains(offset),
                        "write to initialized const object field");
                state.initialized.insert(offset);
                state.maybeInitialized.insert(offset);
            };
            auto receiverShape = [&](int fieldIndex) -> ClassField {
                require(!signature.borrowedParameter(),
                        "borrowed free formal grants no direct receiver field authority");
                loanAccess(0, false);
                require(receiverFields.has_value(), "receiver access without bound receiver");
                require(fieldIndex >= 0 && static_cast<std::size_t>(fieldIndex) < receiverFields->size(),
                        "receiver field type/layout mismatch");
                return (*receiverFields)[fieldIndex];
            };
            auto receiverField = [&](int fieldIndex, const Type &type) -> ClassField {
                const auto field = receiverShape(fieldIndex);
                require(!field.array && scalarValueType(field.elementType, metadata) && field.elementType == type,
                        "receiver field type/layout mismatch");
                return field;
            };
            auto receiverArray = [&](int fieldIndex, bool initialized) -> ClassField {
                const auto field = receiverShape(fieldIndex);
                require(field.array, "receiver array operation requires array field");
                require(scalar(field.elementType), "receiver scalar array operation requires scalar array field");
                if (initialized) {
                    require(!functionReceiver->constructor,
                            "constructor cannot access receiver array during initialization");
                    for (int element = 0; element < field.length; ++element)
                        require(state.receiverInitialized.contains(field.firstLeaf + element),
                                "receiver array element not initialized");
                }
                return field;
            };
            auto receiverEvidence = [&](int fieldIndex, const ClassField &field) {
                return ReceiverGuard{
                    functionReceiver->className, fieldIndex, field.firstLeaf, field.length, field.elementType};
            };
            auto receiverGuard = [&](const Value &value, int fieldIndex, const ClassField &field) {
                require(value.type == Type::I64 &&
                            value.guard == std::optional<BoundsEvidence>(receiverEvidence(fieldIndex, field)),
                        "receiver index access lacks matching dominating bounds token");
            };
            auto array = [&](int offset, int length, const Type &type) {
                require(scalar(type) && length >= 1 && length <= 4096, "invalid array shape");
                require(offset >= length * storageWidth(type), "array layout underflow");
                for (int element = 0; element < length; ++element) {
                    const int elementOffset = offset - element * storageWidth(type);
                    slot(elementOffset, type);
                    activeObjectField(elementOffset);
                    activeArrayElement(elementOffset);
                    require(!nestedObjectLeaves.contains(elementOffset),
                            "scalar array operation cannot address nested class field");
                    require(state.initialized.contains(elementOffset), "array element not initialized");
                }
            };
            auto guard = [&](const Value &value, int offset, int length, const Type &type) {
                require(value.type == Type::I64 &&
                            value.guard == std::optional<BoundsEvidence>(Guard{offset, length, type}),
                        "index access lacks matching dominating bounds token");
            };
            auto logicalComplete = [&](int base) {
                if (state.ownedObjects.contains(base)) {
                    const auto &object = state.ownedObjects.at(base);
                    require(object.disposition == ByteDisposition::Live,
                            "owning object does not hold complete live ownership");
                    for (const auto &[unused, field] : object.fields) {
                        (void)unused;
                        require(field.disposition == ByteDisposition::Live && field.token &&
                                    !field.token->region.borrowed &&
                                    region(field.token->region.offset) == field.token->region,
                                "owning object field lacks live region ownership");
                    }
                }
                const auto &name = objectSlots.at(base).className;
                if (metadata.findClass(name))
                    for (std::size_t field = 0; field < logicalFields(name).size(); ++field)
                        if (logicalFields(name)[field].elementType.isClass())
                            require(state.objectClassesInitialized.contains({base, static_cast<int>(field)}),
                                    "nested class field not completely initialized");
                if (classLeaves(name).empty())
                    require(state.objectClassesInitialized.contains({base, -1}),
                            "empty object not completely initialized");
            };
            auto liveCopiedArgument = [&](int base, const Type &type, const std::string &role) {
                require(state.activeObjects.contains(base), role + " argument outside active object lifetime");
                const auto layout = classLeaves(type.className);
                for (std::size_t field = 0; field < layout.size(); ++field)
                    require(state.initialized.contains(objectLeaf(base, field)),
                            role + " argument object not fully initialized");
                logicalComplete(base);
            };
            auto markObject = [&](int base) {
                const auto &name = objectSlots.at(base).className;
                const auto layout = classLeaves(name);
                state.maybeConstructedObjects.insert(base);
                state.objectClassesInitialized.insert({base, -1});
                for (std::size_t leaf = 0; leaf < layout.size(); ++leaf) {
                    const int offset = objectLeaf(base, leaf);
                    state.initialized.insert(offset);
                    state.maybeInitialized.insert(offset);
                }
                if (metadata.findClass(name))
                    for (std::size_t field = 0; field < logicalFields(name).size(); ++field)
                        if (logicalFields(name)[field].elementType.isClass())
                            state.objectClassesInitialized.insert({base, static_cast<int>(field)});
            };
            auto initializedObject = [&](int base) -> ObjectSlot {
                require(state.activeObjects.contains(base), "copy object outside active lifetime");
                auto object = objectSlots.at(base);
                const auto layout = classLeaves(object.className);
                for (std::size_t leaf = 0; leaf < layout.size(); ++leaf)
                    require(state.initialized.contains(objectLeaf(base, leaf)),
                            "copy source object not fully initialized");
                logicalComplete(base);
                return object;
            };
            auto liveObject = [&](int base) -> ObjectSlot {
                loanAccess(base, false);
                return initializedObject(base);
            };
            auto completeObject = [&](int base) -> ObjectSlot {
                loanAccess(base, false);
                require(objectSlots.contains(base), "copy requires exact object slot");
                return initializedObject(base);
            };
            auto boundRoot = [&](int root) -> const Receiver & {
                require(root == 0 || root == -1, "invalid bound object root selector");
                const auto &formal = root == 0 ? functionReceiver : secondReceiver;
                require(formal.has_value(), "borrowed object root is not bound");
                return *formal;
            };
            auto liveOwnedRoot = [&](int root) -> const OwnedObjectBinding & {
                require(state.ownedObjects.contains(root),
                        "object loan requires exact owning root");
                const auto &object = state.ownedObjects.at(root);
                require(object.disposition == ByteDisposition::Live, "object loan requires complete live root");
                for (const auto &[ordinal, field] : object.fields) {
                    require(field.disposition == ByteDisposition::Live && field.token &&
                                field.token->fieldOrdinal == ordinal,
                            "object loan field lacks live ownership");
                    if (root <= 0)
                        require(field.token->region == RegionIdentity{root, 0, true},
                                "borrowed root field provenance mismatch");
                    else
                        require(!field.token->region.borrowed &&
                                    region(field.token->region.offset) == field.token->region,
                                "object loan field region is not active");
                }
                return object;
            };
            auto liveOwningRoot = [&](int root) -> const OwnedObjectBinding & {
                require(root >= -1, "invalid borrowed object root");
                const auto &name = root <= 0 ? boundRoot(root).className : completeObject(root).className;
                require(owningClass(metadata, name), "object loan requires exact owning root");
                return liveOwnedRoot(root);
            };
            auto initializedReceiverClassField = [&](int index) {
                require(state.receiverClassesInitialized.contains(index),
                        "receiver nested class field not initialized");
            };
            auto liveClassField = [&](int base, int index, bool mutableAccess) {
                loanAccess(base, mutableAccess);
                if (base == 0)
                    initializedReceiverClassField(index);
                else
                    liveObject(base);
            };
            auto completeClassField = [&](int base, int index, bool mutableAccess) -> ClassField {
                loanAccess(base, mutableAccess);
                require(base >= 0, "invalid owned field root offset");
                ClassField field{};
                if (base == 0) {
                    field = receiverShape(index);
                    require(!functionReceiver->constructor,
                            "constructor cannot access owned field during initialization");
                    require(!mutableAccess || functionReceiver->mutableValue,
                            "const receiver cannot supply mutable owned field");
                    initializedReceiverClassField(index);
                } else {
                    const auto &root = completeObject(base);
                    require(!mutableAccess || root.mutableValue, "const object cannot supply mutable owned field");
                    require(metadata.findClass(root.className) && index >= 0 &&
                                static_cast<std::size_t>(index) < logicalFields(root.className).size(),
                            "owned field logical index out of range");
                    field = logicalFields(root.className)[index];
                }
                require(!field.array && field.elementType.isClass(), "owned field operation requires class field");
                return field;
            };
            auto completeClassArray = [&](int base, int fieldIndex, bool mutableAccess) -> ClassField {
                require(base >= 0, "invalid class array root offset");
                loanAccess(base, mutableAccess);
                ClassField field{};
                if (base == 0) {
                    field = receiverShape(fieldIndex);
                    require(!functionReceiver->constructor,
                            "constructor cannot access class array during initialization");
                    require(!mutableAccess || functionReceiver->mutableValue,
                            "const receiver cannot supply mutable class array");
                    require(state.receiverClassesInitialized.contains(fieldIndex),
                            "receiver class array not completely initialized");
                } else {
                    const auto &root = completeObject(base);
                    require(!mutableAccess || root.mutableValue, "const object cannot supply mutable class array");
                    require(metadata.findClass(root.className) && fieldIndex >= 0 &&
                                static_cast<std::size_t>(fieldIndex) < logicalFields(root.className).size(),
                            "class array logical field index out of range");
                    field = logicalFields(root.className)[fieldIndex];
                }
                require(field.array && field.elementType.isClass(),
                        "class array operation requires class array field");
                require(!owningClass(metadata, field.elementType.className),
                        "class array elements must be copied values");
                return field;
            };
            auto classArrayEvidence = [&](int base, int fieldIndex, const ClassField &field) {
                return ClassArrayGuard{base,
                                       base == 0 ? functionReceiver->className
                                                 : objectSlots.at(base).className,
                                       fieldIndex,
                                       field.elementType,
                                       field.elementCount};
            };
            auto checkedClassArray = [&](int base, int fieldIndex, const ClassField &field) {
                require(current(Type::I64).guard ==
                            std::optional<BoundsEvidence>(classArrayEvidence(base, fieldIndex, field)),
                        "class array access lacks matching dominating bounds token");
            };
            auto initializeObject = [&](int base) {
                require(!state.maybeConstructedObjects.contains(base), "copy result object already initialized");
                const auto layout = classLeaves(objectSlots.at(base).className);
                for (std::size_t leaf = 0; leaf < layout.size(); ++leaf)
                    require(!state.maybeInitialized.contains(objectLeaf(base, leaf)),
                            "copy requires pristine result object");
                if (state.ownedObjects.contains(base)) {
                    const auto &object = state.ownedObjects.at(base);
                    require(object.disposition == ByteDisposition::Pristine,
                            "owning object result requires pristine root");
                    for (const auto &[unused, field] : object.fields) {
                        (void)unused;
                        require(field.disposition == ByteDisposition::Pristine && !field.token,
                                "owning object result requires pristine fields");
                    }
                }
                markObject(base);
            };
            auto copyTarget = [&](int base, const std::string &name) {
                require(objectSlots.contains(base), "copy requires exact object slot");
                require(state.activeObjects.contains(base), "copy object outside active lifetime");
                require(objectSlots.at(base).className == name, "copy nominal class mismatch");
                initializeObject(base);
            };
            auto liveCopyTarget = [&](int base) {
                require(state.activeObjects.contains(base), "copy object outside active lifetime");
                initializeObject(base);
            };
            auto beginOwnedObject = [&](int base, const std::string &name) {
                require(!state.ownedObjects.contains(base), "owning object lifetime already active");
                OwnedObjectBinding object{instructionId, ByteDisposition::Pristine, {}};
                for (std::size_t field = 0; field < logicalFields(name).size(); ++field)
                    if (logicalFields(name)[field].elementType.isOwnerStorage())
                        object.fields.emplace(static_cast<int>(field),
                                              ByteBinding{instructionId, ByteDisposition::Pristine, {}});
                state.ownedObjects.emplace(base, std::move(object));
            };
            auto mintObjectFields = [&](int base, const RegionIdentity &origin) {
                auto &object = state.ownedObjects.at(base);
                for (auto &[ordinal, field] : object.fields) {
                    field.token = freshToken(origin, ordinal);
                    field.disposition = ByteDisposition::Live;
                }
                object.disposition = ByteDisposition::Live;
            };
            auto mintLiveObject = [&](int base, const RegionIdentity &origin) {
                liveCopyTarget(base);
                mintObjectFields(base, origin);
            };
            auto consumeObject = [&](int base) {
                ownerWritable(base);
                auto &object = state.ownedObjects.at(base);
                object.disposition = ByteDisposition::Consumed;
                for (auto &[unused, field] : object.fields) {
                    (void)unused;
                    field.disposition = ByteDisposition::Consumed;
                    field.token.reset();
                }
            };
            auto ownedObjectRegion = [&](int base, bool mutableAccess) -> RegionIdentity {
                if (mutableAccess)
                    ownerWritable(base);
                const auto &object = state.ownedObjects.at(base);
                std::optional<RegionIdentity> origin;
                for (const auto &[unused, field] : object.fields) {
                    (void)unused;
                    require(field.token.has_value(), "owning object field missing token");
                    if (origin)
                        require(*origin == field.token->region, "owning object fields have different regions");
                    else
                        origin = field.token->region;
                }
                require(origin.has_value(), "owning object has no resource fields");
                return *origin;
            };
            auto ownedObject = [&](int base, const std::string &name, bool mutableAccess) -> RegionIdentity {
                const auto &slot = completeObject(base);
                require(slot.className == name && owningClass(metadata, name),
                        "owning object nominal class mismatch");
                require(!mutableAccess || slot.mutableValue, "const owning object cannot be moved or mutated");
                return ownedObjectRegion(base, mutableAccess);
            };
            auto liveResourceField = [&](int base, int ordinal, bool mutableAccess) -> const ByteBinding & {
                require(state.ownedObjects.contains(base), "resource field requires owning root");
                const auto &object = state.ownedObjects.at(base);
                require(object.disposition == ByteDisposition::Live && object.fields.contains(ordinal),
                        "resource field root is not complete and live");
                const auto &field = object.fields.at(ordinal);
                require(field.disposition == ByteDisposition::Live && field.token,
                        "resource field does not hold live ownership");
                if (base == 0)
                    require(field.token->region.borrowed, "borrowed receiver provenance mismatch");
                else
                    require(!field.token->region.borrowed && region(field.token->region.offset) == field.token->region,
                            "resource field region is not active");
                if (mutableAccess)
                    ownerWritable(base, ordinal);
                return field;
            };
            auto accessBytes = [&](int base, int ordinal, bool mutableAccess) -> const ByteBinding & {
                loanAccess(base, mutableAccess);
                require(ordinal >= -1, "invalid owned byte field selector");
                if (ordinal == -1)
                    return bytes(base, mutableAccess);
                require(base >= 0, "invalid owned byte object root");
                if (base == 0) {
                    const auto field = receiverShape(ordinal);
                    require(field.elementType.isOwnerStorage() && !field.array,
                            "owned byte access requires direct resource field");
                    require(!functionReceiver->constructor,
                            "constructor cannot access resource field during initialization");
                    require(!mutableAccess || functionReceiver->mutableValue,
                            "const receiver cannot mutate resource field");
                } else {
                    const auto &object = completeObject(base);
                    require(!mutableAccess || object.mutableValue, "const object cannot mutate resource field");
                    require(metadata.findClass(object.className) &&
                                static_cast<std::size_t>(ordinal) < logicalFields(object.className).size() &&
                                logicalFields(object.className)[ordinal].elementType.isOwnerStorage() &&
                                !logicalFields(object.className)[ordinal].array,
                            "owned byte access requires direct resource field");
                }
                return liveResourceField(base, ordinal, mutableAccess);
            };
            auto accessedOwnerType = [&](int base, int ordinal) {
                if (ordinal == -1)
                    return ownerType(base);
                require(ordinal >= 0 && base >= 0, "invalid owned storage field selector");
                const auto &name = base == 0 ? functionReceiver->className : objectSlots.at(base).className;
                const auto type = logicalFields(name).at(ordinal).elementType;
                verifyOwnerType(type, metadata);
                return type;
            };
            auto copiedValue = [&](int base, const Type &owner, int root) {
                require(base != root, "owned value snapshot aliases owner root");
                const auto &value = completeObject(base);
                require(owner.isOwnedValues() && value.className == owner.className,
                        "owned value snapshot nominal class mismatch");
                require(!value.mutableValue, "owned value snapshot must be readonly");
                require(state.objectClassesInitialized.contains({base, -1}),
                        "owned value snapshot requires complete copied or constructed value");
                require(!owningClass(metadata, value.className) && !carrier(value.className),
                        "owned value snapshot must be copied class");
            };
            auto publishOwnedBorrow = [&](int root, int ordinal, int result, const ByteBinding &binding) {
                const auto rootSite = ordinal == -1 ? binding.site : state.ownedObjects.at(root).site;
                state.activeSpans.emplace(
                    result, SpanCapability{false, root, rootSite, 0, 0, instructionId, binding.token, ordinal});
            };
            auto borrowOwned = [&](int root, int ordinal, int result) {
                const auto &binding = accessBytes(root, ordinal, false);
                require(accessedOwnerType(root, ordinal) == Type::OwnedBytes,
                        "typed owned values cannot supply a byte span");
                spanTarget(result);
                publishOwnedBorrow(root, ordinal, result, binding);
            };
            auto borrowLiveOwnedField = [&](int root, int ordinal, int result) {
                loanAccess(root, false);
                if (root > 0)
                    liveObject(root);
                const auto &binding = liveResourceField(root, ordinal, false);
                inactiveSpanTarget(result);
                publishOwnedBorrow(root, ordinal, result, binding);
            };
            auto initializedReceiverArray = [&](const ClassField &field) {
                for (int leaf = 0; leaf < field.length; ++leaf)
                    require(state.receiverInitialized.contains(field.firstLeaf + leaf),
                            "receiver array span requires complete initialization");
            };
            auto publishArrayBorrow = [&](int root, int ordinal, int result, InstructionId site) {
                state.activeSpans.emplace(
                    result, SpanCapability{false, root, site, 0, 0, instructionId, {}, -1, false, ordinal});
            };
            auto borrowReceiverArrayField = [&](int ordinal, int result) {
                require(ordinal >= 0, "invalid fixed array span root or field");
                loanAccess(0, false);
                const auto field = receiverShape(ordinal);
                require(!functionReceiver->constructor, "constructor cannot borrow receiver array");
                initializedReceiverArray(field);
                require(field.array && field.elementType == Type::U8,
                        "fixed array span requires direct u8 array field");
                spanTarget(result);
                publishArrayBorrow(0, ordinal, result, 0);
            };
            auto borrowLiveArrayField = [&](int root, int ordinal, int result) {
                loanAccess(root, false);
                InstructionId site = 0;
                if (root == 0)
                    initializedReceiverArray((*receiverFields)[ordinal]);
                else {
                    liveObject(root);
                    site = state.activeObjects.at(root);
                }
                inactiveSpanTarget(result);
                publishArrayBorrow(root, ordinal, result, site);
            };
            auto closedOwnedObjects = [&]() {
                require(state.serviceLoans.empty(), "return with active synchronous service loan");
                require(state.objectLoans.empty(), "return with active synchronous object loan");
                for (const auto &[base, unused] : state.ownedObjects) {
                    (void)unused;
                    require((base == 0 && functionReceiver.has_value()) ||
                                (base == -1 && secondReceiver.has_value()),
                            "return with active owning object lifetime");
                }
            };
            std::visit(
                [&](const auto &operation) {
                    using Op = std::decay_t<decltype(operation)>;
                    if constexpr (std::is_same_v<Op, Constant>) {
                        require(scalar(operation.type), "invalid constant type");
                        require(operation.type != Type::Bool || operation.value == 0 || operation.value == 1,
                                "noncanonical bool");
                        require(operation.type != Type::U8 || (operation.value >= 0 && operation.value <= 255),
                                "noncanonical u8");
                        state.current = Value{operation.type, {}};
                    } else if constexpr (std::is_same_v<Op, EnumConstant>) {
                        require(operation.type.isEnum() && scalarValueType(operation.type, metadata),
                                "invalid enum constant type");
                        require(operation.caseIndex >= 0 &&
                                    operation.caseIndex <
                                        metadata.enumCases(metadata.findEnum(operation.type.className).value()),
                                "enum constant is not a declared case");
                        state.current = Value{operation.type, {}};
                    } else if constexpr (std::is_same_v<Op, Load>) {
                        slot(operation.offset, operation.type);
                        activeObjectField(operation.offset);
                        activeArrayElement(operation.offset);
                        require(state.initialized.contains(operation.offset), "load before initialization");
                        state.current = Value{operation.type, {}};
                    } else if constexpr (std::is_same_v<Op, Store>) {
                        current(operation.type);
                        store(operation.offset, operation.type);
                    } else if constexpr (std::is_same_v<Op, Push>) {
                        require(state.current.has_value(), "push without current value");
                        state.stack.push_back(*state.current);
                        if (metrics)
                            metrics->peakOperandDepth = std::max(metrics->peakOperandDepth, state.stack.size());
                    } else if constexpr (std::is_same_v<Op, Pop>) {
                        state.current = pop();
                    } else if constexpr (std::is_same_v<Op, UnaryValue>) {
                        std::optional<Type> type;
                        switch (operation.operation) {
                        case Unary::CheckedNegate:
                            type = Type::I64;
                            break;
                        case Unary::LogicalNot:
                            type = Type::Bool;
                            break;
                        case Unary::BitNot:
                            require(operation.operandType == Type::U64 || operation.operandType == Type::U8,
                                    "invalid unary operand type");
                            type = operation.operandType;
                            break;
                        }
                        require(type.has_value(), "invalid unary operation");
                        require(operation.operandType == *type, "invalid unary operand type");
                        current(*type);
                        state.current = Value{*type, {}};
                    } else if constexpr (std::is_same_v<Op, BinaryValue>) {
                        bool valid = false;
                        bool unsignedOnly = false;
                        bool shift = false;
                        switch (operation.operation) {
                        case Binary::CheckedAdd:
                        case Binary::CheckedSubtract:
                        case Binary::CheckedMultiply:
                        case Binary::CheckedDivide:
                        case Binary::CheckedRemainder:
                            valid = true;
                            break;
                        case Binary::BitAnd:
                        case Binary::BitOr:
                        case Binary::BitXor:
                            valid = true;
                            unsignedOnly = true;
                            break;
                        case Binary::ShiftLeft:
                        case Binary::ShiftRight:
                            valid = true;
                            unsignedOnly = true;
                            shift = true;
                            break;
                        }
                        require(valid, "invalid binary operation");
                        require(operation.operandType == Type::U64 || operation.operandType == Type::U8 ||
                                    (!unsignedOnly && operation.operandType == Type::I64),
                                "invalid binary operand type");
                        current(shift ? Type::I64 : operation.operandType);
                        require(pop().type == operation.operandType, "noninteger left operand or binary type mismatch");
                        state.current = Value{operation.operandType, {}};
                    } else if constexpr (std::is_same_v<Op, Convert>) {
                        const auto integer = [](const Type &type) {
                            return type == Type::I64 || type == Type::U64 || type == Type::U8;
                        };
                        require(integer(operation.sourceType) && integer(operation.resultType) &&
                                    operation.sourceType != operation.resultType,
                                "invalid checked conversion types");
                        current(operation.sourceType);
                        // A value conversion never preserves an index's bounds evidence.
                        state.current = Value{operation.resultType, {}};
                    } else if constexpr (std::is_same_v<Op, Compare>) {
                        bool valid = false;
                        bool ordered = false;
                        switch (operation.operation) {
                        case Comparison::Equal:
                        case Comparison::NotEqual:
                            valid = true;
                            break;
                        case Comparison::Less:
                        case Comparison::Greater:
                        case Comparison::LessEqual:
                        case Comparison::GreaterEqual:
                            valid = true;
                            ordered = true;
                            break;
                        }
                        require(valid, "invalid comparison");
                        require(scalarValueType(operation.operandType, metadata), "non-scalar comparison");
                        if (ordered)
                            require(operation.operandType == Type::I64 || operation.operandType == Type::U64 ||
                                        operation.operandType == Type::U8,
                                    "ordered bool comparison or enum comparison");
                        current(operation.operandType);
                        require(pop().type == operation.operandType, "comparison type mismatch");
                        state.current = Value{Type::Bool, {}};
                    } else if constexpr (std::is_same_v<Op, BoundsGuard>) {
                        current(Type::I64);
                        array(operation.offset, operation.length, operation.elementType);
                        state.current =
                            Value{Type::I64, Guard{operation.offset, operation.length, operation.elementType}};
                    } else if constexpr (std::is_same_v<Op, IndexLoad>) {
                        array(operation.offset, operation.length, operation.elementType);
                        guard(current(Type::I64), operation.offset, operation.length, operation.elementType);
                        state.current = Value{operation.elementType, {}};
                    } else if constexpr (std::is_same_v<Op, IndexStore>) {
                        array(operation.offset, operation.length, operation.elementType);
                        current(operation.elementType);
                        guard(pop(), operation.offset, operation.length, operation.elementType);
                        for (int element = 0; element < operation.length; ++element) {
                            const int offset = operation.offset - element * storageWidth(operation.elementType);
                            arrayWritable(offset);
                            if (objectBases.contains(offset))
                                loanAccess(objectBases.at(offset), true);
                            require(!nestedObjectLeaves.contains(offset),
                                    "indexed store cannot write nested class field");
                            require(!entryBindings.contains<BindParameter>(offset),
                                    "indexed write to immutable scalar parameter");
                            require(!objectBases.contains(offset) || objectSlots.at(objectBases.at(offset)).mutableValue,
                                    "indexed write to const object field");
                        }
                    } else if constexpr (std::is_same_v<Op, BorrowHandle>) {
                        slot(operation.ownerOffset, Type::I64);
                        require(!objectBases.contains(operation.ownerOffset),
                                "object field cannot become a scalar borrow handle");
                        require(state.initialized.contains(operation.ownerOffset), "borrow of uninitialized payload");
                        require(operation.referenceType == Type::Ref || operation.referenceType == Type::MutRef,
                                "invalid borrow-handle type");
                        state.current = Value{operation.referenceType, {}};
                    } else if constexpr (std::is_same_v<Op, Call>) {
                        const auto target = metadata.callable(metadata.findCallable(operation.callee).value());
                        for (std::size_t argument = target.parameters().size(); argument > 0; --argument)
                            require(pop().type == target.parameters()[argument - 1], "call argument type mismatch");
                        state.current = Value{target.result(), {}};
                    } else if constexpr (std::is_same_v<Op, AggregateCallObservation>) {
                        const auto target = metadata.callable(metadata.findCallable(operation.callee).value());
                        for (std::size_t arg = target.parameters().size(); arg > 0; --arg) {
                            const auto &type = target.parameters()[arg - 1];
                            const int base = operation.objectArguments[arg - 1];
                            if (type.isSpan()) {
                                liveSpan(operation.spanArguments[arg - 1]);
                                continue;
                            }
                            if (scalarValueType(type, metadata)) {
                                require(pop().type == type, "aggregate scalar argument type mismatch");
                                continue;
                            }
                            liveCopiedArgument(base, type, "aggregate");
                        }
                        if (target.result().isClass()) {
                            const int base = operation.resultOffset;
                            const auto &object = objectSlots.at(base);
                            require(state.activeObjects.contains(base),
                                    "aggregate result outside active object lifetime");
                            require(!state.maybeConstructedObjects.contains(base),
                                    "aggregate result object already initialized");
                            const auto layout = classLeaves(object.className);
                            for (std::size_t field = 0; field < layout.size(); ++field)
                                require(!state.maybeInitialized.contains(objectLeaf(base, field)),
                                        "aggregate result requires uninitialized object");
                            markObject(base);
                            state.current.reset();
                        } else {
                            state.current = Value{target.result(), {}};
                        }
                    } else if constexpr (std::is_same_v<Op, ResourceCallObservation>) {
                        const auto target = metadata.callable(metadata.findCallable(operation.callee).value());
                        const bool constructor = target.receiver().has_value();
                        const auto origin = activeRegion(operation.regionOffset);
                        for (std::size_t arg = target.parameters().size(); arg > 0; --arg) {
                            const auto &type = target.parameters()[arg - 1];
                            const int base = operation.ownerArguments[arg - 1];
                            if (type.isOwnerStorage() || owningType(type)) {
                                RegionIdentity argumentOrigin;
                                if (type.isOwnerStorage()) {
                                    argumentOrigin = liveBytes(base).token->region;
                                    ownerWritable(base, -1);
                                } else {
                                    liveObject(base);
                                    argumentOrigin = ownedObjectRegion(base, true);
                                }
                                require(argumentOrigin == origin, "resource call owning argument has wrong region");
                            } else if (constructor && type.isClass()) {
                                liveObject(base);
                            } else if (arg > 1) {
                                require(pop().type == type, "resource call scalar argument type mismatch");
                            }
                        }
                        if (!constructor && target.result().isOwnerStorage()) {
                            pristineBytes(operation.resultOffset);
                        } else if (!constructor && target.result().isClass() && !owningType(target.result())) {
                            const int base = operation.resultOffset;
                            const auto &object = objectSlots.at(base);
                            require(state.activeObjects.contains(base),
                                    "resource copied result outside active object lifetime");
                            require(!state.maybeConstructedObjects.contains(base),
                                    "resource copied result object already initialized");
                            const auto layout = classLeaves(object.className);
                            for (std::size_t field = 0; field < layout.size(); ++field)
                                require(!state.maybeInitialized.contains(objectLeaf(base, field)),
                                        "resource copied result requires uninitialized object");
                        }
                        // The source admitted distinct storage. Revisit borrowed
                        // argument rows to transfer only the target's owner lanes.
                        for (std::size_t arg = 0; arg < target.parameters().size(); ++arg) {
                            const auto &type = target.parameters()[arg];
                            const int base = operation.ownerArguments[arg];
                            if (owningType(type))
                                consumeObject(base);
                            else if (type.isOwnerStorage()) {
                                ownerWritable(base, -1);
                                consumeByteBinding(activeByteBinding(base));
                            }
                        }
                        if (constructor) {
                            mintLiveObject(operation.receiverOffset, origin);
                            state.current = Value{target.result(), {}};
                        } else if (target.result().isOwnerStorage()) {
                            mintByteBinding(pristineBytes(operation.resultOffset), origin);
                            state.current.reset();
                        } else if (owningType(target.result())) {
                            mintLiveObject(operation.resultOffset, origin);
                            state.current.reset();
                        } else if (target.result().isClass()) {
                            // A complete pointer-free copy carries no owner token or region provenance.
                            markObject(operation.resultOffset);
                            state.current.reset();
                        } else
                            state.current = Value{target.result(), {}};
                    } else if constexpr (std::is_same_v<Op, BeginBytes>) {
                        require(byteSlots.contains(operation.offset),
                                "owned byte lifetime requires exact typed spill");
                        require(!entryBindings.contains<BindBytesParameter>(operation.offset),
                                "owned byte parameter lifetime cannot restart");
                        require(!state.activeBytes.contains(operation.offset), "owned byte lifetime already active");
                        state.activeBytes.emplace(
                            operation.offset, ByteBinding{instructionId, ByteDisposition::Pristine, {}});
                    } else if constexpr (std::is_same_v<Op, AllocateBytes>) {
                        require(ownerType(operation.resultOffset) == Type::OwnedBytes,
                                "byte allocation cannot initialize typed owned values");
                        current(Type::I64);
                        mintBytes(operation.resultOffset, region(operation.regionOffset));
                        state.current.reset();
                    } else if constexpr (std::is_same_v<Op, AllocateValues>) {
                        const auto type = ownerType(operation.resultOffset);
                        require(type.isOwnedValues(), "value allocation requires typed owner");
                        current(Type::I64);
                        copiedValue(operation.fillOffset, type, operation.resultOffset);
                        mintBytes(operation.resultOffset, region(operation.regionOffset));
                        state.current.reset();
                    } else if constexpr (std::is_same_v<Op, ValuesLoad>) {
                        accessBytes(operation.offset, operation.fieldIndex, false);
                        const auto type = accessedOwnerType(operation.offset, operation.fieldIndex);
                        require(type.isOwnedValues(), "value load requires typed owner");
                        current(Type::I64);
                        require(operation.resultOffset != operation.offset, "value load result aliases owner root");
                        copyTarget(operation.resultOffset, type.className);
                        state.current.reset();
                    } else if constexpr (std::is_same_v<Op, ValuesStore> || std::is_same_v<Op, ValuesResize>) {
                        accessBytes(operation.offset, operation.fieldIndex, true);
                        const auto type = accessedOwnerType(operation.offset, operation.fieldIndex);
                        require(type.isOwnedValues(), "value mutation requires typed owner");
                        current(Type::I64);
                        if constexpr (std::is_same_v<Op, ValuesStore>)
                            copiedValue(operation.valueOffset, type, operation.offset);
                        else
                            copiedValue(operation.fillOffset, type, operation.offset);
                        state.current = Value{Type::Bool, {}};
                    } else if constexpr (std::is_same_v<Op, MoveBytes>) {
                        require(operation.sourceOffset != operation.resultOffset,
                                "owned byte move source aliases result");
                        require(ownerType(operation.sourceOffset) == ownerType(operation.resultOffset),
                                "owner move nominal type mismatch");
                        const auto token = bytes(operation.sourceOffset, true).token;
                        auto &target = byteTarget(operation.resultOffset);
                        consumeBytes(operation.sourceOffset);
                        target.disposition = ByteDisposition::Live;
                        target.token = token;
                    } else if constexpr (std::is_same_v<Op, BytesOk> || std::is_same_v<Op, BytesLength>) {
                        accessBytes(operation.offset, operation.fieldIndex, false);
                        state.current = Value{std::is_same_v<Op, BytesOk> ? Type::Bool : Type::I64, {}};
                    } else if constexpr (std::is_same_v<Op, BytesLoad>) {
                        accessBytes(operation.offset, operation.fieldIndex, false);
                        require(accessedOwnerType(operation.offset, operation.fieldIndex) == Type::OwnedBytes,
                                "byte payload operation cannot access typed owned values");
                        current(Type::I64);
                        state.current = Value{Type::U8, {}};
                    } else if constexpr (std::is_same_v<Op, BytesStore>) {
                        accessBytes(operation.offset, operation.fieldIndex, true);
                        require(accessedOwnerType(operation.offset, operation.fieldIndex) == Type::OwnedBytes,
                                "byte payload operation cannot access typed owned values");
                        current(Type::U8);
                        require(pop().type == Type::I64, "owned byte store index requires i64");
                        state.current = Value{Type::Bool, {}};
                    } else if constexpr (std::is_same_v<Op, BytesResize>) {
                        accessBytes(operation.offset, operation.fieldIndex, true);
                        require(accessedOwnerType(operation.offset, operation.fieldIndex) == Type::OwnedBytes,
                                "byte payload operation cannot access typed owned values");
                        current(Type::I64);
                        state.current = Value{Type::Bool, {}};
                    } else if constexpr (std::is_same_v<Op, EndBytes>) {
                        byteBinding(operation.offset);
                        ownerWritable(operation.offset, -1);
                        state.activeBytes.erase(operation.offset);
                    } else if constexpr (std::is_same_v<Op, BeginArray> || std::is_same_v<Op, EndArray>) {
                        require(arraySlots.contains(operation.offset),
                                "array lifetime requires exact byte array origin");
                        if constexpr (std::is_same_v<Op, BeginArray>) {
                            require(!state.activeArrays.contains(operation.offset), "array lifetime already active");
                            state.activeArrays.emplace(operation.offset, instructionId);
                        } else {
                            require(state.activeArrays.contains(operation.offset), "array lifetime is not active");
                            for (const auto &[unused, capability] : state.activeSpans) {
                                (void)unused;
                                require(capability.literalOrigin || capability.ownedToken ||
                                            capability.parameterOrigin || capability.origin != operation.offset,
                                        "array lifetime ends with live readonly span");
                            }
                            state.activeArrays.erase(operation.offset);
                        }
                        for (int element = 0; element < arraySlots.at(operation.offset); ++element) {
                            state.initialized.erase(operation.offset - element);
                            state.maybeInitialized.erase(operation.offset - element);
                        }
                    } else if constexpr (std::is_same_v<Op, BorrowSpan>) {
                        require(arraySlots.contains(operation.arrayOffset),
                                "span borrow requires exact local byte array origin");
                        require(state.activeArrays.contains(operation.arrayOffset),
                                "span borrow requires active byte array origin");
                        array(operation.arrayOffset, arraySlots.at(operation.arrayOffset), Type::U8);
                        spanTarget(operation.resultOffset);
                        state.activeSpans.emplace(operation.resultOffset,
                                                  SpanCapability{false,
                                                                 operation.arrayOffset,
                                                                 state.activeArrays.at(operation.arrayOffset),
                                                                 0,
                                                                 0,
                                                                 instructionId});
                    } else if constexpr (std::is_same_v<Op, BorrowReceiverArraySpan>) {
                        borrowReceiverArrayField(operation.fieldIndex, operation.resultOffset);
                    } else if constexpr (std::is_same_v<Op, BorrowLiteralSpanObservation>) {
                        require(operation.bytes.size() <= maxByteStringBytes, "literal span exceeds byte-string bound");
                        spanTarget(operation.resultOffset);
                        state.activeSpans.emplace(
                            operation.resultOffset,
                            SpanCapability{
                                false, operation.resultOffset, instructionId, 0, 0, instructionId, {}, -1, true});
                    } else if constexpr (std::is_same_v<Op, BorrowOwnedSpan>) {
                        borrowOwned(operation.offset, operation.fieldIndex, operation.resultOffset);
                    } else if constexpr (std::is_same_v<Op, ReborrowSpan> || std::is_same_v<Op, Subspan>) {
                        if constexpr (std::is_same_v<Op, Subspan>) {
                            current(Type::I64);
                            require(pop().type == Type::I64, "subspan offset requires i64");
                            // A narrowed view creates no scalar bounds evidence.
                            state.current = Value{Type::I64, {}};
                        }
                        auto capability = span(operation.sourceOffset);
                        spanTarget(operation.resultOffset);
                        capability.parent = operation.sourceOffset;
                        capability.parentSite = capability.site;
                        capability.site = instructionId;
                        state.activeSpans.emplace(operation.resultOffset, capability);
                    } else if constexpr (std::is_same_v<Op, EndSpan>) {
                        span(operation.offset);
                        for (const auto &[unused, capability] : state.activeSpans) {
                            (void)unused;
                            require(capability.parent != operation.offset,
                                    "span lifetime ends with live child reborrow");
                        }
                        state.activeSpans.erase(operation.offset);
                    } else if constexpr (std::is_same_v<Op, SpanLength>) {
                        span(operation.offset);
                        state.current = Value{Type::I64, {}};
                    } else if constexpr (std::is_same_v<Op, SpanLoad>) {
                        span(operation.offset);
                        current(Type::I64);
                        state.current = Value{Type::U8, {}};
                    } else if constexpr (std::is_same_v<Op, BeginObject> || std::is_same_v<Op, EndObject>) {
                        require(objectSlots.contains(operation.offset),
                                "lifetime operation requires exact object slot");
                        if constexpr (std::is_same_v<Op, BeginObject>) {
                            require(!entryBindings.contains<BindObjectParameter, BindOwnedObjectParameter>(operation.offset),
                                    "object parameter lifetime cannot restart");
                            require(!state.activeObjects.contains(operation.offset), "object lifetime already active");
                            state.activeObjects.emplace(operation.offset, instructionId);
                            const auto &name = objectSlots.at(operation.offset).className;
                            if (owningClass(metadata, name))
                                beginOwnedObject(operation.offset, name);
                        } else {
                            require(state.activeObjects.contains(operation.offset), "object lifetime is not active");
                            ownerWritable(operation.offset);
                            state.activeObjects.erase(operation.offset);
                            state.ownedObjects.erase(operation.offset);
                        }
                        // A checked scalar index carries no escaping address, but its
                        // nominal evidence still belongs to this root lifetime.
                        auto invalidate = [&](Value &value) {
                            if (value.guard)
                                if (const auto *evidence = std::get_if<ClassArrayGuard>(&*value.guard);
                                    evidence && evidence->objectOffset == operation.offset)
                                    value.guard.reset();
                        };
                        if (state.current)
                            invalidate(*state.current);
                        for (auto &value : state.stack)
                            invalidate(value);
                        const auto &object = objectSlots.at(operation.offset);
                        const auto layout = classLeaves(object.className);
                        for (std::size_t field = 0; field < layout.size(); ++field) {
                            const int offset = objectLeaf(operation.offset, field);
                            state.initialized.erase(offset);
                            state.maybeInitialized.erase(offset);
                        }
                        state.maybeConstructedObjects.erase(operation.offset);
                        for (auto field = state.objectClassesInitialized.begin();
                             field != state.objectClassesInitialized.end();) {
                            if (field->first == operation.offset)
                                field = state.objectClassesInitialized.erase(field);
                            else
                                ++field;
                        }
                    } else if constexpr (std::is_same_v<Op, InitializeEmptyObject>) {
                        require(objectSlots.contains(operation.offset),
                                "empty initialization requires exact object slot");
                        const auto &name = objectSlots.at(operation.offset).className;
                        require(classLeaves(name).empty() && logicalFields(name).empty() &&
                                    !owningClass(metadata, name) && !carrier(name),
                                "empty initialization requires zero logical fields and leaves");
                        copyTarget(operation.offset, name);
                        state.current.reset();
                    } else if constexpr (std::is_same_v<Op, MoveObject>) {
                        require(operation.sourceOffset != operation.resultOffset,
                                "owning object move source aliases result");
                        const auto &source = completeObject(operation.sourceOffset);
                        ownedObject(operation.sourceOffset, source.className, true);
                        const auto fields = state.ownedObjects.at(operation.sourceOffset).fields;
                        copyTarget(operation.resultOffset, source.className);
                        consumeObject(operation.sourceOffset);
                        auto &destination = state.ownedObjects.at(operation.resultOffset);
                        destination.disposition = ByteDisposition::Live;
                        for (const auto &[ordinal, field] : fields) {
                            auto &target = destination.fields.at(ordinal);
                            target.disposition = ByteDisposition::Live;
                            target.token = field.token;
                        }
                        state.current.reset();
                    } else if constexpr (std::is_same_v<Op, InitializeBytesField>) {
                        require(operation.objectOffset == 0 && owningConstructor,
                                "resource field initialization requires bound owning constructor");
                        const auto shape = receiverShape(operation.fieldIndex);
                        require(shape.elementType.isOwnerStorage() && !shape.array,
                                "resource field initialization requires direct owner field");
                        require(ownerType(operation.sourceOffset) == shape.elementType,
                                "resource field initialization owner nominal type mismatch");
                        auto &target = state.ownedObjects.at(0).fields.at(operation.fieldIndex);
                        require(target.disposition == ByteDisposition::Pristine && !target.token,
                                "constructor resource field initialized more than once");
                        const auto token = bytes(operation.sourceOffset, true).token;
                        const auto boundRegion = entryBindings.region();
                        require(boundRegion && token->region == region(*boundRegion),
                                "constructor resource field has wrong region");
                        consumeBytes(operation.sourceOffset);
                        target.disposition = ByteDisposition::Live;
                        target.token = token;
                        state.current.reset();
                    } else if constexpr (std::is_same_v<Op, CopyObject>) {
                        require(operation.sourceOffset != operation.resultOffset, "copy source aliases result");
                        const auto &source = completeObject(operation.sourceOffset);
                        require(!owningClass(metadata, source.className),
                                "owning class cannot be implicitly copied");
                        copyTarget(operation.resultOffset, source.className);
                        state.current.reset();
                    } else if constexpr (std::is_same_v<Op, ObjectFieldCopy>) {
                        ClassField field{};
                        if (operation.sourceOffset == 0) {
                            field = receiverShape(operation.fieldIndex);
                            require(!functionReceiver->constructor,
                                    "constructor cannot project receiver during initialization");
                            require(state.receiverClassesInitialized.contains(operation.fieldIndex),
                                    "receiver nested class field not initialized");
                        } else {
                            require(operation.sourceOffset != operation.resultOffset,
                                    "projection source aliases result");
                            const auto &source = completeObject(operation.sourceOffset);
                            require(metadata.findClass(source.className) && operation.fieldIndex >= 0 &&
                                        static_cast<std::size_t>(operation.fieldIndex) <
                                            logicalFields(source.className).size(),
                                    "projection logical field index out of range");
                            field = logicalFields(source.className)[operation.fieldIndex];
                        }
                        require(!field.array && field.elementType.isClass(), "projection requires class field");
                        require(!owningClass(metadata, field.elementType.className),
                                "owning class field cannot be copied");
                        copyTarget(operation.resultOffset, field.elementType.className);
                        state.current.reset();
                    } else if constexpr (std::is_same_v<Op, AssignObjectField>) {
                        require(operation.objectOffset != operation.sourceOffset,
                                "class field assignment source aliases root");
                        const auto field = completeClassField(operation.objectOffset, operation.fieldIndex, true);
                        const auto &source = completeObject(operation.sourceOffset);
                        require(!owningClass(metadata, field.elementType.className),
                                "owning class field cannot be copied");
                        require(source.className == field.elementType.className,
                                "class field assignment nominal class mismatch");
                        // Both values were already complete; replacement cannot mint
                        // initialization evidence or create a separately live subobject.
                        state.current.reset();
                    } else if constexpr (std::is_same_v<Op, InitializeObjectField>) {
                        require(operation.objectOffset == 0,
                                "class field initialization requires bound constructor receiver");
                        const auto field = receiverShape(operation.fieldIndex);
                        require(functionReceiver->constructor && functionReceiver->mutableValue,
                                "class field initialization requires constructor receiver");
                        require(!field.array && field.elementType.isClass(),
                                "class field initialization requires class field");
                        const auto &source = completeObject(operation.sourceOffset);
                        require(!owningClass(metadata, field.elementType.className),
                                "owning class field cannot be copied");
                        require(source.className == field.elementType.className,
                                "class field initializer nominal class mismatch");
                        require(!state.receiverClassesMaybeInitialized.contains(operation.fieldIndex),
                                "constructor class field initialized more than once");
                        for (int leaf = 0; leaf < field.length; ++leaf) {
                            require(!state.receiverMaybeInitialized.contains(field.firstLeaf + leaf),
                                    "constructor class field leaves already initialized");
                            state.receiverInitialized.insert(field.firstLeaf + leaf);
                            state.receiverMaybeInitialized.insert(field.firstLeaf + leaf);
                        }
                        state.receiverClassesInitialized.insert(operation.fieldIndex);
                        state.receiverClassesMaybeInitialized.insert(operation.fieldIndex);
                        state.current.reset();
                    } else if constexpr (std::is_same_v<Op, InitializeClassArrayObservation>) {
                        require(operation.objectOffset >= 0, "invalid class array initialization root");
                        ClassField field{};
                        if (operation.objectOffset == 0) {
                            field = receiverShape(operation.fieldIndex);
                            require(functionReceiver->constructor && functionReceiver->mutableValue,
                                    "class array initialization requires constructor receiver");
                        } else {
                            require(objectSlots.contains(operation.objectOffset),
                                    "class array initialization requires exact object slot");
                            const auto &name = objectSlots.at(operation.objectOffset).className;
                            require(carrier(name) && operation.fieldIndex == 0,
                                    "local class array initialization requires declared carrier field");
                            field = logicalFields(name).front();
                        }
                        require(field.array && field.elementType.isClass(),
                                "class array initialization requires class array field");
                        require(operation.sources.size() == static_cast<std::size_t>(field.elementCount),
                                "class array initializer element count mismatch");
                        for (int sourceOffset : operation.sources) {
                            require(sourceOffset != operation.objectOffset,
                                    "class array initialization source aliases root");
                            const auto &source = completeObject(sourceOffset);
                            require(source.className == field.elementType.className,
                                    "class array initializer nominal class mismatch");
                        }
                        if (operation.objectOffset == 0) {
                            require(!state.receiverClassesMaybeInitialized.contains(operation.fieldIndex),
                                    "constructor class array initialized more than once");
                            for (int leaf = 0; leaf < field.length; ++leaf) {
                                const int ordinal = field.firstLeaf + leaf;
                                require(!state.receiverMaybeInitialized.contains(ordinal),
                                        "constructor class array leaves already initialized");
                                state.receiverInitialized.insert(ordinal);
                                state.receiverMaybeInitialized.insert(ordinal);
                            }
                            state.receiverClassesInitialized.insert(operation.fieldIndex);
                            state.receiverClassesMaybeInitialized.insert(operation.fieldIndex);
                        } else {
                            copyTarget(operation.objectOffset,
                                       objectSlots.at(operation.objectOffset).className);
                        }
                        state.current.reset();
                    } else if constexpr (std::is_same_v<Op, ClassArrayBoundsGuard>) {
                        const auto field = completeClassArray(operation.objectOffset, operation.fieldIndex, false);
                        current(Type::I64);
                        state.current =
                            Value{Type::I64, classArrayEvidence(operation.objectOffset, operation.fieldIndex, field)};
                    } else if constexpr (std::is_same_v<Op, ClassArrayCopy>) {
                        const auto field = completeClassArray(operation.objectOffset, operation.fieldIndex, false);
                        checkedClassArray(operation.objectOffset, operation.fieldIndex, field);
                        require(operation.objectOffset != operation.resultOffset,
                                "class array projection source aliases result");
                        copyTarget(operation.resultOffset, field.elementType.className);
                        state.current.reset();
                    } else if constexpr (std::is_same_v<Op, ClassArrayAssign>) {
                        const auto field = completeClassArray(operation.objectOffset, operation.fieldIndex, true);
                        checkedClassArray(operation.objectOffset, operation.fieldIndex, field);
                        require(operation.objectOffset != operation.sourceOffset,
                                "class array assignment source aliases root");
                        const auto &source = completeObject(operation.sourceOffset);
                        require(source.className == field.elementType.className,
                                "class array assignment nominal class mismatch");
                        // Replacement cannot establish completion or create a live
                        // subobject. Only already complete independent values enter.
                        state.current.reset();
                    } else if constexpr (std::is_same_v<Op, ReceiverLoad>) {
                        const auto field = receiverField(operation.fieldIndex, operation.type);
                        require(!functionReceiver->constructor,
                                "constructor cannot read receiver during initialization");
                        require(state.receiverInitialized.contains(field.firstLeaf), "receiver field not initialized");
                        state.current = Value{operation.type, {}};
                    } else if constexpr (std::is_same_v<Op, ReceiverStore>) {
                        const auto field = receiverField(operation.fieldIndex, operation.type);
                        current(operation.type);
                        require(functionReceiver->mutableValue, "write through const receiver");
                        if (functionReceiver->constructor)
                            require(!state.receiverMaybeInitialized.contains(field.firstLeaf),
                                    "constructor field initialized more than once");
                        state.receiverInitialized.insert(field.firstLeaf);
                        state.receiverMaybeInitialized.insert(field.firstLeaf);
                    } else if constexpr (std::is_same_v<Op, ReceiverArrayZero>) {
                        const auto field = receiverArray(operation.fieldIndex, false);
                        require(functionReceiver->constructor && functionReceiver->mutableValue,
                                "receiver array zero requires constructor receiver");
                        for (int element = 0; element < field.length; ++element) {
                            const int leaf = field.firstLeaf + element;
                            require(!state.receiverMaybeInitialized.contains(leaf),
                                    "constructor array initialized more than once");
                            state.receiverInitialized.insert(leaf);
                            state.receiverMaybeInitialized.insert(leaf);
                        }
                    } else if constexpr (std::is_same_v<Op, ReceiverBoundsGuard>) {
                        const auto field = receiverArray(operation.fieldIndex, true);
                        current(Type::I64);
                        state.current = Value{Type::I64, receiverEvidence(operation.fieldIndex, field)};
                    } else if constexpr (std::is_same_v<Op, ReceiverIndexLoad>) {
                        const auto field = receiverArray(operation.fieldIndex, true);
                        receiverGuard(current(Type::I64), operation.fieldIndex, field);
                        state.current = Value{field.elementType, {}};
                    } else if constexpr (std::is_same_v<Op, ReceiverIndexStore>) {
                        const auto field = receiverArray(operation.fieldIndex, true);
                        require(functionReceiver->mutableValue, "write through const receiver");
                        current(field.elementType);
                        receiverGuard(pop(), operation.fieldIndex, field);
                        ownerWritable(0, operation.fieldIndex);
                    } else if constexpr (std::is_same_v<Op, AcquireObjectLoan>) {
                        require(operation.loanId > 0 && !state.objectLoans.contains(operation.loanId),
                                "invalid or duplicate object loan identity");
                        require(operation.root >= 0 ||
                                    (operation.root == -1 && secondReceiver.has_value()),
                                "invalid borrowed object root");
                        loanAccess(operation.root, operation.mutableValue);
                        std::string name;
                        if (operation.root <= 0) {
                            require(signature.borrowedParameter() && functionReceiver,
                                    "root zero loan requires named borrowed formal");
                            const auto &formal = boundRoot(operation.root);
                            require(!operation.mutableValue || formal.mutableValue,
                                    "shared formal cannot supply mutable object loan");
                            name = formal.className;
                        } else {
                            const auto &object = completeObject(operation.root);
                            require(!operation.mutableValue || object.mutableValue,
                                    "const object cannot supply mutable object loan");
                            name = object.className;
                        }
                        const auto &object = liveOwningRoot(operation.root);
                        if (operation.mutableValue)
                            ownerWritable(operation.root);
                        state.objectLoans.emplace(
                            operation.loanId,
                            ObjectLoan{operation.root, object.site, name, operation.mutableValue, false});
                    } else if constexpr (std::is_same_v<Op, ReleaseObjectLoan>) {
                        require(state.objectLoans.contains(operation.loanId), "release requires active object loan");
                        require(state.objectLoans.at(operation.loanId).called,
                                "object loan release requires completed borrowed call");
                        state.objectLoans.erase(operation.loanId);
                    } else if constexpr (std::is_same_v<Op, MethodCallObservation> ||
                                         std::is_same_v<Op, BorrowedCallObservation>) {
                        const auto target = metadata.callable(metadata.findCallable(operation.callee).value());
                        if constexpr (std::is_same_v<Op, BorrowedCallObservation>) {
                            auto useLoan = [&](int id, int root, const Receiver &formal) {
                                require(state.objectLoans.contains(id), "borrowed call requires active loan");
                                auto &loan = state.objectLoans.at(id);
                                require(!loan.called, "object loan already used by a call");
                                require(loan.root == root && loan.className == formal.className &&
                                            loan.mutableValue == formal.mutableValue &&
                                            state.ownedObjects.contains(root) &&
                                            state.ownedObjects.at(root).site == loan.rootSite &&
                                            state.ownedObjects.at(root).disposition == ByteDisposition::Live,
                                        "borrowed call root, lifetime, nominal type or authority mismatch");
                                if (root > 0)
                                    liveObject(root);
                                liveOwnedRoot(root);
                                loanAccess(root, formal.mutableValue);
                                loan.called = true;
                            };
                            useLoan(operation.loanId, operation.receiverOffset, *target.receiver());
                            if (target.secondBorrowedParameter())
                                useLoan(operation.secondLoanId,
                                        operation.secondReceiverOffset,
                                        *target.secondBorrowedParameter());
                        } else {
                            loanAccess(operation.receiverOffset, target.receiver()->mutableValue);
                        }
                        const auto receiver = *target.receiver();
                        for (std::size_t arg = target.parameters().size(); arg > 0; --arg) {
                            const auto &type = target.parameters()[arg - 1];
                            if (type.isSpan()) {
                                liveSpan(operation.spanArguments[arg - 1]);
                            } else if (scalarValueType(type, metadata)) {
                                require(pop().type == type, "method argument type mismatch");
                            } else {
                                liveObject(operation.objectArguments[arg - 1]);
                            }
                        }
                        if (receiver.mutableValue)
                            ownerWritable(operation.receiverOffset);
                        if (operation.receiverFieldIndex >= 0) {
                            liveClassField(operation.receiverOffset, operation.receiverFieldIndex, receiver.mutableValue);
                        } else if (operation.receiverOffset > 0) {
                            const auto &object = objectSlots.at(operation.receiverOffset);
                            require(state.activeObjects.contains(operation.receiverOffset),
                                    "method receiver outside active object lifetime");
                            const auto layout = classLeaves(object.className);
                            if (receiver.constructor) {
                                require(!state.maybeConstructedObjects.contains(operation.receiverOffset),
                                        "object constructor called more than once");
                                for (std::size_t field = 0; field < layout.size(); ++field)
                                    require(
                                        !state.maybeInitialized.contains(objectLeaf(operation.receiverOffset, field)),
                                        "constructor requires uninitialized object");
                                markObject(operation.receiverOffset);
                            } else {
                                for (std::size_t field = 0; field < layout.size(); ++field)
                                    require(state.initialized.contains(objectLeaf(operation.receiverOffset, field)),
                                            "method receiver object not fully initialized");
                                logicalComplete(operation.receiverOffset);
                            }
                        }
                        if (target.result() == Type::ByteSpan) {
                            const auto field = logicalFields(receiver.className).at(*target.receiverSpanField());
                            if (field.array)
                                borrowLiveArrayField(
                                    operation.receiverOffset, *target.receiverSpanField(), operation.resultOffset);
                            else
                                borrowLiveOwnedField(
                                    operation.receiverOffset, *target.receiverSpanField(), operation.resultOffset);
                            state.current.reset();
                        } else if (target.result().isClass()) {
                            const int base = operation.resultOffset;
                            const auto &object = objectSlots.at(base);
                            require(state.activeObjects.contains(base), "method result outside active object lifetime");
                            require(!state.maybeConstructedObjects.contains(base),
                                    "method result object already initialized");
                            const auto layout = classLeaves(object.className);
                            for (std::size_t field = 0; field < layout.size(); ++field)
                                require(!state.maybeInitialized.contains(objectLeaf(base, field)),
                                        "method result requires uninitialized object");
                            markObject(base);
                            state.current.reset();
                        } else {
                            state.current = Value{target.result(), {}};
                        }
                    } else if constexpr (std::is_same_v<Op, MetadataQuery>) {
                        require(operation.query == Query::Size || operation.query == Query::PublicFieldCount,
                                "unknown metadata query");
                        require(operation.moduleScope == signature.moduleScope(),
                                "metadata query changes defining-module scope");
                        current(Type::I64);
                        state.current = Value{Type::I64, {}};
                    } else if constexpr (std::is_same_v<Op, Label> || std::is_same_v<Op, Jump>) {
                        // Nonempty expression stacks retain exact type and guard
                        // equality at every join, including loop backedges.
                    } else if constexpr (std::is_same_v<Op, BranchFalse>) {
                        current(Type::Bool);
                    } else if constexpr (std::is_same_v<Op, Return>) {
                        require(scalarValueType(signature.result(), metadata),
                                "scalar return cannot return class value or resource value");
                        current(signature.result());
                        require(state.stack.empty(), "unbalanced stack at return");
                        require(state.activeBytes.empty(), "return with active owned byte lifetime");
                        closedOwnedObjects();
                        require(state.activeSpans.empty() && state.activeArrays.empty(),
                                "return with active span or byte array lifetime");
                        if (functionReceiver && functionReceiver->constructor) {
                            require(state.receiverInitialized.size() == receiverLayout->size(),
                                    "constructor returns before all fields initialized");
                            for (std::size_t field = 0; field < receiverFields->size(); ++field)
                                if ((*receiverFields)[field].elementType.isClass())
                                    require(state.receiverClassesInitialized.contains(static_cast<int>(field)),
                                            "constructor returns before all class fields initialized");
                        }
                        if (owningConstructor) {
                            const auto boundRegion = entryBindings.region();
                            require(boundRegion.has_value(), "owning constructor lacks region");
                            for (const auto &[unused, field] : state.ownedObjects.at(0).fields) {
                                (void)unused;
                                require(field.disposition == ByteDisposition::Live && field.token &&
                                            field.token->region == region(*boundRegion),
                                        "constructor returns before all resource fields initialized");
                            }
                        }
                    } else if constexpr (std::is_same_v<Op, ReturnSpan>) {
                        require(signature.result() == Type::ByteSpan && signature.receiverSpanField() && functionReceiver &&
                                    !functionReceiver->constructor && !functionReceiver->mutableValue,
                                "span return requires const owning receiver field summary");
                        const auto &capability = span(operation.offset);
                        const bool fixed = receiverShape(*signature.receiverSpanField()).array;
                        const auto token = fixed ? std::optional<ByteToken>{}
                                                 : accessBytes(0, *signature.receiverSpanField(), false).token;
                        auto matchesReceiver = [&](const SpanCapability &view) {
                            return view.origin == 0 && !view.parameterOrigin && !view.literalOrigin &&
                                   (fixed ? view.arrayField == *signature.receiverSpanField() && !view.ownedToken
                                          : view.arrayField == -1 && view.ownedField == *signature.receiverSpanField() &&
                                                view.ownedToken == token && token && token->region.borrowed);
                        };
                        require(matchesReceiver(capability),
                                "span return does not match receiver field summary and token");
                        require(state.stack.empty(), "unbalanced stack at span return");
                        require(state.activeBytes.empty() && state.activeArrays.empty() && state.activeObjects.empty(),
                                "span return with unrelated active local lifetime");
                        closedOwnedObjects();
                        // The returned record and its exact receiver-derived ancestor
                        // chain remain live until the hidden result is copied. Other
                        // views require explicit cleanup, even when they borrow this.
                        std::set<int> retained;
                        for (int base = operation.offset; base != 0; base = span(base).parent)
                            require(retained.insert(base).second, "cyclic returned span parent chain");
                        for (const auto &[base, active] : state.activeSpans) {
                            span(base);
                            require(retained.contains(base) && matchesReceiver(active),
                                    "span return with unrelated active span lifetime");
                        }
                    } else if constexpr (std::is_same_v<Op, ReturnObject>) {
                        require(signature.result().isClass() && !owningType(signature.result()),
                                "object return requires class result; owning classes require an explicit move return");
                        require(objectSlots.contains(operation.offset),
                                "object return requires exact object slot");
                        const auto &object = objectSlots.at(operation.offset);
                        require(object.className == signature.result().className, "object return nominal class mismatch");
                        require(state.activeObjects.contains(operation.offset),
                                "object return outside active lifetime");
                        const auto layout = classLeaves(object.className);
                        for (std::size_t field = 0; field < layout.size(); ++field)
                            require(state.initialized.contains(objectLeaf(operation.offset, field)),
                                    "returned object not fully initialized");
                        logicalComplete(operation.offset);
                        require(state.stack.empty(), "unbalanced stack at object return");
                        require(state.activeBytes.empty(), "return with active owned byte lifetime");
                        closedOwnedObjects();
                        require(state.activeSpans.empty() && state.activeArrays.empty(),
                                "return with active span or byte array lifetime");
                    } else if constexpr (std::is_same_v<Op, ReturnOwnedObject>) {
                        require(!functionReceiver && owningType(signature.result()),
                                "owning object return requires ordinary owning class result");
                        const auto boundRegion = entryBindings.region();
                        require(boundRegion.has_value(), "owning object return requires bound region");
                        require(ownedObject(operation.offset, signature.result().className, true) ==
                                    region(*boundRegion),
                                "owning object return has wrong region");
                        state.ownedObjects.erase(operation.offset);
                        state.activeObjects.erase(operation.offset);
                        closedOwnedObjects();
                        require(state.activeBytes.empty(), "return with active owned byte lifetime");
                        require(state.activeSpans.empty() && state.activeArrays.empty(),
                                "return with active span or byte array lifetime");
                        require(state.stack.empty(), "unbalanced stack at owning object return");
                    } else if constexpr (std::is_same_v<Op, ReturnBytes>) {
                        require(signature.result().isOwnerStorage() && ownerType(operation.offset) == signature.result(),
                                "owner return nominal type mismatch");
                        const auto boundRegion = entryBindings.region();
                        require(boundRegion.has_value(), "owned byte return requires bound region parameter");
                        require(bytes(operation.offset, true).token->region == region(*boundRegion),
                                "owned byte return has wrong region");
                        state.activeBytes.erase(operation.offset);
                        require(state.activeBytes.empty(), "return with active owned byte lifetime");
                        closedOwnedObjects();
                        require(state.activeSpans.empty() && state.activeArrays.empty(),
                                "return with active span or byte array lifetime");
                        require(state.stack.empty(), "unbalanced stack at owned byte return");
                    } else if constexpr (std::is_same_v<Op, BindServiceParameter>) {
                        require(!state.activeServices.contains(operation.offset),
                                "service parameter authority already active");
                        state.activeServices.emplace(operation.offset, ServiceIdentity{instructionId, operation.kind});
                    } else if constexpr (std::is_same_v<Op, AcquireServiceLoan>) {
                        require(operation.loanId > 0 && !state.serviceLoans.contains(operation.loanId) &&
                                    std::none_of(state.serviceLoans.begin(),
                                                 state.serviceLoans.end(),
                                                 [&](const auto &loan) {
                                                     return loan.second.offset == operation.offset;
                                                 }) &&
                                    state.activeServices.contains(operation.offset) &&
                                    state.activeServices.at(operation.offset).kind == operation.kind,
                                "service loan requires unsuspended parameter authority");
                        state.serviceLoans.emplace(
                            operation.loanId,
                            ServiceLoan{operation.offset, state.activeServices.at(operation.offset), false});
                    } else if constexpr (std::is_same_v<Op, ReleaseServiceLoan>) {
                        require(state.serviceLoans.contains(operation.loanId) &&
                                    state.serviceLoans.at(operation.loanId).called &&
                                    state.serviceLoans.at(operation.loanId).identity.kind == operation.kind,
                                "service release requires exactly one completed helper call");
                        state.serviceLoans.erase(operation.loanId);
                    } else if constexpr (std::is_same_v<Op, ServiceOperation>) {
                        require(state.activeServices.contains(operation.offset) &&
                                    std::none_of(state.serviceLoans.begin(),
                                                 state.serviceLoans.end(),
                                                 [&](const auto &loan) {
                                                     return loan.second.offset == operation.offset;
                                                 }),
                                "service operation requires active unsuspended capability provenance");
                        require(state.activeServices.at(operation.offset).kind == operation.kind &&
                                    service::description(operation.operation).kind == operation.kind,
                                "service operation kind does not match active capability");
                        if (operation.operation == service::Operation::Pixel) {
                            for (int argument = 4; argument >= 0; --argument)
                                require(pop().type == (argument < 2 ? Type::U64 : Type::U8),
                                        "pixel argument type mismatch");
                            require(operation.resultOffset == 0 &&
                                        metadata.findEnum(std::string(service::displayPutResultName)),
                                    "pixel requires closed enum result and no object storage");
                            state.current = Value{service::displayPutResultType(), {}};
                        } else if (operation.operation == service::Operation::Put) {
                            current(Type::U8);
                            require(operation.resultOffset == 0 &&
                                        metadata.findEnum(std::string(service::putResultName)),
                                    "put requires closed enum result and no object storage");
                            state.current = Value{service::putResultType(), {}};
                        } else if (operation.operation == service::Operation::IommuAcknowledge) {
                            require(operation.resultOffset == 0 &&
                                        metadata.findEnum(std::string(service::eventAckResultName)),
                                    "acknowledge requires closed enum result and no object storage");
                            state.current = Value{service::eventAckResultType(), {}};
                        } else if (operation.operation == service::Operation::Next ||
                                   operation.operation == service::Operation::IommuPoll) {
                            const bool event = operation.operation == service::Operation::IommuPoll;
                            const auto reportName = event ? service::eventSampleName : service::sampleName;
                            const int base = operation.resultOffset;
                            require(objectSlots.contains(base) &&
                                        objectSlots.at(base).className == reportName &&
                                        state.activeObjects.contains(base) &&
                                        !state.maybeConstructedObjects.contains(base),
                                    "service observation requires exact pristine active copied sample object");
                            for (std::size_t field = 0; field < (event ? 4u : 3u); ++field)
                                require(!state.maybeInitialized.contains(objectLeaf(base, field)),
                                        "service observation cannot overwrite initialized sample storage");
                            markObject(base);
                            state.current.reset();
                        } else {
                            require(false, "unknown sealed service operation");
                        }
                    } else if constexpr (std::is_same_v<Op, ServiceCallObservation>) {
                        const auto target = metadata.callable(metadata.findCallable(operation.callee).value());
                        const auto argumentAt = [&](std::size_t position) {
                            return position == 0 ? ServiceArgument{operation.loanId, operation.kind}
                                                 : operation.additionalServices.at(position - 1);
                        };
                        const auto count = static_cast<std::size_t>(
                            std::count_if(target.parameters().begin(), target.parameters().end(), [](const Type &type) {
                                return type.isService();
                            }));
                        // Distinct explicit IDs are source facts; distinct roots
                        // depend on the loans active along this executed path.
                        std::set<int> usedRoots;
                        for (std::size_t position = 0; position < count; ++position) {
                            const auto argument = argumentAt(position);
                            require(state.serviceLoans.contains(argument.loanId),
                                    "service helper requires distinct acquired loans in leading positions");
                            auto &loan = state.serviceLoans.at(argument.loanId);
                            require(!loan.called && usedRoots.insert(loan.offset).second &&
                                        state.activeServices.contains(loan.offset) &&
                                        state.activeServices.at(loan.offset) == loan.identity &&
                                        loan.identity.kind == argument.kind,
                                    "service helper requires an unused loan with exact provenance");
                        }
                        for (std::size_t reverse = target.parameters().size(); reverse > count; --reverse) {
                            const auto position = reverse - 1;
                            const auto &type = target.parameters()[position];
                            const int base = operation.spanArguments[position];
                            if (type.isSpan()) {
                                require(state.activeSpans.contains(base), "service span argument is not active");
                                liveSpan(base);
                            } else if (type.isClass()) {
                                liveCopiedArgument(operation.objectArguments[position], type, "service");
                            } else {
                                require(pop().type == type, "service scalar argument mismatch");
                            }
                        }
                        if (target.result().isClass()) {
                            // Signature validation applies the ordinary copied-value
                            // bounds; use its full nominal layout, including empty
                            // and nested completion facts, for the fresh destination.
                            liveCopyTarget(operation.resultOffset);
                            state.current.reset();
                        } else {
                            state.current = Value{target.result(), {}};
                        }
                        for (std::size_t position = 0; position < count; ++position)
                            state.serviceLoans.at(argumentAt(position).loanId).called = true;
                    } else if constexpr (std::is_same_v<Op, BindRegionParameter>) {
                        require(state.activeRegions.empty(), "region parameter authority already active");
                        state.activeRegions.emplace(operation.offset, RegionIdentity{operation.offset, instructionId});
                    } else if constexpr (std::is_same_v<Op, BindBytesParameter>) {
                        require(!state.activeBytes.contains(operation.offset),
                                "owned byte parameter lifetime already active");
                        const auto token = freshToken(activeRegion(*entryBindings.region()), -1);
                        state.activeBytes.emplace(
                            operation.offset, ByteBinding{instructionId, ByteDisposition::Live, token});
                    } else if constexpr (std::is_same_v<Op, BindSpanParameter>) {
                        require(!state.activeSpans.contains(operation.offset),
                                "span parameter lifetime already active");
                        state.activeSpans.emplace(
                            operation.offset, SpanCapability{true, operation.index, instructionId, 0, 0, instructionId});
                    } else if constexpr (std::is_same_v<Op, BindOwnedObjectParameter>) {
                        require(!state.activeObjects.contains(operation.offset),
                                "owning class parameter lifetime already active");
                        state.activeObjects.emplace(operation.offset, instructionId);
                        beginOwnedObject(operation.offset, operation.className);
                        initializeObject(operation.offset);
                        mintObjectFields(operation.offset, activeRegion(*entryBindings.region()));
                    } else if constexpr (std::is_same_v<Op, BindObjectParameter>) {
                        require(!state.activeObjects.contains(operation.offset),
                                "object parameter lifetime already active");
                        state.activeObjects.emplace(operation.offset, instructionId);
                        markObject(operation.offset);
                    } else if constexpr (std::is_same_v<Op, BindParameter>) {
                        require(!state.maybeInitialized.contains(operation.offset),
                                "write to immutable scalar parameter");
                        state.initialized.insert(operation.offset);
                        state.maybeInitialized.insert(operation.offset);
                    } else {
                        static_assert(!std::is_same_v<Op, Op>, "unhandled typed IR verifier operation");
                    }
                },
                instruction);
            stackAfter[index] = state.stack.size();
            // Preserve target-before-fallthrough scheduling. Successors and
            // block boundaries are copied source facts, not opcode decisions.
            if (flow.target)
                enqueue(*flow.target, state);
            if (!flow.fallsThrough)
                break;
            ++index;
            if (function.code.flowAt(index).blockEntry) {
                enqueue(index, state);
                break;
            }
        }
    }
    std::size_t emittedDepth = 0;
    for (CodePosition index = 0; index < function.code.size(); ++index) {
        // The backend counts push/pop effects in emitted order. Certify
        // that order separately from CFG joins; arbitrary non-linear stack
        // layouts are unsupported. Never reset this counter at a label.
        require(stackBefore[index] == emittedDepth, "operand stack depth differs from linear emission order");
        emittedDepth = stackAfter[index];
    }
}
inline void verifyFunctions(std::vector<FunctionBody> &input, const Metadata &metadata,
                            Metrics *metrics = nullptr) {
    require(input.size() == metadata.callableCount(), "callable body count mismatch");
    for (std::size_t index = 0; index < input.size(); ++index) {
        // This is the executable-to-metadata association, not signature admission.
        // Original declaration IDs remain stable after graph pruning below.
        require(input[index].callableId == index, "callable body ID does not match declaration order");
        verifyFunction(input[index], metadata, metrics);
    }
    verifyHostedGraph(input, metadata);
}
} // namespace verification
inline ValidatedModule validate(Module module, verification::Metrics *metrics) {
    // Import consumes and destroys all raw fixture construction before either
    // independent admission. Only the paired Aurora-owned bundle returns.
    auto pending = InstructionIngress::import(std::move(module));
    return validate(std::move(pending), metrics);
}
inline ValidatedModule validate(InstructionIngress pending, verification::Metrics *metrics) {
    // Finish metadata first; then source generic instruction admission checks
    // suffix tails before codec reconstruction can discard unresolved payloads.
    auto metadata = std::move(pending.metadata_).finish();
    auto instructions = std::move(pending.instructions_);
    if (!instructions)
        throw Error(DiagnosticCode::Internal, "missing hosted IR instruction ingress");
    instructions->admit(*metadata);
    // Source checks every CFG, then every normalized entry binding, then every
    // immutable call contract before allocating native value-state arrays.
    instructions->structure();
    std::vector<FunctionBody> functions;
    functions.reserve(instructions->bodyCount());
    for (std::size_t id = 0; id < instructions->bodyCount(); ++id)
        functions.push_back({id, instructions->range(id)});
    // Native value semantics and the existing graph seam consume source rows
    // already frozen at structured status. Publication records their completion.
    verification::verifyFunctions(functions, *metadata, metrics);
    instructions->publish();
    return ValidatedModule(std::move(functions), std::move(metadata), std::move(instructions));
}
} // namespace aurora::ir
