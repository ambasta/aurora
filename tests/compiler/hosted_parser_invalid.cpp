// Adversarial host-only controls: forged records never reach generated Aurora.
// Every failure must preserve the input cursor and release the arena once.
#include "lexer.hpp"
#include "hosted_parser.hpp"
#include "parser.hpp"
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <functional>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <utility>
#include <vector>

namespace {
using ResultWords = std::array<std::int64_t, 5>;
using NodeWords = std::array<std::int64_t, 7>;
using EdgeWords = std::array<std::int64_t, 4>;
using aurora::hosted_parser::NodeKind;
using aurora::hosted_parser::Status;
using aurora::hosted_parser::Stop;
constexpr std::int64_t wire(Status value) {
    return static_cast<std::int64_t>(value);
}
constexpr std::int64_t wire(NodeKind value) {
    return static_cast<std::int64_t>(value);
}
bool hookControl = false;
std::vector<Stop> hookStops;
ResultWords result;
std::vector<NodeWords> records;
std::vector<EdgeWords> edges;
std::int64_t count = 0, edgeCount = 0;
int created = 0, parsed = 0, released = 0, read = 0, edgeRead = 0;
std::size_t cases = 0;
void require(bool value, const std::string &message) {
    if (!value)
        throw std::runtime_error(message);
}
void reset() {
    result = {wire(Status::Success), 2, 3, 3, 3};
    records = {{wire(NodeKind::Literal), 0, -1, -1, 1, 0, 0},
               {wire(NodeKind::Literal), 2, -1, -1, 1, 2, 2},
               {wire(NodeKind::Binary), 1, 0, 1, 2, 1, 1}};
    count = 3;
    edgeCount = 0;
    edges.clear();
    hookStops.clear();
    created = parsed = released = read = edgeRead = 0;
}
void fixture(const std::string &source, std::vector<NodeWords> nodes, std::vector<EdgeWords> arguments = {}) {
    const auto tokens = aurora::lex(source, "forged.au");
    records = std::move(nodes);
    edges = std::move(arguments);
    count = static_cast<std::int64_t>(records.size());
    edgeCount = static_cast<std::int64_t>(edges.size());
    result = {wire(Status::Success),
              count - 1,
              count,
              static_cast<std::int64_t>(tokens.size()) - 2,
              static_cast<std::int64_t>(tokens[tokens.size() - 2].span.begin.offset)};
}
void callFixture(const std::string &source = "f(1,2);") {
    fixture(source,
            {{wire(NodeKind::Literal), 2, -1, -1, 1, 2, 2},
             {wire(NodeKind::Literal), 4, -1, -1, 1, 4, 4},
             {wire(NodeKind::Call), 0, 1, 2, 2, 0, 5}},
            {{0, -1, 1, 2}, {1, 0, 2, 2}});
}
void methodFixture(const std::string &source = "a.m(1);") {
    fixture(source,
            {{wire(NodeKind::Name), 0, -1, -1, 1, 0, 0},
             {wire(NodeKind::Literal), 4, -1, -1, 1, 4, 4},
             {wire(NodeKind::MethodCall), 2, 1, 2, 2, 2, 5}},
            {{0, -1, 1, 2}, {1, 0, 2, 2}});
}
void indexFixture(const std::string &source = "a[i];") {
    fixture(source,
            {{wire(NodeKind::Name), 0, -1, -1, 1, 0, 0},
             {wire(NodeKind::Name), 2, -1, -1, 1, 2, 2},
             {wire(NodeKind::Index), 1, 0, 1, 2, 1, 3}});
}
void sameExpression(const aurora::ExpressionPtr &actual, const aurora::ExpressionPtr &expected) {
    require(actual && expected && actual->op == expected->op && actual->token.text == expected->token.text &&
                actual->token.line == expected->token.line && actual->depth == expected->depth &&
                actual->args.size() == expected->args.size(),
            "valid forged control changed AST spelling, kind, depth or arguments");
    const auto &a = actual->token.span, &b = expected->token.span;
    require(a.source == b.source && a.begin.offset == b.begin.offset && a.begin.line == b.begin.line &&
                a.begin.column == b.begin.column && a.end.offset == b.end.offset && a.end.line == b.end.line &&
                a.end.column == b.end.column,
            "valid forged control changed token provenance");
    for (std::size_t index = 0; index < actual->args.size(); ++index)
        sameExpression(actual->args[index], expected->args[index]);
}
void valid(const std::string &source, const std::function<void()> &configure) {
    reset();
    configure();
    const auto tokens = aurora::lex(source, "forged.au");
    std::size_t position = 0;
    const auto actual = aurora::parseHostedExpression(tokens, position, Stop::Semicolon);
    sameExpression(actual, aurora::Parser(tokens, false).expr());
    require(position == static_cast<std::size_t>(result[3]) && created == 1 && parsed == 1 && released == 1 &&
                read == count && edgeRead == edgeCount,
            "valid forged control lost cursor, record reads or exact cleanup");
    ++cases;
}
void invalid(const std::string &label, const std::function<void()> &mutate, const std::string &source = "1+2;") {
    reset();
    mutate();
    const auto tokens = aurora::lex(source, "forged.au");
    std::size_t position = 0;
    bool rejected = false;
    try {
        static_cast<void>(aurora::parseHostedExpression(tokens, position, Stop::Semicolon));
    } catch (const aurora::Error &error) {
        rejected = error.diagnostic.code == aurora::DiagnosticCode::Internal &&
                   error.diagnostic.message == "hosted parser returned an invalid result";
    }
    require(rejected && position == 0 && created == 1 && parsed == 1 && released == 1,
            label + ": forged result escaped or changed cursor/cleanup");
    require(tokens.front().span.source->text == source, label + ": immutable source changed");
    ++cases;
}
void diagnostic(const std::string &source, Status status, std::size_t ordinal) {
    reset();
    const auto tokens = aurora::lex(source, "forged.au");
    result = {wire(status),
              -1,
              0,
              static_cast<std::int64_t>(ordinal),
              static_cast<std::int64_t>(tokens[ordinal].span.begin.offset)};
    count = 0;
    std::size_t position = 0;
    std::string message;
    try {
        static_cast<void>(aurora::Parser(tokens, false).expr());
    } catch (const aurora::Error &error) {
        message = error.diagnostic.message;
    }
    require(!message.empty(), "diagnostic control did not reject in reference parser");
    bool rejected = false;
    try {
        static_cast<void>(aurora::parseHostedExpression(tokens, position, Stop::Semicolon));
    } catch (const aurora::Error &error) {
        const auto &span = error.diagnostic.span, &expected = tokens[ordinal].span;
        rejected = error.diagnostic.code == aurora::DiagnosticCode::UnexpectedToken &&
                   error.diagnostic.message == message && span.source == expected.source &&
                   span.begin.offset == expected.begin.offset && span.end.offset == expected.end.offset;
    }
    require(rejected && position == 0 && created == 1 && parsed == 1 && released == 1,
            "diagnostic conversion lost reference message, location, cursor or cleanup");
    ++cases;
}
} // namespace

