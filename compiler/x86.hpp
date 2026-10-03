#pragma once
#include "ir.hpp"
#include <sstream>
#include <type_traits>

namespace aurora {
// This backend accepts validated typed IR only. It has no AST, scope, borrow or move state.
class X86Emitter {
    std::ostringstream output;
    int stackDepth = 0;
    int functionIndex = 0;
    std::map<std::string, std::size_t> argumentCounts;
    const std::vector<std::string> argumentRegisters = {"%rdi", "%rsi", "%rdx",
                                                        "%rcx", "%r8",  "%r9"};
    void line(const std::string &text) {
        output << "    " << text << '\n';
    }
    std::string address(int offset) {
        return "-" + std::to_string(offset) + "(%rbp)";
    }
    std::string label(int id) {
        return ".Lau" + std::to_string(functionIndex) + "_" + std::to_string(id);
    }
    std::string returnLabel() {
        return ".Lreturn" + std::to_string(functionIndex);
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
                    if (operation.operation == ir::Unary::LogicalNot)
                        line("xorq $1, %rax");
                    else {
                        line("negq %rax");
                        line("jo .Laurora_overflow_trap");
                    }
                } else if constexpr (std::is_same_v<Op, ir::BinaryValue>) {
                    pop("%rcx");
                    if (operation.operation == ir::Binary::CheckedAdd)
                        line("addq %rcx, %rax");
                    else if (operation.operation == ir::Binary::CheckedMultiply)
                        line("imulq %rcx, %rax");
                    else {
                        line("subq %rax, %rcx");
                        line("movq %rcx, %rax");
                    }
                    line("jo .Laurora_overflow_trap");
                } else if constexpr (std::is_same_v<Op, ir::Compare>) {
                    pop("%rcx");
                    line("cmpq %rax, %rcx");
                    const std::map<ir::Comparison, std::string> conditions = {
                        {ir::Comparison::Equal, "e"},      {ir::Comparison::NotEqual, "ne"},
                        {ir::Comparison::Less, "l"},       {ir::Comparison::Greater, "g"},
                        {ir::Comparison::LessEqual, "le"}, {ir::Comparison::GreaterEqual, "ge"}};
                    line("set" + conditions.at(operation.operation) + " %al");
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
                } else if constexpr (std::is_same_v<Op, ir::BindParameter>) {
                    line("movq " + argumentRegisters[operation.index] + ", " +
                         address(operation.offset));
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
        functionIndex = 0;
        for (const auto &function : module.functions)
            argumentCounts[function.name] = function.parameters.size();
        output << "# Aurora compiler output: validated typed IR, x86-64 bootstrap\n.text\n";
        for (const auto &function : module.functions) {
            stackDepth = 0;
            output << ".globl " << function.name << "\n.type " << function.name << ", @function\n"
                   << function.name << ":\n";
            line("pushq %rbp");
            line("movq %rsp, %rbp");
            line("subq $" + std::to_string(function.frameBytes) + ", %rsp");
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
        output << ".Laurora_bounds_trap:\n    ud2\n.Laurora_overflow_trap:\n    ud2\n.section "
                  ".note.GNU-stack,\"\",@progbits\n";
        return output.str();
    }
};
} // namespace aurora
