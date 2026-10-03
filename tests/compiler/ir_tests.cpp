#include "ir_verify.hpp"
#include "x86.hpp"
#include <bit>
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
    caller.code = {BeginObject{16},
                   Constant{42, Type::I64},
                   Push{},
                   Constant{1, Type::Bool},
                   Push{},
                   MethodCall{"construct_pair", 16},
                   MethodCall{"relay_pair", 16},
                   Return{}};
    aurora::ir::Function constructor;
    constructor.name = "construct_pair";
    constructor.result = Type::I64;
    constructor.parameters = {Type::I64, Type::Bool};
    constructor.frameBytes = 16;
    constructor.slots = {{8, Type::I64}, {16, Type::Bool}};
    constructor.receiver = Receiver{"Pair", true, true};
    constructor.code = {BindParameter{0, 8, Type::I64},
                        BindParameter{1, 16, Type::Bool},
                        Load{8, Type::I64},
                        ReceiverStore{0, Type::I64},
                        Load{16, Type::Bool},
                        ReceiverStore{1, Type::Bool},
                        Constant{0, Type::I64},
                        Return{}};
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
Module valueBaseline() {
    Module module;
    module.classLayouts["Pair"] = {Type::I64, Type::Bool};
    aurora::ir::Function caller;
    caller.name = "test";
    caller.result = Type::I64;
    caller.frameBytes = 48;
    caller.slots = {{16, Type::I64},  {8, Type::Bool}, {32, Type::I64},
                    {24, Type::Bool}, {48, Type::I64}, {40, Type::Bool}};
    caller.objectSlots = {{16, ObjectSlot{"Pair", false}},
                          {32, ObjectSlot{"Pair", false}},
                          {48, ObjectSlot{"Pair", false}}};
    caller.code = {BeginObject{16},         Constant{12, Type::I64},
                   Store{16, Type::I64},    Constant{1, Type::Bool},
                   Store{8, Type::Bool},    BeginObject{32},
                   Constant{20, Type::I64}, Store{32, Type::I64},
                   Constant{0, Type::Bool}, Store{24, Type::Bool},
                   Constant{10, Type::I64}, Push{},
                   Constant{1, Type::Bool}, Push{},
                   BeginObject{48},         AggregateCall{"copy_pair", {16, 0, 32, 0}, 48},
                   Load{48, Type::I64},     Return{}};
    aurora::ir::Function copy;
    copy.name = "copy_pair";
    copy.result = Type("Pair");
    copy.parameters = {Type("Pair"), Type::I64, Type("Pair"), Type::Bool};
    copy.frameBytes = 64;
    copy.slots = {{16, Type::I64},  {8, Type::Bool},  {24, Type::I64}, {40, Type::I64},
                  {32, Type::Bool}, {48, Type::Bool}, {64, Type::I64}, {56, Type::Bool}};
    copy.objectSlots = {{16, ObjectSlot{"Pair", false}},
                        {40, ObjectSlot{"Pair", false}},
                        {64, ObjectSlot{"Pair", false}}};
    copy.code = {BindObjectParameter{0, 16, "Pair"},
                 BindParameter{1, 24, Type::I64},
                 BindObjectParameter{2, 40, "Pair"},
                 BindParameter{3, 48, Type::Bool},
                 BeginObject{64},
                 Load{16, Type::I64},
                 Push{},
                 Load{24, Type::I64},
                 BinaryValue{Binary::CheckedAdd},
                 Push{},
                 Load{40, Type::I64},
                 BinaryValue{Binary::CheckedAdd},
                 Store{64, Type::I64},
                 Load{48, Type::Bool},
                 Store{56, Type::Bool},
                 ReturnObject{64}};
    module.functions = {caller, copy};
    return module;
}
AggregateCall &valueCall(Module &module) {
    for (auto &instruction : module.functions[0].code)
        if (auto *call = std::get_if<AggregateCall>(&instruction))
            return *call;
    throw Error("missing aggregate test call");
}
void rejectValue(const std::string &name, const std::function<void(Module &)> &mutate,
                 const std::string &expected) {
    rejectModule(name, valueBaseline(), mutate, expected);
}
Module emptyValueBaseline() {
    Module module;
    module.classLayouts["Empty"] = {};
    aurora::ir::Function entry;
    entry.name = "test";
    entry.result = Type::I64;
    entry.frameBytes = 16;
    entry.objectSlots = {{8, ObjectSlot{"Empty", false}}, {16, ObjectSlot{"Empty", false}}};
    entry.code = {BeginObject{8}, BeginObject{16}, AggregateCall{"copy_empty", {8}, 16},
                  Constant{42, Type::I64}, Return{}};
    aurora::ir::Function copy;
    copy.name = "copy_empty";
    copy.result = Type("Empty");
    copy.parameters = {Type("Empty")};
    copy.frameBytes = 16;
    copy.objectSlots[8] = ObjectSlot{"Empty", false};
    copy.code = {BindObjectParameter{0, 8, "Empty"}, ReturnObject{8}};
    auto make = copy;
    make.name = "make_empty";
    make.parameters.clear();
    make.code = {BeginObject{8}, ReturnObject{8}};
    module.functions = {entry, copy, make};
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
Module unsignedBinary(Binary operation) {
    auto module = baseline();
    auto &function = module.functions[0];
    function.result = Type::U64;
    const bool shift = operation == Binary::ShiftLeft || operation == Binary::ShiftRight;
    function.code = {Constant{std::bit_cast<std::int64_t>(UINT64_MAX), Type::U64}, Push{},
                     Constant{shift ? 0 : 1, shift ? Type::I64 : Type::U64},
                     BinaryValue{operation, Type::U64}, Return{}};
    return module;
}
Module unsignedOperations() {
    Module module;
    int index = 0;
    for (const auto operation :
         {Binary::CheckedAdd, Binary::CheckedSubtract, Binary::CheckedMultiply,
          Binary::CheckedDivide, Binary::CheckedRemainder, Binary::BitAnd, Binary::BitOr,
          Binary::BitXor, Binary::ShiftLeft, Binary::ShiftRight}) {
        const bool shift = operation == Binary::ShiftLeft || operation == Binary::ShiftRight;
        const auto right = shift ? Type::I64 : Type::U64;
        auto function = unsignedBinary(operation).functions[0];
        function.name = "unsigned_op" + std::to_string(index++);
        function.parameters = {Type::U64, right};
        function.slots = {{8, Type::U64}, {16, right}};
        function.code = {BindParameter{0, 8, Type::U64},
                         BindParameter{1, 16, right},
                         Load{8, Type::U64},
                         Push{},
                         Load{16, right},
                         BinaryValue{operation, Type::U64},
                         Return{}};
        module.functions.push_back(std::move(function));
    }
    for (const auto operation :
         {Comparison::Equal, Comparison::NotEqual, Comparison::Less, Comparison::Greater,
          Comparison::LessEqual, Comparison::GreaterEqual}) {
        auto function = module.functions[0];
        function.name = "unsigned_compare" + std::to_string(static_cast<int>(operation));
        function.result = Type::Bool;
        function.code[5] = Compare{operation, Type::U64};
        module.functions.push_back(std::move(function));
    }
    auto function = module.functions[0];
    function.name = "unsigned_not";
    function.parameters = {Type::U64};
    function.code = {BindParameter{0, 8, Type::U64}, Load{8, Type::U64}, UnaryValue{Unary::BitNot},
                     Return{}};
    module.functions.push_back(function);
    for (const auto &source : {Type::I64, Type::U64}) {
        function.name = source == Type::I64 ? "signed_to_unsigned" : "unsigned_to_signed";
        function.result = source == Type::I64 ? Type::U64 : Type::I64;
        function.parameters = {source};
        function.slots = {{8, source}};
        function.code = {BindParameter{0, 8, source}, Load{8, source},
                         Convert{source, function.result}, Return{}};
        module.functions.push_back(function);
    }
    return module;
}
void unsignedTests() {
    accept("unsigned operation callable fixture", unsignedOperations());
    for (const auto operation :
         {Binary::CheckedAdd, Binary::CheckedSubtract, Binary::CheckedMultiply,
          Binary::CheckedDivide, Binary::CheckedRemainder, Binary::BitAnd, Binary::BitOr,
          Binary::BitXor, Binary::ShiftLeft, Binary::ShiftRight}) {
        const auto name = "u64 binary " + std::to_string(static_cast<int>(operation));
        const auto module = unsignedBinary(operation);
        accept(name, module);
        rejectModule(
            name + " signed left", module,
            [](Module &m) { std::get<Constant>(m.functions[0].code[0]).type = Type::I64; },
            "left operand");
        rejectModule(
            name + " bool right", module,
            [](Module &m) { m.functions[0].code[2] = Constant{1, Type::Bool}; },
            "mistyped current");
        rejectModule(
            name + " missing left", module,
            [](Module &m) { m.functions[0].code.erase(m.functions[0].code.begin() + 1); },
            "stack underflow");
        rejectModule(
            name + " bool operation type", module,
            [](Module &m) {
                std::get<BinaryValue>(m.functions[0].code[3]).operandType = Type::Bool;
            },
            "invalid binary operand type");
        rejectModule(
            name + " invalid operation", module,
            [](Module &m) {
                std::get<BinaryValue>(m.functions[0].code[3]).operation = static_cast<Binary>(-1);
            },
            "invalid binary operation");
        rejectModule(
            name + " forged scalar type", module,
            [](Module &m) {
                std::get<BinaryValue>(m.functions[0].code[3]).operandType.className = "X";
            },
            "invalid binary operand type");
        const bool shift = operation == Binary::ShiftLeft || operation == Binary::ShiftRight;
        rejectModule(
            name + " wrong right signedness", module,
            [shift](Module &m) {
                std::get<Constant>(m.functions[0].code[2]).type = shift ? Type::U64 : Type::I64;
            },
            "mistyped current");
        if (operation == Binary::BitAnd || operation == Binary::BitOr ||
            operation == Binary::BitXor || shift)
            rejectModule(
                name + " signed operation type", module,
                [](Module &m) {
                    std::get<BinaryValue>(m.functions[0].code[3]).operandType = Type::I64;
                },
                "invalid binary operand type");
        const auto emission = X86Emitter{}.emit(validate(module));
        if (shift) {
            const auto guard = emission.find("ja .Laurora_shift_count_trap");
            const auto instruction =
                emission.find(operation == Binary::ShiftLeft ? "shlq %cl, %rax" : "shrq %cl, %rax");
            if (guard == std::string::npos || instruction == std::string::npos ||
                guard >= instruction)
                throw Error("shift guard must precede hardware count masking");
            if (operation == Binary::ShiftLeft &&
                emission.find("cmpq %rdx, %r11\n    jne .Laurora_overflow_trap") ==
                    std::string::npos)
                throw Error("left shift must check every discarded bit");
            ++passed;
            std::cout << "PASS IR " << name << " native guard order\n";
        } else if (operation == Binary::CheckedDivide || operation == Binary::CheckedRemainder) {
            const auto guard = emission.find("jz .Laurora_division_zero_trap");
            const auto division = emission.find("divq %r11");
            if (guard == std::string::npos || division == std::string::npos || guard >= division ||
                emission.find("xorq %rdx, %rdx\n    divq %r11") == std::string::npos ||
                emission.find("idivq") != std::string::npos ||
                emission.find("cmpq $-1, %r11") != std::string::npos)
                throw Error("unsigned division must clear high dividend and guard zero");
            ++passed;
            std::cout << "PASS IR " << name << " native division guard\n";
        }
    }
    for (const auto &source : {Type::I64, Type::U64}) {
        auto module = baseline();
        auto &function = module.functions[0];
        const auto result = source == Type::I64 ? Type::U64 : Type::I64;
        function.result = result;
        function.code = {Constant{42, source}, Convert{source, result}, Return{}};
        const auto name = typeName(source) + " checked conversion";
        accept(name, module);
        rejectModule(
            name + " wrong source value", module,
            [result](Module &m) { std::get<Constant>(m.functions[0].code[0]).type = result; },
            "mistyped current");
        for (const auto &target :
             {Type::Bool, Type::Ref, Type::MutRef, Type::Own, Type("Pair"),
              Type::array(TypeKind::U64, 1), Type(static_cast<TypeKind>(99))}) {
            rejectModule(
                name + " invalid target " + typeName(target), module,
                [target](Module &m) {
                    std::get<Convert>(m.functions[0].code[1]).resultType = target;
                },
                "invalid checked conversion types");
            rejectModule(
                name + " invalid source " + typeName(target), module,
                [target](Module &m) {
                    std::get<Convert>(m.functions[0].code[1]).sourceType = target;
                },
                "invalid checked conversion types");
        }
        rejectModule(
            name + " identity rejected", module,
            [source](Module &m) { std::get<Convert>(m.functions[0].code[1]).resultType = source; },
            "invalid checked conversion types");
    }
    for (const auto operation : {Unary::CheckedNegate, Unary::LogicalNot})
        reject(
            "unary signed or bool operation on u64",
            [operation](Module &m) {
                m.functions[0].code = {Constant{1, Type::U64}, UnaryValue{operation}, Return{}};
            },
            "mistyped current");
    for (const auto &source : {Type::I64, Type::Bool})
        reject(
            "bitwise not requires u64 " + typeName(source),
            [source](Module &m) {
                m.functions[0].code = {Constant{1, source}, UnaryValue{Unary::BitNot}, Return{}};
            },
            "mistyped current");
    for (const auto operation :
         {Comparison::Equal, Comparison::NotEqual, Comparison::Less, Comparison::Greater,
          Comparison::LessEqual, Comparison::GreaterEqual}) {
        auto module = unsignedBinary(Binary::CheckedAdd);
        module.functions[0].result = Type::Bool;
        module.functions[0].code[3] = Compare{operation, Type::U64};
        const auto name = "u64 comparison " + std::to_string(static_cast<int>(operation));
        accept(name, module);
        rejectModule(
            name + " signed left", module,
            [](Module &m) { std::get<Constant>(m.functions[0].code[0]).type = Type::I64; },
            "comparison type mismatch");
        rejectModule(
            name + " signed right", module,
            [](Module &m) { std::get<Constant>(m.functions[0].code[2]).type = Type::I64; },
            "mistyped current");
        rejectModule(
            name + " invalid enum", module,
            [](Module &m) {
                std::get<Compare>(m.functions[0].code[3]).operation = static_cast<Comparison>(-1);
            },
            "invalid comparison");
        rejectModule(
            name + " reference forgery", module,
            [](Module &m) { std::get<Compare>(m.functions[0].code[3]).operandType = Type::Ref; },
            "non-scalar comparison");
    }
    auto call = unsignedOperations();
    auto entry = baseline().functions[0];
    entry.result = Type::U64;
    entry.code = {Constant{-1, Type::U64}, Push{},  Constant{0, Type::U64}, Push{},
                  Call{"unsigned_op0"},    Return{}};
    call.functions.push_back(entry);
    accept("u64 scalar call boundary", call);
    rejectModule(
        "signed argument cannot cross u64 scalar call boundary", call,
        [](Module &m) { std::get<Constant>(m.functions.back().code[0]).type = Type::I64; },
        "call argument type mismatch");
    auto receiver = receiverBaseline();
    receiver.classLayouts["Pair"][0] = Type::U64;
    receiver.functions[0].result = Type::U64;
    receiver.functions[0].slots[16] = Type::U64;
    receiver.functions[0].code[1] = Constant{-1, Type::U64};
    receiver.functions[1].parameters[0] = Type::U64;
    receiver.functions[1].slots[8] = Type::U64;
    receiver.functions[1].code[0] = BindParameter{0, 8, Type::U64};
    receiver.functions[1].code[2] = Load{8, Type::U64};
    receiver.functions[1].code[3] = ReceiverStore{0, Type::U64};
    receiver.functions[2].result = Type::U64;
    receiver.functions[2].code[0] = ReceiverLoad{0, Type::U64};
    receiver.functions[3].result = Type::U64;
    accept("u64 nominal receiver construction and forwarding", receiver);
    rejectModule(
        "u64 receiver field cannot be loaded as signed", receiver,
        [](Module &m) { m.functions[2].code[0] = ReceiverLoad{0, Type::I64}; },
        "receiver field type/layout mismatch");
    reject(
        "conversion roundtrip cannot preserve bounds token",
        [](Module &m) {
            m.functions[0].code = {Constant{42, Type::I64},       Store{8, Type::I64},
                                   Constant{0, Type::I64},        BoundsGuard{8, 1, Type::I64},
                                   Convert{Type::I64, Type::U64}, Convert{Type::U64, Type::I64},
                                   IndexLoad{8, 1, Type::I64},    Return{}};
        },
        "bounds token");
    auto array = baseline();
    array.functions[0].result = Type::U64;
    array.functions[0].slots[8] = Type::U64;
    array.functions[0].code = {Constant{-1, Type::U64},    Store{8, Type::U64},
                               Constant{0, Type::I64},     BoundsGuard{8, 1, Type::U64},
                               IndexLoad{8, 1, Type::U64}, Return{}};
    accept("u64 array guarded load", array);
    auto arrayStore = array;
    arrayStore.functions[0].code = {Constant{0, Type::U64},
                                    Store{8, Type::U64},
                                    Constant{0, Type::I64},
                                    BoundsGuard{8, 1, Type::U64},
                                    Push{},
                                    Constant{-1, Type::U64},
                                    IndexStore{8, 1, Type::U64},
                                    Load{8, Type::U64},
                                    Return{}};
    accept("u64 array guarded store", arrayStore);
    rejectModule(
        "u64 array store requires matching token", arrayStore,
        [](Module &m) { m.functions[0].code[3] = Constant{0, Type::I64}; }, "bounds token");
    rejectModule(
        "u64 array index cannot be u64", array,
        [](Module &m) { std::get<Constant>(m.functions[0].code[2]).type = Type::U64; },
        "mistyped current");
    rejectModule(
        "u64 array token cannot alias signed layout", array,
        [](Module &m) { m.functions[0].code[4] = IndexLoad{8, 1, Type::I64}; }, "slot type/layout");
    rejectModule(
        "u64 payload cannot mint borrow capability", array,
        [](Module &m) { m.functions[0].code[4] = BorrowHandle{8, Type::Ref}; }, "slot type/layout");
}
Module arrayReceiverBaseline() {
    Module module;
    module.classLayouts["ArrayBox"] = {Type::I64,  Type::I64,  Type::I64, Type::Bool,
                                       Type::Bool, Type::Bool, Type::I64, Type::I64};
    module.classFields["ArrayBox"] = {{Type::I64, 0, 1, false},
                                      {Type::I64, 1, 2, true},
                                      {Type::Bool, 3, 1, false},
                                      {Type::Bool, 4, 2, true},
                                      {Type::I64, 6, 2, true}};
    aurora::ir::Function entry;
    entry.name = "test";
    entry.result = Type::I64;
    entry.frameBytes = 64;
    entry.objectSlots[64] = ObjectSlot{"ArrayBox", true};
    for (std::size_t leaf = 0; leaf < module.classLayouts["ArrayBox"].size(); ++leaf)
        entry.slots[64 - static_cast<int>(leaf * 8)] = module.classLayouts["ArrayBox"][leaf];
    entry.code = {BeginObject{64},
                  MethodCall{"construct_array", 64},
                  Constant{1, Type::I64},
                  Push{},
                  Constant{42, Type::I64},
                  Push{},
                  MethodCall{"set_array", 64},
                  Constant{1, Type::I64},
                  Push{},
                  MethodCall{"get_array", 64},
                  Return{}};
    aurora::ir::Function constructor;
    constructor.name = "construct_array";
    constructor.result = Type::I64;
    constructor.receiver = Receiver{"ArrayBox", true, true};
    constructor.code = {Constant{7, Type::I64},  ReceiverStore{0, Type::I64},  ReceiverArrayZero{1},
                        Constant{1, Type::Bool}, ReceiverStore{2, Type::Bool}, ReceiverArrayZero{3},
                        ReceiverArrayZero{4},    Constant{0, Type::I64},       Return{}};
    aurora::ir::Function getter;
    getter.name = "get_array";
    getter.result = Type::I64;
    getter.parameters = {Type::I64};
    getter.frameBytes = 16;
    getter.slots[8] = Type::I64;
    getter.receiver = Receiver{"ArrayBox", false, false};
    getter.code = {BindParameter{0, 8, Type::I64}, Load{8, Type::I64}, ReceiverBoundsGuard{1},
                   ReceiverIndexLoad{1}, Return{}};
    aurora::ir::Function setter;
    setter.name = "set_array";
    setter.result = Type::I64;
    setter.parameters = {Type::I64, Type::I64};
    setter.frameBytes = 16;
    setter.slots = {{8, Type::I64}, {16, Type::I64}};
    setter.receiver = Receiver{"ArrayBox", true, false};
    setter.code = {BindParameter{0, 8, Type::I64},
                   BindParameter{1, 16, Type::I64},
                   Load{8, Type::I64},
                   ReceiverBoundsGuard{1},
                   Push{},
                   Load{16, Type::I64},
                   ReceiverIndexStore{1},
                   Constant{0, Type::I64},
                   Return{}};
    module.functions = {entry, constructor, getter, setter};
    return module;
}
Module arrayNativeModule() {
    auto module = arrayReceiverBaseline();
    auto mapping = module.functions[2];
    mapping.name = "array_scalar_getter";
    mapping.parameters.clear();
    mapping.code = {ReceiverLoad{0, Type::I64}, Return{}};
    module.functions.push_back(mapping);
    mapping.name = "array_bool_getter";
    mapping.result = Type::Bool;
    mapping.code = {ReceiverLoad{2, Type::Bool}, Return{}};
    module.functions.push_back(mapping);
    mapping.name = "array_bool_index_getter";
    mapping.code = {Constant{1, Type::I64}, ReceiverBoundsGuard{3}, ReceiverIndexLoad{3}, Return{}};
    module.functions.push_back(mapping);
    mapping.name = "array_bool_setter";
    mapping.result = Type::I64;
    mapping.receiver->mutableValue = true;
    mapping.code = {
        Constant{1, Type::I64}, ReceiverBoundsGuard{3}, Push{},  Constant{1, Type::Bool},
        ReceiverIndexStore{3},  Constant{0, Type::I64}, Return{}};
    module.functions.push_back(mapping);
    auto entry = module.functions[0];
    entry.name = "array_scalar_mapping";
    entry.code = {BeginObject{64}, MethodCall{"construct_array", 64},
                  MethodCall{"array_scalar_getter", 64}, Return{}};
    module.functions.push_back(entry);
    entry.name = "array_bool_mapping";
    entry.result = Type::Bool;
    entry.code = {BeginObject{64}, MethodCall{"construct_array", 64},
                  MethodCall{"array_bool_getter", 64}, Return{}};
    module.functions.push_back(entry);
    entry.name = "array_bool_zero";
    entry.code = {BeginObject{64}, MethodCall{"construct_array", 64},
                  MethodCall{"array_bool_index_getter", 64}, Return{}};
    module.functions.push_back(entry);
    entry.name = "array_bool_store";
    entry.code = {BeginObject{64}, MethodCall{"construct_array", 64},
                  MethodCall{"array_bool_setter", 64}, MethodCall{"array_bool_index_getter", 64},
                  Return{}};
    module.functions.push_back(entry);
    entry.name = "array_dynamic";
    entry.result = Type::I64;
    entry.parameters = {Type::I64};
    entry.frameBytes = 80;
    entry.slots[72] = Type::I64;
    entry.code = {BindParameter{0, 72, Type::I64},
                  BeginObject{64},
                  MethodCall{"construct_array", 64},
                  Load{72, Type::I64},
                  Push{},
                  MethodCall{"get_array", 64},
                  Return{}};
    module.functions.push_back(entry);
    auto explosive = module.functions[3];
    explosive.name = "array_explosive_setter";
    explosive.code[5] = Call{"array_explosive_rhs"};
    module.functions.push_back(explosive);
    explosive.name = "array_explosive_rhs";
    explosive.receiver.reset();
    explosive.parameters.clear();
    explosive.code = {Constant{1, Type::I64}, Push{}, Constant{0, Type::I64},
                      BinaryValue{Binary::CheckedDivide}, Return{}};
    module.functions.push_back(explosive);
    entry.name = "array_store_dynamic";
    entry.code = {BindParameter{0, 72, Type::I64},
                  BeginObject{64},
                  MethodCall{"construct_array", 64},
                  Load{72, Type::I64},
                  Push{},
                  Constant{42, Type::I64},
                  Push{},
                  MethodCall{"array_explosive_setter", 64},
                  Return{}};
    module.functions.push_back(entry);
    aurora::ir::Function copy;
    copy.name = "copy_array_box";
    copy.result = Type("ArrayBox");
    copy.parameters = {Type("ArrayBox")};
    copy.frameBytes = 64;
    copy.slots = module.functions[0].slots;
    copy.objectSlots[64] = ObjectSlot{"ArrayBox", false};
    copy.code = {BindObjectParameter{0, 64, "ArrayBox"}, ReturnObject{64}};
    module.functions.push_back(copy);
    entry = module.functions[0];
    entry.name = "array_copy";
    entry.frameBytes = 192;
    entry.objectSlots[128] = ObjectSlot{"ArrayBox", false};
    entry.objectSlots[192] = ObjectSlot{"ArrayBox", false};
    for (std::size_t leaf = 0; leaf < module.classLayouts["ArrayBox"].size(); ++leaf) {
        const auto type = module.classLayouts["ArrayBox"][leaf];
        entry.slots[128 - static_cast<int>(leaf * 8)] = type;
        entry.slots[192 - static_cast<int>(leaf * 8)] = type;
    }
    entry.code.resize(7);
    entry.code.push_back(BeginObject{128});
    for (std::size_t leaf = 0; leaf < module.classLayouts["ArrayBox"].size(); ++leaf) {
        const auto type = module.classLayouts["ArrayBox"][leaf];
        entry.code.push_back(Load{64 - static_cast<int>(leaf * 8), type});
        entry.code.push_back(Store{128 - static_cast<int>(leaf * 8), type});
    }
    entry.code.insert(entry.code.end(),
                      {BeginObject{192}, AggregateCall{"copy_array_box", {128}, 192},
                       Constant{1, Type::I64}, Push{}, Constant{99, Type::I64}, Push{},
                       MethodCall{"set_array", 64}, Constant{1, Type::I64}, Push{},
                       MethodCall{"get_array", 192}, Return{}});
    module.functions.push_back(entry);
    return module;
}
void arrayReceiverTests() {
    accept("logical array fields constructor and checked methods", arrayReceiverBaseline());
    accept("array fields copied through complete private value ABI", arrayNativeModule());
    auto rejectArray = [](const std::string &name, const std::function<void(Module &)> &mutate,
                          const std::string &expected) {
        rejectModule(name, arrayReceiverBaseline(), mutate, expected);
    };
    rejectArray(
        "logical fields unknown nominal layout",
        [](Module &m) { m.classFields["Unknown"] = m.classFields.at("ArrayBox"); },
        "unknown class layout");
    for (int first : {-1, 0, 2, 8192})
        rejectArray(
            "logical array range offset " + std::to_string(first),
            [=](Module &m) { m.classFields["ArrayBox"][1].firstLeaf = first; },
            "invalid logical class field shape");
    for (int length : {-1, 0, 65})
        rejectArray(
            "logical array length " + std::to_string(length),
            [=](Module &m) { m.classFields["ArrayBox"][1].length = length; },
            "invalid logical class field shape");
    rejectArray(
        "logical scalar range cannot hide array",
        [](Module &m) { m.classFields["ArrayBox"][1].array = false; },
        "invalid logical class field shape");
    rejectArray(
        "logical arrays require scalar leaves",
        [](Module &m) { m.classFields["ArrayBox"][1].elementType = Type::Own; },
        "invalid logical class field shape");
    rejectArray(
        "logical array leaf payload matches layout",
        [](Module &m) { m.classLayouts["ArrayBox"][2] = Type::U64; }, "leaf type mismatch");
    rejectArray(
        "logical array range cannot escape layout",
        [](Module &m) { m.classFields["ArrayBox"].back().length = 3; }, "range exceeds layout");
    rejectArray(
        "logical fields cover every leaf", [](Module &m) { m.classFields["ArrayBox"].pop_back(); },
        "do not cover complete layout");
    rejectArray(
        "explicit empty shape cannot hide payload",
        [](Module &m) { m.classFields["ArrayBox"].clear(); }, "do not cover complete layout");
    rejectArray(
        "absent shape cannot forge array access", [](Module &m) { m.classFields.clear(); },
        "requires array field");
    rejectArray(
        "scalar receiver load cannot access array",
        [](Module &m) { m.functions[2].code[2] = ReceiverLoad{1, Type::I64}; },
        "receiver field type/layout");
    rejectArray(
        "scalar receiver init cannot partially initialize array",
        [](Module &m) { m.functions[1].code[2] = ReceiverStore{1, Type::I64}; },
        "receiver field type/layout");
    rejectArray(
        "array constructor must initialize every field",
        [](Module &m) { m.functions[1].code.erase(m.functions[1].code.begin() + 5); },
        "before all fields initialized");
    rejectArray(
        "array constructor rejects repeated zero",
        [](Module &m) {
            m.functions[1].code.insert(m.functions[1].code.begin() + 3, ReceiverArrayZero{1});
        },
        "array initialized more than once");
    rejectArray(
        "array constructor conditional missing zero",
        [](Module &m) {
            m.functions[1].code.insert(m.functions[1].code.begin() + 2,
                                       {Constant{1, Type::Bool}, BranchFalse{1}});
            m.functions[1].code.insert(m.functions[1].code.begin() + 5, Label{1});
        },
        "before all fields initialized");
    rejectArray(
        "array constructor conditional duplicate zero",
        [](Module &m) {
            m.functions[1].code.insert(
                m.functions[1].code.begin() + 3,
                {Constant{1, Type::Bool}, BranchFalse{1}, ReceiverArrayZero{1}, Label{1}});
        },
        "array initialized more than once");
    rejectArray(
        "array constructor loop cannot repeat initialization",
        [](Module &m) {
            m.functions[1].code.insert(m.functions[1].code.begin() + 2, Label{1});
            m.functions[1].code.insert(
                m.functions[1].code.begin() + 4,
                {Constant{1, Type::Bool}, BranchFalse{2}, Jump{1}, Label{2}});
        },
        "array initialized more than once");
    rejectArray(
        "array zero requires constructor",
        [](Module &m) { m.functions[2].code[2] = ReceiverArrayZero{1}; },
        "zero requires constructor");
    rejectArray(
        "array write requires mutable receiver",
        [](Module &m) { m.functions[3].receiver->mutableValue = false; },
        "write through const receiver");
    for (const auto &[name, operation] :
         std::vector<std::pair<std::string, Instruction>>{{"zero", ReceiverArrayZero{1}},
                                                          {"guard", ReceiverBoundsGuard{1}},
                                                          {"load", ReceiverIndexLoad{1}},
                                                          {"store", ReceiverIndexStore{1}}}) {
        rejectArray(
            "array " + name + " requires receiver",
            [=](Module &m) { m.functions[0].code.insert(m.functions[0].code.begin(), operation); },
            "without bound receiver");
    }
    for (const auto &[name, operation] : std::vector<std::pair<std::string, Instruction>>{
             {"zero", ReceiverArrayZero{0}},
             {"guard", ReceiverBoundsGuard{0}},
             {"load", ReceiverIndexLoad{0}},
             {"store", ReceiverIndexStore{0}},
             {"guard negative field", ReceiverBoundsGuard{-1}},
             {"guard past field", ReceiverBoundsGuard{5}}}) {
        rejectArray(
            "array operation rejects scalar or invalid " + name,
            [=](Module &m) { m.functions[2].code[2] = operation; },
            name.find("field") == std::string::npos ? "requires array field" : "field type/layout");
    }
    for (const auto &[name, operation] :
         std::vector<std::pair<std::string, Instruction>>{{"guard", ReceiverBoundsGuard{1}},
                                                          {"load", ReceiverIndexLoad{1}},
                                                          {"store", ReceiverIndexStore{1}}}) {
        rejectArray(
            "constructor cannot use indexed " + name,
            [=](Module &m) {
                m.functions[1].code.insert(m.functions[1].code.end() - 1, operation);
            },
            "constructor cannot access receiver array");
    }
    rejectArray(
        "receiver index requires signed i64",
        [](Module &m) { m.functions[2].code[1] = Constant{0, Type::U64}; }, "mistyped current");
    rejectArray(
        "receiver load requires bounds evidence",
        [](Module &m) { m.functions[2].code[2] = Constant{0, Type::I64}; }, "bounds token");
    rejectArray(
        "receiver store requires saved evidence",
        [](Module &m) { m.functions[3].code[3] = Constant{0, Type::I64}; }, "bounds token");
    rejectArray(
        "same shape other field cannot reuse load token",
        [](Module &m) { m.functions[2].code[3] = ReceiverIndexLoad{4}; }, "bounds token");
    rejectArray(
        "same shape other field cannot reuse store token",
        [](Module &m) { m.functions[3].code[6] = ReceiverIndexStore{4}; }, "bounds token");
    rejectArray(
        "bool array store rejects integer payload",
        [](Module &m) {
            m.functions[3].code[3] = ReceiverBoundsGuard{3};
            m.functions[3].code[6] = ReceiverIndexStore{3};
        },
        "mistyped current");
    rejectArray(
        "scalar arithmetic cannot retain receiver bounds",
        [](Module &m) {
            m.functions[2].code.insert(m.functions[2].code.begin() + 3,
                                       UnaryValue{Unary::CheckedNegate});
        },
        "bounds token");
    rejectArray(
        "conversion roundtrip cannot retain receiver bounds",
        [](Module &m) {
            m.functions[2].code.insert(
                m.functions[2].code.begin() + 3,
                {Convert{Type::I64, Type::U64}, Convert{Type::U64, Type::I64}});
        },
        "bounds token");
    rejectArray(
        "unguarded pop cannot forge receiver bounds",
        [](Module &m) {
            m.functions[2].code.insert(m.functions[2].code.begin() + 2, Push{});
            m.functions[2].code.insert(m.functions[2].code.begin() + 4, Pop{});
        },
        "bounds token");
    rejectArray(
        "slot reload cannot retain receiver bounds",
        [](Module &m) {
            m.functions[2].slots[16] = Type::I64;
            m.functions[2].code.insert(m.functions[2].code.begin() + 3,
                                       {Store{16, Type::I64}, Load{16, Type::I64}});
        },
        "bounds token");
    rejectArray(
        "local token cannot authorize receiver access",
        [](Module &m) { m.functions[2].code[2] = BoundsGuard{8, 1, Type::I64}; }, "bounds token");
    rejectArray(
        "receiver token cannot authorize local access",
        [](Module &m) { m.functions[2].code[3] = IndexLoad{8, 1, Type::I64}; }, "bounds token");
    rejectArray(
        "array receiver nominal mismatch rejected",
        [](Module &m) {
            m.classLayouts["OtherBox"] = m.classLayouts["ArrayBox"];
            m.classFields["OtherBox"] = m.classFields["ArrayBox"];
            m.functions[2].receiver->className = "OtherBox";
        },
        "nominal class mismatch");
    auto saved = arrayReceiverBaseline();
    auto helper = baseline().functions[0];
    helper.name = "array_rhs";
    helper.frameBytes = 0;
    helper.slots.clear();
    helper.code = {Constant{42, Type::I64}, Return{}};
    saved.functions.push_back(helper);
    saved.functions[3].code[5] = Call{"array_rhs"};
    accept("saved receiver token survives scalar RHS call", saved);
    helper.name = "array_rhs_method";
    helper.receiver = Receiver{"ArrayBox", true, false};
    helper.code = {Constant{1, Type::I64},  ReceiverBoundsGuard{4}, Push{},
                   Constant{42, Type::I64}, ReceiverIndexStore{4},  Return{}};
    saved.functions.push_back(helper);
    saved.functions[3].code[5] = MethodCall{"array_rhs_method", 0};
    accept("saved receiver token survives mutable receiver reborrow", saved);
    rejectModule(
        "returned scalar cannot forge receiver token", saved,
        [](Module &m) { m.functions[2].code[2] = Call{"array_rhs"}; }, "bounds token");
    auto restored = arrayReceiverBaseline();
    restored.functions[2].code.insert(restored.functions[2].code.begin() + 3,
                                      {Push{}, Constant{99, Type::I64}, Pop{}});
    accept("unchanged receiver token survives push and pop", restored);
    auto joined = arrayReceiverBaseline();
    joined.functions[2].code = {BindParameter{0, 8, Type::I64},
                                Constant{1, Type::Bool},
                                BranchFalse{1},
                                Load{8, Type::I64},
                                ReceiverBoundsGuard{1},
                                Jump{2},
                                Label{1},
                                Load{8, Type::I64},
                                ReceiverBoundsGuard{1},
                                Label{2},
                                ReceiverIndexLoad{1},
                                Return{}};
    accept("same receiver field bounds evidence survives CFG join", joined);
    rejectModule(
        "cross-field bounds evidence cannot survive CFG join", joined,
        [](Module &m) { m.functions[2].code[8] = ReceiverBoundsGuard{4}; }, "mistyped current");
    rejectModule(
        "branch cannot bypass receiver bounds check", joined,
        [](Module &m) { m.functions[2].code[8] = Constant{0, Type::I64}; }, "mistyped current");
    for (const auto &type : {Type::I64, Type::U64, Type::Bool}) {
        auto module = baseline();
        module.classLayouts["Capacity"] = std::vector<Type>(64, type);
        module.classFields["Capacity"] = {{type, 0, 64, true}};
        auto ctor = helper;
        ctor.name = "capacity_ctor";
        ctor.result = Type::I64;
        ctor.receiver = Receiver{"Capacity", true, true};
        ctor.code = {ReceiverArrayZero{0}, Constant{0, Type::I64}, Return{}};
        module.functions.push_back(ctor);
        aurora::ir::Function copy;
        copy.name = "capacity_copy";
        copy.result = Type("Capacity");
        copy.parameters = {Type("Capacity")};
        copy.frameBytes = 512;
        copy.objectSlots[512] = ObjectSlot{"Capacity", false};
        for (int leaf = 0; leaf < 64; ++leaf)
            copy.slots[512 - leaf * 8] = type;
        copy.code = {BindObjectParameter{0, 512, "Capacity"}, ReturnObject{512}};
        module.functions.push_back(copy);
        accept(typeName(type) + " array 64-leaf boundary", module);
        rejectModule(
            typeName(type) + " array plus scalar exceeds boundary", module,
            [=](Module &m) {
                m.classLayouts["Capacity"].push_back(type);
                m.classFields["Capacity"].push_back({type, 64, 1, false});
                m.functions[1].code.insert(m.functions[1].code.end() - 2,
                                           {Constant{0, type}, ReceiverStore{1, type}});
            },
            "exceeds 64 scalar fields");
        module.functions.pop_back();
        module.classLayouts["Capacity"].push_back(type);
        module.classFields["Capacity"].push_back({type, 64, 1, false});
        module.functions[1].code.insert(module.functions[1].code.end() - 2,
                                        {Constant{0, type}, ReceiverStore{1, type}});
        accept(typeName(type) + " local class may exceed boundary leaf cap", module);
    }
    const auto assembly = X86Emitter{}.emit(validate(arrayNativeModule()));
    for (const std::string fragment :
         {"movq $0, 8(%r10)", "movq $0, 16(%r10)", "movq %rax, 24(%r10)", "movq $0, 32(%r10)",
          "movq $0, 40(%r10)", "movq $0, 48(%r10)", "movq $0, 56(%r10)",
          "cmpq $2, %rax\n    jae .Laurora_bounds_trap", "movq 8(%r10,%rax,8), %rax",
          "movq %rax, 8(%r10,%rcx,8)", "movq 32(%r10,%rax,8), %rax", "movq %rax, 32(%r10,%rcx,8)"})
        if (assembly.find(fragment) == std::string::npos)
            throw Error("array receiver emission missing " + fragment);
    ++passed;
    std::cout << "PASS IR array zero, scalar mapping, bool stride and checked index emission\n";
    const auto savedAssembly = X86Emitter{}.emit(validate(saved));
    const auto start = savedAssembly.find("set_array:");
    const auto bounds = savedAssembly.find("jae .Laurora_bounds_trap", start);
    const auto rhs = savedAssembly.find("call array_rhs_method", start);
    const auto write = savedAssembly.find("movq %rax, 8(%r10,%rcx,8)", start);
    if (start == std::string::npos || bounds >= rhs || rhs >= write ||
        savedAssembly.find("movq -24(%rbp), %r10", rhs) >= write)
        throw Error("array store must check bounds before RHS and reload receiver after call");
    ++passed;
    std::cout << "PASS IR receiver store guard precedes RHS and receiver reload follows call\n";
}

// Distinct logical fields retain nominal identity even when their leaf vectors
// are equal. Empty embedded fields deliberately have no scalar storage.
Module composedBaseline() {
    Module module;
    module.classLayouts = {{"Leaf", {Type::I64, Type::Bool}},
                           {"Other", {Type::I64, Type::Bool}},
                           {"Empty", {}},
                           {"Outer", {Type::I64, Type::I64, Type::Bool}}};
    module.classFields["Outer"] = {
        {Type::I64, 0, 1, false}, {Type("Leaf"), 1, 2, false}, {Type("Empty"), 3, 0, false}};
    aurora::ir::Function entry;
    entry.name = "test";
    entry.result = Type::I64;
    entry.frameBytes = 160;
    entry.objectSlots = {{16, {"Leaf", true}},    {32, {"Leaf", false}},  {56, {"Outer", false}},
                         {72, {"Leaf", true}},    {96, {"Outer", false}}, {104, {"Empty", false}},
                         {128, {"Outer", false}}, {152, {"Outer", false}}};
    for (const auto &[base, object] : entry.objectSlots)
        for (std::size_t leaf = 0; leaf < module.classLayouts.at(object.className).size(); ++leaf)
            entry.slots[base - static_cast<int>(leaf * 8)] =
                module.classLayouts.at(object.className)[leaf];
    entry.code = {BeginObject{16},
                  Constant{42, Type::I64},
                  Store{16, Type::I64},
                  Constant{1, Type::Bool},
                  Store{8, Type::Bool},
                  BeginObject{32},
                  CopyObject{16, 32},
                  Constant{9, Type::I64},
                  Store{16, Type::I64},
                  BeginObject{104},
                  BeginObject{56},
                  Constant{7, Type::I64},
                  Push{},
                  Constant{5, Type::I64},
                  Push{},
                  MethodCall{"construct_outer", 56, {0, 32, 104, 0}},
                  BeginObject{96},
                  CopyObject{56, 96},
                  BeginObject{128},
                  AggregateCall{"copy_outer", {96}, 128},
                  BeginObject{72},
                  ObjectFieldCopy{128, 1, 72},
                  Load{72, Type::I64},
                  Return{}};
    aurora::ir::Function constructor;
    constructor.name = "construct_outer";
    constructor.result = Type::I64;
    constructor.parameters = {Type::I64, Type("Leaf"), Type("Empty"), Type::I64};
    constructor.frameBytes = 48;
    constructor.slots = {{8, Type::I64}, {24, Type::I64}, {16, Type::Bool}, {40, Type::I64}};
    constructor.objectSlots = {{24, {"Leaf", false}}, {32, {"Empty", false}}};
    constructor.receiver = Receiver{"Outer", true, true};
    constructor.code = {BindParameter{0, 8, Type::I64},
                        BindObjectParameter{1, 24, "Leaf"},
                        BindObjectParameter{2, 32, "Empty"},
                        BindParameter{3, 40, Type::I64},
                        Load{8, Type::I64},
                        Push{},
                        Load{40, Type::I64},
                        BinaryValue{Binary::CheckedAdd},
                        ReceiverStore{0, Type::I64},
                        InitializeObjectField{0, 1, 24},
                        InitializeObjectField{0, 2, 32},
                        Constant{0, Type::I64},
                        Return{}};
    aurora::ir::Function copy;
    copy.name = "copy_outer";
    copy.result = Type("Outer");
    copy.parameters = {Type("Outer")};
    copy.frameBytes = 32;
    copy.slots = {{24, Type::I64}, {16, Type::I64}, {8, Type::Bool}};
    copy.objectSlots = {{24, {"Outer", false}}};
    copy.code = {BindObjectParameter{0, 24, "Outer"}, ReturnObject{24}};
    aurora::ir::Function getter;
    getter.name = "get_outer";
    getter.result = Type::I64;
    getter.receiver = Receiver{"Outer", false, false};
    getter.frameBytes = 16;
    getter.slots = {{16, Type::I64}, {8, Type::Bool}};
    getter.objectSlots = {{16, {"Leaf", true}}};
    getter.code = {BeginObject{16}, ObjectFieldCopy{0, 1, 16}, Load{16, Type::I64}, Return{}};
    module.functions = {entry, constructor, copy, getter};
    return module;
}
MethodCall &composedCall(Module &module) {
    return std::get<MethodCall>(module.functions[0].code[15]);
}
Module composedEmptyBaseline() {
    Module module;
    module.classLayouts = {{"Empty", {}}, {"OuterEmpty", {}}};
    module.classFields["OuterEmpty"] = {{Type("Empty"), 0, 0, false}};
    aurora::ir::Function entry;
    entry.name = "test";
    entry.result = Type::I64;
    entry.frameBytes = 32;
    entry.objectSlots = {{8, {"Empty", false}},
                         {16, {"OuterEmpty", false}},
                         {24, {"Empty", false}},
                         {32, {"OuterEmpty", false}}};
    entry.code = {BeginObject{8},
                  BeginObject{16},
                  MethodCall{"construct_empty_outer", 16, {8}},
                  BeginObject{24},
                  ObjectFieldCopy{16, 0, 24},
                  BeginObject{32},
                  CopyObject{16, 32},
                  Constant{42, Type::I64},
                  Return{}};
    aurora::ir::Function constructor;
    constructor.name = "construct_empty_outer";
    constructor.result = Type::I64;
    constructor.parameters = {Type("Empty")};
    constructor.receiver = Receiver{"OuterEmpty", true, true};
    constructor.frameBytes = 16;
    constructor.objectSlots = {{8, {"Empty", false}}};
    constructor.code = {BindObjectParameter{0, 8, "Empty"}, InitializeObjectField{0, 0, 8},
                        Constant{0, Type::I64}, Return{}};
    module.functions = {entry, constructor};
    return module;
}
Module composedNativeModule() {
    auto module = composedBaseline();
    auto entry = module.functions[0];
    entry.code.resize(16);
    entry.code.insert(entry.code.end(), {MethodCall{"get_outer", 56}, Return{}});
    entry.name = "nested_receiver_projection";
    module.functions.push_back(entry);
    entry.name = "nested_scalar_mapping";
    entry.code[16] = Load{56, Type::I64};
    module.functions.push_back(entry);
    entry.name = "nested_snapshot_independence";
    entry.code[16] = Load{16, Type::I64};
    module.functions.push_back(entry);
    entry = module.functions[0];
    entry.name = "nested_projection_independence";
    entry.code.resize(22);
    entry.code.insert(entry.code.end(), {Constant{99, Type::I64}, Store{72, Type::I64},
                                         MethodCall{"get_outer", 128}, Return{}});
    module.functions.push_back(entry);
    entry.name = "nested_bool_mapping";
    entry.result = Type::Bool;
    entry.code.resize(22);
    entry.code.insert(entry.code.end(), {Load{64, Type::Bool}, Return{}});
    module.functions.push_back(entry);
    // A receiver-local constructor executes while another receiver is bound.
    // Its record, local argument snapshots and both receivers remain disjoint.
    auto relay = module.functions[3];
    relay.name = "nested_receiver_constructor";
    relay.frameBytes = 64;
    relay.slots = {
        {16, Type::I64}, {8, Type::Bool}, {48, Type::I64}, {40, Type::I64}, {32, Type::Bool}};
    relay.objectSlots = {{16, {"Leaf", false}}, {24, {"Empty", false}}, {48, {"Outer", false}}};
    relay.code = {BeginObject{16},
                  ObjectFieldCopy{0, 1, 16},
                  BeginObject{24},
                  ObjectFieldCopy{0, 2, 24},
                  BeginObject{48},
                  Constant{11, Type::I64},
                  Push{},
                  Constant{13, Type::I64},
                  Push{},
                  MethodCall{"construct_outer", 48, {0, 16, 24, 0}},
                  ReceiverLoad{0, Type::I64},
                  Push{},
                  Load{48, Type::I64},
                  BinaryValue{Binary::CheckedAdd},
                  Return{}};
    module.functions.push_back(relay);
    entry = module.functions[0];
    entry.name = "nested_distinct_receiver_record";
    entry.code.resize(16);
    entry.code.insert(entry.code.end(), {MethodCall{"nested_receiver_constructor", 56}, Return{}});
    module.functions.push_back(entry);
    auto empty = composedEmptyBaseline();
    for (const auto &[name, layout] : empty.classLayouts)
        module.classLayouts[name] = layout;
    for (const auto &[name, fields] : empty.classFields)
        module.classFields[name] = fields;
    empty.functions[0].name = "nested_empty_copy";
    module.functions.insert(module.functions.end(), empty.functions.begin(), empty.functions.end());
    return module;
}
void composedTests() {
    accept("composed nominal copies and mixed constructor record", composedBaseline());
    accept("composed empty class has logical initialization", composedEmptyBaseline());
    accept("composed receiver and ordinary call native fixtures", composedNativeModule());
    auto rejectComposed = [&](const std::string &name, const std::function<void(Module &)> &change,
                              const std::string &expected) {
        rejectModule(name, composedBaseline(), change, expected);
    };
    for (const int index : {-1, 3, 99})
        rejectComposed(
            "projection invalid logical index " + std::to_string(index),
            [=](Module &m) {
                std::get<ObjectFieldCopy>(m.functions[0].code[21]).fieldIndex = index;
            },
            "logical field index");
    rejectComposed(
        "projection scalar field rejected",
        [](Module &m) { std::get<ObjectFieldCopy>(m.functions[0].code[21]).fieldIndex = 0; },
        "projection requires class field");
    rejectComposed(
        "projection wrong nominal child",
        [](Module &m) { m.functions[0].objectSlots[72].className = "Other"; },
        "copy nominal class mismatch");
    rejectComposed(
        "whole copy equal-byte nominal forgery",
        [](Module &m) { m.functions[0].objectSlots[32].className = "Other"; },
        "copy nominal class mismatch");
    rejectComposed(
        "projection interior source",
        [](Module &m) { std::get<ObjectFieldCopy>(m.functions[0].code[21]).sourceOffset = 120; },
        "exact object slot");
    rejectComposed(
        "projection interior result",
        [](Module &m) { std::get<ObjectFieldCopy>(m.functions[0].code[21]).resultOffset = 64; },
        "exact object slot");
    rejectComposed(
        "projection aliases owner",
        [](Module &m) { std::get<ObjectFieldCopy>(m.functions[0].code[21]).resultOffset = 128; },
        "projection source aliases result");
    rejectComposed(
        "whole copy aliases source", [](Module &m) { m.functions[0].code[6] = CopyObject{16, 16}; },
        "copy source aliases result");
    rejectComposed(
        "copy inactive source",
        [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 6, EndObject{16});
        },
        "outside active lifetime");
    rejectComposed(
        "copy inactive result",
        [](Module &m) { m.functions[0].code.erase(m.functions[0].code.begin() + 5); },
        "outside active lifetime");
    rejectComposed(
        "copy partially initialized source",
        [](Module &m) { m.functions[0].code.erase(m.functions[0].code.begin() + 4); },
        "not fully initialized");
    rejectComposed(
        "copy partially initialized result",
        [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 6,
                                       {Constant{0, Type::I64}, Store{32, Type::I64}});
        },
        "pristine result");
    rejectComposed(
        "copy initialized result",
        [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 7, CopyObject{16, 32});
        },
        "already initialized");
    rejectComposed(
        "copy stale current register rejected",
        [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 7, Store{16, Type::Bool});
        },
        "missing or mistyped current value");
    rejectComposed(
        "nested direct scalar initialization rejected",
        [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 15,
                                       {Constant{3, Type::I64}, Store{48, Type::I64}});
        },
        "scalar store cannot write nested class field");
    rejectComposed(
        "nested direct scalar mutation rejected",
        [](Module &m) {
            m.functions[0].objectSlots[56].mutableValue = true;
            m.functions[0].code.insert(m.functions[0].code.begin() + 16,
                                       {Constant{3, Type::I64}, Store{48, Type::I64}});
        },
        "scalar store cannot write nested class field");
    rejectComposed(
        "nested direct indexed mutation rejected",
        [](Module &m) {
            m.functions[0].objectSlots[56].mutableValue = true;
            m.functions[0].code.insert(m.functions[0].code.begin() + 16,
                                       {Constant{0, Type::I64}, BoundsGuard{48, 1, Type::I64},
                                        Push{}, Constant{3, Type::I64},
                                        IndexStore{48, 1, Type::I64}});
        },
        "indexed store cannot write nested class field");
    rejectComposed(
        "class receiver scalar store forgery",
        [](Module &m) { m.functions[1].code[9] = ReceiverStore{1, Type::I64}; },
        "receiver field type/layout mismatch");
    rejectComposed(
        "constructor class field absent",
        [](Module &m) { m.functions[1].code.erase(m.functions[1].code.begin() + 9); },
        "returns before all fields initialized");
    rejectComposed(
        "constructor empty class field absent",
        [](Module &m) { m.functions[1].code.erase(m.functions[1].code.begin() + 10); },
        "returns before all class fields initialized");
    for (const int field : {1, 2})
        rejectComposed(
            "constructor repeated logical field " + std::to_string(field),
            [=](Module &m) {
                m.functions[1].code.insert(m.functions[1].code.begin() + 11,
                                           InitializeObjectField{0, field, field == 1 ? 24 : 32});
            },
            "class field initialized more than once");
    rejectComposed(
        "class initialization local receiver unsupported",
        [](Module &m) {
            std::get<InitializeObjectField>(m.functions[1].code[9]).objectOffset = 24;
        },
        "requires bound constructor receiver");
    rejectComposed(
        "class initialization scalar logical field rejected",
        [](Module &m) { std::get<InitializeObjectField>(m.functions[1].code[9]).fieldIndex = 0; },
        "requires class field");
    rejectComposed(
        "class initialization wrong nominal child",
        [](Module &m) {
            // Equal scalar bytes do not erase a different recursive logical shape.
            m.classFields["Other"] = {{Type("Leaf"), 0, 2, false}};
            m.classFields["Outer"][1].elementType = Type("Other");
            m.functions[0].objectSlots[72].className = "Other";
            m.functions[3].objectSlots[16].className = "Other";
        },
        "initializer nominal class mismatch");
    rejectComposed(
        "constructor receiver projection rejected",
        [](Module &m) { m.functions[1].code[9] = ObjectFieldCopy{0, 1, 24}; },
        "cannot project receiver");
    rejectComposed(
        "constructor argument missing vector",
        [](Module &m) { composedCall(m).objectArguments.clear(); },
        "argument vector size mismatch");
    rejectComposed(
        "constructor scalar argument object forgery",
        [](Module &m) { composedCall(m).objectArguments[3] = 104; }, "scalar constructor argument");
    rejectComposed(
        "constructor argument mutable snapshot",
        [](Module &m) { m.functions[0].objectSlots[32].mutableValue = true; },
        "snapshot must be readonly");
    rejectComposed(
        "constructor argument aliases receiver",
        [](Module &m) { composedCall(m).objectArguments[1] = 56; },
        "receiver aliases argument snapshot");
    rejectComposed(
        "constructor argument reused snapshot",
        [](Module &m) { composedCall(m).objectArguments[1] = 104; },
        "argument snapshots must be distinct");
    rejectComposed(
        "constructor argument wrong nominal class",
        [](Module &m) {
            m.functions[0].objectSlots[104].className = "Other";
            m.classLayouts["Other"].clear();
        },
        "argument nominal class mismatch");
    rejectComposed(
        "constructor argument incomplete snapshot",
        [](Module &m) { m.functions[0].code.erase(m.functions[0].code.begin() + 6); },
        "not fully initialized");
    rejectComposed(
        "constructor argument scalar operand missing",
        [](Module &m) { m.functions[0].code.erase(m.functions[0].code.begin() + 14); },
        "value stack underflow");
    rejectComposed(
        "constructor parameter mutable rejected",
        [](Module &m) { m.functions[1].objectSlots[24].mutableValue = true; },
        "object parameter must be readonly");
    rejectComposed(
        "ordinary method class parameter rejected",
        [](Module &m) { m.functions[1].receiver->constructor = false; },
        "receiver signatures must remain scalar");
    rejectComposed(
        "constructor class result rejected",
        [](Module &m) { m.functions[1].result = Type("Outer"); },
        "receiver signatures must remain scalar");
    rejectComposed(
        "nested metadata wrong flattened length",
        [](Module &m) { m.classFields["Outer"][1].length = 1; },
        "nested class field length mismatch");
    rejectComposed(
        "nested metadata wrong leaf type", [](Module &m) { m.classLayouts["Leaf"][0] = Type::U64; },
        "nested class field leaf type mismatch");
    rejectComposed(
        "nested metadata missing class",
        [](Module &m) { m.classFields["Outer"][1].elementType = Type("Missing"); },
        "invalid nominal nested class field");
    rejectComposed(
        "nested metadata array class forbidden",
        [](Module &m) { m.classFields["Outer"][1].array = true; },
        "invalid nominal nested class field");
    rejectComposed(
        "nested metadata unresolved specialization",
        [](Module &m) {
            m.classFields["Outer"][1].elementType.templateArguments = {TypeKind::I64};
        },
        "invalid nominal nested class field");
    rejectComposed(
        "nested metadata overlap", [](Module &m) { m.classFields["Outer"][1].firstLeaf = 0; },
        "invalid logical class field shape");
    rejectComposed(
        "nested metadata negative length", [](Module &m) { m.classFields["Outer"][2].length = -1; },
        "nested class field length mismatch");
    for (const Type &invalid : {Type::Ref, Type::MutRef, Type::Own})
        rejectComposed(
            "nested metadata nonvalue " + typeName(invalid),
            [=](Module &m) { m.classFields["Outer"][1].elementType = invalid; },
            "invalid logical class field shape");
    rejectComposed(
        "empty nested self cycle",
        [](Module &m) { m.classFields["Empty"] = {{Type("Empty"), 0, 0, false}}; },
        "cyclic nested class layout");
    rejectComposed(
        "empty nested indirect cycle",
        [](Module &m) {
            m.classLayouts["AnotherEmpty"] = {};
            m.classFields["AnotherEmpty"] = {{Type("Empty"), 0, 0, false}};
            m.classFields["Empty"] = {{Type("AnotherEmpty"), 0, 0, false}};
        },
        "cyclic nested class layout");
    auto depth = baseline();
    depth.classLayouts["D1"] = {Type::I64};
    for (int count = 2; count <= 4; ++count) {
        depth.classLayouts["D" + std::to_string(count)] = {Type::I64};
        depth.classFields["D" + std::to_string(count)] = {
            {Type("D" + std::to_string(count - 1)), 0, 1, false}};
    }
    accept("nested depth exactly four", depth);
    rejectModule(
        "nested depth five rejected", depth,
        [](Module &m) {
            m.classLayouts["D5"] = {Type::I64};
            m.classFields["D5"] = {{Type("D4"), 0, 1, false}};
        },
        "exceeds depth 4");
    auto capacity = baseline();
    capacity.classLayouts["Child"] = std::vector<Type>(64, Type::I64);
    capacity.classLayouts["Parent"] = capacity.classLayouts["Child"];
    capacity.classFields["Parent"] = {{Type("Child"), 0, 64, false}};
    accept("composed capacity exactly 64 scalar leaves", capacity);
    rejectModule(
        "composed capacity 65 leaves rejected", capacity,
        [](Module &m) {
            m.classLayouts["Parent"].push_back(Type::I64);
            m.classFields["Parent"].push_back({Type::I64, 64, 1, false});
        },
        "exceeds 64 scalar leaves");
    auto rejectEmpty = [&](const std::string &name, const std::function<void(Module &)> &change,
                           const std::string &expected) {
        rejectModule(name, composedEmptyBaseline(), change, expected);
    };
    rejectEmpty(
        "empty nested copy cannot forge initialization",
        [](Module &m) { m.functions[0].code.erase(m.functions[0].code.begin() + 2); },
        "nested class field not completely initialized");
    rejectEmpty(
        "empty nested constructor missing logical initialization",
        [](Module &m) { m.functions[1].code.erase(m.functions[1].code.begin() + 1); },
        "returns before all class fields initialized");
    rejectEmpty(
        "empty nested destination still owns one storage word",
        [](Module &m) { m.functions[0].slots[16] = Type::I64; },
        "scalar slot overlaps empty object");
    rejectEmpty(
        "empty nested duplicate whole copy rejected",
        [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 7, CopyObject{16, 32});
        },
        "already initialized");
    rejectEmpty(
        "empty nested missing init on one branch",
        [](Module &m) {
            auto &code = m.functions[1].code;
            code.insert(code.begin() + 1, {Constant{1, Type::Bool}, BranchFalse{1}});
            code.insert(code.begin() + 4, Label{1});
        },
        "returns before all class fields initialized");
    rejectEmpty(
        "empty nested duplicate init through backedge",
        [](Module &m) {
            auto &code = m.functions[1].code;
            code.insert(code.begin() + 1, Label{1});
            code.insert(code.begin() + 3, {Constant{1, Type::Bool}, BranchFalse{1}});
        },
        "class field initialized more than once");
    rejectEmpty(
        "empty nested logical completion reset by lifetime",
        [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 3,
                                       {EndObject{16}, BeginObject{16}});
        },
        "nested class field not completely initialized");
    const auto assembly = X86Emitter{}.emit(validate(composedBaseline()));
    const auto start = assembly.find("construct_outer:\n");
    if (start == std::string::npos ||
        assembly.find("movq %r10, -56(%rbp)", start) == std::string::npos ||
        assembly.find("movq %r11, -64(%rbp)", start) == std::string::npos)
        throw Error("constructor receiver and packed argument record share private storage");
    ++passed;
    std::cout << "PASS IR constructor receiver and argument record use distinct private slots\n";
}

} // namespace
int main(int argc, char **argv) {
    try {
        if (argc == 2 && std::string(argv[1]) == "--emit-value-abi") {
            std::cout << X86Emitter{}.emit(validate(valueBaseline()));
            return 0;
        }
        if (argc == 2 && std::string(argv[1]) == "--emit-u64") {
            std::cout << X86Emitter{}.emit(validate(unsignedOperations()));
            return 0;
        }
        if (argc == 2 && std::string(argv[1]) == "--emit-array-fields") {
            std::cout << X86Emitter{}.emit(validate(arrayNativeModule()));
            return 0;
        }
        if (argc == 2 && std::string(argv[1]) == "--emit-composed-fields") {
            std::cout << X86Emitter{}.emit(validate(composedNativeModule()));
            return 0;
        }
        composedTests();
        arrayReceiverTests();
        unsignedTests();
        for (const auto operation : {Binary::CheckedDivide, Binary::CheckedRemainder}) {
            const auto name = operation == Binary::CheckedDivide ? "division" : "remainder";
            auto arithmetic = baseline();
            arithmetic.functions[0].code = {Constant{84, Type::I64}, Push{}, Constant{2, Type::I64},
                                            BinaryValue{operation}, Return{}};
            accept(std::string("typed checked ") + name, arithmetic);
            rejectModule(
                std::string(name) + " bool right operand", arithmetic,
                [](Module &module) { module.functions[0].code[2] = Constant{1, Type::Bool}; },
                "mistyped current");
            rejectModule(
                std::string(name) + " bool left operand", arithmetic,
                [](Module &module) { module.functions[0].code[0] = Constant{1, Type::Bool}; },
                "noninteger left operand");
            rejectModule(
                std::string(name) + " missing left operand", arithmetic,
                [](Module &module) {
                    module.functions[0].code.erase(module.functions[0].code.begin() + 1);
                },
                "stack underflow");
            auto emission = X86Emitter{}.emit(validate(arithmetic));
            const auto zero = emission.find("jz .Laurora_division_zero_trap");
            const auto checked = emission.find("cmpq $-1, %r11");
            const auto division = emission.find("idivq %r11");
            if (zero == std::string::npos || checked == std::string::npos ||
                division == std::string::npos || !(zero < checked && checked < division))
                throw Error("native division must retain zero and overflow checks before IDIV");
            ++passed;
            std::cout << "PASS IR " << name << " guard ordering\n";
        }
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
        rejectReceiver(
            "missing class layout", [](Module &m) { m.classLayouts.clear(); },
            "unknown object class");
        rejectReceiver(
            "non-scalar class layout", [](Module &m) { m.classLayouts["Pair"][0] = Type::Ref; },
            "non-scalar class layout");
        rejectReceiver(
            "unknown bound receiver nominal type",
            [](Module &m) { m.functions[2].receiver->className = "Unknown"; },
            "unknown receiver class");
        rejectReceiver(
            "forged object type",
            [](Module &m) {
                m.classLayouts["Other"] = m.classLayouts["Pair"];
                m.functions[0].objectSlots[16].className = "Other";
            },
            "nominal class mismatch");
        rejectReceiver(
            "forged object scalar layout", [](Module &m) { m.functions[0].slots[8] = Type::I64; },
            "object field slot type/layout mismatch");
        rejectReceiver(
            "missing object field slot", [](Module &m) { m.functions[0].slots.erase(8); },
            "object field slot type/layout mismatch");
        rejectReceiver(
            "overlapping object layouts",
            [](Module &m) {
                m.classLayouts["Small"] = {Type::Bool};
                m.functions[0].objectSlots[8] = ObjectSlot{"Small", true};
            },
            "overlapping object layouts");
        rejectReceiver(
            "object base underflows layout",
            [](Module &m) {
                m.functions[0].objectSlots.clear();
                m.functions[0].objectSlots[8] = ObjectSlot{"Pair", true};
            },
            "invalid object layout offset");
        rejectReceiver(
            "object base outside frame",
            [](Module &m) { m.functions[0].objectSlots[24] = ObjectSlot{"Pair", true}; },
            "invalid object layout offset");
        rejectReceiver(
            "receiver load without bound receiver",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin(), ReceiverLoad{0, Type::I64});
            },
            "without bound receiver");
        rejectReceiver(
            "receiver store without bound receiver",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin() + 2,
                                           ReceiverStore{0, Type::I64});
            },
            "without bound receiver");
        rejectReceiver(
            "negative receiver field",
            [](Module &m) { m.functions[2].code[0] = ReceiverLoad{-1, Type::I64}; },
            "receiver field type/layout");
        rejectReceiver(
            "receiver field past layout",
            [](Module &m) { m.functions[2].code[0] = ReceiverLoad{2, Type::I64}; },
            "receiver field type/layout");
        rejectReceiver(
            "receiver field type forged",
            [](Module &m) { m.functions[2].code[0] = ReceiverLoad{1, Type::I64}; },
            "receiver field type/layout");
        rejectReceiver(
            "receiver cannot become scalar",
            [](Module &m) { m.functions[2].code[0] = ReceiverLoad{0, Type::Ref}; },
            "receiver field type/layout");
        rejectReceiver(
            "receiver write through readonly capability",
            [](Module &m) {
                m.functions[2].code = {Constant{42, Type::I64}, ReceiverStore{0, Type::I64},
                                       Return{}};
            },
            "write through const receiver");
        rejectReceiver(
            "scalar call receiver bypass",
            [](Module &m) { m.functions[0].code[6] = Call{"get_pair"}; },
            "plain call cannot target receiver");
        rejectReceiver(
            "method call scalar target",
            [](Module &m) { m.functions[0].code[6] = MethodCall{"test", 16}; },
            "method call requires receiver target");
        rejectReceiver(
            "unknown method", [](Module &m) { m.functions[0].code[6] = MethodCall{"missing", 16}; },
            "unknown method call target");
        rejectReceiver(
            "method requires exact object base",
            [](Module &m) { m.functions[0].code[6] = MethodCall{"get_pair", 8}; },
            "not an object slot");
        rejectReceiver(
            "method rejects negative base",
            [](Module &m) { m.functions[0].code[6] = MethodCall{"get_pair", -16}; },
            "invalid method receiver offset");
        rejectReceiver(
            "receiver cannot alias arbitrary scalar",
            [](Module &m) {
                m.functions[0].objectSlots.clear();
                m.functions[0].code.erase(m.functions[0].code.begin());
            },
            "not an object slot");
        rejectReceiver(
            "forwarding requires receiver",
            [](Module &m) { m.functions[0].code[6] = MethodCall{"get_pair", 0}; },
            "forwarding without bound receiver");
        rejectReceiver(
            "forwarding preserves nominal identity",
            [](Module &m) {
                m.classLayouts["Other"] = m.classLayouts["Pair"];
                m.functions[2].receiver->className = "Other";
            },
            "forwarded receiver nominal class mismatch");
        rejectReceiver(
            "const receiver cannot forward exclusively",
            [](Module &m) { m.functions[2].receiver->mutableValue = true; },
            "const receiver cannot forward mutable");
        rejectReceiver(
            "const local cannot supply mutable receiver",
            [](Module &m) { m.functions[3].receiver->mutableValue = true; },
            "const object cannot supply mutable");
        rejectReceiver(
            "constructor requires mutable receiver",
            [](Module &m) { m.functions[1].receiver->mutableValue = false; },
            "invalid constructor receiver signature");
        rejectReceiver(
            "constructor requires i64 internal result",
            [](Module &m) { m.functions[1].result = Type::Bool; },
            "invalid constructor receiver signature");
        rejectReceiver(
            "constructor missing field",
            [](Module &m) {
                m.functions[1].code.erase(m.functions[1].code.begin() + 4,
                                          m.functions[1].code.begin() + 6);
            },
            "before all fields initialized");
        rejectReceiver(
            "constructor duplicate field",
            [](Module &m) {
                m.functions[1].code.insert(m.functions[1].code.begin() + 4,
                                           ReceiverStore{0, Type::I64});
            },
            "field initialized more than once");
        rejectReceiver(
            "constructor receiver read even after final write",
            [](Module &m) { m.functions[1].code[6] = ReceiverLoad{0, Type::I64}; },
            "constructor cannot read receiver");
        rejectReceiver(
            "constructor cannot forward receiver",
            [](Module &m) { m.functions[1].code[6] = MethodCall{"get_pair", 0}; },
            "constructor cannot forward receiver");
        rejectReceiver(
            "ordinary method cannot forward as constructor",
            [](Module &m) {
                m.functions[3].code = {Constant{42, Type::I64},         Push{},
                                       Constant{1, Type::Bool},         Push{},
                                       MethodCall{"construct_pair", 0}, Return{}};
            },
            "constructor cannot forward receiver");
        rejectReceiver(
            "method requires full object initialization",
            [](Module &m) {
                m.functions[0].code = {BeginObject{16}, Constant{42, Type::I64},
                                       Store{16, Type::I64}, MethodCall{"get_pair", 16}, Return{}};
            },
            "object not fully initialized");
        rejectReceiver(
            "constructor rejects partially initialized object",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin() + 2, Store{16, Type::I64});
            },
            "requires uninitialized object");
        rejectReceiver(
            "constructor cannot run twice",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin() + 6,
                                           {Constant{42, Type::I64}, Push{},
                                            Constant{1, Type::Bool}, Push{},
                                            MethodCall{"construct_pair", 16}});
            },
            "constructor called more than once");
        rejectReceiver(
            "constructor argument type",
            [](Module &m) { m.functions[0].code[3] = Constant{1, Type::I64}; },
            "method argument type mismatch");
        rejectReceiver(
            "constructor argument underflow",
            [](Module &m) { m.functions[0].code.erase(m.functions[0].code.begin() + 4); },
            "method argument type mismatch");
        rejectReceiver(
            "const object field direct overwrite",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin() + 6, Store{16, Type::I64});
            },
            "write to initialized const object");
        rejectReceiver(
            "const object field indexed overwrite",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin() + 6,
                                           {Constant{0, Type::I64}, BoundsGuard{16, 1, Type::I64},
                                            Push{}, Constant{1, Type::I64},
                                            IndexStore{16, 1, Type::I64}});
            },
            "indexed write to const object");
        rejectReceiver(
            "object cannot forge scalar borrow capability",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin() + 6,
                                           BorrowHandle{16, Type::Ref});
            },
            "object field cannot become a scalar borrow handle");
        rejectReceiver(
            "parameter cannot alias object",
            [](Module &m) {
                auto &f = m.functions[0];
                f.parameters = {Type::I64};
                f.code.insert(f.code.begin(), BindParameter{0, 16, Type::I64});
            },
            "parameter cannot bind object field");
        rejectReceiver(
            "self-recursive receiver",
            [](Module &m) { m.functions[2].code = {MethodCall{"get_pair", 0}, Return{}}; },
            "recursive receiver call cycle");
        rejectReceiver(
            "mutually recursive receivers",
            [](Module &m) { m.functions[2].code = {MethodCall{"relay_pair", 0}, Return{}}; },
            "recursive receiver call cycle");
        rejectReceiver(
            "receiver recursion through scalar intermediary",
            [](Module &m) { m.functions[2].code = {Call{"test"}, Return{}}; },
            "recursive receiver call cycle");
        rejectReceiver(
            "unreachable receiver instruction",
            [](Module &m) { m.functions[2].code.push_back(ReceiverStore{0, Type::I64}); },
            "unreachable semantic instruction");
        rejectReceiver(
            "constructor conditional field omitted",
            [](Module &m) {
                m.functions[1].code = {BindParameter{0, 8, Type::I64},
                                       BindParameter{1, 16, Type::Bool},
                                       Constant{1, Type::Bool},
                                       BranchFalse{1},
                                       Constant{42, Type::I64},
                                       ReceiverStore{0, Type::I64},
                                       Label{1},
                                       Constant{1, Type::Bool},
                                       ReceiverStore{1, Type::Bool},
                                       Constant{0, Type::I64},
                                       Return{}};
            },
            "before all fields initialized");
        rejectReceiver(
            "constructor conditional duplicate field",
            [](Module &m) {
                m.functions[1].code = {BindParameter{0, 8, Type::I64},
                                       BindParameter{1, 16, Type::Bool},
                                       Constant{1, Type::Bool},
                                       BranchFalse{1},
                                       Constant{42, Type::I64},
                                       ReceiverStore{0, Type::I64},
                                       Label{1},
                                       Constant{42, Type::I64},
                                       ReceiverStore{0, Type::I64},
                                       Constant{1, Type::Bool},
                                       ReceiverStore{1, Type::Bool},
                                       Constant{0, Type::I64},
                                       Return{}};
            },
            "field initialized more than once");
        rejectReceiver(
            "constructor loop duplicate field",
            [](Module &m) {
                m.functions[1].code = {BindParameter{0, 8, Type::I64},
                                       BindParameter{1, 16, Type::Bool},
                                       Label{1},
                                       Constant{42, Type::I64},
                                       ReceiverStore{0, Type::I64},
                                       Constant{1, Type::Bool},
                                       BranchFalse{1},
                                       ReceiverStore{1, Type::Bool},
                                       Constant{0, Type::I64},
                                       Return{}};
            },
            "field initialized more than once");
        rejectReceiver(
            "conditional object initialization before construction",
            [](Module &m) {
                auto &f = m.functions[0];
                f.objectSlots[16].mutableValue = true;
                f.code.insert(f.code.begin() + 1,
                              {Constant{1, Type::Bool}, BranchFalse{1}, Constant{42, Type::I64},
                               Store{16, Type::I64}, Label{1}});
            },
            "requires uninitialized object");
        auto aggregateReceiver = receiverBaseline();
        aggregateReceiver.functions[0].code = {BeginObject{16},
                                               Constant{42, Type::I64},
                                               Store{16, Type::I64},
                                               Constant{1, Type::Bool},
                                               Store{8, Type::Bool},
                                               MethodCall{"get_pair", 16},
                                               Return{}};
        accept("fully initialized aggregate supplies receiver", aggregateReceiver);
        auto mutableReceiver = receiverBaseline();
        mutableReceiver.functions[0].objectSlots[16].mutableValue = true;
        mutableReceiver.functions[3].receiver->mutableValue = true;
        mutableReceiver.functions[3].code = {Constant{41, Type::I64},   ReceiverStore{0, Type::I64},
                                             Constant{42, Type::I64},   ReceiverStore{0, Type::I64},
                                             MethodCall{"get_pair", 0}, Return{}};
        accept("mutable receiver reborrow downgrades and returns", mutableReceiver);
        auto scalarHelper = receiverBaseline();
        auto helper = baseline().functions[0];
        helper.name = "helper";
        scalarHelper.functions.push_back(helper);
        scalarHelper.functions[2].code.insert(scalarHelper.functions[2].code.begin(),
                                              Call{"helper"});
        accept("receiver function ordinary scalar helper", scalarHelper);
        auto scalarRecursive = baseline();
        scalarRecursive.functions[0].code.insert(scalarRecursive.functions[0].code.begin(),
                                                 Call{"test"});
        accept("pure scalar recursion stays supported", scalarRecursive);
        auto branchConstructor = receiverBaseline();
        branchConstructor.functions[1].code = {BindParameter{0, 8, Type::I64},
                                               BindParameter{1, 16, Type::Bool},
                                               Constant{1, Type::Bool},
                                               BranchFalse{1},
                                               Constant{42, Type::I64},
                                               ReceiverStore{0, Type::I64},
                                               Jump{2},
                                               Label{1},
                                               Constant{42, Type::I64},
                                               ReceiverStore{0, Type::I64},
                                               Label{2},
                                               Constant{1, Type::Bool},
                                               ReceiverStore{1, Type::Bool},
                                               Constant{0, Type::I64},
                                               Return{}};
        accept("constructor disjoint branch initialization", branchConstructor);
        auto emptyReceiver = receiverBaseline();
        emptyReceiver.classLayouts["Pair"].clear();
        emptyReceiver.functions[0].slots.clear();
        emptyReceiver.functions[1].code = {BindParameter{0, 8, Type::I64},
                                           BindParameter{1, 16, Type::Bool}, Constant{0, Type::I64},
                                           Return{}};
        emptyReceiver.functions[2].code = {Constant{42, Type::I64}, Return{}};
        accept("empty object reserves private receiver storage", emptyReceiver);
        rejectModule(
            "empty object constructor cannot repeat", emptyReceiver,
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin() + 6,
                                           {Constant{42, Type::I64}, Push{},
                                            Constant{1, Type::Bool}, Push{},
                                            MethodCall{"construct_pair", 16}});
            },
            "constructor called more than once");
        rejectModule(
            "empty object cannot alias scalar slot", emptyReceiver,
            [](Module &m) { m.functions[0].slots[16] = Type::I64; },
            "scalar slot overlaps empty object");
        rejectReceiver(
            "object method before lifetime begin",
            [](Module &m) { m.functions[0].code.erase(m.functions[0].code.begin()); },
            "outside active object lifetime");
        rejectReceiver(
            "object field store before lifetime begin",
            [](Module &m) {
                m.functions[0].code = {Constant{42, Type::I64}, Store{16, Type::I64}, Return{}};
            },
            "outside active lifetime");
        rejectReceiver(
            "object field load after lifetime end",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin() + 6,
                                           {EndObject{16}, Load{16, Type::I64}});
            },
            "outside active lifetime");
        rejectReceiver(
            "object indexed access after lifetime end",
            [](Module &m) {
                m.functions[0].code.insert(
                    m.functions[0].code.begin() + 6,
                    {EndObject{16}, Constant{0, Type::I64}, BoundsGuard{16, 1, Type::I64}});
            },
            "outside active lifetime");
        rejectReceiver(
            "object method after lifetime end",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin() + 6, EndObject{16});
            },
            "outside active object lifetime");
        rejectReceiver(
            "object double begin",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin(), BeginObject{16});
            },
            "lifetime already active");
        rejectReceiver(
            "object end before begin",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin(), EndObject{16});
            },
            "lifetime is not active");
        rejectReceiver(
            "object double end",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin() + 6,
                                           {EndObject{16}, EndObject{16}});
            },
            "lifetime is not active");
        rejectReceiver(
            "object begin requires exact base",
            [](Module &m) { m.functions[0].code[0] = BeginObject{8}; },
            "lifetime operation requires exact object slot");
        rejectReceiver(
            "object end requires exact base",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin() + 6, EndObject{8});
            },
            "lifetime operation requires exact object slot");
        rejectReceiver(
            "new lifetime cannot inherit initialized fields",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin() + 6,
                                           {EndObject{16}, BeginObject{16}});
            },
            "object not fully initialized");
        rejectReceiver(
            "branch cannot skip lifetime end",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.end() - 1,
                                           {Constant{1, Type::Bool}, BranchFalse{1}, EndObject{16},
                                            Label{1}, Constant{42, Type::I64}});
            },
            "incompatible active object lifetimes");
        rejectReceiver(
            "branch cannot skip lifetime begin",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin(),
                                           {Constant{1, Type::Bool}, BranchFalse{1}, Jump{2},
                                            Label{1}, BeginObject{16}, Label{2}});
            },
            "incompatible active object lifetimes");
        rejectReceiver(
            "loop cannot silently restart active object",
            [](Module &m) {
                auto &code = m.functions[0].code;
                code.insert(code.begin(), Label{1});
                code.insert(code.end() - 1,
                            {Constant{1, Type::Bool}, BranchFalse{1}, Constant{42, Type::I64}});
            },
            "incompatible active object lifetimes");
        auto lifetimeReuse = receiverBaseline();
        lifetimeReuse.functions[0].code.insert(
            lifetimeReuse.functions[0].code.begin() + 6,
            {EndObject{16}, BeginObject{16}, Constant{42, Type::I64}, Push{},
             Constant{1, Type::Bool}, Push{}, MethodCall{"construct_pair", 16}});
        accept("new lifetime permits constructing same storage again", lifetimeReuse);
        auto lifetimeLoop = receiverBaseline();
        lifetimeLoop.functions[0].code.insert(lifetimeLoop.functions[0].code.begin(), Label{1});
        lifetimeLoop.functions[0].code.insert(
            lifetimeLoop.functions[0].code.end() - 1,
            {EndObject{16}, Constant{1, Type::Bool}, BranchFalse{1}, Constant{42, Type::I64}});
        accept("const constructor object lifetime ends before loop backedge", lifetimeLoop);
        auto aggregateLoop = aggregateReceiver;
        aggregateLoop.functions[0].code.insert(aggregateLoop.functions[0].code.begin(), Label{1});
        aggregateLoop.functions[0].code.insert(
            aggregateLoop.functions[0].code.end() - 1,
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
        rejectModule(
            "deep scalar bridge cannot hide receiver cycle", deepCalls,
            [](Module &m) {
                const auto name = m.functions.back().name;
                m.functions.back() = m.functions[0];
                m.functions.back().name = name;
            },
            "recursive receiver call cycle");
        deepCalls.functions.back().code = {Call{"deep_helper0"}, Return{}};
        accept("receiver may call a pure scalar recursive component", deepCalls);

        accept("class arguments and result use independent value storage", valueBaseline());
        rejectValue(
            "unknown value call", [](Module &m) { valueCall(m).callee = "missing"; },
            "unknown aggregate call");
        rejectValue(
            "missing value argument vector",
            [](Module &m) { valueCall(m).objectArguments.clear(); }, "vector size");
        rejectValue(
            "extra value argument vector entry",
            [](Module &m) { valueCall(m).objectArguments.push_back(0); }, "vector size");
        rejectValue(
            "scalar argument cannot contain object base",
            [](Module &m) { valueCall(m).objectArguments[1] = 16; }, "scalar argument cannot");
        rejectValue(
            "class argument cannot be scalar zero",
            [](Module &m) { valueCall(m).objectArguments[0] = 0; }, "exact object slot");
        rejectValue(
            "class argument cannot be negative",
            [](Module &m) { valueCall(m).objectArguments[0] = -16; }, "exact object slot");
        rejectValue(
            "class argument requires exact base",
            [](Module &m) { valueCall(m).objectArguments[0] = 8; }, "exact object slot");
        rejectValue(
            "argument snapshots cannot alias",
            [](Module &m) { valueCall(m).objectArguments[2] = 16; }, "snapshots must be distinct");
        rejectValue(
            "argument nominal class identity",
            [](Module &m) {
                m.classLayouts["Other"] = m.classLayouts["Pair"];
                m.functions[0].objectSlots[16].className = "Other";
            },
            "argument nominal class");
        rejectValue(
            "argument snapshot readonly",
            [](Module &m) { m.functions[0].objectSlots[16].mutableValue = true; },
            "snapshot must be readonly");
        rejectValue(
            "argument snapshot inactive",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin() + 15, EndObject{16});
            },
            "argument outside active");
        rejectValue(
            "argument snapshot partially initialized",
            [](Module &m) { m.functions[0].code.erase(m.functions[0].code.begin() + 4); },
            "argument object not fully");
        rejectValue(
            "argument snapshot uninitialized",
            [](Module &m) {
                auto &code = m.functions[0].code;
                code.erase(code.begin() + 1, code.begin() + 5);
            },
            "argument object not fully");
        rejectValue(
            "argument scalar type mismatch",
            [](Module &m) { m.functions[0].code[12] = Constant{1, Type::I64}; },
            "scalar argument type");
        rejectValue(
            "argument missing scalar operand",
            [](Module &m) { m.functions[0].code.erase(m.functions[0].code.begin() + 13); },
            "scalar argument type");
        rejectValue(
            "result cannot be zero", [](Module &m) { valueCall(m).resultOffset = 0; },
            "result requires exact");
        rejectValue(
            "result cannot be negative", [](Module &m) { valueCall(m).resultOffset = -48; },
            "result requires exact");
        rejectValue(
            "result cannot be interior field", [](Module &m) { valueCall(m).resultOffset = 40; },
            "result requires exact");
        rejectValue(
            "result cannot alias snapshot", [](Module &m) { valueCall(m).resultOffset = 16; },
            "result aliases argument");
        rejectValue(
            "result nominal class identity",
            [](Module &m) {
                m.classLayouts["Other"] = m.classLayouts["Pair"];
                m.functions[0].objectSlots[48].className = "Other";
            },
            "result nominal class");
        rejectValue(
            "result lifetime required",
            [](Module &m) { m.functions[0].code.erase(m.functions[0].code.begin() + 14); },
            "result outside active");
        rejectValue(
            "result pristine field requirement",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin() + 15,
                                           {Constant{0, Type::I64}, Store{48, Type::I64}});
            },
            "result requires uninitialized");
        rejectValue(
            "result cannot initialize twice",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin() + 16,
                                           {Constant{10, Type::I64}, Push{},
                                            Constant{1, Type::Bool}, Push{},
                                            AggregateCall{"copy_pair", {16, 0, 32, 0}, 48}});
            },
            "result object already initialized");
        rejectValue(
            "result cannot conditionally initialize twice",
            [](Module &m) {
                auto &code = m.functions[0].code;
                code.insert(code.begin() + 16,
                            {Constant{1, Type::Bool}, BranchFalse{1}, EndObject{48},
                             BeginObject{48}, Label{1}, Constant{10, Type::I64}, Push{},
                             Constant{1, Type::Bool}, Push{},
                             AggregateCall{"copy_pair", {16, 0, 32, 0}, 48}});
            },
            "result object already initialized");
        rejectValue(
            "result scalar current cannot carry class capability",
            [](Module &m) { m.functions[0].code.erase(m.functions[0].code.begin() + 16); },
            "mistyped current");
        rejectValue(
            "plain call cannot bypass value ABI",
            [](Module &m) { m.functions[0].code[15] = Call{"copy_pair"}; },
            "plain call cannot target aggregate");
        rejectValue(
            "object return exact slot",
            [](Module &m) { m.functions[1].code.back() = ReturnObject{56}; },
            "return requires exact");
        rejectValue(
            "object return nominal identity",
            [](Module &m) {
                m.classLayouts["Other"] = m.classLayouts["Pair"];
                m.functions[1].objectSlots[64].className = "Other";
            },
            "return nominal class");
        rejectValue(
            "object return active lifetime",
            [](Module &m) {
                m.functions[1].code.insert(m.functions[1].code.end() - 1, EndObject{64});
            },
            "return outside active");
        rejectValue(
            "object return complete initialization",
            [](Module &m) { m.functions[1].code.erase(m.functions[1].code.end() - 2); },
            "returned object not fully");
        rejectValue(
            "object return balanced scalar stack",
            [](Module &m) { m.functions[1].code.insert(m.functions[1].code.end() - 1, Push{}); },
            "unbalanced stack at object return");
        rejectValue(
            "scalar return cannot bypass value ABI",
            [](Module &m) { m.functions[1].code.back() = Return{}; },
            "scalar return cannot return class");
        rejectValue(
            "object return cannot bypass scalar result",
            [](Module &m) { m.functions[0].code.back() = ReturnObject{48}; },
            "object return requires class");
        rejectValue(
            "object bind cannot use scalar instruction",
            [](Module &m) { m.functions[1].code[0] = BindParameter{0, 16, Type("Pair")}; },
            "entry prefix");
        rejectValue(
            "scalar bind cannot use object instruction",
            [](Module &m) { m.functions[1].code[1] = BindObjectParameter{1, 16, "Pair"}; },
            "entry prefix");
        rejectValue(
            "object bind wrong index",
            [](Module &m) { m.functions[1].code[0] = BindObjectParameter{1, 16, "Pair"}; },
            "entry prefix");
        rejectValue(
            "object bind wrong declared class",
            [](Module &m) { m.functions[1].code[0] = BindObjectParameter{0, 16, "Other"}; },
            "object parameter type");
        rejectValue(
            "object bind wrong slot class",
            [](Module &m) {
                m.classLayouts["Other"] = m.classLayouts["Pair"];
                m.functions[1].objectSlots[16].className = "Other";
            },
            "object parameter nominal");
        rejectValue(
            "object bind requires exact slot",
            [](Module &m) { m.functions[1].code[0] = BindObjectParameter{0, 8, "Pair"}; },
            "object parameter requires exact");
        rejectValue(
            "object bind readonly requirement",
            [](Module &m) { m.functions[1].objectSlots[16].mutableValue = true; },
            "object parameter must be readonly");
        rejectValue(
            "object parameters cannot alias",
            [](Module &m) { m.functions[1].code[2] = BindObjectParameter{2, 16, "Pair"}; },
            "object parameter bindings overlap");
        rejectValue(
            "object bind outside prefix",
            [](Module &m) {
                m.functions[1].code.insert(m.functions[1].code.begin() + 4,
                                           BindObjectParameter{0, 16, "Pair"});
            },
            "outside entry prefix");
        rejectValue(
            "object parameter cannot restart lifetime",
            [](Module &m) {
                m.functions[1].code.insert(m.functions[1].code.begin() + 4,
                                           {EndObject{16}, BeginObject{16}});
            },
            "parameter lifetime cannot restart");
        rejectValue(
            "object parameter cannot overwrite field",
            [](Module &m) {
                m.functions[1].code.insert(m.functions[1].code.begin() + 4,
                                           {Constant{9, Type::I64}, Store{16, Type::I64}});
            },
            "write to initialized const");
        rejectValue(
            "scalar value-call parameter immutable",
            [](Module &m) {
                m.functions[1].code.insert(m.functions[1].code.begin() + 4,
                                           {Constant{9, Type::I64}, Store{24, Type::I64}});
            },
            "immutable scalar parameter");
        rejectValue(
            "scalar value-call parameter indexed immutable",
            [](Module &m) {
                m.functions[1].code.insert(m.functions[1].code.begin() + 4,
                                           {Constant{0, Type::I64}, BoundsGuard{24, 1, Type::I64},
                                            Push{}, Constant{9, Type::I64},
                                            IndexStore{24, 1, Type::I64}});
            },
            "indexed write to immutable scalar");
        rejectValue(
            "method aggregate result signature denied",
            [](Module &m) { m.functions[1].receiver = Receiver{"Pair", false, false}; },
            "aggregate call cannot target receiver");
        rejectValue(
            "value-call hidden frame slot inaccessible",
            [](Module &m) { m.functions[1].slots[72] = Type::I64; }, "invalid slot offset");
        rejectValue(
            "value-call class capabilities are not scalar slots",
            [](Module &m) { m.functions[1].slots[16] = Type("Pair"); }, "invalid slot payload");
        rejectValue(
            "value signature cannot contain reference",
            [](Module &m) { m.functions[0].parameters = {Type::Ref}; },
            "invalid value boundary type");
        rejectValue(
            "value signature cannot contain mutable reference",
            [](Module &m) { m.functions[0].result = Type::MutRef; }, "invalid value boundary type");
        rejectValue(
            "value signature cannot contain owner",
            [](Module &m) { m.functions[0].result = Type::Own; }, "invalid value boundary type");
        rejectValue(
            "value signature cannot contain array",
            [](Module &m) { m.functions[0].result = Type::array(TypeKind::I64, 1); },
            "invalid value boundary type");
        rejectValue(
            "value signature unknown nominal type",
            [](Module &m) { m.functions[0].result = Type("Missing"); },
            "unknown value boundary class");
        rejectValue(
            "value signature malformed class payload",
            [](Module &m) {
                m.functions[0].result = Type("Pair");
                m.functions[0].result.length = 1;
            },
            "invalid value boundary type");
        rejectValue(
            "value signature at most six parameters",
            [](Module &m) { m.functions[0].parameters = std::vector<Type>(7, Type("Pair")); },
            "too many parameters");
        rejectValue(
            "value boundary at most 64 fields",
            [](Module &m) {
                m.classLayouts["Large"] = std::vector<Type>(65, Type::I64);
                m.functions[0].result = Type("Large");
            },
            "exceeds 64 scalar fields");
        reject(
            "aggregate call cannot replace scalar call",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin(),
                                           AggregateCall{"test", {}, 0});
            },
            "requires aggregate signature");
        auto scalarValueResult = valueBaseline();
        scalarValueResult.functions[1].result = Type::I64;
        scalarValueResult.functions[1].code.back() = Load{64, Type::I64};
        scalarValueResult.functions[1].code.push_back(Return{});
        valueCall(scalarValueResult).resultOffset = 0;
        scalarValueResult.functions[0].code.erase(scalarValueResult.functions[0].code.begin() + 16);
        accept("value arguments with scalar result", scalarValueResult);
        rejectModule(
            "scalar result rejects object result storage", scalarValueResult,
            [](Module &m) { valueCall(m).resultOffset = 48; }, "scalar result cannot name");
        auto reusableValueResult = valueBaseline();
        reusableValueResult.functions[0].code.insert(
            reusableValueResult.functions[0].code.begin() + 16,
            {EndObject{48}, BeginObject{48}, Constant{10, Type::I64}, Push{},
             Constant{1, Type::Bool}, Push{}, AggregateCall{"copy_pair", {16, 0, 32, 0}, 48}});
        accept("result storage reused only after lifetime transition", reusableValueResult);
        auto mutableValueResult = valueBaseline();
        mutableValueResult.functions[0].objectSlots[48].mutableValue = true;
        mutableValueResult.functions[0].code.insert(
            mutableValueResult.functions[0].code.begin() + 16,
            {Constant{43, Type::I64}, Store{48, Type::I64}});
        accept("returned value has caller-selected mutability", mutableValueResult);
        auto retainedGuard = valueBaseline();
        retainedGuard.functions[0].code.insert(
            retainedGuard.functions[0].code.begin() + 10,
            {Constant{0, Type::I64}, BoundsGuard{16, 1, Type::I64}, Push{}});
        retainedGuard.functions[0].code.insert(retainedGuard.functions[0].code.end() - 1,
                                               {Pop{}, IndexLoad{16, 1, Type::I64}});
        accept("saved bounds token survives value call", retainedGuard);
        auto directParameterReturn = valueBaseline();
        directParameterReturn.functions[1].code.resize(4);
        directParameterReturn.functions[1].code.push_back(ReturnObject{16});
        accept("class parameter returned through independent caller result", directParameterReturn);
        auto emptyValues = emptyValueBaseline();
        accept("empty values use reserved distinct storage", emptyValues);
        rejectModule(
            "empty value result cannot initialize twice", emptyValues,
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin() + 3,
                                           AggregateCall{"copy_empty", {8}, 16});
            },
            "result object already initialized");
        rejectModule(
            "empty parameter cannot become result target", emptyValues,
            [](Module &m) {
                m.functions[1].code.insert(m.functions[1].code.begin() + 1,
                                           AggregateCall{"make_empty", {}, 8});
            },
            "result object already initialized");
        rejectModule(
            "empty result cannot alias empty argument", emptyValues,
            [](Module &m) { std::get<AggregateCall>(m.functions[0].code[2]).resultOffset = 8; },
            "result aliases argument");
        auto largeValue = emptyValues;
        largeValue.classLayouts["Empty"] = std::vector<Type>(64, Type::I64);
        for (auto &function : largeValue.functions) {
            function.slots.clear();
            function.objectSlots.clear();
            function.code.clear();
        }
        auto &largeEntry = largeValue.functions[0];
        largeEntry.frameBytes = 1024;
        largeEntry.objectSlots = {{512, ObjectSlot{"Empty", false}},
                                  {1024, ObjectSlot{"Empty", false}}};
        largeEntry.code = {BeginObject{512}, Constant{42, Type::I64}};
        for (int field = 0; field < 64; ++field) {
            largeEntry.slots[512 - field * 8] = Type::I64;
            largeEntry.slots[1024 - field * 8] = Type::I64;
            largeEntry.code.push_back(Store{512 - field * 8, Type::I64});
        }
        largeEntry.code.insert(largeEntry.code.end(),
                               {BeginObject{1024}, AggregateCall{"copy_empty", {512}, 1024},
                                Load{520, Type::I64}, Return{}});
        auto &largeCopy = largeValue.functions[1];
        largeCopy.frameBytes = 512;
        largeCopy.objectSlots[512] = ObjectSlot{"Empty", false};
        for (int field = 0; field < 64; ++field)
            largeCopy.slots[512 - field * 8] = Type::I64;
        largeCopy.code = {BindObjectParameter{0, 512, "Empty"}, ReturnObject{512}};
        largeValue.functions.pop_back();
        accept("64-field value boundary accepted", largeValue);
        auto receiverValueCycle = receiverBaseline();
        auto &valueGetter = receiverValueCycle.functions[2];
        valueGetter.frameBytes = 16;
        valueGetter.objectSlots[16] = ObjectSlot{"Pair", false};
        valueGetter.slots = {{16, Type::I64}, {8, Type::Bool}};
        valueGetter.code = {BeginObject{16},
                            ReceiverLoad{0, Type::I64},
                            Store{16, Type::I64},
                            ReceiverLoad{1, Type::Bool},
                            Store{8, Type::Bool},
                            AggregateCall{"value_bridge", {16}, 0},
                            Return{}};
        aurora::ir::Function valueBridge;
        valueBridge.name = "value_bridge";
        valueBridge.result = Type::I64;
        valueBridge.parameters = {Type("Pair")};
        valueBridge.frameBytes = 16;
        valueBridge.objectSlots[16] = ObjectSlot{"Pair", false};
        valueBridge.slots = {{16, Type::I64}, {8, Type::Bool}};
        valueBridge.code = {BindObjectParameter{0, 16, "Pair"}, MethodCall{"get_pair", 16},
                            Return{}};
        receiverValueCycle.functions.push_back(valueBridge);
        rejectModule(
            "aggregate edge cannot conceal receiver recursion", receiverValueCycle, [](Module &) {},
            "recursive receiver call cycle");
        receiverValueCycle.functions.back().code = {BindObjectParameter{0, 16, "Pair"},
                                                    Load{16, Type::I64}, Return{}};
        accept("receiver may call acyclic ordinary value helper", receiverValueCycle);
        rejectModule(
            "receiver aggregate parameter denied", receiverValueCycle,
            [](Module &m) {
                m.functions.back().receiver = Receiver{"Pair", false, false};
                m.functions[2].code[5] = MethodCall{"value_bridge", 16};
            },
            "receiver signatures must remain scalar");
        const auto valueAssembly = X86Emitter{}.emit(validate(valueBaseline()));
        for (const auto &fragment :
             {".local copy_pair", "movq %r11, -72(%rbp)", "movq %r10, -80(%rbp)", "movq %rsp, %r11",
              "leaq -48(%rbp), %r10", "movq 40(%r11), %rax", "movq %rax, 8(%r10)"})
            if (valueAssembly.find(fragment) == std::string::npos)
                throw Error(std::string("private value-call ABI emission mismatch: ") + fragment);
        ++passed;
        std::cout << "PASS IR private value ABI uses packed record and hidden result slot\n";

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
        reject(
            "unsubstituted template parameter result",
            [](Module &m) { m.functions[0].result = Type(TypeKind::Parameter); },
            "invalid value boundary type");
        reject(
            "unsubstituted template parameter slot",
            [](Module &m) { m.functions[0].slots[8] = Type(TypeKind::Parameter); },
            "invalid slot payload type");
        reject(
            "unsubstituted template parameter constant",
            [](Module &m) {
                std::get<Constant>(m.functions[0].code[0]).type = Type(TypeKind::Parameter);
            },
            "invalid constant type");
        rejectValue(
            "unresolved specialization arguments on result",
            [](Module &m) { m.functions[1].result.templateArguments = {TypeKind::I64}; },
            "invalid value boundary type");
        rejectValue(
            "unresolved specialization arguments on parameter",
            [](Module &m) { m.functions[1].parameters[0].templateArguments = {TypeKind::I64}; },
            "invalid value boundary type");
        rejectValue(
            "same-layout specialization argument forgery",
            [](Module &m) {
                m.classLayouts["OtherSpecialization"] = m.classLayouts["Pair"];
                m.functions[0].objectSlots[16].className = "OtherSpecialization";
            },
            "argument nominal class");
        rejectValue(
            "same-layout specialization result forgery",
            [](Module &m) {
                m.classLayouts["OtherSpecialization"] = m.classLayouts["Pair"];
                m.functions[0].objectSlots[48].className = "OtherSpecialization";
            },
            "result nominal class");
        rejectReceiver(
            "same-layout specialization receiver forgery",
            [](Module &m) {
                m.classLayouts["OtherSpecialization"] = m.classLayouts["Pair"];
                m.functions[2].receiver->className = "OtherSpecialization";
            },
            "forwarded receiver nominal class mismatch");
        std::cout << passed << " typed IR tests passed\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
