// The copied admission configuration. Aurora owns the grammar and renders
// its rejections.
#include "hosted_parser.hpp"

namespace aurora {
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
} // namespace hosted_parser
} // namespace aurora
