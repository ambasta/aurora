#pragma once
#include "lexer.hpp"
#include "parser.hpp"
#include <algorithm>
#include <map>
#include <set>
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

// These are roles from the compiler AST, not a second language parser. Bracket
// pairing below only lays out already accepted syntax; it never accepts syntax.
class Roles {
    const std::vector<Token> &tokens;
    void initializerAfter(const Token &token) {
        auto found = std::lower_bound(
            tokens.begin(), tokens.end(), token.span.begin.offset, [](const Token &value, std::size_t offset) {
                return value.span.begin.offset < offset;
            });
        while (found != tokens.end() && found->text != "{")
            ++found;
        if (found == tokens.end())
            throw Error(DiagnosticCode::Internal, "formatter cannot locate an AST initializer", token.span);
        initializers.insert(found->span.begin.offset);
    }
    void expression(const ExpressionPtr &value) {
        if (!value)
            return;
        if (value->op == "unary")
            unary.insert(value->token.span.begin.offset);
        if (value->op == "binary")
            binary.insert(value->token.span.begin.offset);
        if (value->op == "array_literal" || value->op == "construct" || value->op == "array_zero")
            initializerAfter(value->token);
        for (const auto &argument : value->args)
            expression(argument);
    }
    void statement(const StatementPtr &value) {
        expression(value->expr);
        expression(value->target);
        for (const auto &child : value->body)
            statement(child);
        for (const auto &child : value->other)
            statement(child);
    }
    void function(const Function &value) {
        for (const auto &parameter : value.params)
            if (parameter.borrowed)
                references.insert(parameter.borrowSpan.begin.offset);
        for (const auto &initializer : value.initializers)
            expression(initializer.second);
        for (const auto &child : value.body)
            statement(child);
    }

public:
    std::set<std::size_t> unary, binary, initializers, enums, references;
    Roles(const std::vector<Token> &input, const Program &program) : tokens(input) {
        for (const auto &value : program.functions)
            function(value);
        for (const auto &value : program.functionTemplates)
            function(value);
        for (const auto &value : program.classes) {
            for (const auto &method : value.methods)
                function(method);
        }
        for (const auto &value : program.templates) {
            for (const auto &method : value.methods)
                function(method);
        }
        for (const auto &value : program.enums) {
            initializerAfter(value.token);
            auto found = initializers.lower_bound(value.token.span.begin.offset);
            enums.insert(*found);
            initializers.erase(found);
        }
    }
};

inline bool joinsWithoutChangingTokens(const std::string &left, const std::string &right) {
    const auto combined = lex(left + right);
    return combined.size() == 3 && combined[0].text == left && combined[1].text == right;
}

