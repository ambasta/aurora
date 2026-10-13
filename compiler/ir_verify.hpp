#pragma once
#include "hosted_graph.hpp"
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
// internally from instruction sites, never supplied by an IR operand or runtime
// descriptor. A failed allocation still creates one live logical ownership token.
class RegionIdentity {
public:
    int offset;
    std::size_t site;
    bool borrowed = false; // symbolic receiver provenance never grants allocation authority
    bool operator==(const RegionIdentity &) const = default;
};
class ByteToken {
public:
    std::size_t site;
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
    std::size_t originSite;
    int parent;
    std::size_t parentSite;
    std::size_t site;
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
    std::size_t site;
    ByteDisposition disposition;
    std::optional<ByteToken> token;
    bool operator==(const ByteBinding &) const = default;
};
class OwnedObjectBinding {
public:
    std::size_t site;
    ByteDisposition disposition;
    std::map<int, ByteBinding> fields;
    bool operator==(const OwnedObjectBinding &) const = default;
};
class ObjectLoan {
public:
    int root;
    std::size_t rootSite;
    std::string className;
    bool mutableValue;
    bool called = false;
    bool operator==(const ObjectLoan &) const = default;
};
class ServiceIdentity {
public:
    std::size_t site;
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
    std::map<int, std::size_t> activeObjects; // object base -> creation/binding site
    std::map<int, std::size_t> activeArrays;  // array base -> BeginArray site
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
inline bool scalarValueType(const Type &type, const std::map<std::string, int> &enumCases) {
    return scalar(type) ||
           (type.isEnum() && type == Type::enumeration(type.className) && enumCases.contains(type.className));
}
// A typed owner carries exactly one canonical copied-class identity. Descriptor
// shape alone never authorizes scalar reinterpretation, a carrier or resource payload.
inline void verifyOwnerType(const Type &type,
                            const std::map<std::string, std::vector<Type>> &classLayouts,
                            const std::map<std::string, std::vector<ClassField>> &classFields,
                            const std::map<std::string, ClassStorage> &classStorage,
                            const std::set<std::string> &classArrayCarriers) {
    if (type == Type::OwnedBytes)
        return;
    require(type.isOwnedValues() && type == Type::ownedValues(Type(type.className)),
            "invalid canonical owned value type");
    require(classLayouts.contains(type.className) && classStorage.contains(type.className),
            "owned value element requires known canonical class layout");
    require(!owningClass(classFields, type.className) && !classArrayCarriers.contains(type.className),
            "owned value element must be a copied class, not an owner or carrier");
    require(copiedClassLeavesSupported(classLayouts.at(type.className)),
            "owned value element exceeds copied class leaf limits");
    const auto &storage = classStorage.at(type.className);
    require(storage.sizeBytes >= 1 && storage.sizeBytes <= maximumCopiedClassBytes &&
                storage.reservedBytes <= maximumCopiedClassBytes,
            "owned value element storage exceeds 520 bytes");
}
inline bool serviceSignature(const Function &function) {
    return std::any_of(function.parameters.begin(), function.parameters.end(), [](const Type &type) {
        return type.isService();
    });
}
inline bool resourceSignature(const Function &function,
                              const std::map<std::string, std::vector<ClassField>> &fields = {}) {
    const auto resource = [&](const Type &type) {
        return type.isResource() || (type.isClass() && owningClass(fields, type.className));
    };
    return resource(function.result) ||
           (function.receiver && function.receiver->constructor && owningClass(fields, function.receiver->className)) ||
           std::any_of(function.parameters.begin(), function.parameters.end(), resource);
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
inline void verifyFunction(Function &function,
                           const std::map<std::string, const Function *> &functions,
                           Metrics *metrics = nullptr,
                           const std::set<int> &availableScopes = {0},
                           const std::map<std::string, std::vector<Type>> &classLayouts = {},
                           const std::map<std::string, std::vector<ClassField>> &classFields = {},
                           const std::map<std::string, int> &enumCases = {},
                           const std::map<std::string, ClassStorage> &classStorage = {},
                           const std::set<std::string> &classArrayCarriers = {}) {
    std::map<std::string, ClassStorage> derivedStorage;
    if (classStorage.empty() && !classLayouts.empty()) {
        auto fields = classFields;
        for (const auto &[name, leaves] : classLayouts)
            if (!fields.contains(name)) {
                auto &logical = fields[name];
                for (std::size_t leaf = 0; leaf < leaves.size(); ++leaf)
                    logical.push_back(ClassField{leaves[leaf], static_cast<int>(leaf), 1, false});
            }
        derivedStorage = computeClassStorageLayouts(classLayouts, fields);
    }
    const auto &storage = classStorage.empty() ? derivedStorage : classStorage;
    auto ownerType = [&](int base) {
        require(function.byteSlots.contains(base), "owner type requires exact typed spill");
        return function.ownedValueTypes.contains(base) ? Type::ownedValues(Type(function.ownedValueTypes.at(base)))
                                                       : Type::OwnedBytes;
    };
    for (const auto &[base, name] : function.ownedValueTypes) {
        require(function.byteSlots.contains(base), "owned value metadata requires exact owner spill");
        verifyOwnerType(Type::ownedValues(Type(name)), classLayouts, classFields, storage, classArrayCarriers);
    }
    auto objectLeaf = [&](int base, std::size_t leaf) {
        return base - storage.at(function.objectSlots.at(base).className).leafOffsets.at(leaf);
    };
    require(availableScopes.contains(function.moduleScope), "unknown function module scope");
    const auto owningType = [&](const Type &type) {
        return type.isClass() && owningClass(classFields, type.className);
    };
    const bool owningConstructor =
        function.receiver && function.receiver->constructor && owningClass(classFields, function.receiver->className);
    const bool resourceFunction = resourceSignature(function, classFields);
    const bool serviceFunction = serviceSignature(function);
    std::size_t serviceParameterCount = 0;
    if (serviceFunction) {
        require(!function.receiver && !function.borrowedParameter && !function.secondBorrowedParameter &&
                    !resourceFunction &&
                    !function.parameters.empty() && function.parameters.front().isService(),
                "service signature requires a leading sealed group and no receiver or region");
        std::set<service::Kind> kinds;
        while (serviceParameterCount < function.parameters.size() &&
               function.parameters[serviceParameterCount].isService()) {
            require(kinds.insert(service::kind(function.parameters[serviceParameterCount])).second,
                    "service signature requires distinct capability kinds");
            ++serviceParameterCount;
        }
        // Deliberately independent closed allowlist: adding a recognized kind
        // does not grant arbitrary pair or triple forwarding authority.
        require(serviceParameterCount <= 2 &&
                    (kinds == std::set<service::Kind>{service::Kind::Console} ||
                     kinds == std::set<service::Kind>{service::Kind::Display} ||
                     kinds == std::set<service::Kind>{service::Kind::IommuEvent} ||
                     kinds == std::set<service::Kind>{service::Kind::Console, service::Kind::Display} ||
                     kinds == std::set<service::Kind>{service::Kind::Console, service::Kind::IommuEvent}),
                "unsupported service group");
        for (std::size_t index = serviceParameterCount; index < function.parameters.size(); ++index)
            require(scalarValueType(function.parameters[index], enumCases) ||
                        function.parameters[index] == Type::ByteSpan,
                    "service signature requires later scalar, enum or readonly span arguments");
        require(scalarValueType(function.result, enumCases) ||
                    (kinds.contains(service::Kind::Console) && function.result == service::sampleType()) ||
                    (kinds.contains(service::Kind::IommuEvent) && function.result == service::eventSampleType()),
                "service signature has unsupported result");
    }
    require(serviceFunction || function.serviceSlots.empty(), "service spills without a service signature");
    if (function.borrowedParameter) {
        require(function.receiver && !function.receiver->constructor &&
                    owningClass(classFields, function.receiver->className),
                "borrowed formal requires nonconstructor owning receiver shape");
        require(!resourceFunction && !function.result.isSpan() && !function.receiverSpanField,
                "borrowed formal cannot have resource or borrowed result");
        require(function.parameters.size() <= 5, "borrowed formal counts toward six parameters");
    }
    if (function.secondBorrowedParameter) {
        const auto &second = *function.secondBorrowedParameter;
        require(function.borrowedParameter && function.receiver && function.receiver->mutableValue &&
                    !function.receiver->constructor && !second.mutableValue && !second.constructor,
                "paired borrowed formals require mutable first and readonly second owning roots");
        require(classLayouts.contains(second.className) && owningClass(classFields, second.className) &&
                    !classArrayCarriers.contains(second.className),
                "second borrowed formal requires known owning class");
        require(function.parameters.size() <= 4, "two borrowed formals count toward six parameters");
        require(scalarValueType(function.result, enumCases) &&
                    std::all_of(function.parameters.begin(), function.parameters.end(), [&](const Type &type) {
                        return scalarValueType(type, enumCases);
                    }),
                "paired borrowed signature requires scalar or enum values");
    }
    if (resourceFunction) {
        require(!function.receiver || owningConstructor,
                "resource signature only supports an owning constructor receiver");
        require(!function.parameters.empty() && function.parameters.front() == Type::ByteRegion,
                "resource signature requires its region parameter first");
        require(scalarValueType(function.result, enumCases) || function.result.isOwnerStorage() ||
                    (!function.receiver && function.result.isClass()),
                "resource signature requires scalar, owned byte or class result");
        for (std::size_t index = 1; index < function.parameters.size(); ++index)
            require(scalarValueType(function.parameters[index], enumCases) ||
                        function.parameters[index].isOwnerStorage() ||
                        (!function.receiver && owningType(function.parameters[index])) ||
                        (owningConstructor && function.parameters[index].isClass() &&
                         !owningType(function.parameters[index])),
                    "resource signature requires exactly one region and supported owning parameters");
    }
    auto boundaryType = [&](const Type &type, bool parameter) {
        if (scalarValueType(type, enumCases))
            return;
        if (type.isService()) {
            require(parameter && serviceFunction, "service capability cannot cross an ordinary boundary or return");
            return;
        }
        if (type.isResource()) {
            require(resourceFunction && (type.isOwnerStorage() || (parameter && type == Type::ByteRegion)),
                    "invalid resource boundary type");
            if (type.isOwnerStorage())
                verifyOwnerType(type, classLayouts, classFields, storage, classArrayCarriers);
            return;
        }
        if (type.isSpan()) {
            require(type == Type::ByteSpan && ((parameter && (!function.receiver || !function.receiver->constructor)) ||
                                               (!parameter && function.receiver && !function.receiver->mutableValue &&
                                                !function.receiver->constructor && function.receiverSpanField)),
                    "readonly span boundary requires ordinary parameter or const receiver result");
            return;
        }
        require(!function.receiver || parameter || !function.receiver->constructor,
                "constructor result must remain scalar");
        require(type.isClass() && type == Type(type.className), "invalid value boundary type");
        require(classLayouts.contains(type.className), "unknown value boundary class");
        require(!classArrayCarriers.contains(type.className), "class array carrier cannot cross value boundary");
        require(!owningType(type) || (resourceFunction && !function.receiver),
                "owning class requires an ordinary resource boundary");
        require(!resourceFunction || owningType(type) || !parameter || owningConstructor,
                "only an owning constructor may take a copied class resource parameter");
        require(copiedClassLeavesSupported(classLayouts.at(type.className)),
                "value boundary class exceeds 64 scalar fields excluding u8, 512 u8 leaves or 513 total leaves");
        require(storage.at(type.className).reservedBytes <= maximumCopiedClassBytes,
                "value boundary class storage exceeds 520 bytes");
    };
    require(!function.receiverSpanField || function.result == Type::ByteSpan,
            "receiver span field summary requires span result");
    boundaryType(function.result, false);
    require(function.parameters.size() <= 6, "too many parameters");
    for (const auto &type : function.parameters)
        boundaryType(type, true);
    require(function.frameBytes >= 0 && function.frameBytes <= 65536 && function.frameBytes % 16 == 0,
            "invalid frame size");
    std::set<int> occupiedSlotBytes;
    for (const auto &[offset, type] : function.slots) {
        require(offset >= storageWidth(type) && offset <= function.frameBytes && offset % storageAlignment(type) == 0,
                "invalid slot offset");
        require(scalarValueType(type, enumCases) || type == Type::Ref || type == Type::MutRef,
                "invalid slot payload type");
        for (int byte = offset - storageWidth(type) + 1; byte <= offset; ++byte)
            require(occupiedSlotBytes.insert(byte).second, "overlapping scalar slot storage");
    }
    const std::vector<Type> *receiverLayout = nullptr;
    const std::vector<ClassField> *receiverFields = nullptr;
    std::vector<ClassField> legacyReceiverFields;
    if (function.receiver) {
        const auto &receiver = *function.receiver;
        require(classLayouts.contains(receiver.className), "unknown receiver class");
        require(!classArrayCarriers.contains(receiver.className), "class array carrier cannot be receiver");
        receiverLayout = &classLayouts.at(receiver.className);
        if (classFields.contains(receiver.className))
            receiverFields = &classFields.at(receiver.className);
        else {
            for (std::size_t leaf = 0; leaf < receiverLayout->size(); ++leaf)
                legacyReceiverFields.push_back(ClassField{(*receiverLayout)[leaf], static_cast<int>(leaf), 1, false});
            receiverFields = &legacyReceiverFields;
        }
        require(!receiver.constructor || (receiver.mutableValue && function.result == Type::I64),
                "invalid constructor receiver signature");
    }
    if (function.receiverSpanField) {
        const int field = *function.receiverSpanField;
        require(receiverFields && field >= 0 && static_cast<std::size_t>(field) < receiverFields->size() &&
                    (((*receiverFields)[field].elementType == Type::OwnedBytes && !(*receiverFields)[field].array) ||
                     ((*receiverFields)[field].elementType == Type::U8 && (*receiverFields)[field].array)),
                "receiver span field summary requires exact direct byte-storage field");
    }
    // Physical reservation and logical completion are separate. Every occupied
    // scalar byte is disjoint; object padding (including empty storage) has no slot.
    std::map<int, const ObjectSlot *> objectFields;
    std::map<int, int> objectBases;
    std::set<int> objectStorage;
    std::set<int> nestedObjectLeaves;
    for (const auto &[base, object] : function.objectSlots) {
        require(classLayouts.contains(object.className), "unknown object class");
        const auto &layout = classLayouts.at(object.className);
        const auto &physical = storage.at(object.className);
        require(base > 0 && base <= function.frameBytes && base % 8 == 0 && base >= physical.reservedBytes,
                "invalid object layout offset");
        if (classFields.contains(object.className))
            for (const auto &field : classFields.at(object.className))
                if (field.elementType.isClass())
                    for (int leaf = 0; leaf < field.length; ++leaf)
                        nestedObjectLeaves.insert(objectLeaf(base, field.firstLeaf + leaf));
        for (int byte = base - physical.reservedBytes + 1; byte <= base; ++byte)
            require(objectStorage.insert(byte).second, "overlapping object layouts");
        for (std::size_t index = 0; index < layout.size(); ++index) {
            const int offset = objectLeaf(base, index);
            require(function.slots.contains(offset) && function.slots.at(offset) == layout[index],
                    "object field slot type/layout mismatch");
            objectFields.emplace(offset, &object);
            objectBases.emplace(offset, base);
        }
    }
    for (const auto &[offset, type] : function.slots)
        for (int byte = offset - storageWidth(type) + 1; byte <= offset; ++byte)
            require(!objectStorage.contains(byte) || objectFields.contains(offset),
                    "scalar slot overlaps empty object or padding");
    // Array declarations are exact standalone u8 origins, not object projections
    // or arbitrarily overlapping scalar reservations. Their scalar leaves are
    // still addressed by ordinary typed loads/stores during initialization.
    std::map<int, int> arrayBases;
    std::set<int> arrayStorage;
    for (const auto &[base, length] : function.arraySlots) {
        require(length >= 1 && length <= 4096 && base >= length && base <= function.frameBytes,
                "invalid byte array origin extent");
        for (int element = 0; element < length; ++element) {
            const int offset = base - element;
            require(function.slots.contains(offset) && function.slots.at(offset) == Type::U8,
                    "byte array origin requires exact u8 element slots");
            require(!objectStorage.contains(offset), "byte array origin overlaps object storage");
            require(arrayStorage.insert(offset).second, "overlapping byte array origins");
            arrayBases.emplace(offset, base);
        }
    }
    std::set<int> spanStorage;
    for (int base : function.spanSlots) {
        require(base >= spanBytes && base <= function.frameBytes && base % 8 == 0,
                "invalid span spill extent or alignment");
        for (int byte = base - spanBytes + 1; byte <= base; ++byte) {
            require(!occupiedSlotBytes.contains(byte) && !objectStorage.contains(byte) && !arrayStorage.contains(byte),
                    "span spill overlaps scalar, object or array storage");
            require(spanStorage.insert(byte).second, "overlapping span spills");
        }
    }
    std::set<int> resourceStorage;
    auto reserveResource = [&](int base, int width, const std::string &name) {
        require(base >= width && base <= function.frameBytes && base % 8 == 0,
                "invalid " + name + " spill extent or alignment");
        for (int byte = base - width + 1; byte <= base; ++byte) {
            require(!occupiedSlotBytes.contains(byte) && !objectStorage.contains(byte) &&
                        !arrayStorage.contains(byte) && !spanStorage.contains(byte),
                    name + " spill overlaps scalar, object, array or span storage");
            require(resourceStorage.insert(byte).second, "overlapping region or owned byte spills");
        }
    };
    for (int base : function.serviceSlots)
        reserveResource(base, service::capabilityBytes, "service");
    for (int base : function.regionSlots)
        reserveResource(base, 8, "region");
    for (const auto &[base, mutableValue] : function.byteSlots) {
        (void)mutableValue;
        reserveResource(base, 32, "owned byte");
    }
    // Physical offset/layout validation above proves every slot belongs to the
    // existing bounded frame. Share this immutable dense domain across snapshots.
    std::vector<int> initializationOffsets;
    initializationOffsets.reserve(function.slots.size());
    for (const auto &[offset, type] : function.slots) {
        (void)type;
        initializationOffsets.push_back(offset);
    }
    const auto initializationUniverse =
        std::make_shared<const InitializationSlotUniverse>(std::move(initializationOffsets), function.frameBytes);
    require(!function.code.empty(), "empty function body");
    std::set<int> scalarParameterSlots;
    std::set<int> objectParameterSlots;
    std::set<int> spanParameterSlots;
    std::set<int> byteParameterSlots;
    std::optional<int> regionParameterSlot;
    std::map<int, int> serviceParameterSlots; // source index -> distinct root spill
    std::map<int, int> spanParameterOrigins;  // source position -> root spill
    for (std::size_t index = 0; index < function.code.size(); ++index) {
        if (const auto *literal = std::get_if<BorrowLiteralSpan>(&function.code[index])) {
            require(literal->bytes.size() <= maxByteStringBytes, "literal span exceeds byte-string bound");
            require(function.spanSlots.contains(literal->resultOffset), "literal span requires exact typed spill");
        }
        const auto *serviceBinding = std::get_if<BindServiceParameter>(&function.code[index]);
        const auto *binding = std::get_if<BindParameter>(&function.code[index]);
        const auto *objectBinding = std::get_if<BindObjectParameter>(&function.code[index]);
        const auto *spanBinding = std::get_if<BindSpanParameter>(&function.code[index]);
        const auto *regionBinding = std::get_if<BindRegionParameter>(&function.code[index]);
        const auto *byteBinding = std::get_if<BindBytesParameter>(&function.code[index]);
        const auto *ownedObjectBinding = std::get_if<BindOwnedObjectParameter>(&function.code[index]);
        if (index < function.parameters.size()) {
            const auto &type = function.parameters[index];
            if (type.isService()) {
                require(serviceBinding && serviceBinding->index == static_cast<int>(index) &&
                            index < serviceParameterCount,
                        "service bindings must form the leading entry group");
                for (const auto &[position, root] : serviceParameterSlots) {
                    (void)position;
                    require(root != serviceBinding->offset, "service parameter bindings overlap");
                }
                serviceParameterSlots.emplace(static_cast<int>(index), serviceBinding->offset);
            } else if (type.isRegion()) {
                require(regionBinding && regionBinding->index == 0 && index == 0,
                        "region parameter binding must begin the entry prefix");
                require(!regionParameterSlot, "duplicate region parameter binding");
                regionParameterSlot = regionBinding->offset;
            } else if (type.isOwnerStorage()) {
                require(byteBinding && byteBinding->index == static_cast<int>(index),
                        "owned byte parameter bindings must form the entry prefix");
                require(byteParameterSlots.insert(byteBinding->offset).second, "owned byte parameter bindings overlap");
            } else if (owningType(type)) {
                require(ownedObjectBinding && ownedObjectBinding->index == static_cast<int>(index),
                        "owning class parameter bindings must form the entry prefix");
                require(objectParameterSlots.insert(ownedObjectBinding->offset).second,
                        "owning class parameter bindings overlap");
            } else if (type.isClass()) {
                require(objectBinding && objectBinding->index == static_cast<int>(index),
                        "object parameter bindings must form the entry prefix");
                require(objectParameterSlots.insert(objectBinding->offset).second, "object parameter bindings overlap");
            } else if (type.isSpan()) {
                require(spanBinding && spanBinding->index == static_cast<int>(index),
                        "span parameter bindings must form the entry prefix");
                require(spanParameterSlots.insert(spanBinding->offset).second, "span parameter bindings overlap");
                spanParameterOrigins.emplace(static_cast<int>(index), spanBinding->offset);
            } else {
                require(binding && binding->index == static_cast<int>(index),
                        "parameter bindings must form the entry prefix");
                require(scalarParameterSlots.insert(binding->offset).second, "scalar parameter bindings overlap");
            }
        } else
            require(!binding && !objectBinding && !spanBinding && !regionBinding && !byteBinding &&
                        !ownedObjectBinding && !serviceBinding,
                    "parameter binding outside entry prefix");
    }
    std::map<int, std::size_t> labels;
    std::map<int, std::pair<int, service::Kind>> serviceLoanRoots;
    for (std::size_t index = 0; index < function.code.size(); ++index) {
        if (const auto *loan = std::get_if<AcquireServiceLoan>(&function.code[index])) {
            const auto root = std::pair{loan->offset, loan->kind};
            require(loan->loanId > 0 &&
                        (!serviceLoanRoots.contains(loan->loanId) || serviceLoanRoots.at(loan->loanId) == root),
                    "service loan identity cannot change static root or kind");
            serviceLoanRoots.emplace(loan->loanId, root);
        }
        if (const auto *label = std::get_if<Label>(&function.code[index]))
            require(label->id >= 0 && labels.emplace(label->id, index).second, "duplicate or invalid label");
    }
    // Check targets even in unreachable instructions, so they cannot hide malformed references.
    for (const auto &instruction : function.code) {
        if (const auto *jump = std::get_if<Jump>(&instruction))
            require(labels.contains(jump->target), "unknown jump target");
        if (const auto *branch = std::get_if<BranchFalse>(&instruction))
            require(labels.contains(branch->target), "unknown branch target");
    }
    // Only block entries retain snapshots. Saving a full state at every instruction
    // makes a straight-line N-element initializer retain O(N^2) stack/set contents.
    std::vector<bool> blockEntry(function.code.size(), false);
    std::vector<bool> reached(function.code.size(), false);
    // Depths alone are linear-sized. Full operand/provenance states still live
    // only at basic-block entries, never once per instruction.
    std::vector<std::size_t> stackBefore(function.code.size()), stackAfter(function.code.size());
    blockEntry[0] = true;
    for (std::size_t index = 0; index < function.code.size(); ++index) {
        if (std::holds_alternative<Label>(function.code[index]))
            blockEntry[index] = true;
        if (std::holds_alternative<BranchFalse>(function.code[index]) && index + 1 < function.code.size())
            blockEntry[index + 1] = true;
    }
    std::vector<std::optional<State>> states(function.code.size());
    BlockRetentionBudget retention;
    retention.retain(0);
    states[0] = State{initializationUniverse};
    if (function.receiver && owningClass(classFields, function.receiver->className)) {
        OwnedObjectBinding receiver{
            0, function.receiver->constructor ? ByteDisposition::Pristine : ByteDisposition::Live, {}};
        const RegionIdentity borrowed{0, 0, true};
        for (std::size_t field = 0; field < receiverFields->size(); ++field)
            if ((*receiverFields)[field].elementType.isOwnerStorage()) {
                ByteBinding binding{0, receiver.disposition, {}};
                if (!function.receiver->constructor)
                    binding.token = ByteToken{0, borrowed, static_cast<int>(field)};
                receiver.fields.emplace(static_cast<int>(field), binding);
            }
        states[0]->ownedObjects.emplace(0, std::move(receiver));
    }
    if (function.secondBorrowedParameter) {
        OwnedObjectBinding second{0, ByteDisposition::Live, {}};
        // The selector distinguishes symbolic provenance even when both formal
        // classes and field ordinals match. It is never allocation authority.
        const RegionIdentity borrowed{-1, 0, true};
        const auto &fields = classFields.at(function.secondBorrowedParameter->className);
        for (std::size_t field = 0; field < fields.size(); ++field)
            if (fields[field].elementType.isOwnerStorage())
                second.fields.emplace(static_cast<int>(field),
                                      ByteBinding{0,
                                                  ByteDisposition::Live,
                                                  ByteToken{0, borrowed, static_cast<int>(field)}});
        states[0]->ownedObjects.emplace(-1, std::move(second));
    }
    if (function.receiver && !function.receiver->constructor) {
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
    std::deque<std::size_t> pending{0};
    std::size_t retainedValueFacts = 0;
    if (metrics) {
        *metrics = Metrics{};
        metrics->snapshots = 1;
    }
    auto slot = [&](int offset, const Type &type) {
        const auto found = function.slots.find(offset);
        require(found != function.slots.end() && found->second == type, "slot type/layout mismatch");
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
    auto enqueue = [&](std::size_t index, const State &state) {
        require(index < function.code.size(), "reachable fallthrough without return");
        require(blockEntry[index], "worklist target is not a basic-block entry");
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
            reached[index] = true;
            stackBefore[index] = state.stack.size();
            bool fallsThrough = true;
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
            // Only the validated BorrowedCall may exercise its one or two loans.
            const auto *borrowedCall = std::get_if<BorrowedCall>(&function.code[index]);
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
                    const auto &name = function.objectSlots.at(root).className;
                    for (const auto &[unused, capability] : state.activeSpans) {
                        (void)unused;
                        if (capability.arrayField < 0 || capability.origin != root)
                            continue;
                        const int first = storage.at(name).fieldOffsets.at(capability.arrayField);
                        const int length = classFields.at(name).at(capability.arrayField).length;
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
            auto span = [&](int base) -> const SpanCapability & {
                require(function.spanSlots.contains(base), "span requires exact typed spill");
                require(state.activeSpans.contains(base), "span capability is not active");
                const auto &capability = state.activeSpans.at(base);
                if (capability.literalOrigin) {
                    require(!capability.parameterOrigin && !capability.ownedToken && capability.ownedField == -1,
                            "literal span cannot carry another origin kind");
                    require(capability.originSite < function.code.size(), "literal span origin site is invalid");
                    const auto *literal = std::get_if<BorrowLiteralSpan>(&function.code[capability.originSite]);
                    require(literal && literal->resultOffset == capability.origin &&
                                literal->bytes.size() <= maxByteStringBytes,
                            "literal span must retain its exact immutable origin");
                } else if (capability.arrayField >= 0) {
                    require(!capability.parameterOrigin && !capability.ownedToken && capability.ownedField == -1,
                            "fixed array span cannot carry another origin kind");
                    loanAccess(capability.origin, false);
                    if (capability.origin == 0) {
                        require(function.receiver && !function.receiver->constructor && capability.originSite == 0,
                                "fixed array span receiver lifetime is not active");
                    } else {
                        require(state.activeObjects.contains(capability.origin) &&
                                    state.activeObjects.at(capability.origin) == capability.originSite,
                                "fixed array span object lifetime is not active");
                    }
                    const auto &name = capability.origin == 0 ? function.receiver->className
                                                              : function.objectSlots.at(capability.origin).className;
                    const auto &fields = classFields.at(name);
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
                        require(capability.origin == 0 && capability.ownedField >= 0 && function.receiver,
                                "span borrowed receiver provenance mismatch");
                    else
                        require(state.activeRegions.contains(identity.offset) &&
                                    state.activeRegions.at(identity.offset) == identity,
                                "span owner region identity is not active");
                } else if (capability.parameterOrigin) {
                    require(spanParameterOrigins.contains(capability.origin), "span parameter origin does not exist");
                    const auto root = state.activeSpans.find(spanParameterOrigins.at(capability.origin));
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
            auto spanTarget = [&](int base) {
                require(function.spanSlots.contains(base), "span requires exact typed spill");
                require(!spanParameterSlots.contains(base), "span parameter cannot be rebound");
                require(!state.activeSpans.contains(base), "span spill is already active");
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
            auto region = [&](int base) -> RegionIdentity {
                require(function.regionSlots.contains(base), "region requires exact typed spill");
                require(state.activeRegions.contains(base), "region authority is not active");
                return state.activeRegions.at(base);
            };
            auto byteBinding = [&](int base) -> ByteBinding & {
                require(function.byteSlots.contains(base), "owned byte operation requires exact typed spill");
                require(state.activeBytes.contains(base), "owned byte lifetime is not active");
                return state.activeBytes.at(base);
            };
            auto bytes = [&](int base, bool mutableAccess) -> ByteBinding & {
                auto &binding = byteBinding(base);
                require(binding.disposition == ByteDisposition::Live && binding.token.has_value(),
                        "owned byte binding does not hold live ownership");
                require(region(binding.token->region.offset) == binding.token->region,
                        "owned byte region identity does not match active authority");
                require(!mutableAccess || function.byteSlots.at(base),
                        "const owned byte binding cannot be mutated or moved");
                if (mutableAccess)
                    ownerWritable(base, -1);
                return binding;
            };
            auto byteTarget = [&](int base) -> ByteBinding & {
                auto &binding = byteBinding(base);
                require(binding.disposition == ByteDisposition::Pristine && !binding.token,
                        "owned byte result requires pristine binding");
                return binding;
            };
            auto freshToken = [&](const RegionIdentity &origin, int ordinal) {
                auto distinct = [&](const ByteBinding &other) {
                    require(!other.token || other.token->region.borrowed || other.token->site != index ||
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
                return ByteToken{index, origin, ordinal};
            };
            auto mintBytes = [&](int base, const RegionIdentity &origin) {
                auto &binding = byteTarget(base);
                const auto token = freshToken(origin, -1);
                binding.disposition = ByteDisposition::Live;
                binding.token = token;
            };
            auto consumeBytes = [&](int base) {
                ownerWritable(base, -1);
                auto &binding = byteBinding(base);
                binding.disposition = ByteDisposition::Consumed;
                binding.token.reset();
            };
            auto store = [&](int offset, const Type &type) {
                slot(offset, type);
                activeObjectField(offset);
                if (objectBases.contains(offset))
                    loanAccess(objectBases.at(offset), true);
                activeArrayElement(offset);
                arrayWritable(offset);
                require(!nestedObjectLeaves.contains(offset), "scalar store cannot write nested class field");
                require(!scalarParameterSlots.contains(offset) || !state.maybeInitialized.contains(offset),
                        "write to immutable scalar parameter");
                const auto object = objectFields.find(offset);
                require(object == objectFields.end() || object->second->mutableValue ||
                            !state.maybeInitialized.contains(offset),
                        "write to initialized const object field");
                state.initialized.insert(offset);
                state.maybeInitialized.insert(offset);
            };
            auto receiverShape = [&](int fieldIndex, bool verifiedMethodView = false) -> const ClassField & {
                require(!function.borrowedParameter || verifiedMethodView,
                        "borrowed free formal grants no direct receiver field authority");
                loanAccess(0, false);
                require(receiverFields != nullptr, "receiver access without bound receiver");
                require(fieldIndex >= 0 && static_cast<std::size_t>(fieldIndex) < receiverFields->size(),
                        "receiver field type/layout mismatch");
                return (*receiverFields)[fieldIndex];
            };
            auto receiverField = [&](int fieldIndex, const Type &type) -> const ClassField & {
                const auto &field = receiverShape(fieldIndex);
                require(!field.array && scalarValueType(field.elementType, enumCases) && field.elementType == type,
                        "receiver field type/layout mismatch");
                return field;
            };
            auto receiverArray = [&](int fieldIndex, bool initialized) -> const ClassField & {
                const auto &field = receiverShape(fieldIndex);
                require(field.array, "receiver array operation requires array field");
                require(scalar(field.elementType), "receiver scalar array operation requires scalar array field");
                if (initialized) {
                    require(!function.receiver->constructor,
                            "constructor cannot access receiver array during initialization");
                    for (int element = 0; element < field.length; ++element)
                        require(state.receiverInitialized.contains(field.firstLeaf + element),
                                "receiver array element not initialized");
                }
                return field;
            };
            auto receiverEvidence = [&](int fieldIndex, const ClassField &field) {
                return ReceiverGuard{
                    function.receiver->className, fieldIndex, field.firstLeaf, field.length, field.elementType};
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
                const auto &name = function.objectSlots.at(base).className;
                if (classFields.contains(name))
                    for (std::size_t field = 0; field < classFields.at(name).size(); ++field)
                        if (classFields.at(name)[field].elementType.isClass())
                            require(state.objectClassesInitialized.contains({base, static_cast<int>(field)}),
                                    "nested class field not completely initialized");
                if (classLayouts.at(name).empty())
                    require(state.objectClassesInitialized.contains({base, -1}),
                            "empty object not completely initialized");
            };
            auto markObject = [&](int base) {
                const auto &name = function.objectSlots.at(base).className;
                const auto &layout = classLayouts.at(name);
                state.maybeConstructedObjects.insert(base);
                state.objectClassesInitialized.insert({base, -1});
                for (std::size_t leaf = 0; leaf < layout.size(); ++leaf) {
                    const int offset = objectLeaf(base, leaf);
                    state.initialized.insert(offset);
                    state.maybeInitialized.insert(offset);
                }
                if (classFields.contains(name))
                    for (std::size_t field = 0; field < classFields.at(name).size(); ++field)
                        if (classFields.at(name)[field].elementType.isClass())
                            state.objectClassesInitialized.insert({base, static_cast<int>(field)});
            };
            auto completeObject = [&](int base) -> const ObjectSlot & {
                loanAccess(base, false);
                require(function.objectSlots.contains(base), "copy requires exact object slot");
                require(state.activeObjects.contains(base), "copy object outside active lifetime");
                const auto &object = function.objectSlots.at(base);
                const auto &layout = classLayouts.at(object.className);
                for (std::size_t leaf = 0; leaf < layout.size(); ++leaf)
                    require(state.initialized.contains(objectLeaf(base, leaf)),
                            "copy source object not fully initialized");
                logicalComplete(base);
                return object;
            };
            auto boundRoot = [&](int root) -> const Receiver & {
                require(root == 0 || root == -1, "invalid bound object root selector");
                const auto &formal = root == 0 ? function.receiver : function.secondBorrowedParameter;
                require(formal.has_value(), "borrowed object root is not bound");
                return *formal;
            };
            auto liveOwningRoot = [&](int root) -> const OwnedObjectBinding & {
                require(root >= -1, "invalid borrowed object root");
                const auto &name = root <= 0 ? boundRoot(root).className : completeObject(root).className;
                require(owningClass(classFields, name) && state.ownedObjects.contains(root),
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
            auto completeClassField = [&](int base, int index, bool mutableAccess) -> const ClassField & {
                loanAccess(base, mutableAccess);
                require(base >= 0, "invalid owned field root offset");
                const ClassField *field = nullptr;
                if (base == 0) {
                    field = &receiverShape(index);
                    require(!function.receiver->constructor,
                            "constructor cannot access owned field during initialization");
                    require(!mutableAccess || function.receiver->mutableValue,
                            "const receiver cannot supply mutable owned field");
                    require(state.receiverClassesInitialized.contains(index),
                            "receiver nested class field not initialized");
                } else {
                    const auto &root = completeObject(base);
                    require(!mutableAccess || root.mutableValue, "const object cannot supply mutable owned field");
                    require(classFields.contains(root.className) && index >= 0 &&
                                static_cast<std::size_t>(index) < classFields.at(root.className).size(),
                            "owned field logical index out of range");
                    field = &classFields.at(root.className)[index];
                }
                require(!field->array && field->elementType.isClass(), "owned field operation requires class field");
                return *field;
            };
            auto completeClassArray = [&](int base, int fieldIndex, bool mutableAccess) -> const ClassField & {
                require(base >= 0, "invalid class array root offset");
                loanAccess(base, mutableAccess);
                const ClassField *field = nullptr;
                if (base == 0) {
                    field = &receiverShape(fieldIndex);
                    require(!function.receiver->constructor,
                            "constructor cannot access class array during initialization");
                    require(!mutableAccess || function.receiver->mutableValue,
                            "const receiver cannot supply mutable class array");
                    require(state.receiverClassesInitialized.contains(fieldIndex),
                            "receiver class array not completely initialized");
                } else {
                    const auto &root = completeObject(base);
                    require(!mutableAccess || root.mutableValue, "const object cannot supply mutable class array");
                    require(classFields.contains(root.className) && fieldIndex >= 0 &&
                                static_cast<std::size_t>(fieldIndex) < classFields.at(root.className).size(),
                            "class array logical field index out of range");
                    field = &classFields.at(root.className)[fieldIndex];
                }
                require(field->array && field->elementType.isClass(),
                        "class array operation requires class array field");
                require(!owningClass(classFields, field->elementType.className),
                        "class array elements must be copied values");
                return *field;
            };
            auto classArrayEvidence = [&](int base, int fieldIndex, const ClassField &field) {
                return ClassArrayGuard{base,
                                       base == 0 ? function.receiver->className
                                                 : function.objectSlots.at(base).className,
                                       fieldIndex,
                                       field.elementType,
                                       field.elementCount};
            };
            auto checkedClassArray = [&](int base, int fieldIndex, const ClassField &field) {
                require(current(Type::I64).guard ==
                            std::optional<BoundsEvidence>(classArrayEvidence(base, fieldIndex, field)),
                        "class array access lacks matching dominating bounds token");
            };
            auto copyTarget = [&](int base, const std::string &name) {
                require(function.objectSlots.contains(base), "copy requires exact object slot");
                require(state.activeObjects.contains(base), "copy object outside active lifetime");
                require(function.objectSlots.at(base).className == name, "copy nominal class mismatch");
                require(!state.maybeConstructedObjects.contains(base), "copy result object already initialized");
                const auto &layout = classLayouts.at(name);
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
            auto beginOwnedObject = [&](int base, const std::string &name) {
                require(!state.ownedObjects.contains(base), "owning object lifetime already active");
                OwnedObjectBinding object{index, ByteDisposition::Pristine, {}};
                for (std::size_t field = 0; field < classFields.at(name).size(); ++field)
                    if (classFields.at(name)[field].elementType.isOwnerStorage())
                        object.fields.emplace(static_cast<int>(field),
                                              ByteBinding{index, ByteDisposition::Pristine, {}});
                state.ownedObjects.emplace(base, std::move(object));
            };
            auto mintObject = [&](int base, const std::string &name, const RegionIdentity &origin) {
                require(owningClass(classFields, name), "owning result requires owning class");
                copyTarget(base, name);
                auto &object = state.ownedObjects.at(base);
                for (auto &[ordinal, field] : object.fields) {
                    field.token = freshToken(origin, ordinal);
                    field.disposition = ByteDisposition::Live;
                }
                object.disposition = ByteDisposition::Live;
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
            auto ownedObject = [&](int base, const std::string &name, bool mutableAccess) -> RegionIdentity {
                const auto &slot = completeObject(base);
                require(slot.className == name && owningClass(classFields, name),
                        "owning object nominal class mismatch");
                require(!mutableAccess || slot.mutableValue, "const owning object cannot be moved or mutated");
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
            auto accessBytes =
                [&](int base, int ordinal, bool mutableAccess, bool verifiedMethodView = false) -> const ByteBinding & {
                loanAccess(base, mutableAccess);
                require(ordinal >= -1, "invalid owned byte field selector");
                if (ordinal == -1)
                    return bytes(base, mutableAccess);
                require(base >= 0, "invalid owned byte object root");
                if (base == 0) {
                    const auto &field = receiverShape(ordinal, verifiedMethodView);
                    require(field.elementType.isOwnerStorage() && !field.array,
                            "owned byte access requires direct resource field");
                    require(!function.receiver->constructor,
                            "constructor cannot access resource field during initialization");
                    require(!mutableAccess || function.receiver->mutableValue,
                            "const receiver cannot mutate resource field");
                } else {
                    const auto &object = completeObject(base);
                    require(!mutableAccess || object.mutableValue, "const object cannot mutate resource field");
                    require(classFields.contains(object.className) &&
                                static_cast<std::size_t>(ordinal) < classFields.at(object.className).size() &&
                                classFields.at(object.className)[ordinal].elementType.isOwnerStorage() &&
                                !classFields.at(object.className)[ordinal].array,
                            "owned byte access requires direct resource field");
                }
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
            auto accessedOwnerType = [&](int base, int ordinal) {
                if (ordinal == -1)
                    return ownerType(base);
                require(ordinal >= 0 && base >= 0, "invalid owned storage field selector");
                const auto &name = base == 0 ? function.receiver->className : function.objectSlots.at(base).className;
                const auto &type = classFields.at(name).at(ordinal).elementType;
                verifyOwnerType(type, classLayouts, classFields, storage, classArrayCarriers);
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
                require(!owningClass(classFields, value.className) && !classArrayCarriers.contains(value.className),
                        "owned value snapshot must be copied class");
            };
            auto borrowOwned = [&](int root, int ordinal, int result, bool verifiedMethodView = false) {
                const auto &binding = accessBytes(root, ordinal, false, verifiedMethodView);
                require(accessedOwnerType(root, ordinal) == Type::OwnedBytes,
                        "typed owned values cannot supply a byte span");
                spanTarget(result);
                const auto rootSite = ordinal == -1 ? binding.site : state.ownedObjects.at(root).site;
                state.activeSpans.emplace(result,
                                          SpanCapability{false, root, rootSite, 0, 0, index, binding.token, ordinal});
            };
            auto borrowArrayField = [&](int root, int ordinal, int result, bool verifiedMethodView = false) {
                require(root >= 0 && ordinal >= 0, "invalid fixed array span root or field");
                loanAccess(root, false);
                const ClassField *field = nullptr;
                std::size_t site = 0;
                if (root == 0) {
                    field = &receiverShape(ordinal, verifiedMethodView);
                    require(!function.receiver->constructor, "constructor cannot borrow receiver array");
                    for (int leaf = 0; leaf < field->length; ++leaf)
                        require(state.receiverInitialized.contains(field->firstLeaf + leaf),
                                "receiver array span requires complete initialization");
                } else {
                    require(verifiedMethodView, "local fixed array fields require verified receiver result");
                    const auto &object = completeObject(root);
                    const auto &fields = classFields.at(object.className);
                    require(static_cast<std::size_t>(ordinal) < fields.size(), "fixed array span field out of range");
                    field = &fields[ordinal];
                    site = state.activeObjects.at(root);
                }
                require(field->array && field->elementType == Type::U8,
                        "fixed array span requires direct u8 array field");
                spanTarget(result);
                state.activeSpans.emplace(result,
                                          SpanCapability{false, root, site, 0, 0, index, {}, -1, false, ordinal});
            };
            auto closedOwnedObjects = [&]() {
                require(state.serviceLoans.empty(), "return with active synchronous service loan");
                require(state.objectLoans.empty(), "return with active synchronous object loan");
                for (const auto &[base, unused] : state.ownedObjects) {
                    (void)unused;
                    require((base == 0 && function.receiver.has_value()) ||
                                (base == -1 && function.secondBorrowedParameter.has_value()),
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
                        require(operation.type.isEnum() && scalarValueType(operation.type, enumCases),
                                "invalid enum constant type");
                        require(operation.caseIndex >= 0 &&
                                    operation.caseIndex < enumCases.at(operation.type.className),
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
                        require(scalarValueType(operation.operandType, enumCases), "non-scalar comparison");
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
                            require(!scalarParameterSlots.contains(offset),
                                    "indexed write to immutable scalar parameter");
                            require(!objectFields.contains(offset) || objectFields.at(offset)->mutableValue,
                                    "indexed write to const object field");
                        }
                    } else if constexpr (std::is_same_v<Op, BorrowHandle>) {
                        slot(operation.ownerOffset, Type::I64);
                        require(!objectFields.contains(operation.ownerOffset),
                                "object field cannot become a scalar borrow handle");
                        require(state.initialized.contains(operation.ownerOffset), "borrow of uninitialized payload");
                        require(operation.referenceType == Type::Ref || operation.referenceType == Type::MutRef,
                                "invalid borrow-handle type");
                        state.current = Value{operation.referenceType, {}};
                    } else if constexpr (std::is_same_v<Op, Call>) {
                        require(!operation.callee.starts_with("__au_runtime_"),
                                "ordinary call cannot target runtime symbol");
                        require(functions.contains(operation.callee), "unknown call target");
                        const auto &target = *functions.at(operation.callee);
                        require(!target.receiver, "plain call cannot target receiver function");
                        require(!serviceSignature(target), "plain call cannot bypass a service loan");
                        require(!resourceSignature(target, classFields), "plain call cannot target resource signature");
                        require(scalarValueType(target.result, enumCases) &&
                                    std::all_of(target.parameters.begin(),
                                                target.parameters.end(),
                                                [&](const Type &type) {
                                                    return scalarValueType(type, enumCases);
                                                }),
                                "plain call cannot target aggregate signature");
                        for (auto argument = target.parameters.rbegin(); argument != target.parameters.rend();
                             ++argument)
                            require(pop().type == *argument, "call argument type mismatch");
                        state.current = Value{target.result, {}};
                    } else if constexpr (std::is_same_v<Op, AggregateCall>) {
                        require(functions.contains(operation.callee), "unknown aggregate call target");
                        const auto &target = *functions.at(operation.callee);
                        require(!target.receiver, "aggregate call cannot target receiver function");
                        require(!serviceSignature(target), "aggregate call cannot bypass a service loan");
                        require(!resourceSignature(target, classFields),
                                "aggregate call cannot target resource signature");
                        require(target.result.isClass() || std::any_of(target.parameters.begin(),
                                                                       target.parameters.end(),
                                                                       [](const Type &type) {
                                                                           return type.isClass() || type.isSpan();
                                                                       }),
                                "aggregate call requires aggregate signature");
                        require(operation.objectArguments.size() == target.parameters.size(),
                                "aggregate call argument vector size mismatch");
                        const bool spanParameters =
                            std::any_of(target.parameters.begin(), target.parameters.end(), [](const Type &type) {
                                return type.isSpan();
                            });
                        require((!spanParameters && operation.spanArguments.empty()) ||
                                    operation.spanArguments.size() == target.parameters.size(),
                                "span call argument vector size mismatch");
                        std::set<int> argumentStorage;
                        for (std::size_t arg = target.parameters.size(); arg > 0; --arg) {
                            const auto &type = target.parameters[arg - 1];
                            const int base = operation.objectArguments[arg - 1];
                            const int capability =
                                operation.spanArguments.empty() ? 0 : operation.spanArguments[arg - 1];
                            if (type.isSpan()) {
                                require(type == Type::ByteSpan && base == 0,
                                        "span argument cannot name object storage");
                                span(capability);
                                continue;
                            }
                            require(capability == 0, "non-span argument cannot name span storage");
                            if (scalarValueType(type, enumCases)) {
                                require(base == 0, "scalar argument cannot name object storage");
                                require(pop().type == type, "aggregate scalar argument type mismatch");
                                continue;
                            }
                            require(type.isClass() && classLayouts.contains(type.className),
                                    "invalid aggregate parameter type");
                            require(function.objectSlots.contains(base),
                                    "aggregate argument requires exact object slot");
                            require(argumentStorage.insert(base).second,
                                    "aggregate argument snapshots must be distinct");
                            const auto &object = function.objectSlots.at(base);
                            require(object.className == type.className, "aggregate argument nominal class mismatch");
                            require(!object.mutableValue, "aggregate argument snapshot must be readonly");
                            require(state.activeObjects.contains(base),
                                    "aggregate argument outside active object lifetime");
                            const auto &layout = classLayouts.at(type.className);
                            for (std::size_t field = 0; field < layout.size(); ++field)
                                require(state.initialized.contains(objectLeaf(base, field)),
                                        "aggregate argument object not fully initialized");
                            logicalComplete(base);
                        }
                        if (target.result.isClass()) {
                            const int base = operation.resultOffset;
                            require(function.objectSlots.contains(base), "aggregate result requires exact object slot");
                            require(!argumentStorage.contains(base), "aggregate result aliases argument snapshot");
                            const auto &object = function.objectSlots.at(base);
                            require(object.className == target.result.className,
                                    "aggregate result nominal class mismatch");
                            require(state.activeObjects.contains(base),
                                    "aggregate result outside active object lifetime");
                            require(!state.maybeConstructedObjects.contains(base),
                                    "aggregate result object already initialized");
                            const auto &layout = classLayouts.at(object.className);
                            for (std::size_t field = 0; field < layout.size(); ++field)
                                require(!state.maybeInitialized.contains(objectLeaf(base, field)),
                                        "aggregate result requires uninitialized object");
                            markObject(base);
                            state.current.reset();
                        } else {
                            require(scalarValueType(target.result, enumCases), "invalid aggregate result type");
                            require(operation.resultOffset == 0, "scalar result cannot name object storage");
                            state.current = Value{target.result, {}};
                        }
                    } else if constexpr (std::is_same_v<Op, ResourceCall>) {
                        require(functions.contains(operation.callee), "unknown resource call target");
                        const auto &target = *functions.at(operation.callee);
                        const bool constructor = target.receiver && target.receiver->constructor &&
                                                 owningClass(classFields, target.receiver->className);
                        require(resourceSignature(target, classFields) && (!target.receiver || constructor) &&
                                    !target.parameters.empty() && target.parameters.front() == Type::ByteRegion,
                                "resource call requires ordinary resource signature or owning constructor");
                        require(!constructor || target.receiver->publicAccess ||
                                    (function.receiver && !function.borrowedParameter &&
                                     function.receiver->className == target.receiver->className),
                                "private constructor requires lexical class authority");
                        require(constructor ? operation.receiverOffset > 0 : operation.receiverOffset == 0,
                                "resource call receiver offset does not match target");
                        const auto origin = region(operation.regionOffset);
                        require(operation.ownerArguments.size() == target.parameters.size(),
                                "resource call argument vector size mismatch");
                        std::map<int, bool> arguments; // transferred: true for owning object, false for bytes
                        std::set<int> argumentStorage; // also includes readonly constructor snapshots
                        for (std::size_t arg = target.parameters.size(); arg > 0; --arg) {
                            const auto &type = target.parameters[arg - 1];
                            const int base = operation.ownerArguments[arg - 1];
                            if (type.isOwnerStorage() || owningType(type)) {
                                require(!constructor || type.isOwnerStorage(),
                                        "constructor cannot take owning class arguments");
                                require(argumentStorage.insert(base).second,
                                        "resource call argument storage must be distinct");
                                arguments.emplace(base, owningType(type));
                                require(base != operation.receiverOffset,
                                        "resource constructor receiver aliases owning argument");
                                if (type.isOwnerStorage())
                                    require(ownerType(base) == type,
                                            "resource call owner argument nominal type mismatch");
                                const auto argumentOrigin = type.isOwnerStorage()
                                                                ? bytes(base, true).token->region
                                                                : ownedObject(base, type.className, true);
                                require(argumentOrigin == origin, "resource call owning argument has wrong region");
                            } else if (constructor && type.isClass() && !owningType(type)) {
                                require(argumentStorage.insert(base).second,
                                        "constructor argument snapshots must be distinct");
                                require(base != operation.receiverOffset,
                                        "constructor receiver aliases copied argument snapshot");
                                const auto &object = completeObject(base);
                                require(object.className == type.className,
                                        "constructor copied argument nominal class mismatch");
                                require(!object.mutableValue, "constructor copied argument snapshot must be readonly");
                            } else {
                                require(base == 0, "resource call non-owner argument cannot name storage");
                                if (arg == 1)
                                    require(type == Type::ByteRegion, "resource call first argument must be region");
                                else {
                                    require(scalarValueType(type, enumCases), "invalid resource call parameter type");
                                    require(pop().type == type, "resource call scalar argument type mismatch");
                                }
                            }
                        }
                        if (constructor) {
                            require(target.result == Type::I64 && operation.resultOffset == 0,
                                    "owning constructor requires scalar result and no result storage");
                            require(function.objectSlots.contains(operation.receiverOffset) &&
                                        function.objectSlots.at(operation.receiverOffset).className ==
                                            target.receiver->className,
                                    "owning constructor requires exact nominal receiver root");
                        } else if (target.result.isOwnerStorage() || owningType(target.result)) {
                            require(!arguments.contains(operation.resultOffset),
                                    "resource call owning result aliases argument");
                            if (target.result.isOwnerStorage()) {
                                require(ownerType(operation.resultOffset) == target.result,
                                        "resource call owner result nominal type mismatch");
                                byteTarget(operation.resultOffset);
                            }
                        } else if (target.result.isClass()) {
                            const int base = operation.resultOffset;
                            require(function.objectSlots.contains(base),
                                    "resource copied result requires exact object slot");
                            require(!argumentStorage.contains(base), "resource copied result aliases argument storage");
                            const auto &object = function.objectSlots.at(base);
                            require(object.className == target.result.className,
                                    "resource copied result nominal class mismatch");
                            require(state.activeObjects.contains(base),
                                    "resource copied result outside active object lifetime");
                            require(!state.maybeConstructedObjects.contains(base),
                                    "resource copied result object already initialized");
                            const auto &layout = classLayouts.at(object.className);
                            for (std::size_t field = 0; field < layout.size(); ++field)
                                require(!state.maybeInitialized.contains(objectLeaf(base, field)),
                                        "resource copied result requires uninitialized object");
                        } else {
                            require(scalarValueType(target.result, enumCases), "invalid resource call result type");
                            require(operation.resultOffset == 0,
                                    "scalar resource call result cannot name owning storage");
                        }
                        for (const auto &[base, object] : arguments) {
                            if (object)
                                consumeObject(base);
                            else
                                consumeBytes(base);
                        }
                        if (constructor) {
                            mintObject(operation.receiverOffset, target.receiver->className, origin);
                            state.current = Value{target.result, {}};
                        } else if (target.result.isOwnerStorage()) {
                            mintBytes(operation.resultOffset, origin);
                            state.current.reset();
                        } else if (owningType(target.result)) {
                            mintObject(operation.resultOffset, target.result.className, origin);
                            state.current.reset();
                        } else if (target.result.isClass()) {
                            // A complete pointer-free copy carries no owner token or region provenance.
                            markObject(operation.resultOffset);
                            state.current.reset();
                        } else
                            state.current = Value{target.result, {}};
                    } else if constexpr (std::is_same_v<Op, BeginBytes>) {
                        require(function.byteSlots.contains(operation.offset),
                                "owned byte lifetime requires exact typed spill");
                        require(!byteParameterSlots.contains(operation.offset),
                                "owned byte parameter lifetime cannot restart");
                        require(!state.activeBytes.contains(operation.offset), "owned byte lifetime already active");
                        state.activeBytes.emplace(operation.offset, ByteBinding{index, ByteDisposition::Pristine, {}});
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
                        require(function.arraySlots.contains(operation.offset),
                                "array lifetime requires exact byte array origin");
                        if constexpr (std::is_same_v<Op, BeginArray>) {
                            require(!state.activeArrays.contains(operation.offset), "array lifetime already active");
                            state.activeArrays.emplace(operation.offset, index);
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
                        for (int element = 0; element < function.arraySlots.at(operation.offset); ++element) {
                            state.initialized.erase(operation.offset - element);
                            state.maybeInitialized.erase(operation.offset - element);
                        }
                    } else if constexpr (std::is_same_v<Op, BorrowSpan>) {
                        require(function.arraySlots.contains(operation.arrayOffset),
                                "span borrow requires exact local byte array origin");
                        require(state.activeArrays.contains(operation.arrayOffset),
                                "span borrow requires active byte array origin");
                        array(operation.arrayOffset, function.arraySlots.at(operation.arrayOffset), Type::U8);
                        spanTarget(operation.resultOffset);
                        state.activeSpans.emplace(operation.resultOffset,
                                                  SpanCapability{false,
                                                                 operation.arrayOffset,
                                                                 state.activeArrays.at(operation.arrayOffset),
                                                                 0,
                                                                 0,
                                                                 index});
                    } else if constexpr (std::is_same_v<Op, BorrowReceiverArraySpan>) {
                        borrowArrayField(0, operation.fieldIndex, operation.resultOffset);
                    } else if constexpr (std::is_same_v<Op, BorrowLiteralSpan>) {
                        require(operation.bytes.size() <= maxByteStringBytes, "literal span exceeds byte-string bound");
                        spanTarget(operation.resultOffset);
                        state.activeSpans.emplace(
                            operation.resultOffset,
                            SpanCapability{false, operation.resultOffset, index, 0, 0, index, {}, -1, true});
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
                        capability.site = index;
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
                        require(function.objectSlots.contains(operation.offset),
                                "lifetime operation requires exact object slot");
                        if constexpr (std::is_same_v<Op, BeginObject>) {
                            require(!objectParameterSlots.contains(operation.offset),
                                    "object parameter lifetime cannot restart");
                            require(!state.activeObjects.contains(operation.offset), "object lifetime already active");
                            state.activeObjects.emplace(operation.offset, index);
                            const auto &name = function.objectSlots.at(operation.offset).className;
                            if (owningClass(classFields, name))
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
                        const auto &object = function.objectSlots.at(operation.offset);
                        const auto &layout = classLayouts.at(object.className);
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
                        require(function.objectSlots.contains(operation.offset),
                                "empty initialization requires exact object slot");
                        const auto &name = function.objectSlots.at(operation.offset).className;
                        require(classLayouts.at(name).empty() && classFields.at(name).empty() &&
                                    !owningClass(classFields, name) && !classArrayCarriers.contains(name),
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
                        const auto &shape = receiverShape(operation.fieldIndex);
                        require(shape.elementType.isOwnerStorage() && !shape.array,
                                "resource field initialization requires direct owner field");
                        require(ownerType(operation.sourceOffset) == shape.elementType,
                                "resource field initialization owner nominal type mismatch");
                        auto &target = state.ownedObjects.at(0).fields.at(operation.fieldIndex);
                        require(target.disposition == ByteDisposition::Pristine && !target.token,
                                "constructor resource field initialized more than once");
                        const auto token = bytes(operation.sourceOffset, true).token;
                        require(regionParameterSlot && token->region == region(*regionParameterSlot),
                                "constructor resource field has wrong region");
                        consumeBytes(operation.sourceOffset);
                        target.disposition = ByteDisposition::Live;
                        target.token = token;
                        state.current.reset();
                    } else if constexpr (std::is_same_v<Op, CopyObject>) {
                        require(operation.sourceOffset != operation.resultOffset, "copy source aliases result");
                        const auto &source = completeObject(operation.sourceOffset);
                        require(!owningClass(classFields, source.className),
                                "owning class cannot be implicitly copied");
                        copyTarget(operation.resultOffset, source.className);
                        state.current.reset();
                    } else if constexpr (std::is_same_v<Op, ObjectFieldCopy>) {
                        const ClassField *field = nullptr;
                        if (operation.sourceOffset == 0) {
                            field = &receiverShape(operation.fieldIndex);
                            require(!function.receiver->constructor,
                                    "constructor cannot project receiver during initialization");
                            require(state.receiverClassesInitialized.contains(operation.fieldIndex),
                                    "receiver nested class field not initialized");
                        } else {
                            require(operation.sourceOffset != operation.resultOffset,
                                    "projection source aliases result");
                            const auto &source = completeObject(operation.sourceOffset);
                            require(classFields.contains(source.className) && operation.fieldIndex >= 0 &&
                                        static_cast<std::size_t>(operation.fieldIndex) <
                                            classFields.at(source.className).size(),
                                    "projection logical field index out of range");
                            field = &classFields.at(source.className)[operation.fieldIndex];
                        }
                        require(!field->array && field->elementType.isClass(), "projection requires class field");
                        require(!owningClass(classFields, field->elementType.className),
                                "owning class field cannot be copied");
                        copyTarget(operation.resultOffset, field->elementType.className);
                        state.current.reset();
                    } else if constexpr (std::is_same_v<Op, AssignObjectField>) {
                        require(operation.objectOffset != operation.sourceOffset,
                                "class field assignment source aliases root");
                        const auto &field = completeClassField(operation.objectOffset, operation.fieldIndex, true);
                        const auto &source = completeObject(operation.sourceOffset);
                        require(!owningClass(classFields, field.elementType.className),
                                "owning class field cannot be copied");
                        require(source.className == field.elementType.className,
                                "class field assignment nominal class mismatch");
                        // Both values were already complete; replacement cannot mint
                        // initialization evidence or create a separately live subobject.
                        state.current.reset();
                    } else if constexpr (std::is_same_v<Op, InitializeObjectField>) {
                        require(operation.objectOffset == 0,
                                "class field initialization requires bound constructor receiver");
                        const auto &field = receiverShape(operation.fieldIndex);
                        require(function.receiver->constructor && function.receiver->mutableValue,
                                "class field initialization requires constructor receiver");
                        require(!field.array && field.elementType.isClass(),
                                "class field initialization requires class field");
                        const auto &source = completeObject(operation.sourceOffset);
                        require(!owningClass(classFields, field.elementType.className),
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
                    } else if constexpr (std::is_same_v<Op, InitializeClassArray>) {
                        require(operation.objectOffset >= 0, "invalid class array initialization root");
                        const ClassField *field = nullptr;
                        if (operation.objectOffset == 0) {
                            field = &receiverShape(operation.fieldIndex);
                            require(function.receiver->constructor && function.receiver->mutableValue,
                                    "class array initialization requires constructor receiver");
                        } else {
                            require(function.objectSlots.contains(operation.objectOffset),
                                    "class array initialization requires exact object slot");
                            const auto &name = function.objectSlots.at(operation.objectOffset).className;
                            require(classArrayCarriers.contains(name) && operation.fieldIndex == 0,
                                    "local class array initialization requires declared carrier field");
                            field = &classFields.at(name).front();
                        }
                        require(field->array && field->elementType.isClass(),
                                "class array initialization requires class array field");
                        require(operation.sources.size() == static_cast<std::size_t>(field->elementCount),
                                "class array initializer element count mismatch");
                        for (int sourceOffset : operation.sources) {
                            require(sourceOffset != operation.objectOffset,
                                    "class array initialization source aliases root");
                            const auto &source = completeObject(sourceOffset);
                            require(source.className == field->elementType.className,
                                    "class array initializer nominal class mismatch");
                        }
                        if (operation.objectOffset == 0) {
                            require(!state.receiverClassesMaybeInitialized.contains(operation.fieldIndex),
                                    "constructor class array initialized more than once");
                            for (int leaf = 0; leaf < field->length; ++leaf) {
                                const int ordinal = field->firstLeaf + leaf;
                                require(!state.receiverMaybeInitialized.contains(ordinal),
                                        "constructor class array leaves already initialized");
                                state.receiverInitialized.insert(ordinal);
                                state.receiverMaybeInitialized.insert(ordinal);
                            }
                            state.receiverClassesInitialized.insert(operation.fieldIndex);
                            state.receiverClassesMaybeInitialized.insert(operation.fieldIndex);
                        } else {
                            copyTarget(operation.objectOffset,
                                       function.objectSlots.at(operation.objectOffset).className);
                        }
                        state.current.reset();
                    } else if constexpr (std::is_same_v<Op, ClassArrayBoundsGuard>) {
                        const auto &field = completeClassArray(operation.objectOffset, operation.fieldIndex, false);
                        current(Type::I64);
                        state.current =
                            Value{Type::I64, classArrayEvidence(operation.objectOffset, operation.fieldIndex, field)};
                    } else if constexpr (std::is_same_v<Op, ClassArrayCopy>) {
                        const auto &field = completeClassArray(operation.objectOffset, operation.fieldIndex, false);
                        checkedClassArray(operation.objectOffset, operation.fieldIndex, field);
                        require(operation.objectOffset != operation.resultOffset,
                                "class array projection source aliases result");
                        copyTarget(operation.resultOffset, field.elementType.className);
                        state.current.reset();
                    } else if constexpr (std::is_same_v<Op, ClassArrayAssign>) {
                        const auto &field = completeClassArray(operation.objectOffset, operation.fieldIndex, true);
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
                        const auto &field = receiverField(operation.fieldIndex, operation.type);
                        require(!function.receiver->constructor,
                                "constructor cannot read receiver during initialization");
                        require(state.receiverInitialized.contains(field.firstLeaf), "receiver field not initialized");
                        state.current = Value{operation.type, {}};
                    } else if constexpr (std::is_same_v<Op, ReceiverStore>) {
                        const auto &field = receiverField(operation.fieldIndex, operation.type);
                        current(operation.type);
                        require(function.receiver->mutableValue, "write through const receiver");
                        if (function.receiver->constructor)
                            require(!state.receiverMaybeInitialized.contains(field.firstLeaf),
                                    "constructor field initialized more than once");
                        state.receiverInitialized.insert(field.firstLeaf);
                        state.receiverMaybeInitialized.insert(field.firstLeaf);
                    } else if constexpr (std::is_same_v<Op, ReceiverArrayZero>) {
                        const auto &field = receiverArray(operation.fieldIndex, false);
                        require(function.receiver->constructor && function.receiver->mutableValue,
                                "receiver array zero requires constructor receiver");
                        for (int element = 0; element < field.length; ++element) {
                            const int leaf = field.firstLeaf + element;
                            require(!state.receiverMaybeInitialized.contains(leaf),
                                    "constructor array initialized more than once");
                            state.receiverInitialized.insert(leaf);
                            state.receiverMaybeInitialized.insert(leaf);
                        }
                    } else if constexpr (std::is_same_v<Op, ReceiverBoundsGuard>) {
                        const auto &field = receiverArray(operation.fieldIndex, true);
                        current(Type::I64);
                        state.current = Value{Type::I64, receiverEvidence(operation.fieldIndex, field)};
                    } else if constexpr (std::is_same_v<Op, ReceiverIndexLoad>) {
                        const auto &field = receiverArray(operation.fieldIndex, true);
                        receiverGuard(current(Type::I64), operation.fieldIndex, field);
                        state.current = Value{field.elementType, {}};
                    } else if constexpr (std::is_same_v<Op, ReceiverIndexStore>) {
                        const auto &field = receiverArray(operation.fieldIndex, true);
                        require(function.receiver->mutableValue, "write through const receiver");
                        current(field.elementType);
                        receiverGuard(pop(), operation.fieldIndex, field);
                        ownerWritable(0, operation.fieldIndex);
                    } else if constexpr (std::is_same_v<Op, AcquireObjectLoan>) {
                        require(operation.loanId > 0 && !state.objectLoans.contains(operation.loanId),
                                "invalid or duplicate object loan identity");
                        require(operation.root >= 0 ||
                                    (operation.root == -1 && function.secondBorrowedParameter.has_value()),
                                "invalid borrowed object root");
                        loanAccess(operation.root, operation.mutableValue);
                        std::string name;
                        if (operation.root <= 0) {
                            require(function.borrowedParameter && function.receiver,
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
                    } else if constexpr (std::is_same_v<Op, MethodCall> || std::is_same_v<Op, BorrowedCall>) {
                        require(functions.contains(operation.callee), "unknown method call target");
                        const auto &target = *functions.at(operation.callee);
                        require(target.receiver.has_value(), "method call requires receiver target");
                        if constexpr (std::is_same_v<Op, BorrowedCall>) {
                            require(target.borrowedParameter, "borrowed call requires borrowed formal target");
                            require(target.secondBorrowedParameter
                                        ? operation.secondLoanId > 0 && operation.secondLoanId != operation.loanId &&
                                              operation.secondReceiverOffset != operation.receiverOffset
                                        : operation.secondReceiverOffset == 0 && operation.secondLoanId == -1,
                                    "borrowed call second root tuple does not match target");
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
                                liveOwningRoot(root);
                                loanAccess(root, formal.mutableValue);
                                loan.called = true;
                            };
                            useLoan(operation.loanId, operation.receiverOffset, *target.receiver);
                            if (target.secondBorrowedParameter)
                                useLoan(operation.secondLoanId,
                                        operation.secondReceiverOffset,
                                        *target.secondBorrowedParameter);
                        } else {
                            require(!target.borrowedParameter, "method call cannot target borrowed free function");
                            loanAccess(operation.receiverOffset, target.receiver->mutableValue);
                            require(target.receiver->publicAccess ||
                                        (function.receiver && !function.borrowedParameter &&
                                         function.receiver->className == target.receiver->className),
                                    "private method requires lexical class authority");
                        }
                        require(!resourceSignature(target, classFields),
                                "method call cannot target resource signature or owning constructor");
                        require((scalarValueType(target.result, enumCases) ||
                                 (!target.receiver->constructor && target.result.isClass()) ||
                                 (target.result == Type::ByteSpan && target.receiverSpanField &&
                                  !target.receiver->mutableValue && !target.receiver->constructor)) &&
                                    std::all_of(target.parameters.begin(),
                                                target.parameters.end(),
                                                [&](const Type &type) {
                                                    return scalarValueType(type, enumCases) || type.isClass() ||
                                                           (!target.receiver->constructor && type == Type::ByteSpan);
                                                }),
                                "receiver signature requires scalar, enum or class values");
                        const auto &receiver = *target.receiver;
                        const bool aggregate =
                            std::any_of(target.parameters.begin(), target.parameters.end(), [](const Type &type) {
                                return type.isClass() || type.isSpan();
                            });
                        require(aggregate ? operation.objectArguments.size() == target.parameters.size()
                                          : operation.objectArguments.empty(),
                                (receiver.constructor ? "constructor object argument vector size mismatch"
                                                      : "receiver object argument vector size mismatch"));
                        const bool spanParameters =
                            std::any_of(target.parameters.begin(), target.parameters.end(), [](const Type &type) {
                                return type.isSpan();
                            });
                        require((!spanParameters && operation.spanArguments.empty()) ||
                                    operation.spanArguments.size() == target.parameters.size(),
                                "method span argument vector size mismatch");
                        std::set<int> argumentStorage;
                        for (std::size_t arg = target.parameters.size(); arg > 0; --arg) {
                            const auto &type = target.parameters[arg - 1];
                            const int capability =
                                operation.spanArguments.empty() ? 0 : operation.spanArguments[arg - 1];
                            if (type.isSpan()) {
                                require(operation.objectArguments[arg - 1] == 0,
                                        "span method argument cannot name object storage");
                                span(capability);
                                continue;
                            }
                            require(capability == 0, "non-span method argument cannot name span storage");
                            if (scalarValueType(type, enumCases)) {
                                require(!aggregate || operation.objectArguments[arg - 1] == 0,
                                        (receiver.constructor ? "scalar constructor argument cannot name object storage"
                                                              : "scalar receiver argument cannot name object storage"));
                                require(pop().type == type, "method argument type mismatch");
                            } else {
                                const int base = operation.objectArguments[arg - 1];
                                require(base != operation.receiverOffset,
                                        (receiver.constructor ? "constructor receiver aliases argument snapshot"
                                                              : "receiver aliases argument snapshot"));
                                require(argumentStorage.insert(base).second,
                                        (receiver.constructor ? "constructor argument snapshots must be distinct"
                                                              : "receiver argument snapshots must be distinct"));
                                const auto &object = completeObject(base);
                                require(object.className == type.className,
                                        (receiver.constructor ? "constructor argument nominal class mismatch"
                                                              : "receiver argument nominal class mismatch"));
                                require(!object.mutableValue,
                                        (receiver.constructor ? "constructor argument snapshot must be readonly"
                                                              : "receiver argument snapshot must be readonly"));
                            }
                        }
                        require(operation.receiverOffset >= 0 ||
                                    (operation.receiverOffset == -1 && function.secondBorrowedParameter.has_value()),
                                "invalid method receiver offset");
                        require(operation.receiverFieldIndex >= -1, "invalid method receiver field index");
                        if (receiver.mutableValue)
                            ownerWritable(operation.receiverOffset);
                        if (operation.receiverFieldIndex >= 0) {
                            require(!receiver.constructor, "nested receiver cannot call constructor");
                            const auto &field = completeClassField(
                                operation.receiverOffset, operation.receiverFieldIndex, receiver.mutableValue);
                            require(field.elementType.className == receiver.className,
                                    "nested method receiver nominal class mismatch");
                        } else if (operation.receiverOffset <= 0) {
                            require(function.receiver.has_value(), "forwarding without bound receiver");
                            const auto &formal = boundRoot(operation.receiverOffset);
                            require(!formal.constructor && !receiver.constructor,
                                    "constructor cannot forward receiver during initialization");
                            require(formal.className == receiver.className,
                                    "forwarded receiver nominal class mismatch");
                            require(!receiver.mutableValue || formal.mutableValue,
                                    "const receiver cannot forward mutable capability");
                        } else {
                            require(function.objectSlots.contains(operation.receiverOffset),
                                    "method receiver is not an object slot");
                            const auto &object = function.objectSlots.at(operation.receiverOffset);
                            require(state.activeObjects.contains(operation.receiverOffset),
                                    "method receiver outside active object lifetime");
                            require(object.className == receiver.className, "method receiver nominal class mismatch");
                            const auto &layout = classLayouts.at(object.className);
                            if (receiver.constructor) {
                                require(!state.maybeConstructedObjects.contains(operation.receiverOffset),
                                        "object constructor called more than once");
                                for (std::size_t field = 0; field < layout.size(); ++field)
                                    require(
                                        !state.maybeInitialized.contains(objectLeaf(operation.receiverOffset, field)),
                                        "constructor requires uninitialized object");
                                markObject(operation.receiverOffset);
                            } else {
                                require(!receiver.mutableValue || object.mutableValue,
                                        "const object cannot supply mutable receiver");
                                for (std::size_t field = 0; field < layout.size(); ++field)
                                    require(state.initialized.contains(objectLeaf(operation.receiverOffset, field)),
                                            "method receiver object not fully initialized");
                                logicalComplete(operation.receiverOffset);
                            }
                        }
                        if (target.result == Type::ByteSpan) {
                            require(!function.secondBorrowedParameter || operation.receiverOffset > 0,
                                    "paired borrowed roots cannot produce span results");
                            require(operation.receiverFieldIndex == -1, "span result requires direct receiver root");
                            require(target.receiverSpanField.has_value(), "span result lacks receiver field summary");
                            const auto &field = classFields.at(receiver.className).at(*target.receiverSpanField);
                            if (field.array)
                                borrowArrayField(
                                    operation.receiverOffset, *target.receiverSpanField, operation.resultOffset, true);
                            else
                                borrowOwned(
                                    operation.receiverOffset, *target.receiverSpanField, operation.resultOffset, true);
                            state.current.reset();
                        } else if (target.result.isClass()) {
                            const int base = operation.resultOffset;
                            require(base != operation.receiverOffset, "method result aliases receiver");
                            require(!argumentStorage.contains(base), "method result aliases argument snapshot");
                            require(function.objectSlots.contains(base), "method result requires exact object slot");
                            const auto &object = function.objectSlots.at(base);
                            require(object.className == target.result.className,
                                    "method result nominal class mismatch");
                            require(state.activeObjects.contains(base), "method result outside active object lifetime");
                            require(!state.maybeConstructedObjects.contains(base),
                                    "method result object already initialized");
                            const auto &layout = classLayouts.at(object.className);
                            for (std::size_t field = 0; field < layout.size(); ++field)
                                require(!state.maybeInitialized.contains(objectLeaf(base, field)),
                                        "method result requires uninitialized object");
                            markObject(base);
                            state.current.reset();
                        } else {
                            require(operation.resultOffset == 0, "scalar method result cannot name object storage");
                            state.current = Value{target.result, {}};
                        }
                    } else if constexpr (std::is_same_v<Op, MetadataQuery>) {
                        require(operation.query == Query::Size || operation.query == Query::PublicFieldCount,
                                "unknown metadata query");
                        require(operation.moduleScope == function.moduleScope,
                                "metadata query changes defining-module scope");
                        current(Type::I64);
                        state.current = Value{Type::I64, {}};
                    } else if constexpr (std::is_same_v<Op, Label>) {
                        // Nonempty expression stacks retain exact type and guard
                        // equality at every join, including loop backedges.
                    } else if constexpr (std::is_same_v<Op, Jump>) {
                        enqueue(labels.at(operation.target), state);
                        fallsThrough = false;
                    } else if constexpr (std::is_same_v<Op, BranchFalse>) {
                        current(Type::Bool);
                        enqueue(labels.at(operation.target), state);
                    } else if constexpr (std::is_same_v<Op, Return>) {
                        require(scalarValueType(function.result, enumCases),
                                "scalar return cannot return class value or resource value");
                        current(function.result);
                        require(state.stack.empty(), "unbalanced stack at return");
                        require(state.activeBytes.empty(), "return with active owned byte lifetime");
                        closedOwnedObjects();
                        require(state.activeSpans.empty() && state.activeArrays.empty(),
                                "return with active span or byte array lifetime");
                        if (function.receiver && function.receiver->constructor) {
                            require(state.receiverInitialized.size() == receiverLayout->size(),
                                    "constructor returns before all fields initialized");
                            for (std::size_t field = 0; field < receiverFields->size(); ++field)
                                if ((*receiverFields)[field].elementType.isClass())
                                    require(state.receiverClassesInitialized.contains(static_cast<int>(field)),
                                            "constructor returns before all class fields initialized");
                        }
                        if (owningConstructor) {
                            require(regionParameterSlot.has_value(), "owning constructor lacks region");
                            for (const auto &[unused, field] : state.ownedObjects.at(0).fields) {
                                (void)unused;
                                require(field.disposition == ByteDisposition::Live && field.token &&
                                            field.token->region == region(*regionParameterSlot),
                                        "constructor returns before all resource fields initialized");
                            }
                        }
                        fallsThrough = false;
                    } else if constexpr (std::is_same_v<Op, ReturnSpan>) {
                        require(function.result == Type::ByteSpan && function.receiverSpanField && function.receiver &&
                                    !function.receiver->constructor && !function.receiver->mutableValue,
                                "span return requires const owning receiver field summary");
                        const auto &capability = span(operation.offset);
                        const bool fixed = receiverShape(*function.receiverSpanField).array;
                        const auto token = fixed ? std::optional<ByteToken>{}
                                                 : accessBytes(0, *function.receiverSpanField, false).token;
                        auto matchesReceiver = [&](const SpanCapability &view) {
                            return view.origin == 0 && !view.parameterOrigin && !view.literalOrigin &&
                                   (fixed ? view.arrayField == *function.receiverSpanField && !view.ownedToken
                                          : view.arrayField == -1 && view.ownedField == *function.receiverSpanField &&
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
                        fallsThrough = false;
                    } else if constexpr (std::is_same_v<Op, ReturnObject>) {
                        require(function.result.isClass() && !owningType(function.result),
                                "object return requires class result; owning classes require an explicit move return");
                        require(function.objectSlots.contains(operation.offset),
                                "object return requires exact object slot");
                        const auto &object = function.objectSlots.at(operation.offset);
                        require(object.className == function.result.className, "object return nominal class mismatch");
                        require(state.activeObjects.contains(operation.offset),
                                "object return outside active lifetime");
                        const auto &layout = classLayouts.at(object.className);
                        for (std::size_t field = 0; field < layout.size(); ++field)
                            require(state.initialized.contains(objectLeaf(operation.offset, field)),
                                    "returned object not fully initialized");
                        logicalComplete(operation.offset);
                        require(state.stack.empty(), "unbalanced stack at object return");
                        require(state.activeBytes.empty(), "return with active owned byte lifetime");
                        closedOwnedObjects();
                        require(state.activeSpans.empty() && state.activeArrays.empty(),
                                "return with active span or byte array lifetime");
                        fallsThrough = false;
                    } else if constexpr (std::is_same_v<Op, ReturnOwnedObject>) {
                        require(!function.receiver && owningType(function.result),
                                "owning object return requires ordinary owning class result");
                        require(regionParameterSlot.has_value(), "owning object return requires bound region");
                        require(ownedObject(operation.offset, function.result.className, true) ==
                                    region(*regionParameterSlot),
                                "owning object return has wrong region");
                        state.ownedObjects.erase(operation.offset);
                        state.activeObjects.erase(operation.offset);
                        closedOwnedObjects();
                        require(state.activeBytes.empty(), "return with active owned byte lifetime");
                        require(state.activeSpans.empty() && state.activeArrays.empty(),
                                "return with active span or byte array lifetime");
                        require(state.stack.empty(), "unbalanced stack at owning object return");
                        fallsThrough = false;
                    } else if constexpr (std::is_same_v<Op, ReturnBytes>) {
                        require(function.result.isOwnerStorage() && ownerType(operation.offset) == function.result,
                                "owner return nominal type mismatch");
                        require(regionParameterSlot.has_value(), "owned byte return requires bound region parameter");
                        require(bytes(operation.offset, true).token->region == region(*regionParameterSlot),
                                "owned byte return has wrong region");
                        state.activeBytes.erase(operation.offset);
                        require(state.activeBytes.empty(), "return with active owned byte lifetime");
                        closedOwnedObjects();
                        require(state.activeSpans.empty() && state.activeArrays.empty(),
                                "return with active span or byte array lifetime");
                        require(state.stack.empty(), "unbalanced stack at owned byte return");
                        fallsThrough = false;
                    } else if constexpr (std::is_same_v<Op, BindServiceParameter>) {
                        require(serviceFunction && index < serviceParameterCount &&
                                    operation.index == static_cast<int>(index) &&
                                    operation.kind == service::kind(function.parameters[index]) &&
                                    serviceParameterSlots.at(operation.index) == operation.offset &&
                                    function.serviceSlots.contains(operation.offset) &&
                                    !state.activeServices.contains(operation.offset),
                                "service binding requires exact authorized leading parameter");
                        state.activeServices.emplace(operation.offset, ServiceIdentity{index, operation.kind});
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
                                        enumCases.contains(std::string(service::displayPutResultName)),
                                    "pixel requires closed enum result and no object storage");
                            state.current = Value{service::displayPutResultType(), {}};
                        } else if (operation.operation == service::Operation::Put) {
                            current(Type::U8);
                            require(operation.resultOffset == 0 &&
                                        enumCases.contains(std::string(service::putResultName)),
                                    "put requires closed enum result and no object storage");
                            state.current = Value{service::putResultType(), {}};
                        } else if (operation.operation == service::Operation::IommuAcknowledge) {
                            require(operation.resultOffset == 0 &&
                                        enumCases.contains(std::string(service::eventAckResultName)),
                                    "acknowledge requires closed enum result and no object storage");
                            state.current = Value{service::eventAckResultType(), {}};
                        } else if (operation.operation == service::Operation::Next ||
                                   operation.operation == service::Operation::IommuPoll) {
                            const bool event = operation.operation == service::Operation::IommuPoll;
                            const auto reportName = event ? service::eventSampleName : service::sampleName;
                            const int base = operation.resultOffset;
                            require(function.objectSlots.contains(base) &&
                                        function.objectSlots.at(base).className == reportName &&
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
                    } else if constexpr (std::is_same_v<Op, ServiceCall>) {
                        require(functions.contains(operation.callee), "unknown service helper target");
                        const auto &target = *functions.at(operation.callee);
                        require(serviceSignature(target) && !target.receiver,
                                "service helper requires service target and acquired loans");
                        std::vector<ServiceArgument> arguments{{operation.loanId, operation.kind}};
                        arguments.insert(
                            arguments.end(), operation.additionalServices.begin(), operation.additionalServices.end());
                        const auto count = static_cast<std::size_t>(
                            std::count_if(target.parameters.begin(), target.parameters.end(), [](const Type &type) {
                                return type.isService();
                            }));
                        require(arguments.size() == count && count <= 2 &&
                                    operation.spanArguments.size() == target.parameters.size(),
                                "service helper argument vector mismatch");
                        std::set<int> usedLoans, usedRoots;
                        for (std::size_t position = 0; position < count; ++position) {
                            const auto &argument = arguments[position];
                            require(state.serviceLoans.contains(argument.loanId) &&
                                        usedLoans.insert(argument.loanId).second &&
                                        operation.spanArguments[position] == 0 &&
                                        target.parameters[position].isService(),
                                    "service helper requires distinct acquired loans in leading positions");
                            auto &loan = state.serviceLoans.at(argument.loanId);
                            require(!loan.called && usedRoots.insert(loan.offset).second &&
                                        state.activeServices.contains(loan.offset) &&
                                        state.activeServices.at(loan.offset) == loan.identity &&
                                        loan.identity.kind == argument.kind &&
                                        argument.kind == service::kind(target.parameters[position]),
                                    "service helper requires an unused loan with exact provenance");
                        }
                        for (std::size_t reverse = target.parameters.size(); reverse > count; --reverse) {
                            const auto position = reverse - 1;
                            const auto &type = target.parameters[position];
                            const int base = operation.spanArguments[position];
                            if (type.isSpan()) {
                                require(state.activeSpans.contains(base), "service span argument is not active");
                            } else {
                                require(base == 0 && scalarValueType(type, enumCases) && pop().type == type,
                                        "service scalar argument mismatch");
                            }
                        }
                        if (target.result.isClass()) {
                            const int base = operation.resultOffset;
                            const bool event = target.result == service::eventSampleType();
                            require(function.objectSlots.contains(base) &&
                                        (event || target.result == service::sampleType()) &&
                                        function.objectSlots.at(base).className == target.result.className &&
                                        state.activeObjects.contains(base) &&
                                        !state.maybeConstructedObjects.contains(base),
                                    "service helper requires pristine copied sample destination");
                            for (std::size_t field = 0; field < (event ? 4u : 3u); ++field)
                                require(!state.maybeInitialized.contains(objectLeaf(base, field)),
                                        "service helper destination already initialized");
                            markObject(base);
                            state.current.reset();
                        } else {
                            require(operation.resultOffset == 0 && scalarValueType(target.result, enumCases),
                                    "service scalar result mismatch");
                            state.current = Value{target.result, {}};
                        }
                        for (const auto &argument : arguments)
                            state.serviceLoans.at(argument.loanId).called = true;
                    } else if constexpr (std::is_same_v<Op, BindRegionParameter>) {
                        require(resourceFunction && operation.index == 0 &&
                                    function.parameters.front() == Type::ByteRegion,
                                "region parameter type or index mismatch");
                        require(function.regionSlots.contains(operation.offset),
                                "region parameter requires exact typed spill");
                        require(state.activeRegions.empty(), "region parameter authority already active");
                        state.activeRegions.emplace(operation.offset, RegionIdentity{operation.offset, index});
                    } else if constexpr (std::is_same_v<Op, BindBytesParameter>) {
                        require(operation.index > 0 &&
                                    static_cast<std::size_t>(operation.index) < function.parameters.size(),
                                "invalid owned byte parameter index");
                        require(function.parameters[operation.index].isOwnerStorage() &&
                                    ownerType(operation.offset) == function.parameters[operation.index],
                                "owned byte parameter type mismatch");
                        require(regionParameterSlot.has_value(), "owned byte parameter requires bound region");
                        require(function.byteSlots.contains(operation.offset),
                                "owned byte parameter requires exact typed spill");
                        require(function.byteSlots.at(operation.offset), "owned byte parameter must be mutable");
                        require(!state.activeBytes.contains(operation.offset),
                                "owned byte parameter lifetime already active");
                        state.activeBytes.emplace(operation.offset, ByteBinding{index, ByteDisposition::Pristine, {}});
                        mintBytes(operation.offset, region(*regionParameterSlot));
                    } else if constexpr (std::is_same_v<Op, BindSpanParameter>) {
                        require(operation.index >= 0 &&
                                    static_cast<std::size_t>(operation.index) < function.parameters.size(),
                                "invalid span parameter index");
                        require(function.parameters[operation.index] == Type::ByteSpan &&
                                    (!function.receiver || !function.receiver->constructor),
                                "span parameter type mismatch");
                        require(function.spanSlots.contains(operation.offset),
                                "span parameter requires exact typed spill");
                        require(!state.activeSpans.contains(operation.offset),
                                "span parameter lifetime already active");
                        state.activeSpans.emplace(operation.offset,
                                                  SpanCapability{true, operation.index, index, 0, 0, index});
                    } else if constexpr (std::is_same_v<Op, BindOwnedObjectParameter>) {
                        require(!function.receiver && operation.index > 0 &&
                                    static_cast<std::size_t>(operation.index) < function.parameters.size(),
                                "invalid owning class parameter index");
                        require(function.parameters[operation.index] == Type(operation.className) &&
                                    owningClass(classFields, operation.className),
                                "owning class parameter type mismatch");
                        require(regionParameterSlot.has_value(), "owning class parameter requires bound region");
                        require(function.objectSlots.contains(operation.offset) &&
                                    function.objectSlots.at(operation.offset).className == operation.className,
                                "owning class parameter requires exact nominal object slot");
                        require(function.objectSlots.at(operation.offset).mutableValue,
                                "owning class parameter must be mutable");
                        require(!state.activeObjects.contains(operation.offset),
                                "owning class parameter lifetime already active");
                        state.activeObjects.emplace(operation.offset, index);
                        beginOwnedObject(operation.offset, operation.className);
                        mintObject(operation.offset, operation.className, region(*regionParameterSlot));
                    } else if constexpr (std::is_same_v<Op, BindObjectParameter>) {
                        require(operation.index >= 0 &&
                                    static_cast<std::size_t>(operation.index) < function.parameters.size(),
                                "invalid object parameter index");
                        require(!owningClass(classFields, operation.className),
                                "copied parameter cannot bind owning class");
                        require(function.parameters[operation.index] == Type(operation.className),
                                "object parameter type mismatch");
                        require(function.objectSlots.contains(operation.offset),
                                "object parameter requires exact object slot");
                        const auto &object = function.objectSlots.at(operation.offset);
                        require(object.className == operation.className, "object parameter nominal class mismatch");
                        require(!object.mutableValue, "object parameter must be readonly");
                        require(!state.activeObjects.contains(operation.offset),
                                "object parameter lifetime already active");
                        state.activeObjects.emplace(operation.offset, index);
                        markObject(operation.offset);
                    } else if constexpr (std::is_same_v<Op, BindParameter>) {
                        require(operation.index >= 0 &&
                                    static_cast<std::size_t>(operation.index) < function.parameters.size(),
                                "invalid parameter index");
                        require(function.parameters[operation.index] == operation.type, "parameter type mismatch");
                        require(!objectFields.contains(operation.offset), "parameter cannot bind object field storage");
                        require(!arrayBases.contains(operation.offset),
                                "parameter cannot bind byte array origin storage");
                        store(operation.offset, operation.type);
                    } else {
                        static_assert(!std::is_same_v<Op, Op>, "unhandled typed IR verifier operation");
                    }
                },
                function.code[index]);
            stackAfter[index] = state.stack.size();
            if (!fallsThrough)
                break;
            ++index;
            require(index < function.code.size(), "reachable fallthrough without return");
            if (blockEntry[index]) {
                enqueue(index, state);
                break;
            }
        }
    }
    std::vector<Instruction> reachable;
    std::size_t emittedDepth = 0;
    for (std::size_t index = 0; index < function.code.size(); ++index) {
        if (reached[index]) {
            // The backend counts push/pop effects in emitted order. Certify
            // that order separately from CFG joins; arbitrary non-linear stack
            // layouts are unsupported. Never reset this counter at a label.
            require(stackBefore[index] == emittedDepth, "operand stack depth differs from linear emission order");
            emittedDepth = stackAfter[index];
            reachable.push_back(std::move(function.code[index]));
        } else
            require(std::holds_alternative<Label>(function.code[index]) ||
                        std::holds_alternative<Jump>(function.code[index]),
                    "unreachable semantic instruction");
    }
    // Remove unreachable structural artifacts (e.g. a jump emitted after a branch return).
    // Depth continuity above includes only this exact retained emission sequence.
    function.code = std::move(reachable);
}
inline bool symbol(const std::string &value) {
    if (value.empty())
        return false;
    auto letter = [](char c) {
        return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_';
    };
    if (!letter(value[0]))
        return false;
    return std::all_of(value.begin() + 1, value.end(), [&](char c) {
        return letter(c) || (c >= '0' && c <= '9');
    });
}
} // namespace verification
inline ValidatedModule validate(Module module) {
    std::map<std::string, const Function *> functions;
    verification::require(!module.functions.empty(), "empty module");
    for (const auto &function : module.functions) {
        verification::require(verification::symbol(function.name) && function.name != "aurora_reflect_size" &&
                                  function.name != "aurora_reflect_field_count" &&
                                  !function.name.starts_with("__au_reflect_") &&
                                  !function.name.starts_with("__au_runtime_"),
                              "invalid or reserved function symbol");
        verification::require(functions.emplace(function.name, &function).second, "duplicate function");
    }
    for (const auto &[id, descriptor] : module.descriptors)
        verification::require(id > 0 && descriptor.size >= 0 && descriptor.publicFields >= 0,
                              "invalid metadata descriptor");
    std::set<int> scopes;
    verification::require(module.descriptorViews.contains(0), "missing root reflection scope");
    for (const auto &[scope, view] : module.descriptorViews) {
        verification::require(scope >= 0 && scope < 64, "invalid reflection scope");
        scopes.insert(scope);
        for (int id : view)
            verification::require(module.descriptors.contains(id), "reflection view references missing descriptor");
    }
    verification::require(module.enumCases.size() <= 64, "too many enum declarations");
    for (const auto &[name, cases] : module.enumCases) {
        verification::require(!name.empty() && name.size() <= 4096 && cases >= 1 && cases <= 256,
                              "invalid nominal enum declaration");
        verification::require(!module.classLayouts.contains(name), "class and enum nominal names overlap");
    }
    for (const auto &[name, layout] : module.classLayouts) {
        verification::require(!name.empty() && name.size() <= 4096 && layout.size() <= 8192,
                              "invalid nominal class layout");
        for (const auto &field : layout)
            verification::require(verification::scalarValueType(field, module.enumCases),
                                  "non-scalar class layout field");
    }
    for (const auto &[name, fields] : module.classFields)
        verification::require(module.classLayouts.contains(name), "logical fields reference unknown class layout");
    for (const auto &[name, layout] : module.classLayouts) {
        if (module.classFields.contains(name))
            continue;
        auto &fields = module.classFields[name];
        for (std::size_t leaf = 0; leaf < layout.size(); ++leaf)
            fields.push_back(ClassField{layout[leaf], static_cast<int>(leaf), 1, false});
    }
    for (const auto &[name, fields] : module.classFields) {
        const auto &layout = module.classLayouts.at(name);
        std::size_t nextLeaf = 0;
        bool composed = false;
        for (const auto &field : fields) {
            const bool child = field.elementType.isClass();
            verification::require((field.array && child) || field.elementCount == 1,
                                  "noncanonical class array element count");
            verification::require(!child || !module.classArrayCarriers.contains(field.elementType.className),
                                  "class array carrier cannot be nested element type");
            verification::require(field.firstLeaf >= 0 && static_cast<std::size_t>(field.firstLeaf) == nextLeaf,
                                  "invalid logical class field shape");
            if (field.elementType.isOwnerStorage()) {
                verification::require(!field.array && field.length == 0,
                                      "owned storage field requires zero scalar leaves");
                verification::require(field.elementType == Type::OwnedBytes ||
                                          (field.elementType.isOwnedValues() &&
                                           field.elementType == Type::ownedValues(Type(field.elementType.className))),
                                      "invalid canonical owned value field type");
            } else if (child) {
                composed = true;
                verification::require(!owningClass(module.classFields, field.elementType.className),
                                      "nested owning class field is unsupported");
                verification::require(field.elementType == Type(field.elementType.className) &&
                                          module.classLayouts.contains(field.elementType.className),
                                      "invalid nominal nested class field");
                const auto &childLayout = module.classLayouts.at(field.elementType.className);
                const int count = field.array ? field.elementCount : 1;
                verification::require(count >= 1 && count <= maximumClassScalarArrayLength,
                                      "class array element count exceeds 1..64");
                verification::require(field.length >= 0 && field.length <= maximumCopiedClassLeaves &&
                                          static_cast<std::size_t>(field.length) == childLayout.size() * count,
                                      "nested class field length mismatch");
                verification::require(nextLeaf + static_cast<std::size_t>(field.length) <= layout.size(),
                                      "logical class field range exceeds layout");
                for (int element = 0; element < count; ++element)
                    for (std::size_t leaf = 0; leaf < childLayout.size(); ++leaf)
                        verification::require(layout[nextLeaf + element * childLayout.size() + leaf] ==
                                                  childLayout[leaf],
                                              "nested class field leaf type mismatch");
            } else {
                verification::require(
                    (field.array ? scalar(field.elementType)
                                 : verification::scalarValueType(field.elementType, module.enumCases)) &&
                        field.length >= 1 &&
                        field.length <= (field.array ? maximumClassArrayLength(field.elementType) : 1),
                    "invalid logical class field shape");
                verification::require(nextLeaf + static_cast<std::size_t>(field.length) <= layout.size(),
                                      "logical class field range exceeds layout");
                for (int element = 0; element < field.length; ++element)
                    verification::require(layout[nextLeaf + element] == field.elementType,
                                          "logical class field leaf type mismatch");
            }
            nextLeaf += static_cast<std::size_t>(field.length);
        }
        verification::require(nextLeaf == layout.size(), "logical class fields do not cover complete layout");
        verification::require(!(composed || owningClass(module.classFields, name)) ||
                                  copiedClassLeavesSupported(layout),
                              "composed or owning class exceeds 64 scalar leaves excluding u8, "
                              "512 u8 leaves or 513 total leaves");
    }
    for (const auto &name : module.classArrayCarriers) {
        verification::require(module.classFields.contains(name), "unknown class array carrier");
        const auto &fields = module.classFields.at(name);
        verification::require(fields.size() == 1 && fields.front().array && fields.front().elementType.isClass(),
                              "class array carrier requires exactly one class array field");
    }
    // The graph walk is bounded before recursion, including zero-leaf cycles.
    // Leaf vectors alone cannot establish the logical shape or nesting depth.
    std::map<std::string, int> depths;
    std::set<std::string> visiting;
    std::function<int(const std::string &, int)> depth = [&](const std::string &name, int path) {
        verification::require(!visiting.contains(name), "cyclic nested class layout");
        verification::require(path <= 4, "nested class layout exceeds depth 4");
        if (depths.contains(name)) {
            verification::require(path + depths.at(name) - 1 <= 4, "nested class layout exceeds depth 4");
            return depths.at(name);
        }
        visiting.insert(name);
        int result = 1;
        for (const auto &field : module.classFields.at(name))
            if (field.elementType.isClass())
                result = std::max(result, 1 + depth(field.elementType.className, path + 1));
        visiting.erase(name);
        depths[name] = result;
        return result;
    };
    for (const auto &[name, fields] : module.classFields)
        depth(name, 1);
    if (module.classLayouts.contains(std::string(service::sampleName))) {
        verification::require(module.classLayouts.at(std::string(service::sampleName)) ==
                                  std::vector<Type>{Type::Bool, Type::U8, Type::Bool},
                              "noncanonical sealed ConsoleSample layout");
        const auto &fields = module.classFields.at(std::string(service::sampleName));
        verification::require(fields.size() == 3, "noncanonical sealed ConsoleSample fields");
        for (std::size_t index = 0; index < fields.size(); ++index)
            verification::require(!fields[index].array && fields[index].firstLeaf == static_cast<int>(index) &&
                                      fields[index].length == 1 &&
                                      fields[index].elementType ==
                                          module.classLayouts.at(std::string(service::sampleName))[index],
                                  "noncanonical sealed ConsoleSample field shape");
    }
    if (module.classLayouts.contains(std::string(service::eventSampleName))) {
        const auto name = std::string(service::eventSampleName);
        const std::vector<Type> layout{service::eventPollResultType(), Type::U64, Type::U64, Type::U64};
        verification::require(module.classLayouts.at(name) == layout, "noncanonical sealed IommuEventSample layout");
        const auto &fields = module.classFields.at(name);
        verification::require(fields.size() == 4, "noncanonical sealed IommuEventSample fields");
        for (std::size_t index = 0; index < fields.size(); ++index)
            verification::require(!fields[index].array && fields[index].firstLeaf == static_cast<int>(index) &&
                                      fields[index].length == 1 && fields[index].elementType == layout[index],
                                  "noncanonical sealed IommuEventSample field shape");
    }
    for (const auto &[name, count] :
         std::vector<std::pair<std::string_view, int>>{{service::eventPollResultName, 4},
                                                       {service::eventAckResultName, 3},
                                                       {service::eventIntakeCompletionName, 7}})
        if (module.enumCases.contains(std::string(name)))
            verification::require(module.enumCases.at(std::string(name)) == count,
                                  "noncanonical sealed event service enum");
    for (const auto name : {service::putResultName,
                            service::completionName,
                            service::displayPutResultName,
                            service::displayCompletionName})
        if (module.enumCases.contains(std::string(name)))
            verification::require(module.enumCases.at(std::string(name)) == 2, "noncanonical sealed service enum");
    const auto canonicalStorage = computeClassStorageLayouts(module.classLayouts, module.classFields);
    for (const auto &[name, fields] : module.classFields) {
        for (const auto &field : fields)
            if (field.elementType.isOwnerStorage())
                verification::verifyOwnerType(field.elementType,
                                              module.classLayouts,
                                              module.classFields,
                                              canonicalStorage,
                                              module.classArrayCarriers);
        const bool composed = std::any_of(fields.begin(), fields.end(), [](const ClassField &field) {
            return field.elementType.isClass();
        });
        verification::require(!(composed || owningClass(module.classFields, name)) ||
                                  canonicalStorage.at(name).reservedBytes <= maximumCopiedClassBytes,
                              "composed or owning class storage exceeds 520 bytes");
    }
    verification::require(module.classStorage.empty() || module.classStorage == canonicalStorage,
                          "noncanonical class storage metadata");
    module.classStorage = canonicalStorage;
    for (auto &function : module.functions)
        verification::verifyFunction(function,
                                     functions,
                                     nullptr,
                                     scopes,
                                     module.classLayouts,
                                     module.classFields,
                                     module.enumCases,
                                     module.classStorage,
                                     module.classArrayCarriers);
    verifyHostedGraph(module);
    return ValidatedModule(std::move(module));
}
} // namespace aurora::ir
