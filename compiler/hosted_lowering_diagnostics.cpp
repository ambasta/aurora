#include "hosted_lowering_diagnostics.hpp"
#include <string_view>
#include <utility>

namespace aurora {
namespace {
namespace wire = hosted_abi::compiler_lowering;
using wire::LoweringError;
using wire::LoweringStatus;
using wire::OperandRole;

enum class Origin { sourceOrSynthetic, synthetic, none };

[[noreturn]] void invalidDiagnostic() {
    throw Error(DiagnosticCode::Internal, "invalid hosted lowering diagnostic");
}

class DiagnosticRenderer {
    const wire::LoweringResult &result;
    const HostedLoweringInput &input;
    const HostedLoweringDiagnosticServices &services;
    SourceSpan span;

    void check(LoweringStatus status, Origin origin, OperandRole first, OperandRole second) {
        if (result.result_status != status || input.operands[1].operandRole != first ||
            input.operands[2].operandRole != second)
            invalidDiagnostic();
        for (std::size_t index = 1; index != 3; ++index) {
            const auto &value = input.operands[index];
            if (value.operandRole != OperandRole::NoDiagnosticValue && value.signedValue < 0)
                invalidDiagnostic();
        }
        const auto &source = input.operands[0];
        if (origin == Origin::none) {
            if (source.operandRole != OperandRole::NoDiagnosticSource)
                invalidDiagnostic();
            return;
        }
        if (source.operandRole != OperandRole::DiagnosticSyntheticRef &&
            (origin != Origin::sourceOrSynthetic || source.operandRole != OperandRole::DiagnosticSourceRef))
            invalidDiagnostic();
        if (source.signedValue < 0 || !services.sourceReference)
            invalidDiagnostic();
        const auto token = services.sourceReference(source.signedValue);
        if (source.operandRole == OperandRole::DiagnosticSourceRef) {
            const auto &location = token.span;
            if (!location.source || location.begin.offset > location.end.offset ||
                location.end.offset > location.source->text.size() || location.begin.line < 1 ||
                location.begin.column < 1 || location.end.line < location.begin.line ||
                location.end.column < 1 ||
                (location.begin.line == location.end.line && location.end.column < location.begin.column))
                invalidDiagnostic();
            span = location;
        }
        // The synthetic role preserves Token(name, line)'s empty SourceSpan.
        // Never recover a source span from a same-spelled or backing token.
    }

public:
    DiagnosticRenderer(const wire::LoweringResult &value, const HostedLoweringInput &pools,
                       const HostedLoweringDiagnosticServices &renderers)
        : result(value), input(pools), services(renderers) {
        if ((result.result_status != LoweringStatus::semantic_failure &&
             result.result_status != LoweringStatus::invalid) ||
            result.root_row != -1 || input.moduleRoot != -1 || result.diagnostic_row != 0 ||
            input.diagnosticRow != 0 || input.rows.empty() || input.operands.size() < 3)
            invalidDiagnostic();
        const auto &row = input.rows[0];
        if (row.recordKind != wire::RecordKind::DiagnosticPayload || row.operandBegin != 0 || row.operandCount != 3)
            invalidDiagnostic();
    }