inline std::string layout(const LexedSource &source, const Program &program) {
    const Roles roles(source.tokens, program);
    class Piece {
    public:
        std::string text;
        SourceSpan span;
        bool comment;
    };
    std::vector<Piece> pieces;
    for (const auto &token : source.tokens) {
        if (token.text != "<eof>")
            pieces.push_back({token.text, token.span, false});
    }
    for (const auto &trivia : source.trivia) {
        if (trivia.kind == TriviaKind::LineComment)
            pieces.push_back({std::string(spelling(trivia.span)), trivia.span, true});
    }
    std::sort(pieces.begin(), pieces.end(), [](const Piece &left, const Piece &right) {
        return left.span.begin.offset < right.span.begin.offset;
    });
    class Brace {
    public:
        bool initializer;
        bool enumeration;
        std::size_t parentheses;
    };
    std::vector<Brace> braces;
    std::string result;
    std::size_t column = 0, parentheses = 0, lineStart = 0;
    // Only grammar-shaped boundaries can become soft breaks. Keep candidates
    // until the line overflows, so the decision includes the whole pending atom
    // rather than splitting whichever token happens to cross the byte limit.
    class Break {
    public:
        std::size_t offset, depth, gap;
        unsigned priority;
    };
    std::vector<Break> breaks;
    bool hardBreak = false;
    bool previousUnary = false, previousTemplateOpen = false;
    std::string previous;
    SourceSpan previousSpan;
    const auto newline = [&]() {
        if (!result.empty() && result.back() != '\n') {
            if (result.size() == sourceLimit)
                throw Error(DiagnosticCode::Internal, "formatted output exceeds 1 MiB bound");
            result += '\n';
        }
        column = 0;
        lineStart = result.size();
        breaks.clear();
    };
    const auto blankLine = [&]() {
        newline();
        if (!result.empty() && (result.size() < 2 || result[result.size() - 2] != '\n')) {
            if (result.size() == sourceLimit)
                throw Error(DiagnosticCode::Internal, "formatted output exceeds 1 MiB bound");
            result += '\n';
            lineStart = result.size();
        }
    };
    const auto append = [&](std::string_view text, std::size_t depth) {
        const auto needed = text.size() + (column == 0 ? depth * indentWidth : 0);
        if (needed > sourceLimit - result.size())
            throw Error(DiagnosticCode::Internal, "formatted output exceeds 1 MiB bound");
        if (column == 0) {
            result.append(depth * indentWidth, ' ');
            column = depth * indentWidth;
        }
        result.append(text);
        column += text.size();
    };
    for (std::size_t index = 0; index < pieces.size(); ++index) {
        const auto &piece = pieces[index];
        const auto &text = piece.text;
        // Inspect only the whitespace between adjacent lossless pieces. Counting
        // from a preceding code token would mistake intervening comments for an
        // intentional blank line. LF matches the shared lexer's line contract.
        bool separated = false;
        if (index > 0) {
            const auto begin = pieces[index - 1].span.end.offset;
            const auto gap = std::string_view(source.source->text).substr(begin, piece.span.begin.offset - begin);
            separated = std::count(gap.begin(), gap.end(), '\n') >= 2;
        }
        const bool afterOpeningBrace = index > 0 && !pieces[index - 1].comment && pieces[index - 1].text == "{";
        std::size_t depth = braces.size();
        if (piece.comment) {
            const bool wasTrailing = previousSpan.source && previousSpan.end.line == piece.span.begin.line;
            if (!wasTrailing || column + 1 + text.size() > columnLimit)
                newline();
            if (separated && !afterOpeningBrace)
                blankLine();
            if (column != 0)
                append(" ", depth);
            append(text, depth);
            newline();
            hardBreak = false;
            continue;
        }
        const bool unary = roles.unary.contains(piece.span.begin.offset);
        const bool binary = roles.binary.contains(piece.span.begin.offset);
        const bool templateOpen = text == "<" && !binary;
        const bool templateClose = (text == ">" || text == ">>") && !binary;
        const bool initializer = text == "{" && roles.initializers.contains(piece.span.begin.offset);
        const bool emptyInitializer = initializer && index + 1 < pieces.size() && pieces[index + 1].text == "}";
        const bool closesEmpty = text == "}" && previous == "{" && !braces.empty() && braces.back().initializer;
        const bool label =
            (text == "public" || text == "private") && index + 1 < pieces.size() && pieces[index + 1].text == ":";
        if (text == "}") {
            if (braces.empty())
                throw Error(DiagnosticCode::Internal, "formatter encountered an unpaired brace", piece.span);
            --depth;
        }
        if (label && depth > 0)
            --depth;
        const bool structuralBreak =
            (hardBreak && text != ";" && text != "," && text != ")" && text != "]" && text != "else") ||
            (text == "}" && !closesEmpty) || label;
        if (structuralBreak)
            newline();
        // Keep one user separator between declarations, statements, members or
        // comments. Block/file edges and expression gaps remain canonical; soft
        // wrapping never creates a separator that a later pass could amplify.
        if (separated && !afterOpeningBrace && text != "}" &&
            (structuralBreak || (index > 0 && pieces[index - 1].comment)))
            blankLine();
        hardBreak = false;
        bool space = !previous.empty();
        if (text == ";" || text == "," || text == ")" || text == "]" || text == "." || text == "::" || templateClose ||
            previous == "(" || previous == "[" || previous == "." || previous == "::" || previousUnary ||
            previousTemplateOpen || closesEmpty)
            space = false;
        if (roles.references.contains(piece.span.begin.offset))
            space = false;
        if (text == "(" || text == "[")
            space = previous == "if" || previous == "while" || (text == "(" && previous == "return") ||
                    (text == "(" && roles.binary.contains(previousSpan.begin.offset));
        if (templateOpen)
            space = previous == "template";
        if (text == ":")
            space = previous != "public" && previous != "private";
        if (initializer && previous != "=" && previous != "," && previous != "return" && previous != "(")
            space = false;
        if (column != 0 && !space && !joinsWithoutChangingTokens(previous, text))
            space = true;
        // Commas and AST binary operators are preferred over opening a list
        // or breaking after an assignment/return/result-type introducer. No
        // candidate exists inside a member/scope chain, around unary operators,
        // before call/index punctuation, or before a closing delimiter.
        unsigned priority = 0;
        if (binary || previous == ",")
            priority = 2;
        else if (previous == "=" || previous == "return" || previous == "->" ||
                 ((previous == "(" || previous == "[") && text != ")" && text != "]"))
            priority = 1;
        if (priority != 0 && column != 0)
            breaks.push_back({result.size(), braces.size() + 1, space ? 1u : 0u, priority});
        if (column != 0 && space)
            append(" ", depth);
        append(text, depth);
        while (column > columnLimit && !breaks.empty()) {
            // Prefer the strongest, latest boundary whose prefix fits. If an
            // indivisible prefix is itself oversized, emit it intact at the
            // first available boundary and retain its long-line finding.
            auto chosen = breaks.begin();
            bool fits = false;
            for (auto candidate = breaks.begin(); candidate != breaks.end(); ++candidate) {
                if (candidate->offset - lineStart > columnLimit)
                    break;
                if (!fits || candidate->priority >= chosen->priority) {
                    chosen = candidate;
                    fits = true;
                }
            }
            const auto boundary = *chosen;
            const auto added = 1 + boundary.depth * indentWidth;
            if (added - boundary.gap > sourceLimit - result.size())
                throw Error(DiagnosticCode::Internal, "formatted output exceeds 1 MiB bound");
            result.replace(boundary.offset, boundary.gap, "\n" + std::string(boundary.depth * indentWidth, ' '));
            breaks.erase(breaks.begin(), chosen + 1);
            for (auto &candidate : breaks)
                candidate.offset += added - boundary.gap;
            lineStart = boundary.offset + 1;
            column = result.size() - lineStart;
        }
        if (text == "(")
            ++parentheses;
        else if (text == ")") {
            if (parentheses == 0)
                throw Error(DiagnosticCode::Internal, "formatter encountered an unpaired parenthesis", piece.span);
            --parentheses;
        }
        if (text == "{") {
            braces.push_back({initializer, roles.enums.contains(piece.span.begin.offset), parentheses});
            hardBreak = !emptyInitializer;
        } else if (text == "}") {
            hardBreak = !braces.back().initializer;
            braces.pop_back();
        } else if (text == ";" || (text == ":" && (previous == "public" || previous == "private"))) {
            hardBreak = true;
        } else if (text == "," && !braces.empty() && (braces.back().initializer || braces.back().enumeration) &&
                   parentheses == braces.back().parentheses) {
            hardBreak = true;
        }
        previous = text;
        previousSpan = piece.span;
        previousUnary = unary;
        previousTemplateOpen = templateOpen;
    }
    newline();
    return result;
}

