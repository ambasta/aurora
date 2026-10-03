#include "lexer.hpp"
#include "parser.hpp"
#include "semantics.hpp"
#include "x86.hpp"
#include <fstream>
#include <iostream>
#include <sstream>

int main(int argc, char **argv) {
    try {
        if (argc != 4 || std::string(argv[2]) != "-o") {
            std::cerr << "usage: aurorac INPUT.au -o OUTPUT.s\n";
            return 2;
        }
        std::ifstream in(argv[1]);
        if (!in)
            throw aurora::Error("cannot open input");
        std::ostringstream source;
        source << in.rdbuf();
        aurora::Parser parser(aurora::lex(source.str()));
        aurora::SemanticAnalyzer analyzer(parser.parse());
        auto checked = analyzer.analyze();
        auto result = aurora::X86Emitter{}.emit(checked);
        std::ofstream out(argv[3]);
        if (!out)
            throw aurora::Error("cannot open output");
        out << result;
        if (!out)
            throw aurora::Error("cannot write output");
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "aurorac: " << e.what() << '\n';
        return 1;
    }
}
