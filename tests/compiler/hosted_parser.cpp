// Exercise the real Aurora phase and compare complete ASTs/diagnostics with the
// retained C++ parser. Raw records are deliberately independent of the adapter.
#include "lexer.hpp"
#include "parser.hpp"
#include "hosted_parser.hpp"
#include "../../runtime/hosted_bytes.hpp"
#include <array>
#include <cerrno>
#include <csignal>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <optional>
#include <stdexcept>
#include <string>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>

#if !defined(AURORA_HOSTED_PARSER) || !defined(AURORA_HOSTED_LEXER)
#error The hosted parser fixture must link the real Aurora frontend
#endif
extern "C" {
void checked_hosted_parser_create(const void *, void *);
void checked_hosted_parser_parse(void *, const void *, void *);
std::int64_t checked_hosted_parser_count(const void *);
void checked_hosted_parser_read(const void *, std::int64_t, void *);
std::int64_t checked_hosted_parser_edges(const void *);
void checked_hosted_parser_edge(const void *, std::int64_t, void *);
void checked_hosted_parser_release(void *);
}

using AbiEntry = void (*)(const void *, const void *, void *);
extern "C" {
void checked_hosted_parser_call(const void *, const void *, void *, AbiEntry);
void hosted_parser_clobber_rbp(const void *, const void *, void *);
void hosted_parser_clobber_rbx(const void *, const void *, void *);
void hosted_parser_clobber_r12(const void *, const void *, void *);
void hosted_parser_clobber_r13(const void *, const void *, void *);
void hosted_parser_clobber_r14(const void *, const void *, void *);
void hosted_parser_clobber_r15(const void *, const void *, void *);
void hosted_parser_clobber_canary(const void *, const void *, void *);
void hosted_parser_shift_stack(const void *, const void *, void *);
void hosted_parser_misaligned_call(const void *, const void *, void *, AbiEntry);
}

