#pragma once
#include "ir_layout.hpp"
#include <algorithm>
#include <optional>
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
// This narrow ABI uses R11 for dense copied input and R10 for copied output.
// It describes trusted lowering, never permission to call an emitted symbol.
class CopiedRecordFacts {
public:
    std::vector<int> parameterBytes;
    int resultBytes;
};
class ServiceRecordFacts {
public:
    std::vector<std::pair<std::string, int>> parameters;
    int resultBytes;
};
class ServiceCallFacts {
public:
    int arguments, resultMax;
};
// Stack use follows the instructions emitted below, not a second ABI calculator.
// Like GCC .su, localBytes includes the incoming return address. Call-site bytes
// stop immediately before CALL; the callee's own incoming slot is counted there.
class FunctionStackFacts {
public:
    int localBytes = 8;
    std::map<std::string, int> calls;
    std::optional<CopiedRecordFacts> copiedRecord;
    std::optional<ServiceRecordFacts> serviceRecord;
    std::map<std::string, ServiceCallFacts> serviceCalls;
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
    bool directResult = false; // the next ValuesLoad writes the function result storage
    bool leftInRcx = false;    // the next binary operation's left operand is in %rcx, not pushed
    bool ownedSpanRuntime = false;
    std::map<int, int> serviceLoanOffsets;
    const ir::FunctionBody *currentFunction = nullptr;
    const ir::Metadata *metadata = nullptr;
    ir::CallableView currentCallable() const {
        return metadata->callable(currentFunction->callableId);
    }
    ir::FrameView currentFrame() const {
        return metadata->frame(currentFunction->callableId);
    }
    ir::TypeRange classLeaves(const std::string &name) const {
        return metadata->leaves(metadata->findClass(name).value());
    }
    ir::FieldRange logicalFields(const std::string &name) const {
        return metadata->fields(metadata->findClass(name).value());
    }
    ir::StorageView physicalStorage(const std::string &name) const {
        return metadata->storage(metadata->findClass(name).value());
    }
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
    void copyLeaves(ir::TypeRange leaves,
                    ir::IndexRange sourceOffsets,
                    ir::IndexRange destinationOffsets,
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
        return base - physicalStorage(currentFrame().objectSlots().at(base).className).leafOffsets.at(leaf);
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
        const auto physical = physicalStorage(name);
        const auto leaves = classLeaves(name);
        // Descriptors have no scalar leaves, but still occupy private payload
        // bytes. Clearing representation gaps must never clear a live owner.
        std::vector<std::pair<int, int>> payload;
        for (std::size_t leaf = 0; leaf < leaves.size(); ++leaf)
            payload.emplace_back(physical.leafOffsets[leaf], ir::storageWidth(leaves[leaf]));
        const auto fields = logicalFields(name);
        for (std::size_t field = 0; field < fields.size(); ++field)
            if (fields[field].elementType.isOwnerStorage())
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
        const auto fields = logicalFields(name);
        const auto physical = physicalStorage(name);
        for (std::size_t field = 0; field < fields.size(); ++field)
            if (fields[field].elementType.isOwnerStorage())
                clearBytesOwner(base - physical.fieldOffsets[field]);
    }
    std::string address(int offset) {
        return "-" + std::to_string(offset) + "(%rbp)";
    }
    int rootSaveOffset(std::size_t ordinal) const {
        const auto function = currentCallable();
        const auto count = function.borrowedParameter() ? function.borrowedRootCount()
                                                       : function.receiver() ? 1u : 0u;
        if (!receiverSaveOffset || ordinal >= count || ordinal >= 6)
            throw Error("x86 backend received an unbound object root ordinal");
        return receiverSaveOffset + static_cast<int>(ordinal) * 8;
    }
    void receiverAddress(int root, const std::string &target) {
        // Bound negative selectors before negation; none is a frame offset.
        // Ordinal saves survive nested R10/R11 clobbers and root permutations.
        if (root >= -5 && root <= 0)
            line("movq " + address(rootSaveOffset(static_cast<std::size_t>(-root))) + ", " + target);
        else if (root > 0)
            line("leaq " + address(root) + ", " + target);
        else
            throw Error("x86 backend received an unbound object root selector");
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
    bool aggregateSignature(ir::CallableView function) const {
        if (function.result().isClass() || function.result().isOwnerStorage() || function.result().isSpan())
            return true;
        for (const auto &type : function.parameters())
            if (type.isClass() || type.isSpan() || type.isResource() || type.isService())
                return true;
        return false;
    }
    bool classParameters(ir::CallableView function) const {
        const auto parameters = function.parameters();
        return std::any_of(parameters.begin(), parameters.end(), [](const Type &type) {
            return type.isClass() || type.isSpan();
        });
    }
    int argumentBytes(const Type &type) const {
        return type.isService()        ? service::capabilityBytes
               : type.isOwnerStorage() ? 32
               : type.isClass()        ? physicalStorage(type.className).reservedBytes
               : type.isSpan()         ? ir::spanBytes
                                       : 8;
    }
    int recordOffset(ir::CallableView function, std::size_t parameter) const {
        const auto parameters = function.parameters();
        int offset = 0;
        for (std::size_t index = 0; index < parameter; ++index)
            offset += argumentBytes(parameters[index]);
        return offset;
    }
    std::optional<CopiedRecordFacts> copiedRecordFacts(ir::CallableView function) const {
        if (function.receiver() || !function.result().isClass())
            return std::nullopt;
        const auto bytes = [&](const Type &type) {
            if (!type.isClass())
                return scalarValue(type) && ir::storageWidth(type) == 8 ? argumentBytes(type) : 0;
            if (ir::owningClass(*metadata, type.className))
                return 0;
            const auto physical = physicalStorage(type.className);
            const auto leaves = classLeaves(type.className);
            int cursor = 0;
            for (std::size_t leaf = 0; leaf < leaves.size(); ++leaf) {
                if (physical.leafOffsets[leaf] != cursor)
                    return 0;
                cursor += ir::storageWidth(leaves[leaf]);
            }
            return cursor == physical.reservedBytes ? argumentBytes(type) : 0;
        };
        CopiedRecordFacts facts{{}, bytes(function.result())};
        if (!facts.resultBytes)
            return std::nullopt;
        for (const auto &type : function.parameters()) {
            const int extent = bytes(type);
            if (!extent)
                return std::nullopt;
            facts.parameterBytes.push_back(extent);
        }
        return facts;
    }
    std::optional<ServiceRecordFacts> serviceRecordFacts(ir::CallableView function) const {
        const auto parameters = function.parameters();
        if (function.receiver() || !scalarValue(function.result()) ||
            std::none_of(parameters.begin(), parameters.end(), [](const Type &type) {
                return type.isService();
            }))
            return std::nullopt;
        ServiceRecordFacts facts{{}, ir::storageWidth(function.result())};
        for (const auto &type : parameters) {
            if (!type.isService() && !scalarValue(type))
                return std::nullopt;
            facts.parameters.emplace_back(type.isService() ? typeName(type) : "scalar", argumentBytes(type));
        }
        return facts;
    }
    void scalarServiceCompletion(service::Operation operation, int arguments, int maximum) {
        currentStackFacts->serviceCalls[std::string(service::description(operation).hostSymbol)] =
            ServiceCallFacts{arguments, maximum};
        line("cmpq $" + std::to_string(maximum) + ", %rax");
        line("ja .Laurora_bounds_trap");
    }
    ir::ClassField receiverField(int fieldIndex) const {
        const auto receiver = currentCallable().receiver();
        return logicalFields(receiver->className)[fieldIndex];
    }
    ir::StorageView receiverStorage() const {
        const auto receiver = currentCallable().receiver();
        return physicalStorage(receiver->className);
    }
    int packArguments(ir::CallableView target, ir::OffsetRange objects, ir::OffsetRange spans = {}) {
        const auto parameters = target.parameters();
        for (std::size_t index = parameters.size(); index > 0; --index)
            if (!parameters[index - 1].isClass() && !parameters[index - 1].isSpan())
                pop(argumentRegisters[index - 1]);
        const int recordBytes = (recordOffset(target, parameters.size()) + 15) & ~15;
        if (recordBytes)
            reserveStack(recordBytes);
        // Clear only representation gaps. Verified payload copies initialize
        // their own bytes; old all-word objects need no redundant zero stores.
        for (std::size_t index = 0; index < parameters.size(); ++index) {
            const auto type = parameters[index];
            const int offset = recordOffset(target, index);
            const auto destination = [&](int byte) {
                return std::to_string(offset + byte) + "(%rsp)";
            };
            if (type.isClass())
                clearPadding(type.className, destination);
            else if (!type.isSpan())
                clearBytes(ir::storageWidth(type), 8, destination);
        }
        clearBytes(recordOffset(target, parameters.size()), recordBytes, [](int byte) {
            return std::to_string(byte) + "(%rsp)";
        });
        for (std::size_t index = 0; index < parameters.size(); ++index) {
            const auto type = parameters[index];
            const int offset = recordOffset(target, index);
            if (type.isSpan()) {
                for (int byte = 0; byte < ir::spanBytes; byte += 8) {
                    line("movq " + address(spans[index] - byte) + ", %rax");
                    line("movq %rax, " + std::to_string(offset + byte) + "(%rsp)");
                }
            } else if (!type.isClass())
                storeArgument(type, index, std::to_string(offset) + "(%rsp)");
            else {
                const auto layout = classLeaves(type.className);
                const auto offsets = physicalStorage(type.className).leafOffsets;
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
    int packService(ir::CallableView target, const ir::ServiceCallObservation &operation) {
        const auto parameters = target.parameters();
        for (std::size_t reverse = parameters.size(); reverse > 0; --reverse)
            if (!parameters[reverse - 1].isSpan() && !parameters[reverse - 1].isService() &&
                !parameters[reverse - 1].isClass())
                pop(argumentRegisters[reverse - 1]);
        const int bytes = (recordOffset(target, parameters.size()) + 15) & ~15;
        reserveStack(bytes);
        for (int byte = 0; byte < bytes; byte += 8)
            line("movq $0, " + std::to_string(byte) + "(%rsp)");
        for (std::size_t index = 0; index < parameters.size(); ++index) {
            const int offset = recordOffset(target, index);
            if (parameters[index].isService()) {
                const int loan = index == 0 ? operation.loanId : operation.additionalServices.at(index - 1).loanId;
                const int capability = serviceLoanOffsets.at(loan);
                for (int byte = 0; byte < service::capabilityBytes; byte += 8) {
                    line("movq " + address(capability - byte) + ", %rax");
                    line("movq %rax, " + std::to_string(offset + byte) + "(%rsp)");
                }
            } else if (parameters[index].isSpan()) {
                for (int byte = 0; byte < ir::spanBytes; byte += 8) {
                    line("movq " + address(operation.spanArguments[index] - byte) + ", %rax");
                    line("movq %rax, " + std::to_string(offset + byte) + "(%rsp)");
                }
            } else if (parameters[index].isClass()) {
                const auto layout = classLeaves(parameters[index].className);
                const auto offsets = physicalStorage(parameters[index].className).leafOffsets;
                copyLeaves(
                    layout,
                    offsets,
                    offsets,
                    [&](int byte) {
                        return address(operation.objectArguments[index] - byte);
                    },
                    [&](int byte) {
                        return std::to_string(offset + byte) + "(%rsp)";
                    },
                    CopyBases::StackDestination);
            } else
                storeArgument(parameters[index], index, std::to_string(offset) + "(%rsp)");
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
    Type ownerStorageType(int offset, int fieldIndex) const {
        if (fieldIndex < 0) {
            const auto ownerTypes = currentFrame().ownedValueTypes();
            return ownerTypes.contains(offset) ? Type::ownedValues(Type(ownerTypes.at(offset))) : Type::OwnedBytes;
        }
        const auto receiver = currentCallable().receiver();
        const auto &name = offset == 0 ? receiver->className : currentFrame().objectSlots().at(offset).className;
        return logicalFields(name).at(fieldIndex).elementType;
    }
    int ownerElementStride(int offset, int fieldIndex) const {
        return physicalStorage(ownerStorageType(offset, fieldIndex).className).sizeBytes;
    }
    std::string bytesOwnerAddress(int offset, int fieldIndex, int byte = 0) {
        if (fieldIndex < 0)
            return address(offset - byte);
        const auto receiver = currentCallable().receiver();
        const auto &name = offset == 0 ? receiver->className : currentFrame().objectSlots().at(offset).className;
        const int fieldOffset = physicalStorage(name).fieldOffsets[fieldIndex];
        if (offset != 0)
            return address(offset - fieldOffset - byte);
        line("movq " + address(receiverSaveOffset) + ", %r10");
        return std::to_string(fieldOffset + byte) + "(%r10)";
    }
    template <class Source, class Destination>
    void transferObject(const std::string &name, const Source &source, const Destination &destination) {
        const auto layout = classLeaves(name);
        const auto physical = physicalStorage(name);
        // Transfer scalar payload by its verified width, preserving the current
        // scalar value. Genuine padding stays with the destination reservation.
        for (std::size_t leaf = 0; leaf < layout.size(); ++leaf) {
            const int byte = physical.leafOffsets[leaf];
            const bool narrow = layout[leaf] == Type::U8;
            line(std::string(narrow ? "movzbq " : "movq ") + source(byte) + ", %rcx");
            line(std::string(narrow ? "movb %cl, " : "movq %rcx, ") + destination(byte));
        }
        const auto fields = logicalFields(name);
        for (std::size_t field = 0; field < fields.size(); ++field) {
            if (!fields[field].elementType.isOwnerStorage())
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
        if (!ir::owningClass(*metadata, name))
            return;
        // A class lifetime owns each descriptor in reverse declaration order.
        // Preserve the pending scalar result and every outstanding operand.
        push();
        const auto fields = logicalFields(name);
        const auto physical = physicalStorage(name);
        for (std::size_t field = fields.size(); field > 0; --field)
            if (fields[field - 1].elementType.isOwnerStorage()) {
                line("leaq " + address(base - physical.fieldOffsets[field - 1]) + ", %rdi");
                call("__au_runtime_bytes_drop");
            }
        pop("%rax");
    }
    int packResources(ir::CallableView target, const ir::ResourceCallObservation &operation) {
        const auto parameters = target.parameters();
        for (std::size_t index = parameters.size(); index > 1; --index)
            if (!parameters[index - 1].isOwnerStorage() && !parameters[index - 1].isClass())
                pop(argumentRegisters[index - 1]);
        const int recordBytes = (recordOffset(target, parameters.size()) + 15) & ~15;
        reserveStack(recordBytes);
        clearBytes(0, recordBytes, [](int byte) {
            return std::to_string(byte) + "(%rsp)";
        });
        // Save scalar arguments before descriptor copying reuses scratch GPRs.
        for (std::size_t index = 1; index < parameters.size(); ++index)
            if (!parameters[index].isOwnerStorage() && !parameters[index].isClass())
                storeArgument(parameters[index], index, std::to_string(recordOffset(target, index)) + "(%rsp)");
        line("movq " + address(operation.regionOffset) + ", %rax");
        line("movq %rax, (%rsp)");
        for (std::size_t index = 1; index < parameters.size(); ++index)
            if (parameters[index].isOwnerStorage()) {
                const int source = operation.ownerArguments[index];
                const int destination = recordOffset(target, index);
                for (int byte = 0; byte < 32; byte += 8) {
                    line("movq " + address(source - byte) + ", %rax");
                    line("movq %rax, " + std::to_string(destination + byte) + "(%rsp)");
                }
                clearBytesOwner(source);
            } else if (parameters[index].isClass()) {
                const int source = operation.ownerArguments[index];
                const int destination = recordOffset(target, index);
                transferObject(
                    parameters[index].className,
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
    static bool plainLoad(const ir::InstructionObservation &operation) {
        return std::holds_alternative<ir::Constant>(operation) || std::holds_alternative<ir::EnumConstant>(operation) ||
               std::holds_alternative<ir::Load>(operation) || std::holds_alternative<ir::ReceiverLoad>(operation);
    }
    static bool poppedBinary(const ir::InstructionObservation &operation) {
        return std::holds_alternative<ir::BinaryValue>(operation) || std::holds_alternative<ir::Compare>(operation);
    }
    void instruction(const ir::InstructionObservation &instruction, ir::InstructionId instructionId) {
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
                    if (!leftInRcx)
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
                    if (!leftInRcx)
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
                    const auto target = metadata->callable(metadata->findCallable(operation.callee).value());
                    for (std::size_t index = target.parameters().size(); index > 0; --index)
                        pop(argumentRegisters[index - 1]);
                    call(operation.callee);
                } else if constexpr (std::is_same_v<Op, ir::AggregateCallObservation>) {
                    const auto target = metadata->callable(metadata->findCallable(operation.callee).value());
                    const int recordBytes = packArguments(target, operation.objectArguments, operation.spanArguments);
                    if (target.result().isClass())
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
                } else if constexpr (std::is_same_v<Op, ir::AllocateValues>) {
                    line("movq %rax, %rsi");
                    line("movq " + address(operation.regionOffset) + ", %rdi");
                    line("movq $" + std::to_string(ownerElementStride(operation.resultOffset, -1)) + ", %rdx");
                    line("leaq " + address(operation.fillOffset) + ", %rcx");
                    line("leaq " + address(operation.resultOffset) + ", %r8");
                    call("__au_runtime_values_allocate");
                } else if constexpr (std::is_same_v<Op, ir::ValuesLoad> || std::is_same_v<Op, ir::ValuesStore> ||
                                     std::is_same_v<Op, ir::ValuesResize>) {
                    line("movq %rax, %rsi");
                    if constexpr (std::is_same_v<Op, ir::ValuesLoad>) {
                        const auto length = bytesOwnerAddress(operation.offset, operation.fieldIndex, 16);
                        line("movq " + length + ", %rax");
                        line("movq $" + std::to_string(ownerElementStride(operation.offset, operation.fieldIndex)) +
                             ", %rcx");
                        line("xorq %rdx, %rdx");
                        line("divq %rcx");
                        line("cmpq %rax, %rsi");
                        line("jae .Laurora_bounds_trap");
                    }
                    const auto owner = bytesOwnerAddress(operation.offset, operation.fieldIndex);
                    line("leaq " + owner + ", %rdi");
                    line("movq $" + std::to_string(ownerElementStride(operation.offset, operation.fieldIndex)) +
                         ", %rdx");
                    if constexpr (std::is_same_v<Op, ir::ValuesLoad>) {
                        if (directResult)
                            line("movq " + address(resultSaveOffset) + ", %rcx");
                        else
                            line("leaq " + address(operation.resultOffset) + ", %rcx");
                        call("__au_runtime_values_at");
                    } else if constexpr (std::is_same_v<Op, ir::ValuesStore>) {
                        line("leaq " + address(operation.valueOffset) + ", %rcx");
                        call("__au_runtime_values_set");
                    } else {
                        line("leaq " + address(operation.fillOffset) + ", %rcx");
                        call("__au_runtime_values_resize");
                    }
                } else if constexpr (std::is_same_v<Op, ir::MoveBytes>) {
                    moveBytesOwner(operation.sourceOffset, operation.resultOffset);
                } else if constexpr (std::is_same_v<Op, ir::BytesOk>) {
                    const auto value = bytesOwnerAddress(operation.offset, operation.fieldIndex, 24);
                    line("movq " + value + ", %rax");
                } else if constexpr (std::is_same_v<Op, ir::BytesLength>) {
                    const auto value = bytesOwnerAddress(operation.offset, operation.fieldIndex, 16);
                    line("movq " + value + ", %rax");
                    if (ownerStorageType(operation.offset, operation.fieldIndex).isOwnedValues()) {
                        line("movq $" + std::to_string(ownerElementStride(operation.offset, operation.fieldIndex)) +
                             ", %rcx");
                        line("xorq %rdx, %rdx");
                        line("divq %rcx");
                    }
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
                } else if constexpr (std::is_same_v<Op, ir::ResourceCallObservation>) {
                    const auto target = metadata->callable(metadata->findCallable(operation.callee).value());
                    const int recordBytes = packResources(target, operation);
                    if (target.receiver())
                        line("leaq " + address(operation.receiverOffset) + ", %r10");
                    else if (target.result().isOwnerStorage() || target.result().isClass())
                        line("leaq " + address(operation.resultOffset) + ", %r10");
                    call(operation.callee);
                    releaseStack(recordBytes);
                } else if constexpr (std::is_same_v<Op, ir::BindServiceParameter>) {
                    line("movq " + address(callRecordSaveOffset) + ", %r11");
                    for (int byte = 0; byte < service::capabilityBytes; byte += 8) {
                        line("movq " + std::to_string(recordOffset(currentCallable(), operation.index) + byte) +
                             "(%r11), %rax");
                        line("movq %rax, " + address(operation.offset - byte));
                    }
                } else if constexpr (std::is_same_v<Op, ir::AcquireServiceLoan>) {
                    // Static loan-to-root map is prepared before code emission.
                } else if constexpr (std::is_same_v<Op, ir::ReleaseServiceLoan>) {
                    // Static provenance is checked across joins independently.
                } else if constexpr (std::is_same_v<Op, ir::ServiceCallObservation>) {
                    const auto target = metadata->callable(metadata->findCallable(operation.callee).value());
                    const int recordBytes = packService(target, operation);
                    if (target.result().isClass())
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
                        scalarServiceCompletion(operation.operation, 7, 1);
                    } else if (operation.operation == service::Operation::Put) {
                        line("movq %rax, %rdx");
                        call(std::string(service::description(operation.operation).hostSymbol));
                        scalarServiceCompletion(operation.operation, 3, 1);
                    } else if (operation.operation == service::Operation::IommuAcknowledge) {
                        call(std::string(service::description(operation.operation).hostSymbol));
                        scalarServiceCompletion(operation.operation, 2, 2);
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
                    const int source = recordOffset(currentCallable(), operation.index);
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
                    line("movq $" + std::to_string(currentFrame().arraySlots().at(operation.arrayOffset)) + ", " +
                         address(operation.resultOffset - 48));
                } else if constexpr (std::is_same_v<Op, ir::BorrowReceiverArraySpan>) {
                    const auto receiver = currentCallable().receiver();
                    const auto &name = receiver->className;
                    const auto field = logicalFields(name).at(operation.fieldIndex);
                    const int byte = physicalStorage(name).fieldOffsets.at(operation.fieldIndex);
                    line("movq $0, " + address(operation.resultOffset));
                    line("movq " + address(receiverSaveOffset) + ", %rcx");
                    line("leaq " + std::to_string(byte) + "(%rcx), %rcx");
                    line("movq %rcx, " + address(operation.resultOffset - 8));
                    for (int padding = 16; padding <= 40; padding += 8)
                        line("movq $0, " + address(operation.resultOffset - padding));
                    line("movq $" + std::to_string(field.length) + ", " + address(operation.resultOffset - 48));
                } else if constexpr (std::is_same_v<Op, ir::BorrowLiteralSpanObservation>) {
                    const std::string label = ".Laurora_literal_" + std::to_string(instructionId);
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
                    clearObject(operation.offset, currentFrame().objectSlots().at(operation.offset).className);
                } else if constexpr (std::is_same_v<Op, ir::InitializeEmptyObject>) {
                    // Verified explicit empty value completion; BeginObject
                    // already initialized all canonical representation padding.
                } else if constexpr (std::is_same_v<Op, ir::EndObject>) {
                    dropObject(operation.offset, currentFrame().objectSlots().at(operation.offset).className);
                } else if constexpr (std::is_same_v<Op, ir::MoveObject>) {
                    const auto &name = currentFrame().objectSlots().at(operation.sourceOffset).className;
                    transferObject(
                        name,
                        [&](int byte) {
                            return address(operation.sourceOffset - byte);
                        },
                        [&](int byte) {
                            return address(operation.resultOffset - byte);
                        });
                } else if constexpr (std::is_same_v<Op, ir::CopyObject>) {
                    const auto &name = currentFrame().objectSlots().at(operation.sourceOffset).className;
                    const auto layout = classLeaves(name);
                    const auto offsets = physicalStorage(name).leafOffsets;
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
                    ir::ClassField field{};
                    ir::StorageView source;
                    if (operation.sourceOffset == 0) {
                        field = receiverField(operation.fieldIndex);
                        source = receiverStorage();
                        line("movq " + address(receiverSaveOffset) + ", %r10");
                    } else {
                        const auto &name = currentFrame().objectSlots().at(operation.sourceOffset).className;
                        field = logicalFields(name)[operation.fieldIndex];
                        source = physicalStorage(name);
                        line("leaq " + address(operation.sourceOffset) + ", %r10");
                    }
                    const auto layout = classLeaves(field.elementType.className);
                    copyLeaves(
                        layout,
                        source.leafOffsets.subrange(field.firstLeaf, field.length),
                        physicalStorage(field.elementType.className).leafOffsets,
                        [](int byte) {
                            return std::to_string(byte) + "(%r10)";
                        },
                        [&](int byte) {
                            return address(operation.resultOffset - byte);
                        },
                        CopyBases::Stable);
                } else if constexpr (std::is_same_v<Op, ir::AssignObjectField>) {
                    const auto receiver = currentCallable().receiver();
                    const auto &name = operation.objectOffset == 0
                                           ? receiver->className
                                           : currentFrame().objectSlots().at(operation.objectOffset).className;
                    const auto field = logicalFields(name)[operation.fieldIndex];
                    const auto sourceLayout = classLeaves(field.elementType.className);
                    const auto destinationStorage = physicalStorage(name);
                    if (operation.objectOffset == 0)
                        line("movq " + address(receiverSaveOffset) + ", %r10");
                    else
                        line("leaq " + address(operation.objectOffset) + ", %r10");
                    copyLeaves(
                        sourceLayout,
                        physicalStorage(field.elementType.className).leafOffsets,
                        destinationStorage.leafOffsets.subrange(field.firstLeaf, field.length),
                        [&](int byte) {
                            return address(operation.sourceOffset - byte);
                        },
                        [](int byte) {
                            return std::to_string(byte) + "(%r10)";
                        },
                        CopyBases::Stable);
                } else if constexpr (std::is_same_v<Op, ir::InitializeClassArrayObservation>) {
                    const auto receiver = currentCallable().receiver();
                    const auto &name = operation.objectOffset == 0
                                           ? receiver->className
                                           : currentFrame().objectSlots().at(operation.objectOffset).className;
                    const auto field = logicalFields(name)[operation.fieldIndex];
                    const auto layout = classLeaves(field.elementType.className);
                    const auto child = physicalStorage(field.elementType.className);
                    const auto storage = physicalStorage(name);
                    if (operation.objectOffset == 0)
                        line("movq " + address(receiverSaveOffset) + ", %r10");
                    else
                        line("leaq " + address(operation.objectOffset) + ", %r10");
                    for (std::size_t element = 0; element < operation.sources.size(); ++element) {
                        copyLeaves(
                            layout,
                            child.leafOffsets,
                            storage.leafOffsets.subrange(field.firstLeaf + element * layout.size(), layout.size()),
                            [&](int byte) {
                                return address(operation.sources[element] - byte);
                            },
                            [](int byte) {
                                return std::to_string(byte) + "(%r10)";
                            },
                            CopyBases::Stable);
                    }
                } else if constexpr (std::is_same_v<Op, ir::ClassArrayBoundsGuard>) {
                    const auto receiver = currentCallable().receiver();
                    const auto &name = operation.objectOffset == 0
                                           ? receiver->className
                                           : currentFrame().objectSlots().at(operation.objectOffset).className;
                    const auto field = logicalFields(name)[operation.fieldIndex];
                    // Reject signed-negative and upper bounds before multiplying.
                    line("cmpq $" + std::to_string(field.elementCount) + ", %rax");
                    line("jae .Laurora_bounds_trap");
                } else if constexpr (std::is_same_v<Op, ir::ClassArrayCopy> ||
                                     std::is_same_v<Op, ir::ClassArrayAssign>) {
                    const auto receiver = currentCallable().receiver();
                    const auto &name = operation.objectOffset == 0
                                           ? receiver->className
                                           : currentFrame().objectSlots().at(operation.objectOffset).className;
                    const auto field = logicalFields(name)[operation.fieldIndex];
                    const auto layout = classLeaves(field.elementType.className);
                    const auto child = physicalStorage(field.elementType.className);
                    // Canonical validated shape bounds both factors and the complete
                    // byte extent. No indexed pointer or receiver escapes this copy.
                    const int stride = child.leafOffsets.empty() ? 0 : child.sizeBytes;
                    line("imulq $" + std::to_string(stride) + ", %rax");
                    if (operation.objectOffset == 0)
                        line("movq " + address(receiverSaveOffset) + ", %r10");
                    else
                        line("leaq " + address(operation.objectOffset) + ", %r10");
                    line("leaq " + std::to_string(physicalStorage(name).fieldOffsets[operation.fieldIndex]) +
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
                    const auto field = receiverField(operation.fieldIndex);
                    const auto layout = classLeaves(field.elementType.className);
                    line("movq " + address(receiverSaveOffset) + ", %r10");
                    copyLeaves(
                        layout,
                        physicalStorage(field.elementType.className).leafOffsets,
                        receiverStorage().leafOffsets.subrange(field.firstLeaf, field.length),
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
                    const auto field = receiverField(operation.fieldIndex);
                    line("movq " + address(receiverSaveOffset) + ", %r10");
                    for (int element = 0; element < field.length; ++element)
                        line(std::string(field.elementType == Type::U8 ? "movb $0, " : "movq $0, ") +
                             std::to_string(receiverStorage().leafOffsets[field.firstLeaf + element]) + "(%r10)");
                } else if constexpr (std::is_same_v<Op, ir::ReceiverBoundsGuard>) {
                    const auto field = receiverField(operation.fieldIndex);
                    // The unsigned comparison also rejects every negative i64 index.
                    line("cmpq $" + std::to_string(field.length) + ", %rax");
                    line("jae .Laurora_bounds_trap");
                } else if constexpr (std::is_same_v<Op, ir::ReceiverIndexLoad>) {
                    const auto field = receiverField(operation.fieldIndex);
                    line("movq " + address(receiverSaveOffset) + ", %r10");
                    loadValue(field.elementType,
                              std::to_string(receiverStorage().fieldOffsets[operation.fieldIndex]) + "(%r10,%rax," +
                                  std::to_string(ir::storageWidth(field.elementType)) + ")");
                } else if constexpr (std::is_same_v<Op, ir::ReceiverIndexStore>) {
                    const auto field = receiverField(operation.fieldIndex);
                    pop("%rcx");
                    line("movq " + address(receiverSaveOffset) + ", %r10");
                    storeValue(field.elementType,
                               std::to_string(receiverStorage().fieldOffsets[operation.fieldIndex]) + "(%r10,%rcx," +
                                   std::to_string(ir::storageWidth(field.elementType)) + ")");
                } else if constexpr (std::is_same_v<Op, ir::MethodCallObservation> ||
                                     std::is_same_v<Op, ir::BorrowedCallObservation>) {
                    const auto target = metadata->callable(metadata->findCallable(operation.callee).value());
                    const bool aggregate = classParameters(target);
                    const int recordBytes =
                        aggregate ? packArguments(target, operation.objectArguments, operation.spanArguments) : 0;
                    if (!aggregate)
                        for (std::size_t index = target.parameters().size(); index > 0; --index)
                            pop(argumentRegisters[index - 1]);
                    int borrowedRecordBytes = 0;
                    if constexpr (std::is_same_v<Op, ir::BorrowedCallObservation>) {
                        const auto rootCount = target.borrowedRootCount();
                        if (rootCount < 1 || rootCount > 6 || operation.roots.size() != rootCount)
                            throw Error("x86 backend received a mismatched borrowed root prefix");
                        if (rootCount > 1) {
                            // Payload and reservation are distinct for odd counts.
                            // The scalar operand stack and tail register order stay
                            // unchanged; only R10 is scratch while packing roots.
                            borrowedRecordBytes = (static_cast<int>(rootCount) * 8 + 15) & ~15;
                            reserveStack(borrowedRecordBytes);
                            for (std::size_t ordinal = 0; ordinal < rootCount; ++ordinal) {
                                receiverAddress(operation.roots[ordinal].root, "%r10");
                                line("movq %r10, " + std::to_string(ordinal * 8) + "(%rsp)");
                            }
                            line("leaq (%rsp), %r10");
                        } else {
                            receiverAddress(operation.roots.front().root, "%r10");
                        }
                    } else {
                        receiverAddress(operation.receiverOffset, "%r10");
                        if (operation.receiverFieldIndex >= 0) {
                            const auto receiver = currentCallable().receiver();
                            const auto &name = operation.receiverOffset == 0
                                                   ? receiver->className
                                                   : currentFrame().objectSlots().at(operation.receiverOffset).className;
                            const int fieldOffset = physicalStorage(name).fieldOffsets[operation.receiverFieldIndex];
                            if (fieldOffset != 0)
                                line("addq $" + std::to_string(fieldOffset) + ", %r10");
                        }
                    }
                    if (target.result().isClass() || target.result().isSpan())
                        line("leaq " + address(operation.resultOffset) + (aggregate ? ", %rax" : ", %r11"));
                    call(operation.callee);
                    if (borrowedRecordBytes)
                        releaseStack(borrowedRecordBytes);
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
                    const auto layout = classLeaves(currentCallable().result().className);
                    const auto offsets = physicalStorage(currentCallable().result().className).leafOffsets;
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
                        currentCallable().result().className,
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
                                  std::to_string(recordOffset(currentCallable(), operation.index)) + "(%r11)");
                        storeValue(operation.type, address(operation.offset));
                    } else
                        storeArgument(operation.type, operation.index, address(operation.offset));
                } else if constexpr (std::is_same_v<Op, ir::BindSpanParameter>) {
                    line("movq " + address(callRecordSaveOffset) + ", %r11");
                    const int offset = recordOffset(currentCallable(), operation.index);
                    for (int byte = 0; byte < ir::spanBytes; byte += 8) {
                        line("movq " + std::to_string(offset + byte) + "(%r11), %rax");
                        line("movq %rax, " + address(operation.offset - byte));
                    }
                } else if constexpr (std::is_same_v<Op, ir::BindObjectParameter>) {
                    line("movq " + address(callRecordSaveOffset) + ", %r11");
                    const auto layout = classLeaves(operation.className);
                    const int offset = recordOffset(currentCallable(), operation.index);
                    clearObject(operation.offset, operation.className);
                    const auto offsets = physicalStorage(operation.className).leafOffsets;
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
                    const int offset = recordOffset(currentCallable(), operation.index);
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
        facts << "{\"version\":2,\"functions\":{";
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
            facts << "},\"copied_record\":";
            if (usage.copiedRecord) {
                facts << "{\"parameter_bytes\":[";
                bool firstParameter = true;
                for (const int bytes : usage.copiedRecord->parameterBytes) {
                    if (!std::exchange(firstParameter, false))
                        facts << ',';
                    facts << bytes;
                }
                facts << "],\"result_bytes\":" << usage.copiedRecord->resultBytes << '}';
            } else
                facts << "null";
            if (usage.serviceRecord || !usage.serviceCalls.empty()) {
                facts << ",\"service_abi\":{\"record\":";
                if (usage.serviceRecord) {
                    facts << "{\"parameters\":[";
                    bool first = true;
                    for (const auto &[kind, bytes] : usage.serviceRecord->parameters) {
                        if (!std::exchange(first, false))
                            facts << ',';
                        facts << '[';
                        writeJsonString(facts, kind);
                        facts << ',' << bytes << ']';
                    }
                    facts << "],\"result_bytes\":" << usage.serviceRecord->resultBytes << '}';
                } else
                    facts << "null";
                facts << ",\"calls\":{";
                bool first = true;
                for (const auto &[callee, call] : usage.serviceCalls) {
                    if (!std::exchange(first, false))
                        facts << ',';
                    writeJsonString(facts, callee);
                    facts << ":{\"sysv_arguments\":" << call.arguments << ",\"result_max\":" << call.resultMax << '}';
                }
                facts << "}}";
            }
            facts << '}';
        }
        facts << "}}\n";
        return facts.str();
    }
    // This sidecar describes the exact validated module emitted by this instance.
    // It is data for private adapters, not a second storage/calling-convention calculator.
    std::string abiFactsJson(const ir::ValidatedModule &validated, const auto &declarations) const {
        const auto &module = validated.get();
        if (metadata != &validated.metadata())
            throw Error("ABI facts require the same emitted module");
        std::ostringstream facts;
        const auto type = [&](const Type &value) {
            std::string kind = value.isClass()          ? "class"
                               : value.isEnum()         ? "enum"
                               : value.isSpan()         ? "span"
                               : value.isOwnerStorage() ? "owner"
                               : value.isService()      ? "service"
                               : value.isRegion()       ? "region"
                               : value == Type::U8      ? "u8"
                               : value == Type::U64     ? "u64"
                               : value == Type::Bool    ? "bool"
                               : value == Type::I64     ? "i64"
                               : value == Type::Own     ? "own"
                               : value == Type::Ref     ? "ref"
                               : value == Type::MutRef  ? "mutref"
                                                        : "";
            if (kind.empty())
                throw Error("unsupported type in ABI facts");
            facts << "\"kind\":";
            writeJsonString(facts, kind);
            if (value.isClass() || value.isEnum()) {
                facts << ",\"type_name\":";
                writeJsonString(facts, value.className);
            }
        };
        facts << "{\"version\":2,\"span_bytes\":" << ir::spanBytes << ",\"records\":{";
        bool first = true;
        for (const auto &[symbol, declaration] : declarations.records) {
            const auto layout = physicalStorage(symbol);
            const auto fields = logicalFields(symbol);
            if (fields.size() != declaration.members.size())
                throw Error("ABI field names do not match validated storage");
            if (!std::exchange(first, false))
                facts << ',';
            writeJsonString(facts, symbol);
            facts << ":{\"source_name\":";
            writeJsonString(facts, declaration.sourceName);
            facts << ",\"size\":" << layout.sizeBytes << ",\"alignment\":" << layout.alignment
                  << ",\"reserved\":" << layout.reservedBytes << ",\"fields\":[";
            for (std::size_t index = 0; index < fields.size(); ++index) {
                const auto field = fields[index];
                if (index)
                    facts << ',';
                int width = ir::storageWidth(field.elementType);
                int count = field.array ? field.length : 1;
                if (field.elementType.isOwnerStorage())
                    width = argumentBytes(field.elementType);
                if (field.elementType.isClass()) {
                    const auto child = physicalStorage(field.elementType.className);
                    width = child.leafOffsets.empty() ? 0 : child.sizeBytes;
                    count = field.array ? field.elementCount : 1;
                }
                facts << "{\"name\":";
                writeJsonString(facts, declaration.members[index]);
                facts << ",\"offset\":" << layout.fieldOffsets.at(index) << ",\"bytes\":" << width * count
                      << ",\"array_length\":" << (field.array ? count : 0) << ',';
                type(field.elementType);
                facts << '}';
            }
            facts << "]}";
        }
        facts << "},\"enums\":{";
        first = true;
        for (const auto &[symbol, declaration] : declarations.enums) {
            if (metadata->enumCases(metadata->findEnum(symbol).value()) !=
                static_cast<int>(declaration.members.size()))
                throw Error("ABI enum names do not match validated cases");
            if (!std::exchange(first, false))
                facts << ',';
            writeJsonString(facts, symbol);
            facts << ":{\"source_name\":";
            writeJsonString(facts, declaration.sourceName);
            facts << ",\"cases\":{";
            for (std::size_t index = 0; index < declaration.members.size(); ++index) {
                if (index)
                    facts << ',';
                writeJsonString(facts, declaration.members[index]);
                facts << ':' << index;
            }
            facts << "}}";
        }
        facts << "},\"functions\":{";
        first = true;
        for (const auto &body : module.functions) {
            const auto function = metadata->callable(body.callableId);
            const auto receiver = function.receiver();
            const auto borrowedRootCount = function.borrowedRootCount();
            const auto declaration = declarations.functions.find(function.name());
            if (declaration == declarations.functions.end())
                continue;
            if (!std::exchange(first, false))
                facts << ',';
            writeJsonString(facts, function.name());
            facts << ":{\"source_name\":";
            writeJsonString(facts, declaration->second.sourceName);
            facts << ",\"receiver\":";
            if (receiver && !borrowedRootCount)
                writeJsonString(facts, receiver->className);
            else
                facts << "null";
            facts << ",\"receiver_mutable\":";
            facts << (receiver && !borrowedRootCount ? (receiver->mutableValue ? "true" : "false") : "null");
            facts << ",\"borrowed_root_count\":" << borrowedRootCount << ",\"borrowed_roots\":[";
            for (std::size_t ordinal = 0; ordinal < borrowedRootCount; ++ordinal) {
                if (ordinal)
                    facts << ',';
                facts << "{\"ordinal\":" << ordinal << ",\"selector\":" << -static_cast<int>(ordinal)
                      << ",\"type_name\":";
                writeJsonString(facts, function.borrowedRootType(ordinal).className);
                facts << ",\"mutable\":" << (function.borrowedRootMutable(ordinal) ? "true" : "false") << '}';
            }
            const int tuplePayloadBytes = borrowedRootCount > 1 ? static_cast<int>(borrowedRootCount) * 8 : 0;
            const int tupleReservedBytes = (tuplePayloadBytes + 15) & ~15;
            const int rootSaveBytes = (static_cast<int>(borrowedRootCount) * 8 + 15) & ~15;
            facts << "],\"borrowed_root_abi\":{\"kind\":";
            writeJsonString(facts, !borrowedRootCount ? "none" : borrowedRootCount == 1 ? "direct" : "tuple");
            facts << ",\"register\":" << (borrowedRootCount ? "\"r10\"" : "null")
                  << ",\"tuple_payload_bytes\":" << tuplePayloadBytes
                  << ",\"tuple_reserved_bytes\":" << tupleReservedBytes
                  << ",\"saved_root_reserved_bytes\":" << rootSaveBytes << '}';
            facts << ",\"parameter_bytes\":" << recordOffset(function, function.parameters().size())
                  << ",\"parameters\":[";
            for (std::size_t index = 0; index < function.parameters().size(); ++index) {
                if (index)
                    facts << ',';
                facts << "{\"offset\":" << recordOffset(function, index)
                      << ",\"bytes\":" << argumentBytes(function.parameters()[index]) << ',';
                type(function.parameters()[index]);
                facts << '}';
            }
            facts << "],\"result\":{\"bytes\":" << argumentBytes(function.result()) << ',';
            type(function.result());
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
        emittedStackFacts.clear();
        currentStackFacts = nullptr;
        metadata = &validated.metadata();
        functionIndex = 0;
        std::set<std::string> referencedReflection;
        if (reflection == ReflectionEmission::Referenced)
            for (const auto &body : module.functions)
                for (const auto instruction : body.code)
                    if (const auto *query = std::get_if<ir::MetadataQuery>(&instruction))
                        referencedReflection.insert(querySymbol(query->query, query->moduleScope));
        // Resource graphs link a trusted host adapter. No user-selected source
        // symbol may interpose its allocator, stdio or fail-stop dependencies.
        // Derive this from validated signatures/lifetime IR, never an input flag.
        bool owningMetadata = false;
        for (std::size_t index = 0; index < metadata->classCount(); ++index)
            owningMetadata = owningMetadata || metadata->isOwning(metadata->classAt(index));
        const bool resourceGraph = owningMetadata ||
            std::any_of(module.functions.begin(), module.functions.end(), [&](const ir::FunctionBody &body) {
                const auto function = metadata->callable(body.callableId);
                const auto receiver = function.receiver();
                return function.result().isResource() ||
                       (function.result().isClass() && ir::owningClass(*metadata, function.result().className)) ||
                       (receiver && ir::owningClass(*metadata, receiver->className)) ||
                       std::any_of(function.parameters().begin(),
                                   function.parameters().end(),
                                   [&](const Type &type) {
                                       return type.isResource() ||
                                              (type.isClass() && ir::owningClass(*metadata, type.className));
                                   }) ||
                       std::any_of(body.code.begin(), body.code.end(), [](const ir::InstructionObservation &op) {
                           return std::holds_alternative<ir::BeginBytes>(op) ||
                                  std::holds_alternative<ir::ResourceCallObservation>(op) ||
                                  std::holds_alternative<ir::InitializeBytesField>(op) ||
                                  std::holds_alternative<ir::MoveObject>(op) ||
                                  std::holds_alternative<ir::BindOwnedObjectParameter>(op) ||
                                  std::holds_alternative<ir::ReturnOwnedObject>(op);
                       });
            });
        const bool serviceGraph =
            std::any_of(module.functions.begin(), module.functions.end(), [&](const ir::FunctionBody &body) {
                const auto function = metadata->callable(body.callableId);
                return std::any_of(function.parameters().begin(), function.parameters().end(), [](const Type &type) {
                    return type.isService();
                });
            });
        const bool privateGraph = resourceGraph || serviceGraph;
        ownedSpanRuntime = resourceGraph;
        output << "# Aurora compiler output: validated typed IR, x86-64 bootstrap\n.text\n";
        for (const auto &body : module.functions) {
            const auto function = metadata->callable(body.callableId);
            const int declaredFrameBytes = metadata->frame(body.callableId).frameBytes();
            const auto receiver = function.receiver();
            const auto borrowedRootCount = function.borrowedRootCount();
            stackDepth = 0;
            beginStackFacts(function.name());
            serviceLoanOffsets.clear();
            for (const auto operation : body.code)
                if (const auto *loan = std::get_if<ir::AcquireServiceLoan>(&operation))
                    serviceLoanOffsets.emplace(loan->loanId, loan->offset);
            divisionIndex = 0;
            currentFunction = &body;
            const bool aggregate = aggregateSignature(function);
            // Receiver and aggregate entry points use a private compiler ABI and cannot be
            // exposed as ordinary scalar-callable external symbols.
            output << (binding == SymbolBinding::Local || privateGraph || receiver || aggregate ||
                               function.name().starts_with("__au_o_")
                           ? ".local "
                           : ".globl ")
                   << function.name() << "\n.type " << function.name() << ", @function\n"
                   << function.name() << ":\n";
            line("pushq %rbp");
            growStack(8);
            line("movq %rsp, %rbp");
            receiverSaveOffset = receiver ? declaredFrameBytes + 8 : 0;
            // Resource constructors always receive a packed record, even when
            // their explicit parameters contain no class values. Borrowed
            // ordinary methods retain their existing hidden-register modes.
            const bool resourceParameters = !function.parameters().empty() && function.parameters().front().isRegion();
            const bool packedArguments = receiver ? classParameters(function) || resourceParameters : aggregate;
            if (packedArguments) {
                currentStackFacts->copiedRecord = copiedRecordFacts(function);
                currentStackFacts->serviceRecord = serviceRecordFacts(function);
            }
            const bool combinedMethod =
                receiver && packedArguments && (function.result().isClass() || function.result().isSpan());
            callRecordSaveOffset = packedArguments ? declaredFrameBytes + (receiver ? 16 : 8) : 0;
            resultSaveOffset =
                (function.result().isClass() || function.result().isOwnerStorage() || function.result().isSpan())
                    ? declaredFrameBytes + (combinedMethod ? 24 : 16)
                    : 0;
            // Hidden roots never occupy source-addressable slots. Preserve
            // single-root copied/span saves and the literal two-root layout;
            // longer scalar-only prefixes reserve their aligned pointer extent.
            const int rootSaveBytes = (static_cast<int>(borrowedRootCount) * 8 + 15) & ~15;
            const int frameBytes = declaredFrameBytes + (borrowedRootCount > 1   ? rootSaveBytes
                                                         : combinedMethod       ? 32
                                                         : receiver || aggregate ? 16
                                                                                 : 0);
            reserveStack(frameBytes);
            if (borrowedRootCount > 1) {
                // Keep the tuple in R10 until every later pointer is safely
                // saved. R11 is scratch only in this scalar-only entry mode.
                for (std::size_t ordinal = 1; ordinal < borrowedRootCount; ++ordinal) {
                    line("movq " + std::to_string(ordinal * 8) + "(%r10), %r11");
                    line("movq %r11, " + address(rootSaveOffset(ordinal)));
                }
                line("movq (%r10), %r10");
            }
            if (receiver)
                line("movq %r10, " + address(rootSaveOffset(0)));
            if (packedArguments)
                line("movq %r11, " + address(callRecordSaveOffset));
            if (function.result().isClass() || function.result().isOwnerStorage() || function.result().isSpan())
                line(std::string("movq ") +
                     (combinedMethod ? "%rax"
                      : receiver     ? "%r11"
                                     : "%r10") +
                     ", " + address(resultSaveOffset));
            // Validation certifies operand-depth continuity in this exact retained
            // sequence, including branch joins. Outgoing reservations are balanced
            // inside each instruction; no instruction-text interpretation is used.
            // Both forms are set and cleared around one instruction; start each
            // function clean even if an earlier emission was abandoned by a throw.
            directResult = false;
            leftInRcx = false;
            for (ir::CodePosition at = 0; at < body.code.size(); ++at) {
                // An element read returned at once is copied into the result
                // storage directly. Adjacency means no label or other use lies
                // between; the slot is never read again after the return.
                const auto currentInstruction = body.code[at];
                const auto nextInstruction = at + 1 < body.code.size()
                                                 ? std::optional<ir::InstructionObservation>(body.code[at + 1])
                                                 : std::nullopt;
                const auto followingInstruction = at + 2 < body.code.size()
                                                      ? std::optional<ir::InstructionObservation>(body.code[at + 2])
                                                      : std::nullopt;
                const auto *load = std::get_if<ir::ValuesLoad>(&currentInstruction);
                const auto *result = nextInstruction ? std::get_if<ir::ReturnObject>(&*nextInstruction) : nullptr;
                // A pushed left operand followed by a plain accumulator load stays
                // in %rcx for the binary operation that would pop it. The load
                // touches neither %rcx nor the stack, and no label lies between.
                if (followingInstruction && std::holds_alternative<ir::Push>(currentInstruction) &&
                    plainLoad(*nextInstruction) && poppedBinary(*followingInstruction)) {
                    line("movq %rax, %rcx");
                    instruction(*nextInstruction, body.code.idAt(at + 1));
                    leftInRcx = true;
                    instruction(*followingInstruction, body.code.idAt(at + 2));
                    leftInRcx = false;
                    at += 2;
                } else if (load && result && result->offset == load->resultOffset) {
                    if (physicalStorage(function.result().className).sizeBytes !=
                        ownerElementStride(load->offset, load->fieldIndex))
                        throw Error("x86 backend returned element storage of a different extent");
                    directResult = true;
                    instruction(currentInstruction, body.code.idAt(at));
                    directResult = false;
                    line("xorq %rax, %rax");
                    line("jmp " + returnLabel());
                    ++at;
                } else
                    instruction(currentInstruction, body.code.idAt(at));
            }
            if (stackDepth != 0 || liveStackBytes != frameBytes + 16)
                throw Error("x86 backend left an unbalanced stack reservation");
            output << returnLabel() << ":\n";
            line("leave");
            line("ret");
            output << ".size " << function.name() << ", .-" << function.name() << "\n";
            ++functionIndex;
        }
        for (std::size_t index = 0; index < metadata->scopeCount(); ++index) {
            const auto scope = metadata->scopeAt(index);
            const auto view = metadata->visibleDescriptors(scope);
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
                    const auto descriptor = metadata->findDescriptor(id).value();
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
        // Retained code names durable payload rows. Revisit those literals rather
        // than retaining a second native owner of their bytes during emission.
        bool literalSection = false;
        for (const auto &body : module.functions)
            for (ir::CodePosition at = 0; at < body.code.size(); ++at) {
                const auto observation = body.code[at];
                if (const auto *literal = std::get_if<ir::BorrowLiteralSpanObservation>(&observation)) {
                    if (!literalSection) {
                        output << ".section .rodata\n";
                        literalSection = true;
                    }
                    output << ".Laurora_literal_" << body.code.idAt(at) << ":\n";
                    for (const auto byte : literal->bytes)
                        output << "    .byte " << static_cast<unsigned>(byte) << '\n';
                }
            }
        output << ".section .note.GNU-stack,\"\",@progbits\n";
        return output.str();
    }
};
} // namespace aurora
