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
// Aurora owns all module syntax; the adapter checks representation safety.
Program parseHostedProgram(const std::vector<Token> &tokens);
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
// Complete syntax plus the original semantic-admission cursors. Importing and
// admission leave caller state untouched; Parser commits next only after both.
class ParsedCallable {
public:
    Function function;
    std::vector<Token> borrowAdmissions, nameAdmissions;
    Token nameAdmission{"", 0}, resultAdmission{"", 0};
    hosted_parser::Cursor next;
    explicit ParsedCallable(Token token) : function(std::move(token)) {
    }
};
ParsedCallable parseHostedCallable(const std::vector<Token> &tokens,
                                   hosted_parser::Cursor cursor,
                                   hosted_parser::Stop stop,
                                   const hosted_parser::Context &context = {});
void admitHostedCallable(const ParsedCallable &parsed,
                         hosted_parser::Stop stop,
                         const hosted_parser::Context &context = {},
                         const std::string &className = {});
class ParsedField {
public:
    Field field;
    Token admission{"", 0};
    SourceSpan typeSpan;
    hosted_parser::Cursor next;
    ParsedField(Token token, Type type) : field(std::move(token), std::move(type)) {
    }
};
ParsedField parseHostedField(const std::vector<Token> &tokens,
                             hosted_parser::Cursor cursor,
                             const hosted_parser::Context &context = {});
void admitHostedField(const ParsedField &parsed, bool publicAccess, bool templated);
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
