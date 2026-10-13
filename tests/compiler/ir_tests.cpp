#include "ir_verify.hpp"
#include "hosted_ir_metadata_writer.hpp"
#include "hosted_ir_instructions.hpp"
#include "x86.hpp"
#include <bit>
#include <functional>
#include <iostream>
#include <string>
#include <tuple>
#include <type_traits>

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
void rejectModule(const std::string &name,
                  Module module,
                  const std::function<void(Module &)> &mutate,
                  const std::string &expected) {
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
void reject(const std::string &name, const std::function<void(Module &)> &mutate, const std::string &expected) {
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
    caller.slots = {
        {16, Type::I64}, {8, Type::Bool}, {32, Type::I64}, {24, Type::Bool}, {48, Type::I64}, {40, Type::Bool}};
    caller.objectSlots = {
        {16, ObjectSlot{"Pair", false}}, {32, ObjectSlot{"Pair", false}}, {48, ObjectSlot{"Pair", false}}};
    caller.code = {BeginObject{16},
                   Constant{12, Type::I64},
                   Store{16, Type::I64},
                   Constant{1, Type::Bool},
                   Store{8, Type::Bool},
                   BeginObject{32},
                   Constant{20, Type::I64},
                   Store{32, Type::I64},
                   Constant{0, Type::Bool},
                   Store{24, Type::Bool},
                   Constant{10, Type::I64},
                   Push{},
                   Constant{1, Type::Bool},
                   Push{},
                   BeginObject{48},
                   AggregateCall{"copy_pair", {16, 0, 32, 0}, 48},
                   Load{48, Type::I64},
                   Return{}};
    aurora::ir::Function copy;
    copy.name = "copy_pair";
    copy.result = Type("Pair");
    copy.parameters = {Type("Pair"), Type::I64, Type("Pair"), Type::Bool};
    copy.frameBytes = 64;
    copy.slots = {{16, Type::I64},
                  {8, Type::Bool},
                  {24, Type::I64},
                  {40, Type::I64},
                  {32, Type::Bool},
                  {48, Type::Bool},
                  {64, Type::I64},
                  {56, Type::Bool}};
    copy.objectSlots = {
        {16, ObjectSlot{"Pair", false}}, {40, ObjectSlot{"Pair", false}}, {64, ObjectSlot{"Pair", false}}};
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
void rejectValue(const std::string &name, const std::function<void(Module &)> &mutate, const std::string &expected) {
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
    entry.code = {BeginObject{8},
                  InitializeEmptyObject{8},
                  BeginObject{16},
                  AggregateCall{"copy_empty", {8}, 16},
                  Constant{42, Type::I64},
                  Return{}};
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
    make.code = {BeginObject{8}, InitializeEmptyObject{8}, ReturnObject{8}};
    module.functions = {entry, copy, make};
    return module;
}
void rejectReceiver(const std::string &name, const std::function<void(Module &)> &mutate, const std::string &expected) {
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
    function.code = {Constant{std::bit_cast<std::int64_t>(UINT64_MAX), Type::U64},
                     Push{},
                     Constant{shift ? 0 : 1, shift ? Type::I64 : Type::U64},
                     BinaryValue{operation, Type::U64},
                     Return{}};
    return module;
}
Module unsignedOperations() {
    Module module;
    int index = 0;
    for (const auto operation : {Binary::CheckedAdd,
                                 Binary::CheckedSubtract,
                                 Binary::CheckedMultiply,
                                 Binary::CheckedDivide,
                                 Binary::CheckedRemainder,
                                 Binary::BitAnd,
                                 Binary::BitOr,
                                 Binary::BitXor,
                                 Binary::ShiftLeft,
                                 Binary::ShiftRight}) {
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
    for (const auto operation : {Comparison::Equal,
                                 Comparison::NotEqual,
                                 Comparison::Less,
                                 Comparison::Greater,
                                 Comparison::LessEqual,
                                 Comparison::GreaterEqual}) {
        auto function = module.functions[0];
        function.name = "unsigned_compare" + std::to_string(static_cast<int>(operation));
        function.result = Type::Bool;
        function.code[5] = Compare{operation, Type::U64};
        module.functions.push_back(std::move(function));
    }
    auto function = module.functions[0];
    function.name = "unsigned_not";
    function.parameters = {Type::U64};
    function.code = {BindParameter{0, 8, Type::U64}, Load{8, Type::U64}, UnaryValue{Unary::BitNot}, Return{}};
    module.functions.push_back(function);
    for (const auto &source : {Type::I64, Type::U64}) {
        function.name = source == Type::I64 ? "signed_to_unsigned" : "unsigned_to_signed";
        function.result = source == Type::I64 ? Type::U64 : Type::I64;
        function.parameters = {source};
        function.slots = {{8, source}};
        function.code = {BindParameter{0, 8, source}, Load{8, source}, Convert{source, function.result}, Return{}};
        module.functions.push_back(function);
    }
    return module;
}
void unsignedTests() {
    accept("unsigned operation callable fixture", unsignedOperations());
    for (const auto operation : {Binary::CheckedAdd,
                                 Binary::CheckedSubtract,
                                 Binary::CheckedMultiply,
                                 Binary::CheckedDivide,
                                 Binary::CheckedRemainder,
                                 Binary::BitAnd,
                                 Binary::BitOr,
                                 Binary::BitXor,
                                 Binary::ShiftLeft,
                                 Binary::ShiftRight}) {
        const auto name = "u64 binary " + std::to_string(static_cast<int>(operation));
        const auto module = unsignedBinary(operation);
        accept(name, module);
        rejectModule(
            name + " signed left",
            module,
            [](Module &m) {
                std::get<Constant>(m.functions[0].code[0]).type = Type::I64;
            },
            "left operand");
        rejectModule(
            name + " bool right",
            module,
            [](Module &m) {
                m.functions[0].code[2] = Constant{1, Type::Bool};
            },
            "mistyped current");
        rejectModule(
            name + " missing left",
            module,
            [](Module &m) {
                m.functions[0].code.erase(m.functions[0].code.begin() + 1);
            },
            "stack underflow");
        rejectModule(
            name + " bool operation type",
            module,
            [](Module &m) {
                std::get<BinaryValue>(m.functions[0].code[3]).operandType = Type::Bool;
            },
            "invalid binary operand type");
        rejectModule(
            name + " invalid operation",
            module,
            [](Module &m) {
                std::get<BinaryValue>(m.functions[0].code[3]).operation = static_cast<Binary>(-1);
            },
            "invalid binary operation");
        rejectModule(
            name + " forged scalar type",
            module,
            [](Module &m) {
                std::get<BinaryValue>(m.functions[0].code[3]).operandType.className = "X";
            },
            "invalid binary operand type");
        const bool shift = operation == Binary::ShiftLeft || operation == Binary::ShiftRight;
        rejectModule(
            name + " wrong right signedness",
            module,
            [shift](Module &m) {
                std::get<Constant>(m.functions[0].code[2]).type = shift ? Type::U64 : Type::I64;
            },
            "mistyped current");
        if (operation == Binary::BitAnd || operation == Binary::BitOr || operation == Binary::BitXor || shift)
            rejectModule(
                name + " signed operation type",
                module,
                [](Module &m) {
                    std::get<BinaryValue>(m.functions[0].code[3]).operandType = Type::I64;
                },
                "invalid binary operand type");
        const auto emission = X86Emitter{}.emit(validate(module));
        if (shift) {
            const auto guard = emission.find("ja .Laurora_shift_count_trap");
            const auto instruction =
                emission.find(operation == Binary::ShiftLeft ? "shlq %cl, %rax" : "shrq %cl, %rax");
            if (guard == std::string::npos || instruction == std::string::npos || guard >= instruction)
                throw Error("shift guard must precede hardware count masking");
            if (operation == Binary::ShiftLeft &&
                emission.find("cmpq %rdx, %r11\n    jne .Laurora_overflow_trap") == std::string::npos)
                throw Error("left shift must check every discarded bit");
            ++passed;
            std::cout << "PASS IR " << name << " native guard order\n";
        } else if (operation == Binary::CheckedDivide || operation == Binary::CheckedRemainder) {
            const auto guard = emission.find("jz .Laurora_division_zero_trap");
            const auto division = emission.find("divq %r11");
            if (guard == std::string::npos || division == std::string::npos || guard >= division ||
                emission.find("xorq %rdx, %rdx\n    divq %r11") == std::string::npos ||
                emission.find("idivq") != std::string::npos || emission.find("cmpq $-1, %r11") != std::string::npos)
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
            name + " wrong source value",
            module,
            [result](Module &m) {
                std::get<Constant>(m.functions[0].code[0]).type = result;
            },
            "mistyped current");
        for (const auto &target : {Type::Bool,
                                   Type::Ref,
                                   Type::MutRef,
                                   Type::Own,
                                   Type("Pair"),
                                   Type::array(TypeKind::U64, 1),
                                   Type(static_cast<TypeKind>(99))}) {
            rejectModule(
                name + " invalid target " + typeName(target),
                module,
                [target](Module &m) {
                    std::get<Convert>(m.functions[0].code[1]).resultType = target;
                },
                target.isArray() ? "noncanonical instruction type payload" : "invalid checked conversion types");
            rejectModule(
                name + " invalid source " + typeName(target),
                module,
                [target](Module &m) {
                    std::get<Convert>(m.functions[0].code[1]).sourceType = target;
                },
                target.isArray() ? "noncanonical instruction type payload" : "invalid checked conversion types");
        }
        rejectModule(
            name + " identity rejected",
            module,
            [source](Module &m) {
                std::get<Convert>(m.functions[0].code[1]).resultType = source;
            },
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
    for (const auto operation : {Comparison::Equal,
                                 Comparison::NotEqual,
                                 Comparison::Less,
                                 Comparison::Greater,
                                 Comparison::LessEqual,
                                 Comparison::GreaterEqual}) {
        auto module = unsignedBinary(Binary::CheckedAdd);
        module.functions[0].result = Type::Bool;
        module.functions[0].code[3] = Compare{operation, Type::U64};
        const auto name = "u64 comparison " + std::to_string(static_cast<int>(operation));
        accept(name, module);
        rejectModule(
            name + " signed left",
            module,
            [](Module &m) {
                std::get<Constant>(m.functions[0].code[0]).type = Type::I64;
            },
            "comparison type mismatch");
        rejectModule(
            name + " signed right",
            module,
            [](Module &m) {
                std::get<Constant>(m.functions[0].code[2]).type = Type::I64;
            },
            "mistyped current");
        rejectModule(
            name + " invalid enum",
            module,
            [](Module &m) {
                std::get<Compare>(m.functions[0].code[3]).operation = static_cast<Comparison>(-1);
            },
            "invalid comparison");
        rejectModule(
            name + " reference forgery",
            module,
            [](Module &m) {
                std::get<Compare>(m.functions[0].code[3]).operandType = Type::Ref;
            },
            "non-scalar comparison");
    }
    auto call = unsignedOperations();
    auto entry = baseline().functions[0];
    entry.result = Type::U64;
    entry.code = {Constant{-1, Type::U64}, Push{}, Constant{0, Type::U64}, Push{}, Call{"unsigned_op0"}, Return{}};
    call.functions.push_back(entry);
    accept("u64 scalar call boundary", call);
    rejectModule(
        "signed argument cannot cross u64 scalar call boundary",
        call,
        [](Module &m) {
            std::get<Constant>(m.functions.back().code[0]).type = Type::I64;
        },
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
        "u64 receiver field cannot be loaded as signed",
        receiver,
        [](Module &m) {
            m.functions[2].code[0] = ReceiverLoad{0, Type::I64};
        },
        "receiver field type/layout mismatch");
    reject(
        "conversion roundtrip cannot preserve bounds token",
        [](Module &m) {
            m.functions[0].code = {Constant{42, Type::I64},
                                   Store{8, Type::I64},
                                   Constant{0, Type::I64},
                                   BoundsGuard{8, 1, Type::I64},
                                   Convert{Type::I64, Type::U64},
                                   Convert{Type::U64, Type::I64},
                                   IndexLoad{8, 1, Type::I64},
                                   Return{}};
        },
        "bounds token");
    auto array = baseline();
    array.functions[0].result = Type::U64;
    array.functions[0].slots[8] = Type::U64;
    array.functions[0].code = {Constant{-1, Type::U64},
                               Store{8, Type::U64},
                               Constant{0, Type::I64},
                               BoundsGuard{8, 1, Type::U64},
                               IndexLoad{8, 1, Type::U64},
                               Return{}};
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
        "u64 array store requires matching token",
        arrayStore,
        [](Module &m) {
            m.functions[0].code[3] = Constant{0, Type::I64};
        },
        "bounds token");
    rejectModule(
        "u64 array index cannot be u64",
        array,
        [](Module &m) {
            std::get<Constant>(m.functions[0].code[2]).type = Type::U64;
        },
        "mistyped current");
    rejectModule(
        "u64 array token cannot alias signed layout",
        array,
        [](Module &m) {
            m.functions[0].code[4] = IndexLoad{8, 1, Type::I64};
        },
        "slot type/layout");
    rejectModule(
        "u64 payload cannot mint borrow capability",
        array,
        [](Module &m) {
            m.functions[0].code[4] = BorrowHandle{8, Type::Ref};
        },
        "slot type/layout");
}
// Canonical numerical byte values remain wide in registers and pack into byte
// storage. These fixtures are the compiler's source ABI, not a foreign ABI.
Module byteBinary(Binary operation) {
    auto module = baseline();
    auto &function = module.functions[0];
    function.result = Type::U8;
    const bool shift = operation == Binary::ShiftLeft || operation == Binary::ShiftRight;
    function.code = {Constant{255, Type::U8},
                     Push{},
                     Constant{shift ? 0 : 1, shift ? Type::I64 : Type::U8},
                     BinaryValue{operation, Type::U8},
                     Return{}};
    return module;
}
Module byteValueBaseline() {
    auto module = valueBaseline();
    module.classLayouts["Pair"][0] = Type::U8;
    for (auto &function : module.functions) {
        if (function.result == Type::I64)
            function.result = Type::U8;
        for (auto &type : function.parameters)
            if (type == Type::I64)
                type = Type::U8;
        for (auto &[offset, type] : function.slots) {
            (void)offset;
            if (type == Type::I64)
                type = Type::U8;
        }
        for (auto &instruction : function.code)
            std::visit(
                [](auto &operation) {
                    using Op = std::decay_t<decltype(operation)>;
                    if constexpr (std::is_same_v<Op, Constant> || std::is_same_v<Op, Load> ||
                                  std::is_same_v<Op, Store> || std::is_same_v<Op, BindParameter>) {
                        if (operation.type == Type::I64)
                            operation.type = Type::U8;
                    } else if constexpr (std::is_same_v<Op, BinaryValue>)
                        operation.operandType = Type::U8;
                },
                instruction);
    }
    module.functions[0].name = "byte_aggregate";
    return module;
}
Module byteReceiverBaseline() {
    auto module = receiverBaseline();
    module.classLayouts["Pair"][0] = Type::U8;
    module.functions[0].name = "byte_receiver";
    module.functions[0].result = Type::U8;
    module.functions[0].slots[16] = Type::U8;
    module.functions[0].code[1] = Constant{255, Type::U8};
    module.functions[1].parameters[0] = Type::U8;
    module.functions[1].slots[8] = Type::U8;
    module.functions[1].code[0] = BindParameter{0, 8, Type::U8};
    module.functions[1].code[2] = Load{8, Type::U8};
    module.functions[1].code[3] = ReceiverStore{0, Type::U8};
    module.functions[2].result = Type::U8;
    module.functions[2].code[0] = ReceiverLoad{0, Type::U8};
    module.functions[3].result = Type::U8;
    return module;
}
Module byteOperations() {
    Module module;
    for (const auto operation : {Binary::CheckedAdd,
                                 Binary::CheckedSubtract,
                                 Binary::CheckedMultiply,
                                 Binary::CheckedDivide,
                                 Binary::CheckedRemainder,
                                 Binary::BitAnd,
                                 Binary::BitOr,
                                 Binary::BitXor,
                                 Binary::ShiftLeft,
                                 Binary::ShiftRight}) {
        const bool shift = operation == Binary::ShiftLeft || operation == Binary::ShiftRight;
        const auto right = shift ? Type::I64 : Type::U8;
        auto function = byteBinary(operation).functions[0];
        function.name = "byte_op" + std::to_string(static_cast<int>(operation));
        function.parameters = {Type::U8, right};
        function.slots = {{8, Type::U8}, {16, right}};
        function.code = {BindParameter{0, 8, Type::U8},
                         BindParameter{1, 16, right},
                         Load{8, Type::U8},
                         Push{},
                         Load{16, right},
                         BinaryValue{operation, Type::U8},
                         Return{}};
        module.functions.push_back(std::move(function));
    }
    for (const auto operation : {Comparison::Equal,
                                 Comparison::NotEqual,
                                 Comparison::Less,
                                 Comparison::Greater,
                                 Comparison::LessEqual,
                                 Comparison::GreaterEqual}) {
        auto function = module.functions[0];
        function.name = "byte_compare" + std::to_string(static_cast<int>(operation));
        function.result = Type::Bool;
        function.code[5] = Compare{operation, Type::U8};
        module.functions.push_back(std::move(function));
    }
    auto function = module.functions[0];
    function.name = "byte_not";
    function.parameters = {Type::U8};
    function.slots = {{8, Type::U8}};
    function.code = {BindParameter{0, 8, Type::U8}, Load{8, Type::U8}, UnaryValue{Unary::BitNot, Type::U8}, Return{}};
    module.functions.push_back(function);
    for (const auto &wide : {Type::I64, Type::U64})
        for (bool narrow : {false, true}) {
            const auto source = narrow ? wide : Type::U8;
            const auto result = narrow ? Type::U8 : wide;
            function.name = typeName(source) + "_to_" + typeName(result);
            function.result = result;
            function.parameters = {source};
            function.slots = {{8, source}};
            function.code = {BindParameter{0, 8, source}, Load{8, source}, Convert{source, result}, Return{}};
            module.functions.push_back(function);
        }
    function = baseline().functions[0];
    function.name = "byte_local_array";
    function.result = Type::U8;
    function.slots = {{15, Type::U8}, {16, Type::U8}};
    function.code = {Constant{0, Type::U8},
                     Store{16, Type::U8},
                     Constant{1, Type::U8},
                     Store{15, Type::U8},
                     Constant{1, Type::I64},
                     BoundsGuard{16, 2, Type::U8},
                     Push{},
                     Constant{255, Type::U8},
                     IndexStore{16, 2, Type::U8},
                     Constant{1, Type::I64},
                     BoundsGuard{16, 2, Type::U8},
                     IndexLoad{16, 2, Type::U8},
                     Return{}};
    module.functions.push_back(function);
    for (auto fixture : {byteValueBaseline(), byteReceiverBaseline()}) {
        module.classLayouts.insert(fixture.classLayouts.begin(), fixture.classLayouts.end());
        module.functions.insert(module.functions.end(), fixture.functions.begin(), fixture.functions.end());
    }
    return module;
}
void byteTests() {
    accept("u8 callable operations and packed-storage fixture", byteOperations());
    for (const auto value : {0, 1, 127, 128, 254, 255}) {
        auto module = baseline();
        module.functions[0].result = Type::U8;
        module.functions[0].code = {Constant{value, Type::U8}, Return{}};
        accept("canonical u8 constant " + std::to_string(value), module);
    }
    for (const auto value : {INT64_MIN, INT64_C(-1), INT64_C(256), INT64_C(65535), INT64_MAX})
        reject(
            "noncanonical u8 constant " + std::to_string(value),
            [value](Module &module) {
                module.functions[0].result = Type::U8;
                module.functions[0].code = {Constant{value, Type::U8}, Return{}};
            },
            "noncanonical u8");
    for (const auto operation : {Binary::CheckedAdd,
                                 Binary::CheckedSubtract,
                                 Binary::CheckedMultiply,
                                 Binary::CheckedDivide,
                                 Binary::CheckedRemainder,
                                 Binary::BitAnd,
                                 Binary::BitOr,
                                 Binary::BitXor,
                                 Binary::ShiftLeft,
                                 Binary::ShiftRight}) {
        const auto name = "u8 binary " + std::to_string(static_cast<int>(operation));
        const auto module = byteBinary(operation);
        accept(name, module);
        for (const auto &type : {Type::I64, Type::U64, Type::Bool}) {
            rejectModule(
                name + " mixed left " + typeName(type),
                module,
                [type](Module &m) {
                    m.functions[0].code[0] = Constant{1, type};
                },
                "left operand");
            const bool shift = operation == Binary::ShiftLeft || operation == Binary::ShiftRight;
            if (shift && type == Type::I64)
                continue;
            rejectModule(
                name + " mixed right " + typeName(type),
                module,
                [type](Module &m) {
                    m.functions[0].code[2] = Constant{1, type};
                },
                "mistyped current");
        }
        rejectModule(
            name + " missing left",
            module,
            [](Module &m) {
                m.functions[0].code.erase(m.functions[0].code.begin() + 1);
            },
            "stack underflow");
        rejectModule(
            name + " bool operand type",
            module,
            [](Module &m) {
                std::get<BinaryValue>(m.functions[0].code[3]).operandType = Type::Bool;
            },
            "invalid binary operand type");
        rejectModule(
            name + " forged u8 type",
            module,
            [](Module &m) {
                std::get<BinaryValue>(m.functions[0].code[3]).operandType.className = "X";
            },
            "invalid binary operand type");
        if (operation == Binary::ShiftLeft || operation == Binary::ShiftRight)
            rejectModule(
                name + " byte count",
                module,
                [](Module &m) {
                    m.functions[0].code[2] = Constant{1, Type::U8};
                },
                "mistyped current");
    }
    for (const auto operation : {Unary::CheckedNegate, Unary::LogicalNot}) {
        reject(
            "u8 rejects signed/bool unary operation",
            [operation](Module &m) {
                m.functions[0].code = {Constant{1, Type::U8}, UnaryValue{operation, Type::U8}, Return{}};
            },
            "invalid unary operand type");
        reject(
            "u8 rejects legacy signed/bool unary operation",
            [operation](Module &m) {
                m.functions[0].code = {Constant{1, Type::U8}, UnaryValue{operation}, Return{}};
            },
            "mistyped current");
    }
    for (const auto &type : {Type::I64, Type::Bool, Type::Ref, Type("Fake")})
        reject(
            "u8 not rejects operand type " + typeName(type),
            [type](Module &m) {
                m.functions[0].code = {Constant{1, Type::U8}, UnaryValue{Unary::BitNot, type}, Return{}};
            },
            "invalid unary operand type");
    reject(
        "u8 not cannot use u64 width",
        [](Module &m) {
            m.functions[0].code = {Constant{1, Type::U8}, UnaryValue{Unary::BitNot}, Return{}};
        },
        "mistyped current");
    reject(
        "u8 not rejects forged type",
        [](Module &m) {
            auto forged = Type::U8;
            forged.templateArguments = {TypeKind::U8};
            m.functions[0].code = {Constant{1, Type::U8}, UnaryValue{Unary::BitNot, forged}, Return{}};
        },
        "noncanonical instruction type payload");
    for (const auto &wide : {Type::I64, Type::U64})
        for (bool narrow : {false, true}) {
            const auto source = narrow ? wide : Type::U8;
            const auto result = narrow ? Type::U8 : wide;
            auto module = baseline();
            module.functions[0].result = result;
            module.functions[0].code = {Constant{255, source}, Convert{source, result}, Return{}};
            const auto name = typeName(source) + " checked conversion to " + typeName(result);
            accept(name, module);
            rejectModule(
                name + " mistyped source",
                module,
                [result](Module &m) {
                    m.functions[0].code[0] = Constant{1, result};
                },
                "mistyped current");
            for (const auto &invalid : {Type::Bool,
                                        Type::Ref,
                                        Type::Own,
                                        Type("Pair"),
                                        Type::enumeration("E"),
                                        Type::array(TypeKind::U8, 1)}) {
                rejectModule(
                    name + " invalid source " + typeName(invalid),
                    module,
                    [invalid](Module &m) {
                        std::get<Convert>(m.functions[0].code[1]).sourceType = invalid;
                    },
                    invalid.isArray() ? "noncanonical instruction type payload" : "invalid checked conversion types");
                rejectModule(
                    name + " invalid target " + typeName(invalid),
                    module,
                    [invalid](Module &m) {
                        std::get<Convert>(m.functions[0].code[1]).resultType = invalid;
                    },
                    invalid.isArray() ? "noncanonical instruction type payload" : "invalid checked conversion types");
            }
        }
    reject(
        "u8 identity conversion rejected",
        [](Module &m) {
            m.functions[0].code = {Constant{1, Type::U8}, Convert{Type::U8, Type::U8}, Return{}};
        },
        "invalid checked conversion types");
    reject(
        "u8 conversion cannot preserve bounds token",
        [](Module &m) {
            m.functions[0].code = {Constant{42, Type::I64},
                                   Store{8, Type::I64},
                                   Constant{0, Type::I64},
                                   BoundsGuard{8, 1, Type::I64},
                                   Convert{Type::I64, Type::U8},
                                   Convert{Type::U8, Type::I64},
                                   IndexLoad{8, 1, Type::I64},
                                   Return{}};
        },
        "bounds token");
    for (const auto operation : {Comparison::Equal,
                                 Comparison::NotEqual,
                                 Comparison::Less,
                                 Comparison::Greater,
                                 Comparison::LessEqual,
                                 Comparison::GreaterEqual}) {
        auto module = byteBinary(Binary::CheckedAdd);
        module.functions[0].result = Type::Bool;
        module.functions[0].code[3] = Compare{operation, Type::U8};
        const auto name = "u8 comparison " + std::to_string(static_cast<int>(operation));
        accept(name, module);
        for (const auto &wide : {Type::I64, Type::U64}) {
            rejectModule(
                name + " mixed left " + typeName(wide),
                module,
                [wide](Module &m) {
                    m.functions[0].code[0] = Constant{255, wide};
                },
                "comparison type mismatch");
            rejectModule(
                name + " mixed right " + typeName(wide),
                module,
                [wide](Module &m) {
                    m.functions[0].code[2] = Constant{1, wide};
                },
                "mistyped current");
        }
    }
    auto call = byteOperations();
    auto entry = baseline().functions[0];
    entry.result = Type::U8;
    entry.code = {Constant{255, Type::U8}, Push{}, Constant{0, Type::U8}, Push{}, Call{"byte_op0"}, Return{}};
    call.functions.push_back(entry);
    accept("u8 scalar call boundary", call);
    rejectModule(
        "u8 call rejects wide argument",
        call,
        [](Module &m) {
            m.functions.back().code[0] = Constant{255, Type::U64};
        },
        "call argument type mismatch");
    rejectModule(
        "u8 return rejects wide payload",
        call,
        [](Module &m) {
            m.functions.back().result = Type::U64;
        },
        "mistyped current");
    rejectModule(
        "u8 parameter binding must match signature",
        call,
        [](Module &m) {
            std::get<BindParameter>(m.functions[0].code[0]).type = Type::U64;
        },
        "parameter type mismatch");
    auto aggregate = byteValueBaseline();
    accept("u8 aggregate argument and result mixed-width slots", aggregate);
    rejectModule(
        "u8 aggregate scalar argument rejects wide payload",
        aggregate,
        [](Module &m) {
            m.functions[0].code[10] = Constant{10, Type::U64};
        },
        "aggregate scalar argument type mismatch");
    rejectModule(
        "u8 aggregate leaf cannot have wide slot",
        aggregate,
        [](Module &m) {
            m.functions[0].slots[16] = Type::U64;
        },
        "object field slot type/layout mismatch");
    auto receiver = byteReceiverBaseline();
    accept("u8 receiver construction and forwarding", receiver);
    rejectModule(
        "u8 receiver load rejects wide type",
        receiver,
        [](Module &m) {
            m.functions[2].code[0] = ReceiverLoad{0, Type::U64};
        },
        "receiver field type/layout mismatch");
    const auto assembly = X86Emitter{}.emit(validate(byteOperations()));
    for (const auto &fragment :
         {"xorq $255, %rax", "cmpq $7, %rax", "cmpq $255, %rax", "movb %dil, -8(%rbp)", "movzbq (%rcx,%rax,1), %rax"})
        if (assembly.find(fragment) == std::string::npos)
            throw Error(std::string("u8 width or packed storage emission mismatch: ") + fragment);
    ++passed;
    std::cout << "PASS IR u8 checked width and packed byte storage\n";
}
Module arrayReceiverBaseline() {
    Module module;
    module.classLayouts["ArrayBox"] = {
        Type::I64, Type::I64, Type::I64, Type::Bool, Type::Bool, Type::Bool, Type::I64, Type::I64};
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
    constructor.code = {Constant{7, Type::I64},
                        ReceiverStore{0, Type::I64},
                        ReceiverArrayZero{1},
                        Constant{1, Type::Bool},
                        ReceiverStore{2, Type::Bool},
                        ReceiverArrayZero{3},
                        ReceiverArrayZero{4},
                        Constant{0, Type::I64},
                        Return{}};
    aurora::ir::Function getter;
    getter.name = "get_array";
    getter.result = Type::I64;
    getter.parameters = {Type::I64};
    getter.frameBytes = 16;
    getter.slots[8] = Type::I64;
    getter.receiver = Receiver{"ArrayBox", false, false};
    getter.code = {
        BindParameter{0, 8, Type::I64}, Load{8, Type::I64}, ReceiverBoundsGuard{1}, ReceiverIndexLoad{1}, Return{}};
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
    mapping.code = {Constant{1, Type::I64},
                    ReceiverBoundsGuard{3},
                    Push{},
                    Constant{1, Type::Bool},
                    ReceiverIndexStore{3},
                    Constant{0, Type::I64},
                    Return{}};
    module.functions.push_back(mapping);
    auto entry = module.functions[0];
    entry.name = "array_scalar_mapping";
    entry.code = {BeginObject{64}, MethodCall{"construct_array", 64}, MethodCall{"array_scalar_getter", 64}, Return{}};
    module.functions.push_back(entry);
    entry.name = "array_bool_mapping";
    entry.result = Type::Bool;
    entry.code = {BeginObject{64}, MethodCall{"construct_array", 64}, MethodCall{"array_bool_getter", 64}, Return{}};
    module.functions.push_back(entry);
    entry.name = "array_bool_zero";
    entry.code = {
        BeginObject{64}, MethodCall{"construct_array", 64}, MethodCall{"array_bool_index_getter", 64}, Return{}};
    module.functions.push_back(entry);
    entry.name = "array_bool_store";
    entry.code = {BeginObject{64},
                  MethodCall{"construct_array", 64},
                  MethodCall{"array_bool_setter", 64},
                  MethodCall{"array_bool_index_getter", 64},
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
    explosive.code = {
        Constant{1, Type::I64}, Push{}, Constant{0, Type::I64}, BinaryValue{Binary::CheckedDivide}, Return{}};
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
                      {BeginObject{192},
                       AggregateCall{"copy_array_box", {128}, 192},
                       Constant{1, Type::I64},
                       Push{},
                       Constant{99, Type::I64},
                       Push{},
                       MethodCall{"set_array", 64},
                       Constant{1, Type::I64},
                       Push{},
                       MethodCall{"get_array", 192},
                       Return{}});
    module.functions.push_back(entry);
    return module;
}
void arrayReceiverTests() {
    accept("logical array fields constructor and checked methods", arrayReceiverBaseline());
    accept("array fields copied through complete private value ABI", arrayNativeModule());
    auto rejectArray =
        [](const std::string &name, const std::function<void(Module &)> &mutate, const std::string &expected) {
            rejectModule(name, arrayReceiverBaseline(), mutate, expected);
        };
    rejectArray(
        "logical fields unknown nominal layout",
        [](Module &m) {
            m.classFields["Unknown"] = m.classFields.at("ArrayBox");
        },
        "unknown class layout");
    for (int first : {-1, 0, 2, 8192})
        rejectArray(
            "logical array range offset " + std::to_string(first),
            [=](Module &m) {
                m.classFields["ArrayBox"][1].firstLeaf = first;
            },
            "invalid logical class field shape");
    for (int length : {-1, 0, 65})
        rejectArray(
            "logical array length " + std::to_string(length),
            [=](Module &m) {
                m.classFields["ArrayBox"][1].length = length;
            },
            "invalid logical class field shape");
    rejectArray(
        "logical scalar range cannot hide array",
        [](Module &m) {
            m.classFields["ArrayBox"][1].array = false;
        },
        "invalid logical class field shape");
    rejectArray(
        "logical arrays require scalar leaves",
        [](Module &m) {
            m.classFields["ArrayBox"][1].elementType = Type::Own;
        },
        "invalid logical class field shape");
    rejectArray(
        "logical array leaf payload matches layout",
        [](Module &m) {
            m.classLayouts["ArrayBox"][2] = Type::U64;
        },
        "leaf type mismatch");
    rejectArray(
        "logical array range cannot escape layout",
        [](Module &m) {
            m.classFields["ArrayBox"].back().length = 3;
        },
        "range exceeds layout");
    rejectArray(
        "logical fields cover every leaf",
        [](Module &m) {
            m.classFields["ArrayBox"].pop_back();
        },
        "do not cover complete layout");
    rejectArray(
        "explicit empty shape cannot hide payload",
        [](Module &m) {
            m.classFields["ArrayBox"].clear();
        },
        "do not cover complete layout");
    rejectArray(
        "absent shape cannot forge array access",
        [](Module &m) {
            m.classFields.clear();
        },
        "requires array field");
    rejectArray(
        "scalar receiver load cannot access array",
        [](Module &m) {
            m.functions[2].code[2] = ReceiverLoad{1, Type::I64};
        },
        "receiver field type/layout");
    rejectArray(
        "scalar receiver init cannot partially initialize array",
        [](Module &m) {
            m.functions[1].code[2] = ReceiverStore{1, Type::I64};
        },
        "receiver field type/layout");
    rejectArray(
        "array constructor must initialize every field",
        [](Module &m) {
            m.functions[1].code.erase(m.functions[1].code.begin() + 5);
        },
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
            m.functions[1].code.insert(m.functions[1].code.begin() + 2, {Constant{1, Type::Bool}, BranchFalse{1}});
            m.functions[1].code.insert(m.functions[1].code.begin() + 5, Label{1});
        },
        "before all fields initialized");
    rejectArray(
        "array constructor conditional duplicate zero",
        [](Module &m) {
            m.functions[1].code.insert(m.functions[1].code.begin() + 3,
                                       {Constant{1, Type::Bool}, BranchFalse{1}, ReceiverArrayZero{1}, Label{1}});
        },
        "array initialized more than once");
    rejectArray(
        "array constructor loop cannot repeat initialization",
        [](Module &m) {
            m.functions[1].code.insert(m.functions[1].code.begin() + 2, Label{1});
            m.functions[1].code.insert(m.functions[1].code.begin() + 4,
                                       {Constant{1, Type::Bool}, BranchFalse{2}, Jump{1}, Label{2}});
        },
        "array initialized more than once");
    rejectArray(
        "array zero requires constructor",
        [](Module &m) {
            m.functions[2].code[2] = ReceiverArrayZero{1};
        },
        "zero requires constructor");
    rejectArray(
        "array write requires mutable receiver",
        [](Module &m) {
            m.functions[3].receiver->mutableValue = false;
        },
        "write through const receiver");
    for (const auto &[name, operation] :
         std::vector<std::pair<std::string, Instruction>>{{"zero", ReceiverArrayZero{1}},
                                                          {"guard", ReceiverBoundsGuard{1}},
                                                          {"load", ReceiverIndexLoad{1}},
                                                          {"store", ReceiverIndexStore{1}}}) {
        rejectArray(
            "array " + name + " requires receiver",
            [=](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin(), operation);
            },
            "without bound receiver");
    }
    for (const auto &[name, operation] :
         std::vector<std::pair<std::string, Instruction>>{{"zero", ReceiverArrayZero{0}},
                                                          {"guard", ReceiverBoundsGuard{0}},
                                                          {"load", ReceiverIndexLoad{0}},
                                                          {"store", ReceiverIndexStore{0}},
                                                          {"guard negative field", ReceiverBoundsGuard{-1}},
                                                          {"guard past field", ReceiverBoundsGuard{5}}}) {
        rejectArray(
            "array operation rejects scalar or invalid " + name,
            [=](Module &m) {
                m.functions[2].code[2] = operation;
            },
            name.find("field") == std::string::npos ? "requires array field" : "field type/layout");
    }
    for (const auto &[name, operation] : std::vector<std::pair<std::string, Instruction>>{
             {"guard", ReceiverBoundsGuard{1}}, {"load", ReceiverIndexLoad{1}}, {"store", ReceiverIndexStore{1}}}) {
        rejectArray(
            "constructor cannot use indexed " + name,
            [=](Module &m) {
                m.functions[1].code.insert(m.functions[1].code.end() - 1, operation);
            },
            "constructor cannot access receiver array");
    }
    rejectArray(
        "receiver index requires signed i64",
        [](Module &m) {
            m.functions[2].code[1] = Constant{0, Type::U64};
        },
        "mistyped current");
    rejectArray(
        "receiver load requires bounds evidence",
        [](Module &m) {
            m.functions[2].code[2] = Constant{0, Type::I64};
        },
        "bounds token");
    rejectArray(
        "receiver store requires saved evidence",
        [](Module &m) {
            m.functions[3].code[3] = Constant{0, Type::I64};
        },
        "bounds token");
    rejectArray(
        "same shape other field cannot reuse load token",
        [](Module &m) {
            m.functions[2].code[3] = ReceiverIndexLoad{4};
        },
        "bounds token");
    rejectArray(
        "same shape other field cannot reuse store token",
        [](Module &m) {
            m.functions[3].code[6] = ReceiverIndexStore{4};
        },
        "bounds token");
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
            m.functions[2].code.insert(m.functions[2].code.begin() + 3, UnaryValue{Unary::CheckedNegate});
        },
        "bounds token");
    rejectArray(
        "conversion roundtrip cannot retain receiver bounds",
        [](Module &m) {
            m.functions[2].code.insert(m.functions[2].code.begin() + 3,
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
            m.functions[2].code.insert(m.functions[2].code.begin() + 3, {Store{16, Type::I64}, Load{16, Type::I64}});
        },
        "bounds token");
    rejectArray(
        "local token cannot authorize receiver access",
        [](Module &m) {
            m.functions[2].code[2] = BoundsGuard{8, 1, Type::I64};
        },
        "bounds token");
    rejectArray(
        "receiver token cannot authorize local access",
        [](Module &m) {
            m.functions[2].code[3] = IndexLoad{8, 1, Type::I64};
        },
        "bounds token");
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
    helper.code = {Constant{1, Type::I64},
                   ReceiverBoundsGuard{4},
                   Push{},
                   Constant{42, Type::I64},
                   ReceiverIndexStore{4},
                   Return{}};
    saved.functions.push_back(helper);
    saved.functions[3].code[5] = MethodCall{"array_rhs_method", 0};
    accept("saved receiver token survives mutable receiver reborrow", saved);
    rejectModule(
        "returned scalar cannot forge receiver token",
        saved,
        [](Module &m) {
            m.functions[2].code[2] = Call{"array_rhs"};
        },
        "bounds token");
    auto restored = arrayReceiverBaseline();
    restored.functions[2].code.insert(restored.functions[2].code.begin() + 3, {Push{}, Constant{99, Type::I64}, Pop{}});
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
        "cross-field bounds evidence cannot survive CFG join",
        joined,
        [](Module &m) {
            m.functions[2].code[8] = ReceiverBoundsGuard{4};
        },
        "mistyped current");
    rejectModule(
        "branch cannot bypass receiver bounds check",
        joined,
        [](Module &m) {
            m.functions[2].code[8] = Constant{0, Type::I64};
        },
        "mistyped current");
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
            typeName(type) + " array plus scalar exceeds boundary",
            module,
            [=](Module &m) {
                m.classLayouts["Capacity"].push_back(type);
                m.classFields["Capacity"].push_back({type, 64, 1, false});
                m.functions[1].code.insert(m.functions[1].code.end() - 2, {Constant{0, type}, ReceiverStore{1, type}});
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
    for (const std::string fragment : {"movq $0, 8(%r10)",
                                       "movq $0, 16(%r10)",
                                       "movq %rax, 24(%r10)",
                                       "movq $0, 32(%r10)",
                                       "movq $0, 40(%r10)",
                                       "movq $0, 48(%r10)",
                                       "movq $0, 56(%r10)",
                                       "cmpq $2, %rax\n    jae .Laurora_bounds_trap",
                                       "movq 8(%r10,%rax,8), %rax",
                                       "movq %rax, 8(%r10,%rcx,8)",
                                       "movq 32(%r10,%rax,8), %rax",
                                       "movq %rax, 32(%r10,%rcx,8)"})
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
    module.classFields["Outer"] = {{Type::I64, 0, 1, false}, {Type("Leaf"), 1, 2, false}, {Type("Empty"), 3, 0, false}};
    aurora::ir::Function entry;
    entry.name = "test";
    entry.result = Type::I64;
    entry.frameBytes = 160;
    entry.objectSlots = {{16, {"Leaf", true}},
                         {32, {"Leaf", false}},
                         {56, {"Outer", false}},
                         {72, {"Leaf", true}},
                         {96, {"Outer", false}},
                         {104, {"Empty", false}},
                         {128, {"Outer", false}},
                         {152, {"Outer", false}}};
    for (const auto &[base, object] : entry.objectSlots)
        for (std::size_t leaf = 0; leaf < module.classLayouts.at(object.className).size(); ++leaf)
            entry.slots[base - static_cast<int>(leaf * 8)] = module.classLayouts.at(object.className)[leaf];
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
                  InitializeEmptyObject{104},
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
    return std::get<MethodCall>(module.functions[0].code[16]);
}
Module composedEmptyBaseline() {
    Module module;
    module.classLayouts = {{"Empty", {}}, {"OuterEmpty", {}}};
    module.classFields["OuterEmpty"] = {{Type("Empty"), 0, 0, false}};
    aurora::ir::Function entry;
    entry.name = "test";
    entry.result = Type::I64;
    entry.frameBytes = 32;
    entry.objectSlots = {
        {8, {"Empty", false}}, {16, {"OuterEmpty", false}}, {24, {"Empty", false}}, {32, {"OuterEmpty", false}}};
    entry.code = {BeginObject{8},
                  InitializeEmptyObject{8},
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
    constructor.code = {
        BindObjectParameter{0, 8, "Empty"}, InitializeObjectField{0, 0, 8}, Constant{0, Type::I64}, Return{}};
    module.functions = {entry, constructor};
    return module;
}
Module composedNativeModule() {
    auto module = composedBaseline();
    auto entry = module.functions[0];
    entry.code.resize(17);
    entry.code.insert(entry.code.end(), {MethodCall{"get_outer", 56}, Return{}});
    entry.name = "nested_receiver_projection";
    module.functions.push_back(entry);
    entry.name = "nested_scalar_mapping";
    entry.code[17] = Load{56, Type::I64};
    module.functions.push_back(entry);
    entry.name = "nested_snapshot_independence";
    entry.code[17] = Load{16, Type::I64};
    module.functions.push_back(entry);
    entry = module.functions[0];
    entry.name = "nested_projection_independence";
    entry.code.resize(23);
    entry.code.insert(entry.code.end(),
                      {Constant{99, Type::I64}, Store{72, Type::I64}, MethodCall{"get_outer", 128}, Return{}});
    module.functions.push_back(entry);
    entry.name = "nested_bool_mapping";
    entry.result = Type::Bool;
    entry.code.resize(23);
    entry.code.insert(entry.code.end(), {Load{64, Type::Bool}, Return{}});
    module.functions.push_back(entry);
    // A receiver-local constructor executes while another receiver is bound.
    // Its record, local argument snapshots and both receivers remain disjoint.
    auto relay = module.functions[3];
    relay.name = "nested_receiver_constructor";
    relay.frameBytes = 64;
    relay.slots = {{16, Type::I64}, {8, Type::Bool}, {48, Type::I64}, {40, Type::I64}, {32, Type::Bool}};
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
    entry.code.resize(17);
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
    auto rejectComposed =
        [&](const std::string &name, const std::function<void(Module &)> &change, const std::string &expected) {
            rejectModule(name, composedBaseline(), change, expected);
        };
    for (const int index : {-1, 3, 99})
        rejectComposed(
            "projection invalid logical index " + std::to_string(index),
            [=](Module &m) {
                std::get<ObjectFieldCopy>(m.functions[0].code[22]).fieldIndex = index;
            },
            "logical field index");
    rejectComposed(
        "projection scalar field rejected",
        [](Module &m) {
            std::get<ObjectFieldCopy>(m.functions[0].code[22]).fieldIndex = 0;
        },
        "projection requires class field");
    rejectComposed(
        "projection wrong nominal child",
        [](Module &m) {
            m.functions[0].objectSlots[72].className = "Other";
        },
        "copy nominal class mismatch");
    rejectComposed(
        "whole copy equal-byte nominal forgery",
        [](Module &m) {
            m.functions[0].objectSlots[32].className = "Other";
        },
        "copy nominal class mismatch");
    rejectComposed(
        "projection interior source",
        [](Module &m) {
            std::get<ObjectFieldCopy>(m.functions[0].code[22]).sourceOffset = 120;
        },
        "exact object slot");
    rejectComposed(
        "projection interior result",
        [](Module &m) {
            std::get<ObjectFieldCopy>(m.functions[0].code[22]).resultOffset = 64;
        },
        "exact object slot");
    rejectComposed(
        "projection aliases owner",
        [](Module &m) {
            std::get<ObjectFieldCopy>(m.functions[0].code[22]).resultOffset = 128;
        },
        "projection source aliases result");
    rejectComposed(
        "whole copy aliases source",
        [](Module &m) {
            m.functions[0].code[6] = CopyObject{16, 16};
        },
        "copy source aliases result");
    rejectComposed(
        "copy inactive source",
        [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 6, EndObject{16});
        },
        "outside active lifetime");
    rejectComposed(
        "copy inactive result",
        [](Module &m) {
            m.functions[0].code.erase(m.functions[0].code.begin() + 5);
        },
        "outside active lifetime");
    rejectComposed(
        "copy partially initialized source",
        [](Module &m) {
            m.functions[0].code.erase(m.functions[0].code.begin() + 4);
        },
        "not fully initialized");
    rejectComposed(
        "copy partially initialized result",
        [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 6, {Constant{0, Type::I64}, Store{32, Type::I64}});
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
            m.functions[0].code.insert(m.functions[0].code.begin() + 16,
                                       {Constant{3, Type::I64}, Store{48, Type::I64}});
        },
        "scalar store cannot write nested class field");
    rejectComposed(
        "nested direct scalar mutation rejected",
        [](Module &m) {
            m.functions[0].objectSlots[56].mutableValue = true;
            m.functions[0].code.insert(m.functions[0].code.begin() + 17,
                                       {Constant{3, Type::I64}, Store{48, Type::I64}});
        },
        "scalar store cannot write nested class field");
    rejectComposed(
        "nested direct indexed mutation rejected",
        [](Module &m) {
            m.functions[0].objectSlots[56].mutableValue = true;
            m.functions[0].code.insert(m.functions[0].code.begin() + 17,
                                       {Constant{0, Type::I64},
                                        BoundsGuard{48, 1, Type::I64},
                                        Push{},
                                        Constant{3, Type::I64},
                                        IndexStore{48, 1, Type::I64}});
        },
        "scalar array operation cannot address nested class field");
    rejectComposed(
        "class receiver scalar store forgery",
        [](Module &m) {
            m.functions[1].code[9] = ReceiverStore{1, Type::I64};
        },
        "receiver field type/layout mismatch");
    rejectComposed(
        "constructor class field absent",
        [](Module &m) {
            m.functions[1].code.erase(m.functions[1].code.begin() + 9);
        },
        "returns before all fields initialized");
    rejectComposed(
        "constructor empty class field absent",
        [](Module &m) {
            m.functions[1].code.erase(m.functions[1].code.begin() + 10);
        },
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
        [](Module &m) {
            std::get<InitializeObjectField>(m.functions[1].code[9]).fieldIndex = 0;
        },
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
        [](Module &m) {
            m.functions[1].code[9] = ObjectFieldCopy{0, 1, 24};
        },
        "cannot project receiver");
    rejectComposed(
        "constructor argument missing vector",
        [](Module &m) {
            composedCall(m).objectArguments.clear();
        },
        "argument vector size mismatch");
    rejectComposed(
        "constructor scalar argument object forgery",
        [](Module &m) {
            composedCall(m).objectArguments[3] = 104;
        },
        "scalar constructor argument");
    rejectComposed(
        "constructor argument mutable snapshot",
        [](Module &m) {
            m.functions[0].objectSlots[32].mutableValue = true;
        },
        "snapshot must be readonly");
    rejectComposed(
        "constructor argument aliases receiver",
        [](Module &m) {
            composedCall(m).objectArguments[1] = 56;
        },
        "receiver aliases argument snapshot");
    rejectComposed(
        "constructor argument reused snapshot",
        [](Module &m) {
            composedCall(m).objectArguments[1] = 104;
        },
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
        [](Module &m) {
            m.functions[0].code.erase(m.functions[0].code.begin() + 6);
        },
        "not fully initialized");
    rejectComposed(
        "constructor argument scalar operand missing",
        [](Module &m) {
            m.functions[0].code.erase(m.functions[0].code.begin() + 15);
        },
        "value stack underflow");
    rejectComposed(
        "constructor parameter mutable rejected",
        [](Module &m) {
            m.functions[1].objectSlots[24].mutableValue = true;
        },
        "object parameter must be readonly");
    rejectComposed(
        "ordinary method copied arguments require complete receiver",
        [](Module &m) {
            m.functions[1].receiver->constructor = false;
            m.functions[1].receiver->mutableValue = false;
        },
        "method receiver object not fully initialized");
    rejectComposed(
        "constructor class result rejected",
        [](Module &m) {
            m.functions[1].result = Type("Outer");
        },
        "receiver signature requires scalar, enum or class values");
    rejectComposed(
        "nested metadata wrong flattened length",
        [](Module &m) {
            m.classFields["Outer"][1].length = 1;
        },
        "nested class field length mismatch");
    rejectComposed(
        "nested metadata wrong leaf type",
        [](Module &m) {
            m.classLayouts["Leaf"][0] = Type::U64;
        },
        "nested class field leaf type mismatch");
    rejectComposed(
        "nested metadata missing class",
        [](Module &m) {
            m.classFields["Outer"][1].elementType = Type("Missing");
        },
        "invalid nominal nested class field");
    rejectComposed(
        "scalar class-field projection cannot reinterpret class array",
        [](Module &m) {
            m.classFields["Outer"][1].array = true;
        },
        "projection requires class field");
    rejectComposed(
        "nested metadata unresolved specialization",
        [](Module &m) {
            m.classFields["Outer"][1].elementType.templateArguments = {TypeKind::I64};
        },
        "invalid nominal nested class field");
    rejectComposed(
        "nested metadata overlap",
        [](Module &m) {
            m.classFields["Outer"][1].firstLeaf = 0;
        },
        "invalid logical class field shape");
    rejectComposed(
        "nested metadata negative length",
        [](Module &m) {
            m.classFields["Outer"][2].length = -1;
        },
        "nested class field length mismatch");
    for (const Type &invalid : {Type::Ref, Type::MutRef, Type::Own})
        rejectComposed(
            "nested metadata nonvalue " + typeName(invalid),
            [=](Module &m) {
                m.classFields["Outer"][1].elementType = invalid;
            },
            "invalid logical class field shape");
    rejectComposed(
        "empty nested self cycle",
        [](Module &m) {
            m.classFields["Empty"] = {{Type("Empty"), 0, 0, false}};
        },
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
        depth.classFields["D" + std::to_string(count)] = {{Type("D" + std::to_string(count - 1)), 0, 1, false}};
    }
    accept("nested depth exactly four", depth);
    rejectModule(
        "nested depth five rejected",
        depth,
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
        "composed capacity 65 leaves rejected",
        capacity,
        [](Module &m) {
            m.classLayouts["Parent"].push_back(Type::I64);
            m.classFields["Parent"].push_back({Type::I64, 64, 1, false});
        },
        "exceeds 64 scalar leaves");
    auto rejectEmpty =
        [&](const std::string &name, const std::function<void(Module &)> &change, const std::string &expected) {
            rejectModule(name, composedEmptyBaseline(), change, expected);
        };
    rejectEmpty(
        "empty nested copy cannot forge initialization",
        [](Module &m) {
            m.functions[0].code.erase(m.functions[0].code.begin() + 3);
        },
        "nested class field not completely initialized");
    rejectEmpty(
        "empty nested constructor missing logical initialization",
        [](Module &m) {
            m.functions[1].code.erase(m.functions[1].code.begin() + 1);
        },
        "returns before all class fields initialized");
    rejectEmpty(
        "empty nested destination still owns one storage word",
        [](Module &m) {
            m.functions[0].slots[16] = Type::I64;
        },
        "scalar slot overlaps empty object");
    rejectEmpty(
        "empty nested duplicate whole copy rejected",
        [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 8, CopyObject{16, 32});
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
            m.functions[0].code.insert(m.functions[0].code.begin() + 4, {EndObject{16}, BeginObject{16}});
        },
        "nested class field not completely initialized");
    const auto assembly = X86Emitter{}.emit(validate(composedBaseline()));
    const auto start = assembly.find("construct_outer:\n");
    if (start == std::string::npos || assembly.find("movq %r10, -56(%rbp)", start) == std::string::npos ||
        assembly.find("movq %r11, -64(%rbp)", start) == std::string::npos)
        throw Error("constructor receiver and packed argument record share private storage");
    ++passed;
    std::cout << "PASS IR constructor receiver and argument record use distinct private slots\n";
}

