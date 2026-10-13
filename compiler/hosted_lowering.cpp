#include "hosted_lowering.hpp"
#include <algorithm>
#include <bit>
#include <limits>
#include <map>
#include <set>
#include <utility>

namespace aurora {
namespace {
namespace wire = hosted_abi::compiler_lowering;
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
    std::vector<int> offsets(Operands &values, OperandRole role) {
        const auto items = list(values.take(role), OperandRole::Offset);
        charge(items.size(), sizeof(int));
        std::vector<int> result;
        result.reserve(items.size());
        for (const auto &item : items)
            result.push_back(intValue(item.signedValue));
        return result;
    }
    std::vector<Type> types(Operands &values, OperandRole role) {
        const auto items = list(values.take(role), OperandRole::TypeId);
        charge(items.size(), sizeof(Type));
        std::vector<Type> result;
        result.reserve(items.size());
        for (const auto &item : items)
            result.push_back(services.type(identity(item.signedValue)));
        return result;
    }
    std::vector<ir::ServiceArgument> additionalServices(Operands &values) {
        const auto &slice = values.take(OperandRole::AdditionalServices);
        const auto items = takeRange(slice.sliceBegin, slice.sliceCount);
        if (items.size() % 2 != 0)
            invalidLowering();
        charge(items.size() / 2, sizeof(ir::ServiceArgument));
        std::vector<ir::ServiceArgument> result;
        result.reserve(items.size() / 2);
        for (std::size_t at = 0; at < items.size(); at += 2) {
            if (items[at].operandRole != OperandRole::ServiceLoanId ||
                items[at + 1].operandRole != OperandRole::ServiceKindId)
                invalidLowering();
            result.push_back(
                {intValue(items[at].signedValue), services.serviceKind(identity(items[at + 1].signedValue))});
        }
        return result;
    }
    std::vector<unsigned char> literalBytes(Operands &values) {
        const auto &slice = values.take(OperandRole::LiteralBytes);
        const auto length = range(slice.sliceBegin, slice.sliceCount, sizeValue(input.sourceByteCount)).second;
        // Source ranges are immutable identity references and may repeat. Charge
        // every materialized occurrence, including identical literal payloads.
        charge(length, sizeof(unsigned char));
        auto bytes = services.literalBytes(slice.sliceBegin, slice.sliceCount);
        if (bytes.size() != length)
            invalidLowering();
        return bytes;
    }
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
    ir::Instruction instructionValue(const wire::OutputRow &header, Operands &values) {
        // Generated Aurora enum types are consumed directly. Every case spells
        // the exact ordered transport fields; defaults never fill omitted data.
        switch (header.instructionForm) {
        case InstructionForm::BindServiceParameter:
            return ir::BindServiceParameter{
                values.integer(OperandRole::Index), values.integer(OperandRole::Offset), serviceKind(values)};
        case InstructionForm::AcquireServiceLoan:
            return ir::AcquireServiceLoan{
                values.integer(OperandRole::LoanId), values.integer(OperandRole::Offset), serviceKind(values)};
        case InstructionForm::ReleaseServiceLoan:
            return ir::ReleaseServiceLoan{values.integer(OperandRole::LoanId), serviceKind(values)};
        case InstructionForm::ServiceOperation:
            return ir::ServiceOperation{
                values.integer(OperandRole::Offset),
                services.serviceOperation(identity(values.scalar(OperandRole::ServiceOperationId))),
                values.integer(OperandRole::ResultOffset),
                serviceKind(values)};
        case InstructionForm::ServiceCall:
            return ir::ServiceCall{functionName(values, OperandRole::CalleeSymbolId),
                                   values.integer(OperandRole::LoanId),
                                   values.integer(OperandRole::ResultOffset),
                                   offsets(values, OperandRole::SpanArguments),
                                   serviceKind(values),
                                   additionalServices(values)};
        case InstructionForm::Constant: {
            const auto &payload = values.take();
            auto resultType = type(values, OperandRole::TypeId);
            std::int64_t result;
            if (resultType == Type::U64) {
                if (payload.operandRole != OperandRole::UnsignedConstant)
                    invalidLowering();
                result = std::bit_cast<std::int64_t>(payload.unsignedValue);
            } else {
                if (payload.operandRole != OperandRole::SignedConstant)
                    invalidLowering();
                result = payload.signedValue;
            }
            return ir::Constant{result, std::move(resultType)};
        }
        case InstructionForm::EnumConstant:
            return ir::EnumConstant{type(values, OperandRole::TypeId), values.integer(OperandRole::CaseIndex)};
        case InstructionForm::Load:
            return ir::Load{values.integer(OperandRole::Offset), type(values, OperandRole::TypeId)};
        case InstructionForm::Store:
            return ir::Store{values.integer(OperandRole::Offset), type(values, OperandRole::TypeId)};
        case InstructionForm::Push:
            return ir::Push{};
        case InstructionForm::Pop:
            return ir::Pop{};
        case InstructionForm::UnaryValue:
            return ir::UnaryValue{unary(header.unaryOperation), type(values, OperandRole::OperandTypeId)};
        case InstructionForm::BinaryValue:
            return ir::BinaryValue{binary(header.binaryOperation), type(values, OperandRole::OperandTypeId)};
        case InstructionForm::Convert:
            return ir::Convert{type(values, OperandRole::SourceTypeId), type(values, OperandRole::ResultTypeId)};
        case InstructionForm::Compare:
            return ir::Compare{comparison(header.comparisonOperation), type(values, OperandRole::OperandTypeId)};
        case InstructionForm::BoundsGuard:
            return ir::BoundsGuard{values.integer(OperandRole::Offset),
                                   values.integer(OperandRole::Length),
                                   type(values, OperandRole::ElementTypeId)};
        case InstructionForm::IndexLoad:
            return ir::IndexLoad{values.integer(OperandRole::Offset),
                                 values.integer(OperandRole::Length),
                                 type(values, OperandRole::ElementTypeId)};
        case InstructionForm::IndexStore:
            return ir::IndexStore{values.integer(OperandRole::Offset),
                                  values.integer(OperandRole::Length),
                                  type(values, OperandRole::ElementTypeId)};
        case InstructionForm::BorrowHandle:
            return ir::BorrowHandle{values.integer(OperandRole::OwnerOffset),
                                    type(values, OperandRole::ReferenceTypeId)};
        case InstructionForm::Call:
            return ir::Call{functionName(values, OperandRole::CalleeSymbolId)};
        case InstructionForm::AggregateCall:
            return ir::AggregateCall{functionName(values, OperandRole::CalleeSymbolId),
                                     offsets(values, OperandRole::ObjectArguments),
                                     values.integer(OperandRole::ResultOffset),
                                     offsets(values, OperandRole::SpanArguments)};
        case InstructionForm::BeginObject:
            return ir::BeginObject{values.integer(OperandRole::Offset)};
        case InstructionForm::InitializeEmptyObject:
            return ir::InitializeEmptyObject{values.integer(OperandRole::Offset)};
        case InstructionForm::EndObject:
            return ir::EndObject{values.integer(OperandRole::Offset)};
        case InstructionForm::CopyObject:
            return ir::CopyObject{values.integer(OperandRole::SourceOffset), values.integer(OperandRole::ResultOffset)};
        case InstructionForm::ObjectFieldCopy:
            return ir::ObjectFieldCopy{values.integer(OperandRole::SourceOffset),
                                       values.integer(OperandRole::FieldIndex),
                                       values.integer(OperandRole::ResultOffset)};
        case InstructionForm::AssignObjectField:
            return ir::AssignObjectField{values.integer(OperandRole::ObjectOffset),
                                         values.integer(OperandRole::FieldIndex),
                                         values.integer(OperandRole::SourceOffset)};
        case InstructionForm::InitializeObjectField:
            return ir::InitializeObjectField{values.integer(OperandRole::ObjectOffset),
                                             values.integer(OperandRole::FieldIndex),
                                             values.integer(OperandRole::SourceOffset)};
        case InstructionForm::InitializeClassArray:
            return ir::InitializeClassArray{values.integer(OperandRole::ObjectOffset),
                                            values.integer(OperandRole::FieldIndex),
                                            offsets(values, OperandRole::Sources)};
        case InstructionForm::ClassArrayBoundsGuard:
            return ir::ClassArrayBoundsGuard{values.integer(OperandRole::ObjectOffset),
                                             values.integer(OperandRole::FieldIndex)};
        case InstructionForm::ClassArrayCopy:
            return ir::ClassArrayCopy{values.integer(OperandRole::ObjectOffset),
                                      values.integer(OperandRole::FieldIndex),
                                      values.integer(OperandRole::ResultOffset)};
        case InstructionForm::ClassArrayAssign:
            return ir::ClassArrayAssign{values.integer(OperandRole::ObjectOffset),
                                        values.integer(OperandRole::FieldIndex),
                                        values.integer(OperandRole::SourceOffset)};
        case InstructionForm::ReceiverLoad:
            return ir::ReceiverLoad{values.integer(OperandRole::FieldIndex), type(values, OperandRole::TypeId)};
        case InstructionForm::ReceiverStore:
            return ir::ReceiverStore{values.integer(OperandRole::FieldIndex), type(values, OperandRole::TypeId)};
        case InstructionForm::ReceiverArrayZero:
            return ir::ReceiverArrayZero{values.integer(OperandRole::FieldIndex)};
        case InstructionForm::ReceiverBoundsGuard:
            return ir::ReceiverBoundsGuard{values.integer(OperandRole::FieldIndex)};
        case InstructionForm::ReceiverIndexLoad:
            return ir::ReceiverIndexLoad{values.integer(OperandRole::FieldIndex)};
        case InstructionForm::ReceiverIndexStore:
            return ir::ReceiverIndexStore{values.integer(OperandRole::FieldIndex)};
        case InstructionForm::MethodCall:
            return ir::MethodCall{functionName(values, OperandRole::CalleeSymbolId),
                                  values.integer(OperandRole::ReceiverOffset),
                                  offsets(values, OperandRole::ObjectArguments),
                                  values.integer(OperandRole::ResultOffset),
                                  values.integer(OperandRole::ReceiverFieldIndex),
                                  offsets(values, OperandRole::SpanArguments)};
        case InstructionForm::MetadataQuery:
            return ir::MetadataQuery{query(header.queryOperation), moduleScope(values)};
        case InstructionForm::Label:
            return ir::Label{values.integer(OperandRole::LabelId)};
        case InstructionForm::Jump:
            return ir::Jump{values.integer(OperandRole::Target)};
        case InstructionForm::BranchFalse:
            return ir::BranchFalse{values.integer(OperandRole::Target)};
        case InstructionForm::Return:
            return ir::Return{};
        case InstructionForm::ReturnObject:
            return ir::ReturnObject{values.integer(OperandRole::Offset)};
        case InstructionForm::BindParameter:
            return ir::BindParameter{values.integer(OperandRole::Index),
                                     values.integer(OperandRole::Offset),
                                     type(values, OperandRole::TypeId)};
        case InstructionForm::BindObjectParameter:
            return ir::BindObjectParameter{
                values.integer(OperandRole::Index), values.integer(OperandRole::Offset), className(values)};
        case InstructionForm::BeginArray:
            return ir::BeginArray{values.integer(OperandRole::Offset)};
        case InstructionForm::EndArray:
            return ir::EndArray{values.integer(OperandRole::Offset)};
        case InstructionForm::BorrowSpan:
            return ir::BorrowSpan{values.integer(OperandRole::ArrayOffset), values.integer(OperandRole::ResultOffset)};
        case InstructionForm::BorrowReceiverArraySpan:
            return ir::BorrowReceiverArraySpan{values.integer(OperandRole::FieldIndex),
                                               values.integer(OperandRole::ResultOffset)};
        case InstructionForm::BorrowLiteralSpan:
            return ir::BorrowLiteralSpan{literalBytes(values), values.integer(OperandRole::ResultOffset)};
        case InstructionForm::BorrowOwnedSpan:
            return ir::BorrowOwnedSpan{values.integer(OperandRole::Offset),
                                       values.integer(OperandRole::FieldIndex),
                                       values.integer(OperandRole::ResultOffset)};
        case InstructionForm::ReturnSpan:
            return ir::ReturnSpan{values.integer(OperandRole::Offset)};
        case InstructionForm::ReborrowSpan:
            return ir::ReborrowSpan{values.integer(OperandRole::SourceOffset),
                                    values.integer(OperandRole::ResultOffset)};
        case InstructionForm::Subspan:
            return ir::Subspan{values.integer(OperandRole::SourceOffset), values.integer(OperandRole::ResultOffset)};
        case InstructionForm::EndSpan:
            return ir::EndSpan{values.integer(OperandRole::Offset)};
        case InstructionForm::SpanLength:
            return ir::SpanLength{values.integer(OperandRole::Offset)};
        case InstructionForm::SpanLoad:
            return ir::SpanLoad{values.integer(OperandRole::Offset)};
        case InstructionForm::BindSpanParameter:
            return ir::BindSpanParameter{values.integer(OperandRole::Index), values.integer(OperandRole::Offset)};
        case InstructionForm::BeginBytes:
            return ir::BeginBytes{values.integer(OperandRole::Offset)};
        case InstructionForm::AllocateBytes:
            return ir::AllocateBytes{values.integer(OperandRole::RegionOffset),
                                     values.integer(OperandRole::ResultOffset)};
        case InstructionForm::AllocateValues:
            return ir::AllocateValues{values.integer(OperandRole::RegionOffset),
                                      values.integer(OperandRole::ResultOffset),
                                      values.integer(OperandRole::FillOffset)};
        case InstructionForm::ValuesLoad:
            return ir::ValuesLoad{values.integer(OperandRole::Offset),
                                  values.integer(OperandRole::FieldIndex),
                                  values.integer(OperandRole::ResultOffset)};
        case InstructionForm::ValuesStore:
            return ir::ValuesStore{values.integer(OperandRole::Offset),
                                   values.integer(OperandRole::FieldIndex),
                                   values.integer(OperandRole::ValueOffset)};
        case InstructionForm::ValuesResize:
            return ir::ValuesResize{values.integer(OperandRole::Offset),
                                    values.integer(OperandRole::FieldIndex),
                                    values.integer(OperandRole::FillOffset)};
        case InstructionForm::MoveBytes:
            return ir::MoveBytes{values.integer(OperandRole::SourceOffset), values.integer(OperandRole::ResultOffset)};
        case InstructionForm::BytesOk:
            return ir::BytesOk{values.integer(OperandRole::Offset), values.integer(OperandRole::FieldIndex)};
        case InstructionForm::BytesLength:
            return ir::BytesLength{values.integer(OperandRole::Offset), values.integer(OperandRole::FieldIndex)};
        case InstructionForm::BytesLoad:
            return ir::BytesLoad{values.integer(OperandRole::Offset), values.integer(OperandRole::FieldIndex)};
        case InstructionForm::BytesStore:
            return ir::BytesStore{values.integer(OperandRole::Offset), values.integer(OperandRole::FieldIndex)};
        case InstructionForm::BytesResize:
            return ir::BytesResize{values.integer(OperandRole::Offset), values.integer(OperandRole::FieldIndex)};
        case InstructionForm::EndBytes:
            return ir::EndBytes{values.integer(OperandRole::Offset)};
        case InstructionForm::BindRegionParameter:
            return ir::BindRegionParameter{values.integer(OperandRole::Index), values.integer(OperandRole::Offset)};
        case InstructionForm::BindBytesParameter:
            return ir::BindBytesParameter{values.integer(OperandRole::Index), values.integer(OperandRole::Offset)};
        case InstructionForm::ResourceCall:
            return ir::ResourceCall{functionName(values, OperandRole::CalleeSymbolId),
                                    values.integer(OperandRole::RegionOffset),
                                    offsets(values, OperandRole::OwnerArguments),
                                    values.integer(OperandRole::ResultOffset),
                                    values.integer(OperandRole::ReceiverOffset)};
        case InstructionForm::ReturnBytes:
            return ir::ReturnBytes{values.integer(OperandRole::Offset)};
        case InstructionForm::InitializeBytesField:
            return ir::InitializeBytesField{values.integer(OperandRole::ObjectOffset),
                                            values.integer(OperandRole::FieldIndex),
                                            values.integer(OperandRole::SourceOffset)};
        case InstructionForm::MoveObject:
            return ir::MoveObject{values.integer(OperandRole::SourceOffset), values.integer(OperandRole::ResultOffset)};
        case InstructionForm::BindOwnedObjectParameter:
            return ir::BindOwnedObjectParameter{
                values.integer(OperandRole::Index), values.integer(OperandRole::Offset), className(values)};
        case InstructionForm::ReturnOwnedObject:
            return ir::ReturnOwnedObject{values.integer(OperandRole::Offset)};
        case InstructionForm::AcquireObjectLoan:
            return ir::AcquireObjectLoan{values.integer(OperandRole::LoanId),
                                         values.integer(OperandRole::Root),
                                         values.boolean(OperandRole::MutableValue)};
        case InstructionForm::ReleaseObjectLoan:
            return ir::ReleaseObjectLoan{values.integer(OperandRole::LoanId)};
        case InstructionForm::BorrowedCall:
            return ir::BorrowedCall{functionName(values, OperandRole::CalleeSymbolId),
                                    values.integer(OperandRole::ReceiverOffset),
                                    values.integer(OperandRole::LoanId),
                                    offsets(values, OperandRole::ObjectArguments),
                                    values.integer(OperandRole::ResultOffset),
                                    offsets(values, OperandRole::SpanArguments),
                                    values.integer(OperandRole::SecondReceiverOffset),
                                    values.integer(OperandRole::SecondLoanId)};
        }
        invalidLowering();
    }
    ir::Instruction instruction(std::int64_t id, RecordKind kind = RecordKind::Instruction) {
        const auto &header = own(id, kind);
        Operands values(*this, header);
        auto result = instructionValue(header, values);
        values.finish();
        return result;
    }
    void slot(ir::Function &function, std::int64_t id) {
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
            break;
        default:
            invalidLowering();
        }
        Operands values(*this, own(id, kind));
        const auto offset = values.integer(OperandRole::Offset);
        switch (kind) {
        case RecordKind::ScalarSlot:
            insertUnique(function.slots, offset, type(values, OperandRole::TypeId));
            break;
        case RecordKind::ObjectSlot: {
            auto name = classOrCarrier(values);
            const auto mutableValue = values.boolean(OperandRole::MutableValue);
            insertUnique(function.objectSlots, offset, ir::ObjectSlot{std::move(name), mutableValue});
            break;
        }
        case RecordKind::ArraySlot:
            insertUnique(function.arraySlots, offset, values.integer(OperandRole::Length));
            break;
        case RecordKind::SpanSlot:
            insertUnique(function.spanSlots, offset);
            break;
        case RecordKind::ServiceSlot:
            insertUnique(function.serviceSlots, offset);
            break;
        case RecordKind::RegionSlot:
            insertUnique(function.regionSlots, offset);
            break;
        case RecordKind::ByteSlot:
            insertUnique(function.byteSlots, offset, values.boolean(OperandRole::MutableValue));
            break;
        case RecordKind::OwnedValueType:
            insertUnique(function.ownedValueTypes, offset, className(values));
            break;
        default:
            invalidLowering();
        }
        values.finish();
    }
    ir::Receiver receiver(std::int64_t id) {
        Operands values(*this, own(id, RecordKind::Receiver));
        ir::Receiver result{className(values),
                            values.boolean(OperandRole::MutableValue),
                            values.boolean(OperandRole::Constructor),
                            values.boolean(OperandRole::PublicAccess)};
        values.finish();
        return result;
    }
    ir::Function function(std::int64_t id) {
        Operands values(*this, own(id, RecordKind::Function));
        ir::Function result;
        result.name = functionName(values, OperandRole::FunctionSymbolId);
        result.moduleScope = moduleScope(values);
        result.result = type(values, OperandRole::ResultTypeId);
        result.parameters = types(values, OperandRole::ParameterTypes);
        const auto slots = rows(values, OperandRole::Slots);
        for (const auto &item : slots)
            slot(result, item.signedValue);
        const auto &receiverOperand = values.take();
        if (receiverOperand.operandRole == OperandRole::ReceiverRef)
            result.receiver = receiver(receiverOperand.signedValue);
        else if (receiverOperand.operandRole != OperandRole::NoReceiver)
            invalidLowering();
        result.borrowedParameter = values.boolean(OperandRole::BorrowedParameter);
        const auto &secondReceiverOperand = values.take();
        if (secondReceiverOperand.operandRole == OperandRole::SecondReceiverRef)
            result.secondBorrowedParameter = receiver(secondReceiverOperand.signedValue);
        else if (secondReceiverOperand.operandRole != OperandRole::NoSecondReceiver)
            invalidLowering();
        const auto &spanOperand = values.take();
        if (spanOperand.operandRole == OperandRole::ReceiverSpanField)
            result.receiverSpanField = intValue(spanOperand.signedValue);
        else if (spanOperand.operandRole != OperandRole::NoReceiverSpan)
            invalidLowering();
        result.frameBytes = values.integer(OperandRole::FrameBytes);
        const auto code = rows(values, OperandRole::Code);
        values.finish();
        charge(code.size(), sizeof(ir::Instruction));
        result.code.reserve(code.size());
        for (const auto &item : code)
            result.code.push_back(instruction(item.signedValue));
        return result;
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
    ir::ClassStorage storage(std::int64_t id) {
        Operands values(*this, own(id, RecordKind::ClassStorage));
        ir::ClassStorage result{offsets(values, OperandRole::LeafOffsets),
                                offsets(values, OperandRole::FieldOffsets),
                                values.integer(OperandRole::SizeBytes),
                                values.integer(OperandRole::Alignment),
                                values.integer(OperandRole::ReservedBytes)};
        values.finish();
        return result;
    }
    void classRecord(ir::Module &module, std::int64_t id) {
        Operands values(*this, own(id, RecordKind::Class));
        auto name = classOrCarrier(values);
        auto leaves = types(values, OperandRole::LeafTypes);
        const auto fieldRows = rows(values, OperandRole::Fields);
        charge(fieldRows.size(), sizeof(ir::ClassField));
        std::vector<ir::ClassField> fields;
        fields.reserve(fieldRows.size());
        for (const auto &item : fieldRows)
            fields.push_back(field(item.signedValue));
        auto layout = storage(values.scalar(OperandRole::StorageRef));
        values.finish();
        insertUnique(module.classLayouts, name, std::move(leaves));
        insertUnique(module.classFields, name, std::move(fields));
        insertUnique(module.classStorage, std::move(name), std::move(layout));
    }
    void carrier(ir::Module &module, std::int64_t id) {
        Operands values(*this, own(id, RecordKind::Carrier));
        const auto elementType = type(values, OperandRole::ElementTypeId);
        const auto count = values.integer(OperandRole::ElementCount);
        values.finish();
        // The producer explicitly selected a private class-array carrier. This
        // check only establishes the native nominal-name domain used to spell it.
        if (elementType.kind != TypeKind::Class)
            invalidLowering();
        auto name = "@array:" + elementType.className + ":" + std::to_string(count);
        insertUnique(module.classArrayCarriers, name);
        insertUnique(carrierNames, id, std::move(name));
    }
    void descriptor(ir::Module &module, std::int64_t id) {
        Operands values(*this, own(id, RecordKind::Descriptor));
        const auto publicId = intValue(identity(values.scalar(OperandRole::PublicDescriptorId)));
        const ir::Descriptor result{values.scalar(OperandRole::Size), values.scalar(OperandRole::PublicFields)};
        values.finish();
        insertUnique(module.descriptors, publicId, result);
    }
    void descriptorView(ir::Module &module, std::int64_t id) {
        Operands values(*this, own(id, RecordKind::DescriptorView));
        const auto scope = moduleScope(values);
        const auto items = list(values.take(OperandRole::VisibleDescriptors), OperandRole::PublicDescriptorId);
        values.finish();
        charge(items.size(), sizeof(int));
        std::set<int> visible;
        for (const auto &item : items) {
            const auto publicId = intValue(identity(item.signedValue));
            if (!module.descriptors.contains(publicId))
                invalidLowering();
            insertUnique(visible, publicId);
        }
        // Insert even an empty view; the Module constructor's legacy root view
        // is cleared before any transport rows are consumed.
        insertUnique(module.descriptorViews, scope, std::move(visible));
    }
    void enumeration(ir::Module &module, std::int64_t id) {
        Operands values(*this, own(id, RecordKind::EnumCases));
        auto name = services.enumName(identity(values.scalar(OperandRole::EnumNominalId)));
        const auto count = values.integer(OperandRole::CaseCount);
        values.finish();
        insertUnique(module.enumCases, std::move(name), count);
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
        if (input.rows.size() < sizeValue(hostedLoweringPreludeRows) || input.moduleRoot < hostedLoweringPreludeRows)
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
        identity(configuration.scalar(OperandRole::SupportedServiceGroups));
        configuration.finish();
        for (std::int64_t at = 2; at < 9; ++at) {
            Operands scalar(*this, own(at, RecordKind::ScalarContract));
            (void)type(scalar, OperandRole::TypeId);
            intValue(identity(scalar.scalar(OperandRole::PublicDescriptorId)));
            scalar.scalar(OperandRole::Size);
            scalar.finish();
        }
        for (std::int64_t at = 9; at < 14; ++at) {
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
        Operands layoutOrder(*this, own(14, RecordKind::InitialLayoutOrder));
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
            !services.literalBytes)
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
        result.module.descriptorViews.clear();
        // Carrier names are shared output identities. Materialize their owning
        // list once before following nonowning CarrierId references elsewhere.
        for (const auto &item : carriers)
            carrier(result.module, item.signedValue);
        charge(functions.size(), sizeof(ir::Function));
        result.module.functions.reserve(functions.size());
        std::set<std::string> functionNames;
        for (const auto &item : functions) {
            auto next = function(item.signedValue);
            insertUnique(functionNames, next.name);
            result.module.functions.push_back(std::move(next));
        }
        for (const auto &item : classes)
            classRecord(result.module, item.signedValue);
        for (const auto &item : descriptors)
            descriptor(result.module, item.signedValue);
        for (const auto &item : views)
            descriptorView(result.module, item.signedValue);
        for (const auto &item : enums)
            enumeration(result.module, item.signedValue);
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