extern "C" void aurora_hosted_parser_create(const void *input, void *) {
    std::array<std::uint64_t, 2> value{};
    std::memcpy(value.data(), input, sizeof(value));
    require(value[0] != 0 && value[1] == 0, "adapter did not request empty arena with live region");
    ++created;
}
extern "C" void aurora_hosted_parser_parse(void *, const void *input, void *output) {
    ++parsed;
    if (hookControl) {
        std::array<std::uint64_t, 11> value{};
        std::memcpy(value.data(), input, sizeof(value));
        const auto *source = reinterpret_cast<const char *>(value[1]);
        const auto offset = static_cast<std::int64_t>(value[7]);
        const auto lexical = aurora::lex(std::string(source, static_cast<std::size_t>(value[6])), "hook.au");
        const auto token = std::find_if(lexical.begin(), lexical.end(), [&](const auto &item) {
            return item.span.begin.offset == static_cast<std::size_t>(offset);
        });
        require(token != lexical.end() && token + 1 != lexical.end(), "hook cursor is not a source token");
        result = {wire(Status::Success), 0, 1, 1, static_cast<std::int64_t>((token + 1)->span.begin.offset)};
        count = 1;
        records = {{wire(source[offset] == 'x' ? NodeKind::Name : NodeKind::Literal), 0, -1, -1, 1, 0, 0}};
        hookStops.push_back(static_cast<Stop>(value[10]));
    }
    std::memcpy(output, result.data(), sizeof(result));
}
extern "C" std::int64_t aurora_hosted_parser_count(const void *) {
    return count;
}
extern "C" void aurora_hosted_parser_read(const void *, std::int64_t index, void *output) {
    require(index >= 0 && static_cast<std::size_t>(index) < records.size(), "adapter requested out-of-range node");
    ++read;
    std::memcpy(output, records[static_cast<std::size_t>(index)].data(), sizeof(NodeWords));
}
extern "C" std::int64_t aurora_hosted_parser_edges(const void *) {
    return edgeCount;
}
extern "C" void aurora_hosted_parser_edge(const void *, std::int64_t index, void *output) {
    require(index >= 0 && static_cast<std::size_t>(index) < edges.size(), "adapter requested out-of-range edge");
    ++edgeRead;
    std::memcpy(output, edges[static_cast<std::size_t>(index)].data(), sizeof(EdgeWords));
}
extern "C" void aurora_hosted_parser_release(void *) {
    ++released;
}

