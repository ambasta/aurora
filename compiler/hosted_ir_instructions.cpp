#include "hosted_ir_instructions.hpp"
#include "../runtime/hosted_bytes.hpp"
#include <array>
#include <cstring>
#include <limits>
#include <span>
#include <type_traits>

extern "C" {
void aurora_hosted_instructions_create(const void *, void *) noexcept;
void aurora_hosted_instructions_release(void *) noexcept;
std::int64_t aurora_hosted_instructions_allocated(const void *) noexcept;
std::int64_t aurora_hosted_instructions_admit(const void *) noexcept;
std::int64_t aurora_hosted_instructions_structure(const void *) noexcept;
std::int64_t aurora_hosted_instructions_publish(void *) noexcept;
std::int64_t aurora_hosted_instructions_error(const void *) noexcept;
}

namespace aurora::ir {
namespace {
namespace wire = hosted_abi::compiler_ir_instructions;
namespace lowering = hosted_abi::compiler_lowering;
namespace bytes = hosted::bytes;
using Role = lowering::OperandRole;
[[noreturn]] void invalidInstructions() {
    throw Error(DiagnosticCode::Internal, "invalid hosted IR instruction transport");
}
[[noreturn]] void allocationFailure() {
    throw Error(DiagnosticCode::Internal, "hosted IR instruction allocation failed");
}
std::int64_t checkedCount(std::size_t value) {
    if (value > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()))
        invalidInstructions();
    return static_cast<std::int64_t>(value);
}
std::int64_t checkedAdd(std::int64_t a, std::int64_t b) {
    if (a < 0 || b < 0 || a > std::numeric_limits<std::int64_t>::max() - b)
        invalidInstructions();
    return a + b;
}
std::size_t index(std::int64_t value) {
    if (value < 0 || static_cast<std::uint64_t>(value) > std::numeric_limits<std::size_t>::max())
        invalidInstructions();
    return static_cast<std::size_t>(value);
}
int integer(std::int64_t value) {
    if (value < std::numeric_limits<int>::min() || value > std::numeric_limits<int>::max())
        invalidInstructions();
    return static_cast<int>(value);
}
void checkIndex(std::size_t position, std::size_t size) {
    if (position >= size)
        throw std::out_of_range("IR instruction index");
}
void checkRange(std::size_t begin, std::size_t count, std::size_t size) {
    if (begin > size || count > size - begin)
        invalidInstructions();
}
// Closed owner-field/row association. Only physical offsets/strides are learned
// from generated facts; no descriptor, arbitrary stride or owner escapes.
enum class Pool : std::size_t { instructions, operands, literals, codeOrder, bodies, count };
struct Binding { std::size_t offset, ownerBytes, stride; };
constexpr std::array bindings{
    Binding{hosted_abi::instructionStore_instructionsOffset, hosted_abi::instructionStore_instructionsBytes,
            hosted_abi::instructionRawInstructionRowPhysicalBytes},
    Binding{hosted_abi::instructionStore_operandsOffset, hosted_abi::instructionStore_operandsBytes,
            hosted_abi::instructionRawOperandRowPhysicalBytes},
    Binding{hosted_abi::instructionStore_literalsOffset, hosted_abi::instructionStore_literalsBytes, 1},
    Binding{hosted_abi::instructionStore_codeOrderOffset, hosted_abi::instructionStore_codeOrderBytes,
            hosted_abi::instructionCodeRowPhysicalBytes},
    Binding{hosted_abi::instructionStore_bodiesOffset, hosted_abi::instructionStore_bodiesBytes,
            hosted_abi::instructionBodyRowPhysicalBytes},
};
template<Pool> struct Row;
template<> struct Row<Pool::instructions> { using Type = wire::RawInstructionRow; };
template<> struct Row<Pool::operands> { using Type = wire::RawOperandRow; };
template<> struct Row<Pool::codeOrder> { using Type = wire::CodeRow; };
template<> struct Row<Pool::bodies> { using Type = wire::BodyRow; };
template<Pool pool> using RowType = typename Row<pool>::Type;
template<Pool pool> constexpr bool exactRow =
    std::is_standard_layout_v<RowType<pool>> && std::is_trivially_copyable_v<RowType<pool>> &&
    alignof(RowType<pool>) == 8 && sizeof(RowType<pool>) == bindings[static_cast<std::size_t>(pool)].stride;
static_assert(exactRow<Pool::instructions> && exactRow<Pool::operands> &&
              exactRow<Pool::codeOrder> && exactRow<Pool::bodies>);
static_assert(sizeof(wire::RawInstructionRow) == 8 * sizeof(std::int64_t) &&
              sizeof(wire::RawOperandRow) == 5 * sizeof(std::int64_t) &&
              sizeof(wire::CodeRow) == 4 * sizeof(std::int64_t) &&
              sizeof(wire::BodyRow) == 3 * sizeof(std::int64_t));
static_assert(bindings.size() == static_cast<std::size_t>(Pool::count));
static_assert([] {
    for (std::size_t i = 0; i < bindings.size(); ++i) {
        const auto b = bindings[i];
        if (b.ownerBytes != sizeof(bytes::NativeOwner) || b.offset % alignof(bytes::NativeOwner) != 0 ||
            b.offset > sizeof(wire::InstructionStore) || b.ownerBytes > sizeof(wire::InstructionStore) - b.offset)
            return false;
        for (std::size_t j = 0; j < i; ++j)
            if (b.offset < bindings[j].offset + bindings[j].ownerBytes &&
                bindings[j].offset < b.offset + b.ownerBytes)
                return false;
    }
    return true;
}());
static_assert(static_cast<std::int64_t>(lowering::RecordKind::Instruction) == 1);
// Source structural and static admission consume these ordinals. Pin them to
// generated lowering facts rather than maintaining another opcode schema.
static_assert(static_cast<std::int64_t>(lowering::InstructionForm::Label) == 40 &&
              static_cast<std::int64_t>(lowering::InstructionForm::Jump) == 41 &&
              static_cast<std::int64_t>(lowering::InstructionForm::BranchFalse) == 42 &&
              static_cast<std::int64_t>(lowering::InstructionForm::Return) == 43 &&
              static_cast<std::int64_t>(lowering::InstructionForm::ReturnObject) == 44 &&
              static_cast<std::int64_t>(lowering::InstructionForm::ReturnSpan) == 53 &&
              static_cast<std::int64_t>(lowering::InstructionForm::ReturnBytes) == 76 &&
              static_cast<std::int64_t>(lowering::InstructionForm::ReturnOwnedObject) == 80);
static_assert(static_cast<std::int64_t>(lowering::InstructionForm::BindServiceParameter) == 0 &&
              static_cast<std::int64_t>(lowering::InstructionForm::BindParameter) == 45 &&
              static_cast<std::int64_t>(lowering::InstructionForm::BindObjectParameter) == 46 &&
              static_cast<std::int64_t>(lowering::InstructionForm::BindSpanParameter) == 59 &&
              static_cast<std::int64_t>(lowering::InstructionForm::BindRegionParameter) == 73 &&
              static_cast<std::int64_t>(lowering::InstructionForm::BindBytesParameter) == 74 &&
              static_cast<std::int64_t>(lowering::InstructionForm::BindOwnedObjectParameter) == 79);
static_assert(static_cast<std::int64_t>(lowering::InstructionForm::AcquireServiceLoan) == 1 &&
              static_cast<std::int64_t>(lowering::InstructionForm::ReleaseServiceLoan) == 2 &&
              static_cast<std::int64_t>(lowering::InstructionForm::ServiceOperation) == 3);
static_assert(static_cast<std::int64_t>(lowering::InstructionForm::ServiceCall) == 4 &&
              static_cast<std::int64_t>(lowering::InstructionForm::Call) == 19 &&
              static_cast<std::int64_t>(lowering::InstructionForm::AggregateCall) == 20 &&
              static_cast<std::int64_t>(lowering::InstructionForm::MethodCall) == 38 &&
              static_cast<std::int64_t>(lowering::InstructionForm::ResourceCall) == 75 &&
              static_cast<std::int64_t>(lowering::InstructionForm::BorrowedCall) == 83);
static_assert(static_cast<std::int64_t>(lowering::InstructionForm::Load) == 7 &&
              static_cast<std::int64_t>(lowering::InstructionForm::Store) == 8 &&
              static_cast<std::int64_t>(lowering::InstructionForm::BoundsGuard) == 15 &&
              static_cast<std::int64_t>(lowering::InstructionForm::IndexLoad) == 16 &&
              static_cast<std::int64_t>(lowering::InstructionForm::IndexStore) == 17 &&
              static_cast<std::int64_t>(lowering::InstructionForm::BorrowHandle) == 18 &&
              static_cast<std::int64_t>(lowering::InstructionForm::BeginArray) == 47 &&
              static_cast<std::int64_t>(lowering::InstructionForm::EndArray) == 48 &&
              static_cast<std::int64_t>(lowering::InstructionForm::BorrowSpan) == 49);
static_assert(static_cast<std::int64_t>(lowering::InstructionForm::Constant) == 5 &&
              static_cast<std::int64_t>(lowering::InstructionForm::EnumConstant) == 6 &&
              static_cast<std::int64_t>(lowering::InstructionForm::UnaryValue) == 11 &&
              static_cast<std::int64_t>(lowering::InstructionForm::BinaryValue) == 12 &&
              static_cast<std::int64_t>(lowering::InstructionForm::Convert) == 13 &&
              static_cast<std::int64_t>(lowering::InstructionForm::Compare) == 14);
static_assert(static_cast<std::int64_t>(lowering::Unary::CheckedNegate) == 0 &&
              static_cast<std::int64_t>(lowering::Unary::LogicalNot) == 1 &&
              static_cast<std::int64_t>(lowering::Unary::BitNot) == 2);
static_assert(static_cast<std::int64_t>(lowering::Binary::CheckedAdd) == 0 &&
              static_cast<std::int64_t>(lowering::Binary::CheckedSubtract) == 1 &&
              static_cast<std::int64_t>(lowering::Binary::CheckedMultiply) == 2 &&
              static_cast<std::int64_t>(lowering::Binary::CheckedDivide) == 3 &&
              static_cast<std::int64_t>(lowering::Binary::CheckedRemainder) == 4 &&
              static_cast<std::int64_t>(lowering::Binary::BitAnd) == 5 &&
              static_cast<std::int64_t>(lowering::Binary::BitOr) == 6 &&
              static_cast<std::int64_t>(lowering::Binary::BitXor) == 7 &&
              static_cast<std::int64_t>(lowering::Binary::ShiftLeft) == 8 &&
              static_cast<std::int64_t>(lowering::Binary::ShiftRight) == 9);
static_assert(static_cast<std::int64_t>(lowering::Comparison::Equal) == 0 &&
              static_cast<std::int64_t>(lowering::Comparison::NotEqual) == 1 &&
              static_cast<std::int64_t>(lowering::Comparison::Less) == 2 &&
              static_cast<std::int64_t>(lowering::Comparison::Greater) == 3 &&
              static_cast<std::int64_t>(lowering::Comparison::LessEqual) == 4 &&
              static_cast<std::int64_t>(lowering::Comparison::GreaterEqual) == 5);
static_assert(static_cast<std::int64_t>(Role::Index) == 1 && static_cast<std::int64_t>(Role::Offset) == 2 &&
              static_cast<std::int64_t>(Role::ServiceKindId) == 3);
static_assert(static_cast<std::int64_t>(Role::LoanId) == 4 && static_cast<std::int64_t>(Role::ResultOffset) == 6 &&
              static_cast<std::int64_t>(Role::ReceiverOffset) == 26 &&
              static_cast<std::int64_t>(Role::ReceiverFieldIndex) == 27 &&
              static_cast<std::int64_t>(Role::RegionOffset) == 34 &&
              static_cast<std::int64_t>(Role::SecondReceiverOffset) == 98 &&
              static_cast<std::int64_t>(Role::SecondLoanId) == 99);
static_assert(static_cast<std::int64_t>(Role::ServiceOperationId) == 5);
static_assert(static_cast<std::int64_t>(service::Kind::Console) == 0 &&
              static_cast<std::int64_t>(service::Kind::Display) == 1 &&
              static_cast<std::int64_t>(service::Kind::IommuEvent) == 2);
static_assert(static_cast<std::int64_t>(service::Operation::Next) == 0 &&
              static_cast<std::int64_t>(service::Operation::Put) == 1 &&
              static_cast<std::int64_t>(service::Operation::Pixel) == 2 &&
              static_cast<std::int64_t>(service::Operation::IommuPoll) == 3 &&
              static_cast<std::int64_t>(service::Operation::IommuAcknowledge) == 4);
// Source operation/kind admission is tied to the closed service table as well
// as its wire ordinals. It does not retain a second native service schema.
static_assert(service::operations.size() == 5 &&
              service::operations[0].operation == service::Operation::Next &&
              service::operations[0].kind == service::Kind::Console &&
              service::operations[1].operation == service::Operation::Put &&
              service::operations[1].kind == service::Kind::Console &&
              service::operations[2].operation == service::Operation::Pixel &&
              service::operations[2].kind == service::Kind::Display &&
              service::operations[3].operation == service::Operation::IommuPoll &&
              service::operations[3].kind == service::Kind::IommuEvent &&
              service::operations[4].operation == service::Operation::IommuAcknowledge &&
              service::operations[4].kind == service::Kind::IommuEvent);
static_assert(static_cast<std::int64_t>(Role::TypeId) == 12 && static_cast<std::int64_t>(Role::OperandTypeId) == 14 &&
              static_cast<std::int64_t>(Role::SourceTypeId) == 15 && static_cast<std::int64_t>(Role::ResultTypeId) == 16 &&
              static_cast<std::int64_t>(Role::ElementTypeId) == 18 && static_cast<std::int64_t>(Role::ReferenceTypeId) == 20);
static_assert(static_cast<std::int64_t>(Role::SpanArguments) == 8 && static_cast<std::int64_t>(Role::AdditionalServices) == 9 &&
              static_cast<std::int64_t>(Role::ObjectArguments) == 21 && static_cast<std::int64_t>(Role::Sources) == 25 &&
              static_cast<std::int64_t>(Role::OwnerArguments) == 37);
static_assert(static_cast<std::int64_t>(Role::LiteralBytes) == 33 && static_cast<std::int64_t>(Role::UnsignedConstant) == 11 &&
              static_cast<std::int64_t>(Role::CalleeName) == 100 && static_cast<std::int64_t>(Role::ClassName) == 101);
static_assert(static_cast<std::int64_t>(Role::SignedConstant) == 10 && static_cast<std::int64_t>(Role::CaseIndex) == 13);
using Capacities = std::array<std::int64_t, static_cast<std::size_t>(Pool::count)>;
Capacities capacities(const wire::InstructionCounts &counts) {
    return {counts.instructionCount, counts.operandCount, counts.literalCount, counts.instructionCount, counts.bodyCount};
}
std::uint64_t quota(const Capacities &limits) {
    const auto maximum = static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max());
    std::uint64_t total = 0;
    for (std::size_t i = 0; i < limits.size(); ++i) {
        if (limits[i] < 0)
            invalidInstructions();
        const auto count = static_cast<std::uint64_t>(limits[i]);
        if (count > (maximum - total) / bindings[i].stride)
            invalidInstructions();
        total += count * bindings[i].stride;
    }
    return total;
}
class SourceOwner {
    hosted_abi::InstructionsRelease release_;
public:
    SourceOwner(std::uint64_t region, const wire::InstructionCounts &counts) {
        release_.region = region;
        hosted_abi::InstructionsCreate create;
        create.region = region;
        create.counts = counts;
        aurora_hosted_instructions_create(&create, data());
    }
    ~SourceOwner() { aurora_hosted_instructions_release(&release_); }
    SourceOwner(const SourceOwner &) = delete;
    SourceOwner &operator=(const SourceOwner &) = delete;
    void *data() { return release_.store.storage.data(); }
    const void *data() const { return release_.store.storage.data(); }
    bytes::NativeOwner descriptor(Pool pool) const {
        bytes::NativeOwner value;
        std::memcpy(&value, release_.store.storage.data() + bindings[static_cast<std::size_t>(pool)].offset,
                    sizeof(value));
        return value;
    }
};
} // namespace

