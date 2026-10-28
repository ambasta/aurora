#pragma once
#include "hosted_pipeline.hpp"
#include "../runtime/hosted_bytes.hpp"
#include <algorithm>
#include <limits>
#include <memory>

namespace aurora::format {
inline constexpr std::size_t sourceLimit = 1024 * 1024;

class Finding {
public:
    std::string code;
    std::string message;
    SourceSpan span;
};
class Result {
public:
    std::string text;
    std::vector<Finding> findings;
    bool changed = false;
    std::vector<Finding> remainingFindings;
};

// One Aurora call parses the source, lays it out, checks that the output keeps
// every token and comment in place and formats to itself. The host bounds the
// source and copies out the output and the findings and failure Aurora renders.
class Operation {
    // Aurora bounds the workspace by the 1 MiB source and output limits it checks.
    hosted::bytes::Region region{std::numeric_limits<std::int64_t>::max()};
    hosted_abi::FormatterRelease formatter{};
    void *workspace() {
        return formatter.workspace.storage.data();
    }
    // Diagnostic -1 is the failure; findings of the source are sources[0],
    // those of the output sources[1].
    Diagnostic diagnostic(std::int64_t index, const std::vector<std::shared_ptr<const SourceText>> &sources) {
        return copyReport(
            [&](std::int64_t offset) {
                hosted_abi::compiler_resolver::Report report{};
                aurora_hosted_formatter_diagnostic(workspace(), index, offset, &report);
                return report;
            },
            [&](std::int64_t source) {
                if (source < 0 || static_cast<std::uint64_t>(source) >= sources.size())
                    throw Error(DiagnosticCode::Internal, "invalid hosted formatter result");
                return sources[static_cast<std::size_t>(source)];
            });
    }
    std::vector<Finding>
    findings(std::int64_t first, std::int64_t count, const std::vector<std::shared_ptr<const SourceText>> &sources) {
        std::vector<Finding> result;
        for (auto index = first; index < first + count; ++index) {
            auto found = diagnostic(index, sources);
            result.push_back({diagnosticCode(found.code, "AUF"), std::move(found.message), std::move(found.span)});
        }
        return result;
    }

public:
    Operation() {
        formatter.region = region.id();
        hosted_abi::FormatterCreate create;
        create.region = region.id();
        aurora_hosted_formatter_create(&create, workspace());
    }
    ~Operation() {
        aurora_hosted_formatter_release(&formatter);
    }
    Operation(const Operation &) = delete;
    Operation &operator=(const Operation &) = delete;
    // Without layout only the source's style findings are produced.
    Result run(const std::shared_ptr<const SourceText> &source, bool layout) {
        hosted_abi::FormatterInput input;
        input.source.backing = source->text.data();
        input.source.length = static_cast<std::int64_t>(source->text.size());
        if (aurora_hosted_formatter_prepare(workspace(), &input) != 1)
            throw Error(diagnostic(-1, {source}));
        // The workspace moves through the call and back; the copy left in `run` is dead.
        hosted_abi::FormatterRun run;
        run.region = region.id();
        run.workspace = formatter.workspace;
        run.layout = layout;
        aurora_hosted_formatter_run(&run, workspace());
        // Status 4 completes; 7 rejects the output, whose text stays readable.
        hosted_abi::compiler_formatter::Row report;
        aurora_hosted_formatter_finding(workspace(), -1, &report);
        if (report.a != 4 && report.a != 7)
            throw Error(diagnostic(-1, {source}));
        Result result;
        for (std::int64_t offset = 0; offset < report.b;) {
            hosted_abi::compiler_x86::EmitChunk chunk;
            aurora_hosted_formatter_chunk(workspace(), offset, &chunk);
            if (chunk.byteCount != std::min<std::int64_t>(512, report.b - offset))
                throw Error(DiagnosticCode::Internal, "invalid hosted formatter chunk");
            result.text.append(reinterpret_cast<const char *>(chunk.payload.data()), chunk.byteCount);
            offset += chunk.byteCount;
        }
        const std::vector sources{source, std::make_shared<const SourceText>(source->path, result.text)};
        if (report.a == 7)
            throw Error(diagnostic(-1, sources));
        result.findings = findings(0, report.c, sources);
        result.remainingFindings = findings(report.c, report.d, sources);
        return result;
    }
};
inline std::vector<Finding> styleFindings(const std::string &text) {
    if (text.size() > sourceLimit)
        throw Error(DiagnosticCode::Module, "formatter input exceeds 1 MiB source bound");
    return Operation().run(std::make_shared<const SourceText>("", text), false).findings;
}
inline Result source(const std::string &contents, const std::string &path = {}) {
    if (contents.size() > sourceLimit)
        throw Error(DiagnosticCode::Module, "formatter input exceeds 1 MiB source bound");
    auto result = Operation().run(std::make_shared<const SourceText>(path, contents), true);
    result.changed = contents != result.text;
    return result;
}
} // namespace aurora::format
