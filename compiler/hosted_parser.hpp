#pragma once
#include "syntax.hpp"
#include "hosted_parser_abi.hpp"

namespace aurora {
// Parser first screens template/call ambiguity with its non-consuming lookahead.
// This lower adapter receives an expression candidate, not a general dispatcher.
// ConstructorBraces starts at the original field identifier and includes both
// braces; its checked cursor ends immediately after the closing brace.
// Only Unsupported yields an empty pointer. The caller commits position after
// complete checked conversion; all rejected results leave its state untouched.
ExpressionPtr parseHostedExpression(const std::vector<Token> &tokens, std::size_t &position, hosted_parser::Stop stop);
} // namespace aurora