namespace {
using aurora::hosted_parser::NodeKind;
using aurora::hosted_parser::Status;
using aurora::hosted_parser::Stop;
using Words = std::array<std::int64_t, 5>;
using NodeWords = std::array<std::int64_t, 7>;
using EdgeWords = std::array<std::int64_t, 4>;
constexpr std::int64_t wire(NodeKind value) {
    return static_cast<std::int64_t>(value);
}
constexpr std::int64_t wire(Status value) {
    return static_cast<std::int64_t>(value);
}
constexpr std::uint64_t canary = 0xa3159f274c86be02ULL;
std::size_t cases = 0;
std::string context;
void require(bool value, const std::string &message) {
    if (!value)
        throw std::runtime_error(context + ": " + message);
}
void samePosition(const aurora::SourcePosition &a, const aurora::SourcePosition &b) {
    require(a.offset == b.offset && a.line == b.line && a.column == b.column, "source position differs");
}
void sameSpan(const aurora::SourceSpan &a, const aurora::SourceSpan &b) {
    require(a.source == b.source, "source snapshot identity differs");
    samePosition(a.begin, b.begin);
    samePosition(a.end, b.end);
}
void sameExpression(const aurora::ExpressionPtr &a, const aurora::ExpressionPtr &b) {
    require(bool(a) == bool(b), "expression presence differs");
    if (!a)
        return;
    require(a->op == b->op && a->depth == b->depth && a->token.text == b->token.text &&
                a->token.line == b->token.line && a->args.size() == b->args.size() && a->fieldNames == b->fieldNames &&
                a->templateArguments.size() == b->templateArguments.size(),
            "expression shape/spelling/depth differs");
    sameSpan(a->token.span, b->token.span);
    for (std::size_t i = 0; i < a->args.size(); ++i)
        sameExpression(a->args[i], b->args[i]);
}
std::size_t nodes(const aurora::ExpressionPtr &expression) {
    std::size_t count = 1;
    for (const auto &child : expression->args)
        count += nodes(child);
    return count;
}
void sameStatements(const std::vector<aurora::StatementPtr> &a, const std::vector<aurora::StatementPtr> &b) {
    require(a.size() == b.size(), "statement count differs");
    for (std::size_t i = 0; i < a.size(); ++i) {
        require(a[i]->kind == b[i]->kind && a[i]->name == b[i]->name && a[i]->fieldName == b[i]->fieldName &&
                    a[i]->mutableValue == b[i]->mutableValue,
                "statement shape differs");
        sameSpan(a[i]->token.span, b[i]->token.span);
        sameSpan(a[i]->bindingSpan, b[i]->bindingSpan);
        sameExpression(a[i]->expr, b[i]->expr);
        sameExpression(a[i]->target, b[i]->target);
        sameStatements(a[i]->body, b[i]->body);
        sameStatements(a[i]->other, b[i]->other);
    }
}
void compareProgram(const std::string &source, bool valid = true) {
    context = source;
    const auto tokens = aurora::lex(source, "parser-differential.au");
    std::array<std::optional<aurora::Program>, 2> programs;
    std::array<std::optional<aurora::Diagnostic>, 2> errors;
    for (std::size_t i = 0; i < 2; ++i) {
        try {
            programs[i] = aurora::Parser(tokens, i == 0).parse();
        } catch (const aurora::Error &error) {
            errors[i] = error.diagnostic;
        }
    }
    require(bool(programs[0]) == valid && bool(programs[1]) == valid, "acceptance differs from reference/expectation");
    if (!valid) {
        require(errors[0] && errors[1], "missing exact rejection");
        require(errors[0]->code == errors[1]->code && errors[0]->message == errors[1]->message,
                "diagnostic code/message differs: " + errors[0]->message + " versus " + errors[1]->message);
        sameSpan(errors[0]->span, errors[1]->span);
    } else {
        require(programs[0]->functions.size() == programs[1]->functions.size(), "function count differs");
        for (std::size_t i = 0; i < programs[0]->functions.size(); ++i)
            sameStatements(programs[0]->functions[i].body, programs[1]->functions[i].body);
    }
    ++cases;
}
std::string chain(std::size_t count) {
    std::string result = "1";
    while (--count)
        result += "+1";
    return result;
}
void supported(const std::string &text, Stop stop = Stop::Semicolon) {
    context = text;
    const auto tokens = aurora::lex(text, "supported.au");
    std::size_t position = 0;
    const auto hosted = aurora::parseHostedExpression(tokens, position, stop);
    require(bool(hosted), "supported expression silently fell back");
    aurora::Parser reference(tokens, false);
    const auto expected = reference.expr();
    sameExpression(hosted, expected);
    require(tokens[position].text == reference.peek().text, "committed token cursor differs");
    if (text == chain(100) + ";")
        require(nodes(hosted) == 199 && hosted->depth == 100, "100 terms did not yield 199 real Aurora nodes");
    ++cases;
}
void unsupported(const std::string &text) {
    context = text;
    const auto tokens = aurora::lex(text, "unsupported.au");
    const auto before = tokens;
    std::size_t position = 0;
    require(!aurora::parseHostedExpression(tokens, position, Stop::Semicolon),
            "unsupported expression was partially accepted");
    require(position == 0 && tokens.size() == before.size(), "fallback was not atomic");
    for (std::size_t i = 0; i < tokens.size(); ++i) {
        require(tokens[i].text == before[i].text, "fallback changed a token");
        sameSpan(tokens[i].span, before[i].span);
    }
    compareProgram("module fallback; auto f()->i64{return " + text + "}");
}

class Allocations {
public:
    std::size_t allowed = std::numeric_limits<std::size_t>::max(), successful = 0, released = 0;
    static void *allocate(void *context, std::size_t bytes) noexcept {
        auto &state = *static_cast<Allocations *>(context);
        if (state.successful >= state.allowed)
            return nullptr;
        auto *result = std::malloc(bytes);
        if (result)
            ++state.successful;
        return result;
    }
    static void deallocate(void *context, void *address) noexcept {
        ++static_cast<Allocations *>(context)->released;
        std::free(address);
    }
    aurora::hosted::bytes::Allocator allocator() {
        return {this, allocate, deallocate};
    }
};
template <std::size_t N> class GuardedWords {
public:
    std::uint64_t before = canary;
    std::array<std::int64_t, N> value{};
    std::uint64_t after = canary;
    void check() const {
        require(before == canary && after == canary, "result write escaped its ABI extent");
    }
};
static_assert(sizeof(Words) == 40 && sizeof(GuardedWords<5>) == 56 && sizeof(GuardedWords<7>) == 72 &&
              sizeof(GuardedWords<4>) == 48);
class RawArena {
    aurora::hosted::bytes::Region region;
    // This storage is never copied or inspected as an owner descriptor. Aurora
    // constructs and consumes it; the host only supplies region identity.
    std::uint64_t before = canary;
    std::array<std::uint64_t, 17> record{};
    std::uint64_t after = canary;
    bool active = true;

public:
    explicit RawArena(Allocations &allocations, std::uint64_t quota = 1048576, std::int64_t initial = 0)
        : region(quota, allocations.allocator()) {
        record[0] = region.id();
        const std::array<std::uint64_t, 2> input{region.id(), static_cast<std::uint64_t>(initial)};
        checked_hosted_parser_create(input.data(), data());
        guards();
    }
    ~RawArena() {
        if (active)
            checked_hosted_parser_release(record.data());
    }
    RawArena(const RawArena &) = delete;
    RawArena &operator=(const RawArena &) = delete;
    void *data() {
        return record.data() + 1;
    }
    void guards() const {
        require(before == canary && after == canary, "arena write escaped its ABI extent");
    }
    Words parse(const std::string &source, Stop stop = Stop::Semicolon, std::int64_t offset = 0) {
        const std::array<std::uint64_t, 11> input{0,
                                                  reinterpret_cast<std::uintptr_t>(source.data()),
                                                  0,
                                                  0,
                                                  0,
                                                  0,
                                                  source.size(),
                                                  static_cast<std::uint64_t>(offset),
                                                  1,
                                                  0,
                                                  static_cast<std::uint64_t>(stop)};
        GuardedWords<5> output;
        checked_hosted_parser_parse(data(), input.data(), output.value.data());
        output.check();
        guards();
        require(output.value[2] == checked_hosted_parser_count(data()),
                "reported arena count differs from real storage");
        return output.value;
    }
    NodeWords read(std::int64_t index) {
        GuardedWords<7> output;
        checked_hosted_parser_read(data(), index, output.value.data());
        output.check();
        guards();
        return output.value;
    }
    std::int64_t edges() {
        return checked_hosted_parser_edges(data());
    }
    EdgeWords edge(std::int64_t index) {
        GuardedWords<4> output;
        checked_hosted_parser_edge(data(), index, output.value.data());
        output.check();
        guards();
        return output.value;
    }
    aurora::hosted::bytes::Metrics metrics() const {
        return region.metrics();
    }
    void finish() {
        checked_hosted_parser_release(record.data());
        active = false;
        guards();
        const auto final = region.metrics();
        require(final.used == 0 && final.live_allocations == 0 && final.releases == final.successful_allocations,
                "Aurora cleanup leaked payload or ownership metadata");
        require(region.close(), "empty parser region did not close");
    }
};
void rawCase(const std::string &source, Status expected, Stop stop = Stop::Semicolon) {
    context = "raw ABI " + source;
    Allocations allocations;
    RawArena arena(allocations);
    const auto result = arena.parse(source, stop);
    require(result[0] == static_cast<std::int64_t>(expected), "raw status enum differs");
    if (expected == Status::Unsupported)
        require(result == Words{wire(Status::Unsupported), -1, 0, 0, 0}, "raw fallback was not empty and atomic");
    arena.finish();
    require(allocations.released == allocations.successful, "host allocator did not observe exact cleanup");
    ++cases;
}
void abiControls() {
    context = "independent ABI envelope controls";
    const rlimit noCore{0, 0};
    require(setrlimit(RLIMIT_CORE, &noCore) == 0, "cannot disable negative-control core dumps");
    const std::array<AbiEntry, 8> controls{hosted_parser_clobber_rbp,
                                           hosted_parser_clobber_rbx,
                                           hosted_parser_clobber_r12,
                                           hosted_parser_clobber_r13,
                                           hosted_parser_clobber_r14,
                                           hosted_parser_clobber_r15,
                                           hosted_parser_clobber_canary,
                                           hosted_parser_shift_stack};
    for (std::size_t i = 0; i <= controls.size(); ++i) {
        const auto child = fork();
        require(child >= 0, "cannot fork ABI control");
        if (child == 0) {
            if (i < controls.size())
                checked_hosted_parser_call(nullptr, nullptr, nullptr, controls[i]);
            else
                hosted_parser_misaligned_call(nullptr, nullptr, nullptr, controls[0]);
            _exit(0);
        }
        int status = 0;
        pid_t observed;
        do {
            observed = waitpid(child, &status, 0);
        } while (observed < 0 && errno == EINTR);
        require(observed == child && WIFSIGNALED(status) && WTERMSIG(status) == SIGILL,
                "ABI corruption did not produce SIGILL: " + std::to_string(i));
    }
}
void rawGrowth() {
    context = "real Aurora growth and ABI node records";
    const auto source = chain(100) + ";";
    std::size_t successful = 0;
    {
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(source);
        require(result == Words{wire(Status::Success), 198, 199, 199, 199},
                "100-term raw parse did not return exact graph/cursor");
        for (std::int64_t i = 0; i < 199; ++i) {
            const auto node = arena.read(i);
            if (i == 0)
                require(node == NodeWords{wire(NodeKind::Literal), 0, -1, -1, 1, 0, 0}, "first literal ABI differs");
            else if (i % 2 == 1)
                require(node == NodeWords{wire(NodeKind::Literal), i + 1, -1, -1, 1, i + 1, i + 1},
                        "literal ABI differs");
            else
                require(node == NodeWords{wire(NodeKind::Binary), i - 1, i - 2, i - 1, i / 2 + 1, i - 1, i - 1},
                        "binary ABI/topology/depth differs");
        }
        const auto used = arena.metrics();
        require(used.successful_allocations > 4 && used.peak_live_allocations == 3 && used.live_allocations == 3,
                "parser did not grow its node/frame stores while retaining the empty edge owner");
        successful = allocations.successful;
        arena.finish();
        require(allocations.released == successful, "success cleanup mismatch");
    }
    for (std::size_t allowed = 0; allowed < 3; ++allowed) {
        Allocations allocations;
        allocations.allowed = allowed;
        RawArena arena(allocations);
        require(arena.parse("\"text\";")[0] == wire(Status::AllocationFailure),
                "failed arena allocation silently fell back on unsupported syntax");
        arena.finish();
    }
    // Refuse every allocation in sequence, including frame and node growth.
    // All partial graphs still leave all three owners releasable exactly once.
    for (std::size_t allowed = 0; allowed < successful; ++allowed) {
        Allocations allocations;
        allocations.allowed = allowed;
        RawArena arena(allocations);
        const auto result = arena.parse(source);
        require(result[0] == static_cast<std::int64_t>(Status::AllocationFailure) && result[1] == -1,
                "injected allocation/growth failure did not fail closed");
        if (result[2] > 0)
            require(arena.read(0) == NodeWords{wire(NodeKind::Literal), 0, -1, -1, 1, 0, 0},
                    "failed growth changed an already committed node");
        arena.finish();
        require(allocations.successful == allocations.released, "failure cleanup mismatch");
    }
    {
        Allocations allocations;
        RawArena arena(allocations, 0);
        require(arena.parse("1;")[0] == static_cast<std::int64_t>(Status::AllocationFailure), "quota failure accepted");
        arena.finish();
    }
    for (const auto &[sourceText, expected] :
         std::array<std::pair<std::string, NodeWords>, 4>{{{"name;", {wire(NodeKind::Name), 0, -1, -1, 1, 0, 0}},
                                                           {"true;", {wire(NodeKind::Literal), 0, -1, -1, 1, 0, 0}},
                                                           {"'x';", {wire(NodeKind::Literal), 0, -1, -1, 1, 0, 0}},
                                                           {"-1;", {wire(NodeKind::Unary), 0, 0, -1, 2, 0, 0}}}}) {
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(sourceText);
        require(result[0] == wire(Status::Success) && arena.read(result[1]) == expected,
                "real generated node kind ABI differs");
        arena.finish();
    }
    {
        Allocations allocations;
        RawArena arena(allocations);
        require(arena.parse("1;", Stop::Semicolon, 3)[0] == wire(Status::Invalid),
                "invalid lexer cursor did not return the named Invalid status");
        arena.finish();
    }
    ++cases;
}
void rawFrameGrowth() {
    context = "real Aurora explicit-frame growth and failure cleanup";
    const auto source = std::string(127, '(') + "1" + std::string(127, ')') + ";";
    const NodeWords literal{wire(NodeKind::Literal), 127, -1, -1, 1, 127, 127};
    std::size_t successful = 0;
    {
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(source);
        require(result == Words{wire(Status::Success), 0, 1, 255, 255} && arena.read(0) == literal,
                "127 nested groups did not return the exact leaf graph/cursor");
        const auto used = arena.metrics();
        // One leaf needs only the first eight-node capacity. Payload above the
        // first eight-frame plus eight-node capacities therefore proves actual
        // explicit-frame growth, independently of the allocation count.
        require(used.peak_used > 8 * 32 + 8 * 56 && used.successful_allocations > 4 &&
                    used.peak_live_allocations == 3 && used.live_allocations == 3,
                "nested parser did not grow its explicit frame owner");
        successful = allocations.successful;
        arena.finish();
        require(allocations.released == successful, "nested success cleanup mismatch");
    }
    for (std::size_t allowed = 0; allowed < successful; ++allowed) {
        Allocations allocations;
        allocations.allowed = allowed;
        RawArena arena(allocations);
        const auto result = arena.parse(source);
        require(result[0] == wire(Status::AllocationFailure) && result[1] == -1,
                "injected frame-growth failure did not fail closed");
        if (result[2] > 0)
            require(arena.read(0) == literal, "failed frame growth changed an already committed node");
        arena.finish();
        require(allocations.successful == allocations.released, "frame-growth failure cleanup mismatch");
    }
    ++cases;
}
void rawArguments() {
    context = "real argument-edge growth and failure cleanup";
    constexpr std::int64_t count = 257;
    std::string source = "f(";
    for (std::int64_t index = 0; index < count; ++index) {
        if (index)
            source += ',';
        source += '1';
    }
    source += ");";
    std::size_t successful = 0;
    {
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(source);
        require(result == Words{wire(Status::Success), count, count + 1, 2 * count + 2, 2 * count + 2},
                "wide call did not return the complete graph/cursor");
        require(arena.edges() == count &&
                    arena.read(count) == NodeWords{wire(NodeKind::Call), 0, count - 1, count, 2, 0, 2 * count + 1},
                "call ABI, arity or closing-token provenance differs");
        for (std::int64_t index = 0; index < count; ++index)
            require(arena.edge(index) == EdgeWords{index, index - 1, index + 1, 2},
                    "reverse-linked argument ABI differs");
        const auto metrics = arena.metrics();
        require(metrics.successful_allocations > 10 && metrics.live_allocations == 3 &&
                    metrics.peak_live_allocations == 3,
                "wide call did not grow independent node and argument owners");
        successful = allocations.successful;
        arena.finish();
    }
    for (std::size_t allowed = 0; allowed < successful; ++allowed) {
        Allocations allocations;
        allocations.allowed = allowed;
        RawArena arena(allocations);
        const auto result = arena.parse(source);
        require(result[0] == wire(Status::AllocationFailure) && result[1] == -1,
                "injected argument allocation failure did not reject");
        arena.finish();
        require(allocations.successful == allocations.released, "partial argument graph leaked an owner");
    }
    for (const auto &[text, expected] :
         std::array<std::pair<std::string, NodeWords>, 4>{{{"ns::f(1,2);", {wire(NodeKind::Call), 0, 1, 2, 2, 2, 7}},
                                                           {"obj.m();", {wire(NodeKind::MethodCall), 2, 0, 1, 2, 2, 4}},
                                                           {"a.b;", {wire(NodeKind::Member), 2, 0, -1, 2, 2, 2}},
                                                           {"a[0];", {wire(NodeKind::Index), 1, 0, 1, 2, 1, 3}}}}) {
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(text);
        require(result[0] == wire(Status::Success) && arena.read(result[1]) == expected,
                "postfix generated-code node ABI differs");
        arena.finish();
    }
    supported(source);
    ++cases;
}
} // namespace