Module enumBaseline() {
    const auto mode = Type::enumeration("Mode");
    Module module;
    module.enumCases = {{"Mode", 2}, {"OtherMode", 2}};
    aurora::ir::Function entry;
    entry.name = "test";
    entry.result = Type::Bool;
    entry.frameBytes = 16;
    entry.slots[8] = mode;
    entry.code = {EnumConstant{mode, 1},
                  Store{8, mode},
                  Load{8, mode},
                  Push{},
                  Call{"identity_mode"},
                  Push{},
                  EnumConstant{mode, 1},
                  Compare{Comparison::Equal, mode},
                  Return{}};
    aurora::ir::Function identity;
    identity.name = "identity_mode";
    identity.result = mode;
    identity.parameters = {mode};
    identity.frameBytes = 16;
    identity.slots[8] = mode;
    identity.code = {BindParameter{0, 8, mode}, Load{8, mode}, Return{}};
    module.functions = {entry, identity};
    return module;
}
aurora::ir::Function &namedFunction(Module &module, const std::string &name) {
    for (auto &function : module.functions)
        if (function.name == name)
            return function;
    throw Error("missing IR test function " + name);
}
MethodCall &namedMethodCall(aurora::ir::Function &function, const std::string &name) {
    for (auto &instruction : function.code)
        if (auto *call = std::get_if<MethodCall>(&instruction); call && call->callee == name)
            return *call;
    throw Error("missing IR test method call " + name);
}
void addObject(
    Module &module, aurora::ir::Function &function, int base, const std::string &name, bool mutableValue = false) {
    function.objectSlots[base] = ObjectSlot{name, mutableValue};
    const auto &layout = module.classLayouts.at(name);
    for (std::size_t leaf = 0; leaf < layout.size(); ++leaf)
        function.slots[base - static_cast<int>(leaf * 8)] = layout[leaf];
}
// A class result combines a two-element array, an enum, bool and zero-leaf child.
// The method invokes a class-parameter constructor and an ordinary aggregate call,
// then reuses its receiver after both hidden registers have been clobbered.
Module methodResultBaseline() {
    const auto mode = Type::enumeration("Mode");
    Module module;
    module.enumCases = {{"Mode", 2}, {"OtherMode", 2}};
    module.classLayouts = {{"Empty", {}},
                           {"Leaf", {mode, Type::I64, Type::I64, Type::Bool}},
                           {"Outer", {Type::I64, mode, Type::I64, Type::I64, Type::Bool}}};
    module.classFields["Leaf"] = {
        {mode, 0, 1, false}, {Type::I64, 1, 2, true}, {Type::Bool, 3, 1, false}, {Type("Empty"), 4, 0, false}};
    module.classFields["Outer"] = {{Type::I64, 0, 1, false}, {Type("Leaf"), 1, 4, false}, {Type("Empty"), 5, 0, false}};
    aurora::ir::Function leaf;
    leaf.name = "construct_leaf";
    leaf.result = Type::I64;
    leaf.parameters = {mode, Type::Bool, Type("Empty")};
    leaf.receiver = Receiver{"Leaf", true, true};
    leaf.frameBytes = 32;
    leaf.slots = {{8, mode}, {16, Type::Bool}};
    addObject(module, leaf, 24, "Empty");
    leaf.code = {BindParameter{0, 8, mode},
                 BindParameter{1, 16, Type::Bool},
                 BindObjectParameter{2, 24, "Empty"},
                 Load{8, mode},
                 ReceiverStore{0, mode},
                 Load{16, Type::Bool},
                 ReceiverStore{2, Type::Bool},
                 ReceiverArrayZero{1},
                 InitializeObjectField{0, 3, 24},
                 Constant{0, Type::I64},
                 Return{}};
    aurora::ir::Function outer;
    outer.name = "construct_outer";
    outer.result = Type::I64;
    outer.parameters = {Type::I64, Type("Leaf"), Type("Empty"), Type::I64};
    outer.receiver = Receiver{"Outer", true, true};
    outer.frameBytes = 64;
    outer.slots = {{8, Type::I64}, {56, Type::I64}};
    addObject(module, outer, 40, "Leaf");
    addObject(module, outer, 48, "Empty");
    outer.code = {BindParameter{0, 8, Type::I64},
                  BindObjectParameter{1, 40, "Leaf"},
                  BindObjectParameter{2, 48, "Empty"},
                  BindParameter{3, 56, Type::I64},
                  Load{8, Type::I64},
                  Push{},
                  Load{56, Type::I64},
                  BinaryValue{Binary::CheckedAdd},
                  ReceiverStore{0, Type::I64},
                  InitializeObjectField{0, 1, 40},
                  InitializeObjectField{0, 2, 48},
                  Constant{0, Type::I64},
                  Return{}};
    aurora::ir::Function setter;
    setter.name = "set_leaf";
    setter.result = Type::I64;
    setter.parameters = {Type::I64, Type::I64};
    setter.receiver = Receiver{"Leaf", true, false};
    setter.frameBytes = 16;
    setter.slots = {{8, Type::I64}, {16, Type::I64}};
    setter.code = {BindParameter{0, 8, Type::I64},
                   BindParameter{1, 16, Type::I64},
                   Load{8, Type::I64},
                   ReceiverBoundsGuard{1},
                   Push{},
                   Load{16, Type::I64},
                   ReceiverIndexStore{1},
                   Constant{0, Type::I64},
                   Return{}};
    aurora::ir::Function getter;
    getter.name = "get_outer_header";
    getter.result = Type::I64;
    getter.receiver = Receiver{"Outer", false, false};
    getter.code = {ReceiverLoad{0, Type::I64}, Return{}};
    auto enumGetter = getter;
    enumGetter.name = "get_leaf_mode";
    enumGetter.result = mode;
    enumGetter.receiver = Receiver{"Leaf", false, false};
    enumGetter.code = {ReceiverLoad{0, mode}, Return{}};
    aurora::ir::Function copy;
    copy.name = "copy_outer";
    copy.result = Type("Outer");
    copy.parameters = {Type("Outer")};
    copy.frameBytes = 48;
    addObject(module, copy, 40, "Outer");
    copy.code = {BindObjectParameter{0, 40, "Outer"}, ReturnObject{40}};
    aurora::ir::Function clobber;
    clobber.name = "clobber_scalar";
    clobber.result = Type::I64;
    clobber.code = {
        Constant{81, Type::I64}, Push{}, Constant{9, Type::I64}, BinaryValue{Binary::CheckedDivide}, Return{}};
    auto identity = enumBaseline().functions[1];
    aurora::ir::Function method;
    method.name = "snapshot_outer";
    method.result = Type("Outer");
    method.parameters = {Type::I64, mode};
    method.receiver = Receiver{"Outer", false, false};
    method.frameBytes = 160;
    method.slots = {{8, Type::I64}, {16, mode}, {144, Type::Bool}};
    addObject(module, method, 48, "Leaf");
    addObject(module, method, 56, "Empty");
    addObject(module, method, 96, "Outer");
    addObject(module, method, 136, "Outer", true);
    method.code = {BindParameter{0, 8, Type::I64},
                   BindParameter{1, 16, mode},
                   BeginObject{48},
                   ObjectFieldCopy{0, 1, 48},
                   BeginObject{56},
                   ObjectFieldCopy{0, 2, 56},
                   Load{16, mode},
                   Push{},
                   Call{"identity_mode"},
                   Push{},
                   Load{48, mode},
                   Compare{Comparison::Equal, mode},
                   Store{144, Type::Bool},
                   Call{"clobber_scalar"},
                   BeginObject{96},
                   Load{8, Type::I64},
                   Push{},
                   ReceiverLoad{0, Type::I64},
                   Push{},
                   MethodCall{"construct_outer", 96, {0, 48, 56, 0}},
                   BeginObject{136},
                   AggregateCall{"copy_outer", {96}, 136},
                   MethodCall{"get_outer_header", 0},
                   Push{},
                   Load{136, Type::I64},
                   BinaryValue{Binary::CheckedAdd},
                   Store{136, Type::I64},
                   Load{144, Type::Bool},
                   BranchFalse{1},
                   ReturnObject{136},
                   Label{1},
                   Constant{1, Type::I64},
                   Push{},
                   Constant{0, Type::I64},
                   BinaryValue{Binary::CheckedDivide},
                   ReturnObject{136}};
    aurora::ir::Function relay;
    relay.name = "relay_outer";
    relay.result = Type("Outer");
    relay.parameters = method.parameters;
    relay.receiver = method.receiver;
    relay.frameBytes = 64;
    relay.slots = {{8, Type::I64}, {16, mode}};
    addObject(module, relay, 56, "Outer");
    relay.code = {BindParameter{0, 8, Type::I64},
                  BindParameter{1, 16, mode},
                  BeginObject{56},
                  Load{8, Type::I64},
                  Push{},
                  Load{16, mode},
                  Push{},
                  MethodCall{"snapshot_outer", 0, {}, 56},
                  ReturnObject{56}};
    aurora::ir::Function empty;
    empty.name = "snapshot_empty";
    empty.result = Type("Empty");
    empty.receiver = Receiver{"Outer", false, false};
    empty.frameBytes = 16;
    addObject(module, empty, 8, "Empty");
    empty.code = {BeginObject{8}, ObjectFieldCopy{0, 2, 8}, Call{"clobber_scalar"}, ReturnObject{8}};
    aurora::ir::Function entry;
    entry.name = "test";
    entry.result = Type::I64;
    entry.frameBytes = 192;
    addObject(module, entry, 8, "Empty");
    addObject(module, entry, 40, "Leaf", true);
    addObject(module, entry, 72, "Leaf");
    addObject(module, entry, 112, "Outer");
    addObject(module, entry, 152, "Outer");
    addObject(module, entry, 184, "Leaf", true);
    addObject(module, entry, 192, "Empty");
    entry.code = {BeginObject{8},
                  InitializeEmptyObject{8},
                  BeginObject{40},
                  EnumConstant{mode, 1},
                  Push{},
                  Constant{1, Type::Bool},
                  Push{},
                  MethodCall{"construct_leaf", 40, {0, 0, 8}},
                  Constant{0, Type::I64},
                  Push{},
                  Constant{11, Type::I64},
                  Push{},
                  MethodCall{"set_leaf", 40},
                  Constant{1, Type::I64},
                  Push{},
                  Constant{42, Type::I64},
                  Push{},
                  MethodCall{"set_leaf", 40},
                  BeginObject{72},
                  CopyObject{40, 72},
                  Constant{1, Type::I64},
                  Push{},
                  Constant{99, Type::I64},
                  Push{},
                  MethodCall{"set_leaf", 40},
                  BeginObject{112},
                  Constant{7, Type::I64},
                  Push{},
                  Constant{5, Type::I64},
                  Push{},
                  MethodCall{"construct_outer", 112, {0, 72, 8, 0}},
                  BeginObject{152},
                  Constant{5, Type::I64},
                  Push{},
                  EnumConstant{mode, 1},
                  Push{},
                  MethodCall{"snapshot_outer", 112, {}, 152},
                  BeginObject{184},
                  ObjectFieldCopy{152, 1, 184},
                  Load{168, Type::I64},
                  Return{}};
    module.functions = {entry, leaf, outer, setter, getter, copy, clobber, identity, method, relay, empty, enumGetter};
    return module;
}
Module methodResultNativeModule() {
    auto module = methodResultBaseline();
    auto entry = module.functions[0];
    for (const auto &[name, offset, type] :
         std::vector<std::tuple<std::string, int, Type>>{{"method_result_header", 152, Type::I64},
                                                         {"method_result_first_array", 176, Type::I64},
                                                         {"method_result_enum", 184, Type::enumeration("Mode")},
                                                         {"method_result_bool", 160, Type::Bool},
                                                         {"method_source_snapshot", 24, Type::I64},
                                                         {"method_source_header", 112, Type::I64}}) {
        entry.name = name;
        entry.result = type;
        entry.code[entry.code.size() - 2] = Load{offset, type};
        module.functions.push_back(entry);
    }
    entry = module.functions[0];
    entry.name = "method_result_independence";
    entry.code.resize(entry.code.size() - 2);
    entry.code.insert(entry.code.end(),
                      {Constant{1, Type::I64},
                       Push{},
                       Constant{-13, Type::I64},
                       Push{},
                       MethodCall{"set_leaf", 184},
                       Load{128, Type::I64},
                       Return{}});
    module.functions.push_back(entry);
    entry = module.functions[0];
    entry.name = "method_forwarded_result";
    namedMethodCall(entry, "snapshot_outer").callee = "relay_outer";
    entry.code[entry.code.size() - 2] = Load{152, Type::I64};
    module.functions.push_back(entry);
    entry = module.functions[0];
    entry.name = "method_empty_result";
    entry.code.resize(entry.code.size() - 2);
    entry.code.insert(
        entry.code.end(),
        {BeginObject{192}, MethodCall{"snapshot_empty", 112, {}, 192}, Constant{42, Type::I64}, Return{}});
    module.functions.push_back(entry);
    entry.name = "method_empty_from_result";
    namedMethodCall(entry, "snapshot_empty").receiverOffset = 152;
    module.functions.push_back(entry);
    entry = module.functions[0];
    entry.name = "method_enum_receiver_read";
    entry.result = Type::enumeration("Mode");
    entry.code[entry.code.size() - 2] = MethodCall{"get_leaf_mode", 184};
    module.functions.push_back(entry);
    entry = module.functions[0];
    entry.name = "method_result_saved_operand";
    // Save below the method arguments, after the constructor has consumed its
    // own operands. Find the result lifetime boundary rather than an IR index:
    // explicit empty-object initialization adds a real instruction earlier.
    const auto savedPosition = std::find_if(entry.code.begin(), entry.code.end(), [](const Instruction &instruction) {
        const auto *begin = std::get_if<BeginObject>(&instruction);
        return begin && begin->offset == 152;
    });
    if (savedPosition == entry.code.end())
        throw Error("missing method-result lifetime boundary in saved-operand fixture");
    entry.code.insert(savedPosition, {Constant{3, Type::I64}, Push{}});
    entry.code.insert(entry.code.end() - 1, BinaryValue{Binary::CheckedAdd});
    module.functions.push_back(entry);
    return module;
}
// Reuse the full M012 receiver/result stress shape with its two array leaves
// packed as bytes. Logical fields, enum identity and empty descendants stay intact.
Module packedMethodModule() {
    auto module = methodResultBaseline();
    const auto oldLayouts = module.classLayouts;
    module.classLayouts["Leaf"][1] = Type::U8;
    module.classLayouts["Leaf"][2] = Type::U8;
    module.classLayouts["Outer"][2] = Type::U8;
    module.classLayouts["Outer"][3] = Type::U8;
    module.classFields["Leaf"][1].elementType = Type::U8;
    module.classFields["Empty"] = {};
    // An independent oracle, not the implementation under test.
    const std::map<std::string, ClassStorage> physical = {{"Empty", {{}, {}, 8, 8, 8}},
                                                           {"Leaf", {{0, 8, 9, 16}, {0, 8, 16, 24}, 24, 8, 24}},
                                                           {"Outer", {{0, 8, 16, 17, 24}, {0, 8, 32}, 32, 8, 32}}};
    for (auto &function : module.functions) {
        std::map<int, std::pair<int, Type>> remap;
        for (const auto &[base, object] : function.objectSlots) {
            const auto &layout = module.classLayouts.at(object.className);
            for (std::size_t leaf = 0; leaf < oldLayouts.at(object.className).size(); ++leaf) {
                const int oldOffset = base - static_cast<int>(leaf * 8);
                const int newOffset = base - physical.at(object.className).leafOffsets[leaf];
                function.slots.erase(oldOffset);
                remap[oldOffset] = {newOffset, layout[leaf]};
            }
        }
        for (const auto &[unused, replacement] : remap) {
            (void)unused;
            function.slots[replacement.first] = replacement.second;
        }
        for (auto &instruction : function.code)
            std::visit(
                [&](auto &operation) {
                    using Op = std::decay_t<decltype(operation)>;
                    if constexpr (std::is_same_v<Op, Load> || std::is_same_v<Op, Store>)
                        if (remap.contains(operation.offset)) {
                            const auto replacement = remap.at(operation.offset);
                            operation.offset = replacement.first;
                            operation.type = replacement.second;
                        }
                },
                instruction);
        for (std::size_t index = 0; index < function.code.size(); ++index)
            if (auto *call = std::get_if<MethodCall>(&function.code[index]); call && call->callee == "set_leaf")
                std::get<Constant>(function.code[index - 2]).type = Type::U8;
        if (function.name == "set_leaf") {
            function.parameters[1] = Type::U8;
            function.slots[16] = Type::U8;
            function.code[1] = BindParameter{1, 16, Type::U8};
            function.code[5] = Load{16, Type::U8};
        }
    }
    module.functions[0].name = "packed_result_array";
    module.functions[0].result = Type::U8;
    auto entry = module.functions[0];
    for (const auto &[name, offset, type] :
         std::vector<std::tuple<std::string, int, Type>>{{"packed_result_header", 152, Type::I64},
                                                         {"packed_result_first", 176, Type::U8},
                                                         {"packed_result_enum", 184, Type::enumeration("Mode")},
                                                         {"packed_result_bool", 168, Type::Bool},
                                                         {"packed_source_array", 31, Type::U8},
                                                         {"packed_source_header", 112, Type::I64}}) {
        entry.name = name;
        entry.result = type;
        entry.code[entry.code.size() - 2] = Load{offset, type};
        module.functions.push_back(entry);
    }
    entry = module.functions[0];
    entry.name = "packed_result_independence";
    entry.code.resize(entry.code.size() - 2);
    entry.code.insert(entry.code.end(),
                      {Constant{1, Type::I64},
                       Push{},
                       Constant{255, Type::U8},
                       Push{},
                       MethodCall{"set_leaf", 184},
                       Load{135, Type::U8},
                       Return{}});
    module.functions.push_back(entry);
    entry = module.functions[0];
    entry.name = "packed_forwarded_result";
    entry.result = Type::I64;
    namedMethodCall(entry, "snapshot_outer").callee = "relay_outer";
    entry.code[entry.code.size() - 2] = Load{152, Type::I64};
    module.functions.push_back(entry);
    entry = module.functions[0];
    entry.name = "packed_empty_result";
    entry.result = Type::I64;
    entry.code.resize(entry.code.size() - 2);
    entry.code.insert(
        entry.code.end(),
        {BeginObject{192}, MethodCall{"snapshot_empty", 152, {}, 192}, Constant{42, Type::I64}, Return{}});
    module.functions.push_back(entry);
    // A three-byte aggregate verifies that record slots use its reserved extent,
    // and that copies preserve high-bit byte values in a compact leaf sequence.
    module.classLayouts["Tiny"] = {Type::U8, Type::U8, Type::U8};
    module.classFields["Tiny"] = {{Type::U8, 0, 3, true}};
    aurora::ir::Function copy;
    copy.name = "packed_copy_tiny";
    copy.result = Type("Tiny");
    copy.parameters = {Type("Tiny")};
    copy.frameBytes = 16;
    copy.objectSlots[8] = ObjectSlot{"Tiny", false};
    copy.slots = {{8, Type::U8}, {7, Type::U8}, {6, Type::U8}};
    copy.code = {BindObjectParameter{0, 8, "Tiny"}, ReturnObject{8}};
    module.functions.push_back(copy);
    aurora::ir::Function tiny;
    tiny.name = "packed_tiny_roundtrip";
    tiny.result = Type::U8;
    tiny.frameBytes = 16;
    tiny.objectSlots = {{8, ObjectSlot{"Tiny", false}}, {16, ObjectSlot{"Tiny", false}}};
    tiny.slots = {{8, Type::U8}, {7, Type::U8}, {6, Type::U8}, {16, Type::U8}, {15, Type::U8}, {14, Type::U8}};
    tiny.code = {BeginObject{8},
                 Constant{7, Type::U8},
                 Store{8, Type::U8},
                 Constant{128, Type::U8},
                 Store{7, Type::U8},
                 Constant{255, Type::U8},
                 Store{6, Type::U8},
                 BeginObject{16},
                 AggregateCall{"packed_copy_tiny", {8}, 16},
                 Load{15, Type::U8},
                 Return{}};
    module.functions.push_back(tiny);
    return module;
}
bool storageMatches(StorageView actual, const ClassStorage &expected) {
    return actual.sizeBytes == expected.sizeBytes && actual.alignment == expected.alignment &&
           actual.reservedBytes == expected.reservedBytes &&
           std::equal(actual.leafOffsets.begin(), actual.leafOffsets.end(),
                      expected.leafOffsets.begin(), expected.leafOffsets.end()) &&
           std::equal(actual.fieldOffsets.begin(), actual.fieldOffsets.end(),
                      expected.fieldOffsets.begin(), expected.fieldOffsets.end());
}
void packedStorageTests() {
    const auto module = packedMethodModule();
    accept("packed bytes preserve composed receiver/results and tiny aggregate", module);
    const auto validated = validate(module);
    const std::map<std::string, ClassStorage> expected = {{"Empty", {{}, {}, 8, 8, 8}},
                                                          {"Leaf", {{0, 8, 9, 16}, {0, 8, 16, 24}, 24, 8, 24}},
                                                          {"Outer", {{0, 8, 16, 17, 24}, {0, 8, 32}, 32, 8, 32}},
                                                          {"Tiny", {{0, 1, 2}, {0}, 3, 1, 8}}};
    if (validated.metadata().classCount() != expected.size())
        throw Error("packed class storage has unexpected class count");
    for (const auto &[name, storage] : expected) {
        const auto id = validated.metadata().findClass(name);
        if (!id || !storageMatches(validated.metadata().storage(*id), storage))
            throw Error("packed class storage does not match explicit byte layout oracle");
    }
    ++passed;
    std::cout << "PASS IR canonical mixed/nested/empty/tiny class byte layout\n";
    auto checked = module;
    checked.classStorage = expected;
    accept("explicit canonical class storage metadata", checked);
    for (const auto &name : {"Empty", "Leaf", "Outer", "Tiny"}) {
        for (const auto member : {&ClassStorage::sizeBytes, &ClassStorage::alignment, &ClassStorage::reservedBytes})
            rejectModule(
                std::string("forged class physical extent ") + name,
                checked,
                [name, member](Module &m) {
                    ++(m.classStorage[name].*member);
                },
                "noncanonical class storage metadata");
        rejectModule(
            std::string("missing class physical metadata ") + name,
            checked,
            [name](Module &m) {
                m.classStorage.erase(name);
            },
            "noncanonical class storage metadata");
    }
    for (int offset : {-1, 0, 7, 16, 65536})
        rejectModule(
            "forged packed leaf offset " + std::to_string(offset),
            checked,
            [offset](Module &m) {
                m.classStorage["Leaf"].leafOffsets[2] = offset;
            },
            "noncanonical class storage metadata");
    rejectModule(
        "forged logical field physical offset",
        checked,
        [](Module &m) {
            m.classStorage["Outer"].fieldOffsets[1] = 1;
        },
        "noncanonical class storage metadata");
    rejectModule(
        "forged extra physical class",
        checked,
        [](Module &m) {
            m.classStorage["Unknown"] = ClassStorage{{}, {}, 8, 8, 8};
        },
        "noncanonical class storage metadata");
    rejectModule(
        "packed byte overlaps wide slot",
        module,
        [](Module &m) {
            m.functions[0].slots[167] = Type::U8;
        },
        "overlapping scalar slot storage");
    rejectModule(
        "packed byte cannot occupy object padding",
        module,
        [](Module &m) {
            m.functions[0].slots[174] = Type::U8;
        },
        "scalar slot overlaps empty object or padding");
    rejectModule(
        "packed leaf must use canonical offset",
        module,
        [](Module &m) {
            m.functions[0].slots.erase(175);
            m.functions[0].slots[174] = Type::U8;
        },
        "object field slot type/layout mismatch");
    rejectModule(
        "tiny rounded reservation padding cannot be a scalar",
        module,
        [](Module &m) {
            namedFunction(m, "packed_tiny_roundtrip").slots[5] = Type::U8;
        },
        "scalar slot overlaps empty object or padding");
    rejectModule(
        "packed object invalid minimum offset",
        module,
        [](Module &m) {
            m.functions[0].objectSlots[INT32_MIN] = ObjectSlot{"Outer", false};
        },
        "invalid object layout offset");
    rejectModule(
        "u8 slot zero offset",
        module,
        [](Module &m) {
            m.functions[0].slots[0] = Type::U8;
        },
        "invalid slot offset");
    rejectModule(
        "u8 slot exceeds frame",
        module,
        [](Module &m) {
            m.functions[0].slots[193] = Type::U8;
        },
        "invalid slot offset");
    auto emptyChild = module;
    emptyChild.classLayouts["EmptyShell"] = {};
    emptyChild.classFields["EmptyShell"] = {{Type("Empty"), 0, 0, false}};
    emptyChild.classLayouts["ByteEmpty"] = {Type::U8, Type::U8};
    emptyChild.classFields["ByteEmpty"] = {
        {Type::U8, 0, 1, false}, {Type("EmptyShell"), 1, 0, false}, {Type::U8, 1, 1, false}};
    const auto emptyChecked = validate(emptyChild);
    const auto byteEmpty = emptyChecked.metadata().findClass("ByteEmpty");
    if (!byteEmpty || !storageMatches(emptyChecked.metadata().storage(*byteEmpty),
                                     ClassStorage{{0, 1}, {0, 1, 1}, 2, 1, 8}))
        throw Error("empty descendant introduced physical payload or alignment");
    ++passed;
    std::cout << "PASS IR zero-leaf descendants retain logical shape without byte payload\n";
}
void enumAndMethodResultTests() {
    const auto mode = Type::enumeration("Mode");
    const auto other = Type::enumeration("OtherMode");
    accept("enum constant store call and equality", enumBaseline());
    auto rejectEnum =
        [&](const std::string &name, const std::function<void(Module &)> &change, const std::string &expected) {
            rejectModule(name, enumBaseline(), change, expected);
        };
    for (const int value : {-1, 2, 256})
        rejectEnum(
            "enum undeclared case " + std::to_string(value),
            [=](Module &m) {
                std::get<EnumConstant>(m.functions[0].code[0]).caseIndex = value;
            },
            "not a declared case");
    for (const auto &type : {Type::I64, Type::Bool, Type("Mode"), Type::enumeration("Unknown")})
        rejectEnum(
            "enum constant wrong type " + typeName(type),
            [=](Module &m) {
                std::get<EnumConstant>(m.functions[0].code[0]).type = type;
            },
            "invalid enum constant type");
    rejectEnum(
        "enum constant malformed metadata",
        [](Module &m) {
            std::get<EnumConstant>(m.functions[0].code[0]).type.length = 1;
        },
        "noncanonical instruction type payload");
    rejectEnum(
        "integer constant cannot forge enum",
        [=](Module &m) {
            m.functions[0].code[0] = Constant{1, mode};
        },
        "invalid constant type");
    rejectEnum(
        "cross enum store rejected",
        [=](Module &m) {
            m.functions[0].code[0] = EnumConstant{other, 1};
        },
        "mistyped current value");
    rejectEnum(
        "cross enum call rejected",
        [=](Module &m) {
            m.functions[0].code[2] = EnumConstant{other, 1};
        },
        "call argument type mismatch");
    rejectEnum(
        "cross enum comparison rejected",
        [=](Module &m) {
            m.functions[0].code[6] = EnumConstant{other, 1};
        },
        "mistyped current value");
    rejectEnum(
        "cross enum comparison stack rejected",
        [=](Module &m) {
            m.functions[0].code[6] = EnumConstant{other, 1};
            std::get<Compare>(m.functions[0].code[7]).operandType = other;
        },
        "comparison type mismatch");
    for (const auto operation :
         {Comparison::Less, Comparison::Greater, Comparison::LessEqual, Comparison::GreaterEqual})
        rejectEnum(
            "enum ordering rejected " + std::to_string(static_cast<int>(operation)),
            [=](Module &m) {
                std::get<Compare>(m.functions[0].code[7]).operation = operation;
            },
            "ordered bool comparison or enum comparison");
    rejectEnum(
        "enum arithmetic rejected",
        [=](Module &m) {
            m.functions[0].code[7] = BinaryValue{Binary::CheckedAdd, mode};
        },
        "invalid binary operand type");
    rejectEnum(
        "enum local arrays rejected",
        [=](Module &m) {
            m.functions[0].code = {EnumConstant{mode, 1},
                                   Store{8, mode},
                                   Constant{0, Type::I64},
                                   BoundsGuard{8, 1, mode},
                                   IndexLoad{8, 1, mode},
                                   Return{}};
        },
        "invalid array shape");
    rejectEnum(
        "unknown enum slot rejected",
        [](Module &m) {
            m.functions[0].slots[8] = Type::enumeration("Unknown");
        },
        "invalid slot payload type");
    rejectEnum(
        "unknown enum boundary rejected",
        [](Module &m) {
            m.functions[0].result = Type::enumeration("Unknown");
        },
        "invalid value boundary type");
    for (const int cases : {0, -1, 257})
        rejectEnum(
            "enum case count bound " + std::to_string(cases),
            [=](Module &m) {
                m.enumCases["Mode"] = cases;
            },
            "invalid nominal enum declaration");
    for (const auto &name : {std::string{}, std::string(4097, 'E')})
        rejectEnum(
            "enum name bounds",
            [=](Module &m) {
                m.enumCases[name] = 1;
            },
            "invalid nominal enum declaration");
    rejectEnum(
        "enum declaration count cap",
        [](Module &m) {
            for (int index = 0; index < 63; ++index)
                m.enumCases["E" + std::to_string(index)] = 1;
        },
        "too many enum declarations");
    rejectEnum(
        "enum class nominal name collision",
        [](Module &m) {
            m.classLayouts["Mode"] = {};
        },
        "class and enum nominal names overlap");
    auto maximum = enumBaseline();
    maximum.enumCases["Mode"] = 256;
    std::get<EnumConstant>(maximum.functions[0].code[0]).caseIndex = 255;
    for (int index = 0; index < 62; ++index)
        maximum.enumCases["E" + std::to_string(index)] = 1;
    accept("enum exact declaration and case limits", maximum);

    accept("method result with composed enum array empty descendants", methodResultBaseline());
    accept("method result native combined fixtures", methodResultNativeModule());
    auto rejectResult =
        [&](const std::string &name, const std::function<void(Module &)> &change, const std::string &expected) {
            rejectModule(name, methodResultBaseline(), change, expected);
        };
    for (const int offset : {0, 144, -152, 200})
        rejectResult(
            "method result exact destination " + std::to_string(offset),
            [=](Module &m) {
                namedMethodCall(m.functions[0], "snapshot_outer").resultOffset = offset;
            },
            "method result requires exact object slot");
    rejectResult(
        "method result aliases receiver",
        [](Module &m) {
            namedMethodCall(m.functions[0], "snapshot_outer").resultOffset = 112;
        },
        "method result aliases receiver");
    rejectResult(
        "method result physical overlap",
        [=](Module &m) {
            m.classLayouts["EnumLeaf"] = {mode};
            m.functions[0].objectSlots[144] = ObjectSlot{"EnumLeaf", false};
        },
        "overlapping object layouts");
    rejectResult(
        "method result inactive destination",
        [](Module &m) {
            auto &code = m.functions[0].code;
            code.erase(std::remove_if(code.begin(),
                                      code.end(),
                                      [](const Instruction &instruction) {
                                          const auto *begin = std::get_if<BeginObject>(&instruction);
                                          return begin && begin->offset == 152;
                                      }),
                       code.end());
        },
        "method result outside active object lifetime");
    rejectResult(
        "method result partial destination",
        [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 32,
                                       {Constant{0, Type::I64}, Store{152, Type::I64}});
        },
        "method result requires uninitialized object");
    rejectResult(
        "method result complete destination",
        [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 32, CopyObject{112, 152});
        },
        "method result object already initialized");
    rejectResult(
        "method result conditional partial destination",
        [](Module &m) {
            m.functions[0].code.insert(
                m.functions[0].code.begin() + 32,
                {Constant{1, Type::Bool}, BranchFalse{7}, Constant{0, Type::I64}, Store{152, Type::I64}, Label{7}});
        },
        "method result requires uninitialized object");
    rejectResult(
        "method result scalar call destination forbidden",
        [](Module &m) {
            namedMethodCall(m.functions[0], "construct_outer").resultOffset = 152;
        },
        "scalar method result cannot name object storage");
    rejectResult(
        "method result const receiver blocks mutable method",
        [](Module &m) {
            namedFunction(m, "snapshot_outer").receiver->mutableValue = true;
        },
        "const object cannot supply mutable receiver");
    rejectResult(
        "method result forwarding const receiver blocks mutable method",
        [](Module &m) {
            m.functions[0].objectSlots[112].mutableValue = true;
            namedFunction(m, "snapshot_outer").receiver->mutableValue = true;
        },
        "const receiver cannot forward mutable capability");
    rejectResult(
        "method result recursive nominal shape mismatch",
        [](Module &m) {
            m.classLayouts["OtherLeaf"] = m.classLayouts.at("Leaf");
            m.classFields["OtherLeaf"] = m.classFields.at("Leaf");
            m.classLayouts["OtherOuter"] = m.classLayouts.at("Outer");
            m.classFields["OtherOuter"] = m.classFields.at("Outer");
            m.classFields["OtherOuter"][1].elementType = Type("OtherLeaf");
            m.functions[0].objectSlots[152].className = "OtherOuter";
        },
        "method result nominal class mismatch");
    rejectResult(
        "method result enum nominal field mismatch",
        [=](Module &m) {
            m.classLayouts["Leaf"][0] = other;
            m.classFields["Leaf"][0].elementType = other;
        },
        "nested class field leaf type mismatch");
    rejectResult(
        "method result enum arrays remain forbidden",
        [=](Module &m) {
            m.classFields["Leaf"][0].array = true;
        },
        "invalid logical class field shape");
    rejectResult(
        "method result unknown enum layout leaf",
        [](Module &m) {
            m.classLayouts["Leaf"][0] = Type::enumeration("Missing");
        },
        "non-scalar class layout field");
    rejectResult(
        "method result cannot omit empty constructor child",
        [](Module &m) {
            auto &code = namedFunction(m, "construct_leaf").code;
            code.erase(code.begin() + 8);
        },
        "constructor returns before all class fields initialized");
    rejectResult(
        "method result wrong enum scalar argument",
        [=](Module &m) {
            m.functions[0].code[34] = EnumConstant{other, 1};
        },
        "method argument type mismatch");
    rejectResult(
        "constructor record wrong enum argument",
        [=](Module &m) {
            m.functions[0].code[3] = EnumConstant{other, 1};
        },
        "method argument type mismatch");
    rejectResult(
        "method class argument requires snapshot vector",
        [](Module &m) {
            namedFunction(m, "snapshot_outer").parameters[1] = Type("Empty");
        },
        "object argument vector size mismatch");
    rejectResult(
        "method object-argument vector not repurposed as result",
        [](Module &m) {
            namedMethodCall(m.functions[0], "snapshot_outer").objectArguments = {152};
        },
        "receiver object argument vector size mismatch");
    rejectResult(
        "method result cannot expose scalar current value",
        [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 37, Push{});
        },
        "push without current value");
    rejectResult(
        "method enum receiver field nominal mismatch",
        [=](Module &m) {
            namedFunction(m, "get_leaf_mode").code[0] = ReceiverLoad{0, other};
        },
        "receiver field type/layout mismatch");
    rejectResult(
        "constructor enum receiver store nominal mismatch",
        [=](Module &m) {
            namedFunction(m, "construct_leaf").code[3] = EnumConstant{other, 1};
        },
        "mistyped current value");
    rejectResult(
        "method enum return nominal mismatch",
        [=](Module &m) {
            namedFunction(m, "get_leaf_mode").result = other;
        },
        "mistyped current value");
    rejectResult(
        "method empty result already complete",
        [](Module &m) {
            auto &code = m.functions[0].code;
            code.insert(code.end() - 2,
                        {BeginObject{192},
                         MethodCall{"snapshot_empty", 112, {}, 192},
                         MethodCall{"snapshot_empty", 112, {}, 192}});
        },
        "method result object already initialized");
    rejectResult(
        "method aggregate result cannot use scalar return",
        [](Module &m) {
            namedFunction(m, "snapshot_empty").code.back() = Return{};
        },
        "scalar return cannot return class value");
    rejectResult(
        "method result source partial object",
        [](Module &m) {
            namedFunction(m, "snapshot_outer").code[21] = Constant{0, Type::I64};
        },
        "load before initialization");
    rejectResult(
        "method result cannot hide receiver recursion",
        [](Module &m) {
            namedMethodCall(namedFunction(m, "relay_outer"), "snapshot_outer").callee = "relay_outer";
        },
        "recursive receiver call cycle");
    const auto assembly = X86Emitter{}.emit(validate(methodResultBaseline()));
    for (const auto &fragment : {"movq %r10, -168(%rbp)",
                                 "movq %r11, -176(%rbp)",
                                 "leaq -152(%rbp), %r11",
                                 "movq %rdi, -8(%rbp)",
                                 "movq %rsi, -16(%rbp)"})
        if (assembly.find(fragment) == std::string::npos)
            throw Error(std::string("method result ABI emission mismatch: ") + fragment);
    ++passed;
    std::cout << "PASS IR method receiver and class result use distinct saved capabilities\n";
}

