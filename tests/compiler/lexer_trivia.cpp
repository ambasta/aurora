#include "lexer.hpp"
#include "parser.hpp"
#include <algorithm>
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
        cases();
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
