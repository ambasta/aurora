#include "ir_verify.hpp"
#include "x86.hpp"
#include <functional>
#include <iostream>
#include <string>

using namespace aurora;
using namespace aurora::ir;
namespace {
int passed = 0;
Module baseline() {
    Module module;
    aurora::ir::Function function;
    function.name = "test";
    function.result = Type::I64;
    function.frameBytes = 16;
    function.slots[8] = Type::I64;
    function.code = {Constant{42, Type::I64}, Store{8, Type::I64}, Load{8, Type::I64}, Return{}};
    module.functions.push_back(std::move(function));
    return module;
}
void reject(const std::string &name, const std::function<void(Module &)> &mutate,
            const std::string &expected) {
    auto module = baseline();
    mutate(module);
    try {
        auto checked = validate(std::move(module));
        (void)checked;
    } catch (const Error &error) {
        if (std::string(error.what()).find(expected) == std::string::npos)
            throw Error(name + ": wrong diagnostic: " + error.what());
        ++passed;
        std::cout << "PASS IR " << name << '\n';
        return;
    }
    throw Error(name + ": malformed IR was accepted");
}
void accept(const std::string &name, Module module) {
    const auto checked = validate(std::move(module));
    const auto assembly = X86Emitter{}.emit(checked);
    if (assembly.empty())
        throw Error(name + ": empty assembly");
    ++passed;
    std::cout << "PASS IR " << name << '\n';
}
} // namespace
int main() {
    try {
        accept("typed load/store", baseline());
        reject("empty module", [](Module &m) { m.functions.clear(); }, "empty module");
        reject(
            "symbol injection", [](Module &m) { m.functions[0].name = "x:\n.include \"bad\""; },
            "function symbol");
        reject(
            "reserved symbol", [](Module &m) { m.functions[0].name = "aurora_reflect_size"; },
            "function symbol");
        reject(
            "duplicate function", [](Module &m) { m.functions.push_back(m.functions[0]); },
            "duplicate function");
        reject("bad frame", [](Module &m) { m.functions[0].frameBytes = 8; }, "frame size");
        reject(
            "oversized frame", [](Module &m) { m.functions[0].frameBytes = 65552; }, "frame size");
        reject("bad slot", [](Module &m) { m.functions[0].slots[7] = Type::I64; }, "slot offset");
        reject(
            "slot past frame", [](Module &m) { m.functions[0].slots[24] = Type::I64; },
            "slot offset");
        reject(
            "noncanonical bool",
            [](Module &m) { m.functions[0].code[0] = Constant{2, Type::Bool}; },
            "noncanonical bool");
        reject(
            "load uninitialized",
            [](Module &m) {
                m.functions[0].code.erase(m.functions[0].code.begin(),
                                          m.functions[0].code.begin() + 2);
            },
            "load before initialization");
        reject(
            "load wrong type", [](Module &m) { m.functions[0].code[2] = Load{8, Type::Bool}; },
            "slot type/layout");
        reject(
            "store wrong type", [](Module &m) { m.functions[0].code[0] = Constant{1, Type::Bool}; },
            "mistyped current");
        reject(
            "stack underflow",
            [](Module &m) { m.functions[0].code.insert(m.functions[0].code.begin(), Pop{}); },
            "stack underflow");
        reject(
            "push undefined",
            [](Module &m) { m.functions[0].code.insert(m.functions[0].code.begin(), Push{}); },
            "push without");
        reject(
            "unbalanced return",
            [](Module &m) { m.functions[0].code.insert(m.functions[0].code.end() - 1, Push{}); },
            "unbalanced stack");
        reject(
            "wrong return", [](Module &m) { m.functions[0].result = Type::Bool; },
            "mistyped current");
        reject("fallthrough", [](Module &m) { m.functions[0].code.pop_back(); }, "fallthrough");
        reject(
            "unknown jump", [](Module &m) { m.functions[0].code.push_back(Jump{99}); },
            "unknown jump");
        reject(
            "duplicate label",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin(), {Label{1}, Label{1}});
            },
            "duplicate or invalid label");
        reject(
            "unreachable operation",
            [](Module &m) { m.functions[0].code.push_back(Constant{0, Type::I64}); },
            "unreachable semantic");
        reject(
            "unreachable bad parameter",
            [](Module &m) { m.functions[0].code.push_back(BindParameter{999, 8, Type::I64}); },
            "outside entry prefix");
        reject(
            "jump over stack effect",
            [](Module &m) {
                m.functions[0].code = {Constant{42, Type::I64},    Jump{1}, Push{}, Label{1},
                                       MetadataQuery{Query::Size}, Return{}};
            },
            "unreachable semantic");
        reject(
            "missing parameter prefix", [](Module &m) { m.functions[0].parameters = {Type::I64}; },
            "entry prefix");
        reject(
            "parameter rebound after call",
            [](Module &m) {
                auto &f = m.functions[0];
                f.parameters = {Type::Bool};
                f.slots[8] = Type::Bool;
                f.code = {BindParameter{0, 8, Type::Bool}, Constant{42, Type::I64},
                          MetadataQuery{Query::Size},      BindParameter{0, 8, Type::Bool},
                          Constant{42, Type::I64},         Return{}};
            },
            "outside entry prefix");
        reject(
            "unknown call",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin(), Call{"missing"});
            },
            "unknown call");
        reject(
            "bad unary enum",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.end() - 1,
                                           UnaryValue{static_cast<Unary>(99)});
            },
            "invalid unary");
        reject(
            "bad binary enum",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.end() - 1,
                                           BinaryValue{static_cast<Binary>(99)});
            },
            "invalid binary");
        reject(
            "bad query enum",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.end() - 1,
                                           MetadataQuery{static_cast<Query>(99)});
            },
            "unknown metadata");
        reject(
            "bad descriptor", [](Module &m) { m.descriptors[-1] = Descriptor{8, 0}; },
            "invalid metadata");
        reject(
            "borrow uninitialized payload",
            [](Module &m) {
                m.functions[0].code = {BorrowHandle{8, Type::Ref}, Constant{42, Type::I64},
                                       Return{}};
            },
            "uninitialized payload");
        reject(
            "unchecked index",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.end() - 1,
                                           IndexLoad{8, 1, Type::I64});
            },
            "bounds token");
        reject(
            "guard invalidated by value change",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.end() - 1,
                                           {Constant{0, Type::I64}, BoundsGuard{8, 1, Type::I64},
                                            Constant{1, Type::I64}, IndexLoad{8, 1, Type::I64}});
            },
            "bounds token");
        reject(
            "guard wrong length",
            [](Module &m) {
                auto &f = m.functions[0];
                f.slots[16] = Type::I64;
                f.code = {Constant{42, Type::I64},
                          Store{8, Type::I64},
                          Store{16, Type::I64},
                          Constant{0, Type::I64},
                          BoundsGuard{16, 2, Type::I64},
                          IndexLoad{16, 1, Type::I64},
                          Return{}};
            },
            "bounds token");
        reject(
            "guard wrong base",
            [](Module &m) {
                auto &f = m.functions[0];
                f.slots[16] = Type::I64;
                f.code = {Constant{42, Type::I64},
                          Store{8, Type::I64},
                          Store{16, Type::I64},
                          Constant{0, Type::I64},
                          BoundsGuard{16, 1, Type::I64},
                          IndexLoad{8, 1, Type::I64},
                          Return{}};
            },
            "bounds token");
        reject(
            "guard bypass through branch",
            [](Module &m) {
                m.functions[0].code = {Constant{42, Type::I64},
                                       Store{8, Type::I64},
                                       Constant{1, Type::Bool},
                                       BranchFalse{1},
                                       Constant{0, Type::I64},
                                       BoundsGuard{8, 1, Type::I64},
                                       Jump{2},
                                       Label{1},
                                       Constant{0, Type::I64},
                                       Label{2},
                                       IndexLoad{8, 1, Type::I64},
                                       Return{}};
            },
            "mistyped current");
        reject(
            "partial array initialization",
            [](Module &m) {
                auto &f = m.functions[0];
                f.slots[16] = Type::I64;
                f.code = {Constant{42, Type::I64},     Store{8, Type::I64},
                          Constant{0, Type::I64},      BoundsGuard{16, 2, Type::I64},
                          IndexLoad{16, 2, Type::I64}, Return{}};
            },
            "array element not initialized");
        reject(
            "array layout underflow",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.end() - 1,
                                           BoundsGuard{8, 2, Type::I64});
            },
            "layout underflow");
        reject(
            "store without checked index",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.end() - 1,
                                           {Push{}, IndexStore{8, 1, Type::I64}});
            },
            "bounds token");
        reject(
            "initialization missing branch",
            [](Module &m) {
                m.functions[0].code = {Constant{1, Type::Bool},
                                       BranchFalse{1},
                                       Constant{42, Type::I64},
                                       Store{8, Type::I64},
                                       Label{1},
                                       Load{8, Type::I64},
                                       Return{}};
            },
            "load before initialization");
        reject(
            "loop backedge loses current guard",
            [](Module &m) {
                m.functions[0].code = {Constant{42, Type::I64},
                                       Store{8, Type::I64},
                                       Constant{0, Type::I64},
                                       BoundsGuard{8, 1, Type::I64},
                                       Label{1},
                                       IndexLoad{8, 1, Type::I64},
                                       Constant{0, Type::I64},
                                       Jump{1}};
            },
            "mistyped current");
        reject(
            "late predecessor removes initialization",
            [](Module &m) {
                m.functions[0].code = {Constant{1, Type::Bool},
                                       BranchFalse{1},
                                       Label{2},
                                       Jump{4},
                                       Label{1},
                                       Constant{42, Type::I64},
                                       Store{8, Type::I64},
                                       Jump{3},
                                       Label{4},
                                       Jump{3},
                                       Label{3},
                                       Load{8, Type::I64},
                                       Return{}};
            },
            "load before initialization");
        auto joinedGuard = baseline();
        joinedGuard.functions[0].code = {Constant{42, Type::I64},
                                         Store{8, Type::I64},
                                         Constant{1, Type::Bool},
                                         BranchFalse{1},
                                         Constant{0, Type::I64},
                                         BoundsGuard{8, 1, Type::I64},
                                         Jump{2},
                                         Label{1},
                                         Constant{0, Type::I64},
                                         BoundsGuard{8, 1, Type::I64},
                                         Label{2},
                                         IndexLoad{8, 1, Type::I64},
                                         Return{}};
        accept("identical guards join safely", std::move(joinedGuard));

        // Portable resource regression: bound retained abstract facts, not wall time or
        // platform-specific RSS. A maximum-size straight-line initializer must not
        // snapshot its growing operand stack / initialized set after every instruction.
        constexpr int elementCount = 4096;
        auto large = baseline();
        auto &largeFunction = large.functions[0];
        largeFunction.frameBytes = elementCount * 8;
        largeFunction.slots.clear();
        largeFunction.code.clear();
        for (int index = 0; index < elementCount; ++index) {
            largeFunction.slots[(index + 1) * 8] = Type::I64;
            largeFunction.code.push_back(Constant{1, Type::I64});
            largeFunction.code.push_back(Push{});
        }
        for (int index = 0; index < elementCount; ++index) {
            largeFunction.code.push_back(Pop{});
            largeFunction.code.push_back(Store{(index + 1) * 8, Type::I64});
        }
        largeFunction.code.insert(largeFunction.code.end(),
                                  {Constant{elementCount - 1, Type::I64},
                                   BoundsGuard{elementCount * 8, elementCount, Type::I64},
                                   IndexLoad{elementCount * 8, elementCount, Type::I64}, Return{}});
        std::map<std::string, const aurora::ir::Function *> largeFunctions{
            {"test", &largeFunction}};
        verification::Metrics metrics;
        verification::verifyFunction(largeFunction, largeFunctions, &metrics);
        if (metrics.peakOperandDepth != elementCount || metrics.snapshots > 8 ||
            metrics.peakRetainedValueFacts > elementCount * 16)
            throw Error("maximum initializer retained non-linear verifier state");
        ++passed;
        std::cout << "PASS IR bounded maximum initializer: snapshots=" << metrics.snapshots
                  << ", peak operand depth=" << metrics.peakOperandDepth
                  << ", retained facts=" << metrics.peakRetainedValueFacts << '\n';
        auto guarded = baseline();
        guarded.functions[0].code.insert(guarded.functions[0].code.end() - 1,
                                         {Constant{0, Type::I64}, BoundsGuard{8, 1, Type::I64},
                                          Push{}, Constant{42, Type::I64},
                                          MetadataQuery{Query::Size}, IndexStore{8, 1, Type::I64}});
        accept("saved guard survives RHS query", std::move(guarded));
        auto structural = baseline();
        structural.functions[0].code.push_back(Jump{1});
        structural.functions[0].code.push_back(Label{1});
        auto checked = validate(std::move(structural));
        if (checked.get().functions[0].code.size() != 4)
            throw Error("unreachable structural cleanup failed");
        ++passed;
        std::cout << "PASS IR unreachable structural cleanup\n";
        std::cout << passed << " typed IR tests passed\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
