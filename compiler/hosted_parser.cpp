// Trusted hosted bootstrap boundary. Source snapshots remain immutable and live
// throughout each synchronous call; no owner descriptor or payload pointer is
// constructed, copied or inspected here.
#include "hosted_parser.hpp"
#include "services.hpp"
#include "../runtime/hosted_bytes.hpp"
#include <algorithm>
#include <cstddef>
#include <limits>
#include <optional>
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
using Result = hosted_abi::compiler_parser::ParseResult;
using Node = hosted_abi::compiler_parser::AstNode;
using Edge = hosted_abi::compiler_parser::ChildEdge;
using TypeSyntax = hosted_abi::compiler_parser::TypeSyntax;
using StatementSyntax = hosted_abi::compiler_parser::StatementSyntax;
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
        return record.arena.storage.data();
    }
};

[[noreturn]] void invalid() {
    throw Error(DiagnosticCode::Internal, "hosted parser returned an invalid result");
}
class ImportedSyntax {
public:
    ExpressionPtr expression;
    std::vector<StatementPtr> body;
    Type type;
    std::optional<Token> residual;
};

ImportedSyntax parseHostedSyntax(const std::vector<Token> &tokens,
                                 std::size_t &position,
                                 Stop stop,
                                 const hosted_parser::Context &context) {
    const bool body = stop == Stop::body;
    const bool declarationType = stop == Stop::type;
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
    input.source.backing = source->text.data();
    input.source.length = static_cast<std::int64_t>(source->text.size());
    input.cursor.offset = static_cast<std::int64_t>(begin.begin.offset);
    input.cursor.line = begin.begin.line;
    input.cursor.line_start = input.cursor.offset - begin.begin.column + 1;
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
        parameter(context.typeParameters[0], input.context.first_begin, input.context.first_end);
        if (context.typeParameters.size() == 2)
            parameter(context.typeParameters[1], input.context.second_begin, input.context.second_end);
        input.context.template_mode = context.functionTemplate ? 2 : 1;
    }
    if (!context.capacityParameters.empty())
        parameter(context.capacityParameters[0], input.context.capacity_begin, input.context.capacity_end);
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
    if (result.result < Status::success || result.result >= Status::invalid || result.node_count < 0 ||
        result.node_count != actualCount || edgeCount < 0 || typeCount < 0 || statementCount < 0 ||
        (!body && statementCount != 0) || result.token_count < 0 ||
        static_cast<std::uint64_t>(result.token_count) >= tokens.size() - position ||
        result.source_offset < input.cursor.offset || result.source_offset > input.source.length)
        invalid();
    if (result.result == Status::unsupported)
        invalid();
    const auto end = position + static_cast<std::size_t>(result.token_count);
    for (auto index = position; index <= end; ++index) {
        const auto &token = tokens[index];
        const auto &span = token.span;
        if (!span.source || span.begin.offset > span.end.offset || span.end.offset > span.source->text.size() ||
            token.text.empty())
            invalid();
    }
    auto at = tokens[end];
    if (static_cast<std::size_t>(result.source_offset) != at.span.begin.offset) {
        if ((result.result == Status::success && !declarationType) || at.text != ">>" ||
            at.span.end.offset - at.span.begin.offset != 2 ||
            static_cast<std::size_t>(result.source_offset) != at.span.begin.offset + 1 ||
            at.span.begin.column == std::numeric_limits<int>::max())
            invalid();
        at.text = ">";
        ++at.span.begin.offset;
        ++at.span.begin.column;
    }
    if (result.result != Status::success) {
        if (result.root_node != -1)
            invalid();
        if (result.result == Status::allocation_failure)
            throw Error(DiagnosticCode::Internal, "hosted parser allocation failed", at.span);
        if ((!body && result.result >= Status::expected_open) || (body && result.result == Status::expected_end))
            invalid();
        if (result.result == Status::block_nesting_limit)
            throw Error(DiagnosticCode::NestingLimit, "block nesting exceeds 128", at.span);
        if (result.result == Status::nesting_limit)
            throw Error(DiagnosticCode::NestingLimit, "expression parser nesting exceeds 128", at.span);
        if (result.result == Status::type_nesting_limit || result.result == Status::template_nesting_limit ||
            result.result == Status::call_template_nesting_limit)
            throw Error(DiagnosticCode::NestingLimit,
                        result.result == Status::type_nesting_limit       ? "type nesting exceeds 64"
                        : result.result == Status::template_nesting_limit ? "template-id nesting exceeds 4"
                                                                          : "template-id nesting exceeds 5",
                        at.span);
        std::string message;
        if (result.result == Status::expected_expression)
            message = "expected expression";
        else if (result.result == Status::expected_close)
            message = "expected ')'";
        else if (result.result == Status::expected_index_close)
            message = "expected ']'";
        else if (result.result == Status::expected_brace_close)
            message = "expected '}'";
        else if (result.result == Status::expected_dot)
            message = "expected '.'";
        else if (result.result == Status::expected_equal)
            message = "expected '='";
        else if (result.result == Status::expected_brace_open)
            message = "expected '{'";
        else if (result.result == Status::expected_identifier)
            message = "expected identifier";
        else if (result.result == Status::reserved_identifier)
            message = "reserved identifier";
        else if (result.result == Status::reserved_builtin)
            message = "reserved builtin storage name";
        else if (result.result == Status::reserved_prefix)
            message = "reserved compiler identifier prefix: __au_";
        else if (result.result == Status::depth_limit)
            message = "expression AST depth exceeds 128";
        else if (result.result == Status::expected_angle_open)
            message = "expected '<'";
        else if (result.result == Status::expected_angle_close)
            message = "expected '>'";
        else if (result.result == Status::expected_scope)
            message = "expected '::'";
        else if (result.result == Status::expected_comma)
            message = "expected ','";
        else if (result.result == Status::expected_const)
            message = "expected 'const'";
        else if (result.result == Status::expected_u8)
            message = "expected 'u8'";
        else if (result.result == Status::expected_i64)
            message = "expected 'i64'";
        else if (result.result == Status::expected_array)
            message = "expected 'array'";
        else if (result.result == Status::reserved_type)
            message = "unsupported or reserved type spelling";
        else if (result.result == Status::expected_type)
            message = "expected type name";
        else if (result.result == Status::template_context)
            message = "template-id references inside template definitions are not supported";
        else if (result.result == Status::template_arity)
            message = "template arguments are limited to one or two types or capacity literals";
        else if (result.result == Status::template_argument)
            message = "template arguments require scalar, named class or enum types, or capacities from 1 to 64";
        else if (result.result == Status::capacity_argument)
            message = "capacity template arguments must be decimal literals from 1 to 64";
        else if (result.result == Status::nested_dependent)
            message = "nested dependent template arguments are not supported";
        else if (result.result == Status::owned_element)
            message = "owned values require a named concrete copied class";
        else if (result.result == Status::array_element)
            message = "array elements require i64, u64, u8, bool or a concrete copied class";
        else if (result.result == Status::array_length)
            message = "array length requires a decimal integer literal between 1 and 4096";
        else if (result.result == Status::class_array_length)
            message = "class-element array capacity must be between 1 and 64";
        else if (result.result == Status::expected_open)
            message = "expected '('";
        else if (result.result == Status::expected_semicolon)
            message = "expected ';'";
        else if (result.result == Status::unterminated_block)
            message = "unterminated block";
        else if (result.result == Status::assignment_target)
            message = "assignment requires a local or local field";
        else if (result.result == Status::expected_end)
            message = stop == Stop::close_parenthesis ? "expected ')'" : "expected ';'";
        else
            invalid();
        throw Error(DiagnosticCode::UnexpectedToken, message + " (found '" + at.text + "')", at.span);
    }
    const bool residual = static_cast<std::size_t>(result.source_offset) != tokens[end].span.begin.offset;
    const auto tokenCount = result.token_count + (residual ? 1 : 0);
    if (result.token_count == 0 || result.node_count > result.token_count || typeCount > tokenCount ||
        statementCount > result.token_count ||
        (result.node_count == 0 ? edgeCount != 0 : edgeCount >= result.node_count) ||
        (declarationType ? result.node_count != 0 || typeCount == 0 || result.root_node != typeCount - 1
         : body          ? statementCount == 0 || result.root_node != statementCount - 1
                         : result.node_count == 0 || result.root_node != result.node_count - 1))
        invalid();
    const auto text = [&](std::int64_t ordinal) -> const std::string & {
        if (ordinal < 0 || ordinal >= tokenCount)
            invalid();
        return tokens[position + static_cast<std::size_t>(ordinal)].text;
    };
    const auto name = [&](std::int64_t first, std::int64_t last) {
        if (first < 0 || last < first || last >= tokenCount)
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
        if (statement.tag <= StatementKind::invalid || statement.tag > StatementKind::index_assign ||
            statement.token_index < 0 || statement.token_index >= statement.end_token ||
            statement.end_token > result.token_count || statement.previous_statement < -1 ||
            statement.previous_statement >= index || statement.expression_root < -1 ||
            statement.expression_root >= result.node_count || statement.target_root < -1 ||
            statement.target_root >= result.node_count || statement.declared_type < -1 ||
            statement.declared_type >= typeCount || statement.binding_token < -1 ||
            statement.binding_token >= result.token_count || statement.body_statement < -1 ||
            statement.body_statement >= index || statement.other_statement < -1 || statement.other_statement >= index ||
            (statement.mutable_value != 0 && statement.mutable_value != 1))
            invalid();
        const bool local = statement.tag == StatementKind::local;
        const bool block = statement.tag == StatementKind::block;
        const bool conditional = statement.tag == StatementKind::conditional;
        const bool loop = statement.tag == StatementKind::loop;
        const bool assignment = statement.tag == StatementKind::assign ||
                                statement.tag == StatementKind::field_assign ||
                                statement.tag == StatementKind::index_assign;
        if ((statement.expression_root == -1) != block || (statement.target_root >= 0) != assignment ||
            (statement.declared_type >= 0) != local || (statement.binding_token >= 0) != local ||
            (!local && statement.mutable_value != 0) ||
            (!block && !conditional && !loop && statement.body_statement != -1) ||
            ((conditional || loop) && statement.body_statement == -1) ||
            (!conditional && statement.other_statement != -1))
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
            for (auto child = statement.body_statement; child != -1;) {
                const auto &value = ownStatement(child);
                depth = std::max(depth, blockDepth[static_cast<std::size_t>(child)]);
                children.push_back(child);
                child = value.previous_statement;
            }
            std::reverse(children.begin(), children.end());
            if (++depth > 128)
                invalid();
        } else if (conditional || loop) {
            const auto &branch = ownStatement(statement.body_statement);
            if (branch.tag != StatementKind::block || branch.previous_statement != -1)
                invalid();
            // Control nodes unwrap their block records, so they add no extra
            // lexical nesting beyond those blocks.
            depth = blockDepth[static_cast<std::size_t>(statement.body_statement)];
            if (statement.other_statement >= 0) {
                const auto &other = ownStatement(statement.other_statement);
                if (other.tag != StatementKind::block || other.previous_statement != -1)
                    invalid();
                depth = std::max(depth, blockDepth[static_cast<std::size_t>(statement.other_statement)]);
            }
        }
    }
    if (body) {
        const auto &root = statements[static_cast<std::size_t>(result.root_node)];
        if (root.tag != StatementKind::block || root.previous_statement != -1 ||
            statementUsed[static_cast<std::size_t>(result.root_node)])
            invalid();
        statementUsed[static_cast<std::size_t>(result.root_node)] = true;
        if (std::find(statementUsed.begin(), statementUsed.end(), false) != statementUsed.end())
            invalid();
    }
    using SyntaxKind = hosted_parser::TypeKind;
    std::vector<TypeSyntax> types(static_cast<std::size_t>(typeCount));
    std::vector<Type> typeValues(static_cast<std::size_t>(typeCount));
    std::vector<std::int64_t> capacities(static_cast<std::size_t>(typeCount), 0);
    std::vector<bool> typeUsed(static_cast<std::size_t>(typeCount), false);
    std::vector<int> typeDepth(static_cast<std::size_t>(typeCount), 1);
    std::vector<std::int64_t> templateRoots(static_cast<std::size_t>(tokenCount), -1);
    std::vector<std::int64_t> reflectedRoots(static_cast<std::size_t>(tokenCount), -1);
    std::vector<std::int64_t> declarationRoots(static_cast<std::size_t>(tokenCount), -1);
    // Aurora owns grammar validation. Here each recursive host value has one
    // owner and bounded structural depth, so forged DAGs cannot amplify copies.
    // This is a host construction limit, not a replay of type/template nesting.
    for (std::int64_t index = 0; index < typeCount; ++index) {
        auto &type = types[static_cast<std::size_t>(index)];
        aurora_hosted_parser_type(arena.data(), index, &type);
        if (type.tag <= SyntaxKind::invalid || type.tag > SyntaxKind::builtin_class || type.token_index < 0 ||
            type.token_index >= tokenCount || type.name_end < type.token_index || type.name_end >= tokenCount ||
            type.closing_token < 0 || type.closing_token / 2 >= tokenCount || type.first_child < -1 ||
            type.second_child < -1 || type.first_child >= index || type.second_child >= index ||
            (type.first_child == -1 && type.second_child != -1))
            invalid();
        if (type.owner_role == 0) {
            if (type.owner_token != -1)
                invalid();
        } else {
            if (type.owner_token < 0 || type.owner_token >= tokenCount ||
                (type.owner_role != 1 && type.owner_role != 2 &&
                 !((body || declarationType) && type.owner_role == 3)) ||
                (type.owner_role == 1 && (type.tag != SyntaxKind::named || type.first_child < 0)) ||
                type.tag == SyntaxKind::capacity || type.tag == SyntaxKind::length_parameter)
                invalid();
            auto &roots = type.owner_role == 1   ? templateRoots
                          : type.owner_role == 2 ? reflectedRoots
                                                 : declarationRoots;
            if (roots[static_cast<std::size_t>(type.owner_token)] != -1)
                invalid();
            roots[static_cast<std::size_t>(type.owner_token)] = index;
        }
        auto &depth = typeDepth[static_cast<std::size_t>(index)];
        for (const auto child : {type.first_child, type.second_child}) {
            if (child < 0)
                continue;
            const auto ordinal = static_cast<std::size_t>(child);
            if (typeUsed[ordinal] || types[ordinal].owner_role != 0)
                invalid();
            typeUsed[ordinal] = true;
            depth = std::max(depth, typeDepth[ordinal] + 1);
        }
        if (depth > 128)
            invalid();
    }
    const auto argumentValue = [&](std::int64_t child) {
        const auto &type = types[static_cast<std::size_t>(child)];
        if (type.tag == SyntaxKind::capacity) {
            const auto capacity = capacities[static_cast<std::size_t>(child)];
            if (capacity < 1 || capacity > 64)
                invalid();
            return TemplateArgument::capacity(capacity);
        }
        if (type.tag != SyntaxKind::i64_type && type.tag != SyntaxKind::u64_type && type.tag != SyntaxKind::u8_type &&
            type.tag != SyntaxKind::bool_type && type.tag != SyntaxKind::named && type.tag != SyntaxKind::parameter)
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
        if (type.tag == SyntaxKind::array_type) {
            if (type.first_child < 0 || type.second_child < 0)
                invalid();
        } else if (type.tag == SyntaxKind::owned_values) {
            if (type.first_child < 0 || type.second_child != -1)
                invalid();
        } else if (type.tag != SyntaxKind::named && (type.first_child != -1 || type.second_child != -1))
            invalid();
        auto &value = typeValues[static_cast<std::size_t>(index)];
        const auto &spelling = text(type.token_index);
        if (type.tag == SyntaxKind::i64_type || type.tag == SyntaxKind::u64_type || type.tag == SyntaxKind::u8_type ||
            type.tag == SyntaxKind::bool_type) {
            value = type.tag == SyntaxKind::i64_type   ? Type::I64
                    : type.tag == SyntaxKind::u64_type ? Type::U64
                    : type.tag == SyntaxKind::u8_type  ? Type::U8
                                                       : Type::Bool;
        } else if (type.tag == SyntaxKind::parameter || type.tag == SyntaxKind::length_parameter) {
            value = Type(TypeKind::Parameter);
            value.className = spelling;
        } else if (type.tag == SyntaxKind::capacity) {
            std::int64_t capacity = 0;
            for (const auto byte : spelling) {
                if (byte < '0' || byte > '9' || capacity > 4096)
                    invalid();
                capacity = capacity * 10 + byte - '0';
            }
            if (capacity < 1 || capacity > 4096)
                invalid();
            capacities[static_cast<std::size_t>(index)] = capacity;
        } else if (type.tag == SyntaxKind::named) {
            value = Type(name(type.token_index, type.name_end));
            if (type.first_child >= 0)
                value.templateArguments.push_back(argumentValue(type.first_child));
            if (type.second_child >= 0)
                value.templateArguments.push_back(argumentValue(type.second_child));
        } else if (type.tag == SyntaxKind::own_type || type.tag == SyntaxKind::ref_type ||
                   type.tag == SyntaxKind::mutref_type) {
            value = type.tag == SyntaxKind::own_type   ? Type::Own
                    : type.tag == SyntaxKind::ref_type ? Type::Ref
                                                       : Type::MutRef;
        } else if (type.tag == SyntaxKind::builtin_type || type.tag == SyntaxKind::builtin_class) {
            const auto &builtin = text(type.name_end);
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
        } else if (type.tag == SyntaxKind::byte_span) {
            value = Type::ByteSpan;
        } else if (type.tag == SyntaxKind::array_type || type.tag == SyntaxKind::owned_values) {
            const auto &elementSyntax = types[static_cast<std::size_t>(type.first_child)];
            const auto &element = typeValues[static_cast<std::size_t>(type.first_child)];
            if (type.tag == SyntaxKind::owned_values) {
                if (!element.isClass() || !element.templateArguments.empty())
                    invalid();
                value = Type::ownedValues(element);
            } else {
                const auto &length = types[static_cast<std::size_t>(type.second_child)];
                if (elementSyntax.tag == SyntaxKind::capacity || elementSyntax.tag == SyntaxKind::length_parameter ||
                    (!scalar(element) && element.kind != TypeKind::Parameter && !element.isClass()) ||
                    (length.tag != SyntaxKind::capacity && length.tag != SyntaxKind::length_parameter))
                    invalid();
                value = Type::array(element, static_cast<int>(capacities[static_cast<std::size_t>(type.second_child)]));
                if (length.tag == SyntaxKind::length_parameter)
                    value.lengthParameter = text(length.token_index);
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
        if (edge.child_node < 0 || edge.child_node >= result.node_count || edge.previous_edge < -1 ||
            edge.previous_edge >= index || edge.field_token < -1 || edge.field_token >= result.token_count ||
            edge.argument_count < 1 || edge.argument_count > edgeCount || edge.tree_depth < 1 || edge.tree_depth > 128)
            invalid();
    }
    std::vector<ExpressionPtr> nodes;
    std::vector<bool> used(static_cast<std::size_t>(result.node_count), false);
    std::vector<bool> edgeUsed(static_cast<std::size_t>(edgeCount), false);
    nodes.reserve(static_cast<std::size_t>(result.node_count));
    for (std::int64_t index = 0; index < result.node_count; ++index) {
        Node node;
        aurora_hosted_parser_read(arena.data(), index, &node);
        if (node.tag <= NodeKind::invalid || node.tag > NodeKind::array_zero || node.token_index < 0 ||
            node.token_index >= result.token_count || node.name_end < node.token_index ||
            node.name_end >= result.token_count || node.closing_token < 0 || node.closing_token >= result.token_count ||
            node.tree_depth < 1 || node.tree_depth > 128)
            invalid();
        auto token = tokens[position + static_cast<std::size_t>(node.token_index)];
        std::string op;
        if (node.tag == NodeKind::name || node.tag == NodeKind::call || node.tag == NodeKind::construct) {
            op = node.tag == NodeKind::name ? "name" : node.tag == NodeKind::call ? "call" : "construct";
            token.text = name(node.token_index, node.name_end);
            token.span.end = tokens[position + static_cast<std::size_t>(node.name_end)].span.end;
            if (token.span.end.offset < token.span.begin.offset ||
                token.span.end.offset > token.span.source->text.size())
                invalid();
        } else if (node.tag == NodeKind::literal && (token.text == "true" || token.text == "false"))
            op = "bool";
        else if (node.tag == NodeKind::literal && token.text.front() == '"')
            op = "byte_string";
        else if (node.tag == NodeKind::literal && token.text.front() == '\'')
            op = "byte";
        else if (node.tag == NodeKind::literal && token.text.front() >= '0' && token.text.front() <= '9')
            op = "number";
        else if (node.tag == NodeKind::unary)
            op = "unary";
        else if (node.tag == NodeKind::binary)
            op = "binary";
        else if (node.tag == NodeKind::member)
            op = "member";
        else if (node.tag == NodeKind::method_call)
            op = "method_call";
        else if (node.tag == NodeKind::index)
            op = "index";
        else if (node.tag == NodeKind::array_literal)
            op = "array_literal";
        else if (node.tag == NodeKind::array_zero)
            op = "array_zero";
        else
            invalid();
        auto expression = std::make_shared<Expression>(op, token);
        const auto templateRoot = templateRoots[static_cast<std::size_t>(node.token_index)];
        const auto reflectedRoot = reflectedRoots[static_cast<std::size_t>(node.token_index)];
        const auto takeType = [&](std::int64_t root) -> Type & {
            if (typeUsed[static_cast<std::size_t>(root)])
                invalid();
            typeUsed[static_cast<std::size_t>(root)] = true;
            return typeValues[static_cast<std::size_t>(root)];
        };
        if (templateRoot >= 0) {
            if (node.tag != NodeKind::call && node.tag != NodeKind::construct)
                invalid();
            expression->templateArguments = std::move(takeType(templateRoot).templateArguments);
        }
        if (reflectedRoot >= 0) {
            if (node.tag != NodeKind::call || node.first_child != -1 || node.second_child != 0)
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
        if (node.tag == NodeKind::call || node.tag == NodeKind::method_call || node.tag == NodeKind::array_literal ||
            node.tag == NodeKind::construct || node.tag == NodeKind::array_zero) {
            if (node.second_child < 0 || node.second_child > edgeCount ||
                (node.first_child == -1) != (node.second_child == 0) ||
                (node.tag == NodeKind::method_call && node.second_child == 0) ||
                (node.tag == NodeKind::array_zero && node.second_child != 0))
                invalid();
            std::vector<std::int64_t> children;
            for (auto edge = node.first_child; edge != -1;) {
                if (edge < 0 || edge >= edgeCount || edgeUsed[static_cast<std::size_t>(edge)])
                    invalid();
                edgeUsed[static_cast<std::size_t>(edge)] = true;
                const auto &record = edges[static_cast<std::size_t>(edge)];
                if ((node.tag == NodeKind::construct) != (record.field_token >= 0))
                    invalid();
                children.push_back(edge);
                edge = record.previous_edge;
            }
            if (children.size() != static_cast<std::size_t>(node.second_child))
                invalid();
            for (auto child = children.rbegin(); child != children.rend(); ++child) {
                const auto &edge = edges[static_cast<std::size_t>(*child)];
                attach(edge.child_node);
                if (edge.field_token >= 0)
                    expression->fieldNames.push_back(text(edge.field_token));
            }
        } else if (node.tag == NodeKind::unary || node.tag == NodeKind::member) {
            if (node.second_child != -1)
                invalid();
            attach(node.first_child);
        } else if (node.tag == NodeKind::binary || node.tag == NodeKind::index) {
            attach(node.first_child);
            attach(node.second_child);
            // The host AST locates indexing at the base expression's token.
            if (node.tag == NodeKind::index)
                expression->token = expression->args.front()->token;
        } else if (node.first_child != -1 || node.second_child != -1)
            invalid();
        if (node.tree_depth != expression->depth)
            invalid();
        nodes.push_back(std::move(expression));
    }
    // Every expression root belongs to exactly one statement field, or to the
    // public expression result. Unreferenced records and shared roots fail closed.
    const auto takeExpression = [&](std::int64_t root) {
        if (root < 0 || root >= result.node_count || used[static_cast<std::size_t>(root)])
            invalid();
        used[static_cast<std::size_t>(root)] = true;
        return nodes[static_cast<std::size_t>(root)];
    };
    std::vector<StatementPtr> statementValues;
    statementValues.reserve(statements.size());
    for (std::int64_t index = 0; index < statementCount; ++index) {
        const auto &syntax = statements[static_cast<std::size_t>(index)];
        auto statement = std::make_shared<Statement>(tokens[position + static_cast<std::size_t>(syntax.token_index)]);
        if (syntax.tag == StatementKind::block) {
            statement->kind = "block";
            for (const auto child : statementLists[static_cast<std::size_t>(index)])
                statement->body.push_back(statementValues[static_cast<std::size_t>(child)]);
        } else {
            statement->expr = takeExpression(syntax.expression_root);
            if (syntax.tag == StatementKind::conditional || syntax.tag == StatementKind::loop) {
                statement->kind = syntax.tag == StatementKind::conditional ? "if" : "while";
                statement->body = std::move(statementValues[static_cast<std::size_t>(syntax.body_statement)]->body);
                if (syntax.other_statement >= 0)
                    statement->other =
                        std::move(statementValues[static_cast<std::size_t>(syntax.other_statement)]->body);
            } else if (syntax.tag == StatementKind::local) {
                const auto typeIndex = static_cast<std::size_t>(syntax.declared_type);
                const auto &type = types[typeIndex];
                if (type.owner_role != 3 || type.owner_token != syntax.token_index ||
                    declarationRoots[static_cast<std::size_t>(syntax.token_index)] != syntax.declared_type ||
                    typeUsed[typeIndex])
                    invalid();
                typeUsed[typeIndex] = true;
                const auto &binding = tokens[position + static_cast<std::size_t>(syntax.binding_token)];
                statement->kind = "let";
                statement->type = std::move(typeValues[typeIndex]);
                statement->name = binding.text;
                statement->bindingSpan = binding.span;
                statement->mutableValue = syntax.mutable_value == 1;
            } else if (syntax.tag == StatementKind::return_value)
                statement->kind = "return";
            else if (syntax.tag == StatementKind::static_assertion)
                statement->kind = "static_assert";
            else if (syntax.tag == StatementKind::expression)
                statement->kind = "expression";
            else {
                auto target = takeExpression(syntax.target_root);
                if (syntax.tag == StatementKind::assign) {
                    if (target->op != "name" || !target->args.empty())
                        invalid();
                    statement->kind = "assign";
                    statement->name = target->token.text;
                } else if (syntax.tag == StatementKind::field_assign) {
                    if (target->op != "member" || target->args.size() != 1 || target->args[0]->op != "name" ||
                        !target->args[0]->args.empty())
                        invalid();
                    statement->kind = "field_assign";
                    statement->name = target->args[0]->token.text;
                    statement->fieldName = target->token.text;
                } else {
                    if (syntax.tag != StatementKind::index_assign || target->op != "index" || target->args.size() != 2)
                        invalid();
                    statement->kind = "index_assign";
                    statement->target = std::move(target);
                }
            }
        }
        statementValues.push_back(std::move(statement));
    }
    ImportedSyntax imported;
    if (declarationType) {
        const auto root = static_cast<std::size_t>(result.root_node);
        if (types[root].owner_role != 3 || types[root].owner_token != 0 || typeUsed[root])
            invalid();
        typeUsed[root] = true;
        imported.type = std::move(typeValues[root]);
        if (residual)
            imported.residual = std::move(at);
    } else if (body)
        imported.body = std::move(statementValues[static_cast<std::size_t>(result.root_node)]->body);
    else
        imported.expression = takeExpression(result.root_node);
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
    if (stop != Stop::semicolon && stop != Stop::close_parenthesis && stop != Stop::assignment &&
        stop != Stop::constructor_braces)
        invalid();
    return parseHostedSyntax(tokens, position, stop, context).expression;
}

std::vector<StatementPtr>
parseHostedBody(const std::vector<Token> &tokens, std::size_t &position, const hosted_parser::Context &context) {
    return parseHostedSyntax(tokens, position, Stop::body, context).body;
}

Type parseHostedType(std::vector<Token> &tokens, std::size_t &position, const hosted_parser::Context &context) {
    auto candidate = position;
    auto imported = parseHostedSyntax(tokens, candidate, Stop::type, context);
    // A type may consume only the first half of >>. Project the remaining
    // token in the caller-owned copy only after complete safe conversion.
    static_assert(noexcept(std::swap(tokens[candidate], *imported.residual)));
    static_assert(noexcept(Type(std::move(imported.type))));
    if (imported.residual)
        std::swap(tokens[candidate], *imported.residual);
    position = candidate;
    return std::move(imported.type);
}
} // namespace aurora
