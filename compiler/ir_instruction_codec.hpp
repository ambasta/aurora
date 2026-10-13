#pragma once
#include "ir.hpp"
#include <type_traits>
#include <utility>

namespace aurora::ir::detail {
// One closed field walk serves source reads, durable observations, raw fixture
// writes and count cursors. Cursors own storage mechanics and identity domains;
// ordered operation shape is defined only here.
using InstructionForm = hosted_abi::compiler_lowering::InstructionForm;
using OperandRole = hosted_abi::compiler_lowering::OperandRole;
template<class Operation> struct InstructionCodec {
    static_assert(!std::is_same_v<Operation, Operation>, "unhandled typed IR instruction codec operation");
};

template<> struct InstructionCodec<BindServiceParameter> {
    static constexpr auto form = InstructionForm::BindServiceParameter;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Index, value.index);
        cursor.integer(OperandRole::Offset, value.offset);
        cursor.serviceKind(value.kind);
    }
};

template<> struct InstructionCodec<AcquireServiceLoan> {
    static constexpr auto form = InstructionForm::AcquireServiceLoan;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::LoanId, value.loanId);
        cursor.integer(OperandRole::Offset, value.offset);
        cursor.serviceKind(value.kind);
    }
};

template<> struct InstructionCodec<ReleaseServiceLoan> {
    static constexpr auto form = InstructionForm::ReleaseServiceLoan;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::LoanId, value.loanId);
        cursor.serviceKind(value.kind);
    }
};

template<> struct InstructionCodec<ServiceOperation> {
    static constexpr auto form = InstructionForm::ServiceOperation;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
        cursor.serviceOperation(value.operation);
        cursor.integer(OperandRole::ResultOffset, value.resultOffset);
        cursor.serviceKind(value.kind);
    }
};

template<class Offsets, class Services>
struct InstructionCodec<BasicServiceCall<Offsets, Services>> {
    static constexpr auto form = InstructionForm::ServiceCall;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.callee(value.callee);
        cursor.integer(OperandRole::LoanId, value.loanId);
        cursor.integer(OperandRole::ResultOffset, value.resultOffset);
        cursor.offsets(OperandRole::SpanArguments, value.spanArguments);
        cursor.serviceKind(value.kind);
        cursor.services(value.additionalServices);
        cursor.offsets(OperandRole::ObjectArguments, value.objectArguments);
    }
};

template<> struct InstructionCodec<Constant> {
    static constexpr auto form = InstructionForm::Constant;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.constant(value.value, value.type);
    }
};

template<> struct InstructionCodec<EnumConstant> {
    static constexpr auto form = InstructionForm::EnumConstant;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.type(OperandRole::TypeId, value.type);
        cursor.integer(OperandRole::CaseIndex, value.caseIndex);
    }
};

template<> struct InstructionCodec<Load> {
    static constexpr auto form = InstructionForm::Load;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
        cursor.type(OperandRole::TypeId, value.type);
    }
};

template<> struct InstructionCodec<Store> {
    static constexpr auto form = InstructionForm::Store;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
        cursor.type(OperandRole::TypeId, value.type);
    }
};

template<> struct InstructionCodec<Push> {
    static constexpr auto form = InstructionForm::Push;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        (void)cursor;
        (void)value;
    }
};

template<> struct InstructionCodec<Pop> {
    static constexpr auto form = InstructionForm::Pop;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        (void)cursor;
        (void)value;
    }
};

template<> struct InstructionCodec<UnaryValue> {
    static constexpr auto form = InstructionForm::UnaryValue;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.unary(value.operation);
        cursor.type(OperandRole::OperandTypeId, value.operandType);
    }
};

template<> struct InstructionCodec<BinaryValue> {
    static constexpr auto form = InstructionForm::BinaryValue;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.binary(value.operation);
        cursor.type(OperandRole::OperandTypeId, value.operandType);
    }
};

template<> struct InstructionCodec<Convert> {
    static constexpr auto form = InstructionForm::Convert;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.type(OperandRole::SourceTypeId, value.sourceType);
        cursor.type(OperandRole::ResultTypeId, value.resultType);
    }
};

template<> struct InstructionCodec<Compare> {
    static constexpr auto form = InstructionForm::Compare;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.comparison(value.operation);
        cursor.type(OperandRole::OperandTypeId, value.operandType);
    }
};

template<> struct InstructionCodec<BoundsGuard> {
    static constexpr auto form = InstructionForm::BoundsGuard;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
        cursor.integer(OperandRole::Length, value.length);
        cursor.type(OperandRole::ElementTypeId, value.elementType);
    }
};

