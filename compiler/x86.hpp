#pragma once
#include "ir_layout.hpp"
#include <algorithm>
#include <sstream>
#include <type_traits>

namespace aurora {
// This backend accepts validated typed IR only. It has no AST, scope, borrow or move state.
class X86Emitter {
    std::ostringstream output;
    int stackDepth = 0;
    int functionIndex = 0;
    int divisionIndex = 0;
    int receiverSaveOffset = 0;
    int callRecordSaveOffset = 0;
    int resultSaveOffset = 0;
    const ir::Function *currentFunction = nullptr;
    const std::map<std::string, std::vector<Type>> *classLayouts = nullptr;
    const std::map<std::string, std::vector<ir::ClassField>> *classFields = nullptr;
    const std::map<std::string, ir::ClassStorage> *classStorage = nullptr;
    std::map<std::string, const ir::Function *> functions;
    std::map<std::string, std::size_t> argumentCounts;
    const std::vector<std::string> argumentRegisters = {"%rdi", "%rsi", "%rdx",
                                                        "%rcx", "%r8",  "%r9"};
    const std::vector<std::string> byteArgumentRegisters = {"%dil", "%sil", "%dl",
                                                            "%cl",  "%r8b", "%r9b"};
    void line(const std::string &text) { output << "    " << text << '\n'; }
    void loadValue(const Type &type, const std::string &source) {
        line(std::string(type == Type::U8 ? "movzbq " : "movq ") + source + ", %rax");
    }
    void storeValue(const Type &type, const std::string &destination) {
        line(std::string(type == Type::U8 ? "movb %al, " : "movq %rax, ") + destination);
    }
    void storeArgument(const Type &type, std::size_t index, const std::string &destination) {
        line(std::string(type == Type::U8 ? "movb " : "movq ") +
             (type == Type::U8 ? byteArgumentRegisters[index] : argumentRegisters[index]) + ", " +
             destination);
    }
    int objectLeaf(int base, std::size_t leaf) const {
        return base - classStorage->at(currentFunction->objectSlots.at(base).className)
                          .leafOffsets.at(leaf);
    }
    template <class Address> void clearBytes(int begin, int end, const Address &destination) {
        while (begin < end) {
            const int remaining = end - begin;
            const int width = remaining >= 8 ? 8 : remaining >= 4 ? 4 : remaining >= 2 ? 2 : 1;
            const char suffix = width == 8 ? 'q' : width == 4 ? 'l' : width == 2 ? 'w' : 'b';
            line(std::string("mov") + suffix + " $0, " + destination(begin));
            begin += width;
        }
    }
    template <class Address>
    void clearPadding(const std::string &name, const Address &destination) {
        const auto &physical = classStorage->at(name);
        const auto &leaves = classLayouts->at(name);
        int cursor = 0;
        for (std::size_t leaf = 0; leaf < leaves.size(); ++leaf) {
            clearBytes(cursor, physical.leafOffsets[leaf], destination);
            cursor = physical.leafOffsets[leaf] + ir::storageWidth(leaves[leaf]);
        }
        clearBytes(cursor, physical.reservedBytes, destination);
    }
    void clearObject(int base, const std::string &name) {
        clearPadding(name, [&](int byte) { return address(base - byte); });
    }
    std::string address(int offset) { return "-" + std::to_string(offset) + "(%rbp)"; }
    std::string label(int id) {
        return ".Lau" + std::to_string(functionIndex) + "_" + std::to_string(id);
    }
    std::string returnLabel() { return ".Lreturn" + std::to_string(functionIndex); }
    void reserveStack(int bytes) {
        // Verified frames and call records are nonnegative multiples of 16.
        // Touch every new page and the final remainder before another downward
        // adjustment. The qword is wholly inside this new reservation, at RSP,
        // never in a red zone. No argument or hidden-capability GPR is clobbered.
        // Flags are dead at both callers, as with their previous SUB instruction.
        if (bytes == 0) {
            line("subq $0, %rsp");
            return;
        }
        while (bytes > 0) {
            const int step = std::min(bytes, 4096);
            line("subq $" + std::to_string(step) + ", %rsp");
            line("orq $0, (%rsp)");
            bytes -= step;
        }
    }
    void push() {
        line("pushq %rax");
        ++stackDepth;
    }
    void pop(const std::string &target) {
        line("popq " + target);
        --stackDepth;
    }
    void call(const std::string &name) {
        if (stackDepth % 2)
            line("subq $8, %rsp");
        line("call " + name);
        if (stackDepth % 2)
            line("addq $8, %rsp");
    }
    std::string querySymbol(ir::Query query, int scope) {
        const std::string name = query == ir::Query::Size ? "size" : "field_count";
        return scope == 0 ? "aurora_reflect_" + name
                          : "__au_reflect_s" + std::to_string(scope) + "_" + name;
    }
    bool aggregateSignature(const ir::Function &function) const {
        if (function.result.isClass() || function.result.isBytes())
            return true;
        for (const auto &type : function.parameters)
            if (type.isClass() || type.isSpan() || type.isResource())
                return true;
        return false;
    }
    bool classParameters(const ir::Function &function) const {
        return std::any_of(function.parameters.begin(), function.parameters.end(),
                           [](const Type &type) { return type.isClass(); });
    }
    int argumentBytes(const Type &type) const {
        return type.isBytes()   ? 32
               : type.isClass() ? classStorage->at(type.className).reservedBytes
               : type.isSpan()  ? 16
                                : 8;
    }
    int recordOffset(const ir::Function &function, std::size_t parameter) const {
        int offset = 0;
        for (std::size_t index = 0; index < parameter; ++index)
            offset += argumentBytes(function.parameters[index]);
        return offset;
    }
    const ir::ClassField &receiverField(int fieldIndex) const {
        return classFields->at(currentFunction->receiver->className)[fieldIndex];
    }
    const ir::ClassStorage &receiverStorage() const {
        return classStorage->at(currentFunction->receiver->className);
    }
    int packArguments(const ir::Function &target, const std::vector<int> &objects,
                      const std::vector<int> &spans = {}) {
        for (std::size_t index = target.parameters.size(); index > 0; --index)
            if (!target.parameters[index - 1].isClass() && !target.parameters[index - 1].isSpan())
                pop(argumentRegisters[index - 1]);
        const int recordBytes = (recordOffset(target, target.parameters.size()) + 15) & ~15;
        if (recordBytes)
            reserveStack(recordBytes);
        // Clear only representation gaps. Verified payload copies initialize
        // their own bytes; old all-word objects need no redundant zero stores.
        for (std::size_t index = 0; index < target.parameters.size(); ++index) {
            const auto &type = target.parameters[index];
            const int offset = recordOffset(target, index);
            const auto destination = [&](int byte) {
                return std::to_string(offset + byte) + "(%rsp)";
            };
            if (type.isClass())
                clearPadding(type.className, destination);
            else if (!type.isSpan())
                clearBytes(ir::storageWidth(type), 8, destination);
        }
        clearBytes(recordOffset(target, target.parameters.size()), recordBytes,
                   [](int byte) { return std::to_string(byte) + "(%rsp)"; });
        for (std::size_t index = 0; index < target.parameters.size(); ++index) {
            const auto &type = target.parameters[index];
            const int offset = recordOffset(target, index);
            if (type.isSpan()) {
                line("movq " + address(spans[index]) + ", %rax");
                line("movq %rax, " + std::to_string(offset) + "(%rsp)");
                line("movq " + address(spans[index] - 8) + ", %rax");
                line("movq %rax, " + std::to_string(offset + 8) + "(%rsp)");
            } else if (!type.isClass())
                storeArgument(type, index, std::to_string(offset) + "(%rsp)");
            else {
                const auto &layout = classLayouts->at(type.className);
                for (std::size_t field = 0; field < layout.size(); ++field) {
                    loadValue(layout[field], address(objectLeaf(objects[index], field)));
                    storeValue(layout[field],
                               std::to_string(offset +
                                              classStorage->at(type.className).leafOffsets[field]) +
                                   "(%rsp)");
                }
            }
        }
        line("movq %rsp, %r11");
        return recordBytes;
    }
    void clearBytesOwner(int offset) {
        for (int byte = 0; byte < 32; byte += 8)
            line("movq $0, " + address(offset - byte));
    }
    void moveBytesOwner(int source, int destination) {
        for (int byte = 0; byte < 32; byte += 8) {
            line("movq " + address(source - byte) + ", %rcx");
            line("movq %rcx, " + address(destination - byte));
        }
        clearBytesOwner(source);
    }
    int packResources(const ir::Function &target, const ir::ResourceCall &operation) {
        for (std::size_t index = target.parameters.size(); index > 1; --index)
            if (!target.parameters[index - 1].isBytes())
                pop(argumentRegisters[index - 1]);
        const int recordBytes = (recordOffset(target, target.parameters.size()) + 15) & ~15;
        reserveStack(recordBytes);
        clearBytes(0, recordBytes, [](int byte) {
            return std::to_string(byte) + "(%rsp)";
        });
        // Save scalar arguments before descriptor copying reuses scratch GPRs.
        for (std::size_t index = 1; index < target.parameters.size(); ++index)
            if (!target.parameters[index].isBytes())
                storeArgument(target.parameters[index], index, std::to_string(recordOffset(target, index)) + "(%rsp)");
        line("movq " + address(operation.regionOffset) + ", %rax");
        line("movq %rax, (%rsp)");
        for (std::size_t index = 1; index < target.parameters.size(); ++index)
            if (target.parameters[index].isBytes()) {
                const int source = operation.ownerArguments[index];
                const int destination = recordOffset(target, index);
                for (int byte = 0; byte < 32; byte += 8) {
                    line("movq " + address(source - byte) + ", %rax");
                    line("movq %rax, " + std::to_string(destination + byte) + "(%rsp)");
                }
                clearBytesOwner(source);
            }
        line("movq %rsp, %r11");
        return recordBytes;
    }
    void checkedDivision(bool remainder, bool unsignedValue) {
        const auto suffix = std::to_string(functionIndex) + "_" + std::to_string(divisionIndex++);
        const auto ready = ".Ldivision_ready_" + suffix;
        const auto done = ".Ldivision_done_" + suffix;
        // Left operand is RCX, right operand RAX. Reject every IDIV fault
        // before issuing it; receiver/value-call capabilities are saved privately.
        line("movq %rax, %r11");
        line("testq %r11, %r11");
        line("jz .Laurora_division_zero_trap");
        line("movq %rcx, %rax");
        if (unsignedValue) {
            line("xorq %rdx, %rdx");
            line("divq %r11");
            if (remainder)
                line("movq %rdx, %rax");
            return;
        }
        line("cmpq $-1, %r11");
        line("jne " + ready);
        line("movabsq $-9223372036854775808, %rdx");
        line("cmpq %rdx, %rax");
        line("jne " + ready);
        if (remainder) {
            // The mathematical remainder is representable even when the quotient is not.
            line("xorq %rax, %rax");
            line("jmp " + done);
        } else {
            line("jmp .Laurora_overflow_trap");
        }
        output << ready << ":\n";
        line("cqto");
        line("idivq %r11");
        if (remainder)
            line("movq %rdx, %rax");
        output << done << ":\n";
    }
    void checkedShift(bool left, bool byteValue) {
        // Unsigned comparison rejects negative i64 counts too, before x86 can mask them.
        line(std::string("cmpq $") + (byteValue ? "7" : "63") + ", %rax");
        line("ja .Laurora_shift_count_trap");
        line("movq %rcx, %rdx");
        line("movq %rax, %rcx");
        line("movq %rdx, %rax");
        if (left) {
            line("shlq %cl, %rax");
            if (byteValue) {
                // At most seven shifts of a canonical byte fit in the wide
                // register; overflow is exactly a result outside 0..255.
                line("cmpq $255, %rax");
                line("ja .Laurora_overflow_trap");
            } else {
                // Shifting back detects every lost high bit, including counts > 1,
                // for which the processor's overflow flag has no defined meaning.
                line("movq %rax, %r11");
                line("shrq %cl, %r11");
                line("cmpq %rdx, %r11");
                line("jne .Laurora_overflow_trap");
            }
        } else
            line("shrq %cl, %rax");
    }
    void instruction(const ir::Instruction &instruction) {
        std::visit(
            [&](const auto &operation) {
                using Op = std::decay_t<decltype(operation)>;
                if constexpr (std::is_same_v<Op, ir::Constant>) {
                    line("movabsq $" + std::to_string(operation.value) + ", %rax");
                } else if constexpr (std::is_same_v<Op, ir::EnumConstant>) {
                    line("movq $" + std::to_string(operation.caseIndex) + ", %rax");
                } else if constexpr (std::is_same_v<Op, ir::Load>) {
                    loadValue(operation.type, address(operation.offset));
                } else if constexpr (std::is_same_v<Op, ir::Store>) {
                    storeValue(operation.type, address(operation.offset));
                } else if constexpr (std::is_same_v<Op, ir::Push>) {
                    push();
                } else if constexpr (std::is_same_v<Op, ir::Pop>) {
                    pop("%rax");
                } else if constexpr (std::is_same_v<Op, ir::UnaryValue>) {
                    switch (operation.operation) {
                    case ir::Unary::LogicalNot:
                        line("xorq $1, %rax");
                        break;
                    case ir::Unary::CheckedNegate:
                        line("negq %rax");
                        line("jo .Laurora_overflow_trap");
                        break;
                    case ir::Unary::BitNot:
                        line(operation.operandType == Type::U8 ? "xorq $255, %rax" : "notq %rax");
                        break;
                    }
                } else if constexpr (std::is_same_v<Op, ir::BinaryValue>) {
                    pop("%rcx");
                    const bool byteValue = operation.operandType == Type::U8;
                    const bool unsignedValue = operation.operandType == Type::U64 || byteValue;
                    const std::string overflowJump = unsignedValue ? "jc" : "jo";
                    switch (operation.operation) {
                    case ir::Binary::CheckedAdd:
                        line("addq %rcx, %rax");
                        line(overflowJump + " .Laurora_overflow_trap");
                        if (byteValue) {
                            line("cmpq $255, %rax");
                            line("ja .Laurora_overflow_trap");
                        }
                        break;
                    case ir::Binary::CheckedSubtract:
                        line("subq %rax, %rcx");
                        line("movq %rcx, %rax");
                        line(overflowJump + " .Laurora_overflow_trap");
                        if (byteValue) {
                            line("cmpq $255, %rax");
                            line("ja .Laurora_overflow_trap");
                        }
                        break;
                    case ir::Binary::CheckedMultiply:
                        if (unsignedValue)
                            line("mulq %rcx");
                        else
                            line("imulq %rcx, %rax");
                        line(overflowJump + " .Laurora_overflow_trap");
                        if (byteValue) {
                            line("cmpq $255, %rax");
                            line("ja .Laurora_overflow_trap");
                        }
                        break;
                    case ir::Binary::CheckedDivide:
                        checkedDivision(false, unsignedValue);
                        break;
                    case ir::Binary::CheckedRemainder:
                        checkedDivision(true, unsignedValue);
                        break;
                    case ir::Binary::BitAnd:
                        line("andq %rcx, %rax");
                        break;
                    case ir::Binary::BitOr:
                        line("orq %rcx, %rax");
                        break;
                    case ir::Binary::BitXor:
                        line("xorq %rcx, %rax");
                        break;
                    case ir::Binary::ShiftLeft:
                        checkedShift(true, byteValue);
                        break;
                    case ir::Binary::ShiftRight:
                        checkedShift(false, byteValue);
                        break;
                    }
                } else if constexpr (std::is_same_v<Op, ir::Convert>) {
                    if (operation.resultType == Type::U8) {
                        // Unsigned comparison rejects negative i64 inputs too.
                        line("cmpq $255, %rax");
                        line("ja .Laurora_overflow_trap");
                    } else if (operation.sourceType != Type::U8) {
                        // i64 <-> u64 has the intersection 0..INT64_MAX.
                        line("testq %rax, %rax");
                        line("js .Laurora_overflow_trap");
                    }
                    // Widening canonical u8 is exact: its high bits are already zero.
                } else if constexpr (std::is_same_v<Op, ir::Compare>) {
                    pop("%rcx");
                    line("cmpq %rax, %rcx");
                    const bool byteValue = operation.operandType == Type::U8;
                    const bool unsignedValue = operation.operandType == Type::U64 || byteValue;
                    std::string condition;
                    switch (operation.operation) {
                    case ir::Comparison::Equal:
                        condition = "e";
                        break;
                    case ir::Comparison::NotEqual:
                        condition = "ne";
                        break;
                    case ir::Comparison::Less:
                        condition = unsignedValue ? "b" : "l";
                        break;
                    case ir::Comparison::Greater:
                        condition = unsignedValue ? "a" : "g";
                        break;
                    case ir::Comparison::LessEqual:
                        condition = unsignedValue ? "be" : "le";
                        break;
                    case ir::Comparison::GreaterEqual:
                        condition = unsignedValue ? "ae" : "ge";
                        break;
                    }
                    line("set" + condition + " %al");
                    line("movzbq %al, %rax");
                } else if constexpr (std::is_same_v<Op, ir::BoundsGuard>) {
                    line("cmpq $" + std::to_string(operation.length) + ", %rax");
                    line("jae .Laurora_bounds_trap");
                } else if constexpr (std::is_same_v<Op, ir::IndexLoad>) {
                    line("leaq " + address(operation.offset) + ", %rcx");
                    loadValue(operation.elementType,
                              "(%rcx,%rax," +
                                  std::to_string(ir::storageWidth(operation.elementType)) + ")");
                } else if constexpr (std::is_same_v<Op, ir::IndexStore>) {
                    pop("%rcx");
                    line("leaq " + address(operation.offset) + ", %rdx");
                    storeValue(operation.elementType,
                               "(%rdx,%rcx," +
                                   std::to_string(ir::storageWidth(operation.elementType)) + ")");
                } else if constexpr (std::is_same_v<Op, ir::BorrowHandle>) {
                    line("leaq " + address(operation.ownerOffset) + ", %rax");
                } else if constexpr (std::is_same_v<Op, ir::Call>) {
                    for (std::size_t index = argumentCounts.at(operation.callee); index > 0;
                         --index)
                        pop(argumentRegisters[index - 1]);
                    call(operation.callee);
                } else if constexpr (std::is_same_v<Op, ir::AggregateCall>) {
                    const auto &target = *functions.at(operation.callee);
                    const int recordBytes =
                        packArguments(target, operation.objectArguments, operation.spanArguments);
                    if (target.result.isClass())
                        line("leaq " + address(operation.resultOffset) + ", %r10");
                    call(operation.callee);
                    if (recordBytes)
                        line("addq $" + std::to_string(recordBytes) + ", %rsp");
                } else if constexpr (std::is_same_v<Op, ir::BeginBytes>) {
                    clearBytesOwner(operation.offset);
                } else if constexpr (std::is_same_v<Op, ir::AllocateBytes>) {
                    line("movq %rax, %rsi");
                    line("movq " + address(operation.regionOffset) + ", %rdi");
                    line("leaq " + address(operation.resultOffset) + ", %rdx");
                    call("__au_runtime_bytes_allocate");
                } else if constexpr (std::is_same_v<Op, ir::MoveBytes>) {
                    moveBytesOwner(operation.sourceOffset, operation.resultOffset);
                } else if constexpr (std::is_same_v<Op, ir::BytesOk>) {
                    line("movq " + address(operation.offset - 24) + ", %rax");
                } else if constexpr (std::is_same_v<Op, ir::BytesLength>) {
                    line("movq " + address(operation.offset - 16) + ", %rax");
                } else if constexpr (std::is_same_v<Op, ir::BytesLoad>) {
                    // Canonical failed/empty owners have length zero. Unsigned
                    // comparison rejects negative and upper-bound indices too.
                    line("cmpq " + address(operation.offset - 16) + ", %rax");
                    line("jae .Laurora_bounds_trap");
                    line("movq %rax, %rsi");
                    line("leaq " + address(operation.offset) + ", %rdi");
                    call("__au_runtime_bytes_at");
                } else if constexpr (std::is_same_v<Op, ir::BytesStore>) {
                    line("movq %rax, %rdx");
                    pop("%rsi");
                    line("leaq " + address(operation.offset) + ", %rdi");
                    call("__au_runtime_bytes_set");
                } else if constexpr (std::is_same_v<Op, ir::EndBytes>) {
                    // Cleanup may occur with a return value or other expression
                    // operands outstanding. Preserve both value and stack parity.
                    push();
                    line("leaq " + address(operation.offset) + ", %rdi");
                    call("__au_runtime_bytes_drop");
                    pop("%rax");
                } else if constexpr (std::is_same_v<Op, ir::ResourceCall>) {
                    const auto &target = *functions.at(operation.callee);
                    const int recordBytes = packResources(target, operation);
                    if (target.result.isBytes())
                        line("leaq " + address(operation.resultOffset) + ", %r10");
                    call(operation.callee);
                    line("addq $" + std::to_string(recordBytes) + ", %rsp");
                } else if constexpr (std::is_same_v<Op, ir::BindRegionParameter>) {
                    line("movq " + address(callRecordSaveOffset) + ", %r11");
                    line("movq (%r11), %rax");
                    line("movq %rax, " + address(operation.offset));
                } else if constexpr (std::is_same_v<Op, ir::BindBytesParameter>) {
                    line("movq " + address(callRecordSaveOffset) + ", %r11");
                    const int source = recordOffset(*currentFunction, operation.index);
                    for (int byte = 0; byte < 32; byte += 8) {
                        const auto field = std::to_string(source + byte) + "(%r11)";
                        line("movq " + field + ", %rax");
                        line("movq %rax, " + address(operation.offset - byte));
                        line("movq $0, " + field);
                    }
                } else if constexpr (std::is_same_v<Op, ir::ReturnBytes>) {
                    line("movq " + address(resultSaveOffset) + ", %r10");
                    for (int byte = 0; byte < 32; byte += 8) {
                        line("movq " + address(operation.offset - byte) + ", %rcx");
                        line("movq %rcx, " + std::to_string(byte) + "(%r10)");
                    }
                    clearBytesOwner(operation.offset);
                    line("xorq %rax, %rax");
                    line("jmp " + returnLabel());
                } else if constexpr (std::is_same_v<Op, ir::BeginArray> || std::is_same_v<Op, ir::EndArray> ||
                                     std::is_same_v<Op, ir::EndSpan>) {
                    // Static lifetime changes preserve the scalar current value.
                } else if constexpr (std::is_same_v<Op, ir::BorrowSpan>) {
                    line("leaq " + address(operation.arrayOffset) + ", %rcx");
                    line("movq %rcx, " + address(operation.resultOffset));
                    line("movq $" +
                         std::to_string(currentFunction->arraySlots.at(operation.arrayOffset)) +
                         ", " + address(operation.resultOffset - 8));
                } else if constexpr (std::is_same_v<Op, ir::ReborrowSpan>) {
                    line("movq " + address(operation.sourceOffset) + ", %rcx");
                    line("movq %rcx, " + address(operation.resultOffset));
                    line("movq " + address(operation.sourceOffset - 8) + ", %rcx");
                    line("movq %rcx, " + address(operation.resultOffset - 8));
                } else if constexpr (std::is_same_v<Op, ir::Subspan>) {
                    pop("%rcx"); // offset; current %rax is count
                    // Lengths originate only in validated local byte-array borrows
                    // and checked child windows. Unsigned comparisons reject both
                    // negative i64 operands and values above the bounded extent.
                    line("movq " + address(operation.sourceOffset - 8) + ", %rdx");
                    line("cmpq %rdx, %rcx");
                    line("ja .Laurora_bounds_trap");
                    line("subq %rcx, %rdx");
                    line("cmpq %rdx, %rax");
                    line("ja .Laurora_bounds_trap");
                    // Even an empty endpoint view stays tied to its parent; no
                    // byte is loaded here, and SpanLoad rejects every empty index.
                    line("addq " + address(operation.sourceOffset) + ", %rcx");
                    line("movq %rcx, " + address(operation.resultOffset));
                    line("movq %rax, " + address(operation.resultOffset - 8));
                } else if constexpr (std::is_same_v<Op, ir::SpanLength>) {
                    line("movq " + address(operation.offset - 8) + ", %rax");
                } else if constexpr (std::is_same_v<Op, ir::SpanLoad>) {
                    // Unsigned comparison rejects negative signed indices before
                    // loading the base pointer or addressing any payload byte.
                    line("cmpq " + address(operation.offset - 8) + ", %rax");
                    line("jae .Laurora_bounds_trap");
                    line("movq " + address(operation.offset) + ", %rcx");
                    line("movzbq (%rcx,%rax,1), %rax");
                } else if constexpr (std::is_same_v<Op, ir::BeginObject>) {
                    clearObject(operation.offset,
                                currentFunction->objectSlots.at(operation.offset).className);
                } else if constexpr (std::is_same_v<Op, ir::EndObject>) {
                    // The verifier ends the lexical lifetime; no storage escapes.
                } else if constexpr (std::is_same_v<Op, ir::CopyObject>) {
                    const auto &name =
                        currentFunction->objectSlots.at(operation.sourceOffset).className;
                    const auto &layout = classLayouts->at(name);
                    for (std::size_t leaf = 0; leaf < layout.size(); ++leaf) {
                        loadValue(layout[leaf], address(objectLeaf(operation.sourceOffset, leaf)));
                        storeValue(layout[leaf], address(objectLeaf(operation.resultOffset, leaf)));
                    }
                } else if constexpr (std::is_same_v<Op, ir::ObjectFieldCopy>) {
                    const ir::ClassField *field = nullptr;
                    const ir::ClassStorage *source = nullptr;
                    if (operation.sourceOffset == 0) {
                        field = &receiverField(operation.fieldIndex);
                        source = &receiverStorage();
                        line("movq " + address(receiverSaveOffset) + ", %r10");
                    } else {
                        const auto &name =
                            currentFunction->objectSlots.at(operation.sourceOffset).className;
                        field = &classFields->at(name)[operation.fieldIndex];
                        source = &classStorage->at(name);
                        line("leaq " + address(operation.sourceOffset) + ", %r10");
                    }
                    const auto &layout = classLayouts->at(field->elementType.className);
                    for (int leaf = 0; leaf < field->length; ++leaf) {
                        loadValue(layout[leaf],
                                  std::to_string(source->leafOffsets[field->firstLeaf + leaf]) +
                                      "(%r10)");
                        storeValue(layout[leaf], address(objectLeaf(operation.resultOffset, leaf)));
                    }
                } else if constexpr (std::is_same_v<Op, ir::AssignObjectField>) {
                    const auto &name = operation.objectOffset == 0
                                           ? currentFunction->receiver->className
                                           : currentFunction->objectSlots.at(operation.objectOffset).className;
                    const auto &field = classFields->at(name)[operation.fieldIndex];
                    const auto &sourceLayout = classLayouts->at(field.elementType.className);
                    const auto &destinationStorage = classStorage->at(name);
                    if (operation.objectOffset == 0)
                        line("movq " + address(receiverSaveOffset) + ", %r10");
                    else
                        line("leaq " + address(operation.objectOffset) + ", %r10");
                    for (int leaf = 0; leaf < field.length; ++leaf) {
                        loadValue(sourceLayout[leaf], address(objectLeaf(operation.sourceOffset, leaf)));
                        storeValue(sourceLayout[leaf],
                                   std::to_string(destinationStorage.leafOffsets[field.firstLeaf + leaf]) + "(%r10)");
                    }
                } else if constexpr (std::is_same_v<Op, ir::InitializeObjectField>) {
                    const auto &field = receiverField(operation.fieldIndex);
                    const auto &layout = classLayouts->at(field.elementType.className);
                    line("movq " + address(receiverSaveOffset) + ", %r10");
                    for (int leaf = 0; leaf < field.length; ++leaf) {
                        loadValue(layout[leaf], address(objectLeaf(operation.sourceOffset, leaf)));
                        storeValue(
                            layout[leaf],
                            std::to_string(receiverStorage().leafOffsets[field.firstLeaf + leaf]) +
                                "(%r10)");
                    }
                } else if constexpr (std::is_same_v<Op, ir::ReceiverLoad>) {
                    line("movq " + address(receiverSaveOffset) + ", %r10");
                    loadValue(operation.type,
                              std::to_string(receiverStorage().fieldOffsets[operation.fieldIndex]) +
                                  "(%r10)");
                } else if constexpr (std::is_same_v<Op, ir::ReceiverStore>) {
                    line("movq " + address(receiverSaveOffset) + ", %r10");
                    storeValue(
                        operation.type,
                        std::to_string(receiverStorage().fieldOffsets[operation.fieldIndex]) +
                            "(%r10)");
                } else if constexpr (std::is_same_v<Op, ir::ReceiverArrayZero>) {
                    const auto &field = receiverField(operation.fieldIndex);
                    line("movq " + address(receiverSaveOffset) + ", %r10");
                    for (int element = 0; element < field.length; ++element)
                        line(
                            std::string(field.elementType == Type::U8 ? "movb $0, " : "movq $0, ") +
                            std::to_string(
                                receiverStorage().leafOffsets[field.firstLeaf + element]) +
                            "(%r10)");
                } else if constexpr (std::is_same_v<Op, ir::ReceiverBoundsGuard>) {
                    const auto &field = receiverField(operation.fieldIndex);
                    // The unsigned comparison also rejects every negative i64 index.
                    line("cmpq $" + std::to_string(field.length) + ", %rax");
                    line("jae .Laurora_bounds_trap");
                } else if constexpr (std::is_same_v<Op, ir::ReceiverIndexLoad>) {
                    const auto &field = receiverField(operation.fieldIndex);
                    line("movq " + address(receiverSaveOffset) + ", %r10");
                    loadValue(field.elementType,
                              std::to_string(receiverStorage().fieldOffsets[operation.fieldIndex]) +
                                  "(%r10,%rax," +
                                  std::to_string(ir::storageWidth(field.elementType)) + ")");
                } else if constexpr (std::is_same_v<Op, ir::ReceiverIndexStore>) {
                    const auto &field = receiverField(operation.fieldIndex);
                    pop("%rcx");
                    line("movq " + address(receiverSaveOffset) + ", %r10");
                    storeValue(
                        field.elementType,
                        std::to_string(receiverStorage().fieldOffsets[operation.fieldIndex]) +
                            "(%r10,%rcx," + std::to_string(ir::storageWidth(field.elementType)) +
                            ")");
                } else if constexpr (std::is_same_v<Op, ir::MethodCall>) {
                    const auto &target = *functions.at(operation.callee);
                    const bool aggregate = classParameters(target);
                    const int recordBytes =
                        aggregate ? packArguments(target, operation.objectArguments) : 0;
                    if (!aggregate)
                        for (std::size_t index = argumentCounts.at(operation.callee); index > 0;
                             --index)
                            pop(argumentRegisters[index - 1]);
                    if (operation.receiverOffset == 0)
                        line("movq " + address(receiverSaveOffset) + ", %r10");
                    else
                        line("leaq " + address(operation.receiverOffset) + ", %r10");
                    if (operation.receiverFieldIndex >= 0) {
                        const auto &name = operation.receiverOffset == 0
                                               ? currentFunction->receiver->className
                                               : currentFunction->objectSlots.at(operation.receiverOffset).className;
                        const int fieldOffset = classStorage->at(name).fieldOffsets[operation.receiverFieldIndex];
                        if (fieldOffset != 0)
                            line("addq $" + std::to_string(fieldOffset) + ", %r10");
                    }
                    if (target.result.isClass())
                        line("leaq " + address(operation.resultOffset) +
                             (aggregate ? ", %rax" : ", %r11"));
                    call(operation.callee);
                    if (recordBytes)
                        line("addq $" + std::to_string(recordBytes) + ", %rsp");
                } else if constexpr (std::is_same_v<Op, ir::MetadataQuery>) {
                    line("movq %rax, %rdi");
                    call(querySymbol(operation.query, operation.moduleScope));
                } else if constexpr (std::is_same_v<Op, ir::Label>) {
                    output << label(operation.id) << ":\n";
                } else if constexpr (std::is_same_v<Op, ir::Jump>) {
                    line("jmp " + label(operation.target));
                } else if constexpr (std::is_same_v<Op, ir::BranchFalse>) {
                    line("testq %rax, %rax");
                    line("jz " + label(operation.target));
                } else if constexpr (std::is_same_v<Op, ir::Return>) {
                    line("jmp " + returnLabel());
                } else if constexpr (std::is_same_v<Op, ir::ReturnObject>) {
                    line("movq " + address(resultSaveOffset) + ", %r10");
                    const auto &layout = classLayouts->at(currentFunction->result.className);
                    for (std::size_t field = 0; field < layout.size(); ++field) {
                        loadValue(layout[field], address(objectLeaf(operation.offset, field)));
                        storeValue(
                            layout[field],
                            std::to_string(classStorage->at(currentFunction->result.className)
                                               .leafOffsets[field]) +
                                "(%r10)");
                    }
                    line("xorq %rax, %rax");
                    line("jmp " + returnLabel());
                } else if constexpr (std::is_same_v<Op, ir::BindParameter>) {
                    if (callRecordSaveOffset) {
                        line("movq " + address(callRecordSaveOffset) + ", %r11");
                        loadValue(operation.type,
                                  std::to_string(recordOffset(*currentFunction, operation.index)) +
                                      "(%r11)");
                        storeValue(operation.type, address(operation.offset));
                    } else
                        storeArgument(operation.type, operation.index, address(operation.offset));
                } else if constexpr (std::is_same_v<Op, ir::BindSpanParameter>) {
                    line("movq " + address(callRecordSaveOffset) + ", %r11");
                    const int offset = recordOffset(*currentFunction, operation.index);
                    line("movq " + std::to_string(offset) + "(%r11), %rax");
                    line("movq %rax, " + address(operation.offset));
                    line("movq " + std::to_string(offset + 8) + "(%r11), %rax");
                    line("movq %rax, " + address(operation.offset - 8));
                } else if constexpr (std::is_same_v<Op, ir::BindObjectParameter>) {
                    line("movq " + address(callRecordSaveOffset) + ", %r11");
                    const auto &layout = classLayouts->at(operation.className);
                    const int offset = recordOffset(*currentFunction, operation.index);
                    clearObject(operation.offset, operation.className);
                    for (std::size_t field = 0; field < layout.size(); ++field) {
                        loadValue(
                            layout[field],
                            std::to_string(
                                offset + classStorage->at(operation.className).leafOffsets[field]) +
                                "(%r11)");
                        storeValue(layout[field], address(objectLeaf(operation.offset, field)));
                    }
                } else {
                    static_assert(!std::is_same_v<Op, Op>, "unhandled typed IR backend operation");
                }
            },
            instruction);
    }

