// Host-only representation controls. Aurora owns grammar; these stubs exercise
// safe copied-record conversion, bounded ownership, cleanup and cursor commits.
#include "hosted_graph.hpp"
#include "hosted_parser.hpp"
#include "hosted_resolver.hpp"
#include "lexer.hpp"
#include "services.hpp"
#include "../../runtime/bytes_abi.hpp"
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <functional>
#include <iostream>
#include <limits>
#include <optional>
#include <set>
#include <stdexcept>
#include <utility>
#include <vector>

namespace {
using ResultWords = std::array<std::int64_t, 6>;
using AdmissionWords = std::array<std::int64_t, 5>;
using AdmissionInputWords = std::array<std::uint64_t, 14>;
using NodeWords = std::array<std::int64_t, 7>;
using EdgeWords = std::array<std::int64_t, 5>;
using TypeWords = std::array<std::int64_t, 8>;
using SyntaxWords = std::array<std::int64_t, 12>;
using InputWords = std::array<std::uint64_t, 19>;
static_assert(sizeof(ResultWords) == sizeof(aurora::hosted_abi::compiler_parser::ParseResult) &&
              sizeof(NodeWords) == sizeof(aurora::hosted_abi::compiler_parser::AstNode) &&
              sizeof(EdgeWords) == sizeof(aurora::hosted_abi::compiler_parser::ChildEdge) &&
              sizeof(TypeWords) == sizeof(aurora::hosted_abi::compiler_parser::TypeSyntax) &&
              sizeof(SyntaxWords) == sizeof(aurora::hosted_abi::compiler_parser::SyntaxNode) &&
              sizeof(InputWords) == sizeof(aurora::hosted_abi::ParserInput));
static_assert(sizeof(ResultWords) == 48 && sizeof(SyntaxWords) == 96 && sizeof(InputWords) == 152);
static_assert(sizeof(AdmissionWords) == sizeof(aurora::hosted_abi::compiler_parser::AdmissionResult) &&
              sizeof(AdmissionInputWords) == sizeof(aurora::hosted_abi::AdmissionInput) &&
              sizeof(AdmissionWords) == 40 && sizeof(AdmissionInputWords) == 112);
static_assert(offsetof(aurora::hosted_abi::AdmissionInput, root) == 56 &&
              offsetof(aurora::hosted_abi::AdmissionInput, configuration) == 64);
static_assert(offsetof(aurora::hosted_abi::ParserInput, enum_count) == 144);
static_assert(offsetof(aurora::hosted_abi::compiler_parser::ParseResult, token_half) == 40 &&
              offsetof(aurora::hosted_abi::compiler_parser::SyntaxNode, borrow_token) == 88);
using aurora::DiagnosticCode;
using aurora::hosted_parser::AdmissionStatus;
using aurora::hosted_parser::NodeKind;
using aurora::hosted_parser::Status;
using aurora::hosted_parser::Stop;
using aurora::hosted_parser::SyntaxKind;
using aurora::hosted_parser::TypeKind;
template <class T> constexpr std::int64_t wire(T value) {
    return static_cast<std::int64_t>(value);
}
ResultWords result;
AdmissionWords admissionResult;
AdmissionInputWords capturedAdmissionInput{};
std::vector<NodeWords> records;
std::vector<EdgeWords> edges;
std::vector<TypeWords> types;
std::vector<SyntaxWords> statements;
InputWords capturedInput{};
void *arenaAddress = nullptr;
std::uint64_t arenaRegion = 0;
constexpr std::uint64_t arenaCanary = 0x746970656172656eULL;
std::int64_t count = 0, edgeCount = 0, typeCount = 0, statementCount = 0;
int created = 0, parsed = 0, admitted = 0, released = 0, read = 0, edgeRead = 0, typeRead = 0;
bool throwingAdmission = false;
int throwingRead = 0, statementRead = 0;
namespace Resolution = aurora::hosted_abi::compiler_resolver;
std::vector<Resolution::SyntaxRow> resolutionSyntax;
std::vector<Resolution::MetaRow> resolutionMetadata;
std::vector<Resolution::ResolvedRow> resolutionDecorations;
Resolution::SessionStatus resolutionStatus;
void *sessionAddress = nullptr;
std::uint64_t sessionRegion = 0;
// Charge copied fixture rows to the real host region so Projection's payload
// bound is exercised. This owner is the stub's own runtime allocation, never an
// interpretation or a copy of the generated opaque Session descriptor.
aurora::hosted::bytes::NativeOwner sessionPayload;
constexpr std::uint64_t sessionCanary = 0x7265736f6c766564ULL;
int sessionsCreated = 0, sessionsReleased = 0, transferred = 0, pairsReleased = 0, projectionThrow = 0;
bool resolverRunning = false, allocationOnIngest = false;
std::int64_t reportedSyntax = 0, reportedMetadata = 0, reportedDecorations = 0, sourceBytes = 0, seedIdentity = 0;
namespace Lowering = aurora::hosted_abi::compiler_lowering;
Lowering::LoweringResult loweringResult{};
Lowering::OutputRow loweringReport{};
std::array<Lowering::OperandRow, 3> loweringOperands{};
std::int64_t reportedOutputs = 1, reportedOperands = 3;
int loweringBegun = 0, loweringRun = 0, loweringOutputReads = 0, loweringOperandReads = 0;
int scalarSeeds = 0, serviceSeeds = 0;
bool loweringAllocation = false;
std::size_t cases = 0;
void require(bool value, const std::string &message) {
    if (!value)
        throw std::runtime_error(message);
}
void reset() {
    result = {wire(Status::success), 2, 3, 3, 3};
    admissionResult = {wire(AdmissionStatus::success), -1, -1, -1, 0};
    capturedAdmissionInput = {};
    throwingAdmission = false;
    records = {{wire(NodeKind::literal), 0, -1, -1, 1, 0, 0},
               {wire(NodeKind::literal), 2, -1, -1, 1, 2, 2},
               {wire(NodeKind::binary), 1, 0, 1, 2, 1, 1}};
    count = 3;
    edgeCount = typeCount = statementCount = 0;
    edges.clear();
    types.clear();
    statements.clear();
    created = parsed = admitted = released = read = edgeRead = typeRead = statementRead = throwingRead = 0;
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
bool unchanged(const Tokens &before, const Tokens &after) {
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
}
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
              static_cast<std::int64_t>(tokens[ordinal].span.begin.offset) + (secondHalf ? 1 : 0),
              secondHalf ? 1 : 0};
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
    for (const auto half : {-1LL, 1LL, 2LL, std::numeric_limits<long long>::max()})
        invalid("expression result half", [=] {
            result[5] = half;
        });
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
        local ? std::vector<SyntaxWords>{{wire(SyntaxKind::local), 1, 6, -1, 0, -1, 0, 2, -1, -1, 1, -1},
                                         {wire(SyntaxKind::return_value), 6, 9, 0, 1, -1, -1, -1, -1, -1, 0, -1},
                                         {wire(SyntaxKind::block), 0, 10, -1, -1, -1, -1, -1, 1, -1, 0, -1}}
              : std::vector<SyntaxWords>{{wire(SyntaxKind::return_value), 1, 4, -1, 0, -1, -1, -1, -1, -1, 0, -1},
                                         {wire(SyntaxKind::block), 0, 5, -1, -1, -1, -1, -1, 0, -1, 0, -1}};
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
        result = {wire(Status::success), 1, 0, 3, 8, 1};
    };
    configure();
    const auto tokens = aurora::lex(source, "type.au");
    const auto original = tokens;
    const aurora::hosted_parser::Cursor position{0, 0};
    const auto value = aurora::parseHostedType(tokens, position);
    require(value.type.isClass() && value.type.className == "Box" && value.type.templateArguments.size() == 1 &&
                value.type.templateArguments[0].type == aurora::TypeKind::I64 && value.next.ordinal == 3 &&
                value.next.half == 1 && position.ordinal == 0 && position.half == 0 && unchanged(original, tokens) &&
                tokens[3].text == ">>" && tokens[3].span.begin.offset == 7 && tokens[3].span.end.offset == 9 &&
                tokens[3].span.source->text == source && read == 0 && edgeRead == 0 && statementRead == 0 &&
                typeRead == 2 && created == 1 && parsed == 1 && released == 1 &&
                capturedInput[10] == static_cast<std::uint64_t>(Stop::type),
            "declaration type lost copied conversion, immutable half cursor or cleanup");
    ++cases;
    configure();
    const auto wholeTokens = aurora::lex("Box<i64> name;", "whole-type.au");
    const auto wholeOriginal = wholeTokens;
    result[3] = 4;
    result[4] = static_cast<std::int64_t>(wholeTokens[4].span.begin.offset);
    result[5] = 0;
    const auto whole = aurora::parseHostedType(wholeTokens, {0, 0});
    require(whole.next.ordinal == 4 && whole.next.half == 0 && unchanged(wholeOriginal, wholeTokens) && released == 1,
            "whole-token type cursor did not preserve its exact offset and immutable input");
    ++cases;
    const auto reject = [&](const std::string &label, const std::function<void()> &mutate, bool readFailure = false) {
        configure();
        mutate();
        auto input = aurora::lex(source, "bad-type.au");
        const auto before = input;
        const aurora::hosted_parser::Cursor cursor{0, 0};
        bool rejected = false;
        try {
            static_cast<void>(aurora::parseHostedType(input, cursor));
        } catch (const aurora::Error &error) {
            rejected = !readFailure && error.diagnostic.code == DiagnosticCode::Internal;
        } catch (const std::runtime_error &error) {
            rejected = readFailure && std::string(error.what()) == "injected read failure";
        }
        require(rejected && cursor.ordinal == 0 && cursor.half == 0 && unchanged(before, input) &&
                    input.front().span.source->text == source && created == 1 && parsed == 1 && released == 1,
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
    reject("half-zero residual offset", [] {
        result[5] = 0;
    });
    reject("half-one whole-token offset", [] {
        result[4] = 7;
    });
    for (const auto half : {-1LL, 2LL, std::numeric_limits<long long>::max()})
        reject("invalid residual half", [=] {
            result[5] = half;
        });
    reject(
        "type read exception",
        [] {
            throwingRead = 3;
        },
        true);
}
void continuationControls() {
    const auto tokens = aurora::lex("Box<i64>> name;", "continuation.au");
    const auto original = tokens;
    const aurora::hosted_parser::Cursor cursor{3, 1};
    // The scanner sees the residual byte as an ordinary > at entry. Its initial
    // half-zero result is normalized to the caller's original half-one token.
    for (const bool advance : {false, true}) {
        reset();
        records.clear();
        count = 0;
        const auto ordinal = advance ? 4U : 3U;
        const auto offset = tokens[ordinal].span.begin.offset + (advance ? 0U : 1U);
        result = {wire(Status::expected_type), -1, 0, advance ? 1 : 0, static_cast<std::int64_t>(offset), 0};
        bool rejected = false;
        try {
            static_cast<void>(aurora::parseHostedType(tokens, cursor));
        } catch (const aurora::Error &error) {
            const auto &span = error.diagnostic.span;
            const auto &expected = tokens[ordinal].span;
            rejected = error.diagnostic.code == DiagnosticCode::UnexpectedToken &&
                       error.diagnostic.message ==
                           (advance ? "expected type name (found 'name')" : "expected type name (found '>')") &&
                       span.source == expected.source && span.begin.offset == offset &&
                       span.begin.line == expected.begin.line &&
                       span.begin.column == expected.begin.column + (advance ? 0 : 1) &&
                       span.end.offset == expected.end.offset && span.end.line == expected.end.line &&
                       span.end.column == expected.end.column;
        }
        require(rejected && cursor.ordinal == 3 && cursor.half == 1 && unchanged(original, tokens) &&
                    capturedInput[7] == 8 && created == 1 && parsed == 1 && released == 1,
                "half-one continuation failure lost exact location, immutable caller state or cleanup");
        ++cases;
    }
    for (const aurora::hosted_parser::Cursor invalidCursor :
         {aurora::hosted_parser::Cursor{0, 1}, {3, 2}, {tokens.size(), 0}}) {
        reset();
        bool rejected = false;
        try {
            static_cast<void>(aurora::parseHostedType(tokens, invalidCursor));
        } catch (const aurora::Error &error) {
            rejected = error.diagnostic.code == DiagnosticCode::Internal;
        }
        require(rejected && unchanged(original, tokens) && created == 0 && parsed == 0 && released == 0,
                "invalid input cursor crossed the arena boundary or changed caller tokens");
        ++cases;
    }
}
void fieldControls() {
    const auto tokens = aurora::lex("Box<i64> value;", "field-record.au");
    const auto original = tokens;
    const aurora::hosted_parser::Cursor cursor{0, 0};
    const auto configure = [&] {
        reset();
        records.clear();
        count = 0;
        types = {{wire(TypeKind::i64_type), 2, 2, 4, -1, -1, -1, 0}, {wire(TypeKind::named), 0, 0, 6, 0, -1, 0, 3}};
        typeCount = 2;
        statements = {{wire(SyntaxKind::field), 0, 6, -1, -1, -1, 1, 4, -1, -1, 0, -1}};
        statementCount = 1;
        result = {wire(Status::success), 0, 0, 6, static_cast<std::int64_t>(tokens.back().span.begin.offset), 0};
    };
    configure();
    const auto value = aurora::parseHostedField(tokens, cursor);
    require(value.field.token.text == "value" && value.field.type.className == "Box" &&
                value.field.type.templateArguments.size() == 1 &&
                value.field.type.templateArguments[0].type == aurora::TypeKind::I64 && value.next.ordinal == 6 &&
                value.next.half == 0 && cursor.ordinal == 0 && cursor.half == 0 && unchanged(original, tokens) &&
                read == 0 && edgeRead == 0 && typeRead == 2 && statementRead == 1 &&
                capturedInput[10] == static_cast<std::uint64_t>(Stop::field) && admitted == 0 && released == 1,
            "whole field conversion lost its owned type, cursor or cleanup");
    ++cases;
    const auto reject = [&](const std::string &label, const std::function<void()> &mutate, bool readFailure = false) {
        configure();
        mutate();
        bool rejected = false;
        try {
            static_cast<void>(aurora::parseHostedField(tokens, cursor));
        } catch (const aurora::Error &error) {
            rejected = !readFailure && error.diagnostic.code == DiagnosticCode::Internal;
        } catch (const std::runtime_error &error) {
            rejected = readFailure && std::string(error.what()) == "injected read failure";
        }
        require(rejected && cursor.ordinal == 0 && cursor.half == 0 && unchanged(original, tokens) && created == 1 &&
                    parsed == 1 && released == 1,
                label + ": invalid field escaped or changed caller state/cleanup");
        ++cases;
    };
    reject("wrong field root", [] {
        result[1] = -1;
    });
    reject("wrong field tag", [] {
        statements[0][0] = wire(SyntaxKind::local);
    });
    reject("field type index", [] {
        statements[0][6] = typeCount;
    });
    reject("field binding index", [] {
        statements[0][7] = result[3];
    });
    reject("field end cursor", [] {
        statements[0][2] = result[3] + 1;
    });
    reject("field type owner", [] {
        types[1][6] = 4;
    });
    reject("field type role", [] {
        types[1][7] = 2;
    });
    reject("orphan field type", [] {
        statements[0][6] = 0;
    });
    reject("shared field type child", [] {
        types[1][5] = 0;
    });
    for (const auto slot : {3U, 4U, 5U, 8U, 9U, 11U})
        reject("unexpected field child or borrow", [=] {
            statements[0][slot] = 0;
        });
    reject("field qualifier", [] {
        statements[0][10] = 1;
    });
    reject("field residual half", [] {
        result[5] = 1;
    });
    reject("orphan field syntax", [] {
        statements.push_back(statements.front());
        statementCount = 2;
        result[1] = 1;
    });
    reject(
        "field read exception",
        [] {
            throwingRead = 4;
        },
        true);
}
void preambleEnumControls() {
    for (const auto stop : {Stop::preamble, Stop::enum_definition}) {
        const bool preamble = stop == Stop::preamble;
        const auto tokens = aurora::lex(preamble ? "prefix;export module one.two;import alpha.beta;import gamma;next"
                                                 : "prefix;enum class E{first,second};next",
                                        "record.au");
        const auto original = tokens;
        const aurora::hosted_parser::Cursor cursor{2};
        const std::int64_t end = preamble ? 14 : 9;
        const auto configure = [&] {
            reset();
            records.clear();
            count = 0;
            statements = preamble ? std::vector<SyntaxWords>{{18, 7, 10, -1, -1, -1, -1, -1, -1, -1, 0, -1},
                                                             {18, 12, 13, 0, -1, -1, -1, -1, -1, -1, 0, -1},
                                                             {17, 2, 14, -1, -1, -1, -1, 4, 1, -1, 1, -1}}
                                  : std::vector<SyntaxWords>{{20, 4, 5, -1, -1, -1, -1, -1, -1, -1, 0, -1},
                                                             {20, 6, 7, 0, -1, -1, -1, -1, -1, -1, 0, -1},
                                                             {19, 2, 9, -1, -1, -1, -1, -1, 1, -1, 0, -1}};
            statementCount = 3;
            result = {wire(Status::success),
                      2,
                      0,
                      end,
                      static_cast<std::int64_t>(tokens.at(cursor.ordinal + end).span.begin.offset),
                      0};
        };
        configure();
        if (preamble) {
            const auto value = aurora::parseHostedPreamble(tokens, cursor);
            require(value.program.moduleName == "one.two" && value.program.interfaceUnit &&
                        value.program.imports.size() == 2 && value.program.imports[0].text == "alpha.beta" &&
                        value.program.imports[1].text == "gamma" &&
                        value.program.imports[0].span.begin.offset == tokens[9].span.begin.offset &&
                        value.program.imports[0].span.end.offset == tokens[11].span.end.offset &&
                        value.program.imports[1].span.begin.offset == tokens[14].span.begin.offset &&
                        value.program.imports[1].span.end.offset == tokens[14].span.end.offset &&
                        value.next.ordinal == cursor.ordinal + end && value.next.half == 0,
                    "preamble conversion lost source ranges, import order or cursor");
        } else {
            const auto value = aurora::parseHostedEnum(tokens, cursor, 63);
            require(value.definition.name == "E" && value.definition.scope.empty() && !value.definition.exported &&
                        value.definition.cases.size() == 2 && value.definition.cases[0].text == "first" &&
                        value.definition.cases[1].text == "second" &&
                        value.definition.token.span.begin.offset == tokens[4].span.begin.offset &&
                        value.definition.cases[0].span.begin.offset == tokens[6].span.begin.offset &&
                        value.definition.cases[1].span.end.offset == tokens[8].span.end.offset &&
                        value.next.ordinal == cursor.ordinal + end && value.next.half == 0,
                    "enum conversion lost source ranges, case order or cursor");
        }
        require(cursor.ordinal == 2 && cursor.half == 0 && unchanged(original, tokens) && created == 1 && parsed == 1 &&
                    released == 1 && read == 0 && edgeRead == 0 && typeRead == 0 && statementRead == 3 &&
                    capturedInput[10] == static_cast<std::uint64_t>(stop) && capturedInput[18] == (preamble ? 0U : 63U),
                "preamble/enum conversion changed immutable input, explicit count or exact owner cleanup");
        ++cases;
        const auto reject = [&](const char *label, const std::function<void()> &mutate, bool readFailure = false) {
            configure();
            mutate();
            bool rejected = false;
            try {
                if (preamble)
                    static_cast<void>(aurora::parseHostedPreamble(tokens, cursor));
                else
                    static_cast<void>(aurora::parseHostedEnum(tokens, cursor, 63));
            } catch (const aurora::Error &error) {
                rejected = !readFailure && error.diagnostic.code == DiagnosticCode::Internal;
            } catch (const std::runtime_error &error) {
                rejected = readFailure && std::string(error.what()) == "injected read failure";
            }
            require(rejected && cursor.ordinal == 2 && cursor.half == 0 && unchanged(original, tokens) &&
                        created == 1 && parsed == 1 && released == 1,
                    std::string(label) + ": invalid preamble/enum representation escaped or changed owner cleanup");
            ++cases;
        };
        reject("cyclic list link", [] {
            statements[0][3] = 0;
        });
        reject("orphan list record", [] {
            statements[2][8] = 0;
        });
        reject("out-of-range name index", [] {
            statements[1][1] = result[3];
        });
        if (preamble) {
            reject("empty name range", [] {
                statements[0][2] = statements[0][1];
            });
            reject("invalid interface flag", [] {
                statements[2][10] = 2;
            });
        }
        reject("wrong root tag", [] {
            statements[2][0] = wire(SyntaxKind::field);
        });
        reject(
            "syntax read exception",
            [] {
                throwingRead = 4;
            },
            true);
    }
    for (const auto count : {std::size_t{65}, std::numeric_limits<std::size_t>::max()}) {
        reset();
        const auto tokens = aurora::lex("enum class E{one};", "invalid-count.au"), original = tokens;
        bool rejected = false;
        try {
            static_cast<void>(aurora::parseHostedEnum(tokens, {}, count));
        } catch (const aurora::Error &error) {
            rejected = error.diagnostic.code == DiagnosticCode::Internal;
        }
        require(rejected && unchanged(original, tokens) && created == 0 && parsed == 0 && released == 0,
                "unrepresentable enum count crossed the arena boundary");
        ++cases;
    }
}

void moduleControls() {
    const auto tokens =
        aurora::lex("export module m;namespace n{template<Scalar T,i64 N>class C{T value;};}", "module-record.au");
    const auto original = tokens;
    const auto configure = [&] {
        reset();
        records.clear();
        count = 0;
        types = {{wire(TypeKind::parameter), 18, 18, 36, -1, -1, 18, 3}};
        typeCount = 1;
        statements = {{17, 2, 4, -1, -1, -1, -1, 2, -1, -1, 1, -1},
                      {25, 10, 11, -1, -1, -1, -1, -1, -1, -1, 0, -1},
                      {27, 13, 14, 1, -1, -1, -1, -1, -1, -1, 0, -1},
                      {16, 18, 21, -1, -1, -1, 0, 19, -1, -1, 0, -1},
                      {24, 18, 21, -1, -1, -1, -1, -1, 3, -1, 0, -1},
                      {23, 16, 23, -1, -1, -1, -1, -1, 4, -1, 0, -1},
                      {24, 16, 23, -1, -1, -1, -1, -1, 5, 2, 0, -1},
                      {22, 5, 24, -1, -1, -1, -1, 5, 6, -1, 0, -1},
                      {24, 5, 24, -1, -1, -1, -1, -1, 7, -1, 0, -1},
                      {21, 0, 24, -1, -1, -1, -1, -1, 0, 8, 0, -1}};
        statementCount = static_cast<std::int64_t>(statements.size());
        result = {wire(Status::success), 9, 0, 24, static_cast<std::int64_t>(tokens.back().span.begin.offset), 0};
    };
    configure();
    const auto program = aurora::parseHostedProgram(tokens);
    require(program.moduleName == "m" && program.interfaceUnit && program.namespaces == std::set<std::string>{"n"} &&
                program.classes.empty() && program.templates.size() == 1 && program.templates[0].name == "C" &&
                program.templates[0].scope == "n" && !program.templates[0].exported &&
                program.templates[0].fields.size() == 1 && program.templates[0].fields[0].token.text == "value" &&
                program.templates[0].fields[0].type.kind == aurora::TypeKind::Parameter &&
                program.templates[0].fields[0].type.className == "T" &&
                program.templates[0].templateParameters.size() == 2 &&
                program.templates[0].templateParameters[0].kind == aurora::TemplateParameterKind::Scalar &&
                program.templates[0].templateParameters[0].name == "T" &&
                program.templates[0].templateParameters[1].kind == aurora::TemplateParameterKind::Capacity &&
                program.templates[0].templateParameters[1].name == "N" &&
                program.templates[0].token.span.begin.offset == tokens[16].span.begin.offset &&
                program.templates[0].fields[0].token.span.begin.offset == tokens[19].span.begin.offset,
            "whole-module copied conversion lost container/template/member metadata");
    require(unchanged(original, tokens) && created == 1 && parsed == 1 && admitted == 1 && released == 1 && read == 0 &&
                edgeRead == 0 && typeRead == 1 && statementRead == 10 &&
                capturedInput[10] == static_cast<std::uint64_t>(Stop::module_definition) &&
                std::all_of(capturedInput.begin() + 11,
                            capturedInput.end(),
                            [](auto value) {
                                return value == 0;
                            }),
            "whole-module conversion did not use one empty-context call and exact owner cleanup");
    ++cases;
    const auto reject = [&](const char *label, const std::function<void()> &mutate, bool readFailure = false) {
        configure();
        mutate();
        bool rejected = false;
        try {
            static_cast<void>(aurora::parseHostedProgram(tokens));
        } catch (const aurora::Error &error) {
            rejected = !readFailure && error.diagnostic.code == DiagnosticCode::Internal;
        } catch (const std::runtime_error &error) {
            rejected = readFailure && std::string(error.what()) == "injected read failure";
        }
        require(rejected && unchanged(original, tokens) && created == 1 && parsed == 1 && released == 1,
                std::string(label) + ": malformed module forest escaped or changed input/cleanup");
        ++cases;
    };
    reject("unknown container tag", [] {
        statements[5][0] = wire(SyntaxKind::template_capacity) + 1;
    });
    reject("wrong module root tag", [] {
        statements[9][0] = wire(SyntaxKind::declaration);
    });
    reject("module root outside forest", [] {
        result[1] = statementCount;
    });
    reject("module residual half", [] {
        result[5] = 1;
    });
    reject("module missing preamble", [] {
        statements[9][8] = -1;
    });
    reject("wrong preamble family", [] {
        statements[9][8] = 7;
    });
    reject("orphan declaration list", [] {
        statements[9][9] = -1;
    });
    reject("forward container ownership", [] {
        statements[5][8] = 6;
    });
    reject("namespace binding outside tokens", [] {
        statements[7][7] = result[3];
    });
    reject("namespace reversed name interval", [] {
        statements[7][7] = 4;
    });
    reject("class token outside tokens", [] {
        statements[5][1] = result[3];
    });
    reject("container end outside tokens", [] {
        statements[5][2] = result[3] + 1;
    });
    reject("wrapper missing declaration", [] {
        statements[6][8] = -1;
    });
    reject("wrapper owns wrong leaf family", [] {
        statements[6][8] = 2;
    });
    reject("member list wrong family", [] {
        statements[5][8] = 3;
    });
    reject("class orphan member", [] {
        statements[5][8] = -1;
    });
    reject("duplicate declaration owner", [] {
        statements[8][8] = 5;
    });
    reject("wrapper list self cycle", [] {
        statements[4][3] = 4;
    });
    reject("template list self cycle", [] {
        statements[1][3] = 1;
    });
    reject("template list wrong family", [] {
        statements[6][9] = 4;
    });
    reject("shared template chain", [] {
        statements[8][9] = 2;
    });
    reject("orphan template parameter", [] {
        statements[6][9] = 1;
    });
    reject("invalid wrapper qualifier", [] {
        statements[6][10] = 2;
    });
    reject("field type outside forest", [] {
        statements[3][6] = typeCount;
    });
    reject(
        "syntax read exception",
        [] {
            throwingRead = 4;
        },
        true);
    // Admission is a private post-grammar result, with no policy replay here.
    // Every malformed tag/range/detail must fail before a Program is published.
    for (const auto &[label, forged] : std::vector<std::pair<const char *, AdmissionWords>>{
             {"negative admission status", {-1, -1, -1, -1, 0}},
             {"invalid admission status", {wire(AdmissionStatus::invalid), -1, -1, -1, 0}},
             {"unknown admission status", {99, -1, -1, -1, 0}},
             {"success has token", {wire(AdmissionStatus::success), 0, -1, -1, 0}},
             {"success has end", {wire(AdmissionStatus::success), -1, 0, -1, 0}},
             {"success has type", {wire(AdmissionStatus::success), -1, -1, 0, 0}},
             {"success has detail", {wire(AdmissionStatus::success), -1, -1, -1, 1}},
             {"failure has metadata", {wire(AdmissionStatus::allocation_failure), 0, -1, -1, 0}},
             {"negative admission token", {wire(AdmissionStatus::public_array), -1, 1, -1, 0}},
             {"admission token outside input", {wire(AdmissionStatus::public_array), 25, 26, -1, 0}},
             {"admission end outside input", {wire(AdmissionStatus::public_array), 24, 26, -1, 0}},
             {"reversed admission range", {wire(AdmissionStatus::public_array), 20, 19, -1, 0}},
             {"ordinary admission spans multiple tokens", {wire(AdmissionStatus::public_array), 19, 21, -1, 0}},
             {"ordinary admission carries type", {wire(AdmissionStatus::public_array), 20, 21, 0, 0}},
             {"ordinary admission carries detail", {wire(AdmissionStatus::public_array), 20, 21, -1, 1}},
             {"unsupported field lacks type", {wire(AdmissionStatus::unsupported_field), 18, 19, -1, 0}},
             {"unsupported field type outside forest", {wire(AdmissionStatus::unsupported_field), 18, 19, 1, 0}},
             {"unsupported field carries detail", {wire(AdmissionStatus::unsupported_field), 18, 19, 0, 1}},
             {"array limit outside configuration", {wire(AdmissionStatus::array_capacity), 20, 21, -1, 65}}}) {
        configure();
        admissionResult = forged;
        bool rejected = false;
        try {
            static_cast<void>(aurora::parseHostedProgram(tokens));
        } catch (const aurora::Error &error) {
            rejected = error.diagnostic.code == DiagnosticCode::Internal &&
                       error.diagnostic.message == "hosted parser returned an invalid result";
        }
        require(rejected && unchanged(original, tokens) && created == 1 && parsed == 1 && admitted == 1 &&
                    released == 1,
                std::string(label) + ": unsafe admission result escaped or changed input/cleanup");
        ++cases;
    }
    for (const bool throws : {false, true}) {
        configure();
        throwingAdmission = throws;
        admissionResult = {wire(AdmissionStatus::allocation_failure), -1, -1, -1, 0};
        bool rejected = false;
        try {
            static_cast<void>(aurora::parseHostedProgram(tokens));
        } catch (const aurora::Error &error) {
            rejected = !throws && error.diagnostic.code == DiagnosticCode::Internal &&
                       error.diagnostic.message == "hosted declaration admission allocation failed";
        } catch (const std::runtime_error &error) {
            rejected = throws && std::string(error.what()) == "injected admission failure";
        }
        require(rejected && unchanged(original, tokens) && created == 1 && parsed == 1 && admitted == 1 &&
                    released == 1,
                "admission allocation/bridge failure leaked the existing arena or published a program");
        ++cases;
    }
    // This copied forest checks the independent host construction bound, not
    // namespace grammar acceptance. All links are backward and singly owned.
    for (const int depth : {63, 64}) {
        reset();
        std::string source = "export module deep;";
        for (int level = 0; level < depth; ++level)
            source += "namespace n{";
        source += "auto f()->i64{}" + std::string(depth, '}');
        const auto input = aurora::lex(source, "module-construction-depth.au"), before = input;
        const std::int64_t start = 4 + 3 * depth, end = 12 + 4 * depth;
        records.clear();
        count = 0;
        types = {{wire(TypeKind::i64_type), start + 5, start + 5, 2 * (start + 5), -1, -1, start + 1, 3}};
        typeCount = 1;
        statements = {{17, 2, 4, -1, -1, -1, -1, 2, -1, -1, 1, -1},
                      {1, start + 6, start + 8, -1, -1, -1, -1, -1, -1, -1, 0, -1},
                      {13, start + 1, start + 8, -1, -1, -1, 0, -1, 1, -1, 0, -1},
                      {24, start + 1, start + 8, -1, -1, -1, -1, -1, 2, -1, 0, -1}};
        std::int64_t tail = 3;
        for (int level = depth - 1; level >= 0; --level) {
            const std::int64_t name = 5 + 3 * level, close = start + 8 + depth - level;
            statements.push_back({22, name, close, -1, -1, -1, -1, name, tail, -1, 0, -1});
            statements.push_back({24, name, close, -1, -1, -1, -1, -1, tail + 1, -1, 0, -1});
            tail += 2;
        }
        statements.push_back({21, 0, end, -1, -1, -1, -1, -1, 0, tail, 0, -1});
        statementCount = static_cast<std::int64_t>(statements.size());
        result = {wire(Status::success),
                  statementCount - 1,
                  0,
                  end,
                  static_cast<std::int64_t>(input.back().span.begin.offset),
                  0};
        bool rejected = false;
        try {
            const auto value = aurora::parseHostedProgram(input);
            require(value.functions.size() == 1 && value.namespaces.size() == static_cast<std::size_t>(depth),
                    "bounded module construction lost a container or callable");
        } catch (const aurora::Error &error) {
            rejected = error.diagnostic.code == DiagnosticCode::Internal;
        }
        require(rejected == (depth == 64) && unchanged(before, input) && created == 1 && parsed == 1 && released == 1,
                "independent module construction depth did not bound conversion and preserve cleanup");
        ++cases;
    }
}

void bodyControls() {
    reset();
    records.clear();
    count = 0;
    statements = {{wire(SyntaxKind::block), 0, 2, -1, -1, -1, -1, -1, -1, -1, 0, -1}};
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
        statements[0][0] = wire(SyntaxKind::assign);
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
        statements = {{wire(SyntaxKind::block), 1, 2, -1, -1, -1, -1, -1, -1, -1, 0, -1},
                      {wire(SyntaxKind::conditional), 1, 4, -1, 0, -1, -1, -1, 0, 0, 0, -1},
                      {wire(SyntaxKind::block), 0, 5, -1, -1, -1, -1, -1, 1, -1, 0, -1}};
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
            statements.push_back({wire(SyntaxKind::block), 0, depth * 2, -1, -1, -1, -1, -1, index - 1, -1, 0, -1});
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
void callableControls() {
    const std::string source = "auto f(i64 x)->i64{return x;}";
    const auto configure = [&] {
        reset();
        const auto tokens = aurora::lex(source, "callable-record.au");
        records = {{wire(NodeKind::name), 10, -1, -1, 1, 10, 10}};
        types = {{wire(TypeKind::i64_type), 3, 3, 6, -1, -1, 3, 3}, {wire(TypeKind::i64_type), 7, 7, 14, -1, -1, 1, 3}};
        statements = {{wire(SyntaxKind::parameter), 3, 5, -1, -1, -1, 0, 4, -1, -1, 0, -1},
                      {wire(SyntaxKind::return_value), 9, 12, -1, 0, -1, -1, -1, -1, -1, 0, -1},
                      {wire(SyntaxKind::block), 8, 13, -1, -1, -1, -1, -1, 1, -1, 0, -1},
                      {wire(SyntaxKind::function), 1, 13, -1, -1, -1, 1, -1, 2, 0, 0, -1}};
        count = 1;
        typeCount = 2;
        statementCount = 4;
        result = {wire(Status::success), 3, 1, 13, static_cast<std::int64_t>(tokens.back().span.begin.offset)};
    };
    configure();
    auto tokens = aurora::lex(source, "callable-record.au");
    const auto original = tokens;
    const aurora::hosted_parser::Cursor cursor{0, 0};
    const auto parsedCallable = aurora::parseHostedCallable(tokens, cursor, Stop::function);
    require(parsedCallable.function.name == "f" && parsedCallable.function.params.size() == 1 &&
                parsedCallable.function.params.front().name == "x" && parsedCallable.function.body.size() == 1 &&
                parsedCallable.function.body.front()->expr->token.text == "x" && parsedCallable.next.ordinal == 13 &&
                parsedCallable.next.half == 0 && cursor.ordinal == 0 && cursor.half == 0 &&
                unchanged(original, tokens) && admitted == 0 && released == 1 && statementRead == 4 && typeRead == 2,
            "complete callable conversion, immutable caller state or cleanup changed");
    ++cases;
    const auto reject = [&](const std::string &label, const std::function<void()> &mutate) {
        configure();
        mutate();
        bool rejected = false;
        try {
            static_cast<void>(aurora::parseHostedCallable(tokens, cursor, Stop::function));
        } catch (const aurora::Error &error) {
            rejected = error.diagnostic.code == DiagnosticCode::Internal;
        }
        require(rejected && cursor.ordinal == 0 && cursor.half == 0 && unchanged(original, tokens) && released == 1,
                label + " did not preserve caller state and release the arena");
        ++cases;
    };
    reject("parameter type index", [] {
        statements[0][6] = typeCount;
    });
    reject("parameter binding index", [] {
        statements[0][7] = result[3];
    });
    reject("parameter borrow index", [] {
        statements[0][11] = result[3];
    });
    reject("parameter list cycle", [] {
        statements[0][3] = 0;
    });
    reject("parameter list wrong tag", [] {
        statements[3][9] = 1;
    });
    reject("callable body wrong tag", [] {
        statements[3][8] = 0;
    });
    reject("callable missing body", [] {
        statements[3][8] = -1;
    });
    reject("shared result type", [] {
        statements[3][6] = 0;
    });
    reject("unowned parameter", [] {
        statements[3][9] = -1;
    });
    reject("unowned callable body", [] {
        statements[3][8] = 1;
    });
    reject("wrong callable profile", [] {
        statements[3][0] = wire(SyntaxKind::method);
    });
    reject("invalid callable qualifier", [] {
        statements[3][10] = 2;
    });
    reject("callable residual half", [] {
        result[5] = 1;
    });
    reset();
    const std::string empty = "Box(){}";
    tokens = aurora::lex(empty, "empty-constructor.au");
    records.clear();
    count = 0;
    statements = {{wire(SyntaxKind::constructor), 0, 5, -1, -1, -1, -1, -1, -1, -1, 0, -1}};
    statementCount = 1;
    result = {wire(Status::success), 0, 0, 5, static_cast<std::int64_t>(tokens.back().span.begin.offset)};
    const auto constructor = aurora::parseHostedCallable(tokens, {0, 0}, Stop::constructor);
    require(constructor.function.constructor && constructor.function.initializers.empty() &&
                constructor.function.params.empty() && constructor.function.body.empty() &&
                constructor.next.ordinal == 5 && constructor.next.half == 0 && released == 1 && read == 0 &&
                typeRead == 0 && statementRead == 1,
            "empty constructor forest conversion changed");
    ++cases;
    const std::string initialized = "Box(i64 x):value(x){}";
    const auto configureConstructor = [&] {
        reset();
        tokens = aurora::lex(initialized, "initializer-record.au");
        records = {{wire(NodeKind::name), 8, -1, -1, 1, 8, 8}};
        types = {{wire(TypeKind::i64_type), 2, 2, 4, -1, -1, 2, 3}};
        statements = {{wire(SyntaxKind::parameter), 2, 4, -1, -1, -1, 0, 3, -1, -1, 0, -1},
                      {wire(SyntaxKind::initializer), 6, 10, -1, 0, -1, -1, -1, -1, -1, 0, -1},
                      {wire(SyntaxKind::constructor), 0, 12, -1, -1, -1, -1, -1, 1, 0, 0, -1}};
        count = typeCount = 1;
        statementCount = 3;
        result = {wire(Status::success), 2, 1, 12, static_cast<std::int64_t>(tokens.back().span.begin.offset)};
    };
    configureConstructor();
    const auto initializedCallable = aurora::parseHostedCallable(tokens, {0, 0}, Stop::constructor);
    require(initializedCallable.function.initializers.size() == 1 &&
                initializedCallable.function.initializers.front().first.text == "value" &&
                initializedCallable.function.initializers.front().second->token.text == "x" && released == 1,
            "constructor initializer conversion changed");
    ++cases;
    for (const int mutation : {0, 1, 2}) {
        configureConstructor();
        if (mutation == 0)
            statements[1][4] = count;
        else if (mutation == 1)
            statements[2][8] = 0;
        else
            statements[1][3] = 1;
        bool rejected = false;
        try {
            static_cast<void>(aurora::parseHostedCallable(tokens, {0, 0}, Stop::constructor));
        } catch (const aurora::Error &error) {
            rejected = error.diagnostic.code == DiagnosticCode::Internal;
        }
        require(rejected && released == 1, "invalid initializer ownership was not safely rejected");
        ++cases;
    }
    configure();
    tokens = aurora::lex(source, "throw-callable.au");
    const auto beforeThrow = tokens;
    throwingRead = 4;
    bool threw = false;
    try {
        static_cast<void>(aurora::parseHostedCallable(tokens, cursor, Stop::function));
    } catch (const std::runtime_error &error) {
        threw = std::string(error.what()) == "injected read failure";
    }
    require(threw && cursor.ordinal == 0 && cursor.half == 0 && unchanged(beforeThrow, tokens) && released == 1,
            "callable read exception leaked its arena or changed caller state");
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

Resolution::MetaRow resolutionMeta(Resolution::MetaTag tag) {
    Resolution::MetaRow value;
    value.tag = tag;
    value.value0 = value.value1 = value.value2 = value.value3 = value.value4 = value.value5 = value.value6 =
        value.value7 = value.value8 = value.value9 = value.value10 = value.value11 = value.value12 = value.value13 =
            value.value14 = -1;
    return value;
}
Resolution::SyntaxRow resolutionNode(Resolution::SyntaxTag tag) {
    Resolution::SyntaxRow value;
    value.tag = tag;
    value.value0 = value.value1 = value.value2 = value.value3 = value.value4 = value.value5 = value.value6 =
        value.value7 = value.value8 = value.value9 = value.value10 = value.value11 = -1;
    return value;
}
std::shared_ptr<const aurora::SourceText> resolutionFixture() {
    require(!sessionAddress && sessionPayload.allocation == 0, "previous forged resolution retained its payload owner");
    reset();
    auto source =
        std::make_shared<const aurora::SourceText>("resolved-record.au", "module forged;auto f()->i64{return 1;}");
    const auto tokens = aurora::lex(source);
    records = {{wire(NodeKind::literal), 11, -1, -1, 1, 11, 11}};
    types = {{wire(TypeKind::i64_type), 8, 8, 16, -1, -1, 4, 3}};
    statements = {{wire(SyntaxKind::preamble), 1, 3, -1, -1, -1, -1, 1, -1, -1, 0, -1},
                  {wire(SyntaxKind::return_value), 10, 13, -1, 0, -1, -1, -1, -1, -1, 0, -1},
                  {wire(SyntaxKind::block), 9, 14, -1, -1, -1, -1, -1, 1, -1, 0, -1},
                  {wire(SyntaxKind::function), 4, 14, -1, -1, -1, 0, -1, 2, -1, 0, -1},
                  {wire(SyntaxKind::declaration), 4, 14, -1, -1, -1, -1, -1, 3, -1, 0, -1},
                  {wire(SyntaxKind::module_definition), 0, 14, -1, -1, -1, -1, -1, 0, 4, 0, -1}};
    count = typeCount = 1;
    statementCount = 6;
    result = {wire(Status::success), 5, 1, 14, static_cast<std::int64_t>(source->text.size()), 0};
    resolutionSyntax.assign(8, resolutionNode(Resolution::SyntaxTag::declaration));
    resolutionSyntax[0] = resolutionNode(Resolution::SyntaxTag::expression);
    resolutionSyntax[0].expression_tag = NodeKind::literal;
    resolutionSyntax[0].value0 = 3;
    resolutionSyntax[1] = resolutionNode(Resolution::SyntaxTag::type);
    resolutionSyntax[1].type_tag = TypeKind::i64_type;
    resolutionSyntax[2].declaration_tag = SyntaxKind::preamble;
    resolutionSyntax[3].declaration_tag = SyntaxKind::return_value;
    resolutionSyntax[3].value0 = 2;
    resolutionSyntax[3].value3 = 0;
    resolutionSyntax[4].declaration_tag = SyntaxKind::block;
    resolutionSyntax[4].value7 = 3;
    resolutionSyntax[5].declaration_tag = SyntaxKind::function;
    resolutionSyntax[5].value0 = 1;
    resolutionSyntax[5].value5 = 1;
    resolutionSyntax[5].value7 = 4;
    resolutionSyntax[5].value9 = 0;
    resolutionSyntax[6].declaration_tag = SyntaxKind::declaration;
    resolutionSyntax[7].declaration_tag = SyntaxKind::module_definition;
    resolutionMetadata.assign(8, resolutionMeta(Resolution::MetaTag::invalid));
    auto &module = resolutionMetadata[0];
    module.tag = Resolution::MetaTag::module_source;
    module.value0 = 0;
    module.value1 = static_cast<std::int64_t>(source->text.size());
    module.value2 = 0;
    module.value3 = 1;
    module.value4 = 1;
    module.value5 = 0;
    module.value6 = 1;
    module.value7 = 1;
    module.value8 = 2;
    module.value9 = 6;
    module.value11 = 0;
    for (const auto &[reference, ordinal] : {std::pair{1, 4}, std::pair{2, 10}, std::pair{3, 11}}) {
        auto &value = resolutionMetadata[reference];
        const auto &token = tokens[ordinal];
        value.tag = Resolution::MetaTag::source_reference;
        value.value0 = 0;
        value.value1 = static_cast<std::int64_t>(token.span.begin.offset);
        value.value2 = static_cast<std::int64_t>(token.span.end.offset);
        value.value3 = token.span.begin.line;
        value.value4 = token.span.begin.column;
        value.value5 = ordinal;
        value.value6 = 0;
        value.value7 = token.span.end.line;
        value.value8 = token.span.end.column;
        value.value9 = 0;
    }
    resolutionMetadata[4].tag = Resolution::MetaTag::concrete_type;
    resolutionMetadata[4].concrete_tag = Resolution::ResolvedTypeKind::i64_value;
    auto &symbol = resolutionMetadata[5];
    symbol.tag = Resolution::MetaTag::symbol;
    symbol.declaration_tag = Resolution::DeclarationKind::function;
    symbol.native_tag = Resolution::NativeMode::root_entry;
    symbol.value1 = 0;
    symbol.value4 = 1;
    symbol.value5 = 5;
    symbol.value6 = 0;
    resolutionMetadata[6].tag = Resolution::MetaTag::link;
    resolutionMetadata[6].value0 = 5;
    resolutionMetadata[7].tag = Resolution::MetaTag::context;
    resolutionMetadata[7].value0 = 1;
    resolutionMetadata[7].value1 = 6;
    Resolution::ResolvedRow decoration;
    decoration.operation_tag = Resolution::ResolvedOperation::unchanged;
    decoration.value0 = decoration.value1 = decoration.value2 = decoration.value3 = decoration.value4 =
        decoration.value5 = decoration.value6 = decoration.value7 = -1;
    resolutionDecorations.assign(8, decoration);
    resolutionDecorations[1].value2 = 4;
    resolutionStatus = {Resolution::StorageStatus::none, Resolution::SemanticError::none, -1, -1, -1};
    sessionAddress = nullptr;
    sessionsCreated = sessionsReleased = transferred = pairsReleased = projectionThrow = 0;
    resolverRunning = allocationOnIngest = false;
    reportedSyntax = 8;
    reportedMetadata = 8;
    reportedDecorations = 8;
    sourceBytes = static_cast<std::int64_t>(source->text.size());
    seedIdentity = 0;
    loweringResult = {
        Lowering::LoweringStatus::semantic_failure, Lowering::LoweringError::function_parameter_limit, 0, -1};
    loweringReport = {};
    loweringReport.recordKind = Lowering::RecordKind::DiagnosticPayload;
    loweringReport.operandBegin = 0;
    loweringReport.operandCount = 3;
    loweringOperands = {};
    loweringOperands[0].operandRole = Lowering::OperandRole::DiagnosticSourceRef;
    loweringOperands[0].signedValue = 1;
    loweringOperands[1].operandRole = loweringOperands[2].operandRole = Lowering::OperandRole::NoDiagnosticValue;
    reportedOutputs = 1;
    reportedOperands = 3;
    loweringBegun = loweringRun = loweringOutputReads = loweringOperandReads = scalarSeeds = serviceSeeds = 0;
    loweringAllocation = false;
    return source;
}
void resolutionControls() {
    auto source = resolutionFixture();
    // This host-only fixture publishes a deliberately forged failure report.
    // It never claims that stubbed native lowering produced a valid module.
    std::optional<aurora::Diagnostic> diagnostic;
    {
        aurora::HostedResolution resolution;
        const auto module = resolution.add(source);
        require(module.id == 0 && module.moduleName == "forged" && !module.interfaceUnit && module.imports.empty(),
                "session ingestion lost copied parser header metadata");
        try {
            static_cast<void>(resolution.resolve({module.id}, module.id, aurora::AnalysisMode::Check, true));
        } catch (const aurora::Error &error) {
            diagnostic = error.diagnostic;
        }
        require(sessionsReleased == 1 && sessionPayload.allocation == 0,
                "failed lowering retained its Session until adapter destruction");
    }
    require(diagnostic && diagnostic->code == DiagnosticCode::Semantic &&
                diagnostic->message == "at most six parameters supported" && diagnostic->span.source == source &&
                diagnostic->span.begin.offset == source->text.find("f()") &&
                diagnostic->span.end.offset == diagnostic->span.begin.offset + 1 && sessionsCreated == 1 &&
                sessionsReleased == 1 && transferred == 1 && pairsReleased == 0 && created == 1 && parsed == 1 &&
                admitted == 1 && released == 1 && statementRead == 2 && read == 0 && edgeRead == 0 && typeRead == 0 &&
                loweringBegun == 1 && loweringRun == 1 && scalarSeeds == 7 && serviceSeeds == 5 &&
                loweringOutputReads == 1 && loweringOperandReads == 3 && sessionPayload.allocation == 0,
            "typed failure report lost source, bounded reads, configuration or exact consuming cleanup");
    ++cases;
    const auto reject = [&](const char *label, const std::function<void()> &mutate, bool injected = false) {
        source = resolutionFixture();
        bool rejected = false;
        try {
            aurora::HostedResolution resolution;
            const auto module = resolution.add(source);
            mutate();
            static_cast<void>(resolution.resolve({module.id}, module.id, aurora::AnalysisMode::Check, true));
        } catch (const aurora::Error &error) {
            rejected = !injected && error.diagnostic.code == DiagnosticCode::Internal;
        } catch (const std::runtime_error &error) {
            rejected = injected && std::string(error.what()) == "injected resolved read failure";
        }
        require(rejected && sessionsCreated == 1 && sessionsReleased == 1 && transferred == 1 && pairsReleased == 0 &&
                    released == 1 && sessionPayload.allocation == 0,
                std::string(label) + ": unsafe typed projection escaped or released a consumed owner twice");
        ++cases;
    };
    reject("negative source byte count", [] {
        sourceBytes = -1;
    });
    reject("source byte count exceeds payload", [] {
        sourceBytes = std::numeric_limits<std::int64_t>::max();
    });
    reject("negative resolved syntax count", [] {
        reportedSyntax = -1;
    });
    reject("negative resolved metadata count", [] {
        reportedMetadata = -1;
    });
    reject("negative resolved decoration count", [] {
        reportedDecorations = -1;
    });
    reject("resolved syntax count exceeds payload", [] {
        reportedSyntax = std::numeric_limits<std::int64_t>::max();
    });
    reject("resolved metadata count exceeds payload", [] {
        reportedMetadata = std::numeric_limits<std::int64_t>::max();
    });
    reject("resolved decoration count exceeds payload", [] {
        reportedDecorations = std::numeric_limits<std::int64_t>::max();
    });
    reject("unknown storage status", [] {
        resolutionStatus.storage = static_cast<Resolution::StorageStatus>(99);
    });
    reject("unknown semantic diagnostic", [] {
        resolutionStatus.diagnostic = static_cast<Resolution::SemanticError>(999);
    });
    reject("successful resolver status carries a node", [] {
        resolutionStatus.node = 0;
    });
    reject("successful resolver status carries first detail", [] {
        resolutionStatus.first = 0;
    });
    reject("successful resolver status carries second detail", [] {
        resolutionStatus.second = 0;
    });
    reject("mismatched decoration count", [] {
        --reportedDecorations;
    });
    reject("ABI declaration has wrong syntax domain", [] {
        resolutionSyntax[5].tag = Resolution::SyntaxTag::expression;
    });
    reject("unknown native identity mode", [] {
        resolutionMetadata[5].native_tag = static_cast<Resolution::NativeMode>(99);
    });
    reject("symbol defining module outside graph", [] {
        resolutionMetadata[5].value1 = 1;
    });
    reject("output list cycle", [] {
        resolutionMetadata[6].value1 = 6;
    });
    reject("wrong output list tag", [] {
        resolutionMetadata[6].tag = Resolution::MetaTag::signature;
    });
    reject("output symbol outside metadata", [] {
        resolutionMetadata[6].value0 = 8;
    });
    reject("reversed sparse source span", [] {
        resolutionMetadata[1].value2 = resolutionMetadata[1].value1 - 1;
    });
    reject("sparse span outside source", [] {
        resolutionMetadata[1].value2 = sourceBytes + 1;
    });
    reject("sparse span wrong source", [] {
        resolutionMetadata[1].value0 = 1;
    });
    reject("sparse span invalid column", [] {
        resolutionMetadata[1].value4 = 0;
    });
    const auto typeReport = [] {
        loweringResult.result_reason = Lowering::LoweringError::type_mismatch;
        loweringOperands[1].operandRole = loweringOperands[2].operandRole = Lowering::OperandRole::DiagnosticTypeId;
        loweringOperands[1].signedValue = loweringOperands[2].signedValue = 4;
    };
    reject("diagnostic concrete type has wrong metadata domain", [&] {
        typeReport();
        resolutionMetadata[4].tag = Resolution::MetaTag::symbol;
    });
    reject("diagnostic concrete type outside metadata", [&] {
        typeReport();
        loweringOperands[1].signedValue = 8;
    });
    reject("diagnostic concrete type has unknown kind", [&] {
        typeReport();
        resolutionMetadata[4].concrete_tag = static_cast<Resolution::ResolvedTypeKind>(99);
    });
    // The projection no longer reads every syntax/decoration row to build an
    // AST. Exceptions are injected only on source views it still consumes.
    for (const int read : {1, 2})
        reject(
            "resolved copied-row read exception",
            [=] {
                projectionThrow = read;
            },
            true);

    reject("unknown lowering status", [] {
        loweringResult.result_status = static_cast<Lowering::LoweringStatus>(99);
    });
    reject("unknown lowering reason", [] {
        loweringResult.result_reason = static_cast<Lowering::LoweringError>(999);
    });
    reject("failure lacks a reason", [] {
        loweringResult.result_reason = Lowering::LoweringError::none;
    });
    reject("failure publishes a module root", [] {
        loweringResult.root_row = 15;
    });
    reject("failure omits its diagnostic root", [] {
        loweringResult.diagnostic_row = -1;
    });
    reject("success carries a failure reason", [] {
        loweringResult.result_status = Lowering::LoweringStatus::success;
    });
    reject("success publishes no module root", [] {
        loweringResult.result_status = Lowering::LoweringStatus::success;
        loweringResult.result_reason = Lowering::LoweringError::none;
    });
    reject("success publishes a prelude row", [] {
        loweringResult.result_status = Lowering::LoweringStatus::success;
        loweringResult.result_reason = Lowering::LoweringError::none;
        loweringResult.root_row = 14;
    });
    reject("storage failure lacks an allocation status", [] {
        loweringResult.result_status = Lowering::LoweringStatus::storage_failure;
    });
    reject("negative typed output count", [] {
        reportedOutputs = -1;
    });
    reject("negative typed operand count", [] {
        reportedOperands = -1;
    });
    reject("typed output count exceeds payload", [] {
        reportedOutputs = std::numeric_limits<std::int64_t>::max();
    });
    reject("typed operand count exceeds payload", [] {
        reportedOperands = std::numeric_limits<std::int64_t>::max();
    });
    reject("truncated failure output row", [] {
        reportedOutputs = 0;
    });
    reject("truncated failure operand prefix", [] {
        reportedOperands = 2;
    });
    reject("failure row has wrong record kind", [] {
        loweringReport.recordKind = Lowering::RecordKind::Module;
    });
    reject("failure row has wrong prefix begin", [] {
        loweringReport.operandBegin = 1;
    });
    reject("failure row has wrong prefix length", [] {
        loweringReport.operandCount = 2;
    });
    reject("failure source has wrong operand domain", [] {
        loweringOperands[0].operandRole = Lowering::OperandRole::TypeId;
    });
    reject("failure source escapes metadata", [] {
        loweringOperands[0].signedValue = 8;
    });
    reject("failure detail has wrong operand domain", [] {
        loweringOperands[1].operandRole = Lowering::OperandRole::DiagnosticInteger;
    });
    reject("negative active diagnostic type", [&] {
        typeReport();
        loweringOperands[2].signedValue = -1;
    });
    reject("native lowering allocation preserves owner cleanup", [] {
        loweringAllocation = true;
    });

    for (const bool afterTransfer : {false, true}) {
        source = resolutionFixture();
        allocationOnIngest = afterTransfer;
        throwingAdmission = !afterTransfer;
        bool rejected = false;
        try {
            aurora::HostedResolution resolution;
            static_cast<void>(resolution.add(source));
        } catch (const aurora::Error &error) {
            rejected = afterTransfer && error.diagnostic.code == DiagnosticCode::Internal &&
                       error.diagnostic.message == "hosted module resolution allocation failed";
        } catch (const std::runtime_error &error) {
            rejected = !afterTransfer && std::string(error.what()) == "injected admission failure";
        }
        require(rejected && sessionsReleased == 1 && released == 1 && transferred == int(afterTransfer) &&
                    pairsReleased == int(!afterTransfer) && sessionPayload.allocation == 0 && loweringRun == 0,
                "failure on either side of owner consumption selected the wrong cleanup prefix");
        ++cases;
    }
}

} // namespace
// No forged report in this fixture may reach successful module verification.
// A distinct exception prevents the rejection controls from accepting this path.
void aurora::ir::verifyHostedGraph(Module &) {
    throw std::runtime_error("forged projection unexpectedly reached graph verification");
}
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
            "copied Input152 changed the borrowed source descriptor");
    ++parsed;
    std::memcpy(output, result.data(), sizeof(result));
}
extern "C" void aurora_hosted_parser_admit(void *arena, const void *input, void *output) {
    require(arena == arenaAddress, "admission changed the existing arena address");
    std::memcpy(capturedAdmissionInput.data(), input, sizeof(capturedAdmissionInput));
    require(std::equal(capturedAdmissionInput.begin(), capturedAdmissionInput.begin() + 7, capturedInput.begin()) &&
                capturedAdmissionInput[7] == static_cast<std::uint64_t>(result[1]) && capturedAdmissionInput[8] == 64 &&
                capturedAdmissionInput[9] == 512 && capturedAdmissionInput[10] == 62 &&
                capturedAdmissionInput[11] == 1 && capturedAdmissionInput[12] == 2 && capturedAdmissionInput[13] == 4,
            "admission changed its copied source/root or canonical layout/service configuration");
    ++admitted;
    if (throwingAdmission)
        throw std::runtime_error("injected admission failure");
    std::memcpy(output, admissionResult.data(), sizeof(admissionResult));
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
extern "C" std::int64_t aurora_hosted_parser_syntax_count(const void *) {
    return statementCount;
}
extern "C" void aurora_hosted_parser_syntax(const void *, std::int64_t index, void *output) {
    if (throwingRead == 4)
        throw std::runtime_error("injected read failure");
    require(index >= 0 && static_cast<std::size_t>(index) < statements.size(),
            "adapter requested out-of-range statement");
    ++statementRead;
    std::memcpy(output, statements[static_cast<std::size_t>(index)].data(), sizeof(SyntaxWords));
}
extern "C" void aurora_hosted_parser_release(void *owner) {
    const auto &record = *static_cast<const aurora::hosted_abi::ParserRelease *>(owner);
    require(record.arena.storage.data() == arenaAddress, "release did not receive the enclosing owner");
    std::uint64_t canary = 0;
    std::memcpy(&canary, record.arena.storage.data() + record.arena.storage.size() - sizeof(canary), sizeof(canary));
    require(record.region == arenaRegion && canary == arenaCanary, "owner region or arena boundary was corrupted");
    ++released;
}

namespace {
void checkSession(const void *address) {
    require(address == sessionAddress && sessionsCreated == sessionsReleased + 1,
            "resolver used an inactive or copied Session slot");
    std::uint64_t value = 0;
    std::memcpy(&value,
                static_cast<const unsigned char *>(address) + aurora::hosted_abi::sessionBytes - sizeof(value),
                sizeof(value));
    require(value == sessionCanary, "Session owner boundary was corrupted");
}
void armSession(void *address) {
    sessionAddress = address;
    static_assert(aurora::hosted_abi::sessionBytes >= sizeof(sessionCanary));
    std::memcpy(static_cast<unsigned char *>(address) + aurora::hosted_abi::sessionBytes - sizeof(sessionCanary),
                &sessionCanary,
                sizeof(sessionCanary));
}
void consumeParsed(const void *address, std::uint64_t region) {
    require(address == arenaAddress && region == arenaRegion && created == released + 1,
            "resolver consumed an inactive parser or crossed its region");
    std::uint64_t value = 0;
    std::memcpy(&value,
                static_cast<const unsigned char *>(address) + aurora::hosted_abi::arenaBytes - sizeof(value),
                sizeof(value));
    require(value == arenaCanary, "paired parser owner boundary was corrupted");
    ++released;
    arenaAddress = nullptr;
}
template <class Row>
void resolvedRead(const void *session, std::int64_t index, void *output, const std::vector<Row> &rows, int kind) {
    checkSession(session);
    if (resolverRunning && projectionThrow == kind)
        throw std::runtime_error("injected resolved read failure");
    require(index >= 0 && static_cast<std::size_t>(index) < rows.size(), "resolver requested an out-of-range row");
    std::memcpy(output, &rows[static_cast<std::size_t>(index)], sizeof(Row));
}
} // namespace
extern "C" void aurora_hosted_resolver_create(const void *input, void *output) {
    const auto &record = *static_cast<const aurora::hosted_abi::ResolverCreate *>(input);
    require(record.region != 0 && !sessionAddress, "resolver create did not receive a fresh same-region slot");
    sessionRegion = record.region;
    const auto bytes = resolutionSyntax.size() * sizeof(Resolution::SyntaxRow) +
                       resolutionMetadata.size() * sizeof(Resolution::MetaRow) +
                       resolutionDecorations.size() * sizeof(Resolution::ResolvedRow) +
                       static_cast<std::size_t>(sourceBytes) + sizeof(loweringReport) + sizeof(loweringOperands);
    aurora::hosted::bytes::__au_runtime_bytes_allocate(
        record.region, static_cast<std::int64_t>(bytes), &sessionPayload);
    require(sessionPayload.success == 1, "forged resolution payload allocation failed");
    ++sessionsCreated;
    armSession(output);
}
extern "C" void aurora_hosted_resolver_ingest(void *input, void *output) {
    const auto &record = *static_cast<const aurora::hosted_abi::ResolverIngest *>(input);
    checkSession(record.session.storage.data());
    require(record.region == sessionRegion && record.module == 0 && record.root == result[1] &&
                output != record.session.storage.data() && output != record.parsed.storage.data(),
            "consuming transfer aliased input/output or changed its copied coordinates");
    consumeParsed(record.parsed.storage.data(), record.region);
    ++transferred;
    armSession(output);
    if (allocationOnIngest)
        resolutionStatus.storage = Resolution::StorageStatus::allocation;
    else {
        resolutionMetadata[0].tag = Resolution::MetaTag::module_unit;
        resolutionMetadata[0].value10 = 7;
    }
}
extern "C" void aurora_hosted_resolver_release(void *input) {
    const auto &record = *static_cast<const aurora::hosted_abi::ResolverRelease *>(input);
    checkSession(record.session.storage.data());
    require(record.region == sessionRegion && created == released,
            "Session-only release retained a live parsed owner or lost its region");
    aurora::hosted::bytes::__au_runtime_bytes_drop(&sessionPayload);
    ++sessionsReleased;
    sessionAddress = nullptr;
}
extern "C" void aurora_hosted_resolver_release_pair(void *input) {
    const auto &record = *static_cast<const aurora::hosted_abi::ResolverReleasePair *>(input);
    checkSession(record.session.storage.data());
    require(record.region == sessionRegion, "paired release changed its Session region");
    consumeParsed(record.parsed.storage.data(), record.region);
    aurora::hosted::bytes::__au_runtime_bytes_drop(&sessionPayload);
    ++pairsReleased;
    ++sessionsReleased;
    sessionAddress = nullptr;
}
extern "C" std::int64_t aurora_hosted_resolver_append_source(void *session, const void *input) {
    checkSession(session);
    const auto &record = *static_cast<const aurora::hosted_abi::ResolverSourceInput *>(input);
    require(record.source.kind == 0 && record.source.start == 0 && record.source.length == sourceBytes &&
                record.source.reserved == std::array<std::uint64_t, 3>{},
            "source ingestion changed its borrowed contiguous span");
    return 0;
}
extern "C" std::int64_t aurora_hosted_resolver_append_text(void *session, const void *input) {
    checkSession(session);
    const auto &record = *static_cast<const aurora::hosted_abi::ResolverTextInput *>(input);
    require(record.text.kind == 0 && record.text.start == 0 && record.text.length > 0,
            "canonical seed spelling lost its copied source span");
    return 0;
}
extern "C" std::int64_t aurora_hosted_resolver_seed_builtin(void *session, const void *) {
    checkSession(session);
    return seedIdentity++;
}
extern "C" std::int64_t aurora_hosted_resolver_seed_member(void *session, const void *) {
    checkSession(session);
    return 0;
}
extern "C" std::int64_t aurora_hosted_resolver_order_module(void *session, const void *input) {
    checkSession(session);
    const auto &record = *static_cast<const aurora::hosted_abi::ResolverOrderInput *>(input);
    require(record.module == 0 && record.order == 0 && record.scope == 0 && record.root == 1,
            "resolved root/order/scope inputs differ");
    return 1;
}
extern "C" std::int64_t aurora_hosted_resolver_bind_import(void *, const void *) {
    throw std::runtime_error("import-free resolution fixture acquired an import binding");
}
extern "C" std::int64_t aurora_hosted_resolver_run(void *session) {
    checkSession(session);
    resolverRunning = true;
    return 0;
}
extern "C" std::int64_t aurora_hosted_resolver_count(const void *session, std::int64_t pool) {
    checkSession(session);
    if (pool == 0)
        return sourceBytes;
    if (pool == 1)
        return reportedSyntax;
    if (pool == 2)
        return reportedMetadata;
    if (pool == 3)
        return reportedDecorations;
    if (pool == 4)
        return 0;
    if (pool == 5)
        return 1;
    return -1;
}
extern "C" std::int64_t aurora_hosted_resolver_read_source(const void *session, std::int64_t) {
    checkSession(session);
    return -1;
}
extern "C" void aurora_hosted_resolver_status(const void *session, void *output) {
    checkSession(session);
    std::memcpy(output, &resolutionStatus, sizeof(resolutionStatus));
}
extern "C" void aurora_hosted_resolver_read_syntax(const void *session, std::int64_t index, void *output) {
    resolvedRead(session, index, output, resolutionSyntax, 1);
}
extern "C" void aurora_hosted_resolver_read_meta(const void *session, std::int64_t index, void *output) {
    resolvedRead(session, index, output, resolutionMetadata, 2);
}
extern "C" void aurora_hosted_resolver_read_resolved(const void *session, std::int64_t index, void *output) {
    resolvedRead(session, index, output, resolutionDecorations, 3);
}

// Eight copied lowering endpoints. Only the fixed failure report above is
// supplied; valid typed modules must come from the real native fixture.
extern "C" std::int64_t aurora_hosted_lowering_begin(void *session, const void *input) noexcept {
    checkSession(session);
    const auto &configuration = static_cast<const aurora::hosted_abi::LoweringBeginInput *>(input)->configuration;
    require(configuration.byteLeaves == aurora::maximumCopiedByteLeaves &&
                configuration.nonByteLeaves == aurora::maximumCopiedNonByteLeaves &&
                configuration.totalLeaves == aurora::maximumCopiedClassLeaves &&
                configuration.copiedBytes == aurora::maximumCopiedClassBytes &&
                configuration.byteArrayLength == aurora::maximumClassByteArrayLength &&
                configuration.scalarArrayLength == aurora::maximumClassScalarArrayLength &&
                configuration.analysisMode == 0 &&
                configuration.serviceGroups == aurora::service::supportedGroupBitmap(),
            "lowering received a changed copied configuration");
    ++loweringBegun;
    return 1;
}
extern "C" std::int64_t aurora_hosted_lowering_seed_scalar(void *session, const void *input) noexcept {
    checkSession(session);
    const auto &seed = static_cast<const aurora::hosted_abi::LoweringScalarInput *>(input)->seed;
    require(seed.publicId > 0 && (seed.byteSize == 1 || seed.byteSize == 8), "invalid copied scalar seed");
    return ++scalarSeeds + 1;
}
extern "C" std::int64_t aurora_hosted_lowering_seed_service(void *session, const void *input) noexcept {
    checkSession(session);
    const auto &seed = static_cast<const aurora::hosted_abi::LoweringServiceInput *>(input)->seed;
    require(seed.operationId == serviceSeeds && seed.kindId >= 0 && seed.kindId < 3 &&
                seed.parameterTypes.parameterCount >= 0 && seed.parameterTypes.parameterCount <= 5,
            "invalid copied service seed");
    return ++serviceSeeds + 8;
}
extern "C" std::int64_t aurora_hosted_lowering_seed_layout_symbol(void *session, std::int64_t) noexcept {
    checkSession(session);
    // This fixture has no nominal layout. An unexpected seed must fail closed.
    return -1;
}
extern "C" void aurora_hosted_lowering_run(void *session, void *output) noexcept {
    checkSession(session);
    ++loweringRun;
    auto result = loweringResult;
    if (loweringAllocation) {
        resolutionStatus.storage = Resolution::StorageStatus::allocation;
        result = {Lowering::LoweringStatus::storage_failure, Lowering::LoweringError::none, -1, -1};
    }
    std::memcpy(output, &result, sizeof(result));
}
extern "C" std::int64_t aurora_hosted_lowering_count(const void *session, std::int64_t pool) noexcept {
    checkSession(session);
    return pool == 0 ? reportedOutputs : pool == 1 ? reportedOperands : -1;
}
extern "C" void aurora_hosted_lowering_read_output(const void *session, std::int64_t index, void *output) noexcept {
    checkSession(session);
    require(index == 0, "failure conversion read beyond its reserved output row");
    ++loweringOutputReads;
    std::memcpy(output, &loweringReport, sizeof(loweringReport));
}
extern "C" void aurora_hosted_lowering_read_operand(const void *session, std::int64_t index, void *output) noexcept {
    checkSession(session);
    require(index >= 0 && index < 3, "failure conversion read beyond its reserved operand prefix");
    ++loweringOperandReads;
    std::memcpy(output, &loweringOperands[static_cast<std::size_t>(index)], sizeof(loweringOperands[0]));
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
        callableControls();
        declarationTypeControls();
        continuationControls();
        fieldControls();
        preambleEnumControls();
        moduleControls();
        resolutionControls();
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
