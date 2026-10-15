// Independent logical-shape, move-only and resource ABI fixtures. All byte
// offsets below are literal expectations, not production layout-helper results.
#include "ir_verify.hpp"
#include "hosted_resolver.hpp"
#include "x86.hpp"
#include <functional>
#include <iostream>
#include <limits>
#include <string>
#include <tuple>

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
// The constructor owns both produced temporaries until field transfer. A nested
// resource factory exercises receiver/result preservation across allocation.
Module constructedProducers(int savedDepth = 0) {
    auto module = constructed(savedDepth);
    auto &caller = module.functions[0];
    const auto call = at<ResourceCall>(caller);
    const auto begin = at<BeginBytes>(caller);
    caller.code.erase(caller.code.begin() + begin, caller.code.begin() + call);
    caller.code.insert(caller.code.begin() + begin, BeginObject{96});
    op<ResourceCall>(module).ownerArguments = {0};
    remove<EndBytes>(caller);
    remove<EndBytes>(caller);
    auto &ctor = module.functions[1];
    ctor.parameters = {Type::ByteRegion};
    ctor.slots.clear();
    ctor.code = {BindRegionParameter{0, 8},
                 Constant{197, Type::U8},
                 ReceiverStore{0, Type::U8},
                 BeginBytes{40},
                 Constant{3, Type::I64},
                 AllocateBytes{8, 40},
                 InitializeBytesField{0, 1, 40},
                 Constant{123456789, Type::U64},
                 ReceiverStore{2, Type::U64},
                 BeginBytes{80},
                 Constant{5, Type::I64},
                 Push{},
                 ResourceCall{"owner_factory", 8, {0, 0}, 80},
                 InitializeBytesField{0, 3, 80},
                 Constant{223, Type::U8},
                 ReceiverStore{4, Type::U8},
                 EndBytes{80},
                 EndBytes{40},
                 Constant{0, Type::I64},
                 Return{}};
    IRFunction factory;
    factory.name = "owner_factory";
    factory.result = Type::OwnedBytes;
    factory.parameters = {Type::ByteRegion, Type::I64};
    factory.regionSlots = {8};
    factory.slots = {{16, Type::I64}};
    factory.byteSlots = {{48, true}};
    factory.frameBytes = 48;
    factory.code = {BindRegionParameter{0, 8},
                    BindParameter{1, 16, Type::I64},
                    BeginBytes{48},
                    Load{16, Type::I64},
                    AllocateBytes{8, 48},
                    ReturnBytes{48}};
    module.functions.push_back(factory);
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
// The caller and callee both return a padded copied value through separate
// hidden storage, while the callee closes every incoming owner before copying.
Module copiedResource() {
    auto module = called(false);
    for (auto &function : module.functions) {
        function.result = Type("Copy");
        function.objectSlots[368] = {"Copy", false};
        function.slots[368] = Type::U8;
        function.slots[360] = Type::U64;
        function.code.back() = ReturnObject{368};
    }
    auto &caller = module.functions[0];
    before<ResourceCall>(caller, {BeginObject{368}});
    op<ResourceCall>(module).resultOffset = 368;
    auto &callee = module.functions[1];
    before<BytesLength>(
        callee,
        {BeginObject{368}, Load{344, Type::U8}, Store{368, Type::U8}, Load{352, Type::U64}, Store{360, Type::U64}});
    return module;
}

Module copiedFactory(bool empty = false, bool nested = false) {
    auto module = shapes();
    const std::string name = nested ? "Nested" : empty ? "Empty" : "Copy";
    if (nested) {
        module.classLayouts[name] = {Type::U8, Type::U64};
        module.classFields[name] = {{Type("Copy"), 0, 2, false}, {Type("Empty"), 2, 0, false}};
        module.classStorage[name] = {{0, 8}, {0, 16}, 16, 8, 16};
    }
    IRFunction caller;
    caller.name = "copied_caller";
    caller.result = Type(name);
    caller.parameters = {Type::ByteRegion};
    caller.frameBytes = 80;
    caller.regionSlots = {8};
    caller.objectSlots = {{32, {name, false}}, {48, {name, false}}};
    if (!empty || nested)
        caller.slots = {{32, Type::U8}, {24, Type::U64}, {48, Type::U8}, {40, Type::U64}};
    caller.code = {
        BindRegionParameter{0, 8}, BeginObject{32}, ResourceCall{"copied_factory", 8, {0}, 32}, ReturnObject{32}};
    auto factory = caller;
    factory.name = "copied_factory";
    factory.code = {BindRegionParameter{0, 8}, BeginObject{32}};
    if (nested) {
        factory.objectSlots[64] = {"Copy", false};
        factory.slots[64] = Type::U8;
        factory.slots[56] = Type::U64;
        factory.objectSlots[72] = {"Empty", false};
        append(factory,
               {BeginObject{64},
                Constant{201, Type::U8},
                Store{64, Type::U8},
                Constant{0x123456789LL, Type::U64},
                Store{56, Type::U64},
                BeginObject{72},
                MethodCall{"empty_constructor", 72},
                MethodCall{"nested_constructor", 32, {64, 72}},
                EndObject{72},
                EndObject{64}});
    } else if (!empty) {
        append(
            factory,
            {Constant{201, Type::U8}, Store{32, Type::U8}, Constant{0x123456789LL, Type::U64}, Store{24, Type::U64}});
    }
    if (empty && !nested)
        append(factory, {MethodCall{"empty_constructor", 32}});
    append(factory, {ReturnObject{32}});
    module.functions = {caller, factory};
    if (nested) {
        IRFunction constructor;
        constructor.name = "nested_constructor";
        constructor.result = Type::I64;
        constructor.receiver = Receiver{"Nested", true, true};
        constructor.parameters = {Type("Copy"), Type("Empty")};
        constructor.frameBytes = 32;
        constructor.objectSlots = {{16, {"Copy", false}}, {24, {"Empty", false}}};
        constructor.slots = {{16, Type::U8}, {8, Type::U64}};
        constructor.code = {BindObjectParameter{0, 16, "Copy"},
                            BindObjectParameter{1, 24, "Empty"},
                            InitializeObjectField{0, 0, 16},
                            InitializeObjectField{0, 1, 24},
                            Constant{0, Type::I64},
                            Return{}};
        module.functions.push_back(constructor);
    }
    if (empty || nested) {
        IRFunction constructor;
        constructor.name = "empty_constructor";
        constructor.result = Type::I64;
        constructor.receiver = Receiver{"Empty", true, true};
        constructor.code = {Constant{0, Type::I64}, Return{}};
        module.functions.push_back(constructor);
    }
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
Module resizingField(bool borrowed = false, int fieldIndex = 1, std::int64_t requested = 65) {
    auto module = shapes();
    auto function = borrowed ? IRFunction{} : ordinary("owning_resize", Type::Bool);
    if (borrowed) {
        function.name = "owning_resize_method";
        function.result = Type::Bool;
        function.receiver = Receiver{"Parcel", true, false};
    }
    append(function, {Constant{requested, Type::I64}, BytesResize{borrowed ? 0 : 96, fieldIndex}});
    if (!borrowed)
        append(function, {EndObject{96}});
    append(function, {Return{}});
    module.functions = {function};
    return module;
}

Module resizeBoundary(const std::string &mode) {
    if (mode == "resize-move") {
        auto module = moving(true);
        before<MoveObject>(module.functions[0], {Constant{65, Type::I64}, BytesResize{96, 1}});
        return module;
    }
    const int field = mode == "resize-odd" || mode == "resize-even" ? 3 : 1;
    const int depth = mode == "resize-odd" ? 1 : mode == "resize-even" ? 2 : 0;
    auto module = resizingField(true, field);
    auto &function = module.functions[0];
    function.result = Type::I64;
    function.code.clear();
    for (int index = 0; index < depth; ++index)
        append(function, {Constant{4294967313LL + index, Type::I64}, Push{}});
    append(function,
           {Constant{mode == "resize-failed" ? 2048 : 65, Type::I64},
            BytesResize{0, field},
            BranchFalse{1},
            BytesLength{0, field},
            Jump{2},
            Label{1},
            Constant{-1000, Type::I64},
            Label{2}});
    for (int index = 0; index < depth; ++index)
        append(function, {BinaryValue{Binary::CheckedAdd, Type::I64}});
    append(function, {Return{}});
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
void reject(const std::string &, Module, const std::function<void(Module &)> &, const std::string & = {});
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
void reject(const std::string &name,
            Module module,
            const std::function<void(Module &)> &change,
            const std::string &diagnostic) {
    change(module);
    try {
        (void)validate(std::move(module));
    } catch (const Error &error) {
        require(std::string(error.what()).find("invalid typed IR") != std::string::npos ||
                    std::string(error.what()).starts_with("IR:"),
                name + ": wrong diagnostic: " + error.what());
        require(diagnostic.empty() || std::string(error.what()).find(diagnostic) != std::string::npos,
                name + ": wrong entry diagnostic: " + error.what());
        ++rejected;
        std::cout << "PASS owning IR " << name << '\n';
        return;
    }
    throw Error(name + ": malformed IR accepted");
}

void copiedResourceTests() {
    accept("copied resource result after mixed owner cleanup", copiedResource());
    accept("copied resource result carries no owning provenance", copiedFactory());
    accept("empty resource result retains completion marker", copiedFactory(true));
    reject("empty resource return cannot be bare lifetime", copiedFactory(true), [](Module &m) {
        remove<MethodCall>(m.functions[1]);
    });
    reject("empty copied source cannot launder bare lifetime", copiedFactory(true), [](Module &m) {
        auto &function = m.functions[1];
        function.code[at<MethodCall>(function)] = BeginObject{48};
        before<ReturnObject>(function, {CopyObject{32, 48}});
        std::get<ReturnObject>(function.code[at<ReturnObject>(function)]).offset = 48;
    });
    reject("empty copied completion must dominate join", copiedFactory(true), [](Module &m) {
        auto &function = m.functions[1];
        before<MethodCall>(function, {Constant{1, Type::Bool}, BranchFalse{1}});
        before<ReturnObject>(function, {Label{1}, BeginObject{48}, CopyObject{32, 48}});
        std::get<ReturnObject>(function.code[at<ReturnObject>(function)]).offset = 48;
    });
    accept("nested resource result establishes logical completion", copiedFactory(false, true));
    reject("copied result requires exact root", copiedFactory(), [](Module &m) {
        op<ResourceCall>(m).resultOffset = 24;
    });
    reject("copied result cannot alias owning argument", copiedResource(), [](Module &m) {
        op<ResourceCall>(m).resultOffset = 96;
    });
    reject("copied result cannot overlap region spill", copiedFactory(), [](Module &m) {
        m.functions[0].regionSlots.insert(24);
    });
    reject("copied result cannot overlap owner spill", copiedFactory(), [](Module &m) {
        m.functions[0].byteSlots[48] = true;
    });
    reject("copied result layout metadata must be canonical", copiedFactory(), [](Module &m) {
        m.classStorage["Copy"].leafOffsets[1] = 1;
    });
    reject("copied result requires exact nominal type", copiedFactory(), [](Module &m) {
        m.classLayouts["Other"] = m.classLayouts.at("Copy");
        m.classFields["Other"] = m.classFields.at("Copy");
        m.classStorage["Other"] = m.classStorage.at("Copy");
        m.functions[0].objectSlots[32].className = "Other";
    });
    reject("copied result requires active lifetime", copiedFactory(), [](Module &m) {
        remove<BeginObject>(m.functions[0]);
    });
    reject("copied result cannot reuse ended lifetime", copiedFactory(), [](Module &m) {
        before<ResourceCall>(m.functions[0], {EndObject{32}});
    });
    reject("copied result cannot overwrite partial initialization", copiedFactory(), [](Module &m) {
        before<ResourceCall>(m.functions[0], {Constant{0, Type::U8}, Store{32, Type::U8}});
    });
    for (bool empty : {false, true}) {
        reject("copied result cannot initialize twice", copiedFactory(empty), [](Module &m) {
            before<ReturnObject>(m.functions[0], {ResourceCall{"copied_factory", 8, {0}, 32}});
        });
        auto restart = copiedFactory(empty);
        before<ReturnObject>(restart.functions[0],
                             {EndObject{32}, BeginObject{32}, ResourceCall{"copied_factory", 8, {0}, 32}});
        accept("copied result may restart a closed lifetime", restart);
    }
    reject("conditional copied initialization cannot be overwritten", copiedFactory(), [](Module &m) {
        before<ResourceCall>(
            m.functions[0],
            {Constant{1, Type::Bool}, BranchFalse{1}, ResourceCall{"copied_factory", 8, {0}, 32}, Label{1}});
    });
    reject("resource copied result cannot be scalar operand", copiedFactory(), [](Module &m) {
        before<ReturnObject>(m.functions[0], {Push{}});
    });
    reject("ordinary aggregate call cannot bypass region grant", copiedFactory(), [](Module &m) {
        auto &f = m.functions[0];
        f.code[at<ResourceCall>(f)] = AggregateCall{"copied_factory", {0}, 32};
    });
    reject("copied result cannot be moved as owner", copiedFactory(), [](Module &m) {
        before<ReturnObject>(m.functions[0], {BeginObject{48}, MoveObject{32, 48}});
    });
    reject("copied return cannot retain byte owner", copiedResource(), [](Module &m) {
        remove<EndBytes>(m.functions[1]);
    });
    reject("copied return cannot retain owning root", copiedResource(), [](Module &m) {
        remove<EndObject>(m.functions[1]);
    });
    reject("copied return cannot retain byte view", copiedResource(), [](Module &m) {
        auto &f = m.functions[1];
        f.frameBytes = 480;
        f.spanSlots.insert(480);
        before<EndBytes>(f, {BorrowOwnedSpan{304, -1, 480}});
    });
    reject("resource result cannot carry region authority", copiedFactory(), [](Module &m) {
        m.classFields["Copy"][0].elementType = Type::ByteRegion;
    });
    reject("resource result cannot carry span capability", copiedFactory(), [](Module &m) {
        m.classFields["Copy"][0].elementType = Type::ByteSpan;
    });
    reject("resource copied return must be complete", copiedFactory(), [](Module &m) {
        remove<Store>(m.functions[1], 1);
    });
    reject("nested resource return needs empty child completion", copiedFactory(false, true), [](Module &m) {
        remove<InitializeObjectField>(m.functions[2], 1);
    });
}

void metadataLifetimeTests() {
    static_assert(!std::is_copy_constructible_v<ValidatedModule>);
    static_assert(std::is_move_constructible_v<ValidatedModule>);
    static_assert(!std::is_constructible_v<ValidatedModule, std::vector<FunctionBody>, std::unique_ptr<Metadata>>);
    auto input = moving();
    input.descriptors = {{7, {88, 5}}};
    input.descriptorViews = {{0, {7}}};
    input.enumCases = {{"Phase", 2}};
    auto checked = validate(input);
    const auto independent = validate(input);
    const auto *identity = &checked.metadata();
    const auto parcelId = checked.metadata().findClass("Parcel").value();
    const auto leaves = checked.metadata().leaves(parcelId);
    const auto fields = checked.metadata().fields(parcelId);
    const auto offsets = checked.metadata().storage(parcelId).fieldOffsets;
    const auto visible = checked.metadata().visibleDescriptors(0);
    const auto frame = checked.metadata().frame(0);
    const auto regions = frame.regionSlots();
    const auto owners = frame.byteSlots();
    const auto objects = frame.objectSlots();
    AbiDeclarations declarations;
    declarations.records["Parcel"] = {"Parcel", {"tag", "first", "value", "second", "tail"}};
    declarations.enums["Phase"] = {"Phase", {"ready", "done"}};
    declarations.functions["owning_entry"] = {"owning_entry", {}};
    X86Emitter emitter;
    const auto assembly = emitter.emit(checked);
    const auto facts = emitter.abiFactsJson(checked, declarations);
    auto changed = declarations;
    changed.records.at("Parcel").sourceName = "RenamedParcel";
    changed.records.at("Parcel").members[0] = "renamed_tag";
    changed.enums.at("Phase").members[0] = "renamed_ready";
    changed.functions.at("owning_entry").sourceName = "RenamedEntry";
    changed.functions["not_in_metadata"] = {"ignored", {"ignored_member"}};
    const auto changedFacts = emitter.abiFactsJson(checked, changed);
    require(changedFacts != facts && changedFacts.find("RenamedParcel") != std::string::npos &&
                changedFacts.find("renamed_tag") != std::string::npos &&
                changedFacts.find("renamed_ready") != std::string::npos &&
                changedFacts.find("RenamedEntry") != std::string::npos &&
                changedFacts.find("not_in_metadata") == std::string::npos,
            "repeat ABI request reused stale names or admitted an unrelated function");
    auto malformed = declarations;
    malformed.records.at("Parcel").members.pop_back();
    bool badNamesRejected = false;
    try {
        (void)emitter.abiFactsJson(checked, malformed);
    } catch (const Error &) {
        badNamesRejected = true;
    }
    require(badNamesRejected && emitter.abiFactsJson(checked, declarations) == facts,
            "malformed ABI names were accepted or poisoned the next independent request");
    auto hostileNames = declarations;
    hostileNames.records.at("Parcel").sourceName = std::string("bad") + char(0xff) + char(0) + char(0xc3) + "(";
    const auto hostileFacts = emitter.abiFactsJson(checked, hostileNames);
    require(hostileFacts.find("bad\\u00ff\\u0000\\u00c3(") != std::string::npos &&
                emitter.abiFactsJson(checked, declarations) == facts,
            "ABI name escaping changed bytes or retained a prior optional suffix");
    accepted += 3;
    // Drop every hostile ingress container, then move only the capsule's native
    // owning handle. Previously acquired views still read that same source owner.
    input = Module{};
    auto moved = std::move(checked);
    bool movedFromRejected = false;
    try {
        (void)checked.metadata();
    } catch (const Error &error) {
        movedFromRejected = std::string(error.what()) == "metadata access on moved-from validated module";
    }
    require(movedFromRejected, "moved-from validated module did not reject metadata access");
    ++rejected;
    require(&moved.metadata() == identity, "validated move changed metadata identity");
    require(leaves.size() == 3 && leaves[0] == Type::U8 && leaves[1] == Type::U64 && leaves[2] == Type::U8 &&
                fields.size() == 5 && fields[1].elementType == Type::OwnedBytes && offsets.size() == 5 &&
                offsets[1] == 8 && offsets[3] == 48 && visible.size() == 1 && visible[0] == 7,
            "metadata views did not survive ingress destruction and validated move");
    require(frame.frameBytes() == 416 && regions.size() == 2 && regions.contains(8) && regions.contains(416) &&
                owners.size() == 2 && owners.at(304) && owners.at(336) && objects.size() == 3 &&
                objects.at(96).className == "Parcel" && objects.at(96).mutableValue,
            "resource frame views did not survive ingress destruction and validated move");
    auto copiedField = fields[1];
    copiedField.elementType = Type::U64;
    require(copiedField.elementType == Type::U64 && fields[1].elementType == Type::OwnedBytes,
            "metadata field observation exposed mutable source storage");
    require(emitter.abiFactsJson(moved, declarations) == facts,
            "ABI facts lost same-owner identity after validated move");
    require(X86Emitter{}.emit(moved) == assembly, "validated move changed emitted assembly");
    ++accepted;
    try {
        (void)emitter.abiFactsJson(independent, declarations);
    } catch (const Error &error) {
        require(std::string(error.what()) == "ABI facts require the same emitted module",
                "independent metadata owner produced wrong ABI identity diagnostic");
        ++rejected;
        return;
    }
    throw Error("independent equal metadata owner passed emitted-module identity guard");
}

void layoutTests() {
    accept("literal two-descriptor layout", moving());
    accept("descriptor-only class is not empty", descriptorOnly());
    accept("two descriptor-only fields are distinct", descriptorOnly(true));
    auto inferred = moving();
    inferred.classStorage.clear();
    const auto verified = validate(std::move(inferred));
    const auto expected = shapes().classStorage;
    const auto &metadata = verified.metadata();
    require(metadata.classCount() == expected.size(), "inferred layout class count differs from literal oracle");
    for (const auto &[name, layout] : expected) {
        const auto id = metadata.findClass(name);
        require(id.has_value(), "inferred layout missing literal oracle class");
        const auto storage = metadata.storage(*id);
        require(storage.sizeBytes == layout.sizeBytes && storage.alignment == layout.alignment &&
                    storage.reservedBytes == layout.reservedBytes &&
                    storage.leafOffsets.size() == layout.leafOffsets.size() &&
                    storage.fieldOffsets.size() == layout.fieldOffsets.size(),
                "inferred layout extent differs from literal oracle");
        for (std::size_t index = 0; index < layout.leafOffsets.size(); ++index)
            require(storage.leafOffsets[index] == layout.leafOffsets[index],
                    "inferred leaf offset differs from literal oracle");
        for (std::size_t index = 0; index < layout.fieldOffsets.size(); ++index)
            require(storage.fieldOffsets[index] == layout.fieldOffsets[index],
                    "inferred field offset differs from literal oracle");
    }
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
    reject(
        "inactive authority cannot replace owner provenance",
        called(),
        [](Module &m) {
            op<ResourceCall>(m).regionOffset = 416;
        },
        "region authority is not active");
    reject("scalar argument cannot name owner", called(), [](Module &m) {
        op<ResourceCall>(m).ownerArguments[2] = 96;
    });
    reject("ordinary resource call cannot carry receiver", called(), [](Module &m) {
        op<ResourceCall>(m).receiverOffset = 96;
    });
    reject("resource call exact positional count", called(), [](Module &m) {
        op<ResourceCall>(m).ownerArguments.pop_back();
    });
    reject(
        "wrong owning parameter nominal identity",
        moving(),
        [](Module &m) {
            std::get<BindOwnedObjectParameter>(m.functions[0].code[1]).className = "Only";
        },
        "owning class parameter type mismatch");
    for (const auto &[name, mutate, diagnostic] :
         std::vector<std::tuple<const char *, std::function<void(Module &)>, const char *>>{
             {"exact owning root",
              [](auto &module) {
                  op<BindOwnedObjectParameter>(module).offset = 88;
              },
              "owning class parameter requires exact nominal object slot"},
             {"nominal owning root",
              [](auto &module) {
                  module.functions[0].parameters[1] = Type("Only");
                  op<BindOwnedObjectParameter>(module).className = "Only";
              },
              "owning class parameter requires exact nominal object slot"},
             {"mutable owning root",
              [](auto &module) {
                  module.functions[0].objectSlots[96].mutableValue = false;
              },
              "owning class parameter must be mutable"},
             {"distinct owning roots",
              [](auto &module) {
                  auto &function = module.functions[0];
                  function.parameters.push_back(Type("Parcel"));
                  function.code.insert(function.code.begin() + 2, BindOwnedObjectParameter{2, 96, "Parcel"});
              },
              "owning class parameter bindings overlap"}})
        reject(std::string("source entry ") + name, moving(), mutate, diagnostic);
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
void resizeFieldTests() {
    for (bool borrowed : {false, true}) {
        const std::string root = borrowed ? "borrowed receiver" : "owning parameter";
        for (int field : {1, 3}) {
            for (std::int64_t requested : {std::numeric_limits<std::int64_t>::min(),
                                           std::int64_t{-1},
                                           std::int64_t{0},
                                           std::int64_t{65},
                                           std::numeric_limits<std::int64_t>::max()}) {
                accept(root + " resize retains direct field " + std::to_string(field) + " for request " +
                           std::to_string(requested),
                       resizingField(borrowed, field, requested));
            }
        }
        reject(root + " resize rejects const root", resizingField(borrowed), [=](Module &m) {
            if (borrowed)
                m.functions[0].receiver->mutableValue = false;
            else
                m.functions[0].objectSlots[96].mutableValue = false;
        });
        for (int field : {-2, -1, 0, 2, 4, 5, std::numeric_limits<int>::max()}) {
            reject(root + " resize rejects nonresource selector " + std::to_string(field),
                   resizingField(borrowed),
                   [=](Module &m) {
                       op<BytesResize>(m).fieldIndex = field;
                   });
        }
        reject(root + " resize rejects negative root", resizingField(borrowed), [](Module &m) {
            op<BytesResize>(m).offset = -8;
        });
        for (const auto &type : {Type::Bool, Type::U8, Type::U64}) {
            reject(root + " resize requires current i64 rather than " + typeName(type),
                   resizingField(borrowed),
                   [=](Module &m) {
                       op<Constant>(m).value = 1;
                       op<Constant>(m).type = type;
                   });
        }
        reject(root + " resize rejects nominal enum length", resizingField(borrowed), [](Module &m) {
            m.enumCases["Length"] = 1;
            auto &f = m.functions[0];
            f.code[at<Constant>(f)] = EnumConstant{Type::enumeration("Length"), 0};
        });
        reject(root + " resize requires a current length", resizingField(borrowed), [](Module &m) {
            remove<Constant>(m.functions[0]);
        });
        reject(root + " resize bool cannot be another length", resizingField(borrowed), [=](Module &m) {
            auto &f = m.functions[0];
            f.code.insert(f.code.begin() + at<BytesResize>(f) + 1, BytesResize{borrowed ? 0 : 96, 1});
        });
        reject(root + " resize result is bool", resizingField(borrowed), [](Module &m) {
            m.functions[0].result = Type::I64;
        });
        reject(root + " resize does not consume saved length", resizingField(borrowed), [](Module &m) {
            before<BytesResize>(m.functions[0], {Push{}});
        });
        reject(root + " resize does not create a saved operand", resizingField(borrowed), [](Module &m) {
            before<Return>(m.functions[0], {Pop{}});
        });

        auto stack = resizingField(borrowed);
        auto &f = stack.functions[0];
        f.frameBytes = 416;
        f.slots[344] = Type::I64;
        f.slots[352] = Type::U64;
        f.slots[360] = Type::U8;
        f.slots[368] = Type::Bool;
        f.slots[376] = Type::Bool;
        before<BytesResize>(f,
                            {Push{},
                             Constant{7, Type::U64},
                             Push{},
                             Constant{255, Type::U8},
                             Push{},
                             Constant{1, Type::Bool},
                             Push{},
                             Constant{513, Type::I64}});
        before<Return>(f,
                       {Store{376, Type::Bool},
                        Pop{},
                        Store{368, Type::Bool},
                        Pop{},
                        Store{360, Type::U8},
                        Pop{},
                        Store{352, Type::U64},
                        Pop{},
                        Store{344, Type::I64},
                        Load{376, Type::Bool}});
        accept(root + " resize preserves exact heterogeneous operand stack", stack);
    }
    auto local = constructed();
    before<BytesLength>(local.functions[0],
                        {Constant{65, Type::I64}, BytesResize{96, 1}, Constant{0, Type::I64}, BytesResize{96, 3}});
    accept("constructed local can resize both descriptors and remain queryable", local);
    auto moved = moving();
    before<BytesLength>(moved.functions[0], {Constant{65, Type::I64}, BytesResize{184, 3}});
    accept("moved destination can resize and retain both descriptors", moved);
    auto returned = moving(true);
    before<ReturnOwnedObject>(returned.functions[0], {Constant{65, Type::I64}, BytesResize{184, 1}});
    accept("resized field retains whole-object return authority", returned);
    auto call = called();
    before<ResourceCall>(call.functions[0], {Constant{65, Type::I64}, BytesResize{96, 1}});
    accept("resized field retains resource-call authority and staged arguments", call);
    before<ReturnOwnedObject>(call.functions[0], {Constant{0, Type::I64}, BytesResize{272, 3}});
    accept("resource-call result can resize before whole-object return", call);

    for (int offset : {0, 8, 16, 40, 48, 56, 64, 72, 80, 88, 95, 97, 176, 184, 272, 304, 416}) {
        reject("field resize requires exact live root " + std::to_string(offset), resizingField(), [=](Module &m) {
            op<BytesResize>(m).offset = offset;
        });
    }
    reject("field resize cannot bypass inactive object lifetime", constructed(), [](Module &m) {
        before<BeginObject>(m.functions[0], {Constant{65, Type::I64}, BytesResize{96, 1}});
    });
    reject("field resize cannot initialize pristine root", constructed(), [](Module &m) {
        before<ResourceCall>(m.functions[0], {Constant{65, Type::I64}, BytesResize{96, 1}});
    });
    reject("field resize cannot use consumed root", resizingField(), [](Module &m) {
        before<BytesResize>(m.functions[0], {BeginObject{184}, MoveObject{96, 184}});
    });
    reject("field resize cannot use ended root", resizingField(), [](Module &m) {
        before<BytesResize>(m.functions[0], {EndObject{96}});
    });
    reject("field resize cannot revive consumed root after destination cleanup", resizingField(), [](Module &m) {
        before<BytesResize>(m.functions[0], {BeginObject{184}, MoveObject{96, 184}, EndObject{184}});
    });
    reject("field resize cannot revive restarted pristine local", local, [](Module &m) {
        before<BytesResize>(m.functions[0], {EndObject{96}, BeginObject{96}});
    });
    reject("field resize cannot bypass resource-call consumption", called(false), [](Module &m) {
        before<EndObject>(m.functions[0], {Constant{65, Type::I64}, BytesResize{96, 1}});
    });
    for (std::int64_t requested : {std::int64_t{-1}, std::int64_t{0}, std::int64_t{65}}) {
        reject("field resize retains cleanup obligation for request " + std::to_string(requested),
               resizingField(false, 1, requested),
               [](Module &m) {
                   remove<EndObject>(m.functions[0]);
               });
    }
    auto ctor = shapes();
    ctor.functions = {constructor()};
    reject("constructor cannot resize uninitialized field", ctor, [](Module &m) {
        before<InitializeBytesField>(m.functions[0], {Constant{65, Type::I64}, BytesResize{0, 1}});
    });
    reject("constructor cannot resize initialized field in partial root", ctor, [](Module &m) {
        before<InitializeBytesField>(m.functions[0], {Constant{65, Type::I64}, BytesResize{0, 1}}, 1);
    });
    reject("constructor cannot resize receiver before constructor returns", ctor, [](Module &m) {
        before<EndBytes>(m.functions[0], {Constant{65, Type::I64}, BytesResize{0, 1}});
    });
    reject("copied child cannot impersonate resize descriptor", copiedChild(), [](Module &m) {
        before<MethodCall>(m.functions[0], {Constant{65, Type::I64}, BytesResize{96, 1}});
    });
    reject("copyable object cannot become resize owner", copiedChild(), [](Module &m) {
        before<MethodCall>(m.functions[0], {Constant{65, Type::I64}, BytesResize{368, 0}});
    });
    reject("resize cannot make owning root copyable", resizingField(), [](Module &m) {
        before<EndObject>(m.functions[0], {BeginObject{184}, CopyObject{96, 184}});
    });
    reject("resize cannot permit copied owning return", returned, [](Module &m) {
        auto &f = m.functions[0];
        f.code[at<ReturnOwnedObject>(f)] = ReturnObject{184};
    });
    reject("resize cannot extract field with standalone move", resizingField(), [](Module &m) {
        before<EndObject>(m.functions[0], {BeginBytes{304}, MoveBytes{88, 304}});
    });
    reject("borrowed resize cannot extract receiver as owner", resizingField(true), [](Module &m) {
        before<Return>(m.functions[0], {ReturnBytes{0}});
    });
    reject("borrowed resize cannot extract field via scalar load", resizingField(true), [](Module &m) {
        before<Return>(m.functions[0], {ReceiverLoad{1, Type::U64}});
    });

    auto branch = resizingField();
    auto &f = branch.functions[0];
    f.code.erase(f.code.begin() + at<Constant>(f), f.code.end());
    append(f,
           {BytesOk{96, 1},
            BranchFalse{1},
            Constant{65, Type::I64},
            BytesResize{96, 1},
            Jump{2},
            Label{1},
            Constant{0, Type::Bool},
            Label{2},
            EndObject{96},
            Return{}});
    accept("conditional field resize preserves every ownership token at join", branch);
    auto both = branch;
    before<Constant>(both.functions[0], {Constant{0, Type::I64}, BytesResize{96, 3}}, 1);
    accept("distinct field resize sites preserve whole-root ownership at join", both);
    reject("conditional field resize cannot hide root consumption", branch, [](Module &m) {
        before<Jump>(m.functions[0], {BeginObject{184}, MoveObject{96, 184}, EndObject{184}});
    });
    reject("field resize false does not discharge cleanup", branch, [](Module &m) {
        auto &f = m.functions[0];
        f.code.erase(f.code.begin() + at<EndObject>(f), f.code.end());
        append(f,
               {BranchFalse{3},
                EndObject{96},
                Constant{1, Type::Bool},
                Return{},
                Label{3},
                Constant{0, Type::Bool},
                Return{}});
    });
    auto loop = constructed();
    before<BytesLength>(loop.functions[0],
                        {Label{1},
                         Constant{65, Type::I64},
                         BytesResize{96, 1},
                         BranchFalse{2},
                         Constant{0, Type::I64},
                         BytesResize{96, 3},
                         Jump{1},
                         Label{2}});
    accept("loop resize of two fields preserves original ownership across backedge", loop);
    reject("loop field resize cannot hide root consumption", loop, [](Module &m) {
        before<Jump>(m.functions[0], {BeginObject{184}, MoveObject{96, 184}, EndObject{184}});
    });
}

void constructorTests() {
    for (int depth : {0, 1, 2})
        accept("producing constructor with saved operands " + std::to_string(depth), constructedProducers(depth));
    auto produced = constructedProducers();
    reject("produced field retains temporary binding", produced, [](Module &m) {
        remove<EndBytes>(m.functions[1]);
    });
    reject("produced temporary closes twice", produced, [](Module &m) {
        before<Return>(m.functions[1], {EndBytes{80}});
    });
    reject("produced owner cannot initialize two fields", produced, [](Module &m) {
        auto &f = m.functions[1];
        std::get<InitializeBytesField>(f.code[at<InitializeBytesField>(f, 1)]).sourceOffset = 40;
    });
    reject("factory cannot observe partially initialized receiver", produced, [](Module &m) {
        before<ResourceCall>(m.functions[1], {BytesLength{0, 1}});
    });
    reject("produced field requires mutable temporary", produced, [](Module &m) {
        m.functions[1].byteSlots[40] = false;
    });
    reject("produced field cannot omit transfer", produced, [](Module &m) {
        remove<InitializeBytesField>(m.functions[1]);
    });
    reject("factory owner result cannot reuse consumed first temporary", produced, [](Module &m) {
        auto &f = m.functions[1];
        std::get<ResourceCall>(f.code[at<ResourceCall>(f)]).resultOffset = 40;
    });
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
                        mode == "construct-odd" || mode == "construct-even" || mode == "resize-first" ||
                        mode == "resize-odd" || mode == "resize-even" || mode == "resize-failed" ||
                        mode == "resize-move" || mode == "copied-resource" || mode == "construct-produced" ||
                        mode == "construct-produced-odd" || mode == "construct-produced-even",
                    "unknown ABI fixture mode");
            auto module = mode == "construct-produced"        ? constructedProducers()
                          : mode == "construct-produced-odd"  ? constructedProducers(1)
                          : mode == "construct-produced-even" ? constructedProducers(2)
                          : mode == "copied-resource"         ? copiedResource()
                          : mode.starts_with("resize-")       ? resizeBoundary(mode)
                          : mode == "construct-odd"           ? constructed(1)
                          : mode == "construct-even"          ? constructed(2)
                          : mode == "construct"               ? constructed()
                          : mode == "six"                     ? called()
                          : mode == "method"                  ? method(true)
                          : mode == "copied"                  ? copiedChild()
                                                              : moving(true);
            std::cout << X86Emitter{}.emit(validate(std::move(module)));
            return 0;
        }
        require(argc == 1,
                "usage: owning_classes_ir [--emit-abi construct|construct-odd|construct-even|six|method|copied|move|"
                "resize-first|resize-odd|resize-even|resize-failed|resize-move|copied-resource|"
                "construct-produced|construct-produced-odd|construct-produced-even]");
        metadataLifetimeTests();
        layoutTests();
        ownershipTests();
        resizeFieldTests();
        constructorTests();
        controlTests();
        childTests();
        copiedResourceTests();
        std::cout << "PASS owning class IR: " << accepted << " accepted, " << rejected << " rejected\n";
    } catch (const std::exception &error) {
        std::cerr << "FAIL owning class IR: " << error.what() << '\n';
        return 1;
    }
}
