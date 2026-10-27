#include "types.hpp"
#include <iostream>
#include <sstream>

namespace {
void require(bool condition, const std::string &message) {
    if (!condition)
        throw std::runtime_error(message);
}
void checkSyntheticToken() {
    const aurora::Token synthetic("generated", 7);
    require(!synthetic.span.source && synthetic.line == 7, "synthetic token must not invent a source range");
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
    const auto source = std::make_shared<const aurora::SourceText>("bad.au", "// comment\n @");
    const aurora::Error error(
        aurora::DiagnosticCode::UnsupportedCharacter, "unsupported character", {source, {12, 2, 2}, {13, 2, 3}});
    const auto wrapped = error.withContext("module dep: ").withDefaultCode(aurora::DiagnosticCode::Module);
    require(wrapped.diagnostic.code == error.diagnostic.code &&
                wrapped.diagnostic.span.source == error.diagnostic.span.source,
            "context wrapping preserves provenance");
    require(std::string(wrapped.what()) == "module dep: unsupported character",
            "location-neutral import context message");
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
        checkSyntheticToken();
        checkErrors();
        checkTextRendering();
        std::cerr << "PASS shared diagnostic rendering\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL " << error.what() << '\n';
        return 1;
    }
}
