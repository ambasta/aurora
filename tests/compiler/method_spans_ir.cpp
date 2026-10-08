// Independently authored malformed method capability IR; no parser involvement.
#include "ir_verify.hpp"
#include <functional>
#include <iostream>
using namespace aurora;
using namespace aurora::ir;
using F = aurora::ir::Function;
namespace {
int accepted = 0, rejected = 0;
template <class T> T &op(F &f) {
    for (auto &i : f.code)
        if (auto *p = std::get_if<T>(&i))
            return *p;
    throw Error("fixture operation missing");
}
template <class T> void before(F &f, std::initializer_list<Instruction> code) {
    for (auto i = f.code.begin(); i != f.code.end(); ++i)
        if (std::holds_alternative<T>(*i)) {
            f.code.insert(i, code);
            return;
        }
    throw Error("fixture insertion missing");
}
Module fixture() {
    Module m;
    m.classLayouts = {{"Receiver", {Type::I64}}, {"Box", {Type::I64}}};
    m.classFields["Receiver"] = {{Type::I64, 0, 1, false}, {Type::OwnedBytes, 1, 0, false}};
    m.classFields["Box"] = {{Type::I64, 0, 1, false}};
    m.classStorage = {{"Receiver", {{0}, {0, 8}, 40, 8, 40}}, {"Box", {{0}, {0}, 8, 8, 8}}};
    F target;
    target.name = "target";
    target.receiver = Receiver{"Receiver", false, false};
    target.result = Type::I64;
    target.parameters = {Type::I64, Type::ByteSpan, Type("Box")};
    target.frameBytes = 80;
    target.slots = {{8, Type::I64}, {72, Type::I64}};
    target.spanSlots = {64};
    target.objectSlots = {{72, {"Box", false}}};
    target.code = {BindParameter{0, 8, Type::I64},
                   BindSpanParameter{1, 64},
                   BindObjectParameter{2, 72, "Box"},
                   SpanLength{64},
                   EndSpan{64},
                   EndObject{72},
                   Return{}};
    F caller;
    caller.name = "caller";
    caller.receiver = Receiver{"Receiver", true, false};
    caller.result = Type::I64;
    caller.parameters = {Type::ByteSpan};
    caller.frameBytes = 192;
    caller.spanSlots = {56, 112, 168};
    caller.slots = {{176, Type::I64}};
    caller.objectSlots = {{176, {"Box", false}}};
    caller.code = {BindSpanParameter{0, 56},
                   ReborrowSpan{56, 112},
                   Constant{0, Type::I64},
                   Push{},
                   Constant{0, Type::I64},
                   Subspan{112, 168},
                   BeginObject{176},
                   Constant{71, Type::I64},
                   Store{176, Type::I64},
                   Constant{33, Type::I64},
                   Push{},
                   MethodCall{"target", 0, {0, 0, 176}, 0, -1, {0, 168, 0}},
                   EndObject{176},
                   EndSpan{168},
                   EndSpan{112},
                   EndSpan{56},
                   Return{}};
    m.functions = {caller, target};
    return m;
}
void accept(const std::string &name, Module m) {
    (void)validate(std::move(m));
    ++accepted;
    std::cout << "PASS method span IR " << name << '\n';
}
void reject(const std::string &name,
            Module m,
            const std::function<void(Module &)> &change,
            const std::string &diagnostic) {
    change(m);
    try {
        (void)validate(std::move(m));
    } catch (const Error &error) {
        if (std::string(error.what()).find(diagnostic) == std::string::npos)
            throw Error(name + ": unexpected diagnostic: " + error.what());
        ++rejected;
        std::cout << "PASS method span IR " << name << '\n';
        return;
    }
    throw Error(name + ": malformed IR accepted");
}
} // namespace
int main() {
    try {
        accept("bound receiver forwards empty descendant with scalar/class neighbors", fixture());
        auto mutate = [](Module &m) {
            m.functions[1].receiver->mutableValue = true;
        };
        auto independent = fixture();
        mutate(independent);
        accept("mutable receiver accepts unrelated incoming capability", independent);
        for (const auto &v : std::vector<std::vector<int>>{{}, {168}, {0, 168}, {0, 168, 0, 0}})
            reject(
                "span vector size",
                fixture(),
                [&](Module &m) {
                    op<MethodCall>(m.functions[0]).spanArguments = v;
                },
                "span argument vector size mismatch");
        for (const auto &v : std::vector<std::vector<int>>{{}, {0}, {0, 0}, {0, 0, 176, 0}})
            reject(
                "object vector size",
                fixture(),
                [&](Module &m) {
                    op<MethodCall>(m.functions[0]).objectArguments = v;
                },
                "object argument vector size mismatch");
        for (int slot : {0, -1, 160, 184})
            reject(
                "capability requires exact live spill",
                fixture(),
                [=](Module &m) {
                    op<MethodCall>(m.functions[0]).spanArguments[1] = slot;
                },
                "exact typed spill");
        for (int position : {0, 2})
            reject(
                "nonspan position rejects capability",
                fixture(),
                [=](Module &m) {
                    op<MethodCall>(m.functions[0]).spanArguments[position] = 168;
                },
                "non-span method argument cannot name span storage");
        reject(
            "span position rejects object",
            fixture(),
            [](Module &m) {
                op<MethodCall>(m.functions[0]).objectArguments[1] = 176;
            },
            "span method argument cannot name object storage");
        reject(
            "ended argument rejects",
            fixture(),
            [](Module &m) {
                before<MethodCall>(m.functions[0], {EndSpan{168}});
            },
            "span capability is not active");
        reject(
            "parent ends while empty child live",
            fixture(),
            [](Module &m) {
                before<MethodCall>(m.functions[0], {EndSpan{112}});
            },
            "live child reborrow");
        reject(
            "branch capability lifetime mismatch",
            fixture(),
            [](Module &m) {
                before<MethodCall>(m.functions[0], {Constant{1, Type::Bool}, BranchFalse{1}, EndSpan{168}, Label{1}});
            },
            "incompatible active span capabilities");
        reject(
            "scalar result cannot alias argument spill",
            fixture(),
            [](Module &m) {
                op<MethodCall>(m.functions[0]).resultOffset = 168;
            },
            "scalar method result cannot name object storage");
        reject(
            "constructor parameter forbidden",
            fixture(),
            [](Module &m) {
                m.functions[1].receiver = Receiver{"Box", true, true};
                m.functions = {m.functions[1]};
            },
            "readonly span boundary");
        // Replace incoming authority with receiver-owned authority. Empty descendants
        // must freeze the exact root just as nonempty direct views do.
        for (bool empty : {false, true}) {
            auto self = fixture();
            auto &f = self.functions[0];
            f.parameters.clear();
            f.code[0] = BorrowOwnedSpan{0, 1, 56};
            if (!empty)
                op<MethodCall>(f).spanArguments[1] = 56;
            accept(empty ? "const self call empty alias" : "const self call direct alias", self);
            reject(empty ? "mutable self call empty alias" : "mutable self call direct alias",
                   self,
                   mutate,
                   "live readonly span");
            reject(
                "self field resize with active argument",
                self,
                [](Module &m) {
                    before<MethodCall>(m.functions[0], {Constant{0, Type::I64}, BytesResize{0, 1}});
                },
                "live readonly span");
        }
        auto result = fixture();
        auto &f = result.functions[1];
        f.result = Type::ByteSpan;
        f.receiverSpanField = 1;
        f.frameBytes = 144;
        f.spanSlots.insert(136);
        f.code = {BindParameter{0, 8, Type::I64},
                  BindSpanParameter{1, 64},
                  BindObjectParameter{2, 72, "Box"},
                  EndObject{72},
                  EndSpan{64},
                  BorrowOwnedSpan{0, 1, 136},
                  ReturnSpan{136}};
        auto &c = result.functions[0];
        c.frameBytes = 240;
        c.spanSlots.insert(232);
        op<MethodCall>(c).resultOffset = 232;
        before<EndObject>(c, {SpanLength{232}, EndSpan{232}});
        accept("result authority derives from receiver not argument", result);
        reject(
            "result cannot overwrite active argument",
            result,
            [](Module &m) {
                op<MethodCall>(m.functions[0]).resultOffset = 168;
            },
            "span spill is already active");
        reject(
            "parameter cannot escape as receiver result",
            result,
            [](Module &m) {
                auto &f = m.functions[1];
                f.code = {BindParameter{0, 8, Type::I64},
                          BindSpanParameter{1, 64},
                          BindObjectParameter{2, 72, "Box"},
                          EndObject{72},
                          ReturnSpan{64}};
            },
            "span return does not match receiver field summary and token");
        reject(
            "unrelated argument must end before receiver result",
            result,
            [](Module &m) {
                auto &f = m.functions[1];
                f.code.erase(f.code.begin() + 4);
            },
            "unrelated active span lifetime");
        std::cout << "PASS method span IR: " << accepted << " accepted and " << rejected << " rejected\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
