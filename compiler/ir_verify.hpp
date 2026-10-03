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
                           Metrics *metrics = nullptr, const std::set<int> &availableScopes = {0}) {
    require(availableScopes.contains(function.moduleScope), "unknown function module scope");
    require(scalar(function.result), "non-scalar function result");
    require(function.parameters.size() <= 6, "too many parameters");
    for (const auto &type : function.parameters)
        require(scalar(type), "non-scalar parameter");
    require(function.frameBytes >= 0 && function.frameBytes <= 65536 &&
                function.frameBytes % 16 == 0,
            "invalid frame size");
    for (const auto &[offset, type] : function.slots) {
        require(offset > 0 && offset <= function.frameBytes && offset % 8 == 0,
                "invalid slot offset");
        require(scalar(type) || type == Type::Ref || type == Type::MutRef,
                "invalid slot payload type");
    }
    require(!function.code.empty(), "empty function body");
    for (std::size_t index = 0; index < function.code.size(); ++index) {
        const auto *binding = std::get_if<BindParameter>(&function.code[index]);
        if (index < function.parameters.size())
            require(binding && binding->index == static_cast<int>(index),
                    "parameter bindings must form the entry prefix");
        else
            require(!binding, "parameter binding outside entry prefix");
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
    auto enqueue = [&](std::size_t index, const State &state) {
        require(index < function.code.size(), "reachable fallthrough without return");
        require(blockEntry[index], "worklist target is not a basic-block entry");
        if (!states[index]) {
            retainedValueFacts += state.stack.size() + state.initialized.size();
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
        require(merged.stack == state.stack,
                "incompatible value/guard stacks at control-flow join");
        if (merged.current != state.current)
            merged.current.reset();
        std::set<int> initialized;
        std::set_intersection(merged.initialized.begin(), merged.initialized.end(),
                              state.initialized.begin(), state.initialized.end(),
                              std::inserter(initialized, initialized.end()));
        merged.initialized = std::move(initialized);
        if (merged != *states[index]) {
            retainedValueFacts -= states[index]->stack.size() + states[index]->initialized.size();
            retainedValueFacts += merged.stack.size() + merged.initialized.size();
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
            auto array = [&](int offset, int length, const Type &type) {
                require(scalar(type) && length >= 1 && length <= 4096, "invalid array shape");
                require(offset >= length * 8, "array layout underflow");
                for (int element = 0; element < length; ++element) {
                    const int elementOffset = offset - element * 8;
                    slot(elementOffset, type);
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
                        require(state.initialized.contains(operation.offset),
                                "load before initialization");
                        state.current = Value{operation.type, {}};
                    } else if constexpr (std::is_same_v<Op, Store>) {
                        slot(operation.offset, operation.type);
                        current(operation.type);
                        state.initialized.insert(operation.offset);
                    } else if constexpr (std::is_same_v<Op, Push>) {
                        require(state.current.has_value(), "push without current value");
                        state.stack.push_back(*state.current);
                        if (metrics)
                            metrics->peakOperandDepth =
                                std::max(metrics->peakOperandDepth, state.stack.size());
                    } else if constexpr (std::is_same_v<Op, Pop>) {
                        state.current = pop();
                    } else if constexpr (std::is_same_v<Op, UnaryValue>) {
                        require(operation.operation == Unary::CheckedNegate ||
                                    operation.operation == Unary::LogicalNot,
                                "invalid unary operation");
                        const auto type =
                            operation.operation == Unary::LogicalNot ? Type::Bool : Type::I64;
                        current(type);
                        state.current = Value{type, {}};
                    } else if constexpr (std::is_same_v<Op, BinaryValue>) {
                        require(operation.operation == Binary::CheckedAdd ||
                                    operation.operation == Binary::CheckedSubtract ||
                                    operation.operation == Binary::CheckedMultiply,
                                "invalid binary operation");
                        current(Type::I64);
                        require(pop().type == Type::I64, "noninteger left operand");
                        state.current = Value{Type::I64, {}};
                    } else if constexpr (std::is_same_v<Op, Compare>) {
                        const auto ordinal = static_cast<int>(operation.operation);
                        require(ordinal >= 0 &&
                                    ordinal <= static_cast<int>(Comparison::GreaterEqual),
                                "invalid comparison");
                        require(scalar(operation.operandType), "non-scalar comparison");
                        if (operation.operation != Comparison::Equal &&
                            operation.operation != Comparison::NotEqual)
                            require(operation.operandType == Type::I64, "ordered bool comparison");
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
                    } else if constexpr (std::is_same_v<Op, BorrowHandle>) {
                        slot(operation.ownerOffset, Type::I64);
                        require(state.initialized.contains(operation.ownerOffset),
                                "borrow of uninitialized payload");
                        require(operation.referenceType == Type::Ref ||
                                    operation.referenceType == Type::MutRef,
                                "invalid borrow-handle type");
                        state.current = Value{operation.referenceType, {}};
                    } else if constexpr (std::is_same_v<Op, Call>) {
                        require(functions.contains(operation.callee), "unknown call target");
                        const auto &target = *functions.at(operation.callee);
                        for (auto argument = target.parameters.rbegin();
                             argument != target.parameters.rend(); ++argument)
                            require(pop().type == *argument, "call argument type mismatch");
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
                        current(function.result);
                        require(state.stack.empty(), "unbalanced stack at return");
                        fallsThrough = false;
                    } else if constexpr (std::is_same_v<Op, BindParameter>) {
                        require(operation.index >= 0 && static_cast<std::size_t>(operation.index) <
                                                            function.parameters.size(),
                                "invalid parameter index");
                        require(function.parameters[operation.index] == operation.type,
                                "parameter type mismatch");
                        slot(operation.offset, operation.type);
                        state.initialized.insert(operation.offset);
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
    for (auto &function : module.functions)
        verification::verifyFunction(function, functions, nullptr, scopes);
    return ValidatedModule(std::move(module));
}
} // namespace aurora::ir