int main() {
    try {
        for (const auto &expression :
             {"1;",
              "false;",
              "true;",
              "name;",
              "_value;",
              "'x';",
              "'\\n';",
              "123u64;",
              "255u8;",
              "-1 + ~2 * !false;",
              "a || b && c | d ^ e & f == g != h < i <= j > k >= l << m >> n + o - p * q / r % s;",
              "(a + b) * (c - d);",
              "(a);",
              "1 // comment\n + 2;",
              "a < b >> (c);"})
            supported(expression);
        supported("true < x > (y);");
        supported("(a) < b > (c);");
        supported(chain(100) + ";");
        supported(chain(128) + ";");
        supported(std::string(127, '(') + "1" + std::string(127, ')') + ";");
        supported(std::string(127, '-') + "1;");
        supported("1 + 2)", Stop::CloseParenthesis);
        supported("target = 2;", Stop::Assignment);
        supported("1 + 2;", Stop::Assignment);
        for (const auto &expression : {"f();",
                                       "f(1, 2);",
                                       "name.member;",
                                       "name.at(1);",
                                       "one::two;",
                                       "a[1];",
                                       "f(g(1), h(2, 3)) + object.at(index + 1);",
                                       "Box(42);",
                                       "move(value);",
                                       "one // name trivia\n :: two(1, other.run()).field[2].at(3);",
                                       "((a)).field;",
                                       "(a + b)[(i)];",
                                       "a[one::index(f(1))].method().field;",
                                       "builtin::borrow_bytes(value);",
                                       "one::array(1);",
                                       "object.size_of();",
                                       "ns::size_of(i64);",
                                       "-object.at(1) + f(2);",
                                       "fn;",
                                       "__au_name;"})
            supported(expression);
        supported("a[1] = 2;", Stop::Assignment);
        supported("f(a[1], b.member))", Stop::CloseParenthesis);
        for (const auto &expression : {"\"text\";",
                                       "Box{.value=1};",
                                       "{1,2};",
                                       "f(\"text\");",
                                       "f(Box{.value=1});",
                                       "size_of(i64);",
                                       "type_id(array<u8,2>);",
                                       "field_count(Box);",
                                       "f(size_of(i64));"})
            unsupported(expression);
        compareProgram("module templates; auto f()->i64{return f<i64>(1);}");
        compareProgram("module templates; auto f()->i64{return x<y<z>>(a);}");
        compareProgram("module templates; auto f()->i64{return f<T)>(0);}", false);
        compareProgram("module templates; auto f()->i64{if(f<T)>(0)){return 1;}return 0;}", false);
        compareProgram("module templates; auto f()->i64{return f<a<b<c>>>(0);}");
        compareProgram("module templates; auto f()->i64{return f<a<b<c>>(0);}");
        for (const auto &expression : {"(f<T)>(0)", "f<T]>(0)", "f<T:>(0)"})
            compareProgram("module errors; auto f()->i64{return " + std::string(expression) + ";}", false);
        compareProgram("module hooks; auto f()->i64 { i64 x = 1+2; const i64 y = 3; x = x+y; x+1; "
                       "static_assert(true && !false); if(x>0){x=x-1;}else{x=0;} while(x<4){x=x+1;} return x*2; }");
        compareProgram("module fallback; auto f()->i64 { i64 x=f(1); x=f(2); if(f(1)){return f(2);} "
                       "while(f(0)){x=f(3);} static_assert(f(1)); return x<y<z>>(a); }");
        for (const auto &expression : {";",
                                       "1 + ;",
                                       "(1 + 2;",
                                       "1 2;",
                                       "1 +",
                                       "(1) + ;",
                                       ":;",
                                       "];",
                                       ",;",
                                       "1:2;",
                                       "1]2;",
                                       "1,2;",
                                       "1(2);",
                                       "true(2);",
                                       "(1)(2);"})
            compareProgram("module errors; auto f()->i64{return " + std::string(expression) + "}", false);
        compareProgram("module depth; auto f()->i64{return " + chain(129) + ";}", false);
        compareProgram(
            "module depth; auto f()->i64{return " + std::string(128, '(') + "1" + std::string(128, ')') + ";}", false);
        compareProgram("module depth; auto f()->i64{return " + std::string(128, '-') + "1;}", false);
        for (const auto &expression : {"f(;",
                                       "f(1;",
                                       "f(1,);",
                                       "f(,);",
                                       "f(1 2);",
                                       "a.;",
                                       "a..b;",
                                       "a.true;",
                                       "a.array;",
                                       "a.builtin;",
                                       "a.__au_private;",
                                       "name::;",
                                       "name::true;",
                                       "name::builtin;",
                                       "name::__au_x;",
                                       "a[;",
                                       "a[];",
                                       "a[1;",
                                       "a[1);",
                                       "a[1,2];",
                                       "f(1)(2);"})
            compareProgram("module errors; auto f()->i64{return " + std::string(expression) + "}", false);
        std::string members = "a", indices = "a", calls = "1";
        for (int i = 0; i < 127; ++i) {
            members += ".field";
            indices += "[0]";
            calls = "f(" + calls + ")";
        }
        supported(members + ";");
        supported(indices + ";");
        supported(calls + ";");
        compareProgram("module depth; auto f()->i64{return " + members + ".field;}", false);
        compareProgram("module depth; auto f()->i64{return " + indices + "[0];}", false);
        compareProgram("module depth; auto f()->i64{return f(" + calls + ");}", false);
        rawCase("1;", Status::Success);
        rawCase("\"text\";", Status::Unsupported);
        rawCase("f(1);", Status::Success);
        rawCase("a[1;", Status::ExpectedIndexClose);
        rawCase("a.;", Status::ExpectedIdentifier);
        rawCase("a.true;", Status::ReservedIdentifier);
        rawCase("a.array;", Status::ReservedBuiltin);
        rawCase("a.__au_private;", Status::ReservedPrefix);
        rawCase("1+;", Status::ExpectedExpression);
        rawCase("(1;", Status::ExpectedClose);
        rawCase("1 2;", Status::ExpectedEnd);
        for (const auto &source : {":;", "];", ",;"})
            rawCase(source, Status::ExpectedExpression);
        for (const auto &source : {"1:2;", "1]2;", "1,2;", "1(2);", "true(2);", "(1)(2);"})
            rawCase(source, Status::ExpectedEnd);
        rawCase(std::string(128, '(') + "1" + std::string(128, ')') + ";", Status::NestingLimit);
        rawCase(chain(129) + ";", Status::DepthLimit);
        rawCase("1)", Status::Success, Stop::CloseParenthesis);
        rawCase("name=", Status::Success, Stop::Assignment);
        abiControls();
        rawGrowth();
        rawFrameGrowth();
        rawArguments();
        std::cout << "PASS hosted parser " << cases
                  << " differential/ABI cases, 199-node/frame and 257-argument growth with allocation cleanup\n";
    } catch (const std::exception &error) {
        std::cerr << "FAIL " << error.what() << '\n';
        return 1;
    }
}
