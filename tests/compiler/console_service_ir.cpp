// Independently authored IR: no parser, semantic lowering or source fixtures.
#include "ir_verify.hpp"
#include "hosted_resolver.hpp"
#include "x86.hpp"
#include "json_fragments.hpp"
#include <algorithm>
#include <array>
#include <functional>
#include <iostream>
#include <tuple>
using namespace aurora;
using namespace aurora::ir;
using aurora::test::jsonMember;
using aurora::test::jsonMembers;
using F = aurora::ir::Function;
namespace {
int checks{};
void need(bool value, const std::string &message) {
    if (!value)
        throw Error(message);
}
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
Module sample() {
    Module m;
    canonicalTypes(m);
    auto f = entry("read_sample");
    f.objectSlots[40] = {std::string(service::sampleName), false};
    f.slots = {{40, Type::Bool}, {32, Type::U8}, {24, Type::Bool}};
    f.code.insert(f.code.end(),
                  {BeginObject{40},
                   ServiceOperation{16, service::Operation::Next, 40},
                   EndObject{40},
                   Constant{0, Type::I64},
                   Return{}});
    m.functions.push_back(f);
    return m;
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
Module copiedResult(bool empty = false) {
    Module m;
    canonicalTypes(m);
    // Five mixed-width leaves exercise the full layout beyond either native
    // observation's fixed field count. Empty results still need completion.
    m.classLayouts["Reply"] =
        empty ? std::vector<Type>{}
              : std::vector<Type>{Type::U64, service::putResultType(), Type::U8, Type::U8, Type::Bool};
    auto f = entry("caller");
    f.result = Type("Reply");
    f.objectSlots[48] = {"Reply", false};
    if (!empty)
        f.slots = {{48, Type::U64}, {40, service::putResultType()}, {32, Type::U8}, {31, Type::U8}, {24, Type::Bool}};
    auto g = f;
    g.name = "reply";
    f.code.insert(f.code.end(),
                  {BeginObject{48},
                   AcquireServiceLoan{1, 16},
                   ServiceCall{"reply", 1, 48, {0}},
                   ReleaseServiceLoan{1},
                   ReturnObject{48}});
    g.code.push_back(BeginObject{48});
    if (empty)
        g.code.push_back(InitializeEmptyObject{48});
    else
        g.code.insert(g.code.end(),
                      {Constant{2, Type::U64},
                       Store{48, Type::U64},
                       EnumConstant{service::putResultType(), 0},
                       Store{40, service::putResultType()},
                       Constant{65, Type::U8},
                       Store{32, Type::U8},
                       Constant{66, Type::U8},
                       Store{31, Type::U8},
                       Constant{1, Type::Bool},
                       Store{24, Type::Bool}});
    g.code.push_back(ReturnObject{48});
    m.functions = {f, g};
    return m;
}
Module copiedArguments(int shape = 0, bool paired = false) {
    Module m;
    canonicalTypes(m);
    // Shape zero is an independent 80-byte array/count/enum contract. Shapes
    // one and two distinguish zero-field and nested-empty completion evidence.
    if (shape == 0) {
        m.classLayouts["Packet"] = std::vector<Type>(64, Type::U8);
        m.classLayouts["Packet"].insert(m.classLayouts["Packet"].end(), {Type::I64, service::putResultType()});
        m.classFields["Packet"] = {
            {Type::U8, 0, 64, true}, {Type::I64, 64, 1, false}, {service::putResultType(), 65, 1, false}};
    } else {
        m.classLayouts["Packet"] = {};
        if (shape == 2) {
            m.classLayouts["Empty"] = {};
            m.classFields["Packet"] = {{Type("Empty"), 0, 0, false}};
        }
    }
    auto reserve = [&](F &function, int base) {
        function.objectSlots[base] = {"Packet", false};
        if (shape == 0) {
            for (int byte = 0; byte < 64; ++byte)
                function.slots[base - byte] = Type::U8;
            function.slots[base - 64] = Type::I64;
            function.slots[base - 72] = service::putResultType();
        }
    };
    auto f = entry("copied_caller");
    f.frameBytes = 512;
    f.result = Type("Packet");
    f.parameters.insert(f.parameters.end(), {Type("Packet"), Type("Packet")});
    for (const int base : {128, 224, 320, 416, 512})
        reserve(f, base);
    f.code.insert(f.code.end(),
                  {BindObjectParameter{1, 128, "Packet"},
                   BindObjectParameter{2, 224, "Packet"},
                   BeginObject{320},
                   CopyObject{128, 320},
                   BeginObject{416},
                   CopyObject{224, 416},
                   BeginObject{512},
                   AcquireServiceLoan{1, 16},
                   ServiceCall{"copied_helper", 1, 512, {0, 0, 0}, service::Kind::Console, {}, {0, 320, 416}},
                   ReleaseServiceLoan{1},
                   EndObject{416},
                   EndObject{320},
                   ReturnObject{512}});
    auto g = entry("copied_helper");
    g.frameBytes = 224;
    g.result = Type("Packet");
    g.parameters = f.parameters;
    reserve(g, 128);
    reserve(g, 224);
    g.code.insert(g.code.end(),
                  {BindObjectParameter{1, 128, "Packet"}, BindObjectParameter{2, 224, "Packet"}, ReturnObject{128}});
    if (paired) {
        m.enumCases[std::string(service::displayPutResultName)] = 2;
        m.enumCases[std::string(service::displayCompletionName)] = 2;
        for (auto *function : {&f, &g}) {
            function->parameters.insert(function->parameters.begin() + 1, Type::DisplaySession);
            function->serviceSlots.insert(32);
            std::get<BindObjectParameter>(function->code[1]).index = 2;
            std::get<BindObjectParameter>(function->code[2]).index = 3;
            function->code.insert(function->code.begin() + 1, BindServiceParameter{1, 32, service::Kind::Display});
        }
        auto &call = std::get<ServiceCall>(f.code[10]);
        call.spanArguments = {0, 0, 0, 0};
        call.objectArguments = {0, 0, 320, 416};
        call.additionalServices = {{2, service::Kind::Display}};
        f.code.insert(f.code.begin() + 10, AcquireServiceLoan{2, 32, service::Kind::Display});
        f.code.insert(f.code.begin() + 12, ReleaseServiceLoan{2, service::Kind::Display});
    }
    m.functions = {f, g};
    return m;
}
ServiceCall &copiedCall(Module &module) {
    for (auto &instruction : module.functions[0].code)
        if (auto *call = std::get_if<ServiceCall>(&instruction))
            return *call;
    throw Error("copied fixture lost its service call");
}
Module copiedSpanArgument() {
    auto m = copiedArguments();
    auto &f = m.functions[0];
    f.frameBytes = 576;
    f.spanSlots.insert(576);
    auto &call = copiedCall(m);
    call.objectArguments[2] = 0;
    call.spanArguments[2] = 576;
    f.code.insert(f.code.begin() + 8, BorrowLiteralSpan{{65}, 576});
    f.code.insert(f.code.begin() + 12, EndSpan{576});
    auto &g = m.functions[1];
    g.parameters[2] = Type::ByteSpan;
    g.objectSlots.erase(224);
    for (int byte = 0; byte < 80; ++byte)
        g.slots.erase(224 - byte);
    g.spanSlots.insert(224);
    g.code[2] = BindSpanParameter{2, 224};
    g.code.insert(g.code.begin() + 3, EndSpan{224});
    return m;
}
Module mixedEntry() {
    Module m;
    canonicalTypes(m);
    m.enumCases[std::string(service::displayPutResultName)] = 2;
    m.enumCases[std::string(service::displayCompletionName)] = 2;
    m.classLayouts["Packet"] = {Type::U8, Type::I64};
    auto f = entry("mixed_entry");
    f.parameters = {Type::ConsoleSession, Type::DisplaySession, Type::U8, Type::ByteSpan, Type("Packet"), Type::Bool};
    f.result = Type::Bool;
    f.frameBytes = 144;
    f.serviceSlots = {16, 32};
    f.slots = {{40, Type::U8}, {128, Type::U8}, {120, Type::I64}, {136, Type::Bool}};
    f.spanSlots = {104};
    f.objectSlots = {{128, {"Packet", false}}};
    f.code = {BindServiceParameter{0, 16, service::Kind::Console},
              BindServiceParameter{1, 32, service::Kind::Display},
              BindParameter{2, 40, Type::U8},
              BindSpanParameter{3, 104},
              BindObjectParameter{4, 128, "Packet"},
              BindParameter{5, 136, Type::Bool},
              Load{40, Type::U8},
              Load{128, Type::U8},
              EndSpan{104},
              Load{136, Type::Bool},
              Return{}};
    m.functions = {f};
    return m;
}
Module mixedForwarded() {
    auto m = mixedEntry();
    auto caller = m.functions[0];
    caller.name = "mixed_caller";
    caller.code.resize(6);
    caller.code.insert(caller.code.end(),
                       {AcquireServiceLoan{1, 16, service::Kind::Console},
                        AcquireServiceLoan{2, 32, service::Kind::Display},
                        Load{40, Type::U8},
                        Push{},
                        Load{136, Type::Bool},
                        Push{},
                        ServiceCall{"mixed_entry",
                                    1,
                                    0,
                                    {0, 0, 0, 104, 0, 0},
                                    service::Kind::Console,
                                    {{2, service::Kind::Display}},
                                    {0, 0, 0, 0, 128, 0}},
                        ReleaseServiceLoan{2, service::Kind::Display},
                        ReleaseServiceLoan{1, service::Kind::Console},
                        EndSpan{104},
                        Return{}});
    m.functions.push_back(caller);
    return m;
}
// Extend existing independent fixtures with the single admitted mixed prefix.
Module withRegion(Module module) {
    for (auto &function : module.functions) {
        const int region = function.frameBytes + 8;
        function.frameBytes = (region + 15) / 16 * 16;
        function.parameters.insert(function.parameters.begin() + 1, Type::ByteRegion);
        function.regionSlots.insert(region);
        for (auto &instruction : function.code) {
            if (auto *binding = std::get_if<BindParameter>(&instruction))
                ++binding->index;
            if (auto *binding = std::get_if<BindObjectParameter>(&instruction))
                ++binding->index;
            if (auto *binding = std::get_if<BindSpanParameter>(&instruction))
                ++binding->index;
            if (auto *call = std::get_if<ServiceCall>(&instruction)) {
                call->spanArguments.insert(call->spanArguments.begin() + 1, 0);
                if (!call->objectArguments.empty())
                    call->objectArguments.insert(call->objectArguments.begin() + 1, 0);
                call->regionOffset = region;
            }
        }
        function.code.insert(function.code.begin() + 1, BindRegionParameter{1, region});
    }
    return module;
}
void copiedArgumentFacts() {
    for (const bool paired : {false, true}) {
        auto module = copiedArguments(0, paired);
        copiedCall(module).resultOffset = 0;
        auto &caller = module.functions[0];
        // Scalar results ensure a missing narrow service_record is caused by
        // the copied inputs, independently of the existing copied-result rule.
        const auto unused = std::find_if(caller.code.begin(), caller.code.end(), [](const auto &instruction) {
            const auto *begin = std::get_if<BeginObject>(&instruction);
            return begin && begin->offset == 512;
        });
        need(unused != caller.code.end(), "copied fixture lost its result reservation");
        caller.code.erase(unused);
        for (auto &function : module.functions) {
            function.result = Type::Bool;
            function.code.back() = Constant{1, Type::Bool};
            function.code.push_back(Return{});
        }
        const auto checked = validate(std::move(module));
        X86Emitter emitter;
        (void)emitter.emit(checked);
        AbiDeclarations declarations;
        declarations.records["Packet"] = {"Packet", {"bytes", "count", "kind"}};
        declarations.functions["copied_helper"] = {"copied_helper", {}};
        const auto abi = emitter.abiFactsJson(checked, declarations);
        const int grantBytes = paired ? 32 : 16;
        need(abi.find("\"size\":80,\"alignment\":8,\"reserved\":80") != std::string::npos &&
                 abi.find("\"parameter_bytes\":" + std::to_string(grantBytes + 160)) != std::string::npos,
             "copied service generic ABI must preserve complete record widths");
        for (const int offset : {grantBytes, grantBytes + 80})
            need(abi.find("\"offset\":" + std::to_string(offset) +
                          ",\"bytes\":80,\"kind\":\"class\",\"type_name\":\"Packet\"") != std::string::npos,
                 "copied service ABI must retain positional nominal value records");
        const auto stack = emitter.stackFactsJson(checked);
        const auto functions = jsonMember(stack, "functions");
        const auto facts = jsonMember(functions, "copied_caller");
        for (const auto name : {"copied_caller", "copied_helper"}) {
            const auto service = jsonMember(jsonMember(functions, name), "service_abi");
            need(service.empty() || jsonMember(service, "record") == "null",
                 "copied service inputs must not advertise scalar-only service_record facts");
        }
        const auto call = jsonMember(jsonMember(facts, "calls"), "copied_helper");
        std::size_t consumed = 0;
        const int callBytes = std::stoi(std::string(call), &consumed);
        need(consumed == call.size() && jsonMember(facts, "local_bytes") == std::to_string(callBytes + 24),
             "copied service stack facts must retain the bounded copy register-save burst");
        ++checks;
    }
}
void good(Module m) {
    X86Emitter emitter;
    const auto validated = validate(std::move(m));
    const auto text = emitter.emit(validated);
    const auto stack = emitter.stackFactsJson(validated);
    jsonMembers(jsonMember(stack, "functions"), [&](std::string_view, std::string_view facts) {
        for (const auto &[host, arguments, maximum] : {std::tuple{"__au_runtime_console_put", 3, 1},
                                                       std::tuple{"__au_runtime_display_pixel", 7, 1},
                                                       std::tuple{"__au_runtime_iommu_event_acknowledge", 2, 2},
                                                       std::tuple{"__au_runtime_call", 3, 2}})
            if (!jsonMember(jsonMember(facts, "calls"), host).empty()) {
                const auto calls = jsonMember(jsonMember(facts, "service_abi"), "calls");
                need(jsonMember(calls, host) == "{\"sysv_arguments\":" + std::to_string(arguments) +
                                                    ",\"result_max\":" + std::to_string(maximum) + "}",
                     "scalar host ABI facts disagree with independently expected native contract");
            }
    });
    need(text.find("__au_runtime_bytes_") == std::string::npos, "service graph depends on byte-owner runtime");
    need(text.find(".globl caller") == std::string::npos, "ordinary public service entry");
    ++checks;
}
void bad(Module m, const std::function<void(Module &)> &mutate, const std::string &expected = {}) {
    mutate(m);
    try {
        (void)validate(std::move(m));
    } catch (const Error &error) {
        need(expected.empty() || std::string(error.what()).find(expected) != std::string::npos,
             "wrong service IR diagnostic: " + std::string(error.what()));
        ++checks;
        return;
    }
    throw Error("hostile service IR unexpectedly accepted");
}
} // namespace
int main() {
    for (auto fixture : {forwarded(), copiedArguments(), copiedSpanArgument()}) {
        good(withRegion(fixture));
        for (const int offset : {0, 16, 17})
            bad(withRegion(fixture), [=](auto &module) {
                copiedCall(module).regionOffset = offset;
            });
        bad(withRegion(fixture), [](auto &module) {
            copiedCall(module).spanArguments[1] = 16;
        });
        bad(withRegion(fixture), [](auto &module) {
            module.functions[0].parameters[0] = Type::DisplaySession;
        });
        bad(withRegion(fixture), [](auto &module) {
            auto &caller = module.functions[0];
            caller.frameBytes += 16;
            caller.regionSlots.insert(caller.frameBytes);
            copiedCall(module).regionOffset = caller.frameBytes;
        });
        const auto checked = validate(withRegion(fixture));
        X86Emitter emitter;
        (void)emitter.emit(checked);
        AbiDeclarations declarations;
        for (const auto &function : fixture.functions)
            declarations.functions[function.name] = {function.name, {}};
        if (fixture.classLayouts.contains("Packet"))
            declarations.records["Packet"] = {"Packet", {"bytes", "count", "kind"}};
        const auto abi = emitter.abiFactsJson(checked, declarations);
        need(abi.find("\"type_name\":\"builtin::ConsoleSession\"") != std::string::npos &&
                 abi.find("\"type_name\":\"builtin::ByteRegion\"") != std::string::npos,
             "mixed copied/span ABI lost exact capability kinds");
    }
    bad(forwarded(), [](auto &module) {
        copiedCall(module).regionOffset = 16;
    });
    good(sample());
    good(forwarded());
    good(copiedResult());
    good(copiedResult(true));
    good(copiedArguments());
    good(copiedArguments(0, true));
    good(copiedArguments(1));
    good(copiedArguments(2));
    good(copiedSpanArgument());
    good(mixedEntry());
    good(mixedForwarded()); // Two services with interleaved scalar, span and copied lanes.
    for (const auto &[position, diagnostic] :
         std::vector<std::pair<int, const char *>>{{0, "service bindings must form the leading entry group"},
                                                   {1, "service bindings must form the leading entry group"},
                                                   {2, "parameter bindings must form the entry prefix"},
                                                   {3, "span parameter bindings must form the entry prefix"},
                                                   {4, "object parameter bindings must form the entry prefix"},
                                                   {5, "parameter bindings must form the entry prefix"}})
        bad(
            mixedEntry(),
            [=](auto &m) {
                m.functions[0].code.erase(m.functions[0].code.begin() + position);
            },
            diagnostic);
    for (const auto &[mutate, diagnostic] : std::vector<std::pair<std::function<void(Module &)>, const char *>>{
             {[](auto &m) {
                  std::get<BindServiceParameter>(m.functions[0].code[1]).kind = service::Kind::Console;
              },
              "service binding requires exact authorized leading parameter"},
             {[](auto &m) {
                  std::get<BindServiceParameter>(m.functions[0].code[1]).offset = 16;
              },
              "service parameter bindings overlap"},
             {[](auto &m) {
                  std::get<BindSpanParameter>(m.functions[0].code[3]).offset = 40;
              },
              "span parameter requires exact typed spill"},
             {[](auto &m) {
                  m.functions[0].objectSlots[128].mutableValue = true;
              },
              "object parameter must be readonly"},
             {[](auto &m) {
                  m.functions[0].arraySlots[40] = 1;
              },
              "parameter cannot bind byte array origin storage"}})
        bad(mixedEntry(), mutate, diagnostic);
    copiedArgumentFacts();
    for (const std::vector<int> &offsets :
         {std::vector<int>{}, {0, 320}, {0, 320, 416, 0}, {320, 320, 416}, {0, 320, 320}, {0, 16, 416}, {0, 319, 416}})
        bad(copiedArguments(), [&](auto &m) {
            copiedCall(m).objectArguments = offsets;
        });
    bad(copiedArguments(), [](auto &m) {
        m.functions[0].objectSlots[320].mutableValue = true;
    });
    bad(copiedArguments(), [](auto &m) {
        m.classLayouts["Other"] = m.classLayouts.at("Packet");
        m.classFields["Other"] = m.classFields.at("Packet");
        auto &f = m.functions[0];
        f.parameters[2] = Type("Other");
        f.objectSlots[224].className = "Other";
        f.objectSlots[416].className = "Other";
        std::get<BindObjectParameter>(f.code[2]).className = "Other";
    });
    for (const int shape : {0, 1, 2}) {
        bad(copiedArguments(shape), [](auto &m) {
            m.functions[0].code.erase(m.functions[0].code.begin() + 4); // Incomplete snapshot, including empty fields.
        });
        bad(copiedArguments(shape), [](auto &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 9, EndObject{320});
        });
        bad(copiedArguments(shape), [](auto &m) {
            copiedCall(m).resultOffset = 320;
        });
    }
    bad(copiedArguments(), [](auto &m) {
        copiedCall(m).spanArguments[1] = 320;
    });
    bad(copiedSpanArgument(), [](auto &m) {
        copiedCall(m).objectArguments[2] = 416;
    });
    bad(copiedArguments(0, true), [](auto &m) {
        copiedCall(m).objectArguments[1] = 416;
    });
    bad(copiedArguments(0, true), [](auto &m) {
        copiedCall(m).additionalServices[0].kind = service::Kind::Console;
    });
    for (const auto &type : {Type::ConsoleSession, Type::ByteSpan, Type::OwnedBytes, Type::ByteRegion})
        bad(copiedArguments(), [&](auto &m) {
            m.classFields["Packet"].push_back({type, 66, 0, false});
        });
    bad(copiedArguments(), [](auto &m) {
        m.functions[1].parameters.resize(7, Type::I64);
    });
    bad(copiedArguments(), [](auto &m) {
        m.functions[0].code[9] = Call{"copied_helper"};
    });
    bad(copiedArguments(), [](auto &m) {
        m.functions[0].code[9] = AggregateCall{"copied_helper", {0, 320, 416}, 512};
    });
    bad(copiedArguments(), [](auto &m) {
        m.functions[0].code.erase(m.functions[0].code.begin() + 8); // No acquired Console loan.
    });
    bad(copiedArguments(), [](auto &m) {
        m.functions[0].code.insert(m.functions[0].code.begin() + 9,
                                   {Constant{65, Type::U8}, ServiceOperation{16, service::Operation::Put, 0}});
    });
    auto explicitZeroObjects = forwarded();
    std::get<ServiceCall>(explicitZeroObjects.functions[0].code[4]).objectArguments = {0, 0};
    good(explicitZeroObjects);
    bad(explicitZeroObjects, [](auto &m) {
        std::get<ServiceCall>(m.functions[0].code[4]).objectArguments[1] = 24;
    });
    for (const int offset : {0, 16, 40})
        bad(copiedResult(), [=](auto &m) {
            std::get<ServiceCall>(m.functions[0].code[3]).resultOffset = offset;
        });
    bad(copiedResult(), [](auto &m) {
        m.classLayouts["Other"] = m.classLayouts.at("Reply");
        m.functions[0].objectSlots[48].className = "Other";
    });
    bad(copiedResult(), [](auto &m) {
        auto &f = m.functions[0];
        f.serviceSlots = {32}; // The exact result object overlaps its authority spill.
        std::get<BindServiceParameter>(f.code[0]).offset = 32;
        std::get<AcquireServiceLoan>(f.code[2]).offset = 32;
    });
    bad(copiedResult(), [](auto &m) {
        m.functions[0].slots[31] = Type::Bool; // Correct base, malformed physical leaf.
    });
    bad(copiedResult(), [](auto &m) {
        auto &code = m.functions[0].code;
        code.insert(code.begin() + 3, {Constant{0, Type::Bool}, Store{24, Type::Bool}});
    });
    for (const bool empty : {false, true}) {
        bad(copiedResult(empty), [](auto &m) {
            auto &code = m.functions[0].code;
            code.insert(code.end() - 1,
                        {AcquireServiceLoan{1, 16}, ServiceCall{"reply", 1, 48, {0}}, ReleaseServiceLoan{1}});
        });
        bad(copiedResult(empty), [](auto &m) {
            auto &code = m.functions[1].code;
            code.erase(code.end() - 2); // Incomplete return cannot initialize the caller's result.
        });
    }
    for (const auto &type : {Type::ConsoleSession, Type::ByteSpan, Type::OwnedBytes, Type::Ref})
        bad(copiedResult(), [=](auto &m) {
            m.functions[1].result = type;
        });
    bad(copiedResult(), [](auto &m) {
        m.classFields["Reply"] = {{Type::U64, 0, 1, false},
                                  {service::putResultType(), 1, 1, false},
                                  {Type::U8, 2, 1, false},
                                  {Type::U8, 3, 1, false},
                                  {Type::Bool, 4, 1, false},
                                  {Type::OwnedBytes, 5, 0, false}};
    });
    bad(copiedResult(), [](auto &m) {
        m.functions[0].code[3] = AggregateCall{"reply", {0}, 48};
    });
    bad(copiedResult(), [](auto &m) {
        m.functions[0].code.erase(m.functions[0].code.begin() + 4); // Returning data cannot escape a child loan.
    });
    bad(copiedResult(), [](auto &m) {
        m.functions[0].code.insert(m.functions[0].code.begin() + 3,
                                   {Constant{65, Type::U8}, ServiceOperation{16, service::Operation::Put, 0}});
    });
    bad(copiedResult(), [](auto &m) {
        m.functions[0].code[3] = ServiceOperation{16, service::Operation::Next, 48};
        m.functions[0].code.erase(m.functions[0].code.begin() + 4);
        m.functions[0].code.erase(m.functions[0].code.begin() + 2);
    }); // An ordinary helper result never relaxes the native report's exact type.
    // Same static report declaration, but inactive, ended or initialized along
    // the executed path: these must remain native lifetime/pristine checks.
    bad(
        sample(),
        [](auto &m) {
            m.functions[0].code.erase(m.functions[0].code.begin() + 1);
        },
        "service observation requires exact pristine active copied sample object");
    bad(
        sample(),
        [](auto &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 2, EndObject{40});
        },
        "service observation requires exact pristine active copied sample object");
    bad(
        sample(),
        [](auto &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 2,
                                       {Constant{0, Type::Bool}, Store{40, Type::Bool}});
        },
        "service observation cannot overwrite initialized sample storage");
    bad(
        sample(),
        [](auto &m) {
            const auto name = std::string(service::sampleName);
            m.classLayouts["OtherSample"] = m.classLayouts.at(name);
            m.classFields["OtherSample"] = m.classFields.at(name);
            m.functions[0].objectSlots.at(40).className = "OtherSample";
        },
        "service observation requires exact pristine active copied sample object");
    bad(
        sample(),
        [](auto &m) {
            m.enumCases.erase(std::string(service::putResultName));
            m.functions[0].code[2] = ServiceOperation{16, service::Operation::Put, 0};
        },
        "put requires closed enum result and no object storage");
    bad(
        sample(),
        [](auto &m) {
            m.functions[0].code[2] = ServiceOperation{16, service::Operation::Put, 0};
        },
        "missing or mistyped current value"); // Static declaration is valid; no current byte exists.
    bad(
        sample(),
        [](auto &m) {
            m.functions[0].frameBytes = 64;
            m.functions[0].serviceSlots.insert(64);
            std::get<ServiceOperation>(m.functions[0].code[2]).offset = 64;
        },
        "service operation requires active unsuspended capability provenance"); // Declared spill is not an entry root.
    bad(
        forwarded(),
        [](auto &m) {
            m.functions[0].frameBytes = 64;
            m.functions[0].serviceSlots.insert(64);
            std::get<AcquireServiceLoan>(m.functions[0].code[1]).offset = 64;
        },
        "service loan requires unsuspended parameter authority");
    for (const int id : {-1, 0}) {
        bad(
            forwarded(),
            [=](auto &m) {
                std::get<AcquireServiceLoan>(m.functions[0].code[1]).loanId = id;
            },
            "service loan identity cannot change static root or kind");
        bad(
            forwarded(),
            [=](auto &m) {
                std::get<ReleaseServiceLoan>(m.functions[0].code[5]).loanId = id;
            },
            "service release requires exactly one completed helper call");
    }
    for (const auto kind : {static_cast<service::Kind>(-1), static_cast<service::Kind>(999)})
        bad(
            forwarded(),
            [=](auto &m) {
                std::get<ReleaseServiceLoan>(m.functions[0].code[5]).kind = kind;
            },
            "service release requires exactly one completed helper call");
    // Same ID and root pass the source identity check; the second acquisition
    // still fails because the first loan is live on this path.
    bad(
        forwarded(),
        [](auto &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 2, AcquireServiceLoan{1, 16});
        },
        "service loan requires unsuspended parameter authority");
    bad(
        forwarded(),
        [](auto &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 2, AcquireServiceLoan{1, 16});
            std::get<ServiceOperation>(m.functions[1].code[3]).resultOffset = 24;
        },
        "put requires closed enum result and no object storage"); // Later static failure precedes earlier live-loan failure.
    auto reused = forwarded();
    auto &reusedCode = reused.functions[0].code;
    reusedCode.insert(reusedCode.end() - 1,
                      {AcquireServiceLoan{1, 16},
                       Constant{66, Type::U8},
                       Push{},
                       ServiceCall{"putter", 1, 0, {0, 0}},
                       ReleaseServiceLoan{1}});
    good(std::move(reused)); // A released lexical identity cannot preserve old called state.
    auto loop = forwarded();
    loop.functions[0].code = {BindServiceParameter{0, 16, service::Kind::Console},
                              Label{1},
                              AcquireServiceLoan{1, 16},
                              Constant{65, Type::U8},
                              Push{},
                              ServiceCall{"putter", 1, 0, {0, 0}},
                              ReleaseServiceLoan{1},
                              Constant{0, Type::Bool},
                              BranchFalse{2},
                              Jump{1},
                              Label{2},
                              EnumConstant{service::putResultType(), 0},
                              Return{}};
    good(loop);
    bad(loop, [](auto &m) {
        m.functions[0].code.erase(m.functions[0].code.begin() + 6);
    });
    bad(loop, [](auto &m) {
        m.functions[0].code.insert(m.functions[0].code.begin() + 9, AcquireServiceLoan{2, 16});
    });
    bad(sample(), [](auto &m) {
        m.functions[0].code.erase(m.functions[0].code.begin());
    });
    bad(sample(), [](auto &m) {
        std::get<BindServiceParameter>(m.functions[0].code[0]).kind = static_cast<service::Kind>(999);
    });
    bad(sample(), [](auto &m) {
        std::get<BindServiceParameter>(m.functions[0].code[0]).offset = 8;
    });
    bad(sample(), [](auto &m) {
        m.functions[0].parameters.clear();
    });
    bad(sample(), [](auto &m) {
        m.functions[0].slots[16] = Type::U64;
    });
    bad(sample(), [](auto &m) {
        m.functions[0].spanSlots.insert(56);
        m.functions[0].frameBytes = 64;
    });
    bad(sample(), [](auto &m) {
        m.functions[0].byteSlots[32] = true;
    });
    bad(sample(), [](auto &m) {
        m.functions[0].serviceSlots.insert(24);
    });
    bad(
        sample(),
        [](auto &m) {
            std::get<ServiceOperation>(m.functions[0].code[2]).offset = 32;
        },
        "service operation requires active unsuspended capability provenance");
    bad(
        sample(),
        [](auto &m) {
            std::get<ServiceOperation>(m.functions[0].code[2]).operation = static_cast<service::Operation>(999);
        },
        "unknown sealed service operation");
    bad(
        sample(),
        [](auto &m) {
            std::get<ServiceOperation>(m.functions[0].code[2]).resultOffset = 32;
        },
        "service observation requires exact pristine active copied sample object");
    bad(
        sample(),
        [](auto &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 3,
                                       ServiceOperation{16, service::Operation::Next, 40});
        },
        "service observation requires exact pristine active copied sample object");
    bad(
        sample(),
        [](auto &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 2, AcquireServiceLoan{1, 16});
        },
        "service operation requires active unsuspended capability provenance");
    bad(sample(), [](auto &m) {
        m.classLayouts[std::string(service::sampleName)][0] = Type::U64;
    });
    bad(sample(), [](auto &m) {
        m.enumCases[std::string(service::putResultName)] = 3;
    });
    bad(sample(), [](auto &m) {
        m.functions[0].name = "__au_runtime_console_next";
    });
    bad(sample(), [](auto &m) {
        m.functions[0].code.insert(m.functions[0].code.end() - 1, Load{16, Type::U64});
    });
    bad(forwarded(), [](auto &m) {
        m.functions[0].code[4] = Call{"putter"};
    });
    bad(forwarded(), [](auto &m) {
        m.functions[0].code[4] = AggregateCall{"putter", {0, 0}, 0};
    });
    bad(
        forwarded(),
        [](auto &m) {
            m.functions[0].code.erase(m.functions[0].code.begin() + 1);
        },
        "service helper requires distinct acquired loans in leading positions");
    bad(forwarded(), [](auto &m) {
        m.functions[0].code.erase(m.functions[0].code.begin() + 5);
    });
    bad(
        forwarded(),
        [](auto &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 2, ReleaseServiceLoan{1});
        },
        "service release requires exactly one completed helper call");
    bad(
        forwarded(),
        [](auto &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 5, ServiceCall{"putter", 1, 0, {0, 0}});
        },
        "service helper requires an unused loan with exact provenance");
    bad(
        forwarded(),
        [](auto &m) {
            std::get<ServiceCall>(m.functions[0].code[4]).loanId = 2;
        },
        "service helper requires distinct acquired loans in leading positions");
    bad(forwarded(), [](auto &m) {
        std::get<ServiceCall>(m.functions[0].code[4]).spanArguments = {16, 0};
    });
    // Loan validation precedes ordinary arguments; a ready loan reaches the
    // argument error without being consumed by the validation query itself.
    for (const auto &[state, diagnostic] : std::array<std::pair<int, const char *>, 3>{
             {{0, "service scalar argument mismatch"},
              {1, "service helper requires distinct acquired loans in leading positions"},
              {2, "service helper requires an unused loan with exact provenance"}}})
        bad(
            forwarded(),
            [=](auto &m) {
                auto &code = m.functions[0].code;
                if (state == 2)
                    code.insert(code.begin() + 5,
                                {Constant{65, Type::I64}, Push{}, ServiceCall{"putter", 1, 0, {0, 0}}});
                else {
                    code[2] = Constant{65, Type::I64};
                    if (state == 1)
                        code.erase(code.begin() + 1);
                }
            },
            diagnostic);
    bad(forwarded(), [](auto &m) {
        m.functions[0].code.insert(m.functions[0].code.begin() + 2,
                                   {Constant{1, Type::Bool}, BranchFalse{99}, AcquireServiceLoan{2, 16}, Label{99}});
    });
    bad(forwarded(), [](auto &m) {
        m.functions[0].code = {BindServiceParameter{0, 16, service::Kind::Console},
                               AcquireServiceLoan{1, 16},
                               ServiceCall{"caller", 1, 0, {0}},
                               ReleaseServiceLoan{1},
                               Return{}};
    });
    std::cout << "PASS sealed console service IR: " << checks << " independent checks\n";
    return 0;
}
