// Whole-function verifier contract fixtures through the real ingress/validate path.
// These 63 builders retain the independently compared native-oracle constructions.
// Expected diagnostics and partial metrics are frozen separately, not computed by
// this verifier. No native verifier implementation or copied instruction stream.
#include "ir_verify.hpp"
#include <array>
#include <cstdint>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>
#include <vector>

using namespace aurora;
using namespace aurora::ir;
using IRFunction = aurora::ir::Function;

namespace {
constexpr std::string_view protocol = "aurora-verifier-comparison-v2";
constexpr std::array<std::string_view, 63> fixtures{
    "valid-trivial",
    "literal-span-missing-spill-before-metrics",
    "uninitialized-scalar",
    "declaration-order-load-first",
    "declaration-order-underflow-first",
    "unused-declaration-load-first",
    "unused-declaration-underflow-first",
    "unused-invalid-after-valid-root",
    "target-before-fallthrough",
    "duplicate-join",
    "return-43-unbalanced",
    "return-44-valid",
    "return-44-unbalanced",
    "return-53-valid",
    "return-53-unbalanced",
    "return-76-valid",
    "return-76-unbalanced",
    "return-80-valid",
    "return-80-unbalanced",
    "byte-operations-valid",
    "enum-baseline-valid",
    "enum-cross-store",
    "enum-cross-call",
    "terminal-value-before-fallthrough",
    "unreachable-after-return",
    "initialized-empty-valid",
    "owning-copied-child-valid",
    "class-array-local-valid",
    "receiver-array-valid",
    "owned-values-valid",
    "owned-values-parameter-valid",
    "readonly-owner-at-valid",
    "owning-byte-store-valid",
    "owned-bytes-resize-valid",
    "console-forwarded-valid",
    "short-circuit-span-metadata-valid",
    "fixed-field-span-valid",
    "literal-window-valid",
    "borrowed-const-local-valid",
    "initialized-borrow-handle-valid",
    "typed-move-to-bytes",
    "typed-move-to-other",
    "typed-return-as-bytes",
    "typed-return-as-other",
    "range-missing-before-inactive",
    "range-inactive-before-missing",
    "linear-depth-before-omitted",
    "omitted-before-linear-depth",
    "typed-entry-other-before-body",
    "unused-static-storage-before-dynamic",
    "resource-operand-exact",
    "resource-operand-over",
    "resource-state-exact",
    "resource-state-over",
    "resource-operand-exact-null-metrics",
    "resource-operand-over-null-metrics",
    "resource-state-exact-null-metrics",
    "resource-state-over-null-metrics",
    "resource-revisit-valid",
    "borrowed-bound-root-reborrow-valid",
    "borrowed-bound-root-direct-field-denied",
    "borrowed-bound-root-nominal-mismatch",
    "borrowed-bound-root-unbound-selector",
};

IRFunction scalarFunction(std::string name) {
    IRFunction function;
    function.name = std::move(name);
    function.result = Type::I64;
    function.code = {Constant{42, Type::I64}, Return{}};
    return function;
}

IRFunction uninitializedFunction(std::string name) {
    auto function = scalarFunction(std::move(name));
    // Same admitted scalar frame as tests/compiler/ir_tests.cpp::baseline.
    function.frameBytes = 16;
    function.slots = {{8, Type::I64}};
    function.code = {Load{8, Type::I64}, Return{}};
    return function;
}

IRFunction underflowFunction(std::string name) {
    auto function = scalarFunction(std::move(name));
    function.code = {Pop{}, Return{}};
    return function;
}

Module single(IRFunction function) {
    Module module;
    module.functions.push_back(std::move(function));
    return module;
}

Module declarationOrder(bool loadFirst, bool unusedFirst) {
    Module module;
    // Lexical symbol order intentionally opposes declaration order. Both bodies
    // contain distinct dynamic errors, but all metadata/static contracts are valid.
    auto first = loadFirst ? uninitializedFunction("z_declared_first") : underflowFunction("z_declared_first");
    auto second = loadFirst ? underflowFunction("a_declared_second") : uninitializedFunction("a_declared_second");
    if (unusedFirst) {
        module.descriptorViews[1] = {};
        first.moduleScope = 1;
        // No call reaches this imported body. It must still be verified first.
    }
    module.functions = {std::move(first), std::move(second)};
    return module;
}

void leaveOperand(IRFunction &function) {
    // Insert after all admitted entry bindings and immediately before the return.
    // This reaches the selected return's dynamic nonempty-stack check without
    // forging a nominal return type, a spill declaration or a capability token.
    function.code.insert(function.code.end() - 1, {Constant{7, Type::I64}, Push{}});
}

Module copiedReturn(bool unbalanced) {
    Module module;
    module.classLayouts["Word"] = {Type::I64};
    auto function = scalarFunction("copy_return");
    function.result = Type("Word");
    function.parameters = {Type("Word")};
    function.frameBytes = 16;
    function.slots = {{8, Type::I64}};
    function.objectSlots = {{8, {"Word", false}}};
    // Bound copied-parameter return follows ir_tests.cpp::emptyValueBaseline
    // and valueBaseline, using a nonempty one-leaf class.
    function.code = {BindObjectParameter{0, 8, "Word"}, ReturnObject{8}};
    if (unbalanced)
        leaveOperand(function);
    module.functions.push_back(std::move(function));
    return module;
}

Module owningShape() {
    // Same logical "Only" owning class as owning_classes_ir.cpp::shapes.
    // Canonical storage is derived by admission, not supplied by a descriptor.
    Module module;
    module.classLayouts["Only"] = {};
    module.classFields["Only"] = {{Type::OwnedBytes, 0, 0, false}};
    return module;
}

Module spanReturn(bool unbalanced) {
    auto module = owningShape();
    auto function = scalarFunction("span_return");
    function.result = Type::ByteSpan;
    function.receiver = Receiver{"Only", false, false};
    function.receiverSpanField = 0;
    function.frameBytes = 64;
    function.spanSlots = {56};
    // Receiver-derived authority follows owned_spans_ir.cpp::view. There is
    // neither a fabricated span token nor a separately admitted metadata owner.
    function.code = {BorrowOwnedSpan{0, 0, 56}, ReturnSpan{56}};
    if (unbalanced)
        leaveOperand(function);
    module.functions.push_back(std::move(function));
    return module;
}

Module bytesReturn(bool unbalanced) {
    auto function = scalarFunction("bytes_return");
    function.result = Type::OwnedBytes;
    function.parameters = {Type::ByteRegion, Type::OwnedBytes};
    function.frameBytes = 48;
    function.regionSlots = {8};
    function.byteSlots = {{40, true}};
    // Reduced disjoint frame from owned_bytes_ir.cpp::owningParameter(true).
    function.code = {BindRegionParameter{0, 8}, BindBytesParameter{1, 40}, ReturnBytes{40}};
    if (unbalanced)
        leaveOperand(function);
    return single(std::move(function));
}

Module owningReturn(bool unbalanced) {
    auto module = owningShape();
    auto function = scalarFunction("owning_return");
    function.result = Type("Only");
    function.parameters = {Type::ByteRegion, Type("Only")};
    function.frameBytes = 48;
    function.regionSlots = {8};
    function.objectSlots = {{40, {"Only", true}}};
    // Bound-owner return uses the same entry/return operations as
    // owning_classes_ir.cpp::ordinary/moving without unrelated parcel fields.
    function.code = {BindRegionParameter{0, 8}, BindOwnedObjectParameter{1, 40, "Only"}, ReturnOwnedObject{40}};
    if (unbalanced)
        leaveOperand(function);
    module.functions.push_back(std::move(function));
    return module;
}

// Copied narrowly from tests/compiler/ir_tests.cpp: byteOperations, enumBaseline,
// and only their raw-Module builder dependencies. These are ordinary public
// ingress inputs; no admitted instruction, native verifier API or test escape is
// used. Byte operations add forms 8, 11-17, 20, 21, 32, 33, 38, 45; enum operations
// add forms 6 and 19 beyond the original 19-fixture vocabulary.
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

// Exact raw-Module builders and required helpers from tests/compiler/owned_bytes_ir.cpp.
namespace emptyObjectFixture {
Module initializedEmpty() {
    Module module;
    module.classLayouts["Empty"] = {};
    IRFunction function;
    function.name = "explicit_empty";
    function.result = Type("Empty");
    function.frameBytes = 16;
    function.objectSlots = {{8, {"Empty", false}}};
    function.code = {BeginObject{8}, InitializeEmptyObject{8}, ReturnObject{8}};
    module.functions.push_back(std::move(function));
    return module;
}
} // namespace emptyObjectFixture

// Exact raw-Module builders and required helpers from tests/compiler/owning_classes_ir.cpp.
namespace owningChildFixture {
Module shapes() {
    Module module;
    module.classLayouts = {{"Parcel", {Type::U8, Type::U64, Type::U8}},
                           {"Only", {}},
                           {"Pair", {}},
                           {"Copy", {Type::U8, Type::U64}},
                           {"Empty", {}}};
    module.classFields["Parcel"] = {{Type::U8, 0, 1, false},
                                    {Type::OwnedBytes, 1, 0, false},
                                    {Type::U64, 1, 1, false},
                                    {Type::OwnedBytes, 2, 0, false},
                                    {Type::U8, 2, 1, false}};
    module.classFields["Only"] = {{Type::OwnedBytes, 0, 0, false}};
    module.classFields["Pair"] = {{Type::OwnedBytes, 0, 0, false}, {Type::OwnedBytes, 0, 0, false}};
    module.classFields["Copy"] = {{Type::U8, 0, 1, false}, {Type::U64, 1, 1, false}};
    module.classFields["Empty"] = {};
    module.classStorage = {{"Parcel", {{0, 40, 80}, {0, 8, 40, 48, 80}, 88, 8, 88}},
                           {"Only", {{}, {0}, 32, 8, 32}},
                           {"Pair", {{}, {0, 32}, 64, 8, 64}},
                           {"Copy", {{0, 8}, {0, 8}, 16, 8, 16}},
                           {"Empty", {{}, {}, 8, 8, 8}}};
    return module;
}

void parcel(IRFunction &function, int base, bool mutableValue = true) {
    function.objectSlots[base] = {"Parcel", mutableValue};
    function.slots[base] = Type::U8;
    function.slots[base - 40] = Type::U64;
    function.slots[base - 80] = Type::U8;
}

IRFunction ordinary(const std::string &name = "owning_entry", Type result = Type::I64) {
    IRFunction function;
    function.name = name;
    function.result = result;
    function.parameters = {Type::ByteRegion, Type("Parcel")};
    function.regionSlots = {8, 416};
    function.frameBytes = 416;
    parcel(function, 96);
    parcel(function, 184);
    parcel(function, 272);
    function.byteSlots = {{304, true}, {336, true}};
    function.code = {BindRegionParameter{0, 8}, BindOwnedObjectParameter{1, 96, "Parcel"}};
    return function;
}

Module copiedChild() {
    auto module = shapes();
    module.classLayouts["Container"] = {Type::U8, Type::U64, Type::U8};
    module.classFields["Container"] = {
        {Type::OwnedBytes, 0, 0, false}, {Type("Copy"), 0, 2, false}, {Type::U8, 2, 1, false}};
    module.classStorage["Container"] = {{32, 40, 48}, {0, 32, 48}, 56, 8, 56};
    auto caller = ordinary("owning_entry", Type::U64);
    caller.parameters = {Type::ByteRegion};
    caller.objectSlots = {
        {96, {"Container", true}}, {184, {"Container", true}}, {368, {"Copy", false}}, {384, {"Copy", true}}};
    caller.slots = {{64, Type::U8},
                    {56, Type::U64},
                    {48, Type::U8},
                    {152, Type::U8},
                    {144, Type::U64},
                    {136, Type::U8},
                    {368, Type::U8},
                    {360, Type::U64},
                    {384, Type::U8},
                    {376, Type::U64}};
    caller.code = {BindRegionParameter{0, 8},
                   BeginBytes{304},
                   Constant{3, Type::I64},
                   AllocateBytes{8, 304},
                   BeginObject{368},
                   Constant{17, Type::U8},
                   Store{368, Type::U8},
                   Constant{99, Type::U64},
                   Store{360, Type::U64},
                   BeginObject{96},
                   ResourceCall{"copy_constructor", 8, {0, 304, 368}, 0, 96},
                   EndBytes{304},
                   Constant{42, Type::U64},
                   Push{},
                   BeginObject{384},
                   MethodCall{"copy_method", 96, {368, 0}, 384},
                   Load{376, Type::U64},
                   EndObject{384},
                   EndObject{368},
                   EndObject{96},
                   Return{}};
    IRFunction ctor;
    ctor.name = "copy_constructor";
    ctor.result = Type::I64;
    ctor.receiver = Receiver{"Container", true, true};
    ctor.parameters = {Type::ByteRegion, Type::OwnedBytes, Type("Copy")};
    ctor.frameBytes = 64;
    ctor.regionSlots = {8};
    ctor.byteSlots = {{40, true}};
    ctor.objectSlots = {{56, {"Copy", false}}};
    ctor.slots = {{56, Type::U8}, {48, Type::U64}};
    ctor.code = {BindRegionParameter{0, 8},
                 BindBytesParameter{1, 40},
                 BindObjectParameter{2, 56, "Copy"},
                 InitializeBytesField{0, 0, 40},
                 InitializeObjectField{0, 1, 56},
                 Constant{77, Type::U8},
                 ReceiverStore{2, Type::U8},
                 EndBytes{40},
                 Constant{0, Type::I64},
                 Return{}};
    IRFunction method;
    method.name = "copy_method";
    method.result = Type("Copy");
    method.receiver = Receiver{"Container", true, false};
    method.parameters = {Type("Copy"), Type::U64};
    method.frameBytes = 48;
    method.objectSlots = {{16, {"Copy", false}}, {48, {"Copy", true}}};
    method.slots = {{16, Type::U8}, {8, Type::U64}, {24, Type::U64}, {48, Type::U8}, {40, Type::U64}};
    method.code = {BindObjectParameter{0, 16, "Copy"},
                   BindParameter{1, 24, Type::U64},
                   AssignObjectField{0, 1, 16},
                   BeginObject{48},
                   ObjectFieldCopy{0, 1, 48},
                   Load{24, Type::U64},
                   Store{40, Type::U64},
                   ReturnObject{48}};
    IRFunction child;
    child.name = "child_method";
    child.result = Type::U64;
    child.receiver = Receiver{"Copy", false, false};
    child.code = {ReceiverLoad{1, Type::U64}, Return{}};
    module.functions = {caller, ctor, method, child};
    return module;
}
} // namespace owningChildFixture

// Exact raw-Module builders and required helpers from tests/compiler/class_arrays_ir.cpp.
namespace classArrayFixture {
void object(IRFunction &function,
            int base,
            const std::string &name,
            bool mutableValue,
            const std::vector<Type> &leaves,
            const std::vector<int> &offsets) {
    function.objectSlots[base] = {name, mutableValue};
    for (std::size_t leaf = 0; leaf < leaves.size(); ++leaf)
        function.slots[base - offsets[leaf]] = leaves[leaf];
}

Module shape(bool packed = false, bool empty = false) {
    Module module;
    const std::vector<Type> child = empty    ? std::vector<Type>{}
                                    : packed ? std::vector<Type>{Type::U8, Type::U8, Type::U8}
                                             : std::vector<Type>{Type::U8, Type::U64};
    const std::vector<int> offsets = empty    ? std::vector<int>{}
                                     : packed ? std::vector<int>{0, 1, 2}
                                              : std::vector<int>{0, 8};
    const int size = empty ? 8 : packed ? 3 : 16;
    module.classLayouts["Child"] = child;
    module.classLayouts["Other"] = child;
    module.classStorage["Child"] = {offsets, offsets, size, packed ? 1 : 8, empty || packed ? 8 : 16};
    module.classStorage["Other"] = module.classStorage["Child"];
    auto twice = child;
    twice.insert(twice.end(), child.begin(), child.end());
    auto doubleOffsets = offsets;
    for (int offset : offsets)
        doubleOffsets.push_back(size + offset);
    module.classLayouts["Carrier"] = twice;
    module.classFields["Carrier"] = {{Type("Child"), 0, static_cast<int>(twice.size()), true, 2}};
    module.classStorage["Carrier"] = {
        doubleOffsets, {0}, empty ? 8 : size * 2, packed ? 1 : 8, empty || packed ? 8 : 32};
    module.classArrayCarriers.insert("Carrier");
    return module;
}

Module local(bool packed = false, bool empty = false) {
    auto module = shape(packed, empty);
    const auto &leaves = module.classLayouts.at("Child");
    const auto &offsets = module.classStorage.at("Child").leafOffsets;
    IRFunction function;
    function.name = "local";
    function.result = Type("Child");
    function.parameters = {Type("Child"), Type("Child")};
    function.frameBytes = 128;
    object(function, 16, "Child", false, leaves, offsets);
    object(function, 32, "Child", false, leaves, offsets);
    object(function,
           64,
           "Carrier",
           true,
           module.classLayouts.at("Carrier"),
           module.classStorage.at("Carrier").leafOffsets);
    object(function, 80, "Child", false, leaves, offsets);
    object(function,
           112,
           "Carrier",
           true,
           module.classLayouts.at("Carrier"),
           module.classStorage.at("Carrier").leafOffsets);
    function.code = {BindObjectParameter{0, 16, "Child"},
                     BindObjectParameter{1, 32, "Child"},
                     BeginObject{64},
                     InitializeClassArray{64, 0, {16, 32}},
                     BeginObject{112},
                     CopyObject{64, 112},
                     Constant{1, Type::I64},
                     ClassArrayBoundsGuard{64, 0},
                     ClassArrayAssign{64, 0, 16},
                     Constant{1, Type::I64},
                     ClassArrayBoundsGuard{64, 0},
                     BeginObject{80},
                     ClassArrayCopy{64, 0, 80},
                     ReturnObject{80}};
    module.functions.push_back(std::move(function));
    return module;
}
} // namespace classArrayFixture

// Exact raw-Module builders and required helpers from tests/compiler/ir_tests.cpp.
namespace receiverArrayFixture {
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
} // namespace receiverArrayFixture

// Additional accepted raw-Module fixtures copied from existing compiler tests.
// These six paths add forms 0-4, 62-71 (15 distinct additions) only when paired
// execution accepts them with Metrics started. CopyObject (24) is already covered.
namespace owningChildFixture {
Module method(bool write = false) {
    auto module = shapes();
    IRFunction function;
    function.name = "owning_method";
    function.result = write ? Type::Bool : Type::I64;
    function.receiver = Receiver{"Parcel", write, false};
    if (write)
        function.code = {Constant{0, Type::I64}, Push{}, Constant{42, Type::U8}, BytesStore{0, 1}, Return{}};
    else
        function.code = {
            BytesLength{0, 1}, Push{}, BytesLength{0, 3}, BinaryValue{Binary::CheckedAdd, Type::I64}, Return{}};
    module.functions = {function};
    return module;
}
} // namespace owningChildFixture

// Exact helpers/builders from tests/compiler/owned_bytes_ir.cpp.
namespace ownedValuesFixture {
void append(IRFunction &function, std::initializer_list<Instruction> code) {
    function.code.insert(function.code.end(), code);
}

template <class Operation> std::size_t position(const IRFunction &function, std::size_t occurrence = 0) {
    for (std::size_t index = 0; index < function.code.size(); ++index)
        if (std::holds_alternative<Operation>(function.code[index])) {
            if (occurrence == 0)
                return index;
            --occurrence;
        }
    throw Error("missing fixture operation");
}

IRFunction frame(const std::string &name = "bytes_entry", Type result = Type::I64) {
    IRFunction function;
    function.name = name;
    function.result = result;
    function.parameters = {Type::ByteRegion};
    function.frameBytes = 192;
    // Region: [1, 8]. Owners: [9, 40], [41, 72], [73, 104], [105, 136].
    // All four owner slots reserve 32 bytes even while inactive.
    function.regionSlots = {8};
    function.byteSlots = {{40, true}, {72, true}, {104, true}, {136, true}};
    function.code = {BindRegionParameter{0, 8}};
    return function;
}

Module moduleWith(IRFunction function) {
    Module module;
    module.functions.push_back(std::move(function));
    return module;
}

Module allocated(std::int64_t length = 17) {
    auto function = frame();
    append(
        function,
        {BeginBytes{40}, Constant{length, Type::I64}, AllocateBytes{8, 40}, BytesLength{40}, EndBytes{40}, Return{}});
    return moduleWith(std::move(function));
}

Module resized(std::int64_t requested = 65, std::int64_t initial = 17) {
    auto function = frame("bytes_resize", Type::Bool);
    append(function,
           {BeginBytes{40},
            Constant{initial, Type::I64},
            AllocateBytes{8, 40},
            Constant{requested, Type::I64},
            BytesResize{40},
            EndBytes{40},
            Return{}});
    return moduleWith(std::move(function));
}

Module valueShapes() {
    Module module;
    module.enumCases["Mode"] = 2;
    module.classLayouts = {{"Record", {Type::U8, Type::U64, Type::U8}},
                           {"Other", {Type::U8, Type::U64, Type::U8}},
                           {"Empty", {}},
                           {"Nested", {Type::U8, Type::U64, Type::U8}},
                           {"ValuesBox", {}},
                           {"ByteBox", {}}};
    module.classFields["Record"] = {{Type::U8, 0, 1, false}, {Type::U64, 1, 1, false}, {Type::U8, 2, 1, false}};
    module.classFields["Other"] = module.classFields["Record"];
    module.classFields["Empty"] = {};
    module.classFields["Nested"] = {{Type("Record"), 0, 3, false}, {Type("Empty"), 3, 0, false}};
    module.classFields["ValuesBox"] = {{Type::ownedValues(Type("Record")), 0, 0, false}};
    module.classFields["ByteBox"] = {{Type::OwnedBytes, 0, 0, false}};
    module.classStorage = {{"Record", {{0, 8, 16}, {0, 8, 16}, 24, 8, 24}},
                           {"Other", {{0, 8, 16}, {0, 8, 16}, 24, 8, 24}},
                           {"Empty", {{}, {}, 8, 8, 8}},
                           {"Nested", {{0, 8, 16}, {0, 24}, 24, 8, 24}},
                           {"ValuesBox", {{}, {0}, 32, 8, 32}},
                           {"ByteBox", {{}, {0}, 32, 8, 32}}};
    return module;
}

void recordSlot(IRFunction &function, int base, bool mutableValue = false, const std::string &name = "Record") {
    function.objectSlots[base] = {name, mutableValue};
    function.slots[base] = Type::U8;
    function.slots[base - 8] = Type::U64;
    function.slots[base - 16] = Type::U8;
}

Module values() {
    auto module = valueShapes();
    auto function = frame("typed_values");
    function.ownedValueTypes = {{40, "Record"}, {72, "Record"}};
    function.frameBytes = 208;
    recordSlot(function, 208, true);
    recordSlot(function, 160);
    recordSlot(function, 184);
    append(function,
           {BeginObject{208},
            Constant{7, Type::U8},
            Store{208, Type::U8},
            Constant{42, Type::U64},
            Store{200, Type::U64},
            Constant{9, Type::U8},
            Store{192, Type::U8},
            BeginObject{160},
            CopyObject{208, 160},
            EndObject{208},
            BeginBytes{40},
            Constant{2, Type::I64},
            AllocateValues{8, 40, 160},
            BeginObject{184},
            Constant{0, Type::I64},
            ValuesLoad{40, -1, 184},
            Constant{1, Type::I64},
            ValuesStore{40, -1, 184},
            Constant{5, Type::I64},
            ValuesResize{40, -1, 160},
            BytesOk{40},
            BytesLength{40},
            EndObject{184},
            EndObject{160},
            EndBytes{40},
            Return{}});
    module.functions.push_back(std::move(function));
    return module;
}

Module valuesParameter() {
    auto module = valueShapes();
    auto function = frame("values_parameter", Type::ownedValues(Type("Record")));
    function.parameters.push_back(Type::ownedValues(Type("Record")));
    function.ownedValueTypes = {{40, "Record"}, {72, "Record"}};
    append(function, {BindBytesParameter{1, 40}, BeginBytes{72}, MoveBytes{40, 72}, EndBytes{40}, ReturnBytes{72}});
    module.functions.push_back(std::move(function));
    return module;
}

// Select the "at" member of the existing readonly-live-owner accepted loop.
// Keep its raw Module mutation order, exact lookup, and insertion offset intact.
Module readonlyAt() {
    const std::string name = "at";
    const Instruction read = BytesLoad{40};
    auto module = allocated();
    auto &function = module.functions[0];
    function.result = name == "ok" ? Type::Bool : name == "at" ? Type::U8 : Type::I64;
    function.byteSlots[40] = false;
    function.code[position<BytesLength>(function)] = read;
    if (name == "at")
        function.code.insert(function.code.begin() + 4, Constant{0, Type::I64});
    return module;
}
} // namespace ownedValuesFixture

// Exact helpers/builders from tests/compiler/console_service_ir.cpp.
namespace consoleServiceFixture {
using F = aurora::ir::Function;
void canonicalTypes(Module &module) {
    const auto name = std::string(service::sampleName);
    module.classLayouts[name] = {Type::Bool, Type::U8, Type::Bool};
    module.classFields[name] = {{Type::Bool, 0, 1, false}, {Type::U8, 1, 1, false}, {Type::Bool, 2, 1, false}};
    module.enumCases[std::string(service::putResultName)] = 2;
    module.enumCases[std::string(service::completionName)] = 2;
}

F entry(const std::string &name) {
    F f;
    f.name = name;
    f.parameters = {Type::ConsoleSession};
    f.result = Type::I64;
    f.frameBytes = 48;
    f.serviceSlots = {16};
    f.code = {BindServiceParameter{0, 16, service::Kind::Console}};
    return f;
}

Module forwarded() {
    Module m;
    canonicalTypes(m);
    auto f = entry("caller");
    f.result = service::putResultType();
    f.code.insert(f.code.end(),
                  {AcquireServiceLoan{1, 16},
                   Constant{65, Type::U8},
                   Push{},
                   ServiceCall{"putter", 1, 0, {0, 0}},
                   ReleaseServiceLoan{1},
                   Return{}});
    auto g = entry("putter");
    g.parameters.push_back(Type::U8);
    g.slots[24] = Type::U8;
    g.result = service::putResultType();
    g.code.insert(g.code.end(),
                  {BindParameter{1, 24, Type::U8},
                   Load{24, Type::U8},
                   ServiceOperation{16, service::Operation::Put, 0},
                   Return{}});
    m.functions = {f, g};
    return m;
}

} // namespace consoleServiceFixture

// Final bounded raw-Module additions. Copies preserve the accepted source
// builders and metadata; only wrappers select a smaller set of accepted paths.
// These source constructions do not establish paired acceptance or coverage.
namespace shortCircuitFixture {
constexpr std::int64_t prefixValue = 1099511627793LL;
void append(IRFunction &f, std::initializer_list<Instruction> operations) {
    f.code.insert(f.code.end(), operations);
}
bool isMethod(const std::string &kind) {
    return kind.starts_with("method");
}

void addProbeSignatures(Module &m) {
    m.classLayouts["ProbeBox"] = {Type::I64, Type::I64};
    IRFunction scalar;
    scalar.name = "sc_probe_scalar";
    scalar.result = Type::Bool;
    scalar.parameters = {Type::Bool};
    scalar.frameBytes = 16;
    scalar.slots = {{8, Type::Bool}};
    scalar.code = {BindParameter{0, 8, Type::Bool}, Load{8, Type::Bool}, Return{}};
    m.functions.push_back(scalar);
    auto method = scalar;
    method.name = "sc_probe_method";
    method.receiver = Receiver{"ProbeBox", true, false};
    m.functions.push_back(method);
    IRFunction aggregate;
    aggregate.name = "sc_probe_aggregate";
    aggregate.result = Type::Bool;
    aggregate.parameters = {Type("ProbeBox"), Type::Bool};
    aggregate.frameBytes = 32;
    aggregate.slots = {{16, Type::I64}, {8, Type::I64}, {24, Type::Bool}};
    aggregate.objectSlots = {{16, {"ProbeBox", false}}};
    aggregate.code = {
        BindObjectParameter{0, 16, "ProbeBox"}, BindParameter{1, 24, Type::Bool}, Load{24, Type::Bool}, Return{}};
    m.functions.push_back(aggregate);
    auto valueMethod = aggregate;
    valueMethod.name = "sc_probe_method_value";
    valueMethod.receiver = Receiver{"ProbeBox", true, false};
    m.functions.push_back(valueMethod);
    auto result = aggregate;
    result.name = "sc_probe_aggregate_result";
    result.result = Type("ProbeBox");
    result.code = {BindObjectParameter{0, 16, "ProbeBox"}, BindParameter{1, 24, Type::Bool}, ReturnObject{16}};
    m.functions.push_back(result);
    result.name = "sc_probe_method_result";
    result.receiver = Receiver{"ProbeBox", true, false};
    m.functions.push_back(result);
    IRFunction span;
    span.name = "sc_probe_span";
    span.result = Type::Bool;
    span.parameters = {Type::ByteSpan, Type::Bool};
    span.frameBytes = 128;
    span.spanSlots = {120};
    span.slots = {{24, Type::Bool}};
    span.code = {
        BindSpanParameter{0, 120}, BindParameter{1, 24, Type::Bool}, Load{24, Type::Bool}, EndSpan{120}, Return{}};
    m.functions.push_back(span);
    m.descriptors = {{17, {1, 0}}, {18, {0, 0}}};
    m.descriptorViews[0] = {17, 18};
}
void probe(IRFunction &f, const std::string &kind, int booleanSlot, int &label) {
    if (kind == "metadata") {
        const int no = label++, done = label++;
        append(f,
               {Load{booleanSlot, Type::Bool},
                BranchFalse{no},
                Constant{17, Type::I64},
                Jump{done},
                Label{no},
                Constant{18, Type::I64},
                Label{done},
                MetadataQuery{Query::Size},
                Push{},
                Constant{0, Type::I64},
                Compare{Comparison::NotEqual, Type::I64}});
        return;
    }
    if (kind == "subspan")
        append(f, {Constant{1, Type::I64}, Push{}, Constant{1, Type::I64}, Subspan{176, 232}});
    append(f, {Load{booleanSlot, Type::Bool}, Push{}});
    if (kind == "scalar")
        f.code.push_back(Call{"sc_probe_scalar"});
    else if (kind == "aggregate")
        f.code.push_back(AggregateCall{"sc_probe_aggregate", {40, 0}, 0});
    else if (kind == "method")
        f.code.push_back(MethodCall{"sc_probe_method", 56});
    else if (kind == "method_value")
        f.code.push_back(MethodCall{"sc_probe_method_value", 56, {40, 0}});
    else if (kind == "aggregate_result" || kind == "method_result") {
        f.code.push_back(BeginObject{112});
        if (kind == "aggregate_result")
            f.code.push_back(AggregateCall{"sc_probe_aggregate_result", {40, 0}, 112});
        else
            f.code.push_back(MethodCall{"sc_probe_method_result", 56, {40, 0}, 112});
        append(f,
               {Load{112, Type::I64},
                Push{},
                Constant{0, Type::I64},
                Compare{Comparison::NotEqual, Type::I64},
                EndObject{112}});
    } else if (kind == "span" || kind == "subspan") {
        f.code.push_back(AggregateCall{"sc_probe_span", {0, 0}, 0, {kind == "span" ? 176 : 232, 0}});
        if (kind == "subspan")
            f.code.push_back(EndSpan{232});
    } else
        throw Error("unknown native probe kind");
}
void logical(IRFunction &f, const std::string &kind, const std::string &shape, int &label) {
    const int no = label++, done = label++;
    append(f, {Load{8, Type::Bool}, BranchFalse{no}});
    if (shape == "or") {
        append(f, {Constant{1, Type::Bool}, Jump{done}, Label{no}});
        probe(f, kind, 16, label);
        f.code.push_back(Label{done});
        return;
    }
    probe(f, kind, 16, label);
    append(f, {Jump{done}, Label{no}, Constant{0, Type::Bool}, Label{done}});
    if (shape == "nested") {
        const int rhs = label++, joined = label++;
        append(f, {BranchFalse{rhs}, Constant{1, Type::Bool}, Jump{joined}, Label{rhs}});
        probe(f, kind, 24, label);
        f.code.push_back(Label{joined});
    }
}
void boolToInteger(IRFunction &f, int &label) {
    const int no = label++, done = label++;
    append(f, {BranchFalse{no}, Constant{1, Type::I64}, Jump{done}, Label{no}, Constant{0, Type::I64}, Label{done}});
}
IRFunction nativeFunction(const std::string &kind, const std::string &shape, int depth) {
    IRFunction f;
    f.name = "sc_" + kind + "_" + shape + "_" + std::to_string(depth);
    f.result = Type::I64;
    f.parameters = {Type::Bool, Type::Bool, Type::Bool};
    f.frameBytes = 240;
    f.slots = {{8, Type::Bool},
               {16, Type::Bool},
               {24, Type::Bool},
               {40, Type::I64},
               {32, Type::I64},
               {56, Type::I64},
               {48, Type::I64},
               {112, Type::I64},
               {104, Type::I64}};
    f.objectSlots = {{40, {"ProbeBox", false}}, {56, {"ProbeBox", true}}, {112, {"ProbeBox", false}}};
    f.code = {BindParameter{0, 8, Type::Bool},
              BindParameter{1, 16, Type::Bool},
              BindParameter{2, 24, Type::Bool},
              BeginObject{40},
              Constant{17, Type::I64},
              Store{40, Type::I64},
              Constant{19, Type::I64},
              Store{32, Type::I64},
              BeginObject{56},
              Constant{23, Type::I64},
              Store{56, Type::I64},
              Constant{29, Type::I64},
              Store{48, Type::I64}};
    if (kind == "span" || kind == "subspan") {
        f.arraySlots = {{64, 3}};
        f.spanSlots = {176, 232};
        f.slots.insert({{64, Type::U8}, {63, Type::U8}, {62, Type::U8}});
        append(f,
               {BeginArray{64},
                Constant{11, Type::U8},
                Store{64, Type::U8},
                Constant{22, Type::U8},
                Store{63, Type::U8},
                Constant{33, Type::U8},
                Store{62, Type::U8},
                BorrowSpan{64, 176}});
    }
    for (int n = 0; n < depth; ++n)
        append(f, {Constant{prefixValue + n, Type::I64}, Push{}});
    int label = 1;
    logical(f, kind, shape, label);
    if (kind == "span" || kind == "subspan")
        append(f, {EndSpan{176}, EndArray{64}});
    boolToInteger(f, label);
    if (isMethod(kind)) {
        // Native probes mutate a real authorized receiver field. Its observed
        // value distinguishes committed RHS effects from skipped calls.
        append(f,
               {Push{},
                Load{48, Type::I64},
                Push{},
                Constant{100, Type::I64},
                BinaryValue{Binary::CheckedMultiply},
                BinaryValue{Binary::CheckedAdd}});
    }
    for (int n = 0; n < depth; ++n)
        f.code.push_back(BinaryValue{Binary::CheckedAdd});
    append(f, {EndObject{56}, EndObject{40}, Return{}});
    return f;
}
// Reduced selection from nativeModule, whose complete probe set is accepted
// by short_circuit_ir.cpp::directTests. Keep every signature and exact metadata.
Module reduced() {
    Module m;
    addProbeSignatures(m);
    m.functions.push_back(nativeFunction("subspan", "nested", 0));
    m.functions.push_back(nativeFunction("metadata", "and", 0));
    return m;
}
} // namespace shortCircuitFixture

namespace fixedSpanFixture {
using F = aurora::ir::Function;
Module fixedFieldModule() {
    Module m;
    m.classLayouts["Fixed"] = {Type::I64, Type::U8, Type::U8, Type::U8, Type::U8};
    m.classFields["Fixed"] = {{Type::I64, 0, 1, false}, {Type::U8, 1, 2, true}, {Type::U8, 3, 2, true}};
    F view;
    view.name = "fixed_view";
    view.receiver = Receiver{"Fixed", false, false};
    view.result = Type::ByteSpan;
    view.receiverSpanField = 1;
    view.frameBytes = 112;
    view.spanSlots = {56, 112};
    view.code = {BorrowReceiverArraySpan{1, 56}, ReborrowSpan{56, 112}, ReturnSpan{112}};
    F caller;
    caller.name = "fixed_caller";
    caller.result = Type::I64;
    caller.parameters = {Type("Fixed")};
    caller.frameBytes = 128;
    caller.objectSlots = {{16, {"Fixed", false}}};
    caller.slots = {{16, Type::I64}, {8, Type::U8}, {7, Type::U8}, {6, Type::U8}, {5, Type::U8}};
    caller.spanSlots = {72, 128};
    caller.code = {BindObjectParameter{0, 16, "Fixed"},
                   MethodCall{"fixed_view", 16, {}, 72},
                   ReborrowSpan{72, 128},
                   SpanLength{128},
                   EndSpan{128},
                   EndSpan{72},
                   EndObject{16},
                   Return{}};
    m.functions = {view, caller};
    return m;
}
} // namespace fixedSpanFixture

namespace literalWindowFixture {
using F = aurora::ir::Function;
Module base(bool size = false) {
    F f;
    f.name = size ? "window_size" : "window_dynamic";
    f.result = Type::I64;
    f.parameters = {Type::I64, Type::I64, Type::I64};
    f.frameBytes = 256;
    f.slots = {{8, Type::U8}, {7, Type::U8}, {6, Type::U8}, {56, Type::I64}, {64, Type::I64}, {72, Type::I64}};
    f.arraySlots = {{8, 3}};
    f.spanSlots = {128, 184};
    f.code = {BindParameter{0, 56, Type::I64},
              BindParameter{1, 64, Type::I64},
              BindParameter{2, 72, Type::I64},
              BeginArray{8},
              Constant{11, Type::U8},
              Store{8, Type::U8},
              Constant{128, Type::U8},
              Store{7, Type::U8},
              Constant{255, Type::U8},
              Store{6, Type::U8},
              BorrowSpan{8, 128},
              Load{56, Type::I64},
              Push{},
              Load{64, Type::I64},
              Subspan{128, 184}};
    if (size)
        f.code.push_back(SpanLength{184});
    else {
        f.code.push_back(Load{72, Type::I64});
        f.code.push_back(SpanLoad{184});
        f.code.push_back(Convert{Type::U8, Type::I64});
    }
    f.code.insert(f.code.end(), {EndSpan{184}, EndSpan{128}, EndArray{8}, Return{}});
    Module m;
    m.functions = {f};
    return m;
}
Module literal() {
    auto m = base(false);
    // Exact length-three iteration of literalTests' accepted loop.
    m.functions[0].code[10] = BorrowLiteralSpan{std::vector<unsigned char>(3u, 255), 128};
    return m;
}
} // namespace literalWindowFixture

namespace borrowedObjectFixture {
using F = aurora::ir::Function;
template <class T> std::size_t at(const F &function, int occurrence = 0) {
    for (std::size_t index = 0; index < function.code.size(); ++index)
        if (std::holds_alternative<T>(function.code[index]) && occurrence-- == 0)
            return index;
    throw Error("fixture operation missing");
}
template <class T> T &op(F &function, int occurrence = 0) {
    return std::get<T>(function.code[at<T>(function, occurrence)]);
}
template <class T> void before(F &function, std::initializer_list<Instruction> code, int occurrence = 0) {
    function.code.insert(function.code.begin() + at<T>(function, occurrence), code);
}
Module shapes() {
    Module module;
    module.classLayouts = {{"Buffer", {Type::I64}}, {"Other", {Type::I64}}, {"Word", {Type::I64}}};
    module.classFields["Buffer"] = {{Type::OwnedBytes, 0, 0, false}, {Type::I64, 0, 1, false}};
    module.classFields["Other"] = module.classFields["Buffer"];
    module.classFields["Word"] = {{Type::I64, 0, 1, false}};
    module.classStorage = {
        {"Buffer", {{32}, {0, 32}, 40, 8, 40}}, {"Other", {{32}, {0, 32}, 40, 8, 40}}, {"Word", {{0}, {0}, 8, 8, 8}}};
    return module;
}
F method(bool mutating = false) {
    F function;
    function.name = mutating ? "write_buffer" : "read_buffer";
    function.result = Type::I64;
    function.receiver = Receiver{"Buffer", mutating, false, true};
    if (mutating)
        function.code = {Constant{41, Type::I64}, ReceiverStore{1, Type::I64}};
    function.code.insert(function.code.end(), {ReceiverLoad{1, Type::I64}, Return{}});
    return function;
}
F borrowed(bool mutableValue = true) {
    F function;
    function.name = "borrow_buffer";
    function.result = Type::I64;
    function.parameters = {Type("Buffer")};
    function.borrowedRootCount = 1;
    function.firstBorrowedMutable = mutableValue;
    function.code = {MethodCall{mutableValue ? "write_buffer" : "read_buffer", 0}, Return{}};
    return function;
}
F entry() {
    F function;
    function.name = "borrow_entry";
    function.result = Type::I64;
    function.parameters = {Type::ByteRegion, Type("Buffer")};
    function.frameBytes = 256;
    function.regionSlots = {8};
    function.objectSlots = {
        {48, {"Buffer", true}}, {88, {"Buffer", true}}, {96, {"Word", false}}, {104, {"Word", false}}};
    function.slots = {{16, Type::I64}, {56, Type::I64}, {96, Type::I64}, {104, Type::I64}};
    function.spanSlots = {160, 216};
    function.byteSlots = {{248, true}};
    function.code = {BindRegionParameter{0, 8}, BindOwnedObjectParameter{1, 48, "Buffer"}};
    return function;
}
Module fixture(bool mutableValue = true) {
    auto module = shapes();
    auto caller = entry();
    caller.code.insert(caller.code.end(),
                       {AcquireObjectLoan{1, 48, mutableValue},
                        BorrowedCall{"borrow_buffer", {{48, 1}}},
                        ReleaseObjectLoan{1},
                        EndObject{48},
                        Return{}});
    module.functions = {caller, borrowed(mutableValue), method(), method(true)};
    return module;
}
Module constLocal(bool mutableLoan = false) {
    auto module = fixture(mutableLoan);
    auto &caller = module.functions[0];
    caller.objectSlots[88].mutableValue = false;
    before<AcquireObjectLoan>(caller, {BeginObject{88}, MoveObject{48, 88}, EndObject{48}});
    op<AcquireObjectLoan>(caller).root = 88;
    op<BorrowedCall>(caller).roots[0].root = 88;
    op<EndObject>(caller, 1).offset = 88;
    return module;
}
Module boundRootReborrow(std::string_view fixture) {
    auto module = shapes();
    auto caller = borrowed(true);
    caller.name = "reborrow_buffer";
    // Reduced from borrowed_objects_ir.cpp::forwarded: the original suite
    // already covers bound-root reborrowing. This slice isolates its derived
    // receiver observation for exact native/source diagnostics and metrics.
    caller.code = {
        AcquireObjectLoan{2, 0, true}, BorrowedCall{"borrow_buffer", {{0, 2}}}, ReleaseObjectLoan{2}, Return{}};
    if (fixture == "borrowed-bound-root-direct-field-denied")
        caller.code = {ReceiverLoad{1, Type::I64}, Return{}};
    // Nominal mismatch is a static call-admission guard, not dynamic coverage.
    if (fixture == "borrowed-bound-root-nominal-mismatch")
        caller.parameters[0] = Type("Other");
    // Keep the call lane valid so the acquisition checks the unbound selector.
    if (fixture == "borrowed-bound-root-unbound-selector")
        op<AcquireObjectLoan>(caller).root = -1;
    module.functions = {caller, borrowed(true), method(true)};
    return module;
}

} // namespace borrowedObjectFixture

Module initializedBorrowHandle() {
    auto module = baseline();
    // ir_tests.cpp's "borrow uninitialized payload" rejection, with the exact
    // baseline Constant/Store prefix restoring initialization of scalar slot 8.
    // No positive BorrowHandle builder exists in tests/compiler; this minimal
    // adaptation still requires independent paired acceptance with Metrics.
    module.functions[0].code = {
        Constant{42, Type::I64}, Store{8, Type::I64}, BorrowHandle{8, Type::Ref}, Constant{42, Type::I64}, Return{}};
    return module;
}

// Exact real-verifier builders from short_circuit_ir.cpp:865-884,983-998,
// not isolated counter-helper checks.
// The four boundaries have 4226, 4227, 65537 and 65538 instructions; the
// revisit has 138. Pointer and nullptr selections construct identical Modules.
namespace resourceFixture {
void append(IRFunction &f, std::initializer_list<Instruction> operations) {
    f.code.insert(f.code.end(), operations);
}

IRFunction resourceFunction(int depth, int labels, bool operandOver = false) {
    IRFunction f;
    f.name = "resource";
    f.result = Type::I64;
    f.code.push_back(Constant{1, Type::I64});
    for (int index = 0; index < depth; ++index)
        f.code.push_back(Push{});
    for (int index = 0; index < labels; ++index)
        f.code.push_back(Label{index});
    if (operandOver) {
        for (int index = 1; index < depth; ++index)
            f.code.push_back(Pop{});
        f.code.push_back(Label{labels});
        f.code.push_back(Pop{});
    } else
        for (int index = 0; index < depth; ++index)
            f.code.push_back(Pop{});
    f.code.push_back(Return{});
    return f;
}

IRFunction revisitFunction() {
    // The target-first short arm retains the uninitialized join first. The
    // initialized longer arm adds a may-initialization fact on the revisit,
    // but neither another snapshot nor another retained copy of its stack.
    auto revisit = resourceFunction(64, 0);
    revisit.frameBytes = 16;
    revisit.slots = {{8, Type::I64}};
    revisit.code.resize(65);
    append(revisit,
           {Constant{1, Type::Bool},
            BranchFalse{1},
            Constant{7, Type::I64},
            Store{8, Type::I64},
            Jump{2},
            Label{1},
            Jump{2},
            Label{2}});
    for (int n = 0; n < 64; ++n)
        revisit.code.push_back(Pop{});
    revisit.code.push_back(Return{});
    return revisit;
}
} // namespace resourceFixture

bool nullMetricsFixture(std::string_view fixture) {
    return fixture == "resource-operand-exact-null-metrics" || fixture == "resource-operand-over-null-metrics" ||
           fixture == "resource-state-exact-null-metrics" || fixture == "resource-state-over-null-metrics";
}

Module construct(std::string_view fixture) {
    if (fixture == "valid-trivial")
        return single(scalarFunction("trivial"));
    if (fixture == "literal-span-missing-spill-before-metrics") {
        auto function = scalarFunction("literal_preflight");
        // Public ingress admits this literal payload and form 51. The verifier's
        // literal preflight rejects the missing span spill before metrics reset.
        // Keep the ordinary empty frame and no spanSlots, rather than forging
        // any owner, descriptor, normalized instruction or capability token.
        function.code.insert(function.code.begin(), BorrowLiteralSpan{{42}, 56});
        return single(std::move(function));
    }
    if (fixture == "uninitialized-scalar")
        return single(uninitializedFunction("uninitialized"));
    if (fixture == "declaration-order-load-first")
        return declarationOrder(true, false);
    if (fixture == "declaration-order-underflow-first")
        return declarationOrder(false, false);
    if (fixture == "unused-declaration-load-first")
        return declarationOrder(true, true);
    if (fixture == "unused-declaration-underflow-first")
        return declarationOrder(false, true);
    if (fixture == "unused-invalid-after-valid-root") {
        auto module = single(scalarFunction("root"));
        module.descriptorViews[1] = {};
        auto unused = uninitializedFunction("unused");
        unused.moduleScope = 1;
        module.functions.push_back(std::move(unused));
        return module;
    }
    if (fixture == "target-before-fallthrough") {
        auto function = uninitializedFunction("branch_order");
        function.code = {
            Constant{1, Type::Bool}, BranchFalse{7}, Pop{}, Return{}, Label{7}, Load{8, Type::I64}, Return{}};
        return single(std::move(function));
    }
    if (fixture == "duplicate-join") {
        auto function = scalarFunction("duplicate_join");
        function.code = {
            Constant{42, Type::I64}, Push{}, Constant{1, Type::Bool}, BranchFalse{7}, Label{7}, Pop{}, Return{}};
        return single(std::move(function));
    }
    if (fixture == "return-43-unbalanced") {
        auto function = scalarFunction("scalar_return");
        leaveOperand(function);
        return single(std::move(function));
    }
    if (fixture == "return-44-valid" || fixture == "return-44-unbalanced")
        return copiedReturn(fixture == "return-44-unbalanced");
    if (fixture == "return-53-valid" || fixture == "return-53-unbalanced")
        return spanReturn(fixture == "return-53-unbalanced");
    if (fixture == "return-76-valid" || fixture == "return-76-unbalanced")
        return bytesReturn(fixture == "return-76-unbalanced");
    if (fixture == "return-80-valid" || fixture == "return-80-unbalanced")
        return owningReturn(fixture == "return-80-unbalanced");
    if (fixture == "byte-operations-valid")
        return byteOperations();
    if (fixture == "enum-baseline-valid")
        return enumBaseline();
    if (fixture == "enum-cross-store" || fixture == "enum-cross-call") {
        auto module = enumBaseline();
        const auto other = Type::enumeration("OtherMode");
        // Both nominal types and instruction contracts are admitted. Only the
        // dynamic current value / saved call argument has the wrong enum type.
        module.functions[0].code[fixture == "enum-cross-store" ? 0 : 2] = EnumConstant{other, 1};
        return module;
    }
    if (fixture == "terminal-value-before-fallthrough" || fixture == "unreachable-after-return") {
        auto module = baseline();
        // Exact terminal-priority constructions from ir_tests.cpp. Normalization
        // must preserve these errors until dynamic verification has started.
        if (fixture == "terminal-value-before-fallthrough")
            module.functions[0].code = {Pop{}};
        else
            module.functions[0].code = {Constant{42, Type::I64}, Return{}, Constant{0, Type::I64}};
        return module;
    }
    if (fixture == "initialized-empty-valid")
        return emptyObjectFixture::initializedEmpty();
    if (fixture == "owning-copied-child-valid")
        return owningChildFixture::copiedChild();
    if (fixture == "class-array-local-valid")
        return classArrayFixture::local();
    if (fixture == "receiver-array-valid")
        return receiverArrayFixture::arrayReceiverBaseline();
    if (fixture == "owned-values-valid")
        return ownedValuesFixture::values();
    if (fixture == "owned-values-parameter-valid")
        return ownedValuesFixture::valuesParameter();
    if (fixture == "readonly-owner-at-valid")
        return ownedValuesFixture::readonlyAt();
    if (fixture == "owning-byte-store-valid")
        return owningChildFixture::method(true);
    if (fixture == "owned-bytes-resize-valid")
        return ownedValuesFixture::resized();
    if (fixture == "console-forwarded-valid")
        return consoleServiceFixture::forwarded();
    if (fixture == "short-circuit-span-metadata-valid")
        return shortCircuitFixture::reduced();
    if (fixture == "fixed-field-span-valid")
        return fixedSpanFixture::fixedFieldModule();
    if (fixture == "literal-window-valid")
        return literalWindowFixture::literal();
    if (fixture == "borrowed-const-local-valid")
        return borrowedObjectFixture::constLocal();
    if (fixture == "borrowed-bound-root-reborrow-valid" || fixture == "borrowed-bound-root-direct-field-denied" ||
        fixture == "borrowed-bound-root-nominal-mismatch" || fixture == "borrowed-bound-root-unbound-selector")
        return borrowedObjectFixture::boundRootReborrow(fixture);
    if (fixture == "initialized-borrow-handle-valid")
        return initializedBorrowHandle();
    if (fixture == "typed-move-to-bytes" || fixture == "typed-move-to-other" || fixture == "typed-return-as-bytes" ||
        fixture == "typed-return-as-other") {
        // Exact mutations from owned_bytes_ir.cpp:2165-2170,2213-2218.
        // Record and Other have identical layouts but distinct nominal names.
        // Keep entry owner 40 unchanged so the dynamic move/return is reached.
        auto module = ownedValuesFixture::valuesParameter();
        if (fixture == "typed-move-to-bytes")
            module.functions[0].ownedValueTypes.erase(72);
        else if (fixture == "typed-move-to-other")
            module.functions[0].ownedValueTypes[72] = "Other";
        else if (fixture == "typed-return-as-bytes")
            module.functions[0].result = Type::OwnedBytes;
        else
            module.functions[0].result = Type::ownedValues(Type("Other"));
        return module;
    }
    if (fixture == "range-missing-before-inactive" || fixture == "range-inactive-before-missing") {
        // Exact mixed-range construction/mutation from short_circuit_ir.cpp:854-863;
        // baseline supplies the same raw scalar frame before replacing its body.
        auto module = baseline();
        module.functions[0].code = {
            BeginObject{16}, Constant{0, Type::I64}, BoundsGuard{16, 2, Type::I64}, EndObject{16}, Return{}};
        module.classLayouts["WordBox"] = {Type::I64};
        module.functions[0].frameBytes = 16;
        module.functions[0].slots = {{16, Type::I64}, {8, Type::I64}};
        module.functions[0].objectSlots = {{16, {"WordBox", true}}, {8, {"WordBox", true}}};
        if (fixture == "range-inactive-before-missing")
            module.functions[0].code.insert(module.functions[0].code.begin() + 1,
                                            {Constant{1, Type::I64}, Store{16, Type::I64}});
        return module;
    }
    if (fixture == "linear-depth-before-omitted" || fixture == "omitted-before-linear-depth") {
        // Exact competing-error bodies/mutation from ir_tests.cpp:6076-6098.
        auto module = baseline();
        module.functions[0].code = {Constant{42, Type::I64},
                                    Push{},
                                    Jump{1},
                                    Label{2},
                                    Return{},
                                    Constant{0, Type::I64},
                                    Label{1},
                                    Pop{},
                                    Jump{2}};
        if (fixture == "omitted-before-linear-depth")
            module.functions[0].code.insert(module.functions[0].code.begin() + 3,
                                            {Label{9}, Jump{9}, Constant{0, Type::I64}});
        return module;
    }
    if (fixture == "typed-entry-other-before-body") {
        // owned_bytes_ir.cpp:2185-2190: unlike the dynamic nominal cases above,
        // entry admission rejects owner 40 before the later MoveBytes mismatch.
        auto module = ownedValuesFixture::valuesParameter();
        module.functions[0].ownedValueTypes[40] = "Other";
        return module;
    }
    if (fixture == "unused-static-storage-before-dynamic") {
        // Exact Load variant and mutation order from ir_tests.cpp:4091,4106-4119.
        // Module-wide static admission wins over the first body's dynamic Pop.
        auto module = baseline();
        module.descriptorViews[1] = {};
        auto later = module.functions[0];
        later.name = "unused_storage";
        later.moduleScope = 1;
        later.frameBytes = 80;
        later.spanSlots = {72};
        later.code = {Load{24, Type::I64}, Return{}};
        module.functions[0].code = {Pop{}, Return{}};
        module.functions.push_back(later);
        return module;
    }
    if (fixture == "resource-operand-exact" || fixture == "resource-operand-exact-null-metrics")
        return single(resourceFixture::resourceFunction(64, 4096));
    if (fixture == "resource-operand-over" || fixture == "resource-operand-over-null-metrics")
        return single(resourceFixture::resourceFunction(64, 4096, true));
    if (fixture == "resource-state-exact" || fixture == "resource-state-exact-null-metrics")
        return single(resourceFixture::resourceFunction(0, 65535));
    if (fixture == "resource-state-over" || fixture == "resource-state-over-null-metrics")
        return single(resourceFixture::resourceFunction(0, 65536));
    if (fixture == "resource-revisit-valid")
        return single(resourceFixture::revisitFunction());
    throw std::runtime_error("unknown comparison fixture");
}

verification::Metrics sentinelMetrics() {
    // Distinct, representable values outside this bounded suite's count range.
    // All five remain visible even if import/admission fails before metrics reset.
    verification::Metrics metrics;
    metrics.snapshots = 1000000001;
    metrics.peakOperandDepth = 1000000002;
    metrics.peakRetainedOperandFacts = 1000000003;
    metrics.peakRetainedValueFacts = 1000000004;
    metrics.peakRetainedInitializationPayloadBytes = 1000000005;
    return metrics;
}

bool metricsStarted(const verification::Metrics &metrics) {
    const auto before = sentinelMetrics();
    return metrics.snapshots != before.snapshots || metrics.peakOperandDepth != before.peakOperandDepth ||
           metrics.peakRetainedOperandFacts != before.peakRetainedOperandFacts ||
           metrics.peakRetainedValueFacts != before.peakRetainedValueFacts ||
           metrics.peakRetainedInitializationPayloadBytes != before.peakRetainedInitializationPayloadBytes;
}

void quoted(std::string_view value) {
    constexpr char hex[] = "0123456789abcdef";
    std::cout << '"';
    for (const unsigned char byte : value) {
        if (byte == '"' || byte == '\\')
            std::cout << '\\' << static_cast<char>(byte);
        else if (byte < 32 || byte >= 127)
            std::cout << "\\u00" << hex[byte >> 4] << hex[byte & 15];
        else
            std::cout << static_cast<char>(byte);
    }
    std::cout << '"';
}

void record(std::string_view fixture, const verification::Metrics *observedMetrics, const Error *error) {
    std::cout << "{\"protocol\":";
    quoted(protocol);
    std::cout << ",\"fixture\":";
    quoted(fixture);
    std::cout << ",\"outcome\":\"" << (error ? "rejected" : "accepted") << "\",\"diagnostic\":";
    if (error) {
        std::cout << "{\"code\":" << static_cast<int>(error->diagnostic.code) << ",\"name\":";
        quoted(diagnosticCode(error->diagnostic.code));
        std::cout << ",\"text\":";
        quoted(error->diagnostic.message);
        std::cout << '}';
    } else {
        std::cout << "null";
    }
    if (!observedMetrics) {
        // Protocol v2 distinguishes unobserved nullptr calls from untouched
        // pointer sentinels. It must not describe unobserved metrics as false.
        std::cout << ",\"metrics_started\":null,\"metrics\":null}\n";
        return;
    }
    const auto &metrics = *observedMetrics;
    std::cout << ",\"metrics_started\":" << (metricsStarted(metrics) ? "true" : "false")
              << ",\"metrics\":{\"snapshots\":" << metrics.snapshots
              << ",\"peakOperandDepth\":" << metrics.peakOperandDepth
              << ",\"peakRetainedOperandFacts\":" << metrics.peakRetainedOperandFacts
              << ",\"peakRetainedValueFacts\":" << metrics.peakRetainedValueFacts
              << ",\"peakRetainedInitializationPayloadBytes\":" << metrics.peakRetainedInitializationPayloadBytes
              << "}}\n";
}

void observe(std::string_view fixture) {
    // Construction bugs are infrastructure failures, never compiler rejections.
    auto module = construct(fixture);
    auto metrics = sentinelMetrics();
    auto *observedMetrics = nullMetricsFixture(fixture) ? nullptr : &metrics;
    try {
        auto ingress = InstructionIngress::import(std::move(module));
        const auto checked = validate(std::move(ingress), observedMetrics);
        (void)checked;
        record(fixture, observedMetrics, nullptr);
    } catch (const Error &error) {
        record(fixture, observedMetrics, &error);
    }
}
} // namespace

int main() {
    try {
        std::vector<std::string> requested;
        std::set<std::string> seen;
        const std::string prefix = std::string(protocol) + '\t';
        std::string line;
        while (std::getline(std::cin, line)) {
            if (!line.starts_with(prefix))
                throw std::runtime_error("expected versioned comparison fixture input");
            const auto fixture = line.substr(prefix.size());
            bool known = false;
            for (const auto candidate : fixtures)
                known |= candidate == fixture;
            if (!known || !seen.insert(fixture).second)
                throw std::runtime_error("unknown or duplicate comparison fixture input");
            requested.push_back(fixture);
        }
        if (std::cin.bad() || requested.empty())
            throw std::runtime_error("missing or unreadable comparison input");
        for (const auto &fixture : requested)
            observe(fixture);
        if (!std::cout)
            throw std::runtime_error("comparison output write failed");
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "comparison fixture infrastructure failure: " << error.what() << '\n';
        return 2;
    }
}