inline std::vector<Finding> styleFindings(const LexedSource &source) {
    std::vector<Finding> findings;
    SourcePosition position;
    const auto &text = source.source->text;
    while (position.offset < text.size()) {
        const auto lineStart = position;
        auto end = text.find('\n', position.offset);
        if (end == std::string::npos)
            end = text.size();
        const auto span = [&](std::size_t begin, std::size_t finish) {
            return SourceSpan{source.source,
                              {begin, lineStart.line, static_cast<int>(begin - lineStart.offset + 1)},
                              {finish, lineStart.line, static_cast<int>(finish - lineStart.offset + 1)}};
        };
        if (end - position.offset > columnLimit)
            findings.push_back({"AUF1001",
                                "line exceeds 120 byte columns; comments and tokens are never split",
                                span(position.offset + columnLimit, end)});
        auto trailing = end;
        while (trailing > position.offset &&
               (text[trailing - 1] == ' ' || text[trailing - 1] == '\t' || text[trailing - 1] == '\r'))
            --trailing;
        if (trailing != end)
            findings.push_back({"AUF1002", "trailing whitespace", span(trailing, end)});
        auto leading = position.offset;
        bool tab = false;
        while (leading < trailing && (text[leading] == ' ' || text[leading] == '\t')) {
            tab = tab || text[leading] == '\t';
            ++leading;
        }
        if (leading != trailing && (tab || (leading - position.offset) % indentWidth != 0))
            findings.push_back(
                {"AUF1003", "indentation must use groups of four spaces", span(position.offset, leading)});
        position.offset = end == text.size() ? end : end + 1;
        ++position.line;
        position.column = 1;
    }
    return findings;
}

inline Result source(const std::string &contents, const std::string &path = {}) {
    if (contents.size() > sourceLimit)
        throw Error(DiagnosticCode::Module, "formatter input exceeds 1 MiB source bound");
    const auto original = lexSource(contents, path);
    const auto parsed = Parser(original.tokens).parse();
    auto output = layout(original, parsed);
    const auto formatted = lexSource(output, path);
    if (!equivalent(original, formatted))
        throw Error(DiagnosticCode::Internal, "formatter refused a token/comment change");
    const auto reparsed = Parser(formatted.tokens).parse();
    if (layout(formatted, reparsed) != output)
        throw Error(DiagnosticCode::Internal, "formatter refused non-idempotent output");
    return {std::move(output), styleFindings(original), contents != formatted.source->text, styleFindings(formatted)};
}
} // namespace aurora::format