class Instructions::State {
public:
    bytes::Region region;
    SourceOwner owner;
    wire::InstructionCounts counts;
    Capacities limits;
    std::array<std::span<const std::byte>, static_cast<std::size_t>(Pool::count)> pools;
    const Metadata *metadata = nullptr;
    bool published = false;
    explicit State(const wire::InstructionCounts &input)
        : region(quota(capacities(input))), owner(region.id(), input), counts(input), limits(capacities(input)) {}
    template<Pool pool> void set(std::int64_t at, const RowType<pool> &value) {
        auto descriptor = owner.descriptor(pool);
        if (bytes::__au_runtime_values_set(&descriptor, at, static_cast<std::int64_t>(sizeof(value)), &value) != 1)
            invalidInstructions();
    }
    template<Pool pool> RowType<pool> row(std::size_t at) const {
        const auto data = pools[static_cast<std::size_t>(pool)];
        if (at >= data.size() / sizeof(RowType<pool>))
            invalidInstructions();
        RowType<pool> value;
        std::memcpy(&value, data.data() + at * sizeof(value), sizeof(value));
        return value;
    }
    void observe() {
        for (std::size_t i = 0; i < bindings.size(); ++i) {
            const auto data = region.observeMetadataBytes(owner.descriptor(static_cast<Pool>(i)));
            if (data.size() != index(limits[i]) * bindings[i].stride)
                invalidInstructions();
            pools[i] = data;
        }
    }
};

