// Independent IR producer for handwritten native borrowed-object ABI observations.
#include "ir_verify.hpp"
#include "x86.hpp"
#include <iostream>
using namespace aurora;
using namespace aurora::ir;
using F = aurora::ir::Function;
namespace {
void add(F &f, std::initializer_list<Instruction> x) {
    f.code.insert(f.code.end(), x);
}
int slot(F &f, int &cursor, Type type) {
    cursor += type.isSpan() ? 56 : 8;
    if (type.isSpan())
        f.spanSlots.insert(cursor);
    else if (type.isClass()) {
        f.objectSlots[cursor] = {"Box", false};
        f.slots[cursor] = Type::I64;
    } else
        f.slots[cursor] = type;
    f.frameBytes = (cursor + 15) & ~15;
    return cursor;
}
std::vector<Type> parameters(int arity, int mask) {
    std::vector<Type> out;
    for (int i = 0; i < arity; ++i)
        out.push_back(mask < 0 ? Type::I64 : mask & (1 << i) ? Type::ByteSpan : i % 3 == 0 ? Type("Box") : i % 3 == 1 ? Type::U8 : Type::I64);
    return out;
}
std::vector<int> bind(F &f, int &cursor) {
    std::vector<int> out;
    for (std::size_t i = 0; i < f.parameters.size(); ++i) {
        auto type = f.parameters[i];
        int base = slot(f, cursor, type);
        out.push_back(base);
        if (type.isSpan())
            f.code.push_back(BindSpanParameter{static_cast<int>(i), base});
        else if (type.isClass())
            f.code.push_back(BindObjectParameter{static_cast<int>(i), base, "Box"});
        else
            f.code.push_back(BindParameter{static_cast<int>(i), base, type});
    }
    return out;
}
void close(F &f, const std::vector<int> &slots) {
    for (std::size_t i = f.parameters.size(); i > 0; --i) {
        if (f.parameters[i - 1].isSpan())
            f.code.push_back(EndSpan{slots[i - 1]});
        else if (f.parameters[i - 1].isClass())
            f.code.push_back(EndObject{slots[i - 1]});
    }
}
} // namespace
int main() {
    try {
        Module m;
        m.classLayouts = {{"Receiver", {Type::I64, Type::I64}}, {"Box", {Type::I64}}};
        m.classFields["Receiver"] = {
            {Type::I64, 0, 1, false}, {Type::OwnedBytes, 1, 0, false}, {Type::I64, 1, 1, false}};
        m.classFields["Box"] = {{Type::I64, 0, 1, false}};
        m.classStorage = {{"Receiver", {{0, 40}, {0, 8, 40}, 48, 8, 48}}, {"Box", {{0}, {0}, 8, 8, 8}}};
        F observer;
        observer.name = "borrow_object_observe";
        observer.result = Type::I64;
        observer.parameters = {Type::ByteSpan};
        observer.frameBytes = 64;
        observer.spanSlots = {56};
        observer.code = {BindSpanParameter{0, 56}, Constant{42, Type::I64}, EndSpan{56}, Return{}};
        m.functions.push_back(observer);
        std::vector<std::pair<int, int>> shapes;
        for (int n = 1; n <= 5; ++n)
            for (int p = 0; p < n; ++p)
                shapes.emplace_back(n, 1 << p);
        for (auto pair : {std::pair{5, 31}, std::pair{5, 21}, std::pair{5, 10}})
            shapes.push_back(pair);
        for (int n = 0; n <= 5; ++n)
            shapes.emplace_back(n, -1);
        for (auto [n, mask] : shapes)
            for (int mode = 0; mode < 2; ++mode) {
                std::string suffix = std::to_string(n) + "_" + std::to_string(mask) + "_" + std::to_string(mode);
                F target;
                target.name = "borrow_object_target_" + suffix;
                target.receiver = Receiver{"Receiver", mode == 1, false};
                target.borrowedParameter = true;
                target.parameters = parameters(n, mask);
                target.result = mode == 0 ? Type::I64 : mode == 1 ? Type("Box") : Type::ByteSpan;
                if (mode == 2)
                    target.receiverSpanField = 1;
                int cursor = 0;
                auto bound = bind(target, cursor);
                close(target, bound);
                if (mode == 0)
                    add(target, {Constant{42, Type::I64}, Return{}});
                else if (mode == 1) {
                    int result = slot(target, cursor, Type("Box"));
                    add(target,
                        {BeginObject{result},
                         Constant{123, Type::I64},
                         Store{result, Type::I64},
                         ReturnObject{result}});
                } else {
                    int result = slot(target, cursor, Type::ByteSpan);
                    add(target, {BorrowOwnedSpan{0, 1, result}, ReturnSpan{result}});
                }
                m.functions.push_back(target);
                for (int depth = 0; depth <= 2; ++depth)
                    for (int transform = 0; transform <= 1; ++transform) {
                        F f;
                        f.name = "borrow_object_forward_" + suffix + "_" + std::to_string(depth) + "_" +
                                 std::to_string(transform);
                        f.receiver = Receiver{"Receiver", mode == 1, false};
                        f.borrowedParameter = true;
                        f.parameters = target.parameters;
                        f.result = Type::I64;
                        cursor = 0;
                        bound = bind(f, cursor);
                        std::vector<int> objects(n, 0), spans(n, 0), children;
                        add(f, {AcquireObjectLoan{1, 0, mode == 1}});
                        for (int i = 0; i < depth; ++i)
                            add(f, {Constant{4294967313LL + i, Type::I64}, Push{}});
                        for (int i = 0; i < n; ++i) {
                            if (f.parameters[i].isSpan()) {
                                spans[i] = bound[i];
                                if (transform) {
                                    int copy = slot(f, cursor, Type::ByteSpan), child = slot(f, cursor, Type::ByteSpan);
                                    add(f,
                                        {ReborrowSpan{bound[i], copy},
                                         Constant{2, Type::I64},
                                         Push{},
                                         Constant{0, Type::I64},
                                         Subspan{copy, child}});
                                    spans[i] = child;
                                    children.push_back(copy);
                                    children.push_back(child);
                                }
                            } else if (f.parameters[i].isClass())
                                objects[i] = bound[i];
                        }
                        int result = mode ? slot(f, cursor, target.result) : 0;
                        if (mode == 1)
                            f.code.push_back(BeginObject{result});
                        for (int i = 0; i < n; ++i)
                            if (!f.parameters[i].isSpan() && !f.parameters[i].isClass())
                                add(f, {Load{bound[i], f.parameters[i]}, Push{}});
                        f.code.push_back(BorrowedCall{target.name, 0, 1, mask < 0 ? std::vector<int>{} : objects,
                                                       result, mask < 0 ? std::vector<int>{} : spans});
                        f.code.push_back(ReleaseObjectLoan{1});
                        if (mode == 1)
                            add(f, {Load{result, Type::I64}, EndObject{result}});
                        if (mode == 2)
                            add(f, {AggregateCall{"borrow_object_observe", {0}, 0, {result}}, EndSpan{result}});
                        for (int i = 0; i < depth; ++i)
                            f.code.push_back(BinaryValue{Binary::CheckedAdd});
                        for (auto i = children.rbegin(); i != children.rend(); ++i)
                            f.code.push_back(EndSpan{*i});
                        close(f, bound);
                        f.code.push_back(Return{});
                        m.functions.push_back(f);
                    }
            }
        std::cout << X86Emitter{}.emit(validate(std::move(m)));
        return 0;
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
