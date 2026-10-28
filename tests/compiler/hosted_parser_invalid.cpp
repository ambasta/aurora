// Forged Aurora resolver and lowering results through the production host
// adapters, which are linked without the generated frontend: every malformed
// copied report must fail closed and release each owner exactly once.
#include "hosted_resolver.hpp"
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <iostream>
#include <limits>
#include <optional>
#include <stdexcept>
#include <string>

namespace {
using aurora::DiagnosticCode;
using aurora::hosted_abi::compiler_parser::TypeKind;
void *arenaAddress = nullptr;
std::uint64_t arenaRegion = 0;
constexpr std::uint64_t arenaCanary = 0x746970656172656eULL;
int created = 0, parsed = 0, released = 0;
bool throwingAdmission = false;
namespace Resolution = aurora::hosted_abi::compiler_resolver;
Resolution::SessionStatus resolutionStatus;
Resolution::SourceResult admission{};
void *sessionAddress = nullptr;
std::uint64_t sessionRegion = 0;
constexpr std::uint64_t sessionCanary = 0x7265736f6c766564ULL;
int sessionsCreated = 0, sessionsReleased = 0, transferred = 0, reports = 0;
bool allocationOnIngest = false;
std::int64_t sourceBytes = 0;
// The forged rendered diagnostic and an optional header change after its first chunk.
Resolution::Report forgedReport{};
std::string forgedMessage;
std::function<void(Resolution::Report &)> laterChunk;
namespace Lowering = aurora::hosted_abi::compiler_lowering;
Lowering::LoweringResult loweringResult{};
int loweringBegun = 0, loweringRun = 0;
bool loweringAllocation = false;
std::size_t cases = 0;
void require(bool value, const std::string &message) {
    if (!value)
        throw std::runtime_error(message);
}
void forge(std::int64_t family, std::string message, std::int64_t begin, std::int64_t end) {
    forgedReport = {};
    forgedReport.family = family;
    forgedReport.begin = begin;
    forgedReport.begin_line = forgedReport.end_line = 1;
    forgedReport.begin_column = begin + 1;
    forgedReport.end = end;
    forgedReport.end_column = end + 1;
    forgedMessage = std::move(message);
    laterChunk = nullptr;
}
std::shared_ptr<const aurora::SourceText> resolutionFixture() {
    require(!sessionAddress, "previous forged resolution retained its Session");
    throwingAdmission = allocationOnIngest = loweringAllocation = false;
    created = parsed = released = 0;
    arenaAddress = nullptr;
    auto source =
        std::make_shared<const aurora::SourceText>("resolved-record.au", "module forged;auto f()->i64{return 1;}");
    sourceBytes = static_cast<std::int64_t>(source->text.size());
    admission = {};
    admission.field_type = TypeKind::invalid;
    admission.name_begin = 7;
    admission.name_end = 13;
    resolutionStatus = {Resolution::StorageStatus::none, Resolution::SemanticError::none, -1, -1, -1};
    sessionsCreated = sessionsReleased = transferred = reports = 0;
    const auto function = static_cast<std::int64_t>(source->text.find("f()"));
    forge(3001, "at most six parameters supported", function, function + 1);
    loweringResult = {
        Lowering::LoweringStatus::semantic_failure, Lowering::LoweringError::function_parameter_limit, 0, -1};
    loweringBegun = loweringRun = 0;
    return source;
}
// Resolves the fixture, mutated once its source is admitted, and returns the
// diagnostic it reports.
std::optional<aurora::Diagnostic> resolveFixture(const std::shared_ptr<const aurora::SourceText> &source,
                                                 const std::function<void()> &mutate = [] {}) {
    const aurora::EmissionRequest abiFacts{.emit = true, .abiFacts = true};
    try {
        aurora::HostedResolution resolution;
        const auto module = resolution.add(source);
        require(module.id == 0 && module.moduleName == "forged", "session ingestion lost the copied module header");
        mutate();
        static_cast<void>(resolution.resolve({module.id}, module.id, aurora::AnalysisMode::Check, abiFacts));
    } catch (const aurora::Error &error) {
        return error.diagnostic;
    }
    return std::nullopt;
}
void resolutionControls() {
    auto source = resolutionFixture();
    // A 900-byte message crosses three copied chunks.
    forgedMessage += ": " + std::string(866, 'x');
    auto diagnostic = resolveFixture(source);
    require(diagnostic && diagnostic->code == DiagnosticCode::Semantic &&
                diagnostic->message == "at most six parameters supported: " + std::string(866, 'x') &&
                diagnostic->severity == aurora::DiagnosticSeverity::Error && diagnostic->span.source == source &&
                diagnostic->span.begin.offset == source->text.find("f()") &&
                diagnostic->span.end.offset == diagnostic->span.begin.offset + 1 && sessionsCreated == 1 &&
                sessionsReleased == 1 && transferred == 1 && created == 1 && parsed == 1 && released == 1 &&
                loweringBegun == 1 && loweringRun == 1 && reports == 3,
            "rendered lowering report lost its message, source, span or exact cleanup");
    ++cases;

    source = resolutionFixture();
    resolutionStatus.diagnostic = Resolution::SemanticError::unknown_function;
    forge(4001, "unknown function 'g' in defining module forged", -1, -1);
    forgedReport.source = -1;
    diagnostic = resolveFixture(source);
    require(diagnostic && diagnostic->code == DiagnosticCode::Module && !diagnostic->span.source &&
                diagnostic->message == "unknown function 'g' in defining module forged" && loweringRun == 0 &&
                sessionsReleased == 1,
            "rendered resolver report lost its code, message or cleanup");
    ++cases;

    source = resolutionFixture();
    admission.grammar = aurora::hosted_parser::Status::expected_semicolon;
    forge(2001, "expected ';' (found 'f')", 19, 20);
    diagnostic = resolveFixture(source);
    require(diagnostic && diagnostic->code == DiagnosticCode::UnexpectedToken &&
                diagnostic->message == "expected ';' (found 'f')" && diagnostic->span.begin.offset == 19 &&
                transferred == 0 && sessionsReleased == 1 && released == 1,
            "rendered source rejection lost its message, span or cleanup");
    ++cases;

    const auto reject = [&](const char *label, const std::function<void()> &mutate) {
        source = resolutionFixture();
        diagnostic = resolveFixture(source, mutate);
        require(diagnostic && diagnostic->code == DiagnosticCode::Internal && sessionsCreated == 1 &&
                    sessionsReleased == 1 && released == 1,
                std::string(label) + ": unsafe report escaped or released an owner twice");
        ++cases;
    };
    reject("negative report size", [] {
        forgedReport.byteCount = -1;
    });
    reject("unknown diagnostic code", [] {
        forgedReport.family = 1234;
    });
    reject("unknown severity", [] {
        forgedReport.warning = 2;
    });
    reject("report source outside the graph", [] {
        forgedReport.source = 1;
    });
    reject("report span outside its source", [] {
        forgedReport.end = sourceBytes + 1;
    });
    reject("reversed report span", [] {
        forgedReport.end = forgedReport.begin - 1;
    });
    reject("report column precedes its line", [] {
        forgedReport.begin_column = forgedReport.begin + 2;
    });
    reject("report header changes between chunks", [] {
        forgedMessage = std::string(400, 'x');
        laterChunk = [](Resolution::Report &report) {
            report.end = report.begin;
        };
    });
    reject("unknown storage status", [] {
        resolutionStatus.storage = static_cast<Resolution::StorageStatus>(99);
    });
    reject("successful resolver status carries a node", [] {
        resolutionStatus.node = 0;
    });
    reject("successful resolver status carries first detail", [] {
        resolutionStatus.first = 0;
    });
    reject("successful resolver status carries second detail", [] {
        resolutionStatus.second = 0;
    });
    reject("unknown lowering status", [] {
        loweringResult.result_status = static_cast<Lowering::LoweringStatus>(99);
    });
    reject("failure lacks a reason", [] {
        loweringResult.result_reason = Lowering::LoweringError::none;
    });
    reject("failure publishes a module root", [] {
        loweringResult.root_row = 16;
    });
    reject("failure omits its diagnostic root", [] {
        loweringResult.diagnostic_row = -1;
    });
    reject("success carries a failure reason", [] {
        loweringResult.result_status = Lowering::LoweringStatus::success;
    });
    reject("success publishes no module root", [] {
        loweringResult.result_status = Lowering::LoweringStatus::success;
        loweringResult.result_reason = Lowering::LoweringError::none;
    });
    reject("storage failure lacks an allocation status", [] {
        loweringResult.result_status = Lowering::LoweringStatus::storage_failure;
    });
    reject("native lowering allocation preserves owner cleanup", [] {
        loweringAllocation = true;
    });

    for (const bool duringIngest : {false, true}) {
        source = resolutionFixture();
        allocationOnIngest = duringIngest;
        throwingAdmission = !duringIngest;
        bool rejected = false;
        try {
            aurora::HostedResolution resolution;
            static_cast<void>(resolution.add(source));
        } catch (const aurora::Error &error) {
            rejected = duringIngest && error.diagnostic.code == DiagnosticCode::Internal &&
                       error.diagnostic.message == "hosted module resolution allocation failed";
        } catch (const std::runtime_error &error) {
            rejected = !duringIngest && std::string(error.what()) == "injected admission failure";
        }
        require(rejected && sessionsReleased == 1 && released == 1 && transferred == int(duringIngest) &&
                    loweringRun == 0,
                "failure while admitting or ingesting a source did not release Session and arena once");
        ++cases;
    }
}
// The forged report's chunk at offset.
void copyReport(std::int64_t offset, void *output) {
    ++reports;
    auto report = forgedReport;
    if (report.byteCount >= 0) {
        const auto size = static_cast<std::int64_t>(forgedMessage.size());
        report.byteCount = std::min<std::int64_t>(384, std::max<std::int64_t>(0, size - offset));
        std::memcpy(report.payload.data(), forgedMessage.data() + offset, static_cast<std::size_t>(report.byteCount));
    }
    if (offset && laterChunk)
        laterChunk(report);
    std::memcpy(output, &report, sizeof(report));
}
} // namespace
// No forged report in this fixture may reach the compilation pipeline: every
// rejection here precedes it, and it never manufactures accepted durable IR.
[[noreturn]] static void unexpectedPipelineEntry() noexcept {
    std::fputs("forged projection unexpectedly reached the compilation pipeline\n", stderr);
    std::abort();
}
extern "C" void aurora_hosted_pipeline_run(const void *, void *) noexcept {
    unexpectedPipelineEntry();
}
extern "C" void aurora_hosted_pipeline_release(void *) noexcept {
    unexpectedPipelineEntry();
}
extern "C" void aurora_hosted_pipeline_report(const void *, void *) noexcept {
    unexpectedPipelineEntry();
}
extern "C" void aurora_hosted_pipeline_lint(const void *, std::int64_t, std::int64_t, void *) noexcept {
    unexpectedPipelineEntry();
}
extern "C" void aurora_hosted_pipeline_chunk(const void *, std::int64_t, std::int64_t, void *) noexcept {
    unexpectedPipelineEntry();
}
extern "C" void aurora_hosted_catalog_summary(void *output) noexcept {
    // Admission inputs only; this fixture seeds no catalog.
    aurora::hosted_abi::compiler_catalog::Summary summary{};
    summary.serviceGroups = 4295033150;
    std::memcpy(output, &summary, sizeof(summary));
}
extern "C" void aurora_hosted_parser_create(const void *input, void *output) {
    const auto &value = *static_cast<const aurora::hosted_abi::ParserCreate *>(input);
    require(value.region != 0 && value.capacity == 0, "adapter did not request empty arena with live region");
    arenaAddress = output;
    arenaRegion = value.region;
    // Exercise the generated arena's last word and the enclosing owner base.
    static_assert(aurora::hosted_abi::arenaBytes >= sizeof(arenaCanary));
    std::memcpy(static_cast<unsigned char *>(output) + aurora::hosted_abi::arenaBytes - sizeof(arenaCanary),
                &arenaCanary,
                sizeof(arenaCanary));
    ++created;
}
// Resolution sources admit as the forged module header or its forged rejection.
extern "C" void aurora_hosted_parser_source(void *arena, const void *input, void *output) {
    require(arena == arenaAddress, "source admission changed the arena address");
    const auto &value = *static_cast<const aurora::hosted_abi::ParserSourceInput *>(input);
    const auto &configuration = value.configuration;
    require(value.source.kind == 0 && value.source.start == 0 && value.source.length == sourceBytes &&
                configuration.scalar_array_limit == 64 && configuration.byte_array_limit == 512 &&
                configuration.service_groups == 4295033150 && configuration.console_mask == 1 &&
                configuration.display_mask == 2 && configuration.event_mask == 4,
            "source admission changed its borrowed span or canonical layout/service configuration");
    ++parsed;
    if (throwingAdmission)
        throw std::runtime_error("injected admission failure");
    std::memcpy(output, &admission, sizeof(admission));
}
extern "C" void aurora_hosted_resolver_source_report(const void *input, void *output) {
    const auto &value = *static_cast<const aurora::hosted_abi::ResolverSourceReport *>(input);
    require(value.source.length == sourceBytes && value.result.grammar == admission.grammar &&
                value.stop == aurora::hosted_parser::Stop::module_definition,
            "source report changed its borrowed source, result or stop");
    copyReport(value.offset, output);
}
extern "C" void aurora_hosted_resolver_name_chunk(const void *input, void *output) {
    const auto &value = *static_cast<const aurora::hosted_abi::ResolverNameInput *>(input);
    require(value.source.length == sourceBytes && value.begin == 7 && value.end == 13 && value.offset == 0,
            "module name read changed its borrowed source range");
    Resolution::LinkageChunk chunk{};
    chunk.byteCount = value.end - value.begin;
    std::memcpy(chunk.payload.data(), value.source.backing + value.begin, static_cast<std::size_t>(chunk.byteCount));
    std::memcpy(output, &chunk, sizeof(chunk));
}
extern "C" void aurora_hosted_parser_release(void *owner) {
    const auto &record = *static_cast<const aurora::hosted_abi::ParserRelease *>(owner);
    require(record.arena.storage.data() == arenaAddress, "release did not receive the enclosing owner");
    std::uint64_t canary = 0;
    std::memcpy(&canary, record.arena.storage.data() + record.arena.storage.size() - sizeof(canary), sizeof(canary));
    require(record.region == arenaRegion && canary == arenaCanary, "owner region or arena boundary was corrupted");
    ++released;
}

