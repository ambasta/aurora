#include "modules.hpp"
#include "semantics.hpp"
#include "x86.hpp"
#include <fstream>
#include <iostream>

int main(int argc, char **argv) {
    try {
        std::filesystem::path inputPath, outputPath;
        std::vector<std::filesystem::path> roots;
        for (int index = 1; index < argc; ++index) {
            const std::string option = argv[index];
            if (option == "--module-root") {
                if (++index >= argc)
                    throw aurora::Error("--module-root requires a directory");
                roots.emplace_back(argv[index]);
            } else if (option == "-o") {
                if (++index >= argc || !outputPath.empty())
                    throw aurora::Error("exactly one -o OUTPUT.s is required");
                outputPath = argv[index];
            } else if (option.starts_with("-") || !inputPath.empty())
                throw aurora::Error("unknown or duplicate command-line argument: " + option);
            else
                inputPath = option;
        }
        if (inputPath.empty() || outputPath.empty()) {
            std::cerr << "usage: aurorac [--module-root DIR] INPUT.au -o OUTPUT.s\n";
            return 2;
        }
        aurora::ModuleLoader loader(roots);
        auto graph = loader.load(inputPath);
        auto sourceIdentities = graph.sourceIdentities;
        aurora::ModuleResolver resolver(std::move(graph));
        aurora::SemanticAnalyzer analyzer(resolver.resolve());
        auto checked = analyzer.analyze();
        auto result = aurora::X86Emitter{}.emit(checked);
        aurora::host::ArtifactWriter output(outputPath, std::move(sourceIdentities));
        output.write(result);
        output.commit();
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "aurorac: " << error.what() << '\n';
        return 1;
    }
}
