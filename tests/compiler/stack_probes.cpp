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
    std::istringstream input(assembly.substr(begin + name.size() + 2, end - begin - name.size() - 2));
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
        require(at + 1 < lines.size() && lines[at].starts_with(prefix) && lines[at].ends_with(suffix),
                "missing reservation step");
        const auto amount = lines[at].substr(prefix.size(), lines[at].size() - prefix.size() - suffix.size());
        std::size_t consumed = 0;
        const int step = std::stoi(amount, &consumed);
        require(consumed == amount.size() && step > 0 && step <= 4096 && step % 16 == 0 && step <= expected - accounted,
                "invalid or oversized reservation step");
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
                f.code.insert(f.code.end(),
                              {Load{8, Type::I64}, ReceiverStore{0, Type::I64}, Constant{0, Type::I64}, Return{}});
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
            X86Emitter emitter;
            const auto assembly = emitter.emit(validate(fixture(bytes, mode)));
            const auto lines = body(assembly, "probe_scalar");
            require(lines.size() > 3 && lines[0] == "    pushq %rbp" && lines[1] == "    movq %rsp, %rbp",
                    "frame pointer ABI changed");
            const int hidden = mode == "scalar" ? 0 : mode == "combined" ? 32 : 16;
            const auto &facts = emitter.stackFacts().at("probe_scalar");
            require(facts.localBytes == bytes + hidden + 16 && facts.calls.empty(),
                    "frame facts omit return slot, saved RBP or private ABI slots");
            require(facts.copiedRecord.has_value() == (mode == "aggregate"), "copied ABI excludes receiver modes");
            if (facts.copiedRecord)
                require(facts.copiedRecord->parameterBytes == std::vector<int>{8} &&
                            facts.copiedRecord->resultBytes == 8,
                        "copied ABI uses canonical input/result sizes");
            auto at = reservation(lines, 2, bytes + hidden);
            const auto save = [&](const std::string &reg, int offset) {
                require(at < lines.size() &&
                            lines[at++] == "    movq " + reg + ", -" + std::to_string(offset) + "(%rbp)",
                        "hidden capability save changed");
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
        caller.code.insert(caller.code.end(), {AggregateCall{"probe_target", {8}, 16}, Load{16, Type::I64}});
        if (odd)
            caller.code.push_back(BinaryValue{Binary::CheckedAdd});
        caller.code.push_back(Return{});
        m.functions.push_back(std::move(caller));
        X86Emitter emitter;
        const auto assembly = emitter.emit(validate(std::move(m)));
        const auto &facts = emitter.stackFacts().at("probe_caller");
        require(facts.localBytes == (odd ? 96 : 80) &&
                    facts.calls == std::map<std::string, int>{{"probe_target", odd ? 96 : 80}},
                "packed call facts omit record, operand or alignment bytes");
        require(emitter.stackFacts().at("probe_target").localBytes == 48,
                "callee independently includes its incoming return slot");
        const auto lines = body(assembly, "probe_caller");
        reservation(lines, 2, 48);
        const auto record = std::find(lines.begin(), lines.end(), "    subq $16, %rsp");
        require(record != lines.end(), "missing outgoing record");
        reservation(lines, static_cast<std::size_t>(record - lines.begin()), 16);
        require(assembly.find("    movq %rsp, %r11\n    leaq -16(%rbp), %r10\n") != std::string::npos,
                "outgoing hidden ABI changed");
        const std::string call =
            odd ? "    subq $8, %rsp\n    call probe_target\n    addq $8, %rsp\n" : "    call probe_target\n";
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
        function.code = {Constant{42, Type::I64}, Store{bytes, Type::I64}, Load{bytes, Type::I64}, Return{}};
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
    recursive.code = {BindParameter{0, 8, Type::I64},
                      Constant{42, Type::I64},
                      Store{512, Type::I64},
                      Load{8, Type::I64},
                      Push{},
                      Constant{0, Type::I64},
                      Compare{Comparison::Equal, Type::I64},
                      BranchFalse{1},
                      Constant{42, Type::I64},
                      Return{},
                      Label{1},
                      Load{8, Type::I64},
                      Push{},
                      Constant{1, Type::I64},
                      BinaryValue{Binary::CheckedSubtract},
                      Push{},
                      Call{"guard_recursive"},
                      Return{}};
    module.functions.push_back(std::move(recursive));
    return module;
}