Instructions::Instructions() = default;
Instructions::~Instructions() = default;
InstructionIngress::InstructionIngress() = default;
InstructionIngress::~InstructionIngress() = default;
InstructionIngress::InstructionIngress(InstructionIngress &&) noexcept = default;
InstructionIngress &InstructionIngress::operator=(InstructionIngress &&other) noexcept {
    if (this != &other) {
        instructions_.reset();
        metadata_ = std::move(other.metadata_);
        instructions_ = std::move(other.instructions_);
    }
    return *this;
}

std::int64_t detail::InstructionWriter::count(std::size_t value) { return checkedCount(value); }
std::int64_t detail::InstructionWriter::add(std::int64_t left, std::int64_t right) { return checkedAdd(left, right); }
void detail::InstructionWriter::operand(std::int64_t at, const Operand &value) {
    if (allocated_)
        instructions_->state_->set<Pool::operands>(at, value);
}
void detail::InstructionWriter::literal(std::int64_t at, unsigned char value) {
    auto descriptor = instructions_->state_->owner.descriptor(Pool::literals);
    if (bytes::__au_runtime_bytes_set(&descriptor, at, value) != 1)
        invalidInstructions();
}
void detail::InstructionWriter::instruction(const Row &value) {
    if (!inBody_)
        invalidInstructions();
    if (allocated_) {
        instructions_->state_->set<Pool::instructions>(position_.instructionCount, value);
        wire::CodeRow code{};
        code.instructionId = add(position_.instructionCount, 1);
        code.targetPosition = -1;
        instructions_->state_->set<Pool::codeOrder>(position_.instructionCount, code);
    }
    position_.instructionCount = add(position_.instructionCount, 1);
}
void detail::InstructionWriter::beginBody(std::size_t callableId) {
    if (inBody_ || count(callableId) != position_.bodyCount)
        invalidInstructions();
    inBody_ = true;
    bodyBegin_ = position_.instructionCount;
}
void detail::InstructionWriter::endBody() {
    if (!inBody_)
        invalidInstructions();
    wire::BodyRow body;
    body.codeBegin = bodyBegin_;
    body.codeCapacity = body.retainedCount = position_.instructionCount - bodyBegin_;
    if (allocated_)
        instructions_->state_->set<Pool::bodies>(position_.bodyCount, body);
    position_.bodyCount = add(position_.bodyCount, 1);
    inBody_ = false;
}
void detail::InstructionWriter::allocate() {
    if (allocated_ || inBody_)
        invalidInstructions();
    instructions_.reset(new Instructions);
    instructions_->state_ = std::make_unique<Instructions::State>(position_);
    const auto allocated = aurora_hosted_instructions_allocated(instructions_->state_->owner.data());
    if (allocated == 0)
        allocationFailure();
    if (allocated != 1)
        invalidInstructions();
    allocated_ = true;
    position_ = {};
    bodyBegin_ = 0;
}
InstructionIngress detail::InstructionWriter::take() && {
    auto metadata = std::move(metadata_).take();
    if (!allocated_ || inBody_ || !instructions_ || !metadata.state_ ||
        capacities(position_) != instructions_->state_->limits)
        invalidInstructions();
    InstructionIngress result;
    result.metadata_ = std::move(metadata);
    result.instructions_ = std::move(instructions_);
    return result;
}
detail::InstructionWriter::Cursor::Cursor(InstructionWriter &writer, bool measuring, std::int64_t prefixLimit)
    : writer_(writer), measuring_(measuring), prefixLimit_(prefixLimit) {
    row_.recordKind = static_cast<std::int64_t>(lowering::RecordKind::Instruction);
    row_.operandBegin = writer.position_.operandCount;
}
void detail::InstructionWriter::Cursor::emit(Operand value) {
    if (!measuring_)
        writer_.operand(add(row_.operandBegin, prefix_), value);
    prefix_ = add(prefix_, 1);
}
void detail::InstructionWriter::Cursor::scalar(OperandRole role, std::int64_t value) {
    Operand row{};
    row.operandRole = static_cast<std::int64_t>(role);
    row.signedValue = value;
    emit(row);
}
void detail::InstructionWriter::Cursor::slice(OperandRole role, std::int64_t begin, std::int64_t count) {
    Operand row{};
    row.operandRole = static_cast<std::int64_t>(role);
    row.sliceBegin = begin;
    row.sliceCount = count;
    emit(row);
}
void detail::InstructionWriter::Cursor::name(OperandRole role, const std::string &value) {
    if (measuring_) {
        slice(role, 0, 0);
        return;
    }
    const auto text = writer_.metadata_.text(value);
    slice(role, text.firstByte, text.byteCount);
}
void detail::InstructionWriter::Cursor::form(InstructionForm value) { row_.instructionForm = static_cast<std::int64_t>(value); }
void detail::InstructionWriter::Cursor::finish() {
    if (measuring_)
        return;
    if (prefix_ != prefixLimit_)
        invalidInstructions();
    row_.operandCount = prefix_;
    writer_.instruction(row_);
    writer_.position_.operandCount = add(row_.operandBegin, add(prefix_, nested_));
}
void detail::InstructionWriter::Cursor::integer(OperandRole role, const int &value) { scalar(role, value); }
void detail::InstructionWriter::Cursor::boolean(OperandRole role, const bool &value) { scalar(role, value ? 1 : 0); }
void detail::InstructionWriter::Cursor::type(OperandRole role, const Type &value) {
    scalar(role, measuring_ ? 0 : writer_.metadata_.instructionType(value));
}
void detail::InstructionWriter::Cursor::callee(const std::string &value) { name(OperandRole::CalleeName, value); }
void detail::InstructionWriter::Cursor::className(const std::string &value) { name(OperandRole::ClassName, value); }
void detail::InstructionWriter::Cursor::moduleScope(const int &value) { scalar(OperandRole::ModuleScope, value); }
void detail::InstructionWriter::Cursor::serviceKind(const service::Kind &value) { scalar(OperandRole::ServiceKindId, static_cast<std::int64_t>(value)); }
void detail::InstructionWriter::Cursor::serviceOperation(const service::Operation &value) { scalar(OperandRole::ServiceOperationId, static_cast<std::int64_t>(value)); }
void detail::InstructionWriter::Cursor::unary(const Unary &value) { row_.unaryOperation = static_cast<std::int64_t>(value); }
void detail::InstructionWriter::Cursor::binary(const Binary &value) { row_.binaryOperation = static_cast<std::int64_t>(value); }
void detail::InstructionWriter::Cursor::comparison(const Comparison &value) { row_.comparisonOperation = static_cast<std::int64_t>(value); }
void detail::InstructionWriter::Cursor::query(const Query &value) { row_.queryOperation = static_cast<std::int64_t>(value); }
void detail::InstructionWriter::Cursor::constant(const std::int64_t &value, const Type &kind) {
    if (kind.kind == TypeKind::U64) {
        Operand row{};
        row.operandRole = static_cast<std::int64_t>(OperandRole::UnsignedConstant);
        row.unsignedValue = std::bit_cast<std::uint64_t>(value);
        emit(row);
    } else {
        scalar(OperandRole::SignedConstant, value);
    }
    type(OperandRole::TypeId, kind);
}

