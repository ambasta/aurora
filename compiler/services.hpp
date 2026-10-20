#pragma once
#include "types.hpp"
#include <array>
#include <string_view>
#include <set>

namespace aurora::service {
// This closed compiler table is the only source of service identities and
// semantic service contracts. Emission linkage is owned by Aurora x86 emission.
enum class Kind {
    Console,
    Display,
    IommuEvent,
    Call,
    Port
};
enum class Operation {
    Next,
    Put,
    Pixel,
    IommuPoll,
    IommuAcknowledge,
    Call,
    PortRead8,
    PortWrite8
};
inline const std::array capabilityTypes{std::pair{Kind::Console, Type::ConsoleSession},
                                        std::pair{Kind::Display, Type::DisplaySession},
                                        std::pair{Kind::IommuEvent, Type::IommuEventSession},
                                        std::pair{Kind::Call, Type::CallSession},
                                        std::pair{Kind::Port, Type::PortRange}};
inline Kind kind(const Type &type) {
    for (const auto &[identity, candidate] : capabilityTypes)
        if (candidate == type)
            return identity;
    throw Error("not a sealed service capability type");
}
inline Type capabilityType(Kind kind) {
    for (const auto &[identity, type] : capabilityTypes)
        if (identity == kind)
            return type;
    throw Error("unknown sealed service capability kind");
}
inline bool supportedGroup(const std::set<Kind> &kinds) {
    return kinds == std::set<Kind>{Kind::Console} || kinds == std::set<Kind>{Kind::Display} ||
           kinds == std::set<Kind>{Kind::IommuEvent} || kinds == std::set<Kind>{Kind::Call} ||
           kinds == std::set<Kind>{Kind::Port} || kinds == std::set<Kind>{Kind::Console, Kind::Display} ||
           kinds == std::set<Kind>{Kind::Console, Kind::IommuEvent};
}
inline std::int64_t supportedGroupBitmap(bool includeCall = true, bool includePort = true) {
    std::int64_t result = 0;
    for (unsigned mask = 0; mask < (1U << capabilityTypes.size()); ++mask) {
        std::set<Kind> group;
        for (std::size_t index = 0; index < capabilityTypes.size(); ++index)
            if (mask & (1U << index))
                group.insert(capabilityTypes[index].first);
        if ((includeCall || !group.contains(Kind::Call)) && (includePort || !group.contains(Kind::Port)) &&
            supportedGroup(group))
            result |= std::int64_t{1} << mask;
    }
    return result;
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
inline Type sampleType();
inline Type putResultType();
inline Type displayPutResultType();
inline Type eventSampleType();
inline Type eventAckResultType();
inline Type callResultType();
inline Type callStatusType();
inline Type portWriteResultType();
inline Type portReadType() {
    return Type::U8;
}
inline constexpr bool active(Kind kind, bool includeCall, bool includePort) {
    return (kind != Kind::Call || includeCall) && (kind != Kind::Port || includePort);
}
class OperationDescription {
public:
    Kind kind;
    Operation operation;
    std::string_view spelling;
    Type (*result)();
    std::array<TypeKind, 5> parameters;
    unsigned parameterCount;
    Type resultType() const {
        return result();
    }
    std::vector<Type> parameterTypes() const {
        if (parameterCount > parameters.size())
            throw Error("invalid sealed service signature");
        std::vector<Type> values;
        for (unsigned index = 0; index < parameterCount; ++index)
            values.emplace_back(parameters[index]);
        return values;
    }
};
inline constexpr std::array operations{
    OperationDescription{Kind::Console, Operation::Next, "next", sampleType, {}, 0},
    OperationDescription{Kind::Console, Operation::Put, "put", putResultType, {TypeKind::U8}, 1},
    OperationDescription{Kind::Display,
                         Operation::Pixel,
                         "pixel",
                         displayPutResultType,
                         {TypeKind::U64, TypeKind::U64, TypeKind::U8, TypeKind::U8, TypeKind::U8},
                         5},
    OperationDescription{Kind::IommuEvent, Operation::IommuPoll, "poll", eventSampleType, {}, 0},
    OperationDescription{Kind::IommuEvent, Operation::IommuAcknowledge, "acknowledge", eventAckResultType, {}, 0},
    OperationDescription{Kind::Call, Operation::Call, "call", callResultType, {TypeKind::U64}, 1},
    OperationDescription{Kind::Port, Operation::PortRead8, "read8", portReadType, {TypeKind::U64}, 1},
    OperationDescription{
        Kind::Port, Operation::PortWrite8, "write8", portWriteResultType, {TypeKind::U64, TypeKind::U8}, 2}};
inline constexpr std::size_t operationCount(bool includeCall, bool includePort = false) {
    std::size_t count = 0;
    for (const auto &entry : operations)
        if (active(entry.kind, includeCall, includePort))
            ++count;
    return count;
}
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
inline Type callResultType() {
    Type result{std::string("__au_call_result")};
    result.displayName = "builtin::CallResult";
    return result;
}
inline Type callStatusType() {
    Type result = Type::enumeration("__au_call_status");
    result.displayName = "builtin::CallStatus";
    return result;
}
inline Type portWriteResultType() {
    Type result = Type::enumeration("__au_port_write_result");
    result.displayName = "builtin::PortWriteResult";
    return result;
}
inline bool copiedType(const Type &type) {
    return type == portWriteResultType() || type == sampleType() || type == putResultType() ||
           type == completionType() || type == displayPutResultType() || type == displayCompletionType() ||
           type == eventSampleType() || type == callResultType() || type == callStatusType() ||
           type == eventPollResultType() || type == eventAckResultType() || type == eventIntakeCompletionType();
}
// Canonical copied service data, shared by descriptor seeding and existing
// semantic helpers. The source type helpers above retain identity authority.
class CopiedDefinition {
public:
    Type type;
    std::vector<std::pair<std::string, Type>> fields;
    std::vector<std::string> cases;
};
inline std::array<CopiedDefinition, 12> copiedDefinitions() {
    return {
        CopiedDefinition{sampleType(), {{"byte_present", Type::Bool}, {"byte", Type::U8}, {"damaged", Type::Bool}}, {}},
        CopiedDefinition{putResultType(), {}, {"success", "timeout"}},
        CopiedDefinition{completionType(), {}, {"requested_exit", "output_failure"}},
        CopiedDefinition{displayPutResultType(), {}, {"success", "out_of_bounds"}},
        CopiedDefinition{displayCompletionType(), {}, {"rendered", "output_failure"}},
        CopiedDefinition{
            eventSampleType(),
            {{"result", eventPollResultType()}, {"word0", Type::U64}, {"word1", Type::U64}, {"status_low", Type::U64}},
            {}},
        CopiedDefinition{eventPollResultType(), {}, {"empty", "record", "overflow", "transport_failure"}},
        CopiedDefinition{eventAckResultType(), {}, {"committed", "overflow", "transport_failure"}},
        CopiedDefinition{eventIntakeCompletionType(),
                         {},
                         {"drained",
                          "budget_exhausted",
                          "loss_detected",
                          "unsupported_event",
                          "command_error",
                          "transport_failure",
                          "output_failure"}},
        CopiedDefinition{callResultType(), {{"status", callStatusType()}, {"value", Type::U64}}, {}},
        CopiedDefinition{callStatusType(), {}, {"replied", "cancelled", "rejected"}},
        CopiedDefinition{portWriteResultType(), {}, {"issued"}}};
}
} // namespace aurora::service
