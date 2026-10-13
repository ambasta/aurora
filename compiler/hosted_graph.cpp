#include "hosted_graph.hpp"
#include "../runtime/hosted_bytes.hpp"
#include <algorithm>
#include <array>
#include <limits>
#include <type_traits>

extern "C" {
void aurora_hosted_graph_create_input(const void *, void *) noexcept;
void aurora_hosted_graph_create_workspace(const void *, void *) noexcept;
void aurora_hosted_graph_release_input(void *) noexcept;
void aurora_hosted_graph_release_workspace(void *) noexcept;
std::int64_t aurora_hosted_graph_set_function(void *, const void *) noexcept;
std::int64_t aurora_hosted_graph_set_edge(void *, const void *) noexcept;
std::int64_t aurora_hosted_graph_run(const void *) noexcept;
std::int64_t aurora_hosted_graph_retained(const void *, std::int64_t) noexcept;
}

namespace aurora::ir {
namespace {
namespace wire = hosted_abi::compiler_ir_graph;
[[noreturn]] void invalidGraph() {
    throw Error(DiagnosticCode::Internal, "invalid hosted IR graph result");
}
std::int64_t graphCount(std::size_t count) {
    if (count > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()))
        invalidGraph();
    return static_cast<std::int64_t>(count);
}
const std::string *callee(const Instruction &instruction) {
    return std::visit(
        [](const auto &call) -> const std::string * {
            using T = std::decay_t<decltype(call)>;
            if constexpr (std::is_same_v<T, Call> || std::is_same_v<T, MethodCall> ||
                          std::is_same_v<T, BorrowedCall> || std::is_same_v<T, AggregateCall> ||
                          std::is_same_v<T, ServiceCall> || std::is_same_v<T, ResourceCall>)
                return &call.callee;
            return nullptr;
        },
        instruction);
}
std::uint64_t graphQuota(std::int64_t functions, std::int64_t edges) {
    const auto maximum = static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max());
    const auto functionWidth = sizeof(wire::FunctionRow) + sizeof(wire::StateRow) + sizeof(wire::FrameRow) +
                               sizeof(wire::IndexRow);
    const auto edgeWidth = sizeof(wire::IndexRow) + sizeof(wire::ReverseEdge);
    const auto nodes = static_cast<std::uint64_t>(functions), calls = static_cast<std::uint64_t>(edges);
    if (nodes > maximum / functionWidth || calls > (maximum - nodes * functionWidth) / edgeWidth)
        invalidGraph();
    return nodes * functionWidth + calls * edgeWidth;
}
class GraphOwners {
    hosted::bytes::Region region;
    hosted_abi::GraphReleaseInput input;
    hosted_abi::GraphReleaseWorkspace workspace;

public:
    GraphOwners(std::int64_t functions, std::int64_t edges) : region(graphQuota(functions, edges)) {
        input.region = workspace.region = region.id();
        hosted_abi::GraphCreateInput createInput;
        createInput.region = region.id();
        createInput.functions = functions;
        createInput.edges = edges;
        aurora_hosted_graph_create_input(&createInput, inputData());
        hosted_abi::GraphCreateWorkspace createWorkspace;
        createWorkspace.region = region.id();
        createWorkspace.functions = functions;
        createWorkspace.edges = edges;
        aurora_hosted_graph_create_workspace(&createWorkspace, workspaceData());
    }
    ~GraphOwners() {
        aurora_hosted_graph_release_workspace(&workspace);
        aurora_hosted_graph_release_input(&input);
    }
    GraphOwners(const GraphOwners &) = delete;
    GraphOwners &operator=(const GraphOwners &) = delete;
    void *inputData() { return input.input.storage.data(); }
    void *workspaceData() { return workspace.workspace.storage.data(); }
};
} // namespace

void verifyHostedGraph(std::vector<Function> &functions) {
    std::map<std::string, std::int64_t> indices;
    std::size_t callCount = 0;
    for (std::size_t index = 0; index < functions.size(); ++index) {
        indices.emplace(functions[index].name, graphCount(index));
        for (const auto &instruction : functions[index].code)
            if (callee(instruction)) {
                if (callCount == std::numeric_limits<std::size_t>::max())
                    invalidGraph();
                ++callCount;
            }
    }
    GraphOwners owners(graphCount(functions.size()), graphCount(callCount));
    std::int64_t edge = 0;
    for (std::size_t index = 0; index < functions.size(); ++index) {
        const auto &function = functions[index];
        hosted_abi::GraphFunctionInput value;
        value.index = graphCount(index);
        value.function.firstEdge = edge;
        value.function.hasReceiver = function.receiver.has_value();
        value.function.serviceEntry = std::any_of(function.parameters.begin(), function.parameters.end(),
                                                  [](const Type &type) { return type.isService(); });
        value.function.rootScope = function.moduleScope == 0;
        for (const auto &instruction : function.code)
            if (const auto *target = callee(instruction)) {
                hosted_abi::GraphEdgeInput call;
                call.index = edge++;
                call.target = indices.at(*target);
                if (aurora_hosted_graph_set_edge(owners.inputData(), &call) != 1)
                    invalidGraph();
            }
        value.function.edgeCount = edge - value.function.firstEdge;
        if (aurora_hosted_graph_set_function(owners.inputData(), &value) != 1)
            invalidGraph();
    }
    // Paired borrowers receive addresses of live owners, never copied descriptors.
    // Root order and authority are checked against generated ABI facts.
    const std::array<const void *, 2> roots{owners.workspaceData(), owners.inputData()};
    const auto result = aurora_hosted_graph_run(roots.data());
    if (result == static_cast<std::int64_t>(wire::GraphStatus::recursive))
        throw Error("invalid typed IR: recursive receiver call cycle");
    if (result != static_cast<std::int64_t>(wire::GraphStatus::success))
        invalidGraph();
    std::vector<bool> retained;
    retained.reserve(functions.size());
    for (std::size_t index = 0; index < functions.size(); ++index) {
        const auto keep = aurora_hosted_graph_retained(owners.workspaceData(), graphCount(index));
        if (keep != 0 && keep != 1)
            invalidGraph();
        retained.push_back(keep == 1);
    }
    std::erase_if(functions, [&](const Function &function) {
        return !retained[static_cast<std::size_t>(indices.at(function.name))];
    });
}
} // namespace aurora::ir
