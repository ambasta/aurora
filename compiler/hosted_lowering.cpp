#include "hosted_lowering.hpp"
#include "hosted_ir_instructions.hpp"
#include <algorithm>
#include <array>
#include <limits>
#include <utility>

namespace aurora {
namespace {
namespace wire = hosted_abi::compiler_lowering;
using InstructionWriter = ir::detail::InstructionWriter;
using wire::OperandRole;
using wire::RecordKind;
// Source projection uses these closed ordinals as raw integers, never casts
// arbitrary table payloads into a language enum.
static_assert([] {
    constexpr std::array kinds{TypeKind::I64,
                               TypeKind::Bool,
                               TypeKind::Own,
                               TypeKind::Ref,
                               TypeKind::MutRef,
                               TypeKind::Class,
                               TypeKind::Array,
                               TypeKind::U64,
                               TypeKind::Parameter,
                               TypeKind::Enum,
                               TypeKind::U8,
                               TypeKind::ByteSpan,
                               TypeKind::ByteRegion,
                               TypeKind::OwnedBytes,
                               TypeKind::ConsoleSession,
                               TypeKind::DisplaySession,
                               TypeKind::IommuEventSession,
                               TypeKind::OwnedValues,
                               TypeKind::CallSession};
    for (std::size_t at = 0; at < kinds.size(); ++at)
        if (static_cast<std::size_t>(kinds[at]) != at)
            return false;
    return true;
}());
static_assert(static_cast<int>(service::Kind::Console) == 0 && static_cast<int>(service::Kind::Display) == 1 &&
              static_cast<int>(service::Kind::IommuEvent) == 2 && static_cast<int>(service::Kind::Call) == 3);
static_assert(static_cast<int>(service::Operation::Next) == 0 && static_cast<int>(service::Operation::Put) == 1 &&
              static_cast<int>(service::Operation::Pixel) == 2 &&
              static_cast<int>(service::Operation::IommuPoll) == 3 &&
              static_cast<int>(service::Operation::IommuAcknowledge) == 4 &&
              static_cast<int>(service::Operation::Call) == 5);
static_assert(static_cast<int>(RecordKind::ScalarSlot) == 10 && static_cast<int>(RecordKind::ObjectSlot) == 11 &&
              static_cast<int>(RecordKind::ArraySlot) == 12 && static_cast<int>(RecordKind::SpanSlot) == 13 &&
              static_cast<int>(RecordKind::ServiceSlot) == 14 && static_cast<int>(RecordKind::RegionSlot) == 15 &&
              static_cast<int>(RecordKind::ByteSlot) == 16 && static_cast<int>(RecordKind::OwnedValueType) == 17);

[[noreturn]] void invalidLowering() {
    throw Error(DiagnosticCode::Internal, "invalid hosted lowering result");
}
std::size_t sizeValue(std::int64_t value) {
    if (value < 0 || static_cast<std::uint64_t>(value) > std::numeric_limits<std::size_t>::max())
        invalidLowering();
    return static_cast<std::size_t>(value);
}
} // namespace
std::uint64_t projectionQuota(const HostedLoweringInput &input, std::span<const std::uint8_t> table) {
    if (input.sourceByteCount < 0)
        invalidLowering();
    const auto add = [](std::uint64_t a, std::uint64_t b) {
        if (b > std::numeric_limits<std::uint64_t>::max() - a)
            invalidLowering();
        return a + b;
    };
    const auto mul = [](std::uint64_t a, std::uint64_t b) {
        if (a && b > std::numeric_limits<std::uint64_t>::max() / a)
            invalidLowering();
        return a * b;
    };
    const auto rows = input.rows.size(), operands = input.operands.size();
    // Exact graph allocations: one claim byte per row/operand and one
    // 16-byte node/request per row/operand. No rendered identities yet.
    const auto graph = mul(17, add(rows, operands));
    if (table.empty())
        return graph;
    const auto word = [&](std::size_t at) {
        if (at > table.size() || 8 > table.size() - at)
            invalidLowering();
        std::uint64_t result = 0;
        for (unsigned byte = 0; byte < 8; ++byte)
            result |= std::uint64_t{table[at + byte]} << (byte * 8);
        return result;
    };
    const auto identities = word(0);
    if (identities > operands || identities > (table.size() - 8) / 80)
        invalidLowering();
    std::uint64_t longest = 0, carriers = 0;
    for (std::uint64_t at = 0; at < identities; ++at)
        longest = std::max(longest, word(8 + at * 80 + 32));
    for (const auto &row : input.rows)
        carriers += row.recordKind == wire::RecordKind::Carrier;
    const auto rendered = add(table.size(), mul(carriers, add(longest, 28)));
    // Intern entries reference requested or generated carrier names. The
    // geometric capacity is strictly below twice the used count (minimum 8).
    const auto intern = mul(24, std::max<std::uint64_t>(8, mul(2, add(identities, carriers))));
    auto quota = add(graph, rendered);
    quota = add(quota, mul(16, rows));
    quota = add(quota, mul(48, add(operands, mul(2, rows))));
    quota = add(quota, add(35 * 8, intern));
    // Ownership disjointness bounds type occurrences by O+2R, indices by
    // O+R, instruction operands by O, and every other output row pool by R.
    // Their fixed widths sum to <=14O+78R words; 80(O+R) covers all pools.
    quota = add(quota, mul(8 * 80, add(rows, operands)));
    // Interned bytes are drawn from the rendered table/carrier suffix. Each
    // retained instruction has at most one source-bounded literal slice.
    quota = add(quota, add(rendered, mul(rows, input.sourceByteCount)));
    // Region quotas charge logical payload, not realloc overlap or native
    // vectors. Process/cgroup peak memory is measured separately.
    return quota;
}
std::vector<std::uint8_t> renderProjectionIdentities(const void *plan, const HostedLoweringServices &services) {
    std::vector<std::uint8_t> requests;
    for (;;) {
        hosted_abi::compiler_projection::ProjectionChunk chunk{};
        aurora_hosted_projection_requests(plan, static_cast<std::int64_t>(requests.size()), &chunk);
        if (chunk.byteCount < 0 || chunk.byteCount > 512 || chunk.byteCount % 16 != 0)
            invalidLowering();
        requests.insert(requests.end(), chunk.payload.begin(), chunk.payload.begin() + chunk.byteCount);
        if (chunk.byteCount < 512)
            break;
    }
    const auto word = [&](std::size_t at) {
        std::uint64_t result = 0;
        for (unsigned byte = 0; byte < 8; ++byte)
            result |= std::uint64_t{requests.at(at + byte)} << (byte * 8);
        return result;
    };
    const auto count = requests.size() / 16;
    if (count > (static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()) - 8) / 80)
        invalidLowering();
    std::vector<std::uint8_t> response(8 + count * 80);
    const auto put = [&](std::size_t at, std::uint64_t value) {
        for (unsigned byte = 0; byte < 8; ++byte)
            response.at(at + byte) = static_cast<std::uint8_t>(value >> (byte * 8));
    };
    put(0, count);
    for (std::size_t index = 0; index < count; ++index) {
        const auto domain = word(index * 16), rawId = word(index * 16 + 8);
        if (rawId > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()))
            invalidLowering();
        const auto id = static_cast<std::int64_t>(rawId);
        const auto base = 8 + index * 80;
        put(base, domain);
        put(base + 8, rawId);
        std::string name;
        switch (domain) {
        case 3: {
            const auto type = services.type(id);
            put(base + 16, static_cast<std::uint64_t>(type.kind));
            name = type.className;
            put(base + 40, static_cast<std::uint64_t>(type.elementKind));
            put(base + 48, static_cast<std::uint64_t>(type.length));
            put(base + 56, type.elementParameter.size());
            put(base + 64, type.lengthParameter.size());
            put(base + 72, type.templateArguments.size());
            break;
        }
        case 4:
            name = services.functionName(id);
            break;
        case 5:
            name = services.className(id);
            break;
        case 6:
            services.checkModuleScope(id);
            put(base + 16, rawId);
            break;
        case 7:
            put(base + 16, static_cast<std::uint64_t>(services.serviceKind(id)));
            break;
        case 8:
            put(base + 16, static_cast<std::uint64_t>(services.serviceOperation(id)));
            break;
        case 15:
            name = services.enumName(id);
            break;
        case 16:
            name = services.identifier(id).text;
            break;
        default:
            invalidLowering();
        }
        if (name.size() > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()) - response.size())
            invalidLowering();
        put(base + 24, response.size());
        put(base + 32, name.size());
        response.insert(response.end(), name.begin(), name.end());
    }
    return response;
}
HostedLoweringOutput projectHostedLowering(const HostedLoweringInput &input,
                                           const HostedLoweringServices &services,
                                           const void *projectionPlan) {
    if (!projectionPlan || !services.identifier)
        invalidLowering();
    HostedLoweringOutput result;
    result.instructions = InstructionWriter::project(projectionPlan);
    // Source owns graph validation and row selection. Native code retains only
    // diagnostic SourceSpan/string construction for the existing public API.
    const auto rowAt = [&](std::int64_t id) -> const wire::OutputRow & {
        const auto index = sizeValue(id);
        if (index >= input.rows.size())
            invalidLowering();
        return input.rows[index];
    };
    const auto operands = [&](std::int64_t begin, std::int64_t count) {
        const auto first = sizeValue(begin), length = sizeValue(count);
        if (first > input.operands.size() || length > input.operands.size() - first)
            invalidLowering();
        return input.operands.subspan(first, length);
    };
    const auto &root = rowAt(input.moduleRoot);
    if (root.recordKind != RecordKind::Module || root.operandCount != 7)
        invalidLowering();
    const auto lint = operands(root.operandBegin, root.operandCount)[6];
    if (lint.operandRole != OperandRole::LintDiagnostics)
        invalidLowering();
    for (const auto &reference : operands(lint.sliceBegin, lint.sliceCount)) {
        if (reference.operandRole != OperandRole::OutputRowId)
            invalidLowering();
        const auto &row = rowAt(reference.signedValue);
        if (row.recordKind != RecordKind::UnreadLocal || row.operandCount != 1)
            invalidLowering();
        const auto value = operands(row.operandBegin, row.operandCount)[0];
        if (value.operandRole != OperandRole::IdentifierSourceRef || value.signedValue < 0)
            invalidLowering();
        auto token = services.identifier(value.signedValue);
        result.diagnostics.push_back({DiagnosticCode::UnreadLocal,
                                      "local binding '" + token.text + "' is never read",
                                      std::move(token.span),
                                      DiagnosticSeverity::Warning});
    }
    std::sort(result.diagnostics.begin(), result.diagnostics.end(), [](const auto &left, const auto &right) {
        return left.span.begin.offset < right.span.begin.offset;
    });
    return result;
}
} // namespace aurora
