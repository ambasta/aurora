// Exercise the real Aurora phase and compare complete ASTs/diagnostics with the
// retained C++ parser. Raw records are deliberately independent of the adapter.
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
#include <optional>
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
using aurora::hosted_parser::NodeKind;
using aurora::hosted_parser::Status;
using aurora::hosted_parser::Stop;
using Words = std::array<std::int64_t, 5>;
using NodeWords = std::array<std::int64_t, 7>;
using EdgeWords = std::array<std::int64_t, 5>;
constexpr std::int64_t wire(NodeKind value) {
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
            "expression shape/spelling/depth differs");
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
void sameStatements(const std::vector<aurora::StatementPtr> &a, const std::vector<aurora::StatementPtr> &b) {
    require(a.size() == b.size(), "statement count differs");
    for (std::size_t i = 0; i < a.size(); ++i) {
        require(a[i]->kind == b[i]->kind && a[i]->name == b[i]->name && a[i]->fieldName == b[i]->fieldName &&
                    a[i]->mutableValue == b[i]->mutableValue && a[i]->type == b[i]->type,
                "statement shape differs");
        sameSpan(a[i]->token.span, b[i]->token.span);
        sameSpan(a[i]->bindingSpan, b[i]->bindingSpan);
        sameExpression(a[i]->expr, b[i]->expr);
        sameExpression(a[i]->target, b[i]->target);
        sameStatements(a[i]->body, b[i]->body);
        sameStatements(a[i]->other, b[i]->other);
    }
}
void sameFunctions(const std::vector<aurora::Function> &a, const std::vector<aurora::Function> &b) {
    require(a.size() == b.size(), "function/method count differs");
    for (std::size_t i = 0; i < a.size(); ++i) {
        require(a[i].name == b[i].name && a[i].scope == b[i].scope && a[i].exported == b[i].exported &&
                    a[i].constructor == b[i].constructor && a[i].receiverConst == b[i].receiverConst &&
                    a[i].publicAccess == b[i].publicAccess && a[i].result == b[i].result &&
                    a[i].params.size() == b[i].params.size() && a[i].initializers.size() == b[i].initializers.size(),
                "function/method shape differs");
        sameToken(a[i].token, b[i].token);
        for (std::size_t j = 0; j < a[i].params.size(); ++j) {
            const auto &left = a[i].params[j], &right = b[i].params[j];
            require(left.name == right.name && left.type == right.type && left.borrowed == right.borrowed &&
                        left.borrowConst == right.borrowConst,
                    "parameter shape/order differs");
            sameSpan(left.borrowSpan, right.borrowSpan);
        }
        for (std::size_t j = 0; j < a[i].initializers.size(); ++j) {
            sameToken(a[i].initializers[j].first, b[i].initializers[j].first);
            sameExpression(a[i].initializers[j].second, b[i].initializers[j].second);
        }
        sameStatements(a[i].body, b[i].body);
    }
}
void sameClasses(const std::vector<aurora::ClassDefinition> &a, const std::vector<aurora::ClassDefinition> &b) {
    require(a.size() == b.size(), "class count differs");
    for (std::size_t i = 0; i < a.size(); ++i) {
        require(a[i].name == b[i].name && a[i].scope == b[i].scope && a[i].exported == b[i].exported &&
                    a[i].fields.size() == b[i].fields.size(),
                "class shape differs");
        sameToken(a[i].token, b[i].token);
        for (std::size_t j = 0; j < a[i].fields.size(); ++j) {
            sameToken(a[i].fields[j].token, b[i].fields[j].token);
            require(a[i].fields[j].type == b[i].fields[j].type &&
                        a[i].fields[j].publicAccess == b[i].fields[j].publicAccess,
                    "field shape/order differs");
        }
        sameFunctions(a[i].methods, b[i].methods);
    }
}
aurora::Program compareProgram(const std::vector<aurora::Token> &tokens, bool valid = true) {
    std::array<std::optional<aurora::Program>, 2> programs;
    std::array<std::optional<aurora::Diagnostic>, 2> errors;
    for (std::size_t i = 0; i < 2; ++i) {
        try {
            programs[i] = aurora::Parser(tokens, i == 0).parse();
        } catch (const aurora::Error &error) {
            errors[i] = error.diagnostic;
        }
    }
    require(bool(programs[0]) == valid && bool(programs[1]) == valid, "acceptance differs from reference/expectation");
    if (!valid) {
        require(errors[0] && errors[1], "missing exact rejection");
        require(errors[0]->code == errors[1]->code && errors[0]->message == errors[1]->message,
                "diagnostic code/message differs: " + errors[0]->message + " versus " + errors[1]->message);
        sameSpan(errors[0]->span, errors[1]->span);
    } else {
        sameFunctions(programs[0]->functions, programs[1]->functions);
        sameFunctions(programs[0]->functionTemplates, programs[1]->functionTemplates);
        sameClasses(programs[0]->classes, programs[1]->classes);
        sameClasses(programs[0]->templates, programs[1]->templates);
    }
    ++cases;
    return valid ? std::move(*programs[1]) : aurora::Program{};
}
void compareProgram(const std::string &source, bool valid = true) {
    context = source;
    compareProgram(aurora::lex(source, "parser-differential.au"), valid);
}
std::string chain(std::size_t count) {
    std::string result = "1";
    while (--count)
        result += "+1";
    return result;
}
void supported(const std::string &text, Stop stop = Stop::Semicolon) {
    context = text;
    const auto tokens = aurora::lex(text, "supported.au");
    std::size_t position = 0;
    const auto hosted = aurora::parseHostedExpression(tokens, position, stop);
    require(bool(hosted), "supported expression silently fell back");
    aurora::Parser reference(tokens, false);
    const auto expected = reference.expr();
    sameExpression(hosted, expected);
    sameToken(tokens[position], reference.peek());
    if (text == chain(100) + ";")
        require(nodes(hosted) == 199 && hosted->depth == 100, "100 terms did not yield 199 real Aurora nodes");
    ++cases;
}
void unsupported(const std::string &text) {
    context = text;
    const auto tokens = aurora::lex(text, "unsupported.au");
    const auto before = tokens;
    std::size_t position = 0;
    require(!aurora::parseHostedExpression(tokens, position, Stop::Semicolon),
            "unsupported expression was partially accepted");
    require(position == 0 && tokens.size() == before.size(), "fallback was not atomic");
    for (std::size_t i = 0; i < tokens.size(); ++i) {
        require(tokens[i].text == before[i].text, "fallback changed a token");
        sameSpan(tokens[i].span, before[i].span);
    }
    compareProgram("module fallback; auto f()->i64{return " + text + "}");
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
                const aurora::ExpressionPtr &expected) {
    const auto expression = aurora::parseHostedExpression(tokens, position, stop);
    require(bool(expression), "bootstrap expression silently fell back");
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
void bootstrapSources(char **paths) {
    std::size_t initializers = 0, strings = 0, newInitializers = 0;
    const std::array<std::string, 3> modules{
        "aurora.compiler.lexer", "aurora.compiler.expression_arena", "aurora.compiler.expression_parser"};
    for (std::size_t i = 0; i < modules.size(); ++i) {
        context = paths[i];
        std::ifstream input(paths[i], std::ios::binary);
        require(bool(input), "cannot read actual bootstrap source");
        const std::string source((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
        require(!input.bad(), "cannot finish reading actual bootstrap source");
        const auto tokens = aurora::lex(source, paths[i]);
        const auto program = compareProgram(tokens);
        require(program.moduleName == modules[i], "unexpected bootstrap source module/order");
        bootstrapFunctions(tokens, program.functions, initializers, strings, newInitializers);
        bootstrapFunctions(tokens, program.functionTemplates, initializers, strings, newInitializers);
        for (const auto &definition : program.classes)
            bootstrapFunctions(tokens, definition.methods, initializers, strings, newInitializers);
        for (const auto &definition : program.templates)
            bootstrapFunctions(tokens, definition.methods, initializers, strings, newInitializers);
    }
    context = "actual bootstrap source roots";
    require(initializers == 40 && strings == 5 && newInitializers == 2,
            "expected the original 40 constructor and 5 string roots plus 2 field-token initializers, observed " +
                std::to_string(initializers) + ", " + std::to_string(strings) + " and " +
                std::to_string(newInitializers));
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
            auto position = start;
            const auto before = tokens;
            require(!aurora::parseHostedExpression(
                        tokens, position, assertion ? Stop::CloseParenthesis : Stop::Semicolon) &&
                        position == start,
                    "actual reflection consumer did not retain atomic whole-root fallback");
            require(tokens.size() == before.size(), "reflection fallback changed token count");
            for (std::size_t index = 0; index < tokens.size(); ++index)
                sameToken(tokens[index], before[index]);
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
        const auto program = compareProgram(tokens);
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
              sizeof(EdgeWords) == 40);
class RawArena {
    aurora::hosted::bytes::Region region;
    // This storage is never copied or inspected as an owner descriptor. Aurora
    // constructs and consumes it; the host only supplies region identity.
    std::uint64_t before = canary;
    std::array<std::uint64_t, 17> record{};
    std::uint64_t after = canary;
    bool active = true;

public:
    explicit RawArena(Allocations &allocations, std::uint64_t quota = 1048576, std::int64_t initial = 0)
        : region(quota, allocations.allocator()) {
        record[0] = region.id();
        const std::array<std::uint64_t, 2> input{region.id(), static_cast<std::uint64_t>(initial)};
        checked_hosted_parser_create(input.data(), data());
        guards();
    }
    ~RawArena() {
        if (active)
            checked_hosted_parser_release(record.data());
    }
    RawArena(const RawArena &) = delete;
    RawArena &operator=(const RawArena &) = delete;
    void *data() {
        return record.data() + 1;
    }
    void guards() const {
        require(before == canary && after == canary, "arena write escaped its ABI extent");
    }
    Words parse(const std::string &source, Stop stop = Stop::Semicolon, std::int64_t offset = 0) {
        const std::array<std::uint64_t, 11> input{0,
                                                  reinterpret_cast<std::uintptr_t>(source.data()),
                                                  0,
                                                  0,
                                                  0,
                                                  0,
                                                  source.size(),
                                                  static_cast<std::uint64_t>(offset),
                                                  1,
                                                  0,
                                                  static_cast<std::uint64_t>(stop)};
        GuardedWords<5> output;
        checked_hosted_parser_parse(data(), input.data(), output.value.data());
        output.check();
        guards();
        require(output.value[2] == checked_hosted_parser_count(data()),
                "reported arena count differs from real storage");
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
    aurora::hosted::bytes::Metrics metrics() const {
        return region.metrics();
    }
    void finish() {
        checked_hosted_parser_release(record.data());
        active = false;
        guards();
        const auto final = region.metrics();
        require(final.used == 0 && final.live_allocations == 0 && final.releases == final.successful_allocations,
                "Aurora cleanup leaked payload or ownership metadata");
        require(region.close(), "empty parser region did not close");
    }
};
void rawCase(const std::string &source, Status expected, Stop stop = Stop::Semicolon) {
    context = "raw ABI " + source;
    Allocations allocations;
    RawArena arena(allocations);
    const auto result = arena.parse(source, stop);
    require(result[0] == static_cast<std::int64_t>(expected), "raw status enum differs");
    if (expected == Status::Unsupported)
        require(result == Words{wire(Status::Unsupported), -1, 0, 0, 0}, "raw fallback was not empty and atomic");
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
        supported("// preceding trivia\r\n\t" + spelling + ";");
        supported(spelling + ")", Stop::CloseParenthesis);
        compareProgram("module strings; class Text { array<u8,512> bytes; public: Text():bytes(" + spelling +
                       "){} auto first() const->u8 {return bytes[0];} }; "
                       "auto f()->i64 {const array<u8,4096> bytes=" +
                       spelling + ";return 0;}");
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
        compareProgram(prefix + expression + suffix);
    }
    compareProgram("export module constructors; namespace ns { class Pair { i64 first; i64 second; public: "
                   "Pair(i64 x):second // initializer order and field-token trivia\n (ns::value),\n"
                   "first(f(\"text\", a[x + 1])){} auto get() const->i64 {return first + second;} }; }");
    compareProgram("export module constructors; template<Scalar T> class Box { T value; public: "
                   "Box(T x):value(x){} auto read() const->T {return value;} };");
    // Excluded roots must continue to fall back as a whole, including after a
    // supported string/call prefix and inside parenthesized initializers.
    for (const auto &expression : {"size_of(i64)", "type_id(array<u8,2>)", "field_count(Box)", "f(size_of(i64))"}) {
        rawCase(std::string(expression) + ")", Status::Unsupported, Stop::CloseParenthesis);
        compareProgram(prefix + expression + suffix);
    }
    for (const auto &expression : {"f<i64>(1)", "x<y<z>>(a)", "f<a<b<c>>>(0)"})
        compareProgram(prefix + expression + suffix);
    compareProgram("export module constructors; class Box { array<i64,2> values; public: Box():values{1,2}{} };");
    compareProgram("export module constructors; class Box { array<i64,2> values; public: Box():values{}{} };");
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
        compareProgram(prefix + expression + suffix, false);
    compareProgram("export module constructors; class Box { i64 value; public: Box():value(1 {} };", false);
    compareProgram("export module constructors; class Box { i64 value; public: Box():value(1),{} };", false);
}
void constructorBraces(const std::string &contents) {
    const std::string source = "export module braces; class Box { array<i64,4> value; array<i64,4> other; public: "
                               "Box():value" +
                               contents + ",other{}{} };";
    context = source;
    const auto tokens = aurora::lex(source, "constructor-braces.au");
    const auto program = compareProgram(tokens);
    require(program.classes.size() == 1 && program.classes[0].methods.size() == 1,
            "constructor-brace fixture lost its class/method");
    const auto &initializers = program.classes[0].methods[0].initializers;
    require(initializers.size() == 2 && initializers[0].first.text == "value" && initializers[1].first.text == "other",
            "constructor-brace field order differs");
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
        compareProgram("module aggregates; auto f()->i64{return " + std::string(expression) + "}");
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
    constructorBraces("{" + grouped + "}");
    compareProgram("module depth; auto f()->i64{return {" + grouped + "};}", false);
    const auto nested = std::string(127, '{') + "1" + std::string(127, '}');
    supported(nested + ";");
    compareProgram("module depth; auto f()->i64{return {" + nested + "};}", false);
    constructorBraces("{" + chain(127) + "}");
    compareProgram("export module depth; class Box { array<i64,1> value; public: Box():value{" + chain(128) + "}{} };",
                   false);
    // Reflection excludes the entire aggregate, including supported siblings.
    for (const auto &expression : {"{1,size_of(i64)};",
                                   "Box{.first=1,.second=type_id(array<u8,2>)};",
                                   "f({1,field_count(Box)});",
                                   "{Box{.value=f(size_of(i64))}};"}) {
        unsupported(expression);
        rawCase(expression, Status::Unsupported);
    }
    for (const auto &contents : {"{1,size_of(i64)}", "{Box{.value=type_id(array<u8,2>)}}"}) {
        const std::string text = std::string("value") + contents;
        context = text;
        const auto tokens = aurora::lex(text, "constructor-fallback.au");
        const auto before = tokens;
        std::size_t position = 0;
        require(!aurora::parseHostedExpression(tokens, position, Stop::ConstructorBraces) && position == 0,
                "constructor aggregate fallback was not whole-root and atomic");
        require(tokens.size() == before.size(), "constructor fallback changed token count");
        for (std::size_t index = 0; index < tokens.size(); ++index)
            sameToken(tokens[index], before[index]);
        rawCase(text, Status::Unsupported, Stop::ConstructorBraces);
        compareProgram("export module fallback; class Box { array<i64,2> value; public: Box():" + text + "{} };");
    }
    // The actual dispatcher owns template selection; its retained C++ oracle
    // must also agree at malformed boundaries and preserve arithmetic shifts.
    for (const auto &expression : {"{f<i64>(1),2}",
                                   "Box{.first=f<a<b<c>>>(0),.second={x<y<z>>(a)}}",
                                   "f({Box<i64>{.value=1},2})",
                                   "{1,f<a<b<c>>(0)}"}) {
        compareProgram("module templates; auto f()->i64{return " + std::string(expression) + ";}");
        compareProgram("export module templates; class Box { array<i64,2> value; public: Box():value{" +
                       std::string(expression) + "}{} };");
    }
    for (const auto &expression : {"{f<T)>(0)}", "{f<T]>(0)}", "{f<T:>(0)}", "Box{.value=f<T)>(0)}", "f({f<T]>(0)})"}) {
        compareProgram("module templates; auto f()->i64{return " + std::string(expression) + ";}", false);
        compareProgram("export module templates; class Box { array<i64,2> value; public: Box():value{" +
                           std::string(expression) + "}{} };",
                       false);
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
        compareProgram("module errors; auto f()->i64{return " + std::string(expression) + "}", false);
    for (const auto &contents : {"{,}", "{1,}", "{1 2}", "{1", "{1]}", "{Box{.value=1,}}"})
        compareProgram("export module errors; class Box { array<i64,2> value; public: Box():value" +
                           std::string(contents) + "{} };",
                       false);
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
    rawCase("{};", Status::Invalid, static_cast<Stop>(4));
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
        require(used.successful_allocations > 4 && used.peak_live_allocations == 3 && used.live_allocations == 3,
                "parser did not grow its node/frame stores while retaining the empty edge owner");
        successful = allocations.successful;
        arena.finish();
        require(allocations.released == successful, "success cleanup mismatch");
    }
    for (std::size_t allowed = 0; allowed < 3; ++allowed) {
        Allocations allocations;
        allocations.allowed = allowed;
        RawArena arena(allocations);
        require(arena.parse("size_of(i64);")[0] == wire(Status::AllocationFailure),
                "failed arena allocation silently fell back on unsupported syntax");
        arena.finish();
    }
    // Refuse every allocation in sequence, including frame and node growth.
    // All partial graphs still leave all three owners releasable exactly once.
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
        require(used.peak_used > 8 * 40 + 8 * 56 && used.successful_allocations > 4 &&
                    used.peak_live_allocations == 3 && used.live_allocations == 3,
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
        require(metrics.successful_allocations > 10 && metrics.live_allocations == 3 &&
                    metrics.peak_live_allocations == 3,
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
            require(metrics.successful_allocations > 10 && metrics.live_allocations == 3 &&
                        metrics.peak_live_allocations == 3,
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
        if (constructor)
            constructorBraces(source.substr(6, source.size() - 7));
        else
            supported(source);
        ++cases;
    }
}

} // namespace

int main(int argc, char **argv) {
    try {
        context = "fixture arguments";
        require(argc == 9, "expected three bootstrap and five aggregate consumer source paths");
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
            unsupported(expression);
        compareProgram("module templates; auto f()->i64{return f<i64>(1);}");
        compareProgram("module templates; auto f()->i64{return x<y<z>>(a);}");
        compareProgram("module templates; auto f()->i64{return f<T)>(0);}", false);
        compareProgram("module templates; auto f()->i64{if(f<T)>(0)){return 1;}return 0;}", false);
        compareProgram("module templates; auto f()->i64{return f<a<b<c>>>(0);}");
        compareProgram("module templates; auto f()->i64{return f<a<b<c>>(0);}");
        for (const auto &expression : {"(f<T)>(0)", "f<T]>(0)", "f<T:>(0)"})
            compareProgram("module errors; auto f()->i64{return " + std::string(expression) + ";}", false);
        compareProgram("module hooks; auto f()->i64 { i64 x = 1+2; const i64 y = 3; x = x+y; x+1; "
                       "static_assert(true && !false); if(x>0){x=x-1;}else{x=0;} while(x<4){x=x+1;} return x*2; }");
        compareProgram("module fallback; auto f()->i64 { i64 x=f(1); x=f(2); if(f(1)){return f(2);} "
                       "while(f(0)){x=f(3);} static_assert(f(1)); return x<y<z>>(a); }");
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
            compareProgram("module errors; auto f()->i64{return " + std::string(expression) + "}", false);
        compareProgram("module depth; auto f()->i64{return " + chain(129) + ";}", false);
        compareProgram(
            "module depth; auto f()->i64{return " + std::string(128, '(') + "1" + std::string(128, ')') + ";}", false);
        compareProgram("module depth; auto f()->i64{return " + std::string(128, '-') + "1;}", false);
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
            compareProgram("module errors; auto f()->i64{return " + std::string(expression) + "}", false);
        std::string members = "a", indices = "a", calls = "1";
        for (int i = 0; i < 127; ++i) {
            members += ".field";
            indices += "[0]";
            calls = "f(" + calls + ")";
        }
        supported(members + ";");
        supported(indices + ";");
        supported(calls + ";");
        compareProgram("module depth; auto f()->i64{return " + members + ".field;}", false);
        compareProgram("module depth; auto f()->i64{return " + indices + "[0];}", false);
        compareProgram("module depth; auto f()->i64{return f(" + calls + ");}", false);
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
        rawAggregateDiagnostics();
        abiControls();
        rawGrowth();
        rawFrameGrowth();
        rawArguments();
        rawAggregates();
        bootstrapSources(argv + 1);
        consumerSources(argv + 4);
        std::cout
            << "PASS hosted parser " << cases
            << " differential/ABI cases, 199-node/frame and 257-argument/aggregate growth with allocation cleanup; "
               "5 byte-string and 42 constructor roots from actual bootstrap sources; "
               "14 aggregate roots from actual library/example consumers, including 512 XFS elements\n";
    } catch (const std::exception &error) {
        std::cerr << "FAIL " << error.what() << '\n';
        return 1;
    }
}
