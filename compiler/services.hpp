#pragma once
#include "types.hpp"
#include <array>
#include <string_view>

namespace aurora::service {
// This closed compiler table is the only source of service identities and
// operation linkage. There is no source extern declaration or import string.
enum class Kind {
    Console,
    Display
};
enum class Operation {
    Next,
    Put,
    Pixel
};
inline Kind kind(const Type &type) {
    if (type == Type::ConsoleSession)
        return Kind::Console;
    if (type == Type::DisplaySession)
        return Kind::Display;
    throw Error("not a sealed service capability type");
}
inline constexpr int capabilityBytes = 16; // opaque host grant plus invocation generation
inline constexpr std::string_view sampleName = "__au_console_sample";
inline constexpr std::string_view putResultName = "__au_console_put_result";
inline constexpr std::string_view completionName = "__au_console_completion";
inline constexpr std::string_view displayPutResultName = "__au_display_put_result";
inline constexpr std::string_view displayCompletionName = "__au_display_completion";
class OperationDescription {
public:
    Kind kind;
    Operation operation;
    std::string_view spelling;
    std::string_view hostSymbol;
};
inline constexpr std::array operations{
    OperationDescription{Kind::Console, Operation::Next, "next", "__au_runtime_console_next"},
    OperationDescription{Kind::Console, Operation::Put, "put", "__au_runtime_console_put"},
    OperationDescription{Kind::Display, Operation::Pixel, "pixel", "__au_runtime_display_pixel"}};
inline const OperationDescription &description(Operation operation) {
    for (const auto &entry : operations)
        if (entry.operation == operation)
            return entry;
    throw Error("unknown sealed service operation");
}
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
inline Type displayPutResultType() {
    Type result = Type::enumeration(std::string(displayPutResultName));
    result.displayName = "builtin::DisplayPutResult";
    return result;
}
inline Type displayCompletionType() {
    Type result = Type::enumeration(std::string(displayCompletionName));
    result.displayName = "builtin::DisplayCompletion";
    return result;
}
inline bool copiedType(const Type &type) {
    return type == sampleType() || type == putResultType() || type == completionType() ||
           type == displayPutResultType() || type == displayCompletionType();
}
} // namespace aurora::service