Module spanBaseline() {
    Module module;
    aurora::ir::Function function;
    function.name = "span_local";
    function.result = Type::U8;
    function.frameBytes = 640;
    function.slots = {{8, Type::U8}, {7, Type::U8}, {6, Type::U8}};
    function.arraySlots = {{8, 3}};
    function.spanSlots = {256, 320};
    function.code = {BeginArray{8},
                     Constant{11, Type::U8},
                     Store{8, Type::U8},
                     Constant{128, Type::U8},
                     Store{7, Type::U8},
                     Constant{255, Type::U8},
                     Store{6, Type::U8},
                     BorrowSpan{8, 256},
                     ReborrowSpan{256, 320},
                     Constant{1, Type::I64},
                     SpanLoad{320},
                     EndSpan{320},
                     EndSpan{256},
                     EndArray{8},
                     Return{}};
    module.functions.push_back(function);
    return module;
}
Module spanCallModule() {
    auto module = spanBaseline();
    auto local = module.functions.front();
    local.name = "span_length";
    local.result = Type::I64;
    local.code[9] = SpanLength{256};
    local.code.erase(local.code.begin() + 10);
    module.functions.push_back(local);
    local = module.functions.front();
    local.name = "span_preserve_current";
    local.code.erase(local.code.begin() + 9, local.code.begin() + 11);
    module.functions.push_back(local);

    aurora::ir::Function read;
    read.name = "span_read";
    read.result = Type::U8;
    read.parameters = {Type::ByteSpan, Type::I64};
    read.frameBytes = 640;
    read.slots = {{8, Type::I64}};
    read.spanSlots = {256};
    read.code = {BindSpanParameter{0, 256},
                 BindParameter{1, 8, Type::I64},
                 Load{8, Type::I64},
                 SpanLoad{256},
                 EndSpan{256},
                 Return{}};
    module.functions.push_back(read);
    auto relay = read;
    relay.name = "span_forward";
    relay.frameBytes = 640;
    relay.spanSlots.insert(320);
    relay.code = {BindSpanParameter{0, 256},
                  BindParameter{1, 8, Type::I64},
                  ReborrowSpan{256, 320},
                  Load{8, Type::I64},
                  Push{},
                  AggregateCall{"span_read", {0, 0}, 0, {320, 0}},
                  EndSpan{320},
                  EndSpan{256},
                  Return{}};
    module.functions.push_back(relay);
    auto dynamic = module.functions.front();
    dynamic.name = "span_dynamic";
    dynamic.frameBytes = 640;
    dynamic.parameters = {Type::I64};
    dynamic.slots[56] = Type::I64;
    dynamic.code = {BindParameter{0, 56, Type::I64},
                    BeginArray{8},
                    Constant{11, Type::U8},
                    Store{8, Type::U8},
                    Constant{128, Type::U8},
                    Store{7, Type::U8},
                    Constant{255, Type::U8},
                    Store{6, Type::U8},
                    BorrowSpan{8, 256},
                    Load{56, Type::I64},
                    Push{},
                    AggregateCall{"span_forward", {0, 0}, 0, {256, 0}},
                    EndSpan{256},
                    EndArray{8},
                    Return{}};
    module.functions.push_back(dynamic);

    module.classLayouts["SpanPacket"] = {Type::U8, Type::I64, Type::U8};
    aurora::ir::Function mixed;
    mixed.name = "span_mixed_callee";
    mixed.result = Type("SpanPacket");
    mixed.parameters = {Type::U8, Type::ByteSpan, Type("SpanPacket"), Type::I64, Type::ByteSpan, Type::Bool};
    mixed.frameBytes = 640;
    mixed.slots = {{1, Type::U8},
                   {56, Type::U8},
                   {48, Type::I64},
                   {40, Type::U8},
                   {64, Type::I64},
                   {96, Type::Bool},
                   {128, Type::U8},
                   {120, Type::I64},
                   {112, Type::U8},
                   {136, Type::I64}};
    mixed.objectSlots = {{56, ObjectSlot{"SpanPacket", false}}, {128, ObjectSlot{"SpanPacket", false}}};
    mixed.spanSlots = {256, 384};
    mixed.code = {BindParameter{0, 1, Type::U8},
                  BindSpanParameter{1, 256},
                  BindObjectParameter{2, 56, "SpanPacket"},
                  BindParameter{3, 64, Type::I64},
                  BindSpanParameter{4, 384},
                  BindParameter{5, 96, Type::Bool},
                  BeginObject{128},
                  Constant{0, Type::I64},
                  Push{},
                  AggregateCall{"span_forward", {0, 0}, 0, {256, 0}},
                  Convert{Type::U8, Type::I64},
                  Push{},
                  Load{48, Type::I64},
                  BinaryValue{Binary::CheckedAdd},
                  Push{},
                  Load{64, Type::I64},
                  BinaryValue{Binary::CheckedAdd},
                  Push{},
                  Constant{2, Type::I64},
                  Push{},
                  AggregateCall{"span_forward", {0, 0}, 0, {384, 0}},
                  Convert{Type::U8, Type::I64},
                  BinaryValue{Binary::CheckedAdd},
                  Store{136, Type::I64},
                  Load{96, Type::Bool},
                  BranchFalse{1},
                  Load{136, Type::I64},
                  Push{},
                  Constant{1, Type::I64},
                  BinaryValue{Binary::CheckedAdd},
                  Store{136, Type::I64},
                  Label{1},
                  Load{136, Type::I64},
                  Store{120, Type::I64},
                  Load{1, Type::U8},
                  Store{128, Type::U8},
                  Load{40, Type::U8},
                  Store{112, Type::U8},
                  EndSpan{384},
                  EndSpan{256},
                  ReturnObject{128}};
    module.functions.push_back(mixed);
    auto forwarding = mixed;
    forwarding.name = "span_mixed_forward";
    forwarding.frameBytes = 640;
    forwarding.spanSlots.insert({448, 512});
    forwarding.code.resize(6);
    for (const auto &op :
         std::vector<Instruction>{BeginObject{128},
                                  ReborrowSpan{256, 448},
                                  ReborrowSpan{384, 512},
                                  Load{1, Type::U8},
                                  Push{},
                                  Load{64, Type::I64},
                                  Push{},
                                  Load{96, Type::Bool},
                                  Push{},
                                  AggregateCall{"span_mixed_callee", {0, 0, 56, 0, 0, 0}, 128, {0, 448, 0, 0, 512, 0}},
                                  EndSpan{512},
                                  EndSpan{448},
                                  EndSpan{384},
                                  EndSpan{256},
                                  ReturnObject{128}})
        forwarding.code.push_back(op);
    module.functions.push_back(forwarding);
    aurora::ir::Function caller;
    caller.name = "span_mixed_sum";
    caller.result = Type::I64;
    caller.frameBytes = 640;
    caller.slots = {{8, Type::U8},
                    {7, Type::U8},
                    {6, Type::U8},
                    {32, Type::U8},
                    {31, Type::U8},
                    {30, Type::U8},
                    {56, Type::U8},
                    {48, Type::I64},
                    {40, Type::U8},
                    {112, Type::U8},
                    {104, Type::I64},
                    {96, Type::U8}};
    caller.arraySlots = {{8, 3}, {32, 3}};
    caller.spanSlots = {256, 576};
    caller.objectSlots = {{56, ObjectSlot{"SpanPacket", false}}, {112, ObjectSlot{"SpanPacket", false}}};
    caller.code = {BeginArray{8},
                   Constant{11, Type::U8},
                   Store{8, Type::U8},
                   Constant{128, Type::U8},
                   Store{7, Type::U8},
                   Constant{255, Type::U8},
                   Store{6, Type::U8},
                   BeginArray{32},
                   Constant{100, Type::U8},
                   Store{32, Type::U8},
                   Constant{200, Type::U8},
                   Store{31, Type::U8},
                   Constant{255, Type::U8},
                   Store{30, Type::U8},
                   BeginObject{56},
                   Constant{42, Type::U8},
                   Store{56, Type::U8},
                   Constant{13, Type::I64},
                   Store{48, Type::I64},
                   Constant{77, Type::U8},
                   Store{40, Type::U8},
                   BorrowSpan{8, 256},
                   BorrowSpan{32, 576},
                   BeginObject{112},
                   Constant{31, Type::U8},
                   Push{},
                   Constant{19, Type::I64},
                   Push{},
                   Constant{1, Type::Bool},
                   Push{},
                   AggregateCall{"span_mixed_forward", {0, 0, 56, 0, 0, 0}, 112, {0, 256, 0, 0, 576, 0}},
                   EndSpan{576},
                   EndSpan{256},
                   EndArray{32},
                   EndArray{8},
                   Load{104, Type::I64},
                   Return{}};
    module.functions.push_back(caller);
    for (const auto &[name, offset] :
         std::vector<std::pair<std::string, int>>{{"span_mixed_first", 112}, {"span_mixed_last", 96}}) {
        auto projection = caller;
        projection.name = name;
        projection.result = Type::U8;
        projection.code[projection.code.size() - 2] = Load{offset, Type::U8};
        module.functions.push_back(projection);
    }
    caller.name = "span_mixed_saved_operand";
    caller.code.insert(caller.code.begin() + 24, {Constant{1000, Type::I64}, Push{}});
    caller.code.insert(caller.code.end() - 1, BinaryValue{Binary::CheckedAdd});
    module.functions.push_back(caller);
    return module;
}
void spanTests() {
    accept("readonly local byte span and reborrow", spanBaseline());
    {
        auto checked = validate(spanBaseline());
        const auto frame = checked.metadata().frame(0);
        const auto arrays = frame.arraySlots();
        const auto spans = frame.spanSlots();
        auto moved = std::move(checked);
        if (frame.frameBytes() != 640 || arrays.size() != 1 || arrays.at(8) != 3 ||
            spans.size() != 2 || !spans.contains(256) || !spans.contains(320) || spans.contains(264) ||
            frame.scalarSlots().at(6) != Type::U8 || !frame.byteSlots().empty() ||
            moved.metadata().frame(0).arraySlots().at(8) != 3)
            throw Error("frame array/span observations lost source ownership or exact declaration offsets");
        ++passed;
    }
    accept("readonly span forwarding and six mixed argument positions", spanCallModule());
    const auto rejectSpan = [&](const std::string &name,
                                const std::function<void(aurora::ir::Function &)> &mutate,
                                const std::string &expected) {
        rejectModule(
            name,
            spanBaseline(),
            [&](Module &module) {
                mutate(module.functions[0]);
            },
            expected);
    };
    for (int base : {-1, 0, 8, 15, 17, 56})
        rejectSpan(
            "invalid span spill " + std::to_string(base),
            [=](auto &f) {
                f.spanSlots.insert(base);
            },
            "span spill");
    rejectSpan(
        "overlapping span spills",
        [](auto &f) {
            f.spanSlots.insert(264);
        },
        "overlapping span spills");
    rejectSpan(
        "span overlaps byte scalar",
        [](auto &f) {
            f.slots[212] = Type::U8;
        },
        "span spill overlaps");
    rejectSpan(
        "span overlaps wide scalar interior",
        [](auto &f) {
            f.slots[208] = Type::I64;
        },
        "span spill overlaps");
    for (int length : {-1, 0, 9, 4097})
        rejectSpan(
            "invalid byte origin extent " + std::to_string(length),
            [=](auto &f) {
                f.arraySlots[8] = length;
            },
            "byte array origin extent");
    rejectSpan(
        "origin past frame",
        [](auto &f) {
            f.arraySlots[648] = 1;
        },
        "origin extent");
    rejectSpan(
        "overlapping byte origins",
        [](auto &f) {
            f.arraySlots[7] = 2;
        },
        "overlapping byte array origins");
    rejectSpan(
        "missing byte origin element",
        [](auto &f) {
            f.slots.erase(7);
        },
        "exact u8 element slots");
    rejectSpan(
        "wrong byte origin element type",
        [](auto &f) {
            f.slots[8] = Type::I64;
        },
        "overlapping scalar slot");
    rejectSpan(
        "span spill scalar payload",
        [](auto &f) {
            f.slots[48] = Type::ByteSpan;
        },
        "invalid slot payload type");
    rejectSpan(
        "missing byte origin declaration",
        [](auto &f) {
            f.arraySlots.clear();
        },
        "exact byte array origin");
    rejectSpan(
        "borrow scalar origin",
        [](auto &f) {
            f.code[7] = BorrowSpan{7, 256};
        },
        "exact local byte array origin");
    rejectSpan(
        "borrow origin outside frame",
        [](auto &f) {
            f.code[7] = BorrowSpan{64, 256};
        },
        "exact local byte array origin");
    rejectSpan(
        "borrow requires typed spill",
        [](auto &f) {
            f.code[7] = BorrowSpan{8, 32};
        },
        "exact typed spill");
    rejectSpan(
        "array write before lifetime",
        [](auto &f) {
            f.code.erase(f.code.begin());
        },
        "array element access outside active lifetime");
    rejectSpan(
        "array read after lifetime",
        [](auto &f) {
            f.code[14] = Load{8, Type::U8};
        },
        "array element access outside active lifetime");
    rejectSpan(
        "array begin twice",
        [](auto &f) {
            f.code[7] = BeginArray{8};
        },
        "array lifetime already active");
    rejectSpan(
        "array end unknown origin",
        [](auto &f) {
            f.code[13] = EndArray{7};
        },
        "exact byte array origin");
    rejectSpan(
        "array end twice",
        [](auto &f) {
            f.code[14] = EndArray{8};
        },
        "array lifetime is not active");
    rejectSpan(
        "array end with direct borrow",
        [](auto &f) {
            f.code[8] = EndArray{8};
        },
        "array lifetime ends with live readonly span");
    rejectSpan(
        "array end with derived borrow",
        [](auto &f) {
            f.code[11] = EndArray{8};
        },
        "array lifetime ends with live readonly span");
    rejectSpan(
        "partial byte array initialization",
        [](auto &f) {
            f.code.erase(f.code.begin() + 6);
        },
        "array element not initialized");
    rejectSpan(
        "borrow ended array",
        [](auto &f) {
            f.code.insert(f.code.begin() + 7, EndArray{8});
        },
        "active byte array origin");
    rejectSpan(
        "borrow after rebegin needs new initialization",
        [](auto &f) {
            f.code.insert(f.code.begin() + 7, {EndArray{8}, BeginArray{8}});
        },
        "array element not initialized");
    rejectSpan(
        "overwrite live span",
        [](auto &f) {
            f.code[8] = BorrowSpan{8, 256};
        },
        "span spill is already active");
    rejectSpan(
        "reborrow self",
        [](auto &f) {
            f.code[8] = ReborrowSpan{256, 256};
        },
        "span spill is already active");
    rejectSpan(
        "reborrow unknown spill",
        [](auto &f) {
            f.code[8] = ReborrowSpan{32, 320};
        },
        "exact typed spill");
    rejectSpan(
        "reborrow inactive spill",
        [](auto &f) {
            f.code[8] = ReborrowSpan{320, 256};
        },
        "span capability is not active");
    rejectSpan(
        "end parent before child",
        [](auto &f) {
            f.code[11] = EndSpan{256};
        },
        "live child reborrow");
    rejectSpan(
        "end span twice",
        [](auto &f) {
            f.code[12] = EndSpan{320};
        },
        "span capability is not active");
    rejectSpan(
        "end unknown spill",
        [](auto &f) {
            f.code[11] = EndSpan{32};
        },
        "exact typed spill");
    rejectSpan(
        "load inactive span",
        [](auto &f) {
            f.code[7] = SpanLoad{256};
        },
        "span capability is not active");
    rejectSpan(
        "length inactive span",
        [](auto &f) {
            f.code[7] = SpanLength{256};
        },
        "span capability is not active");
    rejectSpan(
        "load after end span",
        [](auto &f) {
            f.code[13] = SpanLoad{320};
        },
        "span capability is not active");
    rejectSpan(
        "load span with unsigned index",
        [](auto &f) {
            f.code[9] = Constant{1, Type::U64};
        },
        "mistyped current value");
    rejectSpan(
        "load span with byte index",
        [](auto &f) {
            f.code[9] = Constant{1, Type::U8};
        },
        "mistyped current value");
    rejectSpan(
        "load span with bool index",
        [](auto &f) {
            f.code[9] = Constant{1, Type::Bool};
        },
        "mistyped current value");
    rejectSpan(
        "write owner with direct span",
        [](auto &f) {
            f.code[8] = Store{8, Type::U8};
        },
        "write to byte array with live readonly span");
    rejectSpan(
        "write owner with derived span",
        [](auto &f) {
            f.code[11] = Store{7, Type::U8};
        },
        "write to byte array with live readonly span");
    rejectSpan(
        "indexed write owner with span",
        [](auto &f) {
            f.code.insert(f.code.begin() + 9,
                          {Constant{0, Type::I64},
                           BoundsGuard{8, 3, Type::U8},
                           Push{},
                           Constant{22, Type::U8},
                           IndexStore{8, 3, Type::U8}});
        },
        "write to byte array with live readonly span");
    rejectSpan(
        "indexed subrange write owner with span",
        [](auto &f) {
            f.code.insert(f.code.begin() + 9,
                          {Constant{0, Type::I64},
                           BoundsGuard{7, 2, Type::U8},
                           Push{},
                           Constant{22, Type::U8},
                           IndexStore{7, 2, Type::U8}});
        },
        "write to byte array with live readonly span");
    rejectSpan(
        "return with active child span",
        [](auto &f) {
            f.code[11] = Return{};
        },
        "return with active span or byte array lifetime");
    rejectSpan(
        "return with active parent span",
        [](auto &f) {
            f.code[12] = Return{};
        },
        "return with active span or byte array lifetime");
    rejectSpan(
        "return with active byte origin",
        [](auto &f) {
            f.code[13] = Return{};
        },
        "return with active span or byte array lifetime");
    rejectSpan(
        "scalar load cannot expose span pointer",
        [](auto &f) {
            f.code[9] = Load{24, Type::I64};
        },
        "slot type/layout mismatch");
    rejectSpan(
        "scalar store cannot overwrite span length",
        [](auto &f) {
            f.code[10] = Store{16, Type::I64};
        },
        "slot type/layout mismatch");
    rejectSpan(
        "span constant cannot mint capability",
        [](auto &f) {
            f.code[9] = Constant{0, Type::ByteSpan};
        },
        "invalid constant type");
    rejectSpan(
        "span cannot become scalar through conversion",
        [](auto &f) {
            f.code[9] = Convert{Type::ByteSpan, Type::I64};
        },
        "invalid checked conversion types");
    rejectSpan(
        "scalar cannot become span through conversion",
        [](auto &f) {
            f.code[10] = Convert{Type::I64, Type::ByteSpan};
        },
        "invalid checked conversion types");
    rejectSpan(
        "span cannot use scalar comparison",
        [](auto &f) {
            f.code[10] = Compare{Comparison::Equal, Type::ByteSpan};
        },
        "non-scalar comparison");
    rejectSpan(
        "span cannot be function result",
        [](auto &f) {
            f.result = Type::ByteSpan;
        },
        "readonly span boundary");
    rejectSpan(
        "bind span outside entry",
        [](auto &f) {
            f.code[7] = BindSpanParameter{0, 256};
        },
        "parameter binding outside entry prefix");
    rejectSpan(
        "span branch lifetime mismatch",
        [](auto &f) {
            f.code.insert(f.code.begin() + 9, {Constant{1, Type::Bool}, BranchFalse{7}, EndSpan{320}, Label{7}});
        },
        "incompatible active span capabilities");
    rejectSpan(
        "span branch origin mismatch",
        [](auto &f) {
            f.code.insert(f.code.begin() + 9,
                          {Constant{1, Type::Bool}, BranchFalse{7}, EndSpan{320}, BorrowSpan{8, 320}, Label{7}});
        },
        "incompatible active span capabilities");
    rejectSpan(
        "span backedge lifetime mismatch",
        [](auto &f) {
            f.code.insert(f.code.begin() + 8, {Label{7}, ReborrowSpan{256, 320}, Jump{7}});
        },
        "incompatible active span capabilities");
    rejectSpan(
        "array branch lifetime mismatch",
        [](auto &f) {
            f.code.insert(f.code.begin() + 14,
                          {Constant{1, Type::Bool}, BranchFalse{7}, BeginArray{8}, Label{7}, Constant{128, Type::U8}});
        },
        "incompatible active array lifetimes");

    const auto rejectCall =
        [&](const std::string &name, const std::function<void(Module &)> &mutate, const std::string &expected) {
            rejectModule(name, spanCallModule(), mutate, expected);
        };
    rejectCall(
        "plain call cannot supply span",
        [](Module &m) {
            m.functions[5].code[11] = Call{"span_forward"};
        },
        "plain call cannot target aggregate signature");
    rejectCall(
        "missing positional span arguments",
        [](Module &m) {
            std::get<AggregateCall>(m.functions[5].code[11]).spanArguments.clear();
        },
        "span call argument vector size mismatch");
    rejectCall(
        "short positional span arguments",
        [](Module &m) {
            std::get<AggregateCall>(m.functions[5].code[11]).spanArguments = {256};
        },
        "span call argument vector size mismatch");
    rejectCall(
        "long positional span arguments",
        [](Module &m) {
            std::get<AggregateCall>(m.functions[5].code[11]).spanArguments = {256, 0, 0};
        },
        "span call argument vector size mismatch");
    rejectCall(
        "missing positional object arguments for span call",
        [](Module &m) {
            std::get<AggregateCall>(m.functions[5].code[11]).objectArguments.clear();
        },
        "aggregate call argument vector size mismatch");
    rejectCall(
        "span argument cannot borrow ordinary scalar slot",
        [](Module &m) {
            std::get<AggregateCall>(m.functions[5].code[11]).spanArguments[0] = 56;
        },
        "exact typed spill");
    rejectCall(
        "span argument cannot use inactive spill",
        [](Module &m) {
            std::get<AggregateCall>(m.functions[5].code[11]).spanArguments[0] = 320;
        },
        "span capability is not active");
    rejectCall(
        "scalar argument cannot also name capability",
        [](Module &m) {
            std::get<AggregateCall>(m.functions[5].code[11]).spanArguments[1] = 256;
        },
        "non-span argument cannot name span storage");
    rejectCall(
        "span argument cannot also name object",
        [](Module &m) {
            std::get<AggregateCall>(m.functions[5].code[11]).objectArguments[0] = 8;
        },
        "span argument cannot name object storage");
    rejectCall(
        "ended capability cannot cross call",
        [](Module &m) {
            m.functions[5].code.insert(m.functions[5].code.begin() + 11, EndSpan{256});
        },
        "span capability is not active");
    rejectCall(
        "owner write between borrow and call",
        [](Module &m) {
            m.functions[5].code.insert(m.functions[5].code.begin() + 9, Store{8, Type::U8});
        },
        "write to byte array with live readonly span");
    rejectCall(
        "span parameter missing canonical prefix",
        [](Module &m) {
            m.functions[3].code[0] = BeginArray{8};
        },
        "span parameter bindings must form the entry prefix");
    rejectCall(
        "span parameter wrong source position",
        [](Module &m) {
            m.functions[3].code[0] = BindSpanParameter{1, 256};
        },
        "span parameter bindings must form the entry prefix");
    rejectCall(
        "span parameter cannot use scalar binding",
        [](Module &m) {
            m.functions[3].code[0] = BindParameter{0, 24, Type::ByteSpan};
        },
        "span parameter bindings must form the entry prefix");
    rejectCall(
        "scalar parameter cannot use span binding",
        [](Module &m) {
            m.functions[3].code[1] = BindSpanParameter{1, 256};
        },
        "parameter bindings must form the entry prefix");
    rejectCall(
        "span parameter cannot bind scalar storage",
        [](Module &m) {
            m.functions[3].code[0] = BindSpanParameter{0, 8};
        },
        "span parameter requires exact typed spill");
    rejectCall(
        "span parameter cannot be rebound",
        [](Module &m) {
            m.functions[4].code.insert(m.functions[4].code.begin() + 6, EndSpan{256});
        },
        "live child reborrow");
    rejectCall(
        "span parameter rebinding after end",
        [](Module &m) {
            auto &f = m.functions[6];
            f.code.insert(f.code.begin() + 6, {EndSpan{256}, ReborrowSpan{384, 256}});
        },
        "span parameter cannot be rebound");
    rejectCall(
        "ordinary span call cannot target receiver",
        [](Module &m) {
            m.functions[3].receiver = Receiver{"SpanPacket", false, false};
        },
        "aggregate call cannot target receiver function");
    rejectCall(
        "constructor span parameter prohibited",
        [](Module &m) {
            auto &f = m.functions[3];
            f.result = Type::I64;
            f.receiver = Receiver{"SpanPacket", true, true};
        },
        "readonly span boundary");
    rejectCall(
        "class field cannot contain span",
        [](Module &m) {
            m.classLayouts["Bad"] = {Type::ByteSpan};
        },
        "non-scalar class layout field");
    rejectCall(
        "span spill overlaps object reservation padding",
        [](Module &m) {
            m.classLayouts["Tiny"] = {Type::U8};
            auto &f = m.functions[0];
            f.objectSlots[216] = ObjectSlot{"Tiny", false};
            f.slots[216] = Type::U8;
        },
        "span spill overlaps");
    rejectCall(
        "object leaf cannot mint local byte origin",
        [](Module &m) {
            auto &f = m.functions[8];
            f.arraySlots[56] = 1;
        },
        "byte array origin overlaps object storage");
    rejectCall(
        "scalar parameter cannot mint byte origin",
        [](Module &m) {
            auto &f = m.functions[6];
            f.arraySlots[1] = 1;
        },
        "parameter cannot bind byte array origin storage");
    rejectCall(
        "class return requires span cleanup",
        [](Module &m) {
            auto &f = m.functions[6];
            f.code.erase(f.code.end() - 2);
        },
        "return with active span or byte array lifetime");
    rejectCall(
        "two span parameters cannot bind same spill",
        [](Module &m) {
            m.functions[6].code[4] = BindSpanParameter{4, 256};
        },
        "span parameter bindings overlap");

    auto writes = spanBaseline();
    auto &wf = writes.functions[0];
    wf.code.insert(wf.code.begin() + 13, {Constant{42, Type::U8}, Store{8, Type::U8}});
    accept("owner write after every span ends", writes);
    auto reads = spanBaseline();
    reads.functions[0].code.insert(reads.functions[0].code.begin() + 9, Load{8, Type::U8});
    accept("owner read with live readonly span", reads);
    auto reuse = spanBaseline();
    reuse.functions[0].code.insert(reuse.functions[0].code.begin() + 13, {BorrowSpan{8, 256}, EndSpan{256}});
    accept("ended local span spill can begin a later lifetime", reuse);
    auto loop = spanBaseline();
    loop.functions[0].code.insert(loop.functions[0].code.begin() + 9,
                                  {Label{7}, Constant{0, Type::Bool}, BranchFalse{8}, Jump{7}, Label{8}});
    accept("unchanged readonly span capabilities across loop", loop);
    auto freshLoop = spanBaseline();
    freshLoop.functions[0].code.insert(
        freshLoop.functions[0].code.begin() + 7,
        {Label{7}, BorrowSpan{8, 256}, EndSpan{256}, Constant{0, Type::Bool}, BranchFalse{8}, Jump{7}, Label{8}});
    accept("span reborrow lifetime closes on backedge", freshLoop);

    // A storage address alone is not the identity of a continuing lifetime.
    // Restarted capabilities on only one branch must not join their predecessors.
    rejectSpan(
        "restarted array and span lifetimes cannot join previous lifetimes",
        [](auto &f) {
            f.code.insert(f.code.begin() + 9,
                          {Constant{1, Type::Bool},
                           BranchFalse{7},
                           EndSpan{320},
                           EndSpan{256},
                           EndArray{8},
                           BeginArray{8},
                           Constant{43, Type::U8},
                           Store{8, Type::U8},
                           Store{7, Type::U8},
                           Store{6, Type::U8},
                           BorrowSpan{8, 256},
                           ReborrowSpan{256, 320},
                           Label{7}});
        },
        "incompatible active array lifetimes");
    rejectSpan(
        "restarted child span cannot join previous lifetime in same spill",
        [](auto &f) {
            f.code.insert(f.code.begin() + 9,
                          {Constant{1, Type::Bool}, BranchFalse{7}, EndSpan{320}, ReborrowSpan{256, 320}, Label{7}});
        },
        "incompatible active span capabilities");
    rejectSpan(
        "restarted parent authority cannot join previous reborrow tree",
        [](auto &f) {
            f.code.insert(f.code.begin() + 9,
                          {Constant{1, Type::Bool},
                           BranchFalse{7},
                           EndSpan{320},
                           EndSpan{256},
                           BorrowSpan{8, 256},
                           ReborrowSpan{256, 320},
                           Label{7}});
        },
        "incompatible active span capabilities");
    auto closedLoop = spanBaseline();
    auto &closed = closedLoop.functions[0];
    closed.code = {Label{7},
                   BeginArray{8},
                   Constant{43, Type::U8},
                   Store{8, Type::U8},
                   Store{7, Type::U8},
                   Store{6, Type::U8},
                   BorrowSpan{8, 256},
                   ReborrowSpan{256, 320},
                   EndSpan{320},
                   EndSpan{256},
                   EndArray{8},
                   Constant{0, Type::Bool},
                   BranchFalse{8},
                   Jump{7},
                   Label{8},
                   Constant{42, Type::U8},
                   Return{}};
    accept("fully ended array and span sites can be reused on loop backedge", closedLoop);
    auto childLoop = spanBaseline();
    childLoop.functions[0].code.insert(
        childLoop.functions[0].code.begin() + 8,
        {Label{7}, ReborrowSpan{256, 320}, EndSpan{320}, Constant{0, Type::Bool}, BranchFalse{8}, Jump{7}, Label{8}});
    accept("fully ended child reborrow site can be reused with live parent", childLoop);

    const auto assembly = X86Emitter{}.emit(validate(spanCallModule()));
    for (const auto &name : {"span_read", "span_forward", "span_mixed_callee", "span_mixed_forward"})
        if (assembly.find(std::string(".local ") + name + "\n") == std::string::npos)
            throw Error("span signatures must have local linkage");
    ++passed;
    std::cout << "PASS IR span signatures use private compiler linkage\n";
    const auto compare = assembly.find("cmpq -272(%rbp), %rax");
    const auto bounds = assembly.find("jae .Laurora_bounds_trap", compare);
    const auto pointer = assembly.find("movq -312(%rbp), %rcx", compare);
    const auto payload = assembly.find("movzbq (%rcx,%rax,1), %rax", compare);
    if (compare == std::string::npos || !(compare < bounds && bounds < pointer && pointer < payload))
        throw Error("span bounds check must precede pointer and payload loads");
    ++passed;
    std::cout << "PASS IR span negative and upper bounds precede pointer load\n";
}

