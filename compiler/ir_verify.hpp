#pragma once
#include "ir.hpp"
#include <algorithm>
#include <deque>
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
class Value {
  public:
    Type type;
    std::optional<Guard> guard;
    bool operator==(const Value &) const = default;
};
class State {
  public:
    std::optional<Value> current;
    std::vector<Value> stack;
    std::set<int> initialized;
    // Must-initialized facts intersect at joins; may-written facts union. The
    // latter prevent an alternate path or backedge from hiding a second init.
    std::set<int> maybeInitialized;
    std::set<int> receiverInitialized;
    std::set<int> receiverMaybeInitialized;
    std::set<int> maybeConstructedObjects;
    std::set<int> activeObjects;
    bool operator==(const State &) const = default;
};
inline void require(bool condition, const std::string &message) {
    if (!condition)
        fail(message);
}
class Metrics {
  public:
    std::size_t snapshots = 0;
    std::size_t peakOperandDepth = 0;
    std::size_t peakRetainedValueFacts = 0;
};
inline void verifyFunction(Function &function,
                           const std::map<std::string, const Function *> &functions,
                           Metrics *metrics = nullptr, const std::set<int> &availableScopes = {0},
                           const std::map<std::string, std::vector<Type>> &classLayouts = {}) {
    require(availableScopes.contains(function.moduleScope), "unknown function module scope");
    auto boundaryType = [&](const Type &type) {
        if (scalar(type))
            return;
        require(!function.receiver, "receiver signatures must remain scalar");
        require(type.isClass() && type == Type(type.className), "invalid value boundary type");
        require(classLayouts.contains(type.className), "unknown value boundary class");
        require(classLayouts.at(type.className).size() <= 64,
                "value boundary class exceeds 64 scalar fields");
    };
    boundaryType(function.result);
    require(function.parameters.size() <= 6, "too many parameters");
    for (const auto &type : function.parameters)
        boundaryType(type);
    require(function.frameBytes >= 0 && function.frameBytes <= 65536 &&
                function.frameBytes % 16 == 0,
            "invalid frame size");
    for (const auto &[offset, type] : function.slots) {
        require(offset > 0 && offset <= function.frameBytes && offset % 8 == 0,
                "invalid slot offset");
        require(scalar(type) || type == Type::Ref || type == Type::MutRef,
                "invalid slot payload type");
    }
    const std::vector<Type> *receiverLayout = nullptr;
    if (function.receiver) {
        const auto &receiver = *function.receiver;
        require(classLayouts.contains(receiver.className), "unknown receiver class");
        receiverLayout = &classLayouts.at(receiver.className);
        require(!receiver.constructor || (receiver.mutableValue && function.result == Type::I64),
                "invalid constructor receiver signature");
    }
    // Validate complete object ranges, including padding for an empty class.
    // Scalar slots may describe actual fields, never padding or the hidden ABI slot.
    std::map<int, const ObjectSlot *> objectFields;
    std::map<int, int> objectBases;
    std::set<int> objectStorage;
    for (const auto &[base, object] : function.objectSlots) {
        require(classLayouts.contains(object.className), "unknown object class");
        const auto &layout = classLayouts.at(object.className);
        const auto words = std::max<std::size_t>(1, layout.size());
        require(base > 0 && base <= function.frameBytes && base % 8 == 0 &&
                    static_cast<std::size_t>(base / 8) >= words,
                "invalid object layout offset");
        for (std::size_t index = 0; index < words; ++index) {
            const int offset = base - static_cast<int>(index * 8);
            require(objectStorage.insert(offset).second, "overlapping object layouts");
            if (index < layout.size()) {
                require(function.slots.contains(offset) &&
                            function.slots.at(offset) == layout[index],
                        "object field slot type/layout mismatch");
                objectFields.emplace(offset, &object);
                objectBases.emplace(offset, base);
            } else
                require(!function.slots.contains(offset), "scalar slot overlaps empty object");
        }
    }
    require(!function.code.empty(), "empty function body");
    std::set<int> scalarParameterSlots;
    std::set<int> objectParameterSlots;
    for (std::size_t index = 0; index < function.code.size(); ++index) {
        const auto *binding = std::get_if<BindParameter>(&function.code[index]);
        const auto *objectBinding = std::get_if<BindObjectParameter>(&function.code[index]);
        if (index < function.parameters.size()) {
            const auto &type = function.parameters[index];
            if (type.isClass()) {
                require(objectBinding && objectBinding->index == static_cast<int>(index),
                        "object parameter bindings must form the entry prefix");
                require(objectParameterSlots.insert(objectBinding->offset).second,
                        "object parameter bindings overlap");
            } else {
                require(binding && binding->index == static_cast<int>(index),
                        "parameter bindings must form the entry prefix");
                require(scalarParameterSlots.insert(binding->offset).second,
                        "scalar parameter bindings overlap");
            }
        } else
            require(!binding && !objectBinding, "parameter binding outside entry prefix");
    }
    std::map<int, std::size_t> labels;
    for (std::size_t index = 0; index < function.code.size(); ++index) {
        if (const auto *label = std::get_if<Label>(&function.code[index]))
            require(label->id >= 0 && labels.emplace(label->id, index).second,
                    "duplicate or invalid label");
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
    blockEntry[0] = true;
    for (std::size_t index = 0; index < function.code.size(); ++index) {
        if (std::holds_alternative<Label>(function.code[index]))
            blockEntry[index] = true;
        if (std::holds_alternative<BranchFalse>(function.code[index]) &&
            index + 1 < function.code.size())
            blockEntry[index + 1] = true;
    }
    std::vector<std::optional<State>> states(function.code.size());
    states[0] = State{};
    if (function.receiver && !function.receiver->constructor) {
        for (std::size_t field = 0; field < receiverLayout->size(); ++field) {
            states[0]->receiverInitialized.insert(static_cast<int>(field));
            states[0]->receiverMaybeInitialized.insert(static_cast<int>(field));
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
        require(found != function.slots.end() && found->second == type,
                "slot type/layout mismatch");
    };
    auto facts = [](const State &state) {
        return state.stack.size() + state.initialized.size() + state.maybeInitialized.size() +
               state.receiverInitialized.size() + state.receiverMaybeInitialized.size() +
               state.maybeConstructedObjects.size() + state.activeObjects.size();
    };
    retainedValueFacts = facts(*states[0]);
    if (metrics)
        metrics->peakRetainedValueFacts = retainedValueFacts;
    auto intersection = [](const std::set<int> &left, const std::set<int> &right) {
        std::set<int> result;
        std::set_intersection(left.begin(), left.end(), right.begin(), right.end(),
                              std::inserter(result, result.end()));
        return result;
    };
    auto enqueue = [&](std::size_t index, const State &state) {
        require(index < function.code.size(), "reachable fallthrough without return");
        require(blockEntry[index], "worklist target is not a basic-block entry");
        if (!states[index]) {
            retainedValueFacts += facts(state);
            if (metrics) {
                ++metrics->snapshots;
                metrics->peakRetainedValueFacts =
                    std::max(metrics->peakRetainedValueFacts, retainedValueFacts);
            }
            states[index] = state;
            pending.push_back(index);
            return;
        }
        State merged = *states[index];
        require(merged.activeObjects == state.activeObjects,
                "incompatible active object lifetimes at control-flow join");
        require(merged.stack == state.stack,
                "incompatible value/guard stacks at control-flow join");
        if (merged.current != state.current)
            merged.current.reset();
        merged.initialized = intersection(merged.initialized, state.initialized);
        merged.receiverInitialized =
            intersection(merged.receiverInitialized, state.receiverInitialized);
        merged.maybeInitialized.insert(state.maybeInitialized.begin(),
                                       state.maybeInitialized.end());
        merged.receiverMaybeInitialized.insert(state.receiverMaybeInitialized.begin(),
                                               state.receiverMaybeInitialized.end());
        merged.maybeConstructedObjects.insert(state.maybeConstructedObjects.begin(),
                                              state.maybeConstructedObjects.end());
        if (merged != *states[index]) {
            retainedValueFacts -= facts(*states[index]);
            retainedValueFacts += facts(merged);
            if (metrics)
                metrics->peakRetainedValueFacts =
                    std::max(metrics->peakRetainedValueFacts, retainedValueFacts);
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
            bool fallsThrough = true;
            auto current = [&](const Type &expected) -> Value {
                require(state.current && state.current->type == expected,
                        "missing or mistyped current value");
                return *state.current;
            };
            auto pop = [&]() -> Value {
                require(!state.stack.empty(), "value stack underflow");
                auto value = state.stack.back();
                state.stack.pop_back();
                return value;
            };
            auto activeObjectField = [&](int offset) {
                require(!objectBases.contains(offset) ||
                            state.activeObjects.contains(objectBases.at(offset)),
                        "object field access outside active lifetime");
            };
            auto store = [&](int offset, const Type &type) {
                slot(offset, type);
                activeObjectField(offset);
                require(!scalarParameterSlots.contains(offset) ||
                            !state.maybeInitialized.contains(offset),
                        "write to immutable scalar parameter");
                const auto object = objectFields.find(offset);
                require(object == objectFields.end() || object->second->mutableValue ||
                            !state.maybeInitialized.contains(offset),
                        "write to initialized const object field");
                state.initialized.insert(offset);
                state.maybeInitialized.insert(offset);
            };
            auto receiverField = [&](int fieldIndex, const Type &type) {
                require(receiverLayout != nullptr, "receiver access without bound receiver");
                require(fieldIndex >= 0 &&
                            static_cast<std::size_t>(fieldIndex) < receiverLayout->size() &&
                            (*receiverLayout)[fieldIndex] == type,
                        "receiver field type/layout mismatch");
            };
            auto array = [&](int offset, int length, const Type &type) {
                require(scalar(type) && length >= 1 && length <= 4096, "invalid array shape");
                require(offset >= length * 8, "array layout underflow");
                for (int element = 0; element < length; ++element) {
                    const int elementOffset = offset - element * 8;
                    slot(elementOffset, type);
                    activeObjectField(elementOffset);
                    require(state.initialized.contains(elementOffset),
                            "array element not initialized");
                }
            };
            auto guard = [&](const Value &value, int offset, int length, const Type &type) {
                require(value.type == Type::I64 &&
                            value.guard == std::optional<Guard>(Guard{offset, length, type}),
                        "index access lacks matching dominating bounds token");
            };
            std::visit(
                [&](const auto &operation) {
                    using Op = std::decay_t<decltype(operation)>;
                    if constexpr (std::is_same_v<Op, Constant>) {
                        require(scalar(operation.type), "invalid constant type");
                        require(operation.type != Type::Bool || operation.value == 0 ||
                                    operation.value == 1,
                                "noncanonical bool");
                        state.current = Value{operation.type, {}};
                    } else if constexpr (std::is_same_v<Op, Load>) {
                        slot(operation.offset, operation.type);
                        activeObjectField(operation.offset);
                        require(state.initialized.contains(operation.offset),
                                "load before initialization");
                        state.current = Value{operation.type, {}};
                    } else if constexpr (std::is_same_v<Op, Store>) {
                        current(operation.type);
                        store(operation.offset, operation.type);
                    } else if constexpr (std::is_same_v<Op, Push>) {
                        require(state.current.has_value(), "push without current value");
                        state.stack.push_back(*state.current);
                        if (metrics)
                            metrics->peakOperandDepth =
                                std::max(metrics->peakOperandDepth, state.stack.size());
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
                            type = Type::U64;
                            break;
                        }
                        require(type.has_value(), "invalid unary operation");
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
                        require(operation.operandType == Type::U64 ||
                                    (!unsignedOnly && operation.operandType == Type::I64),
                                "invalid binary operand type");
                        current(shift ? Type::I64 : operation.operandType);
                        require(pop().type == operation.operandType,
                                "noninteger left operand or binary type mismatch");
                        state.current = Value{operation.operandType, {}};
                    } else if constexpr (std::is_same_v<Op, Convert>) {
                        require((operation.sourceType == Type::I64 &&
                                 operation.resultType == Type::U64) ||
                                    (operation.sourceType == Type::U64 &&
                                     operation.resultType == Type::I64),
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
                        require(scalar(operation.operandType), "non-scalar comparison");
                        if (ordered)
                            require(operation.operandType == Type::I64 ||
                                        operation.operandType == Type::U64,
                                    "ordered bool comparison");
                        current(operation.operandType);
                        require(pop().type == operation.operandType, "comparison type mismatch");
                        state.current = Value{Type::Bool, {}};
                    } else if constexpr (std::is_same_v<Op, BoundsGuard>) {
                        current(Type::I64);
                        array(operation.offset, operation.length, operation.elementType);
                        state.current = Value{Type::I64, Guard{operation.offset, operation.length,
                                                               operation.elementType}};
                    } else if constexpr (std::is_same_v<Op, IndexLoad>) {
                        array(operation.offset, operation.length, operation.elementType);
                        guard(current(Type::I64), operation.offset, operation.length,
                              operation.elementType);
                        state.current = Value{operation.elementType, {}};
                    } else if constexpr (std::is_same_v<Op, IndexStore>) {
                        array(operation.offset, operation.length, operation.elementType);
                        current(operation.elementType);
                        guard(pop(), operation.offset, operation.length, operation.elementType);
                        for (int element = 0; element < operation.length; ++element) {
                            const int offset = operation.offset - element * 8;
                            require(!scalarParameterSlots.contains(offset),
                                    "indexed write to immutable scalar parameter");
                            require(!objectFields.contains(offset) ||
                                        objectFields.at(offset)->mutableValue,
                                    "indexed write to const object field");
                        }
                    } else if constexpr (std::is_same_v<Op, BorrowHandle>) {
                        slot(operation.ownerOffset, Type::I64);
                        require(!objectFields.contains(operation.ownerOffset),
                                "object field cannot become a scalar borrow handle");
                        require(state.initialized.contains(operation.ownerOffset),
                                "borrow of uninitialized payload");
                        require(operation.referenceType == Type::Ref ||
                                    operation.referenceType == Type::MutRef,
                                "invalid borrow-handle type");
                        state.current = Value{operation.referenceType, {}};
                    } else if constexpr (std::is_same_v<Op, Call>) {
                        require(functions.contains(operation.callee), "unknown call target");
                        const auto &target = *functions.at(operation.callee);
                        require(!target.receiver, "plain call cannot target receiver function");
                        require(scalar(target.result) &&
                                    std::all_of(target.parameters.begin(), target.parameters.end(),
                                                [](const Type &type) { return scalar(type); }),
                                "plain call cannot target aggregate signature");
                        for (auto argument = target.parameters.rbegin();
                             argument != target.parameters.rend(); ++argument)
                            require(pop().type == *argument, "call argument type mismatch");
                        state.current = Value{target.result, {}};
                    } else if constexpr (std::is_same_v<Op, AggregateCall>) {
                        require(functions.contains(operation.callee),
                                "unknown aggregate call target");
                        const auto &target = *functions.at(operation.callee);
                        require(!target.receiver, "aggregate call cannot target receiver function");
                        require(target.result.isClass() ||
                                    std::any_of(target.parameters.begin(), target.parameters.end(),
                                                [](const Type &type) { return type.isClass(); }),
                                "aggregate call requires aggregate signature");
                        require(operation.objectArguments.size() == target.parameters.size(),
                                "aggregate call argument vector size mismatch");
                        std::set<int> argumentStorage;
                        for (std::size_t arg = target.parameters.size(); arg > 0; --arg) {
                            const auto &type = target.parameters[arg - 1];
                            const int base = operation.objectArguments[arg - 1];
                            if (scalar(type)) {
                                require(base == 0, "scalar argument cannot name object storage");
                                require(pop().type == type,
                                        "aggregate scalar argument type mismatch");
                                continue;
                            }
                            require(type.isClass() && classLayouts.contains(type.className),
                                    "invalid aggregate parameter type");
                            require(function.objectSlots.contains(base),
                                    "aggregate argument requires exact object slot");
                            require(argumentStorage.insert(base).second,
                                    "aggregate argument snapshots must be distinct");
                            const auto &object = function.objectSlots.at(base);
                            require(object.className == type.className,
                                    "aggregate argument nominal class mismatch");
                            require(!object.mutableValue,
                                    "aggregate argument snapshot must be readonly");
                            require(state.activeObjects.contains(base),
                                    "aggregate argument outside active object lifetime");
                            const auto &layout = classLayouts.at(type.className);
                            for (std::size_t field = 0; field < layout.size(); ++field)
                                require(
                                    state.initialized.contains(base - static_cast<int>(field * 8)),
                                    "aggregate argument object not fully initialized");
                        }
                        if (target.result.isClass()) {
                            const int base = operation.resultOffset;
                            require(function.objectSlots.contains(base),
                                    "aggregate result requires exact object slot");
                            require(!argumentStorage.contains(base),
                                    "aggregate result aliases argument snapshot");
                            const auto &object = function.objectSlots.at(base);
                            require(object.className == target.result.className,
                                    "aggregate result nominal class mismatch");
                            require(state.activeObjects.contains(base),
                                    "aggregate result outside active object lifetime");
                            require(!state.maybeConstructedObjects.contains(base),
                                    "aggregate result object already initialized");
                            const auto &layout = classLayouts.at(object.className);
                            for (std::size_t field = 0; field < layout.size(); ++field)
                                require(!state.maybeInitialized.contains(
                                            base - static_cast<int>(field * 8)),
                                        "aggregate result requires uninitialized object");
                            state.maybeConstructedObjects.insert(base);
                            for (std::size_t field = 0; field < layout.size(); ++field) {
                                const int offset = base - static_cast<int>(field * 8);
                                state.initialized.insert(offset);
                                state.maybeInitialized.insert(offset);
                            }
                            state.current.reset();
                        } else {
                            require(scalar(target.result), "invalid aggregate result type");
                            require(operation.resultOffset == 0,
                                    "scalar result cannot name object storage");
                            state.current = Value{target.result, {}};
                        }
                    } else if constexpr (std::is_same_v<Op, BeginObject> ||
                                         std::is_same_v<Op, EndObject>) {
                        require(function.objectSlots.contains(operation.offset),
                                "lifetime operation requires exact object slot");
                        if constexpr (std::is_same_v<Op, BeginObject>) {
                            require(!objectParameterSlots.contains(operation.offset),
                                    "object parameter lifetime cannot restart");
                            require(!state.activeObjects.contains(operation.offset),
                                    "object lifetime already active");
                            state.activeObjects.insert(operation.offset);
                        } else {
                            require(state.activeObjects.contains(operation.offset),
                                    "object lifetime is not active");
                            state.activeObjects.erase(operation.offset);
                        }
                        const auto &object = function.objectSlots.at(operation.offset);
                        const auto &layout = classLayouts.at(object.className);
                        for (std::size_t field = 0; field < layout.size(); ++field) {
                            const int offset = operation.offset - static_cast<int>(field * 8);
                            state.initialized.erase(offset);
                            state.maybeInitialized.erase(offset);
                        }
                        state.maybeConstructedObjects.erase(operation.offset);
                    } else if constexpr (std::is_same_v<Op, ReceiverLoad>) {
                        receiverField(operation.fieldIndex, operation.type);
                        require(!function.receiver->constructor,
                                "constructor cannot read receiver during initialization");
                        require(state.receiverInitialized.contains(operation.fieldIndex),
                                "receiver field not initialized");
                        state.current = Value{operation.type, {}};
                    } else if constexpr (std::is_same_v<Op, ReceiverStore>) {
                        receiverField(operation.fieldIndex, operation.type);
                        current(operation.type);
                        require(function.receiver->mutableValue, "write through const receiver");
                        if (function.receiver->constructor)
                            require(!state.receiverMaybeInitialized.contains(operation.fieldIndex),
                                    "constructor field initialized more than once");
                        state.receiverInitialized.insert(operation.fieldIndex);
                        state.receiverMaybeInitialized.insert(operation.fieldIndex);
                    } else if constexpr (std::is_same_v<Op, MethodCall>) {
                        require(functions.contains(operation.callee), "unknown method call target");
                        const auto &target = *functions.at(operation.callee);
                        require(target.receiver.has_value(),
                                "method call requires receiver target");
                        require(scalar(target.result) &&
                                    std::all_of(target.parameters.begin(), target.parameters.end(),
                                                [](const Type &type) { return scalar(type); }),
                                "receiver signatures must remain scalar");
                        const auto &receiver = *target.receiver;
                        require(operation.receiverOffset >= 0, "invalid method receiver offset");
                        if (operation.receiverOffset == 0) {
                            require(function.receiver.has_value(),
                                    "forwarding without bound receiver");
                            require(!function.receiver->constructor && !receiver.constructor,
                                    "constructor cannot forward receiver during initialization");
                            require(function.receiver->className == receiver.className,
                                    "forwarded receiver nominal class mismatch");
                            require(!receiver.mutableValue || function.receiver->mutableValue,
                                    "const receiver cannot forward mutable capability");
                        } else {
                            require(function.objectSlots.contains(operation.receiverOffset),
                                    "method receiver is not an object slot");
                            const auto &object = function.objectSlots.at(operation.receiverOffset);
                            require(state.activeObjects.contains(operation.receiverOffset),
                                    "method receiver outside active object lifetime");
                            require(object.className == receiver.className,
                                    "method receiver nominal class mismatch");
                            const auto &layout = classLayouts.at(object.className);
                            if (receiver.constructor) {
                                require(!state.maybeConstructedObjects.contains(
                                            operation.receiverOffset),
                                        "object constructor called more than once");
                                for (std::size_t field = 0; field < layout.size(); ++field)
                                    require(
                                        !state.maybeInitialized.contains(
                                            operation.receiverOffset - static_cast<int>(field * 8)),
                                        "constructor requires uninitialized object");
                                state.maybeConstructedObjects.insert(operation.receiverOffset);
                                for (std::size_t field = 0; field < layout.size(); ++field) {
                                    const int offset =
                                        operation.receiverOffset - static_cast<int>(field * 8);
                                    state.initialized.insert(offset);
                                    state.maybeInitialized.insert(offset);
                                }
                            } else {
                                require(!receiver.mutableValue || object.mutableValue,
                                        "const object cannot supply mutable receiver");
                                for (std::size_t field = 0; field < layout.size(); ++field)
                                    require(state.initialized.contains(operation.receiverOffset -
                                                                       static_cast<int>(field * 8)),
                                            "method receiver object not fully initialized");
                            }
                        }
                        for (auto argument = target.parameters.rbegin();
                             argument != target.parameters.rend(); ++argument)
                            require(pop().type == *argument, "method argument type mismatch");
                        state.current = Value{target.result, {}};
                    } else if constexpr (std::is_same_v<Op, MetadataQuery>) {
                        require(operation.query == Query::Size ||
                                    operation.query == Query::PublicFieldCount,
                                "unknown metadata query");
                        require(operation.moduleScope == function.moduleScope,
                                "metadata query changes defining-module scope");
                        current(Type::I64);
                        state.current = Value{Type::I64, {}};
                    } else if constexpr (std::is_same_v<Op, Label>) {
                        require(state.stack.empty(), "temporary values cross a statement label");
                    } else if constexpr (std::is_same_v<Op, Jump>) {
                        require(state.stack.empty(), "temporary values cross a jump");
                        enqueue(labels.at(operation.target), state);
                        fallsThrough = false;
                    } else if constexpr (std::is_same_v<Op, BranchFalse>) {
                        current(Type::Bool);
                        require(state.stack.empty(), "temporary values cross a branch");
                        enqueue(labels.at(operation.target), state);
                    } else if constexpr (std::is_same_v<Op, Return>) {
                        require(scalar(function.result), "scalar return cannot return class value");
                        current(function.result);
                        require(state.stack.empty(), "unbalanced stack at return");
                        if (function.receiver && function.receiver->constructor)
                            require(state.receiverInitialized.size() == receiverLayout->size(),
                                    "constructor returns before all fields initialized");
                        fallsThrough = false;
                    } else if constexpr (std::is_same_v<Op, ReturnObject>) {
                        require(function.result.isClass(), "object return requires class result");
                        require(function.objectSlots.contains(operation.offset),
                                "object return requires exact object slot");
                        const auto &object = function.objectSlots.at(operation.offset);
                        require(object.className == function.result.className,
                                "object return nominal class mismatch");
                        require(state.activeObjects.contains(operation.offset),
                                "object return outside active lifetime");
                        const auto &layout = classLayouts.at(object.className);
                        for (std::size_t field = 0; field < layout.size(); ++field)
                            require(state.initialized.contains(operation.offset -
                                                               static_cast<int>(field * 8)),
                                    "returned object not fully initialized");
                        require(state.stack.empty(), "unbalanced stack at object return");
                        fallsThrough = false;
                    } else if constexpr (std::is_same_v<Op, BindObjectParameter>) {
                        require(operation.index >= 0 && static_cast<std::size_t>(operation.index) <
                                                            function.parameters.size(),
                                "invalid object parameter index");
                        require(function.parameters[operation.index] == Type(operation.className),
                                "object parameter type mismatch");
                        require(function.objectSlots.contains(operation.offset),
                                "object parameter requires exact object slot");
                        const auto &object = function.objectSlots.at(operation.offset);
                        require(object.className == operation.className,
                                "object parameter nominal class mismatch");
                        require(!object.mutableValue, "object parameter must be readonly");
                        require(!state.activeObjects.contains(operation.offset),
                                "object parameter lifetime already active");
                        state.activeObjects.insert(operation.offset);
                        state.maybeConstructedObjects.insert(operation.offset);
                        const auto &layout = classLayouts.at(object.className);
                        for (std::size_t field = 0; field < layout.size(); ++field)
                            store(operation.offset - static_cast<int>(field * 8), layout[field]);
                    } else if constexpr (std::is_same_v<Op, BindParameter>) {
                        require(operation.index >= 0 && static_cast<std::size_t>(operation.index) <
                                                            function.parameters.size(),
                                "invalid parameter index");
                        require(function.parameters[operation.index] == operation.type,
                                "parameter type mismatch");
                        require(!objectFields.contains(operation.offset),
                                "parameter cannot bind object field storage");
                        store(operation.offset, operation.type);
                    } else {
                        static_assert(!std::is_same_v<Op, Op>,
                                      "unhandled typed IR verifier operation");
                    }
                },
                function.code[index]);
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
    for (std::size_t index = 0; index < function.code.size(); ++index) {
        if (reached[index])
            reachable.push_back(std::move(function.code[index]));
        else
            require(std::holds_alternative<Label>(function.code[index]) ||
                        std::holds_alternative<Jump>(function.code[index]),
                    "unreachable semantic instruction");
    }
    // Remove unreachable structural artifacts (e.g. a jump emitted after a branch return).
    // This also keeps backend linear stack accounting identical to reachable execution.
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
    return std::all_of(value.begin() + 1, value.end(),
                       [&](char c) { return letter(c) || (c >= '0' && c <= '9'); });
}
} // namespace verification
inline ValidatedModule validate(Module module) {
    std::map<std::string, const Function *> functions;
    verification::require(!module.functions.empty(), "empty module");
    for (const auto &function : module.functions) {
        verification::require(verification::symbol(function.name) &&
                                  function.name != "aurora_reflect_size" &&
                                  function.name != "aurora_reflect_field_count" &&
                                  !function.name.starts_with("__au_reflect_"),
                              "invalid or reserved function symbol");
        verification::require(functions.emplace(function.name, &function).second,
                              "duplicate function");
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
            verification::require(module.descriptors.contains(id),
                                  "reflection view references missing descriptor");
    }
    for (const auto &[name, layout] : module.classLayouts) {
        verification::require(!name.empty() && name.size() <= 4096 && layout.size() <= 8192,
                              "invalid nominal class layout");
        for (const auto &field : layout)
            verification::require(scalar(field), "non-scalar class layout field");
    }
    for (auto &function : module.functions)
        verification::verifyFunction(function, functions, nullptr, scopes, module.classLayouts);
    // Analyze the full call graph so scalar helpers cannot hide receiver
    // recursion. Iterative Kosaraju traversal is O(functions + calls) and does
    // not consume host call-stack depth on an adversarial source-sized graph.
    std::map<std::string, std::size_t> functionIndices;
    for (std::size_t index = 0; index < module.functions.size(); ++index)
        functionIndices.emplace(module.functions[index].name, index);
    std::vector<std::vector<std::size_t>> calls(module.functions.size());
    std::vector<std::vector<std::size_t>> callers(module.functions.size());
    for (std::size_t index = 0; index < module.functions.size(); ++index)
        for (const auto &instruction : module.functions[index].code) {
            const std::string *target = nullptr;
            if (const auto *call = std::get_if<Call>(&instruction))
                target = &call->callee;
            if (const auto *call = std::get_if<MethodCall>(&instruction))
                target = &call->callee;
            if (const auto *call = std::get_if<AggregateCall>(&instruction))
                target = &call->callee;
            if (target) {
                const auto next = functionIndices.at(*target);
                calls[index].push_back(next);
                callers[next].push_back(index);
            }
        }
    std::vector<bool> visited(module.functions.size(), false);
    std::vector<std::size_t> finishOrder;
    for (std::size_t start = 0; start < module.functions.size(); ++start) {
        if (visited[start])
            continue;
        visited[start] = true;
        std::vector<std::pair<std::size_t, std::size_t>> pending{{start, 0}};
        while (!pending.empty()) {
            auto &[index, nextEdge] = pending.back();
            if (nextEdge == calls[index].size()) {
                finishOrder.push_back(index);
                pending.pop_back();
                continue;
            }
            const auto next = calls[index][nextEdge++];
            if (!visited[next]) {
                visited[next] = true;
                pending.emplace_back(next, 0);
            }
        }
    }
    std::fill(visited.begin(), visited.end(), false);
    for (auto start = finishOrder.rbegin(); start != finishOrder.rend(); ++start) {
        if (visited[*start])
            continue;
        visited[*start] = true;
        std::vector<std::size_t> pending{*start};
        std::size_t componentSize = 0;
        bool hasReceiver = false;
        bool selfEdge = false;
        while (!pending.empty()) {
            const auto index = pending.back();
            pending.pop_back();
            ++componentSize;
            hasReceiver |= module.functions[index].receiver.has_value();
            selfEdge |=
                std::find(calls[index].begin(), calls[index].end(), index) != calls[index].end();
            for (const auto next : callers[index])
                if (!visited[next]) {
                    visited[next] = true;
                    pending.push_back(next);
                }
        }
        verification::require(!hasReceiver || (componentSize == 1 && !selfEdge),
                              "recursive receiver call cycle");
    }
    return ValidatedModule(std::move(module));
}
} // namespace aurora::ir
