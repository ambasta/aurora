// Trusted hosted bootstrap boundary. Source snapshots remain immutable and live
// throughout each synchronous call; no owner descriptor or payload pointer is
// constructed, copied or inspected here.
#include "hosted_parser.hpp"
#include "services.hpp"
#include "../runtime/hosted_bytes.hpp"
#include <algorithm>
#include <array>
#include <cstddef>
#include <limits>
#include <utility>

#ifndef AURORA_HOSTED_PARSER
#error The hosted parser adapter requires AURORA_HOSTED_PARSER
#endif
extern "C" {
void aurora_hosted_parser_create(const void *, void *);
void aurora_hosted_parser_parse(void *, const void *, void *);
std::int64_t aurora_hosted_parser_count(const void *);
void aurora_hosted_parser_read(const void *, std::int64_t, void *);
std::int64_t aurora_hosted_parser_edges(const void *);
void aurora_hosted_parser_edge(const void *, std::int64_t, void *);
std::int64_t aurora_hosted_parser_types(const void *);
void aurora_hosted_parser_type(const void *, std::int64_t, void *);
void aurora_hosted_parser_release(void *);
}

namespace aurora {
namespace {
using hosted_parser::NodeKind;
using hosted_parser::Status;
using hosted_parser::Stop;
// Literal private ABI layouts, independently checked by generated-code tests.
class Input {
public:
    std::uint64_t kind = 0;
    const char *backing;
    std::array<std::uint64_t, 3> reserved{};
    std::int64_t start = 0;
    std::int64_t length;
    std::int64_t offset;
    std::int64_t line;
    std::int64_t lineStart;
    Stop stop;
    std::int64_t type1Begin = 0, type1End = 0, type2Begin = 0, type2End = 0;
    std::int64_t capacityBegin = 0, capacityEnd = 0, mode = 0;
};
class Result {
public:
    Status status = Status::Invalid;
    std::int64_t root = -1, count = -1, tokens = -1, offset = -1;
};
class Node {
public:
    NodeKind kind = NodeKind::Invalid;
    std::int64_t token = -1, first = -1, second = -1, depth = -1, nameEnd = -1, close = -1;
};
class Edge {
public:
    std::int64_t child = -1, previous = -1, count = -1, depth = -1, field = -1;
};
class TypeSyntax {
public:
    hosted_parser::TypeKind kind = hosted_parser::TypeKind::Invalid;
    std::int64_t token = -1, nameEnd = -1, close = -1, first = -1, second = -1, owner = -1, role = 0;
};
class Arena {
    hosted::bytes::Region region;
    class Record {
    public:
        std::uint64_t region;
        alignas(8) std::array<std::byte, 168> arena{};
    } record;
    static_assert(sizeof(Record) == 176 && offsetof(Record, arena) == 8);

public:
    explicit Arena(std::uint64_t quota) : region(quota), record{region.id(), {}} {
        const std::array<std::uint64_t, 2> input{region.id(), 0};
        aurora_hosted_parser_create(input.data(), data());
    }
    ~Arena() {
        aurora_hosted_parser_release(&record);
    }
    Arena(const Arena &) = delete;
    Arena &operator=(const Arena &) = delete;
    void *data() {
        return record.arena.data();
    }
};
static_assert(sizeof(Input) == 144 && offsetof(Input, backing) == 8 && offsetof(Input, start) == 40 &&
              offsetof(Input, length) == 48 && offsetof(Input, offset) == 56 && offsetof(Input, line) == 64 &&
              offsetof(Input, lineStart) == 72 && offsetof(Input, stop) == 80 && offsetof(Input, type1Begin) == 88 &&
              offsetof(Input, capacityBegin) == 120 && offsetof(Input, mode) == 136);
static_assert(sizeof(Result) == 40 && sizeof(Node) == 56 && sizeof(Edge) == 40 && offsetof(Edge, field) == 32 &&
              sizeof(TypeSyntax) == 64 && offsetof(TypeSyntax, owner) == 48 && offsetof(TypeSyntax, role) == 56);

[[noreturn]] void invalid() {
    throw Error(DiagnosticCode::Internal, "hosted parser returned an invalid result");
}
bool identifier(const std::string &text) {
    if (text.empty())
        return false;
    const auto first = static_cast<unsigned char>(text.front());
    if (!((first >= 'a' && first <= 'z') || (first >= 'A' && first <= 'Z') || first == '_'))
        return false;
    return std::all_of(text.begin() + 1, text.end(), [](unsigned char byte) {
        return (byte >= 'a' && byte <= 'z') || (byte >= 'A' && byte <= 'Z') || (byte >= '0' && byte <= '9') ||
               byte == '_';
    });
}
bool tailIdentifier(const std::string &text, bool allowArray) {
    // primary() accepts an identifier-shaped first name. Only qualified tails
    // and member names pass through the reference parser's stricter ident().
    static const std::array<std::string, 29> reserved{
        "fn",        "module",        "let",       "mut",    "if",     "else",     "return", "true",
        "false",     "static_assert", "class",     "while",  "break",  "continue", "auto",   "const",
        "public",    "private",       "protected", "unsafe", "extern", "struct",   "export", "import",
        "namespace", "this",          "template",  "Scalar", "enum"};
    return identifier(text) && text != "builtin" && (allowArray || text != "array") && !text.starts_with("__au_") &&
           std::find(reserved.begin(), reserved.end(), text) == reserved.end();
}
bool binary(const std::string &text) {
    return text == "||" || text == "&&" || text == "|" || text == "^" || text == "&" || text == "==" || text == "!=" ||
           text == "<" || text == ">" || text == "<=" || text == ">=" || text == "<<" || text == ">>" || text == "+" ||
           text == "-" || text == "*" || text == "/" || text == "%";
}
} // namespace

ExpressionPtr parseHostedExpression(const std::vector<Token> &tokens,
                                    std::size_t &position,
                                    Stop stop,
                                    const hosted_parser::Context &context) {
    if (position >= tokens.size() || (stop != Stop::Semicolon && stop != Stop::CloseParenthesis &&
                                      stop != Stop::Assignment && stop != Stop::ConstructorBraces))
        invalid();
    const auto &begin = tokens[position].span;
    if (!begin.source)
        invalid();
    const auto &source = begin.source;
    if (source->text.size() > static_cast<std::size_t>(std::numeric_limits<int>::max() - 1) ||
        begin.begin.offset > source->text.size() || begin.begin.line < 1 || begin.begin.column < 1 ||
        static_cast<std::size_t>(begin.begin.column - 1) > begin.begin.offset)
        invalid();
    Input input;
    input.backing = source->text.data();
    input.length = static_cast<std::int64_t>(source->text.size());
    input.offset = static_cast<std::int64_t>(begin.begin.offset);
    input.line = begin.begin.line;
    input.lineStart = input.offset - begin.begin.column + 1;
    input.stop = stop;
    if (context.typeParameters.size() > 2 || context.capacityParameters.size() > 1 ||
        context.typeParameters.size() + context.capacityParameters.size() > 2 ||
        (!context.capacityParameters.empty() && (context.typeParameters.size() != 1 || context.functionTemplate)) ||
        (context.functionTemplate && context.typeParameters.empty()))
        invalid();
    std::vector<std::string> parameterNames;
    const auto parameter = [&](const Token &token, std::int64_t &first, std::int64_t &last) {
        const auto &span = token.span;
        if (span.source != source || span.begin.offset >= span.end.offset || span.end.offset > begin.begin.offset ||
            !tailIdentifier(token.text, false) || token.text == "i64" || token.text == "u64" || token.text == "u8" ||
            token.text == "bool" || token.text == "own" || token.text == "ref" || token.text == "mutref" ||
            source->text.compare(span.begin.offset, span.end.offset - span.begin.offset, token.text) != 0 ||
            std::find(parameterNames.begin(), parameterNames.end(), token.text) != parameterNames.end())
            invalid();
        const auto original = std::lower_bound(
            tokens.begin(), tokens.begin() + position, span.begin.offset, [](const Token &value, std::size_t offset) {
                return value.span.begin.offset < offset;
            });
        if (original == tokens.begin() + position || original->text != token.text || original->span.source != source ||
            original->span.begin.offset != span.begin.offset || original->span.end.offset != span.end.offset ||
            original->span.begin.line != span.begin.line || original->span.begin.column != span.begin.column ||
            original->span.end.line != span.end.line || original->span.end.column != span.end.column ||
            token.line != span.begin.line)
            invalid();
        parameterNames.push_back(token.text);
        first = static_cast<std::int64_t>(span.begin.offset);
        last = static_cast<std::int64_t>(span.end.offset);
    };
    if (!context.typeParameters.empty()) {
        parameter(context.typeParameters[0], input.type1Begin, input.type1End);
        if (context.typeParameters.size() == 2)
            parameter(context.typeParameters[1], input.type2Begin, input.type2End);
        input.mode = context.functionTemplate ? 2 : 1;
    }
    if (!context.capacityParameters.empty())
        parameter(context.capacityParameters[0], input.capacityBegin, input.capacityEnd);
    // At most one node per source token and a bounded explicit parser stack.
    // Geometric growth uses replacement quota, not old+new payload quota.
    Arena arena(static_cast<std::uint64_t>(source->text.size()) * 448 + 131072);
    Result result;
    aurora_hosted_parser_parse(arena.data(), &input, &result);
    const auto actualCount = aurora_hosted_parser_count(arena.data());
    const auto edgeCount = aurora_hosted_parser_edges(arena.data());
    const auto typeCount = aurora_hosted_parser_types(arena.data());
    if (result.status < Status::Success || result.status >= Status::Invalid || result.count < 0 ||
        result.count != actualCount || edgeCount < 0 || typeCount < 0 || result.tokens < 0 ||
        static_cast<std::uint64_t>(result.tokens) >= tokens.size() - position || result.offset < input.offset ||
        result.offset > input.length)
        invalid();
    if (result.status == Status::Unsupported)
        invalid();
    const auto end = position + static_cast<std::size_t>(result.tokens);
    for (auto index = position; index <= end; ++index) {
        const auto &token = tokens[index];
        const auto &span = token.span;
        if (span.source != source || span.begin.offset > span.end.offset || span.end.offset > source->text.size() ||
            (index > position && tokens[index - 1].span.end.offset > span.begin.offset) || token.text.empty() ||
            (token.text == "<eof>"
                 ? span.begin.offset != source->text.size() || span.end.offset != span.begin.offset
                 : source->text.compare(span.begin.offset, span.end.offset - span.begin.offset, token.text) != 0))
            invalid();
    }
    auto at = tokens[end];
    if (static_cast<std::size_t>(result.offset) != at.span.begin.offset) {
        if (result.status == Status::Success || at.text != ">>" ||
            static_cast<std::size_t>(result.offset) != at.span.begin.offset + 1 ||
            at.span.end.offset != at.span.begin.offset + 2)
            invalid();
        at.text = ">";
        ++at.span.begin.offset;
        ++at.span.begin.column;
    }
    if (result.status != Status::Success) {
        if (result.root != -1)
            invalid();
        if (result.status == Status::AllocationFailure)
            throw Error(DiagnosticCode::Internal, "hosted parser allocation failed", at.span);
        if (result.status == Status::NestingLimit)
            throw Error(DiagnosticCode::NestingLimit, "expression parser nesting exceeds 128", at.span);
        if (result.status == Status::TypeNestingLimit || result.status == Status::TemplateNestingLimit ||
            result.status == Status::CallTemplateNestingLimit)
            throw Error(DiagnosticCode::NestingLimit,
                        result.status == Status::TypeNestingLimit       ? "type nesting exceeds 64"
                        : result.status == Status::TemplateNestingLimit ? "template-id nesting exceeds 4"
                                                                        : "template-id nesting exceeds 5",
                        at.span);
        std::string message;
        if (result.status == Status::ExpectedExpression)
            message = "expected expression";
        else if (result.status == Status::ExpectedClose)
            message = "expected ')'";
        else if (result.status == Status::ExpectedIndexClose)
            message = "expected ']'";
        else if (result.status == Status::ExpectedBraceClose)
            message = "expected '}'";
        else if (result.status == Status::ExpectedDot)
            message = "expected '.'";
        else if (result.status == Status::ExpectedEqual)
            message = "expected '='";
        else if (result.status == Status::ExpectedBraceOpen)
            message = "expected '{'";
        else if (result.status == Status::ExpectedIdentifier)
            message = "expected identifier";
        else if (result.status == Status::ReservedIdentifier)
            message = "reserved identifier";
        else if (result.status == Status::ReservedBuiltin)
            message = "reserved builtin storage name";
        else if (result.status == Status::ReservedPrefix)
            message = "reserved compiler identifier prefix: __au_";
        else if (result.status == Status::DepthLimit)
            message = "expression AST depth exceeds 128";
        else if (result.status == Status::ExpectedAngleOpen)
            message = "expected '<'";
        else if (result.status == Status::ExpectedAngleClose)
            message = "expected '>'";
        else if (result.status == Status::ExpectedScope)
            message = "expected '::'";
        else if (result.status == Status::ExpectedComma)
            message = "expected ','";
        else if (result.status == Status::ExpectedConst)
            message = "expected 'const'";
        else if (result.status == Status::ExpectedU8)
            message = "expected 'u8'";
        else if (result.status == Status::ExpectedI64)
            message = "expected 'i64'";
        else if (result.status == Status::ExpectedArray)
            message = "expected 'array'";
        else if (result.status == Status::ReservedType)
            message = "unsupported or reserved type spelling";
        else if (result.status == Status::ExpectedType)
            message = "expected type name";
        else if (result.status == Status::TemplateContext)
            message = "template-id references inside template definitions are not supported";
        else if (result.status == Status::TemplateArity)
            message = "template arguments are limited to one or two types or capacity literals";
        else if (result.status == Status::TemplateArgument)
            message = "template arguments require scalar, named class or enum types, or capacities from 1 to 64";
        else if (result.status == Status::CapacityArgument)
            message = "capacity template arguments must be decimal literals from 1 to 64";
        else if (result.status == Status::NestedDependent)
            message = "nested dependent template arguments are not supported";
        else if (result.status == Status::OwnedElement)
            message = "owned values require a named concrete copied class";
        else if (result.status == Status::ArrayElement)
            message = "array elements require i64, u64, u8, bool or a concrete copied class";
        else if (result.status == Status::ArrayLength)
            message = "array length requires a decimal integer literal between 1 and 4096";
        else if (result.status == Status::ClassArrayLength)
            message = "class-element array capacity must be between 1 and 64";
        else if (result.status == Status::ExpectedEnd)
            message = stop == Stop::CloseParenthesis ? "expected ')'" : "expected ';'";
        else
            invalid();
        throw Error(DiagnosticCode::UnexpectedToken, message + " (found '" + at.text + "')", at.span);
    }
    if (result.tokens == 0 || result.count == 0 || result.count > result.tokens || edgeCount >= result.count ||
        typeCount > result.tokens || result.root != result.count - 1 ||
        !(stop == Stop::ConstructorBraces ||
          (stop == Stop::CloseParenthesis ? at.text == ")"
                                          : at.text == ";" || (stop == Stop::Assignment && at.text == "="))))
        invalid();
    const auto size = static_cast<std::size_t>(result.tokens);
    const auto text = [&](std::int64_t ordinal) -> const std::string & {
        if (ordinal < 0 || ordinal >= result.tokens)
            invalid();
        return tokens[position + static_cast<std::size_t>(ordinal)].text;
    };
    std::vector<unsigned char> tokenUsed(size, 0);
    const auto claim = [&](std::int64_t ordinal) {
        if (ordinal < 0 || ordinal >= result.tokens || tokenUsed[static_cast<std::size_t>(ordinal)])
            invalid();
        tokenUsed[static_cast<std::size_t>(ordinal)] = 3;
    };
    const auto punctuation = [&](std::int64_t ordinal, const std::string &expected) {
        if (text(ordinal) != expected)
            invalid();
        claim(ordinal);
    };
    // Match all delimiters independently before any grouping expansion. A call
    // close cannot be borrowed by another call, index, aggregate or grouping node.
    std::vector<std::int64_t> matching(size, -1), openings;
    for (std::int64_t ordinal = 0; ordinal < result.tokens; ++ordinal) {
        const auto &spelling = text(ordinal);
        if (spelling == "(" || spelling == "[" || spelling == "{")
            openings.push_back(ordinal);
        else if (spelling == ")" || spelling == "]" || spelling == "}") {
            if (openings.empty() || text(openings.back()) != (spelling == ")" ? "(" : spelling == "]" ? "[" : "{"))
                invalid();
            matching[static_cast<std::size_t>(ordinal)] = openings.back();
            matching[static_cast<std::size_t>(openings.back())] = ordinal;
            openings.pop_back();
        }
    }
    if (!openings.empty())
        invalid();
    const auto delimiters = [&](std::int64_t open, std::int64_t close, const std::string &opening) {
        punctuation(open, opening);
        punctuation(close, opening == "(" ? ")" : opening == "[" ? "]" : "}");
        if (matching[static_cast<std::size_t>(open)] != close)
            invalid();
    };
    using SyntaxKind = hosted_parser::TypeKind;
    std::vector<TypeSyntax> types(static_cast<std::size_t>(typeCount));
    std::vector<Type> typeValues(static_cast<std::size_t>(typeCount));
    std::vector<std::int64_t> capacities(static_cast<std::size_t>(typeCount), 0);
    std::vector<bool> typeUsed(static_cast<std::size_t>(typeCount), false);
    std::vector<std::int64_t> templateRoots(size, -1), reflectedRoots(size, -1);
    const auto afterType = [&](std::int64_t close) {
        if (close < 0 || close / 2 >= result.tokens || (close % 2 != 0 && text(close / 2) != ">>"))
            invalid();
        return close + (text(close / 2) == ">>" ? 1 : 2);
    };
    const auto angleClose = [&](std::int64_t close) {
        if (close < 0 || close / 2 >= result.tokens)
            invalid();
        const auto &spelling = text(close / 2);
        if (spelling == ">") {
            if (close % 2 != 0)
                invalid();
            claim(close / 2);
        } else if (spelling == ">>") {
            const auto mask = static_cast<unsigned char>(1U << (close % 2));
            auto &used = tokenUsed[static_cast<std::size_t>(close / 2)];
            if ((used & mask) != 0)
                invalid();
            used |= mask;
        } else
            invalid();
    };
    const auto isParameter = [&](const std::string &name, bool capacity) {
        const auto &parameters = capacity ? context.capacityParameters : context.typeParameters;
        return std::any_of(parameters.begin(), parameters.end(), [&](const Token &token) {
            return token.text == name;
        });
    };
    const auto typeNameSpelling = [&](const TypeSyntax &type, bool claimName) {
        if (!identifier(text(type.token)) || (type.nameEnd - type.token) % 2 != 0)
            invalid();
        std::string name = text(type.token);
        if (claimName)
            claim(type.token);
        for (auto tail = type.token + 2; tail <= type.nameEnd; tail += 2) {
            if (text(tail - 1) != "::" || !tailIdentifier(text(tail), true))
                invalid();
            if (claimName) {
                punctuation(tail - 1, "::");
                claim(tail);
            }
            name += "::" + text(tail);
        }
        return name;
    };
    const auto argumentValue = [&](std::int64_t child) {
        const auto &type = types[static_cast<std::size_t>(child)];
        if (type.kind == SyntaxKind::Capacity) {
            const auto capacity = capacities[static_cast<std::size_t>(child)];
            if (capacity < 1 || capacity > 64)
                invalid();
            return TemplateArgument::capacity(capacity);
        }
        if (type.kind != SyntaxKind::I64 && type.kind != SyntaxKind::U64 && type.kind != SyntaxKind::U8 &&
            type.kind != SyntaxKind::Bool && type.kind != SyntaxKind::Named && type.kind != SyntaxKind::Parameter)
            invalid();
        const auto &value = typeValues[static_cast<std::size_t>(child)];
        TemplateArgument argument(value.kind);
        argument.className = value.className;
        argument.templateArguments = value.templateArguments;
        return argument;
    };
    // Copy and validate the complete unresolved type forest before importing it.
    // Every child is backward, uniquely owned, and syntactically contiguous.
    for (std::int64_t index = 0; index < typeCount; ++index) {
        auto &type = types[static_cast<std::size_t>(index)];
        aurora_hosted_parser_type(arena.data(), index, &type);
        if (type.kind <= SyntaxKind::Invalid || type.kind > SyntaxKind::BuiltinClass || type.token < 0 ||
            type.token >= result.tokens || type.nameEnd < type.token || type.nameEnd >= result.tokens ||
            type.close < type.nameEnd * 2 || type.close / 2 >= result.tokens || type.first < -1 || type.second < -1 ||
            type.first >= index || type.second >= index || (type.first == -1 && type.second != -1) ||
            (type.first >= 0 && type.first == type.second))
            invalid();
        afterType(type.close);
        if (type.role == 0) {
            if (type.owner != -1)
                invalid();
        } else {
            if (type.owner < 0 || type.owner >= result.tokens || (type.role != 1 && type.role != 2))
                invalid();
            auto &roots = type.role == 1 ? templateRoots : reflectedRoots;
            if (roots[static_cast<std::size_t>(type.owner)] != -1 ||
                (type.role == 1 && (type.kind != SyntaxKind::Named || type.owner != type.token || type.first < 0)) ||
                (type.role == 2 && type.owner >= type.token))
                invalid();
            roots[static_cast<std::size_t>(type.owner)] = index;
        }
    }
    // Check the reference grammar's independent type and template depth limits.
    // Parameter names confer syntax only; no nominal identity is taken from wire.
    class TypeVisit {
    public:
        std::int64_t index;
        int typeDepth, templateDepth, allowance;
        bool argument;
    };
    std::vector<TypeVisit> visits;
    std::vector<bool> typeVisited(static_cast<std::size_t>(typeCount), false);
    for (std::int64_t index = 0; index < typeCount; ++index) {
        const auto &type = types[static_cast<std::size_t>(index)];
        if (type.role != 0)
            visits.push_back({index, type.role == 1 ? 0 : 1, 0, type.role == 1 ? 1 : 0, false});
    }
    while (!visits.empty()) {
        const auto visit = visits.back();
        visits.pop_back();
        if (visit.index < 0 || visit.index >= typeCount || typeVisited[static_cast<std::size_t>(visit.index)])
            invalid();
        typeVisited[static_cast<std::size_t>(visit.index)] = true;
        const auto &type = types[static_cast<std::size_t>(visit.index)];
        if (visit.typeDepth > 64)
            invalid();
        if (type.kind == SyntaxKind::Named) {
            const auto &first = text(type.token);
            if (type.role != 1) {
                static const std::array<std::string, 17> forbidden{"fn",
                                                                   "let",
                                                                   "mut",
                                                                   "auto",
                                                                   "const",
                                                                   "class",
                                                                   "unsafe",
                                                                   "struct",
                                                                   "extern",
                                                                   "int",
                                                                   "void",
                                                                   "char",
                                                                   "float",
                                                                   "double",
                                                                   "new",
                                                                   "delete",
                                                                   "enum"};
                if (first == "i64" || first == "u64" || first == "u8" || first == "bool" || first == "own" ||
                    first == "ref" || first == "mutref" || first == "array" || first == "builtin" ||
                    (!visit.argument && isParameter(first, false)) ||
                    (visit.argument ? !tailIdentifier(first, false) || isParameter(typeNameSpelling(type, false), false)
                                    : std::find(forbidden.begin(), forbidden.end(), first) != forbidden.end()))
                    invalid();
            }
            if (type.first >= 0) {
                const auto depth = visit.templateDepth + 1;
                if (depth > maximumTemplateNesting + visit.allowance)
                    invalid();
                visits.push_back({type.first, visit.typeDepth, depth, visit.allowance, true});
                if (type.second >= 0)
                    visits.push_back({type.second, visit.typeDepth, depth, visit.allowance, true});
            }
        } else if (type.kind == SyntaxKind::Parameter) {
            // Declaration identifiers such as int are legal parameter names,
            // but type() rejects reserved type spellings before context lookup.
            static const std::array<std::string, 7> reservedParameterTypes{
                "int", "void", "char", "float", "double", "new", "delete"};
            if ((visit.argument && visit.templateDepth != 1) ||
                (!visit.argument &&
                 std::find(reservedParameterTypes.begin(), reservedParameterTypes.end(), text(type.token)) !=
                     reservedParameterTypes.end()))
                invalid();
        } else if (type.kind == SyntaxKind::Capacity || type.kind == SyntaxKind::LengthParameter) {
            if (type.role != 0 || (type.kind == SyntaxKind::LengthParameter && visit.argument))
                invalid();
        } else if (type.kind == SyntaxKind::Array || type.kind == SyntaxKind::OwnedValues) {
            if (visit.argument || type.first < 0 ||
                (type.kind == SyntaxKind::Array ? type.second < 0 : type.second != -1))
                invalid();
            visits.push_back({type.first, visit.typeDepth + 1, visit.templateDepth, visit.allowance, false});
            if (type.second >= 0)
                visits.push_back({type.second, visit.typeDepth, visit.templateDepth, visit.allowance, false});
        }
    }
    if (std::find(typeVisited.begin(), typeVisited.end(), false) != typeVisited.end())
        invalid();
    // Only a bounded, complete forest is converted into recursive host values.
    for (std::int64_t index = 0; index < typeCount; ++index) {
        const auto &type = types[static_cast<std::size_t>(index)];
        const auto child = [&](std::int64_t childIndex) -> const TypeSyntax & {
            if (childIndex < 0 || childIndex >= index || typeUsed[static_cast<std::size_t>(childIndex)])
                invalid();
            const auto &value = types[static_cast<std::size_t>(childIndex)];
            if (value.role != 0 || value.owner != -1)
                invalid();
            typeUsed[static_cast<std::size_t>(childIndex)] = true;
            return value;
        };
        const auto atomic = [&]() {
            if (type.first != -1 || type.second != -1 || type.nameEnd != type.token || type.close != type.token * 2)
                invalid();
            claim(type.token);
        };
        auto &value = typeValues[static_cast<std::size_t>(index)];
        const auto &spelling = text(type.token);
        if (type.kind == SyntaxKind::I64 || type.kind == SyntaxKind::U64 || type.kind == SyntaxKind::U8 ||
            type.kind == SyntaxKind::Bool) {
            atomic();
            const auto expected = type.kind == SyntaxKind::I64   ? "i64"
                                  : type.kind == SyntaxKind::U64 ? "u64"
                                  : type.kind == SyntaxKind::U8  ? "u8"
                                                                 : "bool";
            if (spelling != expected)
                invalid();
            value = type.kind == SyntaxKind::I64   ? Type::I64
                    : type.kind == SyntaxKind::U64 ? Type::U64
                    : type.kind == SyntaxKind::U8  ? Type::U8
                                                   : Type::Bool;
        } else if (type.kind == SyntaxKind::Parameter || type.kind == SyntaxKind::LengthParameter) {
            atomic();
            if (!isParameter(spelling, type.kind == SyntaxKind::LengthParameter))
                invalid();
            value = Type(TypeKind::Parameter);
            value.className = spelling;
        } else if (type.kind == SyntaxKind::Capacity) {
            atomic();
            std::int64_t capacity = 0;
            for (const auto byte : spelling) {
                if (byte < '0' || byte > '9' || capacity > 4096)
                    invalid();
                capacity = capacity * 10 + byte - '0';
            }
            if (capacity < 1 || capacity > 4096)
                invalid();
            capacities[static_cast<std::size_t>(index)] = capacity;
        } else if (type.kind == SyntaxKind::Named) {
            const auto name = typeNameSpelling(type, type.role != 1);
            value = Type(name);
            if (type.first < 0) {
                if (type.close != type.nameEnd * 2)
                    invalid();
            } else {
                if (input.mode == 1)
                    invalid();
                punctuation(type.nameEnd + 1, "<");
                const auto &first = child(type.first);
                if (first.token != type.nameEnd + 2)
                    invalid();
                value.templateArguments.push_back(argumentValue(type.first));
                auto next = afterType(first.close);
                if (type.second >= 0) {
                    if (next % 2 != 0)
                        invalid();
                    punctuation(next / 2, ",");
                    const auto &second = child(type.second);
                    if (second.token * 2 != next + 2)
                        invalid();
                    value.templateArguments.push_back(argumentValue(type.second));
                    next = afterType(second.close);
                }
                if (next != type.close)
                    invalid();
                angleClose(type.close);
            }
        } else if (type.kind == SyntaxKind::Own || type.kind == SyntaxKind::Ref || type.kind == SyntaxKind::MutRef) {
            if (type.first != -1 || type.second != -1 || type.nameEnd != type.token ||
                type.close != (type.token + 3) * 2 || text(type.close / 2) != ">" ||
                spelling != (type.kind == SyntaxKind::Own   ? "own"
                             : type.kind == SyntaxKind::Ref ? "ref"
                                                            : "mutref"))
                invalid();
            claim(type.token);
            punctuation(type.token + 1, "<");
            punctuation(type.token + 2, "i64");
            angleClose(type.close);
            value = type.kind == SyntaxKind::Own ? Type::Own : type.kind == SyntaxKind::Ref ? Type::Ref : Type::MutRef;
        } else {
            const bool qualified = spelling == "builtin";
            if (type.nameEnd != type.token + (qualified ? 2 : 0) ||
                (!qualified && (type.kind != SyntaxKind::Array || spelling != "array")))
                invalid();
            claim(type.token);
            if (qualified) {
                punctuation(type.token + 1, "::");
                claim(type.nameEnd);
            }
            const auto &name = text(type.nameEnd);
            if (type.kind == SyntaxKind::Builtin || type.kind == SyntaxKind::BuiltinClass) {
                if (!qualified || type.first != -1 || type.second != -1 || type.close != type.nameEnd * 2)
                    invalid();
                if ((type.kind == SyntaxKind::BuiltinClass) != (name == "ConsoleSample" || name == "IommuEventSample"))
                    invalid();
                if (name == "ByteRegion")
                    value = Type::ByteRegion;
                else if (name == "OwnedBytes")
                    value = Type::OwnedBytes;
                else if (name == "ConsoleSession")
                    value = Type::ConsoleSession;
                else if (name == "DisplaySession")
                    value = Type::DisplaySession;
                else if (name == "IommuEventSession")
                    value = Type::IommuEventSession;
                else if (name == "ConsoleSample")
                    value = service::sampleType();
                else if (name == "ConsolePutResult")
                    value = service::putResultType();
                else if (name == "ConsoleCompletion")
                    value = service::completionType();
                else if (name == "DisplayPutResult")
                    value = service::displayPutResultType();
                else if (name == "DisplayCompletion")
                    value = service::displayCompletionType();
                else if (name == "IommuEventSample")
                    value = service::eventSampleType();
                else if (name == "EventPollResult")
                    value = service::eventPollResultType();
                else if (name == "EventAckResult")
                    value = service::eventAckResultType();
                else if (name == "EventIntakeCompletion")
                    value = service::eventIntakeCompletionType();
                else
                    invalid();
            } else if (type.kind == SyntaxKind::ByteSpan) {
                if (!qualified || name != "span" || type.first != -1 || type.second != -1 ||
                    type.close != (type.nameEnd + 4) * 2 || text(type.close / 2) != ">")
                    invalid();
                punctuation(type.nameEnd + 1, "<");
                punctuation(type.nameEnd + 2, "const");
                punctuation(type.nameEnd + 3, "u8");
                angleClose(type.close);
                value = Type::ByteSpan;
            } else if (type.kind == SyntaxKind::Array || type.kind == SyntaxKind::OwnedValues) {
                if (name != (type.kind == SyntaxKind::Array ? "array" : "OwnedValues"))
                    invalid();
                punctuation(type.nameEnd + 1, "<");
                const auto &elementSyntax = child(type.first);
                const auto &element = typeValues[static_cast<std::size_t>(type.first)];
                if (elementSyntax.token != type.nameEnd + 2)
                    invalid();
                auto next = afterType(elementSyntax.close);
                if (type.kind == SyntaxKind::OwnedValues) {
                    if (!qualified || type.second != -1 || !element.isClass() || !element.templateArguments.empty())
                        invalid();
                    value = Type::ownedValues(element);
                } else {
                    if (elementSyntax.kind == SyntaxKind::Capacity ||
                        elementSyntax.kind == SyntaxKind::LengthParameter ||
                        (!scalar(element) && element.kind != TypeKind::Parameter && !element.isClass()))
                        invalid();
                    if (next % 2 != 0)
                        invalid();
                    punctuation(next / 2, ",");
                    const auto &length = child(type.second);
                    if (length.token * 2 != next + 2 ||
                        (length.kind != SyntaxKind::Capacity && length.kind != SyntaxKind::LengthParameter))
                        invalid();
                    value = Type::array(element, static_cast<int>(capacities[static_cast<std::size_t>(type.second)]));
                    if (length.kind == SyntaxKind::LengthParameter)
                        value.lengthParameter = text(length.token);
                    else if (element.isClass() && value.length > maximumClassScalarArrayLength)
                        invalid();
                    next = afterType(length.close);
                }
                if (next != type.close)
                    invalid();
                angleClose(type.close);
            } else
                invalid();
        }
    }
    std::vector<Node> records(static_cast<std::size_t>(result.count));
    std::vector<Edge> edges(static_cast<std::size_t>(edgeCount));
    std::vector<std::int64_t> nodeOpen(static_cast<std::size_t>(result.count), -1);
    // Claim every node's own syntax up front, so child grouping cannot consume
    // a call's parentheses. Names retain the original first token and its span.
    for (std::int64_t index = 0; index < result.count; ++index) {
        auto &node = records[static_cast<std::size_t>(index)];
        aurora_hosted_parser_read(arena.data(), index, &node);
        if (node.token < 0 || node.token >= result.tokens || node.nameEnd < node.token ||
            node.nameEnd >= result.tokens || node.close < node.nameEnd || node.close >= result.tokens ||
            node.depth < 1 || node.depth > 128)
            invalid();
        const auto &spelling = text(node.token);
        const auto templateRoot = templateRoots[static_cast<std::size_t>(node.token)];
        const auto reflectedRoot = reflectedRoots[static_cast<std::size_t>(node.token)];
        if ((templateRoot >= 0 && node.kind != NodeKind::Call && node.kind != NodeKind::Construct) ||
            (reflectedRoot >= 0 && node.kind != NodeKind::Call))
            invalid();
        const bool constructorRoot = stop == Stop::ConstructorBraces && index == result.root;
        if (constructorRoot) {
            if (node.token != 0 || node.nameEnd != 0 || node.close != result.tokens - 1 ||
                !tailIdentifier(spelling, false) ||
                (node.kind != NodeKind::ArrayLiteral && node.kind != NodeKind::ArrayZero) ||
                (node.kind == NodeKind::ArrayZero) != (node.second == 0))
                invalid();
            claim(node.token);
            delimiters(1, node.close, "{");
        } else if (node.kind == NodeKind::Name || node.kind == NodeKind::Call || node.kind == NodeKind::Construct) {
            if (!identifier(spelling) || spelling == "true" || spelling == "false" ||
                (node.nameEnd - node.token) % 2 != 0)
                invalid();
            claim(node.token);
            for (auto tail = node.token + 2; tail <= node.nameEnd; tail += 2) {
                punctuation(tail - 1, "::");
                if (!tailIdentifier(text(tail), true))
                    invalid();
                claim(tail);
            }
            if (node.kind == NodeKind::Name) {
                if (node.close != node.nameEnd)
                    invalid();
            } else {
                auto open = node.nameEnd + 1;
                if (templateRoot >= 0) {
                    const auto &root = types[static_cast<std::size_t>(templateRoot)];
                    if (root.token != node.token || root.nameEnd != node.nameEnd ||
                        typeUsed[static_cast<std::size_t>(templateRoot)] || afterType(root.close) % 2 != 0)
                        invalid();
                    typeUsed[static_cast<std::size_t>(templateRoot)] = true;
                    open = afterType(root.close) / 2;
                }
                const bool reflection = node.kind == NodeKind::Call && node.nameEnd == node.token &&
                                        (spelling == "size_of" || spelling == "type_id" || spelling == "field_count");
                if (reflection != (reflectedRoot >= 0))
                    invalid();
                if (reflectedRoot >= 0) {
                    const auto &root = types[static_cast<std::size_t>(reflectedRoot)];
                    if (root.token != open + 1 || afterType(root.close) != node.close * 2 || node.first != -1 ||
                        node.second != 0 || typeUsed[static_cast<std::size_t>(reflectedRoot)])
                        invalid();
                    typeUsed[static_cast<std::size_t>(reflectedRoot)] = true;
                }
                nodeOpen[static_cast<std::size_t>(index)] = open;
                delimiters(open, node.close, node.kind == NodeKind::Construct ? "{" : "(");
            }
        } else if (node.kind == NodeKind::Member || node.kind == NodeKind::MethodCall) {
            if (node.nameEnd != node.token || !tailIdentifier(spelling, false))
                invalid();
            punctuation(node.token - 1, ".");
            claim(node.token);
            if (node.kind == NodeKind::Member) {
                if (node.close != node.token)
                    invalid();
            } else
                delimiters(node.token + 1, node.close, "(");
        } else if (node.kind == NodeKind::Index) {
            if (node.nameEnd != node.token)
                invalid();
            delimiters(node.token, node.close, "[");
        } else if (node.kind == NodeKind::ArrayLiteral) {
            if (node.nameEnd != node.token)
                invalid();
            delimiters(node.token, node.close, "{");
        } else {
            if (node.nameEnd != node.token || node.close != node.token ||
                (node.kind != NodeKind::Literal && node.kind != NodeKind::Unary && node.kind != NodeKind::Binary))
                invalid();
            claim(node.token);
        }
    }
    for (std::int64_t index = 0; index < edgeCount; ++index) {
        auto &edge = edges[static_cast<std::size_t>(index)];
        aurora_hosted_parser_edge(arena.data(), index, &edge);
        if (edge.child < 0 || edge.child >= result.count || edge.previous < -1 || edge.previous >= index ||
            edge.field < -1 || edge.field >= result.tokens)
            invalid();
        const auto childDepth = records[static_cast<std::size_t>(edge.child)].depth + 1;
        const auto previousCount = edge.previous < 0 ? 0 : edges[static_cast<std::size_t>(edge.previous)].count;
        const auto previousDepth = edge.previous < 0 ? 1 : edges[static_cast<std::size_t>(edge.previous)].depth;
        if (edge.count != previousCount + 1 || edge.depth != std::max(previousDepth, childDepth) || edge.depth > 128)
            invalid();
    }
    std::vector<ExpressionPtr> nodes;
    std::vector<bool> used(static_cast<std::size_t>(result.count), false);
    std::vector<bool> edgeUsed(static_cast<std::size_t>(edgeCount), false), postfixAllowed;
    std::vector<std::pair<std::int64_t, std::int64_t>> bounds;
    nodes.reserve(records.size());
    bounds.reserve(records.size());
    postfixAllowed.reserve(records.size());
    for (std::int64_t index = 0; index < result.count; ++index) {
        const auto &node = records[static_cast<std::size_t>(index)];
        auto token = tokens[position + static_cast<std::size_t>(node.token)];
        std::string op;
        if (node.kind == NodeKind::Name || node.kind == NodeKind::Call || node.kind == NodeKind::Construct) {
            op = node.kind == NodeKind::Name ? "name" : node.kind == NodeKind::Call ? "call" : "construct";
            for (auto tail = node.token + 2; tail <= node.nameEnd; tail += 2)
                token.text += "::" + text(tail);
            token.span.end = tokens[position + static_cast<std::size_t>(node.nameEnd)].span.end;
        } else if (node.kind == NodeKind::Literal && (token.text == "true" || token.text == "false"))
            op = "bool";
        else if (node.kind == NodeKind::Literal && token.text.front() == '"')
            op = "byte_string";
        else if (node.kind == NodeKind::Literal && token.text.front() == '\'')
            op = "byte";
        else if (node.kind == NodeKind::Literal && token.text.front() >= '0' && token.text.front() <= '9')
            op = "number";
        else if (node.kind == NodeKind::Unary && (token.text == "-" || token.text == "!" || token.text == "~"))
            op = "unary";
        else if (node.kind == NodeKind::Binary && binary(token.text))
            op = "binary";
        else if (node.kind == NodeKind::Member)
            op = "member";
        else if (node.kind == NodeKind::MethodCall)
            op = "method_call";
        else if (node.kind == NodeKind::Index)
            op = "index";
        else if (node.kind == NodeKind::ArrayLiteral)
            op = "array_literal";
        else if (node.kind == NodeKind::ArrayZero)
            op = "array_zero";
        else
            invalid();
        auto expression = std::make_shared<Expression>(op, token);
        const auto templateRoot = templateRoots[static_cast<std::size_t>(node.token)];
        const auto reflectedRoot = reflectedRoots[static_cast<std::size_t>(node.token)];
        if (templateRoot >= 0)
            expression->templateArguments = typeValues[static_cast<std::size_t>(templateRoot)].templateArguments;
        if (reflectedRoot >= 0)
            expression->reflectedType = typeValues[static_cast<std::size_t>(reflectedRoot)];
        auto firstToken = node.token, lastToken = node.close;
        const auto attach = [&](std::int64_t child) {
            if (child < 0 || child >= index || used[static_cast<std::size_t>(child)])
                invalid();
            used[static_cast<std::size_t>(child)] = true;
            const auto &value = nodes[static_cast<std::size_t>(child)];
            expression->depth = std::max(expression->depth, value->depth + 1);
            if (expression->depth > 128)
                invalid();
            expression->args.push_back(value);
            return bounds[static_cast<std::size_t>(child)];
        };
        const auto receiver = [&](std::int64_t child, std::int64_t following) {
            const auto range = attach(child);
            if (!postfixAllowed[static_cast<std::size_t>(child)] || range.second + 1 != following)
                invalid();
            firstToken = range.first;
        };
        if (node.kind == NodeKind::Call || node.kind == NodeKind::MethodCall || node.kind == NodeKind::ArrayLiteral ||
            node.kind == NodeKind::Construct || node.kind == NodeKind::ArrayZero) {
            if (node.second < 0 || node.second > edgeCount || (node.first == -1) != (node.second == 0) ||
                (node.kind == NodeKind::MethodCall && node.second == 0))
                invalid();
            std::vector<std::int64_t> children;
            for (auto edge = node.first; edge != -1;) {
                if (edge < 0 || edge >= edgeCount || edgeUsed[static_cast<std::size_t>(edge)])
                    invalid();
                edgeUsed[static_cast<std::size_t>(edge)] = true;
                const auto &record = edges[static_cast<std::size_t>(edge)];
                if ((node.kind == NodeKind::Construct) != (record.field >= 0))
                    invalid();
                children.push_back(edge);
                edge = record.previous;
            }
            if (children.size() != static_cast<std::size_t>(node.second) ||
                (node.first != -1 && edges[static_cast<std::size_t>(node.first)].depth != node.depth))
                invalid();
            std::reverse(children.begin(), children.end());
            std::size_t argument = 0;
            if (node.kind == NodeKind::MethodCall) {
                receiver(edges[static_cast<std::size_t>(children.front())].child, node.token - 1);
                argument = 1;
            }
            const bool constructorRoot = stop == Stop::ConstructorBraces && index == result.root;
            auto next = node.kind == NodeKind::ArrayLiteral && !constructorRoot ? node.token + 1 : node.nameEnd + 2;
            if (node.kind == NodeKind::Call || node.kind == NodeKind::Construct)
                next = reflectedRoot >= 0 ? node.close : nodeOpen[static_cast<std::size_t>(index)] + 1;
            for (; argument < children.size(); ++argument) {
                const auto &edge = edges[static_cast<std::size_t>(children[argument])];
                if (node.kind == NodeKind::Construct) {
                    if (edge.field != next + 1 || !tailIdentifier(text(edge.field), false))
                        invalid();
                    punctuation(next, ".");
                    claim(edge.field);
                    punctuation(next + 2, "=");
                    expression->fieldNames.push_back(text(edge.field));
                    next += 3;
                }
                const auto range = attach(edge.child);
                if (range.first != next || range.second >= node.close)
                    invalid();
                next = range.second + 1;
                if (argument + 1 < children.size())
                    punctuation(next++, ",");
            }
            if (next != node.close)
                invalid();
        } else if (node.kind == NodeKind::Unary) {
            const auto range = attach(node.first);
            if (node.second != -1 || range.first != node.token + 1)
                invalid();
            lastToken = range.second;
        } else if (node.kind == NodeKind::Binary) {
            const auto left = attach(node.first), right = attach(node.second);
            if (left.second + 1 != node.token || right.first != node.token + 1)
                invalid();
            firstToken = left.first;
            lastToken = right.second;
        } else if (node.kind == NodeKind::Member) {
            if (node.second != -1)
                invalid();
            receiver(node.first, node.token - 1);
        } else if (node.kind == NodeKind::Index) {
            receiver(node.first, node.token);
            const auto subscript = attach(node.second);
            if (subscript.first != node.token + 1 || subscript.second + 1 != node.close)
                invalid();
            // The reference AST locates indexing at the base expression's token.
            expression->token = nodes[static_cast<std::size_t>(node.first)]->token;
        } else if (node.first != -1 || node.second != -1)
            invalid();
        if (node.depth != expression->depth)
            invalid();
        bool grouped = false;
        while (firstToken > 0 && lastToken + 1 < result.tokens && text(firstToken - 1) == "(" &&
               !tokenUsed[static_cast<std::size_t>(firstToken - 1)] &&
               matching[static_cast<std::size_t>(firstToken - 1)] == lastToken + 1 &&
               !tokenUsed[static_cast<std::size_t>(lastToken + 1)]) {
            claim(--firstToken);
            claim(++lastToken);
            grouped = true;
        }
        postfixAllowed.push_back(grouped || node.kind == NodeKind::Name || node.kind == NodeKind::Call ||
                                 node.kind == NodeKind::Member || node.kind == NodeKind::MethodCall ||
                                 node.kind == NodeKind::Index || node.kind == NodeKind::ArrayLiteral ||
                                 node.kind == NodeKind::Construct);
        bounds.emplace_back(firstToken, lastToken);
        nodes.push_back(std::move(expression));
    }
    if (std::count(used.begin(), used.end(), false) != 1 || used.back() ||
        std::find(edgeUsed.begin(), edgeUsed.end(), false) != edgeUsed.end() ||
        std::find(typeUsed.begin(), typeUsed.end(), false) != typeUsed.end() ||
        std::find_if(tokenUsed.begin(),
                     tokenUsed.end(),
                     [](unsigned char used) {
                         return used != 3;
                     }) != tokenUsed.end() ||
        bounds.back() != std::pair<std::int64_t, std::int64_t>{0, result.tokens - 1})
        invalid();
    position = end;
    return nodes.back();
}
} // namespace aurora
