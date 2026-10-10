// Standalone typed-IR ownership/provenance adversaries. Literal 56-byte record
// extents are independent expectations, not copies of production layout helpers.
#include "ir_verify.hpp"
#include <functional>
#include <iostream>
using namespace aurora;
using namespace aurora::ir;
using F = aurora::ir::Function;
namespace {
int accepted = 0, rejected = 0;
void check(bool value, const std::string &message) {
    if (!value)
        throw Error(message);
}
void append(F &f, std::initializer_list<Instruction> code) {
    f.code.insert(f.code.end(), code);
}
template <class T> std::size_t at(const F &f, int occurrence = 0) {
    for (std::size_t i = 0; i < f.code.size(); ++i)
        if (std::holds_alternative<T>(f.code[i]) && occurrence-- == 0)
            return i;
    throw Error("missing fixture operation");
}
template <class T> void before(F &f, std::initializer_list<Instruction> code, int occurrence = 0) {
    f.code.insert(f.code.begin() + at<T>(f, occurrence), code);
}
template <class T> T &op(F &f, int occurrence = 0) {
    return std::get<T>(f.code[at<T>(f, occurrence)]);
}
void accept(const std::string &name, Module m) {
    (void)validate(std::move(m));
    ++accepted;
    std::cout << "PASS owned span IR " << name << '\n';
}
void reject(const std::string &name,
            Module m,
            const std::function<void(Module &)> &mutate,
            const std::string &diagnostic) {
    mutate(m);
    try {
        (void)validate(std::move(m));
    } catch (const Error &error) {
        check(std::string(error.what()).find(diagnostic) != std::string::npos,
              name + ": wrong diagnostic: " + error.what());
        ++rejected;
        std::cout << "PASS owned span IR " << name << '\n';
        return;
    }
    throw Error(name + ": malformed IR accepted");
}
Module standalone() {
    F f;
    f.name = "owned_span";
    f.result = Type::I64;
    f.parameters = {Type::ByteRegion, Type::OwnedBytes};
    f.frameBytes = 256;
    f.regionSlots = {8};
    f.byteSlots = {{40, true}, {72, true}};
    f.spanSlots = {136, 192, 248};
    f.code = {BindRegionParameter{0, 8},
              BindBytesParameter{1, 40},
              BorrowOwnedSpan{40, -1, 136},
              ReborrowSpan{136, 192},
              Constant{0, Type::I64},
              Push{},
              Constant{0, Type::I64},
              Subspan{192, 248},
              SpanLength{248},
              EndSpan{248},
              EndSpan{192},
              EndSpan{136},
              EndBytes{40},
              Return{}};
    Module m;
    m.functions = {f};
    return m;
}
Module shapes() {
    Module m;
    m.classLayouts = {{"Pair", {Type::U8}}, {"Empty", {}}};
    m.classFields["Pair"] = {{Type::OwnedBytes, 0, 0, false}, {Type::U8, 0, 1, false}, {Type::OwnedBytes, 1, 0, false}};
    m.classFields["Empty"] = {};
    m.classStorage = {{"Pair", {{32}, {0, 32, 40}, 72, 8, 72}}, {"Empty", {{}, {}, 8, 8, 8}}};
    return m;
}
F view() {
    F f;
    f.name = "view";
    f.receiver = Receiver{"Pair", false, false};
    f.result = Type::ByteSpan;
    f.receiverSpanField = 0;
    f.frameBytes = 176;
    f.spanSlots = {56, 112, 168};
    f.code = {BorrowOwnedSpan{0, 0, 56},
              ReborrowSpan{56, 112},
              Constant{0, Type::I64},
              Push{},
              Constant{0, Type::I64},
              Subspan{112, 168},
              ReturnSpan{168}};
    return f;
}
F scalarMethod(bool mutableValue) {
    F f;
    f.name = mutableValue ? "mutate" : "read";
    f.receiver = Receiver{"Pair", mutableValue, false};
    f.result = Type::I64;
    f.code = {BytesLength{0, 0}, Return{}};
    return f;
}
Module receiverResult() {
    auto m = shapes();
    m.functions = {view(), scalarMethod(false), scalarMethod(true)};
    return m;
}
Module object(bool call = false) {
    auto m = receiverResult();
    F f;
    f.name = "caller";
    f.result = Type::I64;
    f.parameters = {Type::ByteRegion, Type("Pair")};
    f.frameBytes = 336;
    f.regionSlots = {8};
    f.objectSlots = {{80, {"Pair", true}}, {160, {"Pair", true}}};
    f.slots = {{48, Type::U8}, {128, Type::U8}};
    f.spanSlots = {216, 272, 328};
    f.code = {BindRegionParameter{0, 8}, BindOwnedObjectParameter{1, 80, "Pair"}};
    if (call)
        f.code.push_back(MethodCall{"view", 80, {}, 216});
    else
        f.code.push_back(BorrowOwnedSpan{80, 0, 216});
    append(f,
           {ReborrowSpan{216, 272},
            Constant{0, Type::I64},
            Push{},
            Constant{0, Type::I64},
            Subspan{272, 328},
            SpanLength{328},
            EndSpan{328},
            EndSpan{272},
            EndSpan{216},
            EndObject{80},
            Return{}});
    m.functions.insert(m.functions.begin(), f);
    return m;
}
void storageTests() {
    check(spanBytes == 56, "public span record width changed");
    ++accepted;
    // Every byte in all seven words must be reserved, even unused payload words.
    for (int byte = 81; byte <= 136; ++byte)
        reject(
            "record byte cannot become scalar " + std::to_string(byte),
            standalone(),
            [=](Module &m) {
                m.functions[0].slots[byte] = Type::U8;
            },
            "span spill overlaps");
    for (int base : {0, 8, 16, 48, 55, 57, 257, 264})
        reject(
            "bad record extent " + std::to_string(base),
            standalone(),
            [=](Module &m) {
                m.functions[0].spanSlots.insert(base);
            },
            "span spill");
    for (int base : {88, 96, 104, 112, 120, 128, 144, 152, 160, 168, 176, 184})
        reject(
            "record overlap " + std::to_string(base),
            standalone(),
            [=](Module &m) {
                m.functions[0].spanSlots.insert(base);
            },
            "overlapping span spills");
    reject(
        "region overlaps tail",
        standalone(),
        [](Module &m) {
            m.functions[0].regionSlots.insert(88);
        },
        "overlaps scalar, object, array or span");
    reject(
        "owner overlaps record",
        standalone(),
        [](Module &m) {
            m.functions[0].byteSlots[112] = true;
        },
        "overlaps scalar, object, array or span");
    reject(
        "array overlaps payload",
        standalone(),
        [](Module &m) {
            m.functions[0].arraySlots[100] = 1;
            m.functions[0].slots[100] = Type::U8;
        },
        "span spill overlaps");
    reject(
        "empty object overlaps payload",
        standalone(),
        [](Module &m) {
            m.classLayouts["Empty"] = {};
            m.functions[0].objectSlots[104] = {"Empty", false};
        },
        "span spill overlaps");
    auto tight = receiverResult();
    tight.functions[0].frameBytes = 64;
    tight.functions[0].spanSlots = {56};
    tight.functions[0].code = {BorrowOwnedSpan{0, 0, 56}, ReturnSpan{56}};
    accept("exact minimum aligned record", tight);
}
void standaloneTests() {
    accept("standalone nested empty owned view", standalone());
    const auto bad =
        [&](const std::string &name, const std::function<void(F &)> &change, const std::string &diagnostic) {
            reject(
                name,
                standalone(),
                [&](Module &m) {
                    change(m.functions[0]);
                },
                diagnostic);
        };
    bad(
        "borrow inactive owner",
        [](F &f) {
            op<BorrowOwnedSpan>(f).offset = 72;
        },
        "lifetime is not active");
    bad(
        "borrow owner interior",
        [](F &f) {
            op<BorrowOwnedSpan>(f).offset = 39;
        },
        "exact typed spill");
    bad(
        "borrow arbitrary selector",
        [](F &f) {
            op<BorrowOwnedSpan>(f).fieldIndex = -2;
        },
        "field selector");
    bad(
        "standalone cannot pretend to be object",
        [](F &f) {
            op<BorrowOwnedSpan>(f).fieldIndex = 0;
        },
        "exact object slot");
    bad(
        "borrow untyped destination",
        [](F &f) {
            op<BorrowOwnedSpan>(f).resultOffset = 128;
        },
        "exact typed spill");
    bad(
        "borrow consumed owner",
        [](F &f) {
            before<BorrowOwnedSpan>(f, {BeginBytes{72}, MoveBytes{40, 72}});
        },
        "live ownership");
    bad(
        "borrow pristine owner",
        [](F &f) {
            before<BorrowOwnedSpan>(f, {BeginBytes{72}});
            op<BorrowOwnedSpan>(f).offset = 72;
        },
        "live ownership");
    for (const std::string action : {"write", "resize", "move", "drop"})
        bad(
            action + " freezes exact standalone owner",
            [=](F &f) {
                if (action == "write")
                    before<SpanLength>(f, {Constant{0, Type::I64}, Push{}, Constant{1, Type::U8}, BytesStore{40}});
                if (action == "resize")
                    before<SpanLength>(f, {Constant{0, Type::I64}, BytesResize{40}});
                if (action == "move")
                    before<SpanLength>(f, {BeginBytes{72}, MoveBytes{40, 72}});
                if (action == "drop")
                    before<SpanLength>(f, {EndBytes{40}});
            },
            "live readonly span");
    bad(
        "parent cannot end before empty descendant",
        [](F &f) {
            before<SpanLength>(f, {EndSpan{192}});
        },
        "live child reborrow");
    bad(
        "root cannot end before descendants",
        [](F &f) {
            before<SpanLength>(f, {EndSpan{136}});
        },
        "live child reborrow");
    bad(
        "return cannot implicitly end local owner",
        [](F &f) {
            f.code = {BindRegionParameter{0, 8},
                      BindBytesParameter{1, 40},
                      BorrowOwnedSpan{40, -1, 136},
                      Constant{0, Type::I64},
                      Return{}};
        },
        "active owned byte lifetime");
    bad(
        "ordinary span return rejected",
        [](F &f) {
            f.result = Type::ByteSpan;
        },
        "resource signature requires scalar");
    bad(
        "forged summary on scalar result",
        [](F &f) {
            f.receiverSpanField = 0;
        },
        "summary requires span result");
    bad(
        "branch loses capability",
        [](F &f) {
            before<SpanLength>(f, {Constant{1, Type::Bool}, BranchFalse{1}, EndSpan{248}, Label{1}});
        },
        "incompatible active span capabilities");
    bad(
        "branch reuses spill with another site",
        [](F &f) {
            before<SpanLength>(
                f, {Constant{1, Type::Bool}, BranchFalse{1}, EndSpan{248}, ReborrowSpan{192, 248}, Label{1}});
        },
        "incompatible active span capabilities");
    auto reads = standalone();
    before<SpanLength>(reads.functions[0], {BytesLength{40}, BytesOk{40}, Constant{0, Type::I64}, BytesLoad{40}});
    accept("copied reads coexist with owned view", reads);
    auto sibling = standalone();
    before<BorrowOwnedSpan>(sibling.functions[0], {BeginBytes{72}, Constant{3, Type::I64}, AllocateBytes{8, 72}});
    before<SpanLength>(sibling.functions[0], {Constant{0, Type::I64}, BytesResize{72}, EndBytes{72}});
    accept("independent standalone owner remains writable", sibling);
    auto released = standalone();
    before<EndBytes>(released.functions[0], {Constant{1, Type::I64}, BytesResize{40}, Constant{0, Type::I64}});
    accept("write restored only after every descendant ends", released);
    auto loop = standalone();
    before<ReborrowSpan>(
        loop.functions[0],
        {Label{1}, ReborrowSpan{136, 192}, EndSpan{192}, Constant{0, Type::Bool}, BranchFalse{2}, Jump{1}, Label{2}});
    accept("closed child site can restart across loop", loop);
    // Acquisition of the first argument is live while the second is evaluated.
    auto args = standalone();
    F read;
    read.name = "read_args";
    read.result = Type::I64;
    read.parameters = {Type::ByteSpan, Type::Bool};
    read.frameBytes = 64;
    read.spanSlots = {56};
    read.slots = {{64, Type::Bool}};
    read.code = {BindSpanParameter{0, 56}, BindParameter{1, 64, Type::Bool}, SpanLength{56}, EndSpan{56}, Return{}};
    args.functions.push_back(read);
    before<SpanLength>(args.functions[0],
                       {Constant{1, Type::Bool}, Push{}, AggregateCall{"read_args", {0, 0}, 0, {248, 0}}});
    accept("temporary argument survives readonly call", args);
    reject(
        "later argument cannot resize earlier view owner",
        args,
        [](Module &m) {
            before<AggregateCall>(m.functions[0], {Constant{0, Type::I64}, BytesResize{40}});
        },
        "live readonly span");
    auto consume = standalone();
    F target;
    target.name = "consume";
    target.result = Type::I64;
    target.parameters = {Type::ByteRegion, Type::OwnedBytes};
    target.frameBytes = 48;
    target.regionSlots = {8};
    target.byteSlots = {{40, true}};
    target.code = {
        BindRegionParameter{0, 8}, BindBytesParameter{1, 40}, EndBytes{40}, Constant{0, Type::I64}, Return{}};
    consume.functions.push_back(target);
    reject(
        "consuming call cannot invalidate view",
        consume,
        [](Module &m) {
            before<SpanLength>(m.functions[0], {ResourceCall{"consume", 8, {0, 40}, 0}});
        },
        "live readonly span");
}
void objectTests() {
    accept("direct field nested empty view", object());
    accept("caller derives returned authority from own root", object(true));
    for (bool call : {false, true}) {
        auto m = object(call);
        const auto bad =
            [&](const std::string &name, const std::function<void(F &)> &change, const std::string &diagnostic) {
                reject(
                    name + (call ? " returned" : " direct"),
                    m,
                    [&](Module &x) {
                        change(x.functions[0]);
                    },
                    diagnostic);
            };
        bad(
            "same field write blocked",
            [](F &f) {
                before<SpanLength>(f, {Constant{0, Type::I64}, Push{}, Constant{1, Type::U8}, BytesStore{80, 0}});
            },
            "live readonly span");
        bad(
            "same field resize blocked",
            [](F &f) {
                before<SpanLength>(f, {Constant{0, Type::I64}, BytesResize{80, 0}});
            },
            "live readonly span");
        bad(
            "root drop blocked",
            [](F &f) {
                before<SpanLength>(f, {EndObject{80}});
            },
            "live readonly span");
        bad(
            "root move blocked",
            [](F &f) {
                before<SpanLength>(f, {BeginObject{160}, MoveObject{80, 160}});
            },
            "live readonly span");
        bad(
            "mutable method freezes whole root",
            [](F &f) {
                before<SpanLength>(f, {MethodCall{"mutate", 80}});
            },
            "live readonly span");
        auto siblings = m;
        before<SpanLength>(siblings.functions[0],
                           {Constant{0, Type::I64},
                            BytesResize{80, 2},
                            Constant{91, Type::U8},
                            Store{48, Type::U8},
                            MethodCall{"read", 80}});
        accept(call ? "returned view permits sibling direct writes" : "direct view permits sibling direct writes",
               siblings);
        auto released = m;
        before<EndObject>(released.functions[0], {MethodCall{"mutate", 80}});
        accept(call ? "released result restores mutable root" : "released direct view restores mutable root", released);
    }
    reject(
        "scalar field is not owner",
        object(),
        [](Module &m) {
            op<BorrowOwnedSpan>(m.functions[0]).fieldIndex = 1;
        },
        "direct resource field");
    reject(
        "out of range field",
        object(),
        [](Module &m) {
            op<BorrowOwnedSpan>(m.functions[0]).fieldIndex = 3;
        },
        "direct resource field");
    reject(
        "owning object interior not root",
        object(),
        [](Module &m) {
            op<BorrowOwnedSpan>(m.functions[0]).offset = 72;
        },
        "exact object slot");
    reject(
        "method result cannot overwrite live span",
        object(true),
        [](Module &m) {
            before<ReborrowSpan>(m.functions[0], {MethodCall{"view", 80, {}, 216}});
        },
        "span spill is already active");
    reject(
        "method result requires typed destination",
        object(true),
        [](Module &m) {
            op<MethodCall>(m.functions[0]).resultOffset = 0;
        },
        "exact typed spill");
    reject(
        "method summary cannot forge other owning field",
        object(true),
        [](Module &m) {
            m.functions[1].receiverSpanField = 2;
        },
        "span return does not match receiver field summary and token");
}
void returnTests() {
    accept("const receiver returns exact derived field", receiverResult());
    const auto bad =
        [&](const std::string &name, const std::function<void(F &)> &change, const std::string &diagnostic) {
            reject(
                name,
                receiverResult(),
                [&](Module &m) {
                    change(m.functions[0]);
                },
                diagnostic);
        };
    bad(
        "span result needs summary",
        [](F &f) {
            f.receiverSpanField.reset();
        },
        "readonly span boundary");
    bad(
        "mutable receiver cannot return view",
        [](F &f) {
            f.receiver->mutableValue = true;
        },
        "readonly span boundary");
    bad(
        "ordinary function cannot claim receiver summary",
        [](F &f) {
            f.receiver.reset();
        },
        "readonly span boundary");
    bad(
        "scalar summary field rejected",
        [](F &f) {
            f.receiverSpanField = 1;
        },
        "exact direct byte-storage field");
    for (int field : {-1, 3, 2147483647})
        bad(
            "bad summary ordinal " + std::to_string(field),
            [=](F &f) {
                f.receiverSpanField = field;
            },
            "exact direct byte-storage field");
    bad(
        "wrong returned field rejected",
        [](F &f) {
            op<BorrowOwnedSpan>(f).fieldIndex = 2;
        },
        "span return does not match receiver field summary and token");
    bad(
        "ended returned capability rejected",
        [](F &f) {
            before<ReturnSpan>(f, {EndSpan{168}});
        },
        "span capability is not active");
    bad(
        "return from untyped spill rejected",
        [](F &f) {
            op<ReturnSpan>(f).offset = 160;
        },
        "exact typed spill");
    bad(
        "ordinary scalar return cannot replace span return",
        [](F &f) {
            f.code.back() = Return{};
        },
        "scalar return cannot return class value or resource value");
    bad(
        "span return cannot leak operand",
        [](F &f) {
            before<ReturnSpan>(f, {Constant{0, Type::I64}, Push{}});
        },
        "unbalanced stack at span return");
    bad(
        "local array cannot be returned",
        [](F &f) {
            f.frameBytes = 192;
            f.slots[176] = Type::U8;
            f.arraySlots[176] = 1;
            f.code = {
                BeginArray{176}, Constant{1, Type::U8}, Store{176, Type::U8}, BorrowSpan{176, 56}, ReturnSpan{56}};
        },
        "span return does not match receiver field summary and token");
    bad(
        "unrelated live array cannot hide behind result",
        [](F &f) {
            f.frameBytes = 192;
            f.slots[176] = Type::U8;
            f.arraySlots[176] = 1;
            before<ReturnSpan>(f, {BeginArray{176}});
        },
        "unrelated active local lifetime");
    bad(
        "unrelated pristine owner cannot hide behind result",
        [](F &f) {
            f.frameBytes = 208;
            f.byteSlots[208] = true;
            before<ReturnSpan>(f, {BeginBytes{208}});
        },
        "unrelated active local lifetime");
    bad(
        "every reachable return is checked",
        [](F &f) {
            f.code = {Constant{1, Type::Bool},
                      BranchFalse{1},
                      BorrowOwnedSpan{0, 0, 56},
                      ReturnSpan{56},
                      Label{1},
                      BorrowOwnedSpan{0, 2, 112},
                      ReturnSpan{112}};
        },
        "span return does not match receiver field summary and token");
    bad(
        "unrelated receiver view must be closed",
        [](F &f) {
            f.code = {BorrowOwnedSpan{0, 0, 56}, BorrowOwnedSpan{0, 2, 112}, ReturnSpan{56}};
        },
        "unrelated active span lifetime");
    bad(
        "sibling view of same field must be closed",
        [](F &f) {
            f.code = {BorrowOwnedSpan{0, 0, 56}, ReborrowSpan{56, 112}, ReborrowSpan{56, 168}, ReturnSpan{112}};
        },
        "unrelated active span lifetime");
    auto copied = receiverResult();
    copied.functions[0].parameters = {Type("Empty")};
    copied.functions[0].frameBytes = 192;
    copied.functions[0].objectSlots[176] = {"Empty", false};
    copied.functions[0].code.insert(copied.functions[0].code.begin(), BindObjectParameter{0, 176, "Empty"});
    before<ReturnSpan>(copied.functions[0], {EndObject{176}});
    accept("ended copied class parameter permits receiver return", copied);
    reject(
        "copied parameter must be explicitly closed",
        copied,
        [](Module &m) {
            auto &f = m.functions[0];
            f.code.erase(f.code.begin() + at<EndObject>(f));
        },
        "unrelated active local lifetime");
    auto branches = receiverResult();
    branches.functions[0].code = {Constant{1, Type::Bool},
                                  BranchFalse{1},
                                  BorrowOwnedSpan{0, 0, 56},
                                  ReturnSpan{56},
                                  Label{1},
                                  BorrowOwnedSpan{0, 0, 112},
                                  ReturnSpan{112}};
    accept("all reachable return arms match exact summary", branches);
    auto forwarding = receiverResult();
    F f = view();
    f.name = "forward";
    f.code = {MethodCall{"view", 0, {}, 56}, ReborrowSpan{56, 112}, ReturnSpan{112}};
    forwarding.functions.push_back(f);
    accept("forwarded receiver retains invocation token", forwarding);
    auto freeze = receiverResult();
    F f2 = view();
    f2.name = "mutable_borrow";
    f2.result = Type::I64;
    f2.receiverSpanField.reset();
    f2.receiver->mutableValue = true;
    f2.code = {BorrowOwnedSpan{0, 0, 56}, MethodCall{"mutate", 0}, EndSpan{56}, Return{}};
    freeze.functions.insert(freeze.functions.begin(), f2);
    reject(
        "bound receiver forwarding remains frozen",
        freeze,
        [](Module &) {
        },
        "live readonly span");
    freeze.functions[0].code = {BorrowOwnedSpan{0, 0, 56},
                                Constant{0, Type::I64},
                                BytesResize{0, 2},
                                EndSpan{56},
                                Constant{0, Type::I64},
                                Return{}};
    accept("bound receiver sibling field remains independent", freeze);
}

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
void fixedFieldTests() {
    accept("fixed field view uses exact copied receiver lifetime", fixedFieldModule());
    reject(
        "fixed field wrong summary",
        fixedFieldModule(),
        [](Module &m) {
            m.functions[0].receiverSpanField = 2;
        },
        "does not match receiver field summary");
    reject(
        "fixed field scalar origin",
        fixedFieldModule(),
        [](Module &m) {
            op<BorrowReceiverArraySpan>(m.functions[0]).fieldIndex = 0;
        },
        "requires direct u8 array field");
    reject(
        "fixed field outside shape",
        fixedFieldModule(),
        [](Module &m) {
            op<BorrowReceiverArraySpan>(m.functions[0]).fieldIndex = 3;
        },
        "receiver field type/layout mismatch");
    reject(
        "fixed field spill interior",
        fixedFieldModule(),
        [](Module &m) {
            op<BorrowReceiverArraySpan>(m.functions[0]).resultOffset = 48;
        },
        "exact typed spill");
    reject(
        "fixed field parent ends first",
        fixedFieldModule(),
        [](Module &m) {
            before<SpanLength>(m.functions[1], {EndSpan{72}});
        },
        "live child reborrow");
    reject(
        "fixed field object ends first",
        fixedFieldModule(),
        [](Module &m) {
            before<SpanLength>(m.functions[1], {EndObject{16}});
        },
        "live readonly span");
    reject(
        "fixed field scalar mutation cannot bypass borrow",
        fixedFieldModule(),
        [](Module &m) {
            before<SpanLength>(m.functions[1], {Constant{1, Type::U8}, Store{8, Type::U8}});
        },
        "live readonly span");
    reject(
        "fixed field indexed mutation cannot bypass borrow",
        fixedFieldModule(),
        [](Module &m) {
            before<SpanLength>(m.functions[1],
                               {Constant{0, Type::I64},
                                BoundsGuard{8, 2, Type::U8},
                                Push{},
                                Constant{1, Type::U8},
                                IndexStore{8, 2, Type::U8}});
        },
        "live readonly span");
    auto local = fixedFieldModule();
    auto &read = local.functions[0];
    read.receiverSpanField.reset();
    read.result = Type::I64;
    read.receiver->mutableValue = true;
    read.code = {BorrowReceiverArraySpan{1, 56},
                 Constant{0, Type::I64},
                 ReceiverBoundsGuard{1},
                 Push{},
                 Constant{1, Type::U8},
                 ReceiverIndexStore{1},
                 EndSpan{56},
                 Constant{0, Type::I64},
                 Return{}};
    local.functions.resize(1);
    reject(
        "fixed receiver indexed mutation cannot bypass borrow",
        local,
        [](Module &) {
        },
        "live readonly span");
    op<ReceiverBoundsGuard>(local.functions[0]).fieldIndex = 2;
    op<ReceiverIndexStore>(local.functions[0]).fieldIndex = 2;
    accept("fixed receiver sibling array stays independent", local);
    auto restart = fixedFieldModule();
    restart.functions.resize(1);
    F root;
    root.name = "fixed_restart";
    root.result = Type::I64;
    root.objectSlots = {{16, {"Fixed", true}}};
    root.slots = {{16, Type::I64}, {8, Type::U8}, {7, Type::U8}, {6, Type::U8}, {5, Type::U8}};
    root.frameBytes = 80;
    root.spanSlots = {72};
    const std::initializer_list<Instruction> initialize = {BeginObject{16},
                                                           Constant{0, Type::I64},
                                                           Store{16, Type::I64},
                                                           Constant{0, Type::U8},
                                                           Store{8, Type::U8},
                                                           Store{7, Type::U8},
                                                           Store{6, Type::U8},
                                                           Store{5, Type::U8}};
    append(root, initialize);
    append(root, {Constant{1, Type::Bool}, BranchFalse{1}, EndObject{16}});
    append(root, initialize);
    append(root,
           {Label{1}, MethodCall{"fixed_view", 16, {}, 72}, SpanLength{72}, EndSpan{72}, EndObject{16}, Return{}});
    restart.functions.push_back(root);
    reject(
        "fixed root restart cannot join retained lifetime",
        restart,
        [](Module &) {
        },
        "active object lifetimes");
}

void importReachabilityTests() {
    auto m = fixedFieldModule();
    m.descriptorViews[1] = {};
    m.functions[0].moduleScope = 1;
    F root;
    root.name = "unused_private_root";
    root.result = Type::I64;
    root.code = {Constant{42, Type::I64}, Return{}};
    m.functions.push_back(root);
    F unused = root;
    unused.name = "unused_import";
    unused.moduleScope = 1;
    m.functions.push_back(unused);
    auto valid = validate(m);
    std::set<std::string> names;
    for (const auto &function : valid.get().functions)
        names.insert(function.name);
    check(names == std::set<std::string>{"fixed_view", "fixed_caller", "unused_private_root"},
          "reachable import or root bridge was pruned, or unused import was retained");
    ++accepted;
    reject(
        "unused imported IR still receives complete validation",
        m,
        [](Module &module) {
            module.functions.back().code = {Constant{300, Type::U8}, Return{}};
        },
        "noncanonical u8");
    auto recursive = fixedFieldModule();
    recursive.descriptorViews[1] = {};
    recursive.functions[0].moduleScope = 1;
    recursive.functions[0].code = {MethodCall{"fixed_view", 0, {}, 56}, ReturnSpan{56}};
    recursive.functions.erase(recursive.functions.begin() + 1);
    recursive.functions.push_back(root);
    reject(
        "unused imported receiver cycles still reject",
        recursive,
        [](Module &) {
        },
        "recursive receiver call cycle");
}
} // namespace
int main() {
    try {
        importReachabilityTests();
        fixedFieldTests();
        storageTests();
        standaloneTests();
        objectTests();
        returnTests();
        std::cout << "PASS owned span IR: " << accepted << " accepted and " << rejected << " rejected\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