namespace {
void checkSession(const void *address) {
    require(address == sessionAddress && sessionsCreated == sessionsReleased + 1,
            "resolver used an inactive or copied Session slot");
    std::uint64_t value = 0;
    std::memcpy(&value,
                static_cast<const unsigned char *>(address) + aurora::hosted_abi::sessionBytes - sizeof(value),
                sizeof(value));
    require(value == sessionCanary, "Session owner boundary was corrupted");
}
void armSession(void *address) {
    sessionAddress = address;
    static_assert(aurora::hosted_abi::sessionBytes >= sizeof(sessionCanary));
    std::memcpy(static_cast<unsigned char *>(address) + aurora::hosted_abi::sessionBytes - sizeof(sessionCanary),
                &sessionCanary,
                sizeof(sessionCanary));
}
} // namespace
extern "C" void aurora_hosted_resolver_create(const void *input, void *output) {
    const auto &record = *static_cast<const aurora::hosted_abi::ResolverCreate *>(input);
    require(record.region != 0 && !sessionAddress, "resolver create did not receive a fresh same-region slot");
    sessionRegion = record.region;
    ++sessionsCreated;
    armSession(output);
}
extern "C" std::int64_t aurora_hosted_resolver_ingest(const void *input) {
    const auto *roots = static_cast<const void *const *>(input);
    checkSession(roots[0]);
    std::uint64_t canary = 0;
    std::memcpy(&canary,
                static_cast<const unsigned char *>(roots[1]) + aurora::hosted_abi::arenaBytes - sizeof(canary),
                sizeof(canary));
    require(roots[1] == arenaAddress && created == released + 1 && canary == arenaCanary,
            "ingest did not borrow the live parser arena");
    ++transferred;
    if (allocationOnIngest) {
        resolutionStatus.storage = Resolution::StorageStatus::allocation;
        return -1;
    }
    return 0;
}
extern "C" void aurora_hosted_resolver_release(void *input) {
    const auto &record = *static_cast<const aurora::hosted_abi::ResolverRelease *>(input);
    checkSession(record.session.storage.data());
    require(record.region == sessionRegion && created == released,
            "Session-only release retained a live parsed owner or lost its region");
    ++sessionsReleased;
    sessionAddress = nullptr;
}
extern "C" std::int64_t aurora_hosted_resolver_append_source(void *session, const void *input) {
    checkSession(session);
    const auto &record = *static_cast<const aurora::hosted_abi::ResolverSourceInput *>(input);
    require(record.source.kind == 0 && record.source.start == 0 && record.source.length == sourceBytes &&
                record.source.reserved == std::array<std::uint64_t, 3>{},
            "source ingestion changed its borrowed contiguous span");
    return 0;
}
extern "C" std::int64_t aurora_hosted_resolver_order_module(void *session, const void *input) {
    checkSession(session);
    const auto &record = *static_cast<const aurora::hosted_abi::ResolverOrderInput *>(input);
    require(record.module == 0 && record.order == 0 && record.scope == 0 && record.root == 1,
            "resolved root/order/scope inputs differ");
    return 1;
}
extern "C" void aurora_hosted_resolver_graph_step(void *, std::int64_t, std::int64_t, void *) {
    throw std::runtime_error("explicit-order resolution fixture acquired graph traversal");
}
extern "C" std::int64_t aurora_hosted_resolver_run(void *session) {
    checkSession(session);
    return 0;
}
extern "C" void aurora_hosted_resolver_status(const void *session, void *output) {
    checkSession(session);
    std::memcpy(output, &resolutionStatus, sizeof(resolutionStatus));
}
extern "C" void aurora_hosted_resolver_report(const void *session, std::int64_t offset, void *output) {
    checkSession(session);
    copyReport(offset, output);
}

