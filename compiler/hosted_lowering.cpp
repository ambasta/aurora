#include "hosted_lowering.hpp"
#include "hosted_ir_metadata_writer.hpp"
#include "hosted_ir_instructions.hpp"
#include "ir_instruction_codec.hpp"
#include <algorithm>
#include <bit>
#include <limits>
#include <map>
#include <set>
#include <utility>

namespace aurora {
namespace {
namespace wire = hosted_abi::compiler_lowering;
namespace metadata = hosted_abi::compiler_ir_metadata;
using MetadataWriter = ir::detail::MetadataWriter;
using ir::detail::metadataFlagMasks;
using InstructionWriter = ir::detail::InstructionWriter;
using wire::InstructionForm;
using wire::OperandRole;
using wire::RecordKind;

[[noreturn]] void invalidLowering() {
    throw Error(DiagnosticCode::Internal, "invalid hosted lowering result");
}
std::size_t sizeValue(std::int64_t value) {
    if (value < 0 || static_cast<std::uint64_t>(value) > std::numeric_limits<std::size_t>::max())
        invalidLowering();
    return static_cast<std::size_t>(value);
}
int intValue(std::int64_t value) {
    if (value < std::numeric_limits<int>::min() || value > std::numeric_limits<int>::max())
        invalidLowering();
    return static_cast<int>(value);
}
bool boolValue(std::int64_t value) {
    if (value != 0 && value != 1)
        invalidLowering();
    return value == 1;
}
std::int64_t identity(std::int64_t value) {
    if (value < 0)
        invalidLowering();
    return value;
}
template <typename Container, typename... Values> void insertUnique(Container &target, Values &&...values) {
    if (!target.emplace(std::forward<Values>(values)...).second)
        invalidLowering();
}

class Projection {
    const HostedLoweringInput &input;
    const HostedLoweringServices &services;
    std::vector<bool> ownedRows;
    std::vector<bool> usedOperands;
    std::map<std::int64_t, std::string> carrierNames;
    std::size_t materializedBytes = 0;

    // Check aggregate vector/list payload arithmetic without inventing a new
    // admission cap. Allocator/node/string overhead and the independent verifier
    // are additional process memory, not a claim covered by this payload count.
    void charge(std::size_t count, std::size_t width) {
        const auto maximum = std::numeric_limits<std::size_t>::max();
        if (width != 0 && count > (maximum - materializedBytes) / width)
            invalidLowering();
        materializedBytes += count * width;
    }
    static std::pair<std::size_t, std::size_t> range(std::int64_t begin, std::int64_t count, std::size_t published) {
        const auto first = sizeValue(begin), length = sizeValue(count);
        if (first > published || length > published - first)
            invalidLowering();
        return {first, length};
    }
    const wire::OutputRow &row(std::int64_t id) const {
        const auto at = sizeValue(id);
        if (at >= input.rows.size())
            invalidLowering();
        return input.rows[at];
    }
    const wire::OutputRow &own(std::int64_t id, RecordKind kind) {
        const auto &value = row(id);
        const auto at = sizeValue(id);
        if (value.recordKind != kind || ownedRows[at])
            invalidLowering();
        ownedRows[at] = true;
        return value;
    }
    std::span<const wire::OperandRow> takeRange(std::int64_t begin, std::int64_t count) {
        const auto [first, length] = range(begin, count, input.operands.size());
        // Prefixes and nonempty flat lists are exclusive. Empty slices carry no
        // ownership and may point at any position through the published end.
        for (std::size_t at = first; at < first + length; ++at) {
            if (usedOperands[at])
                invalidLowering();
            usedOperands[at] = true;
        }
        return input.operands.subspan(first, length);
    }
    class Operands {
        std::span<const wire::OperandRow> values;
        std::size_t next = 0;

