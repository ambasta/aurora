// Diagnostics of rejected Aurora grammar and declaration results, and the
// copied admission configuration. Aurora owns the grammar; the resolver and
// formatter adapters render these for its source results.
#include "hosted_parser.hpp"

namespace aurora {
namespace {
using hosted_parser::AdmissionStatus;
using hosted_parser::Status;
using hosted_parser::Stop;

[[noreturn]] void invalid() {
    throw Error(DiagnosticCode::Internal, "hosted parser returned an invalid result");
}
} // namespace

namespace hosted_parser {
// Layout limits remain authoritative in the existing compiler helpers; the
// service masks and the full supported group set come from the Aurora catalog.
hosted_abi::compiler_parser::AdmissionConfig admissionConfiguration() {
    using hosted_abi::compiler_catalog::ServiceKind;
    hosted_abi::compiler_catalog::Summary catalog;
    aurora_hosted_catalog_summary(&catalog);
    const auto mask = [](ServiceKind kind) {
        return std::int64_t{1} << static_cast<int>(kind);
    };
    hosted_abi::compiler_parser::AdmissionConfig configuration;
    configuration.scalar_array_limit = maximumClassScalarArrayLength;
    configuration.byte_array_limit = maximumClassByteArrayLength;
    configuration.console_mask = mask(ServiceKind::Console);
    configuration.display_mask = mask(ServiceKind::Display);
    configuration.event_mask = mask(ServiceKind::IommuEvent);
    configuration.service_groups = catalog.serviceGroups;
    return configuration;
}
[[noreturn]] void rejectSyntax(Status status, Stop stop, const Token &at, const std::string &previous) {
    if (status == Status::allocation_failure)
        throw Error(DiagnosticCode::Internal, "hosted parser allocation failed", at.span);
    if (status == Status::block_nesting_limit)
        throw Error(DiagnosticCode::NestingLimit, "block nesting exceeds 128", at.span);
    if (status == Status::nesting_limit)
        throw Error(DiagnosticCode::NestingLimit, "expression parser nesting exceeds 128", at.span);
    if (status == Status::type_nesting_limit || status == Status::template_nesting_limit ||
        status == Status::call_template_nesting_limit)
        throw Error(DiagnosticCode::NestingLimit,
                    status == Status::type_nesting_limit       ? "type nesting exceeds 64"
                    : status == Status::template_nesting_limit ? "template-id nesting exceeds 4"
                                                               : "template-id nesting exceeds 5",
                    at.span);
    std::string message;
    if (status == Status::expected_expression)
        message = "expected expression";
    else if (status == Status::expected_close)
        message = "expected ')'";
    else if (status == Status::expected_index_close)
        message = "expected ']'";
    else if (status == Status::expected_brace_close)
        message = "expected '}'";
    else if (status == Status::expected_dot)
        message = "expected '.'";
    else if (status == Status::expected_equal)
        message = "expected '='";
    else if (status == Status::expected_brace_open)
        message = "expected '{'";
    else if (status == Status::expected_identifier)
        message = "expected identifier";
    else if (status == Status::reserved_identifier)
        message = "reserved identifier";
    else if (status == Status::reserved_builtin)
        message = "reserved builtin storage name";
    else if (status == Status::reserved_prefix)
        message = "reserved compiler identifier prefix: __au_";
    else if (status == Status::depth_limit)
        message = "expression AST depth exceeds 128";
    else if (status == Status::expected_angle_open)
        message = "expected '<'";
    else if (status == Status::expected_angle_close)
        message = "expected '>'";
    else if (status == Status::expected_scope)
        message = "expected '::'";
    else if (status == Status::expected_comma)
        message = "expected ','";
    else if (status == Status::expected_const)
        message = "expected 'const'";
    else if (status == Status::expected_u8)
        message = "expected 'u8'";
    else if (status == Status::expected_i64)
        message = "expected 'i64'";
    else if (status == Status::expected_array)
        message = "expected 'array'";
    else if (status == Status::reserved_type)
        message = "unsupported or reserved type spelling";
    else if (status == Status::expected_type)
        message = "expected type name";
    else if (status == Status::template_context)
        message = "template-id references inside template definitions are not supported";
    else if (status == Status::template_arity)
        message = "template arguments are limited to one or two types or capacity literals";
    else if (status == Status::template_argument)
        message = "template arguments require scalar, named class or enum types, or capacities from 1 to 64";
    else if (status == Status::capacity_argument)
        message = "capacity template arguments must be decimal literals from 1 to 64";
    else if (status == Status::nested_dependent)
        message = "nested dependent template arguments are not supported";
    else if (status == Status::owned_element)
        message = "owned values require a named concrete copied class";
    else if (status == Status::span_element)
        message = "typed spans require a named concrete copied class";
    else if (status == Status::array_element)
        message = "array elements require i64, u64, u8, bool or a concrete copied class";
    else if (status == Status::array_length)
        message = "array length requires a decimal integer literal between 1 and 4096";
    else if (status == Status::class_array_length)
        message = "class-element array capacity must be between 1 and 64";
    else if (status == Status::expected_open)
        message = "expected '('";
    else if (status == Status::expected_semicolon)
        message = "expected ';'";
    else if (status == Status::unterminated_block)
        message = "unterminated block";
    else if (status == Status::assignment_target)
        message = "assignment requires a local or local field";
    else if (status == Status::expected_auto)
        message = "expected 'auto'";
    else if (status == Status::expected_arrow)
        message = "expected '->'";
    else if (status == Status::expected_module)
        message = "expected 'module'";
    else if (status == Status::expected_enum)
        message = "expected 'enum'";
    else if (status == Status::expected_class)
        message = "expected 'class'";
    else if (status == Status::module_name_limit)
        message = "module name exceeds 4096 bytes";
    else if (status == Status::module_enum_limit)
        message = "module exceeds 64 enum definitions";
    else if (status == Status::empty_enum)
        message = "enum class requires at least one named case";
    else if (status == Status::enum_case_limit)
        message = "enum class exceeds 256 named cases";
    else if (status == Status::duplicate_enum_case)
        message = "duplicate enum case: " + previous;
    else if (status == Status::explicit_enum_value)
        message = "enum cases cannot have explicit values";
    else if (status == Status::expected_colon)
        message = "expected ':'";
    else if (status == Status::namespace_nesting_limit)
        message = "namespace nesting exceeds 32 components";
    else if (status == Status::export_interface_required)
        message = "export declarations require an export module interface";
    else if (status == Status::module_reexport)
        message = "module reexports are not supported";
    else if (status == Status::imports_after_declarations)
        message = "imports must precede declarations";
    else if (status == Status::template_parameter_limit)
        message = "templates require one or two Scalar or Value parameters";
    else if (status == Status::template_parameter_kind)
        message = "template parameters require Scalar, Value or bounded i64 capacity";
    else if (status == Status::template_parameter_name)
        message = "duplicate or reserved template parameter";
    else if (status == Status::template_capacity_order)
        message = "template capacity requires a preceding Scalar parameter";
    else if (status == Status::template_declaration_kind)
        message = "only class or namespace-level function templates are supported";
    else if (status == Status::function_template_capacity)
        message = "function templates require only Scalar or Value type parameters";
    else if (status == Status::class_template_shadow)
        message = "class name cannot shadow a template parameter";
    else if (status == Status::expected_end)
        message = stop == Stop::close_parenthesis ? "expected ')'" : "expected ';'";
    else
        invalid();
    throw Error(DiagnosticCode::UnexpectedToken, message + " (found '" + at.text + "')", at.span);
}
[[noreturn]] void rejectDeclaration(AdmissionStatus status,
                                    std::int64_t detail,
                                    const Token &at,
                                    const SourceSpan &span,
                                    const std::string &fieldType) {
    if (status == AdmissionStatus::allocation_failure)
        throw Error(DiagnosticCode::Internal, "hosted declaration admission allocation failed", span);
    if (status == AdmissionStatus::unsupported_field)
        throw Error(DiagnosticCode::UnsupportedFieldType,
                    "unsupported class field type '" + fieldType +
                        "': class fields require scalar, class, private fixed-array or private owned-byte storage",
                    span);
    std::string message;
    switch (status) {
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
        if (detail != maximumClassScalarArrayLength && detail != maximumClassByteArrayLength)
            invalid();
        message = "class array field capacity must be between 1 and " + std::to_string(detail);
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
} // namespace hosted_parser
} // namespace aurora
