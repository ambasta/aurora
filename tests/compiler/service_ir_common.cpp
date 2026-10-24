#include "service_ir_common.hpp"

namespace aurora::test::service_ir {
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
Module copiedResult(bool empty) {
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
Module copiedArguments(int shape, bool paired) {
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
void bad(Module m, const std::function<void(Module &)> &mutate, const std::string &expected) {
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
Module displayPixel() {
    Module m;
    canonicalTypes(m);
    m.enumCases[std::string(service::displayPutResultName)] = 2;
    m.enumCases[std::string(service::displayCompletionName)] = 2;
    auto f = entry("pixel_entry");
    f.parameters = {Type::DisplaySession};
    f.result = service::displayPutResultType();
    f.code = {BindServiceParameter{0, 16, service::Kind::Display},
              Constant{7, Type::U64},
              Push{},
              Constant{9, Type::U64},
              Push{},
              Constant{11, Type::U8},
              Push{},
              Constant{13, Type::U8},
              Push{},
              Constant{17, Type::U8},
              Push{},
              ServiceOperation{16, service::Operation::Pixel, 0, service::Kind::Display},
              Return{}};
    m.functions.push_back(f);
    return m;
}
Module displayForwarded() {
    auto m = displayPixel();
    auto caller = entry("display_caller");
    caller.parameters = {Type::DisplaySession};
    caller.result = service::displayPutResultType();
    caller.code = {BindServiceParameter{0, 16, service::Kind::Display},
                   AcquireServiceLoan{1, 16, service::Kind::Display},
                   ServiceCall{"pixel_entry", 1, 0, {0}, service::Kind::Display},
                   ReleaseServiceLoan{1, service::Kind::Display},
                   Return{}};
    m.functions.push_back(caller);
    return m;
}
} // namespace aurora::test::service_ir