template<> struct InstructionCodec<IndexLoad> {
    static constexpr auto form = InstructionForm::IndexLoad;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
        cursor.integer(OperandRole::Length, value.length);
        cursor.type(OperandRole::ElementTypeId, value.elementType);
    }
};

template<> struct InstructionCodec<IndexStore> {
    static constexpr auto form = InstructionForm::IndexStore;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
        cursor.integer(OperandRole::Length, value.length);
        cursor.type(OperandRole::ElementTypeId, value.elementType);
    }
};

template<> struct InstructionCodec<BorrowHandle> {
    static constexpr auto form = InstructionForm::BorrowHandle;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::OwnerOffset, value.ownerOffset);
        cursor.type(OperandRole::ReferenceTypeId, value.referenceType);
    }
};

template<> struct InstructionCodec<Call> {
    static constexpr auto form = InstructionForm::Call;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.callee(value.callee);
    }
};

template<class Offsets>
struct InstructionCodec<BasicAggregateCall<Offsets>> {
    static constexpr auto form = InstructionForm::AggregateCall;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.callee(value.callee);
        cursor.offsets(OperandRole::ObjectArguments, value.objectArguments);
        cursor.integer(OperandRole::ResultOffset, value.resultOffset);
        cursor.offsets(OperandRole::SpanArguments, value.spanArguments);
    }
};

template<> struct InstructionCodec<BeginObject> {
    static constexpr auto form = InstructionForm::BeginObject;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
    }
};

template<> struct InstructionCodec<InitializeEmptyObject> {
    static constexpr auto form = InstructionForm::InitializeEmptyObject;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
    }
};

template<> struct InstructionCodec<EndObject> {
    static constexpr auto form = InstructionForm::EndObject;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
    }
};

template<> struct InstructionCodec<CopyObject> {
    static constexpr auto form = InstructionForm::CopyObject;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::SourceOffset, value.sourceOffset);
        cursor.integer(OperandRole::ResultOffset, value.resultOffset);
    }
};

template<> struct InstructionCodec<ObjectFieldCopy> {
    static constexpr auto form = InstructionForm::ObjectFieldCopy;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::SourceOffset, value.sourceOffset);
        cursor.integer(OperandRole::FieldIndex, value.fieldIndex);
        cursor.integer(OperandRole::ResultOffset, value.resultOffset);
    }
};

template<> struct InstructionCodec<AssignObjectField> {
    static constexpr auto form = InstructionForm::AssignObjectField;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::ObjectOffset, value.objectOffset);
        cursor.integer(OperandRole::FieldIndex, value.fieldIndex);
        cursor.integer(OperandRole::SourceOffset, value.sourceOffset);
    }
};

template<> struct InstructionCodec<InitializeObjectField> {
    static constexpr auto form = InstructionForm::InitializeObjectField;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::ObjectOffset, value.objectOffset);
        cursor.integer(OperandRole::FieldIndex, value.fieldIndex);
        cursor.integer(OperandRole::SourceOffset, value.sourceOffset);
    }
};

template<class Offsets>
struct InstructionCodec<BasicInitializeClassArray<Offsets>> {
    static constexpr auto form = InstructionForm::InitializeClassArray;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::ObjectOffset, value.objectOffset);
        cursor.integer(OperandRole::FieldIndex, value.fieldIndex);
        cursor.offsets(OperandRole::Sources, value.sources);
    }
};

template<> struct InstructionCodec<ClassArrayBoundsGuard> {
    static constexpr auto form = InstructionForm::ClassArrayBoundsGuard;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::ObjectOffset, value.objectOffset);
        cursor.integer(OperandRole::FieldIndex, value.fieldIndex);
    }
};

template<> struct InstructionCodec<ClassArrayCopy> {
    static constexpr auto form = InstructionForm::ClassArrayCopy;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::ObjectOffset, value.objectOffset);
        cursor.integer(OperandRole::FieldIndex, value.fieldIndex);
        cursor.integer(OperandRole::ResultOffset, value.resultOffset);
    }
};

template<> struct InstructionCodec<ClassArrayAssign> {
    static constexpr auto form = InstructionForm::ClassArrayAssign;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::ObjectOffset, value.objectOffset);
        cursor.integer(OperandRole::FieldIndex, value.fieldIndex);
        cursor.integer(OperandRole::SourceOffset, value.sourceOffset);
    }
};

