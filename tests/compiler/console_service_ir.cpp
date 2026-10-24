// Independently authored IR: no parser, semantic lowering or source fixtures.
#include "service_ir_common.hpp"
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
