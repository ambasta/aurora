// Independent direct-IR acceptance and rejection tests. No parser or lowering.
// --emit-native feeds handwritten ABI probes in short_circuit_ir_native.py.
#include "ir_verify.hpp"
#include "x86.hpp"
#include <functional>
#include <iostream>
#include <limits>
#include <string>

using namespace aurora;
using namespace aurora::ir;
using IRFunction = aurora::ir::Function;
namespace {
int accepted = 0, rejected = 0;
void check(bool condition, const std::string &message) {
    if (!condition) throw Error(message);
}
void append(IRFunction &f, std::initializer_list<Instruction> operations) {
    f.code.insert(f.code.end(), operations);
}
Module moduleWith(std::initializer_list<Instruction> code, Type result = Type::I64) {
    IRFunction f;
    f.name = "direct";
    f.result = result;
    f.code = code;
    Module m;
    m.functions.push_back(f);
    return m;
}
void accept(const std::string &name, Module m) {
    check(!X86Emitter{}.emit(validate(std::move(m))).empty(), name + ": empty assembly");
    ++accepted;
    std::cout << "PASS short-circuit IR " << name << '\n';
}
void rejection(const std::string &name, const std::function<void()> &operation,
               const std::string &diagnostic) {
    try {
        operation();
    } catch (const Error &error) {
        check(std::string(error.what()).find(diagnostic) != std::string::npos,
              name + ": wrong rejection: " + error.what());
        ++rejected;
        std::cout << "PASS short-circuit IR " << name << '\n';
        return;
    }
    throw Error(name + ": malformed IR accepted");
}
void reject(const std::string &name, Module m, const std::string &diagnostic) {
    rejection(name, [&] { (void)validate(std::move(m)); }, diagnostic);
}

// A real preserved scalar value, deliberately above both signed and unsigned
// 32-bit ranges. Python independently specifies the expected arithmetic.
constexpr std::int64_t prefixValue = 1099511627793LL;
const std::vector<std::string> callKinds = {
    "scalar", "aggregate", "aggregate_result", "method", "method_value",
    "method_result", "metadata", "span", "subspan"};
bool isMethod(const std::string &kind) { return kind.starts_with("method"); }

// Each probe's signature is verified before any assembly substitution. The
// Python side separately implements and checks its private record layout.
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
    aggregate.code = {BindObjectParameter{0, 16, "ProbeBox"},
                      BindParameter{1, 24, Type::Bool}, Load{24, Type::Bool}, Return{}};
    m.functions.push_back(aggregate);
    auto valueMethod = aggregate;
    valueMethod.name = "sc_probe_method_value";
    valueMethod.receiver = Receiver{"ProbeBox", true, false};
    m.functions.push_back(valueMethod);
    auto result = aggregate;
    result.name = "sc_probe_aggregate_result";
    result.result = Type("ProbeBox");
    result.code = {BindObjectParameter{0, 16, "ProbeBox"},
                   BindParameter{1, 24, Type::Bool}, ReturnObject{16}};
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
    span.code = {BindSpanParameter{0, 120}, BindParameter{1, 24, Type::Bool},
                 Load{24, Type::Bool}, EndSpan{120}, Return{}};
    m.functions.push_back(span);
    m.descriptors = {{17, {1, 0}}, {18, {0, 0}}};
    m.descriptorViews[0] = {17, 18};
}
void probe(IRFunction &f, const std::string &kind, int booleanSlot, int &label) {
    if (kind == "metadata") {
        const int no = label++, done = label++;
        append(f, {Load{booleanSlot, Type::Bool}, BranchFalse{no},
                   Constant{17, Type::I64}, Jump{done}, Label{no},
                   Constant{18, Type::I64}, Label{done}, MetadataQuery{Query::Size},
                   Push{}, Constant{0, Type::I64}, Compare{Comparison::NotEqual, Type::I64}});
        return;
    }
    if (kind == "subspan")
        append(f, {Constant{1, Type::I64}, Push{}, Constant{1, Type::I64}, Subspan{176, 232}});
    append(f, {Load{booleanSlot, Type::Bool}, Push{}});
    if (kind == "scalar") f.code.push_back(Call{"sc_probe_scalar"});
    else if (kind == "aggregate")
        f.code.push_back(AggregateCall{"sc_probe_aggregate", {40, 0}, 0});
    else if (kind == "method") f.code.push_back(MethodCall{"sc_probe_method", 56});
    else if (kind == "method_value")
        f.code.push_back(MethodCall{"sc_probe_method_value", 56, {40, 0}});
    else if (kind == "aggregate_result" || kind == "method_result") {
        f.code.push_back(BeginObject{112});
        if (kind == "aggregate_result")
            f.code.push_back(AggregateCall{"sc_probe_aggregate_result", {40, 0}, 112});
        else f.code.push_back(MethodCall{"sc_probe_method_result", 56, {40, 0}, 112});
        append(f, {Load{112, Type::I64}, Push{}, Constant{0, Type::I64},
                   Compare{Comparison::NotEqual, Type::I64}, EndObject{112}});
    } else if (kind == "span" || kind == "subspan") {
        f.code.push_back(AggregateCall{"sc_probe_span", {0, 0}, 0,
                                      {kind == "span" ? 176 : 232, 0}});
        if (kind == "subspan") f.code.push_back(EndSpan{232});
    } else throw Error("unknown native probe kind");
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
    append(f, {BranchFalse{no}, Constant{1, Type::I64}, Jump{done},
               Label{no}, Constant{0, Type::I64}, Label{done}});
}
IRFunction nativeFunction(const std::string &kind, const std::string &shape, int depth) {
    IRFunction f;
    f.name = "sc_" + kind + "_" + shape + "_" + std::to_string(depth);
    f.result = Type::I64;
    f.parameters = {Type::Bool, Type::Bool, Type::Bool};
    f.frameBytes = 240;
    f.slots = {{8, Type::Bool}, {16, Type::Bool}, {24, Type::Bool},
               {40, Type::I64}, {32, Type::I64}, {56, Type::I64}, {48, Type::I64},
               {112, Type::I64}, {104, Type::I64}};
    f.objectSlots = {{40, {"ProbeBox", false}}, {56, {"ProbeBox", true}},
                     {112, {"ProbeBox", false}}};
    f.code = {BindParameter{0, 8, Type::Bool}, BindParameter{1, 16, Type::Bool},
              BindParameter{2, 24, Type::Bool}, BeginObject{40},
              Constant{17, Type::I64}, Store{40, Type::I64},
              Constant{19, Type::I64}, Store{32, Type::I64}, BeginObject{56},
              Constant{23, Type::I64}, Store{56, Type::I64},
              Constant{29, Type::I64}, Store{48, Type::I64}};
    if (kind == "span" || kind == "subspan") {
        f.arraySlots = {{64, 3}};
        f.spanSlots = {176, 232};
        f.slots.insert({{64, Type::U8}, {63, Type::U8}, {62, Type::U8}});
        append(f, {BeginArray{64}, Constant{11, Type::U8}, Store{64, Type::U8},
                   Constant{22, Type::U8}, Store{63, Type::U8},
                   Constant{33, Type::U8}, Store{62, Type::U8}, BorrowSpan{64, 176}});
    }
    for (int n = 0; n < depth; ++n) append(f, {Constant{prefixValue + n, Type::I64}, Push{}});
    int label = 1;
    logical(f, kind, shape, label);
    if (kind == "span" || kind == "subspan") append(f, {EndSpan{176}, EndArray{64}});
    boolToInteger(f, label);
    if (isMethod(kind)) {
        // Native probes mutate a real authorized receiver field. Its observed
        // value distinguishes committed RHS effects from skipped calls.
        append(f, {Push{}, Load{48, Type::I64}, Push{}, Constant{100, Type::I64},
                   BinaryValue{Binary::CheckedMultiply}, BinaryValue{Binary::CheckedAdd}});
    }
    for (int n = 0; n < depth; ++n) f.code.push_back(BinaryValue{Binary::CheckedAdd});
    append(f, {EndObject{56}, EndObject{40}, Return{}});
    return f;
}
Module nativeModule() {
    Module m;
    addProbeSignatures(m);
    for (const auto &kind : callKinds)
        for (const auto &shape : {"and", "or", "nested"})
            for (int depth = 0; depth <= 3; ++depth)
                m.functions.push_back(nativeFunction(kind, shape, depth));
    // A checked local-index token remains below a complete nested bool result.
    IRFunction guard;
    guard.name = "sc_guarded_store";
    guard.result = Type::I64;
    guard.parameters = {Type::Bool, Type::Bool, Type::Bool};
    guard.frameBytes = 48;
    guard.slots = {{8, Type::Bool}, {16, Type::Bool}, {24, Type::Bool},
                   {40, Type::Bool}, {32, Type::Bool}};
    guard.code = {BindParameter{0, 8, Type::Bool}, BindParameter{1, 16, Type::Bool},
                  BindParameter{2, 24, Type::Bool}, Constant{0, Type::Bool},
                  Store{40, Type::Bool}, Store{32, Type::Bool}, Constant{1, Type::I64},
                  BoundsGuard{40, 2, Type::Bool}, Push{}};
    int label = 1;
    logical(guard, "scalar", "nested", label);
    append(guard, {IndexStore{40, 2, Type::Bool}, Load{32, Type::Bool}});
    boolToInteger(guard, label);
    guard.code.push_back(Return{});
    m.functions.push_back(guard);
    // The subspan offset is already stacked while its count's bool expression
    // branches and calls; this is a distinct consumer from ordinary arguments.
    auto window = nativeFunction("subspan", "nested", 0);
    window.name = "sc_window_count";
    window.code = {BindParameter{0, 8, Type::Bool}, BindParameter{1, 16, Type::Bool},
                   BindParameter{2, 24, Type::Bool}, BeginArray{64},
                   Constant{11, Type::U8}, Store{64, Type::U8},
                   Constant{22, Type::U8}, Store{63, Type::U8},
                   Constant{33, Type::U8}, Store{62, Type::U8}, BorrowSpan{64, 176},
                   Constant{1, Type::I64}, Push{}};
    label = 1;
    logical(window, "scalar", "nested", label);
    boolToInteger(window, label);
    append(window, {Subspan{176, 232}, SpanLength{232}, EndSpan{232}, EndSpan{176},
                    EndArray{64}, Return{}});
    m.functions.push_back(window);
    m.classLayouts["ProbeBits"] = {Type::Bool, Type::Bool};
    m.classFields["ProbeBits"] = {{Type::Bool, 0, 2, true}};
    auto receiverGuard = guard;
    receiverGuard.name = "sc_receiver_guard_method";
    receiverGuard.receiver = Receiver{"ProbeBits", true, false};
    receiverGuard.code = {BindParameter{0, 8, Type::Bool}, BindParameter{1, 16, Type::Bool},
        BindParameter{2, 24, Type::Bool}, Constant{1, Type::I64}, ReceiverBoundsGuard{0}, Push{}};
    label = 1;
    logical(receiverGuard, "scalar", "nested", label);
    receiverGuard.code.push_back(ReceiverIndexStore{0});
    boolToInteger(receiverGuard, label);
    receiverGuard.code.push_back(Return{});
    m.functions.push_back(receiverGuard);
    auto receiverCaller = guard;
    receiverCaller.name = "sc_receiver_guarded_store";
    receiverCaller.objectSlots = {{40, {"ProbeBits", true}}};
    receiverCaller.code = {BindParameter{0, 8, Type::Bool}, BindParameter{1, 16, Type::Bool},
        BindParameter{2, 24, Type::Bool}, BeginObject{40}, Constant{0, Type::Bool},
        Store{40, Type::Bool}, Store{32, Type::Bool}, Load{8, Type::Bool}, Push{},
        Load{16, Type::Bool}, Push{}, Load{24, Type::Bool}, Push{},
        MethodCall{"sc_receiver_guard_method", 40}, Load{32, Type::Bool}};
    label = 1;
    boolToInteger(receiverCaller, label);
    append(receiverCaller, {EndObject{40}, Return{}});
    m.functions.push_back(receiverCaller);
    for (const std::string trap : {"bounds", "overflow", "zero", "shift"}) {
        for (const std::string shape : {"and", "or"}) {
            for (int depth : {1, 2}) {
                IRFunction f;
                f.name = "sc_trap_" + trap + "_" + shape + "_" + std::to_string(depth);
                f.result = Type::I64;
                f.parameters = {Type::Bool, Type::Bool, Type::Bool};
                f.frameBytes = 48;
                f.slots = {{8, Type::Bool}, {16, Type::Bool}, {24, Type::Bool}, {40, Type::I64}};
                f.code = {BindParameter{0, 8, Type::Bool}, BindParameter{1, 16, Type::Bool},
                    BindParameter{2, 24, Type::Bool}, Constant{7, Type::I64}, Store{40, Type::I64}};
                for (int n = 0; n < depth; ++n)
                    append(f, {Constant{prefixValue + n, Type::I64}, Push{}});
                append(f, {Load{8, Type::Bool}, BranchFalse{1}});
                if (shape == "or")
                    append(f, {Constant{1, Type::Bool}, Jump{2}, Label{1}});
                if (trap == "bounds")
                    append(f, {Constant{1, Type::I64}, BoundsGuard{40, 1, Type::I64},
                        IndexLoad{40, 1, Type::I64}});
                else if (trap == "overflow")
                    append(f, {Constant{std::numeric_limits<std::int64_t>::max(), Type::I64},
                        Push{}, Constant{1, Type::I64}, BinaryValue{Binary::CheckedAdd}});
                else if (trap == "zero")
                    append(f, {Constant{42, Type::I64}, Push{}, Constant{0, Type::I64},
                        BinaryValue{Binary::CheckedDivide}});
                else
                    append(f, {Constant{1, Type::U64}, Push{}, Constant{64, Type::I64},
                        BinaryValue{Binary::ShiftLeft, Type::U64}, Convert{Type::U64, Type::I64}});
                append(f, {Push{}, Constant{0, Type::I64}, Compare{Comparison::NotEqual, Type::I64}});
                if (shape == "and")
                    append(f, {Jump{2}, Label{1}, Constant{0, Type::Bool}});
                f.code.push_back(Label{2});
                label = 3;
                boolToInteger(f, label);
                for (int n = 0; n < depth; ++n) f.code.push_back(BinaryValue{Binary::CheckedAdd});
                f.code.push_back(Return{});
                m.functions.push_back(f);
            }
        }
    }
    return m;
}

