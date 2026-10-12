#pragma once
#include "syntax.hpp"
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
// Canonical copied service data used by the resolver descriptor seed and by
// existing semantic/lowering helpers. No source declaration grants a capability.
inline std::array<Type, 9> copiedTypes() {
    return {sampleType(), putResultType(), completionType(), displayPutResultType(),
            displayCompletionType(), eventSampleType(), eventPollResultType(), eventAckResultType(),
            eventIntakeCompletionType()};
}
inline Program copiedDefinitions() {
    Program result;
    ClassDefinition sample(Token(std::string(service::sampleName), 0));
    for (const auto &[name, type] : std::vector<std::pair<std::string, Type>>{
             {"byte_present", Type::Bool}, {"byte", Type::U8}, {"damaged", Type::Bool}}) {
        Field field(Token(name, 0), type);
        field.publicAccess = true;
        sample.fields.push_back(std::move(field));
    }
    result.classes.push_back(std::move(sample));
    EnumDefinition put(Token(std::string(service::putResultName), 0));
    put.cases = {Token("success", 0), Token("timeout", 0)};
    result.enums.push_back(std::move(put));
    EnumDefinition completion(Token(std::string(service::completionName), 0));
    completion.cases = {Token("requested_exit", 0), Token("output_failure", 0)};
    result.enums.push_back(std::move(completion));
    EnumDefinition displayPut(Token(std::string(service::displayPutResultName), 0));
    displayPut.cases = {Token("success", 0), Token("out_of_bounds", 0)};
    result.enums.push_back(std::move(displayPut));
    EnumDefinition displayCompletion(Token(std::string(service::displayCompletionName), 0));
    displayCompletion.cases = {Token("rendered", 0), Token("output_failure", 0)};
    result.enums.push_back(std::move(displayCompletion));
    ClassDefinition eventSample(Token(std::string(service::eventSampleName), 0));
    for (const auto &[name, type] :
         std::vector<std::pair<std::string, Type>>{{"result", service::eventPollResultType()},
                                                   {"word0", Type::U64},
                                                   {"word1", Type::U64},
                                                   {"status_low", Type::U64}}) {
        Field field(Token(name, 0), type);
        field.publicAccess = true;
        eventSample.fields.push_back(std::move(field));
    }
    result.classes.push_back(std::move(eventSample));
    EnumDefinition eventPoll(Token(std::string(service::eventPollResultName), 0));
    eventPoll.cases = {
        Token("empty", 0), Token("record", 0), Token("overflow", 0), Token("transport_failure", 0)};
    result.enums.push_back(std::move(eventPoll));
    EnumDefinition eventAck(Token(std::string(service::eventAckResultName), 0));
    eventAck.cases = {Token("committed", 0), Token("overflow", 0), Token("transport_failure", 0)};
    result.enums.push_back(std::move(eventAck));
    EnumDefinition eventCompletion(Token(std::string(service::eventIntakeCompletionName), 0));
    eventCompletion.cases = {Token("drained", 0),
                             Token("budget_exhausted", 0),
                             Token("loss_detected", 0),
                             Token("unsupported_event", 0),
                             Token("command_error", 0),
                             Token("transport_failure", 0),
                             Token("output_failure", 0)};
    result.enums.push_back(std::move(eventCompletion));
    return result;
}
} // namespace aurora::service
