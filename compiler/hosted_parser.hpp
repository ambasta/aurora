#pragma once
#include "types.hpp"
#include "hosted_parser_abi.hpp"

namespace aurora::hosted_parser {
// Simultaneously live body, expression, type and namespace continuation frames.
inline constexpr std::uint64_t maximumLiveFrames = 256 + 1549 + 70 + 64;

// Copied admission input: host layout limits and the catalog's service set.
hosted_abi::compiler_parser::AdmissionConfig admissionConfiguration();
} // namespace aurora::hosted_parser
