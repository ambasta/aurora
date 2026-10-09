#pragma once
#include "types.hpp"
#include <array>
#include <string_view>
#include <set>

namespace aurora::service {
// This closed compiler table is the only source of service identities and
// operation linkage. There is no source extern declaration or import string.
enum class Kind {
    Console,
    Display,
    IommuEvent
};
enum class Operation {
    Next,
    Put,
    Pixel,
    IommuPoll,
    IommuAcknowledge
};
inline Kind kind(const Type &type) {
    if (type == Type::ConsoleSession)
        return Kind::Console;
    if (type == Type::DisplaySession)
        return Kind::Display;
    if (type == Type::IommuEventSession)
        return Kind::IommuEvent;
    throw Error("not a sealed service capability type");
}
inline bool supportedGroup(const std::set<Kind> &kinds) {
    return kinds == std::set<Kind>{Kind::Console} || kinds == std::set<Kind>{Kind::Display} ||
           kinds == std::set<Kind>{Kind::IommuEvent} || kinds == std::set<Kind>{Kind::Console, Kind::Display} ||
           kinds == std::set<Kind>{Kind::Console, Kind::IommuEvent};
}
inline constexpr int capabilityBytes = 16; // opaque host grant plus invocation generation
inline constexpr std::string_view sampleName = "__au_console_sample";
inline constexpr std::string_view putResultName = "__au_console_put_result";
inline constexpr std::string_view completionName = "__au_console_completion";
inline constexpr std::string_view displayPutResultName = "__au_display_put_result";
inline constexpr std::string_view displayCompletionName = "__au_display_completion";
inline constexpr std::string_view eventSampleName = "__au_iommu_event_sample";
inline constexpr std::string_view eventPollResultName = "__au_event_poll_result";
inline constexpr std::string_view eventAckResultName = "__au_event_ack_result";
inline constexpr std::string_view eventIntakeCompletionName = "__au_event_intake_completion";
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
    OperationDescription{Kind::Display, Operation::Pixel, "pixel", "__au_runtime_display_pixel"},
    OperationDescription{Kind::IommuEvent, Operation::IommuPoll, "poll", "__au_runtime_iommu_event_poll"},
    OperationDescription{
        Kind::IommuEvent, Operation::IommuAcknowledge, "acknowledge", "__au_runtime_iommu_event_acknowledge"}};
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
inline Type eventSampleType() {
    Type result{std::string(eventSampleName)};
    result.displayName = "builtin::IommuEventSample";
    return result;
}
inline Type eventPollResultType() {
    Type result = Type::enumeration(std::string(eventPollResultName));
    result.displayName = "builtin::EventPollResult";
    return result;
}
inline Type eventAckResultType() {
    Type result = Type::enumeration(std::string(eventAckResultName));
    result.displayName = "builtin::EventAckResult";
    return result;
}
inline Type eventIntakeCompletionType() {
    Type result = Type::enumeration(std::string(eventIntakeCompletionName));
    result.displayName = "builtin::EventIntakeCompletion";
    return result;
}
inline bool copiedType(const Type &type) {
    return type == sampleType() || type == putResultType() || type == completionType() ||
           type == displayPutResultType() || type == displayCompletionType() || type == eventSampleType() ||
           type == eventPollResultType() || type == eventAckResultType() || type == eventIntakeCompletionType();
}
} // namespace aurora::service
