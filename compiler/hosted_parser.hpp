#pragma once
#include "types.hpp"
#include "hosted_parser_abi.hpp"

namespace aurora::hosted_parser {
// Simultaneously live body, expression, type and namespace continuation frames.
inline constexpr std::uint64_t maximumLiveFrames = 256 + 1549 + 70 + 64;

// Copied admission input: host layout limits and the catalog's service set.
hosted_abi::compiler_parser::AdmissionConfig admissionConfiguration();
// The diagnostic of a rejected grammar status at its cursor token. `previous`
// spells the token before it, which a duplicate enum case names.
[[noreturn]] void rejectSyntax(Status status, Stop stop, const Token &at, const std::string &previous);
// The diagnostic of a rejected declaration over `span`, citing `at`;
// `fieldType` spells an unsupported field's type.
[[noreturn]] void rejectDeclaration(
    AdmissionStatus status, std::int64_t detail, const Token &at, const SourceSpan &span, const std::string &fieldType);
} // namespace aurora::hosted_parser
