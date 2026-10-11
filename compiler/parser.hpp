#pragma once
#include "hosted_parser.hpp"

namespace aurora {
// Compatibility entrypoint for module loading, formatting and diagnostics.
// All syntax is parsed by one Aurora invocation; semantic admission remains hosted.
class Parser {
    std::vector<Token> tokens;

public:
    explicit Parser(std::vector<Token> value) : tokens(std::move(value)) {
    }
    Program parse() {
        return parseHostedProgram(tokens);
    }
};
} // namespace aurora
