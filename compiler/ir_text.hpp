#pragma once
#include "ir.hpp"
#include <string>
#include <string_view>

// Textual IR (.air): a line-oriented spelling of the raw ir::Module fixture
// route. The reader never validates, so malformed modules can be written down;
// validation stays with ir::validate. See tests/compiler/ir/README.md.
namespace aurora::ir::text {
std::string print(const Module &module);
// Throws Error("air:<line>: ...") on syntax errors only.
Module read(std::string_view source);
std::string printType(const Type &type);
std::string printInstruction(const InstructionObservation &instruction);
} // namespace aurora::ir::text
