#include "frontend.hpp"
#include <fstream>
#include <iostream>
#include <sstream>

namespace {
void require(bool condition, const std::string &message) {
    if (!condition)
        throw std::runtime_error(message);
}
void check(const std::filesystem::path &input) {
    using namespace aurora;
    const auto path = std::filesystem::absolute(input).lexically_normal();
    const std::string text = "// café 😀\r\nmodule demo;\r\nauto test() -> i64 {\r\n"
                             "\tconst i64 unused = 7;\r\n\treturn 42;\r\n}\r\n";
    const auto snapshot = std::make_shared<const SourceText>(path.string(), text);
    const SourceOverlays overlays{{path, snapshot}};
    const auto checked = checkSource(path, {}, overlays);
    require(checked.lintDiagnostics.empty(), "default checking enabled lint");
    const auto linted = checkSource(path, {}, overlays, AnalysisMode::Lint, {.emit = true});
    require(linted.lintDiagnostics.size() == 1, "missing overlay warning");
    require(linted.sourceIdentities == checked.sourceIdentities, "lint lost opened-file identities");
    require(!linted.code.empty(), "lint skipped validated IR");
    const auto &warning = linted.lintDiagnostics.at(0);
    require(warning.code == DiagnosticCode::UnreadLocal && warning.severity == DiagnosticSeverity::Warning,
            "explicit warning code and severity");
    require(warning.span.source == snapshot && warning.span.begin.line == 4 && warning.span.begin.column == 12 &&
                warning.span.end.column == 18,
            "warning uses exact overlay snapshot and byte columns");
    std::ostringstream json;
    writeDiagnosticsJson(json, linted.lintDiagnostics);
    require(json.str().find("\"success\":true") != std::string::npos &&
                json.str().find("\"severity\":\"warning\"") != std::string::npos,
            "warning JSON remains successful");
    std::ostringstream mixed;
    writeDiagnosticsJson(mixed, {warning, {DiagnosticCode::Semantic, "error", {}}});
    require(mixed.str().find("\"success\":false") != std::string::npos &&
                mixed.str().find("\"severity\":\"error\"") != std::string::npos,
            "mixed severity JSON fails and legacy default remains error");
    const auto rejected = std::make_shared<const SourceText>(
        path.string(), "module demo; auto test() -> i64 { i64 unused = 1; return false; }");
    bool failed = false;
    try {
        (void)checkSource(path, {}, {{path, rejected}}, AnalysisMode::Lint);
    } catch (const Error &error) {
        failed = true;
        require(error.diagnostic.code == DiagnosticCode::Semantic &&
                    error.diagnostic.severity == DiagnosticSeverity::Error && error.diagnostic.span.source == rejected,
                "failed analysis must preserve source error");
    }
    require(failed, "lint accepted rejected overlay");
    std::cout << "PASS lint frontend: 10 contract checks\n";
}
} // namespace
int main(int argc, char **argv) {
    try {
        require(argc == 2, "expected existing source fixture path");
        check(argv[1]);
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL lint frontend: " << error.what() << '\n';
        return 1;
    }
}
