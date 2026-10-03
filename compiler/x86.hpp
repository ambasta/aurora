#pragma once
#include "ir.hpp"
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
    std::map<std::string, const ir::Function *> functions;
    std::map<std::string, std::size_t> argumentCounts;
    const std::vector<std::string> argumentRegisters = {"%rdi", "%rsi", "%rdx",
                                                        "%rcx", "%r8",  "%r9"};
    void line(const std::string &text) { output << "    " << text << '\n'; }
    std::string address(int offset) { return "-" + std::to_string(offset) + "(%rbp)"; }
    std::string label(int id) {
        return ".Lau" + std::to_string(functionIndex) + "_" + std::to_string(id);
    }
    std::string returnLabel() { return ".Lreturn" + std::to_string(functionIndex); }
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
        if (function.result.isClass())
            return true;
        for (const auto &type : function.parameters)
            if (type.isClass())
                return true;
        return false;
    }
    int argumentWords(const Type &type) const {
        return type.isClass() ? static_cast<int>(std::max<std::size_t>(
                                    1, classLayouts->at(type.className).size()))
                              : 1;
    }
    int recordOffset(const ir::Function &function, std::size_t parameter) const {
        int offset = 0;
        for (std::size_t index = 0; index < parameter; ++index)
            offset += argumentWords(function.parameters[index]) * 8;
        return offset;
    }
    const ir::ClassField &receiverField(int fieldIndex) const {
        return classFields->at(currentFunction->receiver->className)[fieldIndex];
    }
    int packArguments(const ir::Function &target, const std::vector<int> &objects) {
        for (std::size_t index = target.parameters.size(); index > 0; --index)
            if (scalar(target.parameters[index - 1]))
                pop(argumentRegisters[index - 1]);
        const int recordBytes = (recordOffset(target, target.parameters.size()) + 15) & ~15;
        if (recordBytes)
            line("subq $" + std::to_string(recordBytes) + ", %rsp");
        for (std::size_t index = 0; index < target.parameters.size(); ++index) {
            const auto &type = target.parameters[index];
            const int offset = recordOffset(target, index);
            if (scalar(type))
                line("movq " + argumentRegisters[index] + ", " + std::to_string(offset) + "(%rsp)");
            else {
                const auto &layout = classLayouts->at(type.className);
                for (std::size_t field = 0; field < layout.size(); ++field) {
                    line("movq " + address(objects[index] - static_cast<int>(field * 8)) +
                         ", %rax");
                    line("movq %rax, " + std::to_string(offset + field * 8) + "(%rsp)");
                }
            }
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
    void checkedShift(bool left) {
        // Unsigned comparison rejects negative i64 counts too, before x86 can mask them.
        line("cmpq $63, %rax");
        line("ja .Laurora_shift_count_trap");
        line("movq %rcx, %rdx");
        line("movq %rax, %rcx");
        line("movq %rdx, %rax");
        if (left) {
            line("shlq %cl, %rax");
            // Shifting back detects every lost high bit, including counts > 1,
            // for which the processor's overflow flag has no defined meaning.
            line("movq %rax, %r11");
            line("shrq %cl, %r11");
            line("cmpq %rdx, %r11");
            line("jne .Laurora_overflow_trap");
        } else
            line("shrq %cl, %rax");
    }
    void instruction(const ir::Instruction &instruction) {
        std::visit(
            [&](const auto &operation) {
                using Op = std::decay_t<decltype(operation)>;
                if constexpr (std::is_same_v<Op, ir::Constant>) {
                    line("movabsq $" + std::to_string(operation.value) + ", %rax");
                } else if constexpr (std::is_same_v<Op, ir::Load>) {
                    line("movq " + address(operation.offset) + ", %rax");
                } else if constexpr (std::is_same_v<Op, ir::Store>) {
                    line("movq %rax, " + address(operation.offset));
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
                        line("notq %rax");
                        break;
                    }
                } else if constexpr (std::is_same_v<Op, ir::BinaryValue>) {
                    pop("%rcx");
                    const bool unsignedValue = operation.operandType == Type::U64;
                    const std::string overflowJump = unsignedValue ? "jc" : "jo";
                    switch (operation.operation) {
                    case ir::Binary::CheckedAdd:
                        line("addq %rcx, %rax");
                        line(overflowJump + " .Laurora_overflow_trap");
                        break;
                    case ir::Binary::CheckedSubtract:
                        line("subq %rax, %rcx");
                        line("movq %rcx, %rax");
                        line(overflowJump + " .Laurora_overflow_trap");
                        break;
                    case ir::Binary::CheckedMultiply:
                        if (unsignedValue)
                            line("mulq %rcx");
                        else
                            line("imulq %rcx, %rax");
                        line(overflowJump + " .Laurora_overflow_trap");
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
                        checkedShift(true);
                        break;
                    case ir::Binary::ShiftRight:
                        checkedShift(false);
                        break;
                    }
                } else if constexpr (std::is_same_v<Op, ir::Convert>) {
                    // Both directions have the same representable intersection,
                    // 0..INT64_MAX, but retain distinct types through verification.
                    line("testq %rax, %rax");
                    line("js .Laurora_overflow_trap");
                } else if constexpr (std::is_same_v<Op, ir::Compare>) {
                    pop("%rcx");
                    line("cmpq %rax, %rcx");
                    const bool unsignedValue = operation.operandType == Type::U64;
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
                    line("movq (%rcx,%rax,8), %rax");
                } else if constexpr (std::is_same_v<Op, ir::IndexStore>) {
                    pop("%rcx");
                    line("leaq " + address(operation.offset) + ", %rdx");
                    line("movq %rax, (%rdx,%rcx,8)");
                } else if constexpr (std::is_same_v<Op, ir::BorrowHandle>) {
                    line("leaq " + address(operation.ownerOffset) + ", %rax");
                } else if constexpr (std::is_same_v<Op, ir::Call>) {
                    for (std::size_t index = argumentCounts.at(operation.callee); index > 0;
                         --index)
                        pop(argumentRegisters[index - 1]);
                    call(operation.callee);
                } else if constexpr (std::is_same_v<Op, ir::AggregateCall>) {
                    const auto &target = *functions.at(operation.callee);
                    const int recordBytes = packArguments(target, operation.objectArguments);
                    if (target.result.isClass())
                        line("leaq " + address(operation.resultOffset) + ", %r10");
                    call(operation.callee);
                    if (recordBytes)
                        line("addq $" + std::to_string(recordBytes) + ", %rsp");
                } else if constexpr (std::is_same_v<Op, ir::BeginObject> ||
                                     std::is_same_v<Op, ir::EndObject>) {
                    // Scalar-only class lifetimes need no runtime action. The
                    // verifier prevents use outside their lexical lifetime.
                } else if constexpr (std::is_same_v<Op, ir::CopyObject>) {
                    const auto &name =
                        currentFunction->objectSlots.at(operation.sourceOffset).className;
                    const auto &layout = classLayouts->at(name);
                    for (std::size_t leaf = 0; leaf < layout.size(); ++leaf) {
                        line("movq " +
                             address(operation.sourceOffset - static_cast<int>(leaf * 8)) +
                             ", %rax");
                        line("movq %rax, " +
                             address(operation.resultOffset - static_cast<int>(leaf * 8)));
                    }
                } else if constexpr (std::is_same_v<Op, ir::ObjectFieldCopy>) {
                    const ir::ClassField *field = nullptr;
                    if (operation.sourceOffset == 0) {
                        field = &receiverField(operation.fieldIndex);
                        line("movq " + address(receiverSaveOffset) + ", %r10");
                    } else {
                        const auto &name =
                            currentFunction->objectSlots.at(operation.sourceOffset).className;
                        field = &classFields->at(name)[operation.fieldIndex];
                        line("leaq " + address(operation.sourceOffset) + ", %r10");
                    }
                    for (int leaf = 0; leaf < field->length; ++leaf) {
                        line("movq " + std::to_string((field->firstLeaf + leaf) * 8) +
                             "(%r10), %rax");
                        line("movq %rax, " + address(operation.resultOffset - leaf * 8));
                    }
                } else if constexpr (std::is_same_v<Op, ir::InitializeObjectField>) {
                    const auto &field = receiverField(operation.fieldIndex);
                    line("movq " + address(receiverSaveOffset) + ", %r10");
                    for (int leaf = 0; leaf < field.length; ++leaf) {
                        line("movq " + address(operation.sourceOffset - leaf * 8) + ", %rax");
                        line("movq %rax, " + std::to_string((field.firstLeaf + leaf) * 8) +
                             "(%r10)");
                    }
                } else if constexpr (std::is_same_v<Op, ir::ReceiverLoad>) {
                    line("movq " + address(receiverSaveOffset) + ", %r10");
                    line("movq " +
                         std::to_string(receiverField(operation.fieldIndex).firstLeaf * 8) +
                         "(%r10), %rax");
                } else if constexpr (std::is_same_v<Op, ir::ReceiverStore>) {
                    line("movq " + address(receiverSaveOffset) + ", %r10");
                    line("movq %rax, " +
                         std::to_string(receiverField(operation.fieldIndex).firstLeaf * 8) +
                         "(%r10)");
                } else if constexpr (std::is_same_v<Op, ir::ReceiverArrayZero>) {
                    const auto &field = receiverField(operation.fieldIndex);
                    line("movq " + address(receiverSaveOffset) + ", %r10");
                    for (int element = 0; element < field.length; ++element)
                        line("movq $0, " + std::to_string((field.firstLeaf + element) * 8) +
                             "(%r10)");
                } else if constexpr (std::is_same_v<Op, ir::ReceiverBoundsGuard>) {
                    const auto &field = receiverField(operation.fieldIndex);
                    // The unsigned comparison also rejects every negative i64 index.
                    line("cmpq $" + std::to_string(field.length) + ", %rax");
                    line("jae .Laurora_bounds_trap");
                } else if constexpr (std::is_same_v<Op, ir::ReceiverIndexLoad>) {
                    const auto &field = receiverField(operation.fieldIndex);
                    line("movq " + address(receiverSaveOffset) + ", %r10");
                    line("movq " + std::to_string(field.firstLeaf * 8) + "(%r10,%rax,8), %rax");
                } else if constexpr (std::is_same_v<Op, ir::ReceiverIndexStore>) {
                    const auto &field = receiverField(operation.fieldIndex);
                    pop("%rcx");
                    line("movq " + address(receiverSaveOffset) + ", %r10");
                    line("movq %rax, " + std::to_string(field.firstLeaf * 8) + "(%r10,%rcx,8)");
                } else if constexpr (std::is_same_v<Op, ir::MethodCall>) {
                    const auto &target = *functions.at(operation.callee);
                    const bool aggregate = aggregateSignature(target);
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
                        line("movq " + address(operation.offset - static_cast<int>(field * 8)) +
                             ", %rax");
                        line("movq %rax, " + std::to_string(field * 8) + "(%r10)");
                    }
                    line("xorq %rax, %rax");
                    line("jmp " + returnLabel());
                } else if constexpr (std::is_same_v<Op, ir::BindParameter>) {
                    if (callRecordSaveOffset) {
                        line("movq " + address(callRecordSaveOffset) + ", %r11");
                        line("movq " +
                             std::to_string(recordOffset(*currentFunction, operation.index)) +
                             "(%r11), %rax");
                        line("movq %rax, " + address(operation.offset));
                    } else
                        line("movq " + argumentRegisters[operation.index] + ", " +
                             address(operation.offset));
                } else if constexpr (std::is_same_v<Op, ir::BindObjectParameter>) {
                    line("movq " + address(callRecordSaveOffset) + ", %r11");
                    const auto &layout = classLayouts->at(operation.className);
                    const int offset = recordOffset(*currentFunction, operation.index);
                    for (std::size_t field = 0; field < layout.size(); ++field) {
                        line("movq " + std::to_string(offset + field * 8) + "(%r11), %rax");
                        line("movq %rax, " +
                             address(operation.offset - static_cast<int>(field * 8)));
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
        functionIndex = 0;
        for (const auto &function : module.functions) {
            argumentCounts[function.name] = function.parameters.size();
            functions[function.name] = &function;
        }
        output << "# Aurora compiler output: validated typed IR, x86-64 bootstrap\n.text\n";
        for (const auto &function : module.functions) {
            stackDepth = 0;
            divisionIndex = 0;
            currentFunction = &function;
            const bool aggregate = aggregateSignature(function);
            // Receiver and aggregate entry points use a private compiler ABI and cannot be
            // exposed as ordinary scalar-callable external symbols.
            output << (function.receiver || aggregate ? ".local " : ".globl ") << function.name
                   << "\n.type " << function.name << ", @function\n"
                   << function.name << ":\n";
            line("pushq %rbp");
            line("movq %rsp, %rbp");
            receiverSaveOffset = function.receiver ? function.frameBytes + 8 : 0;
            callRecordSaveOffset =
                aggregate ? function.frameBytes + (function.receiver ? 16 : 8) : 0;
            resultSaveOffset = aggregate ? function.frameBytes + 16 : 0;
            const int frameBytes = function.frameBytes + (function.receiver || aggregate ? 16 : 0);
            line("subq $" + std::to_string(frameBytes) + ", %rsp");
            if (function.receiver)
                line("movq %r10, " + address(receiverSaveOffset));
            if (aggregate) {
                line("movq %r11, " + address(callRecordSaveOffset));
                if (function.result.isClass())
                    line("movq %r10, " + address(resultSaveOffset));
            }
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
