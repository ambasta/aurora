#include "x86.hpp"
#include "hosted_ir_instructions.hpp"
#include "hosted_resolver.hpp"
#include "../runtime/hosted_bytes.hpp"
#include <algorithm>
#include <array>
#include <cstdint>
#include <limits>
#include <set>
#include <string_view>

namespace aurora {
namespace {
namespace wire = hosted_abi::compiler_x86;
constexpr std::int64_t artifactLimit = 64 * 1024 * 1024;
// A quota bounds final logical payload, not reallocations' transient host peaks.
// No IR-sized pool is allocated here: these are checked upper extents used by
// the existing region allocator as the source workspace grows on demand.
constexpr bool addExtent(std::uint64_t &total, std::uint64_t count, std::uint64_t stride) {
    if (stride != 0 && count > (std::numeric_limits<std::uint64_t>::max() - total) / stride)
        return false;
    total += count * stride;
    return true;
}
constexpr std::uint64_t payloadQuota(std::uint64_t retained, std::uint64_t views, std::uint64_t instructions) {
    std::uint64_t functions = retained, calls = instructions;
    // Each direct/query call fact has an instruction. A retained function can
    // additionally call each member of the source's bounded runtime vocabulary.
    if (!addExtent(functions, views, 2) || !addExtent(calls, retained, 64))
        return 0;
    std::uint64_t stack = artifactLimit * 2 + 1024;
    if (!addExtent(stack, functions, 1024) || !addExtent(stack, calls, 128))
        return 0;
    std::uint64_t quota = 0;
    // Geometric output capacity <=2x required bytes (plus its initial block).
    if (!addExtent(quota, artifactLimit + 4096, 2) || !addExtent(quota, stack, 2) ||
        !addExtent(quota, retained, 2 * sizeof(wire::IndexRow)) ||
        !addExtent(quota, functions, sizeof(wire::IndexRow)) || !addExtent(quota, calls, sizeof(wire::IndexRow)) ||
        !addExtent(quota, 32, sizeof(wire::IndexRow)) || !addExtent(quota, functions, 2 * sizeof(wire::FunctionFact)) ||
        !addExtent(quota, 16, 2 * sizeof(wire::FunctionFact)) || !addExtent(quota, calls, 2 * sizeof(wire::CallFact)) ||
        !addExtent(quota, 16, 2 * sizeof(wire::CallFact)) ||
        !addExtent(quota, instructions, 2 * sizeof(wire::LoanRow)) || !addExtent(quota, 16, 2 * sizeof(wire::LoanRow)))
        return 0;
    // Every accepted ABI row and raw name byte contributes >=1 JSON byte.
    // Their extents follow from the requested 64 MiB artifact cap. Runtime names
    // have a separate 64 KiB prefix; the 64-row runtime pool is closed source data.
    if (!addExtent(quota, artifactLimit, sizeof(wire::AbiNameRow) + 1) || !addExtent(quota, 65536, 1) ||
        !addExtent(quota, 64, sizeof(wire::NameRow)))
        return 0;
    return quota;
}
// Count-derived decisions cover the former cap without allocating huge IR in a
// default test: 256 template instances x4097 distinct callees exceed 1M facts
// while their short call text can remain below the assembly artifact cap.
static_assert(payloadQuota(256, 0, 256 * 4097) > payloadQuota(256, 0, 1048576));
static_assert(payloadQuota(0, 0, 0) > 0);
static_assert(payloadQuota(std::numeric_limits<std::uint64_t>::max(), 0, 0) == 0);
static_assert(payloadQuota(0, std::numeric_limits<std::uint64_t>::max(), 0) == 0);
static_assert(payloadQuota(0, 0, std::numeric_limits<std::uint64_t>::max()) == 0);
[[noreturn]] void resourceLimit() {
    throw Error(DiagnosticCode::Internal, "hosted x86 emission workspace extent overflow");
}
[[noreturn]] void invalidEmitter() {
    throw Error(DiagnosticCode::Internal, "invalid hosted x86 emission transport");
}
std::int64_t count(std::size_t value) {
    if (value > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()))
        resourceLimit();
    return static_cast<std::int64_t>(value);
}
} // namespace

