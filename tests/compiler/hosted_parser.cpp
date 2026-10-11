// Exercise the real Aurora phase against explicit AST and diagnostic contracts.
// Whole-program/direct-source comparisons check dispatch consistency only.
// Raw copied ABI records remain deliberately independent of the host adapter.
#include "lexer.hpp"
#include "parser.hpp"
#include "hosted_parser.hpp"
#include "../../runtime/hosted_bytes.hpp"
#include <algorithm>
#include <array>
#include <cerrno>
#include <csignal>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>

#if !defined(AURORA_HOSTED_PARSER) || !defined(AURORA_HOSTED_LEXER)
#error The hosted parser fixture must link the real Aurora frontend
#endif
extern "C" {
void checked_hosted_parser_create(const void *, void *);
void checked_hosted_parser_parse(void *, const void *, void *);
std::int64_t checked_hosted_parser_count(const void *);
void checked_hosted_parser_read(const void *, std::int64_t, void *);
std::int64_t checked_hosted_parser_edges(const void *);
void checked_hosted_parser_edge(const void *, std::int64_t, void *);
std::int64_t checked_hosted_parser_types(const void *);
void checked_hosted_parser_type(const void *, std::int64_t, void *);
std::int64_t checked_hosted_parser_statements(const void *);
void checked_hosted_parser_statement(const void *, std::int64_t, void *);
void checked_hosted_parser_release(void *);
}

using AbiEntry = void (*)(const void *, const void *, void *);
extern "C" {
void checked_hosted_parser_call(const void *, const void *, void *, AbiEntry);
void hosted_parser_clobber_rbp(const void *, const void *, void *);
void hosted_parser_clobber_rbx(const void *, const void *, void *);
void hosted_parser_clobber_r12(const void *, const void *, void *);
void hosted_parser_clobber_r13(const void *, const void *, void *);
void hosted_parser_clobber_r14(const void *, const void *, void *);
void hosted_parser_clobber_r15(const void *, const void *, void *);
void hosted_parser_clobber_canary(const void *, const void *, void *);
void hosted_parser_shift_stack(const void *, const void *, void *);
void hosted_parser_misaligned_call(const void *, const void *, void *, AbiEntry);
}

