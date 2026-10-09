#include "lexer.hpp"
#include "parser.hpp"
#include "integer_literal.hpp"
#include <algorithm>
#include <clocale>
#include <fstream>
#include <iostream>
#include <iterator>
#include <random>

namespace {
void require(bool condition, const std::string &message) {
    if (!condition)
        throw std::runtime_error(message);
}
std::vector<aurora::SourcePosition> positions(const std::string &source) {
    std::vector<aurora::SourcePosition> result;
    aurora::SourcePosition position;
    result.push_back(position);
    for (const auto byte : source) {
        ++position.offset;
        if (byte == '\n') {
            ++position.line;
            position.column = 1;
        } else {
            ++position.column;
        }
        result.push_back(position);
    }
    return result;
}
void samePosition(const aurora::SourcePosition &actual, const aurora::SourcePosition &expected) {
    require(actual.offset == expected.offset && actual.line == expected.line && actual.column == expected.column,
            "range coordinate disagrees with independent byte scan");
}
void verify(const std::string &source, const std::string &path) {
    const auto lexed = aurora::lexSource(source, path);
    const auto legacy = aurora::lex(source, path);
    const auto discarded = aurora::lexSource(source, path, aurora::TriviaRetention::Discard);
    const auto expectedPositions = positions(source);
    require(lexed.source && lexed.source->text == source && lexed.source->path == path, "source ownership");
    require(discarded.trivia.empty(), "legacy compiler mode must not retain trivia");
    require(lexed.tokens.size() == legacy.size() && legacy.size() == discarded.tokens.size(), "token counts");
    std::vector<aurora::SourceSpan> spans;
    for (std::size_t index = 0; index < lexed.tokens.size(); ++index) {
        const auto &token = lexed.tokens[index];
        require(token.text == legacy[index].text && token.line == legacy[index].line &&
                    token.text == discarded.tokens[index].text,
                "lossless and legacy token streams differ");
        require(token.span.source == lexed.source, "token snapshot identity");
        require(token.span.begin.offset <= token.span.end.offset && token.span.end.offset <= source.size(),
                "token range bounds");
        samePosition(token.span.begin, expectedPositions.at(token.span.begin.offset));
        samePosition(token.span.end, expectedPositions.at(token.span.end.offset));
        samePosition(token.span.begin, legacy[index].span.begin);
        samePosition(token.span.end, legacy[index].span.end);
        if (token.text == "<eof>") {
            require(index + 1 == lexed.tokens.size() && token.span.begin.offset == source.size() &&
                        token.span.end.offset == source.size(),
                    "zero-width EOF range");
        } else {
            require(source.substr(token.span.begin.offset, token.span.end.offset - token.span.begin.offset) ==
                        token.text,
                    "exact token spelling");
            spans.push_back(token.span);
        }
    }
    for (const auto &trivia : lexed.trivia) {
        require(trivia.span.source == lexed.source, "trivia snapshot identity");
        require(trivia.span.begin.offset < trivia.span.end.offset && trivia.span.end.offset <= source.size(),
                "nonempty trivia bounds");
        samePosition(trivia.span.begin, expectedPositions.at(trivia.span.begin.offset));
        samePosition(trivia.span.end, expectedPositions.at(trivia.span.end.offset));
        const auto text = source.substr(trivia.span.begin.offset, trivia.span.end.offset - trivia.span.begin.offset);
        if (trivia.kind == aurora::TriviaKind::LineComment)
            require(text.starts_with("//") && text.find('\n') == std::string::npos, "line comment boundaries");
        else
            require(std::all_of(text.begin(),
                                text.end(),
                                [](unsigned char byte) {
                                    return std::isspace(byte);
                                }),
                    "whitespace trivia classification");
        spans.push_back(trivia.span);
    }
    std::sort(spans.begin(), spans.end(), [](const auto &left, const auto &right) {
        return left.begin.offset < right.begin.offset;
    });
    std::size_t next = 0;
    std::string reconstructed;
    for (const auto &span : spans) {
        require(span.begin.offset == next, "token/trivia ranges have a gap or overlap");
        reconstructed += span.source->text.substr(span.begin.offset, span.end.offset - span.begin.offset);
        next = span.end.offset;
    }
    require(next == source.size() && reconstructed == source, "lossless source reconstruction");
}
void binaryLiterals() {
    const std::string prefix = "// header\r\n\t";
    for (const std::string spelling : {"0b0",
                                       "0B00101",
                                       "0b1'0010'11u8",
                                       "0b1'0u64",
                                       "0b10001'10001'10001'11111'10001'10001'01110u64",
                                       "0b",
                                       "0b2",
                                       "0b'1",
                                       "0b1''0",
                                       "0b1'",
                                       "0b1'u64",
                                       "0b1u64'0",
                                       "0b1_0",
                                       "0b1u65"}) {
        verify(prefix + spelling + "+'[' // preserve 'row'\r\n", "binary.au");
        const auto tokens = aurora::lexSource(prefix + spelling).tokens;
        require(tokens.size() == 2 && tokens[0].text == spelling && tokens[0].span.begin.line == 2 &&
                    tokens[0].span.begin.column == 2 && tokens[0].span.end.offset == prefix.size() + spelling.size(),
                "binary spelling is not one lossless token");
    }
    for (std::uint64_t value = 0; value < 256; ++value) {
        std::string spelling = "0b";
        for (int bit = 7; bit >= 0; --bit) {
            if (bit != 7)
                spelling += '\'';
            spelling += ((value >> bit) & 1) ? '1' : '0';
        }
        require(aurora::decodeIntegerMagnitude(spelling) == value, "binary digit/separator decoding");
        require(aurora::decodeIntegerMagnitude(std::to_string(value)) == value, "decimal decoding changed");
        verify(spelling + "u8+'\\''", "binary-byte-boundary.au");
    }
    require(aurora::decodeIntegerMagnitude("18446744073709551615") == UINT64_MAX &&
                aurora::decodeIntegerMagnitude("0B" + std::string(64, '1')) == UINT64_MAX &&
                aurora::decodeIntegerMagnitude("0008") == 8 &&
                aurora::decodeIntegerMagnitude("0b" + std::string(128, '0') + "1") == 1,
            "full-width or leading-zero magnitude decoding");
    for (const std::string &spelling : std::vector<std::string>{"",
                                                                "0b",
                                                                "0B",
                                                                "0b2",
                                                                "0b102",
                                                                "0b'1",
                                                                "0b1''0",
                                                                "0b1'",
                                                                "0b1_0",
                                                                "0b1u64",
                                                                "0b1'a",
                                                                "0b1u8'0",
                                                                "1'0",
                                                                "0x10",
                                                                "18446744073709551616",
                                                                "0b1" + std::string(64, '0')})
        require(!aurora::decodeIntegerMagnitude(spelling), "invalid integer magnitude accepted: " + spelling);
}
void byteLiterals() {
    const std::string prefix = "// header\r\n\t";
    const std::string digits = "0123456789abcdef";
    for (unsigned value = 0; value != 256; ++value) {
        const auto spelling = "'\\x" + std::string(1, digits[value >> 4]) + digits[value & 15] + "'";
        require(aurora::decodeByteLiteral(spelling) == value, "hex byte decoder value");
        verify(prefix + spelling + "+'[' // keep 'quotes' / punctuation\r\n", "byte.au");
        const auto lexed = aurora::lexSource(prefix + spelling, "byte.au");
        require(lexed.tokens[0].text == spelling && lexed.tokens[0].span.begin.line == 2 &&
                    lexed.tokens[0].span.begin.column == 2 &&
                    lexed.tokens[0].span.end.offset - lexed.tokens[0].span.begin.offset == spelling.size(),
                "hex literal spelling or location");
    }
    for (unsigned value = 0; value != 256; ++value) {
        const auto spelling = "'" + std::string(1, static_cast<char>(value)) + "'";
        const bool valid = value >= 32 && value <= 126 && value != 39 && value != 92;
        require(aurora::decodeByteLiteral(spelling).has_value() == valid, "raw byte decoder acceptance");
        if (valid) {
            verify(prefix + spelling, "raw-byte.au");
            continue;
        }
        for (const auto retention : {aurora::TriviaRetention::Keep, aurora::TriviaRetention::Discard}) {
            try {
                aurora::lexSource(prefix + spelling, "raw-byte.au", retention);
                throw std::runtime_error("invalid raw byte accepted");
            } catch (const aurora::Error &error) {
                require(error.diagnostic.code == aurora::DiagnosticCode::InvalidByteLiteral &&
                            error.diagnostic.span.begin.offset == prefix.size() &&
                            error.diagnostic.span.begin.line == 2 && error.diagnostic.span.begin.column == 2 &&
                            error.diagnostic.span.end.offset <= prefix.size() + spelling.size(),
                        "raw-byte diagnostic code, location or bounds");
            }
        }
    }
    for (const std::string spelling :
         {"'\\''", "'\\\\'", "'\\0'", "'\\n'", "'\\r'", "'\\t'", "'\\a'", "'\\b'", "'\\f'", "'\\v'"})
        verify(prefix + spelling + "/'/'// trailing\n'{'=='{'", "escaped-byte.au");
    for (const std::string spelling : {"''",
                                       "'abc'",
                                       "'\\x100'",
                                       "'\\u1234'",
                                       "'\\q'",
                                       "'a'u8",
                                       "'a'_suffix",
                                       "'\\x'",
                                       "'\\x0'",
                                       "'\\xGG'",
                                       "'unclosed",
                                       "'\\"}) {
        try {
            aurora::lexSource(prefix + spelling, "invalid-byte.au");
            throw std::runtime_error("invalid byte spelling accepted");
        } catch (const aurora::Error &error) {
            require(error.diagnostic.code == aurora::DiagnosticCode::InvalidByteLiteral &&
                        error.diagnostic.span.begin.offset == prefix.size() &&
                        error.diagnostic.span.end.offset == prefix.size() + spelling.size(),
                    "invalid byte spelling must retain full attempted token span");
        }
    }
}
void cases() {
    for (const std::string source : {"",
                                     "//",
                                     "// comment at EOF",
                                     " \t\r\n\n",
                                     "a//x\n+b",
                                     "x / / y",
                                     "// café 😀\r\nmodule x;\v\f",
                                     "a>>b >= c && d::e",
                                     "///\r//\t"})
        verify(source, "fixture.au");
    std::string arbitraryComment = "//";
    for (int byte = 0; byte <= 255; ++byte) {
        if (byte != '\n')
            arbitraryComment += static_cast<char>(byte);
    }
    verify(arbitraryComment, "binary-comment.au");
    const std::vector<std::string> pieces = {
        "name", "123", "::", ">>", ">", "+", "/", " ", "\t", "\r\n", "// text\n", "// café 😀\n", "_x", "&&", "{"};
    std::mt19937 random(1707);
    for (int sample = 0; sample < 256; ++sample) {
        std::string source;
        for (int piece = 0; piece < 32; ++piece)
            source += pieces[random() % pieces.size()];
        verify(source, "generated.au");
    }
    auto lexed = aurora::lexSource("// leading\n >> // trailing");
    aurora::Parser parser(lexed.tokens);
    parser.templateClose();
    parser.templateClose();
    require(lexed.tokens[0].text == ">>" && lexed.tokens[0].span.end.offset - lexed.tokens[0].span.begin.offset == 2,
            "parser changed canonical template closer token");
    require(lexed.trivia.size() == 4, "parser changed retained trivia");
    for (const auto retention : {aurora::TriviaRetention::Keep, aurora::TriviaRetention::Discard}) {
        try {
            aurora::lexSource("// before\n @", "bad.au", retention);
            require(false, "unsupported syntax accepted");
        } catch (const aurora::Error &error) {
            require(error.diagnostic.code == aurora::DiagnosticCode::UnsupportedCharacter &&
                        error.diagnostic.span.begin.offset == 11 && error.diagnostic.span.end.offset == 12,
                    "lexical error changed with trivia retention");
        }
    }
}
} // namespace
int main(int argc, char **argv) {
    try {
        const std::string originalLocale = std::setlocale(LC_CTYPE, nullptr);
        for (const auto *locale : {"C", "C.utf8", "en_US", "en_US.utf8", "tr_TR", "tr_TR.utf8"}) {
            if (std::setlocale(LC_CTYPE, locale)) {
                byteLiterals();
                std::cout << "PASS byte literal locale " << locale << '\n';
            } else {
                std::cout << "SKIP unavailable byte literal locale " << locale << '\n';
            }
        }
        require(std::setlocale(LC_CTYPE, originalLocale.c_str()) != nullptr, "cannot restore locale");
        cases();
        binaryLiterals();
        for (int index = 1; index < argc; ++index) {
            std::ifstream input(argv[index], std::ios::binary);
            require(input.good(), "cannot open corpus source");
            const std::string source{std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
            verify(source, argv[index]);
        }
        std::cout << "PASS lossless trivia cases, 256 generated scans, and " << argc - 1 << " corpus sources\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL " << error.what() << '\n';
        return 1;
    }
}