class Instructions::ReadCursor {
    const Instructions &instructions_;
    wire::RawInstructionRow row_;
    std::size_t next_ = 0;
    bool checkPayload_;
    bool unary_ = false, binary_ = false, comparison_ = false, query_ = false;
    wire::RawOperandRow take(Role role) {
        if (next_ >= index(row_.operandCount))
            invalidInstructions();
        const auto value = instructions_.state_->row<Pool::operands>(index(row_.operandBegin) + next_++);
        if (value.operandRole != static_cast<std::int64_t>(role))
            invalidInstructions();
        return value;
    }
    std::int64_t scalar(Role role) { return take(role).signedValue; }
    void name(Role role, std::string &value) {
        const auto row = take(role);
        value = instructions_.state_->metadata->instructionText(index(row.sliceBegin), index(row.sliceCount));
    }
public:
    ReadCursor(const Instructions &instructions, wire::RawInstructionRow row, bool checkPayload)
        : instructions_(instructions), row_(row), checkPayload_(checkPayload) {}
    void finish() {
        if (next_ != index(row_.operandCount) || (!unary_ && row_.unaryOperation != 0) ||
            (!binary_ && row_.binaryOperation != 0) || (!comparison_ && row_.comparisonOperation != 0) ||
            (!query_ && row_.queryOperation != 0))
            invalidInstructions();
    }
    void integer(Role role, int &value) { value = ir::integer(scalar(role)); }
    void boolean(Role role, bool &value) {
        const auto raw = scalar(role);
        if (raw != 0 && raw != 1)
            invalidInstructions();
        value = raw == 1;
    }
    void type(Role role, Type &value) { value = instructions_.state_->metadata->instructionTypeAt(index(scalar(role))); }
    void callee(std::string &value) { name(Role::CalleeName, value); }
    void className(std::string &value) { name(Role::ClassName, value); }
    void moduleScope(int &value) { integer(Role::ModuleScope, value); }
    void serviceKind(service::Kind &value) { value = static_cast<service::Kind>(ir::integer(scalar(Role::ServiceKindId))); }
    void serviceOperation(service::Operation &value) { value = static_cast<service::Operation>(ir::integer(scalar(Role::ServiceOperationId))); }
    void unary(Unary &value) { unary_ = true; value = static_cast<Unary>(row_.unaryOperation); }
    void binary(Binary &value) { binary_ = true; value = static_cast<Binary>(row_.binaryOperation); }
    void comparison(Comparison &value) { comparison_ = true; value = static_cast<Comparison>(row_.comparisonOperation); }
    void query(Query &value) { query_ = true; value = static_cast<Query>(row_.queryOperation); }
    void constant(std::int64_t &value, Type &kind) {
        if (next_ >= index(row_.operandCount))
            invalidInstructions();
        const auto row = instructions_.state_->row<Pool::operands>(index(row_.operandBegin) + next_++);
        type(Role::TypeId, kind);
        if (kind.kind == TypeKind::U64) {
            if (row.operandRole != static_cast<std::int64_t>(Role::UnsignedConstant))
                invalidInstructions();
            value = std::bit_cast<std::int64_t>(row.unsignedValue);
        } else {
            if (row.operandRole != static_cast<std::int64_t>(Role::SignedConstant))
                invalidInstructions();
            value = row.signedValue;
        }
    }
    void offsets(Role role, OffsetRange &value) {
        const auto row = take(role);
        value = instructions_.offsets(index(row.sliceBegin), index(row.sliceCount));
        if (checkPayload_)
            for (std::size_t i = 0; i < value.size(); ++i)
                (void)value.at(i);
    }
    void services(ServiceArgumentRange &value) {
        const auto row = take(Role::AdditionalServices);
        if (row.sliceCount % 2 != 0)
            invalidInstructions();
        value = instructions_.services(index(row.sliceBegin), index(row.sliceCount) / 2);
        if (checkPayload_)
            for (std::size_t i = 0; i < value.size(); ++i)
                (void)value.at(i);
    }
    void literal(LiteralRange &value) {
        const auto row = take(Role::LiteralBytes);
        value = instructions_.literals(index(row.sliceBegin), index(row.sliceCount));
    }
};

