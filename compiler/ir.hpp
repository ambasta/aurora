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
class MetadataQuery {
  public:
    Query query;
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
                                 MetadataQuery, Label, Jump, BranchFalse, Return, BindParameter>;
class Function {
  public:
    std::string name;
    Type result;
    std::vector<Type> parameters;
    std::map<int, Type> slots;
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
    std::map<int, Descriptor> descriptors;
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
