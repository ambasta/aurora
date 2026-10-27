// One raw-ingress driver consumes reviewed shape/corruption cases. Session and
// destination stores are the actual generated source owners, not fake callbacks.
#include "hosted_lowering.hpp"
#include "hosted_lowering_ingress.hpp"
#include "ir_verify.hpp"
#include "../../runtime/hosted_bytes.hpp"
#include <algorithm>
#include <array>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
namespace abi = aurora::hosted_abi;
namespace wire = abi::compiler_lowering;
namespace resolver = abi::compiler_resolver;
namespace meta = abi::compiler_ir_metadata;
namespace bytes = aurora::hosted::bytes;
using Role = wire::OperandRole;
using Kind = wire::RecordKind;
using Form = wire::InstructionForm;
using I64 = std::int64_t;
void require(bool condition, const std::string &message) {
    if (!condition)
        throw std::runtime_error(message);
}
wire::OperandRow scalar(Role role, I64 value = 0) {
    wire::OperandRow row{};
    row.operandRole = role;
    row.signedValue = value;
    return row;
}
resolver::MetaRow metadata(resolver::MetaTag tag) {
    resolver::MetaRow row{};
    row.tag = tag;
    row.value0 = row.value1 = row.value2 = row.value3 = row.value4 = row.value5 = row.value6 = row.value7 = row.value8 =
        row.value9 = row.value10 = row.value11 = row.value12 = row.value13 = row.value14 = -1;
    return row;
}
struct Shape {
    I64 form;
    std::string name;
    std::vector<I64> roles;
};
struct Fixture {
    std::vector<resolver::MetaRow> metadataRows{64};
    std::vector<wire::OutputRow> rows;
    std::vector<wire::OperandRow> operands;
    std::string source;
    I64 i64Type, u64Type, classType, enumType, functionSymbol, classSymbol, enumSymbol, identifier;
    I64 root = 15, function = -1, constant = -1, returned = -1, view = -1, moduleCount = 1;
    I64 selected = -1, literalBegin = 0;
    std::vector<I64> functions, classes, carriers, descriptors, views, enumerations, diagnostics, code, slots;