    public:
        Operands(Projection &owner, const wire::OutputRow &row)
            : values(owner.takeRange(row.operandBegin, row.operandCount)) {
        }
        const wire::OperandRow &take() {
            if (next == values.size())
                invalidLowering();
            return values[next++];
        }
        const wire::OperandRow &take(OperandRole role) {
            const auto &value = take();
            if (value.operandRole != role)
                invalidLowering();
            return value;
        }
        std::int64_t scalar(OperandRole role) {
            return take(role).signedValue;
        }
        int integer(OperandRole role) {
            return intValue(scalar(role));
        }
        bool boolean(OperandRole role) {
            return boolValue(scalar(role));
        }
        void finish() const {
            if (next != values.size())
                invalidLowering();
        }
    };
    std::span<const wire::OperandRow> list(const wire::OperandRow &value, OperandRole itemRole) {
        const auto result = takeRange(value.sliceBegin, value.sliceCount);
        for (const auto &item : result)
            if (item.operandRole != itemRole)
                invalidLowering();
        return result;
    }
    std::span<const wire::OperandRow> rows(Operands &values, OperandRole role) {
        return list(values.take(role), OperandRole::OutputRowId);
    }
    Type type(Operands &values, OperandRole role) const {
        return services.type(identity(values.scalar(role)));
    }
    std::string functionName(Operands &values, OperandRole role) const {
        return services.functionName(identity(values.scalar(role)));
    }
    std::string className(Operands &values) const {
        return services.className(identity(values.scalar(OperandRole::ClassNominalId)));
    }
    std::string classOrCarrier(Operands &values) const {
        const auto &value = values.take();
        if (value.operandRole == OperandRole::ClassNominalId)
            return services.className(identity(value.signedValue));
        if (value.operandRole != OperandRole::CarrierId || row(value.signedValue).recordKind != RecordKind::Carrier)
            invalidLowering();
        const auto name = carrierNames.find(value.signedValue);
        if (name == carrierNames.end())
            invalidLowering();
        // CarrierId is an identity reference: it does not claim row ownership.
        return name->second;
    }
    int moduleScope(Operands &values) const {
        const auto value = identity(values.scalar(OperandRole::ModuleScope));
        services.checkModuleScope(value);
        return intValue(value);
    }
    service::Kind serviceKind(Operands &values) const {
        return services.serviceKind(identity(values.scalar(OperandRole::ServiceKindId)));
    }
    struct SourceOffsets {
        using value_type = int;
        std::span<const wire::OperandRow> values;
        std::size_t size() const {
            return values.size();
        }
        bool empty() const {
            return values.empty();
        }
        int at(std::size_t index) const {
            if (index >= values.size())
                invalidLowering();
            return intValue(values[index].signedValue);
        }
        int operator[](std::size_t index) const {
            return at(index);
        }
        auto begin() const {
            return ir::MetadataIterator<SourceOffsets>(*this, 0);
        }
        auto end() const {
            return ir::MetadataIterator<SourceOffsets>(*this, size());
        }
        bool operator==(const SourceOffsets &other) const {
            return values.data() == other.values.data() && values.size() == other.values.size();
        }
    };
    struct SourceServices {
        using value_type = ir::ServiceArgument;
        std::span<const wire::OperandRow> values;
        const HostedLoweringServices *renderers = nullptr;
        std::size_t size() const {
            return values.size() / 2;
        }
        bool empty() const {
            return values.empty();
        }
        ir::ServiceArgument at(std::size_t index) const {
            if (index >= size() || !renderers)
                invalidLowering();
            return {intValue(values[index * 2].signedValue),
                    renderers->serviceKind(identity(values[index * 2 + 1].signedValue))};
        }
        ir::ServiceArgument operator[](std::size_t index) const {
            return at(index);
        }
        auto begin() const {
            return ir::MetadataIterator<SourceServices>(*this, 0);
        }
        auto end() const {
            return ir::MetadataIterator<SourceServices>(*this, size());
        }
        bool operator==(const SourceServices &other) const {
            return values.data() == other.values.data() && values.size() == other.values.size() &&
                   renderers == other.renderers;
        }
    };
    struct SourceRoots {
        using value_type = ir::BorrowedRootArgument;
        std::span<const wire::OperandRow> values;
        std::size_t size() const {
            return values.size() / 3;
        }
        bool empty() const {
            return values.empty();
        }
        ir::BorrowedRootArgument at(std::size_t index) const {
            if (index >= size())
                invalidLowering();
            return {intValue(values[index * 3].signedValue),
                    intValue(values[index * 3 + 1].signedValue),
                    intValue(values[index * 3 + 2].signedValue)};
        }
        ir::BorrowedRootArgument operator[](std::size_t index) const {
            return at(index);
        }
        auto begin() const {
            return ir::MetadataIterator<SourceRoots>(*this, 0);
        }
        auto end() const {
            return ir::MetadataIterator<SourceRoots>(*this, size());
        }
        bool operator==(const SourceRoots &other) const {
            return values.data() == other.values.data() && values.size() == other.values.size();
        }
    };
    struct SourceLiteral {
        using value_type = unsigned char;
        const HostedLoweringServices *renderers = nullptr;
        std::int64_t first = 0;
        std::size_t count = 0;
        std::size_t size() const {
            return count;
        }
        bool empty() const {
            return count == 0;
        }
        unsigned char at(std::size_t index) const {
            if (index >= count || !renderers)
                invalidLowering();
            return renderers->literalByte(first + static_cast<std::int64_t>(index));
        }
        unsigned char operator[](std::size_t index) const {
            return at(index);
        }
        auto begin() const {
            return ir::MetadataIterator<SourceLiteral>(*this, 0);
        }
        auto end() const {
            return ir::MetadataIterator<SourceLiteral>(*this, size());
        }
        bool operator==(const SourceLiteral &) const = default;
    };
    using SourceInstruction = ir::BasicInstruction<SourceOffsets, SourceServices, SourceLiteral, SourceRoots>;
    struct SourceBody {
        std::size_t callableId;
        std::span<const wire::OperandRow> code;
    };
    static wire::Unary unary(wire::Unary value) {
        switch (value) {
        case wire::Unary::CheckedNegate:
        case wire::Unary::LogicalNot:
        case wire::Unary::BitNot:
            return value;
        }
        invalidLowering();
    }
    static wire::Binary binary(wire::Binary value) {
        switch (value) {
        case wire::Binary::CheckedAdd:
        case wire::Binary::CheckedSubtract:
        case wire::Binary::CheckedMultiply:
        case wire::Binary::CheckedDivide:
        case wire::Binary::CheckedRemainder:
        case wire::Binary::BitAnd:
        case wire::Binary::BitOr:
        case wire::Binary::BitXor:
        case wire::Binary::ShiftLeft:
        case wire::Binary::ShiftRight:
            return value;
        }
        invalidLowering();
    }
    static wire::Comparison comparison(wire::Comparison value) {
        switch (value) {
        case wire::Comparison::Equal:
        case wire::Comparison::NotEqual:
        case wire::Comparison::Less:
        case wire::Comparison::Greater:
        case wire::Comparison::LessEqual:
        case wire::Comparison::GreaterEqual:
            return value;
        }
        invalidLowering();
    }
    static wire::Query query(wire::Query value) {
        switch (value) {
        case wire::Query::Size:
        case wire::Query::PublicFieldCount:
            return value;
        }
        invalidLowering();
    }
    class SourceInstructionCursor {
        Projection &owner;
        const wire::OutputRow &header;
        Operands &values;

