#pragma once
#include "hosted_frontend_abi.hpp"

namespace aurora::hosted_parser {
using hosted_abi::compiler_parser::NodeKind;
using hosted_abi::compiler_parser::Stop;
using hosted_abi::compiler_parser::SyntaxKind;
using hosted_abi::compiler_parser::TypeKind;
using Status = hosted_abi::compiler_parser::ParseStatus;
} // namespace aurora::hosted_parser
