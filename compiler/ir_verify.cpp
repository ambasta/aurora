#include "ir_verify.hpp"
#include "hosted_graph.hpp"
#include "hosted_ir_instructions.hpp"
#include "hosted_ir_initialization.hpp"
#include "ir_layout.hpp"
#include "byte_literal.hpp"
#include <algorithm>
#include <cstdint>
#include <deque>
#include <functional>
#include <type_traits>

namespace aurora::ir {
namespace verification {
namespace {
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
class State {
public:
    std::optional<Value> current;
    std::vector<Value> stack;
    std::map<int, InstructionId> activeObjects; // object base -> creation/binding site
    std::map<int, InstructionId> activeArrays;  // array base -> BeginArray site
    std::map<int, SpanCapability> activeSpans;
    std::map<int, ByteBinding> activeBytes;
    std::map<int, ObjectLoan> objectLoans;
    std::map<int, OwnedObjectBinding> ownedObjects; // 0/-1 are the two distinct bound roots
    bool operator==(const State &) const = default;
};
// Initialization, logical completion and service loans have one source owner. Its retained ordinal
// belongs to the block entry, never to native State equality or State copies.
class BlockEntry {
public:
    State state;
    InitializationWorkspace::Id initialization;
};
inline void require(bool condition, const std::string &message) {
    if (!condition)
        fail(message);
}
inline bool scalarValueType(const Type &type, const Metadata &metadata) {
    return scalar(type) ||
           (type.isEnum() && type == Type::enumeration(type.className) && metadata.findEnum(type.className));
}
// Entry admission has already certified these at-most-six normalized rows.
// Borrow their roots on demand; no native binding index or Type graph survives.
class EntryBindings {
    const InstructionRange &code_;
    std::size_t count_;

public:
    EntryBindings(const InstructionRange &code, std::size_t count) : code_(code), count_(count) {
    }
    template <class Binding> std::optional<int> root(int position) const {
        if (position < 0 || static_cast<std::size_t>(position) >= count_)
            return {};
        const auto instruction = code_[static_cast<CodePosition>(position)];
        if (const auto *binding = std::get_if<Binding>(&instruction))
            return binding->offset;
        return {};
    }
    template <class... Binding> bool contains(int offset) const {
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
} // namespace

void BlockRetentionBudget::retain(std::size_t operands) {
    require(states_ < maximumStates, "block-entry state retention limit exceeds 65536");
    require(operands_ <= maximumOperands && operands <= maximumOperands - operands_,
            "block-entry operand retention limit exceeds 262144");
    ++states_;
    operands_ += operands;
}

void verifyFunction(FunctionBody &function, const Metadata &metadata, Metrics *metrics) {
    const auto signature = metadata.callable(function.callableId);
    const auto frame = metadata.frame(function.callableId);
    const auto objectSlots = frame.objectSlots();
    const auto arraySlots = frame.arraySlots();
    const auto spanSlots = frame.spanSlots();
    const auto regionSlots = frame.regionSlots();
    const auto byteSlots = frame.byteSlots();
    const auto ownedValueTypes = frame.ownedValueTypes();
    const auto parameters = signature.parameters();
    const EntryBindings entryBindings(function.code, parameters.size());
    // The sole region binding is the admitted first row and cannot be revoked.
    const auto regionOffset = entryBindings.region();
    const std::optional<RegionIdentity> regionIdentity =
        regionOffset ? std::optional<RegionIdentity>{{*regionOffset, function.code.idAt(0), false}} : std::nullopt;
    // The first borrowed root is a derived receiver-shaped observation, never
    // lexical receiver authority. The complete prefix stays in source metadata.
    const auto functionReceiver = signature.receiver();
    const auto borrowedRootCount = signature.borrowedRootCount();
    const auto hasBoundRoot = [&](int root) {
        // Bound the signed selector before negating hostile input.
        return root >= -5 && root <= 0 &&
               (borrowedRootCount ? static_cast<std::size_t>(-root) < borrowedRootCount
                                  : root == 0 && functionReceiver.has_value());
    };
    const auto boundRoot = [&](int root) -> Receiver {
        require(hasBoundRoot(root), "borrowed object root is not bound");
        if (!borrowedRootCount)
            return *functionReceiver;
        const auto ordinal = static_cast<std::size_t>(-root);
        return Receiver{
            signature.borrowedRootType(ordinal).className, signature.borrowedRootMutable(ordinal), false, false};
    };
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
    const auto owningType = [&](const Type &type) {
        return type.isClass() && owningClass(metadata, type.className);
    };
    const bool owningConstructor =
        functionReceiver && functionReceiver->constructor && owningClass(metadata, functionReceiver->className);
    std::optional<FieldRange> receiverFields;
    if (functionReceiver) {
        receiverFields = logicalFields(functionReceiver->className);
    }
    // Source metadata supplies the dense domain. This function owns independent
    // current words and append-only retained snapshots through one RAII capsule.
    InitializationWorkspace initialization(metadata, function.callableId);
    for (CodePosition index = 0; index < function.code.size(); ++index) {
        const auto instruction = function.code[index];
        if (const auto *literal = std::get_if<BorrowLiteralSpanObservation>(&instruction)) {
            require(literal->bytes.size() <= maxByteStringBytes, "literal span exceeds byte-string bound");
            require(spanSlots.contains(literal->resultOffset), "literal span requires exact typed spill");
        }
    }
    // Source normalization already checked every body and fixed its retained
    // order. Native worklist entries use those zero-based positions, never IDs.
    // Only block entries retain snapshots. Saving a full state at every instruction
    // makes a straight-line N-element initializer retain O(N^2) stack/set contents.
    // Depths alone are linear-sized. Full operand/provenance states still live
    // only at basic-block entries, never once per instruction.
    std::vector<std::size_t> stackBefore(function.code.size()), stackAfter(function.code.size());
    std::vector<std::optional<BlockEntry>> states(function.code.size());
    BlockRetentionBudget retention;
    retention.retain(0);
    State entryState;
    if (!borrowedRootCount && functionReceiver && owningClass(metadata, functionReceiver->className)) {
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
        entryState.ownedObjects.emplace(0, std::move(receiver));
    }
    for (std::size_t ordinal = 0; ordinal < borrowedRootCount; ++ordinal) {
        const int selector = -static_cast<int>(ordinal);
        OwnedObjectBinding root{0, ByteDisposition::Live, {}};
        // Every formal has independent symbolic provenance, including equal
        // nominal classes and field ordinals. It grants no allocation authority.
        const RegionIdentity borrowed{selector, 0, true};
        const auto fields = logicalFields(signature.borrowedRootType(ordinal).className);
        for (std::size_t field = 0; field < fields.size(); ++field)
            if (fields[field].elementType.isOwnerStorage())
                root.fields.emplace(
                    static_cast<int>(field),
                    ByteBinding{0, ByteDisposition::Live, ByteToken{0, borrowed, static_cast<int>(field)}});
        entryState.ownedObjects.emplace(selector, std::move(root));
    }
    const auto entryInitialization = initialization.retain();
    states[0].emplace(BlockEntry{std::move(entryState), entryInitialization});
    std::deque<CodePosition> pending{0};
    std::uint64_t retainedValueFacts = 0;
    if (metrics) {
        *metrics = Metrics{};
        metrics->snapshots = 1;
    }
    auto facts = [](const State &state) {
        std::uint64_t ownedFields = 0;
        for (const auto &[unused, object] : state.ownedObjects) {
            (void)unused;
            ownedFields += object.fields.size();
        }
        return ownedFields + state.stack.size() + state.activeObjects.size() + state.activeArrays.size() +
               state.activeSpans.size() + state.activeBytes.size() + state.ownedObjects.size() +
               state.objectLoans.size();
    };
    retainedValueFacts = facts(states[0]->state) + initialization.retainedCountAt(entryInitialization);
    const std::uint64_t initializationPayload = initialization.logicalPayloadBytesPerSnapshot();
    std::uint64_t retainedInitializationPayloadBytes = initializationPayload;
    if (metrics) {
        metrics->peakRetainedValueFacts = retainedValueFacts;
        metrics->peakRetainedInitializationPayloadBytes = retainedInitializationPayloadBytes;
    }
    auto enqueue = [&](CodePosition index, const State &state) {
        require(function.code.flowAt(index).blockEntry, "worklist target is not a basic-block entry");
        if (!states[index]) {
            // Check before the snapshot allocation, whether metrics are enabled
            // or not. These retained counts never grow on worklist revisits.
            retention.retain(state.stack.size());
            State retainedState = state;
            const auto retainedInitialization = initialization.retain();
            states[index].emplace(BlockEntry{std::move(retainedState), retainedInitialization});
            retainedValueFacts += facts(states[index]->state) + initialization.retainedCountAt(retainedInitialization);
            retainedInitializationPayloadBytes += initializationPayload;
            if (metrics) {
                ++metrics->snapshots;
                metrics->peakRetainedOperandFacts = retention.operands();
                metrics->peakRetainedValueFacts = std::max(metrics->peakRetainedValueFacts, retainedValueFacts);
                metrics->peakRetainedInitializationPayloadBytes =
                    std::max(metrics->peakRetainedInitializationPayloadBytes, retainedInitializationPayloadBytes);
            }
            pending.push_back(index);
            return;
        }
        const auto &existing = states[index]->state;
        require(existing.activeObjects == state.activeObjects,
                "incompatible active object lifetimes at control-flow join");
        require(existing.activeArrays == state.activeArrays,
                "incompatible active array lifetimes at control-flow join");
        require(existing.activeSpans == state.activeSpans,
                "incompatible active span capabilities at control-flow join");
        require(initialization.sameServiceLoans(states[index]->initialization),
                "incompatible service provenance or loans at control-flow join");
        require(existing.activeBytes == state.activeBytes,
                "incompatible owned byte lifetimes or ownership at control-flow join");
        require(existing.ownedObjects == state.ownedObjects,
                "incompatible owning object lifetimes or field ownership at control-flow join");
        require(existing.objectLoans == state.objectLoans, "incompatible object loans at control-flow join");
        require(existing.stack == state.stack, "incompatible value/guard stacks at control-flow join");
        State merged = existing;
        if (merged.current != state.current)
            merged.current.reset();
        const bool nativeChanged = merged != existing;
        const auto retainedInitialization = states[index]->initialization;
        // Count before source join mutates the retained row. Must losses and may
        // gains can cancel numerically, so only its explicit changed flag drives
        // the initialization half of worklist convergence.
        const auto oldInitializationCount = initialization.retainedCountAt(retainedInitialization);
        const bool initializationChanged = initialization.join(retainedInitialization);
        if (nativeChanged || initializationChanged) {
            retainedValueFacts -= facts(existing) + oldInitializationCount;
            retainedValueFacts += facts(merged) + initialization.retainedCountAt(retainedInitialization);
            if (metrics)
                metrics->peakRetainedValueFacts = std::max(metrics->peakRetainedValueFacts, retainedValueFacts);
            states[index]->state = std::move(merged);
            pending.push_back(index);
        }
    };
    while (!pending.empty()) {
        auto index = pending.front();
        pending.pop_front();
        State state = states[index]->state;
        // Loading copies retained words into independent source current storage.
        // A self-loop join may change its retained row, never the current words
        // subsequently consumed by another successor.
        initialization.load(states[index]->initialization);
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
            // A supplied loan ID alone never exempts an access. Install the
            // borrowed lane range only after every root/loan correspondence and
            // live field has been checked independently below.
            const auto *borrowedCall = std::get_if<BorrowedCallObservation>(&instruction);
            bool borrowedLoansValidated = false;
            auto loanAccess = [&](int root, bool writing) {
                for (const auto &[id, loan] : state.objectLoans) {
                    if (loan.root != root)
                        continue;
                    bool exercised = false;
                    if (borrowedLoansValidated)
                        for (const auto lane : borrowedCall->roots)
                            if (lane.root == root && lane.loanId == id) {
                                exercised = true;
                                break;
                            }
                    if (!exercised)
                        require(!writing && !loan.mutableValue, "object access conflicts with active synchronous loan");
                }
            };
            // Each access borrows exact local origins from the source owner once.
            // Receiver roots, padding and empty object reservations are not leaves.
            auto activeObjectField = [&](std::optional<int> root) {
                if (!root)
                    return;
                require(state.activeObjects.contains(*root), "object field access outside active lifetime");
                loanAccess(*root, false);
                require(!state.ownedObjects.contains(*root) ||
                            state.ownedObjects.at(*root).disposition != ByteDisposition::Consumed,
                        "field access through consumed owning object");
            };
            auto activeArrayElement = [&](std::optional<int> root) {
                require(!root || state.activeArrays.contains(*root), "array element access outside active lifetime");
            };
            auto arrayWritable = [&](int offset, std::optional<int> objectRoot, std::optional<int> arrayRoot) {
                if (objectRoot) {
                    const int root = *objectRoot;
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
                if (!arrayRoot)
                    return;
                const int base = *arrayRoot;
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
                        require(regionIdentity && *regionIdentity == identity,
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
                require(regionIdentity && regionIdentity->offset == base, "region authority is not active");
                return *regionIdentity;
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
                require(!mutableAccess || byteSlots.at(base), "const owned byte binding cannot be mutated or moved");
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
            auto store = [&](int offset) {
                const auto objectRoot = metadata.objectLeafRoot(function.callableId, offset);
                const auto arrayRoot = metadata.byteArrayElementRoot(function.callableId, offset);
                activeObjectField(objectRoot);
                if (objectRoot)
                    loanAccess(*objectRoot, true);
                activeArrayElement(arrayRoot);
                arrayWritable(offset, objectRoot, arrayRoot);
                // Source returns prior must/may bits and sets both together. A
                // rejected immutable write aborts this invocation; no rollback.
                const auto prior = initialization.writeScalar(offset);
                require(!entryBindings.contains<BindParameter>(offset) || (prior & 2u) == 0,
                        "write to immutable scalar parameter");
                require(!objectRoot || objectSlots.at(*objectRoot).mutableValue || (prior & 2u) == 0,
                        "write to initialized const object field");
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
                    require((initialization.receiverFieldState(fieldIndex) &
                             InitializationWorkspace::physical_initialized) != 0,
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
            // Source admission has checked every typed element and nested-field
            // restriction. Write eligibility follows the live-state checks below.
            auto initializedArray = [&](int offset, int length, const Type &type) {
                // This batch only observes initialization. Preserve native error
                // interleaving by completing each preceding element's checks and
                // the missing element's lifetime checks before reporting it.
                const auto firstMissing = initialization.arrayFirstMissing(offset, length, storageWidth(type));
                for (int element = 0; element < length; ++element) {
                    const int elementOffset = offset - element * storageWidth(type);
                    const auto objectRoot = metadata.objectLeafRoot(function.callableId, elementOffset);
                    const auto arrayRoot = metadata.byteArrayElementRoot(function.callableId, elementOffset);
                    activeObjectField(objectRoot);
                    activeArrayElement(arrayRoot);
                    require(!firstMissing || element != *firstMissing, "array element not initialized");
                }
            };
            auto writableArray = [&](int offset, int length, const Type &type) {
                for (int element = 0; element < length; ++element) {
                    const int elementOffset = offset - element * storageWidth(type);
                    const auto objectRoot = metadata.objectLeafRoot(function.callableId, elementOffset);
                    const auto arrayRoot = metadata.byteArrayElementRoot(function.callableId, elementOffset);
                    arrayWritable(elementOffset, objectRoot, arrayRoot);
                    if (objectRoot)
                        loanAccess(*objectRoot, true);
                    require(!entryBindings.contains<BindParameter>(elementOffset),
                            "indexed write to immutable scalar parameter");
                    require(!objectRoot || objectSlots.at(*objectRoot).mutableValue,
                            "indexed write to const object field");
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
                const auto completion = initialization.objectCompletion(base);
                require(completion != InitializationWorkspace::ObjectCompletion::missing_nested,
                        "nested class field not completely initialized");
                require(completion != InitializationWorkspace::ObjectCompletion::missing_empty,
                        "empty object not completely initialized");
                return completion;
            };
            auto liveCopiedArgument = [&](int base, const std::string &role) {
                require(state.activeObjects.contains(base), role + " argument outside active object lifetime");
                require(initialization.objectInitialized(base), role + " argument object not fully initialized");
                logicalComplete(base);
            };
            auto initializedObject =
                [&](int base, InitializationWorkspace::ObjectCompletion *completion = nullptr) -> ObjectSlot {
                require(state.activeObjects.contains(base), "copy object outside active lifetime");
                auto object = objectSlots.at(base);
                require(initialization.objectInitialized(base), "copy source object not fully initialized");
                const auto observed = logicalComplete(base);
                if (completion)
                    *completion = observed;
                return object;
            };
            auto liveObject = [&](int base) -> ObjectSlot {
                loanAccess(base, false);
                return initializedObject(base);
            };
            auto completeObject = [&](int base,
                                      InitializationWorkspace::ObjectCompletion *completion = nullptr) -> ObjectSlot {
                loanAccess(base, false);
                require(objectSlots.contains(base), "copy requires exact object slot");
                return initializedObject(base, completion);
            };
            auto liveOwnedRoot = [&](int root) -> const OwnedObjectBinding & {
                require(state.ownedObjects.contains(root), "object loan requires exact owning root");
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
                require(root > 0 || hasBoundRoot(root), "invalid borrowed object root");
                const auto &name = root <= 0 ? boundRoot(root).className : completeObject(root).className;
                require(owningClass(metadata, name), "object loan requires exact owning root");
                return liveOwnedRoot(root);
            };
            auto initializedReceiverClassField = [&](int index) {
                require((initialization.receiverFieldState(index) & InitializationWorkspace::logical_initialized) != 0,
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
                    require((initialization.receiverFieldState(fieldIndex) &
                             InitializationWorkspace::logical_initialized) != 0,
                            "receiver class array not completely initialized");
                } else {
                    const auto &root = completeObject(base);
                    require(!mutableAccess || root.mutableValue, "const object cannot supply mutable class array");
                    require(metadata.findClass(root.className) && fieldIndex >= 0 &&
                                static_cast<std::size_t>(fieldIndex) < logicalFields(root.className).size(),
                            "class array logical field index out of range");
                    field = logicalFields(root.className)[fieldIndex];
                }
                require(field.array && field.elementType.isClass(), "class array operation requires class array field");
                require(!owningClass(metadata, field.elementType.className),
                        "class array elements must be copied values");
                return field;
            };
            auto classArrayEvidence = [&](int base, int fieldIndex, const ClassField &field) {
                return ClassArrayGuard{base,
                                       base == 0 ? functionReceiver->className : objectSlots.at(base).className,
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
                require(!initialization.objectWasConstructed(base), "copy result object already initialized");
                require(initialization.objectPristine(base), "copy requires pristine result object");
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
                initialization.markObject(base);
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
                require(slot.className == name && owningClass(metadata, name), "owning object nominal class mismatch");
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
                return type;
            };
            auto copiedValue = [&](int base, const Type &owner, int root) {
                require(base != root, "owned value snapshot aliases owner root");
                InitializationWorkspace::ObjectCompletion completion;
                const auto &value = completeObject(base, &completion);
                require(value.className == owner.className, "owned value snapshot nominal class mismatch");
                require(!value.mutableValue, "owned value snapshot must be readonly");
                require(completion == InitializationWorkspace::ObjectCompletion::whole,
                        "owned value snapshot requires complete copied or constructed value");
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
            auto initializedReceiverArray = [&](int field) {
                require((initialization.receiverFieldState(field) & InitializationWorkspace::physical_initialized) != 0,
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
                initializedReceiverArray(ordinal);
                require(field.array && field.elementType == Type::U8,
                        "fixed array span requires direct u8 array field");
                spanTarget(result);
                publishArrayBorrow(0, ordinal, result, 0);
            };
            auto borrowLiveArrayField = [&](int root, int ordinal, int result) {
                loanAccess(root, false);
                InstructionId site = 0;
                if (root == 0)
                    initializedReceiverArray(ordinal);
                else {
                    liveObject(root);
                    site = state.activeObjects.at(root);
                }
                inactiveSpanTarget(result);
                publishArrayBorrow(root, ordinal, result, site);
            };
            auto closedOwnedObjects = [&]() {
                require(initialization.serviceLoansClosed(), "return with active synchronous service loan");
                require(state.objectLoans.empty(), "return with active synchronous object loan");
                for (const auto &[base, unused] : state.ownedObjects) {
                    (void)unused;
                    require(hasBoundRoot(base), "return with active owning object lifetime");
                }
            };
            std::visit(
                [&](const auto &operation) {
                    using Op = std::decay_t<decltype(operation)>;
                    if constexpr (std::is_same_v<Op, Constant>) {
                        state.current = Value{operation.type, {}};
                    } else if constexpr (std::is_same_v<Op, EnumConstant>) {
                        state.current = Value{operation.type, {}};
                    } else if constexpr (std::is_same_v<Op, Load>) {
                        const auto objectRoot = metadata.objectLeafRoot(function.callableId, operation.offset);
                        const auto arrayRoot = metadata.byteArrayElementRoot(function.callableId, operation.offset);
                        activeObjectField(objectRoot);
                        activeArrayElement(arrayRoot);
                        require((initialization.scalarState(operation.offset) & 1u) != 0, "load before initialization");
                        state.current = Value{operation.type, {}};
                    } else if constexpr (std::is_same_v<Op, Store>) {
                        current(operation.type);
                        store(operation.offset);
                    } else if constexpr (std::is_same_v<Op, Push>) {
                        require(state.current.has_value(), "push without current value");
                        state.stack.push_back(*state.current);
                        if (metrics)
                            metrics->peakOperandDepth = std::max(metrics->peakOperandDepth, state.stack.size());
                    } else if constexpr (std::is_same_v<Op, Pop>) {
                        state.current = pop();
                    } else if constexpr (std::is_same_v<Op, UnaryValue>) {
                        current(operation.operandType);
                        state.current = Value{operation.operandType, {}};
                    } else if constexpr (std::is_same_v<Op, BinaryValue>) {
                        const bool shift =
                            operation.operation == Binary::ShiftLeft || operation.operation == Binary::ShiftRight;
                        current(shift ? Type::I64 : operation.operandType);
                        require(pop().type == operation.operandType, "noninteger left operand or binary type mismatch");
                        state.current = Value{operation.operandType, {}};
                    } else if constexpr (std::is_same_v<Op, Convert>) {
                        current(operation.sourceType);
                        // A value conversion never preserves an index's bounds evidence.
                        state.current = Value{operation.resultType, {}};
                    } else if constexpr (std::is_same_v<Op, Compare>) {
                        current(operation.operandType);
                        require(pop().type == operation.operandType, "comparison type mismatch");
                        state.current = Value{Type::Bool, {}};
                    } else if constexpr (std::is_same_v<Op, BoundsGuard>) {
                        current(Type::I64);
                        initializedArray(operation.offset, operation.length, operation.elementType);
                        state.current =
                            Value{Type::I64, Guard{operation.offset, operation.length, operation.elementType}};
                    } else if constexpr (std::is_same_v<Op, IndexLoad>) {
                        initializedArray(operation.offset, operation.length, operation.elementType);
                        guard(current(Type::I64), operation.offset, operation.length, operation.elementType);
                        state.current = Value{operation.elementType, {}};
                    } else if constexpr (std::is_same_v<Op, IndexStore>) {
                        // Preserve range-before-operands-before-write diagnostics.
                        // An earlier write conflict must not hide a later missing
                        // initialization or lifetime within the same range.
                        initializedArray(operation.offset, operation.length, operation.elementType);
                        current(operation.elementType);
                        guard(pop(), operation.offset, operation.length, operation.elementType);
                        writableArray(operation.offset, operation.length, operation.elementType);
                    } else if constexpr (std::is_same_v<Op, BorrowHandle>) {
                        require((initialization.scalarState(operation.ownerOffset) & 1u) != 0,
                                "borrow of uninitialized payload");
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
                            liveCopiedArgument(base, "aggregate");
                        }
                        if (target.result().isClass()) {
                            const int base = operation.resultOffset;
                            require(state.activeObjects.contains(base),
                                    "aggregate result outside active object lifetime");
                            require(!initialization.objectWasConstructed(base),
                                    "aggregate result object already initialized");
                            require(initialization.objectPristine(base),
                                    "aggregate result requires uninitialized object");
                            initialization.markObject(base);
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
                            require(state.activeObjects.contains(base),
                                    "resource copied result outside active object lifetime");
                            require(!initialization.objectWasConstructed(base),
                                    "resource copied result object already initialized");
                            require(initialization.objectPristine(base),
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
                            initialization.markObject(operation.resultOffset);
                            state.current.reset();
                        } else
                            state.current = Value{target.result(), {}};
                    } else if constexpr (std::is_same_v<Op, BeginBytes>) {
                        require(byteSlots.contains(operation.offset), "owned byte lifetime requires exact typed spill");
                        require(!entryBindings.contains<BindBytesParameter>(operation.offset),
                                "owned byte parameter lifetime cannot restart");
                        require(!state.activeBytes.contains(operation.offset), "owned byte lifetime already active");
                        state.activeBytes.emplace(operation.offset,
                                                  ByteBinding{instructionId, ByteDisposition::Pristine, {}});
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
                        initialization.clearArray(operation.offset, arraySlots.at(operation.offset), 1);
                    } else if constexpr (std::is_same_v<Op, BorrowSpan>) {
                        require(state.activeArrays.contains(operation.arrayOffset),
                                "span borrow requires active byte array origin");
                        // The admitted exact byte array cannot overlap an object.
                        // Its one checked lifetime covers every initialized element.
                        const int length = arraySlots.at(operation.arrayOffset);
                        require(!initialization.arrayFirstMissing(operation.arrayOffset, length, 1),
                                "array element not initialized");
                        inactiveSpanTarget(operation.resultOffset);
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
                            require(!entryBindings.contains<BindObjectParameter, BindOwnedObjectParameter>(
                                        operation.offset),
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
                        initialization.clearObject(operation.offset);
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
                        require(!owningClass(metadata, source.className), "owning class cannot be implicitly copied");
                        copyTarget(operation.resultOffset, source.className);
                        state.current.reset();
                    } else if constexpr (std::is_same_v<Op, ObjectFieldCopy>) {
                        ClassField field{};
                        if (operation.sourceOffset == 0) {
                            field = receiverShape(operation.fieldIndex);
                            require(!functionReceiver->constructor,
                                    "constructor cannot project receiver during initialization");
                            require((initialization.receiverFieldState(operation.fieldIndex) &
                                     InitializationWorkspace::logical_initialized) != 0,
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
                        const auto prior = initialization.writeReceiverField(operation.fieldIndex);
                        require((prior & InitializationWorkspace::logical_written) == 0,
                                "constructor class field initialized more than once");
                        require((prior & InitializationWorkspace::physical_written) == 0,
                                "constructor class field leaves already initialized");
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
                            const auto prior = initialization.writeReceiverField(operation.fieldIndex);
                            require((prior & InitializationWorkspace::logical_written) == 0,
                                    "constructor class array initialized more than once");
                            require((prior & InitializationWorkspace::physical_written) == 0,
                                    "constructor class array leaves already initialized");
                        } else {
                            copyTarget(operation.objectOffset, objectSlots.at(operation.objectOffset).className);
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
                        receiverField(operation.fieldIndex, operation.type);
                        require(!functionReceiver->constructor,
                                "constructor cannot read receiver during initialization");
                        require((initialization.receiverFieldState(operation.fieldIndex) &
                                 InitializationWorkspace::physical_initialized) != 0,
                                "receiver field not initialized");
                        state.current = Value{operation.type, {}};
                    } else if constexpr (std::is_same_v<Op, ReceiverStore>) {
                        receiverField(operation.fieldIndex, operation.type);
                        current(operation.type);
                        require(functionReceiver->mutableValue, "write through const receiver");
                        const auto prior = initialization.writeReceiverField(operation.fieldIndex);
                        if (functionReceiver->constructor)
                            require((prior & InitializationWorkspace::physical_written) == 0,
                                    "constructor field initialized more than once");
                    } else if constexpr (std::is_same_v<Op, ReceiverArrayZero>) {
                        receiverArray(operation.fieldIndex, false);
                        require(functionReceiver->constructor && functionReceiver->mutableValue,
                                "receiver array zero requires constructor receiver");
                        const auto prior = initialization.writeReceiverField(operation.fieldIndex);
                        require((prior & InitializationWorkspace::physical_written) == 0,
                                "constructor array initialized more than once");
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
                        require(operation.root > 0 || hasBoundRoot(operation.root), "invalid borrowed object root");
                        loanAccess(operation.root, operation.mutableValue);
                        std::string name;
                        if (operation.root <= 0) {
                            require(signature.borrowedParameter() && functionReceiver,
                                    "bound root loan requires named borrowed formal");
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
                        int receiverOffset;
                        int receiverFieldIndex = -1;
                        if constexpr (std::is_same_v<Op, BorrowedCallObservation>) {
                            const auto count = target.borrowedRootCount();
                            for (std::size_t ordinal = 0; ordinal < count; ++ordinal) {
                                const auto lane = operation.roots[ordinal];
                                require(state.objectLoans.contains(lane.loanId), "borrowed call requires active loan");
                                const auto &loan = state.objectLoans.at(lane.loanId);
                                require(!loan.called, "object loan already used by a call");
                                const auto formal = target.borrowedRootType(ordinal);
                                const bool mutableValue = target.borrowedRootMutable(ordinal);
                                require(loan.root == lane.root && loan.className == formal.className &&
                                            loan.mutableValue == mutableValue,
                                        "borrowed call root, nominal type or authority mismatch");
                                // These checks deliberately do not use loanAccess: no
                                // lane, including a sibling, grants an exemption yet.
                                if (lane.root <= 0) {
                                    require(signature.borrowedParameter(), "borrowed call requires named bound formal");
                                    require(loan.rootSite == 0, "borrowed call formal authority mismatch");
                                } else {
                                    initializedObject(lane.root);
                                    require(state.activeObjects.at(lane.root) == loan.rootSite,
                                            "borrowed call object lifetime or authority mismatch");
                                }
                                const auto &object = liveOwnedRoot(lane.root);
                                require(object.site == loan.rootSite, "borrowed call root lifetime mismatch");
                            }
                            borrowedLoansValidated = true;
                            for (std::size_t ordinal = 0; ordinal < count; ++ordinal)
                                loanAccess(operation.roots[ordinal].root, target.borrowedRootMutable(ordinal));
                            receiverOffset = operation.roots.front().root;
                        } else {
                            receiverOffset = operation.receiverOffset;
                            receiverFieldIndex = operation.receiverFieldIndex;
                            loanAccess(receiverOffset, target.receiver()->mutableValue);
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
                            ownerWritable(receiverOffset);
                        if (receiverFieldIndex >= 0) {
                            liveClassField(receiverOffset, receiverFieldIndex, receiver.mutableValue);
                        } else if (receiverOffset > 0) {
                            require(state.activeObjects.contains(receiverOffset),
                                    "method receiver outside active object lifetime");
                            if (receiver.constructor) {
                                require(!initialization.objectWasConstructed(receiverOffset),
                                        "object constructor called more than once");
                                require(initialization.objectPristine(receiverOffset),
                                        "constructor requires uninitialized object");
                                initialization.markObject(receiverOffset);
                            } else {
                                require(initialization.objectInitialized(receiverOffset),
                                        "method receiver object not fully initialized");
                                logicalComplete(receiverOffset);
                            }
                        }
                        if (target.result() == Type::ByteSpan) {
                            const auto field = logicalFields(receiver.className).at(*target.receiverSpanField());
                            if (field.array)
                                borrowLiveArrayField(
                                    receiverOffset, *target.receiverSpanField(), operation.resultOffset);
                            else
                                borrowLiveOwnedField(
                                    receiverOffset, *target.receiverSpanField(), operation.resultOffset);
                            state.current.reset();
                        } else if (target.result().isClass()) {
                            const int base = operation.resultOffset;
                            require(state.activeObjects.contains(base), "method result outside active object lifetime");
                            require(!initialization.objectWasConstructed(base),
                                    "method result object already initialized");
                            require(initialization.objectPristine(base), "method result requires uninitialized object");
                            initialization.markObject(base);
                            state.current.reset();
                        } else {
                            state.current = Value{target.result(), {}};
                        }
                        if constexpr (std::is_same_v<Op, BorrowedCallObservation>)
                            for (const auto lane : operation.roots)
                                state.objectLoans.at(lane.loanId).called = true;
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
                            const auto completion = initialization.receiverCompletion();
                            require(completion != InitializationWorkspace::ReceiverCompletion::missing_physical,
                                    "constructor returns before all fields initialized");
                            require(completion != InitializationWorkspace::ReceiverCompletion::missing_logical,
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
                        require(signature.result() == Type::ByteSpan && signature.receiverSpanField() &&
                                    functionReceiver && !functionReceiver->constructor &&
                                    !functionReceiver->mutableValue,
                                "span return requires const owning receiver field summary");
                        const auto &capability = span(operation.offset);
                        const bool fixed = receiverShape(*signature.receiverSpanField()).array;
                        const auto token = fixed ? std::optional<ByteToken>{}
                                                 : accessBytes(0, *signature.receiverSpanField(), false).token;
                        auto matchesReceiver = [&](const SpanCapability &view) {
                            return view.origin == 0 && !view.parameterOrigin && !view.literalOrigin &&
                                   (fixed
                                        ? view.arrayField == *signature.receiverSpanField() && !view.ownedToken
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
                        require(objectSlots.contains(operation.offset), "object return requires exact object slot");
                        const auto &object = objectSlots.at(operation.offset);
                        require(object.className == signature.result().className,
                                "object return nominal class mismatch");
                        require(state.activeObjects.contains(operation.offset),
                                "object return outside active lifetime");
                        require(initialization.objectInitialized(operation.offset),
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
                        require(signature.result().isOwnerStorage() &&
                                    ownerType(operation.offset) == signature.result(),
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
                        // Source admission owns immutable entry roots and kinds; only loans vary along the CFG.
                    } else if constexpr (std::is_same_v<Op, AcquireServiceLoan>) {
                        require(initialization.acquireServiceLoan(operation.loanId, operation.offset, operation.kind),
                                "service loan requires unsuspended parameter authority");
                    } else if constexpr (std::is_same_v<Op, ReleaseServiceLoan>) {
                        require(initialization.releaseServiceLoan(operation.loanId, operation.kind),
                                "service release requires exactly one completed helper call");
                    } else if constexpr (std::is_same_v<Op, ServiceOperation>) {
                        require(initialization.serviceUnsuspended(operation.offset),
                                "service operation requires active unsuspended capability provenance");
                        if (operation.operation == service::Operation::Pixel) {
                            for (int argument = 4; argument >= 0; --argument)
                                require(pop().type == (argument < 2 ? Type::U64 : Type::U8),
                                        "pixel argument type mismatch");
                            state.current = Value{service::displayPutResultType(), {}};
                        } else if (operation.operation == service::Operation::Put) {
                            current(Type::U8);
                            state.current = Value{service::putResultType(), {}};
                        } else if (operation.operation == service::Operation::IommuAcknowledge) {
                            state.current = Value{service::eventAckResultType(), {}};
                        } else if (operation.operation == service::Operation::Next ||
                                   operation.operation == service::Operation::IommuPoll) {
                            const int base = operation.resultOffset;
                            require(state.activeObjects.contains(base) && !initialization.objectWasConstructed(base),
                                    "service observation requires exact pristine active copied sample object");
                            require(initialization.objectPristine(base),
                                    "service observation cannot overwrite initialized sample storage");
                            initialization.markObject(base);
                            state.current.reset();
                        } else {
                            require(false, "unknown sealed service operation");
                        }
                    } else if constexpr (std::is_same_v<Op, ServiceCallObservation>) {
                        const auto target = metadata.callable(metadata.findCallable(operation.callee).value());
                        const auto count = static_cast<std::size_t>(
                            std::count_if(target.parameters().begin(), target.parameters().end(), [](const Type &type) {
                                return type.isService();
                            }));
                        require(operation.additionalServices.size() <= 1 &&
                                    count == 1 + operation.additionalServices.size(),
                                "service helper argument vector mismatch");
                        // Source validates dynamic loans before ordinary arguments.
                        const auto second = operation.additionalServices.empty()
                                                ? ServiceArgument{0, service::Kind::Console}
                                                : operation.additionalServices.at(0);
                        const auto loans = initialization.validateServiceCall(
                            operation.loanId, operation.kind, second.loanId, second.kind);
                        require(loans != InitializationWorkspace::ServiceCallState::missing,
                                "service helper requires distinct acquired loans in leading positions");
                        require(loans != InitializationWorkspace::ServiceCallState::provenance,
                                "service helper requires an unused loan with exact provenance");
                        for (std::size_t reverse = target.parameters().size(); reverse > count; --reverse) {
                            const auto position = reverse - 1;
                            const auto &type = target.parameters()[position];
                            const int base = operation.spanArguments[position];
                            if (type.isSpan()) {
                                require(state.activeSpans.contains(base), "service span argument is not active");
                                liveSpan(base);
                            } else if (type.isClass()) {
                                liveCopiedArgument(operation.objectArguments[position], "service");
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
                        initialization.completeServiceCall(operation.loanId, second.loanId);
                    } else if constexpr (std::is_same_v<Op, BindRegionParameter>) {
                        // Immutable authority is derived once from the admitted entry prefix.
                    } else if constexpr (std::is_same_v<Op, BindBytesParameter>) {
                        const auto token = freshToken(activeRegion(*entryBindings.region()), -1);
                        state.activeBytes.emplace(operation.offset,
                                                  ByteBinding{instructionId, ByteDisposition::Live, token});
                    } else if constexpr (std::is_same_v<Op, BindSpanParameter>) {
                        state.activeSpans.emplace(
                            operation.offset,
                            SpanCapability{true, operation.index, instructionId, 0, 0, instructionId});
                    } else if constexpr (std::is_same_v<Op, BindOwnedObjectParameter>) {
                        state.activeObjects.emplace(operation.offset, instructionId);
                        beginOwnedObject(operation.offset, operation.className);
                        initializeObject(operation.offset);
                        mintObjectFields(operation.offset, activeRegion(*entryBindings.region()));
                    } else if constexpr (std::is_same_v<Op, BindObjectParameter>) {
                        state.activeObjects.emplace(operation.offset, instructionId);
                        initialization.markObject(operation.offset);
                    } else if constexpr (std::is_same_v<Op, BindParameter>) {
                        const auto prior = initialization.writeScalar(operation.offset);
                        require((prior & 2u) == 0, "write to immutable scalar parameter");
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
            require(index < function.code.size(), "reachable fallthrough without return");
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
        // Source compaction preserves the first omitted semantic row's place
        // after this retained row, including its priority against depth errors.
        require(!function.code.flowAt(index).unreachableSemanticAfter, "unreachable semantic instruction");
    }
}
static void verifyFunctions(std::vector<FunctionBody> &input, const Metadata &metadata, Metrics *metrics = nullptr) {
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
ValidatedModule validate(Module module, verification::Metrics *metrics) {
    // Import consumes and destroys all raw fixture construction before either
    // independent admission. Only the paired Aurora-owned bundle returns.
    auto pending = InstructionIngress::import(std::move(module));
    return validate(std::move(pending), metrics);
}
ValidatedModule validate(InstructionIngress pending, verification::Metrics *metrics) {
    // Finish metadata first; then source generic instruction admission checks
    // suffix tails before codec reconstruction can discard unresolved payloads.
    auto metadata = std::move(pending.metadata_).finish();
    auto instructions = std::move(pending.instructions_);
    if (!instructions)
        throw Error(DiagnosticCode::Internal, "missing hosted IR instruction ingress");
    instructions->admit(*metadata);
    // Source checks every CFG, then every normalized entry binding, then every
    // immutable call, storage-access and scalar contract before native value-state arrays.
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