namespace {
using aurora::hosted_parser::Context;
using aurora::hosted_parser::NodeKind;
using aurora::hosted_parser::Status;
using aurora::hosted_parser::Stop;
using Words = std::array<std::int64_t, 5>;
using NodeWords = std::array<std::int64_t, 7>;
using EdgeWords = std::array<std::int64_t, 5>;
using TypeWords = std::array<std::int64_t, 8>;
using StatementWords = std::array<std::int64_t, 11>;
using aurora::hosted_parser::StatementKind;
using ContextWords = std::array<std::int64_t, 7>;
constexpr std::int64_t wire(NodeKind value) {
    return static_cast<std::int64_t>(value);
}
constexpr std::int64_t wire(StatementKind value) {
    return static_cast<std::int64_t>(value);
}
constexpr std::int64_t wire(Status value) {
    return static_cast<std::int64_t>(value);
}
constexpr std::uint64_t canary = 0xa3159f274c86be02ULL;
std::size_t cases = 0;
std::string context;
void require(bool value, const std::string &message) {
    if (!value)
        throw std::runtime_error(context + ": " + message);
}
void samePosition(const aurora::SourcePosition &a, const aurora::SourcePosition &b) {
    require(a.offset == b.offset && a.line == b.line && a.column == b.column, "source position differs");
}
void sameSpan(const aurora::SourceSpan &a, const aurora::SourceSpan &b) {
    require(a.source == b.source, "source snapshot identity differs");
    samePosition(a.begin, b.begin);
    samePosition(a.end, b.end);
}
void sameToken(const aurora::Token &a, const aurora::Token &b) {
    require(a.text == b.text && a.line == b.line, "token spelling/line differs");
    sameSpan(a.span, b.span);
}
void sameExpression(const aurora::ExpressionPtr &a, const aurora::ExpressionPtr &b) {
    require(bool(a) == bool(b), "expression presence differs");
    if (!a)
        return;
    require(a->op == b->op && a->depth == b->depth && a->token.text == b->token.text &&
                a->token.line == b->token.line && a->args.size() == b->args.size() && a->fieldNames == b->fieldNames &&
                a->templateArguments == b->templateArguments && a->reflectedType == b->reflectedType,
            "expression shape/spelling/depth differs at " + a->op + ":" + a->token.text + " versus " + b->op + ":" +
                b->token.text);
    sameSpan(a->token.span, b->token.span);
    for (std::size_t i = 0; i < a->args.size(); ++i)
        sameExpression(a->args[i], b->args[i]);
}
std::size_t nodes(const aurora::ExpressionPtr &expression) {
    std::size_t count = 1;
    for (const auto &child : expression->args)
        count += nodes(child);
    return count;
}
// These builders describe expected trees, never parse source. Token ordinals and
// qualified-token ranges are supplied by each fixture; depth follows that stated
// tree. All other Expression fields retain their independent default values.
struct Ast {
    std::string op;
    std::size_t first, last;
    std::vector<Ast> args;
    std::vector<std::string> fields;
    std::vector<aurora::TemplateArgument> types;
    aurora::Type reflected;
};
Ast tree(std::string op, std::size_t token, std::vector<Ast> args = {}) {
    return {std::move(op), token, token, std::move(args), {}, {}, {}};
}
Ast number(std::size_t token) {
    return tree("number", token);
}
Ast name(std::size_t token, std::size_t last) {
    auto result = tree("name", token);
    result.last = last;
    return result;
}
Ast name(std::size_t token) {
    return name(token, token);
}
Ast binary(std::size_t token, Ast left, Ast right) {
    return tree("binary", token, {std::move(left), std::move(right)});
}
Ast call(std::size_t token, std::vector<Ast> args = {}, std::size_t last = std::string::npos) {
    auto result = tree("call", token, std::move(args));
    result.last = last == std::string::npos ? token : last;
    return result;
}
Ast index(Ast base, Ast subscript) {
    auto result = tree("index", base.first, {base, std::move(subscript)});
    result.last = base.last;
    return result;
}
Ast typed(Ast expression, std::vector<aurora::TemplateArgument> types) {
    expression.types = std::move(types);
    return expression;
}
Ast reflected(std::size_t token, aurora::Type type) {
    auto result = call(token);
    result.reflected = std::move(type);
    return result;
}
Ast construct(std::size_t first, std::size_t last, std::vector<std::string> fields = {}, std::vector<Ast> args = {}) {
    auto result = tree("construct", first, std::move(args));
    result.last = last;
    result.fields = std::move(fields);
    return result;
}
aurora::TemplateArgument namedArgument(std::string name, std::vector<aurora::TemplateArgument> args = {}) {
    aurora::TemplateArgument result(std::move(name));
    result.templateArguments = std::move(args);
    return result;
}
aurora::Type namedType(std::string name, std::vector<aurora::TemplateArgument> args = {}) {
    aurora::Type result(std::move(name));
    result.templateArguments = std::move(args);
    return result;
}
aurora::ExpressionPtr expectedTree(const std::vector<aurora::Token> &tokens, const Ast &spec) {
    auto token = tokens.at(spec.first);
    for (auto ordinal = spec.first + 1; ordinal <= spec.last; ++ordinal)
        token.text += tokens.at(ordinal).text;
    token.span.end = tokens.at(spec.last).span.end;
    auto result = std::make_shared<aurora::Expression>(spec.op, token);
    result->fieldNames = spec.fields;
    result->templateArguments = spec.types;
    result->reflectedType = spec.reflected;
    for (const auto &child : spec.args) {
        result->args.push_back(expectedTree(tokens, child));
        result->depth = std::max(result->depth, result->args.back()->depth + 1);
    }
    return result;
}
// Body AST contracts compare every ordered statement field, including the
// declaration binding span rather than inferring it from the initializer.
void sameStatements(const std::vector<aurora::StatementPtr> &actual,
                    const std::vector<aurora::StatementPtr> &expected) {
    require(actual.size() == expected.size(), "statement list size/order differs");
    for (std::size_t index = 0; index < actual.size(); ++index) {
        const auto &a = actual[index];
        const auto &b = expected[index];
        require(a && b && a->kind == b->kind && a->name == b->name && a->fieldName == b->fieldName &&
                    a->type == b->type && a->mutableValue == b->mutableValue,
                "statement kind/binding/type/field/mutability differs");
        sameToken(a->token, b->token);
        sameSpan(a->bindingSpan, b->bindingSpan);
        sameExpression(a->expr, b->expr);
        sameExpression(a->target, b->target);
        sameStatements(a->body, b->body);
        sameStatements(a->other, b->other);
    }
}
aurora::StatementPtr statement(const std::vector<aurora::Token> &tokens,
                               std::size_t token,
                               const std::string &kind,
                               std::optional<Ast> expression = {}) {
    auto value = std::make_shared<aurora::Statement>(tokens.at(token));
    value->kind = kind;
    if (expression)
        value->expr = expectedTree(tokens, *expression);
    return value;
}
aurora::StatementPtr local(const std::vector<aurora::Token> &tokens,
                           std::size_t token,
                           std::size_t binding,
                           aurora::Type type,
                           bool mutableValue,
                           Ast expression) {
    auto value = statement(tokens, token, "let", std::move(expression));
    value->name = tokens.at(binding).text;
    value->bindingSpan = tokens.at(binding).span;
    value->type = std::move(type);
    value->mutableValue = mutableValue;
    return value;
}
std::string fixtureKey(const std::vector<aurora::Token> &tokens) {
    std::string result;
    for (const auto &token : tokens)
        result += std::to_string(token.text.size()) + ":" + token.text;
    return result;
}
struct ExpectedExpression {
    Ast tree;
    std::size_t next;
};
std::map<std::string, ExpectedExpression> expressionExpectations;
void pinExact(const std::string &source, Ast expected, std::size_t next) {
    expressionExpectations.insert_or_assign(fixtureKey(aurora::lex(source, "expectation.au")),
                                            ExpectedExpression{std::move(expected), next});
}
void pin(const std::string &source, const Ast &expected) {
    const auto next = aurora::lex(source, "expectation.au").size() - 1;
    pinExact(source + ";", expected, next);
    pinExact(source + ")", expected, next);
}
struct ExpectedError {
    std::string message;
    std::size_t token;
    int half = 0;
    aurora::DiagnosticCode code = aurora::DiagnosticCode::UnexpectedToken;
};
std::map<std::string, ExpectedError> errorExpectations;
void pinError(const std::string &source,
              std::string message,
              std::size_t token,
              int half = 0,
              aurora::DiagnosticCode code = aurora::DiagnosticCode::UnexpectedToken) {
    errorExpectations.insert_or_assign(fixtureKey(aurora::lex(source, "expectation.au")),
                                       ExpectedError{std::move(message), token, half, code});
}
void sameError(const aurora::Diagnostic &actual,
               const std::vector<aurora::Token> &tokens,
               const ExpectedError &expected,
               std::size_t base = 0) {
    auto token = tokens.at(base + expected.token);
    if (expected.half) {
        require(token.text == ">>", "half-token expectation requires an original >> token");
        token.text = ">";
        ++token.span.begin.offset;
        ++token.span.begin.column;
    }
    const auto message =
        expected.message +
        (expected.code == aurora::DiagnosticCode::UnexpectedToken ? " (found '" + token.text + "')" : "");
    require(actual.code == expected.code && actual.message == message,
            "diagnostic differs: " + actual.message + " versus " + message);
    sameSpan(actual.span, token.span);
}
// Program-only declaration contracts require separate pinned predecessor/current
// source qualification. This check claims acceptance, not an AST
// oracle; expression dispatch inventories below carry their stated assertions.
aurora::Program checkedProgram(const std::vector<aurora::Token> &tokens) {
    auto program = aurora::Parser(tokens).parse();
    require(!program.moduleName.empty(), "accepted program lost its module");
    ++cases;
    return program;
}
void statementRoots(const std::vector<aurora::StatementPtr> &statements, std::vector<aurora::ExpressionPtr> &roots) {
    for (const auto &statement : statements) {
        if (statement->expr)
            roots.push_back(statement->expr);
        if (statement->target)
            roots.push_back(statement->target);
        statementRoots(statement->body, roots);
        statementRoots(statement->other, roots);
    }
}
void functionRoots(const std::vector<aurora::Function> &functions, std::vector<aurora::ExpressionPtr> &roots) {
    for (const auto &function : functions) {
        for (const auto &initializer : function.initializers)
            roots.push_back(initializer.second);
        statementRoots(function.body, roots);
    }
}
void checkedProgram(const std::string &source, const std::vector<Ast> &expected) {
    context = source;
    const auto tokens = aurora::lex(source, "program-roots.au");
    const auto program = checkedProgram(tokens);
    std::vector<aurora::ExpressionPtr> roots;
    functionRoots(program.functions, roots);
    functionRoots(program.functionTemplates, roots);
    for (const auto &definition : program.classes)
        functionRoots(definition.methods, roots);
    for (const auto &definition : program.templates)
        functionRoots(definition.methods, roots);
    require(roots.size() == expected.size(), "program expression-root count/order differs");
    for (std::size_t index = 0; index < roots.size(); ++index)
        sameExpression(roots[index], expectedTree(tokens, expected[index]));
}
void rejectedProgram(const std::string &prefix,
                     const std::string &expression,
                     const std::string &suffix,
                     const ExpectedError &expected) {
    context = prefix + expression + suffix;
    const auto tokens = aurora::lex(context, "parser-program-error.au");
    std::optional<aurora::Diagnostic> diagnostic;
    try {
        aurora::Parser(tokens).parse();
    } catch (const aurora::Error &error) {
        diagnostic = error.diagnostic;
    }
    require(bool(diagnostic), "malformed program was accepted");
    sameError(*diagnostic, tokens, expected, aurora::lex(prefix, "prefix.au").size() - 1);
    ++cases;
}
void rejectedProgram(const std::string &prefix, const std::string &expression, const std::string &suffix) {
    const auto found = errorExpectations.find(fixtureKey(aurora::lex(expression, "expectation.au")));
    require(found != errorExpectations.end(), "missing explicit program rejection for " + expression);
    rejectedProgram(prefix, expression, suffix, found->second);
}
std::string chain(std::size_t count) {
    std::string result = "1";
    while (--count)
        result += "+1";
    return result;
}
Ast sum(std::size_t count, std::size_t first = 0) {
    auto result = number(first);
    for (std::size_t index = 1; index < count; ++index)
        result = binary(first + 2 * index - 1, std::move(result), number(first + 2 * index));
    return result;
}
void supported(const std::string &text, Stop stop = Stop::Semicolon) {
    context = text;
    const auto tokens = aurora::lex(text, "supported.au");
    const auto found = expressionExpectations.find(fixtureKey(tokens));
    require(found != expressionExpectations.end(), "missing explicit AST fixture");
    std::size_t position = 0;
    const auto expression = aurora::parseHostedExpression(tokens, position, stop);
    require(bool(expression), "supported expression was not parsed");
    sameExpression(expression, expectedTree(tokens, found->second.tree));
    require(position == found->second.next, "expression committed the wrong token ordinal");
    if (text == chain(100) + ";")
        require(nodes(expression) == 199 && expression->depth == 100, "100 terms did not yield 199 Aurora nodes");
    ++cases;
}
void rejected(const std::string &text, Stop stop = Stop::Semicolon) {
    context = text;
    const auto tokens = aurora::lex(text, "typed-rejection.au"), before = tokens;
    const auto found = errorExpectations.find(fixtureKey(tokens));
    require(found != errorExpectations.end(), "missing explicit rejection fixture");
    std::optional<aurora::Diagnostic> diagnostic;
    std::size_t position = 0;
    try {
        aurora::parseHostedExpression(tokens, position, stop);
    } catch (const aurora::Error &error) {
        diagnostic = error.diagnostic;
    }
    require(bool(diagnostic), "malformed expression was accepted");
    sameError(*diagnostic, tokens, found->second);
    require(position == 0 && tokens.size() == before.size(), "rejection changed its caller cursor/tokens");
    for (std::size_t index = 0; index < tokens.size(); ++index)
        sameToken(tokens[index], before[index]);
    ++cases;
}

template <typename Expected> void bodyFixture(const std::string &source, Expected expected) {
    context = "explicit body AST " + source;
    const auto tokens = aurora::lex(source, "body-contract.au"), before = tokens;
    std::size_t position = 0;
    const auto body = aurora::parseHostedBody(tokens, position);
    sameStatements(body, expected(tokens));
    require(position == tokens.size() - 1, "body did not consume its exact closing brace");
    for (std::size_t index = 0; index < tokens.size(); ++index)
        sameToken(tokens[index], before[index]);
    ++cases;
}
void bodySyntax() {
    using Body = std::vector<aurora::StatementPtr>;
    bodyFixture("{}", [](const auto &) {
        return Body{};
    });
    bodyFixture("{{}}", [](const auto &tokens) {
        return Body{statement(tokens, 1, "block")};
    });
    bodyFixture("{i64 x=1;const u8 y=2u8;return x;}", [](const auto &tokens) {
        return Body{local(tokens, 1, 2, aurora::Type::I64, true, number(4)),
                    local(tokens, 6, 8, aurora::Type::U8, false, number(10)),
                    statement(tokens, 12, "return", name(13))};
    });
    bodyFixture("{x=1;obj.field=2;a[0]=3;f();}", [](const auto &tokens) {
        auto assign = statement(tokens, 1, "assign", number(3));
        assign->name = "x";
        auto field = statement(tokens, 5, "field_assign", number(9));
        field->name = "obj";
        field->fieldName = "field";
        auto element = statement(tokens, 11, "index_assign", number(16));
        element->target = expectedTree(tokens, index(name(11), number(13)));
        return Body{assign, field, element, statement(tokens, 18, "expression", call(18))};
    });
    bodyFixture("{if(true){return 1;}else{while(false){return 2;}}}", [](const auto &tokens) {
        auto branch = statement(tokens, 1, "if", tree("bool", 3));
        branch->body = {statement(tokens, 6, "return", number(7))};
        auto loop = statement(tokens, 12, "while", tree("bool", 14));
        loop->body = {statement(tokens, 17, "return", number(18))};
        branch->other = {loop};
        return Body{branch};
    });
    bodyFixture("{static_assert(1);{return (2);}}", [](const auto &tokens) {
        auto block = statement(tokens, 6, "block");
        block->body = {statement(tokens, 7, "return", number(9))};
        return Body{statement(tokens, 1, "static_assert", number(3)), block};
    });
    bodyFixture("{array<u8,2> bytes={1u8,2u8};return bytes[0];}", [](const auto &tokens) {
        return Body{local(tokens,
                          1,
                          7,
                          aurora::Type::array(aurora::TypeKind::U8, 2),
                          true,
                          tree("array_literal", 9, {number(10), number(12)})),
                    statement(tokens, 15, "return", index(name(16), number(18)))};
    });
    bodyFixture("{Box<Box<i64>> value=Box<Box<i64>>{};return size_of(Box<Box<i64>>);}", [](const auto &tokens) {
        const auto inner = namedArgument("Box", {aurora::TypeKind::I64});
        const auto type = namedType("Box", {inner});
        return Body{local(tokens, 1, 7, type, true, typed(construct(9, 9), {inner})),
                    statement(tokens, 18, "return", reflected(19, type))};
    });
    bodyFixture("{1;if(true){2;}else{}3;while(false){}4;}", [](const auto &tokens) {
        auto branch = statement(tokens, 3, "if", tree("bool", 5));
        branch->body = {statement(tokens, 8, "expression", number(8))};
        auto loop = statement(tokens, 16, "while", tree("bool", 18));
        return Body{statement(tokens, 1, "expression", number(1)),
                    branch,
                    statement(tokens, 14, "expression", number(14)),
                    loop,
                    statement(tokens, 22, "expression", number(22))};
    });
    bodyFixture("{return values[indices[0]];}", [](const auto &tokens) {
        return Body{statement(tokens, 1, "return", index(name(2), index(name(4), number(6))))};
    });
    bodyFixture("{\n const i64 binding = 1;\n return binding;\n}", [](const auto &tokens) {
        return Body{local(tokens, 1, 3, aurora::Type::I64, false, number(5)), statement(tokens, 7, "return", name(8))};
    });
    // These spellings remain unresolved named types after const. In contrast,
    // the same first-token control words cannot be reclassified as locals.
    bodyFixture("{const return x=1;const if y=2;const while z=3;static_assert a=4;}", [](const auto &tokens) {
        return Body{local(tokens, 1, 3, aurora::Type("return"), false, number(5)),
                    local(tokens, 7, 9, aurora::Type("if"), false, number(11)),
                    local(tokens, 13, 15, aurora::Type("while"), false, number(17)),
                    local(tokens, 19, 20, aurora::Type("static_assert"), true, number(22))};
    });
    // The root consumes exactly its own brace even when a second body follows.
    const auto tokens = aurora::lex("{} {return 1;}", "body-boundary.au");
    std::size_t position = 0;
    require(aurora::parseHostedBody(tokens, position).empty() && position == 2,
            "empty body consumed the following body");
    const auto second = aurora::parseHostedBody(tokens, position);
    sameStatements(second, {statement(tokens, 3, "return", number(4))});
    require(position == 7, "second body did not stop at EOF");
    ++cases;
    // Root block counts once. If/while wrappers must not halve the block limit.
    for (const std::string kind : {"block", "if", "while"}) {
        const auto opening = kind == "block" ? "{" : kind + "(true){";
        std::string source = "{";
        for (int level = 1; level < 128; ++level)
            source += opening;
        source += "return 1;" + std::string(128, '}');
        const auto nested = aurora::lex(source, "body-depth.au");
        std::size_t at = 0;
        auto body = aurora::parseHostedBody(nested, at);
        require(at == nested.size() - 1, "128-block body cursor differs");
        for (int level = 1; level < 128; ++level) {
            require(body.size() == 1 && body[0]->kind == kind && body[0]->other.empty(),
                    "nested body wrapper/order differs");
            body = body[0]->body;
        }
        require(body.size() == 1 && body[0]->kind == "return" && body[0]->expr->token.text == "1",
                "nested body lost its final statement");
        ++cases;
    }
}
void bodyContexts() {
    using T = aurora::Type;
    using K = aurora::TypeKind;
    auto parameter = T(K::Parameter), otherParameter = T(K::Parameter);
    parameter.className = "T";
    otherParameter.className = "U";
    auto typeArgument = namedArgument("T"), otherArgument = namedArgument("U");
    typeArgument.type = otherArgument.type = K::Parameter;
    auto dependentArray = T::array(parameter, 0);
    dependentArray.lengthParameter = "N";
    for (const bool function : {false, true}) {
        const std::string prefix =
            function ? "export module body_context;template<Value T,Value U>auto f(T x,U y)->i64"
                     : "export module body_context;template<Scalar T,i64 N>class Buffer{public:auto f()->i64";
        const std::string body = function ? "{const Pair<T,U> p=Pair<T,U>(x,y);return size_of(T)+type_id(U);}"
                                          : "{array<T,N> items={};return size_of(T);}";
        const auto tokens = aurora::lex(prefix + body + (function ? "" : "};"), "body-context.au");
        context = function ? "explicit function-template body context" : "explicit class-template body context";
        const auto begin = aurora::lex(prefix).size() - 1;
        Context captured;
        require(tokens.at(7).text == "T" && tokens.at(10).text == (function ? "U" : "N"),
                "body context fixture lost its original declaration tokens");
        captured.typeParameters = {tokens.at(7)};
        if (function)
            captured.typeParameters.push_back(tokens.at(10));
        else
            captured.capacityParameters.push_back(tokens.at(10));
        captured.functionTemplate = function;
        std::vector<aurora::StatementPtr> expected;
        if (function) {
            expected = {
                local(tokens,
                      begin + 1,
                      begin + 8,
                      namedType("Pair", {typeArgument, otherArgument}),
                      false,
                      typed(call(begin + 10, {name(begin + 17), name(begin + 19)}), {typeArgument, otherArgument})),
                statement(tokens,
                          begin + 22,
                          "return",
                          binary(begin + 27, reflected(begin + 23, parameter), reflected(begin + 28, otherParameter)))};
        } else {
            expected = {local(tokens, begin + 1, begin + 7, dependentArray, true, tree("array_literal", begin + 9)),
                        statement(tokens, begin + 12, "return", reflected(begin + 13, parameter))};
        }
        auto position = begin;
        sameStatements(aurora::parseHostedBody(tokens, position, captured), expected);
        require(position == begin + aurora::lex(body).size() - 1, "context body consumed a declaration delimiter");
        const auto program = checkedProgram(tokens);
        if (function) {
            require(program.functionTemplates.size() == 1, "function-template body fixture was omitted");
            sameStatements(program.functionTemplates.front().body, expected);
        } else {
            require(program.templates.size() == 1 && program.templates.front().methods.size() == 1,
                    "class-template body fixture was omitted");
            sameStatements(program.templates.front().methods.front().body, expected);
        }
        ++cases;
    }
}
void bodyDiagnostics() {
    struct Rejection {
        const char *source;
        const char *message;
        std::size_t token;
    };
    for (const auto &test : std::vector<Rejection>{{"return 1;", "expected '{'", 0},
                                                   {"{", "unterminated block", 1},
                                                   {"{return 1;", "unterminated block", 4},
                                                   {"{return 1}", "expected ';'", 3},
                                                   {"{return;}", "expected expression", 3},
                                                   {"{1 2;}", "expected ';'", 2},
                                                   {"{if true){}}", "expected '('", 2},
                                                   {"{if(true {}}", "expected ')'", 4},
                                                   {"{if(true)1;}", "expected '{'", 5},
                                                   {"{if(true){}else if(false){}}", "expected '{'", 8},
                                                   {"{while(1){}", "unterminated block", 7},
                                                   {"{static_assert 1;}", "expected '('", 2},
                                                   {"{static_assert(1)}", "expected ';'", 5},
                                                   {"{i64 x 1;}", "expected '='", 3},
                                                   {"{const i64 x=1}", "expected ';'", 6},
                                                   {"{i64 true=1;}", "reserved identifier", 2},
                                                   {"{1=2;}", "assignment requires a local or local field", 3},
                                                   {"{f()=2;}", "assignment requires a local or local field", 5},
                                                   {"{a.b.c=2;}", "assignment requires a local or local field", 7},
                                                   {"{return f(1;}", "expected ')'", 5},
                                                   {"{if(1 2){}}", "expected ')'", 4},
                                                   {"{i64 x=1 2;}", "expected ';'", 5},
                                                   {"{return size_of(i64,);}", "expected ')'", 5},
                                                   {"{return x=1;}", "expected ';'", 3},
                                                   {"{if x=1;}", "expected '('", 2},
                                                   {"{while x=1;}", "expected '('", 2}}) {
        context = "explicit body diagnostic " + std::string(test.source);
        const auto tokens = aurora::lex(test.source, "body-error.au"), before = tokens;
        std::size_t position = 0;
        std::optional<aurora::Diagnostic> diagnostic;
        try {
            static_cast<void>(aurora::parseHostedBody(tokens, position));
        } catch (const aurora::Error &error) {
            diagnostic = error.diagnostic;
        }
        require(bool(diagnostic) && position == 0, "body rejection was accepted or committed cursor");
        sameError(*diagnostic, tokens, {test.message, test.token});
        for (std::size_t index = 0; index < tokens.size(); ++index)
            sameToken(tokens[index], before[index]);
        ++cases;
    }
    for (const std::string kind : {"block", "if", "while"}) {
        const auto opening = kind == "block" ? "{" : kind + "(true){";
        std::string source = "{";
        for (int level = 1; level < 129; ++level)
            source += opening;
        source += std::string(129, '}');
        const auto tokens = aurora::lex(source, "body-depth-error.au");
        std::size_t position = 0;
        std::optional<aurora::Diagnostic> diagnostic;
        try {
            static_cast<void>(aurora::parseHostedBody(tokens, position));
        } catch (const aurora::Error &error) {
            diagnostic = error.diagnostic;
        }
        require(bool(diagnostic) && position == 0, "129-block body was accepted or committed cursor");
        sameError(
            *diagnostic,
            tokens,
            {"block nesting exceeds 128", kind == "block" ? 128u : 640u, 0, aurora::DiagnosticCode::NestingLimit});
        ++cases;
    }
}

void diagnosticExpectations() {
    struct Rejection {
        const char *source;
        const char *message;
        std::size_t token;
        int half = 0;
    };
    for (const auto &test : std::vector<Rejection>{
             {"f<T)>(0);", "expected '>'", 3},
             {"f<T]>(0);", "expected '>'", 3},
             {"f<T:>(0);", "expected '>'", 3},
             {"f<>(0);", "expected identifier", 2},
             {"f<i64,>(0);", "expected identifier", 4},
             {"(f<T)>(0);", "expected '>'", 4},
             {"{f<T)>(0)};", "expected '>'", 4},
             {"Box{.value=f<T)>(0)};", "expected '>'", 8},
             {"f< T // malformed trivia\n ) >(0);", "expected '>'", 3},
             {"f<i64,u8,bool>(0);", "template arguments are limited to one or two types or capacity literals", 6},
             {"f<0>(0);", "capacity template arguments must be decimal literals from 1 to 64", 3},
             {"f<65>(0);", "capacity template arguments must be decimal literals from 1 to 64", 3},
             {"f<1u64>(0);", "capacity template arguments must be decimal literals from 1 to 64", 3},
             {"f<18446744073709551616>(0);", "capacity template arguments must be decimal literals from 1 to 64", 3},
             {"f<true>(0);",
              "template arguments require scalar, named class or enum types, or capacities from 1 to 64",
              2},
             {"f<false>(0);",
              "template arguments require scalar, named class or enum types, or capacities from 1 to 64",
              2},
             {"f<own>(0);",
              "template arguments require scalar, named class or enum types, or capacities from 1 to 64",
              2},
             {"f<ref>(0);",
              "template arguments require scalar, named class or enum types, or capacities from 1 to 64",
              2},
             {"f<mutref>(0);",
              "template arguments require scalar, named class or enum types, or capacities from 1 to 64",
              2},
             {"f<array>(0);",
              "template arguments require scalar, named class or enum types, or capacities from 1 to 64",
              2},
             {"f<builtin>(0);",
              "template arguments require scalar, named class or enum types, or capacities from 1 to 64",
              2},
             {"f<fn>(0);", "reserved identifier", 2},
             {"f<ns::true>(0);", "reserved identifier", 4},
             {"f<__au_private>(0);", "reserved compiler identifier prefix: __au_", 2},
             {"size_of();", "expected type name", 3},
             {"size_of(fn);", "unsupported or reserved type spelling", 2},
             {"size_of(123);", "expected type name", 3},
             {"size_of(i64,u8);", "expected ')'", 3},
             {"size_of(own);", "expected '<'", 3},
             {"size_of(own<u8>);", "expected 'i64'", 4},
             {"size_of(ref<i64>>);", "expected '>'", 5},
             {"size_of(mutref<i64);", "expected '>'", 5},
             {"size_of(builtin);", "expected '::'", 3},
             {"size_of(builtin::unknown);", "expected 'array'", 4},
             {"size_of(builtin::span<u8>);", "expected 'const'", 6},
             {"size_of(builtin::span<const i64>);", "expected 'u8'", 7},
             {"size_of(builtin::span<const u8>>);", "expected '>'", 8},
             {"size_of(array<i64>);", "expected ','", 5},
             {"size_of(array<own<i64>,1>);", "array elements require i64, u64, u8, bool or a concrete copied class", 8},
             {"size_of(array<array<i64,1>,1>);",
              "array elements require i64, u64, u8, bool or a concrete copied class",
              10},
             {"size_of(array<i64,0>);", "array length requires a decimal integer literal between 1 and 4096", 7},
             {"size_of(array<i64,4097>);", "array length requires a decimal integer literal between 1 and 4096", 7},
             {"size_of(array<i64,1u64>);", "array length requires a decimal integer literal between 1 and 4096", 7},
             {"size_of(array<i64,N>);", "array length requires a decimal integer literal between 1 and 4096", 7},
             {"size_of(array<Class,65>);", "class-element array capacity must be between 1 and 64", 8},
             {"size_of(builtin::OwnedValues<i64>);", "owned values require a named concrete copied class", 7},
             {"size_of(builtin::OwnedValues<Box<i64>>);", "owned values require a named concrete copied class", 9, 1},
             {"size_of(Box<i64,u8,bool>);",
              "template arguments are limited to one or two types or capacity literals",
              8},
             {"size_of(Box<i64,>);", "expected identifier", 6},
             {"size_of(Box<0>);", "capacity template arguments must be decimal literals from 1 to 64", 5},
             {"size_of(array<builtin::ConsolePutResult,2>);",
              "array elements require i64, u64, u8, bool or a concrete copied class",
              7},
             {"size_of(array<builtin::DisplayCompletion,2>);",
              "array elements require i64, u64, u8, bool or a concrete copied class",
              7},
             {"size_of(builtin::OwnedValues<builtin::EventPollResult>);",
              "owned values require a named concrete copied class",
              9},
             {"size_of(Box<i64>>);", "expected ')'", 5, 1},
             {"size_of(array<i64,2>>);", "expected ')'", 7, 1},
             {"size_of(builtin::OwnedValues<Value>>);", "expected ')'", 7, 1},
             {";", "expected expression", 1},
             {"1 + ;", "expected expression", 3},
             {"(1 + 2;", "expected ')'", 4},
             {"1 2;", "expected ';'", 1},
             {"1 +", "expected expression", 3},
             {"(1) + ;", "expected expression", 5},
             {":;", "expected expression", 1},
             {"];", "expected expression", 1},
             {",;", "expected expression", 1},
             {"1:2;", "expected ';'", 1},
             {"1]2;", "expected ';'", 1},
             {"1,2;", "expected ';'", 1},
             {"1(2);", "expected ';'", 1},
             {"true(2);", "expected ';'", 1},
             {"(1)(2);", "expected ';'", 3},
             {"f(;", "expected expression", 3},
             {"f(1;", "expected ')'", 3},
             {"f(1,);", "expected expression", 5},
             {"f(,);", "expected expression", 3},
             {"f(1 2);", "expected ')'", 3},
             {"a.;", "expected identifier", 2},
             {"a..b;", "expected identifier", 2},
             {"a.true;", "reserved identifier", 2},
             {"a.array;", "reserved builtin storage name", 2},
             {"a.builtin;", "reserved builtin storage name", 2},
             {"a.__au_private;", "reserved compiler identifier prefix: __au_", 2},
             {"name::;", "expected identifier", 2},
             {"name::true;", "reserved identifier", 2},
             {"name::builtin;", "reserved builtin storage name", 2},
             {"name::__au_x;", "reserved compiler identifier prefix: __au_", 2},
             {"a[;", "expected expression", 3},
             {"a[];", "expected expression", 3},
             {"a[1;", "expected ']'", 3},
             {"a[1);", "expected ']'", 3},
             {"a[1,2];", "expected ']'", 3},
             {"f(1)(2);", "expected ';'", 4},
             {"{,};", "expected expression", 2},
             {"{1,};", "expected expression", 4},
             {"{1 2};", "expected '}'", 2},
             {"{1;", "expected '}'", 2},
             {"{1,2", "expected ';'", 5},
             {"{1];", "expected '}'", 2},
             {"{1)};", "expected '}'", 2},
             {"Box{value=1};", "expected '.'", 2},
             {"Box{..value=1};", "expected identifier", 3},
             {"Box{.1=1};", "expected identifier", 3},
             {"Box{.true=1};", "reserved identifier", 3},
             {"Box{.array=1};", "reserved builtin storage name", 3},
             {"Box{.builtin=1};", "reserved builtin storage name", 3},
             {"Box{.__au_private=1};", "reserved compiler identifier prefix: __au_", 3},
             {"Box{.value 1};", "expected '='", 4},
             {"Box{.value==1};", "expected '='", 4},
             {"Box{.value=};", "expected expression", 6},
             {"Box{.value=1,};", "expected '.'", 7},
             {"Box{.value=1;", "expected '}'", 6},
             {"Box{.value=1 .other=2};", "expected '}'", 6},
             {"Box{.value={1,}};", "expected expression", 9},
             {"{}(1);", "expected ';'", 2},
             {"Box{}(1);", "expected ';'", 3},
             {"{f<T]>(0)}", "expected '>'", 4},
             {"{f<T:>(0)}", "expected '>'", 4},
             {"f({f<T]>(0)})", "expected '>'", 6},
             {"", "expected expression", 1},
             {"(1 + 2", "expected ')'", 5},
             {"1 2", "expected ')'", 1},
             {"a[1", "expected ']'", 3},
             {R"("text"(1))", "expected ')'", 1},
             {R"("text"[0])", "expected ')'", 1},
             {"{1", "expected '}'", 2},
             {"{1]}", "expected '}'", 2},
             {"{Box{.value=1,}}", "expected '.'", 8}}) {
        pinError(test.source, test.message, test.token, test.half);
        const std::string source = test.source;
        if (source.ends_with(';'))
            pinError(source.substr(0, source.size() - 1), test.message, test.token, test.half);
    }
    // In an initializer, a consumed ')' leaves its outer ')' as the exact error
    // token. Unlike return statements, its terminator is not a semicolon.
    pinError("1 +", "expected expression", 3);
    pinError("(f<T)>(0)", "expected '>'", 4);
    pinError("f<A<B<C<D<E<i64>>>>>>();", "template-id nesting exceeds 5", 11, 0, aurora::DiagnosticCode::NestingLimit);
    pinError(
        "size_of(A<B<C<D<E<i64>>>>>);", "template-id nesting exceeds 4", 11, 0, aurora::DiagnosticCode::NestingLimit);
}

Ast shifted(Ast value, std::size_t offset) {
    value.first += offset;
    value.last += offset;
    for (auto &child : value.args)
        child = shifted(std::move(child), offset);
    return value;
}
Ast pinned(const std::string &source) {
    return expressionExpectations.at(fixtureKey(aurora::lex(source + ";", "expectation.au"))).tree;
}
void checkedRootProgram(const std::string &prefix,
                        const std::string &expression,
                        const std::string &suffix,
                        bool constructor = false) {
    context = prefix + expression + suffix;
    const auto tokens = aurora::lex(context, "program-root.au");
    const auto program = checkedProgram(tokens);
    auto source = expression;
    if (source.ends_with(';'))
        source.pop_back();
    const auto expected = shifted(pinned(source), aurora::lex(prefix, "prefix.au").size() - 1);
    if (constructor) {
        require(program.classes.size() == 1 && program.classes[0].methods.size() == 2 &&
                    program.classes[0].methods[0].initializers.size() == 1 &&
                    program.classes[0].methods[0].initializers[0].first.text == "value",
                "constructor initializer declaration/order differs");
        sameExpression(program.classes[0].methods[0].initializers[0].second, expectedTree(tokens, expected));
        sameExpression(program.classes[0].methods[1].body.at(0)->expr, expectedTree(tokens, name(tokens.size() - 6)));
    } else {
        require(program.functions.size() == 1 && program.functions[0].body.size() == 1 &&
                    program.functions[0].body[0]->kind == "return",
                "return fixture statement inventory differs");
        sameExpression(program.functions[0].body[0]->expr, expectedTree(tokens, expected));
    }
}
void checkedBracedProgram(const std::string &prefix, const std::string &contents, const std::string &suffix) {
    const auto field = aurora::lex(prefix, "prefix.au").size() - 2;
    auto expected = shifted(pinned(contents), 1);
    expected.first = expected.last = 0;
    if (expected.args.empty())
        expected.op = "array_zero";
    checkedProgram(prefix + contents + suffix, {shifted(expected, field)});
}
void grammarExpectations() {
    using K = aurora::TypeKind;
    using T = aurora::Type;
    const auto capacity = aurora::TemplateArgument::capacity;
    const auto array = [](std::size_t token, std::vector<Ast> children = {}) {
        return tree("array_literal", token, std::move(children));
    };
    const auto unary = [](std::size_t token, Ast child) {
        return tree("unary", token, {std::move(child)});
    };
    const auto member = [](std::size_t token, Ast child) {
        return tree("member", token, {std::move(child)});
    };
    const auto method = [](std::size_t token, std::vector<Ast> children) {
        return tree("method_call", token, std::move(children));
    };
    for (const auto &text : {"1", "123u64", "255u8"})
        pin(text, number(0));
    for (const auto &text : {"false", "true"})
        pin(text, tree("bool", 0));
    for (const auto &text : {"name", "_value", "fn", "__au_name", "x"})
        pin(text, name(0));
    for (const auto &text : {"'x'", "'\\n'"})
        pin(text, tree("byte", 0));
    pin("-1 + ~2 * !false", binary(2, unary(0, number(1)), binary(5, unary(3, number(4)), unary(6, tree("bool", 7)))));
    auto precedence = binary(35, binary(33, binary(31, name(30), name(32)), name(34)), name(36));
    precedence = binary(29, binary(27, name(26), name(28)), precedence);
    precedence = binary(25, binary(23, name(22), name(24)), precedence);
    precedence = binary(21, binary(19, binary(17, binary(15, name(14), name(16)), name(18)), name(20)), precedence);
    precedence = binary(13, binary(11, name(10), name(12)), precedence);
    for (const std::size_t op : {9, 7, 5, 3, 1})
        precedence = binary(op, name(op - 1), precedence);
    pin("a || b && c | d ^ e & f == g != h < i <= j > k >= l << m >> n + o - p * q / r % s", precedence);
    pin("(a + b) * (c - d)", binary(5, binary(2, name(1), name(3)), binary(8, name(7), name(9))));
    pin("(a)", name(1));
    pin("1 + 2", binary(1, number(0), number(2)));
    pin("a < b >> (c)", binary(1, name(0), binary(3, name(2), name(5))));
    pin("true < x > (y)", binary(3, binary(1, tree("bool", 0), name(2)), name(5)));
    pin("(a) < b > (c)", binary(5, binary(3, name(1), name(4)), name(7)));
    for (const auto count : {100, 128})
        pin(chain(count), sum(count));
    pin(std::string(127, '(') + "1" + std::string(127, ')'), number(127));
    auto negatives = number(127);
    for (std::size_t token = 127; token-- > 0;)
        negatives = unary(token, negatives);
    pin(std::string(127, '-') + "1", negatives);
    pinExact("target = 2;", name(0), 1);
    pin("f()", call(0));
    pin("f(1, 2)", call(0, {number(2), number(4)}));
    pin("name.member", member(2, name(0)));
    pin("name.at(1)", method(2, {name(0), number(4)}));
    pin("one::two", name(0, 2));
    pin("a[1]", index(name(0), number(2)));
    pinExact("a[1] = 2;", index(name(0), number(2)), 4);
    pin("f(g(1), h(2, 3)) + object.at(index + 1)",
        binary(14,
               call(0, {call(2, {number(4)}), call(7, {number(9), number(11)})}),
               method(17, {name(15), binary(20, name(19), number(21))})));
    pin("Box(42)", call(0, {number(2)}));
    pin("move(value)", call(0, {name(2)}));
    pin("one :: two(1, other.run()).field[2].at(3)",
        method(18, {index(member(13, call(0, {number(4), method(8, {name(6)})}, 2)), number(15)), number(20)}));
    pin("((a)).field", member(6, name(2)));
    pin("(a + b)[(i)]", index(binary(2, name(1), name(3)), name(7)));
    pin("a[one::index(f(1))].method().field",
        member(17, method(13, {index(name(0), call(2, {call(6, {number(8)})}, 4))})));
    pin("builtin::borrow_bytes(value)", call(0, {name(4)}, 2));
    pin("one::array(1)", call(0, {number(4)}, 2));
    pin("object.size_of()", method(2, {name(0)}));
    pin("ns::size_of(i64)", call(0, {name(4)}, 2));
    pin("-object.at(1) + f(2)", binary(7, unary(0, method(3, {name(1), number(5)})), call(8, {number(10)})));
    pin("f(a[1], b.member)", call(0, {index(name(2), number(4)), member(9, name(7))}));
    pin("size_of(i64)", reflected(0, T::I64));
    pin("type_id(array<u8,2>)", reflected(0, T::array(K::U8, 2)));
    pin("field_count(Box)", reflected(0, T("Box")));
    pin("f(size_of(i64))", call(0, {reflected(2, T::I64)}));
    pin(R"(f("text"))", call(0, {tree("byte_string", 2)}));
    pin(R"(ns::f("", "é😀", "\0\xff"))",
        call(0, {tree("byte_string", 4), tree("byte_string", 6), tree("byte_string", 8)}, 2));
    pin(R"(object.write("\"\\\n"))", method(2, {name(0), tree("byte_string", 4)}));
    pin(R"("left" == "right")", binary(1, tree("byte_string", 0), tree("byte_string", 2)));
    pin(R"(("text")[0])", index(tree("byte_string", 1), number(4)));
    pin("(x + 1) * 2", binary(5, binary(2, name(1), number(3)), number(6)));
    pin("-x + ns::value", binary(2, unary(0, name(1)), name(3, 5)));
    pin("ns::Mode::ready", name(0, 4));
    pin("ns::make(x, a[2]).field", member(12, call(0, {name(4), index(name(6), number(8))}, 2)));
    pin("object.at(index + 1)", method(2, {name(0), binary(5, name(4), number(6))}));
    pin(R"(f("a\0\xff", a[one::index(f(1))]))",
        call(0, {tree("byte_string", 2), index(name(4), call(6, {call(10, {number(12)})}, 8))}));
    pin("{}", array(0));
    pin("{1}", array(0, {number(1)}));
    pin("{1,2,3}", array(0, {number(1), number(3), number(5)}));
    pin("{1,2}", array(0, {number(1), number(3)}));
    pin("{{1,2},{3,4}}", array(0, {array(1, {number(2), number(4)}), array(7, {number(8), number(10)})}));
    pin("{f(), object.at(2), a[0]}", array(0, {call(1), method(7, {name(5), number(9)}), index(name(12), number(14))}));
    pin("{Box{.value=1}, ns::Box{}, {}}",
        array(0, {construct(1, 1, {"value"}, {number(6)}), construct(9, 11), array(15)}));
    pin("{Box{.value=type_id(array<u8,2>)}}",
        array(0, {construct(1, 1, {"value"}, {reflected(6, T::array(K::U8, 2))})}));
    pin("{{}, {1, {2}}, f(3, {4,5})}",
        array(0,
              {array(1),
               array(4, {number(5), array(7, {number(8)})}),
               call(12, {number(14), array(16, {number(17), number(19)})})}));
    pin("{1,2}[0]", index(array(0, {number(1), number(3)}), number(6)));
    pinExact("{1,2}[0] = 3;", pinned("{1,2}[0]"), 8);
    pin("({1,2}).field", member(8, array(1, {number(2), number(4)})));
    pin("{}.size()", method(3, {array(0)}));
    pin("ns::Box{}", construct(0, 2));
    pin("one :: two::Box{.last=3,.first=1,.middle=2}",
        construct(0, 4, {"last", "first", "middle"}, {number(9), number(14), number(19)}));
    pin("Box{.first=f(1,{2}),.last=Other{.items={3,4}}}",
        construct(0,
                  0,
                  {"first", "last"},
                  {call(5, {number(7), array(9, {number(10)})}),
                   construct(17, 17, {"items"}, {array(22, {number(23), number(25)})})}));
    pin("Box{.value=1}.value", member(8, construct(0, 0, {"value"}, {number(5)})));
    pin("Box{.items={1,2}}.items[0]",
        index(member(12, construct(0, 0, {"items"}, {array(5, {number(6), number(8)})})), number(14)));
    pin("Box{.items={1,2}}.at({3,4}[0])",
        method(12,
               {construct(0, 0, {"items"}, {array(5, {number(6), number(8)})}),
                index(array(14, {number(15), number(17)}), number(20))}));
    pin("f({}, Box{.value=1}, {f(2),object.at(3)})",
        call(0,
             {array(2),
              construct(5, 5, {"value"}, {number(10)}),
              array(13, {call(14, {number(16)}), method(21, {name(19), number(23)})})}));
    pin(R"(f("text", Box{.value=1}))", call(0, {tree("byte_string", 2), construct(4, 4, {"value"}, {number(9)})}));
    pin("{true < x > (y), a < b >> (c)}",
        array(0, {shifted(pinned("true < x > (y)"), 1), shifted(pinned("a < b >> (c)"), 9)}));
    // No candidate closes before '}', so these are comparison/shift trees.
    pin("{1,f<T}>(0)", binary(7, array(0, {number(1), binary(4, name(3), name(5))}), number(9)));
    pin("Box{.first=true < x > (y),.last=a < b >> (c)}",
        construct(
            0, 0, {"first", "last"}, {shifted(pinned("true < x > (y)"), 5), shifted(pinned("a < b >> (c)"), 16)}));
    pin("{Box{}, ns::array{}, object.size_of()}", array(0, {construct(1, 1), construct(5, 7), method(13, {name(11)})}));
    pin("Box{.value={1,2}[0]}", construct(0, 0, {"value"}, {shifted(pinned("{1,2}[0]"), 5)}));
    pin("{1,size_of(i64)}", array(0, {number(1), reflected(3, T::I64)}));
    pin("Box{.first=1,.second=type_id(array<u8,2>)}",
        construct(0, 0, {"first", "second"}, {number(5), reflected(10, T::array(K::U8, 2))}));
    pin("f({1,field_count(Box)})", call(0, {array(2, {number(3), reflected(5, T("Box"))})}));
    pin("{Box{.value=f(size_of(i64))}}", array(0, {construct(1, 1, {"value"}, {call(6, {reflected(8, T::I64)})})}));
    pin("f<i64>()", typed(call(0), {K::I64}));
    pin("f<i64>(1)", typed(call(0, {number(5)}), {K::I64}));
    pin("x<y<z>>(a)", typed(call(0, {name(7)}), {namedArgument("y", {namedArgument("z")})}));
    pin("f<a<b<c>>>(0)",
        typed(call(0, {number(10)}), {namedArgument("a", {namedArgument("b", {namedArgument("c")})})}));
    pin("f<u64,u8>(1,2)", typed(call(0, {number(7), number(9)}), {K::U64, K::U8}));
    pin("ns::make<bool,64>(true)", typed(call(0, {tree("bool", 9)}, 2), {K::Bool, capacity(64)}));
    pin("f<Box<i64>>()", typed(call(0), {namedArgument("Box", {K::I64})}));
    pin("f<Pair<i64,u8>,Box<64>>(1)",
        typed(call(0, {number(14)}), {namedArgument("Pair", {K::I64, K::U8}), namedArgument("Box", {capacity(64)})}));
    pin("ns :: make<Pair<i64, u8>>(1)", typed(call(0, {number(11)}, 2), {namedArgument("Pair", {K::I64, K::U8})}));
    pin("f<ns::array<u8,16>>(value)", typed(call(0, {name(11)}), {namedArgument("ns::array", {K::U8, capacity(16)})}));
    pin("one::two::Box<Pair<u8,16>,Other>{.last=2,.first=1}",
        typed(construct(0, 4, {"last", "first"}, {number(19), number(24)}),
              {namedArgument("Pair", {K::U8, capacity(16)}), namedArgument("Other")}));
    pin("f<i64>(type_id(Pair<Box<u8>,i64>)).member[0]",
        index(member(
                  19,
                  typed(call(0, {reflected(5, namedType("Pair", {namedArgument("Box", {K::U8}), K::I64}))}), {K::I64})),
              number(21)));
    pin("{f<i64>(1),size_of(array<u8,4096>),Box<u64>{.value=2}}",
        array(0,
              {typed(call(1, {number(6)}), {K::I64}),
               reflected(9, T::array(K::U8, 4096)),
               typed(construct(19, 19, {"value"}, {number(27)}), {K::U64})}));
    pin("Box<i64>{.value=field_count(Other)}.value",
        member(14, typed(construct(0, 0, {"value"}, {reflected(8, T("Other"))}), {K::I64})));
    pin("size_of<i64>(u8)", typed(reflected(0, T::U8), {K::I64}));
    pin("type_id<8>(Box)", typed(reflected(0, T("Box")), {capacity(8)}));
    pin("f<a<b<c>>(0)", binary(1, name(0), typed(call(2, {number(9)}), {namedArgument("b", {namedArgument("c")})})));
    pin("{f<i64>(1),2}", array(0, {typed(call(1, {number(6)}), {K::I64}), number(9)}));
    pin("Box{.first=f<a<b<c>>>(0),.second={x<y<z>>(a)}}",
        construct(0,
                  0,
                  {"first", "second"},
                  {typed(call(5, {number(15)}), {namedArgument("a", {namedArgument("b", {namedArgument("c")})})}),
                   array(21, {typed(call(22, {name(29)}), {namedArgument("y", {namedArgument("z")})})})}));
    pin("f({Box<i64>{.value=1},2})",
        call(0, {array(2, {typed(construct(3, 3, {"value"}, {number(11)}), {K::I64}), number(14)})}));
    pin("{1,f<a<b<c>>(0)}",
        array(
            0,
            {number(1), binary(4, name(3), typed(call(5, {number(12)}), {namedArgument("b", {namedArgument("c")})}))}));
    const auto deep = namedArgument("A", {namedArgument("B", {namedArgument("C", {namedArgument("D", {K::I64})})})});
    pin("f<A<B<C<D<i64>>>>>()", typed(call(0), {deep}));
    pin("size_of(A<B<C<D<i64>>>>)", reflected(0, namedType("A", deep.templateArguments)));
    pin("A<B<C<D<E<i64>>>>>{}",
        typed(construct(0, 0),
              {namedArgument("B", {namedArgument("C", {namedArgument("D", {namedArgument("E", {K::I64})})})})}));
}

