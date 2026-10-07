// Independent direct-IR resource ownership, provenance, layout and control-flow tests.
// Literal spill extents below are not obtained from the production layout helpers.
#include "ir_verify.hpp"
#include "x86.hpp"
#include <functional>
#include <initializer_list>
#include <iostream>
#include <limits>
#include <string>
#include <utility>
#include <vector>

using namespace aurora;
using namespace aurora::ir;
using IRFunction = aurora::ir::Function;

namespace {
int accepted = 0;
int rejected = 0;

void require(bool condition, const std::string &message) {
    if (!condition)
        throw Error(message);
}

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

template <class Operation> Operation &operation(Module &module, std::size_t occurrence = 0) {
    auto &function = module.functions[0];
    return std::get<Operation>(function.code[position<Operation>(function, occurrence)]);
}

template <class Operation>
void insertBefore(IRFunction &function, std::initializer_list<Instruction> code, std::size_t occurrence = 0) {
    function.code.insert(function.code.begin() + position<Operation>(function, occurrence), code);
}

template <class Operation> void eraseOperation(IRFunction &function, std::size_t occurrence = 0) {
    function.code.erase(function.code.begin() + position<Operation>(function, occurrence));
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

Module moved(bool readonlyDestination = false) {
    auto function = frame();
    function.byteSlots[72] = !readonlyDestination;
    append(function,
           {BeginBytes{40},
            Constant{17, Type::I64},
            AllocateBytes{8, 40},
            BeginBytes{72},
            Constant{42, Type::I64},
            MoveBytes{40, 72},
            EndBytes{40},
            EndBytes{72},
            Return{}});
    return moduleWith(std::move(function));
}

Module owningParameter(bool ownerResult = false) {
    auto function = frame("bytes_parameter", ownerResult ? Type::OwnedBytes : Type::I64);
    function.parameters.push_back(Type::OwnedBytes);
    append(function, {BindBytesParameter{1, 40}});
    if (ownerResult)
        append(function, {ReturnBytes{40}});
    else
        append(function, {BytesLength{40}, EndBytes{40}, Return{}});
    return moduleWith(std::move(function));
}

Module ownerReturn() {
    auto function = frame("bytes_return", Type::OwnedBytes);
    append(function, {BeginBytes{40}, Constant{17, Type::I64}, AllocateBytes{8, 40}, ReturnBytes{40}});
    return moduleWith(std::move(function));
}

Module resourceCall(bool ownerResult = true, int savedDepth = 0, bool readonlyResult = false) {
    auto caller = frame("bytes_caller");
    caller.parameters = {Type::ByteRegion, Type::I64, Type::Bool, Type::U8};
    caller.slots = {{144, Type::I64}, {152, Type::Bool}, {160, Type::U8}};
    caller.byteSlots[104] = !readonlyResult;
    append(caller,
           {BindParameter{1, 144, Type::I64},
            BindParameter{2, 152, Type::Bool},
            BindParameter{3, 160, Type::U8},
            BeginBytes{40},
            Load{144, Type::I64},
            AllocateBytes{8, 40},
            BeginBytes{72},
            Load{144, Type::I64},
            AllocateBytes{8, 72}});
    for (int index = 0; index < savedDepth; ++index)
        append(caller, {Constant{1099511627793LL + index, Type::I64}, Push{}});
    append(caller, {Load{144, Type::I64}, Push{}, Load{152, Type::Bool}, Push{}, Load{160, Type::U8}, Push{}});
    if (ownerResult)
        append(caller, {BeginBytes{104}});
    append(caller,
           {ResourceCall{"bytes_callee", 8, {0, 0, 40, 0, 72, 0}, ownerResult ? 104 : 0}, EndBytes{40}, EndBytes{72}});
    if (ownerResult)
        append(caller, {BytesLength{104}, EndBytes{104}});
    for (int index = 0; index < savedDepth; ++index)
        append(caller, {BinaryValue{Binary::CheckedAdd, Type::I64}});
    append(caller, {Return{}});

    auto callee = frame("bytes_callee", ownerResult ? Type::OwnedBytes : Type::I64);
    callee.parameters = {Type::ByteRegion, Type::I64, Type::OwnedBytes, Type::Bool, Type::OwnedBytes, Type::U8};
    callee.slots = {{144, Type::I64}, {152, Type::Bool}, {160, Type::U8}};
    append(callee,
           {BindParameter{1, 144, Type::I64},
            BindBytesParameter{2, 40},
            BindParameter{3, 152, Type::Bool},
            BindBytesParameter{4, 72},
            BindParameter{5, 160, Type::U8}});
    if (ownerResult)
        append(callee, {EndBytes{72}, ReturnBytes{40}});
    else
        append(callee, {BytesLength{40}, EndBytes{40}, EndBytes{72}, Return{}});
    auto module = moduleWith(std::move(caller));
    module.functions.push_back(std::move(callee));
    return module;
}

Module factoryCall(bool ownerResult = true) {
    auto caller = frame("bytes_factory_caller");
    if (ownerResult)
        append(caller, {BeginBytes{40}});
    append(caller, {ResourceCall{"bytes_factory", 8, {0}, ownerResult ? 40 : 0}});
    if (ownerResult)
        append(caller, {BytesLength{40}, EndBytes{40}});
    append(caller, {Return{}});
    auto module = moduleWith(std::move(caller));
    auto factory = frame("bytes_factory", ownerResult ? Type::OwnedBytes : Type::I64);
    if (ownerResult)
        append(factory, {BeginBytes{40}, Constant{17, Type::I64}, AllocateBytes{8, 40}, ReturnBytes{40}});
    else
        append(factory, {Constant{42, Type::I64}, Return{}});
    module.functions.push_back(std::move(factory));
    return module;
}

void accept(const std::string &name, Module module) {
    const auto validated = validate(std::move(module));
    require(!validated.get().functions.empty(), name + ": empty validated module");
    ++accepted;
    std::cout << "PASS owned byte IR " << name << '\n';
}

void reject(
    const std::string &name,
    Module module,
    const std::function<void(Module &)> &change =
        [](Module &) {
        },
    const std::string &diagnostic = "invalid typed IR") {
    change(module);
    try {
        (void)validate(std::move(module));
    } catch (const Error &error) {
        require(std::string(error.what()).find(diagnostic) != std::string::npos,
                name + ": wrong diagnostic: " + error.what());
        ++rejected;
        std::cout << "PASS owned byte IR " << name << '\n';
        return;
    }
    // Outside the catch: a successful validation must never count as rejection.
    throw Error(name + ": malformed IR accepted");
}

void signatureTests() {
    accept("canonical authority and local owner", allocated());
    accept("mutable owning parameter and scalar return", owningParameter());
    accept("owning parameter transfer return", owningParameter(true));
    accept("local owner transfer without scalar current", ownerReturn());
    accept("six mixed parameters and returned owner", resourceCall());
    accept("six mixed parameters and scalar result", resourceCall(false));

    auto enumFunction = frame("resource_enum", Type::enumeration("Status"));
    enumFunction.parameters.push_back(Type::enumeration("Status"));
    enumFunction.slots[144] = Type::enumeration("Status");
    append(enumFunction,
           {BindParameter{1, 144, Type::enumeration("Status")}, Load{144, Type::enumeration("Status")}, Return{}});
    auto enumModule = moduleWith(std::move(enumFunction));
    enumModule.enumCases["Status"] = 2;
    accept("nominal enum remains an ordinary scalar boundary", enumModule);

    reject("owner signature lacks region", owningParameter(), [](Module &module) {
        module.functions[0].parameters.erase(module.functions[0].parameters.begin());
    });
    reject("owner result lacks region", ownerReturn(), [](Module &module) {
        module.functions[0].parameters.clear();
    });
    reject("region must be first", owningParameter(), [](Module &module) {
        std::swap(module.functions[0].parameters[0], module.functions[0].parameters[1]);
    });
    reject("second region forbidden", owningParameter(), [](Module &module) {
        module.functions[0].parameters[1] = Type::ByteRegion;
    });
    reject("seventh resource parameter forbidden", resourceCall(), [](Module &module) {
        module.functions[1].parameters.push_back(Type::I64);
    });
    reject("region cannot be returned", ownerReturn(), [](Module &module) {
        module.functions[0].result = Type::ByteRegion;
    });
    for (const auto &type :
         {Type::ByteSpan, Type::Own, Type::Ref, Type::MutRef, Type::array(TypeKind::U8, 3), Type("Box")}) {
        reject("resource parameter cannot mix " + typeName(type), owningParameter(), [=](Module &module) {
            module.classLayouts["Box"] = {Type::I64};
            module.functions[0].parameters[1] = type;
        });
        reject("resource result cannot mix " + typeName(type), ownerReturn(), [=](Module &module) {
            module.classLayouts["Box"] = {Type::I64};
            module.functions[0].result = type;
        });
    }
    reject("resource receiver forbidden", allocated(), [](Module &module) {
        module.classLayouts["Box"] = {Type::I64};
        module.functions[0].receiver = Receiver{"Box", true, false};
    });
    for (bool region : {false, true}) {
        reject("decorated resource parameter is not canonical", owningParameter(), [=](Module &module) {
            module.functions[0].parameters[region ? 0 : 1].className = "forged";
        });
        reject("resource array metadata is not canonical", owningParameter(), [=](Module &module) {
            module.functions[0].parameters[region ? 0 : 1].length = 1;
        });
    }
    reject("decorated owner result is not canonical", ownerReturn(), [](Module &module) {
        module.functions[0].result.templateArguments = {TemplateArgument(TypeKind::I64)};
    });
    for (const std::string name : {"__au_runtime_bytes_",
                                   "__au_runtime_bytes_allocate",
                                   "__au_runtime_bytes_at",
                                   "__au_runtime_bytes_set",
                                   "__au_runtime_bytes_resize",
                                   "__au_runtime_bytes_drop",
                                   "__au_runtime_bytes_end",
                                   "__au_runtime_bytes_test_bridge",
                                   "__au_runtime_bytes_test_entry",
                                   "__au_runtime_bytes_test_bounds"})
        reject("reserved runtime helper name " + name, allocated(), [=](Module &module) {
            module.functions[0].name = name;
        });
    auto ordinary = frame("ordinary_scalar");
    ordinary.parameters.clear();
    ordinary.regionSlots.clear();
    ordinary.byteSlots.clear();
    ordinary.code = {Constant{42, Type::I64}, Return{}};
    auto ordinaryModule = moduleWith(std::move(ordinary));
    accept("scalar-only function remains accepted", ordinaryModule);
    reject("reserved helper names also reject scalar-only signatures", ordinaryModule, [](Module &module) {
        module.functions[0].name = "__au_runtime_bytes_fake";
    });
    for (const std::string name :
         {"__au_runtime_bytes_test_bridge", "__au_runtime_bytes_test_entry", "__au_runtime_bytes_test_bounds"})
        reject(
            "reserved test bridge cannot be supplied as scalar function " + name, ordinaryModule, [=](Module &module) {
                module.functions[0].name = name;
            });
}

void layoutTests() {
    auto adjacent = allocated();
    adjacent.functions[0].slots = {{137, Type::U8}, {152, Type::I64}};
    accept("literal 8-byte region and 32-byte owner extents are disjoint", adjacent);
    for (int base : {-8, 0, 7, 9, 200})
        reject("invalid region extent " + std::to_string(base), allocated(), [=](Module &module) {
            module.functions[0].regionSlots.insert(base);
        });
    for (int base : {-32, 0, 24, 39, 200})
        reject("invalid owner extent " + std::to_string(base), allocated(), [=](Module &module) {
            module.functions[0].byteSlots[base] = true;
        });
    reject("region overlaps an owner", allocated(), [](Module &module) {
        module.functions[0].regionSlots.insert(16);
    });
    reject("owners overlap by one aligned word", allocated(), [](Module &module) {
        module.functions[0].byteSlots[64] = true;
    });
    for (int offset : {1, 8, 9, 16, 39, 40, 41, 72, 104, 136})
        reject("u8 scalar overlaps private resource byte " + std::to_string(offset), allocated(), [=](Module &module) {
            module.functions[0].slots[offset] = Type::U8;
        });
    reject("wide scalar overlaps region spill", allocated(), [](Module &module) {
        module.functions[0].slots[8] = Type::I64;
    });
    reject("wide scalar overlaps owner spill", allocated(), [](Module &module) {
        module.functions[0].slots[40] = Type::U64;
    });
    reject("empty object reservation overlaps resource", allocated(), [](Module &module) {
        module.classLayouts["Empty"] = {};
        module.functions[0].objectSlots[24] = {"Empty", false};
    });
    reject("span reservation overlaps region and owner", allocated(), [](Module &module) {
        module.functions[0].spanSlots.insert(16);
    });
    reject("inactive owner reservation still excludes span", allocated(), [](Module &module) {
        module.functions[0].spanSlots.insert(104);
    });
    reject("byte array cannot supply owner descriptor storage", allocated(), [](Module &module) {
        auto &function = module.functions[0];
        function.arraySlots[40] = 2;
        function.slots[40] = Type::U8;
        function.slots[39] = Type::U8;
    });
    for (const auto &type : {Type::ByteRegion, Type::OwnedBytes}) {
        reject("resource cannot be scalar slot payload " + typeName(type), allocated(), [=](Module &module) {
            module.functions[0].slots[144] = type;
        });
        reject("resource cannot be class payload " + typeName(type), allocated(), [=](Module &module) {
            module.classLayouts["Forged"] = {type};
        });
    }
}

void bindingTests() {
    reject("missing region entry binding", allocated(), [](Module &module) {
        eraseOperation<BindRegionParameter>(module.functions[0]);
    });
    reject("region binding after ordinary instruction", allocated(), [](Module &module) {
        module.functions[0].code.insert(module.functions[0].code.begin(), Constant{1, Type::I64});
    });
    reject("region binding index mismatch", allocated(), [](Module &module) {
        operation<BindRegionParameter>(module).index = 1;
    });
    reject("region binding negative index", allocated(), [](Module &module) {
        operation<BindRegionParameter>(module).index = -1;
    });
    reject("region binding requires exact declared spill", allocated(), [](Module &module) {
        operation<BindRegionParameter>(module).offset = 7;
    });
    reject("region cannot bind owner storage", allocated(), [](Module &module) {
        operation<BindRegionParameter>(module).offset = 40;
    });
    reject("scalar binding cannot mint region", allocated(), [](Module &module) {
        module.functions[0].code[0] = BindParameter{0, 8, Type::ByteRegion};
    });
    reject("duplicate region binding after prefix", allocated(), [](Module &module) {
        insertBefore<BeginBytes>(module.functions[0], {BindRegionParameter{0, 8}});
    });
    reject("unreachable late binding remains malformed", allocated(), [](Module &module) {
        append(module.functions[0], {BindRegionParameter{0, 8}});
    });
    reject("owning parameter must be mutable", owningParameter(), [](Module &module) {
        module.functions[0].byteSlots[40] = false;
    });
    reject("owning parameter binding is missing", owningParameter(), [](Module &module) {
        eraseOperation<BindBytesParameter>(module.functions[0]);
    });
    reject("owning parameter uses wrong index", owningParameter(), [](Module &module) {
        operation<BindBytesParameter>(module).index = 0;
    });
    reject("owning parameter requires exact spill", owningParameter(), [](Module &module) {
        operation<BindBytesParameter>(module).offset = 32;
    });
    reject("scalar binding cannot mint owner", owningParameter(), [](Module &module) {
        module.functions[0].code[1] = BindParameter{1, 40, Type::OwnedBytes};
    });
    reject("owning binding outside prefix", owningParameter(), [](Module &module) {
        insertBefore<BytesLength>(module.functions[0], {BindBytesParameter{1, 72}});
    });
    reject("two owning parameters cannot share spill", resourceCall(), [](Module &module) {
        auto &callee = module.functions[1];
        std::get<BindBytesParameter>(callee.code[4]).offset = 40;
    });
    reject("bound parameter cannot begin while live", owningParameter(), [](Module &module) {
        insertBefore<BytesLength>(module.functions[0], {BeginBytes{40}});
    });
    reject("bound parameter cannot restart after end", owningParameter(), [](Module &module) {
        insertBefore<Return>(module.functions[0], {BeginBytes{40}, EndBytes{40}});
    });
    reject("bound parameter cannot restart after transfer and end", owningParameter(true), [](Module &module) {
        auto &function = module.functions[0];
        function.code.pop_back();
        append(function,
               {BeginBytes{72}, MoveBytes{40, 72}, EndBytes{40}, BeginBytes{40}, EndBytes{40}, ReturnBytes{72}});
    });
}

void allocationTests() {
    for (std::int64_t length : {std::int64_t{-1},
                                std::int64_t{0},
                                std::int64_t{1},
                                std::int64_t{65},
                                std::int64_t{513},
                                std::int64_t{4097},
                                std::numeric_limits<std::int64_t>::max()})
        accept("runtime allocation request remains statically live " + std::to_string(length), allocated(length));
    auto readonly = allocated();
    readonly.functions[0].byteSlots[40] = false;
    accept("allocation may initialize readonly owner", readonly);
    auto pristine = frame();
    append(pristine, {BeginBytes{40}, Constant{42, Type::I64}, EndBytes{40}, Return{}});
    accept("pristine lifetime can close without allocation", moduleWith(std::move(pristine)));
    auto restarted = allocated();
    insertBefore<Return>(restarted.functions[0],
                         {BeginBytes{40}, Constant{1, Type::I64}, AllocateBytes{8, 40}, BytesLength{40}, EndBytes{40}});
    accept("ended local storage may begin a new lifetime", restarted);
    reject("begin requires declared exact owner", allocated(), [](Module &module) {
        operation<BeginBytes>(module).offset = 32;
    });
    reject("begin cannot target region", allocated(), [](Module &module) {
        operation<BeginBytes>(module).offset = 8;
    });
    reject("begin cannot overwrite pristine lifetime", allocated(), [](Module &module) {
        insertBefore<Constant>(module.functions[0], {BeginBytes{40}});
    });
    reject("begin cannot overwrite live lifetime", allocated(), [](Module &module) {
        insertBefore<BytesLength>(module.functions[0], {BeginBytes{40}});
    });
    reject("allocation requires begun destination", allocated(), [](Module &module) {
        eraseOperation<BeginBytes>(module.functions[0]);
    });
    reject("allocation requires pristine destination", allocated(), [](Module &module) {
        insertBefore<BytesLength>(module.functions[0], {Constant{1, Type::I64}, AllocateBytes{8, 40}});
    });
    reject("allocation cannot reuse consumed destination", moved(), [](Module &module) {
        insertBefore<EndBytes>(module.functions[0], {Constant{1, Type::I64}, AllocateBytes{8, 40}});
    });
    reject("allocation cannot revive ended destination", allocated(), [](Module &module) {
        insertBefore<Return>(module.functions[0], {Constant{1, Type::I64}, AllocateBytes{8, 40}});
    });
    for (int offset : {0, 7, 40, 176})
        reject("allocation region must be exact active authority " + std::to_string(offset),
               allocated(),
               [=](Module &module) {
                   operation<AllocateBytes>(module).regionOffset = offset;
               });
    reject("declared but unbound region is not authority", allocated(), [](Module &module) {
        module.functions[0].regionSlots.insert(176);
        operation<AllocateBytes>(module).regionOffset = 176;
    });
    for (int offset : {0, 8, 32, 176})
        reject("allocation result requires exact owner " + std::to_string(offset), allocated(), [=](Module &module) {
            operation<AllocateBytes>(module).resultOffset = offset;
        });
    for (const auto &type : {Type::U8, Type::U64, Type::Bool})
        reject("allocation length cannot be " + typeName(type), allocated(), [=](Module &module) {
            operation<Constant>(module).type = type;
            operation<Constant>(module).value = 1;
        });
    reject("allocation requires current length", allocated(), [](Module &module) {
        eraseOperation<Constant>(module.functions[0]);
    });
    reject("allocation clears scalar current", allocated(), [](Module &module) {
        insertBefore<BytesLength>(module.functions[0], {Push{}});
    });
    reject("failed request still needs cleanup", allocated(-1), [](Module &module) {
        eraseOperation<EndBytes>(module.functions[0]);
    });
    auto failed = allocated(-1);
    failed.functions[0].code = {BindRegionParameter{0, 8},
                                BeginBytes{40},
                                Constant{-1, Type::I64},
                                AllocateBytes{8, 40},
                                BytesOk{40},
                                BranchFalse{1},
                                EndBytes{40},
                                Constant{1, Type::I64},
                                Return{},
                                Label{1},
                                BytesLength{40},
                                EndBytes{40},
                                Return{}};
    accept("both success and failure paths close the same static owner", failed);
    reject("false ok path does not implicitly end owner", failed, [](Module &module) {
        eraseOperation<EndBytes>(module.functions[0], 1);
    });
}

void moveAndAccessTests() {
    accept("move preserves scalar current and closes consumed source", moved());
    accept("move may initialize readonly destination", moved(true));
    reject("readonly owner cannot move", moved(), [](Module &module) {
        module.functions[0].byteSlots[40] = false;
    });
    reject("move cannot target its source", moved(), [](Module &module) {
        operation<MoveBytes>(module).resultOffset = 40;
    });
    reject("move needs active destination", moved(), [](Module &module) {
        eraseOperation<BeginBytes>(module.functions[0], 1);
    });
    reject("move cannot overwrite live destination", moved(), [](Module &module) {
        insertBefore<MoveBytes>(module.functions[0], {Constant{1, Type::I64}, AllocateBytes{8, 72}});
    });
    reject("move cannot overwrite consumed destination", moved(), [](Module &module) {
        insertBefore<EndBytes>(module.functions[0], {MoveBytes{72, 40}});
    });
    reject("move cannot repeat consumed source", moved(), [](Module &module) {
        insertBefore<EndBytes>(module.functions[0], {BeginBytes{104}, MoveBytes{40, 104}});
    });
    reject("move cannot read pristine source", moved(), [](Module &module) {
        eraseOperation<AllocateBytes>(module.functions[0]);
    });
    reject("move cannot read ended source", moved(), [](Module &module) {
        insertBefore<MoveBytes>(module.functions[0], {EndBytes{40}});
    });
    reject("move cannot read inactive source", moved(), [](Module &module) {
        operation<MoveBytes>(module).sourceOffset = 104;
    });
    reject("move source must be exact owner", moved(), [](Module &module) {
        operation<MoveBytes>(module).sourceOffset = 32;
    });
    reject("move result must be exact owner", moved(), [](Module &module) {
        operation<MoveBytes>(module).resultOffset = 64;
    });

    const std::vector<std::pair<std::string, Instruction>> reads = {
        {"ok", BytesOk{40}}, {"size", BytesLength{40}}, {"at", BytesLoad{40}}};
    for (const auto &[name, read] : reads) {
        auto module = allocated();
        auto &function = module.functions[0];
        function.result = name == "ok" ? Type::Bool : name == "at" ? Type::U8 : Type::I64;
        function.byteSlots[40] = false;
        function.code[position<BytesLength>(function)] = read;
        if (name == "at")
            function.code.insert(function.code.begin() + 4, Constant{0, Type::I64});
        accept("readonly live owner permits copied " + name, module);
        reject(name + " rejects pristine owner", module, [](Module &changed) {
            eraseOperation<AllocateBytes>(changed.functions[0]);
        });
        reject(name + " rejects ended owner", module, [](Module &changed) {
            changed.functions[0].code.insert(changed.functions[0].code.begin() + 4, EndBytes{40});
        });
        reject(name + " rejects consumed owner", module, [](Module &changed) {
            changed.functions[0].byteSlots[40] = true;
            changed.functions[0].code.insert(changed.functions[0].code.begin() + 4,
                                             {BeginBytes{72}, MoveBytes{40, 72}});
        });
    }
    reject("byte load requires i64 index", allocated(), [](Module &module) {
        auto &function = module.functions[0];
        function.code[position<BytesLength>(function)] = BytesLoad{40};
        function.code.insert(function.code.begin() + 4, Constant{0, Type::U64});
    });
    reject("byte load requires current index", allocated(), [](Module &module) {
        auto &function = module.functions[0];
        function.code[position<BytesLength>(function)] = BytesLoad{40};
    });
    reject("byte query cannot read region", allocated(), [](Module &module) {
        operation<BytesLength>(module).offset = 8;
    });
    reject("byte query cannot read interior descriptor", allocated(), [](Module &module) {
        operation<BytesLength>(module).offset = 32;
    });
    reject("byte query cannot read inactive owner", allocated(), [](Module &module) {
        operation<BytesLength>(module).offset = 72;
    });

    auto store = allocated();
    store.functions[0].result = Type::Bool;
    auto &code = store.functions[0].code;
    code.erase(code.begin() + 4);
    code.insert(code.begin() + 4, {Constant{0, Type::I64}, Push{}, Constant{255, Type::U8}, BytesStore{40}});
    accept("set consumes saved i64 and current u8 and produces bool", store);
    reject("set requires mutable owner", store, [](Module &module) {
        module.functions[0].byteSlots[40] = false;
    });
    reject("set requires saved index", store, [](Module &module) {
        eraseOperation<Push>(module.functions[0]);
    });
    for (const auto &type : {Type::Bool, Type::U8, Type::U64})
        reject("set saved index cannot be " + typeName(type), store, [=](Module &module) {
            operation<Constant>(module, 1).type = type;
        });
    for (const auto &type : {Type::Bool, Type::I64, Type::U64})
        reject("set current value cannot be " + typeName(type), store, [=](Module &module) {
            operation<Constant>(module, 2).type = type;
            operation<Constant>(module, 2).value = 1;
        });
    reject("set cannot use consumed receiver after operand evaluation", store, [](Module &module) {
        insertBefore<BytesStore>(module.functions[0], {BeginBytes{72}, MoveBytes{40, 72}});
    });
    reject("set cannot use ended receiver after operand evaluation", store, [](Module &module) {
        insertBefore<BytesStore>(module.functions[0], {EndBytes{40}});
    });
    reject("set cannot use pristine receiver", store, [](Module &module) {
        eraseOperation<AllocateBytes>(module.functions[0]);
    });
    reject("set result is bool rather than u8", store, [](Module &module) {
        module.functions[0].result = Type::U8;
    });
}

void resizeTests() {
    for (const std::int64_t requested : {std::numeric_limits<std::int64_t>::min(),
                                         std::int64_t{-1},
                                         std::int64_t{0},
                                         std::int64_t{1},
                                         std::int64_t{17},
                                         std::int64_t{65},
                                         std::int64_t{513},
                                         std::int64_t{4097},
                                         std::numeric_limits<std::int64_t>::max()}) {
        accept("resize keeps runtime request statically live " + std::to_string(requested), resized(requested));
    }
    accept("resize of canonical failed allocation remains a live binding", resized(1, -1));
    accept("resize of successful empty owner remains a live binding", resized(65, 0));
    auto parameter = owningParameter();
    insertBefore<BytesLength>(parameter.functions[0], {Constant{65, Type::I64}, BytesResize{40}});
    accept("mutable owning parameter can resize and remain queryable", parameter);
    auto transferred = ownerReturn();
    insertBefore<ReturnBytes>(transferred.functions[0], {Constant{65, Type::I64}, BytesResize{40}});
    accept("resized owner retains authority for an owning return", transferred);
    auto movedResult = moved();
    insertBefore<MoveBytes>(movedResult.functions[0],
                            {Constant{65, Type::I64}, BytesResize{40}, Constant{42, Type::I64}});
    accept("resized owner retains authority for an explicit move", movedResult);
    auto call = resourceCall();
    insertBefore<ResourceCall>(call.functions[0], {Constant{65, Type::I64}, BytesResize{40}});
    accept("resize preserves origin authority and pre-staged scalar call arguments", call);
    auto returnedCall = factoryCall();
    insertBefore<BytesLength>(returnedCall.functions[0], {Constant{65, Type::I64}, BytesResize{40}});
    accept("owner received from resource call can resize", returnedCall);

    reject("resize requires mutable receiver", resized(), [](Module &module) {
        module.functions[0].byteSlots[40] = false;
    });
    reject("even same-size resize cannot use readonly receiver", resized(17), [](Module &module) {
        module.functions[0].byteSlots[40] = false;
    });
    reject("resize requires active receiver lifetime", resized(), [](Module &module) {
        operation<BytesResize>(module).offset = 72;
    });
    reject("resize cannot fabricate ownership in pristine lifetime", resized(), [](Module &module) {
        eraseOperation<AllocateBytes>(module.functions[0]);
    });
    reject("resize cannot revive ended owner", resized(), [](Module &module) {
        insertBefore<BytesResize>(module.functions[0], {EndBytes{40}});
    });
    reject("resize cannot use consumed receiver after size evaluation", resized(), [](Module &module) {
        insertBefore<BytesResize>(module.functions[0], {BeginBytes{72}, MoveBytes{40, 72}});
    });
    reject("resize cannot revive a moved owner after destination cleanup", resized(), [](Module &module) {
        insertBefore<BytesResize>(module.functions[0], {BeginBytes{72}, MoveBytes{40, 72}, EndBytes{72}});
    });
    reject("resize cannot revive a recreated pristine binding", resized(), [](Module &module) {
        insertBefore<BytesResize>(module.functions[0], {EndBytes{40}, BeginBytes{40}});
    });
    reject("resize cannot bypass resource call argument consumption", resourceCall(false), [](Module &module) {
        insertBefore<EndBytes>(module.functions[0], {Constant{65, Type::I64}, BytesResize{40}});
    });
    for (const int offset : {-8, 0, 8, 16, 24, 32, 39, 41, 176}) {
        reject("resize requires exact owner spill " + std::to_string(offset), resized(), [=](Module &module) {
            operation<BytesResize>(module).offset = offset;
        });
    }
    for (const int field : {-2, 0, 1, 3, std::numeric_limits<int>::max()}) {
        reject(
            "standalone resize cannot forge a field selector " + std::to_string(field), resized(), [=](Module &module) {
                operation<BytesResize>(module).fieldIndex = field;
            });
    }
    reject("initialized ordinary scalar is not resize authority", resized(), [](Module &module) {
        module.functions[0].slots[144] = Type::I64;
        insertBefore<BytesResize>(module.functions[0], {Store{144, Type::I64}});
        operation<BytesResize>(module).offset = 144;
    });
    for (const auto &type : {Type::Bool, Type::U8, Type::U64}) {
        reject("resize length cannot be " + typeName(type), resized(), [=](Module &module) {
            operation<Constant>(module, 1).type = type;
            operation<Constant>(module, 1).value = 1;
        });
    }
    reject("resize length cannot be a nominal enum", resized(), [](Module &module) {
        module.enumCases["Length"] = 1;
        auto &function = module.functions[0];
        function.code[position<Constant>(function, 1)] = EnumConstant{Type::enumeration("Length"), 0};
    });
    reject("resize requires current length rather than stale allocation operand", resized(), [](Module &module) {
        eraseOperation<Constant>(module.functions[0], 1);
    });
    reject("resize saved i64 cannot substitute for current length", resized(), [](Module &module) {
        insertBefore<BytesResize>(module.functions[0], {Push{}, Constant{1, Type::Bool}});
    });
    reject("resize bool result cannot act as the next resize length", resized(), [](Module &module) {
        insertBefore<EndBytes>(module.functions[0], {BytesResize{40}});
    });
    for (const auto &type : {Type::I64, Type::U8, Type::U64}) {
        reject("resize result is bool rather than " + typeName(type), resized(), [=](Module &module) {
            module.functions[0].result = type;
        });
    }
    reject("resize cannot erase the owner cleanup obligation", resized(), [](Module &module) {
        eraseOperation<EndBytes>(module.functions[0]);
    });
    reject("failed resize request cannot erase cleanup obligation", resized(-1), [](Module &module) {
        eraseOperation<EndBytes>(module.functions[0]);
    });
    reject("resize does not make its owner a pristine allocation destination", resized(), [](Module &module) {
        insertBefore<EndBytes>(module.functions[0], {Constant{1, Type::I64}, AllocateBytes{8, 40}});
    });
    reject("resize does not make its owner a pristine move destination", resized(), [](Module &module) {
        insertBefore<BytesResize>(
            module.functions[0],
            {BeginBytes{72}, Constant{1, Type::I64}, AllocateBytes{8, 72}, Constant{65, Type::I64}});
        insertBefore<EndBytes>(module.functions[0], {MoveBytes{72, 40}});
    });
    for (int depth : {0, 1, 2, 3, 4}) {
        auto saved = resized();
        auto &function = saved.functions[0];
        function.result = Type::I64;
        for (int index = 0; index < depth; ++index) {
            insertBefore<Constant>(function, {Constant{1099511627793LL + index, Type::I64}, Push{}}, 1);
        }
        insertBefore<EndBytes>(function, {BytesLength{40}});
        for (int index = 0; index < depth; ++index) {
            insertBefore<EndBytes>(function, {BinaryValue{Binary::CheckedAdd, Type::I64}});
        }
        accept("resize preserves pending operand depth " + std::to_string(depth), saved);
    }
    auto typedStack = resized();
    auto &typed = typedStack.functions[0];
    typed.slots = {{144, Type::I64}, {152, Type::U64}, {160, Type::U8}, {168, Type::Bool}, {176, Type::Bool}};
    insertBefore<BytesResize>(typed,
                              {Push{},
                               Constant{7, Type::U64},
                               Push{},
                               Constant{255, Type::U8},
                               Push{},
                               Constant{1, Type::Bool},
                               Push{},
                               Constant{513, Type::I64}});
    insertBefore<EndBytes>(typed,
                           {Store{176, Type::Bool},
                            Pop{},
                            Store{168, Type::Bool},
                            Pop{},
                            Store{160, Type::U8},
                            Pop{},
                            Store{152, Type::U64},
                            Pop{},
                            Store{144, Type::I64},
                            Load{176, Type::Bool}});
    accept("resize preserves exact heterogeneous operand stack and produces current bool", typedStack);
    reject("resize does not secretly consume a saved operand", resized(), [](Module &module) {
        insertBefore<BytesResize>(module.functions[0], {Push{}});
    });
    reject("resize does not secretly create a saved operand", resized(), [](Module &module) {
        insertBefore<EndBytes>(module.functions[0], {Pop{}});
    });

    auto branch = resized();
    auto &branched = branch.functions[0];
    const auto size_operand = position<Constant>(branched, 1);
    branched.code.erase(branched.code.begin() + size_operand, branched.code.end());
    append(branched,
           {BytesOk{40},
            BranchFalse{1},
            Constant{65, Type::I64},
            BytesResize{40},
            Jump{2},
            Label{1},
            Constant{0, Type::Bool},
            Label{2},
            EndBytes{40},
            Return{}});
    accept("short-circuit resize preserves exactly the original ownership token at join", branch);
    auto bothBranches = branch;
    insertBefore<Constant>(bothBranches.functions[0], {Constant{0, Type::I64}, BytesResize{40}}, 2);
    accept("distinct resize sites preserve one shared ownership token", bothBranches);
    reject(
        "conditional resize cannot hide conditional owner consumption",
        branch,
        [](Module &module) {
            insertBefore<Jump>(module.functions[0], {BeginBytes{72}, MoveBytes{40, 72}, EndBytes{72}});
        },
        "control-flow join");
    reject(
        "conditional resize cannot hide conditional owner lifetime restart",
        branch,
        [](Module &module) {
            insertBefore<Jump>(
                module.functions[0],
                {EndBytes{40}, BeginBytes{40}, Constant{17, Type::I64}, AllocateBytes{8, 40}, Constant{1, Type::Bool}});
        },
        "control-flow join");
    reject("resize result false does not discharge the original owner", branch, [](Module &module) {
        auto &function = module.functions[0];
        function.code.erase(function.code.begin() + position<EndBytes>(function), function.code.end());
        append(function,
               {BranchFalse{3},
                EndBytes{40},
                Constant{1, Type::Bool},
                Return{},
                Label{3},
                Constant{0, Type::Bool},
                Return{}});
    });
    auto loop = allocated();
    insertBefore<BytesLength>(loop.functions[0],
                              {Label{1},
                               Constant{65, Type::I64},
                               BytesResize{40},
                               BranchFalse{2},
                               Constant{0, Type::I64},
                               BytesResize{40},
                               Jump{1},
                               Label{2}});
    accept("resize in loop condition and body preserves outer owner across backedge", loop);
    reject(
        "loop resize does not permit conditional outer ownership transfer",
        loop,
        [](Module &module) {
            insertBefore<Jump>(module.functions[0], {BeginBytes{72}, MoveBytes{40, 72}, EndBytes{72}});
        },
        "control-flow join");
}

void cleanupAndReturnTests() {
    for (int depth : {0, 1, 2, 3, 4}) {
        auto module = moved();
        auto &function = module.functions[0];
        insertBefore<BeginBytes>(function, {BeginBytes{104}});
        for (int index = 0; index < depth; ++index)
            insertBefore<MoveBytes>(function, {Constant{1099511627793LL + index, Type::I64}, Push{}});
        insertBefore<MoveBytes>(function, {Constant{42, Type::I64}});
        insertBefore<Return>(function, {EndBytes{104}});
        for (int index = 0; index < depth; ++index)
            insertBefore<Return>(function, {BinaryValue{Binary::CheckedAdd, Type::I64}});
        accept("cleanup preserves current and saved operand depth " + std::to_string(depth), module);
    }
    reject("end cannot close inactive owner", allocated(), [](Module &module) {
        operation<EndBytes>(module).offset = 72;
    });
    reject("end requires exact owner", allocated(), [](Module &module) {
        operation<EndBytes>(module).offset = 32;
    });
    reject("end cannot close region", allocated(), [](Module &module) {
        operation<EndBytes>(module).offset = 8;
    });
    reject("double cleanup is malformed", allocated(), [](Module &module) {
        insertBefore<Return>(module.functions[0], {EndBytes{40}});
    });
    reject("scalar return cannot leak live owner", allocated(), [](Module &module) {
        eraseOperation<EndBytes>(module.functions[0]);
    });
    reject("scalar return cannot leak pristine owner", allocated(), [](Module &module) {
        insertBefore<Return>(module.functions[0], {BeginBytes{72}});
    });
    reject("scalar return cannot leak consumed lifetime", moved(), [](Module &module) {
        eraseOperation<EndBytes>(module.functions[0]);
    });
    reject("scalar return cannot leak owning parameter", owningParameter(), [](Module &module) {
        eraseOperation<EndBytes>(module.functions[0]);
    });
    reject("scalar return still requires empty expression stack", allocated(), [](Module &module) {
        insertBefore<Return>(module.functions[0], {Push{}});
    });
    reject("owner return requires mutable source", ownerReturn(), [](Module &module) {
        module.functions[0].byteSlots[40] = false;
    });
    reject("owner return requires live source", ownerReturn(), [](Module &module) {
        eraseOperation<AllocateBytes>(module.functions[0]);
    });
    reject("owner return cannot read consumed source", ownerReturn(), [](Module &module) {
        insertBefore<ReturnBytes>(module.functions[0], {BeginBytes{72}, MoveBytes{40, 72}, EndBytes{72}});
    });
    reject("owner return cannot read ended source", ownerReturn(), [](Module &module) {
        insertBefore<ReturnBytes>(module.functions[0], {EndBytes{40}});
    });
    reject("owner return cannot read inactive source", ownerReturn(), [](Module &module) {
        operation<ReturnBytes>(module).offset = 72;
    });
    reject("owner return requires exact owner", ownerReturn(), [](Module &module) {
        operation<ReturnBytes>(module).offset = 32;
    });
    reject("owner return cannot return region", ownerReturn(), [](Module &module) {
        operation<ReturnBytes>(module).offset = 8;
    });
    reject("owner return cannot leak other pristine binding", ownerReturn(), [](Module &module) {
        insertBefore<ReturnBytes>(module.functions[0], {BeginBytes{72}});
    });
    reject("owner return cannot leak other live binding", ownerReturn(), [](Module &module) {
        insertBefore<ReturnBytes>(module.functions[0], {BeginBytes{72}, Constant{1, Type::I64}, AllocateBytes{8, 72}});
    });
    reject("owner return cannot leak consumed binding", ownerReturn(), [](Module &module) {
        insertBefore<ReturnBytes>(module.functions[0], {BeginBytes{72}, MoveBytes{40, 72}});
        operation<ReturnBytes>(module).offset = 72;
    });
    reject("owner return requires empty expression stack", ownerReturn(), [](Module &module) {
        insertBefore<ReturnBytes>(module.functions[0], {Constant{42, Type::I64}, Push{}});
    });
    reject("owner return cannot substitute for scalar return", allocated(), [](Module &module) {
        auto &function = module.functions[0];
        eraseOperation<EndBytes>(function);
        function.code.back() = ReturnBytes{40};
    });
    reject("scalar return cannot substitute for owner transfer", ownerReturn(), [](Module &module) {
        auto &function = module.functions[0];
        function.code.pop_back();
        append(function, {BytesLength{40}, EndBytes{40}, Return{}});
    });
    auto transfer = ownerReturn();
    insertBefore<ReturnBytes>(transfer.functions[0], {BeginBytes{72}, MoveBytes{40, 72}, EndBytes{40}});
    operation<ReturnBytes>(transfer).offset = 72;
    accept("return moves one token after consumed source lifetime closes", transfer);
    auto pristine = ownerReturn();
    insertBefore<ReturnBytes>(pristine.functions[0], {BeginBytes{72}, EndBytes{72}});
    accept("owner return permits fully ended pristine sibling", pristine);

    auto object = frame("object_return_with_private_spill", Type("Box"));
    object.parameters.clear();
    object.regionSlots.clear();
    object.slots[144] = Type::I64;
    object.objectSlots[144] = {"Box", true};
    object.code = {BeginObject{144}, Constant{42, Type::I64}, Store{144, Type::I64}, ReturnObject{144}};
    auto objectModule = moduleWith(std::move(object));
    objectModule.classLayouts["Box"] = {Type::I64};
    accept("object return permits inactive declared owner storage", objectModule);
    reject(
        "object return cannot leak pristine owner lifetime",
        objectModule,
        [](Module &module) {
            insertBefore<ReturnObject>(module.functions[0], {BeginBytes{40}});
        },
        "owned byte lifetime");

    auto arrayReturn = ownerReturn();
    arrayReturn.functions[0].arraySlots[144] = 2;
    arrayReturn.functions[0].slots = {{144, Type::U8}, {143, Type::U8}};
    insertBefore<ReturnBytes>(
        arrayReturn.functions[0],
        {BeginArray{144}, Constant{7, Type::U8}, Store{144, Type::U8}, Store{143, Type::U8}, EndArray{144}});
    accept("owner return follows complete local array cleanup", arrayReturn);
    reject(
        "owner return cannot leak active array lifetime",
        arrayReturn,
        [](Module &module) {
            eraseOperation<EndArray>(module.functions[0]);
        },
        "span or byte array lifetime");
    auto spanReturn = arrayReturn;
    spanReturn.functions[0].spanSlots.insert(168);
    insertBefore<EndArray>(spanReturn.functions[0], {BorrowSpan{144, 168}, EndSpan{168}});
    accept("owner return follows complete span and array cleanup", spanReturn);
    reject(
        "owner return cannot leak active span and origin",
        spanReturn,
        [](Module &module) {
            eraseOperation<EndSpan>(module.functions[0]);
            eraseOperation<EndArray>(module.functions[0]);
        },
        "span or byte array lifetime");
}

void resourceCallTests() {
    accept("region-only call may create new returned ownership", factoryCall());
    accept("region-only call may return scalar without owners", factoryCall(false));
    for (int depth : {0, 1, 2, 3}) {
        accept("owner result call preserves saved operands " + std::to_string(depth), resourceCall(true, depth));
        accept("scalar result call preserves saved operands " + std::to_string(depth), resourceCall(false, depth));
    }
    accept("owner call may initialize readonly result", resourceCall(true, 0, true));
    reject("resource call target must exist", resourceCall(), [](Module &module) {
        operation<ResourceCall>(module).callee = "unknown";
    });
    reject("ordinary scalar target is not resource-aware", resourceCall(), [](Module &module) {
        auto &callee = module.functions[1];
        callee = IRFunction{};
        callee.name = "bytes_callee";
        callee.result = Type::I64;
        callee.code = {Constant{42, Type::I64}, Return{}};
    });
    for (int offset : {0, 7, 40, 176})
        reject("resource call requires active exact region " + std::to_string(offset),
               resourceCall(),
               [=](Module &module) {
                   operation<ResourceCall>(module).regionOffset = offset;
               });
    reject("unbound second region cannot transport owner", resourceCall(), [](Module &module) {
        module.functions[0].regionSlots.insert(176);
        operation<ResourceCall>(module).regionOffset = 176;
    });
    reject("resource argument vector cannot omit region position", resourceCall(), [](Module &module) {
        operation<ResourceCall>(module).ownerArguments.erase(operation<ResourceCall>(module).ownerArguments.begin());
    });
    reject("resource argument vector cannot add positions", resourceCall(), [](Module &module) {
        operation<ResourceCall>(module).ownerArguments.push_back(0);
    });
    reject("resource argument vector cannot be absent", resourceCall(), [](Module &module) {
        operation<ResourceCall>(module).ownerArguments.clear();
    });
    for (int index : {0, 1, 3, 5})
        reject(
            "non-owner argument position must be zero " + std::to_string(index), resourceCall(), [=](Module &module) {
                operation<ResourceCall>(module).ownerArguments[index] = 40;
            });
    for (int offset : {0, 8, 32, 136, 176})
        reject(
            "owner argument requires exact live owner " + std::to_string(offset), resourceCall(), [=](Module &module) {
                operation<ResourceCall>(module).ownerArguments[2] = offset;
            });
    reject("one owner cannot supply two arguments", resourceCall(), [](Module &module) {
        operation<ResourceCall>(module).ownerArguments[4] = 40;
    });
    reject("readonly owner cannot supply moved argument", resourceCall(), [](Module &module) {
        module.functions[0].byteSlots[40] = false;
    });
    reject("pristine owner cannot supply argument", resourceCall(), [](Module &module) {
        eraseOperation<AllocateBytes>(module.functions[0]);
    });
    reject("consumed owner cannot supply argument", resourceCall(), [](Module &module) {
        insertBefore<ResourceCall>(module.functions[0], {BeginBytes{136}, MoveBytes{40, 136}});
    });
    reject("ended owner cannot supply argument", resourceCall(), [](Module &module) {
        insertBefore<ResourceCall>(module.functions[0], {EndBytes{40}});
    });
    reject("resource call consumes every argument", resourceCall(), [](Module &module) {
        insertBefore<EndBytes>(module.functions[0], {BytesLength{72}});
    });
    reject("resource call cannot move an argument twice", resourceCall(), [](Module &module) {
        insertBefore<EndBytes>(module.functions[0], {BeginBytes{136}, MoveBytes{40, 136}});
    });
    reject("resource call result must have begun lifetime", resourceCall(), [](Module &module) {
        eraseOperation<BeginBytes>(module.functions[0], 2);
    });
    reject("resource call result must be pristine", resourceCall(), [](Module &module) {
        insertBefore<ResourceCall>(module.functions[0], {Constant{1, Type::I64}, AllocateBytes{8, 104}});
    });
    reject("resource result cannot alias moved argument", resourceCall(), [](Module &module) {
        operation<ResourceCall>(module).resultOffset = 40;
    });
    for (int offset : {0, 8, 96, 176})
        reject("owner call result requires exact owner " + std::to_string(offset), resourceCall(), [=](Module &module) {
            operation<ResourceCall>(module).resultOffset = offset;
        });
    reject("scalar call result requires zero spill", resourceCall(false), [](Module &module) {
        operation<ResourceCall>(module).resultOffset = 104;
    });
    reject("owner call result clears scalar current", resourceCall(), [](Module &module) {
        insertBefore<EndBytes>(module.functions[0], {Push{}});
    });
    reject("resource call requires scalar argument stack", resourceCall(), [](Module &module) {
        eraseOperation<Push>(module.functions[0], 2);
    });
    reject("resource call checks scalar argument type", resourceCall(), [](Module &module) {
        auto &function = module.functions[0];
        const auto lastPush = position<Push>(function, 2);
        function.code[lastPush - 1] = Constant{1, Type::I64};
    });
    reject("scalar Call cannot target resource signature", resourceCall(), [](Module &module) {
        auto &function = module.functions[0];
        function.code[position<ResourceCall>(function)] = Call{"bytes_callee"};
    });
    reject("AggregateCall cannot target resource signature", resourceCall(), [](Module &module) {
        auto &function = module.functions[0];
        function.code[position<ResourceCall>(function)] =
            AggregateCall{"bytes_callee", {0, 0, 0, 0, 0, 0}, 0, {0, 0, 0, 0, 0, 0}};
    });
    reject("consumed call arguments still require lexical cleanup", resourceCall(), [](Module &module) {
        eraseOperation<EndBytes>(module.functions[0]);
    });
    reject("returned call owner still requires cleanup", resourceCall(), [](Module &module) {
        eraseOperation<EndBytes>(module.functions[0], 2);
    });
}

void scalarForgeryTests() {
    for (const auto &type : {Type::ByteRegion, Type::OwnedBytes}) {
        reject("constant cannot fabricate " + typeName(type), allocated(), [=](Module &module) {
            insertBefore<BeginBytes>(module.functions[0], {Constant{0, type}});
        });
        reject("enum constant cannot fabricate " + typeName(type), allocated(), [=](Module &module) {
            insertBefore<BeginBytes>(module.functions[0], {EnumConstant{type, 0}});
        });
        reject("load cannot expose " + typeName(type), allocated(), [=](Module &module) {
            insertBefore<BytesLength>(module.functions[0], {Load{type.isRegion() ? 8 : 40, type}});
        });
        reject("store cannot fabricate " + typeName(type), allocated(), [=](Module &module) {
            insertBefore<BytesLength>(module.functions[0], {Store{type.isRegion() ? 8 : 40, type}});
        });
        reject("checked conversion cannot produce " + typeName(type), allocated(), [=](Module &module) {
            insertBefore<AllocateBytes>(module.functions[0], {Convert{Type::I64, type}});
        });
        reject("checked conversion cannot consume " + typeName(type), allocated(), [=](Module &module) {
            insertBefore<AllocateBytes>(module.functions[0], {Convert{type, Type::I64}});
        });
        reject("binary operation cannot fabricate " + typeName(type), allocated(), [=](Module &module) {
            insertBefore<AllocateBytes>(module.functions[0], {Push{}, BinaryValue{Binary::CheckedAdd, type}});
        });
        reject("comparison cannot interpret " + typeName(type), allocated(), [=](Module &module) {
            insertBefore<AllocateBytes>(module.functions[0], {Push{}, Compare{Comparison::Equal, type}});
        });
    }
    for (int offset : {8, 16, 24, 32, 40}) {
        reject(
            "scalar load cannot inspect private resource word " + std::to_string(offset),
            allocated(),
            [=](Module &module) {
                insertBefore<BytesLength>(module.functions[0], {Load{offset, Type::I64}});
            },
            "slot type/layout mismatch");
        reject(
            "scalar store cannot overwrite private resource word " + std::to_string(offset),
            allocated(),
            [=](Module &module) {
                insertBefore<BytesLength>(module.functions[0], {Constant{0, Type::I64}, Store{offset, Type::I64}});
            },
            "slot type/layout mismatch");
    }
    reject("legacy own handle cannot expose private owner", allocated(), [](Module &module) {
        insertBefore<BytesLength>(module.functions[0], {BorrowHandle{40, Type::Ref}});
    });
    reject("fixed-array scalar load cannot expose private descriptor", allocated(), [](Module &module) {
        insertBefore<BytesLength>(module.functions[0],
                                  {Constant{0, Type::I64}, BoundsGuard{40, 4, Type::I64}, IndexLoad{40, 4, Type::I64}});
    });
}

Module branchMove() {
    auto function = frame();
    append(function,
           {BeginBytes{40},
            Constant{17, Type::I64},
            AllocateBytes{8, 40},
            BeginBytes{72},
            BytesOk{40},
            BranchFalse{1},
            MoveBytes{40, 72},
            Constant{42, Type::I64},
            Jump{2},
            Label{1},
            MoveBytes{40, 72},
            Constant{42, Type::I64},
            Label{2},
            EndBytes{40},
            EndBytes{72},
            Return{}});
    return moduleWith(std::move(function));
}

void branchTests() {
    accept("different move sites preserve the same unique token at join", branchMove());
    auto balanced = allocated();
    balanced.functions[0].code = {BindRegionParameter{0, 8},
                                  BeginBytes{40},
                                  Constant{1, Type::I64},
                                  AllocateBytes{8, 40},
                                  BytesOk{40},
                                  BranchFalse{1},
                                  EndBytes{40},
                                  Constant{42, Type::I64},
                                  Jump{2},
                                  Label{1},
                                  EndBytes{40},
                                  Constant{42, Type::I64},
                                  Label{2},
                                  Return{}};
    accept("both branches completely close owner before join", balanced);
    auto returning = balanced;
    returning.functions[0].code[position<Jump>(returning.functions[0])] = Return{};
    accept("early return and continuing branch each close owner", returning);
    reject("one branch leaves owner live", balanced, [](Module &module) {
        eraseOperation<EndBytes>(module.functions[0]);
    });
    reject(
        "one branch leaves consumed source lifetime open",
        branchMove(),
        [](Module &module) {
            insertBefore<Jump>(module.functions[0], {EndBytes{40}});
        },
        "control-flow join");
    reject(
        "move cannot occur only on one continuing branch",
        branchMove(),
        [](Module &module) {
            eraseOperation<MoveBytes>(module.functions[0]);
        },
        "control-flow join");
    reject(
        "token cannot occupy different slots at join",
        branchMove(),
        [](Module &module) {
            auto &function = module.functions[0];
            insertBefore<BytesOk>(function, {BeginBytes{104}});
            operation<MoveBytes>(module, 1).resultOffset = 104;
            insertBefore<Return>(function, {EndBytes{104}});
        },
        "control-flow join");

    auto distinctBindings = frame();
    append(distinctBindings,
           {Constant{1, Type::Bool},
            BranchFalse{1},
            BeginBytes{40},
            Constant{42, Type::I64},
            Jump{2},
            Label{1},
            BeginBytes{40},
            Constant{42, Type::I64},
            Label{2},
            EndBytes{40},
            Return{}});
    reject(
        "pristine bindings created at distinct sites cannot merge",
        moduleWith(distinctBindings),
        [](Module &) {
        },
        "control-flow join");
    auto distinctAllocations = frame();
    append(distinctAllocations,
           {BeginBytes{40},
            Constant{1, Type::Bool},
            BranchFalse{1},
            Constant{1, Type::I64},
            AllocateBytes{8, 40},
            Constant{42, Type::I64},
            Jump{2},
            Label{1},
            Constant{1, Type::I64},
            AllocateBytes{8, 40},
            Constant{42, Type::I64},
            Label{2},
            EndBytes{40},
            Return{}});
    reject(
        "allocations created at distinct sites cannot merge",
        moduleWith(distinctAllocations),
        [](Module &) {
        },
        "control-flow join");
    auto consumedTokens = distinctAllocations;
    insertBefore<BranchFalse>(consumedTokens, {BeginBytes{72}});
    insertBefore<Jump>(consumedTokens, {MoveBytes{40, 72}, EndBytes{72}});
    consumedTokens.code.insert(consumedTokens.code.begin() + position<Label>(consumedTokens, 1),
                               {MoveBytes{40, 72}, EndBytes{72}});
    accept("consumed tokens clear authority but retain the same binding lifetime", moduleWith(consumedTokens));
    auto restarted = allocated();
    insertBefore<BytesLength>(restarted.functions[0],
                              {BytesOk{40},
                               BranchFalse{1},
                               EndBytes{40},
                               BeginBytes{40},
                               Constant{1, Type::I64},
                               AllocateBytes{8, 40},
                               Jump{2},
                               Label{1},
                               Label{2}});
    reject(
        "one branch cannot restart an outer owner lifetime",
        restarted,
        [](Module &) {
        },
        "control-flow join");
    auto pristine = frame();
    append(pristine,
           {BeginBytes{40},
            Constant{1, Type::Bool},
            BranchFalse{1},
            EndBytes{40},
            Constant{42, Type::I64},
            Jump{2},
            Label{1},
            Constant{42, Type::I64},
            Label{2},
            Return{}});
    reject("pristine lifetime cannot disappear on only one branch", moduleWith(pristine));

    auto ownerPaths = ownerReturn();
    ownerPaths.functions[0].code.pop_back();
    append(ownerPaths.functions[0], {BytesOk{40}, BranchFalse{1}, ReturnBytes{40}, Label{1}, ReturnBytes{40}});
    accept("mutually exclusive returns each transfer the live owner", ownerPaths);
    reject("one return path cannot transfer a consumed owner", ownerPaths, [](Module &module) {
        insertBefore<ReturnBytes>(module.functions[0], {BeginBytes{72}, MoveBytes{40, 72}, EndBytes{72}}, 1);
    });
}

void loopAndLogicalTests() {
    auto loop = allocated();
    insertBefore<BytesLength>(loop.functions[0],
                              {Label{1},
                               BeginBytes{72},
                               Constant{1, Type::I64},
                               AllocateBytes{8, 72},
                               EndBytes{72},
                               BytesOk{40},
                               BranchFalse{2},
                               Jump{1},
                               Label{2}});
    accept("loop allocation site may repeat after every lifetime closes", loop);
    reject(
        "backedge cannot retain an iteration owner",
        loop,
        [](Module &module) {
            eraseOperation<EndBytes>(module.functions[0]);
            insertBefore<Return>(module.functions[0], {EndBytes{72}});
        },
        "control-flow join");
    reject(
        "backedge cannot leave outer owner consumed",
        loop,
        [](Module &module) {
            insertBefore<Jump>(module.functions[0], {BeginBytes{104}, MoveBytes{40, 104}, EndBytes{104}});
        },
        "control-flow join");
    reject(
        "backedge cannot restart outer owner at new site",
        loop,
        [](Module &module) {
            insertBefore<Jump>(module.functions[0],
                               {EndBytes{40}, BeginBytes{40}, Constant{1, Type::I64}, AllocateBytes{8, 40}});
        },
        "control-flow join");
    reject(
        "same allocation site cannot mint again while previous token lives",
        loop,
        [](Module &module) {
            insertBefore<EndBytes>(module.functions[0], {BeginBytes{104}, MoveBytes{72, 104}});
            insertBefore<Return>(module.functions[0], {EndBytes{104}});
        },
        "control-flow join");
    reject(
        "restarted old slot cannot hide its token moved across backedge",
        loop,
        [](Module &module) {
            insertBefore<EndBytes>(module.functions[0], {BeginBytes{104}, MoveBytes{72, 104}});
            insertBefore<BytesOk>(module.functions[0], {BeginBytes{72}});
            insertBefore<Return>(module.functions[0], {EndBytes{72}, EndBytes{104}});
        },
        "control-flow join");
    auto callLoop = factoryCall();
    callLoop.functions[0].code = {BindRegionParameter{0, 8},
                                  Label{1},
                                  BeginBytes{40},
                                  ResourceCall{"bytes_factory", 8, {0}, 40},
                                  EndBytes{40},
                                  Constant{0, Type::Bool},
                                  BranchFalse{2},
                                  Jump{1},
                                  Label{2},
                                  Constant{42, Type::I64},
                                  Return{}};
    accept("call result creation site may repeat after its lifetime closes", callLoop);
    reject(
        "same call site cannot mint again while previous result token lives",
        callLoop,
        [](Module &module) {
            insertBefore<EndBytes>(module.functions[0], {BeginBytes{72}, MoveBytes{40, 72}});
            insertBefore<Return>(module.functions[0], {EndBytes{72}});
        },
        "control-flow join");
    auto reads = allocated();
    insertBefore<BytesLength>(reads.functions[0],
                              {Label{1},
                               BytesOk{40},
                               BranchFalse{2},
                               Constant{0, Type::I64},
                               BytesLoad{40},
                               Constant{0, Type::I64},
                               Push{},
                               Constant{42, Type::U8},
                               BytesStore{40},
                               Jump{1},
                               Label{2}});
    accept("content-only loop condition and body preserve outer ownership", reads);
    auto pristine = allocated();
    insertBefore<BytesLength>(pristine.functions[0],
                              {BeginBytes{72}, Label{1}, BytesOk{40}, BranchFalse{2}, Jump{1}, Label{2}, EndBytes{72}});
    accept("unchanged pristine lifetime may cross backedge", pristine);
    reject(
        "pristine lifetime cannot be conditionally recreated in loop",
        pristine,
        [](Module &module) {
            insertBefore<Jump>(module.functions[0], {EndBytes{72}, BeginBytes{72}});
        },
        "control-flow join");

    auto logical = allocated();
    logical.functions[0].result = Type::Bool;
    auto &function = logical.functions[0];
    function.code.erase(function.code.begin() + 4);
    function.code.insert(function.code.begin() + 4,
                         {BytesOk{40},
                          BranchFalse{1},
                          Constant{0, Type::I64},
                          Push{},
                          Constant{255, Type::U8},
                          BytesStore{40},
                          Jump{2},
                          Label{1},
                          Constant{0, Type::Bool},
                          Label{2}});
    accept("short-circuit copied mutation has identical owner state", logical);
    reject(
        "short-circuit right operand cannot consume outer owner",
        logical,
        [](Module &module) {
            insertBefore<Jump>(module.functions[0], {BeginBytes{72}, MoveBytes{40, 72}, EndBytes{72}});
        },
        "control-flow join");
    reject(
        "short-circuit right operand cannot leave pristine local",
        logical,
        [](Module &module) {
            insertBefore<Jump>(module.functions[0], {BeginBytes{72}});
        },
        "control-flow join");
    reject("short-circuit right operand cannot close outer owner", logical, [](Module &module) {
        insertBefore<Jump>(module.functions[0], {EndBytes{40}});
    });

    auto calls = resourceCall(true);
    auto &caller = calls.functions[0];
    const auto scalarArguments = position<Push>(caller) - 1;
    caller.code.erase(caller.code.begin() + scalarArguments, caller.code.end());
    // Each branch stages its own scalar arguments and supplies a different call
    // token into the same outer pristine binding; equal shape is insufficient.
    append(caller,
           {BeginBytes{104},
            Constant{1, Type::Bool},
            BranchFalse{1},
            Load{144, Type::I64},
            Push{},
            Load{152, Type::Bool},
            Push{},
            Load{160, Type::U8},
            Push{},
            ResourceCall{"bytes_callee", 8, {0, 0, 40, 0, 72, 0}, 104},
            Jump{2},
            Label{1},
            Load{144, Type::I64},
            Push{},
            Load{152, Type::Bool},
            Push{},
            Load{160, Type::U8},
            Push{},
            ResourceCall{"bytes_callee", 8, {0, 0, 40, 0, 72, 0}, 104},
            Label{2},
            EndBytes{40},
            EndBytes{72},
            BytesLength{104},
            EndBytes{104},
            Return{}});
    reject(
        "distinct returned-call token sites cannot merge",
        calls,
        [](Module &) {
        },
        "control-flow join");
}

void emittedSymbolTests() {
    auto addScalarHelpers = [](Module &module) {
        for (const std::string name : {"malloc", "free", "memcpy", "memset", "abort", "fputs", "fflush", "printf"}) {
            IRFunction helper;
            helper.name = name;
            helper.result = Type::I64;
            helper.code = {Constant{42, Type::I64}, Return{}};
            insertBefore<Return>(module.functions.front(), {Call{name}});
            module.functions.push_back(std::move(helper));
        }
    };
    auto checkVisibility = [&](const std::string &name, Module module, bool privateGraph) {
        addScalarHelpers(module);
        const auto validated = validate(std::move(module));
        const auto assembly = X86Emitter{}.emit(validated);
        // Check exact source-function directives. Reserved reflection helpers
        // are emitted separately and do not share host libc symbol names.
        for (const auto &function : validated.get().functions) {
            const auto local = "\n.local " + function.name + "\n";
            const auto global = "\n.globl " + function.name + "\n";
            require(assembly.find(privateGraph ? local : global) != std::string::npos,
                    name + ": missing expected visibility for " + function.name);
            require(assembly.find(privateGraph ? global : local) == std::string::npos,
                    name + ": unexpected opposite visibility for " + function.name);
        }
        if (!privateGraph)
            require(assembly.find("__au_runtime_bytes_") == std::string::npos,
                    name + ": scalar-only output gained owned byte runtime dependencies");
        ++accepted;
        std::cout << "PASS owned byte IR " << name << '\n';
    };
    checkVisibility("owned byte graph keeps every Aurora helper local", factoryCall(), true);

    auto regionOnly = frame("region_only_entry");
    append(regionOnly, {Constant{42, Type::I64}, Return{}});
    checkVisibility("region signature alone makes the whole graph private", moduleWith(std::move(regionOnly)), true);

    auto lifetimeOnly = frame("lifetime_only_entry");
    lifetimeOnly.parameters.clear();
    lifetimeOnly.regionSlots.clear();
    lifetimeOnly.code = {BeginBytes{40}, Constant{42, Type::I64}, EndBytes{40}, Return{}};
    checkVisibility("owner lifetime alone makes the whole graph private", moduleWith(std::move(lifetimeOnly)), true);

    IRFunction scalarOnly;
    scalarOnly.name = "scalar_only_entry";
    scalarOnly.result = Type::I64;
    scalarOnly.code = {Constant{42, Type::I64}, Return{}};
    checkVisibility("scalar-only graph preserves legacy global entry points", moduleWith(std::move(scalarOnly)), false);
}

void directTests() {
    signatureTests();
    layoutTests();
    bindingTests();
    allocationTests();
    moveAndAccessTests();
    resizeTests();
    cleanupAndReturnTests();
    resourceCallTests();
    scalarForgeryTests();
    branchTests();
    loopAndLogicalTests();
    emittedSymbolTests();
}
} // namespace

int main(int argc, char **) {
    try {
        require(argc == 1, "usage: owned-bytes-ir");
        directTests();
        std::cout << "PASS owned byte IR: " << accepted << " accepted, " << rejected << " rejected\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL owned byte IR: " << error.what() << '\n';
        return 1;
    }
}