Module guardedJoin(bool receiver = false) {
    auto m = moduleWith({}, Type::Bool);
    auto &f = m.functions[0];
    f.frameBytes = 32;
    f.slots = {{8, Type::Bool}, {16, Type::Bool}, {24, Type::Bool}, {32, Type::Bool}};
    f.code = {Constant{0, Type::Bool}, Store{8, Type::Bool}, Store{16, Type::Bool},
              Store{24, Type::Bool}, Store{32, Type::Bool}, Constant{0, Type::I64}};
    if (receiver) {
        m.classLayouts["Bits"] = {Type::Bool, Type::Bool, Type::Bool, Type::Bool};
        m.classFields["Bits"] = {{Type::Bool, 0, 2, true}, {Type::Bool, 2, 2, true}};
        f.receiver = Receiver{"Bits", true, false};
        f.code.push_back(ReceiverBoundsGuard{0});
    } else f.code.push_back(BoundsGuard{16, 2, Type::Bool});
    append(f, {Push{}, Constant{1, Type::Bool}, BranchFalse{1},
               Constant{0, Type::Bool}, Jump{2}, Label{1}, Constant{1, Type::Bool}, Label{2}});
    if (receiver) f.code.push_back(ReceiverIndexStore{0});
    else f.code.push_back(IndexStore{16, 2, Type::Bool});
    f.code.push_back(Return{});
    return m;
}
Module lifetimeBase() {
    auto m = moduleWith({Constant{1, Type::I64}, Return{}});
    m.classLayouts["Box"] = {Type::I64};
    auto &f = m.functions[0];
    f.frameBytes = 192;
    f.slots = {{8, Type::U8}, {16, Type::U8}, {24, Type::I64}};
    f.arraySlots = {{8, 1}, {16, 1}};
    f.objectSlots = {{24, {"Box", false}}};
    f.spanSlots = {80, 136, 192};
    return m;
}
void directTests() {
    accept("nested native fixtures and every call shape", nativeModule());
    accept("preserved local bounds evidence", guardedJoin());
    accept("preserved receiver bounds evidence", guardedJoin(true));
    accept("nonempty stack through closed loop", moduleWith({
        Constant{99, Type::I64}, Push{}, Label{1}, Constant{0, Type::Bool},
        BranchFalse{2}, Jump{1}, Label{2}, Pop{}, Return{}}));
    accept("unreachable structural artifacts filtered", moduleWith({
        Constant{1, Type::I64}, Push{}, Jump{2}, Label{1}, Jump{2},
        Label{2}, Pop{}, Return{}}));
    const std::string stackJoin = "incompatible value/guard stacks";
    reject("different stack lengths", moduleWith({Constant{7, Type::I64}, Push{},
        Constant{1, Type::Bool}, BranchFalse{1}, Pop{}, Label{1},
        Pop{}, Return{}}), stackJoin);
    reject("different stack types", moduleWith({Constant{7, Type::I64}, Push{},
        Constant{1, Type::Bool}, BranchFalse{1}, Pop{}, Constant{1, Type::U64},
        Push{}, Label{1}, Pop{}, Constant{0, Type::I64}, Return{}}), stackJoin);
    auto ordered = moduleWith({Constant{1, Type::I64}, Push{}, Constant{1, Type::Bool},
        Push{}, BranchFalse{1}, Pop{}, Pop{}, Constant{1, Type::Bool}, Push{},
        Constant{1, Type::I64}, Push{}, Label{1}, Pop{}, Pop{}, Constant{0, Type::I64}, Return{}});
    reject("ordered stack types cannot be permuted", ordered, stackJoin);
    for (int variant = 0; variant != 3; ++variant) {
        auto m = guardedJoin();
        auto &f = m.functions[0];
        const std::vector<Instruction> changes = variant == 0
            ? std::vector<Instruction>{Pop{}, Constant{0, Type::I64}, Push{}}
            : std::vector<Instruction>{Pop{}, Constant{0, Type::I64},
                BoundsGuard{variant == 1 ? 32 : 16, variant == 1 ? 2 : 1, Type::Bool}, Push{}};
        f.code.insert(f.code.begin() + 10, changes.begin(), changes.end());
        reject("local guard mismatch " + std::to_string(variant), m, stackJoin);
    }
    for (int variant = 0; variant != 2; ++variant) {
        auto m = guardedJoin(true);
        auto &f = m.functions[0];
        std::vector<Instruction> changes{Pop{}, Constant{0, Type::I64}};
        if (variant == 0) changes.push_back(ReceiverBoundsGuard{1});
        else changes.push_back(BoundsGuard{16, 2, Type::Bool});
        changes.push_back(Push{});
        f.code.insert(f.code.begin() + 10, changes.begin(), changes.end());
        reject("receiver guard mismatch " + std::to_string(variant), m, stackJoin);
    }
    auto conditional = moduleWith({Constant{5, Type::I64}, Push{}, Constant{1, Type::Bool},
        BranchFalse{1}, Constant{9, Type::I64}, Store{8, Type::I64}, Label{1},
        Pop{}, Load{8, Type::I64}, Return{}});
    conditional.functions[0].frameBytes = 16;
    conditional.functions[0].slots = {{8, Type::I64}};
    reject("conditional store is not definite initialization", conditional, "load before initialization");
    auto duplicate = conditional;
    duplicate.classLayouts["Box"] = {Type::I64};
    duplicate.functions[0].objectSlots = {{8, {"Box", false}}};
    duplicate.functions[0].code.insert(duplicate.functions[0].code.begin(), BeginObject{8});
    duplicate.functions[0].code.insert(duplicate.functions[0].code.end() - 2, Store{8, Type::I64});
    reject("conditional store retains may-initialization", duplicate, "write to initialized const object field");
    for (const std::string lifetime : {"object", "array", "span"}) {
        auto m = lifetimeBase();
        auto &f = m.functions[0];
        if (lifetime == "object") f.code = {BeginObject{24}};
        else f.code = {BeginArray{8}, Constant{11, Type::U8}, Store{8, Type::U8}};
        if (lifetime == "span") f.code.push_back(BorrowSpan{8, 80});
        append(f, {Constant{7, Type::I64}, Push{}, Constant{1, Type::Bool}, BranchFalse{1}});
        if (lifetime == "object") f.code.push_back(EndObject{24});
        else if (lifetime == "array") f.code.push_back(EndArray{8});
        else f.code.push_back(EndSpan{80});
        append(f, {Label{1}, Pop{}});
        if (lifetime == "span") f.code.push_back(EndSpan{80});
        if (lifetime != "object") f.code.push_back(EndArray{8});
        f.code.push_back(Return{});
        reject("conditional " + lifetime + " lifetime end", m,
               "incompatible active " + lifetime);
    }
    auto restarted = lifetimeBase();
    restarted.functions[0].code = {BeginArray{8}, Constant{11, Type::U8}, Store{8, Type::U8},
        Constant{7, Type::I64}, Push{}, Constant{1, Type::Bool}, BranchFalse{1},
        EndArray{8}, BeginArray{8}, Constant{11, Type::U8}, Store{8, Type::U8},
        Label{1}, Pop{}, EndArray{8}, Return{}};
    reject("same array storage different lifetime site", restarted, "incompatible active array lifetimes");
    for (bool differentOrigin : {false, true}) {
        auto m = lifetimeBase();
        auto &f = m.functions[0];
        f.code = {BeginArray{8}, Constant{11, Type::U8}, Store{8, Type::U8},
            BeginArray{16}, Constant{22, Type::U8}, Store{16, Type::U8},
            Constant{7, Type::I64}, Push{}, Constant{1, Type::Bool}, BranchFalse{1},
            BorrowSpan{8, 80}, Jump{2}, Label{1}, BorrowSpan{differentOrigin ? 16 : 8, 80},
            Label{2}, Pop{}, EndSpan{80}, EndArray{16}, EndArray{8}, Return{}};
        reject(differentOrigin ? "different span root origins" : "different span creation sites", m,
               "incompatible active span capabilities");
    }
    auto parent = lifetimeBase();
    parent.functions[0].code = {BeginArray{8}, Constant{11, Type::U8}, Store{8, Type::U8},
        BorrowSpan{8, 80}, ReborrowSpan{80, 136}, Constant{7, Type::I64}, Push{},
        Constant{1, Type::Bool}, BranchFalse{1}, EndSpan{80}, Label{1}, Pop{},
        EndSpan{136}, EndSpan{80}, EndArray{8}, Return{}};
    reject("conditional stale parent cannot escape", parent, "live child reborrow");
    reject("scalar return with saved operands", moduleWith({Constant{1, Type::I64},
        Push{}, Constant{1, Type::Bool}, BranchFalse{1}, Label{1},
        Constant{0, Type::I64}, Return{}}), "unbalanced stack at return");
    auto objectReturn = lifetimeBase();
    objectReturn.functions[0].result = Type("Box");
    objectReturn.functions[0].code = {BeginObject{24}, Constant{1, Type::I64}, Store{24, Type::I64},
        Push{}, Constant{1, Type::Bool}, BranchFalse{1}, Label{1}, ReturnObject{24}};
    reject("object return with saved operands", objectReturn, "unbalanced stack at object return");
    reject("loop backedge changes stack depth", moduleWith({Constant{1, Type::I64},
        Push{}, Label{1}, Constant{0, Type::Bool}, BranchFalse{2}, Pop{}, Jump{1},
        Label{2}, Pop{}, Return{}}), stackJoin);
    reject("unknown branch target", moduleWith({Constant{0, Type::Bool}, BranchFalse{99},
        Constant{1, Type::I64}, Return{}}), "unknown branch target");
    reject("unknown unreachable jump target", moduleWith({Constant{1, Type::I64}, Return{},
        Jump{99}}), "unknown jump target");
    reject("duplicate label", moduleWith({Label{1}, Label{1}, Constant{1, Type::I64}, Return{}}),
        "duplicate or invalid label");
    reject("unreachable semantic operation", moduleWith({Constant{1, Type::I64}, Return{},
        Push{}}), "unreachable semantic instruction");
    reject("unreachable branch is semantic", moduleWith({Constant{1, Type::I64}, Return{},
        Label{1}, Constant{0, Type::Bool}, BranchFalse{1}}), "unreachable semantic instruction");
    reject("missing bool at branch", moduleWith({Constant{1, Type::I64}, Push{}, BranchFalse{1},
        Label{1}, Pop{}, Return{}}), "missing or mistyped current value");
    // Equal stacks at the join are insufficient: the backend's unchanged linear
    // depth counter would count both mutually exclusive pushes.
    reject("CFG-valid but nonlinear two-arm push", moduleWith({Constant{1, Type::Bool},
        BranchFalse{1}, Constant{7, Type::I64}, Push{}, Jump{2}, Label{1},
        Constant{9, Type::I64}, Push{}, Label{2}, Pop{}, Return{}}),
        "operand stack depth differs from linear emission order");
}

