#pragma once
#include "ir_layout.hpp"
#include <algorithm>
#include <span>
#include <sstream>
#include <type_traits>
#include <utility>

namespace aurora {
// Local binding is for trusted bootstrap units linked with a separate adapter.
// It changes symbol binding only, never signatures or generated instructions.
enum class SymbolBinding {
    Default,
    Local
};
// Default output retains the external bootstrap reflection ABI. Native images
// may select only helpers referenced by retained, fully validated IR.
enum class ReflectionEmission {
    All,
    Referenced
};
// Stack use follows the instructions emitted below, not a second ABI calculator.
// Like GCC .su, localBytes includes the incoming return address. Call-site bytes
// stop immediately before CALL; the callee's own incoming slot is counted there.
class FunctionStackFacts {
public:
    int localBytes = 8;
    std::map<std::string, int> calls;
};
// This backend accepts validated typed IR only. It has no AST, scope, borrow or move state.
class X86Emitter {
    std::ostringstream output;
    int stackDepth = 0;
    int liveStackBytes = 8;
    std::map<std::string, FunctionStackFacts> emittedStackFacts;
    FunctionStackFacts *currentStackFacts = nullptr;
    int functionIndex = 0;
    int divisionIndex = 0;
    int receiverSaveOffset = 0;
    int callRecordSaveOffset = 0;
    int resultSaveOffset = 0;
    bool ownedSpanRuntime = false;
    std::vector<std::vector<unsigned char>> literalBytes;
    std::map<int, int> serviceLoanOffsets;
    const ir::Function *currentFunction = nullptr;
    const std::map<std::string, std::vector<Type>> *classLayouts = nullptr;
    const std::map<std::string, std::vector<ir::ClassField>> *classFields = nullptr;
    const std::map<std::string, ir::ClassStorage> *classStorage = nullptr;
    std::map<std::string, const ir::Function *> functions;
    std::map<std::string, std::size_t> argumentCounts;
    const std::vector<std::string> argumentRegisters = {"%rdi", "%rsi", "%rdx", "%rcx", "%r8", "%r9"};
    const std::vector<std::string> byteArgumentRegisters = {"%dil", "%sil", "%dl", "%cl", "%r8b", "%r9b"};
    void line(const std::string &text) {
        output << "    " << text << '\n';
    }
    void loadValue(const Type &type, const std::string &source) {
        line(std::string(type == Type::U8 ? "movzbq " : "movq ") + source + ", %rax");
    }
    void storeValue(const Type &type, const std::string &destination) {
        line(std::string(type == Type::U8 ? "movb %al, " : "movq %rax, ") + destination);
    }
    enum class CopyBases {
        Stable,
        StackDestination
    };
    template <class Source, class Destination>
    void copyLeaves(std::span<const Type> leaves,
                    std::span<const int> sourceOffsets,
                    std::span<const int> destinationOffsets,
                    const Source &source,
                    const Destination &destination,
                    CopyBases bases) {
        // Only verified copied payload ranges reach this helper. Their objects,
        // receiver storage and call records are disjoint; every source leaf is
        // initialized. Check both canonical offset ranges, never address strings.
        // RAX alone is scratch after either path: packed scalar arguments and
        // R10/R11 may be live. Sources use stable RBP/R10/R11 bases. The sole
        // RSP destination is captured in RAX before any temporary stack saves.
        for (std::size_t leaf = 0; leaf < leaves.size();) {
            std::size_t end = leaf + 1;
            int bytes = ir::storageWidth(leaves[leaf]);
            while (end < leaves.size() && sourceOffsets[end] == sourceOffsets[leaf] + bytes &&
                   destinationOffsets[end] == destinationOffsets[leaf] + bytes) {
                bytes += ir::storageWidth(leaves[end]);
                ++end;
            }
            // Copy only this exact initialized run, never padding or owner
            // descriptors. Stable bases are unchanged by these saves; capture
            // the outgoing record address before RSP moves. No calls occur
            // before restoration. Account for the real transient high water
            // without altering operand depth.
            if (bytes >= 64) {
                if (bases == CopyBases::StackDestination)
                    line("leaq " + destination(destinationOffsets[leaf]) + ", %rax");
                line("pushq %rsi");
                line("pushq %rdi");
                line("pushq %rcx");
                growStack(24);
                line("leaq " + source(sourceOffsets[leaf]) + ", %rsi");
                if (bases == CopyBases::StackDestination)
                    line("movq %rax, %rdi");
                else
                    line("leaq " + destination(destinationOffsets[leaf]) + ", %rdi");
                line("movq $" + std::to_string(bytes) + ", %rcx");
                line("cld");
                line("rep movsb");
                line("popq %rcx");
                line("popq %rdi");
                line("popq %rsi");
                liveStackBytes -= 24;
                leaf = end;
                continue;
            }
            bool qword = leaves.size() - leaf >= 8;
            for (std::size_t byte = 0; qword && byte < 8; ++byte)
                qword = leaves[leaf + byte] == Type::U8 &&
                        sourceOffsets[leaf + byte] == sourceOffsets[leaf] + static_cast<int>(byte) &&
                        destinationOffsets[leaf + byte] == destinationOffsets[leaf] + static_cast<int>(byte);
            if (qword) {
                line("movq " + source(sourceOffsets[leaf]) + ", %rax");
                line("movq %rax, " + destination(destinationOffsets[leaf]));
                leaf += 8;
            } else {
                loadValue(leaves[leaf], source(sourceOffsets[leaf]));
                storeValue(leaves[leaf], destination(destinationOffsets[leaf]));
                ++leaf;
            }
        }
    }
    void storeArgument(const Type &type, std::size_t index, const std::string &destination) {
        line(std::string(type == Type::U8 ? "movb " : "movq ") +
             (type == Type::U8 ? byteArgumentRegisters[index] : argumentRegisters[index]) + ", " + destination);
    }
    int objectLeaf(int base, std::size_t leaf) const {
        return base - classStorage->at(currentFunction->objectSlots.at(base).className).leafOffsets.at(leaf);
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
    template <class Address> void clearPadding(const std::string &name, const Address &destination) {
        const auto &physical = classStorage->at(name);
        const auto &leaves = classLayouts->at(name);
        // Descriptors have no scalar leaves, but still occupy private payload
        // bytes. Clearing representation gaps must never clear a live owner.
        std::vector<std::pair<int, int>> payload;
        for (std::size_t leaf = 0; leaf < leaves.size(); ++leaf)
            payload.emplace_back(physical.leafOffsets[leaf], ir::storageWidth(leaves[leaf]));
        const auto &fields = classFields->at(name);
        for (std::size_t field = 0; field < fields.size(); ++field)
            if (fields[field].elementType.isBytes())
                payload.emplace_back(physical.fieldOffsets[field], 32);
        std::sort(payload.begin(), payload.end());
        int cursor = 0;
        for (const auto &[offset, width] : payload) {
            clearBytes(cursor, offset, destination);
            cursor = offset + width;
        }
        clearBytes(cursor, physical.reservedBytes, destination);
    }
    void clearObject(int base, const std::string &name) {
        clearPadding(name, [&](int byte) {
            return address(base - byte);
        });
        const auto &fields = classFields->at(name);
        const auto &physical = classStorage->at(name);
        for (std::size_t field = 0; field < fields.size(); ++field)
            if (fields[field].elementType.isBytes())
                clearBytesOwner(base - physical.fieldOffsets[field]);
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
    void beginStackFacts(const std::string &name) {
        liveStackBytes = 8;
        currentStackFacts = &emittedStackFacts.emplace(name, FunctionStackFacts{}).first->second;
    }
    void growStack(int bytes) {
        liveStackBytes += bytes;
        currentStackFacts->localBytes = std::max(currentStackFacts->localBytes, liveStackBytes);
    }
    void releaseStack(int bytes) {
        line("addq $" + std::to_string(bytes) + ", %rsp");
        liveStackBytes -= bytes;
    }
    void directCall(const std::string &name) {
        auto &live = currentStackFacts->calls[name];
        live = std::max(live, liveStackBytes);
        line("call " + name);
    }
    void reserveStack(int bytes) {
        growStack(bytes);
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
        growStack(8);
        ++stackDepth;
    }
    void pop(const std::string &target) {
        line("popq " + target);
        liveStackBytes -= 8;
        --stackDepth;
    }
    void call(const std::string &name) {
        if (stackDepth % 2) {
            line("subq $8, %rsp");
            growStack(8);
        }
        directCall(name);
        if (stackDepth % 2)
            releaseStack(8);
    }
    std::string querySymbol(ir::Query query, int scope) {
        const std::string name = query == ir::Query::Size ? "size" : "field_count";
        return scope == 0 ? "aurora_reflect_" + name : "__au_reflect_s" + std::to_string(scope) + "_" + name;
    }
    bool aggregateSignature(const ir::Function &function) const {
        if (function.result.isClass() || function.result.isBytes() || function.result.isSpan())
            return true;
        for (const auto &type : function.parameters)
            if (type.isClass() || type.isSpan() || type.isResource() || type.isService())
                return true;
        return false;
    }
    bool classParameters(const ir::Function &function) const {
        return std::any_of(function.parameters.begin(), function.parameters.end(), [](const Type &type) {
            return type.isClass() || type.isSpan();
        });
    }
    int argumentBytes(const Type &type) const {
        return type.isService() ? service::capabilityBytes
               : type.isBytes() ? 32
               : type.isClass() ? classStorage->at(type.className).reservedBytes
               : type.isSpan()  ? ir::spanBytes
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
    int packArguments(const ir::Function &target, const std::vector<int> &objects, const std::vector<int> &spans = {}) {
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
        clearBytes(recordOffset(target, target.parameters.size()), recordBytes, [](int byte) {
            return std::to_string(byte) + "(%rsp)";
        });
        for (std::size_t index = 0; index < target.parameters.size(); ++index) {
            const auto &type = target.parameters[index];
            const int offset = recordOffset(target, index);
            if (type.isSpan()) {
                for (int byte = 0; byte < ir::spanBytes; byte += 8) {
                    line("movq " + address(spans[index] - byte) + ", %rax");
                    line("movq %rax, " + std::to_string(offset + byte) + "(%rsp)");
                }
            } else if (!type.isClass())
                storeArgument(type, index, std::to_string(offset) + "(%rsp)");
            else {
                const auto &layout = classLayouts->at(type.className);
                const auto &offsets = classStorage->at(type.className).leafOffsets;
                copyLeaves(
                    layout,
                    offsets,
                    offsets,
                    [&](int byte) {
                        return address(objects[index] - byte);
                    },
                    [&](int byte) {
                        return std::to_string(offset + byte) + "(%rsp)";
                    },
                    CopyBases::StackDestination);
            }
        }
        line("movq %rsp, %r11");
        return recordBytes;
    }
    int packService(const ir::Function &target, const ir::ServiceCall &operation) {
        for (std::size_t reverse = target.parameters.size(); reverse > 0; --reverse)
            if (!target.parameters[reverse - 1].isSpan() && !target.parameters[reverse - 1].isService())
                pop(argumentRegisters[reverse - 1]);
        const int bytes = (recordOffset(target, target.parameters.size()) + 15) & ~15;
        reserveStack(bytes);
        for (int byte = 0; byte < bytes; byte += 8)
            line("movq $0, " + std::to_string(byte) + "(%rsp)");
        for (std::size_t index = 0; index < target.parameters.size(); ++index) {
            const int offset = recordOffset(target, index);
            if (target.parameters[index].isService()) {
                const int loan = index == 0 ? operation.loanId : operation.additionalServices.at(index - 1).loanId;
                const int capability = serviceLoanOffsets.at(loan);
                for (int byte = 0; byte < service::capabilityBytes; byte += 8) {
                    line("movq " + address(capability - byte) + ", %rax");
                    line("movq %rax, " + std::to_string(offset + byte) + "(%rsp)");
                }
            } else if (target.parameters[index].isSpan()) {
                for (int byte = 0; byte < ir::spanBytes; byte += 8) {
                    line("movq " + address(operation.spanArguments[index] - byte) + ", %rax");
                    line("movq %rax, " + std::to_string(offset + byte) + "(%rsp)");
                }
            } else
                storeArgument(target.parameters[index], index, std::to_string(offset) + "(%rsp)");
        }
        line("movq %rsp, %r11");
        return bytes;
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
    std::string bytesOwnerAddress(int offset, int fieldIndex, int byte = 0) {
        if (fieldIndex < 0)
            return address(offset - byte);
        const auto &name =
            offset == 0 ? currentFunction->receiver->className : currentFunction->objectSlots.at(offset).className;
        const int fieldOffset = classStorage->at(name).fieldOffsets[fieldIndex];
        if (offset != 0)
            return address(offset - fieldOffset - byte);
        line("movq " + address(receiverSaveOffset) + ", %r10");
        return std::to_string(fieldOffset + byte) + "(%r10)";
    }
    template <class Source, class Destination>
    void transferObject(const std::string &name, const Source &source, const Destination &destination) {
        const auto &layout = classLayouts->at(name);
        const auto &physical = classStorage->at(name);
        // Transfer scalar payload by its verified width, preserving the current
        // scalar value. Genuine padding stays with the destination reservation.
        for (std::size_t leaf = 0; leaf < layout.size(); ++leaf) {
            const int byte = physical.leafOffsets[leaf];
            const bool narrow = layout[leaf] == Type::U8;
            line(std::string(narrow ? "movzbq " : "movq ") + source(byte) + ", %rcx");
            line(std::string(narrow ? "movb %cl, " : "movq %rcx, ") + destination(byte));
        }
        const auto &fields = classFields->at(name);
        for (std::size_t field = 0; field < fields.size(); ++field) {
            if (!fields[field].elementType.isBytes())
                continue;
            const int offset = physical.fieldOffsets[field];
            for (int byte = 0; byte < 32; byte += 8) {
                line("movq " + source(offset + byte) + ", %rcx");
                line("movq %rcx, " + destination(offset + byte));
            }
            clearBytes(offset, offset + 32, source);
        }
    }
    void dropObject(int base, const std::string &name) {
        if (!ir::owningClass(*classFields, name))
            return;
        // A class lifetime owns each descriptor in reverse declaration order.
        // Preserve the pending scalar result and every outstanding operand.
        push();
        const auto &fields = classFields->at(name);
        const auto &physical = classStorage->at(name);
        for (std::size_t field = fields.size(); field > 0; --field)
            if (fields[field - 1].elementType.isBytes()) {
                line("leaq " + address(base - physical.fieldOffsets[field - 1]) + ", %rdi");
                call("__au_runtime_bytes_drop");
            }
        pop("%rax");
    }
    int packResources(const ir::Function &target, const ir::ResourceCall &operation) {
        for (std::size_t index = target.parameters.size(); index > 1; --index)
            if (!target.parameters[index - 1].isBytes() && !target.parameters[index - 1].isClass())
                pop(argumentRegisters[index - 1]);
        const int recordBytes = (recordOffset(target, target.parameters.size()) + 15) & ~15;
        reserveStack(recordBytes);
        clearBytes(0, recordBytes, [](int byte) {
            return std::to_string(byte) + "(%rsp)";
        });
        // Save scalar arguments before descriptor copying reuses scratch GPRs.
        for (std::size_t index = 1; index < target.parameters.size(); ++index)
            if (!target.parameters[index].isBytes() && !target.parameters[index].isClass())
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
            } else if (target.parameters[index].isClass()) {
                const int source = operation.ownerArguments[index];
                const int destination = recordOffset(target, index);
                transferObject(
                    target.parameters[index].className,
                    [&](int byte) {
                        return address(source - byte);
                    },
                    [&](int byte) {
                        return std::to_string(destination + byte) + "(%rsp)";
                    });
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
                if constexpr (std::is_same_v<Op, ir::AcquireObjectLoan> || std::is_same_v<Op, ir::ReleaseObjectLoan>) {
                    // Validated synchronous authority has no runtime ownership record.
                } else if constexpr (std::is_same_v<Op, ir::Constant>) {
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
                              "(%rcx,%rax," + std::to_string(ir::storageWidth(operation.elementType)) + ")");
                } else if constexpr (std::is_same_v<Op, ir::IndexStore>) {
                    pop("%rcx");
                    line("leaq " + address(operation.offset) + ", %rdx");
                    storeValue(operation.elementType,
                               "(%rdx,%rcx," + std::to_string(ir::storageWidth(operation.elementType)) + ")");
                } else if constexpr (std::is_same_v<Op, ir::BorrowHandle>) {
                    line("leaq " + address(operation.ownerOffset) + ", %rax");
                } else if constexpr (std::is_same_v<Op, ir::Call>) {
                    for (std::size_t index = argumentCounts.at(operation.callee); index > 0; --index)
                        pop(argumentRegisters[index - 1]);
                    call(operation.callee);
                } else if constexpr (std::is_same_v<Op, ir::AggregateCall>) {
                    const auto &target = *functions.at(operation.callee);
                    const int recordBytes = packArguments(target, operation.objectArguments, operation.spanArguments);
                    if (target.result.isClass())
                        line("leaq " + address(operation.resultOffset) + ", %r10");
                    call(operation.callee);
                    if (recordBytes)
                        releaseStack(recordBytes);
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
                    const auto value = bytesOwnerAddress(operation.offset, operation.fieldIndex, 24);
                    line("movq " + value + ", %rax");
                } else if constexpr (std::is_same_v<Op, ir::BytesLength>) {
                    const auto value = bytesOwnerAddress(operation.offset, operation.fieldIndex, 16);
                    line("movq " + value + ", %rax");
                } else if constexpr (std::is_same_v<Op, ir::BytesLoad>) {
                    // Canonical failed/empty owners have length zero. Unsigned
                    // comparison rejects negative and upper-bound indices too.
                    const auto length = bytesOwnerAddress(operation.offset, operation.fieldIndex, 16);
                    line("cmpq " + length + ", %rax");
                    line("jae .Laurora_bounds_trap");
                    line("movq %rax, %rsi");
                    const auto owner = bytesOwnerAddress(operation.offset, operation.fieldIndex);
                    line("leaq " + owner + ", %rdi");
                    call("__au_runtime_bytes_at");
                } else if constexpr (std::is_same_v<Op, ir::BytesStore>) {
                    line("movq %rax, %rdx");
                    pop("%rsi");
                    const auto owner = bytesOwnerAddress(operation.offset, operation.fieldIndex);
                    line("leaq " + owner + ", %rdi");
                    call("__au_runtime_bytes_set");
                } else if constexpr (std::is_same_v<Op, ir::BytesResize>) {
                    line("movq %rax, %rsi");
                    const auto owner = bytesOwnerAddress(operation.offset, operation.fieldIndex);
                    line("leaq " + owner + ", %rdi");
                    call("__au_runtime_bytes_resize");
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
                    if (target.receiver)
                        line("leaq " + address(operation.receiverOffset) + ", %r10");
                    else if (target.result.isBytes() || target.result.isClass())
                        line("leaq " + address(operation.resultOffset) + ", %r10");
                    call(operation.callee);
                    releaseStack(recordBytes);
                } else if constexpr (std::is_same_v<Op, ir::BindServiceParameter>) {
                    line("movq " + address(callRecordSaveOffset) + ", %r11");
                    for (int byte = 0; byte < service::capabilityBytes; byte += 8) {
                        line("movq " + std::to_string(recordOffset(*currentFunction, operation.index) + byte) +
                             "(%r11), %rax");
                        line("movq %rax, " + address(operation.offset - byte));
                    }
                } else if constexpr (std::is_same_v<Op, ir::AcquireServiceLoan>) {
                    // Static loan-to-root map is prepared before code emission.
                } else if constexpr (std::is_same_v<Op, ir::ReleaseServiceLoan>) {
                    // Static provenance is checked across joins independently.
                } else if constexpr (std::is_same_v<Op, ir::ServiceCall>) {
                    const auto &target = *functions.at(operation.callee);
                    const int recordBytes = packService(target, operation);
                    if (target.result.isClass())
                        line("leaq " + address(operation.resultOffset) + ", %r10");
                    call(operation.callee);
                    releaseStack(recordBytes);
                } else if constexpr (std::is_same_v<Op, ir::ServiceOperation>) {
                    line("movq " + address(operation.offset) + ", %rdi");
                    line("movq " + address(operation.offset - 8) + ", %rsi");
                    if (operation.operation == service::Operation::Pixel) {
                        pop("%r10"); // blue is the seventh host argument
                        pop("%r9");
                        pop("%r8");
                        pop("%rcx");
                        pop("%rdx");
                        const int outgoingBytes = stackDepth % 2 ? 8 : 16;
                        line("subq $" + std::to_string(outgoingBytes) + ", %rsp");
                        growStack(outgoingBytes);
                        line("movq %r10, (%rsp)");
                        directCall(std::string(service::description(operation.operation).hostSymbol));
                        releaseStack(outgoingBytes);
                        line("cmpq $1, %rax");
                        line("ja .Laurora_bounds_trap");
                    } else if (operation.operation == service::Operation::Put) {
                        line("movq %rax, %rdx");
                        call(std::string(service::description(operation.operation).hostSymbol));
                        line("cmpq $1, %rax");
                        line("ja .Laurora_bounds_trap");
                    } else if (operation.operation == service::Operation::IommuAcknowledge) {
                        call(std::string(service::description(operation.operation).hostSymbol));
                        line("cmpq $2, %rax");
                        line("ja .Laurora_bounds_trap");
                    } else if (operation.operation == service::Operation::IommuPoll) {
                        line("leaq " + address(operation.resultOffset) + ", %rdx");
                        // Private raw output is four complete qwords. None is
                        // published as source data until all channels validate.
                        for (int byte = 0; byte < 32; byte += 8)
                            line("movq $0, " + address(operation.resultOffset - byte));
                        call(std::string(service::description(operation.operation).hostSymbol));
                        line("cmpq $3, " + address(operation.resultOffset));
                        line("ja .Laurora_bounds_trap");
                        line("cmpq $31, " + address(operation.resultOffset - 24));
                        line("ja .Laurora_bounds_trap");
                        // Form an all-zero mask only for the record case. The
                        // full payload must be zero for every other result.
                        line("xorq %rax, %rax");
                        line("cmpq $1, " + address(operation.resultOffset));
                        line("setne %al");
                        line("negq %rax");
                        line("movq " + address(operation.resultOffset - 8) + ", %rcx");
                        line("orq " + address(operation.resultOffset - 16) + ", %rcx");
                        line("andq %rcx, %rax");
                        line("jne .Laurora_bounds_trap");
                    } else if (operation.operation == service::Operation::Next) {
                        line("leaq " + address(operation.resultOffset) + ", %rdx");
                        // Raw host report is three complete words; validation
                        // precedes publication as a copied bool/u8/bool object.
                        for (int byte = 0; byte < 24; byte += 8)
                            line("movq $0, " + address(operation.resultOffset - byte));
                        call(std::string(service::description(operation.operation).hostSymbol));
                        line("cmpq $1, " + address(operation.resultOffset));
                        line("ja .Laurora_bounds_trap");
                        line("cmpq $255, " + address(operation.resultOffset - 8));
                        line("ja .Laurora_bounds_trap");
                        line("cmpq $1, " + address(operation.resultOffset - 16));
                        line("ja .Laurora_bounds_trap");
                        line("movq " + address(operation.resultOffset) + ", %rax");
                        line("negq %rax");
                        line("notq %rax");
                        line("andq " + address(operation.resultOffset - 8) + ", %rax");
                        line("jne .Laurora_bounds_trap");
                    } else {
                        throw Error("unknown sealed service operation");
                    }
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
                    line("movq $0, " + address(operation.resultOffset));
                    line("leaq " + address(operation.arrayOffset) + ", %rcx");
                    line("movq %rcx, " + address(operation.resultOffset - 8));
                    for (int byte = 16; byte <= 40; byte += 8)
                        line("movq $0, " + address(operation.resultOffset - byte));
                    line("movq $" + std::to_string(currentFunction->arraySlots.at(operation.arrayOffset)) + ", " +
                         address(operation.resultOffset - 48));
                } else if constexpr (std::is_same_v<Op, ir::BorrowReceiverArraySpan>) {
                    const auto &name = currentFunction->receiver->className;
                    const auto &field = classFields->at(name).at(operation.fieldIndex);
                    const int byte = classStorage->at(name).fieldOffsets.at(operation.fieldIndex);
                    line("movq $0, " + address(operation.resultOffset));
                    line("movq " + address(receiverSaveOffset) + ", %rcx");
                    line("leaq " + std::to_string(byte) + "(%rcx), %rcx");
                    line("movq %rcx, " + address(operation.resultOffset - 8));
                    for (int padding = 16; padding <= 40; padding += 8)
                        line("movq $0, " + address(operation.resultOffset - padding));
                    line("movq $" + std::to_string(field.length) + ", " + address(operation.resultOffset - 48));
                } else if constexpr (std::is_same_v<Op, ir::BorrowLiteralSpan>) {
                    const std::string label = ".Laurora_literal_" + std::to_string(literalBytes.size());
                    literalBytes.push_back(operation.bytes);
                    line("movq $0, " + address(operation.resultOffset));
                    line("leaq " + label + "(%rip), %rcx");
                    line("movq %rcx, " + address(operation.resultOffset - 8));
                    for (int byte = 16; byte <= 40; byte += 8)
                        line("movq $0, " + address(operation.resultOffset - byte));
                    line("movq $" + std::to_string(operation.bytes.size()) + ", " +
                         address(operation.resultOffset - 48));
                } else if constexpr (std::is_same_v<Op, ir::BorrowOwnedSpan>) {
                    // Runtime validation distinguishes failed and valid-empty owners.
                    // Borrow acquisition must preserve an unrelated current scalar and
                    // every saved operand, including the call-alignment parity.
                    push();
                    const auto owner = bytesOwnerAddress(operation.offset, operation.fieldIndex);
                    line("leaq " + owner + ", %rdi");
                    call("__au_runtime_bytes_borrow_length");
                    line("movq %rax, " + address(operation.resultOffset - 48));
                    line("movq $1, " + address(operation.resultOffset));
                    for (int byte = 0; byte < 32; byte += 8) {
                        const auto word = bytesOwnerAddress(operation.offset, operation.fieldIndex, byte);
                        line("movq " + word + ", %rcx");
                        line("movq %rcx, " + address(operation.resultOffset - 8 - byte));
                    }
                    line("movq $0, " + address(operation.resultOffset - 40));
                    pop("%rax");
                } else if constexpr (std::is_same_v<Op, ir::ReborrowSpan>) {
                    for (int byte = 0; byte < ir::spanBytes; byte += 8) {
                        line("movq " + address(operation.sourceOffset - byte) + ", %rcx");
                        line("movq %rcx, " + address(operation.resultOffset - byte));
                    }
                } else if constexpr (std::is_same_v<Op, ir::Subspan>) {
                    pop("%rcx"); // checked offset; current %rax is count
                    line("movq " + address(operation.sourceOffset - 48) + ", %rdx");
                    line("cmpq %rdx, %rcx");
                    line("ja .Laurora_bounds_trap");
                    line("subq %rcx, %rdx");
                    line("cmpq %rdx, %rax");
                    line("ja .Laurora_bounds_trap");
                    for (int byte = 0; byte < ir::spanBytes; byte += 8) {
                        line("movq " + address(operation.sourceOffset - byte) + ", %rdx");
                        line("movq %rdx, " + address(operation.resultOffset - byte));
                    }
                    line("addq " + address(operation.sourceOffset - 40) + ", %rcx");
                    line("movq %rcx, " + address(operation.resultOffset - 40));
                    line("movq %rax, " + address(operation.resultOffset - 48));
                } else if constexpr (std::is_same_v<Op, ir::SpanLength>) {
                    line("movq " + address(operation.offset - 48) + ", %rax");
                } else if constexpr (std::is_same_v<Op, ir::SpanLoad>) {
                    line("cmpq " + address(operation.offset - 48) + ", %rax");
                    line("jae .Laurora_bounds_trap");
                    line("addq " + address(operation.offset - 40) + ", %rax");
                    const std::string suffix = std::to_string(functionIndex) + "_" + std::to_string(divisionIndex++);
                    const std::string array = ".Lspan_array_" + suffix;
                    const std::string done = ".Lspan_done_" + suffix;
                    if (ownedSpanRuntime) {
                        line("cmpq $0, " + address(operation.offset));
                        line("je " + array);
                        line("cmpq $1, " + address(operation.offset));
                        line("jne .Laurora_bounds_trap");
                        line("movq %rax, %rsi");
                        line("leaq " + address(operation.offset - 8) + ", %rdi");
                        call("__au_runtime_bytes_at");
                        line("jmp " + done);
                        output << array << ":\n";
                    }
                    line("movq " + address(operation.offset - 8) + ", %rcx");
                    line("movzbq (%rcx,%rax,1), %rax");
                    if (ownedSpanRuntime)
                        output << done << ":\n";
                } else if constexpr (std::is_same_v<Op, ir::ReturnSpan>) {
                    line("movq " + address(resultSaveOffset) + ", %r10");
                    for (int byte = 0; byte < ir::spanBytes; byte += 8) {
                        line("movq " + address(operation.offset - byte) + ", %rcx");
                        line("movq %rcx, " + std::to_string(byte) + "(%r10)");
                    }
                    line("xorq %rax, %rax");
                    line("jmp " + returnLabel());
                } else if constexpr (std::is_same_v<Op, ir::BeginObject>) {
                    clearObject(operation.offset, currentFunction->objectSlots.at(operation.offset).className);
                } else if constexpr (std::is_same_v<Op, ir::EndObject>) {
                    dropObject(operation.offset, currentFunction->objectSlots.at(operation.offset).className);
                } else if constexpr (std::is_same_v<Op, ir::MoveObject>) {
                    const auto &name = currentFunction->objectSlots.at(operation.sourceOffset).className;
                    transferObject(
                        name,
                        [&](int byte) {
                            return address(operation.sourceOffset - byte);
                        },
                        [&](int byte) {
                            return address(operation.resultOffset - byte);
                        });
                } else if constexpr (std::is_same_v<Op, ir::CopyObject>) {
                    const auto &name = currentFunction->objectSlots.at(operation.sourceOffset).className;
                    const auto &layout = classLayouts->at(name);
                    const auto &offsets = classStorage->at(name).leafOffsets;
                    copyLeaves(
                        layout,
                        offsets,
                        offsets,
                        [&](int byte) {
                            return address(operation.sourceOffset - byte);
                        },
                        [&](int byte) {
                            return address(operation.resultOffset - byte);
                        },
                        CopyBases::Stable);
                } else if constexpr (std::is_same_v<Op, ir::ObjectFieldCopy>) {
                    const ir::ClassField *field = nullptr;
                    const ir::ClassStorage *source = nullptr;
                    if (operation.sourceOffset == 0) {
                        field = &receiverField(operation.fieldIndex);
                        source = &receiverStorage();
                        line("movq " + address(receiverSaveOffset) + ", %r10");
                    } else {
                        const auto &name = currentFunction->objectSlots.at(operation.sourceOffset).className;
                        field = &classFields->at(name)[operation.fieldIndex];
                        source = &classStorage->at(name);
                        line("leaq " + address(operation.sourceOffset) + ", %r10");
                    }
                    const auto &layout = classLayouts->at(field->elementType.className);
                    copyLeaves(
                        layout,
                        std::span(source->leafOffsets).subspan(field->firstLeaf, field->length),
                        classStorage->at(field->elementType.className).leafOffsets,
                        [](int byte) {
                            return std::to_string(byte) + "(%r10)";
                        },
                        [&](int byte) {
                            return address(operation.resultOffset - byte);
                        },
                        CopyBases::Stable);
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
                    copyLeaves(
                        sourceLayout,
                        classStorage->at(field.elementType.className).leafOffsets,
                        std::span(destinationStorage.leafOffsets).subspan(field.firstLeaf, field.length),
                        [&](int byte) {
                            return address(operation.sourceOffset - byte);
                        },
                        [](int byte) {
                            return std::to_string(byte) + "(%r10)";
                        },
                        CopyBases::Stable);
                } else if constexpr (std::is_same_v<Op, ir::InitializeClassArray>) {
                    const auto &name = operation.objectOffset == 0
                                           ? currentFunction->receiver->className
                                           : currentFunction->objectSlots.at(operation.objectOffset).className;
                    const auto &field = classFields->at(name)[operation.fieldIndex];
                    const auto &layout = classLayouts->at(field.elementType.className);
                    const auto &child = classStorage->at(field.elementType.className);
                    const auto &storage = classStorage->at(name);
                    if (operation.objectOffset == 0)
                        line("movq " + address(receiverSaveOffset) + ", %r10");
                    else
                        line("leaq " + address(operation.objectOffset) + ", %r10");
                    for (std::size_t element = 0; element < operation.sources.size(); ++element) {
                        copyLeaves(
                            layout,
                            child.leafOffsets,
                            std::span(storage.leafOffsets)
                                .subspan(field.firstLeaf + element * layout.size(), layout.size()),
                            [&](int byte) {
                                return address(operation.sources[element] - byte);
                            },
                            [](int byte) {
                                return std::to_string(byte) + "(%r10)";
                            },
                            CopyBases::Stable);
                    }
                } else if constexpr (std::is_same_v<Op, ir::ClassArrayBoundsGuard>) {
                    const auto &name = operation.objectOffset == 0
                                           ? currentFunction->receiver->className
                                           : currentFunction->objectSlots.at(operation.objectOffset).className;
                    const auto &field = classFields->at(name)[operation.fieldIndex];
                    // Reject signed-negative and upper bounds before multiplying.
                    line("cmpq $" + std::to_string(field.elementCount) + ", %rax");
                    line("jae .Laurora_bounds_trap");
                } else if constexpr (std::is_same_v<Op, ir::ClassArrayCopy> ||
                                     std::is_same_v<Op, ir::ClassArrayAssign>) {
                    const auto &name = operation.objectOffset == 0
                                           ? currentFunction->receiver->className
                                           : currentFunction->objectSlots.at(operation.objectOffset).className;
                    const auto &field = classFields->at(name)[operation.fieldIndex];
                    const auto &layout = classLayouts->at(field.elementType.className);
                    const auto &child = classStorage->at(field.elementType.className);
                    // Canonical validated shape bounds both factors and the complete
                    // byte extent. No indexed pointer or receiver escapes this copy.
                    const int stride = child.leafOffsets.empty() ? 0 : child.sizeBytes;
                    line("imulq $" + std::to_string(stride) + ", %rax");
                    if (operation.objectOffset == 0)
                        line("movq " + address(receiverSaveOffset) + ", %r10");
                    else
                        line("leaq " + address(operation.objectOffset) + ", %r10");
                    line("leaq " + std::to_string(classStorage->at(name).fieldOffsets[operation.fieldIndex]) +
                         "(%r10,%rax), %r10");
                    if constexpr (std::is_same_v<Op, ir::ClassArrayCopy>) {
                        copyLeaves(
                            layout,
                            child.leafOffsets,
                            child.leafOffsets,
                            [](int byte) {
                                return std::to_string(byte) + "(%r10)";
                            },
                            [&](int byte) {
                                return address(operation.resultOffset - byte);
                            },
                            CopyBases::Stable);
                    } else {
                        copyLeaves(
                            layout,
                            child.leafOffsets,
                            child.leafOffsets,
                            [&](int byte) {
                                return address(operation.sourceOffset - byte);
                            },
                            [](int byte) {
                                return std::to_string(byte) + "(%r10)";
                            },
                            CopyBases::Stable);
                    }
                } else if constexpr (std::is_same_v<Op, ir::InitializeObjectField>) {
                    const auto &field = receiverField(operation.fieldIndex);
                    const auto &layout = classLayouts->at(field.elementType.className);
                    line("movq " + address(receiverSaveOffset) + ", %r10");
                    copyLeaves(
                        layout,
                        classStorage->at(field.elementType.className).leafOffsets,
                        std::span(receiverStorage().leafOffsets).subspan(field.firstLeaf, field.length),
                        [&](int byte) {
                            return address(operation.sourceOffset - byte);
                        },
                        [](int byte) {
                            return std::to_string(byte) + "(%r10)";
                        },
                        CopyBases::Stable);
                } else if constexpr (std::is_same_v<Op, ir::InitializeBytesField>) {
                    // Only a constructor's bound receiver is admitted here.
                    // Initializing one descriptor never copies sibling payload.
                    line("movq " + address(receiverSaveOffset) + ", %r10");
                    const int destination = receiverStorage().fieldOffsets[operation.fieldIndex];
                    for (int byte = 0; byte < 32; byte += 8) {
                        line("movq " + address(operation.sourceOffset - byte) + ", %rcx");
                        line("movq %rcx, " + std::to_string(destination + byte) + "(%r10)");
                    }
                    clearBytesOwner(operation.sourceOffset);
                } else if constexpr (std::is_same_v<Op, ir::ReceiverLoad>) {
                    line("movq " + address(receiverSaveOffset) + ", %r10");
                    loadValue(operation.type,
                              std::to_string(receiverStorage().fieldOffsets[operation.fieldIndex]) + "(%r10)");
                } else if constexpr (std::is_same_v<Op, ir::ReceiverStore>) {
                    line("movq " + address(receiverSaveOffset) + ", %r10");
                    storeValue(operation.type,
                               std::to_string(receiverStorage().fieldOffsets[operation.fieldIndex]) + "(%r10)");
                } else if constexpr (std::is_same_v<Op, ir::ReceiverArrayZero>) {
                    const auto &field = receiverField(operation.fieldIndex);
                    line("movq " + address(receiverSaveOffset) + ", %r10");
                    for (int element = 0; element < field.length; ++element)
                        line(std::string(field.elementType == Type::U8 ? "movb $0, " : "movq $0, ") +
                             std::to_string(receiverStorage().leafOffsets[field.firstLeaf + element]) + "(%r10)");
                } else if constexpr (std::is_same_v<Op, ir::ReceiverBoundsGuard>) {
                    const auto &field = receiverField(operation.fieldIndex);
                    // The unsigned comparison also rejects every negative i64 index.
                    line("cmpq $" + std::to_string(field.length) + ", %rax");
                    line("jae .Laurora_bounds_trap");
                } else if constexpr (std::is_same_v<Op, ir::ReceiverIndexLoad>) {
                    const auto &field = receiverField(operation.fieldIndex);
                    line("movq " + address(receiverSaveOffset) + ", %r10");
                    loadValue(field.elementType,
                              std::to_string(receiverStorage().fieldOffsets[operation.fieldIndex]) + "(%r10,%rax," +
                                  std::to_string(ir::storageWidth(field.elementType)) + ")");
                } else if constexpr (std::is_same_v<Op, ir::ReceiverIndexStore>) {
                    const auto &field = receiverField(operation.fieldIndex);
                    pop("%rcx");
                    line("movq " + address(receiverSaveOffset) + ", %r10");
                    storeValue(field.elementType,
                               std::to_string(receiverStorage().fieldOffsets[operation.fieldIndex]) + "(%r10,%rcx," +
                                   std::to_string(ir::storageWidth(field.elementType)) + ")");
                } else if constexpr (std::is_same_v<Op, ir::MethodCall> || std::is_same_v<Op, ir::BorrowedCall>) {
                    const auto &target = *functions.at(operation.callee);
                    const bool aggregate = classParameters(target);
                    const int recordBytes =
                        aggregate ? packArguments(target, operation.objectArguments, operation.spanArguments) : 0;
                    if (!aggregate)
                        for (std::size_t index = argumentCounts.at(operation.callee); index > 0; --index)
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
                    if (target.result.isClass() || target.result.isSpan())
                        line("leaq " + address(operation.resultOffset) + (aggregate ? ", %rax" : ", %r11"));
                    call(operation.callee);
                    if (recordBytes)
                        releaseStack(recordBytes);
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
                    const auto &offsets = classStorage->at(currentFunction->result.className).leafOffsets;
                    copyLeaves(
                        layout,
                        offsets,
                        offsets,
                        [&](int byte) {
                            return address(operation.offset - byte);
                        },
                        [](int byte) {
                            return std::to_string(byte) + "(%r10)";
                        },
                        CopyBases::Stable);
                    line("xorq %rax, %rax");
                    line("jmp " + returnLabel());
                } else if constexpr (std::is_same_v<Op, ir::ReturnOwnedObject>) {
                    line("movq " + address(resultSaveOffset) + ", %r10");
                    transferObject(
                        currentFunction->result.className,
                        [&](int byte) {
                            return address(operation.offset - byte);
                        },
                        [](int byte) {
                            return std::to_string(byte) + "(%r10)";
                        });
                    line("xorq %rax, %rax");
                    line("jmp " + returnLabel());
                } else if constexpr (std::is_same_v<Op, ir::BindParameter>) {
                    if (callRecordSaveOffset) {
                        line("movq " + address(callRecordSaveOffset) + ", %r11");
                        loadValue(operation.type,
                                  std::to_string(recordOffset(*currentFunction, operation.index)) + "(%r11)");
                        storeValue(operation.type, address(operation.offset));
                    } else
                        storeArgument(operation.type, operation.index, address(operation.offset));
                } else if constexpr (std::is_same_v<Op, ir::BindSpanParameter>) {
                    line("movq " + address(callRecordSaveOffset) + ", %r11");
                    const int offset = recordOffset(*currentFunction, operation.index);
                    for (int byte = 0; byte < ir::spanBytes; byte += 8) {
                        line("movq " + std::to_string(offset + byte) + "(%r11), %rax");
                        line("movq %rax, " + address(operation.offset - byte));
                    }
                } else if constexpr (std::is_same_v<Op, ir::BindObjectParameter>) {
                    line("movq " + address(callRecordSaveOffset) + ", %r11");
                    const auto &layout = classLayouts->at(operation.className);
                    const int offset = recordOffset(*currentFunction, operation.index);
                    clearObject(operation.offset, operation.className);
                    const auto &offsets = classStorage->at(operation.className).leafOffsets;
                    copyLeaves(
                        layout,
                        offsets,
                        offsets,
                        [&](int byte) {
                            return std::to_string(offset + byte) + "(%r11)";
                        },
                        [&](int byte) {
                            return address(operation.offset - byte);
                        },
                        CopyBases::Stable);
                } else if constexpr (std::is_same_v<Op, ir::BindOwnedObjectParameter>) {
                    line("movq " + address(callRecordSaveOffset) + ", %r11");
                    const int offset = recordOffset(*currentFunction, operation.index);
                    clearObject(operation.offset, operation.className);
                    transferObject(
                        operation.className,
                        [&](int byte) {
                            return std::to_string(offset + byte) + "(%r11)";
                        },
                        [&](int byte) {
                            return address(operation.offset - byte);
                        });
                } else {
                    static_assert(!std::is_same_v<Op, Op>, "unhandled typed IR backend operation");
                }
            },
            instruction);
    }

public:
    const std::map<std::string, FunctionStackFacts> &stackFacts() const {
        return emittedStackFacts;
    }
    std::string stackFactsJson() const {
        std::ostringstream facts;
        facts << "{\"version\":1,\"functions\":{";
        bool firstFunction = true;
        for (const auto &[symbol, usage] : emittedStackFacts) {
            if (!std::exchange(firstFunction, false))
                facts << ',';
            writeJsonString(facts, symbol);
            facts << ":{\"local_bytes\":" << usage.localBytes << ",\"calls\":{";
            bool firstCall = true;
            for (const auto &[callee, live] : usage.calls) {
                if (!std::exchange(firstCall, false))
                    facts << ',';
                writeJsonString(facts, callee);
                facts << ':' << live;
            }
            facts << "}}";
        }
        facts << "}}\n";
        return facts.str();
    }
    std::string emit(const ir::ValidatedModule &validated,
                     SymbolBinding binding = SymbolBinding::Default,
                     ReflectionEmission reflection = ReflectionEmission::All) {
        const auto &module = validated.get();
        output.str("");
        output.clear();
        argumentCounts.clear();
        functions.clear();
        literalBytes.clear();
        emittedStackFacts.clear();
        currentStackFacts = nullptr;
        classLayouts = &module.classLayouts;
        classFields = &module.classFields;
        classStorage = &module.classStorage;
        functionIndex = 0;
        for (const auto &function : module.functions) {
            argumentCounts[function.name] = function.parameters.size();
            functions[function.name] = &function;
        }
        std::set<std::string> referencedReflection;
        if (reflection == ReflectionEmission::Referenced)
            for (const auto &function : module.functions)
                for (const auto &instruction : function.code)
                    if (const auto *query = std::get_if<ir::MetadataQuery>(&instruction))
                        referencedReflection.insert(querySymbol(query->query, query->moduleScope));
        // Resource graphs link a trusted host adapter. No user-selected source
        // symbol may interpose its allocator, stdio or fail-stop dependencies.
        // Derive this from validated signatures/lifetime IR, never an input flag.
        const bool resourceGraph =
            std::any_of(module.classFields.begin(),
                        module.classFields.end(),
                        [&](const auto &entry) {
                            return ir::owningClass(module.classFields, entry.first);
                        }) ||
            std::any_of(module.functions.begin(), module.functions.end(), [&](const ir::Function &function) {
                return function.result.isResource() ||
                       (function.result.isClass() && ir::owningClass(module.classFields, function.result.className)) ||
                       (function.receiver && ir::owningClass(module.classFields, function.receiver->className)) ||
                       std::any_of(function.parameters.begin(),
                                   function.parameters.end(),
                                   [&](const Type &type) {
                                       return type.isResource() ||
                                              (type.isClass() && ir::owningClass(module.classFields, type.className));
                                   }) ||
                       std::any_of(function.code.begin(), function.code.end(), [](const ir::Instruction &op) {
                           return std::holds_alternative<ir::BeginBytes>(op) ||
                                  std::holds_alternative<ir::ResourceCall>(op) ||
                                  std::holds_alternative<ir::InitializeBytesField>(op) ||
                                  std::holds_alternative<ir::MoveObject>(op) ||
                                  std::holds_alternative<ir::BindOwnedObjectParameter>(op) ||
                                  std::holds_alternative<ir::ReturnOwnedObject>(op);
                       });
            });
        const bool serviceGraph =
            std::any_of(module.functions.begin(), module.functions.end(), [](const auto &function) {
                return std::any_of(function.parameters.begin(), function.parameters.end(), [](const Type &type) {
                    return type.isService();
                });
            });
        const bool privateGraph = resourceGraph || serviceGraph;
        ownedSpanRuntime = resourceGraph;
        output << "# Aurora compiler output: validated typed IR, x86-64 bootstrap\n.text\n";
        for (const auto &function : module.functions) {
            stackDepth = 0;
            beginStackFacts(function.name);
            serviceLoanOffsets.clear();
            for (const auto &operation : function.code)
                if (const auto *loan = std::get_if<ir::AcquireServiceLoan>(&operation))
                    serviceLoanOffsets.emplace(loan->loanId, loan->offset);
            divisionIndex = 0;
            currentFunction = &function;
            const bool aggregate = aggregateSignature(function);
            // Receiver and aggregate entry points use a private compiler ABI and cannot be
            // exposed as ordinary scalar-callable external symbols.
            output << (binding == SymbolBinding::Local || privateGraph || function.receiver || aggregate ||
                               function.name.starts_with("__au_o_")
                           ? ".local "
                           : ".globl ")
                   << function.name << "\n.type " << function.name << ", @function\n"
                   << function.name << ":\n";
            line("pushq %rbp");
            growStack(8);
            line("movq %rsp, %rbp");
            receiverSaveOffset = function.receiver ? function.frameBytes + 8 : 0;
            // Resource constructors always receive a packed record, even when
            // their explicit parameters contain no class values. Borrowed
            // ordinary methods retain their existing hidden-register modes.
            const bool resourceParameters = !function.parameters.empty() && function.parameters.front().isRegion();
            const bool packedArguments =
                function.receiver ? classParameters(function) || resourceParameters : aggregate;
            const bool combinedMethod =
                function.receiver && packedArguments && (function.result.isClass() || function.result.isSpan());
            callRecordSaveOffset = packedArguments ? function.frameBytes + (function.receiver ? 16 : 8) : 0;
            resultSaveOffset = (function.result.isClass() || function.result.isBytes() || function.result.isSpan())
                                   ? function.frameBytes + (combinedMethod ? 24 : 16)
                                   : 0;
            // Hidden capabilities never occupy source-addressable slots. The
            // new combined mode needs three distinct saves, rounded to 16-byte
            // alignment; every historical mode retains its original layout.
            const int frameBytes = function.frameBytes + (combinedMethod                   ? 32
                                                          : function.receiver || aggregate ? 16
                                                                                           : 0);
            reserveStack(frameBytes);
            if (function.receiver)
                line("movq %r10, " + address(receiverSaveOffset));
            if (packedArguments)
                line("movq %r11, " + address(callRecordSaveOffset));
            if (function.result.isClass() || function.result.isBytes() || function.result.isSpan())
                line(std::string("movq ") +
                     (combinedMethod      ? "%rax"
                      : function.receiver ? "%r11"
                                          : "%r10") +
                     ", " + address(resultSaveOffset));
            // Validation certifies operand-depth continuity in this exact retained
            // sequence, including branch joins. Outgoing reservations are balanced
            // inside each instruction; no instruction-text interpretation is used.
            for (const auto &operation : function.code)
                instruction(operation);
            if (stackDepth != 0 || liveStackBytes != frameBytes + 16)
                throw Error("x86 backend left an unbalanced stack reservation");
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
                if (reflection == ReflectionEmission::Referenced && !referencedReflection.contains(symbol))
                    continue;
                beginStackFacts(symbol);
                const std::string labelPrefix = ".Lscope" + std::to_string(scope) + "_" + name;
                output << (binding == SymbolBinding::Local ? ".local " : ".globl ") << symbol << "\n.type " << symbol
                       << ", @function\n"
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
                         std::to_string(query == ir::Query::Size ? descriptor.size : descriptor.publicFields) +
                         ", %rax");
                    line("ret");
                }
                output << ".size " << symbol << ", .-" << symbol << "\n";
            }
        }
        output << ".Laurora_bounds_trap:\n    ud2\n.Laurora_overflow_trap:\n    "
                  "ud2\n.Laurora_division_zero_trap:\n    ud2\n.Laurora_shift_count_trap:\n    ud2\n";
        if (!literalBytes.empty()) {
            output << ".section .rodata\n";
            for (std::size_t index = 0; index < literalBytes.size(); ++index) {
                output << ".Laurora_literal_" << index << ":\n";
                for (const auto byte : literalBytes[index])
                    output << "    .byte " << static_cast<unsigned>(byte) << '\n';
            }
        }
        output << ".section .note.GNU-stack,\"\",@progbits\n";
        return output.str();
    }
};
} // namespace aurora