void callGraphTests() {
    const auto scalarFunction = [](const std::string &name, int scope) {
        aurora::ir::Function function;
        function.name = name;
        function.moduleScope = scope;
        function.result = Type::I64;
        function.code = {Constant{42, Type::I64}, Return{}};
        return function;
    };
    const auto retainedNames = [](Module module) {
        const auto checked = validate(std::move(module));
        std::vector<std::string> names;
        for (const auto &function : checked.get().functions)
            names.push_back(checked.metadata().callable(function.callableId).name());
        return names;
    };
    Module module;
    module.descriptorViews[1] = {};
    // Neither declaration nor retention order follows traversal order. Parallel
    // edges must not duplicate output, and every root survives without callers.
    module.functions = {scalarFunction("leaf", 1),
                        scalarFunction("unused", 1),
                        scalarFunction("bridge", 1),
                        scalarFunction("root", 0),
                        scalarFunction("other_root", 0)};
    module.functions[2].code = {Call{"leaf"}, Return{}};
    module.functions[3].code = {Call{"bridge"}, Call{"bridge"}, Return{}, Jump{1}, Label{1}};
    const std::vector<std::string> expected{"leaf", "bridge", "root", "other_root"};
    const auto checked = validate(module);
    if (retainedNames(module) != expected || checked.get().functions[2].code.size() != 3)
        throw Error("graph retention changed transitive roots, original order or normalized code");
    const std::vector<Metadata::CallableId> expectedIds{0, 2, 3, 4};
    if (checked.metadata().callableCount() != 5 || checked.metadata().findCallable("unused") != 1 ||
        checked.metadata().findCallable("absent"))
        throw Error("graph pruning lost admitted callable identity or changed name lookup");
    for (std::size_t index = 0; index < expectedIds.size(); ++index)
        if (checked.get().functions[index].callableId != expectedIds[index] ||
            checked.metadata().callable(expectedIds[index]).name() != expected[index])
            throw Error("graph pruning renumbered stable callable IDs");
    ++passed;
    std::cout << "PASS IR transitive graph retention preserves order and stable callable IDs\n";

    const std::vector<std::pair<Instruction, std::string>> missingCalls{
        {Call{"missing"}, "unknown call target"},
        {MethodCall{"missing", 0}, "unknown method call target"},
        {BorrowedCall{"missing", 0, 1}, "unknown method call target"},
        {AggregateCall{"missing", {}, 0}, "unknown aggregate call target"},
        {ServiceCall{"missing", 1, 0, {}}, "unknown service helper target"},
        {ResourceCall{"missing", 0, {}, 0}, "unknown resource call target"}};
    for (const auto &[call, diagnostic] : missingCalls)
        rejectModule(
            "unused imported call cannot hide missing target " + diagnostic,
            module,
            [&](Module &bad) {
                bad.functions[1].code = {call, Return{}};
            },
            diagnostic);
    rejectModule(
        "unreachable call rejects before graph retention",
        module,
        [](Module &bad) {
            bad.functions[1].code.push_back(Call{"unused"});
        },
        "unreachable semantic instruction");
    for (auto &function : module.functions)
        function.moduleScope = 1;
    if (!retainedNames(module).empty())
        throw Error("graph without root functions retained imported implementations");
    ++passed;
    std::cout << "PASS IR rootless graph retains no imported implementation\n";

    auto receivers = receiverBaseline();
    receivers.descriptorViews[1] = {};
    for (auto &function : receivers.functions)
        function.moduleScope = 1;
    receivers.functions.push_back(scalarFunction("root", 0));
    if (retainedNames(receivers) != std::vector<std::string>{"root"})
        throw Error("unused acyclic receiver component was retained");
    ++passed;
    std::cout << "PASS IR unused acyclic receiver component is pruned\n";
    rejectModule(
        "unused imported receiver cycle is checked before pruning",
        receivers,
        [](Module &bad) {
            bad.functions[2].code = {MethodCall{"relay_pair", 0}, Return{}};
        },
        "invalid typed IR: recursive receiver call cycle");

    auto serviceEntry = scalarFunction("service_root", 0);
    serviceEntry.parameters = {Type::ConsoleSession};
    serviceEntry.frameBytes = 16;
    serviceEntry.serviceSlots = {16};
    serviceEntry.code = {BindServiceParameter{0, 16, service::Kind::Console},
                         AcquireServiceLoan{1, 16},
                         ServiceCall{"service_helper", 1, 0, {0}},
                         ReleaseServiceLoan{1},
                         Return{}};
    auto serviceHelper = serviceEntry;
    serviceHelper.name = "service_helper";
    serviceHelper.moduleScope = 1;
    serviceHelper.code = {BindServiceParameter{0, 16, service::Kind::Console}, Call{"leaf"}, Return{}};
    module.functions = {scalarFunction("leaf", 1),
                        scalarFunction("cycle_a", 1),
                        serviceHelper,
                        scalarFunction("cycle_b", 1),
                        serviceEntry};
    module.functions[1].code = {Call{"cycle_b"}, Return{}};
    module.functions[3].code = {Call{"cycle_a"}, Return{}};
    if (retainedNames(module) != std::vector<std::string>{"leaf", "service_helper", "service_root"})
        throw Error("service edge retention or disconnected scalar SCC handling changed");
    ++passed;
    std::cout << "PASS IR service forwarding retains scalar descendants and permits unrelated scalar cycles\n";
    rejectModule(
        "service-reachable scalar SCC rejects through transitive helpers",
        module,
        [](Module &bad) {
            bad.functions[0].code = {Call{"cycle_a"}, Return{}};
        },
        "invalid typed IR: recursive receiver call cycle");
    rejectModule(
        "service-reachable scalar self edge rejects",
        module,
        [](Module &bad) {
            bad.functions[0].code = {Call{"leaf"}, Return{}};
        },
        "invalid typed IR: recursive receiver call cycle");
}

