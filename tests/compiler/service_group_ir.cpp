// Independently authored distinct-service IR, retaining both single-kind suites.
#define DISPLAY_SERVICE_IR_MAIN display_service_regression
#include "display_service_ir.cpp"
#undef DISPLAY_SERVICE_IR_MAIN
#include <fstream>

namespace {
Module callResult() {
    Module m;
    const auto result = service::callResultType();
    const auto status = service::callStatusType();
    m.classLayouts[result.className] = {status, Type::U64};
    m.classFields[result.className] = {{status, 0, 1, false}, {Type::U64, 1, 1, false}};
    m.enumCases[status.className] = 3;
    auto f = entry("call_result");
    f.parameters = {Type::CallSession};
    f.result = result;
    f.objectSlots[40] = {result.className, false};
    f.slots = {{40, status}, {32, Type::U64}};
    f.code = {BindServiceParameter{0, 16, service::Kind::Call},
              BeginObject{40},
              Constant{42, Type::U64},
              ServiceOperation{16, service::Operation::Call, 40, service::Kind::Call},
              ReturnObject{40}};
    m.functions.push_back(f);
    return m;
}
void callChecks() {
    good(callResult());
    for (auto kind : {service::Kind::Console,
                      service::Kind::Display,
                      service::Kind::IommuEvent,
                      static_cast<service::Kind>(4),
                      static_cast<service::Kind>(-1)})
        bad(callResult(), [=](auto &m) {
            std::get<ServiceOperation>(m.functions[0].code[3]).kind = kind;
        });
    for (int operation : {-1, 0, 1, 2, 3, 4, 6, 999})
        bad(callResult(), [=](auto &m) {
            std::get<ServiceOperation>(m.functions[0].code[3]).operation = static_cast<service::Operation>(operation);
        });
    for (auto type : {Type::I64, Type::U8, Type::Bool})
        bad(callResult(), [=](auto &m) {
            m.functions[0].code[2] = Constant{1, type};
        });
    for (int offset : {0, 8, 16, 32, 48})
        bad(callResult(), [=](auto &m) {
            std::get<ServiceOperation>(m.functions[0].code[3]).resultOffset = offset;
        });
    for (auto type :
         {Type::ConsoleSession, Type::DisplaySession, Type::IommuEventSession, Type::ownedValues(Type::U64)})
        bad(callResult(), [=](auto &m) {
            m.functions[0].parameters[0] = type;
        });
    for (auto type : {Type::ConsoleSession, Type::DisplaySession, Type::IommuEventSession, Type::CallSession})
        bad(callResult(), [=](auto &m) {
            m.functions[0].parameters.push_back(type);
        });
    for (int count : {0, 1, 2, 4})
        bad(callResult(), [=](auto &m) {
            m.enumCases[service::callStatusType().className] = count;
        });
    bad(callResult(), [](auto &m) {
        m.classLayouts[service::callResultType().className][0] = Type::U64;
    });
    bad(callResult(), [](auto &m) {
        m.classFields[service::callResultType().className][1].array = true;
    });
    bad(callResult(), [](auto &m) {
        m.classLayouts["Fake"] = m.classLayouts.at(service::callResultType().className);
        m.classFields["Fake"] = m.classFields.at(service::callResultType().className);
        m.functions[0].objectSlots[40].className = "Fake";
    });
    bad(callResult(), [](auto &m) {
        m.functions[0].code.erase(m.functions[0].code.begin() + 1);
    });
    bad(callResult(), [](auto &m) {
        m.functions[0].code.insert(m.functions[0].code.begin() + 2, {Constant{0, Type::U64}, Store{32, Type::U64}});
    });
    bad(callResult(), [](auto &m) {
        m.functions[0].code.insert(m.functions[0].code.begin() + 2, AcquireServiceLoan{1, 16, service::Kind::Call});
    });
    auto forwarded = callResult();
    auto caller = forwarded.functions[0];
    caller.name = "call_forward";
    caller.code = {BindServiceParameter{0, 16, service::Kind::Call},
                   BeginObject{40},
                   AcquireServiceLoan{1, 16, service::Kind::Call},
                   ServiceCall{"call_result", 1, 40, {0}, service::Kind::Call},
                   ReleaseServiceLoan{1, service::Kind::Call},
                   ReturnObject{40}};
    forwarded.functions.push_back(caller);
    good(forwarded);
    bad(forwarded, [](auto &m) {
        m.functions.back().code.erase(m.functions.back().code.begin() + 4);
    });
}
F groupEntry(const std::string &name, bool displayFirst = false) {
    auto f = entry(name);
    f.parameters = displayFirst ? std::vector<Type>{Type::DisplaySession, Type::ConsoleSession}
                                : std::vector<Type>{Type::ConsoleSession, Type::DisplaySession};
    f.serviceSlots = {16, 32};
    f.code = {BindServiceParameter{0, 16, service::kind(f.parameters[0])},
              BindServiceParameter{1, 32, service::kind(f.parameters[1])}};
    return f;
}
void appendPixel(F &f, int offset) {
    const auto pixel = displayPixel().functions[0];
    for (auto it = pixel.code.begin() + 1; it != pixel.code.end() - 1; ++it) {
        auto operation = *it;
        if (auto *call = std::get_if<ServiceOperation>(&operation))
            call->offset = offset;
        f.code.push_back(std::move(operation));
    }
}
Module groupDirect(bool displayFirst = false) {
    auto m = displayPixel();
    auto f = groupEntry("group_leaf", displayFirst);
    f.code.insert(f.code.end(),
                  {Constant{65, Type::U8},
                   ServiceOperation{displayFirst ? 32 : 16, service::Operation::Put, 0, service::Kind::Console}});
    appendPixel(f, displayFirst ? 16 : 32);
    f.code.insert(f.code.end(), {Constant{0, Type::I64}, Return{}});
    m.functions = {f};
    return m;
}
Module groupForwarded(bool reverseTarget = false) {
    auto m = groupDirect(reverseTarget);
    auto caller = groupEntry("group_caller");
    const ServiceCall call =
        reverseTarget ? ServiceCall{"group_leaf", 2, 0, {0, 0}, service::Kind::Display, {{1, service::Kind::Console}}}
                      : ServiceCall{"group_leaf", 1, 0, {0, 0}, service::Kind::Console, {{2, service::Kind::Display}}};
    caller.code.insert(caller.code.end(),
                       {AcquireServiceLoan{1, 16, service::Kind::Console},
                        AcquireServiceLoan{2, 32, service::Kind::Display},
                        call,
                        ReleaseServiceLoan{2, service::Kind::Display},
                        ReleaseServiceLoan{1, service::Kind::Console},
                        Return{}});
    m.functions.push_back(caller);
    return m;
}
Module oppositeAcquisitionOrders(bool calledMismatch = false) {
    auto m = groupForwarded();
    const auto ordered = m.functions.back().code;
    auto &code = m.functions.back().code;
    code = {ordered[0], ordered[1], Constant{1, Type::Bool}, BranchFalse{20}, ordered[2], ordered[3]};
    if (calledMismatch)
        code.push_back(ordered[4]);
    code.insert(code.end(),
                {Jump{30}, Label{20}, ordered[3], ordered[2], Label{30}, ordered[4], ordered[5], ordered[6], Return{}});
    return m;
}
ServiceCall &groupCall(Module &m) {
    return std::get<ServiceCall>(m.functions.back().code[4]);
}
Module groupSubsets(bool directDisplay = false) {
    auto m = displayPixel();
    m.functions.push_back(forwarded().functions[1]);
    auto caller = groupEntry("subset_caller");
    caller.code.push_back(AcquireServiceLoan{1, 16, service::Kind::Console});
    if (directDisplay)
        appendPixel(caller, 32);
    else
        caller.code.insert(caller.code.end(),
                           {AcquireServiceLoan{2, 32, service::Kind::Display},
                            ServiceCall{"pixel_entry", 2, 0, {0}, service::Kind::Display},
                            ReleaseServiceLoan{2, service::Kind::Display}});
    caller.code.insert(caller.code.end(),
                       {Constant{65, Type::U8},
                        Push{},
                        ServiceCall{"putter", 1, 0, {0, 0}, service::Kind::Console},
                        ReleaseServiceLoan{1, service::Kind::Console},
                        Constant{0, Type::I64},
                        Return{}});
    m.functions.push_back(caller);
    return m;
}
Module groupConsoleSubsets(bool directConsole = false) {
    auto m = displayPixel();
    m.functions.push_back(forwarded().functions[1]);
    auto caller = groupEntry("console_subset_caller");
    caller.code.push_back(AcquireServiceLoan{2, 32, service::Kind::Display});
    if (directConsole)
        caller.code.insert(
            caller.code.end(),
            {Constant{65, Type::U8}, ServiceOperation{16, service::Operation::Put, 0, service::Kind::Console}});
    else
        caller.code.insert(caller.code.end(),
                           {AcquireServiceLoan{1, 16, service::Kind::Console},
                            Constant{65, Type::U8},
                            Push{},
                            ServiceCall{"putter", 1, 0, {0, 0}, service::Kind::Console},
                            ReleaseServiceLoan{1, service::Kind::Console}});
    caller.code.insert(caller.code.end(),
                       {ServiceCall{"pixel_entry", 2, 0, {0}, service::Kind::Display},
                        ReleaseServiceLoan{2, service::Kind::Display},
                        Constant{0, Type::I64},
                        Return{}});
    m.functions.push_back(caller);
    return m;
}
Module groupSample(bool displayFirst) {
    auto m = displayPixel();
    auto f = groupEntry("group_sample", displayFirst);
    f.result = service::sampleType();
    f.frameBytes = 64;
    f.objectSlots[64] = {std::string(service::sampleName), false};
    f.slots = {{64, Type::Bool}, {56, Type::U8}, {48, Type::Bool}};
    f.code.insert(f.code.end(),
                  {BeginObject{64},
                   ServiceOperation{displayFirst ? 32 : 16, service::Operation::Next, 64, service::Kind::Console},
                   ReturnObject{64}});
    m.functions = {f};
    return m;
}
Module groupSampleForwarded(bool displayFirst) {
    auto m = groupSample(displayFirst);
    auto caller = groupEntry("group_sample_caller");
    caller.frameBytes = 64;
    caller.objectSlots[64] = {std::string(service::sampleName), false};
    caller.slots = {{64, Type::Bool}, {56, Type::U8}, {48, Type::Bool}};
    const ServiceCall call =
        displayFirst
            ? ServiceCall{"group_sample", 2, 64, {0, 0}, service::Kind::Display, {{1, service::Kind::Console}}}
            : ServiceCall{"group_sample", 1, 64, {0, 0}, service::Kind::Console, {{2, service::Kind::Display}}};
    caller.code.insert(caller.code.end(),
                       {BeginObject{64},
                        AcquireServiceLoan{1, 16, service::Kind::Console},
                        AcquireServiceLoan{2, 32, service::Kind::Display},
                        call,
                        ReleaseServiceLoan{2, service::Kind::Display},
                        ReleaseServiceLoan{1, service::Kind::Console},
                        Load{56, Type::U8},
                        EndObject{64},
                        Constant{0, Type::I64},
                        Return{}});
    m.functions.push_back(caller);
    return m;
}
ServiceCall &groupSampleCall(Module &m) {
    return std::get<ServiceCall>(m.functions.back().code[5]);
}
Module executedNonlexical() {
    auto m = groupForwarded(true); // Target formals reverse the caller's roots.
    const auto ordered = m.functions.back().code;
    m.functions.back().code = {ordered[0],
                               ordered[1],
                               Jump{10},
                               // The call is textually before either acquisition, but reached afterward.
                               Label{20},
                               ordered[4],
                               ordered[5],
                               ordered[6],
                               Jump{30},
                               Label{10},
                               ordered[2],
                               ordered[3],
                               Jump{20},
                               // Reuse both released IDs at new sites with unchanged roots and kinds.
                               Label{30},
                               ordered[2],
                               ordered[3],
                               ordered[4],
                               ordered[5],
                               ordered[6],
                               Return{}};
    return m;
}
} // namespace

