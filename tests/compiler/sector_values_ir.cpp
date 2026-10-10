// Source-independent owned-sector IR checks. No parser or semantic lowering is used.
// --emit-abi emits the private bootstrap fixtures consumed by sector_values_abi.py.
#include "ir_verify.hpp"
#include "x86.hpp"
#include <functional>
#include <iostream>
#include <sstream>
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

void accept(const std::string &name, Module module) {
    require(!X86Emitter{}.emit(validate(std::move(module))).empty(), "empty assembly");
    ++accepted;
    std::cout << "PASS sector IR " << name << '\n';
}

void reject(const std::string &name, Module module, const std::function<void(Module &)> &change,
            const std::string &diagnostic) {
    change(module);
    try {
        (void)validate(std::move(module));
    } catch (const Error &error) {
        require(std::string(error.what()).find(diagnostic) != std::string::npos,
                name + ": wrong diagnostic: " + error.what());
        ++rejected;
        std::cout << "PASS sector IR " << name << '\n';
        return;
    }
    throw Error(name + ": malformed IR accepted");
}

Module shapes() {
    Module module;
    module.classLayouts["Block"] = std::vector<Type>(512, Type::U8);
    module.classFields["Block"] = {{Type::U8, 0, 512, true}};
    module.classLayouts["Report"] = {Type::U64};
    module.classLayouts["Report"].insert(module.classLayouts["Report"].end(), 512, Type::U8);
    module.classFields["Report"] = {{Type::U64, 0, 1, false}, {Type("Block"), 1, 512, false}};
    return module;
}

Module shapeOnly() {
    auto module = shapes();
    IRFunction function;
    function.name = "entry";
    function.result = Type::I64;
    function.code = {Constant{42, Type::I64}, Return{}};
    module.functions.push_back(function);
    return module;
}

// Literal protocol oracle: status occupies bytes 0..7; payload occupies 8..519.
// These expectations never call computeClassStorageLayouts or storageWidth.
void supplyLiteralStorage(Module &module) {
    ClassStorage block;
    block.fieldOffsets = {0};
    block.sizeBytes = 512;
    block.alignment = 1;
    block.reservedBytes = 512;
    for (int byte = 0; byte < 512; ++byte)
        block.leafOffsets.push_back(byte);
    ClassStorage report;
    report.fieldOffsets = {0, 8};
    report.sizeBytes = 520;
    report.alignment = 8;
    report.reservedBytes = 520;
    report.leafOffsets = {0};
    for (int byte = 0; byte < 512; ++byte)
        report.leafOffsets.push_back(8 + byte);
    module.classStorage = {{"Block", block}, {"Report", report}};
}

void blockSlot(IRFunction &function, int base, const std::string &name = "Block") {
    function.objectSlots[base] = {name, false};
    for (int byte = 0; byte < 512; ++byte)
        function.slots[base - byte] = Type::U8;
}

void reportSlot(IRFunction &function, int base, const std::string &name = "Report") {
    function.objectSlots[base] = {name, false};
    function.slots[base] = Type::U64;
    for (int byte = 0; byte < 512; ++byte)
        function.slots[base - 8 - byte] = Type::U8;
}

Module copyModule(const std::string &kind) {
    auto module = shapes();
    module.classLayouts["Other"] = module.classLayouts["Block"];
    module.classFields["Other"] = module.classFields["Block"];
    module.classLayouts["WrappedBlock"] = module.classLayouts["Block"];
    module.classFields["WrappedBlock"] = {{Type("Block"), 0, 512, false}};
    module.classLayouts["Receiver"] = {Type::U64};
    IRFunction entry;
    entry.name = "entry";
    entry.result = kind == "constructor" ? Type::I64 : Type("Block");
    entry.frameBytes = 1040;
    blockSlot(entry, 512);
    blockSlot(entry, 1024, kind == "constructor" ? "WrappedBlock" : "Block");
    entry.code = {BeginObject{512}};
    for (int byte = 0; byte < 512; ++byte) {
        entry.code.push_back(Constant{byte % 256, Type::U8});
        entry.code.push_back(Store{512 - byte, Type::U8});
    }
    entry.code.push_back(BeginObject{1024});
    if (kind == "copy") {
        entry.code.push_back(CopyObject{512, 1024});
    } else {
        IRFunction target;
        target.name = "target";
        target.result = kind == "constructor" ? Type::I64 : Type("Block");
        target.parameters = {Type("Block")};
        target.frameBytes = 512;
        blockSlot(target, 512);
        target.code = {BindObjectParameter{0, 512, "Block"}};
        if (kind == "constructor") {
            target.receiver = Receiver{"WrappedBlock", true, true};
            target.code.insert(target.code.end(), {InitializeObjectField{0, 0, 512},
                                                  Constant{0, Type::I64}, Return{}});
            entry.code.push_back(MethodCall{"target", 1024, {512}});
        } else {
            target.code.push_back(ReturnObject{512});
            if (kind == "method") {
                target.receiver = Receiver{"Receiver", false, false};
                entry.objectSlots[1032] = {"Receiver", false};
                entry.slots[1032] = Type::U64;
                entry.code.insert(entry.code.end(), {BeginObject{1032}, Constant{7, Type::U64},
                                                     Store{1032, Type::U64}});
                entry.code.push_back(MethodCall{"target", 1032, {512}, 1024});
            } else {
                entry.code.push_back(AggregateCall{"target", {512}, 1024});
            }
        }
        module.functions.push_back(target);
    }
    if (kind == "constructor")
        entry.code.push_back(Return{});
    else
        entry.code.push_back(ReturnObject{1024});
    module.functions.insert(module.functions.begin(), entry);
    return module;
}

