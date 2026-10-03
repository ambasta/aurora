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
void rejectModule(const std::string &name, Module module,
                  const std::function<void(Module &)> &mutate, const std::string &expected) {
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
void reject(const std::string &name, const std::function<void(Module &)> &mutate,
            const std::string &expected) {
    rejectModule(name, baseline(), mutate, expected);
}
Module receiverBaseline() {
    Module module;
    module.classLayouts["Pair"] = {Type::I64, Type::Bool};
    aurora::ir::Function caller;
    caller.name = "test";
    caller.result = Type::I64;
    caller.frameBytes = 16;
    caller.slots = {{16, Type::I64}, {8, Type::Bool}};
    caller.objectSlots[16] = ObjectSlot{"Pair", false};
    caller.code = {BeginObject{16}, Constant{42, Type::I64}, Push{}, Constant{1, Type::Bool}, Push{},
                   MethodCall{"construct_pair", 16}, MethodCall{"relay_pair", 16}, Return{}};
    aurora::ir::Function constructor;
    constructor.name = "construct_pair";
    constructor.result = Type::I64;
    constructor.parameters = {Type::I64, Type::Bool};
    constructor.frameBytes = 16;
    constructor.slots = {{8, Type::I64}, {16, Type::Bool}};
    constructor.receiver = Receiver{"Pair", true, true};
    constructor.code = {BindParameter{0, 8, Type::I64}, BindParameter{1, 16, Type::Bool},
                        Load{8, Type::I64}, ReceiverStore{0, Type::I64},
                        Load{16, Type::Bool}, ReceiverStore{1, Type::Bool},
                        Constant{0, Type::I64}, Return{}};
    aurora::ir::Function getter;
    getter.name = "get_pair";
    getter.result = Type::I64;
    getter.receiver = Receiver{"Pair", false, false};
    getter.code = {ReceiverLoad{0, Type::I64}, Return{}};
    auto relay = getter;
    relay.name = "relay_pair";
    relay.code = {MethodCall{"get_pair", 0}, Return{}};
    module.functions = {caller, constructor, getter, relay};
    return module;
}
void rejectReceiver(const std::string &name, const std::function<void(Module &)> &mutate,
                    const std::string &expected) {
    rejectModule(name, receiverBaseline(), mutate, expected);
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

        accept("constructor, const object and receiver forwarding", receiverBaseline());
        rejectReceiver("missing class layout", [](Module &m) { m.classLayouts.clear(); },
                       "unknown object class");
        rejectReceiver("non-scalar class layout", [](Module &m) {
            m.classLayouts["Pair"][0] = Type::Ref;
        }, "non-scalar class layout");
        rejectReceiver("unknown bound receiver nominal type", [](Module &m) {
            m.functions[2].receiver->className = "Unknown";
        }, "unknown receiver class");
        rejectReceiver("forged object type", [](Module &m) {
            m.classLayouts["Other"] = m.classLayouts["Pair"];
            m.functions[0].objectSlots[16].className = "Other";
        }, "nominal class mismatch");
        rejectReceiver("forged object scalar layout", [](Module &m) {
            m.functions[0].slots[8] = Type::I64;
        }, "object field slot type/layout mismatch");
        rejectReceiver("missing object field slot", [](Module &m) {
            m.functions[0].slots.erase(8);
        }, "object field slot type/layout mismatch");
        rejectReceiver("overlapping object layouts", [](Module &m) {
            m.classLayouts["Small"] = {Type::Bool};
            m.functions[0].objectSlots[8] = ObjectSlot{"Small", true};
        }, "overlapping object layouts");
        rejectReceiver("object base underflows layout", [](Module &m) {
            m.functions[0].objectSlots.clear();
            m.functions[0].objectSlots[8] = ObjectSlot{"Pair", true};
        }, "invalid object layout offset");
        rejectReceiver("object base outside frame", [](Module &m) {
            m.functions[0].objectSlots[24] = ObjectSlot{"Pair", true};
        }, "invalid object layout offset");
        rejectReceiver("receiver load without bound receiver", [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin(), ReceiverLoad{0, Type::I64});
        }, "without bound receiver");
        rejectReceiver("receiver store without bound receiver", [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 2,
                                      ReceiverStore{0, Type::I64});
        }, "without bound receiver");
        rejectReceiver("negative receiver field", [](Module &m) {
            m.functions[2].code[0] = ReceiverLoad{-1, Type::I64};
        }, "receiver field type/layout");
        rejectReceiver("receiver field past layout", [](Module &m) {
            m.functions[2].code[0] = ReceiverLoad{2, Type::I64};
        }, "receiver field type/layout");
        rejectReceiver("receiver field type forged", [](Module &m) {
            m.functions[2].code[0] = ReceiverLoad{1, Type::I64};
        }, "receiver field type/layout");
        rejectReceiver("receiver cannot become scalar", [](Module &m) {
            m.functions[2].code[0] = ReceiverLoad{0, Type::Ref};
        }, "receiver field type/layout");
        rejectReceiver("receiver write through readonly capability", [](Module &m) {
            m.functions[2].code = {Constant{42, Type::I64}, ReceiverStore{0, Type::I64}, Return{}};
        }, "write through const receiver");
        rejectReceiver("scalar call receiver bypass", [](Module &m) {
            m.functions[0].code[6] = Call{"get_pair"};
        }, "plain call cannot target receiver");
        rejectReceiver("method call scalar target", [](Module &m) {
            m.functions[0].code[6] = MethodCall{"test", 16};
        }, "method call requires receiver target");
        rejectReceiver("unknown method", [](Module &m) {
            m.functions[0].code[6] = MethodCall{"missing", 16};
        }, "unknown method call target");
        rejectReceiver("method requires exact object base", [](Module &m) {
            m.functions[0].code[6] = MethodCall{"get_pair", 8};
        }, "not an object slot");
        rejectReceiver("method rejects negative base", [](Module &m) {
            m.functions[0].code[6] = MethodCall{"get_pair", -16};
        }, "invalid method receiver offset");
        rejectReceiver("receiver cannot alias arbitrary scalar", [](Module &m) {
            m.functions[0].objectSlots.clear();
            m.functions[0].code.erase(m.functions[0].code.begin());
        }, "not an object slot");
        rejectReceiver("forwarding requires receiver", [](Module &m) {
            m.functions[0].code[6] = MethodCall{"get_pair", 0};
        }, "forwarding without bound receiver");
        rejectReceiver("forwarding preserves nominal identity", [](Module &m) {
            m.classLayouts["Other"] = m.classLayouts["Pair"];
            m.functions[2].receiver->className = "Other";
        }, "forwarded receiver nominal class mismatch");
        rejectReceiver("const receiver cannot forward exclusively", [](Module &m) {
            m.functions[2].receiver->mutableValue = true;
        }, "const receiver cannot forward mutable");
        rejectReceiver("const local cannot supply mutable receiver", [](Module &m) {
            m.functions[3].receiver->mutableValue = true;
        }, "const object cannot supply mutable");
        rejectReceiver("constructor requires mutable receiver", [](Module &m) {
            m.functions[1].receiver->mutableValue = false;
        }, "invalid constructor receiver signature");
        rejectReceiver("constructor requires i64 internal result", [](Module &m) {
            m.functions[1].result = Type::Bool;
        }, "invalid constructor receiver signature");
        rejectReceiver("constructor missing field", [](Module &m) {
            m.functions[1].code.erase(m.functions[1].code.begin() + 4,
                                       m.functions[1].code.begin() + 6);
        }, "before all fields initialized");
        rejectReceiver("constructor duplicate field", [](Module &m) {
            m.functions[1].code.insert(m.functions[1].code.begin() + 4,
                                      ReceiverStore{0, Type::I64});
        }, "field initialized more than once");
        rejectReceiver("constructor receiver read even after final write", [](Module &m) {
            m.functions[1].code[6] = ReceiverLoad{0, Type::I64};
        }, "constructor cannot read receiver");
        rejectReceiver("constructor cannot forward receiver", [](Module &m) {
            m.functions[1].code[6] = MethodCall{"get_pair", 0};
        }, "constructor cannot forward receiver");
        rejectReceiver("ordinary method cannot forward as constructor", [](Module &m) {
            m.functions[3].code = {Constant{42, Type::I64}, Push{},
                                   Constant{1, Type::Bool}, Push{},
                                   MethodCall{"construct_pair", 0}, Return{}};
        }, "constructor cannot forward receiver");
        rejectReceiver("method requires full object initialization", [](Module &m) {
            m.functions[0].code = {BeginObject{16}, Constant{42, Type::I64}, Store{16, Type::I64},
                                   MethodCall{"get_pair", 16}, Return{}};
        }, "object not fully initialized");
        rejectReceiver("constructor rejects partially initialized object", [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 2, Store{16, Type::I64});
        }, "requires uninitialized object");
        rejectReceiver("constructor cannot run twice", [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 6,
                                      {Constant{42, Type::I64}, Push{},
                                       Constant{1, Type::Bool}, Push{},
                                       MethodCall{"construct_pair", 16}});
        }, "constructor called more than once");
        rejectReceiver("constructor argument type", [](Module &m) {
            m.functions[0].code[3] = Constant{1, Type::I64};
        }, "method argument type mismatch");
        rejectReceiver("constructor argument underflow", [](Module &m) {
            m.functions[0].code.erase(m.functions[0].code.begin() + 4);
        }, "method argument type mismatch");
        rejectReceiver("const object field direct overwrite", [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 6, Store{16, Type::I64});
        }, "write to initialized const object");
        rejectReceiver("const object field indexed overwrite", [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 6,
                                      {Constant{0, Type::I64}, BoundsGuard{16, 1, Type::I64},
                                       Push{}, Constant{1, Type::I64}, IndexStore{16, 1, Type::I64}});
        }, "indexed write to const object");
        rejectReceiver("object cannot forge scalar borrow capability", [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 6, BorrowHandle{16, Type::Ref});
        }, "object field cannot become a scalar borrow handle");
        rejectReceiver("parameter cannot alias object", [](Module &m) {
            auto &f = m.functions[0];
            f.parameters = {Type::I64};
            f.code.insert(f.code.begin(), BindParameter{0, 16, Type::I64});
        }, "parameter cannot bind object field");
        rejectReceiver("self-recursive receiver", [](Module &m) {
            m.functions[2].code = {MethodCall{"get_pair", 0}, Return{}};
        }, "recursive receiver call cycle");
        rejectReceiver("mutually recursive receivers", [](Module &m) {
            m.functions[2].code = {MethodCall{"relay_pair", 0}, Return{}};
        }, "recursive receiver call cycle");
        rejectReceiver("receiver recursion through scalar intermediary", [](Module &m) {
            m.functions[2].code = {Call{"test"}, Return{}};
        }, "recursive receiver call cycle");
        rejectReceiver("unreachable receiver instruction", [](Module &m) {
            m.functions[2].code.push_back(ReceiverStore{0, Type::I64});
        }, "unreachable semantic instruction");
        rejectReceiver("constructor conditional field omitted", [](Module &m) {
            m.functions[1].code = {BindParameter{0, 8, Type::I64}, BindParameter{1, 16, Type::Bool},
                                  Constant{1, Type::Bool}, BranchFalse{1},
                                  Constant{42, Type::I64}, ReceiverStore{0, Type::I64},
                                  Label{1}, Constant{1, Type::Bool}, ReceiverStore{1, Type::Bool},
                                  Constant{0, Type::I64}, Return{}};
        }, "before all fields initialized");
        rejectReceiver("constructor conditional duplicate field", [](Module &m) {
            m.functions[1].code = {BindParameter{0, 8, Type::I64}, BindParameter{1, 16, Type::Bool},
                                  Constant{1, Type::Bool}, BranchFalse{1},
                                  Constant{42, Type::I64}, ReceiverStore{0, Type::I64},
                                  Label{1}, Constant{42, Type::I64}, ReceiverStore{0, Type::I64},
                                  Constant{1, Type::Bool}, ReceiverStore{1, Type::Bool},
                                  Constant{0, Type::I64}, Return{}};
        }, "field initialized more than once");
        rejectReceiver("constructor loop duplicate field", [](Module &m) {
            m.functions[1].code = {BindParameter{0, 8, Type::I64}, BindParameter{1, 16, Type::Bool},
                                  Label{1}, Constant{42, Type::I64}, ReceiverStore{0, Type::I64},
                                  Constant{1, Type::Bool}, BranchFalse{1},
                                  ReceiverStore{1, Type::Bool}, Constant{0, Type::I64}, Return{}};
        }, "field initialized more than once");
        rejectReceiver("conditional object initialization before construction", [](Module &m) {
            auto &f = m.functions[0];
            f.objectSlots[16].mutableValue = true;
            f.code.insert(f.code.begin() + 1, {Constant{1, Type::Bool}, BranchFalse{1},
                                          Constant{42, Type::I64}, Store{16, Type::I64}, Label{1}});
        }, "requires uninitialized object");
        auto aggregateReceiver = receiverBaseline();
        aggregateReceiver.functions[0].code = {BeginObject{16}, Constant{42, Type::I64}, Store{16, Type::I64},
                                               Constant{1, Type::Bool}, Store{8, Type::Bool},
                                               MethodCall{"get_pair", 16}, Return{}};
        accept("fully initialized aggregate supplies receiver", aggregateReceiver);
        auto mutableReceiver = receiverBaseline();
        mutableReceiver.functions[0].objectSlots[16].mutableValue = true;
        mutableReceiver.functions[3].receiver->mutableValue = true;
        mutableReceiver.functions[3].code = {Constant{41, Type::I64}, ReceiverStore{0, Type::I64},
                                             Constant{42, Type::I64}, ReceiverStore{0, Type::I64},
                                             MethodCall{"get_pair", 0}, Return{}};
        accept("mutable receiver reborrow downgrades and returns", mutableReceiver);
        auto scalarHelper = receiverBaseline();
        auto helper = baseline().functions[0];
        helper.name = "helper";
        scalarHelper.functions.push_back(helper);
        scalarHelper.functions[2].code.insert(scalarHelper.functions[2].code.begin(), Call{"helper"});
        accept("receiver function ordinary scalar helper", scalarHelper);
        auto scalarRecursive = baseline();
        scalarRecursive.functions[0].code.insert(scalarRecursive.functions[0].code.begin(), Call{"test"});
        accept("pure scalar recursion stays supported", scalarRecursive);
        auto branchConstructor = receiverBaseline();
        branchConstructor.functions[1].code = {
            BindParameter{0, 8, Type::I64}, BindParameter{1, 16, Type::Bool},
            Constant{1, Type::Bool}, BranchFalse{1},
            Constant{42, Type::I64}, ReceiverStore{0, Type::I64}, Jump{2},
            Label{1}, Constant{42, Type::I64}, ReceiverStore{0, Type::I64},
            Label{2}, Constant{1, Type::Bool}, ReceiverStore{1, Type::Bool},
            Constant{0, Type::I64}, Return{}};
        accept("constructor disjoint branch initialization", branchConstructor);
        auto emptyReceiver = receiverBaseline();
        emptyReceiver.classLayouts["Pair"].clear();
        emptyReceiver.functions[0].slots.clear();
        emptyReceiver.functions[1].code = {BindParameter{0, 8, Type::I64},
                                           BindParameter{1, 16, Type::Bool},
                                           Constant{0, Type::I64}, Return{}};
        emptyReceiver.functions[2].code = {Constant{42, Type::I64}, Return{}};
        accept("empty object reserves private receiver storage", emptyReceiver);
        rejectModule("empty object constructor cannot repeat", emptyReceiver, [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 6,
                                      {Constant{42, Type::I64}, Push{}, Constant{1, Type::Bool},
                                       Push{}, MethodCall{"construct_pair", 16}});
        }, "constructor called more than once");
        rejectModule("empty object cannot alias scalar slot", emptyReceiver, [](Module &m) {
            m.functions[0].slots[16] = Type::I64;
        }, "scalar slot overlaps empty object");
        rejectReceiver("object method before lifetime begin", [](Module &m) {
            m.functions[0].code.erase(m.functions[0].code.begin());
        }, "outside active object lifetime");
        rejectReceiver("object field store before lifetime begin", [](Module &m) {
            m.functions[0].code = {Constant{42, Type::I64}, Store{16, Type::I64}, Return{}};
        }, "outside active lifetime");
        rejectReceiver("object field load after lifetime end", [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 6,
                                      {EndObject{16}, Load{16, Type::I64}});
        }, "outside active lifetime");
        rejectReceiver("object indexed access after lifetime end", [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 6,
                                      {EndObject{16}, Constant{0, Type::I64},
                                       BoundsGuard{16, 1, Type::I64}});
        }, "outside active lifetime");
        rejectReceiver("object method after lifetime end", [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 6, EndObject{16});
        }, "outside active object lifetime");
        rejectReceiver("object double begin", [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin(), BeginObject{16});
        }, "lifetime already active");
        rejectReceiver("object end before begin", [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin(), EndObject{16});
        }, "lifetime is not active");
        rejectReceiver("object double end", [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 6,
                                      {EndObject{16}, EndObject{16}});
        }, "lifetime is not active");
        rejectReceiver("object begin requires exact base", [](Module &m) {
            m.functions[0].code[0] = BeginObject{8};
        }, "lifetime operation requires exact object slot");
        rejectReceiver("object end requires exact base", [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 6, EndObject{8});
        }, "lifetime operation requires exact object slot");
        rejectReceiver("new lifetime cannot inherit initialized fields", [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 6,
                                      {EndObject{16}, BeginObject{16}});
        }, "object not fully initialized");
        rejectReceiver("branch cannot skip lifetime end", [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.end() - 1,
                                      {Constant{1, Type::Bool}, BranchFalse{1},
                                       EndObject{16}, Label{1}, Constant{42, Type::I64}});
        }, "incompatible active object lifetimes");
        rejectReceiver("branch cannot skip lifetime begin", [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin(),
                                      {Constant{1, Type::Bool}, BranchFalse{1}, Jump{2},
                                       Label{1}, BeginObject{16}, Label{2}});
        }, "incompatible active object lifetimes");
        rejectReceiver("loop cannot silently restart active object", [](Module &m) {
            auto &code = m.functions[0].code;
            code.insert(code.begin(), Label{1});
            code.insert(code.end() - 1, {Constant{1, Type::Bool}, BranchFalse{1},
                                        Constant{42, Type::I64}});
        }, "incompatible active object lifetimes");
        auto lifetimeReuse = receiverBaseline();
        lifetimeReuse.functions[0].code.insert(lifetimeReuse.functions[0].code.begin() + 6,
            {EndObject{16}, BeginObject{16}, Constant{42, Type::I64}, Push{},
             Constant{1, Type::Bool}, Push{}, MethodCall{"construct_pair", 16}});
        accept("new lifetime permits constructing same storage again", lifetimeReuse);
        auto lifetimeLoop = receiverBaseline();
        lifetimeLoop.functions[0].code.insert(lifetimeLoop.functions[0].code.begin(), Label{1});
        lifetimeLoop.functions[0].code.insert(lifetimeLoop.functions[0].code.end() - 1,
            {EndObject{16}, Constant{1, Type::Bool}, BranchFalse{1}, Constant{42, Type::I64}});
        accept("const constructor object lifetime ends before loop backedge", lifetimeLoop);
        auto aggregateLoop = aggregateReceiver;
        aggregateLoop.functions[0].code.insert(aggregateLoop.functions[0].code.begin(), Label{1});
        aggregateLoop.functions[0].code.insert(aggregateLoop.functions[0].code.end() - 1,
            {EndObject{16}, Constant{1, Type::Bool}, BranchFalse{1}, Constant{42, Type::I64}});
        accept("const aggregate object lifetime ends before loop backedge", aggregateLoop);
        auto sixArguments = receiverBaseline();
        auto &six = sixArguments.functions[3];
        six.parameters = std::vector<Type>(6, Type::I64);
        six.frameBytes = 48;
        six.code.clear();
        for (int index = 0; index < 6; ++index) {
            six.slots[(index + 1) * 8] = Type::I64;
            six.code.push_back(BindParameter{index, (index + 1) * 8, Type::I64});
        }
        six.code.insert(six.code.end(), {MethodCall{"get_pair", 0}, Return{}});
        auto &sixCaller = sixArguments.functions[0];
        sixCaller.code.insert(sixCaller.code.begin() + 6,
            {Constant{99, Type::I64}, Push{}, Constant{1, Type::I64}, Push{},
             Constant{2, Type::I64}, Push{}, Constant{3, Type::I64}, Push{},
             Constant{4, Type::I64}, Push{}, Constant{5, Type::I64}, Push{},
             Constant{6, Type::I64}, Push{}});
        sixCaller.code.insert(sixCaller.code.end() - 1, Pop{});
        accept("six scalar method arguments with odd live operand depth", sixArguments);
        const auto receiverAssembly = X86Emitter{}.emit(validate(receiverBaseline()));
        if (receiverAssembly.find(".local construct_pair") == std::string::npos ||
            receiverAssembly.find("movq %r10, -24(%rbp)") == std::string::npos ||
            receiverAssembly.find("movq -8(%rbp), %r10") == std::string::npos ||
            receiverAssembly.find("leaq -16(%rbp), %r10") == std::string::npos ||
            receiverAssembly.find("movq %rax, 8(%r10)") == std::string::npos)
            throw Error("private receiver ABI emission mismatch");
        ++passed;
        std::cout << "PASS IR private receiver ABI frame and field layout\n";

        // Call-graph validation must use bounded heap storage rather than one
        // host call-stack frame per source function, including scalar bridges.
        auto deepCalls = receiverBaseline();
        constexpr int helperCount = 4096;
        deepCalls.functions[2].code = {Call{"deep_helper0"}, Return{}};
        for (int index = 0; index < helperCount; ++index) {
            aurora::ir::Function helperFunction;
            helperFunction.name = "deep_helper" + std::to_string(index);
            helperFunction.result = Type::I64;
            if (index + 1 < helperCount)
                helperFunction.code = {Call{"deep_helper" + std::to_string(index + 1)}, Return{}};
            else
                helperFunction.code = {Constant{42, Type::I64}, Return{}};
            deepCalls.functions.push_back(std::move(helperFunction));
        }
        accept("deep receiver-to-scalar call graph uses iterative verification", deepCalls);
        rejectModule("deep scalar bridge cannot hide receiver cycle", deepCalls, [](Module &m) {
            const auto name = m.functions.back().name;
            m.functions.back() = m.functions[0];
            m.functions.back().name = name;
        }, "recursive receiver call cycle");
        deepCalls.functions.back().code = {Call{"deep_helper0"}, Return{}};
        accept("receiver may call a pure scalar recursive component", deepCalls);

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
        reject(
            "query cannot change module view",
            [](Module &m) {
                m.descriptorViews[1] = {};
                m.functions[0].code.insert(m.functions[0].code.end() - 1,
                                           MetadataQuery{Query::Size, 1});
            },
            "changes defining-module scope");
        reject(
            "unknown function module view", [](Module &m) { m.functions[0].moduleScope = 1; },
            "unknown function module scope");
        reject(
            "view cannot name missing descriptor",
            [](Module &m) { m.descriptorViews[0].insert(999); }, "missing descriptor");
        reject(
            "module view scope cap", [](Module &m) { m.descriptorViews[64] = {}; },
            "invalid reflection scope");
        reject(
            "scoped helper name reserved",
            [](Module &m) { m.functions[0].name = "__au_reflect_s1_size"; }, "function symbol");
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