void reflectionEmissionTests() {
    auto module = baseline();
    module.descriptors = {{1, {8, 0}}, {100, {16, 1}}, {101, {0, 0}}};
    module.descriptorViews = {{0, {1, 100, 101}}, {1, {1, 100}}, {2, {101}}};
    module.functions[0].code = {Constant{100, Type::I64},
                                MetadataQuery{Query::Size, 0},
                                Store{8, Type::I64},
                                Call{"scoped"},
                                Load{8, Type::I64},
                                Return{}};
    auto scoped = module.functions[0];
    scoped.name = "scoped";
    scoped.moduleScope = 1;
    scoped.code = {Constant{100, Type::I64}, MetadataQuery{Query::PublicFieldCount, 1}, Return{}};
    module.functions.push_back(scoped);
    scoped.name = "unused";
    scoped.moduleScope = 2;
    scoped.code = {Constant{101, Type::I64}, MetadataQuery{Query::Size, 2}, Return{}};
    module.functions.push_back(scoped);
    const auto validated = validate(module);
    X86Emitter emitter;
    const auto complete = emitter.emit(validated);
    const auto completeFacts = emitter.stackFactsJson();
    const auto selected = emitter.emit(validated, SymbolBinding::Default, ReflectionEmission::Referenced);
    const auto body = [](const std::string &assembly, const std::string &name) {
        const auto begin = assembly.find(name + ":\n");
        const auto end = assembly.find(".size " + name + ",", begin);
        if (begin == std::string::npos || end == std::string::npos)
            throw Error("missing reflection helper body");
        return assembly.substr(begin, end - begin);
    };
    if (emitter.stackFacts().size() != 4 ||
        body(selected, "aurora_reflect_size") != body(complete, "aurora_reflect_size") ||
        body(selected, "__au_reflect_s1_field_count") != body(complete, "__au_reflect_s1_field_count") ||
        !emitter.stackFacts().at("test").calls.contains("aurora_reflect_size") ||
        !emitter.stackFacts().at("scoped").calls.contains("__au_reflect_s1_field_count"))
        throw Error("referenced reflection changed retained bodies or call facts");
    for (const auto &name :
         {"aurora_reflect_field_count", "__au_reflect_s1_size", "__au_reflect_s2_size", "__au_reflect_s2_field_count"})
        if (selected.find(std::string(name) + ":\n") != std::string::npos || emitter.stackFacts().contains(name))
            throw Error("unreferenced reflection helper or fact retained");
    if (emitter.emit(validated) != complete || emitter.stackFactsJson() != completeFacts)
        throw Error("referenced reflection changed default output or leaked emitter state");
    const auto empty = emitter.emit(validate(baseline()), SymbolBinding::Default, ReflectionEmission::Referenced);
    if (empty.find("aurora_reflect_") != std::string::npos || emitter.stackFacts().size() != 1)
        throw Error("query-free closed output retained reflection helpers");
    rejectModule(
        "unreferenced invalid query still rejects",
        module,
        [](Module &bad) {
            std::get<MetadataQuery>(bad.functions.back().code[1]).moduleScope = 1;
        },
        "changes defining-module scope");
    ++passed;
    std::cout << "PASS IR explicit reflection emission preserves queries, scope, validation and default reuse\n";
}

