// Exercise the real Aurora phase against explicit AST and diagnostic contracts.
// Whole-program/direct-source comparisons check dispatch consistency only.
// Raw copied ABI records remain deliberately independent of the host adapter.
#include "lexer.hpp"
#include "parser.hpp"
#include "hosted_parser.hpp"
#include "hosted_resolver.hpp"
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
#include <sstream>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>

#if !defined(AURORA_HOSTED_PARSER) || !defined(AURORA_HOSTED_LEXER)
#error The hosted parser fixture must link the real Aurora frontend
#endif
extern "C" {
void checked_hosted_parser_create(const void *, void *);
void checked_hosted_parser_parse(void *, const void *, void *);
void checked_hosted_parser_admit(void *, const void *, void *);
std::int64_t checked_hosted_parser_count(const void *);
void checked_hosted_parser_read(const void *, std::int64_t, void *);
std::int64_t checked_hosted_parser_edges(const void *);
void checked_hosted_parser_edge(const void *, std::int64_t, void *);
std::int64_t checked_hosted_parser_types(const void *);
void checked_hosted_parser_type(const void *, std::int64_t, void *);
std::int64_t checked_hosted_parser_syntax_count(const void *);
void checked_hosted_parser_syntax(const void *, std::int64_t, void *);
void checked_hosted_parser_release(void *);
void checked_hosted_resolver_create(const void *, void *);
void checked_hosted_resolver_ingest(void *, void *);
void checked_hosted_resolver_release(void *);
void checked_hosted_resolver_release_pair(void *);
std::int64_t checked_hosted_resolver_append_source(void *, const void *);
std::int64_t checked_hosted_resolver_count(const void *, std::int64_t);
std::int64_t checked_hosted_resolver_read_source(const void *, std::int64_t);
void checked_hosted_resolver_read_meta(const void *, std::int64_t, void *);
void checked_hosted_resolver_status(const void *, void *);
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
using aurora::hosted_parser::AdmissionStatus;
using aurora::hosted_parser::Context;
using aurora::hosted_parser::Cursor;
using aurora::hosted_parser::NodeKind;
using aurora::hosted_parser::Status;
using aurora::hosted_parser::Stop;
using Words = std::array<std::int64_t, 6>;
using AdmissionWords = std::array<std::int64_t, 5>;
using AdmissionConfigWords = std::array<std::int64_t, 6>;
constexpr AdmissionConfigWords admissionConfiguration{64, 512, 62, 1, 2, 4};
using NodeWords = std::array<std::int64_t, 7>;
using EdgeWords = std::array<std::int64_t, 5>;
using TypeWords = std::array<std::int64_t, 8>;
using SyntaxWords = std::array<std::int64_t, 12>;
using aurora::hosted_parser::SyntaxKind;
using ContextWords = std::array<std::int64_t, 7>;
constexpr std::int64_t wire(NodeKind value) {
    return static_cast<std::int64_t>(value);
}
constexpr std::int64_t wire(SyntaxKind value) {
    return static_cast<std::int64_t>(value);
}
constexpr std::int64_t wire(Status value) {
    return static_cast<std::int64_t>(value);
}
constexpr std::int64_t wire(AdmissionStatus value) {
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
// Compare the declarative expectation directly; never construct it with the
// parser or the production AST constructors. Depth follows only the stated tree.
int sameTree(const aurora::ExpressionPtr &actual,
             const std::vector<aurora::Token> &tokens,
             const Ast &expected,
             std::size_t base = 0) {
    require(bool(actual), "expected expression is missing");
    auto token = tokens.at(base + expected.first);
    for (auto ordinal = expected.first + 1; ordinal <= expected.last; ++ordinal)
        token.text += tokens.at(base + ordinal).text;
    token.span.end = tokens.at(base + expected.last).span.end;
    require(actual->op == expected.op && actual->args.size() == expected.args.size() &&
                actual->fieldNames == expected.fields && actual->templateArguments == expected.types &&
                actual->reflectedType == expected.reflected,
            "expression shape/spelling differs at " + actual->op + ":" + actual->token.text);
    sameToken(actual->token, token);
    int depth = 1;
    for (std::size_t index = 0; index < expected.args.size(); ++index)
        depth = std::max(depth, sameTree(actual->args[index], tokens, expected.args[index], base) + 1);
    require(actual->depth == depth, "expression depth differs");
    return depth;
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
struct StatementAst {
    std::size_t token;
    std::string kind;
    std::optional<Ast> expr = {};
    std::vector<StatementAst> body = {}, other = {};
    std::string name = {}, fieldName = {};
    std::optional<Ast> target = {};
    aurora::Type type = aurora::Type::I64;
    bool mutableValue = false;
    std::size_t binding = std::string::npos;
};
StatementAst local(std::size_t token, std::size_t binding, aurora::Type type, bool mutableValue, Ast expression) {
    return {.token = token,
            .kind = "let",
            .expr = std::move(expression),
            .type = std::move(type),
            .mutableValue = mutableValue,
            .binding = binding};
}
void sameBody(const std::vector<aurora::StatementPtr> &actual,
              const std::vector<aurora::Token> &tokens,
              const std::vector<StatementAst> &expected,
              std::size_t base = 0) {
    require(actual.size() == expected.size(), "statement list size/order differs");
    for (std::size_t index = 0; index < expected.size(); ++index) {
        const auto &a = actual[index];
        const auto &b = expected[index];
        const bool binding = b.binding != std::string::npos;
        require(a && a->kind == b.kind && a->name == (binding ? tokens.at(base + b.binding).text : b.name) &&
                    a->fieldName == b.fieldName && a->type == b.type && a->mutableValue == b.mutableValue,
                "statement kind/binding/type/field/mutability differs");
        sameToken(a->token, tokens.at(base + b.token));
        sameSpan(a->bindingSpan, binding ? tokens.at(base + b.binding).span : aurora::SourceSpan{});
        require(bool(a->expr) == bool(b.expr) && bool(a->target) == bool(b.target),
                "statement expression presence differs");
        if (b.expr)
            sameTree(a->expr, tokens, *b.expr, base);
        if (b.target)
            sameTree(a->target, tokens, *b.target, base);
        sameBody(a->body, tokens, b.body, base);
        sameBody(a->other, tokens, b.other, base);
    }
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
std::vector<std::pair<std::string, Ast>> aggregateExpressions, typedExpressions;
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
struct ErrorCases {
    ExpectedError expected;
    std::vector<std::string> sources;
};
std::vector<ErrorCases> returnedErrors, typedErrors, aggregateErrors;
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
// Keep diagnostic comparison separate from caller-owned cursor, token and
// grammar/admission-stage assertions. Non-Aurora exceptions remain test failures.
template <class Action>
void expectError(const std::vector<aurora::Token> &tokens,
                 const ExpectedError &expected,
                 Action action,
                 std::size_t base = 0) {
    try {
        action();
    } catch (const aurora::Error &error) {
        sameError(error.diagnostic, tokens, expected, base);
        return;
    }
    require(false, "malformed input was accepted");
}
// Every program fixture enters the one whole-module Aurora call. Acceptance
// alone is not an AST oracle; the explicit inventories below carry that claim.
aurora::Program checkedProgram(const std::vector<aurora::Token> &tokens) {
    auto program = aurora::parseHostedProgram(tokens);
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
        sameTree(roots[index], tokens, expected[index]);
}
void rejectedProgram(const std::string &prefix,
                     const std::string &expression,
                     const std::string &suffix,
                     const ExpectedError &expected) {
    context = prefix + expression + suffix;
    const auto tokens = aurora::lex(context, "parser-program-error.au");
    expectError(
        tokens,
        expected,
        [&] {
            aurora::parseHostedProgram(tokens);
        },
        aurora::lex(prefix, "prefix.au").size() - 1);
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
void supported(const std::string &text, Stop stop = Stop::semicolon) {
    context = text;
    const auto tokens = aurora::lex(text, "supported.au");
    const auto found = expressionExpectations.find(fixtureKey(tokens));
    require(found != expressionExpectations.end(), "missing explicit AST fixture");
    std::size_t position = 0;
    const auto expression = aurora::parseHostedExpression(tokens, position, stop);
    require(bool(expression), "supported expression was not parsed");
    sameTree(expression, tokens, found->second.tree);
    require(position == found->second.next, "expression committed the wrong token ordinal");
    if (text == chain(100) + ";")
        require(nodes(expression) == 199 && expression->depth == 100, "100 terms did not yield 199 Aurora nodes");
    ++cases;
}
void rejected(const std::string &text, Stop stop = Stop::semicolon) {
    context = text;
    const auto tokens = aurora::lex(text, "typed-rejection.au"), before = tokens;
    const auto found = errorExpectations.find(fixtureKey(tokens));
    require(found != errorExpectations.end(), "missing explicit rejection fixture");
    std::size_t position = 0;
    expectError(tokens, found->second, [&] {
        aurora::parseHostedExpression(tokens, position, stop);
    });
    require(position == 0 && tokens.size() == before.size(), "rejection changed its caller cursor/tokens");
    for (std::size_t index = 0; index < tokens.size(); ++index)
        sameToken(tokens[index], before[index]);
    ++cases;
}

void bodySyntax() {
    const auto inner = namedArgument("Box", {aurora::TypeKind::I64});
    const auto box = namedType("Box", {inner});
    const std::vector<std::pair<std::string, std::vector<StatementAst>>> fixtures{
        {"{}", {}},
        {"{{}}", {{1, "block"}}},
        {"{i64 x=1;const u8 y=2u8;return x;}",
         {local(1, 2, aurora::Type::I64, true, number(4)),
          local(6, 8, aurora::Type::U8, false, number(10)),
          {12, "return", name(13)}}},
        {"{x=1;obj.field=2;a[0]=3;f();}",
         {{.token = 1, .kind = "assign", .expr = number(3), .name = "x"},
          {.token = 5, .kind = "field_assign", .expr = number(9), .name = "obj", .fieldName = "field"},
          {.token = 11, .kind = "index_assign", .expr = number(16), .target = index(name(11), number(13))},
          {18, "expression", call(18)}}},
        {"{if(true){return 1;}else{while(false){return 2;}}}",
         {{1,
           "if",
           tree("bool", 3),
           {{6, "return", number(7)}},
           {{12, "while", tree("bool", 14), {{17, "return", number(18)}}}}}}},
        {"{static_assert(1);{return (2);}}",
         {{1, "static_assert", number(3)}, {6, "block", {}, {{7, "return", number(9)}}}}},
        {"{array<u8,2> bytes={1u8,2u8};return bytes[0];}",
         {local(1,
                7,
                aurora::Type::array(aurora::TypeKind::U8, 2),
                true,
                tree("array_literal", 9, {number(10), number(12)})),
          {15, "return", index(name(16), number(18))}}},
        {"{Box<Box<i64>> value=Box<Box<i64>>{};return size_of(Box<Box<i64>>);}",
         {local(1, 7, box, true, typed(construct(9, 9), {inner})), {18, "return", reflected(19, box)}}},
        {"{1;if(true){2;}else{}3;while(false){}4;}",
         {{1, "expression", number(1)},
          {3, "if", tree("bool", 5), {{8, "expression", number(8)}}},
          {14, "expression", number(14)},
          {16, "while", tree("bool", 18)},
          {22, "expression", number(22)}}},
        {"{return values[indices[0]];}", {{1, "return", index(name(2), index(name(4), number(6)))}}},
        {"{\n const i64 binding = 1;\n return binding;\n}",
         {local(1, 3, aurora::Type::I64, false, number(5)), {7, "return", name(8)}}},
        // These spellings remain unresolved named types after const. The same
        // first-token control words cannot be reclassified as locals.
        {"{const return x=1;const if y=2;const while z=3;static_assert a=4;}",
         {local(1, 3, aurora::Type("return"), false, number(5)),
          local(7, 9, aurora::Type("if"), false, number(11)),
          local(13, 15, aurora::Type("while"), false, number(17)),
          local(19, 20, aurora::Type("static_assert"), true, number(22))}}};
    for (const auto &[source, expected] : fixtures) {
        context = "explicit body AST " + source;
        const auto tokens = aurora::lex(source, "body-contract.au"), before = tokens;
        std::size_t position = 0;
        sameBody(aurora::parseHostedBody(tokens, position), tokens, expected);
        require(position == tokens.size() - 1, "body did not consume its exact closing brace");
        for (std::size_t index = 0; index < tokens.size(); ++index)
            sameToken(tokens[index], before[index]);
        ++cases;
    }
    // The root consumes exactly its own brace even when a second body follows.
    const auto tokens = aurora::lex("{} {return 1;}", "body-boundary.au");
    std::size_t position = 0;
    require(aurora::parseHostedBody(tokens, position).empty() && position == 2,
            "empty body consumed the following body");
    const auto second = aurora::parseHostedBody(tokens, position);
    sameBody(second, tokens, {{3, "return", number(4)}});
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
        std::vector<StatementAst> expected;
        if (function) {
            expected = {
                local(begin + 1,
                      begin + 8,
                      namedType("Pair", {typeArgument, otherArgument}),
                      false,
                      typed(call(begin + 10, {name(begin + 17), name(begin + 19)}), {typeArgument, otherArgument})),
                {begin + 22,
                 "return",
                 binary(begin + 27, reflected(begin + 23, parameter), reflected(begin + 28, otherParameter))}};
        } else {
            expected = {local(begin + 1, begin + 7, dependentArray, true, tree("array_literal", begin + 9)),
                        {begin + 12, "return", reflected(begin + 13, parameter)}};
        }
        auto position = begin;
        sameBody(aurora::parseHostedBody(tokens, position, captured), tokens, expected);
        require(position == begin + aurora::lex(body).size() - 1, "context body consumed a declaration delimiter");
        const auto program = checkedProgram(tokens);
        if (function) {
            require(program.functionTemplates.size() == 1, "function-template body fixture was omitted");
            sameBody(program.functionTemplates.front().body, tokens, expected);
        } else {
            require(program.templates.size() == 1 && program.templates.front().methods.size() == 1,
                    "class-template body fixture was omitted");
            sameBody(program.templates.front().methods.front().body, tokens, expected);
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
        expectError(tokens, {test.message, test.token}, [&] {
            aurora::parseHostedBody(tokens, position);
        });
        require(position == 0, "body rejection committed cursor");
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
        expectError(
            tokens,
            {"block nesting exceeds 128", kind == "block" ? 128u : 640u, 0, aurora::DiagnosticCode::NestingLimit},
            [&] {
                aurora::parseHostedBody(tokens, position);
            });
        require(position == 0, "129-block body committed cursor");
        ++cases;
    }
}

void diagnosticExpectations() {
    returnedErrors = {{{"expected expression", 1}, {";", ":;", "];", ",;"}},
                      {{"expected expression", 3}, {"1 + ;", "1 +", "f(;", "f(,);", "a[;", "a[];"}},
                      {{"expected ')'", 4}, {"(1 + 2;"}},
                      {{"expected ';'", 1}, {"1 2;", "1:2;", "1]2;", "1,2;", "1(2);", "true(2);"}},
                      {{"expected expression", 5}, {"(1) + ;", "f(1,);"}},
                      {{"expected ';'", 3}, {"(1)(2);"}},
                      {{"expected ')'", 3}, {"f(1;", "f(1 2);"}},
                      {{"expected identifier", 2}, {"a.;", "a..b;", "name::;"}},
                      {{"reserved identifier", 2}, {"a.true;", "name::true;"}},
                      {{"reserved builtin storage name", 2}, {"a.array;", "a.builtin;", "name::builtin;"}},
                      {{"reserved compiler identifier prefix: __au_", 2}, {"a.__au_private;", "name::__au_x;"}},
                      {{"expected ']'", 3}, {"a[1;", "a[1);", "a[1,2];"}},
                      {{"expected ';'", 4}, {"f(1)(2);"}}};
    typedErrors = {
        {{"expected '>'", 3}, {"f<T)>(0);", "f<T]>(0);", "f<T:>(0);", "f< T // malformed trivia\n ) >(0);"}},
        {{"expected identifier", 2}, {"f<>(0);"}},
        {{"expected identifier", 4}, {"f<i64,>(0);"}},
        {{"expected '>'", 4}, {"(f<T)>(0);", "{f<T)>(0)};"}},
        {{"expected '>'", 8}, {"Box{.value=f<T)>(0)};", "size_of(builtin::span<const u8>>);"}},
        {{"template arguments are limited to one or two types or capacity literals", 6}, {"f<i64,u8,bool>(0);"}},
        {{"capacity template arguments must be decimal literals from 1 to 64", 3},
         {"f<0>(0);", "f<65>(0);", "f<1u64>(0);", "f<18446744073709551616>(0);"}},
        {{"template arguments require scalar, named class or enum types, or capacities from 1 to 64", 2},
         {"f<true>(0);",
          "f<false>(0);",
          "f<own>(0);",
          "f<ref>(0);",
          "f<mutref>(0);",
          "f<array>(0);",
          "f<builtin>(0);"}},
        {{"reserved identifier", 2}, {"f<fn>(0);"}},
        {{"reserved identifier", 4}, {"f<ns::true>(0);"}},
        {{"reserved compiler identifier prefix: __au_", 2}, {"f<__au_private>(0);"}},
        {{"expected type name", 3}, {"size_of();", "size_of(123);"}},
        {{"unsupported or reserved type spelling", 2}, {"size_of(fn);"}},
        {{"expected ')'", 3}, {"size_of(i64,u8);"}},
        {{"expected '<'", 3}, {"size_of(own);"}},
        {{"expected 'i64'", 4}, {"size_of(own<u8>);"}},
        {{"expected '>'", 5}, {"size_of(ref<i64>>);", "size_of(mutref<i64);"}},
        {{"expected '::'", 3}, {"size_of(builtin);"}},
        {{"expected 'array'", 4}, {"size_of(builtin::unknown);"}},
        {{"expected 'const'", 6}, {"size_of(builtin::span<u8>);"}},
        {{"expected 'u8'", 7}, {"size_of(builtin::span<const i64>);"}},
        {{"expected ','", 5}, {"size_of(array<i64>);"}},
        {{"array elements require i64, u64, u8, bool or a concrete copied class", 8}, {"size_of(array<own<i64>,1>);"}},
        {{"array elements require i64, u64, u8, bool or a concrete copied class", 10},
         {"size_of(array<array<i64,1>,1>);"}},
        {{"array length requires a decimal integer literal between 1 and 4096", 7},
         {"size_of(array<i64,0>);",
          "size_of(array<i64,4097>);",
          "size_of(array<i64,1u64>);",
          "size_of(array<i64,N>);"}},
        {{"class-element array capacity must be between 1 and 64", 8}, {"size_of(array<Class,65>);"}},
        {{"owned values require a named concrete copied class", 7}, {"size_of(builtin::OwnedValues<i64>);"}},
        {{"owned values require a named concrete copied class", 9, 1}, {"size_of(builtin::OwnedValues<Box<i64>>);"}},
        {{"template arguments are limited to one or two types or capacity literals", 8},
         {"size_of(Box<i64,u8,bool>);"}},
        {{"expected identifier", 6}, {"size_of(Box<i64,>);"}},
        {{"capacity template arguments must be decimal literals from 1 to 64", 5}, {"size_of(Box<0>);"}},
        {{"array elements require i64, u64, u8, bool or a concrete copied class", 7},
         {"size_of(array<builtin::ConsolePutResult,2>);", "size_of(array<builtin::DisplayCompletion,2>);"}},
        {{"owned values require a named concrete copied class", 9},
         {"size_of(builtin::OwnedValues<builtin::EventPollResult>);"}}};
    aggregateErrors = {{{"expected expression", 2}, {"{,};"}},
                       {{"expected expression", 4}, {"{1,};"}},
                       {{"expected '}'", 2}, {"{1 2};", "{1;", "{1];", "{1)};"}},
                       {{"expected ';'", 5}, {"{1,2"}},
                       {{"expected '.'", 2}, {"Box{value=1};"}},
                       {{"expected identifier", 3}, {"Box{..value=1};", "Box{.1=1};"}},
                       {{"reserved identifier", 3}, {"Box{.true=1};"}},
                       {{"reserved builtin storage name", 3}, {"Box{.array=1};", "Box{.builtin=1};"}},
                       {{"reserved compiler identifier prefix: __au_", 3}, {"Box{.__au_private=1};"}},
                       {{"expected '='", 4}, {"Box{.value 1};", "Box{.value==1};"}},
                       {{"expected expression", 6}, {"Box{.value=};"}},
                       {{"expected '.'", 7}, {"Box{.value=1,};"}},
                       {{"expected '}'", 6}, {"Box{.value=1;", "Box{.value=1 .other=2};"}},
                       {{"expected expression", 9}, {"Box{.value={1,}};"}},
                       {{"expected ';'", 2}, {"{}(1);"}},
                       {{"expected ';'", 3}, {"Box{}(1);"}}};
    std::vector<ErrorCases> remaining = {
        {{"expected '>'", 4}, {"{f<T]>(0)}", "{f<T:>(0)}"}},
        {{"expected ')'", 5, 1}, {"size_of(Box<i64>>);"}},
        {{"expected ')'", 7, 1}, {"size_of(array<i64,2>>);", "size_of(builtin::OwnedValues<Value>>);"}},
        {{"expected expression", 1}, {""}},
        {{"expected ']'", 3}, {"a[1"}},
        {{"expected '}'", 2}, {"{1", "{1]}"}},
        {{"expected '>'", 6}, {"f({f<T]>(0)})"}},
        {{"expected ')'", 5}, {"(1 + 2"}},
        {{"expected ')'", 1}, {"1 2", R"("text"(1))", R"("text"[0])"}},
        {{"expected '.'", 8}, {"{Box{.value=1,}}"}}};
    for (const auto *fixtures : {&typedErrors, &returnedErrors, &aggregateErrors, &remaining})
        for (const auto &group : *fixtures)
            for (const auto &source : group.sources) {
                const auto &error = group.expected;
                pinError(source, error.message, error.token, error.half);
                if (source.ends_with(';'))
                    pinError(source.substr(0, source.size() - 1), error.message, error.token, error.half);
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
        sameTree(program.classes[0].methods[0].initializers[0].second, tokens, expected);
        sameTree(program.classes[0].methods[1].body.at(0)->expr, tokens, name(tokens.size() - 6));
    } else {
        require(program.functions.size() == 1 && program.functions[0].body.size() == 1 &&
                    program.functions[0].body[0]->kind == "return",
                "return fixture statement inventory differs");
        sameTree(program.functions[0].body[0]->expr, tokens, expected);
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
    auto precedence = binary(35, binary(33, binary(31, name(30), name(32)), name(34)), name(36));
    precedence = binary(29, binary(27, name(26), name(28)), precedence);
    precedence = binary(25, binary(23, name(22), name(24)), precedence);
    precedence = binary(21, binary(19, binary(17, binary(15, name(14), name(16)), name(18)), name(20)), precedence);
    precedence = binary(13, binary(11, name(10), name(12)), precedence);
    for (const std::size_t op : {9, 7, 5, 3, 1})
        precedence = binary(op, name(op - 1), precedence);
    auto negatives = number(127);
    for (std::size_t token = 127; token-- > 0;)
        negatives = unary(token, negatives);

    const auto deep = namedArgument("A", {namedArgument("B", {namedArgument("C", {namedArgument("D", {K::I64})})})});
    const auto comparison = binary(3, binary(1, tree("bool", 0), name(2)), name(5));
    const auto shiftComparison = binary(1, name(0), binary(3, name(2), name(5)));
    const auto indexedArray = index(array(0, {number(1), number(3)}), number(6));
    // Each independent source/tree pair is exercised directly and retained for
    // the separate program-dispatch contracts below. Token ordinals and source spans stay explicit.
    std::vector<std::pair<std::string, Ast>> fixtures{
        {"1", number(0)},
        {"123u64", number(0)},
        {"255u8", number(0)},
        {"false", tree("bool", 0)},
        {"true", tree("bool", 0)},
        {"name", name(0)},
        {"_value", name(0)},
        {"fn", name(0)},
        {"__au_name", name(0)},
        {"x", name(0)},
        {"'x'", tree("byte", 0)},
        {"'\\n'", tree("byte", 0)},
        {"-1 + ~2 * !false", binary(2, unary(0, number(1)), binary(5, unary(3, number(4)), unary(6, tree("bool", 7))))},
        {"a || b && c | d ^ e & f == g != h < i <= j > k >= l << m >> n + o - p * q / r % s", precedence},
        {"(a + b) * (c - d)", binary(5, binary(2, name(1), name(3)), binary(8, name(7), name(9)))},
        {"(a)", name(1)},
        {"1 + 2", binary(1, number(0), number(2))},
        {"f()", call(0)},
        {"f(1, 2)", call(0, {number(2), number(4)})},
        {"name.member", member(2, name(0))},
        {"name.at(1)", method(2, {name(0), number(4)})},
        {"one::two", name(0, 2)},
        {"a[1]", index(name(0), number(2))},
        {"f(g(1), h(2, 3)) + object.at(index + 1)",
         binary(14,
                call(0, {call(2, {number(4)}), call(7, {number(9), number(11)})}),
                method(17, {name(15), binary(20, name(19), number(21))}))},
        {"Box(42)", call(0, {number(2)})},
        {"move(value)", call(0, {name(2)})},
        {"one :: two(1, other.run()).field[2].at(3)",
         method(18, {index(member(13, call(0, {number(4), method(8, {name(6)})}, 2)), number(15)), number(20)})},
        {"((a)).field", member(6, name(2))},
        {"(a + b)[(i)]", index(binary(2, name(1), name(3)), name(7))},
        {"a[one::index(f(1))].method().field",
         member(17, method(13, {index(name(0), call(2, {call(6, {number(8)})}, 4))}))},
        {"builtin::borrow_bytes(value)", call(0, {name(4)}, 2)},
        {"one::array(1)", call(0, {number(4)}, 2)},
        {"object.size_of()", method(2, {name(0)})},
        {"ns::size_of(i64)", call(0, {name(4)}, 2)},
        {"-object.at(1) + f(2)", binary(7, unary(0, method(3, {name(1), number(5)})), call(8, {number(10)}))},
        {"f(a[1], b.member)", call(0, {index(name(2), number(4)), member(9, name(7))})},
        {"size_of(i64)", reflected(0, T::I64)},
        {"type_id(array<u8,2>)", reflected(0, T::array(K::U8, 2))},
        {"field_count(Box)", reflected(0, T("Box"))},
        {"f(size_of(i64))", call(0, {reflected(2, T::I64)})},
        {R"(f("text"))", call(0, {tree("byte_string", 2)})},
        {R"(ns::f("", "é😀", "\0\xff"))",
         call(0, {tree("byte_string", 4), tree("byte_string", 6), tree("byte_string", 8)}, 2)},
        {R"(object.write("\"\\\n"))", method(2, {name(0), tree("byte_string", 4)})},
        {R"("left" == "right")", binary(1, tree("byte_string", 0), tree("byte_string", 2))},
        {R"(("text")[0])", index(tree("byte_string", 1), number(4))},
        {"(x + 1) * 2", binary(5, binary(2, name(1), number(3)), number(6))},
        {"-x + ns::value", binary(2, unary(0, name(1)), name(3, 5))},
        {"ns::Mode::ready", name(0, 4)},
        {"ns::make(x, a[2]).field", member(12, call(0, {name(4), index(name(6), number(8))}, 2))},
        {"object.at(index + 1)", method(2, {name(0), binary(5, name(4), number(6))})},
        {R"(f("a\0\xff", a[one::index(f(1))]))",
         call(0, {tree("byte_string", 2), index(name(4), call(6, {call(10, {number(12)})}, 8))})},
        {"{1,2}", array(0, {number(1), number(3)})},
        {"{{1,2},{3,4}}", array(0, {array(1, {number(2), number(4)}), array(7, {number(8), number(10)})})},
        {"{f(), object.at(2), a[0]}",
         array(0, {call(1), method(7, {name(5), number(9)}), index(name(12), number(14))})},
        {"{Box{.value=1}, ns::Box{}, {}}",
         array(0, {construct(1, 1, {"value"}, {number(6)}), construct(9, 11), array(15)})},
        {"{Box{.value=type_id(array<u8,2>)}}",
         array(0, {construct(1, 1, {"value"}, {reflected(6, T::array(K::U8, 2))})})},
        {"one :: two::Box{.last=3,.first=1,.middle=2}",
         construct(0, 4, {"last", "first", "middle"}, {number(9), number(14), number(19)})},
        {"Box{.value={1,2}[0]}", construct(0, 0, {"value"}, {shifted(indexedArray, 5)})},
        {"{1,size_of(i64)}", array(0, {number(1), reflected(3, T::I64)})},
        {"Box{.first=1,.second=type_id(array<u8,2>)}",
         construct(0, 0, {"first", "second"}, {number(5), reflected(10, T::array(K::U8, 2))})},
        {"f({1,field_count(Box)})", call(0, {array(2, {number(3), reflected(5, T("Box"))})})},
        {"{Box{.value=f(size_of(i64))}}", array(0, {construct(1, 1, {"value"}, {call(6, {reflected(8, T::I64)})})})},
        {"f<i64>(1)", typed(call(0, {number(5)}), {K::I64})},
        {"x<y<z>>(a)", typed(call(0, {name(7)}), {namedArgument("y", {namedArgument("z")})})},
        {"f<a<b<c>>>(0)",
         typed(call(0, {number(10)}), {namedArgument("a", {namedArgument("b", {namedArgument("c")})})})},
        {"ns :: make<Pair<i64, u8>>(1)", typed(call(0, {number(11)}, 2), {namedArgument("Pair", {K::I64, K::U8})})},
        {"{f<i64>(1),2}", array(0, {typed(call(1, {number(6)}), {K::I64}), number(9)})},
        {"Box{.first=f<a<b<c>>>(0),.second={x<y<z>>(a)}}",
         construct(
             0,
             0,
             {"first", "second"},
             {typed(call(5, {number(15)}), {namedArgument("a", {namedArgument("b", {namedArgument("c")})})}),
              array(21, {typed(call(22, {name(29)}), {namedArgument("y", {namedArgument("z")})})})})},
        {"f({Box<i64>{.value=1},2})",
         call(0, {array(2, {typed(construct(3, 3, {"value"}, {number(11)}), {K::I64}), number(14)})})},
        {"{1,f<a<b<c>>(0)}",
         array(0,
               {number(1),
                binary(4, name(3), typed(call(5, {number(12)}), {namedArgument("b", {namedArgument("c")})}))})},
        {"f<A<B<C<D<i64>>>>>()", typed(call(0), {deep})},
        {"size_of(A<B<C<D<i64>>>>)", reflected(0, namedType("A", deep.templateArguments))},
        {"A<B<C<D<E<i64>>>>>{}",
         typed(construct(0, 0),
               {namedArgument("B", {namedArgument("C", {namedArgument("D", {namedArgument("E", {K::I64})})})})})}};
    aggregateExpressions = {
        {"{}", array(0)},
        {"{1}", array(0, {number(1)})},
        {"{1,2,3}", array(0, {number(1), number(3), number(5)})},
        {"{{}, {1, {2}}, f(3, {4,5})}",
         array(0,
               {array(1),
                array(4, {number(5), array(7, {number(8)})}),
                call(12, {number(14), array(16, {number(17), number(19)})})})},
        {"{1,2}[0]", indexedArray},
        {"({1,2}).field", member(8, array(1, {number(2), number(4)}))},
        {"{}.size()", method(3, {array(0)})},
        {"ns::Box{}", construct(0, 2)},
        {"one // qualified trivia\n :: two::Box{.last=3,.first=1,.middle=2}",
         construct(0, 4, {"last", "first", "middle"}, {number(9), number(14), number(19)})},
        {"Box{.first=f(1,{2}),.last=Other{.items={3,4}}}",
         construct(0,
                   0,
                   {"first", "last"},
                   {call(5, {number(7), array(9, {number(10)})}),
                    construct(17, 17, {"items"}, {array(22, {number(23), number(25)})})})},
        {"Box{.value=1}.value", member(8, construct(0, 0, {"value"}, {number(5)}))},
        {"Box{.items={1,2}}.items[0]",
         index(member(12, construct(0, 0, {"items"}, {array(5, {number(6), number(8)})})), number(14))},
        {"Box{.items={1,2}}.at({3,4}[0])",
         method(12,
                {construct(0, 0, {"items"}, {array(5, {number(6), number(8)})}),
                 index(array(14, {number(15), number(17)}), number(20))})},
        {"f({}, Box{.value=1}, {f(2),object.at(3)})",
         call(0,
              {array(2),
               construct(5, 5, {"value"}, {number(10)}),
               array(13, {call(14, {number(16)}), method(21, {name(19), number(23)})})})},
        {"f(\"text\", Box{.value=1})", call(0, {tree("byte_string", 2), construct(4, 4, {"value"}, {number(9)})})},
        {"{true < x > (y), a < b >> (c)}", array(0, {shifted(comparison, 1), shifted(shiftComparison, 9)})},
        {"{1,f<T}>(0)", binary(7, array(0, {number(1), binary(4, name(3), name(5))}), number(9))},
        {"Box{.first=true < x > (y),.last=a < b >> (c)}",
         construct(0, 0, {"first", "last"}, {shifted(comparison, 5), shifted(shiftComparison, 16)})},
        {"{Box{}, ns::array{}, object.size_of()}",
         array(0, {construct(1, 1), construct(5, 7), method(13, {name(11)})})}};
    typedExpressions = {
        {"f<i64>()", typed(call(0), {K::I64})},
        {"f<u64,u8>(1,2)", typed(call(0, {number(7), number(9)}), {K::U64, K::U8})},
        {"ns::make<bool,64>(true)", typed(call(0, {tree("bool", 9)}, 2), {K::Bool, capacity(64)})},
        {"f<Box<i64>>()", typed(call(0), {namedArgument("Box", {K::I64})})},
        {"f<Pair<i64,u8>,Box<64>>(1)",
         typed(call(0, {number(14)}), {namedArgument("Pair", {K::I64, K::U8}), namedArgument("Box", {capacity(64)})})},
        {"ns // callee trivia\n :: make<Pair<i64, // argument trivia\n u8>>(1)",
         typed(call(0, {number(11)}, 2), {namedArgument("Pair", {K::I64, K::U8})})},
        {"f<ns::array<u8,16>>(value)", typed(call(0, {name(11)}), {namedArgument("ns::array", {K::U8, capacity(16)})})},
        {"one::two::Box<Pair<u8,16>,Other>{.last=2,.first=1}",
         typed(construct(0, 4, {"last", "first"}, {number(19), number(24)}),
               {namedArgument("Pair", {K::U8, capacity(16)}), namedArgument("Other")})},
        {"f<i64>(type_id(Pair<Box<u8>,i64>)).member[0]",
         index(member(19,
                      typed(call(0, {reflected(5, namedType("Pair", {namedArgument("Box", {K::U8}), K::I64}))}),
                            {K::I64})),
               number(21))},
        {"{f<i64>(1),size_of(array<u8,4096>),Box<u64>{.value=2}}",
         array(0,
               {typed(call(1, {number(6)}), {K::I64}),
                reflected(9, T::array(K::U8, 4096)),
                typed(construct(19, 19, {"value"}, {number(27)}), {K::U64})})},
        {"Box<i64>{.value=field_count(Other)}.value",
         member(14, typed(construct(0, 0, {"value"}, {reflected(8, T("Other"))}), {K::I64}))},
        {"size_of<i64>(u8)", typed(reflected(0, T::U8), {K::I64})},
        {"type_id<8>(Box)", typed(reflected(0, T("Box")), {capacity(8)})},
        {"a < b >> (c)", shiftComparison},
        {"(a) < b > (c)", binary(5, binary(3, name(1), name(4)), name(7))},
        {"true < x > (y)", comparison},
        {"f<a<b<c>>(0)", binary(1, name(0), typed(call(2, {number(9)}), {namedArgument("b", {namedArgument("c")})}))},
        {"{1,f<T}>(0)", binary(7, array(0, {number(1), binary(4, name(3), name(5))}), number(9))}};
    for (const auto *group : {&fixtures, &aggregateExpressions, &typedExpressions})
        for (const auto &[source, expected] : *group) {
            pin(source, expected);
            supported(source + ";");
        }
    for (const auto count : {100, 128})
        pin(chain(count), sum(count));
    pin(std::string(127, '(') + "1" + std::string(127, ')'), number(127));
    pin(std::string(127, '-') + "1", negatives);
    pinExact("target = 2;", name(0), 1);
    pinExact("a[1] = 2;", index(name(0), number(2)), 4);
    pinExact("{1,2}[0] = 3;", indexedArray, 8);
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
    require(tokens.at(position).text == (stop == Stop::close_parenthesis ? ")" : ";"),
            "bootstrap expression committed the wrong delimiter");
    ++cases;
}
void bootstrapStatements(const std::vector<aurora::Token> &tokens,
                         const std::vector<aurora::StatementPtr> &statements,
                         std::size_t &strings) {
    for (const auto &statement : statements) {
        if (statement->expr && statement->expr->op == "byte_string") {
            hostedRoot(tokens, tokenAt(tokens, statement->expr->token), Stop::semicolon, statement->expr);
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
            hostedRoot(tokens, position + 1, Stop::close_parenthesis, expression);
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
std::size_t wholeCallables = 0, wholeFields = 0;
void bootstrapDeclarationTypes(const std::vector<aurora::Token> &, const aurora::Program &, std::size_t);
void bootstrapPreambleEnums(const std::vector<aurora::Token> &, const aurora::Program &, std::size_t);
void bootstrapContainers(const std::vector<aurora::Token> &, const aurora::Program &, std::size_t);
void libraryContainers(const std::vector<aurora::Token> &, const aurora::Program &, bool);
void bootstrapSources(char **paths) {
    std::size_t initializers = 0, strings = 0, newInitializers = 0;
    std::size_t expectedInitializers = 0, expectedStrings = 0;
    const std::array<std::string, 3> modules{
        "aurora.compiler.lexer", "aurora.compiler.syntax_arena", "aurora.compiler.parser"};
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
        bootstrapDeclarationTypes(tokens, program, i);
        bootstrapPreambleEnums(tokens, program, i);
        bootstrapContainers(tokens, program, i);
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
    const auto expression = aurora::parseHostedExpression(tokens, position, Stop::constructor_braces);
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
            const auto hosted = aurora::parseHostedExpression(tokens, position, Stop::semicolon);
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
            hostedRoot(tokens, start, assertion ? Stop::close_parenthesis : Stop::semicolon, statement->expr);
            ++roots;
            ++cases;
        }
        consumerReflection(tokens, statement->body, roots);
        consumerReflection(tokens, statement->other, roots);
    }
}
void consumerSources(const std::array<const char *, 6> &paths) {
    const std::array<std::string, 6> modules{
        "std.array", "console.session_files", "kernel_graphical_console",
        "fs.xfs_sector", "examples.class_values", "console.line"};
    const std::array<AggregateRoots, 6> expectedAggregates{
        AggregateRoots{},
        AggregateRoots{},
        AggregateRoots{{"text", 61}, {"text", 27}, {"text", 63}, {"text", 19}, {"blank", 1}, {"text", 22}},
        AggregateRoots{{"bytes", 512}},
        AggregateRoots{{"current", 2}},
        AggregateRoots{}};
    const std::array<AggregateRoots, 6> expectedBraces{
        AggregateRoots{{"elements", 0}},
        AggregateRoots{{"bytes", 0}, {"records", 4}},
        AggregateRoots{{"desired", 0}, {"committed", 0}},
        AggregateRoots{},
        AggregateRoots{},
        AggregateRoots{{"bytes", 0}}};
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
        if (index == 0)
            libraryContainers(tokens, program, false);
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
            Stop stop = Stop::semicolon;
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
                stop = Stop::close_parenthesis;
            } else if (statement->kind == "assign" || statement->kind == "field_assign" ||
                       statement->kind == "index_assign") {
                const auto target = aurora::parseHostedExpression(tokens, start, Stop::assignment, typeContext);
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
                tokens, position, braces ? Stop::constructor_braces : Stop::close_parenthesis, typeContext);
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
std::vector<std::string> typedProgram(const std::vector<aurora::Token> &tokens, const aurora::Program &program) {
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
std::vector<std::string> typedProgram(const std::vector<aurora::Token> &tokens) {
    return typedProgram(tokens, checkedProgram(tokens));
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
        const auto program = checkedProgram(tokens);
        require(program.moduleName == modules[index], "unexpected typed consumer source/module order");
        if (index == 0)
            libraryContainers(tokens, program, true);
        require(typedProgram(tokens, program) == expected[index], "typed consumer roots changed order or were omitted");
    }
}

// Type fixtures name their expected values independently of the grammar. Type's
// operator== omits presentation/provenance metadata, so check those fields too.
void sameType(const aurora::Type &actual, const aurora::Type &expected) {
    require(actual == expected && actual.displayName == expected.displayName &&
                actual.resolvedClass == expected.resolvedClass,
            "declaration type structure/presentation/provenance differs");
}
aurora::Type displayedType(aurora::Type type, std::string display) {
    type.displayName = std::move(display);
    return type;
}
void unchangedTokens(const std::vector<aurora::Token> &actual, const std::vector<aurora::Token> &before) {
    require(actual.size() == before.size(), "type parse changed token cardinality");
    for (std::size_t index = 0; index < before.size(); ++index)
        sameToken(actual[index], before[index]);
}
void typeFixture(const std::string &source,
                 const aurora::Type &expected,
                 std::size_t start,
                 std::size_t next,
                 bool half = false,
                 const std::vector<std::size_t> &typeParameters = {},
                 const std::vector<std::size_t> &capacityParameters = {},
                 bool functionTemplate = false) {
    context = "explicit declaration type " + source;
    const auto tokens = aurora::lex(source, "declaration-type.au");
    const auto before = tokens;
    Context captured;
    for (const auto ordinal : typeParameters)
        captured.typeParameters.push_back(tokens.at(ordinal));
    for (const auto ordinal : capacityParameters)
        captured.capacityParameters.push_back(tokens.at(ordinal));
    captured.functionTemplate = functionTemplate;
    const Cursor position{start};
    const auto parsed = aurora::parseHostedType(tokens, position, captured);
    sameType(parsed.type, expected);
    require(parsed.next.ordinal == next && parsed.next.half == unsigned(half),
            "type returned the wrong first unconsumed token/half");
    require(position.ordinal == start && position.half == 0, "type changed its input cursor");
    if (half)
        require(tokens.at(next).text == ">>", "residual fixture has no original shared closer");
    unchangedTokens(tokens, before);
    require(before.front().span.source->text == source && tokens.front().span.source == before.front().span.source,
            "declaration type changed its immutable source snapshot");
    // Re-lexing that same snapshot must still expose the original unsplit tokens.
    const auto retained = aurora::lex(before.front().span.source);
    require(retained.size() == before.size(), "immutable type source tokenization changed");
    for (std::size_t index = 0; index < retained.size(); ++index)
        sameToken(retained[index], before[index]);
    ++cases;
}
void typeRejection(const std::string &source,
                   const ExpectedError &expected,
                   std::size_t start = 0,
                   const std::vector<std::size_t> &typeParameters = {},
                   const std::vector<std::size_t> &capacityParameters = {},
                   bool functionTemplate = false) {
    context = "explicit declaration type rejection " + source;
    const auto tokens = aurora::lex(source, "declaration-type-error.au");
    const auto before = tokens;
    Context captured;
    for (const auto ordinal : typeParameters)
        captured.typeParameters.push_back(tokens.at(ordinal));
    for (const auto ordinal : capacityParameters)
        captured.capacityParameters.push_back(tokens.at(ordinal));
    captured.functionTemplate = functionTemplate;
    const Cursor position{start};
    expectError(
        before,
        expected,
        [&] {
            aurora::parseHostedType(tokens, position, captured);
        },
        start);
    require(position.ordinal == start && position.half == 0, "failed declaration type committed its cursor");
    unchangedTokens(tokens, before);
    require(before.front().span.source->text == source, "failed declaration type changed source snapshot");
    ++cases;
}
// Independent type values shared by reflection and declaration profiles. Only
// declaration conversion promises presentation/provenance metadata; sameType
// checks that metadata in addition to the structural equality used by reflection.
std::vector<std::pair<std::string, aurora::Type>> typeExpectations() {
    using K = aurora::TypeKind;
    using T = aurora::Type;
    const auto capacity = aurora::TemplateArgument::capacity;
    const auto sample = displayedType(T("__au_console_sample"), "builtin::ConsoleSample");
    const auto event = displayedType(T("__au_iommu_event_sample"), "builtin::IommuEventSample");
    return {
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
        {"builtin::ConsolePutResult",
         displayedType(T::enumeration("__au_console_put_result"), "builtin::ConsolePutResult")},
        {"builtin::ConsoleCompletion",
         displayedType(T::enumeration("__au_console_completion"), "builtin::ConsoleCompletion")},
        {"builtin::DisplaySession", T::DisplaySession},
        {"builtin::DisplayPutResult",
         displayedType(T::enumeration("__au_display_put_result"), "builtin::DisplayPutResult")},
        {"builtin::DisplayCompletion",
         displayedType(T::enumeration("__au_display_completion"), "builtin::DisplayCompletion")},
        {"builtin::IommuEventSession", T::IommuEventSession},
        {"builtin::IommuEventSample", event},
        {"builtin::EventPollResult",
         displayedType(T::enumeration("__au_event_poll_result"), "builtin::EventPollResult")},
        {"builtin::EventAckResult", displayedType(T::enumeration("__au_event_ack_result"), "builtin::EventAckResult")},
        {"builtin::EventIntakeCompletion",
         displayedType(T::enumeration("__au_event_intake_completion"), "builtin::EventIntakeCompletion")}};
}
void declarationTypeSyntax() {
    using K = aurora::TypeKind;
    using T = aurora::Type;
    const auto capacity = aurora::TemplateArgument::capacity;
    auto fixtures = typeExpectations();
    // Declaration-only trivia, nested names and first-component acceptance.
    const std::vector<std::pair<std::string, T>> declarationOnly{
        {"ns // retained trivia\n :: Name", T("ns::Name")},
        {"ns::Box<other::array<bool,1>>",
         namedType("ns::Box", {namedArgument("other::array", {K::Bool, capacity(1)})})},
        {"true", T("true")},
        {"return", T("return")},
        {"__au_private", T("__au_private")}};
    fixtures.insert(fixtures.end(), declarationOnly.begin(), declarationOnly.end());
    for (const auto &[spelling, expected] : fixtures) {
        const auto count = aurora::lex(spelling).size() - 1;
        typeFixture(spelling, expected, 0, count);
        typeFixture("prefix\n " + spelling + " value, suffix", expected, 1, count + 1);
    }
    // Parse exactly one type. An unrelated malformed template-looking suffix
    // must not be scanned by the expression template-candidate prepass.
    typeFixture("i64 f<T)> broken", T::I64, 0, 1);
    typeFixture("Box<i64> f<T)> broken", namedType("Box", {K::I64}), 0, 4);
    typeFixture("Box<i64>> rest", namedType("Box", {K::I64}), 0, 3, true);
    typeFixture("Box<i64>>", namedType("Box", {K::I64}), 0, 3, true);
    typeFixture("array<i64,2>> rest", T::array(K::I64, 2), 0, 5, true);
    typeFixture("builtin::OwnedValues<Item>> rest", T::ownedValues(T("Item")), 0, 5, true);
    typeFixture("Box<Pair<i64,u8>>> rest", namedType("Box", {namedArgument("Pair", {K::I64, K::U8})}), 0, 8);
    typeFixture("prefix\n Box // first\n <i64 // close\n >> rest", namedType("Box", {K::I64}), 1, 4, true);
    typeFixture("A<B<C<D<i64>>>> next",
                namedType("A", {namedArgument("B", {namedArgument("C", {namedArgument("D", {K::I64})})})}),
                0,
                11);
    context = "successive standalone type cursors";
    const auto tokens = aurora::lex("i64 u8 Box<i64> array<u8,2>", "type-sequence.au"), before = tokens;
    Cursor at;
    for (const auto &[expected, next] : std::vector<std::pair<T, std::size_t>>{
             {T::I64, 1}, {T::U8, 2}, {namedType("Box", {K::I64}), 6}, {T::array(K::U8, 2), 12}}) {
        const auto parsed = aurora::parseHostedType(tokens, at);
        sameType(parsed.type, expected);
        require(parsed.next.ordinal == next && parsed.next.half == 0, "successive type parse lost its cursor");
        at = parsed.next;
        unchangedTokens(tokens, before);
    }
    ++cases;
}
void repeatedResidualType() {
    context = "repeated reads beginning at an explicit residual closer";
    const auto tokens = aurora::lex("prefix Box<i64>> next", "residual-type.au"), before = tokens;
    const auto first = aurora::parseHostedType(tokens, Cursor{1});
    sameType(first.type, namedType("Box", {aurora::TypeKind::I64}));
    require(first.next.ordinal == 4 && first.next.half == 1 && tokens.at(4).text == ">>",
            "first type did not return exactly one residual closer without rewriting tokens");
    for (int repetition = 0; repetition < 2; ++repetition) {
        expectError(tokens, {"expected type name", 5}, [&] {
            aurora::parseHostedType(tokens, first.next);
        });
        require(first.next.ordinal == 4 && first.next.half == 1, "residual failure changed its cursor value");
        unchangedTokens(tokens, before);
    }
    const auto next = aurora::parseHostedType(tokens, Cursor{5});
    sameType(next.type, aurora::Type("next"));
    require(next.next.ordinal == 6 && next.next.half == 0 &&
                tokens.front().span.source->text == "prefix Box<i64>> next",
            "reading beyond a residual closer changed retained source or final cursor");
    unchangedTokens(tokens, before);
    ++cases;
}
void declarationTypeDiagnostics() {
    for (const auto &group : std::vector<ErrorCases>{
             {{"unsupported or reserved type spelling", 0}, {"fn value"}},
             {{"expected type name", 1}, {"123 value"}},
             {{"expected '<'", 1}, {"array;"}},
             {{"expected '>'", 3}, {"own<i64;", "ref<i64>>;"}},
             {{"expected 'i64'", 2}, {"own<u8>;"}},
             {{"expected '::'", 1}, {"builtin;"}},
             {{"expected 'array'", 2}, {"builtin::unknown;"}},
             {{"expected 'const'", 4}, {"builtin::span<u8>;"}},
             {{"expected 'u8'", 5}, {"builtin::span<const i64>;"}},
             {{"expected '>'", 6}, {"builtin::span<const u8>>;"}},
             {{"expected ','", 3}, {"array<i64>;"}},
             {{"array elements require i64, u64, u8, bool or a concrete copied class", 6}, {"array<own<i64>,1>;"}},
             {{"array length requires a decimal integer literal between 1 and 4096", 5},
              {"array<i64,0>;", "array<i64,4097>;", "array<i64,1u64>;", "array<i64,N>;"}},
             {{"class-element array capacity must be between 1 and 64", 6}, {"array<Class,65>;"}},
             {{"class-element array capacity must be between 1 and 64", 5, 1}, {"array<Class,65>>;"}},
             {{"owned values require a named concrete copied class", 5}, {"builtin::OwnedValues<i64>;"}},
             {{"owned values require a named concrete copied class", 7, 1}, {"builtin::OwnedValues<Box<i64>>;"}},
             {{"template arguments are limited to one or two types or capacity literals", 6}, {"Box<i64,u8,bool>;"}},
             {{"template arguments require scalar, named class or enum types, or capacities from 1 to 64", 2},
              {"Box<own>;"}},
             {{"capacity template arguments must be decimal literals from 1 to 64", 3},
              {"Box<0>;", "Box<65>;", "Box<18446744073709551616>;"}},
             {{"expected identifier", 4}, {"Box<i64,>;"}},
             {{"reserved identifier", 2}, {"ns::true;"}},
             {{"reserved compiler identifier prefix: __au_", 2}, {"ns::__au_private;"}},
             {{"template-id nesting exceeds 4", 9, 0, aurora::DiagnosticCode::NestingLimit}, {"A<B<C<D<E<i64>>>>>;"}}})
        for (const auto &source : group.sources) {
            typeRejection(source, group.expected);
            typeRejection("prefix\n " + source, group.expected, 1);
        }
    for (const std::size_t depth : {63, 64}) {
        std::string type = "i64";
        for (std::size_t index = 0; index < depth; ++index)
            type = "array<" + type + ",1>";
        typeRejection(type + ";",
                      {depth == 63 ? "array elements require i64, u64, u8, bool or a concrete copied class"
                                   : "type nesting exceeds 64",
                       depth == 63 ? 130U : 128U,
                       0,
                       depth == 63 ? aurora::DiagnosticCode::UnexpectedToken : aurora::DiagnosticCode::NestingLimit});
    }
    // These fail only after the grammar split >> internally. The caller must
    // retain the complete original token and cursor when conversion rejects.
    rejectedProgram("module type_errors; class C{", "Box<i64>> value;};", "", {"expected identifier", 3, 1});
    rejectedProgram("module type_errors; auto f(", "Box<i64>> value)->i64{}", "", {"expected identifier", 3, 1});
    rejectedProgram("module type_errors; auto f()->", "Box<i64>>{}", "", {"expected '{'", 3, 1});
    rejectedProgram("module type_errors; class C{C(", "Box<i64>> value){} };", "", {"expected identifier", 3, 1});
    rejectedProgram(
        "module type_errors; class C{auto f(", "Box<i64>> value)->i64{} };", "", {"expected identifier", 3, 1});
    rejectedProgram("module type_errors; class C{auto f()->", "Box<i64>>{} };", "", {"expected '{'", 3, 1});
    for (const auto &spelling : {std::string("own<i64>"), std::string("builtin::ByteRegion")}) {
        context = "full rejected field type span " + spelling;
        const auto prefix = "module field_span;class C{";
        const auto tokens = aurora::lex(prefix + spelling + " value;};", "field-type-span.au");
        const auto first = aurora::lex(prefix).size() - 1;
        const auto count = aurora::lex(spelling).size() - 1;
        auto expectedSpan = tokens.at(first).span;
        expectedSpan.end = tokens.at(first + count - 1).span.end;
        std::optional<aurora::Diagnostic> diagnostic;
        try {
            aurora::Parser(tokens).parse();
        } catch (const aurora::Error &error) {
            diagnostic = error.diagnostic;
        }
        require(diagnostic && diagnostic->code == aurora::DiagnosticCode::UnsupportedFieldType &&
                    diagnostic->message ==
                        "unsupported class field type '" + spelling +
                            "': class fields require scalar, class, private fixed-array or private owned-byte storage",
                "rejected field lost its existing declaration diagnostic");
        sameSpan(diagnostic->span, expectedSpan);
        ++cases;
    }
}
void declarationTypeContexts() {
    using K = aurora::TypeKind;
    using T = aurora::Type;
    auto parameter = T(K::Parameter), other = T(K::Parameter);
    parameter.className = "T";
    other.className = "U";
    auto argument = namedArgument("T"), otherArgument = namedArgument("U");
    argument.type = otherArgument.type = K::Parameter;
    auto dependent = T::array(parameter, 0);
    dependent.lengthParameter = "N";
    const std::string function = "template<Value T,Value U> ";
    const std::string definition = "template<Scalar T,i64 N> ";
    typeFixture(function + "T value", parameter, 8, 9, false, {3, 6}, {}, true);
    typeFixture(function + "U value", other, 8, 9, false, {3, 6}, {}, true);
    typeFixture(
        function + "Pair<T,U> value", namedType("Pair", {argument, otherArgument}), 8, 14, false, {3, 6}, {}, true);
    typeFixture(definition + "array<T,N> value", dependent, 8, 14, false, {3}, {6});
    typeFixture(definition + "T<i64> value", parameter, 8, 9, false, {3}, {6});
    typeFixture(function + "ns::T value", T("ns::T"), 8, 11, false, {3, 6}, {}, true);
    typeRejection(definition + "Box<i64> value",
                  {"template-id references inside template definitions are not supported", 1},
                  8,
                  {3},
                  {6});
    for (const auto &[source, error] : std::vector<std::pair<std::string, ExpectedError>>{
             {"Box<Box<T>> value", {"nested dependent template arguments are not supported", 5}},
             {"Box<T<i64>> value", {"nested dependent template arguments are not supported", 3}},
             {"builtin::OwnedValues<T> value", {"owned values require a named concrete copied class", 5}}})
        typeRejection(function + source, error, 8, {3, 6}, {}, true);
    context = "whole declaration parameter/result/field context expectations";
    const auto source = "export module declarations;"
                        "template<Value T,Value U> auto choose(T x,U y)->Pair<T,U>{return Pair<T,U>(x,y);}"
                        "template<Scalar T,i64 N> class Buffer{array<T,N> data;public:"
                        "Buffer(T value):data{value}{} auto read(T index)->T{return index;}};"
                        "class Concrete{Box<Pair<i64,u8>> value;builtin::OwnedValues<Item> items;public:"
                        "Concrete(Box<Pair<i64,u8>> input):value(input),items(make_items()){}"
                        "auto read(u8 index) const ->Box<Pair<i64,u8>>{return value;}};";
    const auto tokens = aurora::lex(source, "declaration-contexts.au");
    const auto program = checkedProgram(tokens);
    require(program.functionTemplates.size() == 1 && program.templates.size() == 1 && program.classes.size() == 1,
            "declaration context fixture lost a declaration");
    const auto &choose = program.functionTemplates.front();
    require(choose.params.size() == 2, "function template lost a parameter");
    sameType(choose.params[0].type, parameter);
    sameType(choose.params[1].type, other);
    sameType(choose.result, namedType("Pair", {argument, otherArgument}));
    const auto &buffer = program.templates.front();
    require(buffer.fields.size() == 1 && buffer.methods.size() == 2 && buffer.methods[0].constructor &&
                buffer.methods[0].params.size() == 1 && buffer.methods[1].params.size() == 1,
            "template class lost field/constructor/method declarations");
    sameType(buffer.fields[0].type, dependent);
    sameType(buffer.methods[0].params[0].type, parameter);
    sameType(buffer.methods[1].params[0].type, parameter);
    sameType(buffer.methods[1].result, parameter);
    const auto nested = namedType("Box", {namedArgument("Pair", {K::I64, K::U8})});
    const auto &concrete = program.classes.front();
    require(concrete.fields.size() == 2 && concrete.methods.size() == 2 && concrete.methods[0].params.size() == 1 &&
                concrete.methods[1].params.size() == 1 && concrete.methods[1].receiverConst,
            "concrete class lost declaration types");
    sameType(concrete.fields[0].type, nested);
    sameType(concrete.fields[1].type, T::ownedValues(T("Item")));
    sameType(concrete.methods[0].params[0].type, nested);
    sameType(concrete.methods[1].params[0].type, T::U8);
    sameType(concrete.methods[1].result, nested);
    ++cases;
}

// Independent declaration trees: token ordinals are relative to the source row,
// so the same expectation checks standalone and namespace/class-wrapped input.
struct ParameterAst {
    std::size_t binding;
    aurora::Type type;
    bool constant = false;
    std::size_t borrow = std::string::npos;
};
struct CallableAst {
    std::size_t name = 1;
    aurora::Type result = aurora::Type::I64;
    std::vector<ParameterAst> parameters = {};
    std::vector<StatementAst> body = {};
    std::vector<std::pair<std::size_t, Ast>> initializers = {};
    bool constant = false;
};
void sameCallableTree(const aurora::ParsedCallable &parsed,
                      const std::vector<aurora::Token> &tokens,
                      const CallableAst &expected,
                      Stop stop,
                      std::size_t base = 0) {
    const auto &actual = parsed.function;
    const auto &name = tokens.at(base + expected.name);
    require(actual.name == name.text && actual.constructor == (stop == Stop::constructor) &&
                actual.receiverConst == expected.constant && actual.params.size() == expected.parameters.size() &&
                actual.initializers.size() == expected.initializers.size(),
            "callable shape/order differs");
    sameToken(actual.token, name);
    sameType(actual.result, expected.result);
    for (std::size_t index = 0; index < expected.parameters.size(); ++index) {
        const auto &a = actual.params[index];
        const auto &b = expected.parameters[index];
        const bool borrowed = b.borrow != std::string::npos;
        require(a.name == tokens.at(base + b.binding).text && a.borrowed == borrowed && a.borrowConst == b.constant,
                "ordered parameter binding/reference/const differs");
        sameType(a.type, b.type);
        sameSpan(a.borrowSpan, borrowed ? tokens.at(base + b.borrow).span : aurora::SourceSpan{});
    }
    for (std::size_t index = 0; index < expected.initializers.size(); ++index) {
        sameToken(actual.initializers[index].first, tokens.at(base + expected.initializers[index].first));
        sameTree(actual.initializers[index].second, tokens, expected.initializers[index].second, base);
    }
    sameBody(actual.body, tokens, expected.body, base);
}
// Whole/direct equality is dispatch evidence, separate from the literal trees.
void sameCallable(const aurora::Function &a, const aurora::Function &b) {
    require(a.name == b.name && a.constructor == b.constructor && a.receiverConst == b.receiverConst &&
                a.params.size() == b.params.size() && a.initializers.size() == b.initializers.size(),
            "whole/direct callable shape differs");
    sameToken(a.token, b.token);
    sameType(a.result, b.result);
    for (std::size_t index = 0; index < a.params.size(); ++index) {
        require(a.params[index].name == b.params[index].name && a.params[index].borrowed == b.params[index].borrowed &&
                    a.params[index].borrowConst == b.params[index].borrowConst,
                "whole/direct parameter differs");
        sameType(a.params[index].type, b.params[index].type);
        sameSpan(a.params[index].borrowSpan, b.params[index].borrowSpan);
    }
    for (std::size_t index = 0; index < a.initializers.size(); ++index) {
        sameToken(a.initializers[index].first, b.initializers[index].first);
        sameExpression(a.initializers[index].second, b.initializers[index].second);
    }
    sameStatements(a.body, b.body);
}
void callableSyntax() {
    using T = aurora::Type;
    const auto nested = namedType("Box", {namedArgument("Box", {aurora::TypeKind::I64})});
    struct Fixture {
        std::string source;
        Stop stop;
        CallableAst expected;
    };
    for (const auto &fixture : std::vector<Fixture>{
             {"auto empty()->i64{}", Stop::function, {}},
             {"auto mix(i64 first,u8 second,bool third,u64 fourth)->bool{return third;}",
              Stop::function,
              {.result = T::Bool,
               .parameters = {{4, T::I64}, {7, T::U8}, {10, T::Bool}, {13, T::U64}},
               .body = {{18, "return", name(19)}}}},
             {"auto inspect(const Owner& owner,i64 amount)->i64{return amount;}",
              Stop::function,
              {.parameters = {{6, T("Owner"), true, 5}, {9, T::I64}}, .body = {{14, "return", name(15)}}}},
             {"auto touch(Owner& owner)->Owner{return owner;}",
              Stop::function,
              {.result = T("Owner"), .parameters = {{5, T("Owner"), false, 4}}, .body = {{10, "return", name(11)}}}},
             {"auto events(builtin::ConsoleSession& console,builtin::DisplaySession& display)->i64{return 0;}",
              Stop::function,
              {.parameters = {{7, T::ConsoleSession, false, 6}, {13, T::DisplaySession, false, 12}},
               .body = {{18, "return", number(19)}}}},
             {"auto read(i64 key)const->u8{const u8 byte=2u8;return byte;}",
              Stop::method,
              {.result = T::U8,
               .parameters = {{4, T::I64}},
               .body = {local(10, 12, T::U8, false, number(14)), {16, "return", name(17)}},
               .constant = true}},
             {"auto transfer(builtin::ByteRegion region,builtin::OwnedBytes bytes)->builtin::OwnedBytes{return "
              "move(bytes);}",
              Stop::function,
              {.result = T::OwnedBytes,
               .parameters = {{6, T::ByteRegion}, {11, T::OwnedBytes}},
               .body = {{18, "return", call(19, {name(21)})}}}},
             {"auto view(builtin::span<const u8> input)const->builtin::span<const u8>{return input;}",
              Stop::method,
              {.result = T::ByteSpan,
               .parameters = {{10, T::ByteSpan}},
               .body = {{22, "return", name(23)}},
               .constant = true}},
             {"Box(){}", Stop::constructor, {.name = 0}},
             {"Box(i64 value):first(value),bytes{},last{1u8,2u8}{}",
              Stop::constructor,
              {.name = 0,
               .parameters = {{3, T::I64}},
               .initializers = {{6, name(8)},
                                {11, tree("array_zero", 11)},
                                {15, tree("array_literal", 15, {number(17), number(19)})}}}},
             {"auto nested(Box<Box<i64>> value)->Box<Box<i64>>{return value;}",
              Stop::function,
              {.result = nested, .parameters = {{9, nested}}, .body = {{19, "return", name(20)}}}},
             {"auto nested(Box<Box<i64>> value)->Box<Box<i64>>{return value;}",
              Stop::method,
              {.result = nested, .parameters = {{9, nested}}, .body = {{19, "return", name(20)}}}}})
        for (const bool wrapped : {false, true}) {
            const bool function = fixture.stop == Stop::function;
            const std::string prefix = function ? "export module callable_contract;namespace ns{"
                                                : "export module callable_contract;namespace ns{class Box{public:";
            context = "independent callable tree " + fixture.source;
            const auto tokens =
                           aurora::lex(wrapped ? prefix + fixture.source + (function ? "}" : "};}") : fixture.source,
                                       "callable-contract.au"),
                       before = tokens;
            const auto begin = wrapped ? aurora::lex(prefix).size() - 1 : 0;
            const auto direct = aurora::parseHostedCallable(tokens, Cursor{begin}, fixture.stop);
            require(direct.next.ordinal == begin + aurora::lex(fixture.source).size() - 1 && direct.next.half == 0,
                    "callable consumed the wrong closing delimiter");
            sameCallableTree(direct, tokens, fixture.expected, fixture.stop, begin);
            require(direct.function.scope.empty() && !direct.function.exported && !direct.function.publicAccess &&
                        direct.function.templateParameters.empty() && direct.function.receiverClass.empty(),
                    "grammar adapter acquired declaration-context authority");
            if (wrapped) {
                const auto program = checkedProgram(tokens);
                const auto &items = function ? program.functions : program.classes.at(0).methods;
                require(items.size() == 1 && items[0].scope == "ns" && !items[0].exported &&
                            items[0].publicAccess == !function,
                        "callable dispatch lost scope/access or declaration count");
                sameCallable(items[0], direct.function);
            }
            unchangedTokens(tokens, before);
            ++cases;
        }
    const auto tokens = aurora::lex("1;auto first()->i64{}auto second()->i64{}", "callable-boundary.au");
    const auto first = aurora::parseHostedCallable(tokens, Cursor{2}, Stop::function);
    const auto second = aurora::parseHostedCallable(tokens, first.next, Stop::method);
    require(first.function.name == "first" && first.next.ordinal == 10 && first.next.half == 0 &&
                second.function.name == "second" && second.next.ordinal == tokens.size() - 1 && second.next.half == 0,
            "adjacent callable cursors escaped their declarations");
    ++cases;
}
void callableRejection(const std::string &source, Stop stop, const ExpectedError &expected, bool admission = false) {
    context = "explicit callable diagnostic " + source;
    const auto tokens = aurora::lex(source, "callable-error.au"), before = tokens;
    if (admission) {
        const auto syntax = aurora::parseHostedCallable(tokens, Cursor{}, stop);
        require(syntax.next.ordinal == tokens.size() - 1 && syntax.next.half == 0,
                "standalone callable syntax acquired whole-module admission");
    } else
        expectError(tokens, expected, [&] {
            static_cast<void>(aurora::parseHostedCallable(tokens, Cursor{}, stop));
        });
    unchangedTokens(tokens, before);
    ++cases;
    // Admission fixtures need a complete class so unrelated EOF syntax cannot
    // mask their policy error. Preserve intentionally truncated grammar inputs.
    rejectedProgram(stop == Stop::function ? "module callable_errors;" : "module callable_errors;class Box{",
                    source,
                    admission && stop != Stop::function ? "};" : "",
                    expected);
}
void callableDiagnostics() {
    struct Rejection {
        const char *source;
        Stop stop;
        ExpectedError error;
    };
    for (const auto &test : std::vector<Rejection>{
             {"f()->i64{}", Stop::function, {"expected 'auto'", 0}},
             {"auto", Stop::function, {"expected identifier", 1}},
             {"auto true()->i64{}", Stop::function, {"reserved identifier", 1}},
             {"auto array()->i64{}", Stop::function, {"reserved builtin storage name", 1}},
             {"auto __au_private()->i64{}", Stop::function, {"reserved compiler identifier prefix: __au_", 1}},
             {"auto f{}", Stop::function, {"expected '('", 2}},
             {"auto f(", Stop::function, {"expected type name", 3}},
             {"auto f(i64", Stop::function, {"expected identifier", 4}},
             {"auto f(i64 x", Stop::function, {"expected ')'", 5}},
             {"auto f(i64 x i64 y)->i64{}", Stop::function, {"expected ')'", 5}},
             {"auto f(i64 x,)->i64{}", Stop::function, {"expected type name", 7}},
             {"auto f(fn x)->i64{}", Stop::function, {"unsupported or reserved type spelling", 3}},
             {"auto f(own<u8> x)->i64{}", Stop::function, {"expected 'i64'", 5}},
             {"auto f(i64 true)->i64{}", Stop::function, {"reserved identifier", 4}},
             {"auto f(i64 array)->i64{}", Stop::method, {"reserved builtin storage name", 4}},
             {"auto f(i64 __au_value)->i64{}", Stop::method, {"reserved compiler identifier prefix: __au_", 4}},
             {"auto f()", Stop::function, {"expected '->'", 4}},
             {"auto f()const->i64{}", Stop::function, {"expected '->'", 4}},
             {"auto f()const const->i64{}", Stop::method, {"expected '->'", 5}},
             {"auto f()->", Stop::function, {"expected type name", 5}},
             {"auto f()->i64", Stop::function, {"expected '{'", 6}},
             {"auto f()->i64;", Stop::method, {"expected '{'", 6}},
             {"auto f()->i64{", Stop::function, {"unterminated block", 7}},
             {"auto f()->i64{return 1}", Stop::method, {"expected ';'", 9}},
             {"auto f()->i64{return;}", Stop::function, {"expected expression", 9}},
             {"auto f()->i64{if(true)return 1;}", Stop::function, {"expected '{'", 11}},
             {"auto f(Box<i64>> value)->i64{}", Stop::function, {"expected identifier", 6, 1}},
             {"auto f()->Box<i64>>{}", Stop::method, {"expected '{'", 8, 1}},
             {"Box(", Stop::constructor, {"expected type name", 2}},
             {"Box(i64 value", Stop::constructor, {"expected ')'", 4}},
             {"Box()", Stop::constructor, {"expected '{'", 3}},
             {"Box(){", Stop::constructor, {"expected '}'", 4}},
             {"Box(){return 1;}", Stop::constructor, {"expected '}'", 4}},
             {"Box(){{}}", Stop::constructor, {"expected '}'", 4}},
             {"Box()const{}", Stop::constructor, {"expected '{'", 3}},
             {"Box():", Stop::constructor, {"expected identifier", 4}},
             {"Box():true(1){}", Stop::constructor, {"reserved identifier", 4}},
             {"Box():array{}{}", Stop::constructor, {"reserved builtin storage name", 4}},
             {"Box():__au_field{}{}", Stop::constructor, {"reserved compiler identifier prefix: __au_", 4}},
             {"Box():value=1{}", Stop::constructor, {"expected '('", 5}},
             {"Box():value(1{}", Stop::constructor, {"expected ')'", 7}},
             {"Box():value(){}", Stop::constructor, {"expected expression", 7}},
             {"Box():value{1,}{}", Stop::constructor, {"expected expression", 9}},
             {"Box():value{}", Stop::constructor, {"expected '{'", 7}},
             {"Box():value(1),{}", Stop::constructor, {"expected identifier", 9}}})
        callableRejection(test.source, test.stop, test.error);
    const std::string borrow =
        "borrowed parameters require a supported leading owning-class reference signature on an ordinary function";
    for (const auto &test :
         std::vector<Rejection>{{"auto f(const i64 value)->i64{}",
                                 Stop::function,
                                 {"const parameter spelling requires a supported owning-class reference", 5}},
                                {"auto f(i64& value)->i64{}", Stop::function, {borrow, 5}},
                                {"auto f(Owner& value)->i64{}", Stop::method, {borrow, 5}},
                                {"Box(Owner& value){}", Stop::constructor, {borrow, 4}},
                                {"auto f(i64 first,Owner& second)->i64{}", Stop::function, {borrow, 8}},
                                {"auto f(Owner& first,Other& second)->i64{}", Stop::function, {borrow, 9}},
                                {"auto f(Box<i64>& value)->i64{}", Stop::function, {borrow, 8}},
                                {"auto f(builtin::ConsoleSession& first,builtin::ConsoleSession& second)->i64{}",
                                 Stop::function,
                                 {borrow, 13}},
                                {"auto f(builtin::DisplaySession& first,builtin::IommuEventSession& second)->i64{}",
                                 Stop::function,
                                 {borrow, 13}},
                                {"auto f(array<i64,2> value)->i64{}",
                                 Stop::function,
                                 {"only scalar function parameters or scalar-field class values are supported", 10}},
                                {"auto f(own<i64> value)->i64{}",
                                 Stop::method,
                                 {"only scalar or enum method parameters are supported", 8}},
                                {"auto f()->array<i64,2>{}",
                                 Stop::function,
                                 {"only scalar function results or scalar-field class values are supported", 11}},
                                {"auto f()->builtin::span<const u8>{}",
                                 Stop::function,
                                 {"only scalar function results or scalar-field class values are supported", 12}},
                                {"auto f()->own<i64>{}",
                                 Stop::method,
                                 {"only scalar, enum, class or readonly span method results are supported", 9}},
                                {"auto Box()->i64{}", Stop::method, {"constructor cannot have a return type", 2}}})
        callableRejection(test.source, test.stop, test.error, true);
    // Intentionally multiply-invalid declarations pin the approved ordering:
    // complete syntax first, then Aurora declaration admission in its original order.
    callableRejection("auto f(i64& true)->i64{}", Stop::function, {"reserved identifier", 5});
    callableRejection("auto f(i64& value)->i64{return 1}", Stop::function, {"expected ';'", 12});
    callableRejection("auto f(array<i64,2> value)->i64{return 1}", Stop::function, {"expected ';'", 16});
    callableRejection("auto Box()->i64{return 1}", Stop::method, {"expected ';'", 9});
    callableRejection("Box(Owner& value){return 1;}", Stop::constructor, {"expected '}'", 7});
}
void serviceAdmission() {
    // Console/display, duplicate-console and display/event already have literal
    // callable fixtures. These are the other ordered two-service combinations.
    struct Fixture {
        const char *first, *second;
        aurora::Type firstType, secondType;
        bool accepted;
    };
    for (const auto &fixture : std::vector<Fixture>{
             {"ConsoleSession",
              "IommuEventSession",
              aurora::Type::ConsoleSession,
              aurora::Type::IommuEventSession,
              true},
             {"IommuEventSession",
              "ConsoleSession",
              aurora::Type::IommuEventSession,
              aurora::Type::ConsoleSession,
              true},
             {"DisplaySession", "ConsoleSession", aurora::Type::DisplaySession, aurora::Type::ConsoleSession, true},
             {"IommuEventSession",
              "DisplaySession",
              aurora::Type::IommuEventSession,
              aurora::Type::DisplaySession,
              false}}) {
        const std::string source =
            "auto f(builtin::" + std::string(fixture.first) + "& first,builtin::" + fixture.second + "& second)->i64{}";
        const std::string prefix = "module service_admission;";
        if (fixture.accepted) {
            const auto program = checkedProgram(aurora::lex(prefix + source, "service-admission.au"));
            require(program.functions.size() == 1 && program.functions[0].params.size() == 2 &&
                        program.functions[0].params[0].borrowed && program.functions[0].params[1].borrowed &&
                        program.functions[0].params[0].type == fixture.firstType &&
                        program.functions[0].params[1].type == fixture.secondType,
                    "two-service admission changed ordered capability types or borrowing");
        } else
            rejectedProgram(
                prefix,
                source,
                "",
                {"borrowed parameters require a supported leading owning-class reference signature on an ordinary function",
                 13});
    }
}
void callableParameterLimit() {
    // Six is a semantic ABI bound, not a callable-grammar or admission bound.
    // Seven complete parameters must survive parsing before the existing
    // typed lowering rejects the declaration at its name.
    for (const std::size_t count : {6, 7}) {
        std::string source = "module callable_limit;auto bounded(";
        for (std::size_t index = 0; index < count; ++index) {
            if (index)
                source += ",";
            source += "i64 p" + std::to_string(index);
        }
        source += ")->i64{return p0;}";
        context = "callable semantic parameter limit " + std::to_string(count);
        const auto tokens = aurora::lex(source, "callable-limit.au");
        const auto direct = aurora::parseHostedCallable(tokens, Cursor{3}, Stop::function);
        require(direct.function.params.size() == count && direct.next.ordinal == tokens.size() - 1 &&
                    direct.next.half == 0,
                "callable parser imposed the semantic six-parameter limit");
        auto program = checkedProgram(tokens);
        sameCallable(program.functions.at(0), direct.function);
        std::optional<aurora::Diagnostic> diagnostic;
        try {
            aurora::HostedResolution resolution;
            const auto module = resolution.add(tokens.front().span.source);
            static_cast<void>(resolution.resolve({module.id}, module.id));
        } catch (const aurora::Error &error) {
            diagnostic = error.diagnostic;
        }
        if (count == 6)
            require(!diagnostic, "six scalar parameters failed existing semantics");
        else {
            require(bool(diagnostic), "seven scalar parameters escaped semantic admission");
            sameError(
                *diagnostic, tokens, {"at most six parameters supported", 4, 0, aurora::DiagnosticCode::Semantic});
        }
        ++cases;
    }
}

void fieldSyntax() {
    using T = aurora::Type;
    struct Fixture {
        std::string source;
        T type;
        std::size_t binding;
        bool publicAccess = false;
    };
    for (const auto &fixture : std::vector<Fixture>{
             {"i64 count;", T::I64, 1, true},
             {"bool ready;", T::Bool, 1},
             {"array<u8,2> bytes;", T::array(aurora::TypeKind::U8, 2), 6},
             {"Box<Box<i64>> value;", namedType("Box", {namedArgument("Box", {aurora::TypeKind::I64})}), 6, true},
             {"Box // retained type trivia\n <i64> value;", namedType("Box", {aurora::TypeKind::I64}), 4},
             {"builtin::OwnedBytes bytes;", T::OwnedBytes, 3},
             {"builtin::OwnedValues<Item> items;", T::ownedValues(T("Item")), 6},
             {"builtin::ConsoleSample sample;", displayedType(T("__au_console_sample"), "builtin::ConsoleSample"), 3}})
        for (const bool wrapped : {false, true}) {
            context = "independent field declaration " + fixture.source;
            const std::string prefix =
                "export module field_contract;class Holder{" + std::string(fixture.publicAccess ? "public:" : "");
            const auto tokens = aurora::lex(wrapped ? prefix + fixture.source + "};" : fixture.source + " next",
                                            "field-contract.au"),
                       before = tokens;
            const auto begin = wrapped ? aurora::lex(prefix).size() - 1 : 0;
            const auto parsed = aurora::parseHostedField(tokens, Cursor{begin});
            sameType(parsed.field.type, fixture.type);
            sameToken(parsed.field.token, tokens.at(begin + fixture.binding));
            require(parsed.next.ordinal == begin + fixture.binding + 2 && parsed.next.half == 0 &&
                        !parsed.field.publicAccess && parsed.field.offset == 0 && parsed.field.index == 0,
                    "field cursor or host-owned metadata differs");
            if (wrapped) {
                const auto program = checkedProgram(tokens);
                require(program.classes.size() == 1 && program.classes[0].fields.size() == 1 &&
                            program.classes[0].fields[0].publicAccess == fixture.publicAccess,
                        "field dispatch lost declaration/access");
                sameToken(program.classes[0].fields[0].token, parsed.field.token);
                sameType(program.classes[0].fields[0].type, fixture.type);
            }
            unchangedTokens(tokens, before);
            ++cases;
        }
}

void declarationContexts() {
    using T = aurora::Type;
    using K = aurora::TypeKind;
    auto t = T(K::Parameter), u = T(K::Parameter);
    t.className = "T";
    u.className = "U";
    auto ta = namedArgument("T"), ua = namedArgument("U");
    ta.type = ua.type = K::Parameter;
    auto array = T::array(t, 0);
    array.lengthParameter = "N";
    struct Fixture {
        std::string source;
        Stop stop;
        CallableAst expected;
    };
    const std::vector<Fixture> functions = {
        {"auto pair(T first,U second)->Pair<T,U>{return Pair<T,U>(first,second);}",
         Stop::function,
         {.result = namedType("Pair", {ta, ua}),
          .parameters = {{4, t}, {7, u}},
          .body = {{17, "return", typed(call(18, {name(25), name(27)}), {ta, ua})}}}}};
    const std::vector<Fixture> methods = {
        {"auto get(T value)->T{array<T,N> items={};return value;}",
         Stop::method,
         {.result = t,
          .parameters = {{4, t}},
          .body = {local(9, 15, array, true, tree("array_literal", 17)), {20, "return", name(21)}}}},
        {"Buffer(T value):items{}{}",
         Stop::constructor,
         {.name = 0, .parameters = {{3, t}}, .initializers = {{6, tree("array_zero", 6)}}}}};
    for (const bool function : {true, false}) {
        const std::string prefix = function
                                       ? "export module callable_context;template<Value T,Value U>"
                                       : "export module callable_context;template<Scalar T,i64 N>class Buffer{public:";
        const auto &fixtures = function ? functions : methods;
        std::string source = prefix;
        for (const auto &fixture : fixtures)
            source += fixture.source;
        if (!function)
            source += "};";
        context = "captured callable declaration context";
        const auto tokens = aurora::lex(source, "callable-context.au"), before = tokens;
        Context captured;
        captured.typeParameters = {tokens.at(7)};
        captured.functionTemplate = function;
        if (function)
            captured.typeParameters.push_back(tokens.at(10));
        else
            captured.capacityParameters = {tokens.at(10)};
        const auto program = checkedProgram(tokens);
        const auto &imported = function ? program.functionTemplates : program.templates.at(0).methods;
        require(imported.size() == fixtures.size(), "template declaration dispatch omitted a callable");
        std::size_t begin = aurora::lex(prefix).size() - 1;
        for (std::size_t index = 0; index < fixtures.size(); ++index) {
            const auto &fixture = fixtures[index];
            const auto direct = aurora::parseHostedCallable(tokens, Cursor{begin}, fixture.stop, captured);
            sameCallableTree(direct, tokens, fixture.expected, fixture.stop, begin);
            sameCallable(imported[index], direct.function);
            begin += aurora::lex(fixture.source).size() - 1;
            require(direct.next.ordinal == begin && direct.next.half == 0, "template callable consumed its neighbor");
            ++cases;
        }
        unchangedTokens(tokens, before);
    }
    const std::string prefix = "export module field_context;template<Scalar T,i64 N>class Buffer{";
    const auto tokens = aurora::lex(prefix + "array<T,N> items;};", "field-context.au"), before = tokens;
    const auto begin = aurora::lex(prefix).size() - 1;
    Context captured;
    captured.typeParameters = {tokens.at(7)};
    captured.capacityParameters = {tokens.at(10)};
    const auto field = aurora::parseHostedField(tokens, Cursor{begin}, captured);
    sameType(field.field.type, array);
    sameToken(field.field.token, tokens.at(begin + 6));
    require(field.next.ordinal == begin + 8 && field.next.half == 0, "dependent field consumed its class terminator");
    sameType(checkedProgram(tokens).templates.at(0).fields.at(0).type, array);
    unchangedTokens(tokens, before);
    ++cases;

    const std::string shadowPrefix = "export module callable_shadow;template<Scalar T>";
    for (const auto &[source, expected] : std::vector<std::pair<std::string, ExpectedError>>{
             {"auto T()->i64{}", {"function name cannot shadow a template parameter", 2}},
             {"auto T()->i64{return 1}", {"expected ';'", 9}},
             {"auto f(Owner& value)->i64{}",
              {"borrowed parameters require a supported leading owning-class reference signature on an ordinary function",
               5}}}) {
        const auto input = aurora::lex(shadowPrefix + source, "callable-shadow.au"), saved = input;
        Context typeContext;
        typeContext.typeParameters = {input.at(7)};
        typeContext.functionTemplate = true;
        const auto start = aurora::lex(shadowPrefix).size() - 1;
        if (expected.message == "expected ';'")
            expectError(
                input,
                expected,
                [&] {
                    static_cast<void>(aurora::parseHostedCallable(input, Cursor{start}, Stop::function, typeContext));
                },
                start);
        else {
            const auto parsed = aurora::parseHostedCallable(input, Cursor{start}, Stop::function, typeContext);
            require(parsed.next.ordinal == input.size() - 1 && parsed.next.half == 0,
                    "standalone callable context acquired whole-module admission");
        }
        unchangedTokens(input, saved);
        rejectedProgram(shadowPrefix, source, "", expected);
        ++cases;
    }
    context = "reserved array constructor in its class context";
    const std::string arrayPrefix = "export module callable_array;namespace std{class array{public:";
    const auto arrayTokens = aurora::lex(arrayPrefix + "array(){}};}", "array-constructor.au");
    const auto start = aurora::lex(arrayPrefix).size() - 1;
    const auto constructor = aurora::parseHostedCallable(arrayTokens, Cursor{start}, Stop::constructor);
    sameCallableTree(constructor, arrayTokens, {.name = 0}, Stop::constructor, start);
    require(constructor.next.ordinal == start + 5 && constructor.next.half == 0, "array constructor escaped its class");
    sameCallable(checkedProgram(arrayTokens).classes.at(0).methods.at(0), constructor.function);
    ++cases;
}
void fieldDiagnostics() {
    struct Fixture {
        std::string source;
        ExpectedError expected;
        bool admission = false, publicAccess = false, templated = false;
    };
    for (const auto &fixture : std::vector<Fixture>{
             {"i64", {"expected identifier", 1}},
             {"i64 value", {"expected ';'", 2}},
             {"i64 true;", {"reserved identifier", 1}},
             {"i64 value=1;", {"expected ';'", 2}},
             {"Box<i64>> value;", {"expected identifier", 3, 1}},
             {"array<u8,2> bytes;", {"array fields must be private", 7}, true, true},
             {"array<i64,65> values;", {"array fields must be private", 7}, true, true},
             {"array<i64,65> values;", {"class array field capacity must be between 1 and 64", 7}, true},
             {"array<u8,513> bytes;", {"class array field capacity must be between 1 and 512", 7}, true},
             {"builtin::OwnedBytes bytes;", {"owned byte fields must be private", 4}, true, true},
             {"builtin::OwnedBytes bytes;", {"owning class templates are unsupported", 4}, true, false, true},
             // Grammar wins before private-field admission in malformed declarations.
             {"array<u8,2> bytes=1;", {"expected ';'", 7}, false, true}}) {
        context = "independent field diagnostic " + fixture.source;
        const auto tokens = aurora::lex(fixture.source, "field-error.au"), before = tokens;
        if (fixture.admission) {
            const auto field = aurora::parseHostedField(tokens, Cursor{});
            require(field.next.ordinal == tokens.size() - 1 && field.next.half == 0,
                    "standalone field syntax acquired whole-module admission");
        } else
            expectError(tokens, fixture.expected, [&] {
                static_cast<void>(aurora::parseHostedField(tokens, Cursor{}));
            });
        unchangedTokens(tokens, before);
        const std::string prefix = "module field_errors;" + std::string(fixture.templated ? "template<Scalar T>" : "") +
                                   "class Holder{" + (fixture.publicAccess ? "public:" : "");
        rejectedProgram(prefix, fixture.source, "};", fixture.expected);
        ++cases;
    }
}

// The actual compiler sources use this closed vocabulary. This is a lookup of
// manually stated Type values, not a second grammar implementation. A new source
// spelling must acquire its own structural expectation rather than silently
// using the product parser as its oracle.
std::map<std::string, aurora::Type> compilerDeclarationTypes() {
    using T = aurora::Type;
    std::map<std::string, T> result{{"i64", T::I64},
                                    {"u64", T::U64},
                                    {"u8", T::U8},
                                    {"bool", T::Bool},
                                    {"builtin::span<constu8>", T::ByteSpan},
                                    {"builtin::ByteRegion", T::ByteRegion},
                                    {"builtin::OwnedBytes", T::OwnedBytes}};
    for (const auto &name : {"Cursor",
                             "Event",
                             "Lexeme",
                             "FrameState",
                             "NodeKind",
                             "ArenaFailure",
                             "ParseFrame",
                             "AstNode",
                             "ChildEdge",
                             "TypeKind",
                             "TypeSyntax",
                             "SyntaxKind",
                             "SyntaxNode",
                             "AstArena",
                             "Stop",
                             "TypeContext",
                             "ParseResult",
                             "ParseStatus",
                             "AdmissionStatus",
                             "AdmissionConfig",
                             "AdmissionResult",
                             "AdmissionProgress",
                             "AdmissionKind",
                             "AdmissionType",
                             "AdmissionScope",
                             "ParseToken",
                             "TypeResult",
                             "TypeWord",
                             "DeclarationWord",
                             "HeaderResult",
                             "IndexRow",
                             "InstructionForm",
                             "Unary",
                             "Binary",
                             "Comparison",
                             "Query",
                             "RecordKind",
                             "OperandRole",
                             "SpanOriginKind",
                             "ContinuationKind",
                             "ContinuationPhase",
                             "ArgumentKind",
                             "CleanupKind",
                             "LoweringStatus",
                             "LoweringError",
                             "LoweringResult",
                             "OutputRow",
                             "OperandRow",
                             "SnapshotRow",
                             "LocalRow",
                             "ArgumentLane",
                             "ContinuationRow",
                             "compiler_lexer::Cursor",
                             "compiler_lexer::Event"})
        result.emplace(name, T(name));
    for (const auto &name : {"AstNode",
                             "ParseFrame",
                             "ChildEdge",
                             "TypeSyntax",
                             "SyntaxNode",
                             "IndexRow",
                             "OutputRow",
                             "OperandRow",
                             "SnapshotRow",
                             "LocalRow",
                             "ContinuationRow"})
        result.emplace(std::string("builtin::OwnedValues<") + name + ">", T::ownedValues(T(name)));
    for (const auto &name : {"Session",
                             "MetaRow",
                             "SyntaxRow",
                             "ResolvedRow",
                             "WorkRow",
                             "ResolvedTypeKind",
                             "NativeMode",
                             "DeclarationKind",
                             "BindContext",
                             "Arguments"})
        result.emplace("compiler_resolver::" + std::string(name), T("compiler_resolver::" + std::string(name)));
    for (const auto &name : {"LoweringConfig",
                             "ScalarSeed",
                             "ServiceParameters",
                             "ServiceSeed",
                             "LocalRequest",
                             "LiteralValue",
                             "IndexedStorage",
                             "FunctionBodyResult"})
        result.emplace(name, T(name));
    return result;
}
void bootstrapDeclarationTypes(const std::vector<aurora::Token> &tokens,
                               const aurora::Program &program,
                               std::size_t module) {
    const auto vocabulary = compilerDeclarationTypes();
    std::size_t parameters = 0, results = 0, fields = 0;
    std::set<std::size_t> lexicalFunctions, importedFunctions, lexicalConstructors, importedConstructors;
    for (std::size_t index = 0; index + 1 < tokens.size(); ++index)
        if (tokens[index].text == "auto")
            lexicalFunctions.insert(index + 1);
    const auto check = [&](std::size_t first, std::size_t end, const aurora::Type &whole) {
        require(first < end && end < tokens.size(), "declaration inventory has an empty/escaped type range");
        std::string spelling;
        for (auto index = first; index < end; ++index)
            spelling += tokens[index].text;
        const auto expected = vocabulary.find(spelling);
        require(expected != vocabulary.end(), "actual declaration type needs an independent expectation: " + spelling);
        sameType(whole, expected->second);
        const auto before = tokens;
        const auto direct = aurora::parseHostedType(tokens, Cursor{first});
        sameType(direct.type, expected->second);
        require(direct.next.ordinal == end && direct.next.half == 0,
                "actual declaration direct parse consumed the following name/delimiter");
        unchangedTokens(tokens, before);
        ++cases;
    };
    const auto functions = [&](const std::vector<aurora::Function> &items,
                               const Context &classContext = {},
                               const std::string &className = {}) {
        for (const auto &function : items) {
            const auto name = tokenAt(tokens, function.token);
            const auto stop = function.constructor ? Stop::constructor
                              : className.empty()  ? Stop::function
                                                   : Stop::method;
            const auto captured = function.templateParameters.empty()
                                      ? classContext
                                      : fixtureContext(tokens, function.token, function.templateParameters, true);
            const auto direct =
                aurora::parseHostedCallable(tokens, Cursor{function.constructor ? name : name - 1}, stop, captured);
            sameCallable(direct.function, function);
            // Current bootstrap constructors use parenthesized initializers;
            // this independent lexical scan must not mistake one for the body.
            for (const auto &[field, expression] : function.initializers) {
                static_cast<void>(expression);
                require(tokens.at(tokenAt(tokens, field) + 1).text == "(",
                        "new braced bootstrap initializer needs its lexical boundary pinned");
            }
            auto body = name + 1;
            while (tokens.at(body).text != "{")
                ++body;
            require(direct.next.ordinal == closingBrace(tokens, body) + 1 && direct.next.half == 0,
                    "whole callable dispatch changed its exact source boundary");
            ++wholeCallables;
            auto &imported = function.constructor ? importedConstructors : importedFunctions;
            require(imported.insert(name).second, "actual declaration type inventory duplicated a function");
            auto position = name + 1;
            require(tokens.at(position++).text == "(", "actual function lost its parameter list");
            for (std::size_t index = 0; index < function.params.size(); ++index) {
                const auto &parameter = function.params[index];
                const bool constant = tokens.at(position).text == "const";
                require(constant == parameter.borrowConst, "actual parameter const qualification differs");
                position += constant;
                auto binding = position;
                while (binding + 1 < tokens.size() &&
                       !(tokens[binding].text == parameter.name &&
                         (tokens[binding + 1].text == "," || tokens[binding + 1].text == ")")))
                    ++binding;
                require(binding > position && binding + 1 < tokens.size(), "actual parameter binding was omitted");
                const bool borrowed = tokens.at(binding - 1).text == "&";
                require(borrowed == parameter.borrowed, "actual parameter reference qualification differs");
                if (borrowed)
                    sameSpan(parameter.borrowSpan, tokens.at(binding - 1).span);
                check(position, binding - borrowed, parameter.type);
                position = binding + 1;
                if (index + 1 < function.params.size())
                    require(tokens.at(position++).text == ",", "actual parameter count/order differs");
                ++parameters;
            }
            require(tokens.at(position++).text == ")", "actual parameter list was truncated");
            if (!function.constructor) {
                const bool constant = tokens.at(position).text == "const";
                require(constant == function.receiverConst, "actual method const qualification differs");
                position += constant;
                require(tokens.at(position++).text == "->", "actual function lost its explicit result type");
                auto opening = position;
                while (opening < tokens.size() && tokens[opening].text != "{")
                    ++opening;
                check(position, opening, function.result);
                ++results;
            }
        }
    };
    functions(program.functions);
    functions(program.functionTemplates);
    const auto classes = [&](const std::vector<aurora::ClassDefinition> &items) {
        for (const auto &definition : items) {
            const auto opening = tokenAt(tokens, definition.token) + 1;
            const auto end = closingBrace(tokens, opening);
            std::set<std::size_t> lexicalFields, importedFields;
            // Count source class-level ';' and constructor headers independently
            // of the parsed declaration lists; method/local statements are deeper.
            std::size_t depth = 1;
            for (auto index = opening + 1; index < end; ++index) {
                if (depth == 1 && tokens[index].text == ";")
                    lexicalFields.insert(index - 1);
                if (depth == 1 && tokens[index].text == definition.name && tokens.at(index + 1).text == "(")
                    lexicalConstructors.insert(index);
                if (tokens[index].text == "{")
                    ++depth;
                else if (tokens[index].text == "}")
                    --depth;
            }
            for (const auto &field : definition.fields) {
                const auto binding = tokenAt(tokens, field.token);
                require(importedFields.insert(binding).second, "actual field type was counted twice");
                auto first = binding;
                while (first > opening + 1 && tokens[first - 1].text != ";" && tokens[first - 1].text != "}" &&
                       tokens[first - 1].text != "{") {
                    if (tokens[first - 1].text == ":")
                        break;
                    --first;
                }
                check(first, binding, field.type);
                const auto captured = fixtureContext(tokens, definition.token, definition.templateParameters, false);
                const auto direct = aurora::parseHostedField(tokens, Cursor{first}, captured);
                sameToken(direct.field.token, field.token);
                sameType(direct.field.type, field.type);
                require(direct.next.ordinal == binding + 2 && direct.next.half == 0 &&
                            tokens.at(binding + 1).text == ";",
                        "whole field dispatch consumed a neighboring declaration");
                ++wholeFields;
                ++fields;
            }
            require(importedFields == lexicalFields, "actual source field declaration type was omitted");
            functions(definition.methods,
                      fixtureContext(tokens, definition.token, definition.templateParameters, false),
                      definition.token.text);
        }
    };
    classes(program.classes);
    classes(program.templates);
    // PR149 source declarations: all 490 type occurrences (259 parameters,
    // 155 results, 76 fields), plus any new declarations. The lexical inventories
    // above prevent larger current sources from hiding omitted new entries.
    const std::array<std::size_t, 6> historicalParameters{24, 91, 144, 0, 0, 0};
    const std::array<std::size_t, 6> historicalResults{18, 73, 64, 0, 0, 0};
    const std::array<std::size_t, 6> historicalFields{7, 47, 22, 0, 0, 0};
    require(importedFunctions == lexicalFunctions && importedConstructors == lexicalConstructors &&
                parameters >= (module < 3 ? historicalParameters.at(module) : 0) &&
                results >= (module < 3 ? historicalResults.at(module) : 0) &&
                fields >= (module < 3 ? historicalFields.at(module) : 0),
            "checked-in compiler declaration-type inventory lost historical or new source entries");
    if (module >= 3 && module <= 5) {
        // New typed schema declarations: exact parameters/results/fields, not a
        // minimum that could silently admit an unregistered source declaration.
        const std::array<std::array<std::size_t, 3>, 3> counts{{{0, 0, 0}, {4, 4, 4}, {70, 88, 72}}};
        require(std::array{parameters, results, fields} == counts.at(module - 3),
                "lowering schema declaration-type coverage differs");
    }
}

// Compact independent container/member inventories. Signs pin access rather
// than deriving it from the parsed AST or replaying declaration grammar.
std::vector<std::string> words(const std::string &text) {
    std::istringstream input(text);
    std::vector<std::string> result;
    for (std::string word; input >> word;)
        result.push_back(std::move(word));
    return result;
}
struct ContainerAst {
    const char *name;
    bool exported;
    const char *fields;
    const char *methods;
};
void sameContainer(const aurora::ClassDefinition &actual,
                   const std::vector<aurora::Token> &tokens,
                   const std::string &scope,
                   const ContainerAst &expected) {
    require(actual.name == expected.name && actual.scope == scope && actual.exported == expected.exported &&
                actual.id == 0 && actual.templateArguments.empty(),
            "class name/scope/export or unresolved identity differs");
    sameToken(actual.token, tokens.at(tokenAt(tokens, actual.token)));
    const auto fields = words(expected.fields), methods = words(expected.methods);
    require(actual.fields.size() == fields.size() && actual.methods.size() == methods.size(),
            "class member count/order differs: " + actual.name);
    for (std::size_t index = 0; index < fields.size(); ++index) {
        const auto &field = actual.fields[index];
        require(field.token.text == fields[index].substr(1) && field.publicAccess == (fields[index][0] == '+') &&
                    field.offset == 0 && field.index == 0,
                "class field name/access or unresolved layout differs: " + actual.name);
        sameToken(field.token, tokens.at(tokenAt(tokens, field.token)));
    }
    for (std::size_t index = 0; index < methods.size(); ++index) {
        const auto &method = actual.methods[index];
        require(method.name == methods[index].substr(1) && method.scope == scope && !method.exported &&
                    method.publicAccess == (methods[index][0] == '+') &&
                    method.constructor == (method.name == actual.name) && method.receiverClass.empty() &&
                    method.templateParameters.empty() && method.templateArguments.empty() && method.moduleScope == 0,
                "class method name/access/scope or constructor marker differs: " + actual.name);
        sameToken(method.token, tokens.at(tokenAt(tokens, method.token)));
    }
    ++cases;
}
void sameTemplateParameters(const std::vector<aurora::TemplateParameter> &actual,
                            const std::vector<aurora::TemplateParameter> &expected) {
    require(actual.size() == expected.size(), "template parameter count differs");
    for (std::size_t index = 0; index < expected.size(); ++index)
        require(actual[index].kind == expected[index].kind && actual[index].name == expected[index].name,
                "template parameter kind/name/order differs");
}
void bootstrapContainers(const std::vector<aurora::Token> &tokens, const aurora::Program &program, std::size_t module) {
    static const std::array<std::vector<ContainerAst>, 3> expected{{
        {{"Cursor", true, "-offset -line -line_start", "+Cursor +at +row +start"},
         {"Lexeme",
          true,
          "-event -offset -line -line_start",
          "+Lexeme +kind +next_offset +next_line +next_line_start"}},
        {{"ParseFrame",
          true,
          "-step -minimum -left -operator_token -field_token",
          "+ParseFrame +state +min +lhs +token +designate +field"},
         {"AstNode",
          true,
          "-tag -token_index -first_child -second_child -tree_depth -name_end -closing_token",
          "+AstNode +kind +token +first +second +depth +locate +last +close"},
         {"ChildEdge",
          true,
          "-child_node -previous_edge -argument_count -tree_depth -field_token",
          "+ChildEdge +child +previous +count +depth +field"},
         {"TypeSyntax",
          true,
          "-tag -token_index -name_end -closing_token -first_child -second_child -owner_token -owner_role",
          "+TypeSyntax +kind +token +last +close +first +second +owner +role +bind_owner"},
         {"SyntaxNode",
          true,
          "-tag -token_index -end_token -previous_node -expression_root -target_root -declared_type -binding_token "
          "-body_node -other_node -qualifier -borrow_token",
          "+SyntaxNode +kind +token +end +previous +expression +target +type +binding +body +other +borrow_site "
          "+bind_borrow +mutable_binding +bind_expression +bind_declaration +bind_body"},
         {"AstArena",
          true,
          "-nodes -used -frames -frame_count -error -edges -edge_count -type_nodes -type_count -syntax_nodes "
          "-syntax_count",
          "-store +AstArena +ok +size +capacity +failure +stack_size +scratch_at +replace_scratch +truncate_stack "
          "+types +type_at +append_type +own_type +syntax_size +syntax_at +append_syntax +frame +pop +replace +push "
          "+at +append_at +append +append_name +append_index +arguments +edge +append_field +append_argument "
          "+append_list"}},
        {{"AdmissionConfig",
          true,
          "-scalar_array_limit -byte_array_limit -service_groups -console_mask -display_mask -event_mask",
          "+AdmissionConfig +array_limit +groups +service_mask"},
         {"AdmissionResult",
          true,
          "-result -token_index -end_token -type_node -detail",
          "+AdmissionResult +status +token +end +type +value"},
         {"TypeContext",
          true,
          "-first_begin -first_end -second_begin -second_end -capacity_begin -capacity_end -template_mode",
          "+TypeContext +update +begin +end +mode +bind_parameter +set_mode"},
         {"ParseResult",
          true,
          "-result -root_node -node_count -token_count -source_offset -token_half",
          "+ParseResult +status +root +size +tokens +offset +half"},
         {"ParseToken",
          false,
          "-event -begin -end -line -line_start -ordinal -token_half",
          "+ParseToken +update +kind +first +last +row +start +index +half +split"},
         {"TypeResult", false, "-result -root_type -next_token", "+TypeResult +status +root +token"},
         {"HeaderResult", false, "-parsed_header -type_context", "+HeaderResult +parsed +context"},
         {"AdmissionProgress", false, "-result -next_token", "+AdmissionProgress +outcome +token"},
         {"AdmissionType", false, "-category -service_bit -next_token", "+AdmissionType +kind +service +token"},
         {"AdmissionScope",
          false,
          "-type_context -class_begin -class_end -public_access",
          "+AdmissionScope +context +begin +end +access"}},
    }};
    const std::string scope = module == 0 ? "compiler_lexer" : "compiler_parser";
    require(program.classes.size() == expected.at(module).size() && program.templates.empty() &&
                program.functionTemplates.empty() && program.namespaces == std::set<std::string>{scope},
            "compiler class/template/namespace inventory differs");
    for (std::size_t index = 0; index < expected[module].size(); ++index) {
        sameContainer(program.classes[index], tokens, scope, expected[module][index]);
        sameTemplateParameters(program.classes[index].templateParameters, {});
    }
    const std::vector<bool> exports =
        module == 2 ? std::vector<bool>{true, false, false, true} : std::vector<bool>{true};
    std::vector<std::size_t> starts;
    for (std::size_t index = 0; index + 1 < tokens.size(); ++index)
        if (tokens[index].text == "namespace") {
            require(starts.size() < exports.size() && tokens[index + 1].text == scope &&
                        (index > 0 && tokens[index - 1].text == "export") == exports[starts.size()],
                    "compiler namespace block name/export/order differs");
            starts.push_back(index);
        }
    require(starts.size() == exports.size(), "compiler omitted one of its six namespace blocks");
    for (const auto &function : program.functions) {
        const auto token = tokenAt(tokens, function.token);
        const auto block = std::upper_bound(starts.begin(), starts.end(), token);
        require(block != starts.begin() && function.scope == scope &&
                    function.exported == exports[static_cast<std::size_t>(block - starts.begin() - 1)],
                "compiler function lost its namespace export inheritance");
    }
    ++cases;
}
void libraryContainers(const std::vector<aurora::Token> &tokens, const aurora::Program &program, bool utility) {
    using Kind = aurora::TemplateParameterKind;
    const std::vector<aurora::TemplateParameter> parameters =
        utility ? std::vector<aurora::TemplateParameter>{{Kind::Value, "T"}, {Kind::Value, "U"}}
                : std::vector<aurora::TemplateParameter>{{Kind::Scalar, "T"}, {Kind::Capacity, "N"}};
    require(program.interfaceUnit && program.namespaces == std::set<std::string>{"std"} && program.classes.empty() &&
                program.templates.size() == 1 && program.functions.empty() &&
                program.functionTemplates.size() == (utility ? 1U : 0U),
            "library template declaration inventory differs");
    sameContainer(program.templates.front(),
                  tokens,
                  "std",
                  utility ? ContainerAst{"pair", true, "+first +second", "+pair"}
                          : ContainerAst{"array", true, "-elements", "+array +size +at +set +exchange"});
    sameTemplateParameters(program.templates.front().templateParameters, parameters);
    if (utility) {
        const auto &function = program.functionTemplates.front();
        require(function.name == "make_pair" && function.scope == "std" && function.exported && !function.constructor &&
                    !function.publicAccess && function.receiverClass.empty(),
                "make_pair lost its namespace/template metadata");
        sameToken(function.token, tokens.at(tokenAt(tokens, function.token)));
        sameTemplateParameters(function.templateParameters, parameters);
        ++cases;
    }
}
void moduleSyntax() {
    const std::string source =
        "export module containers;import dependency;namespace outer::inner{class Box{i64 hidden;public:Box(){}"
        "auto get()const->i64{return 1;}private:i64 secret;auto hide()->i64{return 2;}public:i64 visible;};"
        "export namespace child{class Open{};auto visible()->i64{return 3;}}}"
        "export namespace outer{class Shared{};}class Last{};";
    const auto tokens = aurora::lex(source, "containers.au"), before = tokens;
    const auto program = checkedProgram(tokens);
    require(program.namespaces == std::set<std::string>{"outer", "outer::inner", "outer::inner::child"} &&
                program.classes.size() == 4 && program.functions.size() == 1 && program.templates.empty(),
            "qualified/reopened namespaces changed declaration order or prefix membership");
    sameContainer(
        program.classes[0], tokens, "outer::inner", {"Box", false, "-hidden -secret +visible", "+Box +get -hide"});
    sameContainer(program.classes[1], tokens, "outer::inner::child", {"Open", true, "", ""});
    sameContainer(program.classes[2], tokens, "outer", {"Shared", true, "", ""});
    sameContainer(program.classes[3], tokens, "", {"Last", false, "", ""});
    require(program.functions[0].name == "visible" && program.functions[0].scope == "outer::inner::child" &&
                program.functions[0].exported && program.classes[0].methods[1].receiverConst &&
                !program.classes[0].methods[2].receiverConst,
            "namespace export or method const metadata differs");
    unchangedTokens(tokens, before);
    const auto restored =
        checkedProgram(aurora::lex("export module scopes;namespace std{namespace nested{class Inner{};}class array{};}"
                                   "namespace other{}namespace std{class array{};}",
                                   "restored-scope.au"));
    require(restored.classes.size() == 3 && restored.classes[0].scope == "std::nested" &&
                restored.classes[1].name == "array" && restored.classes[1].scope == "std" &&
                restored.classes[2].name == "array" && restored.classes[2].scope == "std",
            "nested or sibling namespace exit lost exact-std restoration");
    rejectedProgram("export module scopes;",
                    "namespace std{}namespace other{class array{};}",
                    "",
                    {"reserved builtin storage name", 8});
    rejectedProgram("export module scopes;",
                    "namespace std{namespace nested{class array{};}}",
                    "",
                    {"reserved builtin storage name", 7});
    const auto reset = checkedProgram(
        aurora::lex("export module contexts;template<Scalar T,i64 N>class Box{builtin::array<T,N> values;};"
                    "class T{i64 value;};class N{};template<Value U>auto make(U item)->U{return item;}"
                    "auto U(T item)->T{return item;}auto N()->i64{return 1;}"
                    "auto inspect(Owner& owner)->i64{return 0;}",
                    "reset-context.au"));
    require(reset.templates.size() == 1 && reset.classes.size() == 2 && reset.classes[0].name == "T" &&
                reset.classes[1].name == "N" && reset.classes[0].templateParameters.empty() &&
                reset.classes[1].templateParameters.empty() && reset.functionTemplates.size() == 1 &&
                reset.functionTemplates[0].params[0].type.kind == aurora::TypeKind::Parameter &&
                reset.functions.size() == 3 && reset.functions[0].name == "U" && reset.functions[1].name == "N" &&
                reset.functions[0].params[0].type == namedType("T") && reset.functions[0].result == namedType("T") &&
                reset.functions[0].templateParameters.empty() && reset.functions[1].templateParameters.empty() &&
                reset.functions[2].name == "inspect" && reset.functions[2].templateParameters.empty() &&
                reset.functions[2].params[0].borrowed && reset.functions[2].params[0].type == namedType("Owner"),
            "class/function template names or capacity context leaked into a later declaration");
    // The compatibility facade still forwards one complete program parse.
    const auto facade = aurora::Parser(aurora::lex("export module facade;class Empty{};", "facade.au")).parse();
    require(facade.moduleName == "facade" && facade.classes.size() == 1 && facade.classes[0].name == "Empty",
            "Parser compatibility facade lost its whole-module result");
    ++cases;
    for (const bool nested : {false, true}) {
        std::string declaration = "namespace n", scope = "n";
        if (nested)
            declaration += "{";
        for (std::size_t depth = 1; depth < 32; ++depth) {
            declaration += nested ? "namespace n{" : "::n";
            scope += "::n";
        }
        if (!nested)
            declaration += "{";
        declaration += "class Leaf{};" + std::string(nested ? 32 : 1, '}');
        const auto value = checkedProgram(aurora::lex("export module depth;" + declaration, "namespace-depth.au"));
        require(value.namespaces.size() == 32 && value.classes.size() == 1 && value.classes[0].scope == scope,
                "32 namespace components lost their prefixes or leaf scope");
        declaration = nested ? std::string{} : "namespace n";
        for (std::size_t depth = nested ? 0 : 1; depth < 33; ++depth)
            declaration += nested ? "namespace n{" : "::n";
        if (!nested)
            declaration += "{";
        declaration += std::string(nested ? 33 : 1, '}');
        rejectedProgram(
            "export module depth;", declaration, "", {"namespace nesting exceeds 32 components", nested ? 99U : 67U});
    }
}
void moduleDiagnostics() {
    for (const auto &test : std::vector<std::pair<std::string, ExpectedError>>{
             {"namespace", {"expected identifier", 1}},
             {"namespace true{}", {"reserved identifier", 1}},
             {"namespace array{}", {"reserved builtin storage name", 1}},
             {"namespace a::{}", {"expected identifier", 3}},
             {"namespace a", {"expected '{'", 2}},
             {"namespace a{", {"expected '}'", 3}},
             {"namespace a{class C{};", {"expected '}'", 8}},
             {"class", {"expected identifier", 1}},
             {"class true{};", {"reserved identifier", 1}},
             {"class array{};", {"reserved builtin storage name", 1}},
             {"class C", {"expected '{'", 2}},
             {"class C{", {"expected type name", 3}},
             {"class C{}", {"expected ';'", 4}},
             {"class C{public i64 x;};", {"expected ':'", 4}},
             {"class C{private i64 x;};", {"expected ':'", 4}},
             {"template", {"expected '<'", 1}},
             {"template<>class C{};", {"template parameters require Scalar, Value or bounded i64 capacity", 2}},
             {"template<class T>class C{};", {"template parameters require Scalar, Value or bounded i64 capacity", 2}},
             {"template<Scalar>class C{};", {"expected identifier", 3}},
             {"template<Scalar T", {"expected '>'", 4}},
             {"template<Scalar T,Value U,Scalar V>class C{};",
              {"templates require one or two Scalar or Value parameters", 8}},
             {"template<Scalar T,Value T>class C{};", {"duplicate or reserved template parameter", 7}},
             {"template<Scalar i64>class C{};", {"duplicate or reserved template parameter", 4}},
             {"template<i64 N>class C{};", {"template capacity requires a preceding Scalar parameter", 5}},
             {"template<Value T,i64 N>class C{};", {"template capacity requires a preceding Scalar parameter", 8}},
             {"template<Scalar T>namespace n{};",
              {"only class or namespace-level function templates are supported", 5}},
             {"template<Scalar T,i64 N>auto f()->i64{}",
              {"function templates require only Scalar or Value type parameters", 8}},
             {"template<Scalar T>class T{};", {"class name cannot shadow a template parameter", 7}},
             {"class C{};import dependency;", {"imports must precede declarations", 5}},
             {"export import dependency;", {"module reexports are not supported", 1}}})
        rejectedProgram("export module containers;", test.first, "", test.second);
    rejectedProgram(
        "module containers;", "export class C{};", "", {"export declarations require an export module interface", 1});
    rejectedProgram("module containers;", "class C{};", "", {"module must contain a function", 5});
}

// Preamble and enum expectations are independent ordered names and token ranges.
void sameEnum(const aurora::EnumDefinition &definition,
              const std::vector<aurora::Token> &tokens,
              std::size_t start,
              const std::vector<std::string> &names) {
    require(definition.name == tokens.at(start + 2).text && definition.cases.size() == names.size(),
            "enum name or ordered case count differs");
    sameToken(definition.token, tokens.at(start + 2));
    for (std::size_t index = 0; index < names.size(); ++index) {
        require(definition.cases[index].text == names[index], "enum case spelling/order differs");
        sameToken(definition.cases[index], tokens.at(start + 4 + 2 * index));
    }
}
void bootstrapPreambleEnums(const std::vector<aurora::Token> &tokens,
                            const aurora::Program &program,
                            std::size_t module) {
    struct ExpectedEnum {
        const char *name;
        bool exported;
        const char *cases;
    };
    // Explicit source inventory includes the appended module/container wire cases.
    // No production AST supplies these expectations.
    static const std::array<std::vector<ExpectedEnum>, 3> expected{{
        {
            {"Event",
             true,
             "token whitespace line_comment end_of_input unsupported_character invalid_byte invalid_string "
             "invalid_cursor"},
        },
        {
            {"NodeKind",
             true,
             "invalid literal name unary binary call member method_call index array_literal construct array_zero"},
            {"ArenaFailure", true, "none allocation depth invalid"},
            {"FrameState",
             true,
             "expression_start expression_left expression_right primary_start primary_group primary_unary "
             "primary_postfix call_arguments method_arguments index_expression array_arguments construct_field "
             "construct_arguments constructor_arguments template_opening template_candidate type_start "
             "type_arguments type_argument_first type_argument_second type_array_element type_owned_element "
             "body_block body_if_then body_if_else body_while enum_case namespace_parent namespace_header "
             "admission_declaration admission_parameter admission_class_end"},
            {"TypeKind",
             true,
             "invalid i64_type u64_type u8_type bool_type named parameter capacity length_parameter array_type "
             "own_type ref_type mutref_type byte_span builtin_type owned_values builtin_class"},
            {"SyntaxKind",
             true,
             "invalid block local return_value static_assertion conditional loop expression assign field_assign "
             "index_assign parameter initializer function method constructor field preamble import_name "
             "enum_definition enum_case module_definition namespace_definition class_definition declaration "
             "template_scalar template_value template_capacity"},
        },
        {
            {"ParseStatus",
             true,
             "success unsupported expected_expression expected_close expected_end nesting_limit depth_limit "
             "allocation_failure expected_index_close expected_identifier reserved_identifier reserved_builtin "
             "reserved_prefix expected_brace_close expected_dot expected_equal expected_brace_open "
             "expected_angle_open expected_angle_close expected_scope expected_comma expected_const expected_u8 "
             "expected_i64 expected_array reserved_type expected_type type_nesting_limit template_nesting_limit "
             "call_template_nesting_limit template_context template_arity template_argument capacity_argument "
             "nested_dependent owned_element array_element array_length class_array_length expected_open "
             "expected_semicolon unterminated_block block_nesting_limit assignment_target expected_auto "
             "expected_arrow expected_module expected_enum expected_class module_name_limit module_enum_limit "
             "empty_enum enum_case_limit duplicate_enum_case explicit_enum_value expected_colon "
             "namespace_nesting_limit "
             "export_interface_required module_reexport imports_after_declarations template_parameter_limit "
             "template_parameter_kind template_parameter_name template_capacity_order template_declaration_kind "
             "function_template_capacity class_template_shadow invalid"},
            {"AdmissionStatus",
             true,
             "success allocation_failure function_shadow typed_constructor borrowed_parameter const_parameter "
             "function_parameter method_parameter function_result method_result public_array array_capacity "
             "public_owner templated_owner unsupported_field missing_function invalid"},
            {"Stop",
             true,
             "semicolon close_parenthesis assignment constructor_braces body type function method constructor "
             "field preamble enum_definition module_definition"},
            {"TypeWord",
             false,
             "invalid i64_type u64_type u8_type bool_type array_type builtin_type span_type owned_values own_type "
             "ref_type mutref_type const_type"},
            {"DeclarationWord",
             false,
             "invalid export_declaration import_declaration namespace_declaration enum_declaration "
             "template_declaration class_declaration auto_declaration public_access private_access "
             "scalar_parameter value_parameter capacity_parameter"},
            {"AdmissionKind", false, "invalid copied class_value span region owner service unsupported"},
        },
    }};
    const std::array<std::string, 3> modules{
        "aurora.compiler.lexer", "aurora.compiler.syntax_arena", "aurora.compiler.parser"};
    const auto before = tokens;
    const auto preamble = aurora::parseHostedPreamble(tokens, {});
    const std::size_t imports = module == 2 ? 2 : 0, next = module == 2 ? 22 : 8;
    require(preamble.program.moduleName == modules.at(module) && preamble.program.interfaceUnit &&
                preamble.program.imports.size() == imports && program.imports.size() == imports &&
                preamble.next.ordinal == next && preamble.next.half == 0,
            "actual compiler preamble or ordered imports differ");
    for (std::size_t index = 0; index < imports; ++index) {
        auto expectedImport = tokens.at(9 + 7 * index);
        expectedImport.text = modules[index];
        expectedImport.span.end = tokens.at(13 + 7 * index).span.end;
        sameToken(preamble.program.imports[index], expectedImport);
        sameToken(program.imports[index], expectedImport);
    }
    std::vector<std::size_t> starts;
    for (std::size_t index = 0; index + 1 < tokens.size(); ++index)
        if (tokens[index].text == "enum" && tokens[index + 1].text == "class")
            starts.push_back(index);
    require(starts.size() == expected.at(module).size() && program.enums.size() == starts.size(),
            "actual compiler enum source inventory omitted or duplicated a declaration");
    std::size_t caseCount = 0;
    for (std::size_t index = 0; index < starts.size(); ++index) {
        const auto &fixture = expected[module][index];
        std::istringstream words(fixture.cases);
        std::vector<std::string> names;
        for (std::string name; words >> name;)
            names.push_back(std::move(name));
        // These source declarations have no trailing comma.
        const auto start = starts[index], end = start + 2 * names.size() + 5;
        const auto direct = aurora::parseHostedEnum(tokens, Cursor{start}, index);
        require(direct.definition.name == fixture.name && direct.definition.scope.empty() &&
                    !direct.definition.exported && direct.definition.id == 0 && direct.next.ordinal == end &&
                    direct.next.half == 0 && tokens.at(end - 1).text == ";" && tokens.at(end - 2).text == "}" &&
                    program.enums[index].name == fixture.name && program.enums[index].exported == fixture.exported &&
                    program.enums[index].scope == (module == 0 ? "compiler_lexer" : "compiler_parser"),
                "actual compiler enum name/scope/export or exact cursor differs");
        sameEnum(direct.definition, tokens, start, names);
        sameEnum(program.enums[index], tokens, start, names);
        caseCount += names.size();
        ++cases;
    }
    const std::array<std::size_t, 3> counts{8, 93, 132};
    require(caseCount == counts.at(module), "actual compiler enum case inventory differs");
    unchangedTokens(tokens, before);
    ++cases;
}

void preambleEnumSyntax() {
    struct Preamble {
        std::string source, module;
        bool interface;
        std::vector<std::pair<std::size_t, std::size_t>> imports;
        std::size_t next;
    };
    for (const auto &test : std::vector<Preamble>{
             {"module one;enum", "one", false, {}, 3},
             {"export module one.two;import std.array;import alpha.beta;enum", "one.two", true, {{7, 9}, {12, 14}}, 16},
             {"module a.array;import a.array;", "a.array", false, {{6, 8}}, 10},
             {"module one;import one;import one;", "one", false, {{4, 4}, {7, 7}}, 9},
             {"export module a // gap\n . b; // next\n import c . array;class", "a.b", true, {{7, 9}}, 11}}) {
        for (const std::size_t base : {0U, 2U}) {
            context = "preamble boundary " + test.source;
            const auto tokens = aurora::lex((base ? "prefix;" : "") + test.source, "preamble.au"), before = tokens;
            const Cursor cursor{base};
            const auto parsed = aurora::parseHostedPreamble(tokens, cursor);
            const auto &program = parsed.program;
            require(program.moduleName == test.module && program.interfaceUnit == test.interface &&
                        program.imports.size() == test.imports.size() && program.enums.empty() &&
                        program.functions.empty() && program.functionTemplates.empty() && program.classes.empty() &&
                        program.templates.empty() && program.namespaces.empty() && program.reflectionAccess.empty() &&
                        parsed.next.ordinal == base + test.next && parsed.next.half == 0 && cursor.ordinal == base &&
                        cursor.half == 0,
                    "preamble acquired declarations or lost its exact boundary");
            for (std::size_t index = 0; index < test.imports.size(); ++index) {
                const auto [first, last] = test.imports[index];
                auto expected = tokens.at(base + first);
                for (auto ordinal = first + 1; ordinal <= last; ++ordinal)
                    expected.text += tokens.at(base + ordinal).text;
                expected.span.end = tokens.at(base + last).span.end;
                sameToken(program.imports[index], expected);
            }
            unchangedTokens(tokens, before);
            ++cases;
        }
    }
    for (const std::size_t size : {4096U, 4097U}) {
        const std::string name(size - 2, 'a');
        const auto tokens = aurora::lex("module " + (size == 4096 ? name + " // gap\n . // gap\n b" : "short") +
                                            ";import " + name + " // gap\n . b;",
                                        "module-limits.au");
        const auto before = tokens;
        const auto parsed = aurora::parseHostedPreamble(tokens, {});
        require(parsed.program.moduleName.size() == (size == 4096 ? size : 5) &&
                    parsed.program.imports.at(0).text.size() == size && parsed.next.ordinal == tokens.size() - 1 &&
                    parsed.next.half == 0,
                "module-name cap incorrectly counted trivia or limited import names");
        unchangedTokens(tokens, before);
        ++cases;
    }
    struct Enum {
        const char *source;
        std::vector<std::string> names;
        std::size_t next, count;
    };
    for (const auto &test :
         std::vector<Enum>{{"enum class Solo{first};next", {"first"}, 7, 0},
                           {"enum class Shade{red,green,blue,};next", {"red", "green", "blue"}, 12, 63},
                           {"enum class Case{_zero,Same,same};next", {"_zero", "Same", "same"}, 11, 0}}) {
        for (const std::size_t base : {0U, 2U}) {
            context = "enum boundary " + std::string(test.source);
            const auto tokens = aurora::lex((base ? "prefix;" : "") + std::string(test.source), "enum.au"),
                       before = tokens;
            const Cursor cursor{base};
            const auto parsed = aurora::parseHostedEnum(tokens, cursor, test.count);
            sameEnum(parsed.definition, tokens, base, test.names);
            require(parsed.next.ordinal == base + test.next && parsed.next.half == 0 &&
                        parsed.definition.scope.empty() && !parsed.definition.exported && parsed.definition.id == 0 &&
                        cursor.ordinal == base && cursor.half == 0,
                    "enum acquired declaration-context authority or lost cursor boundary");
            unchangedTokens(tokens, before);
            ++cases;
        }
    }
    context = "enum scope/export and module-count dispatch";
    const auto tokens =
        aurora::lex("export module enums;namespace inner{export enum class E{a,b,};}enum class F{c};", "enum-scope.au");
    const auto program = checkedProgram(tokens);
    require(program.enums.size() == 2 && program.enums[0].scope == "inner" && program.enums[0].exported &&
                program.enums[1].scope.empty() && !program.enums[1].exported,
            "enum dispatch lost namespace/export state");
    sameEnum(program.enums[0], tokens, 8, {"a", "b"});
    sameEnum(program.enums[1], tokens, 19, {"c"});
    std::string source = "export module limit;";
    for (std::size_t index = 0; index < 64; ++index)
        source += "enum class E" + std::to_string(index) + "{one};";
    require(checkedProgram(aurora::lex(source, "enum-count.au")).enums.size() == 64,
            "64 enum definitions were rejected");
    rejectedProgram(source, "enum class Last{one};", "", {"module exceeds 64 enum definitions", 3});
    rejectedProgram(source, "enum class 0{};", "", {"expected identifier", 2});
    rejectedProgram(source, "enum class true{};", "", {"reserved identifier", 2});
    rejectedProgram(source, "enum class Last", "", {"module exceeds 64 enum definitions", 3});
}
std::string enumSource(std::size_t width) {
    std::string source = "enum class Wide{";
    for (std::size_t index = 0; index < width; ++index)
        source += (index ? "," : "") + std::string("case_") + std::to_string(index);
    return source + "};";
}

class Allocations {
public:
    std::size_t allowed = std::numeric_limits<std::size_t>::max(), successful = 0, released = 0;
    std::size_t attempted = 0, watchedBytes = 0, observed = 0, failedObserved = 0;
    std::array<std::size_t, 11> initialBytes{};
    std::array<void *, 11> initialOwners{}, releasedOwners{};
    static void *allocate(void *context, std::size_t bytes) noexcept {
        auto &state = *static_cast<Allocations *>(context);
        if (state.attempted < state.initialBytes.size())
            state.initialBytes[state.attempted] = bytes;
        ++state.attempted;
        const bool watched = state.watchedBytes != 0 && bytes == state.watchedBytes;
        state.observed += watched;
        auto *result = state.successful < state.allowed ? std::malloc(bytes) : nullptr;
        if (state.attempted <= state.initialOwners.size())
            state.initialOwners[state.attempted - 1] = result;
        if (result)
            ++state.successful;
        else
            state.failedObserved += watched;
        return result;
    }
    static void deallocate(void *context, void *address) noexcept {
        auto &state = *static_cast<Allocations *>(context);
        if (state.released < state.releasedOwners.size())
            state.releasedOwners[state.released] = address;
        ++state.released;
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
static_assert(sizeof(Words) == 48 && sizeof(GuardedWords<6>) == 64 && sizeof(GuardedWords<5>) == 56 &&
              sizeof(GuardedWords<7>) == 72 && sizeof(EdgeWords) == 40 && sizeof(TypeWords) == 64 &&
              sizeof(GuardedWords<8>) == 80 && sizeof(ContextWords) == 56 && sizeof(GuardedWords<19>) == 168 &&
              sizeof(SyntaxWords) == 96 && sizeof(GuardedWords<12>) == 112);
static_assert(sizeof(AdmissionWords) == sizeof(aurora::hosted_abi::compiler_parser::AdmissionResult) &&
              sizeof(AdmissionConfigWords) == sizeof(aurora::hosted_abi::compiler_parser::AdmissionConfig) &&
              sizeof(std::array<std::int64_t, 14>) == sizeof(aurora::hosted_abi::AdmissionInput) &&
              sizeof(AdmissionWords) == 40 && sizeof(AdmissionConfigWords) == 48);
static_assert(offsetof(aurora::hosted_abi::AdmissionInput, root) == 56 &&
              offsetof(aurora::hosted_abi::AdmissionInput, configuration) == 64);
static_assert(sizeof(Words) == sizeof(aurora::hosted_abi::compiler_parser::ParseResult) &&
              sizeof(NodeWords) == sizeof(aurora::hosted_abi::compiler_parser::AstNode) &&
              sizeof(EdgeWords) == sizeof(aurora::hosted_abi::compiler_parser::ChildEdge) &&
              sizeof(TypeWords) == sizeof(aurora::hosted_abi::compiler_parser::TypeSyntax) &&
              sizeof(SyntaxWords) == sizeof(aurora::hosted_abi::compiler_parser::SyntaxNode) &&
              sizeof(std::array<std::int64_t, 19>) == sizeof(aurora::hosted_abi::ParserInput));
static_assert(sizeof(ContextWords) == offsetof(aurora::hosted_abi::ParserInput, enum_count) -
                                          offsetof(aurora::hosted_abi::ParserInput, context));
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
        return record.arena.storage.data();
    }
    void guards() const {
        require(before == canary && after == canary, "arena write escaped its ABI extent");
    }
    Words parse(const std::string &source,
                Stop stop = Stop::semicolon,
                std::int64_t offset = 0,
                ContextWords typeContext = {},
                std::int64_t enumCount = 0) {
        GuardedWords<19> input;
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
        static_assert(sizeof(input.value) == 152);
        input.value[18] = enumCount;
        const auto beforeSource = source;
        for (std::size_t index = 0; index < typeContext.size(); ++index)
            input.value[11 + index] = typeContext[index];
        const auto beforeInput = input.value;
        GuardedWords<6> output;
        checked_hosted_parser_parse(data(), input.value.data(), output.value.data());
        input.check();
        require(input.value == beforeInput && source == beforeSource,
                "parse changed its copied input/source/context record");
        output.check();
        guards();
        require(output.value[2] == checked_hosted_parser_count(data()),
                "reported arena count differs from real storage");
        if (stop == Stop::semicolon || stop == Stop::close_parenthesis || stop == Stop::assignment ||
            stop == Stop::constructor_braces || stop == Stop::type)
            require(syntaxCount() == 0, "expression/type profile acquired syntax records");
        if (stop == Stop::type)
            require(output.value[2] == 0 && edges() == 0, "type-only profile acquired expression/edge records");
        return output.value;
    }
    AdmissionWords admit(const std::string &source,
                         std::int64_t root,
                         const AdmissionConfigWords &configuration = admissionConfiguration) {
        GuardedWords<14> input;
        input.value = {0,
                       static_cast<std::int64_t>(reinterpret_cast<std::uintptr_t>(source.data())),
                       0,
                       0,
                       0,
                       0,
                       static_cast<std::int64_t>(source.size()),
                       root};
        std::copy(configuration.begin(), configuration.end(), input.value.begin() + 8);
        const auto beforeInput = input.value;
        const auto beforeSource = source;
        GuardedWords<5> output;
        checked_hosted_parser_admit(data(), input.value.data(), output.value.data());
        input.check();
        output.check();
        guards();
        require(input.value == beforeInput && source == beforeSource,
                "admission changed its copied source/root/configuration record");
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
    std::int64_t syntaxCount() {
        const auto count = checked_hosted_parser_syntax_count(data());
        guards();
        return count;
    }
    SyntaxWords syntax(std::int64_t index) {
        GuardedWords<12> output;
        checked_hosted_parser_syntax(data(), index, output.value.data());
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
void preambleEnumDiagnostics() {
    struct Rejection {
        std::string source;
        Stop stop;
        Status status;
        ExpectedError error;
        std::size_t count = 0;
    };
    for (const auto &test : std::vector<Rejection>{
             {"", Stop::preamble, Status::expected_module, {"expected 'module'", 0}},
             {"export", Stop::preamble, Status::expected_module, {"expected 'module'", 1}},
             {"module", Stop::preamble, Status::expected_identifier, {"expected identifier", 1}},
             {"module 0;", Stop::preamble, Status::expected_identifier, {"expected identifier", 1}},
             {"module true;", Stop::preamble, Status::reserved_identifier, {"reserved identifier", 1}},
             {"module array;", Stop::preamble, Status::reserved_builtin, {"reserved builtin storage name", 1}},
             {"module __au_private;",
              Stop::preamble,
              Status::reserved_prefix,
              {"reserved compiler identifier prefix: __au_", 1}},
             {"module a.;", Stop::preamble, Status::expected_identifier, {"expected identifier", 3}},
             {"module a.true;", Stop::preamble, Status::reserved_identifier, {"reserved identifier", 3}},
             {"module a.builtin;", Stop::preamble, Status::reserved_builtin, {"reserved builtin storage name", 3}},
             {"module a.__au_private;",
              Stop::preamble,
              Status::reserved_prefix,
              {"reserved compiler identifier prefix: __au_", 3}},
             {"module a::b;", Stop::preamble, Status::expected_semicolon, {"expected ';'", 2}},
             {"module a", Stop::preamble, Status::expected_semicolon, {"expected ';'", 2}},
             {"module a;import", Stop::preamble, Status::expected_identifier, {"expected identifier", 4}},
             {"module a;import array;", Stop::preamble, Status::reserved_builtin, {"reserved builtin storage name", 4}},
             {"module a;import a.true;", Stop::preamble, Status::reserved_identifier, {"reserved identifier", 6}},
             {"module a;import a.builtin;",
              Stop::preamble,
              Status::reserved_builtin,
              {"reserved builtin storage name", 6}},
             {"module a;import a.", Stop::preamble, Status::expected_identifier, {"expected identifier", 6}},
             {"module a;import a", Stop::preamble, Status::expected_semicolon, {"expected ';'", 5}},
             {"module " + std::string(4095, 'a') + " // gap\n . b;",
              Stop::preamble,
              Status::module_name_limit,
              {"module name exceeds 4096 bytes", 4}},
             {"module " + std::string(4097, 'a') + ".true;",
              Stop::preamble,
              Status::reserved_identifier,
              {"reserved identifier", 3}},
             {"module " + std::string(4097, 'a') + ".;",
              Stop::preamble,
              Status::expected_identifier,
              {"expected identifier", 3}},
             {"module " + std::string(4097, 'a') + " missing",
              Stop::preamble,
              Status::module_name_limit,
              {"module name exceeds 4096 bytes", 2}},
             {"class E{a};", Stop::enum_definition, Status::expected_enum, {"expected 'enum'", 0}},
             {"enum E{a};", Stop::enum_definition, Status::expected_class, {"expected 'class'", 1}},
             {"enum class", Stop::enum_definition, Status::expected_identifier, {"expected identifier", 2}},
             {"enum class true{a};", Stop::enum_definition, Status::reserved_identifier, {"reserved identifier", 2}},
             {"enum class array{a};",
              Stop::enum_definition,
              Status::reserved_builtin,
              {"reserved builtin storage name", 2}},
             {"enum class __au_E{a};",
              Stop::enum_definition,
              Status::reserved_prefix,
              {"reserved compiler identifier prefix: __au_", 2}},
             {"enum class E", Stop::enum_definition, Status::expected_brace_open, {"expected '{'", 3}},
             {"enum class E{};",
              Stop::enum_definition,
              Status::empty_enum,
              {"enum class requires at least one named case", 4}},
             {"enum class E{", Stop::enum_definition, Status::expected_identifier, {"expected identifier", 4}},
             {"enum class E{0};", Stop::enum_definition, Status::expected_identifier, {"expected identifier", 4}},
             {"enum class E{true};", Stop::enum_definition, Status::reserved_identifier, {"reserved identifier", 4}},
             {"enum class E{array};",
              Stop::enum_definition,
              Status::reserved_builtin,
              {"reserved builtin storage name", 4}},
             {"enum class E{__au_case};",
              Stop::enum_definition,
              Status::reserved_prefix,
              {"reserved compiler identifier prefix: __au_", 4}},
             {"enum class E{a,a};", Stop::enum_definition, Status::duplicate_enum_case, {"duplicate enum case: a", 7}},
             {"enum class E{a,a=1};",
              Stop::enum_definition,
              Status::duplicate_enum_case,
              {"duplicate enum case: a", 7}},
             {"enum class E{ab,a,ab};",
              Stop::enum_definition,
              Status::duplicate_enum_case,
              {"duplicate enum case: ab", 9}},
             {"enum class E{a=1};",
              Stop::enum_definition,
              Status::explicit_enum_value,
              {"enum cases cannot have explicit values", 5}},
             {"enum class E{a", Stop::enum_definition, Status::expected_brace_close, {"expected '}'", 5}},
             {"enum class E{a b};", Stop::enum_definition, Status::expected_brace_close, {"expected '}'", 5}},
             {"enum class E{a,,};", Stop::enum_definition, Status::expected_identifier, {"expected identifier", 6}},
             {"enum class E{a,", Stop::enum_definition, Status::expected_identifier, {"expected identifier", 6}},
             {"enum class E{a}", Stop::enum_definition, Status::expected_semicolon, {"expected ';'", 6}},
             {"enum class 0{};", Stop::enum_definition, Status::expected_identifier, {"expected identifier", 2}, 64},
             {"enum class true{};", Stop::enum_definition, Status::reserved_identifier, {"reserved identifier", 2}, 64},
             {"enum E{};", Stop::enum_definition, Status::expected_class, {"expected 'class'", 1}, 64},
             {"enum class E",
              Stop::enum_definition,
              Status::module_enum_limit,
              {"module exceeds 64 enum definitions", 3},
              64},
             {"enum class E{};",
              Stop::enum_definition,
              Status::module_enum_limit,
              {"module exceeds 64 enum definitions", 3},
              64},
             {enumSource(255).substr(0, enumSource(255).size() - 2) + ",case_0};",
              Stop::enum_definition,
              Status::duplicate_enum_case,
              {"duplicate enum case: case_0", 515}},
             {enumSource(257),
              Stop::enum_definition,
              Status::enum_case_limit,
              {"enum class exceeds 256 named cases", 516}},
             {enumSource(256).substr(0, enumSource(256).size() - 2) + ",true};",
              Stop::enum_definition,
              Status::enum_case_limit,
              {"enum class exceeds 256 named cases", 516}}}) {
        context = "preamble/enum diagnostic " + test.source.substr(0, 100);
        const auto tokens = aurora::lex(test.source, "preamble-enum-error.au"), before = tokens;
        const Cursor cursor{};
        expectError(tokens, test.error, [&] {
            if (test.stop == Stop::preamble)
                static_cast<void>(aurora::parseHostedPreamble(tokens, cursor));
            else
                static_cast<void>(aurora::parseHostedEnum(tokens, cursor, test.count));
        });
        require(cursor.ordinal == 0 && cursor.half == 0, "failed preamble/enum changed caller cursor");
        unchangedTokens(tokens, before);
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(test.source, test.stop, 0, {}, test.count);
        require(result == Words{wire(test.status),
                                -1,
                                0,
                                static_cast<std::int64_t>(test.error.token),
                                static_cast<std::int64_t>(tokens.at(test.error.token).span.begin.offset),
                                0} &&
                    arena.types() == 0 && arena.edges() == 0,
                "raw preamble/enum first diagnostic or foreign record count differs");
        arena.finish();
        require(allocations.successful == allocations.released, "failed preamble/enum leaked an owner");
        ++cases;
        if (test.count == 0 && test.error.message != "expected 'enum'")
            rejectedProgram(test.stop == Stop::preamble ? "" : "export module errors;", test.source, "", test.error);
    }
    context = "256 named cases and trailing comma";
    for (const bool trailing : {false, true}) {
        auto source = enumSource(256);
        if (trailing)
            source.insert(source.size() - 2, ",");
        const auto tokens = aurora::lex(source, "enum-wide.au"), before = tokens;
        std::vector<std::string> names;
        for (std::size_t index = 0; index < 256; ++index)
            names.push_back("case_" + std::to_string(index));
        const auto parsed = aurora::parseHostedEnum(tokens, {}, 63);
        sameEnum(parsed.definition, tokens, 0, names);
        require(parsed.next.ordinal == 517U + trailing && parsed.next.half == 0,
                "256-case enum lost its exact closing semicolon");
        unchangedTokens(tokens, before);
        ++cases;
    }
}

// Unresolved syntax comparisons stay above. The production boundary below is
// independently checked typed IR, optional ABI observations and source-backed
// diagnostics; no fixture reconstructs a resolved Program.
template <class Module>
const aurora::ir::Function &typedFunction(const Module &module, const std::string &name) {
    const auto found = std::find_if(module.functions.begin(), module.functions.end(), [&](const auto &function) {
        return function.name == name;
    });
    require(found != module.functions.end(), "typed function was omitted: " + name);
    return *found;
}
template <class Instruction> std::vector<Instruction> typedInstructions(const aurora::ir::Function &function) {
    std::vector<Instruction> result;
    for (const auto &instruction : function.code)
        if (const auto *value = std::get_if<Instruction>(&instruction))
            result.push_back(*value);
    return result;
}
std::string spanText(const aurora::SourceSpan &span) {
    require(span.source && span.begin.offset <= span.end.offset && span.end.offset <= span.source->text.size(),
            "diagnostic source span escaped its immutable source");
    return span.source->text.substr(span.begin.offset, span.end.offset - span.begin.offset);
}
bool nominalViews(const aurora::ir::Metadata &metadata, const std::map<int, std::set<int>> &expected) {
    if (metadata.scopeCount() != expected.size())
        return false;
    auto scope = expected.begin();
    for (std::size_t index = 0; index < metadata.scopeCount(); ++index, ++scope) {
        if (metadata.scopeAt(index) != scope->first)
            return false;
        auto descriptor = scope->second.begin();
        for (const auto id : metadata.visibleDescriptors(scope->first))
            if (id >= 100 && id < 1000000) {
                if (descriptor == scope->second.end() || *descriptor != id)
                    return false;
                ++descriptor;
            }
        if (descriptor != scope->second.end())
            return false;
    }
    return true;
}
void constantReturn(const aurora::ir::Function &function, std::int64_t value) {
    require(function.result == aurora::Type::I64 && function.parameters.empty() && function.code.size() == 2 &&
                std::holds_alternative<aurora::ir::Constant>(function.code[0]) &&
                std::get<aurora::ir::Constant>(function.code[0]).value == value &&
                std::get<aurora::ir::Constant>(function.code[0]).type == aurora::Type::I64 &&
                std::holds_alternative<aurora::ir::Return>(function.code[1]),
            "concrete value/reflection return differs");
}
void resolvedModules() {
    context = "typed module instances, nominal authority, layout and source ownership";
    auto dependency =
        std::make_shared<const aurora::SourceText>("definitions.au",
                                                   "// unused trivia keeps sparse source requests apart\n"
                                                   "export module dep;\n"
                                                   "export namespace lib {\n"
                                                   "enum class Flag {cold,hot};\n"
                                                   "class Leaf {public:i64 value;};\n"
                                                   "template<Scalar T,i64 N> class Buffer {\n"
                                                   "  builtin::array<T,N> data;\n"
                                                   "public:Buffer():data{}{}\n"
                                                   "  auto size()const->i64 {return N;}\n"
                                                   "  auto own_size()const->i64 {return size_of(Buffer);}\n"
                                                   "};\n"
                                                   "template<Value T> auto measure()->i64 {return size_of(T);}\n"
                                                   "}\n");
    auto root = std::make_shared<const aurora::SourceText>(
        "requests.au",
        "module root;import dep // import gap\n ;\n"
        "class Hidden {public:i64 value;};\n"
        "enum class State {zero,one};\n"
        "auto answer()->i64 {\n"
        "  const lib::Buffer<u8,3> first=lib // call gap\n :: Buffer<u8,3>();\n"
        "  const lib::Buffer<u8,4> second=lib::Buffer<u8,4>();\n"
        "  const lib::Buffer<u8,3> again=lib::Buffer<u8,3>();\n"
        "  const State state=State::one;\n"
        "  return lib::measure<Hidden>()+lib::measure<State>()+lib::measure<Hidden>();\n"
        "}\n");
    auto rootTokens = aurora::lex(root);
    const auto resolved = [&] {
        aurora::HostedResolution resolution;
        // Arrival order deliberately differs from dependency/output order.
        const auto main = resolution.add(root), imported = resolution.add(dependency);
        require(main.id != imported.id && main.moduleName == "root" && !main.interfaceUnit &&
                    main.imports.size() == 1 && main.imports.front().text == "dep" && imported.moduleName == "dep" &&
                    imported.interfaceUnit && imported.imports.empty(),
                "copied module header/import identity differs");
        sameToken(main.imports.front(), rootTokens.at(4));
        return resolution.resolve({imported.id, main.id}, main.id, aurora::AnalysisMode::Lint, true);
    }();
    const auto &module = resolved.module.get();
    const auto &metadata = resolved.module.metadata();
    const auto &abi = resolved.abiDeclarations;
    const std::string hidden = "__au_c_m1_4root_n0__d6Hidden", state = "__au_e_m1_4root_n0__d5State";
    const std::string leaf = "__au_c_m1_3dep_n1_3lib_d4Leaf", flag = "__au_e_m1_3dep_n1_3lib_d4Flag";
    const std::array<std::string, 2> buffers{"__au_c_m1_3dep_n1_3lib_d6Buffer_t2_u8_v3",
                                             "__au_c_m1_3dep_n1_3lib_d6Buffer_t2_u8_v4"};
    const std::array<std::string, 2> measures{"__au_g_m1_3dep_n1_3lib_d7measure_t1_c28__au_c_m1_4root_n0__d6Hidden",
                                              "__au_g_m1_3dep_n1_3lib_d7measure_t1_e27__au_e_m1_4root_n0__d5State"};
    // Validated IR prunes unused imported implementations; source ABI metadata
    // retains every resolved declaration. The preserved PR161 probe pins these
    // five retained identities/order independently of the candidate lowerer.
    const std::array<std::string, 5> retained{measures[0],
                                              measures[1],
                                              "answer",
                                              "__au_k_m1_3dep_n2_3lib6Buffer_d6Buffer_t2_u8_v3",
                                              "__au_k_m1_3dep_n2_3lib6Buffer_d6Buffer_t2_u8_v4"};
    require(module.functions.size() == retained.size() && metadata.classCount() == 4 &&
                metadata.enumCount() == 2 && abi.records.size() == 4 && abi.enums.size() == 2 &&
                abi.functions.size() == 9,
            "typed output duplicated concrete instances or lost declarations");
    for (std::size_t index = 0; index < retained.size(); ++index)
        require(module.functions[index].name == retained[index], "retained concrete function order differs");
    for (std::size_t index = 0; index < metadata.classCount(); ++index)
        require(!metadata.isCarrier(metadata.classAt(index)), "typed output added an array carrier");
    const auto definitionSyntax = checkedProgram(aurora::lex(dependency));
    const auto &bufferSyntax = definitionSyntax.templates.at(0);
    require(bufferSyntax.methods.size() == 3, "source Buffer method inventory differs");
    require(abi.records.at(leaf).sourceName == "lib::Leaf" && abi.records.at(hidden).sourceName == "Hidden" &&
                abi.records.at(leaf).members == std::vector<std::string>{"value"} &&
                abi.records.at(hidden).members == std::vector<std::string>{"value"} &&
                abi.enums.at(flag).members == std::vector<std::string>{"cold", "hot"} &&
                abi.enums.at(state).members == std::vector<std::string>{"zero", "one"} &&
                metadata.enumCases(metadata.findEnum(flag).value()) == 2 &&
                metadata.enumCases(metadata.findEnum(state).value()) == 2,
            "source ABI field/case order or concrete enum identity differs");
    for (std::size_t index = 0; index < measures.size(); ++index) {
        const auto &function = module.functions.at(index);
        require(function.name == measures[index] && function.moduleScope == 1 && !function.receiver &&
                    abi.functions.at(function.name).sourceName == "lib::measure",
                "function instance order, exact nominal identity or defining module differs");
        constantReturn(function, 8);
    }
    for (std::size_t index = 0; index < buffers.size(); ++index) {
        const auto capacity = static_cast<int>(index + 3);
        const auto id = metadata.findClass(buffers[index]).value();
        const auto fields = metadata.fields(id);
        const auto leaves = metadata.leaves(id);
        const auto storage = metadata.storage(id);
        require(abi.records.at(buffers[index]).sourceName == "lib::Buffer" &&
                    abi.records.at(buffers[index]).members == std::vector<std::string>{"data"} &&
                    leaves.size() == static_cast<std::size_t>(capacity) &&
                    std::all_of(leaves.begin(), leaves.end(), [](const auto &type) { return type == aurora::Type::U8; }) &&
                    fields.size() == 1 && fields[0].elementType == aurora::Type::U8 && fields[0].firstLeaf == 0 &&
                    fields[0].length == capacity && fields[0].array && fields[0].elementCount == 1 &&
                    storage.sizeBytes == capacity && storage.alignment == 1 && storage.reservedBytes == 8 &&
                    storage.fieldOffsets.size() == 1 && storage.fieldOffsets.at(0) == 0,
                "concrete array instance lost its packed byte layout or ordered field metadata");
        const std::array<std::string, 3> names{
            "__au_k_m1_3dep_n2_3lib6Buffer_d6Buffer_t2_u8_v" + std::to_string(capacity),
            "__au_m_m1_3dep_n2_3lib6Buffer_d4size_t2_u8_v" + std::to_string(capacity),
            "__au_m_m1_3dep_n2_3lib6Buffer_d8own_size_t2_u8_v" + std::to_string(capacity)};
        const std::array<std::string, 3> sourceNames{"lib::Buffer", "lib::size", "lib::own_size"};
        for (std::size_t method = 0; method < names.size(); ++method) {
            const auto &source = bufferSyntax.methods[method];
            require(abi.functions.at(names[method]).sourceName == sourceNames[method] &&
                        abi.functions.at(names[method]).members.empty() && source.params.empty() &&
                        source.result == aurora::Type::I64 && source.constructor == (method == 0) &&
                        source.receiverConst == (method != 0) && source.publicAccess,
                    "method/constructor ABI identity or original source signature differs");
            if (method)
                require(std::none_of(module.functions.begin(),
                                     module.functions.end(),
                                     [&](const auto &function) {
                                         return function.name == names[method];
                                     }),
                        "unused imported getter escaped validated-IR pruning");
        }
        const auto &constructor = typedFunction(module, names[0]);
        require(constructor.moduleScope == 1 && constructor.receiver &&
                    constructor.receiver->className == buffers[index] && constructor.receiver->constructor &&
                    constructor.receiver->mutableValue && constructor.receiver->publicAccess &&
                    constructor.parameters.empty() && constructor.result == aurora::Type::I64 &&
                    constructor.code.size() == 3 &&
                    std::holds_alternative<aurora::ir::ReceiverArrayZero>(constructor.code[0]) &&
                    std::get<aurora::ir::ReceiverArrayZero>(constructor.code[0]).fieldIndex == 0 &&
                    std::holds_alternative<aurora::ir::Constant>(constructor.code[1]) &&
                    std::get<aurora::ir::Constant>(constructor.code[1]).value == 0 &&
                    std::holds_alternative<aurora::ir::Return>(constructor.code[2]),
                "concrete constructor lost its empty-array initialization");
    }
    const auto &answer = module.functions.at(2);
    require(answer.name == "answer" && answer.moduleScope == 0 && !answer.receiver,
            "root callable identity or dependency order differs");
    const auto constructors = typedInstructions<aurora::ir::MethodCall>(answer);
    require(constructors.size() == 3 && constructors[0].callee == constructors[2].callee &&
                constructors[0].callee == "__au_k_m1_3dep_n2_3lib6Buffer_d6Buffer_t2_u8_v3" &&
                constructors[1].callee == "__au_k_m1_3dep_n2_3lib6Buffer_d6Buffer_t2_u8_v4" &&
                constructors[0].receiverOffset != constructors[2].receiverOffset,
            "repeated constructions lost interned targets or independent object storage");
    const auto calls = typedInstructions<aurora::ir::Call>(answer);
    require(calls.size() == 3 && calls[0].callee == measures[0] && calls[1].callee == measures[1] &&
                calls[2].callee == measures[0],
            "typed calls lost repeated concrete-instance identity or source order");
    const auto enumValues = typedInstructions<aurora::ir::EnumConstant>(answer);
    require(enumValues.size() == 1 && enumValues[0].type.isEnum() && enumValues[0].type.className == state &&
                enumValues[0].caseIndex == 1,
            "typed enum expression lost its nominal identity or declaration ordinal");
    require(nominalViews(metadata, {{0, {100, 101, 102, 103, 104, 105}}, {1, {100, 101, 102, 104}}}),
            "template argument authority leaked into runtime reflection views");
    require(resolved.lintDiagnostics.size() == 1 &&
                resolved.lintDiagnostics[0].code == aurora::DiagnosticCode::UnreadLocal &&
                resolved.lintDiagnostics[0].message == "local binding 'state' is never read" &&
                resolved.lintDiagnostics[0].severity == aurora::DiagnosticSeverity::Warning,
            "typed root-only lint lost its scalar binding or diagnostic contract");
    const std::weak_ptr<const aurora::SourceText> retainedRoot = root;
    root.reset();
    rootTokens.clear();
    require(!retainedRoot.expired() && resolved.lintDiagnostics[0].span.source == retainedRoot.lock() &&
                spanText(resolved.lintDiagnostics[0].span) == "state",
            "typed lint lost immutable source ownership after Session cleanup");
    ++cases;
}

void resolvedVisibility() {
    context = "typed overload selection and direct-import reflection views";
    const auto resolved = [] {
        aurora::HostedResolution resolution;
        const auto root = resolution.add(std::make_shared<const aurora::SourceText>(
            "call.au", "module caller;import functions;auto answer()->i64{return choose(42);}"));
        const auto functions = resolution.add(
            std::make_shared<const aurora::SourceText>("functions.au",
                                                       "export module functions;import types;"
                                                       "export auto choose(Leaf value)->i64{return 1;}"
                                                       "export auto choose(i64 value)->i64{return value;}"
                                                       "auto choose(bool value)->i64{return 2;}"));
        const auto types = resolution.add(std::make_shared<const aurora::SourceText>(
            "types.au", "export module types;export class Leaf{public:i64 value;};class Hidden{public:i64 value;};"));
        return resolution.resolve({types.id, functions.id, root.id}, root.id, aurora::AnalysisMode::Check, true);
    }();
    const auto &module = resolved.module.get();
    const auto &metadata = resolved.module.metadata();
    const std::array<std::string, 3> overloads{"__au_o_m1_9functions_n0__d6choose_p1_295___au_c_m1_5types_n0__d4Leaf",
                                               "__au_o_m1_9functions_n0__d6choose_p1_20_",
                                               "__au_o_m1_9functions_n0__d6choose_p1_21_"};
    require(module.functions.size() == 2 && module.functions[0].name == overloads[1] &&
                module.functions[0].moduleScope == 2 &&
                module.functions[0].parameters == std::vector<aurora::Type>{aurora::Type::I64} &&
                module.functions[1].name == "answer" && module.functions[1].moduleScope == 0 &&
                resolved.abiDeclarations.functions.size() == 4 &&
                resolved.abiDeclarations.functions.at("answer").sourceName == "answer",
            "selected overload/root order or pre-pruning ABI inventory differs");
    for (std::size_t index = 0; index < overloads.size(); ++index) {
        require(resolved.abiDeclarations.functions.at(overloads[index]).sourceName == "choose",
                "overload parameter-tuple ABI identity differs");
        if (index != 1)
            require(std::none_of(module.functions.begin(),
                                 module.functions.end(),
                                 [&](const auto &function) {
                                     return function.name == overloads[index];
                                 }),
                    "unselected imported overload escaped validated-IR pruning");
    }
    const auto calls = typedInstructions<aurora::ir::Call>(module.functions.back());
    require(calls.size() == 1 && calls[0].callee == overloads[1],
            "typed overload selection chose a hidden or signature-inaccessible candidate");
    require(nominalViews(metadata, {{0, {}}, {1, {100, 101}}, {2, {100}}}),
            "reflection views lost an empty scope or granted private/transitive nominal types");
    ++cases;

    context = "private overload is not callable through a direct import";
    const auto rootSource = std::make_shared<const aurora::SourceText>(
        "private-call.au", "module caller;import functions;auto answer()->i64{return choose(true);}");
    std::optional<aurora::Diagnostic> rejected;
    try {
        aurora::HostedResolution resolution;
        const auto root = resolution.add(rootSource);
        const auto functions = resolution.add(std::make_shared<const aurora::SourceText>(
            "private-functions.au",
            "export module functions;export auto choose(i64 value)->i64{return value;}"
            "auto choose(bool value)->i64{return 2;}"));
        static_cast<void>(resolution.resolve({functions.id, root.id}, root.id));
    } catch (const aurora::Error &error) {
        rejected = error.diagnostic;
    }
    require(rejected && rejected->code == aurora::DiagnosticCode::Semantic &&
                rejected->message == "no exact ordinary overload for choose" && rejected->span.source == rootSource &&
                spanText(rejected->span) == "choose",
            "private overload rejection lost its exact typed decision or caller span");
    ++cases;

    context = "empty module views and returned lint source lifetime";
    std::weak_ptr<const aurora::SourceText> retained;
    const auto empty = [&] {
        aurora::HostedResolution resolution;
        auto source = std::make_shared<const aurora::SourceText>(
            "empty-view-root.au", "module caller;import empty;auto answer()->i64{const i64 unused=7;return 42;}");
        retained = source;
        const auto root = resolution.add(source);
        const auto imported =
            resolution.add(std::make_shared<const aurora::SourceText>("empty.au", "export module empty;"));
        return resolution.resolve({imported.id, root.id}, root.id, aurora::AnalysisMode::Lint);
    }();
    require(nominalViews(empty.module.metadata(), {{0, {}}, {1, {}}}) &&
                empty.abiDeclarations.records.empty() && empty.abiDeclarations.enums.empty() &&
                empty.abiDeclarations.functions.empty() && empty.lintDiagnostics.size() == 1 && !retained.expired() &&
                empty.lintDiagnostics[0].span.source == retained.lock() &&
                spanText(empty.lintDiagnostics[0].span) == "unused" &&
                empty.lintDiagnostics[0].span.source->path == "empty-view-root.au",
            "typed cleanup omitted empty views, ignored optional ABI collection or invalidated lint sources");
    ++cases;

    context = "instantiated template diagnostic retains its definition source";
    std::weak_ptr<const aurora::SourceText> definition;
    rejected.reset();
    try {
        aurora::HostedResolution resolution;
        auto source = std::make_shared<const aurora::SourceText>(
            "template-error.au", "export module dep;export template<Value T> auto bad()->i64{return true;}");
        definition = source;
        const auto imported = resolution.add(source);
        const auto root = resolution.add(
            std::make_shared<const aurora::SourceText>("template-request.au",
                                                       "module caller;import dep;class Hidden{public:i64 value;};"
                                                       "auto answer()->i64{return bad<Hidden>();}"));
        static_cast<void>(resolution.resolve({imported.id, root.id}, root.id));
    } catch (const aurora::Error &error) {
        rejected = error.diagnostic;
    }
    require(rejected && rejected->code == aurora::DiagnosticCode::Semantic &&
                rejected->message == "expected i64, got bool" && !definition.expired() &&
                rejected->span.source == definition.lock() && spanText(rejected->span) == "return" &&
                rejected->span.source->path == "template-error.au",
            "template semantic diagnostic lost original definition ownership or exact span");
    ++cases;
}

template <class Record> class GuardedRecord {
public:
    std::uint64_t before = canary;
    Record value;
    std::uint64_t after = canary;
    void check() const {
        require(before == canary && after == canary, "generated record write escaped its ABI extent");
    }
};

// Both owning inputs are constructed directly in their final transfer slots.
// Only generated scalar fields and copied readbacks are inspected by the host.
class RawResolution {
    Allocations &allocations;
    aurora::hosted::bytes::Region region;
    std::array<GuardedRecord<aurora::hosted_abi::ResolverIngest>, 2> slots;
    std::size_t active = 0;
    bool owner = false, pair = false;

public:
    bool transferred = false, failedTransfer = false;
    explicit RawResolution(Allocations &allocations)
        : allocations(allocations), region(32 * 1024 * 1024, allocations.allocator()) {
        static_assert(
            offsetof(aurora::hosted_abi::ResolverRelease, session) ==
                offsetof(aurora::hosted_abi::ResolverIngest, session) &&
            sizeof(aurora::hosted_abi::ResolverRelease) == offsetof(aurora::hosted_abi::ResolverIngest, parsed) &&
            offsetof(aurora::hosted_abi::ResolverReleasePair, parsed) ==
                offsetof(aurora::hosted_abi::ResolverIngest, parsed) &&
            sizeof(aurora::hosted_abi::ResolverReleasePair) == offsetof(aurora::hosted_abi::ResolverIngest, module));
        for (auto &slot : slots)
            slot.value.region = region.id();
        aurora::hosted_abi::ResolverCreate input;
        input.region = region.id();
        checked_hosted_resolver_create(&input, data());
        owner = true;
        guards();
    }
    ~RawResolution() {
        if (owner) {
            if (pair)
                checked_hosted_resolver_release_pair(&slots[active].value);
            else
                checked_hosted_resolver_release(&slots[active].value);
        }
    }
    RawResolution(const RawResolution &) = delete;
    RawResolution &operator=(const RawResolution &) = delete;
    void *data() {
        return slots[active].value.session.storage.data();
    }
    void guards() const {
        for (const auto &slot : slots)
            slot.check();
    }
    aurora::hosted_abi::compiler_resolver::SessionStatus status() {
        GuardedRecord<aurora::hosted_abi::compiler_resolver::SessionStatus> output;
        checked_hosted_resolver_status(data(), &output.value);
        output.check();
        guards();
        return output.value;
    }
    aurora::hosted_abi::compiler_resolver::MetaRow meta(std::int64_t index) {
        GuardedRecord<aurora::hosted_abi::compiler_resolver::MetaRow> output;
        checked_hosted_resolver_read_meta(data(), index, &output.value);
        output.check();
        guards();
        return output.value;
    }
    bool ingest(const std::string &source, bool invalidModule = false, bool invalidRoot = false) {
        using Storage = aurora::hosted_abi::compiler_resolver::StorageStatus;
        if (status().storage != Storage::none)
            return false;
        aurora::hosted_abi::ResolverSourceInput sourceInput;
        sourceInput.source.backing = source.data();
        sourceInput.source.length = static_cast<std::int64_t>(source.size());
        const auto module = checked_hosted_resolver_append_source(data(), &sourceInput);
        if (module < 0)
            return false;
        auto &record = slots[active].value;
        aurora::hosted_abi::ParserCreate create;
        create.region = region.id();
        create.capacity = 0;
        checked_hosted_parser_create(&create, record.parsed.storage.data());
        pair = true;
        aurora::hosted_abi::ParserInput input;
        input.source = sourceInput.source;
        input.cursor.line = 1;
        input.stop = Stop::module_definition;
        GuardedWords<6> parsed;
        checked_hosted_parser_parse(record.parsed.storage.data(), &input, parsed.value.data());
        parsed.check();
        guards();
        if (parsed.value[0] != wire(Status::success))
            return false;
        GuardedWords<14> admission;
        admission.value = {0,
                           static_cast<std::int64_t>(reinterpret_cast<std::uintptr_t>(source.data())),
                           0,
                           0,
                           0,
                           0,
                           static_cast<std::int64_t>(source.size()),
                           parsed.value[1]};
        std::copy(admissionConfiguration.begin(), admissionConfiguration.end(), admission.value.begin() + 8);
        GuardedWords<5> admitted;
        checked_hosted_parser_admit(record.parsed.storage.data(), admission.value.data(), admitted.value.data());
        admission.check();
        admitted.check();
        if (admitted.value[0] != wire(AdmissionStatus::success))
            return false;
        record.module = invalidModule ? module + 1 : module;
        record.root = invalidRoot ? -1 : parsed.value[1];
        const auto next = active ^ 1U;
        // A consuming call never has an armed input after transfer begins.
        owner = pair = false;
        // Only the index pool requests eight 80-byte rows during this transfer.
        // Infer the runtime's allocation header from the first empty owner.
        allocations.watchedBytes =
            allocations.initialBytes[0] + 8 * sizeof(aurora::hosted_abi::compiler_resolver::IndexRow);
        checked_hosted_resolver_ingest(&record, slots[next].value.session.storage.data());
        allocations.watchedBytes = 0;
        active = next;
        owner = true;
        transferred = true;
        guards();
        failedTransfer = status().storage != Storage::none;
        return !failedTransfer;
    }
    void finish() {
        require(owner, "resolution cleanup had no active returned owner");
        if (pair)
            checked_hosted_resolver_release_pair(&slots[active].value);
        else
            checked_hosted_resolver_release(&slots[active].value);
        owner = pair = false;
        guards();
        const auto final = region.metrics();
        require(final.used == 0 && final.live_allocations == 0 && final.releases == final.successful_allocations,
                "resolution transfer or pair cleanup leaked payload or owner metadata");
        require(region.close(), "released resolution region did not close");
    }
};

void rawResolutionOwnership() {
    namespace Wire = aurora::hosted_abi::compiler_resolver;
    using Index = Wire::IndexRow;
    static_assert(sizeof(Index) == 80 && alignof(Index) == 8);
    static_assert(offsetof(Index, domain) == 0 && offsetof(Index, key0) == 8 && offsetof(Index, key1) == 16 &&
                  offsetof(Index, key2) == 24 && offsetof(Index, key3) == 32 && offsetof(Index, payload) == 40 &&
                  offsetof(Index, left) == 48 && offsetof(Index, right) == 56 && offsetof(Index, parent) == 64 &&
                  offsetof(Index, height) == 72);
    static_assert(
        std::is_same_v<decltype(Index::domain), std::int64_t> && std::is_same_v<decltype(Index::key0), std::int64_t> &&
        std::is_same_v<decltype(Index::key1), std::int64_t> && std::is_same_v<decltype(Index::key2), std::int64_t> &&
        std::is_same_v<decltype(Index::key3), std::int64_t> && std::is_same_v<decltype(Index::payload), std::int64_t> &&
        std::is_same_v<decltype(Index::left), std::int64_t> && std::is_same_v<decltype(Index::right), std::int64_t> &&
        std::is_same_v<decltype(Index::parent), std::int64_t> && std::is_same_v<decltype(Index::height), std::int64_t>);
    namespace Lowering = aurora::hosted_abi::compiler_lowering;
    using Output = Lowering::OutputRow;
    using Operand = Lowering::OperandRow;
    using Local = Lowering::LocalRow;
    using Snapshot = Lowering::SnapshotRow;
    using Lane = Lowering::ArgumentLane;
    using Continuation = Lowering::ContinuationRow;
    using Result = Lowering::LoweringResult;
    // Literal physical expectations are independent of generated header checks.
    // Session remains opaque; copied rows expose only their named typed fields.
    static_assert(sizeof(Wire::Session) == 520 && alignof(Wire::Session) == 8);
    static_assert(sizeof(Output) == 64 && alignof(Output) == 8 && offsetof(Output, recordKind) == 0 &&
                  offsetof(Output, instructionForm) == 8 && offsetof(Output, unaryOperation) == 16 &&
                  offsetof(Output, binaryOperation) == 24 && offsetof(Output, comparisonOperation) == 32 &&
                  offsetof(Output, queryOperation) == 40 && offsetof(Output, operandBegin) == 48 &&
                  offsetof(Output, operandCount) == 56);
    static_assert(sizeof(Operand) == 40 && alignof(Operand) == 8 && offsetof(Operand, operandRole) == 0 &&
                  offsetof(Operand, signedValue) == 8 && offsetof(Operand, unsignedValue) == 16 &&
                  offsetof(Operand, sliceBegin) == 24 && offsetof(Operand, sliceCount) == 32);
    static_assert(sizeof(Snapshot) == 48 && alignof(Snapshot) == 8 && offsetof(Snapshot, sharedCount) == 0 &&
                  offsetof(Snapshot, objectSharedCount) == 8 && offsetof(Snapshot, liveValue) == 16 &&
                  offsetof(Snapshot, exclusiveValue) == 24 && offsetof(Snapshot, resourceActiveValue) == 32 &&
                  offsetof(Snapshot, objectExclusiveValue) == 40);
    static_assert(sizeof(Local) == 160 && alignof(Local) == 8 && offsetof(Local, nameSourceId) == 0 &&
                  offsetof(Local, concreteTypeId) == 8 && offsetof(Local, storageOffset) == 16 &&
                  offsetof(Local, scopeId) == 24 && offsetof(Local, previousBinding) == 32 &&
                  offsetof(Local, mutableValue) == 40 && offsetof(Local, borrowedObject) == 48 &&
                  offsetof(Local, lintEligible) == 56 && offsetof(Local, readValue) == 64 &&
                  offsetof(Local, ownerId) == 72 && offsetof(Local, spanOriginKind) == 80 &&
                  offsetof(Local, originLocalId) == 88 && offsetof(Local, spanFieldIndex) == 96 &&
                  offsetof(Local, temporaryParent) == 104 && offsetof(Local, sharedCount) == 112 &&
                  offsetof(Local, objectSharedCount) == 120 && offsetof(Local, liveValue) == 128 &&
                  offsetof(Local, exclusiveValue) == 136 && offsetof(Local, resourceActiveValue) == 144 &&
                  offsetof(Local, objectExclusiveValue) == 152);
    static_assert(sizeof(Lane) == 56 && alignof(Lane) == 8 && offsetof(Lane, argumentIndex) == 0 &&
                  offsetof(Lane, argumentKind) == 8 && offsetof(Lane, concreteTypeId) == 16 &&
                  offsetof(Lane, localId) == 24 && offsetof(Lane, loanId) == 32 &&
                  offsetof(Lane, serviceKindId) == 40 && offsetof(Lane, cleanupKind) == 48);
    static_assert(sizeof(Continuation) == 496 && alignof(Continuation) == 8 &&
                  offsetof(Continuation, continuationKind) == 0 && offsetof(Continuation, continuationPhase) == 8 &&
                  offsetof(Continuation, syntaxNode) == 16 && offsetof(Continuation, childCursor) == 24 &&
                  offsetof(Continuation, scopeHead) == 32 && offsetof(Continuation, localPrefixLength) == 40 &&
                  offsetof(Continuation, incomingSnapshotBase) == 48 &&
                  offsetof(Continuation, thenSnapshotBase) == 56 && offsetof(Continuation, firstLabel) == 64 &&
                  offsetof(Continuation, secondLabel) == 72 && offsetof(Continuation, childTypeId) == 80 &&
                  offsetof(Continuation, childLocalId) == 88 && offsetof(Continuation, callTarget) == 96 &&
                  offsetof(Continuation, capabilityRootLocal) == 104 &&
                  offsetof(Continuation, receiverFieldIndex) == 112 && offsetof(Continuation, nextArgument) == 120 &&
                  offsetof(Continuation, argumentCount) == 128 && offsetof(Continuation, outputMark) == 136 &&
                  offsetof(Continuation, operandMark) == 144 && offsetof(Continuation, cleanupCursor) == 152 &&
                  offsetof(Continuation, firstArgument) == 160 && offsetof(Continuation, secondArgument) == 216 &&
                  offsetof(Continuation, thirdArgument) == 272 && offsetof(Continuation, fourthArgument) == 328 &&
                  offsetof(Continuation, fifthArgument) == 384 && offsetof(Continuation, sixthArgument) == 440);
    static_assert(sizeof(Result) == 32 && alignof(Result) == 8 && offsetof(Result, result_status) == 0 &&
                  offsetof(Result, result_reason) == 8 && offsetof(Result, diagnostic_row) == 16 &&
                  offsetof(Result, root_row) == 24);
    static_assert(std::is_same_v<decltype(Output::instructionForm), Lowering::InstructionForm> &&
                  std::is_same_v<decltype(Operand::operandRole), Lowering::OperandRole> &&
                  std::is_same_v<decltype(Operand::unsignedValue), std::uint64_t> &&
                  std::is_same_v<decltype(Continuation::firstArgument), Lane> &&
                  std::is_same_v<decltype(Result::result_status), Lowering::LoweringStatus> &&
                  std::is_same_v<decltype(Result::result_reason), Lowering::LoweringError>);
    context = "resolved transfer allocation prefixes and generated cleanup records";
    std::string source = "export module raw;";
    for (std::size_t index = 0; index < 32; ++index)
        source += "auto f" + std::to_string(index) + "()->i64{return 1+2;}";
    std::size_t successful = 0;
    std::array<std::size_t, 11> initialBytes{};
    {
        Allocations allocations;
        RawResolution resolution(allocations);
        initialBytes = allocations.initialBytes;
        const auto emptyOwner = initialBytes[0];
        require(allocations.attempted == 11 && allocations.successful == 11 &&
                    initialBytes == std::array<std::size_t, 11>{emptyOwner,
                                                                emptyOwner,
                                                                emptyOwner + 64 * sizeof(Wire::MetaRow),
                                                                emptyOwner,
                                                                emptyOwner,
                                                                emptyOwner,
                                                                emptyOwner,
                                                                emptyOwner,
                                                                emptyOwner,
                                                                emptyOwner,
                                                                emptyOwner} &&
                    resolution.status().storage == Wire::StorageStatus::none,
                "Session creation did not retain six original owners followed by five empty typed pools");
        require(resolution.ingest(source) && resolution.transferred && allocations.observed > 0 &&
                    allocations.failedObserved == 0,
                "valid parser/session transfer did not populate the compact index owner");
        const auto first = resolution.meta(0);
        require(first.tag == Wire::MetaTag::module_unit && first.value10 >= 0,
                "successful transfer did not publish exactly one module root");
        require(resolution.ingest("export module second;auto next()->i64{return 3;}") &&
                    resolution.meta(0).value10 == first.value10 &&
                    resolution.meta(1).tag == Wire::MetaTag::module_unit &&
                    checked_hosted_resolver_count(resolution.data(), 5) == 2,
                "alternating owner slots lost an earlier module or the second transfer");
        require(checked_hosted_resolver_read_source(resolution.data(), 0) == 'e' &&
                    checked_hosted_resolver_read_source(resolution.data(), -1) == -1 &&
                    checked_hosted_resolver_read_source(resolution.data(),
                                                        checked_hosted_resolver_count(resolution.data(), 0)) == -1,
                "copied source bytes lost their checked bounds");
        successful = allocations.successful;
        resolution.finish();
        require(allocations.successful == allocations.released, "successful two-owner transfer leaked allocations");
    }
    {
        Allocations allocations;
        RawResolution resolution(allocations);
        require(allocations.initialBytes == initialBytes && allocations.successful == 11,
                "fresh Session did not repeat its eleven initial owner attempts");
        resolution.finish();
        require(allocations.released == 11, "fresh Session did not release all eleven owners");
        for (std::size_t index = 0; index < initialBytes.size(); ++index)
            require(allocations.releasedOwners[index] == allocations.initialOwners[10 - index],
                    "fresh Session did not release its eleven owners in reverse field order");
    }
    bool beforeTransfer = false, afterTransfer = false, indexFailure = false;
    std::size_t initialFailures = 0;
    for (std::size_t prefix = 0; prefix < successful; ++prefix) {
        Allocations allocations;
        allocations.allowed = prefix;
        RawResolution resolution(allocations);
        if (prefix < initialBytes.size()) {
            require(allocations.attempted == 11 && allocations.successful == prefix &&
                        allocations.initialBytes == initialBytes &&
                        resolution.status().storage == Wire::StorageStatus::allocation,
                    "initial owner failure skipped a declared allocation or published a usable Session");
            ++initialFailures;
        }
        bool complete = resolution.ingest(source);
        if (complete)
            complete = resolution.ingest("export module second;auto next()->i64{return 3;}");
        require(!complete, "reachable resolution allocation prefix did not fail");
        beforeTransfer = beforeTransfer || !resolution.transferred;
        afterTransfer = afterTransfer || resolution.failedTransfer;
        if (allocations.failedObserved != 0) {
            const auto attempts = allocations.attempted;
            require(resolution.failedTransfer && resolution.status().storage == Wire::StorageStatus::allocation &&
                        !resolution.ingest(source) && allocations.attempted == attempts &&
                        resolution.meta(0).tag == Wire::MetaTag::module_source && resolution.meta(0).value10 == -1,
                    "compact index growth failure was not sticky or published a module root");
            indexFailure = true;
        }
        resolution.finish();
        require(allocations.successful == allocations.released, "failed transfer retained a consumed owner");
        if (prefix < initialBytes.size())
            for (std::size_t index = 0; index < prefix; ++index)
                require(allocations.releasedOwners[index] == allocations.initialOwners[prefix - index - 1],
                        "failed initial Session did not release its owner prefix in reverse order");
    }
    require(beforeTransfer && afterTransfer && indexFailure && initialFailures == 11,
            "failure sweep missed an initial owner, compact index growth, live pair or returned Session boundary");
    for (const auto &[badModule, badRoot] : {std::pair{true, false}, std::pair{false, true}}) {
        Allocations allocations;
        RawResolution resolution(allocations);
        require(!resolution.ingest(source, badModule, badRoot) && resolution.transferred &&
                    resolution.status().storage == Wire::StorageStatus::invalid &&
                    resolution.meta(0).tag == Wire::MetaTag::module_source && resolution.meta(0).value10 == -1,
                "invalid consumed transfer published a root or lost its returned owner");
        resolution.finish();
        require(allocations.successful == allocations.released, "invalid transfer leaked one of its owning inputs");
    }
    {
        Allocations allocations;
        RawResolution resolution(allocations);
        require(!resolution.ingest("module broken;auto f()->i64{") && !resolution.transferred,
                "parser failure crossed the consuming transfer boundary");
        resolution.finish();
        require(allocations.successful == allocations.released, "parse failure did not release the live owner pair");
    }
    ++cases;
}

// Keep a compact independent declaration inventory for the typed transport.
// Production lowering and its actual implementation sources are exercised below.
void loweringSchemaSources(const std::vector<aurora::Token> &tokens,
                           const aurora::Program &program,
                           std::size_t module) {
    static const std::array<std::vector<ContainerAst>, 3> classes{{
        {},
        {{"LoweringResult",
          true,
          "-result_status -result_reason -diagnostic_row -root_row",
          "+LoweringResult +status +reason +diagnostic_payload_row +module_root"}},
        {{"OutputRow",
          true,
          "-recordKind -instructionForm -unaryOperation -binaryOperation -comparisonOperation -queryOperation "
          "-operandBegin -operandCount",
          "+OutputRow +kind +form +unary_operation +binary_operation +comparison_operation +query +operand_begin "
          "+operand_count +set_unary +set_binary +set_comparison +set_query +discard_instruction"},
         {"OperandRow",
          true,
          "-operandRole -signedValue -unsignedValue -sliceBegin -sliceCount",
          "+OperandRow +role +signed_value +unsigned_value +begin +count"},
         {"SnapshotRow",
          true,
          "-sharedCount -objectSharedCount -liveValue -exclusiveValue -resourceActiveValue -objectExclusiveValue",
          "+SnapshotRow +shared_count +object_shared_count +live +exclusive +resource_active +object_exclusive"},
         {"LocalRow",
          true,
          "-nameSourceId -concreteTypeId -storageOffset -scopeId -previousBinding -mutableValue -borrowedObject "
          "-lintEligible -readValue -ownerId -spanOriginKind -originLocalId -spanFieldIndex -temporaryParent "
          "-sharedCount -objectSharedCount -liveValue -exclusiveValue -resourceActiveValue -objectExclusiveValue",
          "+LocalRow +name_source_id +concrete_type_id +offset +scope_id +previous_binding +mutable_value "
          "+borrowed_object +lint_eligible +was_read +owner_id +span_origin_kind +origin_local_id +span_field_index "
          "+temporary_parent +set_binding_flags +set_origin +mark_read +state +set_state"},
         {"ArgumentLane",
          true,
          "-argumentIndex -argumentKind -concreteTypeId -localId -loanId -serviceKindId -cleanupKind",
          "+ArgumentLane +index +kind +concrete_type_id +local_id +loan_id +service_kind_id +cleanup_kind "
          "+set_cleanup"},
         {"ContinuationRow",
          true,
          "-continuationKind -continuationPhase -syntaxNode -childCursor -scopeHead -localPrefixLength "
          "-incomingSnapshotBase -thenSnapshotBase -firstLabel -secondLabel -childTypeId -childLocalId -callTarget "
          "-capabilityRootLocal -receiverFieldIndex -nextArgument -argumentCount -outputMark -operandMark "
          "-cleanupCursor -firstArgument -secondArgument -thirdArgument -fourthArgument -fifthArgument -sixthArgument",
          "+ContinuationRow +kind +phase +syntax_node +cursor +scope_head +local_prefix_length "
          "+incoming_snapshot_base +then_snapshot_base +first_label +second_label +child_type_id +child_local_id "
          "+call_target +capability_root_local +receiver_field_index +next_argument +argument_count +output_mark "
          "+operand_mark +cleanup_cursor +set_phase +set_cursor +set_scope +set_snapshots +set_labels +set_child "
          "+set_call +set_next_argument +set_marks +set_cleanup_cursor +argument +set_argument"}},
    }};
    static const std::array<std::vector<std::pair<const char *, std::size_t>>, 3> enums{{
        {{"InstructionForm", 84},
         {"Unary", 3},
         {"Binary", 10},
         {"Comparison", 6},
         {"Query", 2},
         {"RecordKind", 27},
         {"OperandRole", 100},
         {"SpanOriginKind", 5},
         {"ContinuationKind", 7},
         {"ContinuationPhase", 14},
         {"ArgumentKind", 7},
         {"CleanupKind", 6}},
        {{"LoweringStatus", 4}, {"LoweringError", 243}},
        {},
    }};
    static const std::array<const char *, 3> functions{
        "", "", "make_output_pool make_operand_pool make_local_pool make_snapshot_pool make_continuation_pool"};
    require(program.classes.size() == classes.at(module).size() && program.enums.size() == enums.at(module).size() &&
                program.templates.empty() && program.functionTemplates.empty() &&
                program.namespaces == std::set<std::string>{"compiler_lowering"},
            "lowering schema class/enum/template/namespace inventory differs");
    for (std::size_t index = 0; index < classes[module].size(); ++index)
        sameContainer(program.classes[index], tokens, "compiler_lowering", classes[module][index]);
    for (std::size_t index = 0; index < enums[module].size(); ++index) {
        const auto &actual = program.enums[index];
        const auto &[name, count] = enums[module][index];
        require(actual.name == name && actual.cases.size() == count && actual.scope == "compiler_lowering" &&
                    actual.exported && actual.id == 0,
                "lowering schema enum name, case count or unresolved identity differs");
    }
    const auto names = words(functions[module]);
    require(program.functions.size() == names.size(), "lowering schema free-function inventory differs");
    for (std::size_t index = 0; index < names.size(); ++index)
        require(program.functions[index].token.text == names[index] && program.functions[index].exported &&
                    program.functions[index].scope == "compiler_lowering",
                "lowering schema factory name/export/order differs");
    ++cases;
}

void loweringImplementationSources(const std::vector<aurora::Token> &tokens,
                                   const aurora::Program &program,
                                   std::size_t module) {
    static const std::array<std::vector<ContainerAst>, 10> classes{{
        {},
        {{"LoweringConfig",
          true,
          "-byteLeaves -nonByteLeaves -totalLeaves -copiedBytes -byteArrayLength -scalarArrayLength -analysisMode "
          "-serviceGroups",
          "+LoweringConfig +byte_leaves +non_byte_leaves +total_leaves +copied_bytes +byte_array_length "
          "+scalar_array_length +mode +service_groups +set_policy"},
         {"ScalarSeed", true, "-concreteKind -publicId -byteSize", "+ScalarSeed +concrete_kind +public_id +byte_size"},
         {"ServiceParameters",
          true,
          "-parameterCount -firstType -secondType -thirdType -fourthType -fifthType",
          "+ServiceParameters +count +type_at"},
         {"ServiceSeed",
          true,
          "-receiverKind -kindId -operationId -spellingSource -resultType -parameterTypes",
          "+ServiceSeed +receiver_kind +kind_id +operation_id +spelling_source +result_type +parameters"}},
        {},
        {{"LocalRequest",
          true,
          "-nameRef -typeId -sourceRef -mutableValue -bindValue -beginValue -ownerId -originKind -originId -fieldId "
          "-temporaryParent -borrowedValue -lintValue -borrowedRoot",
          "+LocalRequest +name +type +source +mutable_value +bind +begin +owner +origin +origin_id +field +temporary "
          "+borrowed +lint +borrowed_root +set_borrowed_root +set_origin +set_flags"},
         {"LiteralValue",
          true,
          "-typeId -signedValue -unsignedValue -validValue",
          "+LiteralValue +type +signed_value +unsigned_value +valid"}},
        {},
        {},
        {{"IndexedStorage", true, "-rootId -fieldId -typeId", "+IndexedStorage +root +field +type"}},
        {},
        {{"FunctionBodyResult", true, "-functionRow -nextLabel", "+FunctionBodyResult +function_row +next_label"}},
        {},
    }};
    static const std::array<const char *, 10> entries{"fail_pair",
                                                      "begin_lowering",
                                                      "prepare_types",
                                                      "add_local",
                                                      "push_frame",
                                                      "begin_call",
                                                      "begin_expression",
                                                      "begin_local",
                                                      "lower_function_body",
                                                      "run_lowering"};
    require(program.classes.size() == classes.at(module).size() && program.enums.empty() && program.templates.empty() &&
                program.functionTemplates.empty() && program.namespaces == std::set<std::string>{"compiler_lowering"},
            "typed implementation class/enum/template/namespace inventory differs");
    for (std::size_t index = 0; index < classes[module].size(); ++index)
        sameContainer(program.classes[index], tokens, "compiler_lowering", classes[module][index]);
    require(std::count_if(program.functions.begin(),
                          program.functions.end(),
                          [&](const auto &function) {
                              return function.name == entries[module] && function.scope == "compiler_lowering" &&
                                     function.exported;
                          }) == 1,
            "typed implementation lost its source entry");
    // Lexical function/constructor/field inventories cover every helper without
    // storing another per-helper semantic or native-name oracle here.
    bootstrapDeclarationTypes(tokens, program, 6 + module);
    ++cases;
}

void resolvedCompilerSources(char **paths) {
    context = "all twenty-six real compiler modules through production typed lowering";
    const std::array<std::size_t, 26> arguments{0,  1,  2,  15, 19, 20, 21, 32, 16, 33, 34, 17, 22,
                                                23, 24, 25, 28, 29, 30, 31, 26, 27, 35, 37, 38, 18};
    const std::array<std::string, 26> modules{"lexer",
                                              "syntax_arena",
                                              "parser",
                                              "resolution_kinds",
                                              "lowering_kinds",
                                              "lowering_errors",
                                              "lowering_storage",
                                              "resolution_rows",
                                              "resolution_arena",
                                              "resolution_names",
                                              "resolution_ingest",
                                              "resolver",
                                              "lowering_common",
                                              "lowering_configuration",
                                              "lowering_types",
                                              "lowering_values",
                                              "lowering_frames",
                                              "lowering_calls",
                                              "lowering_expressions",
                                              "lowering_statements",
                                              "lowering_body",
                                              "lowering",
                                              "ir_graph",
                                              "ir_metadata_storage",
                                              "ir_metadata",
                                              "frontend"};
    const std::array<std::vector<std::string>, 26> classNames{{
        {"Cursor", "Lexeme"},
        {"ParseFrame", "AstNode", "ChildEdge", "TypeSyntax", "SyntaxNode", "AstArena"},
        {"AdmissionConfig",
         "AdmissionResult",
         "TypeContext",
         "ParseResult",
         "ParseToken",
         "TypeResult",
         "HeaderResult",
         "AdmissionProgress",
         "AdmissionType",
         "AdmissionScope"},
        {},
        {},
        {"LoweringResult"},
        {"OutputRow", "OperandRow", "SnapshotRow", "LocalRow", "ArgumentLane", "ContinuationRow"},
        {"SyntaxRow", "MetaRow", "IndexRow", "ResolvedRow", "WorkRow", "SessionStatus"},
        {"Session"},
        {},
        {},
        {"BindContext", "Arguments"},
        {},
        {"LoweringConfig", "ScalarSeed", "ServiceParameters", "ServiceSeed"},
        {},
        {"LocalRequest", "LiteralValue"},
        {},
        {},
        {"IndexedStorage"},
        {},
        {"FunctionBodyResult"},
        {},
        {"FunctionRow", "IndexRow", "StateRow", "ReverseEdge", "FrameRow", "Input", "Workspace"},
        {"ByteRange",
         "IndexRange",
         "RawTypeTail",
         "RawTypeRow",
         "ClassRow",
         "FieldRow",
         "PhysicalExtent",
         "StorageRow",
         "IndexRow",
         "DescriptorRow",
         "ViewRow",
         "EnumRow",
         "ClassResultRow",
         "FrameRow",
         "CoreCounts",
         "MapCounts",
         "InputCounts",
         "MetadataStore"},
        {},
        {},
    }};
    // Frontend's direct imports give this DFS postorder, independent of file argv.
    std::array<aurora::Program, 26> syntax;
    std::array<aurora::HostedModule, 26> headers;
    const auto resolved = [&] {
        aurora::HostedResolution resolution;
        for (std::size_t index = 0; index < modules.size(); ++index) {
            std::ifstream input(paths[arguments[index]], std::ios::binary);
            require(bool(input), "cannot read real compiler source");
            std::string text((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
            require(!input.bad(), "cannot finish reading real compiler source");
            const auto source = std::make_shared<const aurora::SourceText>(paths[arguments[index]], std::move(text));
            const auto tokens = aurora::lex(source);
            syntax[index] = checkedProgram(tokens);
            if (index >= 4 && index <= 6) {
                bootstrapDeclarationTypes(tokens, syntax[index], index - 1);
                loweringSchemaSources(tokens, syntax[index], index - 4);
            }
            if (index >= 12 && index <= 21)
                loweringImplementationSources(tokens, syntax[index], index - 12);
            headers[index] = resolution.add(source);
            require(headers[index].moduleName == "aurora.compiler." + modules[index] && headers[index].interfaceUnit &&
                        syntax[index].classes.size() == classNames[index].size(),
                    "actual compiler module/header/class inventory changed");
            for (std::size_t declaration = 0; declaration < classNames[index].size(); ++declaration)
                require(syntax[index].classes[declaration].token.text == classNames[index][declaration],
                        "actual compiler class declaration order changed");
        }
        std::vector<std::size_t> dependencyOrder;
        for (const auto &header : headers)
            dependencyOrder.push_back(header.id);
        return resolution.resolve(dependencyOrder, headers.back().id, aurora::AnalysisMode::Check, true);
    }();
    const auto &module = resolved.module.get();
    const auto &metadata = resolved.module.metadata();
    const auto &abi = resolved.abiDeclarations;
    require(metadata.scopeCount() == modules.size() && resolved.lintDiagnostics.empty(),
            "actual compiler typed graph omitted a scope or emitted lint in check mode");
    const auto native = [&](const auto &declarations, const std::string &name) -> const std::string & {
        const auto found = std::find_if(declarations.begin(), declarations.end(), [&](const auto &entry) {
            return entry.second.sourceName == name;
        });
        require(found != declarations.end() && std::count_if(declarations.begin(),
                                                             declarations.end(),
                                                             [&](const auto &entry) {
                                                                 return entry.second.sourceName == name;
                                                             }) == 1,
                "compiler source ABI declaration was omitted or duplicated: " + name);
        return found->first;
    };
    const auto qualified = [](const std::string &scope, const std::string &name) {
        return scope.empty() ? name : scope + "::" + name;
    };
    std::size_t functions = 0, retainedFunctions = 0, classes = 0, enums = 0, methods = 0, fields = 0;
    std::set<std::string> identities;
    std::multiset<std::string> sourceFunctionNames, abiFunctionNames;
    for (const auto &[name, declaration] : abi.functions) {
        static_cast<void>(name);
        abiFunctionNames.insert(declaration.sourceName);
    }
    for (std::size_t index = 0; index < syntax.size(); ++index) {
        const auto scope = index + 1 == syntax.size() ? 0 : static_cast<int>(index + 1);
        const auto function = [&](const aurora::Function &source,
                                  const std::string &sourceName,
                                  const std::string &receiver) {
            // Legacy ABI method source names contain the namespace and method,
            // not the owning class. Typed receiver identity disambiguates them.
            const auto matches = [&](const auto &candidate) {
                const auto declaration = abi.functions.find(candidate.name);
                return declaration != abi.functions.end() && declaration->second.sourceName == sourceName &&
                       candidate.moduleScope == scope &&
                       (receiver.empty() ? !candidate.receiver || candidate.borrowedParameter
                                         : candidate.receiver && !candidate.borrowedParameter &&
                                               candidate.receiver->className == receiver);
            };
            ++functions;
            sourceFunctionNames.insert(sourceName);
            const auto found = std::find_if(module.functions.begin(), module.functions.end(), matches);
            if (found == module.functions.end()) {
                require(scope != 0, "compiler root callable was discarded: " + sourceName);
                return;
            }
            require(std::count_if(module.functions.begin(), module.functions.end(), matches) == 1,
                    "compiler retained callable/source identity was duplicated: " + sourceName);
            const auto &actual = *found;
            require(identities.insert(actual.name).second && actual.moduleScope == scope &&
                        actual.borrowedParameter == (!source.params.empty() && source.params.front().borrowed &&
                                                     !source.params.front().type.isService()) &&
                        bool(actual.secondBorrowedParameter) ==
                            (actual.borrowedParameter && source.params.size() > 1 && source.params[1].borrowed) &&
                        actual.parameters.size() == source.params.size() - std::size_t(actual.borrowedParameter) -
                                                        std::size_t(bool(actual.secondBorrowedParameter)) &&
                        bool(actual.receiver) == (!receiver.empty() || actual.borrowedParameter),
                    "compiler typed callable identity, module or receiver presence differs");
            if (!receiver.empty())
                require(actual.receiver->className == receiver && actual.receiver->constructor == source.constructor &&
                            actual.receiver->mutableValue == !source.receiverConst &&
                            actual.receiver->publicAccess == source.publicAccess,
                        "compiler typed method receiver, constructor or visibility differs");
            ++retainedFunctions;
        };
        for (const auto &source : syntax[index].functions)
            function(source, qualified(source.scope, source.token.text), {});
        for (const auto &source : syntax[index].classes) {
            const auto sourceName = qualified(source.scope, source.token.text);
            const auto &name = native(abi.records, sourceName);
            const auto classId = metadata.findClass(name).value();
            const auto shape = metadata.fields(classId);
            const auto storage = metadata.storage(classId);
            require(identities.insert(name).second && shape.size() == source.fields.size() &&
                        storage.fieldOffsets.size() == shape.size(),
                    "compiler class lost its nominal layout or logical field inventory");
            std::vector<std::string> names;
            for (const auto &field : source.fields)
                names.push_back(field.token.text);
            require(abi.records.at(name).members == names, "compiler ABI field source order differs");
            fields += names.size();
            for (const auto &method : source.methods) {
                function(method, qualified(method.scope, method.token.text), name);
                ++methods;
            }
            ++classes;
        }
        for (const auto &source : syntax[index].enums) {
            const auto &name = native(abi.enums, qualified(source.scope, source.token.text));
            std::vector<std::string> names;
            for (const auto &value : source.cases)
                names.push_back(value.text);
            require(identities.insert(name).second && abi.enums.at(name).members == names &&
                        metadata.enumCases(metadata.findEnum(name).value()) == static_cast<int>(names.size()),
                    "compiler enum source order or typed case count differs");
            ++enums;
        }
    }
    require(enums == 38 && classes == 67 && fields > 228 && methods > 307 &&
                retainedFunctions == module.functions.size() && functions == abi.functions.size() &&
                sourceFunctionNames == abiFunctionNames,
            "real compiler typed graph omitted or appended an unaccounted declaration");
    ++cases;
}

void rawModules() {
    static_assert(static_cast<std::int64_t>(Stop::module_definition) == 12 &&
                  wire(SyntaxKind::module_definition) == 21 && wire(SyntaxKind::namespace_definition) == 22 &&
                  wire(SyntaxKind::class_definition) == 23 && wire(SyntaxKind::declaration) == 24 &&
                  wire(SyntaxKind::template_scalar) == 25 && wire(SyntaxKind::template_value) == 26 &&
                  wire(SyntaxKind::template_capacity) == 27);
    context = "raw whole-module container/template records";
    const std::string small = "export module m;namespace n{template<Scalar T,i64 N>class C{T value;};}";
    const std::vector<SyntaxWords> expected{
        {17, 2, 4, -1, -1, -1, -1, 2, -1, -1, 1, -1},
        {25, 10, 11, -1, -1, -1, -1, -1, -1, -1, 0, -1},
        {27, 13, 14, 1, -1, -1, -1, -1, -1, -1, 0, -1},
        {16, 18, 21, -1, -1, -1, 0, 19, -1, -1, 0, -1},
        {24, 18, 21, -1, -1, -1, -1, -1, 3, -1, 0, -1},
        {23, 16, 23, -1, -1, -1, -1, -1, 4, -1, 0, -1},
        {24, 16, 23, -1, -1, -1, -1, -1, 5, 2, 0, -1},
        {22, 5, 24, -1, -1, -1, -1, 5, 6, -1, 0, -1},
        {24, 5, 24, -1, -1, -1, -1, -1, 7, -1, 0, -1},
        {21, 0, 24, -1, -1, -1, -1, -1, 0, 8, 0, -1},
    };
    {
        Allocations allocations;
        RawArena arena(allocations);
        require(arena.parse(small, Stop::module_definition) ==
                        Words{wire(Status::success), 9, 0, 24, static_cast<std::int64_t>(small.size()), 0} &&
                    arena.syntaxCount() == 10 && arena.types() == 1 && arena.edges() == 0,
                "whole-module root/count/EOF differs");
        for (std::size_t index = 0; index < expected.size(); ++index)
            require(arena.syntax(index) == expected[index], "container/template copied record differs");
        require(arena.type(0) == TypeWords{6, 18, 18, 36, -1, -1, 18, 3},
                "class template context lost its source-backed parameter type");
        require(arena.admit(small, 9) == AdmissionWords{wire(AdmissionStatus::success), -1, -1, -1, 0},
                "interface module admission rejected a class-only declaration");
        arena.finish();
        require(allocations.successful == allocations.released, "whole-module records leaked an owner");
        ++cases;
    }
    // Module-function presence belongs to the separate admission stage, after grammar.
    {
        const std::string source = "module declarations;class C{};";
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(source, Stop::module_definition);
        require(result[0] == wire(Status::success) && result[3] == 8 &&
                    arena.syntax(result[1])[0] == wire(SyntaxKind::module_definition),
                "raw module grammar acquired function-presence admission");
        require(arena.admit(source, result[1]) == AdmissionWords{wire(AdmissionStatus::missing_function), 8, 9, -1, 0},
                "post-grammar module admission lost its EOF diagnostic");
        arena.finish();
        require(allocations.successful == allocations.released, "class-only module leaked an owner");
        ++cases;
    }
    {
        Allocations allocations;
        RawArena arena(allocations);
        require(arena.parse(small, Stop::module_definition, 0, {0, 6, 0, 0, 0, 0, 1})[0] == wire(Status::invalid),
                "whole-module input accepted caller-supplied template context");
        arena.finish();
        require(allocations.successful == allocations.released, "invalid module context leaked an owner");
        ++cases;
    }
    context = "whole-module independent-owner growth and failure cleanup";
    constexpr std::int64_t width = 33, nesting = 9;
    std::string source = "export module wide;";
    for (std::int64_t index = 0; index < nesting; ++index)
        source += "namespace n{";
    for (std::int64_t index = 0; index < width; ++index)
        source += "auto f_" + std::to_string(index) + "()->i64{return g(1,2);}";
    source += std::string(nesting, '}');
    const auto tokens = aurora::lex(source, "module-growth.au");
    const auto end = static_cast<std::int64_t>(tokens.size() - 1), syntaxCount = 2 + 2 * nesting + 4 * width;
    std::size_t successful = 0;
    {
        Allocations allocations;
        RawArena arena(allocations);
        require(arena.parse(source, Stop::module_definition) == Words{wire(Status::success),
                                                                      syntaxCount - 1,
                                                                      3 * width,
                                                                      end,
                                                                      static_cast<std::int64_t>(source.size()),
                                                                      0} &&
                    arena.syntaxCount() == syntaxCount && arena.edges() == 2 * width && arena.types() == width,
                "module growth omitted a declaration forest or failed to consume EOF");
        const auto root = arena.syntax(syntaxCount - 1);
        require(root == SyntaxWords{21, 0, end, -1, -1, -1, -1, -1, 0, syntaxCount - 2, 0, -1},
                "module growth root did not own its complete preamble/declaration forest");
        const auto metrics = arena.metrics();
        require(metrics.live_allocations == 5 && metrics.peak_live_allocations == 5 &&
                    metrics.successful_allocations > 10,
                "module growth changed the five independent owners");
        successful = allocations.successful;
        arena.finish();
        require(allocations.successful == allocations.released, "module growth leaked an owner");
        ++cases;
    }
    for (std::size_t allowed = 0; allowed < successful; ++allowed) {
        Allocations allocations;
        allocations.allowed = allowed;
        RawArena arena(allocations);
        const auto result = arena.parse(source, Stop::module_definition);
        require(result[0] == wire(Status::allocation_failure) && result[1] == -1,
                "module partial allocation exposed a complete root");
        if (arena.syntaxCount() > 0)
            require(arena.syntax(0) == SyntaxWords{17, 2, 4, -1, -1, -1, -1, 2, -1, -1, 1, -1},
                    "module growth failure changed a committed preamble");
        arena.finish();
        require(allocations.successful == allocations.released, "failed module parse leaked an owner");
        ++cases;
    }
}

void rawAdmission() {
    // Independent copied configuration controls exercise the private entry,
    // while production policy messages stay in the existing whole-module tables.
    struct Fixture {
        const char *source;
        AdmissionConfigWords configuration;
        AdmissionWords expected;
    };
    for (const auto &fixture : std::vector<Fixture>{
             {"export module admitted;class C{array<i64,65> values;};",
              admissionConfiguration,
              {wire(AdmissionStatus::array_capacity), 14, 15, -1, 64}},
             {"export module admitted;class C{array<i64,65> values;};",
              {65, 512, 62, 1, 2, 4},
              {wire(AdmissionStatus::success), -1, -1, -1, 0}},
             {"module admitted;auto f(builtin::ConsoleSession& first,builtin::DisplaySession& second)->i64{}",
              admissionConfiguration,
              {wire(AdmissionStatus::success), -1, -1, -1, 0}},
             {"module admitted;auto f(builtin::ConsoleSession& first,builtin::DisplaySession& second)->i64{}",
              {64, 512, 54, 1, 2, 4},
              {wire(AdmissionStatus::borrowed_parameter), 16, 17, -1, 0}}}) {
        context = "copied declaration admission configuration";
        Allocations allocations;
        RawArena arena(allocations);
        const auto parsed = arena.parse(fixture.source, Stop::module_definition);
        require(parsed[0] == wire(Status::success), "configuration fixture failed grammar before admission");
        require(arena.admit(fixture.source, parsed[1], fixture.configuration) == fixture.expected,
                "admission ignored its copied scalar limit or supported service-group mask");
        arena.finish();
        require(allocations.successful == allocations.released, "configuration admission leaked an owner");
        ++cases;
    }
    context = "post-grammar admission scratch growth and every allocation failure";
    constexpr std::size_t width = 513;
    std::string source = "module admitted;auto wide(";
    for (std::size_t index = 0; index < width; ++index)
        source += (index ? "," : "") + std::string("i64 p") + std::to_string(index);
    source += ")->i64{return p0;}auto later()->i64{return 0;}";
    // The later declaration remains pending while wide parameter scratch grows.
    // Only admission allocations are denied. Every iteration first establishes
    // a complete valid grammar forest and then checks that all records survive.
    for (std::size_t budget = 0;; ++budget) {
        Allocations allocations;
        RawArena arena(allocations);
        const auto parsed = arena.parse(source, Stop::module_definition);
        require(parsed[0] == wire(Status::success), "wide admission fixture did not complete grammar");
        std::vector<NodeWords> nodes;
        std::vector<TypeWords> types;
        std::vector<SyntaxWords> syntax;
        for (std::int64_t index = 0; index < parsed[2]; ++index)
            nodes.push_back(arena.read(index));
        for (std::int64_t index = 0; index < arena.types(); ++index)
            types.push_back(arena.type(index));
        for (std::int64_t index = 0; index < arena.syntaxCount(); ++index)
            syntax.push_back(arena.syntax(index));
        const auto grammarAllocations = allocations.successful;
        allocations.allowed = grammarAllocations + budget;
        const auto admitted = arena.admit(source, parsed[1]);
        const bool success = admitted[0] == wire(AdmissionStatus::success);
        require(admitted ==
                    AdmissionWords{
                        wire(success ? AdmissionStatus::success : AdmissionStatus::allocation_failure), -1, -1, -1, 0},
                "admission allocation failure published policy metadata or imposed a parameter limit");
        require(checked_hosted_parser_count(arena.data()) == parsed[2] &&
                    arena.types() == static_cast<std::int64_t>(types.size()) &&
                    arena.syntaxCount() == static_cast<std::int64_t>(syntax.size()) && arena.edges() == 0,
                "admission changed grammar forest counts");
        for (std::size_t index = 0; index < nodes.size(); ++index)
            require(arena.read(index) == nodes[index], "admission changed a committed expression");
        for (std::size_t index = 0; index < types.size(); ++index)
            require(arena.type(index) == types[index], "admission changed a committed type");
        for (std::size_t index = 0; index < syntax.size(); ++index)
            require(arena.syntax(index) == syntax[index], "admission changed a committed declaration");
        const auto metrics = arena.metrics();
        require(metrics.live_allocations == 5 && metrics.peak_live_allocations == 5,
                "admission acquired a sixth owner or lost an existing owner");
        if (success) {
            require(budget > 0 && allocations.successful - grammarAllocations == budget,
                    "admission sweep skipped a failing scratch allocation or never grew scratch");
            const auto beforeRepeat = allocations.successful;
            require(arena.admit(source, parsed[1]) == admitted && allocations.successful == beforeRepeat,
                    "repeated admission retained stale scratch context or regrew completed storage");
        }
        arena.finish();
        require(allocations.successful == allocations.released, "admission scratch failure leaked an existing owner");
        ++cases;
        if (success)
            break;
    }
}

void rawBodies() {
    static_assert(sizeof(SyntaxWords) == 96 && static_cast<std::int64_t>(Stop::body) == 4);
    static_assert(wire(SyntaxKind::block) == 1 && wire(SyntaxKind::local) == 2 && wire(SyntaxKind::return_value) == 3 &&
                  wire(SyntaxKind::static_assertion) == 4 && wire(SyntaxKind::conditional) == 5 &&
                  wire(SyntaxKind::loop) == 6 && wire(SyntaxKind::expression) == 7 && wire(SyntaxKind::assign) == 8 &&
                  wire(SyntaxKind::field_assign) == 9 && wire(SyntaxKind::index_assign) == 10);
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
            const auto result = arena.parse(text, Stop::body);
            require(result == Words{wire(Status::success),
                                    nested ? 127 : width,
                                    nested ? 0 : width,
                                    nested ? 256 : 2 * width + 2,
                                    static_cast<std::int64_t>(text.size()),
                                    0} &&
                        arena.syntaxCount() == (nested ? 128 : width + 1),
                    "body growth result differs");
            if (nested) {
                for (std::int64_t i = 0; i < 128; ++i)
                    require(arena.syntax(i) == SyntaxWords{1, 127 - i, 129 + i, -1, -1, -1, -1, -1, i - 1, -1, 0, -1},
                            "nested block ABI differs");
            } else {
                for (std::int64_t i = 0; i < width; ++i) {
                    require(arena.syntax(i) ==
                                SyntaxWords{7, 1 + 2 * i, 3 + 2 * i, i - 1, i, -1, -1, -1, -1, -1, 0, -1},
                            "wide sibling order/end/root differs");
                    require(arena.read(i) == NodeWords{1, 1 + 2 * i, -1, -1, 1, 1 + 2 * i, 1 + 2 * i},
                            "wide body expression forest differs");
                }
                require(arena.syntax(width) ==
                            SyntaxWords{1, 0, 2 * width + 2, -1, -1, -1, -1, -1, width - 1, -1, 0, -1},
                        "wide root differs");
            }
            const auto metrics = arena.metrics();
            require(metrics.live_allocations == 5 && metrics.peak_live_allocations == 5 &&
                        metrics.successful_allocations > 10 && metrics.peak_used > 8 * 96,
                    "body did not grow its real fifth owner");
            successful = allocations.successful;
            arena.finish();
            require(allocations.released == successful, "body growth leaked an owner");
        }
        for (std::size_t allowed = 0; allowed < successful; ++allowed) {
            Allocations allocations;
            allocations.allowed = allowed;
            RawArena arena(allocations);
            const auto result = arena.parse(text, Stop::body);
            require(result[0] == wire(Status::allocation_failure) && result[1] == -1,
                    "body initial/growth failure did not fail closed");
            if (arena.syntaxCount() > 0)
                require(arena.syntax(0) == (nested ? SyntaxWords{1, 127, 129, -1, -1, -1, -1, -1, -1, -1, 0, -1}
                                                   : SyntaxWords{7, 1, 3, -1, 0, -1, -1, -1, -1, -1, 0, -1}),
                        "body failed growth damaged a committed record");
            arena.finish();
            require(allocations.released == allocations.successful, "body failed growth leaked owner metadata");
            ++cases;
        }
        ++cases;
    }
}
void rawCase(const std::string &source, Status expected, Stop stop = Stop::semicolon) {
    context = "raw ABI " + source;
    Allocations allocations;
    RawArena arena(allocations);
    const auto result = arena.parse(source, stop);
    require(result[0] == static_cast<std::int64_t>(expected), "raw status enum differs");
    arena.finish();
    require(allocations.released == allocations.successful, "host allocator did not observe exact cleanup");
    ++cases;
}
void rawDeclarations() {
    static_assert(sizeof(SyntaxWords) == 96 && static_cast<std::int64_t>(Stop::function) == 6 &&
                  static_cast<std::int64_t>(Stop::method) == 7 && static_cast<std::int64_t>(Stop::constructor) == 8);
    static_assert(wire(SyntaxKind::parameter) == 11 && wire(SyntaxKind::initializer) == 12 &&
                  wire(SyntaxKind::function) == 13 && wire(SyntaxKind::method) == 14 &&
                  wire(SyntaxKind::constructor) == 15);
    static_assert(static_cast<std::int64_t>(Stop::preamble) == 10 &&
                  static_cast<std::int64_t>(Stop::enum_definition) == 11 && wire(SyntaxKind::preamble) == 17 &&
                  wire(SyntaxKind::import_name) == 18 && wire(SyntaxKind::enum_definition) == 19 &&
                  wire(SyntaxKind::enum_case) == 20);
    struct Fixture {
        const char *source;
        Stop stop;
        std::vector<SyntaxWords> syntax;
        std::vector<TypeWords> types = {};
        std::vector<NodeWords> nodes = {};
    };
    // Literal 96-byte records independently pin body/declaration topology, owned
    // type roots, reverse list order and located admission cursors.
    for (const auto &test : std::vector<Fixture>{
             {"{} next", Stop::body, {{1, 0, 2, -1, -1, -1, -1, -1, -1, -1, 0, -1}}},
             {"{i64 x=1;return x;} next",
              Stop::body,
              {{2, 1, 6, -1, 0, -1, 0, 2, -1, -1, 1, -1},
               {3, 6, 9, 0, 1, -1, -1, -1, -1, -1, 0, -1},
               {1, 0, 10, -1, -1, -1, -1, -1, 1, -1, 0, -1}},
              {{1, 1, 1, 2, -1, -1, 1, 3}},
              {{1, 4, -1, -1, 1, 4, 4}, {2, 7, -1, -1, 1, 7, 7}}},
             {"module one;next", Stop::preamble, {{17, 1, 3, -1, -1, -1, -1, 1, -1, -1, 0, -1}}},
             {"export module one.two;import std.array;import alpha.beta;next",
              Stop::preamble,
              {{18, 7, 10, -1, -1, -1, -1, -1, -1, -1, 0, -1},
               {18, 12, 15, 0, -1, -1, -1, -1, -1, -1, 0, -1},
               {17, 2, 16, -1, -1, -1, -1, 4, 1, -1, 1, -1}}},
             {"enum class Solo{first};next",
              Stop::enum_definition,
              {{20, 4, 5, -1, -1, -1, -1, -1, -1, -1, 0, -1}, {19, 2, 7, -1, -1, -1, -1, -1, 0, -1, 0, -1}}},
             {"enum class Shade{red,green,blue,};next",
              Stop::enum_definition,
              {{20, 4, 5, -1, -1, -1, -1, -1, -1, -1, 0, -1},
               {20, 6, 7, 0, -1, -1, -1, -1, -1, -1, 0, -1},
               {20, 8, 9, 1, -1, -1, -1, -1, -1, -1, 0, -1},
               {19, 2, 12, -1, -1, -1, -1, -1, 2, -1, 0, -1}}},
             {"i64 value;next",
              Stop::field,
              {{16, 0, 3, -1, -1, -1, 0, 1, -1, -1, 0, -1}},
              {{1, 0, 0, 0, -1, -1, 0, 3}}},
             {"Box<i64> value;next",
              Stop::field,
              {{16, 0, 6, -1, -1, -1, 1, 4, -1, -1, 0, -1}},
              {{1, 2, 2, 4, -1, -1, -1, 0}, {5, 0, 0, 6, 0, -1, 0, 3}}},
             {"array<u8,2> value;next",
              Stop::field,
              {{16, 0, 8, -1, -1, -1, 2, 6, -1, -1, 0, -1}},
              {{3, 2, 2, 4, -1, -1, -1, 0}, {7, 4, 4, 8, -1, -1, -1, 0}, {9, 0, 0, 10, 0, 1, 0, 3}}},
             {"auto f()->i64{} next",
              Stop::function,
              {{1, 6, 8, -1, -1, -1, -1, -1, -1, -1, 0, -1}, {13, 1, 8, -1, -1, -1, 0, -1, 0, -1, 0, -1}},
              {{1, 5, 5, 10, -1, -1, 1, 3}}},
             {"auto f(const Owner& p)->i64{} next",
              Stop::function,
              {{11, 3, 7, -1, -1, -1, 0, 6, -1, -1, 1, 5},
               {1, 10, 12, -1, -1, -1, -1, -1, -1, -1, 0, -1},
               {13, 1, 12, -1, -1, -1, 1, -1, 1, 0, 0, -1}},
              {{5, 4, 4, 8, -1, -1, 3, 3}, {1, 9, 9, 18, -1, -1, 1, 3}}},
             {"auto f(i64 p)const->i64{return p;} next",
              Stop::method,
              {{11, 3, 5, -1, -1, -1, 0, 4, -1, -1, 0, -1},
               {3, 10, 13, -1, 0, -1, -1, -1, -1, -1, 0, -1},
               {1, 9, 14, -1, -1, -1, -1, -1, 1, -1, 0, -1},
               {14, 1, 14, -1, -1, -1, 1, -1, 2, 0, 1, -1}},
              {{1, 3, 3, 6, -1, -1, 3, 3}, {1, 8, 8, 16, -1, -1, 1, 3}},
              {{2, 11, -1, -1, 1, 11, 11}}},
             {"Box(){} next", Stop::constructor, {{15, 0, 5, -1, -1, -1, -1, -1, -1, -1, 0, -1}}},
             {"Box(i64 p):first(p),bytes{}{} next",
              Stop::constructor,
              {{11, 2, 4, -1, -1, -1, 0, 3, -1, -1, 0, -1},
               {12, 6, 10, -1, 0, -1, -1, -1, -1, -1, 0, -1},
               {12, 11, 14, 1, 1, -1, -1, -1, -1, -1, 0, -1},
               {15, 0, 16, -1, -1, -1, -1, -1, 2, 0, 0, -1}},
              {{1, 2, 2, 4, -1, -1, 2, 3}},
              {{2, 8, -1, -1, 1, 8, 8}, {11, 11, -1, 0, 1, 11, 13}}}}) {
        context = "raw complete declaration " + std::string(test.source);
        const auto tokens = aurora::lex(test.source, "raw-declaration.au");
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(test.source, test.stop);
        require(result == Words{wire(Status::success),
                                static_cast<std::int64_t>(test.syntax.size() - 1),
                                static_cast<std::int64_t>(test.nodes.size()),
                                test.syntax.back()[2],
                                static_cast<std::int64_t>(tokens.at(test.syntax.back()[2]).span.begin.offset),
                                0} &&
                    arena.syntaxCount() == static_cast<std::int64_t>(test.syntax.size()) &&
                    arena.types() == static_cast<std::int64_t>(test.types.size()) && arena.edges() == 0,
                "raw declaration counts/root/next-token differ");
        for (std::size_t index = 0; index < test.syntax.size(); ++index)
            require(arena.syntax(index) == test.syntax[index], "raw declaration syntax field/order differs");
        for (std::size_t index = 0; index < test.types.size(); ++index)
            require(arena.type(index) == test.types[index], "raw declaration declared type owner/role differs");
        for (std::size_t index = 0; index < test.nodes.size(); ++index)
            require(arena.read(index) == test.nodes[index], "raw declaration initializer/body expression differs");
        const auto metrics = arena.metrics();
        require(metrics.live_allocations == 5 && metrics.peak_live_allocations == 5,
                "complete declaration introduced a sixth arena owner");
        if (test.stop != Stop::body) {
            require(arena.parse(test.source, test.stop) ==
                        Words{wire(Status::invalid), -1, static_cast<std::int64_t>(test.nodes.size()), 0, 0, 0},
                    "nonempty declaration arena reuse did not fail closed");
            for (std::size_t index = 0; index < test.syntax.size(); ++index)
                require(arena.syntax(index) == test.syntax[index], "rejected declaration reuse changed syntax");
        }
        arena.finish();
        require(allocations.successful == allocations.released, "complete declaration owner cleanup differs");
        ++cases;
    }
    struct Rejection {
        const char *source;
        Stop stop;
        Status status;
        std::size_t token;
        int half = 0;
    };
    for (const auto &test :
         std::vector<Rejection>{{"i64 value", Stop::field, Status::expected_semicolon, 2},
                                {"i64 true;", Stop::field, Status::reserved_identifier, 1},
                                {"Box<i64>> value;", Stop::field, Status::expected_identifier, 3, 1},
                                {"f()->i64{}", Stop::function, Status::expected_auto, 0},
                                {"auto f(){}", Stop::function, Status::expected_arrow, 4},
                                {"auto f()const{}", Stop::method, Status::expected_arrow, 5},
                                {"auto f(Box<i64>> value)->i64{}", Stop::function, Status::expected_identifier, 6, 1},
                                {"auto f()->i64{", Stop::method, Status::unterminated_block, 7},
                                {"Box():field(1", Stop::constructor, Status::expected_close, 7},
                                {"Box():field{}", Stop::constructor, Status::expected_brace_open, 7},
                                {"Box(){{}}", Stop::constructor, Status::expected_brace_close, 4}}) {
        context = "raw declaration diagnostic " + std::string(test.source);
        const auto tokens = aurora::lex(test.source, "raw-callable-error.au");
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(test.source, test.stop);
        require(result[0] == wire(test.status) && result[1] == -1 &&
                    result[3] == static_cast<std::int64_t>(test.token) &&
                    result[4] == static_cast<std::int64_t>(tokens.at(test.token).span.begin.offset + test.half) &&
                    result[5] == test.half,
                "raw declaration diagnostic status/token/half differs");
        if (test.stop == Stop::field)
            require(result[2] == 0 && arena.syntaxCount() == 0, "malformed field published a declaration/expression");
        arena.finish();
        require(allocations.successful == allocations.released, "malformed declaration leaked an owner");
        ++cases;
    }
}
void rawPreambleEnums() {
    context = "explicit enum-count ABI isolation";
    for (std::int64_t stop = 0; stop <= static_cast<std::int64_t>(Stop::module_definition); ++stop)
        for (const std::int64_t count :
             std::array<std::int64_t, 4>{-1, 1, 65, std::numeric_limits<std::int64_t>::max()}) {
            if (stop == static_cast<std::int64_t>(Stop::enum_definition) && count == 1)
                continue;
            Allocations allocations;
            RawArena arena(allocations);
            const auto result = arena.parse("enum class E{a};", static_cast<Stop>(stop), 0, {}, count);
            require(result == Words{wire(Status::invalid), -1, 0, 0, 0, 0} && arena.syntaxCount() == 0 &&
                        arena.types() == 0 && arena.edges() == 0,
                    "invalid or cross-profile enum count acquired syntax authority");
            arena.finish();
            require(allocations.successful == allocations.released, "invalid enum-count input leaked an owner");
            ++cases;
        }
    for (const auto stop : {Stop::preamble, Stop::enum_definition}) {
        context = "preamble/enum fifth-owner growth and every allocation failure";
        const std::int64_t width = stop == Stop::preamble ? 513 : 256;
        std::string source = stop == Stop::preamble ? "export module wide;" : enumSource(width);
        std::vector<SyntaxWords> expected;
        for (std::int64_t index = 0; index < width; ++index) {
            if (stop == Stop::preamble)
                source += "import item_" + std::to_string(index) + ";";
            const auto ordinal = stop == Stop::preamble ? 5 + 3 * index : 4 + 2 * index;
            expected.push_back(
                {stop == Stop::preamble ? 18 : 20, ordinal, ordinal + 1, index - 1, -1, -1, -1, -1, -1, -1, 0, -1});
        }
        const auto tokens = aurora::lex(source, "preamble-enum-growth.au");
        const auto end = static_cast<std::int64_t>(tokens.size() - 1);
        expected.push_back({stop == Stop::preamble ? 17 : 19,
                            2,
                            end,
                            -1,
                            -1,
                            -1,
                            -1,
                            stop == Stop::preamble ? 2 : -1,
                            width - 1,
                            -1,
                            stop == Stop::preamble ? 1 : 0,
                            -1});
        std::size_t successful = 0;
        for (std::size_t allowed = 0;; ++allowed) {
            Allocations allocations;
            allocations.allowed = allowed;
            RawArena arena(allocations);
            const auto result = arena.parse(source, stop, 0, {}, stop == Stop::enum_definition ? 63 : 0);
            const bool accepted = result[0] == wire(Status::success);
            if (accepted) {
                require(result == Words{wire(Status::success),
                                        width,
                                        0,
                                        end,
                                        static_cast<std::int64_t>(tokens.back().span.begin.offset),
                                        0} &&
                            arena.syntaxCount() == width + 1,
                        "wide preamble/enum root or cursor differs");
                const auto metrics = arena.metrics();
                require(metrics.live_allocations == 5 && metrics.peak_live_allocations == 5 &&
                            metrics.successful_allocations > 5 && metrics.peak_used > 8 * 96,
                        "preamble/enum growth added an owner or bypassed syntax storage");
                successful = allocations.successful;
            } else {
                require(result[0] == wire(Status::allocation_failure) && result[1] == -1 && result[2] == 0 &&
                            arena.syntaxCount() >= 0 && arena.syntaxCount() <= width,
                        "preamble/enum allocation failure published a root");
            }
            require(arena.types() == 0 && arena.edges() == 0, "preamble/enum acquired unrelated graph records");
            for (std::int64_t index = 0; index < arena.syntaxCount(); ++index)
                require(arena.syntax(index) == expected.at(index), "preamble/enum growth changed its committed prefix");
            arena.finish();
            require(allocations.successful == allocations.released, "preamble/enum failed growth leaked an owner");
            ++cases;
            if (accepted) {
                require(allowed == successful, "allocation sweep skipped a failing allocation");
                break;
            }
        }
    }
}

void rawCallableGrowth() {
    constexpr std::int64_t width = 513;
    for (const auto stop : {Stop::function, Stop::method, Stop::constructor}) {
        const bool constructor = stop == Stop::constructor;
        std::string source = constructor ? "Box(i64 p):" : "auto wide(";
        for (std::int64_t index = 0; index < width; ++index) {
            if (index)
                source += ',';
            source += constructor ? "f" + std::to_string(index) + "(make(p))" : "i64 p" + std::to_string(index);
        }
        source += constructor ? "{}" : ")->i64{return 1;}";
        context = constructor ? "constructor initializer growth/failure prefixes"
                              : "callable parameter growth/failure prefixes";
        std::vector<SyntaxWords> expected;
        if (constructor) {
            expected.push_back({11, 2, 4, -1, -1, -1, 0, 3, -1, -1, 0, -1});
            for (std::int64_t index = 0; index < width; ++index)
                expected.push_back({12,
                                    6 + 8 * index,
                                    13 + 8 * index,
                                    index == 0 ? -1 : index,
                                    2 * index + 1,
                                    -1,
                                    -1,
                                    -1,
                                    -1,
                                    -1,
                                    0,
                                    -1});
            expected.push_back({15, 0, 8 * width + 7, -1, -1, -1, -1, -1, width, 0, 0, -1});
        } else {
            for (std::int64_t index = 0; index < width; ++index)
                expected.push_back(
                    {11, 3 + 3 * index, 5 + 3 * index, index - 1, -1, -1, index, 4 + 3 * index, -1, -1, 0, -1});
            expected.push_back({3, 3 * width + 6, 3 * width + 9, -1, 0, -1, -1, -1, -1, -1, 0, -1});
            expected.push_back({1, 3 * width + 5, 3 * width + 10, -1, -1, -1, -1, -1, width, -1, 0, -1});
            expected.push_back({stop == Stop::function ? 13 : 14,
                                1,
                                3 * width + 10,
                                -1,
                                -1,
                                -1,
                                width,
                                -1,
                                width + 1,
                                width - 1,
                                0,
                                -1});
        }
        const auto expressions = constructor ? 2 * width : 1;
        const auto next = constructor ? 8 * width + 7 : 3 * width + 10;
        std::size_t successful = 0;
        {
            Allocations allocations;
            RawArena arena(allocations);
            const auto result = arena.parse(source, stop);
            require(result == Words{wire(Status::success),
                                    static_cast<std::int64_t>(expected.size() - 1),
                                    expressions,
                                    next,
                                    static_cast<std::int64_t>(source.size()),
                                    0} &&
                        arena.syntaxCount() == static_cast<std::int64_t>(expected.size()) &&
                        arena.types() == (constructor ? 1 : width + 1) && arena.edges() == (constructor ? width : 0),
                    "wide callable lost a parameter, initializer, type, expression or closing boundary");
            for (std::size_t index = 0; index < expected.size(); ++index)
                require(arena.syntax(index) == expected[index], "wide callable syntax prefix differs");
            const auto metrics = arena.metrics();
            require(metrics.live_allocations == 5 && metrics.peak_live_allocations == 5 &&
                        metrics.successful_allocations > 10 && metrics.peak_used > 8 * 96,
                    "wide callable did not grow the existing five-owner arena");
            successful = allocations.successful;
            arena.finish();
            require(allocations.released == successful, "wide callable leaked a successful allocation");
        }
        for (std::size_t allowed = 0; allowed < successful; ++allowed) {
            Allocations allocations;
            allocations.allowed = allowed;
            RawArena arena(allocations);
            const auto result = arena.parse(source, stop);
            require(result[0] == wire(Status::allocation_failure) && result[1] == -1 && arena.syntaxCount() >= 0 &&
                        arena.syntaxCount() <= static_cast<std::int64_t>(expected.size()),
                    "callable allocation/growth failure did not fail closed");
            for (std::int64_t index = 0; index < arena.syntaxCount(); ++index)
                require(arena.syntax(index) == expected[static_cast<std::size_t>(index)],
                        "callable failed growth damaged a committed syntax prefix");
            arena.finish();
            require(allocations.successful == allocations.released, "callable failed growth leaked an arena owner");
            ++cases;
        }
        const auto tokens = aurora::lex(source, "callable-growth.au");
        const auto direct = aurora::parseHostedCallable(tokens, Cursor{}, stop);
        require(direct.next.ordinal == tokens.size() - 1 && direct.next.half == 0 &&
                    direct.function.params.size() == (constructor ? 1u : static_cast<std::size_t>(width)) &&
                    direct.function.initializers.size() == (constructor ? static_cast<std::size_t>(width) : 0u),
                "wide callable host conversion truncated the ordered list");
        for (std::int64_t index = 0; index < width; ++index) {
            if (constructor) {
                const auto &initializer = direct.function.initializers[static_cast<std::size_t>(index)];
                require(initializer.first.text == "f" + std::to_string(index), "wide initializer field order differs");
                sameTree(initializer.second, tokens, call(8 + 8 * index, {name(10 + 8 * index)}));
            } else {
                const auto &parameter = direct.function.params[static_cast<std::size_t>(index)];
                require(parameter.name == "p" + std::to_string(index) && parameter.type == aurora::Type::I64 &&
                            !parameter.borrowed && !parameter.borrowConst,
                        "wide parameter name/type/qualifier order differs");
            }
        }
        ++cases;
    }
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
        require(result == Words{wire(Status::success), 0, 1, 1, static_cast<std::int64_t>(spelling.size()), 0} &&
                    arena.read(0) == NodeWords{wire(NodeKind::literal), 0, -1, -1, 1, 0, 0} && arena.edges() == 0,
                "byte string did not retain the exact single Literal node ABI/cursor");
        arena.finish();
        require(allocations.released == allocations.successful, "byte-string cleanup mismatch");
        ++cases;
        pin(spelling, tree("byte_string", 0));
        supported("// preceding trivia\r\n\t" + spelling + ";");
        supported(spelling + ")", Stop::close_parenthesis);
        const auto source = "module strings; class Text { array<u8,512> bytes; public: Text():bytes(" + spelling +
                            "){} auto first() const->u8 {return bytes[0];} }; "
                            "auto f()->i64 {const array<u8,4096> bytes=" +
                            spelling + ";return 0;}";
        const auto tokens = aurora::lex(source, "string-program.au");
        const auto program = checkedProgram(tokens);
        require(program.classes.size() == 1 && program.classes[0].methods.size() == 2 && program.functions.size() == 1,
                "byte-string declaration inventory differs");
        sameTree(program.classes[0].methods[0].initializers.at(0).second, tokens, tree("byte_string", 22));
        sameTree(program.classes[0].methods[1].body.at(0)->expr, tokens, index(name(35), number(37)));
        sameTree(program.functions[0].body.at(0)->expr, tokens, tree("byte_string", 59));
        sameTree(program.functions[0].body.at(1)->expr, tokens, number(62));
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
        supported(std::string(expression) + ")", Stop::close_parenthesis);
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
        supported(std::string(expression) + ")", Stop::close_parenthesis);
        rawCase(std::string(expression) + ")", Status::success, Stop::close_parenthesis);
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
    sameTree(initializers[0].second, tokens, shifted(expected, tokenAt(tokens, initializers[0].first)));
    sameTree(initializers[1].second, tokens, tree("array_zero", tokenAt(tokens, initializers[1].first)));
    for (const auto &[field, expression] : initializers)
        hostedBraces(tokens, field, expression);
}
void aggregateSyntax() {
    for (const auto &fixture : aggregateExpressions)
        checkedRootProgram("module aggregates; auto f()->i64{return ", fixture.first + ";", "}");
    supported("{1,2}[0] = 3;", Stop::assignment);
    supported("Box{.value={1,2}[0]})", Stop::close_parenthesis);
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
        rawCase(expression, Status::success);
    }
    for (const auto &contents : {"{1,size_of(i64)}", "{Box{.value=type_id(array<u8,2>)}}"}) {
        const std::string text = std::string("value") + contents;
        rawCase(text, Status::success, Stop::constructor_braces);
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
    for (const auto &group : aggregateErrors)
        for (const auto &expression : group.sources)
            rejectedProgram("module errors; auto f()->i64{return ", expression, "}");
    for (const auto &contents : {"{,}", "{1,}", "{1 2}", "{1", "{1]}", "{Box{.value=1,}}"})
        rejectedProgram("export module errors; class Box { array<i64,2> value; public: Box():value", contents, "{} };");
}
void typedSyntax() {
    using K = aurora::TypeKind;
    using T = aurora::Type;
    for (const auto &fixture : typedExpressions)
        checkedRootProgram("module typed; auto f()->i64{return ", fixture.first + ";", "}");
    for (const auto &[type, expected] : typeExpectations())
        for (const auto &query : {"size_of", "type_id", "field_count"}) {
            const auto source = std::string(query) + "(" + type + ")";
            pin(source, reflected(0, expected));
            supported(source + ";");
        }
    for (const auto &group : typedErrors)
        for (const auto &expression : group.sources) {
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
        rawCase(source, depth == 63 ? Status::array_element : Status::type_nesting_limit);
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
        require(result[0] == wire(Status::success) && result[1] >= 0 &&
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
        const auto result = arena.parse(source, Stop::semicolon, 4, typeContext);
        require(result[0] == wire(Status::success), "raw copied context was not consumed");
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
    const std::vector<Rejection> tests{{"size_of(array);", Status::expected_angle_open, 3},
                                       {"size_of(own<i64);", Status::expected_angle_close, 5},
                                       {"size_of(builtin);", Status::expected_scope, 3},
                                       {"size_of(array<i64>);", Status::expected_comma, 5},
                                       {"size_of(builtin::span<u8>);", Status::expected_const, 6},
                                       {"size_of(builtin::span<const i64>);", Status::expected_u8, 7},
                                       {"size_of(own<u8>);", Status::expected_i64, 4},
                                       {"size_of(builtin::unknown);", Status::expected_array, 4},
                                       {"size_of(fn);", Status::reserved_type, 2},
                                       {"size_of(123);", Status::expected_type, 3},
                                       {"size_of(A<B<C<D<E<i64>>>>>);", Status::template_nesting_limit, 11},
                                       {"f<A<B<C<D<E<i64>>>>>>();", Status::call_template_nesting_limit, 11},
                                       {"f<i64, u8, bool>();", Status::template_arity, 6},
                                       {"f<own>();", Status::template_argument, 2},
                                       {"f<65>();", Status::capacity_argument, 3},
                                       {"size_of(builtin::OwnedValues<i64>);", Status::owned_element, 7},
                                       {"size_of(array<own<i64>, 1>);", Status::array_element, 8},
                                       {"size_of(array<i64, 4097>);", Status::array_length, 7},
                                       {"size_of(array<Class, 65>);", Status::class_array_length, 8},
                                       {"size_of(Box<i64>>);", Status::expected_close, 5, 1},
                                       {"size_of(array<i64, 2>>);", Status::expected_close, 7, 1}};
    for (const auto &[source, expected, token, half] : tests) {
        context = "raw typed status/token/offset " + source;
        const auto tokens = aurora::lex(source, "raw-type-diagnostic.au");
        const auto offset = tokens.at(token).span.begin.offset + half;
        require(!half || tokens.at(token).text == ">>", "raw half-token expectation has no shared closer");
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(source);
        require(result[0] == wire(expected) && result[1] == -1 && result[3] == static_cast<std::int64_t>(token) &&
                    result[4] == static_cast<std::int64_t>(offset) && result[5] == half,
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
         std::vector<Dependent>{{"T f<T>();", {0, 1, 0, 0, 0, 0, 1}, Status::template_context},
                                {"T f<Box<T>>();", {0, 1, 0, 0, 0, 0, 2}, Status::nested_dependent},
                                {"T f<T<i64>>();", {0, 1, 0, 0, 0, 0, 2}, Status::nested_dependent}}) {
        context = "raw dependent context rejection " + test.source;
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(test.source, Stop::semicolon, 2, test.context);
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
        require(result[0] == wire(Status::success) && result[2] == 2 * count + 1 && arena.types() == 5 * count &&
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
        require(result[0] == wire(Status::allocation_failure) && result[1] == -1,
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

void rawDeclarationTypes() {
    static_assert(static_cast<std::int64_t>(Stop::type) == 5);
    struct Fixture {
        std::string source;
        std::int64_t next;
        int half;
        std::vector<TypeWords> types;
    };
    // These literal 64-byte records pin Type profile ownership and topology
    // independently of both the host enum and Type conversion implementation.
    for (const auto &fixture : std::vector<Fixture>{
             {"i64 next", 1, 0, {{1, 0, 0, 0, -1, -1, 0, 3}}},
             {"ns::Name next", 3, 0, {{5, 0, 2, 4, -1, -1, 0, 3}}},
             {"own<i64> next", 4, 0, {{10, 0, 0, 6, -1, -1, 0, 3}}},
             {"builtin::span<const u8> next", 7, 0, {{13, 0, 2, 12, -1, -1, 0, 3}}},
             {"builtin::ByteRegion next", 3, 0, {{14, 0, 2, 4, -1, -1, 0, 3}}},
             {"Box<i64>> next", 3, 1, {{1, 2, 2, 4, -1, -1, -1, 0}, {5, 0, 0, 6, 0, -1, 0, 3}}},
             {"Box<Pair<i64,u8>> next",
              8,
              0,
              {{1, 4, 4, 8, -1, -1, -1, 0},
               {3, 6, 6, 12, -1, -1, -1, 0},
               {5, 2, 2, 14, 0, 1, -1, 0},
               {5, 0, 0, 15, 2, -1, 0, 3}}},
             {"array<u8,4>> next",
              5,
              1,
              {{3, 2, 2, 4, -1, -1, -1, 0}, {7, 4, 4, 8, -1, -1, -1, 0}, {9, 0, 0, 10, 0, 1, 0, 3}}},
             {"builtin::OwnedValues<Item>> next", 5, 1, {{5, 4, 4, 8, -1, -1, -1, 0}, {15, 0, 2, 10, 0, -1, 0, 3}}},
             {"array<builtin::ConsoleSample,2> next",
              8,
              0,
              {{16, 2, 4, 8, -1, -1, -1, 0}, {7, 6, 6, 12, -1, -1, -1, 0}, {9, 0, 0, 14, 0, 1, 0, 3}}}}) {
        context = "raw standalone declaration TypeSyntax " + fixture.source;
        const auto tokens = aurora::lex(fixture.source, "raw-declaration-type.au");
        const auto offset = tokens.at(fixture.next).span.begin.offset + fixture.half;
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(fixture.source, Stop::type);
        require(result == Words{wire(Status::success),
                                static_cast<std::int64_t>(fixture.types.size() - 1),
                                0,
                                fixture.next,
                                static_cast<std::int64_t>(offset),
                                fixture.half} &&
                    arena.types() == static_cast<std::int64_t>(fixture.types.size()) && arena.edges() == 0 &&
                    arena.syntaxCount() == 0,
                "standalone type root/count/cursor/half differs");
        for (std::size_t index = 0; index < fixture.types.size(); ++index)
            require(arena.type(static_cast<std::int64_t>(index)) == fixture.types[index],
                    "standalone type acquired the wrong layout/child/owner/role");
        const auto metrics = arena.metrics();
        require(metrics.live_allocations == 5 && metrics.peak_live_allocations == 5,
                "standalone type introduced an owner beyond the existing five");
        // The arena is invocation-scoped. Re-entry must reject without changing
        // the committed type graph, allocating a sixth owner, or leaking it.
        const auto again = arena.parse("u8 next", Stop::type);
        require(again == Words{wire(Status::invalid), -1, 0, 0, 0, 0} &&
                    arena.types() == static_cast<std::int64_t>(fixture.types.size()) &&
                    arena.metrics().successful_allocations == metrics.successful_allocations,
                "nonempty type-arena reuse did not reject without mutation");
        for (std::size_t index = 0; index < fixture.types.size(); ++index)
            require(arena.type(static_cast<std::int64_t>(index)) == fixture.types[index],
                    "rejected re-entry changed a committed type record");
        arena.finish();
        require(allocations.successful == allocations.released, "standalone type lifecycle leaked storage");
        ++cases;
    }
    for (const bool function : {false, true}) {
        const std::string source = function ? "T U Pair<T,U> next" : "T N array<T,N> next";
        const ContextWords captured = function ? ContextWords{0, 1, 2, 3, 0, 0, 2} : ContextWords{0, 1, 0, 0, 2, 3, 1};
        context = "raw standalone declaration context " + source;
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(source, Stop::type, 4, captured);
        require(result == Words{wire(Status::success), 2, 0, 6, function ? 14 : 15, 0} && arena.types() == 3 &&
                    arena.type(0) == TypeWords{6, 2, 2, 4, -1, -1, -1, 0} &&
                    arena.type(1) == TypeWords{function ? 6 : 8, 4, 4, 8, -1, -1, -1, 0} &&
                    arena.type(2) == TypeWords{function ? 5 : 9, 0, 0, 10, 0, 1, 0, 3},
                "standalone type context lost a captured parameter or declaration root role");
        arena.finish();
        require(allocations.successful == allocations.released, "standalone context leaked storage");
        ++cases;
    }
    struct Rejection {
        std::string source;
        Status status;
        std::size_t token;
        int half = 0;
    };
    for (const auto &test : std::vector<Rejection>{{"fn next", Status::reserved_type, 0},
                                                   {"123 next", Status::expected_type, 1},
                                                   {"array;", Status::expected_angle_open, 1},
                                                   {"own<i64>>;", Status::expected_angle_close, 3},
                                                   {"builtin::span<u8>;", Status::expected_const, 4},
                                                   {"Box<i64,u8,bool>;", Status::template_arity, 6},
                                                   {"array<Class,65>>;", Status::class_array_length, 5, 1},
                                                   {"builtin::OwnedValues<Box<i64>>;", Status::owned_element, 7, 1},
                                                   {"A<B<C<D<E<i64>>>>>;", Status::template_nesting_limit, 9}}) {
        context = "raw declaration type diagnostic " + test.source;
        const auto tokens = aurora::lex(test.source);
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(test.source, Stop::type);
        require(result == Words{wire(test.status),
                                -1,
                                0,
                                static_cast<std::int64_t>(test.token),
                                static_cast<std::int64_t>(tokens.at(test.token).span.begin.offset + test.half),
                                test.half},
                "raw declaration type diagnostic status/cursor/half differs");
        for (std::int64_t index = 0; index < arena.types(); ++index) {
            const auto record = arena.type(index);
            require(record[6] == -1 && record[7] == 0, "failed type bound a declaration owner before success");
        }
        arena.finish();
        require(allocations.successful == allocations.released, "failed declaration type leaked partial records");
        ++cases;
    }
}
// Build a stated complete binary type tree and its independent wire layout.
// Spaced closers deliberately keep this growth test orthogonal to >> tokenization.
std::string rawDeclarationTree(int depth, std::int64_t &token, std::vector<TypeWords> &records) {
    const auto first = token++;
    if (!depth) {
        records.push_back({1, first, first, 2 * first, -1, -1, -1, 0});
        return "i64";
    }
    ++token; // '<'
    const auto left = rawDeclarationTree(depth - 1, token, records);
    const auto leftRoot = static_cast<std::int64_t>(records.size() - 1);
    ++token; // ','
    const auto right = rawDeclarationTree(depth - 1, token, records);
    const auto rightRoot = static_cast<std::int64_t>(records.size() - 1);
    const auto close = token++;
    records.push_back({5, first, first, 2 * close, leftRoot, rightRoot, -1, 0});
    return "Pair < " + left + " , " + right + " >";
}
void rawDeclarationTypeGrowth() {
    context = "standalone type growth, exact prefix preservation and allocation cleanup";
    std::int64_t next = 0;
    std::vector<TypeWords> expected;
    const auto type = rawDeclarationTree(4, next, expected);
    const auto source = type + " next";
    require(expected.size() == 31 && next == 76, "independent binary type fixture changed shape");
    expected.back()[6] = 0;
    expected.back()[7] = 3;
    std::size_t successful = 0;
    for (int cycle = 0; cycle < 3; ++cycle) {
        Allocations allocations;
        RawArena arena(allocations);
        require(arena.parse(source, Stop::type) ==
                        Words{wire(Status::success), 30, 0, 76, static_cast<std::int64_t>(type.size() + 1), 0} &&
                    arena.types() == 31,
                "31-record standalone type growth lost its root/cursor");
        for (std::size_t index = 0; index < expected.size(); ++index)
            require(arena.type(static_cast<std::int64_t>(index)) == expected[index],
                    "standalone type growth changed child-before-parent records");
        const auto metrics = arena.metrics();
        require(metrics.live_allocations == 5 && metrics.peak_live_allocations == 5 &&
                    metrics.successful_allocations >= 7 && metrics.peak_used >= 32 * 64,
                "standalone type did not grow existing type storage while retaining five owners");
        if (cycle)
            require(successful == allocations.successful, "fresh type lifecycle acquired stale storage state");
        successful = allocations.successful;
        arena.finish();
        require(allocations.released == successful, "fresh type lifecycle leaked storage");
        ++cases;
    }
    for (std::size_t allowed = 0; allowed < successful; ++allowed) {
        Allocations allocations;
        allocations.allowed = allowed;
        RawArena arena(allocations);
        const auto result = arena.parse(source, Stop::type);
        require(result[0] == wire(Status::allocation_failure) && result[1] == -1 && result[2] == 0 &&
                    arena.types() >= 0 && arena.types() < static_cast<std::int64_t>(expected.size()),
                "standalone type allocation failure did not fail closed");
        for (std::int64_t index = 0; index < arena.types(); ++index)
            require(arena.type(index) == expected[static_cast<std::size_t>(index)],
                    "failed standalone type growth damaged a committed prefix");
        arena.finish();
        require(allocations.successful == allocations.released, "failed standalone type lifecycle leaked an owner");
        ++cases;
    }
    {
        Allocations allocations;
        RawArena arena(allocations, 0);
        require(arena.parse("i64 next", Stop::type)[0] == wire(Status::allocation_failure),
                "zero-quota standalone type parse was accepted");
        arena.finish();
        require(allocations.successful == allocations.released, "zero-quota standalone type leaked storage");
        ++cases;
    }
}

void rawFields() {
    context = "field type growth and allocation-failure prefixes";
    std::int64_t next = 0;
    std::vector<TypeWords> types;
    const auto source = rawDeclarationTree(4, next, types) + " value;";
    require(types.size() == 31 && next == 76, "field growth fixture changed its independent topology");
    auto owned = types.back();
    owned[6] = 0;
    owned[7] = 3;
    std::size_t allocationsNeeded = 0;
    for (std::size_t allowed = std::numeric_limits<std::size_t>::max();;) {
        Allocations allocations;
        allocations.allowed = allowed;
        RawArena arena(allocations);
        const auto result = arena.parse(source, Stop::field);
        const bool success = allowed == std::numeric_limits<std::size_t>::max();
        if (success) {
            require(result == Words{wire(Status::success), 0, 0, 78, static_cast<std::int64_t>(source.size()), 0} &&
                        arena.syntaxCount() == 1 && arena.types() == 31 && arena.edges() == 0 &&
                        arena.syntax(0) == SyntaxWords{16, 0, 78, -1, -1, -1, 30, 76, -1, -1, 0, -1} &&
                        arena.type(30) == owned,
                    "wide field lost its type graph or closing delimiter");
            const auto metrics = arena.metrics();
            allocationsNeeded = allocations.successful;
            require(metrics.live_allocations == 5 && metrics.peak_live_allocations == 5 && allocationsNeeded > 5,
                    "field type did not grow within the five-owner arena");
        } else
            require(result[0] == wire(Status::allocation_failure) && result[1] == -1 && arena.syntaxCount() == 0,
                    "field allocation failure published a declaration");
        require(arena.types() >= 0 && arena.types() <= 31, "field failure returned an impossible type prefix");
        for (std::int64_t index = 0; index < arena.types(); ++index)
            require(arena.type(index) == types[index] || (index == 30 && arena.type(index) == owned),
                    "field allocation failure corrupted a committed type prefix");
        arena.finish();
        require(allocations.successful == allocations.released, "partial field leaked an owner");
        ++cases;
        if (success)
            allowed = 0;
        else if (++allowed == allocationsNeeded)
            break;
    }
    auto expected = aurora::TemplateArgument(aurora::TypeKind::I64);
    for (int depth = 0; depth < 4; ++depth)
        expected = namedArgument("Pair", {expected, expected});
    const auto tokens = aurora::lex(source), before = tokens;
    const auto parsed = aurora::parseHostedField(tokens, Cursor{});
    sameType(parsed.field.type, namedType("Pair", expected.templateArguments));
    require(parsed.field.token.text == "value" && parsed.next.ordinal == 78 && parsed.next.half == 0,
            "wide field conversion lost its name or cursor");
    unchangedTokens(tokens, before);
    ++cases;
}

void rawAggregateDiagnostics() {
    struct Rejection {
        std::string source;
        Status status;
        std::int64_t token;
        Stop stop = Stop::semicolon;
    };
    for (const auto &test :
         std::vector<Rejection>{{"{1;", Status::expected_brace_close, 2},
                                {"{1,};", Status::expected_expression, 4},
                                {"{,};", Status::expected_expression, 2},
                                {"{1 2};", Status::expected_brace_close, 2},
                                {"{1,2", Status::expected_brace_close, 4},
                                {"Box{value=1};", Status::expected_dot, 2},
                                {"Box{.1=1};", Status::expected_identifier, 3},
                                {"Box{.true=1};", Status::reserved_identifier, 3},
                                {"Box{.array=1};", Status::reserved_builtin, 3},
                                {"Box{.__au_private=1};", Status::reserved_prefix, 3},
                                {"Box{.value 1};", Status::expected_equal, 4},
                                {"Box{.value=};", Status::expected_expression, 6},
                                {"Box{.value=1,};", Status::expected_dot, 7},
                                {"Box{.value=1;", Status::expected_brace_close, 6},
                                {"value(1)", Status::expected_brace_open, 1, Stop::constructor_braces},
                                {"value{1,}", Status::expected_expression, 5, Stop::constructor_braces},
                                {"value{1", Status::expected_brace_close, 3, Stop::constructor_braces},
                                {"true{}", Status::reserved_identifier, 0, Stop::constructor_braces},
                                {"array{}", Status::reserved_builtin, 0, Stop::constructor_braces},
                                {"__au_field{}", Status::reserved_prefix, 0, Stop::constructor_braces}}) {
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
    rawCase("{};", Status::invalid, static_cast<Stop>(-1));
    rawCase("{};", Status::invalid, static_cast<Stop>(static_cast<std::int64_t>(Stop::module_definition) + 1));
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
        require(result == Words{wire(Status::success), 198, 199, 199, 199, 0},
                "100-term raw parse did not return exact graph/cursor");
        for (std::int64_t i = 0; i < 199; ++i) {
            const auto node = arena.read(i);
            if (i == 0)
                require(node == NodeWords{wire(NodeKind::literal), 0, -1, -1, 1, 0, 0}, "first literal ABI differs");
            else if (i % 2 == 1)
                require(node == NodeWords{wire(NodeKind::literal), i + 1, -1, -1, 1, i + 1, i + 1},
                        "literal ABI differs");
            else
                require(node == NodeWords{wire(NodeKind::binary), i - 1, i - 2, i - 1, i / 2 + 1, i - 1, i - 1},
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
        require(arena.parse("size_of(i64);")[0] == wire(Status::allocation_failure),
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
        require(result[0] == static_cast<std::int64_t>(Status::allocation_failure) && result[1] == -1,
                "injected allocation/growth failure did not fail closed");
        if (result[2] > 0)
            require(arena.read(0) == NodeWords{wire(NodeKind::literal), 0, -1, -1, 1, 0, 0},
                    "failed growth changed an already committed node");
        arena.finish();
        require(allocations.successful == allocations.released, "failure cleanup mismatch");
    }
    {
        Allocations allocations;
        RawArena arena(allocations, 0);
        require(arena.parse("1;")[0] == static_cast<std::int64_t>(Status::allocation_failure),
                "quota failure accepted");
        arena.finish();
    }
    for (const auto &[sourceText, expected] :
         std::array<std::pair<std::string, NodeWords>, 4>{{{"name;", {wire(NodeKind::name), 0, -1, -1, 1, 0, 0}},
                                                           {"true;", {wire(NodeKind::literal), 0, -1, -1, 1, 0, 0}},
                                                           {"'x';", {wire(NodeKind::literal), 0, -1, -1, 1, 0, 0}},
                                                           {"-1;", {wire(NodeKind::unary), 0, 0, -1, 2, 0, 0}}}}) {
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(sourceText);
        require(result[0] == wire(Status::success) && arena.read(result[1]) == expected,
                "real generated node kind ABI differs");
        arena.finish();
    }
    {
        Allocations allocations;
        RawArena arena(allocations);
        require(arena.parse("1;", Stop::semicolon, 3)[0] == wire(Status::invalid),
                "invalid lexer cursor did not return the named Invalid status");
        arena.finish();
    }
    ++cases;
}
void rawFrameGrowth() {
    context = "real Aurora explicit-frame growth and failure cleanup";
    const auto source = std::string(127, '(') + "1" + std::string(127, ')') + ";";
    const NodeWords literal{wire(NodeKind::literal), 127, -1, -1, 1, 127, 127};
    std::size_t successful = 0;
    {
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(source);
        require(result == Words{wire(Status::success), 0, 1, 255, 255, 0} && arena.read(0) == literal,
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
        require(result[0] == wire(Status::allocation_failure) && result[1] == -1,
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
        require(result == Words{wire(Status::success), count, count + 1, 2 * count + 2, 2 * count + 2, 0},
                "wide call did not return the complete graph/cursor");
        require(arena.edges() == count &&
                    arena.read(count) == NodeWords{wire(NodeKind::call), 0, count - 1, count, 2, 0, 2 * count + 1},
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
        require(result[0] == wire(Status::allocation_failure) && result[1] == -1,
                "injected argument allocation failure did not reject");
        arena.finish();
        require(allocations.successful == allocations.released, "partial argument graph leaked an owner");
    }
    for (const auto &[text, expected] : std::array<std::pair<std::string, NodeWords>, 4>{
             {{"ns::f(1,2);", {wire(NodeKind::call), 0, 1, 2, 2, 2, 7}},
              {"obj.m();", {wire(NodeKind::method_call), 2, 0, 1, 2, 2, 4}},
              {"a.b;", {wire(NodeKind::member), 2, 0, -1, 2, 2, 2}},
              {"a[0];", {wire(NodeKind::index), 1, 0, 1, 2, 1, 3}}}}) {
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(text);
        require(result[0] == wire(Status::success) && arena.read(result[1]) == expected,
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
             {"{};", Stop::semicolon, NodeKind::array_literal, 0, 1, 2, 2},
             {"{};size_of(i64)", Stop::semicolon, NodeKind::array_literal, 0, 1, 2, 2},
             {"ns::Box{};", Stop::semicolon, NodeKind::construct, 2, 4, 5, 9},
             {"field{}", Stop::constructor_braces, NodeKind::array_zero, 0, 2, 3, 7},
             {"field{},other{}", Stop::constructor_braces, NodeKind::array_zero, 0, 2, 3, 7},
             {"field{}{size_of(i64)", Stop::constructor_braces, NodeKind::array_zero, 0, 2, 3, 7},
             {"field{};size_of(i64)", Stop::constructor_braces, NodeKind::array_zero, 0, 2, 3, 7},
             {"field{} // following trivia\n {", Stop::constructor_braces, NodeKind::array_zero, 0, 2, 3, 29}}) {
        context = "empty aggregate ABI " + test.source;
        if (test.stop == Stop::constructor_braces) {
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
        require(result == Words{wire(Status::success), 0, 1, test.tokens, test.offset, 0} && arena.edges() == 0 &&
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
        const auto expression = aurora::parseHostedExpression(tokens, position, Stop::constructor_braces);
        require(expression && expression->op == "array_literal" && expression->args.size() == 1 &&
                    expression->depth == 2 && expression->args[0]->op == "number" && expression->args[0]->depth == 1 &&
                    position == 4 && tokens.at(position).span.begin.offset == 8,
                "nonempty constructor host conversion lost its exact next-token/EOF boundary");
        sameToken(expression->token, tokens[0]);
        sameToken(expression->args[0]->token, tokens[2]);
        Allocations allocations;
        RawArena arena(allocations);
        require(arena.parse(std::string("field{1}") + suffix, Stop::constructor_braces) ==
                        Words{wire(Status::success), 1, 2, 4, 8, 0} &&
                    arena.read(0) == NodeWords{wire(NodeKind::literal), 2, -1, -1, 1, 2, 2} &&
                    arena.read(1) == NodeWords{wire(NodeKind::array_literal), 0, 0, 1, 2, 0, 3} && arena.edges() == 1 &&
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
        require(arena.parse("{1,{2,3}};") == Words{wire(Status::success), 4, 5, 9, 9, 0},
                "nested array graph/cursor differs");
        const std::array<NodeWords, 5> expected{{{wire(NodeKind::literal), 1, -1, -1, 1, 1, 1},
                                                 {wire(NodeKind::literal), 4, -1, -1, 1, 4, 4},
                                                 {wire(NodeKind::literal), 6, -1, -1, 1, 6, 6},
                                                 {wire(NodeKind::array_literal), 3, 2, 2, 2, 3, 7},
                                                 {wire(NodeKind::array_literal), 0, 3, 2, 3, 0, 8}}};
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
                        Words{wire(Status::success), 2, 3, 14, static_cast<std::int64_t>(source.size() - 1), 0} &&
                    arena.read(0) == NodeWords{wire(NodeKind::literal), 7, -1, -1, 1, 7, 7} &&
                    arena.read(1) == NodeWords{wire(NodeKind::literal), 12, -1, -1, 1, 12, 12} &&
                    arena.read(2) == NodeWords{wire(NodeKind::construct), 0, 1, 2, 2, 2, 13} && arena.edges() == 2 &&
                    arena.edge(0) == EdgeWords{0, -1, 1, 2, 5} && arena.edge(1) == EdgeWords{1, 0, 2, 2, 10},
                "designated construction lost qualified name/field-label provenance");
        arena.finish();
        require(allocations.successful == allocations.released, "designated construction cleanup mismatch");
        ++cases;
    }
    constexpr std::int64_t count = 257;
    for (const auto kind : {NodeKind::array_literal, NodeKind::construct, NodeKind::array_zero}) {
        // ArrayZero selects the constructor profile; its nonempty result must
        // be ArrayLiteral. No input profile imposes a fixed arity ceiling.
        const bool designated = kind == NodeKind::construct, constructor = kind == NodeKind::array_zero;
        const auto stop = constructor ? Stop::constructor_braces : Stop::semicolon;
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
            require(arena.parse(source, stop) == Words{wire(Status::success),
                                                       count,
                                                       count + 1,
                                                       close + 1,
                                                       static_cast<std::int64_t>(source.size() - 1),
                                                       0} &&
                        arena.read(count) == NodeWords{wire(designated ? NodeKind::construct : NodeKind::array_literal),
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
                require(arena.read(index) == NodeWords{wire(NodeKind::literal), token, -1, -1, 1, token, token},
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
            require(result[0] == wire(Status::allocation_failure) && result[1] == -1,
                    "aggregate allocation/growth failure did not fail closed");
            if (result[2] > 0)
                require(arena.read(0) == NodeWords{wire(NodeKind::literal), first, -1, -1, 1, first, first},
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
        require(argc == 40, "expected twenty-six compiler, six aggregate and seven typed consumer source paths");
        grammarExpectations();
        diagnosticExpectations();
        // Table rows cover ordinary semicolon inputs. Keep distinct trivia,
        // boundary/depth and alternate stop-mode contracts explicit here.
        supported("1 // comment\n + 2;");
        supported("one // name trivia\n :: two(1, other.run()).field[2].at(3);");
        supported(chain(100) + ";");
        supported(chain(128) + ";");
        supported(std::string(127, '(') + "1" + std::string(127, ')') + ";");
        supported(std::string(127, '-') + "1;");
        supported("1 + 2)", Stop::close_parenthesis);
        supported("target = 2;", Stop::assignment);
        supported("1 + 2;", Stop::assignment);
        supported("a[1] = 2;", Stop::assignment);
        supported("f(a[1], b.member))", Stop::close_parenthesis);
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
        for (const auto &group : returnedErrors)
            for (const auto &expression : group.sources)
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
        rawCase("1;", Status::success);
        rawCase("{1};", Status::success);
        rawCase("f(1);", Status::success);
        rawCase("a[1;", Status::expected_index_close);
        rawCase("a.;", Status::expected_identifier);
        rawCase("a.true;", Status::reserved_identifier);
        rawCase("a.array;", Status::reserved_builtin);
        rawCase("a.__au_private;", Status::reserved_prefix);
        rawCase("1+;", Status::expected_expression);
        rawCase("(1;", Status::expected_close);
        rawCase("1 2;", Status::expected_end);
        for (const auto &source : {":;", "];", ",;"})
            rawCase(source, Status::expected_expression);
        for (const auto &source : {"1:2;", "1]2;", "1,2;", "1(2);", "true(2);", "(1)(2);"})
            rawCase(source, Status::expected_end);
        rawCase(std::string(128, '(') + "1" + std::string(128, ')') + ";", Status::nesting_limit);
        rawCase(chain(129) + ";", Status::depth_limit);
        rawCase("1)", Status::success, Stop::close_parenthesis);
        rawCase("name=", Status::success, Stop::assignment);
        byteStrings();
        constructors();
        aggregateSyntax();
        typedSyntax();
        callableSyntax();
        callableDiagnostics();
        serviceAdmission();
        callableParameterLimit();
        fieldSyntax();
        fieldDiagnostics();
        declarationContexts();
        preambleEnumSyntax();
        moduleSyntax();
        moduleDiagnostics();
        preambleEnumDiagnostics();
        rawDeclarations();
        rawPreambleEnums();
        rawModules();
        rawAdmission();
        rawCallableGrowth();
        rawFields();
        declarationTypeSyntax();
        repeatedResidualType();
        declarationTypeDiagnostics();
        declarationTypeContexts();
        rawDeclarationTypes();
        rawDeclarationTypeGrowth();
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
        resolvedModules();
        resolvedVisibility();
        rawResolutionOwnership();
        resolvedCompilerSources(argv + 1);
        bootstrapSources(argv + 1);
        consumerSources({argv[4], argv[5], argv[6], argv[7], argv[8], argv[37]});
        typedConsumerSources(argv + 9);
        require(wholeCallables >= 172 && wholeFields >= 76,
                "whole-declaration coverage omitted historical bootstrap callables/fields");
        std::cout
            << "PASS hosted parser " << cases
            << " explicit AST/diagnostic, dispatch-consistency and ABI cases, 199-node/frame and "
               "257-argument/aggregate growth with allocation cleanup; "
               "dispatch-consistent constructor/string roots from all three actual bootstrap sources; "
               "14 aggregate roots including 512 XFS elements, 16 direct typed product roots, "
               "1,285-record type growth, all 125 historical and all new bootstrap bodies, "
               "513-statement/128-block growth and fifth-owner cleanup; "
               "independent declaration types and diagnostics, all 490 historical and new compiler declaration "
               "type occurrences, 31-record standalone type growth with existing-owner cleanup; "
               "whole callable/field boundaries, 513-entry callable and 31-type field failure sweeps; "
               "three compiler preambles, two imports, twelve enums/233 cases, 513-import and 256-case failure sweeps; "
               "18 compiler classes/six namespace blocks, std::array/pair/make_pair template inventories, "
               "whole-module container/depth/header contracts and post-grammar admission scratch-failure controls; "
               "typed native identities, dependency/instance order, exact nominal reflection views, selected "
               "overloads, "
               "independent concrete layouts and retained lint/template-error source spans; "
               "twenty-four-module compiler graph, fifteen typed classes/14 enums/513 cases, all implementation "
               "declaration boundaries, generated typed-row extents and eleven-owner Session failure/release "
               "prefixes\n";
    } catch (const std::exception &error) {
        std::cerr << "FAIL " << error.what() << '\n';
        return 1;
    }
}
