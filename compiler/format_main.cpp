#include "format.hpp"
#include "frontend.hpp"
#include <iostream>

namespace {
void writeFindings(std::ostream &out, const aurora::format::Result &result, bool json) {
    if (json) {
        out << "{\"schemaVersion\":1,\"mode\":\"format-check\",\"success\":"
            << (!result.changed && result.findings.empty() ? "true" : "false")
            << ",\"changed\":" << (result.changed ? "true" : "false") << ",\"diagnostics\":[";
    }
    bool first = true;
    for (const auto &finding : result.findings) {
        if (json) {
            if (!first)
                out << ',';
            out << "{\"code\":";
            aurora::writeJsonString(out, finding.code);
            out << ",\"severity\":\"warning\",\"message\":";
            aurora::writeJsonString(out, finding.message);
            out << ",\"path\":";
            aurora::writeJsonString(out, finding.span.source->path);
            out << ",\"range\":{\"start\":";
            aurora::writeJsonPosition(out, finding.span.begin);
            out << ",\"end\":";
            aurora::writeJsonPosition(out, finding.span.end);
            out << "}}";
        } else {
            out << finding.span.source->path << ':' << finding.span.begin.line << ':' << finding.span.begin.column
                << ": " << finding.code << ": " << finding.message << '\n';
        }
        first = false;
    }
    if (json)
        out << "]}\n";
    else if (result.changed)
        out << "aurora-fmt: formatting differs\n";
}
} // namespace
int main(int argc, char **argv) {
    bool json = false;
    for (int index = 1; index < argc; ++index) {
        const std::string option = argv[index];
        if (option == "--module-root" || option == "--runtime-root")
            ++index;
        else if (option == "--diagnostics=json")
            json = true;
    }
    try {
        std::filesystem::path input;
        std::vector<std::filesystem::path> roots;
        std::filesystem::path runtimeRoot = AURORA_RUNTIME_ROOT;
        bool check = false, lint = false, formatSpecified = false, runtimeRootSpecified = false;
        const auto argumentError = [](const std::string &message) {
            return aurora::Error(aurora::DiagnosticCode::CommandLine, message);
        };
        for (int index = 1; index < argc; ++index) {
            const std::string option = argv[index];
            if (option == "--check" && !check)
                check = true;
            else if (option == "--lint" && !lint)
                lint = true;
            else if (option == "--module-root") {
                if (++index >= argc)
                    throw argumentError("--module-root requires a directory");
                roots.emplace_back(argv[index]);
            } else if (option == "--runtime-root") {
                if (++index >= argc || runtimeRootSpecified || std::string_view(argv[index]).empty())
                    throw argumentError("--runtime-root requires exactly one nonempty directory");
                runtimeRootSpecified = true;
                runtimeRoot = argv[index];
            } else if ((option == "--diagnostics=json" || option == "--diagnostics=text") && !formatSpecified) {
                formatSpecified = true;
            } else if (!option.starts_with("-") && input.empty()) {
                input = option;
            } else {
                throw argumentError("unknown or duplicate command-line argument: " + option);
            }
        }
        if (input.empty())
            throw argumentError("usage: aurora-fmt [--check [--diagnostics=text|json]] INPUT.au\n"
                                "       aurora-fmt --lint [--diagnostics=text|json] [--module-root DIR] "
                                "[--runtime-root DIR] INPUT.au");
        if ((check && lint) || (!lint && (!roots.empty() || runtimeRootSpecified)) || (json && !check && !lint))
            throw argumentError("--check and --lint are separate modes; --module-root and --runtime-root require "
                                "--lint; JSON requires a check mode");
        if (lint) {
            const auto checked = aurora::checkSource(input, roots, {}, aurora::AnalysisMode::Lint, {}, runtimeRoot);
            if (json)
                aurora::writeDiagnosticsJson(std::cerr, checked.lintDiagnostics);
            else
                for (const auto &diagnostic : checked.lintDiagnostics)
                    aurora::writeDiagnosticText(std::cerr, diagnostic, "aurora-fmt");
            return 0;
        }
        std::string contents;
        try {
            auto file = aurora::host::SourceFile::explicitPath(input);
            contents = file.readAtMost(aurora::format::sourceLimit);
        } catch (const aurora::Error &error) {
            throw error.withDefaultCode(aurora::DiagnosticCode::Module);
        }
        const auto result = aurora::format::source(contents, input.string());
        if (check) {
            writeFindings(std::cerr, result, json);
            return result.changed || !result.findings.empty() ? 1 : 0;
        }
        if (!result.remainingFindings.empty())
            writeFindings(std::cerr, {"", result.remainingFindings, false, {}}, false);
        std::cout << result.text;
        if (!std::cout)
            throw aurora::Error(aurora::DiagnosticCode::Internal, "cannot write formatted output");
        return 0;
    } catch (const aurora::Error &error) {
        if (json)
            aurora::writeDiagnosticsJson(std::cerr, {error.diagnostic});
        else
            aurora::writeDiagnosticText(std::cerr, error.diagnostic, "aurora-fmt");
        return 2;
    } catch (const std::exception &error) {
        if (json)
            aurora::writeDiagnosticsJson(std::cerr, {{aurora::DiagnosticCode::Internal, error.what(), {}}});
        else
            aurora::writeDiagnosticText(std::cerr, {aurora::DiagnosticCode::Internal, error.what(), {}}, "aurora-fmt");
        return 2;
    }
}