int main() {
    try {
        reset();
        const auto tokens = aurora::lex("1+2;", "control.au");
        std::size_t position = 0;
        const auto accepted = aurora::parseHostedExpression(tokens, position, Stop::Semicolon);
        require(accepted && accepted->op == "binary" && accepted->args.size() == 2 && accepted->depth == 2 &&
                    position == 3 && created == 1 && parsed == 1 && read == 3 && released == 1,
                "valid control did not convert and commit exactly once");
        for (const auto status :
             {-1LL, static_cast<long long>(wire(Status::Invalid)), static_cast<long long>(wire(Status::Invalid) + 1)})
            invalid("invalid status", [=] {
                result[0] = status;
            });
        invalid("negative count", [] {
            result[2] = count = -1;
        });
        invalid("count disagreement", [] {
            count = 2;
        });
        invalid("count greater than tokens", [] {
            result[2] = count = 4;
            result[1] = 3;
        });
        for (const auto tokenCount : {-1LL, 0LL, 4LL, 5LL, std::numeric_limits<long long>::max()})
            invalid("invalid token progress", [=] {
                result[3] = tokenCount;
            });
        for (const auto offset : {-1LL, 0LL, 2LL, 5LL, std::numeric_limits<long long>::max()})
            invalid("invalid source progress", [=] {
                result[4] = offset;
            });
        for (const auto root : {-1, 0, 1, 3})
            invalid("invalid root", [=] {
                result[1] = root;
            });
        for (std::size_t field = 1; field < 5; ++field)
            invalid("non-atomic fallback", [=] {
                result = {wire(Status::Unsupported), -1, 0, 0, 0};
                count = 0;
                result[field] = 1;
                if (field == 2)
                    count = 1;
            });
        invalid("error with root", [] {
            result[0] = wire(Status::ExpectedExpression);
        });
        for (const auto kind : std::array<std::int64_t, 6>{-1,
                                                           wire(NodeKind::Invalid),
                                                           wire(NodeKind::Name),
                                                           wire(NodeKind::Unary),
                                                           wire(NodeKind::Binary),
                                                           wire(NodeKind::Index) + 1})
            invalid("wrong leaf kind", [=] {
                records[0][0] = kind;
            });
        invalid("literal references operator", [] {
            records[0][1] = 1;
        });
        invalid("binary references literal", [] {
            records[2][1] = 0;
        });
        invalid("two literals reuse one source token", [] {
            records[1][1] = 0;
        });
        invalid("binary operands reverse source order", [] {
            records[2][2] = 1;
            records[2][3] = 0;
        });
        for (const auto token : {0, 2})
            invalid("consumed expression reduced to one leaf", [=] {
                result[1] = 0;
                result[2] = count = 1;
                records = {{wire(NodeKind::Literal), token, -1, -1, 1, token, token}};
            });
        invalid(
            "consumed interior tokens omitted",
            [] {
                result[3] = result[4] = 5;
                records[1][1] = records[1][5] = records[1][6] = 4;
            },
            "1+2*3;");
        invalid(
            "unary operand precedes operator",
            [] {
                result = {wire(Status::Success), 1, 2, 2, 2};
                count = 2;
                records = {{wire(NodeKind::Literal), 0, -1, -1, 1, 0, 0}, {wire(NodeKind::Unary), 1, 0, -1, 2, 1, 1}};
            },
            "1-;");
        invalid(
            "subtree source ranges cross",
            [] {
                result = {wire(Status::Success), 4, 5, 5, 5};
                count = 5;
                records = {{wire(NodeKind::Literal), 0, -1, -1, 1, 0, 0},
                           {wire(NodeKind::Literal), 4, -1, -1, 1, 4, 4},
                           {wire(NodeKind::Binary), 1, 0, 1, 2, 1, 1},
                           {wire(NodeKind::Literal), 2, -1, -1, 1, 2, 2},
                           {wire(NodeKind::Binary), 3, 2, 3, 3, 3, 3}};
            },
            "1+2+3;");
        for (const auto token : {-1, 3, 4})
            invalid("invalid node token", [=] {
                records[0][1] = token;
            });
        for (const auto depth : {0, 2, 129})
            invalid("invalid leaf depth", [=] {
                records[0][4] = depth;
            });
        invalid("invalid computed depth", [] {
            records[2][4] = 3;
        });
        invalid("literal has first child", [] {
            records[0][2] = 0;
        });
        invalid("literal has second child", [] {
            records[0][3] = 0;
        });
        invalid("missing child", [] {
            records[2][2] = -1;
        });
        invalid("forward child", [] {
            records[2][2] = 2;
        });
        invalid("out-of-range child", [] {
            records[2][3] = std::numeric_limits<std::int64_t>::max();
        });
        invalid("reused child", [] {
            records[2][3] = 0;
        });
        invalid("disconnected nodes", [] {
            records[2] = {wire(NodeKind::Literal), 2, -1, -1, 1, 2, 2};
        });
        for (const std::string word : {"true", "false"})
            invalid(
                "boolean forged as Name",
                [&] {
                    result[4] = static_cast<std::int64_t>(word.size()) + 2;
                    records[0][0] = static_cast<std::int64_t>(aurora::hosted_parser::NodeKind::Name);
                },
                word + "+2;");

        for (const std::string source : {R"("";)", R"("\0\xff";)", R"("é😀";)"})
            valid(source, [&] {
                fixture(source, {{wire(NodeKind::Literal), 0, -1, -1, 1, 0, 0}});
            });
        valid(R"(f("text");)", [] {
            fixture(R"(f("text");)",
                    {{wire(NodeKind::Literal), 2, -1, -1, 1, 2, 2}, {wire(NodeKind::Call), 0, 0, 1, 2, 0, 3}},
                    {{0, -1, 1, 2}});
        });
        valid(R"(("x")[0];)", [] {
            fixture(R"(("x")[0];)",
                    {{wire(NodeKind::Literal), 1, -1, -1, 1, 1, 1},
                     {wire(NodeKind::Literal), 4, -1, -1, 1, 4, 4},
                     {wire(NodeKind::Index), 3, 0, 1, 2, 3, 5}});
        });
        invalid(
            "byte string forged as name",
            [] {
                fixture(R"("text";)", {{wire(NodeKind::Name), 0, -1, -1, 1, 0, 0}});
            },
            R"("text";)");
        invalid(
            "bare byte string cannot receive a method",
            [] {
                fixture(R"("x".m();)",
                        {{wire(NodeKind::Literal), 0, -1, -1, 1, 0, 0}, {wire(NodeKind::MethodCall), 2, 0, 1, 2, 2, 4}},
                        {{0, -1, 1, 2}});
            },
            R"("x".m();)");
        invalid(
            "bare byte string cannot receive an index",
            [] {
                fixture(R"("x"[0];)",
                        {{wire(NodeKind::Literal), 0, -1, -1, 1, 0, 0},
                         {wire(NodeKind::Literal), 2, -1, -1, 1, 2, 2},
                         {wire(NodeKind::Index), 1, 0, 1, 2, 1, 3}});
            },
            R"("x"[0];)");

        valid("f(1,2);", [] {
            callFixture();
        });
        valid("a.m(1);", [] {
            methodFixture();
        });
        valid("a[i];", [] {
            indexFixture();
        });
        for (const std::string source : {"foo();", "Widget();", "array();", "if();"})
            valid(source, [&] {
                fixture(source, {{wire(NodeKind::Call), 0, -1, 0, 1, 0, 2}});
            });
        for (const std::string source : {"a::b;", "std::array;", "a // qualification\n :: b;"})
            valid(source, [&] {
                fixture(source, {{wire(NodeKind::Name), 0, -1, -1, 1, 2, 2}});
            });
        valid("std::array();", [] {
            fixture("std::array();", {{wire(NodeKind::Call), 0, -1, 0, 1, 2, 4}});
        });
        valid("a.b;", [] {
            fixture("a.b;", {{wire(NodeKind::Name), 0, -1, -1, 1, 0, 0}, {wire(NodeKind::Member), 2, 0, -1, 2, 2, 2}});
        });
        valid("a.m();", [] {
            fixture("a.m();",
                    {{wire(NodeKind::Name), 0, -1, -1, 1, 0, 0}, {wire(NodeKind::MethodCall), 2, 0, 1, 2, 2, 4}},
                    {{0, -1, 1, 2}});
        });
        valid("(1).m();", [] {
            fixture("(1).m();",
                    {{wire(NodeKind::Literal), 1, -1, -1, 1, 1, 1}, {wire(NodeKind::MethodCall), 4, 0, 1, 2, 4, 6}},
                    {{0, -1, 1, 2}});
        });
        valid("f((1),(2));", [] {
            fixture("f((1),(2));",
                    {{wire(NodeKind::Literal), 3, -1, -1, 1, 3, 3},
                     {wire(NodeKind::Literal), 7, -1, -1, 1, 7, 7},
                     {wire(NodeKind::Call), 0, 1, 2, 2, 0, 9}},
                    {{0, -1, 1, 2}, {1, 0, 2, 2}});
        });
        valid("f(g(1),2);", [] {
            fixture("f(g(1),2);",
                    {{wire(NodeKind::Literal), 4, -1, -1, 1, 4, 4},
                     {wire(NodeKind::Call), 2, 0, 1, 2, 2, 5},
                     {wire(NodeKind::Literal), 7, -1, -1, 1, 7, 7},
                     {wire(NodeKind::Call), 0, 2, 2, 3, 0, 8}},
                    {{0, -1, 1, 2}, {1, -1, 1, 3}, {2, 1, 2, 3}});
        });
        valid("std::f().m()[i].x;", [] {
            fixture("std::f().m()[i].x;",
                    {{wire(NodeKind::Call), 0, -1, 0, 1, 2, 4},
                     {wire(NodeKind::MethodCall), 6, 0, 1, 2, 6, 8},
                     {wire(NodeKind::Name), 10, -1, -1, 1, 10, 10},
                     {wire(NodeKind::Index), 9, 1, 2, 3, 9, 11},
                     {wire(NodeKind::Member), 13, 3, -1, 4, 13, 13}},
                    {{0, -1, 1, 2}});
        });
        valid("(a+b)[i];", [] {
            fixture("(a+b)[i];",
                    {{wire(NodeKind::Name), 1, -1, -1, 1, 1, 1},
                     {wire(NodeKind::Name), 3, -1, -1, 1, 3, 3},
                     {wire(NodeKind::Binary), 2, 0, 1, 2, 2, 2},
                     {wire(NodeKind::Name), 6, -1, -1, 1, 6, 6},
                     {wire(NodeKind::Index), 5, 2, 3, 3, 5, 7}});
        });
        for (std::size_t field : {5U, 6U})
            for (const auto value : {-1LL, 1LL, 3LL, std::numeric_limits<long long>::max()})
                invalid("invalid scalar name/close endpoint", [=] {
                    records[0][field] = value;
                });
        invalid("negative edge count", [] {
            edgeCount = -1;
        });
        invalid("impossible edge count", [] {
            edgeCount = count;
        });
        invalid("fallback retains edges", [] {
            result = {wire(Status::Unsupported), -1, 0, 0, 0};
            count = 0;
            edgeCount = 1;
        });
        for (const auto endpoint : {-1LL, 1LL, 3LL, 5LL, std::numeric_limits<long long>::max()})
            invalid(
                "invalid qualified name endpoint",
                [=] {
                    fixture("a::b;", {{wire(NodeKind::Name), 0, -1, -1, 1, endpoint, endpoint}});
                },
                "a::b;");
        for (const std::string source : {"a+b;", "a.b;", "a::true;", "a::builtin;", "a::__au_x;", "a::class;"})
            invalid(
                "invalid qualified name spelling",
                [&] {
                    fixture(source, {{wire(NodeKind::Name), 0, -1, -1, 1, 2, 2}});
                },
                source);
        invalid(
            "qualified name has child",
            [] {
                fixture("a::b;", {{wire(NodeKind::Name), 0, 0, -1, 1, 2, 2}});
            },
            "a::b;");
        for (const std::string source : {"a.array;", "a.builtin;", "a.true;", "a.__au_x;", "a::b;"})
            invalid(
                "invalid member identifier or dot",
                [&] {
                    fixture(source,
                            {{wire(NodeKind::Name), 0, -1, -1, 1, 0, 0}, {wire(NodeKind::Member), 2, 0, -1, 2, 2, 2}});
                },
                source);
        for (const std::string source : {"size_of(i64);", "type_id(i64);", "field_count(T);"})
            invalid(
                "type-taking reflection forged as call",
                [&] {
                    fixture(source,
                            {{wire(NodeKind::Name), 2, -1, -1, 1, 2, 2}, {wire(NodeKind::Call), 0, 0, 1, 2, 0, 3}},
                            {{0, -1, 1, 2}});
                },
                source);
        for (const auto head : {-2LL, 0LL, 2LL, std::numeric_limits<long long>::max()})
            invalid(
                "invalid argument head",
                [=] {
                    callFixture();
                    records[2][2] = head;
                },
                "f(1,2);");
        for (const auto countValue : {-1LL, 0LL, 1LL, 3LL, std::numeric_limits<long long>::max()})
            invalid(
                "invalid argument count",
                [=] {
                    callFixture();
                    records[2][3] = countValue;
                },
                "f(1,2);");
        for (const auto child : {-1LL, 2LL, 3LL, std::numeric_limits<long long>::max()})
            invalid(
                "invalid edge child",
                [=] {
                    callFixture();
                    edges[0][0] = child;
                },
                "f(1,2);");
        for (const auto previous : {-2LL, 0LL, 1LL, std::numeric_limits<long long>::max()})
            invalid(
                "cyclic or forward argument edge",
                [=] {
                    callFixture();
                    edges[0][1] = previous;
                },
                "f(1,2);");
        for (const auto countValue : {-1LL, 0LL, 1LL, 3LL, std::numeric_limits<long long>::max()})
            invalid(
                "invalid edge count metadata",
                [=] {
                    callFixture();
                    edges[1][2] = countValue;
                },
                "f(1,2);");
        for (const auto depth : {-1LL, 0LL, 1LL, 3LL, 129LL})
            invalid(
                "invalid edge depth metadata",
                [=] {
                    callFixture();
                    edges[1][3] = depth;
                },
                "f(1,2);");
        invalid(
            "reused argument child",
            [] {
                callFixture();
                edges[1][0] = 0;
            },
            "f(1,2);");
        invalid(
            "reversed argument order",
            [] {
                callFixture();
                edges[0][0] = 1;
                edges[1][0] = 0;
            },
            "f(1,2);");
        invalid(
            "disconnected argument edge",
            [] {
                callFixture();
                records[2][2] = 0;
                records[2][3] = 1;
            },
            "f(1,2);");
        invalid(
            "two calls reuse an argument edge",
            [] {
                fixture("f(1)+g(2);",
                        {{wire(NodeKind::Literal), 2, -1, -1, 1, 2, 2},
                         {wire(NodeKind::Call), 0, 0, 1, 2, 0, 3},
                         {wire(NodeKind::Literal), 7, -1, -1, 1, 7, 7},
                         {wire(NodeKind::Call), 5, 0, 1, 2, 5, 8},
                         {wire(NodeKind::Binary), 4, 1, 3, 3, 4, 4}},
                        {{0, -1, 1, 2}, {2, -1, 1, 2}});
            },
            "f(1)+g(2);");
        invalid(
            "call has wrong depth",
            [] {
                callFixture();
                records[2][4] = 3;
            },
            "f(1,2);");
        invalid(
            "argument edge skips earlier link",
            [] {
                callFixture();
                edges[1][1] = -1;
            },
            "f(1,2);");
        for (const auto close : {-1LL, 2LL, 4LL, 6LL, std::numeric_limits<long long>::max()})
            invalid(
                "invalid call close",
                [=] {
                    callFixture();
                    records[2][6] = close;
                },
                "f(1,2);");
        for (const std::string source : {"f[1,2];", "f(1+2);", "f(1;2);", "f(1,2];"})
            invalid(
                "malformed call punctuation",
                [&] {
                    callFixture(source);
                },
                source);
        invalid(
            "call omits trailing comma",
            [] {
                fixture("f(1,);",
                        {{wire(NodeKind::Literal), 2, -1, -1, 1, 2, 2}, {wire(NodeKind::Call), 0, 0, 1, 2, 0, 4}},
                        {{0, -1, 1, 2}});
            },
            "f(1,);");
        invalid(
            "call arguments lack comma",
            [] {
                fixture("f(1 2);",
                        {{wire(NodeKind::Literal), 2, -1, -1, 1, 2, 2},
                         {wire(NodeKind::Literal), 3, -1, -1, 1, 3, 3},
                         {wire(NodeKind::Call), 0, 1, 2, 2, 0, 4}},
                        {{0, -1, 1, 2}, {1, 0, 2, 2}});
            },
            "f(1 2);");
        invalid(
            "method has no receiver",
            [] {
                methodFixture();
                records[2][2] = -1;
                records[2][3] = 0;
            },
            "a.m(1);");
        invalid(
            "method receiver follows dot",
            [] {
                methodFixture();
                edges[0][0] = 1;
                edges[1][0] = 0;
            },
            "a.m(1);");
        invalid(
            "method receiver is self",
            [] {
                methodFixture();
                edges[0][0] = 2;
            },
            "a.m(1);");
        invalid(
            "member has second child",
            [] {
                fixture("a.b;",
                        {{wire(NodeKind::Name), 0, -1, -1, 1, 0, 0}, {wire(NodeKind::Member), 2, 0, 0, 2, 2, 2}});
            },
            "a.b;");
        invalid(
            "ungrouped literal cannot receive postfix",
            [] {
                fixture("1.m();",
                        {{wire(NodeKind::Literal), 0, -1, -1, 1, 0, 0}, {wire(NodeKind::MethodCall), 2, 0, 1, 2, 2, 4}},
                        {{0, -1, 1, 2}});
            },
            "1.m();");
        for (const std::string source : {"a(i);", "a[i);", "a[i[;"})
            invalid(
                "invalid index delimiters",
                [&] {
                    indexFixture(source);
                },
                source);
        invalid(
            "index swapped operands",
            [] {
                indexFixture();
                records[2][2] = 1;
                records[2][3] = 0;
            },
            "a[i];");
        invalid(
            "index missing operand",
            [] {
                indexFixture();
                records[2][3] = -1;
            },
            "a[i];");
        invalid(
            "index incorrect name endpoint",
            [] {
                indexFixture();
                records[2][5] = 2;
            },
            "a[i];");
        invalid(
            "index close reuses token",
            [] {
                indexFixture();
                records[2][6] = 1;
            },
            "a[i];");
        for (const std::string source : {"(1;", "1);", "((1);", "(1));", "()1;", "1();"})
            invalid(
                "unmatched or empty grouping cannot be ignored",
                [&] {
                    const auto lexical = aurora::lex(source);
                    std::int64_t ordinal = 0;
                    while (lexical[static_cast<std::size_t>(ordinal)].text != "1")
                        ++ordinal;
                    fixture(source, {{wire(NodeKind::Literal), ordinal, -1, -1, 1, ordinal, ordinal}});
                },
                source);
        diagnostic("a[1;", Status::ExpectedIndexClose, 3);
        diagnostic("a.;", Status::ExpectedIdentifier, 2);
        diagnostic("a.if;", Status::ReservedIdentifier, 2);
        diagnostic("a.array;", Status::ReservedBuiltin, 2);
        diagnostic("a.__au_x;", Status::ReservedPrefix, 2);
        diagnostic("a::true;", Status::ReservedIdentifier, 2);

        reset();
        result = {wire(Status::Unsupported), -1, 0, 0, 0};
        count = 0;
        position = 0;
        require(!aurora::parseHostedExpression(tokens, position, Stop::Semicolon) && position == 0 && released == 1,
                "valid unsupported control did not preserve position and cleanup");
        reset();
        result = {wire(Status::AllocationFailure), -1, 0, 0, 0};
        count = 0;
        position = 0;
        bool allocationFailure = false;
        try {
            static_cast<void>(aurora::parseHostedExpression(tokens, position, Stop::Semicolon));
        } catch (const aurora::Error &error) {
            allocationFailure = error.diagnostic.code == aurora::DiagnosticCode::Internal &&
                                error.diagnostic.message == "hosted parser allocation failed";
        }
        require(allocationFailure && position == 0 && released == 1, "allocation error lost cursor/cleanup");

        for (int mode = 0; mode < 4; ++mode) {
            reset();
            auto corrupted = tokens;
            if (mode == 0)
                corrupted[1].text = "-";
            else if (mode == 1)
                corrupted[1].span.source = std::make_shared<const aurora::SourceText>("other.au", "1+2;");
            else if (mode == 2)
                corrupted[1].span.begin.offset = 0;
            else
                corrupted[1].span.end.offset = 100;
            position = 0;
            bool rejected = false;
            try {
                static_cast<void>(aurora::parseHostedExpression(corrupted, position, Stop::Semicolon));
            } catch (const aurora::Error &error) {
                rejected = error.diagnostic.code == aurora::DiagnosticCode::Internal;
            }
            require(rejected && position == 0 && released == 1, "inconsistent token provenance accepted");
            ++cases;
        }
        reset();
        hookControl = true;
        const auto hooks =
            aurora::Parser(
                aurora::lex("module hooks;auto f()->i64{i64 x=1;x=1;1;static_assert(1);if(1){}while(1){}return 1;}"),
                true)
                .parse();
        hookControl = false;
        require(hooks.functions.size() == 1 && parsed == 8 && created == 8 && released == 8,
                "a statement hook bypassed hosted dispatch or lost cleanup");
        reset();
        hookControl = true;
        const auto constructors =
            aurora::Parser(aurora::lex("export module hooks;class Hook{i64 first;i64 second;array<u8,2> bytes;public:"
                                       "Hook(i64 x):first(x),second(1),bytes(\"ok\"){}auto get()->i64{return 1;}};"),
                           true)
                .parse();
        hookControl = false;
        require(constructors.classes.size() == 1 && constructors.classes[0].methods.size() == 2 &&
                    constructors.classes[0].methods[0].initializers.size() == 3 && parsed == 4 && created == 4 &&
                    released == 4 &&
                    hookStops ==
                        std::vector<Stop>{
                            Stop::CloseParenthesis, Stop::CloseParenthesis, Stop::CloseParenthesis, Stop::Semicolon},
                "constructor initializer bypassed hosted dispatch or lost its stopping context");
        reset();
        hookControl = true;
        static_cast<void>(
            aurora::Parser(aurora::lex("export module hooks;class Hook{array<i64,1> value;public:Hook():value{1}{}};"),
                           true)
                .parse());
        hookControl = false;
        require(created == 0 && parsed == 0 && released == 0, "brace initializer changed its excluded entry path");
        reset();
        static_cast<void>(aurora::Parser(aurora::lex("module reference;auto f()->i64{return 1;}"), false).parse());
        require(created == 0 && parsed == 0 && released == 0, "explicit reference parser used a hosted hook");
        std::cout << "PASS hosted parser " << cases << " forged-result/provenance controls and exact cleanup\n";
    } catch (const std::exception &error) {
        std::cerr << "FAIL " << error.what() << '\n';
        return 1;
    }
}