void initializationPayloadMetricTests() {
    // Existing legal frame extremes and word boundaries: these are representation
    // measurements, not new semantic admission thresholds or RSS expectations.
    for (int slotCount : {0, 1, 63, 64, 65, 65536}) {
        aurora::ir::Function function;
        function.name = "initialization_payload";
        function.result = Type::I64;
        function.frameBytes = ((slotCount + 15) / 16) * 16;
        function.code.push_back(Constant{1, Type::U8});
        for (int offset = 1; offset <= slotCount; ++offset) {
            function.slots.emplace(offset, Type::U8);
            function.code.push_back(Store{offset, Type::U8});
        }
        for (int branch = 0; branch < 2; ++branch) {
            const int alternate = branch * 2;
            const int join = alternate + 1;
            function.code.insert(function.code.end(),
                                 {Constant{1, Type::Bool},
                                  BranchFalse{alternate},
                                  Constant{1, Type::I64},
                                  Jump{join},
                                  Label{alternate},
                                  Constant{2, Type::I64},
                                  Label{join}});
        }
        function.code.push_back(Return{});
        Module module;
        module.functions.push_back(std::move(function));
        verification::Metrics metrics;
        static_cast<void>(validate(std::move(module), &metrics));
        const auto count = static_cast<std::size_t>(slotCount);
        const auto words = count / 64 + (count % 64 != 0);
        if (metrics.snapshots != 7 || metrics.peakOperandDepth != 0 || metrics.peakRetainedValueFacts != 12 * count ||
            metrics.peakRetainedInitializationPayloadBytes != 7 * 2 * words * sizeof(std::uint64_t))
            throw Error("retained initialization payload differs from exact dense word storage");
        ++passed;
        std::cout << "PASS IR initialization payload for " << count << " slots: snapshots=" << metrics.snapshots
                  << ", retained facts=" << metrics.peakRetainedValueFacts
                  << ", initialization payload bytes=" << metrics.peakRetainedInitializationPayloadBytes << '\n';
    }
}

void instructionOwnerTests() {
    static_assert(!std::is_copy_constructible_v<InstructionIngress> &&
                  std::is_nothrow_move_constructible_v<InstructionIngress> &&
                  std::is_nothrow_move_assignable_v<InstructionIngress>);
    auto source = baseline();
    aurora::ir::Function literal;
    literal.name = "literal_second";
    literal.result = Type::U8;
    literal.frameBytes = 64;
    literal.spanSlots = {56};
    literal.code = {Jump{7}, Label{6}, Jump{7}, Label{7}, BorrowLiteralSpan{{0, 42, 255}, 56},
                    Constant{1, Type::I64}, SpanLoad{56}, EndSpan{56}, Return{}};
    source.functions.push_back(std::move(literal));
    auto checked = validate(source);
    const auto code = checked.get().functions.at(1).code;
    const auto id = code.idAt(2);
    const auto observation = code.instructionById(id);
    const auto bytes = std::get<BorrowLiteralSpanObservation>(observation).bytes;
    source = Module{};
    auto moved = std::move(checked);
    auto replacement = validate(baseline());
    replacement = std::move(moved);
    if (id != 9 || code.size() != 7 || code.idAt(2) != id || bytes.size() != 3 ||
        bytes[0] != 0 || bytes[1] != 42 || bytes[2] != 255 ||
        replacement.get().functions.at(1).code.idAt(2) != id)
        throw Error("instruction identity or borrowed payload changed after compaction, ingress destruction or owner move");
    const auto assembly = X86Emitter{}.emit(replacement);
    if (assembly.find("leaq .Laurora_literal_9(%rip)") == std::string::npos ||
        assembly.find(".Laurora_literal_9:\n") == std::string::npos ||
        assembly.find(".Laurora_literal_1:\n") != std::string::npos)
        throw Error("nonfirst function literal lost its global immutable instruction ID");
    ++passed;
    std::cout << "PASS IR instruction ranges and literal IDs survive compaction and owner replacement\n";
    for (const auto &read : std::vector<std::function<void()>>{
             [&] { static_cast<void>(code.at(code.size())); },
             [&] { static_cast<void>(code.instructionById(0)); },
             [&] { static_cast<void>(code.instructionById(1)); },
             [&] { static_cast<void>(bytes.at(bytes.size())); }}) {
        bool rejected = false;
        try {
            read();
        } catch (const Error &) {
            rejected = true;
        } catch (const std::out_of_range &) {
            rejected = true;
        }
        if (!rejected)
            throw Error("instruction range accepted an out-of-domain position, ID or payload index");
        ++passed;
    }
    for (const auto &mutate : std::vector<std::function<void(Type &)>>{
             [](Type &type) { type.elementKind = TypeKind::U8; },
             [](Type &type) { type.length = 1; },
             [](Type &type) { type.elementParameter = "T"; },
             [](Type &type) { type.lengthParameter = "N"; },
             [](Type &type) { type.templateArguments = {TypeKind::I64}; }})
        reject("instruction ingress preserves unresolved raw type tails", [&](Module &module) {
            mutate(std::get<Constant>(module.functions[0].code[0]).type);
        }, "noncanonical instruction type payload");
    reject("declaration admission precedes malformed instruction tail", [](Module &module) {
        module.functions[0].slots[8].lengthParameter = "N";
        std::get<Constant>(module.functions[0].code[0]).type.lengthParameter = "N";
    }, "invalid slot payload type");
}

void callableOwnerTests() {
    reject("module metadata precedes malformed callable header", [](Module &module) {
        module.descriptors[0] = Descriptor{0, 0};
        module.functions[0].result = Type::Ref;
    }, "invalid metadata descriptor");
    reject("later callable header precedes earlier body frame", [](Module &module) {
        auto later = module.functions[0];
        later.name = "later";
        later.result = Type::Ref;
        module.functions[0].frameBytes = 1;
        module.functions.push_back(std::move(later));
    }, "invalid value boundary type");
    reject("later frame admission precedes earlier malformed body", [](Module &module) {
        auto later = module.functions[0];
        later.name = "later";
        later.frameBytes = 1;
        module.functions[0].code = {Pop{}, Return{}};
        module.functions.push_back(std::move(later));
    }, "invalid frame size");
    reject("frame admission remains declaration order", [](Module &module) {
        auto later = module.functions[0];
        later.name = "alphabetically_first";
        later.frameBytes = 1;
        module.functions[0].slots[7] = Type::I64;
        module.functions.push_back(std::move(later));
    }, "invalid slot offset");
    reject("orphan owner annotation precedes frame and body failures", [](Module &module) {
        module.functions[0].ownedValueTypes[40] = "Missing";
        module.functions[0].frameBytes = 1;
        module.functions[0].code = {Pop{}, Return{}};
    }, "owned value metadata requires exact owner spill");
    reject("service declaration admission precedes frame and body failures", [](Module &module) {
        module.functions[0].serviceSlots.insert(16);
        module.functions[0].frameBytes = 1;
        module.functions[0].code = {Pop{}, Return{}};
    }, "service spills without a service signature");
    for (const auto &[name, mutate, diagnostic] :
         std::vector<std::tuple<const char *, std::function<void(aurora::ir::Function &)>, const char *>>{
             {"service overlaps span", [](auto &function) {
                  function.parameters = {Type::ConsoleSession};
                  function.serviceSlots = {16};
                  function.spanSlots = {64};
              }, "service spill overlaps"},
             {"region overlaps span", [](auto &function) {
                  function.regionSlots = {16};
                  function.spanSlots = {64};
              }, "region spill overlaps"},
             {"owner overlaps span", [](auto &function) {
                  function.byteSlots = {{40, true}};
                  function.spanSlots = {64};
              }, "owned byte spill overlaps"},
             {"region overlaps service", [](auto &function) {
                  function.parameters = {Type::ConsoleSession};
                  function.serviceSlots = {16};
                  function.regionSlots = {16};
              }, "overlapping region or owned byte spills"},
             {"owner overlaps service", [](auto &function) {
                  function.parameters = {Type::ConsoleSession};
                  function.serviceSlots = {16};
                  function.byteSlots = {{32, true}};
              }, "overlapping region or owned byte spills"},
             {"owner overlaps region", [](auto &function) {
                  function.regionSlots = {16};
                  function.byteSlots = {{40, true}};
              }, "overlapping region or owned byte spills"}}) {
        reject(name, [&](Module &module) {
            auto &function = module.functions[0];
            function.frameBytes = 64;
            function.slots.clear();
            function.code = {Pop{}, Return{}};
            mutate(function);
        }, diagnostic);
    }
    reject("receiver header precedes frame layout", [](Module &module) {
        module.functions[0].receiver = Receiver{"Missing", false, false};
        module.functions[0].frameBytes = 1;
    }, "unknown receiver class");
    reject("callable header order remains declaration order", [](Module &module) {
        auto later = module.functions[0];
        later.name = "alphabetically_first";
        later.moduleScope = 63;
        module.functions[0].result = Type::Ref;
        module.functions.push_back(std::move(later));
    }, "invalid value boundary type");
    for (const auto &mutate : std::vector<std::function<void(Type &)>>{
             [](Type &type) { type.length = 1; },
             [](Type &type) { type.className = "forged"; }}) {
        reject("service header rejects noncanonical raw tail", [&](Module &module) {
            module.functions[0].parameters = {Type::ConsoleSession};
            mutate(module.functions[0].parameters[0]);
        }, "invalid canonical service boundary type");
    }
    reject("present negative receiver span summary reaches semantic admission", [](Module &module) {
        module.classLayouts["Pair"] = {Type::U8};
        module.functions[0].receiver = Receiver{"Pair", false, false};
        module.functions[0].result = Type::ByteSpan;
        module.functions[0].receiverSpanField = -1;
    }, "receiver span field summary requires exact direct byte-storage field");
    auto input = receiverBaseline();
    auto checked = validate(input);
    const auto *identity = &checked.metadata();
    const auto id = checked.metadata().findCallable("construct_pair").value();
    const auto callable = checked.metadata().callable(id);
    const auto parameters = callable.parameters();
    const auto frame = callable.frame();
    const auto scalars = frame.scalarSlots();
    const auto objects = checked.metadata().frame(0).objectSlots();
    auto copiedObject = objects.at(16);
    copiedObject.className = "changed frame observation";
    auto receiver = callable.receiver().value();
    receiver.className = "changed observation";
    input = Module{};
    auto moved = std::move(checked);
    if (&moved.metadata() != identity || id != 1 || callable.name() != "construct_pair" ||
        callable.moduleScope() != 0 || callable.result() != Type::I64 || parameters.size() != 2 ||
        parameters[0] != Type::I64 || parameters[1] != Type::Bool || callable.receiver()->className != "Pair" ||
        receiver.className != "changed observation" ||
        !callable.receiver()->constructor || !callable.receiver()->mutableValue ||
        callable.borrowedParameter() || callable.secondBorrowedParameter() || callable.receiverSpanField() ||
        frame.frameBytes() != 16 || scalars.size() != 2 || scalars.at(8) != Type::I64 || scalars.at(16) != Type::Bool ||
        objects.size() != 1 || objects.at(16).className != "Pair" || objects.at(16).mutableValue ||
        copiedObject.className != "changed frame observation" || moved.get().functions[id].callableId != id)
        throw Error("callable observations lost independent ingress lifetime, owner move or immutable receiver");
    ++passed;
    std::cout << "PASS IR callable and frame views survive raw ingress destruction and validated owner move\n";
}

void metadataOwnerTests() {
    auto source = baseline();
    const std::string binaryName("A\0\xff", 3);
    const std::string highName("\xff", 1);
    source.classLayouts[binaryName] = {Type::U8, Type::I64};
    source.classLayouts[highName] = {};
    source.classLayouts["Empty"] = {};
    source.classFields["Empty"] = {};
    source.enumCases["Mode"] = 2;
    source.descriptors[7] = Descriptor{16, 2};
    source.descriptorViews[0] = {7};
    const auto checked = validate(source);
    source.classLayouts.clear();
    source.classFields.clear();
    source.classStorage.clear();
    source.enumCases.clear();
    source.descriptors.clear();
    source.descriptorViews.clear();
    const auto &metadata = checked.metadata();
    const auto binary = metadata.findClass(binaryName);
    const auto high = metadata.findClass(highName);
    const auto empty = metadata.findClass("Empty");
    const auto mode = metadata.findEnum("Mode");
    const auto descriptor = metadata.findDescriptor(7);
    if (!binary || !high || !empty || !mode || metadata.className(*binary) != binaryName ||
        metadata.className(*high) != highName || *high <= *empty ||
        metadata.leaves(*binary).size() != 2 || metadata.leaves(*binary).at(0) != Type::U8 ||
        metadata.fields(*binary).size() != 2 || metadata.fields(*binary).at(1).firstLeaf != 1 ||
        metadata.fields(*binary).at(1).elementType != Type::I64 || !metadata.fields(*empty).empty() ||
        !storageMatches(metadata.storage(*binary), ClassStorage{{0, 8}, {0, 8}, 16, 8, 16}) ||
        !storageMatches(metadata.storage(*empty), ClassStorage{{}, {}, 8, 8, 8}) ||
        metadata.enumCases(*mode) != 2 || !descriptor || descriptor->size != 16 ||
        metadata.visibleDescriptors(0).size() != 1 || metadata.visibleDescriptors(0).at(0) != 7)
        throw Error("durable metadata lost normalized fields, byte names or independent input lifetime");
    ++passed;
    std::cout << "PASS IR durable metadata preserves normalized fields and exact byte names\n";

    const std::vector<std::pair<std::string, std::function<void(Type &)>>> noncanonical = {
        {"unknown kind", [](Type &type) { type.kind = static_cast<TypeKind>(99); }},
        {"unknown element kind", [](Type &type) { type.elementKind = static_cast<TypeKind>(99); }},
        {"length", [](Type &type) { type.length = 1; }},
        {"element parameter", [](Type &type) { type.elementParameter = "T"; }},
        {"length parameter", [](Type &type) { type.lengthParameter = "N"; }},
        {"template arguments", [](Type &type) { type.templateArguments = {TypeKind::I64}; }},
        {"scalar nominal tail", [](Type &type) { type.className = "Unexpected"; }}};
    for (const auto &[name, mutate] : noncanonical) {
        reject("metadata raw leaf " + name, [&](Module &module) {
            module.classLayouts["Leaf"] = {Type::I64};
            mutate(module.classLayouts["Leaf"][0]);
        }, "non-scalar class layout field");
        reject("metadata raw scalar slot " + name, [&](Module &module) {
            mutate(module.functions[0].slots[8]);
        }, "invalid slot payload type");
        reject("metadata raw logical field " + name, [&](Module &module) {
            module.classLayouts["Leaf"] = {Type::I64};
            module.classFields["Leaf"] = {{Type::I64, 0, 1, false}};
            mutate(module.classFields["Leaf"][0].elementType);
        }, "invalid logical class field shape");
    }
    auto provenance = baseline();
    auto leaf = Type::U8;
    leaf.displayName = "diagnostic spelling";
    leaf.resolvedClass = true;
    provenance.classLayouts["Leaf"] = {leaf};
    accept("metadata ignores nonsemantic Type display and provenance", provenance);

    reject("metadata descriptor precedes raw type tail", [](Module &module) {
        module.descriptors[0] = Descriptor{0, 0};
        module.classLayouts["Leaf"] = {Type::I64};
        module.classLayouts["Leaf"][0].lengthParameter = "N";
    }, "invalid metadata descriptor");
    reject("metadata root scope precedes invalid enum", [](Module &module) {
        module.descriptorViews.clear();
        module.enumCases[""] = 0;
    }, "missing root reflection scope");
    reject("metadata enum limit precedes invalid enum shape", [](Module &module) {
        module.enumCases[""] = 0;
        for (int index = 0; index < 64; ++index)
            module.enumCases["E" + std::to_string(index)] = 1;
    }, "too many enum declarations");
    reject("metadata unknown logical key precedes field normalization", [](Module &module) {
        module.classLayouts["A"] = {Type::I64};
        module.classFields["Z"] = {};
    }, "logical fields reference unknown class layout");
    reject("metadata nested carrier precedes field shape and raw tail", [](Module &module) {
        module.classLayouts["AParent"] = {};
        module.classLayouts["Empty"] = {};
        module.classLayouts["ZCarrier"] = {};
        module.classFields["AParent"] = {{Type("ZCarrier"), 1, 0, false}};
        module.classFields["AParent"][0].elementType.length = 1;
        module.classFields["ZCarrier"] = {{Type("Empty"), 0, 0, true, 1}};
        module.classArrayCarriers.insert("ZCarrier");
    }, "class array carrier cannot be nested element type");
    reject("metadata owning child precedes nested canonical type", [](Module &module) {
        module.classLayouts["AParent"] = {};
        module.classLayouts["ZOwner"] = {};
        module.classFields["AParent"] = {{Type("ZOwner"), 0, 0, false}};
        module.classFields["AParent"][0].elementType.templateArguments = {TypeKind::I64};
        module.classFields["ZOwner"] = {{Type::OwnedBytes, 0, 0, false}};
    }, "nested owning class field is unsupported");
    reject("metadata cycle precedes fifth-level depth error", [](Module &module) {
        for (const auto &name : {"A", "B", "C", "D"})
            module.classLayouts[name] = {};
        module.classFields["A"] = {{Type("B"), 0, 0, false}};
        module.classFields["B"] = {{Type("C"), 0, 0, false}};
        module.classFields["C"] = {{Type("D"), 0, 0, false}};
        module.classFields["D"] = {{Type("A"), 0, 0, false}};
    }, "cyclic nested class layout");
    reject("metadata sealed shape precedes supplied physical map", [](Module &module) {
        const auto name = std::string(service::sampleName);
        module.classLayouts[name] = {Type::Bool, Type::U8, Type::Bool};
        module.classFields[name] = {{Type::Bool, 0, 1, true}, {Type::U8, 1, 1, false},
                                   {Type::Bool, 2, 1, false}};
        module.classStorage["Unknown"] = ClassStorage{};
    }, "noncanonical sealed ConsoleSample field shape");
    reject("metadata owning storage limit precedes supplied physical map", [](Module &module) {
        module.classLayouts["Owner"] = {};
        module.classFields["Owner"] = std::vector<ClassField>(17, {Type::OwnedBytes, 0, 0, false});
        module.classStorage["Unknown"] = ClassStorage{};
    }, "composed or owning class storage exceeds 520 bytes");
    reject("metadata standalone supplied key survives union import", [](Module &module) {
        module.classStorage["Unknown"] = ClassStorage{{}, {}, 8, 8, 8};
    }, "noncanonical class storage metadata");
}

void pendingBodies(detail::InstructionWriter &writer, std::size_t count = 1, bool wrongId = false) {
    const std::vector<Instruction> code{Constant{42, Type::I64}, Store{8, Type::I64}, Load{8, Type::I64}, Return{}};
    for (std::size_t id = 0; id < count; ++id) {
        writer.beginBody(wrongId ? id + 1 : id);
        for (const auto &instruction : code)
            writer.append(instruction);
        writer.endBody();
    }
}

enum class CallableMutation {
    None,
    AbsentReceiver,
    UnknownFlag,
    RangeBegin,
    RangeCount,
    IndexOverflow,
    IndexDuplicate,
    IndexOrder,
    SlotRangeBegin,
    SlotRangeCount,
    SlotKind,
    SlotTypePrefix,
    SlotTypeGap,
    SlotLength,
    SlotMutable,
    SlotDuplicate,
    SlotOrder,
    SlotUncovered,
    TypeUncovered,
    ScalarTail,
    ObjectTail,
    OwnerTail,
    OrphanOwner,
    FrameSize,
    SlotKindOrder,
    SlotUnusedType,
    NegativeSingleSlot,
    NegativePairedSlot
};

void pendingCallables(detail::MetadataWriter &writer, const std::vector<std::string> &names,
                      CallableMutation mutation = CallableMutation::None) {
    namespace wire = aurora::hosted_abi::compiler_ir_metadata;
    for (const auto &name : names) {
        wire::CallableRow callable{};
        callable.nameRange = writer.text(name);
        callable.typeRange = {writer.position().coreCounts.types, 1};
        callable.frameBytes = 16;
        callable.slotRange = {writer.slotCount(), 2};
        const bool first = writer.callableCount() == 0;
        if (first) {
            if (mutation == CallableMutation::AbsentReceiver)
                callable.receiver.flags = 1;
            else if (mutation == CallableMutation::UnknownFlag)
                callable.flags = 16;
            else if (mutation == CallableMutation::RangeBegin)
                ++callable.typeRange.firstIndex;
            else if (mutation == CallableMutation::RangeCount)
                ++callable.typeRange.indexCount;
            else if (mutation == CallableMutation::SlotRangeBegin)
                ++callable.slotRange.firstIndex;
            else if (mutation == CallableMutation::SlotRangeCount)
                ++callable.slotRange.indexCount;
            else if (mutation == CallableMutation::FrameSize)
                callable.frameBytes = 8;
        }
        writer.callableType(Type::I64);
        const int slotCount = first && mutation == CallableMutation::NegativeSingleSlot ? 1 : 2;
        if (slotCount == 1)
            callable.slotRange.indexCount = 1;
        for (int ordinal = 0; ordinal < slotCount; ++ordinal) {
            wire::SlotRow slot{};
            slot.recordKind = static_cast<std::int64_t>(aurora::hosted_abi::compiler_lowering::RecordKind::ScalarSlot);
            slot.slotOffset = (ordinal + 1) * 8;
            auto type = Type::I64;
            if (first && ordinal == 0 && mutation == CallableMutation::ScalarTail)
                type.lengthParameter = "N";
            slot.typeIndex = writer.slotType(type);
            if (first) {
                if (ordinal == 0) {
                    if (mutation == CallableMutation::SlotKind)
                        slot.recordKind = 9;
                    else if (mutation == CallableMutation::SlotKindOrder)
                        slot.recordKind = 11;
                    else if (mutation == CallableMutation::SlotUnusedType)
                        slot.recordKind = 13;
                    else if (mutation == CallableMutation::NegativeSingleSlot ||
                             mutation == CallableMutation::NegativePairedSlot)
                        slot.slotOffset = -8;
                    else if (mutation == CallableMutation::SlotTypePrefix)
                        slot.typeIndex = callable.typeRange.firstIndex;
                    else if (mutation == CallableMutation::SlotTypeGap)
                        ++slot.typeIndex;
                    else if (mutation == CallableMutation::SlotLength)
                        slot.slotLength = 1;
                    else if (mutation == CallableMutation::SlotMutable)
                        slot.mutableValue = 1;
                }
                if (mutation == CallableMutation::SlotDuplicate)
                    slot.slotOffset = 8;
                else if (mutation == CallableMutation::SlotOrder)
                    slot.slotOffset = (2 - ordinal) * 8;
            }
            writer.append(slot);
        }
        if (first && (mutation == CallableMutation::ObjectTail || mutation == CallableMutation::OwnerTail ||
                      mutation == CallableMutation::OrphanOwner)) {
            wire::SlotRow extra{};
            const auto nominal = Type(std::string("A\0\xff", 3));
            if (mutation == CallableMutation::ObjectTail) {
                extra.recordKind = 11;
                extra.slotOffset = 16;
                auto type = nominal;
                type.elementParameter = "T";
                extra.typeIndex = writer.slotType(type);
            } else {
                callable.frameBytes = 64;
                if (mutation == CallableMutation::OwnerTail) {
                    wire::SlotRow owner{};
                    owner.recordKind = 16;
                    owner.slotOffset = 64;
                    owner.mutableValue = 1;
                    writer.append(owner);
                    ++callable.slotRange.indexCount;
                }
                extra.recordKind = 17;
                extra.slotOffset = 64;
                auto type = Type::ownedValues(nominal);
                if (mutation == CallableMutation::OwnerTail)
                    type.lengthParameter = "N";
                extra.typeIndex = writer.slotType(type);
            }
            writer.append(extra);
            ++callable.slotRange.indexCount;
        }
        writer.append(callable);
    }
    if (mutation == CallableMutation::SlotUncovered) {
        wire::SlotRow extra{};
        extra.recordKind = static_cast<std::int64_t>(aurora::hosted_abi::compiler_lowering::RecordKind::ArraySlot);
        extra.slotOffset = 1;
        extra.slotLength = 1;
        writer.append(extra);
    }
    if (mutation == CallableMutation::TypeUncovered)
        writer.slotType(Type::I64);
    std::vector<std::size_t> ids(names.size());
    for (std::size_t id = 0; id < ids.size(); ++id)
        ids[id] = id;
    std::sort(ids.begin(), ids.end(), [&](auto left, auto right) {
        return names[left] < names[right] || (names[left] == names[right] && left < right);
    });
    if (mutation == CallableMutation::IndexOrder)
        std::reverse(ids.begin(), ids.end());
    for (const auto id : ids)
        writer.index(static_cast<std::int64_t>(mutation == CallableMutation::IndexOverflow ? names.size()
            : mutation == CallableMutation::IndexDuplicate ? 0 : id));
}