// Flat local classes deliberately retain their pre-existing wider budget.
Module budgetModule(int bytes, int words, bool boundary, bool composed = false) {
    Module module;
    auto &leaves = module.classLayouts["Value"];
    auto &fields = module.classFields["Value"];
    leaves.insert(leaves.end(), bytes, Type::U8);
    leaves.insert(leaves.end(), words, Type::U64);
    for (int leaf = 0; leaf < bytes + words; ++leaf)
        fields.push_back({leaves[leaf], leaf, 1, false});
    if (composed) {
        module.classLayouts["Empty"] = {};
        fields.push_back({Type("Empty"), bytes + words, 0, false});
    }
    IRFunction function;
    function.name = "entry";
    function.result = boundary ? Type("Value") : Type::I64;
    if (boundary) {
        const int wordStart = (bytes + 7) / 8 * 8;
        const int reserved = (wordStart + words * 8 + 7) / 8 * 8;
        const int base = reserved == 0 ? 8 : reserved;
        function.frameBytes = (base + 15) / 16 * 16;
        function.parameters = {Type("Value")};
        function.objectSlots[base] = {"Value", false};
        for (int byte = 0; byte < bytes; ++byte)
            function.slots[base - byte] = Type::U8;
        for (int word = 0; word < words; ++word)
            function.slots[base - wordStart - word * 8] = Type::U64;
        function.code = {BindObjectParameter{0, base, "Value"}, ReturnObject{base}};
    } else {
        function.code = {Constant{42, Type::I64}, Return{}};
    }
    module.functions = {function};
    return module;
}

// This oracle spells out byte offsets and machine widths independently of
// production layout/storage helpers. Labels isolate the instruction under test.
std::string between(const std::string &text, const std::string &first, const std::string &last) {
    const auto begin = text.find(first);
    require(begin != std::string::npos, "missing assembly start: " + first);
    const auto end = text.find(last, begin + first.size());
    require(end != std::string::npos, "missing assembly end: " + last);
    return text.substr(begin + first.size(), end - begin - first.size());
}

std::string
copies(int bytes, const std::function<std::string(int)> &source, const std::function<std::string(int)> &destination) {
    std::string expected;
    for (int byte = 0; byte < bytes;) {
        const bool word = bytes - byte >= 8;
        expected += std::string("    ") + (word ? "movq " : "movzbq ") + source(byte) + ", %rax\n";
        expected += std::string("    ") + (word ? "movq %rax, " : "movb %al, ") + destination(byte) + "\n";
        byte += word ? 8 : 1;
    }
    return expected;
}

// Extract only adjacent payload load/store pairs. Setup, gap zeroing, probes,
// hidden capability saves and call cleanup remain covered by the ABI runner.
std::string transfers(const std::string &assembly) {
    std::istringstream lines(assembly);
    std::string line, store, result;
    while (std::getline(lines, line)) {
        if ((line.starts_with("    movq ") || line.starts_with("    movzbq ")) && line.ends_with(", %rax") &&
            line.find('(') != std::string::npos) {
            require(static_cast<bool>(std::getline(lines, store)), "payload load without store");
            require(store.starts_with("    movq %rax, ") || store.starts_with("    movb %al, "),
                    "payload copy must use RAX only: " + store);
            result += line + "\n" + store + "\n";
        }
    }
    return result;
}

