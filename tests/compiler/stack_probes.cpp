// Source/IR-to-assembly tests. No generated machine code or fault is executed.
// --emit-guard-fixtures emits direct IR for the opt-in disposable-child ABI runner.
#include "ir_verify.hpp"
#include "x86.hpp"
#include <algorithm>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

using namespace aurora;
using namespace aurora::ir;
using IRFunction = aurora::ir::Function;
namespace {
int passed = 0;
void require(bool okay, const std::string &message) {
    if (!okay)
        throw Error(message);
}
std::vector<std::string> body(const std::string &assembly, const std::string &name) {
    const auto begin = assembly.find(name + ":\n");
    require(begin != std::string::npos, "missing fixture symbol " + name);
    const auto end = assembly.find(".size " + name + ",", begin);
    require(end != std::string::npos, "missing fixture size " + name);
    std::istringstream input(assembly.substr(begin + name.size() + 2,
                                            end - begin - name.size() - 2));
    std::vector<std::string> lines;
    for (std::string line; std::getline(input, line);)
        lines.push_back(line);
    return lines;
}
// Independently inspect the emitted instruction stream and accounted extent.
// The exact next instruction check catches missing sub-page/final probes and
// probes at an offset or below RSP; matching only a maximum step would not.
std::size_t reservation(const std::vector<std::string> &lines, std::size_t at, int expected) {
    const std::string prefix = "    subq $", suffix = ", %rsp";
    if (expected == 0) {
        require(at < lines.size() && lines[at] == "    subq $0, %rsp", "zero reservation");
        require(at + 1 == lines.size() || lines[at + 1] != "    orq $0, (%rsp)",
                "zero reservation must not touch storage");
        return at + 1;
    }
    int accounted = 0;
    while (accounted < expected) {
        require(at + 1 < lines.size() && lines[at].starts_with(prefix) &&
                    lines[at].ends_with(suffix), "missing reservation step");
        const auto amount = lines[at].substr(prefix.size(),
                                             lines[at].size() - prefix.size() - suffix.size());
        std::size_t consumed = 0;
        const int step = std::stoi(amount, &consumed);
        require(consumed == amount.size() && step > 0 && step <= 4096 && step % 16 == 0 &&
                    step <= expected - accounted, "invalid or oversized reservation step");
        require(step == 4096 || step == expected - accounted, "noncanonical page step");
        require(lines[at + 1] == "    orq $0, (%rsp)", "missing immediate endpoint probe");
        // The touched interval [new RSP, new RSP + 8) is inside this step.
        require(step >= 8, "probe exceeds fresh reservation");
        accounted += step;
        at += 2;
    }
    require(at == lines.size() || !lines[at].starts_with(prefix), "extra reservation step");
    return at;
}
IRFunction scalar(int bytes) {
    IRFunction f;
    f.name = "probe_scalar";
    f.result = Type::I64;
    f.frameBytes = bytes;
    f.code = {Constant{42, Type::I64}, Return{}};
    return f;
}
Module fixture(int bytes, const std::string &mode) {
    Module m;
    auto f = scalar(bytes);
    if (mode != "scalar") {
        m.classLayouts["Box"] = {Type::I64};
        if (mode == "receiver") {
            f.receiver = Receiver{"Box", false, false};
            f.code = {ReceiverLoad{0, Type::I64}, Return{}};
        } else {
            f.parameters = {Type("Box")};
            f.slots[8] = Type::I64;
            f.objectSlots[8] = {"Box", false};
            f.code = {BindObjectParameter{0, 8, "Box"}};
            if (mode == "constructor") {
                f.receiver = Receiver{"Box", true, true};
                f.code.insert(f.code.end(), {Load{8, Type::I64}, ReceiverStore{0, Type::I64},
                                             Constant{0, Type::I64}, Return{}});
            } else {
                f.result = Type("Box");
                if (mode == "combined")
                    f.receiver = Receiver{"Box", false, false};
                f.code.push_back(ReturnObject{8});
            }
        }
    }
    m.functions.push_back(std::move(f));
    return m;
}
void frameTests() {
    for (const std::string mode : {"scalar", "receiver", "aggregate", "constructor", "combined"}) {
        for (const int bytes : {0, 16, 4080, 4096, 4112, 8192, 8208, 65520, 65536}) {
            if (bytes == 0 && mode != "scalar" && mode != "receiver")
                continue;
            const auto assembly = X86Emitter{}.emit(validate(fixture(bytes, mode)));
            const auto lines = body(assembly, "probe_scalar");
            require(lines.size() > 3 && lines[0] == "    pushq %rbp" &&
                        lines[1] == "    movq %rsp, %rbp", "frame pointer ABI changed");
            const int hidden = mode == "scalar" ? 0 : mode == "combined" ? 32 : 16;
            auto at = reservation(lines, 2, bytes + hidden);
            const auto save = [&](const std::string &reg, int offset) {
                require(at < lines.size() && lines[at++] == "    movq " + reg + ", -" +
                            std::to_string(offset) + "(%rbp)", "hidden capability save changed");
            };
            if (mode == "receiver" || mode == "constructor" || mode == "combined")
                save("%r10", bytes + 8);
            if (mode == "aggregate" || mode == "constructor" || mode == "combined")
                save("%r11", bytes + (mode == "aggregate" ? 8 : 16));
            if (mode == "aggregate" || mode == "combined")
                save(mode == "aggregate" ? "%r10" : "%rax", bytes + (mode == "aggregate" ? 16 : 24));
            require(assembly.find(".Laurora_bounds_trap:\n    ud2\n") != std::string::npos &&
                        assembly.find(".Laurora_overflow_trap:\n    ud2\n") != std::string::npos &&
                        assembly.find(".Laurora_division_zero_trap:\n    ud2\n") != std::string::npos &&
                        assembly.find(".Laurora_shift_count_trap:\n    ud2\n") != std::string::npos,
                    "checked trap stubs changed");
            ++passed;
        }
    }
}
void callTests() {
    for (const bool odd : {false, true}) {
        auto m = fixture(16, "aggregate");
        m.functions[0].name = "probe_target";
        auto caller = scalar(32);
        caller.name = "probe_caller";
        caller.parameters = {Type("Box")};
        caller.slots = {{8, Type::I64}, {16, Type::I64}};
        caller.objectSlots = {{8, {"Box", false}}, {16, {"Box", false}}};
        caller.code = {BindObjectParameter{0, 8, "Box"}, BeginObject{16}};
        if (odd)
            caller.code.insert(caller.code.end(), {Constant{1, Type::I64}, Push{}});
        caller.code.insert(caller.code.end(), {AggregateCall{"probe_target", {8}, 16},
                                               Load{16, Type::I64}});
        if (odd)
            caller.code.push_back(BinaryValue{Binary::CheckedAdd});
        caller.code.push_back(Return{});
        m.functions.push_back(std::move(caller));
        const auto assembly = X86Emitter{}.emit(validate(std::move(m)));
        const auto lines = body(assembly, "probe_caller");
        reservation(lines, 2, 48);
        const auto record = std::find(lines.begin(), lines.end(), "    subq $16, %rsp");
        require(record != lines.end(), "missing outgoing record");
        reservation(lines, static_cast<std::size_t>(record - lines.begin()), 16);
        require(assembly.find("    movq %rsp, %r11\n    leaq -16(%rbp), %r10\n") != std::string::npos,
                "outgoing hidden ABI changed");
        const std::string call = odd ? "    subq $8, %rsp\n    call probe_target\n    addq $8, %rsp\n"
                                     : "    call probe_target\n";
        require(assembly.find(call + "    addq $16, %rsp\n") != std::string::npos,
                "call alignment or record cleanup changed");
        if (odd)
            require(assembly.find("    addq %rcx, %rax\n    jo .Laurora_overflow_trap\n") != std::string::npos,
                    "probe interrupted arithmetic flags");
        ++passed;
    }
}
// Sparse bottom slots deliberately avoid a large initializer corpus. The 8192-byte
// frame's bottom store would reach the writable landing page if its reservation
// skipped a guard. The runner adds symbol labels only; no probe is synthesized.
Module guardFixtures() {
    Module module;
    for (const int bytes : {4080, 4096, 4112, 8192, 65536}) {
        auto function = scalar(bytes);
        function.name = "guard_frame_" + std::to_string(bytes);
        function.slots[bytes] = Type::I64;
        function.code = {Constant{42, Type::I64}, Store{bytes, Type::I64},
                         Load{bytes, Type::I64}, Return{}};
        module.functions.push_back(std::move(function));
    }
    module.classLayouts["GuardBox"] = {Type::I64};
    auto target = scalar(16);
    target.name = "guard_target";
    target.parameters = {Type("GuardBox")};
    target.slots[8] = Type::I64;
    target.objectSlots[8] = {"GuardBox", false};
    target.code = {BindObjectParameter{0, 8, "GuardBox"}, Load{8, Type::I64}, Return{}};
    module.functions.push_back(std::move(target));
    for (const bool odd : {false, true}) {
        auto caller = scalar(32);
        caller.name = odd ? "guard_call_odd" : "guard_call_even";
        caller.slots[8] = Type::I64;
        caller.objectSlots[8] = {"GuardBox", false};
        caller.code = {BeginObject{8}, Constant{42, Type::I64}, Store{8, Type::I64}};
        if (odd)
            caller.code.insert(caller.code.end(), {Constant{1, Type::I64}, Push{}});
        caller.code.push_back(AggregateCall{"guard_target", {8}, 0});
        if (odd)
            caller.code.push_back(BinaryValue{Binary::CheckedAdd});
        caller.code.push_back(Return{});
        module.functions.push_back(std::move(caller));
    }
    auto recursive = scalar(512);
    recursive.name = "guard_recursive";
    recursive.parameters = {Type::I64};
    recursive.slots = {{8, Type::I64}, {512, Type::I64}};
    // The harness supplies 3 or 64. This recursion always terminates even if a
    // broken guard/probe fails to stop it; no unbounded real-stack recursion.
    recursive.code = {
        BindParameter{0, 8, Type::I64}, Constant{42, Type::I64}, Store{512, Type::I64},
        Load{8, Type::I64}, Push{}, Constant{0, Type::I64},
        Compare{Comparison::Equal, Type::I64}, BranchFalse{1},
        Constant{42, Type::I64}, Return{}, Label{1}, Load{8, Type::I64}, Push{},
        Constant{1, Type::I64}, BinaryValue{Binary::CheckedSubtract}, Push{},
        Call{"guard_recursive"}, Return{}};
    module.functions.push_back(std::move(recursive));
    return module;
}
void malformedFrames() {
    for (const int bytes : {-16, 8, 65552}) {
        try {
            (void)validate(fixture(bytes, "scalar"));
        } catch (const Error &error) {
            require(std::string(error.what()).find("invalid frame size") != std::string::npos,
                    "wrong frame rejection");
            ++passed;
            continue;
        }
        throw Error("malformed frame accepted");
    }
}
} // namespace
int main(int argc, char **argv) {
    try {
        if (argc == 2 && std::string(argv[1]) == "--emit-guard-fixtures") {
            std::cout << X86Emitter{}.emit(validate(guardFixtures()));
            return 0;
        }
        require(argc == 1, "usage: stack-probes [--emit-guard-fixtures]");
        frameTests();
        callTests();
        malformedFrames();
        std::cout << passed << " stack-probe IR/assembly cases passed\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