    public:
        SourceInstructionCursor(Projection &owner, const wire::OutputRow &header, Operands &values)
            : owner(owner), header(header), values(values) {
        }
        void integer(OperandRole role, int &value) {
            value = values.integer(role);
        }
        void boolean(OperandRole role, bool &value) {
            value = values.boolean(role);
        }
        void type(OperandRole role, Type &value) {
            value = owner.type(values, role);
        }
        void callee(std::string &value) {
            value = owner.functionName(values, OperandRole::CalleeSymbolId);
        }
        void className(std::string &value) {
            value = owner.className(values);
        }
        void moduleScope(int &value) {
            value = owner.moduleScope(values);
        }
        void serviceKind(service::Kind &value) {
            value = owner.serviceKind(values);
        }
        void serviceOperation(service::Operation &value) {
            value = owner.services.serviceOperation(identity(values.scalar(OperandRole::ServiceOperationId)));
        }
        void unary(wire::Unary &value) {
            value = Projection::unary(header.unaryOperation);
        }
        void binary(wire::Binary &value) {
            value = Projection::binary(header.binaryOperation);
        }
        void comparison(wire::Comparison &value) {
            value = Projection::comparison(header.comparisonOperation);
        }
        void query(wire::Query &value) {
            value = Projection::query(header.queryOperation);
        }
        void constant(std::int64_t &value, Type &resultType) {
            const auto &payload = values.take();
            resultType = owner.type(values, OperandRole::TypeId);
            if (resultType == Type::U64) {
                if (payload.operandRole != OperandRole::UnsignedConstant)
                    invalidLowering();
                value = std::bit_cast<std::int64_t>(payload.unsignedValue);
            } else {
                if (payload.operandRole != OperandRole::SignedConstant)
                    invalidLowering();
                value = payload.signedValue;
            }
        }
        void offsets(OperandRole role, SourceOffsets &value) {
            value.values = owner.list(values.take(role), OperandRole::Offset);
            for (const auto &item : value.values)
                (void)intValue(item.signedValue);
        }
        void services(SourceServices &value) {
            const auto &slice = values.take(OperandRole::AdditionalServices);
            value.values = owner.takeRange(slice.sliceBegin, slice.sliceCount);
            value.renderers = &owner.services;
            if (value.values.size() % 2 != 0)
                invalidLowering();
            for (std::size_t index = 0; index < value.values.size(); index += 2) {
                if (value.values[index].operandRole != OperandRole::ServiceLoanId ||
                    value.values[index + 1].operandRole != OperandRole::ServiceKindId)
                    invalidLowering();
                (void)intValue(value.values[index].signedValue);
                (void)owner.services.serviceKind(identity(value.values[index + 1].signedValue));
            }
        }
        void roots(SourceRoots &value) {
            const auto &slice = values.take(OperandRole::BorrowedRoots);
            value.values = owner.takeRange(slice.sliceBegin, slice.sliceCount);
            if (value.values.empty() || value.values.size() > 18 || value.values.size() % 3 != 0)
                invalidLowering();
            for (std::size_t index = 0; index < value.values.size(); index += 3) {
                if (value.values[index].operandRole != OperandRole::Root ||
                    value.values[index + 1].operandRole != OperandRole::LoanId ||
                    value.values[index + 2].operandRole != OperandRole::FieldIndex)
                    invalidLowering();
                (void)intValue(value.values[index].signedValue);
                (void)intValue(value.values[index + 1].signedValue);
                (void)intValue(value.values[index + 2].signedValue);
            }
        }
        void literal(SourceLiteral &value) {
            const auto &slice = values.take(OperandRole::LiteralBytes);
            const auto count = range(slice.sliceBegin, slice.sliceCount, sizeValue(owner.input.sourceByteCount)).second;
            value = {&owner.services, slice.sliceBegin, count};
            // Discarding suppresses storage, never source-domain validation.
            // Retained literals stream during fill; discarded bytes are checked
            // here because no writer will consume their borrowed interval.
            if (header.recordKind == RecordKind::DiscardedInstruction)
                for (std::size_t index = 0; index < count; ++index)
                    (void)value.at(index);
        }
        void finish() const {
            values.finish();
        }
    };
    SourceInstruction instruction(std::int64_t id, RecordKind kind = RecordKind::Instruction) {
        const auto &header = own(id, kind);
        Operands values(*this, header);
        SourceInstructionCursor cursor(*this, header, values);
        return ir::detail::readInstruction<SourceInstruction>(header.instructionForm, cursor);
    }
    void instructions(InstructionWriter &writer, const std::vector<SourceBody> &bodies) {
        for (const auto &body : bodies) {
            writer.beginBody(body.callableId);
            for (const auto &item : body.code)
                writer.append(instruction(item.signedValue));
            writer.endBody();
        }
    }
    void slot(MetadataWriter &writer, std::int64_t id) {
        const auto kind = row(id).recordKind;
        switch (kind) {
        case RecordKind::ScalarSlot:
        case RecordKind::ObjectSlot:
        case RecordKind::ArraySlot:
        case RecordKind::SpanSlot:
        case RecordKind::ServiceSlot:
        case RecordKind::RegionSlot:
        case RecordKind::ByteSlot:
        case RecordKind::OwnedValueType:
        case RecordKind::SpanValueType:
            break;
        default:
            invalidLowering();
        }
        Operands values(*this, own(id, kind));
        metadata::SlotRow declaration;
        declaration.recordKind = static_cast<std::int64_t>(kind);
        declaration.slotOffset = values.integer(OperandRole::Offset);
        switch (kind) {
        case RecordKind::ScalarSlot: {
            declaration.typeIndex = writer.slotType(type(values, OperandRole::TypeId));
            break;
        }
        case RecordKind::ObjectSlot: {
            declaration.typeIndex = writer.slotType(Type(classOrCarrier(values)));
            declaration.mutableValue = values.boolean(OperandRole::MutableValue);
            break;
        }
        case RecordKind::ArraySlot: {
            declaration.slotLength = values.integer(OperandRole::Length);
            break;
        }
        case RecordKind::SpanSlot:
        case RecordKind::ServiceSlot:
        case RecordKind::RegionSlot:
            break;
        case RecordKind::ByteSlot: {
            declaration.mutableValue = values.boolean(OperandRole::MutableValue);
            break;
        }
        case RecordKind::OwnedValueType: {
            declaration.typeIndex = writer.slotType(Type::ownedValues(Type(className(values))));
            break;
        }
        case RecordKind::SpanValueType: {
            declaration.typeIndex = writer.slotType(Type::valueSpan(Type(className(values))));
            break;
        }
        default:
            invalidLowering();
        }
        values.finish();
        writer.append(declaration);
    }
    metadata::ReceiverShape receiver(MetadataWriter &writer, std::int64_t id) {
        Operands values(*this, own(id, RecordKind::Receiver));
        metadata::ReceiverShape result;
        result.nameRange = writer.text(className(values));
        result.flags = values.boolean(OperandRole::MutableValue) ? metadataFlagMasks().receiverMutable : 0;
        if (values.boolean(OperandRole::Constructor))
            result.flags |= metadataFlagMasks().receiverConstructor;
        if (values.boolean(OperandRole::PublicAccess))
            result.flags |= metadataFlagMasks().receiverPublic;
        values.finish();
        return result;
    }
    void function(MetadataWriter &writer, std::int64_t id, std::vector<SourceBody> &bodies) {
        Operands values(*this, own(id, RecordKind::Function));
        metadata::CallableRow callable;
        callable.nameRange = writer.text(functionName(values, OperandRole::FunctionSymbolId));
        callable.moduleScope = moduleScope(values);
        callable.typeRange.firstIndex = writer.position().coreCounts.types;
        writer.callableType(type(values, OperandRole::ResultTypeId));
        const auto parameters = list(values.take(OperandRole::ParameterTypes), OperandRole::TypeId);
        if (parameters.size() >= static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()))
            invalidLowering();
        callable.typeRange.indexCount = 1 + static_cast<std::int64_t>(parameters.size());
        for (const auto &parameter : parameters)
            writer.callableType(services.type(identity(parameter.signedValue)));
        const auto slots = rows(values, OperandRole::Slots);
        callable.slotRange.firstIndex = writer.slotCount();
        charge(slots.size(), sizeof(std::int64_t));
        std::vector<std::int64_t> slotIds;
        slotIds.reserve(slots.size());
        for (const auto &item : slots)
            slotIds.push_back(item.signedValue);
        // Sort only source-row identities. Declarations are copied directly
        // into the one source owner, in both the counting and filling walks.
        const auto slotKey = [&](std::int64_t slotId) {
            const auto kind = row(slotId).recordKind;
            const auto &offset = key(slotId, kind);
            if (offset.operandRole != OperandRole::Offset)
                invalidLowering();
            return std::pair{static_cast<std::int64_t>(kind), offset.signedValue};
        };
        std::sort(slotIds.begin(), slotIds.end(), [&](auto left, auto right) {
            const auto a = slotKey(left), b = slotKey(right);
            return a < b || (a == b && left < right);
        });
        for (const auto slotId : slotIds)
            slot(writer, slotId);
        callable.slotRange.indexCount = writer.slotCount() - callable.slotRange.firstIndex;
        const auto &receiverOperand = values.take();
        if (receiverOperand.operandRole == OperandRole::ReceiverRef) {
            callable.flags |= metadataFlagMasks().callableReceiver;
            callable.receiver = receiver(writer, receiverOperand.signedValue);
        } else if (receiverOperand.operandRole != OperandRole::NoReceiver) {
            invalidLowering();
        }
        callable.borrowedRootCount = values.scalar(OperandRole::BorrowedRootCount);
        callable.borrowedRootMutability = values.scalar(OperandRole::BorrowedRootMutability);
        const auto &spanOperand = values.take();
        if (spanOperand.operandRole == OperandRole::ReceiverSpanField) {
            callable.flags |= metadataFlagMasks().callableSpanSummary;
            callable.receiverSpanField = intValue(spanOperand.signedValue);
        } else if (spanOperand.operandRole != OperandRole::NoReceiverSpan) {
            invalidLowering();
        }
        callable.frameBytes = values.integer(OperandRole::FrameBytes);
        const auto code = rows(values, OperandRole::Code);
        values.finish();
        // Keep only source code descriptors until all declaration types have
        // been written. Instruction types form one strict suffix afterwards.
        bodies.push_back({static_cast<std::size_t>(writer.callableCount()), code});
        writer.append(callable);
    }
    ir::ClassField field(std::int64_t id) {
        Operands values(*this, own(id, RecordKind::ClassField));
        ir::ClassField result{type(values, OperandRole::ElementTypeId),
                              values.integer(OperandRole::FirstLeaf),
                              values.integer(OperandRole::Length),
                              values.boolean(OperandRole::Array),
                              values.integer(OperandRole::ElementCount)};
        values.finish();
        return result;
    }
    metadata::IndexRange offsets(MetadataWriter &writer, Operands &values, OperandRole role) {
        const auto items = list(values.take(role), OperandRole::Offset);
        metadata::IndexRange range;
        range.firstIndex = writer.position().mapCounts.indices;
        range.indexCount = static_cast<std::int64_t>(items.size());
        for (const auto &item : items)
            writer.index(intValue(item.signedValue));
        return range;
    }
    void storage(MetadataWriter &writer, std::int64_t id) {
        Operands values(*this, own(id, RecordKind::ClassStorage));
        metadata::StorageRow result;
        result.leafOffsetRange = offsets(writer, values, OperandRole::LeafOffsets);
        result.fieldOffsetRange = offsets(writer, values, OperandRole::FieldOffsets);
        result.physicalExtent.sizeBytes = values.integer(OperandRole::SizeBytes);
        result.physicalExtent.alignmentBytes = values.integer(OperandRole::Alignment);
        result.physicalExtent.reservedBytes = values.integer(OperandRole::ReservedBytes);
        values.finish();
        writer.append(result);
    }
    void classRecord(MetadataWriter &writer, const std::string &name, std::int64_t id, bool carrier) {
        metadata::ClassRow result;
        result.nameRange = writer.text(name);
        result.leafRange.firstIndex = writer.position().coreCounts.leaves;
        result.fieldRange.firstIndex = writer.position().coreCounts.fields;
        result.suppliedStorage = -1;
        result.membershipBits = carrier ? metadataFlagMasks().classArrayCarrier : 0;
        if (id >= 0) {
            Operands values(*this, own(id, RecordKind::Class));
            if (classOrCarrier(values) != name)
                invalidLowering();
            const auto leaves = list(values.take(OperandRole::LeafTypes), OperandRole::TypeId);
            result.leafRange.indexCount = static_cast<std::int64_t>(leaves.size());
            for (const auto &item : leaves)
                writer.leaf(services.type(identity(item.signedValue)));
            const auto fieldRows = rows(values, OperandRole::Fields);
            result.fieldRange.indexCount = static_cast<std::int64_t>(fieldRows.size());
            for (const auto &item : fieldRows)
                writer.field(field(item.signedValue));
            result.suppliedStorage = writer.position().mapCounts.storage;
            storage(writer, values.scalar(OperandRole::StorageRef));
            values.finish();
            result.membershipBits |=
                metadataFlagMasks().classLayout | metadataFlagMasks().classFields | metadataFlagMasks().classStorage;
        }
        writer.append(result);
    }
    void carrier(std::set<std::string> &names, std::int64_t id) {
        Operands values(*this, own(id, RecordKind::Carrier));
        const auto elementType = type(values, OperandRole::ElementTypeId);
        const auto count = values.integer(OperandRole::ElementCount);
        values.finish();
        // The producer explicitly selected a private class-array carrier. This
        // check only establishes the native nominal-name domain used to spell it.
        if (elementType.kind != TypeKind::Class)
            invalidLowering();
        auto name = "@array:" + elementType.className + ":" + std::to_string(count);
        insertUnique(names, name);
        insertUnique(carrierNames, id, std::move(name));
    }
    void descriptor(MetadataWriter &writer, std::int64_t key, std::int64_t id) {
        Operands values(*this, own(id, RecordKind::Descriptor));
        metadata::DescriptorRow result;
        result.descriptorId = intValue(identity(values.scalar(OperandRole::PublicDescriptorId)));
        if (result.descriptorId != key)
            invalidLowering();
        result.sizeValue = values.scalar(OperandRole::Size);
        result.publicFieldCount = values.scalar(OperandRole::PublicFields);
        values.finish();
        writer.append(result);
    }
    void descriptorView(MetadataWriter &writer,
                        std::int64_t key,
                        std::int64_t id,
                        const std::map<std::int64_t, std::int64_t> &descriptors) {
        Operands values(*this, own(id, RecordKind::DescriptorView));
        metadata::ViewRow result;
        result.moduleScope = moduleScope(values);
        if (result.moduleScope != key)
            invalidLowering();
        const auto items = list(values.take(OperandRole::VisibleDescriptors), OperandRole::PublicDescriptorId);
        values.finish();
        charge(items.size(), sizeof(int));
        std::set<int> visible;
        for (const auto &item : items) {
            const auto publicId = intValue(identity(item.signedValue));
            if (!descriptors.contains(publicId))
                invalidLowering();
            insertUnique(visible, publicId);
        }
        result.descriptorRange.firstIndex = writer.position().mapCounts.indices;
        result.descriptorRange.indexCount = static_cast<std::int64_t>(visible.size());
        for (auto publicId : visible)
            writer.index(publicId);
        writer.append(result);
    }
    void enumeration(MetadataWriter &writer, const std::string &name, std::int64_t id) {
        Operands values(*this, own(id, RecordKind::EnumCases));
        if (services.enumName(identity(values.scalar(OperandRole::EnumNominalId))) != name)
            invalidLowering();
        metadata::EnumRow result;
        result.nameRange = writer.text(name);
        result.caseCount = values.integer(OperandRole::CaseCount);
        values.finish();
        writer.append(result);
    }
    void metadataRecords(MetadataWriter &writer,
                         const std::map<std::string, std::int64_t> &classes,
                         const std::set<std::string> &carriers,
                         const std::map<std::int64_t, std::int64_t> &descriptors,
                         const std::map<std::int64_t, std::int64_t> &views,
                         const std::map<std::string, std::int64_t> &enums) {
        for (const auto &[name, id] : classes)
            classRecord(writer, name, id, carriers.contains(name));
        for (const auto &[key, id] : descriptors)
            descriptor(writer, key, id);
        for (const auto &[key, id] : views)
            descriptorView(writer, key, id, descriptors);
        for (const auto &[name, id] : enums)
            enumeration(writer, name, id);
    }
    const wire::OperandRow &key(std::int64_t id, RecordKind kind) const {
        const auto &value = row(id);
        const auto [begin, count] = range(value.operandBegin, value.operandCount, input.operands.size());
        if (value.recordKind != kind || count == 0)
            invalidLowering();
        return input.operands[begin];
    }
    std::int64_t key(std::int64_t id, RecordKind kind, OperandRole role) const {
        const auto &value = key(id, kind);
        if (value.operandRole != role)
            invalidLowering();
        return identity(value.signedValue);
    }
    Diagnostic unreadLocal(std::int64_t id) {
        Operands values(*this, own(id, RecordKind::UnreadLocal));
        auto identifier = services.identifier(identity(values.scalar(OperandRole::IdentifierSourceRef)));
        values.finish();
        return {DiagnosticCode::UnreadLocal,
                "local binding '" + identifier.text + "' is never read",
                std::move(identifier.span),
                DiagnosticSeverity::Warning};
    }
    void prelude() {
        if (input.rows.size() < hostedLoweringPrefixRows(false) || input.moduleRoot < hostedLoweringPrefixRows(false))
            invalidLowering();
        // The host supplied these immutable facts once before source lowering.
        // Only their typed transport and identity domains are checked here;
        // this adapter does not recompute limits, signatures, or layout order.
        Operands configuration(*this, own(1, RecordKind::Configuration));
        identity(configuration.integer(OperandRole::MaximumCopiedByteLeaves));
        identity(configuration.integer(OperandRole::MaximumCopiedNonByteLeaves));
        identity(configuration.integer(OperandRole::MaximumCopiedLeaves));
        identity(configuration.integer(OperandRole::MaximumCopiedBytes));
        identity(configuration.integer(OperandRole::MaximumByteArrayLength));
        identity(configuration.integer(OperandRole::MaximumScalarArrayLength));
        configuration.boolean(OperandRole::AnalysisMode);
        const auto groups = configuration.scalar(OperandRole::SupportedServiceGroups);
        std::int64_t layoutRow = -1;
        for (bool call : {false, true})
            for (bool port : {false, true})
                for (bool serve : {false, true})
                    if (groups == service::supportedGroupBitmap(call, port, serve))
                        layoutRow = hostedLoweringPrefixRows(call, port, serve) - 1;
        if (layoutRow < 0)
            invalidLowering();
        if (input.rows.size() <= sizeValue(layoutRow) || input.moduleRoot <= layoutRow)
            invalidLowering();
        configuration.finish();
        for (std::int64_t at = 2; at < 9; ++at) {
            Operands scalar(*this, own(at, RecordKind::ScalarContract));
            (void)type(scalar, OperandRole::TypeId);
            intValue(identity(scalar.scalar(OperandRole::PublicDescriptorId)));
            scalar.scalar(OperandRole::Size);
            scalar.finish();
        }
        for (std::int64_t at = 9; at < layoutRow; ++at) {
            Operands operation(*this, own(at, RecordKind::ServiceContract));
            (void)type(operation, OperandRole::TypeId);
            (void)serviceKind(operation);
            (void)services.serviceOperation(identity(operation.scalar(OperandRole::ServiceOperationId)));
            (void)services.identifier(identity(operation.scalar(OperandRole::IdentifierSourceRef)));
            (void)type(operation, OperandRole::ResultTypeId);
            const auto parameters = list(operation.take(OperandRole::ParameterTypes), OperandRole::TypeId);
            for (const auto &item : parameters)
                (void)services.type(identity(item.signedValue));
            operation.finish();
        }
        Operands layoutOrder(*this, own(layoutRow, RecordKind::InitialLayoutOrder));
        const auto symbols = list(layoutOrder.take(OperandRole::InitialLayoutSymbols), OperandRole::ClassNominalId);
        for (const auto &item : symbols)
            (void)services.className(identity(item.signedValue));
        layoutOrder.finish();
    }

public:
    Projection(const HostedLoweringInput &value, const HostedLoweringServices &renderers)
        : input(value), services(renderers), ownedRows(value.rows.size()), usedOperands(value.operands.size()) {
        if (!services.type || !services.functionName || !services.className || !services.enumName ||
            !services.identifier || !services.checkModuleScope || !services.serviceKind || !services.serviceOperation ||
            !services.literalByte)
            invalidLowering();
    }
    HostedLoweringOutput run() {
        // The success path has no selected semantic diagnostic. Reserve its
        // exact fixed prefix without interpreting reason-specific error payloads.
        const auto &report = row(input.diagnosticRow);
        if (input.diagnosticRow != 0 || report.recordKind != RecordKind::DiagnosticPayload ||
            report.operandBegin != 0 || report.operandCount != 3)
            invalidLowering();
        Operands reportValues(*this, report);
        reportValues.take(OperandRole::NoDiagnosticSource);
        reportValues.take(OperandRole::NoDiagnosticValue);
        reportValues.take(OperandRole::NoDiagnosticValue);
        reportValues.finish();
        prelude();

        Operands values(*this, own(input.moduleRoot, RecordKind::Module));
        const auto functions = rows(values, OperandRole::Functions);
        const auto classes = rows(values, OperandRole::Classes);
        const auto carriers = rows(values, OperandRole::Carriers);
        const auto descriptors = rows(values, OperandRole::Descriptors);
        const auto views = rows(values, OperandRole::DescriptorViews);
        const auto enums = rows(values, OperandRole::Enumerations);
        const auto diagnostics = rows(values, OperandRole::LintDiagnostics);
        values.finish();

        HostedLoweringOutput result;
        // Carrier names are shared output identities. Materialize their owning
        // list once before following nonowning CarrierId references elsewhere.
        std::set<std::string> carrierSymbols;
        for (const auto &item : carriers)
            carrier(carrierSymbols, item.signedValue);
        // A temporary name/ID ordering supplies the source-owned lookup suffix.
        // Callable row IDs preserve function-list order; duplicates remain raw
        // and are rejected by the independent source symbol pass.
        std::vector<std::pair<std::string, std::int64_t>> callableNames;
        charge(functions.size(), sizeof(std::pair<std::string, std::int64_t>));
        callableNames.reserve(functions.size());
        for (std::size_t id = 0; id < functions.size(); ++id)
            callableNames.emplace_back(
                services.functionName(
                    key(functions[id].signedValue, RecordKind::Function, OperandRole::FunctionSymbolId)),
                static_cast<std::int64_t>(id));
        std::sort(callableNames.begin(), callableNames.end());
        // Sort only identities and source row IDs; leaf/field/storage payloads
        // flow directly into the retained owner, in this canonical key order.
        std::map<std::string, std::int64_t> classRows, enumRows;
        std::map<std::int64_t, std::int64_t> descriptorRows, viewRows;
        for (const auto &item : classes) {
            const auto &value = key(item.signedValue, RecordKind::Class);
            std::string name;
            if (value.operandRole == OperandRole::ClassNominalId)
                name = services.className(identity(value.signedValue));
            else if (value.operandRole == OperandRole::CarrierId && carrierNames.contains(value.signedValue))
                name = carrierNames.at(value.signedValue);
            else
                invalidLowering();
            insertUnique(classRows, std::move(name), item.signedValue);
        }
        for (const auto &name : carrierSymbols)
            classRows.try_emplace(name, -1);
        for (const auto &item : descriptors)
            insertUnique(descriptorRows,
                         intValue(key(item.signedValue, RecordKind::Descriptor, OperandRole::PublicDescriptorId)),
                         item.signedValue);
        for (const auto &item : views)
            insertUnique(viewRows,
                         intValue(key(item.signedValue, RecordKind::DescriptorView, OperandRole::ModuleScope)),
                         item.signedValue);
        for (const auto &item : enums)
            insertUnique(enumRows,
                         services.enumName(key(item.signedValue, RecordKind::EnumCases, OperandRole::EnumNominalId)),
                         item.signedValue);
        MetadataWriter writer;
        InstructionWriter instructionWriter(writer);
        {
            // The independent count walk uses the same codec and payload views
            // as fill. It allocates no native instruction or payload vectors.
            Projection counter(input, services);
            counter.carrierNames = carrierNames;
            counter.metadataRecords(writer, classRows, carrierSymbols, descriptorRows, viewRows, enumRows);
            std::vector<SourceBody> bodies;
            bodies.reserve(functions.size());
            for (const auto &item : functions)
                counter.function(writer, item.signedValue, bodies);
            for (const auto &[name, id] : callableNames) {
                (void)name;
                writer.index(id);
            }
            writer.beginInstructions();
            counter.instructions(instructionWriter, bodies);
        }
        writer.allocate();
        instructionWriter.allocate();
        metadataRecords(writer, classRows, carrierSymbols, descriptorRows, viewRows, enumRows);
        std::vector<SourceBody> bodies;
        bodies.reserve(functions.size());
        for (const auto &item : functions)
            function(writer, item.signedValue, bodies);
        for (const auto &[name, id] : callableNames) {
            (void)name;
            writer.index(id);
        }
        writer.beginInstructions();
        instructions(instructionWriter, bodies);
        result.instructions = std::move(instructionWriter).take();
        charge(diagnostics.size(), sizeof(Diagnostic));
        result.diagnostics.reserve(diagnostics.size());
        for (const auto &item : diagnostics)
            result.diagnostics.push_back(unreadLocal(item.signedValue));

        for (std::size_t at = 0; at < input.rows.size(); ++at) {
            if (at == sizeValue(input.diagnosticRow) || ownedRows[at])
                continue;
            // Only the source's explicit discard tag can exclude an instruction
            // from Code. Its active fields remain checked; no constant folding,
            // source legality, or instruction filtering is replayed here.
            if (input.rows[at].recordKind != RecordKind::DiscardedInstruction ||
                at > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()))
                invalidLowering();
            (void)instruction(static_cast<std::int64_t>(at), RecordKind::DiscardedInstruction);
        }
        std::sort(result.diagnostics.begin(), result.diagnostics.end(), [](const auto &left, const auto &right) {
            return left.span.begin.offset < right.span.begin.offset;
        });
        return result;
    }
};
} // namespace
HostedLoweringOutput projectHostedLowering(const HostedLoweringInput &input, const HostedLoweringServices &services) {
    const auto maximum = static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max());
    if (input.rows.size() > maximum || input.operands.size() > maximum)
        invalidLowering();
    (void)sizeValue(input.sourceByteCount);
    return Projection(input, services).run();
}
} // namespace aurora