int main(int argc, char **argv) {
    display_service_regression();
    callChecks();
    good(groupDirect());
    good(groupDirect(true));
    good(groupForwarded());
    good(groupForwarded(true));
    good(oppositeAcquisitionOrders()); // Exact loan equality is independent of insertion order.
    bad(
        oppositeAcquisitionOrders(true),
        [](auto &) {
        },
        "incompatible service provenance or loans at control-flow join");
    good(groupSubsets());            // The unrelated Display loan can complete while Console is suspended.
    good(groupSubsets(true));        // Direct Display operations also remain available.
    good(groupConsoleSubsets());     // The Console child loan can complete while Display is suspended.
    good(groupConsoleSubsets(true)); // Direct Console operations also remain available.
    good(groupSample(false));
    good(groupSample(true));    // Copied Console reports do not depend on formal order.
    good(executedNonlexical()); // Always cover the same reordered, ID-reusing native oracle body.
    // The reordered, ID-reusing oracle retains four block entries. Only the
    // call block holds two dynamic loans; immutable service bindings add no facts.
    verification::Metrics serviceMetrics;
    static_cast<void>(validate(executedNonlexical(), &serviceMetrics));
    need(serviceMetrics.snapshots == 4 && serviceMetrics.peakRetainedValueFacts == 2,
         "service snapshots must retain only dynamic loans");
    ++checks;

    // Grouped copied-result calls require exact pristine storage in either formal order.
    for (bool displayFirst : {false, true}) {
        good(groupSampleForwarded(displayFirst));
        for (int offset : {0, 56})
            bad(groupSampleForwarded(displayFirst), [=](auto &m) {
                groupSampleCall(m).resultOffset = offset;
            });
        bad(groupSampleForwarded(displayFirst), [](auto &m) {
            m.functions.back().code.erase(m.functions.back().code.begin() + 2);
        });
        for (int offset : {64, 56, 48})
            bad(groupSampleForwarded(displayFirst), [=](auto &m) {
                auto &caller = m.functions.back();
                const auto type = caller.slots.at(offset);
                caller.code.insert(caller.code.begin() + 3, {Constant{0, type}, Store{offset, type}});
            });
        bad(groupSampleForwarded(displayFirst), [](auto &m) {
            m.functions.back().code.insert(m.functions.back().code.begin() + 3,
                                           ServiceOperation{16, service::Operation::Next, 64, service::Kind::Console});
        });
        bad(groupSampleForwarded(displayFirst), [](auto &m) {
            const auto sampleName = std::string(service::sampleName);
            m.classLayouts["OtherSample"] = m.classLayouts.at(sampleName);
            m.classFields["OtherSample"] = m.classFields.at(sampleName);
            m.functions.back().objectSlots.at(64).className = "OtherSample";
        });
    }

    auto reused = groupForwarded();
    auto &reusedCode = reused.functions.back().code;
    const std::vector<Instruction> round(reusedCode.begin() + 2, reusedCode.end() - 1);
    reusedCode.insert(reusedCode.end() - 1, round.begin(), round.end());
    good(reused); // Both lexical loan identities become reusable only after release.

    auto nonlexical = groupForwarded();
    const auto ordered = nonlexical.functions.back().code;
    nonlexical.functions.back().code = {ordered[0],
                                        ordered[1],
                                        Jump{10},
                                        Label{20},
                                        ordered[4],
                                        ordered[5],
                                        ordered[6],
                                        Return{},
                                        Label{10},
                                        ordered[2],
                                        ordered[3],
                                        Jump{20}};
    good(nonlexical); // Control flow acquires before calling; textual order does not.

    auto loop = groupForwarded();
    auto &loopCode = loop.functions.back().code;
    loopCode.insert(loopCode.begin() + 2, Label{1});
    loopCode.insert(loopCode.end() - 1,
                    {Constant{0, Type::Bool}, BranchFalse{2}, Jump{1}, Label{2}, Constant{0, Type::I64}});
    good(loop);

    // Exact, distinct, contiguous parameter provenance and disjoint opaque spills.
    bad(groupDirect(), [](auto &m) {
        m.functions[0].parameters[1] = Type::ConsoleSession;
    });
    bad(groupDirect(), [](auto &m) {
        std::get<BindServiceParameter>(m.functions[0].code[1]).index = 0;
    });
    bad(groupDirect(), [](auto &m) {
        std::get<BindServiceParameter>(m.functions[0].code[1]).kind = service::Kind::Console;
    });
    bad(groupDirect(), [](auto &m) {
        std::get<BindServiceParameter>(m.functions[0].code[1]).kind = static_cast<service::Kind>(999);
    });
    bad(groupDirect(), [](auto &m) {
        std::get<BindServiceParameter>(m.functions[0].code[1]).offset = 16;
    });
    bad(groupDirect(), [](auto &m) {
        m.functions[0].code.erase(m.functions[0].code.begin() + 1);
    });
    bad(groupDirect(), [](auto &m) {
        m.functions[0].code.insert(m.functions[0].code.begin() + 1, Constant{0, Type::I64});
    });
    for (const bool displayFirst : {false, true})
        bad(
            groupDirect(displayFirst),
            [=](auto &m) {
                m.functions[0].code.insert(m.functions[0].code.end() - 1,
                                           BindServiceParameter{0, 16, service::kind(m.functions[0].parameters[0])});
            },
            "parameter binding outside entry prefix");
    bad(groupDirect(), [](auto &m) {
        m.functions[0].parameters.insert(m.functions[0].parameters.begin() + 1, Type::I64);
    });
    bad(groupDirect(), [](auto &m) {
        m.functions[0].parameters.push_back(Type::ConsoleSession);
    });
    bad(groupDirect(), [](auto &m) {
        m.functions[0].serviceSlots.erase(32);
    });
    for (int offset : {24, 32})
        bad(groupDirect(), [=](auto &m) {
            m.functions[0].slots[offset] = Type::U64;
        });
    bad(groupDirect(), [](auto &m) {
        m.functions[0].serviceSlots.insert(24);
    });
    bad(groupDirect(), [](auto &m) {
        m.functions[0].code.insert(m.functions[0].code.end() - 1, Load{32, Type::U64});
    });
    bad(groupDirect(), [](auto &m) {
        std::get<ServiceOperation>(m.functions[0].code[3]).offset = 32;
    });

    // Every call position needs its own unused loan of the exact target kind.
    bad(
        groupForwarded(),
        [](auto &m) {
            groupCall(m).additionalServices.clear();
        },
        "service helper argument vector mismatch");
    bad(
        groupForwarded(),
        [](auto &m) {
            groupCall(m).additionalServices.push_back({2, service::Kind::Display});
        },
        "service helper argument vector mismatch");
    for (int loan : {0, 1, 3})
        bad(groupForwarded(), [=](auto &m) {
            groupCall(m).additionalServices[0].loanId = loan;
        });
    bad(groupForwarded(), [](auto &m) {
        groupCall(m).additionalServices[0].kind = service::Kind::Console;
    });
    bad(groupForwarded(), [](auto &m) {
        groupCall(m).additionalServices[0].kind = static_cast<service::Kind>(999);
    });
    bad(groupForwarded(), [](auto &m) {
        groupCall(m).loanId = 2;
    });
    bad(groupForwarded(), [](auto &m) {
        groupCall(m).kind = service::Kind::Display;
    });
    bad(groupForwarded(), [](auto &m) {
        groupCall(m).spanArguments = {0, 32};
    });
    bad(groupForwarded(), [](auto &m) {
        groupCall(m).spanArguments = {0};
    });
    bad(groupForwarded(), [](auto &m) {
        m.functions.back().code.erase(m.functions.back().code.begin() + 3);
    });
    bad(
        groupForwarded(),
        [](auto &m) {
            std::get<AcquireServiceLoan>(m.functions.back().code[3]).loanId = 1;
        },
        "service loan identity cannot change static root or kind"); // Both sites have exact entry roots/kinds.
    bad(
        groupForwarded(),
        [](auto &m) {
            std::get<AcquireServiceLoan>(m.functions.back().code[3]).offset = 16;
        },
        "service loan requires unsuspended parameter authority");
    bad(
        groupForwarded(),
        [](auto &m) {
            std::get<AcquireServiceLoan>(m.functions.back().code[3]).kind = service::Kind::Console;
        },
        "service loan requires unsuspended parameter authority");
    bad(
        groupForwarded(),
        [](auto &m) {
            m.functions.back().code.insert(m.functions.back().code.begin() + 4,
                                           AcquireServiceLoan{3, 32, service::Kind::Display});
        },
        "service loan requires unsuspended parameter authority");
    bad(groupForwarded(), [](auto &m) {
        m.functions.back().code[4] = Call{"group_leaf"};
    });
    bad(groupForwarded(), [](auto &m) {
        m.functions.back().code[4] = AggregateCall{"group_leaf", {0, 0}, 0};
    });
    bad(groupForwarded(), [](auto &m) {
        groupCall(m).callee = "group_caller";
    });
    bad(
        groupForwarded(),
        [](auto &m) {
            auto &code = m.functions.back().code;
            code.insert(code.end() - 1,
                        {AcquireServiceLoan{1, 32, service::Kind::Display},
                         ServiceCall{"pixel_entry", 1, 0, {0}, service::Kind::Display},
                         ReleaseServiceLoan{1, service::Kind::Display},
                         Constant{0, Type::I64}});
            m.functions.push_back(displayPixel().functions[0]);
        },
        "service loan identity cannot change static root or kind"); // Both acquisitions exactly match their own entry.

    // Only the borrowed roots are suspended; neither may be reused while suspended.
    bad(groupSubsets(true), [](auto &m) {
        m.functions.back().code.insert(
            m.functions.back().code.begin() + 3,
            {Constant{65, Type::U8}, ServiceOperation{16, service::Operation::Put, 0, service::Kind::Console}});
    });
    bad(groupConsoleSubsets(true), [](auto &m) {
        F suspendedDisplay;
        appendPixel(suspendedDisplay, 32);
        m.functions.back().code.insert(
            m.functions.back().code.begin() + 3, suspendedDisplay.code.begin(), suspendedDisplay.code.end());
    });
    bad(groupForwarded(), [](auto &m) {
        m.functions.back().code.insert(m.functions.back().code.begin() + 4,
                                       ReleaseServiceLoan{2, service::Kind::Display});
    });
    bad(groupForwarded(), [](auto &m) {
        const auto call = groupCall(m);
        m.functions.back().code.insert(m.functions.back().code.begin() + 5, call);
    });
    bad(groupForwarded(), [](auto &m) {
        std::get<ReleaseServiceLoan>(m.functions.back().code[5]).kind = service::Kind::Console;
    });
    bad(groupForwarded(), [](auto &m) {
        m.functions.back().code.erase(m.functions.back().code.begin() + 5);
    });
    bad(groupForwarded(), [](auto &m) {
        m.functions.back().code.insert(m.functions.back().code.end() - 1,
                                       ReleaseServiceLoan{2, service::Kind::Display});
    });
    bad(groupForwarded(), [](auto &m) {
        m.functions.back().code.insert(m.functions.back().code.begin() + 4, {Constant{0, Type::Bool}, BranchFalse{99}});
        m.functions.back().code.insert(m.functions.back().code.begin() + 7, Label{99});
    });
    bad(loop, [](auto &m) {
        m.functions.back().code.erase(m.functions.back().code.begin() + 6);
    });
    need(argc == 1 || argc == 2, "expected optional executed-IR assembly destination");
    if (argc == 2) {
        const auto assembly = X86Emitter{}.emit(validate(executedNonlexical()));
        std::ofstream output(argv[1]);
        need(static_cast<bool>(output), "cannot open executed-IR assembly destination");
        output << assembly;
        output.flush();
        need(static_cast<bool>(output), "cannot write executed-IR assembly destination");
    }
    std::cout << "PASS distinct service groups and single-kind regression: " << checks << " checks\n";
}
