#pragma once
#include "syntax.hpp"
#include "hosted_parser_abi.hpp"

namespace aurora::hosted_parser {
// Simultaneously live body, expression, type and namespace continuation frames.
inline constexpr std::uint64_t maximumLiveFrames = 256 + 1549 + 70 + 64;

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
// Copied admission input: host layout limits and the catalog's service set.
hosted_abi::compiler_parser::AdmissionConfig admissionConfiguration();
// The diagnostic of a rejected grammar status at its cursor token. `previous`
// spells the token before it, which a duplicate enum case names.
[[noreturn]] void rejectSyntax(Status status, Stop stop, const Token &at, const std::string &previous);
// The diagnostic of a rejected declaration over `span`, citing `at`;
// `fieldType` spells an unsupported field's type.
[[noreturn]] void rejectDeclaration(
    AdmissionStatus status, std::int64_t detail, const Token &at, const SourceSpan &span, const std::string &fieldType);
} // namespace aurora::hosted_parser

namespace aurora {
// The source lifetime and captured context offsets are bounded before the private ABI.
// Position commits only after bounded, uniquely owned AST/type conversion.
// Aurora owns module syntax and unresolved declaration admission; the adapter
// checks representation safety and renders the selected diagnostics.
Program parseHostedProgram(const std::vector<Token> &tokens);
// Parses and admits a module into the caller's already constructed arena, whose
// untouched forest the formatter then reads; rejections throw diagnostics.
void parseHostedModuleSyntax(const std::vector<Token> &tokens, void *arena);

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
