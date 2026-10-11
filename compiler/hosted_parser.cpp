// Trusted hosted bootstrap boundary. Source snapshots remain immutable and live
// throughout each synchronous call; no owner descriptor or payload pointer is
// constructed, copied or inspected here.
#include "hosted_parser.hpp"
#include "../runtime/hosted_bytes.hpp"
#include <algorithm>
#include <array>
#include <cstddef>
#include <limits>
#include <utility>

#ifndef AURORA_HOSTED_PARSER
#error The hosted parser adapter requires AURORA_HOSTED_PARSER
#endif
extern "C" {
void aurora_hosted_parser_create(const void *, void *);
void aurora_hosted_parser_parse(void *, const void *, void *);
std::int64_t aurora_hosted_parser_count(const void *);
void aurora_hosted_parser_read(const void *, std::int64_t, void *);
std::int64_t aurora_hosted_parser_edges(const void *);
void aurora_hosted_parser_edge(const void *, std::int64_t, void *);
void aurora_hosted_parser_release(void *);
}

namespace aurora {
namespace {
using hosted_parser::NodeKind;
using hosted_parser::Status;
using hosted_parser::Stop;
// Literal private ABI layouts, independently checked by generated-code tests.
class Input {
public:
    std::uint64_t kind = 0;
    const char *backing;
    std::array<std::uint64_t, 3> reserved{};
    std::int64_t start = 0;
    std::int64_t length;
    std::int64_t offset;
    std::int64_t line;
    std::int64_t lineStart;
    Stop stop;
};
class Result {
public:
    Status status = Status::Invalid;
    std::int64_t root = -1, count = -1, tokens = -1, offset = -1;
};
class Node {
public:
    NodeKind kind = NodeKind::Invalid;
    std::int64_t token = -1, first = -1, second = -1, depth = -1, nameEnd = -1, close = -1;
};
class Edge {
public:
    std::int64_t child = -1, previous = -1, count = -1, depth = -1;
};
class Arena {
    hosted::bytes::Region region;
    class Record {
    public:
        std::uint64_t region;
        alignas(8) std::array<std::byte, 128> arena{};
    } record;
    static_assert(sizeof(Record) == 136 && offsetof(Record, arena) == 8);

public:
    explicit Arena(std::uint64_t quota) : region(quota), record{region.id(), {}} {
        const std::array<std::uint64_t, 2> input{region.id(), 0};
        aurora_hosted_parser_create(input.data(), data());
    }
    ~Arena() {
        aurora_hosted_parser_release(&record);
    }
    Arena(const Arena &) = delete;
    Arena &operator=(const Arena &) = delete;
    void *data() {
        return record.arena.data();
    }
};
static_assert(sizeof(Input) == 88 && offsetof(Input, backing) == 8 && offsetof(Input, start) == 40 &&
              offsetof(Input, length) == 48 && offsetof(Input, offset) == 56 && offsetof(Input, line) == 64 &&
              offsetof(Input, lineStart) == 72 && offsetof(Input, stop) == 80);
static_assert(sizeof(Result) == 40 && sizeof(Node) == 56 && sizeof(Edge) == 32);

[[noreturn]] void invalid() {
    throw Error(DiagnosticCode::Internal, "hosted parser returned an invalid result");
}
bool identifier(const std::string &text) {
    if (text.empty())
        return false;
    const auto first = static_cast<unsigned char>(text.front());
    if (!((first >= 'a' && first <= 'z') || (first >= 'A' && first <= 'Z') || first == '_'))
        return false;
    return std::all_of(text.begin() + 1, text.end(), [](unsigned char byte) {
        return (byte >= 'a' && byte <= 'z') || (byte >= 'A' && byte <= 'Z') || (byte >= '0' && byte <= '9') ||
               byte == '_';
    });
}
bool tailIdentifier(const std::string &text, bool allowArray) {
    // primary() accepts an identifier-shaped first name. Only qualified tails
    // and member names pass through the reference parser's stricter ident().
    static const std::array<std::string, 29> reserved{
        "fn",        "module",        "let",       "mut",    "if",     "else",     "return", "true",
        "false",     "static_assert", "class",     "while",  "break",  "continue", "auto",   "const",
        "public",    "private",       "protected", "unsafe", "extern", "struct",   "export", "import",
        "namespace", "this",          "template",  "Scalar", "enum"};
    return identifier(text) && text != "builtin" && (allowArray || text != "array") && !text.starts_with("__au_") &&
           std::find(reserved.begin(), reserved.end(), text) == reserved.end();
}
bool binary(const std::string &text) {
    return text == "||" || text == "&&" || text == "|" || text == "^" || text == "&" || text == "==" || text == "!=" ||
           text == "<" || text == ">" || text == "<=" || text == ">=" || text == "<<" || text == ">>" || text == "+" ||
           text == "-" || text == "*" || text == "/" || text == "%";
}
} // namespace

ExpressionPtr parseHostedExpression(const std::vector<Token> &tokens, std::size_t &position, Stop stop) {
    if (position >= tokens.size() ||
        (stop != Stop::Semicolon && stop != Stop::CloseParenthesis && stop != Stop::Assignment))
        invalid();
    const auto &begin = tokens[position].span;
    if (!begin.source)
        invalid();
    const auto &source = begin.source;
    if (source->text.size() > static_cast<std::size_t>(std::numeric_limits<int>::max() - 1) ||
        begin.begin.offset > source->text.size() || begin.begin.line < 1 || begin.begin.column < 1 ||
        static_cast<std::size_t>(begin.begin.column - 1) > begin.begin.offset)
        invalid();
    Input input;
    input.backing = source->text.data();
    input.length = static_cast<std::int64_t>(source->text.size());
    input.offset = static_cast<std::int64_t>(begin.begin.offset);
    input.line = begin.begin.line;
    input.lineStart = input.offset - begin.begin.column + 1;
    input.stop = stop;
    // At most one node per source token and a bounded explicit parser stack.
    // Geometric growth uses replacement quota, not old+new payload quota.
    Arena arena(static_cast<std::uint64_t>(source->text.size()) * 192 + 131072);
    Result result;
    aurora_hosted_parser_parse(arena.data(), &input, &result);
    const auto actualCount = aurora_hosted_parser_count(arena.data());
    const auto edgeCount = aurora_hosted_parser_edges(arena.data());
    if (result.status < Status::Success || result.status >= Status::Invalid || result.count < 0 ||
        result.count != actualCount || edgeCount < 0 || result.tokens < 0 ||
        static_cast<std::uint64_t>(result.tokens) >= tokens.size() - position || result.offset < input.offset ||
        result.offset > input.length)
        invalid();
    if (result.status == Status::Unsupported) {
        if (result.root != -1 || result.count != 0 || edgeCount != 0 || result.tokens != 0 ||
            result.offset != input.offset)
            invalid();
        return {};
    }
    const auto end = position + static_cast<std::size_t>(result.tokens);
    for (auto index = position; index <= end; ++index) {
        const auto &token = tokens[index];
        const auto &span = token.span;
        if (span.source != source || span.begin.offset > span.end.offset || span.end.offset > source->text.size() ||
            (index > position && tokens[index - 1].span.end.offset > span.begin.offset) || token.text.empty() ||
            (token.text == "<eof>"
                 ? span.begin.offset != source->text.size() || span.end.offset != span.begin.offset
                 : source->text.compare(span.begin.offset, span.end.offset - span.begin.offset, token.text) != 0))
            invalid();
    }
    if (static_cast<std::size_t>(result.offset) != tokens[end].span.begin.offset)
        invalid();
    const auto &at = tokens[end];
    if (result.status != Status::Success) {
        if (result.root != -1)
            invalid();
        if (result.status == Status::AllocationFailure)
            throw Error(DiagnosticCode::Internal, "hosted parser allocation failed", at.span);
        if (result.status == Status::NestingLimit)
            throw Error(DiagnosticCode::NestingLimit, "expression parser nesting exceeds 128", at.span);
        std::string message;
        if (result.status == Status::ExpectedExpression)
            message = "expected expression";
        else if (result.status == Status::ExpectedClose)
            message = "expected ')'";
        else if (result.status == Status::ExpectedIndexClose)
            message = "expected ']'";
        else if (result.status == Status::ExpectedIdentifier)
            message = "expected identifier";
        else if (result.status == Status::ReservedIdentifier)
            message = "reserved identifier";
        else if (result.status == Status::ReservedBuiltin)
            message = "reserved builtin storage name";
        else if (result.status == Status::ReservedPrefix)
            message = "reserved compiler identifier prefix: __au_";
        else if (result.status == Status::DepthLimit)
            message = "expression AST depth exceeds 128";
        else if (result.status == Status::ExpectedEnd)
            message = stop == Stop::CloseParenthesis ? "expected ')'" : "expected ';'";
        else
            invalid();
        throw Error(DiagnosticCode::UnexpectedToken, message + " (found '" + at.text + "')", at.span);
    }
    if (result.tokens == 0 || result.count == 0 || result.count > result.tokens || edgeCount >= result.count ||
        result.root != result.count - 1 ||
        !(stop == Stop::CloseParenthesis ? at.text == ")"
                                         : at.text == ";" || (stop == Stop::Assignment && at.text == "=")))
        invalid();
    const auto size = static_cast<std::size_t>(result.tokens);
    const auto text = [&](std::int64_t ordinal) -> const std::string & {
        if (ordinal < 0 || ordinal >= result.tokens)
            invalid();
        return tokens[position + static_cast<std::size_t>(ordinal)].text;
    };
    std::vector<bool> tokenUsed(size, false);
    const auto claim = [&](std::int64_t ordinal) {
        if (ordinal < 0 || ordinal >= result.tokens || tokenUsed[static_cast<std::size_t>(ordinal)])
            invalid();
        tokenUsed[static_cast<std::size_t>(ordinal)] = true;
    };
    const auto punctuation = [&](std::int64_t ordinal, const std::string &expected) {
        if (text(ordinal) != expected)
            invalid();
        claim(ordinal);
    };
    // Match all delimiters independently before any grouping expansion. A call
    // close cannot be borrowed by another call, an index, or a grouping node.
    std::vector<std::int64_t> matching(size, -1), openings;
    for (std::int64_t ordinal = 0; ordinal < result.tokens; ++ordinal) {
        const auto &spelling = text(ordinal);
        if (spelling == "(" || spelling == "[")
            openings.push_back(ordinal);
        else if (spelling == ")" || spelling == "]") {
            if (openings.empty() || text(openings.back()) != (spelling == ")" ? "(" : "["))
                invalid();
            matching[static_cast<std::size_t>(ordinal)] = openings.back();
            matching[static_cast<std::size_t>(openings.back())] = ordinal;
            openings.pop_back();
        }
    }
    if (!openings.empty())
        invalid();
    const auto delimiters = [&](std::int64_t open, std::int64_t close, bool index) {
        punctuation(open, index ? "[" : "(");
        punctuation(close, index ? "]" : ")");
        if (matching[static_cast<std::size_t>(open)] != close)
            invalid();
    };
    std::vector<Node> records(static_cast<std::size_t>(result.count));
    std::vector<Edge> edges(static_cast<std::size_t>(edgeCount));
    // Claim every node's own syntax up front, so child grouping cannot consume
    // a call's parentheses. Names retain the original first token and its span.
    for (std::int64_t index = 0; index < result.count; ++index) {
        auto &node = records[static_cast<std::size_t>(index)];
        aurora_hosted_parser_read(arena.data(), index, &node);
        if (node.token < 0 || node.token >= result.tokens || node.nameEnd < node.token ||
            node.nameEnd >= result.tokens || node.close < node.nameEnd || node.close >= result.tokens ||
            node.depth < 1 || node.depth > 128)
            invalid();
        const auto &spelling = text(node.token);
        if (node.kind == NodeKind::Name || node.kind == NodeKind::Call) {
            if (!identifier(spelling) || spelling == "true" || spelling == "false" ||
                (node.nameEnd - node.token) % 2 != 0)
                invalid();
            claim(node.token);
            for (auto tail = node.token + 2; tail <= node.nameEnd; tail += 2) {
                punctuation(tail - 1, "::");
                if (!tailIdentifier(text(tail), true))
                    invalid();
                claim(tail);
            }
            if (node.kind == NodeKind::Name) {
                if (node.close != node.nameEnd)
                    invalid();
            } else {
                // These unqualified builtins take a type, not expression args.
                if (node.nameEnd == node.token &&
                    (spelling == "size_of" || spelling == "type_id" || spelling == "field_count"))
                    invalid();
                delimiters(node.nameEnd + 1, node.close, false);
            }
        } else if (node.kind == NodeKind::Member || node.kind == NodeKind::MethodCall) {
            if (node.nameEnd != node.token || !tailIdentifier(spelling, false))
                invalid();
            punctuation(node.token - 1, ".");
            claim(node.token);
            if (node.kind == NodeKind::Member) {
                if (node.close != node.token)
                    invalid();
            } else
                delimiters(node.token + 1, node.close, false);
        } else if (node.kind == NodeKind::Index) {
            if (node.nameEnd != node.token)
                invalid();
            delimiters(node.token, node.close, true);
        } else {
            if (node.nameEnd != node.token || node.close != node.token ||
                (node.kind != NodeKind::Literal && node.kind != NodeKind::Unary && node.kind != NodeKind::Binary))
                invalid();
            claim(node.token);
        }
    }
    for (std::int64_t index = 0; index < edgeCount; ++index) {
        auto &edge = edges[static_cast<std::size_t>(index)];
        aurora_hosted_parser_edge(arena.data(), index, &edge);
        if (edge.child < 0 || edge.child >= result.count || edge.previous < -1 || edge.previous >= index)
            invalid();
        const auto childDepth = records[static_cast<std::size_t>(edge.child)].depth + 1;
        const auto previousCount = edge.previous < 0 ? 0 : edges[static_cast<std::size_t>(edge.previous)].count;
        const auto previousDepth = edge.previous < 0 ? 1 : edges[static_cast<std::size_t>(edge.previous)].depth;
        if (edge.count != previousCount + 1 || edge.depth != std::max(previousDepth, childDepth) || edge.depth > 128)
            invalid();
    }
    std::vector<ExpressionPtr> nodes;
    std::vector<bool> used(static_cast<std::size_t>(result.count), false);
    std::vector<bool> edgeUsed(static_cast<std::size_t>(edgeCount), false), postfixAllowed;
    std::vector<std::pair<std::int64_t, std::int64_t>> bounds;
    nodes.reserve(records.size());
    bounds.reserve(records.size());
    postfixAllowed.reserve(records.size());
    for (std::int64_t index = 0; index < result.count; ++index) {
        const auto &node = records[static_cast<std::size_t>(index)];
        auto token = tokens[position + static_cast<std::size_t>(node.token)];
        std::string op;
        if (node.kind == NodeKind::Name || node.kind == NodeKind::Call) {
            op = node.kind == NodeKind::Name ? "name" : "call";
            for (auto tail = node.token + 2; tail <= node.nameEnd; tail += 2)
                token.text += "::" + text(tail);
            token.span.end = tokens[position + static_cast<std::size_t>(node.nameEnd)].span.end;
        } else if (node.kind == NodeKind::Literal && (token.text == "true" || token.text == "false"))
            op = "bool";
        else if (node.kind == NodeKind::Literal && token.text.front() == '\'')
            op = "byte";
        else if (node.kind == NodeKind::Literal && token.text.front() >= '0' && token.text.front() <= '9')
            op = "number";
        else if (node.kind == NodeKind::Unary && (token.text == "-" || token.text == "!" || token.text == "~"))
            op = "unary";
        else if (node.kind == NodeKind::Binary && binary(token.text))
            op = "binary";
        else if (node.kind == NodeKind::Member)
            op = "member";
        else if (node.kind == NodeKind::MethodCall)
            op = "method_call";
        else if (node.kind == NodeKind::Index)
            op = "index";
        else
            invalid();
        auto expression = std::make_shared<Expression>(op, token);
        auto firstToken = node.token, lastToken = node.close;
        const auto attach = [&](std::int64_t child) {
            if (child < 0 || child >= index || used[static_cast<std::size_t>(child)])
                invalid();
            used[static_cast<std::size_t>(child)] = true;
            const auto &value = nodes[static_cast<std::size_t>(child)];
            expression->depth = std::max(expression->depth, value->depth + 1);
            if (expression->depth > 128)
                invalid();
            expression->args.push_back(value);
            return bounds[static_cast<std::size_t>(child)];
        };
        const auto receiver = [&](std::int64_t child, std::int64_t following) {
            const auto range = attach(child);
            if (!postfixAllowed[static_cast<std::size_t>(child)] || range.second + 1 != following)
                invalid();
            firstToken = range.first;
        };
        if (node.kind == NodeKind::Call || node.kind == NodeKind::MethodCall) {
            if (node.second < 0 || node.second > edgeCount || (node.first == -1) != (node.second == 0) ||
                (node.kind == NodeKind::MethodCall && node.second == 0))
                invalid();
            std::vector<std::int64_t> children;
            for (auto edge = node.first; edge != -1;) {
                if (edge < 0 || edge >= edgeCount || edgeUsed[static_cast<std::size_t>(edge)])
                    invalid();
                edgeUsed[static_cast<std::size_t>(edge)] = true;
                const auto &record = edges[static_cast<std::size_t>(edge)];
                children.push_back(record.child);
                edge = record.previous;
            }
            if (children.size() != static_cast<std::size_t>(node.second) ||
                (node.first != -1 && edges[static_cast<std::size_t>(node.first)].depth != node.depth))
                invalid();
            std::reverse(children.begin(), children.end());
            std::size_t argument = 0;
            if (node.kind == NodeKind::MethodCall) {
                receiver(children.front(), node.token - 1);
                argument = 1;
            }
            auto next = node.nameEnd + 2;
            for (; argument < children.size(); ++argument) {
                const auto range = attach(children[argument]);
                if (range.first != next || range.second >= node.close)
                    invalid();
                next = range.second + 1;
                if (argument + 1 < children.size())
                    punctuation(next++, ",");
            }
            if (next != node.close)
                invalid();
        } else if (node.kind == NodeKind::Unary) {
            const auto range = attach(node.first);
            if (node.second != -1 || range.first != node.token + 1)
                invalid();
            lastToken = range.second;
        } else if (node.kind == NodeKind::Binary) {
            const auto left = attach(node.first), right = attach(node.second);
            if (left.second + 1 != node.token || right.first != node.token + 1)
                invalid();
            firstToken = left.first;
            lastToken = right.second;
        } else if (node.kind == NodeKind::Member) {
            if (node.second != -1)
                invalid();
            receiver(node.first, node.token - 1);
        } else if (node.kind == NodeKind::Index) {
            receiver(node.first, node.token);
            const auto subscript = attach(node.second);
            if (subscript.first != node.token + 1 || subscript.second + 1 != node.close)
                invalid();
            // The reference AST locates indexing at the base expression's token.
            expression->token = nodes[static_cast<std::size_t>(node.first)]->token;
        } else if (node.first != -1 || node.second != -1)
            invalid();
        if (node.depth != expression->depth)
            invalid();
        bool grouped = false;
        while (firstToken > 0 && lastToken + 1 < result.tokens && text(firstToken - 1) == "(" &&
               !tokenUsed[static_cast<std::size_t>(firstToken - 1)] &&
               matching[static_cast<std::size_t>(firstToken - 1)] == lastToken + 1 &&
               !tokenUsed[static_cast<std::size_t>(lastToken + 1)]) {
            claim(--firstToken);
            claim(++lastToken);
            grouped = true;
        }
        postfixAllowed.push_back(grouped || node.kind == NodeKind::Name || node.kind == NodeKind::Call ||
                                 node.kind == NodeKind::Member || node.kind == NodeKind::MethodCall ||
                                 node.kind == NodeKind::Index);
        bounds.emplace_back(firstToken, lastToken);
        nodes.push_back(std::move(expression));
    }
    if (std::count(used.begin(), used.end(), false) != 1 || used.back() ||
        std::find(edgeUsed.begin(), edgeUsed.end(), false) != edgeUsed.end() ||
        std::find(tokenUsed.begin(), tokenUsed.end(), false) != tokenUsed.end() ||
        bounds.back() != std::pair<std::int64_t, std::int64_t>{0, result.tokens - 1})
        invalid();
    position = end;
    return nodes.back();
}
} // namespace aurora
