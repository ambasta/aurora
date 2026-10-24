// Independent Serve IR admission and register-only ABI fixture.
#include "service_ir_common.hpp"
#include <fstream>
namespace {
Module serveOperation() {
    Module m;
    const auto result = service::serveRequestType();
    const auto status = service::serveStatusType();
    m.enumCases[status.className] = 2;
    m.classLayouts[result.className] = {status, Type::U64};
    m.classFields[result.className] = {{status, 0, 1, false}, {Type::U64, 1, 1, false}};
    auto f = entry("serve_ir_operation");
    f.parameters = {Type::ServeSession};
    f.result = Type::U64;
    f.objectSlots[32] = {result.className, false};
    f.slots = {{32, status}, {24, Type::U64}};
    f.code = {BindServiceParameter{0, 16, service::Kind::Serve},
              BeginObject{32},
              Constant{42, Type::U64},
              ServiceOperation{16, service::Operation::ServeExchange, 32, service::Kind::Serve},
              EndObject{32},
              Constant{42, Type::U64},
              Return{}};
    m.functions.push_back(f);
    return m;
}
ServiceOperation &serveOp(Module &m) {
    return std::get<ServiceOperation>(m.functions[0].code[3]);
}
Module serveForwarded() {
    auto m = serveOperation();
    auto f = entry("serve_ir_entry");
    f.parameters = {Type::ServeSession};
    f.result = Type::U64;
    f.code = {BindServiceParameter{0, 16, service::Kind::Serve},
              AcquireServiceLoan{1, 16, service::Kind::Serve},
              ServiceCall{"serve_ir_operation", 1, 0, {0}, service::Kind::Serve},
              ReleaseServiceLoan{1, service::Kind::Serve},
              Return{}};
    m.functions.push_back(f);
    return m;
}
} // namespace
int main(int argc, char **argv) {
    need(static_cast<int>(service::Kind::Serve) == 5 && static_cast<int>(service::Operation::ServeExchange) == 8 &&
             static_cast<int>(TypeKind::ServeSession) == 20,
         "appended Serve wire identities changed");
    for (bool call : {false, true})
        for (bool port : {false, true}) {
            const auto legacy = service::supportedGroupBitmap(call, port, false);
            need(service::supportedGroupBitmap(call, port, true) == legacy + (std::int64_t{1} << 32),
                 "Serve must append exact full-width singleton group bit");
        }
    good(serveOperation());
    good(serveForwarded());
    const auto checked = validate(serveOperation());
    X86Emitter emitter;
    (void)emitter.emit(checked);
    const auto facts = emitter.stackFactsJson(checked);
    const auto f = jsonMember(jsonMember(facts, "functions"), "serve_ir_operation");
    need(jsonMember(jsonMember(jsonMember(f, "service_abi"), "calls"), "__au_runtime_serve_exchange") ==
             "{\"sysv_arguments\":3,\"result_max\":1}",
         "Serve runtime facts must retain exact register count and status bound");
    need(jsonMember(jsonMember(f, "service_abi"), "record") ==
             "{\"parameters\":[[\"builtin::ServeSession\",16]],\"result_bytes\":8}",
         "Serve singleton entry facts changed");
    for (int kind : {-1, 0, 1, 2, 3, 4, 6, 999})
        bad(serveOperation(), [=](auto &m) {
            serveOp(m).kind = static_cast<service::Kind>(kind);
        });
    for (int op : {-1, 0, 1, 2, 3, 4, 5, 6, 7, 9, 999})
        bad(serveOperation(), [=](auto &m) {
            serveOp(m).operation = static_cast<service::Operation>(op);
        });
    for (int offset : {0, 8, 24, 32})
        bad(serveOperation(), [=](auto &m) {
            serveOp(m).offset = offset;
        });
    for (int offset : {0, 8, 16, 24, 40})
        bad(serveOperation(), [=](auto &m) {
            serveOp(m).resultOffset = offset;
        });
    for (auto type : {Type::I64, Type::U8, Type::Bool})
        bad(serveOperation(), [=](auto &m) {
            m.functions[0].code[2] = Constant{1, type};
        });
    for (auto type : {Type::ConsoleSession,
                      Type::DisplaySession,
                      Type::IommuEventSession,
                      Type::CallSession,
                      Type::Com1UartGrant,
                      Type::ServeSession,
                      Type::ByteRegion})
        bad(serveOperation(), [=](auto &m) {
            m.functions[0].parameters.push_back(type);
        });
    bad(serveOperation(), [](auto &m) {
        m.functions[0].parameters[0].className = "forged";
    });
    bad(serveOperation(), [](auto &m) {
        m.functions[0].parameters[0].length = 1;
    });
    bad(serveOperation(), [](auto &m) {
        m.functions[0].result = Type::ServeSession;
    });
    bad(serveOperation(), [](auto &m) {
        m.classLayouts["Forged"] = {Type::ServeSession};
        m.classFields["Forged"] = {{Type::ServeSession, 0, 1, false}};
    });
    bad(serveOperation(), [](auto &m) {
        m.functions[0].serviceSlots.clear();
    });
    bad(serveOperation(), [](auto &m) {
        m.functions[0].code.erase(m.functions[0].code.begin());
    });
    bad(serveOperation(), [](auto &m) {
        m.functions[0].code.insert(m.functions[0].code.begin() + 3, AcquireServiceLoan{1, 16, service::Kind::Serve});
    });
    for (int count : {0, 1, 3, 256})
        bad(serveOperation(), [=](auto &m) {
            m.enumCases[service::serveStatusType().className] = count;
        });
    for (auto type : {Type::I64, Type::U64, service::callStatusType()})
        bad(serveOperation(), [=](auto &m) {
            m.enumCases[service::callStatusType().className] = 3;
            m.classLayouts[service::serveRequestType().className][0] = type;
        });
    bad(serveOperation(), [](auto &m) {
        m.classLayouts[service::serveRequestType().className][1] = Type::I64;
    });
    bad(serveOperation(), [](auto &m) {
        m.classFields[service::serveRequestType().className][1].firstLeaf = 0;
    });
    bad(serveForwarded(), [](auto &m) {
        std::get<ServiceCall>(m.functions.back().code[2]).kind = service::Kind::Call;
    });
    bad(serveForwarded(), [](auto &m) {
        m.functions.back().code[2] = Call{"serve_ir_operation"};
    });
    bad(serveForwarded(), [](auto &m) {
        auto &code = m.functions.back().code;
        code.insert(code.begin() + 3, code[2]);
    });
    for (int index : {1, 3})
        bad(serveForwarded(), [=](auto &m) {
            auto &code = m.functions.back().code;
            code.erase(code.begin() + index);
        });
    need(argc == 1 || argc == 2, "expected optional assembly destination");
    if (argc == 2) {
        std::ofstream out(argv[1]);
        out << X86Emitter{}.emit(validate(serveForwarded()));
        out.flush();
        need(static_cast<bool>(out), "cannot write Serve IR assembly");
    }
    std::cout << "PASS sealed Serve IR: " << checks << " checks\n";
}