void stackFactTests() {
    X86Emitter emitter;
    Module module;
    auto leaf = scalar(0);
    leaf.name = "leaf";
    leaf.moduleScope = 1;
    auto unused = leaf;
    unused.name = "unused_import";
    auto caller = scalar(0);
    caller.name = "branches";
    caller.code = {Constant{1, Type::I64},
                   Push{},
                   Call{"leaf"},
                   Pop{},
                   Constant{1, Type::Bool},
                   BranchFalse{1},
                   Call{"leaf"},
                   Jump{2},
                   Label{1},
                   Constant{2, Type::I64},
                   Push{},
                   Call{"leaf"},
                   Pop{},
                   Label{2},
                   Label{3},
                   Constant{0, Type::Bool},
                   BranchFalse{4},
                   Call{"leaf"},
                   Jump{3},
                   Label{4},
                   Constant{0, Type::I64},
                   MetadataQuery{Query::Size},
                   Return{}};
    module.descriptorViews[1] = {};
    module.functions = {caller, leaf, unused};
    const auto validated = validate(module);
    const auto assembly = emitter.emit(validated);
    const auto &facts = emitter.stackFacts();
    require(facts.at("branches").localBytes == 32 &&
                facts.at("branches").calls == std::map<std::string, int>{{"leaf", 32}, {"aurora_reflect_size", 16}},
            "branch/loop call maxima or reflection edge facts");
    require(!facts.contains("unused_import") && assembly.find("unused_import:") == std::string::npos &&
                facts.contains("leaf"),
            "facts do not follow post-validation imported-function pruning");
    for (const std::string symbol :
         {"aurora_reflect_size", "aurora_reflect_field_count", "__au_reflect_s1_size", "__au_reflect_s1_field_count"})
        require(facts.at(symbol).localBytes == 8 && facts.at(symbol).calls.empty(),
                "reflection leaf facts must include exactly its incoming return slot");
    require(facts.size() == 6, "unexpected function or local UD2 trap metadata");
    require(emitter.emit(validated, SymbolBinding::Local).find(".globl ") == std::string::npos &&
                emitter.stackFacts().at("branches").localBytes == 32,
            "local binding changed stack facts");
    // Invalid dead imported bodies must still fail full verification.
    module.functions.back().frameBytes = -16;
    try {
        (void)validate(module);
        throw std::runtime_error("invalid unused imported body escaped validation");
    } catch (const Error &error) {
        require(std::string(error.what()).find("invalid frame size") != std::string::npos,
                "wrong dead-import diagnostic");
    }
    (void)emitter.emit(validate(fixture(0, "scalar")));
    require(emitter.stackFacts().size() == 3 && !emitter.stackFacts().contains("branches"),
            "reused emitter retained stale metadata");
    require(!emitter.stackFacts().at("probe_scalar").serviceRecord &&
                emitter.stackFacts().at("probe_scalar").serviceCalls.empty(),
            "service facts do not leak across emitter reuse");
    require(emitter.stackFactsJson() ==
                "{\"version\":2,\"functions\":{\"aurora_reflect_field_count\":{\"local_bytes\":8,\"calls\":{},"
                "\"copied_record\":null},"
                "\"aurora_reflect_size\":{\"local_bytes\":8,\"calls\":{},\"copied_record\":null},"
                "\"probe_scalar\":{\"local_bytes\":16,\"calls\":{},\"copied_record\":null}}}\n",
            "compact deterministic metadata format");
    ++passed;
}
void copiedRecordFacts() {
    for (const auto &leaves : std::vector<std::vector<Type>>{
             {}, {Type::U8}, {Type::U8, Type::I64}, {Type::I64, Type::U8}, std::vector<Type>(8, Type::U8)}) {
        auto module = fixture(32, "aggregate");
        module.classLayouts["Box"] = leaves;
        auto &function = module.functions[0];
        function.slots.clear();
        int offset = 0;
        for (const auto &type : leaves) {
            if (type != Type::U8)
                offset = (offset + 7) / 8 * 8;
            function.slots[32 - offset] = type;
            offset += type == Type::U8 ? 1 : 8;
        }
        function.objectSlots = {{32, {"Box", false}}};
        function.code = {BindObjectParameter{0, 32, "Box"}, ReturnObject{32}};
        X86Emitter emitter;
        (void)emitter.emit(validate(std::move(module)));
        const auto &facts = emitter.stackFacts().at("probe_scalar").copiedRecord;
        require(facts.has_value() == (leaves.size() == 8), "copied ABI rejects empty and padded classes");
        if (facts)
            require(facts->parameterBytes == std::vector<int>{8} && facts->resultBytes == 8,
                    "dense byte leaves retain physical ABI size");
        ++passed;
    }
    for (const auto &type : {Type::I64, Type::U64, Type::Bool, Type::U8}) {
        auto module = fixture(32, "aggregate");
        module.classLayouts["Box"] = {Type::I64, Type::I64};
        auto &function = module.functions[0];
        function.parameters.push_back(type);
        function.slots = {{16, Type::I64}, {8, Type::I64}, {24, type}};
        function.objectSlots = {{16, {"Box", false}}};
        function.code = {BindObjectParameter{0, 16, "Box"}, BindParameter{1, 24, type}, ReturnObject{16}};
        X86Emitter emitter;
        (void)emitter.emit(validate(std::move(module)));
        const auto &facts = emitter.stackFacts().at("probe_scalar").copiedRecord;
        require(facts.has_value() == (type != Type::U8), "copied ABI admits only qword scalar parameters");
        if (facts) {
            require(facts->parameterBytes == std::vector<int>({16, 8}) && facts->resultBytes == 16,
                    "copied ABI preserves parameter order and packed scalar extent");
            require(emitter.stackFactsJson().find(
                        "\"copied_record\":{\"parameter_bytes\":[16,8],\"result_bytes\":16}") != std::string::npos,
                    "copied ABI JSON retains the emitted sizes and order");
        }
        ++passed;
    }
}
void serviceStackFacts() {
    for (const bool odd : {false, true}) {
        Module module;
        module.enumCases[std::string(service::displayPutResultName)] = 2;
        auto pixel = scalar(48);
        pixel.name = "pixel";
        pixel.parameters = {Type::DisplaySession};
        pixel.serviceSlots = {16};
        pixel.code = {BindServiceParameter{0, 16, service::Kind::Display}};
        if (odd)
            pixel.code.insert(pixel.code.end(), {Constant{42, Type::I64}, Push{}});
        pixel.code.insert(pixel.code.end(),
                          {Constant{7, Type::U64},
                           Push{},
                           Constant{9, Type::U64},
                           Push{},
                           Constant{11, Type::U8},
                           Push{},
                           Constant{13, Type::U8},
                           Push{},
                           Constant{17, Type::U8},
                           Push{},
                           ServiceOperation{16, service::Operation::Pixel, 0, service::Kind::Display}});
        if (odd)
            pixel.code.push_back(Pop{});
        pixel.code.insert(pixel.code.end(), {Constant{42, Type::I64}, Return{}});
        auto caller = scalar(16);
        caller.name = "pixel_caller";
        caller.parameters = {Type::DisplaySession};
        caller.serviceSlots = {16};
        caller.code = {BindServiceParameter{0, 16, service::Kind::Display},
                       AcquireServiceLoan{1, 16, service::Kind::Display},
                       ServiceCall{"pixel", 1, 0, {0}, service::Kind::Display},
                       ReleaseServiceLoan{1, service::Kind::Display},
                       Return{}};
        module.functions = {caller, pixel};
        X86Emitter emitter;
        const auto assembly = emitter.emit(validate(std::move(module)));
        const auto &facts = emitter.stackFacts();
        require(!facts.at("pixel").copiedRecord && !facts.at("pixel_caller").copiedRecord,
                "service entries do not advertise copied-record ABI");
        const auto &record = facts.at("pixel").serviceRecord;
        require(record &&
                    record->parameters == std::vector<std::pair<std::string, int>>{{"builtin::DisplaySession", 16}} &&
                    record->resultBytes == 8 && facts.at("pixel_caller").serviceRecord &&
                    facts.at("pixel_caller").serviceCalls.empty(),
                "service record is distinct from copied ABI");
        const auto &call = facts.at("pixel").serviceCalls.at("__au_runtime_display_pixel");
        require(facts.at("pixel").serviceCalls.size() == 1 && call.arguments == 7 && call.resultMax == 1,
                "scalar service ABI follows actual pixel argument/completion lowering");
        require(emitter.stackFactsJson().find("\"service_abi\":{\"record\":{\"parameters\":[[\"builtin::"
                                              "DisplaySession\",16]],\"result_bytes\":8},\"calls\":{") !=
                    std::string::npos,
                "deterministic service ABI metadata");
        require(facts.at("pixel").localBytes == (odd ? 128 : 120) &&
                    facts.at("pixel").calls == std::map<std::string, int>{{"__au_runtime_display_pixel", 96}},
                "pixel facts omit operand pushes or seventh host argument/alignment");
        require(facts.at("pixel_caller").localBytes == 64 &&
                    facts.at("pixel_caller").calls == std::map<std::string, int>{{"pixel", 64}},
                "service call facts omit capability record");
        require(assembly.find(std::string("    subq $") + (odd ? "8" : "16") +
                              ", %rsp\n    movq %r10, (%rsp)\n    call __au_runtime_display_pixel\n") !=
                    std::string::npos,
                "seventh argument assembly changed");
        ++passed;
    }
}
void pairedServiceRecordFacts() {
    Module module;
    auto entry = scalar(64);
    entry.name = "paired";
    entry.parameters = {Type::ConsoleSession, Type::DisplaySession, Type::U64, Type::U64};
    entry.serviceSlots = {16, 32};
    entry.slots = {{40, Type::U64}, {48, Type::U64}};
    entry.code = {BindServiceParameter{0, 16, service::Kind::Console},
                  BindServiceParameter{1, 32, service::Kind::Display},
                  BindParameter{2, 40, Type::U64},
                  BindParameter{3, 48, Type::U64},
                  Constant{42, Type::I64},
                  Return{}};
    module.functions.push_back(entry);
    X86Emitter emitter;
    const auto assembly = emitter.emit(validate(module));
    const auto &record = emitter.stackFacts().at("paired").serviceRecord;
    require(record &&
                record->parameters == std::vector<std::pair<std::string, int>>{{"builtin::ConsoleSession", 16},
                                                                               {"builtin::DisplaySession", 16},
                                                                               {"scalar", 8},
                                                                               {"scalar", 8}} &&
                record->resultBytes == 8,
            "paired service record order and scalar widths");
    require(assembly.find("movq 32(%r11), %rax") != std::string::npos &&
                assembly.find("movq 40(%r11), %rax") != std::string::npos,
            "paired scalar arguments follow both complete grants");
    module.functions[0].parameters[0] = Type::DisplaySession;
    try {
        (void)validate(module);
        throw std::runtime_error("wrong service role escaped validation");
    } catch (const Error &) {
    }
    ++passed;
}
void resourceStackFacts() {
    Module module;
    auto caller = scalar(48);
    caller.name = "resource_caller";
    caller.parameters = {Type::ByteRegion};
    caller.regionSlots = {8};
    caller.byteSlots = {{40, true}};
    caller.code = {BindRegionParameter{0, 8},
                   BeginBytes{40},
                   Constant{1, Type::I64},
                   AllocateBytes{8, 40},
                   ResourceCall{"resource_callee", 8, {0, 40}, 0},
                   EndBytes{40},
                   Constant{42, Type::I64},
                   Return{}};
    auto callee = caller;
    callee.name = "resource_callee";
    callee.parameters.push_back(Type::OwnedBytes);
    callee.code = {BindRegionParameter{0, 8}, BindBytesParameter{1, 40}, BytesLength{40}, EndBytes{40}, Return{}};
    module.functions = {caller, callee};
    X86Emitter emitter;
    (void)emitter.emit(validate(std::move(module)));
    const auto &facts = emitter.stackFacts();
    require(!facts.at("resource_caller").copiedRecord && !facts.at("resource_callee").copiedRecord,
            "resource entries do not advertise copied-record ABI");
    require(facts.at("resource_caller").localBytes == 128 &&
                facts.at("resource_caller").calls == std::map<std::string, int>{{"resource_callee", 128},
                                                                                {"__au_runtime_bytes_allocate", 80},
                                                                                {"__au_runtime_bytes_drop", 96}},
            "resource call/hidden allocation/cleanup facts");
    require(facts.at("resource_callee").localBytes == 96 &&
                facts.at("resource_callee").calls == std::map<std::string, int>{{"__au_runtime_bytes_drop", 96}},
            "callee cleanup save and alignment facts");
    ++passed;
}

void malformedFrames() {
    for (const int bytes : {-16, 8, 65552}) {
        try {
            (void)validate(fixture(bytes, "scalar"));
        } catch (const Error &error) {
            require(std::string(error.what()).find("invalid frame size") != std::string::npos, "wrong frame rejection");
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
        stackFactTests();
        copiedRecordFacts();
        serviceStackFacts();
        pairedServiceRecordFacts();
        resourceStackFacts();
        std::cout << passed << " stack-probe IR/assembly cases passed\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