    I64 addMeta(resolver::MetaRow row) {
        const auto id = static_cast<I64>(metadataRows.size());
        metadataRows.push_back(row);
        return id;
    }
    I64 type(resolver::ResolvedTypeKind kind, I64 nominal = -1, I64 child = -1, I64 length = 0) {
        auto row = metadata(resolver::MetaTag::concrete_type);
        row.concrete_tag = kind;
        row.value1 = nominal;
        row.value2 = child;
        row.value3 = length;
        return addMeta(row);
    }
    I64 reference(std::string text, I64 owner = -1) {
        auto row = metadata(resolver::MetaTag::source_reference);
        row.value0 = -1;
        row.value1 = static_cast<I64>(source.size());
        source += text;
        row.value2 = static_cast<I64>(source.size());
        row.value9 = owner;
        return addMeta(row);
    }
    I64 symbol(std::string name, resolver::DeclarationKind kind, resolver::NativeMode mode) {
        auto row = metadata(resolver::MetaTag::symbol);
        row.declaration_tag = kind;
        row.native_tag = mode;
        row.value1 = 0;
        const auto id = addMeta(row);
        metadataRows[id].value0 = reference(std::move(name), id);
        return id;
    }
    wire::OperandRow list(Role role, Role item, const std::vector<I64> &values) {
        wire::OperandRow row = scalar(role);
        row.sliceBegin = static_cast<I64>(operands.size());
        row.sliceCount = static_cast<I64>(values.size());
        for (auto value : values)
            operands.push_back(scalar(item, value));
        return row;
    }
    I64 record(Kind kind, std::vector<wire::OperandRow> values, Form form = Form::Push) {
        wire::OutputRow row{};
        row.recordKind = kind;
        row.instructionForm = form;
        row.operandBegin = static_cast<I64>(operands.size());
        row.operandCount = static_cast<I64>(values.size());
        operands.insert(operands.end(), values.begin(), values.end());
        const auto id = static_cast<I64>(rows.size());
        rows.push_back(row);
        return id;
    }
    wire::OperandRow &field(I64 row, I64 index) {
        return operands.at(static_cast<std::size_t>(rows.at(static_cast<std::size_t>(row)).operandBegin + index));
    }
    Fixture() {
        i64Type = type(resolver::ResolvedTypeKind::i64_value);
        u64Type = type(resolver::ResolvedTypeKind::u64_value);
        functionSymbol = symbol("answer", resolver::DeclarationKind::function, resolver::NativeMode::root_entry);
        classSymbol = symbol("C", resolver::DeclarationKind::class_value, resolver::NativeMode::class_value);
        enumSymbol = symbol("E", resolver::DeclarationKind::enumeration, resolver::NativeMode::enumeration);
        classType = type(resolver::ResolvedTypeKind::class_value, classSymbol);
        enumType = type(resolver::ResolvedTypeKind::enum_value, enumSymbol);
        identifier = reference("name");
        literalBegin = static_cast<I64>(source.size());
        source += std::string("A\0\xff", 3);
        record(Kind::DiagnosticPayload,
               {scalar(Role::NoDiagnosticSource), scalar(Role::NoDiagnosticValue), scalar(Role::NoDiagnosticValue)});
        record(Kind::Configuration,
               {scalar(Role::MaximumCopiedByteLeaves, 512),
                scalar(Role::MaximumCopiedNonByteLeaves, 64),
                scalar(Role::MaximumCopiedLeaves, 513),
                scalar(Role::MaximumCopiedBytes, 520),
                scalar(Role::MaximumByteArrayLength, 4096),
                scalar(Role::MaximumScalarArrayLength, 64),
                scalar(Role::AnalysisMode),
                scalar(Role::SupportedServiceGroups, 62)});
        for (I64 at = 0; at < 7; ++at)
            record(Kind::ScalarContract,
                   {scalar(Role::TypeId, i64Type), scalar(Role::PublicDescriptorId, at + 1), scalar(Role::Size, 8)});
        for (I64 at = 0; at < 5; ++at)
            record(Kind::ServiceContract,
                   {scalar(Role::TypeId, i64Type),
                    scalar(Role::ServiceKindId),
                    scalar(Role::ServiceOperationId, at),
                    scalar(Role::IdentifierSourceRef, identifier),
                    scalar(Role::ResultTypeId, i64Type),
                    list(Role::ParameterTypes, Role::TypeId, {})});
        record(Kind::InitialLayoutOrder, {list(Role::InitialLayoutSymbols, Role::ClassNominalId, {})});
        record(Kind::Module, std::vector<wire::OperandRow>(7));
        function = record(Kind::Function,
                          {scalar(Role::FunctionSymbolId, functionSymbol),
                           scalar(Role::ModuleScope),
                           scalar(Role::ResultTypeId, i64Type),
                           list(Role::ParameterTypes, Role::TypeId, {}),
                           list(Role::Slots, Role::OutputRowId, {}),
                           scalar(Role::NoReceiver),
                           scalar(Role::BorrowedRootCount),
                           scalar(Role::BorrowedRootMutability),
                           scalar(Role::NoReceiverSpan),
                           scalar(Role::FrameBytes),
                           list(Role::Code, Role::OutputRowId, {})});
        functions.push_back(function);
        constant = record(
            Kind::Instruction, {scalar(Role::SignedConstant, 42), scalar(Role::TypeId, i64Type)}, Form::Constant);
        returned = record(Kind::Instruction, {}, Form::Return);
        code = {constant, returned};
        view = record(Kind::DescriptorView,
                      {scalar(Role::ModuleScope), list(Role::VisibleDescriptors, Role::PublicDescriptorId, {})});
        views.push_back(view);
    }
    I64 instruction(const Shape &shape, bool discarded) {
        std::vector<wire::OperandRow> values;
        for (auto raw : shape.roles) {
            const auto role = static_cast<Role>(raw);
            if (role == Role::TypeId || role == Role::OperandTypeId || role == Role::SourceTypeId ||
                role == Role::ResultTypeId || role == Role::ElementTypeId || role == Role::ReferenceTypeId) {
                values.push_back(scalar(role, i64Type));
            } else if (role == Role::CalleeSymbolId) {
                values.push_back(scalar(role, functionSymbol));
            } else if (role == Role::ClassNominalId) {
                values.push_back(scalar(role, classSymbol));
            } else if (role == Role::SpanArguments || role == Role::ObjectArguments || role == Role::Sources ||
                       role == Role::OwnerArguments) {
                values.push_back(list(role, Role::Offset, {0, 8}));
            } else if (role == Role::AdditionalServices) {
                auto nested = scalar(role);
                nested.sliceBegin = static_cast<I64>(operands.size());
                nested.sliceCount = 2;
                operands.push_back(scalar(Role::ServiceLoanId, 1));
                operands.push_back(scalar(Role::ServiceKindId));
                values.push_back(nested);
            } else if (role == Role::BorrowedRoots) {
                auto nested = scalar(role);
                nested.sliceBegin = static_cast<I64>(operands.size());
                nested.sliceCount = 3;
                operands.push_back(scalar(Role::Root));
                operands.push_back(scalar(Role::LoanId, 1));
                operands.push_back(scalar(Role::FieldIndex, -1));
                values.push_back(nested);
            } else if (role == Role::LiteralBytes) {
                auto literal = scalar(role);
                literal.sliceBegin = literalBegin;
                literal.sliceCount = 3;
                values.push_back(literal);
            } else {
                values.push_back(scalar(role, role == Role::SignedConstant ? 42 : 0));
            }
        }
        const auto id = record(discarded ? Kind::DiscardedInstruction : Kind::Instruction,
                               std::move(values),
                               static_cast<Form>(shape.form));
        rows[id].unaryOperation = wire::Unary::BitNot;
        rows[id].binaryOperation = wire::Binary::ShiftRight;
        rows[id].comparisonOperation = wire::Comparison::GreaterEqual;
        rows[id].queryOperation = wire::Query::PublicFieldCount;
        if (!discarded)
            code.insert(code.end() - 1, id);
        selected = id;
        return id;
    }
    void declarations() {
        const auto fieldRow = record(Kind::ClassField,
                                     {scalar(Role::ElementTypeId, i64Type),
                                      scalar(Role::FirstLeaf),
                                      scalar(Role::Length, 1),
                                      scalar(Role::Array),
                                      scalar(Role::ElementCount, 1)});
        const auto storage = record(Kind::ClassStorage,
                                    {list(Role::LeafOffsets, Role::Offset, {0}),
                                     list(Role::FieldOffsets, Role::Offset, {0}),
                                     scalar(Role::SizeBytes, 8),
                                     scalar(Role::Alignment, 8),
                                     scalar(Role::ReservedBytes, 8)});
        classes.push_back(record(Kind::Class,
                                 {scalar(Role::ClassNominalId, classSymbol),
                                  list(Role::LeafTypes, Role::TypeId, {i64Type}),
                                  list(Role::Fields, Role::OutputRowId, {fieldRow}),
                                  scalar(Role::StorageRef, storage)}));
        enumerations.push_back(
            record(Kind::EnumCases, {scalar(Role::EnumNominalId, enumSymbol), scalar(Role::CaseCount, 2)}));
        descriptors.push_back(
            record(Kind::Descriptor,
                   {scalar(Role::PublicDescriptorId, 1), scalar(Role::Size, 8), scalar(Role::PublicFields)}));
        field(view, 1) = list(Role::VisibleDescriptors, Role::PublicDescriptorId, {1});
        diagnostics.push_back(record(Kind::UnreadLocal, {scalar(Role::IdentifierSourceRef, identifier)}));
        for (auto kind : {Kind::ScalarSlot,
                          Kind::ObjectSlot,
                          Kind::ArraySlot,
                          Kind::SpanSlot,
                          Kind::ServiceSlot,
                          Kind::RegionSlot,
                          Kind::ByteSlot,
                          Kind::OwnedValueType,
                          Kind::SpanValueType}) {
            std::vector<wire::OperandRow> values{scalar(Role::Offset, static_cast<I64>(slots.size()) * 8)};
            if (kind == Kind::ScalarSlot)
                values.push_back(scalar(Role::TypeId, i64Type));
            if (kind == Kind::ObjectSlot || kind == Kind::OwnedValueType || kind == Kind::SpanValueType)
                values.push_back(scalar(Role::ClassNominalId, classSymbol));
            if (kind == Kind::ObjectSlot || kind == Kind::ByteSlot)
                values.push_back(scalar(Role::MutableValue, 1));
            if (kind == Kind::ArraySlot)
                values.push_back(scalar(Role::Length, 1));
            slots.push_back(record(kind, std::move(values)));
        }
        const auto receiver = record(Kind::Receiver,
                                     {scalar(Role::ClassNominalId, classSymbol),
                                      scalar(Role::MutableValue),
                                      scalar(Role::Constructor),
                                      scalar(Role::PublicAccess, 1)});
        field(function, 5) = scalar(Role::ReceiverRef, receiver);
    }
    void finish() {
        field(function, 4) = list(Role::Slots, Role::OutputRowId, slots);
        field(function, 10) = list(Role::Code, Role::OutputRowId, code);
        std::array groups{functions, classes, carriers, descriptors, views, enumerations, diagnostics};
        const std::array roles{Role::Functions,
                               Role::Classes,
                               Role::Carriers,
                               Role::Descriptors,
                               Role::DescriptorViews,
                               Role::Enumerations,
                               Role::LintDiagnostics};
        for (std::size_t at = 0; at < groups.size(); ++at)
            field(root, static_cast<I64>(at)) = list(roles[at], Role::OutputRowId, groups[at]);
        auto module = metadata(resolver::MetaTag::module_unit);
        module.value0 = 0;
        module.value1 = static_cast<I64>(source.size());
        module.value13 = 0;
        metadataRows[0] = module;
        if (moduleCount == 2) {
            auto other = module;
            other.value13 = 1;
            metadataRows[1] = other;
        }
    }
};