void byteRunTests() {
    for (int bytes : {0, 1, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 63, 64, 65, 511, 512}) {
        auto module = budgetModule(bytes, 0, true);
        auto target = module.functions[0];
        target.name = "target";
        auto &entry = module.functions[0];
        const int base = std::max(8, (bytes + 7) / 8 * 8);
        entry.frameBytes = (3 * base + 15) / 16 * 16;
        for (int copy : {2, 3}) {
            entry.objectSlots[copy * base] = {"Value", false};
            for (int byte = 0; byte < bytes; ++byte)
                entry.slots[copy * base - byte] = Type::U8;
        }
        entry.code = {BindObjectParameter{0, base, "Value"},
                      Label{69},
                      BeginObject{2 * base},
                      Label{70},
                      CopyObject{base, 2 * base},
                      Label{71},
                      BeginObject{3 * base},
                      Label{72},
                      AggregateCall{"target", {2 * base}, 3 * base},
                      Label{73},
                      ReturnObject{3 * base}};
        module.functions.push_back(target);
        const auto assembly = X86Emitter{}.emit(validate(std::move(module)));
        const auto local = [](int base, int byte) {
            return "-" + std::to_string(base - byte) + "(%rbp)";
        };
        const auto pointer = [](int byte) {
            return std::to_string(byte) + "(%r10)";
        };
        require(transfers(between(assembly, "entry:\n", ".Lau0_69:\n")) == copies(
                                                                               bytes,
                                                                               [](int byte) {
                                                                                   return std::to_string(byte) +
                                                                                          "(%r11)";
                                                                               },
                                                                               [&](int byte) {
                                                                                   return local(base, byte);
                                                                               }),
                "bounded byte parameter binding");
        require(between(assembly, ".Lau0_70:\n", ".Lau0_71:\n") == copies(
                                                                       bytes,
                                                                       [&](int byte) {
                                                                           return local(base, byte);
                                                                       },
                                                                       [&](int byte) {
                                                                           return local(2 * base, byte);
                                                                       }),
                "bounded local byte copy");
        require(transfers(between(assembly, ".Lau0_72:\n", ".Lau0_73:\n")) == copies(
                                                                                  bytes,
                                                                                  [&](int byte) {
                                                                                      return local(2 * base, byte);
                                                                                  },
                                                                                  [](int byte) {
                                                                                      return std::to_string(byte) +
                                                                                             "(%rsp)";
                                                                                  }),
                "bounded packed byte argument");
        require(transfers(between(assembly, ".Lau0_73:\n", ".Lreturn0:\n")) == copies(
                                                                                   bytes,
                                                                                   [&](int byte) {
                                                                                       return local(3 * base, byte);
                                                                                   },
                                                                                   pointer),
                "bounded byte result");
        ++accepted;
        std::cout << "PASS sector IR exact qwords and byte tail length=" << bytes << '\n';
    }
}

Module fieldCopyModule(const std::string &kind) {
    Module module;
    module.classLayouts["Bytes9"] = std::vector<Type>(9, Type::U8);
    module.classFields["Bytes9"] = {{Type::U8, 0, 9, true}};
    module.classLayouts["Wrapped"] = std::vector<Type>(11, Type::U8);
    module.classFields["Wrapped"] = {{Type::U8, 0, 1, false}, {Type("Bytes9"), 1, 9, false}, {Type::U8, 10, 1, false}};
    IRFunction function;
    function.name = "entry";
    function.frameBytes = 64;
    function.result = Type::I64;
    auto slot = [&](int base, const std::string &name, int size) {
        function.objectSlots[base] = {name, base == 48};
        for (int byte = 0; byte < size; ++byte)
            function.slots[base - byte] = Type::U8;
    };
    slot(16, "Bytes9", 9);
    if (kind == "project_local" || kind == "assign_local") {
        function.parameters = {Type("Wrapped"), Type("Bytes9")};
        slot(32, "Wrapped", 11);
        slot(48, "Wrapped", 11);
        function.code = {BindObjectParameter{0, 32, "Wrapped"},
                         BindObjectParameter{1, 16, "Bytes9"},
                         BeginObject{48},
                         CopyObject{32, 48}};
    } else {
        function.parameters = {Type("Bytes9")};
        function.receiver = Receiver{"Wrapped", kind != "project_receiver", kind == "initialize"};
        function.code = {BindObjectParameter{0, 16, "Bytes9"}};
    }
    if (kind == "initialize")
        function.code.insert(
            function.code.end(),
            {Constant{17, Type::U8}, ReceiverStore{0, Type::U8}, Constant{19, Type::U8}, ReceiverStore{2, Type::U8}});
    if (kind.starts_with("project")) {
        slot(64, "Bytes9", 9);
        function.code.insert(
            function.code.end(),
            {BeginObject{64}, Label{70}, ObjectFieldCopy{kind == "project_local" ? 48 : 0, 1, 64}, Label{71}});
    } else if (kind == "initialize") {
        function.code.insert(function.code.end(), {Label{70}, InitializeObjectField{0, 1, 16}, Label{71}});
    } else {
        function.code.insert(function.code.end(),
                             {Label{70}, AssignObjectField{kind == "assign_local" ? 48 : 0, 1, 16}, Label{71}});
    }
    function.code.insert(function.code.end(), {Constant{42, Type::I64}, Return{}});
    module.functions = {function};
    return module;
}

