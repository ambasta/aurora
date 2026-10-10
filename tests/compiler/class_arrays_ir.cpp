// Independent class-array logical-shape, completion and checked-index controls.
#include "ir_verify.hpp"
#include <functional>
#include <iostream>

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
void object(IRFunction &function,
            int base,
            const std::string &name,
            bool mutableValue,
            const std::vector<Type> &leaves,
            const std::vector<int> &offsets) {
    function.objectSlots[base] = {name, mutableValue};
    for (std::size_t leaf = 0; leaf < leaves.size(); ++leaf)
        function.slots[base - offsets[leaf]] = leaves[leaf];
}
Module shape(bool packed = false, bool empty = false) {
    Module module;
    const std::vector<Type> child = empty    ? std::vector<Type>{}
                                    : packed ? std::vector<Type>{Type::U8, Type::U8, Type::U8}
                                             : std::vector<Type>{Type::U8, Type::U64};
    const std::vector<int> offsets = empty    ? std::vector<int>{}
                                     : packed ? std::vector<int>{0, 1, 2}
                                              : std::vector<int>{0, 8};
    const int size = empty ? 8 : packed ? 3 : 16;
    module.classLayouts["Child"] = child;
    module.classLayouts["Other"] = child;
    module.classStorage["Child"] = {offsets, offsets, size, packed ? 1 : 8, empty || packed ? 8 : 16};
    module.classStorage["Other"] = module.classStorage["Child"];
    auto twice = child;
    twice.insert(twice.end(), child.begin(), child.end());
    auto doubleOffsets = offsets;
    for (int offset : offsets)
        doubleOffsets.push_back(size + offset);
    module.classLayouts["Carrier"] = twice;
    module.classFields["Carrier"] = {{Type("Child"), 0, static_cast<int>(twice.size()), true, 2}};
    module.classStorage["Carrier"] = {
        doubleOffsets, {0}, empty ? 8 : size * 2, packed ? 1 : 8, empty || packed ? 8 : 32};
    module.classArrayCarriers.insert("Carrier");
    return module;
}
Module local(bool packed = false, bool empty = false) {
    auto module = shape(packed, empty);
    const auto &leaves = module.classLayouts.at("Child");
    const auto &offsets = module.classStorage.at("Child").leafOffsets;
    IRFunction function;
    function.name = "local";
    function.result = Type("Child");
    function.parameters = {Type("Child"), Type("Child")};
    function.frameBytes = 128;
    object(function, 16, "Child", false, leaves, offsets);
    object(function, 32, "Child", false, leaves, offsets);
    object(function,
           64,
           "Carrier",
           true,
           module.classLayouts.at("Carrier"),
           module.classStorage.at("Carrier").leafOffsets);
    object(function, 80, "Child", false, leaves, offsets);
    object(function,
           112,
           "Carrier",
           true,
           module.classLayouts.at("Carrier"),
           module.classStorage.at("Carrier").leafOffsets);
    function.code = {BindObjectParameter{0, 16, "Child"},
                     BindObjectParameter{1, 32, "Child"},
                     BeginObject{64},
                     InitializeClassArray{64, 0, {16, 32}},
                     BeginObject{112},
                     CopyObject{64, 112},
                     Constant{1, Type::I64},
                     ClassArrayBoundsGuard{64, 0},
                     ClassArrayAssign{64, 0, 16},
                     Constant{1, Type::I64},
                     ClassArrayBoundsGuard{64, 0},
                     BeginObject{80},
                     ClassArrayCopy{64, 0, 80},
                     ReturnObject{80}};
    module.functions.push_back(std::move(function));
    return module;
}
Module receiver(bool constructor = false, bool empty = false) {
    auto module = local(false, empty);
    module.classArrayCarriers.clear();
    module.classLayouts["Holder"] = module.classLayouts.at("Carrier");
    module.classFields["Holder"] = module.classFields.at("Carrier");
    module.classStorage["Holder"] = module.classStorage.at("Carrier");
    // A second field distinguishes same-element/same-length receiver identities.
    auto &holder = module.classLayouts["Holder"];
    const auto originalLeaves = holder.size();
    holder.insert(holder.end(), module.classLayouts.at("Carrier").begin(), module.classLayouts.at("Carrier").end());
    module.classFields["Holder"].push_back(
        {Type("Child"), static_cast<int>(originalLeaves), static_cast<int>(originalLeaves), true, 2});
    auto &physical = module.classStorage["Holder"];
    const auto oldOffsets = physical.leafOffsets;
    for (int offset : oldOffsets)
        physical.leafOffsets.push_back(32 + offset);
    physical.fieldOffsets.push_back(empty ? 0 : 32);
    if (!empty)
        physical.sizeBytes = physical.reservedBytes = 64;
    auto &function = module.functions[0];
    function.receiver = Receiver{"Holder", true, constructor};
    function.objectSlots.erase(64);
    function.objectSlots.erase(112);
    for (auto it = function.slots.begin(); it != function.slots.end();) {
        if ((it->first > 32 && it->first <= 64) || it->first > 80)
            it = function.slots.erase(it);
        else
            ++it;
    }
    if (constructor) {
        function.result = Type::I64;
        function.code = {BindObjectParameter{0, 16, "Child"},
                         BindObjectParameter{1, 32, "Child"},
                         InitializeClassArray{0, 0, {16, 32}},
                         InitializeClassArray{0, 1, {16, 16}},
                         Constant{0, Type::I64},
                         Return{}};
    } else {
        function.code = {BindObjectParameter{0, 16, "Child"},
                         BindObjectParameter{1, 32, "Child"},
                         Constant{1, Type::I64},
                         ClassArrayBoundsGuard{0, 0},
                         ClassArrayAssign{0, 0, 16},
                         Constant{0, Type::I64},
                         ClassArrayBoundsGuard{0, 0},
                         BeginObject{80},
                         ClassArrayCopy{0, 0, 80},
                         ReturnObject{80}};
    }
    return module;
}
void addShapeEntry(Module &module) {
    if (!module.functions.empty())
        return;
    IRFunction entry;
    entry.name = "shape_entry";
    entry.result = Type::I64;
    entry.code = {Constant{0, Type::I64}, Return{}};
    module.functions.push_back(std::move(entry));
}
void accept(const std::string &name, Module module) {
    addShapeEntry(module);
    try {
        (void)validate(std::move(module));
        ++accepted;
    } catch (const Error &error) {
        throw Error(name + ": unexpected rejection: " + error.what());
    }
}
void reject(const std::string &name,
            Module module,
            const std::function<void(Module &)> &mutation,
            const std::string &fragment = "") {
    addShapeEntry(module);
    mutation(module);
    try {
        (void)validate(std::move(module));
    } catch (const Error &error) {
        require(fragment.empty() || std::string(error.what()).find(fragment) != std::string::npos,
                name + ": wrong rejection: " + error.what());
        ++rejected;
        return;
    }
    throw Error(name + ": malformed IR accepted");
}
void rejectInstruction(
    const std::string &name, Module module, int position, const Instruction &replacement, const std::string &fragment) {
    reject(
        name,
        std::move(module),
        [&](Module &value) {
            value.functions[0].code[position] = replacement;
        },
        fragment);
}
void rejectInserted(const std::string &name,
                    Module module,
                    int position,
                    std::vector<Instruction> instructions,
                    const std::string &fragment = "") {
    reject(
        name,
        std::move(module),
        [&](Module &value) {
            auto &code = value.functions[0].code;
            code.insert(code.begin() + position, instructions.begin(), instructions.end());
        },
        fragment);
}
void rejectErased(const std::string &name, Module module, int position, const std::string &fragment) {
    reject(
        name,
        std::move(module),
        [&](Module &value) {
            auto &code = value.functions[0].code;
            code.erase(code.begin() + position);
        },
        fragment);
}
void rejectShape(const std::string &name, Module module, const std::string &fragment) {
    reject(
        name,
        std::move(module),
        [](Module &) {
        },
        fragment);
}
Module sizedArray(const std::vector<Type> &child, int count) {
    Module module;
    module.classLayouts["SizedChild"] = child;
    auto &leaves = module.classLayouts["SizedCarrier"];
    for (int element = 0; element < count; ++element)
        leaves.insert(leaves.end(), child.begin(), child.end());
    module.classFields["SizedCarrier"] = {{Type("SizedChild"), 0, static_cast<int>(leaves.size()), true, count}};
    module.classArrayCarriers.insert("SizedCarrier");
    return module;
}
Module emptyDepth(int children) {
    Module module;
    for (int index = 0; index < children; ++index) {
        const auto name = "Depth" + std::to_string(index);
        module.classLayouts[name] = {};
        module.classFields[name] = {};
        if (index != 0)
            module.classFields[name].push_back({Type("Depth" + std::to_string(index - 1)), 0, 0, false});
    }
    module.classLayouts["DepthCarrier"] = {};
    module.classFields["DepthCarrier"] = {{Type("Depth" + std::to_string(children - 1)), 0, 0, true, 2}};
    module.classArrayCarriers.insert("DepthCarrier");
    return module;
}
void run() {
    accept("512 byte leaves remain supported", sizedArray(std::vector<Type>(256, Type::U8), 2));
    accept("64 nonbyte leaves remain supported", sizedArray({Type::U64}, 64));
    accept("packed canonical storage under byte cap", sizedArray({Type::U8, Type::U64}, 32));
    accept("four class levels including carrier", emptyDepth(3));
    rejectShape("byte leaf cap preserved", sizedArray(std::vector<Type>(171, Type::U8), 3), "512 u8");
    rejectShape("nonbyte leaf cap preserved", sizedArray({Type::U64, Type::U64}, 33), "64 scalar");
    rejectShape("storage byte cap preserved", sizedArray({Type::U8, Type::U64}, 33), "520 bytes");
    rejectShape("fifth class level including carrier", emptyDepth(4), "depth 4");
    reject(
        "empty cycle through class array",
        shape(false, true),
        [](Module &m) {
            m.classArrayCarriers.clear();
            m.classFields["Child"] = {{Type("Child"), 0, 0, true, 2}};
        },
        "cyclic");
    reject(
        "owning class array elements",
        shape(false, true),
        [](Module &m) {
            m.classFields["Child"] = {{Type::OwnedBytes, 0, 0, false}};
        },
        "nested owning");
    accept("local checked copy and replacement", local());
    accept("packed three-byte stride", local(true));
    accept("empty local completion", local(false, true));
    auto vacuous = local(false, true);
    vacuous.functions[0].code.insert(vacuous.functions[0].code.begin() + 2, BeginObject{80});
    vacuous.functions[0].code[4] = InitializeClassArray{64, 0, {80, 80}};
    vacuous.functions[0].code[9] = ClassArrayAssign{64, 0, 80};
    vacuous.functions[0].code[12] = EndObject{80};
    vacuous.functions[0].code.insert(vacuous.functions[0].code.begin() + 13, BeginObject{80});
    accept("standalone empty sources retain vacuous completeness", std::move(vacuous));
    accept("receiver checked copy and replacement", receiver());
    accept("complete field constructor", receiver(true));
    accept("empty complete field constructor", receiver(true, true));
    auto duplicate = local();
    std::get<InitializeClassArray>(duplicate.functions[0].code[3]).sources = {16, 16};
    accept("repeated source creates independent elements", std::move(duplicate));
    auto saved = local();
    saved.functions[0].code.insert(saved.functions[0].code.begin() + 12, {Push{}, Constant{99, Type::I64}, Pop{}});
    accept("unchanged saved guard", std::move(saved));
    auto readonly = receiver();
    readonly.functions[0].receiver->mutableValue = false;
    readonly.functions[0].code.erase(readonly.functions[0].code.begin() + 2, readonly.functions[0].code.begin() + 5);
    accept("readonly receiver projection", std::move(readonly));

    reject("guard cannot merge with unguarded branch", local(), [](Module &m) {
        auto &code = m.functions[0].code;
        code.erase(code.begin() + 9, code.end());
        const std::vector<Instruction> tail = {Constant{0, Type::Bool},
                                               BranchFalse{1},
                                               Constant{1, Type::I64},
                                               ClassArrayBoundsGuard{64, 0},
                                               Jump{2},
                                               Label{1},
                                               Constant{1, Type::I64},
                                               Label{2},
                                               BeginObject{80},
                                               ClassArrayCopy{64, 0, 80},
                                               ReturnObject{80}};
        code.insert(code.end(), tail.begin(), tail.end());
    });
    reject(
        "empty constructor maybe-initialization survives branch",
        receiver(true, true),
        [](Module &m) {
            auto &code = m.functions[0].code;
            code.erase(code.begin() + 2, code.end());
            const std::vector<Instruction> tail = {Constant{0, Type::Bool},
                                                   BranchFalse{1},
                                                   InitializeClassArray{0, 0, {16, 32}},
                                                   Label{1},
                                                   InitializeClassArray{0, 0, {16, 32}},
                                                   InitializeClassArray{0, 1, {16, 32}},
                                                   Constant{0, Type::I64},
                                                   Return{}};
            code.insert(code.end(), tail.begin(), tail.end());
        },
        "more than once");
    reject(
        "empty constructor maybe-initialization survives backedge",
        receiver(true, true),
        [](Module &m) {
            auto &code = m.functions[0].code;
            code.erase(code.begin() + 2, code.end());
            const std::vector<Instruction> tail = {Label{1},
                                                   InitializeClassArray{0, 0, {16, 32}},
                                                   Constant{0, Type::Bool},
                                                   BranchFalse{2},
                                                   Jump{1},
                                                   Label{2},
                                                   InitializeClassArray{0, 1, {16, 32}},
                                                   Constant{0, Type::I64},
                                                   Return{}};
            code.insert(code.end(), tail.begin(), tail.end());
        },
        "more than once");
    for (bool packed : {false, true})
        reject(
            "scalar array guard cannot reclassify class-array payload",
            local(packed),
            [=](Module &m) {
                auto &function = m.functions[0];
                function.result = Type::U8;
                function.code.resize(6);
                const int count = packed ? 6 : 1;
                function.code.insert(function.code.end(),
                                     {Constant{count - 1, Type::I64},
                                      BoundsGuard{64, count, Type::U8},
                                      IndexLoad{64, count, Type::U8},
                                      Return{}});
            },
            "scalar array operation cannot address nested class field");
    rejectInstruction("missing guard", local(), 10, Constant{1, Type::I64}, "bounds token");
    rejectInstruction("forged root guard", local(), 10, ClassArrayBoundsGuard{112, 0}, "bounds token");
    rejectInserted("guard destroyed by constant", local(), 12, {Constant{1, Type::I64}}, "bounds token");
    rejectInserted("guard destroyed by conversion",
                   local(),
                   12,
                   {Convert{Type::I64, Type::U64}, Convert{Type::U64, Type::I64}},
                   "bounds token");
    rejectInstruction("guard for wrong receiver field", receiver(), 6, ClassArrayBoundsGuard{0, 1}, "bounds token");
    rejectInstruction(
        "scalar guard cannot authorize class copy", local(), 10, BoundsGuard{32, 1, Type::U8}, "bounds token");
    rejectInstruction(
        "class guard cannot authorize scalar load", local(), 12, IndexLoad{32, 1, Type::U8}, "bounds token");
    rejectInstruction("negative root", local(), 10, ClassArrayBoundsGuard{-1, 0}, "root offset");
    rejectInstruction("interior root", local(), 10, ClassArrayBoundsGuard{56, 0}, "exact object slot");
    rejectInstruction("negative field", local(), 10, ClassArrayBoundsGuard{64, -1}, "index out of range");
    rejectInstruction("past field", local(), 10, ClassArrayBoundsGuard{64, 1}, "index out of range");
    rejectInstruction("mistyped index", local(), 9, Constant{1, Type::U64}, "mistyped current");
    rejectInserted("inactive root", local(), 9, {EndObject{64}}, "outside active lifetime");
    rejectInserted("stale current lifetime guard", local(), 12, {EndObject{64}, BeginObject{64}, CopyObject{112, 64}});
    rejectInserted("stale saved lifetime guard",
                   local(),
                   12,
                   {Push{}, EndObject{64}, BeginObject{64}, CopyObject{112, 64}, Pop{}},
                   "bounds token");
    rejectErased("incomplete local root", local(), 3, "not fully initialized");
    rejectErased("empty incomplete local root", local(false, true), 3, "not completely initialized");
    reject(
        "const local replacement",
        local(),
        [](Module &m) {
            m.functions[0].objectSlots[64].mutableValue = false;
        },
        "const object");
    reject(
        "const receiver replacement",
        receiver(),
        [](Module &m) {
            m.functions[0].receiver->mutableValue = false;
        },
        "const receiver");
    reject(
        "constructor indexing",
        receiver(),
        [](Module &m) {
            m.functions[0].receiver->constructor = true;
            m.functions[0].result = Type::I64;
        },
        "during initialization");
    reject(
        "copy result nominal mismatch",
        local(),
        [](Module &m) {
            m.functions[0].objectSlots[80].className = "Other";
        },
        "nominal class mismatch");
    rejectInstruction("copy aliases root", local(), 12, ClassArrayCopy{64, 0, 64}, "aliases result");
    rejectInstruction("copy result interior", local(), 12, ClassArrayCopy{64, 0, 72}, "exact object slot");
    rejectErased("copy result inactive", local(), 11, "outside active lifetime");
    rejectInserted(
        "copy result already initialized", local(), 12, {Push{}, CopyObject{16, 80}, Pop{}}, "already initialized");
    rejectInstruction("assignment source aliases root", local(), 8, ClassArrayAssign{64, 0, 64}, "aliases root");
    rejectInstruction(
        "assignment source incomplete", local(), 8, ClassArrayAssign{64, 0, 80}, "outside active lifetime");
    reject(
        "assignment source wrong nominal",
        local(),
        [](Module &m) {
            m.functions[0].parameters[0] = Type("Other");
            m.functions[0].objectSlots[16].className = "Other";
            m.functions[0].code[0] = BindObjectParameter{0, 16, "Other"};
            std::get<InitializeClassArray>(m.functions[0].code[3]).sources = {32, 32};
        },
        "assignment nominal");
    reject(
        "initializer too short",
        local(),
        [](Module &m) {
            std::get<InitializeClassArray>(m.functions[0].code[3]).sources.pop_back();
        },
        "element count mismatch");
    reject(
        "initializer too long",
        local(),
        [](Module &m) {
            std::get<InitializeClassArray>(m.functions[0].code[3]).sources.push_back(16);
        },
        "element count mismatch");
    reject(
        "initializer root interior",
        local(),
        [](Module &m) {
            std::get<InitializeClassArray>(m.functions[0].code[3]).objectOffset = 56;
        },
        "exact object slot");
    reject(
        "initializer undeclared carrier",
        local(),
        [](Module &m) {
            m.classArrayCarriers.clear();
        },
        "declared carrier");
    reject(
        "initializer wrong carrier field",
        local(),
        [](Module &m) {
            std::get<InitializeClassArray>(m.functions[0].code[3]).fieldIndex = 1;
        },
        "declared carrier");
    rejectInserted(
        "initializer repeated local", local(), 4, {InitializeClassArray{64, 0, {16, 32}}}, "already initialized");
    rejectInserted("initializer repeated empty local",
                   local(false, true),
                   4,
                   {InitializeClassArray{64, 0, {16, 32}}},
                   "already initialized");
    rejectInstruction(
        "initializer outside constructor", receiver(), 2, InitializeClassArray{0, 0, {16, 32}}, "constructor receiver");
    rejectInstruction(
        "initializer repeated receiver", receiver(true), 3, InitializeClassArray{0, 0, {16, 32}}, "more than once");
    rejectInstruction("initializer repeated empty receiver",
                      receiver(true, true),
                      3,
                      InitializeClassArray{0, 0, {16, 32}},
                      "more than once");
    rejectErased("missing empty receiver initialization", receiver(true, true), 3, "initialized");
    for (const auto &operation : std::vector<Instruction>{
             ReceiverArrayZero{0}, ReceiverBoundsGuard{0}, ReceiverIndexLoad{0}, ReceiverIndexStore{0}})
        reject(
            "scalar receiver operation cannot reinterpret class array",
            receiver(),
            [&](Module &m) {
                m.functions[0].code[3] = operation;
            },
            "scalar array field");
    reject(
        "scalar leaf stores cannot initialize element",
        local(),
        [](Module &m) {
            m.functions[0].code[3] = Constant{1, Type::U8};
            m.functions[0].code.insert(m.functions[0].code.begin() + 4, Store{64, Type::U8});
        },
        "nested class field");
    reject(
        "overlapping forged element object",
        local(),
        [](Module &m) {
            object(m.functions[0], 48, "Child", true, m.classLayouts.at("Child"), {0, 8});
        },
        "overlapping object");
    reject(
        "zero element count",
        local(),
        [](Module &m) {
            m.classFields["Carrier"][0].elementCount = 0;
        },
        "1..64");
    reject(
        "excess element count",
        local(),
        [](Module &m) {
            m.classFields["Carrier"][0].elementCount = 65;
        },
        "1..64");
    reject(
        "leaf count mismatch",
        local(),
        [](Module &m) {
            m.classFields["Carrier"][0].length = 2;
        },
        "length mismatch");
    reject(
        "leaf order mismatch",
        local(),
        [](Module &m) {
            m.classLayouts["Carrier"][2] = Type::U64;
        },
        "leaf type mismatch");
    reject(
        "ordinary field count metadata",
        local(),
        [](Module &m) {
            m.classFields["Child"] = {{Type::U8, 0, 1, false, 2}, {Type::U64, 1, 1, false}};
        },
        "noncanonical");
    reject(
        "forged packed stride",
        local(true),
        [](Module &m) {
            m.classStorage["Carrier"].leafOffsets[3] = 8;
        },
        "noncanonical class storage");
    reject(
        "forged field offset",
        local(),
        [](Module &m) {
            m.classStorage["Carrier"].fieldOffsets[0] = 8;
        },
        "noncanonical class storage");
    reject(
        "unknown carrier",
        local(),
        [](Module &m) {
            m.classArrayCarriers.insert("Missing");
        },
        "unknown class array carrier");
    reject(
        "ordinary class marked carrier",
        local(),
        [](Module &m) {
            m.classArrayCarriers.insert("Other");
        },
        "exactly one class array field");
    reject(
        "carrier parameter",
        local(),
        [](Module &m) {
            m.functions[0].parameters[0] = Type("Carrier");
        },
        "cannot cross value boundary");
    reject(
        "carrier result",
        local(),
        [](Module &m) {
            m.functions[0].result = Type("Carrier");
        },
        "cannot cross value boundary");
    reject(
        "carrier receiver",
        local(),
        [](Module &m) {
            m.functions[0].receiver = Receiver{"Carrier", true, false};
        },
        "cannot be receiver");
    reject(
        "carrier used as array element",
        local(),
        [](Module &m) {
            m.classFields["Carrier"][0].elementType = Type("Carrier");
        },
        "cannot be nested");
    reject(
        "owner array elements",
        local(),
        [](Module &m) {
            m.classFields["Carrier"][0].elementType = Type::OwnedBytes;
        },
        "noncanonical");
    reject(
        "capability array elements",
        local(),
        [](Module &m) {
            m.classFields["Carrier"][0].elementType = Type::ByteSpan;
        },
        "noncanonical");
}
} // namespace

int main() {
    try {
        run();
        std::cout << "PASS class arrays IR: " << accepted << " accepted, " << rejected << " rejected\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL class arrays IR: " << error.what() << '\n';
        return 1;
    }
}