template<> struct InstructionCodec<ReceiverLoad> {
    static constexpr auto form = InstructionForm::ReceiverLoad;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::FieldIndex, value.fieldIndex);
        cursor.type(OperandRole::TypeId, value.type);
    }
};

template<> struct InstructionCodec<ReceiverStore> {
    static constexpr auto form = InstructionForm::ReceiverStore;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::FieldIndex, value.fieldIndex);
        cursor.type(OperandRole::TypeId, value.type);
    }
};

template<> struct InstructionCodec<ReceiverArrayZero> {
    static constexpr auto form = InstructionForm::ReceiverArrayZero;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::FieldIndex, value.fieldIndex);
    }
};

template<> struct InstructionCodec<ReceiverBoundsGuard> {
    static constexpr auto form = InstructionForm::ReceiverBoundsGuard;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::FieldIndex, value.fieldIndex);
    }
};

template<> struct InstructionCodec<ReceiverIndexLoad> {
    static constexpr auto form = InstructionForm::ReceiverIndexLoad;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::FieldIndex, value.fieldIndex);
    }
};

template<> struct InstructionCodec<ReceiverIndexStore> {
    static constexpr auto form = InstructionForm::ReceiverIndexStore;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::FieldIndex, value.fieldIndex);
    }
};

template<class Offsets>
struct InstructionCodec<BasicMethodCall<Offsets>> {
    static constexpr auto form = InstructionForm::MethodCall;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.callee(value.callee);
        cursor.integer(OperandRole::ReceiverOffset, value.receiverOffset);
        cursor.offsets(OperandRole::ObjectArguments, value.objectArguments);
        cursor.integer(OperandRole::ResultOffset, value.resultOffset);
        cursor.integer(OperandRole::ReceiverFieldIndex, value.receiverFieldIndex);
        cursor.offsets(OperandRole::SpanArguments, value.spanArguments);
    }
};

template<> struct InstructionCodec<MetadataQuery> {
    static constexpr auto form = InstructionForm::MetadataQuery;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.query(value.query);
        cursor.moduleScope(value.moduleScope);
    }
};

template<> struct InstructionCodec<Label> {
    static constexpr auto form = InstructionForm::Label;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::LabelId, value.id);
    }
};

template<> struct InstructionCodec<Jump> {
    static constexpr auto form = InstructionForm::Jump;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Target, value.target);
    }
};

template<> struct InstructionCodec<BranchFalse> {
    static constexpr auto form = InstructionForm::BranchFalse;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Target, value.target);
    }
};

template<> struct InstructionCodec<Return> {
    static constexpr auto form = InstructionForm::Return;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        (void)cursor;
        (void)value;
    }
};

template<> struct InstructionCodec<ReturnObject> {
    static constexpr auto form = InstructionForm::ReturnObject;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
    }
};

template<> struct InstructionCodec<BindParameter> {
    static constexpr auto form = InstructionForm::BindParameter;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Index, value.index);
        cursor.integer(OperandRole::Offset, value.offset);
        cursor.type(OperandRole::TypeId, value.type);
    }
};

template<> struct InstructionCodec<BindObjectParameter> {
    static constexpr auto form = InstructionForm::BindObjectParameter;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Index, value.index);
        cursor.integer(OperandRole::Offset, value.offset);
        cursor.className(value.className);
    }
};

template<> struct InstructionCodec<BeginArray> {
    static constexpr auto form = InstructionForm::BeginArray;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
    }
};

template<> struct InstructionCodec<EndArray> {
    static constexpr auto form = InstructionForm::EndArray;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
    }
};

template<> struct InstructionCodec<BorrowSpan> {
    static constexpr auto form = InstructionForm::BorrowSpan;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::ArrayOffset, value.arrayOffset);
        cursor.integer(OperandRole::ResultOffset, value.resultOffset);
    }
};

template<> struct InstructionCodec<BorrowReceiverArraySpan> {
    static constexpr auto form = InstructionForm::BorrowReceiverArraySpan;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::FieldIndex, value.fieldIndex);
        cursor.integer(OperandRole::ResultOffset, value.resultOffset);
    }
};

template<class Literals>
struct InstructionCodec<BasicBorrowLiteralSpan<Literals>> {
    static constexpr auto form = InstructionForm::BorrowLiteralSpan;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.literal(value.bytes);
        cursor.integer(OperandRole::ResultOffset, value.resultOffset);
    }
};