class X86Emitter::State {
    static std::uint64_t quota(const ir::ValidatedModule &validated) {
        if (!validated.instructionOwner)
            invalidEmitter();
        const auto result = payloadQuota(validated.get().functions.size(),
                                         validated.metadata().scopeCount(),
                                         validated.instructionOwner->sourceInstructionCount(validated.metadata()));
        if (result == 0)
            resourceLimit();
        return result;
    }
    hosted::bytes::Region region;
    hosted_abi::EmitterRelease owner{};

public:
    const ir::Metadata *metadata;
    const ir::Instructions *instructions;
    const std::uint64_t sourceIdentity;
    // Three pointers occupy a canonically padded 32-byte borrowed-root tuple.
    alignas(16) std::array<const void *, 4> roots;
    explicit State(const ir::ValidatedModule &validated)
        : region(quota(validated)), metadata(&validated.metadata()), instructions(validated.instructionOwner.get()),
          sourceIdentity(instructions->sourceIdentity(*metadata)),
          roots{
              data(), metadata->sourceOwner(), instructions ? instructions->sourceOwner(*metadata) : nullptr, nullptr} {
        if (!region.is_open())
            throw Error(DiagnosticCode::Internal, "hosted x86 emission region allocation failed");
        owner.region = region.id();
        hosted_abi::EmitterCreate input{};
        input.region = region.id();
        aurora_hosted_emitter_create(&input, data());
    }
    ~State() {
        aurora_hosted_emitter_release(&owner);
    }
    State(const State &) = delete;
    State &operator=(const State &) = delete;
    void *data() {
        return owner.workspace.storage.data();
    }
    const void *data() const {
        return owner.workspace.storage.data();
    }
    bool matches(const ir::ValidatedModule &validated) const {
        if (!validated.instructionOwner)
            return false;
        const auto &supplied = validated.metadata();
        // Region IDs never wrap or repeat. Check the supplied live generation
        // before old pointers: allocator reuse cannot revive cached source roots.
        return sourceIdentity == validated.instructionOwner->sourceIdentity(supplied) && metadata == &supplied &&
               instructions == validated.instructionOwner.get();
    }
    [[noreturn]] void failure() const {
        const auto status = aurora_hosted_emitter_status(data());
        if (status == static_cast<std::int64_t>(wire::EmitStatus::allocation))
            throw Error(DiagnosticCode::Internal, "hosted x86 emission allocation failed");
        if (status == static_cast<std::int64_t>(wire::EmitStatus::limit))
            throw Error(DiagnosticCode::Internal, "hosted x86 emission exceeded its bounded output or workspace");
        invalidEmitter();
    }
    void boolean(std::int64_t result) const {
        if (result != 1)
            failure();
    }
    void complete(std::int64_t result) const {
        if (result != static_cast<std::int64_t>(wire::EmitStatus::complete))
            failure();
    }
    std::string artifact(wire::Artifact kind) const {
        const auto selector = static_cast<std::int64_t>(kind);
        const auto size = aurora_hosted_emitter_size(data(), selector);
        if (size < 0 || (kind != wire::Artifact::stack && size > artifactLimit))
            failure();
        if (static_cast<std::uint64_t>(size) > std::string{}.max_size())
            resourceLimit();
        std::string result(static_cast<std::size_t>(size), '\0');
        for (std::int64_t offset = 0; offset < size;) {
            wire::EmitChunk chunk{};
            aurora_hosted_emitter_chunk(data(), selector, offset, &chunk);
            if (chunk.byteCount <= 0 || chunk.byteCount > 512 || chunk.byteCount > size - offset)
                invalidEmitter();
            std::copy_n(chunk.payload.begin(), static_cast<std::size_t>(chunk.byteCount), result.begin() + offset);
            offset += chunk.byteCount;
        }
        return result;
    }
    void name(std::int64_t category, std::int64_t identity, std::int64_t member, const std::string &text) {
        hosted_abi::EmitterNameInput input{};
        input.name.backing = text.data();
        input.name.length = count(text.size());
        const auto first = aurora_hosted_emitter_append_name(data(), &input);
        if (first < 0)
            failure();
        hosted_abi::EmitterAbiNameInput row{};
        row.name.categoryValue = category;
        row.name.identityValue = identity;
        row.name.memberValue = member;
        row.name.beginValue = first;
        row.name.countValue = count(text.size());
        boolean(aurora_hosted_emitter_add_abi_name(data(), &row));
    }
};