struct Allocations {
    std::size_t attempts = 0, successes = 0, releases = 0;
    std::size_t failAt = std::numeric_limits<std::size_t>::max();
    static void *allocate(void *context, std::size_t size) noexcept {
        auto &self = *static_cast<Allocations *>(context);
        if (self.attempts++ == self.failAt)
            return nullptr;
        void *result = std::malloc(size);
        if (result)
            ++self.successes;
        return result;
    }
    static void release(void *context, void *pointer) noexcept {
        auto &self = *static_cast<Allocations *>(context);
        ++self.releases;
        std::free(pointer);
    }
    bytes::Allocator allocator() {
        return {this, allocate, release};
    }
};
class RawSession {
    bytes::Region region_;
    abi::ResolverRelease owner_{};
    bool live_ = false;
    void count(std::size_t offset, I64 value) {
        std::memcpy(data() + offset, &value, sizeof(value));
    }
    template <class Row> void fill(std::size_t offset, const std::vector<Row> &rows) {
        bytes::NativeOwner descriptor{};
        std::memcpy(&descriptor, data() + offset, sizeof(descriptor));
        Row empty{};
        require(bytes::__au_runtime_values_resize(&descriptor, static_cast<I64>(rows.size()), sizeof(Row), &empty) == 1,
                "raw Session row allocation failed");
        std::memcpy(data() + offset, &descriptor, sizeof(descriptor));
        for (std::size_t at = 0; at < rows.size(); ++at)
            require(bytes::__au_runtime_values_set(&descriptor, static_cast<I64>(at), sizeof(Row), &rows[at]) == 1,
                    "raw Session row write failed");
    }

public:
    explicit RawSession(const Fixture &fixture) : region_(64 * 1024 * 1024) {
        owner_.region = region_.id();
        abi::ResolverCreate create{};
        create.region = region_.id();
        aurora_hosted_resolver_create(&create, data());
        live_ = true;
        fill(abi::projectionSession_metadataOffset, fixture.metadataRows);
        fill(abi::projectionSession_outputRowsOffset, fixture.rows);
        fill(abi::projectionSession_outputOperandsOffset, fixture.operands);
        bytes::NativeOwner descriptor{};
        std::memcpy(&descriptor, data() + abi::projectionSession_sourcesOffset, sizeof(descriptor));
        require(bytes::__au_runtime_bytes_resize(&descriptor, static_cast<I64>(fixture.source.size())) == 1,
                "raw source allocation failed");
        std::memcpy(data() + abi::projectionSession_sourcesOffset, &descriptor, sizeof(descriptor));
        for (std::size_t at = 0; at < fixture.source.size(); ++at)
            require(bytes::__au_runtime_bytes_set(
                        &descriptor, static_cast<I64>(at), static_cast<unsigned char>(fixture.source[at])) == 1,
                    "raw source write failed");
        count(abi::projectionSession_source_usedOffset, static_cast<I64>(fixture.source.size()));
        count(abi::projectionSession_meta_usedOffset, static_cast<I64>(fixture.metadataRows.size()));
        count(abi::projectionSession_output_usedOffset, static_cast<I64>(fixture.rows.size()));
        count(abi::projectionSession_operand_usedOffset, static_cast<I64>(fixture.operands.size()));
        count(abi::projectionSession_modulesOffset, fixture.moduleCount);
    }
    ~RawSession() {
        release();
    }
    std::byte *data() {
        return owner_.session.storage.data();
    }
    std::uint64_t used() const {
        return region_.metrics().used;
    }
    void release() {
        if (live_) {
            aurora_hosted_resolver_release(&owner_);
            live_ = false;
            require(region_.metrics().used == 0 && region_.metrics().live_allocations == 0,
                    "Session release retained source owners");
        }
    }
};
struct Workspace {
    abi::ProjectionRelease owner{};
    Workspace(std::uint64_t region, const Fixture &fixture, I64 names) {
        owner.region = region;
        abi::ProjectionCreate create{};
        create.region = region;
        create.outputs = static_cast<I64>(fixture.rows.size());
        create.operands = static_cast<I64>(fixture.operands.size());
        create.metadata = static_cast<I64>(fixture.metadataRows.size());
        create.nameCapacity = names;
        aurora_hosted_projection_create(&create, data());
    }
    ~Workspace() {
        aurora_hosted_projection_release(&owner);
    }
    void *data() {
        return owner.workspace.storage.data();
    }
};
namespace instructions = abi::compiler_ir_instructions;
bytes::NativeOwner descriptor(const void *store, std::size_t offset) {
    bytes::NativeOwner result{};
    std::memcpy(&result, static_cast<const std::byte *>(store) + offset, sizeof(result));
    return result;
}
template <class Row> Row readRow(const void *store, std::size_t offset, I64 index) {
    const auto owner = descriptor(store, offset);
    Row row{};
    bytes::__au_runtime_values_at(&owner, index, sizeof(Row), &row);
    return row;
}
std::string readText(const void *store, meta::ByteRange range) {
    const auto owner = descriptor(store, abi::metadataStore_bytesOffset);
    std::string result;
    for (I64 at = 0; at < range.byteCount; ++at)
        result.push_back(static_cast<char>(bytes::__au_runtime_bytes_at(&owner, range.firstByte + at)));
    return result;
}
struct PendingStores {
    bytes::Region region{64 * 1024 * 1024};
    abi::MetadataRelease metadata{};
    abi::InstructionsRelease instructions{};
    bool metadataLive = false, instructionsLive = false;
    ~PendingStores() {
        if (instructionsLive)
            aurora_hosted_instructions_release(&instructions);
        if (metadataLive)
            aurora_hosted_metadata_release(&metadata);
        require(region.metrics().used == 0 && region.metrics().live_allocations == 0,
                "pending raw stores leaked allocations");
    }
    void *metadataData() {
        return metadata.store.storage.data();
    }
    void *instructionData() {
        return instructions.store.storage.data();
    }
    void allocate(const meta::InputCounts &counts,
                  I64 callables,
                  I64 slots,
                  I64 instructionBegin,
                  const instructions::InstructionCounts &code) {
        metadata.region = instructions.region = region.id();
        abi::MetadataCreate create{};
        create.region = region.id();
        aurora_hosted_metadata_create(&create, metadataData());
        metadataLive = true;
        abi::MetadataInitialize initialize{};
        initialize.counts = counts;
        initialize.callableCount = callables;
        initialize.slotCount = slots;
        initialize.instructionBegin = instructionBegin;
        require(aurora_hosted_metadata_initialize(metadataData(), &initialize) == 1,
                "pending metadata allocation failed");
        abi::InstructionsCreate codeCreate{};
        codeCreate.region = region.id();
        codeCreate.instructionCount = code.instructionCount;
        codeCreate.operandCount = code.operandCount;
        codeCreate.literalCount = code.literalCount;
        codeCreate.bodyCount = code.bodyCount;
        aurora_hosted_instructions_create(&codeCreate, instructionData());
        instructionsLive = true;
        require(aurora_hosted_instructions_allocated(instructionData()) == 1, "pending instruction allocation failed");
    }
};
I64 fillRaw(const Fixture &fixture,
            PendingStores &pending,
            meta::InputCounts &metadataCounts,
            instructions::InstructionCounts &counts) {
    RawSession session(fixture);
    I64 instructionTypeBegin = -1;
    {
        bytes::Region region(64 * 1024 * 1024);
        {
            Workspace workspace(region.id(), fixture, aurora_hosted_projection_name_capacity(session.data()));
            require(aurora::ir::detail::LoweringIngress::measure(session.data(), workspace.data(), fixture.root, 0) ==
                        1,
                    "raw shape measure failed");
            aurora_hosted_projection_metadata_counts(workspace.data(), &metadataCounts);
            aurora_hosted_projection_instruction_counts(workspace.data(), &counts);
            instructionTypeBegin = aurora_hosted_projection_count(workspace.data(), 12);
            pending.allocate(metadataCounts,
                             aurora_hosted_projection_count(workspace.data(), 10),
                             aurora_hosted_projection_count(workspace.data(), 11),
                             instructionTypeBegin,
                             counts);
            const std::array<const void *, 4> roots{
                session.data(), workspace.data(), pending.metadataData(), pending.instructionData()};
            require(aurora_hosted_projection_fill(roots.data()) == 2, "raw shape fill failed");
        }
        require(region.metrics().used == 0, "shape workspace retained allocations");
    }
    session.release();
    return instructionTypeBegin;
}
void observeShape(const Fixture &fixture) {
    PendingStores pending;
    meta::InputCounts metadataCounts{};
    instructions::InstructionCounts counts{};
    const auto instructionTypeBegin = fillRaw(fixture, pending, metadataCounts, counts);
    // Observe only the surviving durable owners. Expected active fields come
    // from the reviewed case roles and constants; no semantic oracle is rebuilt.
    require(counts.instructionCount == static_cast<I64>(fixture.code.size()) && counts.bodyCount == 1,
            "retained/discarded instruction counts changed");
    const auto body = readRow<instructions::BodyRow>(pending.instructionData(), abi::instructionStore_bodiesOffset, 0);
    require(body.codeBegin == 0 && body.codeCapacity == counts.instructionCount &&
                body.retainedCount == counts.instructionCount && body.unreachableAfter == 0,
            "pending body order changed");
    I64 nextOperand = 0, nextLiteral = 0, nextType = instructionTypeBegin;
    for (I64 ordinal = 0; ordinal < counts.instructionCount; ++ordinal) {
        const auto &source = fixture.rows[fixture.code[ordinal]];
        const auto row = readRow<instructions::RawInstructionRow>(
            pending.instructionData(), abi::instructionStore_instructionsOffset, ordinal);
        const auto order =
            readRow<instructions::CodeRow>(pending.instructionData(), abi::instructionStore_codeOrderOffset, ordinal);
        require(row.recordKind == 1 && row.instructionForm == static_cast<I64>(source.instructionForm) &&
                    row.operandCount == source.operandCount && row.operandBegin == nextOperand &&
                    order.instructionId == ordinal + 1 && order.targetPosition == -1 && order.flowFlags == 0 &&
                    order.scratchValue == 0,
                "raw opcode, prefix or immutable code identity changed");
        if (source.instructionForm == Form::UnaryValue)
            require(row.unaryOperation == static_cast<I64>(wire::Unary::BitNot), "unary operator changed");
        if (source.instructionForm == Form::BinaryValue)
            require(row.binaryOperation == static_cast<I64>(wire::Binary::ShiftRight), "binary operator changed");
        if (source.instructionForm == Form::Compare)
            require(row.comparisonOperation == static_cast<I64>(wire::Comparison::GreaterEqual), "comparison changed");
        if (source.instructionForm == Form::MetadataQuery)
            require(row.queryOperation == static_cast<I64>(wire::Query::PublicFieldCount), "query changed");
        nextOperand += row.operandCount;
        for (I64 field = 0; field < row.operandCount; ++field) {
            const auto &input = fixture.operands[source.operandBegin + field];
            const auto value = readRow<instructions::RawOperandRow>(
                pending.instructionData(), abi::instructionStore_operandsOffset, row.operandBegin + field);
            const auto role = input.operandRole;
            const auto expectedRole = role == Role::CalleeSymbolId   ? Role::CalleeName
                                      : role == Role::ClassNominalId ? Role::ClassName
                                                                     : role;
            require(value.operandRole == static_cast<I64>(expectedRole), "raw operand role changed");
            if (role == Role::TypeId || role == Role::OperandTypeId || role == Role::SourceTypeId ||
                role == Role::ResultTypeId || role == Role::ElementTypeId || role == Role::ReferenceTypeId) {
                require(value.signedValue == nextType++, "occurrence-owned instruction types are not a strict suffix");
                const auto type = readRow<meta::RawTypeRow>(
                    pending.metadataData(), abi::metadataStore_typesOffset, value.signedValue);
                require(type.typeKind == 0 && type.nameRange.byteCount == 0 && type.rawTail.elementKind == 0 &&
                            type.rawTail.arrayLength == 0 && type.rawTail.elementParameterBytes == 0 &&
                            type.rawTail.lengthParameterBytes == 0 && type.rawTail.templateArgumentCount == 0,
                        "reviewed scalar type tail changed");
            } else if (role == Role::CalleeSymbolId || role == Role::ClassNominalId) {
                require(readText(pending.metadataData(), {value.sliceBegin, value.sliceCount}) ==
                            (role == Role::CalleeSymbolId ? "answer" : "C"),
                        "durable nominal/linkage name changed");
            } else if (role == Role::LiteralBytes) {
                require(value.sliceBegin == nextLiteral && value.sliceCount == 3, "literal packing changed");
                const auto owner = descriptor(pending.instructionData(), abi::instructionStore_literalsOffset);
                const std::array<unsigned, 3> expected{65, 0, 255};
                for (I64 at = 0; at < 3; ++at)
                    require(bytes::__au_runtime_bytes_at(&owner, nextLiteral + at) == expected[at],
                            "literal bytes did not survive Session destruction");
                nextLiteral += 3;
            } else if (role == Role::SpanArguments || role == Role::ObjectArguments || role == Role::Sources ||
                       role == Role::OwnerArguments || role == Role::AdditionalServices ||
                       role == Role::BorrowedRoots) {
                require(value.sliceBegin == nextOperand && value.sliceCount == input.sliceCount,
                        "nested-list order changed");
                for (I64 at = 0; at < input.sliceCount; ++at) {
                    const auto &expected = fixture.operands[input.sliceBegin + at];
                    const auto child = readRow<instructions::RawOperandRow>(
                        pending.instructionData(), abi::instructionStore_operandsOffset, value.sliceBegin + at);
                    require(child.operandRole == static_cast<I64>(expected.operandRole) &&
                                child.signedValue == expected.signedValue && child.unsignedValue == 0 &&
                                child.sliceBegin == 0 && child.sliceCount == 0,
                            "nested operand payload changed");
                }
                nextOperand += input.sliceCount;
            } else {
                require(value.signedValue == input.signedValue && value.unsignedValue == input.unsignedValue &&
                            value.sliceBegin == 0 && value.sliceCount == 0,
                        "scalar instruction payload changed");
            }
        }
    }
    require(nextOperand == counts.operandCount && nextLiteral == counts.literalCount &&
                nextType == metadataCounts.coreCounts.types,
            "durable payload suffix has gaps or extra rows");
}
void project(const Fixture &fixture, bool validate = false) {
    RawSession session(fixture);
    auto output = aurora::projectHostedLowering(session.data(), session.used(), fixture.root, 0);
    // No borrowed source or workspace survives into independent admission.
    session.release();
    if (validate) {
        auto checked = aurora::ir::validate(std::move(output.instructions));
        require(checked.metadata().findCallable("answer") == 0,
                "durable callable name changed after source destruction");
        const auto code = checked.get().functions.at(0).code;
        require(code.size() == 2 && std::get<aurora::ir::Constant>(code.at(0)).value == 42,
                "durable code changed after source destruction");
    }
}
const Shape &find(const std::vector<Shape> &shapes, const std::string &name) {
    const auto found = std::find_if(shapes.begin(), shapes.end(), [&](const auto &shape) {
        return shape.name == name;
    });
    if (found == shapes.end())
        throw std::runtime_error("missing case shape " + name);
    return *found;
}
void variant(Fixture &fixture, const std::string &name, const std::vector<Shape> &shapes) {
    if (name == "lifetime")
        return;
    if (name == "unsigned") {
        fixture.field(fixture.constant, 0).operandRole = Role::UnsignedConstant;
        fixture.field(fixture.constant, 0).signedValue = 0;
        fixture.field(fixture.constant, 0).unsignedValue = std::uint64_t{1} << 63;
        fixture.field(fixture.constant, 1).signedValue = fixture.u64Type;
        return;
    }
    if (name == "synthetic") {
        auto atom = metadata(resolver::MetaTag::atom);
        atom.value2 = fixture.metadataRows[fixture.classSymbol].value0;
        const auto atomId = fixture.addMeta(atom);
        auto prefix = metadata(resolver::MetaTag::prefix);
        prefix.value1 = atomId;
        const auto prefixId = fixture.addMeta(prefix);
        const auto type = fixture.type(resolver::ResolvedTypeKind::enum_value, -prefixId - 2);
        fixture.field(fixture.function, 2).signedValue = type;
        return;
    }
    if (name == "carrier") {
        fixture.carriers.push_back(fixture.record(Kind::Carrier,
                                                  {scalar(Role::ElementTypeId, fixture.classType),
                                                   scalar(Role::ElementCount, std::numeric_limits<int>::min())}));
        return;
    }
    if (name == "declarations") {
        fixture.declarations();
        return;
    }
    if (name == "ordering") {
        fixture.declarations();
        fixture.slots.push_back(
            fixture.record(Kind::ScalarSlot, {scalar(Role::Offset, 24), scalar(Role::TypeId, fixture.u64Type)}));
        fixture.slots.push_back(
            fixture.record(Kind::ScalarSlot, {scalar(Role::Offset, 0), scalar(Role::TypeId, fixture.u64Type)}));
        std::reverse(fixture.slots.begin(), fixture.slots.end());
        for (const auto &name : {"zeta", "alpha"}) {
            const auto symbol =
                fixture.symbol(name, resolver::DeclarationKind::function, resolver::NativeMode::function);
            const auto function = fixture.record(Kind::Function,
                                                 {scalar(Role::FunctionSymbolId, symbol),
                                                  scalar(Role::ModuleScope),
                                                  scalar(Role::ResultTypeId, fixture.i64Type),
                                                  fixture.list(Role::ParameterTypes, Role::TypeId, {}),
                                                  fixture.list(Role::Slots, Role::OutputRowId, {}),
                                                  scalar(Role::NoReceiver),
                                                  scalar(Role::BorrowedRootCount),
                                                  scalar(Role::BorrowedRootMutability),
                                                  scalar(Role::NoReceiverSpan),
                                                  scalar(Role::FrameBytes),
                                                  fixture.list(Role::Code, Role::OutputRowId, {})});
            fixture.functions.push_back(function);
        }
        std::swap(fixture.functions[0], fixture.functions[1]); // zeta, answer, alpha; IDs keep this order.
        for (I64 id : {9, 3})
            fixture.descriptors.push_back(fixture.record(
                Kind::Descriptor,
                {scalar(Role::PublicDescriptorId, id), scalar(Role::Size, id), scalar(Role::PublicFields)}));
        fixture.field(fixture.view, 1) = fixture.list(Role::VisibleDescriptors, Role::PublicDescriptorId, {9, 1, 3});
        fixture.moduleCount = 2;
        fixture.views.insert(
            fixture.views.begin(),
            fixture.record(Kind::DescriptorView,
                           {scalar(Role::ModuleScope, 1),
                            fixture.list(Role::VisibleDescriptors, Role::PublicDescriptorId, {3, 1})}));
        const auto carrier = fixture.record(
            Kind::Carrier, {scalar(Role::ElementTypeId, fixture.classType), scalar(Role::ElementCount, 2)});
        fixture.carriers.push_back(carrier); // No Class row: source supplies the membership-only record.
        const auto symbol =
            fixture.symbol("A", resolver::DeclarationKind::class_value, resolver::NativeMode::class_value);
        const auto storage = fixture.record(Kind::ClassStorage,
                                            {fixture.list(Role::LeafOffsets, Role::Offset, {}),
                                             fixture.list(Role::FieldOffsets, Role::Offset, {}),
                                             scalar(Role::SizeBytes),
                                             scalar(Role::Alignment, 8),
                                             scalar(Role::ReservedBytes, 8)});
        fixture.classes.push_back(fixture.record(Kind::Class,
                                                 {scalar(Role::ClassNominalId, symbol),
                                                  fixture.list(Role::LeafTypes, Role::TypeId, {}),
                                                  fixture.list(Role::Fields, Role::OutputRowId, {}),
                                                  scalar(Role::StorageRef, storage)}));
        const auto enumSymbol =
            fixture.symbol("A_enum", resolver::DeclarationKind::enumeration, resolver::NativeMode::enumeration);
        fixture.enumerations.push_back(
            fixture.record(Kind::EnumCases, {scalar(Role::EnumNominalId, enumSymbol), scalar(Role::CaseCount, 3)}));
        return;
    }
    if (name == "nominal") {
        auto atom = metadata(resolver::MetaTag::atom);
        atom.value2 = fixture.metadataRows[fixture.classSymbol].value0;
        const auto atomId = fixture.addMeta(atom);
        auto prefix = metadata(resolver::MetaTag::prefix);
        prefix.value1 = atomId;
        const auto prefixId = fixture.addMeta(prefix);
        std::vector<I64> values;
        for (I64 argument : {fixture.i64Type, fixture.u64Type}) {
            const auto symbol = fixture.symbol(values.empty() ? "C_t1" : "C_t2",
                                               resolver::DeclarationKind::class_value,
                                               resolver::NativeMode::class_template);
            auto instance = metadata(resolver::MetaTag::instance);
            instance.value1 = 1;
            instance.value2 = argument;
            fixture.metadataRows[symbol].value3 = prefixId;
            fixture.metadataRows[symbol].value9 = fixture.addMeta(instance);
            values.push_back(fixture.type(resolver::ResolvedTypeKind::class_value, symbol));
        }
        const auto array = fixture.type(resolver::ResolvedTypeKind::array_value, -1, values[0], 2);
        const auto owner = fixture.type(resolver::ResolvedTypeKind::owned_values, -1, array);
        const auto span = fixture.type(resolver::ResolvedTypeKind::value_span, -1, values[1]);
        fixture.field(fixture.function, 2).signedValue = owner;
        fixture.field(fixture.function, 3) = fixture.list(Role::ParameterTypes, Role::TypeId, {span});
        return;
    }
    if (name == "empty-body") {
        const auto symbol =
            fixture.symbol("unused", resolver::DeclarationKind::function, resolver::NativeMode::function);
        const auto function = fixture.record(Kind::Function,
                                             {scalar(Role::FunctionSymbolId, symbol),
                                              scalar(Role::ModuleScope),
                                              scalar(Role::ResultTypeId, fixture.i64Type),
                                              fixture.list(Role::ParameterTypes, Role::TypeId, {}),
                                              fixture.list(Role::Slots, Role::OutputRowId, {}),
                                              scalar(Role::NoReceiver),
                                              scalar(Role::BorrowedRootCount),
                                              scalar(Role::BorrowedRootMutability),
                                              scalar(Role::NoReceiverSpan),
                                              scalar(Role::FrameBytes),
                                              fixture.list(Role::Code, Role::OutputRowId, {})});
        fixture.functions.push_back(function);
        return;
    }
    if (name == "duplicate-row") {
        fixture.code.push_back(fixture.constant);
    } else if (name == "overlap-prefix") {
        const auto row = fixture.instruction(find(shapes, "Load"), false);
        fixture.rows[row].operandBegin = fixture.rows[fixture.constant].operandBegin;
    } else if (name == "overlap-list") {
        const auto first = fixture.instruction(find(shapes, "AggregateCall"), false);
        const auto second = fixture.instruction(find(shapes, "AggregateCall"), false);
        auto &fields = fixture.operands;
        const auto begin = fixture.rows[first].operandBegin;
        const auto other = fixture.rows[second].operandBegin;
        for (I64 at = 0; at < fixture.rows[first].operandCount; ++at)
            if (fields[begin + at].operandRole == Role::SpanArguments) {
                fields[other + at] = fields[begin + at];
                break;
            }
    } else if (name == "prelude-root") {
        fixture.root = 14;
    } else if (name == "negative-row") {
        fixture.code.push_back(-1);
    } else if (name == "foreign-row") {
        fixture.code.push_back(std::numeric_limits<I64>::max());
    } else if (name == "bad-range") {
        fixture.rows[fixture.constant].operandBegin = std::numeric_limits<I64>::max();
    } else if (name == "bad-role") {
        fixture.field(fixture.constant, 0).operandRole = Role::Offset;
    } else if (name == "bad-type") {
        fixture.field(fixture.constant, 1).signedValue = fixture.classSymbol;
    } else if (name == "type-cycle") {
        const auto id = fixture.type(resolver::ResolvedTypeKind::owned_values);
        fixture.metadataRows[id].value2 = id;
        fixture.field(fixture.constant, 1).signedValue = id;
    } else if (name == "type-kind") {
        fixture.metadataRows[fixture.i64Type].concrete_tag = static_cast<resolver::ResolvedTypeKind>(999);
    } else if (name == "name-domain") {
        fixture.metadataRows[fixture.functionSymbol].declaration_tag = resolver::DeclarationKind::class_value;
    } else if (name == "name-reference") {
        fixture.metadataRows[fixture.metadataRows[fixture.functionSymbol].value0].value9 = fixture.classSymbol;
    } else if (name == "scope") {
        fixture.field(fixture.function, 1).signedValue = 7;
    } else if (name == "unary") {
        const auto row = fixture.instruction(find(shapes, "UnaryValue"), false);
        fixture.rows[row].unaryOperation = static_cast<wire::Unary>(999);
    } else if (name == "binary") {
        const auto row = fixture.instruction(find(shapes, "BinaryValue"), false);
        fixture.rows[row].binaryOperation = static_cast<wire::Binary>(999);
    } else if (name == "comparison") {
        const auto row = fixture.instruction(find(shapes, "Compare"), false);
        fixture.rows[row].comparisonOperation = static_cast<wire::Comparison>(999);
    } else if (name == "query") {
        const auto row = fixture.instruction(find(shapes, "MetadataQuery"), false);
        fixture.rows[row].queryOperation = static_cast<wire::Query>(999);
    } else if (name == "discarded") {
        fixture.record(Kind::DiscardedInstruction, {scalar(Role::Offset)}, Form::Push);
    } else if (name == "discarded-literal") {
        const auto row = fixture.instruction(find(shapes, "BorrowLiteralSpan"), true);
        for (I64 at = 0; at < fixture.rows[row].operandCount; ++at)
            if (fixture.field(row, at).operandRole == Role::LiteralBytes)
                fixture.field(row, at).sliceCount = std::numeric_limits<I64>::max();
    } else if (name == "service") {
        const auto row = fixture.instruction(find(shapes, "BindServiceParameter"), false);
        fixture.field(row, 2).signedValue = 99;
    } else if (name == "operation") {
        const auto row = fixture.instruction(find(shapes, "ServiceOperation"), false);
        fixture.field(row, 1).signedValue = 99;
    } else if (name == "boolean") {
        const auto row = fixture.instruction(find(shapes, "AcquireObjectLoan"), false);
        fixture.field(row, 2).signedValue = 2;
    } else if (name == "integer") {
        const auto row = fixture.instruction(find(shapes, "Load"), false);
        fixture.field(row, 0).signedValue = std::numeric_limits<I64>::max();
    } else if (name == "roots") {
        const auto row = fixture.instruction(find(shapes, "BorrowedCall"), false);
        fixture.field(row, 1).sliceCount = 2;
    } else if (name == "constant-role") {
        fixture.field(fixture.constant, 1).signedValue = fixture.u64Type;
    } else if (name == "orphan") {
        fixture.record(Kind::Receiver, {});
    } else if (name == "class-duplicate") {
        fixture.declarations();
        fixture.classes.push_back(fixture.classes.front());
    } else if (name == "carrier-duplicate") {
        fixture.carriers.push_back(fixture.record(
            Kind::Carrier, {scalar(Role::ElementTypeId, fixture.classType), scalar(Role::ElementCount, 2)}));
        fixture.carriers.push_back(fixture.record(
            Kind::Carrier, {scalar(Role::ElementTypeId, fixture.classType), scalar(Role::ElementCount, 2)}));
    } else if (name == "identifier") {
        auto &reference = fixture.metadataRows[fixture.identifier];
        reference.value0 = 0;
        reference.value1 = -1;
    } else {
        throw std::runtime_error("unknown case mutation " + name);
    }
}
void observeVariant(const Fixture &fixture, const std::string &variant) {
    PendingStores pending;
    meta::InputCounts counts{};
    instructions::InstructionCounts code{};
    fillRaw(fixture, pending, counts, code);
    if (variant == "ordering") {
        const std::array<std::string, 3> functions{"zeta", "answer", "alpha"};
        for (I64 at = 0; at < 3; ++at) {
            const auto row = readRow<meta::CallableRow>(pending.metadataData(), abi::metadataStore_callablesOffset, at);
            require(readText(pending.metadataData(), row.nameRange) == functions[at],
                    "function-list CallableId order changed");
            const auto index = readRow<meta::IndexRow>(
                pending.metadataData(), abi::metadataStore_indicesOffset, counts.mapCounts.indices - 3 + at);
            require(index.indexValue == 2 - at, "callable-name lookup suffix is not byte sorted");
        }
        const std::array<std::string, 3> classes{"@array:C:2", "A", "C"};
        for (I64 at = 0; at < 3; ++at) {
            const auto row = readRow<meta::ClassRow>(pending.metadataData(), abi::metadataStore_classesOffset, at);
            require(readText(pending.metadataData(), row.nameRange) == classes[at], "nominal class order changed");
            if (at == 0)
                require(row.suppliedStorage == -1 && row.membershipBits == 8 && row.leafRange.indexCount == 0 &&
                            row.fieldRange.indexCount == 0,
                        "membership-only carrier acquired a fabricated layout");
        }
        const std::array<std::string, 2> enums{"A_enum", "E"};
        for (I64 at = 0; at < 2; ++at) {
            const auto row = readRow<meta::EnumRow>(pending.metadataData(), abi::metadataStore_enumsOffset, at);
            require(readText(pending.metadataData(), row.nameRange) == enums[at], "enum byte ordering changed");
        }
        const std::array<I64, 3> descriptorIds{1, 3, 9};
        for (I64 at = 0; at < 3; ++at)
            require(readRow<meta::DescriptorRow>(pending.metadataData(), abi::metadataStore_descriptorsOffset, at)
                            .descriptorId == descriptorIds[at],
                    "numeric descriptor order changed");
        for (I64 at = 0; at < 2; ++at) {
            const auto row = readRow<meta::ViewRow>(pending.metadataData(), abi::metadataStore_viewsOffset, at);
            require(row.moduleScope == at && row.descriptorRange.indexCount == 3 - at, "scope/view ordering changed");
            for (I64 item = 0; item < row.descriptorRange.indexCount; ++item)
                require(readRow<meta::IndexRow>(pending.metadataData(),
                                                abi::metadataStore_indicesOffset,
                                                row.descriptorRange.firstIndex + item)
                                .indexValue == descriptorIds[item],
                        "visible descriptors are not independently sorted");
        }
        const std::array<I64, 11> kinds{10, 10, 10, 11, 12, 13, 14, 15, 16, 17, 27};
        const std::array<I64, 11> offsets{0, 0, 24, 8, 16, 24, 32, 40, 48, 56, 64};
        for (I64 at = 0; at < 11; ++at) {
            const auto row = readRow<meta::SlotRow>(pending.metadataData(), abi::metadataStore_slotsOffset, at);
            require(row.recordKind == kinds[at] && row.slotOffset == offsets[at], "slot kind/offset order changed");
            if (at < 3) {
                const auto type =
                    readRow<meta::RawTypeRow>(pending.metadataData(), abi::metadataStore_typesOffset, row.typeIndex);
                require(type.typeKind == (at == 0 ? 0 : 7), "slot row-ID tie order changed");
            }
        }
    } else if (variant == "nominal") {
        const auto callable = readRow<meta::CallableRow>(pending.metadataData(), abi::metadataStore_callablesOffset, 0);
        const auto owner = readRow<meta::RawTypeRow>(
            pending.metadataData(), abi::metadataStore_typesOffset, callable.typeRange.firstIndex);
        const auto span = readRow<meta::RawTypeRow>(
            pending.metadataData(), abi::metadataStore_typesOffset, callable.typeRange.firstIndex + 1);
        require(owner.typeKind == 17 && owner.rawTail.elementKind == 5 && owner.rawTail.arrayLength == 2 &&
                    readText(pending.metadataData(), owner.nameRange) == "C_t1" && span.typeKind == 21 &&
                    span.rawTail.elementKind == 0 && span.rawTail.arrayLength == 0 &&
                    readText(pending.metadataData(), span.nameRange) == "C_t2",
                "template nominal identities or copied owner/span tails changed");
    } else if (variant == "synthetic") {
        const auto callable = readRow<meta::CallableRow>(pending.metadataData(), abi::metadataStore_callablesOffset, 0);
        const auto type = readRow<meta::RawTypeRow>(
            pending.metadataData(), abi::metadataStore_typesOffset, callable.typeRange.firstIndex);
        require(type.typeKind == 5 && readText(pending.metadataData(), type.nameRange) == "C",
                "synthetic enum prefix no longer retains its raw Class identity");
    } else if (variant == "carrier") {
        const auto row = readRow<meta::ClassRow>(pending.metadataData(), abi::metadataStore_classesOffset, 0);
        require(readText(pending.metadataData(), row.nameRange) == "@array:C:-2147483648" && row.membershipBits == 8,
                "signed carrier spelling changed");
    } else if (variant == "unsigned") {
        const auto row =
            readRow<instructions::RawOperandRow>(pending.instructionData(), abi::instructionStore_operandsOffset, 0);
        require(row.operandRole == static_cast<I64>(Role::UnsignedConstant) &&
                    row.unsignedValue == (std::uint64_t{1} << 63),
                "unsigned high-bit constant lost its value");
    } else if (variant == "declarations") {
        require(counts.coreCounts.classes == 1 && counts.coreCounts.fields == 1 && counts.coreCounts.leaves == 1 &&
                    counts.mapCounts.storage == 1 && counts.mapCounts.descriptors == 1 && counts.mapCounts.views == 1 &&
                    counts.mapCounts.enums == 1,
                "declaration record counts changed");
        const auto callable = readRow<meta::CallableRow>(pending.metadataData(), abi::metadataStore_callablesOffset, 0);
        require(callable.slotRange.indexCount == 9 && callable.receiver.flags == 4 && callable.flags == 1,
                "receiver or complete slot-family metadata changed");
    }
}
void independentUnused(const Fixture &fixture) {
    RawSession session(fixture);
    auto output = aurora::projectHostedLowering(session.data(), session.used(), fixture.root, 0);
    session.release();
    bool rejected = false;
    try {
        (void)aurora::ir::validate(std::move(output.instructions));
    } catch (const aurora::Error &) {
        rejected = true;
    }
    require(rejected, "unused empty function bypassed independent verification");
}
void capacityMismatch(const Fixture &fixture) {
    RawSession session(fixture);
    bytes::Region region(64 * 1024 * 1024);
    Workspace workspace(region.id(), fixture, aurora_hosted_projection_name_capacity(session.data()));
    require(aurora::ir::detail::LoweringIngress::measure(session.data(), workspace.data(), fixture.root, 0) == 1,
            "capacity fixture measure failed");
    meta::InputCounts counts{};
    instructions::InstructionCounts code{};
    aurora_hosted_projection_metadata_counts(workspace.data(), &counts);
    aurora_hosted_projection_instruction_counts(workspace.data(), &code);
    ++counts.coreCounts.types;
    PendingStores pending;
    pending.allocate(counts,
                     aurora_hosted_projection_count(workspace.data(), 10),
                     aurora_hosted_projection_count(workspace.data(), 11),
                     aurora_hosted_projection_count(workspace.data(), 12),
                     code);
    const std::array<const void *, 4> roots{
        session.data(), workspace.data(), pending.metadataData(), pending.instructionData()};
    require(aurora_hosted_projection_fill(roots.data()) == 3, "mismatched destination capacity was accepted");
    const auto type = readRow<meta::RawTypeRow>(pending.metadataData(), abi::metadataStore_typesOffset, 0);
    require(type.typeKind == -1, "capacity rejection wrote a partial destination");
}
void factoryAllocations(const Fixture &fixture) {
    RawSession session(fixture);
    const auto names = aurora_hosted_projection_name_capacity(session.data());
    meta::InputCounts metadataCounts{};
    instructions::InstructionCounts instructionCounts{};
    I64 callables = 0, slots = 0, instructionBegin = 0;
    std::size_t measureAttempts = 0;
    {
        bytes::Region region(64 * 1024 * 1024);
        Workspace workspace(region.id(), fixture, names);
        Allocations allocations;
        require(aurora::ir::detail::LoweringIngress::measure(
                    session.data(), workspace.data(), fixture.root, 0, allocations.allocator()) == 1,
                "injected empty-pair measure failed");
        measureAttempts = allocations.attempts;
        require(allocations.successes == allocations.releases, "empty measure pair leaked allocations");
        aurora_hosted_projection_metadata_counts(workspace.data(), &metadataCounts);
        aurora_hosted_projection_instruction_counts(workspace.data(), &instructionCounts);
        callables = aurora_hosted_projection_count(workspace.data(), 10);
        slots = aurora_hosted_projection_count(workspace.data(), 11);
        instructionBegin = aurora_hosted_projection_count(workspace.data(), 12);
    }
    for (std::size_t at = 0; at < measureAttempts; ++at) {
        bytes::Region region(64 * 1024 * 1024);
        Workspace workspace(region.id(), fixture, names);
        Allocations allocations;
        allocations.failAt = at;
        bool rejected = false;
        try {
            (void)aurora::ir::detail::LoweringIngress::measure(
                session.data(), workspace.data(), fixture.root, 0, allocations.allocator());
        } catch (const aurora::Error &) {
            rejected = true;
        }
        require(rejected && allocations.successes == allocations.releases,
                "empty pending-pair allocation failure escaped cleanup");
    }
    std::size_t exactAttempts = 0;
    {
        Allocations allocations;
        {
            aurora::ir::detail::LoweringIngress pending(
                metadataCounts, callables, slots, instructionBegin, instructionCounts, allocations.allocator());
            exactAttempts = allocations.attempts;
        }
        require(allocations.successes == allocations.releases, "unfilled exact pair leaked allocations");
    }
    for (std::size_t at = 0; at < exactAttempts; ++at) {
        Allocations allocations;
        allocations.failAt = at;
        bool rejected = false;
        try {
            aurora::ir::detail::LoweringIngress pending(
                metadataCounts, callables, slots, instructionBegin, instructionCounts, allocations.allocator());
        } catch (const aurora::Error &) {
            rejected = true;
        }
        require(rejected && allocations.successes == allocations.releases,
                "exact pending-pair allocation failure escaped cleanup");
    }
}
void workspaceLifecycle(const Fixture &fixture) {
    RawSession session(fixture);
    const auto names = aurora_hosted_projection_name_capacity(session.data());
    require(names >= 0, "name capacity failed for valid fixture");
    // Fixed grants are deliberately generous fixture limits, not production
    // policy; failure injection targets the real allocator at each attempted
    // allocation of this one source workspace construction/count operation.
    std::size_t attempts = 0;
    {
        Allocations allocations;
        bytes::Region region(64 * 1024 * 1024, allocations.allocator());
        {
            Workspace workspace(region.id(), fixture, names);
            require(aurora::ir::detail::LoweringIngress::measure(session.data(), workspace.data(), fixture.root, 0) ==
                        1,
                    "workspace measure failed");
            require(aurora::ir::detail::LoweringIngress::measure(session.data(), workspace.data(), fixture.root, 0) ==
                        3,
                    "reused measured workspace was accepted");
            attempts = allocations.attempts;
        }
        require(region.metrics().used == 0 && region.metrics().live_allocations == 0 &&
                    allocations.successes == allocations.releases,
                "measured workspace cleanup leaked allocations");
    }
    for (std::size_t failed = 0; failed < attempts; ++failed) {
        Allocations allocations;
        allocations.failAt = failed;
        bytes::Region region(64 * 1024 * 1024, allocations.allocator());
        {
            Workspace workspace(region.id(), fixture, names);
            const auto status =
                aurora::ir::detail::LoweringIngress::measure(session.data(), workspace.data(), fixture.root, 0);
            require(status == 4, "failed projection allocation did not remain allocation status");
            require(aurora::ir::detail::LoweringIngress::measure(session.data(), workspace.data(), fixture.root, 0) ==
                        4,
                    "failed workspace retry changed terminal status");
        }
        require(region.metrics().used == 0 && region.metrics().live_allocations == 0 &&
                    allocations.successes == allocations.releases,
                "failed workspace cleanup leaked allocations");
    }
}
} // namespace
int main(int argc, char **argv) {
    try {
        require(argc == 2, "usage: hosted-lowering CASES");
        std::ifstream file(argv[1]);
        require(file.good(), "cannot open lowering cases");
        std::vector<Shape> shapes;
        struct Case {
            std::string mode, name, variant;
        };
        std::vector<Case> cases;
        std::string line;
        while (std::getline(file, line)) {
            if (line.empty() || line[0] == '#')
                continue;
            std::istringstream words(line);
            std::string mode;
            words >> mode;
            if (mode == "shape") {
                Shape shape{};
                words >> shape.form >> shape.name;
                for (I64 role; words >> role;)
                    shape.roles.push_back(role);
                shapes.push_back(std::move(shape));
            } else {
                Case value;
                value.mode = mode;
                words >> value.name >> value.variant;
                require(mode == "accept" || mode == "reject", "unknown lowering case mode");
                require(!value.name.empty() && !value.variant.empty(), "incomplete lowering case");
                cases.push_back(std::move(value));
            }
        }
        std::size_t completed = 0;
        for (const auto &shape : shapes)
            for (bool discarded : {false, true}) {
                try {
                    Fixture fixture;
                    fixture.instruction(shape, discarded);
                    fixture.finish();
                    observeShape(fixture);
                    ++completed;
                } catch (const std::exception &error) {
                    throw std::runtime_error(shape.name + (discarded ? " discarded: " : " retained: ") + error.what());
                }
            }
        for (const auto &test : cases) {
            Fixture fixture;
            variant(fixture, test.variant, shapes);
            fixture.finish();
            bool rejected = false;
            try {
                project(fixture, test.variant == "lifetime");
                if (test.mode == "accept" && test.variant != "lifetime")
                    observeVariant(fixture, test.variant);
                if (test.variant == "empty-body")
                    independentUnused(fixture);
            } catch (const aurora::Error &) {
                rejected = true;
            }
            require(rejected == (test.mode == "reject"), test.name + " unexpected projection result");
            ++completed;
        }
        Fixture fixture;
        fixture.finish();
        workspaceLifecycle(fixture);
        factoryAllocations(fixture);
        capacityMismatch(fixture);
        std::cout << "hosted lowering: " << completed << " data cases, lifetime/reuse/allocation cleanup passed\n";
    } catch (const std::exception &error) {
        std::cerr << "hosted lowering: " << error.what() << '\n';
        return 1;
    }
}