InstructionIngress pendingMetadata(bool badStorage = false, bool badDescriptor = false,
                                const std::vector<std::string> &names = {"test"},
                                CallableMutation mutation = CallableMutation::None,
                                std::optional<std::size_t> bodyCount = std::nullopt, bool wrongId = false) {
    namespace wire = aurora::hosted_abi::compiler_ir_metadata;
    detail::MetadataWriter writer;
    detail::InstructionWriter instructions(writer);
    const auto fill = [&] {
        wire::ClassRow shape{};
        shape.nameRange = writer.text(std::string("A\0\xff", 3));
        shape.membershipBits = 1 | 2 | 4;
        shape.leafRange = {writer.position().coreCounts.leaves, 2};
        writer.leaf(Type::U8);
        writer.leaf(Type::I64);
        shape.fieldRange = {writer.position().coreCounts.fields, 2};
        writer.field(ClassField{Type::U8, 0, 1, false});
        writer.field(ClassField{Type::I64, 1, 1, false});
        shape.suppliedStorage = writer.position().mapCounts.storage;
        wire::StorageRow storage{};
        storage.leafOffsetRange = {writer.position().mapCounts.indices, 2};
        writer.index(0);
        writer.index(badStorage ? 9 : 8);
        storage.fieldOffsetRange = {writer.position().mapCounts.indices, 2};
        writer.index(0);
        writer.index(8);
        storage.physicalExtent = {16, 8, 16};
        writer.append(storage);
        writer.append(shape);
        wire::DescriptorRow descriptor{};
        descriptor.descriptorId = 7;
        descriptor.sizeValue = badDescriptor ? -1 : 16;
        descriptor.publicFieldCount = 2;
        writer.append(descriptor);
        wire::ViewRow view{};
        view.moduleScope = 0;
        view.descriptorRange = {writer.position().mapCounts.indices, 1};
        writer.index(7);
        writer.append(view);
        pendingCallables(writer, names, mutation);
        writer.beginInstructions();
        pendingBodies(instructions, bodyCount.value_or(names.size()), wrongId);
    };
    fill();
    writer.allocate();
    instructions.allocate();
    fill();
    return std::move(instructions).take();
}

