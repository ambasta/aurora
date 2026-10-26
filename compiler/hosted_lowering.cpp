#include "hosted_lowering.hpp"
#include "hosted_lowering_ingress.hpp"
#include "../runtime/hosted_bytes.hpp"
#include <limits>

namespace aurora {
namespace {
namespace projection = hosted_abi::compiler_lowering_projection;
namespace lowering = hosted_abi::compiler_lowering;
namespace resolver = hosted_abi::compiler_resolver;
namespace bytes = hosted::bytes;
[[noreturn]] void invalidLowering() {
    throw Error(DiagnosticCode::Internal, "invalid hosted lowering result");
}
std::int64_t add(std::int64_t left, std::int64_t right) {
    if (left < 0 || right < 0 || left > std::numeric_limits<std::int64_t>::max() - right)
        invalidLowering();
    return left + right;
}
std::int64_t multiply(std::int64_t count, std::size_t width) {
    if (count < 0 || width > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()) ||
        (width != 0 && static_cast<std::uint64_t>(count) >
                           static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()) / width))
        invalidLowering();
    return count * static_cast<std::int64_t>(width);
}
void published(std::int64_t count, std::size_t width, std::uint64_t payloadBytes) {
    if (count < 0 || static_cast<std::uint64_t>(count) > payloadBytes / width)
        invalidLowering();
}
// These are copied source records, not native interpretations of owner handles.
// The generated ABI must establish each width before its grant is calculated.
static_assert(sizeof(projection::ProjectionRow) == 32 && sizeof(projection::IdentityCache) == 88 &&
              sizeof(projection::NameEntry) == 40 && sizeof(hosted_abi::compiler_ir_metadata::IndexRow) == 8);
std::uint64_t quota(std::int64_t outputs, std::int64_t operands, std::int64_t metadata, std::int64_t nameCapacity) {
    const auto candidates = add(add(metadata, outputs), 1);
    auto total = multiply(outputs, sizeof(projection::ProjectionRow));
    total = add(total, operands);
    total = add(total, multiply(metadata, sizeof(projection::IdentityCache)));
    total = add(total, multiply(add(candidates, candidates), sizeof(projection::NameEntry)));
    const auto ordering = add(outputs, add(operands, operands));
    total = add(total, multiply(ordering, sizeof(hosted_abi::compiler_ir_metadata::IndexRow)));
    total = add(total, multiply(52, sizeof(hosted_abi::compiler_ir_metadata::IndexRow)));
    total = add(total, multiply(add(metadata, 512), sizeof(hosted_abi::compiler_ir_metadata::IndexRow)));
    return static_cast<std::uint64_t>(add(total, nameCapacity));
}
class Workspace final {
    hosted_abi::ProjectionRelease release_{};

public:
    Workspace(std::uint64_t region,
              std::int64_t outputs,
              std::int64_t operands,
              std::int64_t metadata,
              std::int64_t nameCapacity) {
        release_.region = region;
        hosted_abi::ProjectionCreate create{};
        create.region = region;
        create.outputs = outputs;
        create.operands = operands;
        create.metadata = metadata;
        create.nameCapacity = nameCapacity;
        aurora_hosted_projection_create(&create, data());
    }
    ~Workspace() {
        aurora_hosted_projection_release(&release_);
    }
    Workspace(const Workspace &) = delete;
    Workspace &operator=(const Workspace &) = delete;
    void *data() {
        return release_.workspace.storage.data();
    }
};
void measured(std::int64_t status) {
    if (status == 4)
        throw Error(DiagnosticCode::Internal, "hosted lowering projection allocation failed");
    if (status != 1)
        invalidLowering();
}
} // namespace
HostedLoweringOutput projectHostedLowering(const void *session,
                                           std::uint64_t payloadBytes,
                                           std::int64_t moduleRoot,
                                           std::int64_t diagnosticRow) {
    if (!session)
        invalidLowering();
    const auto outputs = aurora_hosted_lowering_count(session, 0);
    const auto operands = aurora_hosted_lowering_count(session, 1);
    const auto metadata = aurora_hosted_resolver_count(session, 2);
    const auto source = aurora_hosted_resolver_count(session, 0);
    published(outputs, sizeof(lowering::OutputRow), payloadBytes);
    published(operands, sizeof(lowering::OperandRow), payloadBytes);
    published(metadata, sizeof(resolver::MetaRow), payloadBytes);
    published(source, 1, payloadBytes);
    // Source scans actual published name contributors before any scratch grant.
    // This is scalar report transport, not a native lowering/name traversal.
    const auto names = aurora_hosted_projection_name_capacity(session);
    bytes::Region region(quota(outputs, operands, metadata, names));
    Workspace workspace(region.id(), outputs, operands, metadata, names);
    measured(ir::detail::LoweringIngress::measure(session, workspace.data(), moduleRoot, diagnosticRow));
    hosted_abi::compiler_ir_metadata::InputCounts metadataCounts{};
    hosted_abi::compiler_ir_instructions::InstructionCounts instructionCounts{};
    aurora_hosted_projection_metadata_counts(workspace.data(), &metadataCounts);
    aurora_hosted_projection_instruction_counts(workspace.data(), &instructionCounts);
    const auto callables = aurora_hosted_projection_count(workspace.data(), 10);
    const auto slots = aurora_hosted_projection_count(workspace.data(), 11);
    const auto instructionBegin = aurora_hosted_projection_count(workspace.data(), 12);
    ir::detail::LoweringIngress pending(metadataCounts, callables, slots, instructionBegin, instructionCounts);
    pending.fill(session, workspace.data());
    HostedLoweringOutput result;
    result.instructions = std::move(pending).take();
    const auto lintCount = aurora_hosted_projection_count(workspace.data(), 37);
    if (lintCount < 0 || lintCount > outputs ||
        static_cast<std::uint64_t>(lintCount) > result.lintReferences.max_size())
        invalidLowering();
    result.lintReferences.reserve(static_cast<std::size_t>(lintCount));
    for (std::int64_t at = 0; at < lintCount; ++at) {
        const auto reference = aurora_hosted_projection_lint(workspace.data(), at);
        if (reference < 0 || reference >= metadata)
            invalidLowering();
        result.lintReferences.push_back(reference);
    }
    return result;
}
} // namespace aurora
