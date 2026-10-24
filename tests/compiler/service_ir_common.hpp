// Shared hand-built service IR fixtures and checks for the sealed-service IR tests.
// Compiled once (service_ir_common.cpp); each service fixture runs only its own cases.
#pragma once
#include "ir_verify.hpp"
#include "hosted_resolver.hpp"
#include "x86.hpp"
#include "json_fragments.hpp"
#include <algorithm>
#include <array>
#include <functional>
#include <iostream>
#include <string>
#include <tuple>

namespace aurora::test::service_ir {
using F = aurora::ir::Function;
using aurora::ir::Module;
extern int checks;
void need(bool value, const std::string &message);
void canonicalTypes(Module &module);
F entry(const std::string &name);
Module sample();
Module forwarded();
Module copiedResult(bool empty = false);
Module copiedArguments(int shape = 0, bool paired = false);
aurora::ir::ServiceCall &copiedCall(Module &module);
Module copiedSpanArgument();
Module mixedEntry();
Module mixedForwarded();
Module withRegion(Module module);
void copiedArgumentFacts();
Module displayPixel();
Module displayForwarded();
void good(Module m);
void displayServiceCases(); // display_service_ir.cpp
void bad(Module m, const std::function<void(Module &)> &mutate, const std::string &expected = {});
} // namespace aurora::test::service_ir

using namespace aurora;
using namespace aurora::ir;
using namespace aurora::test::service_ir;
using aurora::test::jsonMember;
using aurora::test::jsonMembers;
using F = aurora::ir::Function;