void fieldCopyTests() {
    for (const std::string kind :
         {"project_local", "project_receiver", "assign_local", "assign_receiver", "initialize"}) {
        const auto assembly = X86Emitter{}.emit(validate(fieldCopyModule(kind)));
        const auto copied = transfers(between(assembly, ".Lau0_70:\n", ".Lau0_71:\n"));
        const auto expected = kind.starts_with("project") ? copies(
                                                                9,
                                                                [](int byte) {
                                                                    return std::to_string(1 + byte) + "(%r10)";
                                                                },
                                                                [](int byte) {
                                                                    return "-" + std::to_string(64 - byte) + "(%rbp)";
                                                                })
                                                          : copies(
                                                                9,
                                                                [](int byte) {
                                                                    return "-" + std::to_string(16 - byte) + "(%rbp)";
                                                                },
                                                                [](int byte) {
                                                                    return std::to_string(1 + byte) + "(%r10)";
                                                                });
        require(copied == expected, "unaligned selected field range: " + kind);
        ++accepted;
        std::cout << "PASS sector IR unaligned selected field range " << kind << '\n';
    }
}

Module boundsModule(bool split = false) {
    auto module = shapes();
    if (split)
        module.classFields["Block"] = {{Type::U8, 0, 256, true}, {Type::U8, 256, 256, true}};
    IRFunction function;
    function.name = "entry";
    function.result = Type::U8;
    function.receiver = Receiver{"Block", false, false};
    function.parameters = {Type::I64};
    function.frameBytes = 16;
    function.slots = {{8, Type::I64}};
    function.code = {BindParameter{0, 8, Type::I64}, Load{8, Type::I64}, ReceiverBoundsGuard{0},
                     ReceiverIndexLoad{0}, Return{}};
    module.functions = {function};
    return module;
}

std::int64_t status(int record) {
    return 0x1100000000000000LL + record;
}

int payload(int record, int byte) {
    return (byte * 37 + record * 53 + (byte / 256) * 17) % 256;
}

void compareCurrent(IRFunction &function, std::int64_t value, const Type &type) {
    function.code.insert(function.code.end(), {Push{}, Constant{value, type},
                                               Compare{Comparison::Equal, type}, BranchFalse{1}});
}

void checkReport(IRFunction &function, int base, int record) {
    function.code.push_back(Load{base, Type::U64});
    compareCurrent(function, status(record), Type::U64);
    for (int byte = 0; byte < 512; ++byte) {
        function.code.push_back(Load{base - 8 - byte, Type::U8});
        compareCurrent(function, payload(record, byte), Type::U8);
    }
}

void sixParameters(IRFunction &function) {
    for (int record = 0; record < 6; ++record) {
        const int base = (record + 1) * 520;
        function.parameters.push_back(Type("Report"));
        reportSlot(function, base);
        function.code.push_back(BindObjectParameter{record, base, "Report"});
    }
}

void checkBlock(IRFunction &function, int base) {
    for (int byte = 0; byte < 512; ++byte) {
        function.code.push_back(Load{base - byte, Type::U8});
        compareCurrent(function, payload(5, byte), Type::U8);
    }
}

void mixedCopyFixture(Module &module) {
    const auto state = Type::enumeration("CopyState");
    module.enumCases["CopyState"] = 2;
    module.classLayouts["CopyBytes9"] = std::vector<Type>(9, Type::U8);
    module.classFields["CopyBytes9"] = {{Type::U8, 0, 9, true}};
    auto &leaves = module.classLayouts["CopyMixed"];
    leaves = std::vector<Type>(11, Type::U8);
    leaves.insert(leaves.end(), {Type::Bool, state, Type::U64});
    leaves.insert(leaves.end(), 7, Type::U8);
    module.classFields["CopyMixed"] = {{Type::U8, 0, 1, false},
                                       {Type("CopyBytes9"), 1, 9, false},
                                       {Type::U8, 10, 1, false},
                                       {Type::Bool, 11, 1, false},
                                       {state, 12, 1, false},
                                       {Type::U64, 13, 1, false},
                                       {Type::U8, 14, 7, true}};
    // Literal canonical offsets: the final seven bytes may not widen into
    // padding, and the bool/enum/u64 remain three separate eight-byte leaves.
    const std::vector<int> offsets = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 16, 24, 32, 40, 41, 42, 43, 44, 45, 46};
    IRFunction function;
    function.name = "sector_in_mixed";
    function.result = Type("CopyMixed");
    function.parameters = {Type("CopyMixed")};
    function.frameBytes = 48;
    function.objectSlots[48] = {"CopyMixed", false};
    for (std::size_t leaf = 0; leaf < offsets.size(); ++leaf)
        function.slots[48 - offsets[leaf]] = leaves[leaf];
    function.code = {BindObjectParameter{0, 48, "CopyMixed"}, Label{70}, ReturnObject{48}};
    module.functions.push_back(function);
}

