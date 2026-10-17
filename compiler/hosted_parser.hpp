#pragma once
#include "syntax.hpp"
#include "hosted_parser_abi.hpp"

namespace aurora::hosted_parser {
// Original declaration tokens only, never resolved identities or visibility.
class Cursor {
public:
    std::size_t ordinal = 0;
    // One means the first byte of this original >> token is already consumed.
    unsigned half = 0;
};
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
// Aurora owns module syntax and unresolved declaration admission; the adapter
// checks representation safety and renders the selected diagnostics.
Program parseHostedProgram(const std::vector<Token> &tokens);
// Private graph-loader handoff. The caller owns an already constructed arena;
// success returns only source-backed header metadata and its untouched forest.
class ParsedModuleSyntax {
public:
    std::int64_t root = -1;
    std::string moduleName;
    bool interfaceUnit = false;
    bool callFamily = false;
    std::vector<Token> imports;
    std::vector<std::int64_t> importSyntax;
};
ParsedModuleSyntax parseHostedModuleSyntax(const std::vector<Token> &tokens, void *arena);

// Unsupported is an invalid result; no entry has a host grammar fallback.
ExpressionPtr parseHostedExpression(const std::vector<Token> &tokens,
                                    std::size_t &position,
                                    hosted_parser::Stop stop,
                                    const hosted_parser::Context &context = {});
std::vector<StatementPtr>
parseHostedBody(const std::vector<Token> &tokens, std::size_t &position, const hosted_parser::Context &context = {});
// Standalone type reads return a cursor value; source tokens are never rewritten.
class ParsedType {
public:
    Type type;
    hosted_parser::Cursor next;
};
ParsedType parseHostedType(const std::vector<Token> &tokens,
                           hosted_parser::Cursor cursor,
                           const hosted_parser::Context &context = {});
// Fragment utilities import syntax only. Production module parsing also runs
// Aurora declaration admission before publishing the complete program.
class ParsedCallable {
public:
    Function function;
    hosted_parser::Cursor next;
    explicit ParsedCallable(Token token) : function(std::move(token)) {
    }
};
ParsedCallable parseHostedCallable(const std::vector<Token> &tokens,
                                   hosted_parser::Cursor cursor,
                                   hosted_parser::Stop stop,
                                   const hosted_parser::Context &context = {});
class ParsedField {
public:
    Field field;
    hosted_parser::Cursor next;
    ParsedField(Token token, Type type) : field(std::move(token), std::move(type)) {
    }
};
ParsedField parseHostedField(const std::vector<Token> &tokens,
                             hosted_parser::Cursor cursor,
                             const hosted_parser::Context &context = {});
class ParsedPreamble {
public:
    Program program;
    hosted_parser::Cursor next;
};
ParsedPreamble parseHostedPreamble(const std::vector<Token> &tokens, hosted_parser::Cursor cursor);
class ParsedEnum {
public:
    EnumDefinition definition;
    hosted_parser::Cursor next;
};
ParsedEnum parseHostedEnum(const std::vector<Token> &tokens, hosted_parser::Cursor cursor, std::size_t enumCount);
} // namespace aurora
