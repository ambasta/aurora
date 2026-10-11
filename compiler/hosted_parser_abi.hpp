#pragma once
#include <cstdint>

namespace aurora::hosted_parser {
// Private bootstrap wire orders, exercised against real generated code.
enum class NodeKind : std::int64_t {
    Invalid,
    Literal,
    Name,
    Unary,
    Binary,
    Call,
    Member,
    MethodCall,
    Index,
    ArrayLiteral,
    Construct,
    ArrayZero
};
enum class TypeKind : std::int64_t {
    Invalid,
    I64,
    U64,
    U8,
    Bool,
    Named,
    Parameter,
    Capacity,
    LengthParameter,
    Array,
    Own,
    Ref,
    MutRef,
    ByteSpan,
    Builtin,
    OwnedValues,
    BuiltinClass
};
enum class Status : std::int64_t {
    Success,
    Unsupported,
    ExpectedExpression,
    ExpectedClose,
    ExpectedEnd,
    NestingLimit,
    DepthLimit,
    AllocationFailure,
    ExpectedIndexClose,
    ExpectedIdentifier,
    ReservedIdentifier,
    ReservedBuiltin,
    ReservedPrefix,
    ExpectedBraceClose,
    ExpectedDot,
    ExpectedEqual,
    ExpectedBraceOpen,
    ExpectedAngleOpen,
    ExpectedAngleClose,
    ExpectedScope,
    ExpectedComma,
    ExpectedConst,
    ExpectedU8,
    ExpectedI64,
    ExpectedArray,
    ReservedType,
    ExpectedType,
    TypeNestingLimit,
    TemplateNestingLimit,
    CallTemplateNestingLimit,
    TemplateContext,
    TemplateArity,
    TemplateArgument,
    CapacityArgument,
    NestedDependent,
    OwnedElement,
    ArrayElement,
    ArrayLength,
    ClassArrayLength,
    Invalid
};
enum class Stop : std::int64_t {
    Semicolon,
    CloseParenthesis,
    Assignment,
    ConstructorBraces
};
} // namespace aurora::hosted_parser
