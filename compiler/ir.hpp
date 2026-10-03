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
};
class BinaryValue {
  public:
    Binary operation;
    // Both operands and result share this type except shifts, whose count is i64.
    Type operandType = Type::I64;
};
class Convert {
  public:
    // Checked i64 <-> u64 value conversion; never a capability or bit reinterpretation.
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
};
class Call {
  public:
    std::string callee;
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
    std::vector<int> objectArguments = {}; // constructor snapshots; scalar entries are zero
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
                 BranchFalse, Return, ReturnObject, BindParameter, BindObjectParameter>;
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
    // Scalar leaf i lives at base - i*8 and has a matching scalar slot. Empty classes
    // reserve one word but expose no scalar payload.
    std::map<int, ObjectSlot> objectSlots;
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
class Module {
  public:
    std::vector<Function> functions;
    std::map<std::string, std::vector<Type>> classLayouts;
    // Missing entries are normalized to legacy one-leaf scalar fields.
    std::map<std::string, std::vector<ClassField>> classFields;
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
