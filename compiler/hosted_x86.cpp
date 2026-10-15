#include "x86.hpp"
#include "hosted_ir_instructions.hpp"
#include "hosted_resolver.hpp"
#include "../runtime/hosted_bytes.hpp"
#include <algorithm>
#include <array>
#include <charconv>
#include <cstdint>
#include <limits>
#include <set>
#include <string_view>

extern "C" {
void aurora_hosted_emitter_create(const void *, void *) noexcept;
void aurora_hosted_emitter_release(void *) noexcept;
std::int64_t aurora_hosted_emitter_status(const void *) noexcept;
std::int64_t aurora_hosted_emitter_add_retained(void *, std::int64_t) noexcept;
std::int64_t aurora_hosted_emitter_prepare_abi(void *) noexcept;
std::int64_t aurora_hosted_emitter_append_name(void *, const void *) noexcept;
std::int64_t aurora_hosted_emitter_add_abi_name(void *, const void *) noexcept;
std::int64_t aurora_hosted_emitter_run(const void *, std::int64_t, std::int64_t) noexcept;
std::int64_t aurora_hosted_emitter_abi(const void *) noexcept;
std::int64_t aurora_hosted_emitter_size(const void *, std::int64_t) noexcept;
void aurora_hosted_emitter_chunk(const void *, std::int64_t, std::int64_t, void *) noexcept;
}

namespace aurora {
namespace {
namespace wire = hosted_abi::compiler_x86;
constexpr std::int64_t artifactLimit = 64 * 1024 * 1024;
[[noreturn]] void invalidEmitter() {
    throw Error(DiagnosticCode::Internal, "invalid hosted x86 emission transport");
}
std::int64_t count(std::size_t value) {
    if (value > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()))
        invalidEmitter();
    return static_cast<std::int64_t>(value);
}
// Mechanical compatibility decoder for the existing in-process test/consumer
// observation. Production sidecars are the original Aurora-produced bytes;
// this decoder computes no layout, stack cost, symbol or instruction policy.
class StackObservation {
    std::string_view bytes;
    bool take(std::string_view text) {
        if (!bytes.starts_with(text))
            return false;
        bytes.remove_prefix(text.size());
        return true;
    }
    void need(std::string_view text) {
        if (!take(text))
            invalidEmitter();
    }
    std::string string() {
        need("\"");
        std::string result;
        while (!bytes.empty()) {
            char value = bytes.front();
            bytes.remove_prefix(1);
            if (value == '"')
                return result;
            if (value == '\\') {
                if (bytes.empty())
                    invalidEmitter();
                value = bytes.front();
                bytes.remove_prefix(1);
                if (value == 'n')
                    value = '\n';
                else if (value == 'r')
                    value = '\r';
                else if (value == 't')
                    value = '\t';
                else if (value == 'b')
                    value = '\b';
                else if (value == 'f')
                    value = '\f';
                else if (value == 'u') {
                    if (bytes.size() < 4 || !bytes.starts_with("00"))
                        invalidEmitter();
                    unsigned byte = 0;
                    const auto parsed = std::from_chars(bytes.data() + 2, bytes.data() + 4, byte, 16);
                    if (parsed.ec != std::errc{} || parsed.ptr != bytes.data() + 4 || byte > 255)
                        invalidEmitter();
                    bytes.remove_prefix(4);
                    value = static_cast<char>(byte);
                } else if (value != '"' && value != '\\' && value != '/')
                    invalidEmitter();
            } else if (static_cast<unsigned char>(value) < 32)
                invalidEmitter();
            result.push_back(value);
        }
        invalidEmitter();
    }
    int integer() {
        int value = 0;
        const auto parsed = std::from_chars(bytes.data(), bytes.data() + bytes.size(), value);
        if (parsed.ec != std::errc{} || parsed.ptr == bytes.data() || value < 0)
            invalidEmitter();
        bytes.remove_prefix(static_cast<std::size_t>(parsed.ptr - bytes.data()));
        return value;
    }
    template <class Body> void entries(std::string_view end, Body body) {
        if (take(end))
            return;
        do {
            body();
        } while (take(","));
        need(end);
    }

public:
    explicit StackObservation(std::string_view input) : bytes(input) {
    }
    std::map<std::string, FunctionStackFacts> read() {
        std::map<std::string, FunctionStackFacts> result;
        need("{\"version\":2,\"functions\":{");
        entries("}", [&] {
            const auto name = string();
            FunctionStackFacts fact;
            need(":{\"local_bytes\":");
            fact.localBytes = integer();
            need(",\"calls\":{");
            entries("}", [&] {
                const auto callee = string();
                need(":");
                if (!fact.calls.emplace(callee, integer()).second)
                    invalidEmitter();
            });
            need(",\"copied_record\":");
            if (!take("null")) {
                CopiedRecordFacts copied;
                need("{\"parameter_bytes\":[");
                entries("]", [&] {
                    copied.parameterBytes.push_back(integer());
                });
                need(",\"result_bytes\":");
                copied.resultBytes = integer();
                need("}");
                fact.copiedRecord = std::move(copied);
            }
            if (take(",\"service_abi\":{\"record\":")) {
                if (!take("null")) {
                    ServiceRecordFacts service;
                    need("{\"parameters\":[");
                    entries("]", [&] {
                        need("[");
                        const auto kind = string();
                        need(",");
                        service.parameters.emplace_back(kind, integer());
                        need("]");
                    });
                    need(",\"result_bytes\":");
                    service.resultBytes = integer();
                    need("}");
                    fact.serviceRecord = std::move(service);
                }
                need(",\"calls\":{");
                entries("}", [&] {
                    const auto callee = string();
                    need(":{\"sysv_arguments\":");
                    const int arguments = integer();
                    need(",\"result_max\":");
                    const int maximum = integer();
                    need("}");
                    if (!fact.serviceCalls.emplace(callee, ServiceCallFacts{arguments, maximum}).second)
                        invalidEmitter();
                });
                need("}");
            }
            need("}");
            if (!result.emplace(name, std::move(fact)).second)
                invalidEmitter();
        });
        need("}\n");
        if (!bytes.empty())
            invalidEmitter();
        return result;
    }
};
} // namespace

