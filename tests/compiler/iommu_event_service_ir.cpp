// Independent hostile IR for the third sealed kind; preserve single-kind regressions.
#define DISPLAY_SERVICE_IR_MAIN display_service_regression
#include "display_service_ir.cpp"
#undef DISPLAY_SERVICE_IR_MAIN
#include <fstream>
namespace {
constexpr auto eventKind = service::Kind::IommuEvent;
void eventTypes(Module &m) {
    canonicalTypes(m);
    const auto name = std::string(service::eventSampleName);
    m.classLayouts[name] = {service::eventPollResultType(), Type::U64, Type::U64, Type::U64};
    m.classFields[name] = {{service::eventPollResultType(), 0, 1, false},
                           {Type::U64, 1, 1, false},
                           {Type::U64, 2, 1, false},
                           {Type::U64, 3, 1, false}};
    m.enumCases[std::string(service::eventPollResultName)] = 4;
    m.enumCases[std::string(service::eventAckResultName)] = 3;
    m.enumCases[std::string(service::eventIntakeCompletionName)] = 7;
}
F eventEntry(const std::string &name, bool pair = false, bool consoleFirst = false) {
    F f;
    f.name = name;
    f.parameters = {Type::IommuEventSession};
    if (pair)
        f.parameters = consoleFirst ? std::vector<Type>{Type::ConsoleSession, Type::IommuEventSession}
                                    : std::vector<Type>{Type::IommuEventSession, Type::ConsoleSession};
    f.result = Type::U64;
    f.frameBytes = 64;
    for (std::size_t index = 0; index < f.parameters.size(); ++index) {
        const int offset = 16 * (static_cast<int>(index) + 1);
        f.serviceSlots.insert(offset);
        f.code.push_back(BindServiceParameter{static_cast<int>(index), offset, service::kind(f.parameters[index])});
    }
    return f;
}
void reportStorage(F &f) {
    f.objectSlots[64] = {std::string(service::eventSampleName), false};
    f.slots = {{64, service::eventPollResultType()}, {56, Type::U64}, {48, Type::U64}, {40, Type::U64}};
}
Module eventPoll(bool pair = false, bool consoleFirst = false) {
    Module m;
    eventTypes(m);
    auto f = eventEntry("event_sample", pair, consoleFirst);
    reportStorage(f);
    f.result = service::eventSampleType();
    f.code.insert(f.code.end(),
                  {BeginObject{64},
                   ServiceOperation{consoleFirst ? 32 : 16, service::Operation::IommuPoll, 64, eventKind},
                   ReturnObject{64}});
    m.functions.push_back(f);
    return m;
}
Module eventAcknowledge() {
    Module m;
    eventTypes(m);
    auto f = eventEntry("event_acknowledge");
    f.result = service::eventAckResultType();
    f.code.insert(f.code.end(), {ServiceOperation{16, service::Operation::IommuAcknowledge, 0, eventKind}, Return{}});
    m.functions.push_back(f);
    return m;
}
Module eventForwarded(bool consoleFirst = false, bool subset = false) {
    auto m = eventPoll(!subset, consoleFirst);
    auto caller = eventEntry("event_ir_entry", true);
    reportStorage(caller);
    ServiceCall call{"event_sample", 1, 64, subset ? std::vector<int>{0} : std::vector<int>{0, 0}, eventKind};
    if (!subset) {
        if (consoleFirst) {
            call.loanId = 2;
            call.kind = service::Kind::Console;
            call.additionalServices = {{1, eventKind}};
        } else {
            call.additionalServices = {{2, service::Kind::Console}};
        }
    }
    caller.code.insert(caller.code.end(), {BeginObject{64}, AcquireServiceLoan{1, 16, eventKind}});
    if (!subset)
        caller.code.push_back(AcquireServiceLoan{2, 32, service::Kind::Console});
    else // An unrelated Console root remains usable while Event is suspended.
        caller.code.insert(
            caller.code.end(),
            {Constant{65, Type::U8}, ServiceOperation{32, service::Operation::Put, 0, service::Kind::Console}});
    caller.code.push_back(call);
    if (!subset)
        caller.code.push_back(ReleaseServiceLoan{2, service::Kind::Console});
    caller.code.insert(caller.code.end(),
                       {ReleaseServiceLoan{1, eventKind}, Load{48, Type::U64}, EndObject{64}, Return{}});
    m.functions.push_back(caller);
    return m;
}
ServiceOperation &pollOperation(Module &m) {
    return std::get<ServiceOperation>(m.functions.front().code[m.functions.front().parameters.size() + 1]);
}
ServiceCall &eventCall(Module &m) {
    for (auto &instruction : m.functions.back().code)
        if (auto *call = std::get_if<ServiceCall>(&instruction))
            return *call;
    throw Error("missing fixture call");
}
Module executedEvent() {
    auto m = eventForwarded(true);
    // The reversed helper performs Console output before returning four copied
    // qwords through hidden R10. The caller reads the copied third qword.
    auto &callee = m.functions.front();
    callee.code.insert(
        callee.code.begin() + 2,
        {Constant{65, Type::U8}, ServiceOperation{16, service::Operation::Put, 0, service::Kind::Console}});
    return m;
}
} // namespace
int main(int argc, char **argv) {
    display_service_regression();
    good(eventPoll());
    good(eventPoll(true));
    good(eventPoll(true, true));
    good(eventAcknowledge());
    good(eventForwarded());
    good(eventForwarded(true));
    good(eventForwarded(false, true));
    good(executedEvent());
    for (auto op : {service::Operation::Next,
                    service::Operation::Put,
                    service::Operation::Pixel,
                    static_cast<service::Operation>(999)})
        bad(eventPoll(), [=](auto &m) {
            pollOperation(m).operation = op;
        });
    for (auto kind : {service::Kind::Console, service::Kind::Display, static_cast<service::Kind>(999)})
        bad(eventPoll(), [=](auto &m) {
            pollOperation(m).kind = kind;
        });
    for (int offset : {0, 8, 32, 56})
        bad(eventPoll(), [=](auto &m) {
            pollOperation(m).offset = offset;
        });
    for (int offset : {0, 16, 56})
        bad(eventPoll(), [=](auto &m) {
            pollOperation(m).resultOffset = offset;
        });
    bad(eventPoll(), [](auto &m) {
        m.functions[0].code.erase(m.functions[0].code.begin());
    });
    bad(eventPoll(), [](auto &m) {
        m.functions[0].code.erase(m.functions[0].code.begin() + 1);
    });
    bad(eventPoll(), [](auto &m) {
        m.functions[0].code.insert(m.functions[0].code.begin() + 2, AcquireServiceLoan{1, 16, eventKind});
    });
    bad(eventPoll(), [](auto &m) {
        m.functions[0].code.insert(m.functions[0].code.begin() + 3, pollOperation(m));
    });
    for (int offset : {64, 56, 48, 40})
        bad(eventPoll(), [=](auto &m) {
            const auto type = m.functions[0].slots.at(offset);
            const Instruction value =
                type.isEnum() ? Instruction{EnumConstant{type, 0}} : Instruction{Constant{0, type}};
            m.functions[0].code.insert(m.functions[0].code.begin() + 2, {value, Store{offset, type}});
        });
    bad(eventPoll(), [](auto &m) {
        m.functions[0].slots[16] = Type::U64;
    });
    bad(eventPoll(), [](auto &m) {
        const auto name = std::string(service::eventSampleName);
        m.classLayouts["OtherEventSample"] = m.classLayouts.at(name);
        m.classFields["OtherEventSample"] = m.classFields.at(name);
        m.functions[0].objectSlots[64].className = "OtherEventSample";
    }, "service observation requires exact pristine active copied sample object");
    bad(eventPoll(), [](auto &m) {
        m.functions[0].result = service::sampleType();
    });
    for (auto type : {Type::ConsoleSession, Type::DisplaySession})
        bad(eventPoll(), [=](auto &m) {
            m.functions[0].parameters[0] = type;
        });
    for (bool reversed : {false, true}) {
        bad(eventPoll(true, reversed), [=](auto &m) {
            auto &f = m.functions[0];
            const int index = reversed ? 0 : 1;
            f.parameters[index] = Type::DisplaySession;
            std::get<BindServiceParameter>(f.code[index]).kind = service::Kind::Display;
        });
        bad(eventPoll(true, reversed), [](auto &m) {
            m.functions[0].parameters.push_back(Type::DisplaySession);
        });
        bad(eventForwarded(reversed), [](auto &m) {
            eventCall(m).kind = service::Kind::Display;
        });
        bad(eventForwarded(reversed), [](auto &m) {
            eventCall(m).additionalServices[0].loanId = eventCall(m).loanId;
        });
        bad(eventForwarded(reversed), [](auto &m) {
            eventCall(m).resultOffset = 56;
        });
        bad(eventForwarded(reversed), [](auto &m) {
            auto &code = m.functions.back().code;
            for (auto &instruction : code)
                if (std::holds_alternative<ServiceCall>(instruction)) {
                    instruction = Call{"event_sample"};
                    break;
                }
        });
        bad(eventForwarded(reversed), [](auto &m) {
            auto &code = m.functions.back().code;
            code.erase(std::find_if(code.begin(), code.end(), [](auto &i) {
                return std::holds_alternative<ReleaseServiceLoan>(i);
            }));
        });
        bad(eventForwarded(reversed), [](auto &m) {
            auto &code = m.functions.back().code;
            code.insert(code.end() - 1, ReleaseServiceLoan{1, eventKind});
        });
        bad(eventForwarded(reversed), [](auto &m) {
            auto &code = m.functions.back().code;
            code.insert(code.begin() + 5, ServiceOperation{16, service::Operation::IommuAcknowledge, 0, eventKind});
        });
        bad(eventForwarded(reversed), [](auto &m) {
            auto &code = m.functions.back().code;
            code.insert(code.end() - 1, AcquireServiceLoan{1, 32, service::Kind::Console});
        }, "service loan identity cannot change static root or kind"); // Both sites match exact entry bindings.
    }
    for (bool reversed : {false, true}) {
        for (int offset : {64, 56, 48, 40})
            bad(eventForwarded(reversed), [=](auto &m) {
                auto &caller = m.functions.back();
                const auto type = caller.slots.at(offset);
                const Instruction value =
                    type.isEnum() ? Instruction{EnumConstant{type, 0}} : Instruction{Constant{0, type}};
                caller.code.insert(caller.code.begin() + 3, {value, Store{offset, type}});
            });
        bad(eventForwarded(reversed), [](auto &m) {
            for (auto &instruction : m.functions.back().code)
                if (auto *release = std::get_if<ReleaseServiceLoan>(&instruction)) {
                    release->kind = service::Kind::Display;
                    break;
                }
        });
        bad(eventForwarded(reversed), [](auto &m) {
            for (auto &instruction : m.functions.back().code)
                if (auto *loan = std::get_if<AcquireServiceLoan>(&instruction)) {
                    loan->offset = 32;
                    break;
                }
        });
        bad(eventForwarded(reversed), [](auto &m) {
            auto &code = m.functions.back().code;
            code.insert(code.begin() + 5, ReleaseServiceLoan{1, eventKind});
        });
        bad(eventForwarded(reversed), [](auto &m) {
            auto &code = m.functions.back().code;
            const auto call = eventCall(m);
            code.insert(code.begin() + 6, call);
        });
        bad(eventForwarded(reversed), [](auto &m) {
            auto &code = m.functions.back().code;
            code.insert(code.begin() + 3, AcquireServiceLoan{1, 16, eventKind});
        });
    }
    bad(eventPoll(), [](auto &m) {
        m.enumCases.erase(std::string(service::eventPollResultName));
    });
    bad(eventAcknowledge(), [](auto &m) {
        m.enumCases.erase(std::string(service::eventAckResultName));
        m.functions[0].result = Type::I64; // Preserve the operation-result failure after valid metadata admission.
    }, "acknowledge requires closed enum result and no object storage");
    bad(eventPoll(true), [](auto &m) {
        std::get<BindServiceParameter>(m.functions[0].code[1]).offset = 16;
    });
    bad(eventPoll(true), [](auto &m) {
        std::get<BindServiceParameter>(m.functions[0].code[1]).index = 0;
    });
    bad(eventAcknowledge(), [](auto &m) {
        std::get<ServiceOperation>(m.functions[0].code[1]).resultOffset = 64;
    }, "acknowledge requires closed enum result and no object storage");
    for (std::size_t field = 0; field < 4; ++field) {
        bad(eventPoll(), [=](auto &m) {
            m.classLayouts[std::string(service::eventSampleName)][field] = Type::Bool;
        });
        bad(eventPoll(), [=](auto &m) {
            m.classFields[std::string(service::eventSampleName)][field].firstLeaf = 4;
        });
        bad(eventPoll(), [=](auto &m) {
            m.classFields[std::string(service::eventSampleName)][field].length = 2;
        });
        bad(eventPoll(), [=](auto &m) {
            m.classFields[std::string(service::eventSampleName)][field].array = true;
        });
    }
    bad(eventPoll(), [](auto &m) {
        m.classFields[std::string(service::eventSampleName)].pop_back();
    });
    for (const auto &[name, cardinality] :
         std::vector<std::pair<std::string_view, int>>{{service::eventPollResultName, 4},
                                                       {service::eventAckResultName, 3},
                                                       {service::eventIntakeCompletionName, 7}}) {
        for (int count : {0, cardinality - 1, cardinality + 1})
            bad(eventPoll(), [=](auto &m) {
                m.enumCases[std::string(name)] = count;
            });
        bad(eventPoll(), [=](auto &m) {
            m.functions[0].code.insert(m.functions[0].code.end() - 1,
                                       EnumConstant{Type::enumeration(std::string(name)), cardinality});
        });
    }
    for (const auto name :
         {"__au_runtime_iommu_event_poll", "__au_runtime_iommu_event_acknowledge", "__au_runtime_event_other"}) {
        bad(eventPoll(), [=](auto &m) {
            m.functions[0].name = name;
        });
        bad(eventPoll(), [=](auto &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 1, Call{name});
        });
    }
    need(argc == 1 || argc == 2, "expected optional executed-IR assembly destination");
    if (argc == 2) {
        std::ofstream output(argv[1]);
        need(static_cast<bool>(output), "cannot open executed event IR destination");
        output << X86Emitter{}.emit(validate(executedEvent()));
        output.flush();
        need(static_cast<bool>(output), "cannot write executed event IR destination");
    }
    std::cout << "PASS IOMMU event and Console/Display hostile IR: " << checks << " checks\n";
    return 0;
}
