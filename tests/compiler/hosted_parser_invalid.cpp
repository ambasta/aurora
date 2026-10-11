// Host-only representation controls. Aurora owns grammar; these stubs exercise
// safe copied-record conversion, bounded ownership, cleanup and cursor commits.
#include "lexer.hpp"
#include "hosted_parser.hpp"
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <functional>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <utility>
#include <vector>

namespace {
using ResultWords = std::array<std::int64_t, 5>;
using NodeWords = std::array<std::int64_t, 7>;
using EdgeWords = std::array<std::int64_t, 5>;
using TypeWords = std::array<std::int64_t, 8>;
using StatementWords = std::array<std::int64_t, 11>;
using InputWords = std::array<std::uint64_t, 18>;
static_assert(sizeof(ResultWords) == sizeof(aurora::hosted_abi::compiler_parser::ParseResult) &&
              sizeof(NodeWords) == sizeof(aurora::hosted_abi::compiler_parser::AstNode) &&
              sizeof(EdgeWords) == sizeof(aurora::hosted_abi::compiler_parser::ChildEdge) &&
              sizeof(TypeWords) == sizeof(aurora::hosted_abi::compiler_parser::TypeSyntax) &&
              sizeof(StatementWords) == sizeof(aurora::hosted_abi::compiler_parser::StatementSyntax) &&
              sizeof(InputWords) == sizeof(aurora::hosted_abi::ParserInput));
using aurora::DiagnosticCode;
using aurora::hosted_parser::NodeKind;
using aurora::hosted_parser::StatementKind;
using aurora::hosted_parser::Status;
using aurora::hosted_parser::Stop;
using aurora::hosted_parser::TypeKind;
template <class T> constexpr std::int64_t wire(T value) {
    return static_cast<std::int64_t>(value);
}
ResultWords result;
std::vector<NodeWords> records;
std::vector<EdgeWords> edges;
std::vector<TypeWords> types;
std::vector<StatementWords> statements;
InputWords capturedInput{};
void *arenaAddress = nullptr;
std::uint64_t arenaRegion = 0;
constexpr std::uint64_t arenaCanary = 0x746970656172656eULL;
std::int64_t count = 0, edgeCount = 0, typeCount = 0, statementCount = 0;
int created = 0, parsed = 0, released = 0, read = 0, edgeRead = 0, typeRead = 0;
int throwingRead = 0, statementRead = 0;
std::size_t cases = 0;
void require(bool value, const std::string &message) {
    if (!value)
        throw std::runtime_error(message);
}
void reset() {
    result = {wire(Status::success), 2, 3, 3, 3};
    records = {{wire(NodeKind::literal), 0, -1, -1, 1, 0, 0},
               {wire(NodeKind::literal), 2, -1, -1, 1, 2, 2},
               {wire(NodeKind::binary), 1, 0, 1, 2, 1, 1}};
    count = 3;
    edgeCount = typeCount = statementCount = 0;
    edges.clear();
    types.clear();
    statements.clear();
    created = parsed = released = read = edgeRead = typeRead = statementRead = throwingRead = 0;
    capturedInput = {};
    arenaAddress = nullptr;
}
void fixture(const std::string &source,
             std::vector<NodeWords> nodes,
             std::vector<EdgeWords> arguments = {},
             std::int64_t consumed = -1) {
    const auto tokens = aurora::lex(source, "forged.au");
    records = std::move(nodes);
    edges = std::move(arguments);
    count = static_cast<std::int64_t>(records.size());
    edgeCount = static_cast<std::int64_t>(edges.size());
    if (consumed < 0)
        consumed = static_cast<std::int64_t>(tokens.size()) - 2;
    result = {wire(Status::success),
              count - 1,
              count,
              consumed,
              static_cast<std::int64_t>(tokens[static_cast<std::size_t>(consumed)].span.begin.offset)};
}
void callFixture(const std::string &source = "f(1,2);") {
    fixture(source,
            {{wire(NodeKind::literal), 2, -1, -1, 1, 2, 2},
             {wire(NodeKind::literal), 4, -1, -1, 1, 4, 4},
             {wire(NodeKind::call), 0, 1, 2, 2, 0, 5}},
            {{0, -1, 1, 2, -1}, {1, 0, 2, 2, -1}});
}
void methodFixture(const std::string &source = "a.m(1);") {
    fixture(source,
            {{wire(NodeKind::name), 0, -1, -1, 1, 0, 0},
             {wire(NodeKind::literal), 4, -1, -1, 1, 4, 4},
             {wire(NodeKind::method_call), 2, 1, 2, 2, 2, 5}},
            {{0, -1, 1, 2, -1}, {1, 0, 2, 2, -1}});
}
void indexFixture(const std::string &source = "a[i];") {
    fixture(source,
            {{wire(NodeKind::name), 0, -1, -1, 1, 0, 0},
             {wire(NodeKind::name), 2, -1, -1, 1, 2, 2},
             {wire(NodeKind::index), 1, 0, 1, 2, 1, 3}});
}
void arrayFixture(const std::string &source = "{1,2};") {
    fixture(source,
            {{wire(NodeKind::literal), 1, -1, -1, 1, 1, 1},
             {wire(NodeKind::literal), 3, -1, -1, 1, 3, 3},
             {wire(NodeKind::array_literal), 0, 1, 2, 2, 0, 4}},
            {{0, -1, 1, 2, -1}, {1, 0, 2, 2, -1}});
}
void constructFixture(const std::string &source = "T{.a=1,.b=2};") {
    fixture(source,
            {{wire(NodeKind::literal), 5, -1, -1, 1, 5, 5},
             {wire(NodeKind::literal), 10, -1, -1, 1, 10, 10},
             {wire(NodeKind::construct), 0, 1, 2, 2, 0, 11}},
            {{0, -1, 1, 2, 3}, {1, 0, 2, 2, 8}});
}
void constructorFixture(const std::string &source = "field{1};", bool empty = false) {
    if (empty)
        fixture(source, {{wire(NodeKind::array_zero), 0, -1, 0, 1, 0, 2}}, {}, 3);
    else
        fixture(source,
                {{wire(NodeKind::literal), 2, -1, -1, 1, 2, 2}, {wire(NodeKind::array_literal), 0, 0, 1, 2, 0, 3}},
                {{0, -1, 1, 2, -1}},
                4);
}
void typedFixture(const std::string &source,
                  std::vector<TypeWords> syntax,
                  std::vector<NodeWords> nodes = {},
                  std::vector<EdgeWords> arguments = {}) {
    const auto tokens = aurora::lex(source, "forged.au");
    if (nodes.empty())
        nodes = {{wire(NodeKind::call), 0, -1, 0, 1, 0, static_cast<std::int64_t>(tokens.size()) - 3}};
    fixture(source, std::move(nodes), std::move(arguments));
    types = std::move(syntax);
    typeCount = static_cast<std::int64_t>(types.size());
}
void reflectedFixture(const std::string &source = "size_of(i64);") {
    typedFixture(source, {{wire(TypeKind::i64_type), 2, 2, 4, -1, -1, 0, 2}});
}
void splitFixture(const std::string &source = "f<Box<i64>>();") {
    typedFixture(source,
                 {{wire(TypeKind::i64_type), 4, 4, 8, -1, -1, -1, 0},
                  {wire(TypeKind::named), 2, 2, 10, 0, -1, -1, 0},
                  {wire(TypeKind::named), 0, 0, 11, 1, -1, 0, 1}});
}
std::string nestedTemplateSource(int levels, bool reflected) {
    std::string source = reflected ? "size_of(" : "";
    for (int level = 0; level < levels; ++level)
        source += level == 0 && !reflected ? "f<" : "Box<";
    source += "i64";
    for (int level = 0; level < levels; ++level)
        source += " >";
    return source + (reflected ? ");" : "();");
}
void nestedTemplateFixture(int levels, bool reflected) {
    const auto source = nestedTemplateSource(levels, reflected);
    const std::int64_t begin = reflected ? 2 : 0;
    const auto scalar = begin + 2 * levels;
    std::vector<TypeWords> syntax{{wire(TypeKind::i64_type), scalar, scalar, scalar * 2, -1, -1, -1, 0}};
    for (int index = 0; index < levels; ++index) {
        const auto token = begin + 2 * (levels - index - 1);
        syntax.push_back({wire(TypeKind::named),
                          token,
                          token,
                          2 * (scalar + index + 1),
                          index,
                          -1,
                          index + 1 == levels ? 0 : -1,
                          index + 1 == levels ? (reflected ? 2 : 1) : 0});
    }
    typedFixture(source, std::move(syntax));
}
using Tokens = std::vector<aurora::Token>;
using Inspect = std::function<void(const aurora::ExpressionPtr &, const Tokens &)>;
void valid(const std::string &source,
           const std::function<void()> &configure,
           const Inspect &inspect,
           Stop stop = Stop::semicolon) {
    reset();
    configure();
    const auto tokens = aurora::lex(source, "forged.au");
    std::size_t position = 0;
    const auto actual = aurora::parseHostedExpression(tokens, position, stop);
    require(actual && position == static_cast<std::size_t>(result[3]) && created == 1 && parsed == 1 && released == 1 &&
                read == count && edgeRead == edgeCount && typeRead == typeCount,
            "conversion lost cursor, record reads or exact cleanup");
    inspect(actual, tokens);
    ++cases;
}
void invalid(const std::string &label, const std::function<void()> &mutate, const std::string &source = "1+2;") {
    reset();
    mutate();
    const auto tokens = aurora::lex(source, "forged.au");
    std::size_t position = 0;
    bool rejected = false;
    try {
        static_cast<void>(aurora::parseHostedExpression(tokens, position, Stop::semicolon));
    } catch (const aurora::Error &error) {
        rejected = error.diagnostic.code == DiagnosticCode::Internal &&
                   error.diagnostic.message == "hosted parser returned an invalid result";
    }
    require(rejected && position == 0 && created == 1 && parsed == 1 && released == 1,
            label + ": invalid representation escaped or changed cursor/cleanup");
    require(tokens.front().span.source->text == source, label + ": immutable source changed");
    ++cases;
}
void diagnostic(const std::string &source,
                Status status,
                std::size_t ordinal,
                aurora::DiagnosticCode code,
                const std::string &message,
                Stop stop = Stop::semicolon,
                bool secondHalf = false) {
    reset();
    const auto tokens = aurora::lex(source, "forged.au");
    result = {wire(status),
              -1,
              0,
              static_cast<std::int64_t>(ordinal),
              static_cast<std::int64_t>(tokens[ordinal].span.begin.offset) + (secondHalf ? 1 : 0)};
    count = 0;
    std::size_t position = 0;
    bool rejected = false;
    try {
        static_cast<void>(aurora::parseHostedExpression(tokens, position, stop));
    } catch (const aurora::Error &error) {
        const auto &span = error.diagnostic.span, &expected = tokens[ordinal].span;
        rejected = error.diagnostic.code == code && error.diagnostic.message == message &&
                   span.source == expected.source &&
                   span.begin.offset == expected.begin.offset + (secondHalf ? 1 : 0) &&
                   span.begin.line == expected.begin.line &&
                   span.begin.column == expected.begin.column + (secondHalf ? 1 : 0) &&
                   span.end.offset == expected.end.offset && span.end.line == expected.end.line &&
                   span.end.column == expected.end.column;
    }
    require(rejected && position == 0 && created == 1 && parsed == 1 && released == 1,
            "diagnostic conversion lost its specified message, location, cursor or cleanup");
    ++cases;
}
void conversionControls() {
    valid(
        "1+2;",
        [] {
        },
        [](const auto &tree, const auto &tokens) {
            require(tree->op == "binary" && tree->depth == 2 && tree->args.size() == 2 &&
                        tree->args[0]->token.text == "1" && tree->args[1]->token.text == "2" &&
                        tree->token.span.source == tokens[1].span.source &&
                        tree->token.span.begin.offset == tokens[1].span.begin.offset,
                    "binary conversion changed shape or source provenance");
        });
    for (const auto &[source, op] : std::vector<std::pair<std::string, std::string>>{
             {"42;", "number"}, {"true;", "bool"}, {"'a';", "byte"}, {"\"abc\";", "byte_string"}})
        valid(
            source,
            [&] {
                fixture(source, {{wire(NodeKind::literal), 0, -1, -1, 1, 0, 0}});
            },
            [&](const auto &tree, const auto &) {
                require(tree->op == op, "literal tag conversion changed");
            });
    valid(
        "ns::value;",
        [] {
            fixture("ns::value;", {{wire(NodeKind::name), 0, -1, -1, 1, 2, 2}});
        },
        [](const auto &tree, const auto &tokens) {
            require(tree->op == "name" && tree->token.text == "ns::value" &&
                        tree->token.span.end.offset == tokens[2].span.end.offset,
                    "qualified name lost spelling or span");
        });
    valid(
        "a[i];",
        [] {
            indexFixture();
        },
        [](const auto &tree, const auto &tokens) {
            require(tree->op == "index" && tree->args.size() == 2 && tree->token.text == "a" &&
                        tree->token.span.begin.offset == tokens[0].span.begin.offset,
                    "index lost receiver token or child shape");
        });
    valid(
        "a.m(1);",
        [] {
            methodFixture();
        },
        [](const auto &tree, const auto &) {
            require(tree->op == "method_call" && tree->args.size() == 2 && tree->args[0]->token.text == "a" &&
                        tree->args[1]->token.text == "1",
                    "method receiver order changed");
        });
    valid(
        "f(1,2);",
        [] {
            callFixture();
        },
        [](const auto &tree, const auto &) {
            require(tree->op == "call" && tree->args.size() == 2 && tree->args[0]->token.text == "1" &&
                        tree->args[1]->token.text == "2",
                    "argument chain order changed");
        });
    valid(
        "T{.a=1,.b=2};",
        [] {
            constructFixture();
        },
        [](const auto &tree, const auto &) {
            require(tree->op == "construct" && tree->fieldNames == std::vector<std::string>{"a", "b"} &&
                        tree->args.size() == 2,
                    "designated fields lost child alignment");
        });
    valid(
        "{1,2};",
        [] {
            arrayFixture();
        },
        [](const auto &tree, const auto &) {
            require(tree->op == "array_literal" && tree->args.size() == 2, "array children changed");
        });
    valid(
        "field{};",
        [] {
            constructorFixture("field{};", true);
        },
        [](const auto &tree, const auto &) {
            require(tree->op == "array_zero" && tree->args.empty() && tree->token.text == "field",
                    "zero initializer lost field token");
        },
        Stop::constructor_braces);
    valid(
        "f<Box<i64>>();",
        [] {
            splitFixture();
        },
        [](const auto &tree, const auto &) {
            require(tree->templateArguments.size() == 1 && tree->templateArguments[0].className == "Box" &&
                        tree->templateArguments[0].templateArguments.size() == 1 &&
                        tree->templateArguments[0].templateArguments[0].type == aurora::TypeKind::I64,
                    "nested template Type conversion changed");
        });
    valid(
        "size_of(array<i64,8>);",
        [] {
            typedFixture("size_of(array<i64,8>);",
                         {{wire(TypeKind::i64_type), 4, 4, 8, -1, -1, -1, 0},
                          {wire(TypeKind::capacity), 6, 6, 12, -1, -1, -1, 0},
                          {wire(TypeKind::array_type), 2, 2, 14, 0, 1, 0, 2}});
        },
        [](const auto &tree, const auto &) {
            require(tree->reflectedType == aurora::Type::array(aurora::Type::I64, 8), "array Type changed");
        });
    valid(
        "size_of(builtin::ConsoleSample);",
        [] {
            typedFixture("size_of(builtin::ConsoleSample);", {{wire(TypeKind::builtin_class), 2, 4, 8, -1, -1, 0, 2}});
        },
        [](const auto &tree, const auto &) {
            require(tree->reflectedType.isClass() && tree->reflectedType.displayName == "builtin::ConsoleSample" &&
                        tree->reflectedType.className == "__au_console_sample" && !tree->reflectedType.resolvedClass,
                    "builtin Type lost its semantic mapping");
        });
}
void resultControls() {
    for (const auto tag : {-1LL, static_cast<long long>(wire(Status::invalid)), std::numeric_limits<long long>::max()})
        invalid("status tag", [=] {
            result[0] = tag;
        });
    invalid("unsupported result", [] {
        result[0] = wire(Status::unsupported);
    });
    invalid("negative count", [] {
        result[2] = count = -1;
    });
    invalid("count mismatch", [] {
        count = 2;
    });
    invalid("excessive count", [] {
        result[2] = count = std::numeric_limits<std::int64_t>::max();
    });
    invalid("empty graph", [] {
        result[2] = count = 0;
        result[1] = -1;
    });
    for (const auto value : {-1LL, 0LL, 4LL, std::numeric_limits<long long>::max()})
        invalid("token count", [=] {
            result[3] = value;
        });
    for (const auto value : {-1LL, 0LL, 2LL, 5LL, std::numeric_limits<long long>::max()})
        invalid("source offset", [=] {
            result[4] = value;
        });
    for (const auto value : {-1LL, 0LL, 3LL, std::numeric_limits<long long>::max()})
        invalid("root index", [=] {
            result[1] = value;
        });
    for (const auto value : {-1LL, 3LL, std::numeric_limits<long long>::max()})
        invalid("edge count", [=] {
            edgeCount = value;
        });
    for (const auto value : {-1LL, 4LL, std::numeric_limits<long long>::max()})
        invalid("type count", [=] {
            typeCount = value;
        });
    invalid("error with root", [] {
        result[0] = wire(Status::expected_expression);
    });
}
void graphControls() {
    for (const auto kind : {-1LL, 0LL, static_cast<long long>(wire(NodeKind::array_zero) + 1)})
        invalid("node tag", [=] {
            records[0][0] = kind;
        });
    for (const auto value : {-1LL, 3LL, std::numeric_limits<long long>::max()}) {
        invalid("node token", [=] {
            records[0][1] = value;
        });
        invalid("node name bound", [=] {
            records[0][5] = value;
        });
        invalid("node close bound", [=] {
            records[0][6] = value;
        });
    }
    for (const auto value : {-2LL, -1LL, 2LL, std::numeric_limits<long long>::max()})
        invalid("child index", [=] {
            records[2][2] = value;
        });
    invalid("child cycle", [] {
        records[2][2] = 2;
    });
    invalid("shared child", [] {
        records[2][3] = 0;
    });
    invalid("leaf child", [] {
        records[0][2] = 0;
    });
    invalid("missing unary child", [] {
        records[0][0] = wire(NodeKind::unary);
    });
    invalid("orphan node", [] {
        records[2] = {wire(NodeKind::literal), 0, -1, -1, 1, 0, 0};
    });
    for (const auto value : {0LL, 1LL, 129LL, std::numeric_limits<long long>::max()})
        invalid("node depth", [=] {
            records[2][4] = value;
        });
    for (const auto value : {-1LL, 3LL, std::numeric_limits<long long>::max()})
        invalid(
            "edge child",
            [=] {
                callFixture();
                edges[0][0] = value;
            },
            "f(1,2);");
    for (const auto value : {-2LL, 0LL, std::numeric_limits<long long>::max()})
        invalid(
            "edge link",
            [=] {
                callFixture();
                edges[0][1] = value;
            },
            "f(1,2);");
    for (const auto value : {0LL, 129LL, std::numeric_limits<long long>::max()})
        invalid(
            "edge depth",
            [=] {
                callFixture();
                edges[0][3] = value;
            },
            "f(1,2);");
    for (const auto value : {0LL, 3LL, std::numeric_limits<long long>::max()})
        invalid(
            "edge length",
            [=] {
                callFixture();
                edges[0][2] = value;
            },
            "f(1,2);");
    invalid(
        "edge forward node",
        [] {
            callFixture();
            edges[0][0] = 2;
        },
        "f(1,2);");
    invalid(
        "shared edge child",
        [] {
            callFixture();
            edges[1][0] = 0;
        },
        "f(1,2);");
    invalid(
        "list length mismatch",
        [] {
            callFixture();
            records[2][3] = 1;
        },
        "f(1,2);");
    invalid(
        "list head out of bounds",
        [] {
            callFixture();
            records[2][2] = 2;
        },
        "f(1,2);");
    invalid(
        "orphan edge",
        [] {
            callFixture();
            records[2][2] = 0;
            records[2][3] = 1;
        },
        "f(1,2);");
    invalid(
        "shared edge chain",
        [] {
            fixture("f(g(1),2);",
                    {{wire(NodeKind::literal), 4, -1, -1, 1, 4, 4},
                     {wire(NodeKind::literal), 7, -1, -1, 1, 7, 7},
                     {wire(NodeKind::call), 2, 0, 1, 2, 2, 5},
                     {wire(NodeKind::call), 0, 2, 3, 3, 0, 8}},
                    {{0, -1, 1, 2, -1}, {1, 0, 2, 2, -1}, {2, 1, 3, 3, -1}});
        },
        "f(g(1),2);");
    invalid(
        "missing method receiver",
        [] {
            methodFixture();
            records[2][2] = -1;
            records[2][3] = 0;
        },
        "a.m(1);");
    invalid(
        "missing designated field",
        [] {
            constructFixture();
            edges[0][4] = -1;
        },
        "T{.a=1,.b=2};");
    invalid(
        "field index",
        [] {
            constructFixture();
            edges[0][4] = result[3];
        },
        "T{.a=1,.b=2};");
    invalid(
        "field on ordinary argument",
        [] {
            callFixture();
            edges[0][4] = 0;
        },
        "f(1,2);");
}
void typeControls() {
    const std::string source = "f<Box<i64>>();";
    const auto bad = [&](const std::string &label, const std::function<void()> &mutate) {
        invalid(
            label,
            [&] {
                splitFixture();
                mutate();
            },
            source);
    };
    for (const auto tag : {-1LL, 0LL, static_cast<long long>(wire(TypeKind::builtin_class) + 1)})
        bad("type tag", [=] {
            types[0][0] = tag;
        });
    for (const auto index : {-1LL, 8LL, std::numeric_limits<long long>::max()}) {
        bad("type token", [=] {
            types[0][1] = index;
        });
        bad("type name bound", [=] {
            types[0][2] = index;
        });
    }
    bad("type close bound", [] {
        types[0][3] = std::numeric_limits<std::int64_t>::max();
    });
    for (const auto index : {-2LL, 1LL, std::numeric_limits<long long>::max()})
        bad("type child index", [=] {
            types[1][4] = index;
        });
    bad("type cycle", [] {
        types[1][4] = 1;
    });
    bad("shared type child", [] {
        types[2][5] = 0;
    });
    bad("duplicate type child", [] {
        types[1][5] = 0;
    });
    bad("atomic type child", [] {
        types[1][0] = wire(TypeKind::i64_type);
    });
    bad("missing array child", [] {
        types[1][0] = wire(TypeKind::array_type);
    });
    bad("type second without first", [] {
        types[1][4] = -1;
        types[1][5] = 0;
    });
    bad("type role", [] {
        types[2][7] = 3;
    });
    bad("root owner index", [] {
        types[2][6] = result[3];
    });
    bad("child owner", [] {
        types[0][6] = 0;
    });
    bad("root reused as child", [] {
        types[1][6] = 0;
        types[1][7] = 1;
    });
    bad("orphan type root", [] {
        types[2][6] = 1;
    });
    bad("orphan type", [] {
        types[2][6] = -1;
        types[2][7] = 0;
    });
    bad("non-template root value", [] {
        types[2][0] = wire(TypeKind::array_type);
    });
    invalid(
        "capacity overflow",
        [] {
            typedFixture(
                "f<999999999999999999999>();",
                {{wire(TypeKind::capacity), 2, 2, 4, -1, -1, -1, 0}, {wire(TypeKind::named), 0, 0, 6, 0, -1, 0, 1}});
        },
        "f<999999999999999999999>();");
}
std::string depthFixture(int depth) {
    const std::string source = std::string(static_cast<std::size_t>(depth - 1), '!') + "1;";
    std::vector<NodeWords> nodes{{wire(NodeKind::literal), depth - 1, -1, -1, 1, depth - 1, depth - 1}};
    for (int index = 1; index < depth; ++index)
        nodes.push_back({wire(NodeKind::unary),
                         depth - index - 1,
                         index - 1,
                         -1,
                         std::min(index + 1, 128),
                         depth - index - 1,
                         depth - index - 1});
    fixture(source, std::move(nodes));
    return source;
}
void depthControls() {
    const auto inspect = [](const auto &tree, const auto &) {
        require(tree->depth == 128, "AST depth changed");
    };
    const std::string source = std::string(127, '!') + "1;";
    valid(
        source,
        [] {
            depthFixture(128);
        },
        inspect);
    invalid(
        "computed AST depth",
        [] {
            depthFixture(129);
        },
        std::string(128, '!') + "1;");
    // The single structural bound intentionally does not reproduce Aurora's
    // separate grammar nesting counters; it bounds recursive host values.
    valid(
        nestedTemplateSource(127, true),
        [] {
            nestedTemplateFixture(127, true);
        },
        [](const auto &tree, const auto &) {
            require(tree->reflectedType.isClass(), "deep Type conversion failed");
        });
    invalid(
        "structural Type depth",
        [] {
            nestedTemplateFixture(128, true);
        },
        nestedTemplateSource(128, true));
}
void inputControls() {
    for (int control = 0; control < 8; ++control) {
        reset();
        auto tokens = aurora::lex("1+2;", "input.au");
        std::size_t position = 0;
        auto stop = Stop::semicolon;
        aurora::hosted_parser::Context context;
        if (control == 0)
            position = tokens.size();
        if (control == 1)
            stop = static_cast<Stop>(99);
        if (control == 2)
            tokens[0].span.source.reset();
        if (control == 3)
            tokens[0].span.begin.offset = 99;
        if (control == 4)
            tokens[0].span.begin.column = 0;
        if (control == 5)
            context.typeParameters = {tokens[0], tokens[0], tokens[0]};
        if (control == 6)
            context.capacityParameters = {tokens[0], tokens[0]};
        if (control == 7)
            context.typeParameters = {tokens[0]};
        const auto initial = position;
        bool rejected = false;
        try {
            static_cast<void>(aurora::parseHostedExpression(tokens, position, stop, context));
        } catch (const aurora::Error &error) {
            rejected = error.diagnostic.code == DiagnosticCode::Internal;
        }
        require(rejected && position == initial && created == 0 && parsed == 0 && released == 0,
                "invalid input escaped before arena creation");
        ++cases;
    }
    for (int control = 0; control < 4; ++control) {
        reset();
        auto tokens = aurora::lex("1+2;", "input.au");
        if (control == 0)
            tokens[1].span.source.reset();
        if (control == 1)
            tokens[1].span.end.offset = 99;
        if (control == 2)
            tokens[1].text.clear();
        if (control == 3)
            tokens[1].span.begin.offset = tokens[1].span.end.offset + 1;
        std::size_t position = 0;
        bool rejected = false;
        try {
            static_cast<void>(aurora::parseHostedExpression(tokens, position, Stop::semicolon));
        } catch (const aurora::Error &error) {
            rejected = error.diagnostic.code == DiagnosticCode::Internal;
        }
        require(rejected && position == 0 && created == 1 && parsed == 1 && released == 1,
                "unsafe token access escaped or leaked arena");
        ++cases;
    }
    // Grammar and spelling correspondence are Aurora's responsibility. A
    // well-shaped record is converted without independently reparsing tokens.
    reset();
    auto supplied = aurora::lex("1+2;", "supplied.au");
    supplied[1].text = "opaque operator";
    std::size_t suppliedPosition = 0;
    const auto suppliedTree = aurora::parseHostedExpression(supplied, suppliedPosition, Stop::semicolon);
    require(suppliedTree->op == "binary" && suppliedTree->token.text == "opaque operator" && suppliedPosition == 3 &&
                released == 1,
            "adapter replayed operator grammar or spelling provenance");
    ++cases;
    reset();
    const auto tokens = aurora::lex("T;1+2;", "cursor.au");
    aurora::hosted_parser::Context context;
    context.typeParameters = {tokens[0]};
    result[4] += 2;
    std::size_t position = 2;
    const auto tree = aurora::parseHostedExpression(tokens, position, Stop::semicolon, context);
    require(tree->op == "binary" && position == 5 && capturedInput[7] == 2 && capturedInput[11] == 0 &&
                capturedInput[12] == 1 && capturedInput[17] == 1 && released == 1,
            "nonzero cursor or copied context span changed");
    ++cases;
}
void bodyFixture(bool local = false) {
    const std::string source = local ? "{i64 x=1;return x;}" : "{return 1;}";
    const auto tokens = aurora::lex(source, "body.au");
    records = local ? std::vector<NodeWords>{{wire(NodeKind::literal), 4, -1, -1, 1, 4, 4},
                                             {wire(NodeKind::name), 7, -1, -1, 1, 7, 7}}
                    : std::vector<NodeWords>{{wire(NodeKind::literal), 2, -1, -1, 1, 2, 2}};
    statements =
        local ? std::vector<StatementWords>{{wire(StatementKind::local), 1, 6, -1, 0, -1, 0, 2, -1, -1, 1},
                                            {wire(StatementKind::return_value), 6, 9, 0, 1, -1, -1, -1, -1, -1, 0},
                                            {wire(StatementKind::block), 0, 10, -1, -1, -1, -1, -1, 1, -1, 0}}
              : std::vector<StatementWords>{{wire(StatementKind::return_value), 1, 4, -1, 0, -1, -1, -1, -1, -1, 0},
                                            {wire(StatementKind::block), 0, 5, -1, -1, -1, -1, -1, 0, -1, 0}};
    if (local)
        types = {{wire(TypeKind::i64_type), 1, 1, 2, -1, -1, 1, 3}};
    count = static_cast<std::int64_t>(records.size());
    typeCount = static_cast<std::int64_t>(types.size());
    statementCount = static_cast<std::int64_t>(statements.size());
    result = {wire(Status::success),
              statementCount - 1,
              count,
              static_cast<std::int64_t>(tokens.size()) - 1,
              static_cast<std::int64_t>(tokens.back().span.begin.offset)};
}
void declarationTypeControls() {
    const std::string source = "Box<i64>> name;";
    const auto configure = [&] {
        reset();
        records.clear();
        count = 0;
        types = {{wire(TypeKind::i64_type), 2, 2, 4, -1, -1, -1, 0}, {wire(TypeKind::named), 0, 0, 6, 0, -1, 0, 3}};
        typeCount = 2;
        result = {wire(Status::success), 1, 0, 3, 8};
    };
    const auto unchanged = [](const Tokens &before, const Tokens &after) {
        if (before.size() != after.size())
            return false;
        for (std::size_t index = 0; index < before.size(); ++index)
            if (before[index].text != after[index].text || before[index].line != after[index].line ||
                before[index].span.source != after[index].span.source ||
                before[index].span.begin.offset != after[index].span.begin.offset ||
                before[index].span.begin.line != after[index].span.begin.line ||
                before[index].span.begin.column != after[index].span.begin.column ||
                before[index].span.end.offset != after[index].span.end.offset ||
                before[index].span.end.line != after[index].span.end.line ||
                before[index].span.end.column != after[index].span.end.column)
                return false;
        return true;
    };
    configure();
    auto tokens = aurora::lex(source, "type.au");
    const auto original = tokens;
    std::size_t position = 0;
    const auto value = aurora::parseHostedType(tokens, position);
    require(value.isClass() && value.className == "Box" && value.templateArguments.size() == 1 &&
                value.templateArguments[0].type == aurora::TypeKind::I64 && position == 3 && tokens[3].text == ">" &&
                tokens[3].span.begin.offset == 8 && tokens[3].span.begin.column == 9 &&
                tokens[3].span.source->text == source && read == 0 && edgeRead == 0 && statementRead == 0 &&
                typeRead == 2 && created == 1 && parsed == 1 && released == 1 &&
                capturedInput[10] == static_cast<std::uint64_t>(Stop::type),
            "declaration type lost copied conversion, residual cursor or cleanup");
    tokens[3] = original[3];
    require(unchanged(original, tokens), "type conversion modified another caller token");
    ++cases;
    const auto reject = [&](const std::string &label, const std::function<void()> &mutate, bool readFailure = false) {
        configure();
        mutate();
        auto input = aurora::lex(source, "bad-type.au");
        const auto before = input;
        std::size_t cursor = 0;
        bool rejected = false;
        try {
            static_cast<void>(aurora::parseHostedType(input, cursor));
        } catch (const aurora::Error &error) {
            rejected = !readFailure && error.diagnostic.code == DiagnosticCode::Internal;
        } catch (const std::runtime_error &error) {
            rejected = readFailure && std::string(error.what()) == "injected read failure";
        }
        require(rejected && cursor == 0 && unchanged(before, input) && input.front().span.source->text == source &&
                    created == 1 && parsed == 1 && released == 1,
                label + ": unsafe type representation escaped or published caller state");
        ++cases;
    };
    reject("missing type root", [] {
        result[1] = -1;
    });
    reject("wrong type root", [] {
        result[1] = 0;
    });
    reject("negative type count", [] {
        typeCount = -1;
    });
    reject("oversized type count", [] {
        typeCount = result[3] + 2;
    });
    reject("expression in type result", [] {
        result[2] = count = 1;
    });
    reject("statement in type result", [] {
        statementCount = 1;
    });
    reject("edge in type result", [] {
        edgeCount = 1;
    });
    reject("unknown type tag", [] {
        types[1][0] = 99;
    });
    reject("forward type child", [] {
        types[0][4] = 1;
    });
    reject("shared type child", [] {
        types[1][5] = 0;
    });
    reject("orphan type child", [] {
        types[1][4] = -1;
    });
    reject("missing root owner", [] {
        types[1][6] = -1;
        types[1][7] = 0;
    });
    reject("wrong root role", [] {
        types[1][7] = 2;
    });
    reject("out-of-range type token", [] {
        types[1][1] = 4;
    });
    reject("out-of-range type close", [] {
        types[1][3] = 8;
    });
    reject("invalid residual offset", [] {
        result[4] = 9;
    });
    reject(
        "type read exception",
        [] {
            throwingRead = 3;
        },
        true);
}
void bodyControls() {
    reset();
    records.clear();
    count = 0;
    statements = {{wire(StatementKind::block), 0, 2, -1, -1, -1, -1, -1, -1, -1, 0}};
    statementCount = 1;
    result = {wire(Status::success), 0, 0, 2, 2};
    auto tokens = aurora::lex("{}", "empty.au");
    std::size_t position = 0;
    require(aurora::parseHostedBody(tokens, position).empty() && position == 2 && read == 0 && statementRead == 1 &&
                released == 1,
            "empty body lost zero-node conversion or cleanup");
    ++cases;
    reset();
    bodyFixture(true);
    tokens = aurora::lex("{i64 x=1;return x;}", "local.au");
    position = 0;
    const auto body = aurora::parseHostedBody(tokens, position);
    require(body.size() == 2 && body[0]->kind == "let" && body[0]->name == "x" && body[0]->mutableValue &&
                body[0]->type == aurora::Type::I64 &&
                body[0]->bindingSpan.begin.offset == tokens[2].span.begin.offset && body[0]->expr->token.text == "1" &&
                body[1]->kind == "return" && body[1]->expr->token.text == "x" && position == 10 && read == 2 &&
                typeRead == 1 && statementRead == 3 && released == 1,
            "local body conversion lost field order, type, binding, cursor or cleanup");
    ++cases;
    // Root block location is bounded metadata, not an independent grammar or
    // whole-source-coverage claim. The caller cursor comes from ParseResult.
    reset();
    bodyFixture();
    statements.back()[1] = 1;
    statements.back()[2] = 4;
    tokens = aurora::lex("{return 1;}", "root-metadata.au");
    position = 0;
    require(aurora::parseHostedBody(tokens, position).size() == 1 && position == 5 && released == 1,
            "body converter replayed root token coverage");
    ++cases;
    const auto reject = [&](const std::string &label, const std::function<void()> &mutate, bool local = false) {
        reset();
        bodyFixture(local);
        mutate();
        const auto input = aurora::lex(local ? "{i64 x=1;return x;}" : "{return 1;}", "bad-body.au");
        std::size_t cursor = 0;
        bool rejected = false;
        try {
            static_cast<void>(aurora::parseHostedBody(input, cursor));
        } catch (const aurora::Error &error) {
            rejected = error.diagnostic.code == DiagnosticCode::Internal;
        }
        require(rejected && cursor == 0 && created == 1 && parsed == 1 && released == 1,
                label + ": unsafe body representation escaped or committed cursor");
        ++cases;
    };
    reject("negative statement count", [] {
        statementCount = -1;
    });
    reject("oversized statement count", [] {
        statementCount = result[3] + 1;
    });
    reject("missing root", [] {
        result[1] = -1;
    });
    reject("wrong root", [] {
        result[1] = 0;
    });
    reject("unknown statement tag", [] {
        statements[0][0] = 99;
    });
    reject("missing statement token", [] {
        statements[0][1] = -1;
    });
    reject("statement end out of range", [] {
        statements[0][2] = result[3] + 1;
    });
    reject("self sibling", [] {
        statements[0][3] = 0;
    });
    reject("forward child", [] {
        statements[1][8] = 1;
    });
    reject("orphan statement", [] {
        statements[1][8] = -1;
    });
    reject("missing expression", [] {
        statements[0][4] = -1;
    });
    reject("expression outside forest", [] {
        statements[0][4] = count;
    });
    reject("unexpected target", [] {
        statements[0][5] = 0;
    });
    reject("missing assignment target", [] {
        statements[0][0] = wire(StatementKind::assign);
    });
    reject("root carries expression", [] {
        statements[1][4] = 0;
    });
    reject("unexpected branch", [] {
        statements[1][9] = 0;
    });
    reject(
        "invalid mutable bit",
        [] {
            statements[0][10] = 2;
        },
        true);
    reject(
        "missing local type",
        [] {
            statements[0][6] = -1;
        },
        true);
    reject(
        "local type outside forest",
        [] {
            statements[0][6] = typeCount;
        },
        true);
    reject(
        "local binding outside input",
        [] {
            statements[0][7] = result[3];
        },
        true);
    reject(
        "shared expression root",
        [] {
            statements[1][4] = 0;
        },
        true);
    reject(
        "wrong local type role",
        [] {
            types[0][7] = 2;
        },
        true);
    reject(
        "wrong local type owner",
        [] {
            types[0][6] = 0;
        },
        true);
    reject("duplicate branch owner", [] {
        statements = {{wire(StatementKind::block), 1, 2, -1, -1, -1, -1, -1, -1, -1, 0},
                      {wire(StatementKind::conditional), 1, 4, -1, 0, -1, -1, -1, 0, 0, 0},
                      {wire(StatementKind::block), 0, 5, -1, -1, -1, -1, -1, 1, -1, 0}};
        statementCount = 3;
        result[1] = 2;
    });
    for (const int depth : {128, 129}) {
        reset();
        const std::string source = std::string(depth, '{') + std::string(depth, '}');
        tokens = aurora::lex(source, "body-depth.au");
        records.clear();
        count = 0;
        for (int index = 0; index < depth; ++index)
            statements.push_back({wire(StatementKind::block), 0, depth * 2, -1, -1, -1, -1, -1, index - 1, -1, 0});
        statementCount = depth;
        result = {wire(Status::success), depth - 1, 0, depth * 2, depth * 2};
        position = 0;
        bool rejected = false;
        try {
            static_cast<void>(aurora::parseHostedBody(tokens, position));
        } catch (const aurora::Error &error) {
            rejected = error.diagnostic.code == DiagnosticCode::Internal;
        }
        require(rejected == (depth == 129) && position == (depth == 129 ? 0U : static_cast<std::size_t>(depth * 2)) &&
                    released == 1,
                "body construction depth or cleanup changed");
        ++cases;
    }
    invalid("statement records in expression profile", [] {
        statementCount = 1;
    });
    reset();
    bodyFixture();
    throwingRead = 4;
    tokens = aurora::lex("{return 1;}", "throw-body.au");
    position = 0;
    bool threw = false;
    try {
        static_cast<void>(aurora::parseHostedBody(tokens, position));
    } catch (const std::runtime_error &error) {
        threw = std::string(error.what()) == "injected read failure";
    }
    require(threw && position == 0 && released == 1, "statement read exception leaked arena or committed cursor");
    ++cases;
}
void cleanupControls() {
    for (int control = 1; control <= 3; ++control) {
        reset();
        const std::string source = control == 3 ? "size_of(i64);" : "f(1,2);";
        if (control == 3)
            reflectedFixture();
        else
            callFixture();
        throwingRead = control;
        const auto tokens = aurora::lex(source, "throw.au");
        std::size_t position = 0;
        bool threw = false;
        try {
            static_cast<void>(aurora::parseHostedExpression(tokens, position, Stop::semicolon));
        } catch (const std::runtime_error &error) {
            threw = std::string(error.what()) == "injected read failure";
        }
        require(threw && position == 0 && released == 1, "read exception leaked arena or committed cursor");
        ++cases;
    }
}
} // namespace
extern "C" void aurora_hosted_parser_create(const void *input, void *output) {
    const auto &value = *static_cast<const aurora::hosted_abi::ParserCreate *>(input);
    require(value.region != 0 && value.capacity == 0, "adapter did not request empty arena with live region");
    arenaAddress = output;
    arenaRegion = value.region;
    // Exercise the generated arena's last word and the enclosing owner base.
    static_assert(aurora::hosted_abi::arenaBytes >= sizeof(arenaCanary));
    std::memcpy(static_cast<unsigned char *>(output) + aurora::hosted_abi::arenaBytes - sizeof(arenaCanary),
                &arenaCanary,
                sizeof(arenaCanary));
    ++created;
}
extern "C" void aurora_hosted_parser_parse(void *arena, const void *input, void *output) {
    require(arena == arenaAddress, "parse changed the arena address");
    std::memcpy(capturedInput.data(), input, sizeof(capturedInput));
    require(capturedInput[0] == 0 && capturedInput[2] == 0 && capturedInput[3] == 0 && capturedInput[4] == 0 &&
                capturedInput[5] == 0,
            "copied Input144 changed the borrowed source descriptor");
    ++parsed;
    std::memcpy(output, result.data(), sizeof(result));
}
extern "C" std::int64_t aurora_hosted_parser_count(const void *) {
    return count;
}
extern "C" void aurora_hosted_parser_read(const void *, std::int64_t index, void *output) {
    if (throwingRead == 1)
        throw std::runtime_error("injected read failure");
    require(index >= 0 && static_cast<std::size_t>(index) < records.size(), "adapter requested out-of-range node");
    ++read;
    std::memcpy(output, records[static_cast<std::size_t>(index)].data(), sizeof(NodeWords));
}
extern "C" std::int64_t aurora_hosted_parser_edges(const void *) {
    return edgeCount;
}
extern "C" void aurora_hosted_parser_edge(const void *, std::int64_t index, void *output) {
    if (throwingRead == 2)
        throw std::runtime_error("injected read failure");
    require(index >= 0 && static_cast<std::size_t>(index) < edges.size(), "adapter requested out-of-range edge");
    ++edgeRead;
    std::memcpy(output, edges[static_cast<std::size_t>(index)].data(), sizeof(EdgeWords));
}
extern "C" std::int64_t aurora_hosted_parser_types(const void *) {
    return typeCount;
}
extern "C" void aurora_hosted_parser_type(const void *, std::int64_t index, void *output) {
    if (throwingRead == 3)
        throw std::runtime_error("injected read failure");
    require(index >= 0 && static_cast<std::size_t>(index) < types.size(), "adapter requested out-of-range type");
    ++typeRead;
    std::memcpy(output, types[static_cast<std::size_t>(index)].data(), sizeof(TypeWords));
}
extern "C" std::int64_t aurora_hosted_parser_statements(const void *) {
    return statementCount;
}
extern "C" void aurora_hosted_parser_statement(const void *, std::int64_t index, void *output) {
    if (throwingRead == 4)
        throw std::runtime_error("injected read failure");
    require(index >= 0 && static_cast<std::size_t>(index) < statements.size(),
            "adapter requested out-of-range statement");
    ++statementRead;
    std::memcpy(output, statements[static_cast<std::size_t>(index)].data(), sizeof(StatementWords));
}
extern "C" void aurora_hosted_parser_release(void *owner) {
    const auto &record = *static_cast<const aurora::hosted_abi::ParserRelease *>(owner);
    require(record.arena.storage.data() == arenaAddress, "release did not receive the enclosing owner");
    std::uint64_t canary = 0;
    std::memcpy(&canary, record.arena.storage.data() + record.arena.storage.size() - sizeof(canary), sizeof(canary));
    require(record.region == arenaRegion && canary == arenaCanary, "owner region or arena boundary was corrupted");
    ++released;
}

int main() {
    try {
        conversionControls();
        resultControls();
        graphControls();
        typeControls();
        depthControls();
        inputControls();
        cleanupControls();
        bodyControls();
        declarationTypeControls();
        diagnostic("f(",
                   Status::expected_expression,
                   2,
                   DiagnosticCode::UnexpectedToken,
                   "expected expression (found '<eof>')");
        diagnostic("1;", Status::allocation_failure, 0, DiagnosticCode::Internal, "hosted parser allocation failed");
        diagnostic(
            "1;", Status::nesting_limit, 0, DiagnosticCode::NestingLimit, "expression parser nesting exceeds 128");
        diagnostic("size_of(Box<i64>>);",
                   Status::expected_close,
                   5,
                   DiagnosticCode::UnexpectedToken,
                   "expected ')' (found '>')",
                   Stop::semicolon,
                   true);
        std::cout << "hosted parser representation controls: " << cases << " passed\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
