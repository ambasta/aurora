// Adversarial host-only controls: forged records never reach generated Aurora.
// Every failure must preserve the input cursor and release the arena once.
#include "lexer.hpp"
#include "hosted_parser.hpp"
#include "parser.hpp"
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
using InputWords = std::array<std::uint64_t, 18>;
static_assert(sizeof(TypeWords) == 64 && sizeof(InputWords) == 144);
using aurora::DiagnosticCode;
using aurora::hosted_parser::NodeKind;
using aurora::hosted_parser::Status;
using aurora::hosted_parser::Stop;
using aurora::hosted_parser::TypeKind;
constexpr std::int64_t wire(Status value) {
    return static_cast<std::int64_t>(value);
}
constexpr std::int64_t wire(NodeKind value) {
    return static_cast<std::int64_t>(value);
}
constexpr std::int64_t wire(TypeKind value) {
    return static_cast<std::int64_t>(value);
}
bool hookControl = false, hookPrepared = false;
bool hookUnsupported = false, hookCorrupt = false;
std::vector<Stop> hookStops;
std::vector<std::array<std::uint64_t, 7>> hookContexts;
ResultWords result;
std::vector<NodeWords> records;
std::vector<EdgeWords> edges;
std::vector<TypeWords> types;
InputWords capturedInput{};
void *arenaAddress = nullptr;
std::uint64_t arenaRegion = 0;
constexpr std::uint64_t arenaCanary = 0x746970656172656eULL;
std::int64_t count = 0, edgeCount = 0, typeCount = 0;
int created = 0, parsed = 0, released = 0, read = 0, edgeRead = 0, typeRead = 0;
std::size_t cases = 0;
void require(bool value, const std::string &message) {
    if (!value)
        throw std::runtime_error(message);
}
void reset() {
    result = {wire(Status::Success), 2, 3, 3, 3};
    records = {{wire(NodeKind::Literal), 0, -1, -1, 1, 0, 0},
               {wire(NodeKind::Literal), 2, -1, -1, 1, 2, 2},
               {wire(NodeKind::Binary), 1, 0, 1, 2, 1, 1}};
    count = 3;
    edgeCount = typeCount = 0;
    edges.clear();
    types.clear();
    hookStops.clear();
    hookContexts.clear();
    hookUnsupported = hookCorrupt = hookPrepared = false;
    created = parsed = released = read = edgeRead = typeRead = 0;
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
    result = {wire(Status::Success),
              count - 1,
              count,
              consumed,
              static_cast<std::int64_t>(tokens[static_cast<std::size_t>(consumed)].span.begin.offset)};
}
void callFixture(const std::string &source = "f(1,2);") {
    fixture(source,
            {{wire(NodeKind::Literal), 2, -1, -1, 1, 2, 2},
             {wire(NodeKind::Literal), 4, -1, -1, 1, 4, 4},
             {wire(NodeKind::Call), 0, 1, 2, 2, 0, 5}},
            {{0, -1, 1, 2, -1}, {1, 0, 2, 2, -1}});
}
void methodFixture(const std::string &source = "a.m(1);") {
    fixture(source,
            {{wire(NodeKind::Name), 0, -1, -1, 1, 0, 0},
             {wire(NodeKind::Literal), 4, -1, -1, 1, 4, 4},
             {wire(NodeKind::MethodCall), 2, 1, 2, 2, 2, 5}},
            {{0, -1, 1, 2, -1}, {1, 0, 2, 2, -1}});
}
void indexFixture(const std::string &source = "a[i];") {
    fixture(source,
            {{wire(NodeKind::Name), 0, -1, -1, 1, 0, 0},
             {wire(NodeKind::Name), 2, -1, -1, 1, 2, 2},
             {wire(NodeKind::Index), 1, 0, 1, 2, 1, 3}});
}
void arrayFixture(const std::string &source = "{1,2};") {
    fixture(source,
            {{wire(NodeKind::Literal), 1, -1, -1, 1, 1, 1},
             {wire(NodeKind::Literal), 3, -1, -1, 1, 3, 3},
             {wire(NodeKind::ArrayLiteral), 0, 1, 2, 2, 0, 4}},
            {{0, -1, 1, 2, -1}, {1, 0, 2, 2, -1}});
}
void constructFixture(const std::string &source = "T{.a=1,.b=2};") {
    fixture(source,
            {{wire(NodeKind::Literal), 5, -1, -1, 1, 5, 5},
             {wire(NodeKind::Literal), 10, -1, -1, 1, 10, 10},
             {wire(NodeKind::Construct), 0, 1, 2, 2, 0, 11}},
            {{0, -1, 1, 2, 3}, {1, 0, 2, 2, 8}});
}
void constructorFixture(const std::string &source = "field{1};", bool empty = false) {
    if (empty)
        fixture(source, {{wire(NodeKind::ArrayZero), 0, -1, 0, 1, 0, 2}}, {}, 3);
    else
        fixture(source,
                {{wire(NodeKind::Literal), 2, -1, -1, 1, 2, 2}, {wire(NodeKind::ArrayLiteral), 0, 0, 1, 2, 0, 3}},
                {{0, -1, 1, 2, -1}},
                4);
}
void typedFixture(const std::string &source,
                  std::vector<TypeWords> syntax,
                  std::vector<NodeWords> nodes = {},
                  std::vector<EdgeWords> arguments = {}) {
    const auto tokens = aurora::lex(source, "forged.au");
    if (nodes.empty())
        nodes = {{wire(NodeKind::Call), 0, -1, 0, 1, 0, static_cast<std::int64_t>(tokens.size()) - 3}};
    fixture(source, std::move(nodes), std::move(arguments));
    types = std::move(syntax);
    typeCount = static_cast<std::int64_t>(types.size());
}
void templateFixture(const std::string &source = "f<i64>();") {
    typedFixture(source,
                 {{wire(TypeKind::I64), 2, 2, 4, -1, -1, -1, 0}, {wire(TypeKind::Named), 0, 0, 6, 0, -1, 0, 1}});
}
void reflectedFixture(const std::string &source = "size_of(i64);") {
    typedFixture(source, {{wire(TypeKind::I64), 2, 2, 4, -1, -1, 0, 2}});
}
void splitFixture(const std::string &source = "f<Box<i64>>();") {
    typedFixture(source,
                 {{wire(TypeKind::I64), 4, 4, 8, -1, -1, -1, 0},
                  {wire(TypeKind::Named), 2, 2, 10, 0, -1, -1, 0},
                  {wire(TypeKind::Named), 0, 0, 11, 1, -1, 0, 1}});
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
    std::vector<TypeWords> syntax{{wire(TypeKind::I64), scalar, scalar, scalar * 2, -1, -1, -1, 0}};
    for (int index = 0; index < levels; ++index) {
        const auto token = begin + 2 * (levels - index - 1);
        syntax.push_back({wire(TypeKind::Named),
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
// Expected trees are authored separately from the forged ABI records. These
// helpers only assemble explicitly supplied AST fields and original token spans.
using Tokens = std::vector<aurora::Token>;
using ExpectedExpression = std::function<aurora::ExpressionPtr(const Tokens &)>;
aurora::ExpressionPtr expectedNode(const Tokens &tokens,
                                   std::size_t ordinal,
                                   const std::string &operation,
                                   std::vector<aurora::ExpressionPtr> children = {}) {
    auto expression = std::make_shared<aurora::Expression>(operation, tokens.at(ordinal));
    for (const auto &child : children)
        expression->depth = std::max(expression->depth, child->depth + 1);
    expression->args = std::move(children);
    return expression;
}
aurora::ExpressionPtr
qualifiedNode(aurora::ExpressionPtr expression, const Tokens &tokens, std::size_t last, const std::string &spelling) {
    expression->token.text = spelling;
    expression->token.span.end = tokens.at(last).span.end;
    return expression;
}
aurora::ExpressionPtr typedNode(aurora::ExpressionPtr expression,
                                std::vector<aurora::TemplateArgument> arguments,
                                aurora::Type reflected = {}) {
    expression->templateArguments = std::move(arguments);
    expression->reflectedType = std::move(reflected);
    return expression;
}
aurora::ExpressionPtr designatedNode(aurora::ExpressionPtr expression, std::vector<std::string> fields) {
    expression->fieldNames = std::move(fields);
    return expression;
}
aurora::TemplateArgument namedArgument(const std::string &name, std::vector<aurora::TemplateArgument> arguments) {
    aurora::TemplateArgument argument(name);
    argument.templateArguments = std::move(arguments);
    return argument;
}
aurora::Type namedType(const std::string &name, std::vector<aurora::TemplateArgument> arguments = {}) {
    aurora::Type type(name);
    type.templateArguments = std::move(arguments);
    return type;
}
aurora::Type builtinClass(const std::string &identity, const std::string &spelling) {
    aurora::Type type(identity);
    type.displayName = spelling;
    return type;
}
aurora::Type builtinEnum(const std::string &identity, const std::string &spelling) {
    auto type = aurora::Type::enumeration(identity);
    type.displayName = spelling;
    return type;
}
void sameExpression(const aurora::ExpressionPtr &actual, const aurora::ExpressionPtr &expected) {
    require(actual && expected && actual->op == expected->op && actual->token.text == expected->token.text &&
                actual->token.line == expected->token.line && actual->depth == expected->depth &&
                actual->args.size() == expected->args.size() && actual->fieldNames == expected->fieldNames &&
                actual->templateArguments == expected->templateArguments &&
                actual->reflectedType == expected->reflectedType &&
                actual->reflectedType.displayName == expected->reflectedType.displayName &&
                actual->reflectedType.resolvedClass == expected->reflectedType.resolvedClass,
            "valid forged control changed AST spelling, kind, depth or arguments");
    const auto &a = actual->token.span, &b = expected->token.span;
    require(a.source == b.source && a.begin.offset == b.begin.offset && a.begin.line == b.begin.line &&
                a.begin.column == b.begin.column && a.end.offset == b.end.offset && a.end.line == b.end.line &&
                a.end.column == b.end.column,
            "valid forged control changed token provenance");
    for (std::size_t index = 0; index < actual->args.size(); ++index)
        sameExpression(actual->args[index], expected->args[index]);
}
void valid(const std::string &source, const std::function<void()> &configure, const ExpectedExpression &expected) {
    reset();
    configure();
    const auto tokens = aurora::lex(source, "forged.au");
    std::size_t position = 0;
    const auto actual = aurora::parseHostedExpression(tokens, position, Stop::Semicolon);
    sameExpression(actual, expected(tokens));
    require(position == static_cast<std::size_t>(result[3]) && created == 1 && parsed == 1 && released == 1 &&
                read == count && edgeRead == edgeCount && typeRead == typeCount,
            "valid forged control lost cursor, record reads or exact cleanup");
    require(std::all_of(capturedInput.begin() + 11,
                        capturedInput.end(),
                        [](auto word) {
                            return word == 0;
                        }),
            "ordinary expression did not copy an empty TypeContext");
    ++cases;
}
void validConstructor(const std::string &source,
                      const std::function<void()> &configure,
                      const ExpectedExpression &expected,
                      std::size_t consumed) {
    reset();
    configure();
    const auto tokens = aurora::lex(source, "forged.au");
    std::size_t position = 0;
    const auto actual = aurora::parseHostedExpression(tokens, position, Stop::ConstructorBraces);
    sameExpression(actual, expected(tokens));
    require(position == consumed && position == static_cast<std::size_t>(result[3]) && created == 1 && parsed == 1 &&
                released == 1 && read == count && edgeRead == edgeCount && typeRead == typeCount &&
                tokens[consumed - 1].text == "}" &&
                result[4] == static_cast<std::int64_t>(tokens[consumed].span.begin.offset),
            "constructor control lost its cursor, original field token or exact cleanup");
    ++cases;
}
void invalid(const std::string &label,
             const std::function<void()> &mutate,
             const std::string &source = "1+2;",
             Stop stop = Stop::Semicolon) {
    reset();
    mutate();
    const auto tokens = aurora::lex(source, "forged.au");
    std::size_t position = 0;
    bool rejected = false;
    try {
        static_cast<void>(aurora::parseHostedExpression(tokens, position, stop));
    } catch (const aurora::Error &error) {
        rejected = error.diagnostic.code == aurora::DiagnosticCode::Internal &&
                   error.diagnostic.message == "hosted parser returned an invalid result";
    }
    require(rejected && position == 0 && created == 1 && parsed == 1 && released == 1,
            label + ": forged result escaped or changed cursor/cleanup");
    require(tokens.front().span.source->text == source, label + ": immutable source changed");
    ++cases;
}
void contextControl(
    const std::string &label,
    const std::string &expression,
    const std::function<void(aurora::hosted_parser::Context &, std::vector<aurora::Token> &)> &configure,
    const std::function<void()> &prepare,
    bool accepted,
    bool beforeArena = false,
    const std::string &prefix = "T U N;\n") {
    reset();
    prepare();
    auto tokens = aurora::lex(prefix + expression, "context.au");
    aurora::hosted_parser::Context context;
    context.typeParameters = {tokens[0]};
    configure(context, tokens);
    result[4] += static_cast<std::int64_t>(prefix.size());
    std::size_t position = 4;
    bool rejected = false;
    aurora::ExpressionPtr actual;
    try {
        actual = aurora::parseHostedExpression(tokens, position, Stop::Semicolon, context);
    } catch (const aurora::Error &error) {
        rejected = error.diagnostic.code == aurora::DiagnosticCode::Internal &&
                   error.diagnostic.message == "hosted parser returned an invalid result";
    }
    if (accepted) {
        require(!rejected && actual && position == 4 + static_cast<std::size_t>(result[3]) && created == 1 &&
                    parsed == 1 && released == 1 && typeRead == typeCount,
                label + ": valid copied context changed cursor/read/cleanup");
        std::array<std::uint64_t, 7> expected{};
        if (!context.typeParameters.empty()) {
            expected[0] = context.typeParameters[0].span.begin.offset;
            expected[1] = context.typeParameters[0].span.end.offset;
            expected[6] = context.functionTemplate ? 2 : 1;
        }
        if (context.typeParameters.size() == 2) {
            expected[2] = context.typeParameters[1].span.begin.offset;
            expected[3] = context.typeParameters[1].span.end.offset;
        }
        if (!context.capacityParameters.empty()) {
            expected[4] = context.capacityParameters[0].span.begin.offset;
            expected[5] = context.capacityParameters[0].span.end.offset;
        }
        require(std::equal(expected.begin(), expected.end(), capturedInput.begin() + 11),
                label + ": Context's seven copied words or mode changed");
        if (expression == "size_of(T);")
            require(actual->reflectedType.kind == aurora::TypeKind::Parameter &&
                        actual->reflectedType.className == "T" && !actual->reflectedType.resolvedClass,
                    "captured parameter gained a nominal identity or changed spelling");
        if (expression == "size_of(array<T,N>);")
            require(actual->reflectedType.isArray() && actual->reflectedType.elementParameter == "T" &&
                        actual->reflectedType.lengthParameter == "N" && actual->reflectedType.length == 0,
                    "captured array element or length parameter changed");
        if (context.functionTemplate && context.typeParameters.size() == 1 && expression.starts_with("f<"))
            require(actual->templateArguments.size() == 1 &&
                        actual->templateArguments[0].type == aurora::TypeKind::Parameter &&
                        actual->templateArguments[0].className == context.typeParameters[0].text &&
                        !actual->templateArguments[0].resolvedClass,
                    "captured call parameter gained a nominal identity or changed its spelling");
        if (expression == "f<T,U>();")
            require(actual->templateArguments.size() == 2 &&
                        actual->templateArguments[0].type == aurora::TypeKind::Parameter &&
                        actual->templateArguments[0].className == "T" &&
                        actual->templateArguments[1].type == aurora::TypeKind::Parameter &&
                        actual->templateArguments[1].className == "U",
                    "function-template parameters were not imported from their distinct context spans");
    } else {
        const auto calls = beforeArena ? 0 : 1;
        require(rejected && position == 4 && created == calls && parsed == calls && released == calls,
                label + ": invalid context/typed graph escaped or changed cursor/cleanup");
    }
    ++cases;
}
void diagnostic(const std::string &source,
                Status status,
                std::size_t ordinal,
                aurora::DiagnosticCode code,
                const std::string &message,
                Stop stop = Stop::Semicolon,
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
void contextControls() {
    const auto parameterFixture = [] {
        typedFixture("size_of(T);", {{wire(TypeKind::Parameter), 2, 2, 4, -1, -1, 0, 2}});
    };
    const auto arrayParameterFixture = [] {
        typedFixture("size_of(array<T,N>);",
                     {{wire(TypeKind::Parameter), 4, 4, 8, -1, -1, -1, 0},
                      {wire(TypeKind::LengthParameter), 6, 6, 12, -1, -1, -1, 0},
                      {wire(TypeKind::Array), 2, 2, 14, 0, 1, 0, 2}});
    };
    contextControl(
        "ordinary mode zeroes all seven context words",
        "size_of(i64);",
        [](auto &context, auto &) {
            context.typeParameters.clear();
        },
        [] {
            reflectedFixture();
        },
        true);
    contextControl(
        "captured class parameter",
        "size_of(T);",
        [](auto &, auto &) {
        },
        parameterFixture,
        true);
    contextControl(
        "two captured class parameters",
        "size_of(T);",
        [](auto &context, auto &tokens) {
            context.typeParameters.push_back(tokens[1]);
        },
        parameterFixture,
        true);
    contextControl(
        "captured function parameter",
        "size_of(T);",
        [](auto &context, auto &) {
            context.functionTemplate = true;
        },
        parameterFixture,
        true);
    contextControl(
        "captured capacity parameter",
        "size_of(array<T,N>);",
        [](auto &context, auto &tokens) {
            context.capacityParameters = {tokens[2]};
        },
        arrayParameterFixture,
        true);
    contextControl(
        "two function type arguments",
        "f<T,U>();",
        [](auto &context, auto &tokens) {
            context.typeParameters.push_back(tokens[1]);
            context.functionTemplate = true;
        },
        [] {
            typedFixture("f<T,U>();",
                         {{wire(TypeKind::Parameter), 2, 2, 4, -1, -1, -1, 0},
                          {wire(TypeKind::Parameter), 4, 4, 8, -1, -1, -1, 0},
                          {wire(TypeKind::Named), 0, 0, 10, 0, 1, 0, 1}});
        },
        true);
    for (int mode = 0; mode < 21; ++mode)
        contextControl(
            "invalid context cardinality, mode or captured-token provenance",
            "size_of(T);",
            [=](auto &context, auto &tokens) {
                auto &parameter = context.typeParameters[0];
                switch (mode) {
                case 0:
                    context.typeParameters = {tokens[0], tokens[1], tokens[2]};
                    break;
                case 1:
                    context.capacityParameters = {tokens[1], tokens[2]};
                    break;
                case 2:
                    context.typeParameters.push_back(tokens[1]);
                    context.capacityParameters = {tokens[2]};
                    break;
                case 3:
                    context.typeParameters.clear();
                    context.capacityParameters = {tokens[2]};
                    break;
                case 4:
                    context.capacityParameters = {tokens[2]};
                    context.functionTemplate = true;
                    break;
                case 5:
                    context.typeParameters.clear();
                    context.functionTemplate = true;
                    break;
                case 6:
                    context.typeParameters.push_back(tokens[0]);
                    break;
                case 7:
                    context.capacityParameters = {tokens[0]};
                    break;
                case 8:
                    parameter.span.source =
                        std::make_shared<const aurora::SourceText>("other.au", "T U N;\nsize_of(T);");
                    break;
                case 9:
                    parameter.text = "U";
                    break;
                case 10:
                    parameter.span.end.offset = parameter.span.begin.offset;
                    break;
                case 11:
                    parameter.span.end.offset = tokens.back().span.end.offset;
                    break;
                case 12:
                    parameter = tokens[6];
                    break;
                case 13:
                    ++parameter.span.begin.line;
                    break;
                case 14:
                    ++parameter.span.begin.column;
                    break;
                case 15:
                    ++parameter.span.end.line;
                    break;
                case 16:
                    ++parameter.span.end.column;
                    break;
                case 17:
                    ++parameter.line;
                    break;
                case 18:
                    parameter.span.source.reset();
                    break;
                case 19:
                    parameter = tokens[3];
                    break;
                case 20:
                    parameter.span.begin.offset = 1;
                    parameter.span.end.offset = 2;
                    break;
                }
            },
            parameterFixture,
            false,
            true);
    contextControl(
        "wire parameter must be declared in the captured context",
        "size_of(T);",
        [](auto &context, auto &) {
            context.typeParameters.clear();
        },
        parameterFixture,
        false);
    contextControl(
        "captured parameter cannot be forged into a nominal class",
        "size_of(T);",
        [](auto &, auto &) {
        },
        [] {
            typedFixture("size_of(T);", {{wire(TypeKind::Named), 2, 2, 4, -1, -1, 0, 2}});
        },
        false);
    contextControl(
        "captured type parameter is not a capacity parameter",
        "size_of(array<T,N>);",
        [](auto &context, auto &tokens) {
            context.typeParameters.push_back(tokens[2]);
        },
        arrayParameterFixture,
        false);
    contextControl(
        "class templates cannot carry concrete callee template-ids",
        "f<i64>();",
        [](auto &, auto &) {
        },
        [] {
            templateFixture();
        },
        false);
    contextControl(
        "class templates cannot carry reflected template-ids",
        "size_of(Box<i64>);",
        [](auto &, auto &) {
        },
        [] {
            nestedTemplateFixture(1, true);
        },
        false);
    for (const std::string name : {"int", "void", "char", "float", "double", "new", "delete"}) {
        const auto call = "f<" + name + ">();";
        contextControl(
            "reserved type word is still a legal captured call parameter",
            call,
            [](auto &context, auto &) {
                context.functionTemplate = true;
            },
            [&] {
                templateFixture(call);
                types[0][0] = wire(TypeKind::Parameter);
            },
            true,
            false,
            name + " U N;\n");
        const auto query = "size_of(" + name + ");";
        contextControl(
            "captured parameter cannot bypass reserved reflected-type spelling",
            query,
            [](auto &, auto &) {
            },
            [&] {
                typedFixture(query, {{wire(TypeKind::Parameter), 2, 2, 4, -1, -1, 0, 2}});
            },
            false,
            false,
            name + " U N;\n");
    }
    contextControl(
        "nested dependent call argument remains rejected",
        "f<Box<T>>();",
        [](auto &context, auto &) {
            context.functionTemplate = true;
        },
        [] {
            splitFixture("f<Box<T>>();");
            types[0][0] = wire(TypeKind::Parameter);
        },
        false);
}
void typedDiagnosticControls() {
    diagnostic("size_of(own i64>);",
               Status::ExpectedAngleOpen,
               3,
               DiagnosticCode::UnexpectedToken,
               "expected '<' (found 'i64')");
    diagnostic("size_of(own<i64);",
               Status::ExpectedAngleClose,
               5,
               DiagnosticCode::UnexpectedToken,
               "expected '>' (found ')')");
    diagnostic("size_of(builtin ByteRegion);",
               Status::ExpectedScope,
               3,
               DiagnosticCode::UnexpectedToken,
               "expected '::' (found 'ByteRegion')");
    diagnostic("size_of(array<i64 1>);",
               Status::ExpectedComma,
               5,
               DiagnosticCode::UnexpectedToken,
               "expected ',' (found '1')");
    diagnostic("size_of(builtin::span<u8>);",
               Status::ExpectedConst,
               6,
               DiagnosticCode::UnexpectedToken,
               "expected 'const' (found 'u8')");
    diagnostic("size_of(builtin::span<const i64>);",
               Status::ExpectedU8,
               7,
               DiagnosticCode::UnexpectedToken,
               "expected 'u8' (found 'i64')");
    diagnostic(
        "size_of(own<u64>);", Status::ExpectedI64, 4, DiagnosticCode::UnexpectedToken, "expected 'i64' (found 'u64')");
    diagnostic("size_of(builtin::Unknown);",
               Status::ExpectedArray,
               4,
               DiagnosticCode::UnexpectedToken,
               "expected 'array' (found 'Unknown')");
    diagnostic("size_of(int);",
               Status::ReservedType,
               2,
               DiagnosticCode::UnexpectedToken,
               "unsupported or reserved type spelling (found 'int')");
    diagnostic(
        "size_of(1);", Status::ExpectedType, 3, DiagnosticCode::UnexpectedToken, "expected type name (found ')')");
    diagnostic("f<i64,u8,bool>();",
               Status::TemplateArity,
               6,
               DiagnosticCode::UnexpectedToken,
               "template arguments are limited to one or two types or capacity literals (found 'bool')");
    diagnostic("f<own<i64>>();",
               Status::TemplateArgument,
               2,
               DiagnosticCode::UnexpectedToken,
               "template arguments require scalar, named class or enum types, or capacities "
               "from 1 to 64 (found 'own')");
    diagnostic("f<65>();",
               Status::CapacityArgument,
               3,
               DiagnosticCode::UnexpectedToken,
               "capacity template arguments must be decimal literals from 1 to 64 (found '>')");
    diagnostic("size_of(builtin::OwnedValues<i64>);",
               Status::OwnedElement,
               7,
               DiagnosticCode::UnexpectedToken,
               "owned values require a named concrete copied class (found '>')");
    diagnostic("size_of(array<own<i64>,1>);",
               Status::ArrayElement,
               8,
               DiagnosticCode::UnexpectedToken,
               "array elements require i64, u64, u8, bool or a concrete copied class (found ',')");
    diagnostic("size_of(array<u8,0>);",
               Status::ArrayLength,
               7,
               DiagnosticCode::UnexpectedToken,
               "array length requires a decimal integer literal between 1 and 4096 (found '>')");
    diagnostic("size_of(array<Box,65>);",
               Status::ClassArrayLength,
               8,
               DiagnosticCode::UnexpectedToken,
               "class-element array capacity must be between 1 and 64 (found ')')");
    diagnostic("size_of(Box<i64>>);",
               Status::ExpectedClose,
               5,
               DiagnosticCode::UnexpectedToken,
               "expected ')' (found '>')",
               Stop::Semicolon,
               true);
    diagnostic(nestedTemplateSource(5, true),
               Status::TemplateNestingLimit,
               11,
               DiagnosticCode::NestingLimit,
               "template-id nesting exceeds 4");
    diagnostic(nestedTemplateSource(6, false),
               Status::CallTemplateNestingLimit,
               11,
               DiagnosticCode::NestingLimit,
               "template-id nesting exceeds 5");
    std::string deep = "size_of(";
    for (int depth = 0; depth < 64; ++depth)
        deep += "array<";
    deep += "i64";
    for (int depth = 0; depth < 64; ++depth)
        deep += ",1>";
    deep += ");";
    diagnostic(deep, Status::TypeNestingLimit, 130, DiagnosticCode::NestingLimit, "type nesting exceeds 64");
    for (const auto adjustment : {-1, 2, 3})
        invalid(
            "split-token diagnostic requires exactly the second byte",
            [=] {
                const auto tokens = aurora::lex("size_of(Box<i64>>);");
                count = 0;
                result = {wire(Status::ExpectedClose),
                          -1,
                          0,
                          5,
                          static_cast<std::int64_t>(tokens[5].span.begin.offset) + adjustment};
            },
            "size_of(Box<i64>>);");
    invalid(
        "successful result cannot end inside a split token",
        [] {
            splitFixture();
            result[3] = 5;
            result[4] = 10;
        },
        "f<Box<i64>>();");
    invalid(
        "single greater token cannot borrow a second-byte diagnostic",
        [] {
            const auto tokens = aurora::lex("size_of(Box<i64>);");
            count = 0;
            result = {
                wire(Status::ExpectedClose), -1, 0, 5, static_cast<std::int64_t>(tokens[5].span.begin.offset) + 1};
        },
        "size_of(Box<i64>);");
    for (const std::size_t ordinal : {0U, 1U, 2U, 3U, 4U, 5U, 6U, 7U, 8U}) {
        reset();
        splitFixture();
        auto tokens = aurora::lex("f<Box<i64>>();", "type-provenance.au");
        tokens[ordinal].span.source = std::make_shared<const aurora::SourceText>("foreign.au", "f<Box<i64>>();");
        std::size_t position = 0;
        bool rejected = false;
        try {
            static_cast<void>(aurora::parseHostedExpression(tokens, position, Stop::Semicolon));
        } catch (const aurora::Error &error) {
            rejected = error.diagnostic.code == aurora::DiagnosticCode::Internal &&
                       error.diagnostic.message == "hosted parser returned an invalid result";
        }
        require(rejected && position == 0 && created == 1 && parsed == 1 && released == 1,
                "typed name, child, delimiter, split closer or end token lost original-source provenance");
        ++cases;
    }
}
void contextDispatchControls() {
    const std::string functionSource = "export module hooks;template<Scalar T>auto f(T unused)->i64{"
                                       "i64 x=1;x=1;1;static_assert(1);if(1){}while(1){}return 1;}";
    reset();
    hookControl = true;
    const auto functionTokens = aurora::lex(functionSource, "context-hooks.au");
    const auto function = aurora::Parser(functionTokens).parse();
    hookControl = false;
    const auto typeToken = std::find_if(functionTokens.begin(), functionTokens.end(), [](const auto &token) {
        return token.text == "T";
    });
    require(typeToken != functionTokens.end() && function.functionTemplates.size() == 1 && parsed == 8 &&
                created == 8 && released == 8 && hookContexts.size() == 8,
            "function-template statement entry bypassed hosted dispatch");
    const std::array<std::uint64_t, 7> expectedFunction{
        typeToken->span.begin.offset, typeToken->span.end.offset, 0, 0, 0, 0, 2};
    for (const auto &context : hookContexts)
        require(context == expectedFunction, "a statement entry lost its captured function-template context");
    ++cases;

    reset();
    hookControl = true;
    const auto classTokens = aurora::lex(
        "export module hooks;template<Scalar T,i64 N>class Hook{array<T,N> value;array<T,N> zero;i64 scalar;"
        "public:Hook():value{1},zero{},scalar(1){}auto get()->i64{return 1;}};",
        "context-hooks.au");
    const auto definition = aurora::Parser(classTokens).parse();
    hookControl = false;
    const auto capturedType = std::find_if(classTokens.begin(), classTokens.end(), [](const auto &token) {
        return token.text == "T";
    });
    const auto capturedCapacity = std::find_if(classTokens.begin(), classTokens.end(), [](const auto &token) {
        return token.text == "N";
    });
    require(capturedType != classTokens.end() && capturedCapacity != classTokens.end() &&
                definition.templates.size() == 1 && created == 4 && parsed == 4 && released == 4 &&
                hookStops ==
                    std::vector<Stop>{
                        Stop::ConstructorBraces, Stop::ConstructorBraces, Stop::CloseParenthesis, Stop::Semicolon},
            "class-template initializer or method entry bypassed hosted dispatch");
    const std::array<std::uint64_t, 7> expectedClass{capturedType->span.begin.offset,
                                                     capturedType->span.end.offset,
                                                     0,
                                                     0,
                                                     capturedCapacity->span.begin.offset,
                                                     capturedCapacity->span.end.offset,
                                                     1};
    for (const auto &context : hookContexts)
        require(context == expectedClass, "constructor/method entry lost captured class-template/capacity context");
    ++cases;

    for (const bool functionTemplate : {false, true}) {
        reset();
        const std::string prefix =
            functionTemplate ? "export module hooks;template<Scalar T>auto f()->i64{return "
                             : "export module hooks;template<Scalar T>class Hook{public:auto f()->i64{return ";
        const std::string expression = functionTemplate ? "g<Box<T>>();" : "g<i64>();";
        const auto tokens = aurora::lex(prefix + expression + (functionTemplate ? "}" : "}};"), "context-hooks.au");
        const std::string message = functionTemplate
                                        ? "nested dependent template arguments are not supported (found '>>')"
                                        : "template-id references inside template definitions are not supported "
                                          "(found '<')";
        const auto &expected = tokens[functionTemplate ? 22 : 23].span;
        const auto expressionTokens = aurora::lex(expression);
        const std::int64_t ordinal = functionTemplate ? 5 : 1;
        result = {wire(functionTemplate ? Status::NestedDependent : Status::TemplateContext),
                  -1,
                  0,
                  ordinal,
                  static_cast<std::int64_t>(expressionTokens[static_cast<std::size_t>(ordinal)].span.begin.offset)};
        count = 0;
        hookControl = hookPrepared = true;
        bool rejected = false;
        try {
            static_cast<void>(aurora::Parser(tokens).parse());
        } catch (const aurora::Error &error) {
            const auto &span = error.diagnostic.span;
            rejected = error.diagnostic.code == DiagnosticCode::UnexpectedToken &&
                       error.diagnostic.message == message && span.source == expected.source &&
                       span.begin.offset == expected.begin.offset && span.begin.line == expected.begin.line &&
                       span.begin.column == expected.begin.column && span.end.offset == expected.end.offset &&
                       span.end.line == expected.end.line && span.end.column == expected.end.column;
        }
        hookControl = false;
        require(rejected && created == 1 && parsed == 1 && released == 1 &&
                    capturedInput[17] == (functionTemplate ? 2U : 1U),
                "context diagnostic changed its specified message/provenance or escaped direct dispatch");
        ++cases;
    }
}
void typedControls() {
    for (const auto kind : {TypeKind::I64, TypeKind::U64, TypeKind::U8, TypeKind::Bool}) {
        const std::string word = kind == TypeKind::I64   ? "i64"
                                 : kind == TypeKind::U64 ? "u64"
                                 : kind == TypeKind::U8  ? "u8"
                                                         : "bool";
        const auto expectedKind = word == "i64"   ? aurora::TypeKind::I64
                                  : word == "u64" ? aurora::TypeKind::U64
                                  : word == "u8"  ? aurora::TypeKind::U8
                                                  : aurora::TypeKind::Bool;
        const auto source = "f<" + word + ">();";
        valid(
            source,
            [&] {
                templateFixture(source);
                types[0][0] = wire(kind);
            },
            [&](const auto &t) {
                return typedNode(expectedNode(t, 0, "call"), {expectedKind});
            });
        const auto query = "size_of(" + word + ");";
        valid(
            query,
            [&] {
                reflectedFixture(query);
                types[0][0] = wire(kind);
            },
            [&](const auto &t) {
                return typedNode(expectedNode(t, 0, "call"), {}, aurora::Type(expectedKind));
            });
    }
    for (const std::string query : {"size_of", "type_id", "field_count"}) {
        const auto source = query + "(pkg::Box);";
        valid(
            source,
            [&] {
                typedFixture(source, {{wire(TypeKind::Named), 2, 4, 8, -1, -1, 0, 2}});
            },
            [&](const auto &t) {
                return typedNode(expectedNode(t, 0, "call"), {}, namedType("pkg::Box"));
            });
    }
    valid(
        "ns::f<i64>();",
        [] {
            typedFixture(
                "ns::f<i64>();",
                {{wire(TypeKind::I64), 4, 4, 8, -1, -1, -1, 0}, {wire(TypeKind::Named), 0, 2, 10, 0, -1, 0, 1}},
                {{wire(NodeKind::Call), 0, -1, 0, 1, 2, 7}});
        },
        [&](const auto &t) {
            return typedNode(qualifiedNode(expectedNode(t, 0, "call"), t, 2, "ns::f"), {aurora::TypeKind::I64});
        });
    valid(
        "Box<i64>{};",
        [] {
            templateFixture("Box<i64>{};");
            records[0][0] = wire(NodeKind::Construct);
        },
        [&](const auto &t) {
            return typedNode(expectedNode(t, 0, "construct"), {aurora::TypeKind::I64});
        });
    for (const std::string capacity : {"1", "64", "00064"}) {
        const auto source = "f<i64," + capacity + ">();";
        valid(
            source,
            [&] {
                typedFixture(source,
                             {{wire(TypeKind::I64), 2, 2, 4, -1, -1, -1, 0},
                              {wire(TypeKind::Capacity), 4, 4, 8, -1, -1, -1, 0},
                              {wire(TypeKind::Named), 0, 0, 10, 0, 1, 0, 1}});
            },
            [&](const auto &t) {
                return typedNode(expectedNode(t, 0, "call"),
                                 {aurora::TypeKind::I64, aurora::TemplateArgument::capacity(capacity == "1" ? 1 : 64)});
            });
    }
    valid(
        "f<Box<i64>>();",
        [] {
            splitFixture();
        },
        [&](const auto &t) {
            return typedNode(expectedNode(t, 0, "call"), {namedArgument("Box", {aurora::TypeKind::I64})});
        });
    valid(
        "f<Box<i64> >();",
        [] {
            splitFixture("f<Box<i64> >();");
            types.back()[3] = 12;
        },
        [&](const auto &t) {
            return typedNode(expectedNode(t, 0, "call"), {namedArgument("Box", {aurora::TypeKind::I64})});
        });
    valid(
        "size_of<Box<i64>>(Box<u8>);",
        [] {
            typedFixture("size_of<Box<i64>>(Box<u8>);",
                         {{wire(TypeKind::I64), 4, 4, 8, -1, -1, -1, 0},
                          {wire(TypeKind::Named), 2, 2, 10, 0, -1, -1, 0},
                          {wire(TypeKind::Named), 0, 0, 11, 1, -1, 0, 1},
                          {wire(TypeKind::U8), 9, 9, 18, -1, -1, -1, 0},
                          {wire(TypeKind::Named), 7, 7, 20, 3, -1, 0, 2}});
        },
        [&](const auto &t) {
            return typedNode(expectedNode(t, 0, "call"),
                             {namedArgument("Box", {aurora::TypeKind::I64})},
                             namedType("Box", {aurora::TypeKind::U8}));
        });
    for (const std::string source : {"pkg::size_of(\"Box<i64>\");", "pkg::type_id(\"x\");", "pkg::field_count(\"x\");"})
        valid(
            source,
            [&] {
                fixture(source,
                        {{wire(NodeKind::Literal), 4, -1, -1, 1, 4, 4}, {wire(NodeKind::Call), 0, 0, 1, 2, 2, 5}},
                        {{0, -1, 1, 2, -1}});
            },
            [&](const auto &t) {
                return qualifiedNode(
                    expectedNode(t, 0, "call", {expectedNode(t, 4, "byte_string")}), t, 2, "pkg::" + t[2].text);
            });
    valid(
        "\"size_of(Box<i64>)\";",
        [] {
            fixture("\"size_of(Box<i64>)\";", {{wire(NodeKind::Literal), 0, -1, -1, 1, 0, 0}});
        },
        [&](const auto &t) {
            return expectedNode(t, 0, "byte_string");
        });
    valid(
        "a>>b;",
        [] {
            fixture("a>>b;",
                    {{wire(NodeKind::Name), 0, -1, -1, 1, 0, 0},
                     {wire(NodeKind::Name), 2, -1, -1, 1, 2, 2},
                     {wire(NodeKind::Binary), 1, 0, 1, 2, 1, 1}});
        },
        [&](const auto &t) {
            return expectedNode(t, 1, "binary", {expectedNode(t, 0, "name"), expectedNode(t, 2, "name")});
        });
    for (const auto kind : {TypeKind::Own, TypeKind::Ref, TypeKind::MutRef}) {
        const auto expectedType = kind == TypeKind::Own   ? aurora::Type::Own
                                  : kind == TypeKind::Ref ? aurora::Type::Ref
                                                          : aurora::Type::MutRef;
        const auto source = std::string("size_of(") +
                            (kind == TypeKind::Own   ? "own"
                             : kind == TypeKind::Ref ? "ref"
                                                     : "mutref") +
                            "<i64>);";
        valid(
            source,
            [&] {
                typedFixture(source, {{wire(kind), 2, 2, 10, -1, -1, 0, 2}});
            },
            [&](const auto &t) {
                return typedNode(expectedNode(t, 0, "call"), {}, expectedType);
            });
    }
    valid(
        "size_of(builtin::span<const u8>);",
        [] {
            typedFixture("size_of(builtin::span<const u8>);", {{wire(TypeKind::ByteSpan), 2, 4, 16, -1, -1, 0, 2}});
        },
        [&](const auto &t) {
            return typedNode(expectedNode(t, 0, "call"), {}, aurora::Type::ByteSpan);
        });
    for (const auto &[name, expectedType] : std::vector<std::pair<std::string, aurora::Type>>{
             {"ByteRegion", aurora::Type::ByteRegion},
             {"OwnedBytes", aurora::Type::OwnedBytes},
             {"ConsoleSession", aurora::Type::ConsoleSession},
             {"DisplaySession", aurora::Type::DisplaySession},
             {"IommuEventSession", aurora::Type::IommuEventSession},
             {"ConsolePutResult", builtinEnum("__au_console_put_result", "builtin::ConsolePutResult")},
             {"ConsoleCompletion", builtinEnum("__au_console_completion", "builtin::ConsoleCompletion")},
             {"DisplayPutResult", builtinEnum("__au_display_put_result", "builtin::DisplayPutResult")},
             {"DisplayCompletion", builtinEnum("__au_display_completion", "builtin::DisplayCompletion")},
             {"EventPollResult", builtinEnum("__au_event_poll_result", "builtin::EventPollResult")},
             {"EventAckResult", builtinEnum("__au_event_ack_result", "builtin::EventAckResult")},
             {"EventIntakeCompletion", builtinEnum("__au_event_intake_completion", "builtin::EventIntakeCompletion")},
             {"ConsoleSample", builtinClass("__au_console_sample", "builtin::ConsoleSample")},
             {"IommuEventSample", builtinClass("__au_iommu_event_sample", "builtin::IommuEventSample")}}) {
        const auto source = "size_of(builtin::" + name + ");";
        const bool copiedClass = name == "ConsoleSample" || name == "IommuEventSample";
        valid(
            source,
            [&] {
                typedFixture(source,
                             {{wire(copiedClass ? TypeKind::BuiltinClass : TypeKind::Builtin), 2, 4, 8, -1, -1, 0, 2}});
            },
            [&](const auto &t) {
                return typedNode(expectedNode(t, 0, "call"), {}, expectedType);
            });
        invalid(
            "closed builtin alias has the wrong nominal category",
            [&] {
                typedFixture(source,
                             {{wire(copiedClass ? TypeKind::Builtin : TypeKind::BuiltinClass), 2, 4, 8, -1, -1, 0, 2}});
            },
            source);
    }
    for (const std::string length : {"1", "4096"}) {
        const auto source = "size_of(array<u8," + length + ">);";
        valid(
            source,
            [&] {
                typedFixture(source,
                             {{wire(TypeKind::U8), 4, 4, 8, -1, -1, -1, 0},
                              {wire(TypeKind::Capacity), 6, 6, 12, -1, -1, -1, 0},
                              {wire(TypeKind::Array), 2, 2, 14, 0, 1, 0, 2}});
            },
            [&](const auto &t) {
                return typedNode(
                    expectedNode(t, 0, "call"), {}, aurora::Type::array(aurora::Type::U8, length == "1" ? 1 : 4096));
            });
    }
    valid(
        "size_of(builtin::array<Box,64>);",
        [] {
            typedFixture("size_of(builtin::array<Box,64>);",
                         {{wire(TypeKind::Named), 6, 6, 12, -1, -1, -1, 0},
                          {wire(TypeKind::Capacity), 8, 8, 16, -1, -1, -1, 0},
                          {wire(TypeKind::Array), 2, 4, 18, 0, 1, 0, 2}});
        },
        [&](const auto &t) {
            return typedNode(expectedNode(t, 0, "call"), {}, aurora::Type::array(namedType("Box"), 64));
        });
    valid(
        "size_of(builtin::OwnedValues<Box>);",
        [] {
            typedFixture("size_of(builtin::OwnedValues<Box>);",
                         {{wire(TypeKind::Named), 6, 6, 12, -1, -1, -1, 0},
                          {wire(TypeKind::OwnedValues), 2, 4, 14, 0, -1, 0, 2}});
        },
        [&](const auto &t) {
            return typedNode(expectedNode(t, 0, "call"), {}, aurora::Type::ownedValues(namedType("Box")));
        });
    for (const auto &[name, expectedType] : std::vector<std::pair<std::string, aurora::Type>>{
             {"ConsoleSample", builtinClass("__au_console_sample", "builtin::ConsoleSample")},
             {"IommuEventSample", builtinClass("__au_iommu_event_sample", "builtin::IommuEventSample")}}) {
        const auto array = "size_of(array<builtin::" + name + ",64>);";
        valid(
            array,
            [&] {
                typedFixture(array,
                             {{wire(TypeKind::BuiltinClass), 4, 6, 12, -1, -1, -1, 0},
                              {wire(TypeKind::Capacity), 8, 8, 16, -1, -1, -1, 0},
                              {wire(TypeKind::Array), 2, 2, 18, 0, 1, 0, 2}});
            },
            [&](const auto &t) {
                return typedNode(expectedNode(t, 0, "call"), {}, aurora::Type::array(expectedType, 64));
            });
        const auto source = "size_of(builtin::OwnedValues<builtin::" + name + ">);";
        valid(
            source,
            [&] {
                typedFixture(source,
                             {{wire(TypeKind::BuiltinClass), 6, 8, 16, -1, -1, -1, 0},
                              {wire(TypeKind::OwnedValues), 2, 4, 18, 0, -1, 0, 2}});
            },
            [&](const auto &t) {
                return typedNode(expectedNode(t, 0, "call"), {}, aurora::Type::ownedValues(expectedType));
            });
    }

    const auto independentRoots = [] {
        typedFixture("f<i64>()+g<u8>();",
                     {{wire(TypeKind::I64), 2, 2, 4, -1, -1, -1, 0},
                      {wire(TypeKind::Named), 0, 0, 6, 0, -1, 0, 1},
                      {wire(TypeKind::U8), 9, 9, 18, -1, -1, -1, 0},
                      {wire(TypeKind::Named), 7, 7, 20, 2, -1, 7, 1}},
                     {{wire(NodeKind::Call), 0, -1, 0, 1, 0, 5},
                      {wire(NodeKind::Call), 7, -1, 0, 1, 7, 12},
                      {wire(NodeKind::Binary), 6, 0, 1, 2, 6, 6}});
    };
    valid("f<i64>()+g<u8>();", independentRoots, [&](const auto &t) {
        return expectedNode(t,
                            6,
                            "binary",
                            {typedNode(expectedNode(t, 0, "call"), {aurora::TypeKind::I64}),
                             typedNode(expectedNode(t, 7, "call"), {aurora::TypeKind::U8})});
    });
    invalid(
        "distinct callee roots cannot share a type child",
        [&] {
            independentRoots();
            types[3][4] = 0;
        },
        "f<i64>()+g<u8>();");
    invalid(
        "distinct roots cannot borrow another owner's token",
        [&] {
            independentRoots();
            types[3][6] = 0;
        },
        "f<i64>()+g<u8>();");
    invalid(
        "child source tokens cannot be reused by separate type subtrees",
        [&] {
            independentRoots();
            types[2][0] = wire(TypeKind::I64);
            types[2][1] = types[2][2] = 2;
            types[2][3] = 4;
        },
        "f<i64>()+g<u8>();");
    std::string deepSource = "size_of(";
    for (int depth = 0; depth < 64; ++depth)
        deepSource += "array<";
    deepSource += "i64";
    for (int depth = 0; depth < 64; ++depth)
        deepSource += ",1>";
    deepSource += ");";
    invalid(
        "untrusted type forest cannot exceed 64 before recursive host-value import",
        [&] {
            std::vector<TypeWords> syntax{{wire(TypeKind::I64), 130, 130, 260, -1, -1, -1, 0}};
            std::int64_t child = 0;
            for (std::int64_t level = 0; level < 64; ++level) {
                const auto token = 128 - level * 2, length = 132 + level * 3, close = length + 1;
                const auto capacity = static_cast<std::int64_t>(syntax.size());
                syntax.push_back({wire(TypeKind::Capacity), length, length, length * 2, -1, -1, -1, 0});
                syntax.push_back({wire(TypeKind::Array),
                                  token,
                                  token,
                                  close * 2,
                                  child,
                                  capacity,
                                  level == 63 ? 0 : -1,
                                  level == 63 ? 2 : 0});
                child = capacity + 1;
            }
            typedFixture(deepSource, std::move(syntax));
        },
        deepSource);

    for (const auto countValue : {-1LL, 7LL, std::numeric_limits<long long>::max()})
        invalid(
            "type count is negative or exceeds consumed token capacity",
            [=] {
                templateFixture();
                typeCount = countValue;
            },
            "f<i64>();");
    for (const auto kind : {-1LL, 0LL, static_cast<long long>(wire(TypeKind::BuiltinClass) + 1)})
        invalid(
            "type kind is outside the closed wire enum",
            [=] {
                templateFixture();
                types[0][0] = kind;
            },
            "f<i64>();");
    for (const auto field : {1, 2, 3, 4, 5, 6, 7})
        for (const auto value : {-2LL, std::numeric_limits<long long>::max()})
            invalid(
                "type word outside its bounded domain",
                [=] {
                    templateFixture();
                    types[0][static_cast<std::size_t>(field)] = value;
                },
                "f<i64>();");
    for (const auto child : {0, 1, 2})
        invalid(
            "type child must precede its parent",
            [=] {
                templateFixture();
                types[0][4] = child;
            },
            "f<i64>();");
    invalid(
        "type parent must follow child",
        [] {
            templateFixture();
            std::swap(types[0], types[1]);
            types[0][4] = 1;
        },
        "f<i64>();");
    invalid(
        "type child cannot be shared by siblings",
        [] {
            typedFixture("f<i64,u64>();",
                         {{wire(TypeKind::I64), 2, 2, 4, -1, -1, -1, 0},
                          {wire(TypeKind::U64), 4, 4, 8, -1, -1, -1, 0},
                          {wire(TypeKind::Named), 0, 0, 10, 0, 0, 0, 1}});
        },
        "f<i64,u64>();");
    invalid(
        "orphan type record cannot remain outside the forest",
        [] {
            templateFixture();
            types.push_back({wire(TypeKind::I64), 2, 2, 4, -1, -1, -1, 0});
            ++typeCount;
        },
        "f<i64>();");
    invalid(
        "rootless type forest cannot replace a callee root",
        [] {
            templateFixture();
            types[1][6] = -1;
            types[1][7] = 0;
        },
        "f<i64>();");
    invalid(
        "duplicate same-role roots cannot name one owner",
        [] {
            templateFixture();
            types.push_back(types[1]);
            ++typeCount;
        },
        "f<i64>();");
    invalid(
        "type child cannot also be an independently owned reflected root",
        [] {
            templateFixture();
            types[0][6] = 0;
            types[0][7] = 2;
        },
        "f<i64>();");
    invalid(
        "callee root must have a template argument",
        [] {
            templateFixture();
            types[1][4] = -1;
        },
        "f<i64>();");
    invalid(
        "callee root must have Named kind",
        [] {
            templateFixture();
            types[1][0] = wire(TypeKind::Array);
        },
        "f<i64>();");
    for (const auto owner : {-1, 1, 2, 5})
        invalid(
            "callee root owner must match its name-start token",
            [=] {
                templateFixture();
                types[1][6] = owner;
            },
            "f<i64>();");
    invalid(
        "root role cannot be transferred from callee to reflection",
        [] {
            templateFixture();
            types[1][7] = 2;
        },
        "f<i64>();");
    invalid(
        "reflected root cannot be attached to a name node",
        [] {
            reflectedFixture();
            records[0][0] = wire(NodeKind::Name);
        },
        "size_of(i64);");
    invalid(
        "reflected root cannot be attached to a construct",
        [] {
            reflectedFixture("size_of{i64};");
            records[0][0] = wire(NodeKind::Construct);
        },
        "size_of{i64};");
    invalid(
        "reflected root requires an unqualified query call",
        [] {
            reflectedFixture("f(i64);");
        },
        "f(i64);");
    invalid(
        "query call must carry exactly one reflected root",
        [] {
            reflectedFixture();
            types.clear();
            typeCount = 0;
        },
        "size_of(i64);");
    invalid(
        "unused reflected root must not survive token coverage",
        [] {
            reflectedFixture();
            types[0][6] = 1;
        },
        "size_of(i64);");
    invalid(
        "byte string is not a reflected type name",
        [] {
            typedFixture("size_of(\"i64\");", {{wire(TypeKind::Named), 2, 2, 4, -1, -1, 0, 2}});
        },
        "size_of(\"i64\");");
    invalid(
        "qualified query spelling does not acquire reflection syntax",
        [] {
            typedFixture("pkg::size_of(i64);",
                         {{wire(TypeKind::I64), 4, 4, 8, -1, -1, 0, 2}},
                         {{wire(NodeKind::Call), 0, -1, 0, 1, 2, 5}});
        },
        "pkg::size_of(i64);");
    invalid(
        "scalar cannot be forged as a nominal template argument",
        [] {
            templateFixture();
            types[0][0] = wire(TypeKind::Named);
        },
        "f<i64>();");
    invalid(
        "scalar kind must match original spelling",
        [] {
            templateFixture();
            types[0][0] = wire(TypeKind::U64);
        },
        "f<i64>();");
    invalid(
        "type name cannot skip an interior qualification token",
        [] {
            typedFixture("size_of(pkg::Box);", {{wire(TypeKind::Named), 2, 2, 8, -1, -1, 0, 2}});
        },
        "size_of(pkg::Box);");
    invalid(
        "success cannot omit template syntax records",
        [] {
            templateFixture();
            types.clear();
            typeCount = 0;
        },
        "f<i64>();");
    for (const auto close : {10, 12, 13})
        invalid(
            "split closer requires exact first/second half ownership",
            [=] {
                splitFixture();
                types[2][3] = close;
            },
            "f<Box<i64>>();");
    invalid(
        "duplicate second half cannot close both parent and child",
        [] {
            splitFixture();
            types[1][3] = 11;
        },
        "f<Box<i64>>();");
    invalid(
        "unsplit greater token cannot have a second half",
        [] {
            templateFixture();
            types[1][3] = 7;
        },
        "f<i64>();");
    invalid(
        "template success cannot leave one half of shift token unclaimed",
        [] {
            templateFixture("f<i64>>();");
        },
        "f<i64>>();");
    invalid(
        "whole shift operator cannot share its token with type halves",
        [] {
            splitFixture("f<Box<i64>>();");
            types[0][1] = types[0][2] = 5;
            types[0][3] = 10;
        },
        "f<Box<i64>>();");
    invalid(
        "a template child cannot skip a comma-delimited source argument",
        [] {
            typedFixture(
                "f<i64,u8>();",
                {{wire(TypeKind::I64), 2, 2, 4, -1, -1, -1, 0}, {wire(TypeKind::Named), 0, 0, 10, 0, -1, 0, 1}});
        },
        "f<i64,u8>();");
    invalid(
        "a type root cannot extend across its query close",
        [] {
            reflectedFixture();
            types[0][3] = 6;
        },
        "size_of(i64);");

    for (const std::string capacity : {"0", "65", "4097", "0xff", "1u64", "999999999999999999999999999"}) {
        const auto source = "f<" + capacity + ">();";
        invalid(
            "template capacity must preserve decimal range 1..64",
            [&] {
                templateFixture(source);
                types[0][0] = wire(TypeKind::Capacity);
            },
            source);
    }
    for (const std::string length : {"0", "4097", "0xff", "1u64"}) {
        const auto source = "size_of(array<u8," + length + ">);";
        invalid(
            "array length must preserve decimal range 1..4096",
            [&] {
                typedFixture(source,
                             {{wire(TypeKind::U8), 4, 4, 8, -1, -1, -1, 0},
                              {wire(TypeKind::Capacity), 6, 6, 12, -1, -1, -1, 0},
                              {wire(TypeKind::Array), 2, 2, 14, 0, 1, 0, 2}});
            },
            source);
    }
    invalid(
        "class array capacity is independently limited to 64",
        [] {
            typedFixture("size_of(array<Box,65>);",
                         {{wire(TypeKind::Named), 4, 4, 8, -1, -1, -1, 0},
                          {wire(TypeKind::Capacity), 6, 6, 12, -1, -1, -1, 0},
                          {wire(TypeKind::Array), 2, 2, 14, 0, 1, 0, 2}});
        },
        "size_of(array<Box,65>);");
    invalid(
        "OwnedValues element must be a concrete copied class",
        [] {
            typedFixture(
                "size_of(builtin::OwnedValues<i64>);",
                {{wire(TypeKind::I64), 6, 6, 12, -1, -1, -1, 0}, {wire(TypeKind::OwnedValues), 2, 4, 14, 0, -1, 0, 2}});
        },
        "size_of(builtin::OwnedValues<i64>);");
    invalid(
        "builtin result enum is not a copied array class",
        [] {
            typedFixture("size_of(array<builtin::ConsolePutResult,1>);",
                         {{wire(TypeKind::Builtin), 4, 6, 12, -1, -1, -1, 0},
                          {wire(TypeKind::Capacity), 8, 8, 16, -1, -1, -1, 0},
                          {wire(TypeKind::Array), 2, 2, 18, 0, 1, 0, 2}});
        },
        "size_of(array<builtin::ConsolePutResult,1>);");
    for (const bool reflected : {false, true}) {
        const auto limit = reflected ? 4 : 5;
        valid(
            nestedTemplateSource(limit, reflected),
            [&] {
                nestedTemplateFixture(limit, reflected);
            },
            [&](const auto &t) {
                aurora::TemplateArgument argument(aurora::TypeKind::I64);
                for (int level = 1; level < limit; ++level)
                    argument = namedArgument("Box", {argument});
                return reflected ? typedNode(expectedNode(t, 0, "call"), {}, namedType("Box", {argument}))
                                 : typedNode(expectedNode(t, 0, "call"), {argument});
            });
        invalid(
            "template depth exceeds its independent call/reflection allowance",
            [&] {
                nestedTemplateFixture(limit + 1, reflected);
            },
            nestedTemplateSource(limit + 1, reflected));
    }
}
} // namespace

extern "C" void aurora_hosted_parser_create(const void *input, void *output) {
    std::array<std::uint64_t, 2> value{};
    std::memcpy(value.data(), input, sizeof(value));
    require(value[0] != 0 && value[1] == 0, "adapter did not request empty arena with live region");
    arenaAddress = output;
    arenaRegion = value[0];
    // Exercise the newly extended arena's last word and the enclosing owner base.
    std::memcpy(static_cast<unsigned char *>(output) + 160, &arenaCanary, sizeof(arenaCanary));
    ++created;
}
extern "C" void aurora_hosted_parser_parse(void *arena, const void *input, void *output) {
    require(arena == arenaAddress, "parse changed the 168-byte arena address");
    std::memcpy(capturedInput.data(), input, sizeof(capturedInput));
    require(capturedInput[0] == 0 && capturedInput[2] == 0 && capturedInput[3] == 0 && capturedInput[4] == 0 &&
                capturedInput[5] == 0,
            "copied Input144 changed the borrowed source descriptor");
    ++parsed;
    if (hookControl) {
        const auto &value = capturedInput;
        const auto *source = reinterpret_cast<const char *>(value[1]);
        const auto offset = static_cast<std::int64_t>(value[7]);
        const auto lexical = aurora::lex(std::string(source, static_cast<std::size_t>(value[6])), "hook.au");
        const auto token = std::find_if(lexical.begin(), lexical.end(), [&](const auto &item) {
            return item.span.begin.offset == static_cast<std::size_t>(offset);
        });
        require(token != lexical.end() && token + 1 != lexical.end(), "hook cursor is not a source token");
        const auto stop = static_cast<Stop>(value[10]);
        hookStops.push_back(stop);
        std::array<std::uint64_t, 7> copiedContext{};
        std::copy(capturedInput.begin() + 11, capturedInput.end(), copiedContext.begin());
        hookContexts.push_back(copiedContext);
        if (!hookPrepared) {
            edgeCount = typeCount = 0;
            edges.clear();
            types.clear();
        }
        if (hookPrepared) {
            result[4] += offset;
        } else if (hookUnsupported) {
            result = {wire(Status::Unsupported), -1, 0, 0, offset};
            count = 0;
            records.clear();
        } else if (stop == Stop::ConstructorBraces) {
            require((token + 1)->text == "{", "constructor hook did not start at original field identifier");
            const bool empty = (token + 2)->text == "}";
            const auto consumed = empty ? 3 : 4;
            require((token + consumed - 1)->text == "}", "unexpected constructor hook fixture");
            count = empty ? 1 : 2;
            result = {wire(Status::Success),
                      count - 1,
                      count,
                      consumed,
                      static_cast<std::int64_t>((token + consumed)->span.begin.offset)};
            if (empty)
                records = {{wire(NodeKind::ArrayZero), 0, -1, 0, 1, 0, 2}};
            else {
                records = {{wire(NodeKind::Literal), 2, -1, -1, 1, 2, 2},
                           {wire(NodeKind::ArrayLiteral), 0, 0, 1, 2, 0, 3}};
                edges = {{0, -1, 1, 2, -1}};
                edgeCount = 1;
            }
            if (hookCorrupt)
                records.back()[1] = 1;
        } else {
            result = {wire(Status::Success), 0, 1, 1, static_cast<std::int64_t>((token + 1)->span.begin.offset)};
            count = 1;
            records = {{wire(source[offset] == 'x' ? NodeKind::Name : NodeKind::Literal), 0, -1, -1, 1, 0, 0}};
        }
    }
    std::memcpy(output, result.data(), sizeof(result));
}
extern "C" std::int64_t aurora_hosted_parser_count(const void *) {
    return count;
}
extern "C" void aurora_hosted_parser_read(const void *, std::int64_t index, void *output) {
    require(index >= 0 && static_cast<std::size_t>(index) < records.size(), "adapter requested out-of-range node");
    ++read;
    std::memcpy(output, records[static_cast<std::size_t>(index)].data(), sizeof(NodeWords));
}
extern "C" std::int64_t aurora_hosted_parser_edges(const void *) {
    return edgeCount;
}
extern "C" void aurora_hosted_parser_edge(const void *, std::int64_t index, void *output) {
    require(index >= 0 && static_cast<std::size_t>(index) < edges.size(), "adapter requested out-of-range edge");
    ++edgeRead;
    std::memcpy(output, edges[static_cast<std::size_t>(index)].data(), sizeof(EdgeWords));
}
extern "C" std::int64_t aurora_hosted_parser_types(const void *) {
    return typeCount;
}
extern "C" void aurora_hosted_parser_type(const void *, std::int64_t index, void *output) {
    require(index >= 0 && static_cast<std::size_t>(index) < types.size(), "adapter requested out-of-range type");
    ++typeRead;
    std::memcpy(output, types[static_cast<std::size_t>(index)].data(), sizeof(TypeWords));
}
extern "C" void aurora_hosted_parser_release(void *owner) {
    require(static_cast<unsigned char *>(owner) + 8 == arenaAddress,
            "release did not receive the enclosing 176-byte owner");
    std::uint64_t region = 0, canary = 0;
    std::memcpy(&region, owner, sizeof(region));
    std::memcpy(&canary, static_cast<unsigned char *>(owner) + 168, sizeof(canary));
    require(region == arenaRegion && canary == arenaCanary, "owner region or arena168 boundary was corrupted");
    ++released;
}

int main() {
    try {
        reset();
        const auto tokens = aurora::lex("1+2;", "control.au");
        std::size_t position = 0;
        const auto accepted = aurora::parseHostedExpression(tokens, position, Stop::Semicolon);
        require(accepted && accepted->op == "binary" && accepted->args.size() == 2 && accepted->depth == 2 &&
                    position == 3 && created == 1 && parsed == 1 && read == 3 && released == 1,
                "valid control did not convert and commit exactly once");
        for (const auto status :
             {-1LL, static_cast<long long>(wire(Status::Invalid)), static_cast<long long>(wire(Status::Invalid) + 1)})
            invalid("invalid status", [=] {
                result[0] = status;
            });
        invalid("negative count", [] {
            result[2] = count = -1;
        });
        invalid("count disagreement", [] {
            count = 2;
        });
        invalid("count greater than tokens", [] {
            result[2] = count = 4;
            result[1] = 3;
        });
        for (const auto tokenCount : {-1LL, 0LL, 4LL, 5LL, std::numeric_limits<long long>::max()})
            invalid("invalid token progress", [=] {
                result[3] = tokenCount;
            });
        for (const auto offset : {-1LL, 0LL, 2LL, 5LL, std::numeric_limits<long long>::max()})
            invalid("invalid source progress", [=] {
                result[4] = offset;
            });
        for (const auto root : {-1, 0, 1, 3, -1})
            invalid("invalid root", [=] {
                result[1] = root;
            });
        for (std::size_t field = 1; field < 5; ++field)
            invalid("non-atomic Unsupported result", [=] {
                result = {wire(Status::Unsupported), -1, 0, 0, 0};
                count = 0;
                result[field] = 1;
                if (field == 2)
                    count = 1;
            });
        invalid("error with root", [] {
            result[0] = wire(Status::ExpectedExpression);
        });
        for (const auto kind : std::array<std::int64_t, 6>{-1,
                                                           wire(NodeKind::Invalid),
                                                           wire(NodeKind::Name),
                                                           wire(NodeKind::Unary),
                                                           wire(NodeKind::Binary),
                                                           wire(NodeKind::ArrayZero) + 1})
            invalid("wrong leaf kind", [=] {
                records[0][0] = kind;
            });
        invalid("literal references operator", [] {
            records[0][1] = 1;
        });
        invalid("binary references literal", [] {
            records[2][1] = 0;
        });
        invalid("two literals reuse one source token", [] {
            records[1][1] = 0;
        });
        invalid("binary operands reverse source order", [] {
            records[2][2] = 1;
            records[2][3] = 0;
        });
        for (const auto token : {0, 2})
            invalid("consumed expression reduced to one leaf", [=] {
                result[1] = 0;
                result[2] = count = 1;
                records = {{wire(NodeKind::Literal), token, -1, -1, 1, token, token}};
            });
        invalid(
            "consumed interior tokens omitted",
            [] {
                result[3] = result[4] = 5;
                records[1][1] = records[1][5] = records[1][6] = 4;
            },
            "1+2*3;");
        invalid(
            "unary operand precedes operator",
            [] {
                result = {wire(Status::Success), 1, 2, 2, 2};
                count = 2;
                records = {{wire(NodeKind::Literal), 0, -1, -1, 1, 0, 0}, {wire(NodeKind::Unary), 1, 0, -1, 2, 1, 1}};
            },
            "1-;");
        invalid(
            "subtree source ranges cross",
            [] {
                result = {wire(Status::Success), 4, 5, 5, 5};
                count = 5;
                records = {{wire(NodeKind::Literal), 0, -1, -1, 1, 0, 0},
                           {wire(NodeKind::Literal), 4, -1, -1, 1, 4, 4},
                           {wire(NodeKind::Binary), 1, 0, 1, 2, 1, 1},
                           {wire(NodeKind::Literal), 2, -1, -1, 1, 2, 2},
                           {wire(NodeKind::Binary), 3, 2, 3, 3, 3, 3}};
            },
            "1+2+3;");
        for (const auto token : {-1, 3, 4})
            invalid("invalid node token", [=] {
                records[0][1] = token;
            });
        for (const auto depth : {0, 2, 129})
            invalid("invalid leaf depth", [=] {
                records[0][4] = depth;
            });
        invalid("invalid computed depth", [] {
            records[2][4] = 3;
        });
        invalid("literal has first child", [] {
            records[0][2] = 0;
        });
        invalid("literal has second child", [] {
            records[0][3] = 0;
        });
        invalid("missing child", [] {
            records[2][2] = -1;
        });
        invalid("forward child", [] {
            records[2][2] = 2;
        });
        invalid("out-of-range child", [] {
            records[2][3] = std::numeric_limits<std::int64_t>::max();
        });
        invalid("reused child", [] {
            records[2][3] = 0;
        });
        invalid("disconnected nodes", [] {
            records[2] = {wire(NodeKind::Literal), 2, -1, -1, 1, 2, 2};
        });
        for (const std::string word : {"true", "false"})
            invalid(
                "boolean forged as Name",
                [&] {
                    result[4] = static_cast<std::int64_t>(word.size()) + 2;
                    records[0][0] = static_cast<std::int64_t>(aurora::hosted_parser::NodeKind::Name);
                },
                word + "+2;");

        for (const std::string source : {R"("";)", R"("\0\xff";)", R"("é😀";)"})
            valid(
                source,
                [&] {
                    fixture(source, {{wire(NodeKind::Literal), 0, -1, -1, 1, 0, 0}});
                },
                [&](const auto &t) {
                    return expectedNode(t, 0, "byte_string");
                });
        valid(
            R"(f("text");)",
            [] {
                fixture(R"(f("text");)",
                        {{wire(NodeKind::Literal), 2, -1, -1, 1, 2, 2}, {wire(NodeKind::Call), 0, 0, 1, 2, 0, 3}},
                        {{0, -1, 1, 2, -1}});
            },
            [&](const auto &t) {
                return expectedNode(t, 0, "call", {expectedNode(t, 2, "byte_string")});
            });
        valid(
            R"(("x")[0];)",
            [] {
                fixture(R"(("x")[0];)",
                        {{wire(NodeKind::Literal), 1, -1, -1, 1, 1, 1},
                         {wire(NodeKind::Literal), 4, -1, -1, 1, 4, 4},
                         {wire(NodeKind::Index), 3, 0, 1, 2, 3, 5}});
            },
            [&](const auto &t) {
                return expectedNode(t, 1, "index", {expectedNode(t, 1, "byte_string"), expectedNode(t, 4, "number")});
            });
        invalid(
            "byte string forged as name",
            [] {
                fixture(R"("text";)", {{wire(NodeKind::Name), 0, -1, -1, 1, 0, 0}});
            },
            R"("text";)");
        invalid(
            "bare byte string cannot receive a method",
            [] {
                fixture(R"("x".m();)",
                        {{wire(NodeKind::Literal), 0, -1, -1, 1, 0, 0}, {wire(NodeKind::MethodCall), 2, 0, 1, 2, 2, 4}},
                        {{0, -1, 1, 2, -1}});
            },
            R"("x".m();)");
        invalid(
            "bare byte string cannot receive an index",
            [] {
                fixture(R"("x"[0];)",
                        {{wire(NodeKind::Literal), 0, -1, -1, 1, 0, 0},
                         {wire(NodeKind::Literal), 2, -1, -1, 1, 2, 2},
                         {wire(NodeKind::Index), 1, 0, 1, 2, 1, 3}});
            },
            R"("x"[0];)");

        valid(
            "f(1,2);",
            [] {
                callFixture();
            },
            [&](const auto &t) {
                return expectedNode(t, 0, "call", {expectedNode(t, 2, "number"), expectedNode(t, 4, "number")});
            });
        valid(
            "a.m(1);",
            [] {
                methodFixture();
            },
            [&](const auto &t) {
                return expectedNode(t, 2, "method_call", {expectedNode(t, 0, "name"), expectedNode(t, 4, "number")});
            });
        valid(
            "a[i];",
            [] {
                indexFixture();
            },
            [&](const auto &t) {
                return expectedNode(t, 0, "index", {expectedNode(t, 0, "name"), expectedNode(t, 2, "name")});
            });
        for (const std::string source : {"foo();", "Widget();", "array();", "if();"})
            valid(
                source,
                [&] {
                    fixture(source, {{wire(NodeKind::Call), 0, -1, 0, 1, 0, 2}});
                },
                [&](const auto &t) {
                    return expectedNode(t, 0, "call");
                });
        for (const std::string source : {"a::b;", "std::array;", "a // qualification\n :: b;"})
            valid(
                source,
                [&] {
                    fixture(source, {{wire(NodeKind::Name), 0, -1, -1, 1, 2, 2}});
                },
                [&](const auto &t) {
                    return qualifiedNode(expectedNode(t, 0, "name"), t, 2, t[0].text + "::" + t[2].text);
                });
        valid(
            "std::array();",
            [] {
                fixture("std::array();", {{wire(NodeKind::Call), 0, -1, 0, 1, 2, 4}});
            },
            [&](const auto &t) {
                return qualifiedNode(expectedNode(t, 0, "call"), t, 2, "std::array");
            });
        valid(
            "a.b;",
            [] {
                fixture("a.b;",
                        {{wire(NodeKind::Name), 0, -1, -1, 1, 0, 0}, {wire(NodeKind::Member), 2, 0, -1, 2, 2, 2}});
            },
            [&](const auto &t) {
                return expectedNode(t, 2, "member", {expectedNode(t, 0, "name")});
            });
        valid(
            "a.m();",
            [] {
                fixture("a.m();",
                        {{wire(NodeKind::Name), 0, -1, -1, 1, 0, 0}, {wire(NodeKind::MethodCall), 2, 0, 1, 2, 2, 4}},
                        {{0, -1, 1, 2, -1}});
            },
            [&](const auto &t) {
                return expectedNode(t, 2, "method_call", {expectedNode(t, 0, "name")});
            });
        valid(
            "(1).m();",
            [] {
                fixture("(1).m();",
                        {{wire(NodeKind::Literal), 1, -1, -1, 1, 1, 1}, {wire(NodeKind::MethodCall), 4, 0, 1, 2, 4, 6}},
                        {{0, -1, 1, 2, -1}});
            },
            [&](const auto &t) {
                return expectedNode(t, 4, "method_call", {expectedNode(t, 1, "number")});
            });
        valid(
            "f((1),(2));",
            [] {
                fixture("f((1),(2));",
                        {{wire(NodeKind::Literal), 3, -1, -1, 1, 3, 3},
                         {wire(NodeKind::Literal), 7, -1, -1, 1, 7, 7},
                         {wire(NodeKind::Call), 0, 1, 2, 2, 0, 9}},
                        {{0, -1, 1, 2, -1}, {1, 0, 2, 2, -1}});
            },
            [&](const auto &t) {
                return expectedNode(t, 0, "call", {expectedNode(t, 3, "number"), expectedNode(t, 7, "number")});
            });
        valid(
            "f(g(1),2);",
            [] {
                fixture("f(g(1),2);",
                        {{wire(NodeKind::Literal), 4, -1, -1, 1, 4, 4},
                         {wire(NodeKind::Call), 2, 0, 1, 2, 2, 5},
                         {wire(NodeKind::Literal), 7, -1, -1, 1, 7, 7},
                         {wire(NodeKind::Call), 0, 2, 2, 3, 0, 8}},
                        {{0, -1, 1, 2, -1}, {1, -1, 1, 3, -1}, {2, 1, 2, 3, -1}});
            },
            [&](const auto &t) {
                return expectedNode(
                    t,
                    0,
                    "call",
                    {expectedNode(t, 2, "call", {expectedNode(t, 4, "number")}), expectedNode(t, 7, "number")});
            });
        valid(
            "std::f().m()[i].x;",
            [] {
                fixture("std::f().m()[i].x;",
                        {{wire(NodeKind::Call), 0, -1, 0, 1, 2, 4},
                         {wire(NodeKind::MethodCall), 6, 0, 1, 2, 6, 8},
                         {wire(NodeKind::Name), 10, -1, -1, 1, 10, 10},
                         {wire(NodeKind::Index), 9, 1, 2, 3, 9, 11},
                         {wire(NodeKind::Member), 13, 3, -1, 4, 13, 13}},
                        {{0, -1, 1, 2, -1}});
            },
            [&](const auto &t) {
                const auto call = qualifiedNode(expectedNode(t, 0, "call"), t, 2, "std::f");
                const auto method = expectedNode(t, 6, "method_call", {call});
                const auto index = expectedNode(t, 6, "index", {method, expectedNode(t, 10, "name")});
                return expectedNode(t, 13, "member", {index});
            });
        valid(
            "(a+b)[i];",
            [] {
                fixture("(a+b)[i];",
                        {{wire(NodeKind::Name), 1, -1, -1, 1, 1, 1},
                         {wire(NodeKind::Name), 3, -1, -1, 1, 3, 3},
                         {wire(NodeKind::Binary), 2, 0, 1, 2, 2, 2},
                         {wire(NodeKind::Name), 6, -1, -1, 1, 6, 6},
                         {wire(NodeKind::Index), 5, 2, 3, 3, 5, 7}});
            },
            [&](const auto &t) {
                const auto sum = expectedNode(t, 2, "binary", {expectedNode(t, 1, "name"), expectedNode(t, 3, "name")});
                return expectedNode(t, 2, "index", {sum, expectedNode(t, 6, "name")});
            });
        valid(
            "{};",
            [] {
                fixture("{};", {{wire(NodeKind::ArrayLiteral), 0, -1, 0, 1, 0, 1}});
            },
            [&](const auto &t) {
                return expectedNode(t, 0, "array_literal");
            });
        valid(
            "{1,2};",
            [] {
                arrayFixture();
            },
            [&](const auto &t) {
                return expectedNode(
                    t, 0, "array_literal", {expectedNode(t, 1, "number"), expectedNode(t, 3, "number")});
            });
        valid(
            "T{.a=1,.b=2};",
            [] {
                constructFixture();
            },
            [&](const auto &t) {
                return designatedNode(
                    expectedNode(t, 0, "construct", {expectedNode(t, 5, "number"), expectedNode(t, 10, "number")}),
                    {"a", "b"});
            });
        for (const std::string source : {"T{};", "if{};", "array{};", "size_of{};"})
            valid(
                source,
                [&] {
                    fixture(source, {{wire(NodeKind::Construct), 0, -1, 0, 1, 0, 2}});
                },
                [&](const auto &t) {
                    return expectedNode(t, 0, "construct");
                });
        valid(
            "pkg // type\n :: T{.x = 1};",
            [] {
                fixture("pkg // type\n :: T{.x = 1};",
                        {{wire(NodeKind::Literal), 7, -1, -1, 1, 7, 7}, {wire(NodeKind::Construct), 0, 0, 1, 2, 2, 8}},
                        {{0, -1, 1, 2, 5}});
            },
            [&](const auto &t) {
                const auto construct = expectedNode(t, 0, "construct", {expectedNode(t, 7, "number")});
                return designatedNode(qualifiedNode(construct, t, 2, "pkg::T"), {"x"});
            });
        valid(
            "T{.a=1,.a=2};",
            [] {
                constructFixture("T{.a=1,.a=2};");
            },
            [&](const auto &t) {
                return designatedNode(
                    expectedNode(t, 0, "construct", {expectedNode(t, 5, "number"), expectedNode(t, 10, "number")}),
                    {"a", "a"});
            });
        valid(
            "f({1},T{.x=2});",
            [] {
                fixture("f({1},T{.x=2});",
                        {{wire(NodeKind::Literal), 3, -1, -1, 1, 3, 3},
                         {wire(NodeKind::ArrayLiteral), 2, 0, 1, 2, 2, 4},
                         {wire(NodeKind::Literal), 11, -1, -1, 1, 11, 11},
                         {wire(NodeKind::Construct), 6, 2, 1, 2, 6, 12},
                         {wire(NodeKind::Call), 0, 3, 2, 3, 0, 13}},
                        {{0, -1, 1, 2, -1}, {1, -1, 1, 3, -1}, {2, -1, 1, 2, 9}, {3, 1, 2, 3, -1}});
            },
            [&](const auto &t) {
                const auto array = expectedNode(t, 2, "array_literal", {expectedNode(t, 3, "number")});
                const auto construct =
                    designatedNode(expectedNode(t, 6, "construct", {expectedNode(t, 11, "number")}), {"x"});
                return expectedNode(t, 0, "call", {array, construct});
            });
        valid(
            "{1}[0].x;",
            [] {
                fixture("{1}[0].x;",
                        {{wire(NodeKind::Literal), 1, -1, -1, 1, 1, 1},
                         {wire(NodeKind::ArrayLiteral), 0, 0, 1, 2, 0, 2},
                         {wire(NodeKind::Literal), 4, -1, -1, 1, 4, 4},
                         {wire(NodeKind::Index), 3, 1, 2, 3, 3, 5},
                         {wire(NodeKind::Member), 7, 3, -1, 4, 7, 7}},
                        {{0, -1, 1, 2, -1}});
            },
            [&](const auto &t) {
                const auto array = expectedNode(t, 0, "array_literal", {expectedNode(t, 1, "number")});
                const auto index = expectedNode(t, 0, "index", {array, expectedNode(t, 4, "number")});
                return expectedNode(t, 7, "member", {index});
            });
        valid(
            "T{}.m();",
            [] {
                fixture(
                    "T{}.m();",
                    {{wire(NodeKind::Construct), 0, -1, 0, 1, 0, 2}, {wire(NodeKind::MethodCall), 4, 0, 1, 2, 4, 6}},
                    {{0, -1, 1, 2, -1}});
            },
            [&](const auto &t) {
                return expectedNode(t, 4, "method_call", {expectedNode(t, 0, "construct")});
            });
        for (const std::string suffix : {";", ",next{}", "{}", "", ".member", "+1"}) {
            const auto empty = "field{}" + suffix;
            validConstructor(
                empty,
                [&] {
                    constructorFixture(empty, true);
                },
                [&](const auto &t) {
                    return expectedNode(t, 0, "array_zero");
                },
                3);
            const auto nonempty = "field{1}" + suffix;
            validConstructor(
                nonempty,
                [&] {
                    constructorFixture(nonempty);
                },
                [&](const auto &t) {
                    return expectedNode(t, 0, "array_literal", {expectedNode(t, 2, "number")});
                },
                4);
        }
        validConstructor(
            "field // brace\n {{1},T{.x=2}}{}",
            [] {
                fixture("field // brace\n {{1},T{.x=2}}{}",
                        {{wire(NodeKind::Literal), 3, -1, -1, 1, 3, 3},
                         {wire(NodeKind::ArrayLiteral), 2, 0, 1, 2, 2, 4},
                         {wire(NodeKind::Literal), 11, -1, -1, 1, 11, 11},
                         {wire(NodeKind::Construct), 6, 2, 1, 2, 6, 12},
                         {wire(NodeKind::ArrayLiteral), 0, 3, 2, 3, 0, 13}},
                        {{0, -1, 1, 2, -1}, {1, -1, 1, 3, -1}, {2, -1, 1, 2, 9}, {3, 1, 2, 3, -1}},
                        14);
            },
            [&](const auto &t) {
                const auto array = expectedNode(t, 2, "array_literal", {expectedNode(t, 3, "number")});
                const auto construct =
                    designatedNode(expectedNode(t, 6, "construct", {expectedNode(t, 11, "number")}), {"x"});
                return expectedNode(t, 0, "array_literal", {array, construct});
            },
            14);
        for (const auto field : {-2LL, 0LL, 2LL, 4LL, 12LL, std::numeric_limits<long long>::max()})
            invalid(
                "invalid designated field ordinal",
                [=] {
                    constructFixture();
                    edges[0][4] = field;
                },
                "T{.a=1,.b=2};");
        invalid(
            "construct has an undesignated edge",
            [] {
                constructFixture();
                edges[1][4] = -1;
            },
            "T{.a=1,.b=2};");
        invalid(
            "construct reuses a field ordinal",
            [] {
                constructFixture();
                edges[1][4] = 3;
            },
            "T{.a=1,.b=2};");
        for (const std::string source : {"T{+a=1,.b=2};",
                                         "T{.a+1,.b=2};",
                                         "T{.a=1 .b=2};",
                                         "T{.a=1,.b=2];",
                                         "T{.array=1,.b=2};",
                                         "T{.true=1,.b=2};",
                                         "T{.builtin=1,.b=2};",
                                         "T{.__au_x=1,.b=2};"})
            invalid(
                "malformed designator or brace spelling",
                [&] {
                    constructFixture(source);
                },
                source);
        invalid(
            "call edge carries a field label",
            [] {
                callFixture();
                edges[0][4] = 0;
            },
            "f(1,2);");
        invalid(
            "method receiver edge carries a field label",
            [] {
                methodFixture();
                edges[0][4] = 2;
            },
            "a.m(1);");
        invalid(
            "array edge carries a field label",
            [] {
                arrayFixture();
                edges[0][4] = 1;
            },
            "{1,2};");
        for (const auto field : {2U, 3U, 4U, 5U, 6U})
            invalid(
                "invalid array list metadata",
                [=] {
                    arrayFixture();
                    records[2][field] = -1;
                },
                "{1,2};");
        invalid(
            "aggregate borrows nested brace close",
            [] {
                fixture("{{1}};",
                        {{wire(NodeKind::Literal), 2, -1, -1, 1, 2, 2},
                         {wire(NodeKind::ArrayLiteral), 1, 0, 1, 2, 1, 3},
                         {wire(NodeKind::ArrayLiteral), 0, 1, 1, 3, 0, 3}},
                        {{0, -1, 1, 2, -1}, {1, -1, 1, 3, -1}});
            },
            "{{1}};");
        invalid(
            "ordinary empty array forged as zero initializer",
            [] {
                fixture("{};", {{wire(NodeKind::ArrayZero), 0, -1, 0, 1, 0, 1}});
            },
            "{};");
        invalid(
            "constructor profile forged in ordinary expression",
            [] {
                constructorFixture();
            },
            "field{1};");
        invalid(
            "ordinary construct forged as constructor profile",
            [] {
                fixture("field{};", {{wire(NodeKind::Construct), 0, -1, 0, 1, 0, 2}});
            },
            "field{};",
            Stop::ConstructorBraces);
        invalid(
            "ordinary array forged as constructor profile",
            [] {
                arrayFixture();
            },
            "{1,2};",
            Stop::ConstructorBraces);
        invalid(
            "empty constructor forged as array literal",
            [] {
                constructorFixture("field{};", true);
                records[0][0] = wire(NodeKind::ArrayLiteral);
            },
            "field{};",
            Stop::ConstructorBraces);
        invalid(
            "nonempty constructor forged as zero initializer",
            [] {
                constructorFixture();
                records[1][0] = wire(NodeKind::ArrayZero);
            },
            "field{1};",
            Stop::ConstructorBraces);
        invalid(
            "constructor root moved to brace token",
            [] {
                constructorFixture();
                records[1][1] = records[1][5] = 1;
            },
            "field{1};",
            Stop::ConstructorBraces);
        invalid(
            "constructor edge carries a field label",
            [] {
                constructorFixture();
                edges[0][4] = 0;
            },
            "field{1};",
            Stop::ConstructorBraces);
        invalid(
            "constructor root consumes a following brace pair",
            [] {
                constructorFixture("field{1}{};");
                result[3] = 6;
                result[4] = 10;
                records[1][6] = 5;
            },
            "field{1}{};",
            Stop::ConstructorBraces);
        invalid(
            "constructor profile consumes postfix",
            [] {
                fixture("field{}.x;",
                        {{wire(NodeKind::ArrayZero), 0, -1, 0, 1, 0, 2}, {wire(NodeKind::Member), 4, 0, -1, 2, 4, 4}});
            },
            "field{}.x;",
            Stop::ConstructorBraces);
        invalid(
            "constructor profile consumes outer binary",
            [] {
                fixture("field{}+1;",
                        {{wire(NodeKind::ArrayZero), 0, -1, 0, 1, 0, 2},
                         {wire(NodeKind::Literal), 4, -1, -1, 1, 4, 4},
                         {wire(NodeKind::Binary), 3, 0, 1, 2, 3, 3}});
            },
            "field{}+1;",
            Stop::ConstructorBraces);
        for (const std::string field : {"true", "array", "builtin", "__au_x", "1"}) {
            const auto source = field + "{};";
            invalid(
                "constructor field bypasses ident validation",
                [&] {
                    constructorFixture(source, true);
                },
                source,
                Stop::ConstructorBraces);
        }
        for (std::size_t field : {5U, 6U})
            for (const auto value : {-1LL, 1LL, 3LL, std::numeric_limits<long long>::max()})
                invalid("invalid scalar name/close endpoint", [=] {
                    records[0][field] = value;
                });
        invalid("negative edge count", [] {
            edgeCount = -1;
        });
        invalid("impossible edge count", [] {
            edgeCount = count;
        });
        invalid("Unsupported result retains edges", [] {
            result = {wire(Status::Unsupported), -1, 0, 0, 0};
            count = 0;
            edgeCount = 1;
        });
        for (const auto endpoint : {-1LL, 1LL, 3LL, 5LL, std::numeric_limits<long long>::max()})
            invalid(
                "invalid qualified name endpoint",
                [=] {
                    fixture("a::b;", {{wire(NodeKind::Name), 0, -1, -1, 1, endpoint, endpoint}});
                },
                "a::b;");
        for (const std::string source : {"a+b;", "a.b;", "a::true;", "a::builtin;", "a::__au_x;", "a::class;"})
            invalid(
                "invalid qualified name spelling",
                [&] {
                    fixture(source, {{wire(NodeKind::Name), 0, -1, -1, 1, 2, 2}});
                },
                source);
        invalid(
            "qualified name has child",
            [] {
                fixture("a::b;", {{wire(NodeKind::Name), 0, 0, -1, 1, 2, 2}});
            },
            "a::b;");
        for (const std::string source : {"a.array;", "a.builtin;", "a.true;", "a.__au_x;", "a::b;"})
            invalid(
                "invalid member identifier or dot",
                [&] {
                    fixture(source,
                            {{wire(NodeKind::Name), 0, -1, -1, 1, 0, 0}, {wire(NodeKind::Member), 2, 0, -1, 2, 2, 2}});
                },
                source);
        for (const std::string source : {"size_of(i64);", "type_id(i64);", "field_count(T);"})
            invalid(
                "type-taking reflection forged as call",
                [&] {
                    fixture(source,
                            {{wire(NodeKind::Name), 2, -1, -1, 1, 2, 2}, {wire(NodeKind::Call), 0, 0, 1, 2, 0, 3}},
                            {{0, -1, 1, 2, -1}});
                },
                source);
        for (const auto head : {-2LL, 0LL, 2LL, std::numeric_limits<long long>::max()})
            invalid(
                "invalid argument head",
                [=] {
                    callFixture();
                    records[2][2] = head;
                },
                "f(1,2);");
        for (const auto countValue : {-1LL, 0LL, 1LL, 3LL, std::numeric_limits<long long>::max()})
            invalid(
                "invalid argument count",
                [=] {
                    callFixture();
                    records[2][3] = countValue;
                },
                "f(1,2);");
        for (const auto child : {-1LL, 2LL, 3LL, std::numeric_limits<long long>::max()})
            invalid(
                "invalid edge child",
                [=] {
                    callFixture();
                    edges[0][0] = child;
                },
                "f(1,2);");
        for (const auto previous : {-2LL, 0LL, 1LL, std::numeric_limits<long long>::max()})
            invalid(
                "cyclic or forward argument edge",
                [=] {
                    callFixture();
                    edges[0][1] = previous;
                },
                "f(1,2);");
        for (const auto countValue : {-1LL, 0LL, 1LL, 3LL, std::numeric_limits<long long>::max()})
            invalid(
                "invalid edge count metadata",
                [=] {
                    callFixture();
                    edges[1][2] = countValue;
                },
                "f(1,2);");
        for (const auto depth : {-1LL, 0LL, 1LL, 3LL, 129LL})
            invalid(
                "invalid edge depth metadata",
                [=] {
                    callFixture();
                    edges[1][3] = depth;
                },
                "f(1,2);");
        invalid(
            "reused argument child",
            [] {
                callFixture();
                edges[1][0] = 0;
            },
            "f(1,2);");
        invalid(
            "reversed argument order",
            [] {
                callFixture();
                edges[0][0] = 1;
                edges[1][0] = 0;
            },
            "f(1,2);");
        invalid(
            "disconnected argument edge",
            [] {
                callFixture();
                records[2][2] = 0;
                records[2][3] = 1;
            },
            "f(1,2);");
        invalid(
            "two calls reuse an argument edge",
            [] {
                fixture("f(1)+g(2);",
                        {{wire(NodeKind::Literal), 2, -1, -1, 1, 2, 2},
                         {wire(NodeKind::Call), 0, 0, 1, 2, 0, 3},
                         {wire(NodeKind::Literal), 7, -1, -1, 1, 7, 7},
                         {wire(NodeKind::Call), 5, 0, 1, 2, 5, 8},
                         {wire(NodeKind::Binary), 4, 1, 3, 3, 4, 4}},
                        {{0, -1, 1, 2, -1}, {2, -1, 1, 2, -1}});
            },
            "f(1)+g(2);");
        invalid(
            "call has wrong depth",
            [] {
                callFixture();
                records[2][4] = 3;
            },
            "f(1,2);");
        invalid(
            "argument edge skips earlier link",
            [] {
                callFixture();
                edges[1][1] = -1;
            },
            "f(1,2);");
        for (const auto close : {-1LL, 2LL, 4LL, 6LL, std::numeric_limits<long long>::max()})
            invalid(
                "invalid call close",
                [=] {
                    callFixture();
                    records[2][6] = close;
                },
                "f(1,2);");
        for (const std::string source : {"f[1,2];", "f(1+2);", "f(1;2);", "f(1,2];"})
            invalid(
                "malformed call punctuation",
                [&] {
                    callFixture(source);
                },
                source);
        invalid(
            "call omits trailing comma",
            [] {
                fixture("f(1,);",
                        {{wire(NodeKind::Literal), 2, -1, -1, 1, 2, 2}, {wire(NodeKind::Call), 0, 0, 1, 2, 0, 4}},
                        {{0, -1, 1, 2, -1}});
            },
            "f(1,);");
        invalid(
            "call arguments lack comma",
            [] {
                fixture("f(1 2);",
                        {{wire(NodeKind::Literal), 2, -1, -1, 1, 2, 2},
                         {wire(NodeKind::Literal), 3, -1, -1, 1, 3, 3},
                         {wire(NodeKind::Call), 0, 1, 2, 2, 0, 4}},
                        {{0, -1, 1, 2, -1}, {1, 0, 2, 2, -1}});
            },
            "f(1 2);");
        invalid(
            "method has no receiver",
            [] {
                methodFixture();
                records[2][2] = -1;
                records[2][3] = 0;
            },
            "a.m(1);");
        invalid(
            "method receiver follows dot",
            [] {
                methodFixture();
                edges[0][0] = 1;
                edges[1][0] = 0;
            },
            "a.m(1);");
        invalid(
            "method receiver is self",
            [] {
                methodFixture();
                edges[0][0] = 2;
            },
            "a.m(1);");
        invalid(
            "member has second child",
            [] {
                fixture("a.b;",
                        {{wire(NodeKind::Name), 0, -1, -1, 1, 0, 0}, {wire(NodeKind::Member), 2, 0, 0, 2, 2, 2}});
            },
            "a.b;");
        invalid(
            "ungrouped literal cannot receive postfix",
            [] {
                fixture("1.m();",
                        {{wire(NodeKind::Literal), 0, -1, -1, 1, 0, 0}, {wire(NodeKind::MethodCall), 2, 0, 1, 2, 2, 4}},
                        {{0, -1, 1, 2, -1}});
            },
            "1.m();");
        for (const std::string source : {"a(i);", "a[i);", "a[i[;"})
            invalid(
                "invalid index delimiters",
                [&] {
                    indexFixture(source);
                },
                source);
        invalid(
            "index swapped operands",
            [] {
                indexFixture();
                records[2][2] = 1;
                records[2][3] = 0;
            },
            "a[i];");
        invalid(
            "index missing operand",
            [] {
                indexFixture();
                records[2][3] = -1;
            },
            "a[i];");
        invalid(
            "index incorrect name endpoint",
            [] {
                indexFixture();
                records[2][5] = 2;
            },
            "a[i];");
        invalid(
            "index close reuses token",
            [] {
                indexFixture();
                records[2][6] = 1;
            },
            "a[i];");
        for (const std::string source : {"(1;", "1);", "((1);", "(1));", "()1;", "1();"})
            invalid(
                "unmatched or empty grouping cannot be ignored",
                [&] {
                    const auto lexical = aurora::lex(source);
                    std::int64_t ordinal = 0;
                    while (lexical[static_cast<std::size_t>(ordinal)].text != "1")
                        ++ordinal;
                    fixture(source, {{wire(NodeKind::Literal), ordinal, -1, -1, 1, ordinal, ordinal}});
                },
                source);
        diagnostic("a[1;", Status::ExpectedIndexClose, 3, DiagnosticCode::UnexpectedToken, "expected ']' (found ';')");
        diagnostic(
            "a.;", Status::ExpectedIdentifier, 2, DiagnosticCode::UnexpectedToken, "expected identifier (found ';')");
        diagnostic("a.if;",
                   Status::ReservedIdentifier,
                   2,
                   DiagnosticCode::UnexpectedToken,
                   "reserved identifier (found 'if')");
        diagnostic("a.array;",
                   Status::ReservedBuiltin,
                   2,
                   DiagnosticCode::UnexpectedToken,
                   "reserved builtin storage name (found 'array')");
        diagnostic("a.__au_x;",
                   Status::ReservedPrefix,
                   2,
                   DiagnosticCode::UnexpectedToken,
                   "reserved compiler identifier prefix: __au_ (found '__au_x')");
        diagnostic("a::true;",
                   Status::ReservedIdentifier,
                   2,
                   DiagnosticCode::UnexpectedToken,
                   "reserved identifier (found 'true')");
        diagnostic("{1;", Status::ExpectedBraceClose, 2, DiagnosticCode::UnexpectedToken, "expected '}' (found ';')");
        diagnostic("T{1};", Status::ExpectedDot, 2, DiagnosticCode::UnexpectedToken, "expected '.' (found '1')");
        diagnostic("T{.x 1};", Status::ExpectedEqual, 4, DiagnosticCode::UnexpectedToken, "expected '=' (found '1')");
        diagnostic("T{.true=1};",
                   Status::ReservedIdentifier,
                   3,
                   DiagnosticCode::UnexpectedToken,
                   "reserved identifier (found 'true')");
        diagnostic("T{.array=1};",
                   Status::ReservedBuiltin,
                   3,
                   DiagnosticCode::UnexpectedToken,
                   "reserved builtin storage name (found 'array')");
        diagnostic("T{.__au_x=1};",
                   Status::ReservedPrefix,
                   3,
                   DiagnosticCode::UnexpectedToken,
                   "reserved compiler identifier prefix: __au_ (found '__au_x')");
        diagnostic("field(1);",
                   Status::ExpectedBraceOpen,
                   1,
                   DiagnosticCode::UnexpectedToken,
                   "expected '{' (found '(')",
                   Stop::ConstructorBraces);

        invalid("unexpected unsupported result is fail-closed", [] {
            result = {wire(Status::Unsupported), -1, 0, 0, 0};
            count = 0;
        });
        reset();
        result = {wire(Status::AllocationFailure), -1, 0, 0, 0};
        count = 0;
        position = 0;
        bool allocationFailure = false;
        try {
            static_cast<void>(aurora::parseHostedExpression(tokens, position, Stop::Semicolon));
        } catch (const aurora::Error &error) {
            allocationFailure = error.diagnostic.code == aurora::DiagnosticCode::Internal &&
                                error.diagnostic.message == "hosted parser allocation failed";
        }
        require(allocationFailure && position == 0 && released == 1, "allocation error lost cursor/cleanup");

        for (int mode = 0; mode < 4; ++mode) {
            reset();
            auto corrupted = tokens;
            if (mode == 0)
                corrupted[1].text = "-";
            else if (mode == 1)
                corrupted[1].span.source = std::make_shared<const aurora::SourceText>("other.au", "1+2;");
            else if (mode == 2)
                corrupted[1].span.begin.offset = 0;
            else
                corrupted[1].span.end.offset = 100;
            position = 0;
            bool rejected = false;
            try {
                static_cast<void>(aurora::parseHostedExpression(corrupted, position, Stop::Semicolon));
            } catch (const aurora::Error &error) {
                rejected = error.diagnostic.code == aurora::DiagnosticCode::Internal;
            }
            require(rejected && position == 0 && released == 1, "inconsistent token provenance accepted");
            ++cases;
        }
        for (const bool constructor : {false, true}) {
            const std::string source = constructor ? "field{1};" : "T{.a=1,.b=2};";
            for (const std::size_t ordinal :
                 constructor ? std::vector<std::size_t>{0, 1, 3, 4} : std::vector<std::size_t>{2, 3, 4, 11}) {
                reset();
                if (constructor)
                    constructorFixture(source);
                else
                    constructFixture(source);
                auto corrupted = aurora::lex(source, "aggregate-provenance.au");
                corrupted[ordinal].span.source = std::make_shared<const aurora::SourceText>("other.au", source);
                position = 0;
                bool rejected = false;
                try {
                    static_cast<void>(aurora::parseHostedExpression(
                        corrupted, position, constructor ? Stop::ConstructorBraces : Stop::Semicolon));
                } catch (const aurora::Error &error) {
                    rejected = error.diagnostic.code == aurora::DiagnosticCode::Internal;
                }
                require(rejected && position == 0 && created == 1 && parsed == 1 && released == 1,
                        "aggregate field, punctuation or boundary provenance escaped validation");
                ++cases;
            }
        }
        reset();
        hookControl = true;
        const auto hooks =
            aurora::Parser(
                aurora::lex("module hooks;auto f()->i64{i64 x=1;x=1;1;static_assert(1);if(1){}while(1){}return 1;}"))
                .parse();
        hookControl = false;
        require(hooks.functions.size() == 1 && parsed == 8 && created == 8 && released == 8,
                "a statement hook bypassed hosted dispatch or lost cleanup");
        reset();
        hookControl = true;
        const auto constructors =
            aurora::Parser(aurora::lex("export module hooks;class Hook{i64 first;i64 second;array<u8,2> bytes;public:"
                                       "Hook(i64 x):first(x),second(1),bytes(\"ok\"){}auto get()->i64{return 1;}};"))
                .parse();
        hookControl = false;
        require(constructors.classes.size() == 1 && constructors.classes[0].methods.size() == 2 &&
                    constructors.classes[0].methods[0].initializers.size() == 3 && parsed == 4 && created == 4 &&
                    released == 4 &&
                    hookStops ==
                        std::vector<Stop>{
                            Stop::CloseParenthesis, Stop::CloseParenthesis, Stop::CloseParenthesis, Stop::Semicolon},
                "constructor initializer bypassed hosted dispatch or lost its stopping context");
        reset();
        hookControl = true;
        const auto braceTokens = aurora::lex(
            "export module hooks;class Hook{array<i64,1> value;array<i64,1> zero;public:Hook():value{1},zero{}{}};");
        const auto braceConstructors = aurora::Parser(braceTokens).parse();
        hookControl = false;
        require(created == 2 && parsed == 2 && released == 2 &&
                    hookStops == std::vector<Stop>{Stop::ConstructorBraces, Stop::ConstructorBraces},
                "brace initializer bypassed its hosted profile or consumed the next initializer/body");
        sameExpression(braceConstructors.classes[0].methods[0].initializers[0].second,
                       expectedNode(braceTokens, 29, "array_literal", {expectedNode(braceTokens, 31, "number")}));
        sameExpression(braceConstructors.classes[0].methods[0].initializers[1].second,
                       expectedNode(braceTokens, 34, "array_zero"));
        reset();
        hookControl = hookUnsupported = true;
        aurora::Parser unsupportedConstructor(braceTokens);
        bool unsupportedRejected = false;
        try {
            static_cast<void>(unsupportedConstructor.parse());
        } catch (const aurora::Error &error) {
            unsupportedRejected = error.diagnostic.code == aurora::DiagnosticCode::Internal &&
                                  error.diagnostic.message == "hosted parser returned an invalid result";
        }
        hookControl = false;
        require(unsupportedRejected && unsupportedConstructor.peek().text == "{" && created == 1 && parsed == 1 &&
                    released == 1,
                "unexpected Unsupported escaped direct brace dispatch or changed cursor/cleanup");
        reset();
        hookControl = hookCorrupt = true;
        aurora::Parser corruptConstructor(braceTokens);
        bool corruptHookRejected = false;
        try {
            static_cast<void>(corruptConstructor.parse());
        } catch (const aurora::Error &error) {
            corruptHookRejected = error.diagnostic.code == aurora::DiagnosticCode::Internal;
        }
        hookControl = false;
        require(corruptHookRejected && corruptConstructor.peek().text == "{" && created == 1 && parsed == 1 &&
                    released == 1,
                "rejected constructor hook changed the caller cursor or lost cleanup");
        reset();
        hookControl = hookPrepared = true;
        fixture("value{Box<Box<i64>>{.x=1}}{}",
                {{wire(NodeKind::Literal), 12, -1, -1, 1, 12, 12},
                 {wire(NodeKind::Construct), 2, 0, 1, 2, 2, 13},
                 {wire(NodeKind::ArrayLiteral), 0, 1, 1, 3, 0, 14}},
                {{0, -1, 1, 2, 10}, {1, -1, 1, 3, -1}},
                15);
        types = {{wire(TypeKind::I64), 6, 6, 12, -1, -1, -1, 0},
                 {wire(TypeKind::Named), 4, 4, 14, 0, -1, -1, 0},
                 {wire(TypeKind::Named), 2, 2, 15, 1, -1, 2, 1}};
        typeCount = 3;
        const auto templateBraceTokens = aurora::lex(
            "export module hooks;class Hook{array<i64,1> value;public:Hook():value{Box<Box<i64>>{.x=1}}{}};");
        const auto templateBrace = aurora::Parser(templateBraceTokens).parse();
        hookControl = false;
        require(created == 1 && parsed == 1 && released == 1 && typeRead == 3 &&
                    hookStops == std::vector<Stop>{Stop::ConstructorBraces},
                "nested template constructor value bypassed the direct hosted route");
        const auto expectedConstruct = typedNode(
            designatedNode(
                expectedNode(templateBraceTokens, 23, "construct", {expectedNode(templateBraceTokens, 33, "number")}),
                {"x"}),
            {namedArgument("Box", {aurora::TypeKind::I64})});
        sameExpression(templateBrace.classes[0].methods[0].initializers[0].second,
                       expectedNode(templateBraceTokens, 21, "array_literal", {expectedConstruct}));
        for (const auto &[source, failureOrdinal] : std::vector<std::pair<std::string, std::size_t>>{
                 {"field{Box<i64,>{}}{}", 6}, {"field{{Box<i64,>{}}}{}", 7}, {"field{T{.x=Box<i64,>{}}}{}", 11}}) {
            reset();
            const auto malformedTokens =
                aurora::lex("export module hooks;class Hook{array<i64,1> field;public:Hook():" + source + "};");
            const auto &expected = malformedTokens[21 + failureOrdinal].span;
            const auto expressionTokens = aurora::lex(source);
            require(expressionTokens[failureOrdinal].text == ">", "malformed template hook lost its failure token");
            count = 0;
            records.clear();
            result = {wire(Status::ExpectedIdentifier),
                      -1,
                      0,
                      static_cast<std::int64_t>(failureOrdinal),
                      static_cast<std::int64_t>(expressionTokens[failureOrdinal].span.begin.offset)};
            hookControl = hookPrepared = true;
            bool rejected = false;
            try {
                static_cast<void>(aurora::Parser(malformedTokens).parse());
            } catch (const aurora::Error &error) {
                const auto &span = error.diagnostic.span;
                rejected = error.diagnostic.code == DiagnosticCode::UnexpectedToken &&
                           error.diagnostic.message == "expected identifier (found '>')" &&
                           span.source == expected.source && span.begin.offset == expected.begin.offset &&
                           span.begin.line == expected.begin.line && span.begin.column == expected.begin.column &&
                           span.end.offset == expected.end.offset && span.end.line == expected.end.line &&
                           span.end.column == expected.end.column;
            }
            hookControl = false;
            require(rejected && created == 1 && parsed == 1 && released == 1,
                    "malformed nested template bypassed hosted dispatch or changed its brace diagnostic");
            ++cases;
        }
        for (const std::string source : {"field{1}Box<i64>{}", "field{1},next{Box<i64>{}}", "field{a<b}c>d()"}) {
            reset();
            const bool comparison = source == "field{a<b}c>d()";
            const std::size_t consumed = comparison ? 6 : 4;
            const auto next = comparison ? "c" : source == "field{1}Box<i64>{}" ? "Box" : ",";
            if (comparison)
                fixture(source,
                        {{wire(NodeKind::Name), 2, -1, -1, 1, 2, 2},
                         {wire(NodeKind::Name), 4, -1, -1, 1, 4, 4},
                         {wire(NodeKind::Binary), 3, 0, 1, 2, 3, 3},
                         {wire(NodeKind::ArrayLiteral), 0, 0, 1, 3, 0, 5}},
                        {{2, -1, 1, 3, -1}},
                        6);
            else
                constructorFixture(source);
            const auto boundaryTokens = aurora::lex(source, "boundary.au");
            std::size_t boundaryPosition = 0;
            const auto actual =
                aurora::parseHostedExpression(boundaryTokens, boundaryPosition, Stop::ConstructorBraces);
            const auto child =
                comparison
                    ? expectedNode(boundaryTokens,
                                   3,
                                   "binary",
                                   {expectedNode(boundaryTokens, 2, "name"), expectedNode(boundaryTokens, 4, "name")})
                    : expectedNode(boundaryTokens, 2, "number");
            sameExpression(actual, expectedNode(boundaryTokens, 0, "array_literal", {child}));
            require(boundaryPosition == consumed && boundaryTokens[consumed - 1].text == "}" &&
                        boundaryTokens[consumed].text == next && created == 1 && parsed == 1 && released == 1 &&
                        read == count && edgeRead == edgeCount && typeRead == typeCount,
                    "constructor hosted cursor crossed its root closing brace or lost AST/read/cleanup");
            ++cases;
        }
        reset();
        hookControl = true;
        static_cast<void>(aurora::Parser(aurora::lex("module reference;auto f()->i64{return 1;}")).parse());
        hookControl = false;
        require(created == 1 && parsed == 1 && released == 1 && read == 1 &&
                    hookStops == std::vector<Stop>{Stop::Semicolon},
                "default parser bypassed mandatory hosted expression dispatch or lost cleanup");
        require(cases >= 273, "an existing forged-result/provenance control was lost");
        typedControls();
        contextControls();
        contextDispatchControls();
        typedDiagnosticControls();
        std::cout << "PASS hosted parser " << cases << " forged-result/provenance controls and exact cleanup\n";
    } catch (const std::exception &error) {
        std::cerr << "FAIL " << error.what() << '\n';
        return 1;
    }
}
