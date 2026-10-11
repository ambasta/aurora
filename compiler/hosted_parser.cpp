// Trusted hosted bootstrap boundary. Source snapshots remain immutable and live
// throughout each synchronous call; no owner descriptor or payload pointer is
// constructed, copied or inspected here.
#include "hosted_parser.hpp"
#include "../runtime/hosted_bytes.hpp"
#include <algorithm>
#include <array>
#include <cstddef>
#include <limits>

#ifndef AURORA_HOSTED_PARSER
#error The hosted parser adapter requires AURORA_HOSTED_PARSER
#endif
extern "C" {
void aurora_hosted_parser_create(const void *, void *);
void aurora_hosted_parser_parse(void *, const void *, void *);
std::int64_t aurora_hosted_parser_count(const void *);
void aurora_hosted_parser_read(const void *, std::int64_t, void *);
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
    std::int64_t token = -1, first = -1, second = -1, depth = -1;
};
class Arena {
    hosted::bytes::Region region;
    class Record {
    public:
        std::uint64_t region;
        alignas(8) std::array<std::byte, 88> arena{};
    } record;
    static_assert(sizeof(Record) == 96 && offsetof(Record, arena) == 8);

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
static_assert(sizeof(Result) == 40 && sizeof(Node) == 40);

[[noreturn]] void invalid() {
    throw Error(DiagnosticCode::Internal, "hosted parser returned an invalid result");
}
bool identifier(const std::string &text) {
    const auto first = static_cast<unsigned char>(text.front());
    return (first >= 'a' && first <= 'z') || (first >= 'A' && first <= 'Z') || first == '_';
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
    Arena arena(static_cast<std::uint64_t>(source->text.size()) * 80 + 131072);
    Result result;
    aurora_hosted_parser_parse(arena.data(), &input, &result);
    const auto actualCount = aurora_hosted_parser_count(arena.data());
    if (result.status < Status::Success || result.status >= Status::Invalid || result.count < 0 ||
        result.count != actualCount || result.tokens < 0 ||
        static_cast<std::uint64_t>(result.tokens) >= tokens.size() - position || result.offset < input.offset ||
        result.offset > input.length)
        invalid();
    if (result.status == Status::Unsupported) {
        if (result.root != -1 || result.count != 0 || result.tokens != 0 || result.offset != input.offset)
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
        else if (result.status == Status::DepthLimit)
            message = "expression AST depth exceeds 128";
        else if (result.status == Status::ExpectedEnd)
            message = stop == Stop::CloseParenthesis ? "expected ')'" : "expected ';'";
        else
            invalid();
        throw Error(DiagnosticCode::UnexpectedToken, message + " (found '" + at.text + "')", at.span);
    }
    if (result.tokens == 0 || result.count == 0 || result.count > result.tokens || result.root != result.count - 1 ||
        !(stop == Stop::CloseParenthesis ? at.text == ")"
                                         : at.text == ";" || (stop == Stop::Assignment && at.text == "=")))
        invalid();
    std::vector<ExpressionPtr> nodes;
    std::vector<bool> used;
    nodes.reserve(static_cast<std::size_t>(result.count));
    used.resize(static_cast<std::size_t>(result.count), false);
    for (std::int64_t index = 0; index < result.count; ++index) {
        Node node;
        aurora_hosted_parser_read(arena.data(), index, &node);
        if (node.token < 0 || node.token >= result.tokens || node.depth < 1 || node.depth > 128)
            invalid();
        const auto &token = tokens[position + static_cast<std::size_t>(node.token)];
        std::string op;
        if (node.kind == NodeKind::Name && identifier(token.text) && token.text != "true" && token.text != "false")
            op = "name";
        else if (node.kind == NodeKind::Literal && (token.text == "true" || token.text == "false"))
            op = "bool";
        else if (node.kind == NodeKind::Literal && token.text.front() == '\'')
            op = "byte";
        else if (node.kind == NodeKind::Literal && token.text.front() >= '0' && token.text.front() <= '9')
            op = "number";
        else if (node.kind == NodeKind::Unary && (token.text == "-" || token.text == "!" || token.text == "~"))
            op = "unary";
        else if (node.kind == NodeKind::Binary && binary(token.text))
            op = "binary";
        else
            invalid();
        auto expression = std::make_shared<Expression>(op, token);
        const auto attach = [&](std::int64_t child) {
            if (child < 0 || child >= index || used[static_cast<std::size_t>(child)])
                invalid();
            used[static_cast<std::size_t>(child)] = true;
            const auto &value = nodes[static_cast<std::size_t>(child)];
            expression->depth = std::max(expression->depth, value->depth + 1);
            if (expression->depth > 128)
                invalid();
            expression->args.push_back(value);
        };
        if (node.kind == NodeKind::Unary || node.kind == NodeKind::Binary)
            attach(node.first);
        else if (node.first != -1)
            invalid();
        if (node.kind == NodeKind::Binary)
            attach(node.second);
        else if (node.second != -1)
            invalid();
        if (node.depth != expression->depth)
            invalid();
        nodes.push_back(std::move(expression));
    }
    if (std::count(used.begin(), used.end(), false) != 1 || used.back())
        invalid();
    position = end;
    return nodes.back();
}
} // namespace aurora
