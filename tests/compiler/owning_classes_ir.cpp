// Independent logical-shape, move-only and resource ABI fixtures. All byte
// offsets below are literal expectations, not production layout-helper results.
#include "ir_verify.hpp"
#include "x86.hpp"
#include <functional>
#include <iostream>
#include <string>

using namespace aurora;
using namespace aurora::ir;
using IRFunction = aurora::ir::Function;

namespace {
int accepted = 0, rejected = 0;
void require(bool value, const std::string &message) {
    if (!value)
        throw Error(message);
}
void append(IRFunction &function, std::initializer_list<Instruction> code) {
    function.code.insert(function.code.end(), code);
}
template <class T> std::size_t at(const IRFunction &function, int occurrence = 0) {
    for (std::size_t index = 0; index < function.code.size(); ++index)
        if (std::holds_alternative<T>(function.code[index]) && occurrence-- == 0)
            return index;
    throw Error("fixture operation missing");
}
template <class T> T &op(Module &module, int occurrence = 0) {
    auto &function = module.functions[0];
    return std::get<T>(function.code[at<T>(function, occurrence)]);
}
template <class T> void before(IRFunction &function, std::initializer_list<Instruction> code, int occurrence = 0) {
    function.code.insert(function.code.begin() + at<T>(function, occurrence), code);
}
template <class T> void remove(IRFunction &function, int occurrence = 0) {
    function.code.erase(function.code.begin() + at<T>(function, occurrence));
}

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
Module moving(bool result = false) {
    auto module = shapes();
    auto function = ordinary("owning_entry", result ? Type("Parcel") : Type::I64);
    append(function, {BeginObject{184}, MoveObject{96, 184}, EndObject{96}});
    if (result)
        append(function, {ReturnOwnedObject{184}});
    else
        append(function,
               {BytesLength{184, 1},
                Push{},
                BytesLength{184, 3},
                BinaryValue{Binary::CheckedAdd, Type::I64},
                EndObject{184},
                Return{}});
    module.functions = {function};
    return module;
}
IRFunction constructor() {
    IRFunction function;
    function.name = "owning_constructor";
    function.result = Type::I64;
    function.receiver = Receiver{"Parcel", true, true};
    function.parameters = {Type::ByteRegion, Type::OwnedBytes, Type::U8, Type::OwnedBytes, Type::U64, Type::U8};
    function.frameBytes = 96;
    function.regionSlots = {8};
    function.byteSlots = {{40, true}, {80, true}};
    function.slots = {{48, Type::U8}, {88, Type::U64}, {96, Type::U8}};
    function.code = {BindRegionParameter{0, 8},
                     BindBytesParameter{1, 40},
                     BindParameter{2, 48, Type::U8},
                     BindBytesParameter{3, 80},
                     BindParameter{4, 88, Type::U64},
                     BindParameter{5, 96, Type::U8},
                     Load{48, Type::U8},
                     ReceiverStore{0, Type::U8},
                     InitializeBytesField{0, 1, 40},
                     Load{88, Type::U64},
                     ReceiverStore{2, Type::U64},
                     InitializeBytesField{0, 3, 80},
                     Load{96, Type::U8},
                     ReceiverStore{4, Type::U8},
                     EndBytes{80},
                     EndBytes{40},
                     Constant{0, Type::I64},
                     Return{}};
    return function;
}
Module constructed(int savedDepth = 0) {
    auto module = shapes();
    auto function = ordinary();
    function.parameters = {Type::ByteRegion};
    function.code = {BindRegionParameter{0, 8},
                     BeginBytes{304},
                     Constant{3, Type::I64},
                     AllocateBytes{8, 304},
                     BeginBytes{336},
                     Constant{5, Type::I64},
                     AllocateBytes{8, 336},
                     Constant{197, Type::U8},
                     Push{},
                     Constant{123456789, Type::U64},
                     Push{},
                     Constant{223, Type::U8},
                     Push{},
                     BeginObject{96},
                     ResourceCall{"owning_constructor", 8, {0, 304, 0, 336, 0, 0}, 0, 96},
                     EndBytes{336},
                     EndBytes{304},
                     BytesLength{96, 1},
                     Push{},
                     BytesLength{96, 3},
                     BinaryValue{Binary::CheckedAdd, Type::I64},
                     EndObject{96},
                     Return{}};
    for (int index = 0; index < savedDepth; ++index) {
        before<BeginBytes>(function, {Constant{savedDepth == 1 ? 34 : 17, Type::I64}, Push{}});
        before<Return>(function, {BinaryValue{Binary::CheckedAdd, Type::I64}});
    }
    module.functions = {function, constructor()};
    return module;
}
Module called(bool result = true) {
    auto module = shapes();
    auto caller = ordinary("owning_entry", result ? Type("Parcel") : Type::I64);
    // Incoming Parcel is passed at position 1; local bytes at position 3; a
    // second independently bound Parcel is passed at position 5.
    caller.parameters.push_back(Type("Parcel"));
    append(caller,
           {BindOwnedObjectParameter{2, 184, "Parcel"},
            BeginBytes{304},
            Constant{7, Type::I64},
            AllocateBytes{8, 304},
            Constant{201, Type::U8},
            Push{},
            Constant{0x123456789LL, Type::U64},
            Push{}});
    if (result)
        append(caller, {BeginObject{272}});
    append(caller,
           {ResourceCall{"owning_six", 8, {0, 96, 0, 304, 0, 184}, result ? 272 : 0},
            EndObject{184},
            EndBytes{304},
            EndObject{96}});
    if (result)
        append(caller, {ReturnOwnedObject{272}});
    else
        append(caller, {Return{}});
    auto callee = ordinary("owning_six", result ? Type("Parcel") : Type::I64);
    callee.parameters = {Type::ByteRegion, Type("Parcel"), Type::U8, Type::OwnedBytes, Type::U64, Type("Parcel")};
    callee.slots[344] = Type::U8;
    callee.slots[352] = Type::U64;
    append(callee,
           {BindParameter{2, 344, Type::U8},
            BindBytesParameter{3, 304},
            BindParameter{4, 352, Type::U64},
            BindOwnedObjectParameter{5, 184, "Parcel"},
            BytesLength{304},
            EndBytes{304},
            EndObject{184}});
    if (result)
        append(callee, {ReturnOwnedObject{96}});
    else
        append(callee, {EndObject{96}, Return{}});
    module.functions = {caller, callee};
    return module;
}
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
Module descriptorOnly(bool pair = false) {
    auto module = shapes();
    const std::string name = pair ? "Pair" : "Only";
    auto function = ordinary("owning_only", Type(name));
    function.slots.clear();
    function.objectSlots = {{96, {name, true}}, {184, {name, false}}};
    function.parameters[1] = Type(name);
    function.code[1] = BindOwnedObjectParameter{1, 96, name};
    // A const destination may be initialized and read/dropped, but never moved.
    append(function,
           {BeginObject{184}, MoveObject{96, 184}, EndObject{96}, BytesLength{184, 0}, EndObject{184}, Return{}});
    function.result = Type::I64;
    module.functions = {function};
    return module;
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
void accept(const std::string &, Module);
void reject(const std::string &, Module, const std::function<void(Module &)> &);
void childTests() {
    accept("copyable constructor snapshot and borrowed method result", copiedChild());
    auto nested = copiedChild();
    before<EndObject>(nested.functions[0], {MethodCall{"child_method", 96, {}, 0, 1}});
    accept("direct copied-child receiver through owning root", nested);
    reject("nested child receiver cannot borrow consumed root", nested, [](Module &m) {
        before<MethodCall>(m.functions[0], {BeginObject{184}, MoveObject{96, 184}}, 1);
    });
    reject("child projection cannot read consumed root", copiedChild(), [](Module &m) {
        before<MethodCall>(m.functions[0], {BeginObject{184}, MoveObject{96, 184}, ObjectFieldCopy{96, 1, 384}});
    });
    reject("constructor copied snapshot cannot alias receiver", copiedChild(), [](Module &m) {
        op<ResourceCall>(m).ownerArguments[2] = 96;
    });
    reject("constructor copied snapshot must be readonly", copiedChild(), [](Module &m) {
        m.functions[0].objectSlots[368].mutableValue = true;
    });
    reject("constructor copied snapshot must be complete", copiedChild(), [](Module &m) {
        remove<Store>(m.functions[0], 1);
    });
    reject("constructor copied snapshot cannot be consumed", copiedChild(), [](Module &m) {
        before<ResourceCall>(m.functions[0], {EndObject{368}});
    });
    reject("owning constructor cannot take owning class", copiedChild(), [](Module &m) {
        m.functions[1].parameters[2] = Type("Only");
    });
    reject("ordinary resource cannot take copied class", copiedChild(), [](Module &m) {
        m.functions[1].receiver.reset();
    });
}

void accept(const std::string &name, Module module) {
    require(!X86Emitter{}.emit(validate(std::move(module))).empty(), name + ": empty assembly");
    ++accepted;
    std::cout << "PASS owning IR " << name << '\n';
}
void reject(const std::string &name, Module module, const std::function<void(Module &)> &change) {
    change(module);
    try {
        (void)validate(std::move(module));
    } catch (const Error &error) {
        require(std::string(error.what()).find("invalid typed IR") != std::string::npos ||
                    std::string(error.what()).starts_with("IR:"),
                name + ": wrong diagnostic: " + error.what());
        ++rejected;
        std::cout << "PASS owning IR " << name << '\n';
        return;
    }
    throw Error(name + ": malformed IR accepted");
}

void layoutTests() {
    accept("literal two-descriptor layout", moving());
    accept("descriptor-only class is not empty", descriptorOnly());
    accept("two descriptor-only fields are distinct", descriptorOnly(true));
    auto inferred = moving();
    inferred.classStorage.clear();
    const auto verified = validate(std::move(inferred));
    require(verified.get().classStorage == shapes().classStorage, "inferred layout differs from literal oracle");
    ++accepted;
    for (int field : {1, 3}) {
        reject("descriptor overlaps scalar payload", moving(), [=](Module &m) {
            m.classStorage["Parcel"].fieldOffsets[field] = 0;
        });
        reject("descriptor is not scalar leaf", moving(), [=](Module &m) {
            m.classFields["Parcel"][field].length = 1;
        });
        reject("descriptor cannot be an array", moving(), [=](Module &m) {
            m.classFields["Parcel"][field].array = true;
        });
    }
    for (int offset : {88, 80, 72, 64, 48, 40, 32, 24})
        reject("descriptor words unavailable to scalar slots", moving(), [=](Module &m) {
            m.functions[0].slots[offset] = Type::U64;
        });
    reject("descriptor unavailable as standalone owner", moving(), [](Module &m) {
        m.functions[0].byteSlots[88] = true;
    });
    reject("descriptor unavailable as authority", moving(), [](Module &m) {
        m.functions[0].regionSlots.insert(88);
    });
    reject("descriptor unavailable as span", moving(), [](Module &m) {
        m.functions[0].spanSlots.insert(88);
    });
    reject("descriptor unavailable as nested object", moving(), [](Module &m) {
        m.functions[0].objectSlots[88] = {"Only", true};
    });
    reject("zero-leaf owning child remains prohibited", moving(), [](Module &m) {
        m.classFields["Parcel"][1] = {Type("Only"), 1, 0, false};
        m.classStorage.clear();
    });
    reject("descriptor-only storage cannot collapse", descriptorOnly(), [](Module &m) {
        m.classStorage["Only"] = {{}, {0}, 8, 8, 8};
    });
    reject("descriptor alignment cannot weaken", moving(), [](Module &m) {
        m.classStorage["Parcel"].alignment = 1;
    });
    reject("owner shape cannot be hidden in scalar leaves", moving(), [](Module &m) {
        m.classLayouts["Parcel"][0] = Type::OwnedBytes;
    });
}
void ownershipTests() {
    accept("owning return transfers exactly one root", moving(true));
    accept("six mixed resource inputs and owning result", called());
    accept("six mixed resource inputs and scalar result", called(false));
    accept("owning receiver readonly borrowed access", method());
    accept("owning receiver mutable borrowed access", method(true));
    auto copy = [](Module &m) {
        auto &f = m.functions[0];
        f.code[at<MoveObject>(f)] = CopyObject{96, 184};
    };
    reject("copy object cannot clone resource", moving(), copy);
    reject("copied bind cannot clone resource", moving(), [](Module &m) {
        m.functions[0].code[1] = BindObjectParameter{1, 96, "Parcel"};
    });
    reject("copied return cannot clone resource", moving(true), [](Module &m) {
        auto &f = m.functions[0];
        f.code.back() = ReturnObject{184};
    });
    reject("aggregate call cannot bypass ownership", called(), [](Module &m) {
        auto &f = m.functions[0];
        f.code[at<ResourceCall>(f)] = AggregateCall{"owning_six", {0, 96, 0, 304, 0, 184}, 272};
    });
    reject("ordinary call cannot bypass ownership", called(), [](Module &m) {
        auto &f = m.functions[0];
        f.code[at<ResourceCall>(f)] = Call{"owning_six"};
    });
    reject("move source aliases destination", moving(), [](Module &m) {
        op<MoveObject>(m).resultOffset = 96;
    });
    reject("move const root", moving(), [](Module &m) {
        m.functions[0].objectSlots[96].mutableValue = false;
    });
    reject("move already-initialized distinct root", called(), [](Module &m) {
        before<ResourceCall>(m.functions[0], {MoveObject{96, 184}});
    });
    reject("move from initialized const local root", moving(), [](Module &m) {
        m.functions[0].objectSlots[184].mutableValue = false;
        before<EndObject>(m.functions[0], {BeginObject{272}, MoveObject{184, 272}});
    });
    reject("mutate descriptor through const local root", moving(), [](Module &m) {
        m.functions[0].objectSlots[184].mutableValue = false;
        before<EndObject>(m.functions[0], {Constant{0, Type::I64}, Push{}, Constant{7, Type::U8}, BytesStore{184, 1}});
    });
    reject("descriptor-only pristine object cannot become complete from zero leaves", descriptorOnly(), [](Module &m) {
        remove<MoveObject>(m.functions[0]);
    });
    reject("move twice", moving(), [](Module &m) {
        before<EndObject>(m.functions[0], {BeginObject{272}, MoveObject{96, 272}});
    });
    reject("move into live root", moving(), [](Module &m) {
        before<EndObject>(m.functions[0], {MoveObject{184, 184}});
    });
    reject("move into unbegun root", moving(), [](Module &m) {
        remove<BeginObject>(m.functions[0]);
    });
    reject("return consumed root", moving(true), [](Module &m) {
        op<ReturnOwnedObject>(m).offset = 96;
    });
    reject("return const root", moving(true), [](Module &m) {
        m.functions[0].objectSlots[184].mutableValue = false;
    });
    reject("return leaks consumed binding", moving(true), [](Module &m) {
        remove<EndObject>(m.functions[0]);
    });
    reject("scalar return leaks live owner", moving(), [](Module &m) {
        remove<EndObject>(m.functions[0], 1);
    });
    reject("return owning with a second owner leaks", called(), [](Module &m) {
        remove<EndObject>(m.functions[0]);
    });
    reject("end owner twice", moving(), [](Module &m) {
        before<Return>(m.functions[0], {EndObject{184}});
    });
    reject("end unbegun root", moving(), [](Module &m) {
        before<BeginObject>(m.functions[0], {EndObject{184}});
    });
    reject("restart owning parameter lifetime", moving(), [](Module &m) {
        before<Return>(m.functions[0], {BeginObject{96}, EndObject{96}});
    });
    reject("scalar load from moved root", moving(), [](Module &m) {
        before<EndObject>(m.functions[0], {Load{96, Type::U8}});
    });
    reject("scalar store into moved root", moving(), [](Module &m) {
        before<EndObject>(m.functions[0], {Constant{7, Type::U8}, Store{96, Type::U8}});
    });
    reject("byte read from moved root", moving(), [](Module &m) {
        before<EndObject>(m.functions[0], {BytesLength{96, 1}});
    });
    reject("unclosed pristine root", moving(), [](Module &m) {
        before<Return>(m.functions[0], {BeginObject{272}});
    });
    reject("whole-result wrong nominal class", moving(true), [](Module &m) {
        m.functions[0].result = Type("Only");
    });
    reject("resource result aliases owning argument", called(), [](Module &m) {
        op<ResourceCall>(m).resultOffset = 96;
    });
    reject("duplicate owning positional arguments", called(), [](Module &m) {
        op<ResourceCall>(m).ownerArguments[5] = 96;
    });
    reject("inactive authority cannot replace owner provenance", called(), [](Module &m) {
        op<ResourceCall>(m).regionOffset = 416;
    });
    reject("scalar argument cannot name owner", called(), [](Module &m) {
        op<ResourceCall>(m).ownerArguments[2] = 96;
    });
    reject("ordinary resource call cannot carry receiver", called(), [](Module &m) {
        op<ResourceCall>(m).receiverOffset = 96;
    });
    reject("resource call exact positional count", called(), [](Module &m) {
        op<ResourceCall>(m).ownerArguments.pop_back();
    });
    reject("wrong owning parameter nominal identity", moving(), [](Module &m) {
        std::get<BindOwnedObjectParameter>(m.functions[0].code[1]).className = "Only";
    });
    reject("owning class requires first region", moving(), [](Module &m) {
        m.functions[0].parameters[0] = Type::I64;
    });
    reject("owning method result unsupported", method(), [](Module &m) {
        m.functions[0].result = Type("Parcel");
    });
    reject("owning method parameter unsupported", method(), [](Module &m) {
        m.functions[0].parameters.push_back(Type("Parcel"));
    });
    reject("const receiver mutation", method(true), [](Module &m) {
        m.functions[0].receiver->mutableValue = false;
    });
    reject("negative field selector", method(), [](Module &m) {
        op<BytesLength>(m).fieldIndex = -2;
    });
    reject("scalar field cannot impersonate descriptor", method(), [](Module &m) {
        op<BytesLength>(m).fieldIndex = 2;
    });
    reject("field selector beyond layout", method(), [](Module &m) {
        op<BytesLength>(m).fieldIndex = 5;
    });
    reject("negative root cannot borrow descriptor", method(), [](Module &m) {
        op<BytesLength>(m).offset = -8;
    });
    reject("borrowed receiver cannot extract owner", method(), [](Module &m) {
        before<Return>(m.functions[0], {ReturnBytes{0}});
    });
}
void constructorTests() {
    accept("six-position owning constructor", constructed());
    accept("constructor calls and cleanup preserve odd operand depth", constructed(1));
    accept("constructor calls and cleanup preserve even operand depth", constructed(2));
    auto module = shapes();
    module.functions = {constructor()};
    accept("partial initialization completed before normal return", module);
    reject("constructor omits descriptor", module, [](Module &m) {
        remove<InitializeBytesField>(m.functions[0]);
    });
    reject("constructor initializes descriptor twice", module, [](Module &m) {
        op<InitializeBytesField>(m, 1).fieldIndex = 1;
    });
    reject("constructor consumes one input twice", module, [](Module &m) {
        op<InitializeBytesField>(m, 1).sourceOffset = 40;
    });
    reject("constructor retains consumed parameter binding", module, [](Module &m) {
        remove<EndBytes>(m.functions[0]);
    });
    reject("constructor cannot initialize scalar as descriptor", module, [](Module &m) {
        op<InitializeBytesField>(m).fieldIndex = 2;
    });
    reject("constructor field write requires receiver zero", module, [](Module &m) {
        op<InitializeBytesField>(m).objectOffset = 16;
    });
    reject("constructor cannot read partial receiver", module, [](Module &m) {
        before<InitializeBytesField>(m.functions[0], {BytesLength{0, 1}});
    });
    reject("nonconstructor cannot install descriptor", module, [](Module &m) {
        m.functions[0].receiver->constructor = false;
    });
    reject("constructor must receive region", module, [](Module &m) {
        m.functions[0].parameters[0] = Type::I64;
    });
    reject("constructor call lacks receiver", constructed(), [](Module &m) {
        op<ResourceCall>(m).receiverOffset = 0;
    });
    reject("constructor receiver must be pristine", constructed(), [](Module &m) {
        before<ResourceCall>(m.functions[0], {Constant{9, Type::U8}, Store{96, Type::U8}});
    });
    reject("constructor result cannot also name storage", constructed(), [](Module &m) {
        op<ResourceCall>(m).resultOffset = 184;
    });
    reject("constructor receiver must match nominal class", constructed(), [](Module &m) {
        auto &f = m.functions[0];
        f.objectSlots[96].className = "Only";
        f.slots.erase(96);
        f.slots.erase(56);
        f.slots.erase(16);
    });
}
void controlTests() {
    auto local = constructed();
    auto &f = local.functions[0];
    // A complete loop iteration destroys the class and both consumed staging
    // bindings before executing the same creation site again.
    f.code.insert(f.code.begin() + 1, Label{1});
    before<Return>(f, {Constant{0, Type::Bool}, BranchFalse{2}, Jump{1}, Label{2}, Constant{8, Type::I64}});
    accept("creation site reuse after full normal cleanup", local);
    reject("conditional owning root consumption", moving(), [](Module &m) {
        auto &f = m.functions[0];
        before<MoveObject>(f, {Constant{1, Type::Bool}, BranchFalse{1}});
        before<EndObject>(f, {Label{1}});
    });
    reject("branch-local lifetime cannot disappear at join", moving(), [](Module &m) {
        before<Return>(m.functions[0], {Constant{1, Type::Bool}, BranchFalse{1}, BeginObject{272}, Label{1}});
    });
    reject("creation site reuse while transferred token survives", constructed(), [](Module &m) {
        auto &f = m.functions[0];
        f.code.insert(f.code.begin() + 1, Label{1});
        before<EndObject>(f, {BeginObject{184}, MoveObject{96, 184}});
        before<Return>(f, {Jump{1}});
    });
    auto pristine = moving();
    before<BeginObject>(pristine.functions[0], {BeginObject{272}, EndObject{272}});
    accept("pristine owner can close without allocation", pristine);
}
} // namespace

int main(int argc, char **argv) {
    try {
        if (argc == 3 && std::string(argv[1]) == "--emit-abi") {
            const std::string mode = argv[2];
            require(mode == "construct" || mode == "six" || mode == "method" || mode == "copied" || mode == "move" ||
                        mode == "construct-odd" || mode == "construct-even",
                    "unknown ABI fixture mode");
            auto module = mode == "construct-odd"    ? constructed(1)
                          : mode == "construct-even" ? constructed(2)
                          : mode == "construct"      ? constructed()
                          : mode == "six"            ? called()
                          : mode == "method"         ? method(true)
                          : mode == "copied"         ? copiedChild()
                                                     : moving(true);
            std::cout << X86Emitter{}.emit(validate(std::move(module)));
            return 0;
        }
        require(argc == 1, "usage: owning_classes_ir [--emit-abi construct|six|method|copied|move]");
        layoutTests();
        ownershipTests();
        constructorTests();
        controlTests();
        childTests();
        std::cout << "PASS owning class IR: " << accepted << " accepted, " << rejected << " rejected\n";
    } catch (const std::exception &error) {
        std::cerr << "FAIL owning class IR: " << error.what() << '\n';
        return 1;
    }
}
