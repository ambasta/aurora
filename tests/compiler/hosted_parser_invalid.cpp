// Adversarial host-only controls: forged records never reach generated Aurora.
// Every failure must preserve the input cursor and release the arena once.
#include "lexer.hpp"
#include "hosted_parser.hpp"
#include "parser.hpp"
#include <array>
#include <cstdint>
#include <cstring>
#include <functional>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <vector>

namespace {
using Words = std::array<std::int64_t, 5>;
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
Words result;
std::vector<Words> records;
std::int64_t count = 0;
int created = 0, parsed = 0, released = 0, read = 0;
std::size_t cases = 0;
void require(bool value, const std::string &message) {
    if (!value)
        throw std::runtime_error(message);
}
void reset() {
    result = {wire(Status::Success), 2, 3, 3, 3};
    records = {{wire(NodeKind::Literal), 0, -1, -1, 1},
               {wire(NodeKind::Literal), 2, -1, -1, 1},
               {wire(NodeKind::Binary), 1, 0, 1, 2}};
    count = 3;
    created = parsed = released = read = 0;
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
        result = {wire(Status::Success), 0, 1, 1, offset + 1};
        count = 1;
        records = {{wire(source[offset] == 'x' ? NodeKind::Name : NodeKind::Literal), 0, -1, -1, 1}};
    }
    std::memcpy(output, result.data(), sizeof(result));
}
extern "C" std::int64_t aurora_hosted_parser_count(const void *) {
    return count;
}
extern "C" void aurora_hosted_parser_read(const void *, std::int64_t index, void *output) {
    require(index >= 0 && static_cast<std::size_t>(index) < records.size(), "adapter requested out-of-range node");
    ++read;
    std::memcpy(output, records[static_cast<std::size_t>(index)].data(), sizeof(Words));
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
                                                           wire(NodeKind::Binary) + 1})
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
                records = {{wire(NodeKind::Literal), token, -1, -1, 1}};
            });
        invalid(
            "consumed interior tokens omitted",
            [] {
                result[3] = result[4] = 5;
                records[1][1] = 4;
            },
            "1+2*3;");
        invalid(
            "unary operand precedes operator",
            [] {
                result = {wire(Status::Success), 1, 2, 2, 2};
                count = 2;
                records = {{wire(NodeKind::Literal), 0, -1, -1, 1}, {wire(NodeKind::Unary), 1, 0, -1, 2}};
            },
            "1-;");
        invalid(
            "subtree source ranges cross",
            [] {
                result = {wire(Status::Success), 4, 5, 5, 5};
                count = 5;
                records = {{wire(NodeKind::Literal), 0, -1, -1, 1},
                           {wire(NodeKind::Literal), 4, -1, -1, 1},
                           {wire(NodeKind::Binary), 1, 0, 1, 2},
                           {wire(NodeKind::Literal), 2, -1, -1, 1},
                           {wire(NodeKind::Binary), 3, 2, 3, 3}};
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
            records[2] = {wire(NodeKind::Literal), 2, -1, -1, 1};
        });
        for (const std::string word : {"true", "false"})
            invalid(
                "boolean forged as Name",
                [&] {
                    result[4] = static_cast<std::int64_t>(word.size()) + 2;
                    records[0][0] = static_cast<std::int64_t>(aurora::hosted_parser::NodeKind::Name);
                },
                word + "+2;");

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
        static_cast<void>(aurora::Parser(aurora::lex("module reference;auto f()->i64{return 1;}"), false).parse());
        require(created == 0 && parsed == 0 && released == 0, "explicit reference parser used a hosted hook");
        std::cout << "PASS hosted parser " << cases << " forged-result/provenance controls and exact cleanup\n";
    } catch (const std::exception &error) {
        std::cerr << "FAIL " << error.what() << '\n';
        return 1;
    }
}