template<> struct InstructionCodec<BorrowOwnedSpan> {
    static constexpr auto form = InstructionForm::BorrowOwnedSpan;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
        cursor.integer(OperandRole::FieldIndex, value.fieldIndex);
        cursor.integer(OperandRole::ResultOffset, value.resultOffset);
    }
};

template<> struct InstructionCodec<ReturnSpan> {
    static constexpr auto form = InstructionForm::ReturnSpan;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
    }
};

template<> struct InstructionCodec<ReborrowSpan> {
    static constexpr auto form = InstructionForm::ReborrowSpan;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::SourceOffset, value.sourceOffset);
        cursor.integer(OperandRole::ResultOffset, value.resultOffset);
    }
};

template<> struct InstructionCodec<Subspan> {
    static constexpr auto form = InstructionForm::Subspan;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::SourceOffset, value.sourceOffset);
        cursor.integer(OperandRole::ResultOffset, value.resultOffset);
    }
};

template<> struct InstructionCodec<EndSpan> {
    static constexpr auto form = InstructionForm::EndSpan;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
    }
};

template<> struct InstructionCodec<SpanLength> {
    static constexpr auto form = InstructionForm::SpanLength;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
    }
};

template<> struct InstructionCodec<SpanLoad> {
    static constexpr auto form = InstructionForm::SpanLoad;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
    }
};

template<> struct InstructionCodec<BindSpanParameter> {
    static constexpr auto form = InstructionForm::BindSpanParameter;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Index, value.index);
        cursor.integer(OperandRole::Offset, value.offset);
    }
};

template<> struct InstructionCodec<BeginBytes> {
    static constexpr auto form = InstructionForm::BeginBytes;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
    }
};

template<> struct InstructionCodec<AllocateBytes> {
    static constexpr auto form = InstructionForm::AllocateBytes;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::RegionOffset, value.regionOffset);
        cursor.integer(OperandRole::ResultOffset, value.resultOffset);
    }
};

template<> struct InstructionCodec<AllocateValues> {
    static constexpr auto form = InstructionForm::AllocateValues;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::RegionOffset, value.regionOffset);
        cursor.integer(OperandRole::ResultOffset, value.resultOffset);
        cursor.integer(OperandRole::FillOffset, value.fillOffset);
    }
};

template<> struct InstructionCodec<ValuesLoad> {
    static constexpr auto form = InstructionForm::ValuesLoad;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
        cursor.integer(OperandRole::FieldIndex, value.fieldIndex);
        cursor.integer(OperandRole::ResultOffset, value.resultOffset);
    }
};

template<> struct InstructionCodec<ValuesStore> {
    static constexpr auto form = InstructionForm::ValuesStore;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
        cursor.integer(OperandRole::FieldIndex, value.fieldIndex);
        cursor.integer(OperandRole::ValueOffset, value.valueOffset);
    }
};

template<> struct InstructionCodec<ValuesResize> {
    static constexpr auto form = InstructionForm::ValuesResize;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
        cursor.integer(OperandRole::FieldIndex, value.fieldIndex);
        cursor.integer(OperandRole::FillOffset, value.fillOffset);
    }
};

template<> struct InstructionCodec<MoveBytes> {
    static constexpr auto form = InstructionForm::MoveBytes;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::SourceOffset, value.sourceOffset);
        cursor.integer(OperandRole::ResultOffset, value.resultOffset);
    }
};

template<> struct InstructionCodec<BytesOk> {
    static constexpr auto form = InstructionForm::BytesOk;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
        cursor.integer(OperandRole::FieldIndex, value.fieldIndex);
    }
};

template<> struct InstructionCodec<BytesLength> {
    static constexpr auto form = InstructionForm::BytesLength;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
        cursor.integer(OperandRole::FieldIndex, value.fieldIndex);
    }
};

template<> struct InstructionCodec<BytesLoad> {
    static constexpr auto form = InstructionForm::BytesLoad;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
        cursor.integer(OperandRole::FieldIndex, value.fieldIndex);
    }
};

template<> struct InstructionCodec<BytesStore> {
    static constexpr auto form = InstructionForm::BytesStore;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
        cursor.integer(OperandRole::FieldIndex, value.fieldIndex);
    }
};

template<> struct InstructionCodec<BytesResize> {
    static constexpr auto form = InstructionForm::BytesResize;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
        cursor.integer(OperandRole::FieldIndex, value.fieldIndex);
    }
};

template<> struct InstructionCodec<EndBytes> {
    static constexpr auto form = InstructionForm::EndBytes;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
    }
};

