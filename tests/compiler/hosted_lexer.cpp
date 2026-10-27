// Aurora lexer cases checked against the reviewed golden file hosted_lexer.golden
// (--update rewrites it). Every case reads the lexer's event rows through its
// bridge entry; raw ABI records below deliberately do not use production layouts.
#include "lexemes.hpp"
#include "hosted_lexer_abi.hpp"
#include <algorithm>
#include <array>
#include <cerrno>
#include <clocale>
#include <csignal>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
#include <map>
#include <optional>
#include <random>
#include <sstream>
#include <sys/mman.h>

using Entry = void (*)(const void *, void *);
extern "C" void checked_hosted_lexer_call(const void *, void *, Entry);

namespace {
using aurora::Diagnostic;
using aurora::DiagnosticCode;
using aurora::SourcePosition;
using aurora::lexemes::Lexeme;
using Input = std::array<std::uint64_t, 10>;
using Event = std::array<std::int64_t, 4>;
static_assert(sizeof(Input) == 80 && sizeof(Event) == 32);
static_assert(sizeof(Input) == sizeof(aurora::hosted_abi::LexerInput) &&
              sizeof(Event) == sizeof(aurora::hosted_abi::compiler_lexer::Lexeme));
static_assert(sizeof(void *) == 8);

std::string context;
std::size_t cases = 0;
std::size_t abiCalls = 0;
bool updating = false;
std::map<std::string, std::string> golden;
std::map<std::string, std::size_t> occurrences;

void require(bool condition, const std::string &message) {
    if (!condition)
        throw std::runtime_error(context + ": " + message);
}

bool space(unsigned char byte) {
    return byte == ' ' || (byte >= '\t' && byte <= '\r');
}

std::vector<SourcePosition> positions(const std::string &text) {
    std::vector<SourcePosition> out;
    out.reserve(text.size() + 1);
    SourcePosition at;
    out.push_back(at);
    for (unsigned char byte : text) {
        ++at.offset;
        if (byte == '\n') {
            ++at.line;
            at.column = 1;
        } else {
            ++at.column;
        }
        out.push_back(at);
    }
    return out;
}

// Each event's line/column pairs must agree with an independent byte scan.
void positionsAgree(const Lexeme &lexeme, const std::vector<SourcePosition> &expected) {
    require(lexeme.begin >= 0 && lexeme.begin <= lexeme.end && static_cast<std::size_t>(lexeme.end) < expected.size(),
            "event bounds");
    const auto &begin = expected[static_cast<std::size_t>(lexeme.begin)];
    const auto &end = expected[static_cast<std::size_t>(lexeme.end)];
    require(lexeme.line == begin.line && lexeme.column == begin.column && lexeme.endLine == end.line &&
                lexeme.endColumn == end.column,
            "event line/column differs from its byte offset");
}

class Outcome {
public:
    std::vector<Lexeme> lexemes;
    std::optional<Diagnostic> error;
};

Outcome scan(const std::string &text) {
    Outcome out{aurora::lexemes::scan(text), {}};
    const auto expected = positions(text);
    for (const auto &lexeme : out.lexemes) {
        positionsAgree(lexeme, expected);
        const auto bytes = text.substr(lexeme.begin, lexeme.end - lexeme.begin);
        if (lexeme.event == aurora::lexemes::Event::whitespace)
            require(std::all_of(bytes.begin(), bytes.end(), space), "non-ASCII-whitespace in whitespace event");
        else if (lexeme.event == aurora::lexemes::Event::line_comment)
            require(bytes.starts_with("//") && bytes.find('\n') == std::string::npos, "comment boundary mismatch");
    }
    const auto &last = out.lexemes.back();
    if (last.event == aurora::lexemes::Event::end_of_input) {
        require(last.begin == static_cast<std::int64_t>(text.size()) && last.end == last.begin,
                "EOF is not the zero-width end of the source");
        return out;
    }
    require(last.begin < last.end, "empty lexical error range");
    const auto source = std::make_shared<const aurora::SourceText>("case.au", text);
    const aurora::SourceSpan span{
        source, expected[static_cast<std::size_t>(last.begin)], expected[static_cast<std::size_t>(last.end)]};
    try {
        aurora::hosted_lexer::rejectLexical(last.event, span);
    } catch (const aurora::Error &error) {
        out.error = error.diagnostic;
    }
    require(out.error.has_value(), "lexer stopped without end of input or a rejection");
    return out;
}

// One golden line per case: token boundaries for accepted input, or the
// diagnostic code, extent and message. Long token lists keep only their count.
std::string summary(const Outcome &outcome) {
    std::ostringstream out;
    if (outcome.error) {
        const auto &error = *outcome.error;
        out << "err " << static_cast<int>(error.code) << ' ' << error.span.begin.offset << '-' << error.span.end.offset
            << ' ' << error.message;
        return out.str();
    }
    std::vector<const Lexeme *> tokens;
    std::size_t trivia = 0;
    for (const auto &lexeme : outcome.lexemes) {
        if (lexeme.event == aurora::lexemes::Event::token)
            tokens.push_back(&lexeme);
        trivia += lexeme.trivia();
    }
    out << "ok " << tokens.size() << " trivia " << trivia;
    if (tokens.size() <= 64)
        for (std::size_t index = 0; index < tokens.size(); ++index)
            out << (index ? ',' : ' ') << tokens[index]->begin << '-' << tokens[index]->end;
    return out.str();
}

void expectGolden(const std::string &name, const Outcome &outcome) {
    const auto key = name + "#" + std::to_string(occurrences[name]++);
    const auto line = summary(outcome);
    if (updating) {
        golden.emplace(key, line);
        return;
    }
    const auto found = golden.find(key);
    require(found != golden.end(), "case is missing from the golden file: " + key);
    require(found->second == line,
            "lexer output differs from the golden file for " + key + ": got '" + line + "', expected '" +
                found->second + "'");
}

Outcome verify(const std::string &text, const std::string &name) {
    context = name;
    ++cases;
    const auto result = scan(text);
    expectGolden(name, result);
    return result;
}

void valid(const std::string &text, const std::string &name) {
    require(!verify(text, name).error, "independently valid source was rejected");
}

void invalid(
    const std::string &text, const std::string &name, DiagnosticCode code, std::size_t begin, std::size_t end) {
    const auto result = verify(text, name);
    require(result.error && result.error->code == code, "independent diagnostic family mismatch");
    const auto &error = *result.error;
    const std::string message = code == DiagnosticCode::InvalidByteLiteral         ? "invalid byte literal"
                                : code == DiagnosticCode::InvalidByteStringLiteral ? "invalid byte-string literal"
                                                                                   : "unsupported character";
    require(error.message == message, "independent diagnostic message mismatch");
    require(error.span.begin.offset == begin && error.span.end.offset == end, "independent diagnostic extent mismatch");
}

std::string bytes(std::initializer_list<unsigned> values) {
    std::string out;
    for (unsigned value : values)
        out += static_cast<char>(value);
    return out;
}

void byteCases() {
    constexpr char hex[] = "0123456789abcdef";
    const std::string prefix = "// header\r\n\t";
    for (unsigned byte = 0; byte != 256; ++byte) {
        const auto one = std::string(1, static_cast<char>(byte));
        verify(one, "all-byte-" + std::to_string(byte));
        verify("identifier" + one + "suffix", "identifier-byte-" + std::to_string(byte));
        verify("123" + one + "word", "number-byte-" + std::to_string(byte));
        verify(prefix + "'" + one + "'", "raw-byte-" + std::to_string(byte));
        verify(prefix + "\"" + one + "\"", "raw-string-byte-" + std::to_string(byte));
        verify(prefix + "'\\" + one + "'", "escape-byte-" + std::to_string(byte));
        verify(prefix + "\"\\" + one + "\"", "escape-string-byte-" + std::to_string(byte));
        const auto escaped = "\\x" + std::string(1, hex[byte >> 4]) + hex[byte & 15];
        valid(prefix + "'" + escaped + "'", "hex-byte-" + std::to_string(byte));
        valid(prefix + "\"" + escaped + "\"", "hex-string-" + std::to_string(byte));
    }
    std::string opaque = "//";
    for (unsigned byte = 0; byte != 256; ++byte)
        if (byte != '\n')
            opaque += static_cast<char>(byte);
    valid(opaque, "opaque-all-bytes-comment");
    valid(opaque + "\nname", "opaque-all-bytes-comment-newline");
    for (const auto &spelling : {"''",
                                 "'ab'",
                                 "'\\q'",
                                 "'\\x'",
                                 "'\\x1'",
                                 "'\\xgg'",
                                 "'\\x100'",
                                 "'\\u0041'",
                                 "'a'u8",
                                 "'a'_name0",
                                 "'unclosed",
                                 "'\\"})
        invalid(prefix + spelling,
                "invalid-byte-spelling",
                DiagnosticCode::InvalidByteLiteral,
                prefix.size(),
                prefix.size() + std::strlen(spelling));
    for (const auto &spelling : {R"("\q")",
                                 R"("\x")",
                                 R"("\x0")",
                                 R"("\xGG")",
                                 R"("\u0041")",
                                 R"("a"u8)",
                                 R"(""_name0)",
                                 "\"unclosed",
                                 "\"\\"})
        invalid(prefix + spelling,
                "invalid-string-spelling",
                DiagnosticCode::InvalidByteStringLiteral,
                prefix.size(),
                prefix.size() + std::strlen(spelling));
    for (const std::string quote : {"'", "\""}) {
        const auto code = quote == "'" ? DiagnosticCode::InvalidByteLiteral : DiagnosticCode::InvalidByteStringLiteral;
        for (const std::string ending : {"\n", "\r", "\r\n"}) {
            invalid(prefix + quote + "bad" + ending + quote + "tail",
                    "quoted-line-end",
                    code,
                    prefix.size(),
                    prefix.size() + 4);
            invalid(prefix + quote + "\\" + ending + quote + "tail",
                    "escaped-line-end",
                    code,
                    prefix.size(),
                    prefix.size() + 2);
        }
    }
}

void utf8Cases() {
    const std::vector<std::string> good = {bytes({0xc2, 0x80}),
                                           bytes({0xdf, 0xbf}),
                                           bytes({0xe0, 0xa0, 0x80}),
                                           bytes({0xed, 0x9f, 0xbf}),
                                           bytes({0xee, 0x80, 0x80}),
                                           bytes({0xef, 0xbf, 0xbf}),
                                           bytes({0xf0, 0x90, 0x80, 0x80}),
                                           bytes({0xf4, 0x8f, 0xbf, 0xbf})};
    for (const auto &raw : good) {
        valid("\"" + raw + "\"", "utf8-valid-boundary");
        valid("\"a" + raw + R"(\xff\0b")", "utf8-escape-mixture");
        for (std::size_t length = 1; length < raw.size(); ++length) {
            const auto spelling = "\"" + raw.substr(0, length) + "\"";
            invalid(spelling, "utf8-truncated", DiagnosticCode::InvalidByteStringLiteral, 0, spelling.size());
        }
        for (std::size_t offset = 1; offset < raw.size(); ++offset) {
            auto corrupted = raw;
            for (unsigned byte : {0U, 0x7fU, 0xc0U, 0xffU}) {
                corrupted[offset] = static_cast<char>(byte);
                const auto spelling = "\"" + corrupted + "\"";
                invalid(
                    spelling, "utf8-bad-continuation", DiagnosticCode::InvalidByteStringLiteral, 0, spelling.size());
            }
        }
    }
    for (const auto &raw : {bytes({0x80}),
                            bytes({0xbf}),
                            bytes({0xc0, 0x80}),
                            bytes({0xc1, 0xbf}),
                            bytes({0xe0, 0x80, 0x80}),
                            bytes({0xed, 0xa0, 0x80}),
                            bytes({0xed, 0xbf, 0xbf}),
                            bytes({0xf0, 0x80, 0x80, 0x80}),
                            bytes({0xf4, 0x90, 0x80, 0x80}),
                            bytes({0xf5, 0x80, 0x80, 0x80}),
                            bytes({0xfe}),
                            bytes({0xff})}) {
        const auto spelling = "\"" + raw + "\"";
        invalid(spelling, "utf8-invalid-scalar", DiagnosticCode::InvalidByteStringLiteral, 0, spelling.size());
    }
}

void boundaryCases() {
    for (std::size_t length : {4095U, 4096U, 4097U, 1U << 20}) {
        valid(std::string(length, 'a'), "long-identifier-" + std::to_string(length));
        valid("//" + std::string(length - 2, '\xff'), "long-comment-" + std::to_string(length));
        valid(std::string(length - 2, ' ') + "\r\n", "long-whitespace-" + std::to_string(length));
        valid(std::string(length, '\n'), "long-lines-" + std::to_string(length));
        std::string mixed;
        while (mixed.size() + 16 <= length)
            mixed += "name0+0b1'0 //x\n";
        mixed.resize(length, ' ');
        valid(mixed, "long-mixed-" + std::to_string(length));
    }
    for (std::size_t decoded : {4095U, 4096U, 4097U}) {
        for (unsigned mode = 0; mode != 3; ++mode) {
            std::string spelling = "\"";
            if (mode == 0)
                spelling += std::string(decoded, 'a');
            else if (mode == 1)
                for (std::size_t index = 0; index < decoded; ++index)
                    spelling += "\\x00";
            else {
                for (std::size_t index = 0; index < decoded / 4; ++index)
                    spelling += bytes({0xf0, 0x90, 0x80, 0x80});
                spelling += std::string(decoded % 4, 'a');
            }
            spelling += '"';
            if (decoded <= 4096)
                valid(spelling, "decoded-string-limit-valid");
            else
                invalid(spelling,
                        "decoded-string-limit-invalid",
                        DiagnosticCode::InvalidByteStringLiteral,
                        0,
                        spelling.size());
        }
    }
}

void languageCases() {
    for (const std::string text : {"",
                                   "//",
                                   "// EOF",
                                   " \t\v\f\r\n",
                                   "a\r\nb\rc\nd\te",
                                   "///\r//\t",
                                   "a//x\n+b",
                                   "x / / y",
                                   "a>>b >= c && d::e",
                                   "_0 A0 a_Z 0123u8",
                                   R"('\\' '\'' '\0' '\a' '\b' '\f' '\n' '\r' '\t' '\v')",
                                   R"("" "// {} \" \\ \0\xff")",
                                   "// café 😀\r\nmodule x;\v\f",
                                   "// café\r\n\tmodule demo;\r\n",
                                   R"('\''/'/'// trailing
'{'=='{')"})
        valid(text, "language-case");
    const std::vector<std::string> operators = {"->", "==", "!=", "<=", ">=", "::", "<<", ">>", "&&", "||", "(",
                                                ")",  "{",  "}",  "[",  "]",  ":",  ";",  ",",  "=",  "+",  "-",
                                                "*",  "/",  "%",  "<",  ">",  "!",  ".",  "&",  "|",  "^",  "~"};
    for (const auto &a : operators)
        for (const auto &b : operators)
            valid(a + b, "adjacent-operators");
    for (const std::string word : {"0b0",
                                   "0B00101",
                                   "0b1'0010'11u8",
                                   "0b",
                                   "0b2",
                                   "0b'1",
                                   "0b1''0",
                                   "0b1'",
                                   "0b1'u64",
                                   "0b1u64'0",
                                   "0b1_0",
                                   "0b1u65",
                                   "0xdeadbeef",
                                   "123abc",
                                   "0b1'0u64",
                                   "0b10001'10001'10001'11111'10001'10001'01110u64"}) {
        const auto out = verify(word + "+'['", "binary-word-boundary");
        require(!out.error && out.lexemes.size() == 4 && out.lexemes.front().end == std::ssize(word),
                "attempted numeric word split");
    }
    invalid("// before\r\n\t@", "unsupported-location", DiagnosticCode::UnsupportedCharacter, 12, 13);
    std::mt19937 random(0x48584c31U);
    const std::vector<std::string> pieces = {"name",
                                             "123",
                                             "::",
                                             ">>",
                                             ">",
                                             "+",
                                             "/",
                                             " ",
                                             "\t",
                                             "\r\n",
                                             "// opaque\xff\n",
                                             "_x",
                                             "&&",
                                             "{",
                                             "0b1'0",
                                             "'\\x00'",
                                             R"("é😀")"};
    for (unsigned sample = 0; sample != 256; ++sample) {
        std::string source;
        for (unsigned part = 0; part != 32; ++part)
            source += pieces[random() % pieces.size()];
        verify(source, "generated-pieces-" + std::to_string(sample));
        source.clear();
        for (unsigned part = 0; part != 64; ++part)
            source += static_cast<char>(random() & 255);
        verify(source, "generated-bytes-" + std::to_string(sample));
    }
}

Input input(
    const void *data, std::size_t size, std::int64_t offset = 0, std::int64_t line = 1, std::int64_t lineStart = 0) {
    return {0,
            reinterpret_cast<std::uintptr_t>(data),
            0,
            0,
            0,
            0,
            size,
            static_cast<std::uint64_t>(offset),
            static_cast<std::uint64_t>(line),
            static_cast<std::uint64_t>(lineStart)};
}

Event raw(const Input &record) {
    constexpr std::uint64_t guard = 0x7b0cc731de29a685ULL;
    Event result{};
    // Exercise legal eight-byte alignment both with and without 16-byte alignment.
    for (std::size_t shift : {0U, 1U}) {
        alignas(16) std::array<std::uint64_t, 19> in;
        alignas(16) std::array<std::uint64_t, 13> out;
        in.fill(guard);
        out.fill(guard);
        std::copy(record.begin(), record.end(), in.begin() + 4 + shift);
        const auto before = in;
        checked_hosted_lexer_call(in.data() + 4 + shift, out.data() + 4 + shift, aurora_hosted_lexer_invoke);
        ++abiCalls;
        require(in == before, "raw ABI input record modified");
        for (std::size_t index = 0; index != out.size(); ++index)
            if (index < 4 + shift || index >= 8 + shift)
                require(out[index] == guard, "raw ABI output overrun");
        Event observed;
        std::memcpy(observed.data(), out.data() + 4 + shift, sizeof(observed));
        if (shift == 0)
            result = observed;
        else
            require(result == observed, "raw ABI result depends on record alignment");
    }
    return result;
}

void expectRaw(
    const std::string &source, std::int64_t offset, std::int64_t line, std::int64_t lineStart, const Event &expected) {
    const auto original = source;
    const auto observed = raw(input(source.data(), source.size(), offset, line, lineStart));
    require(observed == expected, "raw event or copied cursor mismatch");
    require(source == original, "raw scanner modified source backing");
}

void eventAbiCases() {
    using Kind = aurora::hosted_lexer::Event;
    // Observe the real Aurora result through the independent raw record/ABI
    // envelope, not through a source-text enum-order check.
    const std::array<std::pair<std::string, Kind>, 8> cases{{
        {"name", Kind::token},
        {" \t\r\n", Kind::whitespace},
        {"// comment", Kind::line_comment},
        {"", Kind::end_of_input},
        {"@", Kind::unsupported_character},
        {"'ab'", Kind::invalid_byte},
        {"\"\\q\"", Kind::invalid_string},
        {"name", Kind::invalid_cursor},
    }};
    for (const auto &[source, expected] : cases) {
        context = "host/Aurora event ABI parity " + std::to_string(static_cast<std::int64_t>(expected));
        const auto observed = raw(input(source.data(), source.size(), expected == Kind::invalid_cursor ? -1 : 0));
        require(observed[0] == static_cast<std::int64_t>(expected), "generated event disagrees with host ABI enum");
    }
}

class GuardPage {
public:
    std::size_t page;
    unsigned char *mapping;
    GuardPage() : page(static_cast<std::size_t>(sysconf(_SC_PAGESIZE))), mapping(nullptr) {
        require(page >= 4096 && page <= (1U << 20), "unsupported page size");
        const auto address = mmap(nullptr, page * 3, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        require(address != MAP_FAILED, "mmap guard pages failed");
        mapping = static_cast<unsigned char *>(address);
        require(mprotect(mapping + page, page, PROT_READ | PROT_WRITE) == 0, "mprotect data page failed");
    }
    ~GuardPage() {
        if (mapping)
            munmap(mapping, page * 3);
    }
    GuardPage(const GuardPage &) = delete;
    GuardPage &operator=(const GuardPage &) = delete;
    unsigned char *end() const {
        return mapping + page * 2;
    }
};

void abiCases() {
    context = "raw-event-ABI";
    for (unsigned byte = 0; byte != 256; ++byte) {
        const bool word =
            (byte >= 'A' && byte <= 'Z') || (byte >= 'a' && byte <= 'z') || (byte >= '0' && byte <= '9') || byte == '_';
        const bool punctuation =
            std::string_view("(){}[]:;,=+-*/%<>!.&|^~").find(static_cast<char>(byte)) != std::string_view::npos;
        const std::int64_t event = byte == '\'' ? 5 : byte == '"' ? 6 : space(byte) ? 1 : word || punctuation ? 0 : 4;
        expectRaw(
            std::string(1, static_cast<char>(byte)), 0, 1, 0, {event, 1, byte == '\n' ? 2 : 1, byte == '\n' ? 1 : 0});
    }
    expectRaw("", 0, 1, 0, {3, 0, 1, 0});
    expectRaw("name +", 0, 1, 0, {0, 4, 1, 0});
    expectRaw(" \t\r\n\v\fX", 0, 1, 0, {1, 6, 2, 4});
    expectRaw(std::string("//\xff\0\r\nx", 7), 0, 1, 0, {2, 5, 1, 0});
    expectRaw("@x", 0, 1, 0, {4, 1, 1, 0});
    expectRaw("'a'u8+", 0, 1, 0, {5, 5, 1, 0});
    expectRaw("\"a\"suffix+", 0, 1, 0, {6, 9, 1, 0});
    expectRaw("0b1'0u8+", 0, 1, 0, {0, 7, 1, 0});
    expectRaw("ab\r\n\t->", 5, 2, 4, {0, 7, 2, 4});
    expectRaw("ab\r\n\t->", 7, 2, 4, {3, 7, 2, 4});
    for (const auto cursor : {Event{7, -1, 1, 0},
                              Event{7, 4, 1, 0},
                              Event{7, 0, 0, 0},
                              Event{7, 0, -1, 0},
                              Event{7, 1, 1, -1},
                              Event{7, 1, 1, 2},
                              Event{7, 1, 2, 0},
                              Event{7, 2, 1, 1},
                              Event{7, 3, std::numeric_limits<std::int64_t>::max(), 3},
                              Event{7, std::numeric_limits<std::int64_t>::min(), 1, 0},
                              Event{7, std::numeric_limits<std::int64_t>::max(), 1, 0},
                              Event{7, 0, 1, std::numeric_limits<std::int64_t>::min()}})
        expectRaw("abc", cursor[1], cursor[2], cursor[3], cursor);

    GuardPage source, in, out;
    for (const std::string spelling :
         {"x", "0", "/", "-", "'", "\"", "'a'", "\"x\"", "//", "\r", "\n", "\\", "@", "\"\xf0\x90\x80\x80\""}) {
        context = "guard-page-source-end";
        auto *backing = source.end() - spelling.size();
        std::memcpy(backing, spelling.data(), spelling.size());
        require(mprotect(source.mapping + source.page, source.page, PROT_READ) == 0, "source read-only guard failed");
        const auto record = input(backing, spelling.size());
        std::memcpy(in.end() - 80, record.data(), 80);
        require(mprotect(in.mapping + in.page, in.page, PROT_READ) == 0, "input read-only guard failed");
        std::memset(out.end() - 32, 0x5a, 32);
        checked_hosted_lexer_call(in.end() - 80, out.end() - 32, aurora_hosted_lexer_invoke);
        ++abiCalls;
        Event observed;
        std::memcpy(observed.data(), out.end() - 32, 32);
        require(observed == raw(input(spelling.data(), spelling.size())), "guarded backing changed event");
        require(mprotect(source.mapping + source.page, source.page, PROT_READ | PROT_WRITE) == 0,
                "restore source guard failed");
        require(mprotect(in.mapping + in.page, in.page, PROT_READ | PROT_WRITE) == 0, "restore input guard failed");
    }
    context = "zero-length-inaccessible-backing";
    require(raw(input(source.end(), 0)) == Event{3, 0, 1, 0}, "empty scanner dereferenced inaccessible backing");
}

} // namespace

int main(int argc, char **argv) {
    try {
        updating = argc == 3 && std::string_view(argv[1]) == "--update";
        require(argc == 2 || updating, "usage: hosted-lexer-test [--update] GOLDEN");
        const std::string path = argv[argc - 1];
        if (!updating) {
            std::ifstream file(path);
            require(file.good(), "cannot open golden file " + path);
            for (std::string line; std::getline(file, line);) {
                const auto tab = line.find('\t');
                require(tab != std::string::npos, "malformed golden line");
                golden.emplace(line.substr(0, tab), line.substr(tab + 1));
            }
        }
        require(std::setlocale(LC_CTYPE, "C") != nullptr, "C locale unavailable");
        eventAbiCases();
        abiCases();
        languageCases();
        byteCases();
        utf8Cases();
        boundaryCases();
        for (const char *locale : {"C.utf8", "en_US.utf8", "tr_TR.utf8"}) {
            if (std::setlocale(LC_CTYPE, locale)) {
                occurrences.clear();
                byteCases();
                utf8Cases();
                std::cout << "PASS hosted lexer locale " << locale << '\n';
            } else {
                std::cout << "SKIP unavailable hosted lexer locale " << locale << '\n';
            }
        }
        require(std::setlocale(LC_CTYPE, "C") != nullptr, "cannot restore C locale");
        if (updating) {
            std::ofstream file(path);
            for (const auto &[key, line] : golden)
                file << key << '\t' << line << '\n';
            require(file.good(), "cannot write golden file " + path);
        }
        std::cout << "PASS hosted lexer: " << cases << " golden cases, " << abiCalls << " raw ABI calls\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL hosted lexer: " << error.what() << '\n';
        return 1;
    }
}
