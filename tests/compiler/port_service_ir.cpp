// Independent Port IR mutations reuse the established service fixture machinery.
#define main console_service_regression
#include "console_service_ir.cpp"
#undef main
#include <fstream>
namespace {
Module portOperation(bool write = false) {
    Module m;
    m.enumCases[service::portWriteResultType().className] = 1;
    auto f = entry(write ? "port_write" : "port_read");
    f.parameters = {Type::PortRange};
    f.result = write ? service::portWriteResultType() : Type::U8;
    f.code = {BindServiceParameter{0, 16, service::Kind::Port}, Constant{7, Type::U64}};
    if (write)
        f.code.insert(f.code.end(), {Push{}, Constant{255, Type::U8}, Push{}});
    f.code.insert(
        f.code.end(),
        {ServiceOperation{
             16, write ? service::Operation::PortWrite8 : service::Operation::PortRead8, 0, service::Kind::Port},
         Return{}});
    m.functions.push_back(f);
    return m;
}
ServiceOperation &portOp(Module &m) {
    for (auto &op : m.functions[0].code)
        if (auto *service = std::get_if<ServiceOperation>(&op))
            return *service;
    throw Error("missing port operation");
}
Module portForwarded() {
    auto m = portOperation();
    auto caller = m.functions[0];
    caller.name = "port_ir_entry";
    caller.result = Type::I64;
    caller.code = {BindServiceParameter{0, 16, service::Kind::Port},
                   AcquireServiceLoan{1, 16, service::Kind::Port},
                   ServiceCall{"port_read", 1, 0, {0}, service::Kind::Port},
                   ReleaseServiceLoan{1, service::Kind::Port},
                   Constant{7, Type::U64},
                   Push{},
                   Constant{255, Type::U8},
                   Push{},
                   ServiceOperation{16, service::Operation::PortWrite8, 0, service::Kind::Port},
                   Constant{42, Type::I64},
                   Return{}};
    m.functions.push_back(caller);
    return m;
}
Module portCopied(int shape) {
    auto m = copiedArguments(shape);
    m.enumCases[service::portWriteResultType().className] = 1;
    for (auto &f : m.functions) {
        f.parameters[0] = Type::PortRange;
        for (auto &i : f.code) {
            if (auto *v = std::get_if<BindServiceParameter>(&i))
                v->kind = service::Kind::Port;
            if (auto *v = std::get_if<AcquireServiceLoan>(&i))
                v->kind = service::Kind::Port;
            if (auto *v = std::get_if<ReleaseServiceLoan>(&i))
                v->kind = service::Kind::Port;
            if (auto *v = std::get_if<ServiceCall>(&i))
                v->kind = service::Kind::Port;
        }
    }
    return m;
}
} // namespace
int main(int argc, char **argv) {
    need(static_cast<int>(service::Kind::Port) == 4 && static_cast<int>(service::Operation::PortRead8) == 6 &&
             static_cast<int>(service::Operation::PortWrite8) == 7,
         "permanent Port wire identities changed");
    need(static_cast<int>(Type::PortRange.kind) == 19, "permanent Port type identity changed");
    for (bool write : {false, true}) {
        const auto checked = validate(portOperation(write));
        X86Emitter emitter;
        (void)emitter.emit(checked);
        const auto facts = emitter.stackFactsJson(checked);
        const auto function = jsonMember(jsonMember(facts, "functions"), write ? "port_write" : "port_read");
        const auto calls = jsonMember(jsonMember(function, "service_abi"), "calls");
        need(jsonMember(calls, write ? "__au_runtime_port_write8" : "__au_runtime_port_read8") ==
                 (write ? "{\"sysv_arguments\":4,\"result_max\":0}" : "{\"sysv_arguments\":3,\"result_max\":255}"),
             "Port runtime ABI facts must retain exact widths and canonical result bounds");
        good(portOperation(write));
        for (int kind : {-1, 0, 1, 2, 3, 5, 999})
            bad(portOperation(write), [=](auto &m) {
                portOp(m).kind = static_cast<service::Kind>(kind);
            });
        for (int op : {-1, 0, 1, 2, 3, 4, 5, 8, 999})
            bad(portOperation(write), [=](auto &m) {
                portOp(m).operation = static_cast<service::Operation>(op);
            });
        for (int slot : {0, 8, 24, 32})
            bad(portOperation(write), [=](auto &m) {
                portOp(m).offset = slot;
            });
        bad(portOperation(write), [](auto &m) {
            portOp(m).resultOffset = 32;
        });
        bad(portOperation(write), [](auto &m) {
            m.functions[0].code.erase(m.functions[0].code.begin());
        });
        bad(portOperation(write), [](auto &m) {
            m.functions[0].serviceSlots.clear();
        });
        bad(portOperation(write), [](auto &m) {
            std::get<BindServiceParameter>(m.functions[0].code[0]).index = 1;
        });
        for (int slot : {8, 16}) {
            bad(portOperation(write), [=](auto &m) {
                m.functions[0].slots[slot] = Type::U64;
            });
            bad(portOperation(write), [=](auto &m) {
                m.classLayouts["Alias"] = {Type::U64};
                m.functions[0].objectSlots[slot] = {"Alias", false};
                m.functions[0].slots[slot] = Type::U64;
            });
        }
        for (auto type : {Type::I64, Type::U8, Type::Bool})
            bad(portOperation(write), [=](auto &m) {
                m.functions[0].code[1] = Constant{1, type};
            });
        bad(portOperation(write), [](auto &m) {
            m.functions[0].result = Type::U64;
        });
        bad(portOperation(write), [](auto &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 1, AcquireServiceLoan{1, 16, service::Kind::Port});
        });
        for (auto type :
             {Type::ConsoleSession, Type::DisplaySession, Type::IommuEventSession, Type::CallSession, Type::PortRange})
            bad(portOperation(write), [=](auto &m) {
                m.functions[0].parameters.push_back(type);
            });
    }
    for (auto type : {Type::U64, Type::I64, Type::Bool})
        bad(portOperation(true), [=](auto &m) {
            m.functions[0].code[3] = Constant{1, type};
        });
    for (int index : {2, 4})
        bad(portOperation(true), [=](auto &m) {
            m.functions[0].code.erase(m.functions[0].code.begin() + index);
        });
    bad(portOperation(false), [](auto &m) {
        m.functions[0].code[1] = Constant{256, Type::U8};
    });
    bad(portOperation(false), [](auto &m) {
        m.functions[0].code.insert(m.functions[0].code.begin() + 2, Push{});
    });
    bad(portOperation(true), [](auto &m) {
        m.functions[0].code[3] = Constant{256, Type::U8};
    });
    bad(portOperation(true), [](auto &m) {
        m.functions[0].code[3] = EnumConstant{service::portWriteResultType(), 0};
    });
    bad(portOperation(true), [](auto &m) {
        m.functions[0].code = {BindServiceParameter{0, 16, service::Kind::Port},
                               EnumConstant{service::portWriteResultType(), 1},
                               Return{}};
    });
    for (int count : {0, 2, 256})
        bad(portOperation(true), [=](auto &m) {
            m.enumCases[service::portWriteResultType().className] = count;
        });
    good(portForwarded());
    for (int index : {1, 3})
        bad(portForwarded(), [=](auto &m) {
            auto &c = m.functions.back().code;
            c.erase(c.begin() + index);
        });
    bad(portForwarded(), [](auto &m) {
        std::get<ServiceCall>(m.functions.back().code[2]).loanId = 2;
    });
    bad(portForwarded(), [](auto &m) {
        std::get<ServiceCall>(m.functions.back().code[2]).kind = service::Kind::Call;
    });
    bad(portForwarded(), [](auto &m) {
        std::get<ServiceCall>(m.functions.back().code[2]).spanArguments = {16};
    });
    bad(portForwarded(), [](auto &m) {
        m.functions.back().code[2] = Call{"port_read"};
    });
    bad(portForwarded(), [](auto &m) {
        auto &c = m.functions.back().code;
        c.insert(c.begin() + 3, c[2]);
    });
    for (int shape : {0, 1, 2}) {
        good(portCopied(shape));
        bad(portCopied(shape), [](auto &m) {
            copiedCall(m).resultOffset = 16;
        });
        bad(portCopied(shape), [](auto &m) {
            copiedCall(m).objectArguments[1] = 16;
        });
    }
    need(argc == 1 || argc == 2, "expected optional assembly destination");
    if (argc == 2) {
        std::ofstream out(argv[1]);
        out << X86Emitter{}.emit(validate(portForwarded()));
        out.flush();
        need(static_cast<bool>(out), "cannot write Port IR assembly");
    }
    std::cout << "PASS sealed Port IR: " << checks << " checks\n";
}
