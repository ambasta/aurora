// Independently authored IR for synchronous named owning-object borrows.
// No parser or lowering is used. Layout offsets are literal test expectations.
#include "ir_verify.hpp"
#include "x86.hpp"
#include <functional>
#include <iostream>
#include <string>

using namespace aurora;
using namespace aurora::ir;
using F = aurora::ir::Function;
namespace {
int accepted = 0, rejected = 0;
void require(bool condition, const std::string &message) {
    if (!condition)
        throw Error(message);
}
F &named(Module &module, const std::string &name) {
    for (auto &function : module.functions)
        if (function.name == name)
            return function;
    throw Error("missing fixture function " + name);
}
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
template <class T> void remove(F &function, int occurrence = 0) {
    function.code.erase(function.code.begin() + at<T>(function, occurrence));
}
void accept(const std::string &name, Module module) {
    require(!X86Emitter{}.emit(validate(std::move(module))).empty(), name + ": empty assembly");
    ++accepted;
    std::cout << "PASS borrowed object IR " << name << '\n';
}
void reject(const std::string &name,
            Module module,
            const std::function<void(Module &)> &change,
            const std::string &diagnostic) {
    change(module);
    try {
        (void)validate(std::move(module));
    } catch (const Error &error) {
        require(std::string(error.what()).find(diagnostic) != std::string::npos,
                name + ": wrong diagnostic: " + error.what());
        ++rejected;
        std::cout << "PASS borrowed object IR " << name << '\n';
        return;
    }
    throw Error(name + ": malformed IR accepted");
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
    function.receiver = Receiver{"Buffer", mutableValue, false, true};
    function.borrowedParameter = true;
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
                        BorrowedCall{"borrow_buffer", 48, 1},
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
    op<BorrowedCall>(caller).receiverOffset = 88;
    op<EndObject>(caller, 1).offset = 88;
    return module;
}
Module constructed() {
    auto module = fixture();
    auto &caller = module.functions[0];
    caller.parameters = {Type::ByteRegion};
    caller.code.erase(caller.code.begin() + 1);
    before<AcquireObjectLoan>(caller,
                              {BeginBytes{248},
                               Constant{1, Type::I64},
                               AllocateBytes{8, 248},
                               BeginObject{48},
                               ResourceCall{"construct_buffer", 8, {0, 248}, 0, 48},
                               EndBytes{248}});
    F constructor;
    constructor.name = "construct_buffer";
    constructor.result = Type::I64;
    constructor.receiver = Receiver{"Buffer", true, true, true};
    constructor.parameters = {Type::ByteRegion, Type::OwnedBytes};
    constructor.frameBytes = 48;
    constructor.regionSlots = {8};
    constructor.byteSlots = {{40, true}};
    constructor.code = {BindRegionParameter{0, 8},
                        BindBytesParameter{1, 40},
                        InitializeBytesField{0, 0, 40},
                        Constant{41, Type::I64},
                        ReceiverStore{1, Type::I64},
                        EndBytes{40},
                        Constant{0, Type::I64},
                        Return{}};
    module.functions.push_back(constructor);
    return module;
}
F viewMethod() {
    F view;
    view.name = "view_buffer";
    view.result = Type::ByteSpan;
    view.receiver = Receiver{"Buffer", false, false, true};
    view.receiverSpanField = 0;
    view.frameBytes = 64;
    view.spanSlots = {56};
    view.code = {BorrowOwnedSpan{0, 0, 56}, ReturnSpan{56}};
    return view;
}
Module forwarded(bool outerMutable, bool innerMutable) {
    auto module = fixture(outerMutable);
    auto inner = borrowed(innerMutable);
    inner.name = "borrow_leaf";
    named(module, "borrow_buffer").code = {
        AcquireObjectLoan{2, 0, innerMutable}, BorrowedCall{"borrow_leaf", 0, 2}, ReleaseObjectLoan{2}, Return{}};
    module.functions.push_back(inner);
    return module;
}
Module mixed() {
    auto module = fixture();
    module.enumCases["Mode"] = 2;
    const auto mode = Type::enumeration("Mode");
    auto &caller = named(module, "borrow_entry");
    caller.parameters.push_back(Type("Buffer"));
    caller.code.insert(caller.code.begin() + 2, BindOwnedObjectParameter{2, 88, "Buffer"});
    before<AcquireObjectLoan>(caller,
                              {BeginObject{96},
                               Constant{53, Type::I64},
                               Store{96, Type::I64},
                               BeginObject{104},
                               BorrowOwnedSpan{88, 0, 160}});
    before<BorrowedCall>(
        caller, {Constant{19, Type::I64}, Push{}, EnumConstant{mode, 1}, Push{}, Constant{251, Type::U8}, Push{}});
    op<BorrowedCall>(caller).objectArguments = {0, 0, 96, 0, 0};
    op<BorrowedCall>(caller).spanArguments = {0, 0, 0, 160, 0};
    op<BorrowedCall>(caller).resultOffset = 104;
    before<EndObject>(caller, {Load{104, Type::I64}, EndSpan{160}, EndObject{88}, EndObject{96}, EndObject{104}});
    auto &target = named(module, "borrow_buffer");
    target.result = Type("Word");
    target.parameters = {Type::I64, mode, Type("Word"), Type::ByteSpan, Type::U8};
    target.frameBytes = 96;
    target.slots = {{8, Type::I64}, {16, mode}, {24, Type::I64}, {88, Type::U8}};
    target.objectSlots = {{24, {"Word", false}}};
    target.spanSlots = {80};
    target.code = {BindParameter{0, 8, Type::I64},
                   BindParameter{1, 16, mode},
                   BindObjectParameter{2, 24, "Word"},
                   BindSpanParameter{3, 80},
                   BindParameter{4, 88, Type::U8},
                   MethodCall{"write_buffer", 0},
                   EndSpan{80},
                   ReturnObject{24}};
    return module;
}
Module composed(bool mutableLoan) {
    auto module = fixture(mutableLoan);
    // Replacing the scalar with a copyable child leaves the physical layout
    // unchanged but requires separate logical completion and projection authority.
    module.classFields["Buffer"][1].elementType = Type("Word");
    for (bool writing : {false, true}) {
        auto &method = named(module, writing ? "write_buffer" : "read_buffer");
        method.frameBytes = 16;
        method.slots = {{8, Type::I64}};
        method.objectSlots = {{8, {"Word", false}}};
        method.code = {BeginObject{8}};
        if (writing)
            method.code.insert(method.code.end(),
                               {Constant{41, Type::I64}, Store{8, Type::I64}, AssignObjectField{0, 1, 8}});
        else
            method.code.push_back(ObjectFieldCopy{0, 1, 8});
        method.code.insert(method.code.end(), {Load{8, Type::I64}, EndObject{8}, Return{}});
    }
    auto &caller = module.functions[0];
    before<AcquireObjectLoan>(caller, {BeginObject{96}, Constant{53, Type::I64}, Store{96, Type::I64}});
    before<EndObject>(caller, {EndObject{96}});
    return module;
}
void loanTests() {
    accept("mutable local root", fixture());
    accept("shared local root", fixture(false));
    accept("shared loan of const local", constLocal());
    accept("public owning constructor then synchronous borrow", constructed());
    accept("mutable formal forwards mutable loan", forwarded(true, true));
    accept("mutable formal forwards shared loan", forwarded(true, false));
    accept("shared formal forwards shared loan", forwarded(false, false));
    accept("five remaining scalar enum class span parameters and copied result", mixed());
    const auto check =
        [](const std::string &name, const std::function<void(Module &)> &change, const std::string &diagnostic) {
            reject(name, fixture(), change, diagnostic);
        };
    check(
        "call missing acquire",
        [](Module &m) {
            remove<AcquireObjectLoan>(m.functions[0]);
        },
        "borrowed call requires active loan");
    check(
        "call wrong loan identity",
        [](Module &m) {
            op<BorrowedCall>(m.functions[0]).loanId = 2;
        },
        "borrowed call requires active loan");
    for (int identity : {0, -1})
        check(
            "invalid loan identity " + std::to_string(identity),
            [=](Module &m) {
                op<AcquireObjectLoan>(m.functions[0]).loanId = identity;
            },
            "invalid or duplicate object loan identity");
    check(
        "duplicate loan identity",
        [](Module &m) {
            before<BorrowedCall>(m.functions[0], {AcquireObjectLoan{1, 48, true}});
        },
        "invalid or duplicate object loan identity");
    check(
        "second mutable loan same root",
        [](Module &m) {
            before<BorrowedCall>(m.functions[0], {AcquireObjectLoan{2, 48, true}});
        },
        "object access conflicts with active synchronous loan");
    check(
        "shared acquisition during mutable loan",
        [](Module &m) {
            before<BorrowedCall>(m.functions[0], {AcquireObjectLoan{2, 48, false}});
        },
        "object access conflicts with active synchronous loan");
    reject(
        "mutable acquisition during shared loan",
        fixture(false),
        [](Module &m) {
            before<BorrowedCall>(m.functions[0], {AcquireObjectLoan{2, 48, true}});
        },
        "object access conflicts with active synchronous loan");
    check(
        "negative root",
        [](Module &m) {
            op<AcquireObjectLoan>(m.functions[0]).root = -1;
        },
        "invalid borrowed object root");
    check(
        "interior root",
        [](Module &m) {
            op<AcquireObjectLoan>(m.functions[0]).root = 40;
        },
        "copy requires exact object slot");
    check(
        "scalar leaf cannot be a root",
        [](Module &m) {
            op<AcquireObjectLoan>(m.functions[0]).root = 16;
        },
        "copy requires exact object slot");
    check(
        "unbound root zero",
        [](Module &m) {
            op<AcquireObjectLoan>(m.functions[0]).root = 0;
        },
        "root zero loan requires named borrowed formal");
    check(
        "inactive root",
        [](Module &m) {
            op<AcquireObjectLoan>(m.functions[0]).root = 88;
        },
        "copy object outside active lifetime");
    check(
        "pristine root",
        [](Module &m) {
            before<AcquireObjectLoan>(m.functions[0], {BeginObject{88}});
            op<AcquireObjectLoan>(m.functions[0]).root = 88;
        },
        "copy source object not fully initialized");
    check(
        "consumed root",
        [](Module &m) {
            before<AcquireObjectLoan>(m.functions[0], {BeginObject{88}, MoveObject{48, 88}});
        },
        "owning object does not hold complete live ownership");
    check(
        "copyable root",
        [](Module &m) {
            before<AcquireObjectLoan>(m.functions[0], {BeginObject{96}, Constant{1, Type::I64}, Store{96, Type::I64}});
            op<AcquireObjectLoan>(m.functions[0]).root = 96;
            op<AcquireObjectLoan>(m.functions[0]).mutableValue = false;
        },
        "object loan requires exact owning root");
    reject(
        "const local cannot supply mutable loan",
        constLocal(true),
        [](Module &) {
        },
        "const object cannot supply mutable object loan");
    check(
        "same-layout wrong nominal target",
        [](Module &m) {
            named(m, "borrow_buffer").receiver->className = "Other";
        },
        "borrowed call root, lifetime, nominal type or authority mismatch");
    check(
        "call substitutes different root",
        [](Module &m) {
            op<BorrowedCall>(m.functions[0]).receiverOffset = 88;
        },
        "borrowed call root, lifetime, nominal type or authority mismatch");
    check(
        "call substitutes interior root",
        [](Module &m) {
            op<BorrowedCall>(m.functions[0]).receiverOffset = 40;
        },
        "borrowed call root, lifetime, nominal type or authority mismatch");
    check(
        "mutable loan cannot call shared target",
        [](Module &m) {
            named(m, "borrow_buffer").receiver->mutableValue = false;
        },
        "borrowed call root, lifetime, nominal type or authority mismatch");
    reject(
        "shared loan cannot call mutable target",
        fixture(false),
        [](Module &m) {
            named(m, "borrow_buffer").receiver->mutableValue = true;
        },
        "borrowed call root, lifetime, nominal type or authority mismatch");
    check(
        "release before call",
        [](Module &m) {
            before<BorrowedCall>(m.functions[0], {ReleaseObjectLoan{1}});
        },
        "object loan release requires completed borrowed call");
    check(
        "release unknown identity",
        [](Module &m) {
            op<ReleaseObjectLoan>(m.functions[0]).loanId = 2;
        },
        "release requires active object loan");
    check(
        "duplicate release",
        [](Module &m) {
            before<EndObject>(m.functions[0], {ReleaseObjectLoan{1}});
        },
        "release requires active object loan");
    check(
        "loan used twice",
        [](Module &m) {
            before<ReleaseObjectLoan>(m.functions[0], {BorrowedCall{"borrow_buffer", 48, 1}});
        },
        "object loan already used by a call");
    check(
        "stale call after release",
        [](Module &m) {
            before<EndObject>(m.functions[0], {BorrowedCall{"borrow_buffer", 48, 1}});
        },
        "borrowed call requires active loan");
    check(
        "stale lifetime cannot restart while loan active",
        [](Module &m) {
            before<BorrowedCall>(m.functions[0], {EndObject{48}, BeginObject{48}});
        },
        "object access conflicts with active synchronous loan");
    reject(
        "shared formal cannot escalate acquisition",
        forwarded(false, true),
        [](Module &m) {
            // Validate the callee body directly; the outer shared call is otherwise valid.
            (void)m;
        },
        "shared formal cannot supply mutable object loan");
}
void aliasTests() {
    const std::vector<std::pair<std::string, std::vector<Instruction>>> reads = {
        {"scalar read", {Load{16, Type::I64}}},
        {"byte status", {BytesOk{48, 0}}},
        {"byte length", {BytesLength{48, 0}}},
        {"byte load", {Constant{0, Type::I64}, BytesLoad{48, 0}}},
        {"readonly method", {MethodCall{"read_buffer", 48}}},
        {"new readonly span", {BorrowOwnedSpan{48, 0, 160}}}};
    for (const auto &[name, code] : reads)
        reject(
            "mutable loan excludes later " + name,
            fixture(),
            [&](Module &m) {
                auto &f = m.functions[0];
                f.code.insert(f.code.begin() + at<BorrowedCall>(f), code.begin(), code.end());
            },
            "object access conflicts with active synchronous loan");
    const std::vector<std::pair<std::string, std::vector<Instruction>>> writes = {
        {"scalar write", {Constant{7, Type::I64}, Store{16, Type::I64}}},
        {"byte write", {Constant{0, Type::I64}, Push{}, Constant{7, Type::U8}, BytesStore{48, 0}}},
        {"byte resize", {Constant{65, Type::I64}, BytesResize{48, 0}}},
        {"mutable method", {MethodCall{"write_buffer", 48}}},
        {"move", {BeginObject{88}, MoveObject{48, 88}}},
        {"drop", {EndObject{48}}}};
    for (bool mutableLoan : {false, true})
        for (const auto &[name, code] : writes)
            reject(
                std::string(mutableLoan ? "mutable" : "shared") + " loan excludes later " + name,
                fixture(mutableLoan),
                [&](Module &m) {
                    auto &f = m.functions[0];
                    f.code.insert(f.code.begin() + at<BorrowedCall>(f), code.begin(), code.end());
                },
                "object access conflicts with active synchronous loan");
    for (bool mutableLoan : {false, true}) {
        reject(
            std::string(mutableLoan ? "mutable" : "shared") + " loan excludes indexed scalar write",
            fixture(mutableLoan),
            [](Module &m) {
                before<AcquireObjectLoan>(m.functions[0],
                                          {Constant{0, Type::I64}, BoundsGuard{16, 1, Type::I64}, Push{}});
                before<BorrowedCall>(m.functions[0], {Constant{7, Type::I64}, IndexStore{16, 1, Type::I64}});
            },
            "object access conflicts with active synchronous loan");
        auto child = composed(mutableLoan);
        accept(std::string(mutableLoan ? "mutable" : "shared") + " owning root with copied child", child);
        reject(
            std::string(mutableLoan ? "mutable" : "shared") + " loan excludes copied child replacement",
            child,
            [](Module &m) {
                before<BorrowedCall>(m.functions[0], {AssignObjectField{48, 1, 96}});
            },
            "object access conflicts with active synchronous loan");
        reject(
            std::string(mutableLoan ? "mutable" : "shared") + " loan excludes ResourceCall consumption",
            fixture(mutableLoan),
            [](Module &m) {
                F consume = entry();
                consume.name = "consume_buffer";
                consume.code.insert(consume.code.end(), {EndObject{48}, Constant{0, Type::I64}, Return{}});
                m.functions.push_back(consume);
                before<BorrowedCall>(m.functions[0], {ResourceCall{"consume_buffer", 8, {0, 48}, 0}});
            },
            "object access conflicts with active synchronous loan");
    }
    auto laterView = fixture(false);
    before<BorrowedCall>(laterView.functions[0], {BorrowOwnedSpan{48, 0, 160}});
    before<EndObject>(laterView.functions[0], {SpanLength{160}, EndSpan{160}});
    accept("shared self-derived later view survives synchronous call", laterView);
    auto sharedReads = fixture(false);
    before<BorrowedCall>(sharedReads.functions[0],
                         {Load{16, Type::I64}, BytesLength{48, 0}, MethodCall{"read_buffer", 48}});
    accept("shared loan allows later scalar resource and method reads", sharedReads);
    auto independent = fixture();
    auto &caller = independent.functions[0];
    caller.parameters.push_back(Type("Buffer"));
    caller.code.insert(caller.code.begin() + 2, BindOwnedObjectParameter{2, 88, "Buffer"});
    before<BorrowedCall>(caller, {MethodCall{"write_buffer", 88}, BytesLength{88, 0}});
    before<EndObject>(caller, {EndObject{88}});
    accept("later mutation of independent root", independent);
    auto sharedView = fixture(false);
    before<AcquireObjectLoan>(sharedView.functions[0], {BorrowOwnedSpan{48, 0, 160}});
    before<BorrowedCall>(sharedView.functions[0], {SpanLength{160}});
    before<EndObject>(sharedView.functions[0], {EndSpan{160}});
    accept("shared loan coexists with exact existing readonly view", sharedView);
    reject(
        "mutable acquisition conflicts with existing view",
        fixture(),
        [](Module &m) {
            before<AcquireObjectLoan>(m.functions[0], {BorrowOwnedSpan{48, 0, 160}});
        },
        "owned byte or root mutation with live readonly span");
    auto twoShared = fixture(false);
    before<BorrowedCall>(twoShared.functions[0], {AcquireObjectLoan{2, 48, false}});
    before<EndObject>(twoShared.functions[0], {BorrowedCall{"borrow_buffer", 48, 2}, ReleaseObjectLoan{2}});
    accept("overlapping shared loans each consumed once", twoShared);
    auto sequential = fixture();
    before<EndObject>(sequential.functions[0],
                      {AcquireObjectLoan{1, 48, true}, BorrowedCall{"borrow_buffer", 48, 1}, ReleaseObjectLoan{1}});
    accept("released identity can name a new synchronous interval", sequential);
    reject(
        "completed call still protects root until release",
        fixture(),
        [](Module &m) {
            before<ReleaseObjectLoan>(m.functions[0], {MethodCall{"read_buffer", 48}});
        },
        "object access conflicts with active synchronous loan");
}
void authorityTests() {
    const auto check =
        [](const std::string &name, const std::function<void(Module &)> &change, const std::string &diagnostic) {
            reject(name, fixture(), change, diagnostic);
        };
    check(
        "borrowed call cannot target ordinary method",
        [](Module &m) {
            op<BorrowedCall>(m.functions[0]).callee = "write_buffer";
        },
        "borrowed call requires borrowed formal target");
    check(
        "regular method call cannot bypass acquisition",
        [](Module &m) {
            auto &f = m.functions[0];
            f.code[at<BorrowedCall>(f)] = MethodCall{"borrow_buffer", 48};
        },
        "method call cannot target borrowed free function");
    check(
        "plain call cannot bypass hidden formal",
        [](Module &m) {
            auto &f = m.functions[0];
            f.code[at<BorrowedCall>(f)] = Call{"borrow_buffer"};
        },
        "plain call cannot target receiver");
    check(
        "aggregate call cannot bypass hidden formal",
        [](Module &m) {
            auto &f = m.functions[0];
            f.code[at<BorrowedCall>(f)] = AggregateCall{"borrow_buffer", {}, 0};
        },
        "aggregate call cannot target receiver");
    check(
        "resource call cannot bypass hidden formal",
        [](Module &m) {
            auto &f = m.functions[0];
            f.code[at<BorrowedCall>(f)] = ResourceCall{"borrow_buffer", 8, {}, 0};
        },
        "resource call requires ordinary resource signature or owning constructor");
    reject(
        "source-free call cannot invoke private owning constructor",
        constructed(),
        [](Module &m) {
            named(m, "construct_buffer").receiver->publicAccess = false;
        },
        "private constructor requires lexical class authority");
    auto viewed = fixture(false);
    auto &viewCaller = named(viewed, "borrow_buffer");
    viewCaller.frameBytes = 64;
    viewCaller.spanSlots = {56};
    viewCaller.code = {MethodCall{"view_buffer", 0, {}, 56}, SpanLength{56}, EndSpan{56}, Return{}};
    viewed.functions.push_back(viewMethod());
    accept("borrowed formal can use verified public readonly view", viewed);
    auto blockedView = forwarded(true, true);
    auto &blockedCaller = named(blockedView, "borrow_buffer");
    blockedCaller.frameBytes = 64;
    blockedCaller.spanSlots = {56};
    before<AcquireObjectLoan>(blockedCaller, {MethodCall{"view_buffer", 0, {}, 56}});
    before<Return>(blockedCaller, {EndSpan{56}});
    blockedView.functions.push_back(viewMethod());
    reject(
        "live public view blocks forwarding mutable formal",
        blockedView,
        [](Module &) {
        },
        "owned byte or root mutation with live readonly span");
    check(
        "borrowed free body cannot call private method",
        [](Module &m) {
            named(m, "write_buffer").receiver->publicAccess = false;
        },
        "private method requires lexical class authority");
    auto lexical = fixture();
    auto privateMethod = method(true);
    privateMethod.name = "private_write";
    privateMethod.receiver->publicAccess = false;
    named(lexical, "write_buffer").code = {MethodCall{"private_write", 0}, Return{}};
    lexical.functions.push_back(privateMethod);
    accept("public lexical wrapper may call private implementation", lexical);
    reject(
        "free caller cannot use private local-root method",
        fixture(),
        [](Module &m) {
            named(m, "read_buffer").receiver->publicAccess = false;
            before<AcquireObjectLoan>(m.functions[0], {MethodCall{"read_buffer", 48}});
        },
        "private method requires lexical class authority");
    const std::vector<std::pair<std::string, std::vector<Instruction>>> direct = {
        {"scalar load", {ReceiverLoad{1, Type::I64}, Return{}}},
        {"scalar store", {Constant{1, Type::I64}, ReceiverStore{1, Type::I64}, Return{}}},
        {"resource length", {BytesLength{0, 0}, Return{}}},
        {"resource status", {BytesOk{0, 0}, Constant{0, Type::I64}, Return{}}},
        {"resource read", {Constant{0, Type::I64}, BytesLoad{0, 0}, Constant{0, Type::I64}, Return{}}},
        {"resource write",
         {Constant{0, Type::I64}, Push{}, Constant{7, Type::U8}, BytesStore{0, 0}, Constant{0, Type::I64}, Return{}}},
        {"resource resize", {Constant{65, Type::I64}, BytesResize{0, 0}, Constant{0, Type::I64}, Return{}}},
        {"raw view", {BorrowOwnedSpan{0, 0, 56}, SpanLength{56}, EndSpan{56}, Return{}}},
        {"nested projection", {ObjectFieldCopy{0, 1, 8}, Constant{0, Type::I64}, Return{}}},
        {"array access", {Constant{0, Type::I64}, ReceiverBoundsGuard{1}, Return{}}},
        {"array write", {Constant{7, Type::I64}, ReceiverIndexStore{1}, Return{}}},
        {"copied child assignment", {AssignObjectField{0, 1, 8}, Constant{0, Type::I64}, Return{}}},
        {"copied child initialization", {InitializeObjectField{0, 1, 8}, Constant{0, Type::I64}, Return{}}}};
    for (const auto &[name, code] : direct)
        check(
            "borrowed free formal denies direct " + name,
            [&](Module &m) {
                auto &target = named(m, "borrow_buffer");
                target.frameBytes = 64;
                target.spanSlots = {56};
                target.code = code;
            },
            "borrowed free formal grants no direct receiver field authority");
    reject(
        "shared free formal cannot call mutable public method",
        fixture(false),
        [](Module &m) {
            op<MethodCall>(named(m, "borrow_buffer")).callee = "write_buffer";
        },
        "const receiver cannot forward mutable capability");
    reject(
        "ordinary lexical method cannot mint named-formal loan",
        fixture(),
        [](Module &m) {
            auto &method = named(m, "write_buffer");
            method.code.insert(method.code.begin(), AcquireObjectLoan{2, 0, true});
        },
        "root zero loan requires named borrowed formal");
    check(
        "borrowed formal cannot be missing receiver metadata",
        [](Module &m) {
            named(m, "borrow_buffer").receiver.reset();
            m.functions.erase(m.functions.begin());
        },
        "borrowed formal requires nonconstructor owning receiver shape");
    check(
        "borrowed formal cannot have constructor metadata",
        [](Module &m) {
            named(m, "borrow_buffer").receiver->constructor = true;
            m.functions.erase(m.functions.begin());
        },
        "borrowed formal requires nonconstructor owning receiver shape");
    check(
        "borrowed formal cannot name copyable class",
        [](Module &m) {
            named(m, "borrow_buffer").receiver->className = "Word";
            m.functions.erase(m.functions.begin());
        },
        "borrowed formal requires nonconstructor owning receiver shape");
    for (const auto &type : {Type::OwnedBytes, Type("Buffer"), Type::ByteSpan})
        check(
            "borrowed formal cannot return " + typeName(type),
            [=](Module &m) {
                named(m, "borrow_buffer").result = type;
                m.functions.erase(m.functions.begin());
            },
            "borrowed formal cannot have resource or borrowed result");
    for (const auto &type : {Type::ByteRegion, Type::OwnedBytes, Type("Buffer")})
        check(
            "borrowed formal cannot take extra " + typeName(type),
            [=](Module &m) {
                named(m, "borrow_buffer").parameters = {type};
                m.functions.erase(m.functions.begin());
            },
            "borrowed formal cannot have resource or borrowed result");
    check(
        "hidden formal counts toward six-parameter limit",
        [](Module &m) {
            named(m, "borrow_buffer").parameters.assign(6, Type::I64);
            m.functions.erase(m.functions.begin());
        },
        "borrowed formal counts toward six parameters");
    check(
        "borrowed formal cannot claim escaping field summary",
        [](Module &m) {
            named(m, "borrow_buffer").receiverSpanField = 0;
            m.functions.erase(m.functions.begin());
        },
        "borrowed formal cannot have resource or borrowed result");
}
void argumentTests() {
    const auto check =
        [](const std::string &name, const std::function<void(Module &)> &change, const std::string &diagnostic) {
            reject(name, mixed(), change, diagnostic);
        };
    check(
        "copied result cannot overlap borrowed root",
        [](Module &m) {
            op<BorrowedCall>(m.functions[0]).resultOffset = 48;
        },
        "method result aliases receiver");
    check(
        "copied result cannot overlap copied argument",
        [](Module &m) {
            op<BorrowedCall>(m.functions[0]).resultOffset = 96;
        },
        "method result aliases argument snapshot");
    check(
        "copied result must have exact storage",
        [](Module &m) {
            op<BorrowedCall>(m.functions[0]).resultOffset = 103;
        },
        "method result requires exact object slot");
    check(
        "copied result must be pristine",
        [](Module &m) {
            before<AcquireObjectLoan>(m.functions[0], {Constant{1, Type::I64}, Store{104, Type::I64}});
        },
        "method result requires uninitialized object");
    check(
        "short copied argument vector",
        [](Module &m) {
            op<BorrowedCall>(m.functions[0]).objectArguments.pop_back();
        },
        "receiver object argument vector size mismatch");
    check(
        "missing span vector",
        [](Module &m) {
            op<BorrowedCall>(m.functions[0]).spanArguments.clear();
        },
        "method span argument vector size mismatch");
    check(
        "scalar parameter cannot name storage",
        [](Module &m) {
            op<BorrowedCall>(m.functions[0]).objectArguments[0] = 96;
        },
        "scalar receiver argument cannot name object storage");
    check(
        "span parameter cannot name object",
        [](Module &m) {
            op<BorrowedCall>(m.functions[0]).objectArguments[3] = 96;
        },
        "span method argument cannot name object storage");
    check(
        "copied argument cannot alias receiver",
        [](Module &m) {
            op<BorrowedCall>(m.functions[0]).objectArguments[2] = 48;
        },
        "receiver aliases argument snapshot");
    check(
        "copied argument must be readonly snapshot",
        [](Module &m) {
            m.functions[0].objectSlots[96].mutableValue = true;
        },
        "receiver argument snapshot must be readonly");
    check(
        "span argument must remain active",
        [](Module &m) {
            before<BorrowedCall>(m.functions[0], {EndSpan{160}});
        },
        "span capability is not active");
    check(
        "wrong scalar stack type",
        [](Module &m) {
            auto &f = m.functions[0];
            f.code[at<BorrowedCall>(f) - 2] = Constant{251, Type::I64};
        },
        "method argument type mismatch");
    reject(
        "scalar result cannot name object storage",
        fixture(),
        [](Module &m) {
            op<BorrowedCall>(m.functions[0]).resultOffset = 104;
        },
        "scalar method result cannot name object storage");
}
void graphTests() {
    auto join = forwarded(true, true);
    auto &f = named(join, "borrow_buffer");
    f.code = {AcquireObjectLoan{2, 0, true},
              Constant{1, Type::Bool},
              BranchFalse{1},
              Constant{7, Type::I64},
              Jump{2},
              Label{1},
              Constant{8, Type::I64},
              Label{2},
              BorrowedCall{"borrow_leaf", 0, 2},
              ReleaseObjectLoan{2},
              Return{}};
    accept("unchanged prepared loan survives control-flow join", join);
    auto bothPaths = join;
    auto &both = named(bothPaths, "borrow_buffer");
    remove<AcquireObjectLoan>(both);
    before<Jump>(both, {AcquireObjectLoan{2, 0, true}});
    before<Label>(both, {AcquireObjectLoan{2, 0, true}}, 1);
    accept("equal root and authority loans acquired on both predecessors", bothPaths);
    reject(
        "join rejects loan on only one predecessor",
        join,
        [](Module &m) {
            auto &f = named(m, "borrow_buffer");
            remove<AcquireObjectLoan>(f);
            before<Jump>(f, {AcquireObjectLoan{2, 0, true}});
        },
        "incompatible object loans at control-flow join");
    reject(
        "join rejects different loan identities",
        join,
        [](Module &m) {
            auto &f = named(m, "borrow_buffer");
            remove<AcquireObjectLoan>(f);
            before<Jump>(f, {AcquireObjectLoan{2, 0, true}});
            before<Label>(f, {AcquireObjectLoan{3, 0, true}}, 1);
        },
        "incompatible object loans at control-flow join");
    reject(
        "join rejects called versus uncalled loan",
        join,
        [](Module &m) {
            before<Jump>(named(m, "borrow_buffer"), {BorrowedCall{"borrow_leaf", 0, 2}});
        },
        "incompatible object loans at control-flow join");
    auto loop = fixture();
    auto &loopCaller = loop.functions[0];
    before<AcquireObjectLoan>(loopCaller, {Label{1}});
    before<EndObject>(loopCaller,
                      {Constant{0, Type::Bool}, BranchFalse{2}, Jump{1}, Label{2}, Constant{41, Type::I64}});
    accept("closed synchronous loans permit loop backedge", loop);
    reject(
        "loop backedge cannot carry completed loan",
        forwarded(true, true),
        [](Module &m) {
            named(m, "borrow_buffer").code = {
                Label{1}, AcquireObjectLoan{2, 0, true}, BorrowedCall{"borrow_leaf", 0, 2}, Jump{1}};
        },
        "incompatible object loans at control-flow join");
    reject(
        "scalar return cannot retain uncalled loan",
        forwarded(true, true),
        [](Module &m) {
            named(m, "borrow_buffer").code = {AcquireObjectLoan{2, 0, true}, Constant{0, Type::I64}, Return{}};
        },
        "return with active synchronous object loan");
    reject(
        "scalar return cannot retain completed loan",
        forwarded(true, true),
        [](Module &m) {
            remove<ReleaseObjectLoan>(named(m, "borrow_buffer"));
        },
        "return with active synchronous object loan");
    reject(
        "copied return cannot retain completed loan",
        forwarded(true, true),
        [](Module &m) {
            auto &f = named(m, "borrow_buffer");
            f.result = Type("Word");
            f.frameBytes = 16;
            f.slots = {{8, Type::I64}};
            f.objectSlots = {{8, {"Word", false}}};
            f.code = {BeginObject{8},
                      Constant{1, Type::I64},
                      Store{8, Type::I64},
                      AcquireObjectLoan{2, 0, true},
                      BorrowedCall{"borrow_leaf", 0, 2},
                      ReturnObject{8}};
            m.functions.erase(m.functions.begin());
        },
        "return with active synchronous object loan");
    auto restarted = constructed();
    before<EndObject>(restarted.functions[0],
                      {EndObject{48},
                       BeginBytes{248},
                       Constant{1, Type::I64},
                       AllocateBytes{8, 248},
                       BeginObject{48},
                       ResourceCall{"construct_buffer", 8, {0, 248}, 0, 48},
                       EndBytes{248},
                       AcquireObjectLoan{1, 48, true},
                       BorrowedCall{"borrow_buffer", 48, 1},
                       ReleaseObjectLoan{1}});
    accept("released loan permits same-slot new lifetime and fresh loan", restarted);
    reject(
        "same-slot new lifetime does not revive old loan",
        restarted,
        [](Module &m) {
            remove<AcquireObjectLoan>(m.functions[0], 1);
        },
        "borrowed call requires active loan");
    reject(
        "join rejects same root at different lifetime sites",
        constructed(),
        [](Module &m) {
            auto &f = m.functions[0];
            f.code.erase(f.code.begin() + at<AcquireObjectLoan>(f), f.code.end());
            f.code.insert(f.code.end(),
                          {Constant{1, Type::Bool},
                           BranchFalse{1},
                           AcquireObjectLoan{1, 48, true},
                           Jump{2},
                           Label{1},
                           EndObject{48},
                           BeginBytes{248},
                           Constant{1, Type::I64},
                           AllocateBytes{8, 248},
                           BeginObject{48},
                           ResourceCall{"construct_buffer", 8, {0, 248}, 0, 48},
                           EndBytes{248},
                           AcquireObjectLoan{1, 48, true},
                           Label{2},
                           BorrowedCall{"borrow_buffer", 48, 1},
                           ReleaseObjectLoan{1},
                           EndObject{48},
                           Return{}});
        },
        // Root creation sites are checked before owning fields and active loans.
        "incompatible active object lifetimes at control-flow join");
    reject(
        "direct borrowed recursion",
        forwarded(true, true),
        [](Module &m) {
            op<BorrowedCall>(named(m, "borrow_buffer")).callee = "borrow_buffer";
        },
        "recursive receiver call cycle");
    reject(
        "indirect borrowed recursion",
        forwarded(true, true),
        [](Module &m) {
            named(m, "borrow_leaf").code = {
                AcquireObjectLoan{3, 0, true}, BorrowedCall{"borrow_buffer", 0, 3}, ReleaseObjectLoan{3}, Return{}};
        },
        "recursive receiver call cycle");
    reject(
        "scalar helpers cannot hide reachable receiver recursion",
        fixture(),
        [](Module &m) {
            named(m, "write_buffer").code = {Call{"scalar_helper"}, Return{}};
            F helper;
            helper.name = "scalar_helper";
            helper.result = Type::I64;
            helper.frameBytes = 16;
            helper.slots = {{8, Type::I64}};
            helper.objectSlots = {{8, {"Word", false}}};
            helper.code = {BeginObject{8},
                           Constant{1, Type::I64},
                           Store{8, Type::I64},
                           MethodCall{"word_bridge", 8},
                           EndObject{8},
                           Return{}};
            F bridge;
            bridge.name = "word_bridge";
            bridge.result = Type::I64;
            bridge.receiver = Receiver{"Word", false, false};
            bridge.code = {Call{"scalar_helper"}, Return{}};
            m.functions.push_back(helper);
            m.functions.push_back(bridge);
        },
        "recursive receiver call cycle");
    reject(
        "private lexical graph cycle remains rejected",
        fixture(),
        [](Module &m) {
            auto a = method(true);
            a.name = "private_a";
            a.receiver->publicAccess = false;
            auto b = a;
            b.name = "private_b";
            a.code = {MethodCall{"private_b", 0}, Return{}};
            b.code = {MethodCall{"private_a", 0}, Return{}};
            named(m, "write_buffer").code = {MethodCall{"private_a", 0}, Return{}};
            m.functions.push_back(a);
            m.functions.push_back(b);
        },
        "recursive receiver call cycle");
    reject(
        "nested owning layout stays unsupported",
        fixture(),
        [](Module &m) {
            m.classLayouts["Nested"] = {Type::I64};
            m.classFields["Nested"] = {{Type("Buffer"), 0, 1, false}};
            m.classStorage.clear();
        },
        "nested owning class field is unsupported");
}
} // namespace
int main() {
    try {
        loanTests();
        aliasTests();
        authorityTests();
        argumentTests();
        graphTests();
        std::cout << "borrowed object IR: " << accepted << " valid, " << rejected << " rejected\n";
    } catch (const std::exception &error) {
        std::cerr << "FAIL borrowed object IR: " << error.what() << '\n';
        return 1;
    }
}