IRFunction resourceFunction(int depth, int labels, bool operandOver = false) {
    IRFunction f;
    f.name = "resource";
    f.result = Type::I64;
    f.code.push_back(Constant{1, Type::I64});
    for (int index = 0; index < depth; ++index) f.code.push_back(Push{});
    for (int index = 0; index < labels; ++index) f.code.push_back(Label{index});
    if (operandOver) {
        for (int index = 1; index < depth; ++index) f.code.push_back(Pop{});
        f.code.push_back(Label{labels});
        f.code.push_back(Pop{});
    } else for (int index = 0; index < depth; ++index) f.code.push_back(Pop{});
    f.code.push_back(Return{});
    return f;
}
void verifyResource(IRFunction &f, verification::Metrics *metrics) {
    const std::map<std::string, const IRFunction *> functions{{f.name, &f}};
    verification::verifyFunction(f, functions, metrics);
}
void resourceTests() {
    using Budget = verification::BlockRetentionBudget;
    Budget exact;
    exact.retain(Budget::maximumOperands);
    check(exact.states() == 1 && exact.operands() == Budget::maximumOperands,
          "exact operand budget accounting");
    rejection("budget one operand over", [&] { exact.retain(1); }, "operand retention limit");
    check(exact.states() == 1 && exact.operands() == Budget::maximumOperands,
          "operand rejection mutated counters");
    rejection("budget SIZE_MAX input", [&] { exact.retain(std::numeric_limits<std::size_t>::max()); },
              "operand retention limit");
    check(exact.states() == 1 && exact.operands() == Budget::maximumOperands,
          "SIZE_MAX rejection mutated counters");
    Budget fresh;
    rejection("fresh budget SIZE_MAX input", [&] { fresh.retain(std::numeric_limits<std::size_t>::max()); },
              "operand retention limit");
    check(fresh.states() == 0 && fresh.operands() == 0, "fresh overflow mutated counters");
    for (std::size_t index = 0; index < Budget::maximumStates; ++index) fresh.retain(0);
    rejection("budget one state over", [&] { fresh.retain(0); }, "state retention limit");
    check(fresh.states() == Budget::maximumStates && fresh.operands() == 0,
          "state rejection mutated counters");
    ++accepted;
    for (int labels : {16, 64, 256, 4096}) {
        auto f = resourceFunction(64, labels);
        verification::Metrics metrics;
        verifyResource(f, &metrics);
        check(metrics.snapshots == static_cast<std::size_t>(labels + 1) &&
              metrics.peakOperandDepth == 64 &&
              metrics.peakRetainedOperandFacts == static_cast<std::size_t>(labels) * 64,
              "scaled retained-operand accounting differs");
        ++accepted;
        std::cout << "PASS short-circuit IR retained operands: blocks=" << labels
                  << " facts=" << metrics.peakRetainedOperandFacts << '\n';
    }
    for (bool withMetrics : {false, true}) {
        auto f = resourceFunction(64, 4096, true);
        verification::Metrics metrics;
        rejection("real verifier operand cap " + std::to_string(withMetrics),
                  [&] { verifyResource(f, withMetrics ? &metrics : nullptr); },
                  "operand retention limit");
        if (withMetrics)
            check(metrics.snapshots == 4097 && metrics.peakRetainedOperandFacts == 262144,
                  "rejected operand snapshot was retained");
    }
    {
        auto f = resourceFunction(0, 65535);
        verification::Metrics metrics;
        verifyResource(f, &metrics);
        check(metrics.snapshots == 65536 && metrics.peakRetainedOperandFacts == 0,
              "exact retained state accounting");
        ++accepted;
    }
    for (bool withMetrics : {false, true}) {
        auto f = resourceFunction(0, 65536);
        verification::Metrics metrics;
        rejection("real verifier state cap " + std::to_string(withMetrics),
                  [&] { verifyResource(f, withMetrics ? &metrics : nullptr); },
                  "state retention limit");
        if (withMetrics) check(metrics.snapshots == 65536, "rejected block snapshot was retained");
    }
    {
        auto f = resourceFunction(4096, 0);
        verification::Metrics metrics;
        verifyResource(f, &metrics);
        check(metrics.snapshots == 1 && metrics.peakOperandDepth == 4096 &&
              metrics.peakRetainedOperandFacts == 0, "straight-line stack was unnecessarily retained");
        ++accepted;
    }
    // Revisiting a block after must-initialization intersection must not charge
    // the unchanged exact stack twice. Queue ordering visits this join first
    // through the short uninitialized arm, then through a longer initialized arm.
    auto revisit = resourceFunction(64, 0);
    revisit.frameBytes = 16;
    revisit.slots = {{8, Type::I64}};
    revisit.code.resize(65);
    append(revisit, {Constant{1, Type::Bool}, BranchFalse{1}, Constant{7, Type::I64},
        Store{8, Type::I64}, Jump{2}, Label{1}, Jump{2}, Label{2}});
    for (int n = 0; n < 64; ++n) revisit.code.push_back(Pop{});
    revisit.code.push_back(Return{});
    verification::Metrics metrics;
    verifyResource(revisit, &metrics);
    check(metrics.snapshots == 4 && metrics.peakRetainedOperandFacts == 192,
          "worklist revisit recharged retained operands");
    ++accepted;
}
} // namespace
int main(int argc, char **argv) {
    try {
        if (argc == 2 && std::string(argv[1]) == "--emit-native") {
            std::cout << X86Emitter{}.emit(validate(nativeModule()));
            return 0;
        }
        check(argc == 1, "usage: short-circuit-ir [--emit-native]");
        directTests();
        resourceTests();
        std::cout << "PASS short-circuit direct IR: " << accepted << " accepted, "
                  << rejected << " rejected\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL short-circuit direct IR: " << error.what() << '\n';
        return 1;
    }
}