void gapCopyFixture(Module &module) {
    module.classLayouts["GapChild"] = {Type::U64};
    module.classLayouts["GapChild"].insert(module.classLayouts["GapChild"].end(), 7, Type::U8);
    module.classFields["GapChild"] = {{Type::U64, 0, 1, false}, {Type::U8, 1, 7, true}};
    module.classLayouts["GapOuter"] = module.classLayouts["GapChild"];
    module.classLayouts["GapOuter"].push_back(Type::U8);
    module.classFields["GapOuter"] = {{Type("GapChild"), 0, 8, false}, {Type::U8, 8, 1, false}};
    IRFunction function;
    function.name = "sector_in_gap";
    function.result = Type("GapOuter");
    function.parameters = {Type("GapOuter")};
    function.frameBytes = 32;
    function.objectSlots[24] = {"GapOuter", false};
    function.slots[24] = Type::U64;
    for (int byte : {8, 9, 10, 11, 12, 13, 14, 16})
        function.slots[24 - byte] = Type::U8;
    function.code = {BindObjectParameter{0, 24, "GapOuter"}, Label{70}, ReturnObject{24}};
    module.functions.push_back(function);
}

void gapCopyTests() {
    Module module;
    gapCopyFixture(module);
    const auto assembly = X86Emitter{}.emit(validate(std::move(module)));
    auto expected = [&](const std::function<std::string(int)> &source,
                        const std::function<std::string(int)> &destination) {
        auto result = "    movq " + source(0) + ", %rax\n    movq %rax, " + destination(0) + "\n";
        // These are eight consecutive logical U8 leaves, but child tail padding
        // at byte 15 breaks physical adjacency before the outer sibling at 16.
        for (int byte : {8, 9, 10, 11, 12, 13, 14, 16})
            result += "    movzbq " + source(byte) + ", %rax\n    movb %al, " + destination(byte) + "\n";
        return result;
    };
    const auto local = [](int byte) {
        return "-" + std::to_string(24 - byte) + "(%rbp)";
    };
    require(transfers(between(assembly, "sector_in_gap:\n", ".Lau0_70:\n")) == expected(
                                                                                   [](int byte) {
                                                                                       return std::to_string(byte) +
                                                                                              "(%r11)";
                                                                                   },
                                                                                   local),
            "eight logical byte leaves cannot bind across nested padding");
    require(transfers(between(assembly, ".Lau0_70:\n", ".Lreturn0:\n")) == expected(local,
                                                                                    [](int byte) {
                                                                                        return std::to_string(byte) +
                                                                                               "(%r10)";
                                                                                    }),
            "eight logical byte leaves cannot return across nested padding");
    ++accepted;
    std::cout << "PASS sector IR eight logical U8 leaves split by canonical nested padding\n";
}

void mixedCopyTests() {
    Module module;
    mixedCopyFixture(module);
    const auto assembly = X86Emitter{}.emit(validate(std::move(module)));
    auto expected = [&](const std::function<std::string(int)> &source,
                        const std::function<std::string(int)> &destination) {
        auto result = copies(11, source, destination);
        for (int byte : {16, 24, 32})
            result += "    movq " + source(byte) + ", %rax\n    movq %rax, " + destination(byte) + "\n";
        result += copies(
            7,
            [&](int byte) {
                return source(40 + byte);
            },
            [&](int byte) {
                return destination(40 + byte);
            });
        return result;
    };
    const auto local = [](int byte) {
        return "-" + std::to_string(48 - byte) + "(%rbp)";
    };
    require(transfers(between(assembly, "sector_in_mixed:\n", ".Lau0_70:\n")) == expected(
                                                                                     [](int byte) {
                                                                                         return std::to_string(byte) +
                                                                                                "(%r11)";
                                                                                     },
                                                                                     local),
            "mixed binding widths and padding boundaries");
    require(transfers(between(assembly, ".Lau0_70:\n", ".Lreturn0:\n")) == expected(local,
                                                                                    [](int byte) {
                                                                                        return std::to_string(byte) +
                                                                                               "(%r10)";
                                                                                    }),
            "mixed return widths and padding boundaries");
    ++accepted;
    std::cout << "PASS sector IR mixed U8/bool/enum/u64 widths and untouched gaps\n";
}

