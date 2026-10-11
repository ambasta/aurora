// Trusted hosted bootstrap boundary. Source snapshots remain immutable and live
// throughout each synchronous call; no owner descriptor or payload pointer is
// constructed, copied or inspected here.
#include "hosted_parser.hpp"
#include "services.hpp"
#include "../runtime/hosted_bytes.hpp"
#include <algorithm>
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
std::int64_t aurora_hosted_parser_statements(const void *);
void aurora_hosted_parser_statement(const void *, std::int64_t, void *);
void aurora_hosted_parser_release(void *);
}

namespace aurora {
namespace {
using hosted_parser::NodeKind;
using hosted_parser::StatementKind;
using hosted_parser::Status;
using hosted_parser::Stop;
using Input = hosted_abi::ParserInput;
using Result = hosted_abi::ParseResult;
using Node = hosted_abi::Node;
using Edge = hosted_abi::Edge;
using TypeSyntax = hosted_abi::TypeSyntax;
using StatementSyntax = hosted_abi::StatementSyntax;
class Arena {
    hosted::bytes::Region region;
    hosted_abi::ParserRelease record;

public:
    explicit Arena(std::uint64_t quota) : region(quota) {
        record.region = region.id();
        hosted_abi::ParserCreate input;
        input.region = region.id();
        aurora_hosted_parser_create(&input, data());
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

[[noreturn]] void invalid() {
    throw Error(DiagnosticCode::Internal, "hosted parser returned an invalid result");
}
class ImportedSyntax {
public:
    ExpressionPtr expression;
    std::vector<StatementPtr> body;
};

ImportedSyntax parseHostedSyntax(const std::vector<Token> &tokens,
                                 std::size_t &position,
                                 Stop stop,
                                 const hosted_parser::Context &context) {
    const bool body = stop == Stop::Body;
    if (position >= tokens.size())
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
    if (context.typeParameters.size() > 2 || context.capacityParameters.size() > 1)
        invalid();
    const auto parameter = [&](const Token &token, std::int64_t &first, std::int64_t &last) {
        const auto &span = token.span;
        if (span.begin.offset >= span.end.offset || span.end.offset > begin.begin.offset)
            invalid();
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
    // Each monotone store has at most N records; template candidates add at most
    // N frames. Capacity <= 2*used+8 includes every minimum allocation. Other
    // live frames are bounded by body256 + expression1549 + type70 = 1875.
    // The region charges replacement payload, not metadata or old+new resize bytes.
    constexpr std::uint64_t recordBytes = sizeof(Node) + sizeof(Edge) + sizeof(TypeSyntax) + sizeof(StatementSyntax);
    constexpr std::uint64_t perToken = 2 * (recordBytes + hosted_abi::frameBytes);
    constexpr std::uint64_t fixedBytes = 8 * recordBytes + (2 * 1875 + 8) * hosted_abi::frameBytes;
    if (source->text.size() > (std::numeric_limits<std::uint64_t>::max() - fixedBytes) / perToken)
        invalid();
    Arena arena(static_cast<std::uint64_t>(source->text.size()) * perToken + fixedBytes);
    Result result;
    aurora_hosted_parser_parse(arena.data(), &input, &result);
    const auto actualCount = aurora_hosted_parser_count(arena.data());
    const auto edgeCount = aurora_hosted_parser_edges(arena.data());
    const auto typeCount = aurora_hosted_parser_types(arena.data());
    const auto statementCount = aurora_hosted_parser_statements(arena.data());
    if (result.status < Status::Success || result.status >= Status::Invalid || result.count < 0 ||
        result.count != actualCount || edgeCount < 0 || typeCount < 0 || statementCount < 0 ||
        (!body && statementCount != 0) || result.tokens < 0 ||
        static_cast<std::uint64_t>(result.tokens) >= tokens.size() - position || result.offset < input.offset ||
        result.offset > input.length)
        invalid();
    if (result.status == Status::Unsupported)
        invalid();
    const auto end = position + static_cast<std::size_t>(result.tokens);
    for (auto index = position; index <= end; ++index) {
        const auto &token = tokens[index];
        const auto &span = token.span;
        if (!span.source || span.begin.offset > span.end.offset || span.end.offset > span.source->text.size() ||
            token.text.empty())
            invalid();
    }
    auto at = tokens[end];
    if (static_cast<std::size_t>(result.offset) != at.span.begin.offset) {
        if (result.status == Status::Success || at.text != ">>" || at.span.end.offset - at.span.begin.offset != 2 ||
            static_cast<std::size_t>(result.offset) != at.span.begin.offset + 1 ||
            at.span.begin.column == std::numeric_limits<int>::max())
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
        if ((!body && result.status >= Status::ExpectedOpen) || (body && result.status == Status::ExpectedEnd))
            invalid();
        if (result.status == Status::BlockNestingLimit)
            throw Error(DiagnosticCode::NestingLimit, "block nesting exceeds 128", at.span);
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
        else if (result.status == Status::ExpectedOpen)
            message = "expected '('";
        else if (result.status == Status::ExpectedSemicolon)
            message = "expected ';'";
        else if (result.status == Status::UnterminatedBlock)
            message = "unterminated block";
        else if (result.status == Status::AssignmentTarget)
            message = "assignment requires a local or local field";
        else if (result.status == Status::ExpectedEnd)
            message = stop == Stop::CloseParenthesis ? "expected ')'" : "expected ';'";
        else
            invalid();
        throw Error(DiagnosticCode::UnexpectedToken, message + " (found '" + at.text + "')", at.span);
    }
    if (result.tokens == 0 || result.count > result.tokens || typeCount > result.tokens ||
        statementCount > result.tokens || (result.count == 0 ? edgeCount != 0 : edgeCount >= result.count) ||
        (body ? statementCount == 0 || result.root != statementCount - 1
              : result.count == 0 || result.root != result.count - 1))
        invalid();
    const auto text = [&](std::int64_t ordinal) -> const std::string & {
        if (ordinal < 0 || ordinal >= result.tokens)
            invalid();
        return tokens[position + static_cast<std::size_t>(ordinal)].text;
    };
    const auto name = [&](std::int64_t first, std::int64_t last) {
        if (first < 0 || last < first || last >= result.tokens)
            invalid();
        std::string value;
        for (auto ordinal = first; ordinal <= last; ++ordinal)
            value += text(ordinal);
        return value;
    };
    // Statements form a closed, child-before-parent tree. These are ownership,
    // index and construction-depth checks; Aurora owns all statement grammar.
    std::vector<StatementSyntax> statements(static_cast<std::size_t>(statementCount));
    std::vector<bool> statementUsed(static_cast<std::size_t>(statementCount), false);
    std::vector<std::vector<std::int64_t>> statementLists(static_cast<std::size_t>(statementCount));
    std::vector<int> blockDepth(static_cast<std::size_t>(statementCount), 0);
    for (std::int64_t index = 0; index < statementCount; ++index) {
        auto &statement = statements[static_cast<std::size_t>(index)];
        aurora_hosted_parser_statement(arena.data(), index, &statement);
        if (statement.kind <= StatementKind::Invalid || statement.kind > StatementKind::IndexAssign ||
            statement.token < 0 || statement.token >= statement.end || statement.end > result.tokens ||
            statement.previous < -1 || statement.previous >= index || statement.expression < -1 ||
            statement.expression >= result.count || statement.target < -1 || statement.target >= result.count ||
            statement.declaredType < -1 || statement.declaredType >= typeCount || statement.binding < -1 ||
            statement.binding >= result.tokens || statement.body < -1 || statement.body >= index ||
            statement.other < -1 || statement.other >= index ||
            (statement.mutableValue != 0 && statement.mutableValue != 1))
            invalid();
        const bool local = statement.kind == StatementKind::Local;
        const bool block = statement.kind == StatementKind::Block;
        const bool conditional = statement.kind == StatementKind::Conditional;
        const bool loop = statement.kind == StatementKind::Loop;
        const bool assignment = statement.kind == StatementKind::Assign ||
                                statement.kind == StatementKind::FieldAssign ||
                                statement.kind == StatementKind::IndexAssign;
        if ((statement.expression == -1) != block || (statement.target >= 0) != assignment ||
            (statement.declaredType >= 0) != local || (statement.binding >= 0) != local ||
            (!local && statement.mutableValue != 0) || (!block && !conditional && !loop && statement.body != -1) ||
            ((conditional || loop) && statement.body == -1) || (!conditional && statement.other != -1))
            invalid();
        const auto ownStatement = [&](std::int64_t child) -> const StatementSyntax & {
            if (child < 0 || child >= index || statementUsed[static_cast<std::size_t>(child)])
                invalid();
            statementUsed[static_cast<std::size_t>(child)] = true;
            return statements[static_cast<std::size_t>(child)];
        };
        auto &depth = blockDepth[static_cast<std::size_t>(index)];
        if (block) {
            auto &children = statementLists[static_cast<std::size_t>(index)];
            for (auto child = statement.body; child != -1;) {
                const auto &value = ownStatement(child);
                depth = std::max(depth, blockDepth[static_cast<std::size_t>(child)]);
                children.push_back(child);
                child = value.previous;
            }
            std::reverse(children.begin(), children.end());
            if (++depth > 128)
                invalid();
        } else if (conditional || loop) {
            const auto &branch = ownStatement(statement.body);
            if (branch.kind != StatementKind::Block || branch.previous != -1)
                invalid();
            // Control nodes unwrap their block records, so they add no extra
            // lexical nesting beyond those blocks.
            depth = blockDepth[static_cast<std::size_t>(statement.body)];
            if (statement.other >= 0) {
                const auto &other = ownStatement(statement.other);
                if (other.kind != StatementKind::Block || other.previous != -1)
                    invalid();
                depth = std::max(depth, blockDepth[static_cast<std::size_t>(statement.other)]);
            }
        }
    }
    if (body) {
        const auto &root = statements[static_cast<std::size_t>(result.root)];
        if (root.kind != StatementKind::Block || root.previous != -1 ||
            statementUsed[static_cast<std::size_t>(result.root)])
            invalid();
        statementUsed[static_cast<std::size_t>(result.root)] = true;
        if (std::find(statementUsed.begin(), statementUsed.end(), false) != statementUsed.end())
            invalid();
    }
    using SyntaxKind = hosted_parser::TypeKind;
    std::vector<TypeSyntax> types(static_cast<std::size_t>(typeCount));
    std::vector<Type> typeValues(static_cast<std::size_t>(typeCount));
    std::vector<std::int64_t> capacities(static_cast<std::size_t>(typeCount), 0);
    std::vector<bool> typeUsed(static_cast<std::size_t>(typeCount), false);
    std::vector<int> typeDepth(static_cast<std::size_t>(typeCount), 1);
    std::vector<std::int64_t> templateRoots(static_cast<std::size_t>(result.tokens), -1);
    std::vector<std::int64_t> reflectedRoots(static_cast<std::size_t>(result.tokens), -1);
    std::vector<std::int64_t> declarationRoots(static_cast<std::size_t>(result.tokens), -1);
    // Aurora owns grammar validation. Here each recursive host value has one
    // owner and bounded structural depth, so forged DAGs cannot amplify copies.
    // This is a host construction limit, not a replay of type/template nesting.
    for (std::int64_t index = 0; index < typeCount; ++index) {
        auto &type = types[static_cast<std::size_t>(index)];
        aurora_hosted_parser_type(arena.data(), index, &type);
        if (type.kind <= SyntaxKind::Invalid || type.kind > SyntaxKind::BuiltinClass || type.token < 0 ||
            type.token >= result.tokens || type.nameEnd < type.token || type.nameEnd >= result.tokens ||
            type.close < 0 || type.close / 2 >= result.tokens || type.first < -1 || type.second < -1 ||
            type.first >= index || type.second >= index || (type.first == -1 && type.second != -1))
            invalid();
        if (type.role == 0) {
            if (type.owner != -1)
                invalid();
        } else {
            if (type.owner < 0 || type.owner >= result.tokens ||
                (type.role != 1 && type.role != 2 && !(body && type.role == 3)) ||
                (type.role == 1 && (type.kind != SyntaxKind::Named || type.first < 0)) ||
                type.kind == SyntaxKind::Capacity || type.kind == SyntaxKind::LengthParameter)
                invalid();
            auto &roots = type.role == 1 ? templateRoots : type.role == 2 ? reflectedRoots : declarationRoots;
            if (roots[static_cast<std::size_t>(type.owner)] != -1)
                invalid();
            roots[static_cast<std::size_t>(type.owner)] = index;
        }
        auto &depth = typeDepth[static_cast<std::size_t>(index)];
        for (const auto child : {type.first, type.second}) {
            if (child < 0)
                continue;
            const auto ordinal = static_cast<std::size_t>(child);
            if (typeUsed[ordinal] || types[ordinal].role != 0)
                invalid();
            typeUsed[ordinal] = true;
            depth = std::max(depth, typeDepth[ordinal] + 1);
        }
        if (depth > 128)
            invalid();
    }
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
        auto &value = typeValues[static_cast<std::size_t>(child)];
        TemplateArgument argument(value.kind);
        argument.className = std::move(value.className);
        argument.templateArguments = std::move(value.templateArguments);
        return argument;
    };
    for (std::int64_t index = 0; index < typeCount; ++index) {
        const auto &type = types[static_cast<std::size_t>(index)];
        // Validate representation arity before indexing or constructing a Type.
        if (type.kind == SyntaxKind::Array) {
            if (type.first < 0 || type.second < 0)
                invalid();
        } else if (type.kind == SyntaxKind::OwnedValues) {
            if (type.first < 0 || type.second != -1)
                invalid();
        } else if (type.kind != SyntaxKind::Named && (type.first != -1 || type.second != -1))
            invalid();
        auto &value = typeValues[static_cast<std::size_t>(index)];
        const auto &spelling = text(type.token);
        if (type.kind == SyntaxKind::I64 || type.kind == SyntaxKind::U64 || type.kind == SyntaxKind::U8 ||
            type.kind == SyntaxKind::Bool) {
            value = type.kind == SyntaxKind::I64   ? Type::I64
                    : type.kind == SyntaxKind::U64 ? Type::U64
                    : type.kind == SyntaxKind::U8  ? Type::U8
                                                   : Type::Bool;
        } else if (type.kind == SyntaxKind::Parameter || type.kind == SyntaxKind::LengthParameter) {
            value = Type(TypeKind::Parameter);
            value.className = spelling;
        } else if (type.kind == SyntaxKind::Capacity) {
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
            value = Type(name(type.token, type.nameEnd));
            if (type.first >= 0)
                value.templateArguments.push_back(argumentValue(type.first));
            if (type.second >= 0)
                value.templateArguments.push_back(argumentValue(type.second));
        } else if (type.kind == SyntaxKind::Own || type.kind == SyntaxKind::Ref || type.kind == SyntaxKind::MutRef) {
            value = type.kind == SyntaxKind::Own ? Type::Own : type.kind == SyntaxKind::Ref ? Type::Ref : Type::MutRef;
        } else if (type.kind == SyntaxKind::Builtin || type.kind == SyntaxKind::BuiltinClass) {
            const auto &builtin = text(type.nameEnd);
            if (builtin == "ByteRegion")
                value = Type::ByteRegion;
            else if (builtin == "OwnedBytes")
                value = Type::OwnedBytes;
            else if (builtin == "ConsoleSession")
                value = Type::ConsoleSession;
            else if (builtin == "DisplaySession")
                value = Type::DisplaySession;
            else if (builtin == "IommuEventSession")
                value = Type::IommuEventSession;
            else if (builtin == "ConsoleSample")
                value = service::sampleType();
            else if (builtin == "ConsolePutResult")
                value = service::putResultType();
            else if (builtin == "ConsoleCompletion")
                value = service::completionType();
            else if (builtin == "DisplayPutResult")
                value = service::displayPutResultType();
            else if (builtin == "DisplayCompletion")
                value = service::displayCompletionType();
            else if (builtin == "IommuEventSample")
                value = service::eventSampleType();
            else if (builtin == "EventPollResult")
                value = service::eventPollResultType();
            else if (builtin == "EventAckResult")
                value = service::eventAckResultType();
            else if (builtin == "EventIntakeCompletion")
                value = service::eventIntakeCompletionType();
            else
                invalid();
        } else if (type.kind == SyntaxKind::ByteSpan) {
            value = Type::ByteSpan;
        } else if (type.kind == SyntaxKind::Array || type.kind == SyntaxKind::OwnedValues) {
            const auto &elementSyntax = types[static_cast<std::size_t>(type.first)];
            const auto &element = typeValues[static_cast<std::size_t>(type.first)];
            if (type.kind == SyntaxKind::OwnedValues) {
                if (!element.isClass() || !element.templateArguments.empty())
                    invalid();
                value = Type::ownedValues(element);
            } else {
                const auto &length = types[static_cast<std::size_t>(type.second)];
                if (elementSyntax.kind == SyntaxKind::Capacity || elementSyntax.kind == SyntaxKind::LengthParameter ||
                    (!scalar(element) && element.kind != TypeKind::Parameter && !element.isClass()) ||
                    (length.kind != SyntaxKind::Capacity && length.kind != SyntaxKind::LengthParameter))
                    invalid();
                value = Type::array(element, static_cast<int>(capacities[static_cast<std::size_t>(type.second)]));
                if (length.kind == SyntaxKind::LengthParameter)
                    value.lengthParameter = text(length.token);
                else if (element.isClass() && value.length > maximumClassScalarArrayLength)
                    invalid();
            }
        } else
            invalid();
    }
    std::vector<Edge> edges(static_cast<std::size_t>(edgeCount));
    for (std::int64_t index = 0; index < edgeCount; ++index) {
        auto &edge = edges[static_cast<std::size_t>(index)];
        aurora_hosted_parser_edge(arena.data(), index, &edge);
        if (edge.child < 0 || edge.child >= result.count || edge.previous < -1 || edge.previous >= index ||
            edge.field < -1 || edge.field >= result.tokens || edge.count < 1 || edge.count > edgeCount ||
            edge.depth < 1 || edge.depth > 128)
            invalid();
    }
    std::vector<ExpressionPtr> nodes;
    std::vector<bool> used(static_cast<std::size_t>(result.count), false);
    std::vector<bool> edgeUsed(static_cast<std::size_t>(edgeCount), false);
    nodes.reserve(static_cast<std::size_t>(result.count));
    for (std::int64_t index = 0; index < result.count; ++index) {
        Node node;
        aurora_hosted_parser_read(arena.data(), index, &node);
        if (node.kind <= NodeKind::Invalid || node.kind > NodeKind::ArrayZero || node.token < 0 ||
            node.token >= result.tokens || node.nameEnd < node.token || node.nameEnd >= result.tokens ||
            node.close < 0 || node.close >= result.tokens || node.depth < 1 || node.depth > 128)
            invalid();
        auto token = tokens[position + static_cast<std::size_t>(node.token)];
        std::string op;
        if (node.kind == NodeKind::Name || node.kind == NodeKind::Call || node.kind == NodeKind::Construct) {
            op = node.kind == NodeKind::Name ? "name" : node.kind == NodeKind::Call ? "call" : "construct";
            token.text = name(node.token, node.nameEnd);
            token.span.end = tokens[position + static_cast<std::size_t>(node.nameEnd)].span.end;
            if (token.span.end.offset < token.span.begin.offset ||
                token.span.end.offset > token.span.source->text.size())
                invalid();
        } else if (node.kind == NodeKind::Literal && (token.text == "true" || token.text == "false"))
            op = "bool";
        else if (node.kind == NodeKind::Literal && token.text.front() == '"')
            op = "byte_string";
        else if (node.kind == NodeKind::Literal && token.text.front() == '\'')
            op = "byte";
        else if (node.kind == NodeKind::Literal && token.text.front() >= '0' && token.text.front() <= '9')
            op = "number";
        else if (node.kind == NodeKind::Unary)
            op = "unary";
        else if (node.kind == NodeKind::Binary)
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
        const auto takeType = [&](std::int64_t root) -> Type & {
            if (typeUsed[static_cast<std::size_t>(root)])
                invalid();
            typeUsed[static_cast<std::size_t>(root)] = true;
            return typeValues[static_cast<std::size_t>(root)];
        };
        if (templateRoot >= 0) {
            if (node.kind != NodeKind::Call && node.kind != NodeKind::Construct)
                invalid();
            expression->templateArguments = std::move(takeType(templateRoot).templateArguments);
        }
        if (reflectedRoot >= 0) {
            if (node.kind != NodeKind::Call || node.first != -1 || node.second != 0)
                invalid();
            expression->reflectedType = std::move(takeType(reflectedRoot));
        }
        const auto attach = [&](std::int64_t child) {
            if (child < 0 || child >= index || used[static_cast<std::size_t>(child)])
                invalid();
            used[static_cast<std::size_t>(child)] = true;
            const auto &value = nodes[static_cast<std::size_t>(child)];
            expression->depth = std::max(expression->depth, value->depth + 1);
            if (expression->depth > 128)
                invalid();
            expression->args.push_back(value);
        };
        if (node.kind == NodeKind::Call || node.kind == NodeKind::MethodCall || node.kind == NodeKind::ArrayLiteral ||
            node.kind == NodeKind::Construct || node.kind == NodeKind::ArrayZero) {
            if (node.second < 0 || node.second > edgeCount || (node.first == -1) != (node.second == 0) ||
                (node.kind == NodeKind::MethodCall && node.second == 0) ||
                (node.kind == NodeKind::ArrayZero && node.second != 0))
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
            if (children.size() != static_cast<std::size_t>(node.second))
                invalid();
            for (auto child = children.rbegin(); child != children.rend(); ++child) {
                const auto &edge = edges[static_cast<std::size_t>(*child)];
                attach(edge.child);
                if (edge.field >= 0)
                    expression->fieldNames.push_back(text(edge.field));
            }
        } else if (node.kind == NodeKind::Unary || node.kind == NodeKind::Member) {
            if (node.second != -1)
                invalid();
            attach(node.first);
        } else if (node.kind == NodeKind::Binary || node.kind == NodeKind::Index) {
            attach(node.first);
            attach(node.second);
            // The host AST locates indexing at the base expression's token.
            if (node.kind == NodeKind::Index)
                expression->token = expression->args.front()->token;
        } else if (node.first != -1 || node.second != -1)
            invalid();
        if (node.depth != expression->depth)
            invalid();
        nodes.push_back(std::move(expression));
    }
    // Every expression root belongs to exactly one statement field, or to the
    // public expression result. Unreferenced records and shared roots fail closed.
    const auto takeExpression = [&](std::int64_t root) {
        if (root < 0 || root >= result.count || used[static_cast<std::size_t>(root)])
            invalid();
        used[static_cast<std::size_t>(root)] = true;
        return nodes[static_cast<std::size_t>(root)];
    };
    std::vector<StatementPtr> statementValues;
    statementValues.reserve(statements.size());
    for (std::int64_t index = 0; index < statementCount; ++index) {
        const auto &syntax = statements[static_cast<std::size_t>(index)];
        auto statement = std::make_shared<Statement>(tokens[position + static_cast<std::size_t>(syntax.token)]);
        if (syntax.kind == StatementKind::Block) {
            statement->kind = "block";
            for (const auto child : statementLists[static_cast<std::size_t>(index)])
                statement->body.push_back(statementValues[static_cast<std::size_t>(child)]);
        } else {
            statement->expr = takeExpression(syntax.expression);
            if (syntax.kind == StatementKind::Conditional || syntax.kind == StatementKind::Loop) {
                statement->kind = syntax.kind == StatementKind::Conditional ? "if" : "while";
                statement->body = std::move(statementValues[static_cast<std::size_t>(syntax.body)]->body);
                if (syntax.other >= 0)
                    statement->other = std::move(statementValues[static_cast<std::size_t>(syntax.other)]->body);
            } else if (syntax.kind == StatementKind::Local) {
                const auto typeIndex = static_cast<std::size_t>(syntax.declaredType);
                const auto &type = types[typeIndex];
                if (type.role != 3 || type.owner != syntax.token ||
                    declarationRoots[static_cast<std::size_t>(syntax.token)] != syntax.declaredType ||
                    typeUsed[typeIndex])
                    invalid();
                typeUsed[typeIndex] = true;
                const auto &binding = tokens[position + static_cast<std::size_t>(syntax.binding)];
                statement->kind = "let";
                statement->type = std::move(typeValues[typeIndex]);
                statement->name = binding.text;
                statement->bindingSpan = binding.span;
                statement->mutableValue = syntax.mutableValue == 1;
            } else if (syntax.kind == StatementKind::ReturnValue)
                statement->kind = "return";
            else if (syntax.kind == StatementKind::StaticAssertion)
                statement->kind = "static_assert";
            else if (syntax.kind == StatementKind::Expression)
                statement->kind = "expression";
            else {
                auto target = takeExpression(syntax.target);
                if (syntax.kind == StatementKind::Assign) {
                    if (target->op != "name" || !target->args.empty())
                        invalid();
                    statement->kind = "assign";
                    statement->name = target->token.text;
                } else if (syntax.kind == StatementKind::FieldAssign) {
                    if (target->op != "member" || target->args.size() != 1 || target->args[0]->op != "name" ||
                        !target->args[0]->args.empty())
                        invalid();
                    statement->kind = "field_assign";
                    statement->name = target->args[0]->token.text;
                    statement->fieldName = target->token.text;
                } else {
                    if (syntax.kind != StatementKind::IndexAssign || target->op != "index" || target->args.size() != 2)
                        invalid();
                    statement->kind = "index_assign";
                    statement->target = std::move(target);
                }
            }
        }
        statementValues.push_back(std::move(statement));
    }
    ImportedSyntax imported;
    if (body)
        imported.body = std::move(statementValues[static_cast<std::size_t>(result.root)]->body);
    else
        imported.expression = takeExpression(result.root);
    if (std::find(used.begin(), used.end(), false) != used.end() ||
        std::find(edgeUsed.begin(), edgeUsed.end(), false) != edgeUsed.end() ||
        std::find(typeUsed.begin(), typeUsed.end(), false) != typeUsed.end())
        invalid();
    position = end;
    return imported;
}
} // namespace

ExpressionPtr parseHostedExpression(const std::vector<Token> &tokens,
                                    std::size_t &position,
                                    Stop stop,
                                    const hosted_parser::Context &context) {
    if (stop != Stop::Semicolon && stop != Stop::CloseParenthesis && stop != Stop::Assignment &&
        stop != Stop::ConstructorBraces)
        invalid();
    return parseHostedSyntax(tokens, position, stop, context).expression;
}

std::vector<StatementPtr>
parseHostedBody(const std::vector<Token> &tokens, std::size_t &position, const hosted_parser::Context &context) {
    return parseHostedSyntax(tokens, position, Stop::Body, context).body;
}
} // namespace aurora