X86Emitter::X86Emitter() = default;
X86Emitter::~X86Emitter() = default;
std::string
X86Emitter::emit(const ir::ValidatedModule &validated, SymbolBinding binding, ReflectionEmission reflection) {
    state_.reset();
    auto state = std::make_unique<State>(validated);
    for (const auto &body : validated.get().functions)
        state->boolean(aurora_hosted_emitter_add_retained(state->data(), count(body.callableId)));
    state->complete(aurora_hosted_emitter_run(state->roots.data(),
                                              binding == SymbolBinding::Local ? 1 : 0,
                                              reflection == ReflectionEmission::Referenced ? 1 : 0));
    auto assembly = state->artifact(wire::Artifact::assembly);
    state_ = std::move(state);
    return assembly;
}
std::string X86Emitter::stackFactsJson(const ir::ValidatedModule &validated) const {
    if (!state_ || !state_->matches(validated))
        throw Error("stack facts require the same emitted module");
    const auto artifact = static_cast<std::int64_t>(wire::Artifact::stack);
    state_->boolean(aurora_hosted_emitter_prepare_facts(state_->data(), artifact));
    alignas(16) const std::array<const void *, 2> roots{state_->data(), state_->roots[1]};
    state_->complete(aurora_hosted_emitter_facts(roots.data(), artifact));
    return state_->artifact(wire::Artifact::stack);
}
std::string X86Emitter::abiFactsJson(const ir::ValidatedModule &validated, const AbiDeclarations &declarations) const {
    if (!state_ || !state_->matches(validated))
        throw Error("ABI facts require the same emitted module");
    const auto artifact = static_cast<std::int64_t>(wire::Artifact::abi);
    state_->boolean(aurora_hosted_emitter_prepare_facts(state_->data(), artifact));
    const auto add = [&](const auto &group, std::int64_t category, const auto &find) {
        for (const auto &[symbol, declaration] : group) {
            const auto id = find(symbol);
            if (!id)
                invalidEmitter();
            state_->name(category, count(*id), -1, declaration.sourceName);
            for (std::size_t at = 0; at < declaration.members.size(); ++at)
                state_->name(category, count(*id), count(at), declaration.members[at]);
        }
    };
    add(declarations.records, 0, [&](const auto &symbol) {
        return state_->metadata->findClass(symbol);
    });
    add(declarations.enums, 1, [&](const auto &symbol) {
        return state_->metadata->findEnum(symbol);
    });
    // Transport only observations for the original retained order. Callable
    // aliases can share a symbol, so membership is by that observed name.
    std::set<std::string> retainedNames;
    for (const auto &body : validated.get().functions)
        retainedNames.insert(state_->metadata->callable(body.callableId).name());
    for (const auto &[symbol, declaration] : declarations.functions)
        if (retainedNames.contains(symbol)) {
            const auto id = state_->metadata->findCallable(symbol);
            if (!id)
                invalidEmitter();
            state_->name(2, count(*id), -1, declaration.sourceName);
        }
    alignas(16) const std::array<const void *, 2> roots{state_->data(), state_->roots[1]};
    state_->complete(aurora_hosted_emitter_facts(roots.data(), artifact));
    return state_->artifact(wire::Artifact::abi);
}
} // namespace aurora
