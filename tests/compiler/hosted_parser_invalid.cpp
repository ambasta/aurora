// Forged Aurora resolver and lowering results through the production host
// adapters, which are linked without the generated frontend: every malformed
// copied report must fail closed and release each owner exactly once.
#include "hosted_graph.hpp"
#include "hosted_resolver.hpp"
#include "../../runtime/bytes_abi.hpp"
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <iostream>
#include <limits>
#include <optional>
#include <tuple>
#include <stdexcept>
#include <utility>
#include <vector>

namespace {
using aurora::DiagnosticCode;
using aurora::hosted_abi::compiler_parser::NodeKind;
using aurora::hosted_abi::compiler_parser::SyntaxKind;
using aurora::hosted_abi::compiler_parser::TypeKind;
void *arenaAddress = nullptr;
std::uint64_t arenaRegion = 0;
constexpr std::uint64_t arenaCanary = 0x746970656172656eULL;
int created = 0, parsed = 0, released = 0;
bool throwingAdmission = false;
namespace Resolution = aurora::hosted_abi::compiler_resolver;
std::vector<Resolution::SyntaxRow> resolutionSyntax;
std::vector<Resolution::MetaRow> resolutionMetadata;
std::vector<Resolution::ResolvedRow> resolutionDecorations;
Resolution::SessionStatus resolutionStatus;
void *sessionAddress = nullptr;
std::uint64_t sessionRegion = 0;
// Charge copied fixture rows to the real host region so Projection's payload
// bound is exercised. This owner is the stub's own runtime allocation, never an
// interpretation or a copy of the generated opaque Session descriptor.
aurora::hosted::bytes::NativeOwner sessionPayload;
constexpr std::uint64_t sessionCanary = 0x7265736f6c766564ULL;
int sessionsCreated = 0, sessionsReleased = 0, transferred = 0, projectionThrow = 0;
bool resolverRunning = false, allocationOnIngest = false;
std::int64_t linkageChunkSize = 1;
std::int64_t reportedSyntax = 0, reportedMetadata = 0, reportedDecorations = 0, sourceBytes = 0;
namespace Lowering = aurora::hosted_abi::compiler_lowering;
Lowering::LoweringResult loweringResult{};
Lowering::OutputRow loweringReport{};
std::array<Lowering::OperandRow, 3> loweringOperands{};
std::int64_t reportedOutputs = 1, reportedOperands = 3;
int loweringBegun = 0, loweringRun = 0, loweringOutputReads = 0, loweringOperandReads = 0;
bool loweringAllocation = false;
std::size_t cases = 0;
void require(bool value, const std::string &message) {
    if (!value)
        throw std::runtime_error(message);
}
void reset() {
    throwingAdmission = false;
    created = parsed = released = 0;
    arenaAddress = nullptr;
}

Resolution::MetaRow resolutionMeta(Resolution::MetaTag tag) {
    Resolution::MetaRow value;
    value.tag = tag;
    value.value0 = value.value1 = value.value2 = value.value3 = value.value4 = value.value5 = value.value6 =
        value.value7 = value.value8 = value.value9 = value.value10 = value.value11 = value.value12 = value.value13 =
            value.value14 = -1;
    return value;
}
Resolution::SyntaxRow resolutionNode(Resolution::SyntaxTag tag) {
    Resolution::SyntaxRow value;
    value.tag = tag;
    value.value0 = value.value1 = value.value2 = value.value3 = value.value4 = value.value5 = value.value6 =
        value.value7 = value.value8 = value.value9 = value.value10 = value.value11 = -1;
    return value;
}
std::shared_ptr<const aurora::SourceText> resolutionFixture() {
    require(!sessionAddress && sessionPayload.allocation == 0, "previous forged resolution retained its payload owner");
    reset();
    auto source =
        std::make_shared<const aurora::SourceText>("resolved-record.au", "module forged;auto f()->i64{return 1;}");
    resolutionSyntax.assign(8, resolutionNode(Resolution::SyntaxTag::declaration));
    resolutionSyntax[0] = resolutionNode(Resolution::SyntaxTag::expression);
    resolutionSyntax[0].expression_tag = NodeKind::literal;
    resolutionSyntax[0].value0 = 3;
    resolutionSyntax[1] = resolutionNode(Resolution::SyntaxTag::type);
    resolutionSyntax[1].type_tag = TypeKind::i64_type;
    resolutionSyntax[2].declaration_tag = SyntaxKind::preamble;
    resolutionSyntax[3].declaration_tag = SyntaxKind::return_value;
    resolutionSyntax[3].value0 = 2;
    resolutionSyntax[3].value3 = 0;
    resolutionSyntax[4].declaration_tag = SyntaxKind::block;
    resolutionSyntax[4].value7 = 3;
    resolutionSyntax[5].declaration_tag = SyntaxKind::function;
    resolutionSyntax[5].value0 = 1;
    resolutionSyntax[5].value5 = 1;
    resolutionSyntax[5].value7 = 4;
    resolutionSyntax[5].value9 = 0;
    resolutionSyntax[6].declaration_tag = SyntaxKind::declaration;
    resolutionSyntax[7].declaration_tag = SyntaxKind::module_definition;
    resolutionMetadata.assign(9, resolutionMeta(Resolution::MetaTag::invalid));
    auto &module = resolutionMetadata[0];
    module.tag = Resolution::MetaTag::module_source;
    module.value0 = 0;
    module.value1 = static_cast<std::int64_t>(source->text.size());
    module.value2 = 0;
    module.value3 = 1;
    module.value4 = 1;
    module.value5 = 0;
    module.value6 = 1;
    module.value7 = 1;
    module.value8 = 2;
    module.value9 = 6;
    module.value11 = 0;
    // The one-line source's tokens f, return and 1 are ordinals 4, 10 and 11.
    for (const auto &[reference, ordinal, spelling] :
         {std::tuple{1, 4, "f()"}, std::tuple{2, 10, "return"}, std::tuple{3, 11, "1;"}}) {
        auto &value = resolutionMetadata[reference];
        const auto begin = static_cast<std::int64_t>(source->text.find(spelling));
        const auto end = begin + (ordinal == 10 ? 6 : 1);
        value.tag = Resolution::MetaTag::source_reference;
        value.value0 = 0;
        value.value1 = begin;
        value.value2 = end;
        value.value3 = 1;
        value.value4 = begin + 1;
        value.value5 = ordinal;
        value.value6 = 0;
        value.value7 = 1;
        value.value8 = end + 1;
        value.value9 = 0;
    }
    resolutionMetadata[4].tag = Resolution::MetaTag::concrete_type;
    resolutionMetadata[4].concrete_tag = Resolution::ResolvedTypeKind::i64_value;
    auto &symbol = resolutionMetadata[5];
    symbol.tag = Resolution::MetaTag::symbol;
    symbol.declaration_tag = Resolution::DeclarationKind::function;
    symbol.native_tag = Resolution::NativeMode::root_entry;
    symbol.value0 = 8;
    symbol.value1 = 0;
    symbol.value4 = 1;
    symbol.value5 = 5;
    symbol.value6 = 0;
    resolutionMetadata[6].tag = Resolution::MetaTag::link;
    resolutionMetadata[6].value0 = 5;
    resolutionMetadata[7].tag = Resolution::MetaTag::context;
    resolutionMetadata[7].value0 = 1;
    resolutionMetadata[7].value1 = 6;
    Resolution::ResolvedRow decoration;
    decoration.operation_tag = Resolution::ResolvedOperation::unchanged;
    decoration.value0 = decoration.value1 = decoration.value2 = decoration.value3 = decoration.value4 =
        decoration.value5 = decoration.value6 = decoration.value7 = -1;
    resolutionDecorations.assign(8, decoration);
    resolutionDecorations[1].value2 = 4;
    resolutionStatus = {Resolution::StorageStatus::none, Resolution::SemanticError::none, -1, -1, -1};
    sessionAddress = nullptr;
    sessionsCreated = sessionsReleased = transferred = projectionThrow = 0;
    resolverRunning = allocationOnIngest = false;
    reportedSyntax = 8;
    reportedMetadata = 8;
    reportedDecorations = 8;
    sourceBytes = static_cast<std::int64_t>(source->text.size());
    resolutionMetadata[8].tag = Resolution::MetaTag::source_reference;
    resolutionMetadata[8].value0 = -1;
    resolutionMetadata[8].value1 = resolutionMetadata[1].value1;
    resolutionMetadata[8].value2 = resolutionMetadata[1].value2;
    resolutionMetadata[8].value9 = 5;
    reportedMetadata = 9;
    linkageChunkSize = 1;
    loweringResult = {
        Lowering::LoweringStatus::semantic_failure, Lowering::LoweringError::function_parameter_limit, 0, -1};
    loweringReport = {};
    loweringReport.recordKind = Lowering::RecordKind::DiagnosticPayload;
    loweringReport.operandBegin = 0;
    loweringReport.operandCount = 3;
    loweringOperands = {};
    loweringOperands[0].operandRole = Lowering::OperandRole::DiagnosticSourceRef;
    loweringOperands[0].signedValue = 1;
    loweringOperands[1].operandRole = loweringOperands[2].operandRole = Lowering::OperandRole::NoDiagnosticValue;
    reportedOutputs = 1;
    reportedOperands = 3;
    loweringBegun = loweringRun = loweringOutputReads = loweringOperandReads = 0;
    loweringAllocation = false;
    return source;
}
void resolutionControls() {
    auto source = resolutionFixture();
    // This host-only fixture publishes a deliberately forged failure report.
    // It never claims that stubbed native lowering produced a valid module.
    std::optional<aurora::Diagnostic> diagnostic;
    {
        aurora::HostedResolution resolution;
        const auto module = resolution.add(source);
        require(module.id == 0 && module.moduleName == "forged", "session ingestion lost the copied module header");
        try {
            static_cast<void>(resolution.resolve({module.id}, module.id, aurora::AnalysisMode::Check, true));
        } catch (const aurora::Error &error) {
            diagnostic = error.diagnostic;
        }
        require(sessionsReleased == 1 && sessionPayload.allocation == 0,
                "failed lowering retained its Session until adapter destruction");
    }
    require(diagnostic && diagnostic->code == DiagnosticCode::Semantic &&
                diagnostic->message == "at most six parameters supported" && diagnostic->span.source == source &&
                diagnostic->span.begin.offset == source->text.find("f()") &&
                diagnostic->span.end.offset == diagnostic->span.begin.offset + 1 && sessionsCreated == 1 &&
                sessionsReleased == 1 && transferred == 1 && created == 1 && parsed == 1 && released == 1 &&
                loweringBegun == 1 && loweringRun == 1 && loweringOutputReads == 1 && loweringOperandReads == 3 &&
                sessionPayload.allocation == 0,
            "typed failure report lost source, bounded reads, configuration or exact cleanup");
    ++cases;
    const auto reject = [&](const char *label, const std::function<void()> &mutate, bool injected = false) {
        source = resolutionFixture();
        bool rejected = false;
        try {
            aurora::HostedResolution resolution;
            const auto module = resolution.add(source);
            mutate();
            static_cast<void>(resolution.resolve({module.id}, module.id, aurora::AnalysisMode::Check, true));
        } catch (const aurora::Error &error) {
            rejected = !injected && error.diagnostic.code == DiagnosticCode::Internal;
        } catch (const std::runtime_error &error) {
            rejected = injected && std::string(error.what()) == "injected resolved read failure";
        }
        require(rejected && sessionsCreated == 1 && sessionsReleased == 1 && transferred == 1 && released == 1 &&
                    sessionPayload.allocation == 0,
                std::string(label) + ": unsafe typed projection escaped or released an owner twice");
        ++cases;
    };
    reject("negative source byte count", [] {
        sourceBytes = -1;
    });
    reject("source byte count exceeds payload", [] {
        sourceBytes = std::numeric_limits<std::int64_t>::max();
    });
    reject("negative resolved syntax count", [] {
        reportedSyntax = -1;
    });
    reject("negative resolved metadata count", [] {
        reportedMetadata = -1;
    });
    reject("negative resolved decoration count", [] {
        reportedDecorations = -1;
    });
    reject("resolved syntax count exceeds payload", [] {
        reportedSyntax = std::numeric_limits<std::int64_t>::max();
    });
    reject("resolved metadata count exceeds payload", [] {
        reportedMetadata = std::numeric_limits<std::int64_t>::max();
    });
    reject("resolved decoration count exceeds payload", [] {
        reportedDecorations = std::numeric_limits<std::int64_t>::max();
    });
    reject("unknown storage status", [] {
        resolutionStatus.storage = static_cast<Resolution::StorageStatus>(99);
    });
    reject("unknown semantic diagnostic", [] {
        resolutionStatus.diagnostic = static_cast<Resolution::SemanticError>(999);
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
    reject("mismatched decoration count", [] {
        --reportedDecorations;
    });
    reject("ABI declaration has wrong syntax domain", [] {
        resolutionSyntax[5].tag = Resolution::SyntaxTag::expression;
    });
    reject("unknown native identity mode", [] {
        resolutionMetadata[5].native_tag = static_cast<Resolution::NativeMode>(99);
    });
    reject("missing immutable linkage cache", [] {
        resolutionMetadata[5].value0 = -1;
    });
    reject("linkage cache has another owner", [] {
        resolutionMetadata[8].value9 = 4;
    });
    reject("linkage cache escapes source bytes", [] {
        resolutionMetadata[8].value2 = sourceBytes + 1;
    });
    for (const std::int64_t size : {-1, 0, 2, 513})
        reject("invalid copied linkage chunk extent", [=] {
            linkageChunkSize = size;
        });
    reject("symbol defining module outside graph", [] {
        resolutionMetadata[5].value1 = 1;
    });
    reject("output list cycle", [] {
        resolutionMetadata[6].value1 = 6;
    });
    reject("wrong output list tag", [] {
        resolutionMetadata[6].tag = Resolution::MetaTag::signature;
    });
    reject("output symbol outside metadata", [] {
        resolutionMetadata[6].value0 = 9;
    });
    reject("reversed sparse source span", [] {
        resolutionMetadata[1].value2 = resolutionMetadata[1].value1 - 1;
    });
    reject("sparse span outside source", [] {
        resolutionMetadata[1].value2 = sourceBytes + 1;
    });
    reject("sparse span wrong source", [] {
        resolutionMetadata[1].value0 = 1;
    });
    reject("sparse span invalid column", [] {
        resolutionMetadata[1].value4 = 0;
    });
    const auto typeReport = [] {
        loweringResult.result_reason = Lowering::LoweringError::type_mismatch;
        loweringOperands[1].operandRole = loweringOperands[2].operandRole = Lowering::OperandRole::DiagnosticTypeId;
        loweringOperands[1].signedValue = loweringOperands[2].signedValue = 4;
    };
    reject("diagnostic concrete type has wrong metadata domain", [&] {
        typeReport();
        resolutionMetadata[4].tag = Resolution::MetaTag::symbol;
    });
    reject("diagnostic concrete type outside metadata", [&] {
        typeReport();
        loweringOperands[1].signedValue = 9;
    });
    reject("diagnostic concrete type has unknown kind", [&] {
        typeReport();
        resolutionMetadata[4].concrete_tag = static_cast<Resolution::ResolvedTypeKind>(99);
    });
    // The projection no longer reads every syntax/decoration row to build an
    // AST. Exceptions are injected only on source views it still consumes.
    for (const int read : {1, 2})
        reject(
            "resolved copied-row read exception",
            [=] {
                projectionThrow = read;
            },
            true);

    reject("unknown lowering status", [] {
        loweringResult.result_status = static_cast<Lowering::LoweringStatus>(99);
    });
    reject("unknown lowering reason", [] {
        loweringResult.result_reason = static_cast<Lowering::LoweringError>(999);
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
    reject("negative typed output count", [] {
        reportedOutputs = -1;
    });
    reject("negative typed operand count", [] {
        reportedOperands = -1;
    });
    reject("typed output count exceeds payload", [] {
        reportedOutputs = std::numeric_limits<std::int64_t>::max();
    });
    reject("typed operand count exceeds payload", [] {
        reportedOperands = std::numeric_limits<std::int64_t>::max();
    });
    reject("truncated failure output row", [] {
        reportedOutputs = 0;
    });
    reject("truncated failure operand prefix", [] {
        reportedOperands = 2;
    });
    reject("failure row has wrong record kind", [] {
        loweringReport.recordKind = Lowering::RecordKind::Module;
    });
    reject("failure row has wrong prefix begin", [] {
        loweringReport.operandBegin = 1;
    });
    reject("failure row has wrong prefix length", [] {
        loweringReport.operandCount = 2;
    });
    reject("failure source has wrong operand domain", [] {
        loweringOperands[0].operandRole = Lowering::OperandRole::TypeId;
    });
    reject("failure source escapes metadata", [] {
        loweringOperands[0].signedValue = 8;
    });
    reject("failure detail has wrong operand domain", [] {
        loweringOperands[1].operandRole = Lowering::OperandRole::DiagnosticInteger;
    });
    reject("negative active diagnostic type", [&] {
        typeReport();
        loweringOperands[2].signedValue = -1;
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
                    sessionPayload.allocation == 0 && loweringRun == 0,
                "failure while admitting or ingesting a source did not release Session and arena once");
        ++cases;
    }
}

} // namespace
// No forged report in this fixture may reach successful module verification.
// A distinct exception prevents the rejection controls from accepting this path.
void aurora::ir::verifyHostedGraph(std::vector<FunctionBody> &, const Metadata &) {
    throw std::runtime_error("forged projection unexpectedly reached graph verification");
}
// Link the real native capsule without the generated metadata verifier. Every
// owner entry rejects: parser conversion failures must precede construction,
// and this fixture must never manufacture accepted durable metadata.
[[noreturn]] static void unexpectedMetadataEntry() noexcept {
    std::fputs("forged projection unexpectedly reached metadata verification\n", stderr);
    std::abort();
}
// This report-only fixture rejects before the successful source projection.
// Its real traversal, pending allocation and cleanup are covered by the shared
// projection driver, never by substituting another successful implementation.
extern "C" std::int64_t aurora_hosted_projection_name_capacity(const void *) noexcept {
    unexpectedMetadataEntry();
}
extern "C" void aurora_hosted_projection_create(const void *, void *) noexcept {
    unexpectedMetadataEntry();
}
extern "C" void aurora_hosted_projection_release(void *) noexcept {
    unexpectedMetadataEntry();
}
extern "C" std::int64_t aurora_hosted_projection_measure(const void *, std::int64_t, std::int64_t) noexcept {
    unexpectedMetadataEntry();
}
extern "C" std::int64_t aurora_hosted_projection_fill(const void *) noexcept {
    unexpectedMetadataEntry();
}
extern "C" void aurora_hosted_projection_metadata_counts(const void *, void *) noexcept {
    unexpectedMetadataEntry();
}
extern "C" void aurora_hosted_projection_instruction_counts(const void *, void *) noexcept {
    unexpectedMetadataEntry();
}
extern "C" std::int64_t aurora_hosted_projection_count(const void *, std::int64_t) noexcept {
    unexpectedMetadataEntry();
}
extern "C" std::int64_t aurora_hosted_projection_lint(const void *, std::int64_t) noexcept {
    unexpectedMetadataEntry();
}
extern "C" void aurora_hosted_catalog_summary(void *output) noexcept {
    // Quota and admission inputs only; this fixture seeds no catalog.
    aurora::hosted_abi::compiler_catalog::Summary summary{};
    summary.serviceGroups = 4295033150;
    std::memcpy(output, &summary, sizeof(summary));
}
extern "C" void aurora_hosted_metadata_flag_masks(void *output) noexcept {
    // Projection failures precede construction. This fixture grants no flag
    // authority and still aborts if any forged projection reaches an owner.
    const aurora::hosted_abi::compiler_ir_metadata::FlagMasks inert{};
    std::memcpy(output, &inert, sizeof(inert));
}
extern "C" void aurora_hosted_metadata_create(const void *, void *) noexcept {
    unexpectedMetadataEntry();
}
extern "C" std::int64_t aurora_hosted_metadata_initialize(void *, const void *) noexcept {
    unexpectedMetadataEntry();
}
extern "C" void aurora_hosted_metadata_release(void *) noexcept {
    unexpectedMetadataEntry();
}
extern "C" std::int64_t aurora_hosted_metadata_allocated(const void *) noexcept {
    unexpectedMetadataEntry();
}
extern "C" std::int64_t aurora_hosted_metadata_run(void *) noexcept {
    unexpectedMetadataEntry();
}
extern "C" std::int64_t aurora_hosted_metadata_error(const void *) noexcept {
    unexpectedMetadataEntry();
}
extern "C" std::int64_t aurora_hosted_metadata_object_leaf_root(const void *, std::int64_t, std::int64_t) noexcept {
    unexpectedMetadataEntry();
}
extern "C" std::int64_t
aurora_hosted_metadata_byte_array_element_root(const void *, std::int64_t, std::int64_t) noexcept {
    unexpectedMetadataEntry();
}
extern "C" void aurora_hosted_instructions_create(const void *, void *) noexcept {
    unexpectedMetadataEntry();
}
extern "C" void aurora_hosted_instructions_release(void *) noexcept {
    unexpectedMetadataEntry();
}
extern "C" std::int64_t aurora_hosted_instructions_allocated(const void *) noexcept {
    unexpectedMetadataEntry();
}
extern "C" std::int64_t aurora_hosted_instructions_admit(const void *) noexcept {
    unexpectedMetadataEntry();
}
extern "C" std::int64_t aurora_hosted_instructions_structure(const void *) noexcept {
    unexpectedMetadataEntry();
}
extern "C" std::int64_t aurora_hosted_instructions_publish(void *) noexcept {
    unexpectedMetadataEntry();
}
extern "C" std::int64_t aurora_hosted_instructions_error(const void *) noexcept {
    unexpectedMetadataEntry();
}
// No malformed parser report may reach the mandatory source verifier lifecycle.
extern "C" void aurora_hosted_verification_create(const void *, void *) noexcept {
    unexpectedMetadataEntry();
}
extern "C" std::int64_t aurora_hosted_verification_run(const void *, std::int64_t) noexcept {
    unexpectedMetadataEntry();
}
extern "C" void aurora_hosted_verification_report(const void *, void *) noexcept {
    unexpectedMetadataEntry();
}
extern "C" void aurora_hosted_verification_release(void *) noexcept {
    unexpectedMetadataEntry();
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
// Resolution sources admit as the forged module header; no syntax is read back.
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
    Resolution::SourceResult header{};
    header.lexical = aurora::hosted_abi::compiler_lexer::Event::token;
    header.field_type = TypeKind::invalid;
    header.name_begin = 7;
    header.name_end = 13;
    std::memcpy(output, &header, sizeof(header));
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
template <class Row>
void resolvedRead(const void *session, std::int64_t index, void *output, const std::vector<Row> &rows, int kind) {
    checkSession(session);
    if (resolverRunning && projectionThrow == kind)
        throw std::runtime_error("injected resolved read failure");
    require(index >= 0 && static_cast<std::size_t>(index) < rows.size(), "resolver requested an out-of-range row");
    std::memcpy(output, &rows[static_cast<std::size_t>(index)], sizeof(Row));
}
} // namespace
extern "C" void aurora_hosted_resolver_create(const void *input, void *output) {
    const auto &record = *static_cast<const aurora::hosted_abi::ResolverCreate *>(input);
    require(record.region != 0 && !sessionAddress, "resolver create did not receive a fresh same-region slot");
    sessionRegion = record.region;
    const auto bytes = resolutionSyntax.size() * sizeof(Resolution::SyntaxRow) +
                       resolutionMetadata.size() * sizeof(Resolution::MetaRow) +
                       resolutionDecorations.size() * sizeof(Resolution::ResolvedRow) +
                       static_cast<std::size_t>(sourceBytes) + sizeof(loweringReport) + sizeof(loweringOperands);
    aurora::hosted::bytes::__au_runtime_bytes_allocate(
        record.region, static_cast<std::int64_t>(bytes), &sessionPayload);
    require(sessionPayload.success == 1, "forged resolution payload allocation failed");
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
    resolutionMetadata[0].tag = Resolution::MetaTag::module_unit;
    resolutionMetadata[0].value10 = 7;
    return 0;
}
extern "C" void aurora_hosted_resolver_release(void *input) {
    const auto &record = *static_cast<const aurora::hosted_abi::ResolverRelease *>(input);
    checkSession(record.session.storage.data());
    require(record.region == sessionRegion && created == released,
            "Session-only release retained a live parsed owner or lost its region");
    aurora::hosted::bytes::__au_runtime_bytes_drop(&sessionPayload);
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
    resolverRunning = true;
    return 0;
}
extern "C" std::int64_t aurora_hosted_resolver_count(const void *session, std::int64_t pool) {
    checkSession(session);
    if (pool == 0)
        return sourceBytes;
    if (pool == 1)
        return reportedSyntax;
    if (pool == 2)
        return reportedMetadata;
    if (pool == 3)
        return reportedDecorations;
    if (pool == 4)
        return 0;
    if (pool == 5)
        return 1;
    return -1;
}
extern "C" std::int64_t aurora_hosted_resolver_read_source(const void *session, std::int64_t) {
    checkSession(session);
    return -1;
}
extern "C" void
aurora_hosted_resolver_linkage_chunk(const void *session, std::int64_t symbol, std::int64_t offset, void *output) {
    checkSession(session);
    Resolution::LinkageChunk chunk{};
    chunk.byteCount = -1;
    if (symbol == 5 && offset == 0) {
        chunk.payload[0] = 'f';
        chunk.byteCount = linkageChunkSize;
    }
    std::memcpy(output, &chunk, sizeof(chunk));
}
extern "C" void aurora_hosted_resolver_status(const void *session, void *output) {
    checkSession(session);
    std::memcpy(output, &resolutionStatus, sizeof(resolutionStatus));
}
extern "C" void aurora_hosted_resolver_read_syntax(const void *session, std::int64_t index, void *output) {
    resolvedRead(session, index, output, resolutionSyntax, 1);
}
extern "C" void aurora_hosted_resolver_read_meta(const void *session, std::int64_t index, void *output) {
    resolvedRead(session, index, output, resolutionMetadata, 2);
}
extern "C" void aurora_hosted_resolver_read_resolved(const void *session, std::int64_t index, void *output) {
    resolvedRead(session, index, output, resolutionDecorations, 3);
}

// Eight copied lowering endpoints. Only the fixed failure report above is
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
extern "C" std::int64_t aurora_hosted_lowering_count(const void *session, std::int64_t pool) noexcept {
    checkSession(session);
    return pool == 0 ? reportedOutputs : pool == 1 ? reportedOperands : -1;
}
extern "C" void aurora_hosted_lowering_read_output(const void *session, std::int64_t index, void *output) noexcept {
    checkSession(session);
    require(index == 0, "failure conversion read beyond its reserved output row");
    ++loweringOutputReads;
    std::memcpy(output, &loweringReport, sizeof(loweringReport));
}
extern "C" void aurora_hosted_lowering_read_operand(const void *session, std::int64_t index, void *output) noexcept {
    checkSession(session);
    require(index >= 0 && index < 3, "failure conversion read beyond its reserved operand prefix");
    ++loweringOperandReads;
    std::memcpy(output, &loweringOperands[static_cast<std::size_t>(index)], sizeof(loweringOperands[0]));
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
