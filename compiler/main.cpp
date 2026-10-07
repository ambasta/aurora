#include "frontend.hpp"
#include "x86.hpp"
#include <iostream>

int main(int argc, char **argv) {
    bool jsonDiagnostics = false;
    // Establish the requested renderer before validating arguments, even when an
    // earlier option is invalid. Values of path-taking options are not flags.
    for (int index = 1; index < argc; ++index) {
        const std::string option = argv[index];
        if (option == "--module-root" || option == "-o")
            ++index;
        else if (option == "--diagnostics=json")
            jsonDiagnostics = true;
    }
    try {
        std::filesystem::path inputPath;
        std::filesystem::path outputPath;
        std::vector<std::filesystem::path> roots;
        bool checkOnly = false;
        bool inputSpecified = false;
        bool outputSpecified = false;
        bool formatSpecified = false;
        const auto argumentError = [](const std::string &message) {
            return aurora::Error(aurora::DiagnosticCode::CommandLine, message);
        };
        for (int index = 1; index < argc; ++index) {
            const std::string option = argv[index];
            if (option == "--module-root") {
                if (++index >= argc)
                    throw argumentError("--module-root requires a directory");
                roots.emplace_back(argv[index]);
            } else if (option == "-o") {
                if (++index >= argc || outputSpecified)
                    throw argumentError("exactly one -o OUTPUT.s is required");
                outputSpecified = true;
                outputPath = argv[index];
            } else if (option == "--check") {
                if (checkOnly)
                    throw argumentError("duplicate --check option");
                checkOnly = true;
            } else if (option == "--diagnostics=json" || option == "--diagnostics=text") {
                if (formatSpecified)
                    throw argumentError("exactly one diagnostic format may be specified");
                formatSpecified = true;
            } else if (option.starts_with("-") || inputSpecified) {
                throw argumentError("unknown or duplicate command-line argument: " + option);
            } else {
                inputSpecified = true;
                inputPath = option;
            }
        }
        if (inputPath.empty() || (!checkOnly && outputPath.empty())) {
            const std::string usage = "usage: aurorac [--module-root DIR] INPUT.au -o OUTPUT.s\n"
                                      "       aurorac --check [--diagnostics=text|json] [--module-root DIR] INPUT.au";
            throw argumentError(usage);
        }
        if (checkOnly && outputSpecified)
            throw argumentError("--check does not accept -o");
        if (jsonDiagnostics && !checkOnly)
            throw argumentError("--diagnostics=json requires --check");
        auto checked = aurora::checkSource(inputPath, roots);
        if (checkOnly) {
            if (jsonDiagnostics)
                aurora::writeDiagnosticsJson(std::cout, {});
            return 0;
        }
        auto result = aurora::X86Emitter{}.emit(checked.module);
        aurora::host::ArtifactWriter output(outputPath, std::move(checked.sourceIdentities));
        output.write(result);
        output.commit();
        return 0;
    } catch (const aurora::Error &error) {
        if (jsonDiagnostics)
            aurora::writeDiagnosticsJson(std::cout, {error.diagnostic});
        else
            aurora::writeDiagnosticText(std::cerr, error.diagnostic, "aurorac");
        return error.diagnostic.code == aurora::DiagnosticCode::CommandLine ? 2 : 1;
    } catch (const std::exception &error) {
        if (jsonDiagnostics)
            aurora::writeDiagnosticsJson(std::cout, {{aurora::DiagnosticCode::Internal, error.what(), {}}});
        else
            aurora::writeDiagnosticText(std::cerr, {aurora::DiagnosticCode::Internal, error.what(), {}}, "aurorac");
        return 1;
    }
}