class X86Emitter::State {
    // Includes temporary growth peaks as well as all three bounded artifacts.
    hosted::bytes::Region region{512ULL * 1024 * 1024};
    hosted_abi::EmitterRelease owner{};

public:
    const ir::Metadata *metadata;
    const ir::Instructions *instructions;
    // Three pointers occupy a canonically padded 32-byte borrowed-root tuple.
    alignas(16) std::array<const void *, 4> roots;
    std::string stackJson;
    mutable std::optional<std::map<std::string, FunctionStackFacts>> observation;
    explicit State(const ir::ValidatedModule &validated)
        : metadata(&validated.metadata()), instructions(validated.instructionOwner.get()),
          roots{
              data(), metadata->sourceOwner(), instructions ? instructions->sourceOwner(*metadata) : nullptr, nullptr} {
        if (!instructions || !region.is_open())
            invalidEmitter();
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
    std::string artifact(std::int64_t kind) const {
        const auto size = aurora_hosted_emitter_size(data(), kind);
        if (size < 0 || size > artifactLimit)
            failure();
        std::string result(static_cast<std::size_t>(size), '\0');
        for (std::int64_t offset = 0; offset < size;) {
            wire::EmitChunk chunk{};
            aurora_hosted_emitter_chunk(data(), kind, offset, &chunk);
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
    auto assembly = state->artifact(0);
    state->stackJson = state->artifact(1);
    state_ = std::move(state);
    return assembly;
}
const std::map<std::string, FunctionStackFacts> &X86Emitter::stackFacts() const {
    static const std::map<std::string, FunctionStackFacts> empty;
    if (!state_)
        return empty;
    if (!state_->observation)
        state_->observation = StackObservation(state_->stackJson).read();
    return *state_->observation;
}
std::string X86Emitter::stackFactsJson() const {
    return state_ ? state_->stackJson : "{\"version\":2,\"functions\":{}}\n";
}
std::string X86Emitter::abiFactsJson(const ir::ValidatedModule &validated, const AbiDeclarations &declarations) const {
    if (!state_ || state_->metadata != &validated.metadata() ||
        state_->instructions != validated.instructionOwner.get())
        throw Error("ABI facts require the same emitted module");
    state_->boolean(aurora_hosted_emitter_prepare_abi(state_->data()));
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
    const std::array<const void *, 2> roots{state_->data(), state_->roots[1]};
    state_->complete(aurora_hosted_emitter_abi(roots.data()));
    return state_->artifact(2);
}
} // namespace aurora
