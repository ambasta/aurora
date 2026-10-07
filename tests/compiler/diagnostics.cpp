#include "lexer.hpp"
#include "parser.hpp"
#include <iostream>
#include <sstream>

namespace {
void require(bool condition, const std::string &message) {
    if (!condition)
        throw std::runtime_error(message);
}
void checkPositions() {
    const std::string contents = "// café\r\n\tmodule demo;\r\n";
    const auto tokens = aurora::lex(contents, "café.au");
    const auto &module = tokens.front();
    require(module.line == 2 && module.span.begin.line == 2 && module.span.begin.column == 2,
            "CRLF and tab byte column");
    require(module.span.begin.offset == contents.find("module") &&
                module.span.end.offset == contents.find("module") + 6,
            "UTF-8 byte offsets");
    require(module.span.source->path == "café.au" && module.span.source->text == contents, "owned source snapshot");
    require(tokens.back().span.begin.offset == contents.size() && tokens.back().span.end.offset == contents.size(),
            "EOF is zero width");
    require(tokens.back().span.begin.line == 3 && tokens.back().span.begin.column == 1, "EOF after newline");
    const auto empty = aurora::lex("");
    require(empty.size() == 1 && empty[0].span.begin.offset == 0 && empty[0].span.end.offset == 0, "empty source EOF");
    const aurora::Token synthetic("generated", 7);
    require(!synthetic.span.source && synthetic.line == 7, "synthetic token must not invent a source range");
    const auto operators = aurora::lex("a>=b && c>>2");
    for (const auto &token : operators) {
        if (token.text == "<eof>")
            continue;
        require(token.span.source->text.substr(token.span.begin.offset,
                                               token.span.end.offset - token.span.begin.offset) == token.text,
                "lexical ranges reproduce token text");
    }
}
void checkParserRanges() {
    const auto original = aurora::lex(">>", "closers.au");
    aurora::Parser parser(original);
    parser.templateClose();
    require(parser.peek().text == ">" && parser.peek().span.begin.offset == 1 && parser.peek().span.end.offset == 2 &&
                parser.peek().span.begin.column == 2,
            "virtual second template closer range");
    require(original[0].text == ">>" && original[0].span.begin.offset == 0 && original[0].span.end.offset == 2,
            "parser must not mutate retained lexical stream");
    parser.templateClose();
    require(parser.peek().text == "<eof>", "second closer consumption");
    aurora::Parser qualified(aurora::lex("one :: two"));
    const auto name = qualified.qualifiedIdent();
    require(name.text == "one::two" && name.span.begin.offset == 0 && name.span.end.offset == 10,
            "qualified name range");
    aurora::Parser expression(aurora::lex("one :: two(1)"));
    const auto call = expression.primary();
    require(call->token.text == "one::two" && call->token.span.begin.offset == 0 && call->token.span.end.offset == 10,
            "qualified expression name range");
    aurora::Parser module(aurora::lex("std . bytes"));
    const auto dotted = module.moduleIdent();
    require(dotted.text == "std.bytes" && dotted.span.end.offset == 11, "module name range");
    try {
        aurora::Parser(aurora::lex("module sample", "missing.au")).parse();
        require(false, "expected parser rejection");
    } catch (const aurora::Error &error) {
        require(error.diagnostic.code == aurora::DiagnosticCode::UnexpectedToken, "explicit parser code");
        require(error.diagnostic.span.begin.offset == 13 && error.diagnostic.span.end.offset == 13,
                "parser EOF location");
        require(std::string(error.what()) == "expected ';' (found '<eof>')", "location-neutral parser message");
    }
    const std::string nested =
        "module sample; auto sample() -> i64 { return " + std::string(130, '(') + "1" + std::string(130, ')') + "; }";
    try {
        aurora::Parser(aurora::lex(nested)).parse();
        require(false, "expected nesting rejection");
    } catch (const aurora::Error &error) {
        require(error.diagnostic.code == aurora::DiagnosticCode::NestingLimit && error.diagnostic.span.source,
                "nesting diagnostic code and range");
    }
}
void checkTruncatedSource() {
    const std::string complete =
        "module sample; auto sample() -> i64 { const array<i64, 2> x = {1, 2}; return (x[0]); }";
    for (std::size_t length = 0; length <= complete.size(); ++length) {
        const auto prefix = complete.substr(0, length);
        try {
            aurora::Parser(aurora::lex(prefix, "prefix.au")).parse();
        } catch (const aurora::Error &error) {
            require(error.diagnostic.code == aurora::DiagnosticCode::UnexpectedToken,
                    "truncated parser input must produce a structured parse error");
            require(error.diagnostic.span.source && error.diagnostic.span.end.offset <= length,
                    "truncated parser input range is inside its snapshot");
        }
    }
}
void checkTextRendering() {
    const auto source = std::make_shared<const aurora::SourceText>("sample.au", "\n  name");
    const aurora::SourceSpan span{source, {3, 2, 3}, {7, 2, 7}};
    std::ostringstream located;
    aurora::writeDiagnosticText(located, {aurora::DiagnosticCode::Semantic, "wrong type", span}, "aurorac");
    require(located.str() == "sample.au:2:3: error AU3001: wrong type\n", "located text includes path and column");
    std::ostringstream warning;
    aurora::writeDiagnosticText(
        warning,
        {aurora::DiagnosticCode::UnreadLocal, "unused binding", span, aurora::DiagnosticSeverity::Warning},
        "aurora-fmt");
    require(warning.str() == "sample.au:2:3: warning AU6001: unused binding\n", "text preserves warning severity");
    for (const auto code : {aurora::DiagnosticCode::CommandLine, aurora::DiagnosticCode::Internal}) {
        const aurora::Diagnostic diagnostic{code, "literal line 4: is part of this message", {}};
        std::ostringstream text;
        aurora::writeDiagnosticText(text, diagnostic, "aurorac");
        require(text.str() ==
                    "aurorac: error " + std::string(aurora::diagnosticCode(code)) + ": " + diagnostic.message + "\n",
                "unlocated fallback preserves literal message content without fake coordinates");
        std::ostringstream json;
        aurora::writeDiagnosticsJson(json, {diagnostic});
        require(json.str().find("\"message\":\"" + diagnostic.message + "\"") != std::string::npos &&
                    json.str().find("\"path\":null,\"range\":null") != std::string::npos,
                "unlocated JSON uses the identical location-neutral payload");
    }
    const auto anonymous = std::make_shared<const aurora::SourceText>("", "name");
    std::ostringstream text;
    aurora::writeDiagnosticText(
        text, {aurora::DiagnosticCode::Semantic, "wrong type", {anonymous, {0, 1, 1}, {4, 1, 5}}}, "aurorac");
    require(text.str() == "<source>:1:1: error AU3001: wrong type\n", "unnamed snapshot is explicit");
}
void checkErrors() {
    try {
        aurora::lex("// comment\n @", "bad.au");
        require(false, "expected lexical rejection");
    } catch (const aurora::Error &error) {
        require(error.diagnostic.code == aurora::DiagnosticCode::UnsupportedCharacter, "explicit lexer code");
        require(error.diagnostic.span.begin.offset == 12 && error.diagnostic.span.end.offset == 13 &&
                    error.diagnostic.span.begin.line == 2 && error.diagnostic.span.begin.column == 2,
                "lexer byte range");
        const auto wrapped = error.withContext("module dep: ").withDefaultCode(aurora::DiagnosticCode::Module);
        require(wrapped.diagnostic.code == error.diagnostic.code &&
                    wrapped.diagnostic.span.source == error.diagnostic.span.source,
                "context wrapping preserves provenance");
        require(std::string(wrapped.what()) == "module dep: unsupported character",
                "location-neutral import context message");
    }
    std::string adversarial = "\"\\\n\r\t";
    adversarial.push_back('\0');
    adversarial += " café 😀 ";
    adversarial.push_back(static_cast<char>(0xff));
    adversarial.push_back(static_cast<char>(0xc0));
    adversarial += "\xed\xa0\x80";
    std::ostringstream json;
    aurora::writeJsonString(json, adversarial);
    require(json.str().find("café 😀") != std::string::npos, "valid UTF-8 JSON must be preserved");
    require(json.str().find("\\u00ff\\u00c0\\u00ed\\u00a0\\u0080") != std::string::npos,
            "invalid UTF-8 JSON bytes must be escaped");
    std::cout << json.str() << '\n';
}
} // namespace
int main() {
    try {
        checkPositions();
        checkParserRanges();
        checkTruncatedSource();
        checkErrors();
        checkTextRendering();
        std::cerr << "PASS shared lexer/parser diagnostic ranges\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL " << error.what() << '\n';
        return 1;
    }
}
