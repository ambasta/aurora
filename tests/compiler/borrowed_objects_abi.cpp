// Independent IR producer for handwritten native borrowed-object ABI observations.
#include "ir_verify.hpp"
#include "x86.hpp"
#include <algorithm>
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
        out.push_back(mask < 0          ? Type::I64
                      : mask & (1 << i) ? Type::ByteSpan
                      : i % 3 == 0      ? Type("Box")
                      : i % 3 == 1      ? Type::U8
                                        : Type::I64);
    return out;
}
std::vector<int> bind(F &f, int &cursor) {
    std::vector<int> out;
    for (std::size_t i = 0; i < f.parameters.size() - f.borrowedRootCount; ++i) {
        auto type = f.parameters[f.borrowedRootCount + i];
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
    for (std::size_t i = f.parameters.size() - f.borrowedRootCount; i > 0; --i) {
        if (f.parameters[f.borrowedRootCount + i - 1].isSpan())
            f.code.push_back(EndSpan{slots[i - 1]});
        else if (f.parameters[f.borrowedRootCount + i - 1].isClass())
            f.code.push_back(EndObject{slots[i - 1]});
    }
}
void pairedBoundaries(Module &module) {
    F first;
    first.name = "paired_read_first";
    first.receiver = Receiver{"Receiver", true, false};
    first.result = Type::I64;
    first.code = {ReceiverLoad{0, Type::I64}, Return{}};
    module.functions.push_back(first);
    auto second = first;
    second.name = "paired_read_second";
    second.receiver->mutableValue = false;
    second.code = {ReceiverLoad{2, Type::I64}, Return{}};
    module.functions.push_back(second);
    auto copied = second;
    copied.name = "paired_copy_second";
    copied.result = Type("Box");
    copied.frameBytes = 16;
    copied.slots = {{8, Type::I64}};
    copied.objectSlots = {{8, {"Box", false}}};
    copied.code = {BeginObject{8}, ReceiverLoad{2, Type::I64}, Store{8, Type::I64}, ReturnObject{8}};
    module.functions.push_back(copied);
    auto shared = second;
    shared.name = "paired_single_second";
    shared.receiver.reset();
    shared.parameters = {Type("Receiver")};
    shared.borrowedRootCount = 1;
    shared.code = {MethodCall{"paired_read_second", 0}, Return{}};
    module.functions.push_back(shared);
    F clobber;
    clobber.name = "paired_scalar_clobber";
    clobber.result = Type::I64;
    clobber.code = {Constant{0, Type::I64}, Return{}};
    module.functions.push_back(clobber);
    for (int arity = 0; arity <= 4; ++arity) {
        F target;
        target.name = "paired_target_" + std::to_string(arity);
        target.borrowedRootCount = 2;
        target.mutableBorrowedRootCount = 1;
        target.parameters = {Type("Receiver"), Type("Receiver")};
        target.parameters.insert(target.parameters.end(), arity, Type::I64);
        target.result = Type::I64;
        int cursor = 0;
        const auto bound = bind(target, cursor);
        const int total = slot(target, cursor, Type::I64);
        const int result = slot(target, cursor, Type("Box"));
        add(target,
            {MethodCall{"paired_read_first", 0},
             Store{total, Type::I64},
             Call{"paired_scalar_clobber"},
             BeginObject{result},
             MethodCall{"paired_copy_second", -1, {}, result},
             Load{total, Type::I64},
             Push{},
             Load{result, Type::I64},
             BinaryValue{Binary::CheckedAdd},
             Store{total, Type::I64},
             EndObject{result},
             AcquireObjectLoan{7, -1, false},
             BorrowedCall{"paired_single_second", {{-1, 7}}},
             ReleaseObjectLoan{7},
             Push{},
             Load{total, Type::I64},
             BinaryValue{Binary::CheckedAdd},
             Store{total, Type::I64}});
        for (int base : bound)
            add(target,
                {Load{total, Type::I64},
                 Push{},
                 Load{base, Type::I64},
                 BinaryValue{Binary::CheckedAdd},
                 Store{total, Type::I64}});
        add(target, {Load{total, Type::I64}, Return{}});
        module.functions.push_back(target);
        for (int depth = 0; depth <= 2; ++depth) {
            F forward;
            forward.name = "paired_forward_" + std::to_string(arity) + "_" + std::to_string(depth);
            forward.borrowedRootCount = target.borrowedRootCount;
            forward.mutableBorrowedRootCount = target.mutableBorrowedRootCount;
            forward.parameters = target.parameters;
            forward.result = Type::I64;
            cursor = 0;
            const auto forwarded = bind(forward, cursor);
            const int saved = slot(forward, cursor, Type::I64);
            const int copiedResult = slot(forward, cursor, Type("Box"));
            add(forward, {AcquireObjectLoan{1, 0, true}, AcquireObjectLoan{2, -1, false}});
            for (int operand = 0; operand < depth; ++operand)
                add(forward, {Constant{4294967313LL + operand, Type::I64}, Push{}});
            for (int base : forwarded)
                add(forward, {Load{base, Type::I64}, Push{}});
            add(forward,
                {BorrowedCall{target.name, {{0, 1}, {-1, 2}}, {}, 0, {}},
                 ReleaseObjectLoan{2},
                 ReleaseObjectLoan{1},
                 Store{saved, Type::I64},
                 Call{"paired_scalar_clobber"},
                 BeginObject{copiedResult},
                 MethodCall{"paired_copy_second", -1, {}, copiedResult},
                 Load{saved, Type::I64},
                 Push{},
                 Load{copiedResult, Type::I64},
                 BinaryValue{Binary::CheckedAdd},
                 EndObject{copiedResult}});
            for (int operand = 0; operand < depth; ++operand)
                forward.code.push_back(BinaryValue{Binary::CheckedAdd});
            forward.code.push_back(Return{});
            module.functions.push_back(forward);
        }
    }
}
void boundedBoundaries(Module &module) {
    // Literal writes independently observed by the handwritten oracle. These
    // are class scalar fields, not manufactured owner descriptors.
    for (int ordinal = 0; ordinal < 2; ++ordinal) {
        F write;
        write.name = "dual_write_" + std::to_string(ordinal);
        write.receiver = Receiver{"Receiver", true, false};
        write.result = Type::I64;
        write.code = {
            Constant{501 + ordinal, Type::I64}, ReceiverStore{2, Type::I64}, ReceiverLoad{2, Type::I64}, Return{}};
        module.functions.push_back(write);
    }
    for (int roots = 1; roots <= 3; ++roots)
        for (int mutableFirst = 0; mutableFirst <= std::min(roots, 2); ++mutableFirst)
            for (int tail = 0; tail <= 6 - roots; ++tail) {
                const auto suffix =
                    std::to_string(roots) + "_" + std::to_string(mutableFirst) + "_" + std::to_string(tail);
                F target;
                target.name = "bounded_target_" + suffix;
                target.borrowedRootCount = roots;
                target.mutableBorrowedRootCount = mutableFirst;
                target.parameters.assign(roots, Type("Receiver"));
                target.parameters.insert(target.parameters.end(), tail, Type::I64);
                target.result = Type::I64;
                int cursor = 0;
                const auto inputs = bind(target, cursor);
                const int total = slot(target, cursor, Type::I64);
                add(target, {Constant{0, Type::I64}, Store{total, Type::I64}});
                for (int ordinal = 0; ordinal < roots; ++ordinal) {
                    if (mutableFirst == 2 && ordinal < 2)
                        target.code.push_back(MethodCall{"dual_write_" + std::to_string(ordinal), -ordinal});
                    add(target,
                        {Call{"paired_scalar_clobber"},
                         MethodCall{"paired_read_second", -ordinal},
                         Push{},
                         Load{total, Type::I64},
                         BinaryValue{Binary::CheckedAdd},
                         Store{total, Type::I64}});
                }
                for (int input : inputs)
                    add(target,
                        {Load{input, Type::I64},
                         Push{},
                         Load{total, Type::I64},
                         BinaryValue{Binary::CheckedAdd},
                         Store{total, Type::I64}});
                add(target, {Load{total, Type::I64}, Return{}});
                module.functions.push_back(target);
                for (int depth = 0; depth <= 2; ++depth) {
                    F forward;
                    forward.name = "bounded_forward_" + suffix + "_" + std::to_string(depth);
                    forward.borrowedRootCount = roots;
                    forward.mutableBorrowedRootCount = mutableFirst;
                    forward.parameters = target.parameters;
                    forward.result = Type::I64;
                    cursor = 0;
                    const auto arguments = bind(forward, cursor);
                    const int saved = slot(forward, cursor, Type::I64);
                    const int copied = slot(forward, cursor, Type("Box"));
                    std::vector<BorrowedRootArgument> lanes;
                    for (int ordinal = 0; ordinal < roots; ++ordinal) {
                        forward.code.push_back(AcquireObjectLoan{ordinal + 1, -ordinal, ordinal < mutableFirst});
                        lanes.push_back({-ordinal, ordinal + 1});
                    }
                    for (int index = 0; index < depth; ++index)
                        add(forward, {Constant{4294967313LL + index, Type::I64}, Push{}});
                    for (int argument : arguments)
                        add(forward, {Load{argument, Type::I64}, Push{}});
                    forward.code.push_back(BorrowedCall{target.name, lanes});
                    for (int ordinal = roots; ordinal > 0; --ordinal)
                        forward.code.push_back(ReleaseObjectLoan{ordinal});
                    add(forward,
                        {Store{saved, Type::I64},
                         Call{"paired_scalar_clobber"},
                         BeginObject{copied},
                         MethodCall{"paired_copy_second", 1 - roots, {}, copied},
                         Load{saved, Type::I64},
                         Push{},
                         Load{copied, Type::I64},
                         BinaryValue{Binary::CheckedAdd},
                         EndObject{copied}});
                    for (int index = 0; index < depth; ++index)
                        forward.code.push_back(BinaryValue{Binary::CheckedAdd});
                    forward.code.push_back(Return{});
                    module.functions.push_back(forward);
                }
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
                std::string suffix =
                    std::to_string(n) + "_" + (mask < 0 ? "scalar" : std::to_string(mask)) + "_" + std::to_string(mode);
                F target;
                target.name = "borrow_object_target_" + suffix;
                target.borrowedRootCount = 1;
                target.mutableBorrowedRootCount = mode == 1;
                target.parameters = parameters(n, mask);
                target.parameters.insert(target.parameters.begin(), Type("Receiver"));
                target.result = mode == 0 ? Type::I64 : Type("Box");
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
                }
                m.functions.push_back(target);
                for (int depth = 0; depth <= 2; ++depth)
                    for (int transform = 0; transform <= 1; ++transform) {
                        F f;
                        f.name = "borrow_object_forward_" + suffix + "_" + std::to_string(depth) + "_" +
                                 std::to_string(transform);
                        f.borrowedRootCount = 1;
                        f.mutableBorrowedRootCount = mode == 1;
                        f.parameters = target.parameters;
                        f.result = Type::I64;
                        cursor = 0;
                        bound = bind(f, cursor);
                        std::vector<int> objects(n, 0), spans(n, 0), children;
                        add(f, {AcquireObjectLoan{1, 0, mode == 1}});
                        for (int i = 0; i < depth; ++i)
                            add(f, {Constant{4294967313LL + i, Type::I64}, Push{}});
                        for (int i = 0; i < n; ++i) {
                            if (f.parameters[f.borrowedRootCount + i].isSpan()) {
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
                            } else if (f.parameters[f.borrowedRootCount + i].isClass())
                                objects[i] = bound[i];
                        }
                        int result = mode ? slot(f, cursor, target.result) : 0;
                        if (mode == 1)
                            f.code.push_back(BeginObject{result});
                        for (int i = 0; i < n; ++i)
                            if (!f.parameters[f.borrowedRootCount + i].isSpan() &&
                                !f.parameters[f.borrowedRootCount + i].isClass())
                                add(f, {Load{bound[i], f.parameters[f.borrowedRootCount + i]}, Push{}});
                        f.code.push_back(BorrowedCall{target.name,
                                                      {{0, 1}},
                                                      mask < 0 ? std::vector<int>{} : objects,
                                                      result,
                                                      mask < 0 ? std::vector<int>{} : spans});
                        f.code.push_back(ReleaseObjectLoan{1});
                        if (mode == 1)
                            add(f, {Load{result, Type::I64}, EndObject{result}});
                        for (int i = 0; i < depth; ++i)
                            f.code.push_back(BinaryValue{Binary::CheckedAdd});
                        for (auto i = children.rbegin(); i != children.rend(); ++i)
                            f.code.push_back(EndSpan{*i});
                        close(f, bound);
                        f.code.push_back(Return{});
                        m.functions.push_back(f);
                    }
            }
        pairedBoundaries(m);
        boundedBoundaries(m);
        std::cout << X86Emitter{}.emit(validate(std::move(m)));
        return 0;
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
