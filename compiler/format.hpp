#pragma once
#include "lexer.hpp"
#include "parser.hpp"
#include "../runtime/hosted_bytes.hpp"
#include <algorithm>
#include <string_view>

namespace aurora::format {
inline constexpr std::size_t columnLimit = 120;
inline constexpr std::size_t indentWidth = 4;
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

inline std::string_view spelling(const SourceSpan &span) {
    return std::string_view(span.source->text).substr(span.begin.offset, span.end.offset - span.begin.offset);
}
inline std::vector<std::string> comments(const LexedSource &source) {
    std::vector<std::string> result;
    for (const auto &trivia : source.trivia) {
        if (trivia.kind == TriviaKind::LineComment)
            result.emplace_back(spelling(trivia.span));
    }
    return result;
}
inline bool equivalent(const LexedSource &left, const LexedSource &right) {
    if (left.tokens.size() != right.tokens.size() || comments(left) != comments(right))
        return false;
    for (std::size_t index = 0; index < left.tokens.size(); ++index) {
        if (left.tokens[index].text != right.tokens[index].text)
            return false;
    }
    // A comment may not move across a token, even when all comment bytes survive.
    const auto anchors = [](const LexedSource &source) {
        std::vector<std::size_t> result;
        std::size_t token = 0;
        for (const auto &trivia : source.trivia) {
            if (trivia.kind != TriviaKind::LineComment)
                continue;
            while (token < source.tokens.size() && source.tokens[token].span.end.offset <= trivia.span.begin.offset &&
                   source.tokens[token].text != "<eof>")
                ++token;
            result.push_back(token);
        }
        return result;
    };
    return anchors(left) == anchors(right);
}

// One operation owns all layout and finding decisions. The host retains source
// snapshots, parser diagnostics and copied publication through the generated ABI.
class Operation {
    hosted::bytes::Region region;
    hosted_abi::ParserRelease parser{};
    hosted_abi::FormatterRelease formatter{};
    static std::uint64_t quota(std::size_t bytes) {
        using namespace hosted_abi::compiler_parser;
        constexpr auto records = sizeof(AstNode) + sizeof(ChildEdge) + sizeof(TypeSyntax) + sizeof(SyntaxNode);
        constexpr auto rows = 5 * sizeof(hosted_abi::compiler_formatter::Row);
        return 2 * bytes * (records + hosted_abi::frameBytes + rows) + 8 * (records + rows) +
               (2 * 1939 + 8) * hosted_abi::frameBytes + 5 * sourceLimit;
    }

public:
    explicit Operation(std::size_t bytes) : region(quota(bytes)) {
        parser.region = formatter.region = region.id();
        hosted_abi::ParserCreate parse;
        parse.region = region.id();
        aurora_hosted_parser_create(&parse, parser.arena.storage.data());
        hosted_abi::FormatterCreate create;
        create.region = region.id();
        aurora_hosted_formatter_create(&create, formatter.workspace.storage.data());
    }
    ~Operation() {
        aurora_hosted_formatter_release(&formatter);
        aurora_hosted_parser_release(&parser);
    }
    Operation(const Operation &) = delete;
    Operation &operator=(const Operation &) = delete;
    Result run(const LexedSource &source, bool layout) {
        if (layout)
            (void)parseHostedModuleSyntax(source.tokens, parser.arena.storage.data());
        const std::array<const void *, 2> roots{formatter.workspace.storage.data(), parser.arena.storage.data()};
        hosted_abi::FormatterInput input;
        input.source.backing = source.source->text.data();
        input.source.length = static_cast<std::int64_t>(source.source->text.size());
        if (aurora_hosted_formatter_prepare(formatter.workspace.storage.data(), &input) != 1)
            throw Error(DiagnosticCode::Internal, "formatter workspace allocation failed");
        hosted_abi::compiler_formatter::Row report;
        const auto status = aurora_hosted_formatter_run(roots.data(), layout);
        aurora_hosted_formatter_finding(formatter.workspace.storage.data(), -1, &report);
        if (status != report.a)
            throw Error(DiagnosticCode::Internal, "invalid hosted formatter status");
        if (report.a != 4)
            throw Error(DiagnosticCode::Internal,
                        report.a == 2   ? "formatted output exceeds 1 MiB bound"
                        : report.a == 1 ? "formatter workspace allocation failed"
                                        : "invalid hosted formatter result");
        if (report.b < 0 || report.b > static_cast<std::int64_t>(sourceLimit) || report.c < 0 ||
            report.c > static_cast<std::int64_t>(sourceLimit) || report.d || report.e || report.f)
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
        constexpr std::array codes{"AUF1001", "AUF1002", "AUF1003"};
        constexpr std::array messages{"line exceeds 120 byte columns; comments and tokens are never split",
                                      "trailing whitespace",
                                      "indentation must use groups of four spaces"};
        for (std::int64_t index = 0; index < report.c; ++index) {
            hosted_abi::compiler_formatter::Row row;
            aurora_hosted_formatter_finding(formatter.workspace.storage.data(), index, &row);
            if (row.a < 1 || row.a > 3 || row.b < 0 || row.c < row.b || row.c > input.source.length || row.d < 1 ||
                row.d > input.source.length + 1 || row.e < 1 || row.e > row.b + 1 || row.f < row.e ||
                row.f - row.e != row.c - row.b)
                throw Error(DiagnosticCode::Internal, "invalid hosted formatter finding");
            result.findings.push_back(
                {codes[row.a - 1],
                 messages[row.a - 1],
                 {source.source,
                  {static_cast<std::size_t>(row.b), static_cast<int>(row.d), static_cast<int>(row.e)},
                  {static_cast<std::size_t>(row.c), static_cast<int>(row.d), static_cast<int>(row.f)}}});
        }
        return result;
    }
};
inline std::vector<Finding> styleFindings(const LexedSource &source) {
    if (source.source->text.size() > sourceLimit)
        throw Error(DiagnosticCode::Module, "formatter input exceeds 1 MiB source bound");
    return Operation(source.source->text.size()).run(source, false).findings;
}
inline Result source(const std::string &contents, const std::string &path = {}) {
    if (contents.size() > sourceLimit)
        throw Error(DiagnosticCode::Module, "formatter input exceeds 1 MiB source bound");
    const auto original = lexSource(contents, path);
    auto result = Operation(contents.size()).run(original, true);
    const auto formatted = lexSource(result.text, path);
    if (!equivalent(original, formatted))
        throw Error(DiagnosticCode::Internal, "formatter refused a token/comment change");
    auto again = Operation(result.text.size()).run(formatted, true);
    if (again.text != result.text)
        throw Error(DiagnosticCode::Internal, "formatter refused non-idempotent output");
    result.changed = contents != result.text;
    result.remainingFindings = std::move(again.findings);
    return result;
}
} // namespace aurora::format
