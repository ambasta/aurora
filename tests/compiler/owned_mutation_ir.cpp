// Independent malformed-IR and literal-layout fixtures for direct owned fields.
#include "ir_verify.hpp"
#include "x86.hpp"
#include <functional>
#include <iostream>
#include <string>

using namespace aurora;
using namespace aurora::ir;
using IRFunction = aurora::ir::Function;

namespace {
int accepted = 0;
int rejected = 0;

void require(bool condition, const std::string &message) {
    if (!condition)
        throw Error(message);
}

void childSlot(IRFunction &function, int base, bool mutableValue = false) {
    function.objectSlots[base] = {"Child", mutableValue};
    function.slots[base] = Type::U8;
    function.slots[base - 8] = Type::U64;
}

void holderSlot(IRFunction &function, int base, bool mutableValue = false) {
    function.objectSlots[base] = {"Holder", mutableValue};
    function.slots[base] = Type::U8;
    function.slots[base - 8] = Type::U8;
    function.slots[base - 16] = Type::U64;
    function.slots[base - 24] = Type::U8;
}

Module baseline(bool implicit = false, int resultMode = 0) {
    Module module;
    module.classLayouts = {{"Child", {Type::U8, Type::U64}},
                           {"Other", {Type::U8, Type::U64}},
                           {"Holder", {Type::U8, Type::U8, Type::U64, Type::U8}}};
    module.classFields["Holder"] = {{Type::U8, 0, 1, false}, {Type("Child"), 1, 2, false}, {Type::U8, 3, 1, false}};
    // Literal storage supplied independently of the production layout helper.
    module.classStorage["Child"] = {{0, 8}, {0, 8}, 16, 8, 16};
    module.classStorage["Other"] = module.classStorage["Child"];
    module.classStorage["Holder"] = {{0, 8, 16, 24}, {0, 8, 24}, 32, 8, 32};
    IRFunction caller;
    caller.name = implicit ? "implicit_entry" : "local_entry";
    caller.result = resultMode == 0 ? Type::U64 : Type("Child");
    caller.parameters = {Type("Holder"), Type("Child")};
    caller.frameBytes = 128;
    holderSlot(caller, 32);
    childSlot(caller, 48);
    holderSlot(caller, 80, true);
    childSlot(caller, 96);
    holderSlot(caller, 128);
    caller.code = {
        BindObjectParameter{0, 32, "Holder"}, BindObjectParameter{1, 48, "Child"}, BeginObject{80}, CopyObject{32, 80}};
    const int root = implicit ? 0 : 80;
    if (implicit)
        caller.receiver = Receiver{"Holder", true, false};
    caller.code.push_back(AssignObjectField{root, 1, 48});
    if (resultMode == 2) {
        caller.code.push_back(BeginObject{128});
        caller.code.push_back(CopyObject{32, 128});
    }
    caller.code.push_back(Constant{42, Type::U64});
    caller.code.push_back(Push{});
    if (resultMode != 0)
        caller.code.push_back(BeginObject{96});
    caller.code.push_back(MethodCall{resultMode == 0   ? "set_word"
                                     : resultMode == 1 ? "copy_child"
                                                       : "combined",
                                     root,
                                     resultMode == 2 ? std::vector<int>{128, 0, 48} : std::vector<int>{},
                                     resultMode == 0 ? 0 : 96,
                                     1});
    if (resultMode == 0)
        caller.code.push_back(Return{});
    else
        caller.code.push_back(ReturnObject{96});

    IRFunction setter;
    setter.name = "set_word";
    setter.result = Type::U64;
    setter.receiver = Receiver{"Child", true, false};
    setter.parameters = {Type::U64};
    setter.frameBytes = 16;
    setter.slots = {{8, Type::U64}};
    setter.code = {BindParameter{0, 8, Type::U64},
                   Load{8, Type::U64},
                   ReceiverStore{1, Type::U64},
                   ReceiverLoad{1, Type::U64},
                   Return{}};

    IRFunction copied;
    copied.name = "copy_child";
    copied.result = Type("Child");
    copied.receiver = Receiver{"Child", false, false};
    copied.parameters = {Type::U64};
    copied.frameBytes = 32;
    copied.slots[8] = Type::U64;
    childSlot(copied, 32);
    copied.code = {BindParameter{0, 8, Type::U64},
                   BeginObject{32},
                   ReceiverLoad{0, Type::U8},
                   Store{32, Type::U8},
                   Load{8, Type::U64},
                   Store{24, Type::U64},
                   ReturnObject{32}};

    IRFunction combined;
    combined.name = "combined";
    combined.result = Type("Child");
    combined.receiver = Receiver{"Child", true, false};
    combined.parameters = {Type("Holder"), Type::U64, Type("Child")};
    combined.frameBytes = 64;
    holderSlot(combined, 32);
    combined.slots[40] = Type::U64;
    childSlot(combined, 64);
    combined.code = {BindObjectParameter{0, 32, "Holder"},
                     BindParameter{1, 40, Type::U64},
                     BindObjectParameter{2, 64, "Child"},
                     Load{40, Type::U64},
                     ReceiverStore{1, Type::U64},
                     ReturnObject{64}};
    module.functions = {caller, setter, copied, combined};
    return module;
}

MethodCall &call(Module &module) {
    for (auto &instruction : module.functions[0].code)
        if (auto *operation = std::get_if<MethodCall>(&instruction))
            return *operation;
    throw Error("missing fixture call");
}

void accept(const std::string &name, Module module) {
    require(!X86Emitter{}.emit(validate(std::move(module))).empty(), "empty assembly");
    ++accepted;
    std::cout << "PASS owned IR " << name << '\n';
}

void reject(const std::string &name,
            Module module,
            const std::function<void(Module &)> &change,
            const std::string &diagnostic) {
    change(module);
    try {
        (void)validate(std::move(module));
    } catch (const Error &error) {
        require(std::string(error.what()).find(diagnostic) != std::string::npos,
                name + ": wrong diagnostic: " + error.what());
        ++rejected;
        std::cout << "PASS owned IR " << name << '\n';
        return;
    }
    throw Error(name + ": malformed IR accepted");
}

Module emptyFields() {
    Module module;
    module.classLayouts = {{"Empty", {}}, {"Envelope", {Type::U64}}};
    module.classFields["Envelope"] = {{Type("Empty"), 0, 0, false}, {Type::U64, 0, 1, false}};
    IRFunction function;
    function.name = "empty_entry";
    function.result = Type::U64;
    function.parameters = {Type("Envelope")};
    function.frameBytes = 32;
    function.slots = {{16, Type::U64}, {32, Type::U64}};
    function.objectSlots = {{8, {"Empty", false}}, {16, {"Envelope", false}}, {32, {"Envelope", true}}};
    function.code = {BindObjectParameter{0, 16, "Envelope"},
                     BeginObject{8},
                     InitializeEmptyObject{8},
                     BeginObject{32},
                     CopyObject{16, 32},
                     AssignObjectField{32, 0, 8},
                     MethodCall{"empty_answer", 32, {}, 0, 0},
                     Return{}};
    IRFunction method;
    method.name = "empty_answer";
    method.result = Type::U64;
    method.receiver = Receiver{"Empty", true, false};
    method.code = {Constant{42, Type::U64}, Return{}};
    module.functions = {function, method};
    return module;
}

void directTests() {
    accept("complete empty child replacement and mutable receiver", emptyFields());
    reject(
        "empty logical completion cannot be minted by assignment",
        emptyFields(),
        [](Module &m) {
            auto &code = m.functions[0].code;
            code.erase(code.begin() + 4);
            code.insert(code.begin() + 4, {Constant{7, Type::U64}, Store{32, Type::U64}});
        },
        "nested class field not completely initialized");
    reject(
        "empty logical completion required before nested receiver",
        emptyFields(),
        [](Module &m) {
            auto &code = m.functions[0].code;
            code.erase(code.begin() + 4, code.begin() + 6);
            code.insert(code.begin() + 4, {Constant{7, Type::U64}, Store{32, Type::U64}});
        },
        "nested class field not completely initialized");
    for (bool implicit : {false, true}) {
        for (int mode : {0, 1, 2})
            accept("local/implicit root scalar/scalar-result/combined-result", baseline(implicit, mode));
        auto readonly = baseline(implicit, 1);
        readonly.functions[0].code.erase(readonly.functions[0].code.begin() + 4);
        if (implicit)
            readonly.functions[0].receiver->mutableValue = false;
        else
            readonly.functions[0].objectSlots[80].mutableValue = false;
        accept("readonly root supplies const nested receiver", std::move(readonly));
        auto check =
            [&](const std::string &name, const std::function<void(Module &)> &change, const std::string &diagnostic) {
                reject(name, baseline(implicit), change, diagnostic);
            };
        check(
            "readonly root assignment",
            [=](Module &m) {
                if (implicit)
                    m.functions[0].receiver->mutableValue = false;
                else
                    m.functions[0].objectSlots[80].mutableValue = false;
            },
            "const");
        check(
            "negative assignment root",
            [](Module &m) {
                std::get<AssignObjectField>(m.functions[0].code[4]).objectOffset = -1;
            },
            "root offset");
        check(
            "invalid logical field",
            [](Module &m) {
                std::get<AssignObjectField>(m.functions[0].code[4]).fieldIndex = 8;
            },
            implicit ? "layout mismatch" : "index out of range");
        check(
            "negative logical field",
            [](Module &m) {
                std::get<AssignObjectField>(m.functions[0].code[4]).fieldIndex = -1;
            },
            implicit ? "layout mismatch" : "index out of range");
        check(
            "scalar logical field",
            [](Module &m) {
                std::get<AssignObjectField>(m.functions[0].code[4]).fieldIndex = 0;
            },
            implicit ? "not initialized" : "requires class field");
        check(
            "inactive assignment source",
            [](Module &m) {
                m.functions[0].code.insert(m.functions[0].code.begin() + 4, EndObject{48});
            },
            "outside active lifetime");
        check(
            "active but incomplete assignment source",
            [](Module &m) {
                auto &code = m.functions[0].code;
                std::get<AssignObjectField>(code[4]).sourceOffset = 96;
                code.insert(code.begin() + 4, BeginObject{96});
            },
            "not fully initialized");
        check(
            "source interior offset",
            [](Module &m) {
                std::get<AssignObjectField>(m.functions[0].code[4]).sourceOffset = 40;
            },
            "exact object slot");
        check(
            "nominal mismatch despite equal layout",
            [](Module &m) {
                auto &f = m.functions[0];
                f.parameters[1] = Type("Other");
                f.objectSlots[48].className = "Other";
                std::get<BindObjectParameter>(f.code[1]).className = "Other";
            },
            "nominal class mismatch");
        check(
            "source equals root",
            [](Module &m) {
                auto &assign = std::get<AssignObjectField>(m.functions[0].code[4]);
                assign.sourceOffset = assign.objectOffset;
            },
            "aliases root");
        check(
            "invalid receiver field sentinel",
            [](Module &m) {
                call(m).receiverFieldIndex = -2;
            },
            "field index");
        check(
            "receiver uses byte offset as logical index",
            [](Module &m) {
                call(m).receiverFieldIndex = 8;
            },
            implicit ? "layout mismatch" : "index out of range");
        check(
            "receiver nominal mismatch",
            [](Module &m) {
                m.functions[1].receiver->className = "Other";
            },
            "nominal class mismatch");
        check(
            "nested constructor forbidden",
            [](Module &m) {
                m.functions[1].receiver->constructor = true;
            },
            "nested receiver cannot call constructor");
        check(
            "readonly mutable call",
            [=](Module &m) {
                m.functions[0].code.erase(m.functions[0].code.begin() + 4);
                if (implicit)
                    m.functions[0].receiver->mutableValue = false;
                else
                    m.functions[0].objectSlots[80].mutableValue = false;
            },
            "const");
        reject(
            "result aliases whole root",
            baseline(implicit, 1),
            [=](Module &m) {
                call(m).resultOffset = implicit ? 0 : 80;
            },
            "result aliases receiver");
        reject(
            "result aliases readonly argument",
            baseline(implicit, 2),
            [](Module &m) {
                call(m).resultOffset = 48;
            },
            "result aliases argument");
        reject(
            "argument aliases receiver root",
            baseline(implicit, 2),
            [=](Module &m) {
                call(m).objectArguments[0] = implicit ? 0 : 80;
            },
            "receiver aliases argument");
    }
    reject(
        "inactive root",
        baseline(),
        [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 4, EndObject{80});
        },
        "outside active lifetime");
    reject(
        "incomplete whole root",
        baseline(),
        [](Module &m) {
            m.functions[0].code.erase(m.functions[0].code.begin() + 3);
        },
        "not fully initialized");
    reject(
        "method-only inactive root",
        baseline(),
        [](Module &m) {
            auto &code = m.functions[0].code;
            code[4] = EndObject{80};
        },
        "outside active lifetime");
    reject(
        "method-only incomplete root",
        baseline(),
        [](Module &m) {
            auto &code = m.functions[0].code;
            code.erase(code.begin() + 3, code.begin() + 5);
        },
        "not fully initialized");
    reject(
        "constructor cannot replace nested initialized state",
        baseline(true),
        [](Module &m) {
            m.functions[0].receiver->constructor = true;
            m.functions[0].result = Type::I64;
        },
        "during initialization");
    reject(
        "nested scalar stores remain forbidden",
        baseline(),
        [](Module &m) {
            m.functions[0].code.insert(m.functions[0].code.begin() + 4, {Constant{7, Type::U64}, Store{64, Type::U64}});
        },
        "scalar store cannot write nested class field");
    reject(
        "overlapping subobject object slot forbidden",
        baseline(),
        [](Module &m) {
            childSlot(m.functions[0], 72, true);
        },
        "overlapping object layouts");
    reject(
        "forged canonical field offset",
        baseline(),
        [](Module &m) {
            m.classStorage["Holder"].fieldOffsets[1] = 16;
        },
        "storage");
}
} // namespace

int main(int argc, char **argv) {
    try {
        if (argc == 4 && std::string(argv[1]) == "--emit-abi") {
            const bool implicit = std::string(argv[2]) == "implicit";
            const int mode = std::stoi(argv[3]);
            require(mode >= 0 && mode <= 2, "invalid result mode");
            std::cout << X86Emitter{}.emit(validate(baseline(implicit, mode)));
            return 0;
        }
        require(argc == 1, "usage: owned-mutation-ir [--emit-abi local|implicit 0|1|2]");
        directTests();
        std::cout << "PASS owned IR: " << accepted << " accepted, " << rejected << " rejected\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL owned IR: " << error.what() << '\n';
        return 1;
    }
}