Module abiModule() {
    auto module = shapes();
    module.classLayouts["Receiver"] = {Type::U64};
    module.classLayouts["WrappedReport"] = module.classLayouts["Report"];
    module.classFields["WrappedReport"] = {{Type("Report"), 0, 513, false}};
    IRFunction clobber;
    clobber.name = "sector_clobber";
    clobber.result = Type::I64;
    clobber.code = {Constant{0, Type::I64}, Return{}};
    module.functions.push_back(clobber);
    for (const std::string kind : {"function", "constructor", "method"}) {
        IRFunction incoming;
        incoming.name = "sector_in_" + kind;
        incoming.result = kind == "constructor" ? Type::I64 : Type("Report");
        incoming.frameBytes = 3120;
        sixParameters(incoming);
        if (kind == "constructor")
            incoming.receiver = Receiver{"WrappedReport", true, true};
        else if (kind == "method")
            incoming.receiver = Receiver{"Receiver", false, false};
        incoming.code.push_back(Call{"sector_clobber"});
        for (int record = 0; record < 6; ++record)
            checkReport(incoming, (record + 1) * 520, record);
        if (kind == "method") {
            incoming.code.push_back(ReceiverLoad{0, Type::U64});
            compareCurrent(incoming, 1000, Type::U64);
        }
        if (kind == "constructor") {
            incoming.code.insert(incoming.code.end(), {InitializeObjectField{0, 0, 3120},
                Constant{0, Type::I64}, Return{}, Label{1}, InitializeObjectField{0, 0, 520},
                Constant{0, Type::I64}, Return{}});
        } else {
            incoming.code.insert(incoming.code.end(), {ReturnObject{3120}, Label{1}, ReturnObject{520}});
        }
        module.functions.push_back(incoming);

        // The matching outgoing case replaces this target with handwritten assembly.
        auto target = incoming;
        target.name = "sector_target_" + kind;
        target.code.resize(6);
        if (kind == "constructor")
            target.code.insert(target.code.end(), {InitializeObjectField{0, 0, 3120},
                                                   Constant{0, Type::I64}, Return{}});
        else
            target.code.push_back(ReturnObject{3120});
        module.functions.push_back(target);
        IRFunction outgoing;
        outgoing.name = "sector_out_" + kind;
        outgoing.result = Type::I64;
        outgoing.frameBytes = 3648;
        sixParameters(outgoing);
        reportSlot(outgoing, 3640, kind == "constructor" ? "WrappedReport" : "Report");
        outgoing.objectSlots[3648] = {"Receiver", false};
        outgoing.slots[3648] = Type::U64;
        outgoing.code.insert(outgoing.code.end(), {BeginObject{3640}, BeginObject{3648},
            Constant{1000, Type::U64}, Store{3648, Type::U64}, Constant{1, Type::I64}, Push{}});
        const std::vector<int> arguments = {520, 1040, 1560, 2080, 2600, 3120};
        if (kind == "function")
            outgoing.code.push_back(AggregateCall{target.name, arguments, 3640});
        else
            outgoing.code.push_back(MethodCall{target.name, kind == "constructor" ? 3640 : 3648,
                                              arguments, kind == "constructor" ? 0 : 3640});
        checkReport(outgoing, 3640, 5);
        outgoing.code.insert(outgoing.code.end(), {Constant{42, Type::I64}, Jump{2}, Label{1},
            Constant{-2, Type::I64}, Label{2}, BinaryValue{Binary::CheckedAdd}, Return{}});
        module.functions.push_back(outgoing);
    }
    IRFunction block;
    block.name = "sector_in_block";
    block.result = Type("Block");
    block.parameters = {Type("Block")};
    block.frameBytes = 512;
    blockSlot(block, 512);
    block.code = {BindObjectParameter{0, 512, "Block"}, ReturnObject{512}};
    module.functions.push_back(block);
    block.name = "sector_target_block";
    module.functions.push_back(block);
    IRFunction blockOut;
    blockOut.name = "sector_out_block";
    blockOut.result = Type::I64;
    blockOut.parameters = {Type("Block")};
    blockOut.frameBytes = 1024;
    blockSlot(blockOut, 512);
    blockSlot(blockOut, 1024);
    blockOut.code = {BindObjectParameter{0, 512, "Block"}, BeginObject{1024},
                    Constant{1, Type::I64}, Push{}, AggregateCall{"sector_target_block", {512}, 1024}};
    checkBlock(blockOut, 1024);
    blockOut.code.insert(blockOut.code.end(), {Constant{42, Type::I64}, Jump{2}, Label{1},
        Constant{-2, Type::I64}, Label{2}, BinaryValue{Binary::CheckedAdd}, Return{}});
    module.functions.push_back(blockOut);
    mixedCopyFixture(module);
    gapCopyFixture(module);
    return module;
}

