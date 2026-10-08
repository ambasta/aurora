#pragma once
#include "types.hpp"
#include <array>
#include <string_view>

namespace aurora::service {
// This closed compiler table is the only source of service identities and
// operation linkage. There is no source extern declaration or import string.
enum class Kind {
    Console
};
enum class Operation {
    Next,
    Put
};
inline constexpr int capabilityBytes = 16; // opaque host grant plus invocation generation
inline constexpr std::string_view sampleName = "__au_console_sample";
inline constexpr std::string_view putResultName = "__au_console_put_result";
inline constexpr std::string_view completionName = "__au_console_completion";
class OperationDescription {
public:
    Kind kind;
    Operation operation;
    std::string_view spelling;
    std::string_view hostSymbol;
};
inline constexpr std::array operations{
    OperationDescription{Kind::Console, Operation::Next, "next", "__au_runtime_console_next"},
    OperationDescription{Kind::Console, Operation::Put, "put", "__au_runtime_console_put"}};
inline Type sampleType() {
    Type result{std::string(sampleName)};
    result.displayName = "builtin::ConsoleSample";
    return result;
}
inline Type putResultType() {
    Type result = Type::enumeration(std::string(putResultName));
    result.displayName = "builtin::ConsolePutResult";
    return result;
}
inline Type completionType() {
    Type result = Type::enumeration(std::string(completionName));
    result.displayName = "builtin::ConsoleCompletion";
    return result;
}
inline bool copiedType(const Type &type) {
    return type == sampleType() || type == putResultType() || type == completionType();
}
} // namespace aurora::service
