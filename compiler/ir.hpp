#pragma once
#include "types.hpp"
#include <map>
#include <optional>
#include <set>
#include <variant>
#include <vector>

namespace aurora::ir {
// Operations describe language semantics, never target-register names or assembly text.
enum class Unary { CheckedNegate, LogicalNot };
enum class Binary { CheckedAdd, CheckedSubtract, CheckedMultiply };
enum class Comparison { Equal, NotEqual, Less, Greater, LessEqual, GreaterEqual };
enum class Query { Size, PublicFieldCount };
class Constant {
  public:
    std::int64_t value;
    Type type;
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
class MethodCall {
  public:
    std::string callee;
    int receiverOffset; // zero forwards this; positive names an ObjectSlot base
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
class BindParameter {
  public:
    int index;
    int offset;
    Type type;
};
using Instruction = std::variant<Constant, Load, Store, Push, Pop, UnaryValue, BinaryValue, Compare,
                                 BoundsGuard, IndexLoad, IndexStore, BorrowHandle, Call,
                                 BeginObject, EndObject, ReceiverLoad, ReceiverStore, MethodCall, MetadataQuery, Label, Jump,
                                 BranchFalse, Return, BindParameter>;
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
    // Field i lives at base - i*8 and has a matching scalar slot. Empty classes
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
class Module {
  public:
    std::vector<Function> functions;
    std::map<std::string, std::vector<Type>> classLayouts;
    std::map<int, Descriptor> descriptors;
    std::map<int, std::set<int>> descriptorViews{{0, {}}};
};
class ValidatedModule;
ValidatedModule validate(Module module);
class ValidatedModule {
    Module module;
    explicit ValidatedModule(Module value) : module(std::move(value)) {}
    friend ValidatedModule validate(Module module);

  public:
    const Module &get() const {
        return module;
    }
};
} // namespace aurora::ir