std::size_t tokenAt(const std::vector<aurora::Token> &tokens, const aurora::Token &token) {
    const auto found = std::lower_bound(
        tokens.begin(), tokens.end(), token.span.begin.offset, [](const auto &candidate, std::size_t offset) {
            return candidate.span.begin.offset < offset;
        });
    require(found != tokens.end(), "source root has no retained token");
    sameToken(*found, token);
    return static_cast<std::size_t>(found - tokens.begin());
}
void hostedRoot(const std::vector<aurora::Token> &tokens,
                std::size_t position,
                Stop stop,
                const aurora::ExpressionPtr &expected,
                const Context &typeContext = {}) {
    const auto expression = aurora::parseHostedExpression(tokens, position, stop, typeContext);
    require(bool(expression), "bootstrap dispatch omitted an expression");
    sameExpression(expression, expected);
    require(tokens.at(position).text == (stop == Stop::CloseParenthesis ? ")" : ";"),
            "bootstrap expression committed the wrong delimiter");
    ++cases;
}
void bootstrapStatements(const std::vector<aurora::Token> &tokens,
                         const std::vector<aurora::StatementPtr> &statements,
                         std::size_t &strings) {
    for (const auto &statement : statements) {
        if (statement->expr && statement->expr->op == "byte_string") {
            hostedRoot(tokens, tokenAt(tokens, statement->expr->token), Stop::Semicolon, statement->expr);
            ++strings;
        }
        bootstrapStatements(tokens, statement->body, strings);
        bootstrapStatements(tokens, statement->other, strings);
    }
}
void bootstrapFunctions(const std::vector<aurora::Token> &tokens,
                        const std::vector<aurora::Function> &functions,
                        std::size_t &initializers,
                        std::size_t &strings,
                        std::size_t &newInitializers) {
    for (const auto &function : functions) {
        for (const auto &[field, expression] : function.initializers) {
            const auto position = tokenAt(tokens, field) + 1;
            // These three compiler sources currently have no brace initializers.
            if (tokens.at(position).text == "{")
                continue;
            require(function.constructor && tokens.at(position).text == "(",
                    "constructor initializer has no parenthesized source root");
            hostedRoot(tokens, position + 1, Stop::CloseParenthesis, expression);
            if (field.text == "field_token" &&
                (function.token.text == "ParseFrame" || function.token.text == "ChildEdge"))
                ++newInitializers;
            else
                ++initializers;
        }
        bootstrapStatements(tokens, function.body, strings);
    }
}
std::size_t expectedStringRoots(const std::vector<aurora::StatementPtr> &statements) {
    std::size_t count = 0;
    for (const auto &statement : statements) {
        count += statement->expr && statement->expr->op == "byte_string";
        count += expectedStringRoots(statement->body) + expectedStringRoots(statement->other);
    }
    return count;
}
void expectedBootstrapRoots(const std::vector<aurora::Function> &functions,
                            std::size_t &initializers,
                            std::size_t &strings) {
    for (const auto &function : functions) {
        initializers += function.initializers.size();
        strings += expectedStringRoots(function.body);
    }
}
void bootstrapBodies(const std::vector<aurora::Token> &, const aurora::Program &, std::size_t);
void bootstrapSources(char **paths) {
    std::size_t initializers = 0, strings = 0, newInitializers = 0;
    std::size_t expectedInitializers = 0, expectedStrings = 0;
    const std::array<std::string, 3> modules{
        "aurora.compiler.lexer", "aurora.compiler.expression_arena", "aurora.compiler.expression_parser"};
    for (std::size_t i = 0; i < modules.size(); ++i) {
        context = paths[i];
        std::ifstream input(paths[i], std::ios::binary);
        require(bool(input), "cannot read actual bootstrap source");
        const std::string source((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
        require(!input.bad(), "cannot finish reading actual bootstrap source");
        const auto tokens = aurora::lex(source, paths[i]);
        const auto program = checkedProgram(tokens);
        require(program.moduleName == modules[i], "unexpected bootstrap source module/order");
        bootstrapBodies(tokens, program, i);
        expectedBootstrapRoots(program.functions, expectedInitializers, expectedStrings);
        expectedBootstrapRoots(program.functionTemplates, expectedInitializers, expectedStrings);
        for (const auto &definition : program.classes)
            expectedBootstrapRoots(definition.methods, expectedInitializers, expectedStrings);
        for (const auto &definition : program.templates)
            expectedBootstrapRoots(definition.methods, expectedInitializers, expectedStrings);
        bootstrapFunctions(tokens, program.functions, initializers, strings, newInitializers);
        bootstrapFunctions(tokens, program.functionTemplates, initializers, strings, newInitializers);
        for (const auto &definition : program.classes)
            bootstrapFunctions(tokens, definition.methods, initializers, strings, newInitializers);
        for (const auto &definition : program.templates)
            bootstrapFunctions(tokens, definition.methods, initializers, strings, newInitializers);
    }
    context = "actual bootstrap source roots";
    require(initializers + newInitializers == expectedInitializers && strings == expectedStrings &&
                expectedInitializers >= 42 && expectedStrings >= 5 && newInitializers == 2,
            "actual bootstrap roots were omitted or lost historical coverage: expected " +
                std::to_string(expectedInitializers) + " constructors and " + std::to_string(expectedStrings) +
                " strings, observed " + std::to_string(initializers + newInitializers) + " and " +
                std::to_string(strings));
}

std::size_t closingBrace(const std::vector<aurora::Token> &tokens, std::size_t opening) {
    require(tokens.at(opening).text == "{", "aggregate source root has no opening brace");
    std::size_t depth = 0;
    for (std::size_t index = opening; index < tokens.size(); ++index) {
        if (tokens[index].text == "{")
            ++depth;
        else if (tokens[index].text == "}" && --depth == 0)
            return index;
    }
    throw std::runtime_error(context + ": aggregate source root has no closing brace");
}
void hostedBraces(const std::vector<aurora::Token> &tokens,
                  const aurora::Token &field,
                  const aurora::ExpressionPtr &expected) {
    const auto start = tokenAt(tokens, field);
    const auto close = closingBrace(tokens, start + 1);
    auto position = start;
    const auto expression = aurora::parseHostedExpression(tokens, position, Stop::ConstructorBraces);
    require(bool(expression), "constructor-brace root silently fell back");
    sameExpression(expression, expected);
    sameToken(expression->token, field);
    require(position == close + 1, "constructor braces did not commit exactly through their closing token");
    require(expression->op == (expression->args.empty() ? "array_zero" : "array_literal"),
            "constructor braces lost their empty-array distinction");
    ++cases;
}
using AggregateRoots = std::vector<std::pair<std::string, std::size_t>>;
void consumerStatements(const std::vector<aurora::Token> &tokens,
                        const std::vector<aurora::StatementPtr> &statements,
                        AggregateRoots &aggregates) {
    for (const auto &statement : statements) {
        if (statement->expr && (statement->expr->op == "array_literal" || statement->expr->op == "construct")) {
            const auto &expression = statement->expr;
            const auto start = tokenAt(tokens, expression->token);
            const bool construct = expression->op == "construct";
            const auto close = closingBrace(tokens, start + (construct ? 1 : 0));
            auto position = start;
            const auto hosted = aurora::parseHostedExpression(tokens, position, Stop::Semicolon);
            require(bool(hosted), "actual consumer aggregate silently fell back");
            sameExpression(hosted, expression);
            require(position == close + 1 && tokens.at(position).text == ";",
                    "consumer aggregate lost its exact closing delimiter");
            if (construct)
                require(statement->name == "current" && expression->token.text == "Sample" &&
                            expression->fieldNames == std::vector<std::string>{"value", "ready"} &&
                            expression->args.size() == 2 && expression->args[0]->token.text == "40" &&
                            expression->args[1]->token.text == "false",
                        "class-values consumer lost its designated field order/values");
            aggregates.emplace_back(statement->name, expression->args.size());
            ++cases;
        }
        consumerStatements(tokens, statement->body, aggregates);
        consumerStatements(tokens, statement->other, aggregates);
    }
}
void consumerFunctions(const std::vector<aurora::Token> &tokens,
                       const std::vector<aurora::Function> &functions,
                       AggregateRoots &aggregates,
                       AggregateRoots &braces) {
    for (const auto &function : functions) {
        for (const auto &[field, expression] : function.initializers) {
            if (tokens.at(tokenAt(tokens, field) + 1).text != "{")
                continue;
            require(function.constructor, "brace initializer escaped its constructor");
            hostedBraces(tokens, field, expression);
            braces.emplace_back(field.text, expression->args.size());
            if (field.text == "records")
                for (const auto &child : expression->args)
                    require(child->op == "name" && child->token.text == "empty",
                            "session-file record initialization changed its source/order");
        }
        consumerStatements(tokens, function.body, aggregates);
    }
}
bool containsTypeQuery(const aurora::ExpressionPtr &expression) {
    if (!expression)
        return false;
    if (expression->op == "call" && (expression->token.text == "size_of" || expression->token.text == "type_id" ||
                                     expression->token.text == "field_count"))
        return true;
    return std::any_of(expression->args.begin(), expression->args.end(), containsTypeQuery);
}
void consumerReflection(const std::vector<aurora::Token> &tokens,
                        const std::vector<aurora::StatementPtr> &statements,
                        std::size_t &roots) {
    for (const auto &statement : statements) {
        if (containsTypeQuery(statement->expr)) {
            const bool assertion = statement->token.text == "static_assert";
            require(assertion || statement->token.text == "return", "unexpected reflection consumer statement");
            const auto start = tokenAt(tokens, statement->token) + (assertion ? 2 : 1);
            hostedRoot(tokens, start, assertion ? Stop::CloseParenthesis : Stop::Semicolon, statement->expr);
            ++roots;
            ++cases;
        }
        consumerReflection(tokens, statement->body, roots);
        consumerReflection(tokens, statement->other, roots);
    }
}
void consumerSources(char **paths) {
    const std::array<std::string, 5> modules{
        "std.array", "console.session_files", "kernel_graphical_console", "fs.xfs_sector", "examples.class_values"};
    const std::array<AggregateRoots, 5> expectedAggregates{
        AggregateRoots{},
        AggregateRoots{},
        AggregateRoots{{"text", 61}, {"text", 27}, {"text", 63}, {"text", 19}, {"blank", 1}, {"text", 22}},
        AggregateRoots{{"bytes", 512}},
        AggregateRoots{{"current", 2}}};
    const std::array<AggregateRoots, 5> expectedBraces{AggregateRoots{{"elements", 0}},
                                                       AggregateRoots{{"bytes", 0}, {"records", 4}},
                                                       AggregateRoots{{"bytes", 0}, {"desired", 0}, {"committed", 0}},
                                                       AggregateRoots{},
                                                       AggregateRoots{}};
    std::size_t roots = 0;
    for (std::size_t index = 0; index < modules.size(); ++index) {
        context = paths[index];
        std::ifstream input(paths[index], std::ios::binary);
        require(bool(input), "cannot read actual aggregate consumer source");
        const std::string source((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
        require(!input.bad(), "cannot finish reading actual aggregate consumer source");
        const auto tokens = aurora::lex(source, paths[index]);
        const auto program = checkedProgram(tokens);
        require(program.moduleName == modules[index], "unexpected aggregate consumer module/order");
        AggregateRoots aggregates, braces;
        consumerFunctions(tokens, program.functions, aggregates, braces);
        consumerFunctions(tokens, program.functionTemplates, aggregates, braces);
        for (const auto &definition : program.classes)
            consumerFunctions(tokens, definition.methods, aggregates, braces);
        for (const auto &definition : program.templates)
            consumerFunctions(tokens, definition.methods, aggregates, braces);
        require(aggregates == expectedAggregates[index] && braces == expectedBraces[index],
                "actual consumer aggregate roots changed shape/order or were omitted");
        roots += aggregates.size() + braces.size();
        if (index == 4) {
            std::size_t reflection = 0;
            for (const auto &function : program.functions)
                consumerReflection(tokens, function.body, reflection);
            require(reflection == 3, "expected all three retained class-values reflection roots");
        }
    }
    require(roots == 14, "expected all 14 actual product aggregate roots");
}

// Fixture-only declaration capture. Production Parser captures the same Tokens
// as ident() consumes the header; whole/direct comparisons check dispatch
// consistency only. Never replace these Tokens with spellings synthesized in another source.
Context fixtureContext(const std::vector<aurora::Token> &tokens,
                       const aurora::Token &declaration,
                       const std::vector<aurora::TemplateParameter> &parameters,
                       bool functionTemplate) {
    Context result;
    if (parameters.empty())
        return result;
    auto index = tokenAt(tokens, declaration);
    while (index > 0 && tokens[index].text != "template")
        --index;
    require(tokens[index].text == "template" && tokens.at(index + 1).text == "<",
            "typed fixture declaration lost its original template header");
    index += 2;
    for (std::size_t parameter = 0; parameter < parameters.size(); ++parameter) {
        const auto &expected = parameters[parameter];
        const std::string kind = expected.kind == aurora::TemplateParameterKind::Scalar  ? "Scalar"
                                 : expected.kind == aurora::TemplateParameterKind::Value ? "Value"
                                                                                         : "i64";
        require(tokens.at(index).text == kind && tokens.at(index + 1).text == expected.name,
                "captured template parameter spelling/order differs from declaration");
        auto &names = expected.kind == aurora::TemplateParameterKind::Capacity ? result.capacityParameters
                                                                               : result.typeParameters;
        names.push_back(tokens.at(index + 1));
        index += 2;
        require(tokens.at(index).text == (parameter + 1 == parameters.size() ? ">" : ","),
                "captured template header has an unexpected delimiter");
        ++index;
    }
    result.functionTemplate = functionTemplate;
    return result;
}
// This inventory is pinned to PR147's 18/56/51 pre-migration entries.
// Names are a multiset: all historical methods (including repeated accessors)
// must remain, and every new source auto entry must route through Body too.
// Whole/direct equality establishes dispatch consistency, not independence.
void bootstrapBodies(const std::vector<aurora::Token> &tokens, const aurora::Program &program, std::size_t module) {
    const std::array<std::multiset<std::string>, 3> historical{{
        {"at",
         "row",
         "start",
         "kind",
         "next_offset",
         "next_line",
         "next_line_start",
         "space",
         "letter",
         "digit",
         "word",
         "hex",
         "escape",
         "punctuation",
         "pair",
         "valid_byte",
         "valid_string",
         "next_lexeme"},
        {"state",
         "min",
         "lhs",
         "token",
         "designate",
         "field",
         "kind",
         "token",
         "first",
         "second",
         "depth",
         "locate",
         "last",
         "close",
         "child",
         "previous",
         "count",
         "depth",
         "field",
         "kind",
         "token",
         "last",
         "close",
         "first",
         "second",
         "owner",
         "role",
         "bind_owner",
         "store",
         "ok",
         "size",
         "capacity",
         "failure",
         "stack_size",
         "scratch_at",
         "replace_scratch",
         "truncate_stack",
         "types",
         "type_at",
         "append_type",
         "own_type",
         "frame",
         "pop",
         "replace",
         "push",
         "at",
         "append_at",
         "append",
         "append_name",
         "append_index",
         "arguments",
         "edge",
         "append_field",
         "append_argument",
         "append_list",
         "make_arena"},
        {"begin",
         "end",
         "mode",
         "status",
         "root",
         "size",
         "tokens",
         "offset",
         "update",
         "kind",
         "first",
         "last",
         "row",
         "start",
         "index",
         "half",
         "split",
         "status",
         "root",
         "token",
         "read_token",
         "advance",
         "single",
         "boolean_literal",
         "precedence",
         "stopped",
         "pair",
         "word_matches",
         "word_list_matches",
         "identifier_status",
         "type_query",
         "reserved_type_name",
         "builtin_type_name",
         "type_word",
         "parameter",
         "valid_context",
         "decimal_capacity",
         "type_close",
         "type_error",
         "parse_type",
         "prepare_templates",
         "failure",
         "parse",
         "create",
         "node_count",
         "read_node",
         "edge_count",
         "read_edge",
         "type_count",
         "read_type",
         "release"},
    }};
    auto remaining = historical.at(module);
    std::set<std::size_t> lexical, imported;
    for (std::size_t token = 0; token + 1 < tokens.size(); ++token)
        if (tokens[token].text == "auto")
            lexical.insert(token + 1);
    const auto functions = [&](const std::vector<aurora::Function> &items, const Context &classContext) {
        for (const auto &function : items) {
            if (function.constructor) {
                require(function.body.empty(), "bootstrap constructor acquired a nonempty body");
                continue;
            }
            const auto name = tokenAt(tokens, function.token);
            require(lexical.contains(name) && imported.insert(name).second,
                    "body inventory duplicated or synthesized a nonconstructor declaration");
            const auto found = remaining.find(function.token.text);
            if (found != remaining.end())
                remaining.erase(found);
            auto opening = name + 1;
            while (opening < tokens.size() && tokens[opening].text != "{")
                ++opening;
            require(opening < tokens.size(), "auto declaration lost its body opening");
            const auto expectedEnd = closingBrace(tokens, opening) + 1;
            const auto captured = function.templateParameters.empty()
                                      ? classContext
                                      : fixtureContext(tokens, function.token, function.templateParameters, true);
            auto position = opening;
            sameStatements(aurora::parseHostedBody(tokens, position, captured), function.body);
            require(position == expectedEnd, "actual body dispatch lost its exact closing brace");
            ++cases;
        }
    };
    functions(program.functions, {});
    functions(program.functionTemplates, {});
    for (const auto &definition : program.classes)
        functions(definition.methods, {});
    for (const auto &definition : program.templates)
        functions(definition.methods, fixtureContext(tokens, definition.token, definition.templateParameters, false));
    require(remaining.empty() && imported == lexical && imported.size() >= historical[module].size(),
            "actual bootstrap body inventory lost an old entry or omitted a new auto entry");
}
bool containsTypedSyntax(const aurora::ExpressionPtr &expression) {
    if (!expression)
        return false;
    return !expression->templateArguments.empty() || containsTypeQuery(expression) ||
           std::any_of(expression->args.begin(), expression->args.end(), containsTypedSyntax);
}
void typedNames(const aurora::ExpressionPtr &expression, std::vector<std::string> &names) {
    if (!expression)
        return;
    if (!expression->templateArguments.empty() ||
        (expression->op == "call" && (expression->token.text == "size_of" || expression->token.text == "type_id" ||
                                      expression->token.text == "field_count")))
        names.push_back(expression->token.text);
    for (const auto &child : expression->args)
        typedNames(child, names);
}
void typedStatements(const std::vector<aurora::Token> &tokens,
                     const std::vector<aurora::StatementPtr> &statements,
                     const Context &typeContext,
                     std::vector<std::string> &names) {
    for (const auto &statement : statements) {
        if (containsTypedSyntax(statement->expr)) {
            auto start = tokenAt(tokens, statement->token);
            Stop stop = Stop::Semicolon;
            if (statement->kind == "let") {
                const auto binding = std::lower_bound(tokens.begin(),
                                                      tokens.end(),
                                                      statement->bindingSpan.begin.offset,
                                                      [](const auto &token, std::size_t offset) {
                                                          return token.span.begin.offset < offset;
                                                      });
                require(binding != tokens.end() && binding->text == statement->name,
                        "typed declaration lost its binding token");
                sameSpan(binding->span, statement->bindingSpan);
                start = static_cast<std::size_t>(binding - tokens.begin()) + 1;
                require(tokens.at(start).text == "=", "typed declaration lost its initializer delimiter");
                ++start;
            } else if (statement->token.text == "return") {
                ++start;
            } else if (statement->token.text == "static_assert" || statement->token.text == "if" ||
                       statement->token.text == "while") {
                require(tokens.at(start + 1).text == "(", "typed condition lost its opening delimiter");
                start += 2;
                stop = Stop::CloseParenthesis;
            } else if (statement->kind == "assign" || statement->kind == "field_assign" ||
                       statement->kind == "index_assign") {
                const auto target = aurora::parseHostedExpression(tokens, start, Stop::Assignment, typeContext);
                require(bool(target) && tokens.at(start).text == "=", "typed assignment target fell back");
                if (statement->target)
                    sameExpression(target, statement->target);
                ++start;
            } else {
                require(statement->kind == "expression", "uncovered typed statement root");
            }
            hostedRoot(tokens, start, stop, statement->expr, typeContext);
            typedNames(statement->expr, names);
            if (statement->expr->token.text == "pair" && typeContext.functionTemplate) {
                require(typeContext.typeParameters.size() == 2 && statement->expr->templateArguments.size() == 2,
                        "dependent utility pair lost its captured two-parameter context");
                for (std::size_t index = 0; index < 2; ++index)
                    require(statement->expr->templateArguments[index].type == aurora::TypeKind::Parameter &&
                                statement->expr->templateArguments[index].className ==
                                    typeContext.typeParameters[index].text,
                            "dependent pair argument became a concrete class spelling");
            }
        }
        typedStatements(tokens, statement->body, typeContext, names);
        typedStatements(tokens, statement->other, typeContext, names);
    }
}
void typedFunctions(const std::vector<aurora::Token> &tokens,
                    const std::vector<aurora::Function> &functions,
                    const Context &classContext,
                    std::vector<std::string> &names) {
    for (const auto &function : functions) {
        const auto typeContext = function.templateParameters.empty()
                                     ? classContext
                                     : fixtureContext(tokens, function.token, function.templateParameters, true);
        for (const auto &[field, expression] : function.initializers) {
            if (!containsTypedSyntax(expression))
                continue;
            auto start = tokenAt(tokens, field);
            const bool braces = tokens.at(start + 1).text == "{";
            auto position = braces ? start : start + 2;
            const auto hosted = aurora::parseHostedExpression(
                tokens, position, braces ? Stop::ConstructorBraces : Stop::CloseParenthesis, typeContext);
            require(bool(hosted), "typed constructor initializer silently fell back");
            sameExpression(hosted, expression);
            require(braces ? position == closingBrace(tokens, start + 1) + 1 : tokens.at(position).text == ")",
                    "typed constructor initializer lost its closing delimiter");
            typedNames(expression, names);
            ++cases;
        }
        typedStatements(tokens, function.body, typeContext, names);
    }
}
std::vector<std::string> typedProgram(const std::vector<aurora::Token> &tokens) {
    const auto program = checkedProgram(tokens);
    std::vector<std::string> names;
    typedFunctions(tokens, program.functions, {}, names);
    typedFunctions(tokens, program.functionTemplates, {}, names);
    for (const auto &definition : program.classes)
        typedFunctions(tokens, definition.methods, {}, names);
    for (const auto &definition : program.templates)
        typedFunctions(tokens,
                       definition.methods,
                       fixtureContext(tokens, definition.token, definition.templateParameters, false),
                       names);
    return names;
}
void typedConsumerSources(char **paths) {
    const std::array<std::string, 7> modules{"std.utility",
                                             "std.decimal",
                                             "std.json",
                                             "package.graph",
                                             "function_token_values",
                                             "examples.class_values",
                                             "kernel"};
    const std::array<std::vector<std::string>, 7> expected{std::vector<std::string>{"pair"},
                                                           {"std::array"},
                                                           {"std::array", "std::array"},
                                                           {"std::array", "std::array", "std::array", "std::array"},
                                                           {"std::array", "std::make_pair", "size_of", "field_count"},
                                                           {"size_of", "field_count", "type_id"},
                                                           {"size_of"}};
    for (std::size_t index = 0; index < modules.size(); ++index) {
        context = paths[index];
        std::ifstream input(paths[index], std::ios::binary);
        require(bool(input), "cannot read actual typed consumer source");
        const std::string source((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
        require(!input.bad(), "cannot finish reading actual typed consumer source");
        const auto tokens = aurora::lex(source, paths[index]);
        aurora::Parser parser(tokens);
        require(parser.parse().moduleName == modules[index], "unexpected typed consumer source/module order");
        require(typedProgram(tokens) == expected[index], "typed consumer roots changed order or were omitted");
    }
}

class Allocations {
public:
    std::size_t allowed = std::numeric_limits<std::size_t>::max(), successful = 0, released = 0;
    static void *allocate(void *context, std::size_t bytes) noexcept {
        auto &state = *static_cast<Allocations *>(context);
        if (state.successful >= state.allowed)
            return nullptr;
        auto *result = std::malloc(bytes);
        if (result)
            ++state.successful;
        return result;
    }
    static void deallocate(void *context, void *address) noexcept {
        ++static_cast<Allocations *>(context)->released;
        std::free(address);
    }
    aurora::hosted::bytes::Allocator allocator() {
        return {this, allocate, deallocate};
    }
};
template <std::size_t N> class GuardedWords {
public:
    std::uint64_t before = canary;
    std::array<std::int64_t, N> value{};
    std::uint64_t after = canary;
    void check() const {
        require(before == canary && after == canary, "result write escaped its ABI extent");
    }
};
static_assert(sizeof(Words) == 40 && sizeof(GuardedWords<5>) == 56 && sizeof(GuardedWords<7>) == 72 &&
              sizeof(EdgeWords) == 40 && sizeof(TypeWords) == 64 && sizeof(GuardedWords<8>) == 80 &&
              sizeof(ContextWords) == 56 && sizeof(GuardedWords<18>) == 160 && sizeof(StatementWords) == 88 &&
              sizeof(GuardedWords<11>) == 104);
static_assert(sizeof(Words) == sizeof(aurora::hosted_abi::ParseResult) &&
              sizeof(NodeWords) == sizeof(aurora::hosted_abi::Node) &&
              sizeof(EdgeWords) == sizeof(aurora::hosted_abi::Edge) &&
              sizeof(TypeWords) == sizeof(aurora::hosted_abi::TypeSyntax) &&
              sizeof(StatementWords) == sizeof(aurora::hosted_abi::StatementSyntax) &&
              sizeof(std::array<std::int64_t, 18>) == sizeof(aurora::hosted_abi::ParserInput));
static_assert(sizeof(ContextWords) ==
              sizeof(aurora::hosted_abi::ParserInput) - offsetof(aurora::hosted_abi::ParserInput, type1Begin));
class RawArena {
    aurora::hosted::bytes::Region region;
    // This storage is never copied or inspected as an owner descriptor. Aurora
    // constructs and consumes it; the host only supplies region identity.
    std::uint64_t before = canary;
    aurora::hosted_abi::ParserRelease record;
    std::uint64_t after = canary;
    bool active = true;

public:
    explicit RawArena(Allocations &allocations, std::uint64_t quota = 1048576, std::int64_t initial = 0)
        : region(quota, allocations.allocator()) {
        record.region = region.id();
        aurora::hosted_abi::ParserCreate input;
        input.region = region.id();
        input.capacity = initial;
        checked_hosted_parser_create(&input, data());
        guards();
    }
    ~RawArena() {
        if (active)
            checked_hosted_parser_release(&record);
    }
    RawArena(const RawArena &) = delete;
    RawArena &operator=(const RawArena &) = delete;
    void *data() {
        return record.arena.data();
    }
    void guards() const {
        require(before == canary && after == canary, "arena write escaped its ABI extent");
    }
    Words parse(const std::string &source,
                Stop stop = Stop::Semicolon,
                std::int64_t offset = 0,
                ContextWords typeContext = {}) {
        GuardedWords<18> input;
        input.value = {0,
                       static_cast<std::int64_t>(reinterpret_cast<std::uintptr_t>(source.data())),
                       0,
                       0,
                       0,
                       0,
                       static_cast<std::int64_t>(source.size()),
                       offset,
                       1,
                       0,
                       static_cast<std::int64_t>(stop)};
        static_assert(sizeof(input.value) == 144);
        for (std::size_t index = 0; index < typeContext.size(); ++index)
            input.value[11 + index] = typeContext[index];
        const auto beforeInput = input.value;
        GuardedWords<5> output;
        checked_hosted_parser_parse(data(), input.value.data(), output.value.data());
        input.check();
        require(input.value == beforeInput, "parse changed its copied input/context record");
        output.check();
        guards();
        require(output.value[2] == checked_hosted_parser_count(data()),
                "reported arena count differs from real storage");
        if (stop != Stop::Body)
            require(statements() == 0, "expression profile acquired statement records");
        return output.value;
    }
    NodeWords read(std::int64_t index) {
        GuardedWords<7> output;
        checked_hosted_parser_read(data(), index, output.value.data());
        output.check();
        guards();
        return output.value;
    }
    std::int64_t edges() {
        return checked_hosted_parser_edges(data());
    }
    EdgeWords edge(std::int64_t index) {
        GuardedWords<5> output;
        checked_hosted_parser_edge(data(), index, output.value.data());
        output.check();
        guards();
        return output.value;
    }
    std::int64_t types() {
        const auto count = checked_hosted_parser_types(data());
        guards();
        return count;
    }
    TypeWords type(std::int64_t index) {
        GuardedWords<8> output;
        checked_hosted_parser_type(data(), index, output.value.data());
        output.check();
        guards();
        return output.value;
    }
    std::int64_t statements() {
        const auto count = checked_hosted_parser_statements(data());
        guards();
        return count;
    }
    StatementWords statement(std::int64_t index) {
        GuardedWords<11> output;
        checked_hosted_parser_statement(data(), index, output.value.data());
        output.check();
        guards();
        return output.value;
    }
    aurora::hosted::bytes::Metrics metrics() const {
        return region.metrics();
    }
    void finish() {
        checked_hosted_parser_release(&record);
        active = false;
        guards();
        const auto final = region.metrics();
        require(final.used == 0 && final.live_allocations == 0 && final.releases == final.successful_allocations,
                "Aurora cleanup leaked payload or ownership metadata");
        require(region.close(), "empty parser region did not close");
    }
};
void rawBodies() {
    static_assert(sizeof(StatementWords) == 88 && static_cast<std::int64_t>(Stop::Body) == 4);
    static_assert(wire(StatementKind::Block) == 1 && wire(StatementKind::Local) == 2 &&
                  wire(StatementKind::ReturnValue) == 3 && wire(StatementKind::StaticAssertion) == 4 &&
                  wire(StatementKind::Conditional) == 5 && wire(StatementKind::Loop) == 6 &&
                  wire(StatementKind::Expression) == 7 && wire(StatementKind::Assign) == 8 &&
                  wire(StatementKind::FieldAssign) == 9 && wire(StatementKind::IndexAssign) == 10);
    for (const bool empty : {false, true}) {
        const std::string source = empty ? "{} next" : "{i64 x=1;return x;} next";
        context = "raw complete body " + source;
        const auto tokens = aurora::lex(source);
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(source, Stop::Body);
        const std::int64_t end = empty ? 2 : 10;
        require(result == Words{wire(Status::Success),
                                empty ? 0 : 2,
                                empty ? 0 : 2,
                                end,
                                static_cast<std::int64_t>(tokens[end].span.begin.offset)} &&
                    arena.statements() == (empty ? 1 : 3),
                "body result/count/boundary ABI differs");
        if (empty) {
            require(arena.statement(0) == StatementWords{1, 0, 2, -1, -1, -1, -1, -1, -1, -1, 0} &&
                        arena.types() == 0 && arena.edges() == 0,
                    "empty root acquired phantom records");
        } else {
            require(arena.statement(0) == StatementWords{2, 1, 6, -1, 0, -1, 0, 2, -1, -1, 1} &&
                        arena.statement(1) == StatementWords{3, 6, 9, 0, 1, -1, -1, -1, -1, -1, 0} &&
                        arena.statement(2) == StatementWords{1, 0, 10, -1, -1, -1, -1, -1, 1, -1, 0},
                    "statement 88-byte fields/sibling order differ");
            require(arena.types() == 1 && arena.type(0) == TypeWords{1, 1, 1, 2, -1, -1, 1, 3} &&
                        arena.read(0) == NodeWords{1, 4, -1, -1, 1, 4, 4} &&
                        arena.read(1) == NodeWords{2, 7, -1, -1, 1, 7, 7},
                    "declaration role3 or expression forest ABI differs");
        }
        arena.finish();
        require(allocations.successful == allocations.released, "body owner cleanup differs");
        ++cases;
    }
    // Wide bodies grow independently of expression AST depth. Empty nested
    // blocks also force body frames/storage to grow with zero expression nodes.
    for (const bool nested : {false, true}) {
        constexpr std::int64_t width = 513;
        const auto source = nested ? std::string(128, '{') + std::string(128, '}') : "{" + std::string{};
        std::string text = source;
        if (!nested) {
            for (std::int64_t i = 0; i < width; ++i)
                text += "1;";
            text += "}";
        }
        context = nested ? "raw nested body growth" : "raw wide body growth";
        std::size_t successful = 0;
        {
            Allocations allocations;
            RawArena arena(allocations);
            const auto result = arena.parse(text, Stop::Body);
            require(result == Words{wire(Status::Success),
                                    nested ? 127 : width,
                                    nested ? 0 : width,
                                    nested ? 256 : 2 * width + 2,
                                    static_cast<std::int64_t>(text.size())} &&
                        arena.statements() == (nested ? 128 : width + 1),
                    "body growth result differs");
            if (nested) {
                for (std::int64_t i = 0; i < 128; ++i)
                    require(arena.statement(i) == StatementWords{1, 127 - i, 129 + i, -1, -1, -1, -1, -1, i - 1, -1, 0},
                            "nested block ABI differs");
            } else {
                for (std::int64_t i = 0; i < width; ++i) {
                    require(arena.statement(i) ==
                                StatementWords{7, 1 + 2 * i, 3 + 2 * i, i - 1, i, -1, -1, -1, -1, -1, 0},
                            "wide sibling order/end/root differs");
                    require(arena.read(i) == NodeWords{1, 1 + 2 * i, -1, -1, 1, 1 + 2 * i, 1 + 2 * i},
                            "wide body expression forest differs");
                }
                require(arena.statement(width) ==
                            StatementWords{1, 0, 2 * width + 2, -1, -1, -1, -1, -1, width - 1, -1, 0},
                        "wide root differs");
            }
            const auto metrics = arena.metrics();
            require(metrics.live_allocations == 5 && metrics.peak_live_allocations == 5 &&
                        metrics.successful_allocations > 10 && metrics.peak_used > 8 * 88,
                    "body did not grow its real fifth owner");
            successful = allocations.successful;
            arena.finish();
            require(allocations.released == successful, "body growth leaked an owner");
        }
        for (std::size_t allowed = 0; allowed < successful; ++allowed) {
            Allocations allocations;
            allocations.allowed = allowed;
            RawArena arena(allocations);
            const auto result = arena.parse(text, Stop::Body);
            require(result[0] == wire(Status::AllocationFailure) && result[1] == -1,
                    "body initial/growth failure did not fail closed");
            if (arena.statements() > 0)
                require(arena.statement(0) == (nested ? StatementWords{1, 127, 129, -1, -1, -1, -1, -1, -1, -1, 0}
                                                      : StatementWords{7, 1, 3, -1, 0, -1, -1, -1, -1, -1, 0}),
                        "body failed growth damaged a committed record");
            arena.finish();
            require(allocations.released == allocations.successful, "body failed growth leaked owner metadata");
            ++cases;
        }
        ++cases;
    }
}
void rawCase(const std::string &source, Status expected, Stop stop = Stop::Semicolon) {
    context = "raw ABI " + source;
    Allocations allocations;
    RawArena arena(allocations);
    const auto result = arena.parse(source, stop);
    require(result[0] == static_cast<std::int64_t>(expected), "raw status enum differs");
    arena.finish();
    require(allocations.released == allocations.successful, "host allocator did not observe exact cleanup");
    ++cases;
}
void byteStrings() {
    const std::array<std::string, 7> spellings{R"("")",
                                               R"("text")",
                                               R"("\'\\\0\a\b\f\n\r\t\v\"\x00\x7f\x80\xff")",
                                               R"("é😀")",
                                               R"("\0\x00\x7f\x80\xff")",
                                               "\"" + std::string(4095, 'a') + "\"",
                                               "\"" + std::string(4096, 'a') + "\""};
    for (const auto &spelling : spellings) {
        context = "raw byte string " + spelling;
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(spelling + ";");
        require(result == Words{wire(Status::Success), 0, 1, 1, static_cast<std::int64_t>(spelling.size())} &&
                    arena.read(0) == NodeWords{wire(NodeKind::Literal), 0, -1, -1, 1, 0, 0} && arena.edges() == 0,
                "byte string did not retain the exact single Literal node ABI/cursor");
        arena.finish();
        require(allocations.released == allocations.successful, "byte-string cleanup mismatch");
        ++cases;
        pin(spelling, tree("byte_string", 0));
        supported("// preceding trivia\r\n\t" + spelling + ";");
        supported(spelling + ")", Stop::CloseParenthesis);
        const auto source = "module strings; class Text { array<u8,512> bytes; public: Text():bytes(" + spelling +
                            "){} auto first() const->u8 {return bytes[0];} }; "
                            "auto f()->i64 {const array<u8,4096> bytes=" +
                            spelling + ";return 0;}";
        const auto tokens = aurora::lex(source, "string-program.au");
        const auto program = checkedProgram(tokens);
        require(program.classes.size() == 1 && program.classes[0].methods.size() == 2 && program.functions.size() == 1,
                "byte-string declaration inventory differs");
        sameExpression(program.classes[0].methods[0].initializers.at(0).second,
                       expectedTree(tokens, tree("byte_string", 22)));
        sameExpression(program.classes[0].methods[1].body.at(0)->expr,
                       expectedTree(tokens, index(name(35), number(37))));
        sameExpression(program.functions[0].body.at(0)->expr, expectedTree(tokens, tree("byte_string", 59)));
        sameExpression(program.functions[0].body.at(1)->expr, expectedTree(tokens, number(62)));
    }
    for (const auto &expression : {R"(f("text");)",
                                   R"(ns::f("", "é😀", "\0\xff");)",
                                   R"(object.write("\"\\\n");)",
                                   R"("left" == "right";)",
                                   R"(("text")[0];)"})
        supported(expression);
}
void constructors() {
    const std::string prefix = "export module constructors; class Box { i64 value; public: Box(i64 x):value(";
    const std::string suffix = "){} auto read() const->i64 {return value;} };";
    for (const auto &expression : {"1",
                                   "x",
                                   "(x + 1) * 2",
                                   "-x + ns::value",
                                   "ns::Mode::ready",
                                   "f()",
                                   "ns::make(x, a[2]).field",
                                   "object.at(index + 1)",
                                   R"(f("a\0\xff", a[one::index(f(1))]))",
                                   "true < x > (y)"}) {
        supported(std::string(expression) + ")", Stop::CloseParenthesis);
        checkedRootProgram(prefix, expression, suffix, true);
    }
    checkedProgram("export module constructors; namespace ns { class Pair { i64 first; i64 second; public: "
                   "Pair(i64 x):second // initializer order and field-token trivia\n (ns::value),\n"
                   "first(f(\"text\", a[x + 1])){} auto get() const->i64 {return first + second;} }; }",
                   {name(26, 28),
                    call(33, {tree("byte_string", 35), index(name(37), binary(40, name(39), number(41)))}),
                    binary(57, name(56), name(58))});
    checkedProgram("export module constructors; template<Scalar T> class Box { T value; public: "
                   "Box(T x):value(x){} auto read() const->T {return value;} };",
                   {name(25), name(38)});
    // Reflection and template roots must reach Aurora, including within an
    // otherwise ordinary call or parenthesized constructor initializer.
    for (const auto &expression : {"size_of(i64)", "type_id(array<u8,2>)", "field_count(Box)", "f(size_of(i64))"}) {
        supported(std::string(expression) + ")", Stop::CloseParenthesis);
        rawCase(std::string(expression) + ")", Status::Success, Stop::CloseParenthesis);
        checkedRootProgram(prefix, expression, suffix, true);
    }
    for (const auto &expression : {"f<i64>(1)", "x<y<z>>(a)", "f<a<b<c>>>(0)"})
        checkedRootProgram(prefix, expression, suffix, true);
    checkedBracedProgram(
        "export module constructors; class Box { array<i64,2> values; public: Box():values", "{1,2}", "{} };");
    checkedBracedProgram(
        "export module constructors; class Box { array<i64,2> values; public: Box():values", "{}", "{} };");
    for (const auto &expression : {"",
                                   "1 +",
                                   "(1 + 2",
                                   "1 2",
                                   "f(1,)",
                                   "f(,)",
                                   "a[]",
                                   "a[1",
                                   "a.",
                                   "name::",
                                   R"("text"(1))",
                                   R"("text"[0])",
                                   "f<T)>(0)"})
        rejectedProgram(prefix, expression, suffix);
    rejectedProgram(
        "export module constructors; class Box { i64 value; public: Box():value(", "1", " {} };", {"expected ')'", 1});
    rejectedProgram("export module constructors; class Box { i64 value; public: Box():value(1),",
                    "",
                    "{} };",
                    {"expected identifier", 0});
}
void constructorBraces(const std::string &contents) {
    const std::string source = "export module braces; class Box { array<i64,4> value; array<i64,4> other; public: "
                               "Box():value" +
                               contents + ",other{}{} };";
    context = source;
    const auto tokens = aurora::lex(source, "constructor-braces.au");
    const auto program = checkedProgram(tokens);
    require(program.classes.size() == 1 && program.classes[0].methods.size() == 1,
            "constructor-brace fixture lost its class/method");
    const auto &initializers = program.classes[0].methods[0].initializers;
    require(initializers.size() == 2 && initializers[0].first.text == "value" && initializers[1].first.text == "other",
            "constructor-brace field order differs");
    auto expected = shifted(pinned(contents), 1);
    expected.first = expected.last = 0;
    if (expected.args.empty())
        expected.op = "array_zero";
    sameExpression(initializers[0].second,
                   expectedTree(tokens, shifted(expected, tokenAt(tokens, initializers[0].first))));
    sameExpression(initializers[1].second,
                   expectedTree(tokens, tree("array_zero", tokenAt(tokens, initializers[1].first))));
    for (const auto &[field, expression] : initializers)
        hostedBraces(tokens, field, expression);
}
void aggregateSyntax() {
    for (const auto &expression : {"{};",
                                   "{1};",
                                   "{1,2,3};",
                                   "{{}, {1, {2}}, f(3, {4,5})};",
                                   "{1,2}[0];",
                                   "({1,2}).field;",
                                   "{}.size();",
                                   "ns::Box{};",
                                   "one // qualified trivia\n :: two::Box{.last=3,.first=1,.middle=2};",
                                   "Box{.first=f(1,{2}),.last=Other{.items={3,4}}};",
                                   "Box{.value=1}.value;",
                                   "Box{.items={1,2}}.items[0];",
                                   "Box{.items={1,2}}.at({3,4}[0]);",
                                   "f({}, Box{.value=1}, {f(2),object.at(3)});",
                                   "f(\"text\", Box{.value=1});",
                                   "{true < x > (y), a < b >> (c)};",
                                   "{1,f<T}>(0);",
                                   "Box{.first=true < x > (y),.last=a < b >> (c)};",
                                   "{Box{}, ns::array{}, object.size_of()};"}) {
        supported(expression);
        checkedRootProgram("module aggregates; auto f()->i64{return ", expression, "}");
    }
    supported("{1,2}[0] = 3;", Stop::Assignment);
    supported("Box{.value={1,2}[0]})", Stop::CloseParenthesis);
    for (const auto &contents : {"{}",
                                 "{1,2}",
                                 "{{1,2},{3,4}}",
                                 "{f(), object.at(2), a[0]}",
                                 "{Box{.value=1}, ns::Box{}, {}}",
                                 "{true < x > (y), a < b >> (c)}"})
        constructorBraces(contents);
    const auto grouped = std::string(127, '(') + "1" + std::string(127, ')');
    // The constructor list adds AST depth but does not consume a primary level.
    pin("{" + grouped + "}", tree("array_literal", 0, {number(128)}));
    constructorBraces("{" + grouped + "}");
    rejectedProgram("module depth; auto f()->i64{return ",
                    "{" + grouped + "};",
                    "}",
                    {"expression parser nesting exceeds 128", 128, 0, aurora::DiagnosticCode::NestingLimit});
    const auto nested = std::string(127, '{') + "1" + std::string(127, '}');
    auto nestedTree = number(127);
    for (std::size_t token = 127; token-- > 0;)
        nestedTree = tree("array_literal", token, {nestedTree});
    pin(nested, nestedTree);
    supported(nested + ";");
    rejectedProgram("module depth; auto f()->i64{return ",
                    "{" + nested + "};",
                    "}",
                    {"expression parser nesting exceeds 128", 128, 0, aurora::DiagnosticCode::NestingLimit});
    pin("{" + chain(127) + "}", tree("array_literal", 0, {sum(127, 1)}));
    constructorBraces("{" + chain(127) + "}");
    rejectedProgram("export module depth; class Box { array<i64,1> value; public: Box():value{",
                    chain(128),
                    "}{} };",
                    {"expression AST depth exceeds 128", 255});
    // Reflected types must survive arrays, designators and constructor lists.
    for (const auto &expression : {"{1,size_of(i64)};",
                                   "Box{.first=1,.second=type_id(array<u8,2>)};",
                                   "f({1,field_count(Box)});",
                                   "{Box{.value=f(size_of(i64))}};"}) {
        supported(expression);
        rawCase(expression, Status::Success);
    }
    for (const auto &contents : {"{1,size_of(i64)}", "{Box{.value=type_id(array<u8,2>)}}"}) {
        const std::string text = std::string("value") + contents;
        rawCase(text, Status::Success, Stop::ConstructorBraces);
        constructorBraces(contents);
    }

    // Aurora candidate selection must agree at malformed boundaries and
    // preserve arithmetic shifts.
    for (const auto &expression : {"{f<i64>(1),2}",
                                   "Box{.first=f<a<b<c>>>(0),.second={x<y<z>>(a)}}",
                                   "f({Box<i64>{.value=1},2})",
                                   "{1,f<a<b<c>>(0)}"}) {
        checkedRootProgram("module templates; auto f()->i64{return ", expression, ";}");
        pin("{" + std::string(expression) + "}", tree("array_literal", 0, {shifted(pinned(expression), 1)}));
        checkedBracedProgram("export module templates; class Box { array<i64,2> value; public: Box():value",
                             "{" + std::string(expression) + "}",
                             "{} };");
    }
    for (const auto &expression : {"{f<T)>(0)}", "{f<T]>(0)}", "{f<T:>(0)}", "Box{.value=f<T)>(0)}", "f({f<T]>(0)})"}) {
        rejectedProgram("module templates; auto f()->i64{return ", expression, ";}");
        rejectedProgram(
            "export module templates; class Box { array<i64,2> value; public: Box():value{", expression, "}{} };");
    }
    for (const auto &expression : {"{,};",
                                   "{1,};",
                                   "{1 2};",
                                   "{1;",
                                   "{1,2",
                                   "{1];",
                                   "{1)};",
                                   "Box{value=1};",
                                   "Box{..value=1};",
                                   "Box{.1=1};",
                                   "Box{.true=1};",
                                   "Box{.array=1};",
                                   "Box{.builtin=1};",
                                   "Box{.__au_private=1};",
                                   "Box{.value 1};",
                                   "Box{.value==1};",
                                   "Box{.value=};",
                                   "Box{.value=1,};",
                                   "Box{.value=1;",
                                   "Box{.value=1 .other=2};",
                                   "Box{.value={1,}};",
                                   "{}(1);",
                                   "Box{}(1);"})
        rejectedProgram("module errors; auto f()->i64{return ", expression, "}");
    for (const auto &contents : {"{,}", "{1,}", "{1 2}", "{1", "{1]}", "{Box{.value=1,}}"})
        rejectedProgram("export module errors; class Box { array<i64,2> value; public: Box():value", contents, "{} };");
}
void typedSyntax() {
    for (const auto &expression : {"f<i64>();",
                                   "f<u64,u8>(1,2);",
                                   "ns::make<bool,64>(true);",
                                   "f<Box<i64>>();",
                                   "f<Pair<i64,u8>,Box<64>>(1);",
                                   "ns // callee trivia\n :: make<Pair<i64, // argument trivia\n u8>>(1);",
                                   "f<ns::array<u8,16>>(value);",
                                   "one::two::Box<Pair<u8,16>,Other>{.last=2,.first=1};",
                                   "f<i64>(type_id(Pair<Box<u8>,i64>)).member[0];",
                                   "{f<i64>(1),size_of(array<u8,4096>),Box<u64>{.value=2}};",
                                   "Box<i64>{.value=field_count(Other)}.value;",
                                   "size_of<i64>(u8);",
                                   "type_id<8>(Box);",
                                   "a < b >> (c);",
                                   "(a) < b > (c);",
                                   "true < x > (y);",
                                   "f<a<b<c>>(0);",
                                   "{1,f<T}>(0);"}) {
        supported(expression);
        checkedRootProgram("module typed; auto f()->i64{return ", expression, "}");
    }
    using K = aurora::TypeKind;
    using T = aurora::Type;
    const auto sample = T("__au_console_sample"), event = T("__au_iommu_event_sample");
    const auto capacity = aurora::TemplateArgument::capacity;
    for (const auto &[type, expected] : std::vector<std::pair<std::string, T>>{
             {"i64", T::I64},
             {"u64", T::U64},
             {"u8", T::U8},
             {"bool", T::Bool},
             {"own<i64>", T::Own},
             {"ref<i64>", T::Ref},
             {"mutref<i64>", T::MutRef},
             {"Name", T("Name")},
             {"ns::Name", T("ns::Name")},
             {"Pair<i64,u8>", namedType("Pair", {K::I64, K::U8})},
             {"Box<Pair<u8,64>>", namedType("Box", {namedArgument("Pair", {K::U8, capacity(64)})})},
             {"array<u8,1>", T::array(K::U8, 1)},
             {"array<i64,4096>", T::array(K::I64, 4096)},
             {"array<ns::Value,64>", T::array(T("ns::Value"), 64)},
             {"array<Box<i64>,2>", T::array(namedType("Box", {K::I64}), 2)},
             {"builtin::array<bool,3>", T::array(K::Bool, 3)},
             {"builtin::span<const u8>", T::ByteSpan},
             {"builtin::OwnedValues<ns::Value>", T::ownedValues(T("ns::Value"))},
             {"array<builtin::ConsoleSample,2>", T::array(sample, 2)},
             {"array<builtin::IommuEventSample,64>", T::array(event, 64)},
             {"builtin::OwnedValues<builtin::IommuEventSample>", T::ownedValues(event)},
             {"builtin::OwnedValues<builtin::ConsoleSample>", T::ownedValues(sample)},
             {"builtin::ByteRegion", T::ByteRegion},
             {"builtin::OwnedBytes", T::OwnedBytes},
             {"builtin::ConsoleSession", T::ConsoleSession},
             {"builtin::ConsoleSample", sample},
             {"builtin::ConsolePutResult", T::enumeration("__au_console_put_result")},
             {"builtin::ConsoleCompletion", T::enumeration("__au_console_completion")},
             {"builtin::DisplaySession", T::DisplaySession},
             {"builtin::DisplayPutResult", T::enumeration("__au_display_put_result")},
             {"builtin::DisplayCompletion", T::enumeration("__au_display_completion")},
             {"builtin::IommuEventSession", T::IommuEventSession},
             {"builtin::IommuEventSample", event},
             {"builtin::EventPollResult", T::enumeration("__au_event_poll_result")},
             {"builtin::EventAckResult", T::enumeration("__au_event_ack_result")},
             {"builtin::EventIntakeCompletion", T::enumeration("__au_event_intake_completion")}})
        for (const auto &query : {"size_of", "type_id", "field_count"}) {
            const auto source = std::string(query) + "(" + type + ")";
            pin(source, reflected(0, expected));
            supported(source + ";");
        }
    for (const auto &expression : {"f<T)>(0);",
                                   "f<T]>(0);",
                                   "f<T:>(0);",
                                   "f<>(0);",
                                   "f<i64,>(0);",
                                   "(f<T)>(0);",
                                   "{f<T)>(0)};",
                                   "Box{.value=f<T)>(0)};",
                                   "f< T // malformed trivia\n ) >(0);",
                                   "f<i64,u8,bool>(0);",
                                   "f<0>(0);",
                                   "f<65>(0);",
                                   "f<1u64>(0);",
                                   "f<18446744073709551616>(0);",
                                   "f<true>(0);",
                                   "f<false>(0);",
                                   "f<own>(0);",
                                   "f<ref>(0);",
                                   "f<mutref>(0);",
                                   "f<array>(0);",
                                   "f<builtin>(0);",
                                   "f<fn>(0);",
                                   "f<ns::true>(0);",
                                   "f<__au_private>(0);",
                                   "size_of();",
                                   "size_of(fn);",
                                   "size_of(123);",
                                   "size_of(i64,u8);",
                                   "size_of(own);",
                                   "size_of(own<u8>);",
                                   "size_of(ref<i64>>);",
                                   "size_of(mutref<i64);",
                                   "size_of(builtin);",
                                   "size_of(builtin::unknown);",
                                   "size_of(builtin::span<u8>);",
                                   "size_of(builtin::span<const i64>);",
                                   "size_of(builtin::span<const u8>>);",
                                   "size_of(array<i64>);",
                                   "size_of(array<own<i64>,1>);",
                                   "size_of(array<array<i64,1>,1>);",
                                   "size_of(array<i64,0>);",
                                   "size_of(array<i64,4097>);",
                                   "size_of(array<i64,1u64>);",
                                   "size_of(array<i64,N>);",
                                   "size_of(array<Class,65>);",
                                   "size_of(builtin::OwnedValues<i64>);",
                                   "size_of(builtin::OwnedValues<Box<i64>>);",
                                   "size_of(Box<i64,u8,bool>);",
                                   "size_of(Box<i64,>);",
                                   "size_of(Box<0>);",
                                   "size_of(array<builtin::ConsolePutResult,2>);",
                                   "size_of(array<builtin::DisplayCompletion,2>);",
                                   "size_of(builtin::OwnedValues<builtin::EventPollResult>);"}) {
        rejected(expression);
        rejectedProgram("module typed_errors; auto f()->i64{return ", expression, "}");
    }
    // The second byte of >> is the diagnostic token after a literal > consumer
    // or after a completed reflected type. Source snapshots remain unsplit.
    for (const auto &expression :
         {"size_of(Box<i64>>);", "size_of(array<i64,2>>);", "size_of(builtin::OwnedValues<Value>>);"})
        rejected(expression);
    supported("f<A<B<C<D<i64>>>>>();");
    supported("size_of(A<B<C<D<i64>>>>);");
    supported("A<B<C<D<E<i64>>>>>{};");
    rejected("f<A<B<C<D<E<i64>>>>>>();");
    rejected("size_of(A<B<C<D<E<i64>>>>>);");
    // Invalid recursive arrays still exercise entry to type level 64 before
    // element validation; entering level 65 must win with the nesting diagnostic.
    for (const std::size_t depth : {63, 64}) {
        std::string type = "i64";
        for (std::size_t index = 0; index < depth; ++index)
            type = "array<" + type + ",1>";
        const auto source = "size_of(" + type + ");";
        pinError(source,
                 depth == 63 ? "array elements require i64, u64, u8, bool or a concrete copied class"
                             : "type nesting exceeds 64",
                 depth == 63 ? 132 : 130,
                 0,
                 depth == 63 ? aurora::DiagnosticCode::UnexpectedToken : aurora::DiagnosticCode::NestingLimit);
        rejected(source);
        rawCase(source, depth == 63 ? Status::ArrayElement : Status::TypeNestingLimit);
    }
    auto parameter = T(K::Parameter);
    parameter.className = "T";
    auto otherParameter = T(K::Parameter);
    otherParameter.className = "U";
    auto typeArgument = namedArgument("T"), otherTypeArgument = namedArgument("U");
    typeArgument.type = otherTypeArgument.type = K::Parameter;
    auto dependentArray = T::array(parameter, 0);
    dependentArray.lengthParameter = "N";
    const std::array<std::vector<Ast>, 4> contextRoots{
        {{typed(call(33, {name(40), name(42)}), {typeArgument, otherTypeArgument}),
          binary(50, reflected(46, parameter), reflected(51, otherParameter))},
         {tree("array_literal", 29, {reflected(31, parameter)}), reflected(46, dependentArray)},
         {reflected(23, parameter), reflected(38, parameter)},
         {reflected(20, parameter),
          typed(call(27, {name(32)}), {typeArgument}),
          reflected(38, parameter),
          typed(call(46, {name(51)}), {typeArgument}),
          binary(61, reflected(57, parameter), number(62)),
          number(66)}}};
    std::size_t acceptedContext = 0;
    for (const auto &source :
         {"export module context; template<Value T,Value U> auto f(T x,U y)->i64 {"
          "const Pair<T,U> p=Pair<T,U>(x,y); return size_of(T)+type_id(U);}",
          "export module context; template<Scalar T,i64 N> class C { array<T,N> data; public: "
          "C():data{size_of(T)}{} auto f()->i64{return size_of(array<T,N>);} };",
          "export module context; template<Value T> class C { i64 value; public: "
          "C():value(size_of(T)){} auto f()->i64{return field_count(T);} };",
          "export module context; template<Value T> auto f(T x)->i64 { if(type_id(T)){return g<T>(x);} "
          "while(size_of(T)){x=g<T>(x);} static_assert(size_of(T)>0); return 0;}"}) {
        context = source;
        checkedProgram(source, contextRoots.at(acceptedContext++));
        require(!typedProgram(aurora::lex(source, "typed-context.au")).empty(), "typed context roots were omitted");
    }
    const std::array<ExpectedError, 5> contextErrors{
        {{"template-id references inside template definitions are not supported", 23},
         {"template-id references inside template definitions are not supported", 25},
         {"nested dependent template arguments are not supported", 24},
         {"nested dependent template arguments are not supported", 22},
         {"owned values require a named concrete copied class", 26}}};
    std::size_t rejection = 0;
    for (const auto &source :
         {"export module context; template<Value T> class C { public: auto f()->i64{return g<T>();} };",
          "export module context; template<Value T> class C { public: auto f()->i64{return size_of(Box<i64>);} };",
          "export module context; template<Value T> auto f(T x)->i64{return g<Box<T>>(x);}",
          "export module context; template<Value T> auto f(T x)->i64{return g<T<i64>>(x);}",
          "export module context; template<Value T> auto f(T x)->i64{return size_of(builtin::OwnedValues<T>);}"})
        rejectedProgram("", source, "", contextErrors.at(rejection++));
}
void rawTypeRecords() {
    struct Fixture {
        std::string source;
        std::vector<TypeWords> types;
    };
    // Numeric kind words are independent wire expectations, not casts from the
    // adapter enum. These exact records also pin both halves of a shared >>.
    for (const auto &fixture : std::vector<Fixture>{
             {"size_of(i64);", {{1, 2, 2, 4, -1, -1, 0, 2}}},
             {"size_of(u64);", {{2, 2, 2, 4, -1, -1, 0, 2}}},
             {"size_of(u8);", {{3, 2, 2, 4, -1, -1, 0, 2}}},
             {"size_of(bool);", {{4, 2, 2, 4, -1, -1, 0, 2}}},
             {"size_of(ns::Name);", {{5, 2, 4, 8, -1, -1, 0, 2}}},
             {"size_of(own<i64>);", {{10, 2, 2, 10, -1, -1, 0, 2}}},
             {"size_of(ref<i64>);", {{11, 2, 2, 10, -1, -1, 0, 2}}},
             {"size_of(mutref<i64>);", {{12, 2, 2, 10, -1, -1, 0, 2}}},
             {"size_of(builtin::span<const u8>);", {{13, 2, 4, 16, -1, -1, 0, 2}}},
             {"size_of(builtin::ByteRegion);", {{14, 2, 4, 8, -1, -1, 0, 2}}},
             {"size_of(builtin::ConsoleSample);", {{16, 2, 4, 8, -1, -1, 0, 2}}},
             {"size_of(array<builtin::ConsoleSample,2>);",
              {{16, 4, 6, 12, -1, -1, -1, 0}, {7, 8, 8, 16, -1, -1, -1, 0}, {9, 2, 2, 18, 0, 1, 0, 2}}},
             {"size_of(builtin::OwnedValues<builtin::IommuEventSample>);",
              {{16, 6, 8, 16, -1, -1, -1, 0}, {15, 2, 4, 18, 0, -1, 0, 2}}},
             {"size_of(builtin::OwnedValues<Value>);", {{5, 6, 6, 12, -1, -1, -1, 0}, {15, 2, 4, 14, 0, -1, 0, 2}}},
             {"size_of<i64>(u8);",
              {{1, 2, 2, 4, -1, -1, -1, 0}, {5, 0, 0, 6, 0, -1, 0, 1}, {3, 5, 5, 10, -1, -1, 0, 2}}},
             {"f<i64>();", {{1, 2, 2, 4, -1, -1, -1, 0}, {5, 0, 0, 6, 0, -1, 0, 1}}},
             {"f<Box<i64>>();", {{1, 4, 4, 8, -1, -1, -1, 0}, {5, 2, 2, 10, 0, -1, -1, 0}, {5, 0, 0, 11, 1, -1, 0, 1}}},
             {"size_of(array<u8, 4>);",
              {{3, 4, 4, 8, -1, -1, -1, 0}, {7, 6, 6, 12, -1, -1, -1, 0}, {9, 2, 2, 14, 0, 1, 0, 2}}},
             {"Box<i64>{.value=1};", {{1, 2, 2, 4, -1, -1, -1, 0}, {5, 0, 0, 6, 0, -1, 0, 1}}},
             {"size_of(Box<Pair<i64, u8>>);",
              {{1, 6, 6, 12, -1, -1, -1, 0},
               {3, 8, 8, 16, -1, -1, -1, 0},
               {5, 4, 4, 18, 0, 1, -1, 0},
               {5, 2, 2, 19, 2, -1, 0, 2}}}}) {
        context = "independent TypeSyntax ABI " + fixture.source;
        Allocations allocations;
        RawArena arena(allocations);
        const auto tokens = aurora::lex(fixture.source, "type-abi.au");
        const auto result = arena.parse(fixture.source);
        require(result[0] == wire(Status::Success) && result[1] >= 0 &&
                    result[3] == static_cast<std::int64_t>(tokens.size() - 2) &&
                    result[4] == static_cast<std::int64_t>(fixture.source.size() - 1) &&
                    arena.types() == static_cast<std::int64_t>(fixture.types.size()),
                "typed raw result/count/cursor differs");
        for (std::size_t index = 0; index < fixture.types.size(); ++index)
            require(arena.type(static_cast<std::int64_t>(index)) == fixture.types[index],
                    "TypeSyntax layout/topology/owner/half differs at " + std::to_string(index));
        arena.finish();
        require(allocations.successful == allocations.released, "typed ABI leaked an owner");
        ++cases;
    }
    // Context words are absolute source ranges, while type records use token
    // ordinals relative to the expression cursor. Capture both named slots and
    // the capacity slot independently of the host Context serializer.
    for (const bool function : {false, true}) {
        const std::string source = function ? "T U size_of(T)+type_id(U);" : "T N size_of(array<T, N>);";
        context = "independent copied TypeContext " + source;
        const ContextWords typeContext =
            function ? ContextWords{0, 1, 2, 3, 0, 0, 2} : ContextWords{0, 1, 0, 0, 2, 3, 1};
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(source, Stop::Semicolon, 4, typeContext);
        require(result[0] == wire(Status::Success), "raw copied context was not consumed");
        if (function) {
            require(arena.types() == 2 && arena.type(0) == TypeWords{6, 2, 2, 4, -1, -1, 0, 2} &&
                        arena.type(1) == TypeWords{6, 7, 7, 14, -1, -1, 5, 2},
                    "two captured type slots lost parameter identity/owner");
        } else {
            require(arena.types() == 3 && arena.type(0) == TypeWords{6, 4, 4, 8, -1, -1, -1, 0} &&
                        arena.type(1) == TypeWords{8, 6, 6, 12, -1, -1, -1, 0} &&
                        arena.type(2) == TypeWords{9, 2, 2, 14, 0, 1, 0, 2},
                    "class/capacity context lost independent parameter roles");
        }
        arena.finish();
        require(allocations.successful == allocations.released, "context ABI leaked an owner");
        ++cases;
    }
}
void rawTypeDiagnostics() {
    struct Rejection {
        std::string source;
        Status status;
        std::size_t token;
        int half = 0;
    };
    const std::vector<Rejection> tests{{"size_of(array);", Status::ExpectedAngleOpen, 3},
                                       {"size_of(own<i64);", Status::ExpectedAngleClose, 5},
                                       {"size_of(builtin);", Status::ExpectedScope, 3},
                                       {"size_of(array<i64>);", Status::ExpectedComma, 5},
                                       {"size_of(builtin::span<u8>);", Status::ExpectedConst, 6},
                                       {"size_of(builtin::span<const i64>);", Status::ExpectedU8, 7},
                                       {"size_of(own<u8>);", Status::ExpectedI64, 4},
                                       {"size_of(builtin::unknown);", Status::ExpectedArray, 4},
                                       {"size_of(fn);", Status::ReservedType, 2},
                                       {"size_of(123);", Status::ExpectedType, 3},
                                       {"size_of(A<B<C<D<E<i64>>>>>);", Status::TemplateNestingLimit, 11},
                                       {"f<A<B<C<D<E<i64>>>>>>();", Status::CallTemplateNestingLimit, 11},
                                       {"f<i64, u8, bool>();", Status::TemplateArity, 6},
                                       {"f<own>();", Status::TemplateArgument, 2},
                                       {"f<65>();", Status::CapacityArgument, 3},
                                       {"size_of(builtin::OwnedValues<i64>);", Status::OwnedElement, 7},
                                       {"size_of(array<own<i64>, 1>);", Status::ArrayElement, 8},
                                       {"size_of(array<i64, 4097>);", Status::ArrayLength, 7},
                                       {"size_of(array<Class, 65>);", Status::ClassArrayLength, 8},
                                       {"size_of(Box<i64>>);", Status::ExpectedClose, 5, 1},
                                       {"size_of(array<i64, 2>>);", Status::ExpectedClose, 7, 1}};
    for (const auto &[source, expected, token, half] : tests) {
        context = "raw typed status/token/offset " + source;
        const auto tokens = aurora::lex(source, "raw-type-diagnostic.au");
        const auto offset = tokens.at(token).span.begin.offset + half;
        require(!half || tokens.at(token).text == ">>", "raw half-token expectation has no shared closer");
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(source);
        require(result[0] == wire(expected) && result[1] == -1 && result[3] == static_cast<std::int64_t>(token) &&
                    result[4] == static_cast<std::int64_t>(offset),
                "typed raw rejection status/token/half differs");
        arena.finish();
        require(allocations.successful == allocations.released, "typed diagnostic leaked an owner");
        ++cases;
    }
    struct Dependent {
        std::string source;
        ContextWords context;
        Status status;
    };
    for (const auto &test :
         std::vector<Dependent>{{"T f<T>();", {0, 1, 0, 0, 0, 0, 1}, Status::TemplateContext},
                                {"T f<Box<T>>();", {0, 1, 0, 0, 0, 0, 2}, Status::NestedDependent},
                                {"T f<T<i64>>();", {0, 1, 0, 0, 0, 0, 2}, Status::NestedDependent}}) {
        context = "raw dependent context rejection " + test.source;
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(test.source, Stop::Semicolon, 2, test.context);
        require(result[0] == wire(test.status) && result[1] == -1,
                "copied dependent context did not enforce its stated restriction");
        arena.finish();
        require(allocations.successful == allocations.released, "dependent diagnostic leaked an owner");
        ++cases;
    }
}

void rawTypeGrowth() {
    context = "independent type/candidate growth and every allocation failure";
    constexpr std::int64_t count = 257;
    std::string source = "{";
    for (std::int64_t index = 0; index < count; ++index) {
        if (index)
            source += ',';
        source += "f<i64>(size_of(array<u8, 4>))";
    }
    source += "};";
    std::vector<TypeWords> expected;
    for (std::int64_t index = 0; index < count; ++index) {
        const auto token = 1 + 16 * index, first = 5 * index;
        expected.push_back({1, token + 2, token + 2, 2 * (token + 2), -1, -1, -1, 0});
        expected.push_back({5, token, token, 2 * (token + 3), first, -1, token, 1});
        expected.push_back({3, token + 9, token + 9, 2 * (token + 9), -1, -1, -1, 0});
        expected.push_back({7, token + 11, token + 11, 2 * (token + 11), -1, -1, -1, 0});
        expected.push_back({9, token + 7, token + 7, 2 * (token + 12), first + 2, first + 3, token + 5, 2});
    }
    std::size_t successful = 0;
    {
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(source);
        require(result[0] == wire(Status::Success) && result[2] == 2 * count + 1 && arena.types() == 5 * count &&
                    arena.edges() == 2 * count,
                "wide typed root omitted expression/type records");
        for (std::int64_t index = 0; index < arena.types(); ++index)
            require(arena.type(index) == expected[static_cast<std::size_t>(index)],
                    "type growth changed committed topology/provenance/ownership");
        const auto metrics = arena.metrics();
        require(metrics.successful_allocations > 15 && metrics.live_allocations == 5 &&
                    metrics.peak_live_allocations == 5 && metrics.peak_used > 5 * count * 64,
                "typed parse did not grow all independent storage owners");
        successful = allocations.successful;
        arena.finish();
        require(allocations.successful == allocations.released, "typed growth cleanup mismatch");
    }
    for (std::size_t allowed = 0; allowed < successful; ++allowed) {
        Allocations allocations;
        allocations.allowed = allowed;
        RawArena arena(allocations);
        const auto result = arena.parse(source);
        require(result[0] == wire(Status::AllocationFailure) && result[1] == -1,
                "type/prepass allocation failure did not fail closed");
        require(arena.types() >= 0 && arena.types() <= static_cast<std::int64_t>(expected.size()),
                "type failure exposed an impossible prefix count");
        for (std::int64_t index = 0; index < arena.types(); ++index)
            require(arena.type(index) == expected[static_cast<std::size_t>(index)],
                    "type failure damaged a previously committed record");
        arena.finish();
        require(allocations.successful == allocations.released, "partial type/candidate graph leaked an owner");
    }
    std::vector<Ast> children;
    for (std::size_t index = 0; index < count; ++index) {
        const auto token = 1 + 16 * index;
        children.push_back(typed(call(token, {reflected(token + 5, aurora::Type::array(aurora::TypeKind::U8, 4))}),
                                 {aurora::TypeKind::I64}));
    }
    pin(source.substr(0, source.size() - 1), tree("array_literal", 0, std::move(children)));
    supported(source);
    ++cases;
}

void rawAggregateDiagnostics() {
    struct Rejection {
        std::string source;
        Status status;
        std::int64_t token;
        Stop stop = Stop::Semicolon;
    };
    for (const auto &test :
         std::vector<Rejection>{{"{1;", Status::ExpectedBraceClose, 2},
                                {"{1,};", Status::ExpectedExpression, 4},
                                {"{,};", Status::ExpectedExpression, 2},
                                {"{1 2};", Status::ExpectedBraceClose, 2},
                                {"{1,2", Status::ExpectedBraceClose, 4},
                                {"Box{value=1};", Status::ExpectedDot, 2},
                                {"Box{.1=1};", Status::ExpectedIdentifier, 3},
                                {"Box{.true=1};", Status::ReservedIdentifier, 3},
                                {"Box{.array=1};", Status::ReservedBuiltin, 3},
                                {"Box{.__au_private=1};", Status::ReservedPrefix, 3},
                                {"Box{.value 1};", Status::ExpectedEqual, 4},
                                {"Box{.value=};", Status::ExpectedExpression, 6},
                                {"Box{.value=1,};", Status::ExpectedDot, 7},
                                {"Box{.value=1;", Status::ExpectedBraceClose, 6},
                                {"value(1)", Status::ExpectedBraceOpen, 1, Stop::ConstructorBraces},
                                {"value{1,}", Status::ExpectedExpression, 5, Stop::ConstructorBraces},
                                {"value{1", Status::ExpectedBraceClose, 3, Stop::ConstructorBraces},
                                {"true{}", Status::ReservedIdentifier, 0, Stop::ConstructorBraces},
                                {"array{}", Status::ReservedBuiltin, 0, Stop::ConstructorBraces},
                                {"__au_field{}", Status::ReservedPrefix, 0, Stop::ConstructorBraces}}) {
        context = "raw aggregate diagnostic " + test.source;
        const auto tokens = aurora::lex(test.source, "raw-aggregate-diagnostic.au");
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(test.source, test.stop);
        require(result[0] == wire(test.status) && result[1] == -1 && result[3] == test.token &&
                    result[4] == static_cast<std::int64_t>(tokens.at(test.token).span.begin.offset),
                "aggregate rejection status/token/offset differs");
        arena.finish();
        require(allocations.successful == allocations.released, "aggregate diagnostic leaked an owner");
        ++cases;
    }
    rawCase("{};", Status::Invalid, static_cast<Stop>(-1));
    rawCase("{};", Status::Invalid, static_cast<Stop>(5));
}

void abiControls() {
    context = "independent ABI envelope controls";
    const rlimit noCore{0, 0};
    require(setrlimit(RLIMIT_CORE, &noCore) == 0, "cannot disable negative-control core dumps");
    const std::array<AbiEntry, 8> controls{hosted_parser_clobber_rbp,
                                           hosted_parser_clobber_rbx,
                                           hosted_parser_clobber_r12,
                                           hosted_parser_clobber_r13,
                                           hosted_parser_clobber_r14,
                                           hosted_parser_clobber_r15,
                                           hosted_parser_clobber_canary,
                                           hosted_parser_shift_stack};
    for (std::size_t i = 0; i <= controls.size(); ++i) {
        const auto child = fork();
        require(child >= 0, "cannot fork ABI control");
        if (child == 0) {
            if (i < controls.size())
                checked_hosted_parser_call(nullptr, nullptr, nullptr, controls[i]);
            else
                hosted_parser_misaligned_call(nullptr, nullptr, nullptr, controls[0]);
            _exit(0);
        }
        int status = 0;
        pid_t observed;
        do {
            observed = waitpid(child, &status, 0);
        } while (observed < 0 && errno == EINTR);
        require(observed == child && WIFSIGNALED(status) && WTERMSIG(status) == SIGILL,
                "ABI corruption did not produce SIGILL: " + std::to_string(i));
    }
}
void rawGrowth() {
    context = "real Aurora growth and ABI node records";
    const auto source = chain(100) + ";";
    std::size_t successful = 0;
    {
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(source);
        require(result == Words{wire(Status::Success), 198, 199, 199, 199},
                "100-term raw parse did not return exact graph/cursor");
        for (std::int64_t i = 0; i < 199; ++i) {
            const auto node = arena.read(i);
            if (i == 0)
                require(node == NodeWords{wire(NodeKind::Literal), 0, -1, -1, 1, 0, 0}, "first literal ABI differs");
            else if (i % 2 == 1)
                require(node == NodeWords{wire(NodeKind::Literal), i + 1, -1, -1, 1, i + 1, i + 1},
                        "literal ABI differs");
            else
                require(node == NodeWords{wire(NodeKind::Binary), i - 1, i - 2, i - 1, i / 2 + 1, i - 1, i - 1},
                        "binary ABI/topology/depth differs");
        }
        const auto used = arena.metrics();
        require(used.successful_allocations > 5 && used.peak_live_allocations == 5 && used.live_allocations == 5,
                "parser did not grow its node/frame stores while retaining the empty edge/type/statement owners");
        successful = allocations.successful;
        arena.finish();
        require(allocations.released == successful, "success cleanup mismatch");
    }
    for (std::size_t allowed = 0; allowed < 5; ++allowed) {
        Allocations allocations;
        allocations.allowed = allowed;
        RawArena arena(allocations);
        require(arena.parse("size_of(i64);")[0] == wire(Status::AllocationFailure),
                "failed arena allocation did not reject before typed parsing");
        arena.finish();
    }
    // Refuse every allocation in sequence, including frame and node growth.
    // All partial graphs still leave all five owners releasable exactly once.
    for (std::size_t allowed = 0; allowed < successful; ++allowed) {
        Allocations allocations;
        allocations.allowed = allowed;
        RawArena arena(allocations);
        const auto result = arena.parse(source);
        require(result[0] == static_cast<std::int64_t>(Status::AllocationFailure) && result[1] == -1,
                "injected allocation/growth failure did not fail closed");
        if (result[2] > 0)
            require(arena.read(0) == NodeWords{wire(NodeKind::Literal), 0, -1, -1, 1, 0, 0},
                    "failed growth changed an already committed node");
        arena.finish();
        require(allocations.successful == allocations.released, "failure cleanup mismatch");
    }
    {
        Allocations allocations;
        RawArena arena(allocations, 0);
        require(arena.parse("1;")[0] == static_cast<std::int64_t>(Status::AllocationFailure), "quota failure accepted");
        arena.finish();
    }
    for (const auto &[sourceText, expected] :
         std::array<std::pair<std::string, NodeWords>, 4>{{{"name;", {wire(NodeKind::Name), 0, -1, -1, 1, 0, 0}},
                                                           {"true;", {wire(NodeKind::Literal), 0, -1, -1, 1, 0, 0}},
                                                           {"'x';", {wire(NodeKind::Literal), 0, -1, -1, 1, 0, 0}},
                                                           {"-1;", {wire(NodeKind::Unary), 0, 0, -1, 2, 0, 0}}}}) {
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(sourceText);
        require(result[0] == wire(Status::Success) && arena.read(result[1]) == expected,
                "real generated node kind ABI differs");
        arena.finish();
    }
    {
        Allocations allocations;
        RawArena arena(allocations);
        require(arena.parse("1;", Stop::Semicolon, 3)[0] == wire(Status::Invalid),
                "invalid lexer cursor did not return the named Invalid status");
        arena.finish();
    }
    ++cases;
}
void rawFrameGrowth() {
    context = "real Aurora explicit-frame growth and failure cleanup";
    const auto source = std::string(127, '(') + "1" + std::string(127, ')') + ";";
    const NodeWords literal{wire(NodeKind::Literal), 127, -1, -1, 1, 127, 127};
    std::size_t successful = 0;
    {
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(source);
        require(result == Words{wire(Status::Success), 0, 1, 255, 255} && arena.read(0) == literal,
                "127 nested groups did not return the exact leaf graph/cursor");
        const auto used = arena.metrics();
        // One leaf needs only the first eight-node capacity. Payload above the
        // first eight-frame plus eight-node capacities therefore proves actual
        // explicit-frame growth, independently of the allocation count.
        require(used.peak_used > 8 * 40 + 8 * 56 && used.successful_allocations > 5 &&
                    used.peak_live_allocations == 5 && used.live_allocations == 5,
                "nested parser did not grow its explicit frame owner");
        successful = allocations.successful;
        arena.finish();
        require(allocations.released == successful, "nested success cleanup mismatch");
    }
    for (std::size_t allowed = 0; allowed < successful; ++allowed) {
        Allocations allocations;
        allocations.allowed = allowed;
        RawArena arena(allocations);
        const auto result = arena.parse(source);
        require(result[0] == wire(Status::AllocationFailure) && result[1] == -1,
                "injected frame-growth failure did not fail closed");
        if (result[2] > 0)
            require(arena.read(0) == literal, "failed frame growth changed an already committed node");
        arena.finish();
        require(allocations.successful == allocations.released, "frame-growth failure cleanup mismatch");
    }
    ++cases;
}
void rawArguments() {
    context = "real argument-edge growth and failure cleanup";
    constexpr std::int64_t count = 257;
    std::string source = "f(";
    for (std::int64_t index = 0; index < count; ++index) {
        if (index)
            source += ',';
        source += '1';
    }
    source += ");";
    std::size_t successful = 0;
    {
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(source);
        require(result == Words{wire(Status::Success), count, count + 1, 2 * count + 2, 2 * count + 2},
                "wide call did not return the complete graph/cursor");
        require(arena.edges() == count &&
                    arena.read(count) == NodeWords{wire(NodeKind::Call), 0, count - 1, count, 2, 0, 2 * count + 1},
                "call ABI, arity or closing-token provenance differs");
        for (std::int64_t index = 0; index < count; ++index)
            require(arena.edge(index) == EdgeWords{index, index - 1, index + 1, 2, -1},
                    "reverse-linked argument ABI differs");
        const auto metrics = arena.metrics();
        require(metrics.successful_allocations > 10 && metrics.live_allocations == 5 &&
                    metrics.peak_live_allocations == 5,
                "wide call did not grow independent node and argument owners");
        successful = allocations.successful;
        arena.finish();
    }
    for (std::size_t allowed = 0; allowed < successful; ++allowed) {
        Allocations allocations;
        allocations.allowed = allowed;
        RawArena arena(allocations);
        const auto result = arena.parse(source);
        require(result[0] == wire(Status::AllocationFailure) && result[1] == -1,
                "injected argument allocation failure did not reject");
        arena.finish();
        require(allocations.successful == allocations.released, "partial argument graph leaked an owner");
    }
    for (const auto &[text, expected] :
         std::array<std::pair<std::string, NodeWords>, 4>{{{"ns::f(1,2);", {wire(NodeKind::Call), 0, 1, 2, 2, 2, 7}},
                                                           {"obj.m();", {wire(NodeKind::MethodCall), 2, 0, 1, 2, 2, 4}},
                                                           {"a.b;", {wire(NodeKind::Member), 2, 0, -1, 2, 2, 2}},
                                                           {"a[0];", {wire(NodeKind::Index), 1, 0, 1, 2, 1, 3}}}}) {
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(text);
        require(result[0] == wire(Status::Success) && arena.read(result[1]) == expected,
                "postfix generated-code node ABI differs");
        arena.finish();
    }
    std::vector<Ast> children;
    for (std::size_t index = 0; index < count; ++index)
        children.push_back(number(2 + 2 * index));
    pin(source.substr(0, source.size() - 1), call(0, std::move(children)));
    supported(source);
    ++cases;
}
void rawAggregates() {
    struct Empty {
        std::string source;
        Stop stop;
        NodeKind kind;
        std::int64_t last, close, tokens, offset;
    };
    for (const auto &test : std::vector<Empty>{
             {"{};", Stop::Semicolon, NodeKind::ArrayLiteral, 0, 1, 2, 2},
             {"{};size_of(i64)", Stop::Semicolon, NodeKind::ArrayLiteral, 0, 1, 2, 2},
             {"ns::Box{};", Stop::Semicolon, NodeKind::Construct, 2, 4, 5, 9},
             {"field{}", Stop::ConstructorBraces, NodeKind::ArrayZero, 0, 2, 3, 7},
             {"field{},other{}", Stop::ConstructorBraces, NodeKind::ArrayZero, 0, 2, 3, 7},
             {"field{}{size_of(i64)", Stop::ConstructorBraces, NodeKind::ArrayZero, 0, 2, 3, 7},
             {"field{};size_of(i64)", Stop::ConstructorBraces, NodeKind::ArrayZero, 0, 2, 3, 7},
             {"field{} // following trivia\n {", Stop::ConstructorBraces, NodeKind::ArrayZero, 0, 2, 3, 29}}) {
        context = "empty aggregate ABI " + test.source;
        if (test.stop == Stop::ConstructorBraces) {
            const auto tokens = aurora::lex(test.source, "empty-brace-boundary.au");
            std::size_t position = 0;
            const auto expression = aurora::parseHostedExpression(tokens, position, test.stop);
            require(expression && expression->op == "array_zero" && expression->args.empty() &&
                        expression->depth == 1 && position == static_cast<std::size_t>(test.tokens) &&
                        tokens.at(position).span.begin.offset == static_cast<std::size_t>(test.offset),
                    "empty constructor host conversion lost its exact next-token/EOF boundary");
            sameToken(expression->token, tokens[0]);
        }
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(test.source, test.stop);
        require(result == Words{wire(Status::Success), 0, 1, test.tokens, test.offset} && arena.edges() == 0 &&
                    arena.read(0) == NodeWords{wire(test.kind), 0, -1, 0, 1, test.last, test.close},
                "empty aggregate kind/token/close/cursor ABI differs");
        arena.finish();
        require(allocations.successful == allocations.released, "empty aggregate cleanup mismatch");
        ++cases;
    }
    for (const auto &suffix : {"", ",other{}", "{size_of(i64)", ";"}) {
        context = "nonempty constructor aggregate boundary " + std::string(suffix);
        const auto tokens = aurora::lex(std::string("field{1}") + suffix, "brace-boundary.au");
        std::size_t position = 0;
        const auto expression = aurora::parseHostedExpression(tokens, position, Stop::ConstructorBraces);
        require(expression && expression->op == "array_literal" && expression->args.size() == 1 &&
                    expression->depth == 2 && expression->args[0]->op == "number" && expression->args[0]->depth == 1 &&
                    position == 4 && tokens.at(position).span.begin.offset == 8,
                "nonempty constructor host conversion lost its exact next-token/EOF boundary");
        sameToken(expression->token, tokens[0]);
        sameToken(expression->args[0]->token, tokens[2]);
        Allocations allocations;
        RawArena arena(allocations);
        require(arena.parse(std::string("field{1}") + suffix, Stop::ConstructorBraces) ==
                        Words{wire(Status::Success), 1, 2, 4, 8} &&
                    arena.read(0) == NodeWords{wire(NodeKind::Literal), 2, -1, -1, 1, 2, 2} &&
                    arena.read(1) == NodeWords{wire(NodeKind::ArrayLiteral), 0, 0, 1, 2, 0, 3} && arena.edges() == 1 &&
                    arena.edge(0) == EdgeWords{0, -1, 1, 2, -1},
                "nonempty constructor braces changed their field token or consumed following syntax");
        arena.finish();
        require(allocations.successful == allocations.released, "constructor aggregate cleanup mismatch");
        ++cases;
    }
    {
        context = "nested array exact graph and edge provenance";
        Allocations allocations;
        RawArena arena(allocations);
        require(arena.parse("{1,{2,3}};") == Words{wire(Status::Success), 4, 5, 9, 9},
                "nested array graph/cursor differs");
        const std::array<NodeWords, 5> expected{{{wire(NodeKind::Literal), 1, -1, -1, 1, 1, 1},
                                                 {wire(NodeKind::Literal), 4, -1, -1, 1, 4, 4},
                                                 {wire(NodeKind::Literal), 6, -1, -1, 1, 6, 6},
                                                 {wire(NodeKind::ArrayLiteral), 3, 2, 2, 2, 3, 7},
                                                 {wire(NodeKind::ArrayLiteral), 0, 3, 2, 3, 0, 8}}};
        const std::array<EdgeWords, 4> edges{
            {{0, -1, 1, 2, -1}, {1, -1, 1, 2, -1}, {2, 1, 2, 2, -1}, {3, 0, 2, 3, -1}}};
        require(arena.edges() == static_cast<std::int64_t>(edges.size()), "nested array edge count differs");
        for (std::size_t index = 0; index < expected.size(); ++index)
            require(arena.read(index) == expected[index], "nested array node ABI differs");
        for (std::size_t index = 0; index < edges.size(); ++index)
            require(arena.edge(index) == edges[index], "nested array edge chain/depth differs");
        arena.finish();
        require(allocations.successful == allocations.released, "nested array cleanup mismatch");
        ++cases;
    }
    {
        context = "qualified designated field source order";
        const std::string source = "ns::Box{.last=1,.first=2};";
        Allocations allocations;
        RawArena arena(allocations);
        require(arena.parse(source) ==
                        Words{wire(Status::Success), 2, 3, 14, static_cast<std::int64_t>(source.size() - 1)} &&
                    arena.read(0) == NodeWords{wire(NodeKind::Literal), 7, -1, -1, 1, 7, 7} &&
                    arena.read(1) == NodeWords{wire(NodeKind::Literal), 12, -1, -1, 1, 12, 12} &&
                    arena.read(2) == NodeWords{wire(NodeKind::Construct), 0, 1, 2, 2, 2, 13} && arena.edges() == 2 &&
                    arena.edge(0) == EdgeWords{0, -1, 1, 2, 5} && arena.edge(1) == EdgeWords{1, 0, 2, 2, 10},
                "designated construction lost qualified name/field-label provenance");
        arena.finish();
        require(allocations.successful == allocations.released, "designated construction cleanup mismatch");
        ++cases;
    }
    constexpr std::int64_t count = 257;
    for (const auto kind : {NodeKind::ArrayLiteral, NodeKind::Construct, NodeKind::ArrayZero}) {
        // ArrayZero selects the constructor profile; its nonempty result must
        // be ArrayLiteral. No input profile imposes a fixed arity ceiling.
        const bool designated = kind == NodeKind::Construct, constructor = kind == NodeKind::ArrayZero;
        const auto stop = constructor ? Stop::ConstructorBraces : Stop::Semicolon;
        std::string source = designated ? "ns::Box{" : constructor ? "values{" : "{";
        for (std::int64_t index = 0; index < count; ++index) {
            if (index)
                source += ',';
            if (designated)
                source += ".f" + std::to_string(index) + "=";
            source += '1';
        }
        source += "};";
        context = "wide aggregate ABI " + source;
        const auto first = designated ? 7 : constructor ? 2 : 1;
        const auto step = designated ? 5 : 2;
        const auto close = designated ? 5 * count + 3 : constructor ? 2 * count + 1 : 2 * count;
        std::size_t successful = 0;
        {
            Allocations allocations;
            RawArena arena(allocations);
            require(arena.parse(source, stop) == Words{wire(Status::Success),
                                                       count,
                                                       count + 1,
                                                       close + 1,
                                                       static_cast<std::int64_t>(source.size() - 1)} &&
                        arena.read(count) == NodeWords{wire(designated ? NodeKind::Construct : NodeKind::ArrayLiteral),
                                                       0,
                                                       count - 1,
                                                       count,
                                                       2,
                                                       designated ? 2 : 0,
                                                       close} &&
                        arena.edges() == count,
                    "wide aggregate did not return the exact complete graph/cursor");
            for (std::int64_t index = 0; index < count; ++index) {
                const auto token = first + step * index;
                require(arena.read(index) == NodeWords{wire(NodeKind::Literal), token, -1, -1, 1, token, token},
                        "wide aggregate child order/token differs");
                require(arena.edge(index) == EdgeWords{index, index - 1, index + 1, 2, designated ? 5 + 5 * index : -1},
                        "wide aggregate edge/field-label ABI differs");
            }
            const auto metrics = arena.metrics();
            require(metrics.successful_allocations > 10 && metrics.live_allocations == 5 &&
                        metrics.peak_live_allocations == 5,
                    "wide aggregate did not grow independent node/edge owners");
            successful = allocations.successful;
            arena.finish();
            require(allocations.successful == allocations.released, "wide aggregate cleanup mismatch");
        }
        for (std::size_t allowed = 0; allowed < successful; ++allowed) {
            Allocations allocations;
            allocations.allowed = allowed;
            RawArena arena(allocations);
            const auto result = arena.parse(source, stop);
            require(result[0] == wire(Status::AllocationFailure) && result[1] == -1,
                    "aggregate allocation/growth failure did not fail closed");
            if (result[2] > 0)
                require(arena.read(0) == NodeWords{wire(NodeKind::Literal), first, -1, -1, 1, first, first},
                        "failed aggregate growth changed a committed node");
            arena.finish();
            require(allocations.successful == allocations.released, "partial aggregate graph leaked an owner");
        }
        std::vector<Ast> children;
        std::vector<std::string> fields;
        for (std::size_t index = 0; index < count; ++index) {
            children.push_back(number((constructor ? 1 : first) + step * index));
            if (designated)
                fields.push_back("f" + std::to_string(index));
        }
        if (constructor) {
            const auto contents = source.substr(6, source.size() - 7);
            pin(contents, tree("array_literal", 0, std::move(children)));
            constructorBraces(contents);
        } else {
            pin(source.substr(0, source.size() - 1),
                designated ? construct(0, 2, fields, children) : tree("array_literal", 0, children));
            supported(source);
        }
        ++cases;
    }
}

} // namespace

int main(int argc, char **argv) {
    try {
        context = "fixture arguments";
        require(argc == 16, "expected three bootstrap, five aggregate and seven typed consumer source paths");
        grammarExpectations();
        diagnosticExpectations();
        for (const auto &expression :
             {"1;",
              "false;",
              "true;",
              "name;",
              "_value;",
              "'x';",
              "'\\n';",
              "123u64;",
              "255u8;",
              "-1 + ~2 * !false;",
              "a || b && c | d ^ e & f == g != h < i <= j > k >= l << m >> n + o - p * q / r % s;",
              "(a + b) * (c - d);",
              "(a);",
              "1 // comment\n + 2;",
              "a < b >> (c);"})
            supported(expression);
        supported("true < x > (y);");
        supported("(a) < b > (c);");
        supported(chain(100) + ";");
        supported(chain(128) + ";");
        supported(std::string(127, '(') + "1" + std::string(127, ')') + ";");
        supported(std::string(127, '-') + "1;");
        supported("1 + 2)", Stop::CloseParenthesis);
        supported("target = 2;", Stop::Assignment);
        supported("1 + 2;", Stop::Assignment);
        for (const auto &expression : {"f();",
                                       "f(1, 2);",
                                       "name.member;",
                                       "name.at(1);",
                                       "one::two;",
                                       "a[1];",
                                       "f(g(1), h(2, 3)) + object.at(index + 1);",
                                       "Box(42);",
                                       "move(value);",
                                       "one // name trivia\n :: two(1, other.run()).field[2].at(3);",
                                       "((a)).field;",
                                       "(a + b)[(i)];",
                                       "a[one::index(f(1))].method().field;",
                                       "builtin::borrow_bytes(value);",
                                       "one::array(1);",
                                       "object.size_of();",
                                       "ns::size_of(i64);",
                                       "-object.at(1) + f(2);",
                                       "fn;",
                                       "__au_name;"})
            supported(expression);
        supported("a[1] = 2;", Stop::Assignment);
        supported("f(a[1], b.member))", Stop::CloseParenthesis);
        for (const auto &expression :
             {"size_of(i64);", "type_id(array<u8,2>);", "field_count(Box);", "f(size_of(i64));"})
            supported(expression);
        checkedRootProgram("module templates; auto f()->i64{return ", "f<i64>(1)", ";}");
        checkedRootProgram("module templates; auto f()->i64{return ", "x<y<z>>(a)", ";}");
        rejectedProgram("module templates; auto f()->i64{return ", "f<T)>(0);", "}");
        rejectedProgram("module templates; auto f()->i64{if(", "f<T)>(0)", "){return 1;}return 0;}");
        checkedRootProgram("module templates; auto f()->i64{return ", "f<a<b<c>>>(0)", ";}");
        checkedRootProgram("module templates; auto f()->i64{return ", "f<a<b<c>>(0)", ";}");
        for (const auto &expression : {"(f<T)>(0)", "f<T]>(0)", "f<T:>(0)"})
            rejectedProgram("module errors; auto f()->i64{return ", expression, ";}");
        checkedProgram("module hooks; auto f()->i64 { i64 x = 1+2; const i64 y = 3; x = x+y; x+1; "
                       "static_assert(true && !false); if(x>0){x=x-1;}else{x=0;} while(x<4){x=x+1;} return x*2; }",
                       {binary(14, number(13), number(15)),
                        number(21),
                        binary(26, name(25), name(27)),
                        binary(30, name(29), number(31)),
                        binary(36, tree("bool", 35), tree("unary", 37, {tree("bool", 38)})),
                        binary(44, name(43), number(45)),
                        binary(51, name(50), number(52)),
                        number(59),
                        binary(65, name(64), number(66)),
                        binary(72, name(71), number(73)),
                        binary(78, name(77), number(79))});
        checkedProgram("module fallback; auto f()->i64 { i64 x=f(1); x=f(2); if(f(1)){return f(2);} "
                       "while(f(0)){x=f(3);} static_assert(f(1)); return x<y<z>>(a); }",
                       {call(13, {number(15)}),
                        call(20, {number(22)}),
                        call(27, {number(29)}),
                        call(34, {number(36)}),
                        call(42, {number(44)}),
                        call(50, {number(52)}),
                        call(58, {number(60)}),
                        typed(call(65, {name(72)}), {namedArgument("y", {namedArgument("z")})})});
        for (const auto &expression : {";",
                                       "1 + ;",
                                       "(1 + 2;",
                                       "1 2;",
                                       "1 +",
                                       "(1) + ;",
                                       ":;",
                                       "];",
                                       ",;",
                                       "1:2;",
                                       "1]2;",
                                       "1,2;",
                                       "1(2);",
                                       "true(2);",
                                       "(1)(2);"})
            rejectedProgram("module errors; auto f()->i64{return ", expression, "}");
        rejectedProgram(
            "module depth; auto f()->i64{return ", chain(129), ";}", {"expression AST depth exceeds 128", 256});
        rejectedProgram("module depth; auto f()->i64{return ",
                        std::string(128, '(') + "1" + std::string(128, ')'),
                        ";}",
                        {"expression parser nesting exceeds 128", 128, 0, aurora::DiagnosticCode::NestingLimit});
        rejectedProgram("module depth; auto f()->i64{return ",
                        std::string(128, '-') + "1",
                        ";}",
                        {"expression parser nesting exceeds 128", 128, 0, aurora::DiagnosticCode::NestingLimit});
        for (const auto &expression : {"f(;",
                                       "f(1;",
                                       "f(1,);",
                                       "f(,);",
                                       "f(1 2);",
                                       "a.;",
                                       "a..b;",
                                       "a.true;",
                                       "a.array;",
                                       "a.builtin;",
                                       "a.__au_private;",
                                       "name::;",
                                       "name::true;",
                                       "name::builtin;",
                                       "name::__au_x;",
                                       "a[;",
                                       "a[];",
                                       "a[1;",
                                       "a[1);",
                                       "a[1,2];",
                                       "f(1)(2);"})
            rejectedProgram("module errors; auto f()->i64{return ", expression, "}");
        std::string members = "a", indices = "a", calls = "1";
        for (int i = 0; i < 127; ++i) {
            members += ".field";
            indices += "[0]";
            calls = "f(" + calls + ")";
        }
        auto memberTree = name(0), indexTree = name(0), callTree = number(254);
        for (std::size_t ordinal = 0; ordinal < 127; ++ordinal) {
            memberTree = tree("member", 2 + 2 * ordinal, {memberTree});
            indexTree = index(indexTree, number(2 + 3 * ordinal));
            callTree = call(252 - 2 * ordinal, {callTree});
        }
        pin(members, memberTree);
        pin(indices, indexTree);
        pin(calls, callTree);
        supported(members + ";");
        supported(indices + ";");
        supported(calls + ";");
        rejectedProgram(
            "module depth; auto f()->i64{return ", members + ".field", ";}", {"expression AST depth exceeds 128", 257});
        rejectedProgram(
            "module depth; auto f()->i64{return ", indices + "[0]", ";}", {"expression AST depth exceeds 128", 383});
        rejectedProgram("module depth; auto f()->i64{return ",
                        "f(" + calls + ")",
                        ";}",
                        {"expression parser nesting exceeds 128", 256, 0, aurora::DiagnosticCode::NestingLimit});
        rawCase("1;", Status::Success);
        rawCase("{1};", Status::Success);
        rawCase("f(1);", Status::Success);
        rawCase("a[1;", Status::ExpectedIndexClose);
        rawCase("a.;", Status::ExpectedIdentifier);
        rawCase("a.true;", Status::ReservedIdentifier);
        rawCase("a.array;", Status::ReservedBuiltin);
        rawCase("a.__au_private;", Status::ReservedPrefix);
        rawCase("1+;", Status::ExpectedExpression);
        rawCase("(1;", Status::ExpectedClose);
        rawCase("1 2;", Status::ExpectedEnd);
        for (const auto &source : {":;", "];", ",;"})
            rawCase(source, Status::ExpectedExpression);
        for (const auto &source : {"1:2;", "1]2;", "1,2;", "1(2);", "true(2);", "(1)(2);"})
            rawCase(source, Status::ExpectedEnd);
        rawCase(std::string(128, '(') + "1" + std::string(128, ')') + ";", Status::NestingLimit);
        rawCase(chain(129) + ";", Status::DepthLimit);
        rawCase("1)", Status::Success, Stop::CloseParenthesis);
        rawCase("name=", Status::Success, Stop::Assignment);
        byteStrings();
        constructors();
        aggregateSyntax();
        typedSyntax();
        rawBodies();
        bodySyntax();
        bodyContexts();
        bodyDiagnostics();
        rawTypeRecords();
        rawTypeDiagnostics();
        rawTypeGrowth();
        rawAggregateDiagnostics();
        abiControls();
        rawGrowth();
        rawFrameGrowth();
        rawArguments();
        rawAggregates();
        bootstrapSources(argv + 1);
        consumerSources(argv + 4);
        typedConsumerSources(argv + 9);
        std::cout << "PASS hosted parser " << cases
                  << " explicit AST/diagnostic, dispatch-consistency and ABI cases, 199-node/frame and "
                     "257-argument/aggregate growth with allocation cleanup; "
                     "dispatch-consistent constructor/string roots from all three actual bootstrap sources; "
                     "14 aggregate roots including 512 XFS elements, 16 direct typed product roots, "
                     "1,285-record type growth, all 125 historical and all new bootstrap bodies, "
                     "513-statement/128-block growth and fifth-owner cleanup\n";
    } catch (const std::exception &error) {
        std::cerr << "FAIL " << error.what() << '\n';
        return 1;
    }
}
