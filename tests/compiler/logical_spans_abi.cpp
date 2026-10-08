// Independent typed-IR inputs for logical_spans_abi.py. No parser, production
// record-size constant or production layout calculator supplies the oracle.
#include "ir_verify.hpp"
#include "x86.hpp"
#include <iostream>

using namespace aurora;
using namespace aurora::ir;
using F = aurora::ir::Function;
namespace {
void append(F &f, std::initializer_list<Instruction> code) {
    f.code.insert(f.code.end(), code);
}
int reserve(F &f, int &cursor, const Type &type) {
    cursor += type == Type::ByteSpan ? 56 : 8;
    if (type == Type::ByteSpan)
        f.spanSlots.insert(cursor);
    else if (type.isClass()) {
        f.objectSlots[cursor] = {"Box", false};
        f.slots[cursor] = Type::I64;
    } else
        f.slots[cursor] = type;
    f.frameBytes = (cursor + 15) & ~15;
    return cursor;
}
Type scalar(int position) {
    return position % 3 == 0 ? Type::I64 : position % 3 == 1 ? Type::U8 : Type::Bool;
}
void save(F &f, int depth) {
    for (int i = 0; i < depth; ++i)
        append(f, {Constant{4294967313LL + i, Type::I64}, Push{}});
}
void combine(F &f, int depth) {
    for (int i = 0; i < depth; ++i)
        f.code.push_back(BinaryValue{Binary::CheckedAdd});
}
std::vector<std::pair<int, int>> shapes() {
    std::vector<std::pair<int, int>> result;
    for (int arity = 1; arity <= 6; ++arity)
        for (int position = 0; position < arity; ++position)
            result.emplace_back(arity, 1 << position);
    for (auto shape : {std::pair{2, 3}, {3, 5}, {4, 10}, {6, 63}, {6, 21}})
        result.push_back(shape);
    return result;
}
F probe(const std::string &name, const std::vector<Type> &parameters) {
    F f;
    f.name = name;
    f.result = Type::I64;
    f.parameters = parameters;
    int cursor = 0;
    std::vector<int> spans;
    for (std::size_t i = 0; i < parameters.size(); ++i) {
        const int slot = reserve(f, cursor, parameters[i]);
        if (parameters[i].isSpan()) {
            f.code.push_back(BindSpanParameter{static_cast<int>(i), slot});
            spans.push_back(slot);
        } else
            f.code.push_back(BindParameter{static_cast<int>(i), slot, parameters[i]});
    }
    f.code.push_back(Constant{42, Type::I64});
    for (int slot : spans)
        f.code.push_back(EndSpan{slot});
    f.code.push_back(Return{});
    return f;
}
void forwarding(Module &m) {
    for (auto [arity, mask] : shapes()) {
        std::vector<Type> parameters;
        for (int i = 0; i < arity; ++i)
            parameters.push_back(mask & (1 << i) ? Type::ByteSpan : scalar(i));
        const std::string suffix = std::to_string(arity) + "_" + std::to_string(mask);
        const std::string target = "abi_probe_" + suffix;
        m.functions.push_back(probe(target, parameters));
        for (int transform = 0; transform <= 2; ++transform) {
            for (int depth = 0; depth <= 2; ++depth) {
                F f;
                f.name = "abi_forward_" + suffix + "_" + std::to_string(transform) + "_" + std::to_string(depth);
                f.result = Type::I64;
                f.parameters = parameters;
                int cursor = 0;
                std::vector<int> slots, spans(arity, 0), lifetimes;
                for (int i = 0; i < arity; ++i) {
                    const int slot = reserve(f, cursor, parameters[i]);
                    slots.push_back(slot);
                    if (parameters[i].isSpan()) {
                        f.code.push_back(BindSpanParameter{i, slot});
                        spans[i] = slot;
                        lifetimes.push_back(slot);
                    } else
                        f.code.push_back(BindParameter{i, slot, parameters[i]});
                }
                save(f, depth);
                for (int i = 0; i < arity; ++i) {
                    if (!parameters[i].isSpan())
                        continue;
                    if (transform >= 1) {
                        int copy = reserve(f, cursor, Type::ByteSpan);
                        f.code.push_back(ReborrowSpan{spans[i], copy});
                        spans[i] = copy;
                        lifetimes.push_back(copy);
                    }
                    if (transform == 2) {
                        for (auto [offset, count] : {std::pair{3, 7}, {2, 3}}) {
                            int child = reserve(f, cursor, Type::ByteSpan);
                            append(f,
                                   {Constant{offset, Type::I64},
                                    Push{},
                                    Constant{count, Type::I64},
                                    Subspan{spans[i], child}});
                            spans[i] = child;
                            lifetimes.push_back(child);
                        }
                    }
                }
                for (int i = 0; i < arity; ++i)
                    if (!parameters[i].isSpan())
                        append(f, {Load{slots[i], parameters[i]}, Push{}});
                f.code.push_back(AggregateCall{target, std::vector<int>(arity, 0), 0, spans});
                combine(f, depth);
                for (auto i = lifetimes.rbegin(); i != lifetimes.rend(); ++i)
                    f.code.push_back(EndSpan{*i});
                f.code.push_back(Return{});
                m.functions.push_back(f);
            }
        }
    }
    m.functions.push_back(probe("abi_probe_one", {Type::ByteSpan}));
    for (int depth = 0; depth <= 3; ++depth) {
        F f;
        f.name = "abi_read_" + std::to_string(depth);
        f.result = Type::I64;
        f.parameters = {Type::ByteSpan};
        f.frameBytes = 64;
        f.spanSlots = {56};
        f.code = {BindSpanParameter{0, 56}};
        save(f, depth);
        append(f, {Constant{4, Type::I64}, SpanLoad{56}, Convert{Type::U8, Type::I64}});
        combine(f, depth);
        append(f, {EndSpan{56}, Return{}});
        m.functions.push_back(f);
    }
    for (int depth = 0; depth <= 2; ++depth) {
        F f;
        f.name = "abi_array_mint_" + std::to_string(depth);
        f.result = Type::I64;
        f.frameBytes = 208;
        f.arraySlots = {{32, 32}};
        f.spanSlots = {88, 144, 200};
        f.code = {BeginArray{32}};
        for (int i = 0; i < 32; ++i) {
            f.slots[32 - i] = Type::U8;
            append(f, {Constant{(11 + i * 7) % 256, Type::U8}, Store{32 - i, Type::U8}});
        }
        save(f, depth);
        append(f,
               {BorrowSpan{32, 88},
                ReborrowSpan{88, 144},
                Constant{3, Type::I64},
                Push{},
                Constant{7, Type::I64},
                Subspan{144, 200},
                AggregateCall{"abi_probe_one", {0}, 0, {200}}});
        combine(f, depth);
        append(f, {EndSpan{200}, EndSpan{144}, EndSpan{88}, EndArray{32}, Return{}});
        m.functions.push_back(f);
    }
}
std::vector<Type> resultParameters(int mode) {
    if (mode == 0)
        return {};
    if (mode == 1)
        return {Type::I64};
    if (mode == 2)
        return {Type::I64, Type::I64, Type::I64, Type::I64, Type::I64, Type::I64};
    return {Type("Box"), Type::I64, Type("Box"), Type::U8, Type::I64, Type::Bool};
}
F resultMethod(int mode) {
    F f;
    f.name = "abi_result_" + std::to_string(mode);
    f.receiver = Receiver{"Receiver", false, false};
    f.receiverSpanField = 1;
    f.result = Type::ByteSpan;
    f.parameters = resultParameters(mode);
    int cursor = 0;
    std::vector<int> parameters;
    for (std::size_t i = 0; i < f.parameters.size(); ++i) {
        const int slot = reserve(f, cursor, f.parameters[i]);
        parameters.push_back(slot);
        if (f.parameters[i].isClass())
            f.code.push_back(BindObjectParameter{static_cast<int>(i), slot, "Box"});
        else
            f.code.push_back(BindParameter{static_cast<int>(i), slot, f.parameters[i]});
    }
    const int root = reserve(f, cursor, Type::ByteSpan);
    const int copy = reserve(f, cursor, Type::ByteSpan);
    const int window = reserve(f, cursor, Type::ByteSpan);
    append(f, {BorrowOwnedSpan{0, 1, root}, ReborrowSpan{root, copy}});
    if (mode == 0)
        f.code.push_back(Constant{3, Type::I64});
    else
        f.code.push_back(Load{parameters[mode == 3 ? 4 : mode == 2 ? 5 : 0], Type::I64});
    f.code.push_back(Push{});
    if (mode == 3)
        f.code.push_back(Load{parameters[0], Type::I64});
    else
        f.code.push_back(Constant{7, Type::I64});
    f.code.push_back(Subspan{copy, window});
    for (std::size_t i = 0; i < f.parameters.size(); ++i)
        if (f.parameters[i].isClass())
            f.code.push_back(EndObject{parameters[i]});
    f.code.push_back(ReturnSpan{window});
    return f;
}
void owned(Module &m) {
    m.classLayouts = {{"Receiver", {Type::I64, Type::I64}}, {"Box", {Type::I64}}};
    m.classFields["Receiver"] = {{Type::I64, 0, 1, false}, {Type::OwnedBytes, 1, 0, false}, {Type::I64, 1, 1, false}};
    m.classFields["Box"] = {{Type::I64, 0, 1, false}};
    m.classStorage = {{"Receiver", {{0, 40}, {0, 8, 40}, 48, 8, 48}}, {"Box", {{0}, {0}, 8, 8, 8}}};
    for (int mode = 0; mode <= 3; ++mode) {
        m.functions.push_back(resultMethod(mode));
        for (int depth = 0; depth <= 2; ++depth) {
            F f;
            f.name = "abi_use_result_" + std::to_string(mode) + "_" + std::to_string(depth);
            f.receiver = Receiver{"Receiver", false, false};
            f.result = Type::I64;
            int cursor = 0;
            std::vector<int> objects;
            const auto parameters = resultParameters(mode);
            for (std::size_t i = 0; i < parameters.size(); ++i) {
                if (parameters[i].isClass()) {
                    const int slot = reserve(f, cursor, Type("Box"));
                    append(f, {BeginObject{slot}, Constant{i == 0 ? 7 : 19, Type::I64}, Store{slot, Type::I64}});
                    objects.push_back(slot);
                } else
                    objects.push_back(0);
            }
            const int result = reserve(f, cursor, Type::ByteSpan);
            save(f, depth);
            for (std::size_t i = 0; i < parameters.size(); ++i)
                if (!parameters[i].isClass()) {
                    const int value = mode == 1 || (mode == 2 && i == 5) || (mode == 3 && i == 4) ? 3
                                      : parameters[i] == Type::Bool ? 1
                                                                    : 71 + static_cast<int>(i);
                    append(f, {Constant{value, parameters[i]}, Push{}});
                }
            f.code.push_back(
                MethodCall{"abi_result_" + std::to_string(mode), 0, mode == 3 ? objects : std::vector<int>{}, result});
            f.code.push_back(AggregateCall{"abi_probe_one", {0}, 0, {result}});
            combine(f, depth);
            f.code.push_back(EndSpan{result});
            for (int slot : objects)
                if (slot)
                    f.code.push_back(EndObject{slot});
            f.code.push_back(Return{});
            m.functions.push_back(f);
        }
    }
    for (int depth = 0; depth <= 3; ++depth) {
        F f;
        f.name = "abi_borrow_" + std::to_string(depth);
        f.result = Type::I64;
        f.receiver = Receiver{"Receiver", false, false};
        f.frameBytes = 192;
        f.spanSlots = {56, 112, 168};
        f.slots = {{176, Type::I64}};
        save(f, depth);
        append(f,
               {Constant{123456789, Type::I64},
                BorrowOwnedSpan{0, 1, 56},
                Store{176, Type::I64},
                ReborrowSpan{56, 112},
                Constant{3, Type::I64},
                Push{},
                Constant{7, Type::I64},
                Subspan{112, 168},
                AggregateCall{"abi_probe_one", {0}, 0, {168}},
                Load{176, Type::I64}});
        combine(f, depth);
        append(f, {EndSpan{168}, EndSpan{112}, EndSpan{56}, Return{}});
        m.functions.push_back(f);
    }
}
} // namespace
int main(int argc, char **argv) {
    try {
        if (argc != 2 || (std::string(argv[1]) != "--emit-array" && std::string(argv[1]) != "--emit-owner"))
            throw Error("usage: logical-spans-abi --emit-array|--emit-owner");
        Module m;
        forwarding(m);
        if (std::string(argv[1]) == "--emit-owner")
            owned(m);
        std::cout << X86Emitter{}.emit(validate(std::move(m)));
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
