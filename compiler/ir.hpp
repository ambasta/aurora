#pragma once
#include "types.hpp"
#include "hosted_ir_metadata.hpp"
#include "hosted_frontend_abi.hpp"
#include "services.hpp"
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <variant>
#include <vector>

namespace aurora::ir {
inline constexpr int spanBytes = 56;
class Instructions;
class ServiceArgument;
class BorrowedRootArgument;
// Payload ranges borrow the immutable Aurora instruction owner. They copy one
// requested scalar value and never materialize a native payload container.
template <class Value> class InstructionPayloadRange {
    const Instructions *instructions_ = nullptr;
    std::size_t begin_ = 0, count_ = 0;
    InstructionPayloadRange(const Instructions &instructions, std::size_t begin, std::size_t count)
        : instructions_(&instructions), begin_(begin), count_(count) {
    }
    friend class Instructions;

public:
    using value_type = Value;
    InstructionPayloadRange() = default;
    std::size_t size() const noexcept {
        return count_;
    }
    bool empty() const noexcept {
        return count_ == 0;
    }
    Value at(std::size_t index) const;
    Value operator[](std::size_t index) const {
        return at(index);
    }
    Value front() const {
        return at(0);
    }
    Value back() const {
        return at(count_ - 1);
    }
    auto begin() const {
        return MetadataIterator<InstructionPayloadRange>(*this, 0);
    }
    auto end() const {
        return MetadataIterator<InstructionPayloadRange>(*this, count_);
    }
    bool operator==(const InstructionPayloadRange &) const = default;
};
using OffsetRange = InstructionPayloadRange<int>;
using ServiceArgumentRange = InstructionPayloadRange<ServiceArgument>;
using BorrowedRootArgumentRange = InstructionPayloadRange<BorrowedRootArgument>;
using LiteralRange = InstructionPayloadRange<unsigned char>;
template <> int InstructionPayloadRange<int>::at(std::size_t index) const;
template <> ServiceArgument InstructionPayloadRange<ServiceArgument>::at(std::size_t index) const;
template <> BorrowedRootArgument InstructionPayloadRange<BorrowedRootArgument>::at(std::size_t index) const;
template <> unsigned char InstructionPayloadRange<unsigned char>::at(std::size_t index) const;

// Operations describe language semantics, never target-register names or assembly text.
using hosted_abi::compiler_lowering::Binary;
using hosted_abi::compiler_lowering::Comparison;
using hosted_abi::compiler_lowering::Query;
using hosted_abi::compiler_lowering::Unary;
class Constant {
public:
    // U64 payloads preserve all 64 bits via std::bit_cast<std::int64_t>.
    // U8 payloads are canonical integers in 0..255, including in 64-bit value registers.
    std::int64_t value;
    Type type;
};
// An enum value names a declared case of one exact nominal enum.
class EnumConstant {
public:
    Type type;
    int caseIndex;
};
class Load {
public:
    int offset;
    Type type;
};
class Store {
public:
    int offset;
    Type type;
};
class Push {};
class Pop {};
class UnaryValue {
public:
    Unary operation;
    Type operandType;
    UnaryValue(Unary value, Type type) : operation(value), operandType(std::move(type)) {
    }
    // Keep the pre-u8 IR spelling while making operand width explicit for consumers.
    explicit UnaryValue(Unary value)
        : UnaryValue(value,
                     value == Unary::LogicalNot ? Type::Bool
                     : value == Unary::BitNot   ? Type::U64
                                                : Type::I64) {
    }
};
class BinaryValue {
public:
    Binary operation;
    // Both operands and result share this type except shifts, whose count is i64.
    Type operandType = Type::I64;
};
class Convert {
public:
    // Checked conversion between distinct i64, u64 and u8 values; never a
    // capability or bit reinterpretation. Widening a canonical u8 cannot fail.
    Type sourceType;
    Type resultType;
};
class Compare {
public:
    Comparison operation;
    Type operandType;
};
class BoundsGuard {
public:
    int offset;
    int length;
    Type elementType;
};
class IndexLoad {
public:
    int offset;
    int length;
    Type elementType;
};
class IndexStore {
public:
    int offset;
    int length;
    Type elementType;
};
class BorrowHandle {
public:
    int ownerOffset;
    Type referenceType;
};
// Value-call storage is explicit and cannot inhabit the scalar value stack.
// Scalar positions use zero; class positions name independent readonly snapshots.
template <class Offsets> class BasicAggregateCall {
public:
    std::string callee;
    Offsets objectArguments;
    int resultOffset;           // zero for scalar results, exact pristine object base otherwise
    Offsets spanArguments = {}; // zero except readonly capability positions
};
using AggregateCall = BasicAggregateCall<std::vector<int>>;
using AggregateCallObservation = BasicAggregateCall<OffsetRange>;
class Call {
public:
    std::string callee;
};
// Readonly byte spans have typed, non-scalar spills. Only an active fully
// initialized origin or an existing readonly capability can mint one.
// One seven-word record holds kind, immutable payload, logical start and length.
class BeginArray {
public:
    int offset;
};
class EndArray {
public:
    int offset;
};
class BorrowSpan {
public:
    int arrayOffset;
    int resultOffset;
};
// Direct private u8 array of the invocation receiver; no source address escapes.
class BorrowReceiverArraySpan {
public:
    int fieldIndex;
    int resultOffset;
};
// Immutable module data, with no source/IR-supplied address or terminator.
template <class Literals> class BasicBorrowLiteralSpan {
public:
    Literals bytes;
    int resultOffset;
};
using BorrowLiteralSpan = BasicBorrowLiteralSpan<std::vector<unsigned char>>;
using BorrowLiteralSpanObservation = BasicBorrowLiteralSpan<LiteralRange>;
class BorrowOwnedSpan {
public:
    int offset;
    int fieldIndex; // -1 standalone; otherwise exact direct owned field, root zero is receiver
    int resultOffset;
};
class ReturnSpan {
public:
    int offset;
};
class ReborrowSpan {
public:
    int sourceOffset;
    int resultOffset;
};
// Checked readonly child window. Consumes a saved i64 offset from the operand
// stack and the current i64 count; preserves the current scalar count. Runtime
// bounds are checked before loading/adjusting the parent payload address.
class Subspan {
public:
    int sourceOffset;
    int resultOffset;
};
class EndSpan {
public:
    int offset;
};
class SpanLength {
public:
    int offset;
};
class SpanLoad {
public:
    int offset;
};
// Typed readonly span element copy: current i64 index; the destination is a
// pristine exact-nominal copied object of the span's annotated element class.
class SpanValuesLoad {
public:
    int offset;
    int resultOffset;
};
class BindSpanParameter {
public:
    int index;
    int offset;
};
// Opaque byte resources never inhabit scalar slots or the operand stack. The
// region is borrowed authority; one owner holds a private four-word descriptor.
class BeginBytes {
public:
    int offset;
};
class AllocateBytes {
public:
    int regionOffset;
    int resultOffset; // consumes the current i64 length, creates an owning result
};
// Typed copied-value payload operations reuse byte-owner lifetimes and tokens.
// Element identity comes from the exact owner slot/field, never an operand.
class AllocateValues {
public:
    int regionOffset;
    int resultOffset;
    int fillOffset; // complete exact-nominal readonly copied snapshot; current i64 count
};
class ValuesLoad {
public:
    int offset;
    int fieldIndex;
    int resultOffset; // pristine exact-nominal copied object; current i64 index
};
class ValuesStore {
public:
    int offset;
    int fieldIndex;
    int valueOffset; // complete exact-nominal readonly copied snapshot; current i64 index
};
class ValuesResize {
public:
    int offset;
    int fieldIndex;
    int fillOffset; // complete exact-nominal readonly copied snapshot; current i64 count
};
class MoveBytes {
public:
    int sourceOffset;
    int resultOffset;
};
class BytesOk {
public:
    int offset;
    int fieldIndex = -1; // -1: standalone owner; otherwise direct field at object root
};
class BytesLength {
public:
    int offset;
    int fieldIndex = -1; // -1: standalone owner; otherwise direct field at object root
};
class BytesLoad {
public:
    int offset;          // current i64 index -> copied u8, checked fail-stop access
    int fieldIndex = -1; // -1: standalone owner; otherwise direct field at object root
};
class BytesStore {
public:
    int offset;          // saved i64 index and current u8 -> bool; false never writes
    int fieldIndex = -1; // -1: standalone owner; otherwise direct field at object root
};
class BytesResize {
public:
    int offset;          // current i64 length -> bool; preserves binding/token on either result
    int fieldIndex = -1; // -1: standalone owner; otherwise direct field at object root
};
class EndBytes {
public:
    int offset; // closes pristine, moved or live binding; preserves scalar state
};
// Service authority has no scalar representation. Entry binding is the sole
// provenance root; synchronous loans suspend it until the matching release.
class BindServiceParameter {
public:
    int index;
    int offset;
    service::Kind kind;
};
class AcquireServiceLoan {
public:
    int loanId;
    int offset;
    service::Kind kind = service::Kind::Console;
};
class ReleaseServiceLoan {
public:
    int loanId;
    service::Kind kind = service::Kind::Console;
};
class ServiceOperation {
public:
    int offset;
    service::Operation operation;
    int resultOffset; // exact pristine copied report for next/poll, zero for scalar operations
    service::Kind kind = service::Kind::Console;
};
class ServiceArgument {
public:
    int loanId;
    service::Kind kind;
};
template <class Offsets, class Services> class BasicServiceCall {
public:
    std::string callee;
    int loanId;
    int resultOffset;
    Offsets spanArguments; // full parameter positions, capability/scalar/object positions zero
    service::Kind kind = service::Kind::Console;
    // The first loan retains its original representation for single-service IR.
    Services additionalServices{};
    Offsets objectArguments{}; // readonly copied snapshots; zero at every other position
    int regionOffset = 0;      // authenticated region root for the closed Console+Region prefix
};
using ServiceCall = BasicServiceCall<std::vector<int>, std::vector<ServiceArgument>>;
using ServiceCallObservation = BasicServiceCall<OffsetRange, ServiceArgumentRange>;
class BindRegionParameter {
public:
    int index;
    int offset;
};
class BindBytesParameter {
public:
    int index;
    int offset;
};
template <class Offsets> class BasicResourceCall {
public:
    std::string callee;
    int regionOffset;
    Offsets ownerArguments; // owners or readonly constructor class snapshots; zero otherwise
    int resultOffset;       // pristine bytes/object root for owning or copied result; scalar result is zero
    int receiverOffset = 0; // positive only for an owning constructor
};
using ResourceCall = BasicResourceCall<std::vector<int>>;
using ResourceCallObservation = BasicResourceCall<OffsetRange>;
class InitializeBytesField {
public:
    int objectOffset; // zero only: bound constructor receiver
    int fieldIndex;
    int sourceOffset; // consumed standalone owner
};
class MoveObject {
public:
    int sourceOffset;
    int resultOffset;
};
class BindOwnedObjectParameter {
public:
    int index;
    int offset;
    std::string className;
};
class ReturnOwnedObject {
public:
    int offset;
};
class ReturnBytes {
public:
    int offset;
};
// Receiver capabilities are deliberately not scalar Values. Only these operations
// can address the hidden receiver, and a call consumes a synchronous reborrow.
class BeginObject {
public:
    int offset;
};
// Explicit designated initialization of a zero-field copied class. A lifetime
// reservation alone never establishes complete value initialization.
class InitializeEmptyObject {
public:
    int offset;
};
class EndObject {
public:
    int offset;
};
// Whole values and logical class fields copy by nominal identity. Scalar leaf
// stores cannot mint the evidence that an embedded class value is complete.
class CopyObject {
public:
    int sourceOffset;
    int resultOffset;
};
class ObjectFieldCopy {
public:
    int sourceOffset; // zero projects the bound, fully initialized receiver
    int fieldIndex;
    int resultOffset;
};
// Replaces an already complete direct owned class field. The source is a
// distinct complete local value; no subobject capability escapes this operation.
class AssignObjectField {
public:
    int objectOffset; // zero addresses the bound nonconstructor receiver
    int fieldIndex;
    int sourceOffset;
};
class InitializeObjectField {
public:
    int objectOffset; // currently zero only: bound constructor receiver
    int fieldIndex;
    int sourceOffset;
};
// A class array remains one complete inline value. Indexed operations consume
// a checked i64, never manufacture an element address or escaping reference.
template <class Offsets> class BasicInitializeClassArray {
public:
    int objectOffset; // zero: constructor receiver; positive: declared local carrier
    int fieldIndex;
    Offsets sources;
};
using InitializeClassArray = BasicInitializeClassArray<std::vector<int>>;
using InitializeClassArrayObservation = BasicInitializeClassArray<OffsetRange>;
class ClassArrayBoundsGuard {
public:
    int objectOffset;
    int fieldIndex;
};
class ClassArrayCopy {
public:
    int objectOffset;
    int fieldIndex;
    int resultOffset;
};
class ClassArrayAssign {
public:
    int objectOffset;
    int fieldIndex;
    int sourceOffset;
};
class ReceiverLoad {
public:
    int fieldIndex;
    Type type;
};
class ReceiverStore {
public:
    int fieldIndex;
    Type type;
};
// These operations refer only to the bound receiver and logical field metadata.
// A bounds guard leaves the signed index in the value register with verifier-only
// nominal field evidence; indexed stores consume its saved stack value.
class ReceiverArrayZero {
public:
    int fieldIndex;
};
class ReceiverBoundsGuard {
public:
    int fieldIndex;
};
class ReceiverIndexLoad {
public:
    int fieldIndex;
};
class ReceiverIndexStore {
public:
    int fieldIndex;
};
template <class Offsets> class BasicMethodCall {
public:
    std::string callee;
    int receiverOffset;           // 0: receiver/root 0; -1..-5: borrowed roots; positive: ObjectSlot
    Offsets objectArguments = {}; // readonly copied snapshots; scalar entries are zero
    int resultOffset = 0;         // pristine class result destination; zero for scalar results
    int receiverFieldIndex = -1;  // -1 selects the root; otherwise one logical owned class field
    Offsets spanArguments = {};   // zero except readonly capability positions
};
using MethodCall = BasicMethodCall<std::vector<int>>;
using MethodCallObservation = BasicMethodCall<OffsetRange>;
// Invocation-only owning-root authority. Loan IDs are verifier identities, never
// stack offsets or source-visible addresses. Acquisition precedes later arguments.
class AcquireObjectLoan {
public:
    int loanId;
    int root; // 0..-5 select bound borrowed formals; positive selects an exact ObjectSlot/ByteSlot
    bool mutableValue;
    int fieldIndex = -1; // -1 selects the root; otherwise one direct owner field
};
class ReleaseObjectLoan {
public:
    int loanId;
};
class BorrowedRootArgument {
public:
    int root;
    int loanId;
    int fieldIndex = -1;
};
// Ordered invocation-only root/loan/field triples borrow the same immutable operand
// owner as other payloads. No parallel first/second authority is retained.
template <class Offsets, class Roots> class BasicBorrowedCall {
public:
    std::string callee;
    Roots roots;
    Offsets objectArguments = {};
    int resultOffset = 0;
    Offsets spanArguments = {};
    static constexpr int receiverFieldIndex = -1;
};
using BorrowedCall = BasicBorrowedCall<std::vector<int>, std::vector<BorrowedRootArgument>>;
using BorrowedCallObservation = BasicBorrowedCall<OffsetRange, BorrowedRootArgumentRange>;
class MetadataQuery {
public:
    Query query;
    int moduleScope = 0;
};
class Label {
public:
    int id;
};
class Jump {
public:
    int target;
};
class BranchFalse {
public:
    int target;
};
class Return {};
class ReturnObject {
public:
    int offset;
};
class BindObjectParameter {
public:
    int index;
    int offset;
    std::string className;
};
// Scalar source-call registers use canonical 64-bit values; u8 storage is one
// byte and typed loads zero-extend it. Aggregate records use canonical byte layout.
// Incoming u8 values and u8 object leaves must be canonical 0..255, just as bool
// and enum arguments must already be canonical. All verified Aurora callers
// establish this contract; these entry points are not a foreign-language ABI.
// Verified returns preserve canonicality without truncating or reinterpreting it.
class BindParameter {
public:
    int index;
    int offset;
    Type type;
};
// One operation inventory: hostile fixtures own their variable payloads,
// while production observations borrow only immutable owner ranges. All other
// operation records, including copied Type and name observations, are shared.
template <class Offsets, class Services, class Literals, class Roots>
using BasicInstruction = std::variant<BindServiceParameter,
                                      AcquireServiceLoan,
                                      ReleaseServiceLoan,
                                      ServiceOperation,
                                      BasicServiceCall<Offsets, Services>,
                                      Constant,
                                      EnumConstant,
                                      Load,
                                      Store,
                                      Push,
                                      Pop,
                                      UnaryValue,
                                      BinaryValue,
                                      Convert,
                                      Compare,
                                      BoundsGuard,
                                      IndexLoad,
                                      IndexStore,
                                      BorrowHandle,
                                      Call,
                                      BasicAggregateCall<Offsets>,
                                      BeginObject,
                                      InitializeEmptyObject,
                                      EndObject,
                                      CopyObject,
                                      ObjectFieldCopy,
                                      AssignObjectField,
                                      InitializeObjectField,
                                      BasicInitializeClassArray<Offsets>,
                                      ClassArrayBoundsGuard,
                                      ClassArrayCopy,
                                      ClassArrayAssign,
                                      ReceiverLoad,
                                      ReceiverStore,
                                      ReceiverArrayZero,
                                      ReceiverBoundsGuard,
                                      ReceiverIndexLoad,
                                      ReceiverIndexStore,
                                      BasicMethodCall<Offsets>,
                                      MetadataQuery,
                                      Label,
                                      Jump,
                                      BranchFalse,
                                      Return,
                                      ReturnObject,
                                      BindParameter,
                                      BindObjectParameter,
                                      BeginArray,
                                      EndArray,
                                      BorrowSpan,
                                      BorrowReceiverArraySpan,
                                      BasicBorrowLiteralSpan<Literals>,
                                      BorrowOwnedSpan,
                                      ReturnSpan,
                                      ReborrowSpan,
                                      Subspan,
                                      EndSpan,
                                      SpanLength,
                                      SpanLoad,
                                      BindSpanParameter,
                                      BeginBytes,
                                      AllocateBytes,
                                      AllocateValues,
                                      ValuesLoad,
                                      ValuesStore,
                                      ValuesResize,
                                      MoveBytes,
                                      BytesOk,
                                      BytesLength,
                                      BytesLoad,
                                      BytesStore,
                                      BytesResize,
                                      EndBytes,
                                      BindRegionParameter,
                                      BindBytesParameter,
                                      BasicResourceCall<Offsets>,
                                      ReturnBytes,
                                      InitializeBytesField,
                                      MoveObject,
                                      BindOwnedObjectParameter,
                                      ReturnOwnedObject,
                                      AcquireObjectLoan,
                                      ReleaseObjectLoan,
                                      BasicBorrowedCall<Offsets, Roots>,
                                      SpanValuesLoad>;
using Instruction = BasicInstruction<std::vector<int>,
                                     std::vector<ServiceArgument>,
                                     std::vector<unsigned char>,
                                     std::vector<BorrowedRootArgument>>;
using InstructionObservation =
    BasicInstruction<OffsetRange, ServiceArgumentRange, LiteralRange, BorrowedRootArgumentRange>;
class ObjectSlot {
public:
    std::string className;
    bool mutableValue;
};
class Receiver {
public:
    std::string className;
    bool mutableValue;
    bool constructor;
    bool publicAccess = true;
};
using InstructionId = std::size_t;
using CodePosition = std::size_t;
// A copied observation of source-owned, normalized control flow. Positions
// name the retained function-local order; instruction IDs never change.
class InstructionFlow {
public:
    std::optional<CodePosition> target;
    bool fallsThrough;
    bool blockEntry;
    bool unreachableSemanticAfter;
    bool operator==(const InstructionFlow &) const = default;
};
class InstructionRange {
    const Instructions *instructions_ = nullptr;
    Metadata::CallableId callableId_ = 0;
    InstructionRange(const Instructions &instructions, Metadata::CallableId callableId)
        : instructions_(&instructions), callableId_(callableId) {
    }
    friend class Instructions;

public:
    using value_type = InstructionObservation;
    InstructionRange() = default;
    std::size_t size() const;
    bool empty() const {
        return size() == 0;
    }
    InstructionId idAt(CodePosition position) const;
    InstructionFlow flowAt(CodePosition position) const;
    InstructionObservation instructionById(InstructionId id) const;
    InstructionObservation at(CodePosition position) const;
    InstructionObservation operator[](CodePosition position) const {
        return at(position);
    }
    InstructionObservation front() const {
        return at(0);
    }
    InstructionObservation back() const {
        return at(size() - 1);
    }
    auto begin() const {
        return MetadataIterator<InstructionRange>(*this, 0);
    }
    auto end() const {
        return MetadataIterator<InstructionRange>(*this, size());
    }
    bool operator==(const InstructionRange &) const = default;
};
// Production bodies borrow durable source rows. No native executable payload
// container survives ingress; code positions are separate from immutable IDs.
class FunctionBody {
public:
    Metadata::CallableId callableId = 0;
    InstructionRange code;
};
// Hostile fixture construction deliberately keeps the owning raw spelling.
// It is consumed into the same pending bundle as production lowering.
class Function {
public:
    std::vector<Instruction> code;
    std::map<int, Type> slots;
    // Scalar leaves live at base minus their canonical byte offset and have
    // matching typed slots. Resource descriptors are non-scalar subranges.
    // Empty copyable classes reserve a word but expose no payload.
    std::map<int, ObjectSlot> objectSlots;
    // Local u8 arrays declare exact byte extents, with one matching scalar slot
    // per element. Capability spills reserve spanBytes disjoint bytes and no scalar slot.
    std::map<int, int> arraySlots;
    std::set<int> spanSlots;
    std::set<int> serviceSlots;    // sealed sixteen-byte grant/generation spills
    std::set<int> regionSlots;     // private eight-byte authority spills
    std::map<int, bool> byteSlots; // private 32-byte owner spills, mutable binding
    // Exact subset of byteSlots: missing means OwnedBytes, present means
    // OwnedValues of the named canonical copied class. Never grants a lifetime.
    std::map<int, std::string> ownedValueTypes;
    // Exact subset of spanSlots: missing means a byte span, present means a
    // readonly span of the named canonical copied class.
    std::map<int, std::string> spanValueTypes;
    int frameBytes = 0;
    std::string name;
    int moduleScope = 0;
    Type result;
    std::vector<Type> parameters;
    std::optional<Receiver> receiver;
    // Canonical explicit formals include the leading owning roots. Receiver is
    // reserved for genuine methods/constructors; raw integers stay hostile.
    std::int64_t borrowedRootCount = 0;
    // Bit i grants mutable authority only to admitted root i; reject out-of-range bits.
    std::int64_t borrowedRootMutability = 0;
    std::optional<int> receiverSpanField;
};
class Descriptor {
public:
    std::int64_t size;
    std::int64_t publicFields;
};
// Logical source fields are distinct from the scalar leaves used for inline
// storage and value-call copies. Arrays expose one field and a contiguous range.
// A non-array class field names its nominal child in elementType and its complete
// flattened scalar range in firstLeaf/length (including zero for empty children).
// A direct OwnedBytes field has length zero and reserves a separate descriptor.
class ClassField {
public:
    Type elementType;
    int firstLeaf;
    int length;
    bool array;
    // Only class-valued arrays use this count. length always remains the complete
    // flattened leaf range, including zero for arrays of empty copied classes.
    int elementCount = 1;
};
// Move-only identity comes from independently verified logical shape.
inline bool owningClass(const Metadata &metadata, const std::string &name) {
    const auto id = metadata.findClass(name);
    return id && metadata.isOwning(*id);
}
class ClassStorage {
public:
    std::vector<int> leafOffsets;
    std::vector<int> fieldOffsets;
    int sizeBytes = 0;
    int alignment = 1;
    int reservedBytes = 0;
    bool operator==(const ClassStorage &) const = default;
};
// Raw metadata remains a hostile construction route. Production lowering owns
// one pending metadata/instruction bundle and never fills these maps.
class Module {
public:
    std::vector<Function> functions;
    std::map<std::string, std::vector<Type>> classLayouts;
    // Missing entries are normalized to legacy one-leaf scalar fields.
    std::map<std::string, std::vector<ClassField>> classFields;
    // Optional input metadata is checked against logical shape. Validation always
    // publishes the complete canonical layout for backend consumption.
    std::map<std::string, ClassStorage> classStorage;
    // Compiler-internal local array storage, validated as exactly one class-array
    // field. Carriers are not source classes, receiver types or boundary values.
    std::set<std::string> classArrayCarriers;
    std::map<int, Descriptor> descriptors;
    std::map<int, std::set<int>> descriptorViews{{0, {}}};
    std::map<std::string, int> enumCases;
};
namespace verification {
class Metrics;
}
class ValidatedModule;
ValidatedModule validate(Module module, verification::Metrics *metrics = nullptr);
ValidatedModule validate(InstructionIngress pending, verification::Metrics *metrics = nullptr);
class ValidatedModule {
    class Contents {
    public:
        std::vector<FunctionBody> functions;
    };
    // Reverse destruction drops borrowed bodies, then instructions, then metadata.
    std::unique_ptr<Metadata> metadataOwner;
    std::unique_ptr<Instructions> instructionOwner;
    Contents contents;
    friend class ::aurora::X86Emitter;
    explicit ValidatedModule(std::vector<FunctionBody> functions,
                             std::unique_ptr<Metadata> metadata,
                             std::unique_ptr<Instructions> instructions);
    friend ValidatedModule validate(InstructionIngress pending, verification::Metrics *metrics);

public:
    ~ValidatedModule();
    ValidatedModule(const ValidatedModule &) = delete;
    ValidatedModule &operator=(const ValidatedModule &) = delete;
    ValidatedModule(ValidatedModule &&) noexcept;
    ValidatedModule &operator=(ValidatedModule &&) noexcept;
    const Contents &get() const {
        return contents;
    }
    const Metadata &metadata() const {
        if (!metadataOwner)
            throw Error("metadata access on moved-from validated module");
        return *metadataOwner;
    }
};
} // namespace aurora::ir
