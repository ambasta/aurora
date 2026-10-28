// Trusted transport boundary for one Aurora-owned resolution session. The host
// retains source snapshots and file-opening authority, never semantic lookup;
// Aurora renders every diagnostic the session reports.
#include "hosted_resolver.hpp"
#include "hosted_parser.hpp"
#include "hosted_pipeline.hpp"
#include "../runtime/hosted_bytes.hpp"
#include <array>
#include <limits>
#include <optional>
#include <map>
#include <utility>

namespace aurora {
namespace {
namespace wire = hosted_abi::compiler_resolver;
namespace lowering = hosted_abi::compiler_lowering;
using wire::SemanticError;
using wire::StorageStatus;
[[noreturn]] void invalidResolution() {
    throw Error(DiagnosticCode::Internal, "invalid hosted resolution result");
}
std::size_t sizeValue(std::int64_t value) {
    if (value < 0 || static_cast<std::uint64_t>(value) > std::numeric_limits<std::size_t>::max())
        invalidResolution();
    return static_cast<std::size_t>(value);
}
struct ModuleSource {
    std::shared_ptr<const SourceText> source;
    std::string moduleName;
};
// One Session plus the parser arena every source module reuses until resolution.
// Aurora bounds each Session pool as a checked i64 byte extent, and the input
// limits it enforces bound their contents; the region grants that whole range,
// so an allocation the host cannot satisfy is the only other refusal.
class SessionOwner {
    hosted::bytes::Region region;
    hosted_abi::ResolverRelease session;
    hosted_abi::ParserRelease parser;
    bool sessionLive = false, arenaLive = false;

public:
    SessionOwner() : region(std::numeric_limits<std::int64_t>::max()) {
        session.region = parser.region = region.id();
        hosted_abi::ResolverCreate input;
        input.region = region.id();
        aurora_hosted_resolver_create(&input, data());
        sessionLive = true;
    }
    ~SessionOwner() {
        release();
    }
    void releaseArena() noexcept {
        if (arenaLive)
            aurora_hosted_parser_release(&parser);
        arenaLive = false;
    }
    void release() noexcept {
        releaseArena();
        if (sessionLive)
            aurora_hosted_resolver_release(&session);
        sessionLive = false;
    }
    SessionOwner(const SessionOwner &) = delete;
    SessionOwner &operator=(const SessionOwner &) = delete;
    void *data() {
        return session.session.storage.data();
    }
    void *arena() {
        if (!sessionLive)
            invalidResolution();
        if (!arenaLive) {
            hosted_abi::ParserCreate input;
            input.region = region.id();
            aurora_hosted_parser_create(&input, parser.arena.storage.data());
            arenaLive = true;
        }
        return parser.arena.storage.data();
    }
    std::uint64_t regionId() const {
        return region.id();
    }
    // The pipeline takes the Session; its storage copy left here is dead.
    const hosted_abi::compiler_resolver::Session &consume() {
        if (!sessionLive || arenaLive)
            invalidResolution();
        sessionLive = false;
        return session.session;
    }
};
hosted_abi::BuiltinSpan span(const std::string &text) {
    hosted_abi::BuiltinSpan result;
    if (text.size() > static_cast<std::size_t>(std::numeric_limits<std::int64_t>::max()))
        invalidResolution();
    result.backing = text.data();
    result.length = static_cast<std::int64_t>(text.size());
    return result;
}
// The trivia-free spelling of text[begin, end), as Aurora names modules, or
// the relative path Aurora maps that import name to.
std::string sourceName(const std::string &text, std::int64_t begin, std::int64_t end, bool path = false) {
    hosted_abi::ResolverNameInput input;
    input.source = span(text);
    input.begin = begin;
    input.end = end;
    input.path = path;
    std::string name;
    for (;;) {
        input.offset = static_cast<std::int64_t>(name.size());
        wire::LinkageChunk chunk;
        aurora_hosted_resolver_name_chunk(&input, &chunk);
        if (chunk.byteCount < 0 || chunk.byteCount > static_cast<std::int64_t>(chunk.payload.size()))
            invalidResolution();
        name.append(reinterpret_cast<const char *>(chunk.payload.data()), static_cast<std::size_t>(chunk.byteCount));
        if (chunk.byteCount < static_cast<std::int64_t>(chunk.payload.size()))
            return name;
    }
}
} // namespace

Diagnostic sourceDiagnostic(const std::shared_ptr<const SourceText> &source,
                            const wire::SourceResult &result,
                            hosted_parser::Stop stop) {
    return copyReport(
        [&](std::int64_t offset) {
            hosted_abi::ResolverSourceReport input;
            input.source = span(source->text);
            input.result = result;
            input.stop = stop;
            input.offset = offset;
            wire::Report report{};
            aurora_hosted_resolver_source_report(&input, &report);
            return report;
        },
        [&](std::int64_t index) {
            if (index != 0)
                invalidResolution();
            return source;
        });
}
void rejectSource(const std::shared_ptr<const SourceText> &source, const wire::SourceResult &result) {
    if (result.lexical != hosted_abi::compiler_lexer::Event::token ||
        result.grammar != hosted_parser::Status::success ||
        result.declaration != hosted_parser::AdmissionStatus::success)
        throw Error(sourceDiagnostic(source, result));
    if (result.name_begin < 0 || result.name_end <= result.name_begin ||
        result.name_end > static_cast<std::int64_t>(source->text.size()) || result.detail < 0 || result.detail > 1)
        invalidResolution();
}

class HostedResolution::Impl {
    SessionOwner owner;
    std::vector<ModuleSource> sources;
    const hosted_abi::compiler_parser::AdmissionConfig admission = hosted_parser::admissionConfiguration();
    bool finished = false, failed = false;
    std::optional<std::size_t> graphRoot;
    bool graphComplete = false;
    wire::SessionStatus status() {
        wire::SessionStatus result;
        aurora_hosted_resolver_status(owner.data(), &result);
        return result;
    }
    void storage() {
        const auto result = status();
        if (result.storage == StorageStatus::allocation)
            throw Error(DiagnosticCode::Internal, "hosted module resolution allocation failed");
        if (result.storage != StorageStatus::none)
            invalidResolution();
    }
    void lowerStorage() {
        const auto value = status().storage;
        if (value == StorageStatus::allocation)
            throw Error(DiagnosticCode::Internal, "hosted lowering allocation failed");
        if (value != StorageStatus::none)
            invalidResolution();
    }
    // The source snapshot a report's module index names.
    std::shared_ptr<const SourceText> module(std::int64_t index) const {
        if (index < 0 || sizeValue(index) >= sources.size())
            invalidResolution();
        return sources[sizeValue(index)].source;
    }
    // The resolver or lowering rejection the Session latched, as Aurora rendered it.
    [[noreturn]] void reject() {
        throw Error(copyReport(
            [&](std::int64_t offset) {
                wire::Report report{};
                aurora_hosted_resolver_report(owner.data(), offset, &report);
                return report;
            },
            [this](std::int64_t index) {
                return module(index);
            }));
    }
    void configureLowering(AnalysisMode mode) {
        hosted_abi::LoweringBeginInput configuration{};
        auto &limits = configuration.configuration;
        limits.byteLeaves = maximumCopiedByteLeaves;
        limits.nonByteLeaves = maximumCopiedNonByteLeaves;
        limits.totalLeaves = maximumCopiedClassLeaves;
        limits.copiedBytes = maximumCopiedClassBytes;
        limits.byteArrayLength = maximumClassByteArrayLength;
        limits.scalarArrayLength = maximumClassScalarArrayLength;
        switch (mode) {
        case AnalysisMode::Check:
            limits.analysisMode = 0;
            break;
        case AnalysisMode::Lint:
            limits.analysisMode = 1;
            break;
        default:
            invalidResolution();
        }
        // Lowering publishes its scalar, service and layout prelude itself.
        if (aurora_hosted_lowering_begin(owner.data(), &configuration) != 1) {
            lowerStorage();
            invalidResolution();
        }
        lowerStorage();
    }
    HostedResolvedSource lower(AnalysisMode mode, const EmissionRequest &request) {
        configureLowering(mode);
        lowering::LoweringResult result;
        // Borrowed Session stays armed through execution and diagnostic
        // copying, including their exceptional exits.
        aurora_hosted_lowering_run(owner.data(), &result);
        const auto storageStatus = status().storage;
        if (result.result_status == lowering::LoweringStatus::storage_failure) {
            if (storageStatus != StorageStatus::allocation)
                invalidResolution();
            throw Error(DiagnosticCode::Internal, "hosted lowering allocation failed");
        }
        if (storageStatus != StorageStatus::none)
            invalidResolution();
        const bool success = result.result_status == lowering::LoweringStatus::success;
        if (success) {
            lowerStorage();
            if (result.result_reason != lowering::LoweringError::none || result.root_row < 1 ||
                result.diagnostic_row != 0)
                invalidResolution();
        } else if ((result.result_status != lowering::LoweringStatus::semantic_failure &&
                    result.result_status != lowering::LoweringStatus::invalid) ||
                   result.result_reason == lowering::LoweringError::none || result.root_row != -1 ||
                   result.diagnostic_row != 0) {
            invalidResolution();
        }
        if (!success)
            reject();
        // The rest of the compilation is one Aurora call that consumes the Session.
        auto output = runHostedPipeline(owner.regionId(),
                                        owner.consume(),
                                        result.root_row,
                                        result.diagnostic_row,
                                        request,
                                        [this](std::int64_t index) {
                                            return module(index);
                                        });
        HostedResolvedSource resolved;
        resolved.lintDiagnostics = std::move(output.lints);
        resolved.code = std::move(output.code);
        resolved.stackFacts = std::move(output.stackFacts);
        resolved.abiFacts = std::move(output.abiFacts);
        return resolved;
    }

public:
    Impl() {
        storage();
        sources.reserve(64);
    }
    HostedModule add(std::shared_ptr<const SourceText> source) {
        if (finished || failed || graphComplete || !source || sources.size() >= 64)
            invalidResolution();
        try {
            // Aurora charges the source against its byte limits, then lexes,
            // parses and admits it and ingests it as the next module; only its
            // header name and diagnostics cross back.
            hosted_abi::ResolverSourceInput input;
            input.source = span(source->text);
            const auto index = aurora_hosted_resolver_append_source(owner.data(), &input);
            if (index == -2)
                throw Error("module file exceeds 1048576 bytes");
            if (index == -3)
                throw Error("module graph exceeds 4194304 bytes");
            storage();
            hosted_abi::ParserSourceInput parse;
            parse.source = input.source;
            parse.configuration = admission;
            wire::SourceResult result;
            aurora_hosted_parser_source(owner.arena(), &parse, &result);
            rejectSource(source, result);
            const std::array<const void *, 2> roots{owner.data(), owner.arena()};
            const auto base = aurora_hosted_resolver_ingest(roots.data());
            storage();
            if (index < 0 || sizeValue(index) != sources.size() || base < 0)
                invalidResolution();
            HostedModule header;
            header.id = sources.size();
            header.moduleName = sourceName(source->text, result.name_begin, result.name_end);
            sources.push_back({std::move(source), header.moduleName});
            return header;
        } catch (...) {
            failed = true;
            throw;
        }
    }
    std::optional<HostedImport> nextImport(std::size_t root, std::size_t moduleRoots) {
        if (finished || failed || root >= sources.size() || (graphRoot && *graphRoot != root))
            invalidResolution();
        graphRoot = root;
        try {
            wire::WorkRow result;
            aurora_hosted_resolver_graph_step(
                owner.data(), static_cast<std::int64_t>(root), static_cast<std::int64_t>(moduleRoots), &result);
            storage();
            if (result.value0 == 0) {
                graphComplete = true;
                return std::nullopt;
            }
            if (result.value0 == 4)
                throw Error("module import depth exceeds 16");
            if (result.value0 == 5)
                throw Error("module graph exceeds 64 files");
            if (result.value1 < 0 || sizeValue(result.value1) >= sources.size())
                invalidResolution();
            const auto &unit = sources[sizeValue(result.value1)];
            if (result.value0 == 3)
                throw Error("module import cycle involving " + unit.moduleName);
            const auto name = sourceName(unit.source->text, result.value2, result.value3);
            if (name.empty())
                invalidResolution();
            switch (result.value0) {
            case 1:
                return HostedImport{name, sourceName(unit.source->text, result.value2, result.value3, true)};
            case 2:
                throw Error("duplicate import in " + unit.moduleName + ": " + name);
            case 6:
                throw Error("imports require an explicit --module-root");
            case 7:
                throw Error("invalid or excessive module name");
            case 8:
                throw Error("invalid module path component");
            case 9:
                if (result.value4 < 0 || sizeValue(result.value4) >= sources.size())
                    invalidResolution();
                throw Error("module header mismatch: expected " + name + ", got " +
                            sources[sizeValue(result.value4)].moduleName);
            case 10:
                throw Error("imported module requires an export module interface: " + name);
            default:
                invalidResolution();
            }
        } catch (...) {
            failed = true;
            owner.release();
            throw;
        }
    }
    HostedResolvedSource resolve(const std::vector<std::size_t> &order,
                                 std::size_t root,
                                 AnalysisMode mode,
                                 const EmissionRequest &request,
                                 bool sourceOrdered = false) {
        if (finished || failed || root >= sources.size() ||
            (sourceOrdered ? (!graphComplete || graphRoot != root) : (graphRoot || order.size() != sources.size())))
            invalidResolution();
        finished = true;
        // The direct API may outlive this call. Release its sole armed native
        // owner on earlier failures; after lowering the pipeline consumes it.
        // Releasing an inactive owner is harmless.
        struct Release {
            SessionOwner &owner;
            ~Release() {
                owner.release();
            }
        } release{owner};
        owner.releaseArena();
        if (!sourceOrdered) {
            std::vector<bool> seen(sources.size());
            std::map<std::string, std::size_t> names;
            for (std::size_t i = 0; i < sources.size(); ++i)
                if (!names.emplace(sources[i].moduleName, i).second)
                    invalidResolution();
            std::int64_t nextScope = 1;
            for (std::size_t ordinal = 0; ordinal < order.size(); ++ordinal) {
                const auto index = order[ordinal];
                if (index >= sources.size() || seen[index])
                    invalidResolution();
                seen[index] = true;
                hosted_abi::ResolverOrderInput input;
                input.module = static_cast<std::int64_t>(index);
                input.order = static_cast<std::int64_t>(ordinal);
                input.scope = index == root ? 0 : nextScope++;
                input.root = index == root;
                if (!aurora_hosted_resolver_order_module(owner.data(), &input)) {
                    storage();
                    invalidResolution();
                }
            }
        }
        // Aurora binds any import the graph walk left unbound before resolving.
        const auto result = aurora_hosted_resolver_run(owner.data());
        storage();
        const auto final = status();
        if (final.diagnostic != SemanticError::none)
            reject();
        if (result != 0 || final.node != -1 || final.first != -1 || final.second != -1)
            invalidResolution();
        try {
            return lower(mode, request);
        } catch (const Error &error) {
            throw error.withDefaultCode(DiagnosticCode::Semantic);
        }
    }
};
HostedResolution::HostedResolution() : implementation(std::make_unique<Impl>()) {
}
HostedResolution::~HostedResolution() = default;
HostedModule HostedResolution::add(std::shared_ptr<const SourceText> source) {
    return implementation->add(std::move(source));
}
std::optional<HostedImport> HostedResolution::nextImport(std::size_t root, std::size_t moduleRoots) {
    return implementation->nextImport(root, moduleRoots);
}
HostedResolvedSource HostedResolution::resolve(std::size_t root, AnalysisMode mode, const EmissionRequest &request) {
    return implementation->resolve({}, root, mode, request, true);
}
HostedResolvedSource HostedResolution::resolve(const std::vector<std::size_t> &order,
                                               std::size_t root,
                                               AnalysisMode mode,
                                               const EmissionRequest &request) {
    return implementation->resolve(order, root, mode, request);
}
} // namespace aurora
