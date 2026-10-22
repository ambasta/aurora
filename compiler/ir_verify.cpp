#include "ir_verify.hpp"
#include "hosted_graph.hpp"
#include "hosted_ir_instructions.hpp"
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace aurora::ir {
namespace verification {
namespace {
[[noreturn]] inline void fail(std::string_view message) {
    throw Error("invalid typed IR: " + std::string(message));
}
inline void require(bool condition, std::string_view message) {
    if (!condition)
        fail(message);
}
} // namespace
} // namespace verification
ValidatedModule validate(Module module, verification::Metrics *metrics) {
    // Import consumes and destroys all raw fixture construction before either
    // independent admission. Only the paired Aurora-owned bundle returns.
    auto pending = InstructionIngress::import(std::move(module));
    return validate(std::move(pending), metrics);
}
ValidatedModule validate(InstructionIngress pending, verification::Metrics *metrics) {
    // Finish metadata first; then source generic instruction admission checks
    // suffix tails before codec reconstruction can discard unresolved payloads.
    auto metadata = std::move(pending.metadata_).finish();
    auto instructions = std::move(pending.instructions_);
    if (!instructions)
        throw Error(DiagnosticCode::Internal, "missing hosted IR instruction ingress");
    instructions->admit(*metadata);
    // Source checks every CFG, then every normalized entry binding, then every
    // immutable call, storage-access and scalar contract before dynamic verification.
    instructions->structure();
    std::vector<FunctionBody> functions;
    functions.reserve(instructions->bodyCount());
    for (std::size_t id = 0; id < instructions->bodyCount(); ++id)
        functions.push_back({id, instructions->range(id)});
    verification::require(functions.size() == metadata->callableCount(), "callable body count mismatch");
    for (std::size_t index = 0; index < functions.size(); ++index) {
        // Preserve declaration order, including unused bodies, before pruning.
        verification::require(functions[index].callableId == index,
                              "callable body ID does not match declaration order");
        instructions->verifySource(*metadata, functions[index].callableId, metrics);
    }
    // No native dynamic fallback. Graph admission and publication are reached
    // only after every source whole-function verification succeeds.
    verifyHostedGraph(functions, *metadata);
    instructions->publish();
    return ValidatedModule(std::move(functions), std::move(metadata), std::move(instructions));
}
} // namespace aurora::ir