// The two lowering endpoints. Only the fixed failure report above is
// supplied; valid typed modules must come from the real native fixture.
extern "C" std::int64_t aurora_hosted_lowering_begin(void *session, const void *input) noexcept {
    checkSession(session);
    const auto &configuration = static_cast<const aurora::hosted_abi::LoweringBeginInput *>(input)->configuration;
    require(configuration.byteLeaves == aurora::maximumCopiedByteLeaves &&
                configuration.nonByteLeaves == aurora::maximumCopiedNonByteLeaves &&
                configuration.totalLeaves == aurora::maximumCopiedClassLeaves &&
                configuration.copiedBytes == aurora::maximumCopiedClassBytes &&
                configuration.byteArrayLength == aurora::maximumClassByteArrayLength &&
                configuration.scalarArrayLength == aurora::maximumClassScalarArrayLength &&
                configuration.analysisMode == 0,
            "lowering received a changed copied configuration");
    ++loweringBegun;
    return 1;
}
extern "C" void aurora_hosted_lowering_run(void *session, void *output) noexcept {
    checkSession(session);
    ++loweringRun;
    auto result = loweringResult;
    if (loweringAllocation) {
        resolutionStatus.storage = Resolution::StorageStatus::allocation;
        result = {Lowering::LoweringStatus::storage_failure, Lowering::LoweringError::none, -1, -1};
    }
    std::memcpy(output, &result, sizeof(result));
}

int main() {
    try {
        resolutionControls();
        std::cout << "hosted resolver representation controls: " << cases << " passed\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
