// Trusted transport boundary for one Aurora-owned resolution session. The host
// retains source snapshots and file-opening authority, never semantic lookup;
// Aurora loads, resolves and lowers each source and renders every diagnostic
// the session reports.
#include "hosted_resolver.hpp"
#include "../runtime/hosted_bytes.hpp"
#include <array>
#include <limits>

namespace aurora {
namespace {
namespace wire = hosted_abi::compiler_resolver;
[[noreturn]] void invalidResolution() {
    throw Error(DiagnosticCode::Internal, "invalid hosted resolution result");
}
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
    result.backing = text.data();
    result.length = static_cast<std::int64_t>(text.size());
    return result;
}
// The trivia-free spelling of text[begin, end), as Aurora names modules, or
// the relative path Aurora maps that import name to.
std::string sourceName(const std::string &text, std::int64_t begin, std::int64_t end, bool path) {
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
                            hosted_abi::compiler_parser::Stop stop) {
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

class HostedResolution::Impl {
    SessionOwner owner;
    std::vector<std::shared_ptr<const SourceText>> sources;
    bool finished = false, failed = false;
    std::optional<std::size_t> graphRoot;
    bool graphComplete = false;
    // The source snapshot a report's module index names.
    std::shared_ptr<const SourceText> module(std::int64_t index) const {
        if (index < 0 || static_cast<std::uint64_t>(index) >= sources.size())
            invalidResolution();
        return sources[static_cast<std::size_t>(index)];
    }
    // The rejection the Session latched, as Aurora rendered it.
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
    PipelineOutput lower(AnalysisMode mode, const EmissionRequest &request) {
        // Lowering publishes its limits, scalar, service and layout prelude itself.
        if (aurora_hosted_lowering_begin(owner.data(), mode == AnalysisMode::Lint ? 1 : 0) != 1)
            reject();
        hosted_abi::compiler_lowering::LoweringResult result;
        aurora_hosted_lowering_run(owner.data(), &result);
        if (result.result_status != hosted_abi::compiler_lowering::LoweringStatus::success)
            reject();
        // The rest of the compilation is one Aurora call that consumes the Session.
        return runHostedPipeline(owner.regionId(),
                                 owner.consume(),
                                 result.root_row,
                                 result.diagnostic_row,
                                 request,
                                 [this](std::int64_t index) {
                                     return module(index);
                                 });
    }

public:
    HostedModule add(std::shared_ptr<const SourceText> source) {
        if (finished || failed || graphComplete || !source)
            invalidResolution();
        try {
            // Aurora lexes, parses and admits the source, charges it against
            // its byte limits and ingests it as the next module.
            sources.push_back(source);
            hosted_abi::ParserSourceInput parse;
            parse.source = span(source->text);
            hosted_abi::ResolverSourceInput input;
            input.source = parse.source;
            aurora_hosted_parser_source(owner.arena(), &parse, &input.result);
            if (aurora_hosted_resolver_append_source(owner.data(), &input) < 0)
                reject();
            const std::array<const void *, 2> roots{owner.data(), owner.arena()};
            if (aurora_hosted_resolver_ingest(roots.data()) < 0)
                reject();
            return {sources.size() - 1};
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
            wire::WorkRow step;
            aurora_hosted_resolver_graph_step(
                owner.data(), static_cast<std::int64_t>(root), static_cast<std::int64_t>(moduleRoots), &step);
            if (step.value0 == 0) {
                graphComplete = true;
                return std::nullopt;
            }
            if (step.value0 != 1)
                reject();
            const auto &text = module(step.value1)->text;
            return HostedImport{sourceName(text, step.value2, step.value3, false),
                                sourceName(text, step.value2, step.value3, true)};
        } catch (...) {
            failed = true;
            owner.release();
            throw;
        }
    }
    PipelineOutput resolve(const std::vector<std::size_t> &order,
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
        std::int64_t nextScope = 1;
        for (std::size_t ordinal = 0; !sourceOrdered && ordinal < order.size(); ++ordinal) {
            hosted_abi::ResolverOrderInput input;
            input.module = static_cast<std::int64_t>(order[ordinal]);
            input.order = static_cast<std::int64_t>(ordinal);
            input.scope = order[ordinal] == root ? 0 : nextScope++;
            input.root = order[ordinal] == root;
            if (!aurora_hosted_resolver_order_module(owner.data(), &input))
                reject();
        }
        // Aurora binds any import the graph walk left unbound before resolving.
        if (aurora_hosted_resolver_run(owner.data()) != 0)
            reject();
        return lower(mode, request);
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
PipelineOutput HostedResolution::resolve(std::size_t root, AnalysisMode mode, const EmissionRequest &request) {
    return implementation->resolve({}, root, mode, request, true);
}
PipelineOutput HostedResolution::resolve(const std::vector<std::size_t> &order,
                                         std::size_t root,
                                         AnalysisMode mode,
                                         const EmissionRequest &request) {
    return implementation->resolve(order, root, mode, request);
}
} // namespace aurora