void directTests() {
    byteRunTests();
    fieldCopyTests();
    mixedCopyTests();
    gapCopyTests();
    auto literal = shapeOnly();
    supplyLiteralStorage(literal);
    accept("literal 512-byte Block and 513-leaf 520-byte Report", literal);
    auto enumReport = literal;
    const auto closedStatus = Type::enumeration("Status");
    enumReport.enumCases["Status"] = 2;
    enumReport.classLayouts["Report"][0] = closedStatus;
    enumReport.classFields["Report"][0].elementType = closedStatus;
    auto &enumFunction = enumReport.functions[0];
    enumFunction.result = Type("Report");
    enumFunction.parameters = {Type("Report")};
    enumFunction.frameBytes = 528;
    reportSlot(enumFunction, 520);
    enumFunction.slots[520] = closedStatus;
    enumFunction.code = {BindObjectParameter{0, 520, "Report"}, ReturnObject{520}};
    accept("closed Status enum plus Block copied Report", enumReport);
    reject("closed Report status slot cannot become u64", enumReport, [](Module &module) {
        module.functions[0].slots[520] = Type::U64;
    }, "object field slot type/layout mismatch");
    for (const std::string part : {"offset", "extent", "reservation", "alignment", "field"}) {
        reject("forged canonical " + part, literal, [part](Module &module) {
            auto &storage = module.classStorage.at("Report");
            if (part == "offset")
                storage.leafOffsets[512] = 518;
            else if (part == "extent")
                storage.sizeBytes = 519;
            else if (part == "reservation")
                storage.reservedBytes = 528;
            else if (part == "alignment")
                storage.alignment = 1;
            else
                storage.fieldOffsets[1] = 16;
        }, "noncanonical class storage metadata");
    }
    reject("513-byte private array", shapeOnly(), [](Module &module) {
        module.classLayouts["Block"].push_back(Type::U8);
        module.classFields["Block"][0].length = 513;
    }, "invalid logical class field shape");
    reject("zero private array", shapeOnly(), [](Module &module) {
        module.classFields["Block"][0].length = 0;
    }, "invalid logical class field shape");
    reject("non-byte private array remains capped at 64", shapeOnly(), [](Module &module) {
        module.classLayouts["Words"] = std::vector<Type>(65, Type::U64);
        module.classFields["Words"] = {{Type::U64, 0, 65, true}};
    }, "invalid logical class field shape");
    reject("wrong final byte leaf type", shapeOnly(), [](Module &module) {
        module.classLayouts["Block"].back() = Type::Bool;
    }, "logical class field leaf type mismatch");
    reject("missing final leaf", shapeOnly(), [](Module &module) {
        module.classLayouts["Block"].pop_back();
    }, "logical class field range exceeds layout");
    reject("nested child truncated", shapeOnly(), [](Module &module) {
        module.classFields["Report"][1].length = 511;
    }, "nested class field length mismatch");
    reject("nested byte range overlaps status", shapeOnly(), [](Module &module) {
        module.classFields["Report"][1].firstLeaf = 0;
    }, "invalid logical class field shape");

    accept("64 non-byte plus 8 byte leaves fit 520 reserved bytes", budgetModule(8, 64, true));
    accept("512 byte plus one word leaves fit 520 reserved bytes", budgetModule(512, 1, true));
    accept("flat local 8192 byte leaves retained", budgetModule(8192, 0, false));
    accept("flat local 8192 word leaves retained", budgetModule(0, 8192, false));
    for (const auto &[bytes, words] : {std::pair{513, 0}, std::pair{0, 65}, std::pair{9, 64},
                                    std::pair{511, 2}, std::pair{512, 2}}) {
        const auto label = std::to_string(bytes) + " bytes " + std::to_string(words) + " words";
        reject("copied budget " + label, budgetModule(bytes, words, true), [](Module &) {}, "value boundary");
        reject("composed budget " + label, budgetModule(bytes, words, false, true), [](Module &) {}, "composed");
    }

    for (const std::string kind : {"copy", "function", "constructor", "method"}) {
        const auto baseline = copyModule(kind);
        accept("complete sector " + kind, baseline);
        reject("last byte incomplete " + kind, baseline, [](Module &module) {
            auto &code = module.functions[0].code;
            code.erase(code.begin() + 1024);
        }, "not fully initialized");
        reject("wrong nominal sector " + kind, baseline, [](Module &module) {
            module.functions[0].objectSlots[512].className = "Other";
        }, "nominal class mismatch");
        reject("sector missing last scalar slot " + kind, baseline, [](Module &module) {
            module.functions[0].slots.erase(1);
        }, "object field slot type/layout mismatch");
        reject("sector overlapping object reservations " + kind, baseline, [](Module &module) {
            module.functions[0].objectSlots[1016] = {"Block", false};
        }, "overlapping object layouts");
        reject("sector extent underflows frame " + kind, baseline, [](Module &module) {
            module.functions[0].objectSlots[504] = {"Block", false};
        }, "invalid object layout offset");
    }
    reject("copy aliases result", copyModule("copy"), [](Module &module) {
        std::get<CopyObject>(module.functions[0].code[1026]).resultOffset = 512;
    }, "copy source aliases result");
    reject("function result aliases snapshot", copyModule("function"), [](Module &module) {
        std::get<AggregateCall>(module.functions[0].code[1026]).resultOffset = 512;
    }, "result aliases argument snapshot");
    reject("method result aliases snapshot", copyModule("method"), [](Module &module) {
        std::get<MethodCall>(module.functions[0].code[1029]).resultOffset = 512;
    }, "result aliases argument snapshot");
    reject("constructor receiver aliases snapshot", copyModule("constructor"), [](Module &module) {
        std::get<MethodCall>(module.functions[0].code[1026]).receiverOffset = 512;
    }, "receiver aliases argument snapshot");
    reject("large result is not pristine", copyModule("function"), [](Module &module) {
        auto &code = module.functions[0].code;
        code.insert(code.begin() + 1026, {Constant{1, Type::U8}, Store{513, Type::U8}});
    }, "result requires uninitialized object");
    auto reportConstructor = shapes();
    IRFunction constructor;
    constructor.name = "construct_report";
    constructor.result = Type::I64;
    constructor.receiver = Receiver{"Report", true, true};
    constructor.parameters = {Type("Block")};
    constructor.frameBytes = 512;
    blockSlot(constructor, 512);
    constructor.code = {BindObjectParameter{0, 512, "Block"}, Constant{9, Type::U64},
                        ReceiverStore{0, Type::U64}, InitializeObjectField{0, 1, 512},
                        Constant{0, Type::I64}, Return{}};
    reportConstructor.functions = {constructor};
    accept("status plus complete nested Block constructor", reportConstructor);
    reject("Report constructor missing nested Block completion", reportConstructor, [](Module &module) {
        module.functions[0].code.erase(module.functions[0].code.begin() + 3);
    }, "constructor returns before all fields initialized");
    reject("Report scalar store cannot forge nested completion", shapeOnly(), [](Module &module) {
        auto &function = module.functions[0];
        function.frameBytes = 528;
        reportSlot(function, 520);
        function.code = {BeginObject{520}, Constant{7, Type::U8}, Store{512, Type::U8},
                         Constant{42, Type::I64}, Return{}};
    }, "scalar store cannot write nested class field");

    accept("sector receiver dominating bounds token", boundsModule());
    accept("split sector receiver bounds token", boundsModule(true));
    reject("sector index missing guard", boundsModule(), [](Module &module) {
        module.functions[0].code.erase(module.functions[0].code.begin() + 2);
    }, "lacks matching dominating bounds token");
    reject("sector index token invalidated", boundsModule(), [](Module &module) {
        module.functions[0].code.insert(module.functions[0].code.begin() + 3, Constant{511, Type::I64});
    }, "lacks matching dominating bounds token");
    reject("sector index wrong logical array token", boundsModule(true), [](Module &module) {
        module.functions[0].code[3] = ReceiverIndexLoad{1};
    }, "lacks matching dominating bounds token");
    accept("six maximum Reports across function constructor and method ABI", abiModule());
}
} // namespace

int main(int argc, char **argv) {
    try {
        if (argc == 2 && std::string(argv[1]) == "--emit-abi") {
            std::cout << X86Emitter{}.emit(validate(abiModule()));
            return 0;
        }
        require(argc == 1, "usage: sector-values-ir [--emit-abi]");
        directTests();
        std::cout << "PASS sector IR: " << accepted << " accepted, " << rejected << " rejected, "
                  << accepted + rejected << " total\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL sector IR: " << error.what() << '\n';
        return 1;
    }
}
