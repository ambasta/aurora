#pragma once
#include "ir.hpp"

namespace aurora::ir {
// Called only after module metadata and every function have been checked and
// normalized. Projects that actual Module, runs independent Aurora graph checks,
// and applies its retained bits in original function order. No lowering Session.
void verifyHostedGraph(Module &module);
} // namespace aurora::ir
