// Independently authored Display service IR cases; run by display-service-ir.
#include "service_ir_common.hpp"
void aurora::test::service_ir::displayServiceCases() {
    good(displayPixel());
    good(displayForwarded());
    bad(displayPixel(), [](auto &m) {
        std::get<BindServiceParameter>(m.functions[0].code[0]).kind = service::Kind::Console;
    });
    bad(displayPixel(), [](auto &m) {
        m.functions[0].parameters[0] = Type::ConsoleSession;
    });
    bad(
        displayPixel(),
        [](auto &m) {
            std::get<ServiceOperation>(m.functions[0].code[11]).kind = service::Kind::Console;
        },
        "service operation kind does not match active capability");
    bad(displayPixel(), [](auto &m) {
        std::get<ServiceOperation>(m.functions[0].code[11]).operation = service::Operation::Put;
    });
    bad(displayPixel(), [](auto &m) {
        std::get<ServiceOperation>(m.functions[0].code[11]).operation = service::Operation::Next;
    });
    bad(
        displayPixel(),
        [](auto &m) {
            std::get<ServiceOperation>(m.functions[0].code[11]).resultOffset = 24;
        },
        "pixel requires closed enum result and no object storage");
    bad(displayPixel(), [](auto &m) {
        m.functions[0].result = service::putResultType();
    });
    bad(
        displayPixel(),
        [](auto &m) {
            m.functions[0].code[1] = Constant{7, Type::I64};
        },
        "pixel argument type mismatch");
    bad(
        displayPixel(),
        [](auto &m) {
            m.functions[0].code[9] = Constant{17, Type::U64};
        },
        "pixel argument type mismatch");
    bad(displayPixel(), [](auto &m) {
        m.functions[0].code.erase(m.functions[0].code.begin() + 10);
    });
    bad(displayPixel(), [](auto &m) {
        m.functions[0].slots[8] = Type::U64;
    });
    bad(displayPixel(), [](auto &m) {
        m.functions[0].spanSlots.insert(32);
    });
    bad(displayPixel(), [](auto &m) {
        m.functions[0].serviceSlots.insert(24);
    });
    bad(displayPixel(), [](auto &m) {
        m.functions[0].parameters.push_back(Type::ConsoleSession);
    });
    bad(displayPixel(), [](auto &m) {
        m.functions[0].parameters.push_back(Type::DisplaySession);
    });
    bad(displayPixel(), [](auto &m) {
        m.functions[0].parameters.push_back(Type::ByteRegion);
    });
    bad(displayPixel(), [](auto &m) {
        m.functions[0].parameters.push_back(Type::OwnedBytes);
    });
    bad(displayPixel(), [](auto &m) {
        m.functions[0].parameters.push_back(Type::ByteSpan);
    });
    bad(displayPixel(), [](auto &m) {
        m.enumCases[std::string(service::displayPutResultName)] = 3;
    });
    bad(displayPixel(), [](auto &m) {
        m.enumCases[std::string(service::displayCompletionName)] = 1;
    });
    bad(
        displayPixel(),
        [](auto &m) {
            m.enumCases.erase(std::string(service::displayPutResultName));
            m.functions[0].result = Type::I64; // Keep signature admission from hiding the operation result check.
        },
        "pixel requires closed enum result and no object storage");
    bad(
        displayForwarded(),
        [](auto &m) {
            std::get<AcquireServiceLoan>(m.functions[1].code[1]).kind = service::Kind::Console;
        },
        "service loan requires unsuspended parameter authority");
    bad(displayForwarded(), [](auto &m) {
        std::get<ServiceCall>(m.functions[1].code[2]).kind = service::Kind::Console;
    });
    bad(
        displayForwarded(),
        [](auto &m) {
            std::get<ReleaseServiceLoan>(m.functions[1].code[3]).kind = service::Kind::Console;
        },
        "service release requires exactly one completed helper call");
    bad(displayForwarded(), [](auto &m) {
        m.functions[0].parameters[0] = Type::ConsoleSession;
        std::get<BindServiceParameter>(m.functions[0].code[0]).kind = service::Kind::Console;
    });
    bad(sample(), [](auto &m) {
        std::get<BindServiceParameter>(m.functions[0].code[0]).kind = service::Kind::Display;
    });
    bad(sample(), [](auto &m) {
        std::get<ServiceOperation>(m.functions[0].code[2]).operation = service::Operation::Pixel;
    });
    for (const auto *name : {"__au_runtime_display_pixel",
                             "__au_runtime_display_entry",
                             "__au_runtime_console_next",
                             "__au_runtime_console_put"}) {
        bad(displayPixel(), [=](auto &m) {
            m.functions[0].name = name;
        });
        bad(displayPixel(), [=](auto &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 1, Call{name});
        });
    }
}
