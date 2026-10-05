#pragma once
#include "types.hpp"
#include <map>
#include <optional>
#include <set>
#include <variant>
#include <vector>

namespace aurora::ir {
// Operations describe language semantics, never target-register names or assembly text.
enum class Unary { CheckedNegate, LogicalNot, BitNot };
enum class Binary {
    CheckedAdd,
    CheckedSubtract,
    CheckedMultiply,
    CheckedDivide,
    CheckedRemainder,
    BitAnd,
    BitOr,
    BitXor,
    ShiftLeft,
    ShiftRight
};
enum class Comparison { Equal, NotEqual, Less, Greater, LessEqual, GreaterEqual };
enum class Query { Size, PublicFieldCount };
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
    UnaryValue(Unary value, Type type) : operation(value), operandType(std::move(type)) {}
    // Keep the pre-u8 IR spelling while making operand width explicit for consumers.
    explicit UnaryValue(Unary value)
        : UnaryValue(value, value == Unary::LogicalNot ? Type::Bool
                            : value == Unary::BitNot   ? Type::U64
                                                       : Type::I64) {}
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
class AggregateCall {
  public:
    std::string callee;
    std::vector<int> objectArguments;
    int resultOffset; // zero for scalar results, exact pristine object base otherwise
    std::vector<int> spanArguments = {}; // zero except readonly capability positions
};
class Call {
  public:
    std::string callee;
};
// Readonly byte spans have typed, non-scalar spills. Only an active fully
// initialized local byte array or an existing readonly capability can mint one.
// The base addresses pointer storage; the next word holds the bounded length.
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
class BindSpanParameter {
  public:
    int index;
    int offset;
};
// Receiver capabilities are deliberately not scalar Values. Only these operations
// can address the hidden receiver, and a call consumes a synchronous reborrow.
class BeginObject {
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
class InitializeObjectField {
  public:
    int objectOffset; // currently zero only: bound constructor receiver
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
class MethodCall {
  public:
    std::string callee;
    int receiverOffset;                    // zero forwards this; positive names an ObjectSlot base
    std::vector<int> objectArguments = {}; // readonly copied snapshots; scalar entries are zero
    int resultOffset = 0; // pristine class result destination; zero for scalar results
};
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
using Instruction =
    std::variant<Constant, EnumConstant, Load, Store, Push, Pop, UnaryValue, BinaryValue, Convert,
                 Compare, BoundsGuard, IndexLoad, IndexStore, BorrowHandle, Call, AggregateCall,
                 BeginObject, EndObject, CopyObject, ObjectFieldCopy, InitializeObjectField,
                 ReceiverLoad, ReceiverStore, ReceiverArrayZero, ReceiverBoundsGuard,
                 ReceiverIndexLoad, ReceiverIndexStore, MethodCall, MetadataQuery, Label, Jump,
                 BranchFalse, Return, ReturnObject, BindParameter, BindObjectParameter, BeginArray,
                 EndArray, BorrowSpan, ReborrowSpan, Subspan, EndSpan, SpanLength, SpanLoad,
                 BindSpanParameter>;
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
};
class Function {
  public:
    std::string name;
    int moduleScope = 0;
    Type result;
    std::vector<Type> parameters;
    std::map<int, Type> slots;
    // Scalar leaves live at base minus their canonical byte offset and have
    // matching typed slots. Empty classes reserve a word but expose no payload.
    std::map<int, ObjectSlot> objectSlots;
    // Local u8 arrays declare exact byte extents, with one matching scalar slot
    // per element. Capability spills reserve 16 disjoint bytes and no scalar slot.
    std::map<int, int> arraySlots;
    std::set<int> spanSlots;
    std::optional<Receiver> receiver;
    int frameBytes = 0;
    std::vector<Instruction> code;
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
class ClassField {
  public:
    Type elementType;
    int firstLeaf;
    int length;
    bool array;
};
class ClassStorage {
  public:
    std::vector<int> leafOffsets;
    std::vector<int> fieldOffsets;
    int sizeBytes = 0;
    int alignment = 1;
    int reservedBytes = 0;
    bool operator==(const ClassStorage &) const = default;
};
class Module {
  public:
    std::vector<Function> functions;
    std::map<std::string, std::vector<Type>> classLayouts;
    // Missing entries are normalized to legacy one-leaf scalar fields.
    std::map<std::string, std::vector<ClassField>> classFields;
    // Optional input metadata is checked against logical shape. Validation always
    // publishes the complete canonical layout for backend consumption.
    std::map<std::string, ClassStorage> classStorage;
    std::map<int, Descriptor> descriptors;
    std::map<int, std::set<int>> descriptorViews{{0, {}}};
    std::map<std::string, int> enumCases;
};
class ValidatedModule;
ValidatedModule validate(Module module);
class ValidatedModule {
    Module module;
    explicit ValidatedModule(Module value) : module(std::move(value)) {}
    friend ValidatedModule validate(Module module);

  public:
    const Module &get() const { return module; }
};
} // namespace aurora::ir