void Instructions::admit(const Metadata &metadata) {
    if (!state_ || state_->metadata)
        invalidInstructions();
    const std::array<const void *, 2> roots{state_->owner.data(), metadata.sourceOwner()};
    const auto status = aurora_hosted_instructions_admit(roots.data());
    const auto reason = aurora_hosted_instructions_error(state_->owner.data());
    if (status == static_cast<std::int64_t>(wire::InstructionStatus::allocation)) {
        if (reason != static_cast<std::int64_t>(wire::InstructionError::none))
            invalidInstructions();
        allocationFailure();
    }
    if (status == static_cast<std::int64_t>(wire::InstructionStatus::invalid)) {
        const auto message = wire::instructionErrorMessage(static_cast<wire::InstructionError>(reason));
        if (reason == static_cast<std::int64_t>(wire::InstructionError::none) || !message)
            invalidInstructions();
        throw Error(std::string(message));
    }
    if (status != static_cast<std::int64_t>(wire::InstructionStatus::admitted) ||
        reason != static_cast<std::int64_t>(wire::InstructionError::none))
        invalidInstructions();
    state_->metadata = &metadata;
    state_->observe();
    // Generic source checks run before the codec can reconstruct a Type. The
    // single field walk then admits exact shape for every immutable row.
    for (std::size_t i = 0; i < index(state_->counts.instructionCount); ++i)
        (void)read(i + 1, true);
}
void Instructions::structure() {
    if (!state_ || !state_->metadata || state_->published)
        invalidInstructions();
    // Reuse the same immutable metadata owner paired during generic admission.
    const std::array<const void *, 2> roots{state_->owner.data(), state_->metadata->sourceOwner()};
    const auto status = aurora_hosted_instructions_structure(roots.data());
    const auto reason = aurora_hosted_instructions_error(state_->owner.data());
    if (status == static_cast<std::int64_t>(wire::InstructionStatus::invalid)) {
        const auto message = wire::instructionErrorMessage(static_cast<wire::InstructionError>(reason));
        if (reason == static_cast<std::int64_t>(wire::InstructionError::none) || !message)
            invalidInstructions();
        throw Error(std::string(message));
    }
    if (status != static_cast<std::int64_t>(wire::InstructionStatus::structured) ||
        reason != static_cast<std::int64_t>(wire::InstructionError::none))
        invalidInstructions();
}
void Instructions::publish() {
    if (!state_ || !state_->metadata || state_->published || aurora_hosted_instructions_publish(state_->owner.data()) != 1)
        invalidInstructions();
    state_->published = true;
}
InstructionObservation Instructions::read(InstructionId id, bool checkPayload) const {
    if (!state_ || !state_->metadata || id == 0 || id > index(state_->counts.instructionCount))
        invalidInstructions();
    const auto row = state_->row<Pool::instructions>(id - 1);
    ReadCursor cursor(*this, row, checkPayload);
    return detail::readInstruction<InstructionObservation>(static_cast<lowering::InstructionForm>(row.instructionForm), cursor);
}
std::size_t Instructions::bodyCount() const { return state_ && state_->metadata ? index(state_->counts.bodyCount) : 0; }
std::size_t Instructions::bodySize(Metadata::CallableId callable) const {
    checkIndex(callable, bodyCount());
    return index(state_->row<Pool::bodies>(callable).retainedCount);
}
InstructionId Instructions::codeId(Metadata::CallableId callable, CodePosition position) const {
    checkIndex(position, bodySize(callable));
    const auto body = state_->row<Pool::bodies>(callable);
    return index(state_->row<Pool::codeOrder>(index(body.codeBegin) + position).instructionId);
}
InstructionFlow Instructions::codeFlow(Metadata::CallableId callable, CodePosition position) const {
    checkIndex(position, bodySize(callable));
    const auto body = state_->row<Pool::bodies>(callable);
    const auto code = state_->row<Pool::codeOrder>(index(body.codeBegin) + position);
    return {code.targetPosition == -1 ? std::nullopt : std::optional<CodePosition>{index(code.targetPosition)},
            (code.flowFlags & 2) != 0,
            (code.flowFlags & 1) != 0};
}
InstructionObservation Instructions::bodyInstruction(Metadata::CallableId callable, InstructionId id) const {
    checkIndex(callable, bodyCount());
    const auto body = state_->row<Pool::bodies>(callable);
    const auto begin = index(body.codeBegin), capacity = index(body.codeCapacity);
    if (id <= begin || id - begin > capacity)
        invalidInstructions();
    return read(id);
}
InstructionRange Instructions::range(Metadata::CallableId callable) const {
    checkIndex(callable, bodyCount());
    return {*this, callable};
}
int Instructions::offsetAt(std::size_t at) const {
    const auto row = state_->row<Pool::operands>(at);
    if (row.operandRole != static_cast<std::int64_t>(Role::Offset))
        invalidInstructions();
    return integer(row.signedValue);
}
ServiceArgument Instructions::serviceAt(std::size_t at) const {
    const auto loan = state_->row<Pool::operands>(at), kind = state_->row<Pool::operands>(at + 1);
    if (loan.operandRole != static_cast<std::int64_t>(Role::ServiceLoanId) ||
        kind.operandRole != static_cast<std::int64_t>(Role::ServiceKindId))
        invalidInstructions();
    return {integer(loan.signedValue), static_cast<service::Kind>(integer(kind.signedValue))};
}
unsigned char Instructions::literalAt(std::size_t at) const {
    const auto data = state_->pools[static_cast<std::size_t>(Pool::literals)];
    checkIndex(at, data.size());
    return std::to_integer<unsigned char>(data[at]);
}
OffsetRange Instructions::offsets(std::size_t begin, std::size_t count) const {
    checkRange(begin, count, index(state_->counts.operandCount));
    return {*this, begin, count};
}
ServiceArgumentRange Instructions::services(std::size_t begin, std::size_t count) const {
    if (count > std::numeric_limits<std::size_t>::max() / 2)
        invalidInstructions();
    checkRange(begin, count * 2, index(state_->counts.operandCount));
    return {*this, begin, count};
}
LiteralRange Instructions::literals(std::size_t begin, std::size_t count) const {
    checkRange(begin, count, index(state_->counts.literalCount));
    return {*this, begin, count};
}
template<> int InstructionPayloadRange<int>::at(std::size_t position) const {
    checkIndex(position, count_);
    return instructions_->offsetAt(begin_ + position);
}
template<> ServiceArgument InstructionPayloadRange<ServiceArgument>::at(std::size_t position) const {
    checkIndex(position, count_);
    return instructions_->serviceAt(begin_ + position * 2);
}
template<> unsigned char InstructionPayloadRange<unsigned char>::at(std::size_t position) const {
    checkIndex(position, count_);
    return instructions_->literalAt(begin_ + position);
}
std::size_t InstructionRange::size() const { return instructions_ ? instructions_->bodySize(callableId_) : 0; }
InstructionId InstructionRange::idAt(CodePosition position) const {
    if (!instructions_)
        invalidInstructions();
    return instructions_->codeId(callableId_, position);
}
InstructionFlow InstructionRange::flowAt(CodePosition position) const {
    if (!instructions_)
        invalidInstructions();
    return instructions_->codeFlow(callableId_, position);
}
InstructionObservation InstructionRange::instructionById(InstructionId id) const {
    if (!instructions_)
        invalidInstructions();
    return instructions_->bodyInstruction(callableId_, id);
}
InstructionObservation InstructionRange::at(CodePosition position) const { return instructionById(idAt(position)); }
InstructionIngress InstructionIngress::import(Module module) {
    detail::MetadataWriter metadata;
    detail::InstructionWriter instructions(metadata);
    for (int pass = 0; pass < 2; ++pass) {
        metadata.declarations(module);
        metadata.beginInstructions();
        for (std::size_t i = 0; i < module.functions.size(); ++i) {
            instructions.beginBody(i);
            for (const auto &instruction : module.functions[i].code)
                instructions.append(instruction);
            instructions.endBody();
        }
        if (pass == 0) {
            metadata.allocate();
            instructions.allocate();
        }
    }
    return std::move(instructions).take();
}
ValidatedModule::ValidatedModule(std::vector<FunctionBody> functions, std::unique_ptr<Metadata> metadata,
                                 std::unique_ptr<Instructions> instructions)
    : metadataOwner(std::move(metadata)), instructionOwner(std::move(instructions)), contents{std::move(functions)} {}
ValidatedModule::~ValidatedModule() = default;
ValidatedModule::ValidatedModule(ValidatedModule &&) noexcept = default;
ValidatedModule &ValidatedModule::operator=(ValidatedModule &&other) noexcept {
    if (this != &other) {
        contents.functions.clear();
        instructionOwner.reset();
        metadataOwner = std::move(other.metadataOwner);
        instructionOwner = std::move(other.instructionOwner);
        contents = std::move(other.contents);
    }
    return *this;
}
} // namespace aurora::ir
