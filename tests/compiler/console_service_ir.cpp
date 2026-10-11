// Independently authored IR: no parser, semantic lowering or source fixtures.
#include "ir_verify.hpp"
#include "x86.hpp"
#include <functional>
#include <iostream>
#include <tuple>
using namespace aurora;
using namespace aurora::ir;
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
void good(Module m) {
    X86Emitter emitter;
    const auto text = emitter.emit(validate(std::move(m)));
    for (const auto &[name, facts] : emitter.stackFacts())
        for (const auto &[host, arguments, maximum] : {std::tuple{"__au_runtime_console_put", 3, 1},
                                                       std::tuple{"__au_runtime_display_pixel", 7, 1},
                                                       std::tuple{"__au_runtime_iommu_event_acknowledge", 2, 2}})
            if (facts.calls.contains(host)) {
                const auto &call = facts.serviceCalls.at(host);
                need(call.arguments == arguments && call.resultMax == maximum,
                     "scalar host ABI facts disagree with independently expected native contract");
            }
    need(text.find("__au_runtime_bytes_") == std::string::npos, "service graph depends on byte-owner runtime");
    need(text.find(".globl caller") == std::string::npos, "ordinary public service entry");
    ++checks;
}
void bad(Module m, const std::function<void(Module &)> &mutate) {
    mutate(m);
    try {
        (void)validate(std::move(m));
    } catch (const Error &) {
        ++checks;
        return;
    }
    throw Error("hostile service IR unexpectedly accepted");
}
} // namespace
int main() {
    good(sample());
    good(forwarded());
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
    bad(sample(), [](auto &m) {
        std::get<ServiceOperation>(m.functions[0].code[2]).offset = 32;
    });
    bad(sample(), [](auto &m) {
        std::get<ServiceOperation>(m.functions[0].code[2]).operation = static_cast<service::Operation>(999);
    });
    bad(sample(), [](auto &m) {
        std::get<ServiceOperation>(m.functions[0].code[2]).resultOffset = 32;
    });
    bad(sample(), [](auto &m) {
        m.functions[0].code.insert(m.functions[0].code.begin() + 3, ServiceOperation{16, service::Operation::Next, 40});
    });
    bad(sample(), [](auto &m) {
        m.functions[0].code.insert(m.functions[0].code.begin() + 2, AcquireServiceLoan{1, 16});
    });
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
    bad(forwarded(), [](auto &m) {
        m.functions[0].code.erase(m.functions[0].code.begin() + 1);
    });
    bad(forwarded(), [](auto &m) {
        m.functions[0].code.erase(m.functions[0].code.begin() + 5);
    });
    bad(forwarded(), [](auto &m) {
        m.functions[0].code.insert(m.functions[0].code.begin() + 2, ReleaseServiceLoan{1});
    });
    bad(forwarded(), [](auto &m) {
        m.functions[0].code.insert(m.functions[0].code.begin() + 5, ServiceCall{"putter", 1, 0, {0, 0}});
    });
    bad(forwarded(), [](auto &m) {
        std::get<ServiceCall>(m.functions[0].code[4]).loanId = 2;
    });
    bad(forwarded(), [](auto &m) {
        std::get<ServiceCall>(m.functions[0].code[4]).spanArguments = {16, 0};
    });
    bad(forwarded(), [](auto &m) {
        m.functions[0].code[2] = Constant{65, Type::I64};
    });
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
