#pragma once
#include "syntax.hpp"
#include "hosted_parser_abi.hpp"

namespace aurora::hosted_parser {
// Original declaration tokens only, never resolved identities or visibility.
class Context {
public:
    std::vector<Token> typeParameters;
    std::vector<Token> capacityParameters;
    bool functionTemplate = false;
};
} // namespace aurora::hosted_parser

namespace aurora {
// The source lifetime and captured context offsets are bounded before the private ABI.
// Position commits only after bounded, uniquely owned AST/type conversion.
// Aurora owns expression grammar; the adapter checks representation safety.
// Unsupported is an invalid result; expressions always use the Aurora frontend.
ExpressionPtr parseHostedExpression(const std::vector<Token> &tokens,
                                    std::size_t &position,
                                    hosted_parser::Stop stop,
                                    const hosted_parser::Context &context = {});
} // namespace aurora
