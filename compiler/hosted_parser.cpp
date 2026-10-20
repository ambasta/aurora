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
#include <optional>
#include <set>
#include <utility>

#ifndef AURORA_HOSTED_PARSER
#error The hosted parser adapter requires AURORA_HOSTED_PARSER
#endif

namespace aurora {
namespace {
using hosted_parser::AdmissionStatus;
using hosted_parser::NodeKind;
using hosted_parser::Status;
using hosted_parser::Stop;
using hosted_parser::SyntaxKind;
using TypeSyntaxKind = hosted_parser::TypeKind;
using Input = hosted_abi::ParserInput;
using Result = hosted_abi::compiler_parser::ParseResult;
using Node = hosted_abi::compiler_parser::AstNode;
using Edge = hosted_abi::compiler_parser::ChildEdge;
using TypeSyntax = hosted_abi::compiler_parser::TypeSyntax;
using SyntaxNode = hosted_abi::compiler_parser::SyntaxNode;
class Arena {
    std::optional<hosted::bytes::Region> region;
    hosted_abi::ParserRelease record;
    void *external = nullptr;

public:
    explicit Arena(std::uint64_t quota, void *externalStorage = nullptr) : external(externalStorage) {
        if (external)
            return;
        region.emplace(quota);
        record.region = region->id();
        hosted_abi::ParserCreate input;
        input.region = region->id();
        aurora_hosted_parser_create(&input, data());
    }
    ~Arena() {
        if (!external)
            aurora_hosted_parser_release(&record);
    }
    Arena(const Arena &) = delete;
    Arena &operator=(const Arena &) = delete;
    void *data() {
        return external ? external : record.arena.storage.data();
    }
};

[[noreturn]] void invalid() {
    throw Error(DiagnosticCode::Internal, "hosted parser returned an invalid result");
}
Token cursorToken(const std::vector<Token> &tokens, hosted_parser::Cursor cursor) {
    if (cursor.ordinal >= tokens.size() || cursor.half > 1)
        invalid();
    auto token = tokens[cursor.ordinal];
    if (cursor.half) {
        const auto &span = token.span;
        if (!span.source || span.begin.offset > span.end.offset || span.end.offset > span.source->text.size() ||
            token.text != ">>" || span.end.offset - span.begin.offset != 2 ||
            span.begin.column == std::numeric_limits<int>::max())
            invalid();
        token.text = ">";
        ++token.span.begin.offset;
        ++token.span.begin.column;
    }
    return token;
}
// Shared layout/service policy remains authoritative in the existing compiler
// helpers. Aurora performs declaration admission using this copied configuration.
hosted_abi::compiler_parser::AdmissionConfig admissionConfiguration() {
    hosted_abi::compiler_parser::AdmissionConfig configuration;
    configuration.scalar_array_limit = maximumClassScalarArrayLength;
    configuration.byte_array_limit = maximumClassByteArrayLength;
    configuration.console_mask = 1;
    configuration.display_mask = 2;
    configuration.event_mask = 4;
    configuration.service_groups = service::supportedGroupBitmap();
    return configuration;
}
class ImportedSyntax {
public:
    ExpressionPtr expression;
    std::vector<StatementPtr> body;
    Type type;
    hosted_parser::Cursor next;
    std::optional<ParsedField> field;
    std::optional<ParsedCallable> callable;
    std::optional<Program> preamble;
    std::optional<EnumDefinition> enumeration;
    std::optional<Program> program;
    std::optional<ParsedModuleSyntax> moduleSyntax;
};

ImportedSyntax parseHostedSyntax(const std::vector<Token> &tokens,
                                 hosted_parser::Cursor cursor,
                                 Stop stop,
                                 const hosted_parser::Context &context,
                                 std::size_t enumCount = 0,
                                 void *externalArena = nullptr) {
    const auto position = cursor.ordinal;
    const bool module = stop == Stop::module_definition;
    if (externalArena && !module)
        invalid();
    const bool preamble = stop == Stop::preamble;
    const bool enumeration = stop == Stop::enum_definition;
    const bool header = preamble || enumeration;
    const bool field = stop == Stop::field;
    if (enumCount > 64 || (!enumeration && enumCount != 0))
        invalid();
    const bool body = stop == Stop::body;
    const bool declarationType = stop == Stop::type;
    const bool callable = stop == Stop::function || stop == Stop::method || stop == Stop::constructor;
    if (position >= tokens.size())
        invalid();
    const auto initial = cursorToken(tokens, cursor);
    const auto &begin = initial.span;
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
    input.enum_count = static_cast<std::int64_t>(enumCount);
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
    // Each store has at most N records. Existing syntax nodes charge distinct
    // declaration names, statement/type starts and block braces. New declaration
    // wrappers charge their spare auto/enum/class/namespace keyword, constructor
    // opening parenthesis or field semicolon; module/template rows charge their
    // module keyword/parameter names. These are quota charges, not wire metadata.
    // Template candidates add at most N frames. Capacity <= 2*used+8 includes
    // minimum allocations. Live fixed frames are body256 + expression1549 +
    // type70 + namespace64 = 1939. Namespace frames remain during leaf parsing.
    // Enum duplicate scratch (256) replaces, rather than overlaps, body/type work.
    // Post-grammar admission reuses at most one pending frame per syntax node;
    // parsing continuations are gone, so this fits the existing N-frame term.
    // The region charges replacement payload, not metadata or old+new resize bytes.
    constexpr std::uint64_t recordBytes = sizeof(Node) + sizeof(Edge) + sizeof(TypeSyntax) + sizeof(SyntaxNode);
    constexpr std::uint64_t perToken = 2 * (recordBytes + hosted_abi::frameBytes);
    constexpr std::uint64_t fixedBytes =
        8 * recordBytes + (2 * hosted_parser::maximumLiveFrames + 8) * hosted_abi::frameBytes;
    if (source->text.size() > (std::numeric_limits<std::uint64_t>::max() - fixedBytes) / perToken)
        invalid();
    Arena arena(static_cast<std::uint64_t>(source->text.size()) * perToken + fixedBytes, externalArena);
    Result result;
    aurora_hosted_parser_parse(arena.data(), &input, &result);
    const auto actualCount = aurora_hosted_parser_count(arena.data());
    const auto edgeCount = aurora_hosted_parser_edges(arena.data());
    const auto typeCount = aurora_hosted_parser_types(arena.data());
    const auto statementCount = aurora_hosted_parser_syntax_count(arena.data());
    if (!hosted_abi::compiler_parser::validRaw(result.result) || result.result == Status::invalid ||
        result.node_count < 0 || result.node_count != actualCount || edgeCount < 0 || typeCount < 0 ||
        statementCount < 0 || (!body && !callable && !field && !header && !module && statementCount != 0) ||
        result.token_count < 0 || static_cast<std::uint64_t>(result.token_count) >= tokens.size() - position ||
        result.source_offset < input.cursor.offset || result.source_offset > input.source.length ||
        result.token_half < 0 || result.token_half > 1)
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
    // Lexing from an original second byte starts its local token at half zero.
    // Keep that caller cursor only while the returned ordinal is still zero.
    const auto half = static_cast<unsigned>(result.token_half) | (result.token_count == 0 ? cursor.half : 0U);
    auto at = cursorToken(tokens, {end, half});
    if (static_cast<std::size_t>(result.source_offset) != at.span.begin.offset ||
        (result.result == Status::success && !declarationType && half != 0))
        invalid();
    if (result.result != Status::success) {
        if (result.root_node != -1)
            invalid();
        if (result.result == Status::allocation_failure)
            throw Error(DiagnosticCode::Internal, "hosted parser allocation failed", at.span);
        if ((!body && !callable && !field && !header && !module && result.result >= Status::expected_open) ||
            ((body || callable || field || header || module) && result.result == Status::expected_end) ||
            (!callable && !module &&
             (result.result == Status::expected_auto || result.result == Status::expected_arrow)))
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
        else if (result.result == Status::expected_auto)
            message = "expected 'auto'";
        else if (result.result == Status::expected_arrow)
            message = "expected '->'";
        else if (result.result == Status::expected_module)
            message = "expected 'module'";
        else if (result.result == Status::expected_enum)
            message = "expected 'enum'";
        else if (result.result == Status::expected_class)
            message = "expected 'class'";
        else if (result.result == Status::module_name_limit)
            message = "module name exceeds 4096 bytes";
        else if (result.result == Status::module_enum_limit)
            message = "module exceeds 64 enum definitions";
        else if (result.result == Status::empty_enum)
            message = "enum class requires at least one named case";
        else if (result.result == Status::enum_case_limit)
            message = "enum class exceeds 256 named cases";
        else if (result.result == Status::duplicate_enum_case) {
            if (end <= position)
                invalid();
            message = "duplicate enum case: " + tokens[end - 1].text;
        } else if (result.result == Status::explicit_enum_value)
            message = "enum cases cannot have explicit values";
        else if (result.result == Status::expected_colon)
            message = "expected ':'";
        else if (result.result == Status::namespace_nesting_limit)
            message = "namespace nesting exceeds 32 components";
        else if (result.result == Status::export_interface_required)
            message = "export declarations require an export module interface";
        else if (result.result == Status::module_reexport)
            message = "module reexports are not supported";
        else if (result.result == Status::imports_after_declarations)
            message = "imports must precede declarations";
        else if (result.result == Status::template_parameter_limit)
            message = "templates require one or two Scalar or Value parameters";
        else if (result.result == Status::template_parameter_kind)
            message = "template parameters require Scalar, Value or bounded i64 capacity";
        else if (result.result == Status::template_parameter_name)
            message = "duplicate or reserved template parameter";
        else if (result.result == Status::template_capacity_order)
            message = "template capacity requires a preceding Scalar parameter";
        else if (result.result == Status::template_declaration_kind)
            message = "only class or namespace-level function templates are supported";
        else if (result.result == Status::function_template_capacity)
            message = "function templates require only Scalar or Value type parameters";
        else if (result.result == Status::class_template_shadow)
            message = "class name cannot shadow a template parameter";
        else if (result.result == Status::expected_end)
            message = stop == Stop::close_parenthesis ? "expected ')'" : "expected ';'";
        else
            invalid();
        throw Error(DiagnosticCode::UnexpectedToken, message + " (found '" + at.text + "')", at.span);
    }
    const auto tokenCount = result.token_count + (half ? 1 : 0);
    if (result.token_count == 0 || result.node_count > result.token_count || typeCount > tokenCount ||
        statementCount > result.token_count ||
        (result.node_count == 0 ? edgeCount != 0 : edgeCount >= result.node_count) ||
        (declarationType ? result.node_count != 0 || typeCount == 0 || result.root_node != typeCount - 1
         : body || callable || field || header || module
             ? statementCount == 0 || result.root_node != statementCount - 1
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
    // The production resolver consumes the Aurora forest directly. On success
    // only import/header metadata crosses here; no unresolved host AST is built.
    // Errors reuse the existing checked type/diagnostic conversion below.
    std::optional<hosted_abi::compiler_parser::AdmissionResult> earlyAdmission;
    if (externalArena) {
        hosted_abi::AdmissionInput admissionInput;
        admissionInput.source = input.source;
        admissionInput.root = result.root_node;
        admissionInput.configuration = admissionConfiguration();
        earlyAdmission.emplace();
        aurora_hosted_parser_admit(arena.data(), &admissionInput, &*earlyAdmission);
        const auto &admission = *earlyAdmission;
        if (admission.result == AdmissionStatus::success) {
            if (admission.token_index != -1 || admission.end_token != -1 || admission.type_node != -1 ||
                admission.detail != 0 || end + 1 != tokens.size())
                invalid();
            SyntaxNode root;
            aurora_hosted_parser_syntax(arena.data(), result.root_node, &root);
            if (root.tag != SyntaxKind::module_definition || root.body_node < 0 || root.body_node >= result.root_node)
                invalid();
            SyntaxNode preamble;
            aurora_hosted_parser_syntax(arena.data(), root.body_node, &preamble);
            if (preamble.tag != SyntaxKind::preamble || preamble.qualifier < 0 || preamble.qualifier > 1)
                invalid();
            ParsedModuleSyntax parsed;
            // Inspect admitted syntax, never raw source spellings: comments,
            // strings and unrelated user names cannot enable a builtin family.
            const auto callName = [](const std::string &value) {
                return value == "CallSession" || value == "CallResult" || value == "CallStatus";
            };
            const auto portName = [](const std::string &value) {
                return value == "PortRange" || value == "PortWriteResult";
            };
            for (std::int64_t index = 0; index < typeCount; ++index) {
                TypeSyntax type;
                aurora_hosted_parser_type(arena.data(), index, &type);
                if (type.token_index < 0 || type.name_end < type.token_index || type.name_end >= tokenCount)
                    invalid();
                if ((type.tag == TypeSyntaxKind::builtin_type || type.tag == TypeSyntaxKind::builtin_class) &&
                    callName(text(type.name_end)))
                    parsed.callFamily = true;
                if ((type.tag == TypeSyntaxKind::builtin_type || type.tag == TypeSyntaxKind::builtin_class) &&
                    portName(text(type.name_end)))
                    parsed.portFamily = true;
            }
            // Enum cases can appear without a declaration/type node, including
            // in an uninstantiated template body.
            for (std::int64_t index = 0; index < result.node_count; ++index) {
                Node node;
                aurora_hosted_parser_read(arena.data(), index, &node);
                if (node.token_index < 0 || node.name_end < node.token_index || node.name_end >= tokenCount)
                    invalid();
                if ((node.tag == NodeKind::name || node.tag == NodeKind::call || node.tag == NodeKind::construct) &&
                    node.name_end >= node.token_index + 2 && text(node.token_index) == "builtin" &&
                    text(node.token_index + 1) == "::" && callName(text(node.token_index + 2)))
                    parsed.callFamily = true;
                if ((node.tag == NodeKind::name || node.tag == NodeKind::call || node.tag == NodeKind::construct) &&
                    node.name_end >= node.token_index + 2 && text(node.token_index) == "builtin" &&
                    text(node.token_index + 1) == "::" && portName(text(node.token_index + 2)))
                    parsed.portFamily = true;
            }
            parsed.root = result.root_node;
            parsed.moduleName = name(preamble.token_index, preamble.binding_token);
            parsed.interfaceUnit = preamble.qualifier != 0;
            auto limit = root.body_node;
            for (auto child = preamble.body_node; child != -1;) {
                if (child < 0 || child >= limit)
                    invalid();
                SyntaxNode imported;
                aurora_hosted_parser_syntax(arena.data(), child, &imported);
                if (imported.tag != SyntaxKind::import_name || imported.end_token <= imported.token_index)
                    invalid();
                auto spelling = name(imported.token_index, imported.end_token - 1);
                auto token = tokens[position + static_cast<std::size_t>(imported.token_index)];
                token.text = std::move(spelling);
                token.span.end = tokens[position + static_cast<std::size_t>(imported.end_token - 1)].span.end;
                parsed.imports.push_back(std::move(token));
                parsed.importSyntax.push_back(child);
                limit = child;
                child = imported.previous_node;
            }
            std::reverse(parsed.imports.begin(), parsed.imports.end());
            std::reverse(parsed.importSyntax.begin(), parsed.importSyntax.end());
            ImportedSyntax imported;
            imported.next = {end, half};
            imported.moduleSyntax.emplace(std::move(parsed));
            return imported;
        }
    }
    if (header) {
        if (result.node_count != 0 || edgeCount != 0 || typeCount != 0)
            invalid();
        const auto tokenAt = [&](std::int64_t ordinal) -> const Token & {
            if (ordinal < 0 || ordinal >= tokenCount)
                invalid();
            return tokens[position + static_cast<std::size_t>(ordinal)];
        };
        SyntaxNode root;
        aurora_hosted_parser_syntax(arena.data(), result.root_node, &root);
        if (root.tag != (preamble ? SyntaxKind::preamble : SyntaxKind::enum_definition))
            invalid();
        ImportedSyntax imported;
        imported.next = {end, half};
        if (preamble) {
            if (root.qualifier < 0 || root.qualifier > 1)
                invalid();
            imported.preamble.emplace();
            imported.preamble->moduleName = name(root.token_index, root.binding_token);
            imported.preamble->interfaceUnit = root.qualifier != 0;
        } else
            imported.enumeration.emplace(tokenAt(root.token_index));
        std::vector<Token> names;
        auto child = root.body_node;
        auto limit = result.root_node;
        while (child != -1) {
            if (child < 0 || child >= limit)
                invalid();
            SyntaxNode node;
            aurora_hosted_parser_syntax(arena.data(), child, &node);
            if (node.tag != (preamble ? SyntaxKind::import_name : SyntaxKind::enum_case))
                invalid();
            auto token = tokenAt(node.token_index);
            if (preamble) {
                if (node.end_token <= node.token_index)
                    invalid();
                token.text = name(node.token_index, node.end_token - 1);
                token.span.end = tokenAt(node.end_token - 1).span.end;
            }
            names.push_back(std::move(token));
            limit = child;
            child = node.previous_node;
        }
        if (names.size() + 1 != static_cast<std::size_t>(statementCount))
            invalid();
        std::reverse(names.begin(), names.end());
        if (preamble)
            imported.preamble->imports = std::move(names);
        else
            imported.enumeration->cases = std::move(names);
        return imported;
    }
    // Syntax records form a closed, child-before-parent forest. List families
    // cannot alias each other or executable blocks. These checks bound host
    // ownership and construction depth; Aurora owns all declaration/body grammar.
    std::vector<SyntaxNode> statements(static_cast<std::size_t>(statementCount));
    std::vector<bool> statementUsed(static_cast<std::size_t>(statementCount), false);
    std::vector<std::vector<std::int64_t>> statementLists(static_cast<std::size_t>(statementCount));
    std::vector<std::vector<std::int64_t>> parameterLists(static_cast<std::size_t>(statementCount));
    std::vector<int> containerDepth(static_cast<std::size_t>(statementCount), 0);
    std::vector<int> blockDepth(static_cast<std::size_t>(statementCount), 0);
    const auto executable = [](SyntaxKind kind) {
        return kind >= SyntaxKind::block && kind <= SyntaxKind::index_assign;
    };
    for (std::int64_t index = 0; index < statementCount; ++index) {
        auto &statement = statements[static_cast<std::size_t>(index)];
        aurora_hosted_parser_syntax(arena.data(), index, &statement);
        if (!hosted_abi::compiler_parser::validRaw(statement.tag) || statement.tag == SyntaxKind::invalid ||
            statement.token_index < 0 || statement.token_index >= statement.end_token ||
            statement.end_token > result.token_count || statement.previous_node < -1 ||
            statement.previous_node >= index || statement.expression_root < -1 ||
            statement.expression_root >= result.node_count || statement.target_root < -1 ||
            statement.target_root >= result.node_count || statement.declared_type < -1 ||
            statement.declared_type >= typeCount || statement.binding_token < -1 ||
            statement.binding_token >= result.token_count || statement.body_node < -1 || statement.body_node >= index ||
            statement.other_node < -1 || statement.other_node >= index || statement.borrow_token < -1 ||
            statement.borrow_token >= result.token_count || (statement.qualifier != 0 && statement.qualifier != 1))
            invalid();
        const bool container = statement.tag >= SyntaxKind::preamble;
        const bool local = statement.tag == SyntaxKind::local;
        const bool block = statement.tag == SyntaxKind::block;
        const bool conditional = statement.tag == SyntaxKind::conditional;
        const bool loop = statement.tag == SyntaxKind::loop;
        const bool fieldNode = statement.tag == SyntaxKind::field;
        const bool parameter = statement.tag == SyntaxKind::parameter;
        const bool initializer = statement.tag == SyntaxKind::initializer;
        const bool constructor = statement.tag == SyntaxKind::constructor;
        const bool callableNode =
            statement.tag == SyntaxKind::function || statement.tag == SyntaxKind::method || constructor;
        const bool assignment = statement.tag == SyntaxKind::assign || statement.tag == SyntaxKind::field_assign ||
                                statement.tag == SyntaxKind::index_assign;
        if (!parameter && statement.borrow_token != -1)
            invalid();
        if (container) {
            if (!module || statement.expression_root != -1 || statement.target_root != -1 ||
                statement.declared_type != -1 || statement.borrow_token != -1)
                invalid();
            if (statement.tag == SyntaxKind::preamble || statement.tag == SyntaxKind::namespace_definition) {
                if (statement.binding_token < statement.token_index || statement.other_node != -1)
                    invalid();
            } else if (statement.binding_token != -1)
                invalid();
            if (statement.tag == SyntaxKind::import_name || statement.tag == SyntaxKind::enum_case ||
                statement.tag == SyntaxKind::template_scalar || statement.tag == SyntaxKind::template_value ||
                statement.tag == SyntaxKind::template_capacity) {
                if (statement.body_node != -1 || statement.other_node != -1 || statement.qualifier != 0)
                    invalid();
            } else if (statement.tag == SyntaxKind::module_definition || statement.tag == SyntaxKind::declaration) {
                if (statement.body_node < 0)
                    invalid();
            } else if (statement.other_node != -1)
                invalid();
        } else if (fieldNode) {
            if ((!field && !module) || (!module && index != result.root_node) || statement.previous_node != -1 ||
                statement.expression_root != -1 || statement.target_root != -1 || statement.declared_type < 0 ||
                statement.binding_token <= statement.token_index || statement.body_node != -1 ||
                statement.other_node != -1 || statement.qualifier != 0)
                invalid();
        } else if (parameter) {
            if ((!callable && !module) || statement.expression_root != -1 || statement.target_root != -1 ||
                statement.declared_type < 0 || statement.binding_token < 0 || statement.body_node != -1 ||
                statement.other_node != -1)
                invalid();
        } else if (initializer) {
            if ((!callable && !module) || statement.expression_root < 0 || statement.target_root != -1 ||
                statement.declared_type != -1 || statement.binding_token != -1 || statement.body_node != -1 ||
                statement.other_node != -1 || statement.qualifier != 0)
                invalid();
        } else if (callableNode) {
            if ((!callable && !module) || statement.previous_node != -1 || statement.expression_root != -1 ||
                statement.target_root != -1 || (statement.declared_type >= 0) == constructor ||
                statement.binding_token != -1 || (!constructor && statement.body_node < 0) ||
                (statement.tag != SyntaxKind::method && statement.qualifier != 0))
                invalid();
        } else if ((statement.expression_root == -1) != block || (statement.target_root >= 0) != assignment ||
                   (statement.declared_type >= 0) != local || (statement.binding_token >= 0) != local ||
                   (!local && statement.qualifier != 0) ||
                   (!block && !conditional && !loop && statement.body_node != -1) ||
                   ((conditional || loop) && statement.body_node == -1) || (!conditional && statement.other_node != -1))
            invalid();
        const auto ownStatement = [&](std::int64_t child) -> const SyntaxNode & {
            if (child < 0 || child >= index || statementUsed[static_cast<std::size_t>(child)])
                invalid();
            statementUsed[static_cast<std::size_t>(child)] = true;
            return statements[static_cast<std::size_t>(child)];
        };
        auto &depth = blockDepth[static_cast<std::size_t>(index)];
        if (container) {
            auto &depth = containerDepth[static_cast<std::size_t>(index)];
            const auto own = [&](std::int64_t child) -> const SyntaxNode & {
                const auto &value = ownStatement(child);
                depth = std::max(depth, containerDepth[static_cast<std::size_t>(child)]);
                return value;
            };
            const auto list = [&](std::int64_t tail, auto accepts, std::vector<std::int64_t> &out) {
                for (auto child = tail; child != -1;) {
                    const auto &value = own(child);
                    if (!accepts(value.tag))
                        invalid();
                    out.push_back(child);
                    child = value.previous_node;
                }
                std::reverse(out.begin(), out.end());
            };
            auto &children = statementLists[static_cast<std::size_t>(index)];
            if (statement.tag == SyntaxKind::module_definition) {
                const auto &preamble = own(statement.body_node);
                if (preamble.tag != SyntaxKind::preamble || preamble.previous_node != -1)
                    invalid();
                list(
                    statement.other_node,
                    [](auto kind) {
                        return kind == SyntaxKind::declaration;
                    },
                    children);
            } else if (statement.tag == SyntaxKind::declaration) {
                const auto &child = own(statement.body_node);
                if (child.previous_node != -1 ||
                    (child.tag != SyntaxKind::function && child.tag != SyntaxKind::method &&
                     child.tag != SyntaxKind::constructor && child.tag != SyntaxKind::field &&
                     child.tag != SyntaxKind::enum_definition && child.tag != SyntaxKind::namespace_definition &&
                     child.tag != SyntaxKind::class_definition))
                    invalid();
                list(
                    statement.other_node,
                    [](auto kind) {
                        return kind >= SyntaxKind::template_scalar && kind <= SyntaxKind::template_capacity;
                    },
                    parameterLists[static_cast<std::size_t>(index)]);
            } else if (statement.tag == SyntaxKind::namespace_definition ||
                       statement.tag == SyntaxKind::class_definition)
                list(
                    statement.body_node,
                    [](auto kind) {
                        return kind == SyntaxKind::declaration;
                    },
                    children);
            else if (statement.tag == SyntaxKind::preamble)
                list(
                    statement.body_node,
                    [](auto kind) {
                        return kind == SyntaxKind::import_name;
                    },
                    children);
            else if (statement.tag == SyntaxKind::enum_definition)
                list(
                    statement.body_node,
                    [](auto kind) {
                        return kind == SyntaxKind::enum_case;
                    },
                    children);
            if (++depth > 128)
                invalid();
        } else if (block || constructor) {
            auto &children = statementLists[static_cast<std::size_t>(index)];
            for (auto child = statement.body_node; child != -1;) {
                const auto &value = ownStatement(child);
                if (constructor ? value.tag != SyntaxKind::initializer : !executable(value.tag))
                    invalid();
                depth = std::max(depth, blockDepth[static_cast<std::size_t>(child)]);
                children.push_back(child);
                child = value.previous_node;
            }
            std::reverse(children.begin(), children.end());
            if (block && ++depth > 128)
                invalid();
        } else if (conditional || loop || callableNode) {
            const auto &branch = ownStatement(statement.body_node);
            if (branch.tag != SyntaxKind::block || branch.previous_node != -1)
                invalid();
            // Control/callable nodes unwrap blocks without adding lexical depth.
            depth = blockDepth[static_cast<std::size_t>(statement.body_node)];
            if (conditional && statement.other_node >= 0) {
                const auto &other = ownStatement(statement.other_node);
                if (other.tag != SyntaxKind::block || other.previous_node != -1)
                    invalid();
                depth = std::max(depth, blockDepth[static_cast<std::size_t>(statement.other_node)]);
            }
        }
        if (callableNode) {
            if (!module && index != result.root_node)
                invalid();
            auto &parameters = parameterLists[static_cast<std::size_t>(index)];
            for (auto child = statement.other_node; child != -1;) {
                const auto &value = ownStatement(child);
                if (value.tag != SyntaxKind::parameter)
                    invalid();
                parameters.push_back(child);
                child = value.previous_node;
            }
            std::reverse(parameters.begin(), parameters.end());
        }
    }
    if (body || callable || field || module) {
        const auto &root = statements[static_cast<std::size_t>(result.root_node)];
        const auto expected = module                   ? SyntaxKind::module_definition
                              : field                  ? SyntaxKind::field
                              : body                   ? SyntaxKind::block
                              : stop == Stop::function ? SyntaxKind::function
                              : stop == Stop::method   ? SyntaxKind::method
                                                       : SyntaxKind::constructor;
        if (root.tag != expected || root.previous_node != -1 ||
            statementUsed[static_cast<std::size_t>(result.root_node)])
            invalid();
        statementUsed[static_cast<std::size_t>(result.root_node)] = true;
        if (std::find(statementUsed.begin(), statementUsed.end(), false) != statementUsed.end())
            invalid();
    }
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
        if (type.tag <= TypeSyntaxKind::invalid || type.tag > TypeSyntaxKind::builtin_class || type.token_index < 0 ||
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
                 !((body || callable || field || declarationType || module) && type.owner_role == 3)) ||
                (type.owner_role == 1 && (type.tag != TypeSyntaxKind::named || type.first_child < 0)) ||
                type.tag == TypeSyntaxKind::capacity || type.tag == TypeSyntaxKind::length_parameter)
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
        if (type.tag == TypeSyntaxKind::capacity) {
            const auto capacity = capacities[static_cast<std::size_t>(child)];
            if (capacity < 1 || capacity > 64)
                invalid();
            return TemplateArgument::capacity(capacity);
        }
        if (type.tag != TypeSyntaxKind::i64_type && type.tag != TypeSyntaxKind::u64_type &&
            type.tag != TypeSyntaxKind::u8_type && type.tag != TypeSyntaxKind::bool_type &&
            type.tag != TypeSyntaxKind::named && type.tag != TypeSyntaxKind::parameter)
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
        if (type.tag == TypeSyntaxKind::array_type) {
            if (type.first_child < 0 || type.second_child < 0)
                invalid();
        } else if (type.tag == TypeSyntaxKind::owned_values) {
            if (type.first_child < 0 || type.second_child != -1)
                invalid();
        } else if (type.tag != TypeSyntaxKind::named && (type.first_child != -1 || type.second_child != -1))
            invalid();
        auto &value = typeValues[static_cast<std::size_t>(index)];
        const auto &spelling = text(type.token_index);
        if (type.tag == TypeSyntaxKind::i64_type || type.tag == TypeSyntaxKind::u64_type ||
            type.tag == TypeSyntaxKind::u8_type || type.tag == TypeSyntaxKind::bool_type) {
            value = type.tag == TypeSyntaxKind::i64_type   ? Type::I64
                    : type.tag == TypeSyntaxKind::u64_type ? Type::U64
                    : type.tag == TypeSyntaxKind::u8_type  ? Type::U8
                                                           : Type::Bool;
        } else if (type.tag == TypeSyntaxKind::parameter || type.tag == TypeSyntaxKind::length_parameter) {
            value = Type(TypeKind::Parameter);
            value.className = spelling;
        } else if (type.tag == TypeSyntaxKind::capacity) {
            std::int64_t capacity = 0;
            for (const auto byte : spelling) {
                if (byte < '0' || byte > '9' || capacity > 4096)
                    invalid();
                capacity = capacity * 10 + byte - '0';
            }
            if (capacity < 1 || capacity > 4096)
                invalid();
            capacities[static_cast<std::size_t>(index)] = capacity;
        } else if (type.tag == TypeSyntaxKind::named) {
            value = Type(name(type.token_index, type.name_end));
            if (type.first_child >= 0)
                value.templateArguments.push_back(argumentValue(type.first_child));
            if (type.second_child >= 0)
                value.templateArguments.push_back(argumentValue(type.second_child));
        } else if (type.tag == TypeSyntaxKind::own_type || type.tag == TypeSyntaxKind::ref_type ||
                   type.tag == TypeSyntaxKind::mutref_type) {
            value = type.tag == TypeSyntaxKind::own_type   ? Type::Own
                    : type.tag == TypeSyntaxKind::ref_type ? Type::Ref
                                                           : Type::MutRef;
        } else if (type.tag == TypeSyntaxKind::builtin_type || type.tag == TypeSyntaxKind::builtin_class) {
            const auto &builtin = text(type.name_end);
            if (builtin == "ByteRegion")
                value = Type::ByteRegion;
            else if (builtin == "OwnedBytes")
                value = Type::OwnedBytes;
            else if (builtin == "ConsoleSession")
                value = Type::ConsoleSession;
            else if (builtin == "DisplaySession")
                value = Type::DisplaySession;
            else if (builtin == "PortRange")
                value = Type::PortRange;
            else if (builtin == "PortWriteResult")
                value = service::portWriteResultType();
            else if (builtin == "CallSession")
                value = Type::CallSession;
            else if (builtin == "CallResult")
                value = service::callResultType();
            else if (builtin == "CallStatus")
                value = service::callStatusType();
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
        } else if (type.tag == TypeSyntaxKind::byte_span) {
            value = Type::ByteSpan;
        } else if (type.tag == TypeSyntaxKind::array_type || type.tag == TypeSyntaxKind::owned_values) {
            const auto &elementSyntax = types[static_cast<std::size_t>(type.first_child)];
            const auto &element = typeValues[static_cast<std::size_t>(type.first_child)];
            if (type.tag == TypeSyntaxKind::owned_values) {
                if (!element.isClass() || !element.templateArguments.empty())
                    invalid();
                value = Type::ownedValues(element);
            } else {
                const auto &length = types[static_cast<std::size_t>(type.second_child)];
                if (elementSyntax.tag == TypeSyntaxKind::capacity ||
                    elementSyntax.tag == TypeSyntaxKind::length_parameter ||
                    (!scalar(element) && element.kind != TypeKind::Parameter && !element.isClass()) ||
                    (length.tag != TypeSyntaxKind::capacity && length.tag != TypeSyntaxKind::length_parameter))
                    invalid();
                value = Type::array(element, static_cast<int>(capacities[static_cast<std::size_t>(type.second_child)]));
                if (length.tag == TypeSyntaxKind::length_parameter)
                    value.lengthParameter = text(length.token_index);
                else if (element.isClass() && value.length > maximumClassScalarArrayLength)
                    invalid();
            }
        } else
            invalid();
    }
    if (module) {
        hosted_abi::AdmissionInput admissionInput;
        admissionInput.source = input.source;
        admissionInput.root = result.root_node;
        admissionInput.configuration = admissionConfiguration();
        hosted_abi::compiler_parser::AdmissionResult admission;
        if (earlyAdmission)
            admission = *earlyAdmission;
        else
            aurora_hosted_parser_admit(arena.data(), &admissionInput, &admission);
        if (admission.result < AdmissionStatus::success || admission.result >= AdmissionStatus::invalid)
            invalid();
        if (admission.result == AdmissionStatus::success || admission.result == AdmissionStatus::allocation_failure) {
            if (admission.token_index != -1 || admission.end_token != -1 || admission.type_node != -1 ||
                admission.detail != 0)
                invalid();
            if (admission.result == AdmissionStatus::allocation_failure)
                throw Error(DiagnosticCode::Internal, "hosted declaration admission allocation failed", begin);
        } else {
            if (admission.token_index < 0 || admission.token_index > result.token_count ||
                admission.end_token <= admission.token_index || admission.end_token > result.token_count + 1)
                invalid();
            const auto &at = tokens[position + static_cast<std::size_t>(admission.token_index)];
            auto span = at.span;
            span.end = tokens[position + static_cast<std::size_t>(admission.end_token) - 1].span.end;
            if (admission.result == AdmissionStatus::unsupported_field) {
                if (admission.type_node < 0 || admission.type_node >= typeCount || admission.detail != 0)
                    invalid();
                throw Error(
                    DiagnosticCode::UnsupportedFieldType,
                    "unsupported class field type '" +
                        typeName(typeValues[static_cast<std::size_t>(admission.type_node)]) +
                        "': class fields require scalar, class, private fixed-array or private owned-byte storage",
                    span);
            }
            if (admission.type_node != -1 || admission.end_token != admission.token_index + 1 ||
                (admission.result != AdmissionStatus::array_capacity && admission.detail != 0))
                invalid();
            std::string message;
            switch (admission.result) {
            case AdmissionStatus::function_shadow:
                message = "function name cannot shadow a template parameter";
                break;
            case AdmissionStatus::typed_constructor:
                message = "constructor cannot have a return type";
                break;
            case AdmissionStatus::borrowed_parameter:
                message = "borrowed parameters require a supported leading ownership reference signature on an "
                          "ordinary function";
                break;
            case AdmissionStatus::const_parameter:
                message = "const parameter spelling requires a supported owning-class reference";
                break;
            case AdmissionStatus::function_parameter:
                message = "only scalar function parameters or scalar-field class values are supported";
                break;
            case AdmissionStatus::method_parameter:
                message = "only scalar or enum method parameters are supported";
                break;
            case AdmissionStatus::function_result:
                message = "only scalar function results or scalar-field class values are supported";
                break;
            case AdmissionStatus::method_result:
                message = "only scalar, enum, class or readonly span method results are supported";
                break;
            case AdmissionStatus::public_array:
                message = "array fields must be private";
                break;
            case AdmissionStatus::array_capacity:
                if (admission.detail != admissionInput.configuration.scalar_array_limit &&
                    admission.detail != admissionInput.configuration.byte_array_limit)
                    invalid();
                message = "class array field capacity must be between 1 and " + std::to_string(admission.detail);
                break;
            case AdmissionStatus::public_owner:
                message = "owned byte fields must be private";
                break;
            case AdmissionStatus::templated_owner:
                message = "owning class templates are unsupported";
                break;
            case AdmissionStatus::missing_function:
                message = "module must contain a function";
                break;
            default:
                invalid();
            }
            throw Error(DiagnosticCode::UnexpectedToken, message + " (found '" + at.text + "')", span);
        }
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
    // Every expression root belongs to one statement/initializer field, or to
    // the expression result. Unreferenced records and shared roots fail closed.
    const auto takeExpression = [&](std::int64_t root) {
        if (root < 0 || root >= result.node_count || used[static_cast<std::size_t>(root)])
            invalid();
        used[static_cast<std::size_t>(root)] = true;
        return nodes[static_cast<std::size_t>(root)];
    };
    const auto takeDeclarationType = [&](const SyntaxNode &syntax) {
        if (syntax.declared_type < 0 || syntax.declared_type >= typeCount)
            invalid();
        const auto typeIndex = static_cast<std::size_t>(syntax.declared_type);
        const auto &type = types[typeIndex];
        if (type.owner_role != 3 || type.owner_token != syntax.token_index ||
            declarationRoots[static_cast<std::size_t>(syntax.token_index)] != syntax.declared_type ||
            typeUsed[typeIndex])
            invalid();
        typeUsed[typeIndex] = true;
        return std::move(typeValues[typeIndex]);
    };
    std::vector<StatementPtr> statementValues(static_cast<std::size_t>(statementCount));
    for (std::int64_t index = 0; index < statementCount; ++index) {
        const auto &syntax = statements[static_cast<std::size_t>(index)];
        if (!executable(syntax.tag))
            continue;
        auto statement = std::make_shared<Statement>(tokens[position + static_cast<std::size_t>(syntax.token_index)]);
        if (syntax.tag == SyntaxKind::block) {
            statement->kind = "block";
            for (const auto child : statementLists[static_cast<std::size_t>(index)])
                statement->body.push_back(statementValues[static_cast<std::size_t>(child)]);
        } else {
            statement->expr = takeExpression(syntax.expression_root);
            if (syntax.tag == SyntaxKind::conditional || syntax.tag == SyntaxKind::loop) {
                statement->kind = syntax.tag == SyntaxKind::conditional ? "if" : "while";
                statement->body = std::move(statementValues[static_cast<std::size_t>(syntax.body_node)]->body);
                if (syntax.other_node >= 0)
                    statement->other = std::move(statementValues[static_cast<std::size_t>(syntax.other_node)]->body);
            } else if (syntax.tag == SyntaxKind::local) {
                const auto &binding = tokens[position + static_cast<std::size_t>(syntax.binding_token)];
                statement->kind = "let";
                statement->type = takeDeclarationType(syntax);
                statement->name = binding.text;
                statement->bindingSpan = binding.span;
                statement->mutableValue = syntax.qualifier == 1;
            } else if (syntax.tag == SyntaxKind::return_value)
                statement->kind = "return";
            else if (syntax.tag == SyntaxKind::static_assertion)
                statement->kind = "static_assert";
            else if (syntax.tag == SyntaxKind::expression)
                statement->kind = "expression";
            else {
                auto target = takeExpression(syntax.target_root);
                if (syntax.tag == SyntaxKind::assign) {
                    if (target->op != "name" || !target->args.empty())
                        invalid();
                    statement->kind = "assign";
                    statement->name = target->token.text;
                } else if (syntax.tag == SyntaxKind::field_assign) {
                    if (target->op != "member" || target->args.size() != 1 || target->args[0]->op != "name" ||
                        !target->args[0]->args.empty())
                        invalid();
                    statement->kind = "field_assign";
                    statement->name = target->args[0]->token.text;
                    statement->fieldName = target->token.text;
                } else {
                    if (syntax.tag != SyntaxKind::index_assign || target->op != "index" || target->args.size() != 2)
                        invalid();
                    statement->kind = "index_assign";
                    statement->target = std::move(target);
                }
            }
        }
        statementValues[static_cast<std::size_t>(index)] = std::move(statement);
    }
    const auto tokenAt = [&](std::int64_t ordinal) -> const Token & {
        if (ordinal < 0 || ordinal > result.token_count)
            invalid();
        return tokens[position + static_cast<std::size_t>(ordinal)];
    };
    const auto callableValue = [&](std::size_t root, Stop stop) {
        const auto &syntax = statements[root];
        ParsedCallable parsed(tokenAt(syntax.token_index));
        auto &function = parsed.function;
        parsed.next = {end, half};
        function.constructor = stop == Stop::constructor;
        function.receiverConst = syntax.qualifier == 1;
        for (const auto child : parameterLists[root]) {
            const auto &parameterSyntax = statements[static_cast<std::size_t>(child)];
            Param parameter;
            parameter.type = takeDeclarationType(parameterSyntax);
            parameter.name = tokenAt(parameterSyntax.binding_token).text;
            parameter.borrowConst = parameterSyntax.qualifier == 1;
            parameter.borrowed = parameterSyntax.borrow_token >= 0;
            if (parameter.borrowed)
                parameter.borrowSpan = tokenAt(parameterSyntax.borrow_token).span;
            function.params.push_back(std::move(parameter));
        }
        if (function.constructor) {
            for (const auto child : statementLists[root]) {
                const auto &initializer = statements[static_cast<std::size_t>(child)];
                function.initializers.emplace_back(tokenAt(initializer.token_index),
                                                   takeExpression(initializer.expression_root));
            }
        } else {
            function.result = takeDeclarationType(syntax);
            const auto block = static_cast<std::size_t>(syntax.body_node);
            function.body = std::move(statementValues[block]->body);
        }
        return parsed;
    };
    const auto fieldValue = [&](std::size_t root) {
        const auto &syntax = statements[root];
        const auto binding = position + static_cast<std::size_t>(syntax.binding_token);
        ParsedField parsed(tokens[binding], takeDeclarationType(syntax));
        parsed.next = {end, half};
        return parsed;
    };
    ImportedSyntax imported;
    if (declarationType) {
        const auto root = static_cast<std::size_t>(result.root_node);
        if (types[root].owner_role != 3 || types[root].owner_token != 0 || typeUsed[root])
            invalid();
        typeUsed[root] = true;
        imported.type = std::move(typeValues[root]);
    } else if (body)
        imported.body = std::move(statementValues[static_cast<std::size_t>(result.root_node)]->body);
    else if (callable)
        imported.callable.emplace(callableValue(static_cast<std::size_t>(result.root_node), stop));
    else if (field)
        imported.field.emplace(fieldValue(static_cast<std::size_t>(result.root_node)));
    else if (module) {
        imported.program.emplace();
        auto &program = *imported.program;
        const auto root = static_cast<std::size_t>(result.root_node);
        const auto preambleIndex = static_cast<std::size_t>(statements[root].body_node);
        const auto &preambleSyntax = statements[preambleIndex];
        program.moduleName = name(preambleSyntax.token_index, preambleSyntax.binding_token);
        program.interfaceUnit = preambleSyntax.qualifier != 0;
        for (const auto child : statementLists[preambleIndex]) {
            const auto &syntax = statements[static_cast<std::size_t>(child)];
            if (syntax.end_token <= syntax.token_index)
                invalid();
            auto token = tokenAt(syntax.token_index);
            token.text = name(syntax.token_index, syntax.end_token - 1);
            token.span.end = tokenAt(syntax.end_token - 1).span.end;
            program.imports.push_back(std::move(token));
        }
        const auto templateParameters = [&](std::size_t wrapper) {
            std::vector<TemplateParameter> parameters;
            for (const auto child : parameterLists[wrapper]) {
                const auto &parameter = statements[static_cast<std::size_t>(child)];
                const auto kind = parameter.tag == SyntaxKind::template_scalar  ? TemplateParameterKind::Scalar
                                  : parameter.tag == SyntaxKind::template_value ? TemplateParameterKind::Value
                                                                                : TemplateParameterKind::Capacity;
                parameters.emplace_back(kind, tokenAt(parameter.token_index).text);
            }
            return parameters;
        };
        const auto declarations =
            [&](auto &&self, std::size_t container, const std::string &scope, bool exportScope) -> void {
            for (const auto entry : statementLists[container]) {
                const auto wrapper = static_cast<std::size_t>(entry);
                const auto &declaration = statements[wrapper];
                const auto child = static_cast<std::size_t>(declaration.body_node);
                const auto &syntax = statements[child];
                const bool exported = exportScope || declaration.qualifier != 0;
                if (syntax.tag == SyntaxKind::namespace_definition) {
                    const auto local = name(syntax.token_index, syntax.binding_token);
                    const auto fullScope = scope.empty() ? local : scope + "::" + local;
                    for (std::size_t end = 0;;) {
                        end = fullScope.find("::", end);
                        program.namespaces.insert(fullScope.substr(0, end));
                        if (end == std::string::npos)
                            break;
                        end += 2;
                    }
                    self(self, child, fullScope, exported);
                } else if (syntax.tag == SyntaxKind::enum_definition) {
                    EnumDefinition definition(tokenAt(syntax.token_index));
                    definition.scope = scope;
                    definition.exported = exported;
                    for (const auto item : statementLists[child])
                        definition.cases.push_back(tokenAt(statements[static_cast<std::size_t>(item)].token_index));
                    program.enums.push_back(std::move(definition));
                } else if (syntax.tag == SyntaxKind::class_definition) {
                    ClassDefinition definition(tokenAt(syntax.token_index));
                    definition.scope = scope;
                    definition.exported = exported;
                    definition.templateParameters = templateParameters(wrapper);
                    for (const auto memberEntry : statementLists[child]) {
                        const auto &member = statements[static_cast<std::size_t>(memberEntry)];
                        const auto memberRoot = static_cast<std::size_t>(member.body_node);
                        const auto kind = statements[memberRoot].tag;
                        const bool publicAccess = member.qualifier != 0;
                        if (kind == SyntaxKind::field) {
                            auto parsed = fieldValue(memberRoot);
                            parsed.field.publicAccess = publicAccess;
                            definition.fields.push_back(std::move(parsed.field));
                        } else {
                            if (kind != SyntaxKind::method && kind != SyntaxKind::constructor)
                                invalid();
                            const auto stop = kind == SyntaxKind::method ? Stop::method : Stop::constructor;
                            auto parsed = callableValue(memberRoot, stop);
                            parsed.function.scope = scope;
                            parsed.function.publicAccess = publicAccess;
                            definition.methods.push_back(std::move(parsed.function));
                        }
                    }
                    auto &definitions = definition.templateParameters.empty() ? program.classes : program.templates;
                    definitions.push_back(std::move(definition));
                } else {
                    if (syntax.tag != SyntaxKind::function)
                        invalid();
                    auto parsed = callableValue(child, Stop::function);
                    parsed.function.scope = scope;
                    parsed.function.exported = exported;
                    parsed.function.templateParameters = templateParameters(wrapper);
                    auto &functions =
                        parsed.function.templateParameters.empty() ? program.functions : program.functionTemplates;
                    functions.push_back(std::move(parsed.function));
                }
            }
        };
        declarations(declarations, root, "", false);

    } else
        imported.expression = takeExpression(result.root_node);
    if (std::find(used.begin(), used.end(), false) != used.end() ||
        std::find(edgeUsed.begin(), edgeUsed.end(), false) != edgeUsed.end() ||
        std::find(typeUsed.begin(), typeUsed.end(), false) != typeUsed.end())
        invalid();
    imported.next = {end, half};
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
    auto parsed = parseHostedSyntax(tokens, {position}, stop, context);
    position = parsed.next.ordinal;
    return std::move(parsed.expression);
}

std::vector<StatementPtr>
parseHostedBody(const std::vector<Token> &tokens, std::size_t &position, const hosted_parser::Context &context) {
    auto parsed = parseHostedSyntax(tokens, {position}, Stop::body, context);
    position = parsed.next.ordinal;
    return std::move(parsed.body);
}

ParsedType
parseHostedType(const std::vector<Token> &tokens, hosted_parser::Cursor cursor, const hosted_parser::Context &context) {
    auto imported = parseHostedSyntax(tokens, cursor, Stop::type, context);
    return {std::move(imported.type), imported.next};
}

ParsedCallable parseHostedCallable(const std::vector<Token> &tokens,
                                   hosted_parser::Cursor cursor,
                                   Stop stop,
                                   const hosted_parser::Context &context) {
    if (stop != Stop::function && stop != Stop::method && stop != Stop::constructor)
        invalid();
    auto imported = parseHostedSyntax(tokens, cursor, stop, context);
    if (!imported.callable)
        invalid();
    return std::move(*imported.callable);
}

ParsedField parseHostedField(const std::vector<Token> &tokens,
                             hosted_parser::Cursor cursor,
                             const hosted_parser::Context &context) {
    auto imported = parseHostedSyntax(tokens, cursor, Stop::field, context);
    if (!imported.field)
        invalid();
    return std::move(*imported.field);
}

ParsedPreamble parseHostedPreamble(const std::vector<Token> &tokens, hosted_parser::Cursor cursor) {
    auto imported = parseHostedSyntax(tokens, cursor, Stop::preamble, {});
    return {std::move(*imported.preamble), imported.next};
}
ParsedModuleSyntax parseHostedModuleSyntax(const std::vector<Token> &tokens, void *arena) {
    if (!arena)
        invalid();
    auto imported = parseHostedSyntax(tokens, {}, Stop::module_definition, {}, 0, arena);
    if (!imported.moduleSyntax)
        invalid();
    return std::move(*imported.moduleSyntax);
}
Program parseHostedProgram(const std::vector<Token> &tokens) {
    auto imported = parseHostedSyntax(tokens, {}, Stop::module_definition, {});
    if (imported.next.ordinal + 1 != tokens.size() || imported.next.half != 0)
        invalid();
    return std::move(*imported.program);
}
ParsedEnum parseHostedEnum(const std::vector<Token> &tokens, hosted_parser::Cursor cursor, std::size_t enumCount) {
    auto imported = parseHostedSyntax(tokens, cursor, Stop::enum_definition, {}, enumCount);
    return {std::move(*imported.enumeration), imported.next};
}

} // namespace aurora