template<> struct InstructionCodec<BindRegionParameter> {
    static constexpr auto form = InstructionForm::BindRegionParameter;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Index, value.index);
        cursor.integer(OperandRole::Offset, value.offset);
    }
};

template<> struct InstructionCodec<BindBytesParameter> {
    static constexpr auto form = InstructionForm::BindBytesParameter;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Index, value.index);
        cursor.integer(OperandRole::Offset, value.offset);
    }
};

template<class Offsets>
struct InstructionCodec<BasicResourceCall<Offsets>> {
    static constexpr auto form = InstructionForm::ResourceCall;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.callee(value.callee);
        cursor.integer(OperandRole::RegionOffset, value.regionOffset);
        cursor.offsets(OperandRole::OwnerArguments, value.ownerArguments);
        cursor.integer(OperandRole::ResultOffset, value.resultOffset);
        cursor.integer(OperandRole::ReceiverOffset, value.receiverOffset);
    }
};

template<> struct InstructionCodec<ReturnBytes> {
    static constexpr auto form = InstructionForm::ReturnBytes;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
    }
};

template<> struct InstructionCodec<InitializeBytesField> {
    static constexpr auto form = InstructionForm::InitializeBytesField;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::ObjectOffset, value.objectOffset);
        cursor.integer(OperandRole::FieldIndex, value.fieldIndex);
        cursor.integer(OperandRole::SourceOffset, value.sourceOffset);
    }
};

template<> struct InstructionCodec<MoveObject> {
    static constexpr auto form = InstructionForm::MoveObject;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::SourceOffset, value.sourceOffset);
        cursor.integer(OperandRole::ResultOffset, value.resultOffset);
    }
};

template<> struct InstructionCodec<BindOwnedObjectParameter> {
    static constexpr auto form = InstructionForm::BindOwnedObjectParameter;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Index, value.index);
        cursor.integer(OperandRole::Offset, value.offset);
        cursor.className(value.className);
    }
};

template<> struct InstructionCodec<ReturnOwnedObject> {
    static constexpr auto form = InstructionForm::ReturnOwnedObject;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::Offset, value.offset);
    }
};

template<> struct InstructionCodec<AcquireObjectLoan> {
    static constexpr auto form = InstructionForm::AcquireObjectLoan;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::LoanId, value.loanId);
        cursor.integer(OperandRole::Root, value.root);
        cursor.boolean(OperandRole::MutableValue, value.mutableValue);
    }
};

template<> struct InstructionCodec<ReleaseObjectLoan> {
    static constexpr auto form = InstructionForm::ReleaseObjectLoan;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.integer(OperandRole::LoanId, value.loanId);
    }
};

template<class Offsets, class Roots>
struct InstructionCodec<BasicBorrowedCall<Offsets, Roots>> {
    static constexpr auto form = InstructionForm::BorrowedCall;
    template<class Cursor, class Value> static void fields(Cursor &cursor, Value &value) {
        cursor.callee(value.callee);
        cursor.roots(value.roots);
        cursor.offsets(OperandRole::ObjectArguments, value.objectArguments);
        cursor.integer(OperandRole::ResultOffset, value.resultOffset);
        cursor.offsets(OperandRole::SpanArguments, value.spanArguments);
    }
};

template<class Variant, std::size_t Index = 0, class Cursor>
Variant readInstruction(InstructionForm form, Cursor &cursor) {
    if constexpr (Index == std::variant_size_v<Variant>) {
        throw Error(DiagnosticCode::Internal, "invalid instruction form");
    } else {
        using Operation = std::variant_alternative_t<Index, Variant>;
        if (form == InstructionCodec<Operation>::form) {
            auto value = [] {
                if constexpr (std::is_same_v<Operation, UnaryValue>)
                    return Operation{Unary::CheckedNegate};
                else
                    return Operation{};
            }();
            InstructionCodec<Operation>::fields(cursor, value);
            cursor.finish();
            return Variant(std::move(value));
        }
        return readInstruction<Variant, Index + 1>(form, cursor);
    }
}

template<class Variant, class Cursor>
void writeInstruction(const Variant &instruction, Cursor &cursor) {
    std::visit([&](const auto &value) {
        using Operation = std::remove_cvref_t<decltype(value)>;
        cursor.form(InstructionCodec<Operation>::form);
        InstructionCodec<Operation>::fields(cursor, value);
        cursor.finish();
    }, instruction);
}
} // namespace aurora::ir::detail
