#pragma once
#include <cstdint>

namespace aurora::hosted_parser {
// Private bootstrap wire orders, exercised against real generated code.
enum class NodeKind : std::int64_t {
    Invalid,
    Literal,
    Name,
    Unary,
    Binary
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
    Invalid
};
enum class Stop : std::int64_t {
    Semicolon,
    CloseParenthesis,
    Assignment
};
} // namespace aurora::hosted_parser
