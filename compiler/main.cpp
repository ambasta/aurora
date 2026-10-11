#include "frontend.hpp"
#include "x86.hpp"
#include <iostream>

int main(int argc, char **argv) {
    bool jsonDiagnostics = false;
    // Establish the requested renderer before validating arguments, even when an
    // earlier option is invalid. Values of path-taking options are not flags.
    for (int index = 1; index < argc; ++index) {
        const std::string option = argv[index];
        if (option == "--module-root" || option == "-o" || option == "--stack-facts")
            ++index;
        else if (option == "--diagnostics=json")
            jsonDiagnostics = true;
    }
    try {
        std::filesystem::path inputPath;
        std::filesystem::path outputPath;
        std::filesystem::path stackFactsPath;
        std::vector<std::filesystem::path> roots;
        bool checkOnly = false;
        bool localSymbols = false;
        bool referencedReflectionOnly = false;
        bool inputSpecified = false;
        bool outputSpecified = false;
        bool stackFactsSpecified = false;
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
            } else if (option == "--stack-facts") {
                if (++index >= argc || stackFactsSpecified)
                    throw argumentError("--stack-facts requires exactly one output path");
                stackFactsSpecified = true;
                stackFactsPath = argv[index];
            } else if (option == "--local-symbols") {
                if (localSymbols)
                    throw argumentError("duplicate --local-symbols option");
                localSymbols = true;
            } else if (option == "--referenced-reflection-only") {
                if (referencedReflectionOnly)
                    throw argumentError("duplicate --referenced-reflection-only option");
                referencedReflectionOnly = true;
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
            const std::string usage = "usage: aurorac [--local-symbols] [--referenced-reflection-only] [--module-root "
                                      "DIR] INPUT.au -o OUTPUT.s "
                                      "[--stack-facts OUTPUT.json]\n"
                                      "       aurorac --check [--diagnostics=text|json] [--module-root DIR] INPUT.au";
            throw argumentError(usage);
        }
        if (checkOnly && outputSpecified)
            throw argumentError("--check does not accept -o");
        if (checkOnly && stackFactsSpecified)
            throw argumentError("--check does not accept --stack-facts");
        if (stackFactsSpecified && stackFactsPath.empty())
            throw argumentError("--stack-facts requires a nonempty output path");
        if (checkOnly && localSymbols)
            throw argumentError("--check does not accept --local-symbols");
        if (checkOnly && referencedReflectionOnly)
            throw argumentError("--check does not accept --referenced-reflection-only");
        if (jsonDiagnostics && !checkOnly)
            throw argumentError("--diagnostics=json requires --check");
        auto checked = aurora::checkSource(inputPath, roots);
        if (checkOnly) {
            if (jsonDiagnostics)
                aurora::writeDiagnosticsJson(std::cout, {});
            return 0;
        }
        aurora::X86Emitter emitter;
        auto result = emitter.emit(checked.module,
                                   localSymbols ? aurora::SymbolBinding::Local : aurora::SymbolBinding::Default,
                                   referencedReflectionOnly ? aurora::ReflectionEmission::Referenced
                                                            : aurora::ReflectionEmission::All);
        aurora::host::ArtifactWriter output(outputPath, checked.sourceIdentities);
        std::optional<aurora::host::ArtifactWriter> stackFacts;
        if (stackFactsSpecified) {
            stackFacts.emplace(stackFactsPath, std::move(checked.sourceIdentities));
            if (output.sameDestination(*stackFacts))
                throw argumentError("assembly and stack facts require different output paths");
            stackFacts->write(emitter.stackFactsJson());
        }
        output.write(result);
        if (stackFacts)
            stackFacts->commit();
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
