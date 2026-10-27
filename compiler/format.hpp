#pragma once
#include "hosted_parser.hpp"
#include "hosted_resolver.hpp"
#include "../runtime/hosted_bytes.hpp"
#include <algorithm>
#include <array>
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
// source, copies the output and findings and renders the diagnostics.
class Operation {
    hosted::bytes::Region region;
    hosted_abi::FormatterRelease formatter{};
    // One text's parse arena and workspace; a run formats the source and then
    // its output, which the source bound also bounds.
    static std::uint64_t quota(std::size_t bytes) {
        using namespace hosted_abi::compiler_parser;
        constexpr auto records = sizeof(AstNode) + sizeof(ChildEdge) + sizeof(TypeSyntax) + sizeof(SyntaxNode);
        constexpr auto rows = 5 * sizeof(hosted_abi::compiler_formatter::Row);
        return 2 * bytes * (records + hosted_abi::frameBytes + rows) + 8 * (records + rows) +
               (2 * hosted_parser::maximumLiveFrames + 8) * hosted_abi::frameBytes + 5 * sourceLimit;
    }
    [[noreturn]] void reject(const std::shared_ptr<const SourceText> &text) {
        hosted_abi::compiler_resolver::SourceResult rejection;
        aurora_hosted_formatter_rejection(formatter.workspace.storage.data(), &rejection);
        rejectSource(text, rejection);
        throw Error(DiagnosticCode::Internal, "invalid hosted formatter result");
    }
    std::vector<Finding>
    findings(const std::shared_ptr<const SourceText> &text, std::int64_t first, std::int64_t count) {
        constexpr std::array codes{"AUF1001", "AUF1002", "AUF1003"};
        constexpr std::array messages{"line exceeds 120 byte columns; comments and tokens are never split",
                                      "trailing whitespace",
                                      "indentation must use groups of four spaces"};
        const auto length = static_cast<std::int64_t>(text->text.size());
        std::vector<Finding> result;
        for (auto index = first; index < first + count; ++index) {
            hosted_abi::compiler_formatter::Row row;
            aurora_hosted_formatter_finding(formatter.workspace.storage.data(), index, &row);
            if (row.a < 1 || row.a > 3 || row.b < 0 || row.c < row.b || row.c > length || row.d < 1 ||
                row.d > length + 1 || row.e < 1 || row.e > row.b + 1 || row.f < row.e || row.f - row.e != row.c - row.b)
                throw Error(DiagnosticCode::Internal, "invalid hosted formatter finding");
            result.push_back({codes[row.a - 1],
                              messages[row.a - 1],
                              {text,
                               {static_cast<std::size_t>(row.b), static_cast<int>(row.d), static_cast<int>(row.e)},
                               {static_cast<std::size_t>(row.c), static_cast<int>(row.d), static_cast<int>(row.f)}}});
        }
        return result;
    }

public:
    explicit Operation(std::size_t bytes) : region(quota(bytes) + quota(sourceLimit)) {
        formatter.region = region.id();
        hosted_abi::FormatterCreate create;
        create.region = region.id();
        aurora_hosted_formatter_create(&create, formatter.workspace.storage.data());
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
        input.configuration = hosted_parser::admissionConfiguration();
        if (aurora_hosted_formatter_prepare(formatter.workspace.storage.data(), &input) != 1)
            throw Error(DiagnosticCode::Internal, "formatter workspace allocation failed");
        // The workspace moves through the call and back; the copy left in `run` is dead.
        hosted_abi::FormatterRun run;
        run.region = region.id();
        run.workspace = formatter.workspace;
        run.layout = layout;
        aurora_hosted_formatter_run(&run, formatter.workspace.storage.data());
        hosted_abi::compiler_formatter::Row report;
        aurora_hosted_formatter_finding(formatter.workspace.storage.data(), -1, &report);
        // 6 and 7 reject the source and the output, 8 and 9 refuse the output.
        if (report.a == 6)
            reject(source);
        if (report.a == 8)
            throw Error(DiagnosticCode::Internal, "formatter refused a token/comment change");
        if (report.a == 9)
            throw Error(DiagnosticCode::Internal, "formatter refused non-idempotent output");
        if (report.a != 4 && report.a != 7)
            throw Error(DiagnosticCode::Internal,
                        report.a == 2   ? "formatted output exceeds 1 MiB bound"
                        : report.a == 1 ? "formatter workspace allocation failed"
                                        : "invalid hosted formatter result");
        constexpr auto limit = static_cast<std::int64_t>(sourceLimit);
        if (report.b < 0 || report.b > limit || report.c < 0 || report.c > limit || report.d < 0 || report.d > limit ||
            report.e || report.f)
            throw Error(DiagnosticCode::Internal, "invalid hosted formatter extents");
        Result result;
        for (std::int64_t offset = 0; offset < report.b;) {
            hosted_abi::compiler_x86::EmitChunk chunk;
            aurora_hosted_formatter_chunk(formatter.workspace.storage.data(), offset, &chunk);
            if (chunk.byteCount != std::min<std::int64_t>(512, report.b - offset))
                throw Error(DiagnosticCode::Internal, "invalid hosted formatter chunk");
            result.text.append(reinterpret_cast<const char *>(chunk.payload.data()), chunk.byteCount);
            offset += chunk.byteCount;
        }
        const auto output = std::make_shared<const SourceText>(source->path, result.text);
        if (report.a == 7)
            reject(output);
        result.findings = findings(source, 0, report.c);
        result.remainingFindings = findings(output, report.c, report.d);
        return result;
    }
};
inline std::vector<Finding> styleFindings(const std::string &text) {
    if (text.size() > sourceLimit)
        throw Error(DiagnosticCode::Module, "formatter input exceeds 1 MiB source bound");
    return Operation(text.size()).run(std::make_shared<const SourceText>("", text), false).findings;
}
inline Result source(const std::string &contents, const std::string &path = {}) {
    if (contents.size() > sourceLimit)
        throw Error(DiagnosticCode::Module, "formatter input exceeds 1 MiB source bound");
    auto result = Operation(contents.size()).run(std::make_shared<const SourceText>(path, contents), true);
    result.changed = contents != result.text;
    return result;
}
} // namespace aurora::format