  public:
    std::string emit(const ir::ValidatedModule &validated) {
        const auto &module = validated.get();
        output.str("");
        output.clear();
        argumentCounts.clear();
        functions.clear();
        classLayouts = &module.classLayouts;
        classFields = &module.classFields;
        classStorage = &module.classStorage;
        functionIndex = 0;
        for (const auto &function : module.functions) {
            argumentCounts[function.name] = function.parameters.size();
            functions[function.name] = &function;
        }
        // Resource graphs link a trusted host adapter. No user-selected source
        // symbol may interpose its allocator, stdio or fail-stop dependencies.
        // Derive this from validated signatures/lifetime IR, never an input flag.
        const bool resourceGraph =
            std::any_of(module.functions.begin(), module.functions.end(), [](const ir::Function &function) {
                return function.result.isResource() ||
                       std::any_of(function.parameters.begin(),
                                   function.parameters.end(),
                                   [](const Type &type) {
                                       return type.isResource();
                                   }) ||
                       std::any_of(function.code.begin(), function.code.end(), [](const ir::Instruction &op) {
                           return std::holds_alternative<ir::BeginBytes>(op);
                       });
            });
        output << "# Aurora compiler output: validated typed IR, x86-64 bootstrap\n.text\n";
        for (const auto &function : module.functions) {
            stackDepth = 0;
            divisionIndex = 0;
            currentFunction = &function;
            const bool aggregate = aggregateSignature(function);
            // Receiver and aggregate entry points use a private compiler ABI and cannot be
            // exposed as ordinary scalar-callable external symbols.
            output << (resourceGraph || function.receiver || aggregate || function.name.starts_with("__au_o_")
                           ? ".local "
                           : ".globl ")
                   << function.name << "\n.type " << function.name << ", @function\n"
                   << function.name << ":\n";
            line("pushq %rbp");
            line("movq %rsp, %rbp");
            receiverSaveOffset = function.receiver ? function.frameBytes + 8 : 0;
            const bool packedArguments =
                function.receiver ? classParameters(function) : aggregate;
            const bool combinedMethod =
                function.receiver && packedArguments && function.result.isClass();
            callRecordSaveOffset =
                packedArguments ? function.frameBytes + (function.receiver ? 16 : 8) : 0;
            resultSaveOffset = (function.result.isClass() || function.result.isBytes())
                                   ? function.frameBytes + (combinedMethod ? 24 : 16)
                                   : 0;
            // Hidden capabilities never occupy source-addressable slots. The
            // new combined mode needs three distinct saves, rounded to 16-byte
            // alignment; every historical mode retains its original layout.
            const int frameBytes = function.frameBytes +
                                   (combinedMethod ? 32 : function.receiver || aggregate ? 16 : 0);
            reserveStack(frameBytes);
            if (function.receiver)
                line("movq %r10, " + address(receiverSaveOffset));
            if (packedArguments)
                line("movq %r11, " + address(callRecordSaveOffset));
            if (function.result.isClass() || function.result.isBytes())
                line(std::string("movq ") +
                     (combinedMethod ? "%rax" : function.receiver ? "%r11" : "%r10") + ", " +
                     address(resultSaveOffset));
            for (const auto &operation : function.code)
                instruction(operation);
            output << returnLabel() << ":\n";
            line("leave");
            line("ret");
            output << ".size " << function.name << ", .-" << function.name << "\n";
            ++functionIndex;
        }
        for (const auto &[scope, view] : module.descriptorViews) {
            for (const auto query : {ir::Query::Size, ir::Query::PublicFieldCount}) {
                const std::string name = query == ir::Query::Size ? "size" : "field_count";
                const auto symbol = querySymbol(query, scope);
                const std::string labelPrefix = ".Lscope" + std::to_string(scope) + "_" + name;
                output << ".globl " << symbol << "\n.type " << symbol << ", @function\n"
                       << symbol << ":\n";
                for (int id : view) {
                    line("cmpq $" + std::to_string(id) + ", %rdi");
                    line("je " + labelPrefix + std::to_string(id));
                }
                line("xorq %rax, %rax");
                line("ret");
                for (int id : view) {
                    const auto &descriptor = module.descriptors.at(id);
                    output << labelPrefix << id << ":\n";
                    line("movq $" +
                         std::to_string(query == ir::Query::Size ? descriptor.size
                                                                 : descriptor.publicFields) +
                         ", %rax");
                    line("ret");
                }
                output << ".size " << symbol << ", .-" << symbol << "\n";
            }
        }
        output << ".Laurora_bounds_trap:\n    ud2\n.Laurora_overflow_trap:\n    "
                  "ud2\n.Laurora_division_zero_trap:\n    ud2\n.Laurora_shift_count_trap:\n    "
                  "ud2\n.section "
                  ".note.GNU-stack,\"\",@progbits\n";
        return output.str();
    }
};
} // namespace aurora