    Diagnostic finish(std::string message) const {
        // Layout guard errors used to receive this default code at the semantic
        // frontend stage too; their invalid status must not change that timing.
        return {DiagnosticCode::Semantic, std::move(message), span};
    }
    Diagnostic fixed(std::string_view message, Origin origin = Origin::sourceOrSynthetic) {
        check(LoweringStatus::semantic_failure, origin, OperandRole::NoDiagnosticValue,
              OperandRole::NoDiagnosticValue);
        return finish(std::string(message));
    }
    Diagnostic integrity(std::string_view message) {
        check(LoweringStatus::invalid, Origin::none, OperandRole::NoDiagnosticValue,
              OperandRole::NoDiagnosticValue);
        return finish(std::string(message));
    }
    void dynamic(Origin origin, OperandRole first, OperandRole second = OperandRole::NoDiagnosticValue) {
        check(LoweringStatus::semantic_failure, origin, first, second);
    }
    std::string name(std::size_t index) const {
        if (!services.name)
            invalidDiagnostic();
        return services.name(result.result_reason, input.operands[index + 1].signedValue);
    }
    std::string type(std::size_t index) const {
        if (!services.typeName)
            invalidDiagnostic();
        return services.typeName(input.operands[index + 1].signedValue);
    }
    std::string integer(std::size_t index) const {
        return std::to_string(input.operands[index + 1].signedValue);
    }
};
} // namespace

Diagnostic renderHostedLoweringDiagnostic(const wire::LoweringResult &result,
                                          const HostedLoweringInput &input,
                                          const HostedLoweringDiagnosticServices &services) {
    DiagnosticRenderer render(result, input, services);
    // Aurora has already selected each concrete alternative. This switch only
    // validates its bounded payload and preserves the existing diagnostic text.
    switch (result.result_reason) {
    case LoweringError::none:
        invalidDiagnostic();
    case LoweringError::unknown_class_type:
        render.dynamic(Origin::sourceOrSynthetic, OperandRole::DiagnosticTypeId);
        return render.finish("unknown class type '" + render.type(0) + "'");
    case LoweringError::owned_values_require_copied_element:
        return render.fixed("owned values require a bounded pointer-free copied class element");
    case LoweringError::class_array_requires_concrete_copied_elements:
        return render.fixed("class arrays require 1 to 64 concrete copied class elements");
    case LoweringError::class_array_containment_depth:
        return render.fixed("class array containment depth exceeds four");
    case LoweringError::class_array_copied_leaf_limit:
        return render.fixed("class array exceeds copied class leaf limits");
    case LoweringError::class_array_storage_limit:
        return render.fixed("class array storage exceeds 520 bytes");
    case LoweringError::unknown_enum_type:
        render.dynamic(Origin::sourceOrSynthetic, OperandRole::DiagnosticTypeId);
        return render.finish("unknown enum type '" + render.type(0) + "'");
    case LoweringError::unknown_nested_class_type:
        render.dynamic(Origin::none, OperandRole::DiagnosticNameId);
        return render.finish("unknown nested class type '" + render.name(0) + "'");
    case LoweringError::recursive_class_containment:
        return render.fixed("recursive class containment is unsupported");
    case LoweringError::class_containment_depth:
        return render.fixed("class containment depth exceeds four");
    case LoweringError::duplicate_class_field:
        return render.fixed("duplicate class field");
    case LoweringError::nested_owning_class_field:
        return render.fixed("nested owning class fields are unsupported");
    case LoweringError::owned_byte_field_must_be_private:
        return render.fixed("owned byte fields must be private");
    case LoweringError::owning_class_template:
        return render.fixed("owning class templates are unsupported");
    case LoweringError::class_array_field_storage:
        return render.fixed("class array fields require private concrete scalar or copied class storage of length 1 to 64, or 1 to 512 for u8");
    case LoweringError::owning_class_array:
        return render.fixed("arrays of owning classes are unsupported");
    case LoweringError::class_field_requires_concrete_type:
        return render.fixed("class field must be concrete scalar, enum, class or private array");
    case LoweringError::class_layout_frame_limit:
        return render.fixed("class layout exceeds 65536 bytes");
    case LoweringError::composed_class_leaf_limit:
        return render.fixed("composed classes are limited to 64 non-byte scalar leaves, 512 u8 leaves and 513 total leaves");
    case LoweringError::composed_class_depth:
        return render.fixed("composed class exceeds depth four");
    case LoweringError::aggregate_field_requires_constructor:
        return render.fixed("array or class fields require a declared complete constructor");
    case LoweringError::private_class_field:
        return render.fixed("private class field is inaccessible");
    case LoweringError::unknown_class_field:
        render.dynamic(Origin::sourceOrSynthetic, OperandRole::DiagnosticNameId, OperandRole::DiagnosticTypeId);
        return render.finish("unknown field '" + render.name(0) + "' in " + render.type(1));
    case LoweringError::owning_class_copy:
        return render.fixed("owning class cannot be copied; use move(named_local)");
    case LoweringError::reflection_span_capability:
        return render.fixed("span capabilities are unavailable to reflection");
    case LoweringError::reflection_resource_capability:
        return render.fixed("resource capabilities are unavailable to reflection");
    case LoweringError::unknown_local:
        render.dynamic(Origin::sourceOrSynthetic, OperandRole::DiagnosticNameId);
        return render.finish("unknown local '" + render.name(0) + "'");
    case LoweringError::initializer_receiver_field_access:
        return render.fixed("constructor initializer cannot access receiver fields");
    case LoweringError::ownership_operation_requires_local:
        return render.fixed("ownership operation requires a local name");
    case LoweringError::use_after_move:
        render.dynamic(Origin::sourceOrSynthetic, OperandRole::DiagnosticNameId);
        return render.finish("use after move of '" + render.name(0) + "'");
    case LoweringError::owning_object_exclusively_borrowed:
        return render.fixed("owning object is exclusively borrowed for a call");
    case LoweringError::call_argument_count:
        render.dynamic(Origin::sourceOrSynthetic, OperandRole::DiagnosticNameId);
        return render.finish("wrong argument count for " + render.name(0));
    case LoweringError::type_mismatch:
        render.dynamic(Origin::sourceOrSynthetic, OperandRole::DiagnosticTypeId, OperandRole::DiagnosticTypeId);
        return render.finish("expected " + render.type(0) + ", got " + render.type(1));
    case LoweringError::duplicate_local:
        render.dynamic(Origin::sourceOrSynthetic, OperandRole::DiagnosticNameId);
        return render.finish("duplicate local '" + render.name(0) + "'");
    case LoweringError::function_frame_limit:
        return render.fixed("function local stack frame exceeds 65536 bytes");
    case LoweringError::owning_object_mutation_while_borrowed:
        return render.fixed("cannot mutate or move an owning object while borrowed");
    case LoweringError::owner_mutation_while_span_live:
        return render.fixed("cannot mutate or move an owner while a readonly span is live");
    case LoweringError::invalid_byte_string_literal:
        return render.fixed("invalid byte-string literal");
    case LoweringError::subspan_argument_count:
        return render.fixed("span subspan expects offset and count");
    case LoweringError::subspan_requires_live_readonly_view:
        return render.fixed("subspan requires a named live readonly span or a directly derived temporary view");
    case LoweringError::temporary_subspan_requires_owned_origin:
        return render.fixed("temporary subspan chains require an owned-byte origin; array and parameter views require a named parent span");
    case LoweringError::borrowed_object_field_access:
        return render.fixed("borrowed object parameters support public methods, not field access");
    case LoweringError::borrow_bytes_requires_named_storage_or_private_field:
        return render.fixed("borrow_bytes requires a named local byte array, a named owned-byte value or a direct private owned-byte field");
    case LoweringError::borrow_bytes_field_storage:
        return render.fixed("borrow_bytes fields require private owned bytes or an implicit receiver u8 array");
    case LoweringError::borrow_bytes_requires_named_storage:
        return render.fixed("borrow_bytes requires a named local byte array or owned bytes");
    case LoweringError::invalid_span_initializer:
        return render.fixed("span initializer requires borrow_bytes, a live span or its subspan");
    case LoweringError::dependent_reborrow_lifetime:
        return render.fixed("span lifetime ended before a dependent reborrow", Origin::none);
    case LoweringError::owning_transfer_requires_move:
        return render.fixed("owning transfer requires move(named_local)");
    case LoweringError::move_requires_owner:
        return render.fixed("move requires an owning value");
    case LoweringError::borrowed_object_ownership_transfer:
        return render.fixed("borrowed object parameters cannot transfer ownership");
    case LoweringError::move_const_owner:
        return render.fixed("cannot move a const owner");
    case LoweringError::resource_result_requires_typed_initializer:
        return render.fixed("resource result requires a typed local initializer");
    case LoweringError::owner_region_mismatch:
        return render.fixed("owning value belongs to a different region");
    case LoweringError::owned_bytes_initializer:
        return render.fixed("owned bytes require region.try_allocate, move or an owned-result function call");
    case LoweringError::indexing_requires_local_or_private_receiver_field:
        return render.fixed("indexing requires an array local or implicit private receiver field");
    case LoweringError::indexing_requires_local_or_receiver_field:
        return render.fixed("indexing requires an array local or receiver field");
    case LoweringError::private_constructor:
        return render.fixed("private constructor is inaccessible");
    case LoweringError::private_method:
        return render.fixed("private method is inaccessible");
    case LoweringError::missing_declared_constructor:
        return render.fixed("class has no declared constructor");
    case LoweringError::unknown_class_method:
        return render.fixed("unknown class method");
    case LoweringError::method_signature_import:
        return render.fixed("method signature type requires a direct visible import");
    case LoweringError::local_shadows_method:
        return render.fixed("local binding shadows method and is not callable");
    case LoweringError::borrowed_object_field_projection:
        return render.fixed("borrowed object parameters support public methods, not field projections");
    case LoweringError::method_receiver_requires_class_storage:
        return render.fixed("method receiver requires a class local or direct owned class field");
    case LoweringError::nested_method_receiver_requires_owned_field:
        return render.fixed("nested method receiver requires an owned class field or owned byte field");
    case LoweringError::direct_copied_return_requires_complete_method_receiver:
        return render.fixed("direct copied return requires an ordinary method on a complete receiver");
    case LoweringError::arguments_consumed_method_receiver:
        return render.fixed("method arguments consumed the receiver or its containing object");
    case LoweringError::service_operation_requires_active_exclusive_parameter:
        return render.fixed("service operation requires an active named exclusive service parameter");
    case LoweringError::next_requires_console_sample_initializer:
        return render.fixed("next requires a typed ConsoleSample initializer");
    case LoweringError::poll_requires_event_sample_initializer:
        return render.fixed("poll requires a typed IommuEventSample initializer");
    case LoweringError::acknowledge_returns_scalar_enum:
        return render.fixed("acknowledge returns a scalar enum, not a copied report");
    case LoweringError::put_returns_scalar_enum:
        return render.fixed("put returns a scalar enum, not a copied report");
    case LoweringError::pixel_returns_scalar_enum:
        return render.fixed("pixel returns a scalar enum, not a copied report");
    case LoweringError::unknown_service_operation:
        return render.fixed("unknown operation for sealed service kind");
    case LoweringError::typed_owner_operation_requires_named_owner:
        return render.fixed("typed owner operation requires a named owner");
    case LoweringError::typed_owner_query_returns_scalar:
        return render.fixed("owner status and size return scalar values");
    case LoweringError::unknown_typed_owner_operation:
        return render.fixed("unknown typed owner operation");
    case LoweringError::write_const_typed_owner:
        return render.fixed("cannot write a const typed owner");
    case LoweringError::typed_owner_access_requires_copied_destination:
        return render.fixed("typed owner access requires a typed copied local or direct copied return");
    case LoweringError::typed_owner_mutation_returns_bool:
        return render.fixed("typed owner mutation returns bool");
    case LoweringError::byte_operation_requires_named_owner:
        return render.fixed("byte operation requires a named owner");
    case LoweringError::write_const_byte_owner:
        return render.fixed("cannot write a const byte owner");
    case LoweringError::unknown_owned_byte_operation:
        return render.fixed("unknown owned byte operation");
    case LoweringError::region_allocation_requires_owned_bytes_initializer:
        return render.fixed("region allocation requires an OwnedBytes local initializer");
    case LoweringError::span_operation_requires_named_live_span:
        return render.fixed("span operation requires a named live span");
    case LoweringError::span_size_argument_count:
        return render.fixed("span size expects no arguments");
    case LoweringError::span_at_argument_count:
        return render.fixed("span at expects one index");
    case LoweringError::subspan_requires_span_binding_or_argument:
        return render.fixed("subspan requires a span binding or span argument");
    case LoweringError::unknown_readonly_span_operation:
        return render.fixed("span supports only readonly size, at and subspan operations");
    case LoweringError::copied_argument_consumes_owning_result:
        return render.fixed("copied argument cannot consume an owning result");
    case LoweringError::copied_argument_requires_complete_method_receiver:
        return render.fixed("copied argument requires an ordinary method on a complete receiver");
    case LoweringError::class_method_result_requires_typed_initializer:
        return render.fixed("class-returning method requires a typed local initializer");
    case LoweringError::span_method_result_requires_initializer_or_argument:
        return render.fixed("span-returning method requires a typed local initializer or span argument");
    case LoweringError::span_method_forwards_returned_view:
        return render.fixed("span-result methods cannot forward another method's returned view");
    case LoweringError::returned_span_requires_named_receiver:
        return render.fixed("returned span requires a named receiver or the implicit receiver");
    case LoweringError::span_method_requires_verified_field_summary:
        return render.fixed("span-result method requires a verified receiver-field summary");
    case LoweringError::mutable_method_requires_mutable_receiver:
        return render.fixed("mutable method requires a mutable receiver");
    case LoweringError::method_argument_count:
        return render.fixed("wrong argument count for method");
    case LoweringError::service_report_requires_typed_initializer:
        return render.fixed("copied service report requires a typed local initializer");
    case LoweringError::service_forwarding_requires_named_exclusive_parameter:
        return render.fixed("service forwarding requires a named exclusive service parameter");
    case LoweringError::service_authority_suspended:
        return render.fixed("service authority is suspended during synchronous forwarding");
    case LoweringError::copied_argument_requires_ordinary_call:
        return render.fixed("copied argument requires an ordinary function call");
    case LoweringError::direct_copied_return_requires_ordinary_call:
        return render.fixed("direct copied return requires an ordinary function call");
    case LoweringError::class_call_result_requires_typed_initializer:
        return render.fixed("class-returning call requires a typed local initializer");
    case LoweringError::borrowed_argument_requires_complete_owner:
        return render.fixed("borrowed object argument requires a complete named owning object");
    case LoweringError::mutable_borrowed_argument_requires_mutable_owner:
        return render.fixed("mutable borrowed parameter requires a mutable owning object");
    case LoweringError::unknown_overload_candidate:
        return render.fixed("unknown ordinary overload candidate");
    case LoweringError::ambiguous_exact_overload:
        return render.fixed("ambiguous exact ordinary overload");
    case LoweringError::no_exact_overload:
        render.dynamic(Origin::sourceOrSynthetic, OperandRole::DiagnosticNameId);
        return render.finish("no exact ordinary overload for " + render.name(0));
    case LoweringError::function_signature_import:
        return render.fixed("function signature type requires a direct visible import");
    case LoweringError::invalid_byte_literal:
        return render.fixed("invalid byte literal");
    case LoweringError::invalid_integer_literal_or_suffix:
        return render.fixed("integer literal out of range or invalid suffix");
    case LoweringError::unknown_enum_case:
        return render.fixed("unknown enum case");
    case LoweringError::class_array_copy_requires_typed_initializer:
        return render.fixed("class array element copy requires a typed local initializer");
    case LoweringError::array_literal_requires_typed_initializer:
        return render.fixed("array literals require a typed local initializer");
    case LoweringError::byte_string_requires_typed_array_initializer:
        return render.fixed("byte-string literals require a typed local u8 array initializer");
    case LoweringError::field_access_requires_class_local:
        return render.fixed("field access currently requires a class local");
    case LoweringError::aggregate_field_requires_projection_or_indexing:
        return render.fixed("aggregate fields require a fresh typed class projection or checked indexing");
    case LoweringError::class_construction_requires_typed_initializer:
        return render.fixed("class construction requires a typed local initializer");
    case LoweringError::array_value_requires_initializer_or_indexing:
        return render.fixed("array values are only supported in local initializers and indexing");
    case LoweringError::class_value_requires_initializer_or_field_access:
        return render.fixed("class values are only supported in local initializers and field accesses");
    case LoweringError::service_capability_not_value:
        return render.fixed("service capability is not a value");
    case LoweringError::implicit_owned_value_copy:
        return render.fixed("owned values cannot be implicitly copied; use move, read, or borrow");
    case LoweringError::span_capability_not_scalar:
        return render.fixed("span capability cannot be used as a scalar value");
    case LoweringError::integer_literal_range:
        return render.fixed("integer literal out of range");
    case LoweringError::bitwise_operand_type:
        return render.fixed("expected u64 or u8 bitwise operand");
    case LoweringError::logical_borrow_state_mismatch:
        return render.fixed("logical paths must preserve the same borrow state");
    case LoweringError::logical_byte_ownership_state_mismatch:
        return render.fixed("logical paths must preserve exact byte ownership state");
    case LoweringError::shift_operand_type:
        return render.fixed("expected u64 or u8 shift operand");
    case LoweringError::bitwise_operands_type:
        return render.fixed("expected u64 or u8 bitwise operands");
    case LoweringError::arithmetic_operands_type:
        return render.fixed("expected i64, u64 or u8 arithmetic operands");
    case LoweringError::ordered_comparison_operands_type:
        return render.fixed("expected i64, u64 or u8 ordered comparison operands");
    case LoweringError::invalid_expression:
        return render.fixed("invalid expression");
    case LoweringError::borrow_bytes_requires_span_binding_or_argument:
        return render.fixed("borrow_bytes requires a span binding or span argument");
    case LoweringError::integer_conversion_types:
        return render.fixed("expected distinct i64, u64 or u8 conversion types");
    case LoweringError::len_requires_local_or_receiver_array:
        return render.fixed("len requires an array local or receiver field");
    case LoweringError::read_requires_ownership_reference:
        return render.fixed("read requires own, ref, or mutref");
    case LoweringError::owner_exclusively_borrowed:
        return render.fixed("owner is exclusively borrowed");
    case LoweringError::write_requires_mutable_reference:
        return render.fixed("write requires a non-const mutable reference binding");
    case LoweringError::ownership_constructor_requires_typed_initializer:
        return render.fixed("ownership constructors are only supported in typed local initializers");
    case LoweringError::unknown_function:
        render.dynamic(Origin::sourceOrSynthetic, OperandRole::DiagnosticNameId);
        return render.finish("unknown function '" + render.name(0) + "'");
    case LoweringError::unsupported_static_assert_expression:
        return render.fixed("static_assert supports literals, reflection, comparisons, !, && and || only");
    case LoweringError::unreachable_statement:
        return render.fixed("unreachable statement");
    case LoweringError::byte_array_lifetime_while_borrowed:
        return render.fixed("byte array lifetime ends while borrowed", Origin::synthetic);
    case LoweringError::owning_class_field_reassignment:
        return render.fixed("owning class field reassignment is unsupported");
    case LoweringError::class_field_assignment_requires_complete_local:
        return render.fixed("class field assignment requires a complete local name");
    case LoweringError::direct_copied_return_requires_class_result:
        return render.fixed("direct copied return requires a class-returning function");
    case LoweringError::class_argument_requires_copied_constructor:
        return render.fixed("class argument requires a copied constructor");
    case LoweringError::class_argument_requires_complete_local:
        return render.fixed("class argument requires a complete local name");
    case LoweringError::class_projection_requires_copied_array:
        return render.fixed("class projection requires a copied class array");
    case LoweringError::class_projection_requires_named_receiver:
        return render.fixed("class projection requires a named local receiver");
    case LoweringError::class_projection_requires_class_field:
        return render.fixed("class projection requires a class field");
    case LoweringError::owning_field_extraction:
        return render.fixed("owning field extraction is unsupported");
    case LoweringError::class_initializer_requires_class_result:
        return render.fixed("class initializer requires a class-returning function");
    case LoweringError::constructor_class_designated_initialization:
        return render.fixed("constructor-bearing class rejects designated initialization");
    case LoweringError::private_class_construction_requires_constructor:
        return render.fixed("class construction requires public fields; private construction requires a declared constructor");
    case LoweringError::class_initializer_requires_fields_or_copy:
        return render.fixed("class local requires named-field construction or same-type class copy");
    case LoweringError::duplicate_field_initializer:
        return render.fixed("duplicate field initializer", Origin::synthetic);
    case LoweringError::incomplete_class_field_initialization:
        return render.fixed("every class field must be initialized exactly once");
    case LoweringError::class_array_initializer_count:
        return render.fixed("class array initialization requires exactly one complete named value per element");
    case LoweringError::class_array_initializer_requires_complete_locals:
        return render.fixed("class array initializer elements require complete local names");
    case LoweringError::byte_string_requires_byte_elements:
        return render.fixed("byte-string initializers require u8 array elements");
    case LoweringError::byte_array_initializer_length:
        render.dynamic(Origin::sourceOrSynthetic, OperandRole::DiagnosticInteger, OperandRole::DiagnosticInteger);
        return render.finish("array initializer length does not match its declared type: expected " + render.integer(0) + " bytes, got " + render.integer(1) + " decoded bytes");
    case LoweringError::array_initializer_requires_literal_or_copy:
        return render.fixed("array local requires an array literal or same-type array copy");
    case LoweringError::array_initializer_length:
        return render.fixed("array initializer length does not match its declared type");
    case LoweringError::returned_span_requires_private_receiver_storage:
        return render.fixed("returned span must derive directly from one private receiver byte-storage field");
    case LoweringError::returned_span_field_mismatch:
        return render.fixed("all returned spans must derive from the same receiver byte-storage field");
    case LoweringError::class_return_requires_local_constructor_or_call:
        return render.fixed("class return requires a complete local name, direct copied-class constructor or ordinary call");
    case LoweringError::static_assertion_failed:
        return render.fixed("static assertion failed");
    case LoweringError::local_service_capability:
        return render.fixed("service capability cannot be stored in a local");
    case LoweringError::region_parameter_position:
        return render.fixed("region authority is available only as the first function parameter");
    case LoweringError::span_binding_requires_const:
        return render.fixed("span bindings must be const and cannot be rebound");
    case LoweringError::ownership_binding_requires_constructor:
        return render.fixed("ownership binding requires explicit constructor");
    case LoweringError::move_const_owner_to_mutable_binding:
        return render.fixed("cannot move a const owner into a mutable binding");
    case LoweringError::move_borrowed_owner:
        return render.fixed("cannot move a borrowed owner");
    case LoweringError::mutable_borrow_of_const_owner:
        return render.fixed("cannot mutably borrow a const owner");
    case LoweringError::conflicting_borrow:
        return render.fixed("conflicting borrow");
    case LoweringError::ownership_constructor_type:
        return render.fixed("constructor does not match ownership type");
    case LoweringError::const_method_writes_receiver_array:
        return render.fixed("const method cannot write receiver arrays");
    case LoweringError::index_assignment_requires_mutable_array:
        return render.fixed("index assignment requires a mutable array local");
    case LoweringError::byte_array_mutation_while_span_live:
        return render.fixed("cannot mutate a byte array while a span is live");
    case LoweringError::class_array_replacement_requires_complete_local:
        return render.fixed("class array replacement requires a complete local name");
    case LoweringError::loop_condition_transfers_outer_owner:
        return render.fixed("loop conditions cannot transfer an outer byte owner");
    case LoweringError::loop_backedge_moves_outer_owner:
        return render.fixed("loop backedge cannot move an outer owner; moves require a returning path");
    case LoweringError::loop_backedge_borrow_state_mismatch:
        return render.fixed("loop backedge must preserve outer borrow state");
    case LoweringError::borrowed_object_field_assignment:
        return render.fixed("borrowed object parameters support public methods, not field assignment");
    case LoweringError::field_assignment_requires_mutable_class:
        return render.fixed("field assignment requires a mutable class local");
    case LoweringError::aggregate_or_resource_field_assignment:
        return render.fixed("whole aggregate or resource field assignment is unsupported");
    case LoweringError::field_assignment_consumed_object:
        return render.fixed("field assignment value consumed the containing object");
    case LoweringError::const_method_writes_receiver_field:
        return render.fixed("const method cannot write receiver fields", Origin::synthetic);
    case LoweringError::assignment_requires_mutable_scalar:
        return render.fixed("assignment requires a mutable scalar local");
    case LoweringError::branch_borrow_state_mismatch:
        return render.fixed("continuing branches must preserve the same borrow state");
    case LoweringError::branch_byte_ownership_state_mismatch:
        return render.fixed("continuing branches must preserve exact byte ownership state");
    case LoweringError::nominal_type_id_limit:
        return render.fixed("too many class types for bootstrap type IDs", Origin::none);
    case LoweringError::enum_declaration_limit:
        return render.fixed("module graph exceeds 64 enum declarations", Origin::none);
    case LoweringError::enum_name_or_case_count:
        return render.fixed("enum requires a unique name and 1 to 256 cases");
    case LoweringError::duplicate_enum_case:
        return render.fixed("duplicate enum case");
    case LoweringError::duplicate_or_reserved_class_name:
        return render.fixed("duplicate or reserved class name");
    case LoweringError::owning_class_template_argument:
        return render.fixed("owning classes cannot be template arguments");
    case LoweringError::composed_or_owning_class_storage_limit:
        return render.fixed("composed or owning class storage exceeds 520 bytes");
    case LoweringError::duplicate_or_reserved_function_name:
        return render.fixed("duplicate or reserved function name");
    case LoweringError::function_parameter_limit:
        return render.fixed("at most six parameters supported");
    case LoweringError::service_capability_result:
        return render.fixed("service capabilities cannot be returned");
    case LoweringError::service_function_leading_parameter_or_result:
        return render.fixed("service functions require one leading exclusive sealed service reference and copied result");
    case LoweringError::service_group_requires_distinct_leading_references:
        return render.fixed("service group requires distinct leading exclusive sealed references");
    case LoweringError::service_function_group_or_result:
        return render.fixed("service functions require a leading exclusive sealed service group and copied result");
    case LoweringError::service_helper_parameter_type:
        return render.fixed("service helper parameters require scalars, enums or readonly byte spans");
    case LoweringError::service_capability_parameter_position:
        return render.fixed("service capability must be the leading exclusive parameter");
    case LoweringError::borrowed_function_boundary:
        return render.fixed("borrowed functions require one leading concrete owning-class reference and a scalar or copied result");
    case LoweringError::borrowed_class_template_parameter:
        return render.fixed("borrowed parameters cannot name a class template");
    case LoweringError::borrowed_function_later_parameter_type:
        return render.fixed("later borrowed-function parameters require scalar, copied class or readonly span values");
    case LoweringError::const_permission_requires_borrowed_parameter:
        return render.fixed("const borrowed permission requires a borrowed parameter");
    case LoweringError::resource_function_region_or_result:
        return render.fixed("resource functions and owning constructors require one first region parameter and scalar, copied class or owning result");
    case LoweringError::resource_argument_type:
        return render.fixed("resource arguments require scalar values or moved owners");
    case LoweringError::owning_constructor_result:
        return render.fixed("owning constructor requires its internal scalar result");
    case LoweringError::span_result_method_boundary:
        return render.fixed("span results require a const non-template class method");
    case LoweringError::method_result_type:
        return render.fixed("methods require scalar, enum or copyable class results");
    case LoweringError::method_parameter_type:
        return render.fixed("methods require scalar, enum or copyable class parameters");
    case LoweringError::function_class_leaf_limit:
        return render.fixed("function-boundary classes are limited to 64 scalar fields excluding u8, 512 u8 leaves and 513 total leaves");
    case LoweringError::function_class_storage_limit:
        return render.fixed("function-boundary class storage exceeds 520 bytes");
    case LoweringError::unknown_constructor_field_initializer:
        return render.fixed("unknown constructor field initializer");
    case LoweringError::duplicate_constructor_field_initializer:
        return render.fixed("duplicate constructor field initializer");
    case LoweringError::incomplete_constructor_field_initialization:
        return render.fixed("constructor must initialize every field exactly once");
    case LoweringError::constructor_byte_field_region_mismatch:
        return render.fixed("constructor byte field belongs to a different region");
    case LoweringError::class_field_initializer_requires_complete_local:
        return render.fixed("class field initializer requires a complete named class value");
    case LoweringError::array_field_requires_empty_initialization:
        return render.fixed("array fields require explicit empty-brace zero initialization");
    case LoweringError::empty_initialization_requires_array_field:
        return render.fixed("empty-brace constructor initialization is restricted to array fields");
    case LoweringError::missing_return_path:
        return render.fixed("function must return on every path");
    case LoweringError::span_method_missing_field_return:
        return render.fixed("span-result method has no verified receiver-field return");
    case LoweringError::unknown_reflection_nominal:
        return render.fixed("unknown nominal type in reflection view", Origin::none);
    case LoweringError::ir_storage_extent_limit:
        return render.integrity("IR: storage extent exceeds 65536 bytes");
    case LoweringError::ir_class_storage_depth:
        return render.integrity("IR: cyclic or excessive class storage depth");
    case LoweringError::ir_missing_class_storage_shape:
        return render.integrity("IR: missing logical class storage shape");
    case LoweringError::ir_class_storage_alignment:
        return render.integrity("IR: invalid class storage alignment");
    case LoweringError::ir_logical_field_storage_range:
        return render.integrity("IR: invalid logical field range for storage");
    case LoweringError::ir_owned_byte_field_descriptor:
        return render.integrity("IR: owned byte field requires one non-scalar descriptor");
    case LoweringError::ir_nested_owning_class_field:
        return render.integrity("IR: nested owning class fields are unsupported");
    case LoweringError::ir_nested_field_storage_shape:
        return render.integrity("IR: invalid nested field storage shape");
    case LoweringError::ir_scalar_field_storage_shape:
        return render.integrity("IR: invalid scalar field storage shape");
    case LoweringError::ir_class_storage_limit:
        return render.integrity("IR: class storage exceeds 65536 bytes");
    case LoweringError::ir_class_storage_leaf_coverage:
        return render.integrity("IR: class storage does not cover logical leaves");
    }
    invalidDiagnostic();
}
} // namespace aurora
