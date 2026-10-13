#pragma once
#include "ir.hpp"

namespace aurora::ir {
// Called only after module metadata and every function have been checked and
// normalized through their borrowed instruction ranges. Projects those functions,
// runs independent Aurora graph checks and applies its retained bits in original
// function order. No lowering Session.
void verifyHostedGraph(std::vector<FunctionBody> &functions, const Metadata &metadata);
} // namespace aurora::ir