void metadataIngressTests() {
    static_assert(!std::is_copy_constructible_v<MetadataIngress> && !std::is_copy_assignable_v<MetadataIngress> &&
                  std::is_nothrow_move_constructible_v<MetadataIngress> &&
                  std::is_nothrow_move_assignable_v<MetadataIngress>);
    const auto rejects = [](const char *name, const auto &operation, const char *expected) {
        try {
            operation();
        } catch (const Error &error) {
            if (std::string(error.what()).find(expected) == std::string::npos)
                throw Error(std::string(name) + ": wrong diagnostic: " + error.what());
            ++passed;
            std::cout << "PASS IR " << name << '\n';
            return;
        }
        throw Error(std::string(name) + ": invalid pending metadata was accepted");
    };
    auto pending = pendingMetadata();
    InstructionIngress moved(std::move(pending));
    pending = pendingMetadata();
    pending = std::move(moved);
    const auto checked = validate(std::move(pending));
    const auto &metadata = checked.metadata();
    const auto id = metadata.findClass(std::string("A\0\xff", 3));
    if (!id || metadata.leaves(*id).size() != 2 || metadata.fields(*id).at(1).elementType != Type::I64 ||
        !storageMatches(metadata.storage(*id), ClassStorage{{0, 8}, {0, 8}, 16, 8, 16}) ||
        metadata.visibleDescriptors(0).size() != 1 || metadata.visibleDescriptors(0).front() != 7 ||
        metadata.callableCount() != 1 || metadata.findCallable("test") != 0 ||
        metadata.callable(0).result() != Type::I64 || !metadata.callable(0).parameters().empty() ||
        metadata.frame(0).frameBytes() != 16 || metadata.frame(0).scalarSlots().size() != 2 ||
        metadata.frame(0).scalarSlots().at(8) != Type::I64 || metadata.frame(0).scalarSlots().at(16) != Type::I64)
        throw Error("pending metadata moves lost copied names, fields, storage, callable headers or frame declarations");
    ++passed;
    std::cout << "PASS IR pending metadata move construction, replacement and publication\n";
    rejects("pending metadata cannot publish twice", [&] {
        static_cast<void>(validate(std::move(pending)));
    }, "invalid hosted IR metadata transport");
    // Real Region destruction rejects any leaked owner. Exercise abandonment
    // and exception cleanup without substituting the generated owner/runtime.
    {
        const auto abandoned = pendingMetadata();
        (void)abandoned;
    }
    rejects("partially filled metadata cleans up without publication", [] {
        detail::MetadataWriter partial;
        partial.text("partial");
        partial.allocate();
        partial.text("p");
        static_cast<void>(std::move(partial).take());
    }, "invalid hosted IR metadata transport");
    rejects("partially filled instruction bundle releases both owners", [] {
        detail::MetadataWriter metadata;
        detail::InstructionWriter instructions(metadata);
        const auto fill = [&](bool partial) {
            metadata.declarations(baseline());
            metadata.beginInstructions();
            instructions.beginBody(0);
            instructions.append(Instruction{Push{}});
            if (!partial)
                instructions.append(Instruction{Pop{}});
            instructions.endBody();
        };
        fill(false);
        metadata.allocate();
        instructions.allocate();
        fill(true);
        static_cast<void>(std::move(instructions).take());
    }, "invalid hosted IR instruction transport");
    {
        detail::MetadataWriter writer;
        detail::InstructionWriter instructions(writer);
        aurora::hosted_abi::compiler_ir_metadata::ViewRow root{};
        const auto fill = [&] {
            writer.append(root);
            pendingCallables(writer, {"test"});
            writer.beginInstructions();
            pendingBodies(instructions);
        };
        fill();
        writer.allocate();
        instructions.allocate();
        fill();
        auto sealed = std::move(instructions).take();
        rejects("consumed metadata writer cannot append fields", [&] {
            writer.field(ClassField{Type::I64, 0, 1, false});
        }, "invalid hosted IR metadata transport");
        static_cast<void>(validate(std::move(sealed)));
    }
    for (const int mode : {0, 1, 2}) {
        rejects("source callable symbols precede pending metadata semantics", [=] {
            const std::vector<std::string> names = mode == 0 ? std::vector<std::string>{}
                : mode == 1 ? std::vector<std::string>{"__au_runtime_reserved"}
                            : std::vector<std::string>{"test", "test"};
            static_cast<void>(validate(pendingMetadata(false, true, names)));
        }, mode == 0 ? "empty module" : mode == 1 ? "invalid or reserved function symbol" : "duplicate function");
    }
    rejects("source duplicate symbol precedes later reserved symbol", [] {
        const std::vector<std::string> names{"test", "test", "__au_runtime_reserved"};
        static_cast<void>(validate(pendingMetadata(false, true, names)));
    }, "duplicate function");
    rejects("source reserved symbol precedes later duplicate symbol", [] {
        const std::vector<std::string> names{"__au_runtime_reserved", "test", "test"};
        static_cast<void>(validate(pendingMetadata(false, true, names)));
    }, "invalid or reserved function symbol");
    for (const auto &[name, mutation] : std::vector<std::pair<const char *, CallableMutation>>{
             {"absent receiver payload", CallableMutation::AbsentReceiver},
             {"unknown callable flags", CallableMutation::UnknownFlag},
             {"nonpacked callable type begin", CallableMutation::RangeBegin},
             {"overlapping callable type range", CallableMutation::RangeCount},
             {"callable name index overflow", CallableMutation::IndexOverflow},
             {"duplicate callable index and missing ID", CallableMutation::IndexDuplicate},
             {"unsorted callable name index", CallableMutation::IndexOrder},
             {"nonpacked callable slot begin", CallableMutation::SlotRangeBegin},
             {"overlapping callable slot ranges", CallableMutation::SlotRangeCount},
             {"unknown frame record kind", CallableMutation::SlotKind},
             {"reversed frame declaration kinds", CallableMutation::SlotKindOrder},
             {"untyped spill has a type index", CallableMutation::SlotUnusedType},
             {"slot type aliases signature prefix", CallableMutation::SlotTypePrefix},
             {"slot type skips packed prefix", CallableMutation::SlotTypeGap},
             {"scalar slot has unused length payload", CallableMutation::SlotLength},
             {"scalar slot has unused mutable payload", CallableMutation::SlotMutable},
             {"duplicate scalar declaration rows", CallableMutation::SlotDuplicate},
             {"reversed scalar declaration rows", CallableMutation::SlotOrder},
             {"uncovered frame declaration suffix", CallableMutation::SlotUncovered},
             {"uncovered frame type suffix", CallableMutation::TypeUncovered}}) {
        rejects(name, [=] {
            static_cast<void>(validate(pendingMetadata(false, false, {"alpha", "omega"}, mutation)));
        }, "invalid hosted IR metadata transport");
    }
    // These exercise source admission for both row counts. They do not
    // substitute for a successful hosted-lowering projection/sort fixture.
    for (const auto mutation : {CallableMutation::NegativeSingleSlot, CallableMutation::NegativePairedSlot}) {
        rejects("negative slot offset is independent of declaration count", [=] {
            static_cast<void>(validate(pendingMetadata(false, false, {"test"}, mutation)));
        }, "invalid typed IR: invalid slot offset");
    }
    rejects("pending scalar declaration preserves malformed raw tail", [] {
        static_cast<void>(validate(pendingMetadata(false, false, {"test"}, CallableMutation::ScalarTail)));
    }, "invalid slot payload type");
    rejects("pending object declaration preserves malformed nominal tail", [] {
        static_cast<void>(validate(pendingMetadata(false, false, {"test"}, CallableMutation::ObjectTail)));
    }, "unknown object class");
    rejects("pending typed owner preserves malformed raw tail", [] {
        static_cast<void>(validate(pendingMetadata(false, false, {"test"}, CallableMutation::OwnerTail)));
    }, "invalid canonical owned value type");
    rejects("pending owner annotation cannot omit owner declaration", [] {
        static_cast<void>(validate(pendingMetadata(false, false, {"test"}, CallableMutation::OrphanOwner)));
    }, "owned value metadata requires exact owner spill");
    rejects("pending frame extent receives independent validation", [] {
        static_cast<void>(validate(pendingMetadata(false, false, {"test"}, CallableMutation::FrameSize)));
    }, "invalid frame size");
    rejects("pending descriptor still receives independent validation", [] {
        static_cast<void>(validate(pendingMetadata(false, true)));
    }, "invalid metadata descriptor");
    rejects("pending supplied physical offsets cannot become canonical by assertion", [] {
        static_cast<void>(validate(pendingMetadata(true)));
    }, "noncanonical class storage metadata");
    rejects("pending callable header requires its body", [] {
        static_cast<void>(validate(pendingMetadata(false, false, {"test"}, CallableMutation::None, 0)));
    }, "invalid hosted IR instruction transport");
    rejects("pending body cannot substitute another callable ID", [] {
        static_cast<void>(pendingMetadata(false, false, {"test"}, CallableMutation::None, 1, true));
    }, "invalid hosted IR instruction transport");
}

} // namespace
int main(int argc, char **argv) {
    try {
        if (argc == 2 && std::string(argv[1]) == "--emit-spans") {
            std::cout << X86Emitter{}.emit(validate(spanCallModule()));
            return 0;
        }
        if (argc == 2 && std::string(argv[1]) == "--emit-value-abi") {
            std::cout << X86Emitter{}.emit(validate(valueBaseline()));
            return 0;
        }
        if (argc == 2 && std::string(argv[1]) == "--emit-packed-methods") {
            std::cout << X86Emitter{}.emit(validate(packedMethodModule()));
            return 0;
        }
        if (argc == 2 && std::string(argv[1]) == "--emit-u8") {
            std::cout << X86Emitter{}.emit(validate(byteOperations()));
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
        if (argc == 2 && std::string(argv[1]) == "--emit-method-results") {
            std::cout << X86Emitter{}.emit(validate(methodResultNativeModule()));
            return 0;
        }
        spanTests();
        enumAndMethodResultTests();
        composedTests();
        arrayReceiverTests();
        unsignedTests();
        byteTests();
        packedStorageTests();
        callableOwnerTests();
        metadataOwnerTests();
        instructionOwnerTests();
        metadataIngressTests();
        initializationPayloadMetricTests();
        callGraphTests();
        reflectionEmissionTests();
        for (const auto operation : {Binary::CheckedDivide, Binary::CheckedRemainder}) {
            const auto name = operation == Binary::CheckedDivide ? "division" : "remainder";
            auto arithmetic = baseline();
            arithmetic.functions[0].code = {
                Constant{84, Type::I64}, Push{}, Constant{2, Type::I64}, BinaryValue{operation}, Return{}};
            accept(std::string("typed checked ") + name, arithmetic);
            rejectModule(
                std::string(name) + " bool right operand",
                arithmetic,
                [](Module &module) {
                    module.functions[0].code[2] = Constant{1, Type::Bool};
                },
                "mistyped current");
            rejectModule(
                std::string(name) + " bool left operand",
                arithmetic,
                [](Module &module) {
                    module.functions[0].code[0] = Constant{1, Type::Bool};
                },
                "noninteger left operand");
            rejectModule(
                std::string(name) + " missing left operand",
                arithmetic,
                [](Module &module) {
                    module.functions[0].code.erase(module.functions[0].code.begin() + 1);
                },
                "stack underflow");
            auto emission = X86Emitter{}.emit(validate(arithmetic));
            const auto zero = emission.find("jz .Laurora_division_zero_trap");
            const auto checked = emission.find("cmpq $-1, %r11");
            const auto division = emission.find("idivq %r11");
            if (zero == std::string::npos || checked == std::string::npos || division == std::string::npos ||
                !(zero < checked && checked < division))
                throw Error("native division must retain zero and overflow checks before IDIV");
            ++passed;
            std::cout << "PASS IR " << name << " guard ordering\n";
        }
        accept("typed load/store", baseline());
        reject(
            "empty module",
            [](Module &m) {
                m.functions.clear();
            },
            "empty module");
        reject(
            "symbol injection",
            [](Module &m) {
                m.functions[0].name = "x:\n.include \"bad\"";
            },
            "function symbol");
        reject(
            "reserved symbol",
            [](Module &m) {
                m.functions[0].name = "aurora_reflect_size";
            },
            "function symbol");
        reject(
            "duplicate function",
            [](Module &m) {
                m.functions.push_back(m.functions[0]);
            },
            "duplicate function");
        reject(
            "bad frame",
            [](Module &m) {
                m.functions[0].frameBytes = 8;
            },
            "frame size");
        reject(
            "oversized frame",
            [](Module &m) {
                m.functions[0].frameBytes = 65552;
            },
            "frame size");
        reject(
            "bad slot",
            [](Module &m) {
                m.functions[0].slots[7] = Type::I64;
            },
            "slot offset");
        reject(
            "slot past frame",
            [](Module &m) {
                m.functions[0].slots[24] = Type::I64;
            },
            "slot offset");
        reject(
            "noncanonical bool",
            [](Module &m) {
                m.functions[0].code[0] = Constant{2, Type::Bool};
            },
            "noncanonical bool");
        reject(
            "load uninitialized",
            [](Module &m) {
                m.functions[0].code.erase(m.functions[0].code.begin(), m.functions[0].code.begin() + 2);
            },
            "load before initialization");
        reject(
            "load wrong type",
            [](Module &m) {
                m.functions[0].code[2] = Load{8, Type::Bool};
            },
            "slot type/layout");
        reject(
            "store wrong type",
            [](Module &m) {
                m.functions[0].code[0] = Constant{1, Type::Bool};
            },
            "mistyped current");
        reject(
            "stack underflow",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin(), Pop{});
            },
            "stack underflow");
        reject(
            "push undefined",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin(), Push{});
            },
            "push without");
        reject(
            "unbalanced return",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.end() - 1, Push{});
            },
            "unbalanced stack");
        reject(
            "wrong return",
            [](Module &m) {
                m.functions[0].result = Type::Bool;
            },
            "mistyped current");
        reject(
            "fallthrough",
            [](Module &m) {
                m.functions[0].code.pop_back();
            },
            "fallthrough");
        reject(
            "unknown jump",
            [](Module &m) {
                m.functions[0].code.push_back(Jump{99});
            },
            "unknown jump");
        reject(
            "duplicate label",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin(), {Label{1}, Label{1}});
            },
            "duplicate or invalid label");
        reject(
            "unreachable operation",
            [](Module &m) {
                m.functions[0].code.push_back(Constant{0, Type::I64});
            },
            "unreachable semantic");
        reject(
            "unreachable bad parameter",
            [](Module &m) {
                m.functions[0].code.push_back(BindParameter{999, 8, Type::I64});
            },
            "outside entry prefix");
        reject(
            "jump over stack effect",
            [](Module &m) {
                m.functions[0].code = {
                    Constant{42, Type::I64}, Jump{1}, Push{}, Label{1}, MetadataQuery{Query::Size}, Return{}};
            },
            "unreachable semantic");
        reject(
            "missing parameter prefix",
            [](Module &m) {
                m.functions[0].parameters = {Type::I64};
            },
            "entry prefix");
        reject(
            "parameter rebound after call",
            [](Module &m) {
                auto &f = m.functions[0];
                f.parameters = {Type::Bool};
                f.slots[8] = Type::Bool;
                f.code = {BindParameter{0, 8, Type::Bool},
                          Constant{42, Type::I64},
                          MetadataQuery{Query::Size},
                          BindParameter{0, 8, Type::Bool},
                          Constant{42, Type::I64},
                          Return{}};
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
                m.functions[0].code.insert(m.functions[0].code.end() - 1, UnaryValue{static_cast<Unary>(99)});
            },
            "invalid unary");
        reject(
            "bad binary enum",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.end() - 1, BinaryValue{static_cast<Binary>(99)});
            },
            "invalid binary");
        reject(
            "bad query enum",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.end() - 1, MetadataQuery{static_cast<Query>(99)});
            },
            "unknown metadata");
        reject(
            "bad descriptor",
            [](Module &m) {
                m.descriptors[-1] = Descriptor{8, 0};
            },
            "invalid metadata");
        reject(
            "borrow uninitialized payload",
            [](Module &m) {
                m.functions[0].code = {BorrowHandle{8, Type::Ref}, Constant{42, Type::I64}, Return{}};
            },
            "uninitialized payload");
        reject(
            "unchecked index",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.end() - 1, IndexLoad{8, 1, Type::I64});
            },
            "bounds token");
        reject(
            "guard invalidated by value change",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.end() - 1,
                                           {Constant{0, Type::I64},
                                            BoundsGuard{8, 1, Type::I64},
                                            Constant{1, Type::I64},
                                            IndexLoad{8, 1, Type::I64}});
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
                f.code = {Constant{42, Type::I64},
                          Store{8, Type::I64},
                          Constant{0, Type::I64},
                          BoundsGuard{16, 2, Type::I64},
                          IndexLoad{16, 2, Type::I64},
                          Return{}};
            },
            "array element not initialized");
        reject(
            "array layout underflow",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.end() - 1, BoundsGuard{8, 2, Type::I64});
            },
            "layout underflow");
        reject(
            "store without checked index",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.end() - 1, {Push{}, IndexStore{8, 1, Type::I64}});
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
        // Direct source constructor returns use these existing operations; no
        // verifier relaxation or special temporary capability is permitted.
        auto directConstructorReturn = receiverBaseline();
        directConstructorReturn.functions[0].result = Type("Pair");
        directConstructorReturn.functions[0].code.resize(6);
        directConstructorReturn.functions[0].code.push_back(ReturnObject{16});
        accept("direct constructor result uses complete active object", directConstructorReturn);
        auto directEmptyComposedReturn = composedEmptyBaseline();
        directEmptyComposedReturn.functions[0].result = Type("OuterEmpty");
        directEmptyComposedReturn.functions[0].code.resize(4);
        directEmptyComposedReturn.functions[0].code.push_back(EndObject{8});
        directEmptyComposedReturn.functions[0].code.push_back(ReturnObject{16});
        accept("direct composed empty result ends argument snapshot", directEmptyComposedReturn);
        rejectModule(
            "direct composed empty result cannot omit logical initialization",
            directEmptyComposedReturn,
            [](Module &m) {
                m.functions[0].code.erase(m.functions[0].code.begin() + 3);
            },
            "nested class field not completely initialized");

        rejectModule(
            "direct constructor result lifetime ended",
            directConstructorReturn,
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.end() - 1, EndObject{16});
            },
            "return outside active lifetime");
        rejectModule(
            "direct constructor result initialization omitted",
            directConstructorReturn,
            [](Module &m) {
                m.functions[0].code = {BeginObject{16}, ReturnObject{16}};
            },
            "returned object not fully initialized");
        rejectModule(
            "direct constructor result nominal mismatch",
            directConstructorReturn,
            [](Module &m) {
                m.classLayouts["Other"] = m.classLayouts["Pair"];
                m.functions[0].result = Type("Other");
            },
            "object return nominal class mismatch");
        rejectModule(
            "direct constructor result retains no operand stack",
            directConstructorReturn,
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.end() - 1, Push{});
            },
            "unbalanced stack at object return");
        rejectModule(
            "direct constructor result cannot hide incomplete constructor",
            directConstructorReturn,
            [](Module &m) {
                m.functions[1].code.erase(m.functions[1].code.begin() + 5);
            },
            "returns before all fields initialized");

        rejectReceiver(
            "missing class layout",
            [](Module &m) {
                m.classLayouts.clear();
            },
            "unknown object class");
        rejectReceiver(
            "non-scalar class layout",
            [](Module &m) {
                m.classLayouts["Pair"][0] = Type::Ref;
            },
            "non-scalar class layout");
        rejectReceiver(
            "unknown bound receiver nominal type",
            [](Module &m) {
                m.functions[2].receiver->className = "Unknown";
            },
            "unknown receiver class");
        rejectReceiver(
            "forged object type",
            [](Module &m) {
                m.classLayouts["Other"] = m.classLayouts["Pair"];
                m.functions[0].objectSlots[16].className = "Other";
            },
            "nominal class mismatch");
        rejectReceiver(
            "forged object scalar layout",
            [](Module &m) {
                m.functions[0].slots[8] = Type::I64;
            },
            "object field slot type/layout mismatch");
        rejectReceiver(
            "missing object field slot",
            [](Module &m) {
                m.functions[0].slots.erase(8);
            },
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
            [](Module &m) {
                m.functions[0].objectSlots[24] = ObjectSlot{"Pair", true};
            },
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
                m.functions[0].code.insert(m.functions[0].code.begin() + 2, ReceiverStore{0, Type::I64});
            },
            "without bound receiver");
        rejectReceiver(
            "negative receiver field",
            [](Module &m) {
                m.functions[2].code[0] = ReceiverLoad{-1, Type::I64};
            },
            "receiver field type/layout");
        rejectReceiver(
            "receiver field past layout",
            [](Module &m) {
                m.functions[2].code[0] = ReceiverLoad{2, Type::I64};
            },
            "receiver field type/layout");
        rejectReceiver(
            "receiver field type forged",
            [](Module &m) {
                m.functions[2].code[0] = ReceiverLoad{1, Type::I64};
            },
            "receiver field type/layout");
        rejectReceiver(
            "receiver cannot become scalar",
            [](Module &m) {
                m.functions[2].code[0] = ReceiverLoad{0, Type::Ref};
            },
            "receiver field type/layout");
        rejectReceiver(
            "receiver write through readonly capability",
            [](Module &m) {
                m.functions[2].code = {Constant{42, Type::I64}, ReceiverStore{0, Type::I64}, Return{}};
            },
            "write through const receiver");
        rejectReceiver(
            "scalar call receiver bypass",
            [](Module &m) {
                m.functions[0].code[6] = Call{"get_pair"};
            },
            "plain call cannot target receiver");
        rejectReceiver(
            "method call scalar target",
            [](Module &m) {
                m.functions[0].code[6] = MethodCall{"test", 16};
            },
            "method call requires receiver target");
        rejectReceiver(
            "unknown method",
            [](Module &m) {
                m.functions[0].code[6] = MethodCall{"missing", 16};
            },
            "unknown method call target");
        rejectReceiver(
            "method requires exact object base",
            [](Module &m) {
                m.functions[0].code[6] = MethodCall{"get_pair", 8};
            },
            "not an object slot");
        rejectReceiver(
            "method rejects negative base",
            [](Module &m) {
                m.functions[0].code[6] = MethodCall{"get_pair", -16};
            },
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
            [](Module &m) {
                m.functions[0].code[6] = MethodCall{"get_pair", 0};
            },
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
            [](Module &m) {
                m.functions[2].receiver->mutableValue = true;
            },
            "const receiver cannot forward mutable");
        rejectReceiver(
            "const local cannot supply mutable receiver",
            [](Module &m) {
                m.functions[3].receiver->mutableValue = true;
            },
            "const object cannot supply mutable");
        rejectReceiver(
            "constructor requires mutable receiver",
            [](Module &m) {
                m.functions[1].receiver->mutableValue = false;
            },
            "invalid constructor receiver signature");
        rejectReceiver(
            "constructor requires i64 internal result",
            [](Module &m) {
                m.functions[1].result = Type::Bool;
            },
            "invalid constructor receiver signature");
        rejectReceiver(
            "constructor missing field",
            [](Module &m) {
                m.functions[1].code.erase(m.functions[1].code.begin() + 4, m.functions[1].code.begin() + 6);
            },
            "before all fields initialized");
        rejectReceiver(
            "constructor duplicate field",
            [](Module &m) {
                m.functions[1].code.insert(m.functions[1].code.begin() + 4, ReceiverStore{0, Type::I64});
            },
            "field initialized more than once");
        rejectReceiver(
            "constructor receiver read even after final write",
            [](Module &m) {
                m.functions[1].code[6] = ReceiverLoad{0, Type::I64};
            },
            "constructor cannot read receiver");
        rejectReceiver(
            "constructor cannot forward receiver",
            [](Module &m) {
                m.functions[1].code[6] = MethodCall{"get_pair", 0};
            },
            "constructor cannot forward receiver");
        rejectReceiver(
            "ordinary method cannot forward as constructor",
            [](Module &m) {
                m.functions[3].code = {Constant{42, Type::I64},
                                       Push{},
                                       Constant{1, Type::Bool},
                                       Push{},
                                       MethodCall{"construct_pair", 0},
                                       Return{}};
            },
            "constructor cannot forward receiver");
        rejectReceiver(
            "method requires full object initialization",
            [](Module &m) {
                m.functions[0].code = {BeginObject{16},
                                       Constant{42, Type::I64},
                                       Store{16, Type::I64},
                                       MethodCall{"get_pair", 16},
                                       Return{}};
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
                                           {Constant{42, Type::I64},
                                            Push{},
                                            Constant{1, Type::Bool},
                                            Push{},
                                            MethodCall{"construct_pair", 16}});
            },
            "constructor called more than once");
        rejectReceiver(
            "constructor argument type",
            [](Module &m) {
                m.functions[0].code[3] = Constant{1, Type::I64};
            },
            "method argument type mismatch");
        rejectReceiver(
            "constructor argument underflow",
            [](Module &m) {
                m.functions[0].code.erase(m.functions[0].code.begin() + 4);
            },
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
                                           {Constant{0, Type::I64},
                                            BoundsGuard{16, 1, Type::I64},
                                            Push{},
                                            Constant{1, Type::I64},
                                            IndexStore{16, 1, Type::I64}});
            },
            "indexed write to const object");
        rejectReceiver(
            "object cannot forge scalar borrow capability",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin() + 6, BorrowHandle{16, Type::Ref});
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
            [](Module &m) {
                m.functions[2].code = {MethodCall{"get_pair", 0}, Return{}};
            },
            "recursive receiver call cycle");
        rejectReceiver(
            "mutually recursive receivers",
            [](Module &m) {
                m.functions[2].code = {MethodCall{"relay_pair", 0}, Return{}};
            },
            "recursive receiver call cycle");
        rejectReceiver(
            "receiver recursion through scalar intermediary",
            [](Module &m) {
                m.functions[2].code = {Call{"test"}, Return{}};
            },
            "recursive receiver call cycle");
        rejectReceiver(
            "unreachable receiver instruction",
            [](Module &m) {
                m.functions[2].code.push_back(ReceiverStore{0, Type::I64});
            },
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
                f.code.insert(
                    f.code.begin() + 1,
                    {Constant{1, Type::Bool}, BranchFalse{1}, Constant{42, Type::I64}, Store{16, Type::I64}, Label{1}});
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
        mutableReceiver.functions[3].code = {Constant{41, Type::I64},
                                             ReceiverStore{0, Type::I64},
                                             Constant{42, Type::I64},
                                             ReceiverStore{0, Type::I64},
                                             MethodCall{"get_pair", 0},
                                             Return{}};
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
        emptyReceiver.functions[1].code = {
            BindParameter{0, 8, Type::I64}, BindParameter{1, 16, Type::Bool}, Constant{0, Type::I64}, Return{}};
        emptyReceiver.functions[2].code = {Constant{42, Type::I64}, Return{}};
        accept("empty object reserves private receiver storage", emptyReceiver);
        rejectModule(
            "empty object constructor cannot repeat",
            emptyReceiver,
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin() + 6,
                                           {Constant{42, Type::I64},
                                            Push{},
                                            Constant{1, Type::Bool},
                                            Push{},
                                            MethodCall{"construct_pair", 16}});
            },
            "constructor called more than once");
        rejectModule(
            "empty object cannot alias scalar slot",
            emptyReceiver,
            [](Module &m) {
                m.functions[0].slots[16] = Type::I64;
            },
            "scalar slot overlaps empty object");
        rejectReceiver(
            "object method before lifetime begin",
            [](Module &m) {
                m.functions[0].code.erase(m.functions[0].code.begin());
            },
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
                m.functions[0].code.insert(m.functions[0].code.begin() + 6, {EndObject{16}, Load{16, Type::I64}});
            },
            "outside active lifetime");
        rejectReceiver(
            "object indexed access after lifetime end",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin() + 6,
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
                m.functions[0].code.insert(m.functions[0].code.begin() + 6, {EndObject{16}, EndObject{16}});
            },
            "lifetime is not active");
        rejectReceiver(
            "object begin requires exact base",
            [](Module &m) {
                m.functions[0].code[0] = BeginObject{8};
            },
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
                m.functions[0].code.insert(m.functions[0].code.begin() + 6, {EndObject{16}, BeginObject{16}});
            },
            "object not fully initialized");
        rejectReceiver(
            "branch cannot skip lifetime end",
            [](Module &m) {
                m.functions[0].code.insert(
                    m.functions[0].code.end() - 1,
                    {Constant{1, Type::Bool}, BranchFalse{1}, EndObject{16}, Label{1}, Constant{42, Type::I64}});
            },
            "incompatible active object lifetimes");
        rejectReceiver(
            "branch cannot skip lifetime begin",
            [](Module &m) {
                m.functions[0].code.insert(
                    m.functions[0].code.begin(),
                    {Constant{1, Type::Bool}, BranchFalse{1}, Jump{2}, Label{1}, BeginObject{16}, Label{2}});
            },
            "incompatible active object lifetimes");
        rejectReceiver(
            "loop cannot silently restart active object",
            [](Module &m) {
                auto &code = m.functions[0].code;
                code.insert(code.begin(), Label{1});
                code.insert(code.end() - 1, {Constant{1, Type::Bool}, BranchFalse{1}, Constant{42, Type::I64}});
            },
            "incompatible active object lifetimes");
        auto lifetimeReuse = receiverBaseline();
        lifetimeReuse.functions[0].code.insert(lifetimeReuse.functions[0].code.begin() + 6,
                                               {EndObject{16},
                                                BeginObject{16},
                                                Constant{42, Type::I64},
                                                Push{},
                                                Constant{1, Type::Bool},
                                                Push{},
                                                MethodCall{"construct_pair", 16}});
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
                              {Constant{99, Type::I64},
                               Push{},
                               Constant{1, Type::I64},
                               Push{},
                               Constant{2, Type::I64},
                               Push{},
                               Constant{3, Type::I64},
                               Push{},
                               Constant{4, Type::I64},
                               Push{},
                               Constant{5, Type::I64},
                               Push{},
                               Constant{6, Type::I64},
                               Push{}});
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
            "deep scalar bridge cannot hide receiver cycle",
            deepCalls,
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
            "unknown value call",
            [](Module &m) {
                valueCall(m).callee = "missing";
            },
            "unknown aggregate call");
        rejectValue(
            "missing value argument vector",
            [](Module &m) {
                valueCall(m).objectArguments.clear();
            },
            "vector size");
        rejectValue(
            "extra value argument vector entry",
            [](Module &m) {
                valueCall(m).objectArguments.push_back(0);
            },
            "vector size");
        rejectValue(
            "scalar argument cannot contain object base",
            [](Module &m) {
                valueCall(m).objectArguments[1] = 16;
            },
            "scalar argument cannot");
        rejectValue(
            "class argument cannot be scalar zero",
            [](Module &m) {
                valueCall(m).objectArguments[0] = 0;
            },
            "exact object slot");
        rejectValue(
            "class argument cannot be negative",
            [](Module &m) {
                valueCall(m).objectArguments[0] = -16;
            },
            "exact object slot");
        rejectValue(
            "class argument requires exact base",
            [](Module &m) {
                valueCall(m).objectArguments[0] = 8;
            },
            "exact object slot");
        rejectValue(
            "argument snapshots cannot alias",
            [](Module &m) {
                valueCall(m).objectArguments[2] = 16;
            },
            "snapshots must be distinct");
        rejectValue(
            "argument nominal class identity",
            [](Module &m) {
                m.classLayouts["Other"] = m.classLayouts["Pair"];
                m.functions[0].objectSlots[16].className = "Other";
            },
            "argument nominal class");
        rejectValue(
            "argument snapshot readonly",
            [](Module &m) {
                m.functions[0].objectSlots[16].mutableValue = true;
            },
            "snapshot must be readonly");
        rejectValue(
            "argument snapshot inactive",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin() + 15, EndObject{16});
            },
            "argument outside active");
        rejectValue(
            "argument snapshot partially initialized",
            [](Module &m) {
                m.functions[0].code.erase(m.functions[0].code.begin() + 4);
            },
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
            [](Module &m) {
                m.functions[0].code[12] = Constant{1, Type::I64};
            },
            "scalar argument type");
        rejectValue(
            "argument missing scalar operand",
            [](Module &m) {
                m.functions[0].code.erase(m.functions[0].code.begin() + 13);
            },
            "scalar argument type");
        rejectValue(
            "result cannot be zero",
            [](Module &m) {
                valueCall(m).resultOffset = 0;
            },
            "result requires exact");
        rejectValue(
            "result cannot be negative",
            [](Module &m) {
                valueCall(m).resultOffset = -48;
            },
            "result requires exact");
        rejectValue(
            "result cannot be interior field",
            [](Module &m) {
                valueCall(m).resultOffset = 40;
            },
            "result requires exact");
        rejectValue(
            "result cannot alias snapshot",
            [](Module &m) {
                valueCall(m).resultOffset = 16;
            },
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
            [](Module &m) {
                m.functions[0].code.erase(m.functions[0].code.begin() + 14);
            },
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
                                           {Constant{10, Type::I64},
                                            Push{},
                                            Constant{1, Type::Bool},
                                            Push{},
                                            AggregateCall{"copy_pair", {16, 0, 32, 0}, 48}});
            },
            "result object already initialized");
        rejectValue(
            "result cannot conditionally initialize twice",
            [](Module &m) {
                auto &code = m.functions[0].code;
                code.insert(code.begin() + 16,
                            {Constant{1, Type::Bool},
                             BranchFalse{1},
                             EndObject{48},
                             BeginObject{48},
                             Label{1},
                             Constant{10, Type::I64},
                             Push{},
                             Constant{1, Type::Bool},
                             Push{},
                             AggregateCall{"copy_pair", {16, 0, 32, 0}, 48}});
            },
            "result object already initialized");
        rejectValue(
            "result scalar current cannot carry class capability",
            [](Module &m) {
                m.functions[0].code.erase(m.functions[0].code.begin() + 16);
            },
            "mistyped current");
        rejectValue(
            "plain call cannot bypass value ABI",
            [](Module &m) {
                m.functions[0].code[15] = Call{"copy_pair"};
            },
            "plain call cannot target aggregate");
        rejectValue(
            "object return exact slot",
            [](Module &m) {
                m.functions[1].code.back() = ReturnObject{56};
            },
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
            [](Module &m) {
                m.functions[1].code.erase(m.functions[1].code.end() - 2);
            },
            "returned object not fully");
        rejectValue(
            "object return balanced scalar stack",
            [](Module &m) {
                m.functions[1].code.insert(m.functions[1].code.end() - 1, Push{});
            },
            "unbalanced stack at object return");
        rejectValue(
            "scalar return cannot bypass value ABI",
            [](Module &m) {
                m.functions[1].code.back() = Return{};
            },
            "scalar return cannot return class");
        rejectValue(
            "object return cannot bypass scalar result",
            [](Module &m) {
                m.functions[0].code.back() = ReturnObject{48};
            },
            "object return requires class");
        rejectValue(
            "object bind cannot use scalar instruction",
            [](Module &m) {
                m.functions[1].code[0] = BindParameter{0, 16, Type("Pair")};
            },
            "entry prefix");
        rejectValue(
            "scalar bind cannot use object instruction",
            [](Module &m) {
                m.functions[1].code[1] = BindObjectParameter{1, 16, "Pair"};
            },
            "entry prefix");
        rejectValue(
            "object bind wrong index",
            [](Module &m) {
                m.functions[1].code[0] = BindObjectParameter{1, 16, "Pair"};
            },
            "entry prefix");
        rejectValue(
            "object bind wrong declared class",
            [](Module &m) {
                m.functions[1].code[0] = BindObjectParameter{0, 16, "Other"};
            },
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
            [](Module &m) {
                m.functions[1].code[0] = BindObjectParameter{0, 8, "Pair"};
            },
            "object parameter requires exact");
        rejectValue(
            "object bind readonly requirement",
            [](Module &m) {
                m.functions[1].objectSlots[16].mutableValue = true;
            },
            "object parameter must be readonly");
        rejectValue(
            "object parameters cannot alias",
            [](Module &m) {
                m.functions[1].code[2] = BindObjectParameter{2, 16, "Pair"};
            },
            "object parameter bindings overlap");
        rejectValue(
            "object bind outside prefix",
            [](Module &m) {
                m.functions[1].code.insert(m.functions[1].code.begin() + 4, BindObjectParameter{0, 16, "Pair"});
            },
            "outside entry prefix");
        rejectValue(
            "object parameter cannot restart lifetime",
            [](Module &m) {
                m.functions[1].code.insert(m.functions[1].code.begin() + 4, {EndObject{16}, BeginObject{16}});
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
                                           {Constant{0, Type::I64},
                                            BoundsGuard{24, 1, Type::I64},
                                            Push{},
                                            Constant{9, Type::I64},
                                            IndexStore{24, 1, Type::I64}});
            },
            "indexed write to immutable scalar");
        rejectValue(
            "method aggregate result signature denied",
            [](Module &m) {
                m.functions[1].receiver = Receiver{"Pair", false, false};
            },
            "aggregate call cannot target receiver");
        rejectValue(
            "value-call hidden frame slot inaccessible",
            [](Module &m) {
                m.functions[1].slots[72] = Type::I64;
            },
            "invalid slot offset");
        rejectValue(
            "value-call class capabilities are not scalar slots",
            [](Module &m) {
                m.functions[1].slots[16] = Type("Pair");
            },
            "invalid slot payload");
        rejectValue(
            "value signature cannot contain reference",
            [](Module &m) {
                m.functions[0].parameters = {Type::Ref};
            },
            "invalid value boundary type");
        rejectValue(
            "value signature cannot contain mutable reference",
            [](Module &m) {
                m.functions[0].result = Type::MutRef;
            },
            "invalid value boundary type");
        rejectValue(
            "value signature cannot contain owner",
            [](Module &m) {
                m.functions[0].result = Type::Own;
            },
            "invalid value boundary type");
        rejectValue(
            "value signature cannot contain array",
            [](Module &m) {
                m.functions[0].result = Type::array(TypeKind::I64, 1);
            },
            "invalid value boundary type");
        rejectValue(
            "value signature unknown nominal type",
            [](Module &m) {
                m.functions[0].result = Type("Missing");
            },
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
            [](Module &m) {
                m.functions[0].parameters = std::vector<Type>(7, Type("Pair"));
            },
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
                m.functions[0].code.insert(m.functions[0].code.begin(), AggregateCall{"test", {}, 0});
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
            "scalar result rejects object result storage",
            scalarValueResult,
            [](Module &m) {
                valueCall(m).resultOffset = 48;
            },
            "scalar result cannot name");
        auto reusableValueResult = valueBaseline();
        reusableValueResult.functions[0].code.insert(reusableValueResult.functions[0].code.begin() + 16,
                                                     {EndObject{48},
                                                      BeginObject{48},
                                                      Constant{10, Type::I64},
                                                      Push{},
                                                      Constant{1, Type::Bool},
                                                      Push{},
                                                      AggregateCall{"copy_pair", {16, 0, 32, 0}, 48}});
        accept("result storage reused only after lifetime transition", reusableValueResult);
        auto mutableValueResult = valueBaseline();
        mutableValueResult.functions[0].objectSlots[48].mutableValue = true;
        mutableValueResult.functions[0].code.insert(mutableValueResult.functions[0].code.begin() + 16,
                                                    {Constant{43, Type::I64}, Store{48, Type::I64}});
        accept("returned value has caller-selected mutability", mutableValueResult);
        auto retainedGuard = valueBaseline();
        retainedGuard.functions[0].code.insert(retainedGuard.functions[0].code.begin() + 10,
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
            "empty value result cannot initialize twice",
            emptyValues,
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin() + 4, AggregateCall{"copy_empty", {8}, 16});
            },
            "result object already initialized");
        rejectModule(
            "empty parameter cannot become result target",
            emptyValues,
            [](Module &m) {
                m.functions[1].code.insert(m.functions[1].code.begin() + 1, AggregateCall{"make_empty", {}, 8});
            },
            "result object already initialized");
        rejectModule(
            "empty result cannot alias empty argument",
            emptyValues,
            [](Module &m) {
                std::get<AggregateCall>(m.functions[0].code[3]).resultOffset = 8;
            },
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
        largeEntry.objectSlots = {{512, ObjectSlot{"Empty", false}}, {1024, ObjectSlot{"Empty", false}}};
        largeEntry.code = {BeginObject{512}, Constant{42, Type::I64}};
        for (int field = 0; field < 64; ++field) {
            largeEntry.slots[512 - field * 8] = Type::I64;
            largeEntry.slots[1024 - field * 8] = Type::I64;
            largeEntry.code.push_back(Store{512 - field * 8, Type::I64});
        }
        largeEntry.code.insert(
            largeEntry.code.end(),
            {BeginObject{1024}, AggregateCall{"copy_empty", {512}, 1024}, Load{520, Type::I64}, Return{}});
        auto &largeCopy = largeValue.functions[1];
        largeCopy.frameBytes = 512;
        largeCopy.objectSlots[512] = ObjectSlot{"Empty", false};
        for (int field = 0; field < 64; ++field)
            largeCopy.slots[512 - field * 8] = Type::I64;
        largeCopy.code = {BindObjectParameter{0, 512, "Empty"}, ReturnObject{512}};
        largeValue.functions.pop_back();
        accept("64-field value boundary accepted", largeValue);
        X86Emitter largeEmitter;
        const auto largeAssembly = largeEmitter.emit(validate(largeValue));
        const auto copyBegin = largeAssembly.find("copy_empty:\n");
        const auto copyEnd = largeAssembly.find(".size copy_empty,", copyBegin);
        const auto firstRepeat = largeAssembly.find("rep movsb", copyBegin);
        const auto secondRepeat = largeAssembly.find("rep movsb", firstRepeat + 1);
        if (copyBegin == std::string::npos || copyEnd == std::string::npos || firstRepeat >= copyEnd ||
            secondRepeat >= copyEnd || largeAssembly.find("rep movsb", secondRepeat + 1) < copyEnd ||
            largeAssembly.substr(0, copyBegin)
                    .find("leaq 0(%rsp), %rax\n    pushq %rsi\n    pushq %rdi\n    pushq %rcx") == std::string::npos ||
            largeAssembly.find("pushq %rsi\n    pushq %rdi\n    pushq %rcx", copyBegin) >= copyEnd ||
            largeAssembly.find("movq $512, %rcx\n    cld\n    rep movsb\n    popq %rcx\n    popq %rdi\n    popq %rsi",
                               copyBegin) >= copyEnd ||
            largeEmitter.stackFacts().at("copy_empty").localBytes != 568 ||
            largeEmitter.stackFacts().at(largeEntry.name).localBytes != 1576 ||
            largeEmitter.stackFacts().at(largeEntry.name).calls.at("copy_empty") != 1552)
            throw Error("compact copies changed saved registers, exact extent, stack peak or captured RSP packing");
        ++passed;
        std::cout << "PASS IR compact copies preserve registers and report transient stack peak\n";

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
        valueBridge.code = {BindObjectParameter{0, 16, "Pair"}, MethodCall{"get_pair", 16}, Return{}};
        receiverValueCycle.functions.push_back(valueBridge);
        rejectModule(
            "aggregate edge cannot conceal receiver recursion",
            receiverValueCycle,
            [](Module &) {
            },
            "recursive receiver call cycle");
        receiverValueCycle.functions.back().code = {BindObjectParameter{0, 16, "Pair"}, Load{16, Type::I64}, Return{}};
        accept("receiver may call acyclic ordinary value helper", receiverValueCycle);
        rejectModule(
            "receiver aggregate parameter requires explicit snapshot vector",
            receiverValueCycle,
            [](Module &m) {
                m.functions.back().receiver = Receiver{"Pair", false, false};
                m.functions[2].code[5] = MethodCall{"value_bridge", 16};
            },
            "receiver object argument vector size mismatch");
        const auto valueAssembly = X86Emitter{}.emit(validate(valueBaseline()));
        for (const auto &fragment : {".local copy_pair",
                                     "movq %r11, -72(%rbp)",
                                     "movq %r10, -80(%rbp)",
                                     "movq %rsp, %r11",
                                     "leaq -48(%rbp), %r10",
                                     "movq 40(%r11), %rax",
                                     "movq %rax, 8(%r10)"})
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
                                   IndexLoad{elementCount * 8, elementCount, Type::I64},
                                   Return{}});
        verification::Metrics metrics;
        static_cast<void>(validate(std::move(large), &metrics));
        if (metrics.peakOperandDepth != elementCount || metrics.snapshots > 8 ||
            metrics.peakRetainedValueFacts > elementCount * 16 ||
            metrics.peakRetainedInitializationPayloadBytes !=
                metrics.snapshots * 2 * (elementCount / 64) * sizeof(std::uint64_t))
            throw Error("maximum initializer retained non-linear verifier state");
        ++passed;
        std::cout << "PASS IR bounded maximum initializer: snapshots=" << metrics.snapshots
                  << ", peak operand depth=" << metrics.peakOperandDepth
                  << ", retained facts=" << metrics.peakRetainedValueFacts
                  << ", initialization payload bytes=" << metrics.peakRetainedInitializationPayloadBytes << '\n';
        reject(
            "query cannot change module view",
            [](Module &m) {
                m.descriptorViews[1] = {};
                m.functions[0].code.insert(m.functions[0].code.end() - 1, MetadataQuery{Query::Size, 1});
            },
            "changes defining-module scope");
        reject(
            "unknown function module view",
            [](Module &m) {
                m.functions[0].moduleScope = 1;
            },
            "unknown function module scope");
        reject(
            "view cannot name missing descriptor",
            [](Module &m) {
                m.descriptorViews[0].insert(999);
            },
            "missing descriptor");
        reject(
            "module view scope cap",
            [](Module &m) {
                m.descriptorViews[64] = {};
            },
            "invalid reflection scope");
        reject(
            "scoped helper name reserved",
            [](Module &m) {
                m.functions[0].name = "__au_reflect_s1_size";
            },
            "function symbol");
        auto guarded = baseline();
        guarded.functions[0].code.insert(guarded.functions[0].code.end() - 1,
                                         {Constant{0, Type::I64},
                                          BoundsGuard{8, 1, Type::I64},
                                          Push{},
                                          Constant{42, Type::I64},
                                          MetadataQuery{Query::Size},
                                          IndexStore{8, 1, Type::I64}});
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
            [](Module &m) {
                m.functions[0].result = Type(TypeKind::Parameter);
            },
            "invalid value boundary type");
        reject(
            "unsubstituted template parameter slot",
            [](Module &m) {
                m.functions[0].slots[8] = Type(TypeKind::Parameter);
            },
            "invalid slot payload type");
        reject(
            "unsubstituted template parameter constant",
            [](Module &m) {
                std::get<Constant>(m.functions[0].code[0]).type = Type(TypeKind::Parameter);
            },
            "invalid constant type");
        rejectValue(
            "unresolved specialization arguments on result",
            [](Module &m) {
                m.functions[1].result.templateArguments = {TypeKind::I64};
            },
            "invalid value boundary type");
        rejectValue(
            "unresolved specialization arguments on parameter",
            [](Module &m) {
                m.functions[1].parameters[0].templateArguments = {TypeKind::I64};
            },
            "invalid value boundary type");
        // Nested syntax is frontend-only. Even a tree whose leaf types and
        // apparent layout are otherwise valid cannot reach the concrete IR.
        const auto nestedArgument = [] {
            TemplateArgument inner("Inner");
            inner.templateArguments = {TypeKind::U8, TemplateArgument::capacity(16)};
            TemplateArgument outer("Outer");
            outer.templateArguments = {inner, TypeKind::I64};
            return outer;
        };
        rejectValue(
            "unresolved nested specialization result",
            [&](Module &m) {
                m.functions[1].result.templateArguments = {nestedArgument()};
            },
            "invalid value boundary type");
        rejectValue(
            "unresolved nested specialization parameter",
            [&](Module &m) {
                m.functions[1].parameters[0].templateArguments = {nestedArgument()};
            },
            "invalid value boundary type");
        reject(
            "unresolved nested specialization scalar slot",
            [&](Module &m) {
                m.functions[0].slots[8].templateArguments = {nestedArgument()};
            },
            "invalid slot payload type");
        reject(
            "unresolved nested specialization scalar constant",
            [&](Module &m) {
                std::get<Constant>(m.functions[0].code[0]).type.templateArguments = {nestedArgument()};
            },
            "noncanonical instruction type payload");
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
        rejectValue(
            "function-template unresolved value parameter",
            [](Module &m) {
                m.functions[1].parameters[0] = Type(TypeKind::Parameter);
            },
            "invalid aggregate parameter type");
        rejectValue(
            "function-template unresolved scalar parameter",
            [](Module &m) {
                m.functions[1].parameters[1] = Type(TypeKind::Parameter);
            },
            "invalid aggregate parameter type");
        rejectValue(
            "function-template dependent class result metadata",
            [](Module &m) {
                TemplateArgument parameter(TypeKind::Parameter);
                parameter.className = "T";
                m.functions[1].result.templateArguments = {parameter};
            },
            "invalid value boundary type");
        rejectValue(
            "function-template substituted identity cannot retain argument metadata",
            [](Module &m) {
                TemplateArgument argument("Pair");
                argument.resolvedClass = true;
                m.functions[1].parameters[0].templateArguments = {argument};
            },
            "invalid value boundary type");
        std::cout << passed << " typed IR tests passed\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
